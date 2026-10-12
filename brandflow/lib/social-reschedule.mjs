export const IST_ZONE='Asia/Kolkata';
export const IST_OFFSET='+05:30';

export function validateRescheduleInput(value,now=new Date()){
 if(!value||value.action!=='reschedule')return {ok:false,error:'Explicit reschedule action required'};
 if(value.scheduleTimezone!==IST_ZONE)return {ok:false,error:'Schedule timezone must be Asia/Kolkata'};
 if(value.confirmation!=='CONFIRM RESCHEDULE')return {ok:false,error:'Exact reschedule confirmation required'};
 if(typeof value.note!=='string'||value.note.trim().length<1||value.note.trim().length>4000)return {ok:false,error:'A review note between 1 and 4000 characters is required'};
 if(typeof value.proposedSchedule!=='string'||!/^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(?::[0-9]{2})?\+05:30$/.test(value.proposedSchedule))return {ok:false,error:'Schedule must include the +05:30 IST offset'};
 const date=new Date(value.proposedSchedule);if(Number.isNaN(date.getTime()))return {ok:false,error:'Invalid schedule time'};
 if(date.getTime()<=now.getTime())return {ok:false,error:'Schedule must be in the future'};
 return {ok:true,date,note:value.note.trim()};
}

export function rescheduleEligibility({authenticated,role,status,publicationAuthorized,publishedAt}){
 if(!authenticated)return {ok:false,status:401,error:'Authentication required'};
 if(role!=='admin')return {ok:false,status:403,error:'Owner access required'};
 if(status==='rejected')return {ok:false,status:409,error:'Rejected drafts cannot be rescheduled'};
 if(status!=='approved'||publicationAuthorized!==true)return {ok:false,status:409,error:'Only approved and authorized drafts can be rescheduled'};
 if(publishedAt)return {ok:false,status:409,error:'Published drafts cannot be rescheduled'};
 return {ok:true};
}

export function nextReviewedAt(previous,now=new Date()){
 const prior=new Date(previous);const result=new Date(now);
 if(Number.isNaN(prior.getTime()))throw new Error('Previous review time is invalid');
 if(result.getTime()<=prior.getTime())result.setTime(prior.getTime()+1);
 return result;
}
