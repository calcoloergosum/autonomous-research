# VS-004 proposal — Research Decision Loop with recommendation-guided scheduling

**Status: Proposed; not approved for implementation.** Prepared 2026-11-10 against `main` after VS-003.
**Authority:** Design proposal only. It does not authorize schema migration, code changes, substantive research, network/model calls, generated-code execution, expenditure, or VS-005 implementation. **The project owner has requested recommendation-guided execution order in VS-004, superseding the earlier advisory-only boundary.** This does **not** authorize bypassing task registration/approval, triggering an unattended run, or implementing the unapproved scheduler contract. Human review of the new claim/dispatch semantics and decisions in section 15 is required before implementation.

## 1. Purpose and guiding question

Build the first *research-management decision* vertical slice:

> Given a human-owned study objective, a bounded and explicitly qualified view of the current research graph, several possible research actions, imperfect predictions of their contribution and resource needs, what should be investigated **next**, and why should that recommendation change after new evidence or cost observations?

**VS-004 must produce a ranked, provenance-bound recommendation and let a trusted scheduler dispatch already-authorized, eligible tasks in that recommended order.** It must demonstrate the feedback loop from changed research state to updated candidate assessments, an auditable recommendation, and a verified scheduling decision. The recommendation **controls priority among eligible tasks**, not task admission, worker selection, approval, capacity limits, dependency eligibility, or autonomous execution triggering. Legacy FIFO remains a baseline/comparison and existing v1–v3 behavior must not silently change. This does not claim an optimal general research policy.

Accepted project principles:

1. The study charter's ultimate question, success criteria, constraints and permissions are immutable and human-owned.
2. Candidate research directions are open-ended; only a bounded subset is evaluated in each decision.
3. Expected impact, expected evidence acquisition cost and uncertainty are **predictions**, not observations or validated scientific results.
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
3. **Estimator:** predicts effects and costs of each *candidate action*, recording uncertainty, assumptions, information provenance, estimator version and any unknown quantities.
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
 Impact / evidence-value / cost predictions
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

A single scalar “importance” score is not a scientific primitive. At minimum, keep the following distinct.

| Dimension | Meaning | Example limitations |
| --- | --- | --- |
| **Expected research contribution** | Predicted change in useful progress toward *unchanged charter criteria* if an action succeeds | No universally meaningful normalized progress percentage; often only ordinal or scenario-specific proxy |
| **Probability / uncertainty** | Uncertain outcome quality, estimated success likelihood or interval/distribution | Unknown is not zero; an LLM's confidence is not calibrated probability |
| **Expected information value** | Potential to discriminate hypotheses, reduce uncertainty or change future allocation | Information gain is not automatically aligned with final success; repeated correlated tests may be redundant |
| **Resource demand** | Expected required LLM tokens, CPU/GPU seconds, human minutes, elapsed time, money, etc. **as a vector** | Never silently convert dimensions to one score without an approved exchange/constraint policy |
| **Feasibility and reversibility** | Dependencies, available worker type, constraints, evidence/data prerequisites, permission state | “Advisable” is not “authorized to execute” |
| **Opportunity cost / downstream effects** | Effects on other open directions, baseline applicability and possible future follow-ups | Can be speculative and must retain stated assumptions |

An estimate record should bind: candidate version, study/charter hash, context ID/hash, exact evidence/graph revision references, method/model and version, estimated distribution or interval with units, calibration provenance if available, unknown-field indicators, and separate assumptions. Record estimates as **claims/predictions about candidates**, not as new Evidence rows or as formally reviewed scientific facts.

Do not force numerical probabilities when the source supports only qualitative ranking or an `unknown` value. Different uncertainty classes (epistemic, noisy observation, missing data) may need distinct treatment; compare the minimal representation required for a decision with more elaborate distribution models.

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

**Tentative minimal recommendation:** implement only a **policy seam** and two deterministic offline reference policies: (a) a non-adaptive baseline such as fixed ranking/FIFO and (b) a simple, explicitly parameterized information-aware policy. The second must use an artificial scenario utility, conservative feasibility filters and inspectable tie-breaking. It is a test mechanism, **not** a validated Research Manager algorithm. The proposal should not predetermine a universal equation `impact/cost`, a fixed exploration percentage, an optimal bandit algorithm, or fixed resource exchange rates.

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
- advisory prediction provenance, plus whether the ranked decision was later **activated as a scheduling preference** by a separately trusted controller action; activation is not task authorization;
- optional later **evaluation link** to the next decision or observed cost/evidence changes; historical decision bytes never mutate.

Prefer a normalized record that is sufficient to recompute the recommendation from saved inputs without needing the current graph or model network access. If offline estimate values are fixture supplied, store the exact synthetic fixture version and seed. An AI-generated rationale is data, not execution authority.

**Re-evaluation:** a new graph revision, new evidence, revised interpretation, changed cost observation, candidate arrival or changed policy can prompt a new decision. Preserve old estimates and decisions. A new decision can reference which prior assumptions changed, but do not claim that sequential recommendation changes prove a beneficial causal effect. No continuous background loop or scheduled watcher is required in VS-004; explicit local calls suffice.

**Crash behavior:** prepare inputs and persist a request before invoking any uncertain external provider in future; uncertain results require explicit review rather than hidden replays. For the first purely local deterministic policy, an atomic decision/result/receipt transaction and repeatable tests are enough. Do not introduce network calls or indefinite jobs.

### 8.1. Scheduling: priority selection is not task authorization

**New VS-004 scope requested by the owner:** replace FIFO with recommendation ordering *for eligible, already-admitted tasks* while keeping the existing fixed worker, transactional claim, retry and recovery invariants.

Recommended separation:

1. **Recommendation:** immutable ranked candidate IDs (including unselected/ineligible candidates), tied to a context, policy and exact verified mappings to existing TaskSpecs where such mappings exist. A recommendation may also explicitly abstain.
2. **Activation:** the trusted local operator/controller chooses which decision version is an active scheduling preference (or, if explicitly approved later, a delegated policy may activate it). Record who activated which decision, on what state, with an immutable receipt. An untrusted planner response must not set its own scheduling authority.
3. **Selection:** the scheduler enumerates *pending, dependency-ready, admitted* tasks, intersects with the active rank list, and atomically claims the highest-ranked eligible task. A highly ranked blocked task is **skipped, not run**. Stable tie-breaking and deterministic behavior are required.
4. **Feedback:** the selected task's existing run/evidence history and measured costs become inputs to the next explicit decision; executing one task does not rewrite past rankings.

**Freshness race:** the recommended order may have been computed before a task became blocked, completed or retried. Check recommendation binding and actual current task eligibility in the same claim transaction. The system must record whether it used a fresh recommendation, skipped stale/blocked ranked entries, or refused an unsafe dispatch. Recommendation activation does not imply uninterrupted validity. A distinct historical dispatch receipt should link recommendation version, chosen task/run, scheduler version, skipped entries and the effective eligibility/constraint state. Do not duplicate execution facts as scientific evidence.

**Unranked eligible tasks, absent or stale decisions, abstention, and newly created ready tasks** need an explicit policy. Two reasonable choices are:

- **Strict recommended-order mode (tentative preference):** when no validated applicable ranking exists, return a non-executing `needs_decision`/equivalent result rather than silently reverting to FIFO. Unranked tasks do not dispatch until ranked or a trusted override is recorded.
- **Hybrid fallback mode:** rank all known eligible tasks first, then FIFO among unranked tasks; if there is no usable ranking, fall back to FIFO with a visible fallback reason. Maintains liveness but weakens the user's expectation that decisions control dispatch.

Do **not** select either compatibility-impacting fallback implicitly. Preserve the v1–v3 legacy CLI and `run-next` behavior. The VS-004 implementation contract must decide whether the new ranked selection is explicitly opt-in on v4, the default on v4, or exposed through a new dispatch verb; detail how the older interface reports `no_ready_task` versus `needs_decision`. The choice affects public APIs, readiness behavior, and regression tests and must be approved before coding.

The first slice can still use deterministic mock rankings and a trusted activation fixture; no live Research Manager, automatic approvals, resource optimization or unattended worker trigger is required. **It must nevertheless exercise real ranked task claims and fixed-worker execution** so selection ordering is not merely simulated.

## 9. Observations, learning and policy updates

Differentiate three layers:

1. **Prediction:** model-estimated impact, probability and multidimensional cost, with uncertainty at time `t`.
2. **Observed outcome:** task/run/evidence/cost and graph changes, with original provenance and validation status. The observed result can be irrelevant or inconclusive for an ultimate question.
3. **Evaluation of prediction:** an explicit rule linking the prediction to an observed quantity, or `not_evaluable` if no trustworthy target exists.

In a synthetic fixture, the scenario may provide a private oracle mapping actions to observations and terminal value; the manager/policy **must not access the oracle in advance**. The generator can reveal only the feedback intended for the next decision. Offline evaluation may compute prediction error, calibration-like diagnostics, value gained per constrained resource, regret versus an oracle and time to a synthetic evidence criterion. These are **synthetic benchmark metrics**, not proof about real research.

For real recorded costs, compare like-for-like units and retain missingness. A future estimator may learn from historical outcomes, but do not train a model on misleading `demo_mean` impact rewards. A learned prediction from one study need not generalize to another: track study/scope and domain shifts before transferring knowledge.

A change in active baseline may enter future decision context and update applicability/priority of candidates, but the manager's **recommendation cannot activate or supersede a baseline**. The existing operator-controlled VS-003 transition remains the sole authority.

## 10. Storage and interface alternatives

A persistent decision/dispatch ledger may warrant **SQLite schema v4**, additive to v3, because these are study-scoped immutable artifacts that need transactional history, trusted activation and dispatch provenance. Compare at least:

| Alternative | Benefits | Costs |
| --- | --- | --- |
| SQLite v4 with decision contexts/candidates/estimates/decisions/receipts (tentatively recommended) | One local transaction/trust boundary; durable replay; existing DB lifecycle | New migration, schema verification and compatibility testing |
| Sidecar versioned JSON artifacts | Small initial DB change | Dual-write ordering, provenance drift, atomicity and recovery complexity |
| Pure stateless policy/harness | Fastest narrow test | Cannot satisfy durable decision/re-evaluation history without separate persisted output |

If selecting SQLite v4 later, require an **explicit** v3→v4 migration and preserve every v1–v3 row, original bytes/hash, status, decision/graph sequence and old API output. The existing `Store`, `PlanStore`, and `GraphService` currently recognize specific versions: merely creating tables without updating verified schema compatibility would break them. Old binaries may safely refuse v4; downgrade is not promised.

Candidate tables are a *conceptual responsibility list*, not approved DDL: decision contexts; candidate definitions/versions and provenance; verified task mappings; predictor configurations; immutable candidate estimates; policy configurations; decision outcomes and idempotency receipts; trusted activation records; dispatch selections/receipts with task/run linkage; links to later observations/evaluations. Use constrained typed references and explicit versioned serialized payloads; never let raw JSON reference arbitrary records unchecked.

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
- a trusted activation of the ranked decision followed by **actual existing-worker claims in the recommended order**, with blocked tasks skipped, recorded tie-breaking, one unranked-task case and one stale/abstention case, while preserving legacy FIFO behavior in an older-schema fixture.

**Critical acceptance principle:** the chosen action need not match a single canned ID in every scenario. The decision must follow its declared policy from recorded inputs; appropriate choices can differ by assumptions. Include adversarial fixtures where the policy's recommendation remains poor to expose limitations rather than overfit a demonstration.

Keep synthetic oracle outcomes strictly separate from actual `runs`/`evidence`. If real existing `demo_mean` runs are used to test cost plumbing, treat their observed costs as engineering observations only.

## 12. Proposed first implementation boundary

After approval, a minimal VS-004 implementation would include:

1. Offline selected graph/execution-context builder with exact objective binding, revision pins and completeness/truncation manifest, without altering VS-002 export v1.
2. A versioned advisory candidate contract and deterministic fixture supply; no production LLM integration or new executable `TaskSpec` kinds.
3. Estimate records that distinguish candidate contribution, information value and vector-valued resource cost, with unknowns and uncertainty, even if numeric fixture estimates are supplied rather than learned.
4. A non-adaptive comparator and a parameterized information-aware offline comparator using an explicit, synthetic utility/constraint model.
5. An append-only decision ledger, replay and decision inspection with immutable context/candidate/policy versions and abstention.
6. Explicit multi-round re-evaluation with changed input records, offline scenario tests and regression checks proving **zero changes to admission/approval/import, worker execution safety, dependencies or baseline transition authority**.
7. A **narrow trusted ranked-dispatch path** that activates a versioned recommendation, rechecks ready tasks under the atomic claim boundary, selects the highest-ranked eligible admitted task, records the actual choice, and executes solely via the existing fixed worker. Compare its selections against the legacy FIFO baseline; do not replace the resource scheduler wholesale.

What may be **deferred** from this slice even if useful longer-term: online LLM candidate creation; trained/calibrated real predictor; automatic updating of learned model parameters; live event subscriptions; cross-study learning; general budget exchange rates; stochastic posterior sampling; general POMDP/VOI planning; new human queue; multi-resource capacity scheduling beyond the narrow ready-task selector; a general public Research Manager CLI; UI/VS-005 dashboards.

**Important boundary question:** if the user instead wants a genuine empirically learning estimator as the *first* VS-004 goal, the fixture-only estimator plan may be too small. Such a change requires an explicit review of rewards, observations, training/validation splits and permitted spending; do not treat this proposal as approval for that broader scope.

## 13. Proposed acceptance criteria (future, not yet authorized)

| ID | Observable criterion |
| --- | --- |
| D1 — Objective and permissions | Decisions bind original study/charter hash; no path to mutate objective, graph interpretations, authorization/import or worker policy. Only the separate trusted ranked-dispatch path may perform an ordinary authorized pending→running claim. |
| D2 — Open portfolio | A finite context/decision set can gain new candidates later; provenance, duplicate IDs and revision semantics are controlled; no fixed global arm count. |
| D3 — Context fidelity | Exact graph and execution references; snapshots or equivalent saved canonical inputs; intentional omissions/truncation/unknown status explicit; VS-002 export v1 unchanged. |
| D4 — Predictions | Estimated contribution, information value and resource-vector cost are distinguishable, with uncertainty/missing values; no prediction is inserted into Evidence or labeled validated. |
| D5 — Policy | A static baseline and one adaptive/reference policy are reproducible from stored inputs/configurations; infeasible/unknown cases produce documented filtering or abstention. |
| D6 — Decision ledger | Selected, unselected, rejected candidates, policy/estimator versions, tie-breaking, actor/source, exact input identity, and reasons are preserved. Exact replay is idempotent; conflicts fail. |
| D7 — Re-evaluation | New feedback yields a new decision, can change ranking, never edits earlier records; changing just a policy/configuration is distinguishable from new evidence. |
| D8 — Observation separation | Actual run costs and unvalidated evidence are not conflated with synthetic oracle reward or real scientific impact. Missing observed costs do not become zero. |
| D9 — Authority separation | Recommendation **changes ordering of admitted ready tasks only**, through a trusted activation/claim path; it cannot create/approve/import tasks, bypass dependencies/worker allowlists/capacity, activate baselines, trigger unattended execution or retry. Legacy v1–v3 behavior remains unchanged. |
| D10 — Reliability | Concurrent duplicate/competing decisions, activation conflicts, ranked claims, interrupted writes and restart are tested for atomicity, idempotency and no silent recomputation of uncertain results. Two claimers cannot take one task; the dispatch receipt binds actual task/run identity. |
| D11 — Offline scenario | Multi-round branching/information update, misleading estimates, cost surprises, an ineligible candidate, blocked high-ranked task, truncated context, abstention, explicit scheduling fallback behavior and adverse-policy counterexample all tested deterministically. |
| D12 — Compatibility | Whole VS-001/002/003 regression suite and existing offline demos continue; any approved migration is explicit, rollback-safe, and preserves all legacy bytes/hash/IDs. Legacy FIFO interfaces on v1–v3 are unaffected; new v4 dispatch/API semantics are reviewed explicitly. |
| D13 — Ranked dispatch | Given two or more already-admitted ready tasks with ranking opposite to FIFO, an explicit new dispatch call executes the highest-ranked eligible task using the original worker and records the choice. Blocked, failed, absent, stale, wrong-study, unapproved and speculative candidates cannot be claimed via ranking. Absent/stale/partial-ranking behavior follows a reviewed explicit rule, never an undocumented fallback. |

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
| V4-3 | How are predictions represented? | Contribution, information value and cost **vector**, with missingness/uncertainty and explicit units | One scalar reward (premature); full probabilistic world model (heavy) |
| V4-4 | Which offline policies? | Fixed baseline + minimal information-aware policy seam; no universal scoring rule | UCB, Thompson sampling, multi-step VOI; require nontrivial assumptions and calibration |
| V4-5 | What is the decision context? | Separate pinned, versioned advisory context; legacy VS-002 v1 unchanged | Ephemeral context with embedded ledger input; extend VS-002 export (breaks existing contract) |
| V4-6 | Where is history stored? | Consider additive SQLite v4 for immutable decision contexts/estimates/receipts | Sidecar artifacts (dual-write risk); stateless tests (insufficient durable audit) |
| V4-7 | When does feedback update predictions? | Explicit new decision round with versioned updates from observations and **synthetic** scenario rewards only | Live autonomous retraining or event loop (defer until real impact target and permissions exist) |
| V4-8 | What is the interface/authority? | Internal research decision manager + advisory ledger + **trusted scheduling adapter**; authorization/import remains separate | Direct model-to-dispatch authority (unsafe); graph-bound executable proposal/automation (requires new approval contract) |
| V4-9 | How to handle partial contexts/unknown costs? | Explicit omissions; allow qualified comparison or abstain under a declared policy, no silent imputations | Strict fail on every partial input (simpler but less useful); silently ignore missing data (unsafe) |
| V4-10 | What constitutes convincing validation? | Deterministic multi-round synthetic benchmarks with counterexamples plus preservation of old tests | Claims of real scientific effectiveness from fixture metrics (reject) |
| V4-11 | Which task dispatch interface is authorized? | Ranked dispatch available only on v4 after explicit activation, with original v1–v3 `run-next` behavior preserved | Changing existing `run-next` default across all schemas would break compatibility; a separate command/flag adds an interface |
| V4-12 | What happens with no usable ranking, blocked/ranked tasks, or abstention? | Strict non-execution when no valid ranking; skip blocked candidates; no silent FIFO fallback | Hybrid FIFO tail/fallback aids liveness but can undermine recommendation order; explicit operator override is another option |
| V4-13 | Who may activate a recommendation for scheduling? | Trusted local operator/controller only, append-only activation and dispatch audit | Immediate auto-activation by an untrusted manager would weaken execution sequencing authority |

Before approval, decide which aspects of *candidate proposal generation*, *predictor update* and *policy comparison* must be real algorithms versus deliberately simple synthetic seams. **Also settle V4-11–V4-13 explicitly because changing dispatch ordering affects public behavior, execution authority and liveness.** The goal is to exercise one complete recommendation-to-authorized-dispatch-and-feedback loop without prematurely making the system's research policy a hard-coded architectural fact.

### Suggested next step

Review V4-1–V4-13 with the human owner. Then turn approved choices into explicit ADRs and a **smaller normative** `tasks/VS-004.md` plus internal interface contract, and only then instruct Codex to implement. The present proposal must **not** be treated as authorization for implementation. The owner's new scheduling direction is recorded here, but the exact API, stale-ranking policy, fallback and activation authority still require review.
