/* Homebase Charts — HBTesterUI: the Strategy Tester tab (HBPanel.addTab), built on HBTester (the pure
   model: form defaults/validation, the request body, progress text, tiles/tables/marks). This module owns
   the DOM only: the header row (strategy, inputs dialog, range, costs, holdout, run/progress/cancel, recent
   runs), the inner Overview / Performance summary / List of trades / Properties tabs, and the mini equity +
   drawdown chart.

   Carried finding (2026-09-27 review of Tasks 3-4, restated for this tab): HBPanel.refresh() -- really
   onDeskEvent -- re-renders whichever tab is active on every desk event, including quotes at up to 4/s,
   because a tab with no entry in panel.js's own TAB_EVENTS map (this one included -- panel.js is not a file
   this task touches) always redraws. panel.js calls our render(el) again with the SAME, un-cleared `el` on
   every one of those events. render() below detects that (our own root node is still there) and does
   nothing, so a quote tick never rebuilds the form, tears down the running progress bar, or drops table
   scroll/sort state. Only render() on a genuine tab show (panel.js clears `el` first) rebuilds from scratch.

   Browser only: no `require`/`module.exports` (unlike tester.js's pure half). */
(() => {
'use strict';
const X = window.HBTester;
const Tr = window.HBTrade;
const REASON_MAX = X.REASON_MAX;

const COST_FIELDS = [['qty', 'Qty', 1, 100, 1], ['commission', 'Commission $', 0, 100, 0.01],
  ['slippage_ticks', 'Slippage (ticks)', 0, 20, 0.25]];
const INNER_TABS = [['overview', 'Overview'], ['summary', 'Performance summary'], ['trades', 'List of trades'],
  ['properties', 'Properties']];
const TRADE_COLS = [['n', '#', true], ['side', 'Side', false], ['entry', 'Entry time', false], [null, 'Entry price', true],
  ['exit', 'Exit time', false], [null, 'Exit price', true], ['reason', 'Reason', false], ['qty', 'Qty', true],
  ['net', 'Net', true], ['mae', 'MAE', true], ['mfe', 'MFE', true], ['dur', 'Duration', true]];
const TRADE_CHUNK = 500;

let page = null;

/* ---- strategies / prop rules: fetched once, cached ---- */
let strategiesList = null, propRulesList = null;
let strategiesPromise = null, propRulesPromise = null;
function loadStrategies() {
  if (!strategiesPromise) {
    strategiesPromise = fetch('/api/tester/strategies').then((r) => (r.ok ? r.json() : [])).catch(() => [])
      .then((list) => { strategiesList = Array.isArray(list) ? list : []; return strategiesList; });
  }
  return strategiesPromise;
}
function loadPropRules() {
  if (!propRulesPromise) {
    propRulesPromise = fetch('/api/tester/prop-rules').then((r) => (r.ok ? r.json() : [])).catch(() => [])
      .then((list) => { propRulesList = Array.isArray(list) ? list : []; return propRulesList; });
  }
  return propRulesPromise;
}
function schemaFor(id) { return (strategiesList || []).find((s) => s.id === id) || (strategiesList || [])[0] || null; }

/* ---- per-viewer persisted form ({strategy, forms: {id: form}} in localStorage hb_tester) ---- */
const STORE_KEY = 'hb_tester';
let store = { strategy: null, forms: {} };
function loadStore() {
  try {
    const v = JSON.parse(localStorage.getItem(STORE_KEY) || 'null');
    return (v && typeof v === 'object') ? { strategy: v.strategy || null, forms: (v.forms && typeof v.forms === 'object') ? v.forms : {} } : { strategy: null, forms: {} };
  } catch (_) { return { strategy: null, forms: {} }; }
}
function saveStore() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(store)); } catch (_) { /* storage off: this session only */ }
}

/* ---- state ---- */
let strategyId = null;
let form = null;
let loadedKey = null;      // HBTester.key of the form that produced `bundle`, or null
let bundle = null;         // {run, trades, equity, plots, propsim} or null
let serverError = '';      // a 400 detail, or a run failure -- takes precedence over a client-side `problems()` line
let runId = null;
let runStatus = null;      // the last polled status, or null (no run in flight / just finished)
let pollToken = 0;
let innerTab = 'overview';
let hidden = false;
let selectedTrade = null;
let sortCol = 'n', sortDir = 1;
let visibleTradeRows = TRADE_CHUNK;
let miniChartHandle = null;
const listeners = new Set();

/* ---- DOM roots, rebuilt by render(); refreshed in place by everything else ---- */
let root = null, headerEl = null, tabsEl = null, contentEl = null;
let errEl = null, runBtn = null, progressBarEl = null, progressTextEl = null;

function notify() { for (const fn of [...listeners]) { try { fn(); } catch (e) { console.error(e); } } }
function persist() {
  serverError = '';
  store.strategy = strategyId;
  store.forms[strategyId] = form;
  saveStore();
}

/* ---- validation shown in the header's error line and the inputs dialog: a local copy of tester.js's
   private inputError (not exported -- Task 8's file is not one this task modifies). Kept tiny and mirrors
   the rules HBTester.problems() already applies (and tester.test.mjs already covers) for a schema input. */
function checkInput(inp, v) {
  if (inp.type === 'bool') return typeof v === 'boolean' ? null : `${inp.label}: on or off`;
  if (inp.type === 'choice') return inp.choices.includes(v) ? null : `${inp.label}: one of ${inp.choices.join(', ')}`;
  if (typeof v !== 'number' || !Number.isFinite(v)) return `${inp.label}: a number`;
  if (inp.type === 'int' && !Number.isInteger(v)) return `${inp.label}: a whole number`;
  if ((inp.min != null && v < inp.min) || (inp.max != null && v > inp.max)) return `${inp.label}: ${inp.min} to ${inp.max}`;
  return null;
}

function tickForRoot(root_) {
  const cells = (page.cells && page.cells()) || [];
  const c = cells.find((x) => x.shown && x.shown.root === root_);
  return c && c.tick ? c.tick : 0.25;
}
/* The chart canvas colours for the mini chart: any built cell's own palette, else the theme's own tokens
   (cell.js's palette(), trimmed to what the mini chart needs). */
function palette() {
  const c = page.cur && page.cur();
  if (c && c.P) return c.P;
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  return dark ? { text2: '#8C8C8C', grid: '#1C1C1C', up: '#089981', down: '#F23645' }
              : { text2: '#787B86', grid: '#F0F3FA', up: '#089981', down: '#F23645' };
}

/* ---- the Overview mini chart (equity + drawdown), verbatim per the task brief ---- */
function miniChart(el, equity, P) {
  const LW = window.LightweightCharts, s = X.equitySeries(equity);
  const chart = LW.createChart(el, { autoSize: true, height: 180,
    layout: { background: { color: 'transparent' }, textColor: P.text2, fontSize: 11, attributionLogo: false,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif' },
    grid: { vertLines: { visible: false }, horzLines: { color: P.grid } },
    rightPriceScale: { borderVisible: false }, timeScale: { borderVisible: false }, handleScroll: false, handleScale: false });
  const eq = chart.addSeries(LW.AreaSeries, { lineColor: P.up, topColor: 'rgba(8,153,129,.28)', bottomColor: 'rgba(8,153,129,0)',
    lineWidth: 2, priceFormat: { type: 'price', precision: 0, minMove: 1 }, lastValueVisible: false, priceLineVisible: false });
  eq.setData(s.equity);
  const dd = chart.addSeries(LW.AreaSeries, { lineColor: P.down, topColor: 'rgba(242,54,69,0)', bottomColor: 'rgba(242,54,69,.35)',
    lineWidth: 1, priceFormat: { type: 'price', precision: 0, minMove: 1 }, lastValueVisible: false, priceLineVisible: false }, 1);
  dd.setData(s.drawdown);
  chart.panes()[1].setStretchFactor(0.35);
  chart.timeScale().fitContent();
  return chart;   // caller: chart.remove() before re-render
}
function dropMiniChart() {
  if (!miniChartHandle) return;
  try { miniChartHandle.remove(); } catch (_) { /* already gone */ }
  miniChartHandle = null;
}

/* ================================================================== header ================================================================== */

function computeErrorText() { return serverError || X.problems(form, schemaFor(strategyId)) || ''; }
/* A cheap, focus-preserving update for the fields a viewer types into (qty/commission/slippage, the holdout
   reason): recompute the error line and the Run label without rebuilding the header. */
function syncRunState() {
  const text = computeErrorText();
  if (errEl) { errEl.textContent = text; errEl.hidden = !text; }
  if (runBtn) { const label = X.runLabel(form, loadedKey); runBtn.lastChild.textContent = ' ' + label; runBtn.setAttribute('aria-label', label); }
}
function updateProgressUI() {
  const p = X.progress(runStatus);
  if (progressTextEl) progressTextEl.textContent = p.text;
  if (progressBarEl) { if (p.frac == null) progressBarEl.removeAttribute('value'); else progressBarEl.value = p.frac; }
}

function optionEl(value, text) { const o = document.createElement('option'); o.value = value; o.textContent = text; return o; }

function strategySelect() {
  const sel = page.mk('select', 'set-select tst-strat');
  sel.setAttribute('aria-label', 'Strategy');
  for (const s of strategiesList) sel.appendChild(optionEl(s.id, s.name));
  sel.value = strategyId;
  sel.onchange = () => switchStrategy(sel.value);
  return sel;
}
function iconBtn(name, title, onClick) {
  const b = page.mk('button', 'tst-icon-btn');
  b.type = 'button';
  b.title = title;
  b.setAttribute('aria-label', title);
  b.appendChild(page.icon(name));
  b.onclick = onClick;
  return b;
}
function rangeGroup() {
  const wrap = page.mk('span', 'tst-group');
  const sel = page.mk('select', 'set-select');
  sel.setAttribute('aria-label', 'Range');
  for (const r of X.RANGES) sel.appendChild(optionEl(r.kind, r.label));
  sel.value = form.range.kind;
  sel.onchange = () => { form.range = { kind: sel.value, start: form.range.start, end: form.range.end }; persist(); refreshHeader(); };
  wrap.appendChild(sel);
  if (form.range.kind === 'custom') {
    const start = page.mk('input'), end = page.mk('input');
    start.type = 'date'; start.value = form.range.start || ''; start.setAttribute('aria-label', 'Range start');
    end.type = 'date'; end.value = form.range.end || ''; end.setAttribute('aria-label', 'Range end');
    start.onchange = () => { form.range = { ...form.range, start: start.value }; persist(); refreshHeader(); };
    end.onchange = () => { form.range = { ...form.range, end: end.value }; persist(); refreshHeader(); };
    wrap.append(start, end);
  }
  return wrap;
}
function costInput(key, label, lo, hi, step) {
  const wrap = page.mk('span', 'tst-cost'), lab = page.mk('label', 'tst-cost-l', label), inp = page.mk('input', 'tst-num');
  inp.type = 'number'; inp.min = String(lo); inp.max = String(hi); inp.step = String(step); inp.value = String(form[key]);
  inp.id = `tst-cost-${key}`; lab.htmlFor = inp.id;
  inp.oninput = () => {
    const v = inp.value === '' ? NaN : Number(inp.value);
    form = { ...form, [key]: v };
    persist();
    syncRunState();
  };
  wrap.append(lab, inp);
  return wrap;
}
function holdoutGroup() {
  const wrap = page.mk('span', 'tst-group');
  const lab = page.mk('label', 'tst-cost-l', 'Holdout');
  const sw = page.mk('button', 'switch' + (form.holdout.on ? ' on' : ''));
  sw.type = 'button';
  sw.setAttribute('role', 'switch');
  sw.setAttribute('aria-checked', String(form.holdout.on));
  sw.setAttribute('aria-label', 'Holdout');
  sw.onclick = () => { form = { ...form, holdout: { ...form.holdout, on: !form.holdout.on } }; persist(); refreshHeader(); };
  wrap.append(lab, sw);
  if (form.holdout.on) {
    const reason = page.mk('input', 'tst-reason');
    reason.type = 'text';
    reason.maxLength = REASON_MAX;
    reason.placeholder = 'Why spend holdout data? (logged)';
    reason.value = form.holdout.reason || '';
    reason.setAttribute('aria-label', 'Holdout reason');
    reason.oninput = () => { form = { ...form, holdout: { ...form.holdout, reason: reason.value } }; persist(); syncRunState(); };
    wrap.appendChild(reason);
  }
  return wrap;
}
function runArea() {
  const wrap = page.mk('span', 'tst-run-area');
  if (runStatus) {
    progressBarEl = document.createElement('progress');
    progressBarEl.className = 'tst-progress';
    progressBarEl.max = 1;
    progressTextEl = page.mk('span', 'tst-progress-text', '');
    const cancel = iconBtn('square', 'Cancel', cancelRun);
    wrap.append(progressBarEl, progressTextEl, cancel);
    updateProgressUI();
  } else {
    progressBarEl = null; progressTextEl = null;
    runBtn = page.mk('button', 'btn btn-primary tst-run');
    runBtn.type = 'button';
    runBtn.append(page.icon('play'), document.createTextNode(' ' + X.runLabel(form, loadedKey)));
    runBtn.onclick = startRun;
    wrap.appendChild(runBtn);
  }
  return wrap;
}
function recentRunsBtn() {
  const b = page.mk('button', 'tst-btn');
  b.type = 'button';
  b.setAttribute('aria-haspopup', 'menu');
  b.setAttribute('aria-expanded', 'false');
  b.append(page.icon('history'), document.createTextNode(' Recent runs'), page.icon('chevron'));
  b.onclick = () => page.toggleMenu(b, () => fillRecentRunsMenu(page.openMenu(b, 'menu-tester-runs')));
  return b;
}

function refreshHeader() {
  const schema = schemaFor(strategyId);
  headerEl.replaceChildren();
  headerEl.appendChild(strategySelect());
  headerEl.appendChild(iconBtn('gear', `${schema.name} · Inputs`, openInputsDialog));
  headerEl.appendChild(rangeGroup());
  for (const [key, label, lo, hi, step] of COST_FIELDS) headerEl.appendChild(costInput(key, label, lo, hi, step));
  headerEl.appendChild(holdoutGroup());
  headerEl.appendChild(runArea());
  headerEl.appendChild(recentRunsBtn());
  errEl = page.mk('span', 'tst-err', '');
  headerEl.appendChild(errEl);
  syncRunState();
}

/* ================================================================== the inputs dialog ================================================================== */

function inputsDialogRow(inp, draft) {
  const row = page.mk('div', 'field'), id = `ti-${inp.key}`, lab = page.mk('label', '', inp.label);
  let ctl;
  if (inp.type === 'bool') {
    ctl = page.mk('input');
    ctl.type = 'checkbox';
    ctl.checked = !!draft.inputs[inp.key];
    ctl.onchange = () => { draft.inputs[inp.key] = ctl.checked; };
  } else if (inp.type === 'choice') {
    ctl = page.mk('select', 'set-select');
    for (const c of inp.choices) ctl.appendChild(optionEl(c, c));
    ctl.value = draft.inputs[inp.key];
    ctl.onchange = () => { draft.inputs[inp.key] = ctl.value; };
  } else {
    ctl = page.mk('input');
    ctl.type = 'number';
    if (inp.min != null) ctl.min = String(inp.min);
    if (inp.max != null) ctl.max = String(inp.max);
    if (inp.step != null) ctl.step = String(inp.step);
    ctl.value = String(draft.inputs[inp.key]);
    ctl.oninput = () => { draft.inputs[inp.key] = ctl.value === '' ? NaN : Number(ctl.value); };
  }
  ctl.id = id;
  lab.htmlFor = id;
  row.append(lab, ctl);
  return row;
}
function propRulesRow(draft) {
  const row = page.mk('div', 'field'), lab = page.mk('label', '', 'Rule set'), sel = page.mk('select', 'set-select');
  for (const r of (propRulesList || [])) sel.appendChild(optionEl(r.id, r.name + (r.confirmed ? '' : ' · unconfirmed rules')));
  sel.value = draft.prop_rules;
  sel.onchange = () => { draft.prop_rules = sel.value; };
  row.append(lab, sel);
  return row;
}
function openInputsDialog() {
  const schema = schemaFor(strategyId);
  const box = page.openDialog(`${schema.name} · Inputs`, 'settings-small');
  const fields = page.mk('div', 'dlg-fields'), err = page.mk('div', 'dlg-err');
  err.hidden = true;
  err.setAttribute('role', 'alert');
  const draft = { inputs: { ...form.inputs }, prop_rules: form.prop_rules };
  for (const inp of schema.inputs) fields.appendChild(inputsDialogRow(inp, draft));
  fields.appendChild(page.mk('div', 'set-cap', 'PROP EVAL'));
  fields.appendChild(propRulesRow(draft));
  const foot = page.mk('div', 'dlg-foot'), cancel = page.mk('button', 'btn btn-ghost', 'Cancel'), ok = page.mk('button', 'btn btn-primary', 'Ok');
  cancel.type = 'button';
  ok.type = 'button';
  cancel.onclick = page.closeDialog;
  ok.onclick = () => {
    for (const inp of schema.inputs) {
      const e = checkInput(inp, draft.inputs[inp.key]);
      if (e) { err.textContent = e; err.hidden = false; return; }
    }
    form = { ...form, inputs: draft.inputs, prop_rules: draft.prop_rules };
    persist();
    page.closeDialog();
    refreshHeader();
  };
  foot.append(cancel, ok);
  box.append(fields, err, foot);
  const first = fields.querySelector('input, select');
  if (first) first.focus();
}

/* ================================================================== recent runs ================================================================== */

function recentRunRow(r) {
  const done = r.status === 'done';
  const b = page.mk('button', 'menu-i tst-run-row');
  b.type = 'button';
  b.disabled = !done;
  const stratName = ((strategiesList || []).find((s) => s.id === r.strategy) || {}).name || r.strategy;
  const rangeLabel = (r.range && r.range.label) || '';
  const line = page.mk('span', 'menu-t', done
    ? `${stratName} · ${rangeLabel} · ${Tr.money(r.net_profit)} · ${r.trades ?? 0} trades`
    : `${stratName} · ${rangeLabel} · ${r.status}`);
  b.appendChild(line);
  if (r.holdout) b.appendChild(page.mk('span', 'env live', 'HOLDOUT'));
  if (done) b.onclick = () => { page.closeMenu(); loadRecentRun(r.id); };
  return b;
}
function fillRecentRunsMenu(m) {
  m.appendChild(page.mk('div', 'menu-empty', 'Loading…'));
  fetch('/api/tester/runs').then((r) => (r.ok ? r.json() : [])).catch(() => [])
    .then((list) => {
      if (!document.body.contains(m)) return;   // closed while loading
      m.replaceChildren();
      if (!list.length) { m.appendChild(page.mk('div', 'menu-empty', 'No runs yet')); page.placeMenu(); return; }
      for (const r of list) m.appendChild(recentRunRow(r));
      page.placeMenu();
    });
}
function loadRecentRun(id) {
  fetch(`/api/tester/run/${id}/bundle`).then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((b) => {
      const schema = schemaFor(b.run.strategy.id);
      strategyId = b.run.strategy.id;
      form = X.fromRun(b.run, schema);
      bundle = b;
      loadedKey = X.key(form);
      innerTab = 'overview';
      visibleTradeRows = TRADE_CHUNK;
      selectedTrade = null;
      persist();
      refreshHeader();
      refreshTabsBar();
      refreshContent();
      notify();
    })
    .catch(() => { serverError = 'could not load that run'; refreshHeader(); });
}

/* ================================================================== run / poll / cancel ================================================================== */

function startRun() {
  const schema = schemaFor(strategyId);
  const prob = X.problems(form, schema);
  if (prob) { serverError = ''; refreshHeader(); return; }
  const bodyObj = X.body(form);
  serverError = '';
  runStatus = { status: 'queued' };
  const token = ++pollToken;
  refreshHeader();
  fetch('/api/tester/run', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(bodyObj) })
    .then(async (r) => {
      if (r.status === 400) {
        let detail = '';
        try { detail = (await r.json()).detail || ''; } catch (_) { /* no JSON body */ }
        throw new Error(detail || 'bad request');
      }
      if (!r.ok) throw new Error(`request failed (${r.status})`);
      return r.json();
    })
    .then(({ id }) => {
      if (token !== pollToken) return;
      runId = id;
      poll(id, token);
    })
    .catch((e) => {
      if (token !== pollToken) return;
      runStatus = null;
      serverError = e.message || 'request failed';
      refreshHeader();
    });
}
function poll(rid, token) {
  fetch(`/api/tester/run/${rid}`).then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((st) => {
      if (token !== pollToken) return;
      runStatus = st;
      updateProgressUI();
      const p = X.progress(st);
      if (!p.final) { setTimeout(() => poll(rid, token), 500); return; }
      if (st.status === 'done') { loadBundle(rid, token); return; }
      runStatus = null;
      serverError = p.text;
      refreshHeader();
    })
    .catch(() => {
      if (token !== pollToken) return;
      runStatus = null;
      serverError = 'lost contact with the run';
      refreshHeader();
    });
}
/* loadedKey is HBTester.key of the CURRENT form, not a snapshot of what was submitted (ruling: the run
   label reacts to further edits the same way whether they happened before or during the run). */
function loadBundle(rid, token) {
  fetch(`/api/tester/run/${rid}/bundle`).then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((b) => {
      if (token !== pollToken) return;
      bundle = b;
      loadedKey = X.key(form);
      runStatus = null;
      innerTab = 'overview';
      visibleTradeRows = TRADE_CHUNK;
      selectedTrade = null;
      refreshHeader();
      refreshTabsBar();
      refreshContent();
      notify();
    })
    .catch(() => {
      if (token !== pollToken) return;
      runStatus = null;
      serverError = 'the run finished but its bundle could not be read';
      refreshHeader();
    });
}
function cancelRun() {
  if (!runId) return;
  fetch(`/api/tester/run/${runId}/cancel`, { method: 'POST' }).catch(() => { /* the next poll tick reflects reality either way */ });
}

/* ================================================================== inner tabs + content ================================================================== */

function refreshTabsBar() {
  tabsEl.replaceChildren();
  for (const [id, label] of INNER_TABS) {
    const b = page.mk('button', 'tst-tab' + (innerTab === id ? ' active' : ''), label);
    b.type = 'button';
    b.setAttribute('role', 'tab');
    b.setAttribute('aria-selected', String(innerTab === id));
    b.onclick = () => { innerTab = id; refreshTabsBar(); refreshContent(); };
    tabsEl.appendChild(b);
  }
  tabsEl.appendChild(page.mk('span', 'bp-spacer'));
  const lab = page.mk('label', 'tst-hide'), cb = page.mk('input');
  cb.type = 'checkbox';
  cb.checked = hidden;
  cb.onchange = () => { hidden = cb.checked; notify(); };
  lab.append(cb, document.createTextNode('Hide trades'));
  tabsEl.appendChild(lab);
}

function tileEl(t) {
  const el = page.mk('div', 'tst-tile');
  const v = page.mk('div', `tst-tile-v ${t.tone || ''}`, t.value);
  if (t.title) v.title = t.title;
  el.appendChild(v);
  el.appendChild(page.mk('div', 'tst-tile-l', t.label));
  if (t.sub) el.appendChild(page.mk('div', 'tst-tile-s', t.sub));
  return el;
}
function propBlock(propsim) {
  const view = X.propView(propsim);
  const wrap = page.mk('div', 'tst-prop');
  const head = page.mk('div', 'tst-prop-head');
  head.appendChild(page.mk('span', 'tst-prop-title', 'Prop eval' + (view.rules ? ` · ${view.rules.name}` : '')));
  if (view.unconfirmed) head.appendChild(page.mk('span', 'tst-badge warn', 'unconfirmed rules'));
  wrap.appendChild(head);
  if (view.tiles) {
    const g = page.mk('div', 'tst-tiles tst-tiles-small');
    for (const t of view.tiles) g.appendChild(tileEl(t));
    wrap.appendChild(g);
    if (view.caveat) wrap.appendChild(page.mk('div', 'tst-caveat', view.caveat));
  } else {
    wrap.appendChild(page.mk('div', 'bp-empty', view.message));
  }
  return wrap;
}
function renderOverview(container) {
  const { run, equity, propsim } = bundle;
  const badges = page.mk('div', 'tst-badges');
  for (const b of X.badges(run)) {
    const s = page.mk('span', `tst-badge ${b.tone}`, b.text);
    if (b.title) s.title = b.title;
    badges.appendChild(s);
  }
  container.appendChild(badges);
  const tiles = page.mk('div', 'tst-tiles');
  for (const t of X.tiles(run)) tiles.appendChild(tileEl(t));
  container.appendChild(tiles);
  const chartWrap = page.mk('div', 'tst-chart');
  container.appendChild(chartWrap);
  miniChartHandle = miniChart(chartWrap, equity, palette());
  container.appendChild(propBlock(propsim));
}

function kvTable(rows) {
  const t = page.mk('table', 'bp-table'), tbody = page.mk('tbody');
  for (const [k, v] of rows) {
    const tr = page.mk('tr');
    tr.append(page.mk('td', '', k), page.mk('td', '', v == null || v === '' ? '—' : String(v)));
    tbody.appendChild(tr);
  }
  t.appendChild(tbody);
  return t;
}
function summaryTable(headers, rows, numFrom) {
  const t = page.mk('table', 'bp-table'), thead = page.mk('thead'), htr = page.mk('tr');
  headers.forEach((h, i) => htr.appendChild(page.mk('th', i >= numFrom ? 'num' : '', h)));
  thead.appendChild(htr);
  t.appendChild(thead);
  const tbody = page.mk('tbody');
  for (const cells of rows) {
    const tr = page.mk('tr');
    cells.forEach((c, i) => tr.appendChild(page.mk('td', i >= numFrom ? 'num' : '', c)));
    tbody.appendChild(tr);
  }
  t.appendChild(tbody);
  return t;
}
function renderSummary(container) {
  const { run } = bundle;
  const rows = X.summaryRows(run.report.summary).map((r) => [r.label, r.all, r.long, r.short]);
  container.appendChild(summaryTable(['', 'All', 'Long', 'Short'], rows, 1));
  container.appendChild(page.mk('div', 'set-cap', 'BY YEAR'));
  container.appendChild(periodTable(run.report.by_year));
  const det = document.createElement('details'), sum = document.createElement('summary');
  sum.textContent = 'By month';
  det.appendChild(sum);
  det.appendChild(periodTable(run.report.by_month));
  container.appendChild(det);
}
function periodTable(list) {
  const rows = X.periodRows(list).map((p) => [p.period, p.trades, p.net, p.win, p.pf, p.dd, p.sharpe, p.avg]);
  return summaryTable(['Period', 'Trades', 'Net', 'Win %', 'PF', 'Max DD', 'Sharpe', 'Avg trade'], rows, 1);
}

function skippedList(title, list) {
  const items = list.map((s) => `${s.date} — ${s.reason}`);
  const ul = page.mk('ul', 'tst-list');
  for (const s of items) ul.appendChild(page.mk('li', '', s));
  if (list.length > 10) {
    const det = document.createElement('details'), sum = document.createElement('summary');
    sum.textContent = `${title} (${list.length})`;
    det.append(sum, ul);
    return det;
  }
  const wrap = page.mk('div');
  wrap.append(page.mk('div', 'set-cap', title), ul);
  return wrap;
}
function renderProperties(container) {
  const { run } = bundle, schema = schemaFor(run.strategy.id);
  const rows = [['Strategy', `${run.strategy.name} (${run.strategy.id}) · ${run.strategy.root}`]];
  for (const inp of (schema ? schema.inputs : [])) {
    const v = run.inputs[inp.key];
    rows.push([inp.label, typeof v === 'boolean' ? (v ? 'on' : 'off') : String(v)]);
  }
  rows.push(['Range', run.range.label], ['Qty', run.qty], ['Commission', Tr.money(run.commission)],
    ['Slippage', `${run.slippage_ticks} ticks`], ['Capital', Tr.money(run.capital)], ['Prop rules', run.prop_rules]);
  container.appendChild(kvTable(rows));
  const c = run.coverage || {};
  container.appendChild(page.mk('div', 'tst-kv-line', `Sessions: ${c.used ?? 0} / ${c.sessions ?? 0}`));
  if ((c.skipped || []).length) container.appendChild(skippedList('Skipped sessions', c.skipped));
  if ((c.no_trade || []).length) container.appendChild(skippedList('No-trade sessions', c.no_trade));
  container.appendChild(kvTable([['Engine', run.engine], ['Fill law', run.fill_law]]));
  if (run.holdout) container.appendChild(kvTable([['Holdout reason', run.holdout_reason || '']]));
  container.appendChild(kvTable([['Run id', run.id], ['Created', run.created], ['Finished', run.finished]]));
}

function selectTrade(i) {
  selectedTrade = i;
  if (innerTab === 'trades') refreshContent();
  notify();
}
function renderTrades(container) {
  const trades = bundle.trades || [];
  const tick = tickForRoot(bundle.run.strategy.root);
  const order = X.sortTrades(trades, sortCol, sortDir);
  const table = page.mk('table', 'bp-table'), thead = page.mk('thead'), htr = page.mk('tr');
  TRADE_COLS.forEach(([key, label, num]) => {
    const th = page.mk('th', num ? 'num' : '');
    if (key) {
      const b = page.mk('button', 'sort-th', label + (sortCol === key ? (sortDir === 1 ? ' ▲' : ' ▼') : ''));
      b.type = 'button';
      b.onclick = () => { sortDir = sortCol === key ? -sortDir : 1; sortCol = key; refreshContent(); };
      th.appendChild(b);
    } else th.textContent = label;
    htr.appendChild(th);
  });
  thead.appendChild(htr);
  table.appendChild(thead);
  const tbody = page.mk('tbody');
  const shown = order.slice(0, visibleTradeRows);
  for (const idx of shown) {
    const t = trades[idx];
    const tr = page.mk('tr', selectedTrade === idx ? 'sel' : '');
    X.tradeCells(t, idx, tick).forEach((cell, i) => {
      const td = page.mk('td', TRADE_COLS[i][2] ? 'num' : '', cell);
      if (i === 8) td.classList.add(t.net > 0 ? 'up' : t.net < 0 ? 'down' : '');
      tr.appendChild(td);
    });
    tr.onclick = () => { selectTrade(idx); if (window.HBTesterLayer) window.HBTesterLayer.jump(idx); };
    tbody.appendChild(tr);
  }
  if (order.length > shown.length) {
    const tr = page.mk('tr'), td = page.mk('td', 'tst-more-cell');
    td.colSpan = TRADE_COLS.length;
    const more = page.mk('button', 'bp-act tst-more', `Show more (${order.length - shown.length} left)`);
    more.type = 'button';
    more.onclick = () => { visibleTradeRows += TRADE_CHUNK; refreshContent(); };
    td.appendChild(more);
    tr.appendChild(td);
    tbody.appendChild(tr);
  }
  table.appendChild(tbody);
  container.appendChild(table);
}

const EMPTY_MSG = { overview: 'Run the strategy to see a report', summary: 'Run the strategy to see a performance summary',
  trades: 'Run the strategy to see its trades', properties: 'Run the strategy to see its properties' };
function refreshContent() {
  dropMiniChart();
  contentEl.replaceChildren();
  if (!bundle) { contentEl.appendChild(page.mk('div', 'bp-empty', EMPTY_MSG[innerTab])); return; }
  if (innerTab === 'overview') renderOverview(contentEl);
  else if (innerTab === 'summary') renderSummary(contentEl);
  else if (innerTab === 'trades') renderTrades(contentEl);
  else renderProperties(contentEl);
}

/* ================================================================== strategy switching / mount ================================================================== */

function switchStrategy(id) {
  strategyId = id;
  form = X.restore(store.forms[id], schemaFor(id));
  bundle = null;
  loadedKey = null;
  innerTab = 'overview';
  visibleTradeRows = TRADE_CHUNK;
  selectedTrade = null;
  persist();
  refreshHeader();
  refreshTabsBar();
  refreshContent();
  notify();
}

function buildFull() {
  root.replaceChildren();
  store = loadStore();
  strategyId = (strategiesList.some((s) => s.id === store.strategy) ? store.strategy : strategiesList[0].id);
  form = X.restore(store.forms[strategyId], schemaFor(strategyId));
  headerEl = page.mk('div', 'tst-head');
  tabsEl = page.mk('div', 'tst-tabs');
  contentEl = page.mk('div', 'tst-content');
  root.append(headerEl, tabsEl, contentEl);
  refreshHeader();
  refreshTabsBar();
  refreshContent();
}

function render(el) {
  if (el.querySelector(':scope > .tst')) return;   // a desk event re-render onto our own, still-live DOM: leave it
  root = page.mk('div', 'tst');
  el.appendChild(root);
  if (strategiesList && strategiesList.length) { buildFull(); return; }
  root.appendChild(page.mk('div', 'bp-empty', 'Loading strategies…'));
  Promise.all([loadStrategies(), loadPropRules()]).then(() => {
    if (!root.isConnected) return;   // the tab was hidden (or shown again) while this was in flight
    if (!strategiesList.length) { root.replaceChildren(page.mk('div', 'bp-empty', 'Could not load the strategy list')); return; }
    buildFull();
  });
}
function onHide() { dropMiniChart(); }

function mount(pg) {
  page = pg;
  loadStrategies();
  loadPropRules();
  window.HBPanel.addTab({ id: 'tester', label: 'Strategy Tester', render, onHide });
}

window.HBTesterUI = {
  mount,
  get bundle() { return bundle; },
  get selected() { return selectedTrade; },
  get hidden() { return hidden; },
  on(fn) { listeners.add(fn); return () => listeners.delete(fn); },
  select(i) { selectedTrade = i; if (innerTab === 'trades') refreshContent(); notify(); },
};
})();
