"""ADR-030 first decision: synthetic configuration, unchanged admission/relevance."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
import json
import sqlite3
import subprocess
import sys
import threading

import pytest

from arf import bootstrap
from arf.bootstrap import BootstrapProfile
from arf.decision_models import Constraints, Feedback, Policy, Rule, Selection
from arf.decisions import DecisionService
from arf.dispatch import dispatch_next
from arf.graph_models import Actor, QueryLimits
from arf.models import ARFError, TaskSpec
from arf.plan_models import PlanError, canonical, sha
from arf.service import controller_lock, recover, run_next
from arf.store import Store
from conftest import ROOT, spec
from test_decisions import definition, v4


def register(service, *, bind=True, qualitative=False):
    for key in ('A', 'B'):
        service.store.add_task(TaskSpec.parse(spec(key)))
    definitions = [definition('A', 8), definition('B', 1, 12)]
    if qualitative:
        definitions = [replace(d, synthetic=None) for d in definitions]
    return service.record_candidates('registered', definitions,
                                     {'A': 'A', 'B': 'B'} if bind else {}, 'fixture')['versions']


def count(service, table):
    return service.db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]


def test_first_public_cli_auto_ranks_b_then_refuses_unknown_evidence_and_restarts(v4):
    register(v4)
    original_charter = v4.store.study()
    assert v4.head() is None and not v4.list_decisions()['items']
    process = subprocess.run([sys.executable, '-m', 'arf', 'run-next', '--db', str(v4.store.path)],
                             cwd=ROOT, capture_output=True, text=True)
    assert process.returncode == 0, process.stderr
    first = json.loads(process.stdout)
    assert first['status'] == 'succeeded' and first['task_id'] == 'B'
    decision = v4.show_decision(first['recommendation_id'])
    metadata = decision['controller_profile']
    config = metadata['configuration']
    assert config['name'] == 'offline-synthetic-initial-ranking' and config['version'] == 1
    assert config['policy'] == {'name': 'information', 'version': 1, 'weight': 1}
    assert config['constraints'] == {'ceilings': {'synthetic_tokens': 10}, 'hard': [], 'currency': None}
    assert metadata['configuration_sha256'] == sha(canonical(config))
    assert config['feedback']['rules'] == []
    request = json.loads(v4.db.execute('SELECT request FROM research_decisions').fetchone()[0])
    assert request['controller_profile'] == metadata and request['actor'] == 'trusted-controller'
    receipt = v4.show_dispatch(first['dispatch_id'])
    assert receipt['audit']['bootstrap']['version'] == 1
    assert receipt['audit']['bootstrap']['decision_id'] == first['recommendation_id']
    assert receipt['audit']['ready'] == ['A', 'B']
    assert v4.show_assessment(first['assessment_id'])['outcome'] == 'reuse'
    inspected = subprocess.run([sys.executable, '-m', 'arf.decision_demo', '--inspect', '--db', str(v4.store.path)],
                               cwd=ROOT, capture_output=True, text=True)
    assert inspected.returncode == 0, inspected.stderr
    assert json.loads(inspected.stdout)['decisions'] == v4.list_decisions()['items']
    second = run_next(v4.store)
    assert second['status'] == 'needs_decision' and second['reason'] == 'critical_invalidity'
    assert count(v4, 'decision_publications') == 1 and count(v4, 'research_decisions') == 1
    assert v4.store.task('A')['status'] == 'pending'
    with controller_lock(v4.store.path):
        replay = dispatch_next(v4, first['dispatch_id'])
    assert replay['claim'] is None and replay['receipt'] == receipt
    assert len(v4.store.evidence()) == 1 and v4.store.study() == original_charter


def test_preconfigured_trusted_rules_allow_multi_claim_reuse(v4, monkeypatch):
    register(v4)
    rules = tuple(Rule(k, v4.binding(k)['spec_sha256'], 'engineering_only') for k in ('A', 'B'))
    installed = BootstrapProfile(feedback=Feedback(source='trusted-offline-test', rules=rules))
    monkeypatch.setattr(bootstrap, 'INITIAL_PROFILE', installed)
    first = run_next(v4.store)
    # The stored publication, not a newly installed bootstrap, controls the next claim.
    monkeypatch.setattr(bootstrap, 'INITIAL_PROFILE', None)
    second = run_next(v4.store)
    assert [first['task_id'], second['task_id']] == ['B', 'A']
    assert first['recommendation_id'] == second['recommendation_id']
    assert first['assessment_id'] != second['assessment_id']
    assessment = v4.show_assessment(second['assessment_id'])
    assert assessment['outcome'] == 'reuse'
    assert any(r.startswith('synthetic_engineering_only:') for r in assessment['reasons'])
    assert count(v4, 'decision_publications') == count(v4, 'research_decisions') == 1


@pytest.mark.parametrize('installed', [None, object(), BootstrapProfile(name='live-manager'),
    BootstrapProfile(version=2), BootstrapProfile(policy=Policy('static')),
    BootstrapProfile(policy=Policy(version=True)), BootstrapProfile(policy=Policy(weight=2)),
    BootstrapProfile(constraints=Constraints({'synthetic_tokens': 999}))])
def test_missing_or_unsupported_trusted_profile_refuses(v4, monkeypatch, installed):
    register(v4)
    monkeypatch.setattr(bootstrap, 'INITIAL_PROFILE', installed)
    result = run_next(v4.store)
    assert result['status'] == 'needs_decision' and result['reason'] == 'policy_unconfigured'
    assert result['audit']['bootstrap']['version'] == 1
    assert count(v4, 'research_decisions') == count(v4, 'decision_publications') == count(v4, 'runs') == 0


def test_missing_candidates_nonclaim_replay_precedes_new_config_and_state(v4, monkeypatch):
    v4.store.add_task(TaskSpec.parse(spec('A')))
    first = dispatch_next(v4, 'no-candidates')['receipt']
    assert first['status'] == 'needs_decision' and first['reason'] == 'missing_candidates'
    v4.record_candidates('later', [definition('A')], {'A': 'A'}, 'fixture')
    monkeypatch.setattr(bootstrap, 'INITIAL_PROFILE', None)
    replay = dispatch_next(v4, 'no-candidates')
    assert replay['replayed'] and replay['receipt'] == first and replay['claim'] is None
    assert count(v4, 'runs') == count(v4, 'research_decisions') == 0


@pytest.mark.parametrize('qualitative,reason,status', [(False, 'unranked_ready_task', 'needs_decision'),
                                                      (True, 'reasoned_abstention', 'deferred')])
def test_unbound_or_unrankable_candidates_never_claim(v4, qualitative, reason, status):
    register(v4, bind=qualitative, qualitative=qualitative)
    result = run_next(v4.store)
    assert (result['status'], result['reason']) == (status, reason)
    assert count(v4, 'runs') == 0
    assert count(v4, 'research_decisions') == count(v4, 'decision_publications') == 1
    assert result['audit']['bootstrap']['publication_id'] == v4.head()


def test_bootstrap_preserves_p2_strict_coverage(v4):
    v4.store.add_task(TaskSpec.parse(spec('A')))
    v4.store.add_task(TaskSpec.parse(spec('B')))
    v4.record_candidates('B-only', [definition('B', 1, 12)], {'B': 'B'}, 'fixture')
    result = run_next(v4.store)
    assert result['reason'] == 'unranked_ready_task'
    assert result['audit']['unranked_ready'] == ['A']
    assert v4.store.task('B')['status'] == 'pending'
    assert count(v4, 'runs') == 0


def test_truncated_initial_capture_abstains(v4, monkeypatch):
    register(v4)
    monkeypatch.setattr(bootstrap, 'INITIAL_PROFILE', BootstrapProfile(selection=Selection(limits=QueryLimits(nodes=1))))
    result = run_next(v4.store)
    assert result['status'] == 'deferred' and result['reason'] == 'reasoned_abstention'
    assert v4.show_decision(result['recommendation_id'])['reason'] == 'truncated_selection'
    assert count(v4, 'runs') == 0


def test_no_ready_or_unfinished_capacity_never_calls_bootstrap(v4, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('bootstrap must not run before authoritative readiness/capacity checks')
    monkeypatch.setattr(bootstrap, 'bootstrap_initial', forbidden)
    assert run_next(v4.store)['reason'] == 'empty_queue'
    register(v4)
    with v4.store.transaction():
        v4.store._claim_task_in_transaction('A')
    assert run_next(v4.store)['reason'] == 'unfinished_attempt'
    recover(v4.store)
    # Remove B from the ready set by a normal explicit attempt and failure as well.
    with v4.store.transaction():
        claim = v4.store._claim_task_in_transaction('B')
    v4.store.finish_run(claim['run_id'], result=None, error='controlled test failure', exit_code=1,
                        stdout='', stderr='', wall_seconds=0)
    v4.store.add_task(TaskSpec.parse(spec('blocked', ['A'])))
    assert run_next(v4.store)['reason'] == 'prerequisites_blocked'
    assert count(v4, 'research_decisions') == 0


@pytest.mark.parametrize('change', ['graph', 'task', 'candidate'])
def test_initial_capture_interleaving_refuses_stale_rank(v4, monkeypatch, change):
    register(v4)
    capture = DecisionService.capture_context
    def capture_then_change(service, *args, **kwargs):
        context = capture(service, *args, **kwargs)
        if change == 'graph':
            service.graph.create_human_idea(operation_id='concurrent-H', actor=Actor('operator', 'operator', 'test'),
                                            kind='H', text='Changed consulted premise')
        elif change == 'task':
            service.store.add_task(TaskSpec.parse(spec('new-task')))
        else:
            service.record_candidates('new-candidate', [definition('D')], {}, 'fixture')
        return context
    monkeypatch.setattr(DecisionService, 'capture_context', capture_then_change)
    result = run_next(v4.store)
    assert result['reason'] == 'state_changed'
    assert count(v4, 'runs') == count(v4, 'decision_publications') == 0


def test_racing_initializers_publish_one_head_and_claim_once(v4, monkeypatch):
    register(v4)
    barrier = threading.Barrier(2)
    decide = DecisionService.decide
    def synchronize(service, *args, **kwargs):
        assert not service.db.in_transaction
        barrier.wait(timeout=5)
        return decide(service, *args, **kwargs)
    monkeypatch.setattr(DecisionService, 'decide', synchronize)
    def claim(key):
        with Store(v4.store.path) as store:
            return dispatch_next(DecisionService(store), key)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(claim, ('first', 'second')))
    assert sum(r['claim'] is not None for r in results) == 1
    assert count(v4, 'decision_publications') == count(v4, 'runs') == 1
    assert sum(r['receipt']['reason'] == 'state_changed' for r in results) == 1
    receipt = next(r['receipt'] for r in results if r['claim'] is not None)
    assert receipt['task_id'] == 'B'
    assert v4.db.execute('PRAGMA foreign_key_check').fetchall() == []
    recover(v4.store)


@pytest.mark.parametrize('stage', ['before_commit', 'after_commit'])
def test_interrupted_initial_publication_never_starts_worker(v4, monkeypatch, stage):
    register(v4)
    publish = DecisionService.publish
    def interrupt(service, *args, **kwargs):
        if stage == 'after_commit':
            publish(service, *args, **kwargs)
        raise KeyboardInterrupt()
    with monkeypatch.context() as scoped:
        scoped.setattr(DecisionService, 'publish', interrupt)
        with pytest.raises(KeyboardInterrupt):
            run_next(v4.store)
    assert count(v4, 'runs') == count(v4, 'decision_dispatches') == 0
    assert count(v4, 'decision_publications') == (1 if stage == 'after_commit' else 0)
    assert count(v4, 'research_decisions') == 1
    result = run_next(v4.store)  # An explicit new invocation, never automatic resume.
    assert result['task_id'] == 'B'
    assert count(v4, 'research_decisions') == (1 if stage == 'after_commit' else 2)
    assert count(v4, 'decision_publications') == count(v4, 'runs') == 1


def test_initial_publication_sql_failure_and_claim_receipt_failure(v4):
    register(v4)
    v4.db.execute("CREATE TRIGGER stop_publication BEFORE INSERT ON decision_publications BEGIN SELECT RAISE(ABORT,'publication failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='publication failure'):
        dispatch_next(v4, 'first')
    assert count(v4, 'decision_publications') == count(v4, 'runs') == 0
    assert count(v4, 'research_decisions') == 1
    v4.db.execute('DROP TRIGGER stop_publication')
    v4.db.execute("CREATE TRIGGER stop_receipt BEFORE INSERT ON decision_dispatches BEGIN SELECT RAISE(ABORT,'receipt failure'); END")
    with pytest.raises(sqlite3.IntegrityError, match='receipt failure'):
        dispatch_next(v4, 'second')
    assert count(v4, 'decision_publications') == 1 and count(v4, 'runs') == 0
    v4.db.execute('DROP TRIGGER stop_receipt')
    result = dispatch_next(v4, 'second')
    assert result['claim']['task']['task_id'] == 'B'
    assert count(v4, 'decision_publications') == count(v4, 'runs') == 1
    recover(v4.store)


def test_bootstrap_admission_rechecks_imported_task(v4):
    from arf.authorization import decide, import_proposal
    from arf.planning import propose
    context = v4.plans.export()['context_sha256']
    proposal = propose(v4.plans, context, 'proposal', 'task')['proposal_id']
    decide(v4.plans, proposal, 'approve', 'operator')
    imported = import_proposal(v4.plans, proposal)
    v4.record_candidates('registered', [definition('imported')], {'imported': imported['task_id']}, 'fixture')
    result = run_next(v4.store)
    assert result['task_id'] == imported['task_id']
    assert v4.binding(imported['task_id'])['admission']['kind'] == 'approved_import'
    assert import_proposal(v4.plans, proposal) == imported


def test_bootstrap_legacy_decision_request_encoding_unchanged(v4):
    pairs = register(v4)
    context = v4.capture_context()
    old = v4.decide('ordinary', context['context_id'], pairs)
    request_bytes = v4.db.execute('SELECT request FROM research_decisions').fetchone()[0]
    assert 'controller_profile' not in json.loads(request_bytes)
    assert 'controller_profile' not in old
    assert v4.decide('ordinary', context['context_id'], pairs) == old
    first = run_next(v4.store)
    assert first['task_id'] == 'B'
    assert v4.show_decision('ordinary') == old
    assert v4.db.execute("SELECT request FROM research_decisions WHERE decision_id='ordinary'").fetchone()[0] == request_bytes


def test_initial_rank_skips_blocked_high_priority_task(v4):
    v4.store.add_task(TaskSpec.parse(spec('A')))
    v4.store.add_task(TaskSpec.parse(spec('B', ['A'])))
    v4.record_candidates('registered', [definition('A', 8), definition('B', 1, 12)],
                         {'A': 'A', 'B': 'B'}, 'fixture')
    result = run_next(v4.store)
    assert result['task_id'] == 'A'
    audit = v4.show_dispatch(result['dispatch_id'])['audit']
    assert audit['ready'] == ['A'] and audit['blockers']['B'] == [{'task_id': 'A', 'status': 'pending'}]
    assert v4.store.task('B')['status'] == 'pending'
