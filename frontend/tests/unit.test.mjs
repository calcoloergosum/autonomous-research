import {test} from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import ts from 'typescript';
const load = async name => import('data:text/javascript;base64,'+Buffer.from(ts.transpileModule(fs.readFileSync(new URL('../src/'+name+'.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.ES2022,target:ts.ScriptTarget.ES2022}}).outputText).toString('base64'));
const api = await load('api');
const audit = await load('audit');
const member = (version=1) => ({candidate_id:'stable-id',version,ordinal:0,priority_group:null,exclusion:'missing_synthetic_proxy',binding:null,estimate:{impact:{status:'unknown',rationale:'saved',assumptions:'fixture',uncertainty:'unknown',alternatives:'other'},costs:{cpu_seconds:null}}});
const decision = {decision_id:'one',context_id:'ctx',members:[member()],policy:{name:'information'},status:'abstain',reason:'no comparable synthetic proxy'};
const checkpoint = id => ({decision_id:id,context_id:'ctx',decision:{...decision,decision_id:id},context:{selection:{roles:[],limits:{nodes:32}},feedback:{branch:'unknown'},profile:{name:'synthetic'},execution:{},execution_sha256:'hash',graph:{graph_seq:1}},capture_semantics:'saved_context_input_not_global_time_travel',historical_execution_state:'captured_execution_only',selection_complete:true,portfolio_completeness:'partial'});
test('strict runtime decoding rejects malformed/missing/unsupported fields',()=>{
  for(const value of [null,[],{}, {api_version:2}, {api_version:1,study_id:'x',temporal_scope:'made_up',data:{}}]) assert.throws(()=>api.envelope(value,api.meta,'epoch'));
  for(const value of [{...decision, members:[{...member(),version:'1'}]}, {...decision,members:[{...member(),priority_group:undefined}]}]) assert.throws(()=>api.decision(value));
  assert.equal(api.decision(decision).members[0].priority_group,null);
  assert.equal(api.decision(decision).members[0].estimate.costs.cpu_seconds,null);
  assert.throws(()=>api.json({x:Infinity}));
  assert.throws(()=>api.checkpoint({...checkpoint('one'),historical_execution_state:'global time travel'}));
});
test('candidate versions align by stable ID; incomparable scopes stay distinct',()=>{
  const a = api.checkpoint(checkpoint('one')), b = api.checkpoint(checkpoint('two'));
  b.decision.members[0].version=2;
  let result=audit.compareCheckpoints(a,b);
  assert.equal(result.candidates.length,1);
  assert.ok(result.candidates[0].changes.includes('new version'));
  b.context.selection={roles:['H']};
  result=audit.compareCheckpoints(a,b); assert.equal(result.comparable,false);
  b.selection_complete=false; assert.equal(audit.compareCheckpoints(a,b).comparable,false);
});
test('out-of-order requests and session resets invalidate old tickets',()=>{
  const t=new audit.Tickets(); const first=t.next('trace');const next=t.next('trace');
  assert.equal(t.current('trace',first),false); assert.equal(t.current('trace',next),true);
  const pin=t.next('pin');t.invalidate();assert.equal(t.current('pin',pin),false);
});
test('fetch boundary rejects malformed JSON, errors, oversized data and epoch drift',async()=>{
  const original=globalThis.fetch;
  try {
    const response=(body,status=200,epoch='one')=>new Response(body,{status,headers:{'X-Observer-Epoch':epoch}});
    globalThis.fetch=async()=>response('{');await assert.rejects(api.request('meta',api.meta),api.DecodeError);
    globalThis.fetch=async()=>response('{}');await assert.rejects(api.request('meta',api.meta,undefined,'two'),/epoch changed/);
    globalThis.fetch=async()=>response(JSON.stringify({error:{code:'temporarily_unavailable',message:'busy'}}),503);await assert.rejects(api.request('meta',api.meta),/busy/);
    globalThis.fetch=async()=>response(' '.repeat(262145));await assert.rejects(api.request('meta',api.meta),/byte budget/);
  } finally {globalThis.fetch=original;}
});
