/* Homebase Charts — one chart panel (HBCell.Cell): Lightweight Charts in the
   TradingView-style palette, series built from the chart's indicator
   instances (HBCatalog), the DOM legend, the watermark, and the
   history/update handling. The page (app.js) owns the websocket, the toolbar
   and selection, and gives each cell a `host`:
     {id, send(msg) -> bool, onPick(cell), onLoaded(cell), onRefused(cell, tried, text), onSettings(cell, uid),
      onPosition(cell, d), onChartMenu(cell, {x, y, price}), onIndicatorMenu(cell, uid, {anchor} | {at}),
      changed(), tool(), toolDone(), drawings, magnet(), events()}   (the drawings/tool/magnet four: the drawing
      tools, HBDrawings.Controller; events(): every stored calendar event; the chart/indicator menus: app.js)
   Bar times arrive as ET wall-clock seconds, so the axis reads ET; tick,
   volume and range bars sit on an evenly spaced synthetic axis (many can
   share a second) and are labelled with their real times.
   Its settings (HBSettings: candle colours, precision, time zone, scales, canvas…) live in `cfg.settings` as
   overrides of the defaults and are applied in place. Indicators that can live in their own pane
   (HBCatalog.placement) are drawn there or on the price pane on an overlay scale of their own. */
(() => {
'use strict';
const LW = window.LightweightCharts;
const C = window.HBCatalog;
const S = window.HBSettings;
const CANDLE_KEYS = ['prevClose', 'body', 'bodyUp', 'bodyDown', 'borders', 'borderUp', 'borderDown', 'wick', 'wickUp', 'wickDown'];
const { Footprint, Profile, Gaps, EthBg, Countdown, EventFlags, Start } = window.HBLayers;
const NO_SCALE = () => null;   // autoscaleInfoProvider: the series takes no part in autoscale
const FAKE0 = 946684800;    // synthetic-axis origin for tick/volume/range bars
const FONT = '-apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif';
const LEVELS = [['pdh', 'PDH'], ['pdl', 'PDL'], ['pdc', 'PDC'], ['onh', 'ONH'], ['onl', 'ONL'], ['rth_open', 'Open']];
const PANE_H = 90;          // px: the delta / cumulative delta / ADX panes
const VOL_TOP = 0.8;    // Volume on the price pane: its bars in the bottom 20%
const MAIN_TOP = 0.75;  // another pane-type indicator on the price pane: the bottom quarter, on its own scale
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
    this.eth = this.cd = null; this.clockEt = null;   // the hours background, the countdown, now (ET wall ms)
    this.evl = null;   // the economic-calendar flags layer
    this.back = new window.HBScrollBack.ScrollBack();   // scroll-back: older history on demand
    this.start = null;   // the "Start of data" / "History limit reached" layer
    this.capped = false;   // this.bars hit the 200,000-bar client cap: scroll-back has stopped asking
    this.paneUid = [null];   // pane index -> the uid of the indicator in its own pane (0: the price pane)
    this.magnetXhair = false;   // the rail's magnet is on with a tool picked (MagnetOHLC crosshair)
    this.R = S.resolve(cfg.settings || {}, palette());   // the chart's settings, concrete for the theme
    this.fpHide = false;   // the footprint is readable: candle bodies and borders step aside
    this.wm = null;        // the watermark (its colour and visibility follow the settings)
    slot.className = 'panel';
    slot.innerHTML = `
      <div class="chart"></div>
      <div class="legend">
        <div class="lg-title"><span class="lg-name"></span><span class="badge" hidden>approx. flow</span><span class="lg-msg" role="status"></span></div>
        <div class="lg-ohlc"></div>
        <div class="lg-inds"></div>
      </div>
      <div class="ev-tip" role="tooltip" hidden></div>`;
    this.box = slot.querySelector('.chart');
    this.evTip = slot.querySelector('.ev-tip');
    this.lg = { name: slot.querySelector('.lg-name'), badge: slot.querySelector('.badge'), msg: slot.querySelector('.lg-msg'),
      ohlc: slot.querySelector('.lg-ohlc'), inds: slot.querySelector('.lg-inds') };
    this.lg.badge.title = 'Part of this history has no bid/ask: buys and sells there are split by the tick rule';
    slot.addEventListener('pointerdown', () => host.onPick(this), true);
    this.lg.inds.addEventListener('click', (e) => this.onLegendClick(e));
    this.box.addEventListener('contextmenu', (e) => this.onMenu(e));
    this.box.addEventListener('pointermove', (e) => this.onEventHover(e));
    this.box.addEventListener('pointerleave', () => { this.evTip.hidden = true; });
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
    const { root, spec } = this.cfg, F = S.legendFlags(this.R);
    this.lg.name.hidden = !F.title;
    this.lg.name.textContent = S.titleText(root, C.rootName(root), C.specLabel(spec), F.titleMode);
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

  /* The chart's settings as the layout stores them: what differs from the defaults (a copy). */
  settings() { return { ...(this.cfg.settings || {}) }; }

  /* New settings (the dialog's live preview, Ok, Cancel, Apply to all): kept in the chart's config (none when
     all are defaults) and applied in place. Saving the layout is the page's job (on Ok). */
  setSettings(over) {
    const o = S.overrides(over);
    if (Object.keys(o).length) this.cfg.settings = o; else delete this.cfg.settings;
    this.applySettings();
  }

  /* Apply cfg.settings to the chart in place: the dialog previews every change live, and rebuilding the chart
     would flash. A new time zone re-times every bar and rebuilds. */
  applySettings() {
    const was = this.R, R = this.R = S.resolve(this.cfg.settings || {}, this.P || palette());
    this.title();
    if (!this.chart) return;
    if (was.timezone !== R.timezone) { this.retime(); this.restyle(); return; }
    const o = S.chartOptions(R);
    this.chart.applyOptions({ ...o, rightPriceScale: { ...o.rightPriceScale, scaleMargins: S.scaleMargins(R) } });
    this.candles.applyOptions(this.candleOpts());
    this.wm.applyOptions({ visible: R.watermark, lines: [this.wmLine()] });
    if ((R.prevClose || was.prevClose) && CANDLE_KEYS.some((k) => R[k] !== was[k])) this.resetCandles();
    if (R.scalePriceOnly !== was.scalePriceOnly) {   // "Scale price chart only": the price pane's lines leave autoscale
      for (const l of this.lines) if (l.overlay) l.s.applyOptions({ autoscaleInfoProvider: R.scalePriceOnly ? NO_SCALE : undefined });
    }
    this.syncEth();
    if (this.cd) this.cd.redraw();
    this.redrawEvents();
    this.legendRows();
    this.legend(this.hover);
  }

  /* The candle series' options for the settings; while the footprint is readable, bodies and borders step
     aside (its numbers sit where the bodies are). */
  candleOpts() {
    const o = S.candleOptions(this.R, this.tick);
    return this.fpHide ? { ...o, upColor: S.CLEAR, downColor: S.CLEAR, borderVisible: false } : o;
  }

  /* The watermark line: "NQ, 1m" in the settings' colour. */
  wmLine() {
    const s = this.shown || this.cfg;
    return { text: `${s.root}, ${C.specLabel(s.spec)}`, color: this.R.watermarkColor, fontSize: 48, fontFamily: FONT };
  }

  /* The price step the legend shows: the tick size, or the Precision setting's 10^-n. */
  dtick() { return this.R.precision == null ? this.tick : 10 ** -this.R.precision; }

  /* A bar's axis time: its start on the chart time zone's wall clock (by default ET: the server's own t). */
  wall(b) { return this.R.timezone === 'exchange' ? b.t : S.wallSeconds(b.ms, this.R.timezone); }

  /* The time zone changed: every bar's axis time again. */
  retime() { const bars = this.bars; this.bars = []; this.realT = new Map(); for (const b of bars) this.append(b); }

  /* The electronic-hours background: intraday time charts only. */
  syncEth() {
    if (!this.eth) return;
    this.eth.set(this.bars, this.R.ethBg && this.isTime() && this.barMs() < 86400000, this.R.ethBgColor, S.outsideRth);
  }

  /* The countdown under the last-price label: {text, price, color, font}, or null when it is off, the label is
     off, the chart is not a time chart, no clock came yet, or the last bar already closed. */
  countdownNow() {
    const R = this.R, n = this.bars.length, ms = this.barMs();
    if (!R.countdown || !R.lastLabel || !ms || !n || this.clockEt == null || !this.shown) return null;
    const last = this.bars[n - 1], left = S.barCloseEt(last, ms, C.ALWAYS_OPEN.has(this.shown.root)) - this.clockEt;
    if (left <= 0) return null;
    const prev = n > 1 ? this.bars[n - 2] : null, up = last.c >= (R.prevClose && prev ? prev.c : last.o);
    return { text: S.fmtCountdown(left), price: last.c, color: up ? R.bodyUp : R.bodyDown, font: R.scaleFont };
  }

  /* What the calendar layer draws now: the events this chart shows (its Events settings) and where. A tick,
     volume or range chart has no place for an event outside its bars. */
  eventsNow() {
    const n = this.bars.length;
    if (!n || !this.chart) return null;
    const ts = this.chart.timeScale(), time = this.isTime(), first = this.bars[0].ms, last = this.bars[n - 1].ms;
    const ctx = { bars: this.bars, isTime: time, barMs: this.barMs(), coord: (i) => ts.logicalToCoordinate(i) };
    const xOf = (t) => (!time && (t < first || t > last) ? null : window.HBDrawings.timeToX(t, ctx));
    return { events: window.HBEvents.shown(this.host.events(), this.R), xOf, lines: this.R.evLines };
  }

  redrawEvents() { if (this.evl) this.evl.redraw(); }

  /* Hovering a calendar flag: its events in a tooltip above it (times in the chart's zone). */
  onEventHover(e) {
    const tip = this.evTip, L = this.evl;
    if (!L || e.buttons || !L.flags.length) { tip.hidden = true; return; }
    const r = this.box.getBoundingClientRect();
    const g = window.HBEvents.flagAt(L.flags, { x: e.clientX - r.left, y: e.clientY - r.top }, L.flagY);
    if (!g) { tip.hidden = true; return; }
    tip.replaceChildren(...window.HBEvents.tipLines(g, this.R.timezone).map((s) => mk('div', '', s)));
    tip.hidden = false;
    const w = tip.offsetWidth, h = tip.offsetHeight;
    tip.style.left = `${Math.max(4, Math.min(g.x - w / 2, this.box.clientWidth - w - 4))}px`;
    tip.style.top = `${Math.max(4, L.flagY - 12 - h)}px`;
  }

  /* Once a second, from the page: now as ET wall-clock ms (a replay's own clock in a replay). */
  tickSecond(nowEt) { this.clockEt = nowEt; if (this.cd) this.cd.redraw(); }

  /* TradingView's scroll-back: the view's left edge near the first loaded bar asks the server for the next
     chunk of older sessions (one request at a time; none while a subscription is in flight; none once the
     200,000-bar client cap is hit -- capped stays until the next full history). */
  askOlder(r) {
    if (!this.chart || this.inflight.length || !this.bars.length || this.capped) return;
    const req = this.back.want(r, this.bars[0].ms);
    if (req && this.host.send({ op: 'older', id: this.id, before: req.before })) this.back.sent(req);
  }

  /* Older sessions in front of the chart: the bars, their studies (and the repaired first bars) and session
     labels merged, every series re-set in place (no rebuild: no flash, a drag goes on), the view shifted by
     the bars added so it does not move. The chunk is cropped to the 200,000-bar cap (no eviction: only the
     incoming chunk is trimmed, never the chart's own bars). done or capped: the label at the first bar
     ("Start of data" / "History limit reached"), and scroll-back stops asking. */
  onOlder(m) {
    if (!this.back.take(m) || !this.chart || this.inflight.length) return;
    const { bars: merged, capped } = window.HBScrollBack.capPrepend(this.bars, m);
    if (capped) this.capped = true;
    const k = merged.length - this.bars.length;
    if (k) {
      const r = this.chart.timeScale().getVisibleLogicalRange();
      // a cropped chunk drops its oldest bars: drop their session labels too, so no gap band or approx.-flow
      // badge ever points at a session that never actually landed on the chart
      const kept = new Set(merged.slice(0, k).map((b) => b.s));
      this.sessions = window.HBScrollBack.mergeSessions((m.sessions || []).filter((x) => kept.has(x.date)), this.sessions);
      this.bars = []; this.realT = new Map();
      for (const b of merged) this.append(b);   // axis times again: tick/volume/range bars sit on an index axis
      this.candles.setData(this.candleData());
      for (const l of this.lines) l.s.setData(this.bars.map((b) => this.point(l, b)));
      if (r) this.chart.timeScale().setVisibleLogicalRange({ from: r.from + k, to: r.to + k });
      if (this.hover != null) this.hover += k;
      this.drawMarkers(); this.drawGaps(); this.syncFootprint(); this.syncEth();
      this.lg.badge.hidden = !this.sessions.some((s) => s.approx);
      this.legend(this.hover);
      if (this.dc) this.dc.refresh();
    }
    this.start.set(this.back.done || this.capped, this.capped ? 'History limit reached' : 'Start of data');
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
    this.back.reset();
    this.capped = false;
    const s = this.shown, view = entry && entry.view && s && s.root === m.root && s.spec === m.spec ? entry.view : null;
    this.shown = { root: m.root, spec: m.spec };
    this.tick = m.tick_size; this.pv = m.point_value ?? null; this.sessions = m.sessions || []; this.devel = !!m.live;
    this.keys = new Set(Object.keys(m.studies || {}));
    this.profile = m.profile || null;
    this.bars = []; this.realT = new Map();
    m.bars.forEach((b, i) => { b.sv = {}; for (const k in m.studies) b.sv[k] = m.studies[k][i]; this.append(b); });
    this.build(view);
    // partial: the server's BUILD_BUDGET_S cut the initial load short (a cold, deep chart). It already
    // dropped the OLDEST sessions, never the newest, so what's on screen is right -- but there may be far
    // fewer bars than this bar type's default depth. Ask for the rest right away rather than waiting for
    // the user to scroll into the left edge.
    if (m.partial) this.askOlder({ from: 0, to: this.bars.length });
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
    this.candles.setData(this.candleData());
    this.buildSeries();
    for (const l of this.lines) l.s.setData(this.bars.map((b) => this.point(l, b)));
    this.drawMarkers(); this.drawLevels(); this.drawGaps(); this.syncFootprint(); this.syncProfile(); this.syncEth();
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
    this.start.set(this.back.done || this.capped, this.capped ? 'History limit reached' : 'Start of data');
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
    const R = this.R = S.resolve(this.cfg.settings || {}, P), o = S.chartOptions(R);
    this.fpHide = false;
    this.chart = LW.createChart(this.box, {
      autoSize: true,
      layout: { ...o.layout, fontFamily: FONT,
        attributionLogo: false,   // the credit lives once in the bottom bar
        panes: { separatorColor: P.border, separatorHoverColor: P.accentSoft, enableResize: true } },
      grid: o.grid,
      rightPriceScale: { ...o.rightPriceScale, scaleMargins: S.scaleMargins(R) },
      timeScale: { ...o.timeScale, timeVisible: true, secondsVisible: sub,
        tickMarkFormatter: (t, type) => tickLabel(this.real(t), type) },
      localization: { timeFormatter: (t) => this.fullTime(t) },
      crosshair: { mode: this.magnetXhair ? LW.CrosshairMode.MagnetOHLC : LW.CrosshairMode.Normal,
        vertLine: { ...o.crosshair.vertLine, labelBackgroundColor: P.crossLabel },
        horzLine: { ...o.crosshair.horzLine, labelBackgroundColor: P.crossLabel } },
    });
    this.candles = this.chart.addSeries(LW.CandlestickSeries, this.candleOpts());
    this.markers = LW.createSeriesMarkers(this.candles, []);
    this.wm = LW.createTextWatermark(this.chart.panes()[0], { visible: R.watermark, horzAlign: 'center',
      vertAlign: 'center', lines: [this.wmLine()] });
    this.fp = new Footprint(P); this.prof = new Profile(P); this.gaps = new Gaps(P);
    this.eth = new EthBg(P); this.cd = new Countdown(P, () => this.countdownNow());
    this.evl = new EventFlags(P, () => this.eventsNow());
    this.start = new Start(P);
    const fp = this.fp;   // pin the instance this callback belongs to
    fp.onReadableChange = (on) => {   // fired async from Footprint.updateAllViews(), after layout
      if (this.fp !== fp || !this.chart) return;
      this.fpHide = on;
      this.candles.applyOptions(this.candleOpts());
      if (this.R.prevClose) this.resetCandles();   // per-bar colours ride in the data
    };
    for (const l of [this.eth, this.gaps, this.start, this.prof, this.fp, this.cd, this.evl]) this.candles.attachPrimitive(l);
    this.lines = []; this.levelLines = {}; this.colorOf = {}; this.hover = null;
    this.chart.timeScale().subscribeVisibleLogicalRangeChange((r) => { this.syncFootprint(); this.evTip.hidden = true; this.askOlder(r); });
    this.chart.subscribeCrosshairMove((p) => {
      this.hover = p && p.logical != null ? Math.round(p.logical) : null;
      this.legend(this.hover);
    });
  }

  teardown() {
    if (this.dc) { this.dc.destroy(); this.dc = null; }
    if (!this.chart) return;
    this.chart.remove();
    this.chart = this.candles = this.markers = this.fp = this.prof = this.gaps = this.wm = null;   // stale async callbacks can tell
    this.eth = this.cd = this.evl = this.start = null;
  }

  /* One series per drawn part of each indicator instance, in instance order. A pane-type indicator goes where
     its placement says: 'own' = the next pane below; 'main' = the price pane, on an overlay scale of its own
     pinned to the bottom (as Volume), so it never moves the price autoscale. */
  buildSeries() {
    const P = this.P;
    let ci = 0, pane = 0;
    this.paneUid = [null];
    const add = (inst, src, part, type, opts, where) => {
      const overlay = where === 0 && !opts.priceScaleId;   // on the price pane's own scale (not the volume overlay)
      const auto = overlay && this.R.scalePriceOnly ? { autoscaleInfoProvider: NO_SCALE } : {};
      const s = this.chart.addSeries(type, { priceLineVisible: false, visible: inst.visible !== false, ...opts, ...auto }, where);
      this.lines.push({ uid: inst.uid, s, src, part, overlay });
      return s;
    };
    const line = (inst, src, part, color, width, where = 0, extra = {}) => add(inst, src, part, LW.LineSeries,
      { color, lineWidth: width, lastValueVisible: true, crosshairMarkerVisible: false, title: '', ...extra }, where);
    // {where, scale}: the pane index, and the series options that put it on its overlay scale when on 'main'
    const spot = (inst) => {
      if (C.placement(inst) === 'own') { this.paneUid.push(inst.uid); return { where: ++pane, scale: {} }; }
      return { where: 0, scale: { priceScaleId: 'ind:' + inst.uid, lastValueVisible: false } };
    };
    const pin = (s, where, top) => { if (where === 0) s.priceScale().applyOptions({ scaleMargins: { top, bottom: 0 } }); };
    for (const inst of this.cfg.indicators) {
      const k = C.serverKey(inst);
      switch (inst.id) {
        case 'volume': {
          const { where } = spot(inst);
          const s = add(inst, '__vol', null, LW.HistogramSeries, { priceFormat: { type: 'volume' },
            ...(where === 0 ? { priceScaleId: 'vol', lastValueVisible: false } : { lastValueVisible: true }) }, where);
          pin(s, where, VOL_TOP);
          break;
        }
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
          const { where, scale } = spot(inst);
          const a = line(inst, k, null, P.text, 2, where, scale);
          line(inst, k, 'p', P.up, 1, where, scale); line(inst, k, 'm', P.down, 1, where, scale);
          pin(a, where, MAIN_TOP);   // the three lines share the one scale
          break;
        }
        case 'delta': {
          const { where, scale } = spot(inst);
          pin(add(inst, '__delta', null, LW.HistogramSeries, { lastValueVisible: true, priceFormat: { ...WHOLE }, ...scale }, where),
            where, MAIN_TOP);
          break;
        }
        case 'cumdelta': {
          this.colorOf[inst.uid] = P.cum;
          const { where, scale } = spot(inst);
          pin(line(inst, k, null, P.cum, 2, where, { priceFormat: { ...WHOLE }, ...scale }), where, MAIN_TOP);
          break;
        }
        default:   // levels, footprint, profile, big prints: price lines, layers and markers
          break;
      }
    }
  }

  legendRows() {
    const F = S.legendFlags(this.R);
    this.rows = this.cfg.indicators.map((inst) => {
      const off = inst.visible === false, row = mk('div', 'lg-row' + (off ? ' off' : '')), vals = mk('span', 'lg-vals');
      const btns = mk('span', 'lg-btns'), hasParams = C.def(inst.id).params.length > 0;
      btns.append(iconButton(off ? 'eyeOff' : 'eye', off ? 'Show' : 'Hide', 'eye'));
      if (hasParams) btns.append(iconButton('gear', 'Settings', 'gear'));
      btns.append(iconButton('x', 'Remove', 'x'));
      if (C.movable(inst.id)) {   // TradingView's "More": move to the price pane / to a pane below
        const more = iconButton('ellipsis', 'More', 'more');
        more.setAttribute('aria-haspopup', 'menu');
        more.setAttribute('aria-expanded', 'false');
        btns.append(more);
      }
      row.dataset.uid = inst.uid;
      row.append(mk('span', 'lg-label', S.legendLabel(C.label(inst), hasParams, F)), vals, btns);
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
    else if (b.dataset.act === 'more') this.host.onIndicatorMenu(this, uid, { anchor: b });
    else this.removeIndicator(uid);
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

  removeIndicator(uid) { this.update({ indicators: this.cfg.indicators.filter((x) => x.uid !== uid) }); }

  /* Move a pane-type indicator to 'main' (the price pane) or 'own' (a pane below). The chart is rebuilt
     through update() (view kept, no resubscribe: the studies are the same), as the legend's × does. */
  setPlacement(uid, pane) {
    const inst = this.cfg.indicators.find((x) => x.uid === uid);
    if (!inst || !C.movable(inst.id) || !C.PANES.includes(pane) || C.placement(inst) === pane) return;
    this.update({ indicators: this.cfg.indicators.map((x) => (x.uid === uid ? { ...x, pane } : x)) });
  }

  /* The pane under a viewport y: its index, or -1 (a separator, outside the chart). */
  paneAt(clientY) {
    const panes = this.chart ? this.chart.panes() : [];
    for (let i = 0; i < panes.length; i++) {
      const el = panes[i].getHTMLElement();
      if (!el) continue;
      const r = el.getBoundingClientRect();
      if (clientY >= r.top && clientY < r.bottom) return i;
    }
    return -1;
  }

  /* Right-click (and, from the drawing controller, a double-click on empty price-pane space: dbl): the chart
     menu on the price pane with the tick-rounded price under the pointer; an indicator's own menu in its pane
     (right-click only); nothing on the axes. The browser's own menu never shows over a chart. */
  onMenu(e, dbl = false) {
    e.preventDefault();
    if (!this.chart || !this.bars.length) return;
    const r = this.box.getBoundingClientRect(), x = e.clientX - r.left;
    if (x < 0 || x >= this.box.clientWidth - this.chart.priceScale('right').width()) return;   // the price axis
    const i = this.paneAt(e.clientY), at = { x: e.clientX, y: e.clientY };
    if (i === 0) {
      const top = this.chart.panes()[0].getHTMLElement().getBoundingClientRect().top;
      const raw = this.candles.coordinateToPrice(e.clientY - top);
      this.host.onChartMenu(this, { ...at, price: raw == null ? null : window.HBDrawings.roundToTick(raw, this.tick) });
    } else if (i > 0 && !dbl && this.paneUid[i]) {
      this.host.onIndicatorMenu(this, this.paneUid[i], { at });
    }
  }

  /* Reset chart view (the menu, ⌥R): the default bar spacing with the latest bar at the right margin, and every
     pane's price scale back to auto (T10-R1). */
  resetView() {
    if (!this.chart) return;
    this.chart.timeScale().resetTimeScale();
    this.chart.panes().forEach((_, i) => this.chart.priceScale('right', i).applyOptions({ autoScale: true }));
  }

  /* The OHLC row and every indicator row for bar i (null: the last bar). */
  legend(i) {
    const n = this.bars.length;
    if (!n || !this.P) { this.lg.ohlc.replaceChildren(); return; }
    const k = i == null ? n - 1 : Math.max(0, Math.min(i, n - 1)), b = this.bars[k], prev = k > 0 ? this.bars[k - 1] : null;
    const P = this.P, R = this.R, dt = this.dtick();
    const up = b.c >= (R.prevClose && prev ? prev.c : b.o), col = up ? R.bodyUp : R.bodyDown, ch = C.change(b, prev, dt);
    const F = S.legendFlags(R), parts = [];
    if (F.ohlc) parts.push(...[['O', b.o], ['H', b.h], ['L', b.l], ['C', b.c]].map(([key, v]) => kv(key, C.fmtPrice(v, dt), col)));
    if (F.change) parts.push(val(ch.text, ch.up ? R.bodyUp : R.bodyDown));
    if (F.volume) parts.push(kv('Vol', C.fmtCompact(b.v), col), kv('Δ', C.fmtSigned(b.d), b.d >= 0 ? P.up : P.down));
    this.lg.ohlc.replaceChildren(...parts);
    const colors = { text: P.text, up: P.up, down: P.down, vwap: P.vwap, cum: P.cum };
    for (const r of this.rows) {
      const vs = F.indValues ? C.legendValues(r.inst, b, { ...colors, line: this.colorOf[r.inst.uid] || P.accent }, dt) : [];
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
      const i = this.bars.lastIndexOf(b);
      this.candles.update(this.candle(b, i > 0 ? this.bars[i - 1] : null));
      for (const l of this.lines) l.s.update(this.point(l, b));
    }
    if (m.profile !== undefined) { this.profile = m.profile; this.syncProfile(); }
    if (touched.some((b) => b.big && b.big.length)) this.drawMarkers();
    this.drawLevels(); this.syncFootprint();
    this.legend(this.hover);
  }

  append(b) {
    const last = this.bars[this.bars.length - 1];
    b.tt = this.isTime() ? this.wall(b) : FAKE0 + this.bars.length * 60;
    if (last && b.tt <= last.tt) b.tt = last.tt + 1;
    if (!this.isTime()) this.realT.set(b.tt, this.wall(b));
    this.bars.push(b);
  }

  replaceLast(b) {
    const i = this.bars.length - 1;
    b.tt = this.bars[i].tt;
    if (!this.isTime()) this.realT.set(b.tt, this.wall(b));
    this.bars[i] = b;
  }

  /* One candle; with "Colour bars based on previous close" it carries its own colours (up/down against the
     previous close), hidden like the series' while the footprint is readable. */
  candle(b, prev) {
    const c = { time: b.tt, open: b.o, high: b.h, low: b.l, close: b.c };
    if (!this.R.prevClose) return c;
    const k = S.barColor(b, prev, this.R);
    return { ...c, color: this.fpHide ? S.CLEAR : k.color, borderColor: k.borderColor, wickColor: k.wickColor };
  }
  candleData() { return this.bars.map((b, i) => this.candle(b, i ? this.bars[i - 1] : null)); }
  /* Every candle again (per-bar colours changed), the view kept where it is. */
  resetCandles() {
    const v = this.viewNow();
    this.candles.setData(this.candleData());
    if (v) this.setView(v);
  }

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
