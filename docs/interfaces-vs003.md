# VS-003 internal research graph contracts

This additive, internal interface implements only G1–G10 and ADR-016–023.
There are no new public CLI verbs. `arf.graph.GraphService` accepts an existing
`Store`; `arf.graph_store.migrate(store)` explicitly upgrades known schema v2
(or verifies v3 and returns `already_current`). V1 must first use `plan migrate`.
All old execution/planning operations remain available; `plan migrate` on v3
verifies v3 and preserves the existing response `schema_version: 2` (the
planning compatibility version), without downgrading the actual database.

## Typed requests, authority and results

`Actor(name, role, source)` is a trusted local caller assertion, not authenticated
identity. Roles are `recorder` and `operator`; only operator may create human
ideas or baselines and record baseline transitions. Neither role grants execution,
approval, review or evidence-validation rights. Planner text cannot construct a
capability through a graph request. All mutations take `operation_id` and `actor`.
Identical operation ID + normalized request + actor replays the original receipt;
conflicting reuse raises `GraphError(code='conflict')`. Replays precede head checks.
A receipt contains operation ID, study ID, graph sequence, commit timestamp,
actor/source and a `result` object containing the created IDs. Sequences start at
1 and are allocated under BEGIN IMMEDIATE; failed/replayed operations consume none.

`Ref(role, id, revision=None)` uses O/Q/H/C/T/R/E/B. Q/H/C **require** an exact
revision ID belonging to that identity. Other roles forbid revision pins; their
content is immutable except current task/run status. O is always the stored
study ID; the imported charter is its only body. All references resolve in this
study. There are no graph-created tasks, attempts, observations or objectives.

Operations (keyword arguments, internal signatures may evolve):

- `register_note(proposal_id)`: validate the persisted VS-002 proposal, context,
  hash and successful request linkage. Only research_note creates one Q/H identity,
  initial revision and registration. Record exact source proposal/hash/context,
  proposal author/provider/request attribution, text and registration time. Replay uses the original operation ID; a second registration operation for
  that proposal conflicts, so new operation IDs are never silently left unbound. No freshness/approval is invented.
- `create_human_idea(kind, text, assumptions='', scope='')`: operator Q/H only.
- `create_claim(text, assumptions, scope, premises, joint=True)`: recorder or
  operator creates an unreviewed C. Require 2–64 distinct pinned E/C premises for
  joint synthesis. Create DERIVED_FROM lineage links atomically, not independent
  experimental observations. No truth/validation field is accepted.
- `revise_idea(idea_id, expected_head, text, assumptions, scope, premises=(),
  joint=False)`: append revision, preserving kind and source attribution. C retains
  the joint-premise requirement; Q/H reject premise metadata. New claim revision
  gets its own lineage. Old references keep pointing at old revisions.
- `add_semantic_link(type, source, target, rationale, assumptions='', scope='',
  polarity=None, timing='retrospective', proposal_id=None)`: closed vocabulary
  and endpoint table in VS-003 task. ASSESSES requires polarity, assumptions,
  scope and rationale; other types forbid polarity. Reject self-links (even with
  different revisions), dangling/cross-study references and factual edge types.
  New links have `visibility='unreviewed'`.
- `revise_or_withdraw_link(link_id, expected_head, rationale, assumptions='',
  scope='', polarity=None, target=None, withdraw=False)`: append correction or
  withdrawal attributed to the caller; source and type stay fixed. Target may be
  replaced with another valid pinned revision; no assessment/review is inherited.
  Withdrawals retain endpoints/content and record a new correction rationale.
- `create_baseline(scope, method, configuration, references=())`: immutable
  operator snapshot with bounded textual configuration and exact references.
- `record_baseline_transition(scope, new_baseline, expected_prior, rationale,
  motivations, affected=())`: operator only; first activation expects None.
  New/old baselines must match scope, motivations are exact E/C references,
  affected is up to 64 `(Ref(T/Q/H/C), disposition)` pairs with disposition
  retain/redirect_proposed/pause_direction. CAS against last scoped transition;
  reversion uses a new operation, without touching the execution queue.

Errors use `GraphError` (`invalid`, `not_found`, `conflict`, `unauthorized`,
`schema`, `limit`); SQLite failures propagate and roll back the logical operation.
All text/IDs/actor fields are valid UTF-8, at most 4 KiB; request JSON is at most
64 KiB; reference/affected lists have at most 64 entries. Content is inert data.
DERIVED_FROM insertion checks the directed **revision** lineage for cycles using
indexed, bounded reachability; exhaustion refuses the write with `limit`.
Other semantic cycles are allowed. No automatic assessment propagation exists.

Creation-context timing is conservative: `retrospective` (default) or `unknown`
may be asserted. `creation_context` is accepted only for MOTIVATED_BY with source
registered note or imported task, its exact originating proposal, a valid request,
and target E explicitly included in that original envelope's evidence_refs and
captured execution context. A late registration is never creation provenance
for another idea revision. Proposal evidence_refs never create links implicitly.

## Minimal schema v3

DDL is maintained as `GRAPH_SCHEMA` in `arf/graph_store.py`. Tables:

| Table | Key and immutable contents |
| --- | --- |
| graph_operations | (study_id, seq), unique operation_id, kind, actor/source, canonical request/result bytes, committed_at |
| graph_ideas | idea_id, study, immutable kind Q/H/C, origin JSON, creation seq |
| graph_idea_revisions | revision_id, idea_id, previous revision, text/assumptions/scope, joint/pinned premises JSON, seq |
| graph_links | link_id, study, immutable type, creation seq |
| graph_link_revisions | revision_id, link_id, previous revision, typed pinned endpoints JSON, rationale/assumptions/scope/polarity, timing/proposal, visibility, seq |
| graph_registrations | unique (study_id, proposal_id), idea/revision ID, source proposal/hash/context/request/provider attribution, seq |
| graph_baselines | baseline_id, study/scope, method/configuration/references JSON, seq |
| graph_transitions | transition_id, study/scope, old/new baseline, reason/motivations/affected JSON, seq |

Every table has foreign keys and update/delete guards. Sequence references are
transactionally deferred so child writes and the final immutable receipt commit
together. Indexes cover per-identity revision heads, sequence reads, scoped
transitions and typed source/target endpoint lookup. Typed reference validation
lives in the service; host/DB owners remain trusted. Migration verifies the whole
known schema, checks foreign keys, applies DDL and user_version transactionally.
No legacy table or existing row is rewritten. No generic event engine is added.

## Bounded reads and historical meaning

`QueryLimits(depth=8, nodes=128, edges=256, output_bytes=262144)` has hard maxima
32/1024/2048/1048576; values must be positive (depth may be zero; output_bytes is at least 1024). `read_graph`
accepts optional `at_seq`, `node: Ref`, `edge_id`, `roles` and `edge_types` filters. Read-only
idea lookups may omit a revision to resolve the head at the requested sequence;
writes still require pins. Opaque semantic/transition IDs and reversible factual
IDs support direct lookup (derived factual IDs may be up to 16 KiB).
It returns a bounded page of nodes/edges, current active baseline per scope,
`graph_seq`, `execution_state='current'`, `truncated`, and `frontier` (typed refs
or continuation markers). SQL candidates are paged; no full snapshot is required.
`ancestry(task_id)` traverses outgoing recorded intention/motivation/lineage and
factual prerequisite/source links; `affected_by(evidence_id)` traverses incoming
assertions plus outgoing assessments. Both use visited sets and explicit bounds.
`as_of(seq, ...)` reads graph revision heads/active scopes through that sequence;
`history=True` also includes replaced/withdrawn revisions, their operation actor,
source and timestamp. Withdrawn heads are omitted from active links. No read
infers truth, scientific causation or independent experimental counts.

O resolves charter bytes via source_base64/hash, never a graph copy. T/R/E use
original IDs/bodies. DEPENDS_ON, ATTEMPT_OF and successful PRODUCES are read-only
SQL projections. SUPERSEDES is derived solely from committed transitions.
Legacy execution bodies and factual edges reflect **current** stored execution,
including in as-of views; prior legacy status is unknown, not reconstructed.
Graph-only writes are excluded from VS-002 export v1, identity, freshness and
all approval/import behavior. Baseline snapshots/transitions do not change work.

## Offline demonstration

`python -m arf.graph_demo --db NEW_PATH` is a fixture harness, not a public
operator graph CLI. It requires a fresh path and uses only the existing audited
worker and synthetic demo charter. It prints actual run/evidence IDs, graph
receipts, history/bounds checks and preservation results. Restart inspection:
`python -m arf.graph_demo --inspect --db PATH`. Tests deny network use and cover
G1–G10, populated migration, rollback, conflicts, bounded cycles and old behavior.
