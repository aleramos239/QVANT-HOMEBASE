import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const C = require('../../homebase/static/charts/catalog.js');
const strip = (list) => list.map(({ id, params, visible }) => ({ id, params, visible }));

test('a new chart gets volume, VWAP (ETH), session levels and a 3x footprint', () => {
  assert.deepEqual(strip(C.defaults()), [
    { id: 'volume', params: {}, visible: true },
    { id: 'vwap', params: { anchor: 'eth', bands: false }, visible: true },
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

test('params are clamped to their range and type', () => {
  assert.deepEqual(C.clampParams('ema', { length: 0 }), { length: 1 });
  assert.deepEqual(C.clampParams('ema', { length: 5000 }), { length: 1000 });
  assert.deepEqual(C.clampParams('ema', { length: '12.6' }), { length: 13 });
  assert.deepEqual(C.clampParams('ema', { length: 'abc' }), { length: 20 });
  assert.deepEqual(C.clampParams('ema', {}), { length: 20 });
  assert.deepEqual(C.clampParams('footprint', { imbalance: 2.5 }), { imbalance: 2.5 });
  assert.deepEqual(C.clampParams('footprint', { imbalance: -1 }), { imbalance: 0 });
  assert.deepEqual(C.clampParams('bigprints', { min: 0 }), { min: 1 });
  assert.deepEqual(C.clampParams('vwap', { anchor: 'xyz', bands: 'yes' }), { anchor: 'eth', bands: false });
  assert.deepEqual(C.clampParams('vwap', { anchor: 'rth', bands: true, junk: 1 }), { anchor: 'rth', bands: true });
  assert.deepEqual(C.clampParams('volume', { any: 1 }), {});
});

test('a Build-1 chart (st form) migrates field by field', () => {
  const st = { vwap: true, vwapAnchor: 'rth', vwapBands: true, ema1: 9, ema2: 21, sma: 50, vwma: 20, levels: true,
    volume: true, delta: true, cumdelta: true, adx: 14, footprint: true, imbalance: 4, profile: true, bigMin: 30 };
  const m = C.migrate({ root: 'es', spec: 'tick:1000', st });
  assert.equal(m.root, 'ES');
  assert.equal(m.spec, 'tick:1000');
  assert.deepEqual(strip(m.indicators), [
    { id: 'vwap', params: { anchor: 'rth', bands: true }, visible: true },
    { id: 'ema', params: { length: 9 }, visible: true },
    { id: 'ema', params: { length: 21 }, visible: true },
    { id: 'sma', params: { length: 50 }, visible: true },
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
  assert.deepEqual(m.indicators, [{ uid: 'keep', id: 'ema', params: { length: 1 }, visible: false }]);
  const fresh = C.migrate({ root: 'NQ', spec: 'time:60', indicators: [{ id: 'sma' }] }).indicators[0];
  assert.ok(fresh.uid);
  assert.equal(fresh.visible, true);
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
  assert.deepEqual(C.migrateLayout(undefined), { grid: 4, cells: [] });
});

test('legend labels', () => {
  assert.equal(C.label(C.instance('ema', { length: 20 })), 'EMA 20');
  assert.equal(C.label(C.instance('sma')), 'SMA 50');
  assert.equal(C.label(C.instance('vwap')), 'VWAP');
  assert.equal(C.label(C.instance('vwap', { anchor: 'rth' })), 'VWAP RTH');
  assert.equal(C.label(C.instance('adx')), 'ADX 14');
  assert.equal(C.label(C.instance('footprint')), 'Footprint 3×');
  assert.equal(C.label(C.instance('footprint', { imbalance: 0 })), 'Footprint');
  assert.equal(C.label(C.instance('bigprints')), 'Big prints ≥25');
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
  for (const id of ['volume', 'delta', 'levels', 'footprint', 'profile', 'bigprints']) {
    assert.deepEqual(C.legendValues(C.instance(id), bar, colors, 0.25), [], id);
  }
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
  assert.equal(C.rootName('HG'), 'Copper');
  assert.equal(C.rootName('ZZ'), '');
});

test('Bitcoin has a name', () => {
  assert.equal(C.rootName('BTC'), 'Bitcoin');
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
  assert.deepEqual(C.filter('', 'Moving averages').map((d) => d.id), ['ema', 'sma', 'vwma']);
  assert.deepEqual(C.filter('delta').map((d) => d.id), ['delta', 'cumdelta']);
  assert.deepEqual(C.filter('ORDER').map((d) => d.id), ['footprint', 'profile', 'delta', 'cumdelta', 'bigprints']);
  assert.deepEqual(C.filter('zzz'), []);
  assert.equal(C.filter('').length, C.CATALOG.length);
  assert.deepEqual(C.GROUPS, ['All', 'VWAP', 'Moving averages', 'Trend', 'Levels', 'Volume', 'Order flow']);
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
const live = (roots, extra = {}) => ({ mode: 'live', connected: true, error: null, roots,
  recorder: { written: 0, buffered: 0, error: null }, ...extra });
const tick = (age) => ({ contract: 'X', last_tick_age_s: age, error: null });

test('status: a weekend with Bitcoin fresh and the Globex futures closed is fine', () => {
  const f = C.feedSummary(live({ BTC: tick(2), NQ: tick(180000) }), ...SAT_NOON);
  assert.deepEqual(f, { dot: 'ok', text: 'feeds ok', textClass: '', title: 'BTC 2.0s  ·  NQ closed' });
});

test('status: a stale open market is amber, the stalest first, two at most', () => {
  const f = C.feedSummary(live({ NQ: tick(45), ES: tick(0.5), YM: tick(90), RTY: tick(31) }), ...WED_10);
  assert.equal(f.dot, 'warn');
  assert.equal(f.text, 'YM stale 2m · NQ stale 45.0s');
  assert.equal(f.textClass, 'warn');
  assert.equal(f.title, 'NQ 45.0s  ·  ES 0.5s  ·  YM 2m  ·  RTY 31.0s');
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
  const mixed = C.feedSummary(live({ NQ: tick(45), BTC: tick(null) }), ...WED_10);   // a warning wins the dot and the colour
  assert.deepEqual([mixed.dot, mixed.text, mixed.textClass], ['warn', 'NQ stale 45.0s · BTC no ticks yet', 'warn']);
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
