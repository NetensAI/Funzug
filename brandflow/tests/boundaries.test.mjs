import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import ts from 'typescript';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {mergeOutcomes} from '../lib/funzug-outcomes.mjs';
import * as nativeHelpers from '../lib/funzug-native-handoff.mjs';
const require=createRequire(import.meta.url);
test('middleware routes only the exact native integration path to its bearer-protected handler',async()=>{
 const middleware=load('../middleware.ts',{'next/server':{NextResponse:{next:()=>({allowed:true}),redirect:()=>({allowed:false})}},jose:{jwtVerify:async()=>{throw Error('No session expected');}}},{process:{env:{}}}).middleware;
 for(const [path,allowed] of [['/api/integrations/funzug/native-handoff',true],['/api/integrations/funzug/native-handoff-extra',false],['/social-drafts',false]]){
  const response=await middleware({nextUrl:{pathname:path},url:'https://funzug.netens.top'+path,headers:new Headers(),cookies:{get:()=>undefined}});
  assert.equal(response.allowed,allowed);
 }
});
function nativeRouteFixture({authorized=true,auditFailure=false,draftOverrides={}}={}){
 const calls=[];
 const handoff={state:'reserved',reserved_at:'2000-10-12T14:00:00+05:30',scheduled_at:futureIst,content_hash:'a'.repeat(64),platforms:['facebook','instagram'],receipts:{}};
 const draft={id:'fixture',status:'approved',publication_authorized:true,published_at:null,platform_outcomes:{},schedule_timezone:'Asia/Kolkata',proposed_schedule:futureIst,platforms:handoff.platforms,native_handoff:null,...draftOverrides};
 const handler=load('../app/api/integrations/funzug/native-handoff/route.ts',{
  'next/server':{NextResponse:{json:(body,opts)=>({body,status:opts?.status||200})}},
  '@/lib/funzug-drafts':{validBearer:()=>authorized},'@/lib/funzug-content-hash.mjs':{draftContentHash:()=>handoff.content_hash},'@/lib/funzug-native-handoff.mjs':nativeHelpers,
  '@/lib/db':{db:{connect:async()=>({release(){},query:async(sql,args)=>{calls.push({sql,args});if(sql.startsWith('SELECT'))return {rows:[draft]};if(sql.startsWith('INSERT')&&auditFailure)throw Error('fixture audit failure');return {rows:[]};}})}},
 }).POST;
 return {calls,handoff,send:()=>handler({headers:new Headers(),text:async()=>JSON.stringify({batchId:'fixture',externalId:'fixture',handoff})})};
}
test('native checkpoint authenticates before database access and records state with audit',async()=>{
 const unauthorized=nativeRouteFixture({authorized:false});assert.equal((await unauthorized.send()).status,401);assert.equal(unauthorized.calls.length,0);
 const accepted=nativeRouteFixture();assert.equal((await accepted.send()).status,200);assert.ok(accepted.calls.some(x=>x.sql.startsWith('UPDATE')));assert.ok(accepted.calls.some(x=>x.sql.startsWith('INSERT')));assert.equal(accepted.calls.at(-1).sql,'COMMIT');
});
test('native checkpoint rejects changed slots, revoked approval and outcomes without writes',async()=>{
 for(const draftOverrides of [{publication_authorized:false},{status:'pending_review'},{proposed_schedule:'2099-10-14T19:30:00+05:30'},{platform_outcomes:{instagram:{status:'published'}}}]){
  const fixture=nativeRouteFixture({draftOverrides});assert.equal((await fixture.send()).status,409);assert.ok(!fixture.calls.some(x=>x.sql.startsWith('UPDATE')));assert.equal(fixture.calls.at(-1).sql,'ROLLBACK');
 }
});
test('native checkpoint audit failure rolls back, and replay does not write',async()=>{
 const failed=nativeRouteFixture({auditFailure:true});assert.equal((await failed.send()).status,409);assert.equal(failed.calls.at(-1).sql,'ROLLBACK');assert.ok(!failed.calls.some(x=>x.sql==='COMMIT'));
 const original=nativeRouteFixture();const replay=nativeRouteFixture({draftOverrides:{native_handoff:original.handoff}});assert.equal((await replay.send()).status,200);assert.ok(!replay.calls.some(x=>x.sql.startsWith('UPDATE')||x.sql.startsWith('INSERT')));
});
function reviewFixture({session={sub:'owner',role:'admin'},user={username:'owner',active:true,role:'admin'},origin=true,auditFailure=false,found=true}={}){
 const calls=[];
 const handler=load('../app/api/social-drafts/[id]/review/route.ts',{
  'next/server':{NextResponse:{json:(body,opts)=>({body,status:opts?.status||200})}},
  '@/lib/auth':{getSession:async()=>session},'@/lib/security':{sameOrigin:()=>origin,clientIp:()=>''},
  '@/lib/db':{db:{connect:async()=>({release(){},query:async(sql,args)=>{calls.push({sql,args});if(sql.startsWith('SELECT'))return {rows:user?[user]:[]};if(sql.startsWith('UPDATE'))return {rows:found?[{id:'fixture',brand_id:'brand',status:args[1],proposed_schedule:args[6],schedule_timezone:'Asia/Kolkata'}]:[]};if(sql.startsWith('INSERT')&&auditFailure)throw Error('fixture audit failure');return {rows:[]};}})}},
 }).POST;
 return {calls,send:body=>handler({json:async()=>body},{params:{id:'fixture'}})};
}
const futureIst='2099-10-13T19:30:00+05:30';
test('review rejects invalid origin and missing admin session before database access',async()=>{
 for(const options of [{origin:false},{session:null},{session:{sub:'owner',role:'viewer'}}]){const r=reviewFixture(options);assert.equal((await r.send({action:'reject'})).status,403);assert.equal(r.calls.length,0);}
});
test('review requires one confirmation and a future IST slot without authorization text',async()=>{
 for(const body of [{action:'approve',proposedSchedule:futureIst},{action:'approve',approvalConfirmed:false,proposedSchedule:futureIst},{action:'approve',approvalConfirmed:true,proposedSchedule:'2099-10-13T14:00:00Z'},{action:'approve',approvalConfirmed:true,proposedSchedule:'2000-01-01T19:30:00+05:30'}]){const r=reviewFixture();assert.equal((await r.send(body)).status,400);assert.equal(r.calls.length,0);}
 const r=reviewFixture();assert.equal((await r.send({action:'approve',approvalConfirmed:true,proposedSchedule:futureIst})).status,200);
 const update=r.calls.find(x=>x.sql.startsWith('UPDATE'));assert.equal(update.args[1],'approved');assert.equal(update.args[5],true);assert.equal(JSON.parse(update.args[2]).approvalConfirmed,true);assert.match(update.sql,/status='pending_review'/);assert.equal(r.calls.at(-1).sql,'COMMIT');
});
test('reject does not require a checkbox or schedule and removes publication authorization',async()=>{
 const r=reviewFixture();assert.equal((await r.send({action:'reject'})).status,200);const update=r.calls.find(x=>x.sql.startsWith('UPDATE'));assert.equal(update.args[1],'rejected');assert.equal(update.args[5],false);assert.equal(update.args[6],null);assert.equal(update.args[2],'{}');assert.equal(r.calls.at(-1).sql,'COMMIT');
});
test('review rolls back when admin revoked, already reviewed, or audit insertion fails',async()=>{
 for(const options of [{user:{active:false,role:'admin'}},{found:false},{auditFailure:true}]){const r=reviewFixture(options);assert.ok((await r.send({action:'reject'})).status>=400);assert.equal(r.calls.at(-1).sql,'ROLLBACK');assert.ok(!r.calls.some(x=>x.sql==='COMMIT'));}
});
test('reschedule rejects missing or non-admin sessions before database access',async()=>{
 for(const session of [null,{sub:'fixture',role:'viewer'}]){
  const route=load('../app/api/social-drafts/[id]/reschedule/route.ts',{
   'next/server':{NextResponse:{json:(body,opts)=>({body,status:opts?.status||200})}},
   '@/lib/db':{db:{connect(){throw Error('Unauthorized request reached database');}}},
   '@/lib/auth':{getSession:async()=>session},'@/lib/security':{sameOrigin:()=>true,clientIp:()=>''},
   '@/lib/social-reschedule.mjs':{},'@/lib/funzug-outcomes.mjs':{},
  }).POST;
  assert.equal((await route({},{params:{id:'fixture'}})).status,403);
 }
});
test('reschedule rejects inactive or demoted users before draft lookup',async()=>{
 for(const user of [null,{active:false,role:'admin'},{active:true,role:'viewer'}]){
  const calls=[];
  const route=load('../app/api/social-drafts/[id]/reschedule/route.ts',{
   'next/server':{NextResponse:{json:(body,opts)=>({body,status:opts?.status||200})}},
   '@/lib/db':{db:{connect:async()=>({query:async sql=>{calls.push(sql);if(sql.includes('social_post_drafts'))throw Error('Unauthorized draft lookup');return {rows:user?[user]:[]};},release(){}})}},
   '@/lib/auth':{getSession:async()=>({sub:'fixture',role:'admin'})},'@/lib/security':{sameOrigin:()=>true,clientIp:()=>''},
   '@/lib/social-reschedule.mjs':{validateRescheduleInput:()=>({ok:true})},'@/lib/funzug-outcomes.mjs':{},
  }).POST;
  assert.equal((await route({json:async()=>({})},{params:{id:'fixture'}})).status,403);
  assert.ok(!calls.some(sql=>sql.includes('social_post_drafts')));assert.equal(calls.at(-1),'ROLLBACK');
 }
});
test('draft image verifier accepts native 4:5 and rejects metadata mismatch',()=>{
 const {decodeAndVerifyImage}=load('../lib/funzug-drafts.ts',{});
 const png=(width,height)=>{const bytes=Buffer.alloc(24);Buffer.from([137,80,78,71,13,10,26,10]).copy(bytes);bytes.writeUInt32BE(width,16);bytes.writeUInt32BE(height,20);return bytes.toString('base64');};
 for(const [width,height] of [[1080,1350],[1024,1280],[1200,1500],[1122,1402]])assert.ok(decodeAndVerifyImage(png(width,height),'image/png',width,height));
 assert.throws(()=>decodeAndVerifyImage(png(1123,1402),'image/png'),/4:5/);
 assert.throws(()=>decodeAndVerifyImage(png(1200,1500),'image/png',1080,1350),/metadata/);
});
function load(file, overrides, globals={}){
 const source=fs.readFileSync(new URL(file,import.meta.url),'utf8');
 const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX,esModuleInterop:true,target:ts.ScriptTarget.ES2022}}).outputText;
 const module={exports:{}};
 vm.runInNewContext(compiled,{...globals,module,exports:module.exports,Buffer,console,URL,Date,Map,Object,JSON,require(name){if(name in overrides)return overrides[name];if(name.startsWith('@/')||name.startsWith('next/'))throw Error(`Unmocked production dependency: ${name}`);return require(name);}});
 return module.exports;
}
test('actual reschedule component releases busy state after network and non-JSON errors',async()=>{
 for(const fetch of [async()=>{throw Error('offline')},async()=>({ok:false,json:async()=>{throw Error('HTML response')}})]){
  const states=[true,'2099-10-14T20:30','Owner chooses new slot',true,false,''];let index=0;const changes=[];let refreshed=false;
  const Component=load('../components/SocialDraftReschedule.tsx',{
   react:{...React,useState:()=>{const i=index++;return [states[i],value=>changes.push({i,value})];}},
   'next/navigation':{useRouter:()=>({refresh(){refreshed=true;}})},
  },{fetch}).default;
  const tree=Component({id:'fixture',currentSchedule:'2099-10-13T19:30:00+05:30'});
  function find(node){if(!node||typeof node!=='object')return null;if(node.type==='button'&&node.props.children==='Confirm reschedule')return node;for(const child of [node.props?.children].flat(Infinity)){const found=find(child);if(found)return found;}return null;}
  await find(tree).props.onClick();assert.ok(changes.some(x=>x.i===4&&x.value===false));assert.ok(changes.some(x=>x.i===5&&/check the saved time before retrying/.test(x.value)));assert.equal(refreshed,false);
 }
});
test('actual reschedule success submits the selected IST slot once and refreshes',async()=>{
 const states=[true,'2099-10-14T20:30','Owner changes slot',true,false,''];let index=0,refreshes=0;const changes=[],requests=[];
 const Component=load('../components/SocialDraftReschedule.tsx',{
  react:{...React,useState:()=>{const i=index++;return [states[i],value=>changes.push({i,value})];}},
  'next/navigation':{useRouter:()=>({refresh(){refreshes++;}})},
 },{fetch:async(url,options)=>{requests.push({url,options});return {ok:true};}}).default;
 const tree=Component({id:'fixture',currentSchedule:'2099-10-13T19:30:00+05:30'});
 const buttons=tree.props.children.flat(Infinity).find(x=>x?.props?.className==='row').props.children;
 await buttons[0].props.onClick();assert.equal(requests.length,1);assert.equal(requests[0].url,'/api/social-drafts/fixture/reschedule');
 const body=JSON.parse(requests[0].options.body);assert.equal(body.proposedSchedule,'2099-10-14T20:30:00+05:30');assert.equal(body.scheduleTimezone,'Asia/Kolkata');assert.equal(body.confirmation,'CONFIRM RESCHEDULE');assert.equal(refreshes,1);assert.ok(changes.some(x=>x.i===0&&x.value===false));assert.ok(changes.some(x=>x.i===4&&x.value===false));
});
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
