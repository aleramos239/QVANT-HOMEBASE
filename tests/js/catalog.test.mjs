import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const C = require('../../homebase/static/charts/catalog.js');
const strip = (list) => list.map(({ id, params, visible }) => ({ id, params, visible }));

const VWAP_DEFAULT_PARAMS = { anchor: 'eth', customTime: '02:00',
  band1On: false, band1Mult: 1, band2On: false, band2Mult: 2, band3On: false, band3Mult: 3 };

test('a new chart gets volume, VWAP (ETH), session levels and a 3x footprint', () => {
  assert.deepEqual(strip(C.defaults()), [
    { id: 'volume', params: {}, visible: true },
    { id: 'vwap', params: VWAP_DEFAULT_PARAMS, visible: true },
    { id: 'levels', params: {}, visible: true },
    { id: 'footprint', params: { imbalance: 3 }, visible: true }]);
});

test('every instance gets its own short uid', () => {
  const a = C.instance('ema'), b = C.instance('ema');
  assert.notEqual(a.uid, b.uid);
  assert.ok(a.uid.length >= 1 && a.uid.length <= 40);
  assert.equal(C.instance('nope'), null);
});

test('server keys follow the study wire names and are deduplicated', () => {
  const list = ['vwap', ['vwap', { anchor: 'rth' }], ['ema', { length: 20 }], ['ema', { length: 20 }], 'sma',
    ['vwma', { length: 9 }], 'adx', 'levels', 'cumdelta', 'profile', 'volume', 'delta', 'footprint', 'bigprints']
    .map((x) => (Array.isArray(x) ? C.instance(...x) : C.instance(x)));
  assert.deepEqual(C.serverKeys(list), ['vwap', 'vwap:rth', 'ema:20', 'sma:50', 'vwma:9', 'adx:14', 'levels', 'cumdelta', 'profile']);
  assert.deepEqual(C.serverKeys([]), []);
});

test('VWAP wire keys follow the anchor: eth/rth unchanged, week/month/custom new', () => {
  assert.equal(C.serverKey(C.instance('vwap')), 'vwap');
  assert.equal(C.serverKey(C.instance('vwap', { anchor: 'rth' })), 'vwap:rth');
  assert.equal(C.serverKey(C.instance('vwap', { anchor: 'week' })), 'vwap:week');
  assert.equal(C.serverKey(C.instance('vwap', { anchor: 'month' })), 'vwap:month');
  assert.equal(C.serverKey(C.instance('vwap', { anchor: 'custom', customTime: '02:00' })), 'vwap:t0200');
  assert.equal(C.serverKey(C.instance('vwap', { anchor: 'custom', customTime: '23:59' })), 'vwap:t2359');
  // an invalid customTime never reaches serverKey: clampParams already fell back to the default 02:00
  assert.equal(C.serverKey(C.instance('vwap', { anchor: 'custom', customTime: 'nope' })), 'vwap:t0200');
});

test('SMA/EMA wire keys add a :source only when it is not close; VWMA/ADX never take one', () => {
  assert.equal(C.serverKey(C.instance('ema', { length: 20 })), 'ema:20');
  assert.equal(C.serverKey(C.instance('ema', { length: 20, source: 'close' })), 'ema:20');
  assert.equal(C.serverKey(C.instance('ema', { length: 20, source: 'hl2' })), 'ema:20:hl2');
  assert.equal(C.serverKey(C.instance('sma', { length: 50, source: 'ohlc4' })), 'sma:50:ohlc4');
  assert.equal(C.serverKey(C.instance('vwma', { length: 9 })), 'vwma:9');
  assert.equal(C.serverKey(C.instance('adx', { length: 14 })), 'adx:14');
});

test('params are clamped to their range and type', () => {
  assert.deepEqual(C.clampParams('ema', { length: 0 }), { length: 1, source: 'close' });
  assert.deepEqual(C.clampParams('ema', { length: 5000 }), { length: 1000, source: 'close' });
  assert.deepEqual(C.clampParams('ema', { length: '12.6' }), { length: 13, source: 'close' });
  assert.deepEqual(C.clampParams('ema', { length: 'abc' }), { length: 20, source: 'close' });
  assert.deepEqual(C.clampParams('ema', {}), { length: 20, source: 'close' });
  assert.deepEqual(C.clampParams('ema', { length: 20, source: 'hl2' }), { length: 20, source: 'hl2' });
  assert.deepEqual(C.clampParams('ema', { length: 20, source: 'bogus' }), { length: 20, source: 'close' });
  assert.deepEqual(C.clampParams('sma', { length: 20, source: 'ohlc4' }), { length: 20, source: 'ohlc4' });
  assert.deepEqual(C.clampParams('vwma', { length: 9 }), { length: 9 });   // no Source param for VWMA
  assert.deepEqual(C.clampParams('footprint', { imbalance: 2.5 }), { imbalance: 2.5 });
  assert.deepEqual(C.clampParams('footprint', { imbalance: -1 }), { imbalance: 0 });
  assert.deepEqual(C.clampParams('bigprints', { min: 0 }), { min: 1 });
  assert.deepEqual(C.clampParams('bigorders', {}), { multiple: 5 });
  assert.deepEqual(C.clampParams('bigorders', { multiple: 0 }), { multiple: 1 });
  assert.deepEqual(C.clampParams('bigorders', { multiple: 999 }), { multiple: 50 });
  assert.deepEqual(C.clampParams('imbalance', { junk: 1 }), {});
  assert.deepEqual(C.clampParams('heatmap', { junk: 1 }), {});
  assert.deepEqual(C.clampParams('vwap', { anchor: 'xyz', customTime: 'nope' }), VWAP_DEFAULT_PARAMS);
  assert.deepEqual(C.clampParams('vwap', { anchor: 'rth', junk: 1 }), { ...VWAP_DEFAULT_PARAMS, anchor: 'rth' });
  // "9:30" is loose keyboard entry, not an error: it normalises to "09:30" like the other shorthands do
  assert.deepEqual(C.clampParams('vwap', { anchor: 'custom', customTime: '9:30' }),
    { ...VWAP_DEFAULT_PARAMS, anchor: 'custom', customTime: '09:30' });
  assert.deepEqual(C.clampParams('vwap', { anchor: 'custom', customTime: '09:30' }),
    { ...VWAP_DEFAULT_PARAMS, anchor: 'custom', customTime: '09:30' });
  assert.deepEqual(C.clampParams('vwap', { anchor: 'custom', customTime: 'lunchtime' }),
    { ...VWAP_DEFAULT_PARAMS, anchor: 'custom' });   // genuinely unparseable: falls back to the factory default
  assert.deepEqual(C.clampParams('vwap', { anchor: 'week', band1On: true, band1Mult: 1.5 }),
    { ...VWAP_DEFAULT_PARAMS, anchor: 'week', band1On: true, band1Mult: 1.5 });
  assert.deepEqual(C.clampParams('vwap', { band1Mult: 99 }), { ...VWAP_DEFAULT_PARAMS, band1Mult: 10 });   // clamped to max
  assert.deepEqual(C.clampParams('volume', { any: 1 }), {});
});

test('a Build-1 chart (st form) migrates field by field', () => {
  const st = { vwap: true, vwapAnchor: 'rth', vwapBands: true, ema1: 9, ema2: 21, sma: 50, vwma: 20, levels: true,
    volume: true, delta: true, cumdelta: true, adx: 14, footprint: true, imbalance: 4, profile: true, bigMin: 30 };
  const m = C.migrate({ root: 'es', spec: 'tick:1000', st });
  assert.equal(m.root, 'ES');
  assert.equal(m.spec, 'tick:1000');
  assert.deepEqual(strip(m.indicators), [
    { id: 'vwap', params: { ...VWAP_DEFAULT_PARAMS, anchor: 'rth', band1On: true, band2On: true }, visible: true },
    { id: 'ema', params: { length: 9, source: 'close' }, visible: true },
    { id: 'ema', params: { length: 21, source: 'close' }, visible: true },
    { id: 'sma', params: { length: 50, source: 'close' }, visible: true },
    { id: 'vwma', params: { length: 20 }, visible: true },
    { id: 'levels', params: {}, visible: true },
    { id: 'volume', params: {}, visible: true },
    { id: 'delta', params: {}, visible: true },
    { id: 'cumdelta', params: {}, visible: true },
    { id: 'adx', params: { length: 14 }, visible: true },
    { id: 'footprint', params: { imbalance: 4 }, visible: true },
    { id: 'profile', params: {}, visible: true },
    { id: 'bigprints', params: { min: 30 }, visible: true }]);
});

test('an empty Build-1 st means the Build-1 defaults', () => {
  const m = C.migrate({ root: 'NQ', spec: 'time:60', st: {} });
  assert.deepEqual(m.indicators.map((x) => x.id), ['vwap', 'levels', 'volume', 'footprint']);
});

test('switched-off Build-1 studies are dropped', () => {
  const m = C.migrate({ root: 'NQ', spec: 'time:60', st: { vwap: false, levels: false, volume: false, footprint: false } });
  assert.deepEqual(m.indicators, []);
});

test('new-form configs are sanitised: unknown ids dropped, params clamped, uid and visible kept', () => {
  const m = C.migrate({ root: 'NQ', spec: 'time:300', indicators: [
    { uid: 'keep', id: 'ema', params: { length: 0 }, visible: false }, { uid: 'x', id: 'nope' }, null] });
  assert.deepEqual(m.indicators, [{ uid: 'keep', id: 'ema', params: { length: 1, source: 'close' }, visible: false }]);
  const fresh = C.migrate({ root: 'NQ', spec: 'time:60', indicators: [{ id: 'sma' }] }).indicators[0];
  assert.ok(fresh.uid);
  assert.equal(fresh.visible, true);
});

test('a pre-rework indicators-array vwap ({anchor, bands}) migrates bands into band 1 (x1) + band 2 (x2), not lost', () => {
  const on = C.migrate({ root: 'NQ', spec: 'time:60',
    indicators: [{ uid: 'v', id: 'vwap', params: { anchor: 'rth', bands: true }, visible: true }] }).indicators[0];
  assert.deepEqual(on.params, { ...VWAP_DEFAULT_PARAMS, anchor: 'rth', band1On: true, band2On: true });

  const off = C.migrate({ root: 'NQ', spec: 'time:60',
    indicators: [{ uid: 'v', id: 'vwap', params: { anchor: 'eth', bands: false }, visible: true }] }).indicators[0];
  assert.deepEqual(off.params, VWAP_DEFAULT_PARAMS);

  // a params object that never had `bands` (today's shape, or one with no bands key at all) passes through
  const plain = C.migrate({ root: 'NQ', spec: 'time:60',
    indicators: [{ uid: 'v', id: 'vwap', params: { anchor: 'week' }, visible: true }] }).indicators[0];
  assert.deepEqual(plain.params, { ...VWAP_DEFAULT_PARAMS, anchor: 'week' });
});

test('garbage configs become a default NQ 1m chart', () => {
  const m = C.migrate(null);
  assert.equal(m.root, 'NQ');
  assert.equal(m.spec, 'time:60');
  assert.equal(m.indicators.length, 4);
});

test('layouts migrate every cell and keep only known grids', () => {
  const l = C.migrateLayout({ grid: 3, cells: [{ root: 'NQ', spec: 'time:60', st: {} }] });
  assert.equal(l.grid, 4);
  assert.equal(l.cells.length, 1);
  assert.equal(l.cells[0].indicators[0].id, 'vwap');
  assert.equal(C.migrateLayout({ grid: 6, cells: [] }).grid, 6);
  assert.deepEqual(C.migrateLayout(undefined), { grid: 4, sizes: null, cells: [] });
});

test('legend labels', () => {
  assert.equal(C.label(C.instance('ema', { length: 20 })), 'EMA 20');
  assert.equal(C.label(C.instance('sma')), 'SMA 50');
  assert.equal(C.label(C.instance('vwap')), 'VWAP');
  assert.equal(C.label(C.instance('vwap', { anchor: 'rth' })), 'VWAP RTH');
  assert.equal(C.label(C.instance('vwap', { anchor: 'week' })), 'VWAP W');
  assert.equal(C.label(C.instance('vwap', { anchor: 'month' })), 'VWAP M');
  assert.equal(C.label(C.instance('vwap', { anchor: 'custom', customTime: '02:00' })), 'VWAP 02:00');
  assert.equal(C.label(C.instance('vwap', { anchor: 'custom', customTime: '16:00' })), 'VWAP 16:00');
  assert.equal(C.label(C.instance('ema', { length: 20, source: 'hl2' })), 'EMA 20 HL2');
  assert.equal(C.label(C.instance('sma', { length: 50 })), 'SMA 50');   // default source (close): no suffix
  assert.equal(C.label(C.instance('adx')), 'ADX 14');
  assert.equal(C.label(C.instance('footprint')), 'Footprint 3×');
  assert.equal(C.label(C.instance('footprint', { imbalance: 0 })), 'Footprint');
  assert.equal(C.label(C.instance('bigprints')), 'Big prints ≥25');
  assert.equal(C.label(C.instance('bigorders')), 'Big orders 5×');
  assert.equal(C.label(C.instance('imbalance')), 'Imbalance');
  assert.equal(C.label(C.instance('heatmap')), 'Liquidity heatmap');
  assert.equal(C.label(C.instance('cumdelta')), 'Cumulative delta');
  assert.equal(C.label(C.instance('levels')), 'Session levels');
});

test('legend values per indicator', () => {
  const colors = { line: '#2962FF', text: '#0F0F0F', up: '#089981', down: '#F23645', vwap: '#9C27B0', cum: '#FF6D00' };
  const bar = { sv: { 'ema:20': 30900.5, vwap: { vwap: 30901.25, sd: 3 }, 'adx:14': { adx: 25.123, pdi: 30, mdi: null }, cumdelta: -1500 } };
  assert.deepEqual(C.legendValues(C.instance('ema'), bar, colors, 0.25), [{ text: '30,900.50', color: '#2962FF' }]);
  assert.deepEqual(C.legendValues(C.instance('vwap'), bar, colors, 0.25), [{ text: '30,901.25', color: '#9C27B0' }]);
  assert.deepEqual(C.legendValues(C.instance('adx'), bar, colors, 0.25),
    [{ text: '25.12', color: '#0F0F0F' }, { text: '30.00', color: '#089981' }, { text: '—', color: '#F23645' }]);
  assert.deepEqual(C.legendValues(C.instance('cumdelta'), bar, colors, 0.25), [{ text: '-1.50K', color: '#FF6D00' }]);
  assert.deepEqual(C.legendValues(C.instance('sma'), bar, colors, 0.25), [{ text: '—', color: '#2962FF' }]);
  for (const id of ['volume', 'delta', 'levels', 'footprint', 'profile', 'bigprints', 'bigorders', 'imbalance', 'heatmap']) {
    assert.deepEqual(C.legendValues(C.instance(id), bar, colors, 0.25), [], id);
  }
});

test('normalizeHHMM: loose keyboard entry (H:MM/HH:MM/HMM/HHMM) zero-pads to the canonical HH:MM, or null', () => {
  assert.equal(C.normalizeHHMM('9:30'), '09:30');
  assert.equal(C.normalizeHHMM('09:30'), '09:30');
  assert.equal(C.normalizeHHMM('930'), '09:30');
  assert.equal(C.normalizeHHMM('0930'), '09:30');
  assert.equal(C.normalizeHHMM(' 9:30 '), '09:30');
  assert.equal(C.normalizeHHMM('0:00'), '00:00');
  assert.equal(C.normalizeHHMM('23:59'), '23:59');
  assert.equal(C.normalizeHHMM('2359'), '23:59');
  assert.equal(C.normalizeHHMM('000'), '00:00');    // HMM, 1-digit hour
  assert.equal(C.normalizeHHMM('24:00'), null);      // HH out of range
  assert.equal(C.normalizeHHMM('12:60'), null);      // MM out of range
  assert.equal(C.normalizeHHMM('2400'), null);
  assert.equal(C.normalizeHHMM('99'), null);         // too short for HMM/HHMM
  assert.equal(C.normalizeHHMM('lunchtime'), null);
  assert.equal(C.normalizeHHMM(''), null);
  assert.equal(C.normalizeHHMM(null), null);
});

// ---- per-instance style (Task 3): styleLineKeys / defaultStyle / clampStyle / cycleColor ----
test('styleLineKeys: a Style tab per plotted line for the drawn indicators, none for canvas/fixed-colour ones', () => {
  assert.deepEqual(C.styleLineKeys('vwap'), ['main', 'band1', 'band2', 'band3']);
  assert.deepEqual(C.styleLineKeys('adx'), ['adx', 'pdi', 'mdi']);
  assert.deepEqual(C.styleLineKeys('ema'), ['main']);
  assert.deepEqual(C.styleLineKeys('sma'), ['main']);
  assert.deepEqual(C.styleLineKeys('vwma'), ['main']);
  assert.deepEqual(C.styleLineKeys('cumdelta'), ['main']);
  for (const id of ['delta', 'levels', 'footprint', 'profile', 'bigprints', 'bigorders', 'imbalance', 'heatmap', 'volume']) {
    assert.equal(C.styleLineKeys(id), null, id);
  }
  assert.equal(C.styleLineKeys('nope'), null);
});

test('cycleColor: the first instance keeps its traditional colour, later ones advance and never repeat it', () => {
  assert.equal(C.cycleColor('vwap', []), '#9C27B0');
  assert.equal(C.cycleColor('vwap', [{ id: 'vwap' }]), C.LINE_COLORS[0]);
  assert.equal(C.cycleColor('vwap', [{ id: 'vwap' }, { id: 'vwap' }]), C.LINE_COLORS.filter((c) => c !== '#9C27B0')[1]);
  assert.notEqual(C.cycleColor('vwap', [{ id: 'vwap' }]), '#9C27B0');
  assert.equal(C.cycleColor('ema', []), C.LINE_COLORS[0]);
  assert.equal(C.cycleColor('ema', [{ id: 'ema' }]), C.LINE_COLORS[1]);
  assert.equal(C.cycleColor('ema', [{ id: 'vwap' }]), C.LINE_COLORS[0]);   // only same-id siblings count
  assert.equal(C.cycleColor('cumdelta', []), '#FF6D00');
});

test('defaultStyle: one entry per Style-tab line, width/dash/visible sane, null when there is no Style tab', () => {
  const vs = C.defaultStyle('vwap', []);
  assert.deepEqual(Object.keys(vs).sort(), ['band1', 'band2', 'band3', 'main']);
  assert.equal(vs.main.color, '#9C27B0');
  assert.equal(vs.main.width, 2);
  assert.equal(vs.main.dash, 'solid');
  assert.equal(vs.band1.dash, 'dashed');
  for (const k of ['main', 'band1', 'band2', 'band3']) assert.equal(vs[k].visible, true);
  const second = C.defaultStyle('vwap', [{ id: 'vwap' }]);
  assert.notEqual(second.main.color, vs.main.color);
  const adx = C.defaultStyle('adx', []);
  assert.equal(adx.pdi.color, '#089981');
  assert.equal(adx.mdi.color, '#F23645');
  assert.equal(C.defaultStyle('levels', []), null);
  assert.equal(C.defaultStyle('nope', []), null);
});

test('clampStyle: malformed or missing fields fall back per line, and a style-less indicator clamps to null', () => {
  const bad = C.clampStyle('ema', { main: { color: 'not-a-colour', width: 99, dash: 'zigzag', visible: 'yes' } });
  assert.equal(bad.main.color, C.defaultStyle('ema', []).main.color);
  assert.equal(bad.main.width, 1);
  assert.equal(bad.main.dash, 'solid');
  assert.equal(bad.main.visible, true);
  const good = C.clampStyle('ema', { main: { color: '#123456', width: 3, dash: 'dotted', visible: false } });
  assert.deepEqual(good, { main: { color: '#123456', width: 3, dash: 'dotted', visible: false } });
  assert.equal(C.clampStyle('ema', null), null);
  assert.equal(C.clampStyle('levels', { main: {} }), null);   // no Style tab at all
});

test('sanitizePreset: a loaded preset payload runs through clampParams/clampStyle -- junk can never reach a chart', () => {
  const clean = C.sanitizePreset('ema', { params: { length: 9, source: 'hl2' }, style: { main: { color: '#123456', width: 3, dash: 'dotted', visible: false } } });
  assert.deepEqual(clean.params, { length: 9, source: 'hl2' });
  assert.deepEqual(clean.style, { main: { color: '#123456', width: 3, dash: 'dotted', visible: false } });

  // malformed params/style fall back per-field, not the whole payload
  const bad = C.sanitizePreset('ema', { params: { length: 'nope', source: 'bogus' }, style: { main: { color: 'not-a-colour', width: 99, dash: 'zigzag' } } });
  assert.deepEqual(bad.params, { length: 20, source: 'close' });
  assert.equal(bad.style.main.color, C.defaultStyle('ema', []).main.color);
  assert.equal(bad.style.main.width, 1);

  // missing/non-object payload, or a payload for an indicator with no Style tab: never throws
  assert.deepEqual(C.sanitizePreset('ema', {}), { params: { length: 20, source: 'close' }, style: C.defaultStyle('ema', []) });
  assert.deepEqual(C.sanitizePreset('ema', null), { params: { length: 20, source: 'close' }, style: C.defaultStyle('ema', []) });
  assert.deepEqual(C.sanitizePreset('levels', { params: { junk: 1 }, style: { main: {} } }), { params: {}, style: null });

  // an indicator with a Style tab but no saved style at all -- fresh defaultStyle, not null
  assert.deepEqual(C.sanitizePreset('ema', { params: {} }).style, C.defaultStyle('ema', []));
});

test('a new instance of an indicator already on the chart does not repeat its colour (Task 2)', () => {
  const chart = [C.instance('vwap')];
  chart[0].style = C.defaultStyle('vwap', []);
  const second = C.instance('vwap');
  second.style = C.defaultStyle('vwap', chart);
  assert.notEqual(second.style.main.color, chart[0].style.main.color);
});

test('migrate carries a persisted style over (clamped); an instance with none keeps rendering unstyled', () => {
  const m = C.migrate({ root: 'NQ', spec: 'time:60', indicators: [
    { uid: 'a', id: 'ema', params: { length: 9 }, style: { main: { color: '#ABCDEF', width: 3, dash: 'dotted', visible: false } } },
    { uid: 'b', id: 'ema', params: { length: 9 } },
    { uid: 'c', id: 'levels', params: {}, style: { main: { color: '#ABCDEF' } } }] });
  assert.deepEqual(m.indicators[0].style, { main: { color: '#ABCDEF', width: 3, dash: 'dotted', visible: false } });
  assert.equal('style' in m.indicators[1], false);
  assert.equal('style' in m.indicators[2], false);   // levels has no Style tab: a stray style is dropped
});

test('prices use the tick size decimals with thousands separators', () => {
  assert.equal(C.decimals(0.25), 2);
  assert.equal(C.decimals(0.1), 1);
  assert.equal(C.decimals(0.005), 3);
  assert.equal(C.decimals(1), 0);
  assert.equal(C.decimals(0.015625), 6);
  assert.equal(C.fmtPrice(30919.25, 0.25), '30,919.25');
  assert.equal(C.fmtPrice(2650.3, 0.1), '2,650.3');
  assert.equal(C.fmtPrice(null, 0.25), '—');
  assert.equal(C.fmtPrice(NaN, 0.25), '—');
});

test('volumes are compact and deltas signed', () => {
  assert.equal(C.fmtCompact(950), '950');
  assert.equal(C.fmtCompact(1234), '1.23K');
  assert.equal(C.fmtCompact(4560000), '4.56M');
  assert.equal(C.fmtCompact(-12346), '-12.35K');
  assert.equal(C.fmtCompact(999994), '999.99K');
  assert.equal(C.fmtCompact(999995), '1.00M');
  assert.equal(C.fmtSigned(62), '+62');
  assert.equal(C.fmtSigned(-62), '-62');
  assert.equal(C.fmtSigned(0), '0');
  assert.equal(C.fmtSigned(null), '—');
});

test('change is against the previous close, else the open', () => {
  assert.deepEqual(C.change({ o: 30918, c: 30919.25 }, { c: 30916.5 }, 0.25), { up: true, text: '+2.75 (+0.01%)' });
  assert.deepEqual(C.change({ o: 100, c: 99 }, null, 0.25), { up: false, text: '-1.00 (-1.00%)' });
  assert.deepEqual(C.change({ o: 100, c: 100 }, { c: 100 }, 0.25), { up: true, text: '0.00 (0.00%)' });
});

test('interval labels', () => {
  assert.equal(C.specLabel('time:60'), '1m');
  assert.equal(C.specLabel('time:14400'), '4h');
  assert.equal(C.specLabel('time:86400'), '1D');
  assert.equal(C.specLabel('time:90'), '90s');
  assert.equal(C.specLabel('tick:1000'), '1000T');
  assert.equal(C.specLabel('volume:2000'), '2000V');
  assert.equal(C.specLabel('range:10'), '10R');
  assert.equal(C.specLabel('weird'), 'weird');
  assert.equal(C.longLabel('time:5'), '5 seconds');
  assert.equal(C.longLabel('time:60'), '1 minute');
  assert.equal(C.longLabel('time:14400'), '4 hours');
  assert.equal(C.longLabel('time:86400'), '1 day');
  assert.equal(C.longLabel('tick:500'), '500 ticks');
  assert.equal(C.longLabel('volume:2000'), '2,000 volume');
  assert.equal(C.longLabel('range:10'), '10 range');
});

test('the interval menus only offer the server timeframes', () => {
  const all = C.INTERVAL_GROUPS.flatMap(([, specs]) => specs);
  assert.deepEqual(all, ['time:5', 'time:15', 'time:30', 'time:60', 'time:120', 'time:180', 'time:300', 'time:600',
    'time:900', 'time:1800', 'time:3600', 'time:14400', 'time:86400', 'tick:500', 'tick:1000', 'volume:2000', 'range:10', 'range:20']);
  assert.deepEqual(C.FAVOURITES, [['1m', 'time:60'], ['5m', 'time:300'], ['15m', 'time:900'], ['1h', 'time:3600'], ['4h', 'time:14400'], ['D', 'time:86400']]);
});

test('custom interval text becomes a bar spec', () => {
  for (const [t, s] of [['45s', 'time:45'], ['2m', 'time:120'], ['4h', 'time:14400'], ['1D', 'time:86400'], ['750T', 'tick:750'],
    ['3000v', 'volume:3000'], ['8R', 'range:8'], ['tick:750', 'tick:750'], [' TIME:30 ', 'time:30']]) {
    assert.equal(C.toSpec(t), s, t);
  }
  for (const t of ['', 'abc', '0m', 'time:0', '5x', 'tick:', '1.5m', null]) assert.equal(C.toSpec(t), null, String(t));
});

test('root names', () => {
  assert.equal(C.rootName('NQ'), 'E-mini Nasdaq-100');
  assert.equal(C.rootName('SI'), 'Silver');
  assert.equal(C.rootName('HG'), '');            // cut from the app 2026-10-07
  assert.equal(C.rootName('ZZ'), '');
});

test('market hours: Globex Sunday 18:00 to Friday 17:00 with a daily break; crypto never closes', () => {
  const at = (h, m = 0) => h * 60 + m;
  assert.equal(C.marketOpen('NQ', 6, at(12)), false);        // Saturday
  assert.equal(C.marketOpen('NQ', 0, at(17, 59)), false);    // Sunday before the open
  assert.equal(C.marketOpen('NQ', 0, at(18)), true);
  assert.equal(C.marketOpen('NQ', 3, at(17, 30)), false);    // the daily break
  assert.equal(C.marketOpen('NQ', 3, at(9, 30)), true);
  assert.equal(C.marketOpen('NQ', 5, at(16, 59)), true);
  assert.equal(C.marketOpen('NQ', 5, at(17)), false);        // Friday close
  for (const [wd, t] of [[6, at(12)], [0, at(10)], [3, at(17, 30)], [5, at(20)]]) {
    assert.equal(C.marketOpen('BTC', wd, t), true);
  }
});

test('dialog filtering by name and group', () => {
  assert.deepEqual(C.filter('', 'Moving averages').map((d) => d.id), ['ema', 'sma', 'vwma', 'tema']);
  assert.deepEqual(C.filter('delta').map((d) => d.id), ['delta', 'cumdelta']);
  assert.deepEqual(C.filter('ORDER').map((d) => d.id), ['footprint', 'profile', 'delta', 'cumdelta', 'bigprints', 'bigorders', 'imbalance', 'heatmap']);
  assert.deepEqual(C.filter('heat').map((d) => [d.id, d.group]), [['heatmap', 'Order flow']]);
  assert.deepEqual(C.filter('zzz'), []);
  assert.equal(C.filter('').length, C.CATALOG.length);
  assert.deepEqual(C.GROUPS, ['All', 'VWAP', 'Moving averages', 'Trend', 'Momentum', 'Volatility', 'Structure', 'Ranges', 'Levels', 'Volume', 'Order flow']);
});

test('a saved spec is normalised on migration (a Build-1 tick:0750 is tick:750)', () => {
  assert.equal(C.migrate({ root: 'NQ', spec: 'tick:0750', st: {} }).spec, 'tick:750');
  assert.equal(C.migrate({ root: 'NQ', spec: ' TIME:300 ', indicators: [] }).spec, 'time:300');
  assert.equal(C.migrate({ root: 'NQ', spec: 'bogus', indicators: [] }).spec, 'time:60');
  assert.equal(C.migrate({ root: 'NQ', spec: 'time:0', indicators: [] }).spec, 'time:60');
  assert.equal(C.migrateLayout({ grid: 1, cells: [{ root: 'NQ', spec: 'range:08' }] }).cells[0].spec, 'range:8');
});

test('ages read as s / m / h / d', () => {
  assert.equal(C.fmtAge(null), '—');
  assert.equal(C.fmtAge(undefined), '—');
  assert.equal(C.fmtAge(5), '5.0s');
  assert.equal(C.fmtAge(59.94), '59.9s');
  assert.equal(C.fmtAge(90), '2m');
  assert.equal(C.fmtAge(7200), '2h');
  assert.equal(C.fmtAge(200000), '2d');
});

/* feedSummary(status, ET weekday, ET minute of the day) — the bottom bar's dot, text and tooltip. */
const SAT_NOON = [6, 12 * 60], WED_10 = [3, 10 * 60];
const WED_2 = [3, 2 * 60], TUE_3 = [2, 3 * 60];
const SUN_1803 = [0, 18 * 60 + 3], TUE_1803 = [2, 18 * 60 + 3];
const FRI_1659 = [5, 16 * 60 + 59], WED_1730 = [3, 17 * 60 + 30];
const live = (roots, extra = {}) => ({ mode: 'live', connected: true, error: null, roots,
  recorder: { written: 0, buffered: 0, error: null }, ...extra });
const tick = (age) => ({ contract: 'X', last_tick_age_s: age, error: null });

test('status: a weekend with Bitcoin fresh and the Globex futures closed is fine', () => {
  const f = C.feedSummary(live({ BTC: tick(2), NQ: tick(180000) }), ...SAT_NOON);
  assert.deepEqual(f, { dot: 'ok', text: 'feeds ok', textClass: '', title: 'BTC 2.0s  ·  NQ closed' });
});

test('status: a stale open market is amber, the stalest first, two at most', () => {
  const f = C.feedSummary(live({ NQ: tick(180), ES: tick(2), YM: tick(360), RTY: tick(124) }), ...WED_10);
  assert.equal(f.dot, 'warn');
  assert.equal(f.text, 'YM stale 6m · NQ stale 3m');
  assert.equal(f.textClass, 'warn');
  assert.equal(f.title, 'NQ 3m  ·  ES 2.0s  ·  YM 6m  ·  RTY 2m');
});

test('status: a refused symbol reads "unavailable" in amber, whatever the market hours, with the reason in the tooltip', () => {
  const s = live({ BTC: { contract: null, last_tick_age_s: null, error: 'BTCV6: getChart refused: None' }, NQ: tick(1) });
  for (const at of [WED_10, SAT_NOON]) {
    const f = C.feedSummary(s, ...at);
    assert.equal(f.dot, 'warn');
    assert.equal(f.text, 'BTC unavailable');
    assert.equal(f.textClass, 'warn');
    assert.ok(f.title.startsWith('BTC unavailable: BTCV6: getChart refused: None  ·  NQ '), f.title);
  }
});

test('status: an open market that has not ticked yet is not "feeds ok" — neutral text, grey dot', () => {
  const sat = C.feedSummary(live({ BTC: tick(null), NQ: tick(null) }), ...SAT_NOON);
  assert.deepEqual(sat, { dot: '', text: 'BTC no ticks yet', textClass: '', title: 'BTC no ticks yet  ·  NQ closed' });
  const wed = C.feedSummary(live({ NQ: tick(null), ES: tick(null), YM: tick(null), BTC: tick(1) }), ...WED_10);
  assert.equal(wed.text, 'NQ no ticks yet · ES no ticks yet');
  assert.equal(wed.dot, '');
  assert.equal(wed.textClass, '');
  const mixed = C.feedSummary(live({ NQ: tick(150), BTC: tick(null) }), ...WED_10);   // a warning wins the dot and the colour
  assert.deepEqual([mixed.dot, mixed.text, mixed.textClass], ['warn', 'NQ stale 3m · BTC no ticks yet', 'warn']);
});

/* The data's own state on the strip: how late the feed runs (the service measures it at every print) and whether
   it is thin (the tick job's data watchdog, `data` in the status message). */
const late = (age, late_s) => ({ ...tick(age), late_s });
const watch = (more = {}) => ({ at_utc: '2026-10-06T13:55:00+00:00', age_s: 300, stale: false, level: 'warn',
  line: 'data: thin: NQ got 16% of its ticks 08:00-09:00 ET (15 markets thin)', late: [], thin: ['NQ', 'ES'], silent: [],
  refused: 0, leaving: 0, ...more });

test('status: a feed ten minutes late says so in amber -- ticks flowing is not "feeds ok"', () => {
  const f = C.feedSummary(live({ NQ: late(1, 600), ES: late(2, 601.2), YM: late(1, 600) }), ...WED_10);
  assert.deepEqual([f.dot, f.text, f.textClass], ['warn', 'late 10 min', 'warn']);
  assert.equal(f.title, 'NQ 1.0s, 10m late  ·  ES 2.0s, 10m late  ·  YM 1.0s, 10m late');
  // on time (a fraction of a second behind): as it always read
  assert.deepEqual(C.feedSummary(live({ NQ: late(1, 0.3), ES: late(2, 0) }), ...WED_10),
    { dot: 'ok', text: 'feeds ok', textClass: '', title: 'NQ 1.0s  ·  ES 2.0s' });
});

test('status: lateness is the feed\'s -- the median of the open markets, a closed one\'s old print says nothing', () => {
  const odd = C.feedSummary(live({ NQ: late(1, 0.2), ES: late(1, 0.4), HG: late(40, 95) }), ...WED_10);
  assert.equal(odd.text, 'HG late 2 min');                       // one market behind: named, the feed is not late
  const sat = C.feedSummary(live({ NQ: late(180000, 600), BTC: late(2, 0.5) }), ...SAT_NOON);   // Friday's last print
  assert.deepEqual([sat.dot, sat.text], ['ok', 'feeds ok']);
});

test('status: a thin feed (the watchdog\'s reading) says so; late and thin together read as both', () => {
  const thin = C.feedSummary(live({ NQ: late(1, 0.3) }, { data: watch() }), ...WED_10);
  assert.deepEqual([thin.dot, thin.text, thin.textClass], ['warn', 'thin feed', 'warn']);
  assert.equal(thin.title, 'NQ 1.0s  —  data watch, 5m ago: thin: NQ got 16% of its ticks 08:00-09:00 ET (15 markets thin)');
  const both = C.feedSummary(live({ NQ: late(1, 600) }, { data: watch() }), ...WED_10);
  assert.equal(both.text, 'late 10 min · thin feed');
  const stale = C.feedSummary(live({ NQ: late(150, 600) }, { data: watch() }), ...WED_10);
  assert.equal(stale.text, 'NQ stale 3m · late 10 min · thin feed');   // a stalled market still comes first
});

test('status: a watchdog reading that is fine adds only its tooltip; one too old is not used, and says so', () => {
  const fine = C.feedSummary(live({ NQ: late(1, 0.3) }, { data: watch({ level: 'fine', line: 'data: fine', thin: [] }) }), ...WED_10);
  assert.deepEqual([fine.dot, fine.text, fine.textClass], ['ok', 'feeds ok', '']);
  assert.equal(fine.title, 'NQ 1.0s  —  data watch, 5m ago: fine');
  const old = C.feedSummary(live({ NQ: late(1, 0.3) }, { data: watch({ age_s: 4 * 3600, stale: true }) }), ...WED_10);
  assert.deepEqual([old.dot, old.text], ['ok', 'feeds ok']);
  assert.equal(old.title, 'NQ 1.0s  —  data watch: not checked for 4h');
  assert.equal(C.feedSummary(live({ NQ: late(1, 0.3) }, { data: null }), ...WED_10).title, 'NQ 1.0s');
});

test('status: not connected reads "connecting…", never "feeds ok"', () => {
  const f = C.feedSummary(live({ NQ: tick(1) }, { connected: false }), ...WED_10);
  assert.deepEqual([f.dot, f.text, f.textClass], ['bad', 'connecting…', '']);
});

test('status: an error is red and says what failed', () => {
  const f = C.feedSummary({ connected: false, error: 'chart service unreachable — retrying' }, ...WED_10);
  assert.deepEqual(f, { dot: 'bad', text: 'chart service unreachable — retrying', textClass: 'bad', title: '' });
  const feed = C.feedSummary(live({ NQ: tick(1) }, { error: 'Refused: every symbol refused' }), ...WED_10);
  assert.deepEqual([feed.dot, feed.text, feed.textClass], ['bad', 'Refused: every symbol refused', 'bad']);
  const rec = C.feedSummary(live({ NQ: tick(1) }, { recorder: { written: 0, buffered: 0, error: 'disk full' } }), ...WED_10);
  assert.deepEqual([rec.dot, rec.text, rec.textClass], ['bad', 'recorder: disk full', 'bad']);
});

test('status: a backed-up recorder turns the dot amber and leaves the feed text alone', () => {
  const f = C.feedSummary(live({ NQ: tick(1) }, { recorder: { written: 0, buffered: C.REC_BUSY, error: null } }), ...WED_10);
  assert.deepEqual([f.dot, f.text, f.textClass], ['warn', 'feeds ok', '']);
  assert.equal(C.feedSummary(live({}), ...WED_10).text, '');
});

test('status: RTH is tighter than ETH for a classic root', () => {
  assert.equal(C.feedSummary(live({ NQ: tick(150) }), ...WED_10).text, 'NQ stale 3m');
  assert.equal(C.feedSummary(live({ NQ: tick(100) }), ...WED_10).text, 'feeds ok');
});

test('status: ETH is looser than RTH for a classic root', () => {
  assert.equal(C.feedSummary(live({ ZN: tick(200) }), ...WED_2).text, 'feeds ok');
  assert.equal(C.feedSummary(live({ ZN: tick(400) }), ...WED_2).text, 'ZN stale 7m');
});

test('status: a 24/7 root does not go stale on a quiet weekend', () => {
  const f = C.feedSummary(live({ BTC: tick(3600) }), ...SAT_NOON);
  assert.equal(f.dot, 'ok');
  assert.equal(f.text, 'feeds ok');
  assert.ok(f.title.includes('BTC 1h'), f.title);
});

test('status: a 24/7 root still goes stale after 900 s while the classic market is open', () => {
  assert.equal(C.feedSummary(live({ BTC: tick(1000) }), ...TUE_3).text, 'BTC stale 17m');
  assert.equal(C.feedSummary(live({ BTC: tick(600) }), ...TUE_3).text, 'feeds ok');
});

test('status: the session-open clamp protects a fresh Sunday reopen', () => {
  const nq = C.feedSummary(live({ NQ: tick(180000) }), ...SUN_1803);     // Friday's last tick
  assert.equal(nq.text, 'feeds ok');    // clamped to 180 s; ETH threshold is 300
  const btc = C.feedSummary(live({ BTC: tick(7200) }), ...SUN_1803);
  assert.equal(btc.text, 'feeds ok');   // clamped to 180 s; the 24/7-while-open threshold is 900
});

test('status: the daily 18:00 reopen clamp applies on a weekday too', () => {
  assert.equal(C.feedSummary(live({ NQ: tick(3780) }), ...TUE_1803).text, 'feeds ok');
});

test('staleAfter: RTH, ETH and 24/7 thresholds', () => {
  assert.equal(C.staleAfter('NQ', ...WED_10), 120);            // RTH
  assert.equal(C.staleAfter('ZN', ...WED_2), 300);             // ETH
  assert.equal(C.staleAfter('NQ', ...FRI_1659), 300);          // ETH, one minute before the Friday close
  assert.equal(C.staleAfter('BTC', ...TUE_3), 900);            // 24/7, classic market open
  assert.equal(C.staleAfter('BTC', ...SAT_NOON), Infinity);    // 24/7, weekend
  assert.equal(C.staleAfter('BTC', ...WED_1730), Infinity);    // 24/7, classic daily break
});

// ---- pane placement (spec §7) ----
test('pane-type indicators carry a placement with today as the default; price-pane-only ones carry none', () => {
  assert.deepEqual(C.PANES, ['main', 'own']);
  assert.equal(C.instance('volume').pane, 'main');
  for (const id of ['delta', 'cumdelta', 'adx']) {
    assert.equal(C.instance(id).pane, 'own', id);
    assert.equal(C.movable(id), true, id);
  }
  assert.equal(C.movable('volume'), true);
  for (const id of ['vwap', 'ema', 'sma', 'vwma', 'levels', 'footprint', 'profile', 'bigprints']) {
    assert.equal('pane' in C.instance(id), false, id);
    assert.equal(C.movable(id), false, id);
  }
  assert.equal(C.movable('nope'), false);
});

test('placement: a valid saved pane, else the default; null for what cannot move', () => {
  assert.equal(C.placement({ id: 'delta' }), 'own');
  assert.equal(C.placement({ id: 'delta', pane: 'main' }), 'main');
  assert.equal(C.placement({ id: 'volume', pane: 'own' }), 'own');
  assert.equal(C.placement({ id: 'cumdelta', pane: 'sideways' }), 'own');
  assert.equal(C.placement({ id: 'ema', pane: 'own' }), null);
  assert.equal(C.placement({ id: 'nope', pane: 'main' }), null);
  assert.equal(C.placement(null), null);
});

test('migrate keeps a saved placement and gives a missing or bad one today\'s', () => {
  const m = C.migrate({ root: 'NQ', spec: 'time:60', indicators: [
    { uid: 'a', id: 'delta', params: {}, visible: true, pane: 'main' },
    { uid: 'b', id: 'cumdelta', params: {} },
    { uid: 'c', id: 'volume', params: {}, pane: 'sideways' },
    { uid: 'd', id: 'adx', params: { length: 14 }, pane: 'own' },
    { uid: 'e', id: 'ema', params: { length: 9 }, pane: 'own' }] });
  assert.deepEqual(m.indicators.map((x) => [x.uid, x.pane]),
    [['a', 'main'], ['b', 'own'], ['c', 'main'], ['d', 'own'], ['e', undefined]]);
  assert.equal('pane' in m.indicators[4], false);
});

test('Build-1 charts migrate with today\'s placement', () => {
  const m = C.migrate({ root: 'NQ', spec: 'time:60', st: { volume: true, delta: true, cumdelta: true, adx: 14 } });
  const by = Object.fromEntries(m.indicators.map((x) => [x.id, x.pane]));
  assert.equal(by.volume, 'main');
  assert.equal(by.delta, 'own');
  assert.equal(by.cumdelta, 'own');
  assert.equal(by.adx, 'own');
  assert.equal(by.vwap, undefined);
});

test('a saved layout round-trips each placement', () => {
  const lay = { grid: 1, cells: [{ root: 'NQ', spec: 'time:60', indicators: [
    { uid: 'a', id: 'delta', params: {}, visible: true, pane: 'main' },
    { uid: 'b', id: 'volume', params: {}, visible: true, pane: 'own' }] }] };
  const back = C.migrateLayout(JSON.parse(JSON.stringify(C.migrateLayout(lay))));
  assert.deepEqual(back.cells[0].indicators.map((x) => x.pane), ['main', 'own']);
});

// ---- instance(id, params, extra) — materialising a stored indicator (chart templates, spec §8) ----
test('instance\'s optional third argument carries visible/pane from a stored indicator, with a fresh uid', () => {
  const a = C.instance('delta', {}, { visible: false, pane: 'main' });
  const b = C.instance('delta', {}, { visible: false, pane: 'main' });
  assert.notEqual(a.uid, b.uid);
  assert.equal(a.visible, false);
  assert.equal(a.pane, 'main');
  assert.equal(C.instance('delta', {}, { pane: 'sideways' }).pane, 'own');   // a bad pane: today's default
  assert.equal(C.instance('ema', {}, { visible: false, pane: 'own' }).visible, false);
  assert.equal('pane' in C.instance('ema', {}, { pane: 'own' }), false);     // never movable: no pane, whatever extra says
  assert.equal(C.instance('volume').visible, true);                          // no extra: today's default (visible)
});

// ---- rootBadge(root) — the instrument badge (Task 1: legend + symbol search) ----
test('every ROOT_NAMES key has its own badge', () => {
  for (const root of Object.keys(C.ROOT_NAMES)) {
    const b = C.rootBadge(root);
    assert.ok(b && b.bg && b.fg, `${root} has no badge`);
    assert.ok(b.text || b.icon, `${root} badge has neither text nor icon`);
  }
  assert.deepEqual(C.rootBadge('NQ'), { text: '100', bg: '#0b1f4d', fg: '#fff' });
  assert.deepEqual(C.rootBadge('GC'), { text: 'Au', bg: '#c9a227', fg: '#1b1b1b' });
  assert.deepEqual(C.rootBadge('SI'), { text: 'Ag', bg: '#9ea7ad', fg: '#1b1b1b' });
});

test('an unknown root falls back to its own first two letters', () => {
  assert.deepEqual(C.rootBadge('ZZ'), { text: 'ZZ', bg: '#5d6b7a', fg: '#fff' });
});

test('a micro root (M prefix) uses its parent\'s badge', () => {
  assert.deepEqual(C.rootBadge('MNQ'), C.rootBadge('NQ'));
  assert.deepEqual(C.rootBadge('MES'), C.rootBadge('ES'));
  assert.deepEqual(C.rootBadge('MGC'), C.rootBadge('GC'));
});

// ---- parseInterval(text) — the timeframe-hotkey box (Task 1) ----
test('parseInterval: every accepted form', () => {
  for (const [t, s] of [
    ['5', 'time:300'], ['1', 'time:60'], ['90', 'time:5400'],       // bare N = N minutes
    ['5s', 'time:5'], ['45S', 'time:45'],                           // Ns = seconds
    ['5m', 'time:300'], ['15M', 'time:900'],                        // Nm = minutes
    ['1h', 'time:3600'], ['4H', 'time:14400'],                      // Nh = hours
    ['d', 'time:86400'], ['D', 'time:86400'], ['1d', 'time:86400'], ['1D', 'time:86400'],   // daily
  ]) assert.equal(C.parseInterval(t), s, t);
});

test('parseInterval: weekly ("w") only if the catalog has it — today it does not', () => {
  assert.equal(C.parseInterval('w'), null);
  assert.equal(C.parseInterval('W'), null);
});

test('parseInterval: invalid or unsupported input returns null', () => {
  for (const t of ['', ' ', 'abc', '0', '0s', '0m', '0h', '2d', '1.5m', '5x', '2w', 'time:60', null, undefined]) {
    assert.equal(C.parseInterval(t), null, String(t));
  }
});

// ---- matchSymbols(query, roots) — the symbol-search hotkey box (Task 1 addition) ----
test('matchSymbols: prefix on root first, then on name', () => {
  const roots = ['NQ', 'ES', 'YM', 'GC'];   // names: E-mini Nasdaq-100, E-mini S&P 500, E-mini Dow, Gold
  assert.deepEqual(C.matchSymbols('N', roots), ['NQ']);
  assert.deepEqual(C.matchSymbols('E', roots), ['ES', 'NQ', 'YM']);   // ES by root, then the two other E-minis by name
  assert.deepEqual(C.matchSymbols('G', roots), ['GC']);               // root match "GC" wins over name match "Gold" once
  assert.deepEqual(C.matchSymbols('n', roots), ['NQ']);                // case-insensitive
});

test('matchSymbols: empty query returns every root, unfiltered', () => {
  assert.deepEqual(C.matchSymbols('', ['NQ', 'ES']), ['NQ', 'ES']);
  assert.deepEqual(C.matchSymbols(null, ['NQ', 'ES']), ['NQ', 'ES']);
});

test('matchSymbols: no match returns an empty list', () => {
  assert.deepEqual(C.matchSymbols('Q', ['NQ', 'ES', 'YM', 'GC']), []);
});

test('starred intervals: parse, sort in menu order, toggle', () => {
  const dflt = C.FAVOURITES.map(([, s]) => s);
  assert.deepEqual(C.parseFavs(null), dflt);
  assert.deepEqual(C.parseFavs('junk'), dflt);
  assert.deepEqual(C.parseFavs('[]'), []);
  assert.deepEqual(C.parseFavs(JSON.stringify(['time:3600', 'time:60', 'bogus', 'time:60', 7])), ['time:60', 'time:3600']);
  assert.deepEqual(C.toggleFav(['time:60', 'time:3600'], 'time:300'), ['time:60', 'time:300', 'time:3600']);
  assert.deepEqual(C.toggleFav(['time:60', 'time:300'], 'time:60'), ['time:300']);
  assert.deepEqual(C.toggleFav(['time:60'], 'time:45'), ['time:60', 'time:45'], 'a custom one goes after the listed ones');
});

/* W1 (2026-09-28): the status bar's fit -- lower-priority segments step out whole, lowest rank first, only while the
   bar does not fit; a segment with no rank (the connection / desk state) never does. */
test('W1: statusDrops -- whole segments step out lowest rank first, only while needed; unranked ones never', () => {
  const seg = (width, drop = null, gap = 12) => ({ width, drop, gap });
  const bar = [seg(8, null, 0), seg(90), seg(50), seg(190), seg(150, 6), seg(160, 3), seg(0), seg(200, 4), seg(70, 5), seg(60, 2), seg(60, 1), seg(14)];
  const need = bar.reduce((s, it, i) => s + it.width + (i ? it.gap : 0), 0);
  assert.deepEqual(C.statusDrops(need, bar), [], 'room for all: nothing steps out');
  assert.deepEqual(C.statusDrops(need - 1, bar), [10], 'one px short: the lowest rank (1) alone');
  assert.deepEqual(C.statusDrops(need - 80, bar), [9, 10], 'then rank 2 -- never more than needed');
  assert.deepEqual(C.statusDrops(need - 300, bar), [5, 9, 10], 'ranks 1, 2, 3 free 316 px: enough, rank 4 stays');
  assert.deepEqual(C.statusDrops(need - 400, bar), [5, 7, 9, 10], 'ranks 1, 2, 3, 4 in that order');
  assert.deepEqual(C.statusDrops(0, bar), [4, 5, 7, 8, 9, 10], 'however narrow: only ranked segments, never the rest');
  assert.deepEqual(C.statusDrops(100, []), []);
  assert.deepEqual(C.statusDrops(100, null), []);
});

/* W5 (2026-09-28): the Indicators dialog shows one plain line under each indicator's name -- so every catalog entry
   needs one: a real sentence of its own (not the name again), one line, short enough for the dialog's list. */
test('W5: every catalog entry has a one-line, plain description of its own', () => {
  assert.ok(C.CATALOG.length >= 15);
  const seen = new Set();
  for (const d of C.CATALOG) {
    assert.equal(typeof d.desc, 'string', `${d.id} has a description`);
    const t = d.desc.trim();
    assert.ok(t.length >= 20 && t.length <= 85, `${d.id}: 20-85 characters (${t.length})`);
    assert.equal(t, d.desc, `${d.id}: no stray spaces`);
    assert.doesNotMatch(t, /\n/, `${d.id}: one line`);
    assert.notEqual(t.toLowerCase(), d.name.toLowerCase(), `${d.id}: more than its name`);
    assert.ok(!seen.has(t), `${d.id}: its own words`);
    seen.add(t);
  }
  // the three the audit named, saying what they draw
  assert.match(C.def('bigorders').desc, /median size/);
  assert.match(C.def('imbalance').desc, /top 10/);
  assert.match(C.def('bigprints').desc, /sellers hit the bid/);
});

/* 2026-10-09 chart upgrade: dividers between charts, and the crosshair shared across charts. */
test('layout sizes: kept only when they fit the grid, mean 1, and differ from equal', () => {
  const ok = { cols: [1.5, 0.5], rows: [1, 1] };
  assert.deepEqual(C.migrateLayout({ grid: 4, sizes: ok, cells: [] }).sizes, ok);
  assert.deepEqual(C.cleanSizes({ cols: [3, 1], rows: [1, 1] }, 4), { cols: [1.5, 0.5], rows: [1, 1] }, 'normalised to mean 1');
  assert.equal(C.cleanSizes({ cols: [1, 1], rows: [1, 1] }, 4), null, 'equal tracks are the default');
  assert.equal(C.cleanSizes({ cols: [1.5, 0.5], rows: [1, 1] }, 6), null, 'wrong track count for the grid');
  assert.equal(C.cleanSizes({ cols: [1, -1], rows: [1, 1] }, 4), null);
  assert.equal(C.cleanSizes({ cols: [1, NaN], rows: [1, 1] }, 4), null);
  assert.equal(C.cleanSizes('x', 4), null);
  assert.equal(C.cleanSizes({ cols: [1, 1], rows: [1] }, 4), null);
  assert.deepEqual(C.cleanSizes({ cols: [2, 1, 1], rows: [1, 1] }, 6), { cols: [1.5, 0.75, 0.75], rows: [1, 1] });
});

test('dragTrack moves one divider: the pair keeps its total and neither side vanishes', () => {
  assert.deepEqual(C.dragTrack([1, 1], 1, 0.5), [1.5, 0.5]);
  assert.deepEqual(C.dragTrack([1, 1], 1, -0.25), [0.75, 1.25]);
  assert.deepEqual(C.dragTrack([1, 1], 1, 5), [1.8, 0.2], 'stops at the minimum share');
  assert.deepEqual(C.dragTrack([1, 1], 1, -5), [0.2, 1.8]);
  assert.deepEqual(C.dragTrack([1, 1, 1], 2, 0.5), [1, 1.5, 0.5], 'only the two next to the divider move');
  const t = [1, 1];
  C.dragTrack(t, 1, 0.5);
  assert.deepEqual(t, [1, 1], 'the input is left alone');
  assert.deepEqual(C.dragTrack([1, 1], 0, 0.5), [1, 1], 'no divider before the first track');
  assert.deepEqual(C.dragTrack([1, 1], 1, NaN), [1, 1]);
});

test('barIndexAtMs finds the bar a time falls in, whatever the chart interval', () => {
  const m = (min) => Date.UTC(2026, 9, 9, 13, min);   // 09:30 ET = 13:30 UTC in October
  const five = [0, 5, 10].map((x) => ({ ms: m(30 + x) })), one = Array.from({ length: 12 }, (_, i) => ({ ms: m(30 + i) }));
  assert.equal(C.barIndexAtMs(five, m(30), 300000), 0, 'the 09:30 bar');
  assert.equal(C.barIndexAtMs(five, m(33), 300000), 0, 'a minute chart at 09:33 lands in the 09:30 five-minute bar');
  assert.equal(C.barIndexAtMs(five, m(35), 300000), 1);
  assert.equal(C.barIndexAtMs(one, m(30), 60000), 0);
  assert.equal(C.barIndexAtMs(one, m(41), 60000), 11);
  assert.equal(C.barIndexAtMs(five, m(29), 300000), -1, 'before the first bar');
  assert.equal(C.barIndexAtMs(five, m(45), 300000), -1, 'after the last bar ends: nothing to point at');
  assert.equal(C.barIndexAtMs([{ ms: m(30) }, { ms: m(40) }], m(36), 60000), -1, 'a gap between two bars');
  assert.equal(C.barIndexAtMs([], m(30), 60000), -1);
  assert.equal(C.barIndexAtMs([{ ms: m(30) }, { ms: m(31) }], m(50), 0), 1, 'a tick chart: the last hour counts');
  assert.equal(C.barIndexAtMs([{ ms: m(30) }, { ms: m(31) }], m(30) + 2 * 3600000, 0), -1);
});

/* 2026-10-09 technical indicators: declared as data, keys match studies_ta.py's wire keys. */
test('technical indicators: wire keys, labels and style keys come from the definition', () => {
  const k = (id, params) => C.serverKey(C.instance(id, params));
  assert.equal(k('rsi'), 'rsi:14');
  assert.equal(k('rsi', { length: 2 }), 'rsi:2');
  assert.equal(k('macd'), 'macd:12:26:9');
  assert.equal(k('bb', { length: 20, mult: 2.5 }), 'bb:20:2.5');
  assert.equal(k('stoch'), 'stoch:14:3:3');
  assert.equal(k('keltner'), 'keltner:20:20:1.5');
  assert.equal(k('supertrend'), 'supertrend:10:3');
  assert.equal(k('orb', { minutes: 30 }), 'orb:30');
  assert.equal(k('sess', { session: 'asia' }), 'sess:asia');
  assert.equal(k('sess', { session: 'nonsense' }), 'sess:london', 'a bad choice falls back to the default');
  assert.equal(C.label(C.instance('macd')), 'MACD 12 26 9');
  assert.equal(C.label(C.instance('orb', { minutes: 5 })), 'Opening range 5m');
  assert.deepEqual(C.styleLineKeys('macd'), ['hist', 'macd', 'signal']);
  assert.deepEqual(C.styleLineKeys('supertrend'), ['up', 'dn']);
  assert.equal(C.clampParams('rsi', { length: 99999 }).length, 500);
  assert.equal(C.clampParams('rsi', { length: 1 }).length, 2);
  assert.deepEqual(C.serverKeys([C.instance('rsi'), C.instance('rsi'), C.instance('atr')]), ['rsi:14', 'atr:14'], 'two RSIs ask the server once');
});

test('technical indicators: own-pane ones move between panes, overlays stay on price', () => {
  for (const id of ['rsi', 'macd', 'stoch', 'mfi', 'er', 'atr']) assert.equal(C.placement(C.instance(id)), 'own', id);
  for (const id of ['bb', 'keltner', 'donchian', 'supertrend', 'tema', 'orb', 'sess']) assert.equal(C.placement(C.instance(id)), null, id);
});

test('technical indicators: lineValue reads a number, a part, or a custom reader, and never NaN', () => {
  const [up, dn] = C.TA_BY_ID.supertrend.lines;
  assert.equal(C.lineValue(up, { line: 100, dir: 1 }), 100);
  assert.equal(C.lineValue(dn, { line: 100, dir: 1 }), null, 'only the side the trend is on draws');
  assert.equal(C.lineValue(dn, { line: 100, dir: -1 }), 100);
  assert.equal(C.lineValue(C.TA_BY_ID.rsi.lines[0], 61.5), 61.5);
  assert.equal(C.lineValue(C.TA_BY_ID.rsi.lines[0], null), null);
  assert.equal(C.lineValue(C.TA_BY_ID.macd.lines[0], { hist: -0.3 }), -0.3);
  assert.equal(C.lineValue(C.TA_BY_ID.macd.lines[1], { macd: 1, signal: null }), 1);
  assert.equal(C.lineValue(C.TA_BY_ID.macd.lines[2], { macd: 1, signal: null }), null, 'signal still warming up');
  assert.equal(C.lineValue(C.TA_BY_ID.bb.lines[0], { up: NaN }), null);
});

test('technical indicators: the legend shows one value per visible line in its colour', () => {
  const inst = C.instance('stoch'), bar = { sv: { 'stoch:14:3:3': { k: 71.234, d: 65.5 } } };
  const v = C.legendValues(inst, bar, {}, 0.25);
  assert.deepEqual(v.map((x) => x.text), ['71.23', '65.50']);
  assert.deepEqual(v.map((x) => x.color), [C.TA_BY_ID.stoch.lines[0].color, C.TA_BY_ID.stoch.lines[1].color]);
  inst.style = { k: { color: '#112233', width: 1, dash: 'solid', visible: true }, d: { color: '#445566', width: 1, dash: 'solid', visible: false } };
  assert.deepEqual(C.legendValues(inst, bar, {}, 0.25), [{ text: '71.23', color: '#112233' }], 'a hidden line leaves the legend');
  assert.deepEqual(C.legendValues(C.instance('rsi'), { sv: {} }, {}, 0.25).map((x) => x.text), ['—'], 'warming up reads a dash');
});

test('technical indicators: a second copy of one indicator starts in a different colour', () => {
  const first = C.defaultStyle('rsi', []), second = C.defaultStyle('rsi', [C.instance('rsi')]);
  assert.notEqual(first.main.color, second.main.color);
  const sc = C.defaultStyle('macd', [C.instance('macd')]);
  assert.equal(sc.signal.color, C.TA_BY_ID.macd.lines[2].color, 'only the first line changes colour');
  assert.deepEqual(C.sanitizePreset('macd', { params: { fast: 5 } }).params, { fast: 5, slow: 26, signal: 9 });
});

test('technical indicators: Supertrend\'s legend shows only the side in force', () => {
  const inst = C.instance('supertrend'), k = 'supertrend:10:3';
  assert.deepEqual(C.legendValues(inst, { sv: { [k]: { line: 100.5, dir: 1 } } }, {}, 0.25).map((x) => x.text), ['100.50']);
  const down = C.legendValues(inst, { sv: { [k]: { line: 101, dir: -1 } } }, {}, 0.25);
  assert.deepEqual(down.map((x) => x.text), ['101.00']);
  assert.equal(down[0].color, C.TA_BY_ID.supertrend.lines[1].color, 'in the downtrend colour');
  assert.deepEqual(C.legendValues(inst, { sv: {} }, {}, 0.25).map((x) => x.text), ['—'], 'warming up: one dash');
});

test('structure indicators: wire keys match the server, the levels draw as steps, the range carries its OTE band', () => {
  const k = (id, params) => C.serverKey(C.instance(id, params));
  assert.equal(k('swing'), 'swing:50');
  assert.equal(k('equal', { tol: 5 }), 'equal:50:5');
  assert.equal(k('rmove'), 'rmove:200');
  assert.equal(k('rswing', { length: 20 }), 'rswing:20');
  assert.equal(k('vaprev'), 'vaprev');
  assert.equal(k('dhl'), 'dhl:5');
  assert.equal(k('noise', { k: 0.4, anchor: 'globex' }), 'noise:0.4:globex');
  assert.equal(k('noise', { anchor: 'moon' }), 'noise:0.3:rth');
  assert.equal(k('rvol'), 'rvol:14:10');
  assert.deepEqual(C.styleLineKeys('rmove'), ['hi', 'lo', 'mid', 'ote1', 'ote2']);
  for (const id of ['swing', 'equal', 'rmove', 'rswing', 'vaprev', 'dhl', 'noise']) {
    assert.ok(C.TA_BY_ID[id].lines.every((l) => l.step && l.tag === false), `${id}: step lines without an axis tag`);
  }
  assert.equal(C.placement(C.instance('rvol')), 'own');
  assert.equal(C.lineValue(C.TA_BY_ID.rmove.lines[3], { ote1: 19500.5, dir: 1 }), 19500.5);
  assert.deepEqual(C.legendValues(C.instance('swing'), { sv: { 'swing:50': { hi: 19500.25, lo: null } } }, {}, 0.25).map((x) => x.text), ['19500.25', '—']);
});
