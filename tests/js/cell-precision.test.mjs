import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* The price format of a catalog study's own pane (cell.js buildSeries): two decimals for every study, four for the ones whose catalog
   entry says `digits` (SMI Ergodic: a raw ratio of about 0.04, which two decimals would round to 0.00 / 0.04 / 0.05). */
const require = createRequire(import.meta.url);
globalThis.window = globalThis;
globalThis.HBLayers = {};
globalThis.LightweightCharts = new Proxy({ LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 }, LineType: { Simple: 0, WithSteps: 1, Curved: 2 } },
  { get: (t, k) => (k in t ? t[k] : String(k)) });
require('../../homebase/static/charts/catalog.js');
require('../../homebase/static/charts/cell.js');
const { Cell } = globalThis.HBCell;
const C = globalThis.HBCatalog;

const ind = (id) => ({ uid: id, id, params: C.clampParams(id, {}), visible: true });

function seriesOf(indicators) {
  const added = [];
  const chart = { addSeries: (type, opts) => { const s = { opts: { ...opts }, applyOptions(o) { Object.assign(this.opts, o); }, priceScale: () => ({ applyOptions() {} }),
    createPriceLine() {} }; added.push(s); return s; } };
  const P = new Proxy({ lines: ['#111111', '#222222', '#333333'] }, { get: (t, k) => (k in t ? t[k] : '#444444') });
  const c = Object.assign(Object.create(Cell.prototype), { cfg: { indicators }, chart, P, R: { scalePriceOnly: false }, lines: [], colorOf: {}, inflight: [], paneUid: [],
    lastGood: null, ov: [], host: { changed() {} }, hover: null, drawLevels() {}, drawMarkers() {}, syncFootprint() {}, syncProfile() {}, legendRows() {}, legend() {} });
  c.buildSeries();
  return added;
}

test('an own-pane study formats its axis with the precision its catalog entry asks for, two decimals when it asks for none', () => {
  for (const [id, want] of [['tv_smi', { precision: 4, minMove: 0.0001 }], ['tv_smio', { precision: 4, minMove: 0.0001 }],
    ['tv_rsi', { precision: 2, minMove: 0.01 }], ['tv_bbw', { precision: 2, minMove: 0.01 }], ['rsi', { precision: 2, minMove: 0.01 }]]) {
    const s = seriesOf([ind(id)]);
    assert.ok(s.length > 0, id);
    for (const x of s) assert.deepEqual(x.opts.priceFormat, { type: 'price', ...want }, id);
  }
});
