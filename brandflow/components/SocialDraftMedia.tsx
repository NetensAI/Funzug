type Asset={index:number;mimeType:string;width:number;height:number;sha256?:string};

export default function SocialDraftMedia({id,headline,format,assets,imageHash,priority=false}:{id:string;headline:string;format?:string;assets:Asset[];imageHash?:string;priority?:boolean}){
 const preview=(url:string,hash?:string)=>`${url}?preview=1${hash?`&v=${hash}`:''}`;
 const picture=(url:string,alt:string,hash?:string,first=false)=><a href={hash?`${url}?v=${hash}`:url} target="_blank" rel="noreferrer" title="Open full-size image"><img className="draftimage" src={preview(url,hash)} alt={alt} width={560} height={700} style={{height:'auto',maxWidth:'100%'}} loading={priority&&first?'eager':'lazy'} {...{fetchpriority:priority&&first?'high':'auto'}} decoding="async"/></a>;
 if(!format||format==='image')return <div>{picture(`/api/social-drafts/${id}/image`,headline,imageHash,true)}<div className="muted">Click image to open full size</div></div>;
 const ordered=Array.isArray(assets)&&assets.every((a,i)=>a.index===i&&a.width>0&&a.width<a.height&&Math.abs(a.width*5-a.height*4)<=2);
 if(format==='carousel'&&ordered&&assets.length>=2&&assets.length<=10&&assets.every(a=>['image/png','image/jpeg'].includes(a.mimeType)))return <div className="stack">{assets.map((asset,index)=><figure key={index}>{picture(`/api/social-drafts/${id}/media/${index}`,`${headline}, slide ${index+1} of ${assets.length}`,asset.sha256,index===0)}<figcaption>Slide {index+1} of {assets.length} · Click to open full size</figcaption></figure>)}</div>;
 if(format==='reel'&&ordered&&assets.length===1&&assets[0].mimeType==='video/mp4')return <video className="draftimage" controls preload="metadata" aria-label={headline}><source src={`/api/social-drafts/${id}/media/0`} type="video/mp4"/>Video preview is unavailable in this browser.</video>;
 return <div className="error">Media package is incomplete. Approval is unavailable.</div>;
}
