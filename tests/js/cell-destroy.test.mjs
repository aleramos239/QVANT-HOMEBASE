import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* cell.js is browser-only (it reads window.* at load): load it under minimal stubs and drive
   Cell.prototype.destroy on a bare object -- the seam is destroy()'s own bookkeeping, not the chart. */
const require = createRequire(import.meta.url);
globalThis.window = globalThis;
globalThis.HBLayers = {};
require('../../homebase/static/charts/cell.js');
const { Cell } = globalThis.HBCell;

function bare() {
  const sent = [];
  return { sent, host: { send: (m) => sent.push(m) }, noteTimer: 0, reaching: null, loadWaiters: [], teardown() { this.tornDown = true; } };
}

test('destroy() resolves every pending whenLoaded() false, so a jump pending across a grid rebuild never hangs', () => {
  const c = bare(), got = [];
  c.loadWaiters.push((ok) => got.push(ok), (ok) => got.push(ok));   // whenLoaded()'s resolvers
  Cell.prototype.destroy.call(c);
  assert.deepEqual(got, [false, false]);
  assert.deepEqual(c.loadWaiters, []);
  assert.equal(c.tornDown, true);
  assert.deepEqual(c.sent, [{ op: 'unsub', id: undefined }]);
});

test('destroy() still resolves a pending reach() false', () => {
  const c = bare();
  let got = null;
  c.reaching = { resolve: (ok) => { got = ok; c.reaching = null; } };
  Cell.prototype.destroy.call(c);
  assert.equal(got, false);
});
