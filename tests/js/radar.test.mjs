import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const R = require('../../homebase/static/charts/radar.js');

test('ratioClass: grey below 2x, amber 2-4x, red at/above 4x, at the exact boundaries', () => {
  assert.equal(R.ratioClass(0), 'grey');
  assert.equal(R.ratioClass(1.99), 'grey');
  assert.equal(R.ratioClass(2), 'amber');
  assert.equal(R.ratioClass(3.99), 'amber');
  assert.equal(R.ratioClass(4), 'red');
  assert.equal(R.ratioClass(9.4), 'red');
});

test('ratioClass: null/undefined/NaN/non-numbers are grey, never thrown on', () => {
  for (const v of [null, undefined, NaN, '4', {}, []]) assert.equal(R.ratioClass(v), 'grey');
});

test('ratioText: one decimal with a multiplication sign, em dash for no ratio yet', () => {
  assert.equal(R.ratioText(4.2), '4.2×');
  assert.equal(R.ratioText(0), '0.0×');
  assert.equal(R.ratioText(null), '—');
  assert.equal(R.ratioText(undefined), '—');
  assert.equal(R.ratioText(NaN), '—');
});

const ORDER = ['NQ', 'ES', 'YM', 'RTY', 'GC', 'SI', 'CL', 'ZN', 'NG', 'HG', 'BTC'];   // the service's /api/symbols order

test('radarChips (I2a): a FIXED order -- the catalog order -- never sorted by ratio; the colour shows the ratio', () => {
  const chips = R.radarChips({ NQ: 1.2, CL: 4.5, GC: 3.0, YM: 0 }, ORDER);
  assert.deepEqual(chips.map((c) => c.root), ['NQ', 'YM', 'GC', 'CL']);
  assert.deepEqual(chips.map((c) => c.cls), ['grey', 'grey', 'amber', 'red']);
  assert.deepEqual(chips.map((c) => c.text), ['1.2×', '0.0×', '3.0×', '4.5×']);
});

test('radarChips (I2a): the order does not move when the ratios change (a press lands on the root aimed at)', () => {
  const a = R.radarChips({ NQ: 9, ES: 1, GC: null }, ORDER).map((c) => c.root);
  const b = R.radarChips({ NQ: 0.5, ES: 7, GC: 3 }, ORDER).map((c) => c.root);
  assert.deepEqual(a, ['NQ', 'ES', 'GC']);
  assert.deepEqual(b, a);
});

test('radarChips (I2a): a root with no ratio yet keeps its place and reads as a grey em dash', () => {
  const chips = R.radarChips({ NQ: 1.0, CL: null, BTC: null, GC: 5.0 }, ORDER);
  assert.deepEqual(chips.map((c) => c.root), ['NQ', 'GC', 'CL', 'BTC']);
  assert.deepEqual(chips.map((c) => c.text), ['1.0×', '5.0×', '—', '—']);
  assert.deepEqual(chips.map((c) => c.cls), ['grey', 'red', 'grey', 'grey']);
});

test('radarChips (I2a): a root the order does not list goes after it, alphabetically; no order at all -> alphabetical', () => {
  assert.deepEqual(R.radarChips({ ZZ: 1, NQ: 1, AA: 2 }, ORDER).map((c) => c.root), ['NQ', 'AA', 'ZZ']);
  assert.deepEqual(R.radarChips({ NQ: 1, CL: 2, BTC: null }).map((c) => c.root), ['BTC', 'CL', 'NQ']);
  assert.deepEqual(R.radarChips({ NQ: 1 }, null).map((c) => c.root), ['NQ']);
});

test('radarChips: empty or garbage input never throws, yields no chips', () => {
  assert.deepEqual(R.radarChips({}), []);
  assert.deepEqual(R.radarChips(null), []);
  assert.deepEqual(R.radarChips(undefined), []);
});

test('radarChips: every root stays independently graded even when several tie at the same ratio', () => {
  const chips = R.radarChips({ ES: 4.0, NQ: 4.0 });
  assert.deepEqual(chips.map((c) => c.root).sort(), ['ES', 'NQ']);
  assert.ok(chips.every((c) => c.cls === 'red'));
});
