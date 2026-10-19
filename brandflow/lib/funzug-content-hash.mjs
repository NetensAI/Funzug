import {createHash} from 'node:crypto';
function canonical(value){
  if(Array.isArray(value))return '['+value.map(canonical).join(',')+']';
  if(value!==null&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+canonical(value[k])).join(',')+'}';
  return JSON.stringify(value);
}
export function contentHash(value){return createHash('sha256').update(canonical(value),'utf8').digest('hex')}
// New formats remain disabled at the integration boundary until review and
// native delivery are implemented. This binds every asset in its reviewed order.
export function reviewedMediaHash(draft){
  const content=Object.fromEntries(['headline','caption','claims','sources','platforms'].map(key=>[key,draft[key]]));
  const kind=draft.format??'image';
  if(kind==='image'){
    const bytes=Buffer.from(draft.image.data,'base64');
    return contentHash({...content,imageMimeType:draft.image.mimeType,imageSha256:createHash('sha256').update(bytes).digest('hex')});
  }
  const assets=draft.media;
  if(!['carousel','reel'].includes(kind)||!Array.isArray(assets))throw Error('Unsupported reviewed media format');
  if(kind==='carousel'?(assets.length<2||assets.length>10):assets.length!==1)throw Error('Invalid reviewed media count');
  const media=assets.map((asset,index)=>{
    if(!asset||typeof asset!=='object')throw Error('Invalid reviewed media asset');
    const {mimeType,width,height,data}=asset;
    if(![width,height].every(value=>Number.isSafeInteger(value)&&value>0))throw Error('Invalid reviewed media dimensions');
    if(width>=height||Math.abs(width*5-height*4)>2)throw Error('Reviewed media must be portrait 4:5');
    if(!(kind==='carousel'?['image/png','image/jpeg']:['video/mp4']).includes(mimeType))throw Error('Invalid reviewed media MIME type');
    if(typeof data!=='string'||! /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(data))throw Error('Invalid reviewed media encoding');
    const bytes=Buffer.from(data,'base64');
    if(!bytes.length||bytes.length>(kind==='carousel'?12:100)*1024*1024)throw Error('Invalid reviewed media byte count');
    const entry={index,mimeType,width,height,sha256:createHash('sha256').update(bytes).digest('hex')};
    if(kind==='reel'){
      if(!Number.isSafeInteger(asset.durationMs)||asset.durationMs<1||asset.durationMs>180000)throw Error('Invalid reviewed reel duration');
      entry.durationMs=asset.durationMs;
    }
    return entry;
  });
  if(new Set(media.map(asset=>asset.sha256)).size!==media.length)throw Error('Duplicate reviewed media assets');
  return contentHash({...content,format:kind,media});
}
export function draftContentHash(row){
  if(row.media_format&&row.media_format!=='image'){
    try{return storedOrderedMediaHash(row)}catch{return null}
  }
  if(!Buffer.isBuffer(row.image_bytes))return null;
  return contentHash({headline:row.headline,caption:row.caption,claims:row.claims,sources:row.evidence_sources,platforms:row.platforms,imageMimeType:row.image_mime_type,imageSha256:createHash('sha256').update(row.image_bytes).digest('hex')});
}

// Only use a checksum selected from the database alongside the reviewed fields.
// This produces exactly the same approval fingerprint without transferring BLOBs.
export function draftContentHashFromChecksum(row){
  if(row.media_format&&row.media_format!=='image')return draftContentHash(row);
  if(typeof row.image_sha256!=='string'||! /^[0-9a-f]{64}$/.test(row.image_sha256))return null;
  return contentHash({headline:row.headline,caption:row.caption,claims:row.claims,sources:row.evidence_sources,platforms:row.platforms,imageMimeType:row.image_mime_type,imageSha256:row.image_sha256});
}

// Database-generated checksums from one parent/asset snapshot, never client hashes.
export function storedOrderedMediaHash(row){
  const kind=row.media_format,assets=row.ordered_media;
  if(!['carousel','reel'].includes(kind)||!Array.isArray(assets))throw Error('Missing stored media manifest');
  if(kind==='carousel'?(assets.length<2||assets.length>10):assets.length!==1)throw Error('Invalid stored media count');
  const media=assets.map((asset,index)=>{
    if(asset.index!==index||typeof asset.sha256!=='string'||!/^[0-9a-f]{64}$/.test(asset.sha256))throw Error('Invalid stored media checksum or index');
    if(![asset.width,asset.height].every(v=>Number.isSafeInteger(v)&&v>0)||asset.width>=asset.height||Math.abs(asset.width*5-asset.height*4)>2)throw Error('Invalid stored media dimensions');
    if(!(kind==='carousel'?['image/png','image/jpeg']:['video/mp4']).includes(asset.mimeType))throw Error('Invalid stored MIME type');
    const entry={index,mimeType:asset.mimeType,width:asset.width,height:asset.height,sha256:asset.sha256};
    if(kind==='reel'){
      if(!Number.isSafeInteger(asset.durationMs)||asset.durationMs<1||asset.durationMs>180000)throw Error('Invalid stored duration');
      entry.durationMs=asset.durationMs;
    }else if(asset.durationMs!=null)throw Error('Image duration is invalid');
    return entry;
  });
  if(new Set(media.map(a=>a.sha256)).size!==media.length)throw Error('Duplicate stored media');
  return contentHash({headline:row.headline,caption:row.caption,claims:row.claims,sources:row.evidence_sources,platforms:row.platforms,format:kind,media});
}
