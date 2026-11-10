"""Trusted controller orchestration of offline proposals, without authorization."""

from contextlib import contextmanager
import fcntl
from typing import Iterator

from arf import plan_policy
from arf.planner import (
    FixtureMock, PlannerRequest, Provider, PROMPT, PROMPT_VERSION, PROVIDER_NAME, PROVIDER_VERSION,
)
from arf.plan_models import (
    RESPONSE_LIMIT, PlanError, action_hash, canonical, normalize_response,
    proposal_content, sha, text,
)
from arf.plan_store import PlanStore
from arf.store import utc_now


@contextmanager
def planner_lock(plans: PlanStore) -> Iterator[None]:
    with plans.store.path.with_name(plans.store.path.name + ".planner.lock").open("a+b") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise PlanError("busy", "another planner controller is active") from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _diagnostic(error: PlanError) -> str:
    value = "".join(c for c in str(error) if c.isprintable())
    return value.encode("utf-8")[:4096].decode("utf-8", errors="ignore")


def _outcome(plans: PlanStore, request_id: str, status: str, *, raw: bytes | None = None,
             diagnostic: str | None = None, proposal_id: str | None = None) -> None:
    plans.db.execute("INSERT INTO plan_results VALUES (?,?,?,?,?,?,?,?)", (
        request_id, status, proposal_id, raw[:RESPONSE_LIMIT] if raw is not None else None,
        sha(raw) if raw is not None else None, len(raw) if raw is not None else None,
        diagnostic, utc_now(),
    ))


def _result(plans: PlanStore, request_id: str) -> dict:
    row = plans.db.execute("SELECT * FROM plan_results WHERE request_id=?", (request_id,)).fetchone()
    if row["status"] != "valid":
        code = "review_required" if row["status"] == "review_required" else "invalid"
        raise PlanError(code, row["diagnostic"])
    return {"request_id": request_id, "proposal_id": row["proposal_id"],
            "content_sha256": plans.proposal(row["proposal_id"])["content_sha256"], "status": "valid"}


def propose(plans: PlanStore, context_hash: str, request_id: str, fixture: str,
            *, provider: Provider | None = None) -> dict:
    """Internal provider injection is a test seam; CLI always uses FixtureMock."""
    text(request_id, "request ID")
    if fixture not in ("task", "note", "no_action", "invalid"):
        raise PlanError("invalid", "unknown deterministic fixture")
    raw_context, context = plans.context(context_hash)
    provider = provider if provider is not None else FixtureMock()
    with planner_lock(plans):
        replay = False
        with plans.store.transaction():
            existing = plans.db.execute("SELECT * FROM plan_requests WHERE request_id=?", (request_id,)).fetchone()
            identity = (context_hash, fixture, PROVIDER_NAME, PROVIDER_VERSION, PROMPT_VERSION,
                        PROMPT, sha(PROMPT), plan_policy.POLICY_VERSION, plan_policy.POLICY_SHA256)
            if existing is not None:
                if tuple(existing[k] for k in (
                    "context_sha256", "fixture", "provider_name", "provider_version", "prompt_version",
                    "prompt", "prompt_sha256", "policy_version", "policy_sha256",
                )) != identity:
                    raise PlanError("conflict", "request ID already bound to different input")
                if not plans.db.execute("SELECT 1 FROM plan_results WHERE request_id=?", (request_id,)).fetchone():
                    _outcome(plans, request_id, "review_required",
                             diagnostic="interrupted planner request; outcome unknown; automatic recall forbidden")
                replay = True
            else:
                plans.db.execute("INSERT INTO plan_requests VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                                 (request_id, *identity, utc_now()))
        if replay:
            return _result(plans, request_id)
        try:
            response = provider.propose(PlannerRequest(request_id, context_hash, raw_context, fixture))
        except BaseException as exc:
            # A hard process kill can bypass this. Replay closes the missing outcome.
            with plans.store.transaction():
                _outcome(plans, request_id, "review_required",
                         diagnostic=f"provider interrupted or uncertain: {type(exc).__name__}; no automatic recall")
            if not isinstance(exc, Exception):
                raise
            raise PlanError("review_required", "provider outcome uncertain; inspect request") from exc
        raw = response.raw
        try:
            if response.provider_name != PROVIDER_NAME or response.provider_version != PROVIDER_VERSION:
                raise PlanError("invalid", "provider identity differs from pinned mock")
            normalized = normalize_response(raw, context)
            if len(canonical(normalized)) > RESPONSE_LIMIT:
                raise PlanError("limit", "normalized response exceeds 64 KiB")
            content = proposal_content(normalized, context, context_hash)
            digest = sha(canonical(content))
            proposal_id = "proposal-" + digest
            action_digest = action_hash(content)
            with plans.store.transaction():
                same_action = plans.db.execute(
                    "SELECT content_sha256 FROM plan_proposals WHERE action_sha256=?", (action_digest,)
                ).fetchone() if action_digest else None
                if same_action is not None and same_action[0] != digest:
                    raise PlanError("conflict", "duplicate task action already has an immutable proposal")
                if not plans.db.execute("SELECT 1 FROM plan_proposals WHERE content_sha256=?", (digest,)).fetchone():
                    plans.db.execute("INSERT INTO plan_proposals VALUES (?,?,?,?,?,?,?,?,?,?,?)", (
                        proposal_id, digest, action_digest, content["study_id"], content["charter_sha256"],
                        context_hash, 1, canonical({"proposal_id": proposal_id, **content}),
                        plan_policy.POLICY_VERSION, plan_policy.POLICY_SHA256, utc_now(),
                    ))
                _outcome(plans, request_id, "valid", raw=raw, proposal_id=proposal_id)
        except PlanError as exc:
            with plans.store.transaction():
                _outcome(plans, request_id, "invalid", raw=raw if isinstance(raw, bytes) else None,
                         diagnostic=_diagnostic(exc))
            raise
        # Persistence errors deliberately leave an incomplete request. They never
        # authorize a provider recall, even when the transaction rolled back.
        return _result(plans, request_id)
