import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const D = require('../../homebase/static/charts/drawings.js');

const MIN = 60000;
const T0 = 1_790_000_000_000;
const bars = [0, 1, 2, 3, 4].map((i) => ({ ms: T0 + i * MIN }));   // five 1m bars
const coord = (i) => 100 + i * 10;                                // bar i at x = 100 + 10 i
const TIME = { bars, isTime: true, barMs: MIN, coord };
const geo = { x: (t) => D.timeToX(t, TIME), y: (p) => 1000 - p, w: 400 };
const trend = { id: 'a', type: 'trend', points: [{ t: bars[0].ms, p: 900 }, { t: bars[4].ms, p: 860 }] };   // (100,100)-(140,140)
const rect = { id: 'b', type: 'rect', points: [{ t: bars[1].ms, p: 880 }, { t: bars[3].ms, p: 850 }] };     // x 110-130, y 120-150
const hline = { id: 'c', type: 'hline', points: [{ p: 875 }] };                                          // y 125

test('barIndexAt finds the last bar at or before t', () => {
  assert.equal(D.barIndexAt(bars, T0 - 1), -1);
  assert.equal(D.barIndexAt(bars, T0), 0);
  assert.equal(D.barIndexAt(bars, T0 + 90000), 1);
  assert.equal(D.barIndexAt(bars, T0 + 4 * MIN), 4);
  assert.equal(D.barIndexAt(bars, T0 + 99 * MIN), 4);
  assert.equal(D.barIndexAt([], T0), -1);
});

test('placeMarkers: on the bar holding the time, inside the loaded bars, sorted', () => {
  const tbars = [0, 1, 2].map((i) => ({ ms: T0 + i * MIN, tt: 1000 + i }));
  const out = D.placeMarkers(tbars, [{ id: 'b', ms: T0 + MIN + 5, x: 1 }, { id: 'a', ms: T0 }, { id: 'early', ms: T0 - MIN },
    { id: 'late', ms: T0 + 3 * MIN }], MIN);
  assert.deepEqual(out, [{ id: 'a', time: 1000 }, { id: 'b', x: 1, time: 1001 }]);
  assert.equal(D.placeMarkers(tbars, [{ id: 'late', ms: T0 + 99 * MIN }], 0).length, 1);   // non-time bars: the last bar holds the rest
  assert.deepEqual(D.placeMarkers([], [{ ms: 1 }]), []);
});

test('logicalOf interpolates between bars, extrapolates time bars, clamps the others', () => {
  assert.equal(D.logicalOf(bars, T0 + 90000, true, MIN), 1.5);
  assert.equal(D.logicalOf(bars, T0 - 2 * MIN, true, MIN), -2);
  assert.equal(D.logicalOf(bars, T0 + 7 * MIN, true, MIN), 7);
  assert.equal(D.logicalOf(bars, T0 - 2 * MIN, false, 0), 0);
  assert.equal(D.logicalOf(bars, T0 + 7 * MIN, false, 0), 4);
  assert.equal(D.logicalOf([], T0, true, MIN), null);
});

test('a point inside a data gap sits proportionally between the two bars', () => {
  const g = [{ ms: 0 }, { ms: 60 }, { ms: 120 }, { ms: 600 }];
  assert.equal(D.logicalOf(g, 360, true, 60), 2.5);
});

test('xOfLogical only ever asks for integer coordinates', () => {
  const asked = [];
  const c = (i) => { asked.push(i); return 100 + i * 10; };
  assert.equal(D.xOfLogical(1.5, c), 115);
  assert.equal(D.xOfLogical(-2, c), 80);
  assert.equal(D.xOfLogical(3, c), 130);
  assert.ok(asked.every(Number.isInteger));
  assert.equal(D.xOfLogical(null, c), null);
  assert.equal(D.xOfLogical(1.5, () => null), null);
});

test('timeToX puts a drawing where its time is on this chart', () => {
  assert.equal(D.timeToX(T0 + 90000, TIME), 115);
  assert.equal(D.timeToX(T0 + 6 * MIN, TIME), 160);
  assert.equal(D.timeToX(T0 - MIN, TIME), 90);
  assert.equal(D.timeToX(T0 + 6 * MIN, { ...TIME, isTime: false, barMs: 0 }), 140);
});

test('snapTime picks the nearest bar; beyond the data, whole bar steps (time bars only)', () => {
  assert.equal(D.snapTime(1.4, bars, true, MIN), bars[1].ms);
  assert.equal(D.snapTime(1.6, bars, true, MIN), bars[2].ms);
  assert.equal(D.snapTime(6.2, bars, true, MIN), T0 + 6 * MIN);
  assert.equal(D.snapTime(-1.8, bars, true, MIN), T0 - 2 * MIN);
  assert.equal(D.snapTime(6.2, bars, false, 0), bars[4].ms);
  assert.equal(D.snapTime(-3, bars, false, 0), bars[0].ms);
});

test('prices round to the tick', () => {
  assert.equal(D.roundToTick(30900.13, 0.25), 30900.25);
  assert.equal(D.roundToTick(30900.12, 0.25), 30900);
  assert.equal(D.roundToTick(2650.34, 0.1), 2650.3);
  assert.equal(D.roundToTick(1.23456, 0.005), 1.235);
});

test('distance from a point to a segment', () => {
  assert.equal(D.distToSegment(5, 5, 0, 0, 10, 0), 5);
  assert.equal(D.distToSegment(13, 4, 0, 0, 10, 0), 5);
  assert.equal(D.distToSegment(3, 4, 0, 0, 0, 0), 5);
});

test('hitTest: a trend line grabs its handles first, then its segment', () => {
  assert.deepEqual(D.hitTest(trend, { x: 101, y: 102 }, geo), { part: 'handle', index: 0 });
  assert.deepEqual(D.hitTest(trend, { x: 139, y: 141 }, geo), { part: 'handle', index: 1 });
  assert.deepEqual(D.hitTest(trend, { x: 122, y: 118 }, geo), { part: 'body' });
  assert.equal(D.hitTest(trend, { x: 130, y: 100 }, geo), null);
  assert.equal(D.hitTest(trend, { x: 170, y: 170 }, geo), null);
});

test('hitTest: rectangle corners are handles 0-3 and its inside is the body', () => {
  assert.deepEqual(D.hitTest(rect, { x: 110, y: 120 }, geo), { part: 'handle', index: 0 });
  assert.deepEqual(D.hitTest(rect, { x: 130, y: 150 }, geo), { part: 'handle', index: 1 });
  assert.deepEqual(D.hitTest(rect, { x: 110, y: 150 }, geo), { part: 'handle', index: 2 });
  assert.deepEqual(D.hitTest(rect, { x: 130, y: 120 }, geo), { part: 'handle', index: 3 });
  assert.deepEqual(D.hitTest(rect, { x: 120, y: 135 }, geo), { part: 'body' });
  assert.equal(D.hitTest(rect, { x: 160, y: 135 }, geo), null);
});

test('hitTest: a horizontal line is hit anywhere along it; its handle sits mid-pane', () => {
  assert.deepEqual(D.hitTest(hline, { x: 200, y: 126 }, geo), { part: 'handle', index: 0 });
  assert.deepEqual(D.hitTest(hline, { x: 20, y: 128 }, geo), { part: 'body' });
  assert.equal(D.hitTest(hline, { x: 20, y: 140 }, geo), null);
});

test('hitTest misses a drawing whose points cannot be placed', () => {
  assert.equal(D.hitTest(trend, { x: 101, y: 102 }, { ...geo, x: () => null }), null);
});

test('handle positions: trend ends, rectangle corners + side midpoints, mid-pane for a horizontal line', () => {
  assert.deepEqual(D.handlePoints(trend, geo), [[100, 100], [140, 140]]);
  // corners 0-3, then 4 top-mid, 5 bottom-mid (price only), 6 left-mid, 7 right-mid (time only)
  assert.deepEqual(D.handlePoints(rect, geo),
    [[110, 120], [130, 150], [110, 150], [130, 120], [120, 120], [120, 150], [110, 135], [130, 135]]);
  assert.deepEqual(D.handlePoints(hline, geo), [[200, 125]]);
  assert.equal(D.handlePoints(hline, { ...geo, y: () => null }), null);
});

test('dragging a handle moves that point; rectangle side corners mix the two points', () => {
  assert.deepEqual(D.setPoint(trend, 1, 5, 7).points, [trend.points[0], { t: 5, p: 7 }]);
  assert.deepEqual(D.setPoint(trend, 0, 5, 7).points, [{ t: 5, p: 7 }, trend.points[1]]);
  assert.deepEqual(D.setPoint(rect, 0, 5, 7).points, [{ t: 5, p: 7 }, rect.points[1]]);
  assert.deepEqual(D.setPoint(rect, 2, 5, 7).points, [{ t: 5, p: 880 }, { t: bars[3].ms, p: 7 }]);
  assert.deepEqual(D.setPoint(rect, 3, 5, 7).points, [{ t: bars[1].ms, p: 7 }, { t: 5, p: 850 }]);
  assert.deepEqual(D.setPoint(hline, 0, 5, 7), { id: 'c', type: 'hline', points: [{ p: 7 }] });
  assert.deepEqual(trend.points[1], { t: bars[4].ms, p: 860 });
});

test('rectangle side handles (2026-09-27 draw-tools plan): top/bottom move price only, left/right move time only', () => {
  // rect = [{t: bars[1].ms, p: 880}, {t: bars[3].ms, p: 850}]: a is the higher (top) and earlier (left) point
  assert.deepEqual(D.setPoint(rect, 4, 999, 900).points, [{ t: rect.points[0].t, p: 900 }, rect.points[1]]);   // top-mid: a's price only
  assert.deepEqual(D.setPoint(rect, 5, 999, 800).points, [rect.points[0], { t: rect.points[1].t, p: 800 }]);   // bottom-mid: b's price only
  assert.deepEqual(D.setPoint(rect, 6, bars[0].ms, 999).points,
    [{ t: bars[0].ms, p: rect.points[0].p }, rect.points[1]]);                                                 // left-mid: a's time only
  assert.deepEqual(D.setPoint(rect, 7, bars[4].ms, 999).points,
    [rect.points[0], { t: bars[4].ms, p: rect.points[1].p }]);                                                 // right-mid: b's time only
});

test('a rectangle side dragged past the opposite side flips cleanly (top/bottom, left/right recompute fresh)', () => {
  // top-mid (a, p 880) dragged to p 800 -- below b's 850: a becomes the lower point
  const flippedV = D.setPoint(rect, 4, 999, 800);
  assert.deepEqual(flippedV.points, [{ t: rect.points[0].t, p: 800 }, rect.points[1]]);
  assert.ok(flippedV.points[0].p < flippedV.points[1].p);
  // grabbing top-mid again on the flipped box now moves b (the point that reads as top now)
  assert.deepEqual(D.setPoint(flippedV, 4, 999, 900).points, [flippedV.points[0], { ...flippedV.points[1], p: 900 }]);
  // left-mid (a, t bar1) dragged past b's bar3: a becomes the later (right) point
  const flippedH = D.setPoint(rect, 6, bars[4].ms, 999);
  assert.deepEqual(flippedH.points, [{ t: bars[4].ms, p: rect.points[0].p }, rect.points[1]]);
  assert.ok(flippedH.points[0].t > flippedH.points[1].t);
  assert.deepEqual(D.setPoint(flippedH, 6, bars[0].ms, 999).points,
    [flippedH.points[0], { ...flippedH.points[1], t: bars[0].ms }]);   // now moves b, the one that is actually left
});

test('hitTest: a rectangle\'s side-midpoint handles (4-7) take priority over its body', () => {
  assert.deepEqual(D.hitTest(rect, { x: 120, y: 120 }, geo), { part: 'handle', index: 4 });   // top-mid
  assert.deepEqual(D.hitTest(rect, { x: 120, y: 150 }, geo), { part: 'handle', index: 5 });   // bottom-mid
  assert.deepEqual(D.hitTest(rect, { x: 110, y: 135 }, geo), { part: 'handle', index: 6 });   // left-mid
  assert.deepEqual(D.hitTest(rect, { x: 130, y: 135 }, geo), { part: 'handle', index: 7 });   // right-mid
  assert.deepEqual(D.hitTest(rect, { x: 120, y: 135 }, geo), { part: 'body' });                // dead centre: no handle nearby
});

test('moving shifts every point by whole bars and by price, on the tick grid', () => {
  assert.deepEqual(D.moveDrawing(trend, 2, 1.1, 0.25, TIME).points, [{ t: bars[2].ms, p: 901 }, { t: T0 + 6 * MIN, p: 861 }]);
  assert.deepEqual(D.moveDrawing(hline, 3, -2.3, 0.25, TIME).points, [{ p: 872.75 }]);
  const between = { ...trend, points: [{ t: T0 + 30000, p: 900 }, trend.points[1]] };
  assert.equal(D.moveDrawing(between, 0, 1, 0.25, TIME).points[0].t, T0 + 30000);   // a price-only move keeps t
  assert.equal(D.shiftTime(T0 + 30000, 1, TIME), bars[2].ms);
});

test('durations read like a clock', () => {
  assert.equal(D.fmtDuration(0), '0s');
  assert.equal(D.fmtDuration(45000), '45s');
  assert.equal(D.fmtDuration(8 * MIN), '8m');
  assert.equal(D.fmtDuration(90000), '1m 30s');
  assert.equal(D.fmtDuration(65 * MIN), '1h 5m');
  assert.equal(D.fmtDuration(120 * MIN), '2h');
  assert.equal(D.fmtDuration(27 * 60 * MIN), '1d 3h');
  assert.equal(D.fmtDuration(-8 * MIN), '8m');
});

test('measure label: price change, ticks, bars and time', () => {
  const ctx = { ...TIME, tick: 0.25 };
  assert.deepEqual(D.measureLabel({ t: bars[0].ms, p: 30900 }, { t: bars[4].ms, p: 30912.5 }, ctx),
    ['+12.50 (+0.04%) · 50 ticks', '4 bars · 4m']);
  assert.deepEqual(D.measureLabel({ t: bars[3].ms, p: 100 }, { t: bars[2].ms, p: 99.75 }, ctx),
    ['-0.25 (-0.25%) · 1 tick', '1 bar · 1m']);
});

test('new ids are short and unique', () => {
  const a = D.newId(), b = D.newId();
  assert.notEqual(a, b);
  assert.ok(a.length >= 1 && a.length <= 40);
});

/* ---- the store ---- */
const H1 = { id: 'h1', type: 'hline', points: [{ p: 1 }] };
const H2 = { id: 'h2', type: 'hline', points: [{ p: 2 }] };
const flush = () => new Promise((r) => setImmediate(r));

function fakeFetch(answer) {
  const calls = [];
  const f = async (url, opts = {}) => {
    const method = opts.method || 'GET';
    calls.push({ url, method, body: opts.body ? JSON.parse(opts.body) : undefined });
    const r = answer(url, method) || { status: 200, body: [] };
    return { ok: r.status < 400, status: r.status, json: async () => r.body };
  };
  f.calls = calls;
  return f;
}

test('the store loads a symbol once and tells its subscribers', async () => {
  const f = fakeFetch(() => ({ status: 200, body: [H1] }));
  const s = new D.Store({ fetchFn: f });
  let told = 0;
  s.subscribe('NQ', () => { told += 1; });
  const [a, b] = await Promise.all([s.ensure('NQ'), s.ensure('NQ')]);
  assert.equal(a, true);
  assert.equal(b, true);
  assert.deepEqual(s.list('NQ'), [H1]);
  assert.deepEqual(f.calls.map((c) => [c.method, c.url]), [['GET', '/api/drawings/NQ']]);
  assert.ok(told >= 1);
  assert.deepEqual(s.list('ES'), []);
});

test('edits reach subscribers at once and are saved once, 300 ms after the last', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const f = fakeFetch(() => null);
  const s = new D.Store({ fetchFn: f });
  await s.ensure('NQ');
  const seen = [];
  const off = s.subscribe('NQ', () => seen.push(s.list('NQ').map((d) => d.id)));
  s.add('NQ', H1);
  s.add('NQ', H2);
  s.replace('NQ', { ...H2, points: [{ p: 3 }] });
  s.remove('NQ', 'h1');
  assert.deepEqual(seen, [['h1'], ['h1', 'h2'], ['h1', 'h2'], ['h2']]);
  t.mock.timers.tick(299);
  await flush();
  assert.equal(f.calls.filter((c) => c.method === 'PUT').length, 0);
  t.mock.timers.tick(1);
  await flush();
  const puts = f.calls.filter((c) => c.method === 'PUT');
  assert.equal(puts.length, 1);
  assert.equal(puts[0].url, '/api/drawings/NQ');
  assert.deepEqual(puts[0].body, [{ ...H2, points: [{ p: 3 }] }]);
  off();
  s.clear('NQ');
  assert.equal(seen.length, 4);
});

test('drawings added before the first load finishes are merged with the saved ones', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  let release;
  const gate = new Promise((r) => { release = r; });
  const calls = [];
  const f = async (url, opts = {}) => {
    calls.push({ method: opts.method || 'GET', body: opts.body && JSON.parse(opts.body) });
    if (!opts.method) await gate;
    return { ok: true, status: 200, json: async () => (opts.method ? { ok: true } : [H1]) };
  };
  const s = new D.Store({ fetchFn: f });
  const loading = s.ensure('NQ');
  s.add('NQ', H2);
  release();
  await loading;
  assert.deepEqual(s.list('NQ').map((d) => d.id), ['h1', 'h2']);
  t.mock.timers.tick(300);
  await flush();
  assert.deepEqual(calls.filter((c) => c.method === 'PUT').at(-1).body.map((d) => d.id), ['h1', 'h2']);
});

test('a failed load is reported, retried before saving, and never overwritten', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const errors = [];
  const f = fakeFetch(() => ({ status: 500, body: {} }));
  const s = new D.Store({ fetchFn: f, onError: (root, msg) => errors.push([root, msg]) });
  assert.equal(await s.ensure('NQ'), false);
  s.add('NQ', H1);
  t.mock.timers.tick(300);
  await flush();
  await flush();
  assert.deepEqual(s.list('NQ'), [H1]);
  assert.deepEqual(f.calls.map((c) => c.method), ['GET', 'GET']);
  assert.deepEqual(errors, [['NQ', 'load failed (500)'], ['NQ', 'load failed (500)']]);
});

test('a failed save is reported and the drawings stay on screen', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const errors = [];
  const f = fakeFetch((url, method) => (method === 'PUT' ? { status: 400, body: { detail: 'type: trend, hline or rect' } } : null));
  const s = new D.Store({ fetchFn: f, onError: (root, msg) => errors.push([root, msg]) });
  await s.ensure('NQ');
  s.add('NQ', H1);
  t.mock.timers.tick(300);
  await flush();
  await flush();
  assert.deepEqual(s.list('NQ'), [H1]);
  assert.deepEqual(errors, [['NQ', 'save failed (400): type: trend, hline or rect']]);
});

test('samePoints: two versions of a drawing on exactly the same points', () => {
  assert.equal(D.samePoints(trend, { ...trend, points: trend.points.map((q) => ({ ...q })) }), true);
  assert.equal(D.samePoints(trend, D.moveDrawing(trend, 0, 0.25, 0.25, TIME)), false);
  assert.equal(D.samePoints(trend, D.moveDrawing(trend, 1, 0, 0.25, TIME)), false);
  assert.equal(D.samePoints(hline, { ...hline, points: [{ p: 875 }] }), true);
  assert.equal(D.samePoints(hline, { ...hline, points: [{ p: 875.25 }] }), false);
});

/* The pointer controller on a chart that needs no browser: the price pane
   is 400 x 1000 px at the page origin, bar i at x = 100 + 10 i, price p at
   y = 1000 - p (so one pixel is four 0.25 ticks). opts: the rail's tool (it
   returns to the cursor after a placement, as on the page), the magnet, and
   the chart's bars (OHLC ones for the magnet). */
function pointerRig(saved, { tool = 'cursor', magnet = { on: false, mode: 'weak' }, rigBars = bars, onPosition = () => {},
  styleDefault = undefined, onDrawingSettings = undefined } = {}) {
  globalThis.window = { addEventListener() {}, removeEventListener() {},
    LightweightCharts: { LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 } } };
  const applyCalls = [];
  const chart = { applyOptions(o) { applyCalls.push(o); }, priceScale: () => ({ width: () => 60 }), panes: () => [{ getHeight: () => 1000 }],
    timeScale: () => ({ logicalToCoordinate: (i) => 100 + i * 10, coordinateToLogical: (x) => (x - 100) / 10 }) };
  const menuCalls = [];
  const cell = { shown: { root: 'NQ' }, el: { dataset: {} }, P: { accent: '#2962FF' }, chart, bars: rigBars, tick: 0.25,
    isTime: () => true, barMs: () => MIN, onMenu(e, dbl) { menuCalls.push(!!dbl); },
    box: { clientWidth: 460, getBoundingClientRect: () => ({ left: 0, top: 0 }), addEventListener() {}, removeEventListener() {} },
    candles: { attachPrimitive() {}, priceToCoordinate: (p) => 1000 - p, coordinateToPrice: (y) => 1000 - y,
      createPriceLine: () => ({ applyOptions() {} }), removePriceLine() {} } };
  const f = fakeFetch((url, method) => (method === 'GET' ? { status: 200, body: saved } : null));
  const store = new D.Store({ fetchFn: f, delay: 0 });
  let now = tool;
  const ctl = new D.Controller(cell, { tool: () => now, toolDone() { now = 'cursor'; }, drawings: store,
    magnet: () => magnet, onPosition, ...(styleDefault ? { styleDefault } : {}), ...(onDrawingSettings ? { onDrawingSettings } : {}) });
  const ev = (x, y, buttons = 1, metaKey = false) => ({ button: 0, buttons, ctrlKey: false, metaKey, clientX: x, clientY: y,
    preventDefault() {}, stopPropagation() {} });
  const gesture = async (path, metaKey = false) => {   // press at path[0], move through the rest, release at the last point
    ctl.onDown(ev(...path[0], 1, metaKey));
    for (const p of path.slice(1)) ctl.onMove(ev(...p, 1, metaKey));
    ctl.onUp(ev(...path.at(-1), 0, metaKey));
    await new Promise((r) => setTimeout(r, 5));   // the store's (0 ms) save debounce
    await flush();
  };
  return { ctl, store, gesture, tool: () => now, puts: () => f.calls.filter((c) => c.method === 'PUT'), menuCalls, applyCalls,
    done() { ctl.destroy(); } };
}

test('a click on a drawing selects it and never nudges it; a real drag moves it and saves once', async (t) => {
  const had = globalThis.window;
  t.after(() => { if (had === undefined) delete globalThis.window; else globalThis.window = had; });
  const R = pointerRig([trend]);
  await R.store.ensure('NQ');
  await R.gesture([[120, 120], [121, 121]]);                       // a 1-px jitter on the line's body
  assert.equal(R.ctl.sel, 'a');
  assert.deepEqual(R.store.list('NQ'), [trend]);
  assert.equal(R.puts().length, 0);
  await R.gesture([[100, 100], [102, 101]]);                       // the same on a handle
  assert.deepEqual(R.store.list('NQ'), [trend]);
  assert.equal(R.puts().length, 0);
  await R.gesture([[120, 120], [130, 130], [120, 120]]);           // dragged away and back: nothing changed
  assert.deepEqual(R.store.list('NQ'), [trend]);
  assert.equal(R.puts().length, 0);
  await R.gesture([[120, 120], [122, 121], [130, 130]]);           // a real move: +1 bar, -10.00
  const moved = { ...trend, points: [{ t: bars[1].ms, p: 890 }, { t: bars[4].ms + MIN, p: 850 }] };
  assert.deepEqual(R.store.list('NQ'), [moved]);
  assert.deepEqual(R.puts().map((c) => c.body), [[moved]]);
  R.done();
});

/* ---- the magnet ---- */
test('the magnet state reads back from storage; anything else is off / weak', () => {
  assert.deepEqual(D.parseMagnet('{"on":true,"mode":"strong"}'), { on: true, mode: 'strong' });
  assert.deepEqual(D.parseMagnet('{"on":1,"mode":"x"}'), { on: false, mode: 'weak' });
  assert.deepEqual(D.parseMagnet(null), { on: false, mode: 'weak' });
  assert.deepEqual(D.parseMagnet('not json'), { on: false, mode: 'weak' });
  assert.deepEqual(D.MAGNET_OFF, { on: false, mode: 'weak' });
  assert.equal(D.MAGNET_PX, 12);
});

test('⌘ inverts the magnet for one event', () => {
  assert.equal(D.magnetMode({ on: true, mode: 'weak' }, false), 'weak');
  assert.equal(D.magnetMode({ on: true, mode: 'strong' }, false), 'strong');
  assert.equal(D.magnetMode({ on: true, mode: 'strong' }, true), null);
  assert.equal(D.magnetMode({ on: false, mode: 'strong' }, true), 'strong');
  assert.equal(D.magnetMode({ on: false, mode: 'weak' }, false), null);
  assert.equal(D.magnetMode(null, false), null);
});

const BAR = { ms: T0, o: 900, h: 910, l: 880, c: 905 };
const yOf = (p) => 1000 - p;     // one px per 1.00

test('weak magnet: the nearest O/H/L/C within 12 px, else the pointer\'s price', () => {
  assert.equal(D.snapPrice(BAR, yOf(912), 912, 'weak', yOf), 910);          // 2 px from H
  assert.equal(D.snapPrice(BAR, yOf(922), 922, 'weak', yOf), 910);          // exactly 12 px
  assert.equal(D.snapPrice(BAR, yOf(922.25), 922.25, 'weak', yOf), 922.25); // 12.25 px: too far
  assert.equal(D.snapPrice(BAR, yOf(903), 903, 'weak', yOf), 905);          // C (2 px) beats O (3 px)
});

test('strong magnet: always the nearest O/H/L/C', () => {
  assert.equal(D.snapPrice(BAR, yOf(960), 960, 'strong', yOf), 910);
  assert.equal(D.snapPrice(BAR, yOf(850), 850, 'strong', yOf), 880);
});

test('no magnet, no bar (beyond the data) or no placeable candidate: the pointer\'s price', () => {
  assert.equal(D.snapPrice(BAR, 88, 912, null, yOf), 912);
  assert.equal(D.snapPrice(null, 88, 912, 'strong', yOf), 912);
  assert.equal(D.snapPrice(BAR, 88, 912, 'strong', () => null), 912);
});

/* OHLC bars for the magnet: bar i opens 900, closes 905, high 910 + i, low 880 - i. */
const ohlc = bars.map((b, i) => ({ ...b, o: 900, h: 910 + i, l: 880 - i, c: 905 }));
function withWindow(t) {   // the rig installs a fake window: put the real one (none, in Node) back after the test
  const had = globalThis.window;
  t.after(() => { if (had === undefined) delete globalThis.window; else globalThis.window = had; });
}

test('placing snaps each point to its bar\'s O/H/L/C: weak within 12 px, strong always, ⌘ inverts', async (t) => {
  withWindow(t);
  const place = async (magnet, meta = false) => {
    const R = pointerRig([], { tool: 'trend', magnet, rigBars: ohlc });
    await R.store.ensure('NQ');
    // bar 2 at 915 (its high, 912, is 3 px away); bar 4 at 930 (its high, 914, is 16 px away)
    await R.gesture([[120, 85], [140, 70]], meta);
    const [d] = R.store.list('NQ');
    R.done();
    return d.points.map((q) => q.p);
  };
  assert.deepEqual(await place({ on: true, mode: 'weak' }), [912, 930]);
  assert.deepEqual(await place({ on: true, mode: 'strong' }), [912, 914]);
  assert.deepEqual(await place({ on: false, mode: 'strong' }), [915, 930]);
  assert.deepEqual(await place({ on: false, mode: 'strong' }, true), [912, 914]);   // ⌘: an off magnet works, in its mode
  assert.deepEqual(await place({ on: true, mode: 'strong' }, true), [915, 930]);    // ⌘: an on magnet is off
});

test('dragging a handle takes the magnet; moving a whole drawing never does', async (t) => {
  withWindow(t);
  const line = { id: 'm', type: 'trend', points: [{ t: bars[1].ms, p: 900 }, { t: bars[3].ms, p: 860 }] };   // (110,100)-(130,140)
  const R = pointerRig([line], { magnet: { on: true, mode: 'strong' }, rigBars: ohlc });
  await R.store.ensure('NQ');
  await R.gesture([[120, 120], [120, 116], [120, 114]]);               // the body, 6 px up: +6.00, no snap
  assert.deepEqual(R.store.list('NQ')[0].points, [{ t: bars[1].ms, p: 906 }, { t: bars[3].ms, p: 866 }]);
  await R.gesture([[110, 94], [120, 80], [120, 85]]);                 // handle 0 onto bar 2 near 915: its high, 912
  assert.deepEqual(R.store.list('NQ')[0].points, [{ t: bars[2].ms, p: 912 }, { t: bars[3].ms, p: 866 }]);
  R.done();
});

/* ---- long / short boxes ---- */
const Pos = require('../../homebase/static/charts/position.js');
const posBox = { id: 'p', type: 'long', qty: 1,
  points: [{ t: bars[1].ms, p: 900 }, { t: bars[3].ms, p: 920 }, { t: bars[3].ms, p: 890 }] };   // x 110..130, y 80..110

test('long/short boxes go to HBPosition for handles, hits and handle drags; a move shifts all three points', () => {
  assert.deepEqual(D.handlePoints(posBox, geo), Pos.handles(posBox, geo));
  assert.deepEqual(D.hitTest(posBox, { x: 131, y: 100 }, geo), { part: 'handle', index: 3 });
  assert.deepEqual(D.hitTest(posBox, { x: 120, y: 90 }, geo), { part: 'body' });
  assert.deepEqual(D.setPoint(posBox, 1, bars[0].ms, 880, { ...TIME, tick: 0.25 }).points[1], { t: bars[3].ms, p: 900.25 });
  const moved = D.moveDrawing(posBox, 1, 5, 0.25, TIME);
  assert.deepEqual(moved.points, [{ t: bars[2].ms, p: 905 }, { t: bars[4].ms, p: 925 }, { t: bars[4].ms, p: 895 }]);
  assert.equal(moved.qty, 1);
  assert.equal(D.samePoints(posBox, moved), false);
});

test('the long tool places a 1:2 box: risk 8% of the pane, 20 bars wide, the entry on the magnet', async (t) => {
  withWindow(t);
  const R = pointerRig([], { tool: 'long', magnet: { on: true, mode: 'weak' }, rigBars: ohlc });
  await R.store.ensure('NQ');
  await R.gesture([[120, 85], [150, 60]]);           // press-drag-release places at the press: the drag is ignored
  const [d] = R.store.list('NQ');
  const t1 = bars[4].ms + 18 * MIN;                   // bar 2 + 20 bars, past the last bar: extrapolated
  assert.deepEqual({ type: d.type, qty: d.qty, points: d.points },
    { type: 'long', qty: 1, points: [{ t: bars[2].ms, p: 912 }, { t: t1, p: 1072 }, { t: t1, p: 832 }] });   // 8% of 1000 px = 80.00
  assert.equal(R.ctl.sel, d.id);
  assert.equal(R.tool(), 'cursor');
  assert.equal(R.puts().length, 1);
  R.done();
});

test('the short tool mirrors it', async (t) => {
  withWindow(t);
  const R = pointerRig([], { tool: 'short', rigBars: ohlc });
  await R.store.ensure('NQ');
  await R.gesture([[120, 85]]);
  assert.deepEqual(R.store.list('NQ')[0].points.map((q) => q.p), [915, 755, 995]);
  R.done();
});

test('a double-click on a box opens its settings; on empty chart it opens the chart menu (spec §7)', async (t) => {
  withWindow(t);
  const opened = [];
  const R = pointerRig([posBox], { onPosition: (cell, d) => opened.push(d.id) });
  await R.store.ensure('NQ');
  const dbl = (x, y) => R.ctl.onDbl({ clientX: x, clientY: y, preventDefault() {}, stopPropagation() {} });
  dbl(120, 95);
  dbl(300, 95);
  assert.deepEqual(opened, ['p']);
  assert.equal(R.ctl.sel, 'p');
  assert.deepEqual(R.menuCalls, [true]);   // only the empty-space double-click opened the chart menu (dbl = true)
  R.done();
});

/* ---- 2026-09-27 draw-tools plan: Shift gestures, locked drawings, a new drawing's starting style ---- */
const evAt = (x, y, { buttons = 1, shiftKey = false } = {}) => ({ button: 0, buttons, ctrlKey: false, metaKey: false,
  shiftKey, clientX: x, clientY: y, preventDefault() {}, stopPropagation() {} });

test('Shift + press-drag with the cursor tool starts the ruler, even over a drawing, without selecting it', async (t) => {
  withWindow(t);
  const R = pointerRig([trend], { tool: 'cursor' });
  await R.store.ensure('NQ');
  R.ctl.onDown(evAt(120, 120, { shiftKey: true }));   // squarely on the trend line's own body
  assert.equal(R.ctl.sel, null);                       // the ruler wins, never the drawing under it
  assert.ok(R.ctl.measure && !R.ctl.measure.done);
  R.ctl.onMove(evAt(140, 100, { shiftKey: true }));
  R.ctl.onUp(evAt(140, 100, { buttons: 0, shiftKey: true }));
  assert.ok(R.ctl.measure && R.ctl.measure.done);
  assert.deepEqual(R.store.list('NQ'), [trend]);       // nothing drawn, nothing moved
  R.done();
});

test('a Shift+click with no drag drops the ruler instead of arming a 2nd click', async (t) => {
  withWindow(t);
  const R = pointerRig([], { tool: 'cursor' });
  await R.store.ensure('NQ');
  R.ctl.onDown(evAt(200, 200, { shiftKey: true }));
  R.ctl.onUp(evAt(200, 200, { buttons: 0, shiftKey: true }));
  assert.equal(R.ctl.measure, null);
  assert.equal(R.ctl.mode, null);
  R.ctl.onDown(evAt(120, 120));   // a later plain click must behave normally, not like a pending 2nd click
  R.ctl.onUp(evAt(120, 120, { buttons: 0 }));
  assert.deepEqual(R.store.list('NQ'), []);
  R.done();
});

test('Shift while placing a trend line snaps to horizontal; releasing Shift mid-drag un-snaps', async (t) => {
  withWindow(t);
  const R = pointerRig([], { tool: 'trend' });
  await R.store.ensure('NQ');
  R.ctl.onDown(evAt(100, 100));                          // bar 0, p 900
  R.ctl.onMove(evAt(140, 60, { shiftKey: true }));        // Shift held: stays at p 900 (perfectly horizontal)
  assert.equal(R.ctl.place.points[1].p, 900);
  R.ctl.onMove(evAt(140, 60, { shiftKey: false }));       // Shift released: back to the pointer's own price
  assert.equal(R.ctl.place.points[1].p, 940);
  R.ctl.onUp(evAt(140, 60, { buttons: 0, shiftKey: true }));   // Shift held again at release
  await new Promise((r) => setTimeout(r, 5));
  await flush();
  const [d] = R.store.list('NQ');
  assert.deepEqual(d.points.map((q) => q.p), [900, 900]);
  R.done();
});

test('Shift while dragging a trend line\'s endpoint snaps it to the other endpoint\'s current price', async (t) => {
  withWindow(t);
  const line = { id: 'm', type: 'trend', points: [{ t: bars[1].ms, p: 900 }, { t: bars[3].ms, p: 860 }] };
  const R = pointerRig([line], { tool: 'cursor' });
  await R.store.ensure('NQ');
  R.ctl.onDown(evAt(110, 100));                           // handle 0 (p 900)
  R.ctl.onMove(evAt(112, 80, { shiftKey: true }));         // Shift: takes handle 1's price (860)
  assert.equal(R.ctl.drag.cur.points[0].p, 860);
  R.ctl.onMove(evAt(112, 80, { shiftKey: false }));        // released: the pointer's own price (920)
  assert.equal(R.ctl.drag.cur.points[0].p, 920);
  R.ctl.onUp(evAt(112, 80, { buttons: 0 }));
  R.done();
});

test('a locked drawing can be selected but is never dragged or deleted', async (t) => {
  withWindow(t);
  const locked = { ...trend, locked: true };
  const R = pointerRig([locked], { tool: 'cursor' });
  await R.store.ensure('NQ');
  await R.gesture([[120, 120], [130, 130]]);   // a real drag, on the body
  assert.equal(R.ctl.sel, 'a');                // still selects
  assert.deepEqual(R.store.list('NQ'), [locked]);   // never moved, never PUT
  assert.equal(R.puts().length, 0);
  assert.equal(R.ctl.deleteSelected(), false);
  assert.deepEqual(R.store.list('NQ'), [locked]);
  R.done();
});

test('review finding: a press on a locked drawing still releases pan/zoom on mouseup (no drag is set, but own() ran)', async (t) => {
  withWindow(t);
  const locked = { ...trend, locked: true };
  const R = pointerRig([locked], { tool: 'cursor' });
  await R.store.ensure('NQ');
  await R.gesture([[120, 120], [130, 130]]);   // press, a bit of movement, release -- all on the locked drawing's body
  const owned = R.applyCalls.filter((o) => o.handleScroll === false && o.handleScale === false);
  assert.equal(owned.length, 1);                                             // own() disabled panning/zoom exactly once
  assert.deepEqual(R.applyCalls.at(-1), { handleScroll: true, handleScale: true });   // and onUp's release() restored it
  R.done();
});

test('review finding: a locked-drawing press also releases pan/zoom if the button is lost before mouseup (blur/pointercancel)', async (t) => {
  withWindow(t);
  const locked = { ...trend, locked: true };
  const R = pointerRig([locked], { tool: 'cursor' });
  await R.store.ensure('NQ');
  R.ctl.onDown({ button: 0, buttons: 1, ctrlKey: false, metaKey: false, clientX: 120, clientY: 120, preventDefault() {}, stopPropagation() {} });
  assert.deepEqual(R.applyCalls.at(-1), { handleScroll: false, handleScale: false });
  assert.equal(R.ctl.held(), true);      // this.owned, even though this.drag is null (locked)
  assert.equal(R.ctl.abort(), true);     // what the window's blur / a pointercancel calls
  assert.deepEqual(R.applyCalls.at(-1), { handleScroll: true, handleScale: true });
  R.done();
});

test('an unlocked drawing behaves exactly as before (no regression from the lock check)', async (t) => {
  withWindow(t);
  const R = pointerRig([trend], { tool: 'cursor' });
  await R.store.ensure('NQ');
  assert.equal(R.ctl.deleteSelected(), false);   // nothing selected yet
  R.ctl.onDown(evAt(120, 120));
  R.ctl.onUp(evAt(120, 120, { buttons: 0 }));
  assert.equal(R.ctl.sel, 'a');
  assert.equal(R.ctl.deleteSelected(), true);
  assert.deepEqual(R.store.list('NQ'), []);
  R.done();
});

const DS = require('../../homebase/static/charts/drawstyle.js');

test('a new trend/rect/hline gets that tool\'s built-in default style; long/short take none', async (t) => {
  withWindow(t);
  const trendRig = pointerRig([], { tool: 'trend' });
  await trendRig.store.ensure('NQ');
  await trendRig.gesture([[100, 100], [140, 60]]);
  assert.deepEqual(trendRig.store.list('NQ')[0].style, DS.DEFAULTS.trend);
  trendRig.done();

  const rectRig = pointerRig([], { tool: 'rect' });
  await rectRig.store.ensure('NQ');
  await rectRig.gesture([[100, 100], [140, 60]]);
  assert.deepEqual(rectRig.store.list('NQ')[0].style, DS.DEFAULTS.rect);
  rectRig.done();

  const hlineRig = pointerRig([], { tool: 'hline' });
  await hlineRig.store.ensure('NQ');
  hlineRig.ctl.onDown(evAt(100, 100));
  hlineRig.ctl.onUp(evAt(100, 100, { buttons: 0 }));
  await new Promise((r) => setTimeout(r, 5));
  await flush();
  assert.deepEqual(hlineRig.store.list('NQ')[0].style, DS.DEFAULTS.hline);
  hlineRig.done();

  const longRig = pointerRig([], { tool: 'long', rigBars: ohlc });
  await longRig.store.ensure('NQ');
  await longRig.gesture([[120, 85]]);
  assert.equal('style' in longRig.store.list('NQ')[0], false);
  longRig.done();
});

test('commit() prefers the host\'s saved default preset for that tool, still normalized against junk', async (t) => {
  withWindow(t);
  const R = pointerRig([], { tool: 'trend', styleDefault: (type) => (type === 'trend' ? { width: 4, junk: 1 } : null) });
  await R.store.ensure('NQ');
  await R.gesture([[100, 100], [140, 60]]);
  const style = R.store.list('NQ')[0].style;
  assert.equal(style.width, 4);                          // the saved default's field, kept
  assert.equal(style.lineStyle, DS.DEFAULTS.trend.lineStyle);   // an untouched field still reads the built-in default
  assert.equal('junk' in style, false);                   // a field the type doesn't take is dropped, not stored
  R.done();
});
