import {NextResponse} from 'next/server';
import {db} from '@/lib/db';
import {draftContentHash} from '@/lib/funzug-content-hash.mjs';
import {decodeAndVerifyImage,validBearer} from '@/lib/funzug-drafts';
import {orderedMediaManifest} from '@/lib/ordered-media-manifest.mjs';
import {decodeOrderedMedia} from '@/lib/decode-ordered-media.mjs';

export const dynamic='force-dynamic';

// The existing private integration credential can read only an owner-approved
// Funzug image package. This endpoint never approves, stages or schedules it.
export async function GET(req:Request){
 if(!validBearer(req.headers.get('authorization')))return NextResponse.json({error:'Unauthorized'},{status:401});
 const query=new URL(req.url).searchParams;
 const batchId=query.get('batchId'),externalId=query.get('externalId');
 if(!batchId||batchId.length>200||!externalId||externalId.length>200)return NextResponse.json({error:'Valid batchId and externalId required'},{status:400});
 const {rows:[draft]}=await db.query(`SELECT d.id,d.media_format,d.external_id,d.headline,d.caption,d.claims,d.evidence_sources,d.platforms,d.image_bytes,d.image_mime_type,d.image_width,d.image_height,d.status,d.publication_authorized,d.review_checks,d.reviewed_at,d.reviewed_by,d.proposed_schedule,d.schedule_timezone,d.native_handoff,d.published_at,d.platform_outcomes,
  COALESCE((SELECT jsonb_agg(jsonb_build_object('draft_id',a.draft_id,'media_index',a.media_index,'mime_type',a.mime_type,'width',a.width,'height',a.height,'duration_ms',a.duration_ms,'sha256',a.sha256,'hex_bytes',encode(a.media_bytes,'hex')) ORDER BY a.media_index) FROM social_post_media_assets a WHERE a.draft_id=d.id),'[]'::jsonb) private_assets
  FROM social_post_drafts d JOIN brands b ON b.id=d.brand_id
  WHERE b.slug='funzug' AND d.batch_id=$1 AND d.external_id=$2`,[batchId,externalId]);
 if(!draft)return NextResponse.json({error:'Approved Funzug draft not found'},{status:404});
 if(draft.media_format&&draft.media_format!=='image'&&process.env.FUNZUG_NATIVE_MIXED_ENABLED!=='1')return NextResponse.json({error:'Mixed-format native delivery is not enabled'},{status:409});
 if(draft.status!=='approved'||draft.publication_authorized!==true||!draft.reviewed_by||!draft.reviewed_at||draft.published_at||Object.keys(draft.platform_outcomes||{}).length||draft.schedule_timezone!=='Asia/Kolkata')return NextResponse.json({error:'Owner approval is unavailable for native scheduling'},{status:409});
 const checks=draft.review_checks||{};
 const confirmed=checks.approvalConfirmed===true||['claims','sources','caption','images','platforms','schedule'].every(key=>checks[key]===true);
 if(!confirmed||!Array.isArray(draft.platforms)||!draft.platforms.length||new Set(draft.platforms).size!==draft.platforms.length||draft.platforms.some((p:string)=>!['facebook','instagram'].includes(p)))return NextResponse.json({error:'Owner approval confirmation is invalid'},{status:409});
 try{
  if(draft.media_format&&draft.media_format!=='image'){
   const assets=draft.private_assets.map((asset:any)=>{
    if(typeof asset.hex_bytes!=='string'||!/^([0-9a-f]{2})+$/.test(asset.hex_bytes))throw Error('Invalid private bytes');
    return {...asset,media_bytes:Buffer.from(asset.hex_bytes,'hex')};
   });
   const package1=orderedMediaManifest(draft,assets);
   if(await decodeOrderedMedia(package1.draft)!==package1.contentHash)throw Error('Decode fingerprint mismatch');
   if(!Number.isFinite(new Date(draft.proposed_schedule).getTime())||(draft.native_handoff&&draft.native_handoff.content_hash!==package1.contentHash))throw Error('Reserved content changed');
   return NextResponse.json({batchId,externalId,...package1.draft,contentHash:package1.contentHash,proposedSchedule:draft.proposed_schedule,scheduleTimezone:'Asia/Kolkata',reviewedAt:draft.reviewed_at,nativeHandoff:draft.native_handoff},{headers:{'Cache-Control':'no-store'}});
  }
  if(!Buffer.isBuffer(draft.image_bytes))throw new Error('Image unavailable');
  decodeAndVerifyImage(draft.image_bytes.toString('base64'),draft.image_mime_type,draft.image_width,draft.image_height);
  const contentHash=draftContentHash(draft);
  if(!contentHash||!Number.isFinite(new Date(draft.proposed_schedule).getTime()))throw new Error('Package unavailable');
  if(draft.native_handoff&&draft.native_handoff.content_hash!==contentHash)throw new Error('Reserved content changed');
  return NextResponse.json({batchId,externalId,headline:draft.headline,caption:draft.caption,claims:draft.claims,sources:draft.evidence_sources,platforms:draft.platforms,contentHash,proposedSchedule:draft.proposed_schedule,scheduleTimezone:'Asia/Kolkata',reviewedAt:draft.reviewed_at,nativeHandoff:draft.native_handoff,image:{mimeType:draft.image_mime_type,width:draft.image_width,height:draft.image_height,data:draft.image_bytes.toString('base64')}},{headers:{'Cache-Control':'no-store'}});
 }catch{return NextResponse.json({error:'Approved media package requires reconciliation'},{status:409})}
}
