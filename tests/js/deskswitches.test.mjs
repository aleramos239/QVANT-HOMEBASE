import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';

/* The desk page's (homebase/static/index.html, :8850) ONE confirm policy for every switch
   (2026-09-28, Apple-design audit S6). The same-looking switch used to carry three policies:
   a strategy's on/off asked both ways, chart trading asked only when turning ON, Manage algos'
   "Show on home page" never asked. Now every switch follows chart trading's pattern: ask only
   when a flip turns ON something that can place orders; never in the safer direction; never
   for a switch that changes nothing that trades. The rule is algo-visibility.js's
   switchNeedsConfirm; the page's needsConfirm() falls back to "ask when turning on". */
const require = createRequire(import.meta.url);
const AV = require('../../homebase/static/algo-visibility.js');
const HTML = readFileSync(new URL('../../homebase/static/index.html', import.meta.url), 'utf8');
const STRAT = HTML.slice(HTML.indexOf('/* ---- strategy on/off + flatten ----'),
  HTML.indexOf('/* ---- accounts popup ---- */'));
const plain = (v) => JSON.parse(JSON.stringify(v));

test('the policy: ask only when turning ON something that can trade', () => {
  const ask = AV.switchNeedsConfirm;
  assert.equal(ask('strategy', true), true);
  assert.equal(ask('strategy', false), false, 'OFF only makes things safer');
  assert.equal(ask('strategy', true, { shadow: true }), false, 'a SHADOW strategy never places an order');
  assert.equal(ask('chartTrading', true), true);
  assert.equal(ask('chartTrading', false), false);
  assert.equal(ask('desk', true), true, 'Arm');
  assert.equal(ask('desk', false), false, 'Disarm');
  assert.equal(ask('visibility', true), false, 'showing a card changes nothing that trades');
  assert.equal(ask('visibility', false), false, 'hiding a card changes nothing that trades');
  assert.equal(ask('something-new', true), true, 'an unknown switch asks when turned on (fail toward asking)');
  assert.equal(ask('something-new', false), false);
});

test("the page's needsConfirm uses that policy, and asks whenever a switch turns on if the module is missing", () => {
  const fn = HTML.slice(HTML.indexOf('function needsConfirm('), HTML.indexOf('function cfDone('));
  const withModule = vm.createContext({ window: { AlgoVisibility: AV } });
  vm.runInContext(fn + '\nglobalThis.nc = needsConfirm;', withModule);
  assert.equal(withModule.nc('visibility', true), false);
  assert.equal(withModule.nc('strategy', true), true);
  const without = vm.createContext({ window: {} });
  vm.runInContext(fn + '\nglobalThis.nc = needsConfirm;', without);
  assert.equal(without.nc('visibility', true), true);
  assert.equal(without.nc('strategy', false), false);
  // a cached algo-visibility.js from before the rule existed must not break any switch
  const stale = vm.createContext({ window: { AlgoVisibility: { computeVisibility() {} } } });
  vm.runInContext(fn + '\nglobalThis.nc = needsConfirm;', stale);
  assert.equal(stale.nc('strategy', true), true);
  assert.equal(stale.nc('strategy', false), false);
});

const BOUNCE = HTML.slice(HTML.indexOf('const SWITCH_AT = {};'), HTML.indexOf('function cfDone('));
function load({ confirm = true, shadow = false, enabled = false } = {}) {
  const posts = [], toasts = [], confirms = [], refreshes = [];
  const clock = { now: 1_000_000 };
  const ctx = vm.createContext({
    console, Date: { now: () => clock.now }, DOUBLE_CLICK_MS: 400,
    ST: { strategies: { nq930: { cfg: { enabled, shadow } }, ym930: { cfg: { enabled, shadow } } } },
    needsConfirm: (k, on, o) => AV.switchNeedsConfirm(k, on, o),
    confirmDlg: async (title, body, action, destructive) => { confirms.push({ title, body, action, destructive }); return confirm; },
    post: async (url, body) => { posts.push({ url, body }); return { ok: true }; },
    toast: (t) => toasts.push(t),
    refresh: () => refreshes.push(true),
  });
  vm.runInContext(BOUNCE + STRAT + '\nglobalThis.api = { toggleStrat, flattenStrat };', ctx);
  return { api: ctx.api, posts, toasts, confirms, refreshes, clock };
}

test('a strategy switched ON asks first, then the same POST /api/strategy', async () => {
  const s = load();
  await s.api.toggleStrat('nq930', true);
  assert.equal(s.confirms.length, 1);
  assert.equal(s.confirms[0].title, 'Turn ON NQ930?');
  assert.equal(s.confirms[0].destructive, false);
  assert.deepEqual(plain(s.posts), [{ url: '/api/strategy', body: { strategy: 'nq930', enabled: true } }]);
  assert.equal(s.toasts[0], 'NQ930 is ON.');
});

test('declining the ON confirm sends nothing', async () => {
  const s = load({ confirm: false });
  await s.api.toggleStrat('nq930', true);
  assert.deepEqual(s.posts, []);
  assert.equal(s.refreshes.length, 1, 'the switch repaints back to OFF');
});

test('a strategy switched OFF never asks -- same POST, and the toast says positions are untouched', async () => {
  const s = load();
  await s.api.toggleStrat('nq930', false);
  assert.equal(s.confirms.length, 0);
  assert.deepEqual(plain(s.posts), [{ url: '/api/strategy', body: { strategy: 'nq930', enabled: false } }]);
  assert.match(s.toasts[0], /NQ930 is OFF — .*open positions are untouched/);
});

test('switching ON a SHADOW strategy never asks: it cannot place an order', async () => {
  const s = load({ shadow: true });
  await s.api.toggleStrat('nq930', true);
  assert.equal(s.confirms.length, 0);
  assert.deepEqual(plain(s.posts), [{ url: '/api/strategy', body: { strategy: 'nq930', enabled: true } }]);
});

test('Flatten keeps its confirm: it market-flattens a real position (not a switch)', async () => {
  const s = load();
  await s.api.flattenStrat('nq930');
  assert.equal(s.confirms.length, 1);
  assert.equal(s.confirms[0].destructive, true);
  assert.deepEqual(plain(s.posts), [{ url: '/api/strategy-flatten', body: { strategy: 'nq930' } }]);
});

test("Manage algos' Show-on-home-page switch never asks, either way", () => {
  const fn = HTML.slice(HTML.indexOf('function toggleAlgoHidden('), HTML.indexOf('$("#algoOverlay").addEventListener'));
  assert.doesNotMatch(fn, /confirmDlg\(/);
  assert.equal(AV.switchNeedsConfirm('visibility', true), false);
  assert.equal(AV.switchNeedsConfirm('visibility', false), false);
});

test('a double-click on an ON switch is one flip: OFF once, then no "Turn ON?" from the second click', async () => {
  const s = load({ enabled: true });
  await s.api.toggleStrat('nq930', false);          // click 1: OFF, no prompt (the safe direction)
  s.clock.now += 150;
  await s.api.toggleStrat('nq930', true);           // click 2 lands on the re-painted, now-OFF switch
  assert.deepEqual(plain(s.posts), [{ url: '/api/strategy', body: { strategy: 'nq930', enabled: false } }]);
  assert.equal(s.confirms.length, 0, 'the second click never opens a "Turn ON?"');
  s.clock.now += 400;
  await s.api.toggleStrat('nq930', true);           // a deliberate click later works as usual
  assert.equal(s.confirms.length, 1);
  assert.equal(s.confirms[0].title, 'Turn ON NQ930?');
});

test('the double-click guard is per switch: another strategy\'s switch is never swallowed', async () => {
  const s = load({ enabled: true });
  await s.api.toggleStrat('nq930', false);
  s.clock.now += 100;
  await s.api.toggleStrat('ym930', false);
  assert.equal(s.posts.length, 2);
});

test("a double-click's second half on the confirm's scrim is not a Cancel; the chart-trading switch has the guard too", () => {
  const scrim = HTML.slice(HTML.indexOf('$("#confirmOverlay").addEventListener("click"'), HTML.indexOf('/* ---- master controls (top bar)'));
  assert.match(scrim, /if \(e\.target === e\.currentTarget && !\(e\.detail >= 2\)\) cfDone\(false\);/);
  const ct = HTML.slice(HTML.indexOf('async function setChartTrading('), HTML.indexOf('const MD_CHOICES'));
  assert.match(ct, /if \(switchBounced\("chartTrading"\)\) return;/);
});
