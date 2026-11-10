# VS-002 offline planning contracts

This additive contract implements ADR-012–015 and `tasks/VS-002.md`. All
VS-001 commands and JSON/error behavior remain unchanged on schema v1 and v2.
Only the fixed `demo_mean` worker exists. These CLI names, encodings and limits
are reversible VS-002 defaults, not a permanent research policy.

## Commands and errors

Every command uses `python -m arf plan VERB --db PATH`. Successful commands
print one JSON value to stdout and exit 0. Operational errors print
`error: CODE: MESSAGE` on stderr, leave stdout empty and exit 1. Codes are
`schema`, `invalid`, `not_found`, `conflict`, `stale_context`, `unauthorized`,
`review_required`, `limit`, and `busy`. Database-open and SQLite/filesystem errors retain the
existing `error: MESSAGE`, exit 1 behavior. Argument errors exit 2;
KeyboardInterrupt exits 130. Messages are diagnostic, not a stable API.

| Verb and additional arguments | Exact top-level response |
| --- | --- |
| `migrate` | `{"schema_version":2,"status":"migrated"}` or status `already_current` |
| `export` | `{"context_sha256":HASH,"export_version":1,"size_bytes":N}` |
| `propose --context HASH --request-id ID --fixture task\|note\|no_action` | `{"request_id":ID,"proposal_id":ID,"content_sha256":HASH,"status":"valid"}` |
| `list` | Array of proposal views (same shape as show), sorted by proposal ID |
| `show --id PROPOSAL_ID` | Proposal view below |
| `decide --id PROPOSAL_ID --decision approve\|reject --operator TEXT` | Decision record below |
| `import --id PROPOSAL_ID` | Import receipt below |

`show` returns exactly `envelope`, `content_sha256`, `action_sha256` (null for
inert actions), `canonicalization_version`, `created_at`, `requests`,
`context`, `decision` (null when absent), and `receipt` (null when absent).
`envelope` has exactly integer `proposal_version: 1`, controller-owned
`proposal_id`, `study_id`, `charter_sha256`, `context_sha256`, plus normalized
`rationale`, sorted `evidence_refs`, and `action`. Research notes and no-action
records never have a task status or evidence validity claim.

`context` is the exact exported JSON object, exposing all evidence with
`validation_status: unvalidated`. `requests` is sorted by request ID; each
entry contains `request_id`, `context_sha256`, `fixture`, `provider_name`,
`provider_version`, `prompt_version`, `prompt_sha256`, `prompt_base64`,
`policy_version`, `policy_sha256`, `started_at`, `status`, `completed_at`,
`raw_sha256`, `raw_size_bytes`, `raw_prefix_base64`, `diagnostic`, `usage`.
Usage is null (unmeasured); no live provider cost is inferred. Raw bytes are
retained in full up to 64 KiB; oversized invalid replies retain only that prefix
plus the full hash and byte count. The prompt is a fixed versioned artifact.
Invalid replies are persisted as request diagnostics, never valid proposals;
replaying such a request returns `invalid`. Interrupted requests become
`review_required`; replay never invokes the provider again. These request-only
records are inspectable through the internal request API and SQLite; list/show
cover valid proposals and their linked request provenance.

Decision records have exactly `proposal_id`, `content_sha256`, `study_id`,
`charter_sha256`, `context_sha256`, `policy_version`, `policy_sha256`,
`decision`, `operator`, `decided_at`. They are immutable. An identical repeated
decision/operator replays the record before freshness; any conflict fails.
Only a valid task candidate can be decided, including rejection. Approval
requires fresh context; rejection needs no freshness and never authorizes import.
Operator is a local assertion, not authenticated identity. The provider cannot
supply any decision field. The trusted authorizer is a distinct interface.

Receipts have exactly `proposal_id`, `task_id`, `study_id`, `spec_sha256`,
`imported_at`. Task creation and receipt insertion share one transaction.
Reimport returns the committed receipt before freshness or policy rechecks,
even after execution. A matching manually created task is always a collision;
it is never adopted. Import requires a separate `run-next` for execution.

## Canonical content, limits and mock

Canonicalization/export version 1 uses UTF-8 JSON, sorted keys, compact
separators, unescaped Unicode and no nonfinite numbers. TaskSpec optional
`description` and `dependencies` defaults are normalized; dependencies and
evidence references are unique sorted sets. Numeric input list order is
preserved. Duplicate JSON keys, extra/missing fields, NaN/Infinity and malformed
unions are rejected. Maximum raw response is 64 KiB, context is 1 MiB, every
provider text field/key and operator/request ID is 4 KiB UTF-8, dependency and
evidence lists are at most 64 elements, and JSON container depth is at most 32
(scanned before parsing). Oversized exports fail without truncating evidence.

The provider supplies only rationale, evidence_refs, and one action:

- `task_candidate` with `task_spec` containing only existing TaskSpec fields.
  Only demo_mean, finite input and existing same-study dependencies are allowed.
- `research_note` with note_kind question or hypothesis and bounded nonempty text.
- `no_action` with bounded nonempty reason.

Text is data. The trusted controller binds the study, charter, context and IDs.
Proposal ID is `proposal-` plus SHA-256 of canonical content excluding ID and
timestamps; content includes proposal version, study/charter/context binding,
rationale, references and action. Identical content across request IDs links to
one proposal. A separate unique task-action hash covers study and normalized
full TaskSpec, excluding rationale/context. An action duplicate with different
content is a conflict, never another approval opportunity. Different task IDs
are distinct candidates; scientific equivalence is not inferred.

Only `fixture-mock` version `1` is enabled. The `task` fixture proposes
`planner-demo-` plus a context-hash prefix with the fixed [2,4,6,8] input;
`note` deterministically selects question/hypothesis from the request ID hash;
`no_action` explains the offline boundary. Internal test fixtures cover invalid
replies without adding CLI execution capabilities. Provider input contains only
immutable context/request/prompt data; no Store, credentials, tools or executor.

## Persistence, migration and concurrency

`init` creates schema v1. `plan migrate` explicitly upgrades v1 to v2 in one
transaction, retaining every old row/identity and all charter bytes. It verifies
the known v1 schema before adding planning tables, rejects unknown/unrelated
schemas without writes, and is idempotent. Planning on v1 fails with `schema`.
Completed requests use append-only outcome rows; all planning artifacts,
decisions and receipts are protected against update/delete. Foreign keys and
unique hashes/IDs prevent duplicate records. Host/database owners remain trusted.

Context export uses one consistent read transaction. Context contains
`export_version`, `canonicalization_version`, `study` (parsed charter, original
source_base64/hash and import time), `tasks` (specifications, dependencies,
statuses and original row sequence/timestamps), `runs` (outcomes and observed
costs with nulls intact), and `evidence` (IDs/results/provenance/labels/times).
Arrays have deterministic ordering by task sequence, run ID and evidence ID;
dependencies are sorted. Export timestamps and all planner tables are excluded
from identity. Exact canonical bytes and their hash are stored together.

First approval and import compute the current execution-state hash within a
write transaction and require equality with the pinned hash. Changed execution
state requires a new export/proposal/approval. Export storage uses a separate
transaction after its consistent read; a concurrent change simply makes that
snapshot stale. Decisions/imports serialize with other writers via SQLite
BEGIN IMMEDIATE. Propose holds a nonblocking per-database planner lock across
request creation, mock invocation and finalization. A concurrent propose gets
`busy`; a restart encountering an incomplete request records review_required
instead of recalling the mock. Do not remove lock files while operating.

| Durable restart point | Next identical operation |
| --- | --- |
| Context stored | Same bytes/hash; no duplicate snapshot |
| Request started, no outcome | Record review_required; no provider recall |
| Invalid/review-required outcome | Same refusal; no provider recall |
| Valid proposal/result stored | Return persisted request/proposal link |
| Decision stored | Identical decision replays; conflict refuses |
| Import interrupted before commit | No task or receipt; explicitly invoked import may try again |
| Receipt committed | Replay receipt, never execute/retry the task |

## Offline CLI example

Run from the repository root after activating the environment. Each command
runs a separate process; replace HASH/PROPOSAL with the printed values.

```bash
python -m arf init --db .local/vs002.db --charter examples/demo-charter.yaml
python -m arf task add --db .local/vs002.db --spec examples/demo-task.json
python -m arf run-next --db .local/vs002.db
python -m arf plan migrate --db .local/vs002.db
python -m arf plan export --db .local/vs002.db
python -m arf plan propose --db .local/vs002.db --context HASH --request-id demo-plan --fixture task
python -m arf plan show --db .local/vs002.db --id PROPOSAL
python -m arf plan import --db .local/vs002.db --id PROPOSAL  # unauthorized, exit 1
python -m arf plan decide --db .local/vs002.db --id PROPOSAL --decision approve --operator local-demo
python -m arf plan import --db .local/vs002.db --id PROPOSAL
python -m arf run-next --db .local/vs002.db
python -m arf plan import --db .local/vs002.db --id PROPOSAL  # same historical receipt
```

This verifies plumbing only. No charter interpretation, scientific validation,
strong identity, automatic authorization, network, model SDK or research loop
is introduced.
