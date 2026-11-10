// Versioned runtime boundary. Unknown JSON is never asserted to be a DTO.
export type Json = null | boolean | number | string | Json[] | { [key: string]: Json };
export type Obj = { [key: string]: Json };
export type Scope = 'current_execution' | 'recorded_history' | 'snapshot_at_decision';
export type Kind = 'task' | 'dispatch' | 'run' | 'evidence' | 'decision';
export type Selection = { kind: Kind; id: string };
export type SourceRef = {kind: Kind | 'candidate' | 'context' | 'publication' | 'assessment' | 'graph'; id: string; revision: string | null; source_table: string; temporal_scope: Scope; version?: number};
export type Member = {candidate_id: string; version: number; ordinal: number; priority_group: number | null; exclusion: string | null; binding: Obj | null; estimate: Obj; raw: Obj};
export type Decision = {decision_id: string; context_id: string; members: Member[]; policy: Obj; status: string; reason: string | null; raw: Obj};
export type Task = {task_id: string; title: string; status: string; blockers: Obj[]; created_at: string; raw: Obj};
export type Dispatch = {dispatch_id: string; task_id: string | null; run_id: string | null; decision_id: string | null; status: string; reason: string; created_at: string; raw: Obj};
export type Overview = {tasks: Task[]; task_counts: Obj; task_next_cursor: string | null; dispatches: Dispatch[]; dispatch_next_cursor: string | null; latest_decision_id: string | null; publication_head_id: string | null; observed_generation: number};
export type Meta = {question: string; charter_sha256: string; schema_version: number; epoch: string; generation: number};
export type Changes = {epoch: string; generation: number; token: string; changed: boolean; reset_required: boolean};
export type Trace = {focus: Selection; task: Task | null; dispatch: Dispatch | null; decision: Decision | null; members: Member[]; decisions: SourceRef[]; runs: Obj[]; evidence_records: Obj[]; dispatches: Dispatch[]; candidate_versions: Obj[]; graph_assertions: Obj[]; graph_nodes: Obj[]; missing_relations: string[]; truncated: boolean; continuation: Obj | null; raw: Obj};
export type Checkpoint = {decision_id: string; context_id: string; decision: Decision; context: Obj; selection_complete: boolean; portfolio_completeness: string; capture_semantics: string; historical_execution_state: string};
export type Response<T> = {api_version: 1; study_id: string; temporal_scope: Scope; data: T; epoch: string};
export class DecodeError extends Error { constructor(message = 'Malformed observer response') { super(message); } }
export class ApiError extends Error { constructor(public code: string, message: string) { super(message); } }
export function json(value: unknown, depth = 0): Json {
  if (depth > 48) throw new DecodeError('Response nesting exceeds budget');
  if (value === null || typeof value === 'string' || typeof value === 'boolean') return value;
  if (typeof value === 'number' && Number.isFinite(value)) return value;
  if (Array.isArray(value)) return value.map(v => json(v, depth + 1));
  if (typeof value === 'object' && value !== null) {
    const out: Obj = Object.create(null) as Obj;
    for (const [k, v] of Object.entries(value)) out[k] = json(v, depth + 1);
    return out;
  }
  throw new DecodeError();
}
export function obj(value: unknown): Obj { if (typeof value !== 'object' || value === null || Array.isArray(value)) throw new DecodeError(); return json(value) as Obj; }
export function str(value: unknown): string { if (typeof value !== 'string') throw new DecodeError(); return value; }
export function num(value: unknown): number { if (typeof value !== 'number' || !Number.isFinite(value)) throw new DecodeError(); return value; }
export function int(value: unknown): number { const n = num(value); if (!Number.isSafeInteger(n) || n < 0) throw new DecodeError(); return n; }
export function bool(value: unknown): boolean { if (typeof value !== 'boolean') throw new DecodeError(); return value; }
export function arr<T>(value: unknown, decode: (v: unknown) => T): T[] { if (!Array.isArray(value)) throw new DecodeError(); return value.map(decode); }
export function nullable<T>(value: unknown, decode: (v: unknown) => T): T | null { return value === null ? null : decode(value); }
export function scope(value: unknown): Scope { if (value !== 'current_execution' && value !== 'recorded_history' && value !== 'snapshot_at_decision') throw new DecodeError(); return value; }
export function kind(value: unknown): Kind { if (!['task','dispatch','run','evidence','decision'].includes(str(value))) throw new DecodeError(); return value as Kind; }
export function sourceRef(value: unknown): SourceRef {
  const r = obj(value); const k = str(r.kind);
  if (!['task','dispatch','run','evidence','decision','candidate','context','publication','assessment','graph'].includes(k)) throw new DecodeError();
  const result: SourceRef = {kind:k as SourceRef['kind'],id:str(r.id),revision:nullable(r.revision,str),source_table:str(r.source_table),temporal_scope:scope(r.temporal_scope)};
  if (k === 'candidate') result.version = int(r.version);
  return result;
}
export function member(value: unknown): Member {
  const r = obj(value); const estimate = obj(r.estimate);
  const impact = obj(estimate.impact);
  for (const k of ['status','rationale','assumptions','uncertainty','alternatives']) str(impact[k]);
  obj(estimate.costs);
  if (r.binding !== null) str(obj(r.binding).task_id);
  const version = int(r.version); if (version < 1) throw new DecodeError();
  return {candidate_id:str(r.candidate_id),version,ordinal:int(r.ordinal),priority_group:nullable(r.priority_group,num),exclusion:nullable(r.exclusion,str),binding:nullable(r.binding,obj),estimate,raw:r};
}
export function decision(value: unknown): Decision {
  const r = obj(value);
  return {decision_id:str(r.decision_id),context_id:str(r.context_id),members:arr(r.members,member),policy:obj(r.policy),status:str(r.status),reason:nullable(r.reason,str),raw:r};
}
export function task(value: unknown): Task {
  const r = obj(value); const status = str(r.status);
  if (!['pending','running','succeeded','failed','needs_review'].includes(status)) throw new DecodeError();
  const blockers = arr(r.blockers, obj); blockers.forEach(b => {str(b.task_id); str(b.status);});
  return {task_id:str(r.task_id),title:str(r.title),status,blockers,created_at:str(r.created_at),raw:r};
}
export function dispatch(value: unknown): Dispatch {
  const r = obj(value);
  return {dispatch_id:str(r.dispatch_id),task_id:nullable(r.task_id,str),run_id:nullable(r.run_id,str),decision_id:nullable(r.decision_id,str),status:str(r.status),reason:str(r.reason),created_at:str(r.created_at),raw:r};
}
export function overview(value: unknown): Overview {
  const r = obj(value); const counts = obj(r.task_counts);
  for (const key of ['pending','running','succeeded','failed','needs_review']) int(counts[key]);
  return {tasks:arr(r.tasks,task),task_counts:counts,task_next_cursor:nullable(r.task_next_cursor,str),dispatches:arr(r.dispatches,dispatch),dispatch_next_cursor:nullable(r.dispatch_next_cursor,str),latest_decision_id:nullable(r.latest_decision_id,str),publication_head_id:nullable(r.publication_head_id,str),observed_generation:int(r.observed_generation)};
}
export function meta(value: unknown): Meta {
  const r = obj(value); if (r.schema_version !== 4 || r.observer_version !== 1) throw new DecodeError('Unsupported observer/schema version');
  arr(r.capabilities,str);
  return {question:str(r.question),charter_sha256:str(r.charter_sha256),schema_version:4,epoch:str(r.epoch),generation:int(r.generation)};
}
export function changes(value: unknown): Changes {
  const r = obj(value); str(r.observed_at);
  return {epoch:str(r.epoch),generation:int(r.generation),token:str(r.token),changed:bool(r.changed),reset_required:bool(r.reset_required)};
}
export function trace(value: unknown): Trace {
  const r = obj(value); const focus = obj(r.focus);
  // Validate every projected reference and every nullable section, even if folded.
  arr(r.links, v => { const l = obj(v); str(l.relation); sourceRef(l.source); sourceRef(l.target); str(l.source_record_id); return l; });
  for (const k of ['publication','assessment','continuation']) nullable(r[k],obj);
  nullable(r.run, v => {const run = obj(v); str(run.run_id); str(run.status); scope(run.temporal_scope); return run;});
  nullable(r.evidence, v => {const e = obj(v); str(e.evidence_id); if (e.validation_status !== 'unvalidated') throw new DecodeError(); return e;});
  const runs = arr(r.runs,obj); runs.forEach(v => {str(v.run_id); str(v.status); scope(v.temporal_scope);});
  const evidence = arr(r.evidence_records,obj); evidence.forEach(v => {str(v.evidence_id); str(v.run_id); if (v.validation_status !== 'unvalidated') throw new DecodeError();});
  return {focus:{kind:kind(focus.kind),id:str(focus.id)},task:nullable(r.task,task),dispatch:nullable(r.dispatch,dispatch),decision:nullable(r.decision,decision),members:arr(r.members,member),decisions:arr(r.decisions,sourceRef),runs,evidence_records:evidence,dispatches:arr(r.dispatches,dispatch),candidate_versions:arr(r.candidate_versions,obj),graph_assertions:arr(r.graph_assertions,obj),graph_nodes:arr(r.graph_nodes,obj),missing_relations:arr(r.missing_relations,str),truncated:bool(r.truncated),continuation:nullable(r.continuation,obj),raw:r};
}
export function checkpoint(value: unknown): Checkpoint {
  const r = obj(value); const context = obj(r.context);
  obj(context.selection); obj(context.feedback); obj(context.profile); obj(context.execution); obj(context.graph); str(context.execution_sha256);
  if (r.capture_semantics !== 'saved_context_input_not_global_time_travel' || r.historical_execution_state !== 'captured_execution_only') throw new DecodeError();
  const d = decision(r.decision); const id = str(r.decision_id); const cid = str(r.context_id);
  if (d.decision_id !== id || d.context_id !== cid) throw new DecodeError('Checkpoint identity mismatch');
  return {decision_id:id,context_id:cid,decision:d,context,selection_complete:bool(r.selection_complete),portfolio_completeness:str(r.portfolio_completeness),capture_semantics:r.capture_semantics,historical_execution_state:r.historical_execution_state};
}
export function envelope<T>(value: unknown, decode: (v: unknown) => T, epoch: string): Response<T> {
  const r = obj(value); if (r.api_version !== 1) throw new DecodeError('Unsupported API version');
  return {api_version:1,study_id:str(r.study_id),temporal_scope:scope(r.temporal_scope),data:decode(r.data),epoch};
}
export async function request<T>(path: string, decode: (v: unknown) => T, signal?: AbortSignal, expectedEpoch?: string): Promise<Response<T>> {
  const res = await fetch('/api/v1/' + path, {signal,cache:'no-store',credentials:'omit',redirect:'error'});
  const epoch = res.headers.get('X-Observer-Epoch');
  if (!epoch) throw new DecodeError('Missing source epoch');
  if (expectedEpoch && epoch !== expectedEpoch) throw new ApiError('stale_session','Source epoch changed; explicit recheck required');
  const max = path.startsWith('checkpoint?') ? 3*1024*1024 : 256*1024;
  const reader = res.body?.getReader(); if (!reader) throw new DecodeError();
  const chunks: Uint8Array[] = []; let length = 0;
  for (;;) { const {value,done} = await reader.read(); if (done) break; length += value.length; if (length > max) {await reader.cancel(); throw new DecodeError('Response exceeds byte budget');} chunks.push(value); }
  const bytes = new Uint8Array(length); let offset = 0; for (const chunk of chunks) {bytes.set(chunk,offset); offset += chunk.length;}
  let raw: unknown; try {raw = JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(bytes));} catch {throw new DecodeError('Malformed JSON');}
  if (!res.ok) {const error = obj(obj(raw).error); throw new ApiError(str(error.code),str(error.message));}
  const result = envelope(raw,decode,epoch);
  if ((path === 'meta' || path.startsWith('changes')) && obj(obj(raw).data).epoch !== epoch) throw new DecodeError('Envelope epoch mismatch');
  const expectedScope: Scope = path.startsWith('checkpoint?') ? 'snapshot_at_decision' : path === 'meta' ? 'recorded_history' : 'current_execution';
  if (result.temporal_scope !== expectedScope) throw new DecodeError('Unexpected endpoint temporal scope');
  return result;
}
