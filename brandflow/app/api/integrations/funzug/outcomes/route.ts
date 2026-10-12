import {NextResponse} from 'next/server';
import {z} from 'zod';
import {db} from '@/lib/db';
import {validBearer} from '@/lib/funzug-drafts';
import {mergeOutcomes} from '@/lib/funzug-outcomes.mjs';
export const dynamic='force-dynamic';
const result=z.discriminatedUnion('status',[
 z.object({status:z.literal('published'),postId:z.string().trim().min(1).max(300),publishedAt:z.string().datetime({offset:true})}).strict(),
 z.object({status:z.literal('failed'),failedAt:z.string().datetime({offset:true})}).strict(),
]);
const schema=z.object({batchId:z.string().trim().min(1).max(200),externalId:z.string().trim().min(1).max(200),platformResults:z.record(z.enum(['facebook','instagram']),result)}).strict();
export async function POST(req:Request){
 if(!validBearer(req.headers.get('authorization')))return NextResponse.json({error:'Unauthorized'},{status:401});
 let raw;
 try{const text=await req.text();if(Buffer.byteLength(text,'utf8')>8192)return NextResponse.json({error:'Request too large'},{status:413});raw=JSON.parse(text)}catch{return NextResponse.json({error:'Invalid JSON'},{status:400})}
 const parsed=schema.safeParse(raw);if(!parsed.success)return NextResponse.json({error:'Invalid outcome'},{status:400});
 const data=parsed.data;const client=await db.connect();
 try{
  await client.query('BEGIN');
  const {rows:[draft]}=await client.query(`SELECT d.id,d.status,d.publication_authorized,d.platforms,d.platform_outcomes,d.published_at FROM social_post_drafts d JOIN brands b ON b.id=d.brand_id WHERE b.slug='funzug' AND d.batch_id=$1 AND d.external_id=$2 FOR UPDATE OF d`,[data.batchId,data.externalId]);
  if(!draft||draft.status!=='approved'||!draft.publication_authorized){await client.query('ROLLBACK');return NextResponse.json({error:'Authorized approved draft not found'},{status:409})}
  let outcome;try{outcome=mergeOutcomes(draft.platforms,draft.platform_outcomes,data.platformResults)}catch{await client.query('ROLLBACK');return NextResponse.json({error:'Outcome conflicts with approved draft'},{status:409})}
  const unchanged=JSON.stringify(draft.platform_outcomes)===JSON.stringify(outcome.results);
  if(!unchanged){
   await client.query('UPDATE social_post_drafts SET platform_outcomes=$2::jsonb,published_at=COALESCE(published_at,$3::timestamptz),updated_at=now() WHERE id=$1',[draft.id,JSON.stringify(outcome.results),outcome.publishedAt]);
   await client.query(`INSERT INTO audit_logs(action,target_type,target_id,details) VALUES('social_draft.platform_outcomes','social_post_draft',$1,$2::jsonb)`,[draft.id,JSON.stringify({externalId:data.externalId,platformResults:outcome.results})]);
  }
  await client.query('COMMIT');return NextResponse.json({externalId:data.externalId,complete:Boolean(draft.published_at||outcome.publishedAt),unchanged});
 }catch{await client.query('ROLLBACK');return NextResponse.json({error:'Outcome could not be saved'},{status:500})}finally{client.release()}
}
