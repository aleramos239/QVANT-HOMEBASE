/* Homebase Charts — the page: layout and selection, the top toolbar (it
   acts on the selected chart), menus, the drawing rail (the tool, the
   magnet and the per-symbol drawings store), the websocket to the chart
   service (:8852) and the bottom bar. Each grid slot is an HBCell.Cell;
   the server computes everything, the page only draws. */
(() => {
'use strict';
const C = window.HBCatalog, I = window.HBIcons, S = window.HBSettings, T = window.HBTrade, { Cell, badgeEl } = window.HBCell;
const DS = window.HBDrawStyle;
const GRIDS = { 1: [1, 1], 2: [2, 1], 4: [2, 2], 6: [3, 2] };
const GRID_NAMES = { 1: '1 chart', 2: '2 charts side by side', 4: '2 × 2 charts', 6: '3 × 2 charts' };
const STATUS_STALE_S = 6;   // the server sends a status every 2 s: this long without one = it is stuck
const START = [['NQ', 'time:60'], ['NQ', 'time:300'], ['ES', 'time:60'], ['YM', 'time:60'], ['NQ', 'tick:1000'], ['NQ', 'time:900']];
const ET_CLOCK = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit',
  second: '2-digit', hourCycle: 'h23' });
const ET_PARTS = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', weekday: 'short', hour: '2-digit',
  minute: '2-digit', hourCycle: 'h23' });
const WEEKDAY = { Sun: 0, Mon: 1, Tue: 2, Wed: 3, Thu: 4, Fri: 5, Sat: 6 };
function etNow() {
  const p = Object.fromEntries(ET_PARTS.formatToParts(new Date()).map((x) => [x.type, x.value]));
  return { weekday: WEEKDAY[p.weekday], minutes: +p.hour * 60 + +p.minute };
}

let meta = { roots: ['NQ'], timeframes: [] };
let ws = null;
let layout = { grid: 4, cells: [], name: '', dirty: false };
let cells = [];
let selected = 0;
let nextId = 1;
let statusAt = 0, statusLine = '';
let menuEl = null, menuAnchor = null;
let customWait = null;   // {cell, spec, err}: a custom interval sent from the open interval menu, awaiting the server
let dlg = null;   // the open dialog: {back, box, focus}
let tool = 'cursor';
let noteTimer = 0, armTimer = 0, armRoot = null;   // armRoot: the symbol the armed remove-all names
const drawings = new window.HBDrawings.Store({ onError: (root, msg) => sbNote(`${root} drawings: ${msg}`) });
let magnet = loadMagnet();   // the rail's magnet {on, mode}, per viewer (localStorage hb_charts_magnet)
let menuRight = false;       // the open menu is a rail flyout: it opens to the right of its button
let menuAt = null;   // the open menu is a context menu at this viewport point {x, y}
let replayClock = null;   // {etMs, at, speed, done}: a replay's clock from its last status (live: null)
let calendar = [];   // every stored calendar event (GET /api/calendar), by time
let calendarAt;   // the service's calendar.fetched_at they came with (undefined: never loaded)
let hotkeyBox = null;   // {el, input, kind: 'tf' | 'sym'}: the floating timeframe or symbol-search box a bare keypress opened
let page = null;   // the page interface handed to the trading/tester modules (menus, dialogs, overlays); set in init()
let lastRaw = [];  // the cells exactly as hb_charts_last stored them (the one-time ticked-list migration reads them)

const $ = (s, root = document) => root.querySelector(s);
const iso = (t) => new Date(t * 1000).toISOString();
function mk(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function icon(name) { const s = mk('span', 'icw'); s.innerHTML = I[name] || ''; return s; }   // our own static SVG strings
function button(cls, text) { const b = mk('button', cls, text); b.type = 'button'; return b; }
const cur = () => cells[selected];

/* ---- layout + selection ---- */
function starter(i) {
  const [root, spec] = START[i % START.length];
  return { root, spec, indicators: C.defaults(), trade: { accounts: [] }, algo: null };   // a fresh chart places no new entries
}
function saveLast() { try { localStorage.setItem('hb_charts_last', JSON.stringify(layout)); } catch (_) { /* storage off */ } }
/* Anything that changes a chart outside the Settings dialog's own commit (Ok already marks dirty itself) reads
   the layout as Unsaved the same way: a template apply, removing a chart's indicators, or moving one between
   the price pane and its own — like editing anything else in the layout. */
function markDirty() { layout.dirty = true; saveLast(); renderToolbar(); }

/* The legend's collapse chevron (user request): a per-viewer preference, never part of the saved layout, so
   it lives in its own localStorage key, keyed by the chart's current grid position -- not cell.js, which
   knows nothing of the grid or localStorage. Every access is its own try/catch: a private window, cleared
   site data or a blocked store must not break the legend. */
const LEGEND_FOLD_KEY = 'hb_charts_legend_folded';
function readLegendFold() {
  try { return window.HBChartMenu.readFolded(localStorage.getItem(LEGEND_FOLD_KEY)); } catch (_) { return {}; }
}
function legendFolded(cell) {
  try { return window.HBChartMenu.isFolded(readLegendFold(), cells.indexOf(cell)); } catch (_) { return false; }
}
function toggleLegendFolded(cell) {
  const i = cells.indexOf(cell), map = window.HBChartMenu.toggleFolded(readLegendFold(), i);
  try { localStorage.setItem(LEGEND_FOLD_KEY, JSON.stringify(map)); } catch (_) { /* storage off: this session only */ }
  return window.HBChartMenu.isFolded(map, i);
}
function loadLast() {
  try {
    const v = JSON.parse(localStorage.getItem('hb_charts_last') || 'null');
    if (v && Array.isArray(v.cells)) {
      layout = { ...readLayout(v), name: typeof v.name === 'string' ? v.name : '', dirty: v.dirty === true };
      lastRaw = v.cells;
    }
  } catch (_) { /* unreadable: start fresh */ }
}

/* A saved layout (localStorage or the server) as the page runs it: HBCatalog.migrateLayout gives each chart's
   {root, spec, indicators}; each chart's settings (HBSettings overrides, cleaned) are kept beside them, and its
   trade accounts and algo. EVERY load goes through HBTrade.loadedTrade: DEMO and PAPER accounts come back, a
   LIVE one NEVER does (2026-09-27 accounts-per-chart plan, Global Constraints). A load usually runs before the
   desk has said which accounts are live, so dropLiveAccounts() below re-runs the drop the moment its list
   arrives -- and `pendingDroppedLive` carries what this load already dropped into the one notice. */
let pendingDroppedLive = [];
function readLayout(v) {
  const lay = C.migrateLayout(v), raw = v && Array.isArray(v.cells) ? v.cells : [];
  const st = deskState();
  lay.cells.forEach((c, i) => {
    const r = raw[i] && typeof raw[i] === 'object' ? raw[i] : {};
    const s = r.settings, o = S.overrides(s && typeof s === 'object' ? s : {});
    if (Object.keys(o).length) c.settings = o;
    const t = T.loadedTrade(r.trade, st);
    c.trade = { accounts: t.accounts };
    c.unverified = t.unverified;   // what the desk has not vouched for yet: dropped if it turns out LIVE
    pendingDroppedLive.push(...t.droppedLive);
    c.algo = T.cellAlgo(r.algo);
  });
  return lay;
}
const deskState = () => (window.HBDeskClient && window.HBDeskClient.state) || null;
/* Global Constraints: no load ever leaves a LIVE account on a chart. A load marks what it kept without the
   desk's word as UNVERIFIED on that chart (fix round 1, Critical 1); this checks ONLY those marks, over every
   chart config in the layout (visible ones are the same objects as their cells' cfg), whenever the desk's list
   changes. An account the user ticked and armed in the Trading tab is never marked, so no balance tick can
   take it away. Says so once, naming the accounts. */
function dropLiveAccounts() {
  const st = deskState();
  if (!st) return;
  const dropped = [...pendingDroppedLive];
  pendingDroppedLive = [];
  const v = T.verifyCells(layout.cells, st);
  dropped.push(...v.dropped);
  for (const i of v.changed) if (cells[i]) window.HBTradeUI.setCellTrade(cells[i], cells[i].cfg.trade, { quiet: true });
  if (v.changed.length) saveLast();
  if (dropped.length) window.HBDeskClient.toast('err', T.liveDroppedMessage([...new Set(dropped)], st));
}

/* The desk's strategies (for an algo's symbol), merged with the paper strategies (2026-09-27 paper-forward-test
   plan, Task 2: GET /api/paper/strategies, keyed "paper:<id>") -- never null, so HBTrade.algoForRoot confirms a
   paper algo's root exactly like a desk one, clearing it only once ITS list confirms a mismatch. An absent key
   (the desk, or the paper list, hasn't answered yet) is "kept" by algoForRoot exactly like a missing desk state
   used to be. */
function deskStrategies() {
  const st = window.HBDeskClient && window.HBDeskClient.state;
  const bot = (st && st.bot && st.bot.strategies) || {};
  const paper = window.HBPaperClient ? T.paperStrategiesMap(window.HBPaperClient.strategies()) : {};
  return { ...bot, ...paper };
}
/* A template's trade / algo onto one chart: only the keys the template stored; a LIVE account in it is dropped
   like any load (HBTrade.templateTrade -> loadedTrade); its algo is kept only while the desk confirms it trades
   this chart's symbol (templates never store a symbol). `quiet`: the caller saves (the Settings dialog: on Ok). */
function applyTemplateTrade(cell, raw, { quiet = false } = {}) {
  const st = deskState(), bits = T.templateTrade(raw, st);
  if ('algo' in bits) window.HBTradeUI.setCellAlgo(cell, T.algoForRoot(bits.algo, cell.cfg.root, deskStrategies()), { quiet });
  if (bits.trade) window.HBTradeUI.setCellTrade(cell, bits.trade, { quiet, mark: bits.unverified });
  if (bits.droppedLive.length) window.HBDeskClient.toast('err', T.liveDroppedMessage(bits.droppedLive, st));
}
/* The Settings dialog's Cancel: a chart's accounts and algo as they were at open (HBTrade.tradeBits). Every id
   the restore puts BACK (one no longer on the chart) goes through the same unverified-id drop as a load (fix
   round 1, Minor 3): a cancelled dialog can never bring back a LIVE account, armed or not. Ids still on the
   chart keep whatever mark they already had. */
function restoreTemplateTrade(cell, bits) {
  window.HBTradeUI.setCellAlgo(cell, T.cellAlgo(bits && bits.algo), { quiet: true });
  const have = window.HBTradeUI.tradeOf(cell).accounts, next = T.cellTrade(bits && bits.trade);
  window.HBTradeUI.setCellTrade(cell, next, { quiet: true, mark: next.accounts.filter((id) => !have.includes(id)) });
  dropLiveAccounts();
}

/* The one-time migration of the retired global ticked list onto the SELECTED chart, when that chart has no
   trade config of its own yet (a pre-Task-2 layout, or a fresh one). Other charts get nothing.
   The old list is then cleared, so this never runs again. */
function migrateTickedOnce() {
  const Dc = window.HBDeskClient, ticked = Dc.prefs.ticked;
  if (!ticked || !ticked.length) return;
  const c = cur(), moved = c ? T.migrateTicked(lastRaw[selected], ticked) : null;
  if (moved) {   // a load like any other: LIVE dropped, the rest marked until the desk vouches for it
    const t = T.loadedTrade(moved, deskState());
    pendingDroppedLive.push(...t.droppedLive);
    window.HBTradeUI.setCellTrade(c, { accounts: t.accounts }, { quiet: true, mark: t.unverified });
    saveLast();
  }
  Dc.setPrefs({ ticked: [] });
}

function hostFor(id) {
  return {
    id,
    send(msg) { if (!ws || ws.readyState !== 1) return false; ws.send(JSON.stringify(msg)); return true; },
    onPick(cell, e) {
      // the order panel's price field has focus and the SELECTED chart is pressed: the press fills that field (the
      // price under the pointer, tick-rounded) and does nothing else -- no pan, no drawing, no order
      const OP = window.HBOrderPanel;
      if (e && e.button === 0 && cells.indexOf(cell) === selected && OP && OP.wantsPick()) {
        const price = cell.priceAtEvent(e);
        if (price != null) {
          e.preventDefault();
          e.stopPropagation();
          cell.swallowClicks();
          OP.pickPrice(price);
          return;
        }
      }
      select(cells.indexOf(cell));
    },
    onLoaded,
    onRefused,
    onSettings(cell, uid) { settingsDialog(cell, uid); },
    onChartSettings(cell) { chartSettings(cell); },
    onPosition(cell, d) { positionDialog(cell, d); },
    onDrawingSettings(cell, d) { drawingSettingsDialog(cell, d); },
    onSelectionChanged(cell, d) { syncDrawToolbar(cell, d); },
    styleDefault(type) { return drawStyleDefaults.get(type) || null; },
    onChartMenu(cell, at) { chartMenu(cell, at); },
    onIndicatorMenu(cell, uid, o) { indicatorMenu(cell, uid, o); },
    onReplayGuard(cell, patch) { window.HBReplayUI.guardSymbolChange(cell, patch); },
    // final review I2(b), SAFETY ruling: any symbol change CLEARS that chart's accounts, so the new instrument
    // places no new entries until they are picked again (HBTrade.symbolChangeTrade, from cell.update)
    onSymbolChange(cell, off) {
      if (!off.cleared.length) return;   // nothing on the chart: nothing to clear, nothing to say
      window.HBTradeUI.setCellTrade(cell, off.trade);
      window.HBDeskClient.toast('err', T.SYMBOL_CHANGE_ACCOUNTS_CLEARED);
    },
    changed() { saveLast(); renderToolbar(); },
    tool: () => tool,
    toolDone() { setTool('cursor'); },
    drawings,
    magnet: () => magnet,
    events: () => calendar,
    legendFolded,
    toggleLegendFolded,
    overlays(cell) { return page.overlays.map((f) => f(cell, page)); },
  };
}

function buildGrid() {
  closeHotkeyBox();   // it is anchored to a cell element the rebuild is about to destroy
  closeAllDrawToolbars();   // anchored to cells this rebuild is about to destroy
  for (const c of cells) { window.HBReplayUI.cellDestroyed(c); c.destroy(); }
  cells = [];
  const grid = $('#grid'), [cols, rows] = GRIDS[layout.grid] || GRIDS[4], n = cols * rows;
  // a chart kept beyond the visible grid is re-read like a load: its LIVE accounts drop, the rest stay
  const hidden = T.hiddenCellsLoaded(layout.cells, n, deskState());
  grid.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;
  grid.style.gridTemplateRows = `repeat(${rows}, minmax(0, 1fr))`;
  grid.dataset.count = String(n);
  grid.replaceChildren();
  while (layout.cells.length < n) layout.cells.push(starter(layout.cells.length));
  for (let i = 0; i < n; i++) {
    const slot = mk('div');
    grid.appendChild(slot);
    const cell = new Cell(slot, layout.cells[i], hostFor('c' + (nextId++)));
    cells.push(cell);
    cell.applyFold(legendFolded(cell));   // needs this cell's grid index, only known once it is in `cells`
  }
  // fix round 2: a chart destroyed mid-replay latches whatever chart now sits at its grid position -- for EVERY
  // caller (a layout load, a layout-tab switch, a grid-size change): HBTradeUI holds the positions
  window.HBTradeUI.gridRebuilt(cells);
  select(Math.min(selected, n - 1));
  if (hidden.length) window.HBDeskClient.toast('err', T.liveDroppedMessage(hidden, deskState()));
}

function select(i) {
  if (i < 0 || i >= cells.length) return;
  selected = i;
  cells.forEach((c, k) => c.setSelected(k === i));
  if (page) window.HBOrderPanel.setRoot(panelRoot());   // so does the order panel (it re-reads the chart itself)
  if (page) window.HBTradeUI.paintDeskStatus();         // and the status bar's "this chart: …" (Minor 6)
  renderToolbar();
  syncCrosshair();
}

/* ---- toolbar ---- */
function renderToolbar() {
  const c = cur();
  if (!c) return;
  const { root, spec } = c.cfg;
  $('#tbSymbolText').textContent = root;
  $('#tbSymbol').title = `${root} · ${C.rootName(root) || 'symbol'} — change symbol`;
  const favs = C.FAVOURITES.slice(), box = $('#tbFavs');
  if (!favs.some(([, s]) => s === spec)) favs.push([C.specLabel(spec), spec]);
  const had = box.contains(document.activeElement) ? document.activeElement.dataset.spec : null;   // keyboard focus
  box.replaceChildren(...favs.map(([label, s]) => {
    const b = mk('button', 'tb-btn iv' + (s === spec ? ' active' : ''), label);
    b.type = 'button';
    b.dataset.spec = s;
    b.title = C.longLabel(s);
    b.setAttribute('aria-pressed', String(s === spec));
    b.onclick = () => { if (cur().cfg.spec !== s) cur().update({ spec: s }); };
    return b;
  }));
  if (had) {
    const b = [...box.children].find((x) => x.dataset.spec === had) || box.querySelector('.active');
    if (b) b.focus();
  }
  const dark = document.documentElement.getAttribute('data-theme') === 'dark', th = $('#tbTheme');
  th.replaceChildren(icon(dark ? 'sun' : 'moon'));
  th.title = dark ? 'Light theme' : 'Dark theme';
  thumb(layout.grid, $('#tbGridThumb'));
  $('#tbGrid').title = `Chart layout: ${GRID_NAMES[layout.grid]}`;
  renderTabs();   // the active tab and its unsaved dot follow layout.name / layout.dirty like everything else here
}

/* One popup menu at a time: under its toolbar button, right of a rail button (right), or at the pointer (at: a
   context menu, anchor null). root: the element it is appended to (a dialog's box for in-dialog menus). */
function openMenu(anchor, cls, { right = false, root = null, at = null } = {}) {
  closeMenu();
  closeHotkeyBox();
  const m = mk('div', 'menu' + (cls ? ' ' + cls : ''));
  m.setAttribute('role', 'menu');
  (root || $('#menuRoot')).appendChild(m);
  menuEl = m; menuAnchor = anchor; menuRight = right; menuAt = at;
  if (anchor) { anchor.classList.add('open'); anchor.setAttribute('aria-expanded', 'true'); }
  return m;
}
function placeMenu() {
  if (!menuEl) return;
  const w = menuEl.offsetWidth, h = menuEl.offsetHeight;
  if (menuAt) {   // a context menu: at the pointer, kept inside the window
    menuEl.style.left = Math.max(4, Math.min(menuAt.x, window.innerWidth - w - 4)) + 'px';
    menuEl.style.top = Math.max(4, Math.min(menuAt.y, window.innerHeight - h - 4)) + 'px';
    return;
  }
  if (menuRight) {
    const r = (menuAnchor.closest('.rail-split') || menuAnchor).getBoundingClientRect();
    menuEl.style.left = (r.right + 8) + 'px';
    menuEl.style.top = Math.max(4, Math.min(r.top, window.innerHeight - h - 4)) + 'px';
    return;
  }
  const r = menuAnchor.getBoundingClientRect(), below = r.bottom + 4;
  menuEl.style.left = Math.max(4, Math.min(r.left, window.innerWidth - w - 4)) + 'px';
  // no room below (a dialog footer's menu, a swatch near the bottom): above the anchor instead
  menuEl.style.top = (below + h > window.innerHeight - 4 && r.top - 4 - h >= 4 ? r.top - 4 - h : below) + 'px';
}
function closeMenu() {
  if (!menuEl) return;
  const back = menuAnchor && menuEl.contains(document.activeElement) ? menuAnchor : null;   // keyboard focus goes back to the button
  menuEl.remove();
  if (menuAnchor) { menuAnchor.classList.remove('open'); menuAnchor.setAttribute('aria-expanded', 'false'); }
  menuEl = menuAnchor = menuAt = null;
  customWait = null;
  if (window.HBReplayUI) window.HBReplayUI.disarmPick();   // the Replay popover's "pick a start" arm, if any
  if (back) back.focus();
}
function toggleMenu(anchor, fill) {
  if (menuAnchor === anchor) { closeMenu(); return; }
  fill();
  placeMenu();
}
function menuItem(text, sub, onPick, active) {
  const b = mk('button', 'menu-i' + (active ? ' active' : ''));
  b.type = 'button';
  b.setAttribute('role', 'menuitem');
  b.appendChild(mk('span', 'menu-t', text));
  if (sub) b.appendChild(mk('span', 'menu-sub', sub));
  b.onclick = onPick;
  return b;
}
/* An error line in a menu: shown, and scrolled into the menu's view. */
function menuErr(el, text) {
  el.textContent = text;
  el.hidden = false;
  el.scrollIntoView({ block: 'nearest' });
}

/* A chart's symbol change: the one path the #tbSymbol menu and the letter-hotkey search box use. A new
   symbol switches the chart's Trading OFF and keeps its accounts (final review I2(b), SAFETY ruling -- enforced in
   cell.update for every path, HBTrade.symbolChangeTrade); its algo is cleared only when the desk confirms it trades another
   symbol (Task 2). The algo on the last accepted symbol is kept aside until the change settles, so a refused
   change (the chart rolls back to it) gets its algo back (fix round 1). */
function applySymbol(cell, r) {
  if (cell.cfg.root === r) return;
  if (!algoBefore.has(cell)) algoBefore.set(cell, { root: cell.cfg.root, algo: cell.cfg.algo ?? null });
  cell.update({ root: r, algo: T.algoForRoot(cell.cfg.algo, r, deskStrategies()) });
}

function symbolMenu() {
  const m = openMenu($('#tbSymbol'), 'menu-sym'), input = mk('input', 'menu-input'), list = mk('div');
  input.type = 'text'; input.placeholder = 'Search'; input.spellcheck = false;
  input.setAttribute('aria-label', 'Search symbols');
  const render = () => {
    const q = input.value.trim().toUpperCase(), c = cur();
    const hits = meta.roots.filter((r) => !q || r.includes(q) || C.rootName(r).toUpperCase().includes(q));
    list.replaceChildren(...hits.map((r) => {
      const b = menuItem(r, C.rootName(r), () => { closeMenu(); applySymbol(c, r); }, r === c.cfg.root);
      b.prepend(badgeEl(r, 16));
      return b;
    }));
    if (!hits.length) list.appendChild(mk('div', 'menu-empty', 'No matching symbol'));
  };
  input.oninput = render;
  input.onkeydown = (e) => { if (e.key === 'Enter') { const first = list.querySelector('.menu-i'); if (first) first.click(); } };
  m.append(input, list);
  render();
  input.focus();
}

function intervalMenu() {
  const m = openMenu($('#tbIntervals'), 'menu-iv'), c = cur(), spec = c.cfg.spec;
  for (const [group, specs] of C.INTERVAL_GROUPS) {
    m.appendChild(mk('div', 'menu-h', group));
    for (const s of specs) {
      m.appendChild(menuItem(C.longLabel(s), '', () => { closeMenu(); if (c.cfg.spec !== s) c.update({ spec: s }); }, s === spec));
    }
  }
  m.appendChild(mk('div', 'menu-h', 'Custom'));
  const row = mk('div', 'menu-custom'), input = mk('input', 'menu-input'), apply = mk('button', 'btn btn-primary', 'Apply');
  const err = mk('div', 'menu-err');
  err.hidden = true;
  err.setAttribute('role', 'alert');
  input.type = 'text'; input.placeholder = 'e.g. 45s, 750T, tick:750'; input.spellcheck = false;
  input.setAttribute('aria-label', 'Custom interval');
  apply.type = 'button';
  const go = () => {
    const s = C.toSpec(input.value);
    if (!s) { menuErr(err, 'Use e.g. 45s, 2m, 4h, 1D, 750T, 3000V, 8R or tick:750'); return; }
    err.hidden = true;
    if (s === c.cfg.spec) { closeMenu(); return; }
    customWait = { cell: c, spec: s, err };
    c.update({ spec: s });
  };
  apply.onclick = go;
  input.onkeydown = (e) => { if (e.key === 'Enter') go(); };
  row.append(input, apply);
  m.append(row, err);
}

/* ---- keyboard hotkeys: timeframe box + symbol-search box (TradingView-style, spec Task 1 + addition) ----
   Both are small floating boxes near the SELECTED chart's top-left corner, opened by a bare digit (timeframe)
   or a bare letter (symbol search) — never while an input/select/textarea/contenteditable has focus, or a
   dialog or app menu is open (see onKey). Only one is ever open; closeHotkeyBox tears it down on Enter, Esc,
   blur, or whenever a real menu/dialog opens (openMenu/openDialog) or the grid rebuilds. */
function hotkeyAnchor(cell) {
  const r = cell.el.getBoundingClientRect();
  return { left: r.left + 8, top: r.top + 8 };
}
function closeHotkeyBox() {
  if (!hotkeyBox) return;
  hotkeyBox.el.remove();
  hotkeyBox = null;
}
/* A blur means "cancel" for both boxes, but Enter/Escape already call closeHotkeyBox() themselves before the
   blur fires (removing the focused input triggers one) — guarded by identity so that later blur is a no-op. */
function hotkeyBlur(input) {
  return () => setTimeout(() => { if (hotkeyBox && hotkeyBox.input === input) closeHotkeyBox(); }, 0);
}

function openTimeframeBox(cell, seed) {
  closeHotkeyBox();
  const { left, top } = hotkeyAnchor(cell);
  const box = mk('div', 'hotkey-box hotkey-tf'), input = mk('input', 'hotkey-input'), err = mk('div', 'hotkey-err', 'Not available');
  box.style.left = left + 'px'; box.style.top = top + 'px';
  input.type = 'text'; input.spellcheck = false; input.autocomplete = 'off';
  input.setAttribute('aria-label', 'Timeframe');
  input.placeholder = '5, 30s, 4h, d…';
  err.hidden = true;
  err.setAttribute('role', 'alert');
  const apply = () => {
    const s = C.parseInterval(input.value);
    if (!s) { err.hidden = false; return; }
    closeHotkeyBox();
    if (cell.cfg.spec !== s) cell.update({ spec: s });
  };
  input.oninput = () => { err.hidden = true; };
  input.onkeydown = (e) => {
    if (e.key === 'Enter') { e.preventDefault(); apply(); }
    else if (e.key === 'Escape') { e.preventDefault(); closeHotkeyBox(); }
  };
  input.onblur = hotkeyBlur(input);
  box.append(input, err);
  $('#menuRoot').appendChild(box);
  hotkeyBox = { el: box, input, kind: 'tf' };
  input.value = seed;
  input.focus();
  input.setSelectionRange(seed.length, seed.length);
}

function openSymbolBox(cell, seed) {
  closeHotkeyBox();
  const { left, top } = hotkeyAnchor(cell);
  const box = mk('div', 'hotkey-box hotkey-sym'), input = mk('input', 'hotkey-input'), list = mk('div', 'hotkey-list');
  box.style.left = left + 'px'; box.style.top = top + 'px';
  input.type = 'text'; input.spellcheck = false; input.autocomplete = 'off';
  input.setAttribute('aria-label', 'Search symbols');
  input.placeholder = 'Symbol';
  let active = 0;
  const hits = () => C.matchSymbols(input.value, meta.roots);
  const render = () => {
    const h = hits();
    if (active >= h.length) active = 0;
    list.replaceChildren(...h.map((r, i) => {
      const b = mk('button', 'menu-i hotkey-i' + (i === active ? ' active' : ''));
      b.type = 'button';
      b.append(badgeEl(r, 16), mk('span', 'menu-t', r), mk('span', 'menu-sub', C.rootName(r)));
      b.onclick = () => pick(r);
      return b;
    }));
    if (!h.length) list.appendChild(mk('div', 'menu-empty', 'No matching symbol'));
  };
  const pick = (r) => { closeHotkeyBox(); applySymbol(cell, r); };
  input.oninput = () => { active = 0; render(); };
  input.onkeydown = (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      const h = hits();
      if (h.length) pick(h[Math.min(active, h.length - 1)]);
    } else if (e.key === 'Escape') {
      e.preventDefault();
      closeHotkeyBox();
    } else if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
      e.preventDefault();
      active = window.HBChartMenu.step(active, hits().length, e.key);
      render();
    }
  };
  input.onblur = hotkeyBlur(input);
  box.append(input, list);
  $('#menuRoot').appendChild(box);
  hotkeyBox = { el: box, input, kind: 'sym' };
  input.value = seed;
  render();
  input.focus();
  input.setSelectionRange(seed.length, seed.length);
}

/* A custom interval the open menu sent is on screen: close the menu. */
/* cell -> {root, algo}: a chart's algo on its last accepted symbol while a symbol change is still unanswered. */
const algoBefore = new WeakMap();

/* The selected chart's loaded root (null while it has none). */
function panelRoot() { const c = cur(); return c && c.shown ? c.shown.root : null; }

function onLoaded(cell) {
  algoBefore.delete(cell);   // a history arrived: whatever symbol it is on now, the algo decision stands
  if (page && cell === cur()) window.HBOrderPanel.setRoot(panelRoot());   // its symbol / tick / point value may be new
  if (customWait && customWait.cell === cell && cell.shown.spec === customWait.spec) closeMenu();
}

/* The server refused a change (the cell already went back to its last good
   config): say why inline in the interval menu if that is where it came
   from, else in the chart's legend. */
function onRefused(cell, tried, text) {
  const was = algoBefore.get(cell);
  if (was && cell.cfg.root === was.root) {   // rolled back to the symbol the algo was on: the algo comes back too
    algoBefore.delete(cell);
    window.HBTradeUI.setCellAlgo(cell, was.algo, { quiet: true });
    saveLast();
  }
  if (customWait && customWait.cell === cell && menuEl) {
    menuErr(customWait.err, text);
    customWait = null;
    return;
  }
  cell.note(text);
}

function toggleTheme() {
  const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  try { localStorage.setItem('hb_theme', next); } catch (_) { /* storage off */ }
  for (const c of cells) c.restyle();
  renderToolbar();
}

function thumb(n, into) {
  const [cols, rows] = GRIDS[n];
  into.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;
  into.style.gridTemplateRows = `repeat(${rows}, 1fr)`;
  into.replaceChildren(...Array.from({ length: cols * rows }, () => document.createElement('i')));
  return into;
}

function gridMenu() {
  const m = openMenu($('#tbGrid'), 'menu-grid'), picks = mk('div', 'grid-picks');
  for (const n of [1, 2, 4, 6]) {
    const b = mk('button', 'grid-pick' + (layout.grid === n ? ' active' : ''));
    b.type = 'button';
    b.title = GRID_NAMES[n];
    b.setAttribute('aria-label', GRID_NAMES[n]);
    b.appendChild(thumb(n, mk('span', 'thumb')));
    b.onclick = () => { closeMenu(); if (layout.grid !== n) { layout.grid = n; saveLast(); buildGrid(); } };
    picks.appendChild(b);
  }
  m.appendChild(picks);
}

/* ---- layout tabs (2026-09-27 layout-tabs plan, Task 3) ----
   Each tab IS a saved layout: server truth lives at /api/layouts/{name} (the body) and /api/layout-order
   (the strip's left-to-right order, viewer-agnostic -- everyone who opens this desk sees the same tabs in
   the same place). Pure decisions (ordering, the dot, rename collisions, closing the active tab, default
   names, drag reorder) live in layouts.js (window.HBLayouts) and are unit-tested there; this section only
   owns the fetches, the DOM and localStorage. The LAST open tab is already covered by the existing
   hb_charts_last save/load (saveLast/loadLast above) -- it stores `layout.name` alongside the cells, so
   nothing new is needed for that per the spec. */
let tabOrder = [];          // display order: names that exist, per HBLayouts.orderNames
let layoutsCache = {};      // name -> last-known server body (GET /api/layouts), kept fresh as we write
let tabSnapshot = null;     // the body last written/loaded for layout.name; null = never saved / not loaded yet
let dragTab = null;         // the tab name currently being dragged, or null

/* The current charts as a layout body -- exactly what a PUT (or a rename/duplicate copy) sends. Each
   chart's trade ACCOUNTS and algo are saved (HBTrade.tradeBits), never its Trading switch (Task 2); a LIVE
   one is dropped again on load (readLayout -> HBTrade.loadedTrade). */
function layoutBody() {
  return { grid: layout.grid, cells: layout.cells.map((c) => {
    const { root, spec, indicators, settings } = c;
    const base = settings && Object.keys(settings).length ? { root, spec, indicators, settings } : { root, spec, indicators };
    return { ...base, ...T.tradeBits(c) };
  }) };
}

/* PUT `body` (default: the current charts) under `name`: '' when saved, else the reason. */
async function putLayout(name, body = layoutBody()) {
  let r;
  try {
    r = await fetch('/api/layouts/' + encodeURIComponent(name), { method: 'PUT',
      headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  } catch (e) { return 'save failed: ' + (e && e.message ? e.message : 'network error'); }
  if (r.ok) return '';
  let detail = '';
  try { detail = (await r.json()).detail || ''; } catch (_) { /* no JSON body */ }
  return `save failed (${r.status})` + (detail ? ': ' + detail : '');
}

/* Best-effort: the strip's order is cosmetic (never trade config), so a failed write only means the
   NEXT reload sees the old order -- worth logging, never worth blocking a click over. */
function persistOrder() {
  fetch('/api/layout-order', { method: 'PUT', headers: { 'content-type': 'application/json' }, body: JSON.stringify(tabOrder) })
    .catch(() => { /* next load falls back to A-Z for anything unordered (HBLayouts.orderNames) */ });
}

function loadLayout(name, saved) {
  layout = { ...readLayout(saved), name, dirty: false };
  tabSnapshot = layoutBody();
  saveLast();
  selected = 0;
  buildGrid();
  dropLiveAccounts();   // the load's own LIVE drop is reported once, here (readLayout only collects it)
  renderTabs();
}

/* Clicking a tab: save the current one first if it is named (spec) -- but only write when it actually
   drifted from the server (HBLayouts.isDirty), so a click-through of unrelated tabs never spams PUTs. A
   failed save keeps the user ON the current tab rather than silently discarding their edits. */
async function switchTab(name) {
  if (name === layout.name) return;
  if (layout.name && window.HBLayouts.isDirty(tabSnapshot, layoutBody())) {
    const why = await putLayout(layout.name);
    if (why) { sbNote(why); return; }
    layoutsCache[layout.name] = layoutBody();
    layout.dirty = false;
  }
  const saved = layoutsCache[name];
  if (!saved) { sbNote(`could not open “${name}”`); return; }
  loadLayout(name, saved);
}

/* + : a new tab, auto-named, seeded from whatever is on screen right now. */
async function addTab() {
  const name = window.HBLayouts.uniqueName('Layout', tabOrder);
  const body = layoutBody();
  const why = await putLayout(name, body);
  if (why) { sbNote(why); return; }
  layoutsCache[name] = body;
  tabOrder.push(name);
  persistOrder();
  layout.name = name;
  layout.dirty = false;
  tabSnapshot = body;
  saveLast();
  renderTabs();
  renderToolbar();
}

/* Right-click menu -> Duplicate: a copy under "<name> copy" (counted up on a collision), switched to
   immediately -- landing on the new tab is what TradingView does, and it is also the only sane result
   when `name` IS the active tab (the copy is byte-identical to what is already on screen). */
async function duplicateTab(name) {
  const body = name === layout.name ? layoutBody() : layoutsCache[name];
  if (!body) { sbNote(`could not read “${name}”`); return; }
  const next = window.HBLayouts.uniqueName(`${name} copy`, tabOrder);
  const why = await putLayout(next, body);
  if (why) { sbNote(why); return; }
  layoutsCache[next] = body;
  const at = tabOrder.indexOf(name);
  tabOrder.splice(at < 0 ? tabOrder.length : at + 1, 0, next);
  persistOrder();
  if (name === layout.name) {
    layout.name = next;
    layout.dirty = false;
    tabSnapshot = body;
    saveLast();
    renderToolbar();
  } else {
    loadLayout(next, body);
  }
  renderTabs();
}

/* Rename: a single atomic server-side move (POST /api/layouts/{name}/rename), never a client-side
   PUT-new-then-DELETE-old -- a failed DELETE there would leave two copies with no way to tell which is
   live. Renaming the ACTIVE tab saves its current edits first (under the OLD name) so the rename carries
   them, rather than moving a stale server body and losing what's on screen. */
function renameTab(oldName) {
  const anchor = [...$('#tabStrip').children].find((b) => b.dataset.tab === oldName);
  const m = openMenu(anchor || $('#tabStrip'), 'menu-rename'), row = mk('div', 'menu-custom');
  const input = mk('input', 'menu-input'), ok = mk('button', 'btn btn-primary', 'Rename'), err = mk('div', 'menu-err');
  input.type = 'text'; input.maxLength = 80; input.value = oldName; input.spellcheck = false;
  input.setAttribute('aria-label', 'Layout name');
  err.hidden = true;
  err.setAttribute('role', 'alert');
  ok.type = 'button';
  const go = async () => {
    const next = input.value.trim(), why = window.HBLayouts.renameError(next, oldName, tabOrder);
    if (why) { menuErr(err, why); input.focus(); return; }
    if (next === oldName) { closeMenu(); return; }
    if (oldName === layout.name && window.HBLayouts.isDirty(tabSnapshot, layoutBody())) {
      const saveWhy = await putLayout(oldName);
      if (saveWhy) { menuErr(err, saveWhy); return; }
      layoutsCache[oldName] = layoutBody();
      layout.dirty = false;
    }
    let r;
    try {
      r = await fetch(`/api/layouts/${encodeURIComponent(oldName)}/rename`, { method: 'POST',
        headers: { 'content-type': 'application/json' }, body: JSON.stringify({ to: next }) });
    } catch (e) { menuErr(err, 'rename failed: ' + (e && e.message ? e.message : 'network error')); return; }
    if (!r.ok) {
      let detail = '';
      try { detail = (await r.json()).detail || ''; } catch (_) { /* no JSON body */ }
      menuErr(err, `rename failed (${r.status})` + (detail ? ': ' + detail : ''));
      return;
    }
    layoutsCache[next] = layoutsCache[oldName];
    delete layoutsCache[oldName];
    tabOrder = tabOrder.map((n) => (n === oldName ? next : n));
    persistOrder();
    if (layout.name === oldName) { layout.name = next; tabSnapshot = layoutsCache[next]; saveLast(); renderToolbar(); }
    closeMenu();
    renderTabs();
  };
  ok.onclick = go;
  input.onkeydown = (e) => { if (e.key === 'Enter') go(); };
  row.append(input, ok);
  m.append(row, err);
  placeMenu();
  input.focus();
  input.select();
}

/* Right-click menu -> Close, and middle-click: removes the tab from the STRIP only -- the saved layout
   stays on the server, reachable again from the + menu's "not currently open" list. Closing the active
   tab switches to the neighbour HBLayouts.closeTab picks; closing the last one leaves the current charts
   on screen, just unnamed (nothing left to switch to). Purely local: no network call, so it cannot fail. */
function closeTab(name) {
  const idx = tabOrder.indexOf(name);
  if (idx < 0) return;
  const { order, active } = window.HBLayouts.closeTab(tabOrder, idx);
  tabOrder = order;
  persistOrder();
  if (name === layout.name) {
    if (active >= 0 && layoutsCache[tabOrder[active]]) loadLayout(tabOrder[active], layoutsCache[tabOrder[active]]);
    else { layout.name = ''; layout.dirty = false; tabSnapshot = null; saveLast(); renderToolbar(); }
  }
  renderTabs();
}

/* Right-click menu -> Delete layout... (danger-styled, confirmed through openDialog, never a native
   confirm()): the only path left that removes a saved layout from the server. Closing a tab never does
   this any more -- see closeTab above. */
function deleteLayoutTab(name) {
  const box = openDialog('Delete layout', 'small'), body = mk('div', 'dlg-fields');
  body.appendChild(mk('div', 'dlg-msg', `Delete “${name}”? This removes it from the server for everyone -- it cannot be undone.`));
  const foot = mk('div', 'dlg-foot'), cancel = mk('button', 'btn btn-ghost', 'Cancel'), del = mk('button', 'btn btn-danger', 'Delete');
  cancel.type = 'button';
  del.type = 'button';
  cancel.onclick = closeDialog;
  del.onclick = async () => {
    del.disabled = true;
    let r = null;
    try { r = await fetch('/api/layouts/' + encodeURIComponent(name), { method: 'DELETE' }); } catch (_) { /* r stays null */ }
    if (!r || !r.ok) { del.disabled = false; sbNote(`delete failed${r ? ` (${r.status})` : ': network error'}`); return; }
    closeDialog();
    delete layoutsCache[name];
    const idx = tabOrder.indexOf(name);
    if (idx >= 0) {
      const { order, active } = window.HBLayouts.closeTab(tabOrder, idx);
      tabOrder = order;
      persistOrder();
      if (name === layout.name) {
        if (active >= 0 && layoutsCache[tabOrder[active]]) loadLayout(tabOrder[active], layoutsCache[tabOrder[active]]);
        else { layout.name = ''; layout.dirty = false; tabSnapshot = null; saveLast(); renderToolbar(); }
      }
      renderTabs();
    }
  };
  foot.append(cancel, del);
  body.appendChild(foot);
  box.appendChild(body);
  del.focus();
}

function tabContextMenu(name, at) {
  const m = openMenu(null, 'menu-tabctx', { at });
  const del = menuItem('Delete layout…', '', () => { closeMenu(); deleteLayoutTab(name); });
  del.classList.add('menu-i-danger');
  m.append(
    menuItem('Rename', '', () => { closeMenu(); renameTab(name); }),
    menuItem('Duplicate', '', () => { closeMenu(); duplicateTab(name); }),
    menuItem('Close', '', () => { closeMenu(); closeTab(name); }),
    mk('div', 'menu-sep'),
    del,
  );
  placeMenu();
  m.tabIndex = -1;
  m.focus({ preventScroll: true });
}

/* + menu: "New layout" (the old bare + behaviour) plus, when any saved layout is currently closed, a
   list of those names so one can be reopened. Reopening loads straight from the local cache -- no refetch
   -- consistent with the rest of the strip trusting layoutsCache between explicit server round trips. */
function reopenTab(name) {
  if (!tabOrder.includes(name)) { tabOrder.push(name); persistOrder(); }
  switchTab(name);
}

function addTabMenu(anchor) {
  const names = window.HBLayouts.closedNames(Object.keys(layoutsCache), tabOrder);
  if (!names.length) { addTab(); return; }
  const m = openMenu(anchor, 'menu-tabadd');
  m.appendChild(menuItem('New layout', '', () => { closeMenu(); addTab(); }));
  m.appendChild(mk('div', 'menu-sep'));
  m.appendChild(mk('div', 'menu-h', 'Reopen'));
  for (const name of names) m.appendChild(menuItem(name, '', () => { closeMenu(); reopenTab(name); }));
  placeMenu();
}

function renderTabs() {
  const strip = $('#tabStrip');
  strip.replaceChildren(...tabOrder.map((name, i) => {
    const active = name === layout.name, b = mk('button', 'tab-btn' + (active ? ' active' : ''));
    b.type = 'button';
    b.dataset.tab = name;
    b.draggable = true;
    b.title = name;
    b.setAttribute('role', 'tab');
    b.setAttribute('aria-selected', String(active));
    b.appendChild(mk('span', 'tab-name', name));
    if (active && layout.dirty) { const dot = mk('span', 'tab-dot'); dot.setAttribute('aria-label', 'Unsaved changes'); b.appendChild(dot); }
    b.onclick = () => switchTab(name);
    b.oncontextmenu = (e) => { e.preventDefault(); tabContextMenu(name, { x: e.clientX, y: e.clientY }); };
    // middle-click closes the tab (never deletes -- same as the context menu's Close, not its Delete);
    // auxclick covers the middle button cross-browser without also firing on a plain left-click
    b.onauxclick = (e) => { if (e.button === 1) { e.preventDefault(); closeTab(name); } };
    b.ondragstart = (e) => { dragTab = name; e.dataTransfer.effectAllowed = 'move'; };
    b.ondragend = () => { dragTab = null; strip.querySelectorAll('.drag-over').forEach((x) => x.classList.remove('drag-over')); };
    b.ondragover = (e) => { if (dragTab && dragTab !== name) { e.preventDefault(); b.classList.add('drag-over'); } };
    b.ondragleave = () => b.classList.remove('drag-over');
    b.ondrop = (e) => {
      e.preventDefault();
      b.classList.remove('drag-over');
      if (!dragTab || dragTab === name) return;
      tabOrder = window.HBLayouts.moveTab(tabOrder, dragTab, i);
      dragTab = null;
      persistOrder();
      renderTabs();
    };
    return b;
  }));
  const add = mk('button', 'tab-add');
  add.type = 'button';
  add.title = 'Add layout tab';
  add.setAttribute('aria-label', 'Add layout tab');
  add.appendChild(icon('plus'));
  add.onclick = () => addTabMenu(add);
  strip.appendChild(add);
}

/* Everything the tab strip knows about which layouts exist, at startup: `layout.name` (from
   hb_charts_last, read already by loadLast()) just needs SOMETHING to switch to on a later click, so this
   caches every saved body up front rather than re-fetching per tab (the old menu's lazy-fetch-on-open no
   longer applies -- the strip is on screen from the first paint). */
async function loadTabs() {
  let all = null, order = null;
  try {
    const [ra, ro] = await Promise.all([fetch('/api/layouts'), fetch('/api/layout-order')]);
    all = ra.ok ? await ra.json() : null;
    order = ro.ok ? await ro.json() : null;
  } catch (_) { /* keep whatever we had */ }
  if (!all) { sbNote('could not load saved layouts'); return; }
  layoutsCache = all;
  tabOrder = window.HBLayouts.orderNames(Object.keys(all), Array.isArray(order) ? order : []);
  // the active tab (from hb_charts_last, restored before this resolved) may carry edits made before a
  // refresh -- seed the snapshot from the SERVER's body, never the current one, so isDirty still catches
  // real drift instead of treating "whatever is on screen right now" as automatically saved
  if (layout.name && all[layout.name]) tabSnapshot = all[layout.name];
  const first = window.HBLayouts.startTab(layout.name, layout.dirty, tabOrder, all);
  if (first) { loadLayout(first, all[first]); return; }   // loadLayout renders the tabs itself
  renderTabs();
}

/* ---- chart-settings templates (shared by every chart, saved on the server) ---- */
const templates = {
  /* {name: settings}, or null when they could not be read. */
  async list() { try { const r = await fetch('/api/templates'); return r.ok ? await r.json() : null; } catch (_) { return null; } },
  /* '' when saved / deleted, else the reason. */
  save: (name, settings) => writeTemplate('PUT', name, settings),
  remove: (name) => writeTemplate('DELETE', name),
};
async function writeTemplate(method, name, body) {
  const what = method === 'PUT' ? 'save' : 'delete';
  let r;
  try {
    r = await fetch('/api/templates/' + encodeURIComponent(name), body === undefined ? { method }
      : { method, headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  } catch (_) { return `${what} failed: network error`; }
  if (r.ok) return '';
  let detail = '';
  try { detail = (await r.json()).detail || ''; } catch (_) { /* no JSON body */ }
  return `${what} failed (${r.status})` + (detail ? ': ' + detail : '');
}

/* ---- dialogs ---- */
function openDialog(title, cls) {
  closeMenu();
  closeHotkeyBox();
  closeDialog();
  const back = mk('div', 'backdrop'), box = mk('div', 'dialog' + (cls ? ' ' + cls : '')), head = mk('div', 'dlg-head');
  const x = mk('button', 'dlg-x');
  x.type = 'button';
  x.title = 'Close';
  x.setAttribute('aria-label', 'Close');
  x.appendChild(icon('x'));
  x.onclick = closeDialog;
  box.setAttribute('role', 'dialog');
  box.setAttribute('aria-modal', 'true');
  box.setAttribute('aria-label', title);
  head.append(mk('span', '', title), x);
  box.appendChild(head);
  back.appendChild(box);
  back.addEventListener('pointerdown', (e) => { if (e.target === back) closeDialog(); });
  $('#dialogRoot').appendChild(back);
  dlg = { back, box, focus: document.activeElement };
  return box;
}

function closeDialog() {
  if (!dlg) return;
  closeMenu();   // a menu or swatch popover open inside the dialog goes with it
  const { back, focus, onClose } = dlg;
  dlg = null;
  back.remove();
  if (onClose) onClose();   // the Settings dialog puts every chart back unless Ok was pressed
  if (focus && typeof focus.focus === 'function' && document.contains(focus)) focus.focus();
}

function trapTab(e) {   // Tab stays inside the open dialog
  const f = [...dlg.box.querySelectorAll('button, input, select')].filter((x) => !x.disabled && x.offsetParent !== null);
  if (!f.length) return;
  const first = f[0], last = f[f.length - 1], at = document.activeElement;
  if (!dlg.box.contains(at)) { e.preventDefault(); (e.shiftKey ? last : first).focus(); }   // focus fell out (e.g. to body)
  else if (e.shiftKey && at === first) { e.preventDefault(); last.focus(); }
  else if (!e.shiftKey && at === last) { e.preventDefault(); first.focus(); }
}

/* TradingView's Indicators dialog: search, groups, click a name to add it
   (with defaults) to the selected chart; the dialog stays open. */
function indicatorsDialog() {
  const c = cur();
  if (!c) return;
  const box = openDialog('Indicators');
  const search = mk('label', 'dlg-search'), input = mk('input');
  input.type = 'search'; input.placeholder = 'Search'; input.spellcheck = false;
  input.setAttribute('aria-label', 'Search indicators');
  search.append(icon('search'), input);
  const body = mk('div', 'dlg-body'), groups = mk('div', 'dlg-groups'), list = mk('div', 'dlg-list');
  body.append(groups, list);
  box.append(search, body);
  let group = 'All';
  const render = () => {
    const q = input.value.trim(), hits = C.filter(q, group);
    const had = list.contains(document.activeElement) ? document.activeElement.dataset.id : null;   // keyboard focus
    list.replaceChildren(...hits.map((d) => {
      const row = mk('button', 'dlg-row');
      row.type = 'button';
      row.title = `Add ${d.name}`;
      row.dataset.id = d.id;
      row.append(mk('span', 'dlg-name', d.name));
      if (q && group === 'All') row.append(mk('span', 'dlg-grp', d.group));
      if (c.cfg.indicators.some((x) => x.id === d.id)) row.append(icon('check'));
      row.onclick = () => { c.update({ indicators: [...c.cfg.indicators, C.instance(d.id)] }); render(); };
      return row;
    }));
    if (!hits.length) list.appendChild(mk('div', 'dlg-empty', 'No indicators match'));
    const again = had && [...list.children].find((x) => x.dataset.id === had);
    if (again) again.focus();
  };
  const renderGroups = () => {
    const had = groups.contains(document.activeElement);
    groups.replaceChildren(...C.GROUPS.map((g) => {
      const b = mk('button', 'dlg-group' + (g === group ? ' active' : ''), g);
      b.type = 'button';
      b.onclick = () => { group = g; renderGroups(); render(); };
      return b;
    }));
    if (had) groups.querySelector('.active').focus();
  };
  input.oninput = render;
  input.onkeydown = (e) => { if (e.key === 'Enter') { const first = list.querySelector('.dlg-row'); if (first) first.click(); } };
  renderGroups();
  render();
  input.focus();
}

/* The gear on a legend row: one field per param; OK clamps, applies, resubscribes if needed. */
function settingsDialog(cell, uid) {
  const inst = cell.cfg.indicators.find((x) => x.uid === uid), d = inst && C.def(inst.id);
  if (!d || !d.params.length) return;
  const box = openDialog(d.name, 'small'), form = mk('div', 'dlg-fields'), vals = { ...inst.params };
  for (const p of d.params) {
    const row = mk('div', 'field'), id = `f-${uid}-${p.key}`, lab = mk('label', '', p.label);
    let ctl;
    if (p.type === 'bool') {
      ctl = mk('input');
      ctl.type = 'checkbox';
      ctl.checked = !!vals[p.key];
      ctl.onchange = () => { vals[p.key] = ctl.checked; };
    } else if (p.type === 'choice') {
      ctl = mk('div', 'seg');
      ctl.setAttribute('role', 'radiogroup');
      ctl.setAttribute('aria-label', p.label);
      const draw = () => {
        const had = ctl.contains(document.activeElement);   // keyboard focus stays on the chosen button
        ctl.replaceChildren(...p.choices.map(([v, text]) => {
          const b = mk('button', vals[p.key] === v ? 'on' : '', text);
          b.type = 'button';
          b.setAttribute('role', 'radio');
          b.setAttribute('aria-checked', String(vals[p.key] === v));
          b.onclick = () => { vals[p.key] = v; draw(); };
          return b;
        }));
        if (had) ctl.querySelector('.on').focus();
      };
      draw();
    } else {
      ctl = mk('input');
      ctl.type = 'number';
      ctl.min = p.min; ctl.max = p.max; ctl.step = p.step || 1;
      ctl.value = vals[p.key];
      ctl.oninput = () => { vals[p.key] = ctl.value; };
    }
    ctl.id = id;
    lab.htmlFor = id;
    row.append(lab, ctl);
    form.appendChild(row);
  }
  const foot = mk('div', 'dlg-foot'), cancel = mk('button', 'btn btn-ghost', 'Cancel'), ok = mk('button', 'btn btn-primary', 'OK');
  cancel.type = 'button';
  ok.type = 'button';
  cancel.onclick = closeDialog;
  ok.onclick = () => {
    const params = C.clampParams(inst.id, vals);
    closeDialog();
    cell.update({ indicators: cell.cfg.indicators.map((x) => (x.uid === uid ? { ...x, params } : x)) });
  };
  form.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.tagName === 'INPUT') ok.click(); });
  foot.append(cancel, ok);
  box.append(form, foot);
  const first = form.querySelector('input, button');
  if (first) first.focus();
}

/* Double-click on a long/short box: Entry, Target, Stop (rounded to the tick) and Qty. OK checks the order for
   the type; a wrong one shows why under the fields and saves nothing. */
function positionDialog(cell, d) {
  const Pos = window.HBPosition, D = window.HBDrawings, tick = cell.tick, root = cell.dc ? cell.dc.root : cell.cfg.root;
  const box = openDialog(d.type === 'long' ? 'Long position' : 'Short position', 'small');
  const form = mk('div', 'dlg-fields'), err = mk('div', 'dlg-err'), inputs = {};
  err.hidden = true;
  err.setAttribute('role', 'alert');
  const [E, T, S] = d.points;
  for (const [key, label, v] of [['entry', 'Entry', E.p], ['target', 'Target', T.p], ['stop', 'Stop', S.p], ['qty', 'Qty', d.qty || 1]]) {
    const row = mk('div', 'field'), id = `pos-${key}`, lab = mk('label', '', label), ctl = mk('input', key === 'qty' ? '' : 'price');
    ctl.type = 'number';
    ctl.id = id;
    ctl.step = key === 'qty' ? '1' : String(tick);
    if (key === 'qty') { ctl.min = '1'; ctl.max = String(Pos.QTY_MAX); }
    ctl.value = String(v);
    lab.htmlFor = id;
    row.append(lab, ctl);
    form.appendChild(row);
    inputs[key] = ctl;
  }
  const foot = mk('div', 'dlg-foot'), cancel = mk('button', 'btn btn-ghost', 'Cancel'), ok = mk('button', 'btn btn-primary', 'OK');
  cancel.type = 'button';
  ok.type = 'button';
  cancel.onclick = closeDialog;
  ok.onclick = () => {
    const num = (k) => (inputs[k].value.trim() === '' ? NaN : Number(inputs[k].value));
    const entry = D.roundToTick(num('entry'), tick), target = D.roundToTick(num('target'), tick);
    const stop = D.roundToTick(num('stop'), tick), qty = num('qty');
    const why = Pos.validate(d.type, entry, target, stop, qty, tick);
    if (why) { err.textContent = why; err.hidden = false; return; }
    const now = drawings.list(root).find((x) => x.id === d.id);
    closeDialog();
    if (!now) return;   // removed meanwhile (on another chart of this symbol)
    drawings.replace(root, { ...now, qty, points: [{ t: now.points[0].t, p: entry }, { t: now.points[1].t, p: target },
      { t: now.points[2].t, p: stop }] });
  };
  form.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.tagName === 'INPUT') ok.click(); });
  foot.append(cancel, ok);
  box.append(form, err, foot);
  inputs.entry.focus();
  inputs.entry.select();
}

/* ---- 2026-09-27 draw-tools plan: the floating per-drawing toolbar + its settings dialog ---- */
const DRAW_TYPES = ['trend', 'hline', 'rect'];          // the types that take a style object at all
const isPosDrawing = (d) => d.type === 'long' || d.type === 'short';
const drawStyleDefaults = new Map();                    // type -> that tool's saved "__default__" preset payload
async function loadDrawStyleDefaults() {
  for (const type of DRAW_TYPES) {
    const all = await window.HBPresets.client(`drawing:${type}`).list();
    if (all && window.HBPresets.DEFAULT_NAME in all) drawStyleDefaults.set(type, all[window.HBPresets.DEFAULT_NAME]);
  }
}
/* A dialog-scoped menu host built around the page's own openMenu/closeMenu/placeMenu, the same
   shape settings-dialog.js' own `host.toggleMenu` gives its swatch popovers and Template ▾ --
   so presets.js' menu() (and the swatch popover below) work the same whether they open from
   inside a dialog or from the floating toolbar directly on the chart. */
function pageMenuHost() {
  return { toggleMenu(anchor, cls, fill) { if (menuAnchor === anchor) { closeMenu(); return; } fill(openMenu(anchor, cls)); placeMenu(); },
    closeMenu, placeMenu };
}

/* The swatch popover (palette + opacity), reused by the floating toolbar and the Style tab below:
   `get()` reads the current colour, `set(newColor)` writes it (a live preview; the caller decides
   what "live" means). Same look as settings-dialog.js' own swatchMenu. */
function colorSwatchMenu(anchor, get, set) {
  pageMenuHost().toggleMenu(anchor, 'menu-swatch', (m) => {
    const grid = mk('div', 'sw-grid'), picks = [];
    for (const hex of S.PALETTE.flat()) {
      const b = mk('button', 'sw-cell');
      b.type = 'button';
      b.style.background = hex;
      b.title = hex;
      b.setAttribute('aria-label', hex);
      b.onclick = () => { set(S.withAlpha(hex, S.alphaOf(get()))); sync(); };
      picks.push([hex, b]);
      grid.append(b);
    }
    const opRow = mk('div', 'sw-row'), op = mk('input'), pct = mk('span', 'sw-pct');
    op.type = 'range'; op.min = '0'; op.max = '100'; op.step = '1';
    op.setAttribute('aria-label', 'Opacity');
    op.oninput = () => { set(S.withAlpha(S.hexOf(get()), Number(op.value) / 100)); sync(); };
    opRow.append(mk('span', '', 'Opacity'), op, pct);
    m.append(grid, opRow);
    function sync() {
      const c = get(), h = S.hexOf(c), a = Math.round(S.alphaOf(c) * 100);
      for (const [x, b] of picks) b.classList.toggle('on', x === h);
      op.value = String(a);
      pct.textContent = `${a}%`;
    }
    sync();
  });
}

/* Merges `patch` onto the drawing's saved color/locked/style (style fields renormalized for its
   type, so a bad value never lands) and saves it -- every chart of the symbol, and this one's
   toolbar/dialog through the usual drawings store subscription. */
function patchDrawing(root, id, patch) {
  const now = drawings.list(root).find((x) => x.id === id);
  if (!now) return null;
  const next = { ...now, ...patch };
  if (patch.style) next.style = DS.normalize(now.type, { ...DS.normalize(now.type, now.style), ...patch.style });
  drawings.replace(root, next);
  markDirty();
  return next;
}

/* ---- the floating toolbar: one per cell that has a selected trend/hline/rect/position ---- */
const drawToolbars = new Map();   // cell -> {el, key} ("key" = id|type, so a same-drawing refresh patches in place)

function closeDrawToolbar(cell) {
  const t = drawToolbars.get(cell);
  if (t) { t.el.remove(); drawToolbars.delete(cell); }
}
function closeAllDrawToolbars() { for (const cell of [...drawToolbars.keys()]) closeDrawToolbar(cell); }

function drawToolbarButtons(cell, root, d) {
  const wrap = mk('div', 'draw-toolbar');
  const btn = (name, title) => { const b = mk('button', 'dtb-btn'); b.type = 'button'; b.title = title; b.setAttribute('aria-label', title); b.append(icon(name)); return b; };
  if (!isPosDrawing(d)) {
    const tpl = btn('bookmark', 'Template');
    tpl.setAttribute('aria-haspopup', 'menu');
    tpl.onclick = () => window.HBPresets.menu(pageMenuHost(), tpl, {
      kind: `drawing:${d.type}`,
      current: () => DS.normalize(d.type, (drawings.list(root).find((x) => x.id === d.id) || d).style),
      apply(payload, { isDefault }) {
        patchDrawing(root, d.id, { style: payload });
        if (isDefault) drawStyleDefaults.set(d.type, payload);
      },
    });
    wrap.append(tpl, mk('span', 'dtb-sep'));
  }
  const sw = mk('button', 'dtb-swatch'), swi = mk('i');
  sw.type = 'button'; sw.title = 'Colour'; sw.setAttribute('aria-label', 'Colour');
  swi.style.background = d.color || '#2962FF';
  sw.append(swi);
  sw.onclick = () => colorSwatchMenu(sw,
    () => (drawings.list(root).find((x) => x.id === d.id) || d).color || '#2962FF',
    (c) => { patchDrawing(root, d.id, { color: c }); swi.style.background = c; });
  wrap.append(sw);
  if (!isPosDrawing(d)) {
    const style = DS.normalize(d.type, d.style);
    const w = mk('input', 'dtb-num');
    w.type = 'number'; w.min = '1'; w.max = '4'; w.step = '1'; w.value = String(style.width);
    w.title = 'Width'; w.setAttribute('aria-label', 'Width');
    w.onchange = () => { patchDrawing(root, d.id, { style: { width: Number(w.value) } }); w.value = String(DS.normalize(d.type, (drawings.list(root).find((x) => x.id === d.id) || {}).style).width); };
    const ls = mk('select', 'dtb-select');
    ls.setAttribute('aria-label', 'Line style');
    for (const [v, text] of [['solid', 'Solid'], ['dashed', 'Dashed'], ['dotted', 'Dotted']]) { const o = mk('option', '', text); o.value = v; ls.append(o); }
    ls.value = style.lineStyle;
    ls.onchange = () => patchDrawing(root, d.id, { style: { lineStyle: ls.value } });
    const gear = btn('gear', 'Settings');
    gear.onclick = () => drawingSettingsDialog(cell, d);
    wrap.append(w, ls, gear);
  }
  const lock = btn(d.locked ? 'lock' : 'lockOpen', d.locked ? 'Unlock' : 'Lock');
  lock.setAttribute('aria-pressed', String(!!d.locked));
  lock.onclick = () => patchDrawing(root, d.id, { locked: !d.locked });
  const del = btn('trash', 'Delete');
  del.classList.add('danger');
  del.onclick = () => { if (cell.dc) cell.dc.deleteSelected(); };
  wrap.append(mk('span', 'dtb-sep'), lock, del);
  return { el: wrap, focused: () => wrap.contains(document.activeElement) };
}

/* Positions the toolbar centred above the drawing's own handle points, kept inside the chart's own
   box (never the window: a chart near the page edge must not push it off-screen), a few px above
   the topmost handle -- the same geometry the selection's own handle dots use. */
function placeDrawToolbar(cell, el, d) {
  const dc = cell.dc, geo = dc && dc.geo();
  if (!geo) { el.style.visibility = 'hidden'; return; }
  const D_ = window.HBDrawings, hs = D_.handlePoints(d, geo);
  const anchor = hs && DS.toolbarAnchor(hs);
  if (!anchor) { el.style.visibility = 'hidden'; return; }
  el.style.visibility = '';
  const r = cell.box.getBoundingClientRect(), w = el.offsetWidth, h = el.offsetHeight;
  const x = Math.max(r.left + 2, Math.min(r.left + anchor.cx - w / 2, r.right - w - 2));
  const y = Math.max(r.top + 2, r.top + anchor.top - h - 10);
  el.style.left = `${x}px`;
  el.style.top = `${y}px`;
}

/* Controller#refresh calls this on every selection-affecting change (host.onSelectionChanged): a
   drawing (re)selected, deselected, moved, restyled. A same-drawing refresh patches the existing
   toolbar's lock icon in place and repositions it -- it never rebuilds while one of its own inputs
   has focus (GOTCHAS: never rebuild a container while an input inside it has focus). */
function syncDrawToolbar(cell, d) {
  if (!d) { closeDrawToolbar(cell); return; }
  const root = cell.dc ? cell.dc.root : cell.cfg.root, key = `${d.id}|${d.type}`;
  let t = drawToolbars.get(cell);
  if (t && t.key === key) {
    if (!t.focused()) {
      const lock = t.el.querySelector('.dtb-btn[aria-pressed]');
      if (lock) { lock.innerHTML = ''; lock.append(icon(d.locked ? 'lock' : 'lockOpen')); lock.setAttribute('aria-pressed', String(!!d.locked)); lock.title = d.locked ? 'Unlock' : 'Lock'; }
      const sw = t.el.querySelector('.dtb-swatch i');
      if (sw) sw.style.background = d.color || '#2962FF';
    }
  } else {
    closeDrawToolbar(cell);
    const built = drawToolbarButtons(cell, root, d);
    $('#menuRoot').appendChild(built.el);
    t = { el: built.el, key, focused: built.focused };
    drawToolbars.set(cell, t);
  }
  placeDrawToolbar(cell, t.el, d);
}

/* Double-click on a trend/hline/rect: its own settings dialog -- Style / Text tabs, live preview
   (through the same drawings store every chart of the symbol shares), OK keeps it, Cancel/×/Esc/a
   backdrop click put it back exactly as it was, and a Template ▾ at the bottom-left (the same menu
   the floating toolbar's Template button opens). */
function drawingSettingsDialog(cell, d0) {
  const root = cell.dc ? cell.dc.root : cell.cfg.root;
  const orig = drawings.list(root).find((x) => x.id === d0.id);
  if (!orig) return;
  const atOpen = { color: orig.color || '#2962FF', style: DS.normalize(orig.type, orig.style) };
  let work = { ...atOpen, style: { ...atOpen.style } }, tab = 'style', done = false;
  const title = { trend: 'Trend line', rect: 'Rectangle', hline: 'Horizontal line' }[orig.type] || 'Drawing';
  const box = openDialog(title, 'drawstyle');
  const body = mk('div', 'set-body'), tabs = mk('div', 'set-tabs'), pane = mk('div', 'set-pane'), foot = mk('div', 'set-foot');
  body.append(tabs, pane);
  box.append(body, foot);

  function preview() { patchDrawing(root, d0.id, { color: work.color, style: work.style }); }
  function set(patch) { work = { ...work, ...patch }; preview(); }
  function setStyle(patch) { work = { ...work, style: DS.normalize(orig.type, { ...work.style, ...patch }) }; preview(); renderPane(); }

  function row(label, ctl) { const el = mk('div', 'set-row'), name = mk('div', 'set-name', label), c = mk('div', 'set-ctl'); c.append(ctl); el.append(name, c); return el; }
  function colorCtl(get, setv) {
    const b = mk('button', 'swatch'), i = mk('i');
    i.style.background = get();
    b.append(i);
    b.onclick = () => colorSwatchMenu(b, get, (c) => { setv(c); i.style.background = c; });
    return b;
  }
  function numberCtl(val, min, max, onchange) {
    const n = mk('input', 'set-num');
    n.type = 'number'; n.min = String(min); n.max = String(max); n.step = '1'; n.value = String(val);
    n.onchange = () => onchange(Math.max(min, Math.min(max, Math.round(Number(n.value)) || min)));
    return n;
  }
  function selectCtl(val, choices, onchange) {
    const s = mk('select', 'set-select');
    for (const [v, text] of choices) { const o = mk('option', '', text); o.value = v; s.append(o); }
    s.value = val;
    s.onchange = () => onchange(s.value);
    return s;
  }
  function checkCtl(val, onchange) {
    const c = mk('input'); c.type = 'checkbox'; c.checked = !!val; c.onchange = () => onchange(c.checked);
    return c;
  }
  function textCtl(val, onchange) {
    const inp = mk('input', 'menu-input'); inp.type = 'text'; inp.maxLength = DS.MAX_TEXT; inp.value = val;
    inp.oninput = () => onchange(inp.value);
    return inp;
  }

  function renderTabs() {
    tabs.replaceChildren(...[['style', 'Style'], ['text', 'Text']].map(([id, label]) => {
      const b = mk('button', 'set-tab' + (id === tab ? ' active' : ''), label);
      b.type = 'button';
      b.onclick = () => { if (tab !== id) { tab = id; renderTabs(); renderPane(); } };
      return b;
    }));
  }
  function renderPane() {
    const rows = [];
    if (tab === 'style') {
      rows.push(mk('div', 'set-cap', 'LINE'));
      rows.push(row('Colour', colorCtl(() => work.color, (c) => set({ color: c }))));
      rows.push(row('Width', numberCtl(work.style.width, 1, 4, (v) => setStyle({ width: v }))));
      rows.push(row('Style', selectCtl(work.style.lineStyle, [['solid', 'Solid'], ['dashed', 'Dashed'], ['dotted', 'Dotted']], (v) => setStyle({ lineStyle: v }))));
      if (orig.type === 'trend') {
        rows.push(row('Extend left', checkCtl(work.style.extendLeft, (v) => setStyle({ extendLeft: v }))));
        rows.push(row('Extend right', checkCtl(work.style.extendRight, (v) => setStyle({ extendRight: v }))));
      }
      if (orig.type === 'rect') {
        rows.push(mk('div', 'set-cap', 'FILL'));
        rows.push(row('Fill', colorCtl(() => work.style.fillColor, (c) => setStyle({ fillColor: c }))));
      }
      if (orig.type === 'hline') rows.push(row('Price label', checkCtl(work.style.axisLabel, (v) => setStyle({ axisLabel: v }))));
    } else {
      rows.push(mk('div', 'set-cap', 'TEXT'));
      rows.push(row('Text', textCtl(work.style.text, (v) => setStyle({ text: v }))));
      rows.push(row('Font size', numberCtl(work.style.fontSize, 10, 28, (v) => setStyle({ fontSize: v }))));
      rows.push(row('Colour', colorCtl(() => work.style.textColor, (c) => setStyle({ textColor: c }))));
      rows.push(row('Bold', checkCtl(work.style.bold, (v) => setStyle({ bold: v }))));
      const posChoices = DS.LABEL_POS[orig.type].map((p) => [p, p[0].toUpperCase() + p.slice(1)]);
      rows.push(row('Position', selectCtl(work.style.labelPos, posChoices, (v) => setStyle({ labelPos: v }))));
    }
    pane.replaceChildren(...rows);
  }

  const tpl = button('btn btn-ghost tpl-btn'), chev = mk('span', 'icw sm');
  chev.innerHTML = I.chevron;
  tpl.append(mk('span', '', 'Template'), chev);
  tpl.setAttribute('aria-haspopup', 'menu');
  tpl.onclick = () => window.HBPresets.menu(pageMenuHost(), tpl, {
    kind: `drawing:${orig.type}`,
    current: () => work.style,
    apply(payload, { isDefault }) {
      work = { ...work, style: DS.normalize(orig.type, payload) };
      preview();
      renderPane();
      if (isDefault) drawStyleDefaults.set(orig.type, payload);
    },
  });
  const grow = mk('span', 'grow'), cancel = button('btn btn-ghost', 'Cancel'), ok = button('btn btn-solid', 'OK');
  cancel.onclick = () => closeDialog();
  ok.onclick = () => { done = true; closeDialog(); };
  foot.append(tpl, grow, cancel, ok);
  dlg.onClose = () => { if (!done) patchDrawing(root, d0.id, { color: atOpen.color, style: atOpen.style }); };

  renderTabs();
  renderPane();
}

/* The chart Settings dialog (settings-dialog.js): the toolbar gear opens it for the selected chart, a per-chart
   gear or the chart menu's Settings… for that chart. */
function chartSettings(c = cur(), tab = null) {
  if (!c) return;
  select(cells.indexOf(c));
  const box = openDialog('Settings', 'settings');
  const ctl = window.HBSettingsDialog.mount(box, {
    cell: c,
    tab,                  // which tab to open on: the order panel's "Change" asks for 'trading'
    cells: () => cells,
    templates,
    tradeBits: (x) => T.tradeBits(x.cfg),                               // Task 2: what a template save adds
    applyTrade: (x, raw) => applyTemplateTrade(x, raw, { quiet: true }),  // a template Apply (saved on Ok)
    restoreTrade: restoreTemplateTrade,                                   // Cancel
    // Task 3: the Algo select -- the desk's strategies on this chart's root, plus (paper Task 2) any paper
    // strategy on it ("paper:<id>"); a pick previews live, saved on Ok, and ticks the accounts it books
    algoChoices: (x) => T.algoChoices(window.HBDeskClient.state, x.cfg.root, x.cfg.algo, window.HBPaperClient ? window.HBPaperClient.strategies() : []),
    setAlgo: (x, v) => window.HBTradeUI.pickAlgo(x, v || null, { quiet: true }),
    // 2026-09-27 accounts-per-chart plan, Task 1: the Trading tab's ACCOUNTS list and the all-charts defaults.
    // Every rule (the two-step LIVE arm, an unlisted account failing closed, the algo binding) is HBTradeUI's.
    accountRows: (x) => window.HBTradeUI.accountRows(x),
    // Task 2b: the ACCOUNTS list's "+ Add paper account" (the chart service's own route; its push adds the row)
    createPaperAccount: (name, bal) => window.HBPaperClient.createAccount(name, bal),
    toggleAccount: (x, id) => window.HBTradeUI.toggleAccount(x, id, { quiet: true }),
    armPending: () => window.HBTradeUI.armPending(),
    tradeWhy: (x) => { const m = window.HBTradeUI.effectiveMode(x); return m.mode === 'on' ? '' : m.reason; },
    prefs: () => window.HBDeskClient.prefs,
    setPrefs: (patch) => window.HBDeskClient.setPrefs(patch),
    // the Trading tab re-reads on a tick / LIVE arm AND on a desk change (a new account list, one going
    // not-tradable): both, since the dialog must never show a row the desk no longer backs
    onTradeChange: (fn) => {
      const offTrade = window.HBTradeUI.onTradeChange(fn);
      const offDesk = window.HBDeskClient.on((why) => { if (why.has('state') || why.has('account')) fn(); });
      return () => { offTrade(); offDesk(); };
    },
    countries: () => [...new Set(calendar.map((e) => e.country))].sort(),
    toggleMenu(anchor, cls, fill) {   // menus and popovers open inside the dialog (above its backdrop)
      if (menuAnchor === anchor) { closeMenu(); return; }
      fill(openMenu(anchor, cls, { root: box }));
      placeMenu();
    },
    closeMenu,
    placeMenu,
    commit(changed) {   // Ok: the layout keeps the changes and reads Unsaved until saved
      if (changed) markDirty();
      closeDialog();
    },
    cancel: closeDialog,
  });
  dlg.onClose = ctl.revert;   // Cancel, ×, Esc, a backdrop click: every chart back (a no-op after Ok)
}

/* ---- the chart's context menu (spec §7) ---- */
/* The built-in items' actions (HBChartMenu items carry `act`; an extension's carry their own run). */
const MENU_ACTS = {
  reset: (ctx) => ctx.cell.resetView(),
  copy: (ctx, it) => {   // silent when the clipboard is unavailable or refused
    try { navigator.clipboard.writeText(it.copy).catch(() => {}); } catch (_) { /* no clipboard */ }
  },
  removeDrawings: (ctx) => drawings.clear(ctx.root),
  removeIndicators: (ctx) => { ctx.cell.update({ indicators: [] }); markDirty(); },
  toggleIndicators: (ctx) => {
    const show = ctx.allIndicatorsHidden;   // all hidden already: this shows them again, else it hides them
    ctx.cell.update({ indicators: ctx.cell.cfg.indicators.map((x) => ({ ...x, visible: show })) });
    markDirty();
  },
  settings: (ctx) => chartSettings(ctx.cell),
};

/* Right-click on a chart's price pane, or a double-click on its empty space: the chart menu at the pointer, for
   that chart (it becomes the selected one). Remove N drawings asks twice, like the rail's Remove all: the first
   click arms it for 3 s (the menu stays open), the second removes. Chart template (spec §8) is not one of
   HBChartMenu's built-ins (it needs a network fetch and its own submenu): it is spliced in here, right before
   Settings…. */
function chartMenu(cell, at) {
  const i = cells.indexOf(cell);
  if (i < 0) return;
  select(i);
  const root = cell.shown ? cell.shown.root : cell.cfg.root;
  const ctx = { cell, root, price: at.price, tick: cell.tick, nDrawings: drawings.list(root).length,
    nIndicators: cell.cfg.indicators.length,
    allIndicatorsHidden: cell.cfg.indicators.length > 0 && cell.cfg.indicators.every((x) => x.visible === false) };
  const m = openMenu(null, 'menu-chart', { at });
  let armed = 0;
  for (const it of window.HBChartMenu.items(ctx)) {
    if (it.sep) { m.appendChild(mk('div', 'menu-sep')); continue; }
    if (it.act === 'settings') {
      const tpl = menuItem('Chart template', '›', () => chartTemplateMenu(cell, at));
      tpl.setAttribute('aria-haspopup', 'menu');
      m.appendChild(tpl);
    }
    const b = menuItem(it.text, it.sub || '', () => {
      if (it.disabled) return;   // task-2-review.md Minor 3: an item greyed out by its own provider (e.g. a
                                  // practice Buy/Sell while already in a position) never runs, even from the
                                  // keyboard -- native `disabled` already blocks the mouse (set just below).
      if (it.act === 'removeDrawings' && !armed) {
        b.classList.add('arm');
        b.querySelector('.menu-t').textContent = window.HBChartMenu.armText(ctx.nDrawings, root);
        armed = setTimeout(() => { armed = 0; b.classList.remove('arm'); b.querySelector('.menu-t').textContent = it.text; }, 3000);
        return;
      }
      clearTimeout(armed);
      closeMenu();
      if (it.run) {
        try { it.run(ctx); } catch (e) { sbNote(`menu: ${e && e.message ? e.message : e}`); }
        return;
      }
      if (MENU_ACTS[it.act]) MENU_ACTS[it.act](ctx, it);
    });
    if (it.disabled) { b.disabled = true; b.setAttribute('aria-disabled', 'true'); }
    m.appendChild(b);
  }
  placeMenu();
  m.tabIndex = -1;   // the arrow keys start from the menu
  m.focus({ preventScroll: true });
}

/* An indicator's own menu: from its legend ⋯ (anchor; a second click closes it) or a right-click in its pane (at). */
function indicatorMenu(cell, uid, { anchor = null, at = null } = {}) {
  if (anchor && menuAnchor === anchor) { closeMenu(); return; }
  const inst = cell.cfg.indicators.find((x) => x.uid === uid), i = cells.indexOf(cell);
  if (!inst || i < 0) return;
  select(i);
  const m = openMenu(anchor, 'menu-ind', { at });
  for (const it of window.HBChartMenu.paneItems(inst)) {
    m.appendChild(menuItem(it.text, '', () => {
      closeMenu();
      if (it.act === 'move') { cell.setPlacement(uid, it.pane); markDirty(); } else cell.removeIndicator(uid);
    }));
  }
  placeMenu();
  if (at) { m.tabIndex = -1; m.focus({ preventScroll: true }); }
}

/* Applying a saved chart template (spec §8) to one chart from the chart menu: settings, then indicators/interval
   if the template stored them (fresh uids), and the layout reads Unsaved — the Settings dialog's own Template ▾
   marks it dirty through the usual Ok/commit path; this one applies straight to the chart, so it says so itself. */
function applyChartTemplate(cell, raw) {
  const t = S.applyTemplate(raw);
  cell.setSettings(t.settings);
  const patch = {};
  if (t.indicators) patch.indicators = t.indicators;
  if (t.spec) patch.spec = t.spec;
  if (Object.keys(patch).length) cell.update(patch);
  applyTemplateTrade(cell, raw);   // its accounts (Trading off) and algo, when the template stored them
  markDirty();
}

/* Chart menu -> Chart template ›: save this chart (its settings and, unless unticked, its indicators — fresh
   uids on apply) as a named template, or apply a saved one back to this chart only. Reuses the page's own
   templates client (`templates`, shared with the Settings dialog: GET/PUT/DELETE /api/templates). */
function chartTemplateMenu(cell, at) {
  const m = openMenu(null, 'menu-chart menu-tpl', { at });
  const back = menuItem('‹ Chart template', '', () => chartMenu(cell, at));
  const saveRow = menuItem('Save this chart as template…', '', () => {});
  const list = mk('div'), err = mk('div', 'menu-err');
  err.hidden = true;
  err.setAttribute('role', 'alert');
  m.append(back, mk('div', 'menu-sep'), saveRow, mk('div', 'menu-sep'), list, err);
  const fail = (text) => { err.textContent = text; err.hidden = false; placeMenu(); };
  let names = new Set();
  // the "Replace?" check below only means anything once `names` holds the real list -- a Save clicked (or
  // Enter pressed) while it is still loading used to see an empty set and save straight over an existing
  // template with the same name. The inline Save button stays disabled until the list settles.
  let loaded = false, goBtn = null;
  saveRow.onclick = () => {
    const rowEl = mk('div', 'menu-custom'), input = mk('input', 'menu-input'), go = mk('button', 'btn btn-primary', 'Save');
    go.type = 'button';
    go.disabled = !loaded;
    goBtn = go;
    input.type = 'text'; input.placeholder = 'Template name'; input.maxLength = 40; input.spellcheck = false;
    input.setAttribute('aria-label', 'Template name');
    const doSave = async () => {
      const name = input.value.trim();
      const body = { ...S.buildTemplate({ settings: cell.settings(), indicators: cell.cfg.indicators, spec: cell.cfg.spec }),
        ...T.tradeBits(cell.cfg) };   // Task 2: the chart's accounts and algo too (never its Trading switch)
      const res = await templates.save(name, body);
      if (res) { fail(res); return; }
      names.add(name);
      closeMenu();
    };
    const save = () => {
      if (!loaded) return;   // guards Enter too: the button being disabled is not the only way in
      const name = input.value.trim(), why = S.templateNameError(name);
      if (why) { fail(why); input.focus(); return; }
      if (names.has(name)) {
        const ask = mk('div', 'menu-confirm'), yes = mk('button', 'btn btn-danger', 'Replace'), no = mk('button', 'btn btn-ghost', 'Cancel');
        yes.type = 'button'; no.type = 'button';
        ask.append(mk('span', '', `Replace “${name}”?`), yes, no);
        rowEl.replaceWith(ask);
        no.focus();
        no.onclick = () => { ask.replaceWith(rowEl); input.focus(); };
        yes.onclick = doSave;
        return;
      }
      doSave();
    };
    go.onclick = save;
    input.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); save(); } };
    rowEl.append(input, go);
    saveRow.replaceWith(rowEl);
    input.focus();
  };
  list.append(mk('div', 'menu-empty', 'Loading…'));
  templates.list().then((all) => {
    if (!m.isConnected) return;   // closed meanwhile
    loaded = true;
    if (goBtn) goBtn.disabled = false;
    if (!all) { list.replaceChildren(); fail('could not load the templates'); return; }
    names = new Set(Object.keys(all));
    const ns = [...names].sort((a, b) => a.localeCompare(b));
    list.replaceChildren(...(ns.length ? ns.map((n) => menuItem(n, '', () => {
      closeMenu();
      applyChartTemplate(cell, all[n]);
    })) : [mk('div', 'menu-empty', 'No saved templates')]));
    placeMenu();
  });
  placeMenu();
  m.tabIndex = -1;
  m.focus({ preventScroll: true });
}

/* ---- drawing rail ---- */
function setTool(t) {
  tool = t;
  for (const b of document.querySelectorAll('#rail [data-tool]')) b.setAttribute('aria-pressed', String(b.dataset.tool === t));
  for (const c of cells) if (c.dc) c.dc.toolChanged();
  syncCrosshair();
}

function sbNote(text) {
  const el = $('#sbNote');
  el.textContent = text;
  clearTimeout(noteTimer);
  noteTimer = setTimeout(() => { el.textContent = ''; }, 8000);
}

function showTip(anchor, text) {
  const tip = $('#railTip'), r = anchor.getBoundingClientRect();
  tip.textContent = text;
  tip.hidden = false;
  tip.style.left = `${r.right + 8}px`;
  tip.style.top = `${r.top + r.height / 2 - tip.offsetHeight / 2}px`;
}

function disarm() {
  clearTimeout(armTimer);
  $('#railClear').classList.remove('arm');
  $('#railTip').hidden = true;
}

/* Remove every drawing on the selected chart's symbol: the first click arms, the second (within 3 s) removes.
   The second click must be on the symbol the tip named: another one (the selection moved) arms again for it. */
function clearDrawings() {
  const c = cur(), btn = $('#railClear');
  if (!c) return;
  const root = c.shown ? c.shown.root : c.cfg.root, n = drawings.list(root).length;
  if (btn.classList.contains('arm') && root === armRoot) { disarm(); drawings.clear(root); return; }
  disarm();
  if (!n) { showTip(btn, `No drawings on ${root}`); armTimer = setTimeout(disarm, 1500); return; }
  btn.classList.add('arm');
  armRoot = root;
  showTip(btn, `Click again to remove ${n} drawing${n === 1 ? '' : 's'} on ${root}`);
  armTimer = setTimeout(disarm, 3000);
}

/* ---- magnet ---- */
function loadMagnet() {
  try { return window.HBDrawings.parseMagnet(localStorage.getItem('hb_charts_magnet')); }
  catch (_) { return { ...window.HBDrawings.MAGNET_OFF }; }
}
function setMagnet(next) {
  magnet = { on: !!next.on, mode: next.mode === 'strong' ? 'strong' : 'weak' };
  try { localStorage.setItem('hb_charts_magnet', JSON.stringify(magnet)); } catch (_) { /* storage off */ }
  renderMagnet();
  syncCrosshair();
}
function renderMagnet() {
  const b = $('#railMagnet'), tip = magnet.on ? `Magnet (${magnet.mode})` : 'Magnet off';
  b.setAttribute('aria-pressed', String(magnet.on));
  b.title = tip;
  b.setAttribute('aria-label', tip);
}
/* The selected chart's crosshair snaps like the magnet while it is on and a drawing tool is picked. */
function syncCrosshair() {
  cells.forEach((c, k) => c.setMagnetCrosshair(magnet.on && tool !== 'cursor' && k === selected));
}
/* The corner triangle's flyout: Weak / Strong, a check on the current mode; picking one turns the magnet on. */
function magnetMenu() {
  const m = openMenu($('#railMagnetMore'), 'menu-magnet', { right: true });
  for (const [mode, text] of [['weak', 'Weak magnet'], ['strong', 'Strong magnet']]) {
    const b = menuItem(text, '', () => { closeMenu(); setMagnet({ on: true, mode }); }, false), ck = icon('check');
    ck.classList.add('menu-ck');
    if (magnet.mode !== mode) ck.style.visibility = 'hidden';
    b.setAttribute('role', 'menuitemradio');
    b.setAttribute('aria-checked', String(magnet.mode === mode));
    b.prepend(ck);
    m.appendChild(b);
  }
}

/* ---- economic calendar ---- */
/* The calendar from the chart service: loaded once, then again whenever the service fetched anew. */
async function loadCalendar() {
  try {
    const r = await fetch('/api/calendar');
    if (!r.ok) return;
    const v = await r.json();
    calendar = Array.isArray(v) ? v : [];
  } catch (_) { return; }
  for (const c of cells) c.redrawEvents();
  renderNextEvent();
}

/* Now in epoch ms: a replay's clock in a replay (so its "Next" matches its charts), else the browser's. */
function clockMs() {
  const et = clockEt();
  return replayClock ? et - S.zoneOffsetMs('America/New_York', et) : Date.now();
}

/* The status bar's "Next USD: CPI m/m 08:30 (in 2h 14m)": the next event the selected chart shows. */
function renderNextEvent() {
  const el = $('#sbEvent'), c = cur(), E = window.HBEvents;
  const n = c ? E.nextText(E.shown(calendar, c.R), clockMs()) : null;
  el.hidden = !n;
  if (n) { el.textContent = n.text; el.style.color = n.color; }
}

/* ---- bottom bar ---- */
function showStatus(s) {
  if (s.mode === 'replay') replayClock = { etMs: (s.clock_s || 0) * 1000, at: Date.now(), speed: s.speed || 1, done: !!s.done };
  else if (s.mode === 'live') replayClock = null;
  if (s.calendar && s.calendar.fetched_at !== calendarAt) { calendarAt = s.calendar.fetched_at; loadCalendar(); }
  const now = etNow(), f = C.feedSummary(s, now.weekday, now.minutes), rec = s.recorder;
  $('#sbDot').className = 'sb-dot' + (f.dot ? ' ' + f.dot : '');
  $('#sbMode').textContent = s.mode === 'replay'
    ? `Replay ${s.date} ×${s.speed} · ${iso(s.clock_s || 0).slice(11, 19)} ET${s.done ? ' · done' : ''}`
    : s.mode === 'live' ? `Live · md ${s.md || ''}` : 'Disconnected';
  const feed = $('#sbFeed');
  feed.textContent = f.text;
  feed.title = f.title;
  feed.className = 'sb-feed' + (f.textClass ? ' ' + f.textClass : '');
  const budget = $('#sbBudget');
  budget.textContent = s.mode === 'live' ? `md ${s.budget_hour ?? 0}/180` : '';
  budget.title = s.mode === 'live' ? `Chart requests this hour on the md login (limit 180) · ${s.clients ?? 0} page(s)` : '';
  const recEl = $('#sbRec');
  recEl.textContent = s.mode === 'live' && rec ? `rec buffered ${rec.buffered.toLocaleString('en-US')}` : '';
  recEl.classList.toggle('warn', !!(rec && rec.buffered >= C.REC_BUSY));
  statusLine = feed.textContent;
}

/* The socket is open but no status came for STATUS_STALE_S (the chart
   service is stuck, or its status broadcast is failing): grey the bar so a
   stale chart is never mistaken for a quiet market. A 'bad' dot stays bad. */
function greyIfStale() {
  if (!statusAt || !ws || ws.readyState !== 1) return;
  const age = (Date.now() - statusAt) / 1000;
  if (age < STATUS_STALE_S) return;
  const dot = $('#sbDot');
  if (!dot.classList.contains('bad')) dot.className = 'sb-dot warn';
  $('#sbFeed').textContent = `no status for ${Math.round(age)}s` + (statusLine ? ` · ${statusLine}` : '');
}

/* Now as ET wall-clock ms: a replay's own clock (run on at its speed between its 2 s status messages), else
   the browser's. The charts' countdowns run on it. */
function clockEt() {
  if (replayClock) return replayClock.etMs + (replayClock.done ? 0 : (Date.now() - replayClock.at) * replayClock.speed);
  const now = Date.now();
  return now + S.zoneOffsetMs('America/New_York', now);
}

function tick() {
  $('#sbClock').textContent = `${ET_CLOCK.format(new Date())} ET`;
  greyIfStale();
  const et = clockEt();
  for (const c of cells) c.tickSecond(et);
  renderNextEvent();
}

/* ---- the chart service ---- */
function connect() {
  ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen = () => {
    statusAt = Date.now();
    window.HBReplayUI.onReconnect(cells);   // a fresh connection carries no replay sessions from the old one
    for (const c of cells) { c.clearInflight(); c.subscribe(true); }
  };
  ws.onmessage = (e) => {
    let m;
    try { m = JSON.parse(e.data); } catch (_) { return; }
    if (m.type === 'status') { statusAt = Date.now(); showStatus(m); return; }
    if (m.type === 'desk' || m.type === 'quote') { window.HBDeskClient.onMessage(m); return; }
    if (m.type === 'paper') { window.HBPaperClient.onMessage(m); return; }
    if (m.type === 'paperbook') { window.HBPaperClient.onBook(m); window.HBDeskClient.bookChanged(); return; }   // the PAPER account
    if (m.type === 'depth') { window.HBDomUI.onDepth(m); window.HBL2Layer.onDepth(m); window.HBLiquidity.onDepth(m); return; }
    if (m.type === 'news' || m.type === 'burst' || m.type === 'burst_update') { window.HBNewsUI.onMessage(m); return; }
    if (m.type === 'tester_show') { window.HBTesterUI.show(m); return; }   // Claude's "show on chart" (POST /api/tester/show)
    const c = cells.find((x) => x.id === m.id);
    if (!c) return;
    if (m.type === 'history') c.onHistory(m);
    else if (m.type === 'older') c.onOlder(m);
    else if (m.type === 'update') { c.onUpdate(m); if (c.replay) window.HBReplayUI.onBarUpdate(c, m); }
    else if (m.type === 'reset') c.subscribe(true);
    else if (m.type === 'error') c.onError(m.error);
    else if (m.type === 'replay_state') window.HBReplayUI.onState(c, m);
    else if (m.type === 'replay_error') window.HBReplayUI.onError(c, m);
  };
  ws.onclose = () => {
    showStatus({ connected: false, error: 'chart service unreachable — retrying' });
    // the books went with the socket: the ladder says "Book stale", the lines go, the heatmap leaves a gap
    window.HBDomUI.onDisconnect(); window.HBL2Layer.onDisconnect(); window.HBLiquidity.onDisconnect();
    setTimeout(connect, 2000);
  };
}

/* ---- keyboard ---- */
function onKey(e) {
  if (dlg) {
    if (e.key === 'Escape') { e.preventDefault(); if (menuEl) closeMenu(); else closeDialog(); }
    else if (e.key === 'Tab') trapTab(e);
    return;
  }
  if (e.key === 'Escape' && menuEl) { e.preventDefault(); closeMenu(); return; }
  if (e.target.closest && e.target.closest('input, textarea, select, [contenteditable="true"]')) return;
  const c = cur();
  if (menuEl && ['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(e.key)) {   // walk the open menu's items
    const items = [...menuEl.querySelectorAll('.menu-i')].filter((b) => !b.disabled && b.offsetParent !== null);
    const k = window.HBChartMenu.step(items.indexOf(document.activeElement), items.length, e.key);
    if (k >= 0) { e.preventDefault(); items[k].focus(); }
    return;
  }
  // TradingView-style bare-key hotkeys: a digit opens the timeframe box, a letter opens symbol search -- never
  // while a menu is open (menuEl; dlg already returned above) or a modifier is held (so Alt+R, Ctrl/Cmd
  // shortcuts and Bar Replay's own Space/-> stay untouched -- those aren't single digits/letters anyway).
  if (c && !menuEl && !hotkeyBox && !e.ctrlKey && !e.metaKey && !e.altKey) {
    if (/^[0-9]$/.test(e.key)) { e.preventDefault(); openTimeframeBox(c, e.key); return; }
    if (/^[a-zA-Z]$/.test(e.key)) { e.preventDefault(); openSymbolBox(c, e.key); return; }
  }
  if (e.altKey && !e.metaKey && !e.ctrlKey && e.code === 'KeyR') {   // ⌥R: Reset chart view (e.key is ® on macOS)
    e.preventDefault();
    if (c) c.resetView();
    return;
  }
  // Space plays/pauses, → steps -- only the selected cell while it replays, no input focused (returned above), no
  // menu / hotkey box open, and never a key aimed at the order panel (its send button owns Space itself)
  if (c && c.replay && !menuEl && !hotkeyBox && !(e.target.closest && e.target.closest('#opanel'))) {
    if (e.code === 'Space') { e.preventDefault(); window.HBReplayUI.togglePlay(c); return; }
    if (e.key === 'ArrowRight') { e.preventDefault(); window.HBReplayUI.step(c); return; }
  }
  if (e.key === 'Escape') {
    if (c && c.dc) c.dc.escape();
    if (tool !== 'cursor') setTool('cursor');
  } else if ((e.key === 'Delete' || e.key === 'Backspace') && c && c.dc && c.dc.deleteSelected()) {
    e.preventDefault();
  }
}

async function init() {
  for (const n of document.querySelectorAll('[data-icon]')) n.innerHTML = I[n.dataset.icon] || '';
  $('#tbDesk').href = `${location.protocol}//${location.hostname}:8850/`;
  try { const r = await fetch('/api/symbols'); if (r.ok) meta = await r.json(); } catch (_) { /* keep the fallback */ }
  loadLast();
  $('#tbSymbol').onclick = () => toggleMenu($('#tbSymbol'), symbolMenu);
  $('#tbIntervals').onclick = () => toggleMenu($('#tbIntervals'), intervalMenu);
  $('#tbIndicators').onclick = indicatorsDialog;
  $('#tbGrid').onclick = () => toggleMenu($('#tbGrid'), gridMenu);
  $('#tbSettings').onclick = () => chartSettings();
  $('#tbTheme').onclick = toggleTheme;
  $('#tbDom').onclick = () => window.HBOrderPanel.openTab('dom');
  for (const b of document.querySelectorAll('#rail [data-tool]')) {
    b.onclick = () => setTool(b.dataset.tool === tool && tool !== 'cursor' ? 'cursor' : b.dataset.tool);
  }
  $('#railClear').onclick = clearDrawings;
  $('#railMagnet').onclick = () => setMagnet({ ...magnet, on: !magnet.on });
  $('#railMagnetMore').onclick = () => toggleMenu($('#railMagnetMore'), magnetMenu);
  renderMagnet();
  document.addEventListener('pointerdown', (e) => {
    if (menuEl && !menuEl.contains(e.target) && !(menuAnchor && menuAnchor.contains(e.target))) closeMenu();
    if (hotkeyBox && !hotkeyBox.el.contains(e.target)) closeHotkeyBox();
  }, true);
  window.addEventListener('resize', closeMenu);
  window.addEventListener('resize', closeHotkeyBox);
  document.addEventListener('keydown', onKey);
  page = {
    mk, icon, $, cells: () => cells, cur, select: (c) => select(cells.indexOf(c)),
    openDialog, closeDialog, setDialogClose(fn) { if (dlg) dlg.onClose = fn; }, dialogOpen: () => !!dlg,
    openMenu, closeMenu, placeMenu, toggleMenu, menuItem, sbNote, clockMs, chartSettings,
    deskUrl: () => `${location.protocol}//${location.hostname}:8850/`,
    overlays: [],
    // a chart's trade config changed (HBTradeUI.setCellTrade): an account-list change is a layout change (Unsaved);
    // the switch alone is not saved as "on" anywhere a load could bring back (loadedTrade)
    tradeChanged(cell, accountsChanged) { if (accountsChanged) markDirty(); else saveLast(); },
  };
  page.overlays.push(window.HBTradeLines.overlay);   // Task 6: the per-chart Buy/Sell block, lines and markers
  page.overlays.push(window.HBReplayUI.overlay);     // Bar Replay: the floating control bar, dimming and REPLAY pill
  page.overlays.push(window.HBTesterLayer.overlay);  // Task 10: the tester's trades, plots and jump on the root's chart
  page.overlays.push(window.HBL2Layer.overlay);      // charts-l2-news-ui Task 2: big-order lines + the imbalance gauge
  page.overlays.push(window.HBLiquidity.overlay);    // charts-l2-news-ui Task 3: the liquidity heatmap behind the candles
  page.overlays.push(window.HBNewsUI.overlay);       // 2026-09-27 news-ui plan, Task 4: headline ticks + burst markers
  // M8 (tester review): HBTesterUI.mount registers the 'tester' tab via HBPanel.addTab, so it runs BEFORE
  // HBPanel.mount reads a saved {tab: 'tester'} -- otherwise a saved tester tab is not restored on reload.
  window.HBTesterUI.mount(page);               // Task 9
  window.HBNewsUI.mount(page);                 // 2026-09-27 news-ui plan, Task 4: registers the News tab
  window.HBPanel.mount(page);                 // Task 4
  window.HBTradeUI.mount(page);                // Task 5 (it also owns the desk's line in the status bar)
  window.HBOrderPanel.mount(page);             // order-panel plan Task 3: the right dock (follows the selected chart)
  window.HBReplayUI.mount(page);
  buildGrid();   // after the mounts: page.overlays must be filled before any cell's build() reads host.overlays()
  migrateTickedOnce();
  // Global Constraints: no LIVE account survives a load. The layout was restored before the desk answered, so
  // the drop is (re-)run every time its account list changes -- and once now, in case it already has.
  if (window.HBDeskClient) window.HBDeskClient.on((why) => { if (why.has('state') || why.has('account')) dropLiveAccounts(); });
  dropLiveAccounts();
  loadTabs();    // async: renderTabs() already painted the "+" from buildGrid's renderToolbar; this fills the rest
  loadDrawStyleDefaults();   // async: host.styleDefault() reads whatever has landed by the time a drawing is placed
  connect();
  tick();
  setInterval(tick, 1000);
}

window.HBCharts = { get cells() { return cells; }, get layout() { return layout; }, get selected() { return selected; }, select, buildGrid };
init();
})();
