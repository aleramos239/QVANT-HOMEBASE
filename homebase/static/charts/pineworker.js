/* The Pine Worker: runs ONE Pine script (PineTS 0.12.1, served by GET /api/pine/runtime.js) on the chart's own
   bars, inside a Web Worker so the page never blocks. Standalone: it imports nothing from the other chart
   modules; the page talks to it with postMessage only. tools/pine/parity.mjs loads this same file in Node.

   IN  {type:'init', source, inputs?, root, tf_s, tick_size, point_value, bars, maxBars?}
         source       the .pine text; it needs a //@version line, else an error (PineTS would run it as JavaScript)
         inputs       {key: value} overrides for the script's input.* calls (optional); key = the input's variable name or id
                      (inputsMeta varId / id), which tells apart two inputs of one title; an input's title also works (old saves)
         root         NQ|ES|RTY|YM|GC|SI -> syminfo CME_MINI:NQ1! ES1! RTY1!, CBOT_MINI:YM1!, COMEX:GC1! SI1!,
                      timezone America/Chicago, session 1700-1600; mintick / pointvalue from tick_size / point_value
         tf_s         the chart's bar length in seconds (time bars only)
         bars         [{ms, s?, o, h, l, c, v, fp?}] ascending. s = the trade date (ISO), filled from ms when absent;
                      fp = [[price, sells, buys]] (the footprint wire rows) feeds request.footprint
         maxBars      run on the last N bars (default 5000, at most 20000)
   IN  {type:'bars', bars:[...]}   new or changed bars, same shape. Bars at or after the last known bar run
         incrementally (the PineTS stream re-executes the last bar / appends the new ones); anything older
         (scroll-back, a repaired bar) is a full re-run on the last maxBars.

   OUT {type:'result', full, firstMs, kind, title, overlay, inputsMeta, plots, plotsMeta, shapes,
        boxes, lines, labels, linefills, polylines, tables, strategy, warnings}
         full         true = a whole run; false = only the points with time >= the first changed bar: merge by time
         firstMs      ms of bar_index 0 (drawing x values in bar_index count from it)
         plots        {title: [{time, value, color?}]}  time = bar ms, value = number | null (na)
         plotsMeta    {title: PineTS plot options: style style_line|style_stepline|style_histogram|...|background|
                      barcolor|hline (absent = a line), color, linewidth, overlay}
         shapes       [{title, time, shape, location, color?, text?, char?, size?}]: every plotshape / plotchar /
                      plotarrow hit
         boxes, lines, labels, linefills, polylines, tables   PineTS drawing objects as data (x = bar_index unless
                      xloc is bar_time); deleted ones dropped
         strategy     {closedtrades, opentrades, netprofit, equity, max_drawdown} for a strategy, else null.
                      Pine's own broker, bar fills: never a Homebase backtest
         inputsMeta   [{id, name, title, type, defval, minval, maxval, step, group, options}] from the script
         warnings     [string]: PineTS runtime warnings + this provider's (another symbol, no footprint, ...)
   OUT {type:'error', message}   a compile or runtime error; the last result stands

   Other symbols and lower timeframes answer [] (na) with a warning. A same-symbol higher timeframe is
   aggregated here from the chart's bars: intraday anchored at the 18:00 ET session open, D keyed on the trade
   date, W on its Monday, M on its month. */
'use strict';
importScripts('/api/pine/runtime.js');

const Lib = self.PineTSLib;
/* Best effort, NOT the sandbox: a script that gets past the //@version check below (it cannot: see rerun) would run in this Worker
   with the chart page's origin. The runtime is loaded and needs none of these (it fetches only in data providers this Worker
   does not use), so they go. Dynamic import() cannot be blocked from here: the version check is the real fix. */
for (const k of ['fetch', 'XMLHttpRequest', 'WebSocket', 'EventSource', 'importScripts', 'Worker', 'SharedWorker']) {
  try { Object.defineProperty(self, k, { value: undefined, writable: false, configurable: false }); } catch (e) { /* shortcut: an engine that keeps it, the version check still holds */ }
}
const MAX_LOOPS = 200000;
const POLL_MS = 1000;
const DEFAULT_BARS = 5000, MAX_BARS = 20000;
const MONTH_S = 2628003;              // TradingView's month in timeframe arithmetic
const DAY = 86400000;
const SYM = { NQ: ['CME_MINI', 'E-mini Nasdaq-100'], ES: ['CME_MINI', 'E-mini S&P 500'],
              RTY: ['CME_MINI', 'E-mini Russell 2000'], YM: ['CBOT_MINI', 'E-mini Dow'],
              GC: ['COMEX', 'Gold'], SI: ['COMEX', 'Silver'] };
// The runtime's own marker test: a source it finds no //@version in is run as raw JavaScript, a marked one is Pine or an error.
const MARKER = /^\s*\/\/\s*@version\s*=\s*(\d+)\s*$/im;
const HEAD = /^\s*(indicator|strategy|study)\s*\(\s*(?:title\s*=\s*)?(["'])(.*?)\2/m;   // the title only; the runtime reads the rest of the declaration
const ETDATE = new Intl.DateTimeFormat('en-CA', { timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit' });
const ETTIME = new Intl.DateTimeFormat('en-US', { timeZone: 'America/New_York', hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });

let gen = 0, cfg = null, sym = null, stream = null, running = 0;   // running = the gen whose first run is still in flight
let store = [], byMs = new Map();     // the chart's bars, ascending, keyed by ms
let sinceMs = null;                   // the first bar changed since the last result went out
const offBySession = new Map();

self.onmessage = (e) => {
  const m = e.data || {};
  try {
    if (m.type === 'init') init(m);
    else if (m.type === 'bars') onBars(m.bars || []);
  } catch (err) { fail(err); }
};

function fail(err) { postMessage({ type: 'error', message: String((err && err.message) || err) }); }

function sessionDate(ms) { return ETDATE.format(new Date(ms + 6 * 3600000)); }   // 18:00 ET opens the next trade date

function sinceOpenS(b) {
  // seconds since the 18:00 ET session open; the ET offset is fixed inside a session (DST moves at 02:00 Sunday)
  let off = offBySession.get(b.s);
  if (off === undefined) {
    let h = 0, mi = 0, s = 0;
    for (const p of ETTIME.formatToParts(new Date(b.ms))) {
      if (p.type === 'hour') h = +p.value % 24; else if (p.type === 'minute') mi = +p.value; else if (p.type === 'second') s = +p.value;
    }
    off = ((h * 3600 + mi * 60 + s) * 1000 - (b.ms % DAY) + DAY) % DAY;
    offBySession.set(b.s, off);
  }
  const wall = ((b.ms % DAY) + off) % DAY;
  return ((wall - 18 * 3600000 + DAY) % DAY) / 1000;
}

function parseTf(tf) {   // a Pine timeframe string ("5", "15S", "D", "1W", "M") -> {n, u, s}, or null
  const m = /^(\d*)([SDWM]?)$/i.exec(String(tf).trim());
  if (!m) return null;
  const n = m[1] ? +m[1] : 1, u = m[2].toUpperCase();
  if (!n) return null;
  return { n, u, s: n * (u === 'S' ? 1 : u === '' ? 60 : u === 'D' ? 86400 : u === 'W' ? 604800 : MONTH_S) };
}

function tfString(tfS) { return tfS === 86400 ? 'D' : tfS % 86400 === 0 ? (tfS / 86400) + 'D' : tfS % 60 === 0 ? String(tfS / 60) : tfS + 'S'; }

function weekKey(s) {
  const d = new Date(s + 'T00:00:00Z');
  return new Date(d.getTime() - ((d.getUTCDay() + 6) % 7) * DAY).toISOString().slice(0, 10);
}

function bucketKey(b, tf) {
  if (tf.u === 'D') return b.s;
  if (tf.u === 'W') return weekKey(b.s);
  if (tf.u === 'M') return b.s.slice(0, 7);
  return b.s + ':' + Math.floor(sinceOpenS(b) / tf.s);
}

function kline(b, spanMs) { return { openTime: b.ms, closeTime: b.ms + spanMs, open: b.o, high: b.h, low: b.l, close: b.c, volume: b.v }; }

function aggregate(tf) {
  const out = [];
  let key = null, cur = null;
  for (const b of store) {
    const k = bucketKey(b, tf);
    if (k !== key) { key = k; cur = kline(b, tf.s * 1000); out.push(cur); }
    else { if (b.h > cur.high) cur.high = b.h; if (b.l < cur.low) cur.low = b.l; cur.close = b.c; cur.volume += b.v; }
  }
  return out;
}

function syminfo(c) {
  const [prefix, description] = SYM[c.root] || ['CME', c.root];
  const ticker = c.root + '1!', tickerid = prefix + ':' + ticker;
  const pricescale = Math.pow(10, (String(c.tick_size).split('.')[1] || '').length);
  return { ticker, tickerid, main_tickerid: tickerid, current_contract: ticker, prefix, root: c.root, description,
           type: 'futures', currency: 'USD', basecurrency: '', timezone: 'America/Chicago', session: '1700-1600',
           mintick: c.tick_size, minmove: Math.round(c.tick_size * pricescale), pricescale, pointvalue: c.point_value,
           volumetype: 'base' };
}

function mine(tickerId) {
  const t = String(tickerId || ''), base = t.slice(t.lastIndexOf(':') + 1);
  return base === sym.ticker || base === cfg.root || t === sym.tickerid;
}

function makeProvider(g, warnings) {
  const served = new Map();   // per (ticker, tf): the chart bar object last served, so an unchanged last bar is not re-served
  const warn = (s) => warnings.add(s);
  const range = (rows, limit, sDate, eDate, key) => {
    if (sDate != null) rows = rows.filter((r) => r.openTime >= sDate);
    if (eDate != null) rows = rows.filter((r) => r.openTime <= eDate);
    return limit ? rows.slice(-limit) : rows;
  };
  return {
    configure() {},
    async getSymbolInfo() { return sym; },
    async getMarketData(tickerId, tf, limit, sDate, eDate) {
      if (g !== gen) return [];
      if (!mine(tickerId)) { warn('request.security: no data for ' + tickerId + ' (only the chart\'s own market runs here)'); return []; }
      const p = parseTf(tf);
      if (!p) { warn('timeframe "' + tf + '" is not supported'); return []; }
      const own = p.s === cfg.tf_s;
      if (!own) {
        if (p.u === 'D' || p.u === 'W' || p.u === 'M') {
          if (p.n !== 1 || cfg.tf_s > p.s) { warn('request.security: timeframe "' + tf + '" cannot be built from this chart'); return []; }
        } else if (p.s < cfg.tf_s || p.s % cfg.tf_s) { warn('request.security: timeframe "' + tf + '" is below or not a multiple of the chart\'s'); return []; }
      }
      const key = tickerId + '|' + tf;
      const rows = own ? store.map((b) => kline(b, cfg.tf_s * 1000)) : aggregate(p);
      let out;
      if (sDate != null && eDate == null && limit == null) {
        // the stream's poll from the last bar it holds: the bars after it, plus that bar when it changed
        let i = rows.length;
        while (i > 0 && rows[i - 1].openTime > sDate) i--;
        out = rows.slice(i);
        if (i > 0 && rows[i - 1].openTime === sDate && (!own || byMs.get(sDate) !== served.get(key))) out.unshift(rows[i - 1]);
      } else out = range(rows, limit, sDate, eDate);
      if (out.length) served.set(key, store[store.length - 1]);
      return out;
    },
    async getFootprintData(tickerId, tf, limit, sDate, eDate) {
      if (g !== gen || !mine(tickerId)) return [];
      const p = parseTf(tf);
      if (!p || p.s !== cfg.tf_s) { warn('request.footprint: only the chart\'s own timeframe has a footprint'); return []; }
      if (!store.some((b) => b.fp)) { warn('request.footprint: the chart carries no footprint (fp)'); return []; }
      let rows = store;
      if (sDate != null) rows = rows.filter((b) => b.ms >= sDate);
      if (eDate != null) rows = rows.filter((b) => b.ms <= eDate);
      if (limit) rows = rows.slice(-limit);
      return rows.filter((b) => b.fp && b.fp.length).map((b) => ({ openTime: b.ms, tick: cfg.tick_size,
        levels: b.fp.map((r) => ({ price: r[0], buyVolume: r[2], sellVolume: r[1] })) }));
    },
  };
}

function ingest(bars) {   // true when every bar is at or after the last known one (the stream can take them)
  let tail = true;
  const lastMs = store.length ? store[store.length - 1].ms : -Infinity;
  for (const b of bars) {
    if (!b.s) b.s = sessionDate(b.ms);
    if (b.ms < lastMs) tail = false;
    const old = byMs.get(b.ms);
    byMs.set(b.ms, b);
    if (old) store[store.lastIndexOf(old)] = b;
    else store.push(b);
  }
  if (!tail) store.sort((a, b) => a.ms - b.ms);
  return tail;
}

function stopStream() { if (stream) { stream.stop(); stream = null; } }

function init(m) {
  gen++;
  stopStream();
  cfg = { source: String(m.source || ''), inputs: m.inputs || {}, root: String(m.root || ''), tf_s: +m.tf_s,
          tick_size: +m.tick_size, point_value: +m.point_value, maxBars: Math.min(MAX_BARS, +m.maxBars || DEFAULT_BARS) };
  if (!(cfg.tf_s > 0)) throw new Error('Pine runs on time bars only');
  if (!(cfg.tick_size > 0) || !(cfg.point_value > 0)) throw new Error('tick_size and point_value are needed');
  sym = syminfo(cfg);
  store = []; byMs = new Map(); offBySession.clear();
  ingest(m.bars || []);
  rerun();
}

function onBars(bars) {
  if (!cfg || !bars.length) return;
  const wasFull = store.length >= cfg.maxBars, firstMs = store.length ? store[0].ms : Infinity;
  let lo = Infinity;
  for (const b of bars) if (b.ms < lo) lo = b.ms;
  if (ingest(bars) && (stream || running === gen)) { sinceMs = sinceMs == null ? lo : Math.min(sinceMs, lo); return; }   // the stream's next poll takes them
  if (wasFull && lo < firstMs && !bars.some((b) => b.ms >= firstMs)) { trim(); return; }         // older history only: outside the run window
  gen++;
  stopStream();
  rerun();
}

function trim() {
  if (store.length > cfg.maxBars) { store = store.slice(-cfg.maxBars); byMs = new Map(store.map((b) => [b.ms, b])); }
}

function rerun() {
  trim();
  sinceMs = null;
  if (!store.length) throw new Error('no bars');
  const g = gen, warnings = new Set();
  if (!MARKER.test(cfg.source)) throw new Error('Not a Pine script: it needs a //@version=5 or //@version=6 line');   // else PineTS would run it as JavaScript
  const ind = new Lib.Indicator(cfg.source, cfg.inputs);
  const h = HEAD.exec(cfg.source);
  const meta = { kind: ind.getDeclarationType(), title: h ? h[3] : null, overlay: ind.prop.overlay === true,   // === true: `overlay=ov` comes back as the name
                 inputsMeta: strip(ind.getInputsMeta()) };
  const pine = new Lib.PineTS(makeProvider(g, warnings), sym.tickerid, tfString(cfg.tf_s), store.length);
  pine.setMaxLoops(MAX_LOOPS);
  running = g;
  pine.ready().then(() => {
    if (g !== gen) return;
    let first = true;
    const s = pine.stream(ind, { live: true, interval: POLL_MS, pageSize: 1e9 });
    s.on('data', (ctx) => {
      if (g !== gen) return;
      const full = first, since = full ? null : sinceMs;
      first = false; sinceMs = null;
      postMessage(toResult(ctx, meta, full, since, warnings));
    });
    s.on('error', (err) => { if (g === gen) { running = 0; fail(err); } });
    stream = s;
    running = 0;
  }).catch((err) => { if (g === gen) { running = 0; fail(err); } });
}

function strip(x) {   // drawing / trade objects as plain data: no private fields, no functions
  if (Array.isArray(x)) return x.map(strip);
  if (x && typeof x === 'object') {
    const o = {};
    for (const k in x) if (k[0] !== '_' && typeof x[k] !== 'function') o[k] = strip(x[k]);
    return o;
  }
  return x;
}

function tail(data, since) {   // the plot points from `since` on, one per time (a re-executed bar appends a newer point: the last wins)
  const out = [];
  let i = 0;
  if (since != null) { i = data.length; while (i > 0 && data[i - 1].time >= since) i--; }
  for (; i < data.length; i++) {
    if (i + 1 < data.length && data[i + 1].time === data[i].time) continue;
    out.push(data[i]);
  }
  return out;
}

function toResult(ctx, meta, full, since, warnings) {
  const plots = {}, plotsMeta = {}, shapes = [];
  const draw = { boxes: [], lines: [], labels: [], linefills: [], polylines: [], tables: [] };
  const P = ctx.plots || {};
  for (const title in P) {
    const p = P[title], data = p.data || [];
    if (title.startsWith('__')) {
      const k = title.slice(2, -2);
      if (k in draw) draw[k] = strip((((data[0] || {}).value) || []).filter((d) => !d._deleted));
      continue;
    }
    const o = p.options || {};
    if (o.style === 'shape' || o.style === 'char') {
      for (const d of tail(data, since)) {
        if (!d.value) continue;
        const po = d.options || {};
        shapes.push({ title, time: d.time, shape: po.shape || o.shape || o.style, location: po.location || o.location,
                      color: po.color || o.color || undefined, text: o.text, char: po.char || o.char, size: o.size });
      }
      continue;
    }
    plotsMeta[title] = o;
    plots[title] = tail(data, since).map((d) => {
      const pt = { time: d.time, value: Number.isFinite(d.value) ? d.value : null };
      if (d.options && d.options.color) pt.color = d.options.color;
      return pt;
    });
  }
  const st = ctx.strategy || (ctx.fullContext && ctx.fullContext.strategy) || null;
  const strategy = st ? { closedtrades: strip(st.closedtrades || []), opentrades: strip(st.opentrades || []),
                          netprofit: st.netprofit, equity: st.equity, max_drawdown: st.max_drawdown } : null;
  const warn = new Set(warnings);
  for (const w of ctx.warnings || []) warn.add(String(w.message || w));
  return { type: 'result', full, firstMs: ctx.marketData && ctx.marketData.length ? ctx.marketData[0].openTime : store[0].ms,
           kind: meta.kind, title: meta.title, overlay: meta.overlay, inputsMeta: meta.inputsMeta,
           plots, plotsMeta, shapes, ...draw, strategy, warnings: [...warn].slice(0, 20) };
}
