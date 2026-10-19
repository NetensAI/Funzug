import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {createHash} from 'node:crypto';
import ts from 'typescript';
import {draftContentHash,draftContentHashFromChecksum} from '../lib/funzug-content-hash.mjs';
import {imagePreviewHeaders,etagMatches} from '../lib/image-preview.mjs';

test('database checksum yields the identical approval fingerprint without original bytes',()=>{
 const image_bytes=Buffer.from('exact original bytes');
 const row={headline:'Headline',caption:'Unicode caption: Moon 🌙',claims:[{text:'Claim'}],evidence_sources:[],platforms:['facebook','instagram'],image_mime_type:'image/png',image_bytes};
 const {image_bytes:discard,...metadata}=row;
 metadata.image_sha256=createHash('sha256').update(image_bytes).digest('hex');
 assert.equal(draftContentHashFromChecksum(metadata),draftContentHash(row));
 assert.notEqual(draftContentHashFromChecksum({...metadata,caption:'Changed'}),draftContentHash(row));
 assert.equal(draftContentHashFromChecksum({...metadata,image_sha256:null}),null);
});

const original=Buffer.from('original-image');
const sha=createHash('sha256').update(original).digest('hex');
const id='11111111-1111-4111-8111-111111111111';
function imageRoute({session={sub:'owner',role:'admin'},active=true,cache=Buffer.from('webp-preview')}={}){
 const calls=[];
 class Response{constructor(body,options={}){this.body=body;this.status=options.status||200;this.headers=options.headers;}static json(body,options){return new Response(body,options)}static redirect(url,status){return new Response(url,{status})}}
 const deps={
  'next/server':{NextResponse:Response},'node:crypto':{createHash},
  '@/lib/auth':{getSession:async()=>session},
  '@/lib/db':{db:{query:async(sql)=>{calls.push(sql);return {rows:!active?[]:sql.startsWith('SELECT image_bytes')?[{image_bytes:original}]:[{image_sha256:sha,image_mime_type:'image/png'}]};}}},
  '@/lib/image-preview.mjs':{imagePreviewHeaders,etagMatches,cachedImagePreview:async()=>cache,createImagePreview:async()=>Buffer.from('new-preview')},
 };
 const exports={};const source=fs.readFileSync(new URL('../app/api/social-drafts/[id]/image/route.ts',import.meta.url),'utf8');
 const compiled=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 vm.runInNewContext(compiled,{exports,Buffer,URL,require:name=>deps[name]});
 return {calls,send:(query='',headers={})=>exports.GET(new Request('https://review.example/api/image'+query,{headers}),{params:{id}})};
}
test('cached and conditional images still require a current authorized session',async()=>{
 const headers={'if-none-match':`"preview-v1-${sha}"`};
 const signedOut=imageRoute({session:null});assert.equal((await signedOut.send('?preview=1',headers)).status,401);assert.equal(signedOut.calls.length,0);
 const revoked=imageRoute({active:false});assert.equal((await revoked.send('?preview=1',headers)).status,404);
 const valid=imageRoute();const r=await valid.send('?preview=1',headers);assert.equal(r.status,304);assert.equal(valid.calls.length,1);assert.equal(r.headers['Cache-Control'],'private, no-cache');
});
test('warm previews avoid original BLOB fetch; original link preserves exact bytes',async()=>{
 const preview=imageRoute();const r=await preview.send('?preview=1&v='+sha);assert.equal(r.body.byteLength,12);assert.equal(preview.calls.length,1);
 const full=imageRoute();const f=await full.send('?v='+sha);assert.deepEqual(Buffer.from(f.body),original);assert.equal(full.calls.length,2);
 const stale=imageRoute();assert.equal((await stale.send('?preview=1&v='+'0'.repeat(64))).status,409);assert.equal(stale.calls.length,1);
});
