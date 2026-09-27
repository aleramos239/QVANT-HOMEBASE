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

/* A forced recentre (the Recentre button, or C while the ladder has focus): straight to the last trade's row,
   regardless of whether it already sits in view. null when there is no last trade to centre on. */
function centerOn(lastPrice, tick) { return tickIndex(lastPrice, tick); }

/* Volume at price from the cell's own bars[from..to): each bar's footprint (bar.fp, [[price, sellAtBid,
   buyAtAsk], ...], sent whenever the server's `fp` flag is on -- the default) summed per tick index. null (not a
   Map) when no bar in the range carries footprint data at all -- the whole column is blank, never zeroed; a Map
   with no entry for a price means that price saw no prints, also left blank on the row. */
function addFp(m, bar, tick) {
  for (const row of bar.fp) {
    if (!Array.isArray(row) || row.length < 3) continue;
    const idx = tickIndex(row[0], tick);
    if (idx == null) continue;
    const v = (Number.isFinite(row[1]) ? row[1] : 0) + (Number.isFinite(row[2]) ? row[2] : 0);
    m.set(idx, (m.get(idx) || 0) + v);
  }
}
function volumeAtPrice(bars, tick, from = 0, to = Array.isArray(bars) ? bars.length : 0) {
  if (!Array.isArray(bars) || !bars.length) return null;
  let seen = false;
  const m = new Map();
  for (let i = Math.max(0, from); i < Math.min(to, bars.length); i++) {
    const b = bars[i];
    if (!b || !Array.isArray(b.fp)) continue;
    seen = true;
    addFp(m, b, tick);
  }
  return seen ? m : null;
}
/* `map` (a memo of the closed bars, never mutated) plus the forming bar, as a new Map -- the forming bar is
   replaced in place on every update, so it is added on each paint rather than memoised (review I5). */
function withBar(map, bar, tick) {
  if (!bar || !Array.isArray(bar.fp)) return map;
  const m = new Map(map || []);
  addFp(m, bar, tick);
  return m;
}
/* The session of a bar from its ET wall seconds (bar.t): sessions open at 18:00 ET, so shifting by 6 h puts
   each on one calendar day; Friday's close and Sunday's 18:00 open land on different days (Friday, Monday). */
function sessionKey(etWallS) { return Math.floor((etWallS + 6 * 3600) / 86400); }
/* The index of the first loaded bar in the last bar's session (review 11: Vol is the current session only). */
function sessionStart(bars) {
  const n = Array.isArray(bars) ? bars.length : 0;
  if (!n) return 0;
  const k = sessionKey(bars[n - 1].t);
  let i = n - 1;
  while (i > 0 && sessionKey(bars[i - 1].t) === k) i--;
  return i;
}

/* The DOM toolbar button (review 12): opens the panel onto its tab, or closes it when that tab already shows. */
function toggleTab(state, id) {
  return state.open && state.tab === id ? { open: false, tab: id } : { open: true, tab: id };
}
function pressed(state, id) { return !!state.open && state.tab === id; }
/* The ladder's recentre key while it has focus: a bare C (Ctrl+Space is macOS's input-source switch). */
function isRecentreKey(e) { return !!e && (e.key === 'c' || e.key === 'C') && !e.ctrlKey && !e.metaKey && !e.altKey; }
/* A marker chip's title: its line label and the account(s) it belongs to (review 14). */
function chipTitle(label, legs) {
  const who = [...new Set((legs || []).map((l) => l && l.who).filter(Boolean))];
  return who.length ? `${label} · ${who.join(', ')}` : label;
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
function bigSide(rows, prevSide, threshold, now, fadeMs, tick) {
  const keyOf = (price) => (tick > 0 ? tickIndex(price, tick) : price);   // review 7: the ladder's own key
  const qualifying = new Map();
  for (const r of Array.isArray(rows) ? rows : []) {
    if (Array.isArray(r) && Number.isFinite(r[0]) && Number.isFinite(r[1]) && r[1] >= threshold) {
      qualifying.set(keyOf(r[0]), { price: r[0], size: r[1] });
    }
  }
  const merged = new Map();
  for (const line of Array.isArray(prevSide) ? prevSide : []) {
    if (line && Number.isFinite(line.price) && Number.isFinite(line.since)) {
      merged.set(keyOf(line.price), { price: line.price, size: line.size, since: line.since });
    }
  }
  for (const [k, q] of qualifying) merged.set(k, { price: q.price, size: q.size, since: now });
  const out = [];
  for (const [k, line] of merged) {
    const live = qualifying.has(k);
    const age = live ? 0 : (Number.isFinite(now) ? now - line.since : Infinity);
    if (!live && age >= fadeMs) continue;
    out.push({ idx: k, price: line.price, size: line.size, since: line.since,
      opacity: live ? 1 : Math.max(0, 1 - age / fadeMs) });
  }
  out.sort((a, b) => b.opacity - a.opacity || b.size - a.size);
  return out.slice(0, BIG_CAP);
}

/* The median displayed size over `history` within [now - windowMs, now] -- the caller computes it once per
   root per book (review 8) and hands it to bigLevels as opts.median. */
function medianOf(history, now, windowMs = BIG_WINDOW_MS) { return median(pooledSizes(history, now, windowMs)); }
/* Any line still fading: the overlay keeps repainting on its own clock until none is (review 6). */
function fading(result) {
  return !!result && ['bids', 'offers'].some((s) => Array.isArray(result[s]) && result[s].some((l) => l.opacity < 1));
}

/* The big-order lines for `book` ({bids, offers}: [[price, size], ...] each, best first) given `history`
   (recent books for the same root; order doesn't matter, this function windows it itself). opts: multiple
   (default BIG_MULTIPLE), now (ms; defaults to book.ts), windowMs (default BIG_WINDOW_MS), fadeMs (default
   BIG_FADE_MS), prev (this function's own last return -- {bids, offers} -- omit on the first call for a root),
   tick (key levels by tick index, as the ladder does), median (precomputed: `history` is then not pooled).
   No book, or a history too thin to have a median at all, both mean nothing qualifies. */
function bigLevels(book, history, opts = {}) {
  const multiple = opts.multiple > 0 ? opts.multiple : BIG_MULTIPLE;
  const windowMs = opts.windowMs > 0 ? opts.windowMs : BIG_WINDOW_MS;
  const fadeMs = opts.fadeMs > 0 ? opts.fadeMs : BIG_FADE_MS;
  const now = Number.isFinite(opts.now) ? opts.now : (book && Number.isFinite(book.ts) ? book.ts : 0);
  const prev = opts.prev && typeof opts.prev === 'object' ? opts.prev : {};
  const med = Number.isFinite(opts.median) && opts.median >= 0 ? opts.median : medianOf(history, now, windowMs);
  const threshold = med > 0 ? med * multiple : Infinity;   // no usable median: nothing can qualify
  return {
    bids: bigSide(book && book.bids, prev.bids, threshold, now, fadeMs, opts.tick),
    offers: bigSide(book && book.offers, prev.offers, threshold, now, fadeMs, opts.tick),
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

const api = { LEVELS, tickIndex, priceOf, buildRows, nextCenter, centerOn, volumeAtPrice, withBar, sessionKey,
  sessionStart, toggleTab, pressed, isRecentreKey, chipTitle,
  BIG_WINDOW_MS, BIG_FADE_MS, BIG_CAP, BIG_MULTIPLE, bigLevels, medianOf, fading, imbalance };
if (typeof window !== 'undefined') window.HBDom = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
