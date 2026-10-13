import {timingSafeEqual} from 'crypto';
import {z} from 'zod';

const httpsUrl=z.string().url().refine(v=>new URL(v).protocol==='https:',{message:'HTTPS URL required'});
const source=z.object({id:z.string().trim().min(1).max(200),title:z.string().trim().min(1).max(1000),publisher:z.string().trim().min(1).max(500),url:httpsUrl,published_at:z.string().datetime({offset:true}).nullable(),checked_at:z.string().datetime({offset:true})}).strict();
const claim=z.object({text:z.string().trim().min(1).max(2000),source_ids:z.array(z.string().trim().min(1).max(200)).min(1).max(20),support_note:z.string().trim().min(1).max(4000)}).strict();
const image=z.discriminatedUnion('kind',[
 z.object({kind:z.literal('base64'),mimeType:z.enum(['image/png','image/jpeg']),width:z.number().int().positive(),height:z.number().int().positive(),data:z.string().min(16)}).strict(),
 z.object({kind:z.literal('secure_url'),mimeType:z.enum(['image/png','image/jpeg']),width:z.number().int().positive(),height:z.number().int().positive(),url:httpsUrl}).strict()
]).refine(v=>v.width<v.height&&Math.abs(v.width*5-v.height*4)<=2,{message:'Image must be portrait 4:5 with nearest-pixel rounding'});
const common=z.object({externalId:z.string().trim().min(1).max(200),headline:z.string().trim().min(1).max(500),caption:z.string().trim().min(1).max(10000),claims:z.array(claim).min(1).max(100),sources:z.array(source).min(1).max(100),platforms:z.array(z.enum(['instagram','facebook'])).min(1).max(2),proposedSchedule:z.string().datetime({offset:true}),scheduleTimezone:z.literal('Asia/Kolkata')}).strict();
function validateEvidence(value:z.infer<typeof common>,ctx:z.RefinementCtx){
 if(new Set(value.platforms).size!==value.platforms.length)ctx.addIssue({code:z.ZodIssueCode.custom,path:['platforms'],message:'Platforms must be unique'});
 const ids=value.sources.map(x=>x.id);if(new Set(ids).size!==ids.length)ctx.addIssue({code:z.ZodIssueCode.custom,path:['sources'],message:'Source IDs must be unique'});
 const sources=new Set(ids);for(const [i,item] of value.claims.entries())for(const id of item.source_ids)if(!sources.has(id))ctx.addIssue({code:z.ZodIssueCode.custom,path:['claims',i,'source_ids'],message:'Claim source ID must exist in sources'});
 if(!offsetMatchesZone(value.proposedSchedule,value.scheduleTimezone))ctx.addIssue({code:z.ZodIssueCode.custom,path:['proposedSchedule'],message:'Timestamp offset does not match scheduleTimezone at that instant'});
}
const draft=common.extend({image}).superRefine(validateEvidence);
export const funzugBatchSchema=z.object({schemaVersion:z.literal(1),brandSlug:z.literal('funzug'),batchId:z.string().trim().min(1).max(200),drafts:z.array(draft).length(1)}).strict();
const mediaAsset=z.object({mimeType:z.enum(['image/png','image/jpeg','video/mp4']),width:z.number().int().positive(),height:z.number().int().positive(),data:z.string().min(16),durationMs:z.number().int().min(1).max(180000).optional()}).strict();
const orderedDraft=common.extend({format:z.enum(['carousel','reel']),media:z.array(mediaAsset).min(1).max(10)}).superRefine(validateEvidence);
export const funzugOrderedBatchSchema=z.object({schemaVersion:z.literal(2),brandSlug:z.literal('funzug'),batchId:z.string().trim().min(1).max(200),drafts:z.array(orderedDraft).length(1)}).strict();

function offsetMatchesZone(timestamp:string,timeZone:string){
 const supplied=timestamp.match(/(Z|[+-]\d{2}:\d{2})$/)?.[1];if(!supplied)return false;
 const part=new Intl.DateTimeFormat('en-US',{timeZone,timeZoneName:'longOffset'}).formatToParts(new Date(timestamp)).find(x=>x.type==='timeZoneName')?.value;
 const expected=part?.replace('GMT','')||'';return supplied===(expected||'Z')||(supplied==='Z'&&expected==='+00:00');
}

export function validBearer(header:string|null){
 const secret=process.env.FUNZUG_DRAFT_INGEST_SECRET;
 if(!secret||secret.length<32||!header?.startsWith('Bearer '))return false;
 const supplied=header.slice(7);const a=Buffer.from(secret);const b=Buffer.from(supplied);
 return a.length===b.length&&timingSafeEqual(a,b);
}

export function decodeAndVerifyImage(data:string,mimeType:string,expectedWidth?:number,expectedHeight?:number){
 let bytes:Buffer;try{bytes=Buffer.from(data,'base64')}catch{throw new Error('Invalid base64 image')}
 if(!bytes.length||bytes.length>12*1024*1024)throw new Error('Image must be between 1 byte and 12 MB');
 let width=0,height=0;
 if(mimeType==='image/png'&&bytes.length>=24&&bytes.subarray(0,8).equals(Buffer.from([137,80,78,71,13,10,26,10]))){width=bytes.readUInt32BE(16);height=bytes.readUInt32BE(20)}
 if(mimeType==='image/jpeg'&&bytes[0]===0xff&&bytes[1]===0xd8){let p=2;while(p+9<bytes.length){if(bytes[p]!==0xff){p++;continue}const marker=bytes[p+1];const size=bytes.readUInt16BE(p+2);if([0xc0,0xc1,0xc2,0xc3,0xc5,0xc6,0xc7,0xc9,0xca,0xcb,0xcd,0xce,0xcf].includes(marker)){height=bytes.readUInt16BE(p+5);width=bytes.readUInt16BE(p+7);break}if(size<2)break;p+=2+size}}
 if(!(width>0&&width<height&&Math.abs(width*5-height*4)<=2))throw new Error('Image bytes must be portrait 4:5 with nearest-pixel rounding');
 if((expectedWidth!==undefined&&width!==expectedWidth)||(expectedHeight!==undefined&&height!==expectedHeight))throw new Error('Image dimensions do not match metadata');
 return bytes;
}
