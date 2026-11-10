# Architecture

## Intended system boundaries

```text
Human-owned Study Charter (immutable once imported)
             |
             v
Research Manager (portfolio, hypotheses, impact/cost/evidence estimates)
             |                          ^
             v                          |
Allocation Policy (selects valuable actions) <- Evidence / cost observations
             |
             v
Resource Scheduler (enforces limits, dependencies, scheduling)
             |
       +-----+--------------+
       v     v              v
    LLM/code compute        Human queue
    worker   worker
       \      |              /
        \     v             /
        Persistent Store (tasks, runs, evidence, costs, artifacts, baselines)
```

The research manager proposes and values actions. The resource scheduler independently enforces actual execution permission and capacity. Both use one persistent state store. Human actions and baseline changes are eventually event sources, not special-case implicit prompt context.

## VS-001 implementation path

```text
examples/demo-charter.yaml  --> study import + SHA-256 snapshot --> SQLite
examples/demo-task.json     --> validated task + dependencies    --> SQLite
python -m arf run-next      --> atomic runnable-task claim       --> SQLite
                           --> approved fixed demo worker       --> result JSON
                           --> run + measured wall time         --> SQLite
                           --> unvalidated evidence             --> SQLite
python -m arf recover       --> interrupted/unknown state review --> SQLite
```

**VS-001 responsibilities:**

- `store`: persistence, migrations, atomic task claims, historical runs/evidence.
- `models`: typed, validated task/charter/result contracts.
- `executor`: one allowlisted deterministic demo worker, bounded timeout, output validation.
- `service`: create/list tasks, dependency eligibility, claim/execute/finalize, recover.
- `cli`: small interface exposing the above; machine-readable JSON preferred for inspection.

No AI policy decides task selection yet: `run-next` uses stable FIFO among ready tasks. This is an intentional baseline, not an endorsement of FIFO for real research.

## Data ownership, trust and provenance

- Charter imported as raw bytes + SHA-256 hash + parsed immutable snapshot; the original source is not overwritten. Subsequent import of a changed charter for the same study ID must fail. No charter-update API.
- Task descriptions and predictions are **proposals**, not evidence.
- `runs` are immutable historical attempts after completion; `evidence` is linked to a completed successful run, labeled `unvalidated` by default.
- Artifacts reside outside the DB (later feature) with paths/hashes stored in DB; VS-001 needs only captured JSON result and bounded stdout/stderr or error summary.
- Real LLM/model execution, code generation and external effects are out of scope; do not expose arbitrary shell commands via task JSON.

## Reliability model for the first version

- SQLite foreign keys enabled; use transactions for claim and finalization, a schema version/migration step, and unique task IDs per study.
- Only one `run-next` owns an experiment at a time; concurrent claims must not take the same task. A short SQLite write transaction suffices for claiming; execute outside that transaction.
- On unclean exit, a prior `running` attempt is marked `interrupted` on explicit `recover`, and its task becomes `needs_review`. Never auto-mark it successful or auto-retry.
- An explicit operator `task retry` may reset a demo task for a new attempt. Previously completed run/evidence must remain intact. Strict exactly-once process execution is *not* promised.
- The worker has no network or external effects by design; only one hard-coded supported demo kind is accepted in VS-001.

## Extension seams after VS-001

`ResearchManager`, `AllocationPolicy`, `ImpactCostPredictor`, `ResourceScheduler`, `Worker`, `HumanQueue`, `BaselineManager` are architectural seams, not mandatory full classes in VS-001. Do not implement speculative abstractions without a concrete use in the first milestone.
