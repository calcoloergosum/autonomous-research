# Prompt to hand to Codex — Implement VS-001

You are implementing the **first vertical slice** of the Autonomous Research Framework in this repository.

Before modifying anything, read:
- `AGENTS.md`
- `README.md`
- `docs/project-charter.md`
- `docs/architecture.md`
- `docs/interfaces.md`
- `docs/decisions.md`
- `docs/current-state.md`
- `tasks/VS-001.md`
- `examples/demo-charter.yaml`
- `examples/demo-task.json`

Then implement **exactly VS-001** as specified in `tasks/VS-001.md` and the normative contracts in `docs/interfaces.md`.

Priorities:
1. Preserve human ownership of the ultimate research question. The stored charter is immutable.
2. Implement the complete task -> run -> result/evidence/cost -> recovery path, with SQLite persistence and honest provenance.
3. Implement only the fixed, side-effect-free demo worker. Do not add unrestricted code execution, remote APIs, LLM integration, autonomous research planning, or advanced scheduling.
4. Keep storage, execution and future policy boundaries reasonably separate without speculative abstractions.
5. Add automated tests including crash recovery, failure behavior, immutable charter, dependencies, duplicate-run prevention, and unsupported task rejection.

Use Python 3.11+ with minimal dependencies. Choose small reversible implementation details yourself, documenting assumptions in `docs/current-state.md`. Do not silently modify public CLI/data contract or security-sensitive design decisions.

Run the complete automated test suite and documented end-to-end CLI demo. Update `README.md` to distinguish demonstrated working commands from prior planned commands. Update `docs/current-state.md` with actual results, architecture implications and known limitations.

At the end, report:
- Files changed
- Commands executed and their observed results
- Which acceptance criteria passed/failed
- Reversible assumptions and unresolved architectural decisions
- Any security or recovery limitations

Proceed with implementation; do not stop after giving a plan unless a material decision requires human input.
