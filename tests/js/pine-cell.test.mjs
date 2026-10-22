import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* The 'pine' indicator in cell.js: the Worker (a fake one here), what goes into it, and what comes back onto the chart. Loaded under
   minimal stubs and driven through Cell.prototype; the real Worker and runtime are pineworker.js's own business. */
const require = createRequire(import.meta.url);
globalThis.window = globalThis;
globalThis.HBLayers = {};
globalThis.LightweightCharts = new Proxy({ LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 }, LineType: { Simple: 0, WithSteps: 1, Curved: 2 } },
  { get: (t, k) => (k in t ? t[k] : String(k)) });
require('../../homebase/static/charts/catalog.js');
require('../../homebase/static/charts/indstatus.js');
require('../../homebase/static/charts/cell.js');
const { Cell, pineCss, pinePlotKind, pineMarkers } = globalThis.HBCell;
const C = globalThis.HBCatalog;

class FakeWorker {
  constructor(url) { this.url = url; this.sent = []; this.stopped = false; FakeWorker.all.push(this); }
  postMessage(m) { this.sent.push(m); }
  terminate() { this.stopped = true; }
  say(data) { this.onmessage({ data }); }   // the Worker answers
}
FakeWorker.all = [];
globalThis.Worker = FakeWorker;
const SCRIPTS = { 'a.pine': '//@version=5\nindicator("A")\nplot(close)', 'fp.pine': '//@version=5\nindicator("F")\nx = request.footprint("1")', 'bad.pine': 'not pine' };
const fetched = [];
globalThis.fetch = async (url) => {
  fetched.push(url);
  const name = decodeURIComponent(String(url).split('/').pop());
  return name in SCRIPTS ? { ok: true, text: async () => SCRIPTS[name] } : { ok: false, text: async () => '' };
};
const later = () => new Promise((r) => setTimeout(r, 0));
const reset = () => { FakeWorker.all.length = 0; fetched.length = 0; };

const P = { up: '#0f0', down: '#f00', accent: '#08f', lines: ['#111111', '#222222'] };
const ind = (script, more = {}, params = {}) => ({ uid: 'p1', id: 'pine', visible: true, params: C.clampParams('pine', { script, ...params }), ...more });
const bar = (i, more = {}) => ({ tt: 1000 + i * 60, ms: i * 60000, s: '2026-10-21', o: 10 + i, h: 11 + i, l: 9 + i, c: 10.5 + i, v: 5, ...more });
function cell(indicators, more = {}) {
  const c = Object.assign(Object.create(Cell.prototype), { cfg: { root: 'NQ', spec: 'time:60', indicators }, shown: { root: 'NQ', spec: 'time:60' }, tick: 0.25, pv: 20,
    bars: [bar(0), bar(1), bar(2)], has: { fp: false, big: false, flow: false }, P, extMarkers: {}, wantFp: false, hover: null,
    drawMarkers() {}, refreshStatus() {}, legend() {}, subscribe(k) { this.subscribed = k; } }, more);
  c.pine = new Map();
  return c;
}
const state = (c, uid = 'p1') => c.pine.get(uid);
const ready = async (c, script = 'a.pine', more = {}) => { c.pineSync(); await later(); return state(c); };
const RESULT = { type: 'result', full: true, firstMs: 0, kind: 'indicator', title: 'A', overlay: true, inputsMeta: [{ id: 'in_0', title: 'Length', type: 'int', defval: 14 }],
  plots: { Fast: [{ time: 0, value: 1 }, { time: 60000, value: 2 }, { time: 120000, value: null }] }, plotsMeta: { Fast: { style: 'style_line', color: '#2962FF', linewidth: 2 } },
  shapes: [], boxes: [], lines: [], labels: [], linefills: [], polylines: [], tables: [], warnings: [] };

test('pineCss turns every Pine colour form into one Lightweight Charts reads; a bad one gives the default', () => {
  assert.equal(pineCss('#2962FF'), 'rgba(41,98,255,1)');
  assert.equal(pineCss('#2962FF80'), 'rgba(41,98,255,0.502)');
  assert.equal(pineCss('#fa0'), 'rgba(255,170,0,1)');
  assert.equal(pineCss('rgba(1, 2, 3, 0.5)'), 'rgba(1,2,3,0.5)');
  assert.equal(pineCss('rgb(1,2,3)'), 'rgba(1,2,3,1)');
  assert.equal(pineCss('#2962FF', null, 0.3), 'rgba(41,98,255,0.3)', 'a given alpha replaces the colour\'s own');
  for (const bad of [undefined, null, '', 'red', '#12', '#gggggg']) assert.equal(pineCss(bad, '#abc'), '#abc', String(bad));
});

test('pinePlotKind: how a plot style draws; a background stripe or a bar colour is no series', () => {
  assert.deepEqual(pinePlotKind({ style: 'style_line' }), { kind: 'line', step: false, dashed: false });
  assert.deepEqual(pinePlotKind(undefined), { kind: 'line', step: false, dashed: false });
  assert.deepEqual(pinePlotKind({ style: 'style_stepline' }), { kind: 'line', step: true, dashed: false });
  assert.equal(pinePlotKind({ style: 'hline' }).dashed, true);
  for (const s of ['style_histogram', 'style_columns']) assert.equal(pinePlotKind({ style: s }).kind, 'hist', s);
  for (const s of ['style_area', 'style_areabr']) assert.equal(pinePlotKind({ style: s }).kind, 'area', s);
  for (const s of ['style_circles', 'style_cross']) assert.equal(pinePlotKind({ style: s }).kind, 'dots', s);
  assert.equal(pinePlotKind({ style: 'background' }), null);
  assert.equal(pinePlotKind({ style: 'barcolor' }), null);
});

test('pineMarkers: shape, place, size and colour of a hit; a character is a size-0 mark carrying its text', () => {
  const m = pineMarkers([
    { time: 1, shape: 'shape_triangle_up', location: 'BelowBar', color: '#00FF00', size: 'size.small', text: 'buy' },
    { time: 2, shape: 'shape_triangle_down', location: 'AboveBar' },
    { time: 3, shape: 'shape_xcross', location: 'Top' },
    { time: 4, shape: 'char', location: 'Bottom', char: 'X', text: 'ignored' },
    { time: 5, shape: 'shape_square', location: 'Absolute', size: 'size.huge' }], P);
  assert.deepEqual(m[0], { ms: 1, position: 'belowBar', shape: 'arrowUp', color: 'rgba(0,255,0,1)', text: 'buy', size: 0.75 });
  assert.deepEqual([m[1].shape, m[1].position, m[1].color, m[1].size], ['arrowDown', 'aboveBar', '#f00', 1], 'no colour: the down colour for a down shape');
  assert.deepEqual([m[2].shape, m[2].position, m[2].color], ['circle', 'aboveBar', '#08f']);
  assert.deepEqual([m[3].position, m[3].text, m[3].size], ['belowBar', 'X', 0]);
  assert.deepEqual([m[4].shape, m[4].position, m[4].size], ['square', 'inBar', 2]);
  const many = Array.from({ length: 1500 }, (_, i) => ({ time: i, shape: 'shape_circle', location: 'AboveBar' }));
  const kept = pineMarkers(many, P);
  assert.deepEqual([kept.length, kept[0].ms, kept.at(-1).ms], [1000, 500, 1499], 'the newest 1000');
  assert.deepEqual(pineMarkers(undefined, P), []);
});

test('a Pine row starts its Worker with the chart\'s bars, the script text, the saved inputs and the market', async () => {
  reset();
  const c = cell([ind('a.pine', {}, { inputs: { Length: 9 }, maxbars: 5000 })], { bars: [bar(0), bar(1, { blank: 'closed' }), bar(2)] });
  c.pineSync();
  assert.equal(state(c).running, true);
  await later();
  assert.deepEqual(fetched, ['/api/pine/scripts/a.pine']);
  assert.equal(FakeWorker.all.length, 1);
  const w = FakeWorker.all[0];
  assert.equal(w.url, '/static/charts/pineworker.js?v=1');
  assert.equal(w.sent.length, 1);
  const m = w.sent[0];
  assert.deepEqual({ ...m, bars: undefined }, { type: 'init', source: SCRIPTS['a.pine'], inputs: { Length: 9 }, root: 'NQ', tf_s: 60, tick_size: 0.25, point_value: 20, bars: undefined, maxBars: 5000 });
  assert.deepEqual(m.bars, [{ ms: 0, s: '2026-10-21', o: 10, h: 11, l: 9, c: 10.5, v: 5 }, { ms: 120000, s: '2026-10-21', o: 12, h: 13, l: 11, c: 12.5, v: 5 }], 'a blank slot is not a bar; no fp unless the script reads it');
});

test('only the newest `maxbars` bars go in, and a market with no point value sends 1', async () => {
  reset();
  const c = cell([ind('a.pine', {}, { maxbars: 100 })], { bars: Array.from({ length: 150 }, (_, i) => bar(i)), pv: null });
  await ready(c);
  const m = FakeWorker.all[0].sent[0];
  assert.equal(m.bars.length, 100);
  assert.equal(m.bars[0].ms, 50 * 60000);
  assert.equal(m.point_value, 1);
});

test('a script that reads request.footprint makes the chart ask for the footprint, and then sends it with every bar', async () => {
  reset();
  const c = cell([ind('fp.pine')], { bars: [bar(0, { fp: [[10, 1, 2]] }), bar(1)] });
  assert.equal(c.need().fp, false, 'until its text has been read');
  await ready(c);
  assert.equal(state(c).fp, true);
  assert.equal(c.need().fp, true);
  assert.equal(c.subscribed, true, 'the history comes again with the footprint');
  assert.equal(FakeWorker.all.length, 0, 'the Worker waits for that history');
  c.has.fp = true;
  c.pineFresh = true;
  c.pineSync();
  await later();
  assert.deepEqual(FakeWorker.all[0].sent[0].bars.map((b) => b.fp), [[[10, 1, 2]], undefined]);
  assert.equal(c.need().fp, true);
  assert.equal(cell([ind('a.pine')]).need().fp, false, 'a script that does not: nothing changes');
});

test('later bars go to the Worker as they change; older history too; none before it has started', async () => {
  reset();
  const c = cell([ind('a.pine')]);
  c.pineSync();
  c.pineForward([bar(3)]);
  await later();
  assert.equal(FakeWorker.all[0].sent.length, 1, 'only the init, which already carries what was loaded');
  const w = FakeWorker.all[0];
  c.pineForward([bar(3), bar(4, { blank: 'closed' })]);
  c.pineForward([]);
  assert.deepEqual(w.sent.slice(1).map((m) => [m.type, m.bars.map((b) => b.ms)]), [['bars', [180000]]]);
});

test('a result becomes the plot values of each bar: the value, its colour when the script gave one, a gap for null or a missing bar', async () => {
  reset();
  const c = cell([ind('a.pine')]);
  const st = await ready(c);
  FakeWorker.all[0].say({ ...RESULT, plots: { Fast: [{ time: 0, value: 1, color: '#FF0000' }, { time: 60000, value: 2 }, { time: 120000, value: null }] } });
  const l = { pine: { st, title: 'Fast' } };
  assert.deepEqual(c.point(l, bar(0)), { time: 1000, value: 1, color: 'rgba(255,0,0,1)' });
  assert.deepEqual(c.point(l, bar(1)), { time: 1060, value: 2 });
  assert.deepEqual(c.point(l, bar(2)), { time: 1120 });
  assert.deepEqual(c.point(l, bar(9)), { time: 1540 });
  assert.deepEqual(c.point(l, bar(3, { blank: 'closed' })), { time: 1180 });
  assert.equal(st.running, false);
  assert.deepEqual(c.pineMeta('p1'), { inputs: RESULT.inputsMeta, title: 'A', error: null, running: false });
});

function chartCell(indicators) {
  const added = [];
  const chart = { addSeries: (type, opts, pane) => { const s = { type, opts: { ...opts }, pane, data: null, updates: [], setData(d) { this.data = d; }, update(p) { this.updates.push(p); },
    applyOptions(o) { Object.assign(this.opts, o); }, priceScale: () => ({ applyOptions() {} }) }; added.push(s); return s; } };
  const c = cell(indicators, { chart, R: { scalePriceOnly: false }, lines: [], colorOf: {}, ov: [], candles: null, restyled: 0,
    restyle() { this.restyled++; this.lines = []; this.colorOf = {}; this.buildSeries(); this.pineSync(); } });
  return { c, added };
}

test('a partial result changes only the points it carries; a null removes one; the shapes from the first changed bar are replaced', async () => {
  reset();
  const { c } = chartCell([ind('a.pine')]);
  const st = await ready(c);
  const w = FakeWorker.all[0];
  w.say({ ...RESULT, shapes: [{ time: 0, shape: 'shape_circle', location: 'AboveBar' }, { time: 60000, shape: 'shape_circle', location: 'AboveBar' }] });
  assert.equal(c.extMarkers['pine:p1'].length, 2);
  w.say({ ...RESULT, full: false, plots: { Fast: [{ time: 60000, value: 5 }, { time: 120000, value: 6 }, { time: 0, value: null }] }, shapes: [{ time: 120000, shape: 'shape_circle', location: 'BelowBar' }] });
  assert.deepEqual([...st.data.get('Fast')].map(([t, v]) => [t, v.value]), [[60000, 5], [120000, 6]]);
  assert.deepEqual(c.extMarkers['pine:p1'].map((m) => [m.ms, m.position]), [[120000, 'belowBar']], 'the earlier hits go with the changed point at 0, the new one comes in');
  w.say({ ...RESULT, full: false, plots: {}, shapes: [] });
  assert.deepEqual(c.extMarkers['pine:p1'].map((m) => m.ms), [120000], 'nothing changed: nothing lost');
});

test('the shapes become markers on the chart; an eye that is off takes them away', async () => {
  reset();
  const { c } = chartCell([ind('a.pine')]);
  await ready(c);
  FakeWorker.all[0].say({ ...RESULT, shapes: [{ time: 60000, shape: 'shape_triangle_up', location: 'BelowBar', color: '#00FF00' }] });
  assert.deepEqual(c.extMarkers['pine:p1'].map((m) => [m.ms, m.shape, m.position]), [[60000, 'arrowUp', 'belowBar']]);
  c.cfg.indicators = [ind('a.pine', { visible: false })];
  c.pineDraw(state(c));
  assert.deepEqual(c.extMarkers['pine:p1'], []);
});

test('the plots draw as the series their style says, in the price pane for an overlay and in a pane of their own otherwise', async () => {
  reset();
  const { c, added } = chartCell([ind('a.pine')]);
  await ready(c);
  const plots = { Line: [], Bars: [], Fill: [], Dots: [], Back: [{ time: 0, color: '#FF000040' }] };
  const meta = { Line: { style: 'style_line', color: '#2962FF', linewidth: 3 }, Bars: { style: 'style_histogram', color: '#00FF00' }, Fill: { style: 'style_area' }, Dots: { style: 'style_circles' }, Back: { style: 'background' } };
  FakeWorker.all[0].say({ ...RESULT, overlay: false, plots, plotsMeta: meta });
  assert.equal(c.restyled, 1, 'the first result rebuilds the chart: the plots were not known');
  assert.deepEqual(added.slice(-4).map((s) => [s.type, s.pane]), [['LineSeries', 1], ['HistogramSeries', 1], ['AreaSeries', 1], ['LineSeries', 1]]);
  assert.deepEqual(c.paneUid, [null, 'p1']);
  const [line, hist, area, dots] = added.slice(-4);
  assert.deepEqual([line.opts.color, line.opts.lineWidth], ['rgba(41,98,255,1)', 3]);
  assert.equal(hist.opts.color, 'rgba(0,255,0,1)');
  assert.deepEqual([area.opts.lineColor, area.opts.topColor, area.opts.bottomColor], ['#08f', 'rgba(0,136,255,0.3)', 'rgba(0,136,255,0)'], 'no colour from the script: the accent');
  assert.deepEqual([dots.opts.lineVisible, dots.opts.pointMarkersVisible], [false, true]);
  assert.deepEqual(c.lines.map((l) => l.pine.title), ['Line', 'Bars', 'Fill', 'Dots'], 'a background stripe is the layer\'s, not a series');
  assert.equal(c.colorOf.p1, 'rgba(41,98,255,1)');
  const price = chartCell([ind('a.pine')]);
  await ready(price.c);
  FakeWorker.all.at(-1).say({ ...RESULT, overlay: true });
  assert.deepEqual(price.added.map((s) => s.pane), [0]);
  assert.deepEqual(price.c.paneUid, [null]);
});

test('a result with the same plots sets the data in place; only the developing bar moving is one update; other plots rebuild the chart', async () => {
  reset();
  const { c, added } = chartCell([ind('a.pine')]);
  await ready(c);
  const w = FakeWorker.all[0];
  w.say(RESULT);
  assert.equal(c.restyled, 1);
  const s = added[0];
  w.say({ ...RESULT, plots: { Fast: [{ time: 0, value: 7 }] } });
  assert.equal(c.restyled, 1, 'same plots, no rebuild');
  assert.equal(s.data.length, 3);
  assert.equal(s.data[0].value, 7);
  s.updates.length = 0;
  w.say({ ...RESULT, full: false, plots: { Fast: [{ time: 120000, value: 9 }] } });
  assert.deepEqual(s.updates, [{ time: 1120, value: 9 }], 'the last bar moved: one update, never a point older than the last');
  w.say({ ...RESULT, full: false, plots: { Fast: [{ time: 60000, value: 8 }] } });
  assert.equal(s.data[1].value, 8, 'an older bar changed: the whole series is set again');
  w.say({ ...RESULT, plots: { Other: [] }, plotsMeta: { Other: { style: 'style_histogram' } } });
  assert.equal(c.restyled, 2);
  w.say({ ...RESULT, plots: { Other: [] }, plotsMeta: { Other: { style: 'style_histogram', color: '#FF0000' } } });
  assert.equal(c.restyled, 2, 'a plot colour changing with the bar is not another set of plots');
});

test('the legend reads each plot\'s value on the bar, in its colour', async () => {
  reset();
  const { c } = chartCell([ind('a.pine')]);
  await ready(c);
  FakeWorker.all[0].say({ ...RESULT, plots: { Fast: [{ time: 0, value: 1234.5, color: '#FF0000' }, { time: 60000, value: 2 }] } });
  assert.deepEqual(c.pineValues(c.cfg.indicators[0], bar(0), 0.25), [{ text: '1,234.50', color: 'rgba(255,0,0,1)' }]);
  assert.deepEqual(c.pineValues(c.cfg.indicators[0], bar(1), 0.25), [{ text: '2.00', color: 'rgba(41,98,255,1)' }]);
  assert.deepEqual(c.pineValues(c.cfg.indicators[0], bar(2), 0.25).map((v) => v.text), ['—']);
});

test('a Worker error is the indicator\'s note and warning, never an exception on the chart', async () => {
  reset();
  const c = cell([ind('a.pine')]);
  const st = await ready(c);
  const seen = [];
  c.onPineMeta = (uid) => seen.push(uid);
  FakeWorker.all[0].say({ type: 'error', message: 'Syntax error at line 3\nunexpected token' });
  assert.equal(st.error, 'Syntax error at line 3\nunexpected token');
  assert.deepEqual(seen, ['p1']);
  assert.equal(c.pineMeta('p1').error, st.error);
  const note = globalThis.HBStatus.of(c.cfg.indicators[0], { bars: c.bars, i0: 0, i1: 2, pine: c.pineFacts() });
  assert.deepEqual(note, { text: 'Syntax error at line 3', tone: 'warn', title: 'Syntax error at line 3\nunexpected token' });
  FakeWorker.all[0].say({ ...RESULT, warnings: ['ta.foo is not supported', 'x', 'y'] });
  assert.equal(st.error, null, 'the next good answer clears it');
  assert.deepEqual(globalThis.HBStatus.of(c.cfg.indicators[0], { bars: c.bars, i0: 0, i1: 2, pine: c.pineFacts() }),
    { text: 'ta.foo is not supported (+2 more)', tone: 'warn', title: 'ta.foo is not supported\nx\ny' });
});

test('a missing runtime (the Worker script does not load), a missing script and a browser with no Worker are notes too', async () => {
  reset();
  let c = cell([ind('a.pine')]);
  let st = await ready(c);
  let stopped = false, prevented = false;
  FakeWorker.all[0].terminate = () => { stopped = true; };
  FakeWorker.all[0].onerror({ preventDefault() { prevented = true; } });
  assert.match(st.error, /Pine runtime is not available/);
  assert.deepEqual([stopped, prevented, st.w], [true, true, null]);
  assert.equal(globalThis.HBStatus.of(c.cfg.indicators[0], { bars: c.bars, i0: 0, i1: 2, pine: c.pineFacts() }).tone, 'warn');
  FakeWorker.all[0].say({ ...RESULT });
  assert.equal(st.error && st.error.length > 0, true, 'a late answer from the Worker that was dropped is ignored');

  c = cell([ind('gone.pine')]);
  st = await ready(c);
  assert.match(st.error, /"gone\.pine" was not found/);
  assert.equal(FakeWorker.all.length, 1, 'no Worker for a script that is not there');

  const W = globalThis.Worker;
  delete globalThis.Worker;
  c = cell([ind('a.pine')]);
  st = await ready(c);
  globalThis.Worker = W;
  assert.match(st.error, /cannot run Pine scripts/);
});

test('no script picked is quiet; a chart that is not time bars says so and runs nothing', async () => {
  reset();
  let c = cell([ind('')]);
  let st = await ready(c);
  assert.deepEqual([st.error, st.running, FakeWorker.all.length, fetched.length], [null, false, 0, 0]);
  assert.equal(globalThis.HBStatus.of(c.cfg.indicators[0], { bars: c.bars, i0: 0, i1: 2, pine: c.pineFacts() }), null);

  c = cell([ind('a.pine')], { cfg: { root: 'NQ', spec: 'tick:100', indicators: [ind('a.pine')] }, shown: { root: 'NQ', spec: 'tick:100' } });
  st = await ready(c);
  assert.equal(st.error, 'Pine needs a time chart');
  assert.deepEqual([FakeWorker.all.length, fetched.length], [0, 0]);
  assert.equal(globalThis.HBStatus.of(c.cfg.indicators[0], { bars: c.bars, i0: 0, i1: 2, pine: c.pineFacts() }).text, 'Pine needs a time chart');
});

test('rebuilding the chart does not restart the script; another script, other inputs or fresh history do', async () => {
  reset();
  const c = cell([ind('a.pine', {}, { inputs: { Length: 9 } })]);
  await ready(c);
  const w = FakeWorker.all[0];
  c.pineSync(); c.pineSync();
  await later();
  assert.deepEqual([FakeWorker.all.length, w.sent.length, fetched.length], [1, 1, 1], 'a settings or history rebuild alone changes nothing');

  c.cfg.indicators = [ind('a.pine', {}, { inputs: { Length: 20 } })];
  c.pineSync();
  await later();
  assert.deepEqual([FakeWorker.all.length, w.sent.length, w.sent[1].inputs], [1, 2, { Length: 20 }], 'the same Worker starts over on the new inputs');

  c.pineFresh = true;
  c.pineSync();
  await later();
  assert.equal(w.sent.length, 3, 'a new history: the script runs on it');

  c.cfg.indicators = [ind('fp.pine')];
  c.pineSync();
  await later();
  assert.equal(w.stopped, true, 'another script: the old Worker goes');
  assert.equal(FakeWorker.all.length, 0 + 1, 'the footprint script waits for its history, so no new Worker yet');
  w.say({ ...RESULT });
  assert.equal(state(c).data.size, 0, 'and the old one\'s late answer is dropped');
});

test('a late fetch of an older settings change does not start a Worker', async () => {
  reset();
  const c = cell([ind('a.pine')]);
  c.pineSync();
  c.cfg.indicators = [ind('a.pine', {}, { inputs: { Length: 3 } })];
  c.pineSync();
  await later();
  assert.deepEqual(FakeWorker.all.map((w) => w.sent.map((m) => m.inputs)), [[{ Length: 3 }]], 'one Worker, started once, with the newest inputs');
});

test('with no bars yet nothing starts and nothing fails; the first history starts it', async () => {
  reset();
  const c = cell([ind('a.pine')], { bars: [] });
  c.pineSync();
  await later();
  assert.deepEqual([fetched.length, FakeWorker.all.length, state(c).error, state(c).running], [0, 0, null, false]);
  c.bars = [bar(0)];
  c.pineFresh = true;
  c.pineSync();
  await later();
  assert.deepEqual([FakeWorker.all.length, FakeWorker.all[0].sent[0].bars.length], [1, 1]);
});

test('bars of another market drop the old answer at once; the same market keeps it until the new answer comes', async () => {
  reset();
  const c = cell([ind('a.pine')]);
  await ready(c);
  FakeWorker.all[0].say({ ...RESULT });
  assert.equal(state(c).data.size, 1);
  c.pineReplaced();
  assert.deepEqual([state(c).data.size, c.pineFresh], [1, true], 'the same market: the lines stay until the script answers on the new bars');
  c.shown = { root: 'ES', spec: 'time:60' };
  c.pineReplaced();
  assert.equal(state(c).data.size, 0, 'another market: the old market\'s lines go');
  c.shown = { root: 'ES', spec: 'time:300' };
  FakeWorker.all[0].say({ ...RESULT });
  c.pineReplaced();
  assert.equal(state(c).data.size, 0, 'another interval too');
});

test('removing the row stops its Worker and clears its marks; destroy() stops every Worker', async () => {
  reset();
  const c = cell([ind('a.pine'), ind('a.pine', {}, { maxbars: 200 })]);
  c.cfg.indicators[1].uid = 'p2';
  c.pineSync();
  await later();
  FakeWorker.all[0].say({ ...RESULT, shapes: [{ time: 0, shape: 'shape_circle', location: 'AboveBar' }] });
  assert.equal(FakeWorker.all.length, 2);
  c.cfg.indicators = [c.cfg.indicators[1]];
  c.pineSync();
  assert.equal(FakeWorker.all[0].stopped, true);
  assert.equal(FakeWorker.all[1].stopped, false);
  assert.deepEqual(c.extMarkers['pine:p1'], []);
  assert.deepEqual([...c.pine.keys()], ['p2']);

  const sent = [];
  Object.assign(c, { host: { send: (m) => sent.push(m) }, noteTimer: 0, reaching: null, loadWaiters: [], teardown() { this.tornDown = true; } });
  Cell.prototype.destroy.call(c);
  assert.equal(FakeWorker.all[1].stopped, true);
  assert.equal(c.pine.size, 0);
  assert.equal(c.tornDown, true);
});

test('a chart with no Pine row is untouched: no state, no Worker, no fact for the legend, and an old layout\'s rows draw as they did', () => {
  reset();
  const c = cell([{ uid: 'e1', id: 'ema', visible: true, params: C.clampParams('ema', {}) }]);
  delete c.pine;
  c.pineSync();
  c.pineForward([bar(5)]);
  assert.deepEqual([c.pine.size, FakeWorker.all.length, fetched.length], [0, 0, 0]);
  assert.equal(c.need().fp, false);
  const bare = Object.assign(Object.create(Cell.prototype), { cfg: { indicators: [] }, wantFp: false });
  assert.equal(bare.need().fp, false, 'a cell built before the field existed');
  Cell.prototype.destroy.call(Object.assign(bare, { host: { send() {} }, noteTimer: 0, reaching: null, loadWaiters: [], teardown() {} }));
});

test('the drawings layer: one per chart build, fed the whole state each time (boxes, lines, labels, tables, bgcolor stripes); a hidden row feeds it nothing', async () => {
  reset();
  const made = [], attached = [];
  globalThis.HBPineLayer = { PineLayer: class { constructor(Pal, host) { this.args = [Pal, host]; this.updates = []; made.push(this); } update(r) { this.updates.push(r); } } };
  try {
    const { c } = chartCell([ind('a.pine')]);
    c.candles = { attachPrimitive: (l) => attached.push(l) };
    await ready(c);
    assert.deepEqual([made.length, attached.length, made[0].args[0] === P, made[0].args[1] === c], [1, 1, true, true]);
    const box = { left: 0, right: 1, top: 2, bottom: 1 };
    FakeWorker.all[0].say({ ...RESULT, firstMs: 60000, boxes: [box], tables: [{ position: 'top_right' }], plots: { Back: [{ time: 0, color: '#FF000040' }, { time: 60000, color: null }] },
      plotsMeta: { Back: { style: 'background' } } });
    const last = made.at(-1).updates.at(-1);
    assert.deepEqual([last.full, last.firstMs, last.boxes, last.tables, last.lines], [true, 60000, [box], [{ position: 'top_right' }], []]);
    assert.deepEqual(last.plotsMeta, { Back: { style: 'background' } });
    assert.deepEqual(last.plots, { Back: [{ time: 0, color: 'rgba(255,0,0,0.251)' }] }, 'a stripe with no colour is no stripe');
    c.cfg.indicators = [ind('a.pine', { visible: false })];
    c.pineDraw(state(c));
    const hidden = made.at(-1).updates.at(-1);
    assert.deepEqual([hidden.boxes, hidden.tables, hidden.plots], [undefined, undefined, {}]);
    c.pineSync();
    assert.equal(made.length >= 2, true, 'a rebuilt chart has a new layer');
  } finally { delete globalThis.HBPineLayer; }
});

test('a page without the layer (the Lab) says what it cannot draw, once a script has drawings; plain plots and marks are not a note', async () => {
  reset();
  const { c } = chartCell([ind('a.pine')]);
  await ready(c);
  FakeWorker.all[0].say(RESULT);
  assert.deepEqual(c.pineFacts().p1.notes, []);
  FakeWorker.all[0].say({ ...RESULT, boxes: [{ left: 0, right: 1, top: 2, bottom: 1 }] });
  assert.match(c.pineFacts().p1.notes[0], /cannot draw a script's boxes, lines, labels or tables/);
});
