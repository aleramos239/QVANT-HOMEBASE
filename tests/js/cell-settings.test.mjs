import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

/* The indicator settings in cell.js (2026-10-22): the footprint / profile options and colours it hands the primitives, the big-print
   markers, the Delta divergence / SMT arrows, Volume, Sessions, Levels, and the pane studies' decimals and bar colours. Every default
   is compared with cell.js as committed at HEAD (OLD) so that "no style + default inputs" draws exactly what it always did. */
const require = createRequire(import.meta.url);
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
globalThis.window = globalThis;
globalThis.HBLayers = {};
globalThis.LightweightCharts = new Proxy({ LineStyle: { Solid: 0, Dotted: 1, Dashed: 2 }, LineType: { Simple: 0, WithSteps: 1, Curved: 2 } },
  { get: (t, k) => (k in t ? t[k] : String(k)) });
require('../../homebase/static/charts/catalog.js');
const flowmath = require('../../homebase/static/charts/flowmath.js');
const C = globalThis.HBCatalog;
(0, eval)(execFileSync('git', ['show', 'HEAD:homebase/static/charts/cell.js'], { cwd: root, encoding: 'utf8', maxBuffer: 1 << 26 }));
const Old = globalThis.HBCell.Cell;
require('../../homebase/static/charts/cell.js');
const New = globalThis.HBCell.Cell;
assert.notEqual(Old, New);

/* The inputs go in as given over the clamped defaults: the cell must cope with a junk value too (the dialog clamps, a test or an old layout may not). */
const ind = (id, params = {}, more = {}) => ({ uid: id, id, params: { ...C.clampParams(id, params), ...params }, visible: true, ...more });
const styled = (inst, style) => ({ ...inst, style });
const sty = (color, alpha) => (alpha == null ? { color } : { color, alpha });
const P = new Proxy({ up: '#089981', down: '#F23645', upA: 'rgba(8,153,129,.5)', downA: 'rgba(242,54,69,.5)', level: '#787B86', text2: '#787B86', lines: ['#111111'] },
  { get: (t, k) => (k in t ? t[k] : '#444444') });
const make = (K, indicators, more = {}) => Object.assign(Object.create(K.prototype), { cfg: { root: 'NQ', spec: 'time:60', indicators }, wantFp: false, bars: [], P, ...more });
const both = (fn) => [fn(Old), fn(New)];
const same = (fn, msg) => { const [a, b] = both(fn); assert.deepEqual(b, a, msg); return b; };

/* ---------- footprint / profile ---------- */

function fpSet(K, inst) {
  let got;
  make(K, [inst], { fp: { set: (...a) => { got = a; } }, tick: 0.25 }).syncFootprint();
  return got;
}

test('footprint: every old option is handed over unchanged; the new ones carry the input, and no style leaves every colour undefined', () => {
  const inst = ind('footprint');
  const [o, n] = [fpSet(Old, inst), fpSet(New, inst)];
  for (const k of Object.keys(o[4])) assert.deepEqual(n[4][k], o[4][k], k);
  assert.deepEqual(n.slice(0, 4), o.slice(0, 4));
  assert.deepEqual(n[4].colors, { buy: undefined, sell: undefined, deltaPos: undefined, deltaNeg: undefined, poc: undefined });
  const f = ind('footprint', { fontMax: 13, fontMin: 7, barFill: 70, minBarPx: 80, minRowPx: 12, autoRowPx: 14, pocWidth: 3, stackWidth: 4, edgeWidth: 5, fontFamily: 'sans' });
  const ex = fpSet(New, f)[4];
  assert.deepEqual([ex.fontMax, ex.fontMin, ex.barFill, ex.minBarPx, ex.minRowPx, ex.autoRowPx, ex.pocWidth, ex.stackWidth, ex.edgeWidth, ex.fontFamily],
    [13, 7, 70, 80, 12, 14, 3, 4, 5, 'sans']);
  assert.equal(fpSet(Old, f)[4].fontMax, undefined, 'the old cell never handed the size over');
});

test('footprint: the Style colours reach the primitive with their opacity; a missing or junk style falls back', () => {
  const st = { buy: sty('#112233'), sell: sty('#445566', 50), deltaPos: sty('#010203'), deltaNeg: sty('#040506'), poc: sty('#AABBCC') };
  const c = fpSet(New, styled(ind('footprint'), st))[4].colors;
  assert.deepEqual(c, { buy: C.styleColor({ style: st }, 'buy'), sell: 'rgba(68,85,102,0.5)', deltaPos: C.styleColor({ style: st }, 'deltaPos'),
    deltaNeg: C.styleColor({ style: st }, 'deltaNeg'), poc: C.styleColor({ style: st }, 'poc') });
  assert.equal(c.sell, C.styleColor({ style: st }, 'sell'));
  assert.deepEqual(fpSet(New, styled(ind('footprint'), { buy: 'junk', sell: null }))[4].colors.buy, undefined);
});

test('footprint: hideCandles is on unless the instance says false, and the zoom-to-read width follows minBarPx + 6', () => {
  assert.equal(make(New, [ind('footprint')]).fpHides(), true);
  assert.equal(make(New, [ind('footprint', { hideCandles: false })]).fpHides(), false);
  assert.equal(make(New, []).fpHides(), true);
  const zoom = (K, inst) => {
    let r;
    const c = make(K, inst ? [inst] : [], { bars: new Array(100).fill({}), chart: { timeScale: () => ({ width: () => 1240, setVisibleLogicalRange: (x) => { r = x; } }) } });
    c.zoomToRead();
    return r;
  };
  assert.deepEqual(zoom(New, ind('footprint')), zoom(Old, ind('footprint')));
  assert.deepEqual(zoom(New, null), zoom(Old, null));
  assert.notDeepEqual(zoom(New, ind('footprint', { minBarPx: 120 })), zoom(Old, ind('footprint')));
  assert.equal(zoom(New, ind('footprint', { minBarPx: 120 })).from, 100 - 1 - (Math.floor(1240 / 126) - 2));
});

function profSet(K, inst) {
  let got;
  make(K, [inst], { prof: { set: (...a) => { got = a; } }, profile: { poc: 1 }, tick: 0.25, priorNaked: () => false }).syncProfile();
  return got;
}

test('profile: the old options are unchanged; the new inputs and the six colours are handed over', () => {
  const [o, n] = [profSet(Old, ind('profile')), profSet(New, ind('profile'))];
  for (const k of Object.keys(o[2])) assert.deepEqual(n[2][k], o[2][k], k);
  assert.deepEqual(n[2].colors, { body: undefined, va: undefined, poc: undefined, ghost: undefined, priorVaLines: undefined, priorPoc: undefined });
  const ex = profSet(New, styled(ind('profile', { ghostOpacity: 80, lineWidth: 3, labels: false, fontSize: 13, highlightPoc: false }),
    { body: sty('#112233'), priorPoc: sty('#445566', 40) }))[2];
  assert.deepEqual([ex.ghostOpacity, ex.lineWidth, ex.labels, ex.fontSize, ex.highlightPoc], [80, 3, false, 13, false]);
  assert.equal(ex.colors.body, '#112233');
  assert.equal(ex.colors.priorPoc, 'rgba(68,85,102,0.4)');
  assert.equal(ex.colors.va, undefined);
});

/* ---------- markers: big prints, Delta divergence, SMT ---------- */

function markers(K, indicators, bars, more = {}) {
  let got;
  const c = make(K, indicators, { bars, markers: { setMarkers: (m) => { got = m; } }, extMarkers: {}, barMs: () => 60000, ...more });
  window.HBDrawings = { placeMarkers: () => [] };
  c.drawMarkers();
  return got;
}
const printBars = () => [{ tt: 10, big: [[1, 100, 25, 1], [2, 100, 12, -1], [3, 100, 90, 1]], sv: {} }, { tt: 20, big: [[1, 100, 300, -1]], sv: {} }];

test('big prints: markers identical by default (scale off and on); shape, colours and sizes follow the inputs', () => {
  for (const scale of [false, true]) {
    window.HBFlowMath = flowmath;
    same((K) => markers(K, [ind('bigprints', { min: 10, scale })], printBars()), `scale ${scale}`);
  }
  window.HBFlowMath = flowmath;
  const base = markers(New, [ind('bigprints', { min: 10 })], printBars());
  assert.deepEqual(base.map((m) => m.shape), ['circle', 'circle', 'circle', 'circle']);
  assert.deepEqual(base.map((m) => m.color), ['#089981', '#F23645', '#089981', '#F23645']);
  const sq = markers(New, [styled(ind('bigprints', { min: 10, scale: false, shape: 'arrowUp', markerMin: 1.4 }), { buy: sty('#112233'), sell: sty('#445566', 50) })], printBars());
  assert.deepEqual(sq.map((m) => m.shape), Array(4).fill('arrowUp'));
  assert.deepEqual(sq.map((m) => m.color), ['#112233', 'rgba(68,85,102,0.5)', '#112233', 'rgba(68,85,102,0.5)']);
  assert.deepEqual(sq.map((m) => m.size), Array(4).fill(1.4), 'scale off: every marker is the smallest size');
  assert.equal(markers(New, [ind('bigprints', { min: 10, shape: 'junk' })], printBars())[0].shape, 'circle');
});

test('big prints: the size options go to flowmath markerSize as a fourth argument', () => {
  const calls = [];
  window.HBFlowMath = { markerSize: (...a) => { calls.push(a); return 1; } };
  markers(New, [ind('bigprints', { min: 10, scale: true, markerMin: 1, markerMax: 3, fullAt: 16 })], printBars());
  assert.equal(calls.length, 4);
  assert.deepEqual(calls[0], [25, 10, true, { markerMin: 1, markerMax: 3, fullAt: 16 }]);
  assert.deepEqual(calls[0].slice(0, 3), [25, 10, true]);
  window.HBFlowMath = flowmath;
});

function divBars() {
  const bars = [0, 1, 2, 3, 4, 5, 6].map((i) => ({ tt: 100 + i, ms: i, sv: {} }));
  bars[4].sv['ddiv:5'] = { dir: -1, ago: 2 };
  bars[5].sv['ddiv:5'] = { dir: 1, ago: 1 };
  bars[4].sv['smt:6:36'] = { dir: 1, ago: 1 };
  bars[6].sv['smt:6:36'] = { dir: -1, ago: 3 };
  return bars;
}
const marks = (K, inst) => make(K, [inst], { bars: divBars() }).studyMarks();

test('ddiv: marks identical by default; colours, size, labels and side follow the inputs', () => {
  const base = same((K) => marks(K, ind('ddiv')));
  assert.deepEqual(base.map((m) => [m.color, m.size, m.text, m.shape]), [['#F23645', 1, 'Δ', 'arrowDown'], ['#089981', 1, 'Δ', 'arrowUp']]);
  const st = styled(ind('ddiv', { size: '1.5', labels: false }), { bear: sty('#112233'), bull: sty('#445566', 50) });
  assert.deepEqual(marks(New, st).map((m) => [m.color, m.size, m.text]), [['#112233', 1.5, ''], ['rgba(68,85,102,0.5)', 1.5, '']]);
  assert.deepEqual(marks(New, ind('ddiv', { side: 'up' })).map((m) => m.shape), ['arrowUp']);
  assert.deepEqual(marks(New, ind('ddiv', { side: 'down' })).map((m) => m.shape), ['arrowDown']);
  assert.deepEqual(marks(New, ind('ddiv', { size: 'junk' })).map((m) => m.size), [1, 1], 'a junk size falls back to the mark\'s own');
});

test('smt: marks identical by default; the up / down colours and the size follow the inputs', () => {
  const base = same((K) => marks(K, ind('smt')));
  assert.deepEqual(base.map((m) => [m.color, m.size, m.text]), [['#089981', 1, 'SMT'], ['#F23645', 1, 'SMT']]);
  const out = marks(New, styled(ind('smt', { size: '0.7' }), { up: sty('#112233'), down: sty('#445566') }));
  assert.deepEqual(out.map((m) => [m.color, m.size]), [['#112233', 0.7], ['#445566', 0.7]]);
});

test('another marker study (fractals) is untouched by the ddiv / smt settings', () => {
  const bars = [0, 1, 2, 3, 4].map((i) => ({ tt: 100 + i, ms: i, sv: {} }));
  bars[4].sv['tv:fractals:2'] = { up: 101, dn: 99 };
  same((K) => make(K, [ind('tv_fractals')], { bars }).studyMarks());
});

/* ---------- series: Volume, Sessions, decimals, bar colours ---------- */

function buildFor(K, indicators, more = {}) {
  const added = [], margins = [], refs = [];
  const chart = { addSeries: (type, opts, where) => {
    const s = { opts: { ...opts }, applyOptions(o) { Object.assign(this.opts, o); }, priceScale: () => ({ applyOptions: (o) => margins.push(o) }),
      createPriceLine: (o) => refs.push(o.price) };
    added.push({ type, opts, where, s });
    return s;
  } };
  const c = make(K, indicators, { chart, R: { scalePriceOnly: false }, lines: [], colorOf: {}, inflight: [], lastGood: null, ov: [],
    host: { changed() {} }, hover: null, ...more });
  c.buildSeries();
  return { c, added: added.map(({ type, opts, where }) => ({ type, opts, where })), margins, refs };
}
const built = (K, inds) => { const { added, margins, refs } = buildFor(K, inds); return { added, margins, refs }; };

test('volume: series and pane share identical by default; heightPct moves the pane share; colorBy candle colours by open / close', () => {
  const v = ind('volume');
  assert.deepEqual(built(New, [v]), built(Old, [v]));
  assert.deepEqual(built(New, [v]).margins, [{ scaleMargins: { top: 0.8, bottom: 0 } }]);
  assert.deepEqual(built(New, [ind('volume', { heightPct: 35 })]).margins, [{ scaleMargins: { top: 0.65, bottom: 0 } }]);
  assert.deepEqual(built(New, [{ ...v, params: { colorBy: 'delta' } }]).margins, built(Old, [v]).margins, 'a missing heightPct is 20');
  assert.deepEqual(built(New, [{ ...v, params: { heightPct: 'junk' } }]).margins, built(Old, [v]).margins);
  // a bar that closed up with negative delta
  const b = { tt: 5, v: 40, d: -3, o: 10, c: 11, sv: {} };
  const point = (K, inst) => { const { c } = buildFor(K, [inst]); return c.point(c.lines[0], b); };
  assert.deepEqual(point(New, v), point(Old, v));
  assert.equal(point(New, v).color, P.downA);
  assert.equal(point(New, ind('volume', { colorBy: 'candle' })).color, P.upA);
  const flip = point(New, styled(ind('volume', { colorBy: 'candle' }), { up: sty('#112233'), down: sty('#445566') }));
  assert.equal(flip.color, C.lineColor(sty('#112233')));
});

test('sess: lines identical by default; width, dash and the two show switches follow the inputs', () => {
  const s = ind('sess');
  assert.ok(buildFor(New, [s]).added.length >= 2);
  assert.deepEqual(built(New, [s]), built(Old, [s]));
  const one = (inst) => buildFor(New, [inst]).added.map((a) => a.opts);
  const dflt = one(s);
  const w = one(ind('sess', { lineWidth: 3 }));
  assert.ok(w.every((o) => o.lineWidth === 3) && dflt.every((o) => o.lineWidth === 1));
  const half = dflt.length / 2;
  assert.deepEqual(dflt.slice(0, 2).map((o) => o.lineStyle), [0, 2], 'high solid, low dashed');
  assert.deepEqual(one(ind('sess', { hiDash: 'dotted', loDash: 'solid' })).slice(0, 2).map((o) => o.lineStyle), [1, 0]);
  assert.deepEqual(one(ind('sess', { loDash: 'junk' })).slice(0, 2).map((o) => o.lineStyle), [0, 2]);
  const lines = (inst) => buildFor(New, [inst]).c.lines.map((l) => [l.part, l.own]);
  assert.ok(lines(ind('sess', { showHigh: false })).filter(([p]) => p === 'hi').every(([, own]) => own === false));
  assert.ok(lines(ind('sess', { showHigh: false })).filter(([p]) => p === 'lo').every(([, own]) => own === true));
  assert.ok(lines(ind('sess', { showLow: false })).filter(([p]) => p === 'lo').every(([, own]) => own === false));
  assert.ok(half >= 1);
});

test('pane studies: decimals default to the catalog\'s, and the digits input sets the axis precision', () => {
  for (const id of ['bkimb', 'tspeed', 'pressure', 'tv_rsi', 'tv_smi']) {
    if (!C.TA_BY_ID[id]) continue;
    assert.deepEqual(built(New, [ind(id)]), built(Old, [ind(id)]), id);
  }
  const prec = (inst) => buildFor(New, [inst]).added[0].opts.priceFormat;
  assert.deepEqual(prec(ind('bkimb')), { type: 'price', precision: 2, minMove: 0.01 });
  assert.deepEqual(prec(ind('bkimb', { digits: 4 })), { type: 'price', precision: 4, minMove: 0.0001 });
  assert.deepEqual(prec(ind('pressure', { digits: 0 })), { type: 'price', precision: 0, minMove: 1 });
  assert.equal(prec({ ...ind('bkimb'), params: { levels: '10' } }).precision, 2, 'no digits key: 2');
  assert.equal(prec({ ...ind('bkimb'), params: { levels: '10', digits: 'x' } }).precision, 2);
  assert.equal(prec(ind('bkdepth')).precision, 0, 'an entry that asks for 0 keeps it');
});

test('bkimb: bar colours identical by default; the up / down Style colours colour the bars', () => {
  const bars = [{ tt: 1, sv: { 'bk:imb10': 0.4 } }, { tt: 2, sv: { 'bk:imb10': -0.2 } }];
  const pts = (K, inst) => { const { c } = buildFor(K, [inst]); return bars.map((b) => c.point(c.lines[0], b)); };
  assert.deepEqual(pts(New, ind('bkimb')), pts(Old, ind('bkimb')));
  assert.deepEqual(pts(New, ind('bkimb')).map((p) => p.color), [P.upA, P.downA]);
  assert.deepEqual(pts(New, styled(ind('bkimb'), { up: sty('#112233'), down: sty('#445566', 50) })).map((p) => p.color), ['#112233', 'rgba(68,85,102,0.5)']);
});

const pressBars = () => [4, 12, 30, -4, -12, -30, -20].map((p, i) => ({ tt: i + 1, sv: { 'press:5': { p } } }));
const pressPts = (K, inst) => { const { c } = buildFor(K, [inst]); const l = c.lines.find((x) => x.part === 'p'); return pressBars().map((b) => c.point(l, b)); };

test('pressure: bar colours identical by default; lean / push and the five Style colours follow the inputs', () => {
  assert.deepEqual(pressPts(New, ind('pressure')), pressPts(Old, ind('pressure')));
  assert.deepEqual(pressPts(New, ind('pressure')).map((p) => p.color),
    ['rgba(120,123,134,.45)', P.upA, P.up, 'rgba(120,123,134,.45)', P.downA, P.down, P.downA]);
  assert.deepEqual(pressPts(New, ind('pressure', { lean: 5, push: 15 })).map((p) => p.color),
    ['rgba(120,123,134,.45)', P.upA, P.up, 'rgba(120,123,134,.45)', P.downA, P.down, P.down]);
  const st = { even: sty('#000001'), leanUp: sty('#000002'), leanDown: sty('#000003'), pushUp: sty('#000004'), pushDown: sty('#000005', 50) };
  assert.deepEqual(pressPts(New, styled(ind('pressure'), st)).map((p) => p.color),
    ['#000001', '#000002', '#000004', '#000001', '#000003', 'rgba(0,0,5,0.5)', '#000003']);
  // a missing key / junk falls back to the line's own bands
  assert.deepEqual(pressPts(New, { ...ind('pressure'), params: { length: 5, lean: 'x' } }).map((p) => p.color), pressPts(Old, ind('pressure')).map((p) => p.color));
  // push can never sit under lean
  assert.deepEqual(pressPts(New, ind('pressure', { lean: 20, push: 10 })).map((p) => p.color).slice(0, 3), ['rgba(120,123,134,.45)', 'rgba(120,123,134,.45)', P.up]);
});

test('pressure: the reference levels sit at the instance\'s push and lean', () => {
  assert.deepEqual(built(New, [ind('pressure')]).refs, [25, 10, -10, -25]);
  assert.deepEqual(built(New, [ind('pressure')]).refs, built(Old, [ind('pressure')]).refs);
  assert.deepEqual(built(New, [ind('pressure', { lean: 5, push: 40 })]).refs, [40, 5, -5, -40]);
});

test('tspeed: the burst line is the multiple of the wire\'s 3 x median; the default draws the wire\'s own numbers', () => {
  const wire = [{ rate: 20, burst: 30, hot: 20 }, { rate: 12, burst: 30, hot: null }, { rate: 5, burst: null, hot: null }];
  const bars = wire.map((v, i) => ({ tt: i + 1, sv: { 'tspeed:200': v } }));
  const pts = (K, inst) => { const { c } = buildFor(K, [inst]); return ['rate', 'hot', 'burst'].map((part) => bars.map((b) => c.point(c.lines.find((l) => l.part === part), b))); };
  assert.deepEqual(pts(New, ind('tspeed')), pts(Old, ind('tspeed')));
  const six = pts(New, ind('tspeed', { burstMult: 6 }));
  assert.deepEqual(six[2].map((p) => p.value), [60, 60, undefined], 'burst line = 6 x the median (3 x median = 30 -> 10 -> 60)');
  assert.deepEqual(six[1].map((p) => p.value), [undefined, undefined, undefined], 'nothing reaches 60');
  const two = pts(New, ind('tspeed', { burstMult: 2 }));
  assert.deepEqual(two[2].map((p) => p.value), [20, 20, undefined]);
  assert.deepEqual(two[1].map((p) => p.value), [20, undefined, undefined], 'rate 20 >= 20 is a burst; 12 is not');
  assert.deepEqual(pts(New, { ...ind('tspeed'), params: { length: 200, burstMult: 'x' } }), pts(Old, ind('tspeed')));
});

/* ---------- levels ---------- */

function levelsRun(K, inst, steps) {
  const created = [], removed = [], applied = [];
  const candles = {
    createPriceLine: (o) => { const line = { opts: { ...o }, options() { return this.opts; }, applyOptions(x) { applied.push(x); Object.assign(this.opts, x); } }; created.push(o); return line; },
    removePriceLine: (l) => removed.push(l),
  };
  const lv = { pdh: 110, pdl: 90, pdc: 100, onh: 105, onl: 95, rth_open: 101 };
  const c = make(K, inst ? [inst] : [], { candles, levelLines: {}, bars: [{ sv: { levels: lv } }] });
  c.drawLevels();
  for (const f of steps || []) f(c, lv);
  return { created, removed, applied, c };
}

test('levels: the six price lines are created exactly as before by default', () => {
  const a = levelsRun(Old, ind('levels')), b = levelsRun(New, ind('levels'));
  assert.deepEqual(b.created, a.created);
  assert.equal(b.created.length, 6);
  assert.equal(b.created[0].color, '#787B86');
  assert.equal(b.created[0].lineStyle, 2);
  assert.equal(b.created[0].title, 'PDH');
  // and a price move updates only the price, as before
  const move = (c, lv) => { lv.pdh = 111; c.drawLevels(); };
  assert.deepEqual(levelsRun(New, ind('levels'), [move]).applied, levelsRun(Old, ind('levels'), [move]).applied);
  assert.deepEqual(levelsRun(New, ind('levels'), [move]).applied, [{ price: 111 }]);
});

test('levels: colour per line, width, dash, labels and the six show switches', () => {
  const st = { pdh: sty('#112233'), open: sty('#445566', 50) };
  const r = levelsRun(New, styled(ind('levels', { width: 3, dash: 'dotted', labels: false }), st));
  assert.equal(r.created[0].color, '#112233');
  assert.equal(r.created[5].color, 'rgba(68,85,102,0.5)');
  assert.equal(r.created[1].color, '#787B86', 'a line with no style keeps the theme level colour');
  assert.ok(r.created.every((o) => o.lineWidth === 3 && o.lineStyle === 1 && o.axisLabelVisible === false && o.title === ''));
  const off = levelsRun(New, ind('levels', { showPdh: false, showOpen: false }));
  assert.deepEqual(off.created.map((o) => o.title), ['PDL', 'PDC', 'ONH', 'ONL']);
  assert.deepEqual(levelsRun(New, ind('levels', { dash: 'junk', width: 'x' })).created, levelsRun(Old, ind('levels')).created);
});

test('levels: a change on the instance reaches the lines already drawn (applyOptions), and a switch removes or brings back a line', () => {
  const swap = (inst) => (c, lv) => { c.cfg.indicators = [inst]; c.drawLevels(); };
  const r = levelsRun(New, ind('levels'), [swap(styled(ind('levels', { width: 2 }), { pdl: sty('#112233') }))]);
  assert.equal(r.applied.length, 6);
  assert.ok(r.applied.every((o) => o.lineWidth === 2));
  assert.equal(r.applied[1].color, '#112233');
  const hid = levelsRun(New, ind('levels'), [swap(ind('levels', { showPdc: false }))]);
  assert.equal(hid.removed.length, 1);
  const back = levelsRun(New, ind('levels'), [swap(ind('levels', { showPdc: false })), swap(ind('levels'))]);
  assert.equal(back.created.length, 7);
  const gone = levelsRun(New, ind('levels'), [swap(ind('levels', {}, { visible: false }))]);
  assert.equal(gone.removed.length, 6, 'the eye off still removes every line');
});
