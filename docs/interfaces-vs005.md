# VS-005 Research Observatory — local read-only HTTP and time contract (v1)

**Status: ACCEPTED CONTRACT FOR BOUNDED VS-005; NOT IMPLEMENTED.**
**Scope:** single-host local read-only observer over a **verified schema-v4** database, with an independently built **React + Vite + strict TypeScript** browser client. The [normative task](../tasks/VS-005.md) controls acceptance; this document defines v1 outward-facing GET contract and how its content must be interpreted.
**No new v4 schema**, study charter edits, worker, model, allocation policy, research graph edit, task/decision admission, approval or side effects.

## 1. Server launch, origin, schema, and source of truth

```sh
python -m arf.observer --db /path/to/existing-study.sqlite
# Binds a loopback port on 127.0.0.1 and reports its local URL.
# No worker starts, no schema migration, no controller lock, no remote bind.
```

**Initial runtime assumptions:** Python 3.11+ standard library server, SQLite read-only URI `mode=ro`, `PRAGMA query_only=ON`, short `BEGIN` consistent read snapshots for joined records, zero mutating SQL. Do not construct a `Store` that configures/writes the DB. Database is verified as a known v4 format (user_version=4 + required tables/columns) without running migrations or creating a new DB on missing path. WAL sidecars are compatible with observation, but do not use `immutable=1`. Limit requests and responses; all SQL values are parameterized, no user SQL.

**Origin:** bind `127.0.0.1` only. Reject unexpected `Host` even when DNS points at loopback (DNS rebinding); only same-origin browser requests are supported, no wildcard CORS. Only GET API, GET/HEAD bundled static assets. All other methods return 405 without side effects. Static file serving is an allowlisted build directory, no traversal, no arbitrary workspace file access. Built frontend makes no CDN or model calls and does not render DB-sourced HTML. Set restrictive CSP and suitable `X-Content-Type-Options` and cache headers; JSON may contain private study text but the API is local-only and never logs raw sensitive Context by default.

**Read semantics:** one study per current DB; `study_id` is sourced from stored charter. Existing keys and constraints keep their VS-001–004 meanings. UI never changes a stored value or infers scientific truth.

## 2. Shared JSON envelope and source semantics

All successful JSON responses carry:
```json
{
  "api_version": 1,
  "study_id": "stored-study-id",
  "temporal_scope": "current_execution",
  "data": {}
}
```
The `data` shape depends on endpoint. `temporal_scope` is:
- `current_execution`: the response's read transaction saw current mutable execution state.
- `recorded_history`: immutable saved fact/event, displayed with its record ID.
- `snapshot_at_decision`: original saved **context capture**, not an assertion of all database state at decision/publication time.

An endpoint may include multiple differently scoped sections: **each section then carries its own `temporal_scope`**. There is no global scalar "scientific progress." Unknown or unavailable values are `null`/explicitly typed markers, never invented zero, inferred validity or hidden omission.

For source-linked records, use:
```json
{"kind":"task","id":"B","revision":null,"source_table":"tasks","temporal_scope":"current_execution"}
```
Allowed UI kinds: `task`, `dispatch`, `run`, `evidence`, `decision`, `candidate`, `context`, `publication`, `assessment`, `graph`. Most joins can be represented as explicit typed refs without exposing raw SQLite row identifiers. Candidate identity must include **both** `candidate_id` and `version` when a version is displayed. Graph idea refs include `role`, `id`, `revision` as applicable. Never collapse graph semantic assertions with factual `ATTEMPT_OF`/`PRODUCES` relations.

Errors use a fixed envelope and an appropriate HTTP status:
```json
{"api_version":1,"error":{"code":"invalid_id","message":"Invalid bounded identifier"}}
```
- `400 invalid_query` or `invalid_id`: unexpected/duplicate parameters, invalid types/length/format or malformed cursor.
- `404 not_found`: exact stored record absent.
- `405 method_not_allowed`: non-read methods.
- `409 unsupported_schema` or `stale_session`: wrong DB version, replaced/restarted observer epoch, or incompatible saved client token.
- `413 limit`: query/response object exceeds allowed budget (no silent truncation of exact saved Context).
- `503 temporarily_unavailable`: SQLite busy/locked or transient source unavailable; client retains a visibly stale view.
- `500 corrupt_storage`: verified schema cannot safely read expected data; report generic error, not raw SQL/path/traceback to HTTP clients.

All responses set `Cache-Control: no-store` for the first version, except versioned hashed local static assets which may cache. GET paths and identifiers are bounded and validated before SQL. UI renders errors without claiming a new decision/run/study completion.

## 3. Five read-only resources

These are **v1 local observer endpoints**, not general public cross-network service APIs. Add routes only via separately reviewed versioned contract changes.

### GET /api/v1/meta

No query parameters. Returns at minimum:
```json
{
  "api_version":1,"study_id":"...","temporal_scope":"recorded_history",
  "data":{
    "question":"stored charter question",
    "charter_sha256":"stored source SHA-256",
    "schema_version":4,
    "observer_version":1,
    "epoch":"process-local opaque session identifier",
    "generation":0,
    "capabilities":["read_only","live_poll","decision_checkpoint"]
  }
}
```
Never expose absolute DB path, filesystem metadata or private auth tokens. Empty v4 candidate/decision ledger is a valid observable state.

### GET /api/v1/overview?limit=N&task_cursor=...&dispatch_cursor=...

`limit` defaults to 20, hard max 50, positive integer. Optional cursors are opaque and scoped to this observer epoch/source; they must not execute SQL or be interpreted as raw user-chosen ordering. The initial UI may fetch only the first page.

```json
{
  "api_version":1,"study_id":"...","temporal_scope":"current_execution",
  "data":{
    "task_counts":{"pending":0,"running":0,"succeeded":0,"failed":0,"needs_review":0},
    "tasks":[{"task_id":"B","title":"...","status":"succeeded","blockers":[],"created_at":"..."}],
    "task_next_cursor":null,
    "dispatches":[{"dispatch_id":"...","task_id":"B","status":"claimed","reason":"ranked_ready_task",
                   "decision_id":"...","run_id":"...","created_at":"..."}],
    "dispatch_next_cursor":null,
    "latest_decision_id":"...",
    "publication_head_id":"...",
    "observed_generation":0
  }
}
```

`task_counts` covers all saved tasks and uses actual task status, not a scientific completion claim. Task readiness is `status=pending` **and** no dependency blocker (not merely `pending`); surface blockers when available. Dispatch statuses/reasons come from stored immutable receipts; `claimed` means a task was claimed *then*, not that its current run necessarily succeeded. `latest_decision_id` is a saved decision reference or null and need not equal the decision linked from the current publication. The publication head is the saved linear head or null. Stable source-specific ordering and bounded keyset pagination are required, with deterministic ID tie-breaks; no bogus single global causal event ordering.

A task without any dispatch or an earlier v4 fixture with no publication is a valid condition. Do not replace `needs_decision` with `no_ready_task` or infer permanent study completion from an empty ready set.

### GET /api/v1/trace?kind=K&id=ID

Supported `K`: `task | dispatch | run | evidence | decision`. `id` is a nonempty bounded UTF-8 source ID (maximum **4,096 bytes**, no path interpretation). No loose title/substring lookup; exact record ID in the current study only. The same read transaction captures its coherent joins.

```json
{
  "api_version":1,"study_id":"...","temporal_scope":"current_execution",
  "data":{
    "focus":{"kind":"task","id":"B"},
    "links":[
      {"relation":"candidate_binding","source":{"kind":"task","id":"B"},
       "target":{"kind":"candidate","id":"...", "version":1},"source_record_id":"..."},
      {"relation":"decision_member","source":{"kind":"candidate","id":"...", "version":1},
       "target":{"kind":"decision","id":"..."},"source_record_id":"..."}
    ],
    "task":null,"dispatch":null,"run":null,"evidence":null,
    "candidate_versions":[],
    "decision":null,"members":[],
    "publication":null,"assessment":null,
    "graph_assertions":[],
    "missing_relations":[],
    "truncated":false,"continuation":null
  }
}
```

The example above is a **shape**, not a fictional assertion that the chosen DB has those links. Real `links` and all embedded objects must come from existing exact keys. The server can provide only the records relevant to the focus. A task with multiple dispatch attempts or several relevant decisions must **not silently choose an arbitrary one**; expose bounded selections with source IDs (or an explicit `truncated` continuation), letting the operator select the exact one. `candidate_versions` includes exact version; `members` is the original saved full decision membership including `priority_group=null`, `exclusion` and `ordinal`, not just winners. The stored decision's `impact` and synthetic estimates must not be promoted to scientific truth.

**Graph links:** include only recorded semantic link revisions and factual/run/Evidence edges whose exact source IDs justify them. Use `type`, `category`, `visibility`, `polarity`, attribution, revision and graph-sequence fields available in the v3 graph contract. No blanket graph expansion: initial neighborhood depth <=2, <=32 nodes and <=64 edges, with `truncated/continuation` or `missing_relations` explicit; if no motivation relation exists, return `not_recorded`. Do not invent Task→Hypothesis links simply because Evidence was generated by the task.

**Execution:** one Task can have multiple attempts; include all up to the bound or explicit continuation. A v4 dispatch can reference an unfinished/failed/interrupted run; label the **current** run status separately from the original `claimed` receipt. `Evidence` from a successful run is **unvalidated** unless the actual future schema says otherwise.

### GET /api/v1/checkpoint?id=DECISION_ID

Resolve exactly one saved `research_decisions.decision_id` and its linked **immutable** `decision_contexts` body. Do not call `capture_context` (which would write), rerank or infer current conditions.

```json
{
  "api_version":1,"study_id":"...","temporal_scope":"snapshot_at_decision",
  "data":{
    "decision_id":"...",
    "context_id":"...",
    "decision":{},
    "context":{},
    "capture_semantics":"saved_context_input_not_global_time_travel",
    "selection_complete":true,
    "portfolio_completeness":"partial",
    "historical_execution_state":"captured_execution_only"
  }
}
```

`context` is the exact persisted **original captured input** (including its saved execution snapshot, graph projection, feedback and profile), not reconstructed from today. A Context may have been captured before the associated Decision was created or published; the label **does not** imply the exact instant of execution/claim. `decision` includes **every saved decision member**, policy, source hash and abstention reason. Show as `snapshot_at_decision` with explicit selection/truncation and artificial-policy markers. Null/missing reasoning is not filled with model-generated explanatory text.

The client compares two independently fetched immutable checkpoints by candidate `(candidate_id,version)` and stable idea IDs/revisions. It distinguishes:
- membership arrival/departure, new version, order/rank/exclusion changes;
- changes in declared policy, decision assumptions, feedback, estimated vs observed cost;
- different selection `roles/edge_types/node/limits`, truncated selections, different graph sequence and original execution hash;
- `not_comparable` vs `changed`. **Different scopes do not prove a change in the research world.**

Only two checkpoint records are needed in the initial UI; no compare endpoint. If a selected comparison record is unavailable or 413, show error and keep the previously pinned checkpoint intact.

**Size:** the original saved Context is capped by v4 at about **2 MiB**; allow an explicit **3 MiB** complete checkpoint response ceiling. If even one exact record cannot fit, return `413 limit` with the decision ID in ordinary text (no partial context presented as complete). Other JSON endpoints: **256 KiB** hard response ceiling; enforce bounds before encoding and send an explicit `truncated` flag only when a continuation exists. `/meta` and `/changes` should be much smaller.

### GET /api/v1/changes?since=TOKEN

One observer process maintains `epoch` (random process/source identity) and monotonically increasing `generation` (number of observed changes, not global DB commits). A persistent observer-owned SQLite read-only connection tracks `PRAGMA data_version` **only relative to itself**. Never compare data_version values across unrelated connections, nor rely solely on graph sequence or main DB mtime.

```json
{
  "api_version":1,"study_id":"...","temporal_scope":"current_execution",
  "data":{
    "epoch":"opaque-process-source-epoch",
    "generation":4,
    "token":"opaque-versioned-epoch-generation-token",
    "changed":true,
    "reset_required":false,
    "observed_at":"server-UTC-timestamp"
  }
}
```

`changed` means the source **may contain new committed data** compared with the client's token, not that science progressed. Missing token produces an initial token with `reset_required=true`. If a token's epoch/source no longer matches (server restart or DB replacement), return `reset_required=true` and force a new meta/overview/selection recheck; do **not** silently transfer a pinned study selection to a different DB. Token parsing has a strict small limit (e.g., <=256 bytes) and no user-controlled SQL.

Every poll refreshes the persistent detector as needed; because the observer does not write, external commits increment the same connection's `data_version` as SQLite documents. A long-lived read transaction must **not** pin detector visibility. Check source path identity (where supported) before continuing to serve cached data on path replacement; reopen/reverify and roll epoch or report stale. An externally changed DB must not result in a no-change response forever.

## 4. Browser/TypeScript client contract

Frontend source `.ts/.tsx`, React components, strict TypeScript, Vite build. **Runtime JSON decoding** at the fetch boundary is mandatory: TypeScript type assertions alone do not validate server responses. Distinguish a malformed response, a valid `null`, a missing relationship, an incomplete page, a stale source and a scientific unknown. Reuse a small explicitly versioned discriminated union for reference kinds and temporal scopes; avoid untyped `any` in client data paths.

UI state:
```text
selected = { kind: "task" | "dispatch" | "run" | "evidence" | "decision", id: string } | null
mode     = { kind: "live" } | { kind: "pinned", decisionId: string }
compare  = { decisionId: string } | null
expanded = set of source-linked relation IDs
source   = { studyId, epoch, generation, stale: boolean }
```

- A new activity event updates the rail and only the visible live trace; it does **not** reset `selected`, `expanded` or Inspector scroll.
- A pinned checkpoint retains the **same immutable record** through every poll until explicit unpin/replace. Its comparison target is separately pinned; the UI can still display a small live-change counter or stale banner.
- Discard/abort outdated in-flight fetch results when selection, epoch, mode or fetch generation changes. Do not combine an old trace with a new study snapshot as if they were one atomic read.
- Show `recorded rationale`, `unknown/incomparable impact`, `synthetic proxy`, `unvalidated Evidence`, `current execution`, `snapshot_at_decision`, `not_recorded`, `truncated`, `stale` as neutral, text-accessible semantic labels. No fake progress percentages or automated scientific validation.
- All graph/decision/run explanation text is untrusted text for HTML-rendering purposes. Use React safe text rendering; do not use `dangerouslySetInnerHTML` for stored content.

## 5. Tests and compatibility

Contract tests must cover positive B → decision → B-run/Evidence → compare D, exact saved context bytes/semantics, null/missing/unranked/abstain, supported graph link attribution, separate-writer changes, v4 initial bootstrap and original offline decision-demo, old v1–v3 refusal without migration, broken tables, long IDs, hostile Origin/Host, methods and URL traversal, malformed JSON, SQLite failure, large outputs, out-of-order responses, persistent pinned selection and server restart/DB replacement. Test protected file/table identity before and after observation; failure must never call claim, `recover` or modify any worker/charter paths.

No synthetic policy reranking, new research interpretation or P2 scheduler change is permitted in an observer test. Test assertions about fixture impact must say **synthetic**. Verify TypeScript typecheck/build, Python tests and demos, and `git diff --check`; report actual results in `docs/current-state.md`.

## 6. Changes require review

Changing the five-route shape, mutability, network exposure, DB v4 meaning, human authority, time-travel claims, default frontend stack or execution policy is a **contract change**, not a local refactor. Bring such changes back for human review. Small source layout, component boundaries, exact NPM dependency versions, packaging, cursor codec and HTTP implementation details may be resolved by Codex as reversible choices with tests and documentation, provided the security/read-only/temporal behavior above remains intact.
