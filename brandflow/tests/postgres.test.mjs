import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {randomUUID} from 'node:crypto';
import pg from 'pg';
import ts from 'typescript';
import {mergeOutcomes,canRescheduleOutcomes} from '../lib/funzug-outcomes.mjs';
import * as rescheduleHelpers from '../lib/social-reschedule.mjs';
import * as nativeHelpers from '../lib/funzug-native-handoff.mjs';
import {draftContentHash} from '../lib/funzug-content-hash.mjs';
import * as mixedPolicy from '../lib/mixed-delivery-policy.mjs';

const require=createRequire(import.meta.url);
const url=process.env.FUNZUG_TEST_DATABASE_URL;
if(process.env.FUNZUG_REQUIRE_DATABASE_TESTS==='1'&&!url)throw Error('Disposable PostgreSQL test URL is required');

test('actual outcome handler against disposable PostgreSQL', {skip:!url}, async t=>{
 const parsed=new URL(url);
 assert.ok(['localhost','127.0.0.1','[::1]'].includes(parsed.hostname),'Only a local disposable database is permitted');
 assert.equal(parsed.pathname,'/funzug_test','Never run against the production database');
 const schema='funzug_test_'+randomUUID().replaceAll('-','');
 const admin=new pg.Pool({connectionString:url});
 const pool=new pg.Pool({connectionString:url,options:`-c search_path=${schema} -c statement_timeout=5000`,max:4});
 try{
  await admin.query(`CREATE SCHEMA ${schema}`);
  await pool.query(`CREATE TABLE brands(id text PRIMARY KEY,slug text NOT NULL);
   INSERT INTO brands VALUES('brand','funzug');
   CREATE TABLE social_post_drafts(id text PRIMARY KEY,brand_id text REFERENCES brands(id),batch_id text,external_id text,status text,publication_authorized boolean,platforms jsonb,platform_outcomes jsonb NOT NULL DEFAULT '{}',published_at timestamptz,updated_at timestamptz,
    image_width integer NOT NULL DEFAULT 1080 CONSTRAINT social_post_drafts_image_width_check CHECK(image_width=1080),
    image_height integer NOT NULL DEFAULT 1350 CONSTRAINT social_post_drafts_image_height_check CHECK(image_height=1350));
   CREATE TABLE audit_logs(action text,target_type text,target_id text,details jsonb,actor_user_id text,actor_username text,ip_address text);
   CREATE TABLE users(id text PRIMARY KEY,username text,active boolean,role text);
   INSERT INTO users VALUES('owner','owner',true,'admin'),('other','other',true,'admin');
   ALTER TABLE social_post_drafts ADD COLUMN proposed_schedule timestamptz, ADD COLUMN schedule_timezone text,
    ADD COLUMN review_checks jsonb, ADD COLUMN review_note text, ADD COLUMN reviewed_by text, ADD COLUMN reviewed_at timestamptz,
    ADD COLUMN headline text, ADD COLUMN caption text, ADD COLUMN claims jsonb, ADD COLUMN evidence_sources jsonb, ADD COLUMN image_bytes bytea, ADD COLUMN image_mime_type text,
    ADD COLUMN media_format text NOT NULL DEFAULT 'image';
   CREATE TABLE social_post_reschedules(draft_id text,old_proposed_schedule timestamptz,old_schedule_timezone text,new_proposed_schedule timestamptz,new_schedule_timezone text,previous_reviewed_by text,previous_reviewed_at timestamptz,previous_review_note text,rescheduled_by text,rescheduled_at timestamptz,reschedule_note text);`);  await pool.query(fs.readFileSync(new URL('../db/migrations/012_funzug_native_handoff.sql',import.meta.url),'utf8'));
  await pool.query(`CREATE TABLE social_post_media_assets(
   draft_id text NOT NULL REFERENCES social_post_drafts(id),media_index integer NOT NULL,mime_type text NOT NULL,
   width integer NOT NULL,height integer NOT NULL,duration_ms integer,sha256 text NOT NULL,
   PRIMARY KEY(draft_id,media_index));`);
  const compiled=ts.transpileModule(fs.readFileSync(new URL('../app/api/integrations/funzug/outcomes/route.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const module={exports:{}};
  const adapters={
   'next/server':{NextResponse:{json:(body,opts)=>({body,status:opts?.status||200})}},
   '@/lib/db':{db:pool},'@/lib/funzug-drafts':{validBearer:()=>true},'@/lib/funzug-outcomes.mjs':{mergeOutcomes},
  };
  vm.runInNewContext(compiled,{module,exports:module.exports,Buffer,JSON,require(name){if(name in adapters)return adapters[name];if(name.startsWith('@/')||name.startsWith('next/'))throw Error('Unexpected app dependency');return require(name);}});
  const send=platformResults=>module.exports.POST({headers:new Headers(),text:async()=>JSON.stringify({batchId:'fixture',externalId:'fixture',platformResults})});
  const reset=async(status='approved',authorized=true)=>{
   await pool.query('TRUNCATE audit_logs,social_post_media_assets,social_post_drafts');
   await pool.query("INSERT INTO social_post_drafts(id,brand_id,batch_id,external_id,status,publication_authorized,platforms) VALUES('draft','brand','fixture','fixture',$1,$2,'[\"facebook\",\"instagram\"]')",[status,authorized]);
   await pool.query("UPDATE social_post_drafts SET headline='Reviewed',caption='Reviewed',claims='[]',evidence_sources='[]',image_bytes=$1,image_mime_type='image/png'",[Buffer.from('fixture')]);
  };
  const row=async()=>(await pool.query('SELECT platform_outcomes,published_at FROM social_post_drafts')).rows[0];
  const success=id=>({status:'published',postId:id,publishedAt:'2026-10-12T12:30:00+05:30'});
  const reviewCompiled=ts.transpileModule(fs.readFileSync(new URL('../app/api/social-drafts/[id]/review/route.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  function reviewHandler(userId='owner'){
   const target={exports:{}};
   const reviewAdapters={...adapters,'@/lib/mixed-delivery-policy.mjs':mixedPolicy,'@/lib/funzug-content-hash.mjs':{draftContentHash},'@/lib/auth':{getSession:async()=>({sub:userId,role:'admin'})},'@/lib/security':{sameOrigin:()=>true,clientIp:()=>''}};
   vm.runInNewContext(reviewCompiled,{process:{env:{}},module:target,exports:target.exports,Date,Intl,JSON,require(name){if(name in reviewAdapters)return reviewAdapters[name];if(name.startsWith('@/')||name.startsWith('next/'))throw Error('Unexpected review dependency');return require(name);}});
   return body=>target.exports.POST({json:async()=>body},{params:{id:'draft'}});
  }
  const approve={action:'approve',approvalConfirmed:true,proposedSchedule:'2099-10-13T19:30:00+05:30',reviewedContentHash:draftContentHash({headline:'Reviewed',caption:'Reviewed',claims:[],evidence_sources:[],platforms:['facebook','instagram'],image_bytes:Buffer.from('fixture'),image_mime_type:'image/png'})};
  const reviewRow=async()=>(await pool.query('SELECT status,publication_authorized,proposed_schedule,schedule_timezone,review_checks,reviewed_by FROM social_post_drafts')).rows[0];
  await t.test('single-confirmation approval persists IST slot and authorization with audit',async()=>{
   await reset('pending_review',false);assert.equal((await reviewHandler()(approve)).status,200);
   const saved=await reviewRow();assert.equal(saved.status,'approved');assert.equal(saved.publication_authorized,true);assert.equal(saved.schedule_timezone,'Asia/Kolkata');assert.equal(saved.proposed_schedule.toISOString(),'2099-10-13T14:00:00.000Z');assert.deepEqual(saved.review_checks,{approvalConfirmed:true});assert.equal(saved.reviewed_by,'owner');
   assert.equal((await pool.query('SELECT action FROM audit_logs')).rows[0].action,'social_draft.approved');
  });
  await t.test('rejection persists without granting publication authorization',async()=>{
   await reset('pending_review',false);assert.equal((await reviewHandler()({action:'reject'})).status,200);
   const saved=await reviewRow();assert.equal(saved.status,'rejected');assert.equal(saved.publication_authorized,false);assert.deepEqual(saved.review_checks,{});assert.equal(saved.proposed_schedule,null);
  });
  await t.test('competing administrators can review a pending draft only once',async()=>{
   await reset('pending_review',false);
   const results=await Promise.all([reviewHandler('owner')(approve),reviewHandler('other')({action:'reject'})]);assert.deepEqual(results.map(x=>x.status).sort(),[200,409]);
   const saved=await reviewRow();assert.equal(saved.publication_authorized,saved.status==='approved');assert.equal((await pool.query('SELECT count(*)::int AS n FROM audit_logs')).rows[0].n,1);
  });
  await t.test('approval audit failure leaves draft pending and unauthorized',async()=>{
   await reset('pending_review',false);await pool.query("ALTER TABLE audit_logs ADD CONSTRAINT reject_review CHECK(action <> 'social_draft.approved')");
   try{assert.equal((await reviewHandler()(approve)).status,409);const saved=await reviewRow();assert.equal(saved.status,'pending_review');assert.equal(saved.publication_authorized,false);assert.equal(saved.reviewed_by,null);assert.equal(saved.proposed_schedule,null);}
   finally{await pool.query('ALTER TABLE audit_logs DROP CONSTRAINT reject_review');}
  });
  const rescheduleCompiled=ts.transpileModule(fs.readFileSync(new URL('../app/api/social-drafts/[id]/reschedule/route.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const rescheduleModule={exports:{}};
  const rescheduleAdapters={...adapters,'@/lib/auth':{getSession:async()=>({sub:'owner',role:'admin'})},'@/lib/security':{sameOrigin:()=>true,clientIp:()=>''},'@/lib/social-reschedule.mjs':rescheduleHelpers,'@/lib/funzug-outcomes.mjs':{canRescheduleOutcomes}};
  vm.runInNewContext(rescheduleCompiled,{module:rescheduleModule,exports:rescheduleModule.exports,Date,JSON,require(name){if(name in rescheduleAdapters)return rescheduleAdapters[name];throw Error('Unexpected reschedule dependency');}});
  const reschedule=()=>rescheduleModule.exports.POST({json:async()=>({action:'reschedule',confirmation:'CONFIRM RESCHEDULE',scheduleTimezone:'Asia/Kolkata',proposedSchedule:'2099-10-14T20:30:00+05:30',note:'Owner changes the approved slot'})},{params:{id:'draft'}});
  const prepareReschedule=async()=>{await reset('pending_review',false);await pool.query('TRUNCATE social_post_reschedules');await reviewHandler()(approve);};
  const nativeCompiled=ts.transpileModule(fs.readFileSync(new URL('../app/api/integrations/funzug/native-handoff/route.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const nativeModule={exports:{}};
  const nativeAdapters={...adapters,'@/lib/funzug-content-hash.mjs':{draftContentHash},'@/lib/funzug-native-handoff.mjs':nativeHelpers};
  vm.runInNewContext(nativeCompiled,{module:nativeModule,exports:nativeModule.exports,Buffer,JSON,Date,require(name){if(name in nativeAdapters)return nativeAdapters[name];if(name.startsWith('@/')||name.startsWith('next/'))throw Error('Unexpected native dependency');return require(name);}});
  const nativeSend=handoff=>nativeModule.exports.POST({headers:new Headers(),text:async()=>JSON.stringify({batchId:'fixture',externalId:'fixture',handoff})});
  const prepareNative=async()=>{
   await prepareReschedule();
   await pool.query("UPDATE social_post_drafts SET headline='Fixture',caption='Fixture caption',claims='[]',evidence_sources='[]',image_bytes=$1,image_mime_type='image/png'",[Buffer.from('fixture-image')]);
   const draft=(await pool.query('SELECT * FROM social_post_drafts')).rows[0];
   return {state:'reserved',reserved_at:'2000-10-12T14:00:00+05:30',scheduled_at:approve.proposedSchedule,content_hash:draftContentHash(draft),platforms:['facebook','instagram'],receipts:{}};
  };
  await t.test('native checkpoint persists with audit and JSONB replay is idempotent',async()=>{
   const handoff=await prepareNative();assert.equal((await nativeSend(handoff)).status,200);
   const saved=(await pool.query('SELECT native_handoff FROM social_post_drafts')).rows[0].native_handoff;assert.deepEqual(saved,handoff);
   const before=(await pool.query('SELECT count(*)::int AS n FROM audit_logs')).rows[0].n;
   assert.equal((await nativeSend(handoff)).status,200);assert.equal((await pool.query('SELECT count(*)::int AS n FROM audit_logs')).rows[0].n,before);
  });
  await t.test('native audit failure rolls back checkpoint',async()=>{
   const handoff=await prepareNative();await pool.query("ALTER TABLE audit_logs ADD CONSTRAINT reject_native CHECK(action <> 'social_draft.native_handoff')");
   try{assert.equal((await nativeSend(handoff)).status,409);assert.equal((await pool.query('SELECT native_handoff FROM social_post_drafts')).rows[0].native_handoff,null);}
   finally{await pool.query('ALTER TABLE audit_logs DROP CONSTRAINT reject_native');}
  });
  await t.test('competing native reservation and owner reschedule cannot both succeed',async()=>{
   const handoff=await prepareNative();const results=await Promise.all([nativeSend(handoff),reschedule()]);assert.deepEqual(results.map(x=>x.status).sort(),[200,409]);
   const draft=(await pool.query('SELECT native_handoff,proposed_schedule FROM social_post_drafts')).rows[0];
   if(draft.native_handoff)assert.equal(draft.proposed_schedule.toISOString(),'2099-10-13T14:00:00.000Z');
   else assert.equal(draft.proposed_schedule.toISOString(),'2099-10-14T15:00:00.000Z');
  });
  await t.test('native handoff prevents workflow rescheduling and history writes',async()=>{
   await prepareReschedule();await pool.query("UPDATE social_post_drafts SET native_handoff='{}'::jsonb");
   assert.equal((await reschedule()).status,409);
   assert.equal((await reviewRow()).proposed_schedule.toISOString(),'2099-10-13T14:00:00.000Z');
   assert.equal((await pool.query('SELECT count(*)::int AS n FROM social_post_reschedules')).rows[0].n,0);
  });
  await t.test('reschedule preserves approval and records old and new IST slots',async()=>{
   await prepareReschedule();assert.equal((await reschedule()).status,200);const saved=await reviewRow();assert.equal(saved.status,'approved');assert.equal(saved.publication_authorized,true);assert.equal(saved.proposed_schedule.toISOString(),'2099-10-14T15:00:00.000Z');
   const history=(await pool.query('SELECT * FROM social_post_reschedules')).rows[0];assert.equal(history.old_proposed_schedule.toISOString(),'2099-10-13T14:00:00.000Z');assert.equal(history.new_schedule_timezone,'Asia/Kolkata');assert.equal(history.rescheduled_by,'owner');
  });
  await t.test('any recorded platform outcome prevents rescheduling and history writes',async()=>{
   for(const outcomes of [{instagram:success('already-posted')},{facebook:{status:'failed',failedAt:'2026-10-12T12:30:00+05:30'}}]){
    await prepareReschedule();await pool.query('UPDATE social_post_drafts SET platform_outcomes=$1',[JSON.stringify(outcomes)]);assert.equal((await reschedule()).status,409);assert.equal((await reviewRow()).proposed_schedule.toISOString(),'2099-10-13T14:00:00.000Z');assert.equal((await pool.query('SELECT count(*)::int AS n FROM social_post_reschedules')).rows[0].n,0);
   }
  });
  await t.test('reschedule audit failure rolls back both slot and history insertion',async()=>{
   await prepareReschedule();await pool.query("ALTER TABLE audit_logs ADD CONSTRAINT reject_reschedule CHECK(action <> 'social_draft.rescheduled')");
   try{assert.equal((await reschedule()).status,409);assert.equal((await reviewRow()).proposed_schedule.toISOString(),'2099-10-13T14:00:00.000Z');assert.equal((await pool.query('SELECT count(*)::int AS n FROM social_post_reschedules')).rows[0].n,0);}
   finally{await pool.query('ALTER TABLE audit_logs DROP CONSTRAINT reject_reschedule');}
  });
  await t.test('concurrent independent platforms retain both results and complete once',async()=>{
   await reset();
   const results=await Promise.all([send({facebook:success('fb')}),send({instagram:success('ig')})]);
   assert.deepEqual(results.map(x=>x.status),[200,200]);
   const saved=await row();assert.equal(saved.platform_outcomes.facebook.postId,'fb');assert.equal(saved.platform_outcomes.instagram.postId,'ig');assert.ok(saved.published_at);
   assert.equal((await pool.query('SELECT count(*)::int AS n FROM audit_logs')).rows[0].n,2);
  });
  await t.test('concurrent conflicting successes cannot overwrite a published ID',async()=>{
   await reset();const results=await Promise.all([send({instagram:success('first')}),send({instagram:success('second')})]);
   assert.deepEqual(results.map(x=>x.status).sort(),[200,409]);
   assert.ok(['first','second'].includes((await row()).platform_outcomes.instagram.postId));
   assert.equal((await pool.query('SELECT count(*)::int AS n FROM audit_logs')).rows[0].n,1);
  });
  await t.test('audit insertion failure rolls back the preceding draft update',async()=>{
   await reset();await pool.query("ALTER TABLE audit_logs ADD CONSTRAINT reject_fixture CHECK(action <> 'social_draft.platform_outcomes')");
   try{assert.equal((await send({instagram:success('rollback')})).status,500);assert.deepEqual((await row()).platform_outcomes,{});assert.equal((await row()).published_at,null);}
   finally{await pool.query('ALTER TABLE audit_logs DROP CONSTRAINT reject_fixture');}
  });
  await t.test('pending and unauthorized drafts cannot receive publication results',async()=>{
   for(const [status,authorized] of [['pending_review',false],['approved',false]]){
    await reset(status,authorized);assert.equal((await send({instagram:success('forbidden')})).status,409);assert.deepEqual((await row()).platform_outcomes,{});
   }
  });
  await t.test('native ratio migration preserves rows and enforces 4:5 in PostgreSQL',async()=>{
   await reset();await pool.query(fs.readFileSync(new URL('../db/migrations/010_funzug_native_portrait_ratio.sql',import.meta.url),'utf8'));
   assert.equal((await pool.query('SELECT image_width FROM social_post_drafts')).rows[0].image_width,1080);
   await pool.query('UPDATE social_post_drafts SET image_width=1200,image_height=1500');
   await assert.rejects(pool.query('UPDATE social_post_drafts SET image_width=1122,image_height=1402'),e=>e.code==='23514');
   assert.equal((await pool.query('SELECT image_width FROM social_post_drafts')).rows[0].image_width,1200);
   await pool.query(fs.readFileSync(new URL('../db/migrations/011_funzug_nearest_pixel_ratio.sql',import.meta.url),'utf8'));
   await pool.query('UPDATE social_post_drafts SET image_width=1122,image_height=1402');
   await assert.rejects(pool.query('UPDATE social_post_drafts SET image_width=1123,image_height=1402'),e=>e.code==='23514');
   assert.equal((await pool.query('SELECT image_width FROM social_post_drafts')).rows[0].image_width,1122);
  });
 }finally{
  await pool.end();
  await admin.query(`DROP SCHEMA IF EXISTS ${schema} CASCADE`);
  await admin.end();
 }
});
