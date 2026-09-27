import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const Dom = require('../../homebase/static/charts/dom.js');

const TICK = 0.25;

test('tickIndex / priceOf: exact round trip, and null off bad input', () => {
  assert.equal(Dom.tickIndex(30900.25, TICK), 123601);
  assert.equal(Dom.priceOf(123601, TICK), 30900.25);
  assert.equal(Dom.tickIndex(NaN, TICK), null);
  assert.equal(Dom.tickIndex(30900, 0), null);
  assert.equal(Dom.tickIndex(30900, -1), null);
});

test('tickIndex absorbs float epsilon well under half a tick', () => {
  assert.equal(Dom.tickIndex(30899.999999997, TICK), Dom.tickIndex(30900, TICK));
  assert.equal(Dom.tickIndex(30900.000000004, TICK), Dom.tickIndex(30900, TICK));
  // a price computed with the classic 0.1 + 0.2 float noise still lands on the true row
  assert.equal(Dom.tickIndex(0.1 + 0.2, 0.1), Dom.tickIndex(0.3, 0.1));
});

test('buildRows: 41 rows centred on centerIdx, best price first, exact levels matched', () => {
  const book = { bids: [[30900, 5], [30899.75, 3]], offers: [[30900.25, 4], [30900.5, 2]] };
  const rows = Dom.buildRows(book, TICK, Dom.tickIndex(30900, TICK));
  assert.equal(rows.length, 41);
  assert.equal(rows[0].price, 30905);     // top row: centre + 20 ticks
  assert.equal(rows[rows.length - 1].price, 30895);   // bottom row: centre - 20 ticks
  const at = (p) => rows.find((r) => r.price === p);
  assert.equal(at(30900).bid, 5);
  assert.equal(at(30900).bestBid, true);
  assert.equal(at(30899.75).bid, 3);
  assert.equal(at(30899.75).bestBid, false);
  assert.equal(at(30900.25).ask, 4);
  assert.equal(at(30900.25).bestAsk, true);
  assert.equal(at(30900.5).ask, 2);
  assert.equal(at(30900.5).bestAsk, false);
});

test('buildRows: a gap in the book is blank, never a manufactured zero', () => {
  // liquidity walked away from 30899.75 and 30899.5: only 30900 and 30899.25 are quoted
  const book = { bids: [[30900, 5], [30899.25, 2]], offers: [] };
  const rows = Dom.buildRows(book, TICK, Dom.tickIndex(30900, TICK));
  const at = (p) => rows.find((r) => r.price === p);
  assert.equal(at(30900).bid, 5);
  assert.equal(at(30899.75).bid, null);   // the gap
  assert.equal(at(30899.5).bid, null);    // the gap
  assert.equal(at(30899.25).bid, 2);
  for (const r of rows) assert.equal(r.ask, null);   // no offers at all: every ask blank
  assert.equal(rows.every((r) => r.bestAsk === false), true);
});

test('buildRows: no book at all -- every row blank, no best-bid/best-ask', () => {
  const rows = Dom.buildRows(null, TICK, Dom.tickIndex(30900, TICK));
  assert.equal(rows.length, 41);
  assert.equal(rows.every((r) => r.bid === null && r.ask === null), true);
  assert.equal(rows.every((r) => !r.bestBid && !r.bestAsk), true);
});

test('buildRows: a malformed level (bad price or size) is dropped, not crashed on', () => {
  const book = { bids: [[30900, 5], ['x', 3], [30899.5, NaN], null], offers: [[30900.25, 2]] };
  const rows = Dom.buildRows(book, TICK, Dom.tickIndex(30900, TICK));
  const at = (p) => rows.find((r) => r.price === p);
  assert.equal(at(30900).bid, 5);
  assert.equal(at(30899.5).bid, null);
});

test('buildRows: levels option narrows the grid', () => {
  const rows = Dom.buildRows(null, TICK, 0, { levels: 2 });
  assert.equal(rows.length, 5);
  assert.deepEqual(rows.map((r) => r.idx), [2, 1, 0, -1, -2]);
});

test('recentring: sticky while the last trade stays in the visible rows', () => {
  const c0 = Dom.tickIndex(30900, TICK);
  assert.equal(Dom.nextCenter(c0, 30905, TICK), c0);            // 20 ticks away: still inside
  assert.equal(Dom.nextCenter(c0, 30900.25, TICK), c0);         // one tick away: inside
  assert.equal(Dom.nextCenter(null, 30900, TICK), c0);          // first trade ever: centres on it
  assert.equal(Dom.nextCenter(c0, NaN, TICK), c0);              // unreadable trade: centre unchanged
});

test('recentring: snaps to the last trade once it leaves the visible rows', () => {
  const c0 = Dom.tickIndex(30900, TICK);
  const away = Dom.tickIndex(30905.5, TICK);   // 22 ticks away: outside the default ±20
  assert.equal(Dom.nextCenter(c0, 30905.5, TICK), away);
  const c1 = Dom.nextCenter(c0, 30905.5, TICK);
  assert.equal(Dom.nextCenter(c1, 30906, TICK), c1);   // now sticky around the new centre (still inside ±20)
});

test('recentring: a narrower grid leaves the visible rows sooner', () => {
  const c0 = 0;
  assert.equal(Dom.nextCenter(c0, Dom.priceOf(2, TICK), TICK, 2), c0);      // exactly at the edge: still inside
  assert.equal(Dom.nextCenter(c0, Dom.priceOf(3, TICK), TICK, 2), 3);       // one past it: recentres
});

test('centerOn: the forced recentre always snaps to the last trade', () => {
  assert.equal(Dom.centerOn(30900.25, TICK), Dom.tickIndex(30900.25, TICK));
  assert.equal(Dom.centerOn(null, TICK), null);
});

test('volumeAtPrice: null with no bars, or bars carrying no footprint at all -- the column is blank', () => {
  assert.equal(Dom.volumeAtPrice(null, TICK), null);
  assert.equal(Dom.volumeAtPrice([], TICK), null);
  assert.equal(Dom.volumeAtPrice([{ o: 1, h: 2, l: 0, c: 1 }, { o: 1 }], TICK), null);   // no .fp anywhere
});

test('volumeAtPrice: sums sell+buy per tick index across every loaded bar', () => {
  const bars = [
    { fp: [[30900, 3, 2], [30900.25, 0, 5]] },
    { fp: [[30900, 1, 1], [30899.75, 4, 0]] },
    { o: 1 },   // a bar with no footprint of its own: skipped, doesn't blank the others
  ];
  const v = Dom.volumeAtPrice(bars, TICK);
  assert.notEqual(v, null);
  assert.equal(v.get(Dom.tickIndex(30900, TICK)), 3 + 2 + 1 + 1);
  assert.equal(v.get(Dom.tickIndex(30900.25, TICK)), 5);
  assert.equal(v.get(Dom.tickIndex(30899.75, TICK)), 4);
  assert.equal(v.has(Dom.tickIndex(30899.5, TICK)), false);   // no prints there: absent, not zero
});

test('volumeAtPrice: a malformed footprint row is dropped, not crashed on', () => {
  const bars = [{ fp: [[30900, 1, 1], ['x', 1, 1], [30900.25, 2]] }];
  const v = Dom.volumeAtPrice(bars, TICK);
  assert.equal(v.get(Dom.tickIndex(30900, TICK)), 2);
  assert.equal(v.has(Dom.tickIndex(30900.25, TICK)), false);   // row.length < 3: dropped
});

test('buildRows: volume column blank end to end when unavailable, filled when it is', () => {
  const noVol = Dom.buildRows(null, TICK, 0, { volume: null });
  assert.equal(noVol.every((r) => r.vol === null), true);
  const bars = [{ fp: [[30900, 2, 3]] }];
  const vol = Dom.volumeAtPrice(bars, TICK);
  const rows = Dom.buildRows(null, TICK, Dom.tickIndex(30900, TICK), { volume: vol });
  const at = (p) => rows.find((r) => r.price === p);
  assert.equal(at(30900).vol, 5);
  assert.equal(at(30900.25).vol, null);   // a price with real volume data available, just none printed here
});
