# Autonomous Research Framework (ARF)

**Status:** VS-001 implemented and verified locally on 2026-11-10. The CLI executes only the built-in deterministic demo worker. The autonomous research capabilities described below remain future work.

ARF is a future system for autonomously managing a potentially unbounded portfolio of research tasks to answer a *human-defined* ultimate research question. It will learn estimates of impact and evidence-acquisition cost, balance exploration and exploitation, schedule limited LLM/compute/human resources, and revise intermediate research baselines without changing the ultimate question.

## Authority boundary

A human owns the ultimate study question, success criteria, research limits, and approvals. Agents can generate and revise subordinate questions, hypotheses, experiments, task portfolios, intermediate baselines, and scheduling policies **within** those boundaries. An agent may propose revisions to the study charter, never apply them on its own.

The project development objective (to build ARF) is distinct from the ultimate question of **any individual study run using ARF**. No actual study question has yet been provided. `charter.template.yaml` is incomplete by design; `examples/demo-charter.yaml` is a throwaway integration fixture, not a user research objective.

## Read first

1. [`AGENTS.md`](AGENTS.md): durable Codex operating instructions and authority boundaries.
2. [`docs/project-charter.md`](docs/project-charter.md): purpose, principles, scope, and human ownership.
3. [`docs/architecture.md`](docs/architecture.md): intended separation of research management, scheduling, execution, evidence, and persistence.
4. [`docs/interfaces.md`](docs/interfaces.md): normative VS-001 contracts and status transitions.
5. [`tasks/VS-001.md`](tasks/VS-001.md): first implementation task, tests, and acceptance criteria.
6. [`prompts/codex-vs001.md`](prompts/codex-vs001.md): copy/paste prompt to start Codex.

## First milestone (VS-001)

Prove a complete, safe, restartable path:

`demo study charter -> create task -> persist -> claim -> execute approved local experiment -> record run/evidence/cost -> inspect -> recover from interrupted run`.

VS-001 deliberately has **no live LLM, Codex SDK, network calls, GPU orchestration, autonomous planning, exploration/exploitation, or baseline switching**. This is a vertical slice of the execution substrate, not the final autonomous research system.

## Setup

Requires Python 3.11+, PyYAML, and pytest for tests. Run commands from the repository root.

The verified setup in this workspace used already-installed PyYAML 6.0.1 and pytest 9.1.1, without network access:

```bash
python3 -m venv --without-pip --system-site-packages .venv
source .venv/bin/activate
python --version
```

Observed Python version: 3.12.3. The normal `python3 -m venv .venv` command failed here because `ensurepip` is unavailable; the setup above avoids that requirement. On another machine, when dependencies are absent, install Python's venv support and use the conventional installation below (not exercised in this workspace):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
```

## Working end-to-end demo

These commands were executed successfully in separate CLI processes against a fresh `.local/arf.db`. They use integration fixtures, not a real study question. Generated local databases and the virtual environment are ignored by Git.

```bash
python -m arf init --db .local/arf.db --charter examples/demo-charter.yaml
python -m arf task add --db .local/arf.db --spec examples/demo-task.json
python -m arf task list --db .local/arf.db
python -m arf run-next --db .local/arf.db
python -m arf task show --db .local/arf.db --id demo-mean
python -m arf evidence list --db .local/arf.db
python -m arf recover --db .local/arf.db
python -m arf run-next --db .local/arf.db
python -m pytest -q
```

Observed: task `succeeded`, result `{"mean":5.0,"count":4}`, one linked successful run, one **unvalidated** evidence row, and measured `wall_seconds=0.02032526209950447`. Duration varies per run. LLM tokens, GPU seconds and human minutes were zero; CPU time was unavailable (`null`). Recovery returned an empty `interrupted` list. The final `run-next` returned `{"status":"no_ready_task"}` without executing again. Identical charter reimport is safe; duplicate task creation returns an error rather than overwriting history.

All CLI output is JSON; errors go to stderr with nonzero exit status. `run-next` also returns nonzero for a recorded execution failure. List/show include dependencies and computed `blockers`; show includes run history and actual costs.

## Recovery and explicit retry

An interrupted controller leaves its committed attempt `running`. After confirming the previous controller has stopped:

```bash
python -m arf recover --db .local/arf.db
python -m arf task show --db .local/arf.db --id demo-mean
python -m arf task retry --db .local/arf.db --id demo-mean
python -m arf run-next --db .local/arf.db
```

`recover` marks abandoned attempts `interrupted` and tasks `needs_review`; repeated recovery changes nothing. Unknown duration stays `null`. Only an explicit retry of a failed/needs_review demo task permits a new attempt. Retry is an error for the successful task in the normal demo. This recovery/retry sequence is exercised by automated tests using a simulated crash at the durable claim boundary.

## Execution limits

The fixed worker runs under isolated Python in a subprocess with a five-second timeout, finite numeric input validation, result validation, and bounded recorded output. Task JSON cannot select code, commands, modules, URLs, or another worker. This is not a sandbox for untrusted code.

POSIX advisory locking serializes `run-next` and `recover` on one host; SQLite transactions and uniqueness constraints protect claims. Use one canonical database file on a local filesystem. Do not delete its `.controller.lock` file during operation, use hard-linked database aliases, or copy an active database. A forced controller kill can leave its side-effect-free child briefly alive; exactly-once execution and multi-host recovery are not guaranteed. Study snapshots and completed observations have SQL immutability guards, but filesystem/database owners remain trusted.

## Status and work ownership

- This package: VS-001 source, CLI, persistence, fixed worker, and automated acceptance tests are implemented. See current-state for the observed test count and verification details.
- Scope remains **only** VS-001. No real research study, autonomous planner, LLM integration, or advanced scheduler is implemented or authorized.
- Human + ChatGPT: review deviations, decide on public/data interface changes and future milestones.

See [`docs/current-state.md`](docs/current-state.md) for the precise handoff status.
