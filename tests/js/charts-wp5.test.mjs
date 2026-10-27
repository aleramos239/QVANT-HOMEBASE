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

test('5.4 the button and the ENTRY tag read their words from the send\'s own qty and accounts; the sends are untouched', () => {
  const TL = rd('charts/tradelines.js'), OP = rd('charts/orderpanel.js');
  assert.match(TL, /T\.sendTag\(side, Dc\.prefs\.qty, this\.root, mode\.accounts, Dc\.state\)/);
  // trade() still sends the same qty, root and type it always did
  assert.match(TL, /placeOrder\(\{ cell: this\.cell, root: this\.root, side, type: 'Market', qty: window\.HBDeskClient\.prefs\.qty, surface: 'chart' \}\)/);
  assert.match(OP, /T\.sendTag\(st\.side, Number\.isInteger\(n\) \? n : 0, c\.root, m\.mode === 'on' \? m\.accounts : \[\], D\(\)\.state\)\.full/);
  assert.match(OP, /title: `ENTRY · \$\{tag\}\$\{rr\}`/);
});

test('5.2 the account spot\'s chips open this chart\'s Settings › Trading and do nothing else', () => {
  const TL = rd('charts/tradelines.js');
  const body = TL.slice(TL.indexOf('  paintAccts(mode) {'), TL.indexOf('  /* ---- lines: positions'));
  assert.match(body, /T\.tradeSpot\(t\.accounts\.length, mode\.mode === 'on', !!this\.cell\.replay \|\| !!cfg\.replayHalt\)/);
  assert.match(body, /el\.onclick = \(e\) => \{ e\.stopPropagation\(\); el\.blur\(\); this\.page\.chartSettings\(this\.cell, 'trading'\); \};/);
  assert.doesNotMatch(body, /toggleAccount|setCellTrade|placeOrder|send\(/, 'a chip never ticks an account or sends');
  assert.match(rd('charts/app.js'), /^function chartSettings\(c = cur\(\), tab = null\)/m);
});

test('5.5 Fill quality: its tab shows only while the desk runs one of its bots; the code and its tab stay', () => {
  const PANEL = rd('charts/panel.js');
  assert.match(PANEL, /addTab\(\{ id: 'fillq', label: 'Fill quality', render: renderFillQuality \}\)/, 'still registered');
  const run = (state, active = 'fillq', open = true) => {
    const tabs = [{ id: 'positions', btn: { hidden: false } }, { id: 'fillq', btn: { hidden: false } }];
    const ctx = vm.createContext({ tabs, state, renders: 0, bars: 0, isOpen: open, activeId: active });
    vm.runInContext(`const BOT_KEYS = ['nq930']; const D = () => ({ state });
      function renderTabsBar() { bars++; } function renderActive() { renders++; }
      ${lift(PANEL, 'fillqLive')}${lift(PANEL, 'paintFillq')} paintFillq();`, ctx);
    return { hidden: tabs[1].btn.hidden, active: ctx.activeId, renders: ctx.renders };
  };
  assert.deepEqual(run({ bot: { strategies: {} } }), { hidden: true, active: 'positions', renders: 1 }, 'no bot: hidden, the panel moves off it');
  assert.deepEqual(run(null), { hidden: true, active: 'positions', renders: 1 }, 'no desk yet: hidden');
  assert.deepEqual(run({ bot: { strategies: { gc_nfpcpi: {} } } }, 'positions'), { hidden: true, active: 'positions', renders: 0 });
  assert.deepEqual(run({ bot: { strategies: { nq930: {} } } }), { hidden: false, active: 'fillq', renders: 0 }, 'its bot runs: shown');
});
