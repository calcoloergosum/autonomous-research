"""Trusted offline test writer, never imported by the observer or exposed via HTTP."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from arf.store import Store
from arf.models import TaskSpec
from arf.decision_models import CandidateDefinition, Feedback, Rule, Synthetic
from arf.decisions import DecisionService
from arf.graph import GraphService
from arf.graph_models import Actor
from arf.service import run_next


def write(path, phase="first"):
    with Store(path) as store:
        sid = store.study()['study_id']
        store.add_task(TaskSpec.parse({'study_id': sid, 'task_id': 'pinned-arrival' if phase == 'pinned' else 'writer-task', 'title': 'Separate trusted writer',
            'description': '<script>window.injected = true</script>', 'kind': 'demo_mean',
            'input': {'values': [2, 4, 6, 8]}, 'dependencies': []}))
        if phase == 'pinned':
            return
        service = DecisionService(store)
        service.record_candidates('writer-candidates', [CandidateDefinition('writer-candidate', 'Synthetic writer candidate',
            synthetic=Synthetic(300, 300))], {'writer-candidate': 'writer-task'}, 'test-writer')
        GraphService(store).create_human_idea(operation_id='writer-idea', actor=Actor('test-writer', 'operator', 'offline observer test'),
            kind='Q', text='Fictional writer question', assumptions='Synthetic only', scope='fixture')
        rules = tuple(Rule(t['task_id'], service.binding(t['task_id'])['spec_sha256'], 'engineering_only') for t in store.tasks())
        context = service.capture_context(feedback=Feedback(rules=rules))
        decision = service.decide('writer-decision', context['context_id'], service.heads())
        service.publish('writer-publication', decision['decision_id'], service.head())
        result = run_next(store)
        assert result['task_id'] == 'writer-task', result
        print(result['task_id'])


if __name__ == '__main__':
    write(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else 'first')
