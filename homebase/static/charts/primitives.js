/* Homebase Charts — canvas layers drawn inside Lightweight Charts v5 panes
   (series primitives): footprint cells, session volume profile, data gaps.
   Pure drawing: the server already computed every number. */
(function () {
'use strict';
const key = (px) => +(+px).toFixed(6);

class Layer {
  constructor(P) { this.P = P; this._views = [{ zOrder: () => this.z(), renderer: () => ({ draw: (t) => this.draw(t) }) }]; }
  z() { return 'top'; }
  attached({ chart, series, requestUpdate }) { this.chart = chart; this.series = series; this.requestUpdate = requestUpdate; }
  detached() { this.chart = this.series = null; }
  updateAllViews() {}
  paneViews() { return this._views; }
  redraw() { if (this.requestUpdate) this.requestUpdate(); }
  draw() {}
  spacing() {
    const ts = this.chart.timeScale(), a = ts.logicalToCoordinate(0), b = ts.logicalToCoordinate(1);
    return (a == null || b == null) ? 0 : b - a;
  }
  rowH(px, tick) {
    const a = this.series.priceToCoordinate(px), b = this.series.priceToCoordinate(px + tick);
    return (a == null || b == null) ? 0 : Math.abs(a - b);
  }
}

/* Per bar and price: "sells at bid | buys at ask", a volume bar behind, the
   bar's POC boxed, and diagonal imbalances coloured (buys at P vs sells one
   tick below; sells at P vs buys one tick above) at `ratio`:1. Drawn only
   when zoomed in far enough to read. */
class Footprint extends Layer {
  constructor(P) {
    super(P);
    this.bars = []; this.ratio = 0; this.tick = 0.25; this.on = false;
    this.onReadableChange = null; this._readable = false;   // last value reported to the callback
    this._timer = null;   // pending setTimeout id for the not-yet-delivered flip, if any
  }
  set(bars, on, ratio, tick) { this.bars = bars; this.on = on; this.ratio = ratio; this.tick = tick; this.redraw(); }
  readable() {
    if (!this.on || !this.chart || !this.series || !this.bars.length) return false;
    const last = this.bars[this.bars.length - 1];
    return this.spacing() >= 56 && this.rowH(last.c, this.tick) >= 9;
  }
  /* Cancel any pending flip and drop the callback: a torn-down primitive must
     never dispatch into whatever it used to be attached to. */
  detached() {
    super.detached();
    clearTimeout(this._timer); this._timer = null;
    this.onReadableChange = null;
  }
  /* Lightweight Charts calls this before every render, once layout for the
     new range/zoom/price-scale is settled — so, unlike a subscribe*Change
     event (which fires BEFORE relayout), readable() here sees current
     numbers. Only report on change, and only asynchronously: never call
     chart/series-mutating APIs (applyOptions etc.) from inside a render pass.
     A flip that arrives before the previous one was delivered replaces it --
     only the latest value is ever sent. */
  updateAllViews() {
    const on = this.readable();
    if (on === this._readable) return;
    this._readable = on;
    clearTimeout(this._timer);
    this._timer = setTimeout(() => { this._timer = null; if (this.onReadableChange) this.onReadableChange(on); }, 0);
  }
  draw(target) {
    if (!this.readable()) return;
    const ts = this.chart.timeScale(), r = ts.getVisibleLogicalRange(); if (!r) return;
    const i0 = Math.max(0, Math.floor(r.from)), i1 = Math.min(this.bars.length - 1, Math.ceil(r.to));
    if (i1 < i0) return;   // visible range holds no bars (panned past either end)
    const w = this.spacing() * 0.86, P = this.P, tick = this.tick;
    target.useMediaCoordinateSpace(({ context: ctx }) => {
      const rh = this.rowH(this.bars[i1].c, tick);
      ctx.font = `${Math.max(8, Math.min(11, rh - 2))}px ui-monospace, SFMono-Regular, Menlo, monospace`;
      ctx.textBaseline = 'middle';
      for (let i = i0; i <= i1; i++) {
        const b = this.bars[i]; if (!b || !b.fp || !b.fp.length) continue;
        const x = ts.logicalToCoordinate(i); if (x == null) continue;
        const at = new Map(b.fp.map((row) => [key(row[0]), row]));
        let maxV = 1, poc = b.fp[0];
        for (const row of b.fp) { const v = row[1] + row[2]; if (v > maxV) maxV = v; if (v > poc[1] + poc[2]) poc = row; }
        for (const [px, sv, bv] of b.fp) {
          const y = this.series.priceToCoordinate(px); if (y == null) continue;
          ctx.fillStyle = P.fpBg; ctx.fillRect(x - w / 2, y - rh / 2, w * (sv + bv) / maxV, rh - 1);
          const below = at.get(key(px - tick)), above = at.get(key(px + tick));
          const buyImb = this.ratio > 0 && bv > 0 && bv >= this.ratio * Math.max(below ? below[1] : 0, 1);
          const sellImb = this.ratio > 0 && sv > 0 && sv >= this.ratio * Math.max(above ? above[2] : 0, 1);
          ctx.textAlign = 'right'; ctx.fillStyle = sellImb ? P.down : P.fpText; ctx.fillText(String(sv), x - 3, y);
          ctx.textAlign = 'left'; ctx.fillStyle = buyImb ? P.up : P.fpText; ctx.fillText(String(bv), x + 3, y);
          if (px === poc[0]) { ctx.strokeStyle = P.poc; ctx.lineWidth = 1; ctx.strokeRect(x - w / 2, y - rh / 2, w, rh - 1); }
        }
      }
    });
  }
}

/* Session volume profile on the right edge: POC highlighted, value area darker. */
class Profile extends Layer {
  constructor(P) { super(P); this.p = null; this.tick = 0.25; }
  z() { return 'bottom'; }
  set(p, tick) { this.p = p; this.tick = tick; this.redraw(); }
  draw(target) {
    const p = this.p; if (!p || !this.series || !p.rows || !p.rows.length) return;
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      let maxV = 1; for (const r of p.rows) if (r[1] > maxV) maxV = r[1];
      const W = mediaSize.width * 0.18, rh = Math.max(1, this.rowH(p.poc, this.tick) - 0.5);
      for (const [px, v] of p.rows) {
        const y = this.series.priceToCoordinate(px); if (y == null) continue;
        ctx.fillStyle = px === p.poc ? this.P.poc : (px >= p.val && px <= p.vah ? this.P.vaIn : this.P.va);
        const w = W * v / maxV; ctx.fillRect(mediaSize.width - w, y - rh / 2, w, rh);
      }
    });
  }
}

/* Shaded "no data" bands after the given bar indices (recording gaps). */
class Gaps extends Layer {
  constructor(P) { super(P); this.idx = []; }
  z() { return 'bottom'; }
  set(indices) { this.idx = indices; this.redraw(); }
  draw(target) {
    if (!this.chart || !this.idx.length) return;
    const ts = this.chart.timeScale(), sp = Math.max(this.spacing(), 2);
    target.useMediaCoordinateSpace(({ context: ctx, mediaSize }) => {
      ctx.font = '10px system-ui, sans-serif'; ctx.textAlign = 'center';
      for (const i of this.idx) {
        const x = ts.logicalToCoordinate(i + 0.5); if (x == null) continue;
        ctx.fillStyle = this.P.gap; ctx.fillRect(x - sp / 2, 0, sp, mediaSize.height);
        ctx.fillStyle = this.P.text; ctx.fillText('no data', x, 12);
      }
    });
  }
}

window.HBLayers = { Footprint, Profile, Gaps, Layer };
})();
