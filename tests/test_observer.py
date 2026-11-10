"""VS5 contract: observation is independent of all mutation services."""
import json
import sqlite3
from pathlib import Path

import pytest

from arf.decision_demo import build
from arf.observer_read import ObserverSource, ObserverError, encode


@pytest.fixture
def fixture_db(tmp_path):
    path = tmp_path / 'study.db'
    build(path)
    return path


def logical_dump(path):
    with sqlite3.connect(path) as db:
        return list(db.iterdump())


def test_b_journey_and_exact_checkpoint(fixture_db):
    before = logical_dump(fixture_db)
    with ObserverSource(fixture_db) as source:
        assert source.read('meta', {})['data']['schema_version'] == 4
        trace = source.read('trace', {'kind': 'task', 'id': 'B'})['data']
        assert trace['task']['status'] == 'succeeded'
        assert trace['decision']['decision_id'] == 'information-manager'
        assert trace['run']['status'] == 'succeeded'
        assert trace['evidence']['validation_status'] == 'unvalidated'
        assert any(m['binding'] is None for m in trace['members'])
        assert any(e['type'] == 'ASSESSES' and e['visibility'] == 'unreviewed' for e in trace['graph_assertions'])
        assert 'motivation:not_recorded' in trace['missing_relations']
        saved = source.read('checkpoint', {'id': 'information-manager'})
        with sqlite3.connect(fixture_db) as db:
            original = db.execute('SELECT body FROM decision_contexts WHERE context_id=?', (saved['data']['context_id'],)).fetchone()[0]
        assert saved['data']['context'] == json.loads(original)
        assert encode(saved['data']['context'], 2097152) == original
        assert saved['temporal_scope'] == 'snapshot_at_decision'
        assert saved['data']['capture_semantics'] == 'saved_context_input_not_global_time_travel'
        assert source.db.execute('PRAGMA query_only').fetchone()[0] == 1
        with pytest.raises(sqlite3.DatabaseError):
            source.db.execute('DELETE FROM tasks')
    assert logical_dump(fixture_db) == before


@pytest.mark.parametrize('version', [1, 2, 3])
def test_old_schema_refused_without_change(tmp_path, version):
    from arf.store import Store
    from arf.models import Charter
    from arf.plan_store import migrate
    from arf.graph_store import migrate as graph_migrate
    path = tmp_path / 'old.db'
    with Store(path, create=True) as store:
        store.import_charter(Charter.parse(Path('examples/demo-charter.yaml').read_bytes()))
        if version >= 2:
            migrate(store)
        if version >= 3:
            graph_migrate(store)
    before = logical_dump(path)
    with pytest.raises(ObserverError, match='unsupported_schema'):
        ObserverSource(path)
    assert logical_dump(path) == before

import concurrent.futures
from contextlib import contextmanager
import http.client
import os
import shutil
import subprocess
import sys
import threading
from urllib.parse import quote

from arf.observer import ObserverServer


@contextmanager
def serving(path):
    with ObserverSource(path) as source:
        with ObserverServer(source) as server:
            thread = threading.Thread(target=server.serve_forever)
            thread.start()
            try:
                yield server
            finally:
                server.shutdown()
                thread.join()


def get(server, path='/api/v1/meta', method='GET', headers=None):
    connection = http.client.HTTPConnection('127.0.0.1', server.server_port, timeout=5)
    connection.request(method, path, headers=headers or {})
    response = connection.getresponse()
    raw = response.read()
    result = (response.status, dict(response.getheaders()), raw)
    connection.close()
    return result


def test_http_assets_and_read_only_integrity(fixture_db):
    before, inode = logical_dump(fixture_db), fixture_db.stat().st_ino
    protected = {p: p.read_bytes() for p in (Path('arf/store.py'), Path('arf/worker.py'), Path('examples/demo-charter.yaml'))}
    with serving(fixture_db) as server:
        assert server.server_address[0] == '127.0.0.1'
        status, headers, body = get(server, '/')
        assert status == 200 and b'<div id="root">' in body
        assert "default-src 'none'" in headers['Content-Security-Policy']
        assert "script-src 'self'" in headers['Content-Security-Policy']
        assert headers['X-Content-Type-Options'] == 'nosniff'
        assert headers['Cache-Control'] == 'no-store'
        for route in ('meta', 'overview', 'changes', 'trace?kind=task&id=B', 'checkpoint?id=information-manager'):
            status, headers, body = get(server, '/api/v1/' + route)
            assert status == 200, body
            assert 'Access-Control-Allow-Origin' not in headers
            assert str(fixture_db).encode() not in body
        assert get(server, '/', 'HEAD')[0] == 200
        assert get(server, '/api/v1/meta', 'HEAD')[0] == 405
    assert logical_dump(fixture_db) == before and fixture_db.stat().st_ino == inode
    assert all(p.read_bytes() == content for p, content in protected.items())


@pytest.mark.parametrize('method', ['POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS', 'TRACE', 'CONNECT', 'WHATEVER'])
def test_methods_do_not_write(fixture_db, method):
    before = logical_dump(fixture_db)
    with serving(fixture_db) as server:
        assert get(server, '/api/v1/trace?kind=task&id=B', method)[0] == 405
    assert logical_dump(fixture_db) == before


@pytest.mark.parametrize('path,headers,expected', [
    ('/api/v1/meta', {'Host': 'attacker.local'}, 400),
    ('/api/v1/meta', {'Origin': 'https://attacker.local'}, 400),
    ('/api/v1/meta', {'Origin': 'null'}, 400),
    ('/api/v1/meta', {'Sec-Fetch-Site': 'cross-site'}, 400),
    ('/api/v1/meta', {'Content-Length': '1'}, 400),
    ('/api/v1/meta?foo=1', {}, 400),
    ('/api/v1/overview?limit=1&limit=2', {}, 400),
    ('/api/v1/overview?limit=0', {}, 400),
    ('/api/v1/overview?limit=51', {}, 400),
    ('/api/v1/overview?task_cursor=garbage', {}, 400),
    ('/api/v1/changes?since=garbage', {}, 400),
    ('/api/v1/trace?kind=task&id=', {}, 400),
    ('/api/v1/trace?kind=task&id='+'a'*4097, {}, 400),
    ('/api/v1/trace?kind=other&id=B', {}, 400),
    ('/api/v1/trace?kind=task&id=absent', {}, 404),
    ('/api/v1/trace?kind=task&id=%FF', {}, 400),
    ('/api/v1/trace?kind=task&id=%00', {}, 400),
    ('/api/v1/meta?bad=%', {}, 400),
    ('/api/v1/not-an-api', {}, 404),
    ('/api/v1/meta/extra', {}, 404),
    ('/%2e%2e/README.md', {}, 400),
    ('/%252e%252e/README.md', {}, 400),
    ('/..%5cREADME.md', {}, 400),
    ('/README.md', {}, 404),
    ('http://attacker.local/api/v1/meta', {}, 400),
])
def test_hostile_http(fixture_db, path, headers, expected):
    with serving(fixture_db) as server:
        status, _, body = get(server, path, headers=headers)
        assert status == expected, body
        assert json.loads(body)['error']['code']


def test_separate_writer_all_tables_poll_and_pinned_context(fixture_db):
    with ObserverSource(fixture_db) as source:
        pinned = source.read('checkpoint', {'id': 'information-manager'})
        initial = source.read('changes', {})['data']
        assert initial['reset_required']
        unchanged = source.read('changes', {'since': initial['token']})['data']
        assert not unchanged['changed']
        subprocess.run([sys.executable, 'tests/observer_writer.py', str(fixture_db)], check=True, capture_output=True)
        changed = source.read('changes', {'since': initial['token']})['data']
        assert changed['changed'] and changed['generation'] > initial['generation']
        assert not changed['reset_required']
        assert source.read('checkpoint', {'id': 'information-manager'}) == pinned
        trace = source.read('trace', {'kind': 'task', 'id': 'writer-task'})['data']
        assert trace['task']['status'] == 'succeeded'
        assert trace['evidence']['validation_status'] == 'unvalidated'
        assert trace['decision']['decision_id'] == 'writer-decision'
        assert source.read('changes', {'since': changed['token']})['data']['changed'] is False


def test_restart_and_replacement_epoch(fixture_db, tmp_path):
    with ObserverSource(fixture_db) as source:
        token = source.read('changes', {})['data']['token']
    with ObserverSource(fixture_db) as source:
        reset = source.read('changes', {'since': token})['data']
        assert reset['reset_required']
        replacement = tmp_path / 'replacement.db'
        shutil.copy2(fixture_db, replacement)
        os.replace(replacement, fixture_db)
        replaced = source.read('changes', {'since': reset['token']})['data']
        assert replaced['reset_required'] and replaced['epoch'] != reset['epoch']
        fixture_db.unlink()
        with pytest.raises(ObserverError) as exc:
            source.read('changes', {'since': replaced['token']})
        assert exc.value.code == 'stale_session'


def test_pagination_and_source_scoped_cursors(fixture_db):
    with ObserverSource(fixture_db) as source:
        tasks, dispatches, query = [], [], {'limit': '2'}
        page = source.read('overview', query)['data']
        while True:
            tasks.extend(t['task_id'] for t in page['tasks'])
            if page['task_next_cursor'] is None:
                break
            page = source.read('overview', {'limit': '2', 'task_cursor': page['task_next_cursor']})['data']
        assert tasks == ['A', 'B', 'C', 'blocked', 'D']
        page = source.read('overview', query)['data']
        first_cursor = page['dispatch_next_cursor']
        while True:
            dispatches.extend(t['dispatch_id'] for t in page['dispatches'])
            if page['dispatch_next_cursor'] is None:
                break
            page = source.read('overview', {'limit': '2', 'dispatch_cursor': page['dispatch_next_cursor']})['data']
        assert len(dispatches) == len(set(dispatches)) == 5
        with pytest.raises(ObserverError):
            source.read('overview', {'task_cursor': first_cursor})
    with ObserverSource(fixture_db) as source:
        with pytest.raises(ObserverError):
            source.read('overview', {'dispatch_cursor': first_cursor})


def test_corrupt_missing_and_older_refuse(fixture_db, tmp_path):
    missing = tmp_path / 'absent.db'
    with pytest.raises(ObserverError):
        ObserverSource(missing)
    assert not missing.exists()
    with sqlite3.connect(fixture_db) as db:
        db.execute('DROP TABLE decision_members')
    with pytest.raises(ObserverError) as exc:
        ObserverSource(fixture_db)
    assert exc.value.code == 'unsupported_schema'


def test_busy_source_is_explicit_then_recovers(fixture_db):
    with ObserverSource(fixture_db) as source, sqlite3.connect(fixture_db) as writer:
        writer.execute('BEGIN EXCLUSIVE')
        try:
            with pytest.raises(ObserverError) as exc:
                source.read('overview', {})
            assert exc.value.code == 'temporarily_unavailable'
        finally:
            writer.rollback()
        assert source.read('overview', {})['data']['tasks']


def test_long_unicode_and_pathlike_ids_are_exact(tmp_path):
    from arf.store import Store
    from arf.models import Charter, TaskSpec
    from arf.plan_store import migrate
    from arf.graph_store import migrate as graph_migrate
    from arf.decision_store import migrate_decisions
    from conftest import spec
    path = tmp_path / 'long.db'
    task_id = '한' * 1365 + 'x'  # exactly 4096 UTF-8 bytes
    with Store(path, create=True) as store:
        store.import_charter(Charter.parse(Path('examples/demo-charter.yaml').read_bytes()))
        store.add_task(TaskSpec.parse(spec(task_id)))
        store.add_task(TaskSpec.parse(spec('../saved?not-a-path')))
        migrate(store); graph_migrate(store); migrate_decisions(store)
    with serving(path) as server:
        for identity in (task_id, '../saved?not-a-path'):
            status, _, body = get(server, '/api/v1/trace?kind=task&id='+quote(identity,safe=''))
            assert status == 200, body
            assert json.loads(body)['data']['task']['task_id'] == identity


def test_multiple_attempts_no_arbitrary_choice(fixture_db):
    # Add real failed/interrupted attempts using the original fixed lifecycle helpers.
    from arf.store import Store
    from arf.models import TaskSpec
    from conftest import spec
    with Store(fixture_db) as store:
        store.add_task(TaskSpec.parse(spec('attempts')))
        with store.transaction():
            claim = store._claim_task_in_transaction('attempts')
        # Explicit trusted-writer recovery/retry leaves both attempts visible.
        interrupted_id = claim['run_id']
        store.recover()
        store.retry('attempts')
        with store.transaction():
            claim = store._claim_task_in_transaction('attempts')
        run_id = claim['run_id']
    with ObserverSource(fixture_db) as source:
        trace = source.read('trace', {'kind': 'run', 'id': run_id})['data']
        assert trace['run']['status'] == 'running'
        assert trace['evidence'] is None
        assert trace['dispatch'] is None
        assert 'motivation:not_recorded' in trace['missing_relations']
        task_trace = source.read('trace', {'kind':'task','id':'attempts'})['data']
        assert task_trace['run'] is None
        assert {r['run_id'] for r in task_trace['runs']} == {interrupted_id, run_id}
        old = source.read('trace', {'kind':'run','id':interrupted_id})['data']['run']
        assert old['status'] == 'interrupted' and old['wall_seconds'] is None


def test_response_limits_and_exact_context_error(fixture_db, monkeypatch):
    import arf.observer_read as read
    with ObserverSource(fixture_db) as source:
        monkeypatch.setattr(read, 'API_LIMIT', 1000)
        with pytest.raises(ObserverError) as exc:
            source.read('trace', {'kind':'task', 'id':'B'})
        assert exc.value.status == 413
        monkeypatch.setattr(read, 'CHECKPOINT_LIMIT', 1000)
        with pytest.raises(ObserverError) as exc:
            source.read('checkpoint', {'id':'information-manager'})
        assert exc.value.status == 413 and 'information-manager' in exc.value.message


def test_abstain_and_nonclaim_semantics(fixture_db):
    with ObserverSource(fixture_db) as source:
        checkpoint = source.read('checkpoint', {'id':'truncated-manager'})['data']
        assert checkpoint['decision']['status'] == 'abstain'
        assert checkpoint['selection_complete'] is False
        overview = source.read('overview', {})['data']
        receipt = next(d for d in overview['dispatches'] if d['status'] == 'deferred')
        trace = source.read('trace', {'kind':'dispatch', 'id':receipt['dispatch_id']})['data']
        assert trace['task'] is None and trace['run'] is None
        assert trace['dispatch']['reason'] == 'reasoned_abstention'


def test_parallel_polls_consistent_and_no_mutation(fixture_db):
    before = logical_dump(fixture_db)
    with serving(fixture_db) as server:
        token = json.loads(get(server, '/api/v1/changes')[2])['data']['token']
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(lambda _: get(server, '/api/v1/changes?since='+token), range(10)))
        assert all(s == 200 and not json.loads(raw)['data']['changed'] for s, _, raw in results)
    assert logical_dump(fixture_db) == before


def test_invalid_saved_json_is_explicit(fixture_db):
    with sqlite3.connect(fixture_db) as db:
        db.execute('''INSERT INTO tasks(study_id,task_id,title,description,kind,input_json,status,created_at)
            VALUES ('demo-mean-study','bad-json','Test malformed storage','','demo_mean','{','pending','now')''')
    with ObserverSource(fixture_db) as source:
        with pytest.raises(ObserverError) as exc:
            source.read('trace', {'kind':'task','id':'bad-json'})
        assert exc.value.code == 'corrupt_storage' and exc.value.status == 500


def test_real_large_record_refuses_without_silent_truncation(fixture_db):
    with sqlite3.connect(fixture_db) as db:
        db.execute('''INSERT INTO tasks(study_id,task_id,title,description,kind,input_json,status,created_at)
            VALUES ('demo-mean-study','large','Large',?,'demo_mean','{}','pending','now')''', ('x'*270000,))
    before = logical_dump(fixture_db)
    with serving(fixture_db) as server:
        status, _, raw = get(server, '/api/v1/trace?kind=task&id=large')
        assert status == 413 and json.loads(raw)['error']['code'] == 'limit'
    assert logical_dump(fixture_db) == before


def test_empty_v4_and_initial_bootstrap_observed_without_starting_it(tmp_path):
    from arf.store import Store
    from arf.models import Charter, TaskSpec
    from arf.plan_store import migrate
    from arf.graph_store import migrate as graph_migrate
    from arf.decision_store import migrate_decisions
    from arf.decision_models import CandidateDefinition, Synthetic
    from arf.decisions import DecisionService
    from arf.service import run_next
    from conftest import spec
    path = tmp_path / 'initial.db'
    with Store(path, create=True) as store:
        store.import_charter(Charter.parse(Path('examples/demo-charter.yaml').read_bytes()))
        migrate(store); graph_migrate(store); migrate_decisions(store)
    with ObserverSource(path) as source:
        empty = source.read('overview', {})['data']
        assert empty['tasks'] == [] and empty['dispatches'] == []
        assert empty['latest_decision_id'] is None and empty['publication_head_id'] is None
        with Store(path) as store:
            store.add_task(TaskSpec.parse(spec('bootstrap')))
            DecisionService(store).record_candidates('fixture-candidates',
                [CandidateDefinition('bootstrap', 'Synthetic bootstrap', synthetic=Synthetic(1, 1))],
                {'bootstrap':'bootstrap'}, 'test-writer')
        before = source.read('overview', {})['data']
        assert before['tasks'][0]['status'] == 'pending'
        assert before['dispatches'] == [] and before['latest_decision_id'] is None
        with Store(path) as store:
            result = run_next(store)  # explicitly authorized trusted test writer only
            assert result['task_id'] == 'bootstrap'
        trace = source.read('trace', {'kind':'task','id':'bootstrap'})['data']
        assert trace['dispatch']['status'] == 'claimed'
        assert trace['evidence']['validation_status'] == 'unvalidated'


def test_semantic_revision_provenance_and_motivation(fixture_db):
    from arf.store import Store
    from arf.graph import GraphService
    from arf.graph_models import Actor, Ref
    with Store(fixture_db) as store:
        graph = GraphService(store)
        actor = Actor('observer-fixture', 'operator', 'offline test')
        q = graph.create_human_idea(operation_id='observer-Q',actor=actor,kind='Q',text='Synthetic question')['result']
        h = graph.create_human_idea(operation_id='observer-H',actor=actor,kind='H',text='Synthetic hypothesis')['result']
        graph.add_semantic_link(operation_id='observer-investigates',actor=actor,type='INVESTIGATES',
            source=Ref('T','B'),target=Ref('H',h['idea_id'],h['revision_id']),rationale='Synthetic relation')
        graph.add_semantic_link(operation_id='observer-addresses',actor=actor,type='ADDRESSES',
            source=Ref('H',h['idea_id'],h['revision_id']),target=Ref('Q',q['idea_id'],q['revision_id']),rationale='Synthetic relation')
        evidence = next(e for e in store.evidence() if e['task_id']=='B')
        graph.add_semantic_link(operation_id='observer-motivation',actor=actor,type='MOTIVATED_BY',
            source=Ref('T','B'),target=Ref('E',evidence['evidence_id']),rationale='Retrospective synthetic interpretation')
    with ObserverSource(fixture_db) as source:
        trace = source.read('trace', {'kind':'task','id':'B'})['data']
        assert 'motivation:not_recorded' not in trace['missing_relations']
        assert {'INVESTIGATES','ADDRESSES','MOTIVATED_BY'} <= {e['type'] for e in trace['graph_assertions']}
        for edge in trace['graph_assertions']:
            assert edge['revision_id'] and edge['graph_seq'] and edge['actor']['name']
            assert edge['visibility']=='unreviewed' and edge['category']=='semantic'
        assert {'Q','H'} <= {n['ref']['role'] for n in trace['graph_nodes']}


def test_request_budget_and_same_origin(fixture_db):
    with serving(fixture_db) as server:
        origin=server.url
        assert get(server, headers={'Origin':origin})[0]==200
        status,_,raw=get(server,'/api/v1/trace?kind=task&id='+'a'*33000)
        assert status==400 and json.loads(raw)['error']['code']=='invalid_query'
        status,_,raw=get(server,'/'+'a'*66000)
        assert status==413 and json.loads(raw)['error']['code']=='limit'


def test_observer_imports_no_writer_modules():
    process=subprocess.run([sys.executable,'-c',
        "import arf.observer,sys; assert not any(m in sys.modules for m in ('arf.store','arf.service','arf.decisions','arf.graph','arf.executor'))"],
        check=True,capture_output=True)
    assert process.returncode==0


def test_graph_bounds_have_explicit_frontier(fixture_db):
    from arf.store import Store
    from arf.graph import GraphService
    from arf.graph_models import Actor, Ref
    with Store(fixture_db) as store:
        graph=GraphService(store)
        actor=Actor('bounded-fixture','operator','offline observer test')
        for i in range(35):
            h=graph.create_human_idea(operation_id=f'bounded-h-{i}',actor=actor,kind='H',text='Synthetic bounded idea')['result']
            graph.add_semantic_link(operation_id=f'bounded-l-{i}',actor=actor,type='INVESTIGATES',
                source=Ref('T','B'),target=Ref('H',h['idea_id'],h['revision_id']),rationale='Synthetic neighborhood')
    with ObserverSource(fixture_db) as source:
        trace=source.read('trace', {'kind':'task','id':'B'})['data']
        assert trace['truncated'] and trace['continuation']['graph_frontier']
        assert len(trace['graph_nodes'])<=32 and len(trace['graph_assertions'])<=64


def test_wal_detector_observes_commits_on_same_connection(fixture_db):
    with sqlite3.connect(fixture_db) as writer:
        assert writer.execute('PRAGMA journal_mode=WAL').fetchone()[0]=='wal'
        with ObserverSource(fixture_db) as source:
            initial=source.read('changes', {})['data']
            detector=source.db
            writer.execute('''INSERT INTO tasks(study_id,task_id,title,description,kind,input_json,status,created_at)
                VALUES ('demo-mean-study','wal-arrival','WAL fixture','','demo_mean','{}','pending','now')''')
            writer.commit()
            current=source.read('changes', {'since':initial['token']})['data']
            assert current['changed'] and not current['reset_required'] and source.db is detector
            assert source.read('trace', {'kind':'task','id':'wal-arrival'})['data']['task']['status']=='pending'


def test_exact_qualitative_excluded_unranked_member_visible(fixture_db):
    from arf.store import Store
    from arf.decisions import DecisionService
    from arf.decision_models import CandidateDefinition, Impact
    # Separate trusted fixture setup creates a new advisory record; no existing
    # ranking is rewritten, evaluated by the observer, or published here.
    with Store(fixture_db) as store:
        service=DecisionService(store)
        pairs=service.record_candidates('qualitative-fixture',[
            CandidateDefinition('qualitative-idea','Recorded qualitative judgment',impact=Impact(status='qualitative'))],{},'fixture')['versions']
        context=service.capture_context()
        decision=service.decide('qualitative-only',context['context_id'],pairs)
    with ObserverSource(fixture_db) as source:
        saved=source.read('checkpoint',{'id':'qualitative-only'})['data']['decision']
        assert saved == decision
        member=saved['members'][0]
        assert member['priority_group'] is None and member['exclusion']
        assert member['binding'] is None and member['estimate']['impact']['status']=='qualitative'
        assert member['estimate']['costs'] == {}  # missing estimates stay missing
        trace=source.read('trace',{'kind':'decision','id':'qualitative-only'})['data']
        assert trace['members'][0]['exclusion']==member['exclusion']


def test_unranked_ready_dispatch_is_not_no_ready_or_completion(fixture_db):
    from arf.store import Store
    from arf.models import TaskSpec
    from arf.service import run_next
    from conftest import spec
    subprocess.run([sys.executable,'tests/observer_writer.py',str(fixture_db)],check=True,capture_output=True)
    with Store(fixture_db) as store:
        store.add_task(TaskSpec.parse(spec('uncovered-ready')))
        receipt=run_next(store)
        assert receipt['status']=='needs_decision' and receipt['reason']=='unranked_ready_task'
    before=logical_dump(fixture_db)
    with ObserverSource(fixture_db) as source:
        trace=source.read('trace',{'kind':'dispatch','id':receipt['dispatch_id']})['data']
        assert trace['dispatch']['status']=='needs_decision'
        assert trace['dispatch']['reason']=='unranked_ready_task'
        assert trace['run'] is None and trace['task'] is None
    assert logical_dump(fixture_db)==before
