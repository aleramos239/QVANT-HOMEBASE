import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const X = require('../../homebase/static/charts/testerlayer.js');

const BARS = [
  { ms: 1000, tt: 1000, s: '2024-01-02' },
  { ms: 2000, tt: 2000, s: '2024-01-02' },
  { ms: 3000, tt: 3000, s: '2024-01-03' },
  { ms: 4000, tt: 4000, s: '2024-01-03' },
];

test('tradesInRange: keeps a trade whose entry or exit overlaps the loaded window, drops the rest', () => {
  const trades = [
    { entry_ms: 500, exit_ms: 900 },     // entirely before the first bar: dropped
    { entry_ms: 500, exit_ms: 1500 },    // exit lands inside: kept
    { entry_ms: 2500, exit_ms: 3500 },   // fully inside: kept
    { entry_ms: 3900, exit_ms: 4200 },   // entry before the coverage end (barMs 1000 -> end 5000): kept
    { entry_ms: 5000, exit_ms: 6000 },   // entirely past the coverage end: dropped
  ];
  const kept = X.tradesInRange(trades, BARS, 1000);
  assert.deepEqual(kept.map((t) => t.entry_ms), [500, 2500, 3900]);
});

test('tradesInRange: a non-time chart (barMs 0) never bounds the far end', () => {
  const trades = [{ entry_ms: 999999, exit_ms: 1000000 }];
  assert.deepEqual(X.tradesInRange(trades, BARS, 0), trades);
});

test('tradesInRange: no bars loaded -> nothing, whatever the trades are', () => {
  assert.deepEqual(X.tradesInRange([{ entry_ms: 1, exit_ms: 2 }], [], 1000), []);
  assert.deepEqual(X.tradesInRange([{ entry_ms: 1, exit_ms: 2 }], null, 1000), []);
});

test('sessionSpan: the contiguous bar-index run for a session date, or null when it never loaded', () => {
  assert.deepEqual(X.sessionSpan(BARS, '2024-01-02'), [0, 1]);
  assert.deepEqual(X.sessionSpan(BARS, '2024-01-03'), [2, 3]);
  assert.equal(X.sessionSpan(BARS, '2024-01-09'), null);
});

test('sessionSpan: bounded to a visible window, as the primitive uses it', () => {
  assert.deepEqual(X.sessionSpan(BARS, '2024-01-03', 0, 2), [2, 2]);   // bar 3 is out of the window
  assert.equal(X.sessionSpan(BARS, '2024-01-02', 2, 3), null);         // the date's bars are out of the window
});

test('plotPoints: maps [t_ms, v] to the covering bar\'s tt, drops a point before the first bar, keeps the last value per tt', () => {
  const pts = [[500, 1], [1000, 2], [1500, 3], [2000, 4], [2000, 5]];
  // 500 -> before bar 0: dropped. 1000 and 1500 both cover bar 0 (tt 1000): the later (1500 -> 3) wins.
  // 2000 and 2000 both cover bar 1 (tt 2000): the later (5) wins.
  assert.deepEqual(X.plotPoints(pts, BARS), [{ time: 1000, value: 3 }, { time: 2000, value: 5 }]);
});

test('plotPoints: a point past the last bar still lands on it (no upper bound, unlike a marker)', () => {
  assert.deepEqual(X.plotPoints([[9999, 7]], BARS), [{ time: 4000, value: 7 }]);
});

test('plotPoints: no bars -> []', () => {
  assert.deepEqual(X.plotPoints([[1, 2]], []), []);
  assert.deepEqual(X.plotPoints([[1, 2]], null), []);
});
