/* Homebase Charts — one chart panel (HBCell.Cell): Lightweight Charts in the
   TradingView-style palette, series built from the chart's indicator
   instances (HBCatalog), the DOM legend, the watermark, and the
   history/update handling. The page (app.js) owns the websocket, the toolbar
   and selection, and gives each cell a `host`:
     {id, send(msg) -> bool, onPick(cell), onLoaded(cell), onRefused(cell, tried, text), onSettings(cell, uid),
      onPosition(cell, d), changed(), tool(), toolDone(), drawings, magnet()}   (the last four: the drawing tools,
      HBDrawings.Controller)
   Bar times arrive as ET wall-clock seconds, so the axis reads ET; tick,
   volume and range bars sit on an evenly spaced synthetic axis (many can
   share a second) and are labelled with their real times. */
(() => {
'use strict';
const LW = window.LightweightCharts;
const C = window.HBCatalog;
const { Footprint, Profile, Gaps } = window.HBLayers;
const FAKE0 = 946684800;    // synthetic-axis origin for tick/volume/range bars
const FONT = '-apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif';
const LEVELS = [['pdh', 'PDH'], ['pdl', 'PDL'], ['pdc', 'PDC'], ['onh', 'ONH'], ['onl', 'ONL'], ['rth_open', 'Open']];
const PANE_H = 90;          // px: the delta / cumulative delta / ADX panes
const WHOLE = { type: 'price', precision: 0, minMove: 1 };   // contract counts: -25, not -25.00
const NOTE_MS = 8000;       // a refused change's reason stays this long in the legend
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const DAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const clone = (x) => JSON.parse(JSON.stringify(x));

/* The chart canvas colours: charts.css's tokens for the current theme. */
function palette() {
  const dark = document.documentElement.getAttribute('data-theme') === 'dark';
  const P = { up: '#089981', down: '#F23645', upA: 'rgba(8,153,129,.5)', downA: 'rgba(242,54,69,.5)', accent: '#2962FF',
    lines: C.LINE_COLORS, vwap: '#9C27B0', band: 'rgba(156,39,176,.45)', cum: '#FF6D00', poc: '#F7A600',
    gap: 'rgba(120,123,134,.14)', cross: '#9598A1', crossLabel: '#131722',
    handleFill: '#FFFFFF', onAccent: '#FFFFFF',   // drawing handles: white dots in both themes; text on accent / down fills
    profitZone: 'rgba(8,153,129,.20)', lossZone: 'rgba(242,54,69,.20)' };
  return Object.assign(P, dark
    ? { bg: '#0F0F0F', text: '#DBDBDB', text2: '#8C8C8C', grid: '#1C1C1C', border: '#2E2E2E', accentSoft: 'rgba(41,98,255,.20)',
        downSoft: 'rgba(242,54,69,.18)', watermark: 'rgba(219,219,219,.06)', level: '#8C8C8C', fpText: '#DBDBDB',
        fpBg: 'rgba(255,255,255,.06)', va: 'rgba(41,98,255,.20)', vaIn: 'rgba(41,98,255,.40)' }
    : { bg: '#FFFFFF', text: '#0F0F0F', text2: '#787B86', grid: '#F0F3FA', border: '#E0E3EB', accentSoft: 'rgba(41,98,255,.10)',
        downSoft: 'rgba(242,54,69,.10)', watermark: 'rgba(15,15,15,.06)', level: '#787B86', fpText: '#0F0F0F',
        fpBg: 'rgba(15,15,15,.05)', va: 'rgba(41,98,255,.10)', vaIn: 'rgba(41,98,255,.28)' });
}

function mk(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text != null) e.textContent = text;
  return e;
}
function val(text, color) { const s = mk('span', 'v', text); s.style.color = color; return s; }
function kv(k, v, color) { const s = mk('span', 'kv'); s.append(mk('span', 'k', k), val(v, color)); return s; }
function iconButton(name, title, act) {
  const b = mk('button', 'ib');
  b.type = 'button';
  b.title = title;
  b.dataset.act = act;
  b.setAttribute('aria-label', title);
  b.innerHTML = window.HBIcons[name] || '';   // our own static SVG strings
  return b;
}

/* Time-axis labels like TradingView's: year, month name, day of month, HH:MM(:SS). */
function tickLabel(t, type) {
  const d = new Date(t * 1000);
  if (type === 0) return String(d.getUTCFullYear());
  if (type === 1) return MONTHS[d.getUTCMonth()];
  if (type === 2) return String(d.getUTCDate());
  return d.toISOString().slice(11, type === 4 ? 19 : 16);
}

class Cell {
  constructor(slot, cfg, host) {
    this.el = slot; this.cfg = cfg; this.host = host; this.id = host.id;
    this.chart = null; this.candles = null; this.markers = null; this.P = null;
    this.bars = []; this.realT = new Map(); this.devel = false; this.sessions = []; this.tick = 0.25;
    this.pv = null;   // USD per 1.00 of price for one contract (the history's point_value; null: unknown)
    this.profile = null; this.keys = new Set(); this.lines = []; this.rows = []; this.colorOf = {}; this.levelLines = {};
    this.shown = null;      // {root, spec} of the bars on screen
    this.lastGood = null;   // the config the server last answered with a history
    this.inflight = [];     // subs sent, not answered yet, oldest first: {cfg, view}; the server answers each once, in order
    this.hover = null;      // bar index under the crosshair (null: the last bar)
    this.noteTimer = 0; this.noteOn = false;   // noteOn: the legend message is still a note()
    this.dc = null;   // the drawing controller of the current chart
    this.magnetXhair = false;   // the rail's magnet is on with a tool picked (MagnetOHLC crosshair)
    slot.className = 'panel';
    slot.innerHTML = `
      <div class="chart"></div>
      <div class="legend">
        <div class="lg-title"><span class="lg-name"></span><span class="badge" hidden>approx. flow</span><span class="lg-msg" role="status"></span></div>
        <div class="lg-ohlc"></div>
        <div class="lg-inds"></div>
      </div>`;
    this.box = slot.querySelector('.chart');
    this.lg = { name: slot.querySelector('.lg-name'), badge: slot.querySelector('.badge'), msg: slot.querySelector('.lg-msg'),
      ohlc: slot.querySelector('.lg-ohlc'), inds: slot.querySelector('.lg-inds') };
    this.lg.badge.title = 'Part of this history has no bid/ask: buys and sells there are split by the tick rule';
    slot.addEventListener('pointerdown', () => host.onPick(this), true);
    this.lg.inds.addEventListener('click', (e) => this.onLegendClick(e));
    this.title();
    this.subscribe();
  }

  cfgNow() { return clone({ root: this.cfg.root, spec: this.cfg.spec, indicators: this.cfg.indicators }); }
  spec() { return (this.shown || this.cfg).spec; }
  isTime() { return this.spec().startsWith('time:'); }
  barMs() { const s = C.parseSpec(this.spec()); return s && s.kind === 'time' ? s.n * 1000 : 0; }
  real(tt) { return this.isTime() ? tt : (this.realT.get(tt) ?? tt); }

  /* The crosshair's time label, e.g. "Tue 22 Sep '26  09:31". */
  fullTime(tt) {
    const d = new Date(this.real(tt) * 1000), s = d.toISOString(), ms = this.barMs();
    const day = `${DAYS[d.getUTCDay()]} ${d.getUTCDate()} ${MONTHS[d.getUTCMonth()]} '${s.slice(2, 4)}`;
    if (ms >= 86400000) return day;
    return `${day}  ${s.slice(11, ms >= 60000 ? 16 : 19)}`;
  }

  title() {
    const { root, spec } = this.cfg;
    this.lg.name.textContent = [root, C.rootName(root), C.specLabel(spec)].filter(Boolean).join(' · ');
  }
  message(text, err = false) { this.noteOn = false; this.lg.msg.textContent = text || ''; this.lg.msg.classList.toggle('err', !!err); }
  note(text) {   // a refused change: its reason in red for a while (then cleared, if nothing replaced it)
    this.message(text, true);
    this.noteOn = true;
    clearTimeout(this.noteTimer);
    this.noteTimer = setTimeout(() => { if (this.noteOn) this.message(''); }, NOTE_MS);
  }
  setSelected(on) { this.el.classList.toggle('selected', on); }

  /* The rail's magnet with a drawing tool picked, on the selected chart: the crosshair snaps to O/H/L/C too
     (when this Lightweight Charts has MagnetOHLC); otherwise the normal crosshair. Kept across rebuilds. */
  setMagnetCrosshair(on) {
    const m = !!on && LW.CrosshairMode.MagnetOHLC !== undefined;
    if (this.magnetXhair === m) return;
    this.magnetXhair = m;
    if (this.chart) this.chart.applyOptions({ crosshair: { mode: m ? LW.CrosshairMode.MagnetOHLC : LW.CrosshairMode.Normal } });
  }

  /* Send the chart's config; keepView: restore the view on screen when the
     answer is for the same root + interval. "Loading…" while it asks for
     another root or interval than the bars on screen. */
  subscribe(keepView = false) {
    const cfg = this.cfgNow(), view = keepView && this.chart ? this.viewNow() : null;
    if (!this.host.send({ op: 'sub', id: this.id, root: cfg.root, spec: cfg.spec, studies: C.serverKeys(cfg.indicators), fp: true })) return;
    this.inflight.push({ cfg, view });
    const s = this.shown;
    if (!s || s.root !== cfg.root || s.spec !== cfg.spec) this.message('Loading…');
  }

  /* The socket (re)opened: nothing sent on the old one will be answered. */
  clearInflight() { this.inflight = []; }

  /* A change from the toolbar or a dialog. A new symbol or interval reloads
     the chart at the latest bar; indicator changes rebuild it in place and
     resubscribe (keeping the view) only when they need a study the stream
     does not carry yet, or when a sub is still in flight (its answer would
     otherwise land on top of this change). */
  update(patch) {
    const was = this.shown;
    Object.assign(this.cfg, patch);
    this.title();
    this.host.changed();
    const same = !!was && was.root === this.cfg.root && was.spec === this.cfg.spec;
    if (same && this.chart && !this.inflight.length && C.serverKeys(this.cfg.indicators).every((k) => this.keys.has(k))) {
      this.lastGood = this.cfgNow();
      this.restyle();
      return;
    }
    this.subscribe(same);
  }

  /* The answer to the oldest sub in flight. Only the answer to the newest
     one is drawn: an older one just records what the server accepted. */
  onHistory(m) {
    const entry = this.inflight.shift();
    if (entry) this.lastGood = entry.cfg;
    if (this.inflight.length) return;
    const s = this.shown, view = entry && entry.view && s && s.root === m.root && s.spec === m.spec ? entry.view : null;
    this.shown = { root: m.root, spec: m.spec };
    this.tick = m.tick_size; this.pv = m.point_value ?? null; this.sessions = m.sessions || []; this.devel = !!m.live;
    this.keys = new Set(Object.keys(m.studies || {}));
    this.profile = m.profile || null;
    this.bars = []; this.realT = new Map();
    m.bars.forEach((b, i) => { b.sv = {}; for (const k in m.studies) b.sv[k] = m.studies[k][i]; this.append(b); });
    this.build(view);
    if (!this.noteOn) this.message('');
    this.host.onLoaded(this);
  }

  /* The server refused the oldest sub in flight. If a newer one is on its
     way, that one supersedes it: only say why. Else the chart goes back to
     the last config the server accepted (resubscribed: a refusal can drop
     the old stream) and the page shows why; with none accepted yet, the
     reason stays in the legend. */
  onError(text) {
    const entry = this.inflight.shift(), tried = entry ? entry.cfg : null;
    if (this.inflight.length) { this.note(text); return; }
    if (tried && this.lastGood && JSON.stringify(tried) !== JSON.stringify(this.lastGood)) {
      Object.assign(this.cfg, clone(this.lastGood));
      this.title();
      this.host.changed();
      this.subscribe(true);
      this.host.onRefused(this, tried, text);   // after subscribe(): the reason replaces its "Loading…"
      return;
    }
    this.message(text, true);
  }

  build(view) {
    const sel = this.dc && this.shown && this.dc.root === this.shown.root ? this.dc.sel : null;
    this.makeChart();
    this.candles.setData(this.bars.map((b) => this.candle(b)));
    this.buildSeries();
    for (const l of this.lines) l.s.setData(this.bars.map((b) => this.point(l, b)));
    this.drawMarkers(); this.drawLevels(); this.drawGaps(); this.syncFootprint(); this.syncProfile();
    // Pane heights as px-sized stretch factors. Not setHeight(): it spreads each change using the laid-out
    // heights, and panes added this pass are still 0 px, so with 2+ sub-panes only the last one got PANE_H.
    // Pane 0 still holds the whole plot here; on a small panel it keeps at least half of it.
    const panes = this.chart.panes(), subs = panes.length - 1;
    if (subs) {
      panes[0].setStretchFactor(Math.max(panes[0].getHeight() - subs * PANE_H, subs * PANE_H));
      for (let i = 1; i <= subs; i++) panes[i].setStretchFactor(PANE_H);
    }
    if (view) this.setView(view); else this.chart.timeScale().scrollToRealTime();
    this.lg.badge.hidden = !this.sessions.some((s) => s.approx);
    this.legendRows();
    this.legend(null);
    this.dc = new window.HBDrawings.Controller(this, this.host);
    if (sel) { this.dc.sel = sel; this.dc.refresh(); }
  }

  restyle() { if (this.chart) this.build(this.viewNow()); }

  /* The visible range counted from the last bar, so it survives new bars. */
  viewNow() {
    const r = this.chart && this.chart.timeScale().getVisibleLogicalRange();
    return r ? { fromEnd: this.bars.length - r.from, toEnd: this.bars.length - r.to } : null;
  }
  setView(v) {
    const n = this.bars.length;
    this.chart.timeScale().setVisibleLogicalRange({ from: n - v.fromEnd, to: n - v.toEnd });
  }

  makeChart() {
    this.teardown();
    const P = this.P = palette(), sub = this.isTime() && this.barMs() < 60000;
    this.chart = LW.createChart(this.box, {
      autoSize: true,
      layout: { background: { type: 'solid', color: P.bg }, textColor: P.text2, fontSize: 12, fontFamily: FONT,
        attributionLogo: false,   // the credit lives once in the bottom bar
        panes: { separatorColor: P.border, separatorHoverColor: P.accentSoft, enableResize: true } },
      grid: { vertLines: { color: P.grid }, horzLines: { color: P.grid } },
      rightPriceScale: { borderColor: P.border, scaleMargins: { top: 0.1, bottom: 0.15 } },
      timeScale: { borderColor: P.border, timeVisible: true, secondsVisible: sub, rightOffset: 6,
        tickMarkFormatter: (t, type) => tickLabel(this.real(t), type) },
      localization: { timeFormatter: (t) => this.fullTime(t) },
      crosshair: { mode: this.magnetXhair ? LW.CrosshairMode.MagnetOHLC : LW.CrosshairMode.Normal,
        vertLine: { color: P.cross, width: 1, style: LW.LineStyle.Dashed, labelBackgroundColor: P.crossLabel },
        horzLine: { color: P.cross, width: 1, style: LW.LineStyle.Dashed, labelBackgroundColor: P.crossLabel } },
    });
    this.candles = this.chart.addSeries(LW.CandlestickSeries, { upColor: P.up, downColor: P.down, wickUpColor: P.up,
      wickDownColor: P.down, borderVisible: false, priceLineStyle: LW.LineStyle.Dotted,
      priceFormat: { type: 'price', precision: C.decimals(this.tick), minMove: this.tick } });
    this.markers = LW.createSeriesMarkers(this.candles, []);
    LW.createTextWatermark(this.chart.panes()[0], { horzAlign: 'center', vertAlign: 'center',
      lines: [{ text: `${this.shown.root}, ${C.specLabel(this.shown.spec)}`, color: P.watermark, fontSize: 48, fontFamily: FONT }] });
    this.fp = new Footprint(P); this.prof = new Profile(P); this.gaps = new Gaps(P);
    const fp = this.fp;   // pin the instance this callback belongs to
    fp.onReadableChange = (on) => {   // fired async from Footprint.updateAllViews(), after layout
      if (this.fp !== fp || !this.chart) return;
      this.candles.applyOptions(on ? { upColor: 'rgba(0,0,0,0)', downColor: 'rgba(0,0,0,0)' } : { upColor: P.up, downColor: P.down });
    };
    for (const l of [this.gaps, this.prof, this.fp]) this.candles.attachPrimitive(l);
    this.lines = []; this.levelLines = {}; this.colorOf = {}; this.hover = null;
    this.chart.timeScale().subscribeVisibleLogicalRangeChange(() => this.syncFootprint());
    this.chart.subscribeCrosshairMove((p) => {
      this.hover = p && p.logical != null ? Math.round(p.logical) : null;
      this.legend(this.hover);
    });
  }

  teardown() {
    if (this.dc) { this.dc.destroy(); this.dc = null; }
    if (!this.chart) return;
    this.chart.remove();
    this.chart = this.candles = this.markers = this.fp = this.prof = this.gaps = null;   // stale async callbacks can tell
  }

  /* One series per drawn part of each indicator instance, in instance order. */
  buildSeries() {
    const P = this.P;
    let ci = 0, pane = 0;
    const add = (inst, src, part, type, opts, where) => {
      const s = this.chart.addSeries(type, { priceLineVisible: false, visible: inst.visible !== false, ...opts }, where);
      this.lines.push({ uid: inst.uid, s, src, part });
      return s;
    };
    const line = (inst, src, part, color, width, where = 0, extra = {}) => add(inst, src, part, LW.LineSeries,
      { color, lineWidth: width, lastValueVisible: true, crosshairMarkerVisible: false, title: '', ...extra }, where);
    for (const inst of this.cfg.indicators) {
      const k = C.serverKey(inst);
      switch (inst.id) {
        case 'volume':
          add(inst, '__vol', null, LW.HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: 'vol', lastValueVisible: false }, 0)
            .priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
          break;
        case 'vwap':
          this.colorOf[inst.uid] = P.vwap;
          line(inst, k, null, P.vwap, 2);
          if (inst.params.bands) {
            for (const b of ['u1', 'l1', 'u2', 'l2']) line(inst, k, b, P.band, 1, 0, { lineStyle: LW.LineStyle.Dashed, lastValueVisible: false });
          }
          break;
        case 'ema': case 'sma': case 'vwma': {
          const color = P.lines[ci++ % P.lines.length];
          this.colorOf[inst.uid] = color;
          line(inst, k, null, color, 1);
          break;
        }
        case 'adx': {
          const where = ++pane;
          line(inst, k, null, P.text, 2, where); line(inst, k, 'p', P.up, 1, where); line(inst, k, 'm', P.down, 1, where);
          break;
        }
        case 'delta':
          add(inst, '__delta', null, LW.HistogramSeries, { lastValueVisible: true, priceFormat: { ...WHOLE } }, ++pane);
          break;
        case 'cumdelta':
          this.colorOf[inst.uid] = P.cum;
          line(inst, k, null, P.cum, 2, ++pane, { priceFormat: { ...WHOLE } });
          break;
        default:   // levels, footprint, profile, big prints: price lines, layers and markers
          break;
      }
    }
  }

  legendRows() {
    this.rows = this.cfg.indicators.map((inst) => {
      const off = inst.visible === false, row = mk('div', 'lg-row' + (off ? ' off' : '')), vals = mk('span', 'lg-vals');
      const btns = mk('span', 'lg-btns');
      btns.append(iconButton(off ? 'eyeOff' : 'eye', off ? 'Show' : 'Hide', 'eye'));
      if (C.def(inst.id).params.length) btns.append(iconButton('gear', 'Settings', 'gear'));
      btns.append(iconButton('x', 'Remove', 'x'));
      row.dataset.uid = inst.uid;
      row.append(mk('span', 'lg-label', C.label(inst)), vals, btns);
      return { inst, row, vals };
    });
    this.lg.inds.replaceChildren(...this.rows.map((r) => r.row));
  }

  onLegendClick(e) {
    const b = e.target.closest('button[data-act]');
    if (!b) return;
    const uid = b.closest('.lg-row').dataset.uid, inst = this.cfg.indicators.find((x) => x.uid === uid);
    if (!inst) return;
    if (b.dataset.act === 'eye') this.setVisible(uid, inst.visible === false);
    else if (b.dataset.act === 'gear') this.host.onSettings(this, uid);
    else this.update({ indicators: this.cfg.indicators.filter((x) => x.uid !== uid) });
  }

  /* Client-only: the stream keeps computing a hidden study, so the toggle is instant. */
  setVisible(uid, on) {
    const inst = this.cfg.indicators.find((x) => x.uid === uid);
    if (!inst) return;
    inst.visible = on;
    const good = this.lastGood && this.lastGood.indicators.find((x) => x.uid === uid);
    if (good) good.visible = on;   // a later revert must not undo a hide/show
    for (const e of this.inflight) {   // nor may an answer to a subscription already in flight
      const q = e.cfg.indicators.find((x) => x.uid === uid);
      if (q) q.visible = on;
    }
    this.host.changed();
    for (const l of this.lines) if (l.uid === uid) l.s.applyOptions({ visible: on });
    this.drawLevels(); this.drawMarkers(); this.syncFootprint(); this.syncProfile();
    this.legendRows();
    this.legend(this.hover);
  }

  /* The OHLC row and every indicator row for bar i (null: the last bar). */
  legend(i) {
    const n = this.bars.length;
    if (!n || !this.P) { this.lg.ohlc.replaceChildren(); return; }
    const k = i == null ? n - 1 : Math.max(0, Math.min(i, n - 1)), b = this.bars[k], prev = k > 0 ? this.bars[k - 1] : null;
    const P = this.P, col = b.c >= b.o ? P.up : P.down, ch = C.change(b, prev, this.tick);
    this.lg.ohlc.replaceChildren(
      ...[['O', b.o], ['H', b.h], ['L', b.l], ['C', b.c]].map(([key, v]) => kv(key, C.fmtPrice(v, this.tick), col)),
      val(ch.text, ch.up ? P.up : P.down),
      kv('Vol', C.fmtCompact(b.v), col),
      kv('Δ', C.fmtSigned(b.d), b.d >= 0 ? P.up : P.down));
    const colors = { text: P.text, up: P.up, down: P.down, vwap: P.vwap, cum: P.cum };
    for (const r of this.rows) {
      const vs = C.legendValues(r.inst, b, { ...colors, line: this.colorOf[r.inst.uid] || P.accent }, this.tick);
      r.vals.replaceChildren(...vs.map((x) => val(x.text, x.color)));
    }
  }

  /* Ignored while a sub is in flight: the bars on screen may belong to a
     stream this chart is leaving, and the answer's history carries it all. */
  onUpdate(m) {
    if (!this.chart || this.inflight.length) return;
    const touched = [];
    const vals = (i, live) => { const o = {}; for (const k in m.studies) o[k] = live ? m.studies[k].live : m.studies[k].closed[i]; return o; };
    m.closed.forEach((b, i) => { b.sv = vals(i, false); if (i === 0 && this.devel) this.replaceLast(b); else this.append(b); touched.push(b); });
    if (m.live) { m.live.sv = vals(0, true); if (!m.closed.length && this.devel) this.replaceLast(m.live); else this.append(m.live); touched.push(m.live); }
    this.devel = !!m.live;
    for (const b of touched) {
      this.candles.update(this.candle(b));
      for (const l of this.lines) l.s.update(this.point(l, b));
    }
    if (m.profile !== undefined) { this.profile = m.profile; this.syncProfile(); }
    if (touched.some((b) => b.big && b.big.length)) this.drawMarkers();
    this.drawLevels(); this.syncFootprint();
    this.legend(this.hover);
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

  point(l, b) {
    const P = this.P, time = b.tt;
    if (l.src === '__vol') return { time, value: b.v, color: b.d >= 0 ? P.upA : P.downA };
    if (l.src === '__delta') return { time, value: b.d, color: b.d >= 0 ? P.upA : P.downA };
    const v = b.sv ? b.sv[l.src] : null;
    if (v == null) return { time };
    if (typeof v === 'number') return { time, value: v };
    if (l.src.startsWith('vwap')) {
      if (v.vwap == null || (l.part && v.sd == null)) return { time };
      return { time, value: v.vwap + ({ u1: 1, l1: -1, u2: 2, l2: -2 }[l.part] || 0) * (v.sd || 0) };
    }
    if (l.src.startsWith('adx')) {
      const x = l.part === 'p' ? v.pdi : l.part === 'm' ? v.mdi : v.adx;
      return x == null ? { time } : { time, value: x };
    }
    return { time };
  }

  visible(id) { return this.cfg.indicators.filter((x) => x.id === id && x.visible !== false); }

  drawMarkers() {
    if (!this.markers) return;
    const mins = this.visible('bigprints').map((x) => x.params.min), P = this.P;
    if (!mins.length) { this.markers.setMarkers([]); return; }
    const min = Math.min(...mins), out = [];
    for (const b of this.bars) {
      for (const [, , size, side] of (b.big || [])) {
        if (size >= min) out.push({ time: b.tt, position: side > 0 ? 'belowBar' : 'aboveBar',
          color: side > 0 ? P.up : P.down, shape: 'circle', size: 0.6, text: String(size) });
      }
    }
    this.markers.setMarkers(out.slice(-600));
  }

  drawLevels() {
    if (!this.candles) return;
    const last = this.bars[this.bars.length - 1];
    const lv = this.visible('levels').length && last && last.sv ? last.sv.levels : null;
    for (const [k, title] of LEVELS) {
      const px = lv ? lv[k] : null, cur = this.levelLines[k];
      if (px == null) { if (cur) { this.candles.removePriceLine(cur); delete this.levelLines[k]; } continue; }
      if (cur) { if (cur.options().price !== px) cur.applyOptions({ price: px }); continue; }
      this.levelLines[k] = this.candles.createPriceLine({ price: px, color: this.P.level, lineWidth: 1,
        lineStyle: LW.LineStyle.Dashed, axisLabelVisible: true, title });
    }
  }

  drawGaps() {
    const idx = [];
    for (const s of this.sessions) {
      for (const [a] of (s.gaps || [])) {
        let i = -1;
        for (let j = 0; j < this.bars.length && this.bars[j].t <= a; j++) i = j;
        if (i >= 0 && i < this.bars.length - 1) idx.push(i);
      }
    }
    this.gaps.set(idx);
  }

  syncFootprint() {
    if (!this.fp) return;
    const f = this.visible('footprint')[0];
    this.fp.set(this.bars, !!f, f ? f.params.imbalance : 0, this.tick);
  }

  syncProfile() { if (this.prof) this.prof.set(this.visible('profile').length ? this.profile : null, this.tick); }

  destroy() {
    this.host.send({ op: 'unsub', id: this.id });
    clearTimeout(this.noteTimer);
    this.teardown();
  }
}

window.HBCell = { Cell, palette, FONT };
})();
