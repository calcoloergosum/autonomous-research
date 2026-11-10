"""Bounded v4 projections. Deliberately imports no ARF writer or worker module."""
from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import sqlite3
import threading
import time
from typing import Iterator

API_LIMIT = 256 * 1024
CHECKPOINT_LIMIT = 3 * 1024 * 1024
KINDS = {'task': ('tasks', 'task_id'), 'dispatch': ('decision_dispatches', 'dispatch_id'),
         'run': ('runs', 'run_id'), 'evidence': ('evidence', 'evidence_id'),
         'decision': ('research_decisions', 'decision_id')}


class ObserverError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(code + ': ' + message)
        self.code, self.message, self.status = code, message, status


def encode(value: object, maximum: int = API_LIMIT) -> bytes:
    chunks, size = [], 0
    for chunk in json.JSONEncoder(ensure_ascii=False, allow_nan=False, separators=(',', ':')).iterencode(value):
        raw = chunk.encode('utf-8')
        size += len(raw)
        if size > maximum:
            raise ObserverError('limit', 'Complete response exceeds byte budget', 413)
        chunks.append(raw)
    return b''.join(chunks)


def stored_json(raw: bytes | str) -> dict:
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result
    try:
        value = json.loads(raw, object_pairs_hook=pairs,
                           parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite')))
        if not isinstance(value, dict):
            raise ValueError('object required')
        return value
    except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
        raise ObserverError('corrupt_storage', 'Invalid stored JSON', 500) from exc


def identifier(value: str | None) -> str:
    try:
        valid = isinstance(value, str) and bool(value) and len(value.encode('utf-8')) <= 4096 and '\x00' not in value
    except UnicodeError:
        valid = False
    if not valid:
        raise ObserverError('invalid_id', 'Invalid bounded identifier')
    return value


def ref(kind: str, identity: str, **extra) -> dict:
    table = KINDS[kind][0] if kind in KINDS else {
        'candidate': 'decision_candidates', 'publication': 'decision_publications',
        'assessment': 'decision_assessments', 'context': 'decision_contexts', 'graph': 'graph_link_revisions'}[kind]
    scope = 'current_execution' if kind in ('task', 'run') else 'recorded_history'
    return {'kind': kind, 'id': identity, 'revision': None, 'source_table': table,
            'temporal_scope': scope, **extra}


class ObserverSource:
    """One persistent detector connection; every joined response has a short snapshot."""
    def __init__(self, path: str | Path):
        self.path = Path(path).absolute()  # preserve the requested path to detect symlink replacement
        self.lock = threading.RLock()
        self.db: sqlite3.Connection | None = None
        self.epoch, self.generation = secrets.token_hex(16), 0
        self.cursor_key = secrets.token_bytes(32)
        self._open(initial=True)

    def __enter__(self) -> ObserverSource:
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        if self.db is not None:
            self.db.close()
            self.db = None

    def _identity(self):
        stat = self.path.stat()
        if not self.path.is_file():
            raise OSError('not a regular file')
        return stat.st_dev, stat.st_ino

    def _open(self, *, initial=False):
        try:
            identity = self._identity()
            db = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, isolation_level=None,
                                 timeout=0.2, check_same_thread=False)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA query_only=ON')
            db.setlimit(sqlite3.SQLITE_LIMIT_LENGTH, CHECKPOINT_LIMIT)
            old = self.db
            self.db = db
            try:
                self._verify()
                study = db.execute('SELECT study_id,question,source_sha256 FROM studies').fetchone()
                if study is None or db.execute('SELECT count(*) FROM studies').fetchone()[0] != 1:
                    raise ObserverError('corrupt_storage', 'Expected one stored study', 500)
                if identity != self._identity():
                    raise ObserverError('stale_session', 'Source replaced while opening', 409)
                self.study = dict(study)
                self.identity = identity
                self.data_version = db.execute('PRAGMA data_version').fetchone()[0]
            except BaseException:
                db.close()
                self.db = old
                raise
            if old is not None:
                old.close()
            if not initial:
                self.epoch, self.generation = secrets.token_hex(16), 0
                self.cursor_key = secrets.token_bytes(32)
        except OSError as exc:
            raise ObserverError('unsupported_schema' if initial else 'stale_session',
                                'Existing readable v4 source required', 409) from exc
        except sqlite3.Error as exc:
            raise self.sql_error(exc) from exc

    def _verify(self):
        if self.db.execute('PRAGMA user_version').fetchone()[0] != 4:
            raise ObserverError('unsupported_schema', 'Observer requires known schema v4; no migration performed', 409)
        expected = json.loads(Path(__file__).with_name('observer_schema.json').read_text())
        actual = {r[0]: r[1] for r in self.db.execute(
            "SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'")}
        normalize = lambda sql: ' '.join(sql.split())
        if any(name not in actual or normalize(actual[name]) != normalize(sql) for name, sql in expected.items()):
            raise ObserverError('unsupported_schema', 'Source does not match known v4 objects', 409)

    @staticmethod
    def sql_error(exc):
        code = getattr(exc, 'sqlite_errorcode', 0) & 255
        if code in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED, sqlite3.SQLITE_CANTOPEN, sqlite3.SQLITE_IOERR):
            return ObserverError('temporarily_unavailable', 'Source temporarily unavailable; retain stale view', 503)
        if code in (sqlite3.SQLITE_TOOBIG, sqlite3.SQLITE_INTERRUPT):
            return ObserverError('limit', 'Read exceeds bounded query budget', 413)
        return ObserverError('corrupt_storage', 'Cannot safely read stored data', 500)

    def refresh(self):
        try:
            if self._identity() != self.identity:
                self._open()
                return
            version = self.db.execute('PRAGMA data_version').fetchone()[0]
            if version != self.data_version:
                self._verify()
                study = self.db.execute('SELECT study_id,question,source_sha256 FROM studies').fetchone()
                if study is None or dict(study) != self.study:
                    self._open()
                    return
                self.data_version = version
                self.generation += 1
        except OSError as exc:
            raise ObserverError('stale_session', 'Source unavailable or replaced; recheck required', 409) from exc

    @contextmanager
    def snapshot(self) -> Iterator[None]:
        deadline = time.monotonic() + 1.0
        self.db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        self.db.execute('BEGIN')
        try:
            # Establish the snapshot before any joined reads.
            self.db.execute('SELECT study_id FROM studies').fetchone()
            yield
        finally:
            self.db.rollback()
            self.db.set_progress_handler(None, 0)

    def envelope(self, data: dict, scope='current_execution') -> dict:
        return {'api_version': 1, 'study_id': self.study['study_id'], 'temporal_scope': scope, 'data': data}

    def read(self, route: str, query: dict[str, str]) -> dict:
        with self.lock:
            try:
                self.refresh()
                with self.snapshot():
                    if route == 'meta':
                        self.parameters(query, set())
                        result = self.envelope({'question': self.study['question'],
                            'charter_sha256': self.study['source_sha256'], 'schema_version': 4,
                            'observer_version': 1, 'epoch': self.epoch, 'generation': self.generation,
                            'capabilities': ['read_only', 'live_poll', 'decision_checkpoint']}, 'recorded_history')
                    elif route == 'changes':
                        result = self.changes(query)
                    elif route == 'overview':
                        result = self.overview(query)
                    elif route == 'checkpoint':
                        result = self.checkpoint(query)
                    elif route == 'trace':
                        result = self.trace(query)
                    else:
                        raise ObserverError('not_found', 'Unknown read resource', 404)
                    # An atomic path replacement during the snapshot cannot be served as the new source.
                    if self._identity() != self.identity:
                        raise ObserverError('stale_session', 'Source replaced during read', 409)
                    maximum = CHECKPOINT_LIMIT if route == 'checkpoint' else API_LIMIT
                    try:
                        encode(result, maximum)
                    except ObserverError as exc:
                        if route == 'checkpoint':
                            raise ObserverError('limit', 'Complete checkpoint exceeds budget: ' + query['id'], 413) from exc
                        raise
                    return result
            except sqlite3.Error as exc:
                raise self.sql_error(exc) from exc
            except OSError as exc:
                raise ObserverError('stale_session', 'Source unavailable during read', 409) from exc
            except (KeyError, TypeError, ValueError, RecursionError) as exc:
                raise ObserverError('corrupt_storage', 'Unexpected stored record shape', 500) from exc

    @staticmethod
    def parameters(query, allowed, required=()):
        if set(query) - allowed or set(required) - set(query):
            raise ObserverError('invalid_query', 'Unexpected or missing query parameter')

    def changes(self, query):
        self.parameters(query, {'since'})
        token = query.get('since')
        reset, changed = token is None, True
        if token is not None:
            if len(token) > 256:
                raise ObserverError('invalid_query', 'Invalid change token')
            parts = token.split('.')
            if (len(parts) != 3 or parts[0] != 'v1' or len(parts[1]) != 32
                    or any(c not in '0123456789abcdef' for c in parts[1])
                    or not parts[2].isascii() or not parts[2].isdigit() or len(parts[2]) > 16):
                raise ObserverError('invalid_query', 'Invalid change token')
            reset = parts[1] != self.epoch or int(parts[2]) > self.generation
            changed = reset or int(parts[2]) != self.generation
        return self.envelope({'epoch': self.epoch, 'generation': self.generation,
            'token': f'v1.{self.epoch}.{self.generation}', 'changed': changed, 'reset_required': reset,
            'observed_at': datetime.now(timezone.utc).isoformat()})

    def cursor(self, kind, key):
        raw = encode([1, self.epoch, kind, key], 16384)
        signature = hmac.new(self.cursor_key, raw, hashlib.sha256).digest()
        return base64.urlsafe_b64encode(signature + raw).decode().rstrip('=')

    def cursor_key_for(self, token, kind):
        if token is None:
            return None
        try:
            if len(token) > 16384:
                raise ValueError()
            value = base64.b64decode(token + '=' * (-len(token) % 4), altchars=b'-_', validate=True)
            raw = value[32:]
            if not hmac.compare_digest(value[:32], hmac.new(self.cursor_key, raw, hashlib.sha256).digest()):
                raise ValueError()
            version, epoch, saved_kind, key = json.loads(raw)
            if (version, epoch, saved_kind) != (1, self.epoch, kind):
                raise ValueError()
            if kind == 'task' and (type(key) is not int or key < 1):
                raise ValueError()
            if kind == 'dispatch' and (not isinstance(key, list) or len(key) != 2 or not all(isinstance(k, str) for k in key)):
                raise ValueError()
            return key
        except (ValueError, TypeError, UnicodeError) as exc:
            raise ObserverError('invalid_query', 'Invalid source-scoped cursor') from exc

    def rows(self, sql, args=(), cap=64):
        rows = self.db.execute(sql + ' LIMIT ?', (*args, cap + 1)).fetchall()
        if len(rows) > cap:
            raise ObserverError('limit', 'Relationship exceeds bounded selection; select an exact source ID', 413)
        return rows

    def one(self, table, key, value):
        row = self.db.execute(f'SELECT * FROM {table} WHERE study_id=? AND {key}=?',
                              (self.study['study_id'], value)).fetchone()
        if row is None:
            raise ObserverError('not_found', 'Exact stored record absent', 404)
        return row

    def task(self, row):
        value = dict(row)
        value['input'] = stored_json(value.pop('input_json'))
        deps = self.rows('''SELECT d.prerequisite_id,t.status FROM dependencies d JOIN tasks t
            ON t.study_id=d.study_id AND t.task_id=d.prerequisite_id
            WHERE d.study_id=? AND d.task_id=? ORDER BY t.sequence''', (self.study['study_id'], value['task_id']))
        value['dependencies'] = [r['prerequisite_id'] for r in deps]
        value['blockers'] = [{'task_id': r['prerequisite_id'], 'status': r['status']} for r in deps if r['status'] != 'succeeded']
        value['temporal_scope'] = 'current_execution'
        return value

    @staticmethod
    def execution(row, kind):
        value = dict(row)
        for field in ('result', 'provenance'):
            if field + '_json' in value:
                raw = value.pop(field + '_json')
                value[field] = stored_json(raw) if raw is not None else None
        value['temporal_scope'] = 'current_execution' if kind == 'run' else 'recorded_history'
        return value

    @staticmethod
    def receipt(row):
        return {**stored_json(row['result']), 'created_at': row['created_at'],
                'decision_id': row['decision_id'], 'publication_id': row['publication_id'],
                'task_id': row['task_id'], 'run_id': row['run_id'], 'temporal_scope': 'recorded_history'}

    def overview(self, query):
        self.parameters(query, {'limit', 'task_cursor', 'dispatch_cursor'})
        raw_limit = query.get('limit', '20')
        if not raw_limit.isascii() or not raw_limit.isdigit() or len(raw_limit) > 2 or not 1 <= int(raw_limit) <= 50:
            raise ObserverError('invalid_query', 'limit must be 1..50')
        limit = int(raw_limit)
        task_key = self.cursor_key_for(query.get('task_cursor'), 'task')
        dispatch_key = self.cursor_key_for(query.get('dispatch_cursor'), 'dispatch')
        tasks = self.db.execute('SELECT * FROM tasks WHERE study_id=? AND sequence>? ORDER BY sequence LIMIT ?',
                                (self.study['study_id'], task_key or 0, limit + 1)).fetchall()
        args = [self.study['study_id']]
        where = ''
        if dispatch_key:
            where = ' AND (created_at<? OR (created_at=? AND dispatch_id<?))'
            args += [dispatch_key[0], dispatch_key[0], dispatch_key[1]]
        dispatches = self.db.execute('SELECT * FROM decision_dispatches WHERE study_id=?' + where +
                                    ' ORDER BY created_at DESC,dispatch_id DESC LIMIT ?', (*args, limit + 1)).fetchall()
        counts = dict.fromkeys(('pending', 'running', 'succeeded', 'failed', 'needs_review'), 0)
        counts.update({r[0]: r[1] for r in self.db.execute('SELECT status,count(*) FROM tasks WHERE study_id=? GROUP BY status', (self.study['study_id'],))})
        latest = self.db.execute('SELECT decision_id FROM research_decisions WHERE study_id=? ORDER BY created_at DESC,decision_id DESC LIMIT 1', (self.study['study_id'],)).fetchone()
        head = self.db.execute('''SELECT p.publication_id FROM decision_publications p WHERE p.study_id=? AND
            NOT EXISTS (SELECT 1 FROM decision_publications n WHERE n.study_id=p.study_id AND n.previous=p.publication_id) LIMIT 1''', (self.study['study_id'],)).fetchone()
        return self.envelope({'task_counts': counts, 'tasks': [self.task(r) for r in tasks[:limit]],
            'task_next_cursor': self.cursor('task', tasks[limit-1]['sequence']) if len(tasks) > limit else None,
            'dispatches': [self.receipt(r) for r in dispatches[:limit]],
            'dispatch_next_cursor': self.cursor('dispatch', [dispatches[limit-1]['created_at'], dispatches[limit-1]['dispatch_id']]) if len(dispatches) > limit else None,
            'latest_decision_id': latest[0] if latest else None, 'publication_head_id': head[0] if head else None,
            'observed_generation': self.generation})

    def decision(self, identity):
        row = self.one('research_decisions', 'decision_id', identity)
        result = stored_json(row['result'])
        members = [stored_json(r['body']) for r in self.rows('SELECT * FROM decision_members WHERE study_id=? AND decision_id=? ORDER BY ordinal', (self.study['study_id'], identity))]
        if result['decision_id'] != identity or result['members'] != members:
            raise ObserverError('corrupt_storage', 'Saved membership mismatch', 500)
        return result

    def checkpoint(self, query):
        self.parameters(query, {'id'}, {'id'})
        identity = identifier(query['id'])
        decision = self.decision(identity)
        row = self.one('decision_contexts', 'context_id', decision['context_id'])
        raw = row['body']
        digest = hashlib.sha256(raw if isinstance(raw, bytes) else raw.encode()).hexdigest()
        context = stored_json(raw)
        if digest != row['context_id'] or context['study_id'] != self.study['study_id'] or context['charter_sha256'] != self.study['source_sha256']:
            raise ObserverError('corrupt_storage', 'Saved context identity mismatch', 500)
        return self.envelope({'decision_id': identity, 'context_id': row['context_id'], 'decision': decision,
            'context': context, 'capture_semantics': 'saved_context_input_not_global_time_travel',
            'selection_complete': context['selection_complete'], 'portfolio_completeness': context['portfolio_completeness'],
            'historical_execution_state': 'captured_execution_only'}, 'snapshot_at_decision')

    def trace(self, query):
        self.parameters(query, {'kind', 'id'}, {'kind', 'id'})
        kind, identity = query['kind'], identifier(query['id'])
        if kind not in KINDS:
            raise ObserverError('invalid_query', 'Unsupported trace kind')
        focus = self.one(*KINDS[kind], identity)
        sid = self.study['study_id']
        task_id = focus['task_id'] if kind in ('task', 'dispatch', 'run', 'evidence') else None
        task = self.task(self.one('tasks', 'task_id', task_id)) if task_id is not None else None
        runs, evidence, dispatches = [], [], []
        if task_id is not None:
            runs = [self.execution(r, 'run') for r in self.rows('SELECT * FROM runs WHERE study_id=? AND task_id=? ORDER BY started_at,run_id', (sid, task_id))]
            evidence = [self.execution(r, 'evidence') for r in self.rows('SELECT * FROM evidence WHERE study_id=? AND task_id=? ORDER BY created_at,evidence_id', (sid, task_id))]
            dispatches = [self.receipt(r) for r in self.rows('SELECT * FROM decision_dispatches WHERE study_id=? AND task_id=? ORDER BY created_at,dispatch_id', (sid, task_id))]
        if kind == 'dispatch' and not dispatches:
            dispatches = [self.receipt(focus)]
        candidates = [stored_json(r['body']) for r in self.rows('SELECT body FROM decision_candidates WHERE study_id=? AND task_id=? ORDER BY candidate_id,version', (sid, task_id))] if task_id else []
        links = []
        def link(relation, source, target, source_record_id):
            links.append({'relation': relation, 'source': source, 'target': target, 'source_record_id': source_record_id})
        for c in candidates:
            link('candidate_binding', ref('task', task_id), ref('candidate', c['candidate_id'], version=c['version']), c['candidate_id'])
        decision_ids = set()
        if kind == 'decision':
            decision_ids.add(identity)
        for d in dispatches:
            if d['decision_id']:
                decision_ids.add(d['decision_id'])
                link('dispatch_decision', ref('dispatch', d['dispatch_id']), ref('decision', d['decision_id']), d['dispatch_id'])
            if d['run_id']:
                link('dispatch_run', ref('dispatch', d['dispatch_id']), ref('run', d['run_id']), d['dispatch_id'])
        for c in candidates:
            rows = self.rows('SELECT decision_id FROM decision_members WHERE study_id=? AND candidate_id=? AND version=? ORDER BY decision_id', (sid, c['candidate_id'], c['version']))
            for r in rows:
                decision_ids.add(r['decision_id'])
                link('decision_member', ref('candidate', c['candidate_id'], version=c['version']), ref('decision', r['decision_id']), r['decision_id'])
        if len(decision_ids) > 64:
            raise ObserverError('limit', 'Too many relevant decisions; select an exact decision', 413)
        # Keep all relevant choices explicit. Only exact focus/receipt or a unique choice is embedded.
        selected_dispatch = next((d for d in dispatches if d['dispatch_id'] == identity), None) if kind == 'dispatch' else None
        if kind in ('run', 'evidence'):
            run_id = identity if kind == 'run' else focus['run_id']
            selected_dispatch = next((d for d in dispatches if d['run_id'] == run_id), None)
        if kind == 'decision':
            chosen = identity
        elif selected_dispatch is not None:
            chosen = selected_dispatch['decision_id']
        elif len(dispatches) == 1:
            chosen = dispatches[0]['decision_id']
        else:
            chosen = next(iter(decision_ids)) if len(decision_ids) == 1 else None
        decision = self.decision(chosen) if chosen else None
        publications, assessments = [], []
        if decision:
            for m in decision['members']:
                c = stored_json(self.db.execute('SELECT body FROM decision_candidates WHERE study_id=? AND candidate_id=? AND version=?', (sid, m['candidate_id'], m['version'])).fetchone()[0])
                if (c['candidate_id'], c['version']) not in {(c['candidate_id'], c['version']) for c in candidates}:
                    candidates.append(c)
                link('decision_member', ref('candidate', m['candidate_id'], version=m['version']), ref('decision', chosen), chosen)
                if c['binding']:
                    link('candidate_binding', ref('candidate', c['candidate_id'], version=c['version']),
                         ref('task', c['binding']['task_id']), c['candidate_id'])
            publications = [dict(stored_json(r['result']), temporal_scope='recorded_history') for r in self.rows('SELECT result FROM decision_publications WHERE study_id=? AND decision_id=? ORDER BY created_at,publication_id', (sid, chosen))]
            assessments = [dict(stored_json(r['result']), temporal_scope='recorded_history') for r in self.rows('SELECT result FROM decision_assessments WHERE study_id=? AND decision_id=? ORDER BY created_at,assessment_id', (sid, chosen))]
            link('captured_input', ref('decision', chosen), ref('context', decision['context_id'], temporal_scope='snapshot_at_decision'), chosen)
            for p in publications:
                link('published_decision', ref('publication', p['publication_id']), ref('decision', chosen), p['publication_id'])
            for a in assessments:
                link('assessed_decision', ref('assessment', a['assessment_id']), ref('decision', chosen), a['assessment_id'])
        run_id = focus['run_id'] if kind in ('run', 'evidence', 'dispatch') else None
        selected_run = next((r for r in runs if r['run_id'] == run_id), None) if run_id else (runs[0] if len(runs) == 1 else None)
        selected_evidence = next((e for e in evidence if e['evidence_id'] == identity), None) if kind == 'evidence' else next((e for e in evidence if selected_run and e['run_id'] == selected_run['run_id']), None)
        for r in runs:
            link('ATTEMPT_OF', ref('run', r['run_id']), ref('task', task_id), r['run_id'])
        for e in evidence:
            link('PRODUCES', ref('run', e['run_id']), ref('evidence', e['evidence_id']), e['evidence_id'])
        seeds = ([{'role': 'T', 'id': task_id, 'revision': None}] if task_id else []) + [
            {'role': 'R', 'id': r['run_id'], 'revision': None} for r in runs] + [
            {'role': 'E', 'id': e['evidence_id'], 'revision': None} for e in evidence]
        graph, nodes, frontier = self.graph_neighborhood(seeds)
        missing = []
        if not any(e['type'] == 'MOTIVATED_BY' for e in graph):
            missing.append('motivation:not_recorded')
        if not decision:
            missing.append('decision:select_exact_source' if decision_ids else 'decision:not_recorded')
        if task and not runs:
            missing.append('run:not_recorded')
        if not evidence:
            missing.append('evidence:not_recorded')
        selected_dispatch = selected_dispatch or (dispatches[0] if len(dispatches) == 1 else None)
        def associated(items, key, dispatch_key):
            if selected_dispatch and selected_dispatch.get(dispatch_key):
                return next((p for p in items if p[key] == selected_dispatch[dispatch_key]), None)
            return items[0] if len(items) == 1 else None
        return self.envelope({'focus': {'kind': kind, 'id': identity}, 'links': links,
            'task': task, 'dispatch': selected_dispatch, 'run': selected_run, 'evidence': selected_evidence,
            'runs': runs, 'evidence_records': evidence, 'dispatches': dispatches,
            'candidate_versions': [{**c, 'temporal_scope': 'recorded_history'} for c in candidates],
            'decision': {**decision, 'temporal_scope': 'recorded_history'} if decision else None,
            'members': [{**m, 'temporal_scope': 'recorded_history'} for m in decision['members']] if decision else [],
            'decisions': [ref('decision', d) for d in sorted(decision_ids)],
            'publication': associated(publications, 'publication_id', 'publication_id'),
            'assessment': associated(assessments, 'assessment_id', 'assessment_id'),
            'publications': publications, 'assessments': assessments,
            'graph_assertions': graph, 'graph_nodes': nodes, 'missing_relations': missing,
            'truncated': bool(frontier), 'continuation': {'graph_frontier': frontier} if frontier else None})

    def graph_neighborhood(self, seeds):
        """Two-hop semantic neighborhood of the exact linked execution records.

        Execution facts stay in trace.links. Semantic bodies and attribution are
        original revisions; graph traversal never manufactures motivation.
        """
        sid = self.study['study_id']
        queue = [(r, 0) for r in seeds[:32]]
        visited, edges, nodes, frontier = set(), {}, {}, []
        if len(seeds) > 32:
            frontier.extend(seeds[32:33])
        while queue:
            endpoint, depth = queue.pop(0)
            key = (endpoint['role'], endpoint['id'], endpoint.get('revision'))
            if key in visited:
                continue
            if len(visited) >= 32:
                frontier.append(endpoint)
                break
            visited.add(key)
            if endpoint['role'] in ('Q', 'H', 'C'):
                row = self.db.execute('''SELECT r.*,i.kind,i.origin,o.actor,o.operation_id,o.committed_at
                    FROM graph_idea_revisions r JOIN graph_ideas i ON i.study_id=r.study_id AND i.idea_id=r.idea_id
                    JOIN graph_operations o ON o.study_id=r.study_id AND o.seq=r.seq
                    WHERE r.study_id=? AND r.idea_id=? AND r.revision_id=?''', (sid, endpoint['id'], endpoint.get('revision'))).fetchone()
                if row is None:
                    raise ObserverError('corrupt_storage', 'Missing pinned graph revision', 500)
                nodes[key] = {'ref': endpoint, 'body': stored_json(row['body']), 'origin': stored_json(row['origin']),
                    'graph_seq': row['seq'], 'actor': stored_json(row['actor']), 'operation_id': row['operation_id'],
                    'committed_at': row['committed_at'], 'temporal_scope': 'recorded_history', 'visibility': 'unreviewed'}
            rows = self.db.execute('''SELECT r.*,l.type,o.actor,o.operation_id,o.committed_at
                FROM graph_link_revisions r JOIN graph_links l ON l.study_id=r.study_id AND l.link_id=r.link_id
                JOIN graph_operations o ON o.study_id=r.study_id AND o.seq=r.seq
                WHERE r.study_id=? AND r.visibility='unreviewed'
                AND ((r.source_role=? AND r.source_id=?) OR (r.target_role=? AND r.target_id=?))
                AND NOT EXISTS (SELECT 1 FROM graph_link_revisions n WHERE n.study_id=r.study_id AND n.link_id=r.link_id AND n.seq>r.seq)
                ORDER BY r.link_id LIMIT 65''', (sid, endpoint['role'], endpoint['id'], endpoint['role'], endpoint['id'])).fetchall()
            for row in rows:
                body = stored_json(row['body'])
                source, target = body['source'], body['target']
                matched = source if (source['role'], source['id']) == key[:2] else target
                if endpoint.get('revision') and matched.get('revision') != endpoint['revision']:
                    continue
                other = target if matched is source else source
                if row['link_id'] in edges:
                    continue
                if depth >= 2 or len(edges) >= 64 or len(visited) + len(queue) >= 32:
                    frontier.append(other)
                    continue
                edges[row['link_id']] = {**body, 'id': row['link_id'], 'revision_id': row['revision_id'],
                    'type': row['type'], 'category': 'semantic', 'visibility': row['visibility'], 'previous': row['previous'],
                    'graph_seq': row['seq'], 'actor': stored_json(row['actor']), 'operation_id': row['operation_id'],
                    'committed_at': row['committed_at'], 'temporal_scope': 'recorded_history', 'source_table': 'graph_link_revisions'}
                queue.append((other, depth + 1))
        return list(edges.values()), list(nodes.values()), frontier[:32]
