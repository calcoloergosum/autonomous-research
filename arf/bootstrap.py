"""Trusted, bounded first-ranking bootstrap for the offline synthetic profile."""
from dataclasses import asdict, dataclass, field
from pathlib import Path

from arf.decision_models import Constraints, Feedback, Policy, Selection, bounded
from arf.decisions import DecisionService
from arf.plan_models import PlanError, sha


@dataclass(frozen=True)
class BootstrapProfile:
    name: str = 'offline-synthetic-initial-ranking'
    version: int = 1
    policy: Policy = field(default_factory=Policy)
    constraints: Constraints = field(default_factory=Constraints)
    selection: Selection = field(default_factory=Selection)
    feedback: Feedback = field(default_factory=Feedback)


# Installed trusted local configuration, never supplied by candidate payloads.
# In particular, no evidence-relevance rules are inferred from fixed-worker success.
INITIAL_PROFILE: BootstrapProfile | None = BootstrapProfile()


def _configured(profile: BootstrapProfile | None) -> bool:
    return (isinstance(profile, BootstrapProfile)
            and profile.name == 'offline-synthetic-initial-ranking'
            and type(profile.version) is int and profile.version == 1
            and isinstance(profile.policy, Policy) and profile.policy == Policy()
            and type(profile.policy.version) is int and type(profile.policy.weight) is int
            and isinstance(profile.constraints, Constraints) and profile.constraints == Constraints()
            and type(profile.constraints.ceilings.get('synthetic_tokens')) is int
            and isinstance(profile.selection, Selection) and isinstance(profile.feedback, Feedback))


def bootstrap_initial(service: DecisionService, decision_id: str, publication_id: str,
                      actor: str) -> dict:
    """Only an explicit ranked dispatch invokes this; publication never runs a worker."""
    if service.db.in_transaction:
        raise PlanError('invalid', 'bootstrap policy requires no claim transaction')
    audit = {'version': 1, 'profile': None}
    # Read the installed profile once; concurrent configuration replacement cannot
    # change the saved inputs halfway through this attempt.
    installed = INITIAL_PROFILE
    heads = service.heads()
    if not heads:
        return {'reason': 'missing_candidates', 'audit': audit}
    if not _configured(installed):
        return {'reason': 'policy_unconfigured', 'audit': audit}
    configuration = asdict(installed)
    metadata = {'configuration': configuration, 'configuration_sha256': sha(bounded(configuration)),
                'source_sha256': sha(Path(__file__).read_bytes())}
    audit['profile'] = metadata
    context = service.capture_context(installed.selection, installed.feedback)
    # Do not silently combine a captured state with a different candidate manifest.
    with service.store.transaction():
        if service.head() is not None or service.heads() != heads or not service._matches(context):
            return {'reason': 'state_changed', 'audit': audit}
    try:
        decision = service.decide(decision_id, context['context_id'], heads,
                                  installed.policy, installed.constraints, actor=actor,
                                  controller_profile=metadata)
        audit['decision_id'] = decision_id
        if decision['candidate_heads'] != heads:
            return {'reason': 'state_changed', 'audit': audit}
        publication = service.publish(publication_id, decision_id, None, actor=actor)
    except PlanError as exc:
        if exc.code not in ('conflict', 'stale_context'):
            raise
        return {'reason': 'state_changed', 'audit': audit}
    audit['publication_id'] = publication_id
    return {'reason': None, 'audit': audit, 'publication_id': publication['publication_id']}
