import test from 'node:test';
import assert from 'node:assert/strict';
import {storeOrderedDraft} from '../lib/store-ordered-draft.mjs';
const draft={externalId:'draft',format:'carousel',headline:'Headline',caption:'Caption',claims:[],sources:[],platforms:['facebook'],proposedSchedule:'2099-01-01T12:00:00+05:30',scheduleTimezone:'Asia/Kolkata',media:['one','two'].map(data=>({mimeType:'image/png',width:40,height:50,data:Buffer.from(data).toString('base64')}))};
function fixture(existing){
 const calls=[];return {calls,client:{async query(sql,args){calls.push({sql,args});return {rows:sql.startsWith('SELECT')?(existing?[existing]:[]):sql.startsWith('INSERT INTO social_post_drafts')?[{id:'parent'}]:[]};}}};
}
test('new mixed draft has no fake image and stores exact assets in order',async()=>{
 const {client,calls}=fixture();const result=await storeOrderedDraft(client,'brand','batch',draft);
 assert.equal(result.status,'pending_review');assert.match(calls[1].sql,/NULL,NULL,NULL/);
 assert.match(calls[1].sql,/media_format/);
 const inserts=calls.filter(c=>c.sql.startsWith('INSERT INTO social_post_media_assets'));
 assert.deepEqual(inserts.map(c=>c.args[1]),[0,1]);
 assert.deepEqual(inserts.map(c=>c.args[6].toString()),['one','two']);
 assert.ok(calls.every(c=>!c.sql.includes('publication_authorized')));
});
test('pending replacement locks parent before deleting and inserting assets',async()=>{
 const {client,calls}=fixture({id:'parent',status:'pending_review',media_format:'carousel'});
 await storeOrderedDraft(client,'brand','batch',draft);
 assert.match(calls[0].sql,/FOR UPDATE/);assert.match(calls[1].sql,/DELETE FROM social_post_media_assets/);
 assert.match(calls[2].sql,/status='pending_review'/);
});
test('reviewed content and existing format cannot be overwritten',async()=>{
 for(const existing of [{id:'parent',status:'approved',media_format:'carousel'},{id:'parent',status:'rejected',media_format:'carousel'},{id:'parent',status:'pending_review',media_format:'image'}]){
  const {client,calls}=fixture(existing);await assert.rejects(storeOrderedDraft(client,'brand','batch',draft));assert.equal(calls.length,1);
 }
});
