import { useCallback, useEffect, useRef, useState } from 'react';
import { ApiError, checkpoint, changes, meta, obj, overview, request, trace } from './api';
import type { Checkpoint, Decision, Dispatch, Json, Member, Meta, Overview, Selection, Trace } from './api';
import { compareCheckpoints, Tickets } from './audit';
import './style.css';

type Source = {studyId: string; meta: Meta; token: string; stale: boolean; reset: boolean};
type Mode = {kind:'live'} | {kind:'pinned'; decisionId:string};
const message = (e: unknown) => e instanceof Error ? e.message : 'Observer request failed';
const show = (v: Json | undefined): string => v === undefined ? 'not_recorded' : v === null ? 'unknown / unavailable' : typeof v === 'object' ? JSON.stringify(v,null,2) : String(v);
const idQuery = (id: string) => encodeURIComponent(id);
function name(m: Member) { return m.binding?.task_id ? String(m.binding.task_id) : 'Unmapped candidate'; }

export default function App() {
  const [source,setSource] = useState<Source|null>(null);
  const [work,setWork] = useState<Overview|null>(null);
  const [selected,setSelected] = useState<Selection|null>(null);
  const [story,setStory] = useState<Trace|null>(null);
  const [mode,setMode] = useState<Mode>({kind:'live'});
  const [pinned,setPinned] = useState<Checkpoint|null>(null);
  const [comparison,setComparison] = useState<Checkpoint|null>(null);
  const [expanded,setExpanded] = useState<Set<string>>(new Set());
  const [error,setError] = useState('');
  const [loading,setLoading] = useState('Opening local source…');
  const [refresh,setRefresh] = useState(0);
  const [compareId,setCompareId] = useState('');
  const [liveChanges,setLiveChanges] = useState(0);
  const tickets = useRef(new Tickets());
  const sourceRef = useRef(source); sourceRef.current = source;
  const boot = useCallback(async () => {
    tickets.current.invalidate(); const ticket = tickets.current.next('boot');
    setLoading('Verifying local source…'); setError('');
    setSource(null); setWork(null); setStory(null); setSelected(null); setPinned(null); setComparison(null); setMode({kind:'live'}); setExpanded(new Set()); setLiveChanges(0);
    try {
      const m = await request('meta',meta);
      const w = await request('overview',overview,undefined,m.data.epoch);
      const c = await request('changes',changes,undefined,m.data.epoch);
      if (!tickets.current.current('boot',ticket)) return;
      if (m.study_id !== w.study_id || m.study_id !== c.study_id) throw new Error('Source identity mismatch');
      setSource({studyId:m.study_id,meta:m.data,token:c.data.token,stale:false,reset:false}); setWork(w.data); setLoading('');
    } catch (e) { if(tickets.current.current('boot',ticket)) {setError(message(e)); setLoading('');} }
  },[]);
  useEffect(() => {void boot(); return () => tickets.current.invalidate();},[boot]);
  const fail = useCallback((e: unknown) => {
    setError(message(e));
    setSource(s => s ? {...s,stale:true,reset:s.reset || e instanceof ApiError && ['stale_session','unsupported_schema'].includes(e.code)} : s);
  },[]);
  useEffect(() => {
    if (!source || source.reset) return;
    const epoch = source.meta.epoch;
    let stopped = false, timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController(); let token = source.token;
    const poll = async () => {
      if (stopped) return;
      if (document.hidden) {timer = setTimeout(() => void poll(),3000); return;}
      try {
        const c = await request('changes?since='+idQuery(token),changes,controller.signal,epoch);
        if (stopped) return;
        if (c.study_id !== source.studyId || c.data.reset_required) throw new ApiError('stale_session','Source changed. Recheck explicitly before continuing.');
        if (c.data.changed || sourceRef.current?.stale) {
          const w = await request('overview',overview,controller.signal,epoch);
          if (stopped) return;
          if (w.study_id !== source.studyId) throw new ApiError('stale_session','Study changed');
          setWork(w.data); setRefresh(n=>n+1); setLiveChanges(n=>n+1);
        }
        token = c.data.token;
        setSource(s => s && s.meta.epoch === epoch ? {...s,token,stale:false,meta:{...s.meta,generation:c.data.generation}} : s);
        setError('');
      } catch(e) {if (!stopped) fail(e);}
      if (!stopped && !sourceRef.current?.reset) timer = setTimeout(() => void poll(),3000);
    };
    timer = setTimeout(() => void poll(),3000);
    return () => {stopped = true; clearTimeout(timer); controller.abort();};
  },[source?.meta.epoch,source?.reset,fail]);
  useEffect(() => {
    if (!selected || !source || source.reset || mode.kind !== 'live') return;
    const controller = new AbortController(); const ticket = tickets.current.next('trace');
    const epoch = source.meta.epoch; setLoading('Reading exact source links…');
    void request(`trace?kind=${selected.kind}&id=${idQuery(selected.id)}`,trace,controller.signal,epoch).then(r => {
      if (!tickets.current.current('trace',ticket)) return;
      if (r.study_id !== source.studyId) throw new ApiError('stale_session','Study changed');
      setStory(r.data); setLoading('');
    }).catch(e => {if(!controller.signal.aborted && tickets.current.current('trace',ticket)) {setLoading(''); fail(e);}});
    return () => {controller.abort(); tickets.current.next('trace');};
  },[selected?.kind,selected?.id,source?.meta.epoch,source?.reset,mode.kind,refresh,fail]);
  const choose = (selection: Selection) => {tickets.current.next('pin');tickets.current.next('compare');setSelected(selection); if(mode.kind === 'live') setStory(null);};
  const loadCheckpoint = async (id: string, target: 'pin'|'compare') => {
    if (!source || source.reset || !id) return;
    const epoch = source.meta.epoch, ticket = tickets.current.next(target);
    setLoading('Reading saved captured input…');
    try {
      const r = await request('checkpoint?id='+idQuery(id),checkpoint,undefined,epoch);
      if (!tickets.current.current(target,ticket) || sourceRef.current?.meta.epoch !== epoch || sourceRef.current?.reset) return;
      if(r.study_id !== source.studyId) throw new ApiError('stale_session','Study changed');
      if(target === 'pin') {setPinned(r.data);setMode({kind:'pinned',decisionId:id});}
      else setComparison(r.data);
      setLoading(''); setError('');
    } catch(e) {if(tickets.current.current(target,ticket)) {setLoading(''); setError(message(e));}}
  };
  const toggle = (id: string) => setExpanded(old=>{const next = new Set(old);if(next.has(id))next.delete(id);else next.add(id);return next;});
  const raw = (id: string, label: string, value: Json | undefined) => <div className="raw" key={id}><button className="fold" aria-expanded={expanded.has(id)} onClick={()=>toggle(id)}>{expanded.has(id)?'−':'+'} {label}</button>{expanded.has(id)&&<pre>{show(value)}</pre>}</div>;
  const decisionView = (d: Decision) => <>
    <div className="section-head"><div><span className="eyebrow">Recorded recommendation</span><h3>{d.decision_id}</h3></div><span className="tag">synthetic proxy</span></div>
    <p>Policy <strong>{show(d.policy.name)}</strong> · {d.status}{d.reason ? ' · '+d.reason : ''}. Scientific impact remains unknown or incomparable.</p>
    <p className="hint">Order is saved membership order. A ranked candidate can be unmapped or blocked; a dispatch separately records readiness.</p>
    <div className="table-wrap"><table><caption>All considered and excluded alternatives · recorded_history</caption><thead><tr><th>Candidate / binding</th><th>Version / order</th><th>Priority group</th><th>Recorded judgment</th><th>Synthetic proxy</th></tr></thead><tbody>{d.members.map(m=><tr key={m.candidate_id}><td>{m.binding && mode.kind==='live' ? <button className="subtle" onClick={()=>{if(mode.kind==='live') choose({kind:'task',id:String(m.binding!.task_id)});}}>{name(m)}</button> : <strong>{name(m)}</strong>}<small>{m.candidate_id}</small></td><td>v{m.version} / {m.ordinal}</td><td>{m.priority_group === null ? 'unranked' : m.priority_group}<small>{m.exclusion ?? 'no exclusion recorded'}</small></td><td><strong>{show(obj(m.estimate.impact).status)}</strong><p>{show(obj(m.estimate.impact).rationale)}</p>{raw(d.decision_id+':impact:'+m.candidate_id,'Recorded assumptions / uncertainty',m.estimate.impact)}</td><td>direct {show(m.estimate.direct)}<br/>information {show(m.estimate.information)}{raw(`${d.decision_id}:${m.candidate_id}`,'Estimated costs / saved factors',m.raw)}</td></tr>)}</tbody></table></div>
    {raw(d.decision_id+':policy','Policy, source hashes, assumptions and abstention',d.raw)}
    <button onClick={()=>void loadCheckpoint(d.decision_id,'pin')}>Pin this Decision Context</button>
  </>;
  const dispatchRow = (d: Dispatch) => <div className="activity" key={d.dispatch_id}><button className="activity-link" aria-pressed={selected?.id===d.dispatch_id} onClick={()=>choose({kind:'dispatch',id:d.dispatch_id})}><span>{d.task_id ? 'Task '+d.task_id : 'No task claimed'}</span><strong>{d.status}</strong><small>{d.reason} · {d.created_at}</small><small>{d.dispatch_id}</small></button>{d.decision_id && <button className="subtle" onClick={()=>void loadCheckpoint(d.decision_id! ,pinned ? 'compare':'pin')}>{pinned?'Compare context':'Pin context'}</button>}</div>;
  return <div className="app">
    <header><div className="brand">ARF <span>/</span> Research Observatory</div><span className="tag">LOCAL · READ ONLY</span></header>
    <section className="study"><div><span className="eyebrow">{source?.studyId ?? 'Existing v4 study'}</span><h1>{source?.meta.question ?? 'Open a saved research record'}</h1><p>Audit a recorded choice, follow its observations, and compare captured inputs.</p></div><div className="source-status"><span className={source?.stale?'dot stale':'dot'}/>{source ? `Generation ${source.meta.generation} · ${source.stale?'stale':'polling every ~3s'}` : 'Source unavailable'}</div></section>
    {(error || source?.reset) && <div className="banner" role="alert"><strong>{source?.reset?'Source reset required':'Read unavailable'}</strong><p>{error}. Previously loaded records are retained; they are not a fresh execution snapshot.</p><button onClick={()=>void boot()}>Recheck source and clear selections</button></div>}
    <div className="mode-bar"><span className="tag">{mode.kind==='live'?'Live · current_execution':'Pinned Decision · snapshot_at_decision'}</span>{pinned&&<><span className="mono">{pinned.decision_id}</span><button onClick={()=>{tickets.current.next('pin');tickets.current.next('compare');setMode({kind:'live'});setPinned(null);setComparison(null);setRefresh(n=>n+1);}}>Return to Live</button><span>{liveChanges} live refreshes during this session</span></>}<span className="loading" role="status">{loading}</span></div>
    <main className="workspace"><aside className="rail"><h2>Recent work</h2><span className="eyebrow">Current execution</span>{work&&<p className="counts">{Object.entries(work.task_counts).map(([k,v])=><span key={k}>{k} <b>{show(v)}</b></span>)}</p>}<nav aria-label="Saved tasks">{work?.tasks.map(t=><button className="task-link" key={t.task_id} aria-pressed={selected?.kind==='task'&&selected.id===t.task_id} onClick={()=>choose({kind:'task',id:t.task_id})}><strong>{t.task_id}</strong><span>{t.status}{t.status==='pending'?(t.blockers.length?' · blocked':' · ready'):''}</span><small>{t.title}</small>{t.blockers.map(b=><small key={String(b.task_id)}>Blocked by {show(b.task_id)}: {show(b.status)}</small>)}</button>)}</nav>{work?.task_next_cursor&&<p className="hint">More tasks exist; this is the first page.</p>}<h2>Actual dispatches</h2><p className="hint">Immutable receipts; “claimed” describes the original claim.</p>{work?.dispatches.map(dispatchRow)}{work?.dispatches.length===0&&<p>No dispatch recorded.</p>}{work?.dispatch_next_cursor&&<p className="hint">More dispatches exist; this is the first page.</p>}{!work&&<p>No current overview available.</p>}</aside>
    <section className="inspector" aria-label="Persistent Inspector" tabIndex={0}>
      <div className="section-head"><div><span className="eyebrow">Persistent Inspector</span><h2>{selected ? `${selected.kind} / ${selected.id}`:'Why was this task chosen?'}</h2></div><span className="tag">source-linked records</span></div>
      {!selected&&<div className="empty"><h3>Start with a task or dispatch</h3><p>Follow its exact candidate version, recorded alternatives, and actual Run / Evidence. Pin a decision to compare saved inputs.</p></div>}
      {mode.kind==='live' && story && <>
        <section className="panel"><h3>Why? trace</h3><div className="trace-chain">{story.task&&<span>Task {story.task.task_id}</span>}{story.dispatch&&<><span>→</span><span>{story.dispatch.status}: {story.dispatch.reason}</span></>}{story.decision&&<><span>→</span><button onClick={()=>choose({kind:'decision',id:story.decision!.decision_id})}>Decision {story.decision.decision_id}</button></>}</div>{story.task&&<p className="hint">current_execution: {story.task.status} · {story.task.blockers.length ? 'dependency blockers recorded':'no dependency blockers'}</p>}{story.missing_relations.map(m=><p className="hint" key={m}>{m}</p>)}{story.decisions.length>1&&<div><p>Select an exact relevant decision:</p>{story.decisions.map(d=><button key={d.id} onClick={()=>choose({kind:'decision',id:d.id})}>{d.id}</button>)}</div>}{story.dispatches.length>1&&<div><p>Multiple receipts / attempts:</p>{story.dispatches.map(d=><button key={d.dispatch_id} onClick={()=>choose({kind:'dispatch',id:d.dispatch_id})}>{d.dispatch_id}</button>)}</div>}</section>
        {story.decision&&<section className="panel">{decisionView(story.decision)}</section>}
        <section className="panel"><h3>Actual Run / Evidence</h3><p className="hint">Current run status and measured costs are separate from saved synthetic predictions.</p>{story.runs.map(r=><div className="record" key={String(r.run_id)}><button onClick={()=>choose({kind:'run',id:String(r.run_id)})}>Run {show(r.run_id)}</button><p>current_execution · {show(r.status)} · observed wall seconds: {show(r.wall_seconds)} · CPU: {show(r.cpu_seconds)}</p>{raw(String(r.run_id),'Observed result / costs / error',r)}</div>)}{story.runs.length===0&&<p>Run: not_recorded</p>}{story.evidence_records.map(e=><div className="record" key={String(e.evidence_id)}><span className="tag">unvalidated Evidence</span><button onClick={()=>choose({kind:'evidence',id:String(e.evidence_id)})}>{show(e.evidence_id)}</button>{raw(String(e.evidence_id),'Original observation and provenance',e)}</div>)}{story.evidence_records.length===0&&<p>Evidence: not_recorded</p>}</section>
        <section className="panel"><h3>Recorded semantic assertions</h3><p className="hint">Unreviewed interpretations, distinct from ATTEMPT_OF / PRODUCES facts. Missing motivation is not inferred from execution.</p>{story.graph_assertions.map(g=><div className="record" key={String(g.id)}><p>{show(g.type)} · {show(g.polarity)} · {show(g.visibility)}</p>{raw(String(g.id),'Exact revision, endpoints and attribution',g)}</div>)}{story.graph_assertions.length===0&&<p>not_recorded</p>}{story.truncated&&<p className="banner">truncated · bounded graph neighborhood; frontier is explicit below.</p>}{raw('trace:'+story.focus.id,'All source links, graph ideas, publications, assessments and continuation',story.raw)}</section>
      </>}
      {mode.kind==='pinned'&&pinned&&<>
        <section className="panel checkpoint"><span className="eyebrow">snapshot_at_decision · original captured input</span><h2>{pinned.decision_id}</h2><p>Saved input to the decision, captured before publication. This does not reconstruct the whole database at claim time.</p><p>Selection {pinned.selection_complete?'complete within scope':'truncated'} · portfolio {pinned.portfolio_completeness} · historical execution: captured execution only.</p>{decisionView(pinned.decision)}{raw('context:'+pinned.context_id,'Exact saved Context: execution, graph revisions, feedback, profile',pinned.context)}</section>
        <section className="panel"><h3>Compare a second saved decision</h3><p>Use a dispatch’s Compare context button, or enter an exact saved decision ID. Failed reads keep these pinned records intact.</p><form onSubmit={e=>{e.preventDefault();void loadCheckpoint(compareId,'compare');}}><label htmlFor="compare-id">Decision ID</label><input id="compare-id" value={compareId} maxLength={4096} onChange={e=>setCompareId(e.target.value)}/><button type="submit">Compare captured input</button></form>{work?.latest_decision_id&&<button className="subtle" onClick={()=>void loadCheckpoint(work.latest_decision_id!,'compare')}>Compare latest saved decision</button>}{comparison&&<Comparison a={pinned} b={comparison} raw={raw}/>}</section>
      </>}
    </section></main><footer>Recorded rationale · synthetic proxy · unknown scientific impact · unvalidated Evidence. Observation never starts research.</footer>
  </div>;
}

function Comparison({a,b,raw}:{a:Checkpoint;b:Checkpoint;raw:(id:string,label:string,value:Json|undefined)=>React.ReactNode}) {
  const diff = compareCheckpoints(a,b);
  return <div className="comparison"><h3>{a.decision_id} ↔ {b.decision_id}</h3><p className="tag">{diff.comparable?'Same declared selection scope':'not_comparable · different scope or incomplete selection'}</p><p className="hint">Membership differences do not prove a change in the research world. Candidates align by stable ID; versions are compared fields. Impact remains unknown / incomparable.</p><div className="table-wrap"><table><caption>Saved membership comparison</caption><thead><tr><th>Candidate</th><th>Pinned</th><th>Comparison</th><th>Recorded difference</th></tr></thead><tbody>{diff.candidates.map(r=><tr key={r.id}><td>{name(r.after??r.before!)}<small>{r.id}</small></td><td>{r.before?`v${r.before.version} / order ${r.before.ordinal} / group ${r.before.priority_group??'unranked'}`:'absent'}</td><td>{r.after?`v${r.after.version} / order ${r.after.ordinal} / group ${r.after.priority_group??'unranked'}`:'absent'}</td><td>{r.changes.join('; ')||'unchanged'}</td></tr>)}</tbody></table></div><h3>Graph ideas by stable ID</h3>{diff.ideas.length===0&&<p>not_recorded in these selected graph projections</p>}{diff.ideas.map(i=><p key={i.id}><span className="mono">{i.id}</span>: {i.status}<small>Exact revisions: {show(i.before)} → {show(i.after)}</small></p>)}{diff.fields.map(f=><div className="record" key={f.label}><strong>{f.label}: {f.changed?'changed':'unchanged'}</strong>{raw('compare:'+b.decision_id+f.label,'Original values',{pinned:f.before,comparison:f.after})}</div>)}{raw('compare-context:'+b.context_id,'Exact comparison Context',b.context)}</div>;
}
