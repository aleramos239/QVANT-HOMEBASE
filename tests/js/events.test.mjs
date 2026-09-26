import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const E = require('../../homebase/static/charts/events.js');

const at = (h, m, d = 22) => Date.UTC(2026, 8, d, h + 4, m);    // an ET (EDT) wall time on 2026-09-d, as epoch ms
const ev = (title, h, m, impact, country = 'USD', extra = {}) =>
  ({ t_ms: at(h, m), title, country, impact, forecast: '', previous: '', ...extra });
const CPI = ev('CPI m/m', 8, 30, 'High', 'USD', { forecast: '0.3%', previous: '0.2%' });
const CORE = ev('Core CPI m/m', 8, 30, 'High', 'USD', { forecast: '0.3%', previous: '0.3%' });
const IFO = ev('German ifo Business Climate', 4, 0, 'Medium', 'EUR');
const OIL = ev('Crude Oil Inventories', 10, 30, 'Low');
const HOL = ev('Bank Holiday', 0, 0, 'Holiday', 'JPY');
const OPEC = ev('OPEC Meetings', 3, 0, 'Non-Economic', 'ALL');
const SET = { evHigh: true, evMedium: true, evLow: false, evHoliday: false, evCountries: ['USD'] };

test('a chart shows the impacts it ticks, in the currencies it picks', () => {
  const all = [HOL, OPEC, IFO, CPI, CORE, OIL];
  assert.deepEqual(E.shown(all, SET).map((e) => e.title), ['CPI m/m', 'Core CPI m/m']);
  assert.deepEqual(E.shown(all, { ...SET, evLow: true, evCountries: ['usd', 'EUR'] }).map((e) => e.title),
    ['German ifo Business Climate', 'CPI m/m', 'Core CPI m/m', 'Crude Oil Inventories']);
  assert.deepEqual(E.shown(all, { ...SET, evHoliday: true, evCountries: ['JPY', 'ALL'] }).map((e) => e.title),
    ['Bank Holiday', 'OPEC Meetings']);                            // Holiday covers Non-Economic too
  assert.deepEqual(E.shown(all, { ...SET, evCountries: [] }), []);
});

test('flags: one per event time, merged when closer than a flag, coloured by the highest impact', () => {
  const x = (t) => (t - at(0, 0)) / 60000;                            // 1 px per minute from midnight ET
  const late = { ...OIL, title: 'Late', t_ms: at(10, 36) };
  const flags = E.layout([OIL, CPI, CORE, IFO, late], x, 2000);
  assert.deepEqual(flags.map((f) => [f.x, f.events.map((e) => e.title), f.color, f.line]), [
    [240, ['German ifo Business Climate'], '#FF9800', false],
    [510, ['CPI m/m', 'Core CPI m/m'], '#F23645', true],
    [630, ['Crude Oil Inventories', 'Late'], '#F7C600', false],      // 6 px apart: one flag
  ]);
  assert.equal(E.layout([CPI], () => null, 2000).length, 0);          // not on this chart
  assert.equal(E.layout([CPI], () => 2100, 2000).length, 0);          // off the pane
  assert.deepEqual(E.COLORS, { High: '#F23645', Medium: '#FF9800', Low: '#F7C600', Holiday: '#9598A1', 'Non-Economic': '#9598A1' });
  assert.equal(E.FLAG, 10);
});

test('a flag is hit within its radius + 2 px', () => {
  const flags = [{ x: 100, events: [CPI] }, { x: 140, events: [OIL] }];
  assert.equal(E.flagAt(flags, { x: 104, y: 293 }, 290), flags[0]);
  assert.equal(E.flagAt(flags, { x: 108, y: 290 }, 290), null);
  assert.equal(E.flagAt(flags, { x: 140, y: 296 }, 290), flags[1]);
  assert.equal(E.flagAt(flags, { x: 140, y: 298 }, 290), null);
});

test('the tooltip: one line per event, the time in the chart\'s zone', () => {
  assert.equal(E.tipLine(CPI, 'exchange'), '08:30 CPI m/m · USD · High · forecast 0.3% · prev 0.2%');
  assert.equal(E.tipLine(OIL, 'exchange'), '10:30 Crude Oil Inventories · USD · Low');
  assert.equal(E.tipLine(CPI, 'utc'), '12:30 CPI m/m · USD · High · forecast 0.3% · prev 0.2%');
  assert.deepEqual(E.tipLines({ events: [CPI, CORE] }, 'exchange'), [
    '08:30 CPI m/m · USD · High · forecast 0.3% · prev 0.2%',
    '08:30 Core CPI m/m · USD · High · forecast 0.3% · prev 0.3%',
  ]);
});

test('the status bar: the next event shown, "(in 2h 14m)", coloured by impact; none left: hidden', () => {
  const now = at(6, 16);
  assert.deepEqual(E.nextText([IFO, CPI, CORE, OIL], now), { text: 'Next USD: CPI m/m 08:30 (in 2h 14m)', color: '#F23645' });
  assert.equal(E.nextText([IFO, CPI], at(8, 30)), null);             // at its time it is gone
  assert.equal(E.nextText([], now), null);
  assert.equal(E.nextText([{ ...CPI, t_ms: now + 8 * 86400000 }], now), null);   // not this week
  assert.deepEqual([20000, 59 * 60000, 3600000, 134 * 60000, 27 * 3600000, 48 * 3600000].map(E.fmtIn),
    ['1m', '59m', '1h', '2h 14m', '1d 3h', '2d']);
});
