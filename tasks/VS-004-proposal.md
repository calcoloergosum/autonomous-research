# VS-004 proposal — Research Decision Loop with recommendation-guided scheduling

**Status: Proposed; not approved for implementation.** Prepared 2026-11-10 against `main` after VS-003.

**Updated design principles (2026-11-10):** Research impact cannot be fully computed or reduced to a universal objective score (ADR-026). Favor reusable recommendations across multiple claims, with selective, cost-aware replanning rather than unconditional recomputation after every execution (ADR-027). These constrain later implementation choices without approving a specific predictor, freshness algorithm or v4 schema.
**Authority:** Design proposal only. It does not authorize schema migration, code changes, substantive research, network/model calls, generated-code execution, expenditure, or VS-005 implementation. **The owner has accepted recommendation-ordered execution, automatic Research Manager priority decisions (V4-13 / ADR-024) and independent verification of all ready work without FIFO fallback (V4-12 / ADR-025).** This does **not** authorize bypassing task registration/approval, triggering an unattended run, or implementing the unapproved scheduler contract. Human review of the new claim/dispatch semantics and decisions in section 15 is required before implementation.

## 1. Purpose and guiding question

Build the first *research-management decision* vertical slice:

> Given a human-owned study objective, a bounded and explicitly qualified view of the current research graph, several possible research actions, imperfect predictions of their contribution and resource needs, what should be investigated **next**, and why should that recommendation change after new evidence or cost observations?

**VS-004 must produce a ranked, provenance-bound recommendation and let a trusted scheduler dispatch already-authorized, eligible tasks in that recommended order.** It must demonstrate the feedback loop from changed research state to updated candidate assessments, an auditable recommendation, and a verified scheduling decision. The recommendation **controls priority among eligible tasks**, not task admission, worker selection, approval, capacity limits, dependency eligibility, or autonomous execution triggering. Legacy FIFO remains a baseline/comparison and existing v1–v3 behavior must not silently change. This does not claim an optimal general research policy.

Accepted project principles:

1. The study charter's ultimate question, success criteria, constraints and permissions are immutable and human-owned.
2. Candidate research directions are open-ended; only a bounded subset is evaluated in each decision.
3. Research impact is **a fallible, contextual scientific judgment**, not an objectively computable quantity. Approximate predictions (including qualitative/unknown assessments), observed evidence, and resource costs remain distinct; no mandatory universal impact score exists.
4. Exploration has value because information can change subsequent decisions; exploitation has value because some actions seem more immediately useful. Neither is an absolute priority.
5. A Research Manager recommends/value-estimates actions and orders *authorized task candidates*; an independent authority still admits executable work; a trusted scheduler selects only already-admitted, runnable work subject to dependencies and capacity.
6. Subsequent discoveries can revise subordinate hypotheses, action priorities and baselines, but cannot rewrite previously observed evidence or the charter.
7. Recommendations must be explainable in terms of pinned inputs and recorded versions, rather than a free-form explanation detached from the decision.

### Explicit non-goals

No live LLM/Codex connector, production research, new worker or human job executor, task auto-approval/import, **unattended execution trigger**, general scheduler rewrite, adaptive GPU execution, automatic baseline activation, formal evidence validation, final-science certification, external data access, dashboard, graph UI, or VS-005 monitoring. **Changing the ordering of already-authorized ready tasks is now in scope.** A deterministic offline scenario is sufficient to exercise the decision architecture, **not** to establish scientific effectiveness.

## 2. Repository facts and boundary to preserve

The current repository implements:

| Existing subsystem | Verified implementation fact | VS-004 implication |
| --- | --- | --- |
| Study charter | Immutable study ID/bytes/SHA and human-defined criteria | Decisions may quote or pin it; never write it |
| VS-001 tasks/runs/evidence | Allowlisted `demo_mean`, FIFO `run-next`, persisted actual run costs and `unvalidated` evidence | Extend only the ready-task *selection order* through a reviewed ranked-dispatch path; do not change allowlist, eligibility, execution, recovery or result semantics |
| VS-002 planning | Deterministic offline mock, request/proposal provenance, exact operator approval/import, strict execution context hash | Advisory candidate is **not** an approved VS-002 `task_candidate`; keep legacy hashes and permissions unchanged |
| VS-003 Research Graph | Typed Q/H/C, T/R/E/B references, motivation and scoped assessment links, append-only revisions, operator baseline transitions | Use graph read interfaces and exact revision/provenance, not graph writes in the decision path |
| VS-003 bounded reads | `read_graph`, `ancestry`, `affected_by`, `as_of`; explicit truncation/frontier | Incomplete graph views are not complete scientific knowledge |
| VS-003 history | Recorded graph assertions have graph sequence; legacy task/run/evidence state in an as-of view is **current/unknown**, not an historical execution snapshot | A decision must pin the independently captured execution state, not pretend a graph sequence reconstructs it |

Current code has **no Research Manager, calibrated Impact/Cost Predictor, Allocation Policy, scheduler capacity model, or real scientific reward signal**. The `demo_mean` result and observed milliseconds of wall time are engineering facts about the fixture, not estimates of real research value. Local graph actor names are assertions, not authenticated people.

Read before implementation: `AGENTS.md`, `docs/project-charter.md`, `docs/architecture.md`, `docs/decisions.md`, `docs/interfaces-vs002.md`, `docs/interfaces-vs003.md`, `docs/current-state.md`, and `tasks/VS-003.md`.

## 3. The proposed decision loop

Separate five conceptual responsibilities. They can be small modules rather than a general agent framework.

1. **Decision context builder (trusted, read-only):** selects an objective-bound graph subgraph, pinned revisions and relevant observations, with completeness/frontier metadata and an exact snapshot identity.
2. **Candidate source:** supplies distinct possible research actions, with origin and target references. The first implementation may use deterministic offline fixtures and persisted existing proposal/graph records; a live model generator is not required.
3. **Impact assessment and cost estimation:** document a fallible, possibly qualitative scientific evaluation of each candidate's relevance, possible consequences and uncertainties, alongside separately modeled resource-cost estimates. Numerical heuristics are optional aids and never the authority for scientific truth.
4. **Allocation policy:** filters unsupported candidates, compares alternatives using a declared policy and scenario constraints, then emits a ranked recommendation (or explicit abstention) with reproducible reasoning. A trusted decision ledger stores the attempt.
5. **Trusted dispatch selector:** binds a selected, fresh recommendation to an actual set of **existing, authorized, pending and dependency-ready** task IDs; revalidates eligibility and capacity under the scheduler's atomic claim transaction; dispatches one selected task using the existing worker path. The decision policy never gets a database task-claim or execution capability.

The decision loop may be:

```text
Immutable study charter
        + Research Graph (selected revision-pinned subgraph)
        + current execution/evidence/cost snapshot
                 |
                 v
      Versioned advisory context
                 |
                 v
    Candidate supply (bounded set)
                 |
                 v
 Reasoned impact assessments / evidence information / cost estimates
                 |
                 v
  Explicit policy -> ranked recommendation / abstain
                 |
                 v
  Immutable decision + predictions + provenance
                 |
                 v
 Trusted dispatcher: verify candidate↔task mapping,
 state, authorization, dependencies, and resources
                 |
                 v
 Atomic claim of highest-ranked ELIGIBLE admitted task
                 |
                 v
 Existing fixed worker lifecycle -> recorded run/evidence
                 |
                 v
      NEW research state -> NEW decision
 (neither old decision nor old observation is overwritten)
```

**Recommendation is permitted to influence dispatch order, but never admission.** No recommendation may call `plan decide`, `plan import`, `task add`, change a graph baseline or manufacture an execution grant. Only a controller-verified reference to an **already-admitted task ID** can participate in scheduling. When `run-next` (or a future explicitly reviewed dispatch entry point) is invoked, the scheduler, not the model, checks authorization, task status, dependency completion, resource limits and selection freshness inside the claim boundary. It must never execute merely because a recommendation was saved. A graph-aware proposal-to-import bridge remains a separate, unapproved feature.

## 4. Defining candidates without creating executable tasks

The decision set is *finite per round*, but the universe of candidate ideas is unbounded over time. Distinguish candidate evaluation from materialization:

- **Question/hypothesis exploration:** investigate or refine a particular Q/H revision, possibly motivated by an E/C. A recommendation can point to the pinned idea, without automatically registering a new graph idea.
- **Experiment proposal:** potential experiment addressing a pinned Q/H/C. It is an advisory specification, not an imported `TaskSpec`; non-`demo_mean` experiments cannot be executed under current worker permissions.
- **Evidence acquisition or replication:** seek additional evidence, narrow uncertainty, check robustness or challenge an interpretation. This need not yield immediate improvement of a baseline.
- **Synthesis/verification action:** compare conflicting assessments or inspect a premise. Scientific validation authority is not granted.
- **No action / defer:** abstain when inputs are insufficient, costs/permissions are unknown or all candidates are ineligible.

**Recommended minimal representation:** a tagged advisory candidate with controller-owned `candidate_id`, `candidate_version`, kind, short description, source/origin record, study/charter binding, target idea revision(s), relevant E/C/B references, declared intended result, prerequisites or constraints, and whether it is only a suggestion. The advisory identity must never be usable as an executable `task_id`, grant or approval token. A candidate may carry an **optional controller-verified mapping** to an existing admitted task (manual trusted insertion or an imported approved VS-002 task), including exact study/task/spec identity; speculative or unimported candidates have no dispatchable mapping. The scheduler must refuse a forged or mismatched mapping rather than interpret candidate text as a task ID.

There are three viable sources to compare:

| Source | Strength | Limitation |
| --- | --- | --- |
| Predefined synthetic fixture candidates | Reproducible, cheap, easy to test | Not genuine autonomous idea generation |
| Existing graph ideas and VS-002 proposals | Preserves prior provenance; demonstrates integration | Existing plan mock offers only `demo_mean` and inert notes, not general experiments |
| Future LLM-based candidate generation | Open-ended novel directions | Untrusted content, model costs, state/context binding and permission controls not yet approved |

**Recommendation for first implementation:** deterministic offline candidate provider plus read-only references to real graph/proposal records. Preserve a provider interface but install no external model adapter. Do not automatically convert an unregistered VS-002 note into a graph node, or an unimported candidate into a task.

Repeated proposals of similar scientific content must not be silently deduplicated by text similarity. Separate exact request replay from scientific equivalence and avoid repeatedly valuing a candidate with no known provenance.

## 5. What is predicted? Impact, information and cost

**The impact of an open-ended research action cannot be completely determined by computation.** Importance depends on scientific framing, novel possibilities, latent consequences, missing evidence and human-defined goals. No finite scoring formula can serve as an authoritative definition of scientific value. A computational heuristic or LLM evaluation may help *inform* a provisional judgment but must not be conflated with ground truth. At minimum, keep the following distinct.

| Dimension | Meaning | Example limitations |
| --- | --- | --- |
| **Research impact assessment** | A reasoned, revisable judgment about possible contributions to unchanged human-owned charter criteria; may be qualitative, contested or unknown | No uniquely computable impact, universal scalar or guaranteed mapping from experimental success to significance; record alternatives, rationale and disagreement |
| **Probability / uncertainty** | Uncertain outcome quality, estimated success likelihood or interval/distribution | Unknown is not zero; an LLM's confidence is not calibrated probability |
| **Expected information value** | Potential to discriminate hypotheses, reduce uncertainty or change future allocation | Information gain is not automatically aligned with final success; repeated correlated tests may be redundant |
| **Resource demand** | Expected required LLM tokens, CPU/GPU seconds, human minutes, elapsed time, money, etc. **as a vector** | Never silently convert dimensions to one score without an approved exchange/constraint policy |
| **Feasibility and reversibility** | Dependencies, available worker type, constraints, evidence/data prerequisites, permission state | “Advisable” is not “authorized to execute” |
| **Opportunity cost / downstream effects** | Effects on other open directions, baseline applicability and possible future follow-ups | Can be speculative and must retain stated assumptions |

An assessment record should bind candidate version, study/charter hash, context ID/hash, exact evidence/graph revision references, **author/evaluator and method/version**, scientific reasoning and assumptions, alternative interpretations, scope, uncertainty, and whether its outputs are qualitative, numerical proxy or unknown. Resource-cost predictions must carry separate units/distributions/missingness and calibration provenance if available. A numeric research-impact proxy is optional, not required for every candidate or an empirical truth label. Record estimates as **claims/predictions about candidates**, not as new Evidence rows or as formally reviewed scientific facts.

Do not force a numerical research-impact score, probability or total ordering when the evidence supports only a partial/qualitative comparison or `unknown`. The manager may report incomparability, contested priority or reasoned defer. Different uncertainty classes (epistemic, noisy observation, missing data) may need distinct treatment; compare the minimal representation required for a decision with more elaborate distribution models.

### 5.1 Judgment and computation play different roles

The Research Manager should combine provisional **scientific judgment** (why a direction might matter, what could falsify it, which assumptions are untested) with computable **constraints and accounting** (task readiness, available resource units, observed costs and versioned policy rules). Arithmetic on explicit scenario proxies can assist comparison, but cannot fully determine a scientific claim's eventual importance.

- Preserve descriptive scientific rationale and evidence links even when no calibrated numerical impact estimate exists.
- Preserve incomparability or disagreement. A policy may apply a disclosed tie-break or seek new evidence rather than fabricate a precise impact number.
- Explain exploration versus exploitation with scientific reasons and possible information gain; a score alone is not an explanation.
- Allow human scientific judgment to challenge subordinate assessments without changing charter/evidence; formal scientific certification remains deferred.
- Synthetic oracle rewards test software behavior only; they do not define real research impact.

### Calibration and attribution limits

Observed wall time from the fixed worker is available; LLM/GPU/human costs are zero only because this particular fixture used none; CPU seconds can be null. Preserve observed zero versus unmeasured/null. Never infer real human work rates or production API spending from these demos.

True research impact is not an observed scalar in the present system. An evidence item might support several hypotheses or have competing interpretations. Do **not** update a “scientific success” parameter as though a task's success status or numerical mean were an impact reward. Real impact inference requires later validated criteria and appropriate attribution. VS-004 may update **synthetic prediction proxies** from an offline scenario with known ground truth, while labeling them as such.

## 6. Exploration versus exploitation: alternatives, not a premature winner

Compare several candidate decision policies.

| Policy | Benefit | Important failure mode |
| --- | --- | --- |
| Fixed FIFO / static ranking | Simple, reproducible baseline | Ignores evidence and uncertainty |
| Greedy predicted contribution per constraint | Easy to inspect | Can prematurely discard informative but uncertain directions; one scalar denominator hides cost trade-offs |
| Uncertainty/optimism (UCB-like heuristic) | Encourages uncertain alternatives | Standard bandit assumptions—stationary arms, comparable repeated rewards—are not naturally satisfied by evolving research hypotheses |
| Posterior sampling (Thompson-like) | Explicit stochastic exploration | Requires meaningful posterior, reproducible seed, reward model and calibration |
| Value of information / approximate lookahead | Represents learning as changing future choices | Expensive and sensitive to unverified world model and the choice of terminal utility |
| Pareto/constrained choice + explicit exploration rule | Retains heterogeneous resources and transparent constraints | Does not produce a unique answer without priorities or tie-breaking rules |

**Tentative minimal recommendation:** provide a replaceable decision-policy seam and two offline reference policies: (a) a non-adaptive ordering baseline and (b) a transparent information-aware comparator on **synthetic scenario-specific utility**, with conservative feasibility filtering and inspectable tie-breaking. This numeric proxy is solely an engineering test mechanism; the architecture must accept fallible, qualitative or incomparable real scientific-impact judgments without coerced scores. Neither reference policy is validated as a generally useful Research Manager. The proposal should not predetermine a universal equation `impact/cost`, a fixed exploration percentage, an optimal bandit algorithm, or fixed resource exchange rates.

The policy must be able to **abstain** and must explain why a high predicted value was not selected (e.g. unknown required resource, disallowed action, uncertain evidence basis or strict constraint). The **existing** execution controller remains authoritative for real task eligibility and safe claims. Decision-stage feasibility checks are predictions, not permission grants or capacity reservations. Ranking must not allow speculative candidates to leap ahead by becoming executable automatically.

## 7. A graph-aware decision context without changing VS-002

ADR-022 explicitly preserved the VS-002 export-v1 contract and deferred graph-aware planning. VS-004 is the earliest appropriate point to *reconsider* a separate **advisory decision context**, not permission to edit the legacy contract.

Compare:

**A. Ephemeral selected graph view with version pins.** No durable context object, but decisions store a canonical copy of inputs. Smallest initial integration; can be hard to deduplicate and inspect independently.

**B. Versioned, immutable decision snapshot, separate from VS-002 contexts (recommended for review).** Store canonical bytes/hash of the *selected* context and manifest: study/charter hash, graph sequence, selected exact Q/H/C revisions, pertinent E/R/T/B references, current execution-state snapshot/hash, query policy/versions, inclusion rules, limits, frontier and completeness flags. This snapshot is **only** decision input, not an approval context.

**C. Extend the existing VS-002 plan export and proposal binding.** Would change hashes/freshness and authorization semantics; **reject for VS-004** absent a separate approval contract.

An observed state change should create a **new** decision snapshot or invalidate a *new* recommendation's assumptions; it must not rewrite old contexts/decisions. An identical saved input may replay an identical decision. The context builder must obtain a consistent read. Exact graph-sequence pin alone is insufficient for legacy mutable task/run statuses: use an explicit captured execution snapshot or an independently pinned execution-context identity, clearly labeling its temporal scope. Do not present an as-of graph view as historical execution state.

The graph reader may truncate at depth/node/edge/output limits, and a selected subgraph may intentionally omit relevant paths. Record: selection rules, visited frontier, omitted categories, truncation, sampling if any, and explicit `completeness: partial`. A policy must not claim knowledge of the entire research portfolio from a partial context. Consider whether a selection that exhausts the output budget should fail, abstain, or remain eligible with degraded confidence; this needs an explicit decision.

Be careful with VS-002's complete export size limit (1 MiB). Do not “solve” it by silently dropping evidence. Keep the decision-context limits separate and versioned, with explicit failure/truncation semantics. Context export itself is read-only with respect to research state.

## 8. Decision records, versions and re-evaluation

**Recommendation:** use a durable append-only advisory decision ledger with one decision attempt per input snapshot/candidate set/policy configuration, plus exact replay receipts.

A decision record needs:

- study ID, charter hash, decision ID and request/idempotency key;
- context hash/manifest and actual capture time, execution snapshot identity and graph sequence;
- complete considered candidate IDs/versions, including filtered, rejected, tied, and **not-selected** options;
- estimator name/version/configuration, each predicted impact/information/cost item, uncertainty and missingness;
- policy name/version, constraints, declared comparison units/weights (if any), deterministic seed for stochastic policies, tie-breaking method;
- recommended candidate(s), rank/order if meaningful, or explicit `abstain` with reason;
- decision explanation linked to the factors that actually influenced selection, not an unverified post-hoc rationale;
- prediction provenance and the trusted controller's **automatic publication** of validated Research Manager priority, distinct from task admission/execution authorization;
- optional later **evaluation link** to the next decision or observed cost/evidence changes; historical decision bytes never mutate.

Prefer a normalized record that is sufficient to recompute the recommendation from saved inputs without needing the current graph or model network access. If offline estimate values are fixture supplied, store the exact synthetic fixture version and seed. An AI-generated rationale is data, not execution authority.

**Re-evaluation:** new graph revisions, evidence, interpretations, cost surprises, candidate arrivals and policy changes are reasons to **check whether replanning is worthwhile**, not unconditional triggers for a full new ranking. A separately versioned Replanning Policy considers a decision's consulted premises, potentially changed priorities, uncertainty and estimated evaluation cost. It can recommend reuse, replan, or defer/refuse with traceable rationale. Record these checks separately from full Research Manager evaluations; do not claim a precise VOI estimate is achievable. Preserve original recommendations and judgments. No automatic background watcher is required.

**Crash behavior:** prepare inputs and persist a request before invoking any uncertain external provider in future; uncertain results require explicit review rather than hidden replays. For the first purely local deterministic policy, an atomic decision/result/receipt transaction and repeatable tests are enough. Do not introduce network calls or indefinite jobs.

### 8.1. Scheduling: automatic priority is not task authorization

**Accepted V4-13:** Research Manager automatically determines/updates priority for existing admitted work, without a person activating each ranking. A trusted controller validates study/charter, versioned recommendation, policy and exact candidate-to-task bindings and persists the effective scheduling preference. Neither ranking nor publication can approve/import a task, start work, retry a failure or choose a worker.

**Accepted V4-12:** The Scheduler must enumerate **all** admitted pending tasks and their real dependency eligibility independently of the ranked subset. It must check whether work is *actually runnable*, not infer an empty ready set from an empty recommendation.

- **No eligible ready tasks:** do not execute; distinguish no pending tasks, dependency blockers and resource/capacity limitations. An unfinished running attempt is a separate busy/recovery state. No-ready does **not** mean the ultimate research question is answered.
- **Ready tasks exist, but ranking is absent/stale/unusable or omits all of them:** request a **bounded** Research Manager re-evaluation or record `decision_unavailable` with a concrete reason. Do not report `no_ready_task`, retry forever, fabricate new work or fall back to FIFO.
- **Ready tasks exist, but Research Manager intentionally defers:** preserve a distinct, reasoned abstention/defer decision. No worker starts; this is not the same as a recommendation-generation failure.
- **Fresh usable recommendation:** intersect its admitted task mappings with the independently verified ready set; skip blocked higher-ranked entries and atomically claim the highest-ranked eligible task using existing execution controls. An unranked ready prerequisite remains discoverable but cannot be run merely because it is ready.

The Controller revalidates versioned recommendation/context and actual task eligibility at claim time. Saved priorities, changes and claims need separate provenance and history. Recommendation publication itself **does not trigger unattended execution**. The research manager may continue proposing new subordinate ideas when no executable task is ready, without thereby granting execution rights.

**Still open for approval:** V4-11 exact dispatch entry point; publication-in-decision-transaction versus separate trusted controller call; single-use versus multi-use ranked decisions; freshness granularity and exact result codes. Existing v1–v3 FIFO behavior stays intact; there is no hidden fallback in the new ranked path.

### 8.2 Multi-claim recommendation reuse and Replanning Policy

**Preferred direction, precise implementation pending (ADR-027):** A versioned Research Manager recommendation may remain the ordering basis across **multiple** separately authorized, independently validated task claims. The original decision context is what the manager *saw at creation*; current applicability is a distinct question. A ranking is not a one-use execution ticket.

- **Hard checks for every claim:** trustworthy decision identity, study/charter/policy binding, task admission and current readiness, worker allowlist, actual capacity, and any critical premise or permission invalidation. A saved order cannot override today's ready set.
- **Change screening, not blanket expiration:** ordinary task completion, new evidence, cost surprises, graph revisions, new candidates and baseline transitions are reviewed for *decision relevance* by a separately versioned Replanning Policy. Record why new evidence was judged relevant or not; never silently ignore it.
- **Structured decisions:** reuse existing recommendation, recompute recommendation, refuse due to unverifiable/critical invalidation, or deliberately defer. Persist the premise references, reason and policy version; no claim of exact value-of-replanning computation.
- **Multiple dispatch receipts:** each committed claim records the recommendation version and reuse/replan evaluation applied to it. Retain the original ordering and all past decisions; completed or blocked entries are filtered through current task status, never deleted from ranking history.
- **Cost-aware assessment:** evaluating whether to replan can itself cost tokens/time. Measure it when available; do not silently assume a free manager or an exact impact benefit. Avoid policy/model execution inside the atomic claim transaction.

Open trade-offs: choosing the consulted read-set, handling incomplete graph views, bounding stale age and re-evaluation work, handling concurrency with newly arrived evidence, and whether approximate scientific judgment should trigger replan even without a computable threshold. These need separate human review.

**Superseded as defaults:** one-claim-per-recommendation and unconditional global graph/execution-hash invalidation. They remain conservative alternatives, not the preferred multi-claim design. Existing VS-002 approval freshness is unaffected.

## 9. Observations, learning and policy updates

Differentiate three layers:

1. **Prediction:** model-estimated impact, probability and multidimensional cost, with uncertainty at time `t`.
2. **Observed outcome:** task/run/evidence/cost and graph changes, with original provenance and validation status. The observed result can be irrelevant or inconclusive for an ultimate question.
3. **Evaluation of prediction:** an explicit rule linking the prediction to an observed quantity, or `not_evaluable` if no trustworthy target exists.

In a synthetic fixture, the scenario may provide a private oracle mapping actions to observations and terminal value; the manager/policy **must not access the oracle in advance**. The generator can reveal only the feedback intended for the next decision. Offline evaluation may compute prediction error, calibration-like diagnostics, value gained per constrained resource, regret versus an oracle and time to a synthetic evidence criterion. These are **synthetic benchmark metrics**, not proof about real research.

For real recorded costs, compare like-for-like units and retain missingness. A future estimator may learn from historical outcomes, but do not train a model on misleading `demo_mean` impact rewards. A learned prediction from one study need not generalize to another: track study/scope and domain shifts before transferring knowledge.

A change in active baseline may enter future decision context and update applicability/priority of candidates, but the manager's **recommendation cannot activate or supersede a baseline**. The existing operator-controlled VS-003 transition remains the sole authority.

## 10. Storage and interface alternatives

A persistent decision/dispatch ledger may warrant **SQLite schema v4**, additive to v3, because immutable judgments, decision history, reuse/re-evaluation assessments, trusted priority publication and dispatch provenance need transactional consistency. The *same recommendation* must be representable in several distinct dispatch receipts; uniqueness constraints prevent repeated run claims, not multiple uses of a decision. Compare at least:

| Alternative | Benefits | Costs |
| --- | --- | --- |
| SQLite v4 with decision contexts/candidates/estimates/decisions/receipts (tentatively recommended) | One local transaction/trust boundary; durable replay; existing DB lifecycle | New migration, schema verification and compatibility testing |
| Sidecar versioned JSON artifacts | Small initial DB change | Dual-write ordering, provenance drift, atomicity and recovery complexity |
| Pure stateless policy/harness | Fastest narrow test | Cannot satisfy durable decision/re-evaluation history without separate persisted output |

If selecting SQLite v4 later, require an **explicit** v3→v4 migration and preserve every v1–v3 row, original bytes/hash, status, decision/graph sequence and old API output. The existing `Store`, `PlanStore`, and `GraphService` currently recognize specific versions: merely creating tables without updating verified schema compatibility would break them. Old binaries may safely refuse v4; downgrade is not promised.

Candidate tables are a *conceptual responsibility list*, not approved DDL: decision contexts; candidate identities/versions and provenance; verified task mappings; **reasoned scientific impact assessments separated from quantitative proxy predictions and resource costs**; policy configurations; ranked decisions/idempotency; controller-published preferences; **replanning checks and reuse decisions**; multiple dispatch receipts referencing the same recommendation; later observation links. Do not silently impose uniqueness of one claim per recommendation. Use constrained typed references and explicit versioned serialized payloads; never let raw JSON reference arbitrary records unchecked.

**Interface recommendation:** a trusted decision service, a narrow ranked-dispatch integration point, and an offline fixture harness. Define an inspectable JSON command/service contract before implementation. Existing v1–v3 CLI behavior must remain stable; whether to extend `run-next` on v4, use an explicit opt-in flag, or introduce a separate dispatch command is a **human review decision**, not something to guess while coding.

## 11. Deterministic offline evaluation scenario

Use a **fictional** multi-round research environment with an immutable objective and an open-ended list of subordinate candidate actions. At least three initially visible candidates differ in predicted contribution, uncertainty, expected information gain and resource requirements. Later feedback introduces new candidates; the current candidate set is not fixed globally.

Minimum scenario (illustrative, not accepted experimental results):

- A: seemingly high immediate contribution, high GPU cost, moderate uncertainty.
- B: low-cost diagnostic which may resolve whether an entire research branch is viable; high information value but uncertain direct contribution.
- C: moderate cost with initially ambiguous applicability; can become attractive after B.
- D: candidate introduced only after feedback, motivated by a new evidence record.

A decision policy may first recommend B for information value, then recommend C or D after relevant feedback. A sound test must also show a counterexample where B **should not** be chosen because its information is redundant, too expensive or unrelated to the charter.

The scenario should include:

- two policies given exactly the same contexts, candidates and constraints;
- a visible record of predictions, missing cost estimates, selected/not-selected candidates and abstentions;
- at least one model misprediction, one informative observation, one inconclusive/contradictory assessment, one cost surprise and one baseline change made **only by a trusted operator fixture**;
- a candidate that is attractive but not executable under existing worker policy, plus a high-ranked task whose dependency is still blocked;
- explicit replay and historical decision/activation/dispatch inspection across a process restart;
- a graph context intentionally truncated, and correct downgrade/abstention rather than unwarranted certainty;
- several decision rounds with controlled revelation of oracle outcomes, ensuring no future information is leaked into earlier inputs;
- automatically published manager priority followed by **explicit existing-worker dispatch requests** in the recommended order, with independent full ready-set discovery, blocked tasks skipped, recorded ties, a truly empty ready set, a ready-but-unranked prerequisite, recommendation failure, deliberate abstention and stale-context cases, while preserving older-schema FIFO behavior.

**Critical acceptance principle:** the chosen action need not match a single canned ID in every scenario. The decision must follow its declared policy from recorded inputs; appropriate choices can differ by assumptions. Include adversarial fixtures where the policy's recommendation remains poor to expose limitations rather than overfit a demonstration.

Keep synthetic oracle outcomes strictly separate from actual `runs`/`evidence`. If real existing `demo_mean` runs are used to test cost plumbing, treat their observed costs as engineering observations only.

## 12. Proposed first implementation boundary

After approval, a minimal VS-004 implementation would include:

1. Offline selected graph/execution-context builder with exact objective binding, revision pins and completeness/truncation manifest, without altering VS-002 export v1.
2. A versioned advisory candidate contract and deterministic fixture supply; no production LLM integration or new executable `TaskSpec` kinds.
3. Estimate records that distinguish candidate contribution, information value and vector-valued resource cost, with unknowns and uncertainty, even if numeric fixture estimates are supplied rather than learned.
4. A non-adaptive comparator and a parameterized information-aware offline comparator using an explicit, synthetic utility/constraint model.
5. An append-only decision ledger, replay and decision inspection with immutable context/candidate/policy versions and abstention.
6. Multi-round tests where a valid recommendation guides **more than one claim** when consulted premises remain applicable, and a genuinely relevant discovery triggers a separately justified new decision. Never force each execution hash change to recompute everything. Preserve existing admission/approval/import, worker safety, dependency and baseline transition authority.
7. A **narrow trusted ranked-dispatch path** that automatically publishes controller-validated manager priority, **independently enumerates all eligible admitted work**, checks ranking and state under the atomic claim boundary, differentiates genuine no-ready / decision failure / deliberate deferral, records the choice, and uses only the existing fixed worker. Compare with legacy FIFO without implicit fallback or a general scheduler rewrite.

What may be **deferred** from this slice even if useful longer-term: online LLM candidate creation; trained/calibrated real predictor; automatic updating of learned model parameters; live event subscriptions; cross-study learning; general budget exchange rates; stochastic posterior sampling; general POMDP/VOI planning; new human queue; multi-resource capacity scheduling beyond the narrow ready-task selector; a general public Research Manager CLI; UI/VS-005 dashboards.

**Important boundary question:** if the user instead wants a genuine empirically learning estimator as the *first* VS-004 goal, the fixture-only estimator plan may be too small. Such a change requires an explicit review of rewards, observations, training/validation splits and permitted spending; do not treat this proposal as approval for that broader scope.

## 13. Proposed acceptance criteria (future, not yet authorized)

| ID | Observable criterion |
| --- | --- |
| D1 — Objective and permissions | Decisions bind original study/charter hash; no path to mutate objective, graph interpretations, authorization/import or worker policy. Only the separate trusted ranked-dispatch path may perform an ordinary authorized pending→running claim. |
| D2 — Open portfolio | A finite context/decision set can gain new candidates later; provenance, duplicate IDs and revision semantics are controlled; no fixed global arm count. |
| D3 — Context fidelity | Exact graph and execution references; snapshots or equivalent saved canonical inputs; intentional omissions/truncation/unknown status explicit; VS-002 export v1 unchanged. |
| D4 — Impact judgment | Qualitative, uncertain, contested or incomparable impact judgments are first-class inputs without compulsory universal numerical scoring. Numerical synthetic proxies and resource-cost vectors remain distinct; no predicted value becomes scientific truth or Evidence. |
| D5 — Policy | A static baseline and one adaptive/reference policy are reproducible from stored inputs/configurations; infeasible/unknown cases produce documented filtering or abstention. |
| D6 — Decision ledger | Selected, unselected, rejected candidates, policy/estimator versions, tie-breaking, actor/source, exact input identity, and reasons are preserved. Exact replay is idempotent; conflicts fail. |
| D7 — Replanning/reuse | One recommendation may guide multiple safe claims while decision-relevant premises remain valid. New evidence and costs prompt a recorded reuse/replan/defer evaluation, not unconditional expiry. Relevant evidence can change ranking; old recommendations, reviews and dispatch receipts remain immutable. |
| D8 — Observation separation | Actual run costs and unvalidated evidence are not conflated with synthetic oracle reward or real scientific impact. Missing observed costs do not become zero. |
| D9 — Authority separation | Recommendation **changes ordering of admitted ready tasks only**, through a trusted activation/claim path; it cannot create/approve/import tasks, bypass dependencies/worker allowlists/capacity, activate baselines, trigger unattended execution or retry. Legacy v1–v3 behavior remains unchanged. |
| D10 — Reliability | Concurrent duplicate/competing decisions, activation conflicts, ranked claims, interrupted writes and restart are tested for atomicity, idempotency and no silent recomputation of uncertain results. Two claimers cannot take one task; the dispatch receipt binds actual task/run identity. |
| D11 — Offline scenario | Multi-round branching/information update, misleading estimates, costs, blocked high-ranked task, unranked but ready prerequisite independently discovered, genuine no-ready state, recommendation failure versus reasoned deferral, truncated context and adverse-policy counterexample; no FIFO fallback. |
| D12 — Compatibility | Whole VS-001/002/003 regression suite and existing offline demos continue; any approved migration is explicit, rollback-safe, and preserves all legacy bytes/hash/IDs. Legacy FIFO interfaces on v1–v3 are unaffected; new v4 dispatch/API semantics are reviewed explicitly. |
| D13 — Ranked dispatch | Two admitted ready tasks ranked opposite FIFO are dispatched in manager order **without human per-round activation**. An authoritative scan distinguishes no ready work from ready-but-unranked/failed decision and explicit deferral. Blocked, unapproved, missing, stale or speculative candidates are never claimed; no fallback. |

Tests must verify **behavior**, not merely the number of cases. A synthetic policy comparison is an engineering sanity check; report its failures too. Do not promise scientifically optimal research allocation or production-ready calibration.

## 14. Risks, debt, and future VS-005 boundary

- **Proxy reward mismatch:** Synthetic utility or information gain can favor actions that do not help the human's real ultimate question. No automated `study_complete` decision.
- **Unsupported beliefs:** A probabilistic-looking estimate may be based only on heuristic/LLM judgment. Preserve source and unknown uncertainty; do not claim calibration.
- **Nonstationarity and interference:** Research arms can appear/disappear, depend on one another, share evidence and alter baselines. Standard independent stationary-bandit results do not automatically transfer.
- **Context selection bias:** Bounded graph snapshots omit edges; record selection policy/frontier and test misleading omissions.
- **Cost incommensurability:** Human minutes, GPUs, model tokens, wall time and dollars are neither exchangeable nor independent; use explicit capacity constraints and reviewed preferences.
- **Incomplete evidence pipeline:** A successful run is not an observed research reward. No general validation or final-evidence sufficiency engine currently exists.
- **Recommendation-to-dispatch boundary:** A suggested action may not be an admitted executable task. A valid ranked decision can affect *which admitted task* runs next but cannot grant permission, bypass dependencies or reserve capacity. Stale rankings, missing candidates, abstentions, starvation and no-rank fallback require explicit handling; never silently execute an unapproved task.
- **Existing context limitations:** VS-002 still has a 1 MiB complete export and strict execution freshness; a new advisory context does not cure those limits or authorize graph-bound task imports.
- **Identity/authentication:** Local actor assertions and deterministic fixtures are not strong access control.
- **Decision history volume:** Storing every candidate and estimate can be costly. Bound batch size, preserve summaries with exact provenance and avoid unbounded result payloads; never silently discard considered options.

VS-005 remains a separate design exercise for **monitoring and visualization**. VS-004 should expose durable read-only decision/prediction/re-evaluation records that a later monitor can consume, but must not predefine dashboards, progress percentages, visual layouts or user interaction patterns.

## 15. Human review decisions (unapproved)

The following are **choices for discussion**, not accepted ADRs or instructions to implement any alternative:

| ID | Question | Initial recommendation | Alternatives and consequence |
| --- | --- | --- | --- |
| V4-1 | What is the smallest decision slice? | Research Decision Loop **plus a narrow trusted recommendation-ordered dispatch path** for admitted ready tasks | Advisory-only ranker (no longer meets owner direction); full autonomous loop (too broad) |
| V4-2 | What is the candidate identity/lifecycle? | New versioned advisory candidate bound to Q/H/C/E/B and original proposal provenance | Reuse VS-002 proposal IDs directly (confuses recommendation with approval); graph nodes only (cannot represent unregistered actions) |
| V4-3 | How are impact judgments and costs represented? | **ADR-026:** scientific impact is a fallible, reasoned judgment (including qualitative/unknown/incomparable) distinct from synthetic information-value proxies and resource-cost vectors | A universal impact/reward scalar is not justified; full probabilistic science model is unapproved |
| V4-4 | Which offline policies? | Fixed baseline plus a versioned **synthetic** information-aware comparator; the real manager must preserve scientific reasoning without mandatory score maximization | UCB, Thompson, VOI and global scoring demand unverified priors/rewards |
| V4-5 | What is the decision context? | Separate pinned, versioned advisory context; legacy VS-002 v1 unchanged | Ephemeral context with embedded ledger input; extend VS-002 export (breaks existing contract) |
| V4-6 | Where is history stored? | Consider additive SQLite v4 for immutable decision contexts/estimates/receipts | Sidecar artifacts (dual-write risk); stateless tests (insufficient durable audit) |
| V4-7 | When should feedback trigger a new decision? | **ADR-027 preferred direction:** allow multi-claim ranking reuse, with a bounded Replanning Policy weighing decision-relevant changes and cost; explicit replan/reuse/defer outcomes | Mandatory per-run recomputation is costly; ignoring new evidence is unsafe |
| V4-8 | What is the interface/authority? | Internal research decision manager + advisory ledger + **trusted scheduling adapter**; authorization/import remains separate | Direct model-to-dispatch authority (unsafe); graph-bound executable proposal/automation (requires new approval contract) |
| V4-9 | How to handle partial contexts/unknown costs? | Explicit omissions; allow qualified comparison or abstain under a declared policy, no silent imputations | Strict fail on every partial input (simpler but less useful); silently ignore missing data (unsafe) |
| V4-10 | What constitutes convincing validation? | Deterministic multi-round synthetic benchmarks with counterexamples plus preservation of old tests | Claims of real scientific effectiveness from fixture metrics (reject) |
| V4-11 | Which task dispatch interface is authorized? | New v4 ranked dispatch with **automatic validated manager preference** and original v1–v3 `run-next` preserved | Exact interface and v4 legacy FIFO behavior remain for review |
| V4-12 **ACCEPTED** | How to distinguish no-ready from no-ranking? | **ADR-025:** independently scan all ready work; truly none means no execution, ready-but-unranked means bounded re-evaluation or recorded decision failure, explicit deferral has its own reason. No FIFO fallback | Exact error codes and bounded reevaluation interface remain open |
| V4-13 **ACCEPTED** | Who sets execution priority? | **ADR-024:** Research Manager automatically determines order; trusted controller verifies/publishes it, with no per-round human activation and no new task admission/worker authority | Publication atomicity, head conflicts and validity lifetime remain open |

Before approval, decide which candidate-generation, estimator and policy elements are actual algorithms versus synthetic seams. **V4-12/V4-13 remain accepted; ADR-026 establishes impact as fallible scientific judgment and ADR-027 favors reusable ranking with selective replanning.** The precise assessment interfaces, Replanning Policy, validity premises and v4 dispatch APIs still require review. The goal is to exercise one complete recommendation-to-authorized-dispatch-and-feedback loop without prematurely making the system's research policy a hard-coded architectural fact.

### Suggested next step

Review remaining V4 choices with the human owner, carrying forward V4-12/V4-13 (ADR-024–025). Then finalize the normative `tasks/VS-004.md` and an internal interface contract before asking Codex to implement. The present proposal must **not** be treated as authorization for implementation. The owner's V4-12/V4-13, impact and recommendation-reuse directions are recorded here. Concrete assessment contracts, selective validity checks, replanning budgets, scheduler API and publication mechanics still require review.
