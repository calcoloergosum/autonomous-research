# Current state — VS-003 verified; VS-004 approved, implementation pending

**VS-004 implementation authorization (2026-11-10):** The human owner approved the bounded offline VS-004 task in `tasks/VS-004.md` and V4-11's **same `run-next` interface**: v1–v3 preserve FIFO and exact previous CLI behavior, while explicitly migrated v4 uses Research Manager-ranked dispatch without changing task admission, the worker allowlist or the manual execution trigger (ADR-028–029). ADR-026 forbids treating scientific impact as a fully computable universal score. ADR-027 favors a reusable recommendation across multiple claims, with separately recorded selective and cost-aware replanning instead of automatic expiry on every execution-hash change.

**VS-004 HAS NOT BEEN IMPLEMENTED OR TESTED by this documentation update.** No v4 tables, decision service, Replanning Policy or v4 `run-next` code has been added. Implementation is authorized only for offline deterministic fixtures and verification; no live models, spending, generated code execution, new workers, scientific certification or VS-005 interface. Earlier technical-review proposals suggesting a separate v4 entry point or one-claim lifetime are superseded by `tasks/VS-004.md`.

## Historical VS-004 design decisions and VS-003 verification

# Current state — VS-003 verified; VS-004 design under review

**VS-004 design status (2026-11-10):** The human owner approved two behavioral directions, now recorded as ADR-024–025 in `docs/decisions.md`: **V4-13** Research Manager automatically sets/updates priority of previously admitted work without per-round human activation; **V4-12** the scheduler independently checks *all* registered ready tasks before stopping, distinguishes genuine no-ready from recommendation failure and deliberate deferral, and never silently falls back to FIFO. See `tasks/VS-004-proposal.md`, `tasks/VS-004-technical-review.md`, and the still **DRAFT, NOT APPROVED** `tasks/VS-004.md`.

**Further VS-004 design clarification (2026-11-10):** ADR-026 clarifies that the eventual scientific impact of open-ended research is **not an objectively computable scalar**. Research Manager assessments must preserve reasoned scientific judgment, unknowns, uncertainty, disagreements and supporting context; numerical utility proxies are permissible for labeled synthetic policy tests, not scientific ground truth. ADR-027 records the **preferred architecture of multi-claim recommendation reuse with a separate selective, cost-aware Replanning Policy**. A changed graph/execution hash may indicate relevant new information, but need not automatically invalidate every recommendation. Authoritative task admission, readiness, resources and permissions are still checked on each claim; past recommendations/dispatch records must remain immutable. The exact consulted-premise relevance model, reuse budget and schema/API remain unapproved.

**No VS-004 implementation has been authorized or performed by this update.** Existing `run-next` remains FIFO; actual v4 dispatch API, recommendation reuse/replanning checks, quantitative/qualitative assessment interface, publication, schema and policy contracts remain subject to human review. No new VS-004 tests were run.

## Historical VS-003 implementation verification

# Current state — VS-003 final review corrections verified

**As of 2026-11-10:** Both implementation-review findings (P1 ownership and
P2 initial baseline activation) are corrected within the approved VS-003 scope.
The complete regression suite passes: **450 tests in 17.47s**, including all
G1–G10 acceptance cases, VS-001 on v1/v2/v3 and VS-002 on v2/v3. This remains an
offline engineering fixture with unreviewed graph assertions and unvalidated
observations. No VS-004/VS-005 feature, scientific review, model/API integration,
new worker, execution permission, or authorization delegation was added.

The complete implementation from `0e7b5a4` was cherry-picked onto
`implement/vs003-research-graph`, based on current `origin/main` (`3d9670d`).
This includes the full implementation relative to main while leaving the original
implementation branch intact. PR #1 is already merged and concerned the design
specification; it is not reused. GitHub access is limited to the requested
repository/PR operations; implementation and fixture execution remain offline.
The unrelated untracked `START_HERE_KO.md`, `WORKFLOW.md`, and `docs/roadmap.md`
and all prior local databases were preserved.

## Finalized ownership policy (P1)

Ownership is the exact, case-sensitive local `Actor.name` on the **creation**
operation referenced by `graph_ideas.seq` or `graph_links.seq`. Source records
provenance, and role records caller capability for that operation; neither
changes the owner identity. `revise_idea` and `revise_or_withdraw_link` now use
one ownership check against that original operation inside the write transaction:

- The original author may revise their idea or revise, withdraw or restore their
  own unreviewed semantic assertion, subject to the existing expected-head rule.
- A trusted operator may correct or withdraw another author's assertion. The
  operator's correction is attributed but never transfers ownership.
- Another ordinary recorder receives `unauthorized`, with no inserted revision,
  receipt, sequence increment or other database change. They may instead create
  their own separately attributed competing interpretation.
- For VS-002 notes, the registering graph actor owns graph edits. Original
  provider/request/proposal/hash/context and planner text remain immutable source
  provenance, rather than being relabeled as the registrar's authored content.
  Human Q/H and joint synthesis C follow the same creation-operation rule.

Committed operation replays still precede the new ownership/head checks and
return the original receipt. Tests reproduce a pre-fix cross-author correction,
reopen the database, and verify replay is read-only while a new cross-author
request is refused. Exact replays still bind the full actor tuple and request;
changing either conflicts. Old corrections are not retroactively erased or
reclassified. Older revisions and each correcting actor/source/time remain
available through historical queries. There is no new idea-withdrawal API.

These are local identity assertions, not authentication. The trusted calling
code must supply actor name and operator capability; arbitrary research text
cannot do so. A host owner or caller able to impersonate a local actor remains
trusted. There is no scientific validation or capability delegation mechanism.

## Initial versus subsequent baseline transitions (P2)

An initial activation requires `expected_prior=None`, no active baseline in that
scope, a trusted operator, and valid nonempty rationale. It now accepts
`motivations=()` before any evidence exists. Any supplied motivations still must
be valid exact E/C references. Its stored transition body records
`basis=initial_reference_choice`; this is a reference choice, not an
evidence-supported research conclusion, and its rationale is not an observation.

A replacement or reversion still requires the current predecessor and at least
one valid exact E/C motivation. Its new body records
`basis=evidence_motivated_transition`, without implying scientific validation.
Concurrent initializers or replacements cannot both commit against the same
prior state. Identical operation replay returns the original receipt. Scoped
active state and prior states remain projections of append-only transitions.

There is **no schema migration or API signature/receipt change** for these fixes.
`basis` is additive metadata on newly inserted transition JSON bodies. Tests
prepare the exact older encoding without that key and confirm restart, verified
v3 migration no-op, history and receipt replay leave all bytes/rows unchanged.
The original requests and result shapes are unchanged, and old transition bodies
are never backfilled. Initial activation without E/C is the explicit exception
authorized by this final-review task to the earlier implementation assumption.
No other specification deviation or unresolved architectural approval is needed.

## Verification actually executed for the final review

Environment: existing offline `.venv`, Python 3.12.3, SQLite 3.45.1,
PyYAML 6.0.1 and pytest 9.1.1. No dependencies were installed.

| Command/check | Actual result |
| --- | --- |
| Baseline `python -m pytest -q` before corrections | 427 passed in 16.56s |
| Two focused reproductions, `python -m pytest -q tests/test_graph.py -k 'review_p1_foreign or review_p2_initial'` | 2 failed, 68 deselected in 0.21s: foreign recorder was accepted and evidence-free activation refused |
| `python -m pytest -q tests/test_graph.py` after corrections | 88 passed in 3.75s, before the last three legacy/invalid-motivation cases were added |
| Final complete `python -m pytest -q` | **450 passed in 17.47s** |
| Documented VS-003 offline fixture and separate-process restart inspection | Both exit 0; verification below |
| `git diff --check` | Exit 0, no whitespace errors |

The final graph suite has 91 cases, including 23 new review regressions. These
exercise all Q/H/C creation paths and note registration, self-revision,
operator correction and withdrawal, denied foreign revision/withdrawal,
non-transfer of ownership to a latest reviser, coexisting contradictory
interpretations, historical original authorship, stale heads, replay and exact
no-change checks. Baseline tests cover evidence-free initialization, invalid
rationale/references, recorder refusal, conflicting/concurrent initializers,
replay, motivated replacement, rejection of empty subsequent motivations, and
unchanged pending/running/completed work, observations, charter and legacy
context. Existing G1–G10 tests continue to cover the original graph, migration,
bounds and compatibility contracts.

The README's documented commands were executed using a fresh directory:

```bash
source .venv/bin/activate
mkdir -p .local
graph_demo_dir=$(mktemp -d .local/vs003-review.XXXXXX)
python -m arf.graph_demo --db "$graph_demo_dir/arf.db" > "$graph_demo_dir/result.json"
python -m arf.graph_demo --inspect --db "$graph_demo_dir/arf.db" > "$graph_demo_dir/restarted.json"
```

Actual directory: `.local/vs003-review.JeAfIA/`. JSON transcripts are preserved
beside `arf.db`. Both demo executions succeeded: T1 mean 5.0/count 4,
wall_seconds 0.019873816519975662; T2 mean 9.0/count 2,
wall_seconds 0.01906896010041237. Costs remain zero for LLM tokens, GPU seconds
and human minutes, with CPU seconds null/unmeasured. These are measured fixture
durations, not forecasts. Exactly two observations remain unvalidated; task
`planner-demo-b0849cb9412046e2` stays pending without a run. Graph sequence is 20;
as-of(18) preserves the earlier assessment and motivation. Scoped baseline
`baseline-f4bcc065-86ae-4e45-a84b-2a6946d9a4e1` remains active at transition 18.
Every populated v2 row and the legacy context remained unchanged through graph
writes. The bounded query reported truncation; restart preserved sequence,
runs, observations and active baseline. `PRAGMA foreign_key_check` returned no
violations.

Final correction files are `arf/graph.py`, `tests/test_graph.py`,
`docs/interfaces-vs003.md`, and this state log. README examples are unchanged by
the corrections. The complete implementation PR also includes the original graph
modules, explicit v3 migration, fixture, compatibility extensions, documentation
and expanded regression matrix. Remaining limitations from the initial report
still apply: local trusted identities, no historical reconstruction of legacy
execution status, unchanged VS-002 context v1, no scientific certification,
network research, automatic policy or new executable worker. The implementation
PR is for review; no merge is authorized or performed.

The initial implementation and earlier observations below are historical and
remain intact, including the former evidence requirement for initial activation.

## Historical initial VS-003 implementation report

**As of 2026-11-10:** The approved VS-003 G1–G10 scope and ADR-016–023 are
implemented. VS-001/VS-002 remain operational on their original schemas and v3.
The complete regression suite passed: **427 tests in 16.50s**. This is an offline
engineering fixture, not substantive research or scientific validation. No live
model/API calls, network requests, spending, new worker kinds, generated-code
execution, graph CLI/dashboard or deferred research-policy features were added.
No study charter was modified. The pre-existing untracked `START_HERE_KO.md`,
`WORKFLOW.md`, and `docs/roadmap.md` were left untouched.

## Implemented VS-003 behavior

- `docs/interfaces-vs003.md` was written before implementation and specifies
  the internal typed requests, local caller assertions, errors, schema, limits,
  history and compatibility semantics. Its final text reflects the implementation.
- `arf/graph_store.py`: explicit, verified, transactional v2→v3 migration;
  eight graph tables, foreign keys, indexes and append-only guards. V1 requires
  the existing explicit v1→v2 migration first. Populated migration preserves all
  legacy rows, including exact charter/context/proposal bytes, hashes, identities,
  costs/nulls, decisions, receipts and SQLite task sequence. Repeat is a verified
  no-op; interrupted or unrelated-schema migrations roll back without adoption.
- `arf/graph_models.py`, `arf/graph.py`: typed local actors and revision-pinned
  references; explicit valid-note registration; human Q/H and joint synthesis C;
  six closed semantic edge types; no forged factual edges or objective writes.
  Exact origin/request/provider/hash/context attribution remains distinct from
  scientific evidence. Every logical write, revision and immutable operation
  receipt commits atomically at a monotonically increasing graph sequence.
- Idea/link corrections and withdrawals append attributed revisions under an
  expected-head check. Identical operation replay preserves the original receipt
  without advancing sequence; conflicting reuse fails. Assessments remain scoped
  and unreviewed. Joint C premises get explicit lineage and never extra experiment
  or evidence rows. Derivation cycles are refused; other semantic cycles work.
- Immutable baseline snapshots and scoped operator transitions record reasons,
  exact E/C motivations and affected task/idea dispositions. Concurrent stale
  predecessor writes conflict; reversion is another transition. Nothing cancels,
  starts, retries, rewrites or changes dependencies of existing tasks.
- `arf/graph_query.py`: consistent bounded reads, typed filters, stable node/edge
  lookup, ancestry/affected-by traversal, revision history and as-of projections.
  Original task/run/evidence IDs and successful execution provenance are read
  from legacy storage. Graph history is historical; legacy execution bodies and
  factual edges are explicitly labeled current, with historical status unknown.
  Scoped SUPERSEDES edges derive only from committed operator transitions.
- `arf/graph_demo.py`: deterministic synthetic scenario with two actual fixed
  demo executions, a separate approved/imported pending task, registered Q2,
  branching, competing/convergent assessments, joint C, B0→B1 transition,
  correction/withdrawal and historical/bounded queries. The fixture requires a
  fresh path and has a separate restart inspection mode.
- Compatibility changes are narrow: `Store` accepts schema v3; `PlanStore` accepts
  v2/v3 without graph fields in context v1. `plan migrate` verifies v3 and keeps
  its existing `schema_version: 2, status: already_current` planning response;
  the actual database remains v3. Graph migration is an internal call, not a new
  public command. The executor, fixed worker, authorization and execution DAG
  implementation are unchanged.

## VS-003 verification actually observed

Used the existing offline `.venv`: Python 3.12.3, SQLite 3.45.1, PyYAML 6.0.1,
pytest 9.1.1. No dependency install or network access was performed.

| Command/check | Observed result |
| --- | --- |
| `python -m pytest -q` before VS-003 changes | 222 passed in 7.93s |
| Initial graph acceptance run | 59 passed, 4 failed in 2.90s; inconsistent PlanError/GraphError conversion corrected |
| `python -m pytest -q` first expanded regression run | 421 passed in 14.83s |
| `python -m pytest -q tests/test_graph.py` after additional lookup/concurrency/bounds coverage | 68 passed in 2.92s |
| Final complete `python -m pytest -q` after source changes | **427 passed in 16.50s** |
| Documented fresh `python -m arf.graph_demo --db PATH` | Exit 0; actual observations and receipts persisted |
| Separate-process `python -m arf.graph_demo --inspect --db PATH` | Exit 0; sequence, runs, evidence and active baseline retained |
| Demo `PRAGMA foreign_key_check` | Empty list |
| `git diff --check` and explicit whitespace inspection of new deliverables | Exit 0 / no whitespace errors |

`tests/test_graph.py` contains 68 acceptance cases covering G1–G10. The existing
Store-based VS-001 cases now run on v1/v2/v3; the existing planning fixture cases
run on v2/v3, including the complete separate-process CLI workflow on both
versions. The final total includes 47 additional execution regressions and
90 additional planning regressions over the 222-test starting suite. Tests cover
populated migration and restart, SQLite-authorizer and BaseException rollback,
unknown/modified schemas, invalid/uncertain/non-note registration, exact pins,
source-context verification for both notes and imported tasks, failed/interrupted
run projection, competing evidence, joint premises, append-only history, atomic
receipt rollback, concurrent head/predecessor conflicts, replay, unchanged legacy
freshness, inert injection text, operator checks, and all read bounds.

The scale fixture creates **200 hypotheses and 200 motivation links** around one
real fixed-worker observation. Filtered reads return all 200 within configured
bounds; smaller reads/traversals visibly report truncation/frontier, including
candidate-scan exhaustion and zero-depth traversal. Endpoint index selection is
checked with EXPLAIN QUERY PLAN. No 10,000-node benchmark, hard performance target
or inferred query timing is claimed.

## Reproducible offline fixture and actual observations

Run the README's VS-003 fixture from the repository root:

```bash
source .venv/bin/activate
mkdir -p .local
graph_demo_dir=$(mktemp -d .local/vs003-verified.XXXXXX)
python -m arf.graph_demo --db "$graph_demo_dir/arf.db" > "$graph_demo_dir/result.json"
python -m arf.graph_demo --inspect --db "$graph_demo_dir/arf.db" > "$graph_demo_dir/restarted.json"
```

The recorded run used `.local/vs003-verified.hqk5S8/arf.db`; the two JSON files
beside it retain actual outputs/receipts. Reusing that path for build is refused;
inspection is read-only. Migration preserved every v2 row exactly and repeated
migration returned already_current. After all graph writes, the legacy context
remained `bc55e04d17e8ee1417da940c44f83c773bb5ad9862e544fc3f46addb80b2b8b1`.
No graph operation changed a task, run, observation, approval, receipt or charter.

| Task | Actual result | Measured wall seconds |
| --- | --- | --- |
| synthetic-T1 | mean 5.0, count 4 | 0.02084003947675228 |
| synthetic-T2 | mean 9.0, count 2 | 0.020313862711191177 |
| planner-demo-d29f9b204dca3546 | Pending; no run/result | Unmeasured |

Exactly two evidence rows remain **unvalidated**. LLM tokens, GPU seconds and
human minutes are zero; CPU seconds are null/unmeasured. These durations vary
per run and are observations, not cost predictions. Graph sequence is 20;
as-of(18) recovers the supporting assessment and still-visible motivation before
the later correction/withdrawal. Scope `synthetic-comparison` has active baseline
`baseline-1e7543f2-c39e-4f6e-aed3-724bf8ee65af`, selected by transition 18.
The low-limit query reported truncated; the normal fixture view did not.
Separate-process inspection retained all these rows/IDs and the same sequence.

## Reversible assumptions and remaining limitations

- Local Actor roles are trusted assertions, not authenticated users or protection
  against the filesystem/database owner. Operators can create human ideas and
  baseline records; recorders can register notes and append interpretations.
  Neither grants execution approval, evidence review or scientific validation.
- A registration request is identified by its operation ID. Replay returns that
  receipt; another operation attempting the same source proposal conflicts and
  creates no duplicate identity. Immutable original provider/request attribution
  is stored even if additional identical planning requests are recorded later.
- Only joint C synthesis is created in this slice (2–64 distinct pinned E/C
  premises); a general standalone claim authoring/review system is deferred.
  Default motivation timing is retrospective. Creation-context timing requires
  the exact original registered/imported proposal and explicit E reference in its
  envelope and captured context; later idea revisions do not inherit it.
- The first scoped baseline activation expects no predecessor and requires an
  existing E/C motivation. A baseline snapshot alone is inactive. Reversion
  preserves the old transitions; affected dispositions are records, not lifecycle
  actions. No autonomous selection or impact recalculation exists.
- Mutations are bounded at 64 KiB canonical request, 4 KiB per text field and
  64 references. Default read limits are depth 8, 128 nodes, 256 edges and
  256 KiB; hard maxima are 32/1024/2048/1 MiB. Output has a 1 KiB minimum.
  Derivation checks refuse writes beyond 1024 visited revisions/2048 candidates.
  Reads return explicit frontier refs or bounded continuation markers; markers
  are diagnostic boundaries, not a resumable cursor API. Traversal also bounds
  examined incident candidates and queued nodes, and reports exhausted scans.
- As-of does not reconstruct legacy execution status. Current attempts/evidence
  can appear alongside earlier graph assertions with explicit current/unknown
  labels. No evidence truth, causation, independent-experiment count, transitive
  support or final-study conclusion is inferred.
- SQL guards prevent accidental update/delete; exact JSON references are checked
  by the trusted service. This is a single-host local SQLite service, not a
  distributed engine or tamper-resistant archive. Large legacy bodies may be
  omitted under output bounds with truncation rather than silently shortened.
- Graph-aware planning contexts, graph-bound task approvals, fine-grained context
  freshness, formal review/certification, real research, live models, resource
  policy/scheduling, new workers, generated-code isolation, graph rendering and
  monitoring remain deferred. Existing VS-002 context v1 is unchanged.

The following sections preserve the earlier implementation/approval record.

## Historical VS-002 implementation and VS-003 approval record

**At the pre-implementation handoff on 2026-11-10:** VS-003's narrowed Research Graph design (D1–D8) is now **approved for implementation** and recorded as ADR-016–023 in `docs/decisions.md`. The normative scope is `tasks/VS-003.md` (G1–G10), while `tasks/VS-003-proposal.md` preserves non-binding alternatives and extended test ideas. **No VS-003 code, schema v3 migration, tests or research graph has yet been implemented.** VS-005 monitoring/UI and live research remain deferred.

VS-002 implements the human-approved B/B/A/A choices
(ADR-012–015) within `tasks/VS-002.md`. VS-001 remains operational on schema
v1 and migrated v2 databases. This is an offline plumbing demonstration, with
no substantive research, live model calls, automatic authorization, external
spending, network calls, or generated-code execution. No study charter or old
example fixture was edited. The three pre-existing untracked files
`START_HERE_KO.md`, `WORKFLOW.md`, and `docs/roadmap.md` remain untouched.

## Implemented VS-002 behavior

- `docs/interfaces-vs002.md` was written before service implementation. It
  specifies the additive CLI JSON/error contracts, canonicalization, limits,
  migration, audit records, freshness, deduplication and restart behavior.
- `arf/plan_store.py`: explicit, transactional schema v1 → v2 migration;
  known-schema verification; original row/identity preservation; immutable
  contexts, requests, outcomes, proposals, decisions and import receipts;
  foreign keys and uniqueness constraints; consistent complete context export.
- `arf/plan_models.py`: strict bounded UTF-8/JSON validation, duplicate-key and
  nonfinite-number rejection, depth scan before parsing, normalized TaskSpec
  defaults and sorted reference/dependency sets; separate content/action hashes.
- `arf/planner.py`: data-only provider protocol and deterministic versioned mock
  for task, question/hypothesis note, no-action and controlled invalid output.
  It receives immutable context/request/prompt data without a Store, executor,
  tool or approval capability. No provider adapter or dependency was installed.
- `arf/planning.py`: durable request-before-invocation ordering; raw response and
  prompt provenance; idempotent completed-request replay; a separate planner
  lock; explicit review-required outcomes for uncertain/incomplete requests.
  Invalid responses retain bounded diagnostics/raw prefixes and never tasks.
- `arf/plan_policy.py`, `arf/authorization.py`: versioned local policy identity,
  a separate trusted operator decision interface, exact approval binding, strict
  first-approval/import freshness and atomic task/receipt commit. Import replays
  a committed receipt before freshness/policy checks, never execution or retry.
- `arf/cli.py`: `plan migrate/export/propose/list/show/decide/import`. Existing
  VS-001 command arguments/JSON/error behavior remain intact. `arf/store.py`
  accepts v2 and shares only task insertion internals with the importer; the
  fixed worker, executor, claim/finalize and recovery code are unchanged.
- `tests/test_planning.py`: 101 VS-002 acceptance/error cases. The original
  Store-based tests in `test_lifecycle.py` and `test_validation_cli.py` now run
  against both v1 and v2 through `tests/conftest.py` (47 additional regression
  cases). The existing schema assertion checks the assigned version rather than
  hardcoding v1; all previous behavioral assertions remain.

## Verification actually observed

Used the existing offline environment (`source .venv/bin/activate`), without
installing packages or accessing a network. Python 3.12.3, SQLite 3.45.1,
PyYAML 6.0.1 and pytest 9.1.1 remain the available environment.

| Command | Observed result |
| --- | --- |
| `python -m pytest -q` before implementation | 74 passed in 2.71s |
| `python -m pytest -q tests/test_planning.py` initial acceptance suite | 88 passed in 3.05s |
| `python -m pytest -q` with dual-schema regression coverage | 209 passed in 7.85s |
| `python -m pytest -q tests/test_planning.py` after input/binding cases | 100 passed in 3.16s |
| `python -m pytest -q` final source/test suite | **222 passed in 7.97s** |
| `git diff --check` | Exit 0, no whitespace errors |
| Explicit trailing-whitespace check of eight new deliverables | Passed |

Coverage includes populated migration and exact old row/charter preservation,
no-op/unknown/unrelated schemas, simulated migration interruption/rollback,
consistent snapshots during concurrent writes, complete oversized-export refusal,
restart idempotency, approval/import staleness after task/run/recovery/retry
changes, malformed/forged/prohibited responses, SQL immutability and FK bindings,
action deduplication independent of rationale, manual task collisions, receipt
rollback, concurrent import/propose, policy changes, uncertain planner outcomes,
inert ideas, and network-denied mock calls. Failed imported tasks also replay
receipts without retrying, even after policy changes.

### Separate-process offline demonstrations

The extended workflow ran **41 separate CLI processes**, with assertions on
actual exit codes and outputs. Database: `.local/vs002-verified.rao6zhv5/arf.db`.
Local `transcript.json` and `summary.json` alongside it preserve commands,
stdout/stderr and observed outcomes; these local artifacts are Git-ignored.

1. Imported the unchanged demo charter, created/executed the original task in
   v1, captured all historical rows, migrated and checked exact preservation.
   Second migration returned `already_current`.
2. Exported context
   `775c1afad100fab967449ee948982688bfc01723084cbb007ae4b3c1cc8b5258`.
   Propose/replay linked one proposal without execution-state writes. Unapproved
   import exited 1 with `unauthorized`. The proposal was
   `proposal-301409d68cdd76f1992f61d2e8925a2f75e82b1b494c543dec58cb333c906051`.
3. Explicit local-demo approval/replay returned the identical decision. Import
   created one pending task with no run; a separate `run-next` returned
   `{"mean":5.0,"count":4}`. Measured wall times were
   0.024693643674254417 seconds (original task) and 0.02135372720658779 seconds
   (imported task). These are observed durations, not cost predictions.
4. Replayed decisions/receipts across process restarts and after execution;
   no duplicate task/run/evidence was created. A separate manual demo task
   changed state: first import of an approved second candidate exited 1 with
   `stale_context`. Another candidate became stale when that manual task ran;
   first approval exited 1 with `stale_context`. The original receipt still
   replayed successfully.
5. Persisted note/no-action proposals and refused their imports. Final extended
   state: three tasks, three runs, three **unvalidated** observations (original,
   imported, manual freshness fixture); two stale candidates remained inert.
   Recovery reported no interruptions; final run-next returned `no_ready_task`.
   All pre-migration historical rows and the entire study row remained intact.

The exact runnable README demo was also executed from its code block against
fresh `.local/vs002.29CW7Q/arf.db`. Commands ran with immediate failure checks,
except the intentionally denied import, whose failure was explicitly expected.
It finished with two successful tasks and two unvalidated observations,
identical decision/receipt replays, and `no_ready_task`. Its local
`readme-stdout.jsonl` / `readme-stderr.txt` preserve the output.

Both demonstrations retained charter bytes and SHA-256
`d33806961b80d24f57c72792f9511f29432eb25533990db1aa1cd1ea77dd95e9`.
All evidence labels remained `unvalidated`; planner usage is unknown/null and
no live provider costs are claimed. Existing fixed-worker zero usage fields and
null CPU measurements were retained. These demonstrations establish no
scientific progress.

## Reversible defaults and limitations

The implementation follows the approved task without an additional architectural
decision requiring review. The detailed local defaults are normative in
`docs/interfaces-vs002.md`: UTF-8 canonicalization/export v1; depth 32;
1 MiB contexts, 64 KiB raw responses, 4 KiB text, 64 references/dependencies;
hash-derived proposal identity and independent full-TaskSpec action identity.
Task fixtures derive an ID from a context-hash prefix; notes derive their kind
from request identity. Distinct task IDs remain distinct proposals, without
scientific-equivalence detection. Identical decisions replay; conflicting ones
fail. Rejection is terminal and does not require fresh state.

Migration deliberately refuses customized/unknown schemas; it never silently
adopts an unrelated database. Planning artifacts/outcomes are append-only rather
than overwriting lifecycle fields. An interrupted request is review-required;
there is no automatic recall/retry or recovery-clearance API. Invalid/request-only
outcomes are inspectable with the internal request API/SQLite; CLI list/show
cover valid proposals and their provenance. Export fails on oversized complete
state rather than summarizing or dropping evidence. Strict freshness can require
new proposals after unrelated execution changes.

Operator identity is locally asserted, without authentication. The provider
protocol is a capability separation within trusted installed Python code, not an
OS sandbox for arbitrary provider implementations. Host owners remain trusted;
SQL/hash checks do not protect against owners replacing code or databases.
Locks are single-host POSIX advisory locks; use a canonical local DB path and
retain lock files. Existing hardlink/network-filesystem, crash/orphan-child,
exactly-once and database-owner limitations from VS-001 still apply. No general
resource scheduler, untrusted-code sandbox, live provider, autonomous research
loop, strong identity, scientific evidence promotion, or next milestone is
implemented or authorized by this work.

The following history records earlier VS-001 work and pre-implementation
planning statements. Its statements that VS-002 was pending or required design
selection are superseded by ADR-012–015 and the verified implementation above.

---

## Historical VS-001 handoff (before the VS-002 implementation)

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

Deferred human decisions remain unchanged: actual study question/evidence criteria, real budgets and permissions, impact/cost prediction, allocation policy, baseline revision, human working hours, LLM APIs, GPU scheduling and generated-code isolation. The historical VS-002 material above documents the earlier implementation process. At that earlier handoff, VS-002 had been implemented and reviewed and VS-003 was approved but unimplemented. The new VS-003 implementation and actual verification are recorded at the top of this document. There is no live autonomous research deployment.
