import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* WP5 of the 2026-10-26 Charts clean-up: each change pinned here, the page's own code lifted and run on stand-ins. */
const rd = (f) => readFileSync(new URL(`../../homebase/static/${f}`, import.meta.url), 'utf8');
const APP = rd('charts/app.js');
const lift = (src, name) => {
  const m = new RegExp(`^(async )?function ${name}\\(`, 'm').exec(src);
  assert.ok(m, `defines ${name}`);
  return src.slice(m.index, src.indexOf('\n}\n', m.index) + 2);
};

/* app.js init() on a page without the top-bar gear: every free name it calls is a no-op that records itself. */
async function runInit({ gear }) {
  const calls = [], els = {}, saved = {};
  const el = () => ({ onclick: null, after() {}, append() {} });
  const $ = (sel) => (sel === '#tbSettings' && !gear ? null : (els[sel] ||= el()));
  const stub = new Proxy(function () {}, { get: (t, k) => (k === 'then' ? undefined : stub), apply: () => stub });
  const sandbox = {
    $, calls, saved,
    fetch: async () => ({ ok: false }),
    document: { querySelectorAll: () => [], addEventListener() {} },
    window: { addEventListener() {}, HBPanel: { mount() { calls.push('HBPanel.mount'); } } },
    setInterval() {},
  };
  const ctx = vm.createContext(sandbox);
  const own = new Set(vm.runInContext('Object.getOwnPropertyNames(globalThis)', ctx));
  sandbox.scope = new Proxy({}, {
    has: (t, k) => typeof k === 'string' && !own.has(k),
    get: (t, k) => (k === Symbol.unscopables ? undefined : k in saved ? saved[k] : (...a) => { calls.push(k); return stub; }),
    set: (t, k, v) => { saved[k] = v; return true; },
  });
  vm.runInContext(`with (scope) { ${lift(APP, 'init')} globalThis.run = init; }`, ctx);
  await ctx.run();
  return { calls, els };
}

test('5.6 Charts has no top-bar gear; init still runs to the end without it', async () => {
  assert.doesNotMatch(rd('charts.html'), /id="tbSettings"/, 'the Charts top bar has no gear');
  assert.match(rd('backtest.html'), /id="tbSettings"/, 'the Lab keeps its gear');
  const { calls, els } = await runInit({ gear: false });
  for (const n of ['initRail', 'buildGrid', 'connect', 'HBPanel.mount', 'tick']) assert.ok(calls.includes(n), `${n} ran`);
  assert.equal(typeof els['#tbTheme'].onclick, 'function', 'the bindings after the gear are made');
});

test('5.6 the Lab gear still opens the chart settings', async () => {
  const { els, calls } = await runInit({ gear: true });
  els['#tbSettings'].onclick();
  assert.ok(calls.includes('chartSettings'));
});

test('5.9 Charts does not load the lens glass; the Lab still does, and the skin still takes the lens off', () => {
  assert.doesNotMatch(rd('charts.html'), /hb-glass\.js/);
  assert.match(rd('backtest.html'), /<script src="\/static\/hb-glass\.js\?v=\d+"><\/script>/);
  assert.match(rd('apple/charts.js'), /const unlens = \(\) =>/);
});

test('5.3 the chart lines pass "2+ accounts here" into the chip text', () => {
  const TL = rd('charts/tradelines.js');
  assert.match(TL, /this\.named = window\.HBTradeUI\.tradeOf\(this\.cell\)\.accounts\.length > 1 \|\| new Set\(groups\.flatMap/);
  assert.match(TL, /T\.lineText\(it\.g, q \? q\.last : null, this\.cell\.tick, !!this\.named\)/);
});
