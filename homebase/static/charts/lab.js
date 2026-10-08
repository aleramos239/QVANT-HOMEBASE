/* Homebase Lab (the Backtest page): one workspace of four panels -- a library of strategies, a Python editor, the
   chart, a backtest result -- each shown or hidden from the top bar.
   A strategy here is TEXT. Saving writes ~/.homebase/strategies/<name>.py through the chart service; Run sends the
   saved text to the tester, where it runs only inside the sandboxed backtest child. Nothing on this page
   executes a draft, and nothing here can put one on the desk: "Request review" writes a package for a person
   (and Claude) to read first. The pure half (highlighting, keystrokes, names) is labcode.js. */
(function () {
'use strict';
const root = document.getElementById('lab');
if (!root || !window.HBTester || !window.HBLabCode) return;
const X = window.HBTester, C = window.HBLabCode;
const $ = (s, el = root) => el.querySelector(s);
const esc = (t) => String(t == null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
const MINUS = '−';
const SAVE_ICON_LOCK = '<svg class="lb-lock" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/></svg>';

/* ---- state ---- */
const S = { builtins: [], drafts: [], groups: null, bufs: new Map(), cur: null, forms: {}, run: null, log: [], seq: 0, busy: false,
  view: 'lib', bp: null, bpIdea: '', tk: null, tkQ: '', pl: null, plSaid: null, plBusy: false, plForm: null, plFk: '', plIdea: '', plCard: '', plWant: '', plDetail: null, plArmed: '' };
/* view: what the sidebar lists -- 'lib' (strategies), 'bp' (the blueprint's tools), 'tk' (its blocks, with their code), and the strategy
   pipeline's three: 'pq' (its Queue), 'pb' (its Book), 'pg' (its Guide). */
const VIEWS = [['lib', 'Strategies'], ['bp', 'Blueprint'], ['tk', 'Arsenal']], PIPE_TABS = [['pq', 'Queue'], ['pb', 'Book'], ['pg', 'Guide']];
const PIPE_VIEWS = PIPE_TABS.map(([v]) => v), VIEW_IDS = [...VIEWS, ...PIPE_TABS].map(([v]) => v);
const pipeOn = () => PIPE_VIEWS.includes(S.view);      // a pipeline view is open: the middle of the page is its own
try { const v = localStorage.getItem('hb_lab_view'); if (VIEW_IDS.includes(v)) S.view = v; } catch (_) { /* private mode: strategies */ }
const buf = () => (S.cur ? S.bufs.get(S.cur) : null);
const isDirty = (b) => b.kind !== 'builtin' && (b.kind === 'new' ? !!b.code.trim() : b.code !== b.saved);
const takenNames = () => [...S.drafts.map((d) => d.name), ...[...S.bufs.values()].filter((b) => b.kind === 'new' && b.name).map((b) => b.name)];

async function call(path, opts = {}) {
  try {
    const r = await fetch(path, { ...opts, headers: opts.body ? { 'content-type': 'application/json' } : undefined });
    let j = null; try { j = await r.json(); } catch (_) { /* no body */ }
    return { ok: r.ok, status: r.status, json: j, error: r.ok ? null : (j && (j.detail || j.error)) || `HTTP ${r.status}` };
  } catch (e) { return { ok: false, status: 0, json: null, error: 'The chart service is not reachable' }; }
}
const send = (method, path, body) => call(path, { method, body: body === undefined ? undefined : JSON.stringify(body) });

/* ---- the log line under the editor ---- */
function log(html, tone = '') { S.log.push({ html, tone }); S.log = S.log.slice(-5); paintLog(); }
function paintLog() {
  const el = $('#edLog');
  if (!el) return;
  el.innerHTML = S.log.map((l) => `<div class="${l.tone}">${l.html}</div>`).join('');
  el.scrollTop = el.scrollHeight;
}

/* ---- loading ---- */
async function loadLists() {
  const [a, b, g] = await Promise.all([send('GET', '/api/tester/strategies'), send('GET', '/api/tester/drafts'), send('GET', '/api/tester/groups')]);
  if (a.ok) S.builtins = (a.json || []).filter((s) => !s.draft);
  if (b.ok) S.drafts = b.json || [];
  if (g.ok) S.groups = g.json;
  else if (g.status) {      // a chart service from before groups (404), or a groups file that does not read (409): the plain list
    S.groups = null;
    const why = `<span class="err">No groups: ${esc(g.error)}</span>`;
    if (g.status === 409 && !S.log.some((l) => l.html === why)) log(why);
  }
  paintLib();
  if (S.view === 'bp') loadBlueprint();
  else if (S.view === 'tk') loadToolkit();
}
/* The blueprint toolkit: the tools every chat has and the ideas on file, as the chart service lists them. */
async function loadBlueprint() {
  const r = await send('GET', '/api/tester/blueprint');
  S.bp = r.ok ? r.json : { error: r.status === 404 ? 'The chart service is from before the toolkit: restart it once to see the tools here.' : r.error };
  paintLib();
}
/* The arsenal: every tool we have with its code, read from the code itself (homebase/arsenal.py), so a new tool is here with its code. */
async function loadToolkit() {
  if (S.tk && !S.tk.error) return;
  const r = await send('GET', '/api/tester/arsenal');
  S.tk = r.ok ? r.json : { error: r.status === 404 ? 'The chart service is from before the toolkit list: restart it once to see the arsenal here.' : r.error };
  paintLib();
}
async function openKey(key) {
  S.cur = key;
  const b = S.bufs.get(key);
  if (b && b.code == null) {
    const r = await send('GET', `/api/tester/strategies/${encodeURIComponent(b.id)}/source`);
    const files = (r.ok && r.json && r.json.files) || [];
    b.code = files.length === 1 ? files[0].text : files.map((f) => `# ── ${f.path} ──\n${f.text}`).join('\n\n');
    if (!r.ok) b.code = `# could not load ${b.id}: ${r.error}\n`;
    if (b.kind === 'draft') b.saved = b.code;
  }
  paintAll();
  if (b && b.kind !== 'builtin') queueValidate(b, 0);
  S.run = S.run && S.run.key === key ? S.run : null;
  paintRes();
  if (b && b.kind !== 'new' && !S.run) restoreLastRun(b);
  setHash(b);
}
function setHash(b) {
  try { history.replaceState(null, '', b && b.kind !== 'new' ? `#${b.kind === 'builtin' ? 'builtin' : 'strategy'}=${encodeURIComponent(b.name)}` : location.pathname + location.search); } catch (_) { /* file: or sandbox */ }
}
/* The most recent finished run of this strategy, so a reload (or coming back to it) shows how it last did. */
async function restoreLastRun(b) {
  const id = b.kind === 'builtin' ? b.id : `draft_${b.name}`;
  const l = await send('GET', '/api/tester/runs');
  const hit = l.ok && (l.json || []).find((r) => r.strategy === id && r.status === 'done');
  if (!hit || S.cur !== b.key || S.run) return;
  const bd = await send('GET', `/api/tester/run/${encodeURIComponent(hit.id)}/bundle`);
  if (!bd.ok || S.cur !== b.key || S.run) return;
  S.run = { key: b.key, rid: hit.id, st: { status: 'done' }, bundle: bd.json, strategy: id };
  paintRes(); syncChart();
}
function ensureBuf(kind, key, init) {
  if (!S.bufs.has(key)) S.bufs.set(key, { key, kind, name: '', id: '', code: null, saved: null, valid: null, savedAt: 0, ...init });
  return S.bufs.get(key);
}
function selectDraft(name) { ensureBuf('draft', `d:${name}`, { name, id: `draft_${name}` }); return openKey(`d:${name}`); }
function selectBuiltin(id) { const s = S.builtins.find((x) => x.id === id); ensureBuf('builtin', `b:${id}`, { name: id, id, meta: s }); return openKey(`b:${id}`); }
function openScript(code, name = '') {
  const key = `n:${++S.seq}`;
  const b = ensureBuf('new', key, { name: name || (code && code.trim() ? C.suggestName(code, takenNames()) : ''), code: code || '', saved: null });
  S.cur = key; S.run = null;
  paintAll();
  if (code && code.trim()) queueValidate(b, 0);
  setTimeout(() => { const ta = $('#edTa'); if (ta) { ta.focus(); ta.setSelectionRange(0, 0); } }, 0);
  return b;
}

/* ---- validate / save ---- */
let vTimer = 0, vSeq = 0;
function queueValidate(b, delay = 450) {
  clearTimeout(vTimer);
  vTimer = setTimeout(() => validateNow(b), delay);
}
async function validateNow(b) {
  if (!b || b.kind === 'builtin' || !b.code || !b.code.trim()) { if (b) { b.valid = null; paintHead(); paintGutter(); } return null; }
  const seq = ++vSeq, t0 = performance.now(), code = b.code;
  const r = await send('POST', '/api/tester/drafts/validate', { code });
  if (seq !== vSeq || code !== b.code) return null;               // a newer keystroke won
  b.valid = r.ok ? r.json : { ok: false, error: r.error, line: null };
  b.validMs = Math.round(performance.now() - t0);
  paintHead(); paintGutter(); paintLib();
  return b.valid;
}
async function save(b) {
  if (!b || b.kind === 'builtin') return false;
  const nerr = C.nameError(b.name);
  if (nerr) { log(`<span class="err">${esc(nerr)}</span>`); const n = document.getElementById('edName'); if (n) { n.classList.add('bad'); n.focus(); } return false; }
  const r = await send('PUT', `/api/tester/drafts/${encodeURIComponent(b.name)}`, { code: b.code });
  if (!r.ok) { log(`<span class="err">Not saved: ${esc(r.error)}</span>`); return false; }
  const wasNew = b.kind === 'new';
  if (wasNew) { S.bufs.delete(b.key); b.key = `d:${b.name}`; b.kind = 'draft'; b.id = `draft_${b.name}`; S.bufs.set(b.key, b); S.cur = b.key; }
  b.saved = b.code; b.savedAt = Date.now();
  b.valid = { ok: true, meta: r.json.meta };
  await loadLists();
  paintAll();
  setHash(b);
  return true;
}

/* ---- run ---- */
function metaOf(b) {
  if (b.kind === 'builtin') return b.meta;
  const m = b.valid && b.valid.ok && b.valid.meta;
  return m ? { id: b.id || `draft_${b.name}`, inputs: m.inputs || [] } : null;
}
function formOf(b) {
  const meta = metaOf(b);
  if (!meta) return null;
  const id = b.kind === 'builtin' ? b.id : `draft_${b.name}`;
  const f = X.restore(S.forms[id] ? { ...S.forms[id], strategy: id } : null, { ...meta, id });
  f.strategy = id;
  S.forms[id] = f;
  return f;
}
async function run() {
  const b = buf();
  if (!b || S.busy) return;
  if (b.kind !== 'builtin') {
    if (!b.code.trim()) return;
    const v = await validateNow(b);
    if (!v || !v.ok) { log(`<span class="err">Fix the script first: ${esc(C.statusOf(v).text)}</span>`); return; }
    if (isDirty(b) || b.kind === 'new') { if (!(await save(b))) return; }
  }
  const nb = buf(), f = formOf(nb);
  if (!f) return;
  const pr = X.problems(f, { ...metaOf(nb), id: f.strategy });
  if (pr) { log(`<span class="err">${esc(pr)}</span>`); return; }
  S.busy = true;
  S.run = { key: nb.key, rid: null, st: { status: 'queued' }, bundle: null, strategy: f.strategy };
  paintRes(); paintHead();
  const r = await send('POST', '/api/tester/run', X.body(f));
  if (!r.ok) { S.busy = false; S.run = null; log(`<span class="err">${esc(r.error)}</span>`); paintRes(); paintHead(); return; }
  S.run.rid = r.json.id;
  log(`Running <b>${esc(nb.kind === 'builtin' ? nb.id : nb.name)}</b> over ${esc(X.pillLabel ? X.pillLabel(f.range) : f.range.id)} inside the sandbox…`);
  poll(S.run);
}
async function poll(run) {
  while (S.run === run) {
    const r = await send('GET', `/api/tester/run/${encodeURIComponent(run.rid)}`);
    if (S.run !== run) return;
    if (r.ok) { run.st = r.json; paintRes(); }
    const s = r.ok ? r.json.status : 'error';
    if (s === 'done') {
      const bd = await send('GET', `/api/tester/run/${encodeURIComponent(run.rid)}/bundle`);
      if (S.run !== run) return;
      run.bundle = bd.ok ? bd.json : null;
      S.busy = false;
      if (run.bundle) {
        const a = run.bundle.run.report.summary.all;
        log(`Ran in the sandbox · <b>${esc(String(a.trades ?? 0))} trades</b> · <a data-act="show">Show trades on the chart ›</a>`);
      } else log('<span class="err">The run finished but its report could not be loaded</span>');
      paintRes(); paintHead(); syncChart();
      return;
    }
    if (s === 'error' || s === 'cancelled') {
      S.busy = false;
      const msg = s === 'cancelled' ? 'Cancelled' : `Failed: ${esc((r.json && r.json.error) || r.error || 'unknown error')}`;
      log(`<span class="${s === 'error' ? 'err' : ''}">${msg}</span>`);
      run.st = { ...(run.st || {}), status: s }; paintRes(); paintHead();
      return;
    }
    await new Promise((res) => setTimeout(res, 550));
  }
}
async function cancelRun() { if (S.run && S.run.rid && S.busy) await send('POST', `/api/tester/run/${encodeURIComponent(S.run.rid)}/cancel`); }

/* ---- the workspace: four panels, shown or hidden; Code and Chart share the middle ---- */
const PANELS = ['lib', 'code', 'chart', 'res'];
const P = { lib: true, code: true, chart: false, res: true };
let split = 45, panelsChosen = false;
try {
  const saved = JSON.parse(localStorage.getItem('hb_lab_panels') || 'null');
  if (saved && typeof saved === 'object') { for (const k of PANELS) if (typeof saved[k] === 'boolean') P[k] = saved[k]; panelsChosen = true; }
  const sp = Number(localStorage.getItem('hb_lab_split'));
  if (sp >= 20 && sp <= 80) split = sp;
} catch (_) { /* private mode: the defaults */ }
try {      // ?panels=code,chart,res opens exactly those (a link to a layout)
  const q = new URLSearchParams(location.search).get('panels');
  if (q) { const want = q.split(','); for (const k of PANELS) P[k] = want.includes(k); panelsChosen = true; }
} catch (_) { /* no URL API */ }
if (!P.code && !P.chart) P.code = true;
function refit() { requestAnimationFrame(() => { window.dispatchEvent(new Event('resize')); requestAnimationFrame(() => window.dispatchEvent(new Event('resize'))); }); }
function applyPanels(save = true) {
  /* While a pipeline view is open its page has the middle (#labPipe): the code, the chart and the result are SHOWN as switched off --
     hidden by the rules that hide a panel the person switched off, never rebuilt -- and P, the person's own choice, is not touched:
     leaving the view shows them again exactly as they were. Their three buttons rest meanwhile. */
  const pipe = pipeOn();
  for (const k of PANELS) root.dataset[k] = P[k] && !(pipe && k !== 'lib') ? '1' : '0';
  root.dataset.pipe = pipe ? '1' : '0';
  root.style.setProperty('--lab-code', String(split));
  root.style.setProperty('--lab-chart', String(100 - split));
  document.body.classList.toggle('lab-chart-on', P.chart && !pipe);
  document.body.classList.toggle('lab-pipe-on', pipe);
  for (const x of document.querySelectorAll('#labPanels [data-panel]')) { x.setAttribute('aria-pressed', String(!!P[x.dataset.panel])); x.disabled = pipe && x.dataset.panel !== 'lib'; }
  paintRes();
  if (save) { try { localStorage.setItem('hb_lab_panels', JSON.stringify(P)); localStorage.setItem('hb_lab_split', String(Math.round(split))); } catch (_) { /* private mode */ } }
  refit();
  setTimeout(refit, 340);
  plSync();                 // the pipeline is asked only while one of its views is open
}
/* Show or hide one panel. The middle is never empty: hiding the last of Code / Chart brings the other back. */
function setPanel(k, on) {
  if (!PANELS.includes(k)) return;
  P[k] = on == null ? !P[k] : !!on;
  if (!P.code && !P.chart) P[k === 'code' ? 'chart' : 'code'] = true;
  panelsChosen = true;
  applyPanels();
  if (k === 'chart' && P.chart) setTimeout(() => { soloChart(); syncChart(); }, 160);
}
/* Put the current run on the chart: its executions, its levels and the chart's own indicators. `report` also
   opens the Strategy Tester's full report under the chart. The server refuses 09:20-09:35 ET (the desk's window). */
let shownRid = null, showTries = 0;
function setReport(on) { root.dataset.report = on ? '1' : '0'; paintRes(); refit(); }
async function showOnChart(report = false) {
  const r = S.run;
  if (!r || !r.bundle) return;
  if (!P.chart) {
    P.chart = true;
    if (innerWidth < 1500 && !panelsChosen) P.lib = false;     // a laptop-width window: the library steps aside (first time only)
    applyPanels();
    await new Promise((res) => setTimeout(res, 160));
  }
  if (report) setReport(true);
  soloChart();
  if (shownRid === r.rid) return;
  shownRid = r.rid;
  const n = (r.bundle.trades || []).length;
  ti = n ? n - 1 : null;                        // open on the most recent trade: its executions are what you came to see
  paintNav();
  const o = await send('POST', '/api/tester/show', { run_id: r.rid });
  if (o.ok && o.json.pages && n) frameWhenLoaded(r.rid);
  if (!o.ok) { shownRid = null; log(`<span class="err">Could not show it on the chart: ${esc(o.error)}</span>`); }
  else if (!o.json.pages) {       // this page's own socket is not up yet (just loaded): try again shortly, a few times
    shownRid = null;
    if ((showTries = (showTries || 0) + 1) <= 5) setTimeout(syncChart, 1200); else log('The chart is not connected yet: toggle Chart off and on to try again');
  } else showTries = 0;
  paintNav();
}
/* ONE chart: the Lab never shows a grid of them. (The grid menu is the chart shell's own; its button is hidden here.) */
function soloChart() {
  const H = window.HBCharts;
  if (!H || !H.cells || !H.cells.length) return;
  if (H.layout && H.layout.grid !== 1) { H.layout.grid = 1; H.buildGrid(); }
  bareChart();
}
/* ...and it shows the STRATEGY: price, its executions, the levels and plots the script itself draws. The chart's
   own saved indicators (volume, VWAP, session levels, footprint, ...) are not part of the strategy, so they go. */
function bareChart() {
  const c = window.HBCharts && window.HBCharts.cells && window.HBCharts.cells[0];
  if (c && c.cfg && Array.isArray(c.cfg.indicators) && c.cfg.indicators.length) c.update({ indicators: [] });
}
/* ---- stepping through the trades ---- */
let ti = null;
/* A trade is shown inside its whole trading day: from half an hour before the strategy's session opens to its
   close (the window the script declares; 09:30-16:00 ET when it declares none). */
const ET_HMS = new Intl.DateTimeFormat('en-GB', { timeZone: 'America/New_York', hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' });
const etMsOfDay = (ms) => { const [h, m, s] = ET_HMS.format(new Date(ms)).split(':').map(Number); return ((h * 60 + m) * 60 + s) * 1000; };
const hm = (t, d) => { const m = /^(\d{1,2}):(\d{2})/.exec(String(t || '')); return m ? (Number(m[1]) * 60 + Number(m[2])) * 60000 : d; };
function sessionWindow() {
  const b = buf(), meta = b && (b.kind === 'builtin' ? b.meta : b.valid && b.valid.meta), w = meta && meta.session_window;
  return { open: hm(w && w[0], 570 * 60000), close: hm(w && w[1], 960 * 60000) };
}
const LEAD_MS = 30 * 60000;
function dayContext(t) {
  const w = sessionWindow();
  return { before: Math.max(LEAD_MS, etMsOfDay(t.entry_ms) - (w.open - LEAD_MS)), after: Math.max(LEAD_MS, w.close - etMsOfDay(t.exit_ms)) };
}
/* The show arrives over the page's socket: once the tester holds this run, frame its latest trade. */
async function frameWhenLoaded(rid) {
  const pause = (ms) => new Promise((res) => setTimeout(res, ms));
  for (let k = 0; k < 60; k++) {
    const b = window.HBTesterUI && window.HBTesterUI.bundle;
    if (shownRid !== rid) return;                       // a newer run took the chart
    if (b && b.run && b.run.id === rid) break;
    await pause(200);
  }
  // the tester is still settling the run it was just handed: a jump can lose that race, so make sure it took
  for (let k = 0; k < 4 && shownRid === rid && ti != null; k++) {
    await pause(k ? 1500 : 300);
    if (window.HBTesterUI && window.HBTesterUI.selected === ti) return;
    jumpTo(ti);
  }
}
const jumpTo = (i) => { const t = navTrades()[i]; return t && window.HBTesterLayer && window.HBTesterLayer.jump(i, null, { contextMs: dayContext(t) }); };
const NAV_DAY = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric', year: 'numeric' });
const NAV_DATE = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
const navTrades = () => (S.run && S.run.bundle && shownRid === S.run.rid ? S.run.bundle.trades || [] : []);
function paintNav() {
  const el = document.getElementById('labNavText');
  if (!el) return;
  const ts = navTrades(), n = ts.length, t = ti != null ? ts[ti] : null;
  const [prev, next] = document.querySelectorAll('#labNav [data-nav]');
  if (prev) prev.disabled = !n || ti == null || ti <= 0;
  if (next) next.disabled = !n || (ti != null && ti >= n - 1);
  if (!n) { el.textContent = S.run && S.run.bundle && shownRid === S.run.rid ? 'No trades in this run' : 'Run a backtest to see its trades'; return; }
  if (!t) { el.innerHTML = `<b>${n}</b> trade${n === 1 ? '' : 's'}`; return; }
  const net = Number(t.net) || 0, amt = `${net > 0 ? '+' : net < 0 ? MINUS : ''}$${Math.abs(Math.round(net)).toLocaleString('en-US')}`;
  el.innerHTML = `<b>${ti + 1}</b> of ${n} · ${t.side === 'long' ? 'Long' : 'Short'} <span class="${net > 0 ? 'pos' : 'neg'}">${amt}</span> · ${esc(NAV_DAY.format(new Date(t.entry_ms)))}`;
  el.title = `Trade ${ti + 1} of ${n} · ${NAV_DATE.format(new Date(t.entry_ms))} ET`;
}
function stepTrade(d) {
  const n = navTrades().length;
  if (!n || !window.HBTesterLayer) return;
  ti = Math.max(0, Math.min(n - 1, (ti == null ? (d > 0 ? -1 : n) : ti) + d));
  paintNav();
  jumpTo(ti);
}
document.getElementById('labNav')?.addEventListener('click', (e) => { const b = e.target.closest('[data-nav]'); if (b) stepTrade(Number(b.dataset.nav)); });
// a trade picked in the full report's list moves the stepper too
if (window.HBTesterUI && window.HBTesterUI.on) window.HBTesterUI.on(() => {
  const i = window.HBTesterUI.selected;
  if (i != null && i !== ti && i < navTrades().length) { ti = i; paintNav(); }
});
// a new interval reloads the chart at the latest bars: bring the trade back into view
document.getElementById('tbFavs')?.addEventListener('click', (e) => { if (e.target.closest('button') && ti != null && navTrades().length) setTimeout(() => jumpTo(ti), 400); });

/* The chart follows the strategy: whenever the Chart panel is showing and there is a finished run, it is on it. */
function syncChart() { if (P.chart && S.run && S.run.bundle && shownRid !== S.run.rid) showOnChart(false); }
/* the divider between Code and Chart */
(function () {
  const bar = document.getElementById('labSplit');
  if (!bar) return;
  const span = () => { const a = $('#labEd').getBoundingClientRect(), b = document.getElementById('labChart').getBoundingClientRect(); return { left: a.left, width: b.right - a.left }; };
  const to = (x) => { const s = span(); if (s.width > 0) { split = Math.max(22, Math.min(78, ((x - s.left) / s.width) * 100)); applyPanels(false); } };
  bar.addEventListener('pointerdown', (e) => { bar.setPointerCapture(e.pointerId); bar.classList.add('drag'); e.preventDefault(); });
  bar.addEventListener('pointermove', (e) => { if (bar.classList.contains('drag')) to(e.clientX); });
  const end = () => { if (bar.classList.contains('drag')) { bar.classList.remove('drag'); applyPanels(); } };
  bar.addEventListener('pointerup', end); bar.addEventListener('pointercancel', end);
  bar.addEventListener('dblclick', () => { split = 45; applyPanels(); });
  bar.addEventListener('keydown', (e) => { if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') { e.preventDefault(); split = Math.max(22, Math.min(78, split + (e.key === 'ArrowLeft' ? -3 : 3))); applyPanels(); } });
})();

/* ---- dialogs and menus ---- */
let overlay = null, menuEl = null, dlgFrom = null;
const FOCUSABLE = 'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])';
/* Closing a sheet gives the keyboard back to what opened it (or, when the list was painted again meanwhile, to the same row of it). */
function closeDialog(back = true) {
  if (!overlay) return;
  overlay.remove(); overlay = null;
  const from = dlgFrom; dlgFrom = null;
  if (!back || !from) return;
  const el = from.el.isConnected ? from.el : from.fk ? [...root.querySelectorAll('[data-fk]')].find((x) => x.dataset.fk === from.fk) : null;
  if (el) el.focus({ preventScroll: true });
}
function dialog(html) {
  const a = document.activeElement, from = overlay ? dlgFrom : a && a !== document.body ? { el: a, fk: (a.dataset && a.dataset.fk) || '' } : null;
  closeDialog(false);       // a sheet that opens from a sheet remembers what opened the first one
  dlgFrom = from;
  overlay = document.createElement('div');
  overlay.className = 'lab-ov';
  overlay.innerHTML = `<div class="lab-dlg" role="dialog" aria-modal="true" tabindex="-1">${html}</div>`;
  overlay.addEventListener('pointerdown', (e) => { if (e.target === overlay) closeDialog(); });
  /* Tab stays inside the sheet: from its last control to its first, and back */
  overlay.addEventListener('keydown', (e) => {
    if (e.key !== 'Tab') return;
    const f = [...overlay.querySelectorAll(FOCUSABLE)].filter((x) => !x.disabled && x.getClientRects().length), at = document.activeElement;
    if (!f.length) { e.preventDefault(); return; }
    const first = f[0], last = f[f.length - 1];
    if (e.shiftKey ? at === first || at === overlay.firstElementChild : at === last) { e.preventDefault(); (e.shiftKey ? last : first).focus(); }
  });
  document.body.appendChild(overlay);
  const d = overlay.firstElementChild, h = d.querySelector('h2');
  if (h) { h.id = h.id || 'labDlgTitle'; d.setAttribute('aria-labelledby', h.id); }
  d.focus({ preventScroll: true });      // the sheet has the keyboard from the start; a sheet then moves it to its first field
  return d;
}
function closeMenu() { if (menuEl) { menuEl.remove(); menuEl = null; } }
function menu(anchor, html, onPick) {
  closeMenu();
  menuEl = document.createElement('div');
  menuEl.className = 'lab-menu';
  menuEl.innerHTML = html;
  document.body.appendChild(menuEl);
  const a = anchor.getBoundingClientRect(), m = menuEl.getBoundingClientRect();
  const right = a.left + m.width > innerWidth - 8;            // opens toward the side it has room on, from its button
  menuEl.style.left = `${Math.max(8, right ? a.right - m.width : a.left)}px`;
  menuEl.style.top = `${Math.max(8, Math.min(a.bottom + 8, innerHeight - m.height - 8))}px`;
  menuEl.style.setProperty('--o', right ? 'top right' : 'top left');
  menuEl.addEventListener('click', (e) => { const t = e.target.closest('[data-pick]'); if (t) { closeMenu(); onPick(t.dataset.pick); } });
}
document.addEventListener('pointerdown', (e) => { if (menuEl && !menuEl.contains(e.target) && !e.target.closest('[data-act="new"], [data-act="more"]')) closeMenu(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeMenu(); closeDialog(); } });

async function newMenu(anchor) {
  const r = await send('GET', '/api/tester/drafts/templates');
  const ts = (r.ok && r.json) || [];
  menu(anchor, `<button data-pick="paste"><b>Paste a script</b><small>Insert Python from your clipboard or an editor</small></button>
    <button data-pick="file"><b>Open a .py file…</b><small>Load a script from disk</small></button><hr>
    <h6>Start from a template</h6>${ts.map((t) => `<button data-pick="t:${esc(t.id)}"><b>${esc(t.title)}</b><small>${esc(t.blurb)}</small></button>`).join('')}
    ${S.groups ? '<hr><button data-pick="group"><b>New group…</b><small>A section of this list to keep strategies under</small></button>' : ''}`,
  async (pick) => {
    if (pick === 'paste') return pasteScript();
    if (pick === 'file') return $('#labFile').click();
    if (pick === 'group') return nameGroup();
    const t = ts.find((x) => `t:${x.id}` === pick);
    if (t) openScript(t.code, C.suggestName(t.code, takenNames()));
  });
}
function moreMenu(anchor) {
  const b = buf();
  if (!b) return;
  const draft = b.kind !== 'builtin', saved = b.kind === 'draft';
  menu(anchor, `${draft ? `<button class="row" data-pick="save"${isDirty(b) || b.kind === 'new' ? '' : ' disabled'}><span>Save</span><kbd>⌘S</kbd></button>
      <button class="row" data-pick="review"${saved ? '' : ' disabled'}><span>Request a review…</span></button><hr>` : ''}
    <button class="row" data-pick="ref"><span>Scripting reference</span></button>
    ${saved ? '<hr><button class="row" data-pick="delete"><span>Delete…</span></button>' : ''}`,
  (pick) => {
    if (pick === 'save') save(b);
    else if (pick === 'review') reviewDialog();
    else if (pick === 'ref') referenceDialog();
    else if (pick === 'delete') deleteDialog(b.name);
  });
}
async function referenceDialog() {
  const r = await send('GET', '/api/tester/drafts/reference');
  const d = dialog(`<h2>Scripting reference</h2><p>What a strategy script may use. It only ever runs inside the sandboxed backtest.</p><pre></pre>
    <div class="acts"><button class="btn btn-default" data-x="cancel">Done</button></div>`);
  d.classList.add('wide');
  d.querySelector('pre').textContent = r.ok ? r.json.text : `Could not load it: ${r.error}`;
  d.addEventListener('click', (e) => { if (e.target.closest('[data-x]')) closeDialog(); });
}
async function pasteScript() {
  const b = openScript('', '');
  try {
    const txt = navigator.clipboard && navigator.clipboard.readText ? await navigator.clipboard.readText() : '';
    if (txt && /class\s+\w+\s*\(.*Strategy.*\)/.test(txt)) { b.code = txt; b.name = C.suggestName(txt, takenNames()); paintAll(); queueValidate(b, 0); }
  } catch (_) { /* the clipboard is the person's to give: they can press ⌘V */ }
}
function readFile(file) {
  if (!file) return;
  const rd = new FileReader();
  rd.onload = () => {
    const stem = file.name.replace(/\.[^.]+$/, '').toLowerCase().replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '');
    const code = String(rd.result || '');
    openScript(code, C.nameError(stem) || takenNames().includes(stem) ? C.suggestName(code, takenNames()) : stem);
  };
  rd.readAsText(file);
}

function reviewDialog() {
  const b = buf();
  if (!b || b.kind === 'builtin') return;
  const runOk = S.run && S.run.bundle && S.run.strategy === `draft_${b.name}`;
  const unsaved = isDirty(b);
  const d = dialog(`<h2>Request a review</h2>
    <p>This packages <b>${esc(b.name || 'this strategy')}</b>${runOk ? ' with its latest backtest' : ' (no backtest attached yet)'} into a file for a person to read before it can go anywhere near the desk. Nothing runs and nothing is switched on.</p>
    ${unsaved ? '<p>It has unsaved changes: it will be saved first.</p>' : ''}
    <textarea id="rvNote" placeholder="What is the idea, and what should the reviewer look at? (optional)"></textarea>
    <div class="acts"><button class="btn btn-outline" data-x="cancel">Cancel</button><button class="btn btn-default" data-x="go">Request review</button></div>`);
  $('#rvNote', d).focus();
  d.addEventListener('click', async (e) => {
    const x = e.target.closest('[data-x]');
    if (!x) return;
    if (x.dataset.x === 'cancel') return closeDialog();
    x.disabled = true;
    if (isDirty(b) && !(await save(b))) { closeDialog(); return; }
    const r = await send('POST', `/api/tester/drafts/${encodeURIComponent(b.name)}/review-request`,
      { note: $('#rvNote', d).value, ...(runOk ? { run_id: S.run.rid } : {}) });
    if (!r.ok) { closeDialog(); log(`<span class="err">Review not requested: ${esc(r.error)}</span>`); return; }
    const ck = r.json.checks || [];
    d.innerHTML = `<h2>Review requested</h2><p>Saved as a file. When you want it looked at, tell Claude: <code>review ${esc(r.json.id)}</code></p>
      <ul>${ck.map((c) => `<li class="${c.ok ? '' : 'no'}"><i>${c.ok ? '✓' : '○'}</i>${esc(c.label)}</li>`).join('')}</ul>
      <p style="margin:0"><code>${esc(r.json.md)}</code></p>
      <div class="acts"><button class="btn btn-default" data-x="cancel">Done</button></div>`;
    log(`Review requested · <b>${esc(r.json.id)}</b>`);
  });
}

function deleteDialog(name) {
  const d = dialog(`<h2>Delete ${esc(name)}?</h2><p>Its file is removed from your strategies. Past backtests of it stay in Recent runs.</p>
    <div class="acts"><button class="btn btn-outline" data-x="cancel">Keep it</button><button class="btn btn-default" data-x="go">Delete</button></div>`);
  d.addEventListener('click', async (e) => {
    const x = e.target.closest('[data-x]');
    if (!x) return;
    closeDialog();
    if (x.dataset.x !== 'go') return;
    const r = await send('DELETE', `/api/tester/drafts/${encodeURIComponent(name)}`);
    if (!r.ok) return log(`<span class="err">${esc(r.error)}</span>`);
    S.bufs.delete(`d:${name}`);
    if (S.cur === `d:${name}`) { S.cur = null; S.run = null; }
    await loadLists(); paintAll();
  });
}

/* ---- groups: the library in sections ----
   The groups and who is in them are the server's: one file beside the strategies, and no strategy's own file is
   ever changed for it. Which sections are folded shut is this browser's. */
const folded = new Set();
try { for (const g of JSON.parse(localStorage.getItem('hb_lab_folded') || '[]')) folded.add(String(g)); } catch (_) { /* private mode: all open */ }
const saveFolded = () => { try { localStorage.setItem('hb_lab_folded', JSON.stringify([...folded])); } catch (_) { /* private mode */ } };
function foldGroup(el) {
  const g = el.dataset.g, shut = !folded.has(g);
  if (shut) folded.add(g); else folded.delete(g);
  saveFolded();
  el.setAttribute('aria-expanded', String(!shut));       // in place, without a repaint: the chevron turns
  el.closest('.lb-g').classList.toggle('folded', shut);
}
/* every change answers the whole new state */
async function regroup(path, body) {
  const r = await send('POST', `/api/tester/groups${path}`, body);
  if (r.ok) { S.groups = r.json; paintLib(); }
  return r;
}
/* a row's ⋯: the one group this strategy is listed under */
function fileMenu(el) {
  const { id, name } = el.dataset, to = [...S.groups.groups, ''], cur = S.groups.members[id] || '';
  menu(el, `${to.length > 1 ? `<h6>Move to</h6>${to.map((g, i) => `<button class="row" data-pick="${i}"><span>${esc(g || 'Ungrouped')}</span>${g === cur ? '<small>✓</small>' : ''}</button>`).join('')}<hr>` : ''}
    <button class="row" data-pick="new"><span>New group…</span></button>`,
  async (pick) => {
    if (pick === 'new') return nameGroup('', id, name);
    if (to[pick] === cur) return;
    const r = await regroup('/move', { strategy: id, group: to[pick] });
    if (!r.ok) log(`<span class="err">Not moved: ${esc(r.error)}</span>`);
  });
}
/* a group's ⋯ */
function groupMenu(el) {
  const g = el.dataset.g, n = Number(el.dataset.n);
  menu(el, `<button class="row" data-pick="rename"><span>Rename…</span></button><hr>
    <button class="row" data-pick="delete"><span>Delete group${n ? '…' : ''}</span></button>`,
  (pick) => (pick === 'rename' ? nameGroup(g) : dropGroup(g, n)));
}
/* One sheet names a group: a new one (it takes along the strategy whose row asked for it), or a rename. */
function nameGroup(old = '', id = '', strategy = '') {
  const d = dialog(`<h2>${old ? 'Rename group' : 'New group'}</h2>
    ${old ? '' : `<p>${id ? `<b>${esc(strategy)}</b> moves into it.` : 'A section of your strategy list. To put a strategy in it, use the ⋯ on its row.'}</p>`}
    <input id="grName" value="${esc(old)}" placeholder="Name" maxlength="40" spellcheck="false" autocomplete="off" aria-label="Group name">
    <p class="err" id="grErr" role="alert" hidden></p>
    <div class="acts"><button class="btn btn-outline" data-x="cancel">Cancel</button><button class="btn btn-default" data-x="go">${old ? 'Rename' : 'Create'}</button></div>`);
  const inp = $('#grName', d), err = $('#grErr', d);
  inp.focus(); inp.select();
  let busy = false;
  const go = async () => {
    const name = inp.value.trim().replace(/\s+/g, ' ');
    if (busy) return;
    if (!name) { inp.classList.add('bad'); return inp.focus(); }
    if (name === old) return closeDialog();
    busy = true;
    const r = await (old ? regroup('/rename', { name: old, to: name }) : id ? regroup('/move', { strategy: id, group: name }) : regroup('', { name }));
    busy = false;
    if (!r.ok) { err.textContent = r.error; err.hidden = false; inp.classList.add('bad'); return inp.focus(); }
    if (old && folded.delete(old)) { folded.add(name); saveFolded(); paintLib(); }
    if (d.isConnected) closeDialog();                    // still this sheet (it was not dismissed while the answer came)
  };
  d.addEventListener('click', (e) => { const x = e.target.closest('[data-x]'); if (x) { if (x.dataset.x === 'go') go(); else closeDialog(); } });
  inp.addEventListener('keydown', (e) => { if (e.key === 'Enter' && !e.repeat) { e.preventDefault(); go(); } });
  inp.addEventListener('input', () => { inp.classList.remove('bad'); err.hidden = true; });
}
/* Deleting a group deletes no strategy: they go back to Ungrouped. An empty group goes without a question. */
function dropGroup(g, n) {
  const go = async () => {
    const r = await regroup('/delete', { name: g });
    if (!r.ok) return log(`<span class="err">Not deleted: ${esc(r.error)}</span>`);
    if (folded.delete(g)) saveFolded();
  };
  if (!n) return go();
  const d = dialog(`<h2>Delete the group “${esc(g)}”?</h2><p>Its ${n === 1 ? 'strategy goes' : `${n} strategies go`} back to Ungrouped. No strategy is deleted.</p>
    <div class="acts"><button class="btn btn-outline" data-x="cancel">Keep it</button><button class="btn btn-default" data-x="go">Delete group</button></div>`);
  d.addEventListener('click', (e) => { const x = e.target.closest('[data-x]'); if (!x) return; closeDialog(); if (x.dataset.x === 'go') go(); });
}

/* ---- painting ---- */
function paintAll() { paintLib(); paintEditor(); paintRes(); }

const ICON_DOC = '<svg class="lb-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 3.5H8A2.5 2.5 0 0 0 5.5 6v12A2.5 2.5 0 0 0 8 20.5h8a2.5 2.5 0 0 0 2.5-2.5V8z"/><path d="M14 3.5V8h4.5"/></svg>';
const ICON_LOCK = '<svg class="lb-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5.5" y="11" width="13" height="9" rx="2.5"/><path d="M8.5 11V8.2a3.5 3.5 0 0 1 7 0V11"/></svg>';
const ICON_PLUS = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5.5v13M5.5 12h13"/></svg>';
const ICON_PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7.5 4.8v14.4a.9.9 0 0 0 1.36.77l11.7-7.2a.9.9 0 0 0 0-1.54L8.86 4.03a.9.9 0 0 0-1.36.77z" fill="currentColor"/></svg>';
const ICON_MORE = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5.5" cy="12" r="1.7" fill="currentColor"/><circle cx="12" cy="12" r="1.7" fill="currentColor"/><circle cx="18.5" cy="12" r="1.7" fill="currentColor"/></svg>';
const ICON_CHEV = '<svg class="lb-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 5.5l6.5 6.5L9 18.5"/></svg>';
function paintLib() {
  const el = $('#labLib .in');
  if (!el) return;
  const unsaved = [...S.bufs.values()].filter((b) => b.kind === 'new');
  const rows = [
    ...unsaved.map((b) => ({ key: b.key, name: b.name || 'Untitled', sub: 'Not saved yet', dot: 'off', flag: '' })),
    ...S.drafts.map((d) => {
      const b = S.bufs.get(`d:${d.name}`), dirty = b && isDirty(b);
      const bad = b && b.valid ? !b.valid.ok : !d.ok;
      return { key: `d:${d.name}`, id: d.id, name: d.name, sub: bad ? 'Needs a fix' : dirty ? 'Edited' : 'Draft', dot: bad ? 'err' : dirty ? 'off' : '', flag: bad ? '!' : '' };
    })];
  const builtins = S.builtins.map((s) => ({ key: `b:${s.id}`, id: s.id, name: s.name || s.id, sub: s.root || '', lock: true }));
  const item = (r) => `<button class="lb-item${S.cur === r.key ? ' sel' : ''}" data-key="${esc(r.key)}" aria-current="${S.cur === r.key}"${r.lock ? ' title="Read-only"' : ''}>
        ${r.lock ? ICON_LOCK : ICON_DOC}<span class="it"><b>${esc(r.name)}</b><small>${esc(r.sub)}</small></span>${r.lock ? '<span></span>' : `<span class="lb-flag">${r.flag}</span>`}</button>`;
  /* with groups: each one a section that folds, then Ungrouped. A saved strategy's row carries a ⋯ that moves it. */
  const filed = (r) => (r.id ? `<div class="lb-row">${item(r)}<button class="hb-ib lb-more" data-act="file" data-id="${esc(r.id)}" data-name="${esc(r.name)}" aria-label="Move ${esc(r.name)} to a group" title="Move to a group" aria-haspopup="menu">${ICON_MORE}</button></div>` : item(r));
  const section = (s) => {
    if (!s.name && !s.rows.length) return '';
    const shut = folded.has(s.name), n = s.rows.length;
    return `<div class="lb-g${shut ? ' folded' : ''}"><div class="lb-gh"><button class="lb-sh" data-act="fold" data-g="${esc(s.name)}" aria-expanded="${!shut}">${ICON_CHEV}<span>${esc(s.name || 'Ungrouped')}</span><i>${n}</i></button>
        ${s.name ? `<button class="hb-ib lb-more" data-act="group" data-g="${esc(s.name)}" data-n="${n}" aria-label="Rename or delete the group ${esc(s.name)}" title="Rename or delete" aria-haspopup="menu">${ICON_MORE}</button>` : ''}</div>
      <div class="lb-gb">${s.rows.map(filed).join('') || '<div class="lb-empty">Move a strategy here from its ⋯</div>'}</div></div>`;
  };
  const top = el.scrollTop;
  const tabs = (row) => `<div class="lb-seg" role="presentation">${row.map(([v, t]) => `<button role="tab" data-act="view" data-v="${v}" data-fk="view:${v}" aria-selected="${S.view === v}">${t}</button>`).join('')}</div>`;
  const seg = `<div class="lb-segs" role="tablist" aria-label="What this list shows">${tabs(VIEWS)}${tabs(PIPE_TABS)}</div>`;
  if (pipeOn()) { paintPipe(el, `<div class="lb-top">${seg}</div>`, top); return; }      // its list here, its page in the middle
  if (S.view === 'bp') { el.innerHTML = `<div class="lb-top">${seg}</div>${blueprintList()}`; el.scrollTop = top; return; }
  if (S.view === 'tk') {
    el.innerHTML = `<div class="lb-top">${seg}</div>${toolkitHead()}<div id="tkList">${toolkitList()}</div>`;
    el.scrollTop = top;
    return;
  }
  el.innerHTML = `<div class="lb-top">${seg}<button class="hb-ib" data-act="new" aria-label="New strategy" title="New strategy">${ICON_PLUS}</button></div>
    ${rows.length ? '' : '<div class="lb-empty">Nothing here yet. Press + to paste a script or start from a template.</div>'}
    ${S.groups ? C.sections([...rows, ...builtins], S.groups).map(section).join('')
      : `${rows.map(item).join('')}<div class="lb-sh">Built-in</div>${builtins.map(item).join('')}`}`;
  el.scrollTop = top;
}

/* ---- the arsenal in the sidebar ----
   Every tool we have (blocks, chat tools, skills, scripts), in groups that fold; a click opens its code (read-only). Nothing here runs anything. */
function toolkitHead() {
  const T = S.tk;
  if (!T || T.error) return '';
  const n = T.groups.reduce((a, g) => a + g.items.length, 0);
  return `<div class="tk-find"><input id="tkQ" type="search" placeholder="Find a tool: ${n} in all" value="${esc(S.tkQ)}" spellcheck="false" autocomplete="off" aria-label="Find a tool"></div>`;
}
function toolkitList() {
  const T = S.tk;
  if (!T) return '<div class="lb-empty">Loading the arsenal…</div>';
  if (T.error) return `<div class="lb-empty">${esc(T.error)}</div>`;
  const groups = C.tkFilter(T.groups, S.tkQ), searching = !!S.tkQ.trim();
  if (!groups.length) return '<div class="lb-empty">Nothing matches.</div>';
  const row = (it) => {
    const st = C.tkStatus(it), mk = C.tkMarkets(it);
    return `<button class="tk-row" data-act="tkblock" data-id="${esc(it.id)}" title="Open its code"><span class="tk-nm"><b>${esc(it.name)}</b></span>
      <span class="tk-wd">${esc(C.tkClip(it.words))}</span><span class="tk-mt">${it.sub ? `<i>${esc(it.sub)}</i>` : ''}${mk ? `<i>${esc(mk)}</i>` : ''}${st ? `<i class="${st.tone}">${esc(st.text.length > 40 ? st.text.slice(0, 38) + '…' : st.text)}</i>` : ''}</span></button>`;
  };
  const notes = (T.notes || []).map((n) => `<div class="lb-empty err">${esc(n)}</div>`).join('');
  return notes + groups.map((g) => {
    const key = `tk:${g.id}`, shut = !searching && folded.has(key);
    return `<div class="lb-g${shut ? ' folded' : ''}"><div class="lb-gh"><button class="lb-sh" data-act="fold" data-g="${esc(key)}" aria-expanded="${!shut}" title="${esc(g.words)}">${ICON_CHEV}<span>${esc(g.title)}</span><i>${g.items.length}</i></button></div>
      <div class="lb-gb">${g.items.map(row).join('')}</div></div>`;
  }).join('');
}
/* A block's code: its parts in the order the server gave them, each a source with its line numbers. */
function codeSheet(id) {
  const it = C.tkFind(S.tk && S.tk.groups, id);
  if (!it) return;
  const parts = C.tkParts(it, S.tk.sources), st = C.tkStatus(it), mk = C.tkMarkets(it);
  const sides = (it.sides || []).map((x) => `<li><b>${esc(x.side)}</b> ${esc(x.words)}</li>`).join('');
  const d = dialog(`<div class="tk-head"><h2>${esc(it.name)}</h2><span class="tk-mt">${mk ? `<i>${esc(mk)}</i>` : ''}${st ? `<i class="${st.tone}">${esc(st.text)}</i>` : ''}</span></div>
    ${sides ? `<ul class="tk-sides">${sides}</ul>` : `<p>${esc(it.words)}</p>`}
    ${parts.length > 1 ? `<div class="tk-jump" role="tablist" aria-label="Parts of its code">${parts.map((p) => `<button data-jump="${p.n}" title="${esc(p.label)}">${p.n}. ${esc(p.label.replace(/\s*\(.*$/, '').replace(/^The check.*/, 'The check'))}</button>`).join('')}</div>` : ''}
    <div class="tk-body">${parts.length ? parts.map((p) => `<section class="tk-part" id="tkp${p.n}"><header><b>${p.n}. ${esc(p.label)}</b><code>${esc(p.span)}</code></header>
      <div class="tk-code"><pre class="tk-gut" aria-hidden="true">${C.tkGutter(p.start, p.end)}</pre><pre class="tk-src" tabindex="0" aria-label="${esc(p.label)}"><code>${p.plain ? esc(p.code) : C.highlight(p.code)}</code></pre></div>${p.note ? `<small class="tk-note">${esc(p.note)}</small>` : ''}</section>`).join('')
      : '<p>No code was found for this block.</p>'}</div>
    <div class="acts"><button class="btn btn-outline" data-x="cancel">Close</button></div>`);
  d.classList.add('wide', 'tk-dlg');
  d.addEventListener('click', (e) => {
    const j = e.target.closest('[data-jump]');
    if (j) { const t = d.querySelector(`#tkp${j.dataset.jump}`); if (t) t.scrollIntoView({ block: 'start', behavior: 'smooth' }); return; }
    if (e.target.closest('[data-x]')) closeDialog();
  });
}

/* ---- the blueprint toolkit in the sidebar ----
   The ideas on file and every tool of the blueprint, in the order of its phases. A tool opens as a sheet: its inputs
   as a form, Run, and the tool's own answer in plain words -- the same answer a chat gets, because the chart service
   runs the same tool. Nothing here judges anything, and nothing here can reach the desk. */
function blueprintList() {
  const B = S.bp;
  if (!B) return '<div class="lb-empty">Loading the toolkit…</div>';
  if (B.error) return `<div class="lb-empty">${esc(B.error)}</div>`;
  const idea = (i) => `<button class="lb-item bp-row${S.bpIdea === i.name ? ' sel' : ''}" data-act="bpidea" data-name="${esc(i.name)}" title="Where it stands and what is next">
      ${ICON_DOC}<span class="it"><b>${esc(i.name)}</b><small>${esc(C.bpIdeaLine(i))}</small></span><span></span></button>`;
  const tool = (t) => `<button class="lb-item bp-row" data-act="bptool" data-tool="${esc(t.name)}" title="${esc(t.description.slice(0, 180))}">
      ${ICON_PLAY}<span class="it"><b>${esc(C.bpTitle(t.name))}</b><small>${esc(C.bpPhase(t.phase))}</small></span><span></span></button>`;
  return `<div class="lb-sh">Ideas</div>${B.ideas.length ? B.ideas.map(idea).join('') : '<div class="lb-empty">No idea yet. Start with Blocks, then write an Idea card.</div>'}
    <div class="lb-sh">Tools, in order</div>${B.tools.map(tool).join('')}
    <div class="lb-empty bp-note">Every tool follows BLUEPRINT.md and saves in the app. The same tools run in any chat.</div>`;
}
function bpField(f, v) {
  const id = `bpF_${f.key}`, lab = `<label for="${id}">${esc(f.key.replace(/_/g, ' '))}${f.required ? '' : ' <i>optional</i>'}</label>`;
  const help = f.help ? `<small>${esc(f.help)}</small>` : '';
  if (f.kind === 'bool') return `<div class="bp-f bp-check"><input type="checkbox" id="${id}" data-bp="${esc(f.key)}"${v ? ' checked' : ''}>${lab}${help}</div>`;
  if (f.kind === 'choice') return `<div class="bp-f">${lab}<select id="${id}" data-bp="${esc(f.key)}"><option value="">Default</option>${f.options.map((o) => `<option${o === v ? ' selected' : ''}>${esc(o)}</option>`).join('')}</select>${help}</div>`;
  if (f.kind === 'json') return `<div class="bp-f">${lab}<textarea id="${id}" data-bp="${esc(f.key)}" spellcheck="false" rows="7">${esc(v == null ? f.starter : v)}</textarea>${help}</div>`;
  const list = f.key === 'name' && S.bp && S.bp.ideas.length ? ' list="bpIdeas"' : '';
  return `<div class="bp-f">${lab}<input id="${id}" data-bp="${esc(f.key)}" value="${esc(v == null ? '' : v)}"${f.kind === 'int' || f.kind === 'number' ? ' inputmode="decimal"' : ''}${list} spellcheck="false" autocomplete="off"${f.kind === 'list' ? ' placeholder="name, name"' : ''}>${help}</div>`;
}
function toolSheet(name, preset = {}, runNow = false) {
  const t = S.bp && S.bp.tools && S.bp.tools.find((x) => x.name === name);
  if (!t) return;
  const fields = C.bpFields(t.inputs), start = { ...(S.bpIdea && fields.some((f) => f.key === 'name') ? { name: S.bpIdea } : {}), ...preset };
  const once = name === 'blueprint_test' ? '<p class="err bp-once">The test days are read ONCE for an idea. A read cannot be taken back, and a fail is final.</p>' : '';
  const d = dialog(`<h2>${esc(C.bpTitle(name))}</h2><p><b>${esc(C.bpPhase(t.phase))}.</b> ${esc(t.description.charAt(0).toUpperCase() + t.description.slice(1))}</p>${once}
    <div class="bp-form">${fields.map((f) => bpField(f, start[f.key])).join('')}</div>
    <datalist id="bpIdeas">${S.bp.ideas.map((i) => `<option value="${esc(i.name)}">`).join('')}</datalist>
    <p class="err" id="bpErr" role="alert" hidden></p>
    <div class="acts"><button class="btn btn-outline" data-x="cancel">Close</button><button class="btn btn-default" data-x="go">Run</button></div>
    <pre class="bp-out" id="bpOut" tabindex="0" aria-live="polite" hidden></pre>`);
  d.classList.add('wide');
  const err = $('#bpErr', d), out = $('#bpOut', d), goBtn = $('[data-x="go"]', d);
  let busy = false;
  const go = async () => {
    if (busy) return;
    const values = {};
    for (const x of d.querySelectorAll('[data-bp]')) values[x.dataset.bp] = x.type === 'checkbox' ? x.checked : x.value;
    const got = C.bpArgs(fields, values);
    for (const x of d.querySelectorAll('[data-bp]')) x.classList.toggle('bad', !!got.error && x.dataset.bp === got.key);
    err.hidden = !got.error;
    if (got.error) { err.textContent = got.error; const x = d.querySelector(`[data-bp="${got.key}"]`); if (x) x.focus(); return; }
    busy = true; goBtn.disabled = true; goBtn.textContent = 'Running…';
    out.hidden = false; out.textContent = 'Running…'; out.classList.remove('bad');
    const r = await send('POST', '/api/tester/blueprint/run', { tool: name, args: got.args });
    busy = false; goBtn.disabled = false;
    if (!d.isConnected) return;                       // the sheet was closed while the tool ran: its answer is saved in the app
    const text = r.ok ? r.json.text : r.error;
    out.textContent = text; out.classList.toggle('bad', !r.ok || r.json.ok === false);
    const job = r.ok ? C.bpJob(text) : '', jf = d.querySelector('[data-bp="job_id"]');
    if (job && jf) jf.value = job;                    // a job that is still going: Run again keeps waiting on it
    goBtn.textContent = job && jf ? 'Keep waiting' : 'Run again';
    if (got.args.name) S.bpIdea = got.args.name;
    loadBlueprint();
  };
  d.addEventListener('click', (e) => { const x = e.target.closest('[data-x]'); if (x) { if (x.dataset.x === 'go') go(); else closeDialog(); } });
  d.addEventListener('keydown', (e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && !e.repeat) { e.preventDefault(); go(); } });
  const first = d.querySelector('[data-bp]');
  if (runNow) go(); else if (first) first.focus();
}

/* ---- the strategy pipeline in the sidebar ----
   Three views: the Queue (every idea and where it stands), the Book (the finishers) and the Guide (six steps and the ladder of stages).
   While one of them is open the MIDDLE of the page is theirs (#labPipe): the editor, the chart and the result are hidden, not rebuilt
   (applyPanels shows them as switched off and leaves P, the person's own choice, alone), so leaving the view brings everything back as
   it was. The sidebar keeps the list (the ideas, the strategies) or, beside the Guide, three lines of what is happening now.
   ONE answer of the chart service feeds all three (GET /api/tester/pipeline), asked again every 5 s while one of them is on screen.
   The page judges nothing: a status, a reason and a number are shown as they came (the pure half, C.pl*, only picks words and marks).
   What it can post: an idea card, start / pause / resume, and the owner's yes or no for an idea that passed every stage. Nothing here
   can skip a stage or change a pass line, and nothing here can reach the desk. */
let plTimer = 0, plLoading = false, plAgain = false, plIdeaSeq = 0;
const plOpen = () => pipeOn() && !document.hidden;
async function loadPipeline(force = false) {
  if (plLoading) { plAgain = plAgain || force; return; }      // never two at once: the one in hand is followed by one more
  plLoading = true;
  const r = await send('GET', '/api/tester/pipeline');
  plLoading = false;
  const was = S.pl;
  let changed = force === true;
  if (r.ok && r.json) {
    const text = JSON.stringify(r.json);
    if (!was || !was.data || was.stale || was.text !== text) { S.pl = { data: r.json, text, stale: false, error: '' }; changed = true; }
  } else if (was && was.data) {        // the app cannot be reached: the last answer stays, and the page says so
    if (!was.stale) { was.stale = true; changed = true; }
  } else {
    const error = r.status === 404 ? 'The chart service is from before the pipeline: restart it once to see it here.' : String(r.error || 'No answer');
    if (!was || was.error !== error) { S.pl = { data: null, text: '', stale: false, error }; changed = true; }
  }
  if (r.ok && r.json) plSelect();
  if (changed && plOpen()) paintLib();      // only when the answer changed: the scroll and the keyboard stay where they were
  if (plAgain) { plAgain = false; loadPipeline(true); }
}
/* The one timer: it runs while a pipeline view is open and the window is visible, and at no other time. */
function plSync() {
  const on = plOpen();
  if (on === !!plTimer) return;
  clearInterval(plTimer); plTimer = 0;
  if (on) { loadPipeline(); plTimer = setInterval(loadPipeline, 5000); }
}
function setView(v) {
  S.view = VIEW_IDS.includes(v) ? v : 'lib';
  try { localStorage.setItem('hb_lab_view', S.view); } catch (_) { /* private mode */ }
  if (!pipeOn()) S.plSaid = null;
  S.plArmed = '';
  plSelect();
  applyPanels(false);           // the middle is the pipeline's while one of its views is open, and the editor's again after (it also sets the timer)
  paintLib();
  if (S.view === 'bp') loadBlueprint(); else if (S.view === 'tk') loadToolkit();
}
/* What is selected in each list: the one that was, while it is still there, else the first; and the selected idea's own page. */
function plSelect() {
  const A = S.pl && S.pl.data;
  if (!A) return;
  const names = (A.ideas || []).map((i) => i.name);
  if (S.plWant && names.includes(S.plWant)) { S.plIdea = S.plWant; S.plWant = ''; }      // an idea just added, once the Queue lists it
  S.plIdea = C.plPick(names, S.plIdea);
  S.plCard = C.plPick((A.book || []).map((c) => c.name), S.plCard);
  if (S.view === 'pq' && S.plIdea) loadIdea(S.plIdea);
}
/* One idea in full (GET /pipeline/idea/<name>): asked again when its row in the Queue changed, or when the last try got no answer.
   What was on the page stays until the new answer is here. */
async function loadIdea(name) {
  const A = S.pl && S.pl.data, key = JSON.stringify((A && (A.ideas || []).find((i) => i.name === name)) || null), was = S.plDetail;
  if (was && was.name === name && was.key === key && (was.loading || !was.error)) return;
  const seq = ++plIdeaSeq, old = was && was.name === name ? was : { name, data: null, text: '', error: '' };
  S.plDetail = { ...old, key, loading: true };
  const r = await send('GET', `/api/tester/pipeline/idea/${encodeURIComponent(name)}`);
  if (seq !== plIdeaSeq) return;                              // a newer one was asked for
  const ok = r.ok && !!r.json;
  const next = { name, key, loading: false, data: ok ? r.json : old.data, text: ok ? JSON.stringify(r.json) : old.text, error: ok || old.data ? '' : String(r.error || 'no answer') };
  S.plDetail = next;
  if ((next.text !== old.text || next.error !== old.error) && plOpen()) paintLib();
}
const plKv = (rows) => `<div class="rs-group pl-grp">${rows.map(([k, v]) => `<div class="pl-kv"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('')}</div>`;
const plChip = (label, tone) => `<span class="rs-chip pl-chip ${tone}">${esc(label)}</span>`;
const plStage = (n, name, mark, text, lines) => `<section class="pl-stage"><header><b><span>Stage ${n}</span> ${esc(name)}</b><span class="pl-mark ${mark.tone}">${esc(mark.text)}</span></header>
    ${text ? `<p>${esc(text)}</p>` : ''}
    ${(lines || []).length ? `<ul class="pl-lines">${lines.map((x) => { const k = C.plMark(x.passed); return `<li class="${k.tone}"><i>${esc(k.text)}</i><span>${esc(x.text)}</span></li>`; }).join('')}</ul>` : ''}</section>`;

/* -- the sidebar: a list, or (beside the Guide) what is happening now -- */
function pipeSide() {
  const L = S.pl;
  if (!L) return '<div class="lb-empty" role="status">Loading…</div>';
  if (!L.data) return `<div class="lb-empty" role="status">${esc(L.error)}</div>`;
  const A = L.data;
  if (S.view === 'pg') return `<div class="pl-head">${C.plSummary(A).map((t, i) => `<p class="${i ? 'pl-quiet' : 'pl-count'}">${esc(t)}</p>`).join('')}</div>`;
  if (S.view === 'pb') {
    const book = A.book || [];
    if (!book.length) return '<div class="lb-empty">No strategies yet.</div>';
    return `<div class="pl-list">${book.map((card) => {
      const b = C.plBookCard(card), on = b.name === S.plCard;
      return `<button class="tk-row pl-row${on ? ' sel' : ''}" data-act="plbook" data-name="${esc(b.name)}" data-fk="book:${esc(b.name)}" aria-current="${on}">
        <span class="tk-nm"><b title="${esc(b.name)}">${esc(b.name)}</b>${plChip(b.label, b.tone)}</span><span class="pl-fam">${esc(b.sub)}</span></button>`;
    }).join('')}</div>`;
  }
  const ideas = A.ideas || [], names = Object.fromEntries((A.stages || []).map((s) => [s.n, s.name]));
  if (!ideas.length) return '<div class="lb-empty">No ideas yet.</div>';
  return `<div class="pl-list">${ideas.map((it) => {
    const d = C.plDots(it), why = String(it.why || '').trim(), on = it.name === S.plIdea;
    return `<button class="tk-row pl-row${on ? ' sel' : ''}" data-act="plidea" data-name="${esc(it.name)}" data-fk="idea:${esc(it.name)}" aria-current="${on}">
      <span class="tk-nm"><b title="${esc(it.name)}">${esc(it.name)}</b>${plChip(it.label, C.plTone(it.label))}</span>
      <span class="pl-meta"><span class="pl-fam">${esc(it.family || '—')}</span><span class="pl-dots" role="img" aria-label="${esc(d.label)}">${d.dots.map((k, i) => `<i class="${k}" title="${esc(`Stage ${i}: ${names[i] || ''}`)}"></i>`).join('')}</span></span>
      ${why ? `<span class="tk-wd pl-why" title="${esc(why)}">${esc(why)}</span>` : ''}</button>`;
  }).join('')}</div>`;
}

/* -- the middle: the view's own page -- */
function pipeMain() {
  const L = S.pl;
  if (!L) return '<div class="pp"><p class="pp-lead" role="status">Loading…</p></div>';
  if (!L.data) return `<div class="pp"><p class="pp-lead" role="status">${esc(L.error)}</p></div>`;
  const stale = L.stale ? '<p class="pp-note pl-stale" role="status">Can’t reach the app. Showing the last known state.</p>' : '';
  const said = S.plSaid ? `<div class="pl-said${S.plSaid.bad ? ' bad' : ''}" role="status"><pre>${esc(S.plSaid.text)}</pre><button class="hb-ib" data-act="plhide" data-fk="hide" aria-label="Hide this message" title="Hide">×</button></div>` : '';
  return `<div class="pp">${stale}${said}${S.view === 'pq' ? queueMain(L.data) : S.view === 'pb' ? bookMain(L.data) : guideMain(L.data)}</div>`;
}
/* The Queue's page: the count and the ONE button on top, always; under them the selected idea in full -- why it stopped (the ONE
   line), its card in words, every stage that ran with PASS / FAIL / — and its lines as the server wrote them. An idea that passed
   every stage carries the owner's two buttons. */
function queueMain(A) {
  const c = C.plControl(A), ideas = A.ideas || [];
  const bar = `<div class="pp-bar"><p class="pl-count">${esc(C.plCount(A.counts)).replace(/(\d) /g, '$1 ')}</p>
    <div class="pl-ctl"><button class="btn btn-default" data-act="plctl" data-fk="ctl"${c.enabled && !S.plBusy ? '' : ' disabled'}>${esc(c.label)}</button><span class="pl-quiet">${esc(c.line)}</span></div></div>`;
  const idle = !(A.runner && (A.runner.running || A.runner.paused));       // nothing to count and nothing to start: the one line says it
  if (!ideas.length) return `${idle ? '' : bar}<div class="pp-empty"><p>No ideas yet. Add one from the Guide, or tell Claude your idea in any chat.</p>
    <button class="btn btn-outline" data-act="pladd" data-fk="add">Write an idea</button></div>`;
  const D = S.plDetail && S.plDetail.name === S.plIdea ? S.plDetail : null;
  if (!S.plIdea) return `${bar}<div class="pp-empty"><p>Pick an idea on the left to see how it did.</p></div>`;
  if (!D || !D.data) return `${bar}<div class="pp-empty"><p role="status">${D && D.error ? `Could not load ${esc(S.plIdea)}: ${esc(D.error)}` : 'Loading…'}</p></div>`;
  const I = D.data, st = I.state || {}, card = I.card || {}, why = String(st.why || '').trim(), passed = st.label === 'Passed', armed = S.plArmed === S.plIdea;
  const list = (xs, line) => (xs || []).filter((x) => x && typeof x === 'object').map((x) => `<li>${esc(line(x))}</li>`).join('') || '<li>None</li>';
  return `${bar}<article class="pp-doc" aria-label="${esc(S.plIdea)}">
    <div class="tk-head"><h2>${esc(S.plIdea)}</h2>${plChip(st.label, C.plTone(st.label))}</div>
    ${why ? `<p class="pl-stop"><b>${st.label === 'Refused' ? 'Refused' : st.label === 'Problem' ? 'Problem' : 'Stopped'}:</b> ${esc(why)}</p>` : ''}
    <p class="pl-say">${esc([card.why, card.loser].filter(Boolean).join(' '))}</p>
    ${plKv([['Market', card.market || '—'], ['Time of day', C.plSession(card.session)], ['Sides', `${C.plSide(card.sides)}${card.sides_why ? `: ${card.sides_why}` : ''}`], ['Entry rule', st.family || '—']])}
    <h3>Ways to enter</h3><ul class="pl-ul">${list(card.ways, C.plWayLine)}</ul>
    <h3>Indicators to try</h3><ul class="pl-ul">${list(card.indicators, C.plIndLine)}</ul>
    <h3>Stages</h3>${(I.stages || []).map((s) => plStage(s.n, s.name, C.plMark(s.passed), s.text, s.lines)).join('') || '<p class="pp-note">No stage has run yet.</p>'}
    ${passed ? `<div class="pp-acts"><p>${armed ? 'It goes in the Book. This cannot be undone.' : 'It passed every stage. Read its card, then say yes or no.'}</p>
      <button class="btn btn-outline" data-act="plrefuse" data-fk="refuse"${S.plBusy ? ' disabled' : ''}>Refuse</button>
      <button class="btn btn-default" data-act="plapprove" data-fk="approve"${S.plBusy ? ' disabled' : ''}>${armed ? 'Yes, put it in the Book' : 'Approve'}</button></div>` : ''}</article>`;
}
/* The Book's page: the selected strategy's whole card -- every fact, every account (one whose rules are not confirmed says so), each
   stage's first line. */
function bookMain(A) {
  const card = (A.book || []).find((c) => c && c.name === S.plCard);
  if (!card) return '<div class="pp-empty"><h2>The Book</h2><p>The book is empty. A strategy lands here after it passes every stage and you approve it.</p></div>';
  const b = C.plBookCard(card), full = C.plBookFull(card, A.stages);
  return `<article class="pp-doc" aria-label="${esc(b.name)}"><div class="tk-head"><h2>${esc(b.name)}</h2>${plChip(b.label, b.tone)}</div>
    <p class="pl-say">${esc(full.why)}</p>${plKv(full.facts)}
    <p class="pp-note">Money is for one contract, after costs, on the days it had never seen.</p>
    <h3>Accounts</h3>${full.accounts.map((a) => `<h4 class="pl-h4">${esc(a.name)}</h4>${plKv(a.rows)}`).join('') || '<p class="pp-note">None on this card.</p>'}
    <h3>Stages</h3>${full.stages.map((s) => plStage(s.n, s.name, s.mark, s.text)).join('') || '<p class="pp-note">None on this card.</p>'}</article>`;
}
/* The Guide's page: six steps, each one sentence and one button that is grey until its step makes sense (the reason is written under
   it), then the ladder of the eight stages with the ideas that are at each one now. */
function guideMain(A) {
  const step = (s) => `<li class="pl-step"><span class="pl-num" aria-hidden="true">${s.n}</span><div><b>${esc(s.title)}</b><p>${esc(s.words)}</p>
      ${s.button ? `<button class="btn ${s.primary && s.enabled ? 'btn-default' : 'btn-outline'}" data-act="plstep" data-n="${s.n}" data-fk="step:${s.n}"${s.enabled && !(s.n === 2 && S.plBusy) ? '' : ' disabled'}${s.reason ? ` aria-describedby="plWhy${s.n}"` : ''}>${esc(s.button)}</button>` : `<p class="pl-now" role="status">${esc(s.status)}</p>`}
      ${s.reason ? `<small class="pl-help" id="plWhy${s.n}">${esc(s.reason)}</small>` : ''}</div></li>`;
  const rung = (s) => `<li><span class="pl-num" aria-hidden="true">${s.n}</span><div><div class="pl-rt"><b>${esc(s.name)}</b><i class="${s.ideas ? 'on' : ''}">${esc(s.count)}</i></div><p>${esc(s.words)}</p></div></li>`;
  return `<h2>From an idea to the Book</h2><p class="pp-lead">Six steps. The computer does the testing. You look at the end.</p>
    <ol class="pl-steps">${C.plGuide(A).map(step).join('')}</ol>
    <h3>The eight stages</h3><p class="pp-note">Every idea climbs them one by one and stops at the first it fails. On the right: the ideas at each one now.</p>
    <ol class="pl-ladder" start="0">${C.plLadder(A).map(rung).join('')}</ol>`;
}
/* Both halves painted: only what changed is put in the page, the scroll stays (a new selection starts at the top) and so does the keyboard. */
let plPage = '', plMain = null;
function paintPipe(side, head, sideTop) {
  const main = document.querySelector('#labPipe .in'), at = document.activeElement;
  const fk = (at && (side.contains(at) || (main && main.contains(at))) ? at.dataset.fk : at === document.body ? S.plFk : '') || '';
  side.innerHTML = head + pipeSide();
  side.scrollTop = sideTop;
  if (main) {
    const html = pipeMain(), page = `${S.view}:${S.view === 'pq' ? S.plIdea : S.view === 'pb' ? S.plCard : ''}`, top = page === plPage ? main.scrollTop : 0;
    if (plMain !== html) { main.innerHTML = html; plMain = html; }
    main.scrollTop = top;
    plPage = page;
  }
  const back = fk ? [...root.querySelectorAll('[data-fk]')].find((x) => x.dataset.fk === fk && !x.disabled) : null;
  if (back && back !== document.activeElement) back.focus({ preventScroll: true });
  S.plFk = back ? '' : fk;        // a button that is grey while its action runs gets the keyboard back when it is done
}
function guideStep(n) {
  const A = S.pl && S.pl.data, s = A && C.plGuide(A).find((x) => x.n === n);
  if (!s || !s.enabled) return;
  if (n === 1) addSheet();
  else if (n === 2) pipeActions(s.actions);
  else if (n === 4) setView('pq');
  else if (n === 5) { S.plIdea = s.name; setView('pq'); }
}
function pickIdea(name) { S.plIdea = name; S.plArmed = ''; paintLib(); loadIdea(name); }
function pickCard(name) { S.plCard = name; paintLib(); }

/* One post to the pipeline -> {ok, text}: the server's own sentence either way (a refusal is ok false with its reason). */
async function pipeRun(body) {
  const r = await send('POST', '/api/tester/pipeline/run', body);
  return { ok: r.ok && !!r.json && r.json.ok !== false, text: r.ok ? String((r.json && r.json.text) || '') : String(r.error || '') };
}
/* After any action: what the server said, on top of the page, then the answer again. */
function pipeSaid(text, bad) {
  S.plSaid = { text: text || (bad ? 'It did not work.' : 'Done.'), bad };
  paintLib();
  S.plFk = '';
  loadPipeline(true);
}
/* Start, pause, resume: the actions the button's label stands for, in order; the first one refused ends it. */
async function pipeActions(actions) {
  if (S.plBusy || !actions.length) return;
  S.plBusy = true; paintLib();
  const said = [];
  let bad = false;
  for (const a of actions) {
    const r = await pipeRun({ action: a });
    said.push(r.text);
    if (!r.ok) { bad = true; break; }
  }
  S.plBusy = false;
  pipeSaid(said.filter(Boolean).join('\n'), bad);
}
/* The owner's yes, in two presses: the Book is never edited afterwards. */
async function approveIdea() {
  const name = S.plIdea;
  if (!name || S.plBusy) return;
  if (S.plArmed !== name) { S.plArmed = name; paintLib(); return; }
  S.plBusy = true; paintLib();
  const r = await pipeRun({ action: 'approve', name });
  S.plBusy = false; S.plArmed = '';
  pipeSaid(r.text, !r.ok);
}
/* The owner's no: it needs his reason, and cannot be sent without one. */
function refuseSheet(name) {
  if (!name) return;
  const d = dialog(`<h2>Refuse ${esc(name)}?</h2><p>It stays out of the Book. Say why in a sentence: the reason is kept with the idea.</p>
    <div class="bp-f pl-f"><label for="plWhy">Your reason</label><textarea id="plWhy" maxlength="400"></textarea></div>
    <p class="err pl-pre" id="plErr" role="alert" hidden></p>
    <div class="acts"><button class="btn btn-outline" data-x="cancel">Cancel</button><button class="btn btn-default" data-x="go" disabled>Refuse</button></div>`);
  const ta = $('#plWhy', d), go = $('[data-x="go"]', d), err = $('#plErr', d);
  let busy = false;
  ta.focus();
  ta.addEventListener('input', () => { go.disabled = busy || !ta.value.trim(); });
  d.addEventListener('click', async (e) => {
    const x = e.target.closest('[data-x]'), why = ta.value.trim();
    if (!x || busy) return;
    if (x.dataset.x === 'cancel') return closeDialog();
    if (!why) return;
    busy = true; go.disabled = true; go.textContent = 'Refusing…';
    const r = await pipeRun({ action: 'refuse', name, why });
    busy = false;
    if (r.ok) { if (d.isConnected) closeDialog(); S.plArmed = ''; return pipeSaid(r.text, false); }
    if (!d.isConnected) return pipeSaid(r.text, true);
    go.disabled = false; go.textContent = 'Refuse'; err.textContent = r.text; err.hidden = false;
  });
}

/* The add-idea form (the Guide's step 1), a sheet. Its lists are the server's (`rules`, `indicators`, `sessions`: the research
   toolkit's own block list): an entry rule that runs on the chosen market, its main setting from that rule's settings, three values
   to start from (what the library ran, or the default and its neighbours), each checked against the setting's limits as it is typed,
   and only the times of day the rule runs in. The button is grey until the card could pass, with what is missing written under it.
   A refusal shows the server's own words in the sheet and keeps everything typed; what was typed also survives a sheet closed by
   mistake (S.plForm). Without the lists (a toolkit that could not give them) every field takes text. */
function addSheet() {
  const A = S.pl && S.pl.data;
  if (!A) return;
  const d = dialog('<h2>Write an idea</h2>');
  d.classList.add('wide', 'pl-dlg');
  const F = S.plForm || (S.plForm = C.plForm()), hours = Object.fromEntries((A.sessions || []).map((x) => [x.name, x.words]));
  let busy = false, refused = '';
  const offer = () => C.plRules(A.rules, F.market), ruleOf = (w) => offer().rules.find((r) => r.name === w.family) || null;
  const settingOf = (w) => { const r = ruleOf(w); return (r && r.settings.find((x) => x.name === w.main_setting)) || null; };
  const put = (path, v) => { const ks = path.split('.'), last = ks.pop(); let o = F; for (const k of ks) o = o[k]; o[last] = v; };
  const opt = (v, t, cur) => `<option value="${esc(v)}"${String(v) === String(cur) ? ' selected' : ''}>${esc(t)}</option>`;
  const pick = (path, opts, cur, first = true, more = '') => `<select id="pf_${path}" data-pf="${path}"${more}>${first ? opt('', 'Choose…', cur) : ''}${opts.map(([v, t]) => opt(v, t, cur)).join('')}</select>`;
  const text = (path, v, prose = false, more = '') => `<input id="pf_${path}" data-pf="${path}" value="${esc(v)}" spellcheck="${prose}" autocomplete="off"${prose ? '' : ' autocapitalize="off"'}${more}>`;
  const field = (path, label, control, help = '') => `<div class="bp-f pl-f"><label for="pf_${path}">${esc(label)}</label>${control}${help ? `<small>${esc(help)}</small>` : ''}</div>`;
  /* a way whose rule or setting was just chosen starts from that setting's three values */
  const settle = (w) => {
    if (!w.main_setting) w.main_setting = C.plMainSetting(ruleOf(w));
    const s = settingOf(w);
    w.values = s ? C.plPrefill(s) : ['', '', ''];
  };
  /* what is typed is checked as it is typed: a value the setting does not take is marked, and the line under the three says what it must be */
  const sync = () => {
    const can = C.plCanSend(F, A.rules, A.indicators), go = $('[data-x="go"]', d);
    if (!go) return;
    F.ways.forEach((w, i) => {
      const s = settingOf(w), bad = (w.values || []).map((v) => (s ? C.plValueError(s, v) : ''));
      bad.forEach((b, k) => { const x = d.querySelector(`[data-pf="ways.${i}.values.${k}"]`); if (x) { x.classList.toggle('bad', !!b); x.setAttribute('aria-invalid', String(!!b)); } });
      const line = $(`#pe${i}`, d), k = bad.findIndex(Boolean);
      if (line) { line.textContent = k < 0 ? '' : `Value ${k + 1} must be ${bad[k]}.`; line.hidden = k < 0; }
    });
    go.disabled = busy || !can.ok;
    $('#plNeed', d).textContent = can.ok ? '' : `Still needed: ${can.needs.join('; ')}.`;
    $('[data-x="clear"]', d).hidden = JSON.stringify(F) === JSON.stringify(C.plForm());      // nothing typed: nothing to start over
  };
  const paint = (focus) => {
    const got = offer(), blocks = C.plIndicators(A.indicators, F.market), was = $('.pl-body', d), top = was ? was.scrollTop : 0;
    for (const w of F.ways) if (got.rules.length && w.family && !ruleOf(w)) { w.family = ''; w.main_setting = ''; w.values = ['', '', '']; }      // a rule that does not run on the market now chosen
    for (const x of F.indicators) {
      const b = blocks.find((k) => k.block === x.block);
      if (blocks.length && x.block && !b) { x.block = ''; x.side = ''; } else if (b && !b.sides.some((k) => k.side === x.side)) x.side = b.sides[0].side;
    }
    const times = C.plSessionsFor(F.ways.map(ruleOf)), narrowed = times.length < C.PL_SESSIONS.length;
    if (F.session && !times.some(([k]) => k === F.session)) F.session = '';         // a time of day the chosen rule does not run in
    const way = (w, i) => {
      const rule = ruleOf(w), s = settingOf(w), p = `ways.${i}`, lists = got.rules.length > 0;
      const none = got.hidden ? ` ${Number(got.hidden)} rule${got.hidden === 1 ? ' is' : 's are'} not listed: ${got.hidden === 1 ? 'it has' : 'they have'} no setting to try three values of.` : '';
      const value = (k) => (s && s.kind === 'choice'
        ? `<select data-pf="${p}.values.${k}" aria-label="Value ${k + 1} of way ${i + 1}">${opt('', 'Choose…', w.values[k])}${s.choices.map((c) => opt(c, c, w.values[k])).join('')}</select>`
        : `<input data-pf="${p}.values.${k}" value="${esc(w.values[k])}" aria-label="Value ${k + 1} of way ${i + 1}" aria-describedby="pe${i}" spellcheck="false" autocomplete="off" autocapitalize="off"${s && s.kind !== 'text' ? ' inputmode="decimal"' : ''}>`);
      return `<div class="pl-set" role="group" aria-labelledby="pw${i}"><div class="pl-leg"><b id="pw${i}">Way ${i + 1}</b>${F.ways.length > 1 ? `<button type="button" class="btn btn-ghost btn-sm" data-x="rmway" data-i="${i}" aria-label="Remove way ${i + 1}">Remove</button>` : ''}</div>
        ${field(`${p}.family`, 'Entry rule', lists ? pick(`${p}.family`, got.rules.map((r) => [r.name, r.name]), w.family) : text(`${p}.family`, w.family), rule ? rule.words : lists ? `What starts a trade.${none}` : 'The list could not be loaded. Type the rule’s name.')}
        ${field(`${p}.main_setting`, 'Its main setting', rule ? pick(`${p}.main_setting`, rule.settings.map((x) => [x.name, x.name]), w.main_setting, rule.settings.length > 1) : lists ? pick(`${p}.main_setting`, [], '', true, ' disabled') : text(`${p}.main_setting`, w.main_setting),
    s ? C.plSettingWords(s) : rule ? 'The one setting of this rule to try three values of.' : lists ? 'Choose an entry rule first.' : 'The one setting of this rule to try three values of.')}
        <div class="bp-f pl-f"><span class="pl-lab" id="pv${i}">Three values to try</span><div class="pl-vals" role="group" aria-labelledby="pv${i}">${[0, 1, 2].map(value).join('')}</div>
          <small class="pl-help pl-bad" id="pe${i}" role="alert" hidden></small></div></div>`;
    };
    const ind = (x, i) => {
      const b = blocks.find((k) => k.block === x.block), side = b && b.sides.find((k) => k.side === x.side), p = `indicators.${i}`;
      return `<div class="pl-set" role="group" aria-labelledby="pi${i}"><div class="pl-leg"><b id="pi${i}">Indicator ${i + 1}</b><button type="button" class="btn btn-ghost btn-sm" data-x="rmind" data-i="${i}" aria-label="Remove indicator ${i + 1}">Remove</button></div>
        <div class="pl-two">${field(`${p}.block`, 'Indicator', blocks.length ? pick(`${p}.block`, blocks.map((k) => [k.block, k.block]), x.block) : text(`${p}.block`, x.block))}
          ${field(`${p}.side`, 'Side', b ? pick(`${p}.side`, b.sides.map((k) => [k.side, k.side]), x.side, false) : text(`${p}.side`, x.side))}</div>
        ${side ? `<small class="pl-help">${esc(side.words)}</small>` : ''}
        ${field(`${p}.why`, 'Why it should help', text(`${p}.why`, x.why, true), 'One sentence.')}</div>`;
    };
    const fullW = F.ways.length >= C.PL_WAYS, fullI = F.indicators.length >= C.PL_INDS;
    d.innerHTML = `<h2 id="labDlgTitle">Write an idea</h2>
      <div class="pl-body" tabindex="-1"><div class="bp-form">
        ${field('name', 'Name', text('name', F.name), 'Small letters, numbers and _ , a letter first. For example: fvg_open')}
        ${field('why', 'Why should it make money?', text('why', F.why, true), 'One sentence.')}
        ${field('loser', 'Who loses?', text('loser', F.loser, true), 'One sentence. The two together: 8 words or more.')}
        <div class="pl-two">${field('market', 'Market', pick('market', C.PL_MARKETS.map((m) => [m, m]), F.market))}
          ${field('session', 'Time of day', pick('session', times, F.session), hours[F.session] || (narrowed ? 'Only the times the chosen entry rule runs in.' : 'New York time.'))}</div>
        ${field('sides', 'Sides', pick('sides', C.PL_SIDES, F.sides, false), 'Both = it may buy and it may sell.')}
        ${F.sides !== 'both' ? field('sides_why', 'Why one side only?', text('sides_why', F.sides_why, true), 'One sentence.') : ''}
        ${F.ways.map(way).join('')}
        <div class="pl-more"><button type="button" class="btn btn-outline btn-sm" data-x="addway"${fullW ? ' disabled' : ''}>Add another way</button><small class="pl-help">${fullW ? `${C.PL_WAYS} ways at most.` : `Up to ${C.PL_WAYS} ways to enter. Each is tested on 1-minute and on 5-minute bars.`}</small></div>
        ${F.indicators.map(ind).join('')}
        <div class="pl-more"><button type="button" class="btn btn-outline btn-sm" data-x="addind"${fullI ? ' disabled' : ''}>Add an indicator</button><small class="pl-help">${fullI ? `${C.PL_INDS} indicators at most.` : `You can leave this out. Up to ${C.PL_INDS}, each tried alone.`}</small></div>
      </div></div>
      <div class="pl-foot"><p class="pl-tip">Not sure how? Tell Claude your idea in any chat and it fills this in.</p>
        <p class="err pl-pre" id="plErr" role="alert"${refused ? '' : ' hidden'}>${esc(refused)}</p>
        <small class="pl-help pl-need" id="plNeed"></small>
        <div class="acts"><button class="btn btn-ghost pl-clear" data-x="clear">Start over</button><button class="btn btn-outline" data-x="cancel">Cancel</button><button class="btn btn-default" data-x="go" aria-describedby="plNeed">Add to the Queue</button></div></div>`;
    $('.pl-body', d).scrollTop = top;
    const at = focus ? [...d.querySelectorAll('[data-pf], [data-x]')].find((x) => x.dataset.pf === focus || x.dataset.x === focus) : null;
    (at && !at.disabled ? at : d).focus({ preventScroll: true });      // the keyboard never falls out of the sheet
    sync();
  };
  const go = async () => {
    if (busy || !C.plCanSend(F, A.rules, A.indicators).ok) return;
    busy = true; refused = '';
    const btn = $('[data-x="go"]', d);
    btn.disabled = true; btn.textContent = 'Adding…'; $('#plErr', d).hidden = true;
    const r = await pipeRun({ action: 'add', card: C.plCard(F) });
    busy = false;
    if (r.ok) {         // it is in the Queue: the sheet goes, the server's sentence shows, and the Queue opens on it
      const name = C.plCard(F).name;
      S.plForm = null;
      if (d.isConnected) closeDialog(false);
      S.plSaid = { text: r.text || 'Added.', bad: false };
      S.plWant = name;
      setView('pq'); loadPipeline(true);
      const tab = root.querySelector('[data-v="pq"]'); if (tab) tab.focus({ preventScroll: true });
      return;
    }
    if (!d.isConnected) return pipeSaid(r.text, true);
    refused = r.text || 'It was not added.';
    paint('go');        // the server's own words, and everything typed is still here
  };
  d.addEventListener('click', (e) => {
    const x = e.target.closest('[data-x]'), k = x && x.dataset.x, i = x ? Number(x.dataset.i) : 0;
    if (!x || busy) return;
    if (k === 'cancel') closeDialog();
    else if (k === 'addway' && F.ways.length < C.PL_WAYS) { F.ways.push(C.plWay()); paint(`ways.${F.ways.length - 1}.family`); }
    else if (k === 'rmway') { F.ways.splice(i, 1); paint('addway'); }
    else if (k === 'addind' && F.indicators.length < C.PL_INDS) { F.indicators.push(C.plInd()); paint(`indicators.${F.indicators.length - 1}.block`); }
    else if (k === 'rmind') { F.indicators.splice(i, 1); paint('addind'); }
    else if (k === 'clear') { Object.assign(F, C.plForm()); refused = ''; paint('name'); }
    else if (k === 'go') go();
  });
  /* a list that other fields hang on (the market, the rule, its setting, the indicator, the sides) paints the form again; typing never does */
  const edit = (e) => {
    const t = e.target, path = t.dataset && t.dataset.pf, list = t.tagName === 'SELECT';
    if (!path || list !== (e.type === 'change')) return;
    put(path, t.value);
    if (!list || /\.values\.\d$/.test(path)) return sync();
    const way = /^ways\.(\d)\.(family|main_setting)$/.exec(path);
    if (way) { if (way[2] === 'family') F.ways[way[1]].main_setting = ''; settle(F.ways[way[1]]); }
    if (/\.block$/.test(path)) put(path.replace(/block$/, 'side'), '');
    paint(path);
  };
  d.addEventListener('input', edit);
  d.addEventListener('change', edit);
  d.addEventListener('keydown', (e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'Enter' && !e.repeat) { e.preventDefault(); go(); } });
  paint('name');
}

function paintEditor() {
  const el = $('#labEd');
  const b = buf();
  if (!b) {
    el.innerHTML = `<div class="lab-welcome"><h2>Write or paste a strategy</h2>
      <p>Backtest it on real tick data in a sandbox, see every trade on the chart, and request a review when you like what you see. Nothing here ever runs on the desk.</p>
      <div class="acts"><button class="btn btn-default btn-lg" data-act="paste">Paste a script</button><button class="btn btn-outline btn-lg" data-act="new">Start from a template</button></div></div>`;
    paintHead();
    return;
  }
  const ro = b.kind === 'builtin';
  el.innerHTML = `<div class="ed-wrap" id="edWrap"><pre class="ed-gut" id="edGut" aria-hidden="true"></pre>
      <div class="ed-main"><pre class="ed-hl" aria-hidden="true"><code id="edHl"></code></pre>
        <textarea class="ed-ta" id="edTa" spellcheck="false" autocomplete="off" autocapitalize="off" autocorrect="off" wrap="off" aria-label="Python source" ${ro ? 'readonly' : ''}></textarea>
        <div class="ed-hint" id="edHint" hidden>Press <kbd>⌘V</kbd> to paste your script, or drop a .py file here.</div></div></div>
    <div class="ed-log" id="edLog"></div>`;
  $('#edTa').value = b.code || '';
  paintHead(); paintCode(); paintLog();
}
/* The document's name and state live in the top bar, with the one primary action (Run) and a More menu. */
function paintHead() {
  const b = buf(), doc = document.getElementById('labDoc'), acts = document.getElementById('labActs');
  if (!doc || !acts) return;
  if (!b) { doc.innerHTML = ''; acts.innerHTML = ''; return; }
  const ro = b.kind === 'builtin', busy = S.busy, dirty = isDirty(b);
  let cls = '', text = '', tip = '';
  if (ro) text = 'Built-in · read-only';
  else if (b.valid && !b.valid.ok) { const st = C.statusOf(b.valid); cls = 'err'; text = st.text; }
  else if (b.kind === 'new') text = (b.code || '').trim() ? 'Not saved yet' : '';
  else if (dirty) { cls = 'edited'; text = 'Edited'; }
  else if (b.valid && b.valid.ok) { text = C.metaLine(b.valid.meta); tip = b.savedAt ? `Saved ${C.ago(b.savedAt, Date.now())}` : ''; }
  else if (b.code && b.code.trim()) text = 'Checking…';
  const name = b.kind === 'new'
    ? `<input class="doc-input" id="edName" value="${esc(b.name)}" placeholder="name" spellcheck="false" autocomplete="off" autocapitalize="off" aria-label="Strategy name"><span class="doc-name"><i>.py</i></span>`
    : `<span class="doc-name">${esc(ro ? b.id : b.name)}<i>.py</i></span>`;
  const had = document.activeElement && document.activeElement.id === 'edName';   // typing a name must survive a repaint
  if (!had) doc.innerHTML = `${name}<span class="doc-state ${cls}" id="edState" title="${esc(tip || text)}">${esc(text)}</span>`;
  else { const st = document.getElementById('edState'); if (st) { st.className = `doc-state ${cls}`; st.textContent = text; st.title = tip || text; } }
  const canRun = !busy && (ro || (b.code || '').trim());
  acts.innerHTML = `<button class="btn btn-default lab-run${busy ? ' busy' : ''}" data-act="run"${canRun ? '' : ' disabled'} title="Run the backtest (⌘↵)">${ICON_PLAY}<span>${busy ? 'Running' : 'Run'}</span></button>
    <button class="hb-ib" data-act="more" aria-label="More" title="More" aria-haspopup="menu">${ICON_MORE}</button>`;
  const hint = $('#edHint'); if (hint) hint.hidden = !!(b.code && b.code.length) || ro;
}
function paintGutter() {
  const b = buf(), g = $('#edGut');
  if (!b || !g) return;
  const n = C.lineCount(b.code), bad = b.valid && !b.valid.ok ? b.valid.line : null;
  let h = '';
  for (let i = 1; i <= n; i++) h += (i === bad ? `<span class="err">${i}</span>` : i) + '\n';
  g.innerHTML = h;
}
function paintCode() {
  const b = buf(), hl = $('#edHl');
  if (!b || !hl) return;
  hl.innerHTML = C.highlight(b.code || '') + '\n ';
  paintGutter();
  syncScroll();
}
function syncScroll() {
  const ta = $('#edTa'), hl = $('#edHl'), g = $('#edGut');
  if (!ta || !hl) return;
  hl.style.transform = `translate(${-ta.scrollLeft}px, ${-ta.scrollTop}px)`;
  g.style.transform = `translateY(${-ta.scrollTop}px)`;
}

/* ---- the result ---- */
/* The equity chart: a smooth line, a soft fill, the break-even line, the high and the low labelled, and a scrubber. */
const money0 = (v) => `${v > 0 ? '+' : v < 0 ? MINUS : ''}$${Math.abs(Math.round(v)).toLocaleString('en-US')}`;
const EQ_DAY = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric', year: 'numeric' });
const EQ_MON = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', month: 'short' }), EQ_MONL = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', month: 'long' });
function eqPoints(eq) { const t = eq.t_ms || [], v = eq.equity || []; return t.map((ms, i) => ({ ms, v: Number(v[i]) || 0 })); }
/* at most ~140 points, always keeping the first, the last, the high and the low */
function eqThin(pts) {
  if (pts.length <= 140) return pts;
  const step = pts.length / 140, keep = new Set([0, pts.length - 1]); let hi = 0, lo = 0;
  pts.forEach((p, i) => { if (p.v > pts[hi].v) hi = i; if (p.v < pts[lo].v) lo = i; });
  keep.add(hi); keep.add(lo);
  for (let i = 0; i < 140; i++) keep.add(Math.round(i * step));
  return [...keep].filter((i) => i < pts.length).sort((a, b) => a - b).map((i) => pts[i]);
}
function takeaway(pts, net, trades) {
  if (!pts.length) return '';
  let lo = pts[0]; for (const p of pts) if (p.v < lo.v) lo = p;
  const day = Number(new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', day: 'numeric' }).format(new Date(lo.ms))), part = day < 11 ? 'early' : day < 21 ? 'mid' : 'late';
  const head = `${net > 0 ? 'Up' : net < 0 ? 'Down' : 'Flat at'} <b>$${Math.abs(Math.round(net)).toLocaleString('en-US')}</b> after fees over <b>${trades} trade${trades === 1 ? '' : 's'}</b>.`;
  return lo.v < 0 ? `${head} The lowest point was <b>${money0(lo.v)}</b>, in ${part} ${EQ_MONL.format(new Date(lo.ms))}.` : `${head} It never dipped below where it started.`;
}
let EQD = null;
function drawEq() {
  const box = $('#eqw'); EQD = null;
  if (!box || !S.run || !S.run.bundle) return;
  const pts = eqThin(eqPoints(S.run.bundle.equity || {}));
  if (pts.length < 2) { box.hidden = true; return; }
  const W = box.clientWidth, H = box.clientHeight, top = 20, bot = H - 22, padX = 6;
  const lo = Math.min(0, ...pts.map((p) => p.v)), hi = Math.max(0, ...pts.map((p) => p.v)), t0 = pts[0].ms, t1 = pts[pts.length - 1].ms;
  const X = (p) => padX + (t1 > t0 ? (p.ms - t0) / (t1 - t0) : 0) * (W - 2 * padX), Y = (v) => top + (1 - (v - lo) / ((hi - lo) || 1)) * (bot - top);
  const P = pts.map((p) => [X(p), Y(p.v)]);
  let d = `M${P[0][0].toFixed(1)},${P[0][1].toFixed(1)}`;
  for (let i = 0; i < P.length - 1; i++) { const p0 = P[i - 1] || P[i], p1 = P[i], p2 = P[i + 1], p3 = P[i + 2] || p2, t = 0.16;
    d += `C${(p1[0] + (p2[0] - p0[0]) * t).toFixed(1)},${(p1[1] + (p2[1] - p0[1]) * t).toFixed(1)} ${(p2[0] - (p3[0] - p1[0]) * t).toFixed(1)},${(p2[1] - (p3[1] - p1[1]) * t).toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`; }
  const z = Y(0).toFixed(1), svg = box.querySelector('svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.innerHTML = `<defs><linearGradient id="labEqFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="currentColor" stop-opacity=".28"/><stop offset=".7" stop-color="currentColor" stop-opacity=".05"/><stop offset="1" stop-color="currentColor" stop-opacity="0"/></linearGradient></defs>
    <path d="${d}L${P[P.length - 1][0].toFixed(1)},${bot + 14}L${P[0][0].toFixed(1)},${bot + 14}Z" fill="url(#labEqFill)"/><line class="eq-base" x1="${padX}" x2="${W - padX}" y1="${z}" y2="${z}"/><path class="eq-line" d="${d}"/>`;
  let iHi = 0, iLo = 0; pts.forEach((p, i) => { if (p.v > pts[iHi].v) iHi = i; if (p.v < pts[iLo].v) iLo = i; });
  const tag = (id, i, above) => { const e = $(id); if (!e) return; e.textContent = money0(pts[i].v); e.style.left = `${Math.max(28, Math.min(W - 28, P[i][0]))}px`; e.style.top = `${P[i][1] + (above ? -17 : 5)}px`; e.hidden = pts[i].v === 0; };
  tag('#eqHi', iHi, true); tag('#eqLo', iLo, false);
  const ax = $('#eqAx'); if (ax) { const m = (ms) => EQ_MON.format(new Date(ms)), a = m(t0), c = m(t1), b = m((t0 + t1) / 2); ax.innerHTML = `<span>${a}</span>${b !== a && b !== c ? `<span>${b}</span>` : '<span></span>'}<span>${c}</span>`; }
  EQD = { pts, P, W, padX };
  eqPlace(pts.length - 1);
}
function eqPlace(i) { const dot = $('#eqDot'); if (dot && EQD) { dot.style.left = `${EQD.P[i][0]}px`; dot.style.top = `${EQD.P[i][1]}px`; } }
root.addEventListener('pointermove', (e) => {
  const box = e.target.closest && e.target.closest('#eqw');
  if (!box || !EQD) return;
  const x = e.clientX - box.getBoundingClientRect().left; let i = 0, best = Infinity;
  EQD.P.forEach((p, k) => { const dx = Math.abs(p[0] - x); if (dx < best) { best = dx; i = k; } });
  box.classList.add('scrub'); eqPlace(i);
  const rule = $('#eqRule'), tip = $('#eqTip'); rule.style.left = `${EQD.P[i][0]}px`; tip.style.left = `${Math.max(48, Math.min(EQD.W - 48, EQD.P[i][0]))}px`;
  tip.innerHTML = `<b>${money0(EQD.pts[i].v)}</b>${esc(EQ_DAY.format(new Date(EQD.pts[i].ms)))}`;
});
root.addEventListener('pointerleave', (e) => { const box = e.target.closest && e.target.closest('#eqw'); if (box && EQD) { box.classList.remove('scrub'); eqPlace(EQD.pts.length - 1); } }, true);
window.addEventListener('resize', () => { if (EQD) drawEq(); });
function settingsHtml(b) {
  const f = b && formOf(b), meta = b && metaOf(b);
  if (!f || !meta) return '';
  const ins = meta.inputs || [];
  const rangeOpts = X.RANGES.map((r) => `<option value="${r.id}"${f.range.id === r.id ? ' selected' : ''}>${esc(r.label)}</option>`).join('');
  const inputRow = (i) => {
    const v = f.inputs[i.key], bad = X.inputError(i, v);
    if (i.type === 'bool') return `<label>${esc(i.label)}</label><input type="checkbox" data-in="${esc(i.key)}"${v ? ' checked' : ''}>`;
    if (i.type === 'choice') return `<label>${esc(i.label)}</label><select data-in="${esc(i.key)}">${i.choices.map((c) => `<option${c === v ? ' selected' : ''}>${esc(c)}</option>`).join('')}</select>`;
    return `<label title="${esc(i.label)}">${esc(i.label)}</label><input type="number" data-in="${esc(i.key)}" value="${esc(v)}" step="${i.step || 'any'}"${i.min != null ? ` min="${i.min}"` : ''}${i.max != null ? ` max="${i.max}"` : ''} class="${bad ? 'bad' : ''}">`;
  };
  const { start, end } = X.rangeDates(f.range);
  const spent = end && end >= X.rangeSpec('test').start;
  return `<details class="rs-group rs-set"${S.setOpen ? ' open' : ''}><summary><span>Settings</span><span>${esc(X.pillLabel ? X.pillLabel(f.range) : f.range.id)} · ${f.qty} contract${f.qty === 1 ? '' : 's'}</span></summary>
    <div class="grid"><label>Range</label><select data-f="range">${rangeOpts}</select>
      ${f.range.id === 'custom' ? `<label>From</label><input type="text" data-f="start" value="${esc(f.range.start)}" placeholder="YYYY-MM-DD"><label>To</label><input type="text" data-f="end" value="${esc(f.range.end)}" placeholder="YYYY-MM-DD">` : ''}
      ${spent ? '<div class="warn">This reaches July 2025 or later, the test days: one read, only for a locked strategy. Each look is recorded.</div>' : ''}
      <label>Contracts</label><input type="number" data-f="qty" value="${esc(f.qty)}" min="1" step="1">
      <label title="Dollars per contract, round trip">Fees ($ per contract)</label><input type="number" data-f="commission" value="${esc(f.commission)}" min="0" step="0.25">
      <label>Slippage (ticks)</label><input type="number" data-f="slippage_ticks" value="${esc(f.slippage_ticks)}" min="0" step="1">
      ${ins.length ? `<div class="sep"></div>${ins.map(inputRow).join('')}` : ''}</div></details>`;
}
/* "Oct 1 – Dec 13, 2024" / "2021 – 2024": a run's range the way a person writes it. */
const RS_DAY = new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', day: 'numeric' });
function rangeText(rg) {
  if (!rg) return '';
  const a = rg.start, b = rg.end;
  if (!a || !b) return rg.label || '';
  if (a.slice(5) === '01-01' && b.slice(5) === '12-31') return a.slice(0, 4) === b.slice(0, 4) ? a.slice(0, 4) : `${a.slice(0, 4)} – ${b.slice(0, 4)}`;
  const d = (x) => RS_DAY.format(new Date(`${x}T12:00:00Z`));
  return a.slice(0, 4) === b.slice(0, 4) ? `${d(a)} – ${d(b)}, ${b.slice(0, 4)}` : `${d(a)}, ${a.slice(0, 4)} – ${d(b)}, ${b.slice(0, 4)}`;
}
function paintRes() {
  const el = $('#labRes .in');
  if (!el) return;
  const b = buf(), top = el.scrollTop;
  if (!b) { el.innerHTML = '<div class="rs-empty"><h3>Backtest</h3><p>Pick a strategy, or paste one, to see how it would have done.</p></div>'; return; }
  const r = S.run && S.run.key === b.key ? S.run : null, settings = settingsHtml(b);
  let main = '', settingsDone = false;
  if (r && !r.bundle && (S.busy || (r.st && r.st.status === 'queued'))) {
    const p = X.progress(r.st || { status: 'queued' }), ind = p.frac == null;
    main = `<div class="rs-h"><b>Backtest</b></div><div class="rs-prog"><div class="t">${esc(p.text || 'Starting…')}</div><div class="rs-bar${ind ? ' ind' : ''}"><i style="width:${ind ? 38 : Math.round(p.frac * 100)}%"></i></div>
      <button class="btn btn-outline btn-sm" data-act="cancel">Cancel</button></div>`;
  } else if (r && r.bundle) {
    const run = r.bundle.run, a = run.report.summary.all, tl = X.tiles(run), by = (l) => tl.find((t) => t.label === l) || { value: '—' };
    const netv = a.net_profit || 0, pos = netv > 0, n = a.trades ?? 0, cap = run.capital || 0, pctv = cap ? netv / cap * 100 : null;
    const badges = X.badges(run).filter((x) => x.tone !== 'info');
    const used = run.coverage && run.coverage.used !== run.coverage.sessions ? ` · ${run.coverage.used} of ${run.coverage.sessions} sessions` : '';
    const split = (v) => { const m = /^([+−-]?\$?)(.*?)(%?)$/.exec(String(v)); return m ? `${esc(m[2])}${m[3] ? '<small>%</small>' : ''}` : esc(v); };
    main = `<div class="rs-h"><b>Backtest</b><span>${esc(rangeText(run.range))}</span></div>
      <div class="rs-hero"><div class="rs-net"><i>${netv > 0 ? '+' : netv < 0 ? MINUS : ''}$</i>${esc(Math.abs(Math.round(netv)).toLocaleString('en-US'))}</div>
        ${pctv == null ? '' : `<span class="rs-delta${pos ? '' : ' neg'}" title="Of the $${esc(Math.round(cap).toLocaleString('en-US'))} starting balance">${pos ? '▲' : netv < 0 ? '▼' : ''} ${Math.abs(pctv).toFixed(1)}%</span>`}</div>
      <div class="rs-take">${n === 0 ? 'It took no trades in this range. Check the session window and the entry rules, then run it again.' : takeaway(eqPoints(r.bundle.equity || {}), netv, n)}<span>${esc(used)}</span></div>
      <div class="eqw" id="eqw"><svg preserveAspectRatio="none" role="img" aria-label="Equity curve, after fees"></svg><div class="eq-rule" id="eqRule"></div><span class="eq-dot" id="eqDot"></span>
        <span class="eq-tag" id="eqHi"></span><span class="eq-tag" id="eqLo"></span><div class="eq-tip" id="eqTip"></div><div class="eq-ax" id="eqAx"></div></div>
      <div class="rs-trio"><div><b>${split(by('Profit factor').value)}</b><span>Profit factor</span></div><div><b>${split(by('Win rate').value)}</b><span>Win rate</span></div><div><b>${split(by('Sharpe').value)}</b><span>Sharpe</span></div></div>
      ${badges.length ? `<div class="rs-chips">${badges.map((x) => `<span class="rs-chip ${x.tone === 'err' ? 'err' : x.tone === 'warn' ? 'warn' : ''}" title="${esc(x.title || '')}">${esc(x.text)}</span>`).join('')}</div>` : ''}
      <div class="rs-gh">Per trade</div>
      <div class="rs-group"><div class="rs-kv"><span>Average trade</span><b>${esc(by('Avg trade').value)}</b></div><div class="rs-kv"><span>Average win : loss</span><b>${esc(by('Avg win : loss').value.replace(/^RR /, '').replace(':', ' : '))}</b></div><div class="rs-kv"><span>Max drawdown</span><b>${esc(by('Max drawdown').value)}</b></div></div>
      <div class="rs-gh">Run settings</div>${settings}
      <div class="rs-group">${P.chart ? '' : '<button class="rs-row" data-act="show"><span>Show trades on the chart</span><span>›</span></button>'}
        <button class="rs-row" data-act="report"><span>${root.dataset.report === '1' && P.chart ? 'Hide the full report' : 'Full report'}</span><span>›</span></button>
        <button class="rs-row" data-act="review"${b.kind === 'builtin' ? ' disabled' : ''}><span>Request a review</span><span>›</span></button></div>`;
    settingsDone = true;
  } else if (r && r.st && (r.st.status === 'error' || r.st.status === 'cancelled')) {
    main = `<div class="rs-empty"><h3>${r.st.status === 'cancelled' ? 'Cancelled' : 'The run failed'}</h3><p>${esc(r.st.error || (r.st.status === 'cancelled' ? 'Run it again when you are ready.' : 'See the line under the editor.'))}</p></div>`;
  } else {
    main = `<div class="rs-empty"><h3>No backtest yet</h3><p>Run it to see the P&amp;L, the equity curve and every trade. <kbd>⌘↵</kbd> runs it from the editor.</p></div>`;
  }
  el.innerHTML = settingsDone ? main : `${main}${settings ? `<div class="rs-gh">Run settings</div>${settings}` : ''}`;
  el.scrollTop = top;
  drawEq();
}

/* ---- events ----
   The chart shell sits inside the workspace now: nothing that happens in it is the Lab's to handle. */
const inChart = (e) => !!(e.target && e.target.closest && e.target.closest('#labChart'));
function act(name, el) {
  const b = buf();
  if (name === 'new') newMenu(el);
  else if (name === 'more') moreMenu(el);
  else if (name === 'paste') pasteScript();
  else if (name === 'run') run();
  else if (name === 'cancel') cancelRun();
  else if (name === 'show') showOnChart(false);
  else if (name === 'report') { if (root.dataset.report === '1' && P.chart) setReport(false); else showOnChart(true); }
  else if (name === 'review') reviewDialog();
  else if (name === 'save') save(b);
  else if (name === 'fold') foldGroup(el);
  else if (name === 'file') fileMenu(el);
  else if (name === 'group') groupMenu(el);
  else if (name === 'view') setView(el.dataset.v);
  else if (name === 'plctl') { const c = S.pl && S.pl.data ? C.plControl(S.pl.data) : null; if (c && c.enabled) pipeActions(c.actions); }
  else if (name === 'plidea') pickIdea(el.dataset.name);
  else if (name === 'plbook') pickCard(el.dataset.name);
  else if (name === 'plstep') guideStep(Number(el.dataset.n));
  else if (name === 'plapprove') approveIdea();
  else if (name === 'plrefuse') refuseSheet(S.plIdea);
  else if (name === 'pladd') addSheet();
  else if (name === 'plhide') { S.plSaid = null; paintLib(); }
  else if (name === 'tkblock') codeSheet(el.dataset.id);
  else if (name === 'bptool') toolSheet(el.dataset.tool);
  else if (name === 'bpidea') { S.bpIdea = el.dataset.name; paintLib(); toolSheet('blueprint_status', { name: el.dataset.name }, true); }
}
root.addEventListener('click', (e) => {
  if (inChart(e)) return;
  const lib = e.target.closest('[data-key]');
  if (lib) { const k = lib.dataset.key; if (k.startsWith('d:')) selectDraft(k.slice(2)); else if (k.startsWith('b:')) selectBuiltin(k.slice(2)); else { S.cur = k; S.run = null; paintAll(); } return; }
  const a = e.target.closest('[data-act]');
  if (a) act(a.dataset.act, a);
});
const bar = document.querySelector('.lab-bar');
if (bar) {
  bar.addEventListener('click', (e) => { const a = e.target.closest('[data-act]'); if (a) act(a.dataset.act, a); });
  bar.addEventListener('input', (e) => { const b = buf(); if (e.target.id === 'edName' && b) { b.name = e.target.value.trim(); e.target.classList.remove('bad'); paintLib(); } });
  bar.addEventListener('keydown', (e) => { if (e.target.id === 'edName' && e.key === 'Enter' && !e.repeat) { e.preventDefault(); save(buf()); } });
}
root.addEventListener('toggle', (e) => { if (e.target.classList && e.target.classList.contains('rs-set')) S.setOpen = e.target.open; }, true);
root.addEventListener('input', (e) => {
  if (inChart(e)) return;
  const b = buf(), t = e.target;
  if (t.id === 'tkQ') { S.tkQ = t.value; const l = $('#tkList'); if (l) l.innerHTML = toolkitList(); return; }
  if (t.id === 'edTa' && b && b.kind !== 'builtin') {
    const wasEmpty = !b.code.trim();
    b.code = t.value; b.valid = b.valid && b.valid.ok ? { ...b.valid, stale: true } : null;
    if (b.kind === 'new' && wasEmpty && b.code.trim() && !b.name) { b.name = C.suggestName(b.code, takenNames()); const n = document.getElementById('edName'); if (n) n.value = b.name; }
    paintCode(); paintHead(); queueValidate(b); paintLib();
  } else if (t.dataset.f || t.dataset.in) {
    const f = formOf(b), meta = metaOf(b);
    if (!f) return;
    if (t.dataset.in) {
      const inp = (meta.inputs || []).find((i) => i.key === t.dataset.in);
      f.inputs[inp.key] = inp.type === 'bool' ? t.checked : inp.type === 'choice' ? t.value : t.value === '' ? NaN : Number(t.value);
      t.classList.toggle('bad', !!X.inputError(inp, f.inputs[inp.key]));
    } else if (t.dataset.f === 'range') { f.range = { id: t.value, start: f.range.start, end: f.range.end, wf: null }; paintRes(); }
    else if (t.dataset.f === 'start' || t.dataset.f === 'end') f.range[t.dataset.f] = t.value.trim();
    else f[t.dataset.f] = t.value === '' ? NaN : Number(t.value);
  }
});
root.addEventListener('scroll', (e) => { if (e.target.id === 'edTa') syncScroll(); }, true);
root.addEventListener('keydown', (e) => {
  if (inChart(e) || pipeOn()) return;        // (a pipeline view has the middle: the editor's keys save and run nothing from behind it)
  const b = buf(), t = e.target, mod = e.metaKey || e.ctrlKey;
  if (mod && e.key === 's') { e.preventDefault(); if (b && b.kind !== 'builtin') save(b); return; }
  if (mod && e.key === 'Enter') { e.preventDefault(); if (!e.repeat) run(); return; }   // a held ⌘↵ starts one run, not many
  if (t.id !== 'edTa' || !b || b.kind === 'builtin') return;
  let r = null;
  if (e.key === 'Tab') r = C.tab(t.value, t.selectionStart, t.selectionEnd, e.shiftKey);
  else if (e.key === 'Enter' && !mod && !e.shiftKey) r = C.enter(t.value, t.selectionStart, t.selectionEnd);
  // ^ a plain Enter only types a newline (key repeat is wanted while it is held): it sends nothing
  else if (mod && e.key === '/') r = C.comment(t.value, t.selectionStart, t.selectionEnd);
  if (!r) return;
  e.preventDefault();
  t.value = r.value; t.setSelectionRange(r.start, r.end);
  t.dispatchEvent(new Event('input', { bubbles: true }));
});
root.addEventListener('dragover', (e) => { if (!inChart(e) && [...(e.dataTransfer?.types || [])].includes('Files')) { e.preventDefault(); $('#edWrap')?.classList.add('ed-drop'); } });
root.addEventListener('dragleave', (e) => { if (!root.contains(e.relatedTarget)) $('#edWrap')?.classList.remove('ed-drop'); });
root.addEventListener('drop', (e) => { if (inChart(e)) return; const f = e.dataTransfer?.files?.[0]; $('#edWrap')?.classList.remove('ed-drop'); if (f) { e.preventDefault(); readFile(f); } });
$('#labFile').addEventListener('change', (e) => { readFile(e.target.files[0]); e.target.value = ''; });
window.addEventListener('beforeunload', (e) => { if ([...S.bufs.values()].some(isDirty)) { e.preventDefault(); e.returnValue = ''; } });
for (const x of document.querySelectorAll('#labPanels [data-panel]')) x.addEventListener('click', () => setPanel(x.dataset.panel));
setInterval(() => { const b = buf(); if (b && b.savedAt && !isDirty(b)) paintHead(); }, 30000);

/* ---- go ---- */
root.dataset.report = '0';
document.addEventListener('visibilitychange', plSync);
applyPanels(false);
paintAll();
paintNav();
setTimeout(() => { if (P.chart) soloChart(); }, 1800);
// Bar Replay lives in the same bottom panel: asking for it brings the panel back
document.getElementById('tbReplay')?.addEventListener('click', () => setReport(true));
loadLists().then(() => {
  const m = /^#(strategy|builtin)=(.+)$/.exec(location.hash);
  if (!m) return;
  const name = decodeURIComponent(m[2]);
  if (m[1] === 'strategy' && S.drafts.some((d) => d.name === name)) selectDraft(name);
  else if (m[1] === 'builtin' && S.builtins.some((x) => x.id === name)) selectBuiltin(name);
});
window.HBLab = { openScript, setPanel, panels: P, state: S };
})();
