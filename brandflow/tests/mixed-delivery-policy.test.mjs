import test from 'node:test';
import assert from 'node:assert/strict';
import {mixedDeliveryEnabled} from '../lib/mixed-delivery-policy.mjs';
test('acceptance gate is disabled by default and limited to the two owner-authorized IDs',()=>{
 for(const id of ['funzug-test-2026-10-16-carousel','funzug-test-2026-10-16-reel']){
  assert.equal(mixedDeliveryEnabled(id,{}),false);
  assert.equal(mixedDeliveryEnabled(id,{FUNZUG_NATIVE_ACCEPTANCE_ENABLED:'1'}),true);
 }
 for(const id of ['news-carousel','funzug-test-2026-10-16-carousel-extra',null])assert.equal(mixedDeliveryEnabled(id,{FUNZUG_NATIVE_ACCEPTANCE_ENABLED:'1'}),false);
 assert.equal(mixedDeliveryEnabled('news-carousel',{FUNZUG_NATIVE_MIXED_ENABLED:'1'}),true);
});
