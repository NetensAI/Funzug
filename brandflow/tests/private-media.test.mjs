import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {privateMediaResponse} from '../lib/private-media-response.mjs';

const bytes=Buffer.from('0123456789');
const asset={media_bytes:bytes,mime_type:'video/mp4',sha256:createHash('sha256').update(bytes).digest('hex')};
test('private previews preserve original bytes with no-store and nosniff',()=>{
 const r=privateMediaResponse(asset,null);assert.equal(r.status,200);assert.deepEqual(r.body,bytes);assert.equal(r.headers['Cache-Control'],'private, no-store');assert.equal(r.headers['X-Content-Type-Options'],'nosniff');
});
test('single ranges support video seeking without changing source media',()=>{
 for(const [range,wanted,contentRange] of [['bytes=2-5','2345','bytes 2-5/10'],['bytes=8-','89','bytes 8-9/10'],['bytes=-3','789','bytes 7-9/10'],['bytes=7-99','789','bytes 7-9/10']]){
  const r=privateMediaResponse(asset,range);assert.equal(r.status,206);assert.equal(r.body.toString(),wanted);assert.equal(r.headers['Content-Range'],contentRange);
 }
 for(const range of ['bytes=10-','bytes=3-1','bytes=-0','bytes=-','bytes=0-1,3-4','bytes=999999999999999999999-'])assert.equal(privateMediaResponse(asset,range).status,416);
});
test('incorrect hash and executable MIME types fail closed',()=>{
 for(const changed of [{sha256:'0'.repeat(64)},{mime_type:'text/html'},{media_bytes:Buffer.alloc(0)}])assert.throws(()=>privateMediaResponse({...asset,...changed},null));
});
