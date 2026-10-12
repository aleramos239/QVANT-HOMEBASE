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

test('bubblesOf: a size ceiling and one side only', () => {
  const bar = { bub: [[1000, 100, 4, 1], [1001, 100.25, 30, -1], [1002, 100.5, 80, 1], [1003, 100.75, 12, -1]] };
  assert.deepEqual(M.bubblesOf(bar, 10, 50).map((b) => b.size), [30, 12]);          // 4 under the floor, 80 over the ceiling
  assert.deepEqual(M.bubblesOf(bar, 10, 0).map((b) => b.size), [30, 80, 12]);       // max 0: no ceiling
  assert.deepEqual(M.bubblesOf(bar, 1, 0, 'buy').map((b) => b.size), [4, 80]);
  assert.deepEqual(M.bubblesOf(bar, 1, 0, 'sell').map((b) => b.size), [30, 12]);
  assert.deepEqual(M.bubblesOf(bar, 10, 50, 'sell').map((b) => b.size), [30, 12]);
  assert.equal(M.bubblesOf(bar, 10, 50, 'buy').length, 0);
});

const bar = (h, l, c, extra = {}) => ({ o: (h + l) / 2, h, l, c, v: 100, d: 0, ...extra });

test('stopRuns: a sweep through the swing high / low, enough contracts, flow data required', () => {
  const quiet = Array.from({ length: 10 }, (_, k) => bar(101 + (k === 4 ? 1 : 0), 99, 100));   // swing high 102 at bar 4
  const run = bar(103, 100, 102.5, { sw: [[1, 101.75, 102.75, 30, 1], [2, 100.5, 101, 40, 1]] });
  const bars = [...quiet, run];
  const r = M.stopRuns(bars, 0, bars.length - 1, 10, 25);
  assert.deepEqual(r, [{ i: 10, from: 4, side: 1, level: 102, size: 30, held: true }]);   // only the sweep that reached 102.75 counts
  assert.equal(M.stopRuns(bars, 0, bars.length - 1, 10, 31).length, 0);                     // not enough contracts
  assert.equal(M.stopRuns([...quiet, bar(103, 100, 102.5)], 0, 10, 10, 1).length, 0);       // no flow data: never a run
  const trap = bar(103, 100, 101.5, { sw: [[1, 102, 103, 50, 1]] });                         // pushed straight back
  assert.equal(M.stopRuns([...quiet, trap], 0, 10, 10, 25)[0].held, false);
});

test('stopRuns: down side, the swing is only the bars before, blank slots are skipped', () => {
  const base = Array.from({ length: 6 }, (_, k) => bar(101, k === 2 ? 98 : 99, 100));        // swing low 98 at bar 2
  const dn = bar(100, 97, 97.5, { sw: [[1, 98.5, 97.25, 60, -1]] });
  const bars = [base[0], { blank: true }, ...base.slice(1), dn];
  const r = M.stopRuns(bars, 0, bars.length - 1, 20, 50);
  assert.equal(r.length, 1);
  assert.deepEqual([r[0].side, r[0].level, r[0].size, r[0].held, r[0].i], [-1, 98, 60, true, 7]);
});

test('exhaustions: a big push to a new high that goes nowhere and closes back under its midpoint', () => {
  const calm = Array.from({ length: 12 }, (_, k) => bar(100 + (k % 3) * 0.25, 99, 99.5, { d: k % 2 ? 20 : -20 }));
  const push = bar(103, 100, 102.5, { d: 200 });           // 10x the 20 average, a new high
  const after = [bar(102.75, 101, 102), bar(102.5, 100.5, 101), bar(102, 99.5, 100.5)];   // no high above 103, last closes under 101.5
  const bars = [...calm, push, ...after];
  const r = M.exhaustions(bars, 0, bars.length - 1, 10, 3, 3);
  assert.deepEqual(r, [{ i: 15, at: 12, dir: -1, level: 103, delta: 200 }]);
  const goes = [...calm, push, bar(104, 102, 103.5), bar(103, 101, 102), bar(102, 100, 101)];   // the next bar made a higher high
  assert.equal(M.exhaustions(goes, 0, goes.length - 1, 10, 3, 3).length, 0);
  const holds = [...calm, push, bar(102.75, 101.5, 102.5), bar(102.5, 101.5, 102.25), bar(102.5, 101.5, 102.25)];   // stays above the midpoint
  assert.equal(M.exhaustions(holds, 0, holds.length - 1, 10, 3, 3).length, 0);
  assert.equal(M.exhaustions(bars.slice(0, 15), 0, 14, 10, 3, 3).length, 0);                // not confirmed yet: only 2 bars after the push
});

test('exhaustions: sellers spent at a new low turn price up; a modest delta is not a push', () => {
  const calm = Array.from({ length: 12 }, (_, k) => bar(101, 99 - (k % 3) * 0.25, 100, { d: k % 2 ? 20 : -20 }));
  const push = bar(100, 96, 96.5, { d: -150 });
  const after = [bar(97.5, 96.25, 97.25), bar(98, 96.5, 97.5), bar(99, 97, 98.5)];
  const bars = [...calm, push, ...after];
  assert.deepEqual(M.exhaustions(bars, 0, bars.length - 1, 10, 3, 3), [{ i: 15, at: 12, dir: 1, level: 96, delta: -150 }]);
  const mild = [...calm, { ...push, d: -40 }, ...after];
  assert.equal(M.exhaustions(mild, 0, mild.length - 1, 10, 3, 3).length, 0);
});

test('valueArea: from the busiest price outward until the share of volume is covered', () => {
  const rows = [[100, 5], [101, 10], [102, 30], [103, 20], [104, 15], [105, 5]];     // 85 in all
  assert.deepEqual(M.valueArea(rows, 102, 70), { vah: 104, val: 102 });              // the two rows above (35) beat the two below (15): 30 + 20 + 15 = 65 >= 59.5
  assert.deepEqual(M.valueArea(rows, 102, 100), { vah: 105, val: 100 });
  assert.deepEqual(M.valueArea(rows, 102, 1), { vah: 102, val: 102 });
  assert.deepEqual(M.valueArea([[1, 1]], 1, 70), { vah: 1, val: 1 });
  assert.equal(M.valueArea([], 1, 70), null);
});
