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
