/* Homebase Charts — the Settings > Data (export) tab's pure logic: which controls a data type
   needs, the quick date-picks, building/validating the export request body, and turning a job's
   status into the progress bar's {text, frac} (tester.js's own `progress()` shape, reused here).
   Pure: no browser globals, no fetch -- settings-dialog.js owns the DOM and the host.export.*
   calls; this file only computes. Node tests load it directly (module.exports), same as
   settings.js/trade.js. */
(() => {
'use strict';

/* The full archive (futures_ticks/README.md's own list) -- a fallback for the first paint,
   before GET /api/export/schema answers; the reply is the source of truth after that. */
const ROOTS = ['NQ', 'ES', 'YM', 'RTY', 'GC', 'SI'];
const TIMEFRAMES = ['1s', '5s', '15s', '30s', '1m', '3m', '5m', '15m', '30m', '1h', '4h', '1D'];

/* One entry per Data Type option, in the order the select shows them. `columns` is the small
   caption under the select; `note` (candles/ticks/level1/level2) or `reason` (level3, disabled)
   is the provenance/limitation line the task asked to "say so" for. */
const TYPES = [
  { value: 'candles', label: 'Candles', needsTimeframe: true, needsContract: true,
    columns: 'time, open, high, low, close, volume' },
  { value: 'ticks', label: 'Ticks', needsContract: true,
    columns: 'time, price, size, bid, ask, bid_size, ask_size',
    note: 'bid/ask/sizes are only in desk recordings (2026-09-22 on) — blank before that.' },
  { value: 'level1', label: 'Level 1 (quotes)', needsContract: true,
    columns: 'time, bid, bid_size, ask, ask_size, last, last_size',
    note: 'Built from desk recordings only (2026-09-22 on). Nothing before that.' },
  { value: 'level2', label: 'Level 2 (order book)', needsLevels: true, depthOnly: true,
    columns: 'time, bid_px_1, bid_sz_1, … ask_px_N, ask_sz_N',
    note: 'NQ and ES only, recorded from about 2026-09-26.' },
  { value: 'level3', label: 'Level 3', disabled: true,
    reason: "Order-by-order data isn't in Tradovate's feed, so it isn't recorded." },
];
const TYPE_OF = Object.fromEntries(TYPES.map((t) => [t.value, t]));

/* Short labels: compact enough that all four fit on one line at the dialog's default width
   (full sentences wrapped, and at a fixed row height the wrapped line got covered by the row
   below -- reported with screenshots). The row still wraps cleanly (.tall) at narrower widths;
   this just makes wrapping the exception, not the default. */
const QUICK_PICKS = [['last5', '5 sessions'], ['month', 'This month'],
  ['3months', '3 months'], ['all', 'All']];

/* The 24/7 roots among the 15 (session.ALWAYS_OPEN, minus ETH/MET, which never appear in this
   export's own root list) -- "Last 5 sessions" counts weekends for these, not for the rest. */
const ALWAYS_247 = new Set(['BTC', 'MBT']);
function is247(root) { return ALWAYS_247.has(String(root || '').toUpperCase()); }

const iso = (d) => d.toISOString().slice(0, 10);
const dayMs = 86400000;

/* `today` back n SESSION days (weekdays only, unless always247) -- the same rule the export's
   own expected_sessions() (export.py) uses, so "Last 5 sessions" lines up with what the coverage
   check will call a session. Counts today itself as the first one when it qualifies. */
function backSessions(today, n, always247) {
  const d = new Date(today.getTime());
  let left = n;
  while (left > 0) {
    if (always247 || (d.getUTCDay() !== 0 && d.getUTCDay() !== 6)) left -= 1;
    if (left > 0) d.setTime(d.getTime() - dayMs);
  }
  return d;
}

/* today's date, `pick`'s {start, end} ('YYYY-MM-DD'). 'all' needs the market's own available
   range (avail: [start,end]|null from GET /api/export/meta) since there is no other bound. */
function quickRange(pick, today, always247, avail) {
  const end = iso(today);
  if (pick === 'last5') return { start: iso(backSessions(today, 5, always247)), end };
  if (pick === 'month') return { start: `${end.slice(0, 7)}-01`, end };
  if (pick === '3months') {
    const d = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth() - 2, 1));
    return { start: iso(d), end };
  }
  if (pick === 'all') return avail ? { start: avail[0], end: avail[1] } : { start: end, end };
  return null;
}

/* The export request body from the panel's field values, or {error}. Mirrors export.py's
   validate() closely enough to catch an empty/contradictory form before a round trip, but the
   server has the final say (contract existing, a level2 root, etc). */
function buildRequest(f) {
  if (!f.root) return { error: 'Pick a market' };
  const type = TYPE_OF[f.type];
  if (!type || type.disabled) return { error: 'Pick a data type' };
  if (!f.start || !f.end) return { error: 'Pick a date range' };
  if (f.start > f.end) return { error: 'From must not be after To' };
  if (type.needsTimeframe && !f.timeframe) return { error: 'Pick a timeframe' };
  const body = { root: f.root, type: f.type, contract: f.contract || 'front',
    start: f.start, end: f.end, hours: f.hours === 'rth' ? 'rth' : 'full',
    tz: f.tz === 'utc' ? 'utc' : 'et', ts_format: f.ts_format === 'epoch' ? 'epoch' : 'iso',
    format: f.format === 'gz' ? 'gz' : 'csv' };
  if (type.needsTimeframe) body.timeframe = f.timeframe;
  if (type.needsLevels) {
    const n = Math.round(Number(f.levels));
    if (!Number.isFinite(n) || n < 1 || n > 10) return { error: 'Levels: a whole number 1-10' };
    body.levels = n;
  }
  return { body };
}

/* The file name export.py's output_name() would pick -- a live preview, before the file exists. */
function previewName(body) {
  if (!body) return '';
  const bits = [body.root, body.type];
  if (body.type === 'candles' && body.timeframe) bits.push(body.timeframe);
  bits.push(body.start, body.end);
  return `${bits.join('_')}${body.format === 'gz' ? '.csv.gz' : '.csv'}`;
}

function fmtInt(n) { return Number(n || 0).toLocaleString('en-US'); }
function fmtBytes(n) {
  const v = Number(n) || 0;
  if (v < 1024) return `${v} B`;
  const units = ['KB', 'MB', 'GB'];
  let x = v / 1024, i = 0;
  while (x >= 1024 && i < units.length - 1) { x /= 1024; i += 1; }
  const s = x.toFixed(x < 10 ? 1 : 0);
  return `${s.endsWith('.0') ? s.slice(0, -2) : s} ${units[i]}`;
}

/* A job status (ExportManager.status's shape) -> the progress bar's {text, frac, final} --
   tester.js's own progress() shape, so the Data tab can reuse the SAME <progress class="tst-progress">
   + .tst-progress-text markup the Strategy Tester already draws with. */
function progress(st) {
  const s = st && st.status;
  if (!s) return { text: '', frac: null, final: false };
  if (s === 'queued') return { text: 'Queued…', frac: null, final: false };
  if (s === 'running') {
    const total = st.sessions_total || 0, done = st.sessions_done || 0;
    const where = total ? `${done} / ${total} sessions` : 'starting…';
    const rows = st.rows ? `, ${fmtInt(st.rows)} rows` : '';
    return { text: `Exporting · ${where}${rows}`, frac: total ? done / total : null, final: false };
  }
  if (s === 'error') return { text: `Failed: ${st.error || 'unknown error'}`, frac: null, final: true };
  if (s === 'cancelled') return { text: 'Cancelled', frac: null, final: true };
  if (s === 'done') return { text: `Done · ${fmtInt(st.rows)} rows`, frac: 1, final: true };
  return { text: '', frac: null, final: false };
}

/* The coverage warning line ("3 of 12 sessions missing"), or '' when nothing is missing / not
   checked yet. `cov` is GET /api/export/coverage's body ({sessions_total, missing, missing_hours}). */
function missingSummary(cov) {
  if (!cov || !cov.sessions_total) return '';
  const n = (cov.missing || []).length;
  if (!n) return '';
  return `${n} of ${cov.sessions_total} session${cov.sessions_total === 1 ? '' : 's'} missing (no file)`;
}

/* The KNOWN-gap line for sessions that DO have a file (a live recording's own gaps -- free, no
   tick decode): "2 known gaps within 1 session on disk", or '' when there are none / not checked. */
function gapsSummary(cov) {
  const mh = cov && cov.missing_hours;
  const dates = mh ? Object.keys(mh) : [];
  if (!dates.length) return '';
  const n = dates.reduce((sum, d) => sum + ((mh[d] && mh[d].length) || 0), 0);
  if (!n) return '';
  return `${n} known gap${n === 1 ? '' : 's'} within ${dates.length} session${dates.length === 1 ? '' : 's'} on disk`;
}

/* The "Refresh data" button's status (RefreshManager.status's shape, GET /api/refresh) -> {text, busy, tone}:
   the one line under the button, whether a run is going (the button is disabled and Cancel shows), and
   'err' for a failure. Pure; settings-dialog.js only paints it. */
function refreshView(st) {
  const s = st && st.status;
  if (!s || s === 'idle') return { text: '', busy: false, tone: '' };
  const steps = (st.steps || []).filter((x) => x.state !== 'skipped');
  if (s === 'running') {
    const at = Math.max(0, steps.findIndex((x) => x.key === st.step));
    const label = (steps[at] || {}).label || 'Starting';
    return { text: `Step ${at + 1} of ${steps.length || 1}: ${label}…`, busy: true, tone: '' };
  }
  if (s === 'cancelled') return { text: 'Cancelled', busy: false, tone: '' };
  if (s === 'error') return { text: `Failed: ${st.note || 'unknown error'}`, busy: false, tone: 'err' };
  const bits = [];
  const c = st.coverage;
  if (c && c.sessions) {
    bits.push(`${fmtInt(c.complete || 0)} of ${fmtInt(c.sessions)} recent sessions complete`);
    if (c.missing) bits.push(`${fmtInt(c.missing)} missing`);
    if (c.partial) bits.push(`${fmtInt(c.partial)} with holes`);
  } else bits.push('Done');
  const skipped = (st.steps || []).find((x) => x.state === 'skipped');
  return { text: bits.join(', ') + (skipped ? ` · ${skipped.label} skipped (${skipped.note})` : ''), busy: false, tone: '' };
}

const api = { ROOTS, TIMEFRAMES, TYPES, TYPE_OF, QUICK_PICKS, quickRange, backSessions, is247,
  buildRequest, previewName, fmtInt, fmtBytes, progress, missingSummary, gapsSummary, refreshView };
if (typeof window !== 'undefined') window.HBDataExport = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
