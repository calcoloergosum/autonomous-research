"""Trusted ranked claim adapter; no worker or policy computation in claim transaction."""
import json
import time

from arf.decision_models import Constraints, Policy, bounded
from arf.decisions import DecisionService, feedback_from, profile, selection_from
from arf.plan_models import PlanError, canonical, sha
from arf.replanning import evaluate
from arf.store import utc_now


def derived_id(request_id: str, suffix: str) -> str:
    value = request_id + ':' + suffix
    return value if len(value.encode('utf-8')) <= 4096 else suffix + '-' + sha(canonical(request_id))


def ready_audit(service: DecisionService, bootstrap: dict | None = None) -> dict:
    # Independent of candidate membership. The complete export cap bounds this view.
    tasks = service.store.tasks()
    audit = {'ready': [t['task_id'] for t in tasks if t['status'] == 'pending' and not t['blockers']],
            'blockers': {t['task_id']: t['blockers'] for t in tasks if t['status'] == 'pending' and t['blockers']},
            'pending': [t['task_id'] for t in tasks if t['status'] == 'pending']}
    if bootstrap is not None:
        audit['bootstrap'] = bootstrap
    return audit


def _receipt(service, request_id, request, status, reason, audit, publication=None, assessment=None, claim=None):
    result = {'status': status, 'reason': reason, 'dispatch_id': request_id,
              'recommendation_id': publication['decision_id'] if publication else None,
              'assessment_id': assessment['assessment_id'] if assessment else None, 'audit': audit}
    if claim:
        result.update(task_id=claim['task']['task_id'], run_id=claim['run_id'])
    service.db.execute('INSERT INTO decision_dispatches VALUES (?,?,?,?,?,?,?,?,?,?)',
                       (request_id, sha(bounded(request)), service.study_id,
                        publication['decision_id'] if publication else None,
                        publication['publication_id'] if publication else None,
                        assessment['assessment_id'] if assessment else None,
                        claim['task']['task_id'] if claim else None, claim['run_id'] if claim else None,
                        bounded(result, 262144), utc_now()))
    return {'receipt': result, 'claim': claim, 'replayed': False}


def dispatch_next(service: DecisionService, request_id: str, actor: str = 'trusted-controller') -> dict:
    """Caller must hold controller_lock through claim/execution/finalization.

    Replay returns history with claim=None: it must never run an old attempt.
    """
    request = {'actor': service._actor(actor), 'dispatch_version': 1}
    bootstrap_audit = None
    with service.store.transaction():
        replay = service._replay('decision_dispatches', 'dispatch_id', request_id, request)
        if replay is not None:
            return {'receipt': replay, 'claim': None, 'replayed': True}
        # Complete execution capture bounds scans; fail without truncating observations.
        service.plans.context_bytes()
        audit = ready_audit(service, bootstrap_audit)
        if service.db.execute("SELECT 1 FROM runs WHERE status='running'").fetchone():
            return _receipt(service, request_id, request, 'review_required', 'unfinished_attempt', audit)
        if not audit['ready']:
            reason = 'prerequisites_blocked' if audit['pending'] else 'empty_queue'
            return _receipt(service, request_id, request, 'no_ready_task', reason, audit)
        head = service.head()
    if head is None:
        from arf.bootstrap import bootstrap_initial
        initial = bootstrap_initial(service, derived_id(request_id, 'initial-decision'),
                                    derived_id(request_id, 'initial-publication'), actor)
        bootstrap_audit = initial['audit']
        if initial['reason'] is not None:
            with service.store.transaction():
                replay = service._replay('decision_dispatches', 'dispatch_id', request_id, request)
                if replay is not None:
                    return {'receipt': replay, 'claim': None, 'replayed': True}
                return _receipt(service, request_id, request, 'needs_decision', initial['reason'],
                                ready_audit(service, bootstrap_audit))
        head = initial['publication_id']
    with service.store.transaction():
        publication = service.show_publication(head)
        decision = service.show_decision(publication['decision_id'])
        service.validate_decision(decision)
        original = service.show_context(decision['context_id'])
    # Joint snapshot and relevance inference outside claim/write transaction.
    capture_start = time.monotonic()
    current = service.capture_context(selection_from(original['selection']), feedback_from(original['feedback']))
    heads = service.heads()
    snapshot_seconds = time.monotonic() - capture_start
    assessment_id = derived_id(request_id, 'assessment')
    assessment_request = {'dispatch_id': request_id, 'decision_id': decision['decision_id'],
                          'context_id': current['context_id'], 'heads': heads, 'actor': actor}
    assessment = service._replay('decision_assessments', 'assessment_id', assessment_id, assessment_request)
    if assessment is None:
        assessment = evaluate(original, current, publication['candidate_heads'], heads, decision['constraints'])
        assessment['cost']['snapshot_wall_seconds'] = snapshot_seconds
        assessment['cost']['evaluation_wall_seconds'] = assessment['cost']['wall_seconds']
        assessment['cost']['wall_seconds'] += snapshot_seconds
        assessment.update(assessment_id=assessment_id, decision_id=decision['decision_id'], publication_id=head)
        with service.store.transaction():
            replay = service._replay('decision_dispatches', 'dispatch_id', request_id, request)
            if replay is not None:
                return {'receipt': replay, 'claim': None, 'replayed': True}
            existing = service._replay('decision_assessments', 'assessment_id', assessment_id, assessment_request)
            if existing is not None:
                assessment = existing
            else:
                service.db.execute('INSERT INTO decision_assessments VALUES (?,?,?,?,?,?,?,?)',
                                   (assessment_id, sha(bounded(assessment_request)), service.study_id,
                                    decision['decision_id'], head, current['context_id'],
                                    bounded(assessment, 262144), utc_now()))
    # At most one recomputation/publication; no implicit retries on races/failure.
    if assessment['outcome'] == 'replan':
        updated = service.capture_context(selection_from(original['selection']), feedback_from(assessment['feedback']))
        if (updated['execution_sha256'] != current['execution_sha256']
                or updated['graph'] != current['graph'] or updated['profile'] != current['profile']
                or service.heads() != heads):
            with service.store.transaction():
                return _receipt(service, request_id, request, 'needs_decision', 'state_changed',
                                ready_audit(service, bootstrap_audit), publication, assessment)
        row = service.db.execute('SELECT request FROM research_decisions WHERE decision_id=?',
                                 (decision['decision_id'],)).fetchone()
        saved = json.loads(row[0])
        decision = service.decide(derived_id(request_id, 'replan'), updated['context_id'], heads,
                                  Policy(**saved['policy']), Constraints(**saved['constraints']),
                                  actor='offline-manager', previous_decision_id=decision['decision_id'])
        try:
            publication = service.publish(derived_id(request_id, 'publication'), decision['decision_id'], head)
        except PlanError as exc:
            if exc.code not in ('conflict', 'stale_context'):
                raise
            with service.store.transaction():
                return _receipt(service, request_id, request, 'needs_decision', 'state_changed',
                                ready_audit(service, bootstrap_audit), assessment=assessment)
        current = updated
        head = publication['publication_id']
    with service.store.transaction():
        # Lower-level concurrent requests serialize and replay, even without controller lock.
        replay = service._replay('decision_dispatches', 'dispatch_id', request_id, request)
        if replay is not None:
            return {'receipt': replay, 'claim': None, 'replayed': True}
        audit = ready_audit(service, bootstrap_audit)
        if service.db.execute("SELECT 1 FROM runs WHERE status='running'").fetchone():
            return _receipt(service, request_id, request, 'review_required', 'unfinished_attempt', audit, publication, assessment)
        if service.head() != head or service.heads() != heads or not service._matches(current):
            return _receipt(service, request_id, request, 'needs_decision', 'state_changed', audit, publication, assessment)
        if not audit['ready']:
            return _receipt(service, request_id, request, 'no_ready_task',
                            'prerequisites_blocked' if audit['pending'] else 'empty_queue', audit, publication, assessment)
        if assessment['outcome'] in ('refuse', 'defer'):
            return _receipt(service, request_id, request,
                            'needs_decision' if assessment['outcome'] == 'refuse' else 'deferred',
                            'critical_invalidity' if assessment['outcome'] == 'refuse' else 'assessment_budget',
                            audit, publication, assessment)
        if publication['profile'] != profile():
            raise PlanError('invalid', 'publication execution profile mismatch')
        records = service.validate_decision(decision)
        if any(c['binding'] != m['binding'] for c, m in zip(records, decision['members'])):
            raise PlanError('invalid', 'forged decision member binding')
        covered = {m['binding']['task_id'] for m in decision['members'] if m['binding']}
        audit['unranked_ready'] = sorted(set(audit['ready']) - covered)
        if decision['status'] == 'abstain':
            audit['abstention'] = decision['reason']
            return _receipt(service, request_id, request, 'deferred', 'reasoned_abstention', audit, publication, assessment)
        if audit['unranked_ready']:
            return _receipt(service, request_id, request, 'needs_decision', 'unranked_ready_task', audit, publication, assessment)
        for m in decision['members']:
            if m['priority_group'] is not None and m['binding'] and m['binding']['task_id'] in audit['ready']:
                # Both admission and full TaskSpec were checked above, under this transaction.
                claim = service.store._claim_task_in_transaction(m['binding']['task_id'])
                return _receipt(service, request_id, request, 'claimed', 'ranked_ready_task', audit,
                                publication, assessment, claim)
        return _receipt(service, request_id, request, 'needs_decision', 'no_ranked_ready_task', audit, publication, assessment)
