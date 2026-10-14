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
   flowmath.js (Node-tested). */
(function () {
'use strict';
if (typeof window === 'undefined' || !window.HBLayers || !window.HBLiquidity || !window.HBFlowMath) return;
const { logicalAt } = window.HBLiquidity, M = window.HBFlowMath;

const PAINT_MS = 250;
const inst = (cell, id) => (cell.cfg.indicators || []).find((x) => x.id === id && x.visible !== false) || null;

class BubbleLayer extends window.HBLayers.Layer {
  constructor(P, ov) { super(P); this.ov = ov; }
  z() { return 'bottom'; }
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
    this.timer = setInterval(() => {
      if (this.dead || !this.dirty) return;
      this.dirty = false;
      this.bub.redraw(); this.swp.redraw(); this.run.redraw(); this.fvg.redraw();
    }, PAINT_MS);
    this.onRange = () => { this.dirty = true; };
    if (cell.chart) cell.chart.timeScale().subscribeVisibleLogicalRangeChange(this.onRange);
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
    const min = h.params.bubbleMin, max = +h.params.bubbleMax || 0, side = h.params.bubbleSide || 'all';
    const hi = max > min ? max : Math.max(min * 20, 200);      // a ceiling is the size of the biggest circle
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      for (let i = f.i0; i <= f.i1; i++) {
        for (const b of M.bubblesOf(f.bars[i], min, max, side)) {
          const x = f.X(b.t), y = f.series.priceToCoordinate(b.price);
          if (x == null || y == null || x < -20 || x > mediaSize.width + 20) continue;
          ctx.fillStyle = b.side > 0 ? 'rgba(8,153,129,.45)' : 'rgba(242,54,69,.45)';
          ctx.strokeStyle = b.side > 0 ? '#089981' : '#F23645';
          ctx.lineWidth = 1;
          ctx.beginPath(); ctx.arc(x, y, M.bubbleRadius(b.size, min, hi), 0, Math.PI * 2); ctx.fill(); ctx.stroke();
        }
      }
    });
  }

  drawSweeps(target) {
    const bp = inst(this.cell, 'bigprints');
    if (!bp || !bp.params.sweeps) return;
    const f = this.frame();
    if (!f) return;
    const min = bp.params.min;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      ctx.lineWidth = 2;
      for (let i = f.i0; i <= f.i1; i++) {
        for (const s of M.sweepsOf(f.bars[i], min)) {
          const x = f.X(s.t), y0 = f.series.priceToCoordinate(s.from), y1 = f.series.priceToCoordinate(s.to);
          if (x == null || y0 == null || y1 == null || x < -10 || x > mediaSize.width + 10) continue;
          const col = s.side > 0 ? (f.P.up || '#089981') : (f.P.down || '#F23645');
          ctx.strokeStyle = col; ctx.fillStyle = col;
          ctx.beginPath(); ctx.moveTo(x, y0); ctx.lineTo(x, y1); ctx.stroke();
          const tip = s.side > 0 ? Math.min(y0, y1) : Math.max(y0, y1), d = s.side > 0 ? 6 : -6;   // buyers lift: up
          ctx.beginPath(); ctx.moveTo(x, tip - d); ctx.lineTo(x - 4, tip); ctx.lineTo(x + 4, tip); ctx.closePath(); ctx.fill();
        }
      }
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
    const key = `fvg:${g.params.min}:${g.params.length}`;
    const op = Number.isFinite(+g.params.opacity) ? Math.max(0, Math.min(100, +g.params.opacity)) : 15;
    const wx = f.XI(Math.max(f.i0, 1)) - f.XI(Math.max(f.i0, 1) - 1), half = (Number.isFinite(wx) && wx > 0 ? wx : 8) / 2;
    const A = window.HBDrawings.withAlpha;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      for (const b of M.fvgBoxes(f.bars, key, f.i1 + 1)) {
        if (b.to < f.i0 - 1) continue;
        const xa = f.XI(b.from), xb = f.XI(b.to), ya = f.series.priceToCoordinate(b.top), yb = f.series.priceToCoordinate(b.bottom);
        if (xa == null || xb == null || ya == null || yb == null) continue;
        const x0 = xa - half, x1 = xb + half;
        if (x1 < 0 || x0 > mediaSize.width) continue;
        const col = b.side > 0 ? (f.P.up || '#089981') : (f.P.down || '#F23645');
        const y = Math.min(ya, yb), h = Math.max(1, Math.abs(yb - ya));
        if (op > 0) { ctx.fillStyle = A(col, op / 100); ctx.fillRect(x0, y, x1 - x0, h); }
        ctx.strokeStyle = A(col, Math.min(1, op / 100 + 0.35)); ctx.lineWidth = 1;
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
    const tri = (ctx, x, y, dir, k = 1) => {            // dir 1: points up, -1: points down; y = the tip; k = marker size
      ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x - 5 * k, y + 9 * k * dir); ctx.lineTo(x + 5 * k, y + 9 * k * dir); ctx.closePath();
    };
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      ctx.font = '11px -apple-system, BlinkMacSystemFont, sans-serif';
      ctx.textBaseline = 'middle';
      if (sr) {
        const k = Math.max(0.5, +sr.params.size || 1), only = sr.params.side;
        for (const r of M.stopRuns(f.bars, f.i0, f.i1, sr.params.length, sr.params.minSize)) {
          if ((only === 'up' && r.side <= 0) || (only === 'down' && r.side > 0)) continue;
          const x1 = f.XI(r.i), x0 = f.XI(r.from), y = f.series.priceToCoordinate(r.level);
          if (x1 == null || y == null || x1 < -20 || x1 > mediaSize.width + 20) continue;
          const col = r.side > 0 ? up : down;
          ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = 1;
          ctx.setLineDash([3, 3]);
          ctx.beginPath(); ctx.moveTo(Math.max(-20, x0 ?? x1), y); ctx.lineTo(x1, y); ctx.stroke();
          ctx.setLineDash([]);
          // the arrow sits just past the level, on the side the run went, pointing that way; hollow = pushed back (a trap)
          const tipY = y - 4 * r.side;
          tri(ctx, x1, tipY, r.side, k);
          if (r.held) ctx.fill(); else ctx.stroke();
          ctx.fillStyle = col;
          if (sr.params.labels !== false) ctx.fillText(`${r.size}${r.held ? '' : ' ✕'}`, x1 + 8, tipY - r.side * 8);
        }
      }
      if (sm) {
        // SMT: the chart's own two peaks joined (the reference's extreme to the window's); `lead` says who took it
        const me = String(this.cell.cfg.root || '').toUpperCase(), other = me === 'NQ' ? 'ES' : me === 'ES' ? 'NQ' : '';
        const key = `smt:${sm.params.window}:${sm.params.reference}`;
        for (const r of M.smtLines(f.bars, f.i0, f.i1, key)) {
          const x0 = f.XI(r.from), x1 = f.XI(r.to), y0 = f.series.priceToCoordinate(r.y0), y1 = f.series.priceToCoordinate(r.y1);
          if (x0 == null || x1 == null || y0 == null || y1 == null || x1 < -20 || x0 > mediaSize.width + 20) continue;
          const col = r.dir < 0 ? down : up;
          ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = 1.5;
          ctx.setLineDash(r.live ? [2, 3] : [5, 3]);       // dotted while the bar is still forming
          ctx.beginPath(); ctx.moveTo(x0, y0); ctx.lineTo(x1, y1); ctx.stroke();
          ctx.setLineDash([]);
          for (const [x, y] of [[x0, y0], [x1, y1]]) { ctx.beginPath(); ctx.arc(x, y, 2.5, 0, Math.PI * 2); ctx.fill(); }
          if (sm.params.labels !== false && other) {
            const took = r.lead > 0 ? me : other, failed = r.lead > 0 ? other : me;
            ctx.fillText(`${took} ${r.dir < 0 ? 'high' : 'low'} · ${failed} did not`, x1 + 8, y1 + (r.dir < 0 ? -12 : 12));
          }
        }
      }
      if (ex) {
        const k = Math.max(0.5, +ex.params.size || 1), only = ex.params.side;
        for (const r of M.exhaustions(f.bars, f.i0, f.i1, ex.params.length, ex.params.multiple, ex.params.wait)) {
          if ((only === 'up' && r.dir >= 0) || (only === 'down' && r.dir < 0)) continue;   // 'up' = price turned down (buying spent)
          const xa = f.XI(r.at), xi = f.XI(r.i), y = f.series.priceToCoordinate(r.level);
          if (xi == null || y == null || xi < -20 || xi > mediaSize.width + 20) continue;
          const col = r.dir < 0 ? down : up;               // buyers spent: price turned down (red)
          ctx.strokeStyle = col; ctx.fillStyle = col; ctx.lineWidth = 2;
          ctx.beginPath(); ctx.moveTo((xa ?? xi) - 6, y); ctx.lineTo(xi + 6, y); ctx.stroke();   // the cap: the extreme that stopped
          const dir = r.dir, tipY = y + (dir < 0 ? -2 : 2);   // the arrow points the way price went, at the cap
          tri(ctx, xi, tipY, dir, k);
          ctx.fill();
          if (ex.params.labels !== false) ctx.fillText('Ex', xi + 8, y + (dir < 0 ? -14 : 14));
        }
      }
    });
  }

  onBars() { this.dirty = true; }

  /* The legend's eye: repaint now, not on the next bar (the layer reads each indicator's eye as it draws). */
  onIndicators() {
    if (this.dead) return;
    this.dirty = false;
    this.bub.redraw(); this.swp.redraw(); this.run.redraw(); this.fvg.redraw();
  }

  destroy() {
    this.dead = true;
    clearInterval(this.timer);
    const c = this.cell;
    try { if (c.chart) c.chart.timeScale().unsubscribeVisibleLogicalRangeChange(this.onRange); } catch (_) { /* chart gone */ }
    for (const l of [this.bub, this.swp, this.run, this.fvg]) { try { if (c.candles) c.candles.detachPrimitive(l); } catch (_) { /* series gone */ } }
  }
}

window.HBFlowLayer = { overlay: (cell) => new Overlay(cell) };
})();
