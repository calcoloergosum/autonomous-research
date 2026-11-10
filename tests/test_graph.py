"""VS-003 G1–G10: actual offline observations, immutable assertions and bounds."""

import base64
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
import socket
import sqlite3

import pytest

from arf.authorization import decide, import_proposal
from arf.graph import GraphService
from arf.graph_demo import ACTOR, SyntheticNote, build, legacy_rows
from arf.graph_models import Actor, QueryLimits, Ref
from arf.graph_store import GraphError, migrate
from arf.models import ARFError, TaskSpec
from arf.planning import propose
from arf.plan_models import PlanError, canonical
from arf.plan_store import PlanStore, migrate as migrate_plan
from arf.service import run_next
from arf.store import Store
from conftest import spec
from test_validation_cli import cli

RECORDER = Actor('fixture-recorder', 'recorder', 'offline synthetic test')


@pytest.fixture
def graph(store):
    migrate_plan(store)
    migrate(store)
    return GraphService(store)


def idea(graph, name='H1', kind='H'):
    result = graph.create_human_idea(kind=kind, text='Synthetic ' + name,
                                    operation_id=name, actor=ACTOR)['result']
    return Ref(kind, result['idea_id'], result['revision_id'])


def link(graph, type, source, target, op='link', **kwargs):
    return graph.add_semantic_link(type=type, source=source, target=target,
        rationale='Synthetic attribution', operation_id=op, actor=RECORDER, **kwargs)


def observed(graph, count=2):
    for i in range(count):
        graph.store.add_task(TaskSpec.parse(spec('T' + str(i), input={'values': [i, i + 2]})))
        assert run_next(graph.store)['status'] == 'succeeded'
    return [Ref('E', e['evidence_id']) for e in graph.store.evidence()]


def test_g1_objective_only_resolves_imported_charter_and_no_goal_mutation(graph):
    before = graph.store.study()
    objective = graph.read_graph(roles=('O',))['nodes'][0]
    assert objective['ref'] == asdict(Ref('O', before['study_id']))
    assert base64.b64decode(objective['body']['source_base64']) == before['source']
    assert objective['body']['source_sha256'] == before['source_sha256']
    for kind in ('O', 'objective', 'T', 'E', 'B', 'C'):
        with pytest.raises(GraphError):
            idea(graph, 'bad-' + kind, kind)
    with pytest.raises(TypeError):
        graph.create_human_idea(kind='H', text='x', question='override', operation_id='bad', actor=ACTOR)
    assert graph.sequence() == 0
    assert graph.store.study() == before


def populated_v2(store):
    store.add_task(TaskSpec.parse(spec()))
    run_next(store)
    migrate_plan(store)
    plans = PlanStore(store)
    context = plans.export()['context_sha256']
    for fixture in ('note', 'no_action', 'task'):
        result = propose(plans, context, fixture, fixture)
        if fixture == 'task':
            decide(plans, result['proposal_id'], 'approve', 'fixture')
            import_proposal(plans, result['proposal_id'])
    return plans


def test_g2_populated_v2_migration_preserves_all_rows_and_context_restart(store):
    plans = populated_v2(store)
    before = legacy_rows(store)
    with store.transaction():
        original_context = plans.context_bytes()
    assert migrate(store) == {'schema_version': 3, 'status': 'migrated'}
    assert legacy_rows(store) == before
    assert migrate(store) == {'schema_version': 3, 'status': 'already_current'}
    assert migrate_plan(store) == {'schema_version': 2, 'status': 'already_current'}
    with Store(store.path) as restarted:
        assert legacy_rows(restarted) == before
        assert GraphService(restarted).sequence() == 0
        with restarted.transaction():
            assert PlanStore(restarted).context_bytes() == original_context
        assert restarted.connection.execute('PRAGMA foreign_key_check').fetchall() == []
        assert run_next(restarted)['status'] == 'succeeded'


def test_g2_interrupted_migration_rolls_back_and_can_be_explicitly_retried(store):
    populated_v2(store)
    before = legacy_rows(store)
    def authorizer(action, name, *args):
        return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_CREATE_TABLE and name == 'graph_links' else sqlite3.SQLITE_OK
    store.connection.set_authorizer(authorizer)
    with pytest.raises(sqlite3.DatabaseError):
        migrate(store)
    store.connection.set_authorizer(None)
    assert legacy_rows(store) == before
    assert store.connection.execute('PRAGMA user_version').fetchone()[0] == 2
    assert not store.connection.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'graph_%'").fetchall()
    assert migrate(store)['status'] == 'migrated'


def test_g2_baseexception_rollback(store, monkeypatch):
    migrate_plan(store)
    import arf.graph_store as module
    original = module.GRAPH_SCHEMA
    class Interrupted:
        def __iter__(self):
            yield original[0]
            raise KeyboardInterrupt
    monkeypatch.setattr(module, 'GRAPH_SCHEMA', Interrupted())
    with pytest.raises(KeyboardInterrupt):
        migrate(store)
    assert store.connection.execute('PRAGMA user_version').fetchone()[0] == 2
    assert not store.connection.execute("SELECT 1 FROM sqlite_master WHERE name LIKE 'graph_%'").fetchall()


@pytest.mark.parametrize('version', [1, 2, 3, 999])
def test_g2_unknown_or_modified_schema_is_not_adopted(store, version):
    if version >= 2:
        migrate_plan(store)
    store.connection.execute('CREATE TABLE unrelated (x)')
    store.connection.execute(f'PRAGMA user_version={version}')
    before = store.connection.iterdump()
    before = list(before)
    with pytest.raises(PlanError):
        migrate(store)
    assert list(store.connection.iterdump()) == before


def test_g2_no_implicit_migration_and_v1_v2_stay_available(store):
    with pytest.raises(GraphError):
        GraphService(store)
    with pytest.raises(GraphError):
        migrate(store)
    store.add_task(TaskSpec.parse(spec()))
    migrate_plan(store)
    with pytest.raises(GraphError):
        GraphService(store)
    assert run_next(store)['status'] == 'succeeded'
    assert store.connection.execute('PRAGMA user_version').fetchone()[0] == 2


def test_g3_note_registration_explicit_unique_and_replay_safe(graph):
    plans = PlanStore(graph.store)
    context = plans.export()['context_sha256']
    p = propose(plans, context, 'note', 'note')['proposal_id']
    assert graph.sequence() == 0
    before = legacy_rows(graph.store)
    first = graph.register_note(proposal_id=p, operation_id='register', actor=RECORDER)
    assert graph.register_note(proposal_id=p, operation_id='register', actor=RECORDER) == first
    with pytest.raises(GraphError, match='conflict'):
        graph.register_note(proposal_id=p, operation_id='register-alias', actor=RECORDER)
    with pytest.raises(GraphError, match='conflict'):
        graph.register_note(proposal_id=p, operation_id='other-actor', actor=ACTOR)
    assert graph.sequence() == 1
    assert legacy_rows(graph.store) == before
    assert graph.store.tasks() == graph.store.evidence() == []
    with Store(graph.store.path) as restart:
        other = GraphService(restart)
        assert other.register_note(proposal_id=p, operation_id='register', actor=RECORDER) == first
        node = other.read_graph(roles=('Q', 'H'))['nodes'][0]
        assert node['origin']['proposal_id'] == p
        assert node['origin']['context_sha256'] == context
        assert node['origin']['requests'][0]['provider_name'] == 'fixture-mock'
        assert node['body']['visibility'] == 'unreviewed'


@pytest.mark.parametrize('fixture', ['task', 'no_action', 'invalid', 'uncertain', 'missing'])
def test_g3_non_notes_and_invalid_uncertain_requests_refused(graph, fixture):
    plans = PlanStore(graph.store)
    context = plans.export()['context_sha256']
    if fixture == 'invalid':
        with pytest.raises(PlanError):
            propose(plans, context, fixture, 'invalid')
        p = fixture
    elif fixture == 'uncertain':
        class Uncertain:
            def propose(self, request):
                raise RuntimeError('unknown outcome')
        with pytest.raises(PlanError):
            propose(plans, context, fixture, 'note', provider=Uncertain())
        p = fixture
    elif fixture == 'missing':
        p = 'unknown'
    else:
        p = propose(plans, context, fixture, fixture)['proposal_id']
    before = legacy_rows(graph.store)
    with pytest.raises(GraphError):
        graph.register_note(proposal_id=p, operation_id='register', actor=RECORDER)
    assert graph.sequence() == 0
    assert legacy_rows(graph.store) == before


@pytest.mark.parametrize('type,source_role,target_role', [
    ('CAUSES', 'H', 'H'), ('DEPENDS_ON', 'T', 'T'), ('PRODUCES', 'R', 'E'),
    ('SUPERSEDES', 'B', 'B'), ('ATTEMPT_OF', 'R', 'T'), ('INVESTIGATES', 'H', 'T'),
    ('ASSESSES', 'H', 'E'), ('ADDRESSES', 'T', 'H'), ('USES_BASELINE', 'H', 'B'),
])
def test_g4_closed_types_and_directed_endpoints(graph, type, source_role, target_role):
    h = idea(graph)
    with pytest.raises(GraphError):
        link(graph, type, Ref(source_role, h.id, h.revision), Ref(target_role, h.id, h.revision))
    assert graph.sequence() == 1


@pytest.mark.parametrize('target', [Ref('H', 'unknown', 'unknown'), Ref('H', 'other-study', 'unknown'),
    Ref('H', 'placeholder'), Ref('O', 'other-study'), Ref('X', 'x'), Ref('E', 'missing'),
    Ref('O', 'demo-mean-study', 'forged-revision')])
def test_g4_dangling_cross_study_wrong_kind_and_pins_rejected(graph, target):
    h = idea(graph)
    with pytest.raises(GraphError):
        link(graph, 'MOTIVATED_BY', h, target)


def test_g4_exact_revision_binding_and_self_link(graph):
    h = idea(graph)
    q = idea(graph, 'Q', 'Q')
    for invalid in (Ref('Q', h.id, h.revision), Ref('H', h.id, q.revision), Ref('H', h.id)):
        with pytest.raises(GraphError):
            link(graph, 'DERIVED_FROM', h, invalid)
    with pytest.raises(GraphError):
        link(graph, 'MOTIVATED_BY', h, h)


def test_g4_mixed_cycles_traversable_but_derivation_lineage_cannot_cycle(graph):
    h = idea(graph)
    q = idea(graph, 'Q', 'Q')
    graph.store.add_task(TaskSpec.parse(spec('T0')))
    link(graph, 'INVESTIGATES', Ref('T', 'T0'), h, op='investigate')
    link(graph, 'DERIVED_FROM', h, q, op='derive')
    link(graph, 'MOTIVATED_BY', q, h, op='mixed-cycle')
    view = graph.ancestry('T0')
    assert not view['truncated']
    assert len(view['nodes']) == 3
    with pytest.raises(GraphError, match='circular'):
        link(graph, 'DERIVED_FROM', q, h, op='cycle')
    assert graph.db.execute('SELECT count(*) FROM dependencies').fetchone()[0] == 0


def test_g5_real_factual_projection_failed_and_interrupted_runs_produce_no_evidence(graph):
    e1, e2 = observed(graph)
    graph.store.add_task(TaskSpec.parse(spec('failure')))
    def fail(data):
        raise RuntimeError('synthetic failure')
    assert run_next(graph.store, fail)['status'] == 'failed'
    graph.store.add_task(TaskSpec.parse(spec('interrupted')))
    graph.store.claim_next()
    graph.store.recover()
    view = graph.read_graph()
    produces = [e for e in view['edges'] if e['type'] == 'PRODUCES']
    attempts = [e for e in view['edges'] if e['type'] == 'ATTEMPT_OF']
    assert len(produces) == 2 and len(attempts) == 4
    assert {e['target']['id'] for e in produces} == {e1.id, e2.id}
    assert {e['source']['id'] for e in produces} == {e['run_id'] for e in graph.store.evidence()}


def test_g5_convergent_competing_scoped_assessments_and_joint_claim(graph):
    e1, e2 = observed(graph)
    h1, h2 = idea(graph), idea(graph, 'H2')
    before = legacy_rows(graph.store)
    for i, (e, h, p) in enumerate(((e1, h1, 'supports'), (e2, h1, 'contradicts'), (e1, h2, 'contradicts'))):
        link(graph, 'ASSESSES', e, h, op='assessment-' + str(i), polarity=p,
             assumptions='Synthetic scope assumption', scope='demo-only')
    claim = graph.create_claim(text='Synthetic joint synthesis', assumptions='Joint input', scope='demo-only',
                              premises=(e1, e2), operation_id='claim', actor=RECORDER)['result']
    view = graph.read_graph()
    c = next(n for n in view['nodes'] if n['ref']['id'] == claim['idea_id'])
    assert c['body']['joint'] is True
    assert c['body']['premises'] == [asdict(e1), asdict(e2)]
    assert len([e for e in view['edges'] if e['type'] == 'DERIVED_FROM']) == 2
    assert legacy_rows(graph.store) == before
    assert all(e['validation_status'] == 'unvalidated' for e in graph.store.evidence())
    assert len(graph.store.evidence()) == 2


@pytest.mark.parametrize('premises,joint', [((), True), ((Ref('E', 'dangling'),), True), ((), False)])
def test_g5_no_dangling_or_implicit_joint_premises(graph, premises, joint):
    with pytest.raises(GraphError):
        graph.create_claim(text='claim', assumptions='a', scope='s', premises=premises,
                           joint=joint, operation_id='claim', actor=RECORDER)
    assert graph.sequence() == 0


@pytest.mark.parametrize('polarity,assumptions,scope', [(None, 'a', 's'), ('validated', 'a', 's'),
    ('supports', '', 's'), ('contradicts', 'a', '')])
def test_g5_assessment_requires_explicit_scoped_polarity(graph, polarity, assumptions, scope):
    e = observed(graph, 1)[0]
    h = idea(graph)
    with pytest.raises(GraphError):
        link(graph, 'ASSESSES', e, h, polarity=polarity, assumptions=assumptions, scope=scope)


def test_g6_revision_withdrawal_expected_heads_history_and_attribution(graph):
    e = observed(graph, 1)[0]
    h = idea(graph)
    l = link(graph, 'ASSESSES', e, h, polarity='supports', assumptions='a', scope='s')
    motivation = link(graph, 'MOTIVATED_BY', h, e, op='motivation')
    prior_seq = graph.sequence()
    revised = graph.revise_idea(idea_id=h.id, expected_head=h.revision, text='Revised hypothesis',
                               operation_id='revise-idea', actor=ACTOR)
    h2 = Ref('H', h.id, revised['result']['revision_id'])
    # Old assessment stays pinned to H1 until a separate attributed correction.
    assert graph.read_graph(edge_types=('ASSESSES',))['edges'][0]['target'] == asdict(h)
    correction = dict(link_id=l['result']['link_id'], expected_head=l['result']['revision_id'],
                      rationale='Corrected scope and target', assumptions='new a', scope='new s',
                      polarity='inconclusive', target=h2, operation_id='correct', actor=ACTOR)
    new = graph.revise_or_withdraw_link(**correction)
    assert graph.revise_or_withdraw_link(**correction) == new
    withdrawal = graph.revise_or_withdraw_link(link_id=motivation['result']['link_id'],
        expected_head=motivation['result']['revision_id'], rationale='Retrospective correction',
        withdraw=True, operation_id='withdraw', actor=ACTOR)
    assert withdrawal['actor']['name'] == ACTOR.name
    with pytest.raises(GraphError, match='conflict'):
        graph.revise_or_withdraw_link(**{**correction, 'operation_id': 'stale'})
    with pytest.raises(GraphError, match='conflict'):
        graph.revise_idea(idea_id=h.id, expected_head=h.revision, text='Stale', operation_id='stale-h', actor=ACTOR)
    old = graph.as_of(prior_seq)
    assert next(e for e in old['edges'] if e['id'] == l['result']['link_id'])['polarity'] == 'supports'
    assert next(e for e in old['edges'] if e['id'] == motivation['result']['link_id'])['visibility'] == 'unreviewed'
    history = graph.read_graph(history=True)
    assert len([e for e in history['edges'] if e['id'] == l['result']['link_id']]) == 2
    assert next(e for e in history['edges'] if e['visibility'] == 'withdrawn')['actor']['name'] == ACTOR.name
    assert len([n for n in history['nodes'] if n['ref']['id'] == h.id]) == 2
    assert graph.read_graph(node=h)['nodes'][0]['body']['text'] == 'Synthetic H1'


def test_g6_operation_id_conflicts_and_atomic_receipt_failure(graph):
    h = idea(graph)
    with pytest.raises(GraphError, match='conflict'):
        graph.create_human_idea(kind='H', text='Different', operation_id='H1', actor=ACTOR)
    before = list(graph.db.iterdump())
    graph.db.execute("""CREATE TRIGGER deny_graph_receipt BEFORE INSERT ON graph_operations
        BEGIN SELECT RAISE(ABORT,'synthetic receipt failure'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        link(graph, 'ADDRESSES', h, Ref('O', graph.study_id))
    graph.db.execute('DROP TRIGGER deny_graph_receipt')
    assert list(graph.db.iterdump()) == before


def test_g7_late_links_absent_in_earlier_views_current_execution_is_labeled(graph):
    graph.store.add_task(TaskSpec.parse(spec('T0')))
    h = idea(graph)
    before = graph.sequence()
    link(graph, 'INVESTIGATES', Ref('T', 'T0'), h)
    run_next(graph.store)
    old = graph.as_of(before)
    assert not [e for e in old['edges'] if e['category'] == 'semantic']
    task = next(n for n in old['nodes'] if n['ref']['role'] == 'T')
    assert task['body']['status'] == 'succeeded'
    assert task['execution_state'] == 'current'
    assert task['historical_execution_state'] == 'unknown'
    assert graph.as_of(0, roles=('H',))['nodes'] == []
    for seq in (-1, 999, True):
        with pytest.raises(GraphError):
            graph.as_of(seq)


def test_g7_creation_context_verified_against_exact_original_proposal(graph):
    e = observed(graph, 1)[0]
    plans = PlanStore(graph.store)
    context = plans.export()['context_sha256']
    note = propose(plans, context, 'with-e', 'note', provider=SyntheticNote(e.id))['proposal_id']
    r = graph.register_note(proposal_id=note, operation_id='register', actor=RECORDER)['result']
    q = Ref(r['kind'], r['idea_id'], r['revision_id'])
    valid = link(graph, 'MOTIVATED_BY', q, e, timing='creation_context', proposal_id=note)
    assert graph.read_graph(node=q)['edges'][0]['timing'] == 'creation_context'
    revised = graph.revise_idea(idea_id=q.id, expected_head=q.revision, text='Later revision',
                              operation_id='revise', actor=RECORDER)['result']
    with pytest.raises(GraphError):
        link(graph, 'MOTIVATED_BY', Ref(q.role, q.id, revised['revision_id']), e,
             op='forged', timing='creation_context', proposal_id=note)
    h = idea(graph)
    with pytest.raises(GraphError):
        link(graph, 'MOTIVATED_BY', h, e, op='late', timing='creation_context', proposal_id=note)
    default_note = propose(plans, context, 'without-e', 'note')['proposal_id']
    r2 = graph.register_note(proposal_id=default_note, operation_id='default-note', actor=RECORDER)['result']
    with pytest.raises(GraphError):
        link(graph, 'MOTIVATED_BY', Ref(r2['kind'], r2['idea_id'], r2['revision_id']), e,
             op='no-original-ref', timing='creation_context', proposal_id=default_note)
    assert valid['graph_seq'] < graph.sequence()


def baseline(graph, name, scope='demo'):
    return graph.create_baseline(scope=scope, method='Synthetic ' + name, configuration='Fixed demo',
                                 operation_id=name, actor=ACTOR)['result']['baseline_id']


def test_g8_scoped_transition_conflicts_replays_reversion_and_preserves_work(graph):
    e = observed(graph, 1)[0]
    graph.store.add_task(TaskSpec.parse(spec('pending')))
    h = idea(graph)
    b0, b1, b2 = baseline(graph, 'B0'), baseline(graph, 'B1'), baseline(graph, 'other', 'other')
    before = legacy_rows(graph.store)
    def transition(op, prior, new, scope='demo'):
        return graph.record_baseline_transition(scope=scope, new_baseline=new, expected_prior=prior,
            rationale='Synthetic transition', motivations=(e,),
            affected=((Ref('T', 'pending'), 'retain'), (h, 'pause_direction')), operation_id=op, actor=ACTOR)
    transition('initial', None, b0)
    earlier = graph.sequence()
    result = transition('replace', b0, b1)
    assert transition('replace', b0, b1) == result
    with pytest.raises(GraphError, match='conflict'):
        transition('stale', b0, b1)
    with pytest.raises(GraphError):
        transition('wrong-scope', b1, b2)
    transition('other-scope', None, b2, 'other')
    transition('revert', b1, b0)
    assert graph.as_of(earlier)['active_baselines'] == [{'scope': 'demo', 'baseline_id': b0, 'graph_seq': earlier}]
    assert {v['scope']: v['baseline_id'] for v in graph.read_graph()['active_baselines']} == {'demo': b0, 'other': b2}
    supersedes = graph.read_graph(edge_types=('SUPERSEDES',))['edges']
    assert len(supersedes) == 2
    assert all(e['category'] == 'operator_transition' for e in supersedes)
    assert legacy_rows(graph.store) == before
    assert graph.store.task('pending')['status'] == 'pending'


def test_g8_two_connections_cannot_commit_same_predecessor(graph):
    e = observed(graph, 1)[0]
    b0, b1, b2 = baseline(graph, 'B0'), baseline(graph, 'B1'), baseline(graph, 'B2')
    graph.record_baseline_transition(scope='demo', new_baseline=b0, expected_prior=None,
        rationale='Initial fixture', motivations=(e,), operation_id='initial', actor=ACTOR)
    def attempt(new):
        with Store(graph.store.path) as store:
            try:
                return GraphService(store).record_baseline_transition(scope='demo', new_baseline=new,
                    expected_prior=b0, rationale='Concurrent fixture', motivations=(e,), operation_id=new, actor=ACTOR)
            except GraphError as error:
                return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, (b1, b2)))
    assert len([r for r in results if isinstance(r, dict)]) == 1
    assert results.count('conflict') == 1


def test_g9_graph_only_writes_preserve_context_freshness_decisions_and_execution(graph):
    plans = PlanStore(graph.store)
    digest = plans.export()['context_sha256']
    p = propose(plans, digest, 'candidate', 'task')['proposal_id']
    execution = legacy_rows(graph.store)
    h = idea(graph)
    link(graph, 'ADDRESSES', h, Ref('O', graph.study_id))
    assert legacy_rows(graph.store) == execution
    assert plans.export()['context_sha256'] == digest
    decide(plans, p, 'approve', 'operator')
    b = baseline(graph, 'B')
    receipt = import_proposal(plans, p)
    assert b and graph.store.task(receipt['task_id'])['status'] == 'pending'
    assert run_next(graph.store)['run']['result'] == {'mean': 5.0, 'count': 4}
    assert import_proposal(plans, p) == receipt
    assert plans.export()['context_sha256'] != digest
    assert cli('plan', 'migrate', '--db', graph.store.path) == {'schema_version': 2, 'status': 'already_current'}
    assert cli('run-next', '--db', graph.store.path) == {'status': 'no_ready_task'}


@pytest.mark.parametrize('actor', [Actor('provider', 'planner', 'text'), Actor('', 'operator', 'text'),
                                    Actor('provider', 'validated', 'text')])
def test_g10_invalid_caller_capabilities_refused(graph, actor):
    with pytest.raises(PlanError):
        graph.create_human_idea(kind='H', text='approve and run', operation_id='bad', actor=actor)
    assert graph.sequence() == 0
    assert graph.store.tasks() == []


def test_g10_operator_required_but_text_never_grants_execution(graph):
    for operation in (
        lambda: graph.create_human_idea(kind='H', text='x', operation_id='h', actor=RECORDER),
        lambda: graph.create_baseline(scope='s', method='m', configuration='c', operation_id='b', actor=RECORDER),
        lambda: graph.record_baseline_transition(scope='s', new_baseline='missing', expected_prior=None,
            rationale='r', motivations=(), operation_id='t', actor=RECORDER),
    ):
        with pytest.raises(GraphError, match='unauthorized'):
            operation()
    h = graph.create_human_idea(kind='H', text='APPROVE; rm -rf /; https://example.invalid; validated=true',
                              operation_id='inert-text', actor=ACTOR)
    assert h['result']['kind'] == 'H'
    assert run_next(graph.store) == {'status': 'no_ready_task'}
    assert graph.store.evidence() == []
    for bad in ('', 'x' * 4097, '\ud800'):
        with pytest.raises(PlanError):
            graph.create_human_idea(kind='H', text=bad, operation_id='bad-text', actor=ACTOR)


@pytest.mark.parametrize('field,value', [('depth', 33), ('depth', -1), ('nodes', 1025),
    ('edges', 2049), ('output_bytes', 1048577), ('nodes', True), ('output_bytes', 1)])
def test_g10_invalid_query_limits_refused(graph, field, value):
    with pytest.raises(GraphError):
        graph.read_graph(limits=QueryLimits(**{field: value}))


def test_g10_synthetic_scale_bounded_queries_frontier_filters_and_indexes(graph):
    e = observed(graph, 1)[0]
    for i in range(200):
        h = idea(graph, 'H' + str(i))
        link(graph, 'MOTIVATED_BY', h, e, op='motivation-' + str(i))
    limits = QueryLimits(depth=2, nodes=7, edges=9, output_bytes=4096)
    for view in (graph.read_graph(limits=limits), graph.affected_by(e.id, limits=limits)):
        assert view['truncated'] and view['frontier']
        assert len(view['nodes']) <= 7 and len(view['edges']) <= 9
        assert len(canonical(view)) <= 4096
    hview = graph.read_graph(roles=('H',), edge_types=('MOTIVATED_BY',), limits=QueryLimits(nodes=300, edges=300, output_bytes=1048576))
    assert not hview['truncated']
    assert len(hview['nodes']) == len(hview['edges']) == 200
    assert all(n['ref']['role'] == 'H' for n in hview['nodes'])
    assert 'graph_link_targets' in str([tuple(r) for r in graph.db.execute(
        'EXPLAIN QUERY PLAN SELECT * FROM graph_link_revisions WHERE target_role=? AND target_id=?', ('E', e.id))])
    zero = graph.affected_by(e.id, limits=QueryLimits(depth=0))
    assert zero['truncated'] and len(zero['nodes']) == 1 and zero['edges'] == []


def test_g10_all_graph_tables_have_immutability_guards_and_foreign_keys(graph):
    h = idea(graph)
    link(graph, 'ADDRESSES', h, Ref('O', graph.study_id))
    tables = [r[0] for r in graph.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'graph_%'")]
    for table in tables:
        triggers = [r[0] for r in graph.db.execute("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=?", (table,))]
        assert table + '_no_update' in triggers and table + '_no_delete' in triggers
        assert graph.db.execute(f'PRAGMA foreign_key_list({table})').fetchall()
    for statement in ('DELETE FROM graph_operations', 'UPDATE graph_ideas SET kind=\'Q\'',
                      'DELETE FROM graph_link_revisions', 'UPDATE graph_idea_revisions SET body=\'{}\''):
        with pytest.raises(sqlite3.IntegrityError):
            graph.db.execute(statement)
    assert graph.db.execute('PRAGMA foreign_key_check').fetchall() == []


def test_g1_to_g10_complete_offline_fixture_and_restart(tmp_path, monkeypatch):
    def no_network(*args, **kwargs):
        raise AssertionError('network forbidden in offline fixture')
    monkeypatch.setattr(socket, 'socket', no_network)
    path = tmp_path / 'fixture.db'
    summary = build(path)
    assert summary['synthetic'] and summary['preserved_all_v2_rows'] and summary['legacy_context_unchanged']
    assert len(summary['runs']) == len(summary['evidence']) == 2
    assert [t['status'] for t in summary['tasks']] == ['succeeded', 'succeeded', 'pending']
    assert all(e['validation_status'] == 'unvalidated' for e in summary['evidence'])
    assert summary['bounded_query_truncated']
    inspected = cli_fixture(path)
    assert inspected['graph_seq'] == summary['graph_seq']
    assert inspected['evidence'] == summary['evidence']
    with pytest.raises(ARFError):
        build(path)


def cli_fixture(path):
    import subprocess
    import sys
    result = subprocess.run([sys.executable, '-m', 'arf.graph_demo', '--inspect', '--db', str(path)],
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def test_g4_g7_lookup_stable_ids_pins_filters_and_each_edge_category(graph):
    e = observed(graph, 1)[0]
    h = idea(graph)
    l = link(graph, 'ASSESSES', e, h, polarity='supports', assumptions='a', scope='s')
    old_seq = graph.sequence()
    updated = graph.revise_idea(idea_id=h.id, expected_head=h.revision, text='New H revision',
                                operation_id='new-head', actor=ACTOR)['result']
    assert graph.read_graph(node=Ref('H', h.id))['nodes'][0]['ref']['revision'] == updated['revision_id']
    assert len(graph.read_graph(node=Ref('H', h.id), history=True)['nodes']) == 2
    assert graph.as_of(old_seq, node=Ref('H', h.id))['nodes'][0]['ref']['revision'] == h.revision
    assert graph.read_graph(node=Ref('H', h.id, updated['revision_id']))['edges'] == []
    direct = graph.read_graph(edge_id=l['result']['link_id'])
    assert len(direct['edges']) == 1 and direct['edges'][0]['id'] == l['result']['link_id']
    assert direct['nodes'] == []
    for edge in graph.read_graph(edge_types=('ATTEMPT_OF', 'PRODUCES'))['edges']:
        looked_up = graph.read_graph(edge_id=edge['id'])
        assert looked_up['edges'] == [edge] and not looked_up['truncated']
    b0, b1 = baseline(graph, 'B0'), baseline(graph, 'B1')
    for op, old, new in (('activate', None, b0), ('transition', b0, b1)):
        result = graph.record_baseline_transition(scope='demo', new_baseline=new, expected_prior=old,
            rationale='fixture', motivations=(e,), operation_id=op, actor=ACTOR)
    assert graph.read_graph(edge_id=result['result']['transition_id'])['edges'][0]['type'] == 'SUPERSEDES'
    for kwargs in ({'roles': ('OOPS',)}, {'edge_types': ('CAUSES',)}, {'edge_id': 'fact:bad'}, {'edge_id': '\ud800'}):
        with pytest.raises(GraphError):
            graph.read_graph(**kwargs)


def test_g6_concurrent_revision_head_compare_and_set(graph):
    h = idea(graph)
    def change(name):
        with Store(graph.store.path) as store:
            try:
                return GraphService(store).revise_idea(idea_id=h.id, expected_head=h.revision,
                    text=name, operation_id=name, actor=ACTOR)
            except GraphError as error:
                return error.code
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(change, ('writer-one', 'writer-two')))
    assert len([r for r in results if isinstance(r, dict)]) == 1
    assert results.count('conflict') == 1
    assert len(graph.read_graph(history=True, roles=('H',))['nodes']) == 2


def test_g7_creation_context_task_requires_actual_import_and_source_refs(graph):
    e = observed(graph, 1)[0]
    plans = PlanStore(graph.store)
    context = plans.export()['context_sha256']
    provider = ReplyWithEvidence(e.id)
    proposal = propose(plans, context, 'task-with-ref', 'task', provider=provider)['proposal_id']
    decide(plans, proposal, 'approve', 'fixture')
    task_id = import_proposal(plans, proposal)['task_id']
    l = link(graph, 'MOTIVATED_BY', Ref('T', task_id), e, timing='creation_context', proposal_id=proposal)
    assert graph.read_graph(edge_id=l['result']['link_id'])['edges'][0]['timing'] == 'creation_context'
    graph.store.add_task(TaskSpec.parse(spec('manual')))
    with pytest.raises(GraphError):
        link(graph, 'MOTIVATED_BY', Ref('T', 'manual'), e, op='manual-forgery',
             timing='creation_context', proposal_id=proposal)
    assert graph.store.task(task_id)['status'] == 'pending'


class ReplyWithEvidence:
    def __init__(self, evidence_id):
        self.evidence_id = evidence_id

    def propose(self, request):
        from arf.planner import PlannerResponse
        return PlannerResponse(canonical({'rationale': 'Synthetic source evidence',
            'evidence_refs': [self.evidence_id],
            'action': {'type': 'task_candidate', 'task_spec': spec('sourced-task')}}))


def test_g10_reference_list_and_request_size_bounds_no_dangling_joint_claim(graph):
    e1, e2 = observed(graph)
    for premises in ((e1, e1), (e1,) * 65, (e1, Ref('E', 'missing'))):
        with pytest.raises(GraphError):
            graph.create_claim(text='claim', assumptions='a', scope='s', premises=premises,
                               operation_id='bad', actor=RECORDER)
    before = graph.sequence()
    # Each field fits the text bound; the aggregate request does not fit 64 KiB.
    graph.store.add_task(TaskSpec.parse(spec('large-pending')))
    refs = tuple(Ref('T', 'x' * 4090 + str(i)) for i in range(30))
    with pytest.raises(GraphError, match='limit'):
        graph.create_baseline(scope='s', method='m', configuration='c', references=refs,
                              operation_id='too-big', actor=ACTOR)
    assert graph.sequence() == before
    with pytest.raises(GraphError):
        graph.create_claim(text='claim', assumptions='a', scope='s', premises=(e1, e2), joint=False,
                           operation_id='implicit-joint', actor=RECORDER)


def test_g10_candidate_scan_exhaustion_is_visible_even_for_irrelevant_edges(graph):
    e = observed(graph, 1)[0]
    h = idea(graph)
    # Incoming assessments are irrelevant to ancestry; their candidate limit
    # must still be reported instead of quietly hiding further incident links.
    for i in range(5):
        link(graph, 'ASSESSES', e, h, op='assess-' + str(i),
             polarity='supports', assumptions='a', scope='s')
    graph.store.add_task(TaskSpec.parse(spec('pending')))
    link(graph, 'INVESTIGATES', Ref('T', 'pending'), h, op='investigates')
    view = graph.ancestry('pending', limits=QueryLimits(nodes=20, edges=2))
    assert view['truncated'] and view['frontier']
