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

test('radarChips: sorted by ratio descending, coloured and labelled', () => {
  const chips = R.radarChips({ NQ: 1.2, CL: 4.5, GC: 3.0, YM: 0 });
  assert.deepEqual(chips.map((c) => c.root), ['CL', 'GC', 'NQ', 'YM']);
  assert.deepEqual(chips.map((c) => c.cls), ['red', 'amber', 'grey', 'grey']);
  assert.deepEqual(chips.map((c) => c.text), ['4.5×', '3.0×', '1.2×', '0.0×']);
});

test('radarChips: a root with no median yet (null) sorts after every real ratio, alphabetically among themselves', () => {
  const chips = R.radarChips({ NQ: 1.0, CL: null, BTC: null, GC: 5.0 });
  assert.deepEqual(chips.map((c) => c.root), ['GC', 'NQ', 'BTC', 'CL']);
  assert.deepEqual(chips.slice(2).map((c) => c.text), ['—', '—']);
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
