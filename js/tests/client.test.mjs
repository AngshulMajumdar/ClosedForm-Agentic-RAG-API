import test from 'node:test';
import assert from 'node:assert/strict';
import { APIError, ClosedFormRAGClient } from '../src/client.js';

function json(data, status=200, headers={}) {
  return new Response(JSON.stringify(data), { status, headers: { 'content-type':'application/json', ...headers } });
}

test('routes with exact existing v1 payload and bearer auth', async () => {
  const calls = [];
  const api = new ClosedFormRAGClient({ apiToken:'secret', fetchImpl: async (url,opts) => {
    calls.push({url,opts}); return json({selected:'strong',decision_llm_calls:0,candidates:[],rejected:[]});
  }});
  const r=await api.route([{id:'strong',predicted_accuracy:0.9,expected_cost_usd:0.01,latency_p95_ms:1000,llm_calls:1}],{max_llm_calls:1});
  assert.equal(r.selected, 'strong');
  assert.equal(calls[0].url,'https://angshul-closedform-agentic-rag.hf.space/v1/route');
  assert.equal(calls[0].opts.headers.Authorization, 'Bearer secret');
  assert.equal(JSON.parse(calls[0].opts.body).budgets.max_llm_calls,1);
});

test('answer includes question and does not retry HTTP 503 by default',async()=>{
  let count=0;
  const api=new ClosedFormRAGClient({apiToken:'secret',fetchImpl: async()=>{count++;return json({detail:'Not configured'},503);}});
  await assert.rejects(()=>api.answer('Q?'),e=>e instanceof APIError&&e.status===503);
  assert.equal(count,1);
});

test('route retries 429 once and succeeds',async()=>{
  let count=0;
  const api=new ClosedFormRAGClient({apiToken:'secret',backoffMs:0,fetchImpl:async()=>{
    count++;return count===1?json({detail:'Busy'},429,{'retry-after':'0'}):json({selected:'fast',decision_llm_calls:0});
  }});
  const r=await api.route([{id:'fast'}]);
  assert.equal(r.selected,'fast');assert.equal(count,2);
});

test('bounded batch preserves input order',async()=>{
  let active=0,maxActive=0;
  const api=new ClosedFormRAGClient({apiToken:'secret',fetchImpl:async(_url,opts)=>{
    active++;maxActive=Math.max(maxActive,active);
    const question=JSON.parse(opts.body).question;
    await new Promise(r=>setTimeout(r,4));active--;
    return json({answer:question});
  }});
  const answers=await api.batchAnswers(['a','b','c','d','e'],undefined,{concurrency:2});
  assert.deepEqual(answers.map(x=>x.answer),['a','b','c','d','e']);
  assert.ok(maxActive<=2);
});

test('requires HTTPS outside localhost',()=>{
  assert.throws(()=>new ClosedFormRAGClient({apiToken:'secret',baseUrl:'http://example.com'}),/HTTPS/);
});

test('failed batch completes already-started calls before throwing',async()=>{
  let active=0;
  const api=new ClosedFormRAGClient({apiToken:'secret',fetchImpl:async(_url,opts)=>{
    active++;
    const q=JSON.parse(opts.body).question;
    await new Promise(resolve=>setTimeout(resolve,4));
    active--;
    return q==='a' ? json({detail:'Failed'},503) : json({answer:q});
  }});
  await assert.rejects(()=>api.batchAnswers(['a','b','c'],undefined,{concurrency:2}),e=>e instanceof APIError&&e.status===503);
  assert.equal(active,0);
});
