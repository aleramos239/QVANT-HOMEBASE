/* Homebase Charts — HBDom: the Level 2 ladder, the pure half (2026-09-27 charts-depth plan, Task 1).
   Book -> rows on a tick-index grid, the recentre rule, and session volume at price from the cell's loaded
   bars. Every price is addressed by its TICK INDEX (Math.round(price / tick)) rather than the float itself, so
   a price a hair off its true multiple of tick (book gaps, accumulated arithmetic) still lands on the right
   row -- the epsilon the grid has to tolerate.
   Read-only: nothing here places, drags or cancels anything. The DOM rendering lives in domui.js; this file
   has no browser globals at load time so the Node tests load it directly. */
(function () {
'use strict';
const need = (name, file) => (typeof window !== 'undefined' && window[name]) || (typeof require === 'function' ? require(file) : null);
const Cat = need('HBCatalog', './catalog.js');

const LEVELS = 20;   // rows each side of the centre row (41 rows total)

/* A price's row on the tick grid: null off a non-finite price or a non-positive tick. Math.round absorbs any
   float slop well under half a tick (a book price computed from ticks, a bar's own arithmetic). */
function tickIndex(price, tick) {
  return Number.isFinite(price) && tick > 0 ? Math.round(price / tick) : null;
}
/* The row's price back out, rounded to the tick's own decimals so 30900.25 stays 30900.25, never …249999998. */
function priceOf(idx, tick) {
  return Number((idx * tick).toFixed(Cat.decimals(tick)));
}

/* [[price, size], ...] -> Map(tick index -> size); a malformed row (bad price, non-finite size) is dropped,
   never carried into the grid as a phantom level. */
function levelMap(levels, tick) {
  const m = new Map();
  for (const row of Array.isArray(levels) ? levels : []) {
    if (!Array.isArray(row)) continue;
    const idx = tickIndex(row[0], tick);
    if (idx == null || !Number.isFinite(row[1])) continue;
    m.set(idx, row[1]);
  }
  return m;
}

/* The ladder's visible rows, `levels` each side of `centerIdx`, best price first (highest to lowest) --
   `book` is {bids, offers} ([[price, size], ...] each, best first) or null/undefined (no book at all: every
   bid/ask blank). A price with no matching level -- a gap in the book, or simply outside its depth -- is
   blank (null), never a manufactured zero. `volume` is a Map(tick index -> size) from volumeAtPrice, or null
   when no volume-at-price data exists at all (the whole column blank, not zeroed). */
function buildRows(book, tick, centerIdx, opts = {}) {
  const levels = opts.levels > 0 ? opts.levels : LEVELS;
  const volume = opts.volume || null;
  const bids = levelMap(book && book.bids, tick), offers = levelMap(book && book.offers, tick);
  const bestBidIdx = book && Array.isArray(book.bids) && book.bids.length ? tickIndex(book.bids[0][0], tick) : null;
  const bestAskIdx = book && Array.isArray(book.offers) && book.offers.length ? tickIndex(book.offers[0][0], tick) : null;
  const rows = [];
  for (let idx = centerIdx + levels; idx >= centerIdx - levels; idx--) {
    rows.push({
      idx,
      price: priceOf(idx, tick),
      bid: bids.has(idx) ? bids.get(idx) : null,
      ask: offers.has(idx) ? offers.get(idx) : null,
      vol: volume ? (volume.has(idx) ? volume.get(idx) : null) : null,
      bestBid: bestBidIdx != null && idx === bestBidIdx,
      bestAsk: bestAskIdx != null && idx === bestAskIdx,
    });
  }
  return rows;
}

/* The centre row after a last-trade update: sticky unless the last trade leaves the ±levels visible rows (or
   there was no centre yet) -- "auto-recentre only when the last trade leaves the visible rows". A last trade
   that can't be read (no quote yet) leaves the centre exactly where it was. */
function nextCenter(prevIdx, lastPrice, tick, levels = LEVELS) {
  const lastIdx = tickIndex(lastPrice, tick);
  if (lastIdx == null) return prevIdx;
  if (prevIdx == null || Math.abs(lastIdx - prevIdx) > levels) return lastIdx;
  return prevIdx;
}

/* A forced recentre (the button, or Ctrl+Space while the ladder has focus): straight to the last trade's row,
   regardless of whether it already sits in view. null when there is no last trade to centre on. */
function centerOn(lastPrice, tick) { return tickIndex(lastPrice, tick); }

/* Session (loaded-range) volume at price from the cell's own bars: each bar's footprint (bar.fp,
   [[price, sellAtBid, buyAtAsk], ...], sent whenever the server's `fp` flag is on -- the default) summed per
   tick index across every loaded bar. null (not a Map) when no loaded bar carries footprint data at all -- the
   whole column is blank, never zeroed; a Map that simply has no entry for a price means that price saw no
   prints across the loaded bars, which is a real, drawable zero-ish blank (also left null on the row). */
function volumeAtPrice(bars, tick) {
  if (!Array.isArray(bars) || !bars.length) return null;
  let seen = false;
  const m = new Map();
  for (const b of bars) {
    if (!b || !Array.isArray(b.fp)) continue;
    seen = true;
    for (const row of b.fp) {
      if (!Array.isArray(row) || row.length < 3) continue;
      const idx = tickIndex(row[0], tick);
      if (idx == null) continue;
      const v = (Number.isFinite(row[1]) ? row[1] : 0) + (Number.isFinite(row[2]) ? row[2] : 0);
      m.set(idx, (m.get(idx) || 0) + v);
    }
  }
  return seen ? m : null;
}

const api = { LEVELS, tickIndex, priceOf, buildRows, nextCenter, centerOn, volumeAtPrice };
if (typeof window !== 'undefined') window.HBDom = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
