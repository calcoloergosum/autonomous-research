# Architecture decision log

This file records accepted direction vs temporary implementation assumptions. Decisions about final research goals are human-owned. Do not silently upgrade provisional choices into permanent constraints.

## Accepted project-level principles

- **ADR-001 — Human-owned final research question.** The research charter and final evidence criteria cannot be changed by autonomous research agents. Intermediate tasks/baselines are mutable. Reason: prevent goal drift. Status: accepted.
- **ADR-002 — Unbounded research portfolio with bounded execution.** Separate all candidate ideas from frontier and currently funded tasks. Reason: task generation can outpace execution. Status: accepted.
- **ADR-003 — Research allocation and resource scheduling are distinct.** Value estimates guide proposals; scheduler enforces actual capacity and permissions. Reason: heterogeneous resources and working hours. Status: accepted.
- **ADR-004 — Evidence is decision-relative.** Weak intermediate evidence may guide exploration; final evidence is governed by the charter. Preserve provenance and validation status. Status: accepted.
- **ADR-005 — Baseline changes are not objective changes.** AI may revise subordinate research baselines, retain previous runs and update portfolios, but not alter ultimate question. Status: accepted.

## VS-001 implementation decisions (reversible)

- **ADR-006 — Single-host Python + SQLite.** Low operational cost for first slice. Reconsider when distributed workers or write contention appear. Status: provisional.
- **ADR-007 — No production LLM or unrestricted code execution.** Fixed deterministic local demo only. Integrate Codex/LLM worker after reliable task lifecycle and guardrails exist. Status: scoped to VS-001.
- **ADR-008 — FIFO for first executable task.** Simple comparison baseline, **not** the desired research allocation strategy. Replace in a later milestone after collection of actual costs. Status: provisional.
- **ADR-009 — Explicit recovery and retry.** Crash leaves ambiguous side effects; do not auto-retry. Reconsider only after strong idempotency/sandbox guarantees. Status: accepted for VS-001.
- **ADR-010 — CLI-first, no UI.** Data + service interfaces precede dashboards. Reconsider when human work queue becomes active. Status: provisional.
- **ADR-011 — YAML study charter plus JSON task specifications.** Human-readable charter and easy-to-validate task payloads. PyYAML as a small dependency is permitted. Could evolve with schema versioning. Status: provisional.

## Open questions deferred (do not resolve implicitly in VS-001)

- Formal definition of research impact / utility, evidence sufficiency, and calibration.
- Actual study question, real budget, API/model selection, human working hours.
- Policy choice (Thompson sampling, value-of-information heuristics, constrained lookahead, etc.).
- Baseline revision and branching policies.
- Multiple GPU workers, cancellation/preemption, scheduling across time zones.
- Generated-code sandboxing, network permission model, and external research data provenance.


## VS-002 decisions — human-approved 2026-11-10

The four design selections below were explicitly approved by the project owner after review of `tasks/VS-002-proposal.md`. They authorize a bounded **offline VS-002 implementation**, not live research, external model calls, spending, generated-code execution, or changing a study charter. The implementation contract is `tasks/VS-002.md`.

- **ADR-012 — Proposal persistence: Option B (accepted).** Use an explicit transactional SQLite schema v2 migration for versioned contexts, planner requests/responses, immutable proposals, trusted decisions, and import receipts. Preserve all schema v1 study/task/run/evidence records. An approved proposal-to-task import must be atomic with its provenance receipt. No split-file write journal.
- **ADR-013 — Public interface: Option B (accepted).** Provide a minimal operator CLI for context export, deterministic mock planning, proposal inspection, explicit authorization/rejection, and import. Preserve all VS-001 CLI behavior. The concrete new commands for this milestone are specified in `tasks/VS-002.md`.
- **ADR-014 — Context freshness: Option A (accepted for VS-002).** Approval and first import of a proposal require the current canonical study execution-state hash to equal the captured proposal context hash. An already committed import replays its receipt before checking freshness. Revisit this conservative rule when independent parallel jobs would generate needless conflicts.
- **ADR-015 — Non-executable research ideas: Option A (accepted).** Persist subordinate questions and hypotheses as inert `research_note` proposals, separate from executable tasks and evidence. They cannot be imported or run. A full hypothesis graph is deferred.

### VS-002-specific authorization guardrails

- The planner may propose but cannot authorize, import, execute, change an immutable study objective, alter evidence, or choose worker code. Only the local trusted operator may approve an executable task proposal in VS-002. Approval is recorded as a local operator assertion **without authentication**; do not portray it as a security boundary against the host owner.
- The internal permission model must keep the trusted authorizer separate from the proposing agent so policy-based authorization can be evaluated in a future milestone; **no automatic policy approval** in VS-002.
- The fixed demo worker remains the sole execution kind. The deterministic mock provider is the only enabled provider. Source code, public API and database meaning must not be widened silently.
- Proposal canonicalization and local size limits in the VS-002 task are **initial reversible implementation constraints**, not permanent research-policy decisions. The accepted B/B/A/A architectural choices above are independent from those numerical limits.


## VS-003 accepted decisions — human-approved 2026-11-10

The human owner approved the narrowed Research Graph architecture and authorized the bounded implementation described in `tasks/VS-003.md`, as part of finalizing PR #1. The separate historical design document `tasks/VS-003-proposal.md` remains useful for alternatives; **the approved task controls the initial implementation scope**. This authorizes offline local engineering and regression tests only, not substantive scientific research, live LLM/API calls, spending, untrusted generated-code execution, or charter changes.

- **ADR-016 (D1) — Separate execution and research relations (accepted).** Retain `dependencies` as the sole authoritative execution DAG. Add typed semantic research relations using existing task/run/evidence IDs and a combined *read* projection where helpful. No research edge affects scheduling or approval.
- **ADR-017 (D2) — SQLite schema v3 with bounded append-only history (accepted).** Use an explicit verified v2→v3 transactional migration, immutable graph revisions and operation receipts in the existing SQLite store; no dedicated graph DB or generic event-sourcing engine. Preserve all v1/v2 rows, bytes, hashes, IDs, and public behavior.
- **ADR-018 (D3) — Q/H/C ideas and typed evidence relations (accepted).** Represent subordinate question, hypothesis and claim as immutable-kind idea identities with exact revisions; distinguish factual execution provenance from unreviewed semantic interpretations. Use a closed first edge vocabulary and minimal joint-premise metadata; defer a general argumentation/hypergraph engine.
- **ADR-019 (D4) — Explicit research-note registration (accepted).** A valid VS-002 `research_note` remains an inert proposal until an explicit, idempotent graph registration creates a Q/H identity. No automatic note promotion, evidence, task creation, or scientific acceptance.
- **ADR-020 (D5) — Unreviewed assertions and attributed corrections only (accepted for VS-003).** Preserve provenance, reversible revisions and withdrawals; defer formal interpretation/observation review, evidence promotion and final scientific certification. A local operator correction is not scientific validation.
- **ADR-021 (D6) — Scoped operator-recorded baseline transitions (accepted).** Record immutable baseline snapshots and explicitly authorized old→new transitions with reasons and affected directions. Do not automatically select baselines or mutate/cancel/retry queued work. Human-owned research goal stays unchanged.
- **ADR-022 (D7) — Preserve VS-002 context v1; defer graph-aware planning (accepted).** Do not change existing context/export bytes/hashes, approval freshness or import semantics. Initial graph operations use exact revision pins and local graph sequence/head preconditions; no graph-context artifact or graph-bound executable proposal in VS-003. Reconsider when a future autonomous Research Manager needs it.
- **ADR-023 (D8) — Internal typed graph service plus offline fixture harness (accepted).** Do not add a public graph CLI or dashboard in this slice. Specify and test internal contracts in `docs/interfaces-vs003.md`; VS-005 visualization/monitoring remains deferred.

**Implementation boundary:** `tasks/VS-003.md` G1–G10 are normative acceptance targets. The broader proposal's G11–G13 remain informative extensions and must not silently enlarge VS-003. Existing VS-001/VS-002 invariants and authorizations remain in force.


## VS-004 execution-order decisions — human-approved direction 2026-11-10

These choices supersede the operator-per-recommendation and recommendation-only assumptions in the initial VS-004 technical draft. They **do not approve the full VS-004 implementation**, v4 migration, a new public execution API, real LLM calls, or unattended execution. The draft specification must still resolve the remaining V4 choices before code changes.

- **ADR-024 (V4-13) — Automatic research-priority selection (accepted).** Research Manager may automatically determine and update *priority among already admitted tasks*; a human does not have to activate each new ranking. A trusted controller must validate and persist the recommendation's exact context, candidate-to-task bindings and policy provenance before scheduling uses it. Ranking/activation grants **no** task admission, approval, import, new worker capability, retry, or unattended dispatch. The scheduler independently enforces actual eligibility and capacity at claim time. Exact activation representation, expiry/refresh and dispatch interface remain implementation-review questions.
- **ADR-025 (V4-12) — Verify actual ready work before stopping (accepted).** The scheduler must compute the authoritative set of admitted, pending, dependency-ready tasks independently of the recommendation list; resource/capacity limits are separate. If no eligible runnable task exists, no execution occurs, with the reason distinguished from capacity busy, blocked prerequisites, missing admission and study completion. When ready tasks **do** exist but no fresh/usable recommendation covers them, seek explicit Research Manager re-evaluation (or report its failure) and do **not** silently fall back to FIFO. An intentional, reasoned Research Manager abstention is distinct from recommendation generation failure. No automatic fabrication of new tasks, hidden unranked execution, infinite retry loop or declaration of scientific completion.

**Superseded by subsequent decisions:** The initial remaining V4-11 and one-claim questions were resolved in ADR-028 and the approved bounded task below; implementation remains offline-only.


## VS-004 research-value and recommendation-lifetime direction — 2026-11-10

These statements clarify the human owner's intended research-management philosophy; they **do not approve VS-004 implementation, a utility formula, a new scoring API or automatic dispatch**.

- **ADR-026 — Research impact is an uncertain assessment, not a computable truth (accepted principle).** The framework must not assume an algorithm can completely determine the scientific importance or eventual impact of an open-ended research question or action. A Research Manager combines reasoned scientific judgment, relevant context, evidence and uncertainty with available quantitative or qualitative estimates. Numerical heuristics may assist comparisons in explicitly bounded/synthetic cases, but their outputs are proxy assumptions, never objective ground truth, a mandatory global scalar score, or automatic proof of scientific value. Preserve competing assessments, qualitative/unknown impact, assumptions and provenance. Estimated resource costs and hard execution constraints are distinct from epistemic judgments of research importance. Human-owned study goals and success criteria remain the external reference.
- **ADR-027 — Prefer reusable research recommendations and selective replanning (design direction; detailed contract pending).** A recommendation is a versioned decision made under an original context, not necessarily invalid whenever *any* task/run/evidence or graph sequence changes. Prefer allowing one ranking to guide **multiple separately authorized, independently rechecked claims** when its relevant premises remain valid; a separate Replanning Policy decides when new information justifies the cost of reassessment. Store original context identity, consulted dependencies, current-validity/replanning decisions and reasons; never rewrite old decisions or silently skip new evidence. Force refusal on unverified/critical invalidation; otherwise explicitly reuse, re-evaluate or defer. Current drafts' one-claim lifetime and unconditional global context-hash expiration are **not approved** and should not be mistaken for this design direction.

**Pending implementation review:** What constitutes a decision-relevant change, how partial/unknown impact judgments are represented, how often and at what cost a Replanning Policy runs, confidence and human review thresholds, exact persistence and dispatch API, and how old v1–v3 execution behavior remains unchanged.


## VS-004 bounded implementation approval and V4-11 — human-approved 2026-11-10

The human project owner selected **the existing `run-next` interface on schema v4**, with recommendation-ordered execution; historical v1–v3 retain FIFO. This completes the discussed behavioral choices together with ADR-024–027. Implementation is authorized only for the **bounded offline VS-004 contract** in `tasks/VS-004.md`, not for production autonomy, spending, external models, new worker kinds, unattended execution or scientific certification.

- **ADR-028 (V4-11) — Schema-versioned `run-next` behavior (accepted).** On v1–v3 `run-next` retains exactly its existing FIFO interface and semantics. On verified v4, the **same external command** checks the authoritative ready set, obtains/reuses or explicitly re-evaluates a controller-validated Research Manager ranking, atomically claims its highest-ranked actually eligible admitted task, and runs **at most one** existing fixed worker. An internal ranked-dispatch seam is allowed; direct legacy FIFO `Store.claim_next` on v4 must refuse rather than bypass ranking. Schema migration is explicit; the changed selection policy is documented. A saved recommendation never independently triggers execution or task admission.
- **ADR-029 — VS-004 bounded offline implementation authorization (accepted for this milestone).** Implement the minimal Research Decision Loop and its audit/replanning/dispatch path as defined in the approved `tasks/VS-004.md` and D1–D13 acceptance criteria. The initial impact assessment may be qualitative; numerical utility is **only** a disclosed synthetic test policy. One recommendation may inform multiple claims only after each claim's independently recorded, bounded relevance assessment and current eligibility check; do not expire recommendations for unrelated status changes, and do not assume evidence changes are irrelevant without an explicit traceable basis. Prefer an additive verified SQLite v4 migration, deterministic fixtures, bounded queries and explicit no-ready/needs-decision/deferred outcomes. Specific reversible encoding/size limits and fixture tie-breaks belong to the approved task's versioned interface, not universal research policy.

**Authority and compatibility:** Existing VS-002 proposal approval/import, VS-003 graph ownership/baseline controls, exact charter bytes, worker allowlist, controller lock, dependency eligibility, one-active-run guarantee, recover/retry and v1–v3 responses remain unchanged. Offline implementation requires an additive internal interface specification and actual test evidence; no VS-004 code is reported as implemented by these ADRs. Material deviations from these boundaries require further human review.


## VS-004 follow-up — automatic initial recommendation (human-approved direction 2026-11-10)

- **ADR-030 — Bootstrap the first recommendation from existing candidates (accepted behavioral requirement).** On a verified v4 study with at least one admitted, dependency-ready task and **already registered versioned advisory candidates** but no published recommendation, an explicit `run-next` invocation should have the trusted Research Manager/controller **generate, validate and publish its initial ranking automatically**, then apply the usual transactional ranked claim and fixed-worker lifecycle to at most one eligible admitted task. No separate per-ranking operator activation is necessary. This is the missing *first-decision* counterpart to ADR-024, not an exception to the task-admission boundary.
- **Non-inference boundary.** If no registered candidates exist, if there is no supported/explicitly documented trusted offline decision policy or configuration, or if available candidates cannot be ranked/verified, do **not** create proposals, candidates or TaskSpecs, fabricate scientific impact scores, select FIFO, or execute. Return a distinguishable non-executing `needs_decision` reason. An intentional, recorded abstention remains `deferred` rather than a generation failure. No work automatically begins merely because candidates were registered or a ranking was published.
- **Implementation contract still required.** Use a versioned, locally trusted **synthetic fixture policy** only for the bounded offline VS-004 slice; do not silently elevate its defaults into a general research-science allocation rule. Document the initial policy/configuration source and any temporary default explicitly, along with atomic publication, races, idempotent audit and compatibility. An unconfigured production manager is not authorized to infer real scientific impact from arbitrary text.

This acceptance **does not resolve** the separate open question of whether an unranked but ready task must block selection among other ranked-ready tasks (previously identified as P2). Preserve existing v1–v3 FIFO behavior and all admission, dependency, worker, graph, charter and recovery safeguards.
