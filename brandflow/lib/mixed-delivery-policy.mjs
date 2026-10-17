const acceptanceIds=new Set(['funzug-test-2026-10-22-carousel','funzug-test-2026-10-22-reel']);
const cancelledIds=new Set(['funzug-test-2026-10-16-carousel','funzug-test-2026-10-16-reel']);
export function mixedDeliveryEnabled(externalId,environment){
 if(cancelledIds.has(externalId))return false;
 return environment?.FUNZUG_NATIVE_MIXED_ENABLED==='1'||
  (environment?.FUNZUG_NATIVE_ACCEPTANCE_ENABLED==='1'&&acceptanceIds.has(externalId));
}
