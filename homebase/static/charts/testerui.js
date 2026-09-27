/* Homebase Charts — HBTesterUI: the Strategy Tester tab (HBPanel.addTab), built on HBTester (the pure
   model: form defaults/validation, the request body, progress text, tiles/tables/marks). This module owns
   the DOM only: the header row (strategy, inputs dialog, range, costs, holdout, run/progress/cancel, recent
   runs), the inner Overview / Performance summary / List of trades / Properties / Heat-map tabs, and the mini
   equity + drawdown chart.

   Heat-map: 2 or 3 inputs x value lists (<= 60 cells) run as a grid on the research window 2021-2024 ONLY
   (the server forces it; the Holdout switch is disabled on that tab). Each cell is a full single run: a
   click loads its bundle into the other tabs. The grid DOM is built once per grid (or tab show) and every
   poll PATCHES its cells in place -- never a rebuild (and a desk-event render() is a no-op, see below).

   Walk-forward: the same axis rows (shared with the heat-map) + a selection metric and a minimum trade
   count, run server-side as 1 month to select / the next 3 to test, stepping monthly, on 2021-2024 ONLY
   (homebase/backtest/walkforward.py). Its config + body are built once per job (or tab show); polls patch
   the progress bar/text (with ETA) in place; the result is fetched once when the job is done. Its controls
   are disabled while it runs. Full-window cell results are never shown -- only the picked cells'
   selection-month stats and their out-of-sample test legs.

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

const COST_FIELDS = [['qty', 'Qty', 1, 100, 1], ['commission', 'Commission $/RT (per contract)', 0, 100, 0.01],
  ['slippage_ticks', 'Slippage (ticks)', 0, 20, 0.25]];
const INNER_TABS = [['overview', 'Overview'], ['summary', 'Performance summary'], ['trades', 'List of trades'],
  ['properties', 'Properties'], ['heatmap', 'Heat-map'], ['walkforward', 'Walk-forward']];
const RESEARCH_ONLY_TABS = new Set(['heatmap', 'walkforward']);   // the Holdout switch doesn't apply there
const AXIS_ROLES = ['Rows', 'Columns', 'Panels'];
const TRADE_COLS = [['n', '#', true], ['side', 'Side', false], ['entry', 'Entry time', false], [null, 'Entry price', true],
  ['exit', 'Exit time', false], [null, 'Exit price', true], ['reason', 'Reason', false], ['qty', 'Qty', true],
  ['net', 'Net', true], ['mae', 'MAE', true], ['mfe', 'MFE', true], ['dur', 'Duration', true]];
const TRADE_CHUNK = 500;
// M4: LightweightCharts renders `time` (unix seconds) as UTC by default; every other chart in this app
// reads ET (cell.js's own comment: "Bar times arrive as ET wall-clock seconds, so the axis reads ET").
// The mini chart's `time` values are real epoch seconds (X.equitySeries, unshifted -- its own Node tests
// pin that), so ET-ness has to come from formatting here, not from the data.
const ET_TICK = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', month: 'short', day: 'numeric' });

let page = null;

/* ---- strategies / prop rules: fetched once, cached ---- */
let strategiesList = null, propRulesList = null;
let strategiesPromise = null, propRulesPromise = null;
/* M7: a failed (or empty) load must not wedge the tab on "Could not load…" forever -- clearing the cached
   promise lets the next render() (the next time the tab is shown) try again, instead of replaying the
   same rejection/empty list from cache indefinitely. */
function loadStrategies() {
  if (!strategiesPromise) {
    strategiesPromise = fetch('/api/tester/strategies').then((r) => (r.ok ? r.json() : [])).catch(() => [])
      .then((list) => {
        strategiesList = Array.isArray(list) ? list : [];
        if (!strategiesList.length) strategiesPromise = null;
        return strategiesList;
      });
  }
  return strategiesPromise;
}
function loadPropRules() {
  if (!propRulesPromise) {
    propRulesPromise = fetch('/api/tester/prop-rules').then((r) => (r.ok ? r.json() : [])).catch(() => [])
      .then((list) => {
        propRulesList = Array.isArray(list) ? list : [];
        if (!propRulesList.length) propRulesPromise = null;
        return propRulesList;
      });
  }
  return propRulesPromise;
}
function schemaFor(id) { return (strategiesList || []).find((s) => s.id === id) || (strategiesList || [])[0] || null; }

/* ---- per-viewer persisted form ({strategy, forms: {id: form}, rules} in localStorage hb_tester) ---- */
const STORE_KEY = 'hb_tester';
let store = { strategy: null, forms: {}, heat: {}, wf: {}, rules: true };
function loadStore() {
  const obj = (x) => (x && typeof x === 'object' ? x : {});
  const empty = { strategy: null, forms: {}, heat: {}, wf: {}, rules: true };
  try {
    const v = JSON.parse(localStorage.getItem(STORE_KEY) || 'null');
    return (v && typeof v === 'object') ? { strategy: v.strategy || null, forms: obj(v.forms), heat: obj(v.heat),
      wf: obj(v.wf), rules: v.rules !== false } : empty;
  } catch (_) { return empty; }
}
function saveStore() {
  try { localStorage.setItem(STORE_KEY, JSON.stringify(store)); } catch (_) { /* storage off: this session only */ }
}

/* ---- state ---- */
let strategyId = null;
let form = null;
let loadedKey = null;      // HBTester.key of the form that produced `bundle`, or null
let bundle = null;         // {run, trades, equity, plots, propsim} or null
let serverError = '';      // a 400 detail, or a submit-time refusal -- cleared on the next form edit (persist())
let lastRunFailed = '';    // M1: sticks above the content -- unlike serverError -- until the NEXT successful load
let submittedKey = null, submittedStrategy = null;   // I1: a snapshot of what was actually sent, for the in-flight run
let runId = null;
let runStatus = null;      // the last polled status, or null (no run in flight / just finished)
let pollToken = 0;
let innerTab = 'overview';
let hidden = false;
let rules = true;          // the "Rules" tick: the strategy's own levels + gate plots on the chart
let selectedTrade = null;
let sortCol = 'n', sortDir = 1;
let visibleTradeRows = TRADE_CHUNK;
let miniChartHandle = null;
let mc = { runId: null, src: null, floor: null, loading: false, error: '', result: null };   // Monte Carlo, keyed to bundle.run.id
let mcToken = 0;
/* Compare two runs: picked from Recent runs (<= 2 ids), then the Compare tab's own loaded bundles. */
let compareIds = [];
let compare = null;         // { aId, bId, a: bundle, b: bundle } once both load
let compareLoading = false;
let compareErr = '';
let compareToken = 0;
let compareChartHandle = null;
const listeners = new Set();
/* the heat-map */
let heatRows = null;       // [{key, text}] x 3 for strategyId (key '' = unused): the axis editor
let grid = null;           // the last polled grid status (server shape), or null
let gridToken = 0;
let gridStarting = false;  // POST in flight
let gridErr = '';          // a 400 detail / lost contact -- cleared on the next axis edit
let looksMap = {};         // {strategy: looks}
let heatCell = null;       // {gid, i}: the cell whose report is loaded in the other tabs
let heatResumed = false;   // the newest grid of this strategy was looked up once (page reload / strategy switch)
let looksErr = '';         // GET /looks refused (a corrupt looks.json): shown, never read as 0
let heatCfgEl = null, heatErrEl = null, heatCountEl = null, heatLooksEl = null, heatRunEl = null, heatNoteEl = null;
let heatGridEl = null, heatProgBar = null, heatProgText = null;
let heatCellEls = new Map();
/* the walk-forward */
let wf = null;             // the last polled walk-forward status (server shape), or null
let wfToken = 0;
let wfStarting = false;    // POST in flight
let wfErr = '';            // a 400 detail / lost contact -- cleared on the next edit
let wfResult = null;       // { id, result } -- fetched once per finished job
let wfResultErr = '';
let wfResumed = false;
let wfCfgEl = null, wfErrEl = null, wfCountEl = null, wfLooksEl = null, wfRunEl = null, wfBodyEl = null;
let wfProgBar = null, wfProgText = null, wfChartHandle = null;
let wfScheme = null, wfSchemePromise = null;   // GET /api/tester/walkforward-scheme: the step count (review M5)

/* ---- DOM roots, rebuilt by render(); refreshed in place by everything else ---- */
let root = null, headerEl = null, holdoutBannerEl = null, tabsEl = null, contentEl = null;
let errEl = null, runBtn = null, progressBarEl = null, progressTextEl = null;

function notify() { for (const fn of [...listeners]) { try { fn(); } catch (e) { console.error(e); } } }
function persist() {
  serverError = '';
  store.strategy = strategyId;
  store.forms[strategyId] = form;
  saveStore();
}

/* C1 (critical): a valid, armed holdout run -- the switch is on, the range actually reaches 2025+, and the
   reason is a valid one-liner -- i.e. exactly the condition under which the NEXT Run click spends holdout
   data and gets logged. Mirrors the same check `HBTester.problems()` makes for the holdout block, so the
   amber warning and the "spends holdout" button label track it exactly. */
function holdoutArmed(f) {
  if (!f.holdout.on || !X.reachesHoldout(f.range)) return false;
  const why = (f.holdout.reason || '').trim();
  return !!why && !why.includes('\n') && why.length <= REASON_MAX;
}
function runLabelFor() { return holdoutArmed(form) ? 'Run · spends holdout' : X.runLabel(form, loadedKey); }

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
  return dark ? { text2: '#8C8C8C', grid: '#1C1C1C', up: '#089981', down: '#F23645', accent: '#2962FF', warn: '#F7A600' }
              : { text2: '#787B86', grid: '#F0F3FA', up: '#089981', down: '#F23645', accent: '#2962FF', warn: '#F7A600' };
}

/* ---- the Overview mini chart (equity + drawdown), verbatim per the task brief ---- */
function miniChart(el, equity, P) {
  const LW = window.LightweightCharts, s = X.equitySeries(equity);
  const chart = LW.createChart(el, { autoSize: true, height: 180,
    layout: { background: { color: 'transparent' }, textColor: P.text2, fontSize: 11, attributionLogo: false,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif' },
    grid: { vertLines: { visible: false }, horzLines: { color: P.grid } },
    // M4: ET, not the browser's UTC default -- tick labels via tickMarkFormatter, the crosshair via
    // localization.timeFormatter (X.fmtEt, the same ET formatter every trade time in this tab already uses).
    localization: { timeFormatter: (t) => X.fmtEt(t * 1000) },
    rightPriceScale: { borderVisible: false },
    timeScale: { borderVisible: false, tickMarkFormatter: (t) => ET_TICK.format(new Date(t * 1000)) },
    handleScroll: false, handleScale: false });
  const eq = chart.addSeries(LW.AreaSeries, { lineColor: P.up, topColor: 'rgba(8,153,129,.28)', bottomColor: 'rgba(8,153,129,0)',
    lineWidth: 2, priceFormat: { type: 'price', precision: 0, minMove: 1 }, lastValueVisible: false, priceLineVisible: false });
  eq.setData(s.equity);
  // M4: drawdown is <= 0 -- without invertFilledArea the fill runs from the line down to the pane's own
  // bottom, so a DEEPER drawdown (a line already near the bottom) paints LESS red. Inverting fills from
  // the line up to zero instead, so a deeper drawdown reads as more red, not less.
  const dd = chart.addSeries(LW.AreaSeries, { lineColor: P.down, topColor: 'rgba(242,54,69,0)', bottomColor: 'rgba(242,54,69,.35)',
    lineWidth: 1, priceFormat: { type: 'price', precision: 0, minMove: 1 }, lastValueVisible: false, priceLineVisible: false,
    invertFilledArea: true }, 1);
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
function dropCompareChart() {
  if (!compareChartHandle) return;
  try { compareChartHandle.remove(); } catch (_) { /* already gone */ }
  compareChartHandle = null;
}
/* The Compare tab's overlaid equity + drawdown chart, verbatim in spirit with miniChart() above:
   run A in accent blue, run B in warn orange (Global Constraints: "look like TradingView" -- reusing
   the app's own tokens rather than inventing a new colour pair). */
function compareChart(el, eqA, eqB, P) {
  const LW = window.LightweightCharts, sa = X.equitySeries(eqA), sb = X.equitySeries(eqB);
  const priceFmt = { type: 'price', precision: 0, minMove: 1 };
  const chart = LW.createChart(el, { autoSize: true, height: 260,
    layout: { background: { color: 'transparent' }, textColor: P.text2, fontSize: 11, attributionLogo: false,
      fontFamily: '-apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif' },
    grid: { vertLines: { visible: false }, horzLines: { color: P.grid } },
    localization: { timeFormatter: (t) => X.fmtEt(t * 1000) },
    rightPriceScale: { borderVisible: false },
    timeScale: { borderVisible: false, tickMarkFormatter: (t) => ET_TICK.format(new Date(t * 1000)) },
    handleScroll: false, handleScale: false });
  const eqLineA = chart.addSeries(LW.LineSeries, { color: P.accent, lineWidth: 2, priceFormat: priceFmt,
    lastValueVisible: false, priceLineVisible: false });
  eqLineA.setData(sa.equity);
  const eqLineB = chart.addSeries(LW.LineSeries, { color: P.warn, lineWidth: 2, priceFormat: priceFmt,
    lastValueVisible: false, priceLineVisible: false });
  eqLineB.setData(sb.equity);
  const ddA = chart.addSeries(LW.AreaSeries, { lineColor: P.accent, topColor: 'rgba(41,98,255,0)', bottomColor: 'rgba(41,98,255,.25)',
    lineWidth: 1, priceFormat: priceFmt, lastValueVisible: false, priceLineVisible: false, invertFilledArea: true }, 1);
  ddA.setData(sa.drawdown);
  const ddB = chart.addSeries(LW.AreaSeries, { lineColor: P.warn, topColor: 'rgba(247,166,0,0)', bottomColor: 'rgba(247,166,0,.25)',
    lineWidth: 1, priceFormat: priceFmt, lastValueVisible: false, priceLineVisible: false, invertFilledArea: true }, 1);
  ddB.setData(sb.drawdown);
  chart.panes()[1].setStretchFactor(0.35);
  chart.timeScale().fitContent();
  return chart;
}

/* ================================================================== header ================================================================== */

function computeErrorText() { return serverError || X.problems(form, schemaFor(strategyId)) || ''; }
function updateHoldoutBanner() {
  if (!holdoutBannerEl) return;
  const armed = holdoutArmed(form);
  holdoutBannerEl.hidden = !armed;
  if (armed) holdoutBannerEl.textContent = 'This run spends holdout data (2025+) — logged';
}
/* A cheap, focus-preserving update for the fields a viewer types into (qty/commission/slippage, the holdout
   reason): recompute the error line, the holdout banner and the Run label without rebuilding the header. */
function syncRunState() {
  const text = computeErrorText();
  if (errEl) { errEl.textContent = text; errEl.hidden = !text; }
  updateHoldoutBanner();
  syncHeat();
  if (runBtn) { const label = runLabelFor(); runBtn.lastChild.textContent = ' ' + label; runBtn.setAttribute('aria-label', label); }
}
function updateProgressUI() {
  const p = X.progress(runStatus);
  if (progressTextEl) progressTextEl.textContent = p.text;
  if (progressBarEl) { if (p.frac == null) progressBarEl.removeAttribute('value'); else progressBarEl.value = p.frac; }
}

function optionEl(value, text) { const o = document.createElement('option'); o.value = value; o.textContent = text; return o; }

function strategySelect(busy) {
  const sel = page.mk('select', 'set-select tst-strat');
  sel.setAttribute('aria-label', 'Strategy');
  sel.disabled = busy;
  for (const s of strategiesList) sel.appendChild(optionEl(s.id, s.name));
  sel.value = strategyId;
  sel.onchange = () => switchStrategy(sel.value);
  return sel;
}
function iconBtn(name, title, onClick, busy) {
  const b = page.mk('button', 'tst-icon-btn');
  b.type = 'button';
  b.title = title;
  b.setAttribute('aria-label', title);
  b.disabled = !!busy;
  b.appendChild(page.icon(name));
  b.onclick = onClick;
  return b;
}
/* I3: the date inputs show only for Custom, and leaving Custom clears start/end -- otherwise a range
   switched away from Custom (e.g. to IS months) silently kept sending the old, narrower window, and a
   hidden holdout end date could force the switch on for a range the viewer could no longer see. */
function rangeGroup(busy) {
  const wrap = page.mk('span', 'tst-group');
  const sel = page.mk('select', 'set-select');
  sel.setAttribute('aria-label', 'Range');
  sel.disabled = busy;
  for (const r of X.RANGES) sel.appendChild(optionEl(r.kind, r.label));
  sel.value = form.range.kind;
  sel.onchange = () => {
    const kind = sel.value;
    form.range = { kind, start: kind === 'custom' ? form.range.start : '', end: kind === 'custom' ? form.range.end : '' };
    persist();
    refreshHeader();
  };
  wrap.appendChild(sel);
  if (form.range.kind === 'custom') {
    const start = page.mk('input'), end = page.mk('input');
    start.type = 'date'; start.value = form.range.start || ''; start.setAttribute('aria-label', 'Range start'); start.disabled = busy;
    end.type = 'date'; end.value = form.range.end || ''; end.setAttribute('aria-label', 'Range end'); end.disabled = busy;
    // NEVER refreshHeader() from here: <input type="date"> fires `change` as soon as the value parses,
    // which is the FIRST digit of the year -- rebuilding the header there destroys the field under the
    // caret and leaves a half-typed year (the reported "07/01/0001"). syncRunState() keeps the error
    // text, the holdout banner and the Run label current without touching the inputs, as the cost
    // fields and the holdout reason already do.
    start.onchange = () => { form.range = { ...form.range, start: start.value }; persist(); syncRunState(); };
    end.onchange = () => { form.range = { ...form.range, end: end.value }; persist(); syncRunState(); };
    wrap.append(start, end);
  }
  return wrap;
}
function costInput(key, label, lo, hi, step, busy) {
  const wrap = page.mk('span', 'tst-cost'), lab = page.mk('label', 'tst-cost-l', label), inp = page.mk('input', 'tst-num');
  inp.type = 'number'; inp.min = String(lo); inp.max = String(hi); inp.step = String(step); inp.value = String(form[key]);
  inp.id = `tst-cost-${key}`; lab.htmlFor = inp.id; inp.disabled = busy;
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
  if (RESEARCH_ONLY_TABS.has(innerTab)) {   // the heat-map / walk-forward are the research window only: the switch doesn't apply
    const off = page.mk('button', 'switch');
    off.type = 'button';
    off.disabled = true;
    off.setAttribute('role', 'switch');
    off.setAttribute('aria-checked', 'false');
    off.setAttribute('aria-label', 'Holdout (research window only)');
    wrap.append(lab, off, page.mk('span', 'tst-cost-l', 'research window only'));
    return wrap;
  }
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
    runBtn.append(page.icon('play'), document.createTextNode(' ' + runLabelFor()));
    runBtn.onclick = startRun;
    wrap.appendChild(runBtn);
  }
  return wrap;
}
function recentRunsBtn(busy) {
  const b = page.mk('button', 'tst-btn');
  b.type = 'button';
  b.setAttribute('aria-haspopup', 'menu');
  b.setAttribute('aria-expanded', 'false');
  b.disabled = busy;
  b.append(page.icon('history'), document.createTextNode(' Recent runs'), page.icon('chevron'));
  b.onclick = () => page.toggleMenu(b, () => fillRecentRunsMenu(page.openMenu(b, 'menu-tester-runs')));
  return b;
}

/* I1: while a run is in flight, the strategy select, gear, range/dates and costs are disabled -- editing
   any of them mid-run used to let a stale report land under a form (or even a strategy) that no longer
   matches it, with the button still reading "Run" as if they matched. The holdout switch/reason are left
   live (they can't change what's already in flight, since the range is frozen). */
/* A rebuild must never land under the caret. Any header field being typed in (a run finishing, a desk
   event, a poll) defers the rebuild to that field's blur; selects and buttons rebuild at once, so
   switching the range kind still swaps the date inputs in immediately. */
let headerBlurPending = false;
function refreshHeader() {
  const act = document.activeElement;
  if (act && act.tagName === 'INPUT' && headerEl && headerEl.contains(act)) {
    if (!headerBlurPending) {
      headerBlurPending = true;
      act.addEventListener('blur', () => { headerBlurPending = false; refreshHeader(); }, { once: true });
    }
    syncRunState();
    return;
  }
  const schema = schemaFor(strategyId);
  const busy = !!runStatus;
  headerEl.replaceChildren();
  headerEl.appendChild(strategySelect(busy));
  headerEl.appendChild(iconBtn('gear', `${schema.name} · Inputs`, openInputsDialog, busy));
  headerEl.appendChild(rangeGroup(busy));
  for (const [key, label, lo, hi, step] of COST_FIELDS) headerEl.appendChild(costInput(key, label, lo, hi, step, busy));
  headerEl.appendChild(holdoutGroup());
  headerEl.appendChild(runArea());
  headerEl.appendChild(recentRunsBtn(busy));
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
/* The Eval picker — which funded-account evaluation the prop numbers are scored against.
   One builder, used both in the inputs dialog and beside the prop-eval tiles themselves, so
   "pick the eval it's running" is answerable from where the numbers are. */
function evalSelect(selected, onPick) {
  const sel = page.mk('select', 'set-select');
  for (const o of X.evalOptions(propRulesList, selected)) sel.appendChild(optionEl(o.id, o.label));
  sel.value = selected;
  sel.onchange = () => onPick(sel.value);
  return sel;
}
function propRulesRow(draft) {
  const row = page.mk('div', 'field'), lab = page.mk('label', '', 'Eval'), id = 'ti-eval';
  const sel = evalSelect(draft.prop_rules, (v) => { draft.prop_rules = v; });
  sel.id = id;
  lab.htmlFor = id;
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
      const e = X.inputError(inp, draft.inputs[inp.key]);
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
  const line = page.mk('span', 'menu-t');
  if (done) {
    // M3: a signed $ with a tone (Tr.usd), not the unsigned Tr.money that read a win the same as a loss.
    const net = Tr.usd(r.net_profit) ?? '—', tone = X.toneOf(r.net_profit);
    line.append(document.createTextNode(`${stratName} · ${rangeLabel} · `), page.mk('span', tone, net),
      document.createTextNode(` · ${r.trades ?? 0} trades`));
  } else {
    line.textContent = `${stratName} · ${rangeLabel} · ${r.status}`;
  }
  b.appendChild(line);
  if (r.holdout) b.appendChild(page.mk('span', 'env live', 'HOLDOUT'));
  if (done) b.onclick = () => { page.closeMenu(); loadRecentRun(r.id); };
  if (!done) return b;      // only a finished run has a report to compare
  const row = page.mk('div', 'menu-row');
  const cb = page.mk('input', 'tst-cmp-cb');
  cb.type = 'checkbox';
  cb.checked = compareIds.includes(r.id);
  cb.setAttribute('aria-label', `Pick ${stratName} · ${rangeLabel} to compare`);
  cb.dataset.runId = r.id;
  cb.onchange = () => {
    if (cb.checked) {
      if (compareIds.length >= 2) { cb.checked = false; return; }
      compareIds = [...compareIds, r.id];
    } else {
      compareIds = compareIds.filter((id) => id !== r.id);
    }
    syncCompareFooter(row.parentElement);
  };
  row.append(cb, b);
  return row;
}
function compareFooter() {
  const wrap = page.mk('div', 'menu-confirm tst-cmp-footer');
  wrap.appendChild(page.mk('span', 'tst-cmp-footer-t', ''));
  const btn = page.mk('button', 'btn btn-primary tst-cmp-go', 'Compare');
  btn.type = 'button';
  wrap.appendChild(btn);
  return wrap;
}
/* Focus-preserving: the footer text/button state and every checkbox's disabled state (a 3rd pick is
   refused, not silently swapped for one already ticked). */
function syncCompareFooter(m) {
  if (!m || !document.body.contains(m)) return;
  const label = m.querySelector('.tst-cmp-footer-t'), btn = m.querySelector('.tst-cmp-go');
  if (label) label.textContent = compareIds.length >= 2 ? '2 runs picked'
    : `Pick ${2 - compareIds.length} more run${compareIds.length === 1 ? '' : 's'} to compare`;
  if (btn) btn.disabled = compareIds.length !== 2;
  m.querySelectorAll('.tst-cmp-cb').forEach((cb) => {
    cb.disabled = compareIds.length >= 2 && !compareIds.includes(cb.dataset.runId);
  });
}
function fillRecentRunsMenu(m) {
  m.appendChild(page.mk('div', 'menu-empty', 'Loading…'));
  fetch('/api/tester/runs').then((r) => (r.ok ? r.json() : [])).catch(() => [])
    .then((list) => {
      if (!document.body.contains(m)) return;   // closed while loading
      m.replaceChildren();
      if (!list.length) { m.appendChild(page.mk('div', 'menu-empty', 'No runs yet')); page.placeMenu(); return; }
      compareIds = compareIds.filter((id) => list.some((r) => r.id === id && r.status === 'done'));
      for (const r of list) m.appendChild(recentRunRow(r));
      const footer = compareFooter();
      footer.querySelector('.tst-cmp-go').onclick = () => { const ids = compareIds; page.closeMenu(); startCompare(ids); };
      m.appendChild(footer);
      syncCompareFooter(m);
      page.placeMenu();
    });
}

/* ================================================================== compare two runs ================================================================== */

function startCompare(ids) {
  if (ids.length !== 2) return;
  const [aId, bId] = ids;
  compare = { aId, bId, a: null, b: null };
  compareLoading = true;
  compareErr = '';
  compareIds = [];
  innerTab = 'compare';
  const token = ++compareToken;
  refreshTabsBar();
  refreshContent();
  const fetchOne = (id) => fetch(`/api/tester/run/${id}/bundle`).then((r) => (r.ok ? r.json() : Promise.reject(r.status)));
  Promise.all([fetchOne(aId), fetchOne(bId)])
    .then(([a, b]) => {
      if (token !== compareToken) return;
      compare = { aId, bId, a, b };
      compareLoading = false;
      if (innerTab === 'compare') refreshContent();
    })
    .catch(() => {
      if (token !== compareToken) return;
      compareLoading = false;
      compareErr = 'could not load one of the runs to compare';
      if (innerTab === 'compare') refreshContent();
    });
}
function closeCompare() {
  compare = null;
  compareErr = '';
  compareLoading = false;
  if (innerTab === 'compare') innerTab = 'overview';
  refreshTabsBar();
  refreshContent();
}
function runChip(run, colorClass, letter) {
  const chip = page.mk('span', `tst-cmp-chip ${colorClass}`);
  chip.appendChild(page.mk('span', 'tst-cmp-dot'));
  const stratName = ((strategiesList || []).find((s) => s.id === run.strategy.id) || {}).name || run.strategy.name;
  chip.appendChild(document.createTextNode(`${letter}: ${stratName} · ${run.range.label}`));
  if (run.holdout) chip.appendChild(page.mk('span', 'tst-badge err', 'holdout'));
  return chip;
}
function compareTable(rows) {
  const t = page.mk('table', 'bp-table'), thead = page.mk('thead'), htr = page.mk('tr');
  ['', 'A', 'B', 'Δ'].forEach((h, i) => htr.appendChild(page.mk('th', i ? 'num' : '', h)));
  thead.appendChild(htr);
  t.appendChild(thead);
  const tbody = page.mk('tbody');
  for (const r of rows) {
    const tr = page.mk('tr');
    tr.appendChild(page.mk('td', '', r.label));
    tr.appendChild(page.mk('td', `num${r.better === 'a' ? ' tst-cmp-better' : ''}`, r.a));
    tr.appendChild(page.mk('td', `num${r.better === 'b' ? ' tst-cmp-better' : ''}`, r.b));
    tr.appendChild(page.mk('td', 'num', r.delta));
    tbody.appendChild(tr);
  }
  t.appendChild(tbody);
  return t;
}
function renderCompare(container) {
  const wrap = page.mk('div', 'tst-cmp');
  const head = page.mk('div', 'tst-cmp-head');
  head.appendChild(page.mk('span', 'tst-prop-title', 'Compare'));
  head.appendChild(iconBtn('x', 'Close comparison', closeCompare));
  wrap.appendChild(head);
  container.appendChild(wrap);
  if (compareErr) { wrap.appendChild(page.mk('div', 'tst-err', compareErr)); return; }
  if (compareLoading || !compare || !compare.a || !compare.b) { wrap.appendChild(page.mk('div', 'bp-empty', 'Loading the two runs…')); return; }
  const { a, b } = compare;
  const legend = page.mk('div', 'tst-cmp-legend');
  legend.append(runChip(a.run, 'tst-cmp-a', 'A'), runChip(b.run, 'tst-cmp-b', 'B'));
  wrap.appendChild(legend);
  const chartWrap = page.mk('div', 'tst-cmp-chart');
  wrap.appendChild(chartWrap);
  compareChartHandle = compareChart(chartWrap, a.equity, b.equity, palette());
  wrap.appendChild(compareTable(X.compareRows(a.run.report, b.run.report, a.propsim, b.propsim)));
  const diff = X.paramsDiff(a.run, b.run);
  wrap.appendChild(page.mk('div', 'set-cap', 'PARAMS THAT DIFFER'));
  wrap.appendChild(diff.length ? kvTable(diff.map((d) => [d.label, `${d.a}  →  ${d.b}`])) : page.mk('div', 'bp-empty', 'Same parameters'));
}
function loadRecentRun(id) {
  fetch(`/api/tester/run/${id}/bundle`).then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((b) => {
      const schema = schemaFor(b.run.strategy.id);
      if (b.run.strategy.id !== strategyId) resetGrid();
      strategyId = b.run.strategy.id;
      form = X.fromRun(b.run, schema);
      bundle = b;
      startMonteCarlo(b.run.id);
      loadedKey = X.key(form);
      lastRunFailed = '';
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

/* I1: the strategy/gear/range/dates/costs are disabled while a run is in flight (refreshHeader), but
   submittedKey/submittedStrategy are still snapshotted here, belt-and-suspenders -- loadBundle uses the
   SNAPSHOT for loadedKey (not whatever `form` says once the run lands, which review I1 found could by
   then belong to a different strategy or an edited form) and drops the bundle outright if the live
   strategyId has since moved on from what was actually submitted. */
function startRun() {
  const schema = schemaFor(strategyId);
  const prob = X.problems(form, schema);
  if (prob) { serverError = ''; refreshHeader(); return; }
  const bodyObj = X.body(form);
  submittedKey = X.key(form);
  submittedStrategy = strategyId;
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
/* M2: one dropped status fetch used to end polling for good while the run carried on server-side. Retries
   3x with backoff (500ms, 1s, 2s) before finally giving up; any successful fetch resets the counter. */
function poll(rid, token, attempt = 0) {
  fetch(`/api/tester/run/${rid}`).then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((st) => {
      if (token !== pollToken) return;
      runStatus = st;
      updateProgressUI();
      const p = X.progress(st);
      if (!p.final) { setTimeout(() => poll(rid, token, 0), 500); return; }
      if (st.status === 'done') { loadBundle(rid, token); return; }
      runStatus = null;
      serverError = p.text;
      lastRunFailed = p.text;
      refreshHeader();
      refreshContent();
    })
    .catch(() => {
      if (token !== pollToken) return;
      if (attempt < 3) { setTimeout(() => poll(rid, token, attempt + 1), 500 * (2 ** attempt)); return; }
      runStatus = null;
      serverError = 'lost contact with the run';
      lastRunFailed = 'lost contact with the run';
      refreshHeader();
      refreshContent();
    });
}
function loadBundle(rid, token) {
  fetch(`/api/tester/run/${rid}/bundle`).then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((b) => {
      if (token !== pollToken) return;
      runStatus = null;
      // I1: dropped -- either the snapshot taken at submit time or the bundle's own recorded strategy no
      // longer matches what the header shows now (the controls are disabled mid-run, but this is the
      // belt-and-suspenders half of the fix: the header has moved on to another strategy some other way).
      if (submittedStrategy !== strategyId || b.run.strategy.id !== strategyId) {
        refreshHeader();
        return;
      }
      bundle = b;
      startMonteCarlo(b.run.id);
      loadedKey = submittedKey;
      lastRunFailed = '';   // M1: a successful load is the only thing that clears the stale-failure banner
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
      lastRunFailed = serverError;
      refreshHeader();
      refreshContent();
    });
}
function cancelRun() {
  if (!runId) return;
  fetch(`/api/tester/run/${runId}/cancel`, { method: 'POST' }).catch(() => { /* the next poll tick reflects reality either way */ });
}

/* ================================================================== inner tabs + content ================================================================== */

function refreshTabsBar() {
  tabsEl.replaceChildren();
  const tabs = compare ? [...INNER_TABS, ['compare', 'Compare']] : INNER_TABS;
  for (const [id, label] of tabs) {
    const b = page.mk('button', 'tst-tab' + (innerTab === id ? ' active' : ''), label);
    b.type = 'button';
    b.setAttribute('role', 'tab');
    b.setAttribute('aria-selected', String(innerTab === id));
    b.onclick = () => {
      const was = innerTab;
      innerTab = id;
      // the Holdout switch never carries into (or out of) the heat-map / walk-forward armed: it doesn't apply there
      if (RESEARCH_ONLY_TABS.has(id) !== RESEARCH_ONLY_TABS.has(was)) { if (form.holdout.on) form = { ...form, holdout: { ...form.holdout, on: false } }; refreshHeader(); }
      refreshTabsBar();
      refreshContent();
    };
    tabsEl.appendChild(b);
  }
  tabsEl.appendChild(page.mk('span', 'bp-spacer'));
  const lab = page.mk('label', 'tst-hide'), cb = page.mk('input');
  cb.type = 'checkbox';
  cb.checked = hidden;
  cb.onchange = () => { hidden = cb.checked; notify(); };
  lab.append(cb, document.createTextNode('Hide trades'));
  tabsEl.appendChild(lab);
  // "Rules": the levels the strategy PLACED (both straddle offsets, each leg's bracket, the leg that
  // never filled) and its gate plots -- independent of the trade markers, and remembered per viewer.
  const rl = page.mk('label', 'tst-hide'), rb = page.mk('input');
  rb.type = 'checkbox';
  rb.checked = rules;
  rb.onchange = () => { rules = rb.checked; store.rules = rules; saveStore(); notify(); };
  rl.append(rb, document.createTextNode('Rules'));
  rl.title = 'Show the levels the strategy placed: entries, stops, targets and gates';
  tabsEl.appendChild(rl);
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
/* ---- prop-eval re-score: the eval reads only the finished ledger, so picking another eval on a loaded
   run re-scores it server-side (POST /api/tester/propsim, cached there) -- a VIEW, the run's saved
   propsim.json is never overwritten. A heat-map cell re-scores via the {grid_id, cell} source its
   Monte Carlo already tracks. ---- */
let rescore = { runId: null, rulesId: null, loading: false, error: '', result: null };
let rescoreToken = 0;
function startRescore(run, rulesId) {
  const runId = run.id, token = ++rescoreToken;
  const src = mc.runId === runId && mc.src ? mc.src : { run_id: runId };
  const done = (patch) => { if (token !== rescoreToken) return; rescore = { runId, rulesId, loading: false, error: '', result: null, ...patch }; if (innerTab === 'overview') refreshContent(); };
  rescore = { runId, rulesId, loading: rulesId !== run.prop_rules, error: '', result: null };
  if (innerTab === 'overview') refreshContent();
  if (!rescore.loading) return;
  fetch('/api/tester/propsim', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ ...src, prop_rules: rulesId }) })
    .then(async (r) => {
      if (r.ok) return r.json();
      let d = '';
      try { d = (await r.json()).detail || ''; } catch (_) { /* no body */ }
      throw new Error(d || `request failed (${r.status})`);
    })
    .then((result) => done({ result }))
    .catch((e) => done({ error: `Re-scoring failed: ${e.message || 'unknown error'}` }));
}
function propBlock(saved, run) {
  const shown = X.propShown(saved, run.prop_rules, rescore, run.id);
  const view = X.propView(shown.propsim);
  const wrap = page.mk('div', 'tst-prop');
  const head = page.mk('div', 'tst-prop-head');
  head.appendChild(page.mk('span', 'tst-prop-title', 'Prop eval' + (view.rules ? ` · ${view.rules.name}` : '')));
  if (view.unconfirmed) head.appendChild(page.mk('span', 'tst-badge warn', 'unconfirmed rules'));
  if (shown.loading) {
    const sp = page.mk('span', 'tst-eval-spin');
    sp.setAttribute('role', 'status');
    sp.setAttribute('aria-label', 'Re-scoring');
    head.appendChild(sp);
  }
  // The picker re-scores THIS run under the chosen eval, and makes it the eval for the next run.
  const picker = page.mk('span', 'tst-eval-pick'), lab = page.mk('label', 'tst-cost-l', 'Eval');
  const sel = evalSelect(shown.rulesId, (v) => { form = { ...form, prop_rules: v }; persist(); refreshHeader(); startRescore(run, v); });
  sel.id = 'tst-eval-sel';
  lab.htmlFor = sel.id;
  picker.append(lab, sel);
  head.appendChild(picker);
  wrap.appendChild(head);
  if (shown.error) wrap.appendChild(page.mk('div', 'tst-err', shown.error));
  if (shown.rescored) wrap.appendChild(page.mk('div', 'tst-caveat', `Re-scored from this run's trades; the run was saved under ${run.prop_rules}.`));
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
/* ---- Monte Carlo (Overview sub-tab): fetched once per run id (and floor), cached in `mc` and on the server.
   `src` is {run_id} for a run, {grid_id, cell} for a heat-map cell (review I4). No seed is sent: the server
   derives one from the run id, so reopening a run shows the same numbers (review I2). ---- */
function startMonteCarlo(runId, src = { run_id: runId }, floor = null) {
  mc = { runId, src, floor, loading: true, error: '', result: null };
  const token = ++mcToken;
  const payload = floor == null ? src : { ...src, floor };
  const done = (patch) => { if (token !== mcToken) return; mc = { runId, src, floor, loading: false, error: '', result: null, ...patch }; if (innerTab === 'overview') refreshContent(); };
  fetch('/api/tester/montecarlo', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(payload) })
    .then(async (r) => {
      if (r.ok) return r.json();
      let d = '';
      try { d = (await r.json()).detail || ''; } catch (_) { /* no body */ }
      throw new Error(d || `request failed (${r.status})`);
    })
    .then((result) => done({ result }))
    .catch((e) => done({ error: `Monte Carlo failed to run: ${e.message || 'unknown error'}` }));
}
/* The ruin floor (review I1): P(max drawdown ≥ $floor), editable; committed on Enter / blur. */
function mcFloorInput() {
  const wrap = page.mk('span', 'tst-mc-floor'), lab = page.mk('label', 'tst-cost-l', 'Ruin = drawdown ≥ $');
  const inp = page.mk('input', 'tst-heat-vals tst-mc-floor-in');
  inp.id = 'tst-mc-floor';
  lab.htmlFor = inp.id;
  inp.type = 'number';
  inp.min = '1';
  inp.step = '100';
  inp.disabled = mc.loading;
  inp.value = mc.result ? String(mc.result.floor) : mc.floor != null ? String(mc.floor) : '';
  inp.onchange = () => {
    const v = Number(inp.value);
    if (!(inp.value.trim() && Number.isFinite(v) && v > 0)) { inp.value = mc.result ? String(mc.result.floor) : ''; return; }
    if (mc.result && v === mc.result.floor) return;
    startMonteCarlo(mc.runId, mc.src, v);
  };
  wrap.append(lab, inp);
  return wrap;
}
function mcBarsEl(r) {
  const wrap = page.mk('div', 'tst-mc-hist');
  for (const b of X.mcHistogram(r)) {
    const bar = page.mk('div', 'tst-mc-bar');
    bar.style.height = `${b.pct}%`;
    bar.title = b.title;
    wrap.appendChild(bar);
  }
  return wrap;
}
function mcBlock(runId) {
  const wrap = page.mk('div', 'tst-mc');
  const head = page.mk('div', 'tst-prop-head');
  head.appendChild(page.mk('span', 'tst-prop-title', 'Monte Carlo'));
  if (mc.runId === runId) head.appendChild(mcFloorInput());
  wrap.appendChild(head);
  if (mc.runId !== runId || mc.loading) { wrap.appendChild(page.mk('div', 'bp-empty', 'Running Monte Carlo…')); return wrap; }
  if (mc.error) { wrap.appendChild(page.mk('div', 'tst-err', mc.error)); return wrap; }
  if (!mc.result) return wrap;
  wrap.appendChild(page.mk('div', 'tst-caveat', X.mcHeadline(mc.result)));
  const g = page.mk('div', 'tst-tiles tst-tiles-small');
  for (const t of X.mcTiles(mc.result)) g.appendChild(tileEl(t));
  wrap.appendChild(g);
  wrap.appendChild(mcBarsEl(mc.result));
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
  container.appendChild(propBlock(propsim, run));
  container.appendChild(mcBlock(run.id));
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
      // I4: classList.add('') throws (a $0-net trade, e.g. a 1-tick winner the commission exactly
      // cancels) -- X.toneOf(0) is '', and an empty tone is simply never added.
      if (i === 8) { const tone = X.toneOf(t.net); if (tone) td.classList.add(tone); }
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
/* M1: `serverError` clears on the next keystroke (persist()), so a failed run's reason would otherwise
   vanish the moment the viewer touches anything -- leaving the (stale) last-good report with no note that
   it isn't from the latest attempt. `lastRunFailed` survives edits and sits above the content until the
   NEXT successful load (loadBundle / loadRecentRun / switchStrategy clear it). */
function refreshContent() {
  dropMiniChart();
  dropCompareChart();
  dropWfChart();
  contentEl.replaceChildren();
  if (lastRunFailed) contentEl.appendChild(page.mk('div', 'tst-fail-banner', `The last run failed: ${lastRunFailed}`));
  if (innerTab === 'heatmap') { renderHeatmap(contentEl); return; }
  if (innerTab === 'walkforward') { renderWalkforward(contentEl); return; }
  if (innerTab === 'compare') { renderCompare(contentEl); return; }
  heatGridEl = null;
  if (!bundle) { contentEl.appendChild(page.mk('div', 'bp-empty', EMPTY_MSG[innerTab])); return; }
  if (innerTab === 'overview') renderOverview(contentEl);
  else if (innerTab === 'summary') renderSummary(contentEl);
  else if (innerTab === 'trades') renderTrades(contentEl);
  else renderProperties(contentEl);
}

/* ================================================================== the heat-map ================================================================== */

let heatRowsStrategy = null;
/* The axis editor rows for the current strategy: the saved rows (unknown keys dropped), else the first two
   numeric inputs at their defaults. */
function currentHeatRows() {
  if (heatRows && heatRowsStrategy === strategyId) return heatRows;
  const schema = schemaFor(strategyId), keys = new Set(schema.inputs.map((i) => i.key));
  const saved = Array.isArray(store.heat[strategyId]) ? store.heat[strategyId] : null;
  if (saved && saved.length === 3) {
    heatRows = saved.map((r) => (r && keys.has(r.key) ? { key: r.key, text: typeof r.text === 'string' ? r.text : '' } : { key: '', text: '' }));
  } else {
    const nums = schema.inputs.filter((i) => i.type === 'int' || i.type === 'float');
    heatRows = [0, 1, 2].map((k) => (k < 2 && nums[k] ? { key: nums[k].key, text: String(nums[k].default) } : { key: '', text: '' }));
  }
  heatRowsStrategy = strategyId;
  return heatRows;
}
function saveHeatRows() { gridErr = ''; store.heat[strategyId] = heatRows; saveStore(); }
const gridInFlight = () => gridStarting || !!(grid && !X.gridProgress(grid).final);
const heatLive = () => !!(heatGridEl && heatGridEl.isConnected);

function axisRow(k, busy, sync = syncHeat) {
  const rows = currentHeatRows(), schema = schemaFor(strategyId), row = page.mk('div', 'tst-heat-axis');
  const lab = page.mk('label', 'tst-cost-l tst-heat-role', AXIS_ROLES[k]);
  const sel = page.mk('select', 'set-select');
  sel.id = `tst-heat-key-${k}`;
  lab.htmlFor = sel.id;
  sel.disabled = busy;
  sel.appendChild(optionEl('', k < 2 ? 'Pick a parameter' : '— none —'));
  for (const i of schema.inputs) sel.appendChild(optionEl(i.key, i.label));
  sel.value = rows[k].key;
  const txt = page.mk('input', 'tst-heat-vals');
  txt.type = 'text';
  txt.disabled = busy || !rows[k].key;
  txt.value = rows[k].text;
  txt.setAttribute('aria-label', `${AXIS_ROLES[k]} values`);
  const placeholder = (inp) => (!inp ? '' : inp.type === 'bool' ? 'on, off' : inp.type === 'choice' ? inp.choices.join(', ')
    : 'e.g. 5, 10, 15  or  5:20:5');
  txt.placeholder = placeholder(schema.inputs.find((i) => i.key === rows[k].key));
  sel.onchange = () => {
    const inp = schema.inputs.find((i) => i.key === sel.value);
    rows[k] = { key: sel.value, text: inp ? (inp.type === 'bool' ? 'on, off' : String(inp.default)) : '' };
    txt.value = rows[k].text;
    txt.disabled = !inp;
    txt.placeholder = placeholder(inp);
    saveHeatRows();
    sync();
  };
  txt.oninput = () => { rows[k] = { ...rows[k], text: txt.value }; saveHeatRows(); sync(); };
  row.append(lab, sel, txt);
  return row;
}
/* Focus-preserving: the cell count, the error line, the looks line and the Run grid button's enabled state. */
function syncHeat() {
  if (!heatLive() || !heatErrEl) return;
  const schema = schemaFor(strategyId), rows = currentHeatRows();
  const prob = X.gridProblems(form, schema, rows), g = X.gridAxes(rows, schema);
  heatCountEl.textContent = g.axes ? `${X.gridCount(g.axes)} cells` : '';
  const text = gridErr || prob || '';
  heatErrEl.textContent = text;
  heatErrEl.hidden = !text;
  heatLooksEl.textContent = X.looksLine(looksMap[strategyId] || 0, (grid && grid.looks_error) || looksErr);
  const runBtnEl = heatRunEl && heatRunEl.querySelector('.tst-run');
  if (runBtnEl) runBtnEl.disabled = !!prob;
}
function heatRunArea() {
  heatRunEl.replaceChildren();
  heatProgBar = null; heatProgText = null;
  if (gridInFlight()) {
    heatProgBar = document.createElement('progress');
    heatProgBar.className = 'tst-progress';
    heatProgBar.max = 1;
    heatProgText = page.mk('span', 'tst-progress-text', '');
    heatRunEl.append(heatProgBar, heatProgText, iconBtn('square', 'Cancel the grid', cancelGrid, gridStarting));
    patchProgress();
  } else {
    const b = page.mk('button', 'btn btn-primary tst-run');
    b.type = 'button';
    b.append(page.icon('play'), document.createTextNode(' Run grid'));
    b.onclick = startGrid;
    heatRunEl.appendChild(b);
    if (grid) heatRunEl.appendChild(page.mk('span', 'tst-progress-text', X.gridProgress(grid).text));
  }
}
function patchProgress() {
  if (!heatProgText) return;
  const p = grid ? X.gridProgress(grid) : { text: 'Starting…', frac: null };
  heatProgText.textContent = p.text;
  if (p.frac == null) heatProgBar.removeAttribute('value'); else heatProgBar.value = p.frac;
}
/* The editor + run row. Rebuilt only on a real state change (a strategy switch, a grid starting or ending). */
function refreshHeatConfig() {
  if (!heatLive()) return;
  const busy = gridInFlight();
  heatCfgEl.replaceChildren();
  const axes = page.mk('div', 'tst-heat-axes');
  for (let k = 0; k < 3; k++) axes.appendChild(axisRow(k, busy));
  heatCountEl = page.mk('span', 'tst-heat-count', '');
  heatRunEl = page.mk('span', 'tst-run-area');
  const line = page.mk('div', 'tst-heat-line');
  heatLooksEl = page.mk('span', 'tst-heat-looks', '');
  heatLooksEl.title = 'Every finished heat-map cell is a look. At a 5% level about 1 in 20 looks reads "significant" by luck alone.';
  line.append(heatRunEl, heatCountEl, page.mk('span', 'tst-heat-note', 'Research window 2021–2024 only'), heatLooksEl);
  heatErrEl = page.mk('div', 'tst-err tst-heat-err', '');
  heatCfgEl.append(axes, line, heatErrEl);
  heatRunArea();
  syncHeat();
}

function cellLabel(g, c) { return g.axes.map((a) => `${a.label} ${X.valueLabel(c.params[a.key])}`).join(' · '); }
function updateHeatNote() {
  if (!heatNoteEl) return;
  const c = heatCell && grid && heatCell.gid === grid.id ? grid.cells[heatCell.i] : null;
  heatNoteEl.replaceChildren();
  heatNoteEl.hidden = !c;
  if (!c) return;
  const open = page.mk('button', 'bp-act', 'Open Overview');
  open.type = 'button';
  open.onclick = () => { innerTab = 'overview'; form = { ...form, holdout: { ...form.holdout, on: false } }; refreshHeader(); refreshTabsBar(); refreshContent(); };
  heatNoteEl.append(document.createTextNode(`Loaded in Overview, Performance summary and List of trades: ${cellLabel(grid, c)}  `), open);
}
/* The grid itself: built once per grid (or tab show); patchGrid() fills it in place on every poll. */
function buildGrid() {
  if (!heatLive()) return;
  heatGridEl.replaceChildren();
  heatCellEls = new Map();
  if (!grid || !grid.axes) {
    heatGridEl.appendChild(page.mk('div', 'bp-empty', gridStarting ? 'Starting the grid…'
      : 'Pick 2 or 3 parameters and run the grid: each cell is a full tick-replay run on 2021–2024'));
    return;
  }
  const cost = `qty ${grid.qty} · ${Tr.money(grid.commission)}/RT · ${grid.slippage_ticks} tick slippage`;
  heatGridEl.appendChild(page.mk('div', 'tst-kv-line', `${grid.strategy_name || grid.strategy} · ${grid.range.label} · ${cost} · colour = net $, Sharpe = weekday grid`));
  for (const p of X.heatPanels(grid)) {
    if (p.title) heatGridEl.appendChild(page.mk('div', 'set-cap', p.title));
    const t = page.mk('table', 'tst-heat-table'), thead = page.mk('thead'), htr = page.mk('tr');
    htr.appendChild(page.mk('th', 'tst-heat-corner', `${p.rowLabel} ↓ · ${p.colLabel} →`));
    for (const c of p.cols) htr.appendChild(page.mk('th', 'num', c));
    thead.appendChild(htr);
    const tbody = page.mk('tbody');
    p.rows.forEach((r, ri) => {
      const tr = page.mk('tr');
      tr.appendChild(page.mk('th', 'num', r));
      for (const i of p.cells[ri]) {
        const td = page.mk('td'), b = page.mk('button', 'tst-hcell');
        b.type = 'button';
        b.append(page.mk('span', 'tst-hcell-net', ''), page.mk('span', 'tst-hcell-sh', ''));
        b.onclick = () => loadCell(i);
        td.appendChild(b);
        heatCellEls.set(i, b);
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    });
    t.append(thead, tbody);
    heatGridEl.appendChild(t);
  }
  patchGrid();
}
function patchGrid() {
  if (!heatLive() || !grid || !grid.cells) return;
  const maxAbs = X.heatMaxAbs(grid), sel = heatCell && heatCell.gid === grid.id ? heatCell.i : null;
  for (const c of grid.cells) {
    const b = heatCellEls.get(c.i);
    if (!b) continue;
    const v = X.cellView(c), lvl = X.heatLevel(c.summary && c.summary.net_profit, maxAbs);
    b.firstChild.textContent = v.net;
    b.lastChild.textContent = v.sharpe;
    b.style.background = lvl.alpha ? `color-mix(in srgb, var(--${lvl.tone}) ${Math.round(lvl.alpha * 100)}%, transparent)` : '';
    b.className = `tst-hcell ${v.state}${v.warn ? ' warn' : ''}${sel === c.i ? ' sel' : ''}`;
    b.title = `${cellLabel(grid, c)}\n${v.title}${v.warn ? '\n' + v.warn : ''}`;
    b.disabled = v.state !== 'done';
  }
  patchProgress();
  syncHeat();
  updateHeatNote();
}
function renderHeatmap(container) {
  const wrap = page.mk('div', 'tst-heat');
  heatCfgEl = page.mk('div', 'tst-heat-cfg');
  heatNoteEl = page.mk('div', 'tst-kv-line tst-heat-loaded');
  heatGridEl = page.mk('div', 'tst-heat-grid');
  wrap.append(heatCfgEl, heatNoteEl, heatGridEl);
  container.appendChild(wrap);
  refreshHeatConfig();
  buildGrid();
  updateHeatNote();
  if (!heatResumed) { heatResumed = true; resumeGrid(); }
}

/* A page reload mid-grid: pick the newest grid of this strategy back up (and the looks counter). */
function refreshLooks() {
  fetch('/api/tester/looks').then(async (r) => {
    if (r.status === 409) { let d = ''; try { d = (await r.json()).detail || ''; } catch (_) { /* no body */ } looksErr = d || 'unreadable'; return {}; }
    looksErr = '';
    return r.ok ? r.json() : {};
  }).catch(() => ({}))
    .then((m) => { looksMap = { ...looksMap, ...m }; syncHeat(); syncWf(); });
}
function resumeGrid() {
  refreshLooks();
  const idle = () => !gridStarting && (!grid || grid.lost);
  if (!idle()) return;
  const token = gridToken, want = grid && grid.lost ? grid.id : null;
  fetch('/api/tester/grids').then((r) => (r.ok ? r.json() : [])).catch(() => [])
    .then((list) => {
      const g = (list || []).find((x) => (want ? x.id === want : x.strategy === strategyId));
      if (g && token === gridToken && idle()) { if (grid) grid = null; pollGrid(g.id, ++gridToken); }
    });
}
function startGrid() {
  const schema = schemaFor(strategyId), rows = currentHeatRows();
  if (X.gridProblems(form, schema, rows)) { syncHeat(); return; }
  const bodyObj = X.gridBody(form, X.gridAxes(rows, schema).axes);
  const token = ++gridToken;
  gridErr = '';
  gridStarting = true;
  grid = null;
  heatCell = null;
  refreshHeatConfig();
  buildGrid();
  updateHeatNote();
  fetch('/api/tester/grid', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(bodyObj) })
    .then(async (r) => {
      if (r.status === 400) {
        let detail = '';
        try { detail = (await r.json()).detail || ''; } catch (_) { /* no JSON body */ }
        throw new Error(detail || 'bad request');
      }
      if (!r.ok) throw new Error(`request failed (${r.status})`);
      return r.json();
    })
    .then(({ id }) => { if (token === gridToken) pollGrid(id, token); })
    .catch((e) => {
      if (token !== gridToken) return;
      gridStarting = false;
      gridErr = e.message || 'request failed';
      refreshHeatConfig();
      buildGrid();
    });
}
function pollGrid(gid, token, attempt = 0) {
  fetch(`/api/tester/grid/${gid}`).then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((st) => {
      if (token !== gridToken) return;
      gridErr = gridErr.startsWith('lost contact') ? '' : gridErr;
      const fresh = !grid || grid.id !== st.id, wasBusy = gridInFlight();
      grid = st;
      gridStarting = false;
      if (st.looks != null) looksMap[st.strategy] = st.looks;
      const final = X.gridProgress(st).final;
      if (fresh) { refreshHeatConfig(); buildGrid(); } else { patchGrid(); if (wasBusy && final) refreshHeatConfig(); }
      if (!final) setTimeout(() => pollGrid(gid, token, 0), 1000);
    })
    .catch(() => {
      if (token !== gridToken) return;
      if (attempt < 3) { setTimeout(() => pollGrid(gid, token, attempt + 1), 500 * (2 ** attempt)); return; }
      gridStarting = false;
      gridErr = 'lost contact with the grid (it keeps running on the server; reopen the tab to pick it up)';
      if (grid) grid = { ...grid, status: 'cancelled', error: 'lost contact', lost: true };
      heatResumed = false;
      refreshHeatConfig();
    });
}
function cancelGrid() {
  if (!grid) return;
  fetch(`/api/tester/grid/${grid.id}/cancel`, { method: 'POST' }).catch(() => { /* the next poll reflects reality */ });
}
/* A cell's full report into Overview / Performance summary / List of trades (and the chart), exactly as a
   recent run loads -- the form takes the cell's inputs. Refused while a single run is in flight (I1: the
   header is frozen then). */
function loadCell(i) {
  if (!grid) return;
  if (runStatus) { gridErr = 'A run is in flight: load a cell once it finishes'; syncHeat(); return; }
  const gid = grid.id;
  fetch(`/api/tester/grid/${gid}/cell/${i}/bundle`).then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((b) => {
      if (runStatus || !grid || grid.id !== gid) return;
      const moved = b.run.strategy.id !== strategyId;
      strategyId = b.run.strategy.id;
      form = X.fromRun(b.run, schemaFor(strategyId));
      bundle = b;
      startMonteCarlo(b.run.id, { grid_id: gid, cell: i });
      loadedKey = X.key(form);
      lastRunFailed = '';
      visibleTradeRows = TRADE_CHUNK;
      selectedTrade = null;
      heatCell = { gid, i };
      persist();
      refreshHeader();
      if (moved) refreshHeatConfig();
      patchGrid();
      notify();
    })
    .catch(() => { gridErr = 'could not load that cell'; syncHeat(); });
}

/* ================================================================== the walk-forward ================================================================== */

const wfInFlight = () => wfStarting || !!(wf && !X.wfProgress(wf).final);
const wfLive = () => !!(wfBodyEl && wfBodyEl.isConnected);
function wfPrefs() {
  const p = store.wf[strategyId] || {};
  const metric = X.WF_METRICS.some(([k]) => k === p.metric) ? p.metric : 'net_profit';
  const minText = typeof p.minText === 'string' ? p.minText : '5';
  return { metric, minText, minTrades: minText.trim() === '' ? NaN : Number(minText) };   // what the box shows is what is validated
}
function saveWfPrefs(patch) {
  wfErr = '';
  const { metric, minText } = { ...wfPrefs(), ...patch };
  store.wf[strategyId] = { metric, minText };
  saveStore();
}
function dropWfChart() {
  if (!wfChartHandle) return;
  try { wfChartHandle.remove(); } catch (_) { /* already gone */ }
  wfChartHandle = null;
}
/* Focus-preserving: the cell count, the looks preview, the error line and the Run button's enabled state. */
function syncWf() {
  if (!wfLive() || !wfErrEl) return;
  const schema = schemaFor(strategyId), rows = currentHeatRows(), pr = wfPrefs();
  const prob = X.wfProblems(form, schema, rows, pr.minTrades), g = X.gridAxes(rows, schema);
  const n = g.axes ? X.gridCount(g.axes) : 0;
  wfCountEl.textContent = g.axes ? `${n} cells` : '';
  const total = X.looksLine(looksMap[strategyId] || 0, (wf && wf.looks_error) || looksErr);
  const preview = g.axes && n <= X.MAX_CELLS ? X.wfLooksText(n, wfScheme && wfScheme.n_steps) : '';
  wfLooksEl.textContent = preview ? `${preview} · ${total}` : total;
  const text = wfErr || prob || '';
  wfErrEl.textContent = text;
  wfErrEl.hidden = !text;
  const b = wfRunEl && wfRunEl.querySelector('.tst-run');
  if (b) b.disabled = !!prob;
}
function patchWfProgress() {
  if (!wfProgText) return;
  const p = wf ? X.wfProgress(wf) : { text: 'Starting…', frac: null };
  wfProgText.textContent = p.text;
  if (p.frac == null) wfProgBar.removeAttribute('value'); else wfProgBar.value = p.frac;
}
function wfRunArea() {
  wfRunEl.replaceChildren();
  wfProgBar = null; wfProgText = null;
  if (wfInFlight()) {
    wfProgBar = document.createElement('progress');
    wfProgBar.className = 'tst-progress';
    wfProgBar.max = 1;
    wfProgText = page.mk('span', 'tst-progress-text', '');
    wfRunEl.append(wfProgBar, wfProgText, iconBtn('square', 'Cancel the walk-forward', cancelWf, wfStarting));
    patchWfProgress();
  } else {
    const b = page.mk('button', 'btn btn-primary tst-run');
    b.type = 'button';
    b.append(page.icon('play'), document.createTextNode(' Run walk-forward'));
    b.onclick = startWf;
    wfRunEl.appendChild(b);
    if (wf) wfRunEl.appendChild(page.mk('span', 'tst-progress-text', X.wfProgress(wf).text));
  }
}
/* The editor + run row. Rebuilt only on a real state change (a strategy switch, a job starting or ending). */
function refreshWfConfig() {
  if (!wfLive()) return;
  const busy = wfInFlight(), pr = wfPrefs();
  wfCfgEl.replaceChildren();
  const axes = page.mk('div', 'tst-heat-axes');
  for (let k = 0; k < 3; k++) axes.appendChild(axisRow(k, busy, () => { wfErr = ''; syncWf(); }));
  const sel = page.mk('div', 'tst-heat-axes');
  const mWrap = page.mk('span', 'tst-heat-axis'), mLab = page.mk('label', 'tst-cost-l', 'Select by');
  const metric = page.mk('select', 'set-select');
  metric.id = 'tst-wf-metric';
  mLab.htmlFor = metric.id;
  metric.disabled = busy;
  for (const [k, label] of X.WF_METRICS) metric.appendChild(optionEl(k, label));
  metric.value = pr.metric;
  metric.onchange = () => { saveWfPrefs({ metric: metric.value }); syncWf(); };
  mWrap.append(mLab, metric);
  const nWrap = page.mk('span', 'tst-heat-axis'), nLab = page.mk('label', 'tst-cost-l', 'Min trades in the month');
  const minT = page.mk('input', 'tst-heat-vals tst-wf-min');
  minT.id = 'tst-wf-min';
  nLab.htmlFor = minT.id;
  minT.type = 'number';
  minT.min = '1'; minT.max = '1000'; minT.step = '1';
  minT.disabled = busy;
  minT.value = pr.minText;
  minT.oninput = () => { saveWfPrefs({ minText: minT.value }); syncWf(); };
  nWrap.append(nLab, minT);
  sel.append(mWrap, nWrap);
  wfCountEl = page.mk('span', 'tst-heat-count', '');
  wfRunEl = page.mk('span', 'tst-run-area');
  wfLooksEl = page.mk('span', 'tst-heat-looks', '');
  wfLooksEl.title = 'Every selection month compares every cell: each is a look. At a 5% level about 1 in 20 looks reads "significant" by luck alone.';
  const line = page.mk('div', 'tst-heat-line');
  line.append(wfRunEl, wfCountEl, page.mk('span', 'tst-heat-note', 'Research window 2021–2024 only · select 1 month, test the next 3, monthly'), wfLooksEl);
  wfErrEl = page.mk('div', 'tst-err tst-heat-err', '');
  wfCfgEl.append(axes, sel, line, wfErrEl);
  wfRunArea();
  syncWf();
}
function wfStepTable(r) {
  const t = page.mk('table', 'bp-table tst-wf-steps'), thead = page.mk('thead'), htr = page.mk('tr');
  X.WF_STEP_HEADERS.forEach((h, i) => htr.appendChild(page.mk('th', i >= 3 ? 'num' : '', h)));
  thead.appendChild(htr);
  const tbody = page.mk('tbody');
  for (const row of X.wfStepRows(r, wf.axes)) {
    const tr = page.mk('tr', row.stitched ? 'tst-wf-chain' : '');
    row.cells.forEach((c, i) => {
      const td = page.mk('td', i >= 3 ? 'num' : '', c);
      if (i === 3 && row.isTone) td.classList.add(row.isTone);
      if (i === 6 && row.oosTone) td.classList.add(row.oosTone);
      if (i === 2 && row.changed) td.classList.add('tst-wf-changed');
      tr.appendChild(td);
    });
    if (row.stitched) tr.title = 'In the stitched chain: this pick is held for its full 3-month test window';
    tbody.appendChild(tr);
  }
  t.append(thead, tbody);
  return t;
}
function renderWfResult(r) {
  wfBodyEl.appendChild(page.mk('div', 'tst-kv-line', X.wfScheme(r)));
  const tiles = page.mk('div', 'tst-tiles');
  for (const tl of X.wfTiles(r)) tiles.appendChild(tileEl(tl));
  wfBodyEl.appendChild(tiles);
  const chartWrap = page.mk('div', 'tst-chart');
  wfBodyEl.appendChild(chartWrap);
  if ((r.stitched.equity.t_ms || []).length) wfChartHandle = miniChart(chartWrap, r.stitched.equity, palette());
  else chartWrap.appendChild(page.mk('div', 'bp-empty', 'No out-of-sample trades in the stitched chain'));
  wfBodyEl.appendChild(page.mk('div', 'tst-kv-line', X.wfStability(r)));
  wfBodyEl.appendChild(page.mk('div', 'tst-kv-line', X.wfPhases(r)));
  if (r.skipped_by_error) wfBodyEl.appendChild(page.mk('div', 'tst-err', `${r.skipped_by_error} strategy-error sessions inside the test legs`));
  wfBodyEl.appendChild(page.mk('div', 'set-cap', `STEPS · highlighted rows = the stitched chain · tie-break: ${r.scheme.tie_break}`));
  wfBodyEl.appendChild(wfStepTable(r));
}
/* The body: built once per job state (fresh job, a job ending, the result arriving) -- never on a poll tick. */
function buildWfBody() {
  if (!wfLive()) return;
  dropWfChart();
  wfBodyEl.replaceChildren();
  if (!wf) {
    wfBodyEl.appendChild(page.mk('div', 'bp-empty', wfStarting ? 'Starting the walk-forward…'
      : 'Pick 2 or 3 parameters: each month, every cell is scored and the best is traded for the next 3 months (2021–2024)'));
    return;
  }
  const cost = `qty ${wf.qty} · ${Tr.money(wf.commission)}/RT · ${wf.slippage_ticks} tick slippage`;
  const ran = (wf.axes || []).map((a) => `${a.label}: ${a.values.map(X.valueLabel).join(', ')}`).join(' · ');
  wfBodyEl.appendChild(page.mk('div', 'tst-kv-line', `${wf.strategy_name || wf.strategy} · ${wf.range.label} · ${cost}`));
  if (ran) wfBodyEl.appendChild(page.mk('div', 'tst-kv-line', `Grid: ${ran}`));
  if (wf.status === 'done') {
    if (wfResult && wfResult.id === wf.id) { renderWfResult(wfResult.result); return; }
    wfBodyEl.appendChild(page.mk('div', wfResultErr ? 'tst-err' : 'bp-empty', wfResultErr || 'Loading the result…'));
    if (!wfResultErr) loadWfResult(wf.id, wfToken);
    return;
  }
  if (wf.status === 'error' || wf.status === 'cancelled') {
    wfBodyEl.appendChild(page.mk('div', 'tst-err', X.wfProgress(wf).text));
    return;
  }
  wfBodyEl.appendChild(page.mk('div', 'bp-empty', 'Each cell runs once over 2021–2024; the selection and the stitched out-of-sample equity appear when every cell is done'));
}
function loadWfResult(wid, token) {
  fetch(`/api/tester/walkforward/${wid}/result`).then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((result) => { if (token !== wfToken) return; wfResult = { id: wid, result }; wfResultErr = ''; buildWfBody(); })
    .catch(() => { if (token !== wfToken) return; wfResultErr = 'could not load the walk-forward result'; buildWfBody(); });
}
function loadWfScheme() {
  if (wfScheme || wfSchemePromise) return;
  wfSchemePromise = fetch('/api/tester/walkforward-scheme').then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((sc) => { wfScheme = sc; syncWf(); })
    .catch(() => { /* the preview stays blank; the next render retries */ })
    .finally(() => { wfSchemePromise = null; });
}
function renderWalkforward(container) {
  loadWfScheme();
  const wrap = page.mk('div', 'tst-heat tst-wf');
  wfCfgEl = page.mk('div', 'tst-heat-cfg');
  wfBodyEl = page.mk('div', 'tst-wf-body');
  wrap.append(wfCfgEl, wfBodyEl);
  container.appendChild(wrap);
  refreshWfConfig();
  buildWfBody();
  if (!wfResumed) { wfResumed = true; resumeWf(); }
}
/* A page reload mid-job (or a return to this strategy): pick the newest walk-forward of this strategy back up. */
function resumeWf() {
  refreshLooks();
  const idle = () => !wfStarting && (!wf || wf.lost);
  if (!idle()) return;
  const token = wfToken, want = wf && wf.lost ? wf.id : null;
  fetch('/api/tester/walkforwards').then((r) => (r.ok ? r.json() : [])).catch(() => [])
    .then((list) => {
      const g = (list || []).find((x) => (want ? x.id === want : x.strategy === strategyId));
      if (g && token === wfToken && idle()) { if (wf) wf = null; pollWf(g.id, ++wfToken); }
    });
}
function startWf() {
  const schema = schemaFor(strategyId), rows = currentHeatRows(), pr = wfPrefs();
  if (X.wfProblems(form, schema, rows, pr.minTrades)) { syncWf(); return; }
  const bodyObj = X.wfBody(form, X.gridAxes(rows, schema).axes, pr.metric, pr.minTrades);
  const token = ++wfToken;
  wfErr = '';
  wfStarting = true;
  wf = null;
  wfResult = null;
  wfResultErr = '';
  refreshWfConfig();
  buildWfBody();
  fetch('/api/tester/walkforward', { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(bodyObj) })
    .then(async (r) => {
      if (r.status === 400) {
        let detail = '';
        try { detail = (await r.json()).detail || ''; } catch (_) { /* no JSON body */ }
        throw new Error(detail || 'bad request');
      }
      if (!r.ok) throw new Error(`request failed (${r.status})`);
      return r.json();
    })
    .then(({ id }) => { if (token === wfToken) pollWf(id, token); })
    .catch((e) => {
      if (token !== wfToken) return;
      wfStarting = false;
      wfErr = e.message || 'request failed';
      refreshWfConfig();
      buildWfBody();
    });
}
function pollWf(wid, token, attempt = 0) {
  fetch(`/api/tester/walkforward/${wid}`).then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
    .then((st) => {
      if (token !== wfToken) return;
      wfErr = wfErr.startsWith('lost contact') ? '' : wfErr;
      const fresh = !wf || wf.id !== st.id, wasBusy = wfInFlight(), wasStatus = wf && wf.status;
      wf = st;
      wfStarting = false;
      if (st.looks != null) looksMap[st.strategy] = st.looks;
      const final = X.wfProgress(st).final;
      if (fresh) { refreshWfConfig(); buildWfBody(); } else {
        patchWfProgress();
        if (wasBusy && final) refreshWfConfig();
        if (wasStatus !== st.status) buildWfBody();
        syncWf();
      }
      if (!final) setTimeout(() => pollWf(wid, token, 0), 1000);
    })
    .catch(() => {
      if (token !== wfToken) return;
      if (attempt < 3) { setTimeout(() => pollWf(wid, token, attempt + 1), 500 * (2 ** attempt)); return; }
      wfStarting = false;
      wfErr = 'lost contact with the walk-forward (it keeps running on the server; reopen the tab to pick it up)';
      if (wf) wf = { ...wf, status: 'cancelled', error: 'lost contact', lost: true };
      wfResumed = false;
      refreshWfConfig();
    });
}
function cancelWf() {
  if (!wf) return;
  fetch(`/api/tester/walkforward/${wf.id}/cancel`, { method: 'POST' }).catch(() => { /* the next poll reflects reality */ });
}
function resetWf() {
  wfToken++;
  wf = null;
  wfStarting = false;
  wfErr = '';
  wfResult = null;
  wfResultErr = '';
  wfResumed = false;
}

/* ================================================================== strategy switching / mount ================================================================== */

/* Review #8: the heat-map belongs to ONE strategy. A switch drops the old grid from the page (its poll
   stops via the token); on the server it keeps running, and the next heat-map render re-attaches the
   newest grid of whichever strategy is current -- so switching back picks the old one up again. */
function resetGrid() {
  gridToken++;
  grid = null;
  gridStarting = false;
  gridErr = '';
  heatCell = null;
  heatResumed = false;
}

function switchStrategy(id) {
  if (id !== strategyId) { resetGrid(); resetWf(); }
  strategyId = id;
  form = X.restore(store.forms[id], schemaFor(id));
  bundle = null;
  loadedKey = null;
  lastRunFailed = '';
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
  rules = store.rules !== false;
  strategyId = (strategiesList.some((s) => s.id === store.strategy) ? store.strategy : strategiesList[0].id);
  form = X.restore(store.forms[strategyId], schemaFor(strategyId));
  headerEl = page.mk('div', 'tst-head');
  holdoutBannerEl = page.mk('div', 'tst-holdout-banner', '');
  holdoutBannerEl.hidden = true;
  tabsEl = page.mk('div', 'tst-tabs');
  contentEl = page.mk('div', 'tst-content');
  const sticky = page.mk('div', 'tst-sticky');
  sticky.append(headerEl, holdoutBannerEl, tabsEl);
  root.append(sticky, contentEl);
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
function onHide() { dropMiniChart(); dropWfChart(); }

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
  get rules() { return rules; },
  on(fn) { listeners.add(fn); return () => listeners.delete(fn); },
  select(i) { selectedTrade = i; if (innerTab === 'trades') refreshContent(); notify(); },
};
})();
