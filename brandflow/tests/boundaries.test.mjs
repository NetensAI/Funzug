import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {mergeOutcomes} from '../lib/funzug-outcomes.mjs';
const require=createRequire(import.meta.url);
function load(file, overrides){
 const source=fs.readFileSync(new URL(file,import.meta.url),'utf8');
 const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true,target:ts.ScriptTarget.ES2022}}).outputText;
 const module={exports:{}};
 vm.runInNewContext(compiled,{module,exports:module.exports,Buffer,console,URL,Date,Map,Object,JSON,require(name){if(name in overrides)return overrides[name];if(name.startsWith('@/')||name.startsWith('next/'))throw Error(`Unmocked production dependency: ${name}`);return require(name);}});
 return module.exports;
}
const published={status:'published',postId:'fixture-ig',publishedAt:'2026-10-12T11:30:00+05:30'};
const failed={status:'failed',failedAt:'2026-10-12T11:31:00+05:30'};
function fixture(overrides={}){return {id:'fixture-only',status:'approved',publication_authorized:true,platforms:['facebook','instagram'],platform_outcomes:{},published_at:null,...overrides};}
function route(draft, {authorized=true,failAudit=false}={}){
 const calls=[];let released=false;
 const client={async query(sql,args){calls.push({sql,args});if(sql.startsWith('SELECT'))return {rows:draft?[draft]:[]};if(failAudit&&sql.startsWith('INSERT'))throw Error('fixture audit failure');return {rows:[]};},release(){released=true;}};
 const handler=load('../app/api/integrations/funzug/outcomes/route.ts',{
  'next/server':{NextResponse:{json:(body,opts)=>({body,status:opts?.status||200})}},
  '@/lib/db':{db:{async connect(){return client;}}},
  '@/lib/funzug-drafts':{validBearer:()=>authorized},
  '@/lib/funzug-outcomes.mjs':{mergeOutcomes},
 }).POST;
 return {calls,get released(){return released;},send(platformResults){return handler({headers:new Headers(),text:async()=>JSON.stringify({batchId:'fixture-batch',externalId:'fixture-only',platformResults})});}};
}
test('unauthorized result request cannot open a database transaction',async()=>{
 const r=route(fixture(),{authorized:false});assert.equal((await r.send({instagram:published})).status,401);assert.deepEqual(r.calls,[]);
});
test('unapproved result request rolls back without writes',async()=>{
 const r=route(fixture({status:'pending_review',publication_authorized:false}));assert.equal((await r.send({instagram:published})).status,409);assert.equal(r.calls.at(-1).sql,'ROLLBACK');assert.ok(!r.calls.some(c=>/^(UPDATE|INSERT)/.test(c.sql)));assert.ok(r.released);
});
test('partial failure writes outcomes and audit in one transaction without full publication',async()=>{
 const r=route(fixture());const response=await r.send({instagram:published,facebook:failed});assert.equal(response.status,200);assert.equal(response.body.complete,false);
 const update=r.calls.find(c=>c.sql.startsWith('UPDATE'));assert.equal(update.args[2],null);assert.equal(JSON.parse(update.args[1]).instagram.postId,'fixture-ig');assert.ok(r.calls.some(c=>c.sql.startsWith('INSERT INTO audit_logs')));assert.equal(r.calls.at(-1).sql,'COMMIT');assert.ok(r.released);
});
test('idempotent replay avoids writes and conflicting success rolls back',async()=>{
 const r=route(fixture({platform_outcomes:{instagram:published}}));assert.equal((await r.send({instagram:published})).body.unchanged,true);assert.ok(!r.calls.some(c=>/^(UPDATE|INSERT)/.test(c.sql)));
 const conflict=route(fixture({platform_outcomes:{instagram:published}}));assert.equal((await conflict.send({instagram:{...published,postId:'different'}})).status,409);assert.equal(conflict.calls.at(-1).sql,'ROLLBACK');
});
test('audit failure rolls back the result update',async()=>{
 const r=route(fixture(),{failAudit:true});assert.equal((await r.send({instagram:published})).status,500);assert.equal(r.calls.at(-1).sql,'ROLLBACK');assert.ok(!r.calls.some(c=>c.sql==='COMMIT'));assert.ok(r.released);
});
test('actual dashboard renders partial failure, preserves post ID, and hides rescheduling',async()=>{
 const draft={...fixture({platform_outcomes:{instagram:published,facebook:failed}}),batch_id:'fixture',external_id:'fixture-only',headline:'Fixture headline',caption:'Fixture caption',proposed_schedule:'2026-10-13T19:30:00+05:30',claims:[],evidence_sources:[],reviewed_at:'2026-10-12T11:00:00+05:30',reviewer_username:'fixture-owner',reschedule_history:[]};
 const Page=load('../social-drafts-page.tsx',{
  '@/components/AppPage':{__esModule:true,default:({children})=>children()},
  '@/components/SocialDraftReview':{__esModule:true,default:()=>React.createElement('button',null,'Fixture approval control')},
  '@/components/SocialDraftReschedule':{__esModule:true,default:()=>React.createElement('button',null,'Fixture reschedule control')},
  '@/lib/db':{db:{async query(sql){return {rows:sql.startsWith('SELECT * FROM brands')?[{id:'fixture-brand',slug:'funzug',name:'Funzug'}]:[draft]};}}},
  '@/lib/auth':{getSession:async()=>({role:'admin'})},
 }).default;
 const html=renderToStaticMarkup(await Page({searchParams:{brand:'funzug',status:'approved'}}));
 assert.match(html,/instagram: published/);assert.match(html,/facebook: failed/);assert.match(html,/fixture-ig/);assert.match(html,/Successful posts will not be retried automatically/);assert.match(html,/IST/);assert.doesNotMatch(html,/Fixture reschedule control|Fixture approval control/);
});
