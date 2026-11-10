# VS-004 follow-up — automatic first recommendation on v4 `run-next`

**Status: BEHAVIOR APPROVED (ADR-030); CODE NOT YET CHANGED.**
**Scope:** One bounded, local/offline follow-up to the verified VS-004 implementation. Read the existing `tasks/VS-004.md`, `docs/interfaces-vs004.md`, `docs/decisions.md`, `docs/current-state.md` and `AGENTS.md` before implementation.

## Problem

The implemented `arf.dispatch.dispatch_next` returns `needs_decision / missing` when a v4 database has ready tasks and versioned advisory candidates but `DecisionService.head()` has no publication. Current `arf.decision_demo` calls `decide` and `publish` explicitly before `run-next`. This leaves the **first** priority calculation outside the automatic workflow, even though later recommendation *replans* are automatic.

**Approved behavior:** When **existing** advisory candidates and actual admitted ready work exist, the *first explicit* v4 `run-next` should use a trusted, deterministic Research Manager path to evaluate the current context, record and publish an initial recommendation, then attempt one ranked claim. **No separate human activation of the recommendation.** Registering candidates or publishing a recommendation alone never starts a worker.

## Constraints

1. No new tasks, proposals, approvals, imports, workers, network/model requests or scientific-impact truth claims. The manager may only rank previously registered advisory candidate versions, and only separately verified stored admitted tasks may be executed.
2. The Scheduler still computes the **complete authoritative ready set** independently; a missing/invalid recommendation is not `no_ready_task`. The existing one-active-run, dependency, controller lock, transactional claim, worker result validation, explicit recovery and retry boundaries remain intact.
3. Do **not** silently choose a universal scientific reward function. The first offline version may use the already installed **explicitly documented, versioned synthetic fixture policy**, with stored policy name/version/weight/configuration, algorithm source identity and transparent provenance. The precise first-boot policy/profile binding must be recorded in `docs/interfaces-vs004.md` and test fixtures before code changes. A missing or unsupported trusted policy profile yields `needs_decision / policy_unconfigured` rather than guessed impact.
4. A blank candidate registry, invalid bindings, no mapped ready candidates, qualitative-only candidates with no declared comparison rule, truncated context or untrusted/unknown critical inputs must not automatically run any worker. Distinguish `missing_candidates`, `policy_unconfigured`, `no_ranked_ready_task`, and deliberate `deferred` as appropriate. No FIFO fallback.
5. Existing decisions/publications must **never** be overwritten by bootstrap; once a current publication exists, preserve the current selective reuse/replan path. A first published rank may continue to be reused for multiple claims under the existing Replanning Policy.
6. The initial capture, candidate-head manifest, decision and publication must be attributable to the trusted controller. Use bounded offline work and explicit request identities/receipts; handle concurrent initial invocations or interleaving candidate/task/graph writes with a compare-and-set initial head and final state recheck. Never claim from a stale or partially published initial decision.
7. On v1/v2/v3, preserve `run-next`'s exact FIFO behavior and response/error contract; do not expand public CLI syntax. A v4 `run-next` may return new **versioned** non-executing reason fields after documenting them.

## Narrow implementation approach (reversible engineering choice)

Add a small **bootstrap-if-no-publication** controller function, invoked only within the v4 `run-next` flow after confirming admitted ready work and no publication. Use `DecisionService.heads()`, a fresh joint graph/execution snapshot, and the existing `decide` and trusted `publish` operations. The **synthetic** default `Policy(name="information", version=1, weight=1)` / `Constraints(ceilings={"synthetic_tokens":10})`, already used by the current fixture, is a reasonable *temporary offline profile* **only if** documented as trusted local configuration and persisted in the created decision. It is **not** a scientific importance formula. It must not silently stand in for a future live Research Manager.

Do not invoke the full policy or model while an SQLite claim transaction is open. Before claim, recheck current publication head, candidate versions, task eligibility and decision applicability atomically. A second initializer must observe the winner or return a safe non-execution/conflict result; it must not fork independent initial heads. Reuse immutable receipts and the existing fixed worker lifecycle.

**Separately deferred question:** P2 concerns whether **one unranked but ready** task should prevent another ranked ready task from running. This task does not authorize changing the present strict all-ready coverage rule. Record P2 as pending, and test that bootstrap does not silently relax it.

## Acceptance tests

- A new v4 database with registered A/B candidate versions, existing admitted ready A/B, and **no** decision/publication: first `python -m arf run-next --db PATH` computes, stores, publishes and runs the highest-ranked eligible candidate (B in the documented information-aware fixture), without an explicit preceding `decide` or `publish` call.
- A second `run-next` can reuse the same recommendation after the existing documented noncritical synthetic evidence/relevance check; one ranking can link to more than one distinct run receipt.
- Existing publication: no initial-bootstrap duplicate; use normal reuse/replan, and preserve ledger history.
- No admitted ready tasks: no manager-generated ranking required, return genuine `no_ready_task` with existing reason.
- Ready tasks but **zero** candidates: `needs_decision / missing_candidates`, no worker and no invented candidate.
- Registered but unbound, invalid, unrankable, truncated or missing configured policy: explicit reason and **no execution**, no false `no_ready_task`.
- Concurrent first-call attempt and state changes around capture/publication: one consistent initial publication/claim or safe no-action; no duplicate attempts, orphaned running records or authorization bypass.
- Approval/import provenance, manual task registration and dependency blockers are revalidated under the same trusted claim path.
- All existing VS-001–004 tests and offline demos continue to pass. In particular, old `test_true_empty_blocked_missing_capacity_and_abstain` / `needs_decision missing` scenarios should be revised **only** where registered candidate coverage makes bootstrap applicable; no-candidate cases remain non-executing.

## Completion and handoff

Document exact bootstrap semantics/profile and v4 status/error JSON in `docs/interfaces-vs004.md`, then implement and test; update `docs/current-state.md` with commands, evidence and remaining limits. Run `python -m pytest -q`, all four offline demos and `git diff --check`. Commit the follow-up code only after verification and report the SHA, test totals and any residual issues. Do not report this follow-up as implemented until tests substantiate it.
