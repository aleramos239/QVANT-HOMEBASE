import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* Chart types (2026-10-11): candles (the default), Heikin Ashi, OHLC bars and a close line. Heikin Ashi is the candle
   series' own data averaged; bars and the line ride on a second series (see Cell.makeAlt), so the candle series stays
   under every marker, price line and drawing. Cell.prototype is driven on a bare object, as cell-holes does. */
const require = createRequire(import.meta.url);
globalThis.window = globalThis;
require('../../homebase/static/charts/primitives.js');
require('../../homebase/static/charts/catalog.js');
require('../../homebase/static/charts/drawings.js');
require('../../homebase/static/charts/scrollback.js');
require('../../homebase/static/charts/cell.js');
const S = require('../../homebase/static/charts/settings.js');
const { Cell } = globalThis.HBCell;

const bar = (tt, o, h, l, c, extra = {}) => ({ tt, o, h, l, c, v: 1, ...extra });
const cellWith = (type, bars) => Object.assign(Object.create(Cell.prototype), { R: { chartType: type, prevClose: false }, bars, haC: null, alt: null });

test('the chart type setting: candles by default, a junk value falls back, only a changed one is stored', () => {
  assert.equal(S.DEFAULTS.chartType, 'candles');
  assert.equal(S.normalize({ chartType: 'renko' }).chartType, 'candles');
  assert.equal(S.normalize({ chartType: 'heikin' }).chartType, 'heikin');
  assert.deepEqual(S.overrides({ chartType: 'line' }), { chartType: 'line' });
  assert.deepEqual(S.overrides({ chartType: 'candles' }), {});
});

test('Heikin Ashi: close = (o + h + l + c) / 4, open = the middle of the bar before it, wicks cover both', () => {
  const bars = [bar(1, 10, 12, 9, 11), bar(2, 11, 14, 10, 13), bar(3, 13, 13.5, 8, 9)];
  const c = cellWith('heikin', bars);
  const d = c.candleData();
  assert.deepEqual(d[0], { time: 1, open: 10.5, close: 10.5, high: 12, low: 9 });          // (10 + 11) / 2; (10+12+9+11) / 4
  assert.equal(d[1].close, (11 + 14 + 10 + 13) / 4);
  assert.equal(d[1].open, (10.5 + 10.5) / 2);
  assert.equal(d[1].high, 14);
  assert.equal(d[2].open, (d[1].open + d[1].close) / 2);
  assert.equal(d[2].low, 8);
});

test('Heikin Ashi: a live tick re-prices only the last bar, from the bar before it', () => {
  const bars = [bar(1, 10, 12, 9, 11), bar(2, 11, 14, 10, 13)];
  const c = cellWith('heikin', bars);
  const before = c.candleData();
  bars[1] = bar(2, 11, 15, 10, 14);                       // the last bar moved
  const live = c.candleAt(bars[1], 1);
  assert.equal(live.time, 2);
  assert.equal(live.open, before[1].open);                // its open leans on the bar before, which did not change
  assert.equal(live.close, (11 + 15 + 10 + 14) / 4);
  assert.equal(live.high, 15);
  bars.push(bar(3, 14, 16, 13, 15));                      // a new bar: built on the re-priced one
  const next = c.candleAt(bars[2], 2);
  assert.equal(next.open, (live.open + live.close) / 2);
});

test('candles stay plain candles; bars and the line each have their own point', () => {
  const b = bar(5, 1, 3, 0.5, 2);
  assert.deepEqual(cellWith('candles', [b]).candleAt(b, 0), { time: 5, open: 1, high: 3, low: 0.5, close: 2 });
  assert.deepEqual(cellWith('bars', [b]).altPoint(b), { time: 5, open: 1, high: 3, low: 0.5, close: 2 });
  assert.deepEqual(cellWith('line', [b]).altPoint(b), { time: 5, value: 2 });
  assert.deepEqual(cellWith('line', [bar(6, 1, 1, 1, 1, { blank: 'lost' })]).altPoint({ tt: 6, blank: 'lost' }), { time: 6 });
});
