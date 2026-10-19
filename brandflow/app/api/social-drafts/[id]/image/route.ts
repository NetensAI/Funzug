import {NextResponse} from 'next/server';
import {createHash} from 'node:crypto';
import {db} from '@/lib/db';
import {getSession} from '@/lib/auth';
import {cachedImagePreview,createImagePreview,imagePreviewHeaders,etagMatches} from '@/lib/image-preview.mjs';

export const dynamic='force-dynamic';
export async function GET(req:Request,{params}:{params:{id:string}}){
 const session=await getSession();
 if(!session?.sub)return NextResponse.json({error:'Unauthorized'},{status:401});
 if(!/^[0-9a-f-]{36}$/i.test(params.id))return NextResponse.json({error:'Invalid image reference'},{status:400});
 const {rows:[image]}=await db.query(`SELECT d.image_url,d.image_mime_type,encode(sha256(d.image_bytes),'hex') image_sha256
  FROM social_post_drafts d JOIN users u ON u.id=$2 AND u.active=true AND u.role=$3
  WHERE d.id=$1 AND d.media_format='image'`,[params.id,session.sub,session.role]);
 if(!image)return NextResponse.json({error:'Image unavailable'},{status:404});
 if(image.image_url)return NextResponse.redirect(image.image_url,307);
 const sha=image.image_sha256,url=new URL(req.url);
 if(!sha)return NextResponse.json({error:'Image unavailable'},{status:404});
 if(url.searchParams.has('v')&&url.searchParams.get('v')!==sha)return NextResponse.json({error:'Image changed. Refresh the review page.'},{status:409});
 const preview=url.searchParams.get('preview')==='1';
 const headers:Record<string,string>=preview?imagePreviewHeaders(sha):{'Content-Type':image.image_mime_type,'Cache-Control':'private, no-cache','ETag':`"original-${sha}"`,'Vary':'Cookie','X-Content-Type-Options':'nosniff'};
 // Authorization is checked before returning 304 or accessing the private cache.
 if(etagMatches(req.headers.get('if-none-match'),headers.ETag))return new NextResponse(null,{status:304,headers});
 try{
  let bytes=preview?await cachedImagePreview(sha):null;
  if(!bytes){
   const {rows:[row]}=await db.query('SELECT image_bytes FROM social_post_drafts WHERE id=$1',[params.id]);
   if(!Buffer.isBuffer(row?.image_bytes)||createHash('sha256').update(row.image_bytes).digest('hex')!==sha)return NextResponse.json({error:'Image changed. Refresh the review page.'},{status:409});
   bytes=preview?await createImagePreview(row.image_bytes,sha):row.image_bytes;
  }
  headers['Content-Length']=String(bytes!.length);
  return new NextResponse(new Uint8Array(bytes!).buffer,{headers});
 }catch{return NextResponse.json({error:'Image preview unavailable'},{status:503,headers:{'Cache-Control':'no-store'}});}
}
