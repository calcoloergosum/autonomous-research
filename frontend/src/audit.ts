import type { Checkpoint, Json, Member } from './api';
export function canonical(value: Json): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value !== null && typeof value === 'object') return '{' + Object.keys(value).sort().map(k => JSON.stringify(k)+':'+canonical(value[k])).join(',') + '}';
  return JSON.stringify(value);
}
export function same(a: Json, b: Json) { return canonical(a) === canonical(b); }
export function compareCheckpoints(a: Checkpoint, b: Checkpoint) {
  const left = new Map(a.decision.members.map(m => [m.candidate_id,m]));
  const right = new Map(b.decision.members.map(m => [m.candidate_id,m]));
  const candidates = [...new Set([...left.keys(),...right.keys()])].map(id => {
    const before: Member | null = left.get(id) ?? null, after: Member | null = right.get(id) ?? null;
    const changes: string[] = [];
    if (!before) changes.push('arrived in membership');
    else if (!after) changes.push('departed from membership');
    else {
      if (before.version !== after.version) changes.push('new version');
      if (before.ordinal !== after.ordinal || before.priority_group !== after.priority_group) changes.push('order / priority changed');
      if (before.exclusion !== after.exclusion) changes.push('exclusion changed');
      if (!same(before.estimate.costs,after.estimate.costs)) changes.push('estimated costs changed');
      if (!same(before.estimate.impact,after.estimate.impact)) changes.push('recorded judgment / assumptions changed');
      if (!same(before.estimate,after.estimate)) changes.push('recorded estimate / inputs changed');
    }
    return {id,before,after,changes};
  });
  const comparable = a.selection_complete && b.selection_complete && same(a.context.selection,b.context.selection);
  const pairs: [string,Json,Json][] = [
    ['Declared policy',a.decision.policy,b.decision.policy],
    ['Selection roles / edges / root / limits',a.context.selection,b.context.selection],
    ['Feedback / assumptions',a.context.feedback,b.context.feedback],
    ['Installed profile',a.context.profile,b.context.profile],
    ['Original execution hash',a.context.execution_sha256,b.context.execution_sha256],
    ['Captured observed runs / costs',capturedRuns(a.context),capturedRuns(b.context)],
    ['Graph projection / sequence / revisions',a.context.graph,b.context.graph],
  ];
  const ag = graphIdeas(a.context), bg = graphIdeas(b.context);
  const ideas = [...new Set([...ag.keys(),...bg.keys()])].map(id => ({id,
    before:ag.get(id),after:bg.get(id),status:!ag.has(id)?'arrived in selection':!bg.has(id)?'departed from selection':ag.get(id)!==bg.get(id)?'revision changed':'same revision'}));
  return {candidates,comparable,ideas,fields:pairs.map(([label,x,y])=>({label,changed:!same(x,y),before:x,after:y}))};
}
export class Tickets {
  private counters = new Map<string,number>();
  next(lane: string) { const n = (this.counters.get(lane) ?? 0) + 1; this.counters.set(lane,n); return n; }
  current(lane: string, n: number) { return this.counters.get(lane) === n; }
  invalidate() { for (const lane of this.counters.keys()) this.next(lane); }
}

export function graphIdeas(context: Checkpoint['context']) {
  const graph = context.graph;
  if (graph === null || typeof graph !== 'object' || Array.isArray(graph)) return new Map<string, Json>();
  const result = new Map<string,Json>();
  if (!Array.isArray(graph.nodes)) return result;
  for (const node of graph.nodes) {
    if (node === null || typeof node !== 'object' || Array.isArray(node)) continue;
    const ref = node.ref;
    if (ref === null || typeof ref !== 'object' || Array.isArray(ref)) continue;
    if (['Q','H','C'].includes(String(ref.role)) && typeof ref.id === 'string') result.set(ref.id,ref.revision ?? null);
  }
  return result;
}

function capturedRuns(context: Checkpoint['context']): Json {
  const execution = context.execution;
  if (execution === null || typeof execution !== 'object' || Array.isArray(execution)) return null;
  return execution.runs ?? null;
}
