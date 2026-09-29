import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
// Loaded directly (not through trade.js): these are the exact functions the Backtest page's
// replayui.js / tester.js / testerui.js fall back to when window.HBTrade doesn't exist
// (2026-09-28 three-tabs plan). trade.test.mjs covers the SAME cases through trade.js's own
// re-export, as a regression check that the delegation there is transparent.
const TP = require('../../homebase/static/charts/tradepure.js');
const M = '−';

test('HBTradePure exposes exactly the five re-exported names, nothing money/desk-shaped', () => {
  assert.deepEqual(Object.keys(TP).sort(), ['PREFS_KEY', 'bracket', 'money', 'parsePrefs', 'prefsText', 'roundTick', 'usd'].sort());
  assert.equal(TP.PREFS_KEY, 'hb_trade_prefs');
});

test('prefs: defaults, clamps, de-duplicated ticks, garbage in -> defaults', () => {
  const dflt = { ticked: [], oneClick: false, oneClickChart: true, oneClickPanel: true, qty: 1, slTicks: 0, tpTicks: 0 };
  assert.deepEqual(TP.parsePrefs(null), dflt);
  assert.deepEqual(TP.parsePrefs('garbage'), dflt);
  assert.deepEqual(TP.parsePrefs('[1]'), dflt);
  assert.deepEqual(TP.parsePrefs(JSON.stringify({ ticked: ['a', 'a', 5, ''], oneClick: true, qty: 3.6, slTicks: -2, tpTicks: '8' })),
    { ticked: ['a'], oneClick: true, oneClickChart: true, oneClickPanel: true, qty: 4, slTicks: 0, tpTicks: 0 });
  assert.equal(TP.prefsText({ qty: 0 }), JSON.stringify(dflt));
});

test('prefs: the two one-click switches take the old single value on first read, then keep their own', () => {
  const old = (v) => TP.parsePrefs(JSON.stringify({ oneClick: v, qty: 2 }));
  assert.equal(old(false).oneClickChart, true, 'the old single pref is not carried over');
  assert.equal(old(true).oneClickPanel, true);
  const own = TP.parsePrefs(JSON.stringify({ oneClick: false, oneClickChart: true, oneClickPanel: false }));
  assert.deepEqual([own.oneClick, own.oneClickChart, own.oneClickPanel], [false, true, false]);
  assert.equal(TP.parsePrefs(JSON.stringify({ oneClickChart: 'yes' })).oneClickChart, true, 'garbage -> the default');
});

test('prefs: stored SL/TP tick defaults can no longer attach a bracket', () => {
  const p = TP.parsePrefs(JSON.stringify({ slTicks: 20, tpTicks: 40 }));
  assert.deepEqual([p.slTicks, p.tpTicks], [0, 0]);
  assert.deepEqual(TP.bracket('Buy', 30900, p, 0.25), { sl: null, tp: null });
});

test('brackets from ticks (0 = off), both sides, and ref/tick edge cases -- PracticeSim reads this exactly like the real Buy/Sell block', () => {
  const p = { slTicks: 20, tpTicks: 40 };
  assert.deepEqual(TP.bracket('Buy', 30900, p, 0.25), { sl: 30895, tp: 30910 });
  assert.deepEqual(TP.bracket('Sell', 30900, p, 0.25), { sl: 30905, tp: 30890 });
  assert.deepEqual(TP.bracket('Buy', 30900, { slTicks: 0, tpTicks: 0 }, 0.25), { sl: null, tp: null });
  assert.deepEqual(TP.bracket('Buy', null, p, 0.25), { sl: null, tp: null });
  assert.deepEqual(TP.bracket('Buy', 30900, p, 0), { sl: null, tp: null });
});

test('roundTick: snaps to the tick grid, respecting decimals', () => {
  assert.equal(TP.roundTick(30900.1, 0.25), 30900);
  assert.equal(TP.roundTick(30900.13, 0), 30900.13);   // tick 0: unchanged (no grid)
});

test('money/usd: signed vs unsigned formatting', () => {
  assert.deepEqual([450, -1212.5, 0, null].map(TP.usd), ['+$450', `${M}$1,212.50`, '$0', null]);
  assert.deepEqual([450, -3, null].map(TP.money), ['$450', `${M}$3`, '—']);
});
