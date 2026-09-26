/* Homebase Charts — the page. One websocket to the chart service (:8852);
   each grid cell is a Cell that subscribes one (root, bar type, studies)
   stream. The server computes everything (bars, footprint, studies,
   profile); this file only draws. Bar times arrive as ET wall-clock
   seconds, so the axis reads ET. Tick/volume/range bars sit on an evenly
   spaced synthetic axis (many can share one second) and are labelled with
   their real times. */
(() => {
'use strict';
const LW = window.LightweightCharts;
const { Footprint, Profile, Gaps } = window.HBLayers;
const FAKE0 = 946684800;
const GRIDS = { 1: [1, 1], 2: [2, 1], 4: [2, 2], 6: [3, 2] };
const ST0 = { vwap: true, vwapAnchor: 'eth', vwapBands: false, ema1: 0, ema2: 0, sma: 0, vwma: 0,
  levels: true, volume: true, delta: false, cumdelta: false, adx: 0,
  footprint: true, imbalance: 3, profile: false, bigMin: 0 };
const CELLS0 = [['NQ', 'time:60'], ['NQ', 'time:300'], ['ES', 'time:60'], ['YM', 'time:60'],
  ['NQ', 'tick:1000'], ['NQ', 'time:900']].map(([root, spec]) => ({ root, spec, st: { ...ST0 } }));
const FORM = [
  ['vwap', 'VWAP', 'check'], ['vwapAnchor', 'VWAP anchor', 'select', ['eth', 'rth']], ['vwapBands', 'VWAP 1σ / 2σ bands', 'check'],
  ['ema1', 'EMA', 'num'], ['ema2', 'EMA', 'num'], ['sma', 'SMA', 'num'], ['vwma', 'VWMA', 'num'],
  ['levels', 'Session levels', 'check'], ['volume', 'Volume', 'check'], ['delta', 'Delta', 'check'],
  ['cumdelta', 'Cum. delta', 'check'], ['adx', 'ADX', 'num'], ['footprint', 'Footprint', 'check'],
  ['imbalance', 'Imbalance ×', 'num'], ['profile', 'Volume profile', 'check'], ['bigMin', 'Big prints ≥', 'num'],
];
const LEVELS = [['pdh', 'PDH'], ['pdl', 'PDL'], ['pdc', 'PDC'], ['onh', 'ONH'], ['onl', 'ONL'], ['rth_open', 'Open']];

let meta = { roots: ['NQ'], timeframes: [['1m', 'time:60']] };
let ws = null;
let layout = { grid: 4, cells: CELLS0.map((c) => JSON.parse(JSON.stringify(c))) };
const cells = new Map();
let nextId = 1;

const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
const iso = (t) => new Date(t * 1000).toISOString();

function palette() {
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  return dark
    ? { bg: '#0a0a0a', text: '#a1a1aa', grid: '#1c1c1f', up: '#22c55e', down: '#ef4444',
        upA: 'rgba(34,197,94,.5)', downA: 'rgba(239,68,68,.5)', lines: ['#60a5fa', '#f59e0b', '#c084fc', '#2dd4bf'],
        vwap: '#e879f9', band: 'rgba(232,121,249,.45)', level: '#94a3b8', fpText: '#d4d4d8', fpBg: 'rgba(255,255,255,.06)',
        poc: '#fbbf24', va: 'rgba(96,165,250,.14)', vaIn: 'rgba(96,165,250,.30)', gap: 'rgba(148,163,184,.16)' }
    : { bg: '#ffffff', text: '#52525b', grid: '#f1f1f3', up: '#16a34a', down: '#dc2626',
        upA: 'rgba(22,163,74,.45)', downA: 'rgba(220,38,38,.45)', lines: ['#2563eb', '#d97706', '#9333ea', '#0d9488'],
        vwap: '#c026d3', band: 'rgba(192,38,211,.4)', level: '#64748b', fpText: '#27272a', fpBg: 'rgba(0,0,0,.05)',
        poc: '#d97706', va: 'rgba(37,99,235,.10)', vaIn: 'rgba(37,99,235,.22)', gap: 'rgba(100,116,139,.14)' };
}

function studyKeys(st) {
  const k = [];
  if (st.vwap) k.push(st.vwapAnchor === 'rth' ? 'vwap:rth' : 'vwap');
  for (const [f, name] of [['ema1', 'ema'], ['ema2', 'ema'], ['sma', 'sma'], ['vwma', 'vwma']]) if (+st[f] > 0) k.push(`${name}:${+st[f]}`);
  if (st.levels) k.push('levels');
  if (st.cumdelta) k.push('cumdelta');
  if (+st.adx > 0) k.push(`adx:${+st.adx}`);
  if (st.profile) k.push('profile');
  return [...new Set(k)];
}

class Cell {
  constructor(el, cfg) {
    this.el = el; this.cfg = cfg; this.id = 'c' + (nextId++); cells.set(this.id, this);
    this.bars = []; this.devel = false; this.chart = null; this.sessions = [];
    this.el.innerHTML = `
      <div class="cell-bar">
        <select class="root"></select><select class="spec"></select>
        <input class="custom" size="9" placeholder="tick:750" title="Custom bar type: time:SECONDS, tick:TRADES, volume:CONTRACTS, range:TICKS">
        <span class="spacer"></span>
        <span class="approx pill idle" hidden title="Part of this history has no bid/ask: the buy/sell split there is by tick rule">≈ flow</span>
        <button class="btn btn-outline btn-sm st-btn" type="button">Studies</button>
      </div>
      <div class="cell-chart"><div class="legend"></div><div class="cell-msg">connecting…</div></div>
      <div class="studies-pop"></div>`;
    this.fillControls();
    this.subscribe();
  }

  isTime() { return this.cfg.spec.startsWith('time:'); }

  fillControls() {
    const root = $('.root', this.el), spec = $('.spec', this.el), custom = $('.custom', this.el);
    root.innerHTML = meta.roots.map((r) => `<option ${r === this.cfg.root ? 'selected' : ''}>${esc(r)}</option>`).join('');
    const known = meta.timeframes.some(([, v]) => v === this.cfg.spec);
    spec.innerHTML = meta.timeframes.map(([l, v]) => `<option value="${esc(v)}" ${v === this.cfg.spec ? 'selected' : ''}>${esc(l)}</option>`).join('')
      + (known ? '' : `<option value="${esc(this.cfg.spec)}" selected>${esc(this.cfg.spec)}</option>`);
    root.onchange = () => { this.cfg.root = root.value; this.changed(); };
    spec.onchange = () => { this.cfg.spec = spec.value; this.changed(); };
    custom.onkeydown = (e) => {
      if (e.key !== 'Enter' || !custom.value.trim()) return;
      this.cfg.spec = custom.value.trim(); custom.value = ''; this.fillControls(); this.changed();
    };
    const pop = $('.studies-pop', this.el);
    pop.innerHTML = FORM.map(([k, label, kind, opts]) => {
      const v = this.cfg.st[k];
      if (kind === 'check') return `<label><input type="checkbox" data-k="${k}" ${v ? 'checked' : ''}> ${label}</label>`;
      if (kind === 'num') return `<label>${label} <input type="number" min="0" data-k="${k}" value="${+v || 0}"> <small>0 = off</small></label>`;
      return `<label>${label} <select data-k="${k}">${opts.map((o) => `<option ${o === v ? 'selected' : ''}>${o}</option>`).join('')}</select></label>`;
    }).join('');
    pop.onchange = (e) => {
      const k = e.target.dataset.k; if (!k) return;
      this.cfg.st[k] = e.target.type === 'checkbox' ? e.target.checked : (e.target.type === 'number' ? +e.target.value : e.target.value);
      this.changed();
    };
    $('.st-btn', this.el).onclick = () => pop.classList.toggle('open');
  }

  changed() { saveLast(); this.subscribe(); }

  msg(text) { const m = $('.cell-msg', this.el); m.textContent = text || ''; m.hidden = !text; }

  subscribe() {
    if (!ws || ws.readyState !== 1) return;
    this.msg('loading…');
    ws.send(JSON.stringify({ op: 'sub', id: this.id, root: this.cfg.root, spec: this.cfg.spec,
      studies: studyKeys(this.cfg.st), fp: true }));
  }

  destroy() {
    if (ws && ws.readyState === 1) ws.send(JSON.stringify({ op: 'unsub', id: this.id }));
    if (this.chart) this.chart.remove();
    this.chart = this.candles = this.fp = null;   // so a stale async callback can tell this cell is gone
    cells.delete(this.id);
  }

  real(tt) { return this.isTime() ? tt : (this.realT.get(tt) ?? tt); }
  fullTime(tt) { return iso(this.real(tt)).slice(0, 19).replace('T', ' ') + ' ET'; }
  specLabel() { const t = meta.timeframes.find(([, v]) => v === this.cfg.spec); return t ? t[0] : this.cfg.spec; }

  makeChart() {
    if (this.chart) this.chart.remove();
    const P = this.P = palette(), box = $('.cell-chart', this.el);
    const sub = this.isTime() && +this.cfg.spec.split(':')[1] < 60;
    this.chart = LW.createChart(box, {
      autoSize: true,
      layout: { background: { type: 'solid', color: P.bg }, textColor: P.text, fontSize: 11,
        panes: { separatorColor: P.grid, enableResize: true } },
      grid: { vertLines: { color: P.grid }, horzLines: { color: P.grid } },
      rightPriceScale: { borderColor: P.grid },
      timeScale: { borderColor: P.grid, timeVisible: true, secondsVisible: sub,
        tickMarkFormatter: (t, type) => { const s = iso(this.real(t)); return type <= 2 ? s.slice(5, 10) : (type === 4 ? s.slice(11, 19) : s.slice(11, 16)); } },
      localization: { timeFormatter: (t) => this.fullTime(t) },
      crosshair: { mode: LW.CrosshairMode.Normal },
    });
    this.candles = this.chart.addSeries(LW.CandlestickSeries, { upColor: P.up, downColor: P.down,
      wickUpColor: P.up, wickDownColor: P.down, borderVisible: false });
    this.markers = LW.createSeriesMarkers(this.candles, []);
    this.fp = new Footprint(P); this.prof = new Profile(P); this.gaps = new Gaps(P);
    const fp = this.fp;   // pin the instance this callback was made for
    this.fp.onReadableChange = (on) => {   // fired async from Footprint.updateAllViews(), post-layout
      if (this.fp !== fp || !this.chart) return;   // stale: this cell moved on to a different chart/footprint
      this.fpShown = on;       // footprint visible: hide candle bodies, keep the wicks
      this.candles.applyOptions(on ? { upColor: 'rgba(0,0,0,0)', downColor: 'rgba(0,0,0,0)' } : { upColor: this.P.up, downColor: this.P.down });
    };
    for (const l of [this.gaps, this.prof, this.fp]) this.candles.attachPrimitive(l);
    this.series = {}; this.levelLines = {}; this.paneOf = {}; this.panes = 0; this.fpShown = false;
    this.chart.timeScale().subscribeVisibleLogicalRangeChange(() => this.syncFootprint());
    this.chart.subscribeCrosshairMove((p) => this.legend(p && p.logical != null ? Math.round(p.logical) : null));
  }

  pane(name) { if (!(name in this.paneOf)) this.paneOf[name] = ++this.panes; return this.paneOf[name]; }

  line(key, color, width = 1, pane = 0, style = 0) {
    const s = this.chart.addSeries(LW.LineSeries, { color, lineWidth: width, lineStyle: style,
      priceLineVisible: false, lastValueVisible: pane > 0, crosshairMarkerVisible: false }, pane);
    this.series[key] = s; return s;
  }

  append(b) {
    const last = this.bars[this.bars.length - 1];
    b.tt = this.isTime() ? b.t : FAKE0 + this.bars.length * 60;
    if (last && b.tt <= last.tt) b.tt = last.tt + 1;
    if (!this.isTime()) this.realT.set(b.tt, b.t);
    this.bars.push(b);
  }

  replaceLast(b) {
    const i = this.bars.length - 1;
    b.tt = this.bars[i].tt;
    if (!this.isTime()) this.realT.set(b.tt, b.t);
    this.bars[i] = b;
  }

  candle(b) { return { time: b.tt, open: b.o, high: b.h, low: b.l, close: b.c }; }

  point(key, b) {
    const P = this.P, time = b.tt;
    if (key === '__vol') return { time, value: b.v, color: b.d >= 0 ? P.upA : P.downA };
    if (key === '__delta') return { time, value: b.d, color: b.d >= 0 ? P.upA : P.downA };
    const [base, part] = key.split('#');
    const v = b.sv ? b.sv[base] : null;
    if (v == null) return { time };
    if (typeof v === 'number') return { time, value: v };
    if (base.startsWith('vwap')) {
      if (v.vwap == null) return { time };
      return { time, value: v.vwap + ({ u1: 1, l1: -1, u2: 2, l2: -2 }[part] || 0) * v.sd };
    }
    if (base.startsWith('adx')) { const x = part === 'p' ? v.pdi : part === 'm' ? v.mdi : v.adx; return x == null ? { time } : { time, value: x }; }
    return { time };
  }

  onHistory(m) {
    this.makeChart();
    this.tick = m.tick_size; this.sessions = m.sessions || [];
    this.bars = []; this.realT = new Map(); this.devel = !!m.live;
    m.bars.forEach((b, i) => { b.sv = {}; for (const k in m.studies) b.sv[k] = m.studies[k][i]; this.append(b); });
    this.candles.setData(this.bars.map((b) => this.candle(b)));
    const st = this.cfg.st;
    if (st.volume) this.series.__vol = this.chart.addSeries(LW.HistogramSeries, { priceFormat: { type: 'volume' }, priceLineVisible: false, lastValueVisible: false }, this.pane('volume'));
    if (st.delta) this.series.__delta = this.chart.addSeries(LW.HistogramSeries, { priceLineVisible: false }, this.pane('delta'));
    this.addStudySeries(Object.keys(m.studies || {}));
    this.redrawAll();
    for (const [name, idx] of Object.entries(this.paneOf)) { const pane = this.chart.panes()[idx]; if (pane) pane.setHeight(name === 'volume' ? 70 : 90); }
    $('.approx', this.el).hidden = !this.sessions.some((s) => s.approx);
    this.prof.set(m.profile, this.tick);
    this.msg('');
    this.chart.timeScale().scrollToRealTime();
    this.legend(null);
  }

  addStudySeries(keys) {
    const P = this.P, st = this.cfg.st;
    let ci = 0;
    for (const key of keys) {
      const name = key.split(':')[0];
      if (name === 'ema' || name === 'sma' || name === 'vwma') this.line(key, P.lines[ci++ % P.lines.length]);
      else if (name === 'vwap') {
        this.line(key, P.vwap, 2);
        if (st.vwapBands) for (const b of ['u1', 'l1', 'u2', 'l2']) this.line(`${key}#${b}`, P.band, 1, 0, 2);
      } else if (name === 'cumdelta') this.line(key, P.lines[1], 1, this.pane('cumdelta'));
      else if (name === 'adx') {
        const p = this.pane('adx');
        this.line(key, P.text, 2, p); this.line(`${key}#p`, P.up, 1, p); this.line(`${key}#m`, P.down, 1, p);
      }
    }
  }

  redrawAll() {
    for (const [key, s] of Object.entries(this.series)) s.setData(this.bars.map((b) => this.point(key, b)));
    this.drawMarkers(); this.drawLevels(); this.drawGaps(); this.syncFootprint();
  }

  onUpdate(m) {
    if (!this.chart) return;
    const touched = [];
    const vals = (i, live) => { const o = {}; for (const k in m.studies) o[k] = live ? m.studies[k].live : m.studies[k].closed[i]; return o; };
    m.closed.forEach((b, i) => { b.sv = vals(i, false); if (i === 0 && this.devel) this.replaceLast(b); else this.append(b); touched.push(b); });
    if (m.live) { m.live.sv = vals(0, true); if (!m.closed.length && this.devel) this.replaceLast(m.live); else this.append(m.live); touched.push(m.live); }
    this.devel = !!m.live;
    for (const b of touched) {
      this.candles.update(this.candle(b));
      for (const [key, s] of Object.entries(this.series)) s.update(this.point(key, b));
    }
    if (m.profile !== undefined) this.prof.set(m.profile, this.tick);
    if (touched.some((b) => b.big && b.big.length)) this.drawMarkers();
    this.drawLevels(); this.syncFootprint();
    this.legend(null);
  }

  drawMarkers() {
    const min = +this.cfg.st.bigMin || 0, P = this.P;
    if (!min) { this.markers.setMarkers([]); return; }
    const out = [];
    for (const b of this.bars) for (const [, , size, side] of (b.big || [])) {
      if (size >= min) out.push({ time: b.tt, position: side > 0 ? 'belowBar' : 'aboveBar',
        color: side > 0 ? P.up : P.down, shape: 'circle', size: 0.6, text: String(size) });
    }
    this.markers.setMarkers(out.slice(-600));
  }

  drawLevels() {
    const last = this.bars[this.bars.length - 1], lv = last && last.sv ? last.sv.levels : null;
    for (const [k, title] of LEVELS) {
      const px = lv ? lv[k] : null, cur = this.levelLines[k];
      if (px == null) { if (cur) { this.candles.removePriceLine(cur); delete this.levelLines[k]; } continue; }
      if (cur) { if (cur.options().price !== px) cur.applyOptions({ price: px }); continue; }
      this.levelLines[k] = this.candles.createPriceLine({ price: px, color: this.P.level, lineWidth: 1,
        lineStyle: LW.LineStyle.Dashed, axisLabelVisible: true, title });
    }
  }

  drawGaps() {}                // Task 13
  syncFootprint() {
    if (!this.fp) return;
    this.fp.set(this.bars, !!this.cfg.st.footprint, +this.cfg.st.imbalance || 0, this.tick);
    // readability (and the candle-hide toggle) is decided by the layer itself,
    // at render time, via onReadableChange -- see makeChart().
  }

  legend(i) {
    const el = $('.legend', this.el);
    const b = i == null ? this.bars[this.bars.length - 1] : this.bars[Math.max(0, Math.min(i, this.bars.length - 1))];
    if (!b) { el.textContent = ''; return; }
    el.textContent = `${this.cfg.root} ${this.specLabel()}  ${this.fullTime(b.tt)}  O ${b.o}  H ${b.h}  L ${b.l}  C ${b.c}  V ${b.v}  Δ ${b.d > 0 ? '+' : ''}${b.d}`;
  }
}

function buildGrid() {
  for (const c of [...cells.values()]) c.destroy();
  const grid = $('#grid'), [cols, rows] = GRIDS[layout.grid] || GRIDS[4];
  grid.style.gridTemplateColumns = `repeat(${cols}, minmax(0, 1fr))`;
  grid.style.gridTemplateRows = `repeat(${rows}, minmax(0, 1fr))`;
  grid.innerHTML = '';
  while (layout.cells.length < cols * rows) {
    const c = CELLS0[layout.cells.length % CELLS0.length];
    layout.cells.push({ root: c.root, spec: c.spec, st: { ...ST0 } });
  }
  for (let i = 0; i < cols * rows; i++) {
    const el = document.createElement('div'); el.className = 'cell'; grid.appendChild(el);
    layout.cells[i].st = { ...ST0, ...(layout.cells[i].st || {}) };
    new Cell(el, layout.cells[i]);
  }
  $('#gridSel').value = String(layout.grid);
}

function showStatus() {}         // Task 13
function loadLayouts() {}        // Task 13
function saveLayout() {}         // Task 13
function saveLast() { try { localStorage.setItem('hb_charts_last', JSON.stringify(layout)); } catch (_) {} }
function loadLast() { try { const v = JSON.parse(localStorage.getItem('hb_charts_last') || 'null'); if (v && Array.isArray(v.cells)) layout = v; } catch (_) {} }

function connect() {
  ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`);
  ws.onopen = () => { for (const c of cells.values()) c.subscribe(); };
  ws.onmessage = (e) => {
    const m = JSON.parse(e.data);
    if (m.type === 'status') { showStatus(m); return; }
    const c = cells.get(m.id); if (!c) return;
    if (m.type === 'history') c.onHistory(m);
    else if (m.type === 'update') c.onUpdate(m);
    else if (m.type === 'reset') c.subscribe();
    else if (m.type === 'error') c.msg(m.error);
  };
  ws.onclose = () => { showStatus({ connected: false, error: 'chart service unreachable — retrying' }); setTimeout(connect, 2000); };
}

async function init() {
  $('#navDesk').href = `${location.protocol}//${location.hostname}:8850/`;
  try { const r = await fetch('/api/symbols'); if (r.ok) meta = await r.json(); } catch (_) {}
  loadLast();
  $('#gridSel').onchange = (e) => { layout.grid = +e.target.value; saveLast(); buildGrid(); };
  $('#saveLayout').onclick = () => saveLayout();
  $('#themeToggle').onclick = () => {
    const next = document.documentElement.getAttribute('data-theme') === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    try { localStorage.setItem('hb_theme', next); } catch (_) {}
    for (const c of cells.values()) c.subscribe();
  };
  buildGrid(); loadLayouts(); connect();
}

window.HBCharts = { Cell, cells, palette, studyKeys, LEVELS, get layout() { return layout; }, set layout(v) { layout = v; },
  buildGrid, saveLast, get ws() { return ws; } };
init();
})();
