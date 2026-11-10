# Current state — VS-001 completed; VS-002 approved for implementation

**As of 2026-11-10:** The human owner approved the VS-002 design choices B/B/A/A and authorized an offline implementation task (ADR-012–015; `tasks/VS-002.md`; Codex handoff `prompts/codex-vs002.md`). **VS-002 has not been implemented or tested.** Live LLM calls and automated authorization remain forbidden.

The fixed local execution slice is implemented and exercised. This demonstrates persistence and recovery; it is not a research result or an autonomous research system. No human study question has been supplied; the demo charter remains a fixture. No study charter or example fixture was edited.

## VS-001 review closeout (2026-11-10)

Both review findings were present at the start of this follow-up. The worktree had three unrelated untracked files: `START_HERE_KO.md`, `WORKFLOW.md`, and `docs/roadmap.md`. They were left untouched; tracked files had no pre-existing changes. The earlier implementation/verification record below is retained as historical context.

- `arf/models.py` now compares the returned demo mean with `float(statistics.mean(original_input_values))`, after finite-value, field and count checks. `arf/service.py` and `arf/store.py` pass the original validated/persisted input to this internal validator. Previously, a well-formed mean of `100.0` for `[2,4,6,8]` was accepted and produced evidence; it now records a failed run with no result/evidence through `run-next`. Finalization also rechecks against persisted input; direct invalid finalization rolls back and leaves the active attempt for explicit recovery.
- Exact numeric equality is intentional for this fixed worker in the same Python runtime: it repeats the worker's `float(statistics.mean(...))` calculation, and JSON preserves that float. No approximate tolerance admits a nearby wrong value; numeric equality treats signed zero equally. `statistics.mean` avoids intermediate-sum overflow, retaining `[1e308,1e308] -> 1e308`. This is a demo correctness check, not a general scientific validator; successful observations remain `unvalidated`.
- Seven regression cases in `tests/test_lifecycle.py` cover forged `100.0`, the adjacent float above `5.0`, correct fixture output, cancellation with retained small residual, subnormals, zero from extreme cancellation, and the persisted-input finalization guard. Existing tests, including the extreme positive pair, remain intact.
- `AGENTS.md` now authorizes only the explicitly assigned task/milestone, distinguishes proposals from implementation authority, and generalizes task priority accordingly. `tasks/VS-001.md` is Completed; its acceptance criteria are unchanged. README's ownership/status bullet links to the new proposal.
- `tasks/VS-002-proposal.md` is design only and requires human review. It specifies context/proposal/authorization boundaries, a mock-only provider path, research notes outside executable tasks, validation and deduplication, and storage/interface alternatives. No VS-002 modules, dependencies, schema changes, new CLI commands, live model calls, or research runs were introduced.

### Closeout verification observed

Used the existing offline virtual environment (`source .venv/bin/activate`); no package installation or network access was needed. Observed versions: Python 3.12.3, SQLite 3.45.1, PyYAML 6.0.1, pytest 9.1.1. The original PATH still lacks `python`; activating the existing environment supplies it. The earlier ensurepip limitation below was not bypassed with a download.

| Actual command (after environment activation) | Observed result |
| --- | --- |
| `python -m pytest -q` before edits | 67 passed in 2.45s |
| `python -m pytest -q tests/test_lifecycle.py -k 'demo_wrong_well_formed_mean or demo_correct_mean_and_numerical_edges or demo_finalization_rechecks'` before source fix | 3 failed, 4 passed, 30 deselected; reproduced acceptance of forged means and missing persistence check |
| Same focused command after source fix | 7 passed, 30 deselected in 0.16s |
| `python -m pytest -q` after source/test changes | 74 passed in 2.78s |
| `git diff --check` after documentation updates | Exit 0; no whitespace errors |
| `git diff --no-index --check /dev/null tasks/VS-002-proposal.md` | No whitespace errors; exit 1 indicates the new file differs from `/dev/null` |

The README demo was rerun in separate CLI processes with a fresh database, preserving the previous `.local/arf.db` and its observations:

```bash
source .venv/bin/activate
demo_dir=$(mktemp -d .local/vs001-closeout.XXXXXX)
demo_db="$demo_dir/arf.db"
python -m arf init --db "$demo_db" --charter examples/demo-charter.yaml
python -m arf task add --db "$demo_db" --spec examples/demo-task.json
python -m arf task list --db "$demo_db"
python -m arf run-next --db "$demo_db"
python -m arf task show --db "$demo_db" --id demo-mean
python -m arf evidence list --db "$demo_db"
python -m arf recover --db "$demo_db"
python -m arf run-next --db "$demo_db"
```

All eight CLI commands exited zero. Actual database: `.local/vs001-closeout.Ikwd69/arf.db`. Observed one successful run `5e1ab004-46e3-4b9d-9b00-b28c2a23e0c2`, result `{"mean":5.0,"count":4}`, one linked **unvalidated** evidence row, and measured wall time **0.02093435451388359 seconds**. Other recorded resource usage was zero, with CPU time `null`. Charter SHA-256 remained `d33806961b80d24f57c72792f9511f29432eb25533990db1aa1cd1ea77dd95e9`. Recovery found no interrupted attempts; the final `run-next` returned `no_ready_task` without duplication.

### Remaining limits and next human decisions

The correctness check deliberately duplicates the fixed worker's formula; changes to that formula require keeping controller validation aligned. It provides no independent scientific evidence assessment and does not retroactively reclassify historical observations. No new public task/CLI contract, database schema meaning, ownership, security or recovery behavior was introduced. Existing single-host trust, output/memory bounds and interrupted-process limitations below remain.

Before VS-002 implementation, human review must select proposal persistence (artifact journal/reconciliation versus a transactional schema migration), public entry points (library harness versus explicit CLI), context freshness and deduplication semantics, the approval binding and local bounds, and whether to retain non-executable research notes or explicitly defer them. These alternatives are proposals, not accepted architectural decisions. No next milestone is approved by closing VS-001.

## Implemented files and behavior

- `pyproject.toml`, `.gitignore`: Python 3.11+ packaging, PyYAML runtime dependency, pytest test extra, ignored local artifacts.
- `arf/models.py`: charter and task validation, finite numerical input/output contracts, duplicate-key rejection, dependency cycle check.
- `arf/store.py`: SQLite schema version 1, foreign keys, full synchronous commits, transactional imports/claims/finalization/recovery, stable insertion-order FIFO, one study and one active attempt per database. Raw charter bytes, SHA-256, parsed charter fields and import timestamp are retained. Identical reimport is a no-op; changed bytes fail. SQL triggers protect charters, proposals, dependencies, completed runs and evidence from accidental edits/deletion.
- `arf/worker.py`, `arf/executor.py`: fixed arithmetic mean calculation in an isolated Python subprocess, five-second execution timeout, validated JSON and bounded recorded output. No selectable program or arbitrary code path.
- `arf/service.py`: POSIX controller lock, claim/execute/finalize orchestration, measured monotonic duration, sanitized error summaries, explicit recovery. Worker execution occurs outside SQLite transactions.
- `arf/cli.py`, `arf/__main__.py`, `arf/__init__.py`: all required `python -m arf` commands, JSON inspection output, useful stderr/nonzero failures.
- `tests/`: automated acceptance, restart, validation, concurrency, failure and recovery coverage.
- `README.md`: actual setup/demo commands, observed behavior, explicit retry semantics and execution limits.

At the original implementation's start, the working tree contained only untracked specification files, with no Git commits. Existing unrelated documents and fixtures were preserved. No Git commit, push, package download or network request was made during that implementation or this closeout.

## Original implementation verification observed

Environment: Python 3.12.3, SQLite from the standard library, PyYAML 6.0.1, pytest 9.1.1. There was no `python` on the original PATH. `python3 -m venv .venv` failed because ensurepip is unavailable. The successful offline setup was:

```bash
python3 -m venv --without-pip --system-site-packages .venv
source .venv/bin/activate
```

`python -m pytest -q`: **67 passed in 2.49s** after documentation and immutability-guard review (initial run: 67 passed in 2.47s). `git diff --check` exited zero. Since every project file is untracked in this new repository, an additional `git diff --no-index --check /dev/null FILE` inspection covered each added/edited deliverable; it emitted no whitespace errors (exit 1 indicates differing contents in no-index mode).

The documented end-to-end commands were executed against fresh `.local/arf.db`, each in a separate process:

| Command after `python -m arf` | Observed result |
| --- | --- |
| `init --db .local/arf.db --charter examples/demo-charter.yaml` | Imported `demo-mean-study` |
| `task add --db .local/arf.db --spec examples/demo-task.json` | Created pending `demo-mean` |
| `task list --db .local/arf.db` | One pending task, no blockers |
| `run-next --db .local/arf.db` | Succeeded; mean `5.0`, count `4` |
| `task show --db .local/arf.db --id demo-mean` | Persisted successful run/result/costs |
| `evidence list --db .local/arf.db` | Exactly one linked unvalidated observation |
| `recover --db .local/arf.db` | Empty interrupted list; no mutation |
| `run-next --db .local/arf.db` again | `no_ready_task`; no new attempt |

Demo run ID: `2e11fd0b-a8a2-4155-a940-9c6c848302c0`. Measured wall time: **0.02032526209950447 seconds**. LLM tokens, GPU seconds and human minutes: zero. CPU seconds: `null` (unmeasured). Charter source SHA-256: `d33806961b80d24f57c72792f9511f29432eb25533990db1aa1cd1ea77dd95e9`. These are observations from this execution, not future duration predictions or scientific validation.

## Acceptance coverage

| Scenario | Result and evidence |
| --- | --- |
| A1 Normal | Passed: real worker result, one successful attempt/evidence, measured nonnegative costs |
| A2 Restart | Passed: separate CLI processes retain charter/task/run/evidence/costs unchanged |
| A3 Dependencies | Passed: blockers exposed, failed prerequisites prevent execution, FIFO, missing/self/cross-study references rejected; direct cyclic graph and long acyclic graph tested |
| A4 Immutability | Passed: identical bytes preserve every field/timestamp; question/criteria/constraint/comment changes rejected; SQL update/delete/replacement guards tested |
| A5 Failure | Passed: malformed inputs rejected before claiming; injected exception/nonzero exit/invalid outputs and simulated plus actual subprocess timeouts yield failed attempts without evidence |
| A6 Crash recovery | Passed: durable-claim crash simulation, interrupted/needs_review transition, idempotent recovery, no automatic retry, explicit CLI retry creates a new attempt preserving history |
| A7 Claim safety | Passed: interleaved SQLite claim race grants one claim; separate CLI controllers cannot run/recover while another holds the lock |
| A8 Observation | Passed: repeated inspection/recovery/execution does not duplicate evidence; injected evidence-write failure rolls back the entire finalization and leaves a recoverable running attempt |
| A9 Security boundary | Passed: command/code/module/URL fields, unsupported kinds, executable text and URLs in numeric input rejected through CLI |

## Reversible implementation assumptions

- Schema version 1 is created transactionally. Unknown versions and nonempty unversioned databases are rejected; no speculative future migration is implemented. Table names, indexes and JSON layout inside storage are internal implementation choices.
- A single study occupies each DB; a partial unique index also permits only one persisted active run globally. A stale running attempt prevents `run-next` until explicit recovery, even if another pending task would otherwise be ready.
- FIFO uses a persisted integer insertion sequence, avoiding timestamp ties. Dependencies must already exist, so multi-task cycles cannot be built through the create-only interface. The graph check additionally rejects cycles; no task/dependency editing API is exposed.
- Missing task description defaults to an empty string and missing dependencies to an empty list; missing charter constraints default to an empty list. Unknown executable task/input fields are rejected. Descriptive title/text has no execution semantics. Duplicate JSON/YAML keys are rejected to avoid ambiguous imports.
- Numerical inputs/results must be representable as finite Python binary64 values; bool and integer magnitudes that overflow that representation are rejected. `statistics.mean` avoids intermediate sum overflow; floating-point rounding still applies.
- The worker timeout is a fixed five seconds, with no task-supplied override. The audited worker emits a small JSON result; stdout/stderr records are limited to 4096 characters each. The executor is injectable only through Python for controlled tests, with no CLI/task-code injection surface.
- `wall_seconds` measures controller-observed worker execution/validation using the monotonic clock. Running/interrupted attempts have `null` wall time because a restart cannot reconstruct it honestly. Zero non-demo resource usage is recorded separately from unmeasured CPU time. No predicted costs are invented.
- Every successful observation includes run/study/task linkage, worker identity `arf.demo_mean.v1`, input snapshot and charter hash. It stays `unvalidated`; VS-001 has no validation/promotion operation.
- POSIX `flock` on a persistent sibling `.controller.lock` file is the single-host controller mechanism. The lock spans claim, execution and finalization/recovery. Contention returns a useful nonzero error rather than waiting. Canonical paths resolve symlinks; hard-linked aliases and network filesystems are unsupported.
- `run-next` reports no eligible task with `no_ready_task` and exit zero. An observed execution failure emits its JSON run and exits nonzero. SQLite/persistence failure leaves a running attempt for explicit recovery rather than inventing a successful or failed completion.

These choices implement the existing CLI, ownership and restart contracts. No material contract change or additional human approval question was required.

## Architecture implications and limitations

Storage, validation, execution and orchestration remain separate modules. The selection baseline is FIFO; there are no speculative policy classes. Future resource scheduling can use the persisted actual costs, but must independently enforce new permissions and budgets. Additional workers require an explicit later design; the executor seam does not authorize them.

The filesystem owner and installed Python/package code are trusted. SQL guards deter accidental application writes; they are not tamper resistance against someone who can replace the database or drop its triggers. `-I` isolates Python customization; it is not an OS sandbox and does not authorize generated code. There is no network operation, external spending, model call, shell command execution, GPU worker, planner or dashboard.

The timeout and small output rely on the fixed audited worker. Capturing output is not a general memory sandbox for arbitrary programs. Import size, process memory and total database growth have no configurable quotas in this slice. A forced kill of the controller releases its advisory lock and can leave a child briefly running; that child cannot finalize the DB. Recovery treats its outcome and duration as unknown. The child is side-effect-free, and retry remains explicit; exactly-once execution, orphan-process supervision, distributed leases and full power-loss/storage-corruption recovery are not promised. Lock files must not be removed during operation. The crash test simulates interruption after the durable claim rather than asserting arbitrary machine power-loss behavior.

Deferred human decisions remain unchanged: actual study question/evidence criteria, real budgets and permissions, impact/cost prediction, allocation policy, baseline revision, human working hours, LLM APIs, GPU scheduling and generated-code isolation. No later vertical slice is implemented here; review `tasks/VS-002-proposal.md` and approve its scope and choices before implementation.
