import {createHash, randomUUID} from 'node:crypto';
import {readFile, writeFile, mkdir, rename, readdir, unlink} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {spawn} from 'node:child_process';

const version='preview-v1';
const pending=new Map();
let active=0;
const waiting=[];
const cacheDir=()=>process.env.BRANDFLOW_PREVIEW_CACHE_DIR||path.join(tmpdir(),'brandflow-image-previews');
const cachePath=sha=>{
 if(typeof sha!=='string'||! /^[0-9a-f]{64}$/.test(sha))throw Error('Invalid preview identity');
 return path.join(cacheDir(),`${version}-${sha}.webp`);
};
export const imagePreviewHeaders=sha=>({
 'Content-Type':'image/webp','Cache-Control':'private, no-cache',
 'ETag':`"${version}-${sha}"`,'Vary':'Cookie','X-Content-Type-Options':'nosniff',
});
export function etagMatches(header,etag){return typeof header==='string'&&header.split(',').some(x=>x.trim()===etag||x.trim()===`W/${etag}`);}
export async function cachedImagePreview(sha){
 try{return await readFile(cachePath(sha));}catch(e){if(e.code==='ENOENT')return null;throw e;}
}
async function render(bytes){
 if(active>=2)await new Promise(resolve=>waiting.push(resolve));else active++;
 try{return await new Promise((resolve,reject)=>{
  const child=spawn(process.env.BRANDFLOW_PREVIEW_PYTHON||'python3',[path.join(process.cwd(),'scripts','image_preview.py')],{env:{PATH:process.env.PATH,...(process.env.SystemRoot?{SystemRoot:process.env.SystemRoot}:{})},windowsHide:true,stdio:['pipe','pipe','pipe']});
  const chunks=[];let size=0;let settled=false;
  const finish=(error,result)=>{if(settled)return;settled=true;clearTimeout(timer);error?reject(error):resolve(result);};
  const timer=setTimeout(()=>{child.kill();finish(Error('Preview generation timed out'));},15000);
  child.on('error',()=>finish(Error('Preview generator unavailable')));
  child.stdin.on('error',()=>{});
  child.stderr.resume();
  child.stdout.on('data',chunk=>{size+=chunk.length;if(size>1024*1024){child.kill();finish(Error('Preview exceeds limit'));}else chunks.push(chunk);});
  child.on('close',code=>code===0&&size?finish(null,Buffer.concat(chunks)):finish(Error('Preview generation failed')));
  child.stdin.end(bytes);
 });}finally{const next=waiting.shift();if(next)next();else active--;}
}
export async function createImagePreview(bytes,sha){
 if(!Buffer.isBuffer(bytes)||!bytes.length||bytes.length>12*1024*1024||createHash('sha256').update(bytes).digest('hex')!==sha)throw Error('Image changed while loading');
 if(pending.has(sha))return pending.get(sha);
 const task=(async()=>{
  const cached=await cachedImagePreview(sha);if(cached)return cached;
  const preview=await render(bytes);
  await mkdir(cacheDir(),{recursive:true,mode:0o700});
  const target=cachePath(sha),temporary=`${target}.${randomUUID()}.tmp`;
  try{await writeFile(temporary,preview,{mode:0o600,flag:'wx'});await rename(temporary,target);}finally{await unlink(temporary).catch(()=>{});}
  // Bound disposable cache growth; original files and database rows are untouched.
  const files=(await readdir(cacheDir())).filter(f=>/^preview-v1-[0-9a-f]{64}\.webp$/.test(f));
  if(files.length>512)await Promise.all(files.filter(f=>f!==path.basename(target)).slice(0,files.length-512).map(f=>unlink(path.join(cacheDir(),f)).catch(()=>{})));
  return preview;
 })();
 pending.set(sha,task);
 try{return await task;}finally{pending.delete(sha);}
}
