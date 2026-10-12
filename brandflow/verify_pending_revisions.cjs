// Read-only database check. Never emits credentials, image bytes or full captions.
const {Pool}=require('pg');
const pool=new Pool({connectionString:process.env.DATABASE_URL});
(async()=>{
  try {
    const {rows}=await pool.query(`SELECT d.external_id,d.status,d.publication_authorized,d.published_at,
      position('AI-generated' in caption)>0 AS illustration_disclosed,
      to_char(proposed_schedule AT TIME ZONE 'Asia/Kolkata','YYYY-MM-DD HH24:MI') AS proposed_ist,
      schedule_timezone FROM social_post_drafts d JOIN brands b ON b.id=d.brand_id
      WHERE b.slug=$1 ORDER BY external_id`,['funzug']);
    const pending=rows.filter(r=>r.status==='pending_review');
    if(pending.length!==7||pending.some(r=>r.publication_authorized!==false||r.published_at||!r.illustration_disclosed||r.schedule_timezone!=='Asia/Kolkata')) throw Error('Pending revision verification failed');
    const orion=pending.find(r=>r.external_id==='funzug-2026-10-11-orionid-meteor-shower');
    if(orion?.proposed_ist!=='2026-10-20 19:30')throw Error('Orionids proposal mismatch');
    console.log(JSON.stringify({verifiedPending:pending.length,allUnauthorized:true,allIllustrationsDisclosed:true,orionidsProposalIST:orion.proposed_ist,reviewedCount:rows.length-pending.length}));
  } finally {await pool.end()}
})().catch(()=>{console.error('Pending revision database check failed');process.exitCode=1});
