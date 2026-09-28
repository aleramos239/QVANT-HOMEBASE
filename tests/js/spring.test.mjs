import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const S = require('../../homebase/static/charts/spring.js');

/* ---- stepSpring: the analytic damped oscillator ---- */

test('stepSpring: dt <= 0 is a no-op (never divides by zero, never rewinds)', () => {
  assert.deepEqual(S.stepSpring(10, 5, 0, 1, 0.35, 0), { pos: 10, vel: 5 });
  assert.deepEqual(S.stepSpring(10, 5, 0, 1, 0.35, -1), { pos: 10, vel: 5 });
});

test('stepSpring: critically damped, released from rest, never overshoots the target', () => {
  let pos = 100, vel = 0;
  const target = 0;
  let crossed = false;
  for (let i = 0; i < 600; i++) {
    const r = S.stepSpring(pos, vel, target, 1.0, 0.35, 1 / 60);
    if (Math.sign(r.pos - target) !== Math.sign(pos - target) && r.pos !== target) crossed = true;
    pos = r.pos; vel = r.vel;
  }
  assert.equal(crossed, false);
  assert.ok(Math.abs(pos - target) < 0.01, `should have settled near target, got ${pos}`);
});

test('stepSpring: underdamped, released from rest, overshoots the target at least once', () => {
  let pos = 100, vel = 0;
  const target = 0;
  let crossed = false;
  for (let i = 0; i < 600; i++) {
    const r = S.stepSpring(pos, vel, target, 0.5, 0.35, 1 / 60);
    if (Math.sign(r.pos - target) !== Math.sign(pos - target) && pos !== target) crossed = true;
    pos = r.pos; vel = r.vel;
  }
  assert.equal(crossed, true);
});

test('stepSpring: overdamped settles without overshoot, slower than critical', () => {
  let posOver = 100, velOver = 0, posCrit = 100, velCrit = 0;
  const target = 0;
  let overCrossed = false;
  for (let i = 0; i < 30; i++) {   // a handful of steps: enough to compare settle progress, not full settle
    const ro = S.stepSpring(posOver, velOver, target, 1.6, 0.35, 1 / 60);
    if (Math.sign(ro.pos - target) !== Math.sign(posOver - target) && posOver !== target) overCrossed = true;
    posOver = ro.pos; velOver = ro.vel;
    const rc = S.stepSpring(posCrit, velCrit, target, 1.0, 0.35, 1 / 60);
    posCrit = rc.pos; velCrit = rc.vel;
  }
  assert.equal(overCrossed, false);
  // overdamped has moved LESS far toward the target than critical over the same time (the textbook property)
  assert.ok(Math.abs(posOver - target) > Math.abs(posCrit - target));
});

test('stepSpring: converges to target with ~zero velocity for a range of damping ratios', () => {
  for (const dampingRatio of [0.3, 0.6, 0.8, 1.0, 1.4, 2.0]) {
    let pos = -40, vel = 300;
    for (let i = 0; i < 1000; i++) {
      const r = S.stepSpring(pos, vel, 0, dampingRatio, 0.3, 1 / 60);
      pos = r.pos; vel = r.vel;
    }
    assert.ok(Math.abs(pos) < 0.02, `dampingRatio ${dampingRatio}: pos ${pos}`);
    assert.ok(Math.abs(vel) < 0.02, `dampingRatio ${dampingRatio}: vel ${vel}`);
  }
});

test('stepSpring: the reported velocity matches a numeric (finite-difference) derivative of position', () => {
  for (const dampingRatio of [0.6, 1.0, 1.3]) {
    const pos0 = 50, vel0 = -120, target = 10, response = 0.4, t = 0.12, h = 1e-4;
    const a = S.stepSpring(pos0, vel0, target, dampingRatio, response, t - h / 2);
    const b = S.stepSpring(pos0, vel0, target, dampingRatio, response, t + h / 2);
    const numericVel = (b.pos - a.pos) / h;
    const r = S.stepSpring(pos0, vel0, target, dampingRatio, response, t);
    assert.ok(Math.abs(numericVel - r.vel) < 0.5, `dampingRatio ${dampingRatio}: analytic ${r.vel} vs numeric ${numericVel}`);
  }
});

test('stepSpring: velocity carries continuously across a re-target (no brick wall)', () => {
  // one 200ms step, vs. two 100ms steps with the SAME target throughout -- must land on the same state;
  // this is exactly what a re-target relies on (the second call picks up the first's own pos/vel).
  const whole = S.stepSpring(0, 400, 100, 0.8, 0.3, 0.2);
  const half1 = S.stepSpring(0, 400, 100, 0.8, 0.3, 0.1);
  const half2 = S.stepSpring(half1.pos, half1.vel, 100, 0.8, 0.3, 0.1);
  assert.ok(Math.abs(whole.pos - half2.pos) < 1e-6);
  assert.ok(Math.abs(whole.vel - half2.vel) < 1e-6);
});

/* ---- project() ---- */

test('project: matches Apple\'s exponential-decay formula exactly', () => {
  assert.ok(Math.abs(S.project(1000, 0.998) - 499) < 1e-9);
  assert.equal(S.project(0), 0);
  assert.equal(S.project(0, 0.998), 0);
});

test('project: a faster release projects farther, in the same direction', () => {
  assert.ok(S.project(2000) > S.project(1000));
  assert.ok(S.project(-1000) < 0);
  assert.ok(S.project(1000) > 0);
});

/* ---- rubberband() ---- */

test('rubberband: zero overshoot is zero resistance', () => {
  assert.equal(S.rubberband(0, 400), 0);
});

test('rubberband: odd-symmetric (past either side of a boundary resists the same amount)', () => {
  assert.ok(Math.abs(S.rubberband(120, 400) + S.rubberband(-120, 400)) < 1e-9);
});

test('rubberband: sublinear -- doubling the overshoot less than doubles the applied distance', () => {
  const r100 = S.rubberband(100, 400), r200 = S.rubberband(200, 400);
  assert.ok(r200 > r100);        // still resists more the further past the edge...
  assert.ok(r200 < 2 * r100);    // ...but with diminishing returns, never linear
});

test('rubberband: a stiffer constant resists more for the same overshoot', () => {
  assert.ok(S.rubberband(150, 400, 0.3) < S.rubberband(150, 400, 0.55));
});

/* ---- softClamp() ---- */

test('softClamp: inside the bound passes through unchanged', () => {
  const hard = (v) => Math.min(480, Math.max(260, v));
  assert.equal(S.softClamp(320, hard, 480), 320);
});

test('softClamp: past the bound resists, landing strictly between the hard clamp and the raw value', () => {
  const hard = (v) => Math.min(480, Math.max(260, v));
  const soft = S.softClamp(650, hard, 480);
  assert.ok(soft > 480);     // still past the hard bound -- it's a SOFT stop, not another hard one
  assert.ok(soft < 650);     // but resisted well short of the raw drag distance
});

/* ---- velocity tracker ---- */

test('velocity tracker: one sample has no velocity yet', () => {
  const t = S.createVelocityTracker();
  S.pushSample(t, 10, 20, 1000);
  assert.deepEqual(S.velocityOf(t), { vx: 0, vy: 0 });
});

test('velocity tracker: two samples give an exact px/s rate', () => {
  const t = S.createVelocityTracker();
  S.pushSample(t, 0, 0, 0);
  S.pushSample(t, 100, -50, 200);   // 100px in 200ms = 500px/s
  const v = S.velocityOf(t);
  assert.ok(Math.abs(v.vx - 500) < 1e-9);
  assert.ok(Math.abs(v.vy - (-250)) < 1e-9);
});

test('velocity tracker: samples older than maxAgeMs are dropped, so a pause-then-flick reads the flick', () => {
  const t = S.createVelocityTracker(100);
  S.pushSample(t, 0, 0, 0);
  S.pushSample(t, 1, 0, 90);      // slow drift, about to age out
  S.pushSample(t, 5, 0, 150);     // still slow
  S.pushSample(t, 205, 0, 200);   // the flick: 200px in 50ms = 4000px/s
  const v = S.velocityOf(t);
  assert.ok(v.vx > 1000, `expected a fast reading dominated by the flick, got ${v.vx}`);
});

/* ---- preset selection ---- */

test('pickPreset: a fast release picks the bouncy flick preset', () => {
  assert.equal(S.pickPreset(300, 0), S.PRESETS.panelFlick);
  assert.equal(S.pickPreset(0, -300), S.PRESETS.panelFlick);
});

test('pickPreset: a slow or motionless release picks the critically-damped settle preset', () => {
  assert.equal(S.pickPreset(0, 0), S.PRESETS.panelSettle);
  assert.equal(S.pickPreset(50, 50), S.PRESETS.panelSettle);
});

test('PRESETS: panelFlick bounces (dampingRatio < 1), panelSettle does not (dampingRatio === 1)', () => {
  assert.ok(S.PRESETS.panelFlick.dampingRatio < 1);
  assert.equal(S.PRESETS.panelSettle.dampingRatio, 1.0);
});

/* ---- Spring (the rAF wrapper's synchronous surface -- jumpTo/setTarget never require a DOM) ---- */

test('Spring: constructs at the initial value with zero velocity', () => {
  const s = new S.Spring(42);
  assert.equal(s.value, 42);
  assert.equal(s.velocity, 0);
  assert.equal(s.target, 42);
});

test('Spring#jumpTo: instant, synchronous, no animation loop started', () => {
  const s = new S.Spring(0);
  let updates = 0;
  s.onUpdate = () => { updates += 1; };
  s.jumpTo(75);
  assert.equal(s.value, 75);
  assert.equal(s.target, 75);
  assert.equal(s.velocity, 0);
  assert.equal(s.isRunning(), false);
  assert.equal(updates, 1);
});

test('Spring#setTarget: updates the target (and, on Node, never throws without requestAnimationFrame)', () => {
  const s = new S.Spring(10);
  assert.doesNotThrow(() => s.setTarget(90, { velocity: 500 }));
  assert.equal(s.target, 90);
  assert.equal(s.velocity, 500);
});

/* ---- prefersReducedMotion: safe outside a browser ---- */

test('prefersReducedMotion: false (never throws) when there is no window', () => {
  assert.equal(S.prefersReducedMotion(), false);
});
