/* Homebase Charts — the indicator catalog and the page's pure helpers:
   indicator instances and their server study keys, migration of Build-1
   saved charts, legend and number formatting, interval labels. No DOM and
   no browser globals: the Node tests load this file directly. */
(function () {
'use strict';

const LINE_COLORS = ['#2962FF', '#FF6D00', '#9C27B0', '#00897B', '#E91E63'];
const ROOT_NAMES = { NQ: 'E-mini Nasdaq-100', ES: 'E-mini S&P 500', YM: 'E-mini Dow', RTY: 'E-mini Russell 2000',
  GC: 'Gold', SI: 'Silver' };
const ALWAYS_OPEN = new Set(['BTC', 'MBT', 'ETH', 'MET']);   // CME crypto: 24/7 since 2026-05-30
// The instrument badge (Task 1: legend + symbol search). No exchange or brand logos — these are our own
// text/shape designs; `icon` names a Lucide icon (icons.js) instead of text where one reads better.
const ROOT_BADGES = {
  NQ: { text: '100', bg: '#0b1f4d', fg: '#fff' }, ES: { text: '500', bg: '#b3261e', fg: '#fff' },
  YM: { text: '30', bg: '#1f3a93', fg: '#fff' }, RTY: { text: '2K', bg: '#6a1b9a', fg: '#fff' },
  GC: { text: 'Au', bg: '#c9a227', fg: '#1b1b1b' }, SI: { text: 'Ag', bg: '#9ea7ad', fg: '#1b1b1b' },
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
const GROUPS = ['All', 'VWAP & levels', 'Order flow', 'Book (L2)', 'Volume & profile', 'Calendar & news', 'Ranges & structure', 'Classic TA', 'TradingView'];
const LENGTH = (def) => ({ key: 'length', label: 'Length', type: 'int', min: 1, max: 1000, def });
// SMA/EMA (studies.py SOURCES): "sma:50"/"ema:20" keep meaning close -- the source param defaults to it.
const SOURCES = [['close', 'Close'], ['open', 'Open'], ['high', 'High'], ['low', 'Low'],
  ['hl2', 'HL2'], ['hlc3', 'HLC3'], ['ohlc4', 'OHLC4']];
const SOURCE = { key: 'source', label: 'Source', type: 'choice', choices: SOURCES, def: 'close' };
const BAND = (n, def) => [
  { key: `band${n}On`, label: `Band ${n}`, type: 'bool', def: false },
  { key: `band${n}Mult`, label: `Band ${n} multiplier`, type: 'num', min: 0.1, max: 10, step: 0.1, def }];
/* 2026-10-09: the technical indicators are DATA, not switch cases. Each entry says how its server key is built
   (`key`, matching studies_ta.py's wire keys), how its legend label reads, and every line it draws: `part` (the
   Style tab's key), a default colour/width/dash, and optionally `read` (the number to plot from the server's
   value; default: the value itself, or value[part]), `type: 'hist'` (a histogram coloured by sign) and `tag`
   false (no price-axis tag). `refs` are the dashed reference lines of an own-pane study. Each is the same
   definition the strategy engine's blocks read (studies_ta.py). A def with `pane` can live in a pane of its own
   or on the price pane; one without is drawn on the price pane only. */
/* The order-flow indicators' definitions (flowdefs.js, loaded before this file on the chart page): the book and
   tick studies of 2026-10-11. Absent (a page that does not load it), none of them exist there. */
const FLOW = (typeof window !== 'undefined' && window.HBFlowDefs)
  || (typeof require === 'function' ? require('./flowdefs.js') : { ta: [], catalog: [] });
const TA_UP = '#089981', TA_DOWN = '#F23645', TA_BLUE = '#2962FF', TA_ORANGE = '#FF6D00', TA_VIOLET = '#7E57C2', TA_GREY = '#787B86';
const TA_LEN = (def, min = 2, max = 500) => ({ key: 'length', label: 'Length', type: 'int', min, max, def });
const TA_LINE = (part, label, color, width = 1, dash = 'solid', extra = {}) => ({ part, label, color, width, dash, ...extra });
const TA_LVL = { tag: false, step: true };   // a level: no axis tag, drawn as steps so a moved level is a jump, not a slant
const TA_RANGE = [TA_LINE('hi', 'High', TA_GREY, 1, 'solid', TA_LVL), TA_LINE('lo', 'Low', TA_GREY, 1, 'solid', TA_LVL),
  TA_LINE('mid', 'Middle', TA_GREY, 1, 'dashed', TA_LVL), TA_LINE('ote1', 'OTE 62%', TA_BLUE, 1, 'dotted', TA_LVL),
  TA_LINE('ote2', 'OTE 79%', TA_BLUE, 1, 'dotted', TA_LVL)];
const hhmmMin = (t) => { const m = /^(\d{1,2}):(\d{2})$/.exec(String(t)); return m ? +m[1] * 60 + +m[2] : 0; };
// a custom or evening session's wire key: its start and end as minutes of the ET day (an end before the start crosses midnight)
/* The named sessions an older chart saved (its `session` param) are the times typed now ... */
const SESS_PRESETS = { asia: ['00:00', '03:00'], london: ['03:00', '08:25'], pre: ['08:25', '09:30'], nyam: ['09:30', '11:00'],
  evening: ['18:00', '03:00'] };
/* ... and times that are exactly one of them keep that session's own key (what the server has always computed for it);
   any other pair is a window of your own. */
const sessKey = (p) => {
  const named = Object.keys(SESS_PRESETS).find((n) => n !== 'evening' && SESS_PRESETS[n][0] === p.from && SESS_PRESETS[n][1] === p.to);
  if (named) return `sess:${named}`;
  const a = hhmmMin(p.from), b = hhmmMin(p.to);
  return a === b ? 'sess:1080:180' : `sess:${a}:${b}`;      // a window with no length falls back to the evening session
};
/* A Session range holds a list of boxes, each its own window you can switch on and off. A new one starts with the four
   sessions people watch (ET); each box takes a colour of its own by place in the list unless you pick one. */
const SESS_BOX_DEFAULTS = [{ name: 'London', from: '02:00', to: '05:00' }, { name: 'Asia', from: '20:00', to: '00:00' },
  { name: 'NY AM', from: '09:30', to: '11:00' }, { name: 'NY PM', from: '13:30', to: '16:00' }];
const SESS_BOX_COLORS = ['#2962FF', '#FF9800', '#089981', '#E91E63', '#9C27B0', '#00BCD4', '#F23645', '#8D6E63'];
const SESS_BOX_MAX = 8;
function clampBoxes(v) {
  const out = [];
  for (const b of Array.isArray(v) ? v : []) {
    if (!b || typeof b !== 'object' || out.length >= SESS_BOX_MAX) continue;
    const from = typeof b.from === 'string' && normalizeHHMM(b.from), to = typeof b.to === 'string' && normalizeHHMM(b.to);
    if (!from || !to) continue;
    const box = { name: typeof b.name === 'string' ? b.name.trim().slice(0, 14) : '', from, to, on: b.on !== false };
    if (typeof b.color === 'string' && /^#[0-9A-Fa-f]{6}$/.test(b.color)) box.color = b.color;
    out.push(box);
  }
  return out;
}
/* The boxes an instance draws: the switched-on ones, each with its wire key and colour. */
function sessBoxes(inst) {
  const list = (inst.params && Array.isArray(inst.params.boxes)) ? inst.params.boxes : [];
  return list.map((b, i) => ({ ...b, index: i, key: sessKey(b), color: b.color || SESS_BOX_COLORS[i % SESS_BOX_COLORS.length] }))
    .filter((b) => b.on !== false);
}
/* A VWAP holds its first line (anchor / customTime / bands, its Style) and up to VWAP_MORE_MAX more, each its own anchor
   (session, RTH, a custom ET time, week, month) and colour, switched on and off; they share the first line's width and dash.
   The bands are set once for the whole VWAP; each more line draws them in its own colour unless its `bands` is false. */
const VWAP_MORE_MAX = 5, VWAP_ANCHORS = ['eth', 'rth', 'custom', 'week', 'month'];
function clampVwapLines(v) {
  const out = [];
  for (const l of Array.isArray(v) ? v : []) {
    if (!l || typeof l !== 'object' || out.length >= VWAP_MORE_MAX) continue;
    const row = { anchor: VWAP_ANCHORS.includes(l.anchor) ? l.anchor : 'custom',
      customTime: (typeof l.customTime === 'string' && normalizeHHMM(l.customTime)) || '09:30', on: l.on !== false };
    if (typeof l.color === 'string' && /^#[0-9A-Fa-f]{6}$/.test(l.color)) row.color = l.color;
    if (l.bands === false) row.bands = false;   // absent = the line draws the VWAP's bands too
    out.push(row);
  }
  return out;
}
/* The extra lines a VWAP draws: the switched-on ones, each with its wire key, label and colour (its own, else by place). */
const VWAP_LINE_COLORS = ['#2962FF', '#FF6D00', '#00897B', '#E91E63', '#00BCD4'];
function vwapLines(inst) {
  const list = (inst.params && Array.isArray(inst.params.more)) ? inst.params.more : [];
  return list.map((l, i) => ({ ...l, index: i, key: vwapServerKey(l), label: vwapLabel(l), color: l.color || VWAP_LINE_COLORS[i % VWAP_LINE_COLORS.length] }))
    .filter((l) => l.on !== false);
}
/* ---- the TradingView studies (server: studies_tv.py + studies_tv2.py; wire key "tv:<name>:<args>", the args in this param order,
   TradingView's defaults and ranges). The lines, pane and colours follow the house entry closest to each one. What a plain line
   cannot draw yet (a cloud fill, a zigzag polyline, candles) is the closest line for now: the notes sit on those entries. ---- */
const TV_I = (key, label, def, min = 1, max = 500) => ({ key, label, type: 'int', min, max, def });
const TV_N = (key, label, def, min, max, step = 0.1) => ({ key, label, type: 'num', min, max, step, def });
const TV_LEN = (def, min = 1, max = 500) => TV_I('length', 'Length', def, min, max);
const TV_DEV = (label = 'Deviations') => TV_N('mult', label, 2, 0.001, 50, 0.5);
const TV_SRC = SOURCE;
const TV_ONE = (label, color = TA_BLUE, extra = {}) => [TA_LINE('main', label, color, 1, 'solid', extra)];
const TV_SIG = (a, b, ca = TA_BLUE, cb = TA_ORANGE) => [TA_LINE(a[0], a[1], ca), TA_LINE(b[0], b[1], cb)];
const TV_HIST = (part, label, extra = {}) => TA_LINE(part, label, TA_UP, 1, 'solid', { type: 'hist', tag: false, ...extra });
const TV_BANDS = [TA_LINE('up', 'Upper', TA_BLUE, 1, 'solid', { tag: false }), TA_LINE('mid', 'Basis', TA_ORANGE, 1, 'dashed', { tag: false }),
  TA_LINE('dn', 'Lower', TA_BLUE, 1, 'solid', { tag: false })];
const TV_PIVOTS = [TA_LINE('p', 'Pivot', TA_ORANGE, 1, 'solid', TA_LVL),
  ...[1, 2, 3, 4, 5].flatMap((i) => [TA_LINE(`r${i}`, `R${i}`, TA_DOWN, 1, 'solid', TA_LVL), TA_LINE(`s${i}`, `S${i}`, TA_UP, 1, 'solid', TA_LVL)])];
// a mark on the bar a pivot / fractal is CONFIRMED on, drawn on the bar `ago` bars before it; a top and a bottom on one bar give two marks
const tvMark = (up, dn, ago) => (v, P, p) => {
  const hi = v && v[up] != null, lo = v && v[dn] != null;
  const mk = (top) => ({ position: top ? 'aboveBar' : 'belowBar', color: top ? (P.down || TA_DOWN) : (P.up || TA_UP), shape: top ? 'arrowDown' : 'arrowUp',
    text: '', size: 1, ago: p[ago] });
  return hi && lo ? [mk(true), mk(false)] : hi || lo ? mk(hi) : null;
};
// the wire key's parts are read NOW: the Timeframe param is pushed onto `params` later (HTF_IDS) and is no part of the key
const tvDef = (name, title, desc, params, lines, more = {}) => {
  const keys = params.map((q) => q.key), { short, ...rest } = more;
  return { id: `tv_${name}`, group: 'TradingView', name: `${title} (TV)`, params, desc, lines, ...rest,
    key: (p) => ['tv', name, ...keys.map((k) => p[k])].join(':'),
    label: (p) => ['TV', short || title, ...keys.map((k) => p[k])].join(' ') };
};
const TV_DEFS = [
  // ---- moving averages ----
  tvDef('sma', 'SMA', 'Simple moving average: the plain average of the last N values of the source', [TV_LEN(9, 1, 1000), TV_SRC], TV_ONE('SMA')),
  tvDef('ema', 'EMA', 'Exponential moving average: newer values count more', [TV_LEN(9, 1, 1000), TV_SRC], TV_ONE('EMA')),
  tvDef('rma', 'RMA', 'Running (Wilder) moving average: the smoothing RSI and ATR use', [TV_LEN(7, 1, 1000), TV_SRC], TV_ONE('RMA')),
  tvDef('wma', 'WMA', 'Weighted moving average: the newest value weighs N, the oldest 1', [TV_LEN(9, 1, 1000), TV_SRC], TV_ONE('WMA')),
  tvDef('tema', 'TEMA', 'Triple exponential moving average: follows price with little lag', [TV_LEN(9, 1, 1000), TV_SRC], TV_ONE('TEMA', TA_ORANGE)),
  tvDef('hma', 'Hull MA', 'Hull moving average: a weighted average built to be smooth and quick', [TV_LEN(9, 2)], TV_ONE('HMA')),
  tvDef('dema', 'DEMA', 'Double exponential moving average: twice the EMA minus the EMA of the EMA', [TV_LEN(9)], TV_ONE('DEMA')),
  tvDef('smma', 'Smoothed MA', 'Smoothed moving average: Wilder smoothing of the close, same as RMA', [TV_LEN(7)], TV_ONE('SMMA')),
  tvDef('alma', 'ALMA', 'Arnaud Legoux moving average: a bell-shaped weighting you can lean to the newest bars',
    [TV_LEN(9), TV_N('offset', 'Offset', 0.85, 0, 1, 0.05), TV_N('sigma', 'Sigma', 6, 0.1, 100, 0.5)], TV_ONE('ALMA')),
  tvDef('lsma', 'Least Squares MA', 'The value of the straight line fitted through the last N closes', [TV_LEN(25, 2)], TV_ONE('LSMA'), { short: 'LSMA' }),
  tvDef('mcginley', 'McGinley Dynamic', 'A moving average that speeds up and slows down with price', [TV_LEN(14)], TV_ONE('McGinley')),
  tvDef('kama', 'Kaufman Adaptive MA', 'Moving average that speeds up in clean trends and slows in chop',
    [TV_LEN(10), TV_I('fast', 'Fast length', 2), TV_I('slow', 'Slow length', 30)], TV_ONE('KAMA'), { short: 'KAMA' }),
  tvDef('median', 'Median', 'The middle value of the last N bars of (high + low) / 2', [TV_LEN(3)], TV_ONE('Median')),
  tvDef('envelope', 'Envelope', 'A simple moving average with a band a fixed percent above and below',
    [TV_LEN(20), TV_N('percent', 'Percent', 10, 0.01, 100, 0.5)], TV_BANDS),
  // ---- trend and stops ----
  tvDef('supertrend', 'Supertrend', 'A trailing ATR line: under price in an uptrend, over it in a downtrend',
    [TV_I('length', 'ATR length', 10, 1, 1000), TV_N('mult', 'Factor', 3, 0.01, 100, 0.5)],
    [TA_LINE('up', 'Uptrend', TA_UP, 2, 'solid', { read: (v) => (v.dir === -1 ? v.line : null) }),   // TradingView's sign: -1 is up
      TA_LINE('dn', 'Downtrend', TA_DOWN, 2, 'solid', { read: (v) => (v.dir === 1 ? v.line : null) })]),
  tvDef('sar', 'Parabolic SAR', 'A stop that speeds toward price and flips when price crosses it',
    [TV_N('start', 'Start', 0.02, 0.0001, 1, 0.01), TV_N('step', 'Increment', 0.02, 0.0001, 1, 0.01), TV_N('max', 'Maximum', 0.2, 0.0001, 1, 0.05)],
    [TA_LINE('main', 'SAR', TA_BLUE, 1, 'solid', { tag: false, dots: true })]),   // dots: a line of dots, not a joined line
  tvDef('chandelier', 'Chandelier Exit', 'A stop hung from the highest (or lowest) close by a multiple of ATR',
    [TV_I('length', 'ATR length', 22), TV_N('mult', 'Multiplier', 3, 0.1, 20, 0.5)],
    [TA_LINE('long', 'Long stop', TA_UP, 2, 'solid', { read: (v) => (v.dir === 1 ? v.long : null) }),
      TA_LINE('short', 'Short stop', TA_DOWN, 2, 'solid', { read: (v) => (v.dir === -1 ? v.short : null) })]),
  tvDef('vstop', 'Volatility Stop', 'A stop that trails price by a multiple of ATR and flips when price crosses it',
    [TV_I('length', 'ATR length', 20, 2), TV_N('mult', 'Multiplier', 2, 0.25, 20, 0.25)],
    [TA_LINE('up', 'Uptrend', TA_UP, 1, 'solid', { tag: false, dots: true, read: (v) => (v.dir === 1 ? v.stop : null) }),
      TA_LINE('dn', 'Downtrend', TA_DOWN, 1, 'solid', { tag: false, dots: true, read: (v) => (v.dir === -1 ? v.stop : null) })]),
  tvDef('chandekroll', 'Chande Kroll Stop', 'A long stop and a short stop, each the extreme of an ATR-offset extreme',
    [TV_I('atrlen', 'ATR length', 10), TV_N('mult', 'ATR multiplier', 1, 0.1, 20, 0.1), TV_I('stoplen', 'Stop length', 9)],
    TV_SIG(['long', 'Stop long'], ['short', 'Stop short']), { short: 'Chande Kroll' }),
  tvDef('ichimoku', 'Ichimoku Cloud', 'Conversion and base lines, and the two leading spans (the cloud edges, not filled)',
    [TV_I('conv', 'Conversion line length', 9), TV_I('base', 'Base line length', 26), TV_I('spanb', 'Leading span B length', 52),
      TV_I('disp', 'Displacement', 26)],
    [TA_LINE('conv', 'Conversion line', TA_BLUE), TA_LINE('base', 'Base line', '#B71C1C'),
      TA_LINE('a', 'Leading span A', '#A5D6A7', 1, 'solid', { tag: false }), TA_LINE('b', 'Leading span B', '#FAA1A4', 1, 'solid', { tag: false })]),
  tvDef('alligator', 'Williams Alligator', 'Three smoothed averages of (high + low) / 2, each shown a few bars later',
    [TV_I('jaw', 'Jaw length', 13), TV_I('teeth', 'Teeth length', 8), TV_I('lips', 'Lips length', 5), TV_I('jawoff', 'Jaw offset', 8, 0, 100),
      TV_I('teethoff', 'Teeth offset', 5, 0, 100), TV_I('lipsoff', 'Lips offset', 3, 0, 100)],
    [TA_LINE('jaw', 'Jaw', TA_BLUE), TA_LINE('teeth', 'Teeth', '#E91E63'), TA_LINE('lips', 'Lips', '#66BB6A')]),
  tvDef('adx', 'ADX and DI', 'Trend strength (ADX) with the plus and minus directional lines',
    [TV_I('dilen', 'DI length', 14, 1, 1000), TV_I('adxlen', 'ADX smoothing', 14, 1, 1000)],
    [TA_LINE('adx', 'ADX', TA_BLUE, 2), TA_LINE('pdi', '+DI', TA_UP), TA_LINE('mdi', '-DI', TA_DOWN)], { pane: 'own' }),
  tvDef('aroon', 'Aroon', 'How long ago the highest high and lowest low of N bars were, as 0 to 100',
    [TV_LEN(14)], TV_SIG(['up', 'Aroon Up'], ['dn', 'Aroon Down'], '#FB8C00', TA_BLUE), { pane: 'own' }),
  tvDef('aroonosc', 'Aroon Oscillator', 'Aroon Up minus Aroon Down', [TV_LEN(14)], TV_ONE('Aroon Osc', TA_BLUE), { pane: 'own', refs: [0] }),
  tvDef('vortex', 'Vortex', 'Upward and downward movement against the true range over N bars',
    [TV_LEN(14)], TV_SIG(['vip', 'VI +'], ['vim', 'VI -'], TA_BLUE, '#E91E63'), { pane: 'own' }),
  tvDef('chop', 'Choppiness Index', 'High near 100 in a sideways market, low in a strong trend', [TV_LEN(14, 2)], TV_ONE('CHOP', TA_BLUE),
    { pane: 'own', refs: [61.8, 38.2] }),
  tvDef('dpo', 'Detrended Price Oscillator', 'The close minus an average from half a period back, to show the cycle',
    [TV_LEN(21)], TV_ONE('DPO'), { pane: 'own', refs: [0] }),
  tvDef('massindex', 'Mass Index', 'Sums how wide the bar range is versus its own average, to spot a reversal bulge',
    [TV_LEN(10)], TV_ONE('Mass Index'), { pane: 'own', refs: [27, 26.5], short: 'Mass Index' }),
  tvDef('corr', 'Correlation', 'How straight price runs with time over N bars: 1 up, -1 down, 0 none',
    [TV_LEN(14, 2)], TV_ONE('TSI', TA_BLUE), { pane: 'own', refs: [0], short: 'Correlation' }),
  // ---- momentum ----
  tvDef('rsi', 'RSI', 'Relative strength: how strongly the last N values moved up versus down, 0 to 100',
    [TV_LEN(14, 1, 1000), TV_SRC], TV_ONE('RSI', TA_VIOLET), { pane: 'own', refs: [70, 30] }),
  tvDef('macd', 'MACD', 'TradingView MACD: fast minus slow EMA, a signal line and the histogram',
    [TV_I('fast', 'Fast length', 12, 1, 1000), TV_I('slow', 'Slow length', 26, 1, 1000), TV_I('signal', 'Signal length', 9, 1, 1000), TV_SRC],
    [TV_HIST('hist', 'Histogram'), TA_LINE('macd', 'MACD', TA_BLUE), TA_LINE('signal', 'Signal', TA_ORANGE)], { pane: 'own' }),
  tvDef('stoch', 'Stochastic', 'TradingView Stochastic: where the close sits in the N-bar range, %K and %D',
    [TV_I('length', '%K length', 14, 1, 1000), TV_I('smoothk', '%K smoothing', 1, 1, 1000), TV_I('d', '%D smoothing', 3, 1, 1000)],
    TV_SIG(['k', '%K'], ['d', '%D']), { pane: 'own', refs: [80, 20] }),
  tvDef('stochrsi', 'Stochastic RSI', 'The Stochastic formula applied to RSI instead of price',
    [TV_I('rsilen', 'RSI length', 14), TV_I('length', 'Stochastic length', 14), TV_I('k', '%K smoothing', 3, 1, 100), TV_I('d', '%D smoothing', 3, 1, 100)],
    TV_SIG(['k', '%K'], ['d', '%D']), { pane: 'own', refs: [80, 20] }),
  tvDef('mfi', 'Money Flow Index', 'TradingView Money Flow Index: volume-weighted RSI of the typical price',
    [TV_LEN(14, 1, 1000)], TV_ONE('MFI', TA_VIOLET), { pane: 'own', refs: [80, 20] }),
  tvDef('cci', 'CCI', 'Commodity channel index: how far the typical price sits from its average',
    [TV_LEN(20)], TV_ONE('CCI'), { pane: 'own', refs: [100, -100] }),
  tvDef('wpr', 'Williams %R', 'Where the close sits inside the last N bars range, from 0 (top) to -100 (bottom)',
    [TV_LEN(14)], TV_ONE('%R', TA_VIOLET), { pane: 'own', refs: [-20, -80] }),
  tvDef('mom', 'Momentum', 'The close minus the close N bars ago', [TV_LEN(10)], TV_ONE('MOM'), { pane: 'own', refs: [0] }),
  tvDef('roc', 'Rate of Change', 'The percent change of the close over N bars', [TV_LEN(9)], TV_ONE('ROC'), { pane: 'own', refs: [0] }),
  tvDef('ao', 'Awesome Oscillator', 'A 5-bar average minus a 34-bar average of (high + low) / 2, as bars',
    [TV_I('fast', 'Fast length', 5), TV_I('slow', 'Slow length', 34)], [TV_HIST('main', 'AO')], { pane: 'own' }),
  tvDef('bop', 'Balance of Power', 'Close minus open over the bar range: who won the bar, from -1 to 1',
    [], TV_ONE('BOP'), { pane: 'own', refs: [0] }),
  tvDef('bbp', 'Bull Bear Power', 'How far the high and the low sit from an EMA, added: buyers versus sellers',
    [TV_LEN(13)], [TV_HIST('main', 'BBP')], { pane: 'own' }),
  tvDef('cmo', 'Chande Momentum Oscillator', 'Up moves minus down moves over their sum for N bars, -100 to 100',
    [TV_LEN(9)], TV_ONE('CMO'), { pane: 'own', refs: [0] }),
  tvDef('connors', 'Connors RSI', 'A short RSI, an RSI of the up/down streak and a percent rank, averaged',
    [TV_I('rsilen', 'RSI length', 3), TV_I('streak', 'Up/down length', 2), TV_I('rank', 'Percent rank length', 100, 1, 1000)],
    TV_ONE('CRSI'), { pane: 'own', refs: [70, 30], short: 'CRSI' }),
  tvDef('fisher', 'Fisher Transform', 'Stretches price into a near-normal curve so turns show as sharp peaks',
    [TV_LEN(9)], TV_SIG(['fisher', 'Fisher'], ['trigger', 'Trigger']), { pane: 'own', refs: [1.5, 0.75, 0, -0.75, -1.5] }),
  tvDef('ppo', 'Price Oscillator', 'The gap between a fast and a slow EMA in percent, with signal and histogram',
    [TV_I('fast', 'Fast length', 12), TV_I('slow', 'Slow length', 26), TV_I('signal', 'Signal length', 9)],
    [TV_HIST('hist', 'Histogram'), TA_LINE('ppo', 'PPO', TA_BLUE), TA_LINE('signal', 'Signal', TA_ORANGE)], { pane: 'own' }),
  tvDef('pvo', 'Volume Oscillator', 'The gap between a fast and a slow EMA of volume in percent, with signal and histogram',
    [TV_I('fast', 'Fast length', 12), TV_I('slow', 'Slow length', 26), TV_I('signal', 'Signal length', 9)],
    [TV_HIST('hist', 'Histogram'), TA_LINE('pvo', 'PVO', TA_BLUE), TA_LINE('signal', 'Signal', TA_ORANGE)], { pane: 'own', short: 'PVO' }),
  tvDef('trix', 'TRIX', 'The 1-bar change of a triple-smoothed EMA of the close, in basis points',
    [TV_LEN(18)], TV_ONE('TRIX', TA_DOWN), { pane: 'own', refs: [0] }),
  tvDef('tsi', 'True Strength Index', 'Double-smoothed momentum over double-smoothed absolute momentum, with a signal',
    [TV_I('long', 'Long length', 25), TV_I('short', 'Short length', 13), TV_I('signal', 'Signal length', 13)],
    TV_SIG(['tsi', 'TSI'], ['signal', 'Signal']), { pane: 'own', refs: [0] }),
  tvDef('smi', 'SMI Ergodic Indicator', 'The True Strength Index and its signal line',
    [TV_I('long', 'Long length', 20), TV_I('short', 'Short length', 5), TV_I('signal', 'Signal length', 5)],
    TV_SIG(['erg', 'SMI'], ['sig', 'Signal']), { pane: 'own', refs: [0], digits: 4, short: 'SMI Ergodic' }),
  tvDef('smio', 'SMI Ergodic Oscillator', 'The SMI Ergodic Indicator minus its signal line, as bars',
    [TV_I('long', 'Long length', 20), TV_I('short', 'Short length', 5), TV_I('signal', 'Signal length', 5)],
    [TV_HIST('main', 'SMI Osc')], { pane: 'own', digits: 4 }),
  tvDef('smindex', 'Stochastic Momentum Index', 'Where the close sits versus the middle of the N-bar range, double smoothed',
    [TV_I('k', '%K length', 10), TV_I('d', '%D length', 3), TV_I('ema', 'EMA length', 3)],
    TV_SIG(['smi', 'SMI'], ['ema', 'SMI-based EMA']), { pane: 'own', refs: [40, -40], short: 'SMI Index' }),
  tvDef('uo', 'Ultimate Oscillator', 'Buying pressure over true range, blended across three time frames',
    [TV_I('fast', 'Fast length', 7), TV_I('mid', 'Middle length', 14), TV_I('slow', 'Slow length', 28)], TV_ONE('UO', TA_DOWN), { pane: 'own' }),
  tvDef('rvgi', 'Relative Vigor Index', 'How far bars close from their open versus their range, with a signal line',
    [TV_LEN(10)], TV_SIG(['rvi', 'RVGI'], ['sig', 'Signal'], TA_UP, TA_DOWN), { pane: 'own' }),
  tvDef('rvi', 'Relative Volatility Index', 'RSI built on the standard deviation of closes instead of the change',
    [TV_I('length', 'Std dev length', 10, 2), TV_I('smooth', 'Smoothing length', 14)], TV_ONE('RVI', TA_VIOLET), { pane: 'own', refs: [80, 20] }),
  tvDef('coppock', 'Coppock Curve', 'A weighted average of two rates of change, for long-term turns',
    [TV_I('wma', 'WMA length', 10), TV_I('long', 'Long ROC length', 14), TV_I('short', 'Short ROC length', 11)],
    TV_ONE('Coppock'), { pane: 'own', refs: [0] }),
  tvDef('kst', 'Know Sure Thing', 'Four smoothed rates of change, added with growing weights, and a signal line',
    [TV_I('roc1', 'ROC 1 length', 10), TV_I('roc2', 'ROC 2 length', 15), TV_I('roc3', 'ROC 3 length', 20), TV_I('roc4', 'ROC 4 length', 30),
      TV_I('sma1', 'SMA 1 length', 10), TV_I('sma2', 'SMA 2 length', 10), TV_I('sma3', 'SMA 3 length', 10), TV_I('sma4', 'SMA 4 length', 15),
      TV_I('signal', 'Signal length', 9)],
    TV_SIG(['kst', 'KST'], ['sig', 'Signal'], TA_UP, TA_DOWN), { pane: 'own', refs: [0] }),
  tvDef('rci', 'Rank Correlation Index', 'How closely the price ranks follow the time ranks over N bars, -100 to 100',
    [TV_LEN(10, 2)], TV_ONE('RCI'), { pane: 'own', refs: [0] }),
  // ---- volatility ----
  tvDef('atr', 'ATR', 'TradingView ATR: the Wilder-smoothed average true range, in points',
    [TV_LEN(14, 1, 1000)], TV_ONE('ATR', TA_DOWN), { pane: 'own' }),
  tvDef('bb', 'Bollinger Bands', 'The N-bar average with bands this many standard deviations either side',
    [TV_LEN(20, 1, 1000), TV_DEV(), TV_SRC], TV_BANDS),
  tvDef('bbpct', 'Bollinger %B', 'Where the close sits between the lower band (0) and the upper band (1)',
    [TV_LEN(20, 2), TV_DEV()], TV_ONE('%B', TA_BLUE), { pane: 'own', refs: [1, 0] }),
  tvDef('bbw', 'Bollinger Bandwidth', 'The gap between the bands over the middle line: small before a squeeze breaks',
    [TV_LEN(20, 2), TV_DEV()], TV_ONE('BBW', TA_BLUE), { pane: 'own' }),
  tvDef('bbtrend', 'BBTrend', 'How far short and long Bollinger bands drift apart: trend with its strength',
    [TV_I('short', 'Short length', 20, 2), TV_I('long', 'Long length', 50, 2), TV_DEV()], [TV_HIST('main', 'BBTrend')], { pane: 'own', refs: [0] }),
  tvDef('keltner', 'Keltner (EMA + ATR)', 'An EMA with bands set by the average true range (or true range, or bar range)',
    [TV_LEN(20, 1, 1000), TV_N('mult', 'Multiplier', 2, 0.001, 50, 0.5), TV_I('atr', 'ATR length', 10, 1, 1000),
      { key: 'bands', label: 'Bands style', type: 'choice', def: 'atr', choices: [['atr', 'Average true range'], ['tr', 'True range'], ['range', 'High minus low']] }],
    [TA_LINE('up', 'Upper', TA_VIOLET, 1, 'solid', { tag: false }), TA_LINE('mid', 'Basis', TA_GREY, 1, 'dashed', { tag: false }),
      TA_LINE('dn', 'Lower', TA_VIOLET, 1, 'solid', { tag: false })]),
  tvDef('donchian', 'Donchian Channels', 'TradingView Donchian: highest high and lowest low of N bars, and their middle',
    [TV_LEN(20, 1, 1000)], [TA_LINE('up', 'Upper', TA_BLUE, 1, 'solid', { tag: false }), TA_LINE('mid', 'Middle', TA_GREY, 1, 'dashed', { tag: false }),
      TA_LINE('dn', 'Lower', TA_BLUE, 1, 'solid', { tag: false })]),
  tvDef('ulcer', 'Ulcer Index', 'How deep and how long price sat below its recent high', [TV_LEN(14)], TV_ONE('Ulcer'), { pane: 'own' }),
  tvDef('hv', 'Historical Volatility', 'The yearly-scaled standard deviation of the 1-bar log return', [TV_LEN(10, 2)], TV_ONE('HV'), { pane: 'own' }),
  tvDef('linreg', 'Linear Regression Channel', 'The fitted line of the last N closes with bands this many deviations around it',
    [TV_LEN(100, 2, 1000), TV_N('mult', 'Deviations', 2, 0, 20, 0.5)],
    [TA_LINE('up', 'Upper', TA_VIOLET, 1, 'solid', { tag: false }), TA_LINE('mid', 'Base', TA_BLUE, 1, 'solid', { tag: false }),
      TA_LINE('dn', 'Lower', TA_VIOLET, 1, 'solid', { tag: false })], { short: 'LinReg' }),
  tvDef('cog', 'Center of Gravity', 'A weighted position of the last N closes that turns before price does',
    [TV_LEN(10)], TV_ONE('COG'), { pane: 'own' }),
  // ---- volume ----
  tvDef('vwap', 'VWAP', 'Average price since its anchor, weighted by volume, with standard-deviation bands',
    [{ key: 'anchor', label: 'Anchor', type: 'choice', def: 'session', choices: [['session', 'Session'], ['week', 'Week'], ['month', 'Month'], ['quarter', 'Quarter'], ['year', 'Year']] }],
    [TA_LINE('vwap', 'VWAP', TA_VIOLET, 2), TA_LINE('u1', 'Upper band 1', TA_BLUE, 1, 'dashed', { tag: false }),
      TA_LINE('l1', 'Lower band 1', TA_BLUE, 1, 'dashed', { tag: false }), TA_LINE('u2', 'Upper band 2', TA_BLUE, 1, 'dashed', { tag: false, off: true }),
      TA_LINE('l2', 'Lower band 2', TA_BLUE, 1, 'dashed', { tag: false, off: true }), TA_LINE('u3', 'Upper band 3', TA_BLUE, 1, 'dashed', { tag: false, off: true }),
      TA_LINE('l3', 'Lower band 3', TA_BLUE, 1, 'dashed', { tag: false, off: true })]),
  tvDef('twap', 'TWAP', 'Time-weighted average price since the session open: every bar counts the same',
    [{ ...TV_SRC, def: 'ohlc4' }], TV_ONE('TWAP', TA_VIOLET)),
  tvDef('cvd', 'Cumulative Volume Delta', 'Running total of volume delta since the session open, estimated from candle colour',
    [], [TA_LINE('c', 'CVD', TA_BLUE, 2, 'solid', { tag: false })], { pane: 'own', short: 'CVD' }),   // the server sends candles (o h l c); the close line for now
  tvDef('vdelta', 'Volume Delta', 'Volume delta of each bar as bars, estimated from candle colour (up candle = buying)', [], [TV_HIST('c', 'Delta')], { pane: 'own' }),
  tvDef('updown', 'Up/Down Volume', 'Volume split by candle direction: up candles above zero, down candles below',
    [], [TV_HIST('up', 'Up volume', { fixed: true }), TA_LINE('down', 'Down volume', TA_DOWN, 1, 'solid', { type: 'hist', tag: false, fixed: true }),
      TA_LINE('delta', 'Delta', TA_ORANGE, 1, 'solid', { tag: false, off: true })], { pane: 'own', short: 'Up/Down Vol' }),
  tvDef('rvol', 'Relative Volume at Time', 'Bar volume against the same time of day on earlier days; 2 is a spike',
    [TV_I('length', 'Days compared', 14, 1, 60), { key: 'mode', label: 'Mode', type: 'choice', def: 'cumulative', choices: [['cumulative', 'Cumulative'], ['regular', 'Regular']] }],
    [TA_LINE('main', 'RVOL', TA_VIOLET, 1, 'solid', { type: 'hist', tag: false })], { pane: 'own', refs: [1, 2], short: 'RVOL' }),
  tvDef('adr', 'Average Day Range', 'The average high-to-low range of the last N completed sessions, in points',
    [TV_LEN(14, 1, 250)], TV_ONE('ADR'), { pane: 'own' }),
  tvDef('obv', 'On Balance Volume', 'Adds the bar volume on an up close and subtracts it on a down close',
    [], TV_ONE('OBV'), { pane: 'own' }),
  tvDef('pvt', 'Price Volume Trend', 'Adds a share of volume equal to the percent price change',
    [], TV_ONE('PVT'), { pane: 'own' }),
  tvDef('adl', 'Accumulation / Distribution', 'Adds volume by where the close sits in the bar range, from low to high',
    [], TV_ONE('A/D'), { pane: 'own', short: 'A/D' }),
  tvDef('cmf', 'Chaikin Money Flow', 'Volume-weighted close position over the last N bars: buying above 0, selling below',
    [TV_LEN(20)], TV_ONE('CMF', TA_UP), { pane: 'own', refs: [0] }),
  tvDef('chaikin', 'Chaikin Oscillator', 'A fast EMA minus a slow EMA of the Accumulation / Distribution line',
    [TV_I('fast', 'Fast length', 3), TV_I('slow', 'Slow length', 10)], TV_ONE('Chaikin Osc'), { pane: 'own', refs: [0], short: 'Chaikin Osc' }),
  tvDef('klinger', 'Klinger Oscillator', 'A fast minus a slow EMA of signed volume, with a signal line',
    [TV_I('fast', 'Fast length', 34), TV_I('slow', 'Slow length', 55), TV_I('signal', 'Signal length', 13)],
    TV_SIG(['kvo', 'KVO'], ['sig', 'Signal'], TA_BLUE, TA_UP), { pane: 'own', refs: [0] }),
  tvDef('efi', 'Elder Force Index', 'The bar change in price times volume, smoothed', [TV_LEN(13)], TV_ONE('EFI', TA_DOWN), { pane: 'own', refs: [0] }),
  tvDef('eom', 'Ease of Movement', 'How easily price moved per unit of volume, averaged',
    [TV_LEN(14), TV_N('divisor', 'Divisor', 10000, 1, 1e9, 1000)], TV_ONE('EOM'), { pane: 'own', refs: [0] }),
  tvDef('nvi', 'Negative Volume Index', 'Follows price only on bars where volume fell from the bar before',
    [], TV_ONE('NVI'), { pane: 'own' }),
  tvDef('pvi', 'Positive Volume Index', 'Follows price only on bars where volume rose from the bar before',
    [], TV_ONE('PVI'), { pane: 'own' }),
  tvDef('netvol', 'Net Volume', 'The bar volume, positive on an up close and negative on a down close', [], [TV_HIST('main', 'Net volume')], { pane: 'own' }),
  // ---- levels and marks ----
  tvDef('pivots', 'Pivot Points Standard', "The prior session's pivot with support and resistance levels",
    [{ key: 'kind', label: 'Type', type: 'choice', def: 'traditional', choices: [['traditional', 'Traditional'], ['fibonacci', 'Fibonacci'], ['woodie', 'Woodie'],
      ['classic', 'Classic'], ['dm', 'DM'], ['camarilla', 'Camarilla']] }], TV_PIVOTS, { short: 'Pivots' }),
  tvDef('pivothl', 'Pivot Points High Low', 'A mark on the bar of a high (or low) that N bars each side stay below (above)',
    [TV_I('left', 'Left bars', 10), TV_I('right', 'Right bars', 10)], [], { marks: tvMark('hi', 'lo', 'right'), short: 'Pivot HL' }),
  tvDef('fractals', 'Williams Fractal', 'A mark on a high (or low) that the N bars each side stay below (above)',
    [TV_I('n', 'Periods', 2, 2, 50)], [], { marks: tvMark('up', 'dn', 'n'), short: 'Fractals' }),
  tvDef('zigzag', 'Zig Zag', 'The last turning point once price moved this percent from the one before',
    [TV_N('dev', 'Deviation (%)', 5, 0.00001, 100, 0.5), TV_I('depth', 'Depth', 10)],
    [TA_LINE('px', 'Last pivot', TA_ORANGE, 2, 'solid', TA_LVL)]),   // a polyline joining the pivots is a layer cell.js does not have yet: their steps for now
];
const TA_DEFS = [
  { id: 'rsi', group: 'Classic TA', name: 'RSI', pane: 'own', params: [TA_LEN(14)], key: (p) => `rsi:${p.length}`,
    label: (p) => `RSI ${p.length}`, desc: 'Relative strength: how strongly the last N bars closed up versus down, 0 to 100',
    lines: [TA_LINE('main', 'RSI', TA_VIOLET)], refs: [70, 30] },
  { id: 'macd', group: 'Classic TA', name: 'MACD', pane: 'own', key: (p) => `macd:${p.fast}:${p.slow}:${p.signal}`,
    params: [{ ...TA_LEN(12), key: 'fast', label: 'Fast length' }, { ...TA_LEN(26), key: 'slow', label: 'Slow length' },
      { ...TA_LEN(9, 1), key: 'signal', label: 'Signal length' }],
    label: (p) => `MACD ${p.fast} ${p.slow} ${p.signal}`, desc: 'Fast minus slow EMA, its signal line and the histogram between them',
    lines: [TA_LINE('hist', 'Histogram', TA_UP, 1, 'solid', { type: 'hist', tag: false }), TA_LINE('macd', 'MACD', TA_BLUE),
      TA_LINE('signal', 'Signal', TA_ORANGE)] },
  { id: 'stoch', group: 'Classic TA', name: 'Stochastic', pane: 'own', key: (p) => `stoch:${p.length}:${p.smooth}:${p.d}`,
    params: [{ ...TA_LEN(14), label: 'K length' }, { ...TA_LEN(3, 1, 100), key: 'smooth', label: 'K smoothing' },
      { ...TA_LEN(3, 1, 100), key: 'd', label: 'D smoothing' }],
    label: (p) => `Stoch ${p.length} ${p.smooth} ${p.d}`, desc: 'Where the close sits inside the last N bars range, 0 to 100, with its signal line',
    lines: [TA_LINE('k', '%K', TA_BLUE), TA_LINE('d', '%D', TA_ORANGE)], refs: [80, 20] },
  { id: 'mfi', group: 'Classic TA', name: 'Money flow index', pane: 'own', params: [TA_LEN(14)], key: (p) => `mfi:${p.length}`,
    label: (p) => `MFI ${p.length}`, desc: 'Volume-weighted RSI: buying versus selling pressure over the last N bars, 0 to 100',
    lines: [TA_LINE('main', 'MFI', TA_VIOLET)], refs: [80, 20] },
  { id: 'er', group: 'Classic TA', name: 'Efficiency ratio', pane: 'own', params: [TA_LEN(14)], key: (p) => `er:${p.length}`,
    label: (p) => `ER ${p.length}`, desc: 'Net move over the path travelled in N bars: 1 is a straight line, near 0 is chop',
    lines: [TA_LINE('main', 'ER', TA_BLUE)], refs: [0.5, 0.25] },
  { id: 'atr', group: 'Classic TA', name: 'ATR', pane: 'own', params: [TA_LEN(14, 1)], key: (p) => `atr:${p.length}`,
    label: (p) => `ATR ${p.length}`, desc: 'Average true range: the typical bar size over the last N bars, in points',
    lines: [TA_LINE('main', 'ATR', TA_DOWN)] },
  { id: 'bb', group: 'Classic TA', name: 'Bollinger bands', key: (p) => `bb:${p.length}:${p.mult}`,
    params: [TA_LEN(20), { key: 'mult', label: 'Deviations', type: 'num', min: 0.1, max: 6, step: 0.5, def: 2 }],
    label: (p) => `BB ${p.length} ${p.mult}`, desc: 'The N-bar average of closes with bands this many standard deviations either side',
    lines: [TA_LINE('up', 'Upper', TA_BLUE, 1, 'solid', { tag: false }), TA_LINE('mid', 'Basis', TA_ORANGE, 1, 'dashed', { tag: false }),
      TA_LINE('dn', 'Lower', TA_BLUE, 1, 'solid', { tag: false })] },
  { id: 'keltner', group: 'Classic TA', name: 'Keltner channel', key: (p) => `keltner:${p.length}:${p.atr}:${p.mult}`,
    params: [TA_LEN(20), { ...TA_LEN(20, 1), key: 'atr', label: 'Range length' },
      { key: 'mult', label: 'Multiplier', type: 'num', min: 0.1, max: 10, step: 0.5, def: 1.5 }],
    label: (p) => `KC ${p.length} ${p.atr} ${p.mult}`, desc: 'An EMA with bands set by the SMA of the true range, the squeeze strategy channel',
    lines: [TA_LINE('up', 'Upper', TA_VIOLET, 1, 'solid', { tag: false }), TA_LINE('mid', 'Basis', TA_GREY, 1, 'dashed', { tag: false }),
      TA_LINE('dn', 'Lower', TA_VIOLET, 1, 'solid', { tag: false })] },
  { id: 'donchian', group: 'Classic TA', name: 'Donchian channel', params: [TA_LEN(20, 2, 1000)], key: (p) => `donchian:${p.length}`,
    label: (p) => `Donchian ${p.length}`, desc: 'Highest high and lowest low of the last N bars, with the middle between them',
    lines: [TA_LINE('up', 'Upper', TA_BLUE, 1, 'solid', { tag: false }), TA_LINE('mid', 'Middle', TA_GREY, 1, 'dashed', { tag: false }),
      TA_LINE('dn', 'Lower', TA_BLUE, 1, 'solid', { tag: false })] },
  { id: 'supertrend', group: 'Classic TA', name: 'Supertrend', key: (p) => `supertrend:${p.length}:${p.mult}`,
    params: [TA_LEN(10, 1, 200), { key: 'mult', label: 'Multiplier', type: 'num', min: 0.5, max: 10, step: 0.5, def: 3 }],
    label: (p) => `Supertrend ${p.length} ${p.mult}`, desc: 'A trailing ATR line under price in an uptrend and over it in a downtrend',
    lines: [TA_LINE('up', 'Uptrend', TA_UP, 2, 'solid', { read: (v) => (v.dir === 1 ? v.line : null) }),
      TA_LINE('dn', 'Downtrend', TA_DOWN, 2, 'solid', { read: (v) => (v.dir === -1 ? v.line : null) })] },
  { id: 'tema', group: 'Classic TA', name: 'TEMA', params: [TA_LEN(20)], key: (p) => `tema:${p.length}`,
    label: (p) => `TEMA ${p.length}`, desc: 'Triple exponential moving average: follows price closely with little lag',
    lines: [TA_LINE('main', 'TEMA', TA_ORANGE)] },
  { id: 'orb', group: 'Ranges & structure', name: 'Opening range / open candle', key: (p) => (p.start === '09:30' ? `orb:${p.minutes}` : `orb:${p.minutes}:${hhmmMin(p.start)}`),
    params: [{ key: 'minutes', label: 'Minutes', type: 'int', min: 1, max: 240, def: 15 },
      { key: 'start', label: 'Start (ET)', type: 'time', def: '09:30' }],
    label: (p) => (p.start === '09:30' ? `Opening range ${p.minutes}m` : `Candle ${p.start} ${p.minutes}m`),
    desc: 'High, low and middle of the first N minutes from a start time, all day',
    lines: [TA_LINE('hi', 'High', TA_UP, 1, 'solid', TA_LVL), TA_LINE('mid', 'Middle', TA_GREY, 1, 'dashed', TA_LVL),
      TA_LINE('lo', 'Low', TA_DOWN, 1, 'solid', TA_LVL)] },
  { id: 'sess', group: 'Ranges & structure', name: 'Session range', key: (p) => { const b = (p.boxes || []).find((x) => x.on !== false); return b ? sessKey(b) : null; },
    params: [{ key: 'boxes', label: 'Boxes', type: 'boxes', def: SESS_BOX_DEFAULTS }],
    label: (p) => { const on = (p.boxes || []).filter((b) => b.on !== false); return on.length ? on.map((b) => b.name || `${b.from}-${b.to}`).join(' · ') : 'Session range'; },
    desc: 'High and low of each time window you type (ET), as many as you like, each on or off',
    lines: [TA_LINE('hi', 'High', TA_UP, 1, 'solid', TA_LVL), TA_LINE('lo', 'Low', TA_DOWN, 1, 'dashed', TA_LVL)] },
  // ---- structure: the same definitions the strategy blocks read (engine/levels.py, ranges.py, zones.py) ----
  { id: 'swing', group: 'Ranges & structure', name: 'Swing high / low', params: [{ ...TA_LEN(50), label: 'Bars each side' }],
    key: (p) => `swing:${p.length}`, label: (p) => `Swings ${p.length}`,
    desc: 'Latest swing high and low not yet traded beyond: a bar above or below N each side',
    lines: [TA_LINE('hi', 'Swing high', TA_DOWN, 1, 'dashed', TA_LVL), TA_LINE('lo', 'Swing low', TA_UP, 1, 'dashed', TA_LVL)] },
  { id: 'equal', group: 'Ranges & structure', name: 'Equal highs / lows', key: (p) => `equal:${p.length}:${p.tol}`,
    params: [{ ...TA_LEN(50), label: 'Bars each side' }, { key: 'tol', label: 'Tolerance (points)', type: 'num', min: 0.25, max: 1000, step: 0.25, def: 10 }],
    label: (p) => `Equal H/L ${p.length} ${p.tol}`,
    desc: 'Two swings at nearly one price, not traded beyond since: resting liquidity',
    lines: [TA_LINE('hi', 'Equal highs', TA_DOWN, 1, 'dotted', TA_LVL), TA_LINE('lo', 'Equal lows', TA_UP, 1, 'dotted', TA_LVL)] },
  { id: 'rmove', group: 'Ranges & structure', name: 'Range of the current move', key: (p) => `rmove:${p.points}`,
    params: [{ key: 'points', label: 'Reversal (points)', type: 'num', min: 1, max: 5000, step: 1, def: 200 }],
    label: (p) => `Move range ${p.points}`,
    desc: 'Last turning point to the extreme since, with its middle and 62-79% band',
    lines: TA_RANGE },
  { id: 'rswing', group: 'Ranges & structure', name: 'Range between the last swing high and low', params: [{ ...TA_LEN(50), label: 'Bars each side' }],
    key: (p) => `rswing:${p.length}`, label: (p) => `Swing range ${p.length}`,
    desc: 'Latest untouched swing high to swing low, with its middle and 62-79% band',
    lines: TA_RANGE },
  { id: 'fvg', group: 'Ranges & structure', name: 'Fair value gaps', key: (p) => `fvg:${p.min}:${p.length}`,
    params: [{ key: 'min', label: 'Smallest gap (x ATR)', type: 'num', min: 0, max: 10, step: 0.05, def: 0.25 },
      { ...TA_LEN(14, 1, 200), label: 'ATR length' },
      { key: 'opacity', label: 'Box fill (%)', type: 'int', min: 0, max: 100, def: 15 }],
    label: (p) => `FVG ${p.min}`,
    desc: 'Boxes for the newest unfilled gap each side in the session: bar 3 clear of bar 1',
    lines: [] },   // drawn as boxes by the flow overlay (flowlayer.js) from the study's uh / ul / dh / dl on each bar
  { id: 'wk', group: 'VWAP & levels', name: 'Prior week high / low / close + week open', params: [], key: () => 'wk', label: () => 'Week levels',
    desc: "Last week's high, low and close, and this week's open",
    lines: [TA_LINE('hi', 'Prior week high', TA_DOWN, 1, 'solid', TA_LVL), TA_LINE('lo', 'Prior week low', TA_UP, 1, 'solid', TA_LVL),
      TA_LINE('close', 'Prior week close', TA_GREY, 1, 'dashed', TA_LVL), TA_LINE('open', 'Week open', TA_ORANGE, 1, 'dotted', TA_LVL)] },
  { id: 'mo', group: 'VWAP & levels', name: 'Prior month high / low / close + month open', params: [], key: () => 'mo', label: () => 'Month levels',
    desc: "Last month's high, low and close, and this month's open",
    lines: [TA_LINE('hi', 'Prior month high', TA_DOWN, 1, 'solid', TA_LVL), TA_LINE('lo', 'Prior month low', TA_UP, 1, 'solid', TA_LVL),
      TA_LINE('close', 'Prior month close', TA_GREY, 1, 'dashed', TA_LVL), TA_LINE('open', 'Month open', TA_ORANGE, 1, 'dotted', TA_LVL)] },
  { id: 'topen', group: 'VWAP & levels', name: 'Open at a time', key: (p) => `topen:${hhmmMin(p.time)}`,
    params: [{ key: 'time', label: 'Time (ET)', type: 'time', def: '00:00' }],
    label: (p) => `Open ${p.time}`, desc: 'The price at one time of the ET day, held to the session end',
    lines: [TA_LINE('main', 'Open', TA_ORANGE, 1, 'dashed', TA_LVL)] },
  { id: 'vaprev', group: 'Volume & profile', name: 'Prior value area', params: [], key: () => 'vaprev', label: () => 'Prior VA',
    desc: 'Prior session 09:30-16:00 value area (70% of volume) and its point of control',
    lines: [TA_LINE('vah', 'VAH', TA_BLUE, 1, 'solid', TA_LVL), TA_LINE('poc', 'POC', TA_ORANGE, 1, 'solid', TA_LVL),
      TA_LINE('val', 'VAL', TA_BLUE, 1, 'solid', TA_LVL)] },
  { id: 'dhl', group: 'VWAP & levels', name: 'Prior days high / low', params: [{ key: 'days', label: 'Days', type: 'int', min: 1, max: 60, def: 5 }],
    key: (p) => `dhl:${p.days}`, label: (p) => `${p.days}-day H/L`,
    desc: 'Highest high and lowest low of the last N completed sessions, a liquidity level',
    lines: [TA_LINE('hi', 'High', TA_DOWN, 1, 'solid', TA_LVL), TA_LINE('lo', 'Low', TA_UP, 1, 'solid', TA_LVL)] },
  { id: 'noise', group: 'Ranges & structure', name: 'Noise band', key: (p) => `noise:${p.k}:${p.anchor}`,
    params: [{ key: 'k', label: 'Multiplier', type: 'num', min: 0.05, max: 3, step: 0.05, def: 0.3 },
      { key: 'anchor', label: 'Anchor', type: 'choice', def: 'rth', choices: [['rth', 'RTH open 09:30'], ['globex', 'Globex open 01:00']] }],
    label: (p) => `Noise band ${p.k} ${p.anchor}`, desc: 'The open plus or minus k times the daily ATR: moves beyond it are not noise',
    lines: [TA_LINE('up', 'Upper', TA_UP, 1, 'solid', TA_LVL), TA_LINE('dn', 'Lower', TA_DOWN, 1, 'solid', TA_LVL)] },
  { id: 'rvol', group: 'Volume & profile', name: 'Relative volume', pane: 'own', key: (p) => `rvol:${p.days}:${p.need}`,
    params: [{ key: 'days', label: 'Days compared', type: 'int', min: 3, max: 60, def: 14 },
      { key: 'need', label: 'Fewest days needed', type: 'int', min: 1, max: 60, def: 10 }],
    label: (p) => `RVOL ${p.days}`, desc: 'Bar volume over the median of the same time of day on earlier days; 2 is a spike',
    lines: [TA_LINE('main', 'RVOL', TA_VIOLET, 1, 'solid', { type: 'hist', tag: false })], refs: [1, 2] },
  ...FLOW.ta,
  ...TV_DEFS,
];
const TA_BY_ID = Object.fromEntries(TA_DEFS.map((d) => [d.id, d]));
/* The number a generic line plots from the server's value `v` for one bar, or null (still warming up). */
function lineValue(ln, v) {
  if (v == null) return null;
  const x = ln.read ? ln.read(v) : typeof v === 'number' ? v : v[ln.part];
  return typeof x === 'number' && Number.isFinite(x) ? x : null;
}

/* W5 (2026-09-28): `desc` is the one plain line the Indicators dialog shows under each name (TradingView-style). */
const CATALOG = [
  { id: 'volume', group: 'Volume & profile', name: 'Volume', params: [], pane: 'main',
    desc: 'Contracts traded per bar; green when buyers outweighed sellers, else red' },
  { id: 'vwap', group: 'VWAP & levels', name: 'VWAP', desc: 'Average price since its anchor; several lines, each its own anchor and colour', params: [
    { key: 'anchor', label: 'Anchor', type: 'choice',
      choices: [['eth', 'Session'], ['rth', 'RTH'], ['custom', 'Custom time'], ['week', 'Week'], ['month', 'Month']], def: 'eth' },
    { key: 'customTime', label: 'Time (ET)', type: 'time', def: '02:00' },
    { key: 'more', label: 'More lines', type: 'vwaplines', def: [] },
    ...BAND(1, 1), ...BAND(2, 2), ...BAND(3, 3)] },
  { id: 'ema', group: 'Classic TA', name: 'EMA', params: [LENGTH(20), SOURCE],
    desc: 'Exponential moving average of the last N bars; recent bars count more' },
  { id: 'sma', group: 'Classic TA', name: 'SMA', params: [LENGTH(50), SOURCE], desc: 'Simple moving average: the plain average of the last N bars' },
  { id: 'vwma', group: 'Classic TA', name: 'VWMA', params: [LENGTH(20)], desc: 'Moving average of the last N bars, each bar weighted by its volume' },
  { id: 'adx', group: 'Classic TA', name: 'ADX / DMI', params: [LENGTH(14)], pane: 'own',
    desc: 'Trend strength (ADX) with the +DI / −DI direction lines, in a pane of its own' },
  { id: 'levels', group: 'VWAP & levels', name: 'Session levels', params: [],
    desc: 'Prior session high / low / close, overnight high / low and RTH open, as lines' },
  { id: 'footprint', group: 'Order flow', name: 'Footprint', desc: 'Sells at bid and buys at ask per price in each bar, shown when zoomed in', params: [
    { key: 'imbalance', label: 'Imbalance ratio (a rule below brings its own while this stays 3)', type: 'num', min: 0, max: 20, step: 0.5, def: 3 },
    { key: 'stack', label: 'Stacked imbalances: rows in a row (0 = off)', type: 'int', min: 0, max: 20, def: 3 },
    { key: 'unfinished', label: 'Mark unfinished auctions', type: 'bool', def: true },
    { key: 'deltaNum', label: 'Delta under each bar', type: 'bool', def: true },
    { key: 'rows', label: 'Ticks in each price row', type: 'choice', def: 'auto',
      choices: [['auto', 'Auto'], ['1', '1'], ['2', '2'], ['4', '4'], ['8', '8'], ['16', '16']] },
    { key: 'numbers', label: 'Numbers in each row', type: 'choice', def: 'both',
      choices: [['both', 'Sells | buys'], ['delta', 'Buys − sells'], ['total', 'Total'], ['none', 'None']] },
    { key: 'vbars', label: 'Volume bar behind each row', type: 'bool', def: true },
    { key: 'poc', label: 'Box the busiest row', type: 'bool', def: true },
    // 2026-10-21: other apps' row text and imbalance rules. Every default below is today's behaviour, so no saved chart changes.
    { key: 'text', label: 'What each row shows (overrides the numbers above)', type: 'choice', def: '',
      choices: [['', 'As set in "Numbers in each row"'], ['bidask', 'Sells | buys'], ['delta', 'Buys − sells'], ['volume', 'Total'],
        ['trades', 'Prints: sells | buys'], ['dom', 'Dominant side %'], ['price', 'Price'], ['diag', 'Diagonal differences']] },
    { key: 'imb', label: 'Imbalance rule', type: 'choice', def: 'homebase',
      choices: [['homebase', 'Homebase'], ['atas', 'ATAS (ratio 1.5)'], ['exocharts', 'Exocharts (ratio 2.5)'], ['sierra', 'Sierra Chart (ratio 1)']] },
    { key: 'zero', label: 'Other side traded nothing (a rule above sets it)', type: 'choice', def: 'one', choices: [['one', 'Compare with 1'], ['skip', 'No imbalance']] },
    { key: 'edge', label: 'Bar\'s top and bottom row (a rule above sets it)', type: 'choice', def: 'one', choices: [['one', 'Compare with 1'], ['skip', 'No imbalance']] },
    { key: 'minvol', label: 'Skip a pair when both sides are under (contracts)', type: 'int', min: 0, max: 100000, def: 0 },
    { key: 'mindiff', label: 'Imbalance needs this many more contracts', type: 'int', min: 0, max: 100000, def: 0 }] },
  { id: 'profile', group: 'Volume & profile', name: 'Volume profile', params: [
    { key: 'prior', label: 'Show the prior session', type: 'bool', def: true },
    { key: 'lines', label: 'Prior VAH / VAL / POC lines', type: 'bool', def: false },
    { key: 'va', label: 'Value area covers (% of the volume)', type: 'int', min: 50, max: 95, def: 70 },
    { key: 'width', label: 'Width (% of the chart)', type: 'int', min: 8, max: 45, def: 18 },
    { key: 'side', label: 'Side of the chart', type: 'choice', def: 'right', choices: [['right', 'Right'], ['left', 'Left']] },
    { key: 'method', label: 'POC and value area rule', type: 'choice', def: 'homebase',
      choices: [['homebase', 'Homebase'], ['sierra', 'Sierra Chart'], ['tv', 'TradingView']] }],
    desc: 'Volume at each price this session, POC and value area; prior session as a ghost' },
  { id: 'delta', group: 'Order flow', name: 'Delta', params: [], pane: 'own', desc: 'Buy minus sell volume in each bar: which side was hitting the market harder' },
  { id: 'cumdelta', group: 'Order flow', name: 'Cumulative delta', params: [], pane: 'own',
    desc: "Running total of each bar's buy-minus-sell volume, reset every session" },
  { id: 'bigprints', group: 'Order flow', name: 'Big prints', desc: 'Single N+ contract trades: green = buyers lifted the offer, red = sellers hit the bid', params: [
    { key: 'min', label: 'Minimum size', type: 'int', min: 10, max: 100000, def: 25 },   // min 10: bars.py keeps no print under BIG_MIN
    { key: 'scale', label: 'Marker size follows the print size', type: 'bool', def: true },
    { key: 'sweeps', label: 'Mark sweeps (one order walking several prices)', type: 'bool', def: false },
    { key: 'side', label: 'Show prints of', type: 'choice', def: 'all',
      choices: [['all', 'Both'], ['buy', 'Buyers'], ['sell', 'Sellers']] },
    { key: 'labels', label: 'Write the size next to each marker', type: 'bool', def: true }] },
  { id: 'bigtrades', group: 'Order flow', name: 'Big trades', label: (p) => `Big trades ≥${p.min}`,
    desc: 'Whole aggressor orders as bubbles by size; optionally grouped into one', params: [
    { key: 'min', label: 'Minimum size (contracts)', type: 'int', min: 10, max: 100000, def: 25 },   // min 10: bars.py AG_MIN
    { key: 'max', label: 'Maximum size (0 = no limit)', type: 'int', min: 0, max: 100000, def: 0 },
    { key: 'side', label: 'Show orders of', type: 'choice', def: 'all', choices: [['all', 'Both'], ['buy', 'Buyers'], ['sell', 'Sellers']] },
    { key: 'cluster', label: 'Group orders', type: 'choice', def: 'none',
      choices: [['none', 'No'], ['volume', 'By volume, the remainder carries on'], ['overshoot', 'By volume, the whole sum'], ['price', 'Until the price changes'],
        ['priceside', 'Until the price or the side changes']] },
    { key: 'thr', label: 'Group size (contracts)', type: 'int', min: 1, max: 100000, def: 100 }] },
  { id: 'npoc', group: 'Volume & profile', name: 'Naked POCs', params: [],
    desc: 'A dashed line from each bar\'s busiest price that no later bar has traded back to' },
  { id: 'tpo', group: 'Volume & profile', name: 'TPO profile', desc: 'This session as time-price letters at the right edge, with its value area', params: [
    { key: 'period', label: 'Minutes in a letter', type: 'int', min: 1, max: 240, def: 30 },
    { key: 'rows', label: 'Ticks in each row', type: 'int', min: 1, max: 100, def: 1 },
    { key: 'mode', label: 'A letter marks', type: 'choice', def: 'range',
      choices: [['range', 'Every price from the low to the high (Sierra)'], ['traded', 'Only prices that traded (MotiveWave)']] },
    { key: 'style', label: 'Draw', type: 'choice', def: 'letters', choices: [['letters', 'Letters'], ['blocks', 'Blocks']] },
    { key: 'ib', label: 'Initial balance (letters, 0 = off)', type: 'int', min: 0, max: 20, def: 2 },
    { key: 'va', label: 'Value area covers (% of the letters)', type: 'int', min: 50, max: 95, def: 70 },
    { key: 'method', label: 'POC and value area rule', type: 'choice', def: 'sierra',
      choices: [['sierra', 'Sierra Chart'], ['homebase', 'Homebase'], ['tv', 'TradingView']] }] },
  { id: 'cstat', group: 'Order flow', name: 'Cluster statistics', params: [],
    desc: 'A strip under the candles: delta, volume, trades, delta %, delta range, seconds' },
  { id: 'dturn', group: 'Order flow', name: 'Delta turnaround', desc: 'Arrows where the delta turned against two bars of the other colour', params: [
    { key: 'fix', label: 'Compare with the earlier bar\'s high for a down turn', type: 'bool', def: false }] },
  { id: 'dstr', group: 'Order flow', name: 'Delta strength', desc: 'Arrows on bars that closed near their own best delta', params: [
    { key: 'min', label: 'From (% of the best delta)', type: 'int', min: 1, max: 100, def: 80 },
    { key: 'max', label: 'Up to (% of the best delta)', type: 'int', min: 1, max: 100, def: 100 }] },
  { id: 'mwabs', group: 'Order flow', name: 'Absorption (tape)', desc: 'An imbalance that price then walked away from, a line to the bar that showed it', params: [
    { key: 'ticks', label: 'Price leaves it by (ticks)', type: 'int', min: 1, max: 200, def: 4 },
    { key: 'within', label: 'Within (bars after)', type: 'int', min: 0, max: 50, def: 3 },
    { key: 'imb', label: 'Imbalance rule', type: 'choice', def: 'homebase',
      choices: [['homebase', 'Homebase'], ['atas', 'ATAS'], ['exocharts', 'Exocharts'], ['sierra', 'Sierra Chart']] }] },
  { id: 'bigorders', group: 'Book (L2)', name: 'Big orders', desc: 'Resting book orders N× the median size or more, as lines; ended ones stay', params: [
    { key: 'multiple', label: 'Multiple', type: 'num', min: 1, max: 50, step: 0.5, def: 5 },
    { key: 'minSeconds', label: 'Ended ones that stood at least (seconds)', type: 'int', min: 3, max: 600, def: 5 },   // bookflow.py shows none younger than 3 s
    { key: 'history', label: 'Keep ended orders on the chart', type: 'bool', def: true },
    { key: 'width', label: 'Line thickness', type: 'choice', def: '2', choices: [['1', 'Thin'], ['2', 'Normal'], ['4', 'Thick']] }] },
  { id: 'imbalance', group: 'Book (L2)', name: 'Book imbalance (live)', params: [], desc: 'Bid vs ask size resting in the top 10 book levels, as a gauge in the legend' },
  { id: 'heatmap', group: 'Book (L2)', name: 'Liquidity heatmap', desc: 'Resting book size at each price over time, behind the candles; optional trade bubbles', params: [
    { key: 'map', label: 'Show the heatmap', type: 'bool', def: true },
    { key: 'bubbles', label: 'Trade bubbles', type: 'bool', def: false },
    { key: 'bubbleMin', label: 'Bubble from (contracts in one second)', type: 'int', min: 3, max: 10000, def: 10 },
    { key: 'bubbleMax', label: 'Bubble up to (contracts, 0 = no limit)', type: 'int', min: 0, max: 100000, def: 0 },
    { key: 'bubbleSide', label: 'Bubbles of', type: 'choice', def: 'all', choices: [['all', 'Buyers and sellers'], ['buy', 'Buyers only (lifted the offer)'], ['sell', 'Sellers only (hit the bid)']] },
    { key: 'contrast', label: 'Contrast (strong shows smaller orders too)', type: 'choice', def: 'normal',
      choices: [['soft', 'Soft'], ['normal', 'Normal'], ['strong', 'Strong']] },
    { key: 'palette', label: 'Colours', type: 'choice', def: 'fire',
      choices: [['fire', 'Fire'], ['ice', 'Ice'], ['mono', 'Grey']] }] },
  { id: 'events', group: 'Calendar & news', name: 'Economic calendar', desc: 'Calendar events as flags on the chart; pick red, orange or yellow folders', params: [
    { key: 'high', label: 'Red folder (high impact)', type: 'bool', def: true },
    { key: 'medium', label: 'Orange folder (medium impact)', type: 'bool', def: true },
    { key: 'low', label: 'Yellow folder (low impact)', type: 'bool', def: false },
    { key: 'holiday', label: 'Grey folder (holidays)', type: 'bool', def: false },
    { key: 'lines', label: 'Vertical line at a red or orange event', type: 'bool', def: true },
    { key: 'lineStyle', label: 'Line style', type: 'choice', def: 'dotted', choices: [['solid', 'Solid'], ['dashed', 'Dashed'], ['dotted', 'Dotted']] },
    { key: 'lineWidth', label: 'Line width', type: 'choice', def: '1', choices: [['1', '1'], ['2', '2'], ['3', '3'], ['4', '4']] }] },
  { id: 'headlines', group: 'Calendar & news', name: 'News headlines', desc: 'News dots, and a bolt for a big move that had news behind it', params: [
    { key: 'show', label: 'Show', type: 'choice', def: 'bursts',
      choices: [['bursts', 'Big moves that had news'], ['all', 'Every headline and every big move']] }] },
  /* A Pine script run in the page (cell.js, pineworker.js): no server key. `script` is a name from /api/pine/scripts and
     `inputs` the script's own inputs by variable name or id (only the ones changed from the script's defaults), so a saved layout with
     neither is a pine row that draws nothing. */
  { id: 'pine', group: 'TradingView', name: 'Pine script', desc: 'Runs a Pine script from your script list on this chart\'s bars', params: [
    { key: 'script', label: 'Script', type: 'pinescript', def: '' },
    { key: 'inputs', label: 'Script inputs', type: 'pineinputs' },
    { key: 'maxbars', label: 'Bars to run on', type: 'int', min: 100, max: 20000, step: 100, def: 5000 }],
    label: (p) => (p.script ? `Pine ${p.script}` : 'Pine script') },
  ...FLOW.catalog,
  ...TA_DEFS,
];
/* A study may be read on a longer timeframe (2026-10-11; server studies.HTF, wire key "ema:20@3600"): the window and
   smoothing ones take a Timeframe input, "Chart" (0) = the chart's own bars. */
const HTF_IDS = ['ema', 'sma', 'vwma', 'adx', 'rsi', 'macd', 'stoch', 'mfi', 'er', 'atr', 'bb', 'keltner', 'donchian', 'supertrend', 'tema', 'fvg',
  ...TV_DEFS.filter((d) => !d.marks).map((d) => d.id)];   // every tv: study reads only the bars (studies.HTF_OK holds "tv") -- but a mark study's `ago` counts chart bars (studies.HTF_NOT_TV)
/* The timeframe is typed, any length from a second to a day: "15m", "1h", "90s", "4h", "1D" (a bare number is minutes). */
function parseTf(text) {
  const m = /^\s*(\d+(?:\.\d+)?)\s*(s|sec|secs|m|min|mins|h|hr|hrs|d|day|days)?\s*$/i.exec(String(text == null ? '' : text));
  if (!m) return null;
  const unit = (m[2] || 'm').toLowerCase(), n = Number(m[1]);
  const sec = Math.round(n * (unit[0] === 's' ? 1 : unit[0] === 'm' ? 60 : unit[0] === 'h' ? 3600 : 86400));
  return sec >= 1 && sec <= 86400 ? sec : null;
}
function fmtTf(sec) {
  const n = Number(sec);
  if (!(n > 0)) return '';
  if (n % 86400 === 0) return `${n / 86400}D`;
  if (n % 3600 === 0) return `${n / 3600}h`;
  if (n % 60 === 0) return `${n / 60}m`;
  return `${n}s`;
}
for (const id of HTF_IDS) {
  const d = CATALOG.find((x) => x.id === id);
  if (d) d.params.push({ key: 'tf', label: 'Timeframe', type: 'tf', def: '0', omitDefault: true });
}
const tfSec = (p) => { const n = p && /^\d+$/.test(String(p.tf)) ? Number(p.tf) : 0; return n >= 1 && n <= 86400 ? n : 0; };
const BY_ID = Object.fromEntries(CATALOG.map((d) => [d.id, d]));
const FAVOURITES = [['1m', 'time:60'], ['5m', 'time:300'], ['15m', 'time:900'], ['1h', 'time:3600'], ['4h', 'time:14400'], ['D', 'time:86400']];
/* The starred intervals (the toolbar row), from their stored JSON: valid specs only, each once, in the
   interval menu's order (a custom one after the listed ones, in the order starred); junk/none -> the defaults.
   An empty stored list is kept empty (the user unstarred everything). */
function parseFavs(text) {
  let a = null;
  try { a = JSON.parse(text); } catch (_) { a = null; }
  if (!Array.isArray(a)) return FAVOURITES.map(([, s]) => s);
  const out = [];
  for (const s of a) if (typeof s === 'string' && parseSpec(s) && !out.includes(s)) out.push(s);
  return sortFavs(out);
}
function sortFavs(specs) {
  const order = INTERVAL_GROUPS.flatMap(([, s]) => s), rank = (s) => { const i = order.indexOf(s); return i < 0 ? order.length : i; };
  return specs.map((s, i) => [s, i]).sort((a, b) => rank(a[0]) - rank(b[0]) || a[1] - b[1]).map(([s]) => s);
}
/* Star / unstar one interval: a new sorted list. */
function toggleFav(specs, spec) {
  return specs.includes(spec) ? specs.filter((s) => s !== spec) : sortFavs([...specs, spec]);
}
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
const LATE_S = 60;        // a market whose newest print came in this far behind the wall clock is LATE: the exchange's
                          // delayed feed runs 600 s behind while the socket reads "connected, no error" (2026-10-02)

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

const HHMM = /^([01]\d|2[0-3]):[0-5]\d$/;   // the canonical stored/wire form

/* Loose keyboard entry for a "Time (ET)" field, normalised to the canonical zero-padded "HH:MM", or null:
   "9:30" / "09:30" / "930" / "0930" all mean the same thing -- typing without the colon, or without the
   leading zero, is the normal way to enter a time, not an error. */
function normalizeHHMM(text) {
  const t = String(text == null ? '' : text).trim();
  let hh, mm;
  const withColon = /^(\d{1,2}):(\d{1,2})$/.exec(t);
  if (withColon) { hh = +withColon[1]; mm = +withColon[2]; }
  else {
    const digits = /^(\d{3,4})$/.exec(t);
    if (!digits) return null;
    hh = +digits[1].slice(0, -2);
    mm = +digits[1].slice(-2);
  }
  return hh >= 0 && hh <= 23 && mm >= 0 && mm <= 59 ? `${String(hh).padStart(2, '0')}:${String(mm).padStart(2, '0')}` : null;
}

/* A Pine script's name (a file name the server lists) and its input overrides, by the input's variable name or id (an old save: by
   title): a number, a switch or a word each, at most 64 of them; anything else is dropped, and no override at all is no key.
   PINE_NAME is the server's NAME_RE (homebase/charts/pineapi.py: any letter or digit, then .pine, 255 characters at most): change both together. */
const PINE_NAME = /^(?=.{1,255}$)[\p{L}\p{N}_ .-]+\.pine$/u;
function clampPineInputs(v) {
  if (!v || typeof v !== 'object' || Array.isArray(v)) return null;
  const out = {};
  for (const [k, x] of Object.entries(v).slice(0, 64)) {
    if (!k || k.length > 120) continue;
    if (typeof x === 'boolean' || (typeof x === 'number' && Number.isFinite(x)) || (typeof x === 'string' && x.length <= 200)) out[k] = x;
  }
  return Object.keys(out).length ? out : null;
}
function clampParams(id, params) {
  const d = def(id);
  let src = params && typeof params === 'object' ? params : {};
  const out = {};
  if (!d) return out;
  // a session range saved with a named session: those are the times now typed
  if (id === 'sess' && SESS_PRESETS[src.session]) src = { ...src, from: SESS_PRESETS[src.session][0], to: SESS_PRESETS[src.session][1] };
  // a session range saved with one window (from / to) is one box
  if (id === 'sess' && !Array.isArray(src.boxes) && (src.from || src.to)) src = { ...src, boxes: [{ name: '', from: src.from || '03:00', to: src.to || '08:25', on: true }] };
  for (const p of d.params) {
    const v = src[p.key];
    if (p.type === 'boxes') { out[p.key] = clampBoxes(Array.isArray(v) ? v : p.def); continue; }
    if (p.type === 'vwaplines') { const more = clampVwapLines(v); if (more.length) out[p.key] = more; continue; }   // none = no key
    if (p.type === 'pinescript') { out[p.key] = typeof v === 'string' && PINE_NAME.test(v) ? v : ''; continue; }
    if (p.type === 'pineinputs') { const more = clampPineInputs(v); if (more) out[p.key] = more; continue; }   // none = no key
    if (p.type === 'tf') {      // typed ("15m"), kept as seconds; "Chart" is no key at all
      const s = typeof v === 'string' || typeof v === 'number' ? (/^\d+$/.test(String(v)) ? Number(v) : parseTf(v)) : null;
      if (s && s >= 1 && s <= 86400) out[p.key] = String(s);
      continue;
    }
    if (p.type === 'bool') out[p.key] = typeof v === 'boolean' ? v : p.def;
    else if (p.type === 'choice') {
      const pick = p.choices.some(([c]) => c === v) ? v : p.def;
      if (!(p.omitDefault && pick === p.def)) out[p.key] = pick;     // the timeframe: "Chart" is no key at all, as before it existed
    }
    else if (p.type === 'time') out[p.key] = (typeof v === 'string' && normalizeHHMM(v)) || p.def;
    else {
      let n = v === null || v === '' || typeof v === 'boolean' ? NaN : Number(v);
      if (!Number.isFinite(n)) n = p.def;
      if (p.type === 'int') n = Math.round(n);
      out[p.key] = Math.min(p.max, Math.max(p.min, n));
    }
  }
  if (id === 'rvol' && out.need > out.days) out.need = out.days;    // the server wants "need" within "days" (catalog only: a saved key is never rejected)
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
  adx: ['adx', 'pdi', 'mdi'], cumdelta: ['main'], volume: ['up', 'down'], delta: ['up', 'down'] };
/* volume and delta are histograms coloured by the bar's side: their two "lines" are the up and the down colour, and the
   Style tab shows a colour and an opacity for them, no width or dash (a style row's controls: see styleControls). */
const COLOR_ONLY = new Set(['volume', 'delta']);
function styleControls(id) { return COLOR_ONLY.has(id) ? 'color' : 'line'; }
function styleLineKeys(id) { if (id === 'sess') return null;   // its boxes carry their own colours
  const t = TA_BY_ID[id];
  return STYLE_LINES[id] || (t && t.lines.length ? t.lines.map((l) => l.part) : null); }   // a study drawn as markers only has no line style

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

function lineStyle(color, width, dash, alpha) { return alpha == null ? { color, width, dash, visible: true } : { color, width, dash, visible: true, alpha }; }

/* A fresh per-line style {color, width (1-4), dash ('solid'|'dashed'|'dotted'), visible} for every line of a
   NEW instance of `id`, or null when `id` has no Style tab. `siblings`: see cycleColor. */
function defaultStyle(id, siblings) {
  const keys = styleLineKeys(id);
  if (!keys) return null;
  const color = cycleColor(id, siblings);
  switch (id) {
    case 'volume': case 'delta': return { up: lineStyle(UP_DEFAULT, 1, 'solid', 50), down: lineStyle(DOWN_DEFAULT, 1, 'solid', 50) };
    case 'vwap': return { main: lineStyle(color, 2, 'solid'), band1: lineStyle(color, 1, 'dashed'),
      band2: lineStyle(color, 1, 'dashed'), band3: lineStyle(color, 1, 'dashed') };
    case 'adx': return { adx: lineStyle(color, 2, 'solid'), pdi: lineStyle(UP_DEFAULT, 1, 'solid'),
      mdi: lineStyle(DOWN_DEFAULT, 1, 'solid') };
    default: {
      if (TA_BY_ID[id]) {   // a second copy of the same indicator moves its first line's colour on, the rest keep theirs
        const out = {}, again = (siblings || []).some((x) => x.id === id);
        TA_BY_ID[id].lines.forEach((l, i) => {
          out[l.part] = lineStyle(again && i === 0 ? color : l.color, l.width, l.dash);
          if (l.off) out[l.part].visible = false;   // a part line a new chart starts without (flowdefs.js)
        });
        return out;
      }
      return { main: lineStyle(color, id === 'cumdelta' ? 2 : 1, 'solid') };   // ema, sma, vwma, delta, cumdelta
    }
  }
}

/* The optional extras of a line's style (2026-10-11): alpha (10-100 %, 100 = solid, left out), shape (line | steps |
   curved; left out = the indicator's own), tag (its value on the price axis; left out = the indicator's own). They are
   in the object only when set, so a style nobody touched is stored exactly as before. */
const SHAPES = ['line', 'steps', 'curved'];
function clampLineStyle(v, fallback) {
  const o = v && typeof v === 'object' ? v : {};
  const out = { color: typeof o.color === 'string' && /^#[0-9a-fA-F]{6}$/.test(o.color) ? o.color : fallback.color,
    width: [1, 2, 3, 4].includes(+o.width) ? +o.width : fallback.width,
    dash: DASH_STYLES.includes(o.dash) ? o.dash : fallback.dash,
    visible: typeof o.visible === 'boolean' ? o.visible : fallback.visible };
  const base = fallback.alpha == null ? 100 : fallback.alpha;
  const a = o.alpha === null || o.alpha === '' || typeof o.alpha === 'boolean' ? NaN : Math.round(Number(o.alpha));
  const alpha = Number.isFinite(a) && a >= 10 && a <= 100 ? a : base;
  if (alpha !== 100) out.alpha = alpha;
  if (SHAPES.includes(o.shape)) out.shape = o.shape;
  if (typeof o.tag === 'boolean') out.tag = o.tag;
  return out;
}
/* A line's colour with its opacity applied: '#RRGGBB' alone at 100 %, else 'rgba(r,g,b,a)'. */
function lineColor(st) {
  const hex = st && typeof st.color === 'string' && /^#[0-9a-fA-F]{6}$/.test(st.color) ? st.color : '#787B86';
  const a = st && Number.isFinite(st.alpha) ? Math.min(100, Math.max(10, st.alpha)) : 100;
  if (a >= 100) return hex;
  return `rgba(${parseInt(hex.slice(1, 3), 16)},${parseInt(hex.slice(3, 5), 16)},${parseInt(hex.slice(5, 7), 16)},${a / 100})`;
}

/* An instance's other options (2026-10-11), `opts`, left out when nothing is changed: legend:false (no values in
   the legend row), and for a study with reference levels (RSI 70/30 ...) refs: one value per level, null = that
   level not drawn, and refColor. A value that is not what the dialog can make is dropped; nothing left = null. */
const HEX6 = /^#[0-9a-fA-F]{6}$/;
function refsOf(id) { const t = TA_BY_ID[id]; return t && Array.isArray(t.refs) ? t.refs : null; }
function clampOpts(id, o) {
  const src = o && typeof o === 'object' ? o : {}, out = {}, refs = refsOf(id);
  if (src.legend === false) out.legend = false;
  if (refs) {
    if (Array.isArray(src.refs) && src.refs.length === refs.length && src.refs.every((n) => n === null || (typeof n === 'number' && Number.isFinite(n)))) {
      const r = src.refs.map((n) => (n === null ? null : Math.min(1e6, Math.max(-1e6, n))));
      if (r.some((n, i) => n !== refs[i])) out.refs = r;
    }
    if (typeof src.refColor === 'string' && HEX6.test(src.refColor)) out.refColor = src.refColor;
  }
  return Object.keys(out).length ? out : null;
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

/* A preset payload ({params, style}) loaded from the presets store (or typed by hand into the JSON file), run
   through clampParams/clampStyle so a junk or stale payload can never reach a chart: an unknown/out-of-range
   param falls back to its catalog default, and a style with no line keys (an indicator with no Style tab, or
   one saved before a catalog change added a line) falls back to defaultStyle's fresh colours. Used by the
   indicator settings dialog's Template ▾ (Save as…/Apply default/Apply one of the list) and by the page's
   own indicator-defaults cache (app.js's loadIndicatorDefaults, the add-indicator path). */
function sanitizePreset(id, payload) {
  const p = payload && typeof payload === 'object' ? payload : {};
  const params = clampParams(id, p.params);
  const keys = styleLineKeys(id);
  const style = keys ? (clampStyle(id, p.style) || defaultStyle(id, [])) : null;
  return { params, style };
}

/* The two news indicators (2026-10-12). A chart shows the economic calendar only while an `events` indicator is on
   it and visible, and headlines / big-move bolts only while a `headlines` one is: the folders, the line and the
   mode are its params. A chart saved before this carried the same choices as chart settings (evHigh ... newsOnChart);
   seedNews() turns those into the two indicators once (the cell then carries `newsInd`, so deleting one sticks). */
const NEWS_LEGACY = { evHigh: true, evMedium: true, evLow: false, evHoliday: false, evLines: true, evLineStyle: 'dotted', evLineWidth: 1, newsOnChart: 'bursts' };
function seedNews(indicators, settings) {
  const out = Array.isArray(indicators) ? indicators.slice() : [];
  const s = { ...NEWS_LEGACY, ...(settings && typeof settings === 'object' ? settings : {}) };
  if (!out.some((x) => x.id === 'events')) {
    const any = !!(s.evHigh || s.evMedium || s.evLow || s.evHoliday);
    out.push(instance('events', any ? { high: !!s.evHigh, medium: !!s.evMedium, low: !!s.evLow, holiday: !!s.evHoliday,
      lines: s.evLines !== false, lineStyle: s.evLineStyle, lineWidth: String(s.evLineWidth) } : { lines: s.evLines !== false,
      lineStyle: s.evLineStyle, lineWidth: String(s.evLineWidth) }, { visible: any }));
  }
  if (!out.some((x) => x.id === 'headlines')) {
    out.push(instance('headlines', { show: s.newsOnChart === 'all' ? 'all' : 'bursts' }, { visible: s.newsOnChart !== 'off' }));
  }
  return out;
}
/* What the calendar layer draws for a chart's indicators: null when no visible `events` indicator is on it, else
   the settings HBEvents.shown() and the flag layer read (the countries stay a chart setting: Settings > Events). */
function eventsView(indicators) {
  const x = (indicators || []).find((i) => i.id === 'events' && i.visible !== false);
  if (!x) return null;
  const p = clampParams('events', x.params);
  return { evHigh: p.high, evMedium: p.medium, evLow: p.low, evHoliday: p.holiday, evLines: p.lines, evLineStyle: p.lineStyle,
    evLineWidth: Number(p.lineWidth) };
}
/* The `newsOnChart` mode a chart's indicators ask for: 'off' with no visible `headlines` indicator. */
function newsMode(indicators) {
  const x = (indicators || []).find((i) => i.id === 'headlines' && i.visible !== false);
  return x ? clampParams('headlines', x.params).show : 'off';
}

function defaults() { return [instance('volume'), instance('vwap'), instance('levels'), instance('footprint')]; }

/* The VWAP wire key (studies.py's VWAP anchor) for this instance's params: "vwap"/"vwap:rth" unchanged;
   "vwap:week"/"vwap:month"; "vwap:t0200" for a custom HH:MM ET (colon stripped -- wire keys use ':' as their
   own delimiter). An invalid/missing customTime never reaches here: clampParams already fell back to its
   default. */
function vwapLabel(p) {
  if (p.anchor === 'rth') return 'VWAP RTH';
  if (p.anchor === 'week') return 'VWAP W';
  if (p.anchor === 'month') return 'VWAP M';
  if (p.anchor === 'custom') return `VWAP ${HHMM.test(p.customTime) ? p.customTime : '02:00'}`;
  return 'VWAP';
}
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
  const key = baseServerKey(inst), sec = HTF_IDS.includes(inst.id) ? tfSec(inst.params) : 0;
  return key && sec ? `${key}@${sec}` : key;
}
function baseServerKey(inst) {
  const p = inst.params || {};
  switch (inst.id) {
    case 'vwap': return vwapServerKey(p);
    case 'ema': case 'sma': return `${inst.id}:${p.length}${p.source && p.source !== 'close' ? `:${p.source}` : ''}`;
    case 'vwma': case 'adx': return `${inst.id}:${p.length}`;
    case 'levels': case 'cumdelta': case 'profile': return inst.id;
    default: return TA_BY_ID[inst.id] ? TA_BY_ID[inst.id].key(p) : null;
  }
}

// a session range asks for the window of every box that is on; any other indicator for its one key
const keysOf = (inst) => (inst.id === 'sess' ? sessBoxes(inst).map((b) => b.key)
  : inst.id === 'vwap' ? [serverKey(inst), ...vwapLines(inst).map((l) => l.key)] : [serverKey(inst)]);
/* A "bk:" key is computed in the page from the book samples (flowdefs.js): it is never asked of the server. */
function serverKeys(list) { return [...new Set((list || []).flatMap(keysOf).filter((k) => k && !k.startsWith('bk:')))]; }

/* A saved chart config of any vintage as {root, spec, indicators}. The spec is
   normalised as the server answers it (a Build-1 "tick:0750" is "tick:750"). */
/* A stored vwap params object from BEFORE this anchor/bands rework: the indicators-array format (like
   Build-1's "st" form, migrated a few lines below) could already carry {anchor, bands}. `bands` is not a
   param key any more, so clampParams alone would silently drop it -- translate it into today's band 1 (x1) +
   band 2 (x2) on/off FIRST, the same mapping the st-form branch uses. A params object that never had `bands`
   passes through untouched. */
function migrateVwapParams(params) {
  const src = params && typeof params === 'object' ? params : {};
  if (typeof src.bands !== 'boolean') return src;
  const { bands, ...rest } = src;
  return { ...rest, band1On: bands, band1Mult: 1, band2On: bands, band2Mult: 2 };
}

function migrate(cfg) {
  const c = cfg && typeof cfg === 'object' ? cfg : {};
  const root = typeof c.root === 'string' && c.root ? c.root.toUpperCase() : 'NQ';
  const spec = toSpec(c.spec) || 'time:60';
  if (Array.isArray(c.indicators)) {
    const indicators = c.indicators.filter((x) => x && def(x.id)).map((x) => {
      const params = x.id === 'vwap' ? migrateVwapParams(x.params) : x.params;
      const o = { uid: typeof x.uid === 'string' && x.uid ? x.uid : uid(), id: x.id,
        params: clampParams(x.id, params), visible: x.visible !== false };
      if (movable(x.id)) o.pane = placement(x);
      const st = clampStyle(x.id, x.style);   // absent/malformed: no `style` -- renders as it always has
      if (st) o.style = st;
      const op = clampOpts(x.id, x.opts);
      if (op) o.opts = op;
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

/* Chart grids: [columns, rows]. A layout may also carry `sizes` {cols, rows}: each track's share of the
   page, mean 1 (equal tracks = null). The dividers between charts drag these. */
const GRID_DIMS = { 1: [1, 1], 2: [2, 1], 4: [2, 2], 6: [3, 2] };
const MIN_TRACK = 0.2;   // a track never shrinks below this share of an equal one
function cleanSizes(s, grid) {
  const d = GRID_DIMS[grid];
  if (!d || !s || typeof s !== 'object') return null;
  const ok = (a, n) => Array.isArray(a) && a.length === n && a.every((x) => typeof x === 'number' && Number.isFinite(x) && x > 0);
  if (!ok(s.cols, d[0]) || !ok(s.rows, d[1])) return null;
  const norm = (a) => { const t = a.reduce((x, y) => x + y, 0); return a.map((x) => Math.round((x * a.length / t) * 1e4) / 1e4); };
  const cols = norm(s.cols), rows = norm(s.rows);
  return cols.every((x) => x === 1) && rows.every((x) => x === 1) ? null : { cols, rows };
}
/* Drag the divider between track k-1 and k by `delta` equal-track widths: the pair keeps its total and
   neither side goes under MIN_TRACK. A new array; the input is not touched. */
function dragTrack(tracks, k, delta) {
  const out = tracks.slice();
  if (!(k >= 1 && k < out.length) || !Number.isFinite(delta)) return out;
  const tot = out[k - 1] + out[k], a = Math.min(tot - MIN_TRACK, Math.max(MIN_TRACK, out[k - 1] + delta));
  out[k - 1] = Math.round(a * 1e4) / 1e4;
  out[k] = Math.round((tot - a) * 1e4) / 1e4;
  return out;
}
/* The bar a time falls in, on a chart whose bars (ascending, each with its start `ms`) are given: the last bar
   starting at or before `ms`, or -1 when none does, or when `ms` lies past that bar's end (a gap in the data;
   barMs 0 = an event-driven chart whose bars have no fixed length: only the last hour past the last bar counts). */
function barIndexAtMs(bars, ms, barMs) {
  let lo = 0, hi = bars.length - 1, at = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (bars[mid].ms <= ms) { at = mid; lo = mid + 1; } else hi = mid - 1;
  }
  if (at < 0) return -1;
  if (barMs > 0) return ms < bars[at].ms + barMs ? at : -1;
  return at === bars.length - 1 && ms - bars[at].ms > 3600000 ? -1 : at;
}

function migrateLayout(v) {
  const o = v && typeof v === 'object' ? v : {};
  const grid = [1, 2, 4, 6].includes(+o.grid) ? +o.grid : 4;
  return { grid, sizes: cleanSizes(o.sizes, grid), cells: (Array.isArray(o.cells) ? o.cells : []).map(migrate) };
}

function label(inst) {
  const l = baseLabel(inst), sec = HTF_IDS.includes(inst.id) ? tfSec(inst.params) : 0;
  return sec ? `${l} · ${fmtTf(sec)}` : l;       // "EMA 20 · 1h": read on that timeframe
}
function baseLabel(inst) {
  const d = def(inst.id), p = inst.params || {};
  if (!d) return String(inst.id);
  switch (inst.id) {
    case 'vwap': {
      const n = vwapLines(inst).length;
      return n ? `${vwapLabel(p)} +${n}` : vwapLabel(p);   // "VWAP 09:30 +1": its first line, and how many more
    }
    case 'ema': case 'sma':
      return p.source && p.source !== 'close' ? `${d.name} ${p.length} ${p.source.toUpperCase()}` : `${d.name} ${p.length}`;
    case 'vwma': return `${d.name} ${p.length}`;
    case 'adx': return `ADX ${p.length}`;
    case 'footprint': return p.imbalance > 0 ? `Footprint ${p.imbalance}×` : 'Footprint';
    case 'bigprints': return `Big prints ≥${p.min}`;
    case 'bigorders': return `Big orders ${p.multiple}×`;
    case 'events': {
      const f = [p.high && 'red', p.medium && 'orange', p.low && 'yellow', p.holiday && 'grey'].filter(Boolean);
      return `Calendar ${f.length ? f.join('+') : 'none'}`;   // one word after the title: the legend's "indicator arguments" option
    }
    case 'headlines': return p.show === 'all' ? 'News all' : 'News bolts';
    default: return d.label ? d.label(p) : d.name;
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
  const fix = (d) => (x) => (x == null || !Number.isFinite(x) ? '—' : x.toFixed(d)), n2 = fix(2);
  switch (inst.id) {
    case 'ema': case 'sma': case 'vwma': return [{ text: fmtPrice(v, tick), color: colors.line }];
    case 'vwap': return [{ text: fmtPrice(v ? v.vwap : null, tick), color: colors.vwap },
      ...vwapLines(inst).map((l) => { const lv = bar && bar.sv ? bar.sv[l.key] : null; return { text: fmtPrice(lv ? lv.vwap : null, tick), color: l.color }; })];
    case 'adx': {    // each line in the colour the user gave it (Style tab), else the theme's
      const sc = (part, dflt) => (inst.style && inst.style[part] && inst.style[part].color) || dflt;
      return [{ text: n2(v && v.adx), color: sc('adx', colors.text) }, { text: n2(v && v.pdi), color: sc('pdi', colors.up) },
        { text: n2(v && v.mdi), color: sc('mdi', colors.down) }];
    }
    case 'cumdelta': return [{ text: fmtSigned(v), color: colors.cum }];
    case 'sess': {      // each box on: its high and low in its colour
      return sessBoxes(inst).flatMap((b) => { const bv = bar && bar.sv ? bar.sv[b.key] : null;
        return [{ text: n2(bv && bv.hi), color: b.color }, { text: n2(bv && bv.lo), color: b.color }]; });
    }
    default: {
      const t = TA_BY_ID[inst.id];
      if (!t) return [];
      const nd = fix(t.digits ?? 2);   // a study that sends a small ratio (SMI Ergodic) says how many decimals it needs
      // one value per line that is shown (a hidden line adds nothing), in that line's own colour
      const st = inst.style || {}, out = t.lines.filter((ln) => !(st[ln.part] && st[ln.part].visible === false))
        .map((ln) => ({ text: nd(lineValue(ln, v)), color: (st[ln.part] && st[ln.part].color) || ln.color, on: lineValue(ln, v) != null, pick: !!ln.read }));
      // lines that take turns (Supertrend's up / down side) show only the one in force
      const live = out.filter((x) => !x.pick || x.on);
      const shown = (live.length ? live : out.slice(0, 1)).map(({ text, color }) => ({ text, color }));
      const say = t.words ? t.words(lineValue(t.lines[0], v)) : '';   // a word in front: who is winning, etc.
      if (say) { const x = lineValue(t.lines[0], v); shown.unshift({ text: say, word: true, color: x >= 10 ? colors.up : x <= -10 ? colors.down : colors.text }); }
      return shown;
    }
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
   itself is root- and session-aware — see staleAfter/sinceOpen.
   The data's own state rides along (amber): "late N min" when the open markets' newest prints came in LATE_S or
   more behind the wall (each root's `late_s`, measured by the service; the median, so it is the feed's -- one
   market behind is named instead), and "thin feed" when the tick job's data watchdog (`s.data`) found the live
   recording short of the published tick ids. Its line is the tooltip's last part; a reading too old is not used. */
function feedSummary(s, weekday, minutes) {
  const roots = Object.entries(s.roots || {}), rec = s.recorder, recErr = rec && rec.error;
  const open = (r) => marketOpen(r, weekday, minutes), age = (x) => x.last_tick_age_s;
  const refused = roots.filter(([, x]) => x.error), live = roots.filter(([r, x]) => !x.error && open(r));
  const silent = live.filter(([, x]) => age(x) == null);
  const clamped = (x) => Math.min(age(x), sinceOpen(minutes));
  const stale = live.filter(([r, x]) => age(x) != null && clamped(x) > staleAfter(r, weekday, minutes))
    .sort((a, b) => age(b[1]) - age(a[1]));
  const lag = live.filter(([, x]) => age(x) != null && x.late_s != null).map(([, x]) => x.late_s).sort((a, b) => a - b);
  const feedLate = lag.length && lag[lag.length >> 1] >= LATE_S ? lag[lag.length >> 1] : 0;
  const behind = (r, x) => open(r) && !x.error && age(x) != null && x.late_s >= LATE_S;
  const lateMin = (v) => Math.round(v / 60);
  const d = s.data, thin = !!(d && !d.stale && d.thin && d.thin.length);
  const watch = !d ? '' : d.stale ? `data watch: not checked for ${fmtAge(d.age_s)}`
    : `data watch, ${fmtAge(d.age_s)} ago: ${String(d.line || '').replace(/^data: /, '')}`;
  const title = [roots.map(([r, x]) => `${r} ${x.error ? `unavailable: ${x.error}`
    : !open(r) ? 'closed' : age(x) == null ? 'no ticks yet'
    : fmtAge(age(x)) + (behind(r, x) ? `, ${lateMin(x.late_s)}m late` : '')}`).join('  ·  '), watch].filter(Boolean).join('  —  ');
  if (s.error || recErr) return { dot: 'bad', text: s.error || `recorder: ${recErr}`, textClass: 'bad', title };
  if (!s.connected) return { dot: 'bad', text: 'connecting…', textClass: '', title };
  const late = feedLate ? [`late ${lateMin(feedLate)} min`]
    : roots.filter(([r, x]) => behind(r, x)).slice(0, 2).map(([r, x]) => `${r} late ${lateMin(x.late_s)} min`);
  const warn = refused.length > 0 || stale.length > 0 || late.length > 0 || thin;
  const text = [...refused.map(([r]) => `${r} unavailable`),
    ...stale.slice(0, 2).map(([r, x]) => `${r} stale ${fmtAge(age(x))}`),
    ...late, ...(thin ? ['thin feed'] : []),
    ...silent.slice(0, 2).map(([r]) => `${r} no ticks yet`)].join(' · ') || (roots.length ? 'feeds ok' : '');
  const dot = warn || (rec && rec.buffered >= REC_BUSY) ? 'warn' : silent.length ? '' : 'ok';
  return { dot, text, textClass: warn ? 'warn' : '', title };
}

/* W1 (2026-09-28): which status-bar segments step out so the rest fits `avail` px. `items`, in bar order:
   {width, gap, drop} -- `gap` the space it adds beside its neighbour, `drop` its rank (the lowest steps out first) or
   null: never (the connection and desk state, a note, the licence credit). A segment steps out WHOLE, never cut, and
   only while the bar still does not fit. The indexes to hide, ascending; [] when everything fits. */
function statusDrops(avail, items) {
  const list = Array.isArray(items) ? items : [];
  let need = list.reduce((s, it, i) => s + (it.width || 0) + (i ? it.gap || 0 : 0), 0);
  const ranked = list.map((it, i) => [it, i]).filter(([it]) => it.drop != null).sort((a, b) => a[0].drop - b[0].drop || b[1] - a[1]);
  const out = [];
  for (const [it, i] of ranked) {
    if (need <= avail) break;
    need -= (it.width || 0) + (it.gap || 0);
    out.push(i);
  }
  return out.sort((a, b) => a - b);
}

/* The "Best" group of the indicators dialog (2026-10-12): the ones the build-days prediction study found worth having, in
   the order it ranked them, each with its verdict in plain words (shown under the name in that group). Like Favorites it is
   no catalog group: a fixed list. Finding: 50-Permanent/Findings/2026-10-12-indicator-prediction-study-build-days.md */
const BEST_GROUP = 'Best';
const BEST = [
  ['orb', 'Direction: price above or below the 15-minute range keeps going. The only one that did, a little.'],
  ['atr', 'Size: how big the next moves will be. No direction. Use it for stops and targets.'],
  ['vwap', 'A reference line for fair price. It does not forecast.'],
  ['rvol', 'Size: busy bars are followed by bigger moves. Weak.'],
  ['tspeed', 'Size: a fast tape is followed by bigger moves. Weak.'],
  ['delta', 'Describes the bar just closed, on time. Forecasts nothing.'],
  ['bigprints', 'Describes the bar: big prints and sweeps. Forecasts nothing.'],
  ['footprint', 'Describes the bar: stacked imbalances per price. Forecasts nothing.'],
];
const BEST_NOTE = new Map(BEST);

/* The TradingView tab's sections (2026-10-22): which one holds each tv_ twin (and the Pine runner, first). Only a heading in the
   dialog: ids, groups and wire keys are untouched. The counts match the section comments of TV_DEFS. */
const TV_SECTIONS = ['Pine scripts', 'Moving averages', 'Trend & stops', 'Momentum', 'Volatility & bands', 'Volume', 'Levels & marks'];
const TV_TOPICS = {
  pine: 0,
  ...Object.fromEntries([
    'sma ema rma wma tema hma dema smma alma lsma mcginley kama median envelope',
    'supertrend sar chandelier vstop chandekroll ichimoku alligator adx aroon aroonosc vortex chop dpo massindex corr',
    'rsi macd stoch stochrsi mfi cci wpr mom roc ao bop bbp cmo connors fisher ppo pvo trix tsi smi smio smindex uo rvgi rvi coppock kst rci',
    'atr bb bbpct bbw bbtrend keltner donchian ulcer hv linreg cog',
    'vwap twap cvd vdelta updown rvol adr obv pvt adl cmf chaikin klinger efi eom nvi pvi netvol',
    'pivots pivothl fractals zigzag',
  ].flatMap((names, i) => names.split(' ').map((n) => [`tv_${n}`, i + 1]))),
};
for (const d of CATALOG) if (d.id in TV_TOPICS) d.topic = TV_SECTIONS[TV_TOPICS[d.id]];

/* `favs`: the starred indicator ids, for the Favorites group (which is no catalog group: it is whatever is starred).
   A query ranks (2026-10-22): the exact id or name first, then a name / id hit, then a group-word hit, then a hit only in the
   one-line description; inside a rank the house studies come before the tv_ twins, then catalog order. Every word must match.
   No query: catalog order (the TradingView tab by section). */
function filter(query, group = 'All', favs = []) {
  const q = String(query || '').trim().toLowerCase(), words = q.split(/\s+/).filter(Boolean);
  const rows = CATALOG.filter((d) => group === 'All' || (group === FAV_GROUP ? favs.includes(d.id)
    : group === BEST_GROUP ? BEST_NOTE.has(d.id) : d.group === group));
  const rank = (d) => {
    const name = d.name.toLowerCase(), has = (t) => words.every((w) => t.includes(w));
    if (d.id === q || name === q) return 0;
    if (has(`${name} ${d.id}`)) return 1;
    if (has(`${name} ${d.id} ${d.group.toLowerCase()}`)) return 2;
    const head = `${name} ${d.id} ${d.group.toLowerCase()}`, dw = String(d.desc || '').toLowerCase().split(/[^a-z0-9]+/);
    return words.every((w) => head.includes(w) || dw.some((x) => x.startsWith(w))) ? 3 : -1;     // the description: from a word's start, so "er" is not every "order"
  };
  const by = (key) => rows.map((d, i) => [d, i, key(d)]).filter((x) => x[2] != null).sort((a, b) => a[2] - b[2] || a[1] - b[1]).map((x) => x[0]);
  if (group === BEST_GROUP) return by((d) => (!q || rank(d) >= 0 ? BEST.findIndex(([i]) => i === d.id) : null));
  if (!q) return group === 'TradingView' ? by((d) => TV_SECTIONS.indexOf(d.topic)) : rows;
  return by((d) => { const r = rank(d); return r < 0 ? null : r * 2 + (d.id.startsWith('tv_') ? 1 : 0); });
}

/* ---- starred indicators and drawing tools (2026-10-11) ----
   Both are lists of ids kept per browser. The Favorites group of the indicators dialog is what is starred there; the tools
   rail shows the starred tools in a row of their own and the rest in these popup groups (a group's button shows the tool
   last used from it). Order = the order they were starred. */
const FAV_GROUP = 'Favorites';
const TOOL_GROUPS = [
  ['Lines and shapes', ['trend', 'ray', 'xline', 'arrow', 'channel', 'hline', 'vline', 'rect']],
  ['Fib and positions', ['fib', 'long', 'short', 'measure']],
  ['Notes and marks', ['note', 'avwap', 'alert']],
];
/* The indicators the saved layouts actually use, most first (2026-10-22): the Favorites group before the user stars anything. */
const IND_FAV_DEFAULT = ['vwap', 'volume', 'levels', 'footprint', 'events', 'headlines', 'bigorders', 'bigprints', 'profile', 'delta'];
const TOOL_FAV_DEFAULT = ['trend', 'hline', 'rect', 'fib', 'long', 'short'];
/* A stored JSON list of ids: only ids `valid` knows, each once; junk or nothing stored -> `fallback`. A stored empty list is kept
   (the user unstarred everything). */
function parseIdList(text, valid, fallback) {
  let a = null;
  try { a = JSON.parse(text); } catch (_) { a = null; }
  if (!Array.isArray(a)) return [...fallback];
  const out = [];
  for (const id of a) if (typeof id === 'string' && valid.includes(id) && !out.includes(id)) out.push(id);
  return out;
}
/* Star / unstar one id: a new list, a newly starred one last. */
function toggleId(list, id) { return list.includes(id) ? list.filter((x) => x !== id) : [...list, id]; }
/* Which tool group holds a tool (an index into TOOL_GROUPS), -1 for the cursor or an unknown one. */
function toolGroupOf(tool) { return TOOL_GROUPS.findIndex(([, tools]) => tools.includes(tool)); }

const api = { parseFavs, sortFavs, toggleFav, CATALOG, GROUPS, ROOT_NAMES, FAVOURITES, INTERVAL_GROUPS, LINE_COLORS, uid, def, clampParams, instance,
  defaults, seedNews, eventsView, newsMode, serverKey, serverKeys, migrate, migrateLayout, TA_BY_ID, lineValue, sessBoxes, vwapLines, VWAP_MORE_MAX, VWAP_ANCHORS, SESS_BOX_COLORS, SESS_BOX_MAX, SESS_BOX_DEFAULTS, GRID_DIMS, cleanSizes, dragTrack, barIndexAtMs, label, legendValues, decimals, fmtPrice, fmtCompact,
  fmtSigned, change, parseSpec, specLabel, longLabel, toSpec, parseInterval, matchSymbols, rootName, rootBadge, filter,
  ALWAYS_OPEN, marketOpen, fmtAge, feedSummary, statusDrops, REC_BUSY, staleAfter, sinceOpen, PANES, movable, placement,
  styleLineKeys, styleControls, defaultStyle, clampStyle, cycleColor, sanitizePreset, normalizeHHMM,
  SHAPES, lineColor, refsOf, clampOpts, HTF_IDS, parseTf, fmtTf,
  FAV_GROUP, BEST_GROUP, BEST, TOOL_GROUPS, TOOL_FAV_DEFAULT, IND_FAV_DEFAULT, TV_SECTIONS, TV_TOPICS, parseIdList, toggleId, toolGroupOf };
if (typeof window !== 'undefined') window.HBCatalog = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
