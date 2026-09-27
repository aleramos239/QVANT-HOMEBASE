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

/* ---- Task 2: big-order lines + the imbalance gauge (2026-09-27 charts-l2-news-ui plan) ----
   bigLevels pools the displayed sizes across a window of recent books for the same root (the median window),
   then lines up the CURRENT book's levels against multiple x that median. The fade of a level that fell below
   the threshold or vanished from the book is threaded through opts.prev -- this function's own last return --
   so it stays pure: every input (book, history, now, prev) is explicit, nothing is read off a real clock or a
   module-level store. imbalance is a one-shot read of the current book alone, no state. */
const BIG_WINDOW_MS = 60000;   // "the last 60 s of books"
const BIG_FADE_MS = 5000;      // "fade out over 5 s"
const BIG_CAP = 8;             // "at most 8 lines per side"
const BIG_MULTIPLE = 5;        // the catalog's own default

function median(values) {
  if (!values.length) return 0;
  const s = values.slice().sort((a, b) => a - b), mid = s.length >> 1;
  return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
}

/* Every displayed size across `history` ({ts, bids, offers}[], any order) within [now - windowMs, now]. An
   entry with no finite ts, or older than the window, contributes nothing -- "the median window". */
function pooledSizes(history, now, windowMs) {
  const out = [];
  for (const snap of Array.isArray(history) ? history : []) {
    if (!snap || !Number.isFinite(snap.ts)) continue;
    if (Number.isFinite(now) && now - snap.ts > windowMs) continue;
    for (const rows of [snap.bids, snap.offers]) {
      for (const r of Array.isArray(rows) ? rows : []) if (Array.isArray(r) && Number.isFinite(r[1])) out.push(r[1]);
    }
  }
  return out;
}

/* One side (bids or offers): today's qualifying levels (size >= threshold) merged with `prevSide` (this
   function's own last return for that side), so a level that just fell below the threshold or vanished from
   the book keeps fading instead of vanishing at once. `since` is the last moment the level qualified, and its
   `size` freezes at that moment too (a fading line shows the size that earned it the line, not whatever the
   book prints while it decays). A line whose fade has run its full course (age >= fadeMs, never requalified in
   between) is dropped for good. Capped to BIG_CAP, live (opacity 1) lines ahead of fading ones, largest first. */
function bigSide(rows, prevSide, threshold, now, fadeMs) {
  const qualifying = new Map();
  for (const r of Array.isArray(rows) ? rows : []) {
    if (Array.isArray(r) && Number.isFinite(r[0]) && Number.isFinite(r[1]) && r[1] >= threshold) qualifying.set(r[0], r[1]);
  }
  const merged = new Map();
  for (const line of Array.isArray(prevSide) ? prevSide : []) {
    if (line && Number.isFinite(line.price) && Number.isFinite(line.since)) {
      merged.set(line.price, { price: line.price, size: line.size, since: line.since });
    }
  }
  for (const [price, size] of qualifying) merged.set(price, { price, size, since: now });
  const out = [];
  for (const line of merged.values()) {
    const live = qualifying.has(line.price);
    const age = live ? 0 : (Number.isFinite(now) ? now - line.since : Infinity);
    if (!live && age >= fadeMs) continue;
    out.push({ price: line.price, size: line.size, since: line.since, opacity: live ? 1 : Math.max(0, 1 - age / fadeMs) });
  }
  out.sort((a, b) => b.opacity - a.opacity || b.size - a.size);
  return out.slice(0, BIG_CAP);
}

/* The big-order lines for `book` ({bids, offers}: [[price, size], ...] each, best first) given `history`
   (recent books for the same root; order doesn't matter, this function windows it itself). opts: multiple
   (default BIG_MULTIPLE), now (ms; defaults to book.ts), windowMs (default BIG_WINDOW_MS), fadeMs (default
   BIG_FADE_MS), prev (this function's own last return -- {bids, offers} -- omit on the first call for a root).
   No book, or a history too thin to have a median at all, both mean nothing qualifies. */
function bigLevels(book, history, opts = {}) {
  const multiple = opts.multiple > 0 ? opts.multiple : BIG_MULTIPLE;
  const windowMs = opts.windowMs > 0 ? opts.windowMs : BIG_WINDOW_MS;
  const fadeMs = opts.fadeMs > 0 ? opts.fadeMs : BIG_FADE_MS;
  const now = Number.isFinite(opts.now) ? opts.now : (book && Number.isFinite(book.ts) ? book.ts : 0);
  const prev = opts.prev && typeof opts.prev === 'object' ? opts.prev : {};
  const med = median(pooledSizes(history, now, windowMs));
  const threshold = med > 0 ? med * multiple : Infinity;   // no usable median: nothing can qualify
  return {
    bids: bigSide(book && book.bids, prev.bids, threshold, now, fadeMs),
    offers: bigSide(book && book.offers, prev.offers, threshold, now, fadeMs),
    median: med,
  };
}

/* Sigma bid sizes - Sigma ask sizes over the top `n` (default 10) levels each side, signed as a percentage of
   their total. {bid, ask, pct, side}: side is 'bid' (bid-heavy), 'ask' (ask-heavy) or null (flat, including no
   book or no size on either side at all -- "imbalance maths including empty sides"). */
function imbalance(book, n = 10) {
  const sum = (rows) => (Array.isArray(rows) ? rows.slice(0, n) : [])
    .reduce((s, r) => s + (Array.isArray(r) && Number.isFinite(r[0]) && Number.isFinite(r[1]) ? r[1] : 0), 0);
  const bid = sum(book && book.bids), ask = sum(book && book.offers), total = bid + ask;
  const pct = total > 0 ? (bid - ask) / total * 100 : 0;
  return { bid, ask, pct, side: pct > 0 ? 'bid' : pct < 0 ? 'ask' : null };
}

const api = { LEVELS, tickIndex, priceOf, buildRows, nextCenter, centerOn, volumeAtPrice,
  BIG_WINDOW_MS, BIG_FADE_MS, BIG_CAP, BIG_MULTIPLE, bigLevels, imbalance };
if (typeof window !== 'undefined') window.HBDom = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
