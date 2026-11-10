"""Additive, immutable v4 decision ledger; no legacy row migrations."""
import sqlite3

from arf.graph_store import GRAPH_SCHEMA, verify as verify_graph
from arf.plan_models import PlanError
from arf.plan_store import PLAN_SCHEMA, _schema_objects
from arf.store import SCHEMA, Store


DECISION_SCHEMA = [
    '''CREATE TABLE decision_contexts (
        context_id TEXT PRIMARY KEY, study_id TEXT NOT NULL REFERENCES studies(study_id),
        charter_sha256 TEXT NOT NULL, body BLOB NOT NULL CHECK(length(body)<=2097152),
        created_at TEXT NOT NULL, UNIQUE(study_id,context_id))''',
    '''CREATE TABLE decision_candidates (
        study_id TEXT NOT NULL REFERENCES studies(study_id), candidate_id TEXT NOT NULL,
        version INTEGER NOT NULL CHECK(version>0), previous INTEGER,
        origin_key TEXT NOT NULL, body BLOB NOT NULL CHECK(length(body)<=65536),
        task_id TEXT, created_at TEXT NOT NULL,
        PRIMARY KEY(study_id,candidate_id,version),
        CHECK((version=1 AND previous IS NULL) OR (version>1 AND previous IS NOT NULL AND previous=version-1)),
        FOREIGN KEY(study_id,candidate_id,previous)
            REFERENCES decision_candidates(study_id,candidate_id,version),
        FOREIGN KEY(study_id,task_id) REFERENCES tasks(study_id,task_id))''',
    '''CREATE TABLE decision_batches (
        request_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL,
        study_id TEXT NOT NULL REFERENCES studies(study_id), result BLOB NOT NULL,
        created_at TEXT NOT NULL)''',
    '''CREATE TABLE research_decisions (
        decision_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL,
        study_id TEXT NOT NULL, context_id TEXT NOT NULL,
        previous TEXT, request BLOB NOT NULL, result BLOB NOT NULL CHECK(length(result)<=262144),
        wall_seconds REAL NOT NULL CHECK(wall_seconds>=0), created_at TEXT NOT NULL,
        UNIQUE(study_id,decision_id),
        FOREIGN KEY(study_id,context_id) REFERENCES decision_contexts(study_id,context_id),
        FOREIGN KEY(study_id,previous) REFERENCES research_decisions(study_id,decision_id))''',
    '''CREATE TABLE decision_members (
        study_id TEXT NOT NULL, decision_id TEXT NOT NULL, candidate_id TEXT NOT NULL,
        version INTEGER NOT NULL, ordinal INTEGER NOT NULL CHECK(ordinal>=0),
        priority_group INTEGER, body BLOB NOT NULL,
        PRIMARY KEY(study_id,decision_id,candidate_id), UNIQUE(decision_id,ordinal),
        FOREIGN KEY(study_id,decision_id) REFERENCES research_decisions(study_id,decision_id),
        FOREIGN KEY(study_id,candidate_id,version)
            REFERENCES decision_candidates(study_id,candidate_id,version))''',
    '''CREATE TABLE decision_publications (
        publication_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL,
        study_id TEXT NOT NULL, decision_id TEXT NOT NULL, previous TEXT UNIQUE,
        result BLOB NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(study_id,publication_id),
        FOREIGN KEY(study_id,decision_id) REFERENCES research_decisions(study_id,decision_id),
        FOREIGN KEY(study_id,previous) REFERENCES decision_publications(study_id,publication_id))''',
    'CREATE UNIQUE INDEX decision_initial_publication ON decision_publications(study_id) WHERE previous IS NULL',
    '''CREATE TABLE decision_assessments (
        assessment_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL, study_id TEXT NOT NULL,
        decision_id TEXT NOT NULL, publication_id TEXT NOT NULL, context_id TEXT NOT NULL,
        result BLOB NOT NULL, created_at TEXT NOT NULL,
        UNIQUE(study_id,decision_id,assessment_id),
        FOREIGN KEY(study_id,decision_id) REFERENCES research_decisions(study_id,decision_id),
        FOREIGN KEY(study_id,publication_id) REFERENCES decision_publications(study_id,publication_id),
        FOREIGN KEY(study_id,context_id) REFERENCES decision_contexts(study_id,context_id))''',
    '''CREATE TABLE decision_dispatches (
        dispatch_id TEXT PRIMARY KEY, request_sha256 TEXT NOT NULL,
        study_id TEXT NOT NULL REFERENCES studies(study_id), decision_id TEXT,
        publication_id TEXT, assessment_id TEXT, task_id TEXT, run_id TEXT UNIQUE,
        result BLOB NOT NULL, created_at TEXT NOT NULL,
        CHECK((task_id IS NULL AND run_id IS NULL) OR
              (task_id IS NOT NULL AND run_id IS NOT NULL AND assessment_id IS NOT NULL
               AND decision_id IS NOT NULL AND publication_id IS NOT NULL)),
        FOREIGN KEY(study_id,decision_id) REFERENCES research_decisions(study_id,decision_id),
        FOREIGN KEY(study_id,publication_id) REFERENCES decision_publications(study_id,publication_id),
        FOREIGN KEY(study_id,assessment_id) REFERENCES decision_assessments(study_id,assessment_id),
        FOREIGN KEY(study_id,task_id,run_id) REFERENCES runs(study_id,task_id,run_id))''',
    'CREATE INDEX decision_candidate_heads ON decision_candidates(study_id,candidate_id,version DESC)',
    'CREATE INDEX decision_history ON research_decisions(study_id,created_at,decision_id)',
]
# A separate composite key permits a recompute assessment to precede a new decision.
DECISION_SCHEMA.insert(-2, 'CREATE UNIQUE INDEX decision_assessment_key ON decision_assessments(study_id,assessment_id)')
for _table in ('decision_contexts', 'decision_candidates', 'decision_batches',
               'research_decisions', 'decision_members', 'decision_publications',
               'decision_assessments', 'decision_dispatches'):
    for _action in ('UPDATE', 'DELETE'):
        DECISION_SCHEMA.append(
            f'CREATE TRIGGER {_table}_no_{_action.lower()} BEFORE {_action} ON {_table} '
            f"BEGIN SELECT RAISE(ABORT, '{_table} is immutable'); END")


def verify(store: Store, *, required_only: bool = False) -> None:
    with sqlite3.connect(':memory:') as reference:
        for statement in SCHEMA + PLAN_SCHEMA + GRAPH_SCHEMA + DECISION_SCHEMA:
            reference.execute(statement)
        expected = _schema_objects(reference)
    actual = _schema_objects(store.connection)
    if (any(actual.get(k) != v for k, v in expected.items()) if required_only else actual != expected):
        raise PlanError('schema', 'database does not match known v4 schema')
    if store.connection.execute('PRAGMA foreign_key_check').fetchone():
        raise PlanError('schema', 'foreign key violations')


def migrate_decisions(store: Store) -> dict:
    with store.transaction():
        version = store.connection.execute('PRAGMA user_version').fetchone()[0]
        if version == 4:
            verify(store)
            return {'schema_version': 4, 'status': 'already_current'}
        if version != 3:
            raise PlanError('schema', 'decision migration requires explicit v3')
        verify_graph(store, 3)
        for statement in DECISION_SCHEMA:
            store.connection.execute(statement)
        store.connection.execute('PRAGMA user_version=4')
        verify(store)
    return {'schema_version': 4, 'status': 'migrated'}
