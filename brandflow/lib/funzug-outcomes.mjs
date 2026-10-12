export function canRescheduleOutcomes(outcomes) {
  return outcomes != null && typeof outcomes === 'object' && !Array.isArray(outcomes) && Object.keys(outcomes).length === 0;
}

export function mergeOutcomes(platforms, previous, incoming) {
  if (!Array.isArray(platforms) || !platforms.length || platforms.some(p=>!['facebook','instagram'].includes(p))) throw new Error('Invalid platforms');
  const actual=Object.keys(incoming||{});
  if (!actual.length || actual.some(p=>!platforms.includes(p))) throw new Error('Unexpected platform');
  const merged={...(previous||{})};
  for (const p of actual) {
    const r=incoming[p];
    if (!r || !['published','failed'].includes(r.status)) throw new Error('Invalid result');
    const field=r.status==='published'?'publishedAt':'failedAt';
    if (typeof r[field]!=='string' || !/(Z|[+-]\d\d:\d\d)$/.test(r[field]) || !Number.isFinite(Date.parse(r[field]))) throw new Error('Invalid timestamp');
    if (r.status==='published' && (typeof r.postId!=='string' || !r.postId.trim() || r.postId.length>300)) throw new Error('Invalid post ID');
    if (merged[p]?.status==='published') {
      if (r.status==='published' && merged[p].postId!==r.postId) throw new Error('Published post cannot change');
      continue;
    }
    if (merged[p]?.status==='failed' && r.status==='failed' && Date.parse(r.failedAt)<Date.parse(merged[p].failedAt)) continue;
    merged[p]=r.status==='published'?{status:'published',postId:r.postId,publishedAt:r.publishedAt}:{status:'failed',failedAt:r.failedAt};
  }
  const complete=platforms.every(p=>merged[p]?.status==='published');
  return {results:merged,publishedAt:complete?new Date(Math.max(...platforms.map(p=>Date.parse(merged[p].publishedAt)))).toISOString():null};
}
