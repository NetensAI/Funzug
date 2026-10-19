import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {mkdtemp,rm} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {createHash} from 'node:crypto';
import {createImagePreview,cachedImagePreview} from '../lib/image-preview.mjs';

const python=process.env.BRANDFLOW_PREVIEW_PYTHON||'python3';
const available=spawnSync(python,['-c','from PIL import Image'],{windowsHide:true}).status===0;
test('real preview is small, preserves the complete image, and reuses its content cache',{skip:!available},async()=>{
 const previous=process.cwd(),cache=await mkdtemp(path.join(tmpdir(),'brandflow-preview-test-'));
 process.chdir(fileURLToPath(new URL('..',import.meta.url)));
 process.env.BRANDFLOW_PREVIEW_CACHE_DIR=cache;
 try{
  const result=spawnSync(python,['-c',"from PIL import Image; import random,sys; im=Image.frombytes('RGB',(1122,1402),random.Random(123).randbytes(1122*1402*3)); im.save(sys.stdout.buffer,'PNG')"],{maxBuffer:12*1024*1024,windowsHide:true});
  assert.equal(result.status,0);const original=result.stdout,sha=createHash('sha256').update(original).digest('hex');
  const [preview,same]=await Promise.all([createImagePreview(original,sha),createImagePreview(original,sha)]);
  assert.deepEqual(preview,same);assert.ok(preview.length<original.length/4);
  const info=spawnSync(python,['-c',"from PIL import Image; import io,sys; im=Image.open(io.BytesIO(sys.stdin.buffer.read())); print(im.format,im.width,im.height)"],{input:preview,windowsHide:true});
  assert.equal(info.stdout.toString().trim(),'WEBP 560 700');
  assert.deepEqual(await cachedImagePreview(sha),preview);
  assert.equal(createHash('sha256').update(original).digest('hex'),sha);
  await assert.rejects(createImagePreview(Buffer.from('changed'),'0'.repeat(64)),/Image changed/);
 }finally{process.chdir(previous);delete process.env.BRANDFLOW_PREVIEW_CACHE_DIR;await rm(cache,{recursive:true,force:true});}
});
