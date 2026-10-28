import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';

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
    window: { addEventListener() {}, HBPanel: { mount() { calls.push('HBPanel.mount'); } }, HBChartMenu: { register() {} } },
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
  assert.doesNotMatch(rd('charts.html'), /<script[^>]*hb-glass\.js/);
  assert.match(rd('backtest.html'), /<script src="\/static\/hb-glass\.js\?v=\d+"><\/script>/);
  assert.match(rd('apple/charts.js'), /const unlens = \(\) =>/);
});

test('5.3 the chart lines pass "2+ accounts here" into the chip text', () => {
  const TL = rd('charts/tradelines.js');
  assert.match(TL, /this\.named = window\.HBTradeUI\.tradeOf\(this\.cell\)\.accounts\.length > 1 \|\| new Set\(groups\.flatMap/);
  assert.match(TL, /T\.lineText\(it\.g, q \? q\.last : null, this\.cell\.tick, !!this\.named, /);
});

test('5.4 the button and the ENTRY tag read their words from the send\'s own qty and accounts; the sends are untouched', () => {
  const TL = rd('charts/tradelines.js'), OP = rd('charts/orderpanel.js');
  assert.match(TL, /T\.sendTag\(side, Dc\.prefs\.qty, this\.root, mode\.accounts, Dc\.state\)/);
  // trade() still sends the same qty, root and type it always did
  assert.match(TL, /placeOrder\(\{ cell: this\.cell, root: this\.root, side, type: 'Market', qty: window\.HBDeskClient\.prefs\.qty, surface: 'chart' \}\)/);
  assert.match(OP, /T\.sendTag\(st\.side, Number\.isInteger\(n\) \? n : 0, c\.root, m\.mode === 'on' \? m\.accounts : \[\], D\(\)\.state\)\.tag;/);
  assert.match(OP, /title: `ENTRY · \$\{tag\}\$\{rr\}`/);
});

test('5.2 the account spot\'s chips open this chart\'s Settings › Trading and do nothing else', () => {
  const TL = rd('charts/tradelines.js');
  const body = TL.slice(TL.indexOf('  paintAccts(mode) {'), TL.indexOf('  /* ---- lines: positions'));
  assert.match(body, /T\.tradeSpot\(t\.accounts\.length, mode\.mode === 'on', !!this\.cell\.replay \|\| !!cfg\.replayHalt, !window\.HBDeskClient\.gate\(\)\)/);
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

test('5.8 the status bar shows "md" and "rec" only near their limit; the Live tooltip always says both', () => {
  const limitTexts = vm.runInNewContext(`(${lift(APP, 'limitTexts')})`);
  const live = (md, buffered) => ({ mode: 'live', md: 'live', budget_hour: md, recorder: buffered == null ? null : { buffered } });
  const calm = limitTexts(live(12, 1234), 5000);
  assert.deepEqual([calm.md, calm.rec], ['', ''], 'far from both limits: nothing on the bar');
  assert.match(calm.title, /12\/180 chart requests this hour/);
  assert.match(calm.title, /recorder 1,234 ticks not written yet/);
  assert.equal(limitTexts(live(149, 0), 5000).md, '');
  assert.equal(limitTexts(live(150, 0), 5000).md, 'md 150/180', 'near the md limit it shows');
  assert.equal(limitTexts(live(12, 5000), 5000).rec, 'rec 5,000', 'at the recorder\'s amber line it shows');
  assert.equal(calm.recTitle, 'Recorder: 1,234 ticks buffered, not written yet', 'the rec tooltip, worked out once');
  assert.deepEqual({ ...limitTexts({ mode: 'replay', budget_hour: 170, recorder: { buffered: 9000 } }, 5000) }, { md: '', rec: '', title: '', recTitle: '' });
  assert.equal(limitTexts(live(undefined, null), 5000).title, 'Market data live · 0/180 chart requests this hour');
});

test('5.8 the desk\'s "max …/order, …/position" part is gone from both status bars and from the code that filled it', () => {
  for (const page of ['charts.html', 'backtest.html']) assert.doesNotMatch(rd(page), /sbDeskLim/, page);
  assert.doesNotMatch(rd('charts/tradeui.js'), /sbDeskLim|s\.limits/);
  assert.doesNotMatch(rd('charts/trade.js'), /max_order_qty/);
});

test('5.11 the tab menu: Close leads, Delete is last behind a divider and still asks first; Close never deletes', () => {
  const calls = [];
  const item = (text, k, run) => ({ text, run, classList: { add() {} } });
  const m = { items: [], append(...a) { this.items.push(...a); }, focus() {} };
  const ctx = vm.createContext({
    openMenu: () => m, menuItem: item, mk: (t, cls) => ({ sep: cls === 'menu-sep' }), placeMenu() {}, closeMenu() {},
    closeTab: (n) => calls.push(['close', n]), renameTab: (n) => calls.push(['rename', n]),
    duplicateTab: (n) => calls.push(['duplicate', n]), deleteLayoutTab: (n) => calls.push(['delete-confirm', n]),
  });
  vm.runInContext(`${lift(APP, 'tabContextMenu')} globalThis.run = tabContextMenu;`, ctx);
  ctx.run('HTF', { x: 0, y: 0 });
  assert.deepEqual(m.items.map((i) => (i.sep ? '—' : i.text)), ['Close', 'Rename', 'Duplicate', '—', 'Delete layout…']);
  m.items[0].run();
  assert.deepEqual(calls, [['close', 'HTF']], 'Close only closes the tab');
  m.items[4].run();
  assert.deepEqual(calls.at(-1), ['delete-confirm', 'HTF'], 'Delete goes through its confirm dialog');
  const del = lift(APP, 'deleteLayoutTab'), close = lift(APP, 'closeTab');
  assert.match(del, /openDialog\('Delete layout'/);
  assert.ok(del.indexOf("method: 'DELETE'") > del.indexOf('del.onclick'), 'the DELETE is sent only from the dialog\'s Delete button');
  assert.doesNotMatch(close, /fetch|DELETE/, 'closing a tab never touches the server copy');
});

test('5.12 the chart lines read the desk\'s marks for display only: grey, "not working" on the chip, every click path as before', () => {
  const TL = rd('charts/tradelines.js');
  assert.match(TL, /g\.gone = T\.lineGone\(g, gone\);/);
  assert.match(TL, /\(it\.g\.gone \? ' · not working' : ''\)/);
  assert.doesNotMatch(TL, /gone[^\n]*(onclick|onpointerdown|disabled)/, 'the mark never touches a click, a drag or the ×');
  assert.match(rd('charts/charts.css'), /\.tl-chip\.gone \{ opacity: \.6; \}/);
});

/* The Overlay's own methods, lifted from tradelines.js and run on a stand-in chart: a tiny fake DOM, the real HBTrade,
   stubbed HBTradeUI / HBDeskClient. */
const TL_SRC = rd('charts/tradelines.js');
const method = (name) => {
  const i = TL_SRC.indexOf(`\n  ${name}(`);
  assert.ok(i >= 0, `defines ${name}`);
  return TL_SRC.slice(i + 1, TL_SRC.indexOf('\n  }\n', i) + 4);
};
const fakeEl = (tagName) => ({ tagName, className: '', textContent: '', title: '', hidden: false, disabled: false, children: [],
  classList: { on: new Set(), toggle(c, v) { if (v) this.on.add(c); else this.on.delete(c); }, contains(c) { return this.on.has(c); } },
  append(...k) { this.children.push(...k); }, replaceChildren(...k) { this.children = k; }, blur() {} });
function overlayOn({ ticked, mode, gate = null, qty = 1 }) {
  const T = createRequire(import.meta.url)('../../homebase/static/charts/trade.js');
  const live = (id) => id === 'live099';
  const state = { enabled: true, accounts: [
    { id: 'live099', label: 'FAKELIVE099', env: 'live', tradable: true }, { id: 'sim047', label: 'SIM0000047', env: 'demo', tradable: true }] };
  const calls = [], sent = [];
  const window = {
    HBDeskClient: { state, prefs: { qty }, gate: () => gate },
    HBTradeUI: { tradeOf: () => ({ accounts: ticked }), liveCue: () => (mode.mode === 'on' ? mode.accounts.filter(live) : []),
      busy: () => false, flatBusy: () => false, sending: () => null, placeOrder: (o) => sent.push(o) },
  };
  const ctx = vm.createContext({ window, T, document: { createElement: fakeEl, activeElement: null } });
  vm.runInContext(`${lift(TL_SRC, 'mk')} globalThis.O = { ${method('trade')}, ${method('paintBlock')}, ${method('paintAccts')} };`, ctx);
  const ov = { cell: { cfg: {}, replay: false }, root: 'NQ', page: { chartSettings: (c, tab) => calls.push(['settings', tab]) },
    block: fakeEl('div'), accts: fakeEl('div'), qty: fakeEl('input'), sellBtn: fakeEl('button'), buyBtn: fakeEl('button'),
    flatBtn: fakeEl('button'), sellSub: fakeEl('span'), buySub: fakeEl('span'), sellLive: fakeEl('span'), buyLive: fakeEl('span'), naked: fakeEl('span') };
  for (const k of ['trade', 'paintBlock', 'paintAccts']) ov[k] = ctx.O[k].bind(ov);
  return { ov, calls, sent };
}
const texts = (box) => box.children.map((c) => [c.textContent, ...c.children.map((k) => k.textContent)].join(' '));

test('5.4 run: the BUY / SELL words are the qty and accounts the click sends', () => {
  const { ov, sent } = overlayOn({ ticked: ['live099'], mode: { mode: 'on', accounts: ['live099'] }, qty: 2 });
  ov.paintBlock({ mode: 'on', accounts: ['live099'] });
  assert.equal(ov.block.hidden, false);
  assert.equal(ov.buySub.textContent, '2 NQ · …099');
  assert.equal(ov.sellBtn.title, 'SELL 2 NQ · …099 LIVE · at market');
  ov.trade('Buy');
  assert.deepEqual(sent.map((o) => [o.side, o.qty, o.root, o.type]), [['Buy', 2, 'NQ', 'Market']], 'the qty on the button is the qty sent');
  const two = overlayOn({ ticked: ['live099', 'sim047'], mode: { mode: 'on', accounts: ['live099', 'sim047'] }, qty: 3 });
  two.ov.paintBlock({ mode: 'on', accounts: ['live099', 'sim047'] });
  assert.equal(two.ov.buyBtn.title, 'BUY 3 NQ each · 2 accounts (1 LIVE) · at market');
  assert.equal(two.ov.buySub.textContent, '3 NQ ×2', 'short enough for the 76px button');
});

test('5.2 run: the account spot -- "Accounts:" when it cannot trade, "Trade on: none" only while the desk trades; a chip only opens Settings › Trading', () => {
  const off = overlayOn({ ticked: ['live099'], mode: { mode: 'none', accounts: [] } });
  off.ov.paintAccts({ mode: 'none', accounts: [] });
  assert.equal(off.ov.accts.hidden, false);
  assert.deepEqual(texts(off.ov.accts), ['Accounts:', '…099 LIVE']);
  assert.equal(off.ov.accts.children[1].className, 'tr-acct off', 'dimmed: not trading from this chart right now');
  off.ov.accts.children[1].onclick({ stopPropagation() {} });
  assert.deepEqual(off.calls, [['settings', 'trading']]);
  assert.deepEqual(off.sent, [], 'a chip never sends');
  const on = overlayOn({ ticked: ['live099'], mode: { mode: 'on', accounts: ['live099'] } });
  on.ov.paintAccts({ mode: 'on', accounts: ['live099'] });
  assert.deepEqual(texts(on.ov.accts), ['…099 LIVE'], 'beside a showing BUY / SELL: no lead');
  assert.equal(on.ov.accts.children[0].className, 'tr-acct');
  const none = overlayOn({ ticked: [], mode: { mode: 'off', accounts: [] } });
  none.ov.paintAccts({ mode: 'off', accounts: [] });
  assert.deepEqual(texts(none.ov.accts), ['Trade on: none']);
  const down = overlayOn({ ticked: [], mode: { mode: 'down', accounts: [] }, gate: { mode: 'off' } });
  down.ov.paintAccts({ mode: 'off', accounts: [] });
  assert.equal(down.ov.accts.hidden, true, 'chart trading off at the desk: no prompt on every chart');
});

test('5.12 run: a chip whose order the desk said is not working reads so and greys; unmarked, it is as before', () => {
  const T = createRequire(import.meta.url)('../../homebase/static/charts/trade.js');
  const ctx = vm.createContext({ window: { HBDeskClient: { quotes: {} } }, T });
  vm.runInContext(`globalThis.O = { ${method('paint')} };`, ctx);
  const props = {};
  const chip = { ...fakeEl('div'), text: fakeEl('span'), style: { setProperty: (k, v) => { props[k] = v; } } };
  const g = { kind: 'sl', side: 'Sell', qty: 1, price: 29990, legs: [{ account: 'sim041', order_id: '7', who: '…041' }] };
  const ov = { root: 'NQ', named: false, items: new Map(), cell: { tick: 0.25, P: { up: 'U', down: 'D', accent: 'A', text2: 'G' } } };
  const paint = ctx.O.paint.bind(ov);
  paint({ g: { ...g, gone: true }, chip });
  assert.match(chip.text.textContent, / · not working$/);
  assert.equal(props['--c'], 'G');
  assert.equal(chip.classList.contains('gone'), true);
  assert.match(chip.title, /not working/);
  paint({ g, chip });
  assert.doesNotMatch(chip.text.textContent, /not working/);
  assert.equal(props['--c'], 'D', 'its own colour back');
  assert.equal(chip.classList.contains('gone'), false);
});
