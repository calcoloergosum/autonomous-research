# Codex implementation prompt — VS-002

You are working in `calcoloergosum/autonomous-research`.

**The human owner has approved the VS-002 architecture choices B / B / A / A** and authorized the narrow *offline* implementation described in `tasks/VS-002.md`. Those decisions are recorded as ADR-012–015 in `docs/decisions.md`.

## First, read

`AGENTS.md`, `README.md`, `docs/project-charter.md`, `docs/architecture.md`, `docs/interfaces.md`, `docs/decisions.md`, `docs/current-state.md`, `tasks/VS-001.md`, `tasks/VS-002-proposal.md`, and **`tasks/VS-002.md`**.

Review the Git worktree and preserve unrelated local changes.

## Implement precisely VS-002

1. Write `docs/interfaces-vs002.md` specifying the exact new CLI JSON/error contracts and migration/proposal/approval/import semantics from the approved task before implementing code.
2. Implement transactional SQLite schema v2 migration and prove preservation of existing schema v1 charter, tasks, runs, evidence and costs.
3. Implement deterministic, versioned context export and hashed persistent planner request/response/proposal records.
4. Implement strict tagged action validation: allowlisted `task_candidate`, inert `research_note`, and `no_action`.
5. Implement the **offline deterministic mock** provider interface only. No network, API credentials, model SDK or real research.
6. Add CLI `plan migrate/export/propose/list/show/decide/import` with explicit operator authorization, strict context freshness, transactionally linked task import, and replay-safe idempotency.
7. Keep VS-001 task execution unchanged and require a **separate** `run-next` after importing an approved task.
8. Add B1–B9 acceptance tests plus meaningful error and concurrency cases.

The planner cannot edit study charters, self-approve, run tools, create executable tasks without a trusted approval/import step, or change evidence claims.

Do not implement automated approval, free-form generated-code execution, actual LLM calls, exploration/exploitation policy, impact/cost predictor, GPU scheduler, or a long-running research loop.

The new command names and local limits in the approved task are explicitly documented **reversible VS-002 defaults**. Do not silently widen scope or invent external authority. If a material ambiguity remains around the public CLI, persistent semantics, migration or permission boundary, stop and report the choice instead of guessing.

## Verify and report

- Run the full tests and a clean offline CLI demonstration across separate processes.
- Demonstrate schema v1 -> v2 migration preserving the demo study and its history.
- Show that proposing a task **does not** create an executable task, and only explicit approval/import creates one pending task.
- Show that repeating approval/import and re-opening the database does not duplicate tasks/evidence or re-execute work.
- Demonstrate strict stale-context refusal and historical import-receipt replay.
- Confirm charter contents and hashes are unchanged.
- Run `git diff --check`; update README and `docs/current-state.md` with observed outcomes.

Provide a final concise report: changed files, actual tests run and counts, exact offline demo results, design assumptions, limitations and any architectural decisions requiring human review. **Do not claim successful execution unless verified.**
