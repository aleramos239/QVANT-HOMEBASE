/* Homebase Charts — HBTesterLayer: the Strategy Tester's trades drawn on the root's own chart, one overlay
   per chart (rebuilt with it, like every host.overlays() entry — HBTradeLines is the sibling pattern):
     - entry (arrow) / exit (circle, "+$…") markers for every trade, through cell.setExtraMarkers('tester', …)
       (ruling S22 — merged with the trading and bot markers, never replacing them);
     - one LineSeries per bundle.plots.plots[name] on the price pane;
     - a TesterMarks canvas primitive on cell.candles: the selected trade's entry/SL/TP segments and its
       entry-to-exit connector, and a dotted price line + label per bundle.plots.hlines item;
     - jump(i): scrolls back (switching the chart's interval when needed, ruling S20) and zooms to trade i.
   A tester run can have thousands of trades: markers and plot data are only ever built from the trades/points
   that fall inside the chart's CURRENTLY LOADED bars (tradesInRange/plotPoints below), and are rebuilt only
   when the bundle, the Hide-trades tick, or the loaded range's oldest bar actually changes — never on every
   quote tick or live bar update.

   The pure top half (tradesInRange, sessionSpan, plotPoints) has no browser globals at load time: the Node
   tests load this file directly, like tester.js's own pure half. The Overlay/TesterMarks/jump below it are
   browser-only (LightweightCharts, HBTesterUI, HBTester, page). */
(function () {
'use strict';
const need = (name, file) => (typeof window !== 'undefined' && window[name]) || (typeof require === 'function' ? require(file) : null);
const D = need('HBDrawings', './drawings.js');

/* Trades whose entry-to-exit span overlaps the chart's currently loaded bars: the first bar's start through
   the last bar's own coverage end (its start + one bar's length for a time chart, else unbounded — the same
   bound placeMarkers uses for a single marker). A trade need only touch the window at one end (its other
   marker is dropped later, by placeMarkers itself, if that end lands outside it). */
function tradesInRange(trades, bars, barMs) {
  if (!bars || !bars.length) return [];
  const start = bars[0].ms, end = barMs > 0 ? bars[bars.length - 1].ms + barMs : Infinity;
  return (trades || []).filter((t) => t.exit_ms >= start && t.entry_ms < end);
}

/* The contiguous [firstIndex, lastIndex] of bars whose b.s === date, searched only over [from, to] (the
   visible window: a session hline is drawn only while its day is on screen, and a run can hold years of
   them) — or null when none of those bars belong to that date. */
function sessionSpan(bars, date, from = 0, to = bars.length - 1) {
  let i0 = -1, i1 = -1;
  const lo = Math.max(0, from), hi = Math.min(bars.length - 1, to);
  for (let i = lo; i <= hi; i++) {
    if (bars[i].s === date) { if (i0 < 0) i0 = i; i1 = i; }
  }
  return i0 < 0 ? null : [i0, i1];
}

/* A plot series' data: each [t_ms, v] lands on the tt of the bar covering it (the last bar starting at or
   before t_ms); a point before the first bar is dropped (barIndexAt returns -1); two points landing on the
   same bar keep only the later one (a plot can update several times inside one bar). Sorted by time, as
   LineSeries.setData wants. */
function plotPoints(points, bars) {
  if (!bars || !bars.length) return [];
  const byTt = new Map();
  for (const p of points || []) {
    const i = D.barIndexAt(bars, p[0]);
    if (i < 0) continue;
    byTt.set(bars[i].tt, p[1]);
  }
  return [...byTt.entries()].sort((a, b) => a[0] - b[0]).map(([time, value]) => ({ time, value }));
}

/* ---- rule geometry (2026-09-27): a run records every level the strategy PLACED, not only the fills, so
   a session reads at a glance. Style comes from the record's ROLE (anchor | entry | sl | tp | level), never
   from parsing its name -- except the side of an entry, which only the name carries ("Long entry +5"). A
   "(planned)" bracket (the one the trigger sized, before the engine moved it to the fill) and a
   "(not filled)" leg are the same colour as their live counterpart, dimmed and more finely dashed. */

const LABEL_MIN_PX = 44;         // a session narrower than this draws its lines but no text
const LABEL_ROW_H = 13;          // px between two stacked labels
const DIMMED = /\((?:planned|not filled)\)/;
const LIVE_DASH = [4, 3], DIM_DASH = [1, 5], LEVEL_DASH = [1, 3];

function hlineStyle(item, P) {
  const name = (item && item.name) || '', role = (item && item.role) || 'level';
  const color = role === 'entry' ? (/^short/i.test(name) ? P.down : P.accent)
    : role === 'sl' ? P.down
      : role === 'tp' ? P.up : P.text2;
  const dim = DIMMED.test(name);
  const dash = role === 'anchor' ? [] : dim ? DIM_DASH : role === 'level' ? LEVEL_DASH : LIVE_DASH;
  return { color, dash, alpha: dim ? 0.45 : 1 };
}

const hlinePrice = (v) => Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 });
function hlineLabel(item) { return `${item.name} \u00b7 ${hlinePrice(item.price)}`; }
function hlineTip(item) { return `${hlineLabel(item)}\n${item.date}`; }

/* Labels for levels that sit close together, pushed apart into rows of `rowH` px inside [top, bottom]:
   sorted by y, each one moved down to clear the one above, then the whole stack pushed back up if it ran
   off the bottom. Pure -- a new array, the input rows untouched. */
function stackLabels(rows, rowH, top, bottom) {
  const out = [...(rows || [])].sort((a, b) => a.y - b.y).map((r) => ({ ...r }));
  let floor = top;
  for (const r of out) { r.y = Math.max(r.y, floor); floor = r.y + rowH; }
  let ceil = bottom;
  for (let i = out.length - 1; i >= 0; i--) { out[i].y = Math.min(out[i].y, ceil); ceil = out[i].y - rowH; }
  return out;
}

function labelsFit(x0, x1) { return x0 != null && x1 != null && x1 - x0 >= LABEL_MIN_PX; }

/* ---- WHICH chart shows a tester run: Claude's "show on chart" (POST /api/tester/show -> /ws tester_show) and a
   click in List of trades both plan through here. `charts` is [{root, replay, tradeReady}] in grid order (root =
   what the chart shows now; tradeReady = any account ticked or an algo set). The rules:
     - a replaying chart is NEVER touched;
     - a trade-ready chart is NEVER taken over -- not switched, not re-intervalled, not scrolled -- even when it
       already shows the run's root;
     - avoidSelected (Claude's show): never the selected chart either -- the order panel and DOM follow it;
     - of what is left, a chart already on the root first (the selected one first, when allowed), else one that
       switches to the root. None left: {index: -1, reason} and nothing moves (the page says why).
   Pure. */
function showPlan(charts, selected, root, { avoidSelected = true } = {}) {
  const list = charts || [];
  const order = [selected, ...list.map((_, i) => i).filter((i) => i !== selected)]
    .filter((i) => i >= 0 && i < list.length);
  const ok = (i) => !list[i].replay && !list[i].tradeReady && !(avoidSelected && i === selected);
  for (const i of order) if (ok(i) && list[i].root === root) return { index: i, switchRoot: false };
  for (const i of order) if (ok(i)) return { index: i, switchRoot: true };
  return { index: -1, reason: `No free chart for ${root}: charts with accounts or an algo, a replaying chart`
    + `${avoidSelected ? ' and the selected chart' : ''} are never taken over. Clear a chart's accounts (or add one), then try again.` };
}

/* The trade a show request focuses: {trade_index} as given (when it exists); {date} the first trade on or
   after that session date, else the last one before it; {time_ms} the first trade still open at or after
   that instant (exit_ms >= t), else the last one. null when there are no trades or no focus. Pure. */
function focusTrade(trades, focus) {
  const ts = trades || [];
  if (!focus || !ts.length) return null;
  if (focus.trade_index != null) return Number.isInteger(focus.trade_index) && focus.trade_index >= 0
    && focus.trade_index < ts.length ? focus.trade_index : null;
  let i = -1;
  if (focus.date != null) i = ts.findIndex((t) => t.date >= focus.date);
  else if (focus.time_ms != null) i = ts.findIndex((t) => t.exit_ms >= focus.time_ms);
  else return null;
  return i < 0 ? ts.length - 1 : i;
}

/* ================================================================== browser half ================================================================== */

const PLOT_PANE_H = 90;   // px, = cell.js PANE_H: the gate/indicator sub-pane
const PLOT_FONT = '11px -apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif';

function seg(ctx, x0, x1, y, color, dashed) {
  if (x0 == null || x1 == null || y == null) return;
  ctx.strokeStyle = color;
  ctx.lineWidth = 1;
  ctx.setLineDash(dashed ? [3, 3] : []);
  ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke();
  ctx.setLineDash([]);
}

/* The selected trade: entry/SL/TP as short horizontal segments from x(entry) to x(exit), and a dashed
   connector from (entry, entry price) to (exit, exit price) in the trade's own P&L colour. A segment (or the
   connector) is skipped when either of its ends has no coordinate (off the loaded bars or the price pane). */
function drawTrade(ctx, t, P, xOf, yOf) {
  const ex = xOf(t.entry_ms), xx = xOf(t.exit_ms);
  const ey = yOf(t.entry_price), xy = yOf(t.exit_price);
  seg(ctx, ex, xx, ey, P.text2, false);
  if (t.sl != null) seg(ctx, ex, xx, yOf(t.sl), P.down, true);
  if (t.tp != null) seg(ctx, ex, xx, yOf(t.tp), P.up, true);
  if (ex == null || xx == null || ey == null || xy == null) return;
  ctx.strokeStyle = t.net >= 0 ? P.up : P.down;
  ctx.setLineDash([3, 3]);
  ctx.beginPath(); ctx.moveTo(ex, ey); ctx.lineTo(xx, xy); ctx.stroke();
  ctx.setLineDash([]);
}

/* Every hlines item ({name, price, date, role}) whose session is inside the visible bar window [from, to]:
   one segment per level across its own session, styled by role, then the labels at the right-hand end --
   stacked per session so close levels never overwrite each other, and dropped entirely on a session too
   narrow to carry text (a zoomed-out year must not be a wall of names). Returns the segments it drew, for
   the overlay's hover.  */
function drawHlines(ctx, hlines, bars, P, ts, yOf, from, to, paneH) {
  const hits = [], byDate = new Map();
  for (const item of hlines) {
    const span = sessionSpan(bars, item.date, from, to);
    if (!span) continue;
    const x0 = ts.logicalToCoordinate(span[0]), x1 = ts.logicalToCoordinate(span[1] + 1), y = yOf(item.price);
    if (x0 == null || x1 == null || y == null) continue;
    const st = hlineStyle(item, P);
    ctx.save();
    ctx.globalAlpha = st.alpha;
    ctx.strokeStyle = st.color;
    ctx.lineWidth = 1;
    ctx.setLineDash(st.dash);
    const yy = Math.round(y) + 0.5;
    ctx.beginPath(); ctx.moveTo(x0, yy); ctx.lineTo(x1, yy); ctx.stroke();
    ctx.restore();
    hits.push({ x0, x1, y, tip: hlineTip(item) });
    if (!labelsFit(x0, x1)) continue;
    if (!byDate.has(item.date)) byDate.set(item.date, []);
    byDate.get(item.date).push({ y, x1, item, st });
  }
  ctx.font = PLOT_FONT;
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';
  for (const rows of byDate.values()) {
    for (const r of stackLabels(rows, LABEL_ROW_H, LABEL_ROW_H / 2, Math.max(LABEL_ROW_H / 2, paneH - LABEL_ROW_H / 2))) {
      ctx.save();
      ctx.globalAlpha = r.st.alpha;
      ctx.fillStyle = r.st.color;
      ctx.fillText(hlineLabel(r.item), r.x1 - 4, r.y);
      ctx.restore();
    }
  }
  return hits;
}

/* A series-primitive on cell.candles (the plugin shape Lightweight Charts wants: attached/detached,
   updateAllViews, paneViews — Hook in tradelines.js is the same idea). Reads HBTesterUI/HBTester live at
   every draw() rather than being pushed state, since both are process-wide singletons already. */
class TesterMarks {
  constructor(cell) {
    this.cell = cell;
    this.chart = null; this.series = null; this.requestUpdate = null;
    this.hits = [];                // the level segments last drawn, for the overlay's hover
    this._views = [{ zOrder: () => 'top', renderer: () => ({ draw: (t) => this.draw(t) }) }];
  }
  attached({ chart, series, requestUpdate }) { this.chart = chart; this.series = series; this.requestUpdate = requestUpdate; }
  detached() { this.chart = this.series = null; }
  updateAllViews() {}
  paneViews() { return this._views; }
  redraw() { if (this.requestUpdate) this.requestUpdate(); }

  draw(target) {
    this.hits = [];
    if (!this.chart || !this.series) return;
    const U = window.HBTesterUI, b = U.bundle, cell = this.cell;
    if (!b || !cell.shown || cell.shown.root !== b.run.strategy.root) return;
    const P = cell.P, bars = cell.bars, ts = this.chart.timeScale();
    const bctx = { bars, isTime: cell.isTime(), barMs: cell.barMs(), coord: (i) => ts.logicalToCoordinate(i) };
    const xOf = (ms) => D.timeToX(ms, bctx);
    const yOf = (price) => this.series.priceToCoordinate(price);
    const sel = U.selected, trade = U.hidden || sel == null ? null : b.trades[sel];
    const hlines = U.rules ? ((b.plots && b.plots.hlines) || []) : [];
    let from = 0, to = bars.length - 1;
    if (hlines.length) {
      const vr = ts.getVisibleLogicalRange();
      if (vr) { from = Math.max(0, Math.floor(vr.from)); to = Math.min(bars.length - 1, Math.ceil(vr.to)); }
    }
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      if (trade) drawTrade(ctx, trade, P, xOf, yOf);
      if (hlines.length) this.hits = drawHlines(ctx, hlines, bars, P, ts, yOf, from, to, mediaSize.height);
    });
  }
}

/* One overlay per chart. It shows a run when HBTesterUI.bundle exists and this cell shows that bundle's
   root; within that, the two sub-tab-bar ticks are independent -- "Hide trades" silences the markers and
   the selected trade's segments, "Rules" silences the recorded geometry (the levels and the series plots).
   A series plot draws in its OWN sub-pane below the candles, never over them. */
class Overlay {
  constructor(cell) {
    this.cell = cell;
    this.dead = false;
    this.plotSeries = new Map();   // plot name -> LineSeries
    this.plotsBundle = null;       // the bundle those series were built for (null: none built)
    this.plotPane = null;          // the sub-pane index those series live in
    this.bar0 = null;              // bars[0].ms as of the last recompute
    this.lastBundle = undefined;
    this.lastHidden = undefined;
    this.lastRules = undefined;
    this.marks = new TesterMarks(cell);
    cell.candles.attachPrimitive(this.marks);
    this.layer = document.createElement('div');
    this.layer.className = 'hb-tester-layer';
    this.tip = document.createElement('div');
    this.tip.className = 'ev-tip hb-tester-tip';
    this.tip.hidden = true;
    this.layer.appendChild(this.tip);
    cell.el.appendChild(this.layer);
    this.onMove = (p) => this.hoverTip(p);
    if (cell.chart) cell.chart.subscribeCrosshairMove(this.onMove);
    this.unsub = window.HBTesterUI.on(() => this.onNotify());
    this.onNotify();
  }

  /* This cell is showing the loaded run's instrument. */
  shows() {
    const b = window.HBTesterUI.bundle, cell = this.cell;
    return !!(b && cell.shown && cell.shown.root === b.run.strategy.root);
  }

  active() { return this.shows() && !window.HBTesterUI.hidden; }

  /* The level under the mouse (within 4 px of its segment, inside its own session's span): its name,
     price and session date. Mirrors newsui.js's marker tooltip. */
  hoverTip(p) {
    if (this.dead || !this.cell.chart || !p || !p.point || !this.marks.hits.length) { this.tip.hidden = true; return; }
    const { x, y } = p.point;
    let best = null, bestD = 5;
    for (const hit of this.marks.hits) {
      if (x < hit.x0 || x > hit.x1) continue;
      const d = Math.abs(y - hit.y);
      if (d < bestD) { bestD = d; best = hit; }
    }
    if (!best) { this.tip.hidden = true; return; }
    this.tip.textContent = best.tip;
    this.tip.hidden = false;
    const w = this.layer.clientWidth, tw = this.tip.offsetWidth;
    this.tip.style.left = `${Math.max(4, Math.min(w - tw - 4, x + 12))}px`;
    this.tip.style.top = `${Math.max(4, y - 34)}px`;
  }

  /* HBTesterUI.on() fires for a bundle load, a Recent-runs load, a strategy switch, a trade selection AND a
     Hide-trades toggle — it carries no reason. Only a bundle or hidden change is worth a recompute (rebuilding
     the marker list and the plot series); every other call (a selection change) just needs the primitive
     redrawn, since it reads HBTesterUI.selected live at draw time. */
  onNotify() {
    if (this.dead || !this.cell.chart) return;
    const U = window.HBTesterUI, b = U.bundle, hidden = U.hidden, rules = U.rules;
    if (b !== this.lastBundle || hidden !== this.lastHidden || rules !== this.lastRules) {
      this.lastBundle = b; this.lastHidden = hidden; this.lastRules = rules;
      this.recompute(b);
    }
    this.marks.redraw();
  }

  /* Called by the cell after older history merges in or a live bar updates (host.overlays' onBars hook).
     Recomputed only when the oldest loaded bar actually moved (older history came in) -- a live update at the
     newest bar changes nothing a loaded-run's trades/plots would newly qualify for. */
  onBars() {
    if (this.dead || !this.cell.chart || !this.shows()) return;
    const bars = this.cell.bars, bar0 = bars.length ? bars[0].ms : null;
    if (bar0 === this.bar0) return;
    this.recompute(window.HBTesterUI.bundle);
    this.marks.redraw();
  }

  recompute(b) {
    const bars = this.cell.bars;
    this.bar0 = bars.length ? bars[0].ms : null;
    this.cell.setExtraMarkers('tester', this.active()
      ? window.HBTester.tradeMarks(tradesInRange(b.trades, bars, this.cell.barMs()), this.cell.P) : []);
    this.rebuildPlots(this.shows() && window.HBTesterUI.rules, b);
  }

  /* The run's series plots (an ADX gate, the 10:00 candle's close position) in a sub-pane of their own --
     they are 0-to-1 gate readings, not prices, and would be meaningless stretched over the candles. */
  rebuildPlots(on, b) {
    const chart = this.cell.chart;
    if (!on || b !== this.plotsBundle) {
      this.dropPlots();
      this.plotsBundle = on ? b : null;
      const names = on && chart ? Object.keys((b.plots && b.plots.plots) || {}) : [];
      if (names.length) {
        const LW = window.LightweightCharts, Cat = window.HBCatalog;
        this.plotPane = chart.panes().length;
        names.forEach((name, k) => {
          this.plotSeries.set(name, chart.addSeries(LW.LineSeries, { color: Cat.LINE_COLORS[k % 5], lineWidth: 1,
            lastValueVisible: false, priceLineVisible: false }, this.plotPane));
        });
        const pane = chart.panes()[this.plotPane];
        if (pane) pane.setStretchFactor(PLOT_PANE_H);
      }
    }
    if (!on) return;
    const bars = this.cell.bars;
    for (const [name, series] of this.plotSeries) series.setData(plotPoints((b.plots.plots[name] || []), bars));
  }

  dropPlots() {
    const chart = this.cell.chart;
    const had = this.plotSeries.size, pane = this.plotPane;
    for (const s of this.plotSeries.values()) { if (chart) chart.removeSeries(s); }
    this.plotSeries.clear();
    this.plotPane = null;
    // the sub-pane we opened is now empty: close it, or every toggle leaves a dead band behind
    if (had && chart && pane != null && chart.removePane) { try { chart.removePane(pane); } catch (_) { /* already gone */ } }
  }

  destroy() {
    this.dead = true;
    this.unsub();
    if (this.cell.chart) {
      this.cell.candles.detachPrimitive(this.marks);
      this.cell.chart.unsubscribeCrosshairMove(this.onMove);
    }
    this.dropPlots();
    this.layer.remove();
    this.cell.setExtraMarkers('tester', []);
  }
}

/* What showPlan needs to know about one live chart. Fails closed: no HBTradeUI to ask = trade-ready. */
function chartFacts(c) {
  const TU = typeof window !== 'undefined' ? window.HBTradeUI : null;
  const tr = TU && TU.tradeOf ? TU.tradeOf(c) : null;
  return { root: (c.shown || c.cfg).root, replay: !!c.replay,
    tradeReady: !tr || !!(c.cfg && c.cfg.algo) || !!(tr.accounts && tr.accounts.length) };
}

let PAGE = null;   // the page interface (same singleton every overlay() call hands us): jump()'s own home
function overlay(cell, page) {
  PAGE = page;
  return new Overlay(cell);
}

/* Jump to trade i (ruling S20): select it, pick the chart showing the run's root (falling back to the
   selected one), switch it to whatever interval lets scroll-back reach the trade's entry under the client's
   200,000-bar cap, load history back to it, then zoom. Every early return leaves the status-bar note as
   whatever last explained why. The chart comes from showPlan (a trade-ready or replaying chart is never used);
   `target` (Claude's show, already planned) names it instead, and select: false leaves the selection alone. */
async function jump(i, target = null, { select = true } = {}) {
  if (!PAGE) return;
  const U = window.HBTesterUI, b = U.bundle, t = b && b.trades[i];
  if (!t) return;
  U.select(i);
  const root = b.run.strategy.root, cells = PAGE.cells(), rootOf = (c) => (c.shown || c.cfg).root;
  let cell = target;
  if (!cell) {        // a click in List of trades: the same rule as Claude's show, the selected chart allowed
    const plan = showPlan(cells.map(chartFacts), cells.indexOf(PAGE.cur()), root, { avoidSelected: false });
    if (plan.index < 0) { PAGE.sbNote(plan.reason); return; }
    cell = cells[plan.index];
  }
  // re-checked at the moment it is touched: never a replaying chart, never one with accounts or an algo
  if (cell.replay || !cells.includes(cell)) { PAGE.sbNote('That chart is replaying (or gone): left it alone'); return; }
  if (chartFacts(cell).tradeReady) { PAGE.sbNote('That chart has accounts or an algo on it: left it alone'); return; }
  if (select) PAGE.select(cell);
  const spec = window.HBTester.reachSpec(cell.cfg.spec, t.entry_ms, PAGE.clockMs());
  if (rootOf(cell) !== root || spec !== cell.cfg.spec) {
    const specChanged = spec !== cell.cfg.spec;
    const waiting = cell.whenLoaded();
    cell.update({ root, spec });
    if (!(await waiting)) return;
    // Name the interval the way the toolbar does (e.g. "5m"), not the raw "time:300" spec.
    if (specChanged) PAGE.sbNote(`Switched to ${window.HBCatalog.specLabel(spec)} bars to reach ${t.date}`);
  }
  const day = t.date;
  const ok = await cell.reach(t.entry_ms, (firstMs) => PAGE.sbNote(`Loading history back to ${day}… (at ${new Date(firstMs).toISOString().slice(0, 10)})`));
  if (!ok) { PAGE.sbNote(`${day} is older than this chart's history can load`); return; }
  PAGE.sbNote('');
  cell.focusRange(t.entry_ms, t.exit_ms);
}

const api = { overlay, jump, tradesInRange, sessionSpan, plotPoints, showPlan, focusTrade, chartFacts,
  hlineStyle, hlineLabel, hlineTip, stackLabels, labelsFit, LABEL_MIN_PX };
if (typeof window !== 'undefined') window.HBTesterLayer = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
