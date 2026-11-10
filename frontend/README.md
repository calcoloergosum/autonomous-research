# Local Research Observatory client

React 18, strict TypeScript and Vite. No router, graph engine, state package,
CDN or runtime network dependency. Production assets are checked in under
`arf/observer_assets/`; the Python observer needs no Node installation.

From this directory, with the pinned dependencies available:

```sh
npm ci --offline --ignore-scripts --no-audit --no-fund
npm run typecheck
npm test
npm run build
npm run test:browser
```

`--offline` guarantees npm does not fetch missing packages. A missing cached
package is an environment prerequisite, not permission to use the network.
The lockfile pins the whole tree; postcss/nanoid/rollup overrides select versions
available in the implementation environment's cache. Dependency upgrades are a
separate deliberate change. `npm ci` works conventionally in an environment
where that installation has separately been authorized.

`npm test` runs dependency-free Node test-runner checks for runtime decoding,
unknown/null values, comparison identity/scope and stale request tickets.
Playwright is pinned **development-only** for `test:browser`: it launches an
already installed Chromium, starts and stops its own loopback observer, creates
fresh fixtures under `.local/`, and denies external browser requests. It requires
`../.venv/bin/python` and the existing Python test dependencies. It does not
download a browser. The trusted writer in `tests/observer_writer.py` executes
only existing fixed-demo calculations. It is never imported by the observer.

The first UI intentionally displays only the first overview page, with a visible
incomplete-page label. The API has keyset cursors. Trace relations that cannot
fit the bounded selection return 413; graph neighborhoods have an explicit
frontier. The Inspector contains folded original records for provenance and
unknown fields. Pinned contexts are captured inputs, never global time travel.
