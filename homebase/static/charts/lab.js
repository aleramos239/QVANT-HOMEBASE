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
const S = { builtins: [], drafts: [], bufs: new Map(), cur: null, forms: {}, run: null, log: [], seq: 0, busy: false };
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
  const [a, b] = await Promise.all([send('GET', '/api/tester/strategies'), send('GET', '/api/tester/drafts')]);
  if (a.ok) S.builtins = (a.json || []).filter((s) => !s.draft);
  if (b.ok) S.drafts = b.json || [];
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
  if (nerr) { log(`<span class="err">${esc(nerr)}</span>`); const n = $('#edName'); if (n) { n.classList.add('bad'); n.focus(); } return false; }
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
  for (const k of PANELS) root.dataset[k] = P[k] ? '1' : '0';
  root.style.setProperty('--lab-code', String(split));
  root.style.setProperty('--lab-chart', String(100 - split));
  document.body.classList.toggle('lab-chart-on', P.chart);
  for (const x of document.querySelectorAll('#labPanels [data-panel]')) x.setAttribute('aria-pressed', String(!!P[x.dataset.panel]));
  if (save) { try { localStorage.setItem('hb_lab_panels', JSON.stringify(P)); localStorage.setItem('hb_lab_split', String(Math.round(split))); } catch (_) { /* private mode */ } }
  refit();
}
/* Show or hide one panel. The middle is never empty: hiding the last of Code / Chart brings the other back. */
function setPanel(k, on) {
  if (!PANELS.includes(k)) return;
  P[k] = on == null ? !P[k] : !!on;
  if (!P.code && !P.chart) P[k === 'code' ? 'chart' : 'code'] = true;
  panelsChosen = true;
  applyPanels();
  if (k === 'chart' && P.chart) setTimeout(syncChart, 160);
}
/* Put the current run on the chart: its executions, its levels and the chart's own indicators. `report` also
   opens the Strategy Tester's full report under the chart. The server refuses 09:20-09:35 ET (the desk's window). */
let shownRid = null;
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
  if (shownRid === r.rid) return;
  shownRid = r.rid;
  const o = await send('POST', '/api/tester/show', { run_id: r.rid });
  if (!o.ok) { shownRid = null; log(`<span class="err">Could not show it on the chart: ${esc(o.error)}</span>`); }
  else if (!o.json.pages) { shownRid = null; log('No chart page is open to show it on'); }
}
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
let overlay = null, menuEl = null;
function closeDialog() { if (overlay) { overlay.remove(); overlay = null; } }
function dialog(html) {
  closeDialog();
  overlay = document.createElement('div');
  overlay.className = 'lab-ov';
  overlay.innerHTML = `<div class="lab-dlg" role="dialog" aria-modal="true">${html}</div>`;
  overlay.addEventListener('pointerdown', (e) => { if (e.target === overlay) closeDialog(); });
  document.body.appendChild(overlay);
  return overlay.firstElementChild;
}
function closeMenu() { if (menuEl) { menuEl.remove(); menuEl = null; } }
function menu(anchor, html, onPick) {
  closeMenu();
  menuEl = document.createElement('div');
  menuEl.className = 'lab-menu';
  menuEl.innerHTML = html;
  document.body.appendChild(menuEl);
  const a = anchor.getBoundingClientRect(), m = menuEl.getBoundingClientRect();
  menuEl.style.left = `${Math.max(8, Math.min(a.left, innerWidth - m.width - 8))}px`;
  menuEl.style.top = `${Math.max(8, Math.min(a.bottom + 6, innerHeight - m.height - 8))}px`;
  menuEl.addEventListener('click', (e) => { const t = e.target.closest('[data-pick]'); if (t) { closeMenu(); onPick(t.dataset.pick); } });
}
document.addEventListener('pointerdown', (e) => { if (menuEl && !menuEl.contains(e.target) && !e.target.closest('[data-act="new"]')) closeMenu(); });
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') { closeMenu(); closeDialog(); } });

async function newMenu(anchor) {
  const r = await send('GET', '/api/tester/drafts/templates');
  const ts = (r.ok && r.json) || [];
  menu(anchor, `<button data-pick="paste"><b>Paste a script</b><small>Insert Python from your clipboard or an editor</small></button>
    <button data-pick="file"><b>Open a .py file…</b><small>Load a script from disk</small></button><hr>
    <h6>Start from a template</h6>${ts.map((t) => `<button data-pick="t:${esc(t.id)}"><b>${esc(t.title)}</b><small>${esc(t.blurb)}</small></button>`).join('')}`,
  async (pick) => {
    if (pick === 'paste') return pasteScript();
    if (pick === 'file') return $('#labFile').click();
    const t = ts.find((x) => `t:${x.id}` === pick);
    if (t) openScript(t.code, C.suggestName(t.code, takenNames()));
  });
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

/* ---- painting ---- */
function paintAll() { paintLib(); paintEditor(); paintRes(); }

function paintLib() {
  const el = $('#labLib');
  if (!el) return;
  const unsaved = [...S.bufs.values()].filter((b) => b.kind === 'new');
  const rows = [
    ...unsaved.map((b) => ({ key: b.key, name: b.name || 'untitled', sub: 'Unsaved', dot: 'off', flag: '' })),
    ...S.drafts.map((d) => {
      const b = S.bufs.get(`d:${d.name}`), dirty = b && isDirty(b);
      const bad = b && b.valid ? !b.valid.ok : !d.ok;
      return { key: `d:${d.name}`, name: d.name, sub: bad ? 'Draft · needs a fix' : dirty ? 'Draft · unsaved changes' : 'Draft · valid', dot: bad ? 'err' : dirty ? 'off' : '', flag: bad ? '!' : '', del: d.name };
    })];
  el.innerHTML = `<div class="lb-sh"><span>My strategies</span><span>${rows.length || ''}</span></div>
    ${rows.length ? rows.map((r) => `<button class="lb-item${S.cur === r.key ? ' sel' : ''}" data-key="${esc(r.key)}" aria-current="${S.cur === r.key}">
        <i class="lb-dot ${r.dot}"></i><span class="it"><b>${esc(r.name)}</b><small>${esc(r.sub)}</small></span><span class="lb-flag">${r.flag}</span></button>`).join('')
      : '<div class="lb-empty">Nothing here yet. Paste a script or start from a template.</div>'}
    <button class="btn btn-default lb-new" data-act="new">+ New strategy</button>
    <div class="lb-sh"><span>Built-in · read-only</span><span>${S.builtins.length || ''}</span></div>
    ${S.builtins.map((s) => `<button class="lb-item${S.cur === `b:${s.id}` ? ' sel' : ''}" data-key="b:${esc(s.id)}" aria-current="${S.cur === `b:${s.id}`}">
        <i class="lb-dot lock"></i><span class="it"><b>${esc(s.name || s.id)}</b><small>${esc(s.root || '')}${s.bar_minutes ? ` · ${s.bar_minutes}-min bars` : ''}</small></span>${SAVE_ICON_LOCK}</button>`).join('')}`;
}

function paintEditor() {
  const el = $('#labEd');
  const b = buf();
  if (!b) {
    el.innerHTML = `<div class="lab-welcome"><h2>Write or paste a Python strategy</h2>
      <p>Test it on years of real tick data in a sandbox, see the trades on a chart, and request a review when you like what you see. Your script is only ever read and backtested here, never run on the desk.</p>
      <div class="acts"><button class="btn btn-default btn-lg" data-act="paste">Paste a script</button><button class="btn btn-outline btn-lg" data-act="new">Start from a template</button></div></div>`;
    return;
  }
  const ro = b.kind === 'builtin';
  el.innerHTML = `<div class="ed-head">
      <div class="ed-title">${b.kind === 'new'
        ? `<input class="ed-name" id="edName" value="${esc(b.name)}" placeholder="name" spellcheck="false" autocomplete="off" autocapitalize="off" aria-label="Strategy name"><span class="ed-ext">.py</span>`
        : `<span class="ed-file">${esc(b.kind === 'builtin' ? b.id : b.name)}.py</span>`}
        <span class="ed-state" id="edState"></span></div>
      <div class="ed-actions" id="edActs"></div></div>
    <div class="ed-wrap" id="edWrap"><pre class="ed-gut" id="edGut" aria-hidden="true"></pre>
      <div class="ed-main"><pre class="ed-hl" aria-hidden="true"><code id="edHl"></code></pre>
        <textarea class="ed-ta" id="edTa" spellcheck="false" autocomplete="off" autocapitalize="off" autocorrect="off" wrap="off" aria-label="Python source" ${ro ? 'readonly' : ''}></textarea>
        <div class="ed-hint" id="edHint" hidden>Press <kbd>⌘V</kbd> to paste your script, or drop a .py file here.</div></div></div>
    <div class="ed-log" id="edLog"></div>`;
  $('#edTa').value = b.code || '';
  paintHead(); paintCode(); paintLog();
}
function paintHead() {
  const b = buf(), acts = $('#edActs'), st = $('#edState');
  if (!b || !acts) return;
  const ro = b.kind === 'builtin', busy = S.busy;
  let tone = '', text = '';
  if (ro) text = 'Built-in · read-only';
  else if (b.valid) { const s = C.statusOf(b.valid); tone = s.tone; text = s.text + (b.valid.ok && b.savedAt && !isDirty(b) ? ` · saved ${C.ago(b.savedAt, Date.now())}` : isDirty(b) && b.kind !== 'new' ? ' · unsaved' : ''); }
  else if (b.code && b.code.trim()) text = 'Checking…';
  st.className = `ed-state ${tone}`;
  st.innerHTML = text ? `<i></i>${esc(text)}` : '';
  acts.innerHTML = ro
    ? `<button class="btn btn-default" data-act="run"${busy ? ' disabled' : ''}>${busy ? 'Running…' : 'Run backtest'}</button>`
    : `<button class="btn btn-outline" data-act="validate">Validate</button>
       <button class="btn btn-default" data-act="run"${busy || !(b.code || '').trim() ? ' disabled' : ''}>${busy ? 'Running…' : 'Run backtest'}</button>
       <button class="btn btn-outline" data-act="save"${isDirty(b) || b.kind === 'new' ? '' : ' disabled'}>Save</button>
       <button class="btn btn-outline" data-act="review"${b.kind === 'new' ? ' disabled' : ''} title="Package it for a person to read before it can reach the desk">Request review…</button>`;
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
function equitySvg(eq) {
  const s = X.equitySeries(eq).equity;
  if (s.length < 2) return '';
  const W = 340, H = 120, pad = 6, lo = Math.min(0, ...s.map((p) => p.value)), hi = Math.max(0, ...s.map((p) => p.value));
  const sx = (i) => (i / (s.length - 1)) * W, sy = (v) => pad + (1 - (v - lo) / ((hi - lo) || 1)) * (H - 2 * pad);
  const pts = s.map((p, i) => `${sx(i).toFixed(1)},${sy(p.value).toFixed(1)}`);
  return `<svg class="rs-eq" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Equity curve">
    <line class="z" x1="0" x2="${W}" y1="${sy(0).toFixed(1)}" y2="${sy(0).toFixed(1)}"/>
    <polygon class="a" points="0,${sy(0).toFixed(1)} ${pts.join(' ')} ${W},${sy(0).toFixed(1)}"/><polyline class="l" points="${pts.join(' ')}"/></svg>`;
}
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
  const spent = end && end >= '2025-01-01';
  return `<details class="rs-set"><summary><span>Settings</span><span>${esc(X.pillLabel ? X.pillLabel(f.range) : f.range.id)} · ${f.qty} contract${f.qty === 1 ? '' : 's'}</span></summary>
    <div class="grid"><label>Range</label><select data-f="range">${rangeOpts}</select>
      ${f.range.id === 'custom' ? `<label>From</label><input type="text" data-f="start" value="${esc(f.range.start)}" placeholder="YYYY-MM-DD"><label>To</label><input type="text" data-f="end" value="${esc(f.range.end)}" placeholder="YYYY-MM-DD">` : ''}
      ${spent ? '<div class="warn">This reaches 2025 or later, the data kept back for a final check. Each look is recorded.</div>' : ''}
      <label>Contracts</label><input type="number" data-f="qty" value="${esc(f.qty)}" min="1" step="1">
      <label>Fees ($ / contract, round trip)</label><input type="number" data-f="commission" value="${esc(f.commission)}" min="0" step="0.25">
      <label>Slippage (ticks)</label><input type="number" data-f="slippage_ticks" value="${esc(f.slippage_ticks)}" min="0" step="1">
      ${ins.length ? `<div class="sep"></div>${ins.map(inputRow).join('')}` : ''}</div></details>`;
}
function paintRes() {
  const el = $('#labRes');
  if (!el) return;
  const b = buf();
  if (!b) { el.innerHTML = '<div class="rs-body"><div class="rs-empty"><h3>Backtest</h3><p>Pick a strategy, or paste one, to see how it would have done.</p></div></div>'; return; }
  const r = S.run && S.run.key === b.key ? S.run : null, settings = settingsHtml(b);
  let main = '';
  if (r && !r.bundle && (S.busy || (r.st && r.st.status === 'queued'))) {
    const p = X.progress(r.st || { status: 'queued' }), ind = p.frac == null;
    main = `<div class="rs-prog"><div class="t">${esc(p.text || 'Starting…')}</div><div class="rs-bar${ind ? ' ind' : ''}"><i style="width:${ind ? 38 : Math.round(p.frac * 100)}%"></i></div>
      <button class="btn btn-outline btn-sm" data-act="cancel">Cancel</button></div>`;
  } else if (r && r.bundle) {
    const run = r.bundle.run, a = run.report.summary.all, tl = X.tiles(run), by = (l) => tl.find((t) => t.label === l) || { value: '—' };
    const net = tl[0], pos = (a.net_profit || 0) > 0;
    const badges = X.badges(run).filter((x) => x.tone !== 'info' || /sessions/.test(x.text));
    main = `<div class="rs-top"><span><b>Backtest</b> · ${esc(run.range && run.range.label ? run.range.label : '')}</span><span class="rs-chip">${esc(run.strategy.root || '')} · ${esc(run.qty)} contract${run.qty === 1 ? '' : 's'}</span></div>
      <div class="rs-net${pos ? ' pos' : ''}">${esc(net.value)}</div>
      <div class="rs-sub">After fees · ${esc(String(a.trades ?? 0))} trade${a.trades === 1 ? '' : 's'} · max drawdown ${esc(by('Max drawdown').value)}</div>
      ${equitySvg(r.bundle.equity)}
      <div class="rs-tiles">${[['Profit factor', by('Profit factor').value], ['Win rate', by('Win rate').value], ['Avg trade', by('Avg trade').value],
        ['Trades', String(a.trades ?? 0)], ['Max drawdown', by('Max drawdown').value], ['Sharpe', by('Sharpe').value]].map(([k, v]) => `<div class="rs-tile"><div class="k">${k}</div><div class="v">${esc(v)}</div></div>`).join('')}</div>
      ${(a.trades || 0) === 0 ? '<div class="rs-sub" style="margin-top:10px">It took no trades in this range. Check the session window and the entry rules, then run it again.</div>' : ''}
      <div class="rs-top" style="gap:6px;flex-wrap:wrap;justify-content:flex-start;margin-top:12px">${badges.map((x) => `<span class="rs-chip ${x.tone === 'err' ? 'err' : x.tone === 'warn' ? 'warn' : ''}" title="${esc(x.title || '')}">${esc(x.text)}</span>`).join('')}</div>
      <div class="rs-rows"><button class="rs-row" data-act="show"><span>Show trades on the chart</span><span>›</span></button>
        <button class="rs-row" data-act="report"><span>${root.dataset.report === '1' && P.chart ? 'Hide the full report' : 'Open the full report'}</span><span>›</span></button>
        <button class="rs-row" data-act="review"${b.kind === 'builtin' ? ' disabled' : ''}><span>Request a review</span><span>›</span></button></div>`;
  } else if (r && r.st && (r.st.status === 'error' || r.st.status === 'cancelled')) {
    main = `<div class="rs-empty"><h3>${r.st.status === 'cancelled' ? 'Cancelled' : 'The run failed'}</h3><p>${esc(r.st.error || (r.st.status === 'cancelled' ? 'Run it again when you are ready.' : 'See the line under the editor.'))}</p></div>`;
  } else {
    main = `<div class="rs-empty"><h3>No backtest yet</h3><p>Run it to see the P&amp;L, the trades and the equity curve. <b>⌘↵</b> runs it from the editor.</p></div>`;
  }
  el.innerHTML = `<div class="rs-body">${main}${settings}</div>`;
}

/* ---- events ----
   The chart shell sits inside the workspace now: nothing that happens in it is the Lab's to handle. */
const inChart = (e) => !!(e.target && e.target.closest && e.target.closest('#labChart'));
root.addEventListener('click', (e) => {
  if (inChart(e)) return;
  const lib = e.target.closest('[data-key]');
  if (lib) { const k = lib.dataset.key; if (k.startsWith('d:')) selectDraft(k.slice(2)); else if (k.startsWith('b:')) selectBuiltin(k.slice(2)); else { S.cur = k; paintAll(); } return; }
  const a = e.target.closest('[data-act]');
  if (!a) return;
  const b = buf(), act = a.dataset.act;
  if (act === 'new') newMenu(a);
  else if (act === 'paste') pasteScript();
  else if (act === 'run') run();
  else if (act === 'cancel') cancelRun();
  else if (act === 'show') showOnChart(false);
  else if (act === 'report') { if (root.dataset.report === '1' && P.chart) setReport(false); else showOnChart(true); }
  else if (act === 'review') reviewDialog();
  else if (act === 'save') save(b);
  else if (act === 'validate') validateNow(b).then((v) => { if (v) log(v.ok ? `Validated in ${b.validMs} ms · ${esc(C.metaLine(v.meta))}` : `<span class="err">${esc(C.statusOf(v).text)}</span>`); });
});
root.addEventListener('input', (e) => {
  if (inChart(e)) return;
  const b = buf(), t = e.target;
  if (t.id === 'edTa' && b && b.kind !== 'builtin') {
    const wasEmpty = !b.code.trim();
    b.code = t.value; b.valid = b.valid && b.valid.ok ? { ...b.valid, stale: true } : null;
    if (b.kind === 'new' && wasEmpty && b.code.trim() && !b.name) { b.name = C.suggestName(b.code, takenNames()); const n = $('#edName'); if (n) n.value = b.name; }
    paintCode(); paintHead(); queueValidate(b); paintLib();
  } else if (t.id === 'edName' && b) { b.name = t.value.trim(); t.classList.remove('bad'); paintLib(); }
  else if (t.dataset.f || t.dataset.in) {
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
  if (inChart(e)) return;
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
applyPanels(false);
paintAll();
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
