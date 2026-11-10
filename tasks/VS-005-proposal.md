# VS-005 proposal — Research Observatory (local, read-only, live)

**Status: REVISED PROPOSAL FOR HUMAN REVIEW; NOT APPROVED FOR IMPLEMENTATION.**
Prepared 2026-11-10 against `main` commit `48d2412f26497f500e9de75514add8a78da9c6f3` following the verified VS-004 / ADR-030 offline first-ranking follow-up.
**Human-selected product direction:** VS-005 is **observation-only**, uses a **local browser UI**, and **automatically refreshes**. Latest refinement: prioritize **one complete question-to-evidence user journey** rather than deliver a large multi-dashboard system or predefine nine public APIs. All implementation details and new public interfaces remain unapproved.
**Related contracts:** [VS-003 graph](../docs/interfaces-vs003.md), [VS-004 decision ledger](../docs/interfaces-vs004.md), [current implementation](../docs/current-state.md), [architecture decisions](../docs/decisions.md).
**Authority:** Design only. Do not add application code, DB tables, migrations, approved ADRs, workers, network/model access, executable actions, scientific validation or VS-005 tests under this proposal.

## 1. Product objective: understand one decision end-to-end

> When an experiment has run, can a researcher understand **why that task was selected over available alternatives, what scientific claims and assumptions were recorded, which evidence was actually observed, and why a later decision changed or stayed the same**—in one uninterrupted browser journey?

This is not a generic operations dashboard. The first VS-005 must demonstrate one coherent **decision audit**, backed entirely by existing ARF records. Research Map, Decision Timeline and Execution remain useful *future lenses*, but they are **not three mandatory complete screens** for the first implementation.

The first user's path is:

1. Open Observatory on a supported v4 database. Read the **current admitted task state** and the **latest recorded dispatches**.
2. Select a real task/dispatch (for example the offline fixture's Task B). The **same selection** persists through the rest of the journey.
3. Follow the recorded chain **dispatch → recommendation membership → reasoning / assumptions / excluded alternatives → saved Decision Context**. Show actual source IDs, not synthesized natural-language causality.
4. Inspect the chosen task's run and **unvalidated Evidence**, with actual observed cost separated from synthetic proxy and predicted cost.
5. Open the **decision checkpoint** behind the selected dispatch; compare with a later decision, displaying what genuinely changed (candidate membership/order, feedback, interpretation, selected context scope) and what cannot safely be compared.
6. Observe a trusted *separate process* change the underlying DB. The live shell updates **without stealing focus**; a pinned checkpoint stays pinned.

**Success is this end-to-end understanding, not feature count.** Every visible explanation must be traceable to persisted IDs, a clearly attributed judgment or an explicit `not_recorded`/`unknown` label. Neither task throughput nor graph growth is a universal research-progress score.

**First-slice design constraints:** a minimal single-page interface, a stable Inspector, a short recent-execution list, a small **Why? trace**, two-checkpoint comparison, and safe auto-refresh. Search, a general interactive world graph, advanced charts, a full-screen execution board and flexible timeline browsing are extensions only after the user journey is validated.

## 2. A small single-page Research Explorer

### 2.1 Initial visible regions

Start with only **three coordinated regions** rather than complete Map/Decisions/Execution pages:

- **Recent activity / selection rail:** current admitted tasks and latest recorded dispatches, with short `claimed`, `no_ready_task`, `needs_decision` and `deferred` distinctions. Its purpose is to answer "what happened?" and offer a selectable entry point—not to build a full scheduler dashboard.
- **Why? / evidence trace:** a compact sequence of grounded, clickable references (Task ↔ candidate binding ↔ decision membership ↔ decision context ↔ run/Evidence as available). Show selected vs excluded candidate decisions, recorded assumptions, policy name and whether scores are `synthetic_proxy`. This is the main content, not a decorative network.
- **Persistent Inspector + Checkpoints:** the selected record's original fields/provenance and an optional comparison with one later/earlier Decision. Show uncertainty, incomplete data, temporally qualified status and explicit unavailable links.

Recommended layout: a modest left list, a main center trace, and a contextual Inspector on the right for desktop. On narrow screens the same data may stack, without introducing a separate navigation architecture. One explicit `Live / Pinned checkpoint` control is enough for the initial temporal UI.

### 2.2 One shared selection, not a universal navigation framework

The minimal UI selection is a typed, bounded reference such as `{kind, id, revision?}`. A chosen Task or Dispatch stays selected during live refresh, Inspector expansion and checkpoint comparison. Preserve graph/trace expansion and scroll position where reasonable. If a related record is missing, retain the selection and explain the missing link rather than silently navigate away.

The first prototype should **not** require a dynamic full-graph layout engine, three fully implemented lenses, broad fuzzy search, global time slider or persistent UI preference store. For a local motivated neighborhood, a small *list or fixed DAG trace with explicit link kinds* is sufficient. General Research Map/Focus Mode with expandable typed edges is a deliberate follow-up, once this trace proves useful.

**User-centered hierarchy:** `What happened?` → `Why was this prioritized?` → `What did it rely on?` → `What changed?`. The user should not have to mentally join three dashboards to answer these.

### 2.3 Scope reserved for subsequent iterations

Once the first flow is validated, expand toward the originally proposed three lenses **Map / Decisions / Execution**, integrated with one selection/Inspector, then a richer Focus Mode, full event rail and search. Do not implement those views merely because they were shown in early sketches.

Treat scientific/intention graph edges, factual execution edges and operator baseline transitions as **different meanings** even in the small trace. A recorded motive is not causal proof, an unreviewed assessment is not validation, and an unattested path is `not_recorded`—not guessed.

## 3. Data already available and its limits

### 3.1 Existing verified sources

| Question | Source of truth | Important boundary |
| --- | --- | --- |
| Immutable study objective | `studies` + original source/hash | Never reinterpret or edit it in the viewer |
| Research relations / reasons | v3/v4 Research Graph, `read_graph` / `traverse` / `at_seq` | Q/H/C revisions; `ADDRESSES`, `INVESTIGATES`, `MOTIVATED_BY`, `DERIVED_FROM`, `ASSESSES`, `USES_BASELINE`; unreviewed vs withdrawn |
| Execution relations | SQL-derived `DEPENDS_ON`, `ATTEMPT_OF`, `PRODUCES`; operator baseline `SUPERSEDES` | Derived facts are not editable graph claims; graph-as-of still uses **current** T/R/E bodies |
| Current tasks, blockers, runs, Evidence | v1 execution tables | Task status is current mutable state; runs/Evidence hold immutable event history; Evidence remains `unvalidated` |
| Considered / ranked / excluded candidates | v4 `research_decisions` + `decision_members` | Numeric information/direct values are synthetic fixture scores; no objective scientific impact |
| Original decision-time state | v4 `decision_contexts` | Exact saved selected graph + execution snapshot; intentionally partial or truncated view must stay qualified |
| Publication and re-use/re-plan | v4 `decision_publications`, `decision_assessments` | One ranking can guide multiple claims; a relevance assessment is a recorded *judgment*, not verified scientific truth |
| Actual selected/blocked task | v4 `decision_dispatches` and ordinary run | Distinguish `claimed`, `no_ready_task`, `needs_decision`, `deferred`; recorded selection is not completed scientific progress |

Graph roles currently include `O, Q, H, C, T, R, E, B` and bounded query limits; existing graph output explicitly says `historical_execution_state: unknown`. Current data is single-study per DB, one local worker at a time. The VS-004 graph/execution decision context has a 2 MiB cap and embeds the complete unchanged v1 execution export (1 MiB cap). Do not silently exceed or reconstruct outside those documented bounds.

**P2 note:** the current v4 scheduler may return `needs_decision / unranked_ready_task` if an admitted ready task is outside the recommendation. A subsequent user decision favors partial ranking, but that behavioral change has not been merged here. VS-005 must display the *stored decision and dispatch facts*, not invent a policy or mutate scheduling behavior.

### 3.2 Temporal truth: two UI modes, three underlying meanings

| Mode | Show | Explicit prohibition |
| --- | --- | --- |
| **Live** | One consistent read of current graph, task/statuses, latest saved decisions/dispatch records | Do not label current status as historical merely because it is displayed near old records |
| **Decision checkpoint** | Exact stored Decision Context + its selected graph/assumptions, ranked candidate membership, source/policy version, cost estimates and publication | Do not substitute current task statuses into an old context without marking them `current`; no inferred missing historical facts |
| **Graph as-of (underlying data capability, not a third v1 UI mode)** | Research Graph revision heads and baselines at graph sequence `N`, when linked or inspected from a checkpoint | This is **graph history only**; old task/run/evidence *status* cannot be restored by graph sequence alone |

**Only two user-facing temporal modes in v1: `Live` and `Pinned Decision checkpoint`.** Graph as-of is a qualified data projection used when relevant, not another universal time-navigation screen. Proposed data labels: `snapshot_at_decision`, `current_execution`, `graph_as_of`, `unavailable_historically`, `not_recorded`, `unreviewed`, `truncated`, `synthetic_proxy`. These represent data semantics; they are not evidence certifications.

**Checkpoint comparison:** compare `Decision D1` and `Decision D2` on stable candidate IDs/versions, selected membership, rank/exclusion, cost estimates, reasoning and recorded context pins. Three separate outcomes must be possible: **value changed**, **observation/query scope changed**, and **not comparable/unknown**. Adding a new candidate does not prove that science progressed. Graph `at_seq` differences must be identified as graph revision changes, never promoted to a complete historical execution reconstruction.

**Event ordering:** show each source's own timestamp and stable sequence/ID (graph sequence, run time, decision/publication/assessment/dispatch record). A combined visual timeline is an **ordered presentation**, not proof that two adjacent events caused each other. Ties and missing/unreliable timestamps receive a deterministic, inspectable display order.

## 4. Observer system and safety boundary

### 4.1 Local architecture (tentative)

```text
Browser  ←same-origin GET/JSON→  127.0.0.1 Python observer
  Recent tasks/dispatches          |
  Why? trace + Inspector           | short bounded SELECTs
  Pinned checkpoints + live poll   v
                               SQLite v4 (mode=ro + query_only)
                               ├─ Research Graph
                               ├─ Decision Ledger / Contexts
                               └─ Tasks / Runs / Evidence
```

Start a standalone observer with an explicit database path, e.g. **proposed** `python -m arf.observer --db PATH`. Do **not** add observer behavior to the mutating `run-next` command or start observers in the background on behalf of execution. Bind to **127.0.0.1 only**; do not expose to LAN/remote clients in VS-005.

SQLite must be opened through a **dedicated observer connection**, URI `mode=ro`, plus `PRAGMA query_only=ON`, with short `BEGIN` read transactions only. The observer must not call any migration, `Store.transaction()`, task claim, research decision publication, graph mutation, retry or approval API. Avoid importing write-capable service methods into HTTP handlers. Reuse bounded *read projections* where safe, via a read-only adapter with no write-capable connection. Guard against accidentally relying on writer-enabled `Store(...)` construction. WAL and `-shm` files may be needed for an actively written DB; **do not use `immutable=1` to suppress change visibility** or claim zero filesystem side effects beyond DB-content read-only guarantees.

**Local security:** restrict Host to loopback hostnames/addresses to prevent DNS rebinding; validate same-origin browser requests and do not enable permissive CORS. Serve local bundled JS/CSS/fonts/assets—no CDN, external analytics or network access. Use a restrictive Content Security Policy; render research text as text, not executable HTML/JS or arbitrary URL links. Hide filesystem paths, avoid returning arbitrary SQL or file contents, and cap input IDs, page sizes and response sizes. No POST/PATCH/DELETE, WebSocket commands or write actions. A generated local session token is an option if loopback + origin checks are insufficient; its need and transmission are **not yet approved**.

**Compatibility options:** (A) Python standard-library HTTP handler + small bundled JS/SVG, minimal dependencies (**tentative preference**); (B) FastAPI + client graph library, faster app framework with added packages/build surface; (C) static HTML export, portable but not live. Do not lock a framework or asset pipeline before a small UI prototype is evaluated.

### 4.2 No new persistence

Prefer **zero new SQLite schema objects** in VS-005. Graph layout/selection/viewport may live only in the browser's transient state; a persisted shared preference store or annotation feature would be a separate reviewed capability. Do not write graph coordinates, UI timestamps, reader cursors or poll markers to the ARF DB.

If v4 is required to explain a complete recommendation/dispatch trace, an older v1/v2/v3 DB should show a **clear unsupported-feature message** (or a separately approved reduced mode); never migrate itself. First slice may deliberately support **v4 only** to avoid inventing partial interpretations for older schemas.

## 5. Minimal observer read surface (illustrative, not a public API commitment)

**Design the API from the one user journey, not from every future lens.** The earlier nine-endpoint catalog is a **future resource menu**, not nine required v1 routes. A small read-model can serve the first UI with approximately five bounded GET-only capabilities; exact grouping, paths, query names and JSON types are **to be decided after a working static UI prototype**.

| Candidate capability (illustrative route) | Visible user need | Required semantics |
| --- | --- | --- |
| `GET /api/v1/meta` | Header, supported schema, study identity, observer epoch | No filesystem path, no source mutation |
| `GET /api/v1/overview` | Small current task summary, last dispatches and recent decisions | One consistent read; bounded page/continuation, honest status |
| `GET /api/v1/trace?kind=dispatch&id=...` | Selected task/dispatch → candidate → decision → context → run/Evidence, plus a **bounded** motivated graph neighborhood where available | Join by exact stored keys; missing relationships are `not_recorded`; preserve semantic vs execution fact types |
| `GET /api/v1/checkpoint?id=DECISION_ID` | Open a saved Decision Context and member/rank/exclusion record | Source snapshot clearly separated from current status; optional two-checkpoint comparison can initially happen client-side over two immutable responses |
| `GET /api/v1/changes?since=TOKEN` | Lightweight live refresh trigger | Observer epoch / connection-scoped change detection; never a fabricated global SQLite revision |

An exact selected Task/Run/Evidence may be fetched through the *trace* read-model in this slice; a separate generic `/object`, `/graph`, `/timeline`, `/execution`, `/compare` or full-text search API is **not mandatory**. Add one only if the five-step journey demonstrably cannot be completed without it. Do not design a speculative public API surface.

The read model joins existing v4 decision membership, trusted task bindings, dispatch receipts, run/evidence, and available graph assertions. Do not invent new persisted cross-links, graph motivation or a deterministic scientific explanation when evidence is absent. **All used relations and explanations carry source IDs and temporal labels**; human/AI rationale is attributed judgment, not validated truth.

**Bounds first:** cap response size, list length, graph neighborhood and text fields; use cursor pagination where needed, `truncated/frontier` only when honestly available, and typed `not_found`, `unsupported_schema`, `invalid_id`, `limit` and `temporarily_unavailable` errors. Avoid sending a complete stored Context or full Graph every three seconds. Use a short read transaction for a response that combines logically related data, with no observer write path or speculative snapshot cache.

The observer only displays existing data; no HTTP operation creates candidates, validates research, edits interpretations, starts workers, approves tasks, retries, recovers or changes baselines.

## 6. Live updates that preserve the investigation

**Approved product behavior:** the viewer automatically refreshes. **Tentative v1 choice:** simple same-origin HTTP polling about every **3 seconds**, without WebSocket/SSE or a push worker.

1. A persistent SQLite observer connection opened read-only may use `PRAGMA data_version` to notice other connections' commits. The value is **local to that specific connection**—not a portable revision counter or a fresh-connection comparison. Graph sequence alone misses execution/decision changes; main-file modification time alone misses WAL writes.
2. On detected change, the observer updates its **process-local epoch/generation** and a lightweight `/changes` result. On restart, connection replacement or database identity change, epoch/source identity forces client resynchronization; the API must never treat old cursor tokens as durable database facts.
3. The browser fetches only the visible recent list and currently selected trace/Inspector if Live is active. One response representing several records must use a **consistent DB read snapshot**; do not hold transactions open between polls. It need not stream the entire graph.
4. **Do not steal focus:** preserve selected Task/Dispatch ID, Inspector scroll, expanded trace segments and the user's comparison target. A newly recorded event may update a subtle count, not replace the selected object. The initial trace is a small fixed layout, so there is no whole-network simulation to reset.
5. **Pinned checkpoint mode** remains on that exact saved decision/context across incoming commits. Newly arrived events can be indicated in the header/rail, but archived values cannot be silently replaced with the current execution state.
6. On hidden tabs, slow/suspend polls and refresh once on resume. On disconnect/busy DB, visibly mark the last view as **stale** and retry with bounded backoff. A cached view cannot masquerade as live.

Three seconds is a reversible starting interval, **not** a latency guarantee. The observer's data-change detector is a UI optimization, never an execution trigger, research success signal, or reason to write cursor markers into SQLite.

## 7. Minimum interaction grammar and early prototype

The initial interface needs only a handful of meaningful operations:

- **Select** a recent Task or Dispatch. The main trace and Inspector show that record and its exact linked records.
- **Follow** a typed source link in the trace, with a reliable Back/breadcrumb path. A relation missing from Graph or decision provenance is shown as `not_recorded`.
- **Expand** one local link/evidence detail. Long text and large candidate lists are bounded or paginated; no giant free-layout network.
- **Pin** a Decision checkpoint. The old stored context and its candidate ranks remain fixed while the viewer continues to observe new live events.
- **Compare** two recorded Decisions. Prefer a compact table of candidates, rank/exclusion and recorded reasoning changes, with `scope_changed`/`not_comparable` instead of fabricated historical facts.
- **Return to Live** without discarding the selected object or the reader's location.

The **Inspector is the product**, not a decorative sidebar. Its stable labels should include `recorded rationale`, `assumptions`, `source refs`, `unreviewed assessment`, `unvalidated Evidence`, `synthetic proxy`, `predicted cost`, `observed cost`, and `historically unavailable` where appropriate. Never use a synthetic information bonus as a verified scientific importance score.

**Before freezing server routes or selecting a graph package**, test a tiny static layout filled with the **real VS-004 fixture-shaped responses** (not a generic attractive mock screenshot). Try Task B → why selected → observed E → decision checkpoint → later D. Note every missing or confusing interaction. Only then decide if a small real focused graph is needed; a linked list/mini-DAG may already be better.

**Implementation preference to review:** bundled vanilla JavaScript/CSS and small SVG/HTML trace, with Python standard-library loopback HTTP, no extra runtime dependency. If the prototype proves a graph interaction library essential, reconsider a pinned, offline-bundled dependency based on measured usability and build/license cost. Keep keyboard access, text labels (not color alone), focus states, browser zoom and reduced-motion usability.

Defer rich Focus Mode, Map/Decisions/Execution lens switches, global timeline, free-form semantic search, graph auto-layout, annotations, alerting, user preference persistence, complex charts and reporting. These are **extensions**, not failures of the VS-005 first implementation.

## 8. One end-to-end v1 demonstration

Use the **existing v4 offline synthetic fixture** as read-only input, including its original B/A/C recommendation, later D, unreviewed graph assessments, measured run costs and `unvalidated` Evidence. Starting Observatory must **not** execute a worker.

1. Open the local URL for an existing v4 database. The initial screen shows the study label, latest task/dispatch summary and connected `Live` state. It is **not** an empty all-purpose graph.
2. Choose **Task B** or its dispatch from the recent list. The trace shows its actual admitted TaskSpec, candidate binding, recommendation/rank, considered alternatives and policy explanation. If a direct Q/H motivation is not recorded, show `not_recorded`; never infer it.
3. Inspect B's run/Evidence and observed wall cost, explicitly labeled `unvalidated`. Show synthetic decision proxies and estimated costs separately from actual measurements.
4. Pin the **initial decision checkpoint**. It exposes the exact saved context, original candidate membership/ranks, source version and partiality status; no current mutable task status masquerades as a historical one.
5. Compare with the **later decision that introduced D**. Identify observed candidate arrival, revealed synthetic feedback, rank/exclusion changes and changed query scope if any. Present the saved `replan` assessment as an attributed policy result, not a validated causal inference.
6. From a **separate trusted test writer**, add a legal graph assertion or perform a controlled fixed-worker execution on a disposable fixture. The viewer polls and shows new activity **without page reload or changing the selected B**.
7. Keep the first checkpoint pinned and make another fixture change. The checkpoint remains unchanged, while a modest "new activity" indication appears. Re-enter Live deliberately.
8. Send malformed IDs/oversized queries and attempt write-like HTTP methods / SQLite writes through the observer. Confirm bounded failures, no mutating routes, **read-only DB content** and no controller/worker invocation. Existing VS-001–004 regressions and data remain intact.

This scenario deliberately uses records that exist **today**. It must not depend on P2 being implemented or infer final study success. A v4 dispatch with `needs_decision / unranked_ready_task` should be displayed as an actual recorded nonexecuting result, not rewritten as an imaginary recommendation. The demo is an engineering observation, not scientific certification.

## 9. Proposed acceptance matrix (O1–O12; not approved)

| ID | Observable acceptance requirement |
| --- | --- |
| O1 — Read-only boundary | No mutating HTTP route/callback; all DB connections `mode=ro` + query-only; attempts to write fail; no migration, worker or controller-lock acquisition by observer |
| O2 — Local isolation | Bind 127.0.0.1 only; Host/origin/CORS/CSP controls; no external asset/network/dependency fetch; source research text never becomes executable script |
| O3 — Single workspace | One shared selection/Inspector across Map, Decisions and Execution lenses; focus/filters retained on switch |
| O4 — Provenance | Task→candidate→decision→assessment→dispatch→run/Evidence chain follows actual stored keys; missing links explicitly marked `not_recorded` |
| O5 — Graph fidelity | Typed semantic/derived/operator-transition edges, revisions, unreviewed status, bounds and frontier; no inferred scientific causal claims |
| O6 — Historical honesty | Pinned decision context exact; graph-as-of separate; current task statuses never masquerade as past statuses; unsupported comparisons labeled |
| O7 — Change comparison | Two checkpoints compare candidate/rank/reason changes and detect selection-scope differences/incomparable items |
| O8 — Full decision trace | Ranked, excluded, unranked, unmapped, abstained, reused and replanned records visible with source policy and synthetic impact disclaimer |
| O9 — Execution fidelity | Current readiness/blockers and immutable run/evidence history, with predicted vs observed cost and unknown/null preserved |
| O10 — Live update | Test writer changes graph, task/run and decision records; polling detects each, preserves selection/layout; Historical View stays pinned; server restart resyncs safely |
| O11 — Bounded operation | Large graph/context, malformed IDs, many timeline events and busy/locked DB return bounded pages/errors and never silently truncate historical evidence |
| O12 — Compatibility and reproducibility | Existing VS-001–004 tests/demos unchanged, no v4 schema change, observer browser+server tests and an end-to-end read-only scenario pass; no VS-005 actions created by reading |

For O10, a test that modifies a fixture database must use a **separate trusted writer process** and demonstrate that the observer itself performed no write.

## 10. Risks and deliberately deferred scope

- **Misleading causality:** a graph `MOTIVATED_BY` or `ASSESSES` edge is provenance/interpretation, not proof of discovery, and `unvalidated` Evidence remains such.
- **Fake historical completeness:** Graph `at_seq` and decision snapshots have different semantics. Never stitch current statuses into an old state without a temporal label.
- **Large graphs / performance:** even bounded traversals can be visually busy. Prefer Focus Mode and thin query projections; measure server cost before introducing indexes or persistent caches.
- **Read-only isn't merely missing UI buttons:** even a local web service must defend against DNS rebinding and untrusted research text.
- **Polling connection semantics:** `PRAGMA data_version` is local to a persistent connection; WAL/observer restarts require epoch-based resynchronization.
- **UI policy mismatch:** current P2 and future scheduling changes should alter displayed audit facts, not require rewriting the observer's authority model.
- **No real progress truth:** task throughput, graph growth, synthetic reward and number of citations are metrics about activity, not proof the study's ultimate goal has been answered.

Defer UI edits, authorization, manual annotations, task admission, approval, run/retry, remote hosting, multi-user collaboration, push/WebSockets, notifications, report export, automatic scientific review, source-code execution, new research policies and true whole-study time travel.

## 11. Design alternatives requiring explicit human review (V5-1–V5-9)

| ID | Choice | Tentative preference | Alternatives / risk |
| --- | --- | --- | --- |
| V5-1 | Primary layout | Single Research Explorer + stable Inspector + thin checkpoint/event rail | Three unrelated dashboards duplicate navigation and state |
| V5-2 | UI view selection | Map/Decisions/Execution **lenses** share one typed selection | Separate routes/pages need explicit preserved navigation context |
| V5-3 | Historical model | Decision checkpoint is primary; graph-as-of separately labeled | One universal time slider would falsely imply full execution history |
| V5-4 | Refresh mechanism | HTTP poll approximately 3 s; persistent read-only `data_version` detector + observer epoch | WebSocket/SSE adds lifecycle complexity; naive graph seq/file mtime misses changes |
| V5-5 | Server stack | Local Python stdlib + bounded GET APIs and bundled static assets | FastAPI/framework dependency or static non-live export |
| V5-6 | Frontend/graph | Small locally bundled JS/SVG, bounded focus-first layout | A pinned local graph library if simple prototype underperforms |
| V5-7 | Supported schemas | Explicit **v4-only** full Observatory for first slice; no silent migration | Reduced v3 view could be a follow-up; inventing partial decision history is risky |
| V5-8 | Privacy/security | Loopback-only, read-only SQLite, Host/origin/CSP/same-origin and no external assets | Session token may be warranted; choose after threat review |
| V5-9 | Query/payload limits | Reuse bounded existing graph, ledger and context contracts; add small per-API page/response limits | Relax limits only with measurements; never silently drop evidence |

## 12. Suggested next step

Have the human owner review V5-1–V5-9. Then convert the accepted choices into ADRs and a **smaller, normative `tasks/VS-005.md`**, plus a proposed HTTP/temporal contract before assigning Codex implementation. A quick static prototype using the saved VS-004 offline fixture can validate whether the Inspector and Checkpoints communicate the right information—without adding a production UI, migration or execution capability.

**This proposal is not permission to implement VS-005.**
