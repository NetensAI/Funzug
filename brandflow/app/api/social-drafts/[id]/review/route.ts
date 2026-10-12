import {NextResponse} from 'next/server';
import {z} from 'zod';
import {db} from '@/lib/db';
import {getSession} from '@/lib/auth';
import {clientIp,sameOrigin} from '@/lib/security';

const schema=z.discriminatedUnion('action',[
 z.object({action:z.literal('approve'),approvalConfirmed:z.literal(true),proposedSchedule:z.string().datetime({offset:true})}).strict(),
 z.object({action:z.literal('reject')}).strict()
]);

function offsetMatchesZone(timestamp:string,timeZone:string){
 const supplied=timestamp.match(/(Z|[+-]\d{2}:\d{2})$/)?.[1];if(!supplied)return false;
 const part=new Intl.DateTimeFormat('en-US',{timeZone,timeZoneName:'longOffset'}).formatToParts(new Date(timestamp)).find(x=>x.type==='timeZoneName')?.value;
 const expected=part?.replace('GMT','')||'';return supplied===(expected||'Z')||(supplied==='Z'&&expected==='+00:00');
}

export async function POST(req:Request,{params}:{params:{id:string}}){
 if(!sameOrigin(req))return NextResponse.json({error:'Invalid origin'},{status:403});
 const session=await getSession();if(session?.role!=='admin'||!session.sub)return NextResponse.json({error:'Administrator access required'},{status:403});
 const parsed=schema.safeParse(await req.json().catch(()=>null));if(!parsed.success)return NextResponse.json({error:'Select an IST schedule and confirm approval'},{status:400});
 const approved=parsed.data.action==='approve';
 let schedule:Date|null=null;let note='Rejected in review.';
 if(parsed.data.action==='approve'){
  const input=parsed.data.proposedSchedule;
  schedule=new Date(input);
  if(!Number.isFinite(schedule.getTime())||schedule.getTime()<=Date.now())return NextResponse.json({error:'Choose a future date and time'},{status:400});
  if(!offsetMatchesZone(input,'Asia/Kolkata'))return NextResponse.json({error:'Schedule must use India Standard Time (IST)'},{status:400});
  const formatted=new Intl.DateTimeFormat('en-IN',{timeZone:'Asia/Kolkata',dateStyle:'medium',timeStyle:'short'}).format(schedule);
  note=`Approved for scheduled publishing at ${formatted} IST`;
 }
 const client=await db.connect();try{
  await client.query('BEGIN');
  const {rows:[user]}=await client.query('SELECT username,active,role FROM users WHERE id=$1 FOR UPDATE',[session.sub]);if(!user?.active||user.role!=='admin')throw new Error('Administrator access required');
  const checks=approved?{approvalConfirmed:true}:{};
  const {rows:[draft]}=await client.query(`UPDATE social_post_drafts SET status=$2,proposed_schedule=COALESCE($7,proposed_schedule),schedule_timezone=CASE WHEN $6 THEN 'Asia/Kolkata' ELSE schedule_timezone END,review_checks=$3::jsonb,review_note=$4,reviewed_by=$5,reviewed_at=now(),publication_authorized=$6,updated_at=now() WHERE id=$1 AND status='pending_review' RETURNING id,brand_id,status,proposed_schedule,schedule_timezone`,[params.id,approved?'approved':'rejected',JSON.stringify(checks),note,session.sub,approved,schedule]);
  if(!draft)throw new Error('Draft not found or already reviewed');
  await client.query('INSERT INTO audit_logs(actor_user_id,actor_username,action,target_type,target_id,details,ip_address) VALUES($1,$2,$3,$4,$5,$6::jsonb,$7)',[session.sub,user.username,approved?'social_draft.approved':'social_draft.rejected','social_post_draft',draft.id,JSON.stringify({brandId:draft.brand_id,reviewNote:note,approvalConfirmed:approved,proposedSchedule:draft.proposed_schedule,scheduleTimezone:draft.schedule_timezone,publicationAuthorized:approved}),clientIp(req)]);
  await client.query('COMMIT');return NextResponse.json({ok:true,status:draft.status,publicationAuthorized:approved,proposedSchedule:draft.proposed_schedule,scheduleTimezone:draft.schedule_timezone});
 }catch(e:any){await client.query('ROLLBACK');const status=String(e.message).includes('access')?403:409;return NextResponse.json({error:e.message||'Review failed'},{status})}finally{client.release()}
}
