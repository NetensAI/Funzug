// Caller owns one transaction including the audit record. Never handles approval.
export async function storeOrderedDraft(client,brandId,batchId,draft){
 const existing=(await client.query('SELECT id,status,media_format FROM social_post_drafts WHERE brand_id=$1 AND batch_id=$2 AND external_id=$3 FOR UPDATE',[brandId,batchId,draft.externalId])).rows[0];
 if(existing&&existing.status!=='pending_review')throw Error('Reviewed draft is immutable');
 if(existing&&existing.media_format!==draft.format)throw Error('Existing draft format cannot be replaced through ingestion');
 let id=existing?.id;
 const values=[brandId,batchId,draft.externalId,draft.headline,draft.caption,JSON.stringify(draft.claims),JSON.stringify(draft.sources),JSON.stringify(draft.sources.map(s=>s.url)),JSON.stringify(draft.platforms),draft.proposedSchedule,draft.scheduleTimezone,draft.format];
 if(!id){
  id=(await client.query(`INSERT INTO social_post_drafts(brand_id,batch_id,external_id,headline,caption,claims,evidence_sources,source_urls,platforms,proposed_schedule,schedule_timezone,media_format,image_mime_type,image_width,image_height) VALUES($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8::jsonb,$9::jsonb,$10,$11,$12,NULL,NULL,NULL) RETURNING id`,values)).rows[0].id;
 }else{
  await client.query('DELETE FROM social_post_media_assets WHERE draft_id=$1',[id]);
  await client.query(`UPDATE social_post_drafts SET headline=$4,caption=$5,claims=$6::jsonb,evidence_sources=$7::jsonb,source_urls=$8::jsonb,platforms=$9::jsonb,proposed_schedule=$10,schedule_timezone=$11,updated_at=now() WHERE brand_id=$1 AND batch_id=$2 AND external_id=$3 AND status='pending_review'`,values.slice(0,11));
 }
 for(const [index,asset] of draft.media.entries())await client.query('INSERT INTO social_post_media_assets(draft_id,media_index,mime_type,width,height,duration_ms,media_bytes) VALUES($1,$2,$3,$4,$5,$6,$7)',[id,index,asset.mimeType,asset.width,asset.height,asset.durationMs??null,Buffer.from(asset.data,'base64')]);
 return {externalId:draft.externalId,id,status:'pending_review'};
}
