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

### 3.2 Temporal truth: three modes, no fake global time machine

| Mode | Show | Explicit prohibition |
| --- | --- | --- |
| **Live** | One consistent read of current graph, task/statuses, latest saved decisions/dispatch records | Do not label current status as historical merely because it is displayed near old records |
| **Decision checkpoint** | Exact stored Decision Context + its selected graph/assumptions, ranked candidate membership, source/policy version, cost estimates and publication | Do not substitute current task statuses into an old context without marking them `current`; no inferred missing historical facts |
| **Graph as-of** | Research Graph revision heads and baselines at graph sequence `N` | This is **graph history only**; old task/run/evidence *status* cannot be restored by graph sequence alone |

Proposed explicit badges/labels in data, not flashy UI: `snapshot_at_decision`, `current_execution`, `graph_as_of`, `unavailable_historically`, `unreviewed`, `truncated`, `synthetic_proxy`. These represent data semantics; they are not evidence certifications.

**Checkpoint comparison:** compare `Decision D1` and `Decision D2` on stable candidate IDs/versions, selected membership, rank/exclusion, cost estimates, reasoning and recorded context pins. Three separate outcomes must be possible: **value changed**, **observation/query scope changed**, and **not comparable/unknown**. Adding a new candidate does not prove that science progressed. Graph `at_seq` differences must be identified as graph revision changes, never promoted to a complete historical execution reconstruction.

**Event ordering:** show each source's own timestamp and stable sequence/ID (graph sequence, run time, decision/publication/assessment/dispatch record). A combined visual timeline is an **ordered presentation**, not proof that two adjacent events caused each other. Ties and missing/unreliable timestamps receive a deterministic, inspectable display order.

## 4. Observer system and safety boundary

### 4.1 Local architecture (tentative)

```text
Browser  ←same-origin GET/JSON→  127.0.0.1 Python observer
  Map / Decisions / Execution      |
  Inspector / Checkpoints          | short bounded SELECTs
  Live refresh                     v
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

If v4 is required for all three lenses, an older v1/v2/v3 DB should show a **clear unsupported-feature message** (or a separately approved reduced mode); never migrate itself. First slice may deliberately support **v4 only** to avoid inventing partial interpretations for older schemas.

## 5. Proposed bounded read-only HTTP surface (not yet approved)

Expose a deliberately small set of **versioned GET-only** JSON resources. URLs and response fields below are placeholders for design review, not public contracts:

| Proposed read | Primary purpose | Source / rule |
| --- | --- | --- |
| `GET /api/v1/meta` | Study label/hash, schema, observer version, temporal capabilities and current server session epoch | No charter mutation or full path disclosure |
| `GET /api/v1/changes?since=TOKEN` | Lightweight process-local revision/generation plus changed-domain hints | Graph seq alone is insufficient |
| `GET /api/v1/graph?focus=ROLE:ID&at_seq=N&depth=...` | Bounded typed graph neighborhood, edges, frontier and active baselines | Reuse `read_graph` / `traverse` semantics; never return an unbounded entire graph |
| `GET /api/v1/object?kind=...&id=...&revision=...` | Selected object metadata/provenance and relevant exact links | Same-study typed IDs, bounded raw text |
| `GET /api/v1/timeline?cursor=...` | Stable, paginated decision/graph/run/evidence/dispatch events | Timestamp/sequence provenance and a clear opaque cursor |
| `GET /api/v1/decision?id=...` | Full saved considered members/ranks/exclusions/assessments/publications/dispatches | Reuse v4 ledger; show synthetic status and completeness |
| `GET /api/v1/checkpoint?id=...` | Exact saved decision context + explicit `snapshot_at_decision` labeling | No fake historical execution reconstruction |
| `GET /api/v1/compare?left=...&right=...` | Bounded comparison of two immutable checkpoints | Separate membership change from context scope difference |
| `GET /api/v1/execution?cursor=...` | Current tasks/blockers plus run/evidence/cost history | Cost prediction vs observed costs shown separately |

Avoid returning entire v4 contexts on **every** 3-second poll. Graph is focused/paged, timeline paged, large historical context fetched only on explicit user selection. Use one read transaction for each logically related response, explicit `truncated/frontier/continuation` and typed errors: `not_found`, `unsupported_schema`, `invalid_id`, `limit`, `temporarily_unavailable`. Standard server `5xx` never claims `no_ready_task` or study completion.

For UI-specific joins between Graph, Task, Candidate, Decision and Run, use a **read-model projection layer**, not new authoritative persistent cross-links. A Decision candidate's task binding is distinct from its graph motivation; links must be evidence-backed or marked `not_recorded`.

## 6. Automatic refresh: cheap, consistent and unobtrusive

**Approved direction:** automatic updates; **tentative v1 implementation:** HTTP polling every **3 seconds** with no WebSocket or background pushes.

1. An observer-owned **persistent read-only SQLite connection** may use `PRAGMA data_version` as a cheap detector of commits made by *other* connections. The value is **connection-local**; do not expose it as a portable global DB revision or compare values across fresh connections. No filename mtime checks alone: WAL changes may not update the main file timestamp.
2. Maintain an **in-process observer epoch and monotonic generation**. On a detected change, increment generation and, if useful, compute bounded domain-specific fingerprints/hints (graph, tasks/runs/evidence, decision ledger). A changed generation means `something may have changed`, not that all objects changed. On server restart/connection replacement, epoch changes and clients re-bootstrap.
3. Client polls `/changes`; on a change fetch **only the currently visible panel and selected object's bounded data**. Recheck an atomic response snapshot/observed generation to avoid presenting a mixed view as one time. Do not hold SQLite read transactions across HTTP polling or browser interactions.
4. Keep selected typed ID, lens, filters, graph pan/zoom and expanded neighbors. New graph objects must not trigger a full force-layout reset. Use stable positions/seeded layout with incremental placement of added nodes; remove nodes from the view only when filtering/context semantics demand it.
5. **Live mode** updates in place; **Decision checkpoint / Graph as-of** remains pinned while a small nonintrusive new-events indication appears. A live event may update the sidebar counter, not forcibly replace the historical selection.
6. When browser tab is hidden, reduce or suspend polling; on resume perform one fresh bounded check. On server/DB error, keep last **clearly marked stale** view and retry with bounded backoff, never present cached data as fresh current state. If DB is deleted/replaced, epoch/source identity changes and old selections cannot be silently applied to another study.

Polling rate must be adjustable later; no 3-second responsiveness guarantee. A pure notification/watermark is a read optimization, **not** an authorization or scientific status signal.

## 7. UI behavior and implementation alternatives

**Graph:** default 1-hop or 2-hop focus, semantic edges and execution dependencies visually distinct, explicit legend and edge labels on inspection. Prevent cycles from growing infinite views; cap nodes/edges and show `more`/frontier controls. Stable typed ID + graph revision should ground each node.

**Inspector:** the primary reading surface. Display raw source refs, original vs retrospective motivation, scientific interpretations (supports/contradicts/inconclusive, `unreviewed`), assessment assumptions, Decision members including not-selected/excluded and predicted vs observed cost. Avoid a generic `confidence 87%` or `research progress 62%` unless scientifically grounded.

**Timeline / Checkpoints:** use simple event chips, compact rank comparison table and text explanations before building complex charts. Click a checkpoint to pin the context; compare two decisions using explicit labels `same scope`, `scope differs`, `unknown historical state`. Historical mode does not automatically jump to latest.

**Search:** exact ID/name/title + a few bounded text filters from trusted in-database fields; pagination and explicit result source. Do not invent semantic search or require an embeddings index for VS-005.

**Desktop-first accessibility:** keyboard navigation, focus outline, zoom controls, color-independent edge labels, readable dense panels and reduced-motion option. No decorative animation required. Browser-only graph layout can remain ephemeral and reversible.

**Minimal frontend alternatives:** (A) small bundled vanilla JS and SVG with deterministic incremental layout (**tentative** for a modest focus graph); (B) pinned local Cytoscape/D3 bundle if a measured prototype demonstrates substantially better graph ergonomics; avoid a heavy framework solely to reproduce an inspector and event rail. A library decision must include license/build artifact and fully offline packaging review.

## 8. Narrow v1 vertical slice / demo

Suggested first scenario uses the **already available v4 synthetic fixture** and must not execute research as part of viewing:

1. Start observer pointed at an existing inspected v4 database; see study header, connected status, recent four demo runs B/A/C/D and a compact focused graph.
2. Select Task B: see original task/admission, matched candidate, the ranked recommendation that dispatched B, its synthetic judgment, actual measured run costs and unvalidated evidence link.
3. Open the initial Decision checkpoint: see B/A/C membership, synthetic information bonus, considered/excluded unmapped alternatives, saved context scope and explicit provenance. Never label its numerical bonus actual scientific impact.
4. Compare that checkpoint with the post-C recommendation (D introduced), separating new candidate arrival, changed Evidence/graph context and new synthetic ranking. Follow the recorded replan assessment instead of inventing causal explanations.
5. On a separate writer process, add a legitimate new Research Graph assertion or execute an already authorized demo task in a **test fixture DB**, not through the observer. Without reloading the page, the Live UI detects and displays the changed domain while preserving selection and layout.
6. Pin Historical View, generate a subsequent change, confirm the old checkpoint/Inspector does **not** silently become Live or rewrite its archived task statuses.
7. Confirm browser cannot approve, import, create, retry, recover, activate baseline, edit graph or execute `run-next`; server read-only connection remains unable to write even if a request is malformed.

Do not conflate a successful UI demonstration with a verified scientific conclusion. A dummy DB fixture may intentionally contain a blocked/unranked ready task; display actual `needs_decision` receipt and preserve the currently implemented policy (P2).

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
