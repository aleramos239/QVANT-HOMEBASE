import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const S = require('../../homebase/static/charts/settings.js');

/* HBCell.palette()'s keys that settings resolve against */
const LIGHT = { up: '#089981', down: '#F23645', bg: '#FFFFFF', grid: '#F0F3FA', cross: '#9598A1',
  watermark: 'rgba(15,15,15,.06)', text2: '#787B86', border: '#E0E3EB' };
const DARK = { ...LIGHT, bg: '#0F0F0F', grid: '#1C1C1C', watermark: 'rgba(219,219,219,.06)', text2: '#8C8C8C', border: '#2E2E2E' };

test('the defaults: every field, colours that follow the theme are null, the spec\'s values', () => {
  const d = S.DEFAULTS;
  assert.deepEqual(Object.keys(d), S.FIELDS.map((f) => f.key));
  for (const k of Object.keys(S.THEMED)) assert.equal(d[k], null, k);
  assert.equal(d.prevClose, false);
  assert.equal(d.body && d.borders && d.wick, true);
  assert.equal(d.precision, null);
  assert.equal(d.timezone, 'exchange');
  assert.equal(d.ethBg, false);
  assert.equal(d.ethBgColor, 'rgba(120,123,134,.08)');
  assert.equal(d.title && d.ohlc && d.barChange && d.volume && d.indTitles && d.indArgs && d.indValues, true);
  assert.equal(d.titleMode, 'both');
  assert.equal(d.scalePriceOnly, false);
  assert.equal(d.lastLabel && d.lastLine && d.countdown, true);
  assert.equal(d.lastLineStyle, 'dotted');
  assert.deepEqual([d.marginTop, d.marginBottom, d.rightOffset], [10, 15, 6]);
  assert.equal(d.vertGrid && d.horzGrid && d.watermark, true);
  assert.deepEqual([d.crossStyle, d.crossWidth, d.scaleFont], ['dashed', 1, 12]);
  assert.ok(Object.isFrozen(d));
});

test('colours: #RRGGBB or rgba(r,g,b,a), one spelling each', () => {
  assert.deepEqual(S.parseColor('#26a69a'), { r: 38, g: 166, b: 154, a: 1 });
  assert.deepEqual(S.parseColor(' rgba(120, 123, 134, 0.08) '), { r: 120, g: 123, b: 134, a: 0.08 });
  for (const bad of ['teal', '#12345', '#1234567', 'rgba(256,0,0,1)', 'rgba(1,2,3,1.5)', 'rgb(1,2,3)', null, 7]) {
    assert.equal(S.parseColor(bad), null, String(bad));
  }
  assert.equal(S.fmtColor({ r: 38, g: 166, b: 154, a: 1 }), '#26A69A');
  assert.equal(S.fmtColor({ r: 120, g: 123, b: 134, a: 0.08 }), 'rgba(120,123,134,.08)');
  assert.equal(S.fmtColor({ r: 0, g: 0, b: 0, a: 0 }), S.CLEAR);
  assert.equal(S.hexOf('rgba(15,15,15,.06)'), '#0F0F0F');
  assert.equal(S.alphaOf('rgba(15,15,15,.06)'), 0.06);
  assert.equal(S.alphaOf('#FFFFFF'), 1);
  assert.equal(S.withAlpha('#2962FF', 0.5), 'rgba(41,98,255,.5)');
  assert.equal(S.withAlpha('rgba(41,98,255,.5)', 1), '#2962FF');
});

test('normalize keeps every field, drops the rest, clamps numbers, checks colours and choices', () => {
  const n = S.normalize({ junk: 1, marginTop: 55, marginBottom: '20', rightOffset: -3, crossWidth: 2.6, scaleFont: 9,
    precision: 9, bodyUp: '#26a69a', bg: 'rgba(0, 0, 0, 0.5)', wickUp: 'teal', timezone: 'Mars', lastLineStyle: 'dashed',
    ohlc: 'no', ethBgColor: null });
  assert.equal('junk' in n, false);
  assert.deepEqual(Object.keys(n), S.FIELDS.map((f) => f.key));
  assert.deepEqual([n.marginTop, n.marginBottom, n.rightOffset, n.crossWidth, n.scaleFont, n.precision], [40, 20, 0, 3, 10, 6]);
  assert.equal(n.bodyUp, '#26A69A');
  assert.equal(n.bg, 'rgba(0,0,0,.5)');
  assert.equal(n.wickUp, null);
  assert.equal(n.timezone, 'exchange');
  assert.equal(n.lastLineStyle, 'dashed');
  assert.equal(n.ohlc, true);
  assert.equal(n.ethBgColor, 'rgba(120,123,134,.08)');
  assert.deepEqual([null, 'default', -1, '2', 0].map((p) => S.normalize({ precision: p }).precision), [null, null, 0, 2, 0]);
  assert.deepEqual(S.normalize(null), S.DEFAULTS);
  assert.deepEqual(S.normalize([1, 2]), S.DEFAULTS);
});

test('overrides keep only what differs from the defaults, and round-trip', () => {
  assert.deepEqual(S.overrides(S.DEFAULTS), {});
  assert.deepEqual(S.overrides({}), {});
  assert.deepEqual(S.overrides({ ethBgColor: 'rgba(120, 123, 134, 0.08)', marginTop: 10 }), {});   // the defaults, spelled otherwise
  const o = S.overrides({ prevClose: true, bodyUp: '#26a69a', marginTop: 20, timezone: 'utc', precision: 0, junk: 1 });
  assert.deepEqual(o, { prevClose: true, bodyUp: '#26A69A', precision: 0, timezone: 'utc', marginTop: 20 });
  assert.deepEqual(S.normalize(o), S.normalize({ ...S.DEFAULTS, ...o }));
  assert.deepEqual(S.overrides(S.normalize(o)), o);
});

test('a colour never changed follows the theme; a changed one stays', () => {
  const light = S.resolve({}, LIGHT), dark = S.resolve({}, DARK);
  assert.deepEqual([light.bg, dark.bg], ['#FFFFFF', '#0F0F0F']);
  assert.deepEqual([light.bodyUp, light.bodyDown, light.borderDown, light.wickUp], ['#089981', '#F23645', '#F23645', '#089981']);
  assert.deepEqual([dark.vertGridColor, dark.horzGridColor, dark.scaleText, dark.scaleLines], ['#1C1C1C', '#1C1C1C', '#8C8C8C', '#2E2E2E']);
  assert.deepEqual([light.crossColor, dark.watermarkColor], ['#9598A1', 'rgba(219,219,219,.06)']);
  const mine = { bg: '#131722', bodyUp: '#2962FF' };
  assert.deepEqual([S.resolve(mine, LIGHT).bg, S.resolve(mine, DARK).bg], ['#131722', '#131722']);
  assert.deepEqual([S.resolve(mine, DARK).bodyUp, S.resolve(mine, DARK).bodyDown], ['#2962FF', '#F23645']);
  assert.equal(light.ethBgColor, 'rgba(120,123,134,.08)');
});

test('chartOptions: background, text, font, grid, crosshair, right offset, scale lines', () => {
  assert.deepEqual(S.chartOptions(S.resolve({}, LIGHT)), {
    layout: { background: { type: 'solid', color: '#FFFFFF' }, textColor: '#787B86', fontSize: 12 },
    grid: { vertLines: { visible: true, color: '#F0F3FA' }, horzLines: { visible: true, color: '#F0F3FA' } },
    crosshair: { vertLine: { color: '#9598A1', style: 2, width: 1 }, horzLine: { color: '#9598A1', style: 2, width: 1 } },
    timeScale: { rightOffset: 6, borderColor: '#E0E3EB' },
    rightPriceScale: { borderColor: '#E0E3EB' },
  });
  const o = S.chartOptions(S.resolve({ vertGrid: false, horzGridColor: '#FF0000', crossStyle: 'solid', crossWidth: 3,
    crossColor: '#2962FF', scaleFont: 14, rightOffset: 20, scaleLines: '#000000', scaleText: '#111111', bg: '#131722' }, LIGHT));
  assert.deepEqual(o.grid, { vertLines: { visible: false, color: '#F0F3FA' }, horzLines: { visible: true, color: '#FF0000' } });
  assert.deepEqual(o.crosshair.horzLine, { color: '#2962FF', style: 0, width: 3 });
  assert.deepEqual(o.layout, { background: { type: 'solid', color: '#131722' }, textColor: '#111111', fontSize: 14 });
  assert.deepEqual([o.timeScale.rightOffset, o.timeScale.borderColor, o.rightPriceScale.borderColor], [20, '#000000', '#000000']);
});

test('candleOptions: colours and visibility, precision from the tick or the setting, the last-price label and line', () => {
  assert.deepEqual(S.candleOptions(S.resolve({}, LIGHT), 0.25), {
    upColor: '#089981', downColor: '#F23645', borderVisible: true, borderUpColor: '#089981', borderDownColor: '#F23645',
    wickVisible: true, wickUpColor: '#089981', wickDownColor: '#F23645',
    priceFormat: { type: 'price', precision: 2, minMove: 0.25 },
    lastValueVisible: true, priceLineVisible: true, priceLineStyle: 1,
  });
  const off = S.candleOptions(S.resolve({ body: false, borders: false, wick: false, lastLabel: false, lastLine: false,
    lastLineStyle: 'solid' }, LIGHT), 0.25);
  assert.deepEqual([off.upColor, off.downColor, off.borderVisible, off.wickVisible], [S.CLEAR, S.CLEAR, false, false]);
  assert.deepEqual([off.lastValueVisible, off.priceLineVisible, off.priceLineStyle], [false, false, 0]);
  const pf = (over, tick) => S.candleOptions(S.resolve(over, LIGHT), tick).priceFormat;
  assert.deepEqual(pf({ precision: 0 }, 0.25), { type: 'price', precision: 0, minMove: 1 });
  assert.deepEqual(pf({ precision: 3 }, 0.25), { type: 'price', precision: 3, minMove: 0.001 });
  assert.deepEqual(pf({}, 0.1), { type: 'price', precision: 1, minMove: 0.1 });
  assert.deepEqual(pf({}, 0.015625), { type: 'price', precision: 6, minMove: 0.015625 });
});

test('scale margins and the legend flags', () => {
  assert.deepEqual(S.scaleMargins(S.resolve({}, LIGHT)), { top: 0.1, bottom: 0.15 });
  assert.deepEqual(S.scaleMargins(S.resolve({ marginTop: 0, marginBottom: 40 }, LIGHT)), { top: 0, bottom: 0.4 });
  assert.deepEqual(S.legendFlags(S.resolve({}, LIGHT)), { title: true, titleMode: 'both', ohlc: true, change: true,
    volume: true, indTitles: true, indArgs: true, indValues: true });
  assert.equal(S.legendFlags(S.resolve({ barChange: false }, LIGHT)).change, false);
});

test('colour bars based on previous close: up at or above the previous close (the first bar: its open)', () => {
  const R = S.resolve({ prevClose: true }, LIGHT);
  const bs = [{ o: 10, c: 9 }, { o: 8, c: 9.5 }, { o: 10, c: 9.5 }, { o: 9, c: 9.2 }];
  assert.deepEqual(S.barColorsByPrevClose(bs, R).map((x) => x.color), ['#F23645', '#089981', '#089981', '#F23645']);
  assert.deepEqual(S.barColor(bs[2], bs[1], R), { color: '#089981', borderColor: '#089981', wickColor: '#089981' });
  const hollow = S.resolve({ prevClose: true, body: false }, LIGHT);
  assert.deepEqual(S.barColor(bs[3], bs[2], hollow), { color: S.CLEAR, borderColor: '#F23645', wickColor: '#F23645' });
});

test('legend texts: an indicator\'s title and arguments, the symbol title', () => {
  assert.deepEqual(S.splitLabel('EMA 20', true), ['EMA', '20']);
  assert.deepEqual(S.splitLabel('Big prints ≥25', true), ['Big prints', '≥25']);
  assert.deepEqual(S.splitLabel('Session levels', false), ['Session levels', '']);
  assert.deepEqual(S.splitLabel('VWAP', true), ['VWAP', '']);
  const all = { indTitles: true, indArgs: true };
  assert.equal(S.legendLabel('VWAP RTH', true, all), 'VWAP RTH');
  assert.equal(S.legendLabel('VWAP RTH', true, { ...all, indTitles: false }), 'RTH');
  assert.equal(S.legendLabel('VWAP RTH', true, { ...all, indArgs: false }), 'VWAP');
  assert.equal(S.legendLabel('Session levels', false, { ...all, indArgs: false }), 'Session levels');
  assert.equal(S.titleText('NQ', 'E-mini Nasdaq-100', '1m', 'both'), 'NQ · E-mini Nasdaq-100 · 1m');
  assert.equal(S.titleText('NQ', 'E-mini Nasdaq-100', '1m', 'ticker'), 'NQ · 1m');
  assert.equal(S.titleText('NQ', 'E-mini Nasdaq-100', '1m', 'description'), 'E-mini Nasdaq-100 · 1m');
  assert.equal(S.titleText('ZZ', '', '5m', 'description'), 'ZZ · 5m');
});

const SUMMER = Date.UTC(2026, 8, 22, 13, 30);    // 09:30 EDT
const WINTER = Date.UTC(2026, 0, 15, 14, 30);    // 09:30 EST
const hm = (s) => new Date(s * 1000).toISOString().slice(11, 16);

test('time zones: the axis runs on the zone\'s wall clock', () => {
  assert.deepEqual(['exchange', 'utc', 'chicago', 'london'].map((z) => hm(S.wallSeconds(SUMMER, z))), ['09:30', '13:30', '08:30', '14:30']);
  assert.deepEqual(['exchange', 'utc', 'chicago', 'london'].map((z) => hm(S.wallSeconds(WINTER, z))), ['09:30', '14:30', '08:30', '14:30']);
  assert.equal(S.wallSeconds(SUMMER, 'exchange'), Date.UTC(2026, 8, 22, 9, 30) / 1000);
  assert.equal(S.wallSeconds(SUMMER, 'local'), Math.floor((SUMMER - new Date(SUMMER).getTimezoneOffset() * 60000) / 1000));
  assert.equal(S.wallSeconds(SUMMER + 1500, 'utc'), SUMMER / 1000 + 1);
  assert.equal(S.zoneOffsetMs('America/New_York', Date.UTC(2026, 2, 8, 6, 59)), -5 * 3600000);   // DST starts 07:00 UTC
  assert.equal(S.zoneOffsetMs('America/New_York', Date.UTC(2026, 2, 8, 7, 0)), -4 * 3600000);
  assert.deepEqual(S.TIMEZONES.map(([k]) => k), ['exchange', 'utc', 'chicago', 'london', 'local']);
});

test('regular hours are 09:30-16:00 ET: everything else is shaded', () => {
  const et = (h, m) => Date.UTC(2026, 8, 22, h, m) / 1000;
  assert.deepEqual([et(9, 29), et(9, 30), et(15, 59), et(16, 0), et(18, 0), et(0, 0)].map(S.outsideRth),
    [true, false, false, true, true, true]);
});

test('the countdown: to the bar\'s end, never past its session\'s close', () => {
  const et = (d, h, m = 0) => Date.UTC(2026, 8, d, h, m);
  assert.equal(S.barCloseEt({ t: et(22, 9, 30) / 1000, s: '2026-09-22' }, 60000, false), et(22, 9, 31));
  assert.equal(S.barCloseEt({ t: et(22, 14) / 1000, s: '2026-09-22' }, 4 * 3600000, false), et(22, 17));   // 4h bar: 17:00 close
  assert.equal(S.barCloseEt({ t: et(22, 14) / 1000, s: '2026-09-22' }, 4 * 3600000, true), et(22, 18));    // 24/7: 18:00
  assert.equal(S.barCloseEt({ t: et(21, 18) / 1000, s: '2026-09-22' }, 86400000, false), et(22, 17));      // the daily bar
  assert.equal(S.barCloseEt({ t: et(22, 9) / 1000 }, 3600000, false), et(22, 10));                          // no session: no cap
  assert.deepEqual([0, 59999, 60000, 3599999, 3600000, 3661000, -5].map(S.fmtCountdown),
    ['00:00', '00:59', '01:00', '59:59', '1:00:00', '1:01:01', '00:00']);
});

test('template names: 1-40 characters, no / \\ .. or control characters, not "."', () => {
  for (const bad of ['', 'x'.repeat(41), 'a/b', 'a\\b', '..', 'a..b', '.', 'tab\tx', 'del\x7f']) {
    assert.notEqual(S.templateNameError(bad), '', JSON.stringify(bad));
  }
  assert.equal(S.templateNameError('Dark · v1.2'), '');
  assert.equal(S.templateNameError('x'.repeat(40)), '');
});

test('the swatch palette: 10 hues x 6 shades, all distinct, with the chart\'s up and down', () => {
  assert.equal(S.PALETTE.length, 6);
  assert.ok(S.PALETTE.every((row) => row.length === 10 && row.every((c) => /^#[0-9A-F]{6}$/.test(c))));
  assert.equal(new Set(S.PALETTE.flat()).size, 60);
  assert.ok(S.PALETTE.flat().includes('#089981') && S.PALETTE.flat().includes('#F23645'));
});

// ---- chart templates (spec §8): {settings, indicators?, spec?} ----
const CHART = { settings: { prevClose: true }, indicators: [
  { uid: 'a', id: 'delta', params: {}, visible: true, pane: 'main' },
  { uid: 'b', id: 'ema', params: { length: 9 }, visible: false }], spec: 'time:300' };

test('buildTemplate: settings always, indicators (no uid, movable ones keep pane) unless told off, spec only when asked', () => {
  const full = S.buildTemplate(CHART, { interval: true });
  assert.deepEqual(full.settings, { prevClose: true });
  assert.deepEqual(full.indicators, [{ id: 'delta', params: {}, visible: true, pane: 'main' },
    { id: 'ema', params: { length: 9, source: 'close' }, visible: false }]);
  assert.equal('uid' in full.indicators[0], false);
  assert.equal('pane' in full.indicators[1], false);   // EMA never moves: no pane, whatever the source carried
  assert.equal(full.spec, 'time:300');

  const settingsOnly = S.buildTemplate(CHART, { indicators: false });
  assert.equal('indicators' in settingsOnly, false);
  assert.equal('spec' in settingsOnly, false);   // interval defaults off

  const noInterval = S.buildTemplate(CHART);
  assert.ok(Array.isArray(noInterval.indicators));   // indicators default on
  assert.equal('spec' in noInterval, false);
});

test('applyTemplate: fresh uids each time, spec only when the template stored one, an unknown id or bad spec dropped', () => {
  const stored = S.buildTemplate(CHART, { interval: true });
  const a = S.applyTemplate(stored), b = S.applyTemplate(stored);
  assert.deepEqual(a.settings, { prevClose: true });
  assert.equal(a.indicators.length, 2);
  assert.notEqual(a.indicators[0].uid, b.indicators[0].uid);   // fresh every apply
  assert.notEqual(a.indicators[0].uid, a.indicators[1].uid);
  assert.equal(a.indicators[0].pane, 'main');
  assert.equal('pane' in a.indicators[1], false);
  assert.equal(a.spec, 'time:300');

  const noInterval = S.applyTemplate(S.buildTemplate(CHART));
  assert.equal('spec' in noInterval, false);   // never stored: never applied

  const junk = S.applyTemplate({ settings: { prevClose: true }, indicators: [{ id: 'nope' }], spec: 'nonsense' });
  assert.deepEqual(junk.indicators, []);
  assert.equal('spec' in junk, false);
});

test('applyTemplate: an old (Task 6/7) settings-only template stays valid — indicators and spec left untouched', () => {
  const old = { prevClose: true, marginTop: 20 };   // no settings/indicators/spec keys: the old flat shape
  const t = S.applyTemplate(old);
  assert.deepEqual(t.settings, { prevClose: true, marginTop: 20 });
  assert.equal('indicators' in t, false);
  assert.equal('spec' in t, false);
  assert.deepEqual(S.applyTemplate({}).settings, {});   // "Apply defaults": settings only, back to the defaults
});

test('the Events fields: High and Medium on, USD, lines on; currencies cleaned and sorted', () => {
  const d = S.DEFAULTS;
  assert.deepEqual([d.evHigh, d.evMedium, d.evLow, d.evHoliday, d.evLines], [true, true, false, false, true]);
  assert.deepEqual(d.evCountries, ['USD']);
  assert.deepEqual(S.normalize({ evCountries: ['eur', 'USD', 'usd', 'All', 7, 'toolong', ' gbp '] }).evCountries,
    ['ALL', 'EUR', 'GBP', 'USD']);
  assert.deepEqual(S.normalize({ evCountries: 'USD' }).evCountries, ['USD']);
  assert.deepEqual(S.normalize({ evCountries: [] }).evCountries, []);
  assert.deepEqual(S.overrides({ evCountries: ['usd'] }), {});
  assert.deepEqual(S.overrides({ evCountries: ['USD', 'EUR'], evLow: true }), { evLow: true, evCountries: ['EUR', 'USD'] });
  const n = S.normalize({});
  n.evCountries.push('JPY');                                       // a copy: the defaults never change
  assert.deepEqual(S.DEFAULTS.evCountries, ['USD']);
});

test('clockText: the Time format setting (24h default, 12h AM/PM)', () => {
  const S2 = S;
  assert.equal(S2.clockText('19:30', '24h'), '19:30');
  assert.equal(S2.clockText('19:30', '12h'), '7:30 PM');
  assert.equal(S2.clockText('00:05:09', '12h'), '12:05:09 AM');
  assert.equal(S2.clockText('12:00', '12h'), '12:00 PM');
  assert.equal(S2.clockText('09:15', '12h'), '9:15 AM');
  assert.equal(S2.clockText('garbage', '12h'), 'garbage');
  assert.equal(S.DEFAULTS.timeFormat, '24h');
});

/* 2026-10-09, the owner: "the countdown to bar close sometimes doesn't show" -- white text on his white up
   candles, and nothing at all between a bar's close and the next bar's first trade. */
test('the countdown runs on the clock: past a closed bar it counts to the next boundary while the session is open', () => {
  const et = (d, h, m = 0, s = 0) => Date.UTC(2026, 8, d, h, m, s);
  const bar = { t: et(22, 9, 30) / 1000, s: '2026-09-22' };
  assert.equal(S.countdownLeft(bar, 60000, false, et(22, 9, 30, 20)), 40000);       // the bar is open: until its close
  assert.equal(S.countdownLeft(bar, 60000, false, et(22, 9, 31, 0)), 60000);        // just closed, no new bar yet: the next minute
  assert.equal(S.countdownLeft(bar, 60000, false, et(22, 9, 41, 15)), 45000);       // a feed 10 minutes late: still the clock's minute
  assert.equal(S.countdownLeft(bar, 300000, false, et(22, 9, 37)), 180000);         // 5m bars step from the bar's own start
  const lastBar = { t: et(22, 16, 59) / 1000, s: '2026-09-22' };
  assert.equal(S.countdownLeft(lastBar, 60000, false, et(22, 16, 59, 30)), 30000);
  assert.equal(S.countdownLeft(lastBar, 60000, false, et(22, 17, 0, 0)), 0);        // the session closed: nothing
  assert.equal(S.countdownLeft(lastBar, 60000, false, et(23, 9, 30)), 0);           // next day, no new bar: nothing
  assert.equal(S.countdownLeft(lastBar, 60000, true, et(22, 17, 0, 30)), 30000);    // a 24/7 root closes at 18:00
  assert.equal(S.countdownLeft({ t: et(22, 15) / 1000, s: '2026-09-22' }, 4 * 3600000, false, et(22, 16, 30)), 1800000);   // never past the close
  assert.equal(S.countdownLeft({ t: et(22, 9) / 1000 }, 3600000, false, et(22, 10, 5)), 0);   // no session known: only its own bar
  assert.equal(S.countdownLeft({ t: et(22, 9) / 1000 }, 3600000, false, et(22, 9, 5)), 55 * 60000);
  for (const bad of [[null, 60000, 1], [bar, 0, 1], [bar, 60000, NaN]]) assert.equal(S.countdownLeft(bad[0], bad[1], false, bad[2]), 0);
});

test('the last bar\'s colour: the body\'s, then the border\'s, then the wick\'s -- never a clear one', () => {
  const r = S.resolve({ bodyUp: '#FFFFFF', bodyDown: '#757575', borderUp: '#111111', borderDown: '#222222', wickUp: '#333333' }, DARK);
  assert.equal(S.lastColor(r, true), '#FFFFFF');
  assert.equal(S.lastColor(r, false), '#757575');
  assert.equal(S.lastColor({ ...r, body: false }, true), '#111111');                       // Body off: the border's
  assert.equal(S.lastColor({ ...r, body: false }, false), '#222222');
  assert.equal(S.lastColor({ ...r, body: false, borders: false }, true), '#333333');       // then the wick's
  assert.equal(S.lastColor({ ...r, body: false, borders: false, wick: false }, true), '#8C8C8C');   // then the scale's text
  assert.equal(S.lastColor({ ...r, bodyUp: 'rgba(255,255,255,.1)' }, true), '#111111');    // a see-through body does not count
  assert.equal(S.lastColor({ ...r, bodyUp: 'rgba(8,153,129,.5)' }, true), '#089981');      // half see-through: its solid colour
});

test('text on a fill: dark on a light fill, white on a dark one (the countdown on white candles)', () => {
  assert.equal(S.contrastText('#FFFFFF'), '#000000');
  assert.equal(S.contrastText('#757575'), '#FFFFFF');
  assert.equal(S.contrastText('#089981'), '#FFFFFF');
  assert.equal(S.contrastText('#F23645'), '#FFFFFF');
  assert.equal(S.contrastText('#FFEB3B'), '#000000');
  assert.equal(S.contrastText('rgba(255,255,255,.2)', '#0F0F0F'), '#FFFFFF');   // mostly the dark chart behind it
  assert.equal(S.contrastText('rgba(0,0,0,.2)', '#FFFFFF'), '#000000');
  assert.equal(S.contrastText('teal'), '#FFFFFF');
});
