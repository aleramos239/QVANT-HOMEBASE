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

/* ---- Task 2: big-order lines + the imbalance gauge ---- */

test('bigLevels: the median window only pools books within the last 60s', () => {
  const history = [
    { ts: -1000, bids: [[100, 100000]], offers: [] },   // well before the window: excluded
    { ts: -900, bids: [[100, 100000]], offers: [] },
    { ts: 500, bids: [[100, 10]], offers: [] },         // inside the window
    { ts: 30000, bids: [[100, 10]], offers: [] },
  ];
  const book = { ts: 60000, bids: [[100, 60]], offers: [] };
  const r = Dom.bigLevels(book, history, { now: 60000, windowMs: 60000 });
  assert.equal(r.median, 10);           // the two out-of-window snapshots never enter the pool
  assert.deepEqual(r.bids.map((l) => l.price), [100]);   // 60 >= 5 x 10
});

test('bigLevels: no history at all -- no median, nothing qualifies whatever the book carries', () => {
  const book = { ts: 0, bids: [[100, 1000000]], offers: [] };
  const r = Dom.bigLevels(book, [], { now: 0 });
  assert.equal(r.median, 0);
  assert.deepEqual(r.bids, []);
});

test('bigLevels: the threshold is exactly multiple x the median -- >= qualifies, just under does not', () => {
  const history = [{ ts: 0, bids: [[100, 10], [101, 10]], offers: [[102, 10], [103, 10]] }];
  const book = { ts: 0, bids: [[100, 50], [101, 49.999]], offers: [[102, 30]] };
  const r = Dom.bigLevels(book, history, { now: 0, multiple: 5 });
  assert.deepEqual(r.bids.map((l) => l.price), [100]);   // 50 >= 5 x 10
  assert.equal(r.offers.length, 0);                      // 30 < 50
});

test('bigLevels: a custom multiple narrows or widens what qualifies', () => {
  const history = [{ ts: 0, bids: [[100, 10]], offers: [] }];
  const book = { ts: 0, bids: [[100, 35]], offers: [] };
  assert.deepEqual(Dom.bigLevels(book, history, { now: 0, multiple: 3 }).bids.map((l) => l.price), [100]);   // 35 >= 3x10
  assert.deepEqual(Dom.bigLevels(book, history, { now: 0, multiple: 5 }).bids, []);                          // 35 < 5x10
});

test('bigLevels: caps at 8 lines per side, the largest kept', () => {
  const history = [{ ts: 0, bids: Array.from({ length: 10 }, (_, i) => [100 + i, 10]), offers: [] }];
  const bids = Array.from({ length: 10 }, (_, i) => [100 + i, 50 + i]);   // 50..59, all >= threshold 50
  const book = { ts: 0, bids, offers: [] };
  const r = Dom.bigLevels(book, history, { now: 0 });
  assert.equal(r.bids.length, 8);
  assert.deepEqual(r.bids.map((l) => l.size), [59, 58, 57, 56, 55, 54, 53, 52]);
});

test('bigLevels: a level that falls below the threshold fades out over 5s, then disappears (injected clock)', () => {
  const history = [{ ts: 0, bids: [[100, 10]], offers: [] }];
  let r = Dom.bigLevels({ ts: 0, bids: [[100, 60]], offers: [] }, history, { now: 0 });
  assert.equal(r.bids.length, 1);
  assert.equal(r.bids[0].opacity, 1);
  r = Dom.bigLevels({ ts: 2000, bids: [[100, 5]], offers: [] }, history, { now: 2000, prev: r });
  assert.equal(r.bids.length, 1);
  assert.ok(r.bids[0].opacity > 0 && r.bids[0].opacity < 1, 'mid-fade');
  r = Dom.bigLevels({ ts: 5000, bids: [[100, 5]], offers: [] }, history, { now: 5000, prev: r });
  assert.equal(r.bids.length, 0);   // 5s after it stopped qualifying: gone
});

test('bigLevels: a level that vanishes from the book fades the same as one that drops below threshold', () => {
  const history = [{ ts: 0, bids: [[100, 10]], offers: [] }];
  let r = Dom.bigLevels({ ts: 0, bids: [[100, 60]], offers: [] }, history, { now: 0 });
  r = Dom.bigLevels({ ts: 4999, bids: [], offers: [] }, history, { now: 4999, prev: r });
  assert.ok(r.bids.length === 1 && r.bids[0].opacity > 0);
  r = Dom.bigLevels({ ts: 5000, bids: [], offers: [] }, history, { now: 5000, prev: r });
  assert.equal(r.bids.length, 0);
});

test('bigLevels: no book at all -- nothing to draw, no crash', () => {
  const r = Dom.bigLevels(null, [{ ts: 0, bids: [[100, 10]], offers: [] }], { now: 0 });
  assert.deepEqual(r.bids, []);
  assert.deepEqual(r.offers, []);
});

test('imbalance: sigma bid - sigma ask over the top 10 levels, signed as a pct of the total', () => {
  const book = { bids: [[100, 30], [99, 20]], offers: [[101, 10], [102, 10]] };
  const im = Dom.imbalance(book);
  assert.equal(im.bid, 50);
  assert.equal(im.ask, 20);
  assert.equal(im.pct, (50 - 20) / 70 * 100);
  assert.equal(im.side, 'bid');
});

test('imbalance: only the top 10 levels count', () => {
  const bids = Array.from({ length: 12 }, () => [100, 1]);
  const im = Dom.imbalance({ bids, offers: [] });
  assert.equal(im.bid, 10);
});

test('imbalance: empty sides -- no book, both sides empty, one side empty', () => {
  assert.deepEqual(Dom.imbalance(null), { bid: 0, ask: 0, pct: 0, side: null });
  assert.deepEqual(Dom.imbalance({ bids: [], offers: [] }), { bid: 0, ask: 0, pct: 0, side: null });
  const askOnly = Dom.imbalance({ bids: [], offers: [[100, 5]] });
  assert.equal(askOnly.bid, 0);
  assert.equal(askOnly.pct, -100);
  assert.equal(askOnly.side, 'ask');
});

test('imbalance: a malformed row is dropped, not crashed on', () => {
  const im = Dom.imbalance({ bids: [[100, 10], ['x', 5], null], offers: [[101, NaN]] });
  assert.equal(im.bid, 10);
  assert.equal(im.ask, 0);
  assert.equal(im.side, 'bid');
});

/* ---- review fix round 1 ---- */
const H = 3600;
test('sessionKey / sessionStart: the session opens at 18:00 ET; a weekend folds into Monday', () => {
  const day = 20000 * 86400;                                   // an ET-wall midnight, in ET wall seconds
  assert.equal(Dom.sessionKey(day + 17 * H), Dom.sessionKey(day - 5 * H));        // 19:00 the evening before
  assert.notEqual(Dom.sessionKey(day + 18 * H), Dom.sessionKey(day + 17 * H));    // 18:00 starts the next one
  const bars = [{ t: day + 9 * H }, { t: day + 16 * H }, { t: day + 18 * H }, { t: day + 20 * H }, { t: day + 24 * H + 9 * H }];
  assert.equal(Dom.sessionStart(bars), 2);                     // 18:00 and 20:00 and the next morning: one session
  assert.equal(Dom.sessionStart([]), 0);
  assert.equal(Dom.sessionStart([{ t: day }]), 0);
});

test('volumeAtPrice: an index range; withBar adds the forming bar onto a copy', () => {
  const bars = [{ fp: [[100, 1, 1]] }, { fp: [[100, 2, 0]] }, { fp: [[100, 0, 5], [100.25, 1, 0]] }];
  const closed = Dom.volumeAtPrice(bars, TICK, 1, 2);          // bars[1] only
  assert.equal(closed.get(Dom.tickIndex(100, TICK)), 2);
  const all = Dom.withBar(closed, bars[2], TICK);
  assert.equal(all.get(Dom.tickIndex(100, TICK)), 7);
  assert.equal(all.get(Dom.tickIndex(100.25, TICK)), 1);
  assert.equal(closed.get(Dom.tickIndex(100, TICK)), 2);        // the memo is never mutated
  assert.equal(Dom.withBar(null, { o: 1 }, TICK), null);        // nothing anywhere: still blank
  assert.equal(Dom.withBar(null, bars[2], TICK).get(Dom.tickIndex(100, TICK)), 5);
  assert.equal(Dom.volumeAtPrice(bars, TICK, 3, 3), null);
});

test('bigLevels: levels are keyed by tick index, so a float hair off the tick is the same line', () => {
  const hist = [{ ts: 0, bids: [[100, 1], [99.75, 1]], offers: [[100.25, 1]] }];
  const first = Dom.bigLevels({ ts: 0, bids: [[100, 10]], offers: [] }, hist, { now: 0, tick: TICK });
  const next = Dom.bigLevels({ ts: 1000, bids: [[100.0000000001, 10]], offers: [] }, hist, { now: 1000, tick: TICK, prev: first });
  assert.equal(next.bids.length, 1);
  assert.equal(next.bids[0].opacity, 1);
  assert.equal(next.bids[0].idx, Dom.tickIndex(100, TICK));
});

test('bigLevels: a precomputed median is used as is (computed once per root per book)', () => {
  const r = Dom.bigLevels({ ts: 0, bids: [[100, 10], [99.75, 9]], offers: [] }, null, { now: 0, tick: TICK, median: 2 });
  assert.deepEqual(r.bids.map((l) => l.price), [100]);          // 10 >= 5 x 2, 9 < 10
  assert.equal(r.median, 2);
  assert.equal(Dom.medianOf([{ ts: 0, bids: [[1, 1], [2, 3]], offers: [[3, 2]] }], 0), 2);
  assert.equal(Dom.fading({ bids: [{ opacity: 1 }], offers: [{ opacity: 0.4 }] }), true);
  assert.equal(Dom.fading({ bids: [{ opacity: 1 }], offers: [] }), false);
  assert.equal(Dom.fading(null), false);
});

test('toggleTab: the DOM button opens onto its tab, and closes the panel when that tab is already showing', () => {
  assert.deepEqual(Dom.toggleTab({ open: false, tab: 'order' }, 'dom'), { open: true, tab: 'dom' });
  assert.deepEqual(Dom.toggleTab({ open: true, tab: 'order' }, 'dom'), { open: true, tab: 'dom' });
  assert.deepEqual(Dom.toggleTab({ open: true, tab: 'dom' }, 'dom'), { open: false, tab: 'dom' });
  assert.equal(Dom.pressed({ open: true, tab: 'dom' }, 'dom'), true);
  assert.equal(Dom.pressed({ open: false, tab: 'dom' }, 'dom'), false);
  assert.equal(Dom.pressed({ open: true, tab: 'order' }, 'dom'), false);
});

test('isRecentreKey: a bare C only (never with a modifier)', () => {
  assert.equal(Dom.isRecentreKey({ key: 'c' }), true);
  assert.equal(Dom.isRecentreKey({ key: 'C', shiftKey: true }), true);
  for (const e of [{ key: 'c', ctrlKey: true }, { key: 'c', metaKey: true }, { key: 'c', altKey: true }, { key: ' ', ctrlKey: true }, { key: 'x' }]) {
    assert.equal(Dom.isRecentreKey(e), false, JSON.stringify(e));
  }
});

test('chipTitle: the line label and the account(s) it belongs to', () => {
  assert.equal(Dom.chipTitle('LONG 2', [{ who: '…047' }, { who: '…047' }]), 'LONG 2 · …047');
  assert.equal(Dom.chipTitle('BUY LMT 1', [{ who: '…047' }, { who: '…045' }]), 'BUY LMT 1 · …047, …045');
  assert.equal(Dom.chipTitle('SL 1', []), 'SL 1');
});

/* ---- 2026-10-21 DOM columns: sales at price, net pull/stack, Sierra's Recent Bid/Ask, the column choice ---- */

test('fpSplit / withBarSplit: sell-at-bid and buy-at-ask kept apart per price; the memo is never mutated', () => {
  const bars = [{ fp: [[100, 1, 1]] }, { fp: [[100, 2, 0]] }, { fp: [[100, 0, 5], [100.25, 1, 0]] }, { o: 1 }];
  const closed = Dom.fpSplit(bars, TICK, 0, 2);
  assert.deepEqual(closed.get(Dom.tickIndex(100, TICK)), [3, 1]);
  const all = Dom.withBarSplit(closed, bars[2], TICK);
  assert.deepEqual(all.get(Dom.tickIndex(100, TICK)), [3, 6]);
  assert.deepEqual(all.get(Dom.tickIndex(100.25, TICK)), [1, 0]);
  assert.deepEqual(closed.get(Dom.tickIndex(100, TICK)), [3, 1]);
  assert.equal(Dom.fpSplit([{ o: 1 }], TICK), null);            // no footprint anywhere: blank, not empty
  assert.equal(Dom.withBarSplit(null, { o: 1 }, TICK), null);
  assert.equal(Dom.fpSplit([{ fp: [[100, 1, 1], ['x', 1, 1], [100.25, 2]] }], TICK).size, 1);   // malformed rows dropped
});

test('salesSince: the split now minus the copy at the reset; a price with no copy started at 0', () => {
  const i = (p) => Dom.tickIndex(p, TICK);
  const split0 = new Map([[i(100), [3, 1]]]);
  const split = new Map([[i(100), [5, 1]], [i(100.25), [0, 2]]]);
  assert.deepEqual([...Dom.salesSince(split, split0)], [[i(100), [2, 0]], [i(100.25), [0, 2]]]);
  assert.deepEqual([...Dom.salesSince(split, null)], [...split]);   // no reset yet: the whole session
  assert.equal(Dom.salesSince(null, split0), null);
});

test('knownRange: the deepest shown level each side, null for an empty side', () => {
  const book = { bids: [[100, 5], [99.75, 3], [99.25, 1]], offers: [[100.25, 4], [100.75, 2]] };
  assert.deepEqual(Dom.knownRange(book, TICK), { bidFrom: Dom.tickIndex(99.25, TICK), askTo: Dom.tickIndex(100.75, TICK) });
  assert.deepEqual(Dom.knownRange({ bids: [], offers: [[100.25, 4]] }, TICK), { bidFrom: null, askTo: Dom.tickIndex(100.25, TICK) });
  assert.deepEqual(Dom.knownRange(null, TICK), { bidFrom: null, askTo: null });
});

test('pullStack (Sierra): the bid at 100 goes 50 -> 40 (-10), then 5 trade there (+5): -5', () => {
  const i = (p) => Dom.tickIndex(p, TICK);
  const offers = [[100.25, 10]];
  let r = Dom.pullStack(null, { bids: [[100, 50]], offers }, null, TICK);
  assert.equal(r.rows.get(i(100)).bid, 0);                      // the first call is the base: nothing has changed yet
  r = Dom.pullStack(r.base, { bids: [[100, 40]], offers }, null, TICK);
  assert.equal(r.rows.get(i(100)).bid, -10);
  r = Dom.pullStack(r.base, { bids: [[100, 40]], offers }, new Map([[i(100), [5, 0]]]), TICK);
  assert.equal(r.rows.get(i(100)).bid, -5);
  assert.equal(r.rows.get(i(100.25)).ask, 0);                   // the ask side has its own column
  assert.equal(r.rows.get(i(100.25)).bid, 0);                   // above the best bid: a known 0, not unknown
});

test('pullStack: a buy at the ask counts for the ask side only; a sell at the bid for the bid side only', () => {
  const i = (p) => Dom.tickIndex(p, TICK);
  const book = { bids: [[100, 10]], offers: [[100.25, 10]] };
  let r = Dom.pullStack(null, book, null, TICK);
  r = Dom.pullStack(r.base, { bids: [[100, 10]], offers: [[100.25, 7]] }, new Map([[i(100.25), [0, 3]], [i(100), [2, 0]]]), TICK);
  assert.equal(r.rows.get(i(100.25)).ask, 0);                   // 3 lifted, 3 less resting: nothing pulled
  assert.equal(r.rows.get(i(100)).bid, 2);                      // 2 hit the bid yet 10 still rest: 2 stacked back
});

test('pullStack: unknown rows are absent (never 0); a row below the deepest shown bid is unknown', () => {
  const i = (p) => Dom.tickIndex(p, TICK);
  const r = Dom.pullStack(null, { bids: [[100, 5], [99.5, 2]], offers: [[100.25, 4]] }, null, TICK);
  assert.equal(r.rows.has(i(99.25)), false);                    // below the deepest shown bid: not tracked at all
  assert.equal(r.rows.get(i(99.75)).bid, 0);                    // a gap between the best and the deepest bid: known empty
  assert.equal(r.rows.get(i(99.75)).ask, 0);                    // no ask can rest below the best ask: a known 0
  assert.equal(r.rows.has(i(101)), false);                      // above the deepest shown ask: nothing tracked yet
  assert.deepEqual(Dom.pullStack(null, null, null, TICK).rows.size, 0);
});

test('pullStack: a level filled into a gap is stacked; one that leaves the known range is dropped and starts over when back', () => {
  const i = (p) => Dom.tickIndex(p, TICK);
  const offers = [[100.25, 4]];
  let r = Dom.pullStack(null, { bids: [[100, 5], [99.5, 2]], offers }, null, TICK);
  r = Dom.pullStack(r.base, { bids: [[100, 5], [99.75, 5], [99.5, 2]], offers }, null, TICK);
  assert.equal(r.rows.get(i(99.75)).bid, 5);                    // +5 into the gap
  r = Dom.pullStack(r.base, { bids: [[100, 5], [99.75, 5]], offers }, null, TICK);   // 99.5 fell off the wire's depth
  assert.equal(r.rows.get(i(99.5)).bid, null);                  // dropped, not read as -2 pulled (the ask side still knows it: 0)
  r = Dom.pullStack(r.base, { bids: [[100, 5], [99.75, 5], [99.5, 9]], offers }, null, TICK);
  assert.equal(r.rows.get(i(99.5)).bid, 0);                     // back in range: a fresh base, not +7
  assert.equal(r.rows.get(i(99.75)).bid, 5);                    // the others keep counting
});

test('pullStack: the best level starts over at 0 when the best price moves; the old best keeps its history', () => {
  const i = (p) => Dom.tickIndex(p, TICK);
  let r = Dom.pullStack(null, { bids: [[100, 5], [99.75, 3]], offers: [[100.25, 4]] }, null, TICK);
  r = Dom.pullStack(r.base, { bids: [[100, 2], [99.75, 3]], offers: [[100.25, 4]] }, null, TICK);
  assert.equal(r.rows.get(i(100)).bid, -3);
  r = Dom.pullStack(r.base, { bids: [[99.75, 9]], offers: [[100, 1], [100.25, 4]] }, null, TICK);   // the bid at 100 is gone
  assert.equal(r.rows.get(i(100)).bid, -5);                     // the old best: all 5 pulled
  assert.equal(r.rows.get(i(99.75)).bid, 0);                    // the new best: starts over (was +6)
  assert.equal(r.rows.get(i(100)).ask, 0);                      // the new best ask: fresh
  assert.equal(r.rows.get(i(100.25)).ask, 0);
});

test('recentTraded (Sierra): back at the price within the timeout keeps counting (3); after it, starts over (1)', () => {
  const i = (p) => Dom.tickIndex(p, TICK);
  const prints = [[0, 1000, 2, -1], [100, 999, 3, -1]];
  let s = Dom.recentTraded(null, prints, { tick: TICK });
  assert.equal(s.bid.get(i(1000)).v, 2);
  assert.equal(s.bid.get(i(999)).v, 3);
  assert.equal(Dom.recentTraded(s, [[2000, 1000, 1, -1]], { tick: TICK }).bid.get(i(1000)).v, 3);   // within 2500 ms
  assert.equal(Dom.recentTraded(s, [[2600, 1000, 1, -1]], { tick: TICK }).bid.get(i(1000)).v, 1);   // after 2500 ms
  assert.equal(Dom.recentTraded(s, [[9000, 1000, 1, -1]], { tick: TICK, timeoutMs: 10000 }).bid.get(i(1000)).v, 3);
  assert.equal(s.bid.get(i(1000)).v, 2);                        // the last state is never mutated
});

test('recentTraded: staying at one price keeps counting however slow; sides are separate; junk prints are skipped', () => {
  const i = (p) => Dom.tickIndex(p, TICK);
  let s = Dom.recentTraded(null, [[0, 1000, 2, -1], [9000, 1000, 1, -1]], { tick: TICK });
  assert.equal(s.bid.get(i(1000)).v, 3);                        // the market never traded elsewhere
  s = Dom.recentTraded(s, [[9100, 1000.25, 4, 1], [9200, 1000.25, 1, 1], ['x'], null, [9300, NaN, 1, 1]], { tick: TICK });
  assert.equal(s.ask.get(i(1000.25)).v, 5);
  assert.equal(s.bid.has(i(1000.25)), false);
  assert.equal(s.lastAsk, i(1000.25));
  assert.equal(s.lastBid, i(1000));
  assert.equal(Dom.recentTraded(null, [[0, 1000, 2, -1]]).bid.get(1000).v, 2);   // no tick: keyed by the price itself
});

test('buildRows: no opts -- the rows are exactly what they were (no new fields)', () => {
  const book = { bids: [[30900, 5]], offers: [[30900.25, 4]] };
  const rows = Dom.buildRows(book, TICK, Dom.tickIndex(30900, TICK), { levels: 1 });
  assert.deepEqual(rows, [
    { idx: 123601, price: 30900.25, bid: null, ask: 4, vol: null, bestBid: false, bestAsk: true },
    { idx: 123600, price: 30900, bid: 5, ask: null, vol: null, bestBid: true, bestAsk: false },
    { idx: 123599, price: 30899.75, bid: null, ask: null, vol: null, bestBid: false, bestAsk: false },
  ]);
});

test('buildRows: ps and sales fill psBid/psAsk/sold/bought, null where the row is unknown', () => {
  const i = (p) => Dom.tickIndex(p, TICK);
  const ps = new Map([[i(30900), { bid: -5, ask: null }], [i(30900.25), { bid: 0, ask: 2 }]]);
  const sales = new Map([[i(30900), [7, 1]]]);
  const rows = Dom.buildRows(null, TICK, i(30900), { levels: 1, ps, sales });
  const at = (p) => rows.find((r) => r.price === p);
  assert.deepEqual([at(30900).psBid, at(30900).psAsk, at(30900).sold, at(30900).bought], [-5, null, 7, 1]);
  assert.deepEqual([at(30900.25).psBid, at(30900.25).psAsk, at(30900.25).sold], [0, 2, null]);
  assert.deepEqual([at(30899.75).psBid, at(30899.75).psAsk, at(30899.75).sold, at(30899.75).bought], [null, null, null, null]);
});

test('COLS / parseCols: the column order, and the saved choice (fixed columns always on, junk = every column)', () => {
  assert.deepEqual(Dom.COLS.map((c) => c.label), ['P/S bid', 'Sold', 'Bid', 'Price', 'Ask', 'Bought', 'P/S ask', 'Vol']);
  assert.deepEqual([...Dom.parseCols(null)], Dom.COLS.map((c) => c.id));
  assert.deepEqual([...Dom.parseCols('{')], Dom.COLS.map((c) => c.id));
  assert.deepEqual([...Dom.parseCols('["vol"]')], ['bid', 'price', 'ask', 'vol']);
  assert.deepEqual([...Dom.parseCols('[]')], ['bid', 'price', 'ask']);
});
