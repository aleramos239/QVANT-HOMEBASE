/* Homebase Charts — canvas layers drawn inside Lightweight Charts v5 panes
   (series primitives). Task 12 fills in the drawing. */
(function () {
'use strict';
class Layer {
  constructor(P) { this.P = P; this._views = [{ zOrder: () => this.z(), renderer: () => ({ draw: (t) => this.draw(t) }) }]; }
  z() { return 'top'; }
  attached({ chart, series, requestUpdate }) { this.chart = chart; this.series = series; this.requestUpdate = requestUpdate; }
  detached() { this.chart = this.series = null; }
  updateAllViews() {}
  paneViews() { return this._views; }
  redraw() { if (this.requestUpdate) this.requestUpdate(); }
  draw() {}
}
class Footprint extends Layer { set() {} readable() { return false; } }
class Profile extends Layer { set() {} }
class Gaps extends Layer { set() {} }
window.HBLayers = { Footprint, Profile, Gaps, Layer };
})();
