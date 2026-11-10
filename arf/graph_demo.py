"""Deterministic synthetic VS-003 fixture harness; not a research operator CLI."""

import argparse
import json
from pathlib import Path

from arf.authorization import decide, import_proposal
from arf.graph import GraphService
from arf.graph_models import Actor, QueryLimits, Ref
from arf.graph_store import migrate
from arf.models import ARFError, Charter, TaskSpec
from arf.planner import PlannerResponse
from arf.planning import propose
from arf.plan_models import canonical
from arf.plan_store import PlanStore, migrate as migrate_plan
from arf.service import run_next
from arf.store import Store

ACTOR = Actor('synthetic-fixture-operator', 'operator', 'offline VS-003 fixture')


def legacy_rows(store):
    tables = [r[0] for r in store.connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'graph_%' ORDER BY name")]
    return {table: [tuple(r) for r in store.connection.execute(f'SELECT rowid,* FROM "{table}" ORDER BY rowid')]
            for table in tables}


class SyntheticNote:
    def __init__(self, evidence_id):
        self.evidence_id = evidence_id

    def propose(self, request):
        return PlannerResponse(canonical({
            'rationale': 'Synthetic branching fixture; no scientific acceptance.',
            'evidence_refs': [self.evidence_id],
            'action': {'type': 'research_note', 'note_kind': 'question',
                       'text': 'Synthetic Q2: what further demo comparison could examine E2?'}}))


def inspect(store):
    graph = GraphService(store)
    view = graph.read_graph()
    return {'synthetic': True, 'schema_version': 3, 'graph_seq': graph.sequence(),
            'tasks': [{'task_id': t['task_id'], 'status': t['status']} for t in store.tasks()],
            'runs': [dict(r) for r in store.connection.execute('SELECT run_id,status,wall_seconds FROM runs ORDER BY run_id')],
            'evidence': [{'evidence_id': e['evidence_id'], 'validation_status': e['validation_status']}
                         for e in store.evidence()],
            'active_baselines': view['active_baselines'], 'truncated': view['truncated']}


def build(path: str | Path) -> dict:
    path = Path(path)
    if path.exists():
        raise ARFError('fixture requires a fresh database path; use --inspect for an existing fixture')
    root = Path(__file__).resolve().parents[1]
    with Store(path, create=True) as store:
        store.import_charter(Charter.parse((root / 'examples/demo-charter.yaml').read_bytes()))
        for task_id, values in (('synthetic-T1', [2, 4, 6, 8]), ('synthetic-T2', [8, 10])):
            store.add_task(TaskSpec.parse({'task_id': task_id, 'study_id': store.study()['study_id'],
                'title': 'Synthetic mean fixture', 'description': 'Engineering fixture only',
                'kind': 'demo_mean', 'input': {'values': values}, 'dependencies': []}))
            outcome = run_next(store)
            if outcome['status'] != 'succeeded':
                raise ARFError('fixed fixture worker did not succeed; no automatic retry')
        migrate_plan(store)
        plans = PlanStore(store)
        evidence = store.evidence()
        e1, e2 = [Ref('E', e['evidence_id']) for e in evidence]
        context = plans.export()['context_sha256']
        note = propose(plans, context, 'synthetic-note', 'note', provider=SyntheticNote(e2.id))['proposal_id']
        candidate = propose(plans, context, 'synthetic-task', 'task')['proposal_id']
        decide(plans, candidate, 'approve', ACTOR.name)
        t3 = import_proposal(plans, candidate)['task_id']
        legacy_context = plans.export()
        before = legacy_rows(store)
        migration = migrate(store)
        assert migrate(store)['status'] == 'already_current'
        assert legacy_rows(store) == before
        g = GraphService(store)
        receipts = []
        def record(action, operation_id, **kwargs):
            receipt = action(operation_id=operation_id, actor=ACTOR, **kwargs)
            receipts.append(receipt)
            return receipt['result']
        def idea(kind, name):
            r = record(g.create_human_idea, name, kind=kind, text='Synthetic ' + name,
                       assumptions='Demo numbers only', scope='synthetic-comparison')
            return Ref(kind, r['idea_id'], r['revision_id'])
        def link(name, type, source, target, **kwargs):
            return record(g.add_semantic_link, name, type=type, source=source, target=target,
                          rationale='Synthetic fixture attribution: ' + name, **kwargs)
        h1, h2 = idea('H', 'H1'), idea('H', 'H2')
        q = record(g.register_note, 'register-Q2', proposal_id=note)
        q2 = Ref(q['kind'], q['idea_id'], q['revision_id'])
        link('relevance', 'ADDRESSES', h1, Ref('O', g.study_id))
        for t in ('synthetic-T1', 'synthetic-T2'):
            link('intention-' + t, 'INVESTIGATES', Ref('T', t), h1)
        assessment = link('assessment-E1-H1', 'ASSESSES', e1, h1,
                          polarity='supports', assumptions='Fixed first input', scope='synthetic-comparison')
        link('assessment-E2-H1', 'ASSESSES', e2, h1, polarity='contradicts',
             assumptions='Different second input', scope='synthetic-comparison')
        link('assessment-E1-H2', 'ASSESSES', e1, h2, polarity='contradicts',
             assumptions='Competing synthetic interpretation', scope='synthetic-comparison')
        claim = record(g.create_claim, 'joint-C', text='Synthetic joint interpretation of E1/E2',
                       assumptions='Two distinct observed demo attempts', scope='synthetic-comparison',
                       premises=(e1, e2))
        c = Ref('C', claim['idea_id'], claim['revision_id'])
        link('Q2-motivation', 'MOTIVATED_BY', q2, e2, timing='creation_context', proposal_id=note)
        link('T3-intention', 'INVESTIGATES', Ref('T', t3), q2)
        motivation = link('T3-late-motivation', 'MOTIVATED_BY', Ref('T', t3), e2)
        baselines = []
        for name, reference in (('B0', e1), ('B1', c)):
            r = record(g.create_baseline, name, scope='synthetic-comparison',
                       method='Synthetic ' + name, configuration='Fixed demo comparison ' + name,
                       references=(reference,))
            baselines.append(r['baseline_id'])
        b0, b1 = baselines
        record(g.record_baseline_transition, 'activate-B0', scope='synthetic-comparison',
               new_baseline=b0, expected_prior=None, rationale='Synthetic initial baseline', motivations=(e1,))
        link('T1-baseline', 'USES_BASELINE', Ref('T', 'synthetic-T1'), Ref('B', b0))
        record(g.record_baseline_transition, 'B0-to-B1', scope='synthetic-comparison',
               new_baseline=b1, expected_prior=b0, rationale='Synthetic scoped operator transition',
               motivations=(e2, c), affected=((Ref('T', t3), 'retain'), (q2, 'redirect_proposed')))
        earlier = g.sequence()
        record(g.revise_or_withdraw_link, 'correct-assessment', link_id=assessment['link_id'],
               expected_head=assessment['revision_id'], rationale='Synthetic corrected scope',
               assumptions='Scope reconsidered', scope='synthetic-comparison', polarity='inconclusive')
        record(g.revise_or_withdraw_link, 'withdraw-motivation', link_id=motivation['link_id'],
               expected_head=motivation['revision_id'], rationale='Synthetic retrospective attribution withdrawn',
               withdraw=True)
        old = g.as_of(earlier)
        current = g.read_graph()
        assert next(e for e in old['edges'] if e['id'] == assessment['link_id'])['polarity'] == 'supports'
        assert next(e for e in current['edges'] if e['id'] == assessment['link_id'])['polarity'] == 'inconclusive'
        assert any(e['id'] == motivation['link_id'] for e in old['edges'])
        assert not any(e['id'] == motivation['link_id'] for e in current['edges'])
        assert legacy_rows(store) == before
        assert plans.export() == legacy_context
        bounded = g.affected_by(e2.id, limits=QueryLimits(depth=1, nodes=2, edges=2))
        assert bounded['truncated']
        return {**inspect(store), 'migration': migration, 'preserved_all_v2_rows': True,
                'legacy_context_unchanged': True, 'history_verified_at_seq': earlier,
                'bounded_query_truncated': bounded['truncated'], 'receipts': receipts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True)
    parser.add_argument('--inspect', action='store_true')
    args = parser.parse_args()
    if args.inspect:
        with Store(args.db) as store:
            result = inspect(store)
    else:
        result = build(args.db)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False, sort_keys=True))


if __name__ == '__main__':
    main()
