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
import {orderedMediaManifest} from '../lib/ordered-media-manifest.mjs';
import {createHash} from 'node:crypto';
import * as hashHelpers from '../lib/funzug-content-hash.mjs';
import * as mixedPolicy from '../lib/mixed-delivery-policy.mjs';
const require=createRequire(import.meta.url);
test('ordered ingestion authenticates and decodes before storage, and rolls back audit failure',async()=>{
 const draft={format:'carousel',media:[]};
 for(const mode of ['unauthorized','decode-failed','audit-failed','valid']){
  const calls=[];
  const POST=load('../app/api/integrations/funzug/drafts/route.ts',{
   'next/server':{NextResponse:{json:(body,options)=>({body,status:options?.status||200})}},
   '@/lib/funzug-content-hash.mjs':{draftContentHash:()=>null},
   '@/lib/funzug-drafts':{validBearer:()=>mode!=='unauthorized',funzugOrderedBatchSchema:{safeParse:()=>({success:true,data:{batchId:'batch',drafts:[draft]}})},funzugBatchSchema:{},decodeAndVerifyImage:()=>{}},
   '@/lib/decode-ordered-media.mjs':{decodeOrderedMedia:async()=>{calls.push('decode');if(mode==='decode-failed')throw Error('private error')}},
   '@/lib/store-ordered-draft.mjs':{storeOrderedDraft:async()=>{calls.push('store');return {id:'fixture',status:'pending_review'}}},
   './outcomes/route':{},'../outcomes/route':{},
   '@/lib/db':{db:{query:async()=>{calls.push('brand');return {rows:[{id:'brand'}]}},connect:async()=>({query:async sql=>{calls.push(sql);if(mode==='audit-failed'&&sql.startsWith('INSERT INTO audit_logs'))throw Error('audit error');return {rows:[]}},release:()=>calls.push('release')})}},
  }).POST;
  const res=await POST({headers:new Headers(),text:async()=>JSON.stringify({schemaVersion:2})});
  if(mode==='unauthorized'){assert.equal(res.status,401);assert.equal(calls.length,0);}
  else if(mode==='decode-failed'){assert.equal(res.status,400);assert.deepEqual(calls,['decode']);assert.doesNotMatch(JSON.stringify(res),/private error/);}
  else if(mode==='audit-failed'){assert.equal(res.status,409);assert.ok(calls.includes('ROLLBACK'));assert.ok(!calls.includes('COMMIT'));}
  else{assert.equal(res.status,202);assert.deepEqual(calls.slice(0,4),['decode','brand','BEGIN','store']);assert.ok(calls.includes('COMMIT'));}
 }
});
test('middleware routes only the exact native integration path to its bearer-protected handler',async()=>{
 const middleware=load('../middleware.ts',{'next/server':{NextResponse:{next:()=>({allowed:true}),redirect:()=>({allowed:false})}},jose:{jwtVerify:async()=>{throw Error('No session expected');}}},{process:{env:{}}}).middleware;
 for(const [path,allowed] of [['/api/integrations/funzug/native-handoff',true],['/api/integrations/funzug/native-package',true],['/api/integrations/funzug/native-package-extra',false],['/api/integrations/funzug/native-handoff-extra',false],['/social-drafts',false]]){
  const response=await middleware({nextUrl:{pathname:path},url:'https://funzug.netens.top'+path,headers:new Headers(),cookies:{get:()=>undefined}});
  assert.equal(response.allowed,allowed);
 }
});
function packageFixture({authorized=true,overrides={},mixedEnabled=false,decodeFails=false}={}){
 const calls=[];
 const row={external_id:'fixture',headline:'Reviewed headline',caption:'Reviewed caption',claims:[],evidence_sources:[],platforms:['facebook','instagram'],image_bytes:Buffer.from('private-reviewed-image'),image_mime_type:'image/png',image_width:1080,image_height:1350,status:'approved',publication_authorized:true,review_checks:{approvalConfirmed:true},reviewed_at:'2026-10-13T10:00:00+05:30',reviewed_by:'owner',proposed_schedule:'2099-10-13T19:30:00+05:30',schedule_timezone:'Asia/Kolkata',native_handoff:null,published_at:null,platform_outcomes:{},...overrides};
 const GET=load('../app/api/integrations/funzug/native-package/route.ts',{
  'next/server':{NextResponse:{json:(body,options)=>({body,status:options?.status||200,headers:options?.headers})}},
  '@/lib/db':{db:{query:async(sql,args)=>{calls.push({sql,args});return {rows:[row]}}}},
  '@/lib/funzug-content-hash.mjs':{draftContentHash:()=> 'a'.repeat(64)},
  '@/lib/ordered-media-manifest.mjs':{orderedMediaManifest},
  '@/lib/decode-ordered-media.mjs':{decodeOrderedMedia:async()=>{if(decodeFails)throw Error('private decode error');return orderedMediaManifest(row,row.private_assets.map(a=>({...a,media_bytes:Buffer.from(a.hex_bytes,'hex')}))).contentHash;}},
  '@/lib/funzug-drafts':{validBearer:()=>authorized,decodeAndVerifyImage:()=>{if(row.image_mime_type!=='image/png')throw Error('bad image')}},
 },{Buffer,process:{env:{FUNZUG_NATIVE_MIXED_ENABLED:mixedEnabled?'1':'0'}}}).GET;
 return {calls,row,send:()=>GET({url:'https://funzug.netens.top/api/integrations/funzug/native-package?batchId=fixture&externalId=fixture',headers:new Headers()})};
}

test('mixed native packages remain gated and bind approved ordered bytes',async()=>{
 const private_assets=['first','second'].map((data,index)=>({draft_id:'parent',media_index:index,mime_type:'image/png',width:40,height:50,duration_ms:null,sha256:createHash('sha256').update(data).digest('hex'),hex_bytes:Buffer.from(data).toString('hex')}));
 const overrides={id:'parent',media_format:'carousel',private_assets};
 assert.equal((await packageFixture({overrides}).send()).status,409);
 const good=await packageFixture({overrides,mixedEnabled:true}).send();
 assert.equal(good.status,200);assert.equal(good.body.format,'carousel');assert.equal(good.body.media.length,2);
 assert.equal(Buffer.from(good.body.media[0].data,'base64').toString(),'first');
 assert.equal(good.headers['Cache-Control'],'no-store');assert.ok(!('image' in good.body));
 for(const changes of [{status:'pending_review'},{publication_authorized:false},{published_at:'2026-10-13'},{private_assets:private_assets.toReversed()},{native_handoff:{content_hash:'wrong'}}])assert.equal((await packageFixture({overrides:{...overrides,...changes},mixedEnabled:true}).send()).status,409);
 const failed=await packageFixture({overrides,mixedEnabled:true,decodeFails:true}).send();assert.equal(failed.status,409);assert.doesNotMatch(JSON.stringify(failed),/private decode error/);
});

test('ordered private previews require current administrator access before returning media',async()=>{
 const id='11111111-1111-4111-8111-111111111111';
 const make=(session,row)=>{
  const calls=[];
  const GET=load('../app/api/social-drafts/[id]/media/[index]/route.ts',{
   'next/server':{NextResponse:class{constructor(body,options){this.body=body;Object.assign(this,options)}static json(body,options){return {body,status:options?.status||200}}}},
   '@/lib/auth':{getSession:async()=>session},
   '@/lib/db':{db:{query:async(sql,args)=>{calls.push({sql,args});return {rows:row?[row]:[]}}}},
   '@/lib/private-media-response.mjs':{privateMediaResponse:()=>({body:Buffer.from('private'),status:200,headers:{'Cache-Control':'private, no-store'}})},
   '@/lib/image-preview.mjs':{},
  }).GET;
  return {calls,send:(params={id,index:'0'})=>GET({url:'https://review.example/api/media',headers:new Headers()}, {params})};
 };
 for(const session of [null,{sub:'owner',role:'viewer'}]){const f=make(session,{});assert.equal((await f.send()).status,403);assert.equal(f.calls.length,0);}
 const f=make({sub:'owner',role:'admin'},{});assert.equal((await f.send()).status,200);assert.match(f.calls[0].sql,/u.active=true AND u.role='admin'/);assert.match(f.calls[0].sql,/b.slug='funzug'/);assert.equal(f.calls[0].args[1],0);
 const invalid=make({sub:'owner',role:'admin'},{});assert.equal((await invalid.send({id,index:'10'})).status,400);assert.equal(invalid.calls.length,0);
 const revoked=make({sub:'owner',role:'admin'},null);assert.equal((await revoked.send()).status,404);
});
test('native media package authenticates before any lookup and returns only reviewed content',async()=>{
 const denied=packageFixture({authorized:false});assert.equal((await denied.send()).status,401);assert.equal(denied.calls.length,0);
 const fixture=packageFixture();const response=await fixture.send();assert.equal(response.status,200);assert.equal(response.headers['Cache-Control'],'no-store');assert.equal(response.body.caption,fixture.row.caption);assert.equal(Buffer.from(response.body.image.data,'base64').toString(),'private-reviewed-image');assert.match(fixture.calls[0].sql,/b.slug='funzug'/);assert.equal(JSON.stringify(fixture.calls[0].args),JSON.stringify(['fixture','fixture']));assert.equal(fixture.calls.length,1);
});
test('native media package denies pending, revoked, published, partial and changed approvals',async()=>{
 for(const overrides of [{media_format:'carousel'},{media_format:'reel'},{status:'pending_review'},{publication_authorized:false},{review_checks:{}},{reviewed_by:null},{published_at:'2026-10-13'},{platform_outcomes:{facebook:{status:'published'}}},{schedule_timezone:'UTC'},{platforms:['facebook','facebook']},{platforms:['other']},{native_handoff:{content_hash:'b'.repeat(64)}},{image_mime_type:'text/plain'}]){
  const response=await packageFixture({overrides}).send();assert.equal(response.status,409,JSON.stringify(overrides));assert.equal(response.body.image,undefined);
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
function reviewFixture({session={sub:'owner',role:'admin'},user={username:'owner',active:true,role:'admin'},origin=true,auditFailure=false,found=true,currentHash='a'.repeat(64)}={}){
 const calls=[];
 const handler=load('../app/api/social-drafts/[id]/review/route.ts',{
  'next/server':{NextResponse:{json:(body,opts)=>({body,status:opts?.status||200})}},
  '@/lib/auth':{getSession:async()=>session},'@/lib/security':{sameOrigin:()=>origin,clientIp:()=>''},
  '@/lib/funzug-content-hash.mjs':{draftContentHash:()=>currentHash},
  '@/lib/db':{db:{connect:async()=>({release(){},query:async(sql,args)=>{calls.push({sql,args});if(sql.startsWith('SELECT'))return {rows:user?[user]:[]};if(sql.startsWith('UPDATE'))return {rows:found?[{id:'fixture',brand_id:'brand',status:args[1],proposed_schedule:args[6],schedule_timezone:'Asia/Kolkata'}]:[]};if(sql.startsWith('INSERT')&&auditFailure)throw Error('fixture audit failure');return {rows:[]};}})}},
 }).POST;
 return {calls,send:body=>handler({json:async()=>body},{params:{id:'fixture'}})};
}
const futureIst='2099-10-13T19:30:00+05:30';
test('approval rejects content changed after the review screen loaded',async()=>{
 const r=reviewFixture({currentHash:'b'.repeat(64)});
 const result=await r.send({action:'approve',approvalConfirmed:true,proposedSchedule:futureIst,reviewedContentHash:'a'.repeat(64)});
 assert.equal(result.status,409);assert.match(result.body.error,/changed since review/);
 assert.ok(r.calls.some(x=>x.sql.includes('FOR UPDATE')));
 assert.ok(!r.calls.some(x=>x.sql.startsWith('UPDATE')||x.sql.startsWith('INSERT')));
 assert.equal(r.calls.at(-1).sql,'ROLLBACK');
});
test('review rejects invalid origin and missing admin session before database access',async()=>{
 for(const options of [{origin:false},{session:null},{session:{sub:'owner',role:'viewer'}}]){const r=reviewFixture(options);assert.equal((await r.send({action:'reject'})).status,403);assert.equal(r.calls.length,0);}
});
test('review requires one confirmation and a future IST slot without authorization text',async()=>{
 for(const body of [{action:'approve',proposedSchedule:futureIst},{action:'approve',approvalConfirmed:false,proposedSchedule:futureIst},{action:'approve',approvalConfirmed:true,proposedSchedule:'2099-10-13T14:00:00Z'},{action:'approve',approvalConfirmed:true,proposedSchedule:'2000-01-01T19:30:00+05:30'}]){const r=reviewFixture();assert.equal((await r.send(body)).status,400);assert.equal(r.calls.length,0);}
 const r=reviewFixture();assert.equal((await r.send({action:'approve',approvalConfirmed:true,proposedSchedule:futureIst,reviewedContentHash:'a'.repeat(64)})).status,200);
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
 vm.runInNewContext(compiled,{process:{env:{}},...globals,module,exports:module.exports,Buffer,console,URL,Date,Map,Object,JSON,require(name){if(name in overrides)return overrides[name];if(name==='@/lib/mixed-delivery-policy.mjs')return mixedPolicy;if(name.startsWith('@/')||name.startsWith('next/'))throw Error(`Unmocked production dependency: ${name}`);return require(name);}});
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
  '@/lib/funzug-content-hash.mjs':hashHelpers,
  '@/components/SocialDraftReschedule':{__esModule:true,default:()=>React.createElement('button',null,'Fixture reschedule control')},
  '@/components/SocialDraftMedia':load('../components/SocialDraftMedia.tsx',{}, {React}),
  '@/lib/db':{db:{async query(sql){return {rows:sql.startsWith('SELECT * FROM brands')?[{id:'fixture-brand',slug:'funzug',name:'Funzug'}]:[draft]};}}},
  '@/lib/auth':{getSession:async()=>({role:'admin'})},
 }).default;
 const html=renderToStaticMarkup(await Page({searchParams:{brand:'funzug',status:'approved'}}));
 assert.match(html,/instagram: published/);assert.match(html,/facebook: failed/);assert.match(html,/fixture-ig/);assert.match(html,/Successful posts will not be retried automatically/);assert.match(html,/IST/);assert.doesNotMatch(html,/Fixture reschedule control|Fixture approval control/);
});
