import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {randomUUID,createHash} from 'node:crypto';
import pg from 'pg';

const url=process.env.FUNZUG_TEST_DATABASE_URL;
if(process.env.FUNZUG_REQUIRE_DATABASE_TESTS==='1'&&!url)throw Error('Disposable PostgreSQL URL required');
test('ordered media migration against disposable PostgreSQL',{skip:!url},async t=>{
 const parsed=new URL(url);assert.ok(['localhost','127.0.0.1','[::1]'].includes(parsed.hostname));assert.equal(parsed.pathname,'/funzug_test');
 const schema='funzug_media_test_'+randomUUID().replaceAll('-','');
 const admin=new pg.Pool({connectionString:url});
 const pool=new pg.Pool({connectionString:url,options:`-c search_path=${schema} -c statement_timeout=5000`});
 const id=randomUUID(),image=randomUUID(),reel=randomUUID();
 try{
  await admin.query(`CREATE SCHEMA ${schema}`);
  await pool.query('CREATE TABLE social_post_drafts(id uuid PRIMARY KEY,status text NOT NULL,image_bytes bytea)');
  await pool.query('INSERT INTO social_post_drafts VALUES($1,$2,$3)',[image,'pending_review',Buffer.from('unchanged legacy image')]);
  const migration=fs.readFileSync(new URL('../db/migrations/013_funzug_ordered_media.sql',import.meta.url),'utf8');
  await pool.query(migration);await pool.query(migration);
  assert.equal((await pool.query('SELECT media_format,image_bytes FROM social_post_drafts')).rows[0].media_format,'image');
  assert.equal((await pool.query('SELECT image_bytes FROM social_post_drafts')).rows[0].image_bytes.toString(),'unchanged legacy image');
  await pool.query("INSERT INTO social_post_drafts(id,status,media_format) VALUES($1,'pending_review','carousel'),($2,'pending_review','reel')",[id,reel]);
  const insert=(draft,index,data='first',mime='image/png',width=1122,height=1402,duration=null)=>pool.query('INSERT INTO social_post_media_assets(draft_id,media_index,mime_type,width,height,media_bytes,duration_ms) VALUES($1,$2,$3,$4,$5,$6,$7)',[draft,index,mime,width,height,Buffer.from(data),duration]);
  await t.test('format, ratio, count, duration and duplicate byte constraints fail closed',async()=>{
   await assert.rejects(insert(image,0),/format/);
   await assert.rejects(insert(id,0,'wrong mime','video/mp4',1122,1402,30000),/format/);
   await assert.rejects(insert(id,10),e=>e.code==='23514');
   await assert.rejects(insert(id,0,'wrong ratio','image/png',1123,1402),e=>e.code==='23514');
   await assert.rejects(insert(reel,0,'video','video/mp4',1122,1402,null),e=>e.code==='23514');
   await assert.rejects(insert(reel,1,'video','video/mp4',1122,1402,30000),/format/);
   await assert.rejects(pool.query("UPDATE social_post_drafts SET status='approved' WHERE id=$1",[id]),/Complete ordered media/);
   await insert(id,0);await assert.rejects(insert(id,1),e=>e.code==='23505');await insert(id,2,'second');
   await assert.rejects(pool.query("UPDATE social_post_drafts SET status='approved' WHERE id=$1",[id]),/Complete ordered media/);
   await pool.query('UPDATE social_post_media_assets SET media_index=1 WHERE draft_id=$1 AND media_index=2',[id]);
   const rows=(await pool.query('SELECT media_index,sha256 FROM social_post_media_assets WHERE draft_id=$1 ORDER BY media_index',[id])).rows;
   assert.deepEqual(rows.map(x=>x.media_index),[0,1]);assert.equal(rows[0].sha256,createHash('sha256').update('first').digest('hex'));
  });
  await t.test('reviewed bytes, order, parent and format cannot be changed',async()=>{
   await assert.rejects(pool.query("UPDATE social_post_drafts SET media_format='image' WHERE id=$1",[id]),/Clear pending assets/);
   await pool.query("UPDATE social_post_drafts SET status='approved' WHERE id=$1",[id]);
   for(const sql of ['UPDATE social_post_media_assets SET media_index=3 WHERE draft_id=$1','UPDATE social_post_media_assets SET media_bytes=decode(\'00\',\'hex\') WHERE draft_id=$1','DELETE FROM social_post_media_assets WHERE draft_id=$1'])await assert.rejects(pool.query(sql,[id]),/immutable/);
   await assert.rejects(insert(id,2,'third'),/immutable/);
   await assert.rejects(pool.query("UPDATE social_post_drafts SET media_format='reel' WHERE id=$1",[id]),/immutable/);
   await insert(reel,0,'video','video/mp4',1122,1402,30000);await pool.query("UPDATE social_post_drafts SET status='approved' WHERE id=$1",[reel]);
  });
 }finally{await pool.end();await admin.query(`DROP SCHEMA IF EXISTS ${schema} CASCADE`);await admin.end();}
});
