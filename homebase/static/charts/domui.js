/* Homebase Charts — HBDomUI: the Level 2 ladder's DOM (2026-09-27 charts-depth plan, Task 1). Hosted in the
   order panel's DOM tab (orderpanel.js); follows the SELECTED chart's root. READ-ONLY: nothing here places,
   drags or cancels anything -- a click on a row does nothing that sends.

   Depth reaches the page as {"type":"depth", root, ts, bids, offers} over the existing /ws socket (app.js's
   routing hands it to onDepth), the top levels each side, a null ts meaning the book is gone. This file keeps
   the latest book per root (so switching charts doesn't lose what was already streamed) and asks HBDom (the
   pure half) to turn the book plus the cell's own last trade into rows on the tick grid.

   Repaint discipline: every event (a depth message, a selection change, a quote) only sets a dirty flag; a
   single interval actually patches the DOM, at most once every PAINT_MIN_MS (<= 10 fps). The 41 row elements
   are built once per centre (a rare, structural change -- a recentre) and reused after that: a normal paint
   only rewrites their text, classes and marker chips in place, never rebuilds the ladder. Browser only. */
(() => {
'use strict';
const Dom = window.HBDom;
const Cat = window.HBCatalog;
const T = window.HBTrade;
const D = () => window.HBDeskClient;

const PAINT_MIN_MS = 100;   // <= 10 fps

let page = null;
let container = null;
let ui = null;                                 // built once
let visible = false;                           // the DOM tab is open and showing
let cur = { cell: null, root: null, tick: 0.25 };
let center = null;                             // the ladder's own centre tick index (sticky; HBDom.nextCenter)
let gridCenter = null;                         // the centre the current row elements were built for
const rowEls = new Map();                      // tick index -> {row, bid, priceText, mkWrap, ask, vol}
const seenRoot = new Set();                    // roots we've received at least one depth message for
const books = new Map();                       // root -> the latest {type, root, ts, bids, offers}
let volCache = { bars: null, len: -1, tick: null, start: -1, closed: null };
let dirty = false;

/* ---- small helpers ---- */
function mkEl(tag, cls, text) { return page.mk(tag, cls, text); }
function currentLast() {
  const q = D().quotes[cur.root];
  return q && Number.isFinite(q.last) ? q.last : null;
}
/* The current session's volume at price (review 11), the forming bar included (review I5): the closed bars of
   the session are memoised on the bars array + its length + the session start; the forming bar -- replaced in
   place on every update -- is added onto a copy at each paint. */
function volumeFor(cell, tick) {
  const bars = cell.bars, n = bars.length;
  if (!n) return null;
  const start = Dom.sessionStart(bars);
  if (!(volCache.bars === bars && volCache.len === n && volCache.tick === tick && volCache.start === start)) {
    volCache = { bars, len: n, tick, start, closed: Dom.volumeAtPrice(bars, tick, start, n - 1) };
  }
  return Dom.withBar(volCache.closed, bars[n - 1], tick);
}

/* ---- build (once) ---- */
function buildRowEl(idx) {
  const row = mkEl('div', 'dom-row');
  row.dataset.idx = String(idx);
  const bid = mkEl('span', 'dom-c dom-bid');
  const priceText = mkEl('span', 'dom-px');
  const mkWrap = mkEl('span', 'dom-mk');
  const price = mkEl('span', 'dom-c dom-price');
  price.append(priceText, mkWrap);
  const ask = mkEl('span', 'dom-c dom-ask');
  const vol = mkEl('span', 'dom-c dom-vol');
  row.append(bid, price, ask, vol);
  return { row, bid, priceText, mkWrap, ask, vol };
}
function build() {
  ui = {};
  ui.wrap = mkEl('div', 'dom-wrap');

  ui.head = mkEl('div', 'dom-head');
  ui.recentre = mkEl('button', 'dom-recentre');
  ui.recentre.type = 'button';
  ui.recentre.title = 'Recentre on the last trade (C while the ladder has focus)';
  ui.recentre.append(page.icon('crosshair'), mkEl('span', '', 'Recentre'));
  ui.recentre.onclick = forceRecentre;
  ui.head.append(mkEl('span', 'dom-spacer'), ui.recentre);

  ui.cols = mkEl('div', 'dom-cols');
  ui.cols.append(mkEl('span', 'dom-c', 'Bid'), mkEl('span', 'dom-c', 'Price'), mkEl('span', 'dom-c', 'Ask'), mkEl('span', 'dom-c', 'Vol'));

  ui.rows = mkEl('div', 'dom-rows');
  ui.rows.tabIndex = 0;
  ui.rows.setAttribute('role', 'group');
  ui.rows.setAttribute('aria-label', 'Level 2 ladder');
  ui.rows.addEventListener('pointerdown', () => ui.rows.focus());
  ui.rows.addEventListener('keydown', onKeydown);

  ui.idle = mkEl('div', 'dom-idle');

  ui.wrap.append(ui.head, ui.cols, ui.rows, ui.idle);
  container.replaceChildren(ui.wrap);
}

/* ---- the recentre shortcut: C, only while the ladder itself has focus (a keydown on ui.rows or a descendant --
   never the app-wide document listener, so the symbol box's type-to-search never sees it), and never while a
   dialog owns the keyboard. Not Ctrl+Space: macOS takes it for the input-source switch (review 12). ---- */
function onKeydown(e) {
  if (!Dom.isRecentreKey(e)) return;
  if (page.dialogOpen && page.dialogOpen()) return;
  e.preventDefault();
  e.stopPropagation();
  forceRecentre();
}
function forceRecentre() {
  const last = currentLast();
  if (last == null) return;
  center = Dom.centerOn(last, cur.tick);
  dirty = true;
}

/* ---- inputs: app.js's ws routing and orderpanel.js's own paint feed these; every one just marks dirty ---- */
function onDepth(m) {
  if (!m || typeof m.root !== 'string') return;
  seenRoot.add(m.root);
  books.set(m.root, m);
  if (m.root === cur.root) dirty = true;
}
/* The selected chart, called every orderpanel paint (cheap: it only updates what we track). A new root/symbol
   starts the ladder's own centre over, so a stale centre from the last chart never leaks into this one. */
function sync(cell) {
  const root = cell && cell.shown ? cell.shown.root : null;
  const tick = cell ? cell.tick : 0.25;
  if (root !== cur.root) { center = null; gridCenter = null; }
  cur = { cell, root, tick };
  dirty = true;
}
/* The page's /ws dropped (review 13): every book is stale until the new socket's greeting brings it back. */
function onDisconnect() {
  for (const [root, m] of books) books.set(root, { ...m, ts: null });
  dirty = true;
}
function setVisible(v) {
  v = !!v;
  if (v === visible) return;
  visible = v;
  if (v) dirty = true;
}

/* ---- paint: idle text or the grid; the grid patches its 41 rows in place, rebuilding them only when the
   centre itself moves (a recentre) ---- */
function showIdle(text) {
  ui.idle.textContent = text;
  ui.idle.hidden = false;
  ui.cols.hidden = true;
  ui.rows.hidden = true;
}
function showGrid() {
  ui.idle.hidden = true;
  ui.cols.hidden = false;
  ui.rows.hidden = false;
}
function markerChip(g) {
  const kind = g.kind === 'position' ? 'pos' : g.kind;   // 'pos' | 'sl' | 'tp' | 'order'
  const side = g.side === 'Buy' ? 'buy' : 'sell';
  const chip = mkEl('span', `dom-chip dom-chip-${kind} dom-chip-${side}`, String(g.qty));
  chip.title = Dom.chipTitle(T.lineLabel(g), g.legs);   // names the account(s): "LONG 2 · …047" (review 14)
  return chip;
}
function paintRows(rows, tick, groups) {
  if (gridCenter !== center) {
    ui.rows.replaceChildren();
    rowEls.clear();
    for (const r of rows) { const e = buildRowEl(r.idx); rowEls.set(r.idx, e); ui.rows.appendChild(e.row); }
    gridCenter = center;
  }
  const markers = new Map();   // tick index -> groups at that price
  for (const g of groups) {
    const idx = Dom.tickIndex(g.price, tick);
    if (idx == null) continue;
    let list = markers.get(idx);
    if (!list) { list = []; markers.set(idx, list); }
    list.push(g);
  }
  for (const r of rows) {
    const e = rowEls.get(r.idx);
    if (!e) continue;
    e.row.classList.toggle('best-bid', r.bestBid);
    e.row.classList.toggle('best-ask', r.bestAsk);
    e.bid.textContent = r.bid == null ? '' : Cat.fmtCompact(r.bid);
    e.priceText.textContent = Cat.fmtPrice(r.price, tick);
    e.ask.textContent = r.ask == null ? '' : Cat.fmtCompact(r.ask);
    e.vol.textContent = r.vol == null ? '' : Cat.fmtCompact(r.vol);
    e.mkWrap.replaceChildren(...(markers.get(r.idx) || []).map(markerChip));
  }
}
function paint() {
  const { cell, root, tick } = cur;
  if (!cell) return showIdle('No chart selected');
  if (!root) return showIdle('Loading the chart…');
  if (!seenRoot.has(root)) return showIdle(`No Level 2 for ${root}`);
  const book = books.get(root);
  if (!book || book.ts == null) return showIdle('Book stale');
  center = Dom.nextCenter(center, currentLast(), tick);
  if (center == null) {   // no trade yet at all: seed the centre from the book's own touch
    const seed = (book.bids && book.bids[0] && book.bids[0][0]) ?? (book.offers && book.offers[0] && book.offers[0][0]) ?? null;
    center = seed != null ? Dom.tickIndex(seed, tick) : null;
  }
  if (center == null) return showIdle('Book stale');
  showGrid();
  const volume = volumeFor(cell, tick);
  const rows = Dom.buildRows(book, tick, center, { volume });
  const groups = T.linesFor(D().state, root, []);
  paintRows(rows, tick, groups);
}

function mount(el, pg) {
  container = el;
  page = pg;
  build();
  setInterval(() => { if (dirty) { dirty = false; if (visible) paint(); } }, PAINT_MIN_MS);
}

window.HBDomUI = { mount, sync, setVisible, onDepth, onDisconnect };
})();
