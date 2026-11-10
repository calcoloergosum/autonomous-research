"""SQLite persistence, atomic claims, and immutable study/run history."""

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterator
import uuid

from arf.models import ARFError, Charter, TaskSpec, check_acyclic, json_text, validate_result


SCHEMA_VERSION = 1

SCHEMA = [
    """CREATE TABLE studies (
        study_id TEXT PRIMARY KEY,
        singleton INTEGER NOT NULL UNIQUE CHECK(singleton = 1),
        question TEXT NOT NULL,
        success_criteria_json TEXT NOT NULL,
        constraints_json TEXT NOT NULL,
        source BLOB NOT NULL,
        source_sha256 TEXT NOT NULL,
        imported_at TEXT NOT NULL
    )""",
    """CREATE TABLE tasks (
        sequence INTEGER PRIMARY KEY AUTOINCREMENT,
        study_id TEXT NOT NULL REFERENCES studies(study_id),
        task_id TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL,
        kind TEXT NOT NULL CHECK(kind = 'demo_mean'),
        input_json TEXT NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('pending','running','succeeded','failed','needs_review')),
        created_at TEXT NOT NULL,
        UNIQUE(study_id, task_id)
    )""",
    """CREATE TABLE dependencies (
        study_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        prerequisite_id TEXT NOT NULL,
        PRIMARY KEY(study_id, task_id, prerequisite_id),
        CHECK(task_id <> prerequisite_id),
        FOREIGN KEY(study_id, task_id) REFERENCES tasks(study_id, task_id),
        FOREIGN KEY(study_id, prerequisite_id) REFERENCES tasks(study_id, task_id)
    )""",
    """CREATE TABLE runs (
        run_id TEXT PRIMARY KEY,
        study_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        started_at TEXT NOT NULL,
        ended_at TEXT,
        status TEXT NOT NULL CHECK(status IN ('running','succeeded','failed','interrupted')),
        exit_code INTEGER,
        error TEXT,
        stdout TEXT NOT NULL DEFAULT '',
        stderr TEXT NOT NULL DEFAULT '',
        result_json TEXT,
        wall_seconds REAL CHECK(wall_seconds >= 0),
        llm_tokens INTEGER NOT NULL DEFAULT 0 CHECK(llm_tokens = 0),
        gpu_seconds REAL NOT NULL DEFAULT 0 CHECK(gpu_seconds = 0),
        human_minutes REAL NOT NULL DEFAULT 0 CHECK(human_minutes = 0),
        cpu_seconds REAL,
        FOREIGN KEY(study_id, task_id) REFERENCES tasks(study_id, task_id),
        UNIQUE(study_id, task_id, run_id),
        CHECK((status = 'running' AND ended_at IS NULL AND result_json IS NULL)
           OR (status = 'succeeded' AND ended_at IS NOT NULL AND result_json IS NOT NULL
               AND exit_code = 0 AND error IS NULL AND wall_seconds IS NOT NULL)
           OR (status IN ('failed','interrupted') AND ended_at IS NOT NULL
               AND result_json IS NULL AND error IS NOT NULL))
    )""",
    "CREATE UNIQUE INDEX one_active_run_per_task ON runs(study_id, task_id) WHERE status = 'running'",
    "CREATE UNIQUE INDEX one_active_run ON runs((1)) WHERE status = 'running'",
    """CREATE TABLE evidence (
        evidence_id TEXT PRIMARY KEY,
        study_id TEXT NOT NULL,
        task_id TEXT NOT NULL,
        run_id TEXT NOT NULL UNIQUE,
        result_json TEXT NOT NULL,
        provenance_json TEXT NOT NULL,
        validation_status TEXT NOT NULL CHECK(validation_status = 'unvalidated'),
        created_at TEXT NOT NULL,
        FOREIGN KEY(study_id, task_id, run_id) REFERENCES runs(study_id, task_id, run_id)
    )""",
    """CREATE TRIGGER evidence_requires_success BEFORE INSERT ON evidence
        WHEN NOT EXISTS (SELECT 1 FROM runs WHERE run_id = NEW.run_id
            AND status = 'succeeded' AND result_json = NEW.result_json)
        BEGIN SELECT RAISE(ABORT, 'evidence requires matching successful run'); END""",
    """CREATE TRIGGER finalized_run_immutable BEFORE UPDATE ON runs
        WHEN OLD.status <> 'running'
        BEGIN SELECT RAISE(ABORT, 'completed run is immutable'); END""",
    """CREATE TRIGGER task_proposal_immutable BEFORE UPDATE OF
        study_id, task_id, title, description, kind, input_json, created_at, sequence ON tasks
        BEGIN SELECT RAISE(ABORT, 'task proposal is immutable'); END""",
    """CREATE TRIGGER task_transition BEFORE UPDATE OF status ON tasks
        WHEN NOT ((OLD.status = 'pending' AND NEW.status = 'running')
            OR (OLD.status = 'running' AND NEW.status IN ('succeeded','failed','needs_review'))
            OR (OLD.status IN ('failed','needs_review') AND NEW.status = 'pending'))
        BEGIN SELECT RAISE(ABORT, 'invalid task transition'); END""",
]

# SQL triggers guard against accidental writes through another application path.
for _table in ("studies", "evidence", "dependencies"):
    for _action in ("UPDATE", "DELETE"):
        SCHEMA.append(
            f"CREATE TRIGGER {_table}_no_{_action.lower()} BEFORE {_action} ON {_table} "
            f"BEGIN SELECT RAISE(ABORT, '{_table} is immutable'); END"
        )
for _table in ("tasks", "runs"):
    SCHEMA.append(
        f"CREATE TRIGGER {_table}_no_delete BEFORE DELETE ON {_table} "
        f"BEGIN SELECT RAISE(ABORT, '{_table} history cannot be deleted'); END"
    )


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class Store:
    def __init__(self, path: str | Path, *, create: bool = False):
        self.path = Path(path).resolve()
        if create:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        elif not self.path.is_file():
            raise ARFError("database does not exist; use init first")
        self.connection = sqlite3.connect(self.path, isolation_level=None, timeout=5)
        self.connection.row_factory = sqlite3.Row
        try:
            self.connection.execute("PRAGMA foreign_keys = ON")
            self.connection.execute("PRAGMA recursive_triggers = ON")
            self.connection.execute("PRAGMA synchronous = FULL")
            with self.transaction():
                version = self.connection.execute("PRAGMA user_version").fetchone()[0]
                if version == 0 and create:
                    # Never adopt or overwrite an unrelated unversioned database.
                    if self.connection.execute("SELECT 1 FROM sqlite_master").fetchone():
                        raise ARFError("cannot initialize a nonempty unversioned database")
                    for statement in SCHEMA:
                        self.connection.execute(statement)
                    self.connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
                elif version != SCHEMA_VERSION:
                    raise ARFError(f"unsupported database schema version: {version}")
        except BaseException:
            self.connection.close()
            raise

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *_: Any) -> None:
        self.connection.close()

    @contextmanager
    def transaction(self) -> Iterator[None]:
        self.connection.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.connection.commit()
        except BaseException:
            self.connection.rollback()
            raise

    def study(self) -> dict:
        row = self.connection.execute("SELECT * FROM studies").fetchone()
        if row is None:
            raise ARFError("database has no study; use init first")
        return dict(row)

    def import_charter(self, charter: Charter) -> dict:
        with self.transaction():
            existing = self.connection.execute("SELECT * FROM studies").fetchone()
            if existing is not None:
                if existing["study_id"] != charter.study_id:
                    raise ARFError("only one study per database is supported")
                if existing["source"] != charter.source:
                    raise ARFError("stored study charter is immutable; source bytes changed")
                return {"status": "already_exists", "study_id": charter.study_id}
            self.connection.execute(
                "INSERT INTO studies VALUES (?,1,?,?,?,?,?,?)",
                (charter.study_id, charter.question, json_text(charter.success_criteria),
                 json_text(charter.constraints), charter.source,
                 hashlib.sha256(charter.source).hexdigest(), utc_now()),
            )
            return {"status": "imported", "study_id": charter.study_id}

    def add_task(self, spec: TaskSpec) -> dict:
        with self.transaction():
            if spec.study_id != self.study()["study_id"]:
                raise ARFError("task study_id must match the database study")
            rows = self.connection.execute("SELECT task_id FROM tasks").fetchall()
            graph: dict[str, list[str]] = {row["task_id"]: [] for row in rows}
            if spec.task_id in graph:
                raise ARFError(f"task already exists: {spec.task_id}")
            if spec.task_id in spec.dependencies:
                raise ARFError("self-dependency is a cycle")
            if any(dep not in graph for dep in spec.dependencies):
                raise ARFError("dependencies must reference existing tasks in the same study")
            for row in self.connection.execute("SELECT task_id, prerequisite_id FROM dependencies"):
                graph[row["task_id"]].append(row["prerequisite_id"])
            graph[spec.task_id] = spec.dependencies
            check_acyclic(graph)
            self.connection.execute(
                """INSERT INTO tasks(study_id,task_id,title,description,kind,input_json,status,created_at)
                   VALUES (?,?,?,?,?,?,'pending',?)""",
                (spec.study_id, spec.task_id, spec.title, spec.description, spec.kind,
                 json_text(spec.input), utc_now()),
            )
            self.connection.executemany(
                "INSERT INTO dependencies VALUES (?,?,?)",
                [(spec.study_id, spec.task_id, dep) for dep in spec.dependencies],
            )
        return self.task(spec.task_id)

    def _task_view(self, row: sqlite3.Row) -> dict:
        result = dict(row)
        result["input"] = json.loads(result.pop("input_json"))
        deps = self.connection.execute(
            """SELECT d.prerequisite_id, t.status FROM dependencies d
               JOIN tasks t ON t.study_id=d.study_id AND t.task_id=d.prerequisite_id
               WHERE d.study_id=? AND d.task_id=? ORDER BY t.sequence""",
            (row["study_id"], row["task_id"]),
        ).fetchall()
        result["dependencies"] = [dep["prerequisite_id"] for dep in deps]
        result["blockers"] = [
            {"task_id": dep["prerequisite_id"], "status": dep["status"]}
            for dep in deps if dep["status"] != "succeeded"
        ]
        return result

    def tasks(self) -> list[dict]:
        self.study()
        return [self._task_view(row) for row in self.connection.execute("SELECT * FROM tasks ORDER BY sequence")]

    def task(self, task_id: str) -> dict:
        row = self.connection.execute("SELECT * FROM tasks WHERE task_id=?", (task_id,)).fetchone()
        if row is None:
            raise ARFError(f"unknown task: {task_id}")
        result = self._task_view(row)
        result["runs"] = [
            self._run_view(run) for run in self.connection.execute(
                "SELECT * FROM runs WHERE task_id=? ORDER BY rowid", (task_id,)
            )
        ]
        return result

    @staticmethod
    def _run_view(row: sqlite3.Row) -> dict:
        result = dict(row)
        raw = result.pop("result_json")
        result["result"] = json.loads(raw) if raw is not None else None
        result["cost"] = {
            key: result.pop(key) for key in
            ("wall_seconds", "llm_tokens", "gpu_seconds", "human_minutes", "cpu_seconds")
        }
        return result

    def claim_next(self) -> dict | None:
        """Commit the running attempt before returning; execution is never in this transaction."""
        with self.transaction():
            self.study()
            if self.connection.execute("SELECT 1 FROM runs WHERE status='running'").fetchone():
                raise ARFError("unfinished running attempt; inspect and use recover before run-next")
            row = self.connection.execute(
                """SELECT t.* FROM tasks t WHERE t.status='pending' AND NOT EXISTS (
                    SELECT 1 FROM dependencies d JOIN tasks p
                      ON p.study_id=d.study_id AND p.task_id=d.prerequisite_id
                    WHERE d.study_id=t.study_id AND d.task_id=t.task_id AND p.status <> 'succeeded'
                ) ORDER BY t.sequence LIMIT 1"""
            ).fetchone()
            if row is None:
                return None
            run_id = str(uuid.uuid4())
            self.connection.execute(
                "UPDATE tasks SET status='running' WHERE study_id=? AND task_id=?",
                (row["study_id"], row["task_id"]),
            )
            self.connection.execute(
                "INSERT INTO runs(run_id,study_id,task_id,started_at,status) VALUES (?,?,?,?,'running')",
                (run_id, row["study_id"], row["task_id"], utc_now()),
            )
            task_id = row["task_id"]
        return {"run_id": run_id, "task": self.task(task_id)}

    def finish_run(self, run_id: str, *, result: dict | None, error: str | None,
                   exit_code: int | None, stdout: str, stderr: str, wall_seconds: float) -> dict:
        with self.transaction():
            run = self.connection.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
            if run is None or run["status"] != "running":
                raise ARFError("run is absent or already finalized")
            status = "succeeded" if result is not None else "failed"
            if result is not None:
                task = self.task(run["task_id"])
                validate_result(result, task["input"])
                if error is not None or exit_code != 0:
                    raise ARFError("successful result requires exit code zero and no error")
            elif not error:
                raise ARFError("failed run requires an error summary")
            end = utc_now()
            result_json = json_text(result) if result is not None else None
            self.connection.execute(
                """UPDATE runs SET ended_at=?, status=?, result_json=?, error=?, exit_code=?,
                   stdout=?, stderr=?, wall_seconds=? WHERE run_id=?""",
                (end, status, result_json, error, exit_code, stdout, stderr, wall_seconds, run_id),
            )
            self.connection.execute(
                "UPDATE tasks SET status=? WHERE study_id=? AND task_id=?",
                (status, run["study_id"], run["task_id"]),
            )
            if result is not None:
                provenance = {
                    "worker": "arf.demo_mean.v1", "source": "observed_fixed_worker_result",
                    "charter_sha256": self.study()["source_sha256"],
                    "run_id": run_id, "input": task["input"],
                }
                self.connection.execute(
                    "INSERT INTO evidence VALUES (?,?,?,?,?,?,'unvalidated',?)",
                    (str(uuid.uuid4()), run["study_id"], run["task_id"], run_id,
                     result_json, json_text(provenance), end),
                )
        return self.task(run["task_id"])["runs"][-1]

    def evidence(self) -> list[dict]:
        self.study()
        result = []
        for row in self.connection.execute("SELECT * FROM evidence ORDER BY rowid"):
            item = dict(row)
            item["result"] = json.loads(item.pop("result_json"))
            item["provenance"] = json.loads(item.pop("provenance_json"))
            result.append(item)
        return result

    def recover(self) -> list[dict]:
        """Caller holds the controller lock. Unknown elapsed time remains NULL."""
        changed = []
        with self.transaction():
            self.study()
            rows = self.connection.execute("SELECT * FROM runs WHERE status='running'").fetchall()
            for run in rows:
                self.connection.execute(
                    """UPDATE runs SET status='interrupted', ended_at=?,
                       error='controller interrupted; worker outcome and elapsed time unknown'
                       WHERE run_id=?""", (utc_now(), run["run_id"]),
                )
                self.connection.execute(
                    "UPDATE tasks SET status='needs_review' WHERE study_id=? AND task_id=?",
                    (run["study_id"], run["task_id"]),
                )
                changed.append({"task_id": run["task_id"], "run_id": run["run_id"]})
        return changed

    def retry(self, task_id: str) -> dict:
        with self.transaction():
            task = self.task(task_id)
            if task["kind"] != "demo_mean" or task["status"] not in ("failed", "needs_review"):
                raise ARFError("retry requires a failed or needs_review demo task")
            self.connection.execute("UPDATE tasks SET status='pending' WHERE task_id=?", (task_id,))
        return self.task(task_id)
