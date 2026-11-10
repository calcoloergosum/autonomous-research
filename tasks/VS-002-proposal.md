# VS-002 proposal — Planner proposals at the persistent task boundary

**Status:** Reviewed; architectural alternatives B / B / A / A selected by the human owner on 2026-11-10. Historical design proposal; approved implementation contract is `tasks/VS-002.md`.

**Precondition:** VS-001 is completed. Approved choices are recorded as ADR-012–015 in `docs/decisions.md`. Remaining implementation details are bounded by `tasks/VS-002.md`; the historical alternatives below are retained for traceability.

**Authority:** This document authorizes no research, provider calls, spending, schema migration, or code execution. Examples refer only to the existing integration fixture.

## Candidate goal

Demonstrate an offline planning boundary:

`stored study/task/evidence state -> versioned context -> planner proposal -> structured validation -> persistent task proposal -> explicit human authorization/import -> existing allowlisted executor`

Planning produces suggestions, not executable authority or observations. Persisting a valid proposal must leave the executable task queue unchanged. Importing an explicitly authorized task candidate creates an ordinary pending `TaskSpec`; executing it remains a separate `run-next` operation under all VS-001 checks. The candidate milestone ends with deterministic fixture tests of this path. It does not start an autonomous research loop.

The requirements below are proposed acceptance targets, conditional on human approval. They do not amend accepted decisions in `docs/decisions.md` or the normative VS-001 interfaces.

## In scope and planner authority

The planner may **read** only an explicitly exported snapshot from the selected single-study database: immutable charter bytes/hash and parsed question, criteria and constraints; task specifications, dependencies and statuses; recorded run outcomes/errors; evidence with provenance and validation status; and measured costs labeled as observations. No credentials, environment variables, arbitrary file paths, other studies, or conversation history enter context. Snapshot selection and limits belong to the trusted exporter, not the model.

The planner may **propose** one existing allowlisted demo task candidate, a non-executable subordinate question/hypothesis, or no action. A rationale may cite supplied evidence IDs, but must retain their `unvalidated` status. References establish provenance, not proof. Proposed task titles/descriptions and research notes are inert text.

The planner must **never change** the study question, success criteria, constraints, charter bytes/hash, permissions, context snapshot, observations, evidence validation labels, task/run history, dependencies of existing tasks, or recovery/retry decisions. It cannot approve itself, insert executable tasks, claim work, run tools, select programs, or relax limits. No API for charter revision is added. A subordinate question cannot replace or reinterpret the final question. Human review must reject semantic goal drift; schema validation alone cannot establish scientific relevance.

The trusted implementation, not a prompt, enforces this separation. The planner receives data and returns bytes. It has no database handle, writable store capability, tool access, shell, executor, or approval API. Context text, including task descriptions and errors, is untrusted data and cannot grant permissions. Existing direct operator task creation remains a trusted human-controlled path; the proposal interface does not pretend to protect against the filesystem/database owner.

## Minimal proposed data contract

One envelope contains one action; multi-action batches and dependencies on other unimported proposals are deferred. Field names and commands here are design candidates, not additions to `docs/interfaces.md`.

| Field | Proposed meaning |
| --- | --- |
| `proposal_version` | Integer `1`; reject unsupported versions and bool |
| `proposal_id` | Trusted controller-assigned stable ID for this request/result, never model-selected authority |
| `study_id` | Exact selected persisted study ID |
| `charter_sha256` | Exact imported charter source hash |
| `context_sha256` | Hash of the immutable context artifact used for generation |
| `rationale` | Bounded nonempty explanation; no execution semantics |
| `evidence_refs` | Unique list of evidence IDs present in this context and study; may be empty |
| `action` | Strict tagged union described below |

The provider supplies only `rationale`, `evidence_refs` and `action`. The controller constructs the envelope using the recorded request. It rejects extra provider fields, including attempted overrides of identity, context, permissions or approval status.

Proposed action variants:

1. `{"type":"task_candidate","task_spec":{...}}`: `task_spec` uses exactly the existing `TaskSpec` JSON fields, with current default rules normalized before hashing. Only `kind=demo_mean` and finite numeric input are eligible. Dependencies must already exist in the same study. Unknown fields, commands, code, module paths, URLs as execution targets, and other worker kinds fail. The candidate task ID must be unused or match the same previously imported proposal under the idempotency rules below. A valid spec inside a proposal is still not a task in the queue.
2. `{"type":"research_note","note_kind":"question","text":"..."}` (or `note_kind="hypothesis"`): bounded text persisted as an untested proposal, with no task ID, worker, input, task dependencies, or execution status. It cannot be imported into `tasks`. Turning it into an experiment requires a later separately authorized task candidate. Research notes cannot be used as evidence or executable prerequisites. A general hypothesis/claim graph is deferred.
3. `{"type":"no_action","reason":"..."}`: a bounded explanation that no permitted candidate is appropriate. Persist the planning response without creating a task or evidence. This is an expected planning outcome, not an execution failure.

For example, a fixture candidate's nested `task_spec` could have task ID `planner-demo-1`, study ID `demo-mean-study`, a title and description, `kind="demo_mean"`, `input={"values":[2,4,6,8]}` and `dependencies=[]`. Its envelope refers to an actual exported context and charter hash; placeholder hashes must fail validation. No scientific question is coerced into a mean calculation merely because that is the only worker.

Trusted provenance lives beside the immutable envelope: request ID, provider/mock identity and version, prompt template version/hash, context export version, policy version/hash, raw response bytes/hash, normalized proposal hash, validation decision and sanitized diagnostics. Record local timestamps as controller observations. Do not infer a model's internal state, actual costs, or scientific confidence from its rationale. Invalid raw outputs may be retained in a bounded diagnostics record; they never enter the executable queue.

## Validation, authorization and import

Proposed validation order:

1. Enforce local byte, string, list and nesting limits before expensive parsing; suggested starting limits are a 1 MiB context, 64 KiB response, 4 KiB per text field and 64 dependencies/references. Refuse oversized contexts explicitly rather than silently dropping state. These are planner limits, not changes to existing task input limits or a resource scheduler.
2. Strict JSON parsing: reject duplicate keys, missing/unknown fields, nonfinite numbers, bool-as-integer values, unsupported versions and malformed unions. Validate the trusted request/context binding and study/charter hashes. Validate evidence references against the exported snapshot.
3. For task candidates, reuse `TaskSpec.parse`, current dependency/cycle checks and the worker allowlist. At import, recheck against current stored state inside the selected persistence mechanism. No fallback from an unsupported action to a demo task.
4. Apply a trusted local policy permitting only fixture demonstration tasks in this milestone. Charter constraints are human prose, not a machine-readable grant: a model's claim that an action satisfies them is insufficient. A trusted operator reviews relevance and constraints and explicitly authorizes the exact candidate. No authority derives from proposal validity or evidence citations.
5. Bind an approval record to operator identity (locally asserted, not cryptographically authenticated), study/charter hash, proposal ID/content hash, context hash and local policy version/hash. Model-supplied approval fields are rejected. Edits require a new immutable proposal and approval; no in-place rewriting.
6. Import only an approved `task_candidate`. Recheck current permissions, charter hash, dependency existence, task collisions and context freshness before inserting one pending task. Import never invokes `run-next`, `retry` or `recover` and never changes an existing task/run/evidence record. A pending dependency may still block execution under existing semantics.

Suggested freshness rule: approval/import requires the current exported-state hash to match the proposal context. If tasks, runs or evidence changed, return a stale-context conflict and require a new snapshot/proposal/approval. After a successful import, repeated import uses the committed receipt before checking freshness; its own task insertion must not invalidate its idempotent replay. This conservative rule and its operator experience require approval (see alternatives).

### Identity and deduplication

- A stable request ID is assigned before mock/provider invocation. A completed request replays its stored response; restart never generates again just because the caller lost the reply.
- Define canonical JSON version 1 using UTF-8, sorted object keys, compact separators and no NaN/Infinity. Normalize `TaskSpec` defaults; treat dependencies and evidence references as sets with a documented sorted representation; preserve numeric value-list order. Hash canonical content with SHA-256 and store the canonicalization version. Retain raw bytes separately.
- The normalized proposal content hash includes study, charter/context hashes, rationale, references and action, excluding controller ID/timestamps. A repeated identical response under a new request links to the existing candidate and retains request provenance. Reuse of a proposal/request ID with different content is a conflict, never an overwrite.
- Independently detect a duplicate executable action using study plus normalized full `TaskSpec`, excluding mutable execution state. Different rationale/context does not authorize another copy of an identical task. A matching task ID belonging to unrelated/manual work is a collision requiring review, even if its fields happen to match. A different task ID is a distinct explicit candidate; detecting scientific equivalence across differently named tasks is deferred.
- Reimport of the same approved proposal returns the original task ID/receipt without another task, run, evidence row or timestamp rewrite. Approval and rejection are trusted audit events, not planner fields. An already imported proposal is terminal and cannot reset or retry its task.

## Context as a versioned artifact

Export through a consistent SQLite read transaction, with stable ordering and explicit export version. Preserve charter source bytes (for example base64 in JSON), source hash, parsed fields and evidence labels. Include relevant task/run/evidence IDs and observed costs with units and nulls intact. Exclude export time from the semantic state hash so an unchanged database produces the same hash; record export time separately. Persist the exact canonical snapshot bytes before generation, plus schema/exporter version, prompt template bytes/hash, policy version/hash and provider configuration without secrets.

The recommended initial context is the complete single-study demo state; oversized exports stop explicitly. Future bounded selection would require recording selection rules, included/omitted IDs and a completeness marker. No silent summary may replace charter criteria or evidence provenance. A stored context must be retrievable by hash after restart, enabling reproduction and validation without chat history. Hashes establish identity, not tamper resistance against the trusted filesystem owner.

## Optional provider seam; offline default

A minimal candidate internal protocol is `propose(request: PlannerRequest) -> PlannerResponse`. A request contains stable request ID, immutable context bytes/hash, versioned prompt and approved local response limits. A response contains raw structured-output bytes and provider metadata; usage is optional and unknown usage remains unknown. It has no execution or database capability. Provider invocation and local schema validation remain separate operations.

Required implementation would be a deterministic mock: fixed versioned fixture responses keyed by request/context hash, including task, note, no-action and invalid-response cases. Repeated identical requests return identical bytes. Mock usage is zero external calls, not fabricated live-model performance. Tests inject failures through this seam, never by executing generated code.

A live adapter is optional future work and is not necessary for VS-002 acceptance. Do not install an SDK, discover credentials, make network calls, or enable a provider by default. Any later live adapter needs separate approval of model/API, data disclosure, permission/cost enforcement and failure/retry policy. Unknown/incomplete planner requests remain explicitly unresolved; restart must not automatically repeat a potentially billable call. Planner request recovery is separate from VS-001 run recovery and never changes its interrupted/needs_review behavior.

## Alternatives requiring human selection

These choices affect persistent meaning or public interfaces. Recommendations are provisional; implementation must wait for selection and a reviewed contract.

| Choice | Option A | Option B | Proposed preference / trade-off |
| --- | --- | --- | --- |
| Proposal/context/approval persistence | Versioned local immutable JSON artifacts plus append-only receipts; keep execution DB at schema 1. Write an approved intent before calling existing task creation, with stable task ID and full spec hash. On restart, reconcile an unfinished intent against that exact task before completing its receipt; any mismatch or missing provenance stops for review. Single-controller coordination covers importer and task creation. | Add separate request/context/proposal/decision/import records in a reviewed schema 2 migration. Keep current task/run/evidence semantics; commit task creation and its import link/receipt in one SQLite transaction. | B gives stronger atomic provenance and simpler restart. A avoids migration but has a cross-file/DB commit gap, more reconciliation, backup coordination and explicit uncertain-state handling. Neither may infer authorization from a coincidentally matching task. |
| Public entry points | Library service functions first, with a documented offline Python fixture harness; existing CLI remains unchanged. Human review supplies a trusted approval object through that harness. | Add separate CLI verbs for export, mock planning, proposal inspection, explicit approval/rejection and import. Exact syntax, JSON outputs and errors require a normative interface review; old verbs retain their meaning. | A is smaller; B provides a usable operator boundary and auditable separate steps. Prefer B if a CLI workflow is expected; do not invent the commands during implementation. Both need a way to inspect the exact candidate before approval. |
| Fresh context at approval/import | Require unchanged semantic state hash; a stale proposal needs regeneration and fresh approval. | Allow stale contexts with explicit operator reapproval against a newly recorded snapshot and current permission/dependency revalidation, retaining original context provenance. | A is simpler and conservative for the demo; B avoids wasted plans but introduces additional approval events and stale-state semantics. Prefer A initially. |
| Research ideas outside executable kinds | Retain the tagged `research_note` variant above, never in the task queue. | Explicitly defer persistent research notes: support task/no-action only, and return a no-action explanation when a question/hypothesis is not executable. | A prevents pressure to force ideas into `demo_mean`, at the cost of another persistent proposal variant. B is smaller but postpones a useful research-planning representation. Prefer A; neither adds worker kinds or evidence. |

For either storage option, publish the persistence format, uniqueness rules, concurrency strategy and restart matrix before coding. Option B requires migration tests from schema 1 that preserve every existing charter byte, task, run and evidence row, and reject unknown versions without writes. Option A requires interruption tests at each artifact/task/receipt boundary. Neither choice permits automatic execution or retry. No new `proposed` status is inserted into the existing executable task state machine.

## Proposed acceptance criteria and tests

1. An offline fixture exports a reproducible stored context, invokes the deterministic mock, validates and persists a candidate. Before explicit approval/import, the task queue, runs and evidence are unchanged. After import there is exactly one pending allowlisted task. Only a separate operator `run-next` executes it and produces one **unvalidated** observation.
2. Missing/extra fields, duplicate JSON keys, unsupported versions/kinds, wrong study/charter/context hashes, invalid references, nonfinite inputs, malformed action unions and oversized/deep responses fail without executable writes. Malformed responses remain diagnostics, not successful plans or evidence.
3. Charter question/criteria/constraints/source remain byte-for-byte unchanged after valid, invalid and adversarial proposals. Attempts to write charter/evidence/approval fields, prompt instructions in stored descriptions and attempts to treat research notes as executable tasks cannot cross the boundary.
4. Missing dependencies, self-dependencies, cycles and cross-study references fail; dependencies on unimported proposals are refused. Existing pending/failed prerequisite behavior stays unchanged. Policy denial, absent/forged approval, changed policy, changed candidate content and stale context prevent import.
5. Duplicate requests/proposals and repeated approvals/imports preserve original records and yield at most one linked task. Conflicting IDs never overwrite history. Altered rationale does not evade duplicate-action checks. A colliding unrelated task ID does not become an imported proposal. Reimport remains idempotent after the task succeeds or fails and does not retry it.
6. Restart tests reopen durable state after context persistence, response persistence, proposal validation, approval and task import. Interrupted imports satisfy the selected atomic/reconciliation contract. Concurrent imports cannot create duplicate tasks. Unknown outcomes stop for review; no automatic model recall or experiment rerun occurs.
7. Research notes and no-action responses persist without tasks/runs/evidence; notes remain hypotheses/questions, never validated claims. Unsupported research actions produce a note/no-action or a rejection, never an invented demo experiment.
8. Arbitrary commands, code, modules, URLs as execution targets, tools and unsupported worker kinds are refused. Text is never evaluated, imported or interpolated into a shell. Tests use the deterministic mock and fixed worker, deny network access at the provider seam, and assert zero live provider calls. No orchestration framework is required.
9. Run the complete VS-001 suite, including numerical-result checks, interruption/retry, evidence non-duplication and charter SQL guards. Exercise the chosen offline operator workflow across separate processes if a CLI is approved. Record actual commands/results and limitations in current-state; no claim of scientific progress follows from these plumbing tests.

## Out of scope

Resource scheduling and budgets beyond local planner input/output bounds; impact/cost prediction; adaptive exploration/exploitation; baseline revision; portfolio optimization; general generated-code execution or sandbox design; live research execution; real-study planning runs; live provider/API calls; credentials, spending and network enablement; new experiment workers; automatic approval/import/run loops; autonomous retry/recovery; evidence promotion; distributed operation; dashboards; full hypothesis/claim graphs and scientific-equivalence deduplication.

## Decisions required before implementation

- Approve or revise this candidate milestone and its offline fixture-only boundary; no actual study question is supplied by this proposal.
- Select proposal persistence and migration/reconciliation semantics, including atomic import/provenance and restart tests.
- Select the public entry points and review their exact request/response/error contracts before implementation.
- Approve the action union, canonicalization/deduplication rules, local size bounds, strict freshness policy and exact human approval binding. Choose whether non-executable research notes are included or explicitly deferred.
- Confirm locally trusted operator authorization is sufficient for this demonstration. Stronger identity/authentication is a separate design, not authority that a model can supply.

Human ownership of the study charter, unvalidated evidence labels, the existing worker allowlist and explicit run recovery/retry are invariants, not options being reopened. Once the choices are approved, a separate approved task specification should record them; this proposal alone must not trigger implementation.
