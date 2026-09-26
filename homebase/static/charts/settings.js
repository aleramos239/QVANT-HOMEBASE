/* Homebase Charts — the chart Settings model (TradingView's Settings dialog,
   for the parts that apply to our charts). Pure: every field with its
   default; normalize (unknown keys dropped, numbers clamped, colours and
   choices checked); the overrides a layout or a template stores (only what
   differs from the defaults); theme resolution (a colour never changed is
   null and follows the theme); the mappings to Lightweight Charts options;
   and the small helpers settings need (time zones, the regular-hours test,
   the bar countdown, the swatch palette, template names). No browser
   globals at load time: the Node tests load this file directly. */
(function () {
'use strict';
const Cat = (typeof window !== 'undefined' && window.HBCatalog) || (typeof require === 'function' ? require('./catalog.js') : null);

const LINE_STYLE = { solid: 0, dotted: 1, dashed: 2 };   // Lightweight Charts' LineStyle numbers
const STYLES = Object.keys(LINE_STYLE);
const CLEAR = 'rgba(0,0,0,0)';
/* [value, the dialog's text, IANA zone (null: the browser's own)] */
const TIMEZONES = [['exchange', 'Exchange (New York)', 'America/New_York'], ['utc', 'UTC', 'UTC'],
  ['chicago', 'Chicago', 'America/Chicago'], ['london', 'London', 'Europe/London'], ['local', 'Local', null]];
const ZONE = Object.fromEntries(TIMEZONES.map(([k, , z]) => [k, z]));

const bool = (key, def) => ({ key, type: 'bool', def });
const color = (key, def = null) => ({ key, type: 'color', def });
const int = (key, def, min, max) => ({ key, type: 'int', def, min, max });
const choice = (key, def, choices) => ({ key, type: 'choice', def, choices });
const FIELDS = [
  // Symbol · CANDLES
  bool('prevClose', false),
  bool('body', true), color('bodyUp'), color('bodyDown'),
  bool('borders', true), color('borderUp'), color('borderDown'),
  bool('wick', true), color('wickUp'), color('wickDown'),
  // Symbol · DATA
  { key: 'precision', type: 'precision', def: null },   // null: Default (from the tick size); else 0-6 decimals
  choice('timezone', 'exchange', TIMEZONES.map(([k]) => k)),
  bool('ethBg', false), color('ethBgColor', 'rgba(120,123,134,.08)'),
  // Status line
  bool('title', true), choice('titleMode', 'both', ['ticker', 'description', 'both']),
  bool('ohlc', true), bool('barChange', true), bool('volume', true),
  bool('indTitles', true), bool('indArgs', true), bool('indValues', true),
  // Scales and lines · PRICE SCALE
  bool('scalePriceOnly', false), bool('lastLabel', true), bool('lastLine', true), choice('lastLineStyle', 'dotted', STYLES),
  bool('countdown', true), int('marginTop', 10, 0, 40), int('marginBottom', 15, 0, 40),
  // Scales and lines · TIME SCALE
  int('rightOffset', 6, 0, 100),
  // Canvas · CHART BASIC STYLES
  color('bg'), bool('vertGrid', true), color('vertGridColor'), bool('horzGrid', true), color('horzGridColor'),
  color('crossColor'), choice('crossStyle', 'dashed', STYLES), int('crossWidth', 1, 1, 4),
  bool('watermark', true), color('watermarkColor'),
  // Canvas · SCALES
  color('scaleText'), int('scaleFont', 12, 10, 16), color('scaleLines'),
];
const DEFAULTS = Object.freeze(Object.fromEntries(FIELDS.map((f) => [f.key, f.def])));
/* The colours that follow the theme while never changed, and the HBCell.palette() key each takes. */
const THEMED = { bodyUp: 'up', bodyDown: 'down', borderUp: 'up', borderDown: 'down', wickUp: 'up', wickDown: 'down',
  bg: 'bg', vertGridColor: 'grid', horzGridColor: 'grid', crossColor: 'cross', watermarkColor: 'watermark',
  scaleText: 'text2', scaleLines: 'border' };

/* ---- colours ---- */
const HEX = /^#([0-9a-f]{6})$/i;
const RGBA = /^rgba\(\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d{1,3})\s*,\s*(\d*\.?\d+)\s*\)$/i;

/* '#RRGGBB' or 'rgba(r,g,b,a)' as {r, g, b, a}; null for anything else. */
function parseColor(s) {
  if (typeof s !== 'string') return null;
  const t = s.trim();
  let m = HEX.exec(t);
  if (m) { const n = parseInt(m[1], 16); return { r: n >> 16, g: (n >> 8) & 255, b: n & 255, a: 1 }; }
  m = RGBA.exec(t);
  if (!m) return null;
  const c = { r: +m[1], g: +m[2], b: +m[3], a: +m[4] };
  return c.r <= 255 && c.g <= 255 && c.b <= 255 && c.a <= 1 ? c : null;
}

/* A colour's one spelling: '#RRGGBB' when opaque, else 'rgba(r,g,b,.a)' (alpha to 3 places, no leading 0). */
function fmtColor(c) {
  const a = Math.round(Math.min(1, Math.max(0, c.a)) * 1000) / 1000;
  if (a === 1) return '#' + [c.r, c.g, c.b].map((x) => x.toString(16).padStart(2, '0')).join('').toUpperCase();
  return `rgba(${c.r},${c.g},${c.b},${String(a).replace(/^0\./, '.')})`;
}
const canon = (s) => { const c = parseColor(s); return c ? fmtColor(c) : null; };
/* The swatch popover's pieces: a colour's #RRGGBB, its opacity (0-1), and the same colour at another opacity. */
function hexOf(s) { const c = parseColor(s); return c ? fmtColor({ ...c, a: 1 }) : null; }
function alphaOf(s) { const c = parseColor(s); return c ? c.a : 1; }
function withAlpha(s, a) { const c = parseColor(s); return c ? fmtColor({ ...c, a }) : null; }

/* ---- the model ---- */
const num = (v) => (typeof v === 'number' ? v : typeof v === 'string' && v.trim() !== '' ? Number(v) : NaN);

/* Every field, each valid: unknown keys dropped, numbers rounded and clamped, colours checked (and spelled one
   way), choices checked; anything missing or invalid takes its default. */
function normalize(obj) {
  const src = obj && typeof obj === 'object' && !Array.isArray(obj) ? obj : {}, out = {};
  for (const f of FIELDS) {
    const v = src[f.key];
    let x = f.def;
    if (f.type === 'bool') { if (typeof v === 'boolean') x = v; }
    else if (f.type === 'choice') { if (f.choices.includes(v)) x = v; }
    else if (f.type === 'color') { const c = canon(v); if (c) x = c; }
    else if (v !== null) {
      const n = num(v);
      if (Number.isFinite(n)) {
        x = f.type === 'precision' ? Math.min(6, Math.max(0, Math.round(n))) : Math.min(f.max, Math.max(f.min, Math.round(n)));
      }
    }
    out[f.key] = x;
  }
  return out;
}

/* What a layout or a template stores: only the values that differ from the defaults. */
function overrides(full) {
  const n = normalize(full), out = {};
  for (const f of FIELDS) if (n[f.key] !== f.def) out[f.key] = n[f.key];
  return out;
}

/* Concrete values for a theme: every colour never changed takes the palette's (HBCell.palette()). */
function resolve(over, palette) {
  const n = normalize(over);
  for (const [k, pk] of Object.entries(THEMED)) if (n[k] == null) n[k] = palette[pk];
  return n;
}

/* ---- mappings to Lightweight Charts ---- */
/* Chart-wide options, merged into createChart / applyOptions. */
function chartOptions(r) {
  const cross = () => ({ color: r.crossColor, style: LINE_STYLE[r.crossStyle], width: r.crossWidth });
  return {
    layout: { background: { type: 'solid', color: r.bg }, textColor: r.scaleText, fontSize: r.scaleFont },
    grid: { vertLines: { visible: r.vertGrid, color: r.vertGridColor }, horzLines: { visible: r.horzGrid, color: r.horzGridColor } },
    crosshair: { vertLine: cross(), horzLine: cross() },
    timeScale: { rightOffset: r.rightOffset, borderColor: r.scaleLines },
    rightPriceScale: { borderColor: r.scaleLines },
  };
}

/* The candle series' options. Precision null: the tick size's decimals. */
function candleOptions(r, tick) {
  const p = r.precision;
  return {
    upColor: r.body ? r.bodyUp : CLEAR, downColor: r.body ? r.bodyDown : CLEAR,
    borderVisible: r.borders, borderUpColor: r.borderUp, borderDownColor: r.borderDown,
    wickVisible: r.wick, wickUpColor: r.wickUp, wickDownColor: r.wickDown,
    priceFormat: { type: 'price', precision: p == null ? Cat.decimals(tick) : p,
      minMove: p == null ? tick : Number((10 ** -p).toFixed(p)) },
    lastValueVisible: r.lastLabel, priceLineVisible: r.lastLine, priceLineStyle: LINE_STYLE[r.lastLineStyle],
  };
}

function scaleMargins(r) { return { top: r.marginTop / 100, bottom: r.marginBottom / 100 }; }

function legendFlags(r) {
  return { title: r.title, titleMode: r.titleMode, ohlc: r.ohlc, change: r.barChange, volume: r.volume,
    indTitles: r.indTitles, indArgs: r.indArgs, indValues: r.indValues };
}

/* One candle's colours with "Colour bars based on previous close": up when its close is at or above the
   previous bar's close (the first bar: its own open). */
function barColor(bar, prev, r) {
  const up = bar.c >= (prev ? prev.c : bar.o);
  return { color: r.body ? (up ? r.bodyUp : r.bodyDown) : CLEAR, borderColor: up ? r.borderUp : r.borderDown,
    wickColor: up ? r.wickUp : r.wickDown };
}
function barColorsByPrevClose(bars, r) { return bars.map((b, i) => barColor(b, i ? bars[i - 1] : null, r)); }

/* ---- legend texts ---- */
/* An indicator's legend label cut into its title and its arguments ("EMA 20" -> ["EMA", "20"]); an indicator
   without params has no arguments. */
function splitLabel(label, hasParams) {
  const i = hasParams ? label.lastIndexOf(' ') : -1;
  return i > 0 ? [label.slice(0, i), label.slice(i + 1)] : [label, ''];
}
function legendLabel(label, hasParams, flags) {
  const [t, a] = splitLabel(label, hasParams);
  return [flags.indTitles ? t : '', flags.indArgs ? a : ''].filter(Boolean).join(' ');
}
/* The legend's title row for the Status line's "Symbol title" choice. */
function titleText(root, name, interval, mode) {
  const parts = mode === 'ticker' ? [root, interval] : mode === 'description' ? [name || root, interval] : [root, name, interval];
  return parts.filter(Boolean).join(' · ');
}

/* ---- time ---- */
const FMT = new Map(), OFF = new Map();
/* A zone's UTC offset in ms at an instant (IANA name), cached per hour (these zones change offset on the hour). */
function zoneOffsetMs(zone, ms) {
  if (zone === 'UTC') return 0;
  const hour = Math.floor(ms / 3600000), key = zone + '|' + hour;
  let off = OFF.get(key);
  if (off === undefined) {
    let f = FMT.get(zone);
    if (!f) {
      f = new Intl.DateTimeFormat('en-US', { timeZone: zone, hourCycle: 'h23', year: 'numeric', month: 'numeric',
        day: 'numeric', hour: 'numeric', minute: 'numeric', second: 'numeric' });
      FMT.set(zone, f);
    }
    const p = {};
    for (const x of f.formatToParts(new Date(hour * 3600000))) p[x.type] = x.value;
    off = Date.UTC(+p.year, +p.month - 1, +p.day, +p.hour % 24, +p.minute, +p.second) - hour * 3600000;
    OFF.set(key, off);
  }
  return off;
}
/* An instant as wall-clock seconds in a chart time zone (a TIMEZONES value): the time axis runs on these. */
function wallSeconds(ms, tz) {
  const off = tz === 'local' ? -new Date(ms).getTimezoneOffset() * 60000 : zoneOffsetMs(ZONE[tz] || ZONE.exchange, ms);
  return Math.floor((ms + off) / 1000);
}
/* Is a bar starting at this ET wall-clock second outside regular hours (09:30-16:00 ET)? */
function outsideRth(etWallS) {
  const m = Math.floor((((etWallS % 86400) + 86400) % 86400) / 60);
  return m < 570 || m >= 960;
}
/* When a bar closes, as ET wall-clock ms: its start + its length, but never after its session's close (17:00
   ET; 18:00 for a 24/7 root), where the server closes a session's last bar. bar = {t: ET wall s, s: session}. */
function barCloseEt(bar, barMs, alwaysOpen) {
  const end = bar.t * 1000 + barMs, m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(bar.s || '');
  return m ? Math.min(end, Date.UTC(+m[1], +m[2] - 1, +m[3], alwaysOpen ? 18 : 17)) : end;
}
/* "04:59" under an hour, "1:04:59" from an hour. */
function fmtCountdown(ms) {
  const s = Math.max(0, Math.floor(ms / 1000)), h = Math.floor(s / 3600), p2 = (n) => String(n).padStart(2, '0');
  return h ? `${h}:${p2(Math.floor((s % 3600) / 60))}:${p2(s % 60)}` : `${p2(Math.floor(s / 60))}:${p2(s % 60)}`;
}

/* ---- templates ---- */
/* Why a template name is refused ('' when fine): 1-40 characters with no / \ .. or control characters (the
   server's rule), and not "." (the browser would resolve /api/templates/. as a path step). */
function templateNameError(name) {
  if (typeof name !== 'string' || name.length < 1 || name.length > 40) return 'A name has 1 to 40 characters';
  if (name === '.' || /[/\\]|\.\.|[\u0000-\u001f\u007f]/.test(name)) return 'A name has no / \\ .. or control characters';
  return '';
}

/* The swatch popover's palette: 10 hue columns (grey, red, orange, yellow, green, teal, cyan, blue, purple,
   pink) x 6 rows, light to dark, TradingView-like. */
const PALETTE = [
  ['#FFFFFF', '#FCCBCD', '#FFE0B2', '#FFF9C4', '#C8E6C9', '#ACE5DC', '#B2EBF2', '#BBD9FB', '#D1C4E9', '#F8BBD0'],
  ['#D6D6D6', '#FAA1A4', '#FFCC80', '#FFF59D', '#A5D6A7', '#70CCBD', '#80DEEA', '#90BFF9', '#B39DDB', '#F48FB1'],
  ['#A8A8A8', '#F77C80', '#FFB74D', '#FFF176', '#81C784', '#42BDA8', '#4DD0E1', '#5B9CF6', '#9575CD', '#F06292'],
  ['#757575', '#F23645', '#FF9800', '#FFEB3B', '#4CAF50', '#089981', '#00BCD4', '#2962FF', '#673AB7', '#E91E63'],
  ['#434343', '#B22833', '#F57C00', '#FBC02D', '#388E3C', '#056656', '#0097A7', '#1848CC', '#512DA8', '#C2185B'],
  ['#000000', '#801922', '#E65100', '#F57F17', '#1B5E20', '#00332A', '#006064', '#0C3299', '#311B92', '#880E4F'],
];

const api = { FIELDS, DEFAULTS, THEMED, LINE_STYLE, TIMEZONES, PALETTE, CLEAR, parseColor, fmtColor, hexOf, alphaOf,
  withAlpha, normalize, overrides, resolve, chartOptions, candleOptions, scaleMargins, legendFlags, barColor,
  barColorsByPrevClose, splitLabel, legendLabel, titleText, zoneOffsetMs, wallSeconds, outsideRth, barCloseEt,
  fmtCountdown, templateNameError };
if (typeof window !== 'undefined') window.HBSettings = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
