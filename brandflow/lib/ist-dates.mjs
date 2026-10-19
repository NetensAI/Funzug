export function toIstLocalValue(value){
 if(!value)return '';
 const date=new Date(value);if(Number.isNaN(date.getTime()))return '';
 const parts=new Intl.DateTimeFormat('en-GB',{timeZone:'Asia/Kolkata',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hourCycle:'h23'}).formatToParts(date);
 const get=type=>parts.find(p=>p.type===type)?.value||'';
 return `${get('year')}-${get('month')}-${get('day')}T${get('hour')}:${get('minute')}`;
}
export function displayLocalDate(iso){
 const match=/^(\d{4})-(\d{2})-(\d{2})$/.exec(iso||'');
 return match?`${match[3]}/${match[2]}/${match[1]}`:'';
}
export function parseDisplayDate(value){
 const match=/^(\d{2})\/(\d{2})\/(\d{4})$/.exec(value||'');if(!match)return null;
 const day=Number(match[1]),month=Number(match[2]),year=Number(match[3]);
 if(year<1000||year>9999)return null;
 const date=new Date(Date.UTC(year,month-1,day));
 if(date.getUTCFullYear()!==year||date.getUTCMonth()!==month-1||date.getUTCDate()!==day)return null;
 return `${match[3]}-${match[2]}-${match[1]}`;
}
export function localSchedule(dateText,time){
 const date=parseDisplayDate(dateText);
 return date&&/^(?:[01]\d|2[0-3]):[0-5]\d$/.test(time||'')?`${date}T${time}`:'';
}
export function formatIstDateTime(value){
 const local=toIstLocalValue(value);return local?`${displayLocalDate(local.slice(0,10))} ${local.slice(11,16)}`:'';
}
