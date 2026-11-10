# Codex implementation handoff — VS-004

Repository: `calcoloergosum/autonomous-research`
Task: **Implement the approved bounded offline milestone** in [`tasks/VS-004.md`](../tasks/VS-004.md), consistent with ADR-024–029 in `docs/decisions.md`.

## Critical decisions already settled by the owner

- `python -m arf run-next --db PATH` is the **same public entry point** on every schema. On v1–v3 behavior, FIFO ordering, CLI errors and JSON remain exactly unchanged. On explicitly migrated v4 it automatically uses Research Manager recommendation priority among **existing admitted ready tasks**. No external `dispatch-next` verb is required; a trusted internal helper may be added. Do not call FIFO `Store.claim_next` directly on v4 to bypass ranking.
- The Scheduler must independently enumerate all admitted pending dependency-ready tasks before declaring no-ready; `needs_decision` (ready tasks but missing/invalid recommendation) and `deferred` (reasoned abstention) are **not** `no_ready_task`. No hidden FIFO fallback.
- Research Manager automatically determines/publishes priorities. No human activation on each round. However `run-next` remains the only execution trigger: saving a priority does **not** execute work, grant task admission, approve/import tasks, or permit new worker code.
- Scientific impact cannot be fully calculated. Store reasoned, uncertain, possibly qualitative/contested/incomparable scientific judgments separately from synthetic numerical utility proxies and resource-cost vectors. Never treat demo worker success, LLM confidence, or synthetic rewards as real scientific impact.
- **One recommendation may guide more than one task claim**, with an independently recorded applicability/replanning evaluation before each claim. A new graph or execution hash is a *change signal*, not automatic rank invalidation. Unknown relevant evidence must not be silently classified irrelevant. Prefer conservative refusal/replan when relevant premises cannot be verified; no universal scientific relevance formula.

## Work sequence

1. Inspect current `main`, uncommitted files and repository guidance; read `AGENTS.md`, `README.md`, `docs/current-state.md`, `docs/decisions.md`, `docs/interfaces-vs002.md`, `docs/interfaces-vs003.md`, `tasks/VS-004.md` and the historical proposal/review. **The approved task has precedence over older recommendations.**
2. Before application code, write `docs/interfaces-vs004.md`: v4 schema and exact migration, trusted context/candidate/impact/cost/replanning/decision/dispatch interfaces, `run-next` v4 success/abstain/no-ready/needs-decision/error shapes, canonicalization/limits, claim atomicity, read-set relevance and rollback/replay. Preserve all old interfaces.
3. Implement only the bounded offline v4 additive migration and small decision service, synthetic policy fixture, qualitative impact-assessment storage, bounded cost-aware selective Replanning Policy and ranked `run-next` path. Reuse `controller_lock`, original transaction-owned claim, fixed worker and result/finalization/recover path. Do not add a new executor or a network/model integration.
4. Write and execute D1–D13 tests with special attention to:
   - Real ready tasks A (older) and B, but ranked execution B then A on **v4 `run-next`**.
   - **Same recommendation ID across two separately claimed runs** with recorded relevance checks; a relevant discovered item triggers a new recommendation.
   - A genuine empty ready set versus ready-but-unranked and deliberate `deferred`; full dependency and permission checks; no FIFO fallback.
   - Qualitative/incomparable scientific judgments without forced numeric impact; observed cost null versus zero; synthetic oracle isolation.
   - Concurrent decision/publication/claim, missing/critical evidence, stale state checked at claim, atomic receipt failure, interruption/recovery, exact replay and idempotency.
   - Populated schema v3→v4 migration, old schema/version rejection, and preservation of all VS-001/002/003 behavior, including the exact v1–v3 `run-next` JSON/errors.
5. Run the full `python -m pytest -q`, existing offline demos, new v4 demo and restart inspection, and `git diff --check`. Record **observed** results and limitations in `docs/current-state.md`, and update the approved task status only after genuine verification.

## Stop conditions

Do not silently change an accepted public interface or immutable charter, loosen task admission, replace the fixed demo worker, add untrusted code execution, use model APIs or spend external resources. If the technical design requires a material new choice about scientific attribution, permission/ownership, request idempotency, crash semantics or multi-claim validity beyond the approved narrow contract, **pause implementation and report the alternatives**.

When verified, commit the change set and report the commit SHA, exact tests, compatibility findings, open limitations, and direct source links. Do not claim production autonomous research from synthetic performance.
