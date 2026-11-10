# Codex — implement approved VS-004 initial ranking bootstrap (ADR-030)

Repository: `calcoloergosum/autonomous-research`

Read the current `main`, `AGENTS.md`, `docs/current-state.md`, ADR-024–030 in `docs/decisions.md`, `tasks/VS-004.md`, `docs/interfaces-vs004.md`, and **`tasks/VS-004-followup-initial-ranking.md`**.

**Implement ONLY the approved follow-up.** Existing VS-004 has 535 previously passing tests; do not treat this historical count as new verification.

### Desired behavior

On a v4 database, the first explicit `python -m arf run-next --db PATH` checks all admitted dependency-ready work. If a ready task and trusted, registered candidate versions exist but **no recommendation has been published**, the trusted offline Research Manager creates/records/publishes its initial ranking automatically, then the original ranked scheduler may claim one eligible admitted task. No per-ranking manual activation, second executor, generated worker, new TaskSpec, approval/import action or hidden FIFO fallback.

Use the pre-existing **versioned synthetic reference policy** only as an explicitly documented, reversible *offline fixture configuration*. Never imply that impact is fully computable or silently select a scientific priority for qualitative-only/incomparable candidates. Empty candidates, missing/unsupported policy configuration, unsuitable bindings, or missing trusted relevance information must produce safe, auditable `needs_decision`/abstention reasons rather than executing arbitrary work. Do not invent `engineering_only` evidence rules to enable subsequent reuse.

### Required verification

1. Document the exact bootstrap profile, status output and concurrency/receipt behavior in `docs/interfaces-vs004.md` before coding.
2. Show A/B admitted and candidates registered but **no decision/publication**; first v4 `run-next` automatically computes and publishes a synthetic rank and executes the highest eligible candidate B, with immutable provenance.
3. Subsequent calls use the existing selective Replanning Policy; reuse one recommendation across multiple claims **only when trusted, preconfigured relevance rules support it**. Otherwise conservatively refuse/require further decision.
4. Demonstrate no candidate, invalid/missing policy, unbound/unrankable candidates, blocked tasks, readiness/ranking mismatch, concurrent initializers and interrupted publication. Preserve all v1–v3 behavior and no-FIFO-fallback invariant.
5. Do **not** address the separate P2 issue (one unranked ready task blocking another ranked ready task), change research approvals or implement new models/workers.
6. Run full `python -m pytest -q`, VS-001–004 offline demos, restart/claim replay checks and `git diff --check`. Record **actual** test commands/results in `docs/current-state.md`, update follow-up status only if verified, then commit and report SHA plus any remaining limitations.

If actual code architecture reveals a material authorization or public-interface decision missing from the follow-up, report that trade-off rather than silently choosing it.
