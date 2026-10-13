import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {randomUUID} from 'node:crypto';
import pg from 'pg';
import {storeOrderedDraft} from '../lib/store-ordered-draft.mjs';
import {orderedMediaManifest} from '../lib/ordered-media-manifest.mjs';
import {storedOrderedMediaHash} from '../lib/funzug-content-hash.mjs';
const url=process.env.FUNZUG_TEST_DATABASE_URL;
if(process.env.FUNZUG_REQUIRE_DATABASE_TESTS==='1'&&!url)throw Error('Disposable PostgreSQL URL required');
test('mixed ingestion against actual migrated PostgreSQL storage',{skip:!url},async()=>{
 const parsed=new URL(url);assert.ok(['localhost','127.0.0.1','[::1]'].includes(parsed.hostname));assert.equal(parsed.pathname,'/funzug_test');
 const schema='funzug_ingest_test_'+randomUUID().replaceAll('-','');
 const admin=new pg.Pool({connectionString:url});
 const pool=new pg.Pool({connectionString:url,options:`-c search_path=${schema} -c statement_timeout=5000`});
 const brand=randomUUID();
 try{
  await admin.query(`CREATE SCHEMA ${schema}`);
  await pool.query(`CREATE TABLE social_post_drafts(id uuid PRIMARY KEY DEFAULT gen_random_uuid(),brand_id uuid,batch_id text,external_id text,status text NOT NULL DEFAULT 'pending_review',headline text,caption text,claims jsonb,evidence_sources jsonb,source_urls jsonb,platforms jsonb,proposed_schedule timestamptz,schedule_timezone text,updated_at timestamptz DEFAULT now(),image_mime_type text NOT NULL,image_width integer NOT NULL,image_height integer NOT NULL,image_bytes bytea,image_url text,CONSTRAINT social_post_drafts_check CHECK ((image_bytes IS NOT NULL)<>(image_url IS NOT NULL)),UNIQUE(brand_id,batch_id,external_id));`);
  const image=randomUUID();
  await pool.query("INSERT INTO social_post_drafts(id,brand_id,batch_id,external_id,image_mime_type,image_width,image_height,image_bytes) VALUES($1,$2,'legacy','image','image/png',1080,1350,$3)",[image,brand,Buffer.from('legacy exact bytes')]);
  for(const migration of ['013_funzug_ordered_media.sql','014_funzug_mixed_ingestion.sql']){
   const sql=fs.readFileSync(new URL('../db/migrations/'+migration,import.meta.url),'utf8');await pool.query(sql);await pool.query(sql);
  }
  assert.equal((await pool.query('SELECT image_bytes FROM social_post_drafts WHERE id=$1',[image])).rows[0].image_bytes.toString(),'legacy exact bytes');
  const draft={externalId:'carousel',format:'carousel',headline:'Headline',caption:'Caption',claims:[],sources:[],platforms:['facebook','instagram'],proposedSchedule:'2099-01-01T12:00:00+05:30',scheduleTimezone:'Asia/Kolkata',media:['first','second'].map(data=>({mimeType:'image/png',width:40,height:50,data:Buffer.from(data).toString('base64')}))};
  const client=await pool.connect();
  try{
   await client.query('BEGIN');const accepted=await storeOrderedDraft(client,brand,'batch',draft);await client.query('COMMIT');
   const read=async()=>({row:(await pool.query('SELECT * FROM social_post_drafts WHERE id=$1',[accepted.id])).rows[0],assets:(await pool.query('SELECT * FROM social_post_media_assets WHERE draft_id=$1 ORDER BY media_index',[accepted.id])).rows});
   const original=await read();assert.equal(original.row.image_bytes,null);assert.equal(original.row.image_mime_type,null);
   const before=orderedMediaManifest(original.row,original.assets).contentHash;
   const snapshot=(await pool.query(`SELECT d.*,COALESCE((SELECT jsonb_agg(jsonb_build_object('index',a.media_index,'mimeType',a.mime_type,'width',a.width,'height',a.height,'durationMs',a.duration_ms,'sha256',a.sha256) ORDER BY a.media_index) FROM social_post_media_assets a WHERE a.draft_id=d.id),'[]'::jsonb) ordered_media FROM social_post_drafts d WHERE id=$1`,[accepted.id])).rows[0];
   assert.equal(storedOrderedMediaHash(snapshot),before);
   await client.query('BEGIN');await storeOrderedDraft(client,brand,'batch',{...draft,caption:'Changed'});await client.query('ROLLBACK');
   const after=await read();assert.equal(orderedMediaManifest(after.row,after.assets).contentHash,before);
   await client.query('BEGIN');await assert.rejects(storeOrderedDraft(client,brand,'batch',{...draft,media:[draft.media[0],draft.media[0]]}),e=>e.code==='23505');await client.query('ROLLBACK');
   assert.equal((await read()).assets.length,2);
   await pool.query("UPDATE social_post_drafts SET status='approved' WHERE id=$1",[accepted.id]);
   await client.query('BEGIN');await assert.rejects(storeOrderedDraft(client,brand,'batch',draft),/immutable/);await client.query('ROLLBACK');
   const reel={...draft,externalId:'reel',format:'reel',media:[{mimeType:'video/mp4',width:40,height:50,durationMs:1000,data:Buffer.from('private reel bytes').toString('base64')}]};
   await client.query('BEGIN');const stored=await storeOrderedDraft(client,brand,'batch',reel);await client.query('COMMIT');
   const video=(await pool.query('SELECT * FROM social_post_media_assets WHERE draft_id=$1',[stored.id])).rows[0];assert.equal(video.duration_ms,1000);assert.equal(video.media_bytes.toString(),'private reel bytes');
   await assert.rejects(pool.query('UPDATE social_post_drafts SET image_bytes=NULL WHERE id=$1',[image]),e=>e.code==='23514');
  }finally{client.release();}
 }finally{await pool.end();await admin.query(`DROP SCHEMA IF EXISTS ${schema} CASCADE`);await admin.end();}
});
