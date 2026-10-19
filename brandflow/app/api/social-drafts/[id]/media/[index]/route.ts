import {NextResponse} from 'next/server';
import {db} from '@/lib/db';
import {getSession} from '@/lib/auth';
import {privateMediaResponse} from '@/lib/private-media-response.mjs';
import {createImagePreview,imagePreviewHeaders,etagMatches} from '@/lib/image-preview.mjs';

export const dynamic='force-dynamic';

export async function GET(req:Request,{params}:{params:{id:string,index:string}}){
 const session=await getSession();
 if(session?.role!=='admin'||!session.sub)return NextResponse.json({error:'Administrator access required'},{status:403});
 if(!/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(params.id)||! /^(?:[0-9])$/.test(params.index))return NextResponse.json({error:'Invalid private media reference'},{status:400});
 const {rows:[asset]}=await db.query(`SELECT a.media_bytes,a.mime_type,a.sha256 FROM social_post_media_assets a
  JOIN social_post_drafts d ON d.id=a.draft_id JOIN brands b ON b.id=d.brand_id
  JOIN users u ON u.id=$3 AND u.active=true AND u.role='admin'
  WHERE b.slug='funzug' AND a.draft_id=$1 AND a.media_index=$2`,[params.id,Number(params.index),session.sub]);
 if(!asset)return NextResponse.json({error:'Private media not found'},{status:404});
 try{
  if(new URL(req.url).searchParams.get('preview')==='1'&&['image/png','image/jpeg'].includes(asset.mime_type)){
   privateMediaResponse(asset,null);
   const url=new URL(req.url);
   if(url.searchParams.has('v')&&url.searchParams.get('v')!==asset.sha256)return NextResponse.json({error:'Image changed. Refresh the review page.'},{status:409});
   const headers=imagePreviewHeaders(asset.sha256);
   if(etagMatches(req.headers.get('if-none-match'),headers.ETag))return new NextResponse(null,{status:304,headers});
   const bytes=await createImagePreview(asset.media_bytes,asset.sha256);
   return new NextResponse(new Uint8Array(bytes).buffer,{headers:{...headers,'Content-Length':String(bytes.length)}});
  }
  const response=privateMediaResponse(asset,req.headers.get('range'));return new NextResponse(response.body===null?null:new Uint8Array(response.body).buffer,{status:response.status,headers:response.headers});}
 catch{return NextResponse.json({error:'Private media requires reconciliation'},{status:409});}
}
