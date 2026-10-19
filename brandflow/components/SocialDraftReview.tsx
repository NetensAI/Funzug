'use client';

import {useState} from 'react';
import {useRouter} from 'next/navigation';
import IstScheduleInput from '@/components/IstScheduleInput';
import {toIstLocalValue} from '@/lib/ist-dates.mjs';


export default function SocialDraftReview({id,initialSchedule,reviewedContentHash}:{id:string;initialSchedule:string;reviewedContentHash:string}){
 const router=useRouter();
 const [approved,setApproved]=useState(false);
 const [schedule,setSchedule]=useState(()=>toIstLocalValue(initialSchedule));
 const [busy,setBusy]=useState(false);
 const [error,setError]=useState('');

 async function submit(action:'approve'|'reject'){
  setBusy(true);setError('');
  const body=action==='approve'?{action,approvalConfirmed:approved,proposedSchedule:`${schedule}:00+05:30`,reviewedContentHash}:{action};
  try{
   const res=await fetch(`/api/social-drafts/${id}/review`,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
   const data=await res.json();
   if(res.ok)router.refresh();else setError(data.error||'Review failed');
  }catch{setError('Review request failed. Please try again.');}
  finally{setBusy(false);}
 }

 return <div className="reviewbox stack">
  <IstScheduleInput label="Schedule date and time (IST)" value={schedule} onChange={setSchedule}/>
  <label><input type="checkbox" checked={approved} onChange={e=>setApproved(e.target.checked)}/> I approve this post for scheduled publishing</label>
  <div className="warning">Approving authorizes the reviewed media to be uploaded to Meta and published at the selected IST time. It will not publish immediately.</div>
  {error&&<div className="error">{error}</div>}
  <div className="row"><button className="btn" disabled={busy||!approved||!schedule} onClick={()=>submit('approve')}>Approve</button><button className="btn danger" disabled={busy} onClick={()=>submit('reject')}>Reject</button></div>
 </div>;
}
