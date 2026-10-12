import test from 'node:test';
import assert from 'node:assert/strict';
import {mergeOutcomes,canRescheduleOutcomes} from '../lib/funzug-outcomes.mjs';
const ok={status:'published',postId:'ig-id',publishedAt:'2026-10-11T23:30:00+05:30'};
const bad={status:'failed',failedAt:'2026-10-11T23:31:00+05:30'};
test('reschedule permits only explicitly empty outcomes',()=>{
  assert.equal(canRescheduleOutcomes({}),true);
  for(const value of [null,undefined,[],false,'', {instagram:ok}, {facebook:bad}, {unknown:{}}]) assert.equal(canRescheduleOutcomes(value),false);
});
test('partial failure is not full publication',()=>{const r=mergeOutcomes(['facebook','instagram'],{},{facebook:bad,instagram:ok});assert.equal(r.publishedAt,null);assert.equal(r.results.instagram.postId,'ig-id')});
test('failure cannot erase a success',()=>{assert.deepEqual(mergeOutcomes(['instagram'],{instagram:ok},{instagram:bad}).results.instagram,ok)});
test('conflicting success is rejected',()=>{assert.throws(()=>mergeOutcomes(['instagram'],{instagram:ok},{instagram:{...ok,postId:'different'}}))});
test('unexpected platform is rejected',()=>{assert.throws(()=>mergeOutcomes(['facebook'],{},{instagram:ok}))});
test('complete results mark full publication',()=>{assert.ok(mergeOutcomes(['facebook','instagram'],{instagram:ok},{facebook:{...ok,postId:'fb-id'}}).publishedAt)});
test('failed API details are never persisted',()=>{const r=mergeOutcomes(['facebook'],{},{facebook:{...bad,error:'private-details'}});assert.equal('error' in r.results.facebook,false)});
test('timestamps must be timezone aware',()=>{assert.throws(()=>mergeOutcomes(['facebook'],{},{facebook:{...bad,failedAt:'2026-10-11'}}))});
