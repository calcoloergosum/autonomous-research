# VS-004 technical review — Decision loop and ranked dispatch

**Status: Review recommendations only; not approved for implementation.**
Prepared 2026-11-10 against `main` commit
`12af093a7feabc3c49613cf38d6f4935eba72b23` and the latest
[proposal](VS-004-proposal.md). The companion [implementation draft](VS-004.md)
is conditional on human approval. Neither document adds an accepted ADR.

The owner has decided that recommendation order determines priority on the new
VS-004 execution path. That direction is settled. The interface, persistence,
freshness, activation and fallback choices below are recommendations, not
accepted decisions. This assignment authorizes only these two documents.

## 1. Architecture assessment

The proposal fits the repository if the decision loop remains a producer of
immutable data and the controller remains the sole execution authority. The
smallest useful slice is an explicit round: capture state, supply candidates,
estimate, rank, save, activate, dispatch one admitted task, then capture new
feedback. A saved recommendation must never start a worker.

| Responsibility | Minimal implementation recommendation | Capability boundary |
| --- | --- | --- |
| Research Context Builder | One trusted snapshot function with a selected graph view, complete execution snapshot and completeness manifest | Reads research state; writes only its decision snapshot |
| Candidate Manager | Versioned records and a deterministic candidate source function | Supplies possible actions; cannot add executable tasks or bind them by free text |
| Impact / Cost Predictor | Pure, versioned function over captured inputs and candidate versions | Produces predictions with units, assumptions and unknowns; cannot write Evidence |
| Allocation Policy | Replaceable pure function over estimates, context qualifications and explicit constraints | Produces ranks, exclusions and abstention; receives no Store or executor |
| Decision Ledger | Small trusted service with immutable records and request replay | Validates references and saves complete inputs/results; cannot activate itself |
| Recommendation-Guided Scheduler | Separate controller operation and narrow transaction-owned ranked claim | Checks active selection, freshness, admission and readiness; invokes only the existing lifecycle |

These are responsibilities, not six required class hierarchies. A few typed
records, pure functions and a ledger/dispatch service suffice. Reuse the existing
Store, canonical encoding, task validation, POSIX controller lock and worker.
Avoid an orchestration framework, generic event bus, provider registry, abstract
resource market or independently mutable ranking cache.

The necessary additions are a verified candidate-to-task binding, an exact
freshness contract, a transaction-owned graph read seam, and an immutable
dispatch receipt. A ranking without these cannot safely become execution order.

## 2. Findings from the actual implementation

References below describe the reviewed commit, not hypothetical VS-004 code.

| Finding | Actual implementation | Consequence |
| --- | --- | --- |
| FIFO is localized | [store.py](../arf/store.py), `claim_next` lines 266–291: pending tasks with no nonsucceeded prerequisite, `ORDER BY t.sequence LIMIT 1` | Change selection inside this transaction; do not sort a CLI list and claim later |
| Claims serialize | `Store.transaction`, lines 156–164, uses `BEGIN IMMEDIATE`; claim rejects any running attempt | Read ranking and eligibility under the same write transaction |
| Capacity is one run globally | `store.py`, lines 74–75, has per-task and global partial unique indexes for running attempts | Preserve both indexes and the preclaim check; no parallelism feature is needed |
| Lifecycle already has the right boundary | [service.py](../arf/service.py), `run_next` lines 33–67, locks across claim, execution and finalization; worker runs after claim commit | Share the execution/finalization body with ranked dispatch; do not create a second executor |
| Admission has two existing paths | `Store.add_task` / `_add_task_in_transaction`; [authorization.py](../arf/authorization.py), `import_proposal` lines 46–70 | A manually registered task is admitted under the existing trusted VS-001 contract. Requiring a VS-002 approval for every task would change semantics |
| Unimported approval is insufficient | `import_proposal` checks exact approval, current policy and freshness, parses TaskSpec, then inserts task plus receipt atomically | Ranking may reference only a stored task. An approved but unimported proposal cannot dispatch |
| Specs and observations are protected | `store.py`, immutable spec/dependency triggers and `finish_run` lines 293–329; completed runs/evidence cannot be rewritten | Store advisory artifacts separately. Dispatch receipts must link original task/run IDs |
| Worker restrictions are checked twice | `service.py` lines 45–57 rechecks stored kind/input and result; [executor.py](../arf/executor.py) runs packaged `worker.py` with isolated Python | Retain these checks even after preclaim TaskSpec validation |
| Recovery is explicit | `service.recover` uses the same controller lock; `Store.recover` marks interrupted/needs_review; `retry` is separate | Replaying dispatch must never resume, retry or reexecute a committed claim |
| VS-002 freshness is execution-only | [plan_store.py](../arf/plan_store.py), `context_bytes` lines 150–169, requires an existing transaction and excludes planning/graph records | Reuse the canonical execution bytes as a component; do not extend legacy export-v1 |
| Graph reads cannot currently join a transaction | [graph_query.py](../arf/graph_query.py), `snapshot` lines 18–27, rejects an existing transaction; `read_graph`/`traverse` own their reads | Calling public graph read and execution export successively is not a joint snapshot. A small internal transaction-owned graph read is needed |
| Graph sequence is not execution history | [graph.py](../arf/graph.py), read wrappers; graph query labels T/R/E bodies current and historical execution unknown | Capture execution bytes; graph sequence alone cannot prove which tasks were ready |
| v4 is currently rejected | `Store.__init__` accepts 1/2/3, `PlanStore` accepts 2/3, `GraphService` requires 3 | Adding v4 tables alone breaks every service. Version acceptance and schema verification need coordinated changes |
| Migration verifies exact known schemas | [graph_store.py](../arf/graph_store.py), `verify`/`migrate`; planning migration delegates v3 verification | Update migration compatibility without relaxing verification to arbitrary extra tables |
| Resource controls are narrow | Five-second subprocess timeout, 4096-character captured-output checks, one active run and fixed worker; CPU cost may be null | There is no general cumulative budget, CPU/memory quota, GPU reservation or human-capacity enforcement to inherit |

The executor's timeout is not a hard total-controller wall-time quota, and output
checking after capture is not a general memory sandbox. This review recommends
preserving these limits, not claiming stronger containment. A scheduler cannot
turn estimated cost into an enforced real budget.

## 3. Recommended minimal scheduling integration

### Interface and compatibility

Recommend a separate internal `dispatch_next` operation on explicitly migrated
v4 databases. Keep the original `run-next` and `Store.claim_next` FIFO behavior
on v1–v3. On v4, recommend that these legacy FIFO entry points refuse before
claiming with `ranked_dispatch_required`. This prevents an accidental unranked
route around the new scheduling preference. That v4 behavior requires approval;
it is not an existing contract. A general Research Manager CLI is unnecessary;
an offline harness can exercise internal capture/decision/activation/dispatch.

Future implementation should extract only a small private, transaction-owned
claim helper for ordinary pending→running plus run insertion, and the shared
claim→execute→finalize body. Keep the legacy selection query unchanged on older
schemas. The ranked service supplies a verified ordered intersection, never an
arbitrary task ID received from policy text. Do not call `claim_next` inside a
new transaction: it already opens one and would choose FIFO.

### Exact ordering and readiness

A policy emits integer priority groups, lower first, for explicit candidate
versions. Resolve equal groups by controller-owned candidate ID in UTF-8 byte
order, then version number. Persist the resulting total ordinal order; SQLite
row order, timestamps and mutable estimator scores are not tie-breakers. For
this first slice, reject two mapped candidates for the same task in one decision
instead of silently combining their priorities.

The dispatcher considers only ranked candidates with controller-verified task
bindings. Unmapped scientific suggestions remain inspectable and nondispatchable.
For mapped entries, validate exact study/task/spec/admission identity, require
pending status, and apply the existing dependency predicate. Skip a blocked
ranked task; record its blocker IDs/statuses. All tasks stay subject to the fixed
worker and single-active-run controls. A completed/failed/needs_review task is
never retried by ranking.

### Freshness and one-claim activation

Recommend the conservative pair `(graph_seq, execution_sha256)`, together with
study/charter, context version and trusted dispatch-profile hash. The execution
hash is SHA-256 of unchanged export-v1 canonical bytes. Capture both components
in one consistent read. Any execution-state change or graph operation makes a
decision stale for a new activation or claim, even if unrelated to its selected
subgraph. Ledger-only writes do not change this token.

An activation selects one immutable decision and is valid for **at most one
committed claim**. A claim consumes it through a unique dispatch receipt; no
mutable consumed flag is required. After execution, obtain a new snapshot,
decision and activation for the next claim. Replaying the old activation request
only returns history; it does not make the old decision fresh again.

This deliberately sacrifices batch liveness to avoid inventing rules for which
status/evidence changes may safely retain a multi-task ranking. It still proves
priority opposite to FIFO, skips blocked higher-ranked tasks, and demonstrates
successive ranked executions across new rounds. It does **not** promise draining
an entire saved ranking without re-evaluation. Approval must explicitly accept
this limitation or choose a more complex validity contract.

### Atomic dispatch procedure

1. Acquire the existing persistent `.controller.lock`; do not introduce a second
   independent executor lock. Lock contention remains a nonexecuting busy error.
2. Enter `BEGIN IMMEDIATE`. Validate the bounded request and look up its receipt.
   Identical request/actor replay returns the committed receipt before current
   freshness/selection checks; a changed request under that ID conflicts.
3. For a new request, refuse if any run is running, including an uncertain old
   attempt. No new activation or ranking can make it safe to ignore recovery.
4. Read the active selection head, require the supplied activation ID to match,
   check it is unconsumed, and validate all stored hashes and typed bindings.
   Compare the current freshness pair and trusted profile inside this transaction.
5. If usable, intersect the stored total order with existing admitted, pending,
   dependency-ready tasks. Check the supported execution profile. Rank selects
   priority; it does not supply admission, worker configuration or capacity.
6. Update the chosen task to running and insert its ordinary running attempt and
   immutable dispatch receipt in the **same transaction**. The receipt binds the
   exact activation/decision, task/spec/run, preclaim freshness, scheduler version,
   skipped entries and observed eligibility. No claim may commit without its audit.
7. Commit; execute via the existing fixed worker and finalization body while
   retaining the controller lock. Never call the estimator/policy in this path.

If there is no claim, record a nonexecuting receipt for a valid dispatch request.
Use the outcome table in the draft. Malformed requests, schema failures, lock
contention and transaction failures raise errors without inventing a receipt.
Replay of a committed claim returns its receipt and current linked run for
inspection; even a running/interrupted run is never executed by replay.

### Races and crashes

SQLite writers serialize activation, graph writes, admission and task claims. A
concurrent graph/execution writer either commits before the freshness check and
causes refusal, or commits after claim; later changes affect the next decision,
not the already claimed experiment. Atomic selection-to-claim is the boundary,
not a lock on research state throughout the worker's life.

Two controllers contend on the same lock; lower-level racing claims also obey
the write transaction and unique active-run indexes. A failed dispatch-receipt
insert rolls back task/run insertion. A crash after committed claim preserves
receipt plus running attempt. Existing explicit recovery marks interrupted and
needs_review; explicit retry requires a new decision and activation. Exactly-once
physical execution, power-loss guarantees and orphan-child supervision remain
outside the existing reliability model.

## 4. Recommendations for V4-1 through V4-13

All selections in this table await approval except the owner's already stated
direction that recommendations determine new-path execution priority.

| ID | Recommendation and rationale | Alternative / compatibility implications |
| --- | --- | --- |
| V4-1 | One complete offline round plus real ranked claim and fixed-worker execution | Advisory-only omits the requested execution ordering; unattended autonomy broadens scope |
| V4-2 | New versioned advisory identities with exact graph/proposal origins and optional verified stored-task bindings | Reusing proposal IDs confuses approval with valuation; requiring graph nodes creates unnecessary graph writes |
| V4-3 | Separate contribution, information value, uncertainty and resource vector; preserve unknowns and units | Scalar reward loses resource semantics; full distributions are unnecessary for this deterministic fixture |
| V4-4 | Static baseline and one deterministic information-aware function with explicit synthetic utility | UCB/Thompson/VOI need additional reward/posterior assumptions; no universal winner is selected |
| V4-5 | Separate immutable context containing selected graph and exact execution component | Ephemeral inputs complicate replay; modifying plan export would change authorization hashes |
| V4-6 | Explicit additive SQLite v4; six substantive tables, embedded estimate/configuration payloads | Sidecars complicate atomic claim/audit; stateless tests cannot preserve decision/dispatch history |
| V4-7 | Explicit new round; a versioned fixture estimator actually recalculates estimates from revealed feedback | No live retraining, inferred real impact reward, event subscription or automatic provider recall |
| V4-8 | Trusted ledger and scheduling adapter around pure estimation/ranking | Manager receives no Store, approval, import, baseline-transition or executor capability |
| V4-9 | Declare global portfolio partiality; allow complete selected views, exclude candidates missing required inputs/costs; truncation causes abstention in v1 | Failing every intentionally selected view is unusable; ignoring truncation/unknowns overstates knowledge |
| V4-10 | Multi-round deterministic fixture, adverse cases, replay and real-worker plumbing, plus all legacy regressions | Synthetic improvement cannot establish calibrated predictions or effective real research allocation |
| V4-11 | Separate internal v4 dispatch; v1–v3 keep FIFO; v4 legacy FIFO entry points refuse | Automatic v4 `run-next` ranking hides schema-dependent behavior; a mode flag adds mixed-mode semantics; leaving FIFO on v4 is an explicit bypass option |
| V4-12 | Strict non-execution for absent/stale/abstaining/consumed preferences; skip blocked entries; never use a FIFO tail | FIFO fallback improves liveness but admits unranked selections and requires extra provenance; strict mode has no fairness/starvation guarantee |
| V4-13 | Trusted local operator selects/clears an immutable decision using expected prior activation; one claim per activation | Automatic manager activation combines proposing and sequencing authority; standing delegation and multi-claim validity require separate approval |

### V4-11 interface comparison

| Option | Strength | Cost / recommendation |
| --- | --- | --- |
| Change `run-next` to rank automatically on v4 | Familiar invocation | Behavior and readiness results depend on schema; an implicit selection source is harder to review. Do not choose for this slice |
| Add explicit ranked mode to `run-next` | Reuses CLI command | Must define flag combinations, defaults, activation IDs and whether FIFO is an override. Viable later if a public CLI is wanted |
| Separate dispatch operation | Distinct request ID, activation and replay contract; leaves old CLI intact on v1–v3 | Recommend internal service now, harness for demonstration, public verb deferred. Refuse legacy FIFO on v4 unless an override is separately approved |

### V4-12 safety, liveness and reproducibility

Strict mode may stall when all ranked tasks are blocked while an unranked
prerequisite is ready. It may also starve an always-low-ranked direction. The
first slice reports these conditions and requires an explicit new round; it
adds no aging, automatic prerequisite promotion or fairness promise. Useful
counterexample: rank child C alone while ready prerequisite P is unranked;
dispatch must not invent P's priority. The operator can request a new decision
including P through the ordinary workflow.

Explicit FIFO fallback does not inherently weaken admission, but it weakens the
statement that recommendation order determines priority and can conceal missing
context or failed activation. A reproducible hybrid would need a frozen ranked
prefix, precise FIFO tail and recorded fallback reason/eligible set. It is a
valid alternative only if approved; it is excluded from the draft. Neither mode
solves fairness in an open-ended portfolio.

### V4-13 activation authority

Use a separate trusted caller capability with locally asserted actor/source,
following existing operator trust conventions without claiming authentication.
An expected-head check serializes competing selections. Exact activation replay
returns history before freshness but never reinstalls an old selection.
Activating a decision changes priority only; it creates no task approval,
authorization token or baseline transition. Saving a new recommendation neither
activates it nor automatically supersedes the selected one.

## 5. Proposed persistent data model

This is a logical model, not approved DDL. Each artifact has a payload version,
study/charter binding, canonical bytes/hash and controller timestamp. References
must resolve in the same study. Six substantive tables are sufficient:

| Table | Minimum durable contents and constraints |
| --- | --- |
| `decision_contexts` | Content-addressed context ID; graph sequence/query/view and manifest; exact execution bytes/hash; captured profile; capture timestamp outside content identity |
| `decision_candidates` | `(study_id, candidate_id, version)`; immutable origin, previous version, description, intended result, pinned targets/refs; optional task ID/spec hash and verified admission provenance; actor/request attribution |
| `decision_decisions` | Decision/request ID and normalized request hash; context FK; estimator/policy names, versions, exact config and code-version identifiers; constraints; candidate-set hash; ranked/abstain result and reasons; actor/time; prior-decision link |
| `decision_members` | Decision FK plus candidate-version FK; exact estimate payload and input/feedback refs; disposition/reasons; nullable priority group and total ordinal; optional verified task binding copied from that version |
| `decision_selections` | Study-local sequence and operation ID; expected predecessor; selected decision FK or clear; activating operator/source, freshness token and receipt/time |
| `decision_dispatches` | Request ID/full request binding; selection/decision refs where present; immutable claimed/nonexecuting outcome; chosen task/spec/run refs when claimed; scheduler/profile version; effective freshness, skipped entries and bounded eligibility audit |

Do not create separate estimator/configuration/estimate tables until independently
needed. Estimate payloads in `decision_members` retain their context, method,
units, uncertainty, unknowns and observations used; a new round inserts new
members. Synthetic revealed feedback can be embedded in the context as a
versioned fixture payload with source and digest, not a new Evidence row.
In addition to these six substantive tables, use a small candidate-registration
request-receipt table for exact batch replay, including requests that insert no
new candidate versions. This is narrow idempotency storage, not a generic event
log. Other operation receipts can be stored in their corresponding tables.

An explicit fixture feedback payload is input to estimation only. The dispatcher
does not interpret synthetic reward, privately held oracle data or prediction
scores. Dispatch freshness checks actual DB state and the trusted execution
profile; the exact decision input/configuration hashes remain immutable.

Use composite FKs for decision/member/candidate and study/task references. Bind
claimed task/run with the existing `(study_id, task_id, run_id)` key; constrain
claimed rows to nonnull task/run and nonexecuting rows to null task/run. Require
unique claimed run ID and a partial unique claimed activation ID. Validate typed
polymorphic graph references in the service, as VS-003 does. Guard all new tables
against update/delete. Latest selection is a projection of the append-only
selection sequence; consumed status is a projection of dispatch receipts.

Exact context replay deduplicates identical bytes. Candidate identity is scoped
to a stable origin key; changed versions append with expected prior version.
Do not deduplicate scientific content by description similarity. Idempotency
keys bind normalized inputs and full local actor/source. Same key plus different
input conflicts; committed decisions/selections/dispatches replay without
recomputation. No generic event-sourcing engine is necessary.

### Migration and compatibility

Require an explicit v3→v4 migration, verified before and after, in one transaction.
V1→v2 and v2→v3 remain explicit prior steps. Keep `init` at v1. No legacy row,
DDL meaning, status, byte encoding, hash, graph sequence or receipt is rewritten.
Old binaries may refuse v4; downgrade is not offered.

Future implementation must update Store/PlanStore/GraphService version checks,
both migration dispatchers, and exact schema verification to recognize known
v4. `plan migrate` on verified v4 retains its planning compatibility response
`schema_version: 2, status: already_current`; graph migration similarly reports
graph compatibility version 3. Neither downgrades the actual user_version.
Legacy context bytes and authorization freshness remain unchanged on v4; all
new decision tables are excluded from export-v1. New graph-aware freshness
belongs solely to the new dispatch contract.

## 6. Proposed interface contracts

The companion draft defines the conditional service surface and nonexecuting
outcomes. Names are proposed internal Python interfaces, not existing commands.

- `capture_context`: obtains one read snapshot of graph and execution plus exact
  fixture feedback; persistence may occur later, so freshness is rechecked at use.
- `record_candidates`: validates origins, exact references and separate trusted
  binding inputs; cannot create a TaskSpec or approve/import a proposal.
- `decide`: invokes pure pinned estimator/policy, stores all considered members,
  returns immutable ranks or abstention. No scheduling side effects.
- `select_recommendation`: trusted operator selects/clears against expected prior
  selection, independently of proposing and task admission.
- `dispatch_next`: takes a request ID and explicit selected activation ID;
  verifies and claims at most one task, then uses the existing lifecycle.
- `show/list`: bounded immutable context/decision/selection/dispatch inspection,
  including replay and current linked run state with its temporal label.

To capture consistently, extract a private graph read body that **requires** a
caller-owned transaction. Existing public graph methods keep owning their
transactions and retain their nesting refusal. The context builder begins one
read transaction, invokes the private graph body and `PlanStore.context_bytes`,
and records pins/manifest from that snapshot. Do not relax all public read APIs
or stitch together unqualified snapshots from separate connections.

For the first slice, reuse the complete execution snapshot and its 1 MiB limit
explicitly. Graph bounds remain separately recorded. Decision context size
failure must not truncate execution/evidence; the draft proposes its own wrapper
limit. This knowingly retains the complete-state scaling limitation of VS-002.

## 7. Does this demonstrate exploration and exploitation?

Yes, as a deterministic engineering demonstration, if estimates are calculated
from revealed state rather than a table of canned winning IDs. New candidates
may be appended each round; existing candidate versions retain scientific
content while new decision-member estimates respond to feedback. Changed action
content creates a new candidate version. The scheduler consumes stored ordinals,
so replacing the policy does not require a scheduler change.

Use a fictional branch diagnostic with two possible feedback outcomes and a
small information-aware comparator. In one branch, an informative low-direct-
value action precedes an immediately promising action, and its feedback changes
which follow-up ranks highest. In another, information is redundant or costly
and exploitation ranks first. The estimator must use only revealed feedback;
the evaluation harness retains the unrevealed oracle separately.

An illustrative fixture policy can rank by `direct_value + weight * info_value`
after per-resource feasibility filters, with both terms explicitly measured in
declared synthetic utility units. This equation belongs to that versioned test
policy, not the system architecture. Do not divide by a resource vector or
invent exchange rates. Represent uncertainty separately without pretending a
fixture confidence number is calibrated probability.

Actual demo outcomes may determine which **synthetic** feedback branch is
revealed, under a recorded fixture rule. They do not measure scientific impact.
Measured worker wall time may update a cost estimate in seconds, retaining null
CPU measurements. A successful task/mean must never be treated as a real impact
reward. Historical replay uses saved estimates and exact estimator/policy
versions; unavailable old code must be reported as not recomputable rather
than silently using a current algorithm.

The fixture must include poor policy choices and a counterfactual feedback
branch. Show that different permitted feedback can change the next decision,
not merely that round numbers choose predetermined tasks. Report synthetic
metrics separately from actual run/evidence/cost records. Neither fixture
improvement nor a regret calculation validates an empirical research policy.

## 8. Risks and counterexamples

| Counterexample / risk | Required behavior or limitation |
| --- | --- |
| High-ranked unapproved or approved-but-unimported proposal | No stored-task binding; cannot claim or materialize it |
| Manual task has no plan receipt | Preserve existing trusted manual admission; do not retroactively require proposal approval |
| Candidate text names a task/command/URL | Treat as inert description; only separate verified binding participates |
| Graph interpretation says a prerequisite is satisfied | Ignore it for readiness; use `dependencies` and actual task status |
| Blocked child ranks first, ready mapped task second | Skip child and dispatch second; record blockers |
| Only unranked prerequisite is ready | No FIFO/prerequisite promotion; needs_decision and potential starvation are explicit |
| New evidence or unrelated graph correction after activation | Strict stale refusal; operator must obtain a new round, even for an unrelated correction |
| Worker result committed after a first ranked claim | Old activation consumed and snapshot stale; no second claim from it |
| Activation races with dispatch or another activation | Expected-head check plus one write transaction; each dispatch records the selected head it actually used |
| Failure between run insert and dispatch receipt | Whole claim transaction rolls back |
| Lost response after committed claim | Identical request returns history; does not start worker again, even if no worker actually started |
| CPU/GPU/money requirement is unknown or unenforceable | Policy filters/abstains; dispatcher refuses an unsupported hard execution requirement |
| Synthetic token cap confused with real budget | Store synthetic units as such; no claim of real reservation or cumulative accounting |
| Truncated graph hides contradictory assessment | Mark frontier and abstain under initial policy; no scientific certainty or implicit completeness |
| Two actions map to same task | Reject ambiguous decision mapping; avoid duplicate priority or evidence accounting |
| Information heuristic repeatedly chooses distracting diagnostics | Retain adverse fixture result; no claim of optimality, calibrated VOI or fairness |

Local actor identity is trusted, not authenticated. Store access and installed
Python code remain trusted. Pure function seams are capability discipline within
the application, not a sandbox for arbitrary plugins or generated Python.

## 9. Recommended implementation scope and acceptance

After approval only: implement the six responsibilities with bounded typed
records, additive v4, one static and one feedback-dependent deterministic policy,
explicit selection, one-claim ranked dispatch, replay/inspection and offline
fixture. Defer real candidate generation, learned scientific impact, online
retraining, multi-resource scheduling, standing activation delegation, FIFO
override, background triggers, new workers, dashboards and VS-005.

The [draft](VS-004.md) maps D1–D13 to concrete tests. In particular, require:

1. Two admitted ready tasks in order A then B; recommendation B before A; actual
   first run is B with a linked dispatch receipt, including after restart.
2. A fresh ranking containing a blocked first task and ready second task; second
   runs. Unranked-only, absent, stale, consumed, abstaining and truncated cases
   create no task/run/evidence and report an explicit reason.
3. Concurrent claimers, activation compare-and-set, graph/execution writes around
   claim, fault injection during receipt commit and interruption after commit.
4. Multi-round feedback with changed estimates, new candidate D, counterfactual
   outcome, cost surprise, baseline transition by operator fixture only, and a
   misleading information-policy case. No future oracle inputs reach the policy.
5. Populated migration/reopen/rollback and exact v1–v3 preservation, all original
   execution/planning/graph suites and documented offline demos.

No VS-004 tests or demonstrations have been executed for this design assignment.
The earlier current-state test results are historical evidence about VS-003,
not validation of these proposed interfaces.

## 10. Decisions requiring human approval

Before implementation, approve or amend V4-1–V4-13 and the narrowed choices:

- Separate internal dispatch operation; v4 refusal of legacy FIFO entry points;
  no public ranked CLI or FIFO override in the initial slice.
- Strict graph-sequence plus complete-execution freshness, one claim per
  activation, explicit new round afterward, and accepted liveness/starvation
  limitations. Multi-claim ranking retention is not implicitly authorized.
- Operator-only expected-head activation/clear with local trust assertions;
  no manager auto-activation or authorization delegation.
- Additive six-table v4 ledger, embedded estimates/configurations, verified
  compatibility migration and the transaction-owned graph read extraction.
- Partial-context/truncation and unknown-resource rules; existing fixed-worker
  execution profile only, with refusal of unsupported hard budget constraints.
- The synthetic estimator/policy contract, fixture utility/feedback rules,
  proposed bounds and D1–D13 acceptance matrix in the implementation draft.

The documents prepare reviewable choices. Approval of research direction alone
does not approve this implementation draft, a study, a budget or a new worker.
