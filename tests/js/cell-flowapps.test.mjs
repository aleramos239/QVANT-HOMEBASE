import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* The order-flow apps and the TradingView shapes in cell.js (2026-10-21): what a chart asks the server for, the footprint and profile options it
   hands the primitives, two marks on one bar, and a line drawn as dots. Loaded under minimal stubs and driven through Cell.prototype. */
const require = createRequire(import.meta.url);
globalThis.window = globalThis;
globalThis.HBLayers = {};
globalThis.LightweightCharts = new Proxy({ LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 }, LineType: { Simple: 0, WithSteps: 1, Curved: 2 } },
  { get: (t, k) => (k in t ? t[k] : String(k)) });
require('../../homebase/static/charts/catalog.js');
require('../../homebase/static/charts/cell.js');
const { Cell } = globalThis.HBCell;
const C = globalThis.HBCatalog;

const ind = (id, params = {}, more = {}) => ({ uid: id, id, params: C.clampParams(id, params), visible: true, ...more });
const stub = (indicators, more = {}) => Object.assign(Object.create(Cell.prototype), { cfg: { root: 'NQ', spec: 'time:60', indicators }, wantFp: false, bars: [],
  P: { up: '#0f0', down: '#f00' }, ...more });

test('need(): bigtrades asks for the orders (flow); naked POCs, absorption and a traded-mode TPO ask for the footprint', () => {
  const need = (...list) => stub(list).need();
  assert.deepEqual(need(), { fp: false, big: false, flow: false });
  assert.deepEqual(need(ind('bigtrades')), { fp: false, big: false, flow: true });
  for (const id of ['npoc', 'mwabs']) assert.deepEqual(need(ind(id)), { fp: true, big: false, flow: false }, id);
  assert.deepEqual(need(ind('cstat')), { fp: false, big: false, flow: false });     // the strip counts trades from the bar's own `n`
  assert.equal(need(ind('tpo', { mode: 'traded' })).fp, true);
  assert.equal(need(ind('tpo')).fp, false, 'a range TPO needs only the bars\' high and low');
  for (const id of ['dturn', 'dstr']) assert.deepEqual(need(ind(id)), { fp: false, big: false, flow: false }, `${id}: delta and its extremes ride every bar`);
  assert.equal(need(ind('bigtrades', {}, { visible: false })).flow, true, 'a hidden one counts: showing it again stays instant');
});

test('syncFootprint hands the primitive the new options, and the defaults say nothing the footprint did not already', () => {
  let got;
  const c = stub([ind('footprint')], { fp: { set: (...a) => { got = a; } }, tick: 0.25 });
  c.syncFootprint();
  const ex = got[4];
  assert.deepEqual([ex.text, ex.imb, ex.zero, ex.edge, ex.minvol, ex.mindiff], [undefined, 'homebase', 'one', 'one', 0, 0]);
  assert.deepEqual([ex.numbers, ex.stack, ex.rows], ['both', 3, 'auto']);
  c.cfg.indicators = [ind('footprint', { text: 'trades', imb: 'atas', zero: 'skip', edge: 'skip', minvol: 5, mindiff: 2 })];
  c.syncFootprint();
  assert.deepEqual([got[4].text, got[4].imb, got[4].zero, got[4].edge, got[4].minvol, got[4].mindiff], ['trades', 'atas', 'skip', 'skip', 5, 2]);
});

test('syncProfile hands the primitive the value-area method', () => {
  let got;
  const c = stub([ind('profile')], { prof: { set: (...a) => { got = a; } }, profile: { poc: 1 }, tick: 0.25, priorNaked: () => false });
  c.syncProfile();
  assert.equal(got[2].method, 'homebase');
  c.cfg.indicators = [ind('profile', { method: 'sierra' })];
  c.syncProfile();
  assert.equal(got[2].method, 'sierra');
});

test('fractals and pivots: a top and a bottom confirmed on one bar give two markers on the same swing bar', () => {
  const bars = [0, 1, 2, 3, 4].map((i) => ({ tt: 100 + i, ms: i, sv: {} }));
  bars[4].sv['tv:fractals:2'] = { up: 101, dn: 99 };
  bars[3].sv['tv:fractals:2'] = { up: 102 };
  const c = stub([ind('tv_fractals')], { bars });
  assert.deepEqual(c.studyMarks().map((m) => [m.time, m.position, m.shape]),
    [[101, 'aboveBar', 'arrowDown'], [102, 'aboveBar', 'arrowDown'], [102, 'belowBar', 'arrowUp']]);
});

function seriesOf(indicators) {
  const added = [];
  const chart = { addSeries: (type, opts) => { const s = { opts: { ...opts }, applyOptions(o) { Object.assign(this.opts, o); }, priceScale: () => ({ applyOptions() {} }) }; added.push(s); return s; } };
  const P = new Proxy({ lines: ['#111111', '#222222', '#333333'] }, { get: (t, k) => (k in t ? t[k] : '#444444') });
  const c = Object.assign(Object.create(Cell.prototype), { cfg: { indicators }, chart, P, R: { scalePriceOnly: false }, lines: [], colorOf: {}, inflight: [],
    lastGood: null, ov: [], host: { changed() {} }, hover: null, drawLevels() {}, drawMarkers() {}, syncFootprint() {}, syncProfile() {}, legendRows() {}, legend() {} });
  c.buildSeries();
  return added;
}

test('a line the catalog marks `dots` is drawn as points, not joined; the others stay joined lines', () => {
  const sar = seriesOf([ind('tv_sar')]);
  assert.deepEqual(sar.map((s) => [s.opts.lineVisible, s.opts.pointMarkersVisible]), [[false, true]]);
  const st = seriesOf([ind('tv_supertrend')]);
  assert.ok(st.length > 0 && st.every((s) => s.opts.lineVisible === undefined && s.opts.pointMarkersVisible === undefined));
});
