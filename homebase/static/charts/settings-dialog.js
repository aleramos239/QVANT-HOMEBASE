/* Homebase Charts — the chart Settings dialog (TradingView's Settings, for what applies to our charts): a
   column of tabs, rows of controls, the swatch popover and a footer. Every change previews live on the
   selected chart; Cancel, ×, Esc or a backdrop click put every chart back as it was when the dialog opened;
   Ok keeps the changes. Browser only: the model is HBSettings (settings.js); the page (app.js) owns the
   dialog frame and the menus and hands them over as `host`:
     {cell, cells(), toggleMenu(anchor, cls, fill(menuEl)), closeMenu(), placeMenu(), commit(changed), cancel(),
      templates: {list(), save(name, settings), remove(name)}, countries(),
      algoChoices(cell), setAlgo(cell, key|null)}   (countries(): every currency code seen in the loaded calendar,
      for the Events tab's chips; algoChoices / setAlgo: the Trading tab's Algo select -- HBTrade.algoChoices, and a
      live preview that Cancel puts back through host.restoreTrade)
   The Trading tab (2026-09-27 accounts-per-chart plan, Task 1) also uses:
     {accountRows(cell), toggleAccount(cell, id), armPending(), tradeWhy(cell), prefs(), setPrefs(patch),
      onTradeChange(fn) -> unsubscribe}
   -- the rules behind all of them (the two-step LIVE arm, unlisted accounts failing closed, the algo <->
   accounts binding) live in HBTradeUI / HBTrade, never here: this file only paints and reports clicks. */
(() => {
'use strict';
const S = window.HBSettings, I = window.HBIcons, DX = window.HBDataExport;
const LINE = [['solid', 'Solid'], ['dotted', 'Dotted'], ['dashed', 'Dashed']];
const PRECISION = [['', 'Default'], ...[0, 1, 2, 3, 4, 5, 6].map((n) => [String(n), n ? (10 ** -n).toFixed(n) : '1'])];
const FONT_SIZES = [10, 11, 12, 13, 14, 15, 16].map((n) => [String(n), String(n)]);
const asNumber = (v) => Number(v);
const asPrecision = (v) => (v === '' ? null : Number(v));

/* The tabs, in TradingView's order. A row: {label, check?: key (a checkbox before the label), colors?: [[key,
   what]] (a swatch each), select?: {key, choices: [[value, text]], parse?}, number?: {key, min, max, unit?},
   dot?: colour (a colour dot before the label, no swatch), chips?: key (a multi-select of host.countries()),
   algo?: true (the chart's desk algo: host.algoChoices / host.setAlgo, not a setting),
   accounts?: true (the Trading tab's ACCOUNTS list: the chart's own accounts, not a setting),
   pref?: {key, kind?: 'switch', min, max, note} (a viewer-wide trade preference: host.prefs / host.setPrefs),
   caption?: text (a plain note line, no control)}. */
const TABS = [
  { id: 'symbol', label: 'Symbol', icon: 'candles', sections: [
    ['CANDLES', [
      { label: 'Colour bars based on previous close', check: 'prevClose' },
      { label: 'Body', check: 'body', colors: [['bodyUp', 'up'], ['bodyDown', 'down']] },
      { label: 'Borders', check: 'borders', colors: [['borderUp', 'up'], ['borderDown', 'down']] },
      { label: 'Wick', check: 'wick', colors: [['wickUp', 'up'], ['wickDown', 'down']] },
    ]],
    ['DATA', [
      { label: 'Precision', select: { key: 'precision', choices: PRECISION, parse: asPrecision } },
      { label: 'Timezone', select: { key: 'timezone', choices: S.TIMEZONES.map(([k, text]) => [k, text]) } },
      { label: 'Time format', select: { key: 'timeFormat', choices: [['24h', '24-hour (19:30)'], ['12h', '12-hour (7:30 PM)']] } },
      { label: 'Electronic trading hours background', check: 'ethBg', colors: [['ethBgColor', '']] },
    ]],
  ] },
  { id: 'status', label: 'Status line', icon: 'list', sections: [
    ['SYMBOL', [
      { label: 'Symbol title', check: 'title', select: { key: 'titleMode',
        choices: [['ticker', 'Ticker'], ['description', 'Description'], ['both', 'Ticker and description']] } },
      { label: 'OHLC values', check: 'ohlc' },
      { label: 'Bar change values', check: 'barChange' },
      { label: 'Volume', check: 'volume' },
    ]],
    ['INDICATORS', [
      { label: 'Indicator titles', check: 'indTitles' },
      { label: 'Indicator arguments', check: 'indArgs' },
      { label: 'Indicator values', check: 'indValues' },
    ]],
  ] },
  { id: 'scales', label: 'Scales and lines', icon: 'measure', sections: [
    ['PRICE SCALE', [
      { label: 'Scale price chart only', check: 'scalePriceOnly' },
      { label: 'Symbol last price label', check: 'lastLabel' },
      { label: 'Symbol last price line', check: 'lastLine', select: { key: 'lastLineStyle', choices: LINE } },
      { label: 'Countdown to bar close', check: 'countdown' },
      { label: 'Top margin', number: { key: 'marginTop', min: 0, max: 40, unit: '%' } },
      { label: 'Bottom margin', number: { key: 'marginBottom', min: 0, max: 40, unit: '%' } },
    ]],
    ['TIME SCALE', [
      { label: 'Right margin', number: { key: 'rightOffset', min: 0, max: 100, unit: 'bars' } },
    ]],
  ] },
  { id: 'canvas', label: 'Canvas', icon: 'paintbrush', sections: [
    ['CHART BASIC STYLES', [
      { label: 'Background', colors: [['bg', '']] },
      { label: 'Vert grid lines', check: 'vertGrid', colors: [['vertGridColor', '']] },
      { label: 'Horz grid lines', check: 'horzGrid', colors: [['horzGridColor', '']] },
      { label: 'Crosshair', colors: [['crossColor', '']], select: { key: 'crossStyle', choices: LINE },
        number: { key: 'crossWidth', min: 1, max: 4 } },
      { label: 'Watermark', check: 'watermark', colors: [['watermarkColor', '']] },
    ]],
    ['SCALES', [
      { label: 'Text colour', colors: [['scaleText', '']] },
      { label: 'Text size', select: { key: 'scaleFont', choices: FONT_SIZES, parse: asNumber } },
      { label: 'Lines colour', colors: [['scaleLines', '']] },
    ]],
  ] },
  { id: 'events', label: 'Events', icon: 'calendar', sections: [
    ['ECONOMIC CALENDAR', [
      { label: 'High', check: 'evHigh', dot: '#F23645' },
      { label: 'Medium', check: 'evMedium', dot: '#FF9800' },
      { label: 'Low', check: 'evLow', dot: '#F7C600' },
      { label: 'Holiday', check: 'evHoliday', dot: '#9598A1' },
      { label: 'Currencies', chips: 'evCountries' },
      { label: 'Vertical lines for high impact', check: 'evLines' },
    ]],
    ['NEWS', [
      { label: 'News on chart', select: { key: 'newsOnChart', choices: [
        ['bursts', 'Big moves with news only'], ['all', 'All headlines and moves'], ['off', 'Off']] } },
    ]],
  ] },
  { id: 'trading', label: 'Trading', icon: 'bot', sections: [
    // the chart's ACCOUNTS are what makes it trade-ready at all, so they come first
    ['ACCOUNTS', [
      { accounts: true },
    ]],
    ['ALGO', [
      { label: 'Algo', algo: true },
    ]],
    // viewer-wide (every chart): sends from that surface skip the confirm dialog while its switch is on
    ['ONE-CLICK TRADING', [
      { label: 'Chart buttons', pref: { key: 'oneClickChart', kind: 'switch' } },
      { label: 'Order panel', pref: { key: 'oneClickPanel', kind: 'switch' } },
      { caption: 'Every chart. Off: that surface asks to confirm first.' },
    ]],
  ] },
  { id: 'data', label: 'Data', icon: 'download', sections: [
    ['REFRESH', [
      { refresh: true },
    ]],
    ['EXPORT', [
      { data: true },
    ]],
  ] },
];

function mk(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function button(cls, text) { const b = mk('button', cls, text); b.type = 'button'; return b; }

function mount(box, host) {
  const cell = host.cell;
  // Cancel puts every chart back: its settings, its indicators and its interval (a template's Apply can
  // change any of the three previews live, spec §8)
  // (and, Task 2, its trade accounts + algo: host.tradeBits, when the page provides it)
  const tradeBits = (c) => (host.tradeBits ? host.tradeBits(c) : null);
  const atOpen = new Map(host.cells().map((c) => [c, {
    settings: c.settings(), indicators: JSON.parse(JSON.stringify(c.cfg.indicators)), spec: c.cfg.spec, trade: tradeBits(c),
  }]));
  // 2026-09-28 three-tabs plan: the host offers no trade capabilities at all on a page with no trading
  // module (the Backtest tab) -- the Trading tab itself has nothing to show there, so it is left out.
  const tabList = host.accountRows ? TABS : TABS.filter((t) => t.id !== 'trading');
  // host.tab: which tab to open on (the order panel's "Change" opens Trading); anything else starts on Symbol
  let work = S.normalize(cell.settings()), tab = Math.max(0, tabList.findIndex((t) => t.id === host.tab)), done = false, raf = 0;
  const swatches = new Map();   // colour key -> the <i> inside its swatch button
  let acctBox = null, acctWhy = null, algoSel = null;   // the Trading tab's live parts (null while it is not open)
  let algoKey = '';                       // what the Algo select was last built from, so it rebuilds only on a real change
  let acctKey = '';                       // and what the ACCOUNTS rows were last built from, for the same reason
  const acctCells = new Map();            // account id -> {cb, bal, dot}: focus restore, and in-place updates

  /* ---- the Data tab's live parts (2026-09-28 data-export plan) ---- */
  // every element more than one function below touches; all null while the tab is not open (renderPane)
  let dataJobBox = null, dataCovBox = null, dataPreview = null, dataErr = null,
    dataContractSel = null, dataRangeCap = null, dataStartBtn = null;
  let dataPollId = 0;                     // setInterval id for the active job's poll, 0 while none is running
  // survive a tab switch within the same dialog session (a market/date pick, or a running job, must not
  // reset just because the viewer looked at another tab and came back)
  const dataForm = { root: (DX && DX.ROOTS[0]) || 'NQ', type: 'candles', contract: 'front', timeframe: '5m',
    start: '', end: '', hours: 'full', tz: 'et', ts_format: 'iso', format: 'csv', levels: 10 };
  const dataState = { meta: null, coverage: null, job: null, status: null, error: '' };
  function stopDataPoll() { if (dataPollId) { clearInterval(dataPollId); dataPollId = 0; } }

  /* ---- the Data tab's Refresh button: fetch what is missing from the broker, then fill the older holes ---- */
  let refreshBox = null, refreshPollId = 0;
  function stopRefreshPoll() { if (refreshPollId) { clearInterval(refreshPollId); refreshPollId = 0; } }
  function refreshPaint(st, err) {
    if (!refreshBox) return;
    const v = DX.refreshView(st);
    refreshBox.btn.disabled = v.busy;
    refreshBox.btn.textContent = v.busy ? 'Refreshing…' : 'Refresh data';
    refreshBox.cancel.hidden = !v.busy;
    refreshBox.line.className = v.tone === 'err' || err ? 'set-acct-err' : 'set-note';
    refreshBox.line.textContent = err || v.text;
    refreshBox.line.hidden = !(err || v.text);
  }
  async function refreshPoll() {
    const st = await host.refresh.status();
    refreshPaint(st);
    if (!st || DX.refreshView(st).busy === false) stopRefreshPoll();
  }
  function refreshRow() {
    const el = mk('div', 'set-data');
    if (!host.refresh) return el;
    const btn = button('btn btn-primary', 'Refresh data'), cancel = button('btn btn-ghost', 'Cancel');
    const line = mk('div', 'set-note');
    const note = mk('div', 'set-note',
      'Fetches the ticks the archive is missing from Tradovate, for all six markets. By day it takes a limited number of '
      + 'pages; the hourly and nightly runs finish the rest. What Tradovate no longer has cannot be filled.');
    cancel.hidden = true;
    line.hidden = true;
    refreshBox = { btn, cancel, line };
    btn.onclick = async () => {
      btn.disabled = true;
      const { status, data } = await host.refresh.start();
      if (status !== 200 || !data) {
        refreshPaint(null, (data && data.detail) || 'Could not start the refresh');
        btn.disabled = false;
        return;
      }
      refreshPaint(data);
      stopRefreshPoll();
      refreshPollId = setInterval(refreshPoll, 2000);
    };
    cancel.onclick = async () => {
      cancel.disabled = true;
      const { data } = await host.refresh.cancel();
      cancel.disabled = false;
      if (data) refreshPaint(data);
    };
    const bar = mk('div', 'set-row'), ctl = mk('div', 'set-ctl');
    ctl.append(btn, cancel);
    bar.append(mk('label', 'set-name', ''), ctl);
    el.append(bar, line, note);
    // reattach: closing and reopening Settings must not lose a run in progress, nor the last result
    host.refresh.status().then((st) => {
      refreshPaint(st);
      if (st && DX.refreshView(st).busy && !refreshPollId) refreshPollId = setInterval(refreshPoll, 2000);
    });
    return el;
  }

  function dataUpdatePreview() {
    if (dataPreview) dataPreview.textContent = dataForm.start && dataForm.end ? `File: ${DX.previewName({ ...dataForm })}` : '';
  }

  function dataPaintCoverage() {
    if (!dataCovBox) return;
    const cov = dataState.coverage, msg = DX.missingSummary(cov), gaps = DX.gapsSummary(cov);
    if (!msg && !gaps) { dataCovBox.hidden = true; dataCovBox.replaceChildren(); return; }
    dataCovBox.hidden = false;
    const parts = [];
    if (msg) {
      const icon = mk('span', 'icw sm');
      icon.innerHTML = I.triangleAlert;
      parts.push(icon, mk('span', '', msg));
      if (cov.missing && cov.missing.length) {
        const shown = cov.missing.slice(0, 8).join(', ');
        const more = cov.missing.length > 8 ? ` + ${cov.missing.length - 8} more` : '';
        parts.push(mk('span', 'set-unit', ` (${shown}${more})`));
      }
    }
    if (gaps) {
      if (parts.length) parts.push(mk('br'));
      parts.push(mk('span', 'set-unit', gaps));
    }
    dataCovBox.replaceChildren(...parts);
  }

  async function dataRefreshCoverage() {
    dataUpdatePreview();
    if (!dataForm.start || !dataForm.end) { dataState.coverage = null; dataPaintCoverage(); return; }
    const { root, type, contract, start, end } = dataForm;
    const cov = await host.export.coverage(root, type, contract, start, end);
    // a stale reply (the viewer changed the market/type/dates again before this one landed) is dropped
    if (dataForm.root !== root || dataForm.type !== type || dataForm.contract !== contract
      || dataForm.start !== start || dataForm.end !== end) return;
    dataState.coverage = cov;
    dataPaintCoverage();
  }

  async function dataRefreshMeta() {
    const { root, type } = dataForm;
    dataState.meta = null;
    if (dataContractSel) { dataContractSel.replaceChildren(); dataContractSel.disabled = true; }
    if (dataRangeCap) dataRangeCap.textContent = 'Checking what is on disk…';
    const meta = await host.export.meta(root, type);
    if (dataForm.root !== root || dataForm.type !== type) return;   // superseded meanwhile
    dataState.meta = meta;
    if (dataContractSel) {
      dataContractSel.disabled = false;
      const opts = [['front', 'Front month (auto)'], ...((meta && meta.contracts) || []).map((c) => [c, c])];
      dataContractSel.replaceChildren(...opts.map(([v, t]) => { const o = mk('option', '', t); o.value = v; return o; }));
      dataContractSel.value = dataForm.contract;
    }
    if (dataRangeCap) {
      dataRangeCap.textContent = meta && meta.range ? `On disk: ${meta.range[0]} to ${meta.range[1]}`
        : 'No data on disk yet for this market and data type';
    }
    dataRefreshCoverage();
  }

  function dataPaintJob() {
    if (!dataJobBox) return;
    const st = dataState.status;
    dataJobBox.hidden = !st;
    if (dataStartBtn) dataStartBtn.disabled = !!(st && !DX.progress(st).final);
    if (!st) { dataJobBox.replaceChildren(); return; }
    const p = DX.progress(st);
    const parts = [];
    if (!p.final) {
      const bar = document.createElement('progress');
      bar.className = 'tst-progress';
      bar.max = 1;                         // a fresh element each repaint: indeterminate until .value is set
      if (p.frac != null) bar.value = p.frac;
      const text = mk('span', 'tst-progress-text', p.text);
      const cancel = button('btn btn-ghost', 'Cancel export');
      cancel.onclick = async () => {
        cancel.disabled = true;
        const { data } = await host.export.cancel(dataState.job);
        if (data) { dataState.status = data; dataPaintJob(); }
        stopDataPoll();
      };
      parts.push(bar, text, cancel);
    } else if (st.status === 'done') {
      const res = st.result || {};
      const line = mk('div', 'set-note',
        `${res.name || ''} — ${DX.fmtInt(res.rows)} rows, ${DX.fmtBytes(res.bytes)}`);
      const reveal = button('btn btn-ghost', 'Show in Finder');
      const revealIcon = mk('span', 'icw sm');
      revealIcon.innerHTML = I.folderOpen;
      reveal.prepend(revealIcon);
      reveal.onclick = async () => {
        reveal.disabled = true;
        try { await host.export.reveal(dataState.job); } finally { reveal.disabled = false; }
      };
      parts.push(line, reveal);
    } else {
      parts.push(mk('div', 'set-acct-err', p.text));
    }
    dataJobBox.replaceChildren(...parts);
  }

  async function dataPollTick() {
    if (!dataState.job) { stopDataPoll(); return; }
    const st = await host.export.status(dataState.job);
    dataState.status = st;
    dataPaintJob();
    if (!st || DX.progress(st).final) stopDataPoll();
  }

  /* Reattaches to whatever export is running or last ran (GET /api/export/active), so closing and
     reopening Settings does not lose a job's Cancel/progress or its Done/error line. A no-op once
     this dialog session already has one (a fresh Start, or an earlier attach). */
  async function dataAttachActive() {
    if (dataState.job || !host.export.active) return;
    const st = await host.export.active();
    if (!st || !st.id || dataState.job) return;   // superseded meanwhile by a Start or another attach
    dataState.job = st.id;
    dataState.status = st;
    dataPaintJob();
    if (!DX.progress(st).final) {
      stopDataPoll();
      dataPollId = setInterval(dataPollTick, 700);
    }
  }

  const body = mk('div', 'set-body'), tabs = mk('div', 'set-tabs'), pane = mk('div', 'set-pane'), foot = mk('div', 'set-foot');
  tabs.setAttribute('role', 'tablist');
  tabs.setAttribute('aria-orientation', 'vertical');
  pane.setAttribute('role', 'tabpanel');
  body.append(tabs, pane);
  box.append(body, foot);
  pane.addEventListener('scroll', () => host.closeMenu());   // a popover never floats away from its swatch

  /* Live preview on the selected chart, at most once a frame (a dragged opacity slider fires per pixel). */
  function preview() {
    if (raf || done) return;
    raf = requestAnimationFrame(() => { raf = 0; if (!done) cell.setSettings(S.overrides(work)); });
  }
  function flush() { if (raf) { cancelAnimationFrame(raf); raf = 0; } }
  function set(key, v) { work = S.normalize({ ...work, [key]: v }); preview(); paint(); }
  /* What each colour field shows: its value, or the theme's colour while it follows the theme. */
  const shown = () => S.resolve(S.overrides(work), cell.P || {});
  function paint() { const r = shown(); for (const [k, i] of swatches) i.style.background = r[k] || ''; }

  function renderTabs() {
    const had = tabs.contains(document.activeElement);
    tabs.replaceChildren(...tabList.map((t, i) => {
      const b = button('set-tab' + (i === tab ? ' active' : '')), ic = mk('span', 'icw');
      b.setAttribute('role', 'tab');
      b.setAttribute('aria-selected', String(i === tab));
      // W3 (2026-09-28): at <= 640 px the label is hidden (icons only, charts.css) -- its name stays a tooltip and the
      // tab's accessible name
      b.title = t.label;
      b.setAttribute('aria-label', t.label);
      ic.innerHTML = I[t.icon] || '';   // our own static SVG strings
      b.append(ic, mk('span', '', t.label));
      b.onclick = () => { if (tab !== i) { tab = i; renderTabs(); renderPane(); } };
      return b;
    }));
    if (had) tabs.querySelector('.active').focus();
  }

  function renderPane() {
    host.closeMenu();
    swatches.clear();
    acctBox = acctWhy = algoSel = null;
    algoKey = acctKey = '';
    acctCells.clear();
    dataJobBox = dataCovBox = dataPreview = dataErr = null;   // this tab's live parts: null while it is not open
    // tab indexes tabList (the Trading tab is filtered out when host.accountRows is absent, e.g. Backtest),
    // so every lookup by `tab` must go through tabList, never the unfiltered TABS -- indexing TABS directly
    // would point at the wrong tab whenever 'trading' is missing and 'data' (after it) shifts down.
    pane.replaceChildren(...tabList[tab].sections.flatMap(([cap, rows]) => [mk('div', 'set-cap', cap), ...rows.map(row)]));
    pane.scrollTop = 0;
    paint();
    // a template is chart-appearance/indicators/interval/trade -- none of it applies to an export;
    // Apply to all would silently do nothing useful here too, so both stay hidden on this tab
    const onData = tabList[tab].id === 'data';
    tpl.hidden = onData;
    applyAll.hidden = onData;
  }

  /* ---- the Trading tab's ACCOUNTS list (2026-09-27 accounts-per-chart plan, Task 1) ----
     One row per account: a checkbox, the label, its env chip (LIVE red / DEMO grey / PAPER amber), the
     balance, and a quiet "in NQ 9:30 Straddle" when an algo on this chart's instrument books it. Ticking a
     LIVE row starts the two-step arm and only ticks on the second click; an account the desk does not list
     shows '?' and can never be ticked. Every rule is HBTradeUI.toggleAccount's -- a click only reports. */
  function paintAccounts() {
    if (!acctBox || !host.accountRows) return;
    const arming = host.armPending ? host.armPending() : null;
    const rows = host.accountRows(cell);
    // the rows are rebuilt only when something STRUCTURAL changed (a row, a tick, an arm). A balance or a
    // connection dot arrives up to once a frame while the desk is up: those update in place, so a rebuild can
    // never land between a viewer's pointerdown and the click it was about to make on a checkbox.
    const shape = JSON.stringify([arming, rows.map((r) => [r.id, r.label, r.chip, r.live, r.paper, r.tick, r.disabled, r.error, r.note])]);
    if (shape !== acctKey) {
      acctKey = shape;
      const active = document.activeElement;
      let focused = null;
      for (const [id, c] of acctCells) if (c.cb === active) focused = id;
      acctCells.clear();
      acctBox.replaceChildren(...(rows.length ? rows.map((r) => acctRow(r, arming))
        : [mk('div', 'set-unit', 'The desk has not listed any account yet')]));
      if (focused && acctCells.has(focused)) acctCells.get(focused).cb.focus();
    }
    for (const r of rows) {
      const c = acctCells.get(r.id);
      if (!c) continue;
      c.bal.textContent = r.balance;
      c.dot.className = 'sb-dot' + (r.connected ? ' ok' : ' bad');
    }
    if (acctWhy) {
      const why = host.tradeWhy ? host.tradeWhy(cell) : '';
      acctWhy.textContent = why;
      acctWhy.hidden = !why;
    }
  }
  function acctRow(r, arming) {
    const el = mk('div', 'set-acct'), cb = mk('input');
    cb.type = 'checkbox';
    cb.checked = r.tick === 'ticked';
    cb.indeterminate = r.tick === 'unarmed';
    cb.disabled = r.disabled;
    cb.setAttribute('aria-label', r.label);
    cb.title = r.tick === 'unarmed' ? "On this chart's list but not armed this session — click to remove it" : '';
    cb.onchange = () => { if (host.toggleAccount) host.toggleAccount(cell, r.id); paintAccounts(); syncAlgo(); };
    const lab = mk('div', 'set-acct-lab');
    if (arming === r.id) {
      lab.append(mk('span', 'set-acct-arm', 'Tick LIVE — real orders. Click again'));
    } else {
      lab.append(mk('span', 'set-acct-name', r.label));
      if (r.tick === 'unarmed') lab.append(mk('span', 'set-acct-arm', 'LIVE · not armed'));
      if (r.note) lab.append(mk('span', 'set-acct-note', r.note));
      if (r.error) lab.append(mk('span', 'set-acct-err', r.error));
    }
    const chip = mk('span', 'env' + (r.live ? ' live' : r.paper ? ' paper' : ''), r.chip);
    const dot = mk('span', 'sb-dot' + (r.connected ? ' ok' : ' bad'));
    const bal = mk('span', 'set-acct-bal', r.balance);
    acctCells.set(r.id, { cb, bal, dot });
    el.append(cb, lab, chip, bal, dot);
    return el;
  }

  /* Task 2b: "+ Add paper account" under the ACCOUNTS list -- a small inline form (name, starting balance), never a
     native prompt, and OUTSIDE the rows' box so a row rebuild can never destroy it mid-typing. The new account's
     row appears when the service's push lands; a refusal shows its reason in the form. */
  function paperAdder() {
    const wrap = mk('div', 'set-paper-add');
    const link = mk('button', 'set-link', '+ Add paper account');
    link.type = 'button';
    const form = mk('div', 'set-paper-form');
    form.hidden = true;
    const name = mk('input', 'set-num set-in'), bal = mk('input', 'set-num set-in-num');
    name.placeholder = 'Name'; name.maxLength = 32; name.setAttribute('aria-label', 'Paper account name');
    bal.value = '50000'; bal.inputMode = 'decimal'; bal.setAttribute('aria-label', 'Starting balance (USD)');
    const add = mk('button', 'btn btn-primary', 'Add'), cancel = mk('button', 'btn', 'Cancel'), err = mk('div', 'set-acct-err');
    add.type = cancel.type = 'button';
    err.hidden = true;
    const close = () => { form.hidden = true; link.hidden = false; err.hidden = true; name.value = ''; bal.value = '50000'; };
    link.onclick = () => { link.hidden = true; form.hidden = false; name.focus(); };
    cancel.onclick = close;
    add.onclick = async () => {
      if (add.disabled) return;
      const n = String(name.value || '').trim(), b = Number(String(bal.value || '').replace(/[$,\s]/g, ''));
      const bad = !n ? 'Give it a name' : !(b >= 1000 && b <= 10000000) ? 'Starting balance: $1,000 to $10,000,000' : '';
      if (bad) { err.textContent = bad; err.hidden = false; return; }
      add.disabled = true;
      try {
        const { status, data } = await host.createPaperAccount(n, b);
        if (status === 200 && data && data.ok) close();
        else { err.textContent = (data && (data.detail || data.error)) || `Refused (HTTP ${status})`; err.hidden = false; }
      } finally { add.disabled = false; }
    };
    form.append(name, bal, add, cancel, err);
    wrap.append(link, form);
    return wrap;
  }

  /* The Algo select's options and value, rebuilt only when either really changed (so a rebuild never happens
     under an open dropdown): ticking an account that belongs to an algo moves this select. */
  function syncAlgo() {
    if (!algoSel) return;
    const cur = (cell.cfg && cell.cfg.algo) || '';
    const choices = host.algoChoices ? host.algoChoices(cell) : [{ value: '', text: 'None' }];
    const key = JSON.stringify([choices, cur]);
    if (algoKey === key) return;
    algoKey = key;
    algoSel.replaceChildren(...choices.map((c) => { const o = mk('option', '', c.text); o.value = c.value; return o; }));
    algoSel.value = cur;
  }

  /* ---- the Data (export) tab (2026-09-28 data-export plan) ---- */
  function dataTab() {
    const box = mk('div', 'set-data');
    if (!host.export) { box.append(mk('div', 'set-note', 'Export is not available.')); return box; }
    const f = dataForm;

    function ctlRow(label, ...ctls) {
      const el = mk('div', 'set-row'), name = mk('label', 'set-name', label), ctl = mk('div', 'set-ctl');
      ctl.append(...ctls);
      el.append(name, ctl);
      return el;
    }
    function selectOf(label, choices, value, onchange) {
      const s = mk('select', 'set-select');
      s.setAttribute('aria-label', label);
      for (const c of choices) {
        const [v, text, disabled, title] = c;
        const o = mk('option', '', text);
        o.value = v;
        if (disabled) o.disabled = true;
        if (title) o.title = title;   // a disabled option's reason: a hover tip, never widens the closed select
        s.append(o);
      }
      s.value = value;
      s.onchange = () => onchange(s.value);   // read via closure, not the event -- works the same under a real
      return s;                               // browser (which ignores the unused event arg) and the node harness
    }

    function rebuild() {
      box.replaceChildren(...buildRows());
      dataUpdatePreview();
      dataPaintCoverage();
      dataPaintJob();
      dataRefreshMeta();     // async: repopulates the contract list + the on-disk range, then coverage
    }

    function buildRows() {
      const info = DX.TYPE_OF[f.type];
      const rows = [];
      let startInput, endInput;   // declared here: the quick-pick buttons below reference them, built after

      rows.push(ctlRow('Market', selectOf('Market', DX.ROOTS.map((r) => [r, r]), f.root, (v) => {
        f.root = v;
        f.contract = 'front';
        rebuild();
      })));

      if (info.needsContract) {
        dataContractSel = selectOf('Contract', [['front', 'Front month (auto)']], f.contract, (v) => {
          f.contract = v;
          dataRefreshCoverage();
        });
        dataContractSel.disabled = true;
        rows.push(ctlRow('Contract', dataContractSel));
      } else {
        dataContractSel = null;   // level2/level3: no per-contract choice (depth is recorded per root, not per symbol)
      }

      rows.push(ctlRow('Data type', selectOf('Data type',
        DX.TYPES.map((t) => [t.value, t.label, t.disabled, t.reason]), f.type, (v) => {
        f.type = v;
        f.contract = 'front';
        if (DX.TYPE_OF[f.type].depthOnly && f.root !== 'NQ' && f.root !== 'ES') f.root = 'NQ';
        rebuild();
      })));
      const l3 = DX.TYPE_OF.level3;
      rows.push(mk('div', 'set-note', `${l3.label} isn't offered: ${l3.reason}`));

      if (info.needsTimeframe) {
        rows.push(ctlRow('Timeframe', selectOf('Timeframe', DX.TIMEFRAMES.map((t) => [t, t]), f.timeframe, (v) => {
          f.timeframe = v;
          dataUpdatePreview();
        })));
      }
      if (info.needsLevels) {
        const n = mk('input', 'set-num');
        n.type = 'number'; n.min = '1'; n.max = '10'; n.step = '1'; n.value = String(f.levels);
        n.setAttribute('aria-label', 'Order book levels');
        n.onchange = () => { f.levels = Math.min(10, Math.max(1, Math.round(Number(n.value)) || 1)); n.value = String(f.levels); };
        rows.push(ctlRow('Levels (1-10)', n));
      }
      rows.push(mk('div', 'set-note', info.columns + (info.note ? ` — ${info.note}` : '')));

      dataRangeCap = mk('div', 'set-note', 'Checking what is on disk…');
      rows.push(dataRangeCap);

      rows.push(mk('div', 'set-cap', 'DATE RANGE'));
      const quickCtl = mk('div', 'set-ctl wrap');
      for (const [key, label] of DX.QUICK_PICKS) {
        const b = button('btn btn-ghost quick-btn', label);   // compact: short labels, all four fit on one line
        b.onclick = () => {
          const avail = (dataState.meta && dataState.meta.range) || null;
          const got = DX.quickRange(key, new Date(), DX.is247(f.root), avail);
          if (!got) return;
          f.start = got.start; f.end = got.end;
          startInput.value = f.start; endInput.value = f.end;
          dataRefreshCoverage();
        };
        quickCtl.append(b);
      }
      const quickRow = mk('div', 'set-row'), quickName = mk('label', 'set-name', 'Quick range');
      quickRow.classList.add('tall');   // the buttons wrap at narrow widths; a fixed 40px row clips/overlaps them
      quickRow.append(quickName, quickCtl);
      rows.push(quickRow);

      startInput = mk('input', 'set-num set-date');   // wide enough for YYYY-MM-DD; never type="date" (GOTCHAS)
      startInput.type = 'text'; startInput.placeholder = 'YYYY-MM-DD'; startInput.maxLength = 10;
      startInput.spellcheck = false; startInput.value = f.start;
      startInput.setAttribute('aria-label', 'From date');
      startInput.oninput = () => { f.start = startInput.value.trim(); dataUpdatePreview(); };
      startInput.onblur = () => dataRefreshCoverage();
      endInput = mk('input', 'set-num set-date');
      endInput.type = 'text'; endInput.placeholder = 'YYYY-MM-DD'; endInput.maxLength = 10;
      endInput.spellcheck = false; endInput.value = f.end;
      endInput.setAttribute('aria-label', 'To date');
      endInput.oninput = () => { f.end = endInput.value.trim(); dataUpdatePreview(); };
      endInput.onblur = () => dataRefreshCoverage();
      rows.push(ctlRow('From', startInput));
      rows.push(ctlRow('To', endInput));
      rows.push(ctlRow('Hours', selectOf('Hours', [['full', 'Full session'], ['rth', 'RTH 09:30–16:00 ET']],
        f.hours, (v) => { f.hours = v; })));

      dataCovBox = mk('div', 'set-why');
      dataCovBox.hidden = true;
      rows.push(dataCovBox);

      rows.push(mk('div', 'set-cap', 'OUTPUT'));
      rows.push(ctlRow('Timestamps', selectOf('Timezone', [['et', 'ET'], ['utc', 'UTC']], f.tz, (v) => { f.tz = v; }),
        selectOf('Timestamp format', [['iso', 'ISO (ms)'], ['epoch', 'Epoch (ms)']], f.ts_format,
          (v) => { f.ts_format = v; })));
      rows.push(ctlRow('Format', selectOf('File format', [['csv', 'CSV'], ['gz', 'CSV .gz']], f.format, (v) => {
        f.format = v;
        dataUpdatePreview();
      })));

      dataPreview = mk('div', 'set-note', '');
      rows.push(dataPreview);
      dataErr = mk('div', 'set-acct-err');
      dataErr.hidden = true;
      rows.push(dataErr);

      dataStartBtn = button('btn btn-primary', 'Start export');
      dataStartBtn.onclick = async () => {
        dataErr.hidden = true;
        const { body, error } = DX.buildRequest(f);
        if (error) { dataErr.textContent = error; dataErr.hidden = false; return; }
        dataStartBtn.disabled = true;
        const { data } = await host.export.start(body);
        if (!data || !data.id) {
          dataErr.textContent = (data && data.detail) || 'Could not start the export';
          dataErr.hidden = false;
          dataStartBtn.disabled = false;
          return;
        }
        dataState.job = data.id;
        dataState.status = { status: 'queued' };
        dataPaintJob();
        stopDataPoll();
        dataPollId = setInterval(dataPollTick, 700);
      };
      rows.push(ctlRow('', dataStartBtn));

      dataJobBox = mk('div', 'set-job');
      dataJobBox.hidden = true;
      rows.push(dataJobBox);

      return rows;
    }

    rebuild();
    dataAttachActive();
    return box;
  }

  function row(r) {
    if (r.accounts) {   // the ACCOUNTS list: a block of its own, not a label + control row
      const el = mk('div', 'set-accts');
      acctBox = mk('div', 'set-acct-list');
      acctWhy = mk('div', 'set-why');
      acctWhy.hidden = true;
      el.append(acctBox, acctWhy);
      if (host.createPaperAccount) el.append(paperAdder());
      paintAccounts();
      return el;
    }
    if (r.data) return dataTab();
    if (r.refresh) return refreshRow();
    if (r.caption) return mk('div', 'set-note', r.caption);
    const el = mk('div', 'set-row'), name = mk('label', 'set-name'), ctl = mk('div', 'set-ctl');
    if (r.check) {
      const cb = mk('input');
      cb.type = 'checkbox';
      cb.checked = !!work[r.check];
      cb.onchange = () => set(r.check, cb.checked);
      name.append(cb);
    }
    if (r.dot) { const d = mk('i', 'set-dot'); d.style.background = r.dot; name.append(d); }
    name.append(mk('span', '', r.label));
    for (const [key, what] of r.colors || []) {
      const b = button('swatch'), i = mk('i'), tip = `${r.label}${what ? ` ${what}` : ''} colour`;
      b.title = tip;
      b.setAttribute('aria-label', tip);
      b.setAttribute('aria-haspopup', 'dialog');
      b.append(i);
      swatches.set(key, i);
      b.onclick = () => swatchMenu(b, key);
      ctl.append(b);
    }
    if (r.select) {
      const { key, choices, parse } = r.select, s = mk('select', 'set-select');
      s.setAttribute('aria-label', r.label);
      for (const [v, text] of choices) { const o = mk('option', '', text); o.value = v; s.append(o); }
      s.value = work[key] == null ? '' : String(work[key]);
      s.onchange = () => set(key, parse ? parse(s.value) : s.value);
      ctl.append(s);
    }
    if (r.number) {
      const { key, min, max, unit } = r.number, n = mk('input', 'set-num');
      n.type = 'number'; n.min = String(min); n.max = String(max); n.step = '1';
      n.value = String(work[key]);
      n.setAttribute('aria-label', r.label);
      n.oninput = () => { if (n.value !== '') set(key, Number(n.value)); };
      n.onchange = () => { n.value = String(work[key]); };   // shows the clamped value
      ctl.append(n);
      if (unit) ctl.append(mk('span', 'set-unit', unit));
    }
    if (r.pref) {   // a viewer-wide trade preference (the one-click switches): every chart's, not this one's
      const { key, kind, min, max, note } = r.pref, cur = host.prefs ? host.prefs() : {};
      if (kind === 'switch') {
        const sw = button('switch' + (cur[key] ? ' on' : ''));
        sw.setAttribute('role', 'switch');
        sw.setAttribute('aria-checked', String(!!cur[key]));
        sw.setAttribute('aria-label', r.label);
        sw.onclick = () => {
          if (host.setPrefs) host.setPrefs({ [key]: !(host.prefs() || {})[key] });
          const on = !!(host.prefs ? host.prefs() : {})[key];
          sw.classList.toggle('on', on);
          sw.setAttribute('aria-checked', String(on));
        };
        ctl.append(sw);
      } else {
        const n = mk('input', 'set-num');
        n.type = 'number'; n.min = String(min); n.max = String(max); n.step = '1';
        n.value = String(cur[key] ?? min);
        n.setAttribute('aria-label', r.label);
        n.onchange = () => {
          const v = Math.round(Number(n.value));
          if (host.setPrefs) host.setPrefs({ [key]: Number.isFinite(v) ? v : cur[key] });
          n.value = String((host.prefs ? host.prefs() : cur)[key]);   // shows the clamped value
        };
        ctl.append(n);
        if (note) ctl.append(mk('span', 'set-unit', note));
      }
    }
    if (r.algo) {   // the chart's desk algo: None, or one of the desk's strategies on this chart's root
      const s = mk('select', 'set-select set-algo');
      s.setAttribute('aria-label', r.label);
      s.title = 'Draws this algo on the chart, and ticks the accounts it books on this instrument';
      // picking one also ticks its booked accounts (HBTradeUI.pickAlgo, through host.setAlgo); clearing it to
      // None leaves them alone -- unticking the accounts is how you watch an algo without trading it
      s.onchange = () => { if (host.setAlgo) host.setAlgo(cell, s.value || null); paintAccounts(); };
      algoSel = s;
      syncAlgo();
      ctl.append(s);
    }
    if (r.chips) {   // a multi-select: one checkbox per currency in the feed (plus any already picked)
      const key = r.chips, picked = new Set(work[key]), wrap = mk('div', 'set-chips');
      const all = [...new Set([...(host.countries ? host.countries() : []), ...work[key]])].sort();
      for (const c of all) {
        const lab = mk('label', 'set-chip'), cb = mk('input');
        cb.type = 'checkbox';
        cb.checked = picked.has(c);
        cb.onchange = () => set(key, cb.checked ? [...work[key], c] : work[key].filter((x) => x !== c));
        lab.append(cb, mk('span', '', c));
        wrap.append(lab);
      }
      if (!all.length) wrap.append(mk('span', 'set-unit', 'No calendar loaded yet'));
      ctl.append(wrap);
      el.classList.add('tall');
    }
    el.append(name, ctl);
    return el;
  }

  /* The swatch popover (menu styling): the palette, an opacity slider, a #RRGGBB field and "Default" (back to
     following the theme / the default). Picking a palette colour keeps the opacity. */
  function swatchMenu(anchor, key) {
    host.toggleMenu(anchor, 'menu-swatch', (m) => {
      const cur = () => shown()[key];
      const grid = mk('div', 'sw-grid'), err = mk('div', 'sw-err'), picks = [];
      err.hidden = true;
      err.setAttribute('role', 'alert');
      for (const hex of S.PALETTE.flat()) {
        const b = button('sw-cell');
        b.style.background = hex;
        b.title = hex;
        b.setAttribute('aria-label', hex);
        b.onclick = () => { set(key, S.withAlpha(hex, S.alphaOf(cur()))); sync(); };
        picks.push([hex, b]);
        grid.append(b);
      }
      const opRow = mk('div', 'sw-row'), op = mk('input'), pct = mk('span', 'sw-pct');
      op.type = 'range'; op.min = '0'; op.max = '100'; op.step = '1';
      op.setAttribute('aria-label', 'Opacity');
      op.oninput = () => { set(key, S.withAlpha(S.hexOf(cur()), Number(op.value) / 100)); sync(); };
      opRow.append(mk('span', '', 'Opacity'), op, pct);
      const hexRow = mk('div', 'sw-row'), hex = mk('input', 'sw-hex'), def = button('sw-default', 'Default');
      hex.type = 'text'; hex.maxLength = 7; hex.spellcheck = false;
      hex.setAttribute('aria-label', 'Hex colour');
      const takeHex = () => {
        const v = hex.value.trim();
        if (!/^#[0-9A-Fa-f]{6}$/.test(v)) { err.textContent = 'Use #RRGGBB'; err.hidden = false; return; }
        err.hidden = true;
        set(key, S.withAlpha(v, S.alphaOf(cur())));
        sync();
      };
      hex.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); if (e.repeat) return; takeHex(); } };   // S7
      hex.onchange = takeHex;
      def.onclick = () => { err.hidden = true; set(key, null); sync(); };
      hexRow.append(hex, def);
      m.append(grid, opRow, hexRow, err);
      function sync() {   // the popover shows the field's colour now
        const c = cur(), h = S.hexOf(c), a = Math.round(S.alphaOf(c) * 100);
        for (const [x, b] of picks) b.classList.toggle('on', x === h);
        op.value = String(a);
        pct.textContent = `${a}%`;
        if (document.activeElement !== hex) hex.value = h || '';
      }
      sync();
      (m.querySelector('.sw-cell.on') || picks[0][1]).focus();
    });
  }

  /* A template or "Apply defaults": the dialog's settings become it, previewed live; a template that also
     stored indicators or an interval (spec §8) applies those to the chart too, each with fresh uids. An old
     (Task 6/7) settings-only template, or "Apply defaults" (`{}`), touches only the settings. */
  function applyTemplate(raw) {
    const t = S.applyTemplate(raw);
    work = S.normalize(t.settings);
    renderPane();
    flush();
    cell.setSettings(S.overrides(work));   // applied now (not next frame): indicators below must see it
    const patch = {};
    if (t.indicators) patch.indicators = t.indicators;
    if (t.spec) patch.spec = t.spec;
    if (Object.keys(patch).length) cell.update(patch);
    if (host.applyTrade) {   // Task 2: its accounts (Trading always off) and algo, if stored
      host.applyTrade(cell, raw);
      renderPane();          // fix round 1, M5: the Trading tab's Algo select shows the template's algo, not the old one
    }
  }
  function menuBtn(text) {
    const b = button('menu-i');
    b.setAttribute('role', 'menuitem');
    b.append(mk('span', 'menu-t', text));
    return b;
  }

  /* Template ▾: Save as… (an inline name field, Enter saves), Apply defaults, then the saved templates (a click
     applies one to the dialog; × deletes it after an inline "Delete?"). Every error shows inline. */
  function templateMenu(anchor) {
    host.toggleMenu(anchor, 'menu-tpl', (m) => {
      const list = mk('div'), err = mk('div', 'menu-err'), saveAs = menuBtn('Save as…'), defaults = menuBtn('Apply defaults');
      err.hidden = true;
      err.setAttribute('role', 'alert');
      m.append(saveAs, defaults, mk('div', 'menu-sep'), list, err);
      const fail = (text) => { err.textContent = text; err.hidden = false; host.placeMenu(); };
      defaults.onclick = () => { host.closeMenu(); applyTemplate({}); };
      saveAs.onclick = () => {
        const wrap = mk('div'), rowEl = mk('div', 'menu-custom'), input = mk('input', 'menu-input'), go = button('btn btn-primary', 'Save');
        const opts = mk('div', 'menu-tpl-opts');
        const indLab = mk('label', 'set-chip'), indCb = mk('input');
        indCb.type = 'checkbox'; indCb.checked = true;
        indLab.append(indCb, mk('span', '', 'Include indicators'));
        const ivLab = mk('label', 'set-chip'), ivCb = mk('input');
        ivCb.type = 'checkbox'; ivCb.checked = false;
        ivLab.append(ivCb, mk('span', '', 'Include interval'));
        opts.append(indLab, ivLab);
        input.type = 'text'; input.placeholder = 'Template name'; input.maxLength = 40; input.spellcheck = false;
        input.setAttribute('aria-label', 'Template name');
        const save = async () => {
          const name = input.value.trim(), why = S.templateNameError(name);
          if (why) { fail(why); input.focus(); return; }
          const body = { ...S.buildTemplate({ settings: work, indicators: cell.cfg.indicators, spec: cell.cfg.spec },
            { indicators: indCb.checked, interval: ivCb.checked }), ...(tradeBits(cell) || {}) };   // Task 2: accounts + algo
          const res = await host.templates.save(name, body);
          if (res) { fail(res); return; }
          host.closeMenu();
        };
        go.onclick = save;
        input.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); if (e.repeat) return; save(); } };   // S7: one PUT per press
        rowEl.append(input, go);
        wrap.append(rowEl, opts);
        saveAs.replaceWith(wrap);
        input.focus();
      };
      list.append(mk('div', 'menu-empty', 'Loading…'));
      host.templates.list().then((all) => {
        if (!m.isConnected) return;   // closed meanwhile
        if (!all) { list.replaceChildren(); fail('could not load the templates'); return; }
        const names = Object.keys(all).sort((a, b) => a.localeCompare(b));
        list.replaceChildren(...(names.length ? names.map((n) => tplRow(n, all[n])) : [mk('div', 'menu-empty', 'No saved templates')]));
        host.placeMenu();
      });
      function tplRow(name, settings) {
        const r = mk('div', 'menu-row'), pick = menuBtn(name), del = button('menu-del');
        del.title = `Delete ${name}`;
        del.setAttribute('aria-label', `Delete ${name}`);
        del.innerHTML = I.x;   // our own static SVG string
        pick.onclick = () => { host.closeMenu(); applyTemplate(settings); };
        del.onclick = () => {
          const ask = mk('div', 'menu-confirm'), yes = button('btn btn-danger', 'Delete'), no = button('btn btn-ghost', 'Cancel');
          ask.append(mk('span', '', `Delete “${name}”?`), yes, no);
          r.replaceWith(ask);
          no.focus();
          no.onclick = () => { ask.replaceWith(r); del.focus(); };
          yes.onclick = async () => {
            const res = await host.templates.remove(name);
            if (res) { ask.replaceWith(r); fail(res); return; }
            ask.remove();
            if (!list.querySelector('.menu-row, .menu-confirm')) list.replaceChildren(mk('div', 'menu-empty', 'No saved templates'));
          };
        };
        r.append(pick, del);
        return r;
      }
    });
  }

  /* ---- footer ---- */
  const grow = mk('span', 'grow'), cancel = button('btn btn-ghost', 'Cancel'), ok = button('btn btn-solid', 'Ok');
  cancel.onclick = () => host.cancel();
  ok.onclick = () => {
    flush();
    stopWatching();
    stopDataPoll();
    stopRefreshPoll();
    cell.setSettings(S.overrides(work));
    done = true;
    host.commit(host.cells().some((c) => {
      const at = atOpen.get(c);
      return !at || JSON.stringify(c.settings()) !== JSON.stringify(at.settings)
        || JSON.stringify(c.cfg.indicators) !== JSON.stringify(at.indicators)
        || c.cfg.spec !== at.spec
        || JSON.stringify(tradeBits(c)) !== JSON.stringify(at.trade);
    }));
  };
  const tpl = button('btn btn-ghost tpl-btn'), chev = mk('span', 'icw sm'), applyAll = button('btn btn-ghost', 'Apply to all');
  chev.innerHTML = I.chevron;
  tpl.append(mk('span', '', 'Template'), chev);
  tpl.setAttribute('aria-haspopup', 'menu');
  tpl.onclick = () => templateMenu(tpl);
  applyAll.title = 'Copy these settings to every chart in the layout';
  applyAll.onclick = () => {   // live on every chart; the dialog stays open (Cancel puts them all back)
    flush();
    const o = S.overrides(work);
    for (const c of host.cells()) c.setSettings(o);
  };
  foot.append(tpl, grow, applyAll, cancel, ok);

  /* The chart's accounts, its algo, the desk's list and a LIVE arm's 3 s window can all change while the
     dialog is open. Re-read only the Trading tab's live parts, so a half-typed number or an open swatch
     popover elsewhere in the pane survives. */
  function syncTrading() { paintAccounts(); syncAlgo(); }
  let unsub = host.onTradeChange ? host.onTradeChange(syncTrading) : null;
  const stopWatching = () => { if (unsub) { unsub(); unsub = null; } };

  renderTabs();
  renderPane();
  tabs.querySelector('.active').focus();

  return {
    /* Cancel, ×, Esc, a backdrop click: every chart back to its settings — and its indicators and interval,
       since a template Apply can have changed any of those too (spec §8) — at open. After Ok: nothing. */
    revert() {
      stopWatching();
      stopDataPoll();
      stopRefreshPoll();
      if (done) return;
      done = true;
      flush();
      const now = host.cells();
      for (const [c, at] of atOpen) {
        if (!now.includes(c)) continue;
        c.setSettings(at.settings);
        const patch = {};
        if (JSON.stringify(c.cfg.indicators) !== JSON.stringify(at.indicators)) patch.indicators = at.indicators;
        if (c.cfg.spec !== at.spec) patch.spec = at.spec;
        if (Object.keys(patch).length) c.update(patch);
        // Task 2: accounts + algo back as at open -- with Trading OFF (host.restoreTrade), never switched back on
        if (host.restoreTrade && JSON.stringify(tradeBits(c)) !== JSON.stringify(at.trade)) host.restoreTrade(c, at.trade);
      }
    },
  };
}

window.HBSettingsDialog = { mount, TABS };
})();
