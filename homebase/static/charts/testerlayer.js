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

/* ================================================================== browser half ================================================================== */

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

/* One hlines item ({name, price, date}): a dotted segment across the bars whose b.s === item.date (searched
   only within [from, to], the visible bar window), its name as an 11px label at the left end. */
function drawHline(ctx, ts, bars, item, P, yOf, from, to) {
  const span = sessionSpan(bars, item.date, from, to);
  if (!span) return;
  const x0 = ts.logicalToCoordinate(span[0]), x1 = ts.logicalToCoordinate(span[1] + 1), y = yOf(item.price);
  if (x0 == null || x1 == null || y == null) return;
  const yy = Math.round(y) + 0.5;
  ctx.strokeStyle = P.text2;
  ctx.lineWidth = 1;
  ctx.setLineDash([1, 3]);
  ctx.beginPath(); ctx.moveTo(x0, yy); ctx.lineTo(x1, yy); ctx.stroke();
  ctx.setLineDash([]);
  ctx.font = PLOT_FONT;
  ctx.fillStyle = P.text2;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';
  ctx.fillText(item.name, x0 + 3, yy - 3);
}

/* A series-primitive on cell.candles (the plugin shape Lightweight Charts wants: attached/detached,
   updateAllViews, paneViews — Hook in tradelines.js is the same idea). Reads HBTesterUI/HBTester live at
   every draw() rather than being pushed state, since both are process-wide singletons already. */
class TesterMarks {
  constructor(cell) {
    this.cell = cell;
    this.chart = null; this.series = null; this.requestUpdate = null;
    this._views = [{ zOrder: () => 'top', renderer: () => ({ draw: (t) => this.draw(t) }) }];
  }
  attached({ chart, series, requestUpdate }) { this.chart = chart; this.series = series; this.requestUpdate = requestUpdate; }
  detached() { this.chart = this.series = null; }
  updateAllViews() {}
  paneViews() { return this._views; }
  redraw() { if (this.requestUpdate) this.requestUpdate(); }

  draw(target) {
    if (!this.chart || !this.series) return;
    const U = window.HBTesterUI, b = U.bundle, cell = this.cell;
    if (!b || !cell.shown || cell.shown.root !== b.run.strategy.root || U.hidden) return;
    const P = cell.P, bars = cell.bars, ts = this.chart.timeScale();
    const bctx = { bars, isTime: cell.isTime(), barMs: cell.barMs(), coord: (i) => ts.logicalToCoordinate(i) };
    const xOf = (ms) => D.timeToX(ms, bctx);
    const yOf = (price) => this.series.priceToCoordinate(price);
    const sel = U.selected, trade = sel != null ? b.trades[sel] : null;
    const hlines = (b.plots && b.plots.hlines) || [];
    let from = 0, to = bars.length - 1;
    if (hlines.length) {
      const vr = ts.getVisibleLogicalRange();
      if (vr) { from = Math.max(0, Math.floor(vr.from)); to = Math.min(bars.length - 1, Math.ceil(vr.to)); }
    }
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      if (trade) drawTrade(ctx, trade, P, xOf, yOf);
      for (const item of hlines) drawHline(ctx, ts, bars, item, P, yOf, from, to);
    });
  }
}

/* One overlay per chart. Active when HBTesterUI.bundle exists, this cell shows that bundle's root, and
   trades are not hidden. */
class Overlay {
  constructor(cell) {
    this.cell = cell;
    this.dead = false;
    this.plotSeries = new Map();   // plot name -> LineSeries
    this.plotsBundle = null;       // the bundle those series were built for (null: none built)
    this.bar0 = null;              // bars[0].ms as of the last recompute
    this.lastBundle = undefined;
    this.lastHidden = undefined;
    this.marks = new TesterMarks(cell);
    cell.candles.attachPrimitive(this.marks);
    this.unsub = window.HBTesterUI.on(() => this.onNotify());
    this.onNotify();
  }

  active() {
    const U = window.HBTesterUI, b = U.bundle, cell = this.cell;
    return !!(b && cell.shown && cell.shown.root === b.run.strategy.root && !U.hidden);
  }

  /* HBTesterUI.on() fires for a bundle load, a Recent-runs load, a strategy switch, a trade selection AND a
     Hide-trades toggle — it carries no reason. Only a bundle or hidden change is worth a recompute (rebuilding
     the marker list and the plot series); every other call (a selection change) just needs the primitive
     redrawn, since it reads HBTesterUI.selected live at draw time. */
  onNotify() {
    if (this.dead || !this.cell.chart) return;
    const U = window.HBTesterUI, b = U.bundle, hidden = U.hidden;
    if (b !== this.lastBundle || hidden !== this.lastHidden) {
      this.lastBundle = b; this.lastHidden = hidden;
      this.recompute(b);
    }
    this.marks.redraw();
  }

  /* Called by the cell after older history merges in or a live bar updates (host.overlays' onBars hook).
     Recomputed only when the oldest loaded bar actually moved (older history came in) -- a live update at the
     newest bar changes nothing a loaded-run's trades/plots would newly qualify for. */
  onBars() {
    if (this.dead || !this.cell.chart || !this.active()) return;
    const bars = this.cell.bars, bar0 = bars.length ? bars[0].ms : null;
    if (bar0 === this.bar0) return;
    this.recompute(window.HBTesterUI.bundle);
    this.marks.redraw();
  }

  recompute(b) {
    const active = this.active(), bars = this.cell.bars;
    this.bar0 = bars.length ? bars[0].ms : null;
    this.cell.setExtraMarkers('tester', active
      ? window.HBTester.tradeMarks(tradesInRange(b.trades, bars, this.cell.barMs()), this.cell.P) : []);
    this.rebuildPlots(active, b);
  }

  rebuildPlots(active, b) {
    const chart = this.cell.chart;
    if (!active || b !== this.plotsBundle) {
      for (const s of this.plotSeries.values()) { if (chart) chart.removeSeries(s); }
      this.plotSeries.clear();
      this.plotsBundle = active ? b : null;
      if (active && chart) {
        const LW = window.LightweightCharts, Cat = window.HBCatalog;
        Object.keys((b.plots && b.plots.plots) || {}).forEach((name, k) => {
          this.plotSeries.set(name, chart.addSeries(LW.LineSeries, { color: Cat.LINE_COLORS[k % 5], lineWidth: 1,
            lastValueVisible: false, priceLineVisible: false, autoscaleInfoProvider: () => null }));
        });
      }
    }
    if (!active) return;
    const bars = this.cell.bars;
    for (const [name, series] of this.plotSeries) series.setData(plotPoints((b.plots.plots[name] || []), bars));
  }

  destroy() {
    this.dead = true;
    this.unsub();
    if (this.cell.chart) {
      this.cell.candles.detachPrimitive(this.marks);
      for (const s of this.plotSeries.values()) this.cell.chart.removeSeries(s);
    }
    this.plotSeries.clear();
    this.cell.setExtraMarkers('tester', []);
  }
}

let PAGE = null;   // the page interface (same singleton every overlay() call hands us): jump()'s own home
function overlay(cell, page) {
  PAGE = page;
  return new Overlay(cell);
}

/* Jump to trade i (ruling S20): select it, pick the chart showing the run's root (falling back to the
   selected one), switch it to whatever interval lets scroll-back reach the trade's entry under the client's
   200,000-bar cap, load history back to it, then zoom. Every early return leaves the status-bar note as
   whatever last explained why. */
async function jump(i) {
  if (!PAGE) return;
  const U = window.HBTesterUI, b = U.bundle, t = b && b.trades[i];
  if (!t) return;
  U.select(i);
  const root = b.run.strategy.root, cells = PAGE.cells(), rootOf = (c) => (c.shown || c.cfg).root;
  const cell = rootOf(PAGE.cur()) === root ? PAGE.cur() : cells.find((c) => rootOf(c) === root) || PAGE.cur();
  PAGE.select(cell);
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

const api = { overlay, jump, tradesInRange, sessionSpan, plotPoints };
if (typeof window !== 'undefined') window.HBTesterLayer = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
