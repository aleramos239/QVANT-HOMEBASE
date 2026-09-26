/* Homebase Charts — the page: layout and selection, the top toolbar (it
   acts on the selected chart), menus, the drawing rail (the tool, the
   magnet and the per-symbol drawings store), the websocket to the chart
   service (:8852) and the bottom bar. Each grid slot is an HBCell.Cell;
   the server computes everything, the page only draws. */
(() => {
'use strict';
const C = window.HBCatalog, I = window.HBIcons, S = window.HBSettings, { Cell } = window.HBCell;
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

const $ = (s, root = document) => root.querySelector(s);
const iso = (t) => new Date(t * 1000).toISOString();
function mk(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function icon(name) { const s = mk('span', 'icw'); s.innerHTML = I[name] || ''; return s; }   // our own static SVG strings
const cur = () => cells[selected];

/* ---- layout + selection ---- */
function starter(i) { const [root, spec] = START[i % START.length]; return { root, spec, indicators: C.defaults() }; }
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
    }
  } catch (_) { /* unreadable: start fresh */ }
}

/* A saved layout (localStorage or the server) as the page runs it: HBCatalog.migrateLayout gives each chart's
   {root, spec, indicators}; each chart's settings (HBSettings overrides, cleaned) are kept beside them. */
function readLayout(v) {
  const lay = C.migrateLayout(v), raw = v && Array.isArray(v.cells) ? v.cells : [];
  lay.cells.forEach((c, i) => {
    const s = raw[i] && raw[i].settings, o = S.overrides(s && typeof s === 'object' ? s : {});
    if (Object.keys(o).length) c.settings = o;
  });
  return lay;
}

function hostFor(id) {
  return {
    id,
    send(msg) { if (!ws || ws.readyState !== 1) return false; ws.send(JSON.stringify(msg)); return true; },
    onPick(cell) { select(cells.indexOf(cell)); },
    onLoaded,
    onRefused,
    onSettings(cell, uid) { settingsDialog(cell, uid); },
    onPosition(cell, d) { positionDialog(cell, d); },
    onChartMenu(cell, at) { chartMenu(cell, at); },
    onIndicatorMenu(cell, uid, o) { indicatorMenu(cell, uid, o); },
    changed() { saveLast(); renderToolbar(); },
    tool: () => tool,
    toolDone() { setTool('cursor'); },
    drawings,
    magnet: () => magnet,
    events: () => calendar,
    legendFolded,
    toggleLegendFolded,
  };
}

function buildGrid() {
  for (const c of cells) c.destroy();
  cells = [];
  const grid = $('#grid'), [cols, rows] = GRIDS[layout.grid] || GRIDS[4], n = cols * rows;
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
  select(Math.min(selected, n - 1));
}

function select(i) {
  if (i < 0 || i >= cells.length) return;
  selected = i;
  cells.forEach((c, k) => c.setSelected(k === i));
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
  $('#tbLayoutName').textContent = !layout.name ? 'Unsaved' : layout.dirty ? `${layout.name} · Unsaved` : layout.name;
}

/* One popup menu at a time: under its toolbar button, right of a rail button (right), or at the pointer (at: a
   context menu, anchor null). root: the element it is appended to (a dialog's box for in-dialog menus). */
function openMenu(anchor, cls, { right = false, root = null, at = null } = {}) {
  closeMenu();
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

function symbolMenu() {
  const m = openMenu($('#tbSymbol'), 'menu-sym'), input = mk('input', 'menu-input'), list = mk('div');
  input.type = 'text'; input.placeholder = 'Search'; input.spellcheck = false;
  input.setAttribute('aria-label', 'Search symbols');
  const render = () => {
    const q = input.value.trim().toUpperCase(), c = cur();
    const hits = meta.roots.filter((r) => !q || r.includes(q) || C.rootName(r).toUpperCase().includes(q));
    list.replaceChildren(...hits.map((r) => menuItem(r, C.rootName(r), () => {
      closeMenu();
      if (c.cfg.root !== r) c.update({ root: r });
    }, r === c.cfg.root)));
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

/* A custom interval the open menu sent is on screen: close the menu. */
function onLoaded(cell) {
  if (customWait && customWait.cell === cell && cell.shown.spec === customWait.spec) closeMenu();
}

/* The server refused a change (the cell already went back to its last good
   config): say why inline in the interval menu if that is where it came
   from, else in the chart's legend. */
function onRefused(cell, tried, text) {
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

/* ---- saved layouts ---- */
/* The saved layouts by name; null when they could not be read. */
async function fetchLayouts() {
  try { const r = await fetch('/api/layouts'); return r.ok ? await r.json() : null; } catch (_) { return null; }
}

/* PUT the current layout under `name`: '' when saved, else the reason. */
async function putLayout(name) {
  const body = { grid: layout.grid, cells: layout.cells.map(({ root, spec, indicators, settings }) =>
    (settings && Object.keys(settings).length ? { root, spec, indicators, settings } : { root, spec, indicators })) };
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

let saveMsgTimer = 0;
function saveMsg(text, err = false) {
  const m = $('#tbSaveMsg');
  m.textContent = text;
  m.classList.toggle('err', err);
  clearTimeout(saveMsgTimer);
  if (text && !err) saveMsgTimer = setTimeout(() => { m.textContent = ''; }, 2000);
}

/* Save to the loaded layout's name; with none yet, ask for one in the layouts menu. */
async function save() {
  if (!layout.name) { if (menuAnchor !== $('#tbLayout')) toggleMenu($('#tbLayout'), () => layoutMenu(true)); return; }
  const why = await putLayout(layout.name);
  if (!why && layout.dirty) { layout.dirty = false; saveLast(); renderToolbar(); }
  saveMsg(why || 'Saved', !!why);
}

function loadLayout(name, saved) {
  layout = { ...readLayout(saved), name, dirty: false };
  saveLast();
  selected = 0;
  buildGrid();
}

async function layoutMenu(saveAsFirst = false) {
  const m = openMenu($('#tbLayout'), 'menu-layouts'), list = mk('div'), err = mk('div', 'menu-err');
  err.hidden = true;
  err.setAttribute('role', 'alert');
  const saveAs = menuItem('Save layout as…', '', () => askName());
  m.append(mk('div', 'menu-h', 'Saved layouts'), list, mk('div', 'menu-sep'), saveAs, err);
  // inline in this menu; next to Save if the menu closed while the request was out
  const fail = (text) => { if (menuEl !== m) { saveMsg(text, true); return; } menuErr(err, text); placeMenu(); };

  function askName() {
    const row = mk('div', 'menu-custom'), input = mk('input', 'menu-input'), ok = mk('button', 'btn btn-primary', 'Save');
    input.type = 'text'; input.placeholder = 'Layout name'; input.maxLength = 80; input.value = layout.name;
    input.setAttribute('aria-label', 'Layout name');
    ok.type = 'button';
    const go = async () => {
      const name = input.value.trim(), saving = layout;
      if (!name) { input.focus(); return; }
      // the browser resolves /api/layouts/. and /.. as path steps: the PUT would miss the layout
      if (name === '.' || name === '..') { fail('“.” and “..” cannot be layout names'); input.focus(); return; }
      const why = await putLayout(name);
      if (why) { fail(why); return; }
      if (layout === saving) { layout.name = name; layout.dirty = false; saveLast(); renderToolbar(); }   // not a layout loaded meanwhile
      if (menuEl === m) closeMenu();
      saveMsg('Saved');
    };
    ok.onclick = go;
    input.onkeydown = (e) => { if (e.key === 'Enter') go(); };
    row.append(input, ok);
    saveAs.replaceWith(row);
    input.focus();
    input.select();
  }

  function confirmDelete(row, name) {
    const box = mk('div', 'menu-confirm'), yes = mk('button', 'btn btn-danger', 'Delete'), no = mk('button', 'btn btn-ghost', 'Cancel');
    const del = row.querySelector('.menu-del'), had = row.contains(document.activeElement);
    const back = () => { const f = box.contains(document.activeElement); box.replaceWith(row); if (f) del.focus(); };
    yes.type = 'button';
    no.type = 'button';
    box.append(mk('span', '', `Delete “${name}”?`), yes, no);
    row.replaceWith(box);
    if (had) no.focus();   // keyboard focus moves into the confirm (and back to × on Cancel)
    no.onclick = back;
    yes.onclick = async () => {
      let r = null;
      try { r = await fetch('/api/layouts/' + encodeURIComponent(name), { method: 'DELETE' }); } catch (_) { /* r stays null */ }
      if (!r || !r.ok) { back(); fail(`delete failed${r ? ` (${r.status})` : ': network error'}`); return; }
      const f = box.contains(document.activeElement), near = box.nextElementSibling || box.previousElementSibling;
      box.remove();
      if (layout.name === name) { layout.name = ''; saveLast(); renderToolbar(); }
      // a row waiting in its own delete confirm is still a saved layout
      if (!list.querySelector('.menu-row, .menu-confirm')) list.replaceChildren(mk('div', 'menu-empty', 'No saved layouts yet'));
      if (f) { const to = (near && near.querySelector('.menu-i')) || m.querySelector('.menu-i, .menu-input'); if (to) to.focus(); }
    };
  }

  if (saveAsFirst) askName();
  const all = await fetchLayouts();
  if (menuEl !== m) return;   // closed while loading
  if (!all) { fail('could not load the saved layouts'); return; }
  const names = Object.keys(all).sort((a, b) => a.localeCompare(b));
  if (!names.length) list.appendChild(mk('div', 'menu-empty', 'No saved layouts yet'));
  for (const name of names) {
    const row = mk('div', 'menu-row'), del = mk('button', 'menu-del');
    del.type = 'button';
    del.title = `Delete ${name}`;
    del.setAttribute('aria-label', `Delete ${name}`);
    del.appendChild(icon('x'));
    del.onclick = () => confirmDelete(row, name);
    row.append(menuItem(name, '', () => { closeMenu(); loadLayout(name, all[name]); }, name === layout.name), del);
    list.appendChild(row);
  }
  placeMenu();
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

/* The toolbar gear: the chart Settings dialog for the selected chart (settings-dialog.js). */
function chartSettings() {
  const c = cur();
  if (!c) return;
  const box = openDialog('Settings', 'settings');
  const ctl = window.HBSettingsDialog.mount(box, {
    cell: c,
    cells: () => cells,
    templates,
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
  settings: () => chartSettings(),
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
      const body = S.buildTemplate({ settings: cell.settings(), indicators: cell.cfg.indicators, spec: cell.cfg.spec });
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
  ws.onopen = () => { statusAt = Date.now(); for (const c of cells) { c.clearInflight(); c.subscribe(true); } };
  ws.onmessage = (e) => {
    let m;
    try { m = JSON.parse(e.data); } catch (_) { return; }
    if (m.type === 'status') { statusAt = Date.now(); showStatus(m); return; }
    const c = cells.find((x) => x.id === m.id);
    if (!c) return;
    if (m.type === 'history') c.onHistory(m);
    else if (m.type === 'older') c.onOlder(m);
    else if (m.type === 'update') c.onUpdate(m);
    else if (m.type === 'reset') c.subscribe(true);
    else if (m.type === 'error') c.onError(m.error);
  };
  ws.onclose = () => { showStatus({ connected: false, error: 'chart service unreachable — retrying' }); setTimeout(connect, 2000); };
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
  if (e.altKey && !e.metaKey && !e.ctrlKey && e.code === 'KeyR') {   // ⌥R: Reset chart view (e.key is ® on macOS)
    e.preventDefault();
    if (c) c.resetView();
    return;
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
  $('#tbLayout').onclick = () => toggleMenu($('#tbLayout'), () => layoutMenu(false));
  $('#tbSave').onclick = save;
  $('#tbSettings').onclick = chartSettings;
  $('#tbTheme').onclick = toggleTheme;
  for (const b of document.querySelectorAll('#rail [data-tool]')) {
    b.onclick = () => setTool(b.dataset.tool === tool && tool !== 'cursor' ? 'cursor' : b.dataset.tool);
  }
  $('#railClear').onclick = clearDrawings;
  $('#railMagnet').onclick = () => setMagnet({ ...magnet, on: !magnet.on });
  $('#railMagnetMore').onclick = () => toggleMenu($('#railMagnetMore'), magnetMenu);
  renderMagnet();
  document.addEventListener('pointerdown', (e) => {
    if (menuEl && !menuEl.contains(e.target) && !(menuAnchor && menuAnchor.contains(e.target))) closeMenu();
  }, true);
  window.addEventListener('resize', closeMenu);
  document.addEventListener('keydown', onKey);
  buildGrid();
  connect();
  tick();
  setInterval(tick, 1000);
}

window.HBCharts = { get cells() { return cells; }, get layout() { return layout; }, get selected() { return selected; }, select, buildGrid };
init();
})();
