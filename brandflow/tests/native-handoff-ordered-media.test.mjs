import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
const route = fs.readFileSync(new URL('../app/api/integrations/funzug/native-handoff/route.ts', import.meta.url), 'utf8');
test('native handoff loads ordered media for carousel and reel content hashing', () => {
  assert.match(route, /ordered_media/);
  assert.match(route, /FOR UPDATE OF d/);
});
