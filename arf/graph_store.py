"""Explicit schema v3, separate from authoritative execution/planning storage."""

import sqlite3

from arf.plan_models import PlanError
from arf.plan_store import PLAN_SCHEMA, _schema_objects
from arf.store import SCHEMA, Store


class GraphError(PlanError):
    """Internal graph contract error; never an execution authorization."""


GRAPH_SCHEMA = [
    """CREATE TABLE graph_operations (
        study_id TEXT NOT NULL REFERENCES studies(study_id),
        seq INTEGER NOT NULL CHECK(seq > 0),
        operation_id TEXT NOT NULL UNIQUE,
        kind TEXT NOT NULL,
        actor BLOB NOT NULL,
        request BLOB NOT NULL CHECK(length(request)<=65536),
        result BLOB NOT NULL,
        committed_at TEXT NOT NULL,
        PRIMARY KEY(study_id,seq)
    )""",
    """CREATE TABLE graph_ideas (
        idea_id TEXT PRIMARY KEY,
        study_id TEXT NOT NULL REFERENCES studies(study_id),
        kind TEXT NOT NULL CHECK(kind IN ('Q','H','C')),
        origin BLOB NOT NULL,
        seq INTEGER NOT NULL,
        FOREIGN KEY(study_id,seq) REFERENCES graph_operations(study_id,seq)
            DEFERRABLE INITIALLY DEFERRED
    )""",
    """CREATE TABLE graph_idea_revisions (
        revision_id TEXT PRIMARY KEY,
        idea_id TEXT NOT NULL REFERENCES graph_ideas(idea_id),
        previous TEXT UNIQUE REFERENCES graph_idea_revisions(revision_id),
        body BLOB NOT NULL,
        study_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        UNIQUE(idea_id,seq),
        FOREIGN KEY(study_id,seq) REFERENCES graph_operations(study_id,seq)
            DEFERRABLE INITIALLY DEFERRED
    )""",
    "CREATE INDEX graph_idea_heads ON graph_idea_revisions(idea_id,seq DESC)",
    "CREATE INDEX graph_idea_history ON graph_idea_revisions(study_id,seq)",
    "CREATE INDEX graph_idea_kinds ON graph_ideas(study_id,kind,idea_id)",
    """CREATE TABLE graph_links (
        link_id TEXT PRIMARY KEY,
        study_id TEXT NOT NULL REFERENCES studies(study_id),
        type TEXT NOT NULL CHECK(type IN ('ADDRESSES','INVESTIGATES','MOTIVATED_BY',
            'DERIVED_FROM','ASSESSES','USES_BASELINE')),
        seq INTEGER NOT NULL,
        FOREIGN KEY(study_id,seq) REFERENCES graph_operations(study_id,seq)
            DEFERRABLE INITIALLY DEFERRED
    )""",
    """CREATE TABLE graph_link_revisions (
        revision_id TEXT PRIMARY KEY,
        link_id TEXT NOT NULL REFERENCES graph_links(link_id),
        previous TEXT UNIQUE REFERENCES graph_link_revisions(revision_id),
        source_role TEXT NOT NULL,
        source_id TEXT NOT NULL,
        target_role TEXT NOT NULL,
        target_id TEXT NOT NULL,
        body BLOB NOT NULL,
        visibility TEXT NOT NULL CHECK(visibility IN ('unreviewed','withdrawn')),
        study_id TEXT NOT NULL,
        seq INTEGER NOT NULL,
        UNIQUE(link_id,seq),
        FOREIGN KEY(study_id,seq) REFERENCES graph_operations(study_id,seq)
            DEFERRABLE INITIALLY DEFERRED
    )""",
    "CREATE INDEX graph_link_heads ON graph_link_revisions(link_id,seq DESC)",
    "CREATE INDEX graph_link_history ON graph_link_revisions(study_id,seq)",
    "CREATE INDEX graph_link_sources ON graph_link_revisions(source_role,source_id,seq)",
    "CREATE INDEX graph_link_targets ON graph_link_revisions(target_role,target_id,seq)",
    """CREATE TABLE graph_registrations (
        study_id TEXT NOT NULL REFERENCES studies(study_id),
        proposal_id TEXT NOT NULL REFERENCES plan_proposals(proposal_id),
        idea_id TEXT NOT NULL UNIQUE REFERENCES graph_ideas(idea_id),
        revision_id TEXT NOT NULL REFERENCES graph_idea_revisions(revision_id),
        provenance BLOB NOT NULL,
        seq INTEGER NOT NULL,
        PRIMARY KEY(study_id,proposal_id),
        FOREIGN KEY(study_id,seq) REFERENCES graph_operations(study_id,seq)
            DEFERRABLE INITIALLY DEFERRED
    )""",
    """CREATE TABLE graph_baselines (
        baseline_id TEXT PRIMARY KEY,
        study_id TEXT NOT NULL REFERENCES studies(study_id),
        scope TEXT NOT NULL,
        body BLOB NOT NULL,
        seq INTEGER NOT NULL,
        FOREIGN KEY(study_id,seq) REFERENCES graph_operations(study_id,seq)
            DEFERRABLE INITIALLY DEFERRED
    )""",
    """CREATE TABLE graph_transitions (
        transition_id TEXT PRIMARY KEY,
        study_id TEXT NOT NULL REFERENCES studies(study_id),
        scope TEXT NOT NULL,
        old_baseline TEXT REFERENCES graph_baselines(baseline_id),
        new_baseline TEXT NOT NULL REFERENCES graph_baselines(baseline_id),
        body BLOB NOT NULL,
        seq INTEGER NOT NULL,
        CHECK(old_baseline IS NULL OR old_baseline <> new_baseline),
        UNIQUE(study_id,scope,seq),
        FOREIGN KEY(study_id,seq) REFERENCES graph_operations(study_id,seq)
            DEFERRABLE INITIALLY DEFERRED
    )""",
    "CREATE INDEX graph_baseline_scopes ON graph_baselines(study_id,scope,seq)",
    "CREATE INDEX graph_transition_scopes ON graph_transitions(study_id,scope,seq DESC)",
]
for _table in ("graph_operations", "graph_ideas", "graph_idea_revisions", "graph_links",
               "graph_link_revisions", "graph_registrations", "graph_baselines", "graph_transitions"):
    for _action in ("UPDATE", "DELETE"):
        GRAPH_SCHEMA.append(
            f"CREATE TRIGGER {_table}_no_{_action.lower()} BEFORE {_action} ON {_table} "
            f"BEGIN SELECT RAISE(ABORT, '{_table} is immutable'); END"
        )


def verify(store: Store, version: int) -> None:
    if version == 4:
        from arf.decision_store import verify as verify_decisions
        return verify_decisions(store)
    with sqlite3.connect(":memory:") as reference:
        for statement in SCHEMA + PLAN_SCHEMA + (GRAPH_SCHEMA if version == 3 else []):
            reference.execute(statement)
        expected = _schema_objects(reference)
    if _schema_objects(store.connection) != expected:
        raise GraphError("schema", "database does not match the known ARF schema")
    if store.connection.execute("PRAGMA foreign_key_check").fetchone():
        raise GraphError("schema", "database contains foreign key violations")


def migrate(store: Store) -> dict:
    with store.transaction():
        version = store.connection.execute("PRAGMA user_version").fetchone()[0]
        if version not in (2, 3, 4):
            raise GraphError("schema", "graph migration requires explicit v1 to v2 migration first")
        verify(store, version)
        if version in (3, 4):
            return {"schema_version": 3, "status": "already_current"}
        for statement in GRAPH_SCHEMA:
            store.connection.execute(statement)
        store.connection.execute("PRAGMA user_version=3")
        verify(store, 3)
    return {"schema_version": 3, "status": "migrated"}
