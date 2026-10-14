import {createHash} from 'node:crypto';

export function privateMediaResponse(asset,range){
 const bytes=asset?.media_bytes;
 if(!Buffer.isBuffer(bytes)||!bytes.length||bytes.length>100*1024*1024||!['image/png','image/jpeg','video/mp4'].includes(asset.mime_type)||asset.sha256!==createHash('sha256').update(bytes).digest('hex'))throw Error('Private media unavailable');
 const headers={'Content-Type':asset.mime_type,'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff','Accept-Ranges':'bytes','Content-Disposition':'inline'};
 if(!range)return {body:bytes,status:200,headers:{...headers,'Content-Length':String(bytes.length)}};
 const match=/^bytes=(\d*)-(\d*)$/.exec(range);
 const invalid=()=>({body:null,status:416,headers:{...headers,'Content-Range':`bytes */${bytes.length}`}});
 if(!match||(!match[1]&&!match[2]))return invalid();
 let start,end;
 if(!match[1]){const suffix=Number(match[2]);if(!Number.isSafeInteger(suffix)||suffix<1)return invalid();start=Math.max(0,bytes.length-suffix);end=bytes.length-1;}
 else{start=Number(match[1]);end=match[2]?Number(match[2]):bytes.length-1;}
 if(!Number.isSafeInteger(start)||!Number.isSafeInteger(end)||start<0||start>=bytes.length||end<start)return invalid();
 end=Math.min(end,bytes.length-1);
 return {body:bytes.subarray(start,end+1),status:206,headers:{...headers,'Content-Length':String(end-start+1),'Content-Range':`bytes ${start}-${end}/${bytes.length}`}};
}
