import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

const require = createRequire(import.meta.url);
const G = require('../../homebase/static/hb-glass.js');
const SRC = readFileSync(new URL('../../homebase/static/hb-glass.js', import.meta.url), 'utf8');

test('edge: distance in from a rounded rectangle and the outward normal', () => {
  const mid = G.edge(100, 20, 200, 40, 20);
  assert.equal(mid.d, 20);
  const top = G.edge(100, 2, 200, 40, 20);
  assert.equal(Math.round(top.d), 2); assert.deepEqual([top.nx, top.ny], [0, -1]);
  const left = G.edge(3, 20, 200, 40, 20);
  assert.equal(Math.round(left.nx), -1);
  assert.ok(G.edge(0.5, 0.5, 200, 40, 20).d < 0, 'the square corner is outside the rounded shape');
});

test('bend: the flat middle barely moves the picture, the lip pulls it inward, hardest at the rim', () => {
  const [cx, cy] = G.bend(100, 30, 200, 60, 30);
  assert.ok(Math.abs(cx) < 0.01 && Math.abs(cy) < 0.01, 'the centre is still');
  const rim = G.bend(100, 1.5, 200, 60, 30), inner = G.bend(100, 12, 200, 60, 30);
  assert.ok(rim[1] > inner[1] && inner[1] > 0, `top lip samples from further inside (down): rim ${rim[1]}, inner ${inner[1]}`);
  const l = G.bend(1.5, 30, 200, 60, 30), r = G.bend(198.5, 30, 200, 60, 30);
  assert.ok(l[0] > 0 && r[0] < 0 && Math.abs(l[0] + r[0]) < 1e-6, 'left and right mirror each other');
  for (const v of [...rim, ...l]) assert.ok(Number.isFinite(v) && Math.abs(v) < 80);
});

test('glint: brightest facing the light, a dark line on the far side, nothing in the flat middle', () => {
  const s = Math.SQRT1_2, lit = G.glint(0.7, -s, -s, 20, false), far = G.glint(6, s, s, 20, false), mid = G.glint(25, 0, -1, 20, false);
  assert.ok(lit[0] > 0.8 && lit[1] < 0.05);
  assert.ok(far[1] > far[0] * 0.5 && far[1] > 0.02);
  assert.deepEqual(mid, [0, 0]);
  assert.ok(G.glint(0.7, -s, -s, 20, true)[0] < lit[0], 'calmer on dark');
});

test('it only paints: no network, no storage, no handlers beyond the pointer sheen', () => {
  assert.doesNotMatch(SRC, /fetch\(|XMLHttpRequest|localStorage|sessionStorage|\.onclick|addEventListener\('(click|keydown|submit)/);
  assert.match(SRC, /CSS\.supports\('backdrop-filter', 'url\(#a\)'\)/, 'the bend is used only where the browser can do it');
  assert.match(SRC, /prefers-reduced-transparency/);
});
