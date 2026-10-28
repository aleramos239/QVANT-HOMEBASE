import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* Big prints markers (cell.js drawMarkers): one instance draws exactly as it always did; a second instance draws
   with its OWN minimum, side, labels, shape and colours (it used to be ignored). cell.js is browser-only: loaded under
   minimal stubs, driven through Cell.prototype on a bare object (as cell-bardata.test.mjs does). */
const require = createRequire(import.meta.url);
globalThis.window = globalThis;
globalThis.HBLayers = {};
require('../../homebase/static/charts/catalog.js');
require('../../homebase/static/charts/flowmath.js');
require('../../homebase/static/charts/cell.js');
const { Cell } = globalThis.HBCell;
globalThis.HBDrawings = { placeMarkers: (bars, extra) => extra.map((m) => ({ ...m, time: 5 })) };

const P = { up: '#0f0', down: '#f00' };
const bar = (i, big) => ({ tt: 100 + i, ms: 60000 * i, big });
// rows are [sec, price, size, side]
const BARS = [bar(0, [[1, 10, 30, 1], [2, 10, 80, -1]]), bar(1, [[1, 10, 200, 1], [2, 10, 12, -1]]), bar(2, [[1, 10, 60, -1]])];
function draw(indicators, bars = BARS, extMarkers = {}) {
  let out = null;
  const c = Object.assign(Object.create(Cell.prototype), { cfg: { indicators }, bars, P, extMarkers,
    markers: { setMarkers: (m) => { out = m; } }, barMs: () => 60000 });
  c.drawMarkers();
  return out;
}
const bp = (uid, params, more = {}) => ({ uid, id: 'bigprints', visible: true, params: { min: 25, scale: true, sweeps: false, side: 'all', labels: true, ...params }, ...more });

test('one Big prints instance: the markers are exactly what they were before the second-instance change', () => {
  // pinned from the code as it was: min 25, both sides, labels, scaled circles, sorted by time
  assert.deepEqual(draw([bp('a', {})]), [
    { time: 100, position: 'belowBar', color: '#0f0', shape: 'circle', size: 0.74, text: '30' },
    { time: 100, position: 'aboveBar', color: '#f00', shape: 'circle', size: 1.49, text: '80' },
    { time: 101, position: 'belowBar', color: '#0f0', shape: 'circle', size: 2.2, text: '200' },
    { time: 102, position: 'aboveBar', color: '#f00', shape: 'circle', size: 1.27, text: '60' }]);
  assert.deepEqual(draw([bp('a', { min: 100, side: 'buy', labels: false, scale: false, shape: 'square', markerMin: 1.5 })]), [
    { time: 101, position: 'belowBar', color: '#0f0', shape: 'square', size: 1.5, text: '' }]);
  assert.deepEqual(draw([bp('a', { min: 25, side: 'sell' }, { visible: false })]), []);
  assert.deepEqual(draw([]), []);
});

test('one instance keeps only its newest 600 markers, as before', () => {
  const many = Array.from({ length: 700 }, (_, i) => bar(i, [[1, 10, 50, 1]]));
  const got = draw([bp('a', {})], many);
  assert.equal(got.length, 600);
  assert.equal(got[0].time, 100 + 100);
  assert.equal(got[599].time, 100 + 699);
});

test('a second Big prints instance draws with its own settings, not the first one\'s', () => {
  const got = draw([bp('a', { min: 25, side: 'buy', labels: true }), bp('b', { min: 100, side: 'sell', labels: false, shape: 'square' })]);
  // a: buyers >= 25 with labels; b: sellers >= 100 (none in these bars). The old code drew only the smaller min, with its side/labels.
  assert.deepEqual(got.map((m) => [m.time, m.shape, m.text]), [[100, 'circle', '30'], [101, 'circle', '200']]);
  const both = draw([bp('a', { min: 25, side: 'buy', labels: true }), bp('b', { min: 50, side: 'sell', labels: false, shape: 'square' })]);
  assert.deepEqual(both.map((m) => [m.time, m.position, m.shape, m.text]), [
    [100, 'belowBar', 'circle', '30'], [100, 'aboveBar', 'square', ''], [101, 'belowBar', 'circle', '200'], [102, 'aboveBar', 'square', '']]);
});

test('each instance is independent: a hidden one draws nothing, and it does not change the other one\'s markers', () => {
  const alone = draw([bp('a', { min: 25, side: 'buy' })]);
  assert.deepEqual(draw([bp('a', { min: 25, side: 'buy' }), bp('b', { min: 1, side: 'sell' }, { visible: false })]), alone);
  assert.deepEqual(draw([bp('b', { min: 99999 }), bp('a', { min: 25, side: 'buy' })]), alone);   // order on the chart does not matter
});

test('the 600 cap counts per instance, the extra markers still merge in time order', () => {
  const many = Array.from({ length: 700 }, (_, i) => bar(i, [[1, 10, 50, 1]]));
  assert.equal(draw([bp('a', {}), bp('b', { min: 40 })], many).length, 1200);
  const got = draw([bp('a', {})], BARS, { trade: [{ time: 5 }] });
  assert.equal(got[0].time, 5);                      // the overlay's marker sorts first
  assert.equal(got.length, 5);
});
