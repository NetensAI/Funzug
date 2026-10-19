'use client';
import {useRef,useState} from 'react';
import {displayLocalDate,parseDisplayDate,localSchedule} from '@/lib/ist-dates.mjs';

export default function IstScheduleInput({label,value,onChange,name,required=true}:{label:string;value:string;onChange:(value:string)=>void;name?:string;required?:boolean}){
 const [dateText,setDateText]=useState(()=>displayLocalDate(value.slice(0,10)));
 const [time,setTime]=useState(()=>value.slice(11,16));
 const picker=useRef<HTMLInputElement>(null),dateInput=useRef<HTMLInputElement>(null);
 function changeDate(text:string){
  setDateText(text);
  dateInput.current?.setCustomValidity(text&&!parseDisplayDate(text)?'Enter a valid date as DD/MM/YYYY.':'');
  onChange(localSchedule(text,time));
 }
 return <fieldset className="stack" style={{border:0,padding:0,margin:0,minWidth:0}}>
  <legend className="label">{label}</legend>
  <div className="row" style={{alignItems:'end',flexWrap:'wrap'}}>
   <label className="label" style={{flex:'1 1 170px'}}>Date (DD/MM/YYYY)
    <span style={{display:'flex',position:'relative',gap:6}}>
     <input ref={dateInput} className="input" type="text" inputMode="numeric" placeholder="DD/MM/YYYY" pattern="[0-9]{2}/[0-9]{2}/[0-9]{4}" maxLength={10} value={dateText} onChange={e=>changeDate(e.target.value)} required={required||Boolean(time)} style={{minWidth:0}}/>
     <button type="button" className="btn secondary" aria-label="Choose date from calendar" title="Choose date" onClick={()=>{if(picker.current?.showPicker)picker.current.showPicker();else picker.current?.click();}}>📅</button>
     <input ref={picker} type="date" aria-hidden="true" tabIndex={-1} value={parseDisplayDate(dateText)||''} onChange={e=>changeDate(displayLocalDate(e.target.value))} style={{position:'absolute',width:1,height:1,opacity:0,pointerEvents:'none',right:0,bottom:0}}/>
    </span>
   </label>
   <label className="label" style={{flex:'1 1 120px'}}>Time (IST)
    <input className="input" type="time" value={time} onChange={e=>{setTime(e.target.value);onChange(localSchedule(dateText,e.target.value));}} required={required||Boolean(dateText)}/>
   </label>
  </div>
  {name&&<input type="hidden" name={name} value={value}/>}
 </fieldset>;
}
