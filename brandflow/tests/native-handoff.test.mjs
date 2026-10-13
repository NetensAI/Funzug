import test from 'node:test';
import assert from 'node:assert/strict';
import {mergeNativeHandoff,nativeHandoffEqual} from '../lib/funzug-native-handoff.mjs';
const platforms=['facebook','instagram'];
const reserved={state:'reserved',reserved_at:'2000-10-12T14:00:00+05:30',scheduled_at:'2099-10-13T19:30:00+05:30',content_hash:'a'.repeat(64),platforms,receipts:{}};
const submitting={...reserved,state:'submitting',submission_started_at:reserved.reserved_at};
const receipt=p=>({platform:p,schedule_id:`fixture-${p}`,scheduled_at:reserved.scheduled_at,content_hash:reserved.content_hash,planner_url:'https://business.facebook.com/latest/content_calendar',checked_at:reserved.reserved_at});
test('native handoff requires reservation and moves forward without releasing workflow delivery',()=>{
 assert.deepEqual(mergeNativeHandoff(null,reserved,platforms),reserved);
 assert.throws(()=>mergeNativeHandoff(null,submitting,platforms));
 assert.deepEqual(mergeNativeHandoff(reserved,submitting,platforms),submitting);
 const scheduled={...submitting,state:'scheduled',receipts:{facebook:receipt('facebook'),instagram:receipt('instagram')}};
 assert.deepEqual(mergeNativeHandoff(submitting,scheduled,platforms),scheduled);
 assert.throws(()=>mergeNativeHandoff(scheduled,submitting,platforms));
 assert.throws(()=>mergeNativeHandoff(reserved,scheduled,platforms));
});
test('native receipts bind platform content and schedule and cannot be rewritten',()=>{
 const partial={...submitting,receipts:{facebook:receipt('facebook')}};
 assert.deepEqual(mergeNativeHandoff(submitting,partial,platforms),partial);
 for(const changes of [{content_hash:'b'.repeat(64)},{scheduled_at:'2099-10-14T19:30:00+05:30'},{planner_url:'https://example.org'},{checked_at:'2099-10-14T19:30:00+05:30'},{platform:'instagram'}])assert.throws(()=>mergeNativeHandoff(submitting,{...partial,receipts:{facebook:{...receipt('facebook'),...changes}}},platforms));
 assert.throws(()=>mergeNativeHandoff(partial,{...submitting,receipts:{}},platforms));
 assert.throws(()=>mergeNativeHandoff(submitting,{...submitting,state:'scheduled',receipts:{}},platforms));
});
test('planner placeholders cannot be recorded as native Meta schedule receipts',()=>{
 const fake={...receipt('facebook'),schedule_id:'meta-planner-visible:funzug-2026-test:facebook:2099-10-13T19:30:00+05:30'};
 assert.throws(()=>mergeNativeHandoff(submitting,{...submitting,receipts:{facebook:fake}},platforms));
});
test('a verified Meta ID may promote a prior planner placeholder without changing the approved handoff',()=>{
 const placeholder=p=>({...receipt(p),schedule_id:`meta-planner-visible:funzug-test:${p}`,planner_url:'https://business.facebook.com/latest/content_calendar'});
 const previous={...submitting,state:'scheduled',receipts:{facebook:placeholder('facebook'),instagram:placeholder('instagram')}};
 const promoted=p=>({...receipt(p),schedule_id:p==='facebook'?'1519859980179026':'18121810900845217',planner_url:`https://business.facebook.com/latest/insights/object_insights/?content_id=${p==='facebook'?'1519859980179026':'18121810900845217'}`,checked_at:'2000-10-12T14:01:00+05:30'});
 const incoming={...previous,receipts:{facebook:promoted('facebook'),instagram:promoted('instagram')}};
 assert.deepEqual(mergeNativeHandoff(previous,incoming,platforms),incoming);
 for(const changes of [
  {content_hash:'b'.repeat(64)},
  {scheduled_at:'2099-10-14T19:30:00+05:30'},
  {checked_at:'2000-10-12T13:59:00+05:30'},
 ]) {
  const invalid={...incoming,receipts:{...incoming.receipts,facebook:{...incoming.receipts.facebook,...changes}}};
  assert.throws(()=>mergeNativeHandoff(previous,invalid,platforms));
 }
 const replacement={...incoming,receipts:{...incoming.receipts,facebook:{...incoming.receipts.facebook,schedule_id:'another-actual-id'}}};
 assert.throws(()=>mergeNativeHandoff(incoming,replacement,platforms));
});
test('a legacy scheduled placeholder can be corrected during partial receipt promotion',()=>{
 const placeholder=p=>({...receipt(p),schedule_id:`meta-planner-visible:funzug-legacy:${p}`,planner_url:'https://business.facebook.com/latest/content_calendar'});
 const previous={...submitting,state:'scheduled',receipts:{facebook:placeholder('facebook'),instagram:placeholder('instagram')}};
 const facebook={...receipt('facebook'),schedule_id:'1519859980179026',planner_url:'https://business.facebook.com/latest/insights/object_insights/?content_id=1519859980179026',checked_at:'2000-10-12T14:01:00+05:30'};
 const partial={...previous,state:'submitting',receipts:{facebook,instagram:placeholder('instagram')}};
 assert.deepEqual(mergeNativeHandoff(previous,partial,platforms),partial);
 const instagram={...receipt('instagram'),schedule_id:'18121810900845217',planner_url:'https://business.facebook.com/latest/insights/object_insights/?content_id=18121810900845217',checked_at:'2000-10-12T14:02:00+05:30'};
 const complete={...partial,state:'scheduled',receipts:{facebook,instagram}};
 assert.deepEqual(mergeNativeHandoff(partial,complete,platforms),complete);
 assert.throws(()=>mergeNativeHandoff(previous,{...partial,state:'scheduled'},platforms));
 const changedPlaceholder={...partial,receipts:{facebook,instagram:{...placeholder('instagram'),schedule_id:'meta-planner-visible:changed'}}};
 assert.throws(()=>mergeNativeHandoff(previous,changedPlaceholder,platforms));
 const unrelated={...previous,receipts:{facebook:receipt('facebook'),instagram:placeholder('instagram')}};
 assert.throws(()=>mergeNativeHandoff({...previous,receipts:{facebook:receipt('facebook'),instagram:receipt('instagram')}},unrelated,platforms));
});
test('JSONB key ordering cannot cause receipt conflicts or duplicate state writes',()=>{
 const prior=receipt('facebook');const reordered=Object.fromEntries(Object.entries(prior).reverse());
 assert.ok(nativeHandoffEqual(prior,reordered));
 const partial={...submitting,receipts:{facebook:prior}};
 assert.deepEqual(mergeNativeHandoff(partial,{...partial,receipts:{facebook:reordered}},platforms).receipts.facebook,reordered);
});
test('invalid native states and platform changes fail closed',()=>{
 assert.throws(()=>mergeNativeHandoff({...reserved,state:'toString'},reserved,platforms));
 assert.throws(()=>mergeNativeHandoff(reserved,{...reserved,platforms:['facebook']},platforms));
 assert.throws(()=>mergeNativeHandoff(reserved,{...reserved,content_hash:'b'.repeat(64)},platforms));
});
