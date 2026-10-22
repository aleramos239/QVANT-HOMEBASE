/* Homebase Charts — HBDomUI: the Level 2 ladder's DOM (2026-09-27 charts-depth plan, Task 1). Its own
   floating/dockable panel since the 2026-09-27 panels plan (HBPanelShell owns the chrome; this file only
   fills the container it's handed and follows the SELECTED chart's root on its own, re-resolved every paint
   tick rather than cached, same discipline orderpanel.js uses for its own chart reference). READ-ONLY: nothing
   here places, drags or cancels anything -- a click on a row does nothing that sends.

   Depth reaches the page as {"type":"depth", root, ts, bids, offers} over the existing /ws socket (app.js's
   routing hands it to onDepth), the top levels each side, a null ts meaning the book is gone. This file keeps
   the latest book per root (so switching charts doesn't lose what was already streamed) and asks HBDom (the
   pure half) to turn the book plus the cell's own last trade into rows on the tick grid.

   Repaint discipline: every event (a depth message, a selection change, a quote) only sets a dirty flag; a
   single interval actually patches the DOM, at most once every PAINT_MIN_MS (<= 10 fps). The 41 row elements
   are built once per centre (a rare, structural change -- a recentre) and reused after that: a normal paint
   only rewrites their text, classes and marker chips in place, never rebuilds the ladder. Browser only.

   2026-10-21 columns (orderflow.md §7.2): P/S bid · Sold · Bid · Price · Ask · Bought · P/S ask · Vol. Sold / Bought
   are the sells at the bid / buys at the ask per price since the Reset button (before any: the session); P/S is
   HBDom.pullStack's net pull/stack per side since the same reset. Columns is a per-browser choice. */
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
const rowEls = new Map();                      // tick index -> {row, priceText, mkWrap, c: {column id -> its span}}
const seenRoot = new Set();                    // roots we've received at least one depth message for
const books = new Map();                       // root -> the latest {type, root, ts, bids, offers}
const volCache = { bars: null, len: -1, tick: null, start: -1, closed: null };
const splitCache = { bars: null, len: -1, tick: null, start: -1, closed: null };
const psState = new Map();                     // root -> {base, split0, session}: what the P/S and Sold/Bought columns count from
const COLS_KEY = 'hb_dom_cols';
let cols = loadCols();                         // the visible column ids (HBDom.COLS order)
let dirty = false;

/* ---- small helpers ---- */
function mkEl(tag, cls, text) { return page.mk(tag, cls, text); }
function selectedCell() { const C = window.HBCharts; return C ? C.cells[C.selected] || null : null; }
function currentLast() {
  const q = D().quotes[cur.root];
  return q && Number.isFinite(q.last) ? q.last : null;
}
/* The current session's volume at price (review 11), the forming bar included (review I5): the closed bars of
   the session are memoised on the bars array + its length + the session start; the forming bar -- replaced in
   place on every update -- is added onto a copy at each paint. The chart loads its bars' footprint for this
   (cell.needFootprint); until that history is in the column is blank, never a sum of the few bars that have it.
   splitFor is the same walk keeping the two sides apart (the Sold / Bought and P/S columns). */
function perSession(cache, bars, tick, sum, add) {
  const n = bars.length;
  if (!n) return null;
  const start = Dom.sessionStart(bars);
  if (!(cache.bars === bars && cache.len === n && cache.tick === tick && cache.start === start)) {
    Object.assign(cache, { bars, len: n, tick, start, closed: sum(bars, tick, start, n - 1) });
  }
  return add(cache.closed, bars[n - 1], tick);
}
function volumeFor(cell, tick) {
  cell.needFootprint();
  return cell.has.fp ? perSession(volCache, cell.bars, tick, Dom.volumeAtPrice, Dom.withBar) : null;
}
function splitFor(cell, tick) { return cell.has.fp ? perSession(splitCache, cell.bars, tick, Dom.fpSplit, Dom.withBarSplit) : null; }
function sessionOf(cell) { const n = cell.bars.length; return n ? Dom.sessionKey(cell.bars[n - 1].t) : null; }
/* The P/S and Sold / Bought columns for `root`, both counted from the last Reset (before any: the P/S from the
   first paint of the root, the sales from the session's start); a new session starts both over by itself. The
   pull/stack base is HBDom.pullStack's own last return, kept per root so switching charts loses nothing. */
function columnsFor(root, cell, book, split, tick) {
  if (!split) return { ps: null, sales: null };
  const session = sessionOf(cell);
  let st = psState.get(root);
  if (!st || st.session !== session) { st = { base: null, split0: null, session }; psState.set(root, st); }
  const r = Dom.pullStack(st.base, book, split, tick);
  st.base = r.base;
  return { ps: r.rows, sales: Dom.salesSince(split, st.split0) };
}
function reset() {
  const { cell, root, tick } = cur;
  if (!cell || !root || !cell.has.fp) return;
  psState.set(root, { base: null, split0: splitFor(cell, tick), session: sessionOf(cell) });
  dirty = true;
}
/* The column choice is per browser (localStorage, every access its own try/catch: a private window or cleared site
   data just shows every column for this page). The grid template follows the visible columns. */
function loadCols() { try { return Dom.parseCols(localStorage.getItem(COLS_KEY)); } catch (_) { return Dom.parseCols(null); } }
function saveCols() { try { localStorage.setItem(COLS_KEY, JSON.stringify([...cols])); } catch (_) { /* stays for this page */ } }
function applyCols() {
  const show = (c) => { for (const { id } of Dom.COLS) c[id].hidden = !cols.has(id); };
  show(ui.colEls);
  for (const e of rowEls.values()) show(e.c);
  ui.wrap.setAttribute('style', `--dom-grid: ${Dom.COLS.filter((c) => cols.has(c.id)).map((c) => (c.id === 'price' ? 'minmax(70px, 1fr)' : '1fr')).join(' ')}`);
}
function colsMenu(btn) {
  page.toggleMenu(btn, () => {
    const m = page.openMenu(btn, 'menu-dom-cols');
    for (const { id, label, fixed } of Dom.COLS) {
      if (fixed) continue;
      const on = cols.has(id);
      const b = page.menuItem(label, '', () => { page.closeMenu(); if (on) cols.delete(id); else cols.add(id); saveCols(); applyCols(); }, false);
      const ck = page.icon('check');
      ck.classList.add('menu-ck');
      if (!on) ck.style.visibility = 'hidden';
      b.setAttribute('role', 'menuitemcheckbox');
      b.setAttribute('aria-checked', String(on));
      b.prepend(ck);
      m.appendChild(b);
    }
  });
}

/* ---- build (once) ---- */
function colEls(header) {   // one span per column in HBDom.COLS order: the head's labels, or a row's cells (dom-<id>)
  const c = {};
  for (const { id, label } of Dom.COLS) {
    c[id] = header ? mkEl('span', 'dom-c', label) : mkEl('span', `dom-c dom-${id}`);
    c[id].hidden = !cols.has(id);
  }
  return c;
}
function buildRowEl(idx) {
  const row = mkEl('div', 'dom-row');
  row.dataset.idx = String(idx);
  const c = colEls(false);
  const priceText = mkEl('span', 'dom-px');
  const mkWrap = mkEl('span', 'dom-mk');
  c.price.append(priceText, mkWrap);
  row.append(...Dom.COLS.map(({ id }) => c[id]));
  return { row, priceText, mkWrap, c };
}
function headButton(icon, text, title, onclick) {   // one class for every head button: the apple skin styles .dom-recentre
  const b = mkEl('button', 'dom-recentre');
  b.type = 'button';
  b.title = title;
  b.append(page.icon(icon), mkEl('span', '', text));
  b.onclick = onclick;
  return b;
}
function build() {
  ui = {};
  ui.wrap = mkEl('div', 'dom-wrap');

  ui.head = mkEl('div', 'dom-head');
  ui.colsBtn = headButton('list', 'Columns', 'Which columns the ladder shows', () => colsMenu(ui.colsBtn));
  ui.reset = headButton('history', 'Reset', 'Start the P/S and Sold / Bought columns over from now', reset);
  ui.reset.disabled = true;
  ui.recentre = headButton('crosshair', 'Recentre', 'Recentre on the last trade (C while the ladder has focus)', forceRecentre);
  ui.head.append(mkEl('span', 'dom-spacer'), ui.colsBtn, ui.reset, ui.recentre);

  ui.cols = mkEl('div', 'dom-cols');
  ui.colEls = colEls(true);
  ui.cols.append(...Dom.COLS.map(({ id }) => ui.colEls[id]));

  ui.rows = mkEl('div', 'dom-rows');
  ui.rows.tabIndex = 0;
  ui.rows.setAttribute('role', 'group');
  ui.rows.setAttribute('aria-label', 'Level 2 ladder');
  ui.rows.addEventListener('pointerdown', () => ui.rows.focus());
  ui.rows.addEventListener('keydown', onKeydown);

  ui.idle = mkEl('div', 'dom-idle');

  ui.wrap.append(ui.head, ui.cols, ui.rows, ui.idle);
  applyCols();
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
  const num = (v) => (v == null ? '' : Cat.fmtCompact(v));
  const net = (v) => (v ? (v > 0 ? '+' : '') + Cat.fmtCompact(v) : '');   // a change: signed, and blank at 0 (unknown is blank too)
  for (const r of rows) {
    const e = rowEls.get(r.idx);
    if (!e) continue;
    e.row.classList.toggle('best-bid', r.bestBid);
    e.row.classList.toggle('best-ask', r.bestAsk);
    e.c.bid.textContent = num(r.bid);
    e.priceText.textContent = Cat.fmtPrice(r.price, tick);
    e.c.ask.textContent = num(r.ask);
    e.c.vol.textContent = num(r.vol);
    e.c.psb.textContent = net(r.psBid);
    e.c.psa.textContent = net(r.psAsk);
    e.c.sold.textContent = r.sold ? Cat.fmtCompact(r.sold) : '';
    e.c.bought.textContent = r.bought ? Cat.fmtCompact(r.bought) : '';
    e.mkWrap.replaceChildren(...(markers.get(r.idx) || []).map(markerChip));
  }
}
function paint() {
  const { cell, root, tick } = cur;
  ui.reset.disabled = !(cell && cell.has.fp);   // nothing to count from until the chart carries its footprint
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
  const { ps, sales } = columnsFor(root, cell, book, splitFor(cell, tick), tick);
  const rows = Dom.buildRows(book, tick, center, { volume, ps, sales });
  const groups = T.linesFor(D().state, root, []);
  paintRows(rows, tick, groups);
}

function mount(el, pg) {
  container = el;
  page = pg;
  build();
  // no longer driven by orderpanel.js's own paint (it's a separate panel now): resolve the selected chart
  // itself, on the same cadence, the same way orderpanel.js resolves it fresh rather than caching a reference
  setInterval(() => {
    sync(selectedCell());
    if (dirty) { dirty = false; if (visible) paint(); }
  }, PAINT_MIN_MS);
}

window.HBDomUI = { mount, sync, setVisible, onDepth, onDisconnect };
})();
