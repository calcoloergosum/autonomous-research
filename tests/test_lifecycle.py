from concurrent.futures import ThreadPoolExecutor
import hashlib
import math
import sqlite3
import subprocess
import sys
import threading

import pytest

from arf.executor import WorkerOutput, execute_demo
from arf.models import ARFError, Charter, TaskSpec, check_acyclic
from arf.service import recover, run_next
from arf.store import Store
from conftest import ROOT, spec


def test_a1_success_and_a8_idempotent_observation(ready):
    output = run_next(ready)
    assert output["status"] == "succeeded"
    task = ready.task("demo-mean")
    assert task["status"] == "succeeded"
    assert len(task["runs"]) == 1
    run = task["runs"][0]
    assert run["result"] == {"mean": 5.0, "count": 4}
    assert run["status"] == "succeeded"
    assert run["exit_code"] == 0 and run["error"] is None
    assert run["started_at"].endswith("Z") and run["ended_at"].endswith("Z")
    assert run["cost"]["wall_seconds"] >= 0
    assert run["cost"] == {
        "wall_seconds": run["cost"]["wall_seconds"], "cpu_seconds": None,
        "llm_tokens": 0, "gpu_seconds": 0, "human_minutes": 0,
    }
    evidence = ready.evidence()
    assert len(evidence) == 1
    assert evidence[0]["result"] == run["result"]
    assert evidence[0]["run_id"] == run["run_id"]
    assert evidence[0]["study_id"] == task["study_id"]
    assert evidence[0]["task_id"] == task["task_id"]
    assert evidence[0]["validation_status"] == "unvalidated"
    assert evidence[0]["provenance"]["charter_sha256"] == ready.study()["source_sha256"]
    assert evidence[0]["provenance"]["input"] == task["input"]
    for _ in range(2):
        assert run_next(ready) == {"status": "no_ready_task"}
        assert recover(ready)["interrupted"] == []
        assert ready.task("demo-mean") == task
        assert ready.evidence() == evidence
    with pytest.raises(ARFError, match="retry requires"):
        ready.retry("demo-mean")


def test_a3_dependencies_fifo_and_failed_blockers(store):
    store.add_task(TaskSpec.parse(spec("A")))
    store.add_task(TaskSpec.parse(spec("B", ["A"])))
    store.add_task(TaskSpec.parse(spec("C")))
    assert store.task("B")["blockers"] == [{"task_id": "A", "status": "pending"}]
    assert run_next(store, lambda _: WorkerOutput("", "controlled failure", 2))["task_id"] == "A"
    assert store.task("B")["status"] == "pending"
    assert store.task("B")["blockers"] == [{"task_id": "A", "status": "failed"}]
    assert run_next(store)["task_id"] == "C"
    assert run_next(store) == {"status": "no_ready_task"}
    store.retry("A")
    assert run_next(store)["task_id"] == "A"
    assert store.task("B")["blockers"] == []
    assert run_next(store)["task_id"] == "B"
    assert len(store.task("A")["runs"]) == 2


@pytest.mark.parametrize("data", [
    spec("missing", ["absent"]), spec("self", ["self"]),
    spec("wrong-study", study_id="other"),
])
def test_a3_invalid_dependencies_rejected_atomically(store, data):
    with pytest.raises(ARFError):
        store.add_task(TaskSpec.parse(data))
    assert store.tasks() == []
    assert store.connection.execute("SELECT COUNT(*) FROM dependencies").fetchone()[0] == 0


def test_a3_cycles_and_long_dag():
    # Forward references are rejected by add_task, so a multi-node cycle cannot
    # be constructed through the CLI; exercise the graph check independently.
    with pytest.raises(ARFError, match="cycle"):
        check_acyclic({"A": ["B"], "B": ["C"], "C": ["A"]})
    check_acyclic({"A": ["B", "C"], "B": ["D"], "C": ["D"], "D": []})
    check_acyclic({str(i): [str(i + 1)] for i in range(2000)})


def test_duplicate_task_never_overwrites(ready):
    before = ready.task("demo-mean")
    with pytest.raises(ARFError, match="already exists"):
        ready.add_task(TaskSpec.parse(spec(title="Changed proposal")))
    assert ready.task("demo-mean") == before


@pytest.mark.parametrize("change", [
    lambda raw: raw.replace(b"arithmetic mean of", b"median of"),
    lambda raw: raw.replace(b"mean is 5.0", b"mean is 6.0"),
    lambda raw: raw + b"\n# Same parsed content, changed source\n",
    lambda raw: raw.replace(b"side-effect-free", b"different"),
])
def test_a4_immutable_charter(ready, change):
    before = ready.study()
    raw = before["source"]
    assert before["source_sha256"] == hashlib.sha256(raw).hexdigest()
    assert ready.import_charter(Charter.parse(raw))["status"] == "already_exists"
    assert ready.study() == before
    with pytest.raises(ARFError, match="immutable"):
        ready.import_charter(Charter.parse(change(raw)))
    assert ready.study() == before


def test_a4_sql_guards_and_single_study(ready):
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        ready.connection.execute("UPDATE studies SET question='changed'")
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        ready.connection.execute("DELETE FROM studies")
    # SQLite REPLACE must not bypass the delete guard on a charter with no tasks.
    with pytest.raises(sqlite3.IntegrityError, match="immutable"):
        ready.connection.execute("INSERT OR REPLACE INTO studies SELECT * FROM studies")
    other = Charter.parse(ready.study()["source"].replace(b"demo-mean-study", b"other-study"))
    with pytest.raises(ARFError, match="one study"):
        ready.import_charter(other)


@pytest.mark.parametrize("worker", [
    lambda _: WorkerOutput("not JSON", "", 0),
    lambda _: WorkerOutput("", "", 0),
    lambda _: WorkerOutput('{"mean": NaN, "count": 4}', "", 0),
    lambda _: WorkerOutput('{"mean": 5, "count": true}', "", 0),
    lambda _: WorkerOutput('{"mean": 5, "count": 3}', "", 0),
    lambda _: WorkerOutput('{"mean": 5, "count": 4, "claim": "validated"}', "", 0),
    lambda _: WorkerOutput('{"mean": 5, "mean": 0, "count": 4}', "", 0),
    lambda _: WorkerOutput('{"mean": 5, "count": 4}', "failure", 1),
    lambda _: WorkerOutput("x" * 5000, "", 0),
])
def test_a5_invalid_output_and_exit_failure(ready, worker):
    assert run_next(ready, worker)["status"] == "failed"
    task = ready.task("demo-mean")
    assert task["status"] == "failed"
    assert len(task["runs"]) == 1
    run = task["runs"][0]
    assert run["status"] == "failed" and run["result"] is None and run["error"]
    assert run["cost"]["wall_seconds"] >= 0
    assert len(run["stdout"]) <= 4096
    assert ready.evidence() == []


@pytest.mark.parametrize("mean", [100.0, math.nextafter(5.0, math.inf)])
def test_demo_wrong_well_formed_mean_fails_without_evidence(ready, mean):
    output = run_next(ready, lambda _: WorkerOutput(f'{{"mean": {mean}, "count": 4}}', "", 0))
    assert output["status"] == "failed"
    assert ready.task("demo-mean")["status"] == "failed"
    run = ready.task("demo-mean")["runs"][0]
    assert run["status"] == "failed" and run["result"] is None
    assert run["error"] == "demo_mean worker mean does not match input"
    assert run["exit_code"] == 0
    assert ready.evidence() == []


@pytest.mark.parametrize(("values", "mean"), [
    ([2, 4, 6, 8], 5.0),
    ([1e308, 1.0, -1e308], 1.0 / 3.0),
    ([5e-324, 5e-324], 5e-324),
    ([1e308, -1e308], 0.0),
])
def test_demo_correct_mean_and_numerical_edges(store, values, mean):
    store.add_task(TaskSpec.parse(spec(input={"values": values})))
    output = run_next(store)
    assert output["status"] == "succeeded"
    assert output["run"]["result"] == {"mean": mean, "count": len(values)}
    evidence = store.evidence()
    assert len(evidence) == 1
    assert evidence[0]["result"] == output["run"]["result"]
    assert evidence[0]["validation_status"] == "unvalidated"


def test_demo_finalization_rechecks_mean_against_persisted_input(ready):
    claim = ready.claim_next()
    with pytest.raises(ARFError, match="demo_mean worker mean does not match input"):
        ready.finish_run(claim["run_id"], result={"mean": 100.0, "count": 4}, error=None,
                         exit_code=0, stdout="", stderr="", wall_seconds=0)
    assert ready.task("demo-mean")["runs"][0]["status"] == "running"
    assert ready.evidence() == []


def test_a5_exception_and_timeout(ready, monkeypatch):
    def broken_worker(_):
        raise RuntimeError("an injected worker error")

    result = run_next(ready, broken_worker)
    assert result["run"]["error"] == "executor error: RuntimeError"
    assert result["run"]["exit_code"] is None
    ready.retry("demo-mean")

    def timed_out(*args, **kwargs):
        assert kwargs["timeout"] == 5
        assert kwargs["env"] == {}
        assert args[0][1] == "-I"
        assert args[0][-1].endswith("/arf/worker.py")
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timed_out)
    result = run_next(ready, execute_demo)
    assert result["status"] == "failed"
    assert "timed out" in result["run"]["error"]
    assert ready.evidence() == []
    assert len(ready.task("demo-mean")["runs"]) == 2


def test_actual_subprocess_timeout(ready, monkeypatch):
    monkeypatch.setattr("arf.executor.TIMEOUT_SECONDS", 0.000001)
    result = run_next(ready, execute_demo)
    assert result["status"] == "failed"
    assert "timed out" in result["run"]["error"]
    assert ready.evidence() == []


def test_a6_crash_recovery_retry_preserves_history(ready):
    def interrupted(_):
        raise SystemExit("simulated controller crash after durable claim")

    with pytest.raises(SystemExit):
        run_next(ready, interrupted)
    first = ready.task("demo-mean")["runs"][0]
    assert first["status"] == "running"
    with pytest.raises(ARFError, match="unfinished"):
        run_next(ready)
    # Re-open the connection as on controller restart.
    with Store(ready.path) as restarted:
        assert recover(restarted)["interrupted"] == [
            {"task_id": "demo-mean", "run_id": first["run_id"]}
        ]
        task = restarted.task("demo-mean")
        assert task["status"] == "needs_review"
        old_run = task["runs"][0]
        assert old_run["status"] == "interrupted"
        assert old_run["result"] is None and old_run["cost"]["wall_seconds"] is None
        assert old_run["error"] and old_run["ended_at"]
        assert recover(restarted)["interrupted"] == []
        assert run_next(restarted) == {"status": "no_ready_task"}
        assert restarted.evidence() == []
        restarted.retry("demo-mean")
        assert run_next(restarted)["status"] == "succeeded"
        history = restarted.task("demo-mean")["runs"]
        assert len(history) == 2 and history[0] == old_run
        assert history[1]["run_id"] != history[0]["run_id"]
        assert restarted.evidence()[0]["run_id"] == history[1]["run_id"]


def test_a7_atomic_claim_race(ready):
    barrier = threading.Barrier(2)

    def claim():
        with Store(ready.path) as connection:
            barrier.wait(timeout=10)
            try:
                return connection.claim_next()
            except ARFError:
                return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(lambda _: claim(), range(2)))
    assert sum(outcome is not None for outcome in outcomes) == 1
    assert len(ready.task("demo-mean")["runs"]) == 1


def test_a7_controller_lock_protects_active_worker_from_recovery(ready):
    started = threading.Event()
    release = threading.Event()

    def slow_executor(data):
        started.set()
        assert release.wait(timeout=10)
        return execute_demo(data)

    def controller():
        with Store(ready.path) as connection:
            return run_next(connection, slow_executor)

    with ThreadPoolExecutor(max_workers=1) as pool:
        running = pool.submit(controller)
        try:
            assert started.wait(timeout=10)
            # SQLite remains usable while the worker runs outside a transaction.
            assert ready.task("demo-mean")["status"] == "running"
            for command in ("run-next", "recover"):
                process = subprocess.run(
                    [sys.executable, "-m", "arf", command, "--db", str(ready.path)],
                    cwd=ROOT, capture_output=True, text=True, timeout=10,
                )
                assert process.returncode == 1 and "controller busy" in process.stderr
            assert ready.task("demo-mean")["runs"][0]["status"] == "running"
        finally:
            release.set()
        assert running.result(timeout=10)["status"] == "succeeded"
    assert len(ready.task("demo-mean")["runs"]) == len(ready.evidence()) == 1


def test_a8_finalization_transaction_rolls_back_all_writes(ready):
    ready.connection.execute("""CREATE TRIGGER simulate_disk_failure BEFORE INSERT ON evidence
        BEGIN SELECT RAISE(ABORT, 'injected persistence failure'); END""")
    with pytest.raises(sqlite3.IntegrityError, match="injected persistence failure"):
        run_next(ready)
    task = ready.task("demo-mean")
    assert task["status"] == "running" and task["runs"][0]["status"] == "running"
    assert task["runs"][0]["result"] is None and ready.evidence() == []
    recover(ready)
    assert ready.task("demo-mean")["status"] == "needs_review"


def test_history_and_evidence_cannot_be_rewritten(ready, request):
    run_next(ready)
    for statement in (
        "UPDATE runs SET result_json='{}'", "DELETE FROM runs",
        "UPDATE evidence SET validation_status='unvalidated'", "DELETE FROM evidence",
        "UPDATE tasks SET input_json='{}'", "DELETE FROM tasks",
    ):
        with pytest.raises(sqlite3.IntegrityError):
            ready.connection.execute(statement)
    assert ready.connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert ready.connection.execute("PRAGMA user_version").fetchone()[0] == request.node.callspec.params["store"]
    assert ready.connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_evidence_requires_success_and_finalization_cannot_repeat(ready):
    claim = ready.claim_next()
    with pytest.raises(sqlite3.IntegrityError, match="successful run"):
        ready.connection.execute(
            "INSERT INTO evidence VALUES ('forged','demo-mean-study','demo-mean',?,'{}','{}','unvalidated','now')",
            (claim["run_id"],),
        )
    recover(ready)
    with pytest.raises(ARFError, match="already finalized"):
        ready.finish_run(claim["run_id"], result={"mean": 5.0, "count": 4}, error=None,
                         exit_code=0, stdout="", stderr="", wall_seconds=0)


def test_real_worker_handles_finite_extremes(store):
    store.add_task(TaskSpec.parse(spec(input={"values": [1e308, 1e308]})))
    result = run_next(store)
    assert result["status"] == "succeeded"
    assert result["run"]["result"] == {"mean": 1e308, "count": 2}
