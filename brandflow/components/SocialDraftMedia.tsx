type Asset={index:number;mimeType:string;width:number;height:number};

export default function SocialDraftMedia({id,headline,format,assets}:{id:string;headline:string;format?:string;assets:Asset[]}){
 if(!format||format==='image')return <img className="draftimage" src={`/api/social-drafts/${id}/image`} alt={headline}/>;
 const ordered=Array.isArray(assets)&&assets.every((a,i)=>a.index===i&&a.width>0&&a.width<a.height&&Math.abs(a.width*5-a.height*4)<=2);
 if(format==='carousel'&&ordered&&assets.length>=2&&assets.length<=10&&assets.every(a=>['image/png','image/jpeg'].includes(a.mimeType)))return <div className="stack">{assets.map((asset,index)=><figure key={index}><img className="draftimage" src={`/api/social-drafts/${id}/media/${index}`} alt={`${headline}, slide ${index+1} of ${assets.length}`}/><figcaption>Slide {index+1} of {assets.length}</figcaption></figure>)}</div>;
 if(format==='reel'&&ordered&&assets.length===1&&assets[0].mimeType==='video/mp4')return <video className="draftimage" controls preload="metadata" aria-label={headline}><source src={`/api/social-drafts/${id}/media/0`} type="video/mp4"/>Video preview is unavailable in this browser.</video>;
 return <div className="error">Media package is incomplete. Approval is unavailable.</div>;
}
