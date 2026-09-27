/* Homebase Charts — the Strategy Tester panel, the pure half:
     - the run form: defaults from a strategy's input schema, the range presets, the holdout rule
       the server enforces, the request body, Run vs Update report;
     - the progress text;
     - the report's tiles, tables, trade rows, badges and chart marks;
     - the interval a jump to an old trade can use.
   No browser globals at load time: the Node tests load this file directly. */
(function () {
'use strict';
const need = (name, file) => (typeof window !== 'undefined' && window[name]) || (typeof require === 'function' ? require(file) : null);
const Cat = need('HBCatalog', './catalog.js');
const Tr = need('HBTrade', './trade.js');

const MINUS = '−';
const HOLDOUT_START = '2025-01-01';
const DEFAULT_RULES = 'lucid-flex-50k@2026-08';
const REASON_MAX = 200;
const RANGES = [{ kind: 'research', label: 'Research window 2021–2024' },
  { kind: 'is_months', label: 'IS months only (Jan/Apr/Jul/Oct)' }, { kind: 'custom', label: 'Custom…' }];
const HOLDOUT_MSG = 'This range reaches 2025 or later (holdout data): turn on Holdout and give a one-line reason';
const ISO = /^\d{4}-\d{2}-\d{2}$/;
const ET = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', hourCycle: 'h23', year: 'numeric', month: '2-digit',
  day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' });
const COSTS = [['qty', 'Qty', 1, 100, true], ['commission', 'Commission', 0, 100, false], ['slippage_ticks', 'Slippage (ticks)', 0, 20, false]];

/* ---- formatting ---- */
const neg = (s, v) => (v < 0 ? MINUS + s : s);
/* `inf`: cap at 999 and show '∞' -- only Profit factor and RR are unbounded ratios that can blow up
   (a near-zero denominator); every other num() caller (Sharpe, t-stat, avg bars in trade, Sortino, …) is
   a plain magnitude that can legitimately sit at or past 999 (review M5: a >16.6h trade's "avg bars"
   used to read ∞ because this cap applied to every num() call). */
function num(v, d = 2, inf = false) { return v == null || !Number.isFinite(v) ? '—' : (inf && v >= 999) ? '∞' : neg(Math.abs(v).toFixed(d), v); }
function pct(v) { return v == null || !Number.isFinite(v) ? '—' : (v > 0 ? '+' : v < 0 ? MINUS : '') + Math.abs(v).toFixed(2) + '%'; }
function rate(v) { return v == null || !Number.isFinite(v) ? '—' : v.toFixed(1) + '%'; }
function dur(s) {
  if (s == null || !Number.isFinite(s)) return '—';
  s = Math.round(s);
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m ${s % 60}s`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ${String(Math.floor((s % 3600) / 60)).padStart(2, '0')}m`;
  return `${Math.floor(s / 86400)}d ${Math.floor((s % 86400) / 3600)}h`;
}
function fmtEt(ms) {
  if (!Number.isFinite(ms)) return '—';
  const p = Object.fromEntries(ET.formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}:${p.second}`;
}
const int = (v) => (v == null ? '—' : Number(v).toLocaleString('en-US'));
const signed = (v) => Tr.usd(v) ?? '—';

/* ---- the form ---- */
function inputError(inp, v) {
  if (inp.type === 'bool') return typeof v === 'boolean' ? null : `${inp.label}: on or off`;
  if (inp.type === 'choice') return inp.choices.includes(v) ? null : `${inp.label}: one of ${inp.choices.join(', ')}`;
  if (typeof v !== 'number' || !Number.isFinite(v)) return `${inp.label}: a number`;
  if (inp.type === 'int' && !Number.isInteger(v)) return `${inp.label}: a whole number`;
  if ((inp.min != null && v < inp.min) || (inp.max != null && v > inp.max)) return `${inp.label}: ${inp.min} to ${inp.max}`;
  return null;
}
function defaults(s) {
  return { strategy: s.id, inputs: Object.fromEntries(s.inputs.map((i) => [i.key, i.default])),
    range: { kind: 'research', start: '', end: '' }, qty: 1, commission: 4, slippage_ticks: 1,
    prop_rules: DEFAULT_RULES, holdout: { on: false, reason: '' } };
}
/* A saved form for strategy s: its valid values over the defaults (anything unknown or invalid is dropped). */
function restore(saved, s) {
  const f = defaults(s);
  if (!saved || saved.strategy !== s.id) return f;
  for (const i of s.inputs) { const v = saved.inputs && saved.inputs[i.key]; if (v !== undefined && !inputError(i, v)) f.inputs[i.key] = v; }
  const r = saved.range || {};
  if (RANGES.some((x) => x.kind === r.kind)) f.range = { kind: r.kind, start: ISO.test(r.start) ? r.start : '', end: ISO.test(r.end) ? r.end : '' };
  for (const [k, , lo, hi, whole] of COSTS) { const v = saved[k]; if (typeof v === 'number' && v >= lo && v <= hi && (!whole || Number.isInteger(v))) f[k] = v; }
  if (typeof saved.prop_rules === 'string') f.prop_rules = saved.prop_rules;
  // C1 (critical, 2026-09-27 review): the Holdout switch is never persisted or restored -- `on` is
  // always false coming out of restore(), whatever a saved form (or a loaded run, via fromRun below)
  // says. Approval to spend holdout data is per use, not a standing preference. The reason text alone
  // is still carried over, so a re-armed switch doesn't force retyping it.
  if (saved.holdout && typeof saved.holdout.reason === 'string') f.holdout = { on: false, reason: saved.holdout.reason.slice(0, REASON_MAX) };
  return f;
}
function fromRun(run, s) {
  return restore({ strategy: run.strategy.id, inputs: run.inputs,
    range: { kind: run.range.kind, start: run.range.kind === 'research' ? '' : run.range.start, end: run.range.kind === 'research' ? '' : run.range.end },
    qty: run.qty, commission: run.commission, slippage_ticks: run.slippage_ticks, prop_rules: run.prop_rules,
    holdout: { on: !!run.holdout, reason: run.holdout_reason || '' } }, s);
}
function reachesHoldout(r) { return !!r && r.kind !== 'research' && (r.end || '2024-12-31') >= HOLDOUT_START; }
function problems(f, s) {
  for (const i of s.inputs) { const e = inputError(i, f.inputs[i.key]); if (e) return e; }
  for (const [k, label, lo, hi, whole] of COSTS) {
    const v = f[k];
    if (typeof v !== 'number' || !Number.isFinite(v) || v < lo || v > hi || (whole && !Number.isInteger(v))) return `${label}: ${lo} to ${hi}`;
  }
  const r = f.range;
  if (r.kind === 'custom' && !(ISO.test(r.start) && ISO.test(r.end))) return 'A custom range needs a start and an end date';
  if (r.kind !== 'research' && r.start && r.end && r.start > r.end) return 'The start date is after the end date';
  if (reachesHoldout(r)) {
    const why = (f.holdout.reason || '').trim();
    if (!f.holdout.on || !why) return HOLDOUT_MSG;
    if (why.includes('\n') || why.length > REASON_MAX) return `The holdout reason is one line of at most ${REASON_MAX} characters`;
  }
  return null;
}
function rangeBody(r) {
  if (r.kind === 'research') return { kind: 'research' };
  const b = { kind: r.kind };
  if (r.start) b.start = r.start;
  if (r.end) b.end = r.end;
  return b;
}
/* The POST /api/tester/run body. holdout only when the range reaches 2025 (ruling S16: no spend otherwise). */
function body(f) {
  const b = { strategy: f.strategy, inputs: { ...f.inputs }, range: rangeBody(f.range), qty: f.qty, commission: f.commission,
    slippage_ticks: f.slippage_ticks, prop_rules: f.prop_rules };
  if (reachesHoldout(f.range)) b.holdout = { reason: f.holdout.reason.trim() };
  return b;
}
const key = (f) => JSON.stringify(body(f));
function runLabel(f, loadedKey) { return loadedKey && key(f) !== loadedKey ? 'Update report' : 'Run'; }

function progress(st) {
  const s = st && st.status;
  if (s === 'queued') return { text: 'Queued…', frac: null, final: false };
  if (s === 'running') {
    const n = `${int(st.done)} / ${int(st.total)} sessions`, frac = st.total ? st.done / st.total : null;
    if (st.phase === 'building cache') return { text: `Building the tick cache · ${n}`, frac, final: false };
    if (st.phase === 'daily bars') return { text: 'Loading daily bars…', frac: null, final: false };
    if (st.phase === 'prop sim') return { text: 'Prop sim…', frac: 1, final: false };
    return { text: `Running · ${n}`, frac, final: false };
  }
  if (s === 'error') return { text: `Failed: ${st.error || 'unknown error'}`, frac: null, final: true };
  if (s === 'cancelled') return { text: 'Cancelled', frac: null, final: true };
  if (s === 'done') return { text: 'Done', frac: 1, final: true };
  return { text: '', frac: null, final: false };
}

/* ---- the report ---- */
const toneOf = (v) => (v > 0 ? 'up' : v < 0 ? 'down' : '');
function tiles(run) {
  const a = run.report.summary.all;
  return [
    { label: 'Net P&L', value: signed(a.net_profit), sub: pct(a.net_profit_pct), tone: toneOf(a.net_profit) },
    { label: 'Max drawdown', value: Tr.money(a.max_drawdown), sub: pct(a.max_drawdown_pct), tone: toneOf(a.max_drawdown) },
    { label: 'Win rate', value: rate(a.win_rate), sub: `${a.wins ?? 0}/${a.trades ?? 0}`, tone: '' },
    { label: 'Profit factor', value: num(a.profit_factor, 2, true), sub: '', tone: '' },
    { label: 'Sharpe', value: num(a.sharpe), sub: 'weekday grid', tone: '', title: run.report.sharpe_basis },
    { label: 'Avg trade', value: signed(a.avg_trade), sub: '', tone: toneOf(a.avg_trade) },
    { label: 'Avg win : loss', value: a.rr_label && a.rr_label !== '—' ? `RR ${a.rr_label}` : '—', sub: '', tone: '' },
    { label: 't-stat', value: num(a.t_stat), sub: '', tone: '' }];
}
function badges(run) {
  const c = run.coverage || {}, out = [{ text: 'Tick replay', tone: 'info', title: 'Fills replay the tape: a stop entry pays the gap, a target needs 1-tick penetration' }];
  const skipped = (c.skipped || []).length, why = Object.entries(c.skipped_by_reason || {}).map(([k, n]) => `${n} × ${k}`).join('\n');
  out.push({ text: `${int(c.used)} of ${int(c.sessions)} sessions`, tone: skipped ? 'warn' : 'info', title: why || 'Every session in the range was used' });
  const errs = run.report.skipped_by_error || 0;
  if (errs) out.push({ text: `${errs} strategy error${errs === 1 ? '' : 's'}`, tone: 'err', title: 'Sessions the strategy crashed on (see Properties)' });
  if (run.holdout) out.push({ text: 'Includes holdout', tone: 'err', title: run.holdout_reason || '' });
  return out;
}
function propView(p) {
  const rules = p ? p.rules || null : null, unconfirmed = !!(rules && rules.confirmed === false);
  if (!p) return { message: 'No prop-eval result in this run', rules: null, unconfirmed: false };
  if (p.error) return { message: `Prop eval failed: ${p.error}`, rules, unconfirmed };
  if (p.skipped) return { message: p.skipped, rules, unconfirmed };
  const h = p.headline, ci = h.eval_pass_ci;
  return { rules, unconfirmed, caveat: p.caveat || '', tiles: [
    { label: 'Eval pass', value: rate(h.eval_pass_p * 100), sub: ci ? `95% CI ${(ci[0] * 100).toFixed(1)}–${(ci[1] * 100).toFixed(1)}%` : '' },
    { label: 'Bust', value: rate(h.bust_p * 100), sub: '' },
    { label: 'Median days to pass', value: h.median_days_to_pass == null ? '—' : String(Math.round(h.median_days_to_pass)), sub: '' },
    { label: 'Funded: expected cheque', value: Tr.money(h.funded_expected_cheque), sub: '' }] };
}
const SUMMARY = [
  ['Net profit', (c) => `${signed(c.net_profit)} (${pct(c.net_profit_pct)})`],
  ['Gross profit', (c) => Tr.money(c.gross_profit)], ['Gross loss', (c) => Tr.money(c.gross_loss)],
  ['Commission paid', (c) => Tr.money(c.commission_paid)],
  ['Max drawdown', (c) => `${Tr.money(c.max_drawdown)} (${pct(c.max_drawdown_pct)})`], ['Max run-up', (c) => Tr.money(c.max_runup)],
  ['Profit factor', (c) => num(c.profit_factor, 2, true)], ['Total trades', (c) => int(c.trades)], ['Winning trades', (c) => int(c.wins)],
  ['Losing trades', (c) => int(c.losses)], ['Percent profitable', (c) => rate(c.win_rate)], ['Avg trade', (c) => signed(c.avg_trade)],
  ['Avg winning trade', (c) => signed(c.avg_win)], ['Avg losing trade', (c) => signed(c.avg_loss)],
  ['Ratio avg win / avg loss', (c) => (c.rr_label && c.rr_label !== '—' ? `RR ${c.rr_label}` : '—')],
  ['Largest winning trade', (c) => signed(c.largest_win)], ['Largest losing trade', (c) => signed(c.largest_loss)],
  ['Avg time in trade', (c) => dur(c.avg_seconds_in_trade)], ['Avg bars in trade', (c) => num(c.avg_bars_in_trade, 1)],
  ['Max consecutive losses', (c) => int(c.max_consec_losses)], ['Sharpe ratio', (c) => num(c.sharpe)], ['Sortino ratio', (c) => num(c.sortino)],
  ['Sharpe (traded days only)', (c) => num(c.sharpe_traded_days)], ['t-stat', (c) => num(c.t_stat)], ['Expectancy', (c) => signed(c.expectancy)],
  ['Trading days', (c) => int(c.days)]];
function summaryRows(s) { return SUMMARY.map(([label, f]) => ({ label, all: f(s.all), long: f(s.long), short: f(s.short) })); }
function periodRows(list) {
  return (list || []).map((p) => ({ period: p.period, trades: int(p.trades), net: signed(p.net), tone: toneOf(p.net), win: rate(p.win_rate),
    pf: num(p.profit_factor), dd: Tr.money(p.max_drawdown), sharpe: num(p.sharpe), avg: signed(p.avg_trade) }));
}

/* ---- the list of trades ---- */
const SORT = { n: (t, i) => i, side: (t) => t.side, entry: (t) => t.entry_ms, exit: (t) => t.exit_ms, reason: (t) => t.exit_reason,
  qty: (t) => t.qty, net: (t) => t.net, mae: (t) => t.mae_usd, mfe: (t) => t.mfe_usd, dur: (t) => t.seconds };
/* Trade indices sorted by column `k`, dir 1 ascending / −1 descending; ties keep the trade order. */
function sortTrades(trades, k, dir) {
  const f = SORT[k] || SORT.n;
  return trades.map((t, i) => i).sort((a, b) => {
    const x = f(trades[a], a), y = f(trades[b], b);
    return (x < y ? -1 : x > y ? 1 : 0) * dir || a - b;
  });
}
/* mae_usd (and mfe_usd) are magnitudes from the engine, always >= 0 (engine.py: `max(0.0, ...)`; its own
   test asserts 45.0, never -45.0). MFE is favorable, so signed()'s "+" reads right; MAE is how far the
   trade went AGAINST you, so it must read as a loss (review I2 -- signed() showed an adverse excursion
   as "+$45"). */
function tradeCells(t, i, tick) {
  return [String(i + 1), t.side === 'long' ? 'Long' : 'Short', fmtEt(t.entry_ms), Cat.fmtPrice(t.entry_price, tick), fmtEt(t.exit_ms),
    Cat.fmtPrice(t.exit_price, tick), String(t.exit_reason || '').toUpperCase(), String(t.qty), signed(t.net),
    t.mae_usd ? MINUS + Tr.money(Math.abs(t.mae_usd)) : '$0', signed(t.mfe_usd), dur(t.seconds)];
}
/* Entry ▲/▼ at the entry price, exit ● at the exit price with the net $ (ruling S21); {ms,…} for placeMarkers. */
function tradeMarks(trades, P) {
  const out = [];
  trades.forEach((t, i) => {
    const long = t.side === 'long';
    out.push({ id: `te${i}`, ms: t.entry_ms, price: t.entry_price, position: long ? 'atPriceBottom' : 'atPriceTop',
      shape: long ? 'arrowUp' : 'arrowDown', color: long ? P.accent : P.down, text: '' });
    out.push({ id: `tx${i}`, ms: t.exit_ms, price: t.exit_price, position: 'atPriceMiddle', shape: 'circle',
      color: t.net >= 0 ? P.up : P.down, text: signed(t.net), size: 0.6 });
  });
  return out;
}
function equitySeries(eq) {
  const out = { equity: [], drawdown: [] };
  let last = -Infinity;
  (eq.t_ms || []).forEach((ms, i) => {
    let t = Math.floor(ms / 1000);
    if (t <= last) t = last + 1;
    last = t;
    out.equity.push({ time: t, value: eq.equity[i] });
    out.drawdown.push({ time: t, value: eq.drawdown[i] });
  });
  return out;
}

/* The interval a jump back to `ms` can use (ruling S20): the chart's own time interval when the sessions back to
   it fit under 90% of the client cap, else the finest of 5m, 15m, 1h, 4h, D that does. 23 h sessions, 5 per week. */
function reachSpec(spec, ms, nowMs, cap = 200000) {
  const sessions = Math.ceil(Math.max(1, (nowMs - ms) / 86400000) * 5 / 7) + 2;
  const fits = (sec) => sessions * Math.ceil(82800 / sec) <= cap * 0.9;
  const m = /^time:(\d+)$/.exec(spec), own = m ? Number(m[1]) : 0;
  if (own && fits(own)) return spec;
  for (const s of [300, 900, 3600, 14400, 86400]) if (s >= own && fits(s)) return `time:${s}`;
  return 'time:86400';
}

/* ---- the parameter heat-map (research window 2021–2024 only; the server forces it) ---- */
const MAX_CELLS = 60;
const RANGE_MSG = 'a range is start:end:step with start ≤ end and step > 0';
const decimals = (x) => { const m = /\.(\d+)$/.exec(String(x)); return m ? m[1].length : 0; };
/* One axis's values from the text box: "5, 10, 15", "5:20:5" (inclusive), mixes of both; bools as on/off
   (true/false); a choice by name. {values} or {error}; every value passes inputError, none twice. */
function parseValues(text, inp) {
  const toks = String(text || '').split(/[\s,]+/).filter(Boolean);
  if (!toks.length) return { error: `${inp.label}: enter values` };
  const out = [];
  for (const t of toks) {
    if (inp.type === 'bool') {
      const v = { on: true, true: true, off: false, false: false }[t.toLowerCase()];
      if (v === undefined) return { error: `${inp.label}: on or off` };
      out.push(v);
    } else if (inp.type === 'choice') {
      out.push(t);
    } else if (t.includes(':')) {
      const parts = t.split(':'), [a, b, st] = parts.map(Number);
      if (parts.length !== 3 || ![a, b, st].every(Number.isFinite) || !(st > 0) || a > b) return { error: `${inp.label}: ${RANGE_MSG}` };
      if ((b - a) / st + 1 > MAX_CELLS + 1e-9) return { error: `${inp.label}: more than ${MAX_CELLS} values` };
      const d = Math.max(decimals(parts[0]), decimals(parts[2]));
      for (let k = 0; ; k++) {
        const v = Number((a + k * st).toFixed(d));
        if (v > b + 1e-9) break;
        out.push(v);
      }
    } else {
      const v = Number(t);
      if (!Number.isFinite(v)) return { error: `${inp.label}: "${t}" is not a number` };
      out.push(v);
    }
  }
  if (out.length > MAX_CELLS) return { error: `${inp.label}: more than ${MAX_CELLS} values` };
  for (let j = 0; j < out.length; j++) {
    const e = inputError(inp, out[j]);
    if (e) return { error: e };
    if (out.indexOf(out[j]) !== j) return { error: `${inp.label}: ${valueLabel(out[j])} twice` };
  }
  return { values: out };
}
function valueLabel(v) { return typeof v === 'boolean' ? (v ? 'on' : 'off') : String(v); }
/* The axis rows [{key, text}] (key '' = unused) -> {axes: [{key, values}]} or {error}. */
function gridAxes(rows, s) {
  const used = rows.filter((r) => r.key);
  if (used.length < 2 || used.length > 3) return { error: 'Pick 2 or 3 parameters' };
  const axes = [];
  for (const r of used) {
    const inp = s.inputs.find((i) => i.key === r.key);
    if (!inp) return { error: `Unknown parameter ${r.key}` };
    if (axes.some((a) => a.key === r.key)) return { error: `${inp.label} is picked twice` };
    const p = parseValues(r.text, inp);
    if (p.error) return { error: p.error };
    axes.push({ key: r.key, values: p.values });
  }
  return { axes };
}
const gridCount = (axes) => axes.reduce((n, a) => n * a.values.length, 1);
function gridProblems(f, s, rows) {
  const g = gridAxes(rows, s);
  if (g.error) return g.error;
  const n = gridCount(g.axes);
  if (n > MAX_CELLS) return `${n} cells: a grid is at most ${MAX_CELLS}`;
  const varied = new Set(g.axes.map((a) => a.key));
  for (const i of s.inputs) { if (!varied.has(i.key)) { const e = inputError(i, f.inputs[i.key]); if (e) return e; } }
  for (const [k, label, lo, hi, whole] of COSTS) {
    const v = f[k];
    if (typeof v !== 'number' || !Number.isFinite(v) || v < lo || v > hi || (whole && !Number.isInteger(v))) return `${label}: ${lo} to ${hi}`;
  }
  return null;
}
/* The POST /api/tester/grid body: never a range or a holdout -- the heat-map is the research window only. */
function gridBody(f, axes) {
  const varied = new Set(axes.map((a) => a.key));
  return { strategy: f.strategy, inputs: Object.fromEntries(Object.entries(f.inputs).filter(([k]) => !varied.has(k))),
    axes: axes.map((a) => ({ key: a.key, values: [...a.values] })), qty: f.qty, commission: f.commission,
    slippage_ticks: f.slippage_ticks, prop_rules: f.prop_rules };
}
function looksText(n) {
  n = Number.isFinite(n) ? n : 0;
  return `looks this strategy: ${n} — expect ~${Math.round(n / 20)} lucky cells at 5%`;
}
/* Rows = the 1st parameter, columns = the 2nd, one panel per value of a 3rd; cells[r][c] = the cell index. */
function heatPanels(g) {
  const [ra, ca, pa] = g.axes, at = new Map(g.cells.map((c) => [c.coords.join(','), c.i]));
  return (pa ? pa.values : [null]).map((pv, p) => ({
    title: pa ? `${pa.label} = ${valueLabel(pv)}` : null, rowLabel: ra.label, colLabel: ca.label,
    rows: ra.values.map(valueLabel), cols: ca.values.map(valueLabel),
    cells: ra.values.map((_, r) => ca.values.map((__, c) => at.get((pa ? [r, c, p] : [r, c]).join(',')))) }));
}
function heatMaxAbs(g) {
  return g.cells.reduce((m, c) => (c.status === 'done' && c.summary && Number.isFinite(c.summary.net_profit)
    ? Math.max(m, Math.abs(c.summary.net_profit)) : m), 0);
}
function heatLevel(v, maxAbs) {
  if (v == null || !Number.isFinite(v) || !v || !(maxAbs > 0)) return { tone: '', alpha: 0 };
  return { tone: toneOf(v), alpha: Math.round((0.1 + 0.6 * Math.min(1, Math.abs(v) / maxAbs)) * 100) / 100 };
}
const CELL_STATE = { queued: '·', running: '…', error: 'error', cancelled: '—' };
function cellView(c) {
  if (c.status !== 'done' || !c.summary) return { state: c.status, net: CELL_STATE[c.status] || '·', sharpe: '', tone: '', warn: '', title: c.error || c.status };
  const s = c.summary, errs = s.skipped_by_error || 0;
  return { state: 'done', net: signed(s.net_profit), sharpe: `Sharpe ${num(s.sharpe)}`, tone: toneOf(s.net_profit),
    warn: errs ? `${errs} strategy error${errs === 1 ? '' : 's'}` : '',
    title: `${int(s.trades)} trades · WR ${rate(s.win_rate)} · PF ${num(s.profit_factor, 2, true)} · t ${num(s.t_stat)} · max DD ${Tr.money(s.max_drawdown)}` };
}
function gridProgress(st) {
  const s = st && st.status, n = `${int(st && st.done)} / ${int(st && st.total)} cells`;
  const frac = st && st.total ? st.done / st.total : null;
  if (s === 'queued') return { text: `Queued · ${n}`, frac: null, final: false };
  if (s === 'running') return { text: `Running · ${n}`, frac, final: false };
  if (s === 'done') return { text: `Done · ${n}`, frac: 1, final: true };
  if (s === 'cancelled') return { text: `Cancelled · ${n}${st.error ? ' · ' + st.error : ''}`, frac, final: true };
  return { text: '', frac: null, final: false };
}

const api = { MAX_CELLS, parseValues, valueLabel, gridAxes, gridCount, gridProblems, gridBody, looksText, heatPanels, heatMaxAbs,
  heatLevel, cellView, gridProgress, RANGES, HOLDOUT_START, DEFAULT_RULES, REASON_MAX, defaults, restore, fromRun, reachesHoldout, problems, inputError, body,
  key, runLabel, progress, pct, rate, num, dur, fmtEt, tiles, badges, propView, summaryRows, periodRows, sortTrades, tradeCells,
  tradeMarks, equitySeries, reachSpec, toneOf };
if (typeof window !== 'undefined') window.HBTester = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
