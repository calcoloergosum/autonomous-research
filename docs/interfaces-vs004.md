# VS-004 internal decision and ranked dispatch contract (v1)

This additive offline contract implements ADR-024–030. These encodings and
synthetic policy constants are reversible engineering defaults. V1–v3 CLI,
errors, FIFO, context export, approval and import stay unchanged. Init stays v1.
No network, model, new worker, task admission, baseline authority or scientific
validation is added. Local actor strings are trusted assertions, not authentication.

## Version, storage and migration

`arf.decision_store.migrate_decisions(Store)` accepts only verified v3/v4.
It checks exact SQLite-normalized DDL and foreign keys, creates the additive
`DECISION_SCHEMA` and sets user_version=4 in one BEGIN IMMEDIATE transaction.
Any failure rolls back all DDL/version changes. Verified v4 returns
`{schema_version:4,status:already_current}`. Older migrations verify v4 and
return their historical compatibility version (2 or 3), without downgrade.

Eight immutable tables (DDL in decision_store.py):

- decision_contexts: context hash/ID, study, charter, canonical body, capture time.
- decision_candidates: (study,candidate ID,version), previous version, origin,
  canonical body and optional trusted task/spec/admission binding.
- decision_batches: request ID, complete request hash and returned versions.
- research_decisions: request/decision ID, study/context, previous decision,
  canonical request and complete result, calculation duration, timestamp.
- decision_members: exact candidate version FK, unique ordinal and candidate per
  decision, nullable priority group only for excluded members, estimate/body.
- decision_publications: request/publication ID, decision, unique predecessor
  (including a single initial publication), immutable request/result.
- decision_assessments: request/assessment ID, original decision, current context,
  exact candidate-head digest, publication head, versioned relevance result/cost.
- decision_dispatches: request/dispatch ID, decision/publication/assessment,
  nullable study/task/run with composite FK, unique claimed run, immutable audit.

All references are same-study through composite keys; all tables have update and
delete guards. Canonical JSON retains full configuration/provenance. No legacy
row/backfill changes; all ledger writes are excluded from export-v1 and graph seq.

## Canonical inputs and service

UTF-8 sorted compact JSON, no nonfinite values or duplicate keys, depth <=32,
text <=4 KiB; candidates/refs/batches <=64. Candidate/operation inputs <=64 KiB,
full decision including members <=256 KiB. Execution component <=1 MiB unchanged;
context wrapper <=2 MiB embeds the execution object directly, retains exact
component hash, graph QueryLimits and revealed synthetic feedback. Oversize
refuses without dropping evidence. Inspection is by exact ID or bounded page.

`DecisionService(store)` requires v4 and verifies required objects. Methods:

- `capture_context(selection=Selection(), feedback=Feedback())`: one owned read
  transaction joins private graph read body and unchanged PlanStore.context_bytes.
  Selection stores roles/edge filters/root, limits, intentional omissions, frontier,
  query version, partial portfolio and selected-view completeness. Graph as-of
  execution remains current, never historical. Capture time is outside identity.
- `record_candidates(request_id, definitions, bindings, actor)`: definitions are
  typed CandidateDefinition records, origin kind/key/hash, positive version and
  expected prior, kind, description/intended result, pinned refs, qualitative
  Impact and optional Synthetic values/cost vector. Identity is hash(study, origin
  kind/key), never task ID or text similarity. Same version/content replays;
  revision requires current expected prior. Bindings are separate candidate-origin
  key -> existing task ID. Source payload cannot supply executable binding.
- `decide(request_id, context_id, candidates, policy, constraints, actor,
  previous_decision_id=None, controller_profile=None)`: exact version pairs and pure fixture estimator/
  policy; stores full membership atomically. No execution. `publish` validates
  saved inputs/bindings and current snapshot/head before appending an automatic
  controller publication; no operator activation. `run-next` automatically
  republishes a recomputation when the relevance policy requests one.
- `show_context`, `show_decision`, `show_publication`, `show_assessment`,
  `show_dispatch`, `list_decisions(limit=32, offset=0)`: immutable historical
  payloads. Pages cap at 64 items and 2 MiB, returning `{items,next_offset}`;
  next_offset is null at end. A byte-limited page returns explicit continuation.
  Dispatch result remains historical even when its run is now complete; current
  run state is separately available from Store.task.

Requests bind complete inputs and actor. Exact committed replay precedes current
state checks and calculations. Conflicting request IDs refuse. Batch receipts
commit even when every version already exists. No automatic retry after uncertain
execution. Pure deterministic calculation happens outside write/claim transactions.

Task binding rereads normalized TaskSpec and validates kind/input/dependencies.
Manual admission uses immutable task sequence/creation metadata. Imported admission
verifies exact persisted proposal, approval and matching import receipt/spec hash;
old approval-context freshness is not reimposed. Changing binding requires a new
candidate version. Duplicate mapped tasks within one decision refuse. Unmapped
ideas can rank but never execute. Typed refs resolve via GraphService in this study.

## Scientific judgment, estimates and policies

Impact records carry status qualitative/unknown/incomparable/contested, rationale,
assumptions, uncertainty and alternatives. No numeric scientific impact is
required. Synthetic metadata has viable/nonviable nonnegative integer direct
values, diagnostic bonus, relevance flag and resource vector. Unknown branch uses
floor(mean(values)), min/max interval; known branch uses its value and zero bonus.
The proxy unit is synthetic_points and calibration synthetic_uncalibrated.
Nonnegative fixture proxies cap at 10^9 and cost/ceiling values at 10^15.
Costs retain wall/CPU/GPU seconds, tokens, human minutes, money/currency and
synthetic_tokens; null means unknown. Money ceilings require a currency and
mismatched currencies exclude; no currency conversion is inferred. Wall prediction uses median/min/max of saved
completed same-worker observations, otherwise configured prior. CPU stays unknown.
Revealed synthetic cost overrides have explicit evidence/fixture provenance.

Both policies share saved estimates and per-dimension ceilings; unknown required
costs and infeasible dimensions exclude with reasons. Unsupported real hard
constraints refuse with unsupported_resource_constraint. Static groups follow
saved origin_order; information groups follow negative (direct+weight*information),
weight a declared nonnegative integer. Ties sort candidate ID UTF-8 bytes/version.
Factors/qualifications and exclusions are persisted. Missing proxies exclude;
truncated selection abstains. Qualitative inputs may abstain without invented
scores. Installed algorithm identities include source hashes/config/version.

## Selective replanning and race boundary

Relevance v1 is explicitly a synthetic scenario policy, not scientific inference.
Feedback stores a fixture source, branch, evidence refs and up to 64 trusted rules:
(task ID, exact spec hash, effect engineering_only or branch_from_mean, optional
synthetic cost surprise). branch_from_mean reveals viable when observed mean>=5,
nonviable otherwise. No oracle is accepted before actual evidence exists.
Every new evidence row is compared with these exact rules, regardless of graph
links. Missing/mismatched rule, missing old evidence, unknown/failed/interrupted
attempt, explicit retry or changed profile is critical refusal. Engineering-only
means only this attributed synthetic fixture asserts no branch impact; measured
wall costs are recorded and trigger replanning when the saved policy consults
a wall-cost ceiling; otherwise the synthetic scope explicitly treats them as
noncritical to ranking. Relevant branch/cost
feedback, graph changes (including baseline transitions) and new candidate heads
request recomputation. All graph changes conservatively count as relevant.
Unchanged or explicitly noncritical execution changes permit reuse. The original
context is immutable. No global execution-hash expiry and no one-claim expiry.

Assessment records include original/current context IDs, candidate-head digest,
publication, read-set/change reasons, uncertainty, partiality and measured check
wall time; predicted check/recompute time is unknown with reason. Max 64 changed
items, 1 second inference check budget; exhaustion defers. This is a post-check
time bound, not a preemptive controller deadline. Snapshot and evaluator wall
costs are recorded separately and summed; write/claim overhead is not measured.
One invocation evaluates at most once, computes at most one new recommendation outside transactions, then does
an exact state/head recheck. Replan capture must match the assessed execution/graph
snapshot before any recomputation/publication. Concurrent changes cause
needs_decision/state_changed,
not an implicit retry loop. Assessment cost and recomputation cost stay separate.

Dispatch owns controller_lock. It first replays committed receipts (without
execution), enumerates ALL admitted pending dependency-ready work independently
of ranks, and separates one-active-run capacity. Before a claim BEGIN IMMEDIATE
rechecks context identity, publication/head manifest, admission/spec/profile,
allowlist, statuses and dependencies. Policy runs outside this transaction.
Ranked blocked entries are skipped with blocker audit. Ready work absent from
membership is visible and causes needs_decision/unranked_ready_task. Ready mapped
members excluded by policy are not silently executed. Claim uses the original
transaction-owned pending->running/run insertion body; receipt insertion shares
that transaction. Worker/finalization reuse the original lifecycle outside it.
Receipt write failure rolls back the claim. Finalization failure preserves the
committed running attempt for explicit recover/retry. Replayed claimed receipts
never reexecute, including after recovery, failure or replacement publication.
An assessment committed before a receipt failure replays under the same inputs;
changed intermediate inputs conflict and require a fresh explicit request ID.
Derived IDs exceeding 4 KiB use a hash rather than truncation. The pinned profile
hash covers the fixed worker, execution lifecycle, ranked adapter, decision input
models and relevance implementation; a code upgrade requires a new context and
recommendation rather than silently substituting an implementation.

## Exact v4 run-next shapes

No new public verb/flag. `Store.claim_next` on v4 raises ranked_dispatch_required.
The internal `dispatch_next(service, request_id)` returns a durable receipt;
public run-next uses a fresh UUID per invocation. On a new claim it runs one worker
and returns the historical VS-001 success/failure shape plus `dispatch_id`,
`recommendation_id`, `assessment_id`. Worker failure retains exit 1.
Nonclaim responses (exit 0) contain exactly `status`, `reason`, `dispatch_id`,
`recommendation_id` (nullable), `assessment_id` (nullable), and `audit`:

| status | reason |
| --- | --- |
| review_required | unfinished_attempt |
| no_ready_task | empty_queue or prerequisites_blocked |
| needs_decision | missing_candidates, policy_unconfigured, critical_invalidity, unranked_ready_task, no_ranked_ready_task, state_changed (historical receipts may retain missing) |
| deferred | reasoned_abstention or assessment_budget |

Audit contains authoritative ready IDs and blockers, never a study_complete claim.
Internal claimed receipt adds task_id/run_id with status claimed. Schema,
malformed/forged binding, persistence and limit errors raise PlanError/SQLite
errors and retain existing CLI stderr/exit 1. Controller contention retains the
existing busy error. No arbitrary exceptions are hidden as a harmless no-ready.

## Reproducing the offline fixture

```bash
source .venv/bin/activate
mkdir -p .local
decision_demo_dir=$(mktemp -d .local/vs004.XXXXXX)
python -m arf.decision_demo --db "$decision_demo_dir/arf.db" > "$decision_demo_dir/result.json"
python -m arf.decision_demo --inspect --db "$decision_demo_dir/arf.db" > "$decision_demo_dir/restarted.json"
```

The harness requires a fresh path, admits only fixed demo tasks, automatically
publishes recommendations and invokes explicit run-next calls. B/A/C share one
recommendation; C's actual result reveals fictional branch/cost feedback, then D
arrives and a relevance assessment triggers a new recommendation. Competing
unreviewed graph assessments, an explicit operator baseline transition, an
unmapped idea, a high-priority blocked task, counterfactual feedback and a
misleading information bonus remain inspectable. Truncation ends in deferred
with real ready work. Synthetic payoffs never enter observation tables or policy
inputs. Inspection starts a separate process and performs no dispatch.

## ADR-030 initial recommendation bootstrap (offline profile v1)

On v4, after receipt replay, unfinished-capacity and authoritative ready-set
checks, an absent publication invokes one bounded initial-manager attempt outside
any claim transaction. Zero registered heads returns `needs_decision /
missing_candidates`. No tasks, candidates, approvals, imports or relevance rules
are synthesized. Empty/blocked queues keep the existing no-ready outcomes and
never compute a ranking. Existing publications use the existing relevance path.
The strict all-ready coverage rule is unchanged; P2 remains deferred.

The trusted local `arf.bootstrap.INITIAL_PROFILE` is an installed
`BootstrapProfile(name='offline-synthetic-initial-ranking', version=1)` containing
exact `Policy(name='information',version=1,weight=1)` and
`Constraints(ceilings={'synthetic_tokens':10},hard=(),currency=None)`, plus the
existing default Selection and Feedback. This deliberately synthetic comparison
profile is a reversible offline fixture configuration, never a scientific-impact
formula. A missing/malformed/unsupported name/version/policy/constraints returns
`needs_decision / policy_unconfigured`; the controller does not guess a policy.
No new CLI flag, environment-variable selector or persistent schema is added.

Trusted local fixtures may preconfigure a bounded Selection or explicit Feedback
rules in this profile. The default Feedback has branch unknown, empty evidence,
empty cost overrides and **no rules**. Candidate text, demo success and missing
graph links never produce engineering_only rules. With defaults, the first
claim can execute, but a later call seeing its new evidence conservatively
returns `needs_decision / critical_invalidity`. Reuse requires separately
preconfigured, spec-pinned trusted rules and a fresh recorded relevance check.
Unmapped candidates cannot dispatch. Missing quantitative inputs/qualitative-only
candidates or truncated context produce the existing saved abstention and
`deferred / reasoned_abstention`; a ranked set without a mapped ready member or
with uncovered ready work keeps the existing needs_decision reasons. Corrupt
bindings/schema/persistence failures remain operational errors with no claim.

Bootstrap captures a fresh joint context and bounded exact candidate heads,
validates the snapshot/head manifest, records a decision and publishes it with
expected_prior=None. Its request IDs derive from the dispatch ID with suffixes
initial-decision and initial-publication (using the existing bounded hash rule).
The decision's optional controller_profile metadata binds the full profile,
source SHA-256 and configuration hash in both immutable request and result.
Older decisions omit this key and retain their exact request/replay encoding.
The installed execution source profile also pins bootstrap.py. Profile changes
are not per-ranking human activation and never authorize task admission.

Decision/publication persistence reuses existing transactions and receipts;
policy inference never runs in a claim transaction. Concurrent head, candidate,
graph or execution changes yield `needs_decision / state_changed`, or the caller
observes the committed initial head. At most one initial publication wins CAS;
losing immutable advisory decisions may remain, with no run. The normal final
state/head/binding/readiness check and per-claim assessment still precede the
atomic task/run/dispatch receipt. Controller locking spans the entire lifecycle.

Publication failure rolls back its event, preserving any already committed
advisory context/decision and creating no running task. Interruption after
publication leaves an inspectable published ranking, never an implicit worker
resume. A new explicit invocation follows the existing relevance/claim path.
Committed dispatch receipts replay before bootstrap/config checks and never
execute again. Nonclaim and claimed receipts from an initial attempt add
`audit.bootstrap` with version=1, profile/configuration identity and any created
decision/publication IDs. Public success/failure keys and nonclaim top-level
shapes stay unchanged. New nonclaim reasons missing_candidates,
policy_unconfigured and state_changed are needs_decision outcomes, never
no_ready_task or scientific completion. V1–v3 behavior is unchanged.
