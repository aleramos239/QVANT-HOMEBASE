/* Homebase Charts — HBFlowLayer: what the bars' tick fields add on the price pane, one overlay per chart:
     - heatmap trade bubbles (param `bubbles` of the "heatmap" indicator): executed trades of >= `bubbleMin`
       contracts per second, price and side, as circles sized by their size, behind the candles;
     - sweeps (param `sweeps` of "bigprints"): one aggressor walking several price levels inside one
       millisecond, as a vertical span from the first to the last price with a chevron on the side;
     - stop runs ("stoprun"): a burst of sweeps through the highest high / lowest low of the last N bars, the
       swing's level as a dashed line to the bar that broke it, an arrow and the contracts;
     - fair value gaps ("fvg"): a box per gap, from its first bar to the last bar it was open on;
     - exhaustion ("exhaust"): a big one-sided push to a new extreme that made no progress and was given back,
       a cap at the push's extreme and an arrow on the bar that confirmed it.
   They read `bar.bub` / `bar.sw` (the server sends them on the bar wire's own `flow` flag, so cell.need()
   asks for them only while one of these is on) and `bar.d` (delta, always sent). Pure pieces live in
   flowmath.js (Node-tested).
   Order-flow apps (2026-10-21), each made and attached only while its indicator is on (so a chart without them
   carries the four layers above and nothing else):
     - "bigtrades" (bar.ag, flow): the rebuilt aggressor orders as bubbles, optionally clustered (Bookmap rules);
     - "npoc" (bar.fp): a dashed line from each still-untouched POC to the right edge;
     - "tpo" (bar.fp for mode traded): the newest session's TPO letters / blocks docked at the right edge;
     - "pzone" (bar.fp): stacked profile zones, a band where a delta outlier, single prints and a low volume node line up;
     - "cstat" (bar.d v n dmax dmin, bar.fpn): a text strip of cluster statistics under the candles;
     - "dturn" / "dstr" / "mwabs": delta turnaround and delta strength arrows, MotiveWave absorption marks. */
(function () {
'use strict';
if (typeof window === 'undefined' || !window.HBLayers || !window.HBLiquidity || !window.HBFlowMath) return;
const { logicalAt } = window.HBLiquidity, M = window.HBFlowMath;

const PAINT_MS = 250;
const inst = (cell, id) => (cell.cfg.indicators || []).find((x) => x.id === id && x.visible !== false) || null;

class BubbleLayer extends window.HBLayers.Layer {
  constructor(P, ov) { super(P); this.ov = ov; }
  z() { const h = inst(this.ov.cell, 'heatmap'); return h && h.params && h.params.bubbleFront === true ? 'top' : 'bottom'; }   // read on every paint
  draw(target) { this.ov.drawBubbles(target); }
}
class SweepLayer extends window.HBLayers.Layer {
  constructor(P, ov) { super(P); this.ov = ov; }
  z() { return 'top'; }
  draw(target) { this.ov.drawSweeps(target); }
}

class FvgLayer extends window.HBLayers.Layer {
  constructor(P, ov) { super(P); this.ov = ov; }
  z() { return 'bottom'; }
  draw(target) { this.ov.drawFvg(target); }
}

class RunLayer extends window.HBLayers.Layer {
  constructor(P, ov) { super(P); this.ov = ov; }
  z() { return 'top'; }
  draw(target) { this.ov.drawRuns(target); }
}

/* The order-flow apps' layers: (P, ov) like the four above, but made by Overlay.sync() only while one of their indicators is on. */
const layerOf = (z, draw) => class extends window.HBLayers.Layer {
  constructor(P, ov) { super(P); this.ov = ov; }
  z() { return typeof z === 'function' ? z(this.ov) : z; }
  draw(target) { this.ov[draw](target); }
};
const OrderLayer = layerOf((ov) => { const g = inst(ov.cell, 'bigtrades'); return g && g.params && g.params.front === true ? 'top' : 'bottom'; }, 'drawOrders');   // "bigtrades"
const NakedLayer = layerOf('bottom', 'drawNaked');      // "npoc"
const TpoLayer = layerOf('bottom', 'drawTpo');          // "tpo"
const ZoneLayer = layerOf('bottom', 'drawZones');       // "pzone"
const StatLayer = layerOf('bottom', 'drawStats');       // "cstat"
const MarkLayer = layerOf('top', 'drawMarks');          // "dturn", "dstr", "mwabs"
const LAZY = { ord: [['bigtrades'], OrderLayer], npoc: [['npoc'], NakedLayer], tpo: [['tpo'], TpoLayer], zone: [['pzone'], ZoneLayer],
  stat: [['cstat'], StatLayer], mark: [['dturn', 'dstr', 'mwabs'], MarkLayer] };

const FONT = '11px -apple-system, BlinkMacSystemFont, sans-serif', SMALL = '10px -apple-system, BlinkMacSystemFont, sans-serif';
const font = (px) => `${px}px -apple-system, BlinkMacSystemFont, sans-serif`;      // font(11) === FONT, font(10) === SMALL
/* Settings (Inputs / Style tabs, flowdefs.js `settings`): each reader gives the setting, or today's hard-coded value when it is missing or junk. */
const pn = (v, d) => (v != null && v !== '' && Number.isFinite(+v) ? +v : d);
const pb = (v, d) => (typeof v === 'boolean' ? v : d);
const pc = (v, list, d) => (list.includes(v) ? v : d);
const sc = (i, key, fb) => (window.HBCatalog && window.HBCatalog.styleColor ? window.HBCatalog.styleColor(i, key, fb) : fb);   // the Style tab's colour, else `fb`
const dashOf = (v, dashed, def) => { const m = pc(v, ['solid', 'dashed', 'dotted'], def); return m === 'solid' ? [] : m === 'dotted' ? [1, 2] : dashed; };
const tri = (ctx, x, y, dir, k = 1) => {            // dir 1: points up, -1: points down; y = the tip; k = marker size
  ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - 5 * k, y + 9 * k * dir); ctx.lineTo(x + 5 * k, y + 9 * k * dir); ctx.closePath();
};

class Overlay {
  constructor(cell) {
    this.cell = cell;
    this.dead = false;
    this.dirty = true;
    const P = cell.P || {};
    this.bub = new BubbleLayer(P, this);
    this.swp = new SweepLayer(P, this);
    this.run = new RunLayer(P, this);
    this.fvg = new FvgLayer(P, this);
    if (cell.candles) {
      for (const l of [this.bub, this.swp, this.run, this.fvg]) cell.candles.attachPrimitive(l);
    }
    this.sync();
    this.timer = setInterval(() => {
      if (this.dead || !this.dirty) return;
      this.dirty = false;
      this.sync();
      for (const l of this.layers()) l.redraw();
    }, PAINT_MS);
    this.onRange = () => { this.dirty = true; };
    if (cell.chart) cell.chart.timeScale().subscribeVisibleLogicalRangeChange(this.onRange);
  }

  layers() { return [this.bub, this.swp, this.run, this.fvg, ...Object.keys(LAZY).map((k) => this[k]).filter(Boolean)]; }

  /* Attach the order-flow layers whose indicator is on, detach the ones whose indicator is gone or hidden. */
  sync() {
    const c = this.cell;
    for (const k of Object.keys(LAZY)) {
      const [ids, Cls] = LAZY[k], want = ids.some((id) => inst(c, id));
      if (want && !this[k]) { this[k] = new Cls(c.P || {}, this); if (c.candles) c.candles.attachPrimitive(this[k]); }
      else if (!want && this[k]) { try { if (c.candles) c.candles.detachPrimitive(this[k]); } catch (_) { /* series gone */ } this[k] = null; }
    }
  }

  /* The visible bars' index range and the mapping from a time to an x, or null when there is nothing to draw. */
  frame() {
    const c = this.cell;
    if (this.dead || !c.chart || !c.bars || !c.bars.length) return null;
    const ts = c.chart.timeScale(), vr = ts.getVisibleLogicalRange();
    if (!vr) return null;
    const bars = c.bars, barMs = c.isTime() ? c.barMs() : 0, last = bars[bars.length - 1].ms;
    const end = barMs ? last + barMs : last;
    const i0 = Math.max(0, Math.floor(vr.from) - 1), i1 = Math.min(bars.length - 1, Math.ceil(vr.to) + 1);
    const X = (t) => window.HBDrawings.xOfLogical(logicalAt(bars, t, barMs, end), (i) => ts.logicalToCoordinate(i));
    const XI = (i) => ts.logicalToCoordinate(i);        // the centre of bar i
    return { bars, i0, i1, X, XI, series: c.candles, P: c.P || {} };
  }

  drawBubbles(target) {
    const h = inst(this.cell, 'heatmap');
    if (!h || !h.params.bubbles) return;
    const f = this.frame();
    if (!f) return;
    const q = h.params, min = q.bubbleMin, max = +q.bubbleMax || 0, side = q.bubbleSide || 'all', full = pn(q.bubbleFullSize, 0);
    const hi = max > min ? max : full > 0 ? full : Math.max(min * 20, 200);      // a ceiling is the size of the biggest circle
    const rMin = pn(q.bubbleRadiusMin, 3), rMax = Math.max(rMin, pn(q.bubbleRadiusMax, 14)), lw = pn(q.bubbleLineWidth, 1), labels = pb(q.bubbleLabels, false);
    const fillB = sc(h, 'buyFill', 'rgba(8,153,129,.45)'), fillS = sc(h, 'sellFill', 'rgba(242,54,69,.45)');
    const lineB = sc(h, 'buyOutline', '#089981'), lineS = sc(h, 'sellOutline', '#F23645');
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      if (labels) { ctx.font = SMALL; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; }
      for (let i = f.i0; i <= f.i1; i++) {
        for (const b of M.bubblesOf(f.bars[i], min, max, side)) {
          const x = f.X(b.t), y = f.series.priceToCoordinate(b.price);
          if (x == null || y == null || x < -20 || x > mediaSize.width + 20) continue;
          const r = M.bubbleRadius(b.size, min, hi, rMin, rMax);
          ctx.fillStyle = b.side > 0 ? fillB : fillS;
          ctx.strokeStyle = b.side > 0 ? lineB : lineS;
          ctx.lineWidth = lw;
          ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); if (lw > 0) ctx.stroke();
          if (labels && r >= 7) { ctx.fillStyle = f.P.text || ctx.strokeStyle; ctx.fillText(String(Math.round(b.size)), x, y); }
        }
      }
    });
  }

  drawSweeps(target) {
    const bp = inst(this.cell, 'bigprints');
    if (!bp || !bp.params.sweeps) return;
    const f = this.frame();
    if (!f) return;
    const q = bp.params, sm = pn(q.sweepMin, 0), min = sm > 0 ? sm : q.min;      // 0 = the same as Minimum size
    const k = pn(q.sweepArrow, 1), dash = pc(q.sweepDash, ['solid', 'dashed', 'dotted'], 'solid');
    const buy = sc(bp, 'buy', f.P.up || '#089981'), sell = sc(bp, 'sell', f.P.down || '#F23645');
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      ctx.lineWidth = pn(q.sweepWidth, 2);
      if (dash !== 'solid') ctx.setLineDash(dashOf(dash, [4, 3], 'solid'));
      for (let i = f.i0; i <= f.i1; i++) {
        for (const s of M.sweepsOf(f.bars[i], min)) {
          const x = f.X(s.t), y0 = f.series.priceToCoordinate(s.from), y1 = f.series.priceToCoordinate(s.to);
          if (x == null || y0 == null || y1 == null || x < -10 || x > mediaSize.width + 10) continue;
          const col = s.side > 0 ? buy : sell;
          ctx.strokeStyle = col; ctx.fillStyle = col;
          ctx.beginPath(); ctx.moveTo(x, y0); ctx.lineTo(x, y1); ctx.stroke();
          const tip = s.side > 0 ? Math.min(y0, y1) : Math.max(y0, y1), d = s.side > 0 ? 6 * k : -6 * k;   // buyers lift: up
          ctx.beginPath(); ctx.moveTo(x, tip - d); ctx.lineTo(x - 4 * k, tip); ctx.lineTo(x + 4 * k, tip); ctx.closePath(); ctx.fill();
        }
      }
      if (dash !== 'solid') ctx.setLineDash([]);
    });
  }

  /* Fair value gaps: one box per gap, from its first bar to the last bar it was still open on, up gaps in the up
     colour, down gaps in the down colour. The study's per-bar values (the newest unfilled gap each side) make the boxes;
     no line joins one gap to the next. */
  drawFvg(target) {
    const g = inst(this.cell, 'fvg');
    if (!g) return;
    const f = this.frame();
    if (!f) return;
    const key = window.HBCatalog.serverKey(g);      // with the gap timeframe ("fvg:0.25:14@300") when one is set
    const op = Number.isFinite(+g.params.opacity) ? Math.max(0, Math.min(100, +g.params.opacity)) : 15;
    const wx = f.XI(Math.max(f.i0, 1)) - f.XI(Math.max(f.i0, 1) - 1), half = (Number.isFinite(wx) && wx > 0 ? wx : 8) / 2;
    const A = window.HBDrawings.withAlpha;
    const border = pb(g.params.border, true), bw = pn(g.params.borderWidth, 1), extend = pb(g.params.extend, false);
    let last = f.bars.length - 1;
    while (last > 0 && f.bars[last].blank) last--;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      for (const b of M.fvgBoxes(f.bars, key, f.i1 + 1)) {
        if (b.to < f.i0 - 1) continue;
        const xa = f.XI(b.from), xb = f.XI(b.to), ya = f.series.priceToCoordinate(b.top), yb = f.series.priceToCoordinate(b.bottom);
        if (xa == null || xb == null || ya == null || yb == null) continue;
        const x0 = xa - half, x1 = extend && b.to === last ? Math.max(xb + half, mediaSize.width) : xb + half;   // a gap still open on the newest bar runs on to the right edge
        if (x1 < 0 || x0 > mediaSize.width) continue;
        const col = b.side > 0 ? (f.P.up || '#089981') : (f.P.down || '#F23645');
        const y = Math.min(ya, yb), h = Math.max(1, Math.abs(yb - ya));
        if (op > 0) { ctx.fillStyle = A(col, op / 100); ctx.fillRect(x0, y, x1 - x0, h); }
        if (!border) continue;
        ctx.strokeStyle = A(col, Math.min(1, op / 100 + 0.35)); ctx.lineWidth = bw;
        ctx.strokeRect(x0 + 0.5, y + 0.5, Math.max(0, x1 - x0 - 1), Math.max(0, h - 1));
      }
    });
  }

  /* Stop runs and exhaustion marks: one pass over the visible bars each (the swing / average look back `length`). */
  drawRuns(target) {
    const sr = inst(this.cell, 'stoprun'), ex = inst(this.cell, 'exhaust'), sm = inst(this.cell, 'smt');
    if (!sr && !ex && !sm) return;
    const f = this.frame();
    if (!f) return;
    const up = f.P.up || '#089981', down = f.P.down || '#F23645';
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      ctx.font = FONT;
      ctx.textBaseline = 'middle';
      let fpx = 11;       // the font size now set; each block below sets its own (its Label font setting)
      const useFont = (n) => { if (n !== fpx) { ctx.font = font(n); fpx = n; } };
      if (sr) {
        const q = sr.params, k = Math.max(0.5, +q.size || 1), only = q.side, lw = pn(q.lineWidth, 1), dash = dashOf(q.dash, [3, 3], 'dashed');
        const line = pb(q.levelLine, true), show = pc(q.show, ['all', 'held', 'trap'], 'all'), cross = pb(q.trapMark, true), gap = pn(q.arrowGap, 4);
        const cu = sc(sr, 'up', up), cd = sc(sr, 'down', down);
        useFont(pn(q.fontSize, 11));
        for (const r of M.stopRuns(f.bars, f.i0, f.i1, q.length, q.minSize, pn(q.sweepMin, 1))) {
          if ((only === 'up' && r.side <= 0) || (only === 'down' && r.side > 0)) continue;
          if ((show === 'held' && !r.held) || (show === 'trap' && r.held)) continue;
          const x1 = f.XI(r.i), x0 = f.XI(r.from), y = f.series.priceToCoordinate(r.level);
          if (x1 == null || y == null || x1 < -20 || x1 > mediaSize.width + 20) continue;
          const col = r.side > 0 ? cu : cd;
          ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = lw;
          ctx.setLineDash(dash);
          if (line) { ctx.beginPath(); ctx.moveTo(Math.max(-20, x0 ?? x1), y); ctx.lineTo(x1, y); ctx.stroke(); }
          ctx.setLineDash([]);
          if (lw !== 1) ctx.lineWidth = 1;      // the width is the level line's: a hollow arrow keeps its thin outline
          // the arrow sits just past the level, on the side the run went, pointing that way; hollow = pushed back (a trap)
          const tipY = y - gap * r.side;
          tri(ctx, x1, tipY, r.side, k);
          if (r.held) ctx.fill(); else ctx.stroke();
          ctx.fillStyle = col;
          if (q.labels !== false) ctx.fillText(`${r.size}${r.held || !cross ? '' : ' ✕'}`, x1 + 8, tipY - r.side * 8);
        }
      }
      if (sm) {
        // SMT: the chart's own two peaks joined (the reference's extreme to the window's); `lead` says who took it
        const me = String(this.cell.cfg.root || '').toUpperCase(), other = me === 'NQ' ? 'ES' : me === 'ES' ? 'NQ' : '';
        const key = `smt:${sm.params.window}:${sm.params.reference}`;
        const lw = pn(sm.params.lineWidth, 1.5), line = pb(sm.params.showLine, true), dotR = pn(sm.params.dotRadius, 2.5);
        const cu = sc(sm, 'up', up), cd = sc(sm, 'down', down);
        useFont(pn(sm.params.fontSize, 11));
        for (const r of M.smtLines(f.bars, f.i0, f.i1, key)) {
          const x0 = f.XI(r.from), x1 = f.XI(r.to), y0 = f.series.priceToCoordinate(r.y0), y1 = f.series.priceToCoordinate(r.y1);
          if (x0 == null || x1 == null || y0 == null || y1 == null || x1 < -20 || x0 > mediaSize.width + 20) continue;
          const col = r.dir < 0 ? cd : cu;
          ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = lw;
          ctx.setLineDash(r.live ? [2, 3] : [5, 3]);       // dotted while the bar is still forming
          if (line) { ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke(); }
          ctx.setLineDash([]);
          if (dotR > 0) for (const [x, y] of [[x0, y0], [x1, y1]]) { ctx.beginPath(); ctx.arc(x, y, dotR, 0, Math.PI * 2); ctx.fill(); }
          if (sm.params.labels !== false && other) {
            const took = r.lead > 0 ? me : other, failed = r.lead > 0 ? other : me;
            ctx.fillText(`${took} ${r.dir < 0 ? 'high' : 'low'} · ${failed} did not`, x1 + 8, y1 + (r.dir < 0 ? -12 : 12));
          }
        }
      }
      if (ex) {
        const q = ex.params, k = Math.max(0.5, +q.size || 1), only = q.side, cw = pn(q.capWidth, 2), ch = pn(q.capHalf, 6), arrow = pb(q.arrow, true);
        const cu = sc(ex, 'up', up), cd = sc(ex, 'down', down);
        useFont(pn(q.fontSize, 11));
        for (const r of M.exhaustions(f.bars, f.i0, f.i1, q.length, q.multiple, q.wait, pn(q.giveback, 50))) {
          if ((only === 'up' && r.dir >= 0) || (only === 'down' && r.dir < 0)) continue;   // 'up' = price turned down (buying spent)
          const xa = f.XI(r.at), xi = f.XI(r.i), y = f.series.priceToCoordinate(r.level);
          if (xi == null || y == null || xi < -20 || xi > mediaSize.width + 20) continue;
          const col = r.dir < 0 ? cd : cu;                 // buyers spent: price turned down (red)
          ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = cw;
          ctx.beginPath(); ctx.moveTo((xa ?? xi) - ch, y); ctx.lineTo(xi + ch, y); ctx.stroke();   // the cap: the extreme that stopped
          const dir = r.dir, tipY = y + (dir < 0 ? -2 : 2);   // the arrow points the way price went, at the cap
          if (arrow) { tri(ctx, xi, tipY, dir, k); ctx.fill(); }
          if (q.labels !== false) ctx.fillText('Ex', xi + 8, y + (dir < 0 ? -14 : 14));
        }
      }
    });
  }

  /* Big trades (ATAS / MotiveWave / Bookmap dots on the rebuilt aggressor order): a bubble per order of `min`..`max` contracts, optionally clustered
     (cluster none | volume | price | priceside, `thr` contracts), sized by contracts, the size inside a big one. Clusters never span two bars. */
  drawOrders(target) {
    const g = inst(this.cell, 'bigtrades');
    if (!g) return;
    const f = this.frame();
    if (!f) return;
    const p = g.params, min = Math.max(1, p.min == null ? 25 : +p.min), max = +p.max || 0, full = pn(p.fullSize, 0);
    const hi = max > min ? max : full > 0 ? full : Math.max(min * 20, 200);
    const rMin = pn(p.radiusMin, 3), rMax = Math.max(rMin, pn(p.radiusMax, 14)), lw = pn(p.lineWidth, 1), labels = pb(p.labels, true), labelR = pn(p.labelMinR, 7);
    const fillB = sc(g, 'buyFill', 'rgba(8,153,129,.45)'), fillS = sc(g, 'sellFill', 'rgba(242,54,69,.45)');
    const lineB = sc(g, 'buyOutline', f.P.up || '#089981'), lineS = sc(g, 'sellOutline', f.P.down || '#F23645');
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      ctx.font = font(pn(p.fontSize, 10)); ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      for (let i = f.i0; i <= f.i1; i++) {
        for (const c of M.clusterOrders(M.ordersOf(f.bars[i], 0, 0, p.side || 'all'), p.cluster || 'none', +p.thr || 100)) {
          if (c.size < min || (max > 0 && c.size > max)) continue;
          const x = f.X(c.t), y = f.series.priceToCoordinate(c.price);
          if (x == null || y == null || x < -20 || x > mediaSize.width + 20) continue;
          const r = M.bubbleRadius(c.size, min, hi, rMin, rMax), col = c.side > 0 ? lineB : lineS;
          ctx.fillStyle = c.side > 0 ? fillB : fillS; ctx.strokeStyle = col; ctx.lineWidth = lw;
          ctx.beginPath(); ctx.arc(x, y, r, 0, Math.PI * 2); ctx.fill(); if (lw > 0) ctx.stroke();
          if (labels && r >= labelR) { ctx.fillStyle = f.P.text || col; ctx.fillText(String(Math.round(c.size)), x, y); }
        }
      }
    });
  }

  /* Naked POCs (Exocharts / MotiveWave): from each bar's POC a dashed line to the first later bar that traded back to it, or to the right edge while none
     has. The scan starts 500 bars left of the view so a line from before it still crosses it; the forming bar's own POC is the footprint's. */
  drawNaked(target) {
    const np = inst(this.cell, 'npoc');
    if (!np) return;
    const f = this.frame();
    if (!f) return;
    const q = np.params, back = pn(q.lookback, 500);
    const list = M.nakedPocs(f.bars, Math.max(0, f.i0 - back), Math.min(f.i1, f.bars.length - 2), !pb(q.nakedOnly, false));   // nakedOnly: the lines that stopped at a later bar are not drawn
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      ctx.strokeStyle = sc(np, 'line', f.P.poc || '#f2a900'); ctx.lineWidth = pn(q.width, 1); ctx.setLineDash(dashOf(q.dash, [4, 3], 'dashed'));
      for (const r of list) {
        const x = f.XI(r.i), y = f.series.priceToCoordinate(r.price), x1 = r.hit == null ? mediaSize.width : f.XI(r.hit);
        if (x == null || y == null || x1 == null || x > mediaSize.width || x1 < 0) continue;
        ctx.beginPath(); ctx.moveTo(Math.max(0, x), y); ctx.lineTo(Math.min(mediaSize.width, x1), y); ctx.stroke();
      }
      ctx.setLineDash([]);
    });
  }

  /* Stacked profile zones (flowmath profileZones): a band from the bar that first traded the row to the first later bar back in it, or to the right
     edge while none has; filled at the opacity setting, edged in full colour. Rebuilt only when the newest bar or a setting changes. */
  drawZones(target) {
    const z = inst(this.cell, 'pzone');
    if (!z) return;
    const f = this.frame();
    if (!f) return;
    const p = z.params, bars = f.bars, tick = this.cell.tick || 0.25, last = bars[bars.length - 1];
    const key = [bars.length, last.v, last.h, last.l, tick, p.rows, p.period, p.outlier, p.lvn, p.sessions].join('|');
    if (!this.zk || this.zk.bar !== last || this.zk.key !== key) {
      this.zk = { bar: last, key, list: M.profileZones(bars, { tick, rows: pn(p.rows, 4), period: pn(p.period, 30), outlier: pn(p.outlier, 3), lvn: pn(p.lvn, 30),
        sessions: pn(p.sessions, 5) }) };
    }
    const only = pb(p.untouchedOnly, false), a = Math.max(0, Math.min(100, pn(p.opacity, 20))) / 100;
    const up = sc(z, 'up', '#22D3EE'), down = sc(z, 'down', '#A855F7');
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      ctx.lineWidth = 1;
      for (const r of this.zk.list) {
        if (only && r.hit != null) continue;
        const x0 = f.XI(r.i), x1 = r.hit == null ? mediaSize.width : f.XI(r.hit);
        const ya = f.series.priceToCoordinate(r.hi), yb = f.series.priceToCoordinate(r.lo);
        if (x0 == null || x1 == null || ya == null || yb == null || x0 > mediaSize.width || x1 < 0) continue;
        const col = r.side > 0 ? up : down, xa = Math.max(0, x0), xb = Math.min(mediaSize.width, x1), y = Math.min(ya, yb), h = Math.max(1, Math.abs(yb - ya));
        ctx.fillStyle = window.HBDrawings.withAlpha(col, a); ctx.fillRect(xa, y, xb - xa, h);
        ctx.strokeStyle = col;
        for (const yy of [y, y + h]) { ctx.beginPath(); ctx.moveTo(xa, yy); ctx.lineTo(xb, yy); ctx.stroke(); }
      }
    });
  }

  /* TPO profile (Sierra / MotiveWave / ATAS) of the NEWEST session only, docked at the right edge: a letter (style letters) or a block (blocks, and
     whenever a row is too thin for a letter) per sub-period that touched the row; the value area tinted, the POC row boxed, single prints in the POC
     colour, the initial balance's edges dashed. The profile is rebuilt only when the session's last bar changes. */
  drawTpo(target) {
    const t = inst(this.cell, 'tpo');
    if (!t) return;
    const f = this.frame();
    if (!f) return;
    const p = t.params, bars = f.bars, tick = this.cell.tick || 0.25;
    const fs = pn(p.fontSize, 10), blocksA = pn(p.blocksOpacity, 45) / 100, showPoc = pb(p.showPoc, true), showVa = pb(p.showVa, true), marks = pb(p.markSingles, true);
    const vaC = sc(t, 'va', f.P.vaIn || 'rgba(120,140,200,.15)'), singleC = sc(t, 'single', f.P.poc || '#f2a900');
    const pocC = sc(t, 'poc', f.P.poc || '#f2a900'), ibC = sc(t, 'ib', f.P.text2 || f.P.text || '#9aa4b2');
    let e = bars.length - 1;
    while (e >= 0 && bars[e].blank) e--;
    if (e < 0) return;
    // ticks per row: the setting, widened until a row is 3 px tall (a 300-point NQ session is under a pixel a tick: its rows would smear)
    const c0 = f.series.priceToCoordinate(bars[e].c), c1 = f.series.priceToCoordinate(bars[e].c + tick);
    const rows = Math.max(1, Math.floor(+p.rows) || 1, c0 == null || c1 == null ? 1 : Math.ceil(3 / Math.max(0.01, Math.abs(c0 - c1))));
    let s = e;
    while (s > 0 && bars[s - 1].s === bars[e].s) s--;
    const key = [s, e, bars[e].v, bars[e].h, bars[e].l, tick, rows, p.period, p.mode, p.ib, p.va, p.method].join('|');
    if (!this.tk || this.tk.bar !== bars[e] || this.tk.key !== key) {
      this.tk = { bar: bars[e], key, prof: M.tpo(bars.slice(s, e + 1), +p.period || 30, rows, p.mode === 'traded' ? 'traded' : 'range',
        { tick, ib: p.ib == null ? 2 : +p.ib, va: +p.va || 70, method: p.method || 'sierra' }) };
    }
    const prof = this.tk.prof;
    if (!prof) return;
    const y = (px) => f.series.priceToCoordinate(px + (rows - 1) * tick / 2);
    const a = f.series.priceToCoordinate(prof.rows[0].price), b = f.series.priceToCoordinate(prof.rows[0].price + rows * tick);
    if (a == null || b == null) return;
    const rh = Math.abs(a - b), maxN = Math.max(...prof.rows.map((r) => r.n));
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const W = mediaSize.width, cw = Math.min(9, W * 0.45 / maxN), x0 = W - 6 - maxN * cw, letters = p.style !== 'blocks' && rh >= 8 && cw >= 6;
      ctx.font = font(fs); ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      for (const r of prof.rows) {
        const yc = y(r.price);
        if (yc == null) continue;
        if (showVa && r.price >= prof.val && r.price <= prof.vah) { ctx.fillStyle = vaC; ctx.fillRect(x0 - 3, yc - rh / 2, W - x0 + 3, rh); }
        const ink = r.n === 1 && marks ? singleC : f.P.text || '#9aa4b2';
        ctx.fillStyle = letters ? ink : window.HBDrawings.withAlpha(ink, blocksA);    // blocks are a wash, not a wall: the candles stay readable
        r.per.forEach((per, j) => {
          if (letters) ctx.fillText(M.letterOf(per), x0 + j * cw + cw / 2, yc);
          else ctx.fillRect(x0 + j * cw, yc - rh / 2, cw - 1, Math.max(1, rh - 1));
        });
        if (showPoc && r.price === prof.poc) { ctx.strokeStyle = pocC; ctx.lineWidth = 1; ctx.strokeRect(x0 - 1, yc - rh / 2, r.n * cw + 2, Math.max(1, rh - 1)); }
      }
      if (prof.ib) {
        const hi = y(prof.ib.hi), lo = y(prof.ib.lo);
        ctx.strokeStyle = ibC; ctx.lineWidth = 1; ctx.setLineDash([3, 3]);
        for (const yy of [hi == null ? null : hi - rh / 2, lo == null ? null : lo + rh / 2]) {
          if (yy != null) { ctx.beginPath(); ctx.moveTo(x0 - 3, yy); ctx.lineTo(W, yy); ctx.stroke(); }
        }
        ctx.setLineDash([]);
      }
    });
  }

  /* Cluster statistics (ATAS Cluster Statistic, Bookmap footprint stats): a strip at the bottom of the pane, under the candles, one column per bar
     (delta, volume, trades, delta %, the highest and lowest running delta, seconds); hidden while the bars are too narrow to read. */
  drawStats(target) {
    const cs = inst(this.cell, 'cstat');
    if (!cs) return;
    const f = this.frame();
    if (!f) return;
    const p = cs.params, sp = f.XI(1) - f.XI(0), barMs = this.cell.isTime() ? this.cell.barMs() : 0;
    if (!(sp >= pn(p.minBarPx, 34))) return;      // indstatus.js reads the same setting for its "zoom in" hint
    const LAB = ['Delta', 'Volume', 'Trades', 'Delta %', 'Max delta', 'Min delta', 'Seconds'], RH = pn(p.rowH, 12), LW = pn(p.labelW, 58);
    const rows = LAB.map((_, k) => k).filter((k) => pb(p[['showDelta', 'showVolume', 'showTrades', 'showDeltaPct', 'showMaxDelta', 'showMinDelta', 'showSeconds'][k]], true));
    if (!rows.length) return;
    const kFrom = pn(p.kFrom, 1e4), dec = pn(p.pctDecimals, 1), cp = sc(cs, 'pos', f.P.up), cn = sc(cs, 'neg', f.P.down);
    const num = (v) => (v == null ? '' : Math.abs(v) >= kFrom ? `${(v / 1000).toFixed(1)}k` : String(Math.round(v)));
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const top = pc(p.place, ['bottom', 'top'], 'bottom') === 'top' ? 0 : mediaSize.height - RH * rows.length - 4;
      ctx.fillStyle = window.HBDrawings.withAlpha(f.P.bg || '#131722', 0.8); ctx.fillRect(0, top, mediaSize.width, RH * rows.length + 4);
      ctx.font = font(pn(p.fontSize, 10)); ctx.textBaseline = 'middle';
      ctx.textAlign = 'left'; ctx.fillStyle = f.P.text2 || f.P.text || '#9aa4b2';
      rows.forEach((k, j) => ctx.fillText(LAB[k], 4, top + 2 + RH * (j + 0.5)));
      ctx.textAlign = 'center';
      for (let i = f.i0; i <= f.i1; i++) {
        const b = f.bars[i], x = f.XI(i);
        if (b.blank || x == null || x - sp / 2 < LW || x > mediaSize.width) continue;
        // A time bar lasts at most its length (the next stored bar can be a quiet stretch, the 17:00 hour or a weekend away). A tick / volume / range
        // bar runs to the next bar's start, blank across a session break. shortcut: that includes a quiet gap inside a session, exact once a bar carries its end.
        const nx = f.bars[i + 1];
        const c = M.clusterStats(b, barMs ? Math.min(nx ? nx.ms : Infinity, b.ms + barMs) : nx && nx.s === b.s ? nx.ms : null);
        const cells = [[num(c.delta), c.delta > 0 ? cp : c.delta < 0 ? cn : null], [num(c.volume)], [num(c.trades)],
          [c.deltaPct == null ? '' : `${(100 * c.deltaPct).toFixed(dec)}%`, c.deltaPct > 0 ? cp : c.deltaPct < 0 ? cn : null],
          [num(c.maxDelta), cp], [num(c.minDelta), cn], [c.duration == null ? '' : String(+(c.duration / 1000).toFixed(1))]];
        rows.forEach((k, j) => { const [txt, col] = cells[k]; ctx.fillStyle = col || f.P.text || '#9aa4b2'; ctx.fillText(txt, x, top + 2 + RH * (j + 0.5)); });
      }
    });
  }

  /* Delta turnaround (ATAS; param `fix`), delta strength (ATAS; `min`, `max` percent) and MotiveWave absorption (`ticks`, `within`, `imb` = a
     preset of HBFlowMath.IMB): arrows past the bar's low (the delta pushed up) or high (down), filled for a turnaround, hollow and further out
     for a strength bar; an absorption is a line from the imbalance's price to the bar that confirmed it, with a dot there. */
  drawMarks(target) {
    const dt = inst(this.cell, 'dturn'), ds = inst(this.cell, 'dstr'), ma = inst(this.cell, 'mwabs');
    if (!dt && !ds && !ma) return;
    const f = this.frame();
    if (!f) return;
    const up = f.P.up || '#089981', down = f.P.down || '#F23645';
    // an arrow mark's own settings (colours, size, distance from the bar, fill, outline width); `d` = today's gap and fill for that mark
    const look = (i, d) => ({ up: sc(i, 'up', up), down: sc(i, 'down', down), k: Math.max(0.5, +i.params.size || 1), gap: pn(i.params.gap, d.gap),
      filled: pb(i.params.filled, d.filled), lw: pn(i.params.lineWidth, 1.5) });
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      const arrow = (r, o) => {
        const x = f.XI(r.i), y = f.series.priceToCoordinate(r.dir > 0 ? f.bars[r.i].l : f.bars[r.i].h);
        if (x == null || y == null || x < -20 || x > mediaSize.width + 20) return;
        ctx.strokeStyle = ctx.fillStyle = r.dir > 0 ? o.up : o.down; ctx.lineWidth = o.lw;
        tri(ctx, x, y + o.gap * r.dir, r.dir, o.k);
        if (o.filled) ctx.fill(); else ctx.stroke();
      };
      if (dt) { const o = look(dt, { gap: 3, filled: true }); for (const r of M.deltaTurnaround(f.bars, f.i0, f.i1, { fix: !!dt.params.fix, run: dt.params.run })) arrow(r, o); }
      if (ds) { const o = look(ds, { gap: 17, filled: false }); for (const r of M.deltaStrength(f.bars, f.i0, f.i1, { min: ds.params.min, max: ds.params.max })) arrow(r, o); }
      if (ma) {
        const p = ma.params, lw = pn(p.lineWidth, 1.5), tail = pn(p.tail, 6), dot = pb(p.dot, true), dotR = pn(p.dotR, 3), dash = dashOf(p.dash, [4, 3], 'solid');
        const cu = sc(ma, 'up', up), cd = sc(ma, 'down', down);
        const imb = { ...(p.imb ? { preset: p.imb } : {}) };      // the settings left at "the rule's own" stay out, so the preset decides
        if (pn(p.ratio, 0) > 0) imb.ratio = +p.ratio;
        if (p.zero === 'skip') imb.zero = 'skip';
        if (p.edge === 'skip') imb.edge = 'skip';
        if (pn(p.minvol, 0) > 0) imb.minVolume = +p.minvol;
        if (pn(p.mindiff, 0) > 0) imb.minDiff = +p.mindiff;
        for (const r of M.mwAbsorptions(f.bars, f.i0, f.i1, { tick: this.cell.tick || 0.25, ticks: p.ticks, within: p.within, imb: Object.keys(imb).length ? imb : undefined })) {
          const xa = f.XI(r.i), xb = f.XI(r.j), y = f.series.priceToCoordinate(r.price);
          if (xa == null || xb == null || y == null || xb < -20 || xa > mediaSize.width + 20) continue;
          ctx.strokeStyle = ctx.fillStyle = r.dir < 0 ? cd : cu; ctx.lineWidth = lw;
          if (dash.length) ctx.setLineDash(dash);
          ctx.beginPath(); ctx.moveTo(xa - tail, y); ctx.lineTo(xb, y); ctx.stroke();
          if (dash.length) ctx.setLineDash([]);
          if (dot) { ctx.beginPath(); ctx.arc(xb, y, dotR, 0, Math.PI * 2); ctx.fill(); }
        }
      }
    });
  }

  onBars() { this.dirty = true; }

  /* The legend's eye: repaint now, not on the next bar (the layer reads each indicator's eye as it draws). */
  onIndicators() {
    if (this.dead) return;
    this.dirty = false;
    this.sync();
    for (const l of this.layers()) l.redraw();
  }

  destroy() {
    this.dead = true;
    clearInterval(this.timer);
    const c = this.cell;
    try { if (c.chart) c.chart.timeScale().unsubscribeVisibleLogicalRangeChange(this.onRange); } catch (_) { /* chart gone */ }
    for (const l of this.layers()) { try { if (c.candles) c.candles.detachPrimitive(l); } catch (_) { /* series gone */ } }
  }
}

window.HBFlowLayer = { overlay: (cell) => new Overlay(cell) };
})();
