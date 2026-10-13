import test from 'node:test';
import assert from 'node:assert/strict';
import {reviewedMediaHash} from '../lib/funzug-content-hash.mjs';

function fixture(){return {headline:'Reviewed',caption:'Caption',claims:[],sources:[],platforms:['facebook','instagram'],format:'carousel',media:['first','second'].map(value=>({mimeType:'image/png',width:1122,height:1402,data:Buffer.from(value).toString('base64')}))}}
test('ordered assets are bound and duplicate or invalid assets rejected',()=>{
 const draft=fixture();const before=reviewedMediaHash(draft);
 draft.media.reverse();assert.notEqual(before,reviewedMediaHash(draft));
 for(const change of [{width:true},{height:1122},{mimeType:'text/plain'},{data:'invalid!'}]){
  const bad=fixture();Object.assign(bad.media[0],change);assert.throws(()=>reviewedMediaHash(bad));
 }
 const duplicate=fixture();duplicate.media[1]={...duplicate.media[0]};assert.throws(()=>reviewedMediaHash(duplicate),/Duplicate/);
});
test('reel duration changes invalidate approval and invalid counts are rejected',()=>{
 const draft=fixture();draft.format='reel';draft.media=[{...draft.media[0],mimeType:'video/mp4',durationMs:30000}];
 const before=reviewedMediaHash(draft);draft.media[0].durationMs++;assert.notEqual(before,reviewedMediaHash(draft));
 draft.media[0].durationMs=0;assert.throws(()=>reviewedMediaHash(draft));
 for(const media of [[],fixture().media.slice(0,1),fixture().media.concat(fixture().media,fixture().media,fixture().media,fixture().media,fixture().media)])assert.throws(()=>reviewedMediaHash({...fixture(),media}));
});
