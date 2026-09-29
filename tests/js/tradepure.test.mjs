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

test('HBTradePure exposes exactly the re-exported names, nothing money/desk-shaped', () => {
  // POINT_VALUE/pointValue (opus review, three-tabs): moved here from replay.js, re-exported there
  // unchanged, and read directly by fillquality.js -- see tradepure.js's own docstring.
  assert.deepEqual(Object.keys(TP).sort(),
    ['PREFS_KEY', 'bracket', 'money', 'parsePrefs', 'prefsText', 'roundTick', 'usd', 'POINT_VALUE', 'pointValue',
      'inferType', 'menuText'].sort());
  assert.equal(TP.PREFS_KEY, 'hb_trade_prefs');
});

test('HBTradePure.pointValue: the eight roots replay.js/fillquality.js both need, null for anything else', () => {
  assert.deepEqual(TP.POINT_VALUE, { NQ: 20, ES: 50, YM: 5, RTY: 50, GC: 100, SI: 5000, CL: 1000, BTC: 5 });
  assert.equal(TP.pointValue('nq'), 20);
  assert.equal(TP.pointValue('ES'), 50);
  assert.equal(TP.pointValue('XX'), null);
  assert.equal(TP.pointValue(null), null);
});

test('HBTradePure.inferType/menuText: the Practice menu\'s fallback when trade.js is not loaded '
     + '(2026-09-29 review: moved here from trade.js -- the Backtest page fell back to HBTradePure '
     + 'for these two and they did not exist, so the whole Buy/Sell/Flatten block vanished)', () => {
  const q = { bid: 30900, ask: 30900.25, last: 30900.1 };
  assert.equal(TP.inferType('Buy', 30901, q), 'Stop');
  assert.equal(TP.inferType('Buy', 30900, q), 'Limit');
  assert.equal(TP.inferType('Sell', 30900, q), 'Stop');
  assert.equal(TP.inferType('Buy', 30901, null), null);
  assert.equal(TP.menuText('Buy', 2, 30900, 'Limit', 0.25), 'Buy 2 @ 30,900.00 Limit');
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
