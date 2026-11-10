"""Pure synthetic fixture estimator/policies; never scientific impact computation."""
from dataclasses import asdict
from pathlib import Path
from statistics import median

from arf.decision_models import Constraints, Policy
from arf.plan_models import PlanError, sha


ESTIMATOR = {'name': 'synthetic-branch-and-worker-wall', 'version': 1}


def identity() -> dict:
    return {**ESTIMATOR, 'source_sha256': sha(Path(__file__).read_bytes())}


def estimate(context: dict, candidate: dict) -> dict:
    synthetic = candidate['definition']['synthetic']
    impact = candidate['definition']['impact']
    base = {'impact': impact, 'estimator': identity(), 'context_id': context['context_id'],
            'input_refs': candidate['definition']['refs'],
            'feedback': context['feedback'], 'calibration': 'synthetic_uncalibrated'}
    if synthetic is None:
        return {**base, 'direct': None, 'information': None, 'costs': {},
                'unknown_reason': 'No quantitative synthetic proxy supplied.'}
    branch = context['feedback']['branch']
    values = [synthetic['viable'], synthetic['nonviable']]
    direct = sum(values) // 2 if branch == 'unknown' else synthetic[branch]
    info = synthetic['information_bonus'] if branch == 'unknown' and synthetic['branch_relevant'] else 0
    costs = dict(synthetic['costs'])
    wall = [r['cost']['wall_seconds'] for r in context['execution']['runs']
            if r['status'] in ('succeeded', 'failed') and r['cost']['wall_seconds'] is not None]
    wall_source = 'configured_fixture_prior'
    wall_range = None
    if wall:
        costs['wall_seconds'] = median(wall)
        wall_range = [min(wall), max(wall)]
        wall_source = 'observed_same_fixed_worker_median'
    override = context['feedback']['cost_overrides'].get(candidate['definition']['origin_key'])
    if override is not None:
        costs['synthetic_tokens'] = override
    return {**base, 'direct': direct, 'direct_interval': [min(values), max(values)] if branch == 'unknown' else [direct, direct],
            'information': info, 'proxy_unit': 'synthetic_points', 'costs': costs,
            'cost_units': {'wall_seconds': 'seconds', 'cpu_seconds': 'seconds', 'gpu_seconds': 'seconds',
                           'llm_tokens': 'tokens', 'human_minutes': 'minutes', 'money': costs['currency'],
                           'synthetic_tokens': 'synthetic_tokens'},
            'wall_source': wall_source, 'wall_range': wall_range,
            'synthetic_cost_source': 'revealed_fixture_feedback' if override is not None else 'configured_fixture_prior',
            'unknown_cost_reason': 'Null dimensions are unavailable, never zero.'}


def rank(context: dict, candidates: list[dict], policy: Policy, constraints: Constraints) -> dict:
    if policy.name not in ('static', 'information') or policy.version != 1 or type(policy.weight) is not int or policy.weight < 0:
        raise PlanError('invalid', 'unsupported policy configuration')
    if constraints.hard:
        raise PlanError('unsupported_resource_constraint', 'no real cumulative resource guarantees')
    import math
    if 'money' in constraints.ceilings and not constraints.currency:
        raise PlanError('invalid', 'money ceiling requires an explicit currency')
    for dim, ceiling in constraints.ceilings.items():
        if dim not in ('wall_seconds', 'cpu_seconds', 'gpu_seconds', 'llm_tokens', 'human_minutes', 'money', 'synthetic_tokens'):
            raise PlanError('invalid', 'unknown cost dimension')
        if type(ceiling) not in (int, float) or (isinstance(ceiling, float) and not math.isfinite(ceiling)) or not 0 <= ceiling <= 10**15:
            raise PlanError('invalid', 'ceilings must be nonnegative finite numbers')
    members = []
    for c in candidates:
        e = estimate(context, c)
        reason = None
        for dim, ceiling in sorted(constraints.ceilings.items()):
            value = e['costs'].get(dim)
            if value is None:
                reason = 'unknown_required_cost:' + dim
                break
            if value > ceiling:
                reason = 'cost_ceiling:' + dim
                break
        if 'money' in constraints.ceilings and e['costs'].get('currency') != constraints.currency:
            reason = reason or 'incomparable_currency'
        if e['direct'] is None:
            reason = reason or 'missing_synthetic_proxy; scientific judgment retained'
        group = None if reason else (c['definition']['origin_order'] if policy.name == 'static'
                                      else -(e['direct'] + policy.weight * e['information']))
        members.append({'candidate_id': c['candidate_id'], 'version': c['version'], 'binding': c['binding'],
                        'priority_group': group, 'exclusion': reason, 'estimate': e,
                        'qualification': 'Synthetic comparison; scientific judgments remain fallible.',
                        'factors': {'policy': asdict(policy), 'direct': e['direct'], 'information': e['information']}})
    members.sort(key=lambda m: (m['priority_group'] is None, m['priority_group'] or 0,
                                m['candidate_id'].encode('utf-8'), m['version']))
    for ordinal, m in enumerate(members):
        m['ordinal'] = ordinal
    abstain = 'truncated_selection' if not context['selection_complete'] else (
        'missing_required_estimates' if not any(m['priority_group'] is not None for m in members) else None)
    return {'status': 'abstain' if abstain else 'ranked', 'reason': abstain,
            'members': members, 'policy': {**asdict(policy), 'source_sha256': identity()['source_sha256']},
            'constraints': asdict(constraints), 'portfolio_completeness': 'partial'}
