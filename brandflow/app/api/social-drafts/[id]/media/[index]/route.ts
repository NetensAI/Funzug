import {NextResponse} from 'next/server';
import {db} from '@/lib/db';
import {getSession} from '@/lib/auth';
import {privateMediaResponse} from '@/lib/private-media-response.mjs';

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
 try{const response=privateMediaResponse(asset,req.headers.get('range'));return new NextResponse(response.body,{status:response.status,headers:response.headers});}
 catch{return NextResponse.json({error:'Private media requires reconciliation'},{status:409});}
}
