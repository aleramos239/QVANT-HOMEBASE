/* Homebase Charts — HBSpring: a tiny, dependency-free motion engine for the 2026-09-28 feel pass (see
   docs/superpowers/findings/2026-09-28-feel-audit.md for why this exists and what it does NOT touch --
   the chart canvas, price/time axes, order/position lines and chips, the DOM ladder and the legend's own
   values stay solid, crisp and instant everywhere in this app).

   Follows Apple's "Designing Fluid Interfaces" (WWDC 2018): motion starts from the current on-screen value,
   carries velocity through a re-target (no brick wall on interrupt), and momentum is PROJECTED forward from
   a release velocity rather than snapped to the release point.

   Two layers:
   - PURE functions (stepSpring, project, rubberband, softClamp, the velocity tracker) -- no DOM, no clock
     reads, Node-tested directly (tests/js/spring.test.mjs), same convention as panellayout.js.
   - Spring: a thin requestAnimationFrame-driven wrapper around stepSpring for a single scalar value,
     browser only. Two independent Spring instances give 2D motion (apple-design skill: "decompose 2D
     motion into independent X and Y springs" -- never one 2D spring).
   - materialize/dematerialize: a small CSS-transition-driven enter/exit helper for click-triggered chrome
     (menus, dialogs, toasts, the draw toolbar, the replay bar). NOT spring-stepped on purpose -- none of
     those are gesture-interruptible the way a dragged panel is, so a CSS transition on a spring-SHAPED
     easing curve (charts.css --ease-spring-*) is the simpler, cheaper, equally-correct tool (Emil Kowalski,
     design-eng skill: "use CSS transitions over keyframes for interruptible UI"). They live here anyway so
     every "feel" primitive this pass introduces has one shared, dependency-free home.

   No browser globals at load time: the Node tests load this file directly (dom.js's own pattern). */
(function () {
'use strict';

const EPS = 1e-4;

/* ---- the analytic damped spring (mass = 1) ----
   Apple's SwiftUI mapping from (dampingRatio, response) in seconds to a physical spring:
     angular frequency  w0 = 2*pi / response
     stiffness           k = w0^2
     damping             c = 2 * dampingRatio * w0
   stepSpring evaluates the CLOSED-FORM solution of that damped harmonic oscillator at time `dt` past
   (pos, vel) -- not an Euler integration -- so a dropped frame or a large dt (a backgrounded tab) is still
   exact, never unstable. Three branches, same as any damped oscillator: under- (bouncy, overshoots once or
   more before settling), critically- (reaches the target with no overshoot, fastest non-bouncy settle),
   over-damped (settles slower than critical, also no overshoot; treated as critical within EPS either side
   to avoid a divide-by-zero as the underdamped/overdamped frequency terms approach zero at zeta=1). */
function stepSpring(pos, vel, target, dampingRatio, response, dt) {
  if (!(dt > 0)) return { pos, vel };
  const r = Math.max(response, EPS);
  const zeta = Math.max(dampingRatio, 0);
  const w0 = (2 * Math.PI) / r;
  const x0 = pos - target;
  const v0 = vel;
  let x, v;
  if (Math.abs(zeta - 1) < EPS) {
    // critically damped: x(t) = e^-w0t * (c1 + c2*t), c1 = x0, c2 = v0 + w0*x0
    const c1 = x0, c2 = v0 + w0 * x0;
    const e = Math.exp(-w0 * dt);
    x = e * (c1 + c2 * dt);
    v = e * (c2 - w0 * c1 - w0 * c2 * dt);
  } else if (zeta < 1) {
    // underdamped: x(t) = e^-at * (c1*cos(wd*t) + c2*sin(wd*t)), a = zeta*w0, wd = w0*sqrt(1-zeta^2)
    const a = zeta * w0;
    const wd = w0 * Math.sqrt(1 - zeta * zeta);
    const c1 = x0, c2 = (v0 + a * c1) / wd;
    const e = Math.exp(-a * dt);
    const cos = Math.cos(wd * dt), sin = Math.sin(wd * dt);
    x = e * (c1 * cos + c2 * sin);
    v = e * ((c2 * wd - a * c1) * cos + (-c1 * wd - a * c2) * sin);
  } else {
    // overdamped: same shape with cosh/sinh, wd = w0*sqrt(zeta^2-1)
    const a = zeta * w0;
    const wd = w0 * Math.sqrt(zeta * zeta - 1);
    const c1 = x0, c2 = (v0 + a * c1) / wd;
    const e = Math.exp(-a * dt);
    const cosh = Math.cosh(wd * dt), sinh = Math.sinh(wd * dt);
    x = e * (c1 * cosh + c2 * sinh);
    v = e * ((c2 * wd - a * c1) * cosh + (c1 * wd - a * c2) * sinh);
  }
  return { pos: target + x, vel: v };
}

/* Apple's momentum projection (WWDC 2018 sample code): where a scroll/flick with this release velocity
   (px/s) would coast to a stop under exponential decay. decelerationRate 0.998 is the standard "scroll"
   feel. Returns a px OFFSET from the release point (add it to the release position, not a replacement). */
function project(velocity, decelerationRate) {
  const d = decelerationRate == null ? 0.998 : decelerationRate;
  return ((velocity / 1000) * d) / (1 - d);
}

/* Apple's rubber-band resistance (WWDC 2018 sample code): the further `overshoot` px past a boundary, the
   less of it is actually applied -- a soft stop instead of a hard one, asymptotically approaching a limit
   as overshoot grows. `dim` is the relevant on-screen dimension (viewport width/height, or a control's own
   span); `constant` 0.55 is Apple's own value (smaller = stiffer resistance). */
function rubberband(overshoot, dim, constant) {
  const c = constant == null ? 0.55 : constant;
  const d = Math.max(1, dim);
  return (overshoot * d * c) / (d + c * Math.abs(overshoot));
}

/* Soft-clamp a LIVE drag value against a hard bound function (e.g. HBPanelLayout.clampDockWidth): inside
   the bound, passes through unchanged; past it, resists via rubberband() instead of stopping dead. For
   DURING-drag use only -- the caller still applies the real hardClampFn at release, so persisted state
   never holds an out-of-range value (soft while held, hard the instant it's let go, same convention as
   iOS's own rubber-band scroll). */
function softClamp(raw, hardClampFn, dim) {
  const clamped = hardClampFn(raw);
  const over = raw - clamped;
  return over === 0 ? clamped : clamped + rubberband(over, dim);
}

/* ---- release-velocity tracking: a short rolling window of {x, y, t} samples. Pure -- the caller supplies
   its own timestamps (a pointer event's own e.timeStamp), so this never reads a clock itself and stays
   Node-testable. maxAgeMs 100 mirrors native gesture recognizers: only the last ~100ms of motion should
   count, so a drag that paused then flicked isn't dragged down by its own stale start. ---- */
function createVelocityTracker(maxAgeMs) {
  return { samples: [], maxAgeMs: maxAgeMs == null ? 100 : maxAgeMs };
}
function pushSample(tracker, x, y, t) {
  tracker.samples.push({ x, y, t });
  const cutoff = t - tracker.maxAgeMs;
  while (tracker.samples.length > 2 && tracker.samples[0].t < cutoff) tracker.samples.shift();
}
/* px/s over the tracked window; {vx: 0, vy: 0} with fewer than two samples or a non-positive time span
   (out-of-order or duplicate timestamps -- never divide by zero or go negative-infinite). */
function velocityOf(tracker) {
  const s = tracker.samples;
  if (s.length < 2) return { vx: 0, vy: 0 };
  const first = s[0], last = s[s.length - 1];
  const dt = (last.t - first.t) / 1000;
  if (!(dt > 0)) return { vx: 0, vy: 0 };
  return { vx: (last.x - first.x) / dt, vy: (last.y - first.y) / dt };
}

/* Named presets, exact values from the 2026-09-28 feel-pass brief: a flick (the release carried real
   velocity) settles bouncy; a plain press-release settles critically damped. */
const PRESETS = Object.freeze({
  panelFlick: Object.freeze({ dampingRatio: 0.8, response: 0.3 }),
  panelSettle: Object.freeze({ dampingRatio: 1.0, response: 0.35 }),
});
const FLICK_VELOCITY_PX_S = 200;   // release speed above this counts as "a flick" -> panelFlick, else panelSettle
function pickPreset(vx, vy) {
  return Math.hypot(vx, vy) > FLICK_VELOCITY_PX_S ? PRESETS.panelFlick : PRESETS.panelSettle;
}

function prefersReducedMotion() {
  try { return typeof window !== 'undefined' && !!window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches; }
  catch (_) { return false; }
}

/* ---- Spring: one scalar value, driven by requestAnimationFrame. Browser only -- guarded internally so
   requiring this file on Node for the pure functions above never throws. Two of these (x, y) give
   independent-axis 2D motion, per the apple-design skill. ---- */
function Spring(initial, opts) {
  const o = opts || {};
  this.value = initial || 0;
  this.velocity = 0;
  this.target = initial || 0;
  this.dampingRatio = o.dampingRatio != null ? o.dampingRatio : 1.0;
  this.response = o.response != null ? o.response : 0.35;
  this.onUpdate = o.onUpdate || null;
  this.onSettle = o.onSettle || null;
  this._raf = 0;
  this._last = 0;
}
Spring.prototype._tick = function (now) {
  // dt is clamped so a stalled/backgrounded tab resumes with one normal-sized step, never one giant leap
  // that would fling the value straight through (or past) the target.
  const dt = Math.min(0.05, Math.max(0, (now - this._last) / 1000)) || 1 / 60;
  this._last = now;
  const r = stepSpring(this.value, this.velocity, this.target, this.dampingRatio, this.response, dt);
  this.value = r.pos; this.velocity = r.vel;
  const settled = Math.abs(this.value - this.target) < 0.01 && Math.abs(this.velocity) < 0.01;
  if (settled) { this.value = this.target; this.velocity = 0; }
  if (this.onUpdate) this.onUpdate(this.value);
  if (settled) { this._raf = 0; if (this.onSettle) this.onSettle(); return; }
  this._raf = requestAnimationFrame((t) => this._tick(t));
};
/* Re-target: carries the CURRENT value and velocity forward -- no brick wall on interrupt. An explicit
   `velocity` (e.g. a gesture's release speed) overrides the carried one; dampingRatio/response can change
   per re-target too (e.g. "settle" -> "flick" when a fresh throw starts mid-animation). */
Spring.prototype.setTarget = function (target, opts) {
  const o = opts || {};
  this.target = target;
  if (o.velocity != null) this.velocity = o.velocity;
  if (o.dampingRatio != null) this.dampingRatio = o.dampingRatio;
  if (o.response != null) this.response = o.response;
  if (!this._raf && typeof requestAnimationFrame === 'function') {
    this._last = performance.now();
    this._raf = requestAnimationFrame((t) => this._tick(t));
  }
};
/* Instant jump, no animation: a live 1:1 drag owns the value, or a reduced-motion snap. Stops any run. */
Spring.prototype.jumpTo = function (value) {
  this.stop();
  this.value = this.target = value;
  this.velocity = 0;
  if (this.onUpdate) this.onUpdate(this.value);
};
Spring.prototype.stop = function () {
  if (this._raf) { cancelAnimationFrame(this._raf); this._raf = 0; }
};
Spring.prototype.isRunning = function () { return !!this._raf; };

/* ---- DOM enter/exit for click-triggered chrome -- see the file header for why this is CSS-driven, not
   spring-stepped. Both directions ride the SAME `[data-motion]` attribute (spatial consistency: enter and
   exit are the same transform/opacity/blur delta, charts.css just plays it forwards or backwards), so there
   is exactly one set of CSS rules per surface, not two. ---- */
/* Shows `el` "materializing" in: sets an optional trigger-anchored transform-origin, forces the browser to
   paint the `[data-motion="enter"]` (hidden/offset) state at least once, then releases it one frame later so
   the transition plays toward the shown state. `origin` is a CSS transform-origin string ("140px 40px"); omit
   it for center-anchored surfaces (dialogs -- Emil Kowalski's "modals stay centered" exception). */
function materialize(el, origin) {
  if (!el) return;
  if (origin) el.style.transformOrigin = origin;
  el.setAttribute('data-motion', 'enter');
  void el.offsetWidth;   // flush styles: without this the "enter" state never actually paints before we lift it
  requestAnimationFrame(() => {
    requestAnimationFrame(() => { el.removeAttribute('data-motion'); });
  });
}
/* Starts `el` leaving (transitions to the same hidden/offset geometry materialize() started from) and calls
   `onDone` once -- on the transition's own end, or a fixed backstop, whichever comes first, so a transition
   that never fires `transitionend` (a hidden ancestor, several properties racing, a reduced-motion zero-
   duration override) never leaks the node. Disables pointer-events immediately: a leaving menu/dialog/toast
   must never still be clickable, even for the one frame before it's actually removed (its buttons' onclick
   handlers are still attached until `onDone` removes the node). */
function dematerialize(el, onDone) {
  if (!el) { if (onDone) onDone(); return; }
  el.style.pointerEvents = 'none';
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    el.removeEventListener('transitionend', onEnd);
    clearTimeout(backstop);
    if (onDone) onDone();
  };
  const onEnd = (e) => { if (e.target === el) finish(); };
  el.addEventListener('transitionend', onEnd);
  const backstop = setTimeout(finish, 260);   // comfortably past the longest leave transition in charts.css
  el.setAttribute('data-motion', 'leave');
}

const api = {
  stepSpring, project, rubberband, softClamp,
  createVelocityTracker, pushSample, velocityOf,
  PRESETS, FLICK_VELOCITY_PX_S, pickPreset, prefersReducedMotion,
  Spring, materialize, dematerialize,
};
if (typeof window !== 'undefined') window.HBSpring = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
