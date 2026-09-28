/* Homebase Charts — the Strategy Tester panel, the pure half:
     - the run form: defaults from a strategy's input schema, the range picker (fixed-window presets,
       the walk-forward ratios that compose with them, and a typed custom range), the request body,
       Run vs Update report;
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
const DEFAULT_RULES = 'lucid-flex-50k@2026-09-27';
const ISO = /^\d{4}-\d{2}-\d{2}$/;

/* ---- the range picker (one pill -> a menu of presets -> a Custom dialog) ----
   A form's range is {id, start, end, wf}. `id` names one of the fixed windows below (or 'custom',
   where start/end are the typed dates). `wf` is null, or a walk-forward ratio 1 | 2 | 3 -- months
   OUT-of-sample per 1 selection month -- which COMPOSES with whichever window is chosen, so
   "2025-2026 · WF 1:1" is a walk-forward run over 2025-2026. `wf: 'compare'` = the three ratios
   side by side from one grid run ("2021-2024 · WF compare"). `end: null` in the table means today
   (ET: the session clock, not the viewer's). 2026-09-27: nothing here refuses a date any more. */
const RANGES = [
  { id: 'research', label: '2021-2024', start: '2021-01-01', end: '2024-12-31' },
  { id: '2022-2024', label: '2022-2024', start: '2022-01-01', end: '2024-12-31' },
  { id: '2025-2026', label: '2025-2026', start: '2025-01-01', end: null },
  { id: 'all', label: 'All (2021-now)', start: '2021-01-01', end: null },
  { id: 'custom', label: 'Custom date range…', start: null, end: null },
];
const WF_RATIOS = [1, 2, 3];
const WF_COMPARE = 'compare';
const WF_MODES = [...WF_RATIOS, WF_COMPARE];
const MONTHS_SHORT = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const MONTHS_LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September',
  'October', 'November', 'December'];
const DOW = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'];
const ET_DAY = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' });
function today() { return ET_DAY.format(new Date()); }
const preset = (id) => RANGES.find((r) => r.id === id) || RANGES[0];
/* A preset's own (start, end) — `end: null` resolves to today. 'custom' has neither. */
function rangeSpec(id) {
  const p = preset(id);
  return { start: p.start, end: p.start && p.end == null ? today() : p.end };
}
/* The dates a form's range actually runs over: its preset's, or the typed ones for Custom. */
function rangeDates(r) { return r && r.id === 'custom' ? { start: r.start || '', end: r.end || '' } : rangeSpec(r ? r.id : 'research'); }
const daysInMonth = (y, m) => new Date(Date.UTC(y, m, 0)).getUTCDate();
/* 'YYYY-MM-DD' back, but only for a real calendar date: 2026-02-30 and 2026-13-01 are not dates. */
function parseDate(text) {
  const t = String(text == null ? '' : text).trim();
  if (!ISO.test(t)) return null;
  const [y, m, d] = t.split('-').map(Number);
  return m >= 1 && m <= 12 && d >= 1 && d <= daysInMonth(y, m) ? t : null;
}
function dateError(text, what) {
  const t = String(text == null ? '' : text).trim();
  if (!t) return `${what}: a date, YYYY-MM-DD`;
  return parseDate(t) ? null : `${what}: "${t}" is not a date (YYYY-MM-DD)`;
}
function prettyDate(iso) {
  const d = parseDate(iso);
  if (!d) return '—';
  const [y, m, day] = d.split('-').map(Number);
  return `${MONTHS_SHORT[m - 1]} ${day}, ${y}`;
}
/* The pill's text: the preset's own name (or the custom dates), plus the walk-forward scheme when
   one is on -- "2021-2024 · WF 1:2". */
function pillLabel(r) {
  const base = !r || r.id !== 'custom' ? preset(r ? r.id : 'research').label
    : (parseDate(r.start) && parseDate(r.end) ? `${prettyDate(r.start)} — ${prettyDate(r.end)}` : 'Custom date range');
  if (r && r.wf === WF_COMPARE) return `${base} · WF compare`;
  return r && r.wf ? `${base} · WF 1:${r.wf}` : base;
}
const ymOf = (y, m) => `${y}-${String(m).padStart(2, '0')}`;
function shiftMonth(ym, delta) {
  const [y, m] = String(ym).split('-').map(Number);
  const k = (y * 12 + (m - 1)) + delta;
  return ymOf(Math.floor(k / 12), (k % 12) + 1);
}
/* One month of the Custom dialog's calendar: Sunday first, always 6 rows so the grid never jumps
   height between months. `outside` marks the leading/trailing days of the neighbouring months. */
function monthGrid(ym) {
  const [y, m] = String(ym).split('-').map(Number);
  const lead = new Date(Date.UTC(y, m - 1, 1)).getUTCDay(), weeks = [];
  for (let w = 0; w < 6; w++) {
    const row = [];
    for (let i = 0; i < 7; i++) {
      const d = new Date(Date.UTC(y, m - 1, 1 + w * 7 + i - lead)), iso = d.toISOString().slice(0, 10);
      row.push({ iso, day: d.getUTCDate(), outside: iso.slice(0, 7) !== ymOf(y, m) });
    }
    weeks.push(row);
  }
  return { ym: ymOf(y, m), label: `${MONTHS_LONG[m - 1]} ${y}`, dow: DOW, weeks };
}
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
    range: { id: 'research', start: '', end: '', wf: null }, qty: 1, commission: 4, slippage_ticks: 1,
    max_cells: DEFAULT_MAX_CELLS, prop_rules: DEFAULT_RULES };
}
/* A saved form for strategy s: its valid values over the defaults (anything unknown or invalid is dropped). */
function restore(saved, s) {
  const f = defaults(s);
  if (!saved || saved.strategy !== s.id) return f;
  for (const i of s.inputs) { const v = saved.inputs && saved.inputs[i.key]; if (v !== undefined && !inputError(i, v)) f.inputs[i.key] = v; }
  const r = saved.range || {};
  if (RANGES.some((x) => x.id === r.id)) {
    f.range = { id: r.id, start: ISO.test(r.start) ? r.start : '', end: ISO.test(r.end) ? r.end : '',
      wf: WF_MODES.includes(r.wf) ? r.wf : null };
  }
  for (const [k, , lo, hi, whole] of COSTS) { const v = saved[k]; if (typeof v === 'number' && v >= lo && v <= hi && (!whole || Number.isInteger(v))) f[k] = v; }
  if (!maxCellsError(saved.max_cells)) f.max_cells = saved.max_cells;
  if (typeof saved.prop_rules === 'string') f.prop_rules = saved.prop_rules;
  return f;
}
/* A finished run's own range back onto a picker preset: the fixed window whose dates it matches,
   else Custom with those dates. A loaded run is always a single run, so never a walk-forward. */
function rangeFromRun(rng) {
  if (!rng) return { id: 'research', start: '', end: '' };
  if (rng.kind === 'research') return { id: 'research', start: '', end: '' };
  const hit = RANGES.find((x) => x.id !== 'custom' && x.start === rng.start && rangeSpec(x.id).end === rng.end);
  return hit ? { id: hit.id, start: '', end: '' } : { id: 'custom', start: rng.start || '', end: rng.end || '' };
}
function fromRun(run, s) {
  return restore({ strategy: run.strategy.id, inputs: run.inputs, range: rangeFromRun(run.range),
    qty: run.qty, commission: run.commission, slippage_ticks: run.slippage_ticks,
    max_cells: run.max_cells, prop_rules: run.prop_rules }, s);
}
const isWalkforward = (f) => !!(f && f.range && f.range.wf);
const isWfCompare = (f) => !!(f && f.range && f.range.wf === WF_COMPARE);
function problems(f, s) {
  for (const i of s.inputs) { const e = inputError(i, f.inputs[i.key]); if (e) return e; }
  for (const [k, label, lo, hi, whole] of COSTS) {
    const v = f[k];
    if (typeof v !== 'number' || !Number.isFinite(v) || v < lo || v > hi || (whole && !Number.isInteger(v))) return `${label}: ${lo} to ${hi}`;
  }
  const r = f.range;
  if (r.id === 'custom') {
    const e = dateError(r.start, 'Start date') || dateError(r.end, 'End date');
    if (e) return e;
  }
  const { start, end } = rangeDates(r);
  if (start && end && start > end) return 'The start date is after the end date';
  return null;
}
/* The server's own range shape. The default preset stays `{kind: 'research'}` verbatim, so a
   2021-2024 request is byte for byte the one this tester always sent. */
function rangeBody(r) {
  if (!r || r.id === 'research') return { kind: 'research' };
  const { start, end } = rangeDates(r);
  return { kind: 'custom', start, end };
}
/* The POST /api/tester/run body. */
function body(f) {
  return { strategy: f.strategy, inputs: { ...f.inputs }, range: rangeBody(f.range), qty: f.qty, commission: f.commission,
    slippage_ticks: f.slippage_ticks, prop_rules: f.prop_rules };
}
const key = (f) => JSON.stringify(body(f));
function runLabel(f, loadedKey) { return loadedKey && key(f) !== loadedKey ? 'Update report' : 'Run'; }

function progress(st) {
  const s = st && st.status;
  if (s === 'queued') return { text: st.paused ? `Queued · ${st.paused}` : 'Queued…', frac: null, final: false };
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

/* The Eval picker's options: one per ruleset the server offers, `selected` marking the one in
   force. A run made under a SUPERSEDED snapshot (still loadable, no longer offered) keeps its own
   id as a trailing option, so switching away from it is deliberate rather than silent. */
function evalOptions(list, selected) {
  const out = (list || []).map((r) => ({ id: r.id, label: r.name + (r.confirmed === false ? ' · unconfirmed' : ''),
    unconfirmed: r.confirmed === false, selected: r.id === selected }));
  if (selected && !out.some((o) => o.selected)) out.push({ id: selected, label: selected, unconfirmed: false, selected: true });
  return out;
}

/* Which prop-eval block the Overview shows. `saved` is the run's own propsim.json (scored under
   `ranUnder`); `rs` is the last re-score request {runId, rulesId, loading, error, result}. A re-score
   applies only to the run it was asked for, and only when it names a different eval than the saved
   one. While it is in flight the saved numbers stay up — their header still names their own eval. */
function propShown(saved, ranUnder, rs, runId) {
  const base = { propsim: saved, rulesId: ranUnder, loading: false, error: '', rescored: false };
  if (!rs || rs.runId !== runId || !rs.rulesId || rs.rulesId === ranUnder) return base;
  if (rs.error) return { ...base, error: rs.error };
  if (rs.loading) return { ...base, rulesId: rs.rulesId, loading: true };
  if (rs.result) return { propsim: rs.result, rulesId: rs.rulesId, loading: false, error: '', rescored: true };
  return base;
}

/* ---- Monte Carlo (Overview sub-tab): resamples the run's own DAYS (their trades intact), never the fills ---- */
/* "the backtest's actual path: DD −$X, worse than P% of day reshuffles" -- P = the share of resampled
   paths whose drawdown was strictly less bad (review M2: a high P = an unlucky recorded path). */
function mcHeadline(r) {
  const what = r.mode === 'bootstrap' ? 'day resamples' : 'day reshuffles';
  return `the backtest's actual path: DD ${Tr.money(r.actual.max_dd)}, worse than ${Math.round(r.actual.worse_than_pct)}% of ${what}`;
}
function mcTiles(r) {
  const dd = r.drawdown, fn = r.final_net, ls = r.losing_streak;
  const spread = (m, fmt) => `p5 ${fmt(m.p5)} · p95 ${fmt(m.p95)}`;
  return [
    { label: 'Max drawdown (p50)', value: Tr.money(dd.p50), sub: spread(dd, Tr.money), tone: '' },
    { label: 'Final net (p50)', value: signed(fn.p50), sub: spread(fn, signed), tone: toneOf(fn.p50) },
    { label: 'Losing streak (p50)', value: int(Math.round(ls.p50)), sub: spread(ls, (v) => int(Math.round(v))), tone: '' },
    { label: `P(DD ≥ ${Tr.money(r.floor)})`, value: rate(r.p_ruin * 100), sub: 'ruin floor', tone: '' },
    { label: 'P(prop pass)', value: r.p_prop_pass == null ? '—' : rate(r.p_prop_pass * 100),
      sub: r.prop_rules ? r.prop_rules.label : '', tone: '' },
    { label: 'Paths', value: int(r.paths), sub: `${r.capped ? `capped from ${int(r.paths_requested)} · ` : ''}resampled by day`, tone: '' }];
}
/* Bar heights as a % of the tallest bin (>= 2% so a lone path never disappears); `title` carries
   the bin's own $ range + path count for a hover tooltip -- the chart itself stays a plain <div> row. */
function mcHistogram(r) {
  const { edges, counts } = r.histogram, max = Math.max(1, ...counts);
  return counts.map((c, i) => ({
    pct: Math.max(2, Math.round((c / max) * 100)),
    title: `${Tr.money(edges[i])} to ${Tr.money(edges[i + 1])}: ${c} path${c === 1 ? '' : 's'}`,
  }));
}

/* ---- Compare two runs (Compare sub-tab): diff table + params diff, both pure ---- */
const SIGNCH = (v) => (v > 0 ? '+' : v < 0 ? MINUS : '');
/* signed() and money() already carry their own sign; a delta needs one too even where the metric's
   own formatter (num/rate/int) doesn't, so a +0.3 Sharpe or a +2 trade delta still reads as a gain. */
function numDelta(v, d = 2) { return v == null || !Number.isFinite(v) ? '—' : SIGNCH(v) + Math.abs(v).toFixed(d); }
function rateDelta(v) { return v == null || !Number.isFinite(v) ? '—' : SIGNCH(v) + Math.abs(v).toFixed(1) + '%'; }
function intDelta(v) { return v == null || !Number.isFinite(v) ? '—' : SIGNCH(v) + int(Math.round(Math.abs(v))); }
/* [key, label, getter(summary.all), format, deltaFormat, higherIsBetter|null]. maxDD is <= 0, so
   "higher" (closer to zero) already reads as the less-bad side -- no special-casing needed. `null`
   (trades) never highlights either side: more trades is not inherently better. */
const CMP_ROWS = [
  ['net', 'Net profit', (c) => c.net_profit, signed, (v) => signed(v), true],
  ['pf', 'Profit factor', (c) => c.profit_factor, (v) => num(v, 2, true), (v) => numDelta(v, 2), true],
  ['wr', 'Win rate', (c) => c.win_rate, rate, rateDelta, true],
  ['sharpe', 'Sharpe', (c) => c.sharpe, (v) => num(v), (v) => numDelta(v), true],
  ['maxdd', 'Max drawdown', (c) => c.max_drawdown, (v) => Tr.money(v), (v) => signed(v), true],
  ['avg', 'Avg trade', (c) => c.avg_trade, signed, (v) => signed(v), true],
  ['trades', 'Trades', (c) => c.trades, int, intDelta, null],
];
function greenYears(byYear) { return { n: (byYear || []).filter((y) => y.net > 0).length, total: (byYear || []).length }; }
function propPassOf(propsim) { return propsim && propsim.headline ? propsim.headline.eval_pass_p : null; }
/* 'a' | 'b' | null (a tie, a missing value, or a metric with no better side). */
function betterSide(av, bv, higherBetter) {
  if (higherBetter == null || av == null || bv == null || !Number.isFinite(av) || !Number.isFinite(bv) || av === bv) return null;
  return (higherBetter ? av > bv : av < bv) ? 'a' : 'b';
}
/* net, PF, WR, Sharpe, maxDD, avg trade, trades, green years and prop pass -- one row per metric,
   each {label, a, b, delta, better}. `a`/`b` are `run.report`; `propA`/`propB` are `run.propsim` (or
   null -- a run that never ran a prop eval reads "—", never a false 0%). */
function compareRows(a, b, propA, propB) {
  const ca = a.summary.all, cb = b.summary.all;
  const rows = CMP_ROWS.map(([key, label, get, fmt, fmtDelta, higherBetter]) => {
    const av = get(ca), bv = get(cb);
    // review M1: a profit factor at the no-loss cap (999) is "∞", not a number to subtract
    const capped = key === 'pf' && (av >= 999 || bv >= 999);
    const ok = !capped && av != null && bv != null && Number.isFinite(av) && Number.isFinite(bv);
    return { key, label, a: fmt(av), b: fmt(bv), delta: ok ? fmtDelta(bv - av) : '—', better: betterSide(av, bv, higherBetter) };
  });
  const ga = greenYears(a.by_year), gb = greenYears(b.by_year);
  rows.push({ key: 'green_years', label: 'Green years', a: `${ga.n}/${ga.total}`, b: `${gb.n}/${gb.total}`,
    delta: intDelta(gb.n - ga.n), better: betterSide(ga.n, gb.n, true) });
  const pa = propPassOf(propA), pb = propPassOf(propB);
  const propOk = pa != null && pb != null;
  rows.push({ key: 'prop_pass', label: 'Prop pass', a: pa == null ? '—' : rate(pa * 100), b: pb == null ? '—' : rate(pb * 100),
    delta: propOk ? rateDelta((pb - pa) * 100) : '—', better: betterSide(pa, pb, true) });
  return rows;
}
/* Every strategy input, qty/commission/slippage/capital/prop_rules/range that differs between the
   two runs -- [{label, a, b}], nothing when the two runs are identical on that field. A strategy
   switch itself is the first row rather than a wall of "unknown parameter" noise from comparing
   two unrelated input schemas key-for-key. */
function paramsDiff(a, b) {
  const out = [];
  if (a.strategy.id !== b.strategy.id) out.push({ label: 'Strategy', a: a.strategy.name, b: b.strategy.name });
  const keys = new Set([...Object.keys(a.inputs || {}), ...Object.keys(b.inputs || {})]);
  for (const k of [...keys].sort()) {
    const av = (a.inputs || {})[k], bv = (b.inputs || {})[k];
    if (JSON.stringify(av) !== JSON.stringify(bv)) out.push({ label: k, a: valueLabel(av), b: valueLabel(bv) });
  }
  const FIELDS = [['qty', 'Qty'], ['commission', 'Commission'], ['slippage_ticks', 'Slippage (ticks)'],
    ['capital', 'Capital'], ['prop_rules', 'Prop rules']];
  for (const [k, label] of FIELDS) if (a[k] !== b[k]) out.push({ label, a: String(a[k]), b: String(b[k]) });
  if (a.range.label !== b.range.label) out.push({ label: 'Range', a: a.range.label, b: b.range.label });
  return out;
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

/* ---- the parameter heat-map (over the range picker's own window) ---- */
const DEFAULT_MAX_CELLS = 60;      // the Max cells box's default; the viewer may raise it
const HARD_MAX_CELLS = 400;        // ... but never past here, and the server refuses 401 too
const GRID_WORKERS = 2;            // grid.py's pool: how many cells actually run at once
const RANGE_MSG = 'a range is start:end:step with start ≤ end and step > 0';
function maxCellsError(n) {
  return Number.isInteger(n) && n >= 1 && n <= HARD_MAX_CELLS ? null
    : `Max cells: a whole number 1 to ${HARD_MAX_CELLS}`;
}
/* Above the default the viewer is told what they are asking for, in the measured per-cell time
   when a finished grid has given us one (grid.py runs GRID_WORKERS cells at a time). */
function cellsWarning(n, secPerCell) {
  if (!(n > DEFAULT_MAX_CELLS)) return '';
  const each = Number.isFinite(secPerCell) && secPerCell > 0 ? secPerCell : null;
  return each ? `${n} cells ≈ ${dur((n * each) / GRID_WORKERS)} at ${dur(each)} a cell, ${GRID_WORKERS} at a time`
    : `${n} cells — above ${DEFAULT_MAX_CELLS} a grid can run for hours; only ${GRID_WORKERS} cells run at a time`;
}
/* from / to / steps -> `steps` evenly spaced values, each rounded to the parameter's own step
   (5, 20, 4 -> 5, 10, 15, 20; steps = 1 -> just `from`). Rounding can land two on the same value:
   the duplicate is dropped rather than refused, so a coarse step just yields fewer cells. */
function stepValues(from, to, steps, inp) {
  const lo = Number(from), hi = Number(to), k = Number(steps);
  if (String(from).trim() === '' || String(to).trim() === '' || ![lo, hi].every(Number.isFinite)) {
    return { error: `${inp.label}: from and to are numbers` };
  }
  if (!Number.isInteger(k) || k < 1 || k > HARD_MAX_CELLS) return { error: `${inp.label}: steps is a whole number 1 to ${HARD_MAX_CELLS}` };
  if (k > 1 && !(hi > lo)) return { error: `${inp.label}: to must be above from` };
  const q = Number.isFinite(inp.step) && inp.step > 0 ? inp.step : null, out = [];
  for (let i = 0; i < k; i++) {
    const raw = k === 1 ? lo : lo + (i * (hi - lo)) / (k - 1);
    const v = Number((q ? Math.round(raw / q) * q : raw).toFixed(6));
    if (!out.includes(v)) out.push(v);
  }
  for (const v of out) { const e = inputError(inp, v); if (e) return { error: e }; }
  return { values: out };
}
/* One axis row -> its values: the free-text list, or from/to/steps when the row is in that mode. */
function axisValues(row, inp, maxCells) {
  return row && row.mode === 'range' ? stepValues(row.from, row.to, row.steps, inp)
    : parseValues(row ? row.text : '', inp, maxCells);
}
const decimals = (x) => { const m = /\.(\d+)$/.exec(String(x)); return m ? m[1].length : 0; };
/* One axis's values from the text box: "5, 10, 15", "5:20:5" (inclusive), mixes of both; bools as on/off
   (true/false); a choice by name. {values} or {error}; every value passes inputError, none twice. */
function parseValues(text, inp, maxCells) {
  const cap = maxCellsError(maxCells) ? HARD_MAX_CELLS : maxCells;
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
      if ((b - a) / st + 1 > cap + 1e-9) return { error: `${inp.label}: more than ${cap} values` };
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
  if (out.length > cap) return { error: `${inp.label}: more than ${cap} values` };
  for (let j = 0; j < out.length; j++) {
    const e = inputError(inp, out[j]);
    if (e) return { error: e };
    if (out.indexOf(out[j]) !== j) return { error: `${inp.label}: ${valueLabel(out[j])} twice` };
  }
  return { values: out };
}
function valueLabel(v) { return typeof v === 'boolean' ? (v ? 'on' : 'off') : String(v); }
/* The axis rows [{key, mode, text | from/to/steps}] (key '' = unused) -> {axes: [{key, values}]} or {error}. */
function gridAxes(rows, s, maxCells) {
  // Rows and Columns are required; Panels is optional -- a role never shifts into an empty one's place
  if (!rows[0] || !rows[0].key || !rows[1] || !rows[1].key) return { error: 'Pick a parameter for Rows and Columns' };
  const used = rows.slice(0, 3).filter((r) => r.key);
  const axes = [];
  for (const r of used) {
    const inp = s.inputs.find((i) => i.key === r.key);
    if (!inp) return { error: `Unknown parameter ${r.key}` };
    if (axes.some((a) => a.key === r.key)) return { error: `${inp.label} is picked twice` };
    const p = axisValues(r, inp, maxCells);
    if (p.error) return { error: p.error };
    axes.push({ key: r.key, values: p.values });
  }
  return { axes };
}
const gridCount = (axes) => axes.reduce((n, a) => n * a.values.length, 1);
function gridProblems(f, s, rows) {
  const cap = f.max_cells;
  const capErr = maxCellsError(cap);
  if (capErr) return capErr;
  const g = gridAxes(rows, s, cap);
  if (g.error) return g.error;
  const n = gridCount(g.axes);
  if (n > cap) return `${n} cells: this grid is capped at ${cap} (raise Max cells, up to ${HARD_MAX_CELLS})`;
  const varied = new Set(g.axes.map((a) => a.key));
  for (const i of s.inputs) { if (!varied.has(i.key)) { const e = inputError(i, f.inputs[i.key]); if (e) return e; } }
  for (const [k, label, lo, hi, whole] of COSTS) {
    const v = f[k];
    if (typeof v !== 'number' || !Number.isFinite(v) || v < lo || v > hi || (whole && !Number.isInteger(v))) return `${label}: ${lo} to ${hi}`;
  }
  return null;
}
/* The POST /api/tester/grid body: the range picker's own window, and the viewer's cell cap. */
function gridBody(f, axes) {
  const varied = new Set(axes.map((a) => a.key));
  return { strategy: f.strategy, inputs: Object.fromEntries(Object.entries(f.inputs).filter(([k]) => !varied.has(k))),
    axes: axes.map((a) => ({ key: a.key, values: [...a.values] })), range: rangeBody(f.range),
    qty: f.qty, commission: f.commission, slippage_ticks: f.slippage_ticks,
    max_cells: f.max_cells, prop_rules: f.prop_rules };
}
function looksText(n) {
  n = Number.isFinite(n) ? n : 0;
  return `looks this strategy: ${n} — expect ~${Math.round(n / 20)} lucky cells at 5%`;
}
/* The looks line: a counter the server refused to read (a corrupt looks.json) is said so, never shown as 0. */
function looksLine(n, err) { return err ? `looks counter unreadable: ${err}` : looksText(n); }
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
  const frac = st && st.total ? st.done / st.total : null, pause = st && st.paused ? ` · ${st.paused}` : '';
  if (s === 'queued') return { text: `Queued · ${n}${pause}`, frac: null, final: false };
  if (s === 'running') return { text: `Running · ${n}${pause}`, frac, final: false };
  if (s === 'done') return { text: `Done · ${n}`, frac: 1, final: true };
  if (s === 'cancelled') return { text: `Cancelled · ${n}${st.error ? ' · ' + st.error : ''}`, frac, final: true };
  return { text: '', frac: null, final: false };
}

/* ---- the walk-forward: 1 month to select, the next N to test, stepping monthly, over the window the
   range picker names. It has no tab of its own: picking "Walk-forward 1:N" in the picker turns the
   Run button into a walk-forward over the chosen window, and the result lands in Overview /
   Performance summary / List of trades. (homebase/backtest/walkforward.py owns the scheme; these
   only shape its request and read its result.) ---- */
const WF_METRICS = [['net_profit', 'Net $'], ['sharpe', 'Sharpe'], ['profit_factor', 'Profit factor'], ['t_stat', 't-stat']];
const WF_MIN_TRADES_MAX = 1000;
const WF_NEEDS_GRID = 'Pick the parameters to search on the Heat-map tab first.';
/* test_months = the ratio's OOS side: "1:2" sends 2. It is part of the request, so it is part of
   the job's identity -- switching the ratio can never show the other one's result. */
function wfBody(f, axes, metric, minTrades) {
  if (f.range.wf === WF_COMPARE) return { ...gridBody(f, axes), metric, min_trades: minTrades, compare: true };
  return { ...gridBody(f, axes), metric, min_trades: minTrades, test_months: f.range.wf || 3 };
}
/* A job's mode as the pill spells it: its ratio N, or 'compare' -- what the pill must equal for its result to show. */
function wfModeOf(cfg) { return cfg && cfg.compare ? WF_COMPARE : (cfg ? cfg.test_months : null); }
function wfModeLabel(cfg) { return wfModeOf(cfg) === WF_COMPARE ? '1:1 · 1:2 · 1:3 compare' : `1:${cfg && cfg.test_months}`; }
function wfProblems(f, s, rows, minTrades) {
  if (!rows || !rows[0] || !rows[0].key || !rows[1] || !rows[1].key) return WF_NEEDS_GRID;
  const g = gridProblems(f, s, rows);
  if (g) return g;
  if (!Number.isInteger(minTrades) || minTrades < 1 || minTrades > WF_MIN_TRADES_MAX) return `Min trades: a whole number 1 to ${WF_MIN_TRADES_MAX}`;
  return null;
}
/* A compare needs one full 1:3 cycle. `sc` = GET /api/tester/walkforward-scheme?test_months=compare for the
   window the pill shows (an answer for another window is ignored: the server refuses it anyway). */
const WF_COMPARE_TOO_SHORT = 'Window too short to compare 1:1 · 1:2 · 1:3 (1:3 needs 1 selection month + 3 test months)';
function wfSchemeProblem(f, sc) {
  if (!isWfCompare(f) || !sc || !sc.compare || sc.runnable !== false) return null;
  const d = rangeDates(f.range), w = sc.window || {};
  return w.start === d.start && w.end === d.end ? WF_COMPARE_TOO_SHORT : null;
}
/* nSteps comes from GET /api/tester/walkforward-scheme (review M5); '' until it has loaded. */
/* `penalty` (a compare job): the ×3 for choosing a ratio off the table -- the picks themselves are one search. */
function wfLooksText(cells, nSteps, penalty = 1) {
  if (!Number.isInteger(nSteps)) return '';
  const pen = penalty > 1 ? ` × ${penalty} (choosing a ratio off the table)` : '';
  return `${int(cells)} cell${cells === 1 ? '' : 's'} × ${nSteps} selection months${pen} = ${int(cells * nSteps * penalty)} looks`;
}
function etaText(s) {
  if (s == null || !Number.isFinite(s)) return '';
  if (s < 60) return '<1 min left';
  const m = Math.round(s / 60);
  if (m < 60) return `~${m} min left`;
  const h = Math.floor(m / 60), r = m % 60;
  return r ? `~${h} h ${r} min left` : `~${h} h left`;
}
function wfProgress(st) {
  const s = st && st.status, n = `${int(st && st.done)} / ${int(st && st.total)} cells`, pause = st && st.paused ? ` · ${st.paused}` : '';
  if (st && st.lost) return { text: 'Lost contact · it keeps running on the server', frac: null, final: true };
  if (s === 'queued') return { text: `Queued · ${n}${pause}`, frac: null, final: false };
  if (s === 'running') {
    const p = Number.isFinite(st.progress) ? st.progress : null, eta = pause ? '' : etaText(st.eta_s);
    return { text: `Running · ${n}${p == null ? '' : ` · ${Math.round(p * 100)}%`}${eta ? ` · ${eta}` : ''}${pause}`, frac: p, final: false };
  }
  if (s === 'selecting') return { text: 'Selecting and stitching…', frac: null, final: false };
  if (s === 'done') return { text: `Done · ${int(st.total)} cells · ${int(st.looks_added)} looks counted`, frac: 1, final: true };
  if (s === 'cancelled') return { text: `Cancelled · ${n} · no looks counted${st.error ? ' · ' + st.error : ''}`, frac: null, final: true };
  if (s === 'error') return { text: `Failed · ${st.error || 'unknown error'}`, frac: null, final: true };
  return { text: '', frac: null, final: false };
}
const span = (a, b) => `${a} → ${b}`;
/* One row of tiles for either side of the stitched chain. `which` is 'oos' (the stitched out-of-sample)
   or 'is' (the selection months those picks were chosen on) -- the user's "and then OOS for each". The
   two sides span DIFFERENT month counts (1 per leg vs N per leg), so the headline is per MONTH, each side
   says how many months it covers, and the raw total is labelled as a total over that span. */
const months_ = (n) => `${int(n)} month${n === 1 ? '' : 's'}`;
function wfTiles(r, which = 'oos') {
  const side = which === 'is' ? r.stitched_is : r.stitched;
  const s = side.stats, m = side.months || [], n = side.n_months ?? m.length, pm = side.per_month || {};
  return [
    { label: 'Net / month', value: signed(pm.net_profit), sub: `${months_(n)}${m.length ? ' · ' + span(m[0], m[m.length - 1]) : ''}`,
      tone: toneOf(pm.net_profit) },
    { label: 'Trades / month', value: num(pm.trades, 1), sub: '', tone: '' },
    { label: 'Total net', value: signed(s.net_profit), sub: `over ${months_(n)}`, tone: toneOf(s.net_profit) },
    { label: 'Max drawdown', value: Tr.money(s.max_drawdown), sub: '', tone: toneOf(s.max_drawdown) },
    { label: 'Win rate', value: rate(s.win_rate), sub: '', tone: '' },
    { label: 'Profit factor', value: num(s.profit_factor, 2, true), sub: '', tone: '' },
    { label: 'Sharpe', value: num(s.sharpe), sub: 'weekday grid', tone: '' }];
}
const WF_SIDE_LABELS = { is: 'In-sample (selection)', oos: 'Out-of-sample' };
/* How far the edge fell between the two sides -- per MONTH in $ and %, and in Sharpe (already a rate).
   Never a difference of raw totals: at 1:3 those span 1 month against 3. */
function wfDrop(r) {
  const d = r.drop || {};
  const pp = (v, f) => (v == null || !Number.isFinite(v) ? '—' : (v > 0 ? '+' : v < 0 ? MINUS : '') + f(Math.abs(v)));
  const pct = d.pct == null || !Number.isFinite(d.pct) ? '' : ` (${pp(d.pct, (x) => `${Math.round(x)}%`)})`;
  return `In-sample → out-of-sample, per month: net ${pp(d.net_profit_per_month, (x) => Tr.money(x))}${pct}`
    + ` · Sharpe ${pp(d.sharpe, (x) => x.toFixed(2))}`;
}
/* The months the stitched chain never tests out-of-sample (its last leg did not fit the window). */
function wfUncovered(r) {
  const u = (r.stitched && r.stitched.uncovered) || [];
  return u.length ? `Not tested out-of-sample: ${u.join(', ')}` : '';
}
/* The step table's two header rows: the group spans, then the columns themselves. */
const WF_STEP_GROUPS = [['', 3], [WF_SIDE_LABELS.is, 3], [WF_SIDE_LABELS.oos, 6]];
const WF_STEP_HEADERS = ['Select', 'Test', 'Chosen params', 'Net', 'Trades', 'Sharpe',
  'Net', 'Trades', 'Win %', 'PF', 'Sharpe', 'Max DD'];
function paramsLabel(axes, params) { return axes.map((a) => `${a.label} ${valueLabel(params[a.key])}`).join(' · '); }
function wfStepRows(r, axes) {
  return r.steps.map((s) => {
    const head = [s.select, span(s.test[0], s.test[1])];
    if (s.cell == null) {
      return { cells: [...head, `no pick (no cell with ≥ ${r.scheme.min_trades} trades)`, ...Array(9).fill('—')],
        stitched: !!s.stitched, changed: s.changed, isTone: '', oosTone: '' };
    }
    const i = s.is, o = s.oos;
    return { cells: [...head, paramsLabel(axes, s.params), signed(i.net_profit), int(i.trades), num(i.sharpe),
      signed(o.net_profit), int(o.trades), rate(o.win_rate), num(o.profit_factor, 2, true), num(o.sharpe), Tr.money(o.max_drawdown)],
    stitched: !!s.stitched, changed: s.changed, isTone: toneOf(i.net_profit), oosTone: toneOf(o.net_profit) };
  });
}
function wfStability(r) {
  const s = r.stability, np = s.no_pick;
  return `Params changed ${int(s.changes)} of ${int(s.pairs)} consecutive picks · ${int(s.distinct)} distinct cell${s.distinct === 1 ? '' : 's'}`
    + ` · ${int(np)} month${np === 1 ? '' : 's'} with no pick`;
}
function wfPhases(r) {
  const rest = r.phases.filter((p) => p.phase > 0).map((p) => `phase ${p.phase} ${signed(p.net_profit)}`).join(' · ');
  return `Chain phase check (same picks, chain started 1 or 2 months later): ${rest}`;
}
function wfScheme(r) {
  const c = r.scheme, w = r.window || {};
  const win = w.start && w.end ? `${w.start} → ${w.end} · ` : '';
  return `${win}Walk-forward 1:${c.test_months} — select on ${c.select_months} month by ${c.metric_label} `
    + `(≥ ${c.min_trades} trades), test the next ${c.test_months}, stepping monthly · ${int(r.n_steps)} steps `
    + `· stitched: ${c.stitch}`;
}

/* ---- the walk-forward comparison: 1:1 · 1:2 · 1:3 from one grid run (GET .../walkforward/{id}/compare).
   Every number here is the STITCHED OUT-OF-SAMPLE chain of its scheme -- the summary carries nothing
   in-sample. One colour per scheme, shared by the column header and its equity line. */
const WF_COMPARE_EXTRA = '#9C27B0';     // a third line colour beside the palette's accent and warn
function wfCompareColors(P) { return [P.accent, P.warn, WF_COMPARE_EXTRA]; }
const WF_COMPARE_ROWS = [
  ['span', 'Out-of-sample span'], ['net', 'Net $'], ['net_phases', 'Net across start months (min – max · mean)'],
  ['net_month', 'Net / month'], ['trades', 'Trades'],
  ['win_rate', 'Win rate'], ['pf', 'Profit factor'], ['avg_trade', 'Avg trade $'], ['max_dd', 'Max drawdown $'],
  ['sharpe', 'Sharpe'], ['sharpe_phases', 'Sharpe across start months (min – max · mean)'], ['legs', 'Steps (stitched legs)'], ['legs_pct', '% of steps profitable'],
  ['selects', 'Selection months (first → last)'], ['uncovered', 'Not tested out-of-sample'],
  ['errors', 'Strategy-error sessions']];
/* A phase spread {min, max, mean, n}: the chains started 0 .. N-1 months later (1:1 has only one). */
function phaseSpreadText(sp, fmt, nPhases) {
  if (!sp) return '—';
  if (nPhases === 1) return `${fmt(sp.min)} (one chain)`;
  return `${fmt(sp.min)} – ${fmt(sp.max)} · mean ${fmt(sp.mean)}`;
}
function wfCompareCell(key, c) {
  const s = c.stats || {}, L = c.legs || {}, pm = c.per_month || {}, ps = c.phase_spread || {}, np = (c.phases || []).length;
  switch (key) {
    case 'net_phases': return { text: phaseSpreadText(ps.net_profit, signed, np), tone: '' };
    case 'sharpe_phases': return { text: phaseSpreadText(ps.sharpe, (v) => num(v), np), tone: '' };
    case 'span': return { text: c.span ? `${span(c.span[0], c.span[1])} · ${months_(c.n_months)}` : '—', tone: '' };
    case 'net': return { text: signed(s.net_profit), tone: toneOf(s.net_profit) };
    case 'net_month': return { text: signed(pm.net_profit), tone: toneOf(pm.net_profit) };
    case 'trades': return { text: int(s.trades), tone: '' };
    case 'win_rate': return { text: rate(s.win_rate), tone: '' };
    case 'pf': return { text: num(s.profit_factor, 2, true), tone: '' };
    case 'avg_trade': return { text: signed(s.avg_trade), tone: toneOf(s.avg_trade) };
    case 'max_dd': return { text: Tr.money(s.max_drawdown), tone: toneOf(s.max_drawdown) };
    case 'sharpe': return { text: num(s.sharpe), tone: '' };
    case 'legs': return { text: L.n == null ? '—' : `${int(L.n)}${L.no_pick ? ` (${int(L.no_pick)} no pick)` : ''}`, tone: '' };
    case 'legs_pct': return { text: L.pct_profitable == null ? '—' : `${rate(L.pct_profitable)} (${int(L.profitable)} of ${int(L.n)})`, tone: '' };
    case 'selects': return { text: L.first_select ? span(L.first_select, L.last_select) : '—', tone: '' };
    case 'errors': return { text: s.skipped_by_error == null ? '—' : int(s.skipped_by_error), tone: s.skipped_by_error > 0 ? 'down' : '' };
    case 'uncovered': return { text: (c.uncovered || []).length ? c.uncovered.join(', ') : '—', tone: '' };
    default: return { text: '—', tone: '' };
  }
}
/* Rows that only exist for the full spans: the phase chains, the selection months and the untested tail. */
const WF_FULL_ONLY = new Set(['net_phases', 'sharpe_phases', 'selects', 'uncovered']);
/* The side-by-side table: one column per scheme (header = its ratio), one row per metric. `view` 'shared' =
   every metric on the months all three chains test (the default: identical months per column); 'full' =
   each scheme's whole stitched chain (spans differ). */
function wfCompareTable(cmp, view = 'full') {
  const shared = view === 'shared';
  const cols = ((cmp && cmp.schemes) || []).map((c) => (shared ? { ...c, ...(c.shared || { stats: {}, legs: {}, per_month: {}, span: null }) } : c));
  return { head: cols.map((c) => ({ ratio: c.ratio, test_months: c.test_months,
    title: `Walk-forward ${c.ratio}: select on 1 month, hold the pick for ${c.test_months} — click to open its full result` })),
  rows: WF_COMPARE_ROWS.filter(([key]) => !shared || !WF_FULL_ONLY.has(key))
    .map(([key, label]) => ({ key, label, cells: cols.map((c) => wfCompareCell(key, c)) })) };
}
/* Like the 1:N overview's line: strategy-error sessions inside the stitched chains, per scheme. */
function wfCompareErrLine(cmp) {
  const bad = ((cmp && cmp.schemes) || []).filter((c) => (c.stats || {}).skipped_by_error > 0);
  if (!bad.length) return '';
  return 'Strategy-error sessions inside the stitched chains: '
    + bad.map((c) => `${c.ratio} ${int(c.stats.skipped_by_error)}`).join(' · ');
}
/* The shared block's caption: which months every column covers. */
function wfSharedCaption(cmp) {
  const sm = cmp && cmp.shared_months;
  if (!sm || !sm.span) return 'SHARED MONTHS · none — the three chains test no month in common';
  return `SHARED MONTHS · ${span(sm.span[0], sm.span[1])} · ${months_(sm.n)} every scheme tests out-of-sample — the default view`;
}
/* Said plainly when the start month of a chain moves its net more than switching the ratio does. */
function wfComparePhaseLine(cmp) {
  const pc = cmp && cmp.phase_check;
  if (!pc || !pc.warning) return '';
  return `Phase check: ${pc.warning} — the widest spread across start months is ${Tr.money(pc.widest_phase_spread)}, `
    + `the gap between the three headline nets ${Tr.money(pc.gap_between_schemes)}`;
}
function wfCompareHead(cmp) {
  const c = cmp.scheme || {}, w = cmp.window || {}, b = cmp.looks_basis;
  const win = w.start && w.end ? `${w.start} → ${w.end} · ` : '';
  return `${win}Walk-forward 1:1 · 1:2 · 1:3 — one grid run, select on ${c.select_months} month by ${c.metric_label} `
    + `(≥ ${c.min_trades} trades), stepping monthly · ${int(cmp.looks)} looks counted`
    + (b ? ` (${int(b.cells)} cells × ${int(b.select_months)} selection months × ${b.choice_penalty} for choosing a ratio)` : '');
}

/* A strategy's name in the picker: a DRAFT (~/.homebase/strategies, written by Claude or by hand) says so,
   and one that does not load says that too (the option is disabled; its error is the tooltip). */
function strategyLabel(s) {
  if (!s) return '';
  return s.draft ? `DRAFT · ${s.name || s.id}${s.error ? ' (does not load)' : ''}` : (s.name || s.id);
}
const api = { strategyLabel, DEFAULT_MAX_CELLS, HARD_MAX_CELLS, GRID_WORKERS, maxCellsError, cellsWarning, stepValues, axisValues,
  parseValues, valueLabel, gridAxes, gridCount, gridProblems, gridBody, looksText, looksLine, heatPanels, heatMaxAbs,
  WF_METRICS, WF_RATIOS, WF_COMPARE, WF_MODES, isWfCompare, wfModeOf, wfModeLabel, WF_COMPARE_ROWS, wfCompareColors,
  wfCompareCell, wfCompareTable, wfCompareHead, wfComparePhaseLine, wfSharedCaption, wfCompareErrLine, wfSchemeProblem, WF_COMPARE_TOO_SHORT, WF_STEP_HEADERS, WF_STEP_GROUPS, WF_SIDE_LABELS, WF_NEEDS_GRID, wfBody, wfProblems, wfLooksText,
  etaText, wfProgress, wfTiles, wfDrop, wfUncovered, wfStepRows, wfStability, wfPhases, wfScheme,
  heatLevel, cellView, gridProgress, RANGES, DEFAULT_RULES, defaults, restore, fromRun, rangeFromRun, isWalkforward,
  today, rangeSpec, rangeDates, rangeBody, parseDate, dateError, prettyDate, pillLabel, monthGrid, shiftMonth,
  problems, inputError, body,
  key, runLabel, progress, pct, rate, num, dur, fmtEt, tiles, badges, propView, evalOptions, propShown, mcHeadline, mcTiles, mcHistogram, compareRows, paramsDiff,
  summaryRows, periodRows, sortTrades, tradeCells, tradeMarks, equitySeries, reachSpec, toneOf };
if (typeof window !== 'undefined') window.HBTester = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
