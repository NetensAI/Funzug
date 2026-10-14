import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {storedOrderedMediaHash,reviewedMediaHash,draftContentHash} from '../lib/funzug-content-hash.mjs';
function fixture(format='carousel'){
 const media=['first','second'].slice(0,format==='reel'?1:2).map(data=>({mimeType:format==='reel'?'video/mp4':'image/png',width:40,height:50,data:Buffer.from(data).toString('base64'),...(format==='reel'?{durationMs:1000}:{})}));
 const draft={headline:'Headline',caption:'Caption',claims:[],sources:[],platforms:['facebook','instagram'],format,media};
 const row={...draft,media_format:format,evidence_sources:draft.sources,ordered_media:media.map((a,index)=>({index,mimeType:a.mimeType,width:a.width,height:a.height,durationMs:a.durationMs??null,sha256:createHash('sha256').update(Buffer.from(a.data,'base64')).digest('hex')}))};
 return {draft,row};
}
test('database checksum manifests equal exact-byte review fingerprints',()=>{
 for(const kind of ['carousel','reel']){const {draft,row}=fixture(kind);assert.equal(storedOrderedMediaHash(row),reviewedMediaHash(draft));assert.equal(draftContentHash(row),reviewedMediaHash(draft));}
});
test('invalid stored manifest returns no usable approval fingerprint',()=>{
 for(const mutate of [r=>r.ordered_media.reverse(),r=>r.ordered_media[0].sha256='untrusted',r=>r.ordered_media[0].width=41,r=>r.ordered_media[1].sha256=r.ordered_media[0].sha256,r=>r.ordered_media=[],r=>r.ordered_media[0].durationMs=1000]){
  const {row}=fixture();mutate(row);assert.equal(draftContentHash(row),null);assert.throws(()=>storedOrderedMediaHash(row));
 }
});
