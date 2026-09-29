/* Homebase Charts — HBTesterLayer: a Strategy Tester run drawn on the root's own chart, one overlay per chart
   (rebuilt with it, like every host.overlays() entry — HBTradeLines is the sibling pattern):
     - a TesterMarks canvas primitive on cell.candles draws, for EVERY trade inside the loaded bars, what
       TradingView's strategy tester draws: a translucent green box entry -> TP and a translucent red box
       entry -> SL (both from the entry time to the exit time), the entry line, a thin entry-to-exit connector
       in the trade's P&L colour, the entry / exit execution arrows (the live chart's own arrow, blue buy / red
       sell) and the exit's P&L. The selected trade is emphasised (stronger boxes, outlined, price tags);
     - the strategy's recorded levels (bundle.plots.hlines) as short segments from the moment the strategy
       placed them to its session window's close, with compact labels that never overlap (full detail on hover);
     - one LineSeries per bundle.plots.plots[name] (a strategy's ctx.plot): a price-scale series on the price
       pane, anything else (an oscillator, a 0..1 gate reading) in a sub-pane of its own, with a legend entry
       per series;
     - jump(i): scrolls back (switching the chart's interval when needed, ruling S20) and zooms to trade i, and
       stays with it until the view has actually settled there.
   A tester run can have thousands of trades: everything is only ever built from the trades/points that fall
   inside the chart's CURRENTLY LOADED bars (tradesInRange/plotPoints below), and rebuilt only when the bundle,
   the Hide-trades / Rules ticks, or the loaded range's oldest bar actually changes — never on every quote tick
   or live bar update. Per frame the primitive only projects the trades in the visible window.

   The pure top half has no browser globals at load time: the Node tests load this file directly, like
   tester.js's own pure half. The Overlay/TesterMarks/jump below it are browser-only (LightweightCharts,
   HBTesterUI, HBTester, page). */
(function () {
'use strict';
const need = (name, file) => (typeof window !== 'undefined' && window[name]) || (typeof require === 'function' ? require(file) : null);
const D = need('HBDrawings', './drawings.js');
const TP = need('HBTradePure', './tradepure.js');
const usd = (v) => (TP.usd(v) == null ? '\u2014' : TP.usd(v));      // signed dollars: +$296 / \u2212$114

/* Trades whose entry-to-exit span overlaps the chart's currently loaded bars: the first bar's start through
   the last bar's own coverage end (its start + one bar's length for a time chart, else unbounded — the same
   bound placeMarkers uses for a single marker). A trade need only touch the window at one end. Each comes
   back with its index in the run ({t, i}): the selection and the list of trades speak in run indices. */
function tradesInRange(trades, bars, barMs) {
  if (!bars || !bars.length) return [];
  const start = bars[0].ms, end = barMs > 0 ? bars[bars.length - 1].ms + barMs : Infinity, out = [];
  (trades || []).forEach((t, i) => { if (t.exit_ms >= start && t.entry_ms < end) out.push({ t, i }); });
  return out;
}

/* Where each session date lives in the bars: Map date -> [firstIndex, lastIndex] (a session's bars are
   contiguous). One pass, cached by the caller until the bars change — a year of levels must not rescan a
   200,000-bar chart once per level per frame. */
function sessionIndex(bars) {
  const m = new Map();
  for (let i = 0; i < (bars || []).length; i++) {
    const s = bars[i].s, cur = m.get(s);
    if (cur) cur[1] = i; else m.set(s, [i, i]);
  }
  return m;
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

/* ---- series plots: which pane, and how they look ----
   A price-scale series (a moving average, a VWAP) belongs on the candles' own scale; anything else (an ADX, a
   0..1 reading, a distance in points) would be a flat line squashed against it, so it gets a sub-pane. Judged on
   the data: the series' median value against the median close of the bars it spans. */
const median = (a) => { const s = [...a].sort((x, y) => x - y), n = s.length; return n ? (n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2) : null; };

function plotPane(points, bars) {
  const vals = (points || []).map((p) => p[1]).filter(Number.isFinite);
  if (!vals.length || !bars || !bars.length) return 'sub';
  const closes = [], step = Math.max(1, Math.floor(bars.length / 400));
  for (let i = 0; i < bars.length; i += step) if (Number.isFinite(bars[i].c)) closes.push(bars[i].c);
  const mv = median(vals), mc = median(closes);
  return mc > 0 && mv >= mc * 0.5 && mv <= mc * 2 ? 'price' : 'sub';
}

/* A series that never moves (a threshold: "ADX gate min", "Top quarter") reads as a guide, not a signal. */
const isConstant = (points) => (points || []).length > 0 && points.every((p) => p[1] === points[0][1]);

/* The value a series shows at time `t`: its last point at or before it (a plot is sparse -- one reading a
   day -- so the crosshair's own bar rarely carries a point). data: [{time, value}] sorted by time. */
function valueAt(data, t) {
  let lo = 0, hi = (data || []).length - 1, ans = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (data[mid].time <= t) { ans = mid; lo = mid + 1; } else hi = mid - 1;
  }
  return ans < 0 ? null : data[ans].value;
}

/* ---- rule geometry (2026-09-27): a run records every level the strategy PLACED, not only the fills, so
   a session reads at a glance. Style comes from the record's ROLE (anchor | entry | sl | tp | level), never
   from parsing its name -- except the side of an entry, which only the name carries ("Long entry +5"). A
   "(planned)" bracket (the one the trigger sized, before the engine moved it to the fill) and a
   "(not filled)" leg are the same colour as their live counterpart, dimmed and more finely dashed. */

const LABEL_MIN_PX = 150;        // a level narrower than this draws its line but no text (a zoomed-out fortnight must not be a wall of names)
const LABEL_ROW_H = 12;          // px between two stacked labels
const DIMMED = /\((?:planned|not filled)\)/;
const LIVE_DASH = [4, 3], DIM_DASH = [1, 5], LEVEL_DASH = [1, 3];

function hlineStyle(item, P) {
  const name = (item && item.name) || '', role = (item && item.role) || 'level';
  const color = role === 'entry' ? (/^short/i.test(name) ? P.down : P.accent)
    : role === 'sl' ? P.down
      : role === 'tp' ? P.up : P.text2;
  const dim = DIMMED.test(name);
  const dash = role === 'anchor' ? [] : dim ? DIM_DASH : role === 'level' ? LEVEL_DASH : LIVE_DASH;
  return { color, dash, alpha: dim ? 0.45 : 1, dim };
}

const hlinePrice = (v) => Number(v).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 });
const ET_CLOCK = typeof Intl !== 'undefined' ? new Intl.DateTimeFormat('en-GB', { timeZone: 'America/New_York',
  hourCycle: 'h23', hour: '2-digit', minute: '2-digit', second: '2-digit' }) : null;
const etClock = (ms) => (ET_CLOCK && Number.isFinite(ms) ? ET_CLOCK.format(new Date(ms)) : '');

/* The full text of a level (hover, and the pre-2026-09-29 label): its name and price. */
function hlineLabel(item) { return `${item.name} · ${hlinePrice(item.price)}`; }
/* The compact label drawn on the chart: the name without its price, its "entry" and its (planned) /
   (not filled) mark -- "Long +10", "Short SL", "Anchor · NFP". Dimming already says planned / not filled;
   the hover says the rest. */
function levelText(item) {
  const s = String(item.name || '').replace(/\s*\((?:planned|not filled)\)/, '').replace(/^(Long|Short) entry /i, '$1 ').trim();
  return s.charAt(0).toUpperCase() + s.slice(1);
}
/* Hover: the level, its price, its session, and the window it was drawn over. */
function hlineTip(item) {
  const win = item.t_ms != null ? ` · from ${etClock(item.t_ms)}${item.end_ms != null ? ` to ${etClock(item.end_ms)}` : ''} ET` : '';
  return `${hlineLabel(item)}\n${item.date}${win}`;
}

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

/* One session's level labels: the live ones (not dimmed) are stacked so none overwrites another; a dimmed
   one (planned / not filled) is only kept when it fits in a gap the live ones left -- it is never allowed to
   push anything, and never drawn over anything. Pure. */
function placeLabels(rows, rowH, top, bottom) {
  const live = stackLabels((rows || []).filter((r) => !r.dim), rowH, top, bottom);
  const kept = [...live];
  for (const r of [...(rows || [])].filter((x) => x.dim).sort((a, b) => a.y - b.y)) {
    if (r.y >= top && r.y <= bottom && kept.every((k) => Math.abs(k.y - r.y) >= rowH)) kept.push({ ...r });
  }
  return kept;
}

function labelsFit(x0, x1) { return x0 != null && x1 != null && x1 - x0 >= LABEL_MIN_PX; }

/* Two records that say the same thing about the same session (same words, same price) are one level. */
function dedupeLevels(items) {
  const seen = new Map();
  for (const it of items || []) seen.set(`${it.date}|${levelText(it)}|${it.role}|${it.price}`, it);
  return [...seen.values()];
}

/* ---- positions: TradingView's long / short position box ---- */
const MIN_BOX_W = 6;              // px: a trade closed inside one bar is still a visible tick, not nothing

/* A trade's pixels: x from its entry to its exit time, y of its entry, exit, TP and SL. null when the entry
   or the exit has no x or the entry no y (nothing to anchor a box to). A missing TP / SL is a null y. */
function boxGeometry(t, xOf, yOf) {
  let x0 = xOf(t.entry_ms), x1 = xOf(t.exit_ms);
  const ey = yOf(t.entry_price);
  if (x0 == null || x1 == null || ey == null) return null;
  if (x1 - x0 < MIN_BOX_W) x1 = x0 + MIN_BOX_W;
  return { x0, x1, ey, xy: yOf(t.exit_price), ty: t.tp != null ? yOf(t.tp) : null, sy: t.sl != null ? yOf(t.sl) : null };
}

/* The execution arrows of a trade, in the live chart's convention (blue buy / red sell): a long enters with a
   buy and leaves with a sell, a short the other way round. */
function fillSides(t) { return t.side === 'long' ? { entry: 'buy', exit: 'sell' } : { entry: 'sell', exit: 'buy' }; }

/* P&L / price labels next to each other: keep the highest-priority ones that do not overlap an already kept
   one (rects {x, y, w, h, prio}); the input order is the tie-break. Pure. */
function thinLabels(items, pad = 2) {
  const kept = [];
  for (const it of [...(items || [])].sort((a, b) => (b.prio || 0) - (a.prio || 0))) {
    if (kept.every((k) => it.x + it.w + pad <= k.x || k.x + k.w + pad <= it.x || it.y + it.h + pad <= k.y || k.y + k.h + pad <= it.y)) kept.push(it);
  }
  return kept;
}

/* The hover text of a trade. `f` = {price(v), et(ms), usd(v)} (the page's own formatters). */
function tradeTip(t, i, f) {
  const side = t.side === 'long' ? 'Long' : 'Short', why = String(t.exit_reason || '').toUpperCase();
  const lv = [`Entry ${f.price(t.entry_price)}`, t.sl != null ? `SL ${f.price(t.sl)}` : '', t.tp != null ? `TP ${f.price(t.tp)}` : ''].filter(Boolean);
  return `#${i + 1} ${side} · ${f.et(t.entry_ms)} → ${f.et(t.exit_ms).slice(11)} ET\n${lv.join(' · ')}\n`
    + `Exit ${f.price(t.exit_price)}${why ? ` (${why})` : ''} · ${f.usd(t.net)}`;
}

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

/* Claude's show keeps off the SELECTED chart because the order panel and DOM follow it -- and the Backtest tab has
   neither (no trading module loads there), so on it the selected chart is as free as any other. Without this a
   one-chart layout (the Backtest tab's natural one) had NO chart Claude's show could use: the run loaded, the
   chart stayed at the live bars and a status line said why. */
const claudeAvoidsSelected = () => !(typeof window !== 'undefined' && window.HB_PAGE === 'backtest');

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

/* ---- jumping to a trade, and staying there ----
   A jump is several awaits long (a root / interval switch, then history loading chunk by chunk), and the chart
   keeps moving underneath it: a late history answer re-fits the view, a grid rebuild destroys the chart. So a
   jump is not done when focusRange() returns -- it is done when the view has SETTLED on the trade. */
const SETTLE_MS = 900, SETTLE_TRIES = 4, LOAD_WAIT_MS = 15000;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/* true when the chart's visible window holds the bar the trade entered on. */
function viewShows(cell, t) {
  if (!cell.chart || !cell.bars || !cell.bars.length) return false;
  const vr = cell.chart.timeScale().getVisibleLogicalRange(), i = D.barIndexAt(cell.bars, t.entry_ms);
  return !!vr && i >= 0 && vr.from <= i && i <= vr.to;
}

/* After the first focusRange: watch for the view to be pulled elsewhere and bring it back (reach again if the
   history it needs is gone, focus again) a few times, until it holds -- or the viewer touches the chart, a newer
   jump starts (isCurrent() false) or the chart is destroyed. Resolves true once the view holds the trade. */
async function settleFocus(cell, t, { isCurrent = () => true, wait = sleep, tries = SETTLE_TRIES, gapMs = SETTLE_MS } = {}) {
  let touched = false;
  const mark = () => { touched = true; };
  const box = cell.box || cell.el;
  const evs = ['pointerdown', 'wheel'];
  if (box && box.addEventListener) for (const e of evs) box.addEventListener(e, mark, { passive: true });
  try {
    for (let k = 0; k < tries; k++) {
      await wait(gapMs);
      if (touched || !isCurrent() || !cell.chart) return false;
      if (viewShows(cell, t)) return true;
      if (!(await cell.reach(t.entry_ms, () => {}))) return false;
      if (touched || !isCurrent() || !cell.chart) return false;
      cell.focusRange(t.entry_ms, t.exit_ms);
    }
    return viewShows(cell, t);
  } finally {
    if (box && box.removeEventListener) for (const e of evs) box.removeEventListener(e, mark);
  }
}

/* The jump itself, with everything it touches passed in (env) so it can be exercised without a page:
   env = {U (HBTesterUI), page, tester (reachSpec), cat (specLabel), wait}. `target` names the chart (Claude's
   show, already planned); without it the chart comes from showPlan (`avoidSelected`: Claude's rule, else a
   click's). A chart that disappears mid-jump (a grid rebuild) is re-planned once. */
let jumpToken = 0;
async function runJump(env, i, target = null, { select = true, avoidSelected = false, replanned = false } = {}) {
  const { U, page, tester, cat } = env, wait = env.wait || sleep;
  const b = U.bundle, t = b && b.trades[i];
  if (!t) return;
  const token = ++jumpToken, current = () => token === jumpToken;
  U.select(i);
  const root = b.run.strategy.root, cells = page.cells(), rootOf = (c) => (c.shown || c.cfg).root;
  let cell = target;
  if (!cell) {
    const plan = showPlan(cells.map(env.chartFacts), cells.indexOf(page.cur()), root, { avoidSelected });
    if (plan.index < 0) { page.sbNote(plan.reason); return; }
    cell = cells[plan.index];
  }
  // re-checked at the moment it is touched: never a replaying chart, never one with accounts or an algo
  if (cell.replay || !cells.includes(cell)) { page.sbNote('That chart is replaying (or gone): left it alone'); return; }
  if (env.chartFacts(cell).tradeReady) { page.sbNote('That chart has accounts or an algo on it: left it alone'); return; }
  const gone = () => !page.cells().includes(cell);
  const again = () => (!replanned && current() ? runJump(env, i, null, { select: false, avoidSelected, replanned: true }) : undefined);
  if (select) page.select(cell);
  const spec = tester.reachSpec(cell.cfg.spec, t.entry_ms, page.clockMs());
  if (rootOf(cell) !== root || spec !== cell.cfg.spec) {
    const specChanged = spec !== cell.cfg.spec;
    const waiting = cell.whenLoaded();
    cell.update({ root, spec });
    // an answer that never comes (a refused change, a dropped socket) must not hang the jump for good
    const loaded = await Promise.race([waiting, wait(LOAD_WAIT_MS).then(() => 'late')]);
    if (!current()) return;
    if (gone()) return again();
    if (loaded === false) return;
    if (specChanged) page.sbNote(`Switched to ${cat.specLabel(spec)} bars to reach ${t.date}`);
  }
  const day = t.date;
  const ok = await cell.reach(t.entry_ms, (firstMs) => page.sbNote(`Loading history back to ${day}… (at ${new Date(firstMs).toISOString().slice(0, 10)})`));
  if (!current()) return;
  if (gone()) return again();
  if (!ok) { page.sbNote(`${day} is older than this chart's history can load`); return; }
  page.sbNote('');
  cell.focusRange(t.entry_ms, t.exit_ms);
  const held = await settleFocus(cell, t, { isCurrent: () => current() && !gone(), wait });
  if (!held && current() && gone()) return again();
}

/* ================================================================== browser half ================================================================== */

const PLOT_PANE_H = 90;   // px, = cell.js PANE_H: the gate/indicator sub-pane
const FONT_SM = '10px -apple-system, BlinkMacSystemFont, "Trebuchet MS", Roboto, Ubuntu, sans-serif';
const ZONE_ALPHA = 0.14, ZONE_ALPHA_SEL = 0.28;   // the boxes: light for every trade, stronger for the selected one
const MAX_ARROWS = 400, MAX_LABELS = 120;          // beyond this many trades in view, arrows / P&L text step out

/* Text with a thin background-coloured outline, so it reads over candles without a plate behind it. */
function haloText(ctx, text, x, y, color, P) {
  const a = ctx.globalAlpha;
  ctx.lineWidth = 4; ctx.lineJoin = 'round';
  ctx.strokeStyle = P.bg; ctx.globalAlpha = a * 0.9;
  ctx.strokeText(text, x, y);
  ctx.globalAlpha = a;
  ctx.fillStyle = color;
  ctx.fillText(text, x, y);
}

/* A series-primitive on cell.candles (the plugin shape Lightweight Charts wants: attached/detached,
   updateAllViews, paneViews — Hook in tradelines.js is the same idea). Reads HBTesterUI live at every draw()
   rather than being pushed state, since it is a process-wide singleton already. Two views: the position boxes
   (translucent, over the candles like TradingView's own position tool -- a short trade sits inside one candle
   and would vanish behind it), then everything else on top. */
class TesterMarks {
  constructor(cell, overlay) {
    this.cell = cell;
    this.overlay = overlay;
    this.chart = null; this.series = null; this.requestUpdate = null;
    this.hits = [];                // what was last drawn, for the overlay's hover and click
    this.epoch = 0; this.frameEpoch = -1; this.frame = null;
    this._views = [
      { zOrder: () => 'normal', renderer: () => ({ draw: (t) => this.draw(t, 'zones') }) },
      { zOrder: () => 'top', renderer: () => ({ draw: (t) => this.draw(t, 'marks') }) }];
  }
  attached({ chart, series, requestUpdate }) { this.chart = chart; this.series = series; this.requestUpdate = requestUpdate; }
  detached() { this.chart = this.series = null; }
  updateAllViews() { this.epoch++; }
  paneViews() { return this._views; }

  /* The price range the selected trade needs to be seen whole -- its entry, exit, SL and TP, and the levels its
     session recorded -- so focusing a trade never leaves its stop or target off the top of the chart. Nothing
     when no trade is selected, or it is not inside the window being autoscaled. */
  autoscaleInfo(start, end) {
    const U = window.HBTesterUI, b = U.bundle, cell = this.cell, ov = this.overlay;
    if (!b || U.hidden || U.selected == null || !ov.shows() || !cell.bars.length) return null;
    const hit = ov.inRange.find((e) => e.i === U.selected);
    if (!hit) return null;
    const i = D.barIndexAt(cell.bars, hit.t.entry_ms), j = D.barIndexAt(cell.bars, hit.t.exit_ms);
    if (i > end || j < start) return null;
    const px = [hit.t.entry_price, hit.t.exit_price, hit.t.sl, hit.t.tp];
    if (U.rules) for (const h of (b.plots && b.plots.hlines) || []) if (h.date === hit.t.date && !DIMMED.test(h.name)) px.push(h.price);   // the live levels, not the leg that never filled
    const v = px.filter((x) => Number.isFinite(x));
    return v.length ? { priceRange: { minValue: Math.min(...v), maxValue: Math.max(...v) } } : null;
  }
  redraw() { if (this.requestUpdate) this.requestUpdate(); }

  /* Everything about this frame in pixels, computed once for both views. */
  project(width, height) {
    const U = window.HBTesterUI, b = U.bundle, cell = this.cell, ov = this.overlay;
    const empty = { trades: [], levels: [], labels: [], width, height };
    if (!b || !cell.shown || cell.shown.root !== b.run.strategy.root || !this.chart) return empty;
    const P = cell.P, bars = cell.bars, ts = this.chart.timeScale(), vr = ts.getVisibleLogicalRange();
    if (!bars.length || !vr) return empty;
    const from = Math.max(0, Math.floor(vr.from)), to = Math.min(bars.length - 1, Math.ceil(vr.to));
    const bctx = { bars, isTime: cell.isTime(), barMs: cell.barMs(), coord: (i) => ts.logicalToCoordinate(i) };
    const xOf = (ms) => D.timeToX(ms, bctx);
    const yOf = (price) => this.series.priceToCoordinate(price);
    const fromMs = bars[from].ms, toMs = bars[to].ms + (bctx.barMs || 0), sp = ts.options().barSpacing;
    const out = { P, sp, width, height, trades: [], levels: [], labels: [], selected: U.selected };

    if (!U.hidden) {
      for (const { t, i } of ov.inRange) {
        if (t.exit_ms < fromMs || t.entry_ms > toMs) continue;
        const g = boxGeometry(t, xOf, yOf);
        if (g) out.trades.push({ t, i, g, sel: i === U.selected });
      }
    }
    if (U.rules) this.projectLevels(out, b, bars, from, to, xOf, yOf, ov.sessions(bars));
    return out;
  }

  projectLevels(out, b, bars, from, to, xOf, yOf, sessions) {
    const hlines = (b.plots && b.plots.hlines) || [], byDate = new Map(), ts = this.chart.timeScale();
    for (const item of hlines) {
      const span = sessions.get(item.date);
      if (!span || span[1] < from || span[0] > to) continue;
      const y = yOf(item.price);
      if (y == null) continue;
      // from when the strategy placed it (records from before 2026-09-29 have no stamp: the session's first bar)
      // to its session window's close, never outside the session's own bars
      const c0 = ts.logicalToCoordinate(span[0]), c1 = ts.logicalToCoordinate(span[1] + 1);
      const s0 = item.t_ms != null ? xOf(item.t_ms) : null, s1 = item.end_ms != null ? xOf(item.end_ms) : null;
      const x0 = s0 != null && c0 != null ? Math.max(s0, c0) : c0, x1 = s1 != null && c1 != null ? Math.min(s1, c1) : c1;
      if (x0 == null || x1 == null || x1 <= x0) continue;
      const st = hlineStyle(item, out.P);
      const lv = { x0, x1, y, item, st };
      out.levels.push(lv);
      if (!byDate.has(item.date)) byDate.set(item.date, []);
      byDate.get(item.date).push(lv);
    }
    // labels: one stack per session, at the right-hand end of what is on screen
    for (const rows of byDate.values()) {
      const cand = dedupeLevels(rows.map((r) => r.item)).map((it) => rows.find((r) => r.item === it))
        .filter((r) => labelsFit(Math.max(r.x0, 0), Math.min(r.x1, out.width)))
        .map((r) => ({ y: r.y, x: Math.min(r.x1, out.width) - 4, item: r.item, st: r.st, dim: r.st.dim }));
      out.labels.push(...placeLabels(cand, LABEL_ROW_H, LABEL_ROW_H / 2, Math.max(LABEL_ROW_H / 2, out.height - LABEL_ROW_H / 2)));
    }
  }

  frameFor(mediaSize) {
    if (this.frameEpoch !== this.epoch || !this.frame || this.frame.width !== mediaSize.width || this.frame.height !== mediaSize.height) {
      this.frame = this.project(mediaSize.width, mediaSize.height);
      this.frameEpoch = this.epoch;
      this.hits = this.hitsOf(this.frame);
    }
    return this.frame;
  }

  hitsOf(f) {
    const hits = f.levels.map((l) => ({ kind: 'level', x0: l.x0, x1: l.x1, y: l.y, tip: hlineTip(l.item) }));
    for (const s of f.trades) {
      const ys = [s.g.ey, s.g.ty, s.g.sy].filter((y) => y != null);
      hits.push({ kind: 'trade', i: s.i, t: s.t, x0: s.g.x0, x1: s.g.x1, y0: Math.min(...ys), y1: Math.max(...ys) });
    }
    return hits;
  }

  draw(target, which) {
    if (!this.chart || !this.series) return;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const f = this.frameFor(mediaSize);
      if (which === 'zones') this.drawZones(ctx, f); else this.drawMarks(ctx, f);
    });
  }

  /* TradingView's position boxes: a green one entry -> TP, a red one entry -> SL, over the trade's own time span. */
  drawZones(ctx, f) {
    const outline = f.trades.length <= MAX_ARROWS;     // a fortnight of thousands: fills only
    for (const s of f.trades) {
      const { g } = s;
      const zones = [[g.ty, f.P.up], [g.sy, f.P.down]];
      for (const [y, color] of zones) {
        if (y == null) continue;
        const top = Math.min(g.ey, y), h = Math.abs(y - g.ey);
        ctx.globalAlpha = s.sel ? ZONE_ALPHA_SEL : ZONE_ALPHA;
        ctx.fillStyle = color; ctx.fillRect(g.x0, top, g.x1 - g.x0, h);
        // an outline keeps a zone readable on a candle of its own colour, and a thin one from vanishing
        if (!outline && !s.sel) continue;
        const edge = (w, style, a) => { ctx.globalAlpha = a; ctx.lineWidth = w; ctx.strokeStyle = style; ctx.strokeRect(g.x0 + 0.5, top + 0.5, g.x1 - g.x0 - 1, Math.max(0, h - 1)); };
        edge(3, f.P.bg, s.sel ? 0.7 : 0.45);            // a casing, so the outline holds on a candle of its own colour
        edge(1, color, s.sel ? 1 : 0.7);
      }
    }
    ctx.globalAlpha = 1;
  }

  drawMarks(ctx, f) {
    const P = f.P;
    if (f.levels.length) this.drawLevels(ctx, f);
    if (!f.trades.length) return;
    const ts = this.chart.timeScale(), bars = this.cell.bars, arrows = f.trades.length <= MAX_ARROWS;
    const wantText = f.trades.length <= MAX_LABELS, labels = [];
    for (const s of f.trades) {
      const { t, g } = s, win = t.net >= 0;
      // the entry line, and the connector to where it ended -- in the trade's own P&L colour
      ctx.lineWidth = s.sel ? 1.5 : 1;
      ctx.strokeStyle = P.text2; ctx.setLineDash([]);
      ctx.beginPath(); ctx.moveTo(g.x0, Math.round(g.ey) + 0.5); ctx.lineTo(g.x1, Math.round(g.ey) + 0.5); ctx.stroke();
      if (g.xy != null) {
        ctx.strokeStyle = win ? P.up : P.down; ctx.globalAlpha = s.sel ? 1 : 0.8;
        ctx.setLineDash(s.sel ? [3, 3] : []);
        ctx.beginPath(); ctx.moveTo(g.x0, g.ey); ctx.lineTo(g.x1, g.xy); ctx.stroke();
        ctx.setLineDash([]); ctx.globalAlpha = 1;
      }
      if (arrows) {
        const sides = fillSides(t), col = (side) => (side === 'buy' ? P.accent : P.down);
        this.arrow(ctx, ts, bars, t.entry_ms, g.ey, col(sides.entry));
        if (g.xy != null) this.arrow(ctx, ts, bars, t.exit_ms, g.xy, col(sides.exit));
      }
      if (wantText && g.xy != null && !s.sel) {              // the exit's P&L, right of where the box ends
        ctx.font = FONT_SM;
        const text = usd(t.net);
        labels.push({ x: g.x1 + 6, y: g.xy - 6, w: ctx.measureText(text).width, h: 12, text, color: win ? P.up : P.down });
      }
    }
    if (wantText) this.drawPnl(ctx, f, labels);
    const sel = f.trades.find((s) => s.sel);
    if (sel) this.drawTags(ctx, f, sel);
  }

  arrow(ctx, ts, bars, ms, y, color) {
    const i = D.barIndexAt(bars, ms);
    if (i < 0) return;
    const x = ts.logicalToCoordinate(i);
    if (x == null) return;
    const a = TP.execArrow(x, y, ts.options().barSpacing);
    ctx.beginPath();
    a.pts.forEach(([px, py], k) => (k ? ctx.lineTo(px, py) : ctx.moveTo(px, py)));
    ctx.closePath();
    ctx.fillStyle = color; ctx.fill();
    ctx.lineWidth = 1; ctx.strokeStyle = this.cell.P.bg; ctx.globalAlpha = 0.9; ctx.stroke(); ctx.globalAlpha = 1;   // a red arrow on a red candle must still read
  }

  drawPnl(ctx, f, labels) {
    ctx.font = FONT_SM; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    for (const l of thinLabels(labels)) haloText(ctx, l.text, l.x, l.y + l.h / 2, l.color, f.P);
  }

  /* The selected trade's price tags, right of its box: TP, SL, entry and exit (with its P&L), stacked apart. */
  drawTags(ctx, f, s) {
    const { t, g } = s, fmt = (v) => hlinePrice(v);
    const rows = [];
    if (g.ty != null) rows.push({ y: g.ty, text: `TP ${fmt(t.tp)}`, color: f.P.up });
    if (g.sy != null) rows.push({ y: g.sy, text: `SL ${fmt(t.sl)}`, color: f.P.down });
    rows.push({ y: g.ey, text: `Entry ${fmt(t.entry_price)}`, color: f.P.text2 });
    if (g.xy != null) rows.push({ y: g.xy, text: `Exit ${fmt(t.exit_price)}  ${usd(t.net)}`, color: t.net >= 0 ? f.P.up : f.P.down });
    ctx.font = FONT_SM; ctx.textAlign = 'left'; ctx.textBaseline = 'middle';
    for (const r of stackLabels(rows, LABEL_ROW_H + 1, 8, Math.max(8, f.height - 8))) haloText(ctx, r.text, g.x1 + 6, r.y, r.color, f.P);
  }

  /* Every level as a short segment across its own window, then its compact label. */
  drawLevels(ctx, f) {
    for (const l of f.levels) {
      ctx.save();
      ctx.globalAlpha = l.st.alpha; ctx.strokeStyle = l.st.color; ctx.lineWidth = 1; ctx.setLineDash(l.st.dash);
      const y = Math.round(l.y) + 0.5;
      ctx.beginPath(); ctx.moveTo(l.x0, y); ctx.lineTo(l.x1, y); ctx.stroke();
      ctx.restore();
    }
    ctx.font = FONT_SM; ctx.textAlign = 'right'; ctx.textBaseline = 'middle';
    for (const r of f.labels) {
      ctx.save();
      ctx.globalAlpha = r.st.alpha;
      haloText(ctx, levelText(r.item), r.x, r.y, r.st.color, f.P);
      ctx.restore();
    }
  }
}

/* One overlay per chart. It shows a run when HBTesterUI.bundle exists and this cell shows that bundle's
   root; within that, the two sub-tab-bar ticks are independent -- "Hide trades" silences the boxes, arrows and
   P&L, "Rules" silences the recorded geometry (the levels and the series plots). */
class Overlay {
  constructor(cell, page) {
    this.cell = cell;
    this.page = page || PAGE;
    this.dead = false;
    this.plotSeries = new Map();   // plot name -> {series, data, color, pane}
    this.plotsSig = null;          // the JSON of what those series were built for (bundle-independent: names + panes)
    this.plotsBundle = null;
    this.plotPane = null;          // the sub-pane index those series live in, or null
    this.paneTotal = 0;            // px of all panes before ours was added: what pane 0's share is worked out from
    this.inRange = [];             // [{t, i}] the run's trades inside the loaded bars (see recompute)
    this._sess = null; this._sessKey = null;
    this.bar0 = null;              // bars[0].ms as of the last recompute
    this.lastBundle = undefined;
    this.lastHidden = undefined;
    this.lastRules = undefined;
    this.marks = new TesterMarks(cell, this);
    cell.candles.attachPrimitive(this.marks);
    this.layer = document.createElement('div');
    this.layer.className = 'hb-tester-layer';
    this.tip = document.createElement('div');
    this.tip.className = 'ev-tip hb-tester-tip';
    this.tip.hidden = true;
    this.layer.appendChild(this.tip);
    cell.el.appendChild(this.layer);
    this.legend = document.createElement('div');       // one entry per plotted series, under the chart's own legend
    this.legend.className = 'lg-tester';
    this.legend.hidden = true;
    const lg = cell.el.querySelector('.legend');
    if (lg) lg.appendChild(this.legend);
    this.onMove = (p) => this.onCrosshair(p);
    this.onClick = (p) => this.clickTrade(p);
    this.onRange = () => this.legendValues(null);
    // the bottom panel opening / closing, a new layout: the stretch factors are px-sized against the OLD height
    this.ro = typeof ResizeObserver !== 'undefined' && cell.box ? new ResizeObserver(() => this.refit()) : null;
    if (this.ro) this.ro.observe(cell.box);
    if (cell.chart) {
      cell.chart.subscribeCrosshairMove(this.onMove);
      cell.chart.subscribeClick(this.onClick);
      cell.chart.timeScale().subscribeVisibleLogicalRangeChange(this.onRange);
    }
    this.unsub = window.HBTesterUI.on(() => this.onNotify());
    this.onNotify();
  }

  /* This cell is showing the loaded run's instrument. */
  shows() {
    const b = window.HBTesterUI.bundle, cell = this.cell;
    return !!(b && cell.shown && cell.shown.root === b.run.strategy.root);
  }

  /* date -> [first, last] bar index, rebuilt only when the bars change (a live bar, older history). */
  sessions(bars) {
    const key = `${bars.length}|${bars.length ? bars[0].ms : 0}`;
    if (key !== this._sessKey) { this._sess = sessionIndex(bars); this._sessKey = key; }
    return this._sess;
  }

  /* The thing under the mouse: a trade's box when the pointer is inside it (the smallest, when they overlap),
     else a level within 4 px of its segment, else a trade box within 4 px of an edge. */
  hitAt(x, y) {
    const box = (pad) => {
      let best = null, area = Infinity;
      for (const h of this.marks.hits) {
        if (h.kind !== 'trade' || x < h.x0 - pad || x > h.x1 + pad || y < h.y0 - pad || y > h.y1 + pad) continue;
        const a = (h.x1 - h.x0 + 2 * pad) * (h.y1 - h.y0 + 2 * pad);
        if (a < area) { area = a; best = h; }
      }
      return best;
    };
    const inside = box(0);
    if (inside) return inside;
    let best = null, bestD = 5;
    for (const h of this.marks.hits) {
      if (h.kind !== 'level' || x < h.x0 || x > h.x1) continue;
      const d = Math.abs(y - h.y);
      if (d < bestD) { bestD = d; best = h; }
    }
    return best || box(4);
  }

  tipOf(h) {
    if (h.kind === 'level') return h.tip;
    const T = window.HBTester, cell = this.cell, tick = cell.dtick ? cell.dtick() : 0.01;
    return tradeTip(h.t, h.i, { price: (v) => window.HBCatalog.fmtPrice(v, tick), et: T.fmtEt, usd });
  }

  onCrosshair(p) {
    if (this.dead || !this.cell.chart) return;
    this.hoverTip(p);
    this.legendValues(p);
  }

  hoverTip(p) {
    if (!p || !p.point || !this.marks.hits.length) { this.tip.hidden = true; return; }
    const { x, y } = p.point, best = this.hitAt(x, y);
    if (!best) { this.tip.hidden = true; return; }
    this.tip.textContent = this.tipOf(best);
    this.tip.hidden = false;
    const w = this.layer.clientWidth, tw = this.tip.offsetWidth;
    this.tip.style.left = `${Math.max(4, Math.min(w - tw - 4, x + 12))}px`;
    this.tip.style.top = `${Math.max(4, y - 34)}px`;
  }

  /* A click on a trade's box selects it (List of trades follows), unless a drawing tool is in hand. */
  clickTrade(p) {
    if (this.dead || !p || !p.point || !this.marks.hits.length) return;
    if (this.page && this.page.tool && this.page.tool() !== 'cursor') return;
    const h = this.hitAt(p.point.x, p.point.y);
    if (h && h.kind === 'trade' && window.HBTesterUI.selected !== h.i && !window.HBTesterUI.hidden) window.HBTesterUI.select(h.i);
  }

  /* HBTesterUI.on() fires for a bundle load, a Recent-runs load, a strategy switch, a trade selection AND a
     Hide-trades toggle — it carries no reason. Only a bundle, hidden or rules change is worth a recompute
     (re-filtering the trades, rebuilding the plot series); every other call (a selection change) just needs the
     primitive redrawn, since it reads HBTesterUI.selected live at draw time. */
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
    this.cell.setExtraMarkers('tester', []);     // the trades are the primitive's now; never leave 2026-09-28's markers behind
    this.inRange = this.shows() && b ? tradesInRange(b.trades, bars, this.cell.barMs()) : [];
    this.rebuildPlots(this.shows() && window.HBTesterUI.rules, b);
  }

  /* The run's series plots. A price-scale series joins the candles' pane; the rest share one sub-pane below
     (they are gate readings and oscillators, meaningless stretched over the candles). The series are rebuilt
     only when what they are built FOR changes -- the set of series that have data in the loaded bars, and which
     pane each belongs on (a chart that has not loaded its bars yet cannot say, so it is re-judged as they land).
     Each series gets a legend entry, its value following the crosshair. */
  rebuildPlots(on, b) {
    const chart = this.cell.chart, bars = this.cell.bars;
    const raw = on && b && b.plots ? b.plots.plots || {} : {};
    const plan = [];
    for (const name of Object.keys(raw)) {
      const data = plotPoints(raw[name], bars);
      if (data.length) plan.push({ name, data, pane: plotPane(raw[name], bars), flat: isConstant(raw[name]) });
    }
    const sig = JSON.stringify(plan.map((p) => [p.name, p.pane, p.flat]));
    if (b !== this.plotsBundle || sig !== this.plotsSig) {
      this.dropPlots();
      this.plotsBundle = b; this.plotsSig = sig;
      if (plan.length && chart) this.buildPlots(plan);
    }
    for (const p of plan) { const e = this.plotSeries.get(p.name); if (e) { e.data = p.data; e.series.setData(p.data); } }
    this.renderLegend();
  }

  buildPlots(plan) {
    const chart = this.cell.chart, LW = window.LightweightCharts, Cat = window.HBCatalog, P = this.cell.P;
    const subs = plan.some((p) => p.pane === 'sub');
    if (subs) {
      this.paneTotal = chart.panes().reduce((n, pn) => n + pn.getHeight(), 0);
      this.plotPane = chart.panes().length;
    }
    plan.forEach((p, k) => {
      const color = p.flat ? P.text2 : Cat.LINE_COLORS[k % Cat.LINE_COLORS.length];
      const sparse = !p.flat && p.data.length * 20 < this.cell.bars.length;      // one reading a day: show the readings
      const series = chart.addSeries(LW.LineSeries, { color, lineWidth: 1, lineStyle: p.flat ? LW.LineStyle.Dashed : LW.LineStyle.Solid,
        lastValueVisible: false, priceLineVisible: false, pointMarkersVisible: sparse, crosshairMarkerVisible: !p.flat },
      p.pane === 'sub' ? this.plotPane : 0);
      this.plotSeries.set(p.name, { series, data: p.data, color, pane: p.pane });
    });
    if (subs) this.sizePanes();
  }

  /* Pane 0 keeps what is left of the chart's height once the sub-panes have their PANE_H (cell.build's rule):
     Lightweight Charts splits by stretch factor, and a new pane defaults to a factor that is not in px. */
  sizePanes() {
    const panes = this.cell.chart.panes(), n = panes.length - 1;
    if (n < 1) return;
    if (this.plotPane != null && panes[this.plotPane]) panes[this.plotPane].setStretchFactor(PLOT_PANE_H);
    panes[0].setStretchFactor(Math.max(this.paneTotal - n * PLOT_PANE_H, n * PLOT_PANE_H));
  }

  /* The chart changed height: keep the sub-pane at PANE_H and give pane 0 the rest. Lightweight Charts lays the
     resized panes out after its own observer, so this waits two frames and then reads the heights as they are. */
  refit() {
    if (this.dead || this.plotPane == null || this.refitting) return;
    this.refitting = true;
    requestAnimationFrame(() => requestAnimationFrame(() => {
      this.refitting = false;
      const chart = this.cell.chart;
      if (this.dead || !chart || this.plotPane == null) return;
      this.paneTotal = chart.panes().reduce((n, pn) => n + pn.getHeight(), 0);
      this.sizePanes();
    }));
  }

  dropPlots() {
    const chart = this.cell.chart;
    const had = this.plotSeries.size, pane = this.plotPane;
    for (const e of this.plotSeries.values()) { if (chart) { try { chart.removeSeries(e.series); } catch (_) { /* already gone */ } } }
    this.plotSeries.clear();
    this.plotPane = null;
    this.plotsSig = null;
    // the sub-pane we opened is now empty: close it, or every toggle leaves a dead band behind
    if (had && chart && pane != null && chart.removePane) {
      try { chart.removePane(pane); } catch (_) { /* already gone */ }
      const panes = chart.panes();
      if (panes.length > 1) panes[0].setStretchFactor(Math.max(this.paneTotal - (panes.length - 1) * PLOT_PANE_H, (panes.length - 1) * PLOT_PANE_H));
    }
  }

  renderLegend() {
    this.legend.replaceChildren();
    this.legend.hidden = !this.plotSeries.size;
    for (const [name, e] of this.plotSeries) {
      const row = document.createElement('div');
      row.className = 'lg-row lg-tst';
      const sw = document.createElement('span'); sw.className = 'lg-sw'; sw.style.background = e.color;
      const label = document.createElement('span'); label.className = 'lg-label'; label.textContent = name;
      e.val = document.createElement('span'); e.val.className = 'lg-vals';
      row.append(sw, label, e.val);
      this.legend.appendChild(row);
    }
    this.legendValues(null);
  }

  /* Each series' value at the crosshair's bar (its last reading at or before it); off the chart, at the last bar
     in view (TradingView's legend), so scrolling to a day shows that day's reading. */
  legendValues(p) {
    if (!this.plotSeries.size) return;
    let t = p && p.time != null ? p.time : null;
    if (t == null) {
      const vr = this.cell.chart.timeScale().getVisibleLogicalRange(), bars = this.cell.bars;
      if (vr && bars.length) t = bars[Math.max(0, Math.min(bars.length - 1, Math.floor(vr.to)))].tt;
    }
    for (const e of this.plotSeries.values()) {
      const v = t != null ? valueAt(e.data, t) : null;
      if (e.val) e.val.textContent = v == null ? '' : hlinePrice(v);
    }
  }

  destroy() {
    this.dead = true;
    this.unsub();
    if (this.ro) this.ro.disconnect();
    if (this.cell.chart) {
      this.cell.candles.detachPrimitive(this.marks);
      this.cell.chart.unsubscribeCrosshairMove(this.onMove);
      this.cell.chart.unsubscribeClick(this.onClick);
      this.cell.chart.timeScale().unsubscribeVisibleLogicalRangeChange(this.onRange);
    }
    this.dropPlots();
    this.legend.remove();
    this.layer.remove();
    this.cell.setExtraMarkers('tester', []);
  }
}

/* What showPlan needs to know about one live chart. Fails closed on the Charts tab: no HBTradeUI to
   ask = trade-ready, so a chart's trade state is never guessed wrong. The Backtest tab has no
   HBTradeUI at all -- EVER, not just "not answered yet" -- so failing closed there would read every
   chart as trade-ready and leave showPlan (Claude's show_on_chart, and a List-of-trades click) with
   nowhere to land; every chart is free instead. */
function chartFacts(c) {
  const onBacktest = typeof window !== 'undefined' && window.HB_PAGE === 'backtest';
  const TU = typeof window !== 'undefined' ? window.HBTradeUI : null;
  const tr = TU && TU.tradeOf ? TU.tradeOf(c) : null;
  return { root: (c.shown || c.cfg).root, replay: !!c.replay,
    tradeReady: !onBacktest && (!tr || !!(c.cfg && c.cfg.algo) || !!(tr.accounts && tr.accounts.length)) };
}

let PAGE = null;   // the page interface (same singleton every overlay() call hands us): jump()'s own home
function overlay(cell, page) {
  PAGE = page;
  return new Overlay(cell, page);
}

/* Jump to trade i (ruling S20): select it, pick the chart showing the run's root (falling back to the
   selected one), switch it to whatever interval lets scroll-back reach the trade's entry under the client's
   200,000-bar cap, load history back to it, then zoom -- and stay with it until the view has settled there
   (see runJump). Every early return leaves the status-bar note as whatever last explained why. The chart comes
   from showPlan (a trade-ready or replaying chart is never used); `target` (Claude's show, already planned)
   names it instead, and select: false leaves the selection alone. */
function jump(i, target = null, opts = {}) {
  if (!PAGE) return Promise.resolve();
  return runJump({ U: window.HBTesterUI, page: PAGE, tester: window.HBTester, cat: window.HBCatalog, chartFacts }, i, target, opts);
}

const api = { overlay, jump, runJump, settleFocus, viewShows, tradesInRange, sessionIndex, plotPoints, plotPane, isConstant, valueAt,
  showPlan, claudeAvoidsSelected, focusTrade, chartFacts, hlineStyle, hlineLabel, hlineTip, levelText, stackLabels, placeLabels, dedupeLevels, labelsFit,
  boxGeometry, fillSides, thinLabels, tradeTip, LABEL_MIN_PX, MIN_BOX_W };
if (typeof window !== 'undefined') window.HBTesterLayer = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
