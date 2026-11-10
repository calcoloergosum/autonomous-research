"""Trusted local operator decisions and transactional import; never exposed to provider."""

from arf import plan_policy
from arf.models import TaskSpec
from arf.plan_models import PlanError, canonical, sha, text
from arf.plan_store import PlanStore
from arf.store import utc_now

BINDING_FIELDS = ("proposal_id", "content_sha256", "study_id", "charter_sha256",
                  "context_sha256", "policy_version", "policy_sha256")


def _check_policy(proposal: dict) -> None:
    if (proposal["policy_version"] != plan_policy.POLICY_VERSION
            or proposal["policy_sha256"] != plan_policy.POLICY_SHA256):
        raise PlanError("unauthorized", "proposal policy differs from current local policy")


def _fresh(plans: PlanStore, proposal: dict) -> None:
    if sha(plans.context_bytes()) != proposal["context_sha256"]:
        raise PlanError("stale_context", "execution state changed; export and propose again")


def decide(plans: PlanStore, proposal_id: str, decision: str, operator: str) -> dict:
    text(operator, "operator")
    if decision not in ("approve", "reject"):
        raise PlanError("invalid", "decision must be approve or reject")
    with plans.store.transaction():
        proposal, envelope = plans.validate_proposal(proposal_id)
        if envelope["action"]["type"] != "task_candidate":
            raise PlanError("unauthorized", "inert notes/no_action cannot be authorized or imported")
        existing = plans.decision(proposal_id)
        if existing is not None:
            if existing["decision"] == decision and existing["operator"] == operator:
                return existing
            raise PlanError("conflict", "an immutable decision already exists")
        _check_policy(proposal)
        if decision == "approve":
            _fresh(plans, proposal)
        plans.db.execute("INSERT INTO plan_decisions VALUES (?,?,?,?,?,?,?,?,?,?)", (
            *(proposal[k] for k in BINDING_FIELDS), decision, operator, utc_now(),
        ))
        return plans.decision(proposal_id)


def import_proposal(plans: PlanStore, proposal_id: str) -> dict:
    with plans.store.transaction():
        # A committed receipt is the authority for replay; it precedes freshness.
        receipt = plans.receipt(proposal_id)
        if receipt is not None:
            return receipt
        proposal, envelope = plans.validate_proposal(proposal_id)
        if envelope["action"]["type"] != "task_candidate":
            raise PlanError("unauthorized", "only task candidates can be imported")
        decision = plans.decision(proposal_id)
        if decision is None or decision["decision"] != "approve":
            raise PlanError("unauthorized", "explicit local operator approval required")
        if any(decision[k] != proposal[k] for k in BINDING_FIELDS):
            raise PlanError("unauthorized", "approval binding does not match exact proposal")
        _check_policy(proposal)
        _fresh(plans, proposal)
        spec_data = envelope["action"]["task_spec"]
        spec = TaskSpec.parse(spec_data)  # Recheck allowlist and finite input.
        if plans.db.execute("SELECT 1 FROM tasks WHERE task_id=?", (spec.task_id,)).fetchone():
            raise PlanError("conflict", "task ID collision; manual tasks cannot be adopted")
        plans.store._add_task_in_transaction(spec)
        plans.db.execute("""INSERT INTO plan_receipts
            (proposal_id,task_id,study_id,spec_sha256,imported_at) VALUES (?,?,?,?,?)""",
                         (proposal_id, spec.task_id, spec.study_id, sha(canonical(spec_data)), utc_now()))
        return plans.receipt(proposal_id)
