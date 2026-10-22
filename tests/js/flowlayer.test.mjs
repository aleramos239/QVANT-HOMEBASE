import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const C = '../../homebase/static/charts/';
const T0 = 1_700_000_000_000, BAR = 15 * 60_000;

/* One flow overlay on a stub chart: bar i is at x = i * step, price p at y = 1000 - px p (px 40: a 0.25 tick is 10 px high). */
function rig(indicators, bars, { step = 100, tick = 0.25, px = 40 } = {}) {
  const calls = { attach: [], detach: [] };
  class Layer { constructor(P) { this.P = P; this.redraws = 0; } redraw() { this.redraws++; } }
  globalThis.window = { HBLayers: { Layer }, HBLiquidity: require(C + 'liquidity.js'), HBDrawings: require(C + 'drawings.js'),
    HBFlowMath: require(C + 'flowmath.js') };
  const path = require.resolve(C + 'flowlayer.js');
  delete require.cache[path];
  require(path);
  const n = bars.length;
  const cell = {
    cfg: { root: 'NQ', indicators }, P: {}, tick, bars, isTime: () => true, barMs: () => BAR,
    chart: { timeScale: () => ({ getVisibleLogicalRange: () => ({ from: 0, to: n - 1 }), logicalToCoordinate: (i) => i * step,
      subscribeVisibleLogicalRangeChange() {}, unsubscribeVisibleLogicalRangeChange() {} }) },
    candles: { attachPrimitive: (l) => calls.attach.push(l), detachPrimitive: (l) => calls.detach.push(l), priceToCoordinate: (p) => 1000 - p * px },
  };
  const ctx = { log: [] };
  Object.defineProperty(ctx, 'fillStyle', { set: (v) => ctx.log.push(['fillStyle', v]) });
  for (const k of ['beginPath', 'moveTo', 'lineTo', 'stroke', 'fill', 'fillRect', 'strokeRect', 'arc', 'closePath', 'setLineDash', 'fillText']) ctx[k] = (...a) => ctx.log.push([k, ...a]);
  const target = { useMediaCoordinateSpace: (fn) => fn({ context: ctx, mediaSize: { width: 2000, height: 500 } }) };
  const o = window.HBFlowLayer.overlay(cell);
  const draw = (layer) => { ctx.log.length = 0; layer.draw(target); return ctx.log; };
  return { o, cell, calls, draw, ind: (id, params = {}) => ({ id, visible: true, params }) };
}
const count = (log, n) => log.filter((c) => c[0] === n).length;
const texts = (log) => log.filter((c) => c[0] === 'fillText').map((c) => c[1]);
const yOf = (p) => 1000 - p * 40;
const bar = (i, o = {}) => ({ ms: T0 + i * BAR, s: 'a', o: 100, h: 101, l: 99, c: 100, v: 10, d: 0, n: 5, ...o });

test('flow layer: the order-flow layers are attached only while their indicator is on, and dropped when it goes', () => {
  const r = rig([], [bar(0)]);
  assert.equal(r.calls.attach.length, 4);                          // bubbles, sweeps, runs, gaps: as before
  assert.deepEqual([r.o.ord, r.o.npoc, r.o.tpo, r.o.stat, r.o.mark], [undefined, undefined, undefined, undefined, undefined]);
  r.cell.cfg.indicators.push(r.ind('bigtrades'), r.ind('dstr'), r.ind('dturn'));
  r.o.onIndicators();
  assert.equal(r.calls.attach.length, 6);                          // the order layer, one mark layer for both marks
  assert.ok(r.o.ord && r.o.mark);
  r.cell.cfg.indicators[0].visible = false;                        // the eye
  r.o.onIndicators();
  assert.equal(r.calls.detach.length, 1);
  assert.equal(r.o.ord, null);
  r.o.destroy();
  assert.equal(r.calls.detach.length, 1 + 4 + 1);                  // the four, and the mark layer still there
});

test('flow layer: big trades keep to the size window and side, and cluster inside a bar', () => {
  const b = bar(1, { ag: [[T0 + BAR + 1, 80, 80, 80, 30, 1, 3], [T0 + BAR + 2, 80, 80, 80, 30, 1, 2], [T0 + BAR + 3, 81, 81, 81, 30, -1, 1], [T0 + BAR + 4, 82, 82, 82, 12, 1, 1]] });
  const r = rig([], [bar(0), b, bar(2)]);
  const g = r.ind('bigtrades', { min: 25 });
  r.cell.cfg.indicators.push(g);
  r.o.onIndicators();
  const arcs = (params) => { Object.assign(g.params, params); return count(r.draw(r.o.ord), 'arc'); };
  assert.equal(arcs({}), 3);                                       // the 12 is below the minimum
  assert.equal(arcs({ side: 'sell' }), 1);
  assert.equal(arcs({ side: 'all', max: 30 }), 3);
  assert.equal(arcs({ max: 0, min: 5 }), 4);
  assert.equal(arcs({ min: 25, cluster: 'priceside' }), 2);        // the two buys at 80 are one cluster of 60
  assert.equal(arcs({ max: 60 }), 2);
  assert.deepEqual(texts(r.draw(r.o.ord)), ['60', '30']);          // a bubble big enough to hold it carries its size
  assert.equal(arcs({ max: 0, cluster: 'volume', thr: 100 }), 1);  // 102 contracts in the bar: one cluster of 100, 2 carried
  assert.deepEqual(texts(r.draw(r.o.ord)), ['100']);
  assert.equal(arcs({ thr: 150 }), 0);                             // never reached
  r.o.destroy();
});

test('flow layer: a POC line runs from its bar to the bar that trades back to it, or to the right edge while none has', () => {
  const bars = [100, 102, 104, 106, 108].map((p, i) => bar(i, { l: p, h: p + 1, fp: [[p, 3, 3], [p + 1, 1, 1]] }));
  bars.push(bar(5, { l: 100, h: 110, fp: [[100, 5, 5]] }), bar(6, { l: 112, h: 113, fp: [[112, 2, 2]] }), bar(7, { l: 114, h: 115, fp: [[114, 2, 2]] }));
  const r = rig([], bars);
  r.cell.cfg.indicators.push(r.ind('npoc'));
  r.o.onIndicators();
  const log = r.draw(r.o.npoc);
  const m = log.filter((c) => c[0] === 'moveTo'), to = log.filter((c) => c[0] === 'lineTo');
  // bars 0-4: their POC (100 .. 108) is inside bar 5's range, so each line ends at bar 5 (x 500); bar 5's own 100 and bar 6's 112 are still naked: to the edge.
  // The forming bar 7's own POC is the footprint's.
  assert.deepEqual(m.map((c) => c[2]), [100, 102, 104, 106, 108, 100, 112].map(yOf));
  assert.deepEqual(m.map((c) => c[1]), [0, 100, 200, 300, 400, 500, 600]);
  assert.deepEqual(to.map((c) => c[1]), [500, 500, 500, 500, 500, 2000, 2000]);
  r.cell.cfg.indicators[0].visible = false;
  r.o.onIndicators();
  assert.equal(r.o.npoc, null);
  r.o.destroy();
});

test('flow layer: the TPO profile is the newest session only, letters from A, the POC row boxed', () => {
  const old = [bar(-4, { s: 'z', l: 50, h: 51 }), bar(-3, { s: 'z', l: 50, h: 51 })];
  const now = [0, 1, 2, 3, 4, 5].map((i) => bar(i, { l: 100 + (i >> 1), h: 100.5 + (i >> 1) }));   // two 15-minute bars to a 30-minute letter
  const r = rig([], [...old, ...now]);
  const t = r.ind('tpo', { period: 30, rows: 1 });
  r.cell.cfg.indicators.push(t);
  r.o.onIndicators();
  const prof = require(C + 'flowmath.js').tpo(now, 30, 1, 'range', { tick: 0.25 });
  let log = r.draw(r.o.tpo);
  assert.equal(texts(log).length, prof.rows.reduce((s, x) => s + x.n, 0));
  assert.deepEqual([...new Set(texts(log))].sort(), ['A', 'B', 'C']);   // nothing of the old session (its bars would add a row at 50)
  assert.equal(count(log, 'strokeRect'), 1);                        // the POC row
  t.params.style = 'blocks';
  log = r.draw(r.o.tpo);
  assert.equal(texts(log).length, 0);
  assert.equal(count(log, 'fillRect') >= prof.rows.reduce((s, x) => s + x.n, 0), true);
  t.params.mode = 'traded';                                         // a bar without footprint rows counts its range: same profile
  assert.equal(count(r.draw(r.o.tpo), 'strokeRect'), 1);
  r.o.destroy();
});

test('flow layer: TPO rows widen until 3 px tall, and blocks are a translucent wash', () => {
  const now = [0, 1, 2, 3, 4, 5].map((i) => bar(i, { l: 100 + (i >> 1), h: 100.5 + (i >> 1) }));
  const r = rig([], now, { px: 2 });                                 // a 0.25 tick is half a pixel high
  const t = r.ind('tpo', { period: 30, rows: 1, style: 'blocks' });
  r.cell.cfg.indicators.push(t);
  r.o.onIndicators();
  const wide = require(C + 'flowmath.js').tpo(now, 30, 6, 'range', { tick: 0.25 });   // ceil(3 / 0.5) = 6 ticks a row
  const log = r.draw(r.o.tpo);
  assert.equal(log.filter((c) => c[0] === 'fillRect' && c[4] === 2).length, wide.rows.reduce((s, x) => s + x.n, 0));   // 3 px row, 1 px gap: 2 px blocks
  assert.equal(log.some((c) => c[0] === 'fillRect' && c[4] === 1), false);   // no sub-pixel smear
  assert.equal(log.filter((c) => c[0] === 'fillStyle' && /0\.45/.test(c[1])).length >= wide.rows.length, true);
  r.o.destroy();
});

test('flow layer: the statistics strip writes seven figures a bar, and goes away when the bars are too narrow', () => {
  const bars = [0, 1, 2, 3].map((i) => bar(i, { d: 10 * (i + 1), v: 100, n: 40, dmax: 50, dmin: -5 }));
  const r = rig([], bars);
  r.cell.cfg.indicators.push(r.ind('cstat'));
  r.o.onIndicators();
  const t = texts(r.draw(r.o.stat));
  assert.equal(t.length, 7 + 7 * 2);                               // the labels, then bars 2 and 3 (bars 0, 1 sit under the label column)
  assert.deepEqual(t.slice(7, 14), ['30', '100', '40', '30.0%', '50', '-5', '900']);   // delta, volume, trades, delta %, max, min, seconds to the next bar
  assert.equal(t[20], '900');
  r.o.destroy();
  const narrow = rig([], bars, { step: 20 });
  narrow.cell.cfg.indicators.push(narrow.ind('cstat'));
  narrow.o.onIndicators();
  assert.equal(narrow.draw(narrow.o.stat).length, 0);
  narrow.o.destroy();
});

test('flow layer: Seconds on a time chart is the candle\'s own length, never the gap to the next stored bar', () => {
  const HOUR = 3_600_000, WEEKEND = 176_460_000;                      // a quiet stretch, then Fri 16:59 -> Sun 18:00
  const ms = [0, BAR, 2 * BAR, 3 * BAR + HOUR, 4 * BAR + HOUR + WEEKEND, 5 * BAR + HOUR + WEEKEND];
  const bars = ms.map((t, i) => bar(i, { ms: T0 + t, d: 10, v: 100, n: 40, dmax: 50, dmin: -5 }));
  const r = rig([], bars);
  r.cell.cfg.indicators.push(r.ind('cstat'));
  r.o.onIndicators();
  const t = texts(r.draw(r.o.stat));
  r.o.destroy();
  assert.equal(t.length, 7 + 7 * 4);                                  // bars 0, 1 sit under the label column
  assert.deepEqual([13, 20, 27, 34].map((k) => t[k]), ['900', '900', '900', '900']);   // the quiet stretch, the weekend, a normal next bar, the forming last bar
});

test('flow layer: Seconds on a tick / volume / range chart runs to the next bar\'s start, and stays blank across a session break', () => {
  const at = [[0, 'a'], [1000, 'a'], [20_000, 'a'], [27_000, 'a'], [90_000_000, 'b'], [90_004_000, 'b']];
  const bars = at.map(([t, s], i) => bar(i, { ms: T0 + t, s, d: 10, v: 100, n: 40, dmax: 50, dmin: -5 }));
  const r = rig([], bars);
  r.cell.isTime = () => false; r.cell.barMs = () => 0;
  r.cell.cfg.indicators.push(r.ind('cstat'));
  r.o.onIndicators();
  const t = texts(r.draw(r.o.stat));
  r.o.destroy();
  assert.deepEqual([13, 20, 27, 34].map((k) => t[k]), ['7', '', '4', '']);   // bar 2 -> 3 in one session; 3 -> 4 over a session break; 4 -> 5; the forming last bar
});

test('flow layer: delta turnaround and strength arrows and an absorption line, each only while its indicator is on', () => {
  const bars = [
    bar(0, { o: 103, c: 102, h: 103.5, l: 101.5 }), bar(1, { o: 102, c: 101, h: 102.5, l: 100.5 }),
    bar(2, { o: 101, c: 102, h: 102.5, l: 100, d: 40, dmax: 44, dmin: -3, fp: [[99.75, 1, 0], [100, 0, 10]] }),   // bullish, delta > 0, low under the bar before's low
    bar(3, { o: 102, c: 98.5, h: 102, l: 98, d: 0 }),                                                          // closes 4 ticks under 100: the buy imbalance at 100 was absorbed
  ];
  const r = rig([], bars);
  const ind = r.cell.cfg.indicators;
  ind.push(r.ind('dturn'));
  r.o.onIndicators();
  let log = r.draw(r.o.mark);
  assert.equal(count(log, 'fill'), 1);                              // one filled arrow, up, under bar 2's low
  assert.deepEqual(log.filter((c) => c[0] === 'moveTo').map((c) => [c[1], c[2]]), [[200, yOf(100) + 3]]);
  ind.push(r.ind('dstr', { min: 90 }));
  log = r.draw(r.o.mark);
  assert.equal(count(log, 'fill'), 1);                              // 40 of 44 = 91 %: a hollow arrow further out
  assert.equal(count(log, 'stroke'), 1);
  ind.push(r.ind('mwabs'));
  log = r.draw(r.o.mark);
  assert.equal(count(log, 'arc'), 1);                               // the line and its dot on bar 3
  assert.deepEqual(log.filter((c) => c[0] === 'arc').map((c) => [c[1], c[2]]), [[300, yOf(100)]]);
  ind.forEach((x) => { x.visible = false; });
  r.o.onIndicators();
  assert.equal(r.o.mark, null);
  r.o.destroy();
});

test.after(() => { delete globalThis.window; });
