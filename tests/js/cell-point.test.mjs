import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* cell.js is browser-only: load it under minimal stubs (as cell-destroy.test.mjs does) and drive
   Cell.prototype.point directly -- it is pure given `this.P` and a bar with `.sv`, no chart needed. */
const require = createRequire(import.meta.url);
globalThis.window = globalThis;
globalThis.HBLayers = {};
require('../../homebase/static/charts/cell.js');
const { Cell } = globalThis.HBCell;

const point = (l, b) => Cell.prototype.point.call({ P: {} }, l, b);

test('vwap main line (part null): the vwap value, or a gap while it is still null', () => {
  const b = { tt: 1, sv: { vwap: { vwap: 100, sd: 2 } } };
  assert.deepEqual(point({ src: 'vwap', part: null }, b), { time: 1, value: 100 });
  const warming = { tt: 1, sv: { vwap: { vwap: null, sd: null } } };
  assert.deepEqual(point({ src: 'vwap', part: null }, warming), { time: 1 });
});

test('vwap band lines (part = the signed sd multiplier): value = vwap + part * sd, any multiplier', () => {
  const b = { tt: 1, sv: { vwap: { vwap: 100, sd: 2 } } };
  assert.deepEqual(point({ src: 'vwap', part: 1 }, b), { time: 1, value: 102 });
  assert.deepEqual(point({ src: 'vwap', part: -1 }, b), { time: 1, value: 98 });
  assert.deepEqual(point({ src: 'vwap', part: 2.5 }, b), { time: 1, value: 105 });
  assert.deepEqual(point({ src: 'vwap', part: -2.5 }, b), { time: 1, value: 95 });
});

test('a band gaps while sd is not ready even if vwap already is', () => {
  const b = { tt: 1, sv: { vwap: { vwap: 100, sd: null } } };
  assert.deepEqual(point({ src: 'vwap', part: 1 }, b), { time: 1 });
  assert.deepEqual(point({ src: 'vwap', part: null }, b), { time: 1, value: 100 });   // the main line does not need sd
});

test('a custom/week/month vwap key (vwap:t0200 etc.) is read the same way, by src prefix', () => {
  const b = { tt: 1, sv: { 'vwap:t0200': { vwap: 50, sd: 4 } } };
  assert.deepEqual(point({ src: 'vwap:t0200', part: null }, b), { time: 1, value: 50 });
  assert.deepEqual(point({ src: 'vwap:t0200', part: 2 }, b), { time: 1, value: 58 });
});
