# VS-004 technical review — Decision loop and ranked dispatch

**Status: Review recommendations only; not approved for implementation.**

**Updated after owner review (2026-11-10):** ADR-026 establishes that scientific impact is a fallible, contextual assessment, not an objectively computable number. ADR-027 prefers reusing one recommendation for multiple claims with selective, cost-aware replanning. Earlier one-claim and global-staleness choices are **historical alternatives**, not requirements. All precise interfaces and VS-004 implementation still need review.
Prepared 2026-11-10 against `main` commit
`12af093a7feabc3c49613cf38d6f4935eba72b23` and the latest
[proposal](VS-004-proposal.md). The companion [implementation draft](VS-004.md)
is conditional on human approval. Neither document adds an accepted ADR.

The owner has accepted recommendation-ordered execution, **automatic Research Manager priority selection (V4-13 / ADR-024)** and **independent full ready-set verification without silent FIFO fallback (V4-12 / ADR-025)**. These decisions supersede the original operator-per-round activation assumption. Exact dispatch APIs, persistence and freshness implementation details remain under review; the full VS-004 task is not approved. This assignment authorizes only these two documents.

## 1. Architecture assessment

The proposal fits the repository if the decision loop remains a producer of
immutable data and the controller remains the sole execution authority. The
smallest useful slice is an explicit round: capture state, supply candidates,
estimate, rank, publish a controller-verified scheduling preference automatically,
dispatch one admitted task on explicit invocation, then capture new feedback. A saved recommendation must never start a worker.

| Responsibility | Minimal implementation recommendation | Capability boundary |
| --- | --- | --- |
| Research Context Builder | One trusted snapshot function with a selected graph view, complete execution snapshot and completeness manifest | Reads research state; writes only its decision snapshot |
| Candidate Manager | Versioned records and a deterministic candidate source function | Supplies possible actions; cannot add executable tasks or bind them by free text |
| Scientific impact assessment / Cost Estimation | Reasoned, revisable scientific judgment (possibly qualitative, disputed or unknown) beside separate resource-cost estimation | No formula completely determines research impact; neither assessments nor proxies become Evidence |
| Allocation and Replanning Policies | Rank from evidence-linked judgments, predictions and constraints; separately evaluate whether an existing recommendation still applies | Ranking and re-evaluation have explicit versioned reasons; neither policy receives executor, task admission or authorization capabilities |
| Decision Ledger | Small trusted service with immutable records and request replay | Saves complete inputs/results; a trusted controller can automatically publish the manager's priority, but untrusted text cannot admit tasks or start execution |
| Recommendation-Guided Scheduler | Separate controller operation and narrow transaction-owned ranked claim | Independently enumerates *all* admitted ready tasks, checks ranking/eligibility/capacity, and invokes only existing lifecycle |

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

### Recommendation validity, reuse and automatic publication

**Preferred architecture (ADR-027):** A recommendation can remain the ranking basis for **multiple** distinct, separately authorized task claims. The original context hash identifies what was known at recommendation creation; it does not by itself decide whether a ranking is still useful. New evidence, task completion and graph changes require an auditable *relevance check*, not automatic complete re-ranking.

A separate versioned **Replanning Policy** records consulted premises, changed items, relevant uncertainties, estimated cost of another manager assessment and a reasoned decision to reuse, recompute, refuse or defer. No claim that scientific impact or replan value can be computed exactly. Unknown critical premises must cause conservative refusal or reassessment, not silent reuse.

The trusted controller publishes manager priorities automatically without per-round operator activation (ADR-024), but publishing never triggers a worker. At dispatch, the scheduler verifies admission, all actual ready tasks, dependencies, worker restrictions and capacity regardless of whether an old rank was reused. Multiple immutable dispatch receipts may reference one ranking and distinct task/run IDs, each with a recorded reuse/replan check. A global graph/execution hash difference may signal change but **must not unconditionally expire** a rank. The earlier one-claim proposal is a rejected default, not an accepted constraint.

**Open:** bounded read-set and relevance policy, partial context treatment, concurrency and cache invalidation, stale age/use-count limits, cost of re-evaluation, and how to record human/AI scientific disagreement. No approved precise schema/API yet.

### Atomic dispatch procedure

1. Acquire the existing `.controller.lock` for the same claim/worker/finalization path. Lock contention remains a nonexecuting busy error.
2. Enter `BEGIN IMMEDIATE`; identical dispatch request replay returns its recorded result before recomputing selection or retrying physical execution.
3. Refuse when another attempt is running. Capacity busy or interrupted is distinct from no research tasks being ready.
4. **Independently enumerate the authoritative set of admitted, pending, dependency-ready tasks**, with worker/constraint eligibility. Do not derive this set from the manager's recommendation list. Record whether no pending work exists, tasks are dependency-blocked, or resource constraints prevent execution; none implies study completion.
5. If ready work exists, verify the current controller-published manager decision, its **recorded selective reuse/replanning decision**, and task eligibility inside the claim transaction. One recommendation can guide several claims. Unknown or critically invalid premises trigger bounded reassessment or `decision_unavailable`, not false `no_ready_task` or FIFO. Deliberate `abstain` differs from generation failure. Do not run expensive manager/policy logic under the claim transaction or loop unboundedly.
6. Commit the ordinary task pending→running transition, run row and a dispatch receipt atomically. The receipt binds decision/version, task/spec/run, preclaim freshness, eligibility audit, skipped entries and scheduling version. A failure inserting the receipt rolls back the claim.
7. Run the fixed worker through the existing execution/finalization body outside the transaction under the controller lock. Never call a model/policy within the claim transaction or let the manager claim tasks directly.

An absence of eligible ready work causes no execution. A legitimate non-claim dispatch request may retain an immutable receipt with an explicit outcome; malformed requests/DB failures still fail without inventing a receipt. A committed claimed dispatch never re-executes on replay, even after recovery or a new ranking.

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

**V4-12 and V4-13 are accepted behavioral principles (ADR-024–025)** alongside the owner's ranked-execution direction. V4-11 and other architecture/implementation choices remain proposed.

| ID | Recommendation and rationale | Alternative / compatibility implications |
| --- | --- | --- |
| V4-1 | One complete offline round plus real ranked claim and fixed-worker execution | Advisory-only omits the requested execution ordering; unattended autonomy broadens scope |
| V4-2 | New versioned advisory identities with exact graph/proposal origins and optional verified stored-task bindings | Reusing proposal IDs confuses approval with valuation; requiring graph nodes creates unnecessary graph writes |
| V4-3 | **ADR-026:** preserve reasoned, qualitative/uncertain/incomparable impact assessment separately from information proxies and cost vector | Do not require a universal numerical impact score; synthetic policy arithmetic is only a test fixture |
| V4-4 | Static ordering and optional information-aware arithmetic for **synthetic test utility only**, with separately inspected qualitative scientific reasons | UCB/Thompson/VOI need unvalidated reward/posterior assumptions; no general scientific impact formula |
| V4-5 | Separate immutable context containing selected graph and exact execution component | Ephemeral inputs complicate replay; modifying plan export would change authorization hashes |
| V4-6 | Explicit additive SQLite v4; six substantive tables, embedded estimate/configuration payloads | Sidecars complicate atomic claim/audit; stateless tests cannot preserve decision/dispatch history |
| V4-7 | **ADR-027 preferred:** retain recommendations for multiple claims when the Replanning Policy finds relevant premises still valid; explicitly record reuse/recompute/defer | Do not force full reevaluation after every run or ignore newly relevant evidence |
| V4-8 | Trusted ledger and scheduling adapter around pure estimation/ranking | Manager receives no Store, approval, import, baseline-transition or executor capability |
| V4-9 | Declare global portfolio partiality; allow complete selected views, exclude candidates missing required inputs/costs; truncation causes abstention in v1 | Failing every intentionally selected view is unusable; ignoring truncation/unknowns overstates knowledge |
| V4-10 | Multi-round deterministic fixture, adverse cases, replay and real-worker plumbing, plus all legacy regressions | Synthetic improvement cannot establish calibrated predictions or effective real research allocation |
| V4-11 | Separate internal v4 dispatch; v1–v3 keep FIFO; v4 legacy FIFO entry points refuse | Automatic v4 `run-next` ranking hides schema-dependent behavior; a mode flag adds mixed-mode semantics; leaving FIFO on v4 is an explicit bypass option |
| V4-12 | **ACCEPTED (ADR-025):** check authoritative full ready set first. If zero, do not run; if ready tasks exist but ranking cannot select one, re-evaluate or report recommendation failure; reasoned abstention is distinct. No hidden FIFO fallback | May stall when manager cannot rank a ready prerequisite; do not mislabel this as no work or infer scientific completion |
| V4-13 | **ACCEPTED (ADR-024):** manager automatically updates order and trusted controller publishes verified scheduling preference without per-round human activation; never grants admission or execution | Publication atomicity, refresh, selective replanning and **multi-claim validity mechanics** remain under review; publication never auto-starts a worker |

### V4-11 interface comparison

| Option | Strength | Cost / recommendation |
| --- | --- | --- |
| Change `run-next` to rank automatically on v4 | Familiar invocation | Behavior and readiness results depend on schema; an implicit selection source is harder to review. Do not choose for this slice |
| Add explicit ranked mode to `run-next` | Reuses CLI command | Must define flag combinations, defaults, activation IDs and whether FIFO is an override. Viable later if a public CLI is wanted |
| Separate dispatch operation | Distinct request ID, activation and replay contract; leaves old CLI intact on v1–v3 | Recommend internal service now, harness for demonstration, public verb deferred. Refuse legacy FIFO on v4 unless an override is separately approved |

### V4-12 readiness, abstention and liveness

**Accepted:** check the real ready set from task statuses and dependency rows, independently of ranked IDs. If empty, do not claim; distinguish absent tasks, dependency blockers and resource/capacity limitations. A running attempt is `busy` or `review_required`, not a reason to declare research finished.

If ready tasks exist but the recommendation is absent, stale, unusable or omits all eligible tasks, request explicit bounded re-evaluation by the manager or report `decision_unavailable`. An intentional policy `abstain` must carry a recorded rationale and be distinguishable from estimation failure. Neither may launch a task or silently use FIFO.

Example: a ranked child C depends on ready unranked prerequisite P. P belongs in the authoritative ready set. The manager must reconsider P; the scheduler cannot invent its priority or quietly run it. Starvation remains a possible outcome, and no fairness/aging guarantee is being invented in this slice.

### V4-13 automatic priority selection

**Accepted:** a trusted controller can publish the manager's versioned, provenance-bound ranking automatically; no operator clicks or manual activation for every new decision. **ADR-027:** the same rank may remain usable across multiple independently checked claims. Model output is data, not a task-claim or approval capability. Existing manual task admission and operator approval/import remain unchanged. Dispatch still requires its own explicit trigger; saving a ranking does not start work.

**Still undecided:** the exact publication interface, whether saving and publication are one transaction, handling of competing decisions/selection heads, and lifetime of one saved ranking across multiple claims. One-claim activation remains a conservative historical alternative, **not the preferred ADR-027 multi-claim direction**.

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
| `decision_selections` | Optional study-local automatic controller publication/selection sequence and expected predecessor; verified manager/policy provenance, decision FK, freshness token and receipt/time; no per-round human activation |
| `decision_dispatches` | Request ID/full request binding; reusable recommendation/decision refs and recorded applicability/replanning-check refs; immutable claimed/nonexecuting outcome; unique chosen run, task/spec refs, scheduling profile and eligibility audit |

Do not create separate estimator/configuration/estimate tables until independently
needed. Estimate payloads in `decision_members` retain their context, method,
units, uncertainty, unknowns and observations used; a new round inserts new
members. Synthetic revealed feedback can be embedded in the context as a
versioned fixture payload with source and digest, not a new Evidence row.
In addition to these six substantive tables, use a small candidate-registration
request-receipt table for exact batch replay, including requests that insert no
new candidate versions. This is narrow idempotency storage, not a generic event
log. Other operation receipts can be stored in their corresponding tables.

An explicit fixture feedback payload is input to estimation only. The dispatcher does not treat synthetic rewards or predictor scores as scientific truth. It verifies current readiness and execution profile while a separately recorded Replanning Policy evaluates continuing applicability. Original decision input/configuration hashes remain immutable even after subsequent reuse.

Use composite FKs for decision/member/candidate and study/task references. Bind
claimed task/run with the existing `(study_id, task_id, run_id)` key; constrain
claimed rows to nonnull task/run and nonexecuting rows to null task/run. Require
unique claimed run ID, **without** a uniqueness constraint limiting each recommendation to one claim. Validate typed
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
- Automatic trusted publication of a manager decision: verify its stored inputs,
  task bindings and versioned policy; persist the scheduling preference without
  a human activation each round. Atomic-vs-separate publication remains for review.
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
| Only unranked prerequisite is ready | Authoritative ready scan finds P; manager must re-evaluate P or report a recommendation problem, not `no_ready_task`; no silent FIFO promotion |
| New evidence or unrelated graph correction after publication | Replanning Policy records whether relevant premises changed; reuse may remain valid for unrelated changes, while relevant/unknown critical changes trigger recompute/refusal. A changed global hash alone does not expire a rank |
| Worker result committed after first ranked claim | Scheduler may reuse **the same recommendation** for a subsequent task only after a recorded relevance/replanning check and current authoritative readiness validation, otherwise replan/refuse |
| Automatic publication races with dispatch or another publication | Expected-head check plus one write transaction; each dispatch records the selection head actually used |
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

After approval only: implement bounded versioned contexts/candidates/judgments/cost estimates, synthetic reference policies, automatic priority publication, **versioned selective Replanning Policy**, a reusable ranking with per-claim audit, narrow ranked dispatch, replay/inspection and offline fixtures. No production model, unattended trigger, scheduler-wide rewrite, multi-resource capacity engine or VS-005 dashboard.

The [draft](VS-004.md) maps D1–D13 to concrete tests. Require at minimum:

1. Admitted ready A precedes B by FIFO, but manager ranks B before A; dispatch runs B and the *same* ranking may guide a **second claim** after a recorded applicability/replanning check, without per-round human activation.
2. A higher-ranked child blocked on dependency does not run; an unranked ready prerequisite **is discovered by the independent ready scan**, then causes manager re-evaluation or a visible recommendation failure, not a false `no_ready_task`.
3. No registered ready task means no dispatch and a clear reason; ready tasks with missing/stale/abstaining/incomplete rankings yield distinct results; no FIFO fallback and no invented research-complete claim.
4. Two concurrent claimers, automatic preference/replanning changes, writer-vs-claim races, claim/receipt atomicity, interruption/restart, and replay never duplicate a run or silently replace a historical recommendation.
5. Multi-round feedback with new candidate D, counterfactual, cost surprise, baseline change only through existing operator fixtures, and an adverse information-policy case.
6. Populated migration and exact v1–v3 preservation, all previous tests and offline demos.

This design-only document introduces no VS-004 test result.

## 10. Decisions requiring human approval

**Already settled:** V4-12 (verify the full authoritative ready set; distinct no-ready, recommendation failure and deliberate abstention; no implicit FIFO fallback) and V4-13 (Research Manager determines priority automatically, trusted controller publishes without per-round human activation). See ADR-024–025.

**Still to review before implementation:**

- V4-11: internal ranked-dispatch API and v4 handling of legacy FIFO entry points.
- **Selective premise validity** versus conservative change detection, multi-claim recommendation lifetime and versioned Replanning Policy with bounded evaluation cost; publication atomicity and head-conflict handling.
- Additive v4 ledger/reference semantics, context snapshot and migration compatibility.
- Truncated/partial context and unknown-resource treatment with the existing fixed-worker execution profile.
- Synthetic estimator/policy versions, **qualitative impact judgments**, Replanning Policy/reuse audit, limits and revised D1–D13 test contract.

Human approval of these technical selections is still required before coding. The accepted V4-12/13 principles do **not** authorize live models, task admission changes, background worker triggers, spending or an implemented VS-004.

