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

const slot = (c) => ({ o: c, h: c, l: c, c, v: 0, d: 0, n: 0, sv: {}, blank: 'lost' });   // a blank slot as withBlanks builds it: the last close as every price, no delta
const hole = (c, n) => Array.from({ length: n }, () => slot(c));
const gap = (bars, after, n) => [...bars.slice(0, after + 1), ...hole(bars[after].c, n), ...bars.slice(after + 1)];   // n blank slots after bars[after]

test('stopRuns: a hole is no bars -- not the carried close as the swing, not part of the lookback window', () => {
  const swing = Array.from({ length: 5 }, () => bar(120, 80, 100));
  const run = bar(105, 100, 104, { sw: [[1, 101, 105, 60, 1]] });
  assert.deepEqual(M.stopRuns([...swing, ...hole(100, 25), run], 0, 30, 20, 50), []);       // the 120 high is 5 bars back; 100 never traded
  const quiet = Array.from({ length: 10 }, (_, k) => bar(101 + (k === 4 ? 1 : 0), 99, 100));   // swing high 102 at bar 4
  const sweep = bar(103, 100, 102.5, { sw: [[1, 101.75, 102.75, 30, 1]] });
  const flat = M.stopRuns([...quiet, sweep], 0, 10, 10, 25);
  assert.deepEqual(flat, [{ i: 10, from: 4, side: 1, level: 102, size: 30, held: true }]);
  assert.deepEqual(M.stopRuns([...gap(quiet, 6, 5), sweep], 0, 15, 10, 25), [{ ...flat[0], i: 15 }]);   // 10 bars before it, 5 slots of hole or not
});

test('exhaustions: a hole is no bars -- not in the average delta, not one of the bars that must confirm', () => {
  const calm = Array.from({ length: 10 }, (_, k) => bar(100, 99, 99.5, { d: k % 2 ? 20 : -20 }));
  const after = [bar(102.75, 101, 102), bar(102.5, 100.5, 101), bar(102, 99.5, 100.5)];
  const ask = (bars) => M.exhaustions(bars, 0, bars.length - 1, 20, 3, 3);
  assert.equal(ask([...calm, bar(103, 100, 102.5, { d: 40 }), ...after]).length, 0);        // 40 is 2x the average of 20: no push
  assert.equal(ask([...calm, ...hole(99.5, 10), bar(103, 100, 102.5, { d: 40 }), ...after]).length, 0);   // ten empty slots do not halve the average
  assert.equal(ask([...calm, ...hole(99.5, 10), bar(103, 100, 102.5, { d: 70 }), ...after]).length, 1);
  const push = bar(103, 100, 102.5, { d: 200 });                                           // midpoint 101.5
  assert.equal(ask([...calm, push, bar(102.75, 101, 101), ...hole(101, 2)]).length, 0);     // one bar after it, two empty slots: not confirmed
  const bars = [...calm, push, after[0], ...hole(102, 2), after[1], after[2]];
  assert.deepEqual(ask(bars), [{ i: 15, at: 10, dir: -1, level: 103, delta: 200 }]);          // confirmed on the third real bar, past the hole
  assert.equal(M.exhaustions(bars, 15, 15, 20, 3, 3).length, 1);                             // a view that starts on it still sees it
  assert.equal(M.exhaustions(bars, 16, 20, 20, 3, 3).length, 0);
  assert.equal(M.exhaustions(bars, 0, 14, 20, 3, 3).length, 0);                              // a view that ends before the confirming bar does not
  const mixed = [...Array.from({ length: 10 }, (_, k) => bar(100, 99, 99.5, { d: k % 2 ? 100 : -100 })), ...calm];   // the 20 bars before the push: 60 on average
  assert.equal(ask([...mixed, ...hole(99.5, 10), bar(103, 100, 102.5, { d: 70 }), ...after]).length, 0);   // not the 10 slots of hole + 10 calm bars (20)
});

test('valueArea: from the busiest price outward until the share of volume is covered', () => {
  const rows = [[100, 5], [101, 10], [102, 30], [103, 20], [104, 15], [105, 5]];     // 85 in all
  assert.deepEqual(M.valueArea(rows, 102, 70), { vah: 104, val: 102 });              // the two rows above (35) beat the two below (15): 30 + 20 + 15 = 65 >= 59.5
  assert.deepEqual(M.valueArea(rows, 102, 100), { vah: 105, val: 100 });
  assert.deepEqual(M.valueArea(rows, 102, 1), { vah: 102, val: 102 });
  assert.deepEqual(M.valueArea([[1, 1]], 1, 70), { vah: 1, val: 1 });
  assert.equal(M.valueArea([], 1, 70), null);
});

test('smtLines: the chart market\'s two peaks joined, counted in real bars back from the confirming bar', () => {
  const bars = Array.from({ length: 12 }, (_, i) => ({ h: 100 + i, l: 99 + i, sv: {} }));
  bars[8].sv['smt:2:4'] = { dir: -1, ago: 1, px: 108, aago: 5, apx: 104, lead: -1, live: false };
  assert.deepEqual(M.smtLines(bars, 0, 11, 'smt:2:4'), [{ i: 8, from: 3, to: 7, y0: 104, y1: 108, dir: -1, lead: -1, live: false }]);
  assert.deepEqual(M.smtLines(bars, 0, 11, 'smt:6:36'), []);                     // another setting's key
  bars[5].blank = true;                                                          // a closed hour is no bar: the start moves one slot
  assert.equal(M.smtLines(bars, 0, 11, 'smt:2:4')[0].from, 2);
  bars[3].sv['smt:2:4'] = { dir: 1, ago: 0, px: 90, aago: 9, apx: 95, lead: 1 }; // its start is left of the first loaded bar
  assert.equal(M.smtLines(bars, 0, 11, 'smt:2:4').length, 1);
  assert.equal(M.smtLines(bars, 9, 11, 'smt:2:4').length, 0, 'a divergence confirmed left of the view is not asked for');
});

test('fvgBoxes: one box per gap, from its first bar to the last bar it stayed open, no line to the next gap', () => {
  const K = 'fvg:0.25:14';
  const bars = Array.from({ length: 12 }, () => ({ sv: {} }));
  for (const i of [4, 5, 6]) bars[i].sv[K] = { uh: 102, ul: 100, dh: null, dl: null };   // up gap open on bars 4-6
  bars[7].sv[K] = { uh: null, ul: null, dh: null, dl: null };                            // filled
  for (const i of [8, 9, 10]) bars[i].sv[K] = { uh: 110, ul: 108, dh: 99, dl: 97 };      // a newer up gap + a down gap
  assert.deepEqual(M.fvgBoxes(bars, K, 11), [
    { side: 1, from: 2, to: 6, top: 102, bottom: 100 },
    { side: 1, from: 6, to: 10, top: 110, bottom: 108 },
    { side: -1, from: 6, to: 10, top: 99, bottom: 97 }]);
  assert.deepEqual(M.fvgBoxes(bars, 'fvg:1:14', 11), [], 'another setting\'s key');
  bars[5].blank = true;                                                                  // a closed hour holds the gap open
  assert.equal(M.fvgBoxes(bars, K, 11)[0].to, 6);
  assert.equal(M.fvgBoxes(bars, K, 5).length, 1, 'only bars up to the one asked for');
});

/* ---- order-flow app rules (wave 2) ---- */

const SIERRA = [[106, 0, 56], [105, 293, 359], [104, 48, 532], [103, 1008, 830], [102, 682, 452], [101, 16, 0]];   // Sierra's A-F bar, top to bottom
const keys = (s) => [...s].sort((a, b) => a - b);

test('imbalancesV2: the homebase preset is imbalances() row for row, gaps and edges included', () => {
  let seed = 7;
  const rnd = (n) => { seed = (seed * 1103515245 + 12345) % 2147483648; return seed % n; };
  for (let t = 0; t < 40; t++) {
    const fp = [];
    for (let k = 0; k < 12; k++) if (rnd(5)) fp.push([100 + k * T, rnd(4) ? rnd(30) : 0, rnd(4) ? rnd(30) : 0]);
    for (const ratio of [0.5, 1, 2.5, 3, 5]) {          // below 1 a side may be flagged while smaller than the other: no minDiff, so no check
      const a = M.imbalances(fp, T, ratio), b = M.imbalancesV2(fp, { tick: T, ratio });
      assert.deepEqual(keys(b.buy), keys(a.buy));
      assert.deepEqual(keys(b.sell), keys(a.sell));
      assert.deepEqual(b.runs, M.stackedRuns(fp, T, ratio, 3));
    }
  }
  assert.equal(M.imbalancesV2([[100, 5, 5]], { tick: T, ratio: 0 }).rows.length, 0);   // ratio 0 = off
  const low = [[100, 10, 6], [100.25, 4, 5]];                  // 5 bought against 10 sold below: flagged at ratio 0.5, as imbalances() does
  assert.deepEqual(keys(M.imbalancesV2(low, { tick: T, ratio: 0.5 }).buy), [400, 401]);
  assert.deepEqual(keys(M.imbalancesV2(low, { tick: T, ratio: 0.5, minDiff: 1 }).buy), [400], 'a minDiff still wants the side to lead');
});

test('imbalancesV2: ATAS 30 contracts at 350% means the other side must be GREATER than 105; homebase takes 105', () => {
  const at = (bid) => [[100, bid, 0], [100.25, 0, 30]];       // sells at 100 against the 30 bought one tick above
  assert.deepEqual(keys(M.imbalancesV2(at(105), { tick: T, preset: 'atas', ratio: 3.5 }).sell), []);
  assert.deepEqual(keys(M.imbalancesV2(at(106), { tick: T, preset: 'atas', ratio: 3.5 }).sell), [400]);
  assert.deepEqual(keys(M.imbalancesV2(at(105), { tick: T, preset: 'homebase', ratio: 3.5 }).sell), [400]);
});

test('imbalancesV2: Sierra A-F bar, ratio above 1: bid side B and D, ask side B, D and E; at 3 it is homebase\'s answer', () => {
  const r = M.imbalancesV2(SIERRA, { tick: 1, preset: 'sierra' });
  assert.deepEqual(keys(r.sell), [103, 105]);                  // the bid side (B, D)
  assert.deepEqual(keys(r.buy), [102, 103, 105]);              // the ask side (B, D, E)
  assert.deepEqual(r.rows.map((x) => [x.price, x.sell, x.buy]),
    [[101, false, false], [102, false, true], [103, true, true], [104, false, false], [105, true, true], [106, false, false]]);
  const three = M.imbalancesV2(SIERRA, { tick: 1, preset: 'sierra', ratio: 3 });
  assert.deepEqual(keys(three.buy), [102, 105]);               // E, B
  assert.deepEqual(keys(three.sell), [105]);                   // B
  assert.deepEqual(keys(M.imbalances(SIERRA, 1, 3).buy), [102, 105]);
});

test('imbalancesV2: zero on the other side and the bar\'s edge rows are skipped or taken as one; minVolume, minDiff, stack', () => {
  const zero = [[100, 0, 4], [101, 6, 7]];                     // the buys at 101 face 0 sold at 100
  assert.deepEqual(keys(M.imbalancesV2(zero, { tick: 1 }).buy), [100, 101]);                 // 100 faces nothing below: an edge, taken as one
  assert.deepEqual(keys(M.imbalancesV2(zero, { tick: 1, preset: 'atas', ratio: 3 }).buy), []);
  assert.deepEqual(keys(M.imbalancesV2(zero, { tick: 1, preset: 'atas', ratio: 3, zero: 'one' }).buy), [101]);
  const one = [[100, 5, 9]];                                   // one row: both of its neighbours are beyond the bar
  assert.deepEqual([keys(M.imbalancesV2(one, { tick: 1 }).buy), keys(M.imbalancesV2(one, { tick: 1 }).sell)], [[100], [100]]);
  assert.deepEqual(keys(M.imbalancesV2(one, { tick: 1, preset: 'sierra' }).buy), []);
  assert.deepEqual(keys(M.imbalancesV2(one, { tick: 1, preset: 'sierra', edge: 'one' }).buy), [100]);
  const gap = [[100, 5, 5], [102, 6, 9]];                      // 101 has no row: a zero row, not an edge
  assert.deepEqual(keys(M.imbalancesV2(gap, { tick: 1, preset: 'atas', ratio: 3 }).buy), []);
  const v = [[100, 4, 0], [101, 0, 12]];                       // 12 vs 4 below
  assert.deepEqual(keys(M.imbalancesV2(v, { tick: 1, ratio: 2 }).buy), [101]);
  assert.deepEqual(keys(M.imbalancesV2(v, { tick: 1, ratio: 2, minVolume: 13 }).buy), []);   // both sides under 13
  assert.deepEqual(keys(M.imbalancesV2(v, { tick: 1, ratio: 2, minVolume: 12 }).buy), [101]);
  assert.deepEqual(keys(M.imbalancesV2(v, { tick: 1, ratio: 2, minDiff: 9 }).buy), []);      // 12 - 4 = 8
  const run = [[100, 1, 9], [101, 1, 9], [102, 1, 9]];
  assert.equal(M.imbalancesV2(run, { tick: 1 }).runs.length, 1);
  assert.deepEqual(M.imbalancesV2(run, { tick: 1, stack: 0 }).runs, []);
  assert.equal(M.imbalancesV2(run, { tick: 1, stack: 4 }).runs.length, 0);
});

test('valueAreaV2 homebase = the server\'s profile_from (fixtures made by it, ties and a gap included)', () => {
  const rows = (a) => a.map(([p, v]) => [p, v]);
  const cases = [
    [[[25, 21]], [25, 25, 25]],
    [[[25, 10], [25.25, 26]], [25.25, 25.25, 25.25]],
    [[[25, 4], [25.25, 5], [25.5, 35], [25.75, 7], [26, 24]], [25.5, 26, 25.5]],
    [[[25, 38], [25.25, 4], [25.5, 38], [26, 3], [26.25, 6], [26.5, 28], [26.75, 38], [27, 5]], [25, 26.5, 25]],
    [[[25, 16], [25.25, 6], [25.5, 36], [26, 4], [26.25, 37], [26.5, 8], [26.75, 15], [27, 38], [27.25, 4], [27.5, 37], [27.75, 38], [28, 26], [28.25, 4]], [27, 28, 26.25]],
  ];
  for (const [r, [poc, vah, val]] of cases) assert.deepEqual(M.valueAreaV2(rows(r), 70), { poc, vah, val });
  assert.equal(M.valueAreaV2([], 70), null);
});

test('valueAreaV2 sierra: POC tie -> nearest the middle, then the lower; equal neighbours add BOTH; tv stops before the overshoot', () => {
  assert.equal(M.valueAreaV2([[1, 9], [2, 5], [3, 9], [4, 5], [5, 9]], 70, 'sierra').poc, 3);
  assert.equal(M.valueAreaV2([[1, 9], [2, 5], [3, 9], [4, 5], [5, 9]], 70, 'homebase').poc, 1);
  assert.equal(M.valueAreaV2([[1, 5], [2, 9], [3, 9], [4, 5]], 70, 'sierra').poc, 2);          // equally near: the lower
  const tie = [[1, 10], [2, 50], [3, 10], [4, 10]];                                            // total 80, 70% = 56
  assert.deepEqual(M.valueAreaV2(tie, 70, 'sierra'), { poc: 2, vah: 3, val: 1 });
  assert.deepEqual(M.valueAreaV2(tie, 70, 'homebase'), { poc: 2, vah: 3, val: 2 });
  const q = [[1, 10], [2, 10], [3, 40], [4, 30], [5, 10]];                                     // 60% = 60: 40 + 30 overshoots
  assert.deepEqual(M.valueAreaV2(q, 60, 'homebase'), { poc: 3, vah: 4, val: 3 });
  assert.deepEqual(M.valueAreaV2(q, 60, 'tv'), { poc: 3, vah: 3, val: 3 });
  assert.deepEqual(M.valueAreaV2(q, 70, 'tv'), { poc: 3, vah: 4, val: 3 });                    // exactly 70: reached, not past
  const gap = [[1, 30], [2, 50], [4, 40]];                                                     // 3 traded nothing: with the tick it is a zero row
  assert.deepEqual(M.valueAreaV2(gap, 70, 'sierra'), { poc: 2, vah: 4, val: 2 });
  assert.deepEqual(M.valueAreaV2(gap, 70, 'sierra', 1), { poc: 2, vah: 4, val: 1 });
});

test('nakedPocs: a bar\'s POC stays naked until a later bar\'s range reaches it', () => {
  const bars = [
    { h: 100.25, l: 100, fp: [[100, 5, 5], [100.25, 2, 2]] },        // POC 100, reached by bar 2
    { h: 102, l: 102, fp: [[102, 3, 3]] },                           // POC 102, never reached
    { h: 100.5, l: 99.5, fp: [[100, 1, 1], [99.5, 6, 6]] },          // POC 99.5
    { h: 101, l: 100.75, fp: [[100.75, 4, 4]] },
    { blank: true },
    { h: 100.5, l: 100.25 },                                         // no fp: not a source
  ];
  assert.deepEqual(M.nakedPocs(bars), [{ i: 1, price: 102, vol: 6 }, { i: 2, price: 99.5, vol: 12 }, { i: 3, price: 100.75, vol: 8 }]);
  assert.deepEqual(M.nakedPocs(bars, 2, 2), [{ i: 2, price: 99.5, vol: 12 }]);
  assert.deepEqual(M.nakedPocs([{ h: 5, l: 1, fp: [[2, 3, 3], [4, 3, 3]] }]), [{ i: 0, price: 2, vol: 6 }]);   // tie -> the lowest
});

test('nakedPocs touched: a POC a later bar reached comes with that bar (hit), a naked one with hit null; the default list is unchanged', () => {
  const bars = [
    { h: 100.25, l: 100, fp: [[100, 5, 5], [100.25, 2, 2]] },        // POC 100, first reached by bar 2
    { h: 102, l: 102, fp: [[102, 3, 3]] },                           // POC 102, never reached
    { h: 100.5, l: 99.5, fp: [[100, 1, 1], [99.5, 6, 6]] },          // POC 99.5
    { h: 101, l: 100.75, fp: [[100.75, 4, 4]] },
    { blank: true },
    { h: 100.5, l: 100.25 },
  ];
  assert.deepEqual(M.nakedPocs(bars, 0, 5, true), [
    { i: 0, price: 100, vol: 10, hit: 2 }, { i: 1, price: 102, vol: 6, hit: null }, { i: 2, price: 99.5, vol: 12, hit: null }, { i: 3, price: 100.75, vol: 8, hit: null },
  ]);
  const naked = M.nakedPocs(bars, 0, 5, true).filter((r) => r.hit == null).map(({ i, price, vol }) => ({ i, price, vol }));
  assert.deepEqual(naked, M.nakedPocs(bars));                                           // the old call still answers the untouched ones, same shape
  // a blank slot (the last close as every price) is not a touch; the first real bar that reaches the price is
  const gap = [{ h: 103, l: 101, fp: [[102, 3, 3]] }, { h: 102, l: 102, blank: 'closed' }, { h: 99, l: 98 }, { h: 102.5, l: 101.5 }, { h: 102, l: 101 }];
  assert.deepEqual(M.nakedPocs(gap, 0, 0, true), [{ i: 0, price: 102, vol: 6, hit: 3 }]);
});

test('tpo: letters per 30 minutes, range vs traded rows, initial balance, single prints, POC and value area', () => {
  const t0 = 1700000000000, m = 60000;
  const bars = [
    { ms: t0, l: 10, h: 12 }, { ms: t0 + 15 * m, l: 11, h: 14 },        // A
    { ms: t0 + 30 * m, l: 12, h: 13 },                                  // B
    { ms: t0 + 60 * m, l: 13, h: 16 },                                  // C (nothing traded in the period after B... it starts at 60)
  ];
  const r = M.tpo(bars, 30, 1, 'range', { tick: 1 });
  assert.deepEqual(r.rows.map((x) => [x.price, x.n]), [[10, 1], [11, 1], [12, 2], [13, 3], [14, 2], [15, 1], [16, 1]]);
  assert.deepEqual(r.rows[3].per, [0, 1, 2]);
  assert.equal(r.periods, 3);
  assert.deepEqual([r.poc, r.vah, r.val], [13, 15, 11]);               // 3 of 11, then both neighbours twice (sierra)
  assert.deepEqual(r.ib, { hi: 14, lo: 10 });                          // A and B only
  assert.deepEqual(r.singles, [10, 11, 15, 16]);
  assert.deepEqual(M.letterOf(0) + M.letterOf(25) + M.letterOf(26) + M.letterOf(52), 'AZaA');
  const one = [{ ms: t0, l: 10, h: 12, fp: [[10, 1, 1], [12, 1, 1]] }];
  assert.deepEqual(M.tpo(one, 30, 1, 'traded', { tick: 1 }).rows.map((x) => x.price), [10, 12]);
  assert.deepEqual(M.tpo(one, 30, 1, 'range', { tick: 1 }).rows.map((x) => x.price), [10, 11, 12]);
  assert.deepEqual(M.tpo([{ ms: t0, l: 10, h: 12 }], 30, 1, 'traded', { tick: 1 }).rows.length, 3);   // no fp: the range
  assert.deepEqual(M.tpo(one, 30, 2, 'range', { tick: 1 }).rows.map((x) => x.price), [10, 12]);        // two ticks to a row
  assert.equal(M.tpo([], 30, 1, 'range', { tick: 1 }), null);
  assert.equal(M.tpo(bars, 30, 1, 'range', {}), null);
});

const O = (t, size, side, price = 100) => ({ t, price, lo: price, hi: price, size, side, n: 1 });

test('ordersOf: the wire\'s ag rows filtered by size and side; a bar without ag gives none', () => {
  const bar = { ag: [[1000, 100.5, 100.25, 100.75, 25, 1, 3], [2000, 100, 100, 100, 12, -1, 1], [3000, 101, 101, 101, 60, 1, 2]] };
  assert.deepEqual(M.ordersOf(bar, 20).map((o) => o.size), [25, 60]);
  assert.deepEqual(M.ordersOf(bar, 20, 30).map((o) => o.size), [25]);
  assert.deepEqual(M.ordersOf(bar, 10, 0, 'sell'), [{ t: 2000, price: 100, lo: 100, hi: 100, size: 12, side: -1, n: 1 }]);
  assert.deepEqual(M.ordersOf(bar, 1, 0, 'buy').map((o) => o.t), [1000, 3000]);
  assert.deepEqual(M.ordersOf({}, 1), []);
  assert.deepEqual(M.ordersOf(null, 1), []);
});

test('clusterOrders: Bookmap dots 100 / [20,15,35,270] = one of 300 with carry 40; bars 100 / [50,100] = one of 150; carry runs on', () => {
  const dots = M.clusterOrders([20, 15, 35, 270].map((s, i) => O(i, s, 1)), 'volume', 100);
  assert.equal(dots.length, 1);
  assert.deepEqual([dots[0].size, dots[0].carry, dots[0].count, dots[0].t, dots[0].t1], [300, 40, 4, 0, 3]);
  const bars = M.clusterOrders([50, 100].map((s, i) => O(i, s, -1)), 'overshoot', 100);
  assert.deepEqual([bars.length, bars[0].size, bars[0].carry, bars[0].side], [1, 150, 0, -1]);
  const run = M.clusterOrders([O(0, 270, 1), O(1, 80, 1)], 'volume', 100);
  assert.deepEqual(run.map((c) => [c.size, c.carry, c.count]), [[200, 70, 1], [100, 50, 1]]);
  assert.deepEqual(M.clusterOrders([O(0, 40, 1), O(1, 30, 1)], 'volume', 100), []);   // never reaches the size
});

test('clusterOrders: none keeps each; price runs until the price changes; priceside also until the side changes', () => {
  const l = [O(0, 10, 1, 100), O(1, 20, -1, 100), O(2, 30, 1, 101), O(3, 40, 1, 101), O(4, 50, 1, 100)];
  assert.equal(M.clusterOrders(l, 'none', 0).length, 5);
  assert.equal(M.clusterOrders(l, 'bogus', 100).length, 5);
  const p = M.clusterOrders(l, 'price', 0);
  assert.deepEqual(p.map((c) => [c.size, c.count, c.buy, c.sell, c.side, c.price]), [[30, 2, 10, 20, -1, (10 * 100 + 20 * 100) / 30], [70, 2, 70, 0, 1, 101], [50, 1, 50, 0, 1, 100]]);
  assert.deepEqual(M.clusterOrders(l, 'priceside', 0).map((c) => c.size), [10, 20, 70, 50]);
  assert.deepEqual(M.clusterOrders([], 'price', 0), []);
  assert.equal(M.clusterOrders([O(0, 10, 1), O(1, 10, -1)], 'price', 0)[0].side, 1);   // a tie goes to the buyers
});

test('clusterStats: delta, volume, trades (fpn, else n), max / min delta, delta / volume, duration; missing is null', () => {
  const b = { d: 12, v: 100, n: 99, dmax: 30, dmin: -5, ms: 1000, fpn: [[100, 10, 12], [100.25, 8, 10]] };
  assert.deepEqual(M.clusterStats(b, 61000), { delta: 12, volume: 100, trades: 40, maxDelta: 30, minDelta: -5, deltaPct: 0.12, duration: 60000 });
  assert.deepEqual(M.clusterStats({ d: -3, v: 10, n: 7, ms: 5 }), { delta: -3, volume: 10, trades: 7, maxDelta: null, minDelta: null, deltaPct: -0.3, duration: null });
  assert.deepEqual(M.clusterStats({}), { delta: null, volume: null, trades: null, maxDelta: null, minDelta: null, deltaPct: null, duration: null });
  assert.equal(M.clusterStats({ d: 0, v: 5, dmax: 0 }).maxDelta, 0);
});

test('deltaTurnaround: ATAS 3-bar up and down as written; the corrected option compares the high', () => {
  const up = [{ o: 105, c: 103, h: 105.5, l: 102.5 }, { o: 103, c: 101, h: 103.5, l: 100.5 }, { o: 101, c: 103, h: 103.5, l: 100, d: 15 }];
  assert.deepEqual(M.deltaTurnaround(up, 0, 2), [{ i: 2, dir: 1, price: 100, delta: 15 }]);
  assert.deepEqual(M.deltaTurnaround([up[0], up[1], { ...up[2], l: 101 }], 0, 2), []);          // low above the bar before's low
  assert.deepEqual(M.deltaTurnaround([up[0], up[1], { ...up[2], d: -1 }], 0, 2), []);           // delta not positive
  const down = [{ o: 100, c: 102, h: 102.5, l: 99.5 }, { o: 102, c: 104, h: 104, l: 101.5 }, { o: 104, c: 102, h: 103, l: 101, d: -9 }];
  assert.deepEqual(M.deltaTurnaround(down, 0, 2), [{ i: 2, dir: -1, price: 103, delta: -9 }]);   // 103 >= the previous LOW 101.5
  assert.deepEqual(M.deltaTurnaround(down, 0, 2, { fix: true }), []);                            // 103 < the previous high 104
  assert.deepEqual(M.deltaTurnaround([up[0], { blank: true }, up[2]], 0, 2), []);
  assert.deepEqual(M.deltaTurnaround(up, 0, 1), []);
});

test('deltaStrength: a closing delta within min..max percent of the bar\'s best delta; no dmax / dmin, no mark', () => {
  const bars = [
    { o: 1, c: 2, h: 2, l: 1, d: 90, dmax: 100, dmin: -4 },
    { o: 1, c: 2, h: 2, l: 1, d: 50, dmax: 100, dmin: 0 },
    { o: 2, c: 1, h: 2, l: 1, d: -85, dmax: 3, dmin: -100 },
    { o: 1, c: 2, h: 2, l: 1, d: 70 },
    { o: 1, c: 2, h: 2, l: 1, d: 0, dmax: 5, dmin: -5 },
    { o: 1, c: 2, h: 2, l: 1, d: 100, dmax: 100, dmin: 0 },
  ];
  assert.deepEqual(M.deltaStrength(bars, 0, 5), [{ i: 0, dir: 1, pct: 90 }, { i: 2, dir: -1, pct: 85 }, { i: 5, dir: 1, pct: 100 }]);
  assert.deepEqual(M.deltaStrength(bars, 0, 5, { min: 40, max: 60 }).map((x) => x.i), [1]);
});

test('mwAbsorptions: an imbalance whose price a close then leaves by N ticks the other way, within the window', () => {
  const fp = [[100, 1, 1], [101, 2, 12], [102, 3, 3]];       // buy imbalance at 101 (12 vs 1 below), sell imbalance at 102 (3 vs nothing above)
  const bars = [{ c: 101, h: 102, l: 100, fp }, { c: 96.5, h: 101, l: 96, fp: [[96.5, 1, 1]] }, { c: 101, h: 101, l: 100 }];
  const r = M.mwAbsorptions(bars, 0, 0, { tick: 1, ticks: 4, within: 3, imb: { ratio: 3 } });
  assert.deepEqual(r, [{ i: 0, j: 1, dir: -1, price: 101 }]);
  assert.deepEqual(M.mwAbsorptions(bars, 0, 0, { tick: 1, ticks: 4, within: 0 }), []);          // only its own close counts
  assert.deepEqual(M.mwAbsorptions(bars, 0, 0, { tick: 1, ticks: 6, within: 3 }), []);           // 96.5 is only 4.5 below
  const up = [{ c: 101, h: 102, l: 100, fp }, { c: 107, h: 107, l: 101 }];
  assert.deepEqual(M.mwAbsorptions(up, 0, 0, { tick: 1, ticks: 4, within: 1 }), [{ i: 0, j: 1, dir: 1, price: 102 }]);
  assert.deepEqual(M.mwAbsorptions(bars, 0, 0, {}), []);                                          // no tick
});

test('mwAbsorptions: a close exactly N ticks away counts on a 0.1 / 0.01 / 0.00005 tick too, not only on a binary one', () => {
  const px = (k, tick) => +(k * tick).toFixed(6);                                                 // the wire's price: round(k * tick, 6)
  for (const [tick, k0] of [[0.1, 20000], [0.01, 6000], [0.00005, 21000], [0.25, 20000]]) {      // GC, CL, 6E, ES
    for (let k = k0; k < k0 + 400; k++) {
      const P = (d) => px(k + d, tick), o = { tick, ticks: 4, within: 1 }, at = `tick ${tick} key ${k}`;
      const buy = { c: P(0), h: P(0), l: P(-1), fp: [[P(-1), 1, 1], [P(0), 1, 12]] };            // a buy imbalance at P
      assert.deepEqual(M.mwAbsorptions([buy, { c: P(-4), h: P(0), l: P(-4) }], 0, 0, o), [{ i: 0, j: 1, dir: -1, price: P(0) }], `buy, 4 ticks: ${at}`);
      assert.deepEqual(M.mwAbsorptions([buy, { c: P(-3), h: P(0), l: P(-3) }], 0, 0, o), [], `buy, 3 ticks: ${at}`);
      const sell = { c: P(0), h: P(1), l: P(0), fp: [[P(0), 1, 1], [P(1), 12, 1]] };             // a sell imbalance at P + 1 tick
      assert.deepEqual(M.mwAbsorptions([sell, { c: P(5), h: P(5), l: P(0) }], 0, 0, o), [{ i: 0, j: 1, dir: 1, price: P(1) }], `sell, 4 ticks: ${at}`);
      assert.deepEqual(M.mwAbsorptions([sell, { c: P(4), h: P(4), l: P(0) }], 0, 0, o), [], `sell, 3 ticks: ${at}`);
    }
  }
});

test('rowText: trades, dominant side %, price and the diagonal differences', () => {
  assert.deepEqual(M.rowText('trades', [100, 9, 12], { trades: [100, 3, 4] }), { l: '3', r: '4' });
  assert.deepEqual(M.rowText('trades', [100, 9, 12]), {});
  assert.deepEqual(M.rowText('dom', [100, 25, 75]), { c: '+75' });
  assert.deepEqual(M.rowText('dom', [100, 60, 40]), { c: '-60' });
  assert.deepEqual(M.rowText('dom', [100, 5, 5]), { c: '+50' });
  assert.deepEqual(M.rowText('dom', [100, 0, 0]), {});
  assert.deepEqual(M.rowText('price', [100.25, 1, 1], { dec: 2 }), { c: '100.25' });
  assert.deepEqual(M.rowText('price', [100, 1, 1], { dec: 0 }), { c: '100' });
  // Sierra B row: left = Ask(A) - Bid(B) = 56 - 293, right = Ask(B) - Bid(C) = 359 - 48
  assert.deepEqual(M.rowText('diag', SIERRA[1], { above: SIERRA[0], below: SIERRA[2] }), { l: '-237', r: '311' });
  assert.deepEqual(M.rowText('diag', SIERRA[0], { below: SIERRA[1] }), { l: '0', r: '-237' });   // no row above: 0
  assert.deepEqual(M.rowText('nope', [1, 1, 1]), {});
});

test('a blank slot (the last close as every price) neither covers a POC nor adds a TPO letter', () => {
  const blank = { ms: 120000, h: 102, l: 102, o: 102, c: 102, v: 0, d: 0, blank: 'closed' };
  const bars = [{ ms: 0, h: 103, l: 101, fp: [[102, 3, 3]] }, blank];
  assert.deepEqual(M.nakedPocs(bars), [{ i: 0, price: 102, vol: 6 }]);
  assert.equal(M.tpo([{ ms: 0, h: 101, l: 101 }, { ...blank, ms: 3600000 }], 30, 1, 'range', { tick: 1 }).periods, 1);
});
