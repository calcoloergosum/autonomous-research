"""Bounded, attributed synthetic relevance evaluation. Unknown evidence refuses."""
from copy import deepcopy
from pathlib import Path
import time

from arf.plan_models import sha

MAX_CHANGES = 64
CHECK_SECONDS = 1.0


def evaluate(original: dict, current: dict, original_heads: list, current_heads: list, constraints: dict | None = None) -> dict:
    start = time.monotonic()
    feedback = deepcopy(current['feedback'])
    reasons = []
    outcome = 'reuse'
    old_e = {e['evidence_id']: e for e in original['execution']['evidence']}
    new_e = {e['evidence_id']: e for e in current['execution']['evidence']}
    new_runs = [r for r in current['execution']['runs']
                if r not in original['execution']['runs']]
    changed = sorted(set(new_e) - set(old_e))
    rules = {r['task_id']: r for r in feedback['rules']}
    if len(changed) + len(new_runs) > MAX_CHANGES:
        outcome, reasons = 'defer', ['bounded_change_budget_exhausted']
    elif original['profile'] != current['profile']:
        outcome, reasons = 'refuse', ['critical_execution_profile_changed']
    elif not set(old_e) <= set(new_e) or any(new_e[k] != v for k, v in old_e.items()):
        outcome, reasons = 'refuse', ['missing_or_changed_old_evidence']
    else:
        relevant = False
        branch_values = []
        for eid in changed:
            evidence = new_e[eid]
            rule = rules.get(evidence['task_id'])
            task = next(t for t in current['execution']['tasks'] if t['task_id'] == evidence['task_id'])
            from arf.plan_models import canonical
            spec = {k: task[k] for k in ('task_id', 'study_id', 'title', 'description', 'kind', 'input', 'dependencies')}
            if not rule or rule['spec_sha256'] != sha(canonical(spec)):
                outcome = 'refuse'
                reasons.append('unknown_critical_evidence:' + eid)
                continue
            if eid not in feedback['evidence_refs']:
                feedback['evidence_refs'].append(eid)
            if rule['effect'] == 'branch_from_mean':
                branch_values.append('viable' if evidence['result']['mean'] >= 5 else 'nonviable')
                relevant = True
                reasons.append('relevant_synthetic_branch:' + eid)
            else:
                reasons.append('synthetic_engineering_only:' + eid)
            if rule['cost_surprise'] is not None:
                feedback['cost_overrides'][rule['task_id']] = rule['cost_surprise']
                relevant = True
                reasons.append('relevant_synthetic_cost:' + eid)
        if branch_values:
            if len(set(branch_values)) != 1 or (feedback['branch'] != 'unknown' and feedback['branch'] != branch_values[0]):
                outcome = 'refuse'
                reasons.append('contradictory_branch_feedback')
            else:
                feedback['branch'] = branch_values[0]
        for run in new_runs:
            if run['status'] != 'succeeded' or not any(e['run_id'] == run['run_id'] for e in new_e.values()):
                outcome = 'refuse'
                reasons.append('uncertain_failed_or_interrupted_attempt:' + run['run_id'])
        old_tasks = {t['task_id']: t for t in original['execution']['tasks']}
        for task in current['execution']['tasks']:
            prior = old_tasks.get(task['task_id'])
            if prior and prior['status'] in ('failed', 'needs_review') and task['status'] != prior['status']:
                outcome = 'refuse'
                reasons.append('explicit_retry_requires_new_recommendation:' + task['task_id'])
        if new_runs and 'wall_seconds' in (constraints or {}).get('ceilings', {}):
            relevant = True
            reasons.append('observed_wall_cost_consulted_by_ceiling')
        if original['graph']['graph_seq'] != current['graph']['graph_seq']:
            relevant = True
            reasons.append('graph_or_baseline_change_requires_assessment')
        if original_heads != current_heads:
            relevant = True
            reasons.append('candidate_heads_changed')
        if relevant and outcome != 'refuse':
            outcome = 'replan'
    elapsed = time.monotonic() - start
    if elapsed > CHECK_SECONDS:
        outcome = 'defer'
        reasons.append('assessment_time_budget')
    return {'outcome': outcome, 'reasons': reasons or ['consulted_premises_unchanged'],
            'feedback': feedback, 'original_context_id': original['context_id'],
            'current_context_id': current['context_id'], 'candidate_heads': current_heads,
            'original_partiality': original['portfolio_completeness'],
            'read_set': {'constraints': constraints or {}, 'old_evidence': sorted(old_e), 'new_evidence': sorted(new_e),
                         'changed_runs': [r['run_id'] for r in new_runs],
                         'old_graph_seq': original['graph']['graph_seq'], 'new_graph_seq': current['graph']['graph_seq'],
                         'profile': current['profile']},
            'evaluator': {'name': 'synthetic-relevance', 'version': 1,
                          'source_sha256': sha(Path(__file__).read_bytes()),
                          'max_changes': MAX_CHANGES, 'check_seconds': CHECK_SECONDS},
            'uncertainty': 'Only explicit synthetic rules establish noncritical relevance; no scientific relevance model.',
            'cost': {'wall_seconds': elapsed, 'cpu_seconds': None,
                     'predicted_check_seconds': None, 'predicted_recompute_seconds': None,
                     'unknown_reason': 'No calibrated controller cost predictor.'}}
