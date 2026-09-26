import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const P = require('../../homebase/static/charts/position.js');
const D = require('../../homebase/static/charts/drawings.js');

const MIN = 60000;
const T0 = 1_790_000_000_000;
const bars = [0, 1, 2, 3, 4].map((i) => ({ ms: T0 + i * MIN }));      // five 1m bars; bar i at x = 100 + 10 i
const CTX = { bars, isTime: true, barMs: MIN, tick: 0.25, coord: (i) => 100 + i * 10 };
const geo = { x: (t) => D.timeToX(t, CTX), y: (p) => 1000 - p };     // price p at y = 1000 - p
const box = (type, entry, target, stop, qty = 1, t0 = bars[1].ms, t1 = bars[3].ms) =>
  ({ id: 'p', type, qty, points: [{ t: t0, p: entry }, { t: t1, p: target }, { t: t1, p: stop }] });
const LONG = box('long', 900, 920, 890);        // x 110..130 · entry y 100, target y 80, stop y 110
const SHORT = box('short', 900, 880, 910);      // target y 120, stop y 90

test('a new box risks 8% of the pane in price, on the tick grid, at least 4 ticks', () => {
  assert.equal(P.RISK_PANE, 0.08);
  assert.equal(P.WIDTH_BARS, 20);
  assert.equal(P.MIN_RISK_TICKS, 4);
  assert.equal(P.risk(80, 0.25), 80);
  assert.equal(P.risk(12.37, 0.25), 12.25);
  assert.equal(P.risk(0.6, 0.25), 1);            // 4 ticks of 0.25
  assert.equal(P.risk(0.37, 0.1), 0.4);          // 4 ticks of 0.1, no float dust
  assert.equal(P.risk(1.234, 0.1), 1.2);
});

test('a new long reads RR 1:2: the stop one risk below, the target two above; a short is mirrored', () => {
  const t1 = T0 + 20 * MIN;
  assert.deepEqual(P.create('long', T0, t1, 30900, 25, 0.25),
    { type: 'long', qty: 1, points: [{ t: T0, p: 30900 }, { t: t1, p: 30950 }, { t: t1, p: 30875 }] });
  assert.deepEqual(P.create('short', T0, t1, 30900, 25, 0.25).points.map((q) => q.p), [30900, 30850, 30925]);
  assert.deepEqual(P.create('long', T0, t1, 2650.3, 0.4, 0.1).points.map((q) => q.p), [2650.3, 2651.1, 2649.9]);
  assert.equal(P.labels(P.create('long', T0, t1, 30900, 25, 0.25), 20, 0.25).center, 'RR 1:2 · Qty 1');
  assert.equal(P.isPosition(LONG), true);
  assert.equal(P.isPosition({ type: 'trend' }), false);
});

test('handles: the left edge on entry, target and stop; the right edge on the entry', () => {
  assert.deepEqual(P.handles(LONG, geo), [[110, 100], [110, 80], [110, 110], [130, 100]]);
  assert.equal(P.handles(LONG, { ...geo, y: () => null }), null);
});

test('hitTest: handles first, then anywhere inside the box', () => {
  assert.deepEqual(P.hitTest(LONG, { x: 111, y: 101 }, geo), { part: 'handle', index: 0 });
  assert.deepEqual(P.hitTest(LONG, { x: 109, y: 81 }, geo), { part: 'handle', index: 1 });
  assert.deepEqual(P.hitTest(LONG, { x: 110, y: 112 }, geo), { part: 'handle', index: 2 });
  assert.deepEqual(P.hitTest(LONG, { x: 131, y: 100 }, geo), { part: 'handle', index: 3 });
  assert.deepEqual(P.hitTest(LONG, { x: 120, y: 90 }, geo), { part: 'body' });
  assert.deepEqual(P.hitTest(SHORT, { x: 125, y: 115 }, geo), { part: 'body' });
  assert.equal(P.hitTest(LONG, { x: 140, y: 90 }, geo), null);
  assert.equal(P.hitTest(LONG, { x: 120, y: 70 }, geo), null);
});

test('long handles: the entry stays a tick inside, target and stop a tick beyond it, the edges a bar apart', () => {
  const pts = (d) => d.points.map((q) => [q.t, q.p]);
  assert.deepEqual(pts(P.setHandle(LONG, 0, bars[2].ms, 905, CTX)), [[bars[2].ms, 905], [bars[3].ms, 920], [bars[3].ms, 890]]);
  assert.equal(P.setHandle(LONG, 0, bars[1].ms, 930, CTX).points[0].p, 919.75);
  assert.equal(P.setHandle(LONG, 0, bars[1].ms, 880, CTX).points[0].p, 890.25);
  assert.equal(P.setHandle(LONG, 0, bars[4].ms, 900, CTX).points[0].t, bars[2].ms);      // never past the right edge
  assert.equal(P.setHandle(LONG, 1, bars[0].ms, 950, CTX).points[1].p, 950);
  assert.deepEqual(P.setHandle(LONG, 1, bars[0].ms, 890, CTX).points[1], { t: bars[3].ms, p: 900.25 });   // time ignored
  assert.equal(P.setHandle(LONG, 2, bars[0].ms, 870, CTX).points[2].p, 870);
  assert.equal(P.setHandle(LONG, 2, bars[0].ms, 910, CTX).points[2].p, 899.75);
  assert.deepEqual(pts(P.setHandle(LONG, 3, bars[4].ms, 1, CTX)), [[bars[1].ms, 900], [bars[4].ms, 920], [bars[4].ms, 890]]);
  assert.equal(P.setHandle(LONG, 3, bars[0].ms, 1, CTX).points[1].t, bars[2].ms);         // at least a bar after t0
  assert.equal(P.setHandle(LONG, 3, T0 + 30 * MIN, 1, CTX).points[2].t, T0 + 30 * MIN);   // beyond the data: kept
  assert.deepEqual(LONG.points[0], { t: bars[1].ms, p: 900 });                            // the original is untouched
});

test('short handles mirror the clamps', () => {
  assert.equal(P.setHandle(SHORT, 0, bars[1].ms, 870, CTX).points[0].p, 880.25);
  assert.equal(P.setHandle(SHORT, 0, bars[1].ms, 920, CTX).points[0].p, 909.75);
  assert.equal(P.setHandle(SHORT, 1, bars[1].ms, 905, CTX).points[1].p, 899.75);
  assert.equal(P.setHandle(SHORT, 1, bars[1].ms, 860, CTX).points[1].p, 860);
  assert.equal(P.setHandle(SHORT, 2, bars[1].ms, 895, CTX).points[2].p, 900.25);
  assert.equal(P.setHandle(SHORT, 2, bars[1].ms, 930, CTX).points[2].p, 930);
});

test('labels: price, move, percent of the entry, ticks and dollars (point value × qty)', () => {
  assert.deepEqual(P.labels(box('long', 30900, 30950, 30875), 20, 0.25), {
    target: 'Target 30,950.00 · +50.00 (0.16%) · 200 ticks · +$1,000',
    stop: 'Stop 30,875.00 · −25.00 (0.08%) · 100 ticks · −$500',
    center: 'RR 1:2 · Qty 1' });
  const three = box('long', 30900, 30937.5, 30875, 3);
  assert.equal(P.labels(three, 20, 0.25).target, 'Target 30,937.50 · +37.50 (0.12%) · 150 ticks · +$2,250');
  assert.equal(P.labels(three, 20, 0.25).center, 'RR 1:1.5 · Qty 3');
});

test('without a point value the labels show no dollars', () => {
  const l = P.labels(box('long', 30900, 30950, 30875), null, 0.25);
  assert.equal(l.target, 'Target 30,950.00 · +50.00 (0.16%) · 200 ticks');
  assert.equal(l.stop, 'Stop 30,875.00 · −25.00 (0.08%) · 100 ticks');
});

test('a short\'s target is a gain and its stop a loss', () => {
  const l = P.labels(box('short', 30900, 30850, 30925), 20, 0.25);
  assert.equal(l.target, 'Target 30,850.00 · +50.00 (0.16%) · 200 ticks · +$1,000');
  assert.equal(l.stop, 'Stop 30,925.00 · −25.00 (0.08%) · 100 ticks · −$500');
});

test('odd ticks and cents: one ZN tick is $15.63', () => {
  const zn = box('long', 112.5, 112.515625, 112.484375);
  assert.equal(P.labels(zn, 1000, 0.015625).target, 'Target 112.515625 · +0.015625 (0.01%) · 1 tick · +$15.63');
  assert.equal(P.fmtUsd(1000), '$1,000');
  assert.equal(P.fmtUsd(-0.5), '$0.50');
  assert.equal(P.fmtUsd(1234567.5), '$1,234,567.50');
});

test('RR is 1:X with at most 2 decimals, trailing zeros trimmed', () => {
  assert.equal(P.rr(box('long', 100, 104, 97)), '1:1.33');
  assert.equal(P.rr(box('short', 100, 99, 102)), '1:0.5');
  assert.equal(P.rr(box('long', 100, 110, 95)), '1:2');
});

/* ---- the outcome on the chart's bars ---- */
const run = (...ohlc) => ohlc.map(([o, h, l, c], i) => ({ ms: T0 + i * MIN, o, h, l, c }));
const L100 = (qty = 1, t1 = T0 + 5 * MIN) => box('long', 100, 110, 95, qty, T0 + MIN, t1);   // from bar 1

test('not entered: no bar from the bar holding t0 up to t1 trades the entry', () => {
  const bs = run([100, 101, 99, 100], [102, 104, 101, 103], [103, 105, 102, 104], [104, 106, 103, 105],
    [105, 106, 104, 105], [105, 107, 104, 106]);
  assert.deepEqual(P.outcome(L100(), bs, 20, 0.25), { kind: 'none', text: 'Not entered', path: null });   // bar 0 is before t0
  assert.deepEqual(P.outcome(L100(), [], 20, 0.25), { kind: 'none', text: 'Not entered', path: null });
});

test('closed at the target or the stop, with the path from the entry bar to the exit bar', () => {
  const up = run([101, 102, 100.5, 101], [101, 101, 99, 100], [100, 106, 99.5, 105], [105, 111, 104, 110],
    [110, 112, 109, 111], [111, 112, 110, 111]);
  assert.deepEqual(P.outcome(L100(), up, 20, 0.25),
    { kind: 'closed', text: 'Closed +$200', path: { a: { t: T0 + MIN, p: 100 }, b: { t: T0 + 3 * MIN, p: 110 } } });
  assert.equal(P.outcome(L100(2), up, 20, 0.25).text, 'Closed +$400');
  assert.equal(P.outcome(L100(), up, null, 0.25).text, 'Closed +10.00');
  const down = run([101, 102, 100.5, 101], [101, 101, 99, 100], [100, 101, 96, 97], [97, 98, 94, 95],
    [95, 96, 93, 94], [94, 95, 93, 94]);
  assert.deepEqual(P.outcome(L100(), down, 20, 0.25),
    { kind: 'closed', text: 'Closed −$100', path: { a: { t: T0 + MIN, p: 100 }, b: { t: T0 + 3 * MIN, p: 95 } } });
  assert.equal(P.outcome(L100(), down, null, 0.25).text, 'Closed −5.00');
});

test('bars cannot tell: both levels inside one bar, or the entry bar already at a level', () => {
  const both = run([101, 102, 100.5, 101], [101, 101, 99, 100], [100, 111, 94, 100], [100, 101, 99, 100]);
  assert.deepEqual(P.outcome(L100(), both, 20, 0.25), { kind: 'ambiguous', text: 'Stop and target in one bar', path: null });
  const touch = run([101, 102, 100.5, 101], [101, 102, 94.5, 100], [100, 101, 99, 100]);
  assert.deepEqual(P.outcome(L100(), touch, 20, 0.25),
    { kind: 'ambiguous', text: 'Entry bar touched stop/target', path: null });
});

test('still open at the last close, or "open at end" when t1 is before the last bar', () => {
  const flat = run([101, 102, 100.5, 101], [101, 101, 99, 100], [100, 102, 99, 101], [101, 104, 100, 103]);
  assert.deepEqual(P.outcome(L100(1, T0 + 10 * MIN), flat, 20, 0.25), { kind: 'open', text: 'Open +$60', path: null });
  assert.equal(P.outcome(L100(1, T0 + 3 * MIN), flat, 20, 0.25).kind, 'open');           // t1 on the last bar: open
  assert.deepEqual(P.outcome(L100(1, T0 + 2 * MIN), flat, 20, 0.25),
    { kind: 'expired', text: 'Open at end +$20', path: null });
  const under = run([101, 102, 100.5, 101], [101, 101, 98, 98.5], [98.5, 99, 97, 98]);
  assert.equal(P.outcome(L100(1, T0 + 9 * MIN), under, 20, 0.25).text, 'Open −$40');
  assert.equal(P.outcome(L100(1, T0 + 9 * MIN), under, null, 0.25).text, 'Open −2.00');
  const even = run([101, 102, 100.5, 101], [101, 101, 99, 100]);
  assert.equal(P.outcome(L100(1, T0 + 9 * MIN), even, 20, 0.25).text, 'Open $0');
});

test('a short is mirrored; the entry may fill on the bar holding t0', () => {
  const s = box('short', 100, 90, 105, 1, T0 + MIN, T0 + 5 * MIN);
  const fall = run([99, 99.5, 98.5, 99], [99, 101, 98, 100], [100, 100.5, 95, 96], [96, 97, 89, 90], [90, 91, 89, 90]);
  assert.deepEqual(P.outcome(s, fall, 20, 0.25),
    { kind: 'closed', text: 'Closed +$200', path: { a: { t: T0 + MIN, p: 100 }, b: { t: T0 + 3 * MIN, p: 90 } } });
  const mid = box('long', 100, 110, 95, 1, T0 + MIN + 30000, T0 + 9 * MIN);
  const bs = run([101, 102, 100.5, 101], [101, 101, 99, 100], [100, 111, 99.5, 110]);
  assert.equal(P.outcome(mid, bs, 20, 0.25).text, 'Closed +$200');
});

test('the settings dialog\'s check: the order for the type, a tick apart, qty 1-10,000', () => {
  assert.equal(P.validate('long', 100, 110, 95, 1, 0.25), '');
  assert.equal(P.validate('short', 100, 90, 105, 10000, 0.25), '');
  assert.equal(P.validate('long', 2650.3, 2650.4, 2650.2, 1, 0.1), '');          // one tick of 0.1, float dust and all
  assert.match(P.validate('long', 100, 100, 95, 1, 0.25), /stop < entry < target/);
  assert.match(P.validate('long', 100, 110, 100.25, 1, 0.25), /stop < entry < target/);
  assert.match(P.validate('short', 100, 105, 90, 1, 0.25), /target < entry < stop/);
  assert.match(P.validate('long', 100, 110, 95, 0, 0.25), /Qty/);
  assert.match(P.validate('long', 100, 110, 95, 10001, 0.25), /Qty/);
  assert.match(P.validate('long', 100, 110, 95, 1.5, 0.25), /Qty/);
  assert.match(P.validate('long', NaN, 110, 95, 1, 0.25), /prices/);
});
