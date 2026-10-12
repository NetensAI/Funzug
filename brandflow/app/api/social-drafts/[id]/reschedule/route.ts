import {NextResponse} from 'next/server';
import {db} from '@/lib/db';
import {getSession} from '@/lib/auth';
import {clientIp,sameOrigin} from '@/lib/security';
import {nextReviewedAt,rescheduleEligibility,validateRescheduleInput} from '@/lib/social-reschedule.mjs';
import {canRescheduleOutcomes} from '@/lib/funzug-outcomes.mjs';

export async function POST(req:Request,{params}:{params:{id:string}}){
 if(!sameOrigin(req))return NextResponse.json({error:'Invalid origin'},{status:403});
 const session=await getSession();
 if(!session?.sub||session.role!=='admin')return NextResponse.json({error:'Administrator access required'},{status:403});
 const input=validateRescheduleInput(await req.json().catch(()=>null));if(!input.ok)return NextResponse.json({error:input.error},{status:400});
 const client=await db.connect();try{
  await client.query('BEGIN');
  const {rows:[user]}=await client.query('SELECT username,active,role FROM users WHERE id=$1 FOR UPDATE',[session.sub]);
  if(!user?.active||user.role!=='admin'){await client.query('ROLLBACK');return NextResponse.json({error:'Administrator access required'},{status:403})}
  const {rows:[draft]}=await client.query('SELECT id,brand_id,status,publication_authorized,published_at,platform_outcomes,proposed_schedule,schedule_timezone,reviewed_by,reviewed_at,review_note FROM social_post_drafts WHERE id=$1 FOR UPDATE',[params.id]);
  if(!draft){await client.query('ROLLBACK');return NextResponse.json({error:'Draft not found'},{status:404})}
  if(!canRescheduleOutcomes(draft.platform_outcomes)){await client.query('ROLLBACK');return NextResponse.json({error:'Draft has publication results and requires platform-specific recovery'},{status:409})}
  const eligibility=rescheduleEligibility({authenticated:!!session.sub&&!!user.active,role:user.role,status:draft.status,publicationAuthorized:draft.publication_authorized,publishedAt:draft.published_at});
  if(!eligibility.ok){await client.query('ROLLBACK');return NextResponse.json({error:eligibility.error},{status:eligibility.status})}
  const reviewedAt=nextReviewedAt(draft.reviewed_at);
  await client.query(`INSERT INTO social_post_reschedules(draft_id,old_proposed_schedule,old_schedule_timezone,new_proposed_schedule,new_schedule_timezone,previous_reviewed_by,previous_reviewed_at,previous_review_note,rescheduled_by,rescheduled_at,reschedule_note) VALUES($1,$2,$3,$4,'Asia/Kolkata',$5,$6,$7,$8,$9,$10)`,[draft.id,draft.proposed_schedule,draft.schedule_timezone,input.date,draft.reviewed_by,draft.reviewed_at,draft.review_note,session.sub,reviewedAt,input.note]);
  const {rows:[updated]}=await client.query(`UPDATE social_post_drafts SET proposed_schedule=$2,schedule_timezone='Asia/Kolkata',reviewed_at=$3,reviewed_by=$4,review_note=$5,updated_at=now() WHERE id=$1 AND status='approved' AND publication_authorized=true AND published_at IS NULL RETURNING proposed_schedule,schedule_timezone,reviewed_at`,[draft.id,input.date,reviewedAt,session.sub,input.note]);
  if(!updated)throw new Error('Draft is no longer eligible for rescheduling');
  await client.query(`INSERT INTO audit_logs(actor_user_id,actor_username,action,target_type,target_id,details,ip_address) VALUES($1,$2,'social_draft.rescheduled','social_post_draft',$3,$4::jsonb,$5)`,[session.sub,user.username,draft.id,JSON.stringify({oldProposedSchedule:draft.proposed_schedule,oldScheduleTimezone:draft.schedule_timezone,newProposedSchedule:updated.proposed_schedule,newScheduleTimezone:updated.schedule_timezone,reviewNote:input.note,publicationAuthorized:true}),clientIp(req)]);
  await client.query('COMMIT');return NextResponse.json({ok:true,status:'approved',publicationAuthorized:true,proposedSchedule:updated.proposed_schedule,scheduleTimezone:updated.schedule_timezone,reviewedAt:updated.reviewed_at,reviewedBy:user.username,reviewNote:input.note});
 }catch(e:any){await client.query('ROLLBACK');return NextResponse.json({error:e.message||'Reschedule failed'},{status:409})}finally{client.release()}
}
