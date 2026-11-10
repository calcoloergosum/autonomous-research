# Codex handoff — implement accepted VS-005 Research Observatory

**Target:** the bounded, local, read-only VS-005 engineering task. Do **not** treat the broader proposal as required scope.
**Status at handoff:** design contract is accepted; **implementation is not yet present**. This file is instructions for a separate explicit Codex task, not evidence that any code has been written or tests have run.

## Read before changes

1. `AGENTS.md`, `README.md`, `docs/project-charter.md`, `docs/architecture.md`, `docs/decisions.md`, `docs/current-state.md`.
2. **Normative:** `tasks/VS-005.md` and `docs/interfaces-vs005.md`.
3. Relevant source contracts: `docs/interfaces-vs003.md`, `docs/interfaces-vs004.md`; inspect `arf/store.py`, `arf/graph_query.py`, `arf/decision_store.py`, `arf/decisions.py`, `arf/dispatch.py`, `arf/decision_demo.py`.
4. Check `git status`, current `main` head and local untracked files. Preserve all pre-existing local changes and files unrelated to the task. If API/schema/authority changes are needed, **stop and report alternatives**, rather than silently broadening implementation.

## Build only this vertical slice

Implement one local UI journey:

`open existing v4 study → select Task B/dispatch → see Why? (candidate, rank, alternatives, original assumptions) → inspect actual Run/Evidence → pin saved Decision Context → compare with later D decision → observe separate-writer live update without losing focus.`

**Backend:** small standard-library Python observer, e.g. `python -m arf.observer --db PATH`; loopback `127.0.0.1` only; strictly read-only SQLite `mode=ro` / `query_only=ON`; no migrations, write-capable `Store` path, worker, claims or ranking. Build simple parameterized, bounded read projections and five GET resources **exactly as specified** in `docs/interfaces-vs005.md`: `meta`, `overview`, `trace`, `checkpoint`, `changes`. Keep an explicit source/capture temporal label on every historical inference; no fabricated graph linkage.

**Frontend (selected):** **React + Vite + strict TypeScript**. Minimal one-page recent-activity list + linked Why? trace + persistent Inspector and two checkpoint comparison. Use small local components, robust runtime JSON validation and descriptive status labels; do not add a routing framework, graph engine or state-management package without a demonstrated user-journey failure. Built, bundled assets are served locally by the Python observer; no Node dependency at **observer runtime**.

**Polling:** approximately every 3 seconds with a persistent read-only SQLite connection's locally scoped `PRAGMA data_version` check and server process epoch/generation. Changes must include task/run/evidence/decision writes, not merely graph sequence. Preserve `selected`, `pinned`, `compare`, Inspector scroll and expansion across refresh. If a response is stale, busy or from a different source epoch, show an explicit stale/reset state; do not silently swap underlying studies or apply an out-of-order response.

**Security:** only loopback server and same-origin local assets. Reject DNS-rebinding Host, cross-origin, non-GET API methods, path traversal and large/bad IDs. CSP and safe React text rendering. No unrestricted SQL, arbitrary-file reads, CORS wildcard, external analytics/CDNs, browser commands to modify research or open network. No external model/API calls, payments or substantive research.

**Time honesty:** pinned Decision Context is **captured input**, not a full database image at time of publication. Graph as-of contains graph revisions only; current T/R/E status must not be represented as past. Saved `unvalidated` Evidence and synthetic fixture impact/costs remain clearly labeled. Unknown/unranked/unmapped alternatives remain visible.

## Work sequence

1. Inspect actual repository schemas and v4 demo JSON payloads. Create a tiny fixed React/TS prototype of the B → Why? → Evidence → Decision comparison using those fields; refactor any confusing interactions, not the authority model.
2. Define observer read-model/DTO decoders with strict tests; write/read tests first for no mutation, time semantics, bounds and exact joins. Avoid importing write-capable methods.
3. Implement minimal Python observer and five documented GET endpoints. Add transient error and restart behavior.
4. Wire React UI and runtime JSON decoding. Build with pinned versions/lockfile and repeatable local assets. `npm ci`, `npm run typecheck`, `npm run build` where supported. **Do not silently access the network to install unavailable packages; report a missing offline dependency/environment prerequisite.**
5. Test VS5-01…VS5-12 including fixture B and later D, no rank/abstain/unranked receipts, separate trusted writer that changes graph and execution/decision records, Live and pinned behavior, replay/restart/DB replacement, HTTP hostile inputs, read-only DB content equality, v1–v3 refusal without migration, frontend runtime JSON validation and keyboard navigation.
6. Run full `python -m pytest -q`, v1–v4 documented offline demos, frontend checks/build and `git diff --check`; record **only actual commands/results** and limitations in `docs/current-state.md`. Include browser integration results if a real browser harness ran; otherwise state they remain unverified.
7. Commit only scoped implementation, tests, build metadata/packaged assets and factual documentation. Report exact commit SHA, test totals, skipped checks, source changes and residual risks.

## Important prohibitions

- Do not change `run-next`, admission, P2 scheduler policy, graph assertion owner, decision ranking/replanning, immutable charter, run lifecycle, approval/authorization or any v1–v4 persistence schema/semantics.
- No viewer-generated task, evidence, graph edit, decision, proposal, approval, import, execution, retry, recover or baseline transition.
- No scientific validation inferred from graph assertion or synthetic proxy score.
- Do not expand to a full Map / Decisions / Execution three-dashboard product, a nine-endpoint API, a universal historical time slider, full-graph layout, semantic search or remote deployment.
- Do not treat existing offline verification statements (561 tests reported after VS-004) as proof that the new VS-005 implementation passed tests; run fresh checks and report clearly.

**Definition of done:** a human can reproduce the one decision-audit journey from **real saved v4 records** in a safe local read-only automatically refreshing React interface, with correct provenance, honest historical labeling, and no task or worker side effects.
