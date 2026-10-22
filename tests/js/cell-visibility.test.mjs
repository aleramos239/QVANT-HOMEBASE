import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* The legend's eye and what the chart draws must say the same thing. Two ways they did not (2026-10-12, owner:
   "sometimes the indicator is hidden but still shows on chart or is not hidden but shows hidden"):
     1. a line carried its own Style-tab `visible` and that WON over the instance's eye whenever the chart was
        rebuilt (a setting changed, a timezone, a resubscribe): a hidden indicator drew again, its legend row still
        greyed. And the eye turning an indicator back on showed every line, including the ones the Style tab hid.
     2. the overlay layers (flow bubbles, Level 2 lines, book events) repainted only on a new bar, so an eye click
        left them as they were until the next one.
   cell.js is browser-only: loaded under minimal stubs, driven through Cell.prototype on a bare object. */
const require = createRequire(import.meta.url);
globalThis.window = globalThis;
globalThis.HBLayers = {};
globalThis.LightweightCharts = new Proxy({ LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 }, LineType: { Simple: 0, WithSteps: 1, Curved: 2 } },
  { get: (t, k) => (k in t ? t[k] : String(k)) });
require('../../homebase/static/charts/catalog.js');
require('../../homebase/static/charts/settings.js');
require('../../homebase/static/charts/cell.js');
const { Cell } = globalThis.HBCell;

const part = (visible) => ({ color: '#aaaaaa', width: 1, dash: 'solid', visible });
const vwap = (more = {}) => ({ uid: 'vw', id: 'vwap', params: {}, visible: true, style: { main: part(true), band1: part(true) }, ...more });

function chartCell(indicators) {
  const added = [];
  const chart = { addSeries: (type, opts) => {
    const s = { opts: { ...opts }, applyOptions(o) { Object.assign(this.opts, o); }, priceScale: () => ({ applyOptions() {} }) };
    added.push(s);
    return s;
  } };
  const P = new Proxy({ lines: ['#111111', '#222222', '#333333'] }, { get: (t, k) => (k in t ? t[k] : '#444444') });
  const calls = [];
  const c = Object.create(Cell.prototype);
  Object.assign(c, { cfg: { indicators }, chart, P, R: { scalePriceOnly: false }, lines: [], colorOf: {}, inflight: [], lastGood: null,
    ov: [], host: { changed() {} }, hover: null,
    drawLevels() {}, drawMarkers() {}, syncFootprint() {}, syncProfile() {}, legendRows() {}, legend() {} });
  c.calls = calls;
  return { c, added };
}

test('a hidden indicator stays hidden when the chart is rebuilt, whatever its lines\' own Style flag says', () => {
  const { c, added } = chartCell([vwap({ visible: false, params: { band1On: true } })]);
  c.buildSeries();
  assert.ok(added.length >= 2);
  assert.deepEqual(added.map((s) => s.opts.visible), added.map(() => false));
});

test('a shown indicator keeps the lines its Style tab hid hidden', () => {
  const { c, added } = chartCell([vwap({ style: { main: part(true), band1: part(false) }, params: { band1On: true } })]);
  c.buildSeries();
  const vis = added.map((s) => s.opts.visible);
  assert.ok(vis.includes(true) && vis.includes(false));
  assert.equal(c.lines.filter((l) => l.part == null).every((l) => l.s.opts.visible), true);   // the main line is drawn
});

test('the eye turning an indicator back on does not reveal the lines its Style tab hid', () => {
  const { c } = chartCell([vwap({ style: { main: part(true), band1: part(false) }, params: { band1On: true } })]);
  c.buildSeries();
  const before = c.lines.map((l) => l.s.opts.visible);
  c.setVisible('vw', false);
  assert.ok(c.lines.every((l) => l.s.opts.visible === false));
  c.setVisible('vw', true);
  assert.deepEqual(c.lines.map((l) => l.s.opts.visible), before);
});

test('the eye tells every overlay layer, which repaints (a flow bubble layer waited for the next bar)', () => {
  const { c } = chartCell([vwap()]);
  c.buildSeries();
  let told = 0;
  const log = console.error;
  console.error = () => {};                          // the throwing layer is logged, not rethrown
  c.ov = [{ onIndicators() { told++; } }, {}, { onIndicators() { throw new Error('a layer must not break the eye'); } }];
  try { c.setVisible('vw', false); } finally { console.error = log; }
  assert.equal(told, 1);
  assert.equal(c.cfg.indicators[0].visible, false);
});

test('a VWAP\'s bands are drawn around every line that has bands on, each in its own colour', () => {
  const { c } = chartCell([vwap({ params: { band1On: true, band1Mult: 1,
    more: [{ anchor: 'rth', on: true, color: '#112233' }, { anchor: 'week', on: true, color: '#445566', bands: false }] } })]);
  c.buildSeries();
  const bands = c.lines.filter((l) => l.part != null);
  assert.deepEqual(bands.map((l) => [l.src, l.part, l.s.opts.color]),
    [['vwap', 1, '#aaaaaa'], ['vwap', -1, '#aaaaaa'], ['vwap:rth', 1, '#112233'], ['vwap:rth', -1, '#112233']]);   // week has bands off
});

test('an instance with no style (a template, an old save) starts its off-by-default lines hidden, as its Style tab shows them; a line switched on there is drawn', () => {
  const { c } = chartCell([{ uid: 'tv', id: 'tv_vwap', params: {}, visible: true }, { uid: 'ud', id: 'tv_updown', params: {}, visible: true }]);
  c.buildSeries();
  const seen = (uid) => Object.fromEntries(c.lines.filter((l) => l.uid === uid).map((l) => [l.part, l.s.opts.visible]));
  assert.deepEqual(seen('tv'), { vwap: true, u1: true, l1: true, u2: false, l2: false, u3: false, l3: false });
  assert.deepEqual(seen('ud'), { up: true, down: true, delta: false });
  const style = globalThis.HBCatalog.defaultStyle('tv_vwap', []);
  style.u2.visible = true;
  const on = chartCell([{ uid: 'tv', id: 'tv_vwap', params: {}, visible: true, style }]);
  on.c.buildSeries();
  assert.deepEqual(on.c.lines.filter((l) => l.part === 'u2' || l.part === 'l2').map((l) => [l.part, l.s.opts.visible]), [['u2', true], ['l2', false]]);
});

test('the legend lists the lines the chart draws: no value for an off-by-default line of an instance with no style, one for a line switched on', () => {
  globalThis.document = { createElement: () => ({ style: {}, append() {} }) };
  const bar = { o: 1, h: 2, l: 0.5, c: 1.5, v: 1, d: 0 };
  const listed = (inst) => {
    const shown = [];
    const c = Object.assign(Object.create(Cell.prototype), { bars: [bar], P: { text: '#000', up: '#0f0', down: '#f00', accent: '#08f' }, R: { ohlc: true, indValues: true, precision: 2 },
      tick: 0.25, colorOf: {}, lg: { ohlc: { replaceChildren() {} } }, rows: [{ inst, vals: { replaceChildren: (...x) => shown.push(...x) } }] });
    c.legend(null);
    return shown.length;
  };
  assert.equal(listed({ uid: 'tv', id: 'tv_vwap', params: {}, visible: true }), 3, 'vwap, upper 1, lower 1');
  assert.equal(listed({ uid: 'ud', id: 'tv_updown', params: {}, visible: true }), 2, 'up and down, not delta');
  const style = globalThis.HBCatalog.defaultStyle('tv_vwap', []);
  style.u2.visible = true;
  assert.equal(listed({ uid: 'tv', id: 'tv_vwap', params: {}, visible: true, style }), 4, 'the styled instance: its own style rules, band 2 upper switched on');
});
