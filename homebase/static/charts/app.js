/* Homebase Charts — the page: layout and selection, the top toolbar (it
   acts on the selected chart), menus, the websocket to the chart service
   (:8852) and the bottom bar. Each grid slot is an HBCell.Cell; the server
   computes everything, the page only draws. */
(() => {
'use strict';
const C = window.HBCatalog, I = window.HBIcons, { Cell } = window.HBCell;
const GRIDS = { 1: [1, 1], 2: [2, 1], 4: [2, 2], 6: [3, 2] };
const STATUS_STALE_S = 6;   // the server sends a status every 2 s: this long without one = it is stuck
const START = [['NQ', 'time:60'], ['NQ', 'time:300'], ['ES', 'time:60'], ['YM', 'time:60'], ['NQ', 'tick:1000'], ['NQ', 'time:900']];
const ET_CLOCK = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit',
  second: '2-digit', hourCycle: 'h23' });

let meta = { roots: ['NQ'], timeframes: [] };
let ws = null;
let layout = { grid: 4, cells: [], name: '' };
let cells = [];
let selected = 0;
let nextId = 1;
let statusAt = 0, statusLine = '';
let menuEl = null, menuAnchor = null;
let customWait = null;   // {cell, spec, err}: a custom interval sent from the open interval menu, awaiting the server

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
function loadLast() {
  try {
    const v = JSON.parse(localStorage.getItem('hb_charts_last') || 'null');
    if (v && Array.isArray(v.cells)) layout = { ...C.migrateLayout(v), name: typeof v.name === 'string' ? v.name : '' };
  } catch (_) { /* unreadable: start fresh */ }
}

function hostFor(id) {
  return {
    id,
    send(msg) { if (!ws || ws.readyState !== 1) return false; ws.send(JSON.stringify(msg)); return true; },
    onPick(cell) { select(cells.indexOf(cell)); },
    onLoaded,
    onRefused,
    changed() { saveLast(); renderToolbar(); },
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
    cells.push(new Cell(slot, layout.cells[i], hostFor('c' + (nextId++))));
  }
  select(Math.min(selected, n - 1));
}

function select(i) {
  if (i < 0 || i >= cells.length) return;
  selected = i;
  cells.forEach((c, k) => c.setSelected(k === i));
  renderToolbar();
}

/* ---- toolbar ---- */
function renderToolbar() {
  const c = cur();
  if (!c) return;
  const { root, spec } = c.cfg;
  $('#tbSymbolText').textContent = root;
  $('#tbSymbol').title = `${root} · ${C.rootName(root) || 'symbol'} — change symbol`;
  const favs = C.FAVOURITES.slice();
  if (!favs.some(([, s]) => s === spec)) favs.push([C.specLabel(spec), spec]);
  $('#tbFavs').replaceChildren(...favs.map(([label, s]) => {
    const b = mk('button', 'tb-btn iv' + (s === spec ? ' active' : ''), label);
    b.type = 'button';
    b.title = C.longLabel(s);
    b.setAttribute('aria-pressed', String(s === spec));
    b.onclick = () => { if (cur().cfg.spec !== s) cur().update({ spec: s }); };
    return b;
  }));
  const dark = document.documentElement.getAttribute('data-theme') === 'dark', th = $('#tbTheme');
  th.replaceChildren(icon(dark ? 'sun' : 'moon'));
  th.title = dark ? 'Light theme' : 'Dark theme';
}

/* One popup menu at a time, under its toolbar button. */
function openMenu(anchor, cls) {
  closeMenu();
  const m = mk('div', 'menu' + (cls ? ' ' + cls : ''));
  m.setAttribute('role', 'menu');
  $('#menuRoot').appendChild(m);
  menuEl = m; menuAnchor = anchor;
  anchor.classList.add('open');
  anchor.setAttribute('aria-expanded', 'true');
  return m;
}
function placeMenu() {
  if (!menuEl) return;
  const r = menuAnchor.getBoundingClientRect(), w = menuEl.offsetWidth;
  menuEl.style.left = Math.max(4, Math.min(r.left, window.innerWidth - w - 4)) + 'px';
  menuEl.style.top = (r.bottom + 4) + 'px';
}
function closeMenu() {
  if (!menuEl) return;
  menuEl.remove();
  menuAnchor.classList.remove('open');
  menuAnchor.setAttribute('aria-expanded', 'false');
  menuEl = menuAnchor = null;
  customWait = null;
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
    if (!s) { err.textContent = 'Use e.g. 45s, 2m, 4h, 1D, 750T, 3000V, 8R or tick:750'; err.hidden = false; return; }
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

/* A custom interval the open menu sent loaded: close the menu. */
function onLoaded(cell) {
  if (customWait && customWait.cell === cell && cell.cfg.spec === customWait.spec) closeMenu();
}

/* The server refused a change (the cell already went back to its last good
   config): say why inline in the interval menu if that is where it came
   from, else in the chart's legend. */
function onRefused(cell, tried, text) {
  if (customWait && customWait.cell === cell && menuEl) {
    customWait.err.textContent = text;
    customWait.err.hidden = false;
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

/* ---- bottom bar ---- */
function fmtAge(a) { return a == null ? '—' : a < 60 ? `${a.toFixed(1)}s` : `${Math.round(a / 60)}m`; }

function showStatus(s) {
  const roots = s.roots || {}, rec = s.recorder, recErr = rec && rec.error, recBusy = !!(rec && rec.buffered >= 5000);
  const stale = Object.entries(roots).filter(([, x]) => (x.last_tick_age_s ?? 0) > 30)
    .sort((a, b) => b[1].last_tick_age_s - a[1].last_tick_age_s);
  $('#sbDot').className = 'sb-dot ' + (!s.connected || s.error || recErr ? 'bad' : stale.length || recBusy ? 'warn' : 'ok');
  $('#sbMode').textContent = s.mode === 'replay'
    ? `Replay ${s.date} ×${s.speed} · ${iso(s.clock_s || 0).slice(11, 19)} ET${s.done ? ' · done' : ''}`
    : s.mode === 'live' ? `Live · md ${s.md || ''}` : 'Disconnected';
  const feed = $('#sbFeed');
  feed.textContent = s.error || (recErr ? `recorder: ${recErr}` : '')
    || (stale.length ? stale.slice(0, 2).map(([r, x]) => `${r} stale ${fmtAge(x.last_tick_age_s)}`).join(' · ') : '')
    || (Object.keys(roots).length ? 'feeds ok' : '');
  feed.title = Object.entries(roots).map(([r, x]) => `${r} ${fmtAge(x.last_tick_age_s)}`).join('  ·  ');
  feed.classList.toggle('bad', !!(s.error || recErr));
  const budget = $('#sbBudget');
  budget.textContent = s.mode === 'live' ? `md ${s.budget_hour ?? 0}/180` : '';
  budget.title = s.mode === 'live' ? `Chart requests this hour on the md login (limit 180) · ${s.clients ?? 0} page(s)` : '';
  const recEl = $('#sbRec');
  recEl.textContent = s.mode === 'live' && rec ? `rec buffered ${rec.buffered.toLocaleString('en-US')}` : '';
  recEl.classList.toggle('warn', recBusy);
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

function tick() { $('#sbClock').textContent = `${ET_CLOCK.format(new Date())} ET`; greyIfStale(); }

/* ---- the chart service ---- */
function connect() {
  ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen = () => { statusAt = Date.now(); for (const c of cells) c.subscribe(true); };
  ws.onmessage = (e) => {
    let m;
    try { m = JSON.parse(e.data); } catch (_) { return; }
    if (m.type === 'status') { statusAt = Date.now(); showStatus(m); return; }
    const c = cells.find((x) => x.id === m.id);
    if (!c) return;
    if (m.type === 'history') c.onHistory(m);
    else if (m.type === 'update') c.onUpdate(m);
    else if (m.type === 'reset') c.subscribe(true);
    else if (m.type === 'error') c.onError(m.error);
  };
  ws.onclose = () => { showStatus({ connected: false, error: 'chart service unreachable — retrying' }); setTimeout(connect, 2000); };
}

/* ---- keyboard ---- */
function onKey(e) {
  if (e.key === 'Escape' && menuEl) { e.preventDefault(); closeMenu(); }
}

async function init() {
  for (const n of document.querySelectorAll('[data-icon]')) n.innerHTML = I[n.dataset.icon] || '';
  $('#tbDesk').href = `${location.protocol}//${location.hostname}:8850/`;
  try { const r = await fetch('/api/symbols'); if (r.ok) meta = await r.json(); } catch (_) { /* keep the fallback */ }
  loadLast();
  $('#tbSymbol').onclick = () => toggleMenu($('#tbSymbol'), symbolMenu);
  $('#tbIntervals').onclick = () => toggleMenu($('#tbIntervals'), intervalMenu);
  $('#tbTheme').onclick = toggleTheme;
  document.addEventListener('pointerdown', (e) => {
    if (menuEl && !menuEl.contains(e.target) && !menuAnchor.contains(e.target)) closeMenu();
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
