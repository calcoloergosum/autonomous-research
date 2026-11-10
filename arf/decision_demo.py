"""Offline VS-004 fixture: actual fixed workers, fictional research judgments."""
import argparse
from dataclasses import replace
import json
from pathlib import Path

from arf.decision_models import (CandidateDefinition, Constraints, Feedback, Impact, Policy, Rule, Selection, Synthetic)
from arf.decision_policy import rank
from arf.decision_store import migrate_decisions
from arf.decisions import DecisionService, feedback_from
from arf.graph import GraphService
from arf.graph_models import Actor, QueryLimits, Ref
from arf.graph_store import migrate as migrate_graph
from arf.models import ARFError, Charter, TaskSpec
from arf.plan_models import canonical, sha
from arf.plan_store import PlanStore, migrate as migrate_plan
from arf.service import run_next
from arf.store import Store


ACTOR = Actor('fixture-operator', 'operator', 'offline VS-004 synthetic fixture')


def inspect(store: Store) -> dict:
    service = DecisionService(store)
    dispatches = [json.loads(r[0]) for r in service.db.execute('SELECT result FROM decision_dispatches ORDER BY rowid LIMIT 65')]
    assessments = [json.loads(r[0]) for r in service.db.execute('SELECT result FROM decision_assessments ORDER BY rowid LIMIT 65')]
    page = service.list_decisions()
    return {'synthetic': True, 'schema_version': 4, 'publication_head': service.head(),
            'tasks': store.tasks(), 'evidence': store.evidence(), 'decisions': page['items'],
            'decision_next_offset': page['next_offset'],
            'dispatches': dispatches, 'assessments': assessments,
            'active_baselines': service.graph.read_graph()['active_baselines'],
            'charter_sha256': store.study()['source_sha256'],
            'foreign_key_check': [tuple(r) for r in service.db.execute('PRAGMA foreign_key_check')]}


def build(path: str | Path) -> dict:
    path = Path(path)
    if path.exists():
        raise ARFError('fixture requires a fresh database path; use --inspect')
    root = Path(__file__).resolve().parents[1]
    with Store(path, create=True) as store:
        store.import_charter(Charter.parse((root / 'examples/demo-charter.yaml').read_bytes()))
        charter = store.study()
        migrate_plan(store)
        migrate_graph(store)
        legacy_export = PlanStore(store).export()
        assert migrate_decisions(store)['status'] == 'migrated'
        assert PlanStore(store).export() == legacy_export
        service = DecisionService(store)
        def admit(key, dependencies=()):
            store.add_task(TaskSpec.parse({'study_id': service.study_id, 'task_id': key,
                'title': 'Fixed offline fixture ' + key, 'description': 'No scientific impact claim',
                'kind': 'demo_mean', 'input': {'values': [2, 4, 6, 8]}, 'dependencies': list(dependencies)}))
        for key in ('A', 'B', 'C'):
            admit(key)
        admit('blocked', ('C',))
        graph = GraphService(store)
        hypothesis = graph.create_human_idea(operation_id='H', actor=ACTOR, kind='H',
            text='Fictional branch may be viable', assumptions='Unreviewed synthetic exercise', scope='fixture')['result']
        h = Ref('H', hypothesis['idea_id'], hypothesis['revision_id'])
        b0 = graph.create_baseline(operation_id='B0', actor=ACTOR, scope='fixture', method='static fixture',
                                    configuration='Initial synthetic reference')['result']['baseline_id']
        graph.record_baseline_transition(operation_id='initial', actor=ACTOR, scope='fixture',
            new_baseline=b0, expected_prior=None, rationale='Operator initial fixture reference', motivations=())
        def candidate(key, a, b=None, bonus=0, order=0, **kw):
            return CandidateDefinition(key, 'Synthetic ' + key, origin_order=order,
                origin_sha256=sha(canonical(['fixture', key])),
                synthetic=Synthetic(a, a if b is None else b, bonus, bonus > 0), **kw)
        definitions = [candidate('A', 8), candidate('B', 1, bonus=12, order=1),
                       candidate('C', 14, 0, order=2), candidate('blocked', 100, order=3),
                       candidate('unmapped-idea', 200, order=4, kind='synthesize',
                                 impact=Impact(status='incomparable'))]
        pairs = service.record_candidates('initial-candidates', definitions,
                                           {k: k for k in ('A', 'B', 'C', 'blocked')}, 'fixture')['versions']
        rules = tuple(Rule(k, service.binding(k)['spec_sha256'],
                           'branch_from_mean' if k == 'C' else 'engineering_only',
                           cost_surprise=9 if k == 'C' else None) for k in ('A', 'B', 'C', 'blocked'))
        context = service.capture_context(feedback=Feedback(rules=rules))
        seq = graph.sequence()
        execution = service.plans.export()
        service.decide('static-comparator', context['context_id'], pairs, Policy('static'))
        information = service.decide('information-manager', context['context_id'], pairs)
        service.publish('automatic-initial-priority', information['decision_id'], None)
        assert graph.sequence() == seq and service.plans.export() == execution
        # The diagnostic is inconclusive: no branch revealed by B's actual demo mean.
        # Synthetic information bonus was a misprediction, not an observed reward.
        outcomes = [run_next(store), run_next(store), run_next(store)]
        assert [o['task_id'] for o in outcomes] == ['B', 'A', 'C']
        assert len({o['recommendation_id'] for o in outcomes}) == 1
        evidence = {e['task_id']: e for e in store.evidence()}
        for key, polarity in (('B', 'inconclusive'), ('A', 'contradicts'), ('C', 'supports')):
            graph.add_semantic_link(operation_id='assessment-' + key, actor=ACTOR, type='ASSESSES',
                source=Ref('E', evidence[key]['evidence_id']), target=h, polarity=polarity,
                rationale='Fictional competing interpretation', assumptions='No scientific validation', scope='fixture')
        b1 = graph.create_baseline(operation_id='B1', actor=ACTOR, scope='fixture', method='updated fixture',
                                    configuration='Operator reference after C')['result']['baseline_id']
        graph.record_baseline_transition(operation_id='B0-to-B1', actor=ACTOR, scope='fixture',
            new_baseline=b1, expected_prior=b0, rationale='Explicit operator fixture transition',
            motivations=(Ref('E', evidence['C']['evidence_id']),))
        # Candidate arrival uses only already revealed observed C, never future outcomes.
        observed_branch = 'viable' if evidence['C']['result']['mean'] >= 5 else 'nonviable'
        admit('D')
        d = candidate('D', 200 if observed_branch == 'viable' else 2, order=5,
                      refs=(Ref('E', evidence['C']['evidence_id']),))
        service.record_candidates('arriving-D', [d], {'D': 'D'}, 'fixture')
        fourth = run_next(store)
        outcomes.append(fourth)
        assert fourth['task_id'] == 'D'
        assert fourth['recommendation_id'] != information['decision_id']
        new = service.show_decision(fourth['recommendation_id'])
        revealed = service.show_context(new['context_id'])
        assert revealed['feedback']['branch'] == 'viable'
        assert revealed['feedback']['cost_overrides']['C'] == 9
        assert service.show_assessment(fourth['assessment_id'])['outcome'] == 'replan'
        # Counterfactual is evaluator output only, never written as observed evidence.
        counterfactual = dict(revealed, feedback=dict(revealed['feedback'], branch='nonviable'))
        initial_records = [service.candidate(*p) for p in pairs]
        viable = rank(revealed, initial_records, Policy(), Constraints())
        nonviable = rank(counterfactual, initial_records, Policy(), Constraints())
        c_id = next(c['candidate_id'] for c in initial_records if c['definition']['origin_key'] == 'C')
        c_values = [next(m for m in r['members'] if m['candidate_id'] == c_id)['estimate']['direct'] for r in (viable, nonviable)]
        assert c_values == [14, 0]
        # Truncation must abstain even while blocked is now ready.
        feedback = feedback_from(revealed['feedback'])
        feedback = replace(feedback, rules=feedback.rules + (Rule('D', service.binding('D')['spec_sha256'], 'engineering_only'),))
        truncated = service.capture_context(Selection(limits=QueryLimits(nodes=1)), feedback)
        assert not truncated['selection_complete']
        abstain = service.decide('truncated-manager', truncated['context_id'], service.heads())
        service.publish('automatic-abstention', abstain['decision_id'], service.head())
        deferred = run_next(store)
        assert deferred['status'] == 'deferred'
        assert store.study() == charter
        # This private adverse oracle enters only the evaluator's final report.
        adverse_actual_payoff = {'A': 8, 'B': 1}
        return {**inspect(store), 'outcomes': outcomes, 'deferred': deferred,
                'preserved_charter': True, 'migration_preserved_export': True,
                'selection_writes_preserved_execution_and_graph': True,
                'counterfactual_C_direct': c_values,
                'bad_policy_case': {'unit': 'synthetic_points', 'oracle_in_policy_inputs': False,
                    'static_first_actual_payoff': adverse_actual_payoff['A'],
                    'information_first_actual_payoff': adverse_actual_payoff['B'],
                    'interpretation': 'Misleading diagnostic bonus loses to static in this fictional case.'}}


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
