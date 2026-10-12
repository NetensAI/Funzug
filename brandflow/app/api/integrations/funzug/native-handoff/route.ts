import {NextResponse} from 'next/server';
import {z} from 'zod';
import {db} from '@/lib/db';
import {validBearer} from '@/lib/funzug-drafts';
import {draftContentHash} from '@/lib/funzug-content-hash.mjs';
import {mergeNativeHandoff,nativeHandoffEqual} from '@/lib/funzug-native-handoff.mjs';
export const dynamic='force-dynamic';
const timestamp=z.string().datetime({offset:true});
const receipt=z.object({platform:z.enum(['facebook','instagram']),schedule_id:z.string().trim().min(1).max(200),scheduled_at:timestamp,content_hash:z.string().regex(/^[0-9a-f]{64}$/),planner_url:z.string().url().max(2000),checked_at:timestamp}).strict();
const handoff=z.object({state:z.enum(['reserved','submitting','scheduled']),reserved_at:timestamp,scheduled_at:timestamp,content_hash:z.string().regex(/^[0-9a-f]{64}$/),platforms:z.array(z.enum(['facebook','instagram'])).min(1).max(2),receipts:z.record(z.enum(['facebook','instagram']),receipt),submission_started_at:timestamp.optional()}).strict();
const schema=z.object({batchId:z.string().min(1).max(200),externalId:z.string().min(1).max(200),handoff}).strict();
export async function POST(req:Request){
 if(!validBearer(req.headers.get('authorization')))return NextResponse.json({error:'Unauthorized'},{status:401});
 let raw;try{const text=await req.text();if(Buffer.byteLength(text,'utf8')>12000)return NextResponse.json({error:'Request too large'},{status:413});raw=JSON.parse(text)}catch{return NextResponse.json({error:'Invalid JSON'},{status:400})}
 const parsed=schema.safeParse(raw);if(!parsed.success)return NextResponse.json({error:'Invalid native handoff'},{status:400});
 const data=parsed.data;const client=await db.connect();
 try{
  await client.query('BEGIN');
  const {rows:[draft]}=await client.query(`SELECT d.* FROM social_post_drafts d JOIN brands b ON b.id=d.brand_id WHERE b.slug='funzug' AND d.batch_id=$1 AND d.external_id=$2 FOR UPDATE OF d`,[data.batchId,data.externalId]);
  if(!draft||draft.status!=='approved'||!draft.publication_authorized||draft.published_at||Object.keys(draft.platform_outcomes||{}).length)throw new Error('Draft is not an unpublished owner approval');
  if(draft.schedule_timezone!=='Asia/Kolkata'||new Date(draft.proposed_schedule).getTime()!==Date.parse(data.handoff.scheduled_at)||draftContentHash(draft)!==data.handoff.content_hash)throw new Error('Native handoff differs from reviewed content or IST slot');
  if(data.handoff.state==='reserved'&&Date.parse(data.handoff.scheduled_at)<=Date.now())throw new Error('Native slot has passed');
  const merged=mergeNativeHandoff(draft.native_handoff,data.handoff,draft.platforms);
  const unchanged=nativeHandoffEqual(draft.native_handoff,merged);
  if(!unchanged){
   await client.query('UPDATE social_post_drafts SET native_handoff=$2::jsonb,updated_at=now() WHERE id=$1',[draft.id,JSON.stringify(merged)]);
   await client.query(`INSERT INTO audit_logs(action,target_type,target_id,details) VALUES('social_draft.native_handoff','social_post_draft',$1,$2::jsonb)`,[draft.id,JSON.stringify({externalId:data.externalId,state:merged.state,scheduledAt:merged.scheduled_at})]);
  }
  await client.query('COMMIT');return NextResponse.json({externalId:data.externalId,state:merged.state,unchanged});
 }catch{await client.query('ROLLBACK');return NextResponse.json({error:'Native handoff requires reconciliation'},{status:409})}finally{client.release()}
}
