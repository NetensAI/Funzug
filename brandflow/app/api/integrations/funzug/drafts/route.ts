import {NextResponse} from 'next/server';
import {db} from '@/lib/db';
import {draftContentHash} from '@/lib/funzug-content-hash.mjs';
import {decodeAndVerifyImage,funzugBatchSchema,validBearer} from '@/lib/funzug-drafts';
export {POST as PUT} from '../outcomes/route';

export const dynamic='force-dynamic';
export async function GET(req:Request){
 if(!validBearer(req.headers.get('authorization')))return NextResponse.json({error:'Unauthorized'},{status:401});
 const batchId=new URL(req.url).searchParams.get('batchId');if(!batchId||batchId.length>200)return NextResponse.json({error:'Valid batchId required'},{status:400});
 const {rows}=await db.query(`SELECT d.headline,d.caption,d.claims,d.evidence_sources,d.platforms,d.image_bytes,d.image_mime_type,d.external_id "externalId",d.status,d.proposed_schedule "proposedSchedule",d.schedule_timezone "scheduleTimezone",d.published_at "publishedAt",d.publication_authorized "publicationAuthorized",d.review_checks "reviewChecks",d.reviewed_at "reviewedAt",d.review_note "reviewNote",u.username "reviewedBy" FROM social_post_drafts d JOIN brands b ON b.id=d.brand_id LEFT JOIN users u ON u.id=d.reviewed_by WHERE b.slug='funzug' AND d.batch_id=$1 ORDER BY d.created_at`,[batchId]);
 const drafts=rows.map(row=>{const {headline,caption,claims,evidence_sources,platforms,image_bytes,image_mime_type,...status}=row;return {...status,contentHash:draftContentHash(row)}});
 return NextResponse.json({batchId,drafts});
}
export async function POST(req:Request){
 if(!validBearer(req.headers.get('authorization')))return NextResponse.json({error:'Unauthorized'},{status:401});
 const length=Number(req.headers.get('content-length')||0);if(length>13*1024*1024)return NextResponse.json({error:'Request exceeds 13 MB limit'},{status:413});
 let input:unknown;try{const text=await req.text();if(Buffer.byteLength(text,'utf8')>13*1024*1024)return NextResponse.json({error:'Request exceeds 13 MB limit'},{status:413});input=JSON.parse(text)}catch{return NextResponse.json({error:'Invalid JSON'},{status:400})}
 const parsed=funzugBatchSchema.safeParse(input);if(!parsed.success)return NextResponse.json({error:'Invalid draft batch',issues:parsed.error.issues.map(x=>({path:x.path.join('.'),message:x.message}))},{status:400});
 const {rows:[brand]}=await db.query("SELECT id FROM brands WHERE slug='funzug' AND status<>'archived'");if(!brand)return NextResponse.json({error:'Funzug brand is unavailable'},{status:409});
 const client=await db.connect();try{
  await client.query('BEGIN');const accepted=[];
  for(const draft of parsed.data.drafts){
   const bytes=draft.image.kind==='base64'?decodeAndVerifyImage(draft.image.data,draft.image.mimeType):null;
   const url=draft.image.kind==='secure_url'?draft.image.url:null;
   const {rows:[row]}=await client.query(`INSERT INTO social_post_drafts(brand_id,batch_id,external_id,headline,caption,claims,evidence_sources,source_urls,platforms,proposed_schedule,schedule_timezone,image_mime_type,image_width,image_height,image_bytes,image_url)
    VALUES($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8::jsonb,$9::jsonb,$10,$11,$12,1080,1350,$13,$14)
    ON CONFLICT(brand_id,batch_id,external_id) DO UPDATE SET headline=EXCLUDED.headline,caption=EXCLUDED.caption,claims=EXCLUDED.claims,evidence_sources=EXCLUDED.evidence_sources,source_urls=EXCLUDED.source_urls,platforms=EXCLUDED.platforms,proposed_schedule=EXCLUDED.proposed_schedule,schedule_timezone=EXCLUDED.schedule_timezone,image_mime_type=EXCLUDED.image_mime_type,image_width=1080,image_height=1350,image_bytes=EXCLUDED.image_bytes,image_url=EXCLUDED.image_url,updated_at=now()
    WHERE social_post_drafts.status='pending_review' RETURNING id,status`,[brand.id,parsed.data.batchId,draft.externalId,draft.headline,draft.caption,JSON.stringify(draft.claims),JSON.stringify(draft.sources),JSON.stringify(draft.sources.map(x=>x.url)),JSON.stringify(draft.platforms),draft.proposedSchedule,draft.scheduleTimezone,draft.image.mimeType,bytes,url]);
   if(!row)throw new Error(`Draft ${draft.externalId} has already been reviewed`);accepted.push({externalId:draft.externalId,id:row.id,status:row.status});
  }
  await client.query(`INSERT INTO audit_logs(action,target_type,target_id,details,ip_address) VALUES('social_draft.batch_received','social_post_batch',$1,$2::jsonb,$3)`,[parsed.data.batchId,JSON.stringify({brandSlug:'funzug',draftCount:accepted.length}),req.headers.get('cf-connecting-ip')||req.headers.get('x-forwarded-for')?.split(',')[0]?.trim()||'unknown']);
  await client.query('COMMIT');return NextResponse.json({batchId:parsed.data.batchId,accepted},{status:202});
 }catch(e:any){await client.query('ROLLBACK');return NextResponse.json({error:e.message||'Draft batch rejected'},{status:409})}finally{client.release()}
}
