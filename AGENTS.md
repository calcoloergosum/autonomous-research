# Agent instructions (repository root)

This is a research systems engineering repository. Before implementation, read `README.md`, `docs/project-charter.md`, `docs/architecture.md`, `docs/interfaces.md`, `docs/decisions.md`, `docs/current-state.md`, and the selected `tasks/VS-*.md` task.

## Non-negotiable boundaries

- The ultimate research question and success criteria of a **study** are human-owned. An autonomous agent may read a charter but must not modify it or silently redefine it, including by weakening evidence criteria.
- A development milestone is not authorization to start substantive research, spend external funds, make network requests, change unrelated files, or run arbitrary generated code.
- Keep observations, model predictions, and validated claims distinct. Never fabricate runs, tests, results, or costs.
- Resource limits are enforced by code, not by trusting an LLM prompt.
- Execute generated/unknown code only inside explicitly approved isolation. VS-001 and VS-002 authorize **only** the fixed demo experiment; planner text, commands and URLs cannot select execution.
- A crashed/uncertain run must never be silently counted as successful or automatically rerun when side effects are unknown.

## Current implementation scope

- Work only on the explicitly assigned milestone/task and within its authorized scope; defer other roadmap work. A proposal assignment authorizes design only, not implementation.
- Python 3.11+ and SQLite; keep external dependencies minimal. PyYAML for charter parsing and pytest for tests are acceptable. No large agent/orchestration framework in VS-001.
- Favor explicit, testable modules and small, typed functions. Keep storage, execution, and policy interfaces separate so they can evolve later.
- Preserve evidence and run history; do not mutate or delete observations to make a test pass.
- Preserve the VS-001 deterministic fixed-worker lifecycle and its tests. VS-002 adds proposals and explicit authorization only; no real model calls, automated approval, or new executable worker kinds.

## Working practice

- Check repository state before modifying files. Do not overwrite pre-existing user code or unrelated local changes.
- When an implementation detail is underspecified, choose the smallest reversible option, state the assumption in `docs/current-state.md`, and add a test when meaningful. If a choice changes the public CLI, persistent schema meaning, ownership, or safety boundary, stop and present the alternatives instead of guessing.
- Source-of-truth priority: human-approved study charter / latest human instructions > explicitly assigned task and `docs/interfaces.md` > architecture and decisions > implementation details. A proposal is not an approved implementation task.
- After coding, run `python -m pytest -q`, a documented end-to-end demo, and `git diff --check` where Git is available. Report results truthfully.
- Update `docs/current-state.md` with implemented features, verified commands, test results, and limitations. Do not claim success before tests actually pass.
- Never modify a study charter as part of an automated research operation. Demonstration fixtures are maintainable by developers; a recorded study charter is immutable once imported.
