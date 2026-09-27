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

/* ---------------------------------------------------------------- rule geometry (2026-09-27)
   The strategy records every level it PLACED, so the page must read a session at a glance:
   style by role (never by parsing the name beyond the side), label each line at its right-hand
   end, stack labels that collide, and hide them when the session is too narrow to carry text. */

const P = { up: '#089981', down: '#F23645', accent: '#2962FF', text2: '#787B86' };
const h = (name, role, price = 1) => ({ name, price, role, date: '2024-01-02' });

test('hlineStyle: role picks the colour — entry takes its own side, sl red, tp green, anchor/level neutral', () => {
  assert.equal(X.hlineStyle(h('Long entry +5', 'entry'), P).color, P.accent);
  assert.equal(X.hlineStyle(h('Short entry −5', 'entry'), P).color, P.down);
  assert.equal(X.hlineStyle(h('Long SL', 'sl'), P).color, P.down);
  assert.equal(X.hlineStyle(h('Long TP', 'tp'), P).color, P.up);
  assert.equal(X.hlineStyle(h('anchor · NFP', 'anchor'), P).color, P.text2);
  assert.equal(X.hlineStyle(h('stop', 'level'), P).color, P.text2);
  assert.equal(X.hlineStyle(h('legacy', undefined), P).color, P.text2);   // a record from before roles
});

test('hlineStyle: the anchor is solid, a live level dashed, a planned / unfilled one dimmer and finer', () => {
  assert.deepEqual(X.hlineStyle(h('anchor', 'anchor'), P).dash, []);
  const live = X.hlineStyle(h('Long SL', 'sl'), P);
  const planned = X.hlineStyle(h('Long SL (planned)', 'sl'), P);
  const gone = X.hlineStyle(h('Short SL (not filled)', 'sl'), P);
  assert.equal(live.alpha, 1);
  assert.equal(planned.alpha < 1 && gone.alpha === planned.alpha, true);
  assert.deepEqual(planned.dash, gone.dash);
  // "more finely dashed": shorter ink, longer gap than the live counterpart
  assert.equal(planned.dash[0] < live.dash[0] && planned.dash[1] > live.dash[1], true);
  assert.equal(planned.color, live.color);          // dimmed by alpha, not by a different colour
});

test('hlineLabel: the name and the price, as the tester shows every price', () => {
  assert.equal(X.hlineLabel(h('Long entry +5', 'entry', 30925)), 'Long entry +5 · 30,925.00');
  assert.equal(X.hlineLabel(h('Short SL (not filled)', 'sl', 2050.4)), 'Short SL (not filled) · 2,050.40');
});

test('stackLabels: labels that do not collide keep their own y', () => {
  assert.deepEqual(X.stackLabels([{ y: 10, t: 'a' }, { y: 50, t: 'b' }], 12, 0, 100).map((r) => r.y), [10, 50]);
});

test('stackLabels: colliding labels are pushed apart by one row, in price order', () => {
  const rows = [{ y: 16, t: 'c' }, { y: 10, t: 'a' }, { y: 14, t: 'b' }];
  assert.deepEqual(X.stackLabels(rows, 12, 0, 500), [{ y: 10, t: 'a' }, { y: 22, t: 'b' }, { y: 34, t: 'c' }]);
  assert.deepEqual(rows.map((r) => r.y), [16, 10, 14]);        // pure: the input is untouched
});

test('stackLabels: a stack that runs past the pane is pushed back up, keeping its spacing', () => {
  assert.deepEqual(X.stackLabels([{ y: 95 }, { y: 96 }, { y: 97 }], 12, 0, 100).map((r) => r.y), [76, 88, 100]);
  assert.deepEqual(X.stackLabels([{ y: -5 }], 12, 0, 100).map((r) => r.y), [0]);
});

test('stackLabels: nothing in, nothing out', () => {
  assert.deepEqual(X.stackLabels([], 12, 0, 100), []);
  assert.deepEqual(X.stackLabels(null, 12, 0, 100), []);
});

test('labelsFit: a session narrower than the minimum draws its lines but no text', () => {
  assert.equal(X.labelsFit(100, 100 + X.LABEL_MIN_PX), true);
  assert.equal(X.labelsFit(100, 100 + X.LABEL_MIN_PX - 1), false);
  assert.equal(X.labelsFit(null, 200), false);
});

test('hlineTip: hover text names the level, its price and the session it belongs to', () => {
  assert.equal(X.hlineTip(h('Long TP', 'tp', 30925)), 'Long TP · 30,925.00\n2024-01-02');
});
