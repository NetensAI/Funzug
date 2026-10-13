import {spawn} from 'node:child_process';
import {reviewedMediaHash} from './funzug-content-hash.mjs';

export async function decodeOrderedMedia(draft, {cwd=process.cwd(), python='python3'}={}) {
  const expected=reviewedMediaHash(draft);
  const input=JSON.stringify(draft);
  if(Buffer.byteLength(input)>140*1024*1024)throw Error('Ordered media packet too large');
  return await new Promise((resolve,reject)=>{
    // Do not inherit application, database, Meta or GitHub secrets.
    const child=spawn(python,['-m','scripts.validate_ordered_media'],{
      cwd,env:{PATH:process.env.PATH||'',LANG:'C.UTF-8'},stdio:['pipe','pipe','pipe'],shell:false,
    });
    let output='',finished=false;
    const finish=(error)=>{
      if(finished)return;finished=true;clearTimeout(timer);
      if(error){child.kill('SIGKILL');reject(Error('Ordered media decode failed'));}
      else resolve(expected);
    };
    const timer=setTimeout(()=>finish(true),90000);
    child.on('error',()=>finish(true));
    child.stdin.on('error',()=>finish(true));
    child.stdout.on('data',chunk=>{
      output+=chunk.toString('utf8');if(output.length>128)finish(true);
    });
    child.stderr.resume();
    child.on('close',code=>finish(code!==0||output.trim()!==expected));
    child.stdin.end(input);
  });
}
