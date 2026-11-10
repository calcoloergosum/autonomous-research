"""Trusted offline decision ledger, automatic publication and joint snapshots."""
from dataclasses import asdict
import base64
import json
import math
from pathlib import Path
import time

from arf.authorization import BINDING_FIELDS
from arf.decision_models import (CandidateDefinition, Constraints, Feedback, Policy, Selection, bounded)
from arf.decision_policy import rank
from arf.decision_store import verify
from arf.graph import GraphService
from arf.graph_models import QueryLimits, Ref
from arf.graph_query import _read_graph_in_transaction
from arf.models import TaskSpec
from arf.plan_models import PlanError, canonical, hash_text, sha, text
from arf.plan_store import PlanStore
from arf.store import Store, utc_now


def profile() -> dict:
    files = ('worker.py', 'executor.py', 'models.py', 'service.py', 'store.py',
             'decisions.py', 'decision_models.py', 'dispatch.py', 'replanning.py', 'bootstrap.py')
    return {'name': 'fixed-demo-single-host', 'version': 1, 'worker': 'demo_mean',
            'active_runs': 1, 'timeout_seconds': 5,
            'source_sha256': sha(b''.join((Path(__file__).parent / f).read_bytes() for f in files))}


def candidate_id(study: str, kind: str, key: str) -> str:
    return 'candidate-' + sha(canonical([study, kind, key]))


def selection_from(data: dict) -> Selection:
    return Selection(roles=tuple(data['roles']), edge_types=tuple(data['edge_types']),
                     node=Ref(**data['node']) if data['node'] else None,
                     limits=QueryLimits(**data['limits']), omissions=data['omissions'])


def feedback_from(data: dict) -> Feedback:
    from arf.decision_models import Rule
    return Feedback(source=data['source'], branch=data['branch'], evidence_refs=tuple(data['evidence_refs']),
                    rules=tuple(Rule(**r) for r in data['rules']), cost_overrides=data['cost_overrides'])


class DecisionService:
    def __init__(self, store: Store):
        self.store, self.db = store, store.connection
        if self.db.execute('PRAGMA user_version').fetchone()[0] != 4:
            raise PlanError('schema', 'decisions require explicit v3 to v4 migration')
        verify(store, required_only=True)
        self.study = store.study()
        self.study_id = self.study['study_id']
        self.plans = PlanStore(store)
        self.graph = GraphService(store)

    def _get(self, table: str, key: str, value: str, column: str = 'result') -> dict:
        text(value, key)
        row = self.db.execute(f'SELECT {column} FROM {table} WHERE {key}=?', (value,)).fetchone()
        if row is None:
            raise PlanError('not_found', f'unknown {key}')
        return json.loads(row[0])

    def _replay(self, table: str, key: str, value: str, request: dict) -> dict | None:
        text(value, key)
        row = self.db.execute(f'SELECT request_sha256,result FROM {table} WHERE {key}=?', (value,)).fetchone()
        if row:
            if row[0] != sha(bounded(request)):
                raise PlanError('conflict', 'request ID reused with different inputs/actor')
            return json.loads(row[1])
        return None

    def _actor(self, actor: str) -> str:
        return text(actor, 'trusted actor')

    def binding(self, task_id: str) -> dict:
        task = self.store.task(task_id)
        spec = {k: task[k] for k in ('task_id', 'study_id', 'title', 'description', 'kind', 'input', 'dependencies')}
        spec['dependencies'] = sorted(spec['dependencies'])
        TaskSpec.parse(spec)
        digest = sha(canonical(spec))
        receipt = self.db.execute('SELECT * FROM plan_receipts WHERE study_id=? AND task_id=?',
                                  (self.study_id, task_id)).fetchone()
        if receipt:
            proposal, envelope = self.plans.validate_proposal(receipt['proposal_id'])
            decision = self.plans.decision(receipt['proposal_id'])
            if (not decision or decision['decision'] != 'approve'
                    or any(decision[k] != proposal[k] for k in BINDING_FIELDS)
                    or envelope['action'] != {'type': 'task_candidate', 'task_spec': spec}
                    or receipt['spec_sha256'] != digest):
                raise PlanError('unauthorized', 'invalid imported admission provenance')
            admission = {'kind': 'approved_import', 'receipt': dict(receipt), 'approval': decision,
                         'proposal_content_sha256': proposal['content_sha256']}
        else:
            admission = {'kind': 'manual', 'sequence': task['sequence'], 'created_at': task['created_at']}
        if task['study_id'] != self.study_id:
            raise PlanError('invalid', 'wrong study binding')
        return {'study_id': self.study_id, 'task_id': task_id, 'spec_sha256': digest, 'admission': admission}

    def _validate_feedback(self, feedback: Feedback) -> None:
        text(feedback.source, 'fixture source')
        if feedback.branch not in ('unknown', 'viable', 'nonviable') or len(feedback.rules) > 64 or len(feedback.evidence_refs) > 64:
            raise PlanError('invalid', 'invalid bounded synthetic feedback')
        if len({r.task_id for r in feedback.rules}) != len(feedback.rules):
            raise PlanError('invalid', 'duplicate relevance rule')
        for r in feedback.rules:
            hash_text(r.spec_sha256)
            if r.effect not in ('engineering_only', 'branch_from_mean') or self.binding(r.task_id)['spec_sha256'] != r.spec_sha256:
                raise PlanError('invalid', 'rule requires exact admitted task/spec')
            if r.cost_surprise is not None and (type(r.cost_surprise) is not int or r.cost_surprise < 0):
                raise PlanError('invalid', 'invalid synthetic surprise')
        rules = {r.task_id: r for r in feedback.rules}
        revealed = []
        allowed_costs = {}
        for evidence_id in feedback.evidence_refs:
            row = self.db.execute('SELECT * FROM evidence WHERE evidence_id=? AND study_id=?',
                                  (evidence_id, self.study_id)).fetchone()
            if not row or row['task_id'] not in rules:
                raise PlanError('invalid', 'revealed feedback needs rule-linked observed evidence')
            rule = rules[row['task_id']]
            if rule.effect == 'branch_from_mean':
                revealed.append('viable' if json.loads(row['result_json'])['mean'] >= 5 else 'nonviable')
            if rule.cost_surprise is not None:
                # Cost surprise concerns the candidate whose origin matches the task ID.
                allowed_costs[rule.task_id] = rule.cost_surprise
        if feedback.branch != 'unknown' and (not revealed or any(b != feedback.branch for b in revealed)):
            raise PlanError('invalid', 'unrevealed or contradictory branch is not an oracle input')
        if feedback.cost_overrides != allowed_costs:
            raise PlanError('invalid', 'synthetic cost overrides require revealed rule provenance')

    def _context_body(self, selection: Selection, feedback: Feedback) -> dict:
        if not self.db.in_transaction:
            raise PlanError('invalid', 'joint snapshot requires caller transaction')
        selection.limits.validate()
        bounded(asdict(selection))
        bounded(asdict(feedback))
        self._validate_feedback(feedback)
        execution = self.plans.context_bytes()
        graph = _read_graph_in_transaction(self.graph, node=selection.node, roles=selection.roles,
                                          edge_types=selection.edge_types, limits=selection.limits)
        body = {'version': 1, 'study_id': self.study_id, 'charter_sha256': self.study['source_sha256'],
                'selection': asdict(selection), 'query_version': 1, 'graph': graph,
                'selection_complete': not graph['truncated'], 'portfolio_completeness': 'partial',
                'execution': json.loads(execution), 'execution_sha256': sha(execution),
                'feedback': asdict(feedback), 'feedback_sha256': sha(canonical(asdict(feedback))),
                'profile': profile()}
        raw = canonical(body)
        if len(canonical({'context_id': '0' * 64, **body})) > 2 * 1024 * 1024:
            raise PlanError('limit', 'decision context exceeds 2 MiB; nothing dropped')
        return body

    def capture_context(self, selection: Selection = Selection(), feedback: Feedback = Feedback()) -> dict:
        if self.db.in_transaction:
            raise PlanError('invalid', 'capture owns a read transaction')
        self.db.execute('BEGIN')
        try:
            body = self._context_body(selection, feedback)
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise
        raw = canonical(body)
        digest = sha(raw)
        with self.store.transaction():
            self.db.execute('INSERT OR IGNORE INTO decision_contexts VALUES (?,?,?,?,?)',
                            (digest, self.study_id, self.study['source_sha256'], raw, utc_now()))
        return {'context_id': digest, **json.loads(raw)}

    def show_context(self, context_id: str) -> dict:
        body = self._get('decision_contexts', 'context_id', context_id, 'body')
        if (sha(canonical(body)) != context_id or body['study_id'] != self.study_id
                or body['charter_sha256'] != self.study['source_sha256']
                or sha(canonical(body['execution'])) != body['execution_sha256']
                or body['execution']['study']['source_sha256'] != self.study['source_sha256']
                or base64.b64decode(body['execution']['study']['source_base64']) != self.study['source']):
            raise PlanError('invalid', 'context binding mismatch')
        return {'context_id': context_id, **body}

    def record_candidates(self, request_id: str, definitions: list[CandidateDefinition],
                          bindings: dict[str, str], actor: str) -> dict:
        request = {'definitions': [asdict(d) for d in definitions], 'bindings': bindings, 'actor': self._actor(actor)}
        bounded(request)
        if not 1 <= len(definitions) <= 64 or len({d.origin_key for d in definitions}) != len(definitions):
            raise PlanError('limit', 'batch requires 1..64 distinct origins')
        if not set(bindings) <= {d.origin_key for d in definitions}:
            raise PlanError('invalid', 'binding lacks candidate definition')
        with self.store.transaction():
            replay = self._replay('decision_batches', 'request_id', request_id, request)
            if replay is not None:
                return replay
            versions = []
            for d in definitions:
                self._validate_definition(d)
                cid = candidate_id(self.study_id, d.origin_kind, d.origin_key)
                binding = self.binding(bindings[d.origin_key]) if d.origin_key in bindings else None
                body = {'study_id': self.study_id, 'charter_sha256': self.study['source_sha256'],
                        'candidate_id': cid, 'version': d.version, 'definition': asdict(d), 'binding': binding}
                raw = bounded(body)
                existing = self.db.execute('SELECT body FROM decision_candidates WHERE study_id=? AND candidate_id=? AND version=?',
                                           (self.study_id, cid, d.version)).fetchone()
                if existing:
                    if existing[0] != raw:
                        raise PlanError('conflict', 'immutable candidate version differs')
                else:
                    head = self.db.execute('SELECT max(version) FROM decision_candidates WHERE study_id=? AND candidate_id=?',
                                           (self.study_id, cid)).fetchone()[0]
                    if d.previous != head or d.version != (head or 0) + 1:
                        raise PlanError('conflict', 'candidate expected-prior mismatch')
                    self.db.execute('INSERT INTO decision_candidates VALUES (?,?,?,?,?,?,?,?)',
                                    (self.study_id, cid, d.version, d.previous, d.origin_key, raw,
                                     binding['task_id'] if binding else None, utc_now()))
                versions.append([cid, d.version])
            result = {'request_id': request_id, 'versions': versions}
            self.db.execute('INSERT INTO decision_batches VALUES (?,?,?,?,?)',
                            (request_id, sha(bounded(request)), self.study_id, bounded(result), utc_now()))
            return result

    def _validate_definition(self, d: CandidateDefinition) -> None:
        if (d.kind not in ('explore', 'experiment', 'replicate', 'synthesize')
                or type(d.version) is not int or d.version < 1
                or (d.previous is not None and type(d.previous) is not int) or len(d.refs) > 64
                or type(d.origin_order) is not int or d.origin_order < 0):
            raise PlanError('invalid', 'invalid candidate identity/kind/version/refs')
        for v in (d.origin_key, d.origin_kind, d.description, d.intended_result):
            text(v, 'candidate text')
        hash_text(d.origin_sha256)
        if d.impact.status not in ('qualitative', 'unknown', 'incomparable', 'contested'):
            raise PlanError('invalid', 'impact status must preserve qualitative uncertainty')
        for v in asdict(d.impact).values():
            text(v, 'impact judgment')
        for ref in d.refs:
            self.graph._ref(ref)
        if d.synthetic:
            for v in (d.synthetic.viable, d.synthetic.nonviable, d.synthetic.information_bonus):
                if type(v) is not int or not 0 <= v <= 10**9:
                    raise PlanError('invalid', 'synthetic proxies must be bounded nonnegative integers')
            if type(d.synthetic.branch_relevant) is not bool:
                raise PlanError('invalid', 'branch relevance must be boolean')
            for k, v in asdict(d.synthetic.costs).items():
                if k != 'currency' and v is not None and (type(v) not in (int, float) or (isinstance(v, float) and not math.isfinite(v)) or not 0 <= v <= 10**15):
                    raise PlanError('invalid', 'resource costs must be nonnegative finite or unknown')
            if d.synthetic.costs.money is not None:
                text(d.synthetic.costs.currency, 'money currency')

    def candidate(self, cid: str, version: int) -> dict:
        row = self.db.execute('SELECT body FROM decision_candidates WHERE study_id=? AND candidate_id=? AND version=?',
                              (self.study_id, cid, version)).fetchone()
        if not row:
            raise PlanError('not_found', 'unknown candidate version')
        body = json.loads(row[0])
        if (body['candidate_id'] != cid or body['version'] != version
                or candidate_id(self.study_id, body['definition']['origin_kind'], body['definition']['origin_key']) != cid):
            raise PlanError('invalid', 'candidate identity mismatch')
        return body

    def heads(self) -> list[list]:
        rows = self.db.execute('''SELECT candidate_id,max(version) FROM decision_candidates
            WHERE study_id=? GROUP BY candidate_id ORDER BY candidate_id LIMIT 65''', (self.study_id,)).fetchall()
        if len(rows) > 64:
            raise PlanError('limit', 'candidate selection exceeds 64; no silent truncation')
        return [[r[0], r[1]] for r in rows]

    def check_bindings(self, candidates: list[dict]) -> None:
        mapped = []
        for c in candidates:
            if c['study_id'] != self.study_id or c['charter_sha256'] != self.study['source_sha256']:
                raise PlanError('invalid', 'candidate study/charter mismatch')
            if c['binding']:
                task_id = c['binding']['task_id']
                if c['binding'] != self.binding(task_id):
                    raise PlanError('unauthorized', 'candidate task/spec/admission binding differs')
                mapped.append(task_id)
        if len(mapped) != len(set(mapped)):
            raise PlanError('invalid', 'duplicate mapped task')

    def decide(self, request_id: str, context_id: str, candidates: list[list],
               policy: Policy = Policy(), constraints: Constraints = Constraints(),
               actor: str = 'offline-manager', previous_decision_id: str | None = None,
               *, controller_profile: dict | None = None) -> dict:
        request = {'context_id': context_id, 'candidates': candidates, 'policy': asdict(policy),
                   'constraints': asdict(constraints), 'actor': self._actor(actor), 'previous': previous_decision_id}
        if controller_profile is not None:
            request['controller_profile'] = controller_profile
        bounded(request)
        replay = self._replay('research_decisions', 'decision_id', request_id, request)
        if replay is not None:
            return replay
        if (not isinstance(candidates, list) or not 1 <= len(candidates) <= 64
                or any(not isinstance(p, (list, tuple)) or len(p) != 2 or not isinstance(p[0], str)
                       or type(p[1]) is not int or p[1] < 1 for p in candidates)
                or len({p[0] for p in candidates}) != len(candidates)):
            raise PlanError('invalid', 'decision needs 1..64 distinct exact candidates')
        manifest = self.heads()
        context = self.show_context(context_id)
        records = [self.candidate(*pair) for pair in candidates]
        self.check_bindings(records)
        start = time.monotonic()
        result = {'decision_id': request_id, 'context_id': context_id, 'previous': previous_decision_id,
                  'candidate_heads': manifest, **rank(context, records, policy, constraints)}
        elapsed = time.monotonic() - start
        if controller_profile is not None:
            result['controller_profile'] = controller_profile
        result['calculation_cost'] = {'wall_seconds': elapsed, 'cpu_seconds': None, 'source': 'measured_controller_wall'}
        raw = bounded(result, 262144)
        with self.store.transaction():
            replay = self._replay('research_decisions', 'decision_id', request_id, request)
            if replay is not None:
                return replay
            self.check_bindings(records)
            if self.heads() != manifest:
                raise PlanError('stale_context', 'candidate heads changed during assessment')
            self.db.execute('INSERT INTO research_decisions VALUES (?,?,?,?,?,?,?,?,?)',
                            (request_id, sha(bounded(request)), self.study_id, context_id, previous_decision_id,
                             bounded(request), raw, elapsed, utc_now()))
            for m in result['members']:
                self.db.execute('INSERT INTO decision_members VALUES (?,?,?,?,?,?,?)',
                                (self.study_id, request_id, m['candidate_id'], m['version'], m['ordinal'],
                                 m['priority_group'], bounded(m)))
        return json.loads(raw)

    def validate_decision(self, decision: dict) -> list[dict]:
        from arf.decision_policy import identity
        if decision['policy']['source_sha256'] != identity()['source_sha256']:
            raise PlanError('invalid', 'installed policy implementation differs from saved decision')
        row = self.db.execute('SELECT request_sha256,request FROM research_decisions WHERE decision_id=?',
                              (decision['decision_id'],)).fetchone()
        request = json.loads(row['request'])
        policy_input = {k: decision['policy'][k] for k in ('name', 'version', 'weight')}
        pairs = [[m['candidate_id'], m['version']] for m in decision['members']]
        if (row['request_sha256'] != sha(row['request']) or request['policy'] != policy_input
                or request['constraints'] != decision['constraints']
                or request['context_id'] != decision['context_id']
                or request.get('controller_profile') != decision.get('controller_profile')
                or sorted(request['candidates']) != sorted(pairs)):
            raise PlanError('invalid', 'decision request/configuration binding mismatch')
        saved_members = list(self.db.execute('SELECT * FROM decision_members WHERE decision_id=? ORDER BY ordinal',
                                             (decision['decision_id'],)))
        if len(saved_members) != len(pairs) or any(
            json.loads(row['body']) != m or row['ordinal'] != m['ordinal']
            or row['priority_group'] != m['priority_group'] for row, m in zip(saved_members, decision['members'])):
            raise PlanError('invalid', 'decision membership ledger mismatch')
        records = [self.candidate(m['candidate_id'], m['version']) for m in decision['members']]
        self.check_bindings(records)
        for c, m in zip(records, decision['members']):
            if (c['binding'] != m['binding'] or m['estimate']['context_id'] != decision['context_id']
                    or m['estimate']['estimator'] != identity()):
                raise PlanError('invalid', 'saved decision member binding/implementation differs')
        return records

    def show_decision(self, decision_id: str) -> dict:
        return self._get('research_decisions', 'decision_id', decision_id)

    def show_publication(self, publication_id: str) -> dict:
        return self._get('decision_publications', 'publication_id', publication_id)

    def show_assessment(self, assessment_id: str) -> dict:
        return self._get('decision_assessments', 'assessment_id', assessment_id)

    def show_dispatch(self, dispatch_id: str) -> dict:
        return self._get('decision_dispatches', 'dispatch_id', dispatch_id)

    def list_decisions(self, limit: int = 32, offset: int = 0) -> dict:
        if type(limit) is not int or not 1 <= limit <= 64 or type(offset) is not int or offset < 0:
            raise PlanError('limit', 'invalid decision page')
        rows = self.db.execute('''SELECT result FROM research_decisions
            WHERE study_id=? ORDER BY created_at,decision_id LIMIT ? OFFSET ?''', (self.study_id, limit + 1, offset)).fetchall()
        items = []
        size = 128
        for row in rows[:limit]:
            needed = len(row[0]) + 1
            if size + needed > 2 * 1024 * 1024:
                if not items:
                    raise PlanError('limit', 'single decision exceeds response cap')
                break
            items.append(json.loads(row[0]))
            size += needed
        return {'items': items, 'next_offset': offset + len(items) if len(rows) > len(items) else None}

    def head(self) -> str | None:
        row = self.db.execute('''SELECT publication_id FROM decision_publications p WHERE study_id=?
            AND NOT EXISTS (SELECT 1 FROM decision_publications n WHERE n.previous=p.publication_id)''',
                              (self.study_id,)).fetchone()
        return row[0] if row else None

    def _matches(self, context: dict) -> bool:
        actual = self._context_body(selection_from(context['selection']), feedback_from(context['feedback']))
        return sha(canonical(actual)) == context['context_id']

    def publish(self, request_id: str, decision_id: str, expected_prior: str | None,
                actor: str = 'trusted-controller') -> dict:
        request = {'decision_id': decision_id, 'expected_prior': expected_prior, 'actor': self._actor(actor)}
        with self.store.transaction():
            replay = self._replay('decision_publications', 'publication_id', request_id, request)
            if replay is not None:
                return replay
            decision = self.show_decision(decision_id)
            context = self.show_context(decision['context_id'])
            if self.head() != expected_prior:
                raise PlanError('conflict', 'publication expected-head mismatch')
            if context['profile'] != profile() or not self._matches(context):
                raise PlanError('stale_context', 'publication snapshot/profile changed')
            records = self.validate_decision(decision)
            self.check_bindings(records)
            if decision['candidate_heads'] != self.heads():
                raise PlanError('stale_context', 'candidate manifest changed')
            if any(pair not in self.heads() for pair in [[r['candidate_id'], r['version']] for r in records]):
                raise PlanError('stale_context', 'candidate head changed')
            result = {'publication_id': request_id, 'decision_id': decision_id, 'previous': expected_prior,
                      'context_id': context['context_id'], 'actor': actor, 'automatic': True,
                      'candidate_heads': decision['candidate_heads'], 'profile': profile()}
            self.db.execute('INSERT INTO decision_publications VALUES (?,?,?,?,?,?,?)',
                            (request_id, sha(bounded(request)), self.study_id, decision_id, expected_prior,
                             bounded(result), utc_now()))
            return result
