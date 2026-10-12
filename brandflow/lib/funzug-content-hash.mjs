import {createHash} from 'node:crypto';
function canonical(value){
  if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
  if(value!==null&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
  return JSON.stringify(value);
}
export function contentHash(value){return createHash('sha256').update(canonical(value),'utf8').digest('hex')}
export function draftContentHash(row){
  if(!Buffer.isBuffer(row.image_bytes))return null;
  return contentHash({headline:row.headline,caption:row.caption,claims:row.claims,sources:row.evidence_sources,platforms:row.platforms,imageMimeType:row.image_mime_type,imageSha256:createHash('sha256').update(row.image_bytes).digest('hex')});
}
