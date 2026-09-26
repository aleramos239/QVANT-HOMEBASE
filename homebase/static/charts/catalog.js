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

/* Is root's market open at this ET weekday (0 = Sunday) and minute of the
   day? CME Globex: Sunday 18:00 to Friday 17:00 with a daily 17:00-18:00
   break; crypto never closes. Exchange holidays are not modelled. */
function marketOpen(root, weekday, minutes) {
  if (ALWAYS_OPEN.has(root)) return true;
  if (weekday === 6) return false;
  if (weekday === 0) return minutes >= 18 * 60;
  if (minutes >= 17 * 60 && minutes < 18 * 60) return false;
  if (weekday === 5) return minutes < 17 * 60;
  return true;
}
const GROUPS = ['All', 'VWAP', 'Moving averages', 'Trend', 'Levels', 'Volume', 'Order flow'];
const LENGTH = (def) => ({ key: 'length', label: 'Length', type: 'int', min: 1, max: 1000, def });
const CATALOG = [
  { id: 'volume', group: 'Volume', name: 'Volume', params: [] },
  { id: 'vwap', group: 'VWAP', name: 'VWAP', params: [
    { key: 'anchor', label: 'Anchor', type: 'choice', choices: [['eth', 'ETH'], ['rth', 'RTH']], def: 'eth' },
    { key: 'bands', label: 'Bands (1σ and 2σ)', type: 'bool', def: false }] },
  { id: 'ema', group: 'Moving averages', name: 'EMA', params: [LENGTH(20)] },
  { id: 'sma', group: 'Moving averages', name: 'SMA', params: [LENGTH(50)] },
  { id: 'vwma', group: 'Moving averages', name: 'VWMA', params: [LENGTH(20)] },
  { id: 'adx', group: 'Trend', name: 'ADX / DMI', params: [LENGTH(14)] },
  { id: 'levels', group: 'Levels', name: 'Session levels', params: [] },
  { id: 'footprint', group: 'Order flow', name: 'Footprint', params: [
    { key: 'imbalance', label: 'Imbalance ratio', type: 'num', min: 0, max: 20, step: 0.5, def: 3 }] },
  { id: 'profile', group: 'Order flow', name: 'Volume profile', params: [] },
  { id: 'delta', group: 'Order flow', name: 'Delta', params: [] },
  { id: 'cumdelta', group: 'Order flow', name: 'Cumulative delta', params: [] },
  { id: 'bigprints', group: 'Order flow', name: 'Big prints', params: [
    { key: 'min', label: 'Minimum size', type: 'int', min: 1, max: 100000, def: 25 }] },
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
const STALE_S = 30;       // an open market's symbol without a tick for this long is stale
const REC_BUSY = 5000;    // the recorder's buffer this full turns the status amber

let seq = 0;
function uid() { return 'i' + Date.now().toString(36) + (seq++).toString(36) + Math.random().toString(36).slice(2, 6); }

function def(id) { return BY_ID[id] || null; }

function clampParams(id, params) {
  const d = def(id), src = params && typeof params === 'object' ? params : {}, out = {};
  if (!d) return out;
  for (const p of d.params) {
    const v = src[p.key];
    if (p.type === 'bool') out[p.key] = typeof v === 'boolean' ? v : p.def;
    else if (p.type === 'choice') out[p.key] = p.choices.some(([c]) => c === v) ? v : p.def;
    else {
      let n = v === null || v === '' || typeof v === 'boolean' ? NaN : Number(v);
      if (!Number.isFinite(n)) n = p.def;
      if (p.type === 'int') n = Math.round(n);
      out[p.key] = Math.min(p.max, Math.max(p.min, n));
    }
  }
  return out;
}

function instance(id, params) {
  return def(id) ? { uid: uid(), id, params: clampParams(id, params), visible: true } : null;
}

function defaults() { return [instance('volume'), instance('vwap'), instance('levels'), instance('footprint')]; }

function serverKey(inst) {
  const p = inst.params || {};
  switch (inst.id) {
    case 'vwap': return p.anchor === 'rth' ? 'vwap:rth' : 'vwap';
    case 'ema': case 'sma': case 'vwma': case 'adx': return `${inst.id}:${p.length}`;
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
    const indicators = c.indicators.filter((x) => x && def(x.id)).map((x) => ({
      uid: typeof x.uid === 'string' && x.uid ? x.uid : uid(), id: x.id,
      params: clampParams(x.id, x.params), visible: x.visible !== false }));
    return { root, spec, indicators };
  }
  if (!c.st || typeof c.st !== 'object') return { root, spec, indicators: defaults() };
  const st = { ...ST0, ...c.st }, out = [];
  const add = (id, params) => out.push(instance(id, params));
  if (st.vwap) add('vwap', { anchor: st.vwapAnchor, bands: !!st.vwapBands });
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
    case 'vwap': return p.anchor === 'rth' ? 'VWAP RTH' : 'VWAP';
    case 'ema': case 'sma': case 'vwma': return `${d.name} ${p.length}`;
    case 'adx': return `ADX ${p.length}`;
    case 'footprint': return p.imbalance > 0 ? `Footprint ${p.imbalance}×` : 'Footprint';
    case 'bigprints': return `Big prints ≥${p.min}`;
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

function rootName(root) { return ROOT_NAMES[root] || ''; }

/* An age in seconds as the bottom bar shows it: 12.3s · 4m · 2h · 3d. */
function fmtAge(a) {
  if (a == null) return '—';
  if (a < 60) return `${a.toFixed(1)}s`;
  if (a < 3600) return `${Math.round(a / 60)}m`;
  if (a < 86400) return `${Math.round(a / 3600)}h`;
  return `${Math.round(a / 86400)}d`;
}

/* The bottom bar's feed summary for a status message, at this ET weekday
   (0 = Sunday) and minute of the day: the dot ('ok' | 'warn' | 'bad', or ''
   = grey: an open market has not ticked yet), a one-phrase text with its
   class ('' | 'warn' | 'bad') and the per-root tooltip. A closed market is
   never stale; a refused root is unavailable whatever the hours. */
function feedSummary(s, weekday, minutes) {
  const roots = Object.entries(s.roots || {}), rec = s.recorder, recErr = rec && rec.error;
  const open = (r) => marketOpen(r, weekday, minutes), age = (x) => x.last_tick_age_s;
  const refused = roots.filter(([, x]) => x.error), live = roots.filter(([r, x]) => !x.error && open(r));
  const silent = live.filter(([, x]) => age(x) == null);
  const stale = live.filter(([, x]) => age(x) != null && age(x) > STALE_S).sort((a, b) => age(b[1]) - age(a[1]));
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
  fmtSigned, change, parseSpec, specLabel, longLabel, toSpec, rootName, filter, ALWAYS_OPEN, marketOpen, fmtAge,
  feedSummary, REC_BUSY };
if (typeof window !== 'undefined') window.HBCatalog = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
