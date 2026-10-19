'use client';
import {useState} from 'react';
import {useRouter} from 'next/navigation';
import IstScheduleInput from '@/components/IstScheduleInput';
import {toIstLocalValue} from '@/lib/ist-dates.mjs';

const istLocal=toIstLocalValue;
export default function SocialDraftReschedule({id,currentSchedule}:{id:string,currentSchedule:string}){
 const router=useRouter();const [open,setOpen]=useState(false);const [local,setLocal]=useState(istLocal(currentSchedule));const [note,setNote]=useState('');const [confirmed,setConfirmed]=useState(false);const [busy,setBusy]=useState(false);const [error,setError]=useState('');
 async function submit(){
  setBusy(true);setError('');
  try{
   const proposedSchedule=`${local}:00+05:30`;
   const res=await fetch(`/api/social-drafts/${id}/reschedule`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify({action:'reschedule',proposedSchedule,scheduleTimezone:'Asia/Kolkata',note,confirmation:confirmed?'CONFIRM RESCHEDULE':''})});
   if(res.ok){setOpen(false);router.refresh()}
   else{const data=await res.json().catch(()=>null);setError(data?.error||'Reschedule failed. Refresh to check the saved time before retrying.')}
  }catch{setError('The request could not be confirmed. Refresh to check the saved time before retrying.')}
  finally{setBusy(false)}
 }
 if(!open)return <button className="btn secondary" onClick={()=>setOpen(true)}>Reschedule</button>;
 return <div className="reviewbox stack"><strong>Reschedule approved post</strong><IstScheduleInput label="New future date and time (IST)" value={local} onChange={setLocal}/><label className="label">Reschedule note<textarea className="textarea" value={note} onChange={e=>setNote(e.target.value)} required/></label><label><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/> Confirm this changes the authorized publication time to the selected IST time</label><div className="warning">This keeps the existing approval and authorization. BrandFlow will not upload, schedule through Meta, or publish the post.</div>{error&&<div className="error">{error}</div>}<div className="row"><button className="btn" disabled={busy||!local||!note.trim()||!confirmed} onClick={submit}>Confirm reschedule</button><button className="btn secondary" disabled={busy} onClick={()=>setOpen(false)}>Cancel</button></div></div>
}
