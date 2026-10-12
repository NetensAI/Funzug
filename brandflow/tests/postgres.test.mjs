import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createRequire} from 'node:module';
import {randomUUID} from 'node:crypto';
import pg from 'pg';
import ts from 'typescript';
import {mergeOutcomes} from '../lib/funzug-outcomes.mjs';

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
   CREATE TABLE audit_logs(action text,target_type text,target_id text,details jsonb);`);
  const compiled=ts.transpileModule(fs.readFileSync(new URL('../app/api/integrations/funzug/outcomes/route.ts',import.meta.url),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
  const module={exports:{}};
  const adapters={
   'next/server':{NextResponse:{json:(body,opts)=>({body,status:opts?.status||200})}},
   '@/lib/db':{db:pool},'@/lib/funzug-drafts':{validBearer:()=>true},'@/lib/funzug-outcomes.mjs':{mergeOutcomes},
  };
  vm.runInNewContext(compiled,{module,exports:module.exports,Buffer,JSON,require(name){if(name in adapters)return adapters[name];if(name.startsWith('@/')||name.startsWith('next/'))throw Error('Unexpected app dependency');return require(name);}});
  const send=platformResults=>module.exports.POST({headers:new Headers(),text:async()=>JSON.stringify({batchId:'fixture',externalId:'fixture',platformResults})});
  const reset=async(status='approved',authorized=true)=>{
   await pool.query('TRUNCATE audit_logs,social_post_drafts');
   await pool.query("INSERT INTO social_post_drafts(id,brand_id,batch_id,external_id,status,publication_authorized,platforms) VALUES('draft','brand','fixture','fixture',$1,$2,'[\"facebook\",\"instagram\"]')",[status,authorized]);
  };
  const row=async()=>(await pool.query('SELECT platform_outcomes,published_at FROM social_post_drafts')).rows[0];
  const success=id=>({status:'published',postId:id,publishedAt:'2026-10-12T12:30:00+05:30'});
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
  });
 }finally{
  await pool.end();
  await admin.query(`DROP SCHEMA IF EXISTS ${schema} CASCADE`);
  await admin.end();
 }
});
