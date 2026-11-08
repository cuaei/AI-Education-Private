import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import {webcrypto} from 'node:crypto';
import ts from 'typescript';

const uuidV4=/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

function httpClient(fetch=async()=>({ok:true,json:async()=>({})})){
 const events=[];
 const context=vm.createContext({
  exports:{},crypto:{getRandomValues:webcrypto.getRandomValues.bind(webcrypto)},
  window:{dispatchEvent:event=>events.push(event)},
  CustomEvent:class{constructor(type,{detail}){this.type=type;this.detail=detail}},
  AbortController,FormData,setTimeout,clearTimeout,fetch,
 });
 const source=readFileSync(new URL('../src/api.ts',import.meta.url),'utf8');
 vm.runInContext(ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,context);
 return {client:context.exports,events};
}

test('HTTP operation tracking and notifications work without randomUUID',()=>{
 const {client,events}=httpClient();
 const finish=client.trackOperation('正在提交');
 const operation=client.pendingOperations()[0];
 assert.match(operation.id,uuidV4);
 finish();
 assert.equal(client.pendingOperations().length,0);
 client.notifyUser('请填写答案');
 assert.match(events.at(-1).detail.id,uuidV4);
 assert.equal(events.at(-1).detail.message,'请填写答案');
});

test('HTTP POST retries preserve the idempotency key and deliver grading feedback',async()=>{
 const requests=[];
 const {client,events}=httpClient(async(url,options)=>{
  requests.push({url,options});
  if(requests.length===1)throw new TypeError('network interrupted');
  return {ok:true,json:async()=>({grades:{groups:{score:0,max_score:10,checks:[]}}})};
 });
 await client.api('/submit/groups',{answer:'example'});
 assert.equal(requests.length,2);
 const key=requests[0].options.headers['Idempotency-Key'];
 assert.match(key,uuidV4);
 assert.equal(requests[1].options.headers['Idempotency-Key'],key);
 assert.match(events.find(e=>e.type==='training-feedback').detail.id,uuidV4);
 assert.equal(client.pendingOperations().length,0);
});

test('generated practice attempt IDs retain UUID v4 format and uniqueness',()=>{
 const {client}=httpClient();
 assert.equal(typeof client.createId,'function');
 const ids=Array.from({length:1000},()=>client.createId());
 for(const id of ids)assert.match(id,uuidV4);
 assert.equal(new Set(ids).size,ids.length);
});
