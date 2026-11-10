"""Bounded SQL projections and visited-set traversal; no scientific inference."""

from contextlib import contextmanager
from dataclasses import asdict
import base64
import json

from arf.graph_models import QueryLimits, Ref
from arf.graph_store import GraphError
from arf.plan_models import canonical, sha

ROLES = ('O', 'Q', 'H', 'C', 'T', 'R', 'E', 'B')
FACTS = ('DEPENDS_ON', 'ATTEMPT_OF', 'PRODUCES', 'SUPERSEDES')
SEMANTIC = ('ADDRESSES', 'INVESTIGATES', 'MOTIVATED_BY', 'DERIVED_FROM', 'ASSESSES', 'USES_BASELINE')


@contextmanager
def snapshot(g):
    if g.db.in_transaction:
        raise GraphError('invalid', 'graph read requires its own consistent read transaction')
    g.db.execute('BEGIN')
    try:
        yield
        g.db.commit()
    except BaseException:
        g.db.rollback()
        raise


def sequence(g, value):
    latest = g.sequence()
    if value is None:
        return latest
    if type(value) is not int or not 0 <= value <= latest:
        raise GraphError('invalid', 'as-of sequence must be within recorded graph history')
    return value


def audit(row):
    return {'graph_seq': row['seq'], 'actor': json.loads(row['actor']),
            'committed_at': row['committed_at'], 'operation_id': row['operation_id']}


def node_view(g, ref, seq, *, revision=None):
    if ref.role in 'QHC':
        sql = '''SELECT i.kind,i.origin,r.*,o.actor,o.committed_at,o.operation_id
            FROM graph_ideas i JOIN graph_idea_revisions r USING(idea_id)
            JOIN graph_operations o ON o.study_id=r.study_id AND o.seq=r.seq
            WHERE i.idea_id=? AND r.seq<=?'''
        args = [ref.id, seq]
        pin = revision or ref.revision
        if pin:
            sql += ' AND r.revision_id=?'
            args.append(pin)
        sql += ' ORDER BY r.seq DESC LIMIT 1'
        row = g.db.execute(sql, args).fetchone()
        if not row:
            return None
        return {'ref': asdict(Ref(row['kind'], ref.id, row['revision_id'])),
                'body': json.loads(row['body']), 'origin': json.loads(row['origin']),
                'previous': row['previous'], **audit(row)}
    if ref.role == 'B':
        row = g.db.execute('''SELECT b.*,o.actor,o.committed_at,o.operation_id
            FROM graph_baselines b JOIN graph_operations o ON o.study_id=b.study_id AND o.seq=b.seq
            WHERE baseline_id=? AND b.seq<=?''', (ref.id, seq)).fetchone()
        if not row:
            return None
        return {'ref': asdict(ref), 'body': json.loads(row['body']), **audit(row)}
    if ref.role == 'O':
        body = g.store.study()
        body['source_base64'] = base64.b64encode(body.pop('source')).decode('ascii')
        body['success_criteria'] = json.loads(body.pop('success_criteria_json'))
        body['constraints'] = json.loads(body.pop('constraints_json'))
    else:
        table, column = {'T': ('tasks', 'task_id'), 'R': ('runs', 'run_id'),
                         'E': ('evidence', 'evidence_id')}[ref.role]
        row = g.db.execute(f'SELECT * FROM {table} WHERE {column}=? AND study_id=?',
                           (ref.id, g.study_id)).fetchone()
        if not row:
            return None
        body = dict(row)
        if ref.role == 'R':
            body = g.store._run_view(row)
        elif ref.role == 'T':
            body['input'] = json.loads(body.pop('input_json'))
        elif ref.role == 'E':
            body['result'] = json.loads(body.pop('result_json'))
            body['provenance'] = json.loads(body.pop('provenance_json'))
    return {'ref': asdict(ref), 'body': body, 'execution_state': 'current',
            'historical_execution_state': 'unknown'}


def node_refs(g, seq, roles, history, cap):
    for role in roles or ROLES:
        if role == 'O':
            yield Ref('O', g.study_id)
        elif role in 'QHC':
            sql = '''SELECT i.idea_id,r.revision_id FROM graph_ideas i
                JOIN graph_idea_revisions r USING(idea_id) WHERE i.kind=? AND r.seq<=?'''
            if not history:
                sql += ''' AND NOT EXISTS (SELECT 1 FROM graph_idea_revisions n
                    WHERE n.idea_id=r.idea_id AND n.seq>r.seq AND n.seq<=?)'''
            sql += ' ORDER BY i.idea_id,r.seq LIMIT ?'
            params = [role, seq] + ([] if history else [seq]) + [cap + 1]
            for row in g.db.execute(sql, params):
                yield Ref(role, row['idea_id'], row['revision_id'])
        else:
            table, column = {'T': ('tasks', 'task_id'), 'R': ('runs', 'run_id'),
                             'E': ('evidence', 'evidence_id'), 'B': ('graph_baselines', 'baseline_id')}[role]
            where = ' AND seq<=?' if role == 'B' else ''
            params = [g.study_id] + ([seq] if role == 'B' else []) + [cap + 1]
            for row in g.db.execute(f'SELECT {column} FROM {table} WHERE study_id=?{where} ORDER BY {column} LIMIT ?', params):
                yield Ref(role, row[0])


def _incident(ref, source, target):
    return ref is None or (ref.role, ref.id) in ((source.role, source.id), (target.role, target.id))


def edges(g, seq, types, history, cap, incident=None, edge_id=None):
    selected = types or SEMANTIC + FACTS
    fact_key = None
    if edge_id and edge_id.startswith('fact:'):
        try:
            fact_key = json.loads(base64.urlsafe_b64decode(edge_id[5:].encode('ascii')))
        except (ValueError, UnicodeError) as exc:
            raise GraphError('invalid', 'malformed factual edge ID') from exc
        if (not isinstance(fact_key, list) or len(fact_key) != 3 or fact_key[0] not in FACTS[:3]
                or not all(isinstance(x, str) for x in fact_key)):
            raise GraphError('invalid', 'malformed factual edge ID')
        selected = tuple(t for t in selected if t == fact_key[0])
    semantic = [t for t in selected if t in SEMANTIC]
    if semantic:
        sql = '''SELECT l.type,r.*,o.actor,o.committed_at,o.operation_id
            FROM graph_link_revisions r JOIN graph_links l USING(link_id)
            JOIN graph_operations o ON o.study_id=r.study_id AND o.seq=r.seq
            WHERE r.seq<=? AND l.type IN (''' + ','.join('?' for _ in semantic) + ')'
        params = [seq, *semantic]
        if edge_id:
            sql += ' AND r.link_id=?'
            params.append(edge_id)
        if not history:
            sql += ''' AND r.visibility='unreviewed' AND NOT EXISTS (
                SELECT 1 FROM graph_link_revisions n WHERE n.link_id=r.link_id AND n.seq>r.seq AND n.seq<=?)'''
            params.append(seq)
        if incident:
            sql += ' AND ((r.source_role=? AND r.source_id=?) OR (r.target_role=? AND r.target_id=?))'
            params += [incident.role, incident.id, incident.role, incident.id]
            if incident.revision:
                sql += " AND ((r.source_role=? AND r.source_id=? AND json_extract(r.body,'$.source.revision')=?) OR (r.target_role=? AND r.target_id=? AND json_extract(r.body,'$.target.revision')=?))"
                params += [incident.role, incident.id, incident.revision, incident.role, incident.id, incident.revision]
        sql += ' ORDER BY r.link_id,r.seq LIMIT ?'
        params.append(cap + 1)
        for row in g.db.execute(sql, params):
            yield {'id': row['link_id'], 'revision_id': row['revision_id'], 'type': row['type'],
                   'category': 'semantic', 'visibility': row['visibility'], 'previous': row['previous'],
                   **json.loads(row['body']), **audit(row)}
    for type in selected:
        if type not in FACTS:
            continue
        if type == 'SUPERSEDES':
            sql = '''SELECT t.*,o.actor,o.committed_at,o.operation_id FROM graph_transitions t
                JOIN graph_operations o ON o.study_id=t.study_id AND o.seq=t.seq
                WHERE t.seq<=? AND t.old_baseline IS NOT NULL'''
            params = [seq]
            if edge_id:
                sql += ' AND t.transition_id=?'
                params.append(edge_id)
            if incident:
                if incident.role != 'B':
                    continue
                sql += ' AND (t.new_baseline=? OR t.old_baseline=?)'
                params += [incident.id, incident.id]
            sql += ' ORDER BY t.seq LIMIT ?'
            for row in g.db.execute(sql, params + [cap + 1]):
                yield {'id': row['transition_id'], 'type': type, 'category': 'operator_transition',
                       'source': asdict(Ref('B', row['new_baseline'])),
                       'target': asdict(Ref('B', row['old_baseline'])),
                       'body': json.loads(row['body']), **audit(row)}
            continue
        if type == 'DEPENDS_ON':
            sql = 'SELECT task_id AS src,prerequisite_id AS dst FROM dependencies WHERE study_id=?'
            sr, tr = 'T', 'T'
        elif type == 'ATTEMPT_OF':
            sql = 'SELECT run_id AS src,task_id AS dst FROM runs WHERE study_id=?'
            sr, tr = 'R', 'T'
        else:
            sql = '''SELECT e.run_id AS src,e.evidence_id AS dst FROM evidence e
                JOIN runs r ON r.run_id=e.run_id AND r.study_id=e.study_id AND r.task_id=e.task_id
                WHERE e.study_id=? AND r.status='succeeded' AND r.result_json=e.result_json'''
            sr, tr = 'R', 'E'
        if edge_id and fact_key is None:
            continue
        # Filter by endpoints inside SQL rather than materializing all factual rows.
        outer = f'SELECT * FROM ({sql}) WHERE 1=1'
        params = [g.study_id]
        if fact_key:
            outer += ' AND src=? AND dst=?'
            params += fact_key[1:]
        if incident:
            clauses = []
            if incident.role == sr:
                clauses.append('src=?')
                params.append(incident.id)
            if incident.role == tr:
                clauses.append('dst=?')
                params.append(incident.id)
            if not clauses:
                continue
            outer += ' AND (' + ' OR '.join(clauses) + ')'
        outer += ' ORDER BY src,dst LIMIT ?'
        for row in g.db.execute(outer, params + [cap + 1]):
            source, target = Ref(sr, row['src']), Ref(tr, row['dst'])
            yield {'id': 'fact:' + base64.urlsafe_b64encode(canonical([type, row['src'], row['dst']])).decode('ascii'),
                   'type': type, 'category': 'execution_fact', 'source': asdict(source),
                   'target': asdict(target), 'execution_state': 'current',
                   'historical_execution_state': 'unknown'}


class Budget:
    def __init__(self, seq, limits):
        self.limits = limits
        self.result = {'graph_seq': seq, 'execution_state': 'current',
                       'historical_execution_state': 'unknown', 'nodes': [], 'edges': [],
                       'active_baselines': [], 'truncated': False, 'frontier': []}
        self.size = len(canonical(self.result))

    def stop(self, frontier):
        self.result['truncated'] = True
        # A bounded opaque continuation marker also fits the smallest output cap.
        marker = frontier if isinstance(frontier, dict) and len(canonical(frontier)) <= 160 else {
            'continuation': sha(canonical(frontier))}
        if marker not in self.result['frontier'] and len(canonical(self.result['frontier'] + [marker])) <= 384:
            self.result['frontier'].append(marker)

    def add(self, kind, value):
        maximum = self.limits.nodes if kind in ('nodes', 'active_baselines') else self.limits.edges
        needed = len(canonical(value)) + 1
        if len(self.result[kind]) >= maximum or self.size + needed > self.limits.output_bytes - 512:
            self.stop(value.get('ref', value.get('id', kind)))
            return False
        self.result[kind].append(value)
        self.size += needed
        return True


def baselines(g, seq, budget):
    for row in g.db.execute('''SELECT t.scope,t.new_baseline,t.seq FROM graph_transitions t
        WHERE t.seq<=? AND NOT EXISTS (SELECT 1 FROM graph_transitions n
            WHERE n.study_id=t.study_id AND n.scope=t.scope AND n.seq>t.seq AND n.seq<=?)
        ORDER BY t.scope LIMIT ?''', (seq, seq, budget.limits.nodes + 1)):
        if not budget.add('active_baselines', {'scope': row['scope'], 'baseline_id': row['new_baseline'],
                                              'graph_seq': row['seq']}):
            break


def read_graph(g, *, at_seq=None, node=None, roles=(), edge_types=(), history=False, edge_id=None, limits=QueryLimits()):
    limits.validate()
    if edge_id is not None:
        try:
            valid_id = isinstance(edge_id, str) and bool(edge_id) and len(edge_id.encode('utf-8')) <= 16384
        except UnicodeError:
            valid_id = False
        if not valid_id:
            raise GraphError('invalid', 'edge ID must be bounded UTF-8 text')
    if type(history) is not bool or any(r not in ROLES for r in roles) or any(t not in SEMANTIC + FACTS for t in edge_types):
        raise GraphError('invalid', 'unknown typed query filter')
    with snapshot(g):
        return _read_graph_in_transaction(g, at_seq=at_seq, node=node, roles=roles,
            edge_types=edge_types, history=history, edge_id=edge_id, limits=limits)


def _read_graph_in_transaction(g, *, at_seq=None, node=None, roles=(), edge_types=(), history=False, edge_id=None, limits=QueryLimits()):
    """Private joint-snapshot seam; public wrappers still refuse nesting."""
    if not g.db.in_transaction:
        raise GraphError('invalid', 'caller-owned read transaction required')
    limits.validate()
    if any(r not in ROLES for r in roles) or any(t not in SEMANTIC + FACTS for t in edge_types):
        raise GraphError('invalid', 'unknown typed query filter')
    seq = sequence(g, at_seq)
    budget = Budget(seq, limits)
    if node:
        g._ref(node, allow_head=True)
        if roles and node.role not in roles:
            refs = ()
        elif history and node.role in ('Q', 'H', 'C') and node.revision is None:
            rows = g.db.execute('''SELECT revision_id FROM graph_idea_revisions
                WHERE idea_id=? AND seq<=? ORDER BY seq LIMIT ?''',
                                (node.id, seq, limits.nodes + 1))
            refs = (Ref(node.role, node.id, r['revision_id']) for r in rows)
        else:
            refs = (node,)
    else:
        refs = () if edge_id else node_refs(g, seq, roles, history, limits.nodes)
    for ref in refs:
        value = node_view(g, ref, seq)
        if value and not budget.add('nodes', value):
            break
    for edge in edges(g, seq, edge_types, history, limits.edges, node, edge_id):
        if not budget.add('edges', edge):
            break
    baselines(g, seq, budget)
    return budget.result


def traverse(g, root, direction, at_seq, limits):
    limits.validate()
    with snapshot(g):
        seq = sequence(g, at_seq)
        g._ref(root)
        budget = Budget(seq, limits)
        pending = [(root, 0)]
        visited = set()
        edge_seen = set()
        scanned = 0
        while pending:
            ref, depth = pending.pop(0)
            key = (ref.role, ref.id, ref.revision)
            if key in visited:
                continue
            visited.add(key)
            value = node_view(g, ref, seq)
            if value is None:
                continue
            if not budget.add('nodes', value):
                break
            candidates = 0
            for edge in edges(g, seq, (), False, limits.edges, ref):
                candidates += 1
                if candidates > limits.edges:
                    budget.stop(asdict(ref))
                    break
                scanned += 1
                if scanned > limits.edges * 4:
                    budget.stop({'scan_frontier': asdict(ref)})
                    pending.clear()
                    break
                source, target = Ref(**edge['source']), Ref(**edge['target'])
                outgoing = (source.role, source.id) == (ref.role, ref.id)
                # Traversal follows only the exact revision under consideration.
                endpoint = source if outgoing else target
                if ref.revision and endpoint.revision and ref.revision != endpoint.revision:
                    continue
                if direction == 'ancestry':
                    follow = outgoing or edge['type'] in ('PRODUCES', 'ATTEMPT_OF')
                else:
                    follow = not outgoing or edge['type'] == 'ASSESSES'
                if not follow:
                    continue
                other = target if outgoing else source
                if depth >= limits.depth:
                    budget.stop(asdict(other))
                    continue
                if edge['id'] not in edge_seen:
                    if not budget.add('edges', edge):
                        pending.clear()
                        break
                    edge_seen.add(edge['id'])
                if (other.role, other.id, other.revision) not in visited:
                    # Queue also has a hard bound even for dense branching cycles.
                    if len(pending) >= limits.nodes:
                        budget.stop(asdict(other))
                    else:
                        pending.append((other, depth + 1))
        baselines(g, seq, budget)
        return budget.result
