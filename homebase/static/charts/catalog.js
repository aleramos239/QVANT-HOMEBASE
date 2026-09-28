/* Homebase Charts — the indicator catalog and the page's pure helpers:
   indicator instances and their server study keys, migration of Build-1
   saved charts, legend and number formatting, interval labels. No DOM and
   no browser globals: the Node tests load this file directly. */
(function () {
'use strict';

const LINE_COLORS = ['#2962FF', '#FF6D00', '#9C27B0', '#00897B', '#E91E63'];
const ROOT_NAMES = { NQ: 'E-mini Nasdaq-100', ES: 'E-mini S&P 500', YM: 'E-mini Dow', RTY: 'E-mini Russell 2000',
  GC: 'Gold', SI: 'Silver', CL: 'Crude Oil', ZN: '10-Year T-Note', NG: 'Natural Gas', HG: 'Copper', BTC: 'Bitcoin' };
const ALWAYS_OPEN = new Set(['BTC', 'MBT', 'ETH', 'MET']);   // CME crypto: 24/7 since 2026-05-30
// The instrument badge (Task 1: legend + symbol search). No exchange or brand logos — these are our own
// text/shape designs; `icon` names a Lucide icon (icons.js) instead of text where one reads better (CL, NG).
const ROOT_BADGES = {
  NQ: { text: '100', bg: '#0b1f4d', fg: '#fff' }, ES: { text: '500', bg: '#b3261e', fg: '#fff' },
  YM: { text: '30', bg: '#1f3a93', fg: '#fff' }, RTY: { text: '2K', bg: '#6a1b9a', fg: '#fff' },
  GC: { text: 'Au', bg: '#c9a227', fg: '#1b1b1b' }, SI: { text: 'Ag', bg: '#9ea7ad', fg: '#1b1b1b' },
  HG: { text: 'Cu', bg: '#b87333', fg: '#fff' }, CL: { icon: 'droplet', bg: '#1b1b1b', fg: '#fff' },
  NG: { icon: 'flame', bg: '#1565c0', fg: '#fff' }, ZN: { text: '10Y', bg: '#2e7d32', fg: '#fff' },
  BTC: { text: '₿', bg: '#f7931a', fg: '#fff' },
};
const BADGE_FALLBACK = { bg: '#5d6b7a', fg: '#fff' };

/* CME Globex classic hours: Sunday 18:00 to Friday 17:00 with a daily
   17:00-18:00 break. Exchange holidays are not modelled. Factored out of
   marketOpen so the 24/7-root staleness rule (staleAfter) can ask "is the
   classic market open right now" without the ALWAYS_OPEN shortcut. */
function classicOpen(weekday, minutes) {
  if (weekday === 6) return false;
  if (weekday === 0) return minutes >= 18 * 60;
  if (minutes >= 17 * 60 && minutes < 18 * 60) return false;
  if (weekday === 5) return minutes < 17 * 60;
  return true;
}

/* Is root's market open at this ET weekday (0 = Sunday) and minute of the
   day? Crypto never closes; every other root follows classicOpen. */
function marketOpen(root, weekday, minutes) {
  return ALWAYS_OPEN.has(root) || classicOpen(weekday, minutes);
}
const GROUPS = ['All', 'VWAP', 'Moving averages', 'Trend', 'Levels', 'Volume', 'Order flow'];
const LENGTH = (def) => ({ key: 'length', label: 'Length', type: 'int', min: 1, max: 1000, def });
// SMA/EMA (studies.py SOURCES): "sma:50"/"ema:20" keep meaning close -- the source param defaults to it.
const SOURCES = [['close', 'Close'], ['open', 'Open'], ['high', 'High'], ['low', 'Low'],
  ['hl2', 'HL2'], ['hlc3', 'HLC3'], ['ohlc4', 'OHLC4']];
const SOURCE = { key: 'source', label: 'Source', type: 'choice', choices: SOURCES, def: 'close' };
const BAND = (n, def) => [
  { key: `band${n}On`, label: `Band ${n}`, type: 'bool', def: false },
  { key: `band${n}Mult`, label: `Band ${n} multiplier`, type: 'num', min: 0.1, max: 10, step: 0.1, def }];
const CATALOG = [
  { id: 'volume', group: 'Volume', name: 'Volume', params: [], pane: 'main' },
  { id: 'vwap', group: 'VWAP', name: 'VWAP', params: [
    { key: 'anchor', label: 'Anchor', type: 'choice',
      choices: [['eth', 'Session'], ['rth', 'RTH'], ['custom', 'Custom time'], ['week', 'Week'], ['month', 'Month']], def: 'eth' },
    { key: 'customTime', label: 'Time (ET)', type: 'time', def: '02:00' },
    ...BAND(1, 1), ...BAND(2, 2), ...BAND(3, 3)] },
  { id: 'ema', group: 'Moving averages', name: 'EMA', params: [LENGTH(20), SOURCE] },
  { id: 'sma', group: 'Moving averages', name: 'SMA', params: [LENGTH(50), SOURCE] },
  { id: 'vwma', group: 'Moving averages', name: 'VWMA', params: [LENGTH(20)] },
  { id: 'adx', group: 'Trend', name: 'ADX / DMI', params: [LENGTH(14)], pane: 'own' },
  { id: 'levels', group: 'Levels', name: 'Session levels', params: [] },
  { id: 'footprint', group: 'Order flow', name: 'Footprint', params: [
    { key: 'imbalance', label: 'Imbalance ratio', type: 'num', min: 0, max: 20, step: 0.5, def: 3 }] },
  { id: 'profile', group: 'Order flow', name: 'Volume profile', params: [] },
  { id: 'delta', group: 'Order flow', name: 'Delta', params: [], pane: 'own' },
  { id: 'cumdelta', group: 'Order flow', name: 'Cumulative delta', params: [], pane: 'own' },
  { id: 'bigprints', group: 'Order flow', name: 'Big prints', params: [
    { key: 'min', label: 'Minimum size', type: 'int', min: 1, max: 100000, def: 25 }] },
  { id: 'bigorders', group: 'Order flow', name: 'Big orders', params: [
    { key: 'multiple', label: 'Multiple', type: 'num', min: 1, max: 50, step: 0.5, def: 5 }] },
  { id: 'imbalance', group: 'Order flow', name: 'Imbalance', params: [] },
  { id: 'heatmap', group: 'Order flow', name: 'Liquidity heatmap', params: [] },
];
const BY_ID = Object.fromEntries(CATALOG.map((d) => [d.id, d]));
const FAVOURITES = [['1m', 'time:60'], ['5m', 'time:300'], ['15m', 'time:900'], ['1h', 'time:3600'], ['4h', 'time:14400'], ['D', 'time:86400']];
const INTERVAL_GROUPS = [
  ['Seconds', ['time:5', 'time:15', 'time:30']],
  ['Minutes', ['time:60', 'time:120', 'time:180', 'time:300', 'time:600', 'time:900', 'time:1800']],
  ['Hours', ['time:3600', 'time:14400']],
  ['Days', ['time:86400']],
  ['Ticks', ['tick:500', 'tick:1000']],
  ['Volume', ['volume:2000']],
  ['Range', ['range:10', 'range:20']],
];
// Build 1's per-chart study defaults: a saved `st` is read on top of these.
const ST0 = { vwap: true, vwapAnchor: 'eth', vwapBands: false, ema1: 0, ema2: 0, sma: 0, vwma: 0, levels: true,
  volume: true, delta: false, cumdelta: false, adx: 0, footprint: true, imbalance: 3, profile: false, bigMin: 0 };
const UNITS = [[86400, 'D', 'day'], [3600, 'h', 'hour'], [60, 'm', 'minute'], [1, 's', 'second']];
// Stale thresholds (2026-09-23 tick study, 10 roots): RTH should never go
// quiet this long; ETH is looser because thin overnight roots (ZN, NG) idle
// past 30 s routinely; 24/7 roots are looser still and measured only against
// the classic market they share md capacity with — see staleAfter/sinceOpen
// above feedSummary.
const RTH_STALE_S = 120;
const ETH_STALE_S = 300;
const CRYPTO_STALE_S = 900;
const REC_BUSY = 5000;    // the recorder's buffer this full turns the status amber

let seq = 0;
function uid() { return 'i' + Date.now().toString(36) + (seq++).toString(36) + Math.random().toString(36).slice(2, 6); }

function def(id) { return BY_ID[id] || null; }

/* Where an indicator that can live in its own pane is drawn (spec §7): 'own' = a pane of its own below the price
   pane, 'main' = on the price pane (an overlay at the bottom, out of the price autoscale). A catalog def's `pane`
   is its default, i.e. where it was drawn before placements existed; the price-pane-only ones (VWAP, MAs,
   levels, footprint, profile, big prints) have none and never move. */
const PANES = ['main', 'own'];
function movable(id) { const d = def(id); return !!(d && d.pane); }
function placement(inst) {
  const d = inst && def(inst.id);
  if (!d || !d.pane) return null;
  return PANES.includes(inst.pane) ? inst.pane : d.pane;
}

const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;

function clampParams(id, params) {
  const d = def(id), src = params && typeof params === 'object' ? params : {}, out = {};
  if (!d) return out;
  for (const p of d.params) {
    const v = src[p.key];
    if (p.type === 'bool') out[p.key] = typeof v === 'boolean' ? v : p.def;
    else if (p.type === 'choice') out[p.key] = p.choices.some(([c]) => c === v) ? v : p.def;
    else if (p.type === 'time') out[p.key] = typeof v === 'string' && HHMM.test(v) ? v : p.def;
    else {
      let n = v === null || v === '' || typeof v === 'boolean' ? NaN : Number(v);
      if (!Number.isFinite(n)) n = p.def;
      if (p.type === 'int') n = Math.round(n);
      out[p.key] = Math.min(p.max, Math.max(p.min, n));
    }
  }
  return out;
}

/* A fresh instance of `id`: a new uid, clamped params, and — for a pane-type indicator — its placement. `extra`
   (a stored indicator, e.g. from a chart template, spec §8) carries `visible` and `pane` over; anything it
   leaves out, or a pane that cannot move, takes today's default. No `style` here: an instance from this path
   (defaults(), a template, migrate()'s Build-1 path) keeps rendering through cell.js's legacy hardcoded
   palette unless a `style` was explicitly restored — see migrate()'s modern-format branch and the Indicators
   dialog's addIndicator(), which is the one path that attaches a fresh style (Task 2/3: a new instance of an
   indicator already on the chart must not repeat its colour). */
function instance(id, params, extra) {
  const d = def(id);
  if (!d) return null;
  const inst = { uid: uid(), id, params: clampParams(id, params), visible: !(extra && extra.visible === false) };
  if (d.pane) inst.pane = extra && PANES.includes(extra.pane) ? extra.pane : d.pane;
  return inst;
}

/* Every plotted-line key of `id`'s Style tab (cell.js's buildSeries case, in draw order), or null: an
   indicator with no per-line style (levels, footprint, profile, big prints, imbalance, heatmap, volume --
   canvas-drawn or a single fixed colour not worth a Style tab). */
const STYLE_LINES = { vwap: ['main', 'band1', 'band2', 'band3'], ema: ['main'], sma: ['main'], vwma: ['main'],
  adx: ['adx', 'pdi', 'mdi'], cumdelta: ['main'] };
// delta has no Style tab: it draws a per-bar up/down-coloured histogram, not a single line -- style-able
// the same way would need its own up/down fields, not this one-colour-per-key shape (spec: "unless trivial").
function styleLineKeys(id) { return STYLE_LINES[id] || null; }

const VWAP_DEFAULT = '#9C27B0';   // cell.js palette().vwap -- today's single-VWAP purple, kept as the first colour
const UP_DEFAULT = '#089981', DOWN_DEFAULT = '#F23645';   // palette().up/.down -- theme-independent
const DASH_STYLES = ['solid', 'dashed', 'dotted'];

/* The colour a FRESH instance of `id` gets, cycling so two instances of the same indicator never match: the
   first keeps the indicator's traditional single-instance colour (so an unremarkable single VWAP still looks
   like it always has), and each further one advances through LINE_COLORS. `siblings` is the indicator list
   BEFORE this new instance is added. */
function cycleColor(id, siblings) {
  const n = (siblings || []).filter((x) => x.id === id).length;
  const first = id === 'vwap' ? VWAP_DEFAULT : id === 'cumdelta' || id === 'delta' ? '#FF6D00' : LINE_COLORS[0];
  if (n === 0) return first;
  const rest = LINE_COLORS.filter((c) => c !== first);
  return rest[(n - 1) % rest.length];
}

function lineStyle(color, width, dash) { return { color, width, dash, visible: true }; }

/* A fresh per-line style {color, width (1-4), dash ('solid'|'dashed'|'dotted'), visible} for every line of a
   NEW instance of `id`, or null when `id` has no Style tab. `siblings`: see cycleColor. */
function defaultStyle(id, siblings) {
  const keys = styleLineKeys(id);
  if (!keys) return null;
  const color = cycleColor(id, siblings);
  switch (id) {
    case 'vwap': return { main: lineStyle(color, 2, 'solid'), band1: lineStyle(color, 1, 'dashed'),
      band2: lineStyle(color, 1, 'dashed'), band3: lineStyle(color, 1, 'dashed') };
    case 'adx': return { adx: lineStyle(color, 2, 'solid'), pdi: lineStyle(UP_DEFAULT, 1, 'solid'),
      mdi: lineStyle(DOWN_DEFAULT, 1, 'solid') };
    default: return { main: lineStyle(color, id === 'cumdelta' ? 2 : 1, 'solid') };   // ema, sma, vwma, delta, cumdelta
  }
}

function clampLineStyle(v, fallback) {
  const o = v && typeof v === 'object' ? v : {};
  return { color: typeof o.color === 'string' && /^#[0-9a-fA-F]{6}$/.test(o.color) ? o.color : fallback.color,
    width: [1, 2, 3, 4].includes(+o.width) ? +o.width : fallback.width,
    dash: DASH_STYLES.includes(o.dash) ? o.dash : fallback.dash,
    visible: typeof o.visible === 'boolean' ? o.visible : fallback.visible };
}

/* `style` (as persisted, or straight from the Style tab) clamped to `id`'s line keys, or null: no style tab,
   or nothing usable to clamp -- the caller then leaves the instance with no `style` field at all, so it keeps
   rendering through cell.js's legacy hardcoded palette exactly as it does today. */
function clampStyle(id, style) {
  const keys = styleLineKeys(id);
  if (!keys || !style || typeof style !== 'object') return null;
  const fallback = defaultStyle(id, []);
  const out = {};
  for (const k of keys) out[k] = clampLineStyle(style[k], fallback[k]);
  return out;
}

function defaults() { return [instance('volume'), instance('vwap'), instance('levels'), instance('footprint')]; }

/* The VWAP wire key (studies.py's VWAP anchor) for this instance's params: "vwap"/"vwap:rth" unchanged;
   "vwap:week"/"vwap:month"; "vwap:t0200" for a custom HH:MM ET (colon stripped -- wire keys use ':' as their
   own delimiter). An invalid/missing customTime never reaches here: clampParams already fell back to its
   default. */
function vwapServerKey(p) {
  switch (p.anchor) {
    case 'rth': return 'vwap:rth';
    case 'week': return 'vwap:week';
    case 'month': return 'vwap:month';
    case 'custom': return `vwap:t${(HHMM.test(p.customTime) ? p.customTime : '02:00').replace(':', '')}`;
    default: return 'vwap';
  }
}

function serverKey(inst) {
  const p = inst.params || {};
  switch (inst.id) {
    case 'vwap': return vwapServerKey(p);
    case 'ema': case 'sma': return `${inst.id}:${p.length}${p.source && p.source !== 'close' ? `:${p.source}` : ''}`;
    case 'vwma': case 'adx': return `${inst.id}:${p.length}`;
    case 'levels': case 'cumdelta': case 'profile': return inst.id;
    default: return null;
  }
}

function serverKeys(list) { return [...new Set((list || []).map(serverKey).filter(Boolean))]; }

/* A saved chart config of any vintage as {root, spec, indicators}. The spec is
   normalised as the server answers it (a Build-1 "tick:0750" is "tick:750"). */
function migrate(cfg) {
  const c = cfg && typeof cfg === 'object' ? cfg : {};
  const root = typeof c.root === 'string' && c.root ? c.root.toUpperCase() : 'NQ';
  const spec = toSpec(c.spec) || 'time:60';
  if (Array.isArray(c.indicators)) {
    const indicators = c.indicators.filter((x) => x && def(x.id)).map((x) => {
      const o = { uid: typeof x.uid === 'string' && x.uid ? x.uid : uid(), id: x.id,
        params: clampParams(x.id, x.params), visible: x.visible !== false };
      if (movable(x.id)) o.pane = placement(x);
      const st = clampStyle(x.id, x.style);   // absent/malformed: no `style` -- renders as it always has
      if (st) o.style = st;
      return o;
    });
    return { root, spec, indicators };
  }
  if (!c.st || typeof c.st !== 'object') return { root, spec, indicators: defaults() };
  const st = { ...ST0, ...c.st }, out = [];
  const add = (id, params) => out.push(instance(id, params));
  // Build-1's one "Bands (1σ and 2σ)" toggle becomes today's band 1 (×1) + band 2 (×2), both on.
  if (st.vwap) add('vwap', { anchor: st.vwapAnchor, band1On: !!st.vwapBands, band1Mult: 1, band2On: !!st.vwapBands, band2Mult: 2 });
  for (const f of ['ema1', 'ema2']) if (+st[f] > 0) add('ema', { length: +st[f] });
  if (+st.sma > 0) add('sma', { length: +st.sma });
  if (+st.vwma > 0) add('vwma', { length: +st.vwma });
  if (st.levels) add('levels');
  if (st.volume) add('volume');
  if (st.delta) add('delta');
  if (st.cumdelta) add('cumdelta');
  if (+st.adx > 0) add('adx', { length: +st.adx });
  if (st.footprint) add('footprint', { imbalance: +st.imbalance });
  if (st.profile) add('profile');
  if (+st.bigMin > 0) add('bigprints', { min: +st.bigMin });
  return { root, spec, indicators: out };
}

function migrateLayout(v) {
  const o = v && typeof v === 'object' ? v : {};
  return { grid: [1, 2, 4, 6].includes(+o.grid) ? +o.grid : 4, cells: (Array.isArray(o.cells) ? o.cells : []).map(migrate) };
}

function label(inst) {
  const d = def(inst.id), p = inst.params || {};
  if (!d) return String(inst.id);
  switch (inst.id) {
    case 'vwap':
      if (p.anchor === 'rth') return 'VWAP RTH';
      if (p.anchor === 'week') return 'VWAP W';
      if (p.anchor === 'month') return 'VWAP M';
      if (p.anchor === 'custom') return `VWAP ${HHMM.test(p.customTime) ? p.customTime : '02:00'}`;
      return 'VWAP';
    case 'ema': case 'sma':
      return p.source && p.source !== 'close' ? `${d.name} ${p.length} ${p.source.toUpperCase()}` : `${d.name} ${p.length}`;
    case 'vwma': return `${d.name} ${p.length}`;
    case 'adx': return `ADX ${p.length}`;
    case 'footprint': return p.imbalance > 0 ? `Footprint ${p.imbalance}×` : 'Footprint';
    case 'bigprints': return `Big prints ≥${p.min}`;
    case 'bigorders': return `Big orders ${p.multiple}×`;
    default: return d.name;
  }
}

function decimals(tick) {
  if (!(tick > 0)) return 2;
  for (let d = 0; d <= 6; d++) { const x = tick * 10 ** d; if (Math.abs(Math.round(x) - x) < 1e-9) return d; }
  return 6;
}

function fmtPrice(v, tick) {
  if (v == null || !Number.isFinite(v)) return '—';
  const d = decimals(tick);
  return v.toLocaleString('en-US', { minimumFractionDigits: d, maximumFractionDigits: d });
}

/* 950 · 1.23K · 4.56M (sign kept); inputs are whole contract counts. */
function fmtCompact(v) {
  if (v == null || !Number.isFinite(v)) return '—';
  const a = Math.abs(v), s = v < 0 ? '-' : '';
  if (a >= 999995) return s + (a / 1e6).toFixed(2) + 'M';
  if (a >= 999.5) return s + (a / 1e3).toFixed(2) + 'K';
  return s + Math.round(a);
}

function fmtSigned(v) {
  if (v == null || !Number.isFinite(v)) return '—';
  return (v > 0 ? '+' : '') + fmtCompact(v);
}

/* The bar's change against the previous bar's close (its own open for the first bar). */
function change(bar, prev, tick) {
  const base = prev ? prev.c : bar.o, diff = bar.c - base, pct = base ? diff / base * 100 : 0;
  const sign = diff > 0 ? '+' : diff < 0 ? '-' : '';
  return { up: diff >= 0, text: `${sign}${fmtPrice(Math.abs(diff), tick)} (${sign}${Math.abs(pct).toFixed(2)}%)` };
}

/* The values an indicator's legend row shows for one bar, each in its line colour. */
function legendValues(inst, bar, colors, tick) {
  const k = serverKey(inst), v = bar && bar.sv && k ? bar.sv[k] : null;
  const n2 = (x) => (x == null || !Number.isFinite(x) ? '—' : x.toFixed(2));
  switch (inst.id) {
    case 'ema': case 'sma': case 'vwma': return [{ text: fmtPrice(v, tick), color: colors.line }];
    case 'vwap': return [{ text: fmtPrice(v ? v.vwap : null, tick), color: colors.vwap }];
    case 'adx': return [{ text: n2(v && v.adx), color: colors.text }, { text: n2(v && v.pdi), color: colors.up },
      { text: n2(v && v.mdi), color: colors.down }];
    case 'cumdelta': return [{ text: fmtSigned(v), color: colors.cum }];
    default: return [];
  }
}

function parseSpec(spec) {
  const m = /^(time|tick|volume|range):(\d+)$/.exec(String(spec));
  return m && +m[2] > 0 ? { kind: m[1], n: +m[2] } : null;
}

function specLabel(spec) {
  const s = parseSpec(spec);
  if (!s) return String(spec);
  if (s.kind !== 'time') return `${s.n}${{ tick: 'T', volume: 'V', range: 'R' }[s.kind]}`;
  const [sec, unit] = UNITS.find(([u]) => s.n % u === 0);
  return `${s.n / sec}${unit}`;
}

function longLabel(spec) {
  const s = parseSpec(spec);
  if (!s) return String(spec);
  if (s.kind !== 'time') return `${s.n.toLocaleString('en-US')} ${{ tick: 'ticks', volume: 'volume', range: 'range' }[s.kind]}`;
  const [sec, , word] = UNITS.find(([u]) => s.n % u === 0), k = s.n / sec;
  return `${k} ${word}${k === 1 ? '' : 's'}`;
}

/* What the user typed in the custom-interval box as a bar spec, or null:
   "tick:750" as is, or shorthand 45s / 2m / 4h / 1D / 750T / 3000V / 8R. */
function toSpec(text) {
  const t = String(text == null ? '' : text).trim();
  let m = /^(time|tick|volume|range):(\d+)$/i.exec(t);
  if (m) return +m[2] > 0 ? `${m[1].toLowerCase()}:${+m[2]}` : null;
  m = /^(\d+)\s*([smhdtvr])$/i.exec(t);
  if (!m || +m[1] <= 0) return null;
  const n = +m[1], u = m[2].toLowerCase(), mult = { s: 1, m: 60, h: 3600, d: 86400 }[u];
  return mult ? `time:${n * mult}` : `${{ t: 'tick', v: 'volume', r: 'range' }[u]}:${n}`;
}

/* What the user typed in the timeframe-hotkey box (Task 1) as a bar spec, or null: a bare number is minutes
   ("5" = 5m); Ns/Nm/Nh are seconds/minutes/hours; d/D/1d is daily; w is weekly, but only while the catalog
   actually offers a weekly bar (it does not today, so "w" is unsupported and returns null). Distinct from
   toSpec (the interval menu's custom-spec box, which needs an explicit unit and also parses tick/volume/range
   shorthand): this is the narrower TradingView-style hotkey grammar. */
function parseInterval(text) {
  const t = String(text == null ? '' : text).trim();
  if (!t) return null;
  let m = /^(\d+)$/.exec(t);
  if (m) return +m[1] > 0 ? `time:${+m[1] * 60}` : null;
  m = /^(\d+)s$/i.exec(t);
  if (m) return +m[1] > 0 ? `time:${+m[1]}` : null;
  m = /^(\d+)m$/i.exec(t);
  if (m) return +m[1] > 0 ? `time:${+m[1] * 60}` : null;
  m = /^(\d+)h$/i.exec(t);
  if (m) return +m[1] > 0 ? `time:${+m[1] * 3600}` : null;
  if (/^1?d$/i.test(t)) return 'time:86400';
  if (/^w$/i.test(t)) {
    const week = 'time:604800';
    return INTERVAL_GROUPS.some(([, specs]) => specs.includes(week)) ? week : null;
  }
  return null;
}

/* The command-palette symbol search (Task 1 addition): every root of `roots` whose ROOT itself starts with
   `query` (case-insensitive), then every remaining root whose NAME starts with it. An empty query returns
   every root, unfiltered — the box's opening state before the seed letter narrows it. Pure and DOM-free so
   app.js's #tbSymbol menu and the hotkey box can share it. */
function matchSymbols(query, roots) {
  const q = String(query == null ? '' : query).trim().toUpperCase();
  const list = Array.isArray(roots) ? roots : [];
  if (!q) return list.slice();
  const byRoot = list.filter((r) => String(r).toUpperCase().startsWith(q));
  const byName = list.filter((r) => !byRoot.includes(r) && rootName(r).toUpperCase().startsWith(q));
  return [...byRoot, ...byName];
}

function rootName(root) { return ROOT_NAMES[root] || ''; }

/* The badge for `root`: {text?, icon?, bg, fg}. A micro root (an M prefix, e.g. MNQ, MES, MGC) uses its
   parent's badge; anything else unlisted falls back to its own first two letters. DOM-free — cell.js/app.js
   draw the circle. */
function rootBadge(root) {
  const r = String(root || '').toUpperCase();
  if (ROOT_BADGES[r]) return ROOT_BADGES[r];
  if (r.length > 1 && r[0] === 'M' && ROOT_BADGES[r.slice(1)]) return ROOT_BADGES[r.slice(1)];
  return { text: r.slice(0, 2), ...BADGE_FALLBACK };
}

/* An age in seconds as the bottom bar shows it: 12.3s · 4m · 2h · 3d. */
function fmtAge(a) {
  if (a == null) return '—';
  if (a < 60) return `${a.toFixed(1)}s`;
  if (a < 3600) return `${Math.round(a / 60)}m`;
  if (a < 86400) return `${Math.round(a / 3600)}h`;
  return `${Math.round(a / 86400)}d`;
}

/* Seconds without a tick before `root` counts as stale at this ET weekday /
   minute-of-day. Classic roots: RTH (Mon-Fri 09:30-16:00 ET) is tight, every
   other open hour (ETH) is looser. A 24/7 root (ALWAYS_OPEN) is looser
   still, and only while the classic Globex market it shares md capacity
   with is open — never stale across a weekend or the daily break, when a
   silent feed means nothing traded, not that the feed died. */
function staleAfter(root, weekday, minutes) {
  if (ALWAYS_OPEN.has(root)) return classicOpen(weekday, minutes) ? CRYPTO_STALE_S : Infinity;
  const rth = weekday >= 1 && weekday <= 5 && minutes >= 9 * 60 + 30 && minutes < 16 * 60;
  return rth ? RTH_STALE_S : ETH_STALE_S;
}

/* Seconds since the most recent 18:00 ET session reopen (the Sunday open, or
   a daily reopen after the 17:00-18:00 break). Clamping an age to this
   before comparing it with staleAfter means a market that just reopened is
   never flagged for ticks it could not have had while closed. */
function sinceOpen(minutes) { return ((minutes - 18 * 60 + 1440) % 1440) * 60; }

/* The bottom bar's feed summary for a status message, at this ET weekday
   (0 = Sunday) and minute of the day: the dot ('ok' | 'warn' | 'bad', or ''
   = grey: an open market has not ticked yet), a one-phrase text with its
   class ('' | 'warn' | 'bad') and the per-root tooltip. A closed market is
   never stale; a refused root is unavailable whatever the hours. Staleness
   itself is root- and session-aware — see staleAfter/sinceOpen. */
function feedSummary(s, weekday, minutes) {
  const roots = Object.entries(s.roots || {}), rec = s.recorder, recErr = rec && rec.error;
  const open = (r) => marketOpen(r, weekday, minutes), age = (x) => x.last_tick_age_s;
  const refused = roots.filter(([, x]) => x.error), live = roots.filter(([r, x]) => !x.error && open(r));
  const silent = live.filter(([, x]) => age(x) == null);
  const clamped = (x) => Math.min(age(x), sinceOpen(minutes));
  const stale = live.filter(([r, x]) => age(x) != null && clamped(x) > staleAfter(r, weekday, minutes))
    .sort((a, b) => age(b[1]) - age(a[1]));
  const title = roots.map(([r, x]) => `${r} ${x.error ? `unavailable: ${x.error}`
    : !open(r) ? 'closed' : age(x) == null ? 'no ticks yet' : fmtAge(age(x))}`).join('  ·  ');
  if (s.error || recErr) return { dot: 'bad', text: s.error || `recorder: ${recErr}`, textClass: 'bad', title };
  if (!s.connected) return { dot: 'bad', text: 'connecting…', textClass: '', title };
  const warn = refused.length > 0 || stale.length > 0;
  const text = [...refused.map(([r]) => `${r} unavailable`),
    ...stale.slice(0, 2).map(([r, x]) => `${r} stale ${fmtAge(age(x))}`),
    ...silent.slice(0, 2).map(([r]) => `${r} no ticks yet`)].join(' · ') || (roots.length ? 'feeds ok' : '');
  const dot = warn || (rec && rec.buffered >= REC_BUSY) ? 'warn' : silent.length ? '' : 'ok';
  return { dot, text, textClass: warn ? 'warn' : '', title };
}

function filter(query, group = 'All') {
  const q = String(query || '').trim().toLowerCase();
  return CATALOG.filter((d) => (group === 'All' || d.group === group)
    && (!q || d.name.toLowerCase().includes(q) || d.group.toLowerCase().includes(q) || d.id.includes(q)));
}

const api = { CATALOG, GROUPS, ROOT_NAMES, FAVOURITES, INTERVAL_GROUPS, LINE_COLORS, uid, def, clampParams, instance,
  defaults, serverKey, serverKeys, migrate, migrateLayout, label, legendValues, decimals, fmtPrice, fmtCompact,
  fmtSigned, change, parseSpec, specLabel, longLabel, toSpec, parseInterval, matchSymbols, rootName, rootBadge, filter,
  ALWAYS_OPEN, marketOpen, fmtAge, feedSummary, REC_BUSY, staleAfter, sinceOpen, PANES, movable, placement,
  styleLineKeys, defaultStyle, clampStyle, cycleColor };
if (typeof window !== 'undefined') window.HBCatalog = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
