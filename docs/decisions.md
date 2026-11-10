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
