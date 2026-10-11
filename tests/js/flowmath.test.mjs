import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const M = require('../../homebase/static/charts/flowmath.js');
const T = 0.25;

test('imbalances: buys against the sells one tick below, sells against the buys one tick above', () => {
  const r = M.imbalances([[100, 10, 1], [100.25, 2, 8], [100.5, 1, 9]], T, 3);
  assert.deepEqual([...r.buy], [402]);       // 9 buys vs 2 sells below; 8 vs 10 is not
  assert.deepEqual([...r.sell], []);
  assert.deepEqual([...M.imbalances([[100, 5, 5]], T, 0).buy], []);   // ratio 0 = off
});

test('stackedRuns: three in a row on one side make a run; a gap row or a short run does not', () => {
  const four = [[100, 1, 9], [100.25, 1, 9], [100.5, 1, 9], [100.75, 1, 9]];
  assert.deepEqual(M.stackedRuns(four, T, 3, 3), [{ side: 'buy', from: 100, to: 100.75, n: 4 }]);
  const two = [[100, 1, 9], [100.25, 1, 9]];
  assert.deepEqual(M.stackedRuns(two, T, 3, 3), []);
  const gap = [[100, 1, 9], [100.25, 1, 9], [100.75, 1, 9], [101, 1, 9]];   // 100.5 is missing: two runs of two
  assert.deepEqual(M.stackedRuns(gap, T, 3, 3), []);
  const sells = [[100, 9, 1], [100.25, 9, 1], [100.5, 9, 1], [100.75, 9, 1]];   // sells at P vs buys above: 9 vs 1 (the top row has none above)
  assert.deepEqual(M.stackedRuns(sells, T, 3, 3), [{ side: 'sell', from: 100, to: 100.75, n: 4 }]);
});

test('unfinished: both sides traded at the top / bottom row', () => {
  assert.deepEqual(M.unfinished([[100, 0, 5], [100.25, 3, 4], [100.5, 2, 2]]),
    { high: true, low: false, hi: 100.5, lo: 100 });
  assert.deepEqual(M.unfinished([[100, 3, 5], [100.5, 0, 7]]), { high: false, low: true, hi: 100.5, lo: 100 });
  assert.equal(M.unfinished([]).high, false);
});

test('bubbleRadius grows with the size and is clamped', () => {
  assert.equal(M.bubbleRadius(0, 10, 200), 0);
  assert.equal(M.bubbleRadius(10, 10, 200), 3);
  assert.equal(M.bubbleRadius(5000, 10, 200), 14);
  assert.ok(M.bubbleRadius(50, 10, 200) < M.bubbleRadius(100, 10, 200));
});

test('markerSize: off is 0.6; on grows with the size from the minimum and stops at 8x', () => {
  assert.equal(M.markerSize(100, 10, false), 0.6);
  assert.equal(M.markerSize(10, 10, true), 0.6);
  assert.equal(M.markerSize(80, 10, true), 2.2);
  assert.equal(M.markerSize(9999, 10, true), 2.2);
  assert.ok(M.markerSize(20, 10, true) > 0.6 && M.markerSize(20, 10, true) < M.markerSize(40, 10, true));
});

test('bubblesOf / sweepsOf: filtered by size, a bar without the fields gives none', () => {
  const bar = { bub: [[1000, 100, 4, 1], [1001, 100.25, 30, -1]], sw: [[5000, 100, 101, 12, 1], [6000, 100, 100.5, 3, -1]] };
  assert.deepEqual(M.bubblesOf(bar, 10), [{ t: 1_001_500, price: 100.25, size: 30, side: -1 }]);
  assert.equal(M.bubblesOf(bar, 3).length, 2);
  assert.deepEqual(M.sweepsOf(bar, 10), [{ t: 5000, from: 100, to: 101, size: 12, side: 1 }]);
  assert.deepEqual(M.bubblesOf({}, 1), []);
  assert.deepEqual(M.sweepsOf(null, 1), []);
});
