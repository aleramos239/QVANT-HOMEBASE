/* Homebase Charts — HBL2Layer: big-order lines + the imbalance gauge (2026-09-27 charts-l2-news-ui plan,
   Task 2), one overlay per chart (rebuilt with it, like every host.overlays() entry — HBTradeLines and
   HBTesterLayer are the sibling patterns):
     - "bigorders": a labelled horizontal price line per level whose displayed size cleared its multiple x the
       median size over the last 60 s of books for that root (HBDom.bigLevels), fading out over 5 s once a
       level falls below the threshold or leaves the book, at most 8 lines per side;
     - "imbalance": a small bar + signed percentage (HBDom.imbalance) appended to that indicator's own legend
       row, blue for bid-heavy, red for ask-heavy.
   Both are per chart, on only while their indicator is on the chart, and draw nothing without a live book.
   Depth reaches the page as {"type":"depth", root, ts, bids, offers} over the existing /ws socket — the same
   message app.js already hands to HBDomUI.onDepth for the ladder (Task 1). This file keeps its own tiny
   per-root store (the latest book, plus a ~60 s+ history of past books for the median) fed by the SAME
   onDepth call site in app.js: no new subscription, no new socket.
   Repaint discipline: a depth message only sets a dirty flag; each overlay's own interval (<= PAINT_HZ)
   patches its price lines and legend badge in place — it never rebuilds the chart or the legend rows. Browser
   only: the median/threshold/fade/imbalance math lives in dom.js (Node-tested with an injected clock). */
(() => {
'use strict';
const Dom = window.HBDom;
const Cat = window.HBCatalog;

const PAINT_MIN_MS = 200;      // <= 5 fps: comfortably inside "at most 10 fps", plenty smooth for a 5 s fade
const HISTORY_MS = Dom.BIG_WINDOW_MS + 5000;   // a small margin over the 60 s window so pruning can lag safely

const books = new Map();       // root -> latest {ts, bids, offers} (ts null / message absent: no depth)
const history = new Map();     // root -> [{ts, bids, offers}, ...] pruned to ~HISTORY_MS
const offsets = new Map();     // root -> book.ts - Date.now() at arrival: the fade clock between books
const medians = new Map();     // root -> {ts, value}: the median once per root per book (review 8)
const overlays = new Set();    // live Overlay instances, so one depth message can mark every one dirty

/* The shared entry point app.js's ws routing calls, right alongside HBDomUI.onDepth — same message, same
   {"type":"depth", root, ts, bids, offers} shape (depth.py's docstring). A null ts (the book is gone) clears
   this root's book and history; a malformed message is dropped, never throws. */
function onDepth(m) {
  if (!m || typeof m.root !== 'string') return;
  if (m.ts == null) { books.delete(m.root); history.delete(m.root); medians.delete(m.root); }
  else {
    const snap = { ts: m.ts, bids: m.bids, offers: m.offers };
    books.set(m.root, snap);
    offsets.set(m.root, m.ts - Date.now());
    let h = history.get(m.root);
    if (!h) { h = []; history.set(m.root, h); }
    h.push(snap);
    const cutoff = m.ts - HISTORY_MS;
    while (h.length && h[0].ts < cutoff) h.shift();
  }
  for (const ov of overlays) if (ov.root === m.root) ov.dirty = true;
}
/* The page's /ws dropped: every book is gone (the server greets the new socket with the current ones). */
function onDisconnect() {
  books.clear(); history.clear(); medians.clear();
  for (const ov of overlays) ov.dirty = true;
}
function medianFor(root, book) {
  const m = medians.get(root);
  if (m && m.ts === book.ts) return m.value;
  const value = Dom.medianOf(history.get(root) || [], book.ts);
  medians.set(root, { ts: book.ts, value });
  return value;
}
/* Now on the book's clock: the last book's ts plus the wall time since it arrived (a quiet book still fades). */
function bookNow(root, book) { return offsets.has(root) ? Date.now() + offsets.get(root) : book.ts; }

function hexToRgba(hex, alpha) {
  const h = String(hex).replace('#', '');
  const full = h.length === 3 ? h.split('').map((c) => c + c).join('') : h;
  const n = parseInt(full, 16) || 0;
  return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${Math.max(0, Math.min(1, alpha))})`;
}

function findIndicator(cell, id) {
  return (cell.cfg.indicators || []).find((x) => x.id === id && x.visible !== false) || null;
}

class Overlay {
  constructor(cell) {
    this.cell = cell;
    this.dead = false;
    this.root = cell.shown ? cell.shown.root : cell.cfg.root;
    this.dirty = true;
    this.lines = { bids: [], offers: [] };     // bigLevels' own last return, threaded back in as opts.prev
    this.priceLines = new Map();               // "bids:tickIdx" | "offers:tickIdx" -> the LWC price-line handle
    this.badge = null;                         // {wrap, bar, pct}, once built
    this.badgeUid = null;                      // the 'imbalance' instance uid it was built for
    overlays.add(this);
    // a depth message marks it dirty; a line still fading repaints on this clock alone (review 6)
    this.timer = setInterval(() => {
      if (this.dead || !(this.dirty || Dom.fading(this.lines))) return;
      this.dirty = false;
      this.paint();
    }, PAINT_MIN_MS);
    this.paint();   // an already-streaming root (switching charts, adding the indicator) shows at once
  }

  paint() {
    if (this.dead || !this.cell.chart) return;
    const cell = this.cell;
    this.root = cell.shown ? cell.shown.root : cell.cfg.root;
    // Bar Replay (review I4): a replaying chart shows another date -- the live book is never drawn on it
    const book = this.root && !cell.replay ? books.get(this.root) : null;
    this.paintBigLines(cell, book);
    this.paintImbalance(cell, book);
  }

  /* ---- big-order lines ---- */
  paintBigLines(cell, book) {
    const inst = findIndicator(cell, 'bigorders');
    if (!inst || !book) { this.clearLines(); this.lines = { bids: [], offers: [] }; return; }
    const result = Dom.bigLevels(book, null, { multiple: inst.params.multiple, now: bookNow(this.root, book),
      prev: this.lines, tick: cell.tick, median: medianFor(this.root, book) });
    this.lines = { bids: result.bids, offers: result.offers };
    this.syncLines(cell);
  }

  syncLines(cell) {
    if (!cell.candles) return;
    const P = cell.P || {};
    const wanted = new Map();
    for (const side of ['bids', 'offers']) {
      const color = side === 'bids' ? (P.accent || '#2962FF') : (P.down || '#F23645');
      for (const line of this.lines[side]) wanted.set(`${side}:${line.idx}`, { ...line, color });   // tick index (review 7)
    }
    for (const [key, pl] of [...this.priceLines]) {
      if (!wanted.has(key)) { cell.candles.removePriceLine(pl); this.priceLines.delete(key); }
    }
    for (const [key, w] of wanted) {
      const title = `${Cat.fmtCompact(w.size)} @ ${Cat.fmtPrice(w.price, cell.tick)}`;
      const color = hexToRgba(w.color, Math.max(0.15, w.opacity));
      let pl = this.priceLines.get(key);
      if (!pl) {
        pl = cell.candles.createPriceLine({ price: w.price, color, lineWidth: 1, lineStyle: 0, axisLabelVisible: true, title });
        this.priceLines.set(key, pl);
      } else {
        pl.applyOptions({ price: w.price, color, title });
      }
    }
  }

  clearLines() {
    if (this.cell.candles) for (const pl of this.priceLines.values()) this.cell.candles.removePriceLine(pl);
    this.priceLines.clear();
  }

  /* ---- the imbalance gauge: a badge appended to its own legend row, left alone by cell.js's own per-bar
     legend repaint (that only ever replaces .lg-vals' children, never the row itself) ---- */
  paintImbalance(cell, book) {
    const inst = findIndicator(cell, 'imbalance');
    const row = inst && cell.rows ? cell.rows.find((r) => r.inst.uid === inst.uid) : null;
    if (!inst || !book || !row) { this.removeBadge(); return; }
    this.ensureBadge(row);
    const im = Dom.imbalance(book);
    const pct = Math.round(im.pct);
    this.badge.pct.textContent = `${pct > 0 ? '+' : ''}${pct}%`;
    this.badge.pct.className = 'l2-imb-pct' + (im.side ? ` ${im.side}` : '');
    this.badge.bar.className = 'l2-imb-bar' + (im.side ? ` ${im.side}` : '');
    this.badge.bar.style.width = `${Math.min(100, Math.abs(pct))}%`;
  }

  ensureBadge(row) {
    if (this.badge && this.badgeUid === row.inst.uid && row.row.contains(this.badge.wrap)) return;
    this.removeBadge();
    const wrap = document.createElement('span');
    wrap.className = 'l2-imb';
    const barWrap = document.createElement('span');
    barWrap.className = 'l2-imb-barwrap';
    const bar = document.createElement('span');
    bar.className = 'l2-imb-bar';
    barWrap.appendChild(bar);
    const pct = document.createElement('span');
    pct.className = 'l2-imb-pct';
    wrap.append(barWrap, pct);
    row.row.appendChild(wrap);
    this.badge = { wrap, bar, pct };
    this.badgeUid = row.inst.uid;
  }

  removeBadge() {
    if (this.badge) this.badge.wrap.remove();
    this.badge = null;
    this.badgeUid = null;
  }

  /* Depth-driven only: a new/updated bar changes nothing here (onDepth already marks us dirty). */
  onBars() {}

  destroy() {
    this.dead = true;
    clearInterval(this.timer);
    overlays.delete(this);
    this.clearLines();
    this.removeBadge();
  }
}

function overlay(cell) { return new Overlay(cell); }

const api = { overlay, onDepth, onDisconnect };
if (typeof window !== 'undefined') window.HBL2Layer = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
