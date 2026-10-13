import test from 'node:test';
import assert from 'node:assert/strict';
import {createHash} from 'node:crypto';
import {orderedMediaManifest} from '../lib/ordered-media-manifest.mjs';

function fixture() {
  const row = {id:'private-draft',media_format:'carousel',headline:'Headline',caption:'Caption',claims:[],evidence_sources:[],platforms:['facebook','instagram']};
  const assets = ['first','second'].map((value,index) => {
    const bytes = Buffer.from(value);
    return {draft_id:row.id,asset_index:index,media_bytes:bytes,sha256:createHash('sha256').update(bytes).digest('hex'),mime_type:'image/png',width:1122,height:1402,duration_ms:null};
  });
  return {row,assets};
}
test('database manifest binds exact private bytes and displayed order', () => {
  const {row,assets} = fixture();
  const package1 = orderedMediaManifest(row,assets);
  assert.equal(package1.draft.media[0].data,assets[0].media_bytes.toString('base64'));
  const reversed = assets.toReversed().map((asset,index)=>({...asset,asset_index:index}));
  assert.notEqual(package1.contentHash,orderedMediaManifest(row,reversed).contentHash);
  assert.notEqual(package1.contentHash,orderedMediaManifest({...row,caption:'Changed'},assets).contentHash);
});
test('rejects cross-draft, gaps, absent bytes, forged checksums and duplicates', () => {
  for (const mutation of [
    asset=>{asset.draft_id='other'}, asset=>{asset.asset_index=3},
    asset=>{asset.media_bytes=null}, asset=>{asset.sha256='0'.repeat(64)},
    asset=>{asset.width=1123},
  ]) {
    const {row,assets}=fixture(); mutation(assets[1]);
    assert.throws(()=>orderedMediaManifest(row,assets));
  }
  const {row,assets}=fixture();
  assets[1]={...assets[0],asset_index:1};
  assert.throws(()=>orderedMediaManifest(row,assets),/Duplicate/);
});
test('reel package binds duration and refuses image MIME', () => {
  const {row,assets}=fixture(); row.media_format='reel'; assets.splice(1);
  assert.throws(()=>orderedMediaManifest(row,assets));
  Object.assign(assets[0],{mime_type:'video/mp4',duration_ms:30000});
  const before=orderedMediaManifest(row,assets).contentHash;
  assets[0].duration_ms++;
  assert.notEqual(before,orderedMediaManifest(row,assets).contentHash);
  assets[0].duration_ms=180001;
  assert.throws(()=>orderedMediaManifest(row,assets));
});
