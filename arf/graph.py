"""Trusted, local append-only research assertions; no execution capabilities."""

from dataclasses import asdict
import json
from typing import Callable
import uuid

from arf.graph_models import Actor, QueryLimits, Ref
from arf.graph_store import GRAPH_SCHEMA, GraphError
from arf.plan_models import PlanError, canonical, strict_json, text as plan_text
from arf.plan_store import PlanStore, _schema_objects
from arf.store import Store, utc_now


EDGE_ROLES = {
    'ADDRESSES': ('QHC', 'OQ'),
    'INVESTIGATES': ('T', 'QHC'),
    'MOTIVATED_BY': ('QHCTB', 'QHCEB'),
    'DERIVED_FROM': ('QHC', 'QHCE'),
    'ASSESSES': ('EC', 'HC'),
    'USES_BASELINE': ('T', 'B'),
}
POLARITIES = ('supports', 'contradicts', 'inconclusive')


def text(value, name, *, empty=False):
    try:
        return plan_text(value, name, empty=empty)
    except PlanError as exc:
        raise GraphError(exc.code, str(exc)) from exc


def new_id(prefix: str) -> str:
    return prefix + '-' + str(uuid.uuid4())


def bounded(value: object) -> bytes:
    try:
        raw = canonical(value)
        strict_json(raw)
    except PlanError as exc:
        raise GraphError(exc.code, str(exc)) from exc
    return raw


class GraphService:
    def __init__(self, store: Store):
        self.store = store
        self.db = store.connection
        self.study_id = store.study()['study_id']
        if self.db.execute('PRAGMA user_version').fetchone()[0] != 3:
            raise GraphError('schema', 'graph requires explicit v2 to v3 migration')
        # Like PlanStore, allow additional diagnostic triggers during operation.
        import sqlite3
        with sqlite3.connect(':memory:') as reference:
            for statement in GRAPH_SCHEMA:
                reference.execute(statement)
            expected = _schema_objects(reference)
        actual = _schema_objects(self.db)
        if any(actual.get(k) != v for k, v in expected.items()):
            raise GraphError('schema', 'graph schema is incomplete or unrelated')

    def sequence(self) -> int:
        return self.db.execute('SELECT coalesce(max(seq),0) FROM graph_operations WHERE study_id=?',
                               (self.study_id,)).fetchone()[0]

    @staticmethod
    def _actor(actor: Actor, *, operator: bool = False) -> bytes:
        if not isinstance(actor, Actor) or actor.role not in ('recorder', 'operator'):
            raise GraphError('unauthorized', 'trusted recorder or operator required')
        if operator and actor.role != 'operator':
            raise GraphError('unauthorized', 'trusted operator required')
        text(actor.name, 'actor')
        text(actor.source, 'source')
        return bounded(asdict(actor))

    @staticmethod
    def _receipt(row) -> dict:
        return {'operation_id': row['operation_id'], 'study_id': row['study_id'],
                'graph_seq': row['seq'], 'committed_at': row['committed_at'],
                'actor': json.loads(row['actor']), 'result': json.loads(row['result'])}

    def _require_revision_owner(self, creation_seq: int, actor: Actor) -> None:
        """Ownership stays with the creator, including after operator corrections."""
        row = self.db.execute('SELECT actor FROM graph_operations WHERE study_id=? AND seq=?',
                              (self.study_id, creation_seq)).fetchone()
        if row is None:
            raise GraphError('schema', 'assertion creation provenance is missing')
        owner = json.loads(row['actor'])['name']
        if actor.role != 'operator' and actor.name != owner:
            raise GraphError('unauthorized', 'only the original author or an operator may revise this assertion')

    def _mutate(self, kind: str, request: dict, operation_id: str, actor: Actor,
                action: Callable, *, operator: bool = False) -> dict:
        attribution = self._actor(actor, operator=operator)
        text(operation_id, 'operation ID')
        raw = bounded(request)
        with self.store.transaction():
            existing = self.db.execute('SELECT * FROM graph_operations WHERE operation_id=?',
                                       (operation_id,)).fetchone()
            if existing:
                if (existing['study_id'], existing['kind'], existing['request'], existing['actor']) != (
                        self.study_id, kind, raw, attribution):
                    raise GraphError('conflict', 'operation ID already bound to another request/actor')
                return self._receipt(existing)
            seq = self.sequence() + 1
            try:
                result = action(seq)
            except GraphError:
                raise
            except PlanError as exc:
                raise GraphError(exc.code, str(exc)) from exc
            self.db.execute('INSERT INTO graph_operations VALUES (?,?,?,?,?,?,?,?)',
                            (self.study_id, seq, operation_id, kind, attribution, raw,
                             canonical(result), utc_now()))
            row = self.db.execute('SELECT * FROM graph_operations WHERE operation_id=?',
                                  (operation_id,)).fetchone()
            return self._receipt(row)

    def _ref(self, ref: Ref, *, allow_head: bool = False) -> Ref:
        if not isinstance(ref, Ref) or ref.role not in ('O', 'Q', 'H', 'C', 'T', 'R', 'E', 'B'):
            raise GraphError('invalid', 'unknown typed reference')
        text(ref.id, 'reference ID')
        if ref.role in ('Q', 'H', 'C'):
            if ref.revision is None and allow_head:
                row = self.db.execute('SELECT kind,study_id FROM graph_ideas WHERE idea_id=?',
                                      (ref.id,)).fetchone()
            else:
                text(ref.revision, 'exact idea revision')
                row = self.db.execute('''SELECT i.kind,i.study_id FROM graph_ideas i
                    JOIN graph_idea_revisions r USING(idea_id)
                    WHERE i.idea_id=? AND r.revision_id=?''', (ref.id, ref.revision)).fetchone()
            valid = row and row['study_id'] == self.study_id and row['kind'] == ref.role
        else:
            if ref.revision is not None:
                raise GraphError('invalid', 'only ideas take revision pins')
            table, column = {'O': ('studies', 'study_id'), 'T': ('tasks', 'task_id'),
                             'R': ('runs', 'run_id'), 'E': ('evidence', 'evidence_id'),
                             'B': ('graph_baselines', 'baseline_id')}[ref.role]
            valid = self.db.execute(f'SELECT 1 FROM {table} WHERE {column}=? AND study_id=?',
                                    (ref.id, self.study_id)).fetchone()
        if not valid:
            raise GraphError('not_found', 'reference does not resolve in this study/kind/revision')
        return ref

    def _refs(self, refs, roles: str = 'OQHCTREB') -> list[dict]:
        if not isinstance(refs, (list, tuple)) or len(refs) > 64:
            raise GraphError('limit', 'at most 64 pinned references permitted')
        result = []
        for ref in refs:
            self._ref(ref)
            if ref.role not in roles:
                raise GraphError('invalid', 'reference role is not permitted here')
            result.append(asdict(ref))
        if len({canonical(r) for r in result}) != len(result):
            raise GraphError('invalid', 'duplicate references')
        return result

    def _idea_body(self, kind, value, assumptions, scope, premises, joint) -> dict:
        text(value, 'idea text')
        text(assumptions, 'assumptions', empty=True)
        text(scope, 'scope', empty=True)
        if type(joint) is not bool:
            raise GraphError('invalid', 'joint must be boolean')
        refs = self._refs(premises, 'EC')
        if kind == 'C':
            if not joint or len(refs) < 2:
                raise GraphError('invalid', 'synthesis requires joint marker and at least two premises')
        elif refs or joint:
            raise GraphError('invalid', 'only joint claims carry premises')
        return {'text': value, 'assumptions': assumptions, 'scope': scope,
                'premises': refs, 'joint': joint, 'visibility': 'unreviewed'}

    def _insert_idea_revision(self, idea_id, kind, body, previous, seq) -> str:
        revision = new_id('ir')
        self.db.execute('INSERT INTO graph_idea_revisions VALUES (?,?,?,?,?,?)',
                        (revision, idea_id, previous, bounded(body), self.study_id, seq))
        for premise in body['premises']:
            self._insert_link('DERIVED_FROM', Ref(kind, idea_id, revision), Ref(**premise),
                              'Joint synthesis premise; not an independent experiment',
                              body['assumptions'], body['scope'], None, 'retrospective', None, seq)
        return revision

    def _new_idea(self, kind, body, origin, seq) -> dict:
        idea_id = new_id('idea')
        self.db.execute('INSERT INTO graph_ideas VALUES (?,?,?,?,?)',
                        (idea_id, self.study_id, kind, bounded(origin), seq))
        revision = self._insert_idea_revision(idea_id, kind, body, None, seq)
        return {'idea_id': idea_id, 'revision_id': revision, 'kind': kind}

    def create_human_idea(self, *, kind: str, text: str, assumptions: str = '', scope: str = '',
                          operation_id: str, actor: Actor) -> dict:
        request = dict(kind=kind, text=text, assumptions=assumptions, scope=scope)
        def write(seq):
            if kind not in ('Q', 'H'):
                raise GraphError('invalid', 'human idea path accepts subordinate Q/H only')
            body = self._idea_body(kind, text, assumptions, scope, (), False)
            return self._new_idea(kind, body, {'type': 'human', 'author': asdict(actor)}, seq)
        return self._mutate('create_human_idea', request, operation_id, actor, write, operator=True)

    def create_claim(self, *, text: str, assumptions: str, scope: str, premises: tuple[Ref, ...],
                     joint: bool = True, operation_id: str, actor: Actor) -> dict:
        request = dict(text=text, assumptions=assumptions, scope=scope,
                       premises=[asdict(r) for r in premises], joint=joint)
        return self._mutate('create_claim', request, operation_id, actor, lambda seq: self._new_idea(
            'C', self._idea_body('C', text, assumptions, scope, premises, joint),
            {'type': 'synthesis', 'author': asdict(actor)}, seq))

    def register_note(self, *, proposal_id: str, operation_id: str, actor: Actor) -> dict:
        def write(seq):
            old = self.db.execute('''SELECT o.* FROM graph_registrations r JOIN graph_operations o
                ON r.study_id=o.study_id AND r.seq=o.seq WHERE r.study_id=? AND r.proposal_id=?''',
                                  (self.study_id, proposal_id)).fetchone()
            if old:
                raise GraphError('conflict', 'note already registered; replay its original operation ID')
            plans = PlanStore(self.store)
            row, envelope = plans.validate_proposal(proposal_id)
            requests = [dict(r) for r in self.db.execute('''SELECT q.request_id,q.provider_name,
                q.provider_version,q.prompt_sha256 FROM plan_requests q JOIN plan_results r
                USING(request_id) WHERE r.proposal_id=? AND r.status='valid' ORDER BY q.request_id LIMIT 65''',
                                                        (proposal_id,))]
            if not requests or len(requests) > 64 or envelope['action']['type'] != 'research_note':
                raise GraphError('invalid', 'only a valid persisted research note may be registered')
            action = envelope['action']
            kind = {'question': 'Q', 'hypothesis': 'H'}[action['note_kind']]
            provenance = {'type': 'research_note', 'proposal_id': proposal_id,
                          'content_sha256': row['content_sha256'],
                          'context_sha256': row['context_sha256'], 'requests': requests}
            result = self._new_idea(kind, self._idea_body(kind, action['text'], '', '', (), False),
                                    provenance, seq)
            self.db.execute('INSERT INTO graph_registrations VALUES (?,?,?,?,?,?)',
                            (self.study_id, proposal_id, result['idea_id'], result['revision_id'],
                             bounded(provenance), seq))
            return result
        return self._mutate('register_note', {'proposal_id': proposal_id}, operation_id, actor, write)

    def revise_idea(self, *, idea_id: str, expected_head: str, text: str,
                    assumptions: str = '', scope: str = '', premises: tuple[Ref, ...] = (),
                    joint: bool = False, operation_id: str, actor: Actor) -> dict:
        request = dict(idea_id=idea_id, expected_head=expected_head, text=text, assumptions=assumptions,
                       scope=scope, premises=[asdict(r) for r in premises], joint=joint)
        def write(seq):
            row = self.db.execute('''SELECT i.kind,i.seq AS creation_seq,r.revision_id FROM graph_ideas i
                JOIN graph_idea_revisions r USING(idea_id) WHERE idea_id=? ORDER BY r.seq DESC LIMIT 1''',
                                  (idea_id,)).fetchone()
            if not row:
                raise GraphError('not_found', 'unknown idea')
            self._require_revision_owner(row['creation_seq'], actor)
            if row['revision_id'] != expected_head:
                raise GraphError('conflict', 'stale idea revision head')
            body = self._idea_body(row['kind'], text, assumptions, scope, premises, joint)
            revision = self._insert_idea_revision(idea_id, row['kind'], body, expected_head, seq)
            return {'idea_id': idea_id, 'revision_id': revision, 'kind': row['kind']}
        return self._mutate('revise_idea', request, operation_id, actor, write)

    def _creation_context(self, source: Ref, target: Ref, proposal_id: str | None) -> None:
        if target.role != 'E' or not proposal_id:
            raise GraphError('invalid', 'creation provenance requires exact proposal and evidence source')
        if source.role == 'T':
            valid = self.db.execute('SELECT 1 FROM plan_receipts WHERE proposal_id=? AND task_id=?',
                                    (proposal_id, source.id)).fetchone()
        elif source.role in ('Q', 'H'):
            valid = self.db.execute('''SELECT 1 FROM graph_registrations WHERE proposal_id=?
                AND idea_id=? AND revision_id=?''', (proposal_id, source.id, source.revision)).fetchone()
        else:
            valid = False
        if not valid:
            raise GraphError('invalid', 'source is not the original registered/imported proposal content')
        plans = PlanStore(self.store)
        _, envelope = plans.validate_proposal(proposal_id)
        _, context = plans.context(envelope['context_sha256'])
        request = self.db.execute("SELECT 1 FROM plan_results WHERE proposal_id=? AND status='valid'",
                                  (proposal_id,)).fetchone()
        if (not request or target.id not in envelope['evidence_refs'] or
                target.id not in {e['evidence_id'] for e in context['evidence']}):
            raise GraphError('invalid', 'motivation was not explicitly recorded in creation proposal')

    def _derivation_cycle(self, source: Ref, target: Ref) -> None:
        if target.role == 'E':
            return
        pending = [target]
        visited = set()
        edges = 0
        while pending:
            ref = pending.pop()
            key = (ref.id, ref.revision)
            if key == (source.id, source.revision):
                raise GraphError('invalid', 'circular derivation lineage')
            if key in visited:
                continue
            visited.add(key)
            if len(visited) > 1024:
                raise GraphError('limit', 'derivation reachability exceeds node limit')
            # Preserve lineage across withdrawn/replaced assertions as well.
            for row in self.db.execute('''SELECT r.body FROM graph_link_revisions r
                JOIN graph_links l USING(link_id) WHERE l.type='DERIVED_FROM'
                AND r.source_role=? AND r.source_id=? LIMIT 2049''', (ref.role, ref.id)):
                edges += 1
                if edges > 2048:
                    raise GraphError('limit', 'derivation reachability exceeds edge limit')
                body = json.loads(row['body'])
                if body['source']['revision'] == ref.revision and body['target']['role'] != 'E':
                    pending.append(Ref(**body['target']))

    def _link_body(self, type, source, target, rationale, assumptions, scope,
                   polarity, timing, proposal_id) -> dict:
        if type not in EDGE_ROLES:
            raise GraphError('invalid', 'unknown semantic type or forged factual edge')
        self._ref(source)
        self._ref(target)
        allowed_source, allowed_target = EDGE_ROLES[type]
        if source.role not in allowed_source or target.role not in allowed_target:
            raise GraphError('invalid', 'invalid directed endpoint roles')
        if (source.role, source.id) == (target.role, target.id):
            raise GraphError('invalid', 'self-links are forbidden')
        text(rationale, 'rationale')
        text(assumptions, 'assumptions', empty=type != 'ASSESSES')
        text(scope, 'scope', empty=type != 'ASSESSES')
        if (type == 'ASSESSES' and polarity not in POLARITIES) or (type != 'ASSESSES' and polarity is not None):
            raise GraphError('invalid', 'assessment requires exactly one permitted polarity')
        if timing not in ('retrospective', 'unknown', 'creation_context'):
            raise GraphError('invalid', 'invalid provenance timing')
        if timing == 'creation_context':
            if type != 'MOTIVATED_BY':
                raise GraphError('invalid', 'creation context applies only to recorded motivation')
            self._creation_context(source, target, proposal_id)
        elif proposal_id is not None:
            raise GraphError('invalid', 'proposal pin requires verified creation context')
        if type == 'DERIVED_FROM':
            self._derivation_cycle(source, target)
        return {'source': asdict(source), 'target': asdict(target), 'rationale': rationale,
                'assumptions': assumptions, 'scope': scope, 'polarity': polarity,
                'timing': timing, 'proposal_id': proposal_id}

    def _link_revision(self, link_id, body, previous, visibility, seq) -> str:
        revision = new_id('lr')
        self.db.execute('INSERT INTO graph_link_revisions VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                        (revision, link_id, previous, body['source']['role'], body['source']['id'],
                         body['target']['role'], body['target']['id'], bounded(body), visibility,
                         self.study_id, seq))
        return revision

    def _insert_link(self, type, source, target, rationale, assumptions, scope,
                     polarity, timing, proposal_id, seq) -> dict:
        body = self._link_body(type, source, target, rationale, assumptions, scope,
                               polarity, timing, proposal_id)
        link_id = new_id('link')
        self.db.execute('INSERT INTO graph_links VALUES (?,?,?,?)',
                        (link_id, self.study_id, type, seq))
        revision = self._link_revision(link_id, body, None, 'unreviewed', seq)
        return {'link_id': link_id, 'revision_id': revision}

    def add_semantic_link(self, *, type: str, source: Ref, target: Ref, rationale: str,
                          assumptions: str = '', scope: str = '', polarity: str | None = None,
                          timing: str = 'retrospective', proposal_id: str | None = None,
                          operation_id: str, actor: Actor) -> dict:
        request = dict(type=type, source=asdict(source), target=asdict(target), rationale=rationale,
                       assumptions=assumptions, scope=scope, polarity=polarity,
                       timing=timing, proposal_id=proposal_id)
        return self._mutate('add_semantic_link', request, operation_id, actor,
                            lambda seq: self._insert_link(type, source, target, rationale, assumptions,
                                                         scope, polarity, timing, proposal_id, seq))

    def revise_or_withdraw_link(self, *, link_id: str, expected_head: str, rationale: str,
                                assumptions: str = '', scope: str = '', polarity: str | None = None,
                                target: Ref | None = None, withdraw: bool = False,
                                operation_id: str, actor: Actor) -> dict:
        request = dict(link_id=link_id, expected_head=expected_head, rationale=rationale,
                       assumptions=assumptions, scope=scope, polarity=polarity,
                       target=asdict(target) if target else None, withdraw=withdraw)
        def write(seq):
            if type(withdraw) is not bool:
                raise GraphError('invalid', 'withdraw must be boolean')
            row = self.db.execute('''SELECT l.type,l.seq AS creation_seq,r.* FROM graph_links l
                JOIN graph_link_revisions r USING(link_id) WHERE link_id=? ORDER BY r.seq DESC LIMIT 1''',
                                  (link_id,)).fetchone()
            if not row:
                raise GraphError('not_found', 'unknown semantic link')
            self._require_revision_owner(row['creation_seq'], actor)
            if row['revision_id'] != expected_head:
                raise GraphError('conflict', 'stale link revision head')
            old = json.loads(row['body'])
            if withdraw:
                if target is not None or polarity is not None or assumptions or scope:
                    raise GraphError('invalid', 'withdrawal retains original content/endpoints')
                text(rationale, 'withdrawal reason')
                body = {**old, 'correction_reason': rationale}
            else:
                # A correction is attributed now. It cannot inherit creation-time claims.
                body = self._link_body(row['type'], Ref(**old['source']), target or Ref(**old['target']),
                                       rationale, assumptions, scope, polarity, 'retrospective', None)
            revision = self._link_revision(link_id, body, expected_head,
                                           'withdrawn' if withdraw else 'unreviewed', seq)
            return {'link_id': link_id, 'revision_id': revision}
        return self._mutate('revise_or_withdraw_link', request, operation_id, actor, write)

    def create_baseline(self, *, scope: str, method: str, configuration: str,
                        references: tuple[Ref, ...] = (), operation_id: str, actor: Actor) -> dict:
        request = dict(scope=scope, method=method, configuration=configuration,
                       references=[asdict(r) for r in references])
        def write(seq):
            text(scope, 'scope')
            text(method, 'method')
            text(configuration, 'configuration')
            body = {**request, 'references': self._refs(references)}
            baseline = new_id('baseline')
            self.db.execute('INSERT INTO graph_baselines VALUES (?,?,?,?,?)',
                            (baseline, self.study_id, scope, bounded(body), seq))
            return {'baseline_id': baseline}
        return self._mutate('create_baseline', request, operation_id, actor, write, operator=True)

    def record_baseline_transition(self, *, scope: str, new_baseline: str,
                                   expected_prior: str | None, rationale: str,
                                   motivations: tuple[Ref, ...],
                                   affected: tuple[tuple[Ref, str], ...] = (),
                                   operation_id: str, actor: Actor) -> dict:
        request = dict(scope=scope, new_baseline=new_baseline, expected_prior=expected_prior,
                       rationale=rationale, motivations=[asdict(r) for r in motivations],
                       affected=[{'ref': asdict(r), 'disposition': d} for r, d in affected])
        def write(seq):
            text(scope, 'scope')
            text(rationale, 'rationale')
            refs = self._refs(motivations, 'EC')
            for baseline in (new_baseline, expected_prior):
                if baseline is None:
                    continue
                self._ref(Ref('B', baseline))
                if self.db.execute('SELECT scope FROM graph_baselines WHERE baseline_id=?',
                                   (baseline,)).fetchone()[0] != scope:
                    raise GraphError('invalid', 'baseline scope mismatch')
            current = self.db.execute('''SELECT new_baseline FROM graph_transitions
                WHERE study_id=? AND scope=? ORDER BY seq DESC LIMIT 1''',
                                      (self.study_id, scope)).fetchone()
            if (current[0] if current else None) != expected_prior:
                raise GraphError('conflict', 'stale scoped baseline predecessor')
            if current is not None and not refs:
                raise GraphError('invalid', 'baseline replacement requires exact motivating evidence/claim')
            if new_baseline == expected_prior:
                raise GraphError('invalid', 'transition requires a different baseline')
            self._refs(tuple(r for r, _ in affected), 'TQHC')
            if any(d not in ('retain', 'redirect_proposed', 'pause_direction') for _, d in affected):
                raise GraphError('invalid', 'unknown affected direction disposition')
            transition = new_id('transition')
            basis = 'initial_reference_choice' if current is None else 'evidence_motivated_transition'
            self.db.execute('INSERT INTO graph_transitions VALUES (?,?,?,?,?,?,?)',
                            (transition, self.study_id, scope, expected_prior, new_baseline,
                             bounded({**request, 'basis': basis}), seq))
            return {'transition_id': transition, 'active_baseline': new_baseline, 'scope': scope}
        return self._mutate('record_baseline_transition', request, operation_id, actor, write, operator=True)

    def read_graph(self, *, at_seq: int | None = None, node: Ref | None = None,
                   roles: tuple[str, ...] = (), edge_types: tuple[str, ...] = (),
                   history: bool = False, edge_id: str | None = None,
                   limits: QueryLimits = QueryLimits()) -> dict:
        from arf.graph_query import read_graph
        return read_graph(self, at_seq=at_seq, node=node, roles=roles, edge_types=edge_types,
                          history=history, edge_id=edge_id, limits=limits)

    def as_of(self, graph_seq: int, **kwargs) -> dict:
        return self.read_graph(at_seq=graph_seq, **kwargs)

    def ancestry(self, task_id: str, *, at_seq: int | None = None,
                 limits: QueryLimits = QueryLimits()) -> dict:
        from arf.graph_query import traverse
        return traverse(self, Ref('T', task_id), 'ancestry', at_seq, limits)

    def affected_by(self, evidence_id: str, *, at_seq: int | None = None,
                    limits: QueryLimits = QueryLimits()) -> dict:
        from arf.graph_query import traverse
        return traverse(self, Ref('E', evidence_id), 'affected_by', at_seq, limits)
