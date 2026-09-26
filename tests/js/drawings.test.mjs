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

test('handle positions: trend ends, rectangle corners, mid-pane for a horizontal line', () => {
  assert.deepEqual(D.handlePoints(trend, geo), [[100, 100], [140, 140]]);
  assert.deepEqual(D.handlePoints(rect, geo), [[110, 120], [130, 150], [110, 150], [130, 120]]);
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
   y = 1000 - p (so one pixel is four 0.25 ticks). */
function pointerRig(saved) {
  globalThis.window = { addEventListener() {}, removeEventListener() {} };
  const chart = { applyOptions() {}, priceScale: () => ({ width: () => 60 }), panes: () => [{ getHeight: () => 1000 }],
    timeScale: () => ({ logicalToCoordinate: (i) => 100 + i * 10, coordinateToLogical: (x) => (x - 100) / 10 }) };
  const cell = { shown: { root: 'NQ' }, el: { dataset: {} }, P: { accent: '#2962FF' }, chart, bars, tick: 0.25,
    isTime: () => true, barMs: () => MIN,
    box: { clientWidth: 460, getBoundingClientRect: () => ({ left: 0, top: 0 }), addEventListener() {}, removeEventListener() {} },
    candles: { attachPrimitive() {}, priceToCoordinate: (p) => 1000 - p, coordinateToPrice: (y) => 1000 - y } };
  const f = fakeFetch((url, method) => (method === 'GET' ? { status: 200, body: saved } : null));
  const store = new D.Store({ fetchFn: f, delay: 0 });
  const ctl = new D.Controller(cell, { tool: () => 'cursor', toolDone() {}, drawings: store });
  const ev = (x, y, buttons = 1) => ({ button: 0, buttons, ctrlKey: false, clientX: x, clientY: y,
    preventDefault() {}, stopPropagation() {} });
  const gesture = async (path) => {   // press at path[0], move through the rest, release at the last point
    ctl.onDown(ev(...path[0]));
    for (const p of path.slice(1)) ctl.onMove(ev(...p));
    ctl.onUp(ev(...path.at(-1), 0));
    await new Promise((r) => setTimeout(r, 5));   // the store's (0 ms) save debounce
    await flush();
  };
  return { ctl, store, gesture, puts: () => f.calls.filter((c) => c.method === 'PUT'), done() { ctl.destroy(); } };
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
