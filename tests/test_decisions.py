"""VS-004 D1–D13: offline engineering fixtures, never scientific validation."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import sqlite3
import subprocess
import sys
import threading

import pytest

from arf.decision_models import (CandidateDefinition as Definition, Constraints, Costs, Feedback,
                                 Impact, Policy, Rule, Selection, Synthetic)
from arf.decision_policy import rank
from arf.decision_store import DECISION_SCHEMA, migrate_decisions, verify
from arf.decisions import DecisionService
from arf.dispatch import dispatch_next
from arf.executor import WorkerOutput
from arf.graph import GraphService
from arf.graph_models import Actor, QueryLimits, Ref
from arf.graph_store import migrate as graph_migrate
from arf.models import ARFError, Charter, TaskSpec
from arf.plan_models import PlanError, canonical, sha
from arf.plan_store import PlanStore, migrate as plan_migrate
from arf.service import controller_lock, recover, run_next
from arf.store import Store
from conftest import ROOT, spec


@pytest.fixture
def v4(store, monkeypatch):
    import socket
    def no_network(*args, **kwargs):
        raise AssertionError('network forbidden in offline VS-004 tests')
    monkeypatch.setattr(socket, 'socket', no_network)
    monkeypatch.setattr(socket, 'create_connection', no_network)
    plan_migrate(store)
    graph_migrate(store)
    migrate_decisions(store)
    return DecisionService(store)


def definition(key, direct=8, bonus=0, **kw):
    return Definition(key, key, synthetic=Synthetic(direct, direct, bonus, bonus > 0), **kw)


def setup(v4, keys=('A', 'B'), rules=True, definitions=None, policy=Policy()):
    for key in keys:
        v4.store.add_task(TaskSpec.parse(spec(key)))
    defs = definitions or [definition(k, 8 if k == 'A' else 1, 12 if k == 'B' else 0, origin_order=i)
                           for i, k in enumerate(keys)]
    versions = v4.record_candidates('batch', defs, {k: k for k in keys}, 'fixture')['versions']
    feedback = Feedback(rules=tuple(Rule(k, v4.binding(k)['spec_sha256'], 'engineering_only') for k in keys)) if rules else Feedback()
    context = v4.capture_context(feedback=feedback)
    decision = v4.decide('rank', context['context_id'], versions, policy)
    publication = v4.publish('publication', 'rank', None)
    return context, decision, publication


def legacy_dump(store):
    return {table: [tuple(r) for r in store.connection.execute(f'SELECT * FROM {table}')]
            for table in ('studies', 'tasks', 'dependencies', 'runs', 'evidence', 'plan_contexts',
                          'plan_requests', 'plan_proposals', 'plan_results', 'plan_decisions', 'plan_receipts',
                          'graph_operations', 'graph_ideas', 'graph_idea_revisions', 'graph_links',
                          'graph_link_revisions', 'graph_registrations', 'graph_baselines', 'graph_transitions')}


def test_d13_same_command_reverse_fifo_and_two_claim_reuse(v4):
    context, decision, publication = setup(v4)
    before = legacy_dump(v4.store)
    assert not before['runs']
    first = run_next(v4.store)
    second = run_next(v4.store)
    assert [first['task_id'], second['task_id']] == ['B', 'A']
    assert first['recommendation_id'] == second['recommendation_id'] == 'rank'
    assert first['assessment_id'] != second['assessment_id']
    check = v4.show_assessment(second['assessment_id'])
    assert check['outcome'] == 'reuse'
    assert any(r.startswith('synthetic_engineering_only:') for r in check['reasons'])
    assert check['cost']['wall_seconds'] >= 0
    assert v4.show_context(context['context_id'])['execution']['runs'] == []
    assert len(v4.list_decisions()['items']) == 1
    replay = dispatch_next(v4, first['dispatch_id'])
    assert replay['replayed'] and replay['claim'] is None
    assert replay['receipt']['run_id'] == first['run']['run_id']
    assert len(v4.store.evidence()) == 2
    assert run_next(v4.store)['reason'] == 'empty_queue'
    for e in v4.store.evidence():
        assert e['validation_status'] == 'unvalidated'
    assert v4.store.study()['source'] == before['studies'][0][5]
    assert first['run']['cost']['cpu_seconds'] is None
    assert first['run']['cost']['llm_tokens'] == 0


def test_fifo_bypass_refuses(v4):
    setup(v4)
    with pytest.raises(ARFError, match='ranked_dispatch_required'):
        v4.store.claim_next()
    assert not v4.store.evidence()


def test_relevant_evidence_replans_and_alternative_changes_rank(v4):
    defs = [definition('A', origin_order=0), definition('B', 1, 12, origin_order=1),
            replace(definition('C', origin_order=2), synthetic=Synthetic(14, 0))]
    setup(v4, ('A', 'B', 'C'), definitions=defs)
    # New exact context uses a diagnostic rule, not a future branch oracle.
    fb = Feedback(rules=tuple(Rule(k, v4.binding(k)['spec_sha256'],
                                    'branch_from_mean' if k == 'B' else 'engineering_only') for k in ('A', 'B', 'C')))
    context = v4.capture_context(feedback=fb)
    versions = v4.heads()
    v4.decide('diagnostic', context['context_id'], versions)
    v4.publish('diagnostic-publication', 'diagnostic', 'publication')
    first = run_next(v4.store)
    assert first['task_id'] == 'B'
    second = run_next(v4.store)
    assert second['task_id'] == 'C'
    assert second['recommendation_id'] != first['recommendation_id']
    check = v4.show_assessment(second['assessment_id'])
    assert check['outcome'] == 'replan'
    new = v4.show_decision(second['recommendation_id'])
    revealed = v4.show_context(new['context_id'])
    assert revealed['feedback']['branch'] == 'viable'
    assert new['previous'] == 'diagnostic'
    assert new['members'][0]['estimate']['wall_source'] == 'observed_same_fixed_worker_median'
    # Same pure estimator, alternative *revealed* feedback changes C's value.
    counter = dict(revealed, feedback=dict(revealed['feedback'], branch='nonviable'))
    result = rank(counter, [v4.candidate(*p) for p in versions], Policy(), Constraints())
    assert result['members'][0]['binding']['task_id'] == 'A'


def test_unknown_evidence_refuses_even_without_graph_links(v4):
    setup(v4, rules=False)
    assert run_next(v4.store)['task_id'] == 'B'
    result = run_next(v4.store)
    assert result['status'] == 'needs_decision'
    assert result['reason'] == 'critical_invalidity'
    assert v4.show_assessment(result['assessment_id'])['outcome'] == 'refuse'
    assert len(v4.store.evidence()) == 1


def test_d2_arrival_versions_and_batch_replay(v4):
    setup(v4)
    old = v4.show_decision('rank')
    d = definition('D', 20)
    v4.store.add_task(TaskSpec.parse(spec('D')))
    batch = v4.record_candidates('arrival', [d], {'D': 'D'}, 'fixture')
    assert v4.record_candidates('arrival', [d], {'D': 'D'}, 'fixture') == batch
    assert v4.record_candidates('new-receipt', [d], {'D': 'D'}, 'fixture')['versions'] == batch['versions']
    with pytest.raises(PlanError, match='conflict'):
        v4.record_candidates('arrival', [d], {'D': 'D'}, 'other')
    changed = replace(d, version=2, previous=1, description='new interpretation')
    v4.record_candidates('revision', [changed], {'D': 'D'}, 'fixture')
    with pytest.raises(PlanError, match='conflict'):
        v4.record_candidates('conflict', [replace(changed, description='competing')], {'D': 'D'}, 'fixture')
    assert run_next(v4.store)['task_id'] == 'D'
    assert v4.show_decision('rank') == old


def test_d4_qualitative_incomparable_unknown_costs_and_no_evidence(v4):
    for state in ('qualitative', 'unknown', 'incomparable', 'contested'):
        d = Definition(state, state, impact=Impact(status=state))
        pairs = v4.record_candidates(state, [d], {}, 'fixture')['versions']
        ctx = v4.capture_context()
        saved = v4.decide('decision-' + state, ctx['context_id'], pairs)
        assert saved['status'] == 'abstain'
        assert saved['members'][0]['estimate']['impact']['status'] == state
        assert saved['members'][0]['estimate']['direct'] is None
    assert v4.store.evidence() == []
    assert v4.store.tasks() == []


@pytest.mark.parametrize('cost,ceiling,reason', [(None, 10, 'unknown_required_cost'), (11, 10, 'cost_ceiling')])
def test_missing_or_expensive_cost_excluded(v4, cost, ceiling, reason):
    d = replace(definition('A'), synthetic=Synthetic(8, 8, costs=Costs(synthetic_tokens=cost)))
    c, result, p = setup(v4, ('A',), definitions=[d])
    assert result['status'] == 'abstain'
    assert result['members'][0]['exclusion'].startswith(reason)
    assert run_next(v4.store)['status'] == 'deferred'


def test_policy_redundancy_adverse_case_and_saved_recomputation(v4):
    context, saved, p = setup(v4)
    pairs = v4.heads()
    records = [v4.candidate(*pair) for pair in pairs]
    again = rank(context, records, Policy(), Constraints())
    assert again['members'] == saved['members']
    static = rank(context, records, Policy('static'), Constraints())
    assert static['members'][0]['binding']['task_id'] == 'A'
    known = dict(context, feedback=dict(context['feedback'], branch='viable'))
    known_rank = rank(known, records, Policy(), Constraints())
    assert known_rank['members'][0]['binding']['task_id'] == 'A'
    # Bad diagnostic bonus can waste a synthetic budget: actual branch already known
    # by an evaluator, hidden from the algorithm; choosing B yields only 1 vs A's 8.
    assert saved['members'][0]['estimate']['direct'] == 1
    assert static['members'][0]['estimate']['direct'] == 8


def test_unmapped_and_blocked_rank_skipped_and_ready_independent(v4):
    v4.store.add_task(TaskSpec.parse(spec('prerequisite')))
    v4.store.add_task(TaskSpec.parse(spec('blocked', ['prerequisite'])))
    v4.store.add_task(TaskSpec.parse(spec('ready')))
    defs = [definition('idea', 100), definition('blocked', 90), definition('ready', 8), definition('prerequisite', 1)]
    pairs = v4.record_candidates('batch', defs, {k: k for k in ('blocked', 'ready', 'prerequisite')}, 'fixture')['versions']
    c = v4.capture_context()
    v4.decide('rank', c['context_id'], pairs)
    v4.publish('publication', 'rank', None)
    out = run_next(v4.store)
    assert out['task_id'] == 'ready'
    receipt = v4.show_dispatch(out['dispatch_id'])
    assert receipt['audit']['blockers']['blocked'][0]['task_id'] == 'prerequisite'
    assert v4.store.task('blocked')['status'] == 'pending'


def test_unranked_ready_not_false_no_ready_or_fifo(v4):
    setup(v4, ('A',))
    v4.store.add_task(TaskSpec.parse(spec('unranked')))
    result = run_next(v4.store)
    assert result['status'] == 'needs_decision'
    assert result['reason'] == 'unranked_ready_task'
    assert set(result['audit']['ready']) == {'A', 'unranked'}
    assert not v4.store.evidence()


def test_true_empty_blocked_missing_capacity_and_abstain(v4):
    assert run_next(v4.store)['reason'] == 'empty_queue'
    v4.store.add_task(TaskSpec.parse(spec('A')))
    missing = run_next(v4.store)
    assert missing['status'] == 'needs_decision' and missing['reason'] == 'missing'
    with v4.store.transaction():
        claim = v4.store._claim_task_in_transaction('A')
    assert run_next(v4.store)['reason'] == 'unfinished_attempt'
    recover(v4.store)
    v4.store.add_task(TaskSpec.parse(spec('B', ['A'])))
    assert run_next(v4.store)['reason'] == 'prerequisites_blocked'
    assert v4.store.task('A')['status'] == 'needs_review'


def test_truncated_selection_abstains_and_limits(v4):
    v4.store.add_task(TaskSpec.parse(spec('A')))
    pairs = v4.record_candidates('batch', [definition('A')], {'A': 'A'}, 'fixture')['versions']
    ctx = v4.capture_context(Selection(limits=QueryLimits(nodes=1)))
    assert not ctx['selection_complete'] and ctx['graph']['frontier']
    v4.decide('rank', ctx['context_id'], pairs)
    v4.publish('publication', 'rank', None)
    assert run_next(v4.store)['status'] == 'deferred'
    assert not v4.store.evidence()
    with pytest.raises(PlanError, match='limit'):
        v4.list_decisions(65)


def test_admission_unimported_and_duplicate_mapping_refuse(v4):
    from arf.planning import propose
    from arf.authorization import decide
    ctx = v4.plans.export()['context_sha256']
    p = propose(v4.plans, ctx, 'proposal', 'task')
    envelope = v4.plans.validate_proposal(p['proposal_id'])[1]
    task_id = envelope['action']['task_spec']['task_id']
    for approved in (False, True):
        if approved:
            decide(v4.plans, p['proposal_id'], 'approve', 'operator')
        with pytest.raises(ARFError):
            v4.record_candidates('unimported', [definition('X')], {'X': task_id}, 'fixture')
    assert not v4.heads()
    v4.store.add_task(TaskSpec.parse(spec('A')))
    pairs = v4.record_candidates('mapped', [definition('X'), definition('Y')], {'X': 'A', 'Y': 'A'}, 'fixture')['versions']
    c = v4.capture_context()
    with pytest.raises(PlanError, match='duplicate mapped'):
        v4.decide('bad', c['context_id'], pairs)
    assert not v4.list_decisions()['items']


def test_imported_admission_remains_usable_after_old_context_stales(v4):
    from arf.planning import propose
    from arf.authorization import decide, import_proposal
    ctx = v4.plans.export()['context_sha256']
    p = propose(v4.plans, ctx, 'proposal', 'task')
    decide(v4.plans, p['proposal_id'], 'approve', 'operator')
    imported = import_proposal(v4.plans, p['proposal_id'])
    task_id = imported['task_id']
    pairs = v4.record_candidates('mapped', [definition('imported')], {'imported': task_id}, 'fixture')['versions']
    context = v4.capture_context()
    v4.decide('rank', context['context_id'], pairs)
    v4.publish('publication', 'rank', None)
    assert run_next(v4.store)['task_id'] == task_id
    assert v4.binding(task_id)['admission']['kind'] == 'approved_import'
    assert import_proposal(v4.plans, p['proposal_id']) == imported


def test_d6_restart_replay_conflicts_and_no_reexecution(v4):
    context, d, p = setup(v4)
    with controller_lock(v4.store.path):
        claim = dispatch_next(v4, 'explicit')
    assert claim['claim']
    receipt = claim['receipt']
    recover(v4.store)
    v4.store.retry(receipt['task_id'])
    with Store(v4.store.path) as store:
        reopened = DecisionService(store)
        # Original request order is batch order, not sorted ranking.
        pairs = json.loads(store.connection.execute("SELECT request FROM research_decisions WHERE decision_id='rank'").fetchone()[0])['candidates']
        assert reopened.decide('rank', context['context_id'], pairs) == d
        assert reopened.publish('publication', 'rank', None) == p
        current = reopened.capture_context()
        reopened.decide('replacement-rank', current['context_id'], reopened.heads())
        reopened.publish('replacement-publication', 'replacement-rank', 'publication')
        replay = dispatch_next(reopened, 'explicit')
        assert replay['replayed'] and replay['claim'] is None and replay['receipt'] == receipt
        assert len(store.task(receipt['task_id'])['runs']) == 1
        with pytest.raises(PlanError, match='conflict'):
            dispatch_next(reopened, 'explicit', 'different')


def test_nonclaim_replay_after_state_changes(v4):
    first = dispatch_next(v4, 'empty')
    setup(v4)
    second = dispatch_next(v4, 'empty')
    assert second['receipt'] == first['receipt'] and second['claim'] is None
    assert not v4.store.evidence()


def test_receipt_failure_rolls_back_claim(v4):
    setup(v4)
    v4.db.execute("CREATE TRIGGER inject_receipt BEFORE INSERT ON decision_dispatches BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(sqlite3.IntegrityError, match='injected'):
        run_next(v4.store)
    assert all(t['status'] == 'pending' for t in v4.store.tasks())
    assert not list(v4.db.execute('SELECT * FROM runs'))
    assert not list(v4.db.execute('SELECT * FROM decision_dispatches'))


@pytest.mark.parametrize('interruption', ['worker', 'finalize'])
def test_committed_claim_interruption_and_recovery(v4, monkeypatch, interruption):
    setup(v4)
    def crash(*a, **kw):
        raise KeyboardInterrupt()
    if interruption == 'finalize':
        monkeypatch.setattr(v4.store, 'finish_run', crash)
        with pytest.raises(KeyboardInterrupt):
            run_next(v4.store)
    else:
        with pytest.raises(KeyboardInterrupt):
            run_next(v4.store, crash)
    task = v4.store.task('B')
    assert task['status'] == 'running'
    assert len(list(v4.db.execute('SELECT * FROM decision_dispatches'))) == 1
    assert run_next(v4.store)['status'] == 'review_required'
    assert recover(v4.store)['interrupted'][0]['task_id'] == 'B'
    assert not recover(v4.store)['interrupted']
    assert run_next(v4.store)['status'] == 'needs_decision'
    assert v4.store.task('B')['status'] == 'needs_review'


@pytest.mark.parametrize('output', [WorkerOutput('not json', '', 0), WorkerOutput('', 'failure', 2)])
def test_failed_worker_replay_never_retries(v4, output):
    setup(v4)
    result = run_next(v4.store, lambda _: output)
    assert result['status'] == 'failed'
    receipt = v4.show_dispatch(result['dispatch_id'])
    assert dispatch_next(v4, result['dispatch_id'])['receipt'] == receipt
    assert not v4.store.evidence()
    assert v4.store.task('B')['status'] == 'failed'


def test_claim_race_rechecks_publication_graph_and_execution(v4, monkeypatch):
    setup(v4)
    import arf.dispatch as module
    original = module.evaluate
    def change(*args):
        assessment = original(*args)
        v4.store.add_task(TaskSpec.parse(spec('race')))
        return assessment
    monkeypatch.setattr(module, 'evaluate', change)
    result = run_next(v4.store)
    assert result['reason'] == 'state_changed'
    assert not v4.store.evidence()


def test_graph_change_replans_operator_baseline_and_no_mutation(v4):
    setup(v4)
    g = GraphService(v4.store)
    actor = Actor('operator', 'operator', 'fixture')
    b = g.create_baseline(operation_id='baseline', actor=actor, scope='fixture', method='fixture', configuration='one')
    g.record_baseline_transition(operation_id='transition', actor=actor, scope='fixture',
                                new_baseline=b['result']['baseline_id'], expected_prior=None,
                                rationale='Initial fixture reference', motivations=())
    seq = g.sequence()
    out = run_next(v4.store)
    assert out['recommendation_id'] != 'rank'
    assert v4.show_assessment(out['assessment_id'])['outcome'] == 'replan'
    assert g.sequence() == seq


def test_publication_head_compare_and_swap(v4):
    ctx, d, p = setup(v4)
    with pytest.raises(PlanError, match='conflict'):
        v4.publish('competitor', 'rank', None)
    assert v4.head() == 'publication'
    assert v4.publish('replacement', 'rank', 'publication')['previous'] == 'publication'
    assert len(list(v4.db.execute('SELECT * FROM runs'))) == 0


def test_unsupported_hard_constraint_atomic(v4):
    v4.store.add_task(TaskSpec.parse(spec('A')))
    pairs = v4.record_candidates('batch', [definition('A')], {'A': 'A'}, 'fixture')['versions']
    c = v4.capture_context()
    with pytest.raises(PlanError, match='unsupported_resource_constraint'):
        v4.decide('bad', c['context_id'], pairs, constraints=Constraints(hard=('total_cpu_quota',)))
    assert not v4.list_decisions()['items']


def test_d3_joint_snapshot_and_public_graph_nesting_refusal(v4, monkeypatch):
    setup(v4)
    # First read establishes snapshot; concurrent writer commits under WAL.
    v4.db.execute('PRAGMA journal_mode=WAL')
    original = v4.plans.context_bytes
    def read_then_write():
        raw = original()
        with Store(v4.store.path) as other:
            other.add_task(TaskSpec.parse(spec('after-snapshot')))
        return raw
    monkeypatch.setattr(v4.plans, 'context_bytes', read_then_write)
    context = v4.capture_context()
    assert 'after-snapshot' not in {t['task_id'] for t in context['execution']['tasks']}
    assert 'after-snapshot' not in {n.get('ref', {}).get('id') for n in context['graph']['nodes']}
    with v4.store.transaction(), pytest.raises(PlanError, match='own consistent'):
        v4.graph.read_graph()


def test_populated_v3_migration_preserves_every_legacy_row(store):
    from arf.graph_demo import build
    # Use existing demo to populate all three legacy milestones.
    path = store.path.parent / 'populated.db'
    build(path)
    with Store(path) as legacy:
        plans = PlanStore(legacy)
        before = legacy_dump(legacy)
        execution = plans.export()
        before = legacy_dump(legacy)
        assert migrate_decisions(legacy)['status'] == 'migrated'
        assert legacy_dump(legacy) == before
        assert plans.export() == execution
        assert migrate_decisions(legacy)['status'] == 'already_current'
        assert plan_migrate(legacy) == {'schema_version': 2, 'status': 'already_current'}
        assert graph_migrate(legacy) == {'schema_version': 3, 'status': 'already_current'}
        assert legacy.connection.execute('PRAGMA user_version').fetchone()[0] == 4
        verify(legacy)


def test_migration_rollback_and_unknown_schema(store):
    plan_migrate(store)
    graph_migrate(store)
    def deny(action, one, two, db, source):
        return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_CREATE_TRIGGER and one.startswith('decision_') else sqlite3.SQLITE_OK
    store.connection.set_authorizer(deny)
    with pytest.raises(sqlite3.DatabaseError):
        migrate_decisions(store)
    store.connection.set_authorizer(None)
    assert store.connection.execute('PRAGMA user_version').fetchone()[0] == 3
    assert not store.connection.execute("SELECT 1 FROM sqlite_master WHERE name='decision_contexts'").fetchone()
    store.connection.execute('CREATE TABLE foreign_table (x)')
    with pytest.raises(PlanError, match='schema'):
        migrate_decisions(store)
    assert store.connection.execute('PRAGMA user_version').fetchone()[0] == 3


@pytest.mark.parametrize('version', [1, 2])
def test_requires_explicit_v3(store, version):
    if version == 2:
        plan_migrate(store)
    with pytest.raises(PlanError, match='schema'):
        migrate_decisions(store)


@pytest.mark.parametrize('table', ['decision_contexts', 'decision_candidates', 'decision_batches',
                                    'research_decisions', 'decision_members', 'decision_publications',
                                    'decision_assessments', 'decision_dispatches'])
def test_append_only_guards(v4, table):
    setup(v4)
    run_next(v4.store)
    for action in ('UPDATE', 'DELETE'):
        statement = f'DELETE FROM {table}' if action == 'DELETE' else f'UPDATE {table} SET study_id=study_id'
        with pytest.raises(sqlite3.IntegrityError, match='immutable'):
            v4.db.execute(statement)


def test_concurrent_candidate_expected_prior_and_publication(v4):
    setup(v4)
    barrier = threading.Barrier(2)
    def revise(label):
        with Store(v4.store.path) as store:
            service = DecisionService(store)
            d = replace(definition('A'), description=label, version=2, previous=1)
            barrier.wait()
            try:
                return service.record_candidates(label, [d], {'A': 'A'}, 'fixture')
            except PlanError as exc:
                return exc.code
    with ThreadPoolExecutor(2) as pool:
        outcomes = list(pool.map(revise, ('one', 'two')))
    assert sum(isinstance(r, dict) for r in outcomes) == 1
    assert outcomes.count('conflict') == 1


def test_controller_lock_two_claimers(v4):
    setup(v4)
    entered = threading.Event()
    release = threading.Event()
    def worker(_):
        entered.set()
        assert release.wait(5)
        return WorkerOutput('{"mean":5.0,"count":4}', '', 0)
    def invoke():
        with Store(v4.store.path) as store:
            return run_next(store, worker)
    with ThreadPoolExecutor(1) as pool:
        future = pool.submit(invoke)
        assert entered.wait(5)
        with Store(v4.store.path) as store, pytest.raises(ARFError, match='busy'):
            run_next(store)
        release.set()
        assert future.result()['task_id'] == 'B'
    assert len(v4.store.evidence()) == 1


@pytest.mark.parametrize('change', ['graph', 'publication', 'admission'])
def test_concurrent_change_between_relevance_and_claim_refuses(v4, monkeypatch, change):
    setup(v4)
    import arf.dispatch as module
    original = module.evaluate
    def mutate(*args):
        check = original(*args)
        with Store(v4.store.path) as other:
            service = DecisionService(other)
            if change == 'admission':
                other.add_task(TaskSpec.parse(spec('concurrent')))
            elif change == 'publication':
                service.publish('competing-publication', 'rank', 'publication')
            else:
                service.graph.create_human_idea(operation_id='concurrent-graph',
                    actor=Actor('operator', 'operator', 'fixture'), kind='H', text='Concurrent premise')
        return check
    monkeypatch.setattr(module, 'evaluate', mutate)
    out = run_next(v4.store)
    assert out['reason'] == 'state_changed'
    assert not v4.store.evidence()
    assert not list(v4.db.execute('SELECT * FROM runs'))


def test_new_evidence_or_admission_during_replan_capture_not_silently_accepted(v4, monkeypatch):
    setup(v4)
    v4.store.add_task(TaskSpec.parse(spec('D')))
    v4.record_candidates('D', [definition('D', 20)], {'D': 'D'}, 'fixture')
    original = DecisionService.capture_context
    calls = []
    def capture(service, *a, **kw):
        calls.append(1)
        if len(calls) == 2:
            service.store.add_task(TaskSpec.parse(spec('during-replan')))
        return original(service, *a, **kw)
    monkeypatch.setattr(DecisionService, 'capture_context', capture)
    out = run_next(v4.store)
    assert out['reason'] == 'state_changed'
    assert not v4.store.evidence()
    assert len(v4.list_decisions()['items']) == 1


def test_explicit_retry_same_dispatch_after_receipt_rollback(v4):
    setup(v4)
    v4.db.execute("CREATE TRIGGER fail_receipt BEFORE INSERT ON decision_dispatches BEGIN SELECT RAISE(ABORT,'injected'); END")
    with pytest.raises(sqlite3.IntegrityError):
        dispatch_next(v4, 'retryable')
    check = v4.show_assessment('retryable:assessment')
    v4.db.execute('DROP TRIGGER fail_receipt')
    result = dispatch_next(v4, 'retryable')
    assert result['claim']['task']['task_id'] == 'B'
    assert v4.show_assessment('retryable:assessment') == check
    recover(v4.store)


def test_finalize_database_failure_retains_running_claim(v4):
    setup(v4)
    v4.db.execute("CREATE TRIGGER fail_evidence BEFORE INSERT ON evidence BEGIN SELECT RAISE(ABORT,'injected evidence'); END")
    with pytest.raises(sqlite3.IntegrityError, match='injected evidence'):
        run_next(v4.store)
    assert v4.store.task('B')['status'] == 'running'
    assert not v4.store.evidence()
    receipt = json.loads(v4.db.execute('SELECT result FROM decision_dispatches').fetchone()[0])
    assert receipt['status'] == 'claimed'
    assert dispatch_next(v4, receipt['dispatch_id'])['claim'] is None
    recover(v4.store)
    assert v4.store.task('B')['status'] == 'needs_review'


@pytest.mark.parametrize('stdout', ['not json', '', '{"mean":NaN,"count":4}', '{"mean":5,"count":true}',
                                    '{"mean":5,"count":3}', '{"mean":5,"count":4,"claim":"validated"}',
                                    '{"mean":5,"mean":0,"count":4}', 'x' * 5000,
                                    '{"mean":100,"count":4}', '{"mean":5.000000000000001,"count":4}'])
def test_v4_shared_lifecycle_invalid_output(v4, stdout):
    setup(v4)
    result = run_next(v4.store, lambda _: WorkerOutput(stdout, '', 0))
    assert result['status'] == 'failed'
    assert v4.store.task('B')['status'] == 'failed'
    assert not v4.store.evidence()
    assert len(result['run']['stdout']) <= 4096


@pytest.mark.parametrize('values,mean', [([1e308, 1., -1e308], 1/3), ([5e-324, 5e-324], 5e-324), ([1e308, -1e308], 0.)])
def test_v4_shared_numerical_result_validation(v4, values, mean):
    v4.store.add_task(TaskSpec.parse(spec('A', input={'values': values})))
    pairs = v4.record_candidates('batch', [definition('A')], {'A': 'A'}, 'fixture')['versions']
    ctx = v4.capture_context()
    v4.decide('rank', ctx['context_id'], pairs)
    v4.publish('publication', 'rank', None)
    assert run_next(v4.store)['run']['result']['mean'] == mean


def test_v4_timeout_and_exception(v4, monkeypatch):
    setup(v4)
    def timed_out(*args, **kw):
        assert kw['timeout'] == 5 and kw['env'] == {}
        raise subprocess.TimeoutExpired(args[0], kw['timeout'])
    monkeypatch.setattr(subprocess, 'run', timed_out)
    result = run_next(v4.store)
    assert result['status'] == 'failed'
    assert 'timed out' in result['run']['error']
    assert not v4.store.evidence()


def test_incomplete_relevance_and_budget_defer(v4, monkeypatch):
    setup(v4)
    import arf.replanning as module
    monkeypatch.setattr(module, 'CHECK_SECONDS', -1)
    result = run_next(v4.store)
    assert result['status'] == 'deferred' and result['reason'] == 'assessment_budget'
    assert v4.show_assessment(result['assessment_id'])['outcome'] == 'defer'
    assert not v4.store.evidence()


def test_deterministic_ties_and_null_cpu_filter(v4):
    defs = [definition('A', 8), definition('B', 8)]
    c, result, p = setup(v4, definitions=defs)
    assert [m['candidate_id'] for m in result['members']] == sorted(m['candidate_id'] for m in result['members'])
    missing = v4.decide('cpu-required', c['context_id'], v4.heads(), constraints=Constraints({'cpu_seconds': 1}))
    assert missing['status'] == 'abstain'
    assert all(m['exclusion'] == 'unknown_required_cost:cpu_seconds' for m in missing['members'])


def test_money_currency_is_never_implicitly_exchanged(v4):
    d = replace(definition('A'), synthetic=Synthetic(8, 8, costs=Costs(money=2, currency='USD')))
    c, result, p = setup(v4, ('A',), definitions=[d])
    with pytest.raises(PlanError, match='explicit currency'):
        v4.decide('money-no-unit', c['context_id'], v4.heads(), constraints=Constraints({'money': 10}))
    incomparable = v4.decide('money-other', c['context_id'], v4.heads(),
                            constraints=Constraints({'money': 10}, currency='EUR'))
    assert incomparable['members'][0]['exclusion'] == 'incomparable_currency'


def test_candidate_batch_atomicity_and_expected_prior(v4):
    a, bad = definition('A'), replace(definition('bad'), version=2, previous=1)
    with pytest.raises(PlanError, match='conflict'):
        v4.record_candidates('atomic', [a, bad], {}, 'fixture')
    assert v4.heads() == []
    assert not list(v4.db.execute('SELECT * FROM decision_batches'))
    with pytest.raises(PlanError):
        v4.record_candidates('inject-binding', [a], {'unknown': 'x'}, 'fixture')


@pytest.mark.parametrize('definition_change', [
    {'description': ''}, {'description': 'x' * 4097}, {'kind': 'shell'}, {'version': True},
    {'origin_sha256': 'wrong'}, {'refs': (Ref('T', 'absent'),)},
    {'synthetic': Synthetic(-1, 0)}, {'synthetic': Synthetic(1, 1, costs=Costs(wall_seconds=float('nan')))},
])
def test_malformed_definition_refuses_without_partial_rows(v4, definition_change):
    with pytest.raises((PlanError, ARFError)):
        v4.record_candidates('bad', [replace(definition('A'), **definition_change)], {}, 'fixture')
    assert not v4.heads()


def test_selection_limits_and_snapshot_size_refusal(v4, monkeypatch):
    with pytest.raises(PlanError):
        v4.capture_context(Selection(roles=('invalid',)))
    with pytest.raises(PlanError):
        v4.capture_context(Selection(limits=QueryLimits(nodes=1025)))
    # Preserve the existing complete execution-component cap; never drop evidence.
    monkeypatch.setattr('arf.plan_store.CONTEXT_LIMIT', 10)
    with pytest.raises(PlanError, match='1 MiB'):
        v4.capture_context()
    assert not list(v4.db.execute('SELECT * FROM decision_contexts'))


def test_unknown_future_feedback_is_not_accepted(v4):
    setup(v4)
    with pytest.raises(PlanError, match='unrevealed'):
        v4.capture_context(feedback=Feedback(branch='viable'))
    with pytest.raises(PlanError):
        v4.capture_context(feedback=Feedback(evidence_refs=('missing',)))
    assert not v4.store.evidence()


def test_forged_candidate_binding_cannot_claim(v4):
    setup(v4)
    # Trusted host corruption simulation: restore the exact guards before reading.
    row = v4.db.execute('SELECT * FROM decision_candidates LIMIT 1').fetchone()
    body = json.loads(row['body'])
    body['binding']['spec_sha256'] = 'f' * 64
    v4.db.execute('DROP TRIGGER decision_candidates_no_update')
    v4.db.execute('UPDATE decision_candidates SET body=? WHERE candidate_id=?', (canonical(body), row['candidate_id']))
    v4.db.execute(next(s for s in DECISION_SCHEMA if s.startswith('CREATE TRIGGER decision_candidates_no_update ')))
    with pytest.raises(PlanError, match='binding differs'):
        run_next(v4.store)
    assert not list(v4.db.execute('SELECT * FROM runs'))


def test_concurrent_publications_only_one_expected_head_wins(v4):
    setup(v4)
    barrier = threading.Barrier(2)
    def publish(label):
        with Store(v4.store.path) as store:
            service = DecisionService(store)
            barrier.wait()
            try:
                return service.publish(label, 'rank', 'publication')
            except PlanError as exc:
                return exc.code
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(publish, ('one', 'two')))
    assert sum(isinstance(r, dict) for r in results) == 1
    assert results.count('conflict') == 1


def test_concurrent_exact_decision_request_replays(v4):
    context, d, p = setup(v4)
    candidates = json.loads(v4.db.execute("SELECT request FROM research_decisions WHERE decision_id='rank'").fetchone()[0])['candidates']
    barrier = threading.Barrier(2)
    def decide(label):
        with Store(v4.store.path) as store:
            service = DecisionService(store)
            barrier.wait()
            return service.decide('same-request', context['context_id'], candidates)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(decide, ('one', 'two')))
    assert results[0] == results[1]
    assert v4.db.execute("SELECT count(*) FROM research_decisions WHERE decision_id='same-request'").fetchone()[0] == 1


def test_demo_and_separate_process_restart(v4, tmp_path):
    path = tmp_path / 'scenario.db'
    process = subprocess.run([sys.executable, '-m', 'arf.decision_demo', '--db', str(path)],
                             cwd=ROOT, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    built = json.loads(process.stdout)
    restarted = subprocess.run([sys.executable, '-m', 'arf.decision_demo', '--inspect', '--db', str(path)],
                               cwd=ROOT, capture_output=True, text=True)
    assert restarted.returncode == 0, restarted.stderr
    current = json.loads(restarted.stdout)
    assert [o['task_id'] for o in built['outcomes']] == ['B', 'A', 'C', 'D']
    assert current['decisions'] == built['decisions']
    assert current['evidence'] == built['evidence']
    assert current['dispatches'] == built['dispatches']
    assert len(current['evidence']) == 4
    assert built['deferred']['status'] == 'deferred'
    assert built['counterfactual_C_direct'] == [14, 0]
    assert built['bad_policy_case']['static_first_actual_payoff'] > built['bad_policy_case']['information_first_actual_payoff']
    assert all('oracle' not in json.dumps(d['members']) for d in built['decisions'])
    again = subprocess.run([sys.executable, '-m', 'arf.decision_demo', '--db', str(path)], capture_output=True, text=True)
    assert again.returncode != 0


def test_public_v4_cli_same_command_json_and_old_migrations(v4):
    setup(v4)
    def cli(*args):
        return subprocess.run([sys.executable, '-m', 'arf', *args, '--db', str(v4.store.path)],
                              cwd=ROOT, capture_output=True, text=True)
    result = cli('run-next')
    assert result.returncode == 0, result.stderr
    first = json.loads(result.stdout)
    assert first['task_id'] == 'B' and first['recommendation_id'] == 'rank'
    second = json.loads(cli('run-next').stdout)
    assert second['task_id'] == 'A' and second['recommendation_id'] == 'rank'
    assert json.loads(cli('run-next').stdout)['status'] == 'no_ready_task'
    assert json.loads(cli('plan', 'migrate').stdout) == {'schema_version': 2, 'status': 'already_current'}


def test_inspection_page_byte_cap_and_explicit_continuation(v4):
    impact = Impact(rationale='r' * 3000, assumptions='a' * 3000,
                    uncertainty='u' * 3000, alternatives='b' * 3000)
    pairs = []
    for i in range(9):
        d = replace(definition(str(i)), impact=impact)
        pairs.extend(v4.record_candidates('batch-' + str(i), [d], {}, 'fixture')['versions'])
    context = v4.capture_context()
    for i in range(20):
        v4.decide('decision-' + str(i), context['context_id'], pairs)
    page = v4.list_decisions()
    assert len(canonical(page)) <= 2 * 1024 * 1024
    assert page['next_offset'] == len(page['items']) < 20
    rest = v4.list_decisions(offset=page['next_offset'])
    assert len(page['items']) + len(rest['items']) == 20 and rest['next_offset'] is None


def test_no_ranked_ready_member_is_needs_decision(v4):
    v4.store.add_task(TaskSpec.parse(spec('A')))
    a = replace(definition('A'), synthetic=Synthetic(8, 8, costs=Costs(synthetic_tokens=None)))
    pairs = v4.record_candidates('batch', [a, definition('unmapped', 100)], {'A': 'A'}, 'fixture')['versions']
    context = v4.capture_context()
    v4.decide('rank', context['context_id'], pairs)
    v4.publish('publication', 'rank', None)
    result = run_next(v4.store)
    assert result['status'] == 'needs_decision' and result['reason'] == 'no_ranked_ready_task'
    assert result['audit']['ready'] == ['A']
    assert not v4.store.evidence()


@pytest.mark.parametrize('values,next_task,branch', [([2, 4, 6, 8], 'C', 'viable'), ([0, 2], 'A', 'nonviable')])
def test_alternative_observed_feedback_changes_later_execution(v4, values, next_task, branch):
    for key in ('A', 'B', 'C'):
        v4.store.add_task(TaskSpec.parse(spec(key, input={'values': values if key == 'B' else [2, 4, 6, 8]})))
    definitions = [definition('A', 8), definition('B', 1, 12), replace(definition('C'), synthetic=Synthetic(14, 0))]
    pairs = v4.record_candidates('batch', definitions, {k: k for k in ('A', 'B', 'C')}, 'fixture')['versions']
    rules = tuple(Rule(k, v4.binding(k)['spec_sha256'],
                      'branch_from_mean' if k == 'B' else 'engineering_only') for k in ('A', 'B', 'C'))
    context = v4.capture_context(feedback=Feedback(rules=rules))
    v4.decide('rank', context['context_id'], pairs)
    v4.publish('publication', 'rank', None)
    assert run_next(v4.store)['task_id'] == 'B'
    result = run_next(v4.store)
    assert result['task_id'] == next_task
    saved = v4.show_context(v4.show_decision(result['recommendation_id'])['context_id'])
    assert saved['feedback']['branch'] == branch


def test_observed_wall_cost_is_relevant_when_used_by_ceiling(v4):
    context, _, _ = setup(v4)
    v4.decide('wall-policy', context['context_id'], v4.heads(),
              constraints=Constraints({'synthetic_tokens': 10, 'wall_seconds': 2}))
    v4.publish('wall-publication', 'wall-policy', 'publication')
    first = run_next(v4.store)
    second = run_next(v4.store)
    assert first['task_id'] == 'B' and second['task_id'] == 'A'
    assert first['recommendation_id'] != second['recommendation_id']
    assessment = v4.show_assessment(second['assessment_id'])
    assert 'observed_wall_cost_consulted_by_ceiling' in assessment['reasons']
