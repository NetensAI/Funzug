import test from 'node:test';
import assert from 'node:assert/strict';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {decodeOrderedMedia} from '../lib/decode-ordered-media.mjs';
import {reviewedMediaHash} from '../lib/funzug-content-hash.mjs';
const cwd=fileURLToPath(new URL('../../',import.meta.url));
const python=process.env.FUNZUG_TEST_PYTHON||'python3';
function fixture(){
 const data=JSON.parse(execFileSync(python,['-c',"import io,json,base64;from PIL import Image;result=[]\nfor color in ['red','blue']:\n b=io.BytesIO();Image.new('RGB',(40,50),color).save(b,format='PNG');result.append(base64.b64encode(b.getvalue()).decode())\nprint(json.dumps(result))"],{encoding:'utf8'}));
 return {format:'carousel',headline:'Reviewed',caption:'Caption',claims:[],sources:[],platforms:['facebook'],media:data.map(data=>({mimeType:'image/png',width:40,height:50,data}))};
}
test('dashboard subprocess decodes private bytes and matches the Node fingerprint',async()=>{
 const draft=fixture();assert.equal(await decodeOrderedMedia(draft,{cwd,python}),reviewedMediaHash(draft));
});
test('subprocess rejects truncated media without exposing its stderr',async()=>{
 const draft=fixture();draft.media[0].data=Buffer.from('secret-value-not-a-valid-image').toString('base64');
 await assert.rejects(decodeOrderedMedia(draft,{cwd,python}),error=>error.message==='Ordered media decode failed');
});
test('missing runtime is a rejection rather than trusting declared dimensions',async()=>{
 await assert.rejects(decodeOrderedMedia(fixture(),{cwd,python:'funzug-missing-python-runtime'}),/Ordered media decode failed/);
});
