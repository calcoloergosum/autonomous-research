# VS-001 normative contracts

This document specifies externally visible behavior for the initial vertical slice. Codex may choose internal module names and SQL table names, but should preserve the meaning of the contracts below.

## Study charter

YAML schema:

```yaml
study_id: demo-mean-study
question: "What is the arithmetic mean of [2, 4, 6, 8]?"
success_criteria:
  - "The reported mean equals 5.0 for the fixed dataset."
constraints:
  - "Only the approved deterministic demo worker may run."
```

Required: non-empty `study_id`, `question`, non-empty list `success_criteria`; `constraints` may be empty. The template with null question is intentionally invalid for import. Reject malformed or incomplete charters. On first import, store question, criteria, constraints, source bytes hash, and timestamps. Same study ID with any changed charter bytes must be rejected; identical reimport may return already-exists without modifying records.

## Task creation

JSON task spec:

```json
{
  "task_id": "demo-mean",
  "study_id": "demo-mean-study",
  "title": "Compute deterministic example mean",
  "description": "Approved local numerical calculation for the first vertical slice.",
  "kind": "demo_mean",
  "input": {"values": [2, 4, 6, 8]},
  "dependencies": []
}
```

Only `kind=demo_mean` is runnable in VS-001. Reject arbitrary commands, Python snippets, module paths, network targets, and unrecognized kind values. The worker must validate `input.values` as a nonempty finite number list (reject bool, NaN, +/-Infinity). Task IDs are unique within the study. All dependencies refer to tasks in the same study; reject missing references, self-dependencies, and cycles. Task creation is idempotent only when the caller explicitly handles existing IDs; do not silently overwrite a task.

## Statuses

Task states: `pending`, `running`, `succeeded`, `failed`, `needs_review`.

- `pending -> running`: only if all dependencies are `succeeded`.
- `running -> succeeded`: valid worker output and persisted run/evidence.
- `running -> failed`: worker error, timeout, invalid output, or controlled execution failure.
- `running -> needs_review`: explicit recovery of a run left active after controller interruption (historical attempt status `interrupted`).
- `failed | needs_review -> pending`: only an explicit `task retry` action for the safe demo worker.

A pending task with unresolved or failed prerequisites is **not runnable**; list/show should expose dependencies and computed blocker information without inventing a separate persisted `blocked` state. A successful task is not automatically re-executed.

Run states: `running`, `succeeded`, `failed`, `interrupted`. Each run is a separate append-only attempt; final results are not overwritten. Incomplete running records may be closed by recovery. At most one active run per task. A task cannot be claimed twice concurrently.

## Execution & evidence

- Execute a fixed, audited deterministic local worker, ideally in a subprocess with an execution timeout. Its computation is the arithmetic mean of the supplied finite numeric values (e.g. `[2,4,6,8] -> 5.0`).
- Worker result structure: `{"mean": 5.0, "count": 4}` for the fixture. No unverified success on missing/invalid JSON. Test injected failures or invalid outputs at the executor boundary; do not expose an arbitrary command field in task JSON.
- Record `run_id`, `task_id`, start/end UTC timestamps, status, exit information or sanitized error summary, validated result JSON on success, and measured `wall_seconds` (monotonic clock).
- Cost observations: record `wall_seconds`; fields for `llm_tokens`, `gpu_seconds`, `human_minutes` should be `0` for the fixed demo, not invented usage. Optional CPU seconds may be `null` if unavailable. Predicted cost is separate from actual cost.
- After a **successful** run, record an evidence row that links the study, task and run, stores the worker result, provenance metadata, and `validation_status: unvalidated`. A failure is a run observation, not successful evidence.
- New runs after explicit retry must not erase prior run records. Repeated display or recovery must not create duplicate evidence.

## CLI contract

`python -m arf ...` is the required invocation shape. Exact commands:

```bash
python -m arf init --db PATH --charter PATH
python -m arf task add --db PATH --spec PATH
python -m arf task list --db PATH
python -m arf task show --db PATH --id TASK_ID
python -m arf task retry --db PATH --id TASK_ID
python -m arf run-next --db PATH
python -m arf evidence list --db PATH
python -m arf recover --db PATH
```

For VS-001 there is a single study per database, so `--id TASK_ID` is unambiguous. JSON output for list/show/evidence commands is preferred; useful errors must write to stderr and return a nonzero status. `run-next` exits cleanly with an explicit no-ready-task result if none are eligible.

## Recovery contract

The demo system runs one task at a time. `recover` scans for persisted `running` attempts, closes them as `interrupted`, marks associated tasks `needs_review`, and reports what changed. Calling `recover` twice is idempotent. **Do not automatically rerun interrupted work**. `task retry` must be explicit and may only apply to the side-effect-free demo task. If multiple controller processes are concurrently active, protect against changing a genuinely active run; the simplest VS-001 approach is a single-controller lock around `run-next` and `recover`, with documented limitations for forced kills.

## Error handling and transactional behavior

- Fatal errors must not leave a fake successful task or orphan evidence.
- Claim -> execute -> finalize occurs across multiple transactions; worker execution is **outside** a DB transaction.
- Use SQLite foreign keys, durable commit ordering, and a schema version.
- Distinguish failure to run from failure to evaluate evidence. The demo's evidence is unvalidated even when numerical output is deterministic.
- No secrets or arbitrary user-specified shell commands are stored/executed in this slice.
