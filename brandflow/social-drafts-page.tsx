import AppPage from '@/components/AppPage';
import SocialDraftReview from '@/components/SocialDraftReview';
import SocialDraftReschedule from '@/components/SocialDraftReschedule';
import SocialDraftMedia from '@/components/SocialDraftMedia';
import {db} from '@/lib/db';
import {getSession} from '@/lib/auth';
import {draftContentHashFromChecksum} from '@/lib/funzug-content-hash.mjs';
import {mixedDeliveryEnabled} from '@/lib/mixed-delivery-policy.mjs';

export default async function Page({searchParams}:{searchParams:{brand?:string,status?:string,page?:string}}){
 const {rows:brands}=await db.query("SELECT * FROM brands WHERE status<>'archived' ORDER BY created_at");
 const brand=brands.find(x=>x.slug===searchParams.brand)||brands[0];
 const requestedStatus=searchParams.status||'';
 const status:'pending_review'|'approved'|'rejected'=requestedStatus==='pending_review'||requestedStatus==='approved'||requestedStatus==='rejected'?requestedStatus:'pending_review';
 const page=Math.min(10000,Math.max(1,Number.parseInt(searchParams.page||'1',10)||1));
 const {rows:pageRows}=await db.query(`SELECT d.id,d.media_format,d.batch_id,d.external_id,d.headline,d.caption,d.claims,d.evidence_sources,d.platforms,d.proposed_schedule,d.schedule_timezone,d.status,d.published_at,d.reviewed_at,d.review_note,d.platform_outcomes,d.native_handoff,d.image_mime_type,encode(sha256(d.image_bytes),'hex') image_sha256,u.username reviewer_username,COALESCE((SELECT jsonb_agg(jsonb_build_object('oldSchedule',r.old_proposed_schedule,'oldTimezone',r.old_schedule_timezone,'newSchedule',r.new_proposed_schedule,'newTimezone',r.new_schedule_timezone,'reviewedAt',r.rescheduled_at,'reviewNote',r.reschedule_note,'reviewedBy',ru.username) ORDER BY r.rescheduled_at DESC) FROM social_post_reschedules r LEFT JOIN users ru ON ru.id=r.rescheduled_by WHERE r.draft_id=d.id),'[]'::jsonb) reschedule_history FROM social_post_drafts d LEFT JOIN users u ON u.id=d.reviewed_by WHERE d.brand_id=$1 AND d.status=$2 ORDER BY d.proposed_schedule,d.created_at DESC,d.id LIMIT 9 OFFSET $3`,[brand.id,status,(page-1)*8]);
 const rows=pageRows.slice(0,8),hasMore=pageRows.length>8;
 const pageUrl=(n:number)=>`/social-drafts?brand=${encodeURIComponent(brand.slug)}&status=${status}&page=${n}`;
 const session=await getSession();
 const mixedIds=rows.filter(d=>d.media_format&&d.media_format!=='image').map(d=>d.id);
 if(mixedIds.length){
  const {rows:assets}=await db.query('SELECT draft_id,media_index,mime_type,width,height,duration_ms,sha256 FROM social_post_media_assets WHERE draft_id=ANY($1::uuid[]) ORDER BY draft_id,media_index',[mixedIds]);
  for(const draft of rows){
   draft.media_assets=assets.filter(a=>a.draft_id===draft.id).map(a=>({index:a.media_index,mimeType:a.mime_type,width:a.width,height:a.height,sha256:a.sha256}));
   draft.ordered_media=assets.filter(a=>a.draft_id===draft.id).map(a=>({index:a.media_index,mimeType:a.mime_type,width:a.width,height:a.height,durationMs:a.duration_ms,sha256:a.sha256}));
  }
 }
 return <AppPage>{()=> <div className="stack">
  <div className="card"><div className="row spread"><div><h2>{brand.name} social-post review</h2><div className="muted">Approve to authorize publishing at your selected IST time. Approval does not publish immediately.</div></div><div className="row">{['pending_review','approved','rejected'].map(s=><a className={`btn ${s===status?'':'secondary'}`} href={`/social-drafts?brand=${brand.slug}&status=${s}`} key={s}>{s.replace('_',' ')}</a>)}</div></div></div>
  <nav className="row" aria-label="Review pages">{page>1&&<a className="btn secondary" href={pageUrl(page-1)}>Previous</a>}<span>Page {page}</span>{hasMore&&<a className="btn secondary" href={pageUrl(page+1)}>Next 8 posts</a>}</nav>
  {rows.map((d,index)=>{
   const sources=new Map((d.evidence_sources||[]).map((s:any)=>[s.id,s]));
   const published=Boolean(d.published_at);
   const reviewedContentHash=draftContentHashFromChecksum(d);
   const reviewEnabled=(!d.media_format||d.media_format==='image'||mixedDeliveryEnabled(d.external_id,process.env))&&Boolean(reviewedContentHash);
   return <article className="card draft" key={d.id}>
    <div><SocialDraftMedia id={d.id} headline={d.headline} format={d.media_format} assets={d.media_assets||[]} imageHash={d.image_sha256} priority={index===0}/></div>
    <div className="stack">
     <div className="row spread"><span className="badge">{published?'published':d.status.replace('_',' ')}</span><span className="muted">Batch {d.batch_id} · {d.external_id}</span></div>
     <h2>{d.headline}</h2><p className="caption">{d.caption}</p>
     <div><strong>Platforms</strong><div>{d.platforms.join(', ')}</div></div>
     <div><strong>Scheduled for (IST)</strong><div>{new Date(d.proposed_schedule).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'})} IST</div></div>
     {published&&<div><strong>Published (IST)</strong><div>{new Date(d.published_at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'})} IST</div></div>}
     {Object.keys(d.platform_outcomes||{}).length>0&&<div className="reviewbox"><strong>Platform results</strong>{d.platforms.map((p:string)=>{const r=d.platform_outcomes?.[p];return <div key={p}>{p}: {r?.status||'not reported'}{r?.status==='published'&&<span> · Post ID {r.postId}</span>}{r&&<span> · {new Date(r.publishedAt||r.failedAt).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})} IST</span>}</div>})}{Object.values(d.platform_outcomes||{}).some((r:any)=>r.status==='failed')&&<p className="error">Publishing failed on at least one platform. Successful posts will not be retried automatically. Contact the workflow operator for recovery.</p>}</div>}
     <div><strong>Claims and evidence</strong><ol>{d.claims.map((c:any,i:number)=><li key={i}><div>{c.text}</div><div className="muted">Support: {c.support_note}</div>{c.source_ids.map((id:string)=>{const s:any=sources.get(id);return s?<div className="evidence" key={id}><a className="source" href={s.url} target="_blank" rel="noreferrer">{s.publisher}: {s.title}</a><span className="muted">Published {s.published_at?new Date(s.published_at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'}):'not supplied'}; checked {new Date(s.checked_at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})} IST</span></div>:<div className="error" key={id}>Missing source {id}</div>})}</li>)}</ol></div>
     <div><strong>All sources</strong>{(d.evidence_sources||[]).map((s:any)=><div className="evidence" key={s.id}><a className="source" href={s.url} target="_blank" rel="noreferrer">{s.publisher}: {s.title}</a><span className="muted">ID {s.id}; checked {new Date(s.checked_at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})} IST</span></div>)}</div>
     {d.status==='pending_review'&&session?.role==='admin'&&reviewEnabled&&<SocialDraftReview id={d.id} initialSchedule={new Date(d.proposed_schedule).toISOString()} reviewedContentHash={reviewedContentHash!}/>}
     {d.status==='pending_review'&&!reviewEnabled&&<div className="warning">Media verification or delivery is unavailable. This draft cannot be approved yet.</div>}
     {d.status!=='pending_review'&&<div className="reviewbox"><strong>{published?'Published':d.status==='approved'?'Approved for scheduling':'Rejected'}</strong><div>{d.review_note}</div><div className="muted">Reviewed by {d.reviewer_username||'deleted user'} on {new Date(d.reviewed_at).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})} IST</div></div>}
     {d.native_handoff!=null&&<div className="reviewbox"><strong>Meta delivery: {d.native_handoff.state||'reconciliation required'}</strong><div>Review upcoming content in Meta Business Suite. A reservation alone does not mean the post is scheduled. Native schedule reconciliation is required before changing its time.</div>{Object.entries(d.native_handoff.receipts||{}).map(([p,r]:[string,any])=><div key={p}>{p}: schedule ID {r.schedule_id}</div>)}</div>}
     {d.status==='approved'&&!published&&d.native_handoff==null&&Object.keys(d.platform_outcomes||{}).length===0&&session?.role==='admin'&&<SocialDraftReschedule id={d.id} currentSchedule={d.proposed_schedule}/>}
     {(d.reschedule_history||[]).length>0&&<details className="reviewbox"><summary>Reschedule history ({d.reschedule_history.length})</summary>{d.reschedule_history.map((r:any,i:number)=><div className="evidence" key={i}><div>{new Date(r.oldSchedule).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})} IST → {new Date(r.newSchedule).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})} IST</div><div>{r.reviewNote}</div><span className="muted">By {r.reviewedBy||'deleted user'} at {new Date(r.reviewedAt).toLocaleString('en-IN',{timeZone:'Asia/Kolkata'})} IST</span></div>)}</details>}
    </div>
   </article>;
  })}
  {!rows.length&&<div className="card empty">No {status.replace('_',' ')} social-post drafts on this page.</div>}
  <nav className="row" aria-label="More review pages">{page>1&&<a className="btn secondary" href={pageUrl(page-1)}>Previous</a>}{hasMore&&<a className="btn" href={pageUrl(page+1)}>Next 8 posts</a>}</nav>
 </div>}</AppPage>;
}
