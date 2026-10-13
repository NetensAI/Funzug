export function nativeHandoffEqual(a,b) {
  const canonical=x=>Array.isArray(x)?x.map(canonical):x&&typeof x==='object'?Object.fromEntries(Object.keys(x).sort().map(k=>[k,canonical(x[k])])):x;
  return JSON.stringify(canonical(a))===JSON.stringify(canonical(b));
}
export function mergeNativeHandoff(previous, incoming, platforms) {
  if (!incoming || !['reserved','submitting','scheduled'].includes(incoming.state)) throw new Error('Invalid native handoff');
  if (!Array.isArray(incoming.platforms) || new Set(incoming.platforms).size!==incoming.platforms.length || JSON.stringify([...incoming.platforms].sort())!==JSON.stringify([...platforms].sort())) throw new Error('Native platforms differ from approval');
  if (!incoming.receipts || typeof incoming.receipts!=='object' || Array.isArray(incoming.receipts)) throw new Error('Invalid receipts');
  const receipts=Object.keys(incoming.receipts);
  if (receipts.some(p=>!platforms.includes(p))) throw new Error('Unexpected native receipt');
  if (incoming.state==='reserved' && (receipts.length || incoming.submission_started_at)) throw new Error('Unsubmitted reservation has submission evidence');
  if (incoming.state!=='reserved' && !incoming.submission_started_at) throw new Error('Missing native submission checkpoint');
  if (incoming.state==='scheduled' && receipts.length!==platforms.length) throw new Error('Missing native platform receipts');
  for (const platform of receipts) {
    const r=incoming.receipts[platform];
    if (!r || r.platform!==platform || r.content_hash!==incoming.content_hash || r.scheduled_at!==incoming.scheduled_at || !r.schedule_id || String(r.schedule_id).trim().toLowerCase().startsWith('meta-planner-visible:')) throw new Error('Receipt differs from reservation');
    const url=new URL(r.planner_url);
    if (url.protocol!=='https:' || url.hostname!=='business.facebook.com' || url.username || url.password) throw new Error('Invalid planner URL');
    if (!Number.isFinite(Date.parse(r.checked_at)) || Date.parse(r.checked_at)<Date.parse(incoming.submission_started_at) || Date.parse(r.checked_at)>Date.now()) throw new Error('Invalid receipt observation');
  }
  if (previous==null) {
    if (incoming.state!=='reserved') throw new Error('Reservation must precede submission');
  } else {
    if (previous.content_hash!==incoming.content_hash || previous.scheduled_at!==incoming.scheduled_at || previous.reserved_at!==incoming.reserved_at || JSON.stringify(previous.platforms)!==JSON.stringify(incoming.platforms)) throw new Error('Native reservation cannot change');
    const rank={reserved:0,submitting:1,scheduled:2};
    if (!Object.hasOwn(rank,previous.state) || rank[incoming.state]<rank[previous.state] || rank[incoming.state]>rank[previous.state]+1) throw new Error('Native state needs reconciliation');
    if (previous.submission_started_at && previous.submission_started_at!==incoming.submission_started_at) throw new Error('Submission checkpoint cannot change');
    for (const [p,r] of Object.entries(previous.receipts||{})) if (!nativeHandoffEqual(incoming.receipts[p],r)) throw new Error('Native receipt cannot change');
  }
  return incoming;
}
