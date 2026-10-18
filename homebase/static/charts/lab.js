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
  view: 'lib', libQ: '', tk: null, tkQ: '', pl: null, plSaid: null, plBusy: false, plFilter: 'all', plForm: null, plFk: '', plIdea: '', plCard: '', plWant: '', plDetail: null, plArmed: '', plCurve: null, plExec: '', desk: null, deskBuiltins: new Set(), deskBusy: false,
  picks: [], anchor: '', listFocus: false, delBusy: false, unlocked: new Set(), heat: {}, wf: {} };
/* picks: the list's rows picked for a delete (keys, shown order); anchor: where a shift-click's range starts; listFocus: the
   list was the last thing touched (a button takes no focus on a click in Safari, so the keyboard is judged by this) */
/* view: what the sidebar lists -- 'lib' (strategies), 'tk' (the arsenal: every tool, with its code), and the strategy pipeline's three:
   'pq' (its Queue), 'pb' (its Book). A stored view that is no longer one of these opens Strategies. */
const VIEWS = [['lib', 'Strategies'], ['tk', 'Arsenal']], PIPE_TABS = [['pq', 'Queue'], ['pb', 'Book']];
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
  if (S.view === 'tk') loadToolkit();
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
  S.run = S.run && S.run.key === key ? S.run : (S.active && !S.active.dead && S.active.key === key ? S.active : null);   // coming back to a strategy that is still running shows its progress
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
  if (!b || b.kind === 'builtin' || locked(b)) return false;
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
  return m ? { id: b.id || `draft_${b.name}`, inputs: m.inputs || [], bar_minutes: m.bar_minutes || 0, bar_sizes: m.bar_sizes || [] } : null;
}
function formOf(b) {
  const meta = metaOf(b);
  if (!meta) return null;
  const id = b.kind === 'builtin' ? b.id : `draft_${b.name}`;
  const fresh = !S.forms[id];
  const f = X.restore(S.forms[id] ? { ...S.forms[id], strategy: id } : null, { ...meta, id });
  if (fresh) f.range = { id: 'all', start: '', end: '', wf: X.WF_ROLL, side: 'is' };   // the Lab's default: 3:1 in-sample (owner, 2026-10-18)
  f.strategy = id;
  S.forms[id] = f;
  return f;
}
/* One backtest runs at a time. Clicking Run shows "Running" at once (the checks and the save come first and can take a
   moment); starting another strategy's run stops the one in flight instead of doing nothing. */
function release(run) {
  run.dead = true;
  if (S.active === run) { S.active = null; S.busy = false; }
  if (S.run === run) S.run = null;
}
async function run() {
  const b = buf();
  if (!b) return;
  const wf0 = b.kind !== 'pipe' && formOf(b);
  if (wf0 && wf0.range.wf) return wfRun();                          // Run settings › Walk-forward is on
  S.deskErr = '';
  if (S.busy && S.active && !S.active.dead) {
    if (S.active.key === b.key) return;                              // this one is already running
    const prev = S.active; prev.dead = true;
    if (prev.rid) send('POST', `/api/tester/run/${encodeURIComponent(prev.rid)}/cancel`);
    log(`Stopped the run of <b>${esc(prev.name || 'the other strategy')}</b> to run this one.`);
  }
  if (b.kind !== 'builtin' && !b.code.trim()) return;
  const me = { key: b.key, rid: null, st: { status: 'queued' }, bundle: null, strategy: '', name: b.kind === 'builtin' ? b.id : b.name, dead: false };
  S.busy = true; S.active = me; S.run = me;
  paintRes(); paintHead();
  if (b.kind !== 'builtin') {
    const v = await validateNow(b);
    if (me.dead) return;
    if (!v || !v.ok) { release(me); log(`<span class="err">Fix the script first: ${esc(C.statusOf(v).text)}</span>`); paintRes(); paintHead(); return; }
    if (isDirty(b) || b.kind === 'new') { if (!(await save(b))) { release(me); paintRes(); paintHead(); return; } }
    if (me.dead) return;
  }
  const nb = buf(), f = nb ? formOf(nb) : null;
  if (!f || !nb) { release(me); paintRes(); paintHead(); return; }
  me.key = nb.key; me.strategy = f.strategy; me.name = nb.kind === 'builtin' ? nb.id : nb.name;
  if (S.cur !== nb.key) S.cur = nb.key;
  const pr = X.problems(f, { ...metaOf(nb), id: f.strategy });
  if (pr) { release(me); log(`<span class="err">${esc(pr)}</span>`); paintRes(); paintHead(); return; }
  if (nb.kind !== 'builtin' && /BLUEPRINT RECORD/.test(nb.code)) { release(me); if (!P.res) setPanel('res', true); const shown = await openRecordRun(nb, f); paintRes(); paintHead(); if (shown) return; S.busy = true; S.active = me; me.dead = false; S.run = me; }
  paintRes(); paintHead();
  const r = await send('POST', '/api/tester/run', X.body(f));
  if (me.dead) return;
  if (!r.ok) { release(me); log(`<span class="err">${esc(r.error)}</span>`); paintRes(); paintHead(); return; }
  me.rid = r.json.id;
  log(`Running <b>${esc(me.name)}</b> over ${esc(X.pillLabel ? X.pillLabel(f.range) : f.range.id)} inside the sandbox…`);
  poll(me);
}
/* A "Blueprint record" file is the written card of an idea the research engine already ran: the script itself places no
   trades, so running it here would only ever say 0 trades. Show the idea's own latest run with trades instead. */
async function openRecordRun(nb, f) {
  const l = await send('GET', `/api/tester/runs?limit=50&strategy=${encodeURIComponent(f.strategy)}`);     // asks for this idea's runs only: it can be older than the newest 50
  const list = l.ok && l.json ? (Array.isArray(l.json) ? l.json : l.json.runs || []) : [];
  const mine = list.filter((x) => x && x.strategy === f.strategy && x.status === 'done' && (x.trades || 0) > 0);
  const hit = mine[0];
  if (!hit) { log(`<b>${esc(nb.name || f.strategy)}</b> is a written record: the script places no trades itself, and no research-engine run with trades is saved for it yet.`); return true; }
  const bd = await send('GET', `/api/tester/run/${encodeURIComponent(hit.id)}/bundle`);
  if (!bd.ok || !bd.json) return false;
  S.busy = false;
  S.run = { key: nb.key, rid: hit.id, st: { status: 'done' }, bundle: bd.json, strategy: f.strategy, record: true };
  const rg = (hit.range && (hit.range.label || hit.range.id)) || '';
  log(`<b>${esc(nb.name || f.strategy)}</b> is a written record: its script places no trades, so this is its saved research-engine run${rg ? ` (${esc(rg)})` : ''} · <b>${esc(String(hit.trades))} trades</b> · <a data-act="show">Show trades on the chart ›</a>`);
  paintRes(); paintHead(); syncChart();
  return true;
}
async function poll(run) {
  const viewing = () => S.run === run;                               // the user may have gone to another strategy meanwhile: the run still finishes
  const settle = () => {
    if (S.active === run) { S.active = null; S.busy = false; }
    if (!viewing() && !S.run && S.cur === run.key) S.run = run;     // back on its strategy with nothing else open: show it
  };
  while (!run.dead) {
    const r = await send('GET', `/api/tester/run/${encodeURIComponent(run.rid)}`);
    if (run.dead) return;
    if (r.ok) { run.st = r.json; if (viewing()) paintRes(); }
    const s = r.ok ? r.json.status : 'error';
    if (s === 'done') {
      const bd = await send('GET', `/api/tester/run/${encodeURIComponent(run.rid)}/bundle`);
      if (run.dead) return;
      run.bundle = bd.ok ? bd.json : null;
      settle(); run.dead = true;
      const who = viewing() ? '' : ` <b>${esc(run.name || '')}</b>`;
      if (run.bundle) {
        const a = run.bundle.run.report.summary.all;
        log(`Ran${who} in the sandbox · <b>${esc(String(a.trades ?? 0))} trades</b>${viewing() ? ' · <a data-act="show">Show trades on the chart ›</a>' : ' · open the strategy to see it'}`);
        const held = run.bundle.run.controls && run.bundle.run.controls.blocked;
        if (held && Object.keys(held).length) log(`Trade rules held back ${esc(Object.entries(held).map(([k, n]) => `${n} × ${k}`).join(', '))}`);
      } else log('<span class="err">The run finished but its report could not be loaded</span>');
      paintRes(); paintHead(); if (viewing()) syncChart();
      return;
    }
    if (s === 'error' || s === 'cancelled') {
      settle(); run.dead = true;
      const msg = s === 'cancelled' ? 'Cancelled' : `Failed: ${esc((r.json && r.json.error) || r.error || 'unknown error')}`;
      log(`<span class="${s === 'error' ? 'err' : ''}">${msg}</span>`);
      run.st = { ...(run.st || {}), status: s }; paintRes(); paintHead();
      return;
    }
    await new Promise((res) => setTimeout(res, 550));
  }
}
async function cancelRun() {
  const a = S.active;
  if (!a || a.dead) return;
  if (!a.rid) { release(a); log('Cancelled'); paintRes(); paintHead(); return; }     // still checking or saving: nothing is out yet
  await send('POST', `/api/tester/run/${encodeURIComponent(a.rid)}/cancel`);
}

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
  root.dataset.view = S.view;        // lab.css: with nothing open, the Arsenal shows its own line where the welcome and the empty result would be
  root.style.setProperty('--lab-code', String(split));
  root.style.setProperty('--lab-chart', String(100 - split));
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
  const o = await send('POST', '/api/tester/show', r.grid ? { grid_id: r.grid.id, cell: r.grid.cell } : { run_id: r.rid });
  if (o.ok && o.json.pages && n) frameWhenLoaded(r.rid, r.grid ? r.bundle.run.id : r.rid);
  if (!o.ok) { shownRid = null; log(`<span class="err">Could not show it on the chart: ${esc(o.error)}</span>`); }
  else if (!o.json.pages) {       // this page's own socket is not up yet (just loaded): try again shortly, a few times
    shownRid = null;
    if ((showTries = (showTries || 0) + 1) <= 5) setTimeout(syncChart, 1200); else log('The chart is not connected yet: toggle Chart off and on to try again');
  } else showTries = 0;
  paintNav();
}
/* A run that is NOT the open strategy's (a pipeline idea's executions, a run the Desk page asked for): the chart comes
   forward with the Strategy Tester's report under it, and the tester is asked to show the run, at `focus` when given
   ({date}). The pipeline's pages step aside first: the chart is behind them. -> true once this page's chart took it. */
const RUN_ID = /^[0-9]{8}-[0-9]{6}-[a-z][a-z0-9_]*-[0-9a-f]{4}$/;
async function showRunOnChart(rid, focus = null) {
  if (!RUN_ID.test(String(rid))) return false;
  if (pipeOn()) setView('lib');
  if (!P.chart) {
    P.chart = true;
    if (innerWidth < 1500 && !panelsChosen) P.lib = false;
    applyPanels();
    await new Promise((res) => setTimeout(res, 160));
  }
  const bd = await send('GET', `/api/tester/run/${encodeURIComponent(rid)}/bundle`);     // the run becomes the open result: the chart's own panel (trade list, stepper, report), not a bare chart
  if (bd.ok && bd.json) {
    const trades = (bd.json.trades || []).length;
    S.run = { key: `pl:${rid}`, pipe: true, rid, st: { status: 'done' }, bundle: bd.json, strategy: (bd.json.run && bd.json.run.strategy && (bd.json.run.strategy.id || bd.json.run.strategy)) || '', cellLabel: (bd.json.run && bd.json.run.strategy && bd.json.run.strategy.name) || '' };   // a pipeline run has no open script: its own key
    ti = trades ? trades - 1 : null;
    paintRes();
  }
  setReport(false);                 // the chart with its stepper, big; the Strategy Tester report is one toggle away
  soloChart();
  shownRid = rid;
  paintNav();
  for (let k = 0; k < 6; k++) {          // this page's own socket may not be up yet (the page just loaded)
    const o = await send('POST', '/api/tester/show', focus ? { run_id: rid, focus } : { run_id: rid });
    if (!o.ok) { shownRid = null; log(`<span class="err">Could not show it on the chart: ${esc(o.error)}</span>`); return false; }
    if (o.json.pages) return true;
    await new Promise((res) => setTimeout(res, 1200));
  }
  shownRid = null;
  return false;
}
/* Coming back to the app, the chart service socket has often dropped and every chart is subscribed again: the chart then holds
   only the newest bars, so the run's executions are out of view (they are still loaded). The page checks, and when the run
   is open but none of its trades is in the bars, it asks the tester for the run again if it was lost, then jumps back to the trade
   the stepper is on. Same run, same position; nothing new is run or read. */
let reshowAt = 0;
async function reshow() {
  if (!shownRid || !RUN_ID.test(String(shownRid)) || Date.now() - reshowAt < 1500) return;
  reshowAt = Date.now();
  const rid = shownRid, U = window.HBTesterUI, L = window.HBTesterLayer, cell = window.HBCharts && window.HBCharts.cells && window.HBCharts.cells[0];
  if (!U || !L || !cell) return;
  if (!U.bundle || !U.bundle.run || U.bundle.run.id !== rid) {          // the tester let go of it: ask for it again
    for (let k = 0; k < 6 && shownRid === rid; k++) {
      const o = await send('POST', '/api/tester/show', { run_id: rid });
      if (o.ok && o.json.pages) break;
      await new Promise((res) => setTimeout(res, 1200));
    }
  }
  for (let k = 0; k < 8 && shownRid === rid; k++) {                       // the bars are on their way back
    await new Promise((res) => setTimeout(res, 700));
    const tr = navTrades();
    if (!tr.length || !cell.bars || !cell.bars.length || !U.bundle) continue;
    if (L.tradesInRange(U.bundle.trades, cell.bars, cell.barMs()).length) return;     // they are in view: nothing to do
    const i = ti != null ? Math.min(ti, tr.length - 1) : tr.length - 1;
    await jumpTo(i);
    return;
  }
}
window.addEventListener('hb:chart-reconnect', () => setTimeout(reshow, 500));
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') setTimeout(reshow, 900); });

/* ONE chart: the Lab never shows a grid of them. (The grid menu is the chart shell's own; its button is hidden here.) */
function soloChart() {
  const H = window.HBCharts;
  if (!H || !H.cells || !H.cells.length) return;
  if (H.layout && H.layout.grid !== 1) { H.layout.grid = 1; H.buildGrid(); }
  bareChart();
}
/* ...and it shows the STRATEGY: price, its executions, the levels and plots the script itself draws. The chart's
   own saved indicators (volume, VWAP, session levels, footprint, ...) are not part of the strategy, so they go --
   ONCE, when the page opens. The Indicators button (the Lab shows it since 2026-10-11) then adds and removes them
   for as long as the page is open: what a person added is never taken away by a later solo / sync. */
let barred = false;
function bareChart() {
  if (barred) return;
  const c = window.HBCharts && window.HBCharts.cells && window.HBCharts.cells[0];
  if (!c || !c.cfg) return;
  barred = true;
  if (Array.isArray(c.cfg.indicators) && c.cfg.indicators.length) c.update({ indicators: [] });
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
async function frameWhenLoaded(rid, runId = rid) {
  const pause = (ms) => new Promise((res) => setTimeout(res, ms));
  for (let k = 0; k < 60; k++) {
    const b = window.HBTesterUI && window.HBTesterUI.bundle;
    if (shownRid !== rid) return;                       // a newer run took the chart
    if (b && b.run && b.run.id === runId) break;
    await pause(200);
  }
  // the tester is still settling the run it was just handed: a jump can lose that race, so make sure it took
  for (let k = 0; k < 4 && shownRid === rid && ti != null; k++) {
    await pause(k ? 1500 : 300);
    if (window.HBTesterUI && window.HBTesterUI.selected === ti) return;
    jumpTo(ti);
  }
}
// the Lab's chart keeps the interval the viewer picked: a trade too old for its scroll-back loads as a window, never as a coarser interval
if (window.HBTesterLayer && window.HBTesterLayer.setWindowJumps) window.HBTesterLayer.setWindowJumps(true);
const jumpTo = (i) => { const t = navTrades()[i]; return t && window.HBTesterLayer && window.HBTesterLayer.jump(i, null, { contextMs: dayContext(t) }); };
const NAV_DAY = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric', year: 'numeric' });
const NAV_DATE = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false });
/* The trades of the run on the chart: the open strategy's own, or -- a run shown from the Book, the Queue or a link -- the
   tester's copy of it once it has arrived. */
function navTrades() {
  if (S.run && S.run.bundle && shownRid === S.run.rid) return S.run.bundle.trades || [];
  const b = window.HBTesterUI && window.HBTesterUI.bundle;
  return shownRid && b && b.run && b.run.id === shownRid ? b.trades || [] : [];
}
/* The stepper on the chart: previous, "3 of 42" and the trade in a few words, next. It shows only while a finished run with
   trades is on the chart (paintRes calls this, so it goes with the run). The words after the count are their own span: where the
   chart is narrow the page shows the count alone. */
let navEditing = null;        // the element a typed trade number is being asked in (paintNav leaves it alone)
function paintNav() {
  const nav = document.getElementById('labNav'), el = document.getElementById('labNavText');
  if (!nav || !el) return;
  const ts = navTrades(), n = ts.length, t = ti != null ? ts[ti] : null;
  nav.hidden = !n;
  if (!n) return;
  const [prev, next] = nav.querySelectorAll('[data-nav]');
  if (prev) prev.disabled = ti == null || ti <= 0;
  if (next) next.disabled = ti != null && ti >= n - 1;
  let html = `<span><b>${n}</b> trade${n === 1 ? '' : 's'}</span>`;
  if (t) {
    const net = Number(t.net) || 0, amt = `${net > 0 ? '+' : net < 0 ? MINUS : ''}$${Math.abs(Math.round(net)).toLocaleString('en-US')}`;
    html = `<span><b>${ti + 1}</b> of ${n}</span><span class="lab-nav-d"> · ${t.side === 'long' ? 'Long' : 'Short'} <span class="${net > 0 ? 'pos' : 'neg'}">${amt}</span> · ${esc(NAV_DAY.format(new Date(t.entry_ms)))}</span>`;
    const at = NAV_DATE.format(new Date(t.entry_ms));
    el.title = `Trade ${ti + 1} of ${n} · ${window.HBClock ? window.HBClock.within(at) : at} ET`;      // the app's one clock format
  }
  if (navEditing === el) return;                         // the number is being typed: the box is not rewritten under it
  if (el.innerHTML !== html) el.innerHTML = html;        // (the text is a live region: the same words are not written twice)
}
function stepTrade(d) {
  const n = navTrades().length;
  if (!n || !window.HBTesterLayer) return;
  ti = Math.max(0, Math.min(n - 1, (ti == null ? (d > 0 ? -1 : n) : ti) + d));
  paintNav();
  jumpTo(ti);
}
/* Click the count and type the trade's number instead of stepping: Enter goes there (a number past either end goes to the
   nearest trade), Escape or a click away leaves things as they were. `host` is the element that shows the count; `done` runs
   when the box is closed. The chart's own capsule (labstep.js) asks in its text through window.HBLabNav. */
function askTrade(host, done) {
  const n = navTrades().length;
  if (!n || !host || navEditing === host || navEditing) return;
  const inp = document.createElement('input');
  inp.type = 'text'; inp.inputMode = 'numeric'; inp.autocomplete = 'off'; inp.spellcheck = false;
  inp.className = 'lab-nav-in'; inp.value = ti != null ? String(ti + 1) : ''; inp.placeholder = `1–${n}`;
  inp.setAttribute('aria-label', `Go to trade, 1 to ${n}`);
  navEditing = host;
  host.textContent = '';
  host.appendChild(inp);
  inp.focus(); inp.select();
  let closed = false;
  const outside = (e) => { if (e.target !== inp) close(false); };      // a click anywhere else closes it, focused or not
  document.addEventListener('pointerdown', outside, true);
  const close = (go) => {
    if (closed) return;
    closed = true;
    document.removeEventListener('pointerdown', outside, true);
    const v = parseInt(String(inp.value).replace(/[^\d]/g, ''), 10);
    navEditing = null;
    host.textContent = '';
    if (go && Number.isFinite(v) && v > 0) { ti = Math.min(n, v) - 1; paintNav(); jumpTo(ti); } else paintNav();
    if (done) done();
  };
  inp.addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'Enter') { e.preventDefault(); if (!e.repeat) close(true); }
    else if (e.key === 'Escape') { e.preventDefault(); close(false); }
  });
  inp.addEventListener('blur', () => close(false));
}
window.HBLabNav = { ask: askTrade };
document.getElementById('labNav')?.addEventListener('click', (e) => {
  const b = e.target.closest('[data-nav]');
  if (b) { stepTrade(Number(b.dataset.nav)); return; }
  if (e.target.closest('#labNavText') && !e.target.closest('input')) askTrade(document.getElementById('labNavText'));
});
// a trade picked in the full report's list moves the stepper too; and a run the tester has just been handed brings it up
if (window.HBTesterUI && window.HBTesterUI.on) window.HBTesterUI.on(() => {
  const i = window.HBTesterUI.selected;
  if (i != null && i !== ti && i < navTrades().length) ti = i;
  if (ti != null && ti >= navTrades().length) ti = null;      // another run's count
  paintNav();
});
// a run Claude put on the chart (the tester was handed it over the socket, not through showOnChart): the stepper walks it too
window.addEventListener('hb:tester-show', (e) => {
  const rid = e.detail && e.detail.run_id, ui = window.HBTesterUI;
  if (!rid || !ui) return;
  shownRid = rid;
  const i = ui.selected;
  ti = i != null && i < navTrades().length ? i : null;      // opened on a trade: that one; otherwise the first Next goes to trade 1
  paintNav();
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
function closeMenu() {
  if (menuEl) { menuEl.remove(); menuEl = null; }
  for (const t of document.querySelectorAll('[data-act="viewmenu"][aria-expanded="true"]')) t.setAttribute('aria-expanded', 'false');
}
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
document.addEventListener('pointerdown', (e) => { if (menuEl && !menuEl.contains(e.target) && !e.target.closest('[data-act="new"], [data-act="more"], [data-act="viewmenu"]')) closeMenu(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeMenu(); closeDialog(); } });

async function newMenu(anchor) {
  const r = await send('GET', '/api/tester/drafts/templates');
  const ts = (r.ok && r.json) || [];
  menu(anchor, `<button data-pick="form"><b>Fill in a form</b><small>Pick a market, an entry rule, a stop and a target. No code.</small></button><hr>
    <button data-pick="paste"><b>Paste a script</b><small>Insert Python from your clipboard or an editor</small></button>
    <button data-pick="file"><b>Open a .py file…</b><small>Load a script from disk</small></button><hr>
    <h6>Start from a template</h6>${ts.map((t) => `<button data-pick="t:${esc(t.id)}"><b>${esc(t.title)}</b><small>${esc(t.blurb)}</small></button>`).join('')}
    ${S.groups ? '<hr><button data-pick="group"><b>New group…</b><small>A section of this list to keep strategies under</small></button>' : ''}`,
  async (pick) => {
    if (pick === 'form') return formOpen(anchor);
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
  const draft = b.kind !== 'builtin', saved = b.kind === 'draft', code = b.code || '', lockedNow = locked(b);
  const formRow = '<button class="row" data-pick="form"><span>Edit in the form…</span></button>';
  const known = draft && !lockedNow && fmRead.code === code && !!fmRead.got;          // the form's read of this code, when it is already in
  menu(anchor, `${draft ? `<button class="row" data-pick="save"${!lockedNow && (isDirty(b) || b.kind === 'new') ? '' : ' disabled'}><span>Save</span><kbd>⌘S</kbd></button>${known ? formRow : ''}
      <button class="row" data-pick="review"${saved ? '' : ' disabled'}><span>Request a review…</span></button><hr>` : ''}
    <button class="row" data-pick="ref"><span>Scripting reference</span></button>
    ${saved ? '<hr><button class="row" data-pick="delete"><span>Delete…</span></button>' : ''}`,
  (pick) => {
    if (pick === 'save') save(b);
    else if (pick === 'form') formEdit(anchor, b);
    else if (pick === 'review') reviewDialog();
    else if (pick === 'ref') referenceDialog();
    else if (pick === 'delete') deleteDialog(b.name);
  });
  if (draft && !known && code) {            // asked once for this code; the row appears when the answer says the form made it
    const mine = menuEl;
    formRead(code).then((got) => { if (got && menuEl === mine && mine.isConnected && !mine.querySelector('[data-pick="form"]') && buf() === b && b.code === code) mine.querySelector('[data-pick="save"]').insertAdjacentHTML('afterend', formRow); });
  }
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

/* ---- the strategy form: "Fill in a form" in the + menu, "Edit in the form…" in the ⋯ menu (2026-10-09) ----
   The owner fills in a short form and gets a normal strategy file. The form is the server's (GET /api/tester/drafts/form: the
   entry rules, their fields, words, choices, limits, defaults): this page names no rule. What he has chosen is read back in one
   sentence that the server writes (the build route's `sentence`), asked for 400 ms after the last change and never while an earlier
   answer is still out. The server is the authority on every answer; the page only spares a request for a number that is plainly not
   one. Nothing in the sheet is rebuilt while a box has focus: the helper words, the errors and the sentence are patched in place, and
   only the part below the entry rule is drawn again (when the rule changes, with the keyboard on the rule's own box above it).
   Nothing is saved until he saves or runs, as with a template. */
const FM_NAME_WORDS = 'Small letters, numbers and _ , a letter first. For example: nq_orb';
const fmRead = { code: null, p: null, got: undefined };       // the form's read of the open code: asked once per code, kept
function formRead(code) {
  if (fmRead.code === code && fmRead.p) return fmRead.p;
  fmRead.code = code; fmRead.got = undefined;
  const p = send('POST', '/api/tester/drafts/form/read', { code }).then((r) => {
    const got = r.ok && r.json && r.json.answers && typeof r.json.answers === 'object' ? { answers: r.json.answers, intact: r.json.intact === true } : null;
    if (fmRead.p === p) { if (r.ok) fmRead.got = got; else fmRead.code = null; }         // a failed ask is asked again next time
    return got;
  });
  fmRead.p = p;
  return p;
}
function replaceCode(b, code) {       // as if he had typed it: the draft is changed and unsaved, and is checked again
  b.code = code; b.valid = null;
  if (S.cur === b.key) { paintEditor(); paintLib(); }
  queueValidate(b, 0);
}
/* a key still held when the sheet closes must not type into the editor that gets the keyboard next */
function swallowRepeats() {
  const eat = (e) => { if (e.repeat) { e.preventDefault(); e.stopPropagation(); } };
  const off = () => { document.removeEventListener('keydown', eat, true); document.removeEventListener('keyup', off, true); };
  document.addEventListener('keydown', eat, true);
  document.addEventListener('keyup', off, true);
}
const FM_FAILED = 'The form could not be checked. Try again.';
const FM_STALE = 'The code changed while the form was open. Open the form again.';
/* a POST that never stays out for ever: after 10 s it is cut off and counts as no answer */
function timed(path, body, ms = 10000) {
  const ctl = new AbortController();
  let t = 0;
  const late = new Promise((res) => { t = setTimeout(() => { ctl.abort(); res({ ok: false, status: 0, json: null, error: 'No answer' }); }, ms); });
  return Promise.race([call(path, { method: 'POST', body: JSON.stringify(body), signal: ctl.signal }), late]).finally(() => clearTimeout(t));
}
/* the button that opened a sheet, found again by its own data-fk after a repaint */
const backTo = (anchor, kind) => {
  const fk = anchor && anchor.dataset && anchor.dataset.fk;
  return (fk && [...root.querySelectorAll('[data-fk]')].find((x) => x.dataset.fk === fk)) || root.querySelector(`[data-act="${kind}"]`);
};
/* edit: null for a new strategy, else { key, answers, code, wanted? } of the open draft. Resolves true when the sheet opened. */
async function formOpen(anchor, edit = null) {
  const r = await send('GET', '/api/tester/drafts/form');
  const sc = r.ok && r.json && Array.isArray(r.json.rules) && r.json.rules.length ? r.json : null;
  if (edit && edit.wanted && !edit.wanted()) return false;       // the question that led here was answered No while this loaded
  const F0 = sc && (edit ? C.fmFill(sc, edit.answers) : C.fmStart(sc, takenNames()));
  if (!F0) {
    log(`<span class="err">${esc(!sc ? (r.status === 404 ? 'The chart service is from before the form: restart it once to use it.' : `Could not load the form: ${r.error || 'it came back empty'}`) : 'The form does not know this strategy’s entry rule.')}</span>`);
    return false;
  }
  const back = anchor && anchor.isConnected ? anchor : backTo(anchor, edit ? 'more' : 'new');
  if (back && !overlay) back.focus({ preventScroll: true });       // the sheet hands the keyboard back to what opened it
  let F = F0, touched = !!edit, built = null, serverErr = {}, served = null, failed = false, stale = false, lastSay = '', flying = false, making = false, timer = 0, ver = 0;
  const id = C.fmId;       // a schema value that goes into markup (an id, a for, a data- attribute) is cut down to [a-z0-9_] first
  const taken = takenNames();
  const d = dialog(`<h2 id="labDlgTitle">${edit ? 'Edit strategy' : 'New strategy'}</h2>`);
  d.classList.add('pl-dlg');
  const ruleOf = () => sc.rules.find((x) => x.id === F.rule) || sc.rules[0];
  const words = (f) => (f === 'name' ? (edit ? 'A strategy keeps its name.' : FM_NAME_WORDS) : f === 'rule' ? ruleOf().words : C.fmWords(sc, F.rule, f));
  const opt = (v, t, cur) => `<option value="${esc(v)}"${String(v) === String(cur) ? ' selected' : ''}>${esc(t)}</option>`;
  const sel = (f, opts, cur, more = '') => `<select id="fm_${id(f)}" data-fm="${id(f)}"${more} aria-describedby="fh_${id(f)}">${opts.map(([v, t]) => opt(v, t, cur)).join('')}</select>`;
  const kindOf = (f) => C.fmKinds(sc, F.rule, f).find((k) => k.id === (F[f] || {}).kind);
  const control = (f) => {
    const desc = ` aria-describedby="fh_${id(f)}"`;
    if (f === 'name') return `<input id="fm_name" data-fm="name" value="${esc(F.name)}"${edit ? ' readonly' : ''} spellcheck="false" autocomplete="off" autocapitalize="off"${desc}>`;
    if (f === 'rule') return sel(f, sc.rules.map((x) => [x.id, x.label]), F.rule);
    const def = sc.fields[f];
    if (f === 'side') return sel(f, C.fmSides(sc, F.rule), F.side);
    if (def.type === 'choice') return sel(f, (def.choices || []).map((c) => [c, c]), F[f]);
    if (def.type === 'time') return `<input type="time" id="fm_${id(f)}" data-fm="${id(f)}" value="${esc(F[f])}" max="${C.FM_LATEST}" step="60"${desc}>`;
    if (def.type === 'stop' || def.type === 'target') {
      const k = kindOf(f);
      return `<div class="pl-two">${sel(f, C.fmKinds(sc, F.rule, f).map((x) => [x.id, x.label]), (F[f] || {}).kind, ' data-part="kind"')}
        <input id="fm_${id(f)}_v" class="fm-v" data-fm="${id(f)}" data-part="value" value="${esc((F[f] || {}).value == null ? '' : F[f].value)}" inputmode="decimal" aria-label="${esc(def.label)} amount" aria-describedby="fh_${id(f)}" spellcheck="false" autocomplete="off"${C.fmHasValue(k) ? '' : ' hidden'}></div>`;
    }
    return `<input id="fm_${id(f)}" data-fm="${id(f)}" value="${esc(F[f] == null ? '' : F[f])}" inputmode="${def.type === 'int' ? 'numeric' : 'decimal'}" spellcheck="false" autocomplete="off"${desc}>`;
  };
  const field = (f) => `<div class="bp-f pl-f"><label for="fm_${id(f)}">${esc(f === 'name' ? 'Name' : f === 'rule' ? 'Entry rule' : sc.fields[f].label)}</label>${control(f)}<small id="fh_${id(f)}">${esc(words(f))}</small></div>`;
  const restHtml = () => C.fmShown(sc, F.rule).slice(3).map(field).join('');
  d.innerHTML = `<h2 id="labDlgTitle">${edit ? 'Edit strategy' : 'New strategy'}</h2>
    <div class="pl-body" tabindex="-1"><div class="bp-form">${['name', 'market', 'rule'].map(field).join('')}<div class="bp-form" id="fmRest">${restHtml()}</div></div></div>
    <div class="pl-foot"><p class="fm-say" id="fmSay" role="status" aria-live="polite"></p>
      <button class="btn btn-ghost btn-sm fm-retry" data-x="retry" hidden>Try again</button>
      <div class="acts"><button class="btn btn-outline" data-x="cancel">Cancel</button><button class="btn btn-default" data-x="go" aria-describedby="fmSay" disabled>${edit ? 'Update' : 'Make it'}</button></div></div>`;
  const rest = $('#fmRest', d), say = $('#fmSay', d), go = $('[data-x="go"]', d), retry = $('[data-x="retry"]', d);
  const errors = () => ({ ...serverErr, ...C.fmErrors(sc, F) });          // what the page can see wins over an older answer
  const ready = () => !making && !stale && !failed && !flying && !timer && !!built && built.ver === ver && !Object.keys(C.fmErrors(sc, F)).length;
  /* everything that changes while a box has focus is changed where it stands */
  const paintState = () => {
    const e = errors(), order = C.fmShown(sc, F.rule);
    for (const f of order) {
      const h = $(`#fh_${id(f)}`, d);
      if (!h) continue;
      h.textContent = e[f] || words(f);
      h.classList.toggle('pl-bad', !!e[f]);
      for (const c of d.querySelectorAll(`[data-fm="${id(f)}"]`)) { c.classList.toggle('bad', !!e[f]); c.setAttribute('aria-invalid', String(!!e[f])); }
    }
    const first = stale ? FM_STALE : C.fmFirstError(e, order);
    if (built && built.ver === ver) lastSay = built.sentence;
    say.textContent = first || (failed ? FM_FAILED : lastSay);
    say.classList.toggle('bad', !!first || failed);
    const pending = !!(timer || flying);          // the words under it may describe an older form: kept, shown dim, and said to be on their way
    if (pending) say.setAttribute('aria-busy', 'true'); else say.removeAttribute('aria-busy');
    retry.hidden = !failed || !!first;
    go.disabled = !ready();
  };
  const ask = async () => {
    timer = 0;
    if (!d.isConnected || flying) return;           // an answer on its way asks again when it lands, if the form changed since
    if (Object.keys(C.fmErrors(sc, F)).length) {            // not sent: an older answer's errors stay only under boxes that are as they were
      built = null; failed = false;
      serverErr = C.fmKeepErrors(serverErr, served, C.fmAnswers(sc, F));
      paintState();
      return;
    }
    const mine = ver, answers = C.fmAnswers(sc, F);
    flying = true; failed = false; paintState();
    let a;
    try { a = await timed('/api/tester/drafts/form/build', edit ? { answers, replace: true } : { answers }); }
    catch (_) { a = { ok: false, json: null }; }
    finally { flying = false; }            // whatever happened, a request is never still "out"
    if (!d.isConnected) return;
    const j = a.ok && a.json && typeof a.json === 'object' ? a.json : null;
    if (mine === ver) {
      built = null; serverErr = {}; served = null;
      if (j && j.ok === true && typeof j.code === 'string') built = { ver: mine, code: j.code, name: String(j.name || ''), sentence: String(j.sentence || '') };
      else if (j && j.ok === false && j.errors && typeof j.errors === 'object') { serverErr = Object.fromEntries(Object.entries(j.errors).filter(([, v]) => typeof v === 'string')); served = answers; }
      else failed = true;                     // no answer, a refusal of the request, or something this page does not read
    }
    paintState();
    if (mine !== ver && !timer) ask();           // changed meanwhile and the 400 ms have passed: ask now
  };
  const touch = (f) => {
    ver++;
    failed = false;
    if (f === 'rule' || f === 'market') serverErr = {}; else delete serverErr[f];
    clearTimeout(timer);
    timer = setTimeout(ask, 400);
    paintState();
  };
  const suggest = () => { if (touched) return; F.name = C.fmSuggest(F.market, F.rule, taken); $('#fm_name', d).value = F.name; };
  const onEdit = (e) => {
    const t = e.target, f = t.dataset && t.dataset.fm;
    if (!f || (t.tagName === 'SELECT') !== (e.type === 'change')) return;      // a box counts as it is typed, a list when it is chosen
    if (f === 'rule' || f === 'market') {         // a market change gives the boxes still at the old market's starting numbers the new one's
      F = f === 'rule' ? C.fmSwitch(sc, F, t.value) : C.fmSetMarket(sc, F, t.value);
      suggest(); rest.innerHTML = restHtml();
    }
    else if (f === 'stop' || f === 'target') {
      if (t.dataset.part === 'kind') {
        const k = C.fmKinds(sc, F.rule, f).find((x) => x.id === t.value), v = $(`#fm_${id(f)}_v`, d);
        F[f] = C.fmHasValue(k) ? { kind: t.value, value: C.fmKindValue(sc, F.rule, f, t.value, F.market) } : { kind: t.value };
        v.value = F[f].value == null ? '' : F[f].value; v.hidden = !C.fmHasValue(k);
      } else F[f] = { ...F[f], value: t.value };
    } else {
      F[f] = t.value;
      if (f === 'name') touched = true;
    }
    touch(f);
  };
  d.addEventListener('input', onEdit);
  d.addEventListener('change', onEdit);
  d.addEventListener('keydown', (e) => { if (e.repeat && (e.key === 'Enter' || e.key === ' ') && e.target.closest('button')) e.preventDefault(); });      // a held key presses nothing twice
  d.addEventListener('click', (e) => {
    const x = e.target.closest('[data-x]');
    if (!x) return;
    if (x.dataset.x === 'cancel') return closeDialog();
    if (x.dataset.x === 'retry') {
      if (flying) return;
      d.focus({ preventScroll: true });           // the button goes away: the keyboard stays in the sheet
      clearTimeout(timer); timer = 0; failed = false;
      return ask();
    }
    if (x.dataset.x !== 'go' || !ready()) return;
    if (edit) {                                   // the draft is replaced only if it is the code the form read
      const b = S.bufs.get(edit.key);
      if (!b || b.kind === 'builtin') { closeDialog(); return log('<span class="err">That strategy is not open any more.</span>'); }
      if (b.code !== edit.code) { stale = true; paintState(); return; }
    }
    making = true; go.disabled = true;
    if (e.detail === 0) swallowRepeats();           // pressed with the keyboard: a held key goes nowhere
    if (!edit) {
      closeDialog(false);
      openScript(built.code, built.name);
      return log('Made from the form. Run it to see how it would have done.');
    }
    replaceCode(S.bufs.get(edit.key), built.code);
    closeDialog();
    log('Updated from the form. Run it again.');
  });
  const at = $(edit ? '#fm_market' : '#fm_name', d);
  at.focus({ preventScroll: true });
  if (!edit) at.select();
  paintState();
  ask();
  return true;
}
/* "Edit in the form…": a strategy the form made opens in it; one changed by hand asks first */
async function formEdit(anchor, b) {
  const code = b.code;            // what the form reads, and what Update may replace
  const got = await formRead(code);
  if (!got) return log('<span class="err">This strategy was not made with the form.</span>');
  if (got.intact) return formOpen(anchor, { key: b.key, answers: got.answers, code });
  const back = anchor && anchor.isConnected ? anchor : backTo(anchor, 'more');
  if (back) back.focus({ preventScroll: true });
  const d = dialog(`<h2>Edit in the form</h2><p>This strategy was changed by hand. Updating it from the form replaces the code with the form's version.</p>
    <div class="acts"><button class="btn btn-outline" data-x="cancel">Cancel</button><button class="btn btn-default" data-x="go">Open the form</button></div>`);
  d.querySelector('[data-x="go"]').focus();
  d.addEventListener('click', async (e) => {
    const x = e.target.closest('[data-x]');
    if (!x) return;
    if (x.dataset.x === 'cancel') return closeDialog();
    x.disabled = true;
    if (!(await formOpen(anchor, { key: b.key, answers: got.answers, code, wanted: () => d.isConnected })) && d.isConnected) closeDialog();
  });
}

function reviewDialog() {
  const b = buf();
  if (!b || b.kind === 'builtin') return;
  const runOk = S.run && S.run.bundle && !S.run.grid && S.run.strategy === `draft_${b.name}`;
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

/* ---- every metric of the open run: a popup. Build and unseen days side by side, by year, categories and rows picked by you ---- */
const AM = window.HBAllMetrics;
const AMK = 'hb_lab_am';
const amDefault = () => ({ cols: ['build', 'unseen', 'all'], year: '', side: '', hideCat: [], hide: [], view: 'metrics' });
function amLoad() { try { return { ...amDefault(), ...(JSON.parse(localStorage.getItem(AMK)) || {}) }; } catch (_) { return amDefault(); } }
function amSave(st) { try { localStorage.setItem(AMK, JSON.stringify(st)); } catch (_) { /* private mode: not kept */ } }
function allMetricsDialog() {
  const r = S.run && S.run.bundle ? S.run : null;
  if (!r || !AM) return;
  const trades = (r.bundle.trades || []).filter((t) => t && t.date), cap = r.bundle.run.capital || 0, st = amLoad();
  const yrs = AM.years(trades), scopeName = Object.fromEntries(AM.SCOPES);
  const d = dialog('');
  d.classList.add('am-dlg');
  const cell = (unit, v, tone) => `<td class="${tone || ''}">${esc(AM.format(unit, v))}</td>`;
  const toneOf = (unit, v) => (unit === 'usd' && v != null ? (v > 0 ? 'up' : v < 0 ? 'dn' : '') : '');
  function draw() {
    let cols = AM.SCOPES.map(([k]) => k).filter((k) => st.cols.includes(k));
    // A column with no trades (a run that only touched unseen days has no build days) is dropped when another has some,
    // and a card never opens with no column at all.
    const live = cols.filter((k) => AM.compute(AM.pick(trades, k, st.year, st.side), cap).trades);
    if (live.length) cols = live; else if (!cols.length) cols = ['all'];
    const sets = cols.map((k) => AM.compute(AM.pick(trades, k, st.year, st.side), cap));
    const none = (k, i) => k === 'unseen' && !sets[i].trades;
    const head = `<tr><th></th>${cols.map((k) => `<th>${esc(scopeName[k])}</th>`).join('')}</tr>`;
    let body = '';
    if (st.view === 'year') {
      const rows = AM.yearly(trades.filter((t) => !st.side || t.side === st.side), cap), keys = [['trades', 'int'], ['net', 'usd'], ['win_rate', 'pct'], ['profit_factor', 'num'], ['expectancy', 'usd'], ['max_dd', 'usd'], ['sharpe', 'num'], ['month_wr', 'pct']];
      const lab = { trades: 'Trades', net: 'Net', win_rate: 'Win rate', profit_factor: 'Profit factor', expectancy: 'Avg trade', max_dd: 'Max drawdown', sharpe: 'Sharpe', month_wr: 'Good months' };
      body = `<table class="am-t am-y"><thead><tr><th>Year</th>${keys.map(([k]) => `<th>${lab[k]}</th>`).join('')}</tr></thead><tbody>${rows.map((y) =>
        `<tr><th>${esc(y.year)}${y.unseen ? '*' : ''}</th>${keys.map(([k, u]) => cell(u, y[k], toneOf(u, y[k]))).join('')}</tr>`).join('')}</tbody></table>
        <p class="am-note">Each row is the calendar year's own trades. * 2025 straddles the cut: build days end 2025-06-30, unseen days start 2025-07-01 (pick the year above to see them apart).</p>`;
    } else {
      body = AM.CATS.filter(([id]) => !st.hideCat.includes(id)).map(([id, name, rows]) => {
        const shown = rows.filter(([m]) => !st.hide.includes(m));
        if (!shown.length) return '';
        return `<table class="am-t"><thead><tr><th>${esc(name)}</th>${cols.map((k) => `<th>${esc(scopeName[k])}</th>`).join('')}</tr></thead><tbody>${shown.map(([m, label, unit, hint]) =>
          `<tr><th title="${esc(hint)}">${esc(label)}</th>${cols.map((k, i) => none(k, i) ? '<td class="mu">not read</td>' : cell(unit, sets[i][m], toneOf(unit, sets[i][m]))).join('')}</tr>`).join('')}</tbody></table>`;
      }).join('');
    }
    if (!trades.length) body = '<p class="am-note">This run placed no trades, so there is nothing to measure. A written record draft places none itself: press Run again and it opens its saved research-engine run.</p>';
    const chip = (attr, val, text, on) => `<button class="am-c${on ? ' on' : ''}" data-${attr}="${esc(val)}">${esc(text)}</button>`;
    const sets2 = AM.CATS.map(([id, name, rows]) => `<fieldset><legend><label><input type="checkbox" data-cat="${id}"${st.hideCat.includes(id) ? '' : ' checked'}> ${esc(name)}</label></legend>${rows.map(([m, label]) =>
      `<label><input type="checkbox" data-m="${m}"${st.hide.includes(m) ? '' : ' checked'}> ${esc(label)}</label>`).join('')}</fieldset>`).join('');
    d.innerHTML = `<div class="am-head"><div class="am-top"><h2>All metrics</h2><button class="btn btn-outline btn-sm" data-x="close">Close</button></div>
      <p class="am-sub">${esc(String(r.cellLabel || r.strategy || ''))} · ${trades.length} trades · ${esc(trades.length ? `${trades[0].date} → ${trades[trades.length - 1].date}` : 'none')}${trades.some((t) => t.date >= AM.UNSEEN_FROM) ? '' : ' · this run never touched the unseen days'}</p>
      <div class="am-bar">
        <div class="am-g"><span>Days</span>${AM.SCOPES.map(([k, n]) => chip('col', k, n, st.cols.includes(k))).join('')}</div>
        <div class="am-g"><span>Year</span>${chip('year', '', 'All', !st.year)}${yrs.map((y) => chip('year', y, y, st.year === y)).join('')}</div>
        <div class="am-g"><span>Side</span>${chip('side', '', 'Both', !st.side)}${chip('side', 'long', 'Long', st.side === 'long')}${chip('side', 'short', 'Short', st.side === 'short')}</div>
        <div class="am-g"><span>Show</span>${chip('view', 'metrics', 'Every metric', st.view === 'metrics')}${chip('view', 'year', 'Year by year', st.view === 'year')}<button class="am-c" data-act2="adj">Choose rows</button></div>
      </div>
      <div class="am-adj" hidden>${sets2}<div class="am-adjb"><button class="btn btn-outline btn-sm" data-act2="all">Show all</button></div></div></div>
      <div class="am-body">${body || '<p class="am-note">Every category is hidden. Choose rows to bring some back.</p>'}</div>
      ${['n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw'].map((k) => `<i class="am-rz am-rz-${k}" data-rz="${k}"></i>`).join('')}`;
  }
  try { const z = JSON.parse(localStorage.getItem('hb_lab_am_size')); if (z && z.w && z.h) { d.style.width = `${Math.min(z.w, innerWidth - 16)}px`; d.style.height = `${Math.min(z.h, innerHeight - 16)}px`; } } catch (_) { /* default size */ }
  draw();
  let adjOpen = false;
  d.addEventListener('pointerdown', (e) => {          // stretch from any edge or corner; the card stays centred, so a dragged edge follows the pointer at twice the change
    const h = e.target.closest('[data-rz]');
    if (!h) return;
    e.preventDefault();
    const k = h.dataset.rz, x0 = e.clientX, y0 = e.clientY, w0 = d.offsetWidth, h0 = d.offsetHeight;
    h.setPointerCapture(e.pointerId);
    const mv = (m) => {
      if (k.includes('e')) d.style.width = `${Math.max(380, Math.min(innerWidth - 16, w0 + 2 * (m.clientX - x0)))}px`;
      if (k.includes('w')) d.style.width = `${Math.max(380, Math.min(innerWidth - 16, w0 - 2 * (m.clientX - x0)))}px`;
      if (k.includes('s')) d.style.height = `${Math.max(300, Math.min(innerHeight - 16, h0 + 2 * (m.clientY - y0)))}px`;
      if (k.includes('n')) d.style.height = `${Math.max(300, Math.min(innerHeight - 16, h0 - 2 * (m.clientY - y0)))}px`;
    };
    const up = () => {
      h.removeEventListener('pointermove', mv); h.removeEventListener('pointerup', up); h.removeEventListener('pointercancel', up);
      try { localStorage.setItem('hb_lab_am_size', JSON.stringify({ w: d.offsetWidth, h: d.offsetHeight })); } catch (_) { /* not kept */ }
    };
    h.addEventListener('pointermove', mv); h.addEventListener('pointerup', up); h.addEventListener('pointercancel', up);
  });
  d.addEventListener('click', (e) => {
    const t = e.target.closest('button');
    if (!t) return;
    if (t.dataset.x === 'close') return closeDialog();
    const ds = t.dataset;
    if (ds.col != null) { st.cols = st.cols.includes(ds.col) ? st.cols.filter((c) => c !== ds.col) : [...st.cols, ds.col]; if (!st.cols.length) st.cols = [ds.col]; }
    else if (ds.year != null) st.year = ds.year;
    else if (ds.side != null) st.side = ds.side;
    else if (ds.view != null) st.view = ds.view;
    else if (ds.act2 === 'adj') { adjOpen = !adjOpen; $('.am-adj', d).hidden = !adjOpen; return; }
    else if (ds.act2 === 'all') { st.hide = []; st.hideCat = []; }
    else return;
    amSave(st); draw(); $('.am-adj', d).hidden = !adjOpen;
  });
  d.addEventListener('change', (e) => {
    const i = e.target;
    if (i.dataset.cat) st.hideCat = i.checked ? st.hideCat.filter((c) => c !== i.dataset.cat) : [...st.hideCat, i.dataset.cat];
    else if (i.dataset.m) st.hide = i.checked ? st.hide.filter((c) => c !== i.dataset.m) : [...st.hide, i.dataset.m];
    else return;
    amSave(st); draw(); $('.am-adj', d).hidden = !adjOpen;
  });
}

/* Delete one strategy or several: one sheet, then one request per name, one after the other. A refusal is the server's own
   sentence. The files go to the trash folder beside the strategies (the server moves them; nothing is unlinked). */
function deleteDialog(name) { deleteStrategies([name]); }
function deleteStrategies(names) {
  if (!names.length || S.delBusy) return;
  const dirty = names.filter((n) => { const b = S.bufs.get(`d:${n}`); return !!b && isDirty(b); });      // their changes go with them: the sheet says so
  const d = dialog(C.deleteConfirmHtml(names, dirty));
  d.addEventListener('click', (e) => {
    const x = e.target.closest('[data-x]');
    if (!x) return;
    closeDialog();
    if (x.dataset.x === 'go') deleteNow(names);
  });
}
async function deleteNow(names) {
  if (S.delBusy) return;
  S.delBusy = true;
  const done = [], gone = [], failed = [];     // gone: the server did not have it any more (told apart: not counted as deleted)
  try {
    for (const name of names) {
      const r = await send('DELETE', `/api/tester/drafts/${encodeURIComponent(name)}`);
      if (!r.ok) { failed.push({ name, error: r.error }); continue; }
      (r.json && r.json.deleted === true ? done : gone).push(name);
      S.bufs.delete(`d:${name}`);
      if (S.cur === `d:${name}`) { S.cur = null; S.run = null; }
    }
    const out = [...done, ...gone];
    S.picks = S.picks.filter((k) => !out.includes(C.draftName(k)));
    if (S.anchor && out.includes(C.draftName(S.anchor))) S.anchor = '';
    await loadLists(); paintAll();
  } finally { S.delBusy = false; }
  if (names.length === 1) {
    if (failed.length) log(`<span class="err">${esc(failed[0].error)}</span>`);
    else if (gone.length) log(esc(C.goneLine(gone)));
  } else {
    const line = esc(C.deleteLine(done.length, failed, gone));
    log(failed.length ? `<span class="err">${line}</span>` : line);
  }
}

/* ---- groups: the library in sections ----
   The groups and who is in them are the server's: one file beside the strategies, and no strategy's own file is
   ever changed for it. Which sections are folded shut is this browser's. */
const folded = new Set();
/* the list's sort, status filter and market (the owner, 2026-10-18): kept in this browser */
const LIST_KEY = 'hb.labList';
const listView = (() => { try { return { sort: 'groups', show: 'live', market: '', ...JSON.parse(localStorage.getItem(LIST_KEY) || '{}') }; } catch (_) { return { sort: 'groups', show: 'live', market: '' }; } })();
function setListView(k, v) {
  listView[k] = v;
  try { localStorage.setItem(LIST_KEY, JSON.stringify(listView)); } catch (_) { /* this session only */ }
  paintLibList();
}
try { for (const g of JSON.parse(localStorage.getItem('hb_lab_folded') || '[]')) folded.add(String(g)); } catch (_) { /* private mode: all open */ }
const saveFolded = () => { try { localStorage.setItem('hb_lab_folded', JSON.stringify([...folded])); } catch (_) { /* private mode */ } };
function foldGroup(el) {
  const g = el.dataset.g, shut = !folded.has(g);
  if (shut) folded.add(g); else folded.delete(g);
  saveFolded();
  el.setAttribute('aria-expanded', String(!shut));       // in place, without a repaint: the chevron turns
  el.closest('.lb-g').classList.toggle('folded', shut);
  if (S.picks.length && S.view === 'lib') {              // rows that are folded away are no longer picked (the repaint is only for that)
    const keep = C.prunePicks(S.picks, shownList());
    if (keep.length !== S.picks.length) { S.picks = keep; paintLib(); }
  }
}
/* every change answers the whole new state */
async function regroup(path, body) {
  const r = await send('POST', `/api/tester/groups${path}`, body);
  if (r.ok) { S.groups = r.json; paintLib(); }
  return r;
}
/* a row's ⋯: the one group this strategy is listed under */
function fileMenu(el) {
  const { id, name, row } = el.dataset, to = [...S.groups.groups, ''], cur = S.groups.members[id] || '';
  const mark = (S.groups.status || {})[id] || '', marks = [...Object.entries(C.MARKS), ['', 'No status']];
  const targets = row ? C.deleteTargets(S.picks, row) : [];       // a saved strategy's row also deletes: itself, or every picked one when it is picked
  menu(el, `<h6>Status</h6>${marks.map(([m, t]) => `<button class="row" data-pick="st:${m}"><span>${t}</span>${m === mark ? '<small>✓</small>' : ''}</button>`).join('')}<hr>
    ${to.length > 1 ? `<h6>Move to</h6>${to.map((g, i) => `<button class="row" data-pick="${i}"><span>${esc(g || 'Ungrouped')}</span>${g === cur ? '<small>✓</small>' : ''}</button>`).join('')}<hr>` : ''}
    <button class="row" data-pick="new"><span>New group…</span></button>${row ? `<hr><button class="row" data-pick="delete"><span>${esc(C.deleteItem(S.picks, row))}</span></button>` : ''}`,
  async (pick) => {
    if (pick === 'delete') return deleteStrategies(targets);
    if (String(pick).startsWith('st:')) {
      const m = String(pick).slice(3);
      if (m === mark) return;
      const r = await regroup('/status', { strategy: id, status: m || null });
      if (!r.ok) log(`<span class="err">Status not set: ${esc(r.error)}</span>`);
      return;
    }
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
const ICON_UNLOCK = '<svg class="lb-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="11" width="14" height="9" rx="2"/><path d="M8 11V8a4 4 0 0 1 7.5-2"/></svg>';
const ICON_LOCK = '<svg class="lb-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5.5" y="11" width="13" height="9" rx="2.5"/><path d="M8.5 11V8.2a3.5 3.5 0 0 1 7 0V11"/></svg>';
const ICON_PLUS = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M12 5.5v13M5.5 12h13"/></svg>';
const ICON_PLAY = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M7.5 4.8v14.4a.9.9 0 0 0 1.36.77l11.7-7.2a.9.9 0 0 0 0-1.54L8.86 4.03a.9.9 0 0 0-1.36.77z" fill="currentColor"/></svg>';
const ICON_MORE = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5.5" cy="12" r="1.7" fill="currentColor"/><circle cx="12" cy="12" r="1.7" fill="currentColor"/><circle cx="18.5" cy="12" r="1.7" fill="currentColor"/></svg>';
const ICON_CHEV = '<svg class="lb-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 5.5l6.5 6.5L9 18.5"/></svg>';
/* ---- the view switcher (2026-10-09) ----
   Six views used to sit in two rows of segmented buttons. Now the sidebar's head is ONE button that names the view
   on show; it opens a short menu in two groups -- the library of strategies, and the pipeline that tests ideas. */
const VIEW_GROUPS = [['Library', VIEWS, { lib: 'Your saved scripts and the built-in ones', tk: 'Every block, chat tool, skill and script, read-only' }],
  ['Pipeline', PIPE_TABS, { pq: 'Ideas waiting, running and finished', pb: 'The strategies that passed every stage' }]];
const ICON_UPDOWN = '<svg class="lb-ud" viewBox="0 0 10 14" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 5.2 5 2.2l3 3M2 8.8l3 3 3-3"/></svg>';
function viewName(v) { const t = [...VIEWS, ...PIPE_TABS].find(([id]) => id === v); return t ? t[1] : 'Strategies'; }
function viewSwitch() {
  return `<button class="lb-view" data-act="viewmenu" data-fk="viewmenu" aria-haspopup="menu" aria-expanded="false" aria-label="${esc(viewName(S.view))}: choose what this list shows" title="Switch between Strategies, Arsenal, Queue and Book"><b>${esc(viewName(S.view))}</b>${ICON_UPDOWN}</button>`;
}
function viewMenu(anchor) {
  const html = VIEW_GROUPS.map(([group, views, why]) => `<h6>${group}</h6>${views.map(([v, t]) =>
    `<button class="row" role="menuitemradio" aria-checked="${S.view === v}" data-pick="${v}" title="${esc(why[v] || '')}"><span>${t}</span>${S.view === v ? '<small>✓</small>' : ''}</button>`).join('')}`).join('<hr>');
  menu(anchor, html, (v) => { setView(v); const t = root.querySelector('[data-fk="viewmenu"]'); if (t) t.focus({ preventScroll: true }); });
  menuEl.dataset.for = 'view';
  menuEl.setAttribute('role', 'menu');
  anchor.setAttribute('aria-expanded', 'true');
}
/* A strategy that is on the Desk is locked in the Lab (its code is what the Desk copied): read-only until the owner unlocks it by hand.
   The unlock lasts until the page is closed; the copy on the Desk never changes by editing, only by Promote. */
const onDesk = (b) => !!b && b.kind === 'draft' && !!S.desk && S.desk.has(b.name);
const locked = (b) => onDesk(b) && !S.unlocked.has(b.name);
/* The name a strategy gives itself (its `name`, the one the Desk shows), when it is not the file's: "NQ 5m 9:30 CLOSE" for nq_fair_price_v1. */
function ownName(file) {
  const b = S.bufs.get(`d:${file}`), d = S.drafts.find((x) => x.name === file);
  const v = (b && b.valid && b.valid.ok && b.valid.meta && b.valid.meta.name) || (d && d.meta && d.meta.name);
  return typeof v === 'string' && v.trim() && v.trim() !== file ? v.trim() : '';
}
/* the Strategies list's rows: the saved and unsaved ones, then the locked built-ins */
function libRows() {
  const unsaved = [...S.bufs.values()].filter((b) => b.kind === 'new');
  const rows = [
    ...unsaved.map((b) => ({ key: b.key, name: b.name || 'Untitled', sub: 'Not saved yet', dot: 'off', flag: '' })),
    ...S.drafts.map((d) => {
      const b = S.bufs.get(`d:${d.name}`), dirty = b && isDirty(b);
      const bad = b && b.valid ? !b.valid.ok : !d.ok;
      const own = ownName(d.name), state = bad ? 'Needs a fix' : dirty ? 'Edited' : 'Draft';
      return { key: `d:${d.name}`, id: d.id, name: d.name, title: own, root: (d.meta && d.meta.root) || '', modified: d.modified || '', locked: !!(S.desk && S.desk.has(d.name) && !S.unlocked.has(d.name)), dirty: !!dirty, sub: state, dot: bad ? 'err' : dirty ? 'off' : '', flag: bad ? '!' : '', desk: !!(S.desk && S.desk.has(d.name)) };
    })];
  const builtins = S.builtins.map((s) => ({ key: `b:${s.id}`, id: s.id, name: s.name || s.id, sub: s.root || '', root: s.root || '', lock: true, desk: S.deskBuiltins.has(s.id) }));
  return { rows, builtins };
}
/* the rows as the list shows them, top to bottom (a folded group's rows are not shown) */
/* what the list shows: the status / market filter first; then a search (best first), a sort (flat), or the groups */
function listShape() {
  const { rows, builtins } = libRows(), keep = (l) => C.libShow(l, S.groups, listView.show, listView.market);
  const r = keep(rows), b = keep(builtins), all = [...r, ...b];
  if (S.libQ.trim()) return { flat: C.libFilter(all, S.libQ), search: true, r, b };
  if (listView.sort !== 'groups') return { flat: C.libSort(all, S.groups, listView.sort), r, b };
  return S.groups ? { secs: C.withDeskGroup(C.sections(all, S.groups)), r, b } : { flat: null, r, b };
}
const shownList = () => { const v = listShape(); return v.flat || (v.secs ? C.shownRows(v.secs, folded) : [...v.r, ...v.b]); };
/* the Strategies list under its search box: with a search, one flat list of what matches (best first); without, the groups */
function libBody() {
  const v = listShape(), { r: rows, b: builtins } = v;
  const item = (r) => `<button class="lb-item${C.markOf(r, S.groups) === 'dead' ? ' dead' : ''}${S.cur === r.key ? ' sel' : ''}${S.picks.includes(r.key) ? ' picked' : ''}" data-key="${esc(r.key)}" aria-current="${S.cur === r.key}"${C.canPick(r) ? ` aria-selected="${S.picks.includes(r.key)}"` : ''} title="${esc([r.title ? `${r.name}.py` : '', r.lock ? 'Read-only' : r.locked ? 'On the Desk: locked. Open it and press the lock to edit.' : ''].filter(Boolean).join(' · '))}">
        ${r.lock || r.locked ? ICON_LOCK : ICON_DOC}<span class="it"><b>${esc(r.title || r.name)}</b><small>${markPill(r)}${esc(r.sub)}</small>${r.desk && !S.groups ? '<i class="lb-desk" title="On the Desk page">On the Desk</i>' : ''}</span>${r.lock ? '<span></span>' : `<span class="lb-flag">${r.flag}</span>`}</button>`;
  /* with groups: each one a section that folds, then Ungrouped. A saved strategy's row carries a ⋯ that moves it. */
  const filed = (r) => (r.id ? `<div class="lb-row">${item(r)}<button class="hb-ib lb-more" data-act="file" data-id="${esc(r.id)}" data-name="${esc(r.name)}"${C.canPick(r) ? ` data-row="${esc(r.key)}"` : ''} aria-label="${C.canPick(r) ? `Move ${esc(r.name)} to a group, or delete it` : `Move ${esc(r.name)} to a group`}" title="${C.canPick(r) ? 'Move to a group, or delete' : 'Move to a group'}" aria-haspopup="menu">${ICON_MORE}</button></div>` : item(r));
  const section = (s) => {
    if (!s.name && !s.rows.length) return '';
    const shut = folded.has(s.name), n = s.rows.length;
    return `<div class="lb-g${shut ? ' folded' : ''}"><div class="lb-gh"><button class="lb-sh" data-act="fold" data-g="${esc(s.name)}" aria-expanded="${!shut}">${ICON_CHEV}<span>${esc(s.name || 'Ungrouped')}</span><i>${n}</i></button>
        ${s.name && !s.auto ? `<button class="hb-ib lb-more" data-act="group" data-g="${esc(s.name)}" data-n="${n}" aria-label="Rename or delete the group ${esc(s.name)}" title="Rename or delete" aria-haspopup="menu">${ICON_MORE}</button>` : ''}</div>
      <div class="lb-gb">${s.rows.map(filed).join('') || '<div class="lb-empty">Move a strategy here from its ⋯</div>'}</div></div>`;
  };
  if (v.flat) {
    return v.flat.length ? v.flat.map(S.groups ? filed : item).join('')
      : `<div class="lb-empty">${v.search ? `No strategy matches “${esc(S.libQ.trim())}”.` : 'No strategy with this status or market.'}</div>`;
  }
  return `${rows.length ? '' : '<div class="lb-empty">Nothing here yet. Press + to paste a script or start from a template.</div>'}
    ${v.secs ? v.secs.map(section).join('')
      : `${rows.map(item).join('')}<div class="lb-sh">Built-in</div>${builtins.map(item).join('')}`}`;
}
/* a row's status as a small pill before its sub-line */
function markPill(r) { const m = C.markOf(r, S.groups); return m ? `<i class="lb-mark m-${m}">${C.MARKS[m]}</i>` : ''; }
/* Sort, Show (by status) and Market, under the search box */
function listTools(all) {
  const opt = (v, t, cur) => `<option value="${esc(v)}"${v === cur ? ' selected' : ''}>${esc(t)}</option>`;
  const mk = C.libMarkets(all);
  return `<div class="lb-tools">
    <select id="libSort" aria-label="Sort the list" title="Sort">${C.LIB_SORTS.map(([v, t]) => opt(v, t, listView.sort)).join('')}</select>
    <select id="libShow" aria-label="Show by status" title="Show">${C.LIB_SHOWS.map(([v, t]) => opt(v, t, listView.show)).join('')}</select>
    <select id="libMkt" aria-label="Market" title="Market">${opt('', 'Markets', listView.market)}${mk.map((m) => opt(m, m, listView.market)).join('')}</select>
  </div>`;
}
/* the search box's own change: only the list under it is painted again, so the box keeps the caret */
function paintLibList() {
  const l = $('#libList');
  if (!l) return;
  if (S.picks.length) S.picks = C.prunePicks(S.picks, shownList());
  l.innerHTML = libBody();
}
function paintLib() {
  const el = $('#labLib .in');
  if (!el) return;
  if (S.picks.length) S.picks = C.prunePicks(S.picks, shownList());          // a row that is folded away, deleted or gone is no longer picked
  const top = el.scrollTop, q = document.activeElement && document.activeElement.id === 'libQ' ? document.activeElement : null, at = q ? q.selectionStart : 0;
  const seg = viewSwitch();
  if (pipeOn()) { paintPipe(el, `<div class="lb-top lb-sw">${seg}</div>`, top); return; }      // its list here, its page in the middle
  if (S.view === 'tk') {
    el.innerHTML = `<div class="lb-top lb-sw">${seg}</div>${toolkitHead()}<div id="tkList">${toolkitList()}</div>`;
    el.scrollTop = top;
    return;
  }
  const { rows, builtins } = libRows(), n = rows.length + builtins.length;
  el.innerHTML = `<div class="lb-top lb-sw">${seg}<button class="hb-ib" data-act="new" data-fk="new" aria-label="New strategy" title="New strategy">${ICON_PLUS}</button></div>
    <div class="tk-find"><input id="libQ" type="search" placeholder="Find a strategy: ${n} in all" value="${esc(S.libQ)}" spellcheck="false" autocomplete="off" aria-label="Find a strategy"></div>
    ${listTools([...rows, ...builtins])}
    <div id="libList">${libBody()}</div>`;
  el.scrollTop = top;
  if (q) { const n = $('#libQ'); if (n) { n.focus(); n.setSelectionRange(at, at); } }      // a repaint from elsewhere never takes the caret from the search box
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

/* ---- the strategy pipeline in the sidebar ----
   Two views: the Queue (every idea and where it stands) and the Book (the finishers).
   While one of them is open the MIDDLE of the page is theirs (#labPipe): the editor, the chart and the result are hidden, not rebuilt
   (applyPanels shows them as switched off and leaves P, the person's own choice, alone), so leaving the view brings everything back as
   it was. The sidebar keeps the list (the ideas, the strategies).
   ONE answer of the chart service feeds both (GET /api/tester/pipeline), asked again every 5 s while one of them is on screen.
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
  if (S.view === 'tk') loadToolkit(); else if (S.view === 'lib') loadDesk();
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
  if (S.view === 'pb') {
    const card = (A.book || []).find((c) => c && c.name === S.plCard);
    if (card) loadCurve(card.name, String(card.utc || ''));
    if (!S.desk) loadDesk();      // the "On the Desk" badge reads the promoted Lab strategies
  }
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
/* A Book row's own line: what it made on the unseen days (one contract, after costs), then how many trades and its profit factor. */
function plBookRowLine(card) {
  const l = C.plBookLine(card);
  if (l.net === '—' && !l.rest) return '';
  return `<span class="pl-res"><b class="${l.tone}">${esc(l.net)}</b>${l.rest ? `<span>${esc(l.rest)}</span>` : ''}${S.desk && S.desk.has(card.name) ? '<i title="A promoted Lab strategy of this name is on the Desk">On the Desk</i>' : ''}</span>`;
}
/* An idea's equity curve and first numbers (GET /pipeline/curve/<name>): asked once per name and row change; the old one stays on the page meanwhile. */
let plCurveSeq = 0;
async function loadCurve(name, key = '') {
  const was = S.plCurve;
  if (!name || (was && was.name === name && was.key === key && (was.loading || was.data || was.error))) return;
  const seq = ++plCurveSeq;
  S.plCurve = { name, key, loading: true, data: was && was.name === name ? was.data : null, error: '' };
  const r = await send('GET', `/api/tester/pipeline/curve/${encodeURIComponent(name)}`);
  if (seq !== plCurveSeq) return;
  const ok = r.ok && !!r.json;
  S.plCurve = { name, key, loading: false, data: ok ? r.json : null, error: ok ? '' : String(r.error || 'no answer') };
  if (plOpen()) paintLib();
}
/* The curve as a picture: the running total by traded day, a soft fill to the $0 line, the last value marked; its two ends dated. */
const EQ_W = 640, EQ_H = 180, EQ_PAD = 8;
function plCurveFig(cv) {
  const g = C.plCurvePath(cv && cv.curve, EQ_W, EQ_H, EQ_PAD);
  if (!g) return '<p class="pp-note">Not enough traded days to draw a curve.</p>';
  const tone = g.up ? 'pos' : 'neg';
  return `<figure class="pl-eq ${tone}" data-curve="1">
    <div class="pl-eq-top"><span class="pl-eq-read" id="plEqRead" aria-live="off">${esc(C.plCurveRead(cv, null))}</span><span class="pl-eq-max">${esc(C.plMoney(g.max))}</span></div>
    <svg viewBox="0 0 ${EQ_W} ${EQ_H}" preserveAspectRatio="none" role="img" aria-label="Equity curve: ${esc(C.plSigned(g.last))} over ${esc(String(cv.days))} traded days">
      <path class="pl-eq-area" d="${esc(g.area)}"/><line class="pl-eq-zero" x1="${EQ_PAD}" x2="${EQ_W - EQ_PAD}" y1="${esc(g.zero)}" y2="${esc(g.zero)}"/>
      <path class="pl-eq-line" d="${esc(g.line)}"/><line class="pl-eq-x" id="plEqX" x1="0" x2="0" y1="${EQ_PAD}" y2="${EQ_H - EQ_PAD}" hidden/>
      <circle class="pl-eq-dot" cx="${g.dot[0]}" cy="${g.dot[1]}" r="3.5"/></svg>
    <figcaption><span>${esc(cv.start || '')}</span><span>${cv.period === 'test' ? 'the days it had never seen' : 'the build days'} · 1 contract, after costs</span><span>${esc(cv.end || '')}</span></figcaption></figure>`;
}
/* What a strategy did, on top of its page: the tiles, the curve, and what can be done with it. */
function plResults(name, canShow) {
  const L = S.plCurve && S.plCurve.name === name ? S.plCurve : null, cv = L && L.data;
  const busy = S.plExec === name;
  const acts = `<div class="pl-acts2"><button class="btn btn-outline" data-act="plexec" data-name="${esc(name)}" data-fk="exec"${busy || S.plBusy ? ' disabled' : ''}>${busy ? 'Opening the chart…' : 'Show executions on chart'}</button></div>`;
  if (!cv) return `${L && L.error ? `<p class="pp-note" role="status">${esc(L.error)}</p>` : '<p class="pp-note" role="status">Loading its results…</p>'}${L && L.error ? '' : ''}${canShow ? acts : ''}`;
  return `<div class="pl-tiles">${C.plCurveTiles(cv).map((t) => `<div class="pl-tile"><span>${esc(t.k)}</span><b class="${t.tone}">${esc(t.v)}</b></div>`).join('')}</div>
    ${plCurveFig(cv)}${acts}`;
}
/* The curve under the pointer: the day's date and the total by then, with a hairline; off the chart, the last value again. */
document.addEventListener('pointermove', (e) => {
  const svg = e.target && e.target.closest ? e.target.closest('.pl-eq svg') : null;
  if (!svg) return;
  const cv = S.plCurve && S.plCurve.data, read = document.getElementById('plEqRead'), hair = document.getElementById('plEqX');
  if (!cv || !read || !hair) return;
  const box = svg.getBoundingClientRect(), x = ((e.clientX - box.left) / box.width) * EQ_W, n = cv.curve.length;
  const i = C.plCurveAt(cv.curve, x, EQ_W, EQ_PAD);
  const px = EQ_PAD + ((i + 1) / n) * (EQ_W - 2 * EQ_PAD);
  hair.setAttribute('x1', px); hair.setAttribute('x2', px); hair.removeAttribute('hidden');
  read.textContent = C.plCurveRead(cv, i);
});
document.addEventListener('pointerout', (e) => {
  const svg = e.target && e.target.closest ? e.target.closest('.pl-eq svg') : null;
  if (!svg || (e.relatedTarget && svg.contains(e.relatedTarget))) return;
  const cv = S.plCurve && S.plCurve.data, read = document.getElementById('plEqRead'), hair = document.getElementById('plEqX');
  if (hair) hair.setAttribute('hidden', '');
  if (cv && read) read.textContent = C.plCurveRead(cv, null);
});
/* Show-on-chart: the picked box's trades become a run of the tester (once), and the chart on this page is asked to show it. */
async function showExecutions(name) {
  if (!name || S.plExec) return;
  S.plExec = name; paintLib();
  const r = await send('POST', '/api/tester/pipeline/executions', { name });
  S.plExec = '';
  const j = r.json || {};
  if (!r.ok || j.ok === false) { pipeSaid(String(j.detail || r.error || 'The chart could not be opened.'), true); return; }
  const shown = await showRunOnChart(j.run_id, j.end ? { date: j.end } : null);
  log(esc(C.plExecSaid(name, j, shown)));
}
const plKv = (rows) => `<div class="rs-group pl-grp">${rows.map(([k, v]) => `<div class="pl-kv"><span>${esc(k)}</span><b>${esc(v)}</b></div>`).join('')}</div>`;
const plChip = (label, tone) => `<span class="rs-chip pl-chip ${tone}">${esc(label)}</span>`;
const plStage = (n, name, mark, text, lines) => `<section class="pl-stage"><header><b><span>Stage ${n}</span> ${esc(name)}</b><span class="pl-mark ${mark.tone}">${esc(mark.text)}</span></header>
    ${text ? `<p>${esc(text)}</p>` : ''}
    ${(lines || []).length ? `<ul class="pl-lines">${lines.map((x) => { const k = C.plMark(x.passed); return `<li class="${k.tone}"><i>${esc(k.text)}</i><span>${esc(x.text)}</span></li>`; }).join('')}</ul>` : ''}</section>`;

/* -- the sidebar: a list -- */
function pipeSide() {
  const L = S.pl;
  if (!L) return '<div class="lb-empty" role="status">Loading…</div>';
  if (!L.data) return `<div class="lb-empty" role="status">${esc(L.error)}</div>`;
  const A = L.data;
  if (S.view === 'pb') {
    const book = A.book || [];
    if (!book.length) return '<div class="lb-empty">No strategies yet.</div>';
    return `<div class="pl-list">${book.map((card) => {
      const b = C.plBookCard(card), on = b.name === S.plCard;
      return `<button class="tk-row pl-row${on ? ' sel' : ''}" data-act="plbook" data-name="${esc(b.name)}" data-fk="book:${esc(b.name)}" aria-current="${on}">
        <span class="tk-nm"><b title="${esc(b.name)}">${esc(b.name)}</b>${plChip(b.label, b.tone)}</span><span class="pl-fam">${esc(b.sub)}</span>
        ${plBookRowLine(card)}</button>`;
    }).join('')}</div>`;
  }
  const all = A.ideas || [], names = Object.fromEntries((A.stages || []).map((s) => [s.n, s.name]));
  if (!all.length) return '<div class="lb-empty">No ideas yet.</div>';
  const cnt = (f) => (f === 'all' ? all.length : all.filter((i) => i.label === f).length);
  const fs = ['all', 'Passed', 'Waiting', 'Running', 'Stopped', 'Problem'].filter((f) => f === 'all' || f === S.plFilter || cnt(f) > 0);
  const chips = `<div class="pl-filter" role="group" aria-label="Show">${fs.map((f) => `<button class="pl-fc${S.plFilter === f ? ' on' : ''}" data-act="plfilter" data-f="${esc(f)}" data-fk="f:${esc(f)}" aria-pressed="${S.plFilter === f}">${f === 'all' ? 'All' : esc(f)} <i>${cnt(f)}</i></button>`).join('')}</div>`;
  const ideas = S.plFilter === 'all' ? all : all.filter((i) => i.label === S.plFilter);
  if (!ideas.length) return `${chips}<div class="lb-empty">None are ${esc(S.plFilter.toLowerCase())}.</div>`;
  return `${chips}<div class="pl-list">${ideas.map((it) => {
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
  return `<div class="pp">${stale}${said}${profBar(L.data)}${S.view === 'pq' ? queueMain(L.data) : bookMain(L.data)}</div>`;
}
/* THE SWITCH: the pipeline works, or it does not (one pipeline since 2026-10-18). The choice is the whole app's: the runner and every chat read it. */
const MODE_SAYS = { off: 'The pipeline is off. Press On to start it.',
  live: 'Each idea is judged at one contract after costs: it makes money, beats random entries, and wins 3 points more often than its reward-to-risk needs. A pass is tagged Live, or Live + Prop when its Sharpe and months positive are steady too.' };
function profBar(A) {
  const P = A && A.profile;
  if (!P || !Array.isArray(P.modes)) return '';
  const seg = P.modes.map((o) => `<button class="pl-fc${o.id === P.mode ? ' on' : ''}" data-act="plmode" data-m="${esc(o.id)}" data-fk="mode:${esc(o.id)}" aria-pressed="${o.id === P.mode}"${S.plBusy ? ' disabled' : ''}>${esc(o.short || o.label)}</button>`).join('');
  return `<div class="pl-prof"><div class="pl-prof-row"><span class="pl-prof-l">Pipeline</span><div class="pl-filter" role="group" aria-label="Pipeline">${seg}</div></div>
    <p class="pl-quiet">${MODE_SAYS[P.mode] || ''}</p></div>`;
}
async function pickMode(id) {
  if (S.plBusy) return;
  S.plBusy = true; paintLib();
  const r = await send('POST', '/api/tester/pipeline/mode', { mode: id });
  S.plBusy = false;
  pipeSaid(r.ok && r.json ? String(r.json.text || '') : String(r.error || ''), !(r.ok && r.json && r.json.ok !== false));
}
/* The Queue's page: the count and the ONE button on top, always; under them the selected idea in full -- why it stopped (the ONE
   line), its card in words, every stage that ran with PASS / FAIL / — and its lines as the server wrote them. An idea that passed
   every stage carries the owner's two buttons. */
function queueMain(A) {
  const c = C.plControl(A), ideas = A.ideas || [];
  const bar = `<div class="pp-bar"><p class="pl-count">${esc(C.plCount(A.counts)).replace(/(\d) /g, '$1 ')}</p>
    <div class="pl-ctl"><button class="btn btn-default" data-act="plctl" data-fk="ctl"${c.enabled && !S.plBusy ? '' : ' disabled'}>${esc(c.label)}</button><span class="pl-quiet">${esc(c.line)}</span></div></div>`;
  const idle = !(A.runner && (A.runner.running || A.runner.paused));       // nothing to count and nothing to start: the one line says it
  if (!ideas.length) return `${idle ? '' : bar}<div class="pp-empty"><p>No ideas yet. Press Write an idea, or tell Claude your idea in any chat.</p>
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
    ${(I.stages || []).some((x) => x.n === 1 && x.passed) ? `<div class="pl-acts2"><button class="btn btn-outline" data-act="plexec" data-name="${esc(S.plIdea)}" data-fk="exec"${S.plExec || S.plBusy ? ' disabled' : ''}>${S.plExec === S.plIdea ? 'Opening the chart…' : 'Show executions on chart'}</button><span class="pl-quiet">The picked box, on the build days.</span></div>` : ''}
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
    <p class="pl-say">${esc(full.why)}</p>
    ${plResults(b.name, true)}
    <h3>The card</h3>${plKv(full.facts)}
    <p class="pp-note">Money is for one contract, after costs, on the days it had never seen.</p>
    ${full.numbers.length ? `<h3>Numbers</h3>${full.numbers.map((a) => `<h4 class="pl-h4">${esc(a.name)}</h4>${plKv(a.rows)}`).join('')}` : `<h3>Accounts</h3>${full.accounts.map((a) => `<h4 class="pl-h4">${esc(a.name)}</h4>${plKv(a.rows)}`).join('') || '<p class="pp-note">None on this card.</p>'}`}
    <h3>Stages</h3>${full.stages.map((s) => plStage(s.n, s.name, s.mark, s.text)).join('') || '<p class="pp-note">None on this card.</p>'}</article>`;
}
/* Both halves painted: only what changed is put in the page, the scroll stays (a new selection starts at the top) and so does the keyboard. */
let plPage = '', plMain = null;
function paintPipe(side, head, sideTop) {
  const main = document.querySelector('#labPipe .in'), at = document.activeElement;
  const fk = (at && (side.contains(at) || (main && main.contains(at))) ? at.dataset.fk : at === document.body ? S.plFk : '') || '';
  side.innerHTML = head + pipeSide();
  side.scrollTop = sideTop;
  if (main) {
    const html = pipeMain(), page = `${S.view}:${S.view === 'pq' ? S.plIdea : S.plCard}`, top = page === plPage ? main.scrollTop : 0;
    if (plMain !== html) { main.innerHTML = html; plMain = html; }
    main.scrollTop = top;
    plPage = page;
  }
  const back = fk ? [...root.querySelectorAll('[data-fk]')].find((x) => x.dataset.fk === fk && !x.disabled) : null;
  if (back && back !== document.activeElement) back.focus({ preventScroll: true });
  S.plFk = back ? '' : fk;        // a button that is grey while its action runs gets the keyboard back when it is done
}
function pickIdea(name) { S.plIdea = name; S.plArmed = ''; paintLib(); loadIdea(name); }
function pickCard(name) { S.plCard = name; plSelect(); paintLib(); }

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

/* The add-idea form (the Queue's Write an idea), a sheet. Its lists are the server's (`rules`, `indicators`, `sessions`: the research
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
      const tab = root.querySelector('[data-fk="viewmenu"]'); if (tab) tab.focus({ preventScroll: true });
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
      <p>Backtest it on real tick data in a sandbox, see every trade on the chart, and promote it to the Desk when you like what you see.</p>
      <div class="acts"><button class="btn btn-default btn-lg" data-act="paste">Paste a script</button><button class="btn btn-outline btn-lg" data-act="new" data-fk="new-welcome">Start from a template</button></div></div>`;
    paintHead();
    return;
  }
  const ro = b.kind === 'builtin';
  el.innerHTML = `<div class="ed-wrap" id="edWrap"><pre class="ed-gut" id="edGut" aria-hidden="true"></pre>
      <div class="ed-main"><pre class="ed-hl" aria-hidden="true"><code id="edHl"></code></pre>
        <textarea class="ed-ta" id="edTa" spellcheck="false" autocomplete="off" autocapitalize="off" autocorrect="off" wrap="off" aria-label="Python source" ${ro || locked(b) ? 'readonly' : ''}></textarea>
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
  const ro = b.kind === 'builtin', busy = !!(S.busy && S.active && S.active.key === b.key), dirty = isDirty(b);
  let cls = '', text = '', tip = '';
  if (ro) text = 'Built-in · read-only';
  else if (locked(b)) { cls = ''; text = 'On the Desk · locked'; tip = 'It is the code the Desk copied. Press the lock to edit it; the copy on the Desk changes only when you promote it again.'; }
  else if (b.valid && !b.valid.ok) { const st = C.statusOf(b.valid); cls = 'err'; text = st.text; }
  else if (b.kind === 'new') text = (b.code || '').trim() ? 'Not saved yet' : '';
  else if (dirty) { cls = 'edited'; text = 'Edited'; }
  else if (b.valid && b.valid.ok) { text = C.metaLine(b.valid.meta); tip = b.savedAt ? `Saved ${C.ago(b.savedAt, Date.now())}` : ''; }
  else if (b.code && b.code.trim()) text = 'Checking…';
  const own = b.kind === 'draft' ? ownName(b.name) : '';
  const name = b.kind === 'new'
    ? `<input class="doc-input" id="edName" value="${esc(b.name)}" placeholder="name" spellcheck="false" autocomplete="off" autocapitalize="off" aria-label="Strategy name"><span class="doc-name"><i>.py</i></span>`
    : own ? `<span class="doc-name">${esc(own)}</span>`
    : `<span class="doc-name">${esc(ro ? b.id : b.name)}<i>.py</i></span>`;
  if (own) text = text ? `${b.name}.py · ${text}` : `${b.name}.py`;
  const had = document.activeElement && document.activeElement.id === 'edName';   // typing a name must survive a repaint
  if (!had) doc.innerHTML = `${name}<span class="doc-state ${cls}" id="edState" title="${esc(tip || text)}">${esc(text)}</span>`;
  else { const st = document.getElementById('edState'); if (st) { st.className = `doc-state ${cls}`; st.textContent = text; st.title = tip || text; } }
  const canRun = !busy && (ro || (b.code || '').trim());
  const lockBtn = onDesk(b)
    ? (locked(b) ? `<button class="hb-ib" data-act="unlock" aria-label="Unlock to edit" title="On the Desk: locked. Unlock to edit.">${ICON_LOCK}</button>`
      : `<button class="hb-ib" data-act="lock" aria-label="Lock again" title="Unlocked. Lock it again.">${ICON_UNLOCK}</button>`) : '';
  const wfF = formOf(b), wfOn = !!(wfF && wfF.range.wf);
  acts.innerHTML = `${lockBtn}<button class="btn btn-default lab-run${busy ? ' busy' : ''}" data-act="run"${canRun ? '' : ' disabled'} title="${wfOn ? 'Run the walk-forward' : 'Run the backtest'} (⌘↵)">${ICON_PLAY}<span>${busy ? 'Running' : wfOn ? `Run ${esc(X.wfRatioText(wfF.range.wf))}` : 'Run'}</span></button>
    <button class="hb-ib" data-act="more" data-fk="more" aria-label="More" title="More" aria-haspopup="menu">${ICON_MORE}</button>`;
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
let WFEQ = null;      // the walk-forward's curve while its result is on screen (the out-of-sample one when both are)
let WFEQ2 = null;     // ... and the in-sample one beside it, when both sides are on screen
function drawEq() {
  const box = $('#eqw'); EQD = null;
  const eq = WFEQ || (S.run && S.run.bundle && S.run.bundle.equity);
  if (!box || !eq) return;
  const pts = eqThin(eqPoints(eq)), p2 = WFEQ2 ? eqThin(eqPoints(WFEQ2)) : [];
  if (pts.length < 2) { box.hidden = true; return; }
  const W = box.clientWidth, H = box.clientHeight, top = 20, bot = H - 22, padX = 6, all = pts.concat(p2);
  const lo = Math.min(0, ...all.map((p) => p.v)), hi = Math.max(0, ...all.map((p) => p.v));
  const t0 = Math.min(...all.map((p) => p.ms)), t1 = Math.max(...all.map((p) => p.ms));
  const X = (p) => padX + (t1 > t0 ? (p.ms - t0) / (t1 - t0) : 0) * (W - 2 * padX), Y = (v) => top + (1 - (v - lo) / ((hi - lo) || 1)) * (bot - top);
  const P = pts.map((p) => [X(p), Y(p.v)]);
  let d = `M${P[0][0].toFixed(1)},${P[0][1].toFixed(1)}`;
  for (let i = 0; i < P.length - 1; i++) { const p0 = P[i - 1] || P[i], p1 = P[i], p2 = P[i + 1], p3 = P[i + 2] || p2, t = 0.16;
    d += `C${(p1[0] + (p2[0] - p0[0]) * t).toFixed(1)},${(p1[1] + (p2[1] - p0[1]) * t).toFixed(1)} ${(p2[0] - (p3[0] - p1[0]) * t).toFixed(1)},${(p2[1] - (p3[1] - p1[1]) * t).toFixed(1)} ${p2[0].toFixed(1)},${p2[1].toFixed(1)}`; }
  const z = Y(0).toFixed(1), svg = box.querySelector('svg');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svg.innerHTML = `<defs><linearGradient id="labEqFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="currentColor" stop-opacity=".28"/><stop offset=".7" stop-color="currentColor" stop-opacity=".05"/><stop offset="1" stop-color="currentColor" stop-opacity="0"/></linearGradient></defs>
    <path d="${d}L${P[P.length - 1][0].toFixed(1)},${bot + 14}L${P[0][0].toFixed(1)},${bot + 14}Z" fill="url(#labEqFill)"/><line class="eq-base" x1="${padX}" x2="${W - padX}" y1="${z}" y2="${z}"/>${p2.length > 1 ? `<path class="eq-line2" d="${p2.map((p, i) => `${i ? 'L' : 'M'}${X(p).toFixed(1)},${Y(p.v).toFixed(1)}`).join('')}"/>` : ''}<path class="eq-line" d="${d}"/>`;
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
  const wfSel = wfRangeVal(f.range);
  const rangeOpts = X.RANGES.map((r) => `<option value="${r.id}"${!wfSel && f.range.id === r.id ? ' selected' : ''}>${esc(r.label)}</option>`).join('')
    + `<optgroup label="Walk-forward 3:1 blocks · all data">${WF_RANGE_OPTS.map(([v, l]) => `<option value="${v}"${wfSel === v ? ' selected' : ''}>${esc(l)}</option>`).join('')}</optgroup>`;
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
      ${wfSel ? `<div class="wf-hint">${wfRolling(f.range) ? 'Rolling: each month is traded on the best of the Heat map settings over the 3 months before it, then it steps a month.' : 'Run splits the data into blocks: 3 months in, the next 1 out, then the next block. Pick settings in Heat map below to let each block choose the best of them; for a search you can pick 3:1 rolling.'}</div>` : ''}
      ${!wfSel && f.range.id === 'custom' ? `<label>From</label><input type="text" data-f="start" value="${esc(f.range.start)}" placeholder="YYYY-MM-DD"><label>To</label><input type="text" data-f="end" value="${esc(f.range.end)}" placeholder="YYYY-MM-DD">` : ''}
      ${spent && !wfSel ? '<div class="warn">This reaches July 2025 or later, the test days: one read, only for a locked strategy. Each look is recorded.</div>' : ''}
      <label>Contracts</label><input type="number" data-f="qty" value="${esc(f.qty)}" min="1" step="1">
      <label title="Dollars per contract, round trip">Fees ($ per contract)</label><input type="number" data-f="commission" value="${esc(f.commission)}" min="0" step="0.25">
      <label>Slippage (ticks)</label><input type="number" data-f="slippage_ticks" value="${esc(f.slippage_ticks)}" min="0" step="1">
    </div></details>
  ${ins.length ? `<details class="rs-group rs-set rs-inputs"${S.inOpen === false ? '' : ' open'}><summary><span>Strategy settings</span><span>${esc(ins.filter((i) => i.type === 'choice').slice(0, 3).map((i) => f.inputs[i.key]).join(' · ') || `${ins.length} inputs`)}</span></summary>
    <div class="grid">${ins.map(inputRow).join('')}</div></details>` : ''}${rulesHtml(f, meta)}${heatSettingsHtml(f, meta)}`;
}
/* ---- Heat map (2026-10-12): pick up to three settings (the strategy's own, or any Trade rule), type the values each takes,
   and run every combination. A cell is an ordinary run (the same tester); the other settings stay as set above. The rules
   are tester.js (gridAxes, gridProblems, gridBody, heatPanels); the server is /api/tester/grid. */
const HEAT_ROLES = ['Rows', 'Columns', 'Panels'];
const HEAT_SUGGEST = { 'ctl.stop_pts': '10, 15, 20, 25', 'ctl.stop_atr': '1, 1.5, 2', 'ctl.target_pts': '20, 30, 40', 'ctl.target_atr': '1, 2, 3',
  'ctl.target_rr': '1, 2, 3', 'ctl.stop_wins': '0, 1, 2', 'ctl.stop_losses': '0, 1, 2', 'ctl.max_trades': '0, 1, 2, 3', 'ctl.max_consec_losses': '0, 2, 3',
  'ctl.entry_from': '09:35, 10:00, 10:30', 'ctl.entry_to': '10:30, 11:30, 12:00', 'ctl.flat_at': '11:30, 15:55', 'ctl.direction': 'both, long, short',
  'ctl.day_loss': '0, 500, 1000', 'ctl.day_profit': '0, 1000, 2000', 'ctl.cooldown_min': '0, 5, 15, 30', 'ctl.max_hold_min': '0, 15, 30, 60',
  'ctl.stop_mode': 'own, fixed, atr, candle', 'ctl.target_mode': 'own, fixed, rr', 'ctl.atr_minutes': '1, 5, 15', 'ctl.atr_period': '7, 14, 21',
  'ctl.be_after_pts': '0, 5, 10, 15, 20', 'ctl.trail_pts': '0, 5, 10, 15, 20', 'ctl.trail_after_pts': '0, 5, 10', 'ctl.stop_candle_ticks': '0, 2, 4, 8',
  'ctl.exit_line': 'off, vwap, vwap_rth, ema20, ema50', 'ctl.be_offset_ticks': '0, 1, 4', 'ctl.exit_line_min': '1, 5, 15' };
const HEAT_ZERO = { 'ctl.stop_pts': 'the strategy\'s own stop', 'ctl.stop_atr': 'the strategy\'s own stop', 'ctl.target_pts': 'the strategy\'s own target',
  'ctl.target_atr': 'the strategy\'s own target', 'ctl.target_rr': 'the strategy\'s own target', 'ctl.bar_minutes': 'the strategy\'s own bar',
  'ctl.be_after_pts': 'no breakeven', 'ctl.trail_pts': 'no trailing stop', 'ctl.trail_after_pts': 'trail from the fill' };
/* The Exit lab (the owner, 2026-10-18): the heat map set up to try exits on this strategy's own entries -- breakeven x a trailing
   stop, and its own stop vs the signal candle's. 0 / own = the strategy as it is. Run it on the build days. */
const EXIT_LAB = [['ctl.be_after_pts', '0, 5, 10, 15, 20'], ['ctl.trail_pts', '0, 5, 10, 15, 20'], ['ctl.stop_mode', 'own, candle']];
function exitLab() {
  const b = buf(), f = b && formOf(b);
  if (!f) return;
  const h = heatState(f);
  if (heatBusy(h)) return;
  h.rows = EXIT_LAB.map(([key, text]) => ({ key, text }));
  S.heatOpen = true;
  paintRes();
}
function heatSuggest(inp) {
  if (!inp) return '';
  if (HEAT_SUGGEST[inp.key]) return HEAT_SUGGEST[inp.key];
  if (inp.key === 'ctl.bar_minutes') return inp.choices.join(', ');
  if (inp.type === 'bool') return 'on, off';
  if (inp.type === 'choice') return inp.choices.slice(0, 4).join(', ');
  const st = inp.step || 1, d = Number(inp.default) || 0, lo = inp.min != null ? inp.min : -Infinity, hi = inp.max != null ? inp.max : Infinity;
  const round = (v) => { const r = Math.round(v / st) * st; return Number((inp.type === 'int' ? Math.round(r) : r).toFixed(4)); };
  const base = d ? [d * 0.5, d, d * 1.5, d * 2] : [lo > -Infinity ? lo : 0, 1, 2, 3].map((v, i) => (lo > -Infinity ? lo : 0) + i * st);
  return [...new Set(base.map(round).filter((v) => v >= lo && v <= hi))].join(', ');
}
function heatState(f) {
  return S.heat[f.strategy] || (S.heat[f.strategy] = { rows: [{ key: '', text: '' }, { key: '', text: '' }, { key: '', text: '' }], grid: null, id: '', token: 0, starting: false, err: '' });
}
const heatBusy = (h) => h.starting || (h.grid && !X.gridProgress(h.grid).final);
/* the current Rows / Columns / Panels as gridAxes wants them, and what it says about them */
function heatCheck(f, meta, h) {
  const rows = h.rows, filled = rows.filter((r) => r.key);
  if (!filled.length) return { note: 'Pick what to vary: two settings make a table, a third makes one table for each of its values.', bad: false };
  const m = { ...meta, id: f.strategy };
  const err = X.gridProblems(f, m, rows);
  if (err) return { note: err, bad: true };
  const g = X.gridAxes(rows, m, f.max_cells);
  const n = X.gridCount(g.axes);
  return { note: `${n} run${n === 1 ? '' : 's'}${n > X.DEFAULT_MAX_CELLS ? ' — a long wait' : ''}`, bad: false, n };
}
function heatPickHtml(f, meta, h) {
  const strat = meta.inputs || [];
  const ctl = X.ctlAxisInputs(meta);
  const opt = (i, cur) => `<option value="${esc(i.key)}"${i.key === cur ? ' selected' : ''}>${esc(i.label)}</option>`;
  return HEAT_ROLES.map((role, k) => {
    const r = h.rows[k], inp = r.key ? X.axisInput(meta, r.key) : null;
    const hint = inp ? `${X.axisHint(inp)}${HEAT_ZERO[inp.key] ? ` · 0 = ${HEAT_ZERO[inp.key]}` : ''}` : '';
    return `<label>${role}</label>
      <select data-hk="${k}"><option value="">${k === 2 ? 'None (optional)' : 'Pick a setting'}</option>
        ${strat.length ? `<optgroup label="Strategy settings">${strat.map((i) => opt(i, r.key)).join('')}</optgroup>` : ''}
        <optgroup label="Trade rules">${ctl.map((i) => opt(i, r.key)).join('')}</optgroup></select>
      ${inp ? `<input type="text" class="heat-vals" data-ht="${k}" value="${esc(r.text)}" placeholder="${esc(heatSuggest(inp))}" spellcheck="false" autocomplete="off">
        <div class="heat-hint">${esc(hint)}</div>` : ''}`;
  }).join('');
}
function heatSettingsHtml(f, meta) {
  const h = heatState(f), chk = heatCheck(f, meta, h), busy = heatBusy(h);
  const picked = h.rows.filter((r) => r.key).map((r) => (X.axisInput(meta, r.key) || {}).label).filter(Boolean);
  return `<details class="rs-group rs-set rs-heat"${S.heatOpen ? ' open' : ''}><summary><span>Heat map</span><span>${picked.length ? esc(picked.join(' × ')) : 'off'}</span></summary>
    <div class="grid heat-grid">${heatPickHtml(f, meta, h)}
      <div class="sep"></div>
      <div class="heat-note${chk.bad ? ' bad' : ''}" id="heatNote">${esc(chk.note)}</div>
      <button class="btn btn-sm btn-outline heat-exit" data-act="exitlab"${busy ? ' disabled' : ''} title="Fill the heat map with exits to try on this strategy: breakeven × trailing stop × own vs candle stop">Exit lab</button>
      <button class="btn btn-sm heat-run" data-act="${busy ? 'heatcancel' : 'heatrun'}" id="heatBtn"${!busy && (chk.bad || !chk.n) ? ' disabled' : ''}>${busy ? 'Cancel' : 'Run heat map'}</button>
    </div>
    <div class="heat-res" id="heatRes">${heatResHtml(f, meta)}</div></details>`;
}
/* the table(s): one per value of Panels; a cell is net $ (tone by sign, depth by size), a click puts that run on the chart */
function heatResHtml(f, meta) {
  const h = heatState(f), g = h.grid;
  if (h.err) return `<div class="heat-err">${esc(h.err)}</div>`;
  if (h.starting && !g) return '<div class="heat-prog">Starting…</div>';
  if (!g) return '';
  const pr = X.gridProgress(g), maxAbs = X.heatMaxAbs(g), bad = (g.cells || []).filter((c) => c.status === 'error');
  const prog = `<div class="heat-prog"><span>${esc(pr.text)}</span>${pr.final ? '' : `<span class="rs-bar${pr.frac == null ? ' ind' : ''}"><i style="width:${pr.frac == null ? 38 : Math.round(pr.frac * 100)}%"></i></span>`}</div>`;
  if (!g.axes || g.axes.length < 2) return prog;
  const panels = X.heatPanels(g);
  const tables = panels.map((pn) => `<div class="heat-panel">${pn.title ? `<div class="heat-title">${esc(pn.title)}</div>` : ''}
    <div class="heat-corner"><span>${esc(pn.rowLabel)} ↓</span><span>${esc(pn.colLabel)} →</span></div>
    <table class="heat-tbl"><thead><tr><th></th>${pn.cols.map((c) => `<th>${esc(c)}</th>`).join('')}</tr></thead><tbody>
      ${pn.rows.map((rl, r) => `<tr><th>${esc(rl)}</th>${pn.cells[r].map((ci) => {
        const c = g.cells[ci], v = X.cellView(c), lvl = X.heatLevel(c && c.summary ? c.summary.net_profit : null, maxAbs);
        const sel = h.cell === ci ? ' sel' : '';
        return `<td><button class="heat-c ${v.tone}${sel}" data-act="heatcell" data-i="${ci}" title="${esc(v.title)}"${lvl.alpha ? ` style="--a:${lvl.alpha}"` : ''}${c && c.status === 'done' ? '' : ' disabled'}>
          <b>${esc(v.net)}</b>${v.sharpe ? `<small>${esc(v.sharpe)}</small>` : ''}</button></td>`;
      }).join('')}</tr>`).join('')}</tbody></table></div>`).join('');
  const looks = g.looks != null ? `<div class="heat-looks">${esc(X.looksLine(g.looks, g.looks_error))}</div>` : '';
  return `${prog}${tables}${bad.length ? `<div class="heat-err">${bad.length} cell${bad.length === 1 ? '' : 's'} failed: ${esc(bad[0].error || 'error')}</div>` : ''}${looks}
    <div class="heat-foot">Average of the whole table is the answer, not the best cell.</div>`;
}
/* paint only the heat block + its note/button: a poll must not redraw the pane (it would take the focus out of a text box) */
function heatPaint() {
  const b = buf(), f = b && formOf(b), meta = b && metaOf(b);
  if (!f || !meta) return;
  const h = heatState(f), chk = heatCheck(f, meta, h), busy = heatBusy(h);
  const note = $('#heatNote'), btn = $('#heatBtn'), res = $('#heatRes');
  if (note) { note.textContent = chk.note; note.classList.toggle('bad', !!chk.bad); }
  if (btn) { btn.textContent = busy ? 'Cancel' : 'Run heat map'; btn.dataset.act = busy ? 'heatcancel' : 'heatrun'; btn.disabled = !busy && (chk.bad || !chk.n); }
  if (res) res.innerHTML = heatResHtml(f, meta);
}
async function heatRun() {
  const b = buf();
  if (!b || (S.busy && S.active && S.active.key === b.key)) return;
  if (b.kind !== 'builtin') {
    if (!b.code.trim()) return;
    const v = await validateNow(b);
    if (!v || !v.ok) { log(`<span class="err">Fix the script first: ${esc(C.statusOf(v).text)}</span>`); return; }
    if (isDirty(b) || b.kind === 'new') { if (!(await save(b))) return; }
  }
  const nb = buf(), f = formOf(nb), meta = { ...metaOf(nb), id: f.strategy };
  const h = heatState(f), err = X.gridProblems(f, meta, h.rows);
  if (err) { log(`<span class="err">${esc(err)}</span>`); return; }
  const bodyObj = X.gridBody(f, X.gridAxes(h.rows, meta, f.max_cells).axes);
  const token = ++h.token;
  h.err = ''; h.starting = true; h.grid = null; h.cell = null;
  heatPaint();
  const r = await send('POST', '/api/tester/grid', bodyObj);
  if (token !== h.token) return;
  if (!r.ok) { h.starting = false; h.err = r.error || 'request failed'; heatPaint(); return; }
  h.id = r.json.id;
  log(`Heat map of <b>${esc(nb.kind === 'builtin' ? nb.id : nb.name)}</b>: ${esc(String(X.gridCount(X.gridAxes(h.rows, meta, f.max_cells).axes)))} runs inside the sandbox…`);
  heatPoll(h, token);
}
async function heatPoll(h, token) {
  let lost = 0;
  while (token === h.token) {
    const r = await send('GET', `/api/tester/grid/${encodeURIComponent(h.id)}`);
    if (token !== h.token) return;
    if (r.ok) {
      lost = 0; h.starting = false; h.grid = r.json; h.err = '';
      heatPaint();
      if (X.gridProgress(r.json).final) {
        const done = (r.json.cells || []).filter((c) => c.status === 'done').length;
        log(`Heat map ${r.json.status === 'cancelled' ? 'cancelled' : 'done'} · <b>${done} of ${(r.json.cells || []).length} runs</b>`);
        return;
      }
    } else if (++lost > 8) { h.starting = false; h.err = `lost contact with the heat map: ${r.error || 'unknown'}`; heatPaint(); return; }
    await new Promise((res) => setTimeout(res, 700));
  }
}
async function heatCancel() {
  const b = buf(), f = b && formOf(b);
  if (!f) return;
  const h = heatState(f);
  if (h.id && h.grid && !X.gridProgress(h.grid).final) await send('POST', `/api/tester/grid/${encodeURIComponent(h.id)}/cancel`);
}
/* a cell becomes the open run: its numbers fill the pane, its trades go on the chart */
async function heatCell(i) {
  const b = buf(), f = b && formOf(b);
  if (!f) return;
  const h = heatState(f), g = h.grid;
  if (!g || !g.cells[i] || g.cells[i].status !== 'done') return;
  h.cell = i; heatPaint();
  const r = await send('GET', `/api/tester/grid/${encodeURIComponent(h.id)}/cell/${i}/bundle`);
  if (!r.ok || h.cell !== i) { if (!r.ok) log(`<span class="err">Could not load that run: ${esc(r.error)}</span>`); return; }
  const labels = g.axes.map((a, k) => `${a.label} ${X.axisLabels(a)[g.cells[i].coords[k]]}`).join(' · ');
  S.run = { key: b.key, rid: `${h.id}-c${i}`, st: { status: 'done' }, bundle: r.json, strategy: f.strategy, grid: { id: h.id, cell: i }, cellLabel: labels };
  shownRid = null;
  paintRes();
  if (P.chart) showOnChart(false); else log(`Heat-map run: <b>${esc(labels)}</b> · <a data-act="show">Show trades on the chart ›</a>`);
}
/* ---- Walk-forward (the owner, 2026-10-18): the heat map's settings searched block by block. 3:1 picks the best cell on 3
   whole months and trades it the next 1, then the next block (never rolling); 1:N picks on 1 month and trades the next N. It runs over the
   Range's two 3:1 choices, over all the data (the owner's window). The words are tester.js (wfBody, wfTiles, wfStepRows, ...); the
   server is /api/tester/walkforward. */
const WF_EMPTY = '<div class="rs-empty"><h3>No walk-forward yet</h3><p>Run it to split the data into blocks: 3 months in-sample, the next 1 out-of-sample, then the next block. To let each block pick the best setting, choose what to vary in Heat map below.</p></div>';
/* The Range list's two 3:1 choices (the owner, 2026-10-18): one walk-forward over all the data, seen from either side --
   in-sample = the 3-month windows the picks were made on, out-of-sample = each next month, traded on that pick. */
const WF_RANGE_OPTS = [['wf31_is', '3:1 in-sample'], ['wf31_oos', '3:1 out-of-sample'], ['wf31_both', '3:1 in + out-of-sample'],
  ['wf31r_both', '3:1 rolling · in + out-of-sample']];
const WF_SIDE_TEXT = { is: 'in-sample', oos: 'out-of-sample', both: 'in + out-of-sample' };
const wfSide = (f) => (WF_SIDE_TEXT[f.range.side] ? f.range.side : 'oos');
const wfRolling = (r) => !!(r && r.wf === X.WF_ROLL && r.step === 1);
const wfRangeVal = (r) => (r && r.wf === X.WF_ROLL ? (wfRolling(r) ? 'wf31r_both' : `wf31_${WF_SIDE_TEXT[r.side] ? r.side : 'oos'}`) : '');
/* Blocks are ALWAYS the default (the owner, 2026-10-18); rolling is only ever picked by hand, here or by asking Claude. */
function wfLabState(f) {
  return S.wf[f.strategy] || (S.wf[f.strategy] = { job: null, result: null, id: '', token: 0, starting: false, err: '' });
}
const wfLabBusy = (w) => w.starting || (w.job && !X.wfProgress(w.job).final);
/* The walk-forward's result, laid out like a run (the owner, 2026-10-18: "i liked how it was before"): the net, the curve, the
   numbers, then grouped rows. Out-of-sample = each test month traded on the pick from the 3 months before it; in-sample = the
   blocks those picks were made on; both = the two side by side, the in-sample curve the quieter line. */
const wfKv = (k, v, tone = '') => `<div class="rs-kv"><span>${esc(k)}</span><b class="${tone}">${esc(v)}</b></div>`;
const wfTone = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');
const WF_MON = new Intl.DateTimeFormat('en-US', { timeZone: 'UTC', month: 'short', year: 'numeric' });
const wfMon = (ym) => { const m = /^(\d{4})-(\d\d)$/.exec(ym || ''); return m ? WF_MON.format(new Date(Date.UTC(+m[1], +m[2] - 1, 15))) : ym || ''; };
function wfSplitHtml(r) {
  if (!r.split) return '';
  const b = r.split.build, u = r.split.unseen;
  const row = (k, f, t) => `<div class="rs-kv wf-kv2"><span>${esc(k)}</span><b class="${t ? wfTone(t(b)) : ''}">${esc(f(b))}</b><b class="${t ? wfTone(t(u)) : ''}">${esc(f(u))}</b></div>`;
  const pm = (s) => (s.per_month ? s.per_month.net_profit : null);
  return `<div class="rs-gh">Build and unseen days</div><div class="rs-group">
    <div class="rs-kv wf-kv2 wf-kvh"><span></span><span title="${esc(b.n_months ? `${b.months[0]} → ${b.months[b.months.length - 1]}` : '')}">Build</span><span title="${esc(u.n_months ? `${u.months[0]} → ${u.months[u.months.length - 1]}` : '')}">Unseen</span></div>
    ${row('Months', (s) => String(s.n_months || 0))}
    ${row('Net / month', (s) => (pm(s) == null ? '—' : money0(pm(s))), pm)}
    ${row('Total net', (s) => money0(s.stats.net_profit || 0), (s) => s.stats.net_profit)}
    ${row('Profit factor', (s) => X.num(s.stats.profit_factor, 2, true))}
    ${row('Win rate', (s) => X.rate(s.stats.win_rate))}
    ${row('Max drawdown', (s) => (s.stats.max_drawdown == null ? '—' : money0(s.stats.max_drawdown)))}</div>`;
}
/* What to trade now: the best of the searched settings on the last 3 whole months -- the setting the Desk would tell the owner
   to switch to. Under it, how often the pick moved from block to block, and the blocks where no setting had enough trades. */
function wfPickRows(r, axes) {
  if (!axes || !axes.length) return '';                  // the strategy as set: nothing was chosen
  const n = r.next, st = r.stability || {};
  const pick = !n ? '—' : !n.params ? 'No setting (too few trades on those months)' : (axes || []).map((a) => `${a.label} ${X.valueLabel(n.params[a.key])}`).join(' · ');
  return `<div class="rs-gh">${esc(n ? `What to trade in ${wfMon(n.for)}` : 'What to trade now')}</div><div class="rs-group">
    <div class="rs-kv wf-pick"><span>${esc(pick)}</span></div>
    ${n ? wfKv('Best on', `${wfMon(n.select_ms[0])} – ${wfMon(n.select_ms[n.select_ms.length - 1])}`) : ''}
    ${wfKv('Pick changed', `${st.changes ?? 0} of ${st.pairs ?? 0} blocks`)}
    ${wfKv('Blocks with no pick', String(st.no_pick ?? 0))}</div>`;
}
function wfStepsHtml(r, axes) {
  const rows = X.wfStepRows(r, axes);
  return `<details class="rs-group rs-set wf-steps-box"${S.wfStepsOpen ? ' open' : ''}><summary><span>Block by block</span><span>${r.n_steps} blocks</span></summary>
    <div class="wf-scroll"><table class="heat-tbl wf-steps"><thead><tr>${X.WF_STEP_HEADERS.map((h) => `<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>
    ${rows.map((row) => `<tr>${row.cells.map((c, i) => `<td class="${i === 3 ? row.isTone : i === 6 ? row.oosTone : ''}">${esc(c)}</td>`).join('')}</tr>`).join('')}
    </tbody></table></div></details>`;
}
/* blocks and rolling are different runs: a result shows only under the Range choice it was run for */
const wfJobFits = (f, job) => !job || !job.walkforward || (job.walkforward.step_months === 1) === wfRolling(f.range);
function wfResHtml(f) {
  const w = wfLabState(f);
  if (!wfJobFits(f, w.job) && !w.starting) return '';
  const job = w.job, r = w.result;
  if (w.err) return `<div class="rs-empty"><h3>The walk-forward failed</h3><p>${esc(w.err)}</p></div>`;
  if (w.starting && !job) return '<div class="rs-prog"><div class="t">Starting the walk-forward…</div><div class="rs-bar ind"><i style="width:38%"></i></div></div>';
  if (!job) return '';
  const pr = X.wfProgress(job);
  if (!r) {
    return `<div class="rs-prog"><div class="t">${esc(pr.text)}</div>${pr.final ? '' : `<div class="rs-bar${pr.frac == null ? ' ind' : ''}"><i style="width:${pr.frac == null ? 38 : Math.round(pr.frac * 100)}%"></i></div>
      <button class="btn btn-outline btn-sm" data-act="wfcancel">Cancel</button>`}</div>`;
  }
  const axes = job.axes || [], side = wfSide(f), so = r.stitched, si = r.stitched_is;
  const one = side === 'is' ? si : so, s = one.stats, pm = one.per_month || {};
  const span = (x) => (x.months && x.months.length ? ` (${wfMon(x.months[0])} – ${wfMon(x.months[x.months.length - 1])})` : '');
  const amt = (v) => `${v > 0 ? 'Up' : v < 0 ? 'Down' : 'Flat at'} <b>$${Math.abs(Math.round(v || 0)).toLocaleString('en-US')}</b>`;
  const hero = s.net_profit || 0;
  const take = side === 'is'
    ? `${amt(hero)} over <b>${one.n_months} months</b>${esc(span(one))}: ${r.n_cells > 1 ? 'the months the picks were made on' : 'the in-sample months'}.`
    : side === 'both'
      ? (r.scheme.rolling
        ? `Out-of-sample ${amt(so.stats.net_profit)} over ${so.n_months} months, each traded on the best setting of the 3 months before it. In-sample ${amt((si.per_month || {}).net_profit)} a month on those windows (they overlap, so no total).`
        : `<span class="wf-key oos"></span>Out-of-sample ${amt(so.stats.net_profit)} over ${so.n_months} months · <span class="wf-key is"></span>in-sample ${amt(si.stats.net_profit)} over ${si.n_months} months.`)
      : `${amt(hero)} over <b>${one.n_months} months</b>${esc(span(one))}, each traded on the pick from the 3 months before it.`;
  const rr = (x) => x.rr_label || (x.rr == null ? '—' : `1:${Number(x.rr).toFixed(2)}`);
  const d = r.drop || {};
  const head = `<div class="rs-hero"><div class="rs-net"><i>${hero > 0 ? '+' : hero < 0 ? MINUS : ''}$</i>${esc(Math.abs(Math.round(hero)).toLocaleString('en-US'))}</div>${side === 'both' ? '<span class="rs-delta neg">out-of-sample</span>' : ''}</div>
    <div class="rs-take">${take}</div>
    <div class="eqw" id="eqw"><svg preserveAspectRatio="none" role="img" aria-label="Walk-forward equity curve, after fees"></svg><div class="eq-rule" id="eqRule"></div><span class="eq-dot" id="eqDot"></span>
      <span class="eq-tag" id="eqHi"></span><span class="eq-tag" id="eqLo"></span><div class="eq-tip" id="eqTip"></div><div class="eq-ax" id="eqAx"></div></div>`;
  if (side === 'both') {
    const row = (k, f, t) => `<div class="rs-kv wf-kv2"><span>${esc(k)}</span><b class="${t ? wfTone(t(si)) : ''}">${esc(f(si))}</b><b class="${t ? wfTone(t(so)) : ''}">${esc(f(so))}</b></div>`;
    const net = (x) => x.stats.net_profit, pmn = (x) => (x.per_month || {}).net_profit;
    const ov = (x) => x === si && r.scheme.rolling;          // rolling's in-sample windows overlap: no months / total / trade count
    return `${head}<div class="rs-gh">In-sample and out-of-sample</div><div class="rs-group">
      <div class="rs-kv wf-kv2 wf-kvh"><span></span><span>In</span><span>Out</span></div>
      ${row('Months', (x) => (ov(x) ? '—' : String(x.n_months || 0)))}${row('Net / month', (x) => money0(pmn(x) || 0), pmn)}${row('Total net', (x) => (ov(x) ? '—' : money0(net(x) || 0)), (x) => (ov(x) ? null : net(x)))}
      ${row('Trades', (x) => (ov(x) ? '—' : String(x.stats.trades ?? '—')))}${row('Profit factor', (x) => X.num(x.stats.profit_factor, 2, true))}
      ${row('Win rate', (x) => X.rate(x.stats.win_rate))}${row('Realized RR', (x) => rr(x.stats))}
      ${row('Max drawdown', (x) => (x.stats.max_drawdown == null ? '—' : money0(x.stats.max_drawdown)), (x) => x.stats.max_drawdown)}
      ${row('Sharpe', (x) => X.num(x.stats.sharpe))}</div>
      ${wfSplitHtml(r)}${wfPickRows(r, axes)}${wfStepsHtml(r, axes)}
      <div class="heat-foot">${esc(r.n_cells > 1 ? `${r.n_cells} settings searched · ${r.looks} looks counted` : 'The strategy as set: nothing searched')}</div>`;
  }
  return `${head}
    <div class="rs-trio"><div><b>${esc(X.num(s.profit_factor, 2, true))}</b><span>Profit factor</span></div><div><b>${esc(X.rate(s.win_rate))}</b><span>Win rate</span></div><div><b>${esc(rr(s))}</b><span>Realized RR</span></div><div><b>${esc(X.num(s.sharpe))}</b><span>Sharpe</span></div></div>
    ${side === 'is' ? '' : wfSplitHtml(r)}
    <div class="rs-gh">Per month</div><div class="rs-group">
      ${wfKv('Net / month', money0(pm.net_profit || 0), wfTone(pm.net_profit))}${wfKv('Trades / month', X.num(pm.trades, 1))}
      ${wfKv('Max drawdown', s.max_drawdown == null ? '—' : money0(s.max_drawdown), wfTone(s.max_drawdown))}
      ${d.net_profit_per_month == null ? '' : wfKv('Out-of-sample vs in-sample', `${money0(d.net_profit_per_month)} a month`, wfTone(d.net_profit_per_month))}</div>
    ${wfPickRows(r, axes)}
    ${wfStepsHtml(r, axes)}
    <div class="heat-foot">${esc(r.n_cells > 1 ? `${r.n_cells} settings searched · ${r.looks} looks counted` : 'The strategy as set: nothing searched')}</div>`;
}
function wfPaint() {
  const b = buf(), f = b && formOf(b), meta = b && metaOf(b);
  if (!f || !meta) return;
  const w = wfLabState(f), busy = wfLabBusy(w), chk = heatCheck(f, meta, heatState(f));
  const res = $('#wfRes');
  if (res) res.innerHTML = wfResHtml(f) || WF_EMPTY;
}
async function wfRun() {
  const b = buf();
  if (!b || (S.busy && S.active && S.active.key === b.key)) return;
  if (b.kind !== 'builtin') {
    if (!b.code.trim()) return;
    const v = await validateNow(b);
    if (!v || !v.ok) { log(`<span class="err">Fix the script first: ${esc(C.statusOf(v).text)}</span>`); return; }
    if (isDirty(b) || b.kind === 'new') { if (!(await save(b))) return; }
  }
  const nb = buf(), f = formOf(nb), meta = { ...metaOf(nb), id: f.strategy };
  if (!f.range.wf) return;
  const h = heatState(f), w = wfLabState(f), search = h.rows.some((r) => r.key);
  const err = search ? X.gridProblems(f, meta, h.rows) : X.problems(f, meta);   // no heat-map settings: the strategy as set
  if (err) { log(`<span class="err">${esc(err)}</span>`); return; }
  const bodyObj = X.wfBody(f, search ? X.gridAxes(h.rows, meta, f.max_cells).axes : [], 'net_profit', 5);
  const token = ++w.token;
  w.err = ''; w.starting = true; w.job = null; w.result = null; S.wfStepsOpen = false;
  wfPaint();
  const r = await send('POST', '/api/tester/walkforward', bodyObj);
  if (token !== w.token) return;
  if (!r.ok) { w.starting = false; w.err = r.error || 'request failed'; wfPaint(); return; }
  w.id = r.json.id;
  log(`Walk-forward ${esc(X.wfRatioText(f.range.wf))} of <b>${esc(nb.kind === 'builtin' ? nb.id : nb.name)}</b> over ${esc(X.pillLabel(f.range))}: every cell runs once, then each month is picked…`);
  wfPoll(w, token);
}
async function wfPoll(w, token) {
  let lost = 0;
  while (token === w.token) {
    const r = await send('GET', `/api/tester/walkforward/${encodeURIComponent(w.id)}`);
    if (token !== w.token) return;
    if (r.ok) {
      lost = 0; w.starting = false; w.job = r.json; w.err = '';
      if (X.wfProgress(r.json).final) {
        if (r.json.status === 'done') {
          const res = await send('GET', `/api/tester/walkforward/${encodeURIComponent(w.id)}/result`);
          if (token !== w.token) return;
          if (res.ok) w.result = res.json; else w.err = `could not load the walk-forward result: ${res.error || 'unknown'}`;
        }
        paintRes();          // the whole view: the net, the curve, the rows
        log(`Walk-forward ${esc(r.json.status)}${w.result ? ` · out-of-sample <b>${esc(money0(w.result.stitched.stats.net_profit || 0))}</b>` : ''}`);
        return;
      }
      wfPaint();
    } else if (++lost > 8) { w.starting = false; w.err = `lost contact with the walk-forward: ${r.error || 'unknown'}`; wfPaint(); return; }
    await new Promise((res) => setTimeout(res, 1500));
  }
}
async function wfCancel() {
  const b = buf(), f = b && formOf(b);
  if (!f) return;
  const w = wfLabState(f);
  if (w.id && w.job && !X.wfProgress(w.job).final) await send('POST', `/api/tester/walkforward/${encodeURIComponent(w.id)}/cancel`);
}
/* ---- Trade rules (2026-10-12): the engine's run controls (backtest/controls.py, mirrored in tester.js) as a settings group.
   Off by default; they hold for every strategy here, whatever its code does. A mode select repaints so only the number it
   reads shows; every number field blank = that rule off. */
const RULE_AUX = new Set(['stop_pts', 'stop_atr', 'target_pts', 'target_atr', 'target_rr', 'atr_minutes', 'atr_period', 'stop_candle_ticks',
  'be_offset_ticks', 'trail_after_pts', 'exit_line_min']);
function rulesHtml(f, meta) {
  const raw = f.controls || {}, c = X.controlsClean(raw), D = X.CONTROLS;
  const n = Object.keys(c).filter((k) => !RULE_AUX.has(k)).length;
  const num = (k, label, hint, step = 1) => `<label title="${esc(hint)}">${esc(label)}</label><input type="number" data-c="${k}" value="${raw[k] == null ? '' : esc(raw[k])}" placeholder="off" min="0" step="${step}">`;
  const time = (k, label, hint) => `<label title="${esc(hint)}">${esc(label)}</label><input type="time" data-c="${k}" value="${esc(raw[k] || '')}">`;
  const sel = (k, label, opts, hint = '') => {
    const cur = String(c[k] === undefined ? D[k][1] : c[k]);
    return `<label title="${esc(hint)}">${esc(label)}</label><select data-c="${k}">${opts.map(([v, t]) => `<option value="${esc(v)}"${String(v) === cur ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select>`;
  };
  const stopMode = c.stop_mode || 'own', tgtMode = c.target_mode || 'own';
  const usesAtr = stopMode === 'atr' || tgtMode === 'atr';
  const sizes = (meta && meta.bar_sizes) || [];       // the signal bar sizes this strategy's logic can be read on
  const own = meta && meta.bar_minutes ? ` (${meta.bar_minutes} min)` : '';
  return `<details class="rs-group rs-set rs-rules"${S.rulesOpen ? ' open' : ''}><summary><span>Trade rules</span><span>${n ? `${n} set` : 'none'}</span></summary>
    <div class="grid">
      ${sizes.length ? sel('bar_minutes', 'Signal bar', [[0, `Strategy's own${own}`], ...sizes.map((m) => [m, `${m} minute${m === 1 ? '' : 's'}`])], 'The candle size the strategy reads its signals on') : ''}
      ${time('entry_from', 'Trade from (NY)', 'No entry before this time')}
      ${time('entry_to', 'Trade until (NY)', 'No new entry from this time; an order still waiting is cancelled, an open trade is left alone')}
      ${time('flat_at', 'Flat at (NY)', 'Cancels everything and closes what is open at this time; no entry after it')}
      ${sel('direction', 'Direction', [['both', 'Both'], ['long', 'Long only'], ['short', 'Short only']])}
      ${num('max_trades', 'Trades a day', 'The most entries in a day')}
      ${num('stop_wins', 'Stop after wins', 'No new entry once the day has this many winning trades')}
      ${num('stop_losses', 'Stop after losses', 'No new entry once the day has this many losing trades')}
      ${num('max_consec_losses', 'Losses in a row', 'No new entry after this many losing trades in a row')}
      ${num('day_loss', 'Daily loss ($)', 'No new entry once the day\'s closed P&L is down this much', 50)}
      ${num('day_profit', 'Daily profit ($)', 'No new entry once the day\'s closed P&L is up this much', 50)}
      ${num('cooldown_min', 'Cool off after a loss (min)', 'Minutes with no new entry after a losing trade')}
      ${num('max_hold_min', 'Close after (min held)', 'A trade open this long is closed at the next print')}
      <div class="sep"></div>
      ${sel('stop_mode', 'Stop', [['own', 'Strategy\'s own'], ['fixed', 'Fixed points'], ['atr', 'ATR multiple'], ['candle', 'Signal candle'], ['none', 'No stop']], 'Replaces the strategy\'s stop, measured from the fill')}
      ${stopMode === 'fixed' ? num('stop_pts', 'Stop (points)', 'Distance from the fill', 0.25) : stopMode === 'atr' ? num('stop_atr', 'Stop (× ATR)', 'Multiple of the ATR at the entry', 0.1)
        : stopMode === 'candle' ? num('stop_candle_ticks', 'Past the candle (ticks)', 'The stop sits this many ticks past the last closed signal candle\'s high / low', 1).replace('placeholder="off"', 'placeholder="0"') : ''}
      ${sel('target_mode', 'Target', [['own', 'Strategy\'s own'], ['fixed', 'Fixed points'], ['atr', 'ATR multiple'], ['rr', 'R multiple of the stop'], ['none', 'No target']], 'Replaces the strategy\'s target, measured from the fill')}
      ${tgtMode === 'fixed' ? num('target_pts', 'Target (points)', 'Distance from the fill', 0.25) : tgtMode === 'atr' ? num('target_atr', 'Target (× ATR)', 'Multiple of the ATR at the entry', 0.1) : tgtMode === 'rr' ? num('target_rr', 'Target (× stop)', 'Multiple of the stop distance', 0.25) : ''}
      <div class="sep"></div>
      ${num('be_after_pts', 'Breakeven after (points)', 'Once the trade is this far in profit, the stop moves to the fill + 1 tick (never looser)', 0.25)}
      ${num('be_offset_ticks', 'Breakeven + (ticks)', 'How far into profit the breakeven stop sits (used with Breakeven after)', 1).replace('placeholder="off"', 'placeholder="1"')}
      ${num('trail_pts', 'Trailing stop (points)', 'The stop follows the best price since the fill by this much, tick by tick, only tighter', 0.25)}
      ${num('trail_after_pts', 'Trail after (points)', 'Start trailing once the trade is this far in profit (empty: from the fill; used with Trailing stop)', 0.25).replace('placeholder="off"', 'placeholder="0"')}
      ${sel('exit_line', 'Exit on close through', [['', 'Off'], ['vwap', 'VWAP (from the Globex open)'], ['vwap_rth', 'VWAP (from 09:30)'], ['ema20', 'EMA 20'], ['ema50', 'EMA 50']], 'Close the trade when a bar closes back through this line: a long below it, a short above')}
      ${c.exit_line ? sel('exit_line_min', 'Exit line bars', [[1, '1 minute'], [5, '5 minutes'], [15, '15 minutes']], 'The bar the close is read on') : ''}
      ${usesAtr ? `${sel('atr_minutes', 'ATR bars', [[1, '1 minute'], [5, '5 minutes'], [15, '15 minutes']], 'The bar size the ATR is read on')}${num('atr_period', 'ATR length', 'Bars averaged: the mean true range of the last N closed bars before the entry', 1).replace('placeholder="off"', 'placeholder="14"')}` : ''}
    </div></details>`;
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
/* ---- Promote to Desk (2026-10-09) ----
   A draft that was backtested can go on the Desk page. It lands there switched off; switched on, the runner hosts it in SHADOW: it
   writes down its orders and nothing is sent. The chart service keeps a frozen copy of the code (POST /desklab/promote) and says what the Desk would refuse; this page only
   asks, and shows the answer. Which Lab strategies are on the Desk (GET /desklab) is asked when the Strategies list opens and after
   each action -- never on a timer. The pure half (the row's four states, the words) is labcode.js. */
async function hexSha(text) {        // the sha-256 the Desk keeps of the code it runs; '' where this browser cannot say
  try {
    const d = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(String(text)));
    return [...new Uint8Array(d)].map((x) => x.toString(16).padStart(2, '0')).join('');
  } catch (_) { return ''; }
}
const shaMemo = new Map(), shaAsked = new Set();
function shaNow(code) {              // the hash of saved code, once it is worked out (a repaint follows); '' until then
  if (code == null) return '';
  if (shaMemo.has(code)) return shaMemo.get(code);
  if (!shaAsked.has(code)) {
    shaAsked.add(code);
    hexSha(code).then((h) => {
      shaMemo.set(code, h);
      if (shaMemo.size > 6) { const old = shaMemo.keys().next().value; shaMemo.delete(old); shaAsked.delete(old); }
      paintRes();
    });
  }
  return '';
}
async function loadDesk() {
  const r = await send('GET', '/api/tester/desklab');
  if (!r.ok || !r.json) return;                      // the last list stays
  const key = (m) => JSON.stringify(m ? [...m].map(([n, x]) => [n, x.sha256, x.enabled, x.promoted_utc]).concat([[...S.deskBuiltins]]) : null);
  const was = key(S.desk);
  S.desk = new Map((r.json.strategies || []).filter((x) => x && x.name).map((x) => [x.name, x]));
  S.deskBuiltins = new Set((Array.isArray(r.json.builtins) ? r.json.builtins : []).filter((x) => typeof x === 'string'));      // the built-ins the Desk itself runs
  if (key(S.desk) === was) return;                   // nothing changed: the page stays as it is (a field being typed in is not rebuilt)
  paintLib(); paintRes();
  if (buf() && buf().kind === 'draft') paintEditor();          // its lock may have changed (promoted, or taken off the Desk)
}
/* The row under a finished run: its state, from what is open now (never from a remembered one). */
function deskState(b) {
  if (!b || b.kind !== 'draft') return null;
  const dirty = isDirty(b), sha = dirty ? '' : shaNow(b.code);
  const r = S.run && S.run.key === b.key && !S.run.grid ? S.run : null;      // (a heat-map cell has no run of its own to promote)
  /* the hash only tells the same code on the Desk from other code; it never gates Promote -- the Desk judges the run when it is asked */
  /* a written record's run is the research engine's, not the file's code: the Desk would refuse it (the file places no orders) */
  if (r && r.record) return { label: 'Promote to Desk', hint: RECORD_NO_DESK, disabled: true, action: null };
  return C.promoteState({ kind: 'draft', dirty, hasRun: !!(r && r.bundle && r.rid), row: (S.desk && S.desk.get(b.name)) || null, sha });
}
const RECORD_NO_DESK = 'Cannot go on the Desk: this file is a written record and places no orders. Rebuild the idea as a real strategy first.';
/* The hint of the row, as a line under the group: what a keyboard or a screen reader reaches (the row's title is for the mouse). */
function deskNote(b) {
  const st = deskState(b);
  return st ? `<div class="rs-take" id="deskHint">${esc(st.hint)}</div>${S.deskErr ? `<div class="rs-take err" role="alert">${esc(S.deskErr)}</div>` : ''}` : '';
}
function deskRows(b) {
  const st = deskState(b);
  if (!st) return '';
  const on = !!(S.desk && S.desk.has(b.name));
  return `<button class="rs-row" data-act="deskgo" data-fk="deskgo" aria-describedby="deskHint" title="${esc(st.hint)}"${st.disabled ? ' aria-disabled="true"' : ''}${S.deskBusy ? ' disabled' : ''}><span>${esc(st.label)}</span><span>›</span></button>`
    + (on ? `<button class="rs-row" data-act="deskoff" data-fk="deskoff" title="Takes it off the Desk. Its history is kept."${S.deskBusy ? ' disabled' : ''}><span>Remove from Desk</span><span>›</span></button>` : '');
}
function deskGo() {
  const b = buf(), st = deskState(b);
  if (!st || st.disabled || S.deskBusy) return;
  if (st.action === 'open') {      // the Desk page, where the page switcher already points, on this strategy
    const home = document.querySelector('#pgSw a[data-page="desk"]');
    if (home && home.href) location.href = `${home.href.split('#')[0]}#lab=${encodeURIComponent(b.name)}`;
    return;
  }
  if (st.action === 'promote') promoteToDesk(b);
}
async function promoteToDesk(b) {
  const r = S.run && S.run.key === b.key ? S.run : null;
  if (!r || !r.rid || !r.bundle || r.grid) return;      // a heat-map cell has no run of its own to promote
  S.deskBusy = true; S.deskErr = ''; paintRes();
  const a = await send('POST', '/api/tester/desklab/promote', { name: b.name, run_id: r.rid });
  S.deskBusy = false;
  const j = a.json || {};
  if (!a.ok || j.ok === false) { S.deskErr = String(j.detail || a.error || 'It did not work.'); log(`<span class="err">${esc(S.deskErr)}</span>`); }
  else for (const line of C.deskSaid(j)) log(esc(line));
  await loadDesk();
  paintRes(); paintLib();
}
function deskOffDialog() {
  const b = buf();
  if (!b || b.kind !== 'draft' || S.deskBusy) return;
  const name = b.name;
  const d = dialog(`<h2>Remove ${esc(name)} from the Desk?</h2><p>Its history is kept.</p>
    <div class="acts"><button class="btn btn-outline" data-x="cancel">Keep it</button><button class="btn btn-default" data-x="go">Remove</button></div>`);
  d.addEventListener('click', async (e) => {
    const x = e.target.closest('[data-x]');
    if (!x) return;
    closeDialog();
    if (x.dataset.x !== 'go') return;
    S.deskBusy = true; paintRes();
    const r = await send('POST', '/api/tester/desklab/remove', { name });
    S.deskBusy = false;
    const j = r.json || {};
    if (!r.ok || j.ok === false) log(`<span class="err">${esc(String(j.detail || r.error || 'It did not work.'))}</span>`);
    else log(`${esc(name)} is off the Desk. Its history is kept.`);
    await loadDesk();
    paintRes(); paintLib();
  });
}

function paintRes() {
  const el = $('#labRes .in');
  if (!el) return;
  const b = (S.run && S.run.pipe ? { key: S.run.key, kind: 'pipe', name: S.run.strategy, id: S.run.strategy } : null) || buf(), top = el.scrollTop;
  paintNav();
  if (!b) { el.innerHTML = '<div class="rs-empty rs-none"><h3>Backtest</h3><p>Pick a strategy, or paste one, to see how it would have done.</p></div>'; return; }
  const r = S.run && S.run.key === b.key ? S.run : null, settings = b.kind === 'pipe' ? '' : settingsHtml(b);
  let main = '', settingsDone = false;
  const wfF = b.kind === 'pipe' ? null : formOf(b);
  WFEQ = null; WFEQ2 = null;
  if (wfF && wfF.range.wf) {
    const wr = wfLabState(wfF).result, sd = wfSide(wfF);
    if (wr && wfJobFits(wfF, wfLabState(wfF).job)) { WFEQ = sd === 'is' ? wr.stitched_is.equity : wr.stitched.equity; WFEQ2 = sd === 'both' ? wr.stitched_is.equity : null; }
    main = `<div class="rs-h"><b>Walk-forward ${esc(X.wfRatioText(wfF.range.wf))}${wfRolling(wfF.range) ? ' rolling' : ''} · ${WF_SIDE_TEXT[wfSide(wfF)]}</b><span>All data</span></div>
      <div class="wf-main" id="wfRes">${wfResHtml(wfF) || WF_EMPTY}</div>`;
  } else if (r && !r.bundle && !r.dead && (S.busy || (r.st && r.st.status === 'queued'))) {
    const p = X.progress(r.st || { status: 'queued' }), ind = p.frac == null;
    main = `<div class="rs-h"><b>Backtest</b></div><div class="rs-prog"><div class="t">${esc(p.text || 'Starting…')}</div><div class="rs-bar${ind ? ' ind' : ''}"><i style="width:${ind ? 38 : Math.round(p.frac * 100)}%"></i></div>
      <button class="btn btn-outline btn-sm" data-act="cancel">Cancel</button></div>`;
  } else if (r && r.bundle) {
    const run = r.bundle.run, a = run.report.summary.all, tl = X.tiles(run), by = (l) => tl.find((t) => t.label === l) || { value: '—' };
    const netv = a.net_profit || 0, pos = netv > 0, n = a.trades ?? 0, cap = run.capital || 0, pctv = cap ? netv / cap * 100 : null;
    const badges = X.badges(run).filter((x) => x.tone !== 'info');
    const used = run.coverage && run.coverage.used !== run.coverage.sessions ? ` · ${run.coverage.used} of ${run.coverage.sessions} sessions` : '';
    const split = (v) => { const m = /^([+−-]?\$?)(.*?)(%?)$/.exec(String(v)); return m ? `${esc(m[2])}${m[3] ? '<small>%</small>' : ''}` : esc(v); };
    main = `<div class="rs-h"><b>Backtest</b><span>${esc(r.cellLabel ? r.cellLabel : rangeText(run.range))}</span></div>
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
        <button class="rs-row" data-act="allmetrics"><span>All metrics</span><span>›</span></button>
        <button class="rs-row" data-act="report"><span>${root.dataset.report === '1' && P.chart ? 'Hide the full report' : 'Full report'}</span><span>›</span></button>
        ${b.kind === 'pipe' ? '' : `<button class="rs-row" data-act="review"${b.kind === 'builtin' ? ' disabled' : ''}><span>Request a review</span><span>›</span></button>${deskRows(b)}`}</div>${b.kind === 'pipe' ? '' : deskNote(b)}`;
    settingsDone = true;
  } else if (r && r.st && (r.st.status === 'error' || r.st.status === 'cancelled')) {
    main = `<div class="rs-empty"><h3>${r.st.status === 'cancelled' ? 'Cancelled' : 'The run failed'}</h3><p>${esc(r.st.error || (r.st.status === 'cancelled' ? 'Run it again when you are ready.' : 'See the line under the editor.'))}</p></div>`;
  } else if (b.kind !== 'builtin' && b.kind !== 'pipe' && /BLUEPRINT RECORD/.test(b.code || '')) {
    main = `<div class="rs-empty"><h3>A written record</h3><p>This file is the card and verdict of an idea the research engine already ran. It places no trades here, so Run has nothing to run. Run shows the idea's saved research-engine run when one with trades exists.</p></div>`;
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
  else if (name === 'heatrun') heatRun();
  else if (name === 'exitlab') exitLab();
  else if (name === 'heatcancel') heatCancel();
  else if (name === 'wfrun') wfRun();
  else if (name === 'wfcancel') wfCancel();
  else if (name === 'heatcell') heatCell(Number(el.dataset.i));
  else if (name === 'show') showOnChart(false);
  else if (name === 'report') { if (root.dataset.report === '1' && P.chart) setReport(false); else showOnChart(true); }
  else if (name === 'allmetrics') allMetricsDialog();
  else if (name === 'review') reviewDialog();
  else if (name === 'deskgo') deskGo();
  else if (name === 'deskoff') deskOffDialog();
  else if (name === 'save') save(b);
  else if (name === 'unlock' && b) { S.unlocked.add(b.name); log('Unlocked. The copy on the Desk does not change until you promote it again.'); paintLib(); paintEditor(); }
  else if (name === 'lock' && b) { S.unlocked.delete(b.name); paintLib(); paintEditor(); }
  else if (name === 'fold') foldGroup(el);
  else if (name === 'file') fileMenu(el);
  else if (name === 'group') groupMenu(el);
  else if (name === 'view') setView(el.dataset.v);
  else if (name === 'viewmenu') { if (menuEl && menuEl.dataset.for === 'view') closeMenu(); else viewMenu(el); }
  else if (name === 'plctl') { const c = S.pl && S.pl.data ? C.plControl(S.pl.data) : null; if (c && c.enabled) pipeActions(c.actions); }
  else if (name === 'plfilter') { S.plFilter = el.dataset.f || 'all'; paintLib(); }
  else if (name === 'plmode') pickMode(el.dataset.m);
  else if (name === 'plidea') pickIdea(el.dataset.name);
  else if (name === 'plbook') pickCard(el.dataset.name);
  else if (name === 'plapprove') approveIdea();
  else if (name === 'plrefuse') refuseSheet(S.plIdea);
  else if (name === 'pladd') addSheet();
  else if (name === 'plhide') { S.plSaid = null; paintLib(); }
  else if (name === 'plexec') showExecutions(el.dataset.name);
  else if (name === 'tkblock') codeSheet(el.dataset.id);
}
root.addEventListener('click', (e) => {
  if (inChart(e)) return;
  const lib = e.target.closest('[data-key]');
  if (lib) {
    const k = lib.dataset.key;
    S.listFocus = true;
    const go = S.view === 'lib' ? C.rowClick({ picks: S.picks, anchor: S.anchor, cur: S.cur }, shownList(), k, { shift: e.shiftKey, meta: e.metaKey || e.ctrlKey }) : { picks: [], anchor: k, open: true };
    S.picks = go.picks; S.anchor = go.anchor;
    if (!go.open) { paintLib(); return; }                        // a shift- or cmd-click picks rows and opens nothing
    if (k.startsWith('d:')) selectDraft(k.slice(2)); else if (k.startsWith('b:')) selectBuiltin(k.slice(2)); else { S.cur = k; S.run = null; paintAll(); }
    paintLib();
    return;
  }
  const a = e.target.closest('[data-act]');
  if (a) act(a.dataset.act, a);
});
const bar = document.querySelector('.lab-bar');
if (bar) {
  bar.addEventListener('click', (e) => { const a = e.target.closest('[data-act]'); if (a) act(a.dataset.act, a); });
  bar.addEventListener('input', (e) => { const b = buf(); if (e.target.id === 'edName' && b) { b.name = e.target.value.trim(); e.target.classList.remove('bad'); paintLib(); } });
  bar.addEventListener('keydown', (e) => { if (e.target.id === 'edName' && e.key === 'Enter' && !e.repeat) { e.preventDefault(); save(buf()); } });
}
root.addEventListener('toggle', (e) => {
  const cl = e.target.classList;
  if (cl && cl.contains('rs-rules')) S.rulesOpen = e.target.open;
  else if (cl && cl.contains('rs-heat')) S.heatOpen = e.target.open;
  else if (cl && cl.contains('wf-steps-box')) S.wfStepsOpen = e.target.open;
  else if (cl && cl.contains('rs-inputs')) S.inOpen = e.target.open;
  else if (cl && cl.contains('rs-set')) S.setOpen = e.target.open;
}, true);
root.addEventListener('input', (e) => {
  if (inChart(e)) return;
  const b = buf(), t = e.target;
  if (t.id === 'libQ') { S.libQ = t.value; paintLibList(); return; }
  if (t.id === 'libSort' || t.id === 'libShow' || t.id === 'libMkt') { setListView({ libSort: 'sort', libShow: 'show', libMkt: 'market' }[t.id], t.value); return; }
  if (t.id === 'tkQ') { S.tkQ = t.value; const l = $('#tkList'); if (l) l.innerHTML = toolkitList(); return; }
  if (t.id === 'edTa' && b && b.kind !== 'builtin' && !locked(b)) {
    const wasEmpty = !b.code.trim();
    b.code = t.value; b.valid = b.valid && b.valid.ok ? { ...b.valid, stale: true } : null;
    if (b.kind === 'new' && wasEmpty && b.code.trim() && !b.name) { b.name = C.suggestName(b.code, takenNames()); const n = document.getElementById('edName'); if (n) n.value = b.name; }
    paintCode(); paintHead(); queueValidate(b); paintLib();
  } else if (t.dataset.hk !== undefined || t.dataset.ht !== undefined) {
    const f = b && formOf(b), meta = b && metaOf(b);
    if (!f || !meta) return;
    const h = heatState(f);
    if (t.dataset.hk !== undefined) {
      const row = h.rows[Number(t.dataset.hk)];
      row.key = t.value;
      row.text = t.value ? heatSuggest(X.axisInput({ ...meta, id: f.strategy }, t.value)) : '';      // a pick brings values to start from
      paintRes();
    } else {
      h.rows[Number(t.dataset.ht)].text = t.value;
      heatPaint();
    }
  } else if (t.dataset.f || t.dataset.in || t.dataset.c) {
    const f = formOf(b), meta = metaOf(b);
    if (!f) return;
    if (t.dataset.c) {
      f.controls = X.setControl(f.controls, t.dataset.c, t.value);
      if (t.tagName === 'SELECT' && /_mode$|^exit_line$/.test(t.dataset.c)) paintRes();     // only the number this mode reads shows
    } else if (t.dataset.in) {
      const inp = (meta.inputs || []).find((i) => i.key === t.dataset.in);
      f.inputs[inp.key] = inp.type === 'bool' ? t.checked : inp.type === 'choice' ? t.value : t.value === '' ? NaN : Number(t.value);
      t.classList.toggle('bad', !!X.inputError(inp, f.inputs[inp.key]));
      if (inp.type === 'choice') paintRes();          // the group's summary names the choices
    } else if (t.dataset.f === 'range') {
      const side = /^wf31_(is|oos|both)$/.test(t.value) ? t.value.slice(5) : t.value === 'wf31r_both' ? 'both' : null;
      S.wfStepsOpen = false;                                                  // Block by block opens by hand only
      f.range = side ? { id: 'all', start: f.range.start, end: f.range.end, wf: X.WF_ROLL, side, ...(t.value === 'wf31r_both' ? { step: 1 } : {}) }     // 3:1 runs over all the data
        : { id: t.value, start: f.range.start, end: f.range.end, wf: null };
      paintRes(); paintHead();
    }
    else if (t.dataset.f === 'start' || t.dataset.f === 'end') f.range[t.dataset.f] = t.value.trim();
    else f[t.dataset.f] = t.value === '' ? NaN : Number(t.value);
  }
});
root.addEventListener('scroll', (e) => { if (e.target.id === 'edTa') syncScroll(); }, true);
/* The list has the keyboard from a touch on it until a touch elsewhere. Escape lets go of the picks; Delete / Backspace deletes them. */
document.addEventListener('pointerdown', (e) => { S.listFocus = !!(e.target.closest && e.target.closest('#labLib')); }, true);
document.addEventListener('focusin', (e) => { if (e.target.closest && !e.target.closest('.lab-menu, .lab-ov')) S.listFocus = !!e.target.closest('#labLib'); }, true);
document.addEventListener('keydown', (e) => {          // (capture: before the menu and sheet close themselves on Escape)
  if (S.view !== 'lib' || !S.picks.length) return;
  if (e.key === 'Escape') { if (!menuEl && !overlay) { S.picks = []; paintLib(); } return; }
  if (!C.deleteKey(e, { picked: S.picks.length, inList: S.listFocus, typing: C.isTyping(e.target), dialog: !!overlay || !!menuEl })) return;
  e.preventDefault();
  e.stopImmediatePropagation();          // the chart's own Delete (it removes a selected drawing) must not also run
  deleteStrategies(C.deleteTargets(S.picks, S.picks[0]));
}, true);
root.addEventListener('keydown', (e) => {
  if (e.target.id === 'libQ') {          // the search box: Enter opens the best match, Escape clears it
    if (e.key === 'Escape' && S.libQ) { e.preventDefault(); e.stopPropagation(); S.libQ = ''; e.target.value = ''; paintLibList(); }
    else if (e.key === 'Enter' && !e.repeat) { const b = document.querySelector('#libList .lb-item'); if (b) { e.preventDefault(); b.click(); } }
    return;
  }
  if (inChart(e) || pipeOn()) return;        // (a pipeline view has the middle: the editor's keys save and run nothing from behind it)
  const b = buf(), t = e.target, mod = e.metaKey || e.ctrlKey;
  if (mod && e.key === 's') { e.preventDefault(); if (b && b.kind !== 'builtin') save(b); return; }
  if (mod && e.key === 'Enter') { e.preventDefault(); if (!e.repeat) run(); return; }   // a held ⌘↵ starts one run, not many
  if (t.id !== 'edTa' || !b || b.kind === 'builtin' || locked(b)) return;
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
setTimeout(() => { if (P.chart) soloChart(); }, 1800);
// Bar Replay lives in the same bottom panel: asking for it brings the panel back
document.getElementById('tbReplay')?.addEventListener('click', () => setReport(true));
loadDesk();
/* The Desk page's "Open in the Lab": the Mac app switches tab and drops the link's #strategy part, so the Desk leaves its ask with the
   chart service and this page takes it, when it is shown and every few seconds (a hidden tab's page may not be told it was shown). */
async function takeDeskAsk() {
  const r = await send('GET', '/api/tester/lab-open');
  const name = r.ok && r.json && typeof r.json.name === 'string' ? r.json.name : '';
  if (!name) return;
  const run = r.json && typeof r.json.run === 'string' && /^[0-9a-z_-]+$/.test(r.json.run) ? r.json.run : '';   // the Desk's "Show on chart"
  const builtin = r.json && r.json.builtin === true;          // a Desk straddle's tester twin (nq930, gc_nfpcpi), not a draft
  if (builtin ? !S.builtins.some((x) => x.id === name) : !S.drafts.some((d) => d.name === name)) await loadLists();
  if (builtin) { if (S.builtins.some((x) => x.id === name)) selectBuiltin(name); }
  else if (S.drafts.some((d) => d.name === name)) selectDraft(name);
  if (run) showRunOnChart(run).then((ok) => log(ok ? 'Its run on the unseen days is on the chart: the list under it steps through every trade.' : 'The chart did not take that run: turn Chart off and on to try again.'));
}
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') takeDeskAsk(); });
window.addEventListener('focus', takeDeskAsk);
setInterval(takeDeskAsk, 2500);
loadLists().then(() => {
  const run = /^#run=([0-9a-z_-]+)$/.exec(location.hash);       // the Desk page's "Show executions on chart"
  if (run) { showRunOnChart(run[1]).then((ok) => log(ok ? 'Its executions are on the chart: the list under it steps through every trade.' : 'The chart did not take that run: turn Chart off and on to try again.')); return; }
  const m = /^#(strategy|builtin)=(.+)$/.exec(location.hash);
  if (!m) return;
  const name = decodeURIComponent(m[2]);
  if (m[1] === 'strategy' && S.drafts.some((d) => d.name === name)) selectDraft(name);
  else if (m[1] === 'builtin' && S.builtins.some((x) => x.id === name)) selectBuiltin(name);
});
window.HBLab = { openScript, setPanel, panels: P, state: S };
})();
