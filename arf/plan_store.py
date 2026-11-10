"""Version 2 additive persistence, consistent context snapshots and audit views."""

import base64
import json
import sqlite3
from typing import Any

from arf.plan_models import (
    CANONICAL_VERSION, CONTEXT_LIMIT, EXPORT_VERSION, PlanError, action_hash,
    canonical, hash_text, normalize_response, proposal_content, sha,
)
from arf.store import SCHEMA, Store, utc_now


PLAN_SCHEMA = [
    """CREATE TABLE plan_contexts (
        context_sha256 TEXT PRIMARY KEY,
        study_id TEXT NOT NULL REFERENCES studies(study_id),
        charter_sha256 TEXT NOT NULL,
        export_version INTEGER NOT NULL CHECK(export_version=1),
        canonical BLOB NOT NULL CHECK(length(canonical)<=1048576),
        created_at TEXT NOT NULL
    )""",
    """CREATE TABLE plan_requests (
        request_id TEXT PRIMARY KEY,
        context_sha256 TEXT NOT NULL REFERENCES plan_contexts(context_sha256),
        fixture TEXT NOT NULL,
        provider_name TEXT NOT NULL,
        provider_version TEXT NOT NULL,
        prompt_version TEXT NOT NULL,
        prompt BLOB NOT NULL,
        prompt_sha256 TEXT NOT NULL,
        policy_version TEXT NOT NULL,
        policy_sha256 TEXT NOT NULL,
        started_at TEXT NOT NULL
    )""",
    """CREATE TABLE plan_proposals (
        proposal_id TEXT PRIMARY KEY,
        content_sha256 TEXT NOT NULL UNIQUE,
        action_sha256 TEXT UNIQUE,
        study_id TEXT NOT NULL REFERENCES studies(study_id),
        charter_sha256 TEXT NOT NULL,
        context_sha256 TEXT NOT NULL REFERENCES plan_contexts(context_sha256),
        canonicalization_version INTEGER NOT NULL CHECK(canonicalization_version=1),
        envelope BLOB NOT NULL,
        policy_version TEXT NOT NULL,
        policy_sha256 TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(proposal_id,content_sha256,study_id,charter_sha256,context_sha256,policy_version,policy_sha256)
    )""",
    """CREATE TABLE plan_results (
        request_id TEXT PRIMARY KEY REFERENCES plan_requests(request_id),
        status TEXT NOT NULL CHECK(status IN ('valid','invalid','review_required')),
        proposal_id TEXT REFERENCES plan_proposals(proposal_id),
        raw BLOB CHECK(length(raw)<=65536),
        raw_sha256 TEXT,
        raw_size_bytes INTEGER,
        diagnostic TEXT,
        completed_at TEXT NOT NULL,
        CHECK((status='valid' AND proposal_id IS NOT NULL AND raw IS NOT NULL
               AND raw_sha256 IS NOT NULL AND raw_size_bytes=length(raw) AND diagnostic IS NULL)
           OR (status<>'valid' AND proposal_id IS NULL AND diagnostic IS NOT NULL))
    )""",
    """CREATE TABLE plan_decisions (
        proposal_id TEXT PRIMARY KEY,
        content_sha256 TEXT NOT NULL,
        study_id TEXT NOT NULL,
        charter_sha256 TEXT NOT NULL,
        context_sha256 TEXT NOT NULL,
        policy_version TEXT NOT NULL,
        policy_sha256 TEXT NOT NULL,
        decision TEXT NOT NULL CHECK(decision IN ('approve','reject')),
        operator TEXT NOT NULL CHECK(length(operator)>0),
        decided_at TEXT NOT NULL,
        UNIQUE(proposal_id,decision),
        FOREIGN KEY(proposal_id,content_sha256,study_id,charter_sha256,context_sha256,policy_version,policy_sha256)
          REFERENCES plan_proposals(proposal_id,content_sha256,study_id,charter_sha256,context_sha256,policy_version,policy_sha256)
    )""",
    """CREATE TABLE plan_receipts (
        proposal_id TEXT PRIMARY KEY,
        decision TEXT NOT NULL DEFAULT 'approve' CHECK(decision='approve'),
        task_id TEXT NOT NULL,
        study_id TEXT NOT NULL,
        spec_sha256 TEXT NOT NULL,
        imported_at TEXT NOT NULL,
        UNIQUE(study_id,task_id),
        FOREIGN KEY(proposal_id,decision) REFERENCES plan_decisions(proposal_id,decision),
        FOREIGN KEY(study_id,task_id) REFERENCES tasks(study_id,task_id)
    )""",
]
for _table in ("plan_contexts", "plan_requests", "plan_proposals", "plan_results", "plan_decisions", "plan_receipts"):
    for _action in ("UPDATE", "DELETE"):
        PLAN_SCHEMA.append(
            f"CREATE TRIGGER {_table}_no_{_action.lower()} BEFORE {_action} ON {_table} "
            f"BEGIN SELECT RAISE(ABORT, '{_table} is immutable'); END"
        )


def _schema_objects(connection: sqlite3.Connection) -> dict:
    return {row[0]: (row[1], row[2]) for row in connection.execute(
        "SELECT name,type,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%'"
    )}


def verify_schema(store: Store, version: int) -> None:
    # Compare to SQLite's own normalized representation of our known DDL.
    with sqlite3.connect(":memory:") as reference:
        for statement in SCHEMA + (PLAN_SCHEMA if version == 2 else []):
            reference.execute(statement)
        expected = _schema_objects(reference)
    actual = _schema_objects(store.connection)
    if actual != expected:
        raise PlanError("schema", "database does not match the known ARF schema")


def migrate(store: Store) -> dict:
    with store.transaction():
        version = store.connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (1, 2):
            raise PlanError("schema", "unsupported database version")
        verify_schema(store, version)
        if version == 2:
            return {"schema_version": 2, "status": "already_current"}
        for statement in PLAN_SCHEMA:
            store.connection.execute(statement)
        store.connection.execute("PRAGMA user_version=2")
    return {"schema_version": 2, "status": "migrated"}


class PlanStore:
    def __init__(self, store: Store):
        self.store = store
        self.db = store.connection
        if self.db.execute("PRAGMA user_version").fetchone()[0] != 2:
            raise PlanError("schema", "planning requires explicit plan migrate")
        # Required objects are verified; extra developer diagnostic triggers are
        # harmless here. Migration itself checks the complete known schema.
        with sqlite3.connect(":memory:") as reference:
            for statement in PLAN_SCHEMA:
                reference.execute(statement)
            expected = _schema_objects(reference)
        actual = _schema_objects(self.db)
        if any(actual.get(name) != value for name, value in expected.items()):
            raise PlanError("schema", "planning schema is incomplete or unrelated")

    def context_bytes(self) -> bytes:
        """Caller owns a read or write transaction for one consistent snapshot."""
        if not self.db.in_transaction:
            raise PlanError("invalid", "context export requires a transaction")
        study = self.store.study()
        study.pop("singleton")
        study["source_base64"] = base64.b64encode(study.pop("source")).decode("ascii")
        study["success_criteria"] = json.loads(study.pop("success_criteria_json"))
        study["constraints"] = json.loads(study.pop("constraints_json"))
        tasks = self.store.tasks()
        for task in tasks:
            task["dependencies"].sort()
            task.pop("blockers")  # Derived from included statuses/dependencies.
        runs = [self.store._run_view(row) for row in self.db.execute("SELECT * FROM runs ORDER BY run_id")]
        evidence = sorted(self.store.evidence(), key=lambda e: e["evidence_id"])
        raw = canonical({"export_version": EXPORT_VERSION, "canonicalization_version": CANONICAL_VERSION,
                         "study": study, "tasks": tasks, "runs": runs, "evidence": evidence})
        if len(raw) > CONTEXT_LIMIT:
            raise PlanError("limit", "complete context exceeds 1 MiB; no evidence was dropped")
        return raw

    def export(self) -> dict:
        # Deferred BEGIN permits a consistent read without reserving a writer.
        self.db.execute("BEGIN")
        try:
            raw = self.context_bytes()
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        digest = sha(raw)
        context = json.loads(raw)
        with self.store.transaction():
            self.db.execute(
                "INSERT OR IGNORE INTO plan_contexts VALUES (?,?,?,?,?,?)",
                (digest, context["study"]["study_id"], context["study"]["source_sha256"],
                 EXPORT_VERSION, raw, utc_now()),
            )
        return {"context_sha256": digest, "export_version": EXPORT_VERSION, "size_bytes": len(raw)}

    def context(self, digest: str) -> tuple[bytes, dict]:
        hash_text(digest)
        row = self.db.execute("SELECT * FROM plan_contexts WHERE context_sha256=?", (digest,)).fetchone()
        if row is None:
            raise PlanError("not_found", "unknown context hash; use plan export")
        raw = row["canonical"]
        data = json.loads(raw)
        study = self.store.study()
        if (sha(raw) != digest or canonical(data) != raw or data["export_version"] != EXPORT_VERSION
                or data["canonicalization_version"] != CANONICAL_VERSION
                or row["study_id"] != study["study_id"] or data["study"]["study_id"] != study["study_id"]
                or row["charter_sha256"] != study["source_sha256"]
                or data["study"]["source_sha256"] != study["source_sha256"]
                or base64.b64decode(data["study"]["source_base64"]) != study["source"]):
            raise PlanError("invalid", "stored context binding failed")
        return raw, data

    def proposal(self, proposal_id: str) -> dict:
        row = self.db.execute("SELECT * FROM plan_proposals WHERE proposal_id=?", (proposal_id,)).fetchone()
        if row is None:
            raise PlanError("not_found", "unknown valid proposal")
        return dict(row)

    def validate_proposal(self, proposal_id: str) -> tuple[dict, dict]:
        row = self.proposal(proposal_id)
        envelope = json.loads(row["envelope"])
        _, context = self.context(row["context_sha256"])
        expected_keys = {"proposal_version", "proposal_id", "study_id", "charter_sha256", "context_sha256",
                         "rationale", "evidence_refs", "action"}
        if set(envelope) != expected_keys or type(envelope["proposal_version"]) is not int or envelope["proposal_version"] != 1:
            raise PlanError("invalid", "unsupported proposal envelope/version")
        normalized = normalize_response(canonical({k: envelope[k] for k in ("rationale", "evidence_refs", "action")}), context)
        content = proposal_content(normalized, context, row["context_sha256"])
        digest = sha(canonical(content))
        expected = {"proposal_id": "proposal-" + digest, **content}
        if (envelope != expected or canonical(expected) != row["envelope"] or digest != row["content_sha256"]
                or row["proposal_id"] != expected["proposal_id"] or row["action_sha256"] != action_hash(content)
                or any(row[k] != content[k] for k in ("study_id", "charter_sha256", "context_sha256"))):
            raise PlanError("invalid", "proposal content binding failed")
        return row, envelope

    def decision(self, proposal_id: str) -> dict | None:
        row = self.db.execute("SELECT * FROM plan_decisions WHERE proposal_id=?", (proposal_id,)).fetchone()
        return dict(row) if row else None

    def receipt(self, proposal_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT proposal_id,task_id,study_id,spec_sha256,imported_at FROM plan_receipts WHERE proposal_id=?",
            (proposal_id,),
        ).fetchone()
        return dict(row) if row else None

    def request(self, request_id: str) -> dict:
        row = self.db.execute("""SELECT q.*,r.status,r.completed_at,r.raw_sha256,r.raw_size_bytes,
            r.raw,r.diagnostic FROM plan_requests q LEFT JOIN plan_results r USING(request_id)
            WHERE q.request_id=?""", (request_id,)).fetchone()
        if row is None:
            raise PlanError("not_found", "unknown planner request")
        result = dict(row)
        result["prompt_base64"] = base64.b64encode(result.pop("prompt")).decode("ascii")
        raw = result.pop("raw")
        result["raw_prefix_base64"] = base64.b64encode(raw).decode("ascii") if raw is not None else None
        result["status"] = result["status"] or "review_required"
        result["usage"] = None
        return result

    def show(self, proposal_id: str) -> dict[str, Any]:
        row, envelope = self.validate_proposal(proposal_id)
        requests = [self.request(r[0]) for r in self.db.execute(
            "SELECT request_id FROM plan_results WHERE proposal_id=? ORDER BY request_id", (proposal_id,)
        )]
        return {"envelope": envelope, "content_sha256": row["content_sha256"],
                "action_sha256": row["action_sha256"], "canonicalization_version": row["canonicalization_version"],
                "created_at": row["created_at"], "requests": requests,
                "context": self.context(row["context_sha256"])[1],
                "decision": self.decision(proposal_id), "receipt": self.receipt(proposal_id)}

    def list(self) -> list[dict]:
        return [self.show(r[0]) for r in self.db.execute("SELECT proposal_id FROM plan_proposals ORDER BY proposal_id")]
