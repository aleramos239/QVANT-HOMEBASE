import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* Two small cell.js facts (indicator cleanup P2): the legend's eye repaints the calendar flags too (events is not an
   overlay layer: it is the EventFlags primitive, so setVisible must call redrawEvents), and a catalog study that asks
   for `digits: 0` (a count) gets zero decimals, while one that says nothing still gets two. */
const require = createRequire(import.meta.url);
globalThis.window = globalThis;
globalThis.HBLayers = {};
globalThis.LightweightCharts = new Proxy({ LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 }, LineType: { Simple: 0, WithSteps: 1, Curved: 2 } },
  { get: (t, k) => (k in t ? t[k] : String(k)) });
require('../../homebase/static/charts/catalog.js');
require('../../homebase/static/charts/cell.js');
const { Cell } = globalThis.HBCell;
const C = globalThis.HBCatalog;

function cellOf(indicators) {
  const added = [];
  const chart = { addSeries: (type, opts) => { const s = { opts: { ...opts }, applyOptions(o) { Object.assign(this.opts, o); }, priceScale: () => ({ applyOptions() {} }),
    createPriceLine() {} }; added.push(s); return s; } };
  const P = new Proxy({ lines: ['#111111', '#222222', '#333333'] }, { get: (t, k) => (k in t ? t[k] : '#444444') });
  const c = Object.assign(Object.create(Cell.prototype), { cfg: { indicators }, chart, P, R: { scalePriceOnly: false }, lines: [], colorOf: {}, inflight: [], paneUid: [],
    lastGood: null, ov: [], host: { changed() {} }, hover: null, drawLevels() {}, drawMarkers() {}, syncFootprint() {}, syncProfile() {}, legendRows() {}, legend() {} });
  return { c, added };
}

test('the eye repaints the calendar flags', () => {
  const { c } = cellOf([{ uid: 'ev', id: 'events', params: {}, visible: true }]);
  let n = 0;
  c.evl = { redraw() { n++; } };
  c.setVisible('ev', false);
  assert.equal(n, 1);
  c.setVisible('ev', true);
  assert.equal(n, 2);
});

test('digits 0 is honoured on the axis; no digits still means two decimals', () => {
  const def = C.TA_BY_ID.tv_rsi, had = Object.getOwnPropertyDescriptor(def, 'digits');
  const fmts = (id) => { const { c, added } = cellOf([{ uid: id, id, params: C.clampParams(id, {}), visible: true }]); c.buildSeries(); return added.map((s) => s.opts.priceFormat); };
  try {
    def.digits = 0;
    for (const f of fmts('tv_rsi')) assert.deepEqual(f, { type: 'price', precision: 0, minMove: 1 });
    delete def.digits;
    for (const f of fmts('tv_rsi')) assert.deepEqual(f, { type: 'price', precision: 2, minMove: 0.01 });
  } finally { if (had) Object.defineProperty(def, 'digits', had); else delete def.digits; }
});

/* newsui.js (browser only): its overlay painted headline dots and bolts on a store change or a new bar, never on the eye. */
test('the eye repaints the headline dots and bolts at once (newsui overlay)', () => {
  globalThis.HBNews = require('../../homebase/static/charts/news.js');
  globalThis.HBTrade = {};
  globalThis.requestAnimationFrame = (fn) => { fn(); return 0; };
  const el = () => ({ className: '', textContent: '', hidden: false, dataset: {}, classList: { add() {} }, appendChild() {}, remove() {}, addEventListener() {} });
  globalThis.document = { createElement: el };
  const path = require.resolve('../../homebase/static/charts/newsui.js');
  delete require.cache[path];
  require(path);
  const T0 = Date.now() - 600_000;
  const marks = [];
  const cell = { el: el(), cfg: { root: 'NQ', indicators: [{ id: 'headlines', params: { show: 'all' }, visible: true }] }, shown: null,
    chart: { subscribeCrosshairMove() {}, unsubscribeCrosshairMove() {} },
    bars: [{ ms: T0 }, { ms: T0 + 60_000 }], barMs: () => 60_000,
    setExtraMarkers: (name, list) => marks.push([name, list.length]) };
  const o = globalThis.HBNewsUI.overlay(cell);
  globalThis.HBNewsUI.onMessage({ type: 'news', id: 'n1', t_ms: T0 + 60_000, seen_ms: T0 + 60_000, title: 'x', source: 's', tags: [] });
  assert.deepEqual(marks.filter((m) => m[0] === 'news').pop(), ['news', 1]);
  cell.cfg.indicators[0].visible = false;            // the eye: nothing else changed
  o.onIndicators();
  assert.deepEqual(marks.filter((m) => m[0] === 'news').pop(), ['news', 0]);
  cell.cfg.indicators[0].visible = true;
  o.onIndicators();
  assert.deepEqual(marks.filter((m) => m[0] === 'news').pop(), ['news', 1]);
  o.destroy();
});
