import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* desk/acctset.js: the pure per-account settings helpers (the settings sheet itself went with the Desk makeover, Task 9). */
const CODE = readFileSync(new URL('../../homebase/static/desk/acctset.js', import.meta.url), 'utf8');
const plain = (v) => JSON.parse(JSON.stringify(v));

function load() {
  const ctx = vm.createContext({ console });
  vm.runInContext(CODE + '\nglobalThis.api = { AcctSet };', ctx);
  return { api: ctx.api };
}
const A = load().api.AcctSet;

test('label: xN for contracts, $X risk for risk', () => {
  assert.equal(A.label({ qty: 3 }), '×3');
  assert.equal(A.label({ qty: 3, size: 'contracts' }), '×3');
  assert.equal(A.label({ qty: 1, size: 'risk', risk_usd: 500 }), '$500 risk');
});

test('tag: the stop-after words, nothing for never', () => {
  assert.equal(A.tag({ stop_after: 'win' }), 'stops after a win');
  assert.equal(A.tag({ stop_after: 'profit' }), 'stops in profit');
  assert.equal(A.tag({ qty: 1 }), '');
  assert.equal(A.tag({ stop_after: 'none' }), '');
});

test('rowFrom: drops most when removed and stop_after when never; risk keeps a whole qty', () => {
  const prev = { account: 'a', qty: 2, size: 'contracts', stop_after: 'win', most: 20 };
  const r = A.rowFrom({ size: 'contracts', qty: 4, stop_after: 'none', most: null }, prev);
  assert.deepEqual(plain(r), { account: 'a', qty: 4, size: 'contracts' });
  assert.ok(!('most' in r) && !('stop_after' in r));
  const k = A.rowFrom({ size: 'risk', risk_usd: 750, qty: 9, stop_after: 'profit', most: 12 }, prev);
  assert.deepEqual(plain(k), { account: 'a', qty: 2, size: 'risk', risk_usd: 750, stop_after: 'profit', most: 12 });   // qty stays the row's own
  const legacy = A.rowFrom({ size: 'risk', risk_usd: 100, stop_after: 'none', most: null }, { account: 'b' });
  assert.equal(legacy.qty, 1, 'a row with no qty falls back to 1');
});

test('needsAsk: a LIVE raise or a switch to risk asks; lower, same, or a non-live account never', () => {
  const c3 = { account: 'a', qty: 3, size: 'contracts' }, r500 = { account: 'a', qty: 1, size: 'risk', risk_usd: 500 };
  assert.equal(A.needsAsk(c3, { ...c3, qty: 4 }, true), true);
  assert.equal(A.needsAsk(c3, { ...c3, qty: 2 }, true), false);
  assert.equal(A.needsAsk(c3, { ...c3, stop_after: 'win' }, true), false);
  assert.equal(A.needsAsk(c3, r500, true), true, 'switched to risk');
  assert.equal(A.needsAsk(r500, { ...r500, risk_usd: 600 }, true), true);
  assert.equal(A.needsAsk(r500, { ...r500, risk_usd: 400 }, true), false);
  assert.equal(A.needsAsk(c3, { ...c3, qty: 9 }, false), false);
  assert.equal(A.needsAsk(c3, r500, false), false);
  assert.equal(A.needsAsk({ account: 'a', qty: 1 }, { account: 'a', qty: 2 }, true), true, 'a legacy row reads as contracts');
});

test('withRow replaces one account\'s row and keeps every other row as it is', () => {
  const other = { account: 'b', qty: 1, size: 'risk', risk_usd: 250, stop_after: 'win', most: 5 };
  const out = A.withRow([{ account: 'a', qty: 1 }, other], { account: 'a', qty: 2, size: 'contracts' });
  assert.deepEqual(plain(out), [{ account: 'a', qty: 2, size: 'contracts' }, plain(other)]);
  assert.deepEqual(plain(A.withRow([other], { account: 'c', qty: 1 })).map((r) => r.account), ['b', 'c'], 'a new account is added');
});

test('formOf: a legacy row opens as "own" with no Most box; a set row opens as it is', () => {
  assert.deepEqual(plain(A.formOf({ account: 'a', qty: 3 })), { size: 'own', qty: 3, risk_usd: '', stop_after: 'none', most: null, hold: false });
  assert.deepEqual(plain(A.formOf({ account: 'a', qty: 1, size: 'risk', risk_usd: 500, stop_after: 'win' })),
    { size: 'risk', qty: 1, risk_usd: 500, stop_after: 'win', most: null, hold: false });
});

test('rowFrom "own": {account, qty, stop_after?} only, never size or most', () => {
  const r = A.rowFrom({ size: 'own', qty: 4, stop_after: 'win', most: 20 }, { account: 'a', qty: 3 });
  assert.deepEqual(plain(r), { account: 'a', qty: 4, stop_after: 'win' });
});

test('needsAsk: a LIVE plain row given a size asks; a plain qty raise asks; Most up or removed on a risk or contracts row asks', () => {
  const legacy = { account: 'a', qty: 2 }, r = { account: 'a', qty: 1, size: 'risk', risk_usd: 500, most: 20 };
  const c = { account: 'a', qty: 2, size: 'contracts', most: 20 };
  assert.equal(A.needsAsk(legacy, { ...legacy, stop_after: 'win' }, true), false);
  assert.equal(A.needsAsk(legacy, { ...legacy, qty: 3 }, true), true);
  assert.equal(A.needsAsk(legacy, { ...c }, true), true, 'legacy switched to Contracts');
  assert.equal(A.needsAsk(legacy, { ...c }, false), false);
  assert.equal(A.needsAsk(r, { ...r, most: 40 }, true), true);
  assert.equal(A.needsAsk(r, { account: 'a', qty: 1, size: 'risk', risk_usd: 500 }, true), true, 'Most removed');
  assert.equal(A.needsAsk(r, { ...r, most: 10 }, true), false);
  assert.equal(A.needsAsk(c, { ...c, most: 40 }, true), true, 'a contracts row\'s Most raised asks too (Task 10)');
});

// ---- final fixes (final-review.md) -----------------------------------------------------------------------
test('words: label, then Most when asked, then the stop-after tag', () => {
  assert.equal(A.words({ qty: 3 }), '×3');
  assert.equal(A.words({ qty: 1, size: 'risk', risk_usd: 500, stop_after: 'win', most: 4 }), '$500 risk · stops after a win');
  assert.equal(A.words({ qty: 1, size: 'risk', risk_usd: 500, stop_after: 'win', most: 4 }, undefined, true), '$500 risk · most 4 · stops after a win');
  assert.equal(A.words({ qty: 2, stop_after: 'profit' }, undefined, true), '×2 · stops in profit');
});

test('words, ownWords, switchContract: the gear\'s pure helpers', () => {
  assert.deepEqual(plain(A.switchContract({contract:'MNQ', size:'contracts', qty:3, most:20}, 'NQ', {MNQ:20, NQ:2})),
                   {contract:'NQ', size:'contracts', qty:1, most:2});
  assert.equal(A.switchContract({contract:'MNQ', size:'risk', risk_usd:500, most:20}, 'NQ', {MNQ:20, NQ:2}).risk_usd, 500);
  assert.equal(A.words({contract:'NQ', size:'contracts', qty:1}, 'FLEX'), 'FLEX · 1 NQ');
  assert.equal(A.words({contract:'MNQ', size:'risk', risk_usd:500, qty:1}, 'FAST'), 'FAST · $500 risk · MNQ');
  assert.equal(A.words({contract:'MNQ', qty:3}), '3 MNQ');
  assert.equal(A.words({qty:3}), '×3');
  assert.equal(A.words({contract:'MNQ', size:'contracts', qty:3, most:20}, undefined, true), '3 MNQ · most 20');
  assert.equal(A.ownWords(650), 'its own $650 a trade');
  const C = ['MNQ', 'NQ'];
  assert.equal(A.needsAsk({contract:'MNQ', qty:1}, {contract:'NQ', qty:1}, true, C), true);
  assert.equal(A.needsAsk({qty:1}, {contract:'NQ', qty:1}, true, C), true);
  assert.equal(A.needsAsk({contract:'NQ', qty:1}, {contract:'MNQ', qty:1}, true, C), false);
  assert.equal(A.needsAsk({contract:'MNQ', qty:1}, {contract:'NQ', qty:1}, false, C), false);
  assert.equal(A.needsAsk({contract:'MNQ', size:'contracts', qty:1, most:20}, {contract:'MNQ', size:'contracts', qty:1, most:30}, true, C), true);
});
