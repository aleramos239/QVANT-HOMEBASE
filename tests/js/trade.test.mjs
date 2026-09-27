import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const T = require('../../homebase/static/charts/trade.js');
const D = require('../../homebase/static/charts/drawings.js');
const M = '−';
const P = { up: '#089981', down: '#F23645', accent: '#2962FF', warn: '#F7A600' };

const acct = (id, label, env, extra = {}) => ({ id, label, env, connected: true, tradable: true, error: null,
  balance: 50000, realized_pnl: 0, positions: [], orders: [], fills: [], strategies: [], ...extra });
const STATE = {
  enabled: true, limits: { max_order_qty: 10, max_position_qty: 20 },
  accounts: [
    acct('sim041', 'SIM0000041', 'demo', {
      positions: [{ symbol: 'NQZ6', net: 2, avg_price: 30900, root: 'NQ', point_value: 20 }],
      orders: [
        { order_id: '11', symbol: 'NQZ6', side: 'Sell', type: 'Stop', qty: 2, price: null, stop_price: 30885, owner: null },
        { order_id: '12', symbol: 'NQZ6', side: 'Sell', type: 'Limit', qty: 2, price: 30930, stop_price: null, owner: null },
        { order_id: '13', symbol: 'NQZ6', side: 'Buy', type: 'Limit', qty: 1, price: 30880, stop_price: null, owner: null },
        { order_id: '14', symbol: 'NQZ6', side: 'Sell', type: 'Stop', qty: 1, price: null, stop_price: 30890, owner: 'nq930' }],
      fills: [{ id: 1, order_id: '9', symbol: 'NQZ6', side: 'Buy', qty: 2, price: 30900, time: '2026-09-22T13:31:12.000Z', owner: null },
        { id: 2, order_id: '8', symbol: 'NQZ6', side: 'Buy', qty: 1, price: 30910, time: '2026-09-22T13:30:01.000Z', owner: 'nq930' }],
      strategies: ['nq930'] }),
    acct('sim047', 'SIM0000047', 'demo', {
      positions: [{ symbol: 'NQZ6', net: 1, avg_price: 30900, root: 'NQ', point_value: 20 }],
      orders: [{ order_id: '21', symbol: 'NQZ6', side: 'Sell', type: 'Stop', qty: 1, price: null, stop_price: 30885, owner: null }] }),
    acct('live099', 'FAKELIVE099', 'live', {
      positions: [{ symbol: 'ESZ6', net: -1, avg_price: 6500, root: 'ES', point_value: 50 }] })],
  bot: { date: '2026-09-22', strategies: {
    nq930: { symbol: 'NQ', kind: 'straddle', enabled: true, shadow: false, book: { sim041: 1 },
      timer: { stage: 'done', gate: true, adx: 23.44, anchor: 30900 }, day_status: 'placed',
      accounts: { sim041: { status: 'placed', qty: 10, upper: 30910, lower: 30890, entry_side: null, sl: null, tp: null, pnl: null } } },
    nq10am: { symbol: 'NQ', kind: 'bars', enabled: true, shadow: true, book: {}, timer: null, day_status: 'idle', accounts: {} },
    ym930: { symbol: 'YM', kind: 'straddle', enabled: false, shadow: false, book: {}, timer: null, day_status: 'idle', accounts: {} } } },
};
const TICKED = { ticked: ['sim041', 'sim047'], oneClick: false, qty: 2, slTicks: 0, tpTicks: 0 };

test('prefs: defaults, clamps, de-duplicated ticks, garbage in -> defaults', () => {
  const dflt = { ticked: [], oneClick: false, qty: 1, slTicks: 0, tpTicks: 0 };
  assert.deepEqual(T.parsePrefs(null), dflt);
  assert.deepEqual(T.parsePrefs('garbage'), dflt);
  assert.deepEqual(T.parsePrefs('[1]'), dflt);
  assert.deepEqual(T.parsePrefs(JSON.stringify({ ticked: ['a', 'a', 5, ''], oneClick: true, qty: 3.6, slTicks: -2, tpTicks: '8' })),
    { ticked: ['a'], oneClick: true, qty: 4, slTicks: 0, tpTicks: 8 });
  assert.equal(T.prefsText({ qty: 0 }), JSON.stringify({ ticked: [], oneClick: false, qty: 1, slTicks: 0, tpTicks: 0 }));
});

test('names: short account, contract root', () => {
  assert.equal(T.short({ id: 'x', label: 'SIM0000047' }), '…047');
  assert.equal(T.short({ id: 'ab' }), 'ab');
  assert.deepEqual(['NQZ6', 'MNQH27', 'NQ', '6EZ6', 'ZN', 'ZNZ6', null].map(T.rootOf), ['NQ', 'MNQ', 'NQ', '6E', 'ZN', 'ZN', '']);
});

test('Limit or Stop from the clicked price (TradingView); AT the touch is marketable (re-review Minor 1)', () => {
  const q = { bid: 30900, ask: 30900.25, last: 30900.25 };
  assert.equal(T.inferType('Buy', 30901, q), 'Stop');
  assert.equal(T.inferType('Buy', 30900.25, q), 'Stop');    // AT the ask: marketable, not passive (>= )
  assert.equal(T.inferType('Buy', 30900, q), 'Limit');      // strictly below the ask: still passive
  assert.equal(T.inferType('Sell', 30899.75, q), 'Stop');
  assert.equal(T.inferType('Sell', 30900, q), 'Stop');      // AT the bid: marketable, not passive (<=)
  assert.equal(T.inferType('Sell', 30900.25, q), 'Limit');  // strictly above the bid: still passive
  assert.equal(T.inferType('Buy', 30901, null), null);
  assert.equal(T.inferType('Buy', 30902, { last: 30902 }), 'Stop');    // no ask: the last trade, AT it is marketable
  assert.equal(T.inferType('Buy', 30901, { last: 30902 }), 'Limit');   // no ask: the last trade, below it is passive
  assert.equal(T.menuText('Buy', 2, 30900, 'Limit', 0.25), 'Buy 2 @ 30,900.00 Limit');
});

test('brackets from ticks (0 = off) and the order body', () => {
  const p = { ...TICKED, slTicks: 20, tpTicks: 40 };
  assert.deepEqual(T.bracket('Buy', 30900, p, 0.25), { sl: 30895, tp: 30910 });
  assert.deepEqual(T.bracket('Sell', 30900, p, 0.25), { sl: 30905, tp: 30890 });
  assert.deepEqual(T.bracket('Buy', 30900, TICKED, 0.25), { sl: null, tp: null });
  assert.deepEqual(T.orderBody({ clientId: 'c1', accounts: ['a'], root: 'NQ', side: 'Buy', qty: 1, type: 'Market', price: 1, sl: 2 }),
    { client_id: 'c1', accounts: ['a'], root: 'NQ', side: 'Buy', qty: 1, type: 'Market', sl_price: 2 });
  assert.deepEqual(T.orderBody({ clientId: 'c1', accounts: ['a'], root: 'NQ', side: 'Sell', qty: 1, type: 'Limit', price: 5 }),
    { client_id: 'c1', accounts: ['a'], root: 'NQ', side: 'Sell', qty: 1, type: 'Limit', price: 5 });
  const a = T.clientId(), b = T.clientId();
  assert.notEqual(a, b);
  assert.ok(a.length >= 1 && a.length <= 64);
});

test('trade mode (per chart): the chart\'s switch, its accounts, then the desk\'s rules', () => {
  const ON = { on: true, accounts: ['sim041', 'sim047'] };
  assert.deepEqual(T.tradeMode({ state: STATE }, { on: false, accounts: ['sim041'] }),
    { mode: 'off', reason: 'Trading is off on this chart', accounts: [] });
  assert.deepEqual(T.tradeMode({ state: STATE }, undefined), { mode: 'off', reason: 'Trading is off on this chart', accounts: [] });
  assert.deepEqual(T.tradeMode({ state: STATE }, { on: 'yes', accounts: ['sim041'] }).mode, 'off');   // only a real true turns it on
  assert.deepEqual(T.tradeMode({ state: STATE }, { on: true, accounts: [] }),
    { mode: 'none', reason: 'Pick accounts for this chart in the Trade menu', accounts: [] });
  assert.deepEqual(T.tradeMode({ state: null, down: 'desk unreachable' }, ON), { mode: 'down', reason: 'desk unreachable', accounts: [] });
  assert.equal(T.tradeMode({ state: { ...STATE, enabled: false } }, ON).mode, 'off');
  assert.equal(T.tradeMode({ state: { ...STATE, enabled: false } }, ON).reason, 'Chart trading is off on the desk');
  const odd = { ...STATE, accounts: STATE.accounts.map((a) => ({ ...a, tradable: false })) };
  assert.deepEqual(T.tradeMode({ state: odd }, ON), { mode: 'none', reason: 'No ticked account can trade right now', accounts: [] });
  assert.deepEqual(T.tradeMode({ state: STATE }, ON), { mode: 'on', reason: '', accounts: ['sim041', 'sim047'] });
  // only THIS chart's accounts: another account the desk knows is never added
  assert.deepEqual(T.tradeMode({ state: STATE }, { on: true, accounts: ['sim047'] }), { mode: 'on', reason: '', accounts: ['sim047'] });
  assert.deepEqual(T.tradeMode({ state: STATE }, { on: true, accounts: ['ghost'] }).mode, 'none');
  // the desk-level gate on its own (the Trade menu's status line)
  assert.equal(T.deskGate({ state: STATE }), null);
  assert.deepEqual(T.deskGate({ state: null, down: 'x' }), { mode: 'down', reason: 'x', accounts: [] });
  assert.equal(T.deskGate({ state: { ...STATE, enabled: false } }).mode, 'off');
});

test('armedMode: an unarmed LIVE account drops out of a chart\'s mode; none left -> not on', () => {
  const m = { mode: 'on', reason: '', accounts: ['sim041', 'live099'] };
  assert.deepEqual(T.armedMode(m, STATE, new Set()), { mode: 'on', reason: '', accounts: ['sim041'] });
  assert.deepEqual(T.armedMode(m, STATE, new Set(['live099'])), m);
  assert.deepEqual(T.armedMode({ mode: 'on', reason: '', accounts: ['live099'] }, STATE, new Set()),
    { mode: 'none', reason: 'Arm the LIVE account for this chart in the Trade menu', accounts: [] });
  const off = { mode: 'off', reason: 'Trading is off on this chart', accounts: [] };
  assert.equal(T.armedMode(off, STATE, new Set()), off);
});

test('cellTrade: sanitised {on, accounts}; at most 20 ids of 1-64 characters, de-duplicated', () => {
  assert.deepEqual(T.cellTrade(undefined), { on: false, accounts: [] });
  assert.deepEqual(T.cellTrade(null), { on: false, accounts: [] });
  assert.deepEqual(T.cellTrade('on'), { on: false, accounts: [] });
  assert.deepEqual(T.cellTrade([1]), { on: false, accounts: [] });
  assert.deepEqual(T.cellTrade({ on: true, accounts: ['a', 'a', 5, '', null, 'x'.repeat(65), 'x'.repeat(64), 'b'] }),
    { on: true, accounts: ['a', 'x'.repeat(64), 'b'] });
  assert.deepEqual(T.cellTrade({ on: 1, accounts: 'sim041' }), { on: false, accounts: [] });
  const many = Array.from({ length: 25 }, (_, i) => `a${i}`);
  assert.deepEqual(T.cellTrade({ on: true, accounts: many }).accounts, many.slice(0, 20));
  const src = { on: true, accounts: ['a'] }, out = T.cellTrade(src);
  out.accounts.push('b');
  assert.deepEqual(src.accounts, ['a']);   // a copy, never the caller's own array
});

test('loadedTrade: a layout / template load keeps the accounts and ALWAYS forces Trading off', () => {
  assert.deepEqual(T.loadedTrade({ on: true, accounts: ['sim041', 'sim047'] }), { on: false, accounts: ['sim041', 'sim047'] });
  assert.deepEqual(T.loadedTrade({ accounts: ['sim041'] }), { on: false, accounts: ['sim041'] });
  assert.deepEqual(T.loadedTrade(undefined), { on: false, accounts: [] });
  assert.deepEqual(T.loadedTrade({ on: true, accounts: [7, ''] }), { on: false, accounts: [] });
});

test('migrateTicked: the old global ticked list goes to the selected chart only, Trading off', () => {
  assert.deepEqual(T.migrateTicked(undefined, ['sim041', 'sim047']), { on: false, accounts: ['sim041', 'sim047'] });
  assert.deepEqual(T.migrateTicked({ root: 'NQ', spec: 'time:60' }, ['sim041']), { on: false, accounts: ['sim041'] });
  assert.equal(T.migrateTicked({ root: 'NQ', trade: { accounts: [] } }, ['sim041']), null);   // already has a config
  assert.equal(T.migrateTicked({ root: 'NQ', trade: null }, ['sim041']), null);                // the key is there: not an old cell
  assert.equal(T.migrateTicked(undefined, []), null);
  assert.equal(T.migrateTicked(undefined, undefined), null);
  assert.equal(T.migrateTicked(undefined, [5, '']), null);   // nothing valid to move
});

test('layout bits: saves write trade.accounts and algo (never `on`); algo sanitised; symbol change', () => {
  assert.deepEqual(T.tradeBits({ root: 'NQ', trade: { on: true, accounts: ['sim041'] }, algo: 'nq930' }),
    { trade: { accounts: ['sim041'] }, algo: 'nq930' });
  assert.deepEqual(T.tradeBits({ root: 'NQ' }), { trade: { accounts: [] }, algo: null });
  assert.equal(T.cellAlgo('nq930'), 'nq930');
  assert.equal(T.cellAlgo(''), null);
  assert.equal(T.cellAlgo('x'.repeat(65)), null);
  assert.equal(T.cellAlgo(7), null);
  assert.equal(T.cellAlgo(undefined), null);
  const strats = STATE.bot.strategies;
  assert.equal(T.algoForRoot('nq930', 'NQ', strats), 'nq930');   // still NQ: kept
  assert.equal(T.algoForRoot('nq930', 'ES', strats), null);      // no longer matches: cleared
  assert.equal(T.algoForRoot('ym930', 'YM', strats), 'ym930');
  // fix round 1: only a CONFIRMED mismatch clears; an algo the desk can't speak to (not answered yet, not listed,
  // no symbol) is kept
  assert.equal(T.algoForRoot('gone', 'NQ', strats), 'gone');     // not listed: kept
  assert.equal(T.algoForRoot('nq930', 'NQ', null), 'nq930');     // no desk state yet: kept
  assert.equal(T.algoForRoot('nq930', 'ES', null), 'nq930');     // no desk state yet: kept, even for another symbol
  assert.equal(T.algoForRoot('odd', 'NQ', { odd: { kind: 'bars' } }), 'odd');   // listed with no symbol: kept
  assert.equal(T.algoForRoot('nq930', 'YM', strats), null);      // the desk confirms NQ, the chart is YM: cleared
  assert.equal(T.algoForRoot(null, 'NQ', strats), null);
  assert.equal(T.algoForRoot('', 'NQ', null), null);             // not a valid algo at all
});

test('templateTrade: a stored template\'s trade / algo, loaded Trading-off; absent keys stay absent', () => {
  assert.deepEqual(T.templateTrade({ settings: {}, trade: { on: true, accounts: ['sim041'] }, algo: 'nq930' }),
    { trade: { on: false, accounts: ['sim041'] }, algo: 'nq930' });
  assert.deepEqual(T.templateTrade({ settings: {} }), {});
  assert.deepEqual(T.templateTrade({ algo: null }), { algo: null });
  assert.deepEqual(T.templateTrade(null), {});
});

test('accountChips: the chart\'s accounts as "…047 DEMO" chips, dimmed when not in the live set', () => {
  assert.deepEqual(T.accountChips(STATE, ['sim047', 'live099', 'ghost'], ['sim047']), [
    { id: 'sim047', who: '…047', env: 'DEMO', live: false, active: true },
    { id: 'live099', who: '…099', env: 'LIVE', live: true, active: false },
    { id: 'ghost', who: '…ost', env: '', live: false, active: false }]);
  assert.deepEqual(T.accountChips(null, ['sim041'], []), [{ id: 'sim041', who: '…041', env: '', live: false, active: false }]);
});

test('acctTick (fix round 1): a chart\'s LIVE account not armed this session shows ticked-but-not-armed', () => {
  const live = STATE.accounts[2], demo = STATE.accounts[0];
  assert.equal(T.acctTick(live, ['live099'], new Set()), 'unarmed');
  assert.equal(T.acctTick(live, ['live099'], new Set(['live099'])), 'ticked');
  assert.equal(T.acctTick(live, [], new Set(['live099'])), 'off');
  assert.equal(T.acctTick(demo, ['sim041'], new Set()), 'ticked');
  assert.equal(T.acctTick(demo, [], new Set()), 'off');
  assert.equal(T.acctTick(live, ['live099'], ['live099']), 'ticked');   // an array of armed ids works too
});

test('hiddenCellsOff (fix round 1): charts beyond the visible grid get Trading switched off, accounts kept', () => {
  const cells = [{ trade: { on: true, accounts: ['a'] } }, { trade: { on: true, accounts: ['b'] } }, { root: 'NQ' },
    { trade: { on: true, accounts: ['c'] }, algo: 'nq930' }];
  T.hiddenCellsOff(cells, 1);
  assert.deepEqual(cells[0].trade, { on: true, accounts: ['a'] });   // visible: untouched
  assert.deepEqual(cells[1].trade, { on: false, accounts: ['b'] });
  assert.deepEqual(cells[2].trade, { on: false, accounts: [] });
  assert.deepEqual(cells[3], { trade: { on: false, accounts: ['c'] }, algo: 'nq930' });
  assert.doesNotThrow(() => T.hiddenCellsOff(null, 0));
});

test('legsWithin: a line may be moved / closed only when every leg\'s account is one of the chart\'s', () => {
  const g = { legs: [{ account: 'sim041' }, { account: 'sim047' }] };
  assert.equal(T.legsWithin(g, ['sim041', 'sim047']), true);
  assert.equal(T.legsWithin(g, ['sim041']), false);
  assert.equal(T.legsWithin({ legs: [] }, ['sim041']), false);
  assert.equal(T.legsWithin(null, ['sim041']), false);
});

test('quote view: prices, spread in ticks, stale after 30 s', () => {
  const q = { bid: 30900, ask: 30900.5, last: 30900.5, ts_ms: 1000 };
  assert.deepEqual(T.quoteView(q, 0.25, 2000), { bid: '30,900.00', ask: '30,900.50', spread: '2', stale: false, age: 1000 });
  assert.equal(T.quoteView(q, 0.25, 32000).stale, true);
  assert.deepEqual(T.quoteView(null, 0.25, 0), { bid: '—', ask: '—', spread: '', stale: true, age: null });
});

test('money: signed dollars with a true minus, RR 1:X', () => {
  assert.deepEqual([450, -1212.5, 0, null].map(T.usd), ['+$450', `${M}$1,212.50`, '$0', null]);
  assert.deepEqual([450, -3, null].map(T.money), ['$450', `${M}$3`, '—']);
  assert.equal(T.pnl(30900, 30910, 1, 2, 20), 400);
  assert.equal(T.pnl(30900, 30910, -1, 1, 20), -200);
  assert.equal(T.pnl(30900, 30910, 1, 1, null), null);
  assert.equal(T.rrText(15, 30), '1:2');
  assert.equal(T.rrText(20, 30), '1:1.5');
  assert.equal(T.rrText(0, 30), null);
});

test('lines: merged positions, SL/TP legs with dollars, plain orders, bots\' orders left out; editable = the chart\'s accounts', () => {
  const EDIT = ['sim041', 'sim047'];
  const lines = T.linesFor(STATE, 'NQ', EDIT);
  assert.deepEqual(lines.map((g) => g.kind), ['position', 'sl', 'tp', 'order']);
  assert.deepEqual(lines.map((g) => g.editable), [true, true, true, true]);
  assert.deepEqual(lines.map((g) => T.lineText(g, 30910)),
    ['LONG 3 · +$600 · 2 accts', `SL 3 · ${M}$900 · 2 accts`, 'TP 2 · +$1,200 · …041', 'BUY LMT 1 · …041']);
  assert.equal(T.lineText(lines[0], null), 'LONG 3 · 2 accts');
  assert.deepEqual(lines[1].legs.map((l) => [l.account, l.order_id]), [['sim041', '11'], ['sim047', '21']]);
  assert.deepEqual(lines.map((g) => T.lineColor(g, P)), [P.up, P.down, P.up, P.accent]);
  assert.equal(T.lineText(T.withPrice(lines[1], 30880), 30910), `SL 3 · ${M}$1,200 · 2 accts`);
  assert.deepEqual(T.linesFor(null, 'NQ', EDIT), []);
  assert.deepEqual(T.lineLabel(lines[3]), 'BUY LMT 1');
  assert.equal(T.withPrice(lines[1], 1).editable, true);
});

test('lines on a chart with Trading off: every account\'s lines, all view only', () => {
  const lines = T.linesFor(STATE, 'NQ', []);
  assert.deepEqual(lines.map((g) => g.editable), [false, false, false, false]);
  assert.deepEqual(lines.map((g) => T.lineText(g, 30910)),
    ['LONG 3 · +$600 · 2 accts · view only', `SL 3 · ${M}$900 · 2 accts · view only`, 'TP 2 · +$1,200 · …041 · view only',
      'BUY LMT 1 · …041 · view only']);
  assert.deepEqual(T.linesFor(STATE, 'NQ', undefined).map((g) => g.editable), [false, false, false, false]);
  assert.deepEqual(T.linesFor(STATE, 'ES', []).map((g) => T.lineText(g, 6490)), ['SHORT 1 · +$500 · …099 · view only']);
});

test('lines on a chart trading some accounts: others\' lines stay view only, never merged into an editable one', () => {
  const lines = T.linesFor(STATE, 'NQ', ['sim047']);
  const byKey = (k, e) => lines.find((g) => g.kind === k && g.editable === e);
  assert.deepEqual(byKey('sl', true).legs.map((l) => l.account), ['sim047']);
  assert.deepEqual(byKey('sl', false).legs.map((l) => l.account), ['sim041']);
  assert.notEqual(byKey('sl', true).key, byKey('sl', false).key);
  assert.equal(T.lineText(byKey('sl', true), 30910), `SL 1 · ${M}$300 · …047`);
  assert.equal(T.lineText(byKey('sl', false), 30910), `SL 2 · ${M}$600 · …041 · view only`);
  for (const g of lines) if (g.editable) assert.ok(g.legs.every((l) => l.account === 'sim047'));
  // a Set works the same as an array
  assert.deepEqual(T.linesFor(STATE, 'NQ', new Set(['sim047'])).map((g) => g.key), lines.map((g) => g.key));
});

test('confirm: title, bracket dollars and RR, accounts, LIVE flag', () => {
  const b = T.orderBody({ clientId: 'c', accounts: ['sim041', 'sim047'], root: 'NQ', side: 'Buy', qty: 2, type: 'Limit', price: 30900, sl: 30885, tp: 30930 });
  assert.deepEqual(T.confirmOrder(b, STATE, null, 20, 0.25), {
    title: 'Buy 2 NQ Limit @ 30,900.00',
    accounts: [{ id: 'sim041', label: 'SIM0000041', env: 'demo' }, { id: 'sim047', label: 'SIM0000047', env: 'demo' }],
    bracket: `SL 30,885.00 ${M}$600 · TP 30,930.00 +$1,200 · RR 1:2`, each: 'each of 2 accounts', live: false, warn: '' });
  const m = T.orderBody({ clientId: 'c', accounts: ['live099'], root: 'NQ', side: 'Sell', qty: 1, type: 'Market' });
  const c = T.confirmOrder(m, STATE, { last: 30910 }, 20, 0.25);
  assert.equal(c.title, 'Sell 1 NQ at market');
  assert.equal(c.live, true);
  assert.equal(c.bracket, '');
  const sl = T.linesFor(STATE, 'NQ', ['sim041', 'sim047'])[1];
  assert.equal(T.actionTitle('modify', { root: 'NQ', line: sl, from: 30885, to: 30880 }, 0.25), 'Move SL 3 30,885.00 → 30,880.00');
  assert.equal(T.actionTitle('cancel', { root: 'NQ', line: sl }, 0.25), 'Cancel SL 3 @ 30,885.00 · 2 accts');
  assert.equal(T.actionTitle('reverse', { root: 'NQ' }, 0.25), 'Reverse NQ');
  assert.equal(T.actionTitle('cancel-symbol', { root: 'NQ' }, 0.25), 'Cancel all NQ orders');
  assert.equal(T.actionTitle('flatten', { root: 'NQ', line: T.linesFor(STATE, 'NQ', ['sim041', 'sim047'])[0] }, 0.25), 'Flatten NQ · 2 accts');
});

test('toasts: one per account from the desk, the proxy detail otherwise; fills', () => {
  const data = { results: { sim041: { ok: true, order_id: '5', error: null },
    sim047: { ok: false, order_id: null, error: 'chart trading is off — switch it on on the desk page', refused: true } } };
  assert.deepEqual(T.resultToasts('order', 200, data, STATE), [
    { tone: 'ok', text: '…041 · order accepted' },
    { tone: 'err', text: '…047 · chart trading is off — switch it on on the desk page' }]);
  assert.deepEqual(T.resultToasts('flatten', 504, { detail: 'no answer from the desk in 20 s — check the Orders tab before trying again' }, STATE),
    [{ tone: 'err', text: 'no answer from the desk in 20 s — check the Orders tab before trying again' }]);
  assert.deepEqual(T.resultToasts('order', 0, null, STATE), [{ tone: 'err', text: 'desk error (HTTP 0)' }]);
  assert.equal(T.fillText({ account: 'sim041', fill: { side: 'Buy', qty: 2, price: 30910.25 } }, STATE, 0.25), 'Filled 2 @ 30,910.25 · …041');
});

test('execution markers: the chart\'s accounts, manual fills only, at the fill price', () => {
  assert.deepEqual(T.fillMarkers(STATE, 'NQ', [], P), []);
  assert.deepEqual(T.fillMarkers(STATE, 'NQ', ['sim041'], P), [{ id: 'fsim041:1', ms: Date.parse('2026-09-22T13:31:12.000Z'), price: 30900,
    position: 'atPriceBottom', shape: 'arrowUp', color: P.accent, text: '' }]);
});

/* ---- the algo on a chart (2026-09-27 plan, Task 3) ---- */
const NQ930 = STATE.bot.strategies.nq930;
const botState = (patch = {}, acctPatch = null) => {
  const st = structuredClone(STATE);
  Object.assign(st.bot.strategies.nq930, patch);
  if (acctPatch) st.bot.strategies.nq930.accounts = acctPatch;
  return st;
};

test('algo names: the desk strategy, its booked accounts, the choices for a chart\'s root', () => {
  assert.equal(T.algoName('nq930'), 'NQ 9:30 Straddle');
  assert.equal(T.algoName('mystery'), 'mystery');
  assert.equal(T.algoLabel('nq930', NQ930, STATE), 'NQ 9:30 Straddle · …041');
  assert.equal(T.algoLabel('nq930', { ...NQ930, book: { sim041: 1, sim047: 2 } }, STATE), 'NQ 9:30 Straddle · …041, …047');
  assert.equal(T.algoLabel('nq930', { ...NQ930, book: { acct123456: 1 } }, STATE), 'NQ 9:30 Straddle · …456');   // not listed: its id
  assert.equal(T.algoLabel('nq10am', STATE.bot.strategies.nq10am, STATE), 'NQ 10:00 Continuation');         // no book: the name alone
  assert.deepEqual(T.algoChoices(STATE, 'NQ'), [{ value: '', text: 'None' },
    { value: 'nq930', text: 'NQ 9:30 Straddle · …041' }, { value: 'nq10am', text: 'NQ 10:00 Continuation' }]);
  assert.deepEqual(T.algoChoices(STATE, 'YM'), [{ value: '', text: 'None' }, { value: 'ym930', text: 'YM 9:30 Straddle' }]);
  assert.deepEqual(T.algoChoices(STATE, 'ES'), [{ value: '', text: 'None' }]);
  // the chart's current algo stays pickable while the desk hasn't listed it (no state yet)
  assert.deepEqual(T.algoChoices(null, 'NQ', 'nq930'), [{ value: '', text: 'None' }, { value: 'nq930', text: 'NQ 9:30 Straddle' }]);
  assert.deepEqual(T.algoChoices(STATE, 'NQ', 'nq930').length, 3);   // listed already: not twice
  assert.deepEqual(T.algoChoices(STATE, 'ES', 'nq930'), [{ value: '', text: 'None' }]);   // the desk CONFIRMS it trades NQ: not offered on ES
  assert.deepEqual(T.algoChoices(STATE, 'NQ', 'gone'), [{ value: '', text: 'None' },
    { value: 'nq930', text: 'NQ 9:30 Straddle · …041' }, { value: 'nq10am', text: 'NQ 10:00 Continuation' }, { value: 'gone', text: 'gone' }]);   // not listed: kept
});

test('algo badge: the state pill from the bot view', () => {
  const pill = (patch, accts) => T.botPill(botState(patch, accts).bot.strategies.nq930);
  assert.deepEqual([pill({}).state, pill({}).text, pill({}).tone], ['armed', 'armed', 'live']);   // placed: entries working
  assert.equal(pill({ day_status: 'placing' }).state, 'placing');
  assert.equal(pill({ day_status: 'live' }).state, 'in trade');
  assert.equal(pill({ day_status: 'done' }).state, 'done');
  assert.equal(pill({ day_status: 'idle', timer: { stage: 'idle', gate: null } }).state, 'idle');
  assert.equal(pill({ day_status: 'idle', timer: { stage: 'gated', gate: true, adx: 30 } }).state, 'idle');
  assert.equal(pill({ day_status: 'idle', timer: { stage: 'staged', gate: true, adx: 30 } }).state, 'armed');
  const chop = pill({ day_status: 'idle', timer: { stage: 'skipped', gate: false, adx: 14.24 } });
  assert.deepEqual([chop.state, chop.tip], ['skipped', 'Skipped today — CHOP ADX 14.2']);
  assert.equal(pill({ day_status: 'idle', timer: { stage: 'missed' } }).state, 'skipped');
  assert.equal(pill({ day_status: 'idle', timer: null }).state, 'idle');
  assert.equal(pill({ day_status: 'done', killed: true }).state, 'killed');
  assert.equal(pill({ day_status: 'idle', timer: { stage: 'skipped', killed: true } }).state, 'killed');
  assert.equal(pill({ shadow: true, day_status: 'idle' }).state, 'shadow');
  assert.equal(pill({ enabled: false }).state, 'off');
  assert.deepEqual([pill({ day_status: 'error' }).state, pill({ day_status: 'error' }).tone], ['error', 'err']);
  // a killed run the desk could not attribute: CHECK IT, amber, whatever else is going on
  const ck = pill({ killed: true, day_status: 'live' }, { sim041: { status: 'live', qty: 1, check_it: true } });
  assert.deepEqual([ck.state, ck.text, ck.tone], ['check it', 'CHECK IT', 'warn']);
  assert.match(ck.tip, /stops were left working/);
  assert.match(ck.tip, /verify the position/);
});

test('algo badge: today\'s P&L -- realized, plus an open trade at the last price', () => {
  const s = (accounts) => ({ ...NQ930, accounts });
  assert.equal(T.botToday(s({}), 30900, 20), null);                                          // nothing yet
  assert.equal(T.botToday(s({ a: { status: 'placed', qty: 1, pnl: null } }), 30900, 20), null);
  assert.equal(T.botToday(s({ a: { status: 'done', pnl: 296 }, b: { status: 'done', pnl: -104 } }), null, null), 192);
  assert.equal(T.botToday(s({ a: { status: 'live', entry_side: 'Sell', entry_fill: 30910, entry_qty: 2, qty: 2, pnl: null } }), 30900, 20), 400);
  assert.equal(T.botToday(s({ a: { status: 'live', entry_side: 'Buy', entry_fill: 30910, entry_qty: 1, pnl: null } }), null, 20), null);   // no price: unknown
});

test('algo overlay: only for the chart\'s own algo on its own root; BOT lines are read-only', () => {
  assert.equal(T.algoOverlay(STATE, null, 'NQ', 0.25, P, null), null);        // no algo: nothing, even on the bot's root
  assert.equal(T.algoOverlay(STATE, 'nq930', 'ES', 0.25, P, null), null);     // another root
  assert.equal(T.algoOverlay(STATE, 'gone', 'NQ', 0.25, P, null), null);      // not on the desk
  assert.equal(T.algoOverlay(null, 'nq930', 'NQ', 0.25, P, null), null);      // no desk state
  const o = T.algoOverlay(STATE, 'nq930', 'NQ', 0.25, P, 30900, 20);
  assert.equal(o.name, 'NQ 9:30 Straddle');
  assert.equal(o.pill.state, 'armed');
  assert.deepEqual(o.accounts, ['sim041']);
  // the Sell entry is a real working order (owner nq930); the Buy entry comes from the bot view (no order listed)
  assert.deepEqual(o.lines.map((l) => [l.kind, l.text]), [['entry', 'BOT BUY STP 10 @ 30,910.00'], ['entry', 'BOT SELL STP 1 @ 30,890.00']]);
  assert.ok(o.lines.every((l) => l.editable === false && l.bot === true && l.key.startsWith('bot|nq930|')));
  // the manual lines never include the bot's order
  assert.ok(!T.linesFor(STATE, 'NQ', ['sim041']).some((g) => g.legs.some((l) => l.order_id === '14')));
  const live = botState({ day_status: 'live' }, { sim041: { status: 'live', qty: 10, entry_side: 'Buy', entry_fill: 30910, entry_qty: 10, sl: 30905, tp: 30925, pnl: null } });
  live.accounts[0].orders = live.accounts[0].orders.filter((x) => !x.owner);
  const lo = T.algoOverlay(live, 'nq930', 'NQ', 0.25, P, 30912, 20);
  assert.deepEqual(lo.lines.map((l) => l.text), ['BOT TP 10 @ 30,925.00', 'BOT SL 10 @ 30,905.00']);
  assert.deepEqual(lo.lines.map((l) => l.color), [P.up, P.down]);
  assert.equal(lo.pnl, 400);
  // owner orders once the position is on: the opposite side's Stop is the SL, its Limit the TP
  live.accounts[0].orders.push({ order_id: '31', symbol: 'NQZ6', side: 'Sell', type: 'Stop', qty: 10, price: null, stop_price: 30905, owner: 'nq930' },
    { order_id: '32', symbol: 'NQZ6', side: 'Sell', type: 'Limit', qty: 10, price: 30925, stop_price: null, owner: 'nq930' });
  assert.deepEqual(T.algoOverlay(live, 'nq930', 'NQ', 0.25, P, 30912, 20).lines.map((l) => l.text), ['BOT TP 10 @ 30,925.00', 'BOT SL 10 @ 30,905.00']);
  // fix round 1, M6: the view's level and the working order disagree (a bracket move in flight): the ORDER only, no
  // phantom second SL/TP from the view
  const moved = structuredClone(live);
  moved.accounts[0].orders = moved.accounts[0].orders.map((o) => (o.order_id === '31' ? { ...o, stop_price: 30906.25 } : o.order_id === '32' ? { ...o, price: 30926 } : o));
  assert.deepEqual(T.algoOverlay(moved, 'nq930', 'NQ', 0.25, P, 30912, 20).lines.map((l) => l.text), ['BOT TP 10 @ 30,926.00', 'BOT SL 10 @ 30,906.25']);
  // an entry order a float hair off the view's trigger is still that entry (tick epsilon), not a second line
  const hair = botState();
  hair.accounts[0].orders = [{ order_id: '41', symbol: 'NQZ6', side: 'Buy', type: 'Stop', qty: 10, price: null, stop_price: 30910.0000001, owner: 'nq930' },
    { order_id: '42', symbol: 'NQZ6', side: 'Sell', type: 'Stop', qty: 10, price: null, stop_price: 30890, owner: 'nq930' }];
  assert.deepEqual(T.algoOverlay(hair, 'nq930', 'NQ', 0.25, P, 30900, 20).lines.map((l) => [l.kind, l.side, l.qty]), [['entry', 'Buy', 10], ['entry', 'Sell', 10]]);
  // today's fill markers: the bot's own fills only, the entry an arrow, the exit a circle with the P&L
  const done = botState({ day_status: 'done' }, { sim041: { status: 'done', qty: 1, entry_side: 'Buy', entry_fill: 30910, pnl: 296 } });
  done.accounts[0].fills.push({ id: 3, order_id: '7', symbol: 'NQZ6', side: 'Sell', qty: 1, price: 30925, time: '2026-09-22T13:44:10.000Z', owner: 'nq930' });
  const mk = T.algoOverlay(done, 'nq930', 'NQ', 0.25, P, 30912, 20).markers;
  assert.deepEqual(mk.map((m) => [m.shape, m.price, m.position, m.text, m.color]),
    [['arrowUp', 30910, 'atPriceBottom', '', P.warn], ['circle', 30925, 'atPriceMiddle', '+$296', P.up]]);
  assert.equal(mk[0].tip, 'Today · …041 · Buy 1 @ 30,910.00');
  assert.deepEqual(T.algoOverlay(done, 'nq930', 'NQ', 0.25, P, 30912, 20).liveAccounts, ['sim041']);   // today's run: drawn live
  assert.deepEqual(T.algoOverlay(STATE, 'nq930', 'NQ', 0.25, P, 30900, 20).liveAccounts, ['sim041']);
  // an order of the bot still working after it is done (a kill that left its stop): still drawn, as its SL
  assert.deepEqual(T.algoOverlay(done, 'nq930', 'NQ', 0.25, P, 30912, 20).lines.map((l) => l.text), ['BOT SL 1 @ 30,890.00']);
  done.accounts[0].orders = done.accounts[0].orders.filter((x) => !x.owner);
  assert.deepEqual(T.algoOverlay(done, 'nq930', 'NQ', 0.25, P, 30912, 20).lines, []);
});

const at = (iso) => Date.parse(iso);
const RUNS = [
  { date: '2026-09-18', account: 'sim041', status: 'traded', legs: [], entry: { side: 'Buy', price: 30100, ts: at('2026-09-18T13:30:01Z') },
    exit: { price: 30115, ts: at('2026-09-18T13:44:10Z'), kind: 'tp' }, pnl_usd: 296 },                       // before the loaded range
  { date: '2026-09-21', account: 'sim047', status: 'traded', legs: [{ side: 'Buy', price: 30120, ts: at('2026-09-21T13:30:00Z') }],
    entry: { side: 'Buy', price: 30120.25, ts: at('2026-09-21T13:30:01Z') }, exit: { price: 30135.25, ts: at('2026-09-21T13:44:10Z'), kind: 'tp' },
    pnl_usd: 2960 },
  { date: '2026-09-22', account: 'sim041', status: 'traded', legs: [], entry: { side: 'Sell', price: 30200, ts: at('2026-09-22T13:30:01Z') },
    exit: { price: 30205, ts: at('2026-09-22T13:33:20Z'), kind: 'sl' } },                                      // no P&L
  { date: '2026-09-23', account: null, status: 'skipped', reason: 'gate_chop', legs: [] },
  { date: '2026-09-24', account: 'sim041', status: 'no_fill', legs: [{ side: 'Buy', price: 30300, ts: at('2026-09-24T13:30:00.088Z') }] },
  { date: '2026-09-25', account: null, status: 'refused', reason: 'bad_spread', legs: [] },
  { date: '2026-09-28', account: 'sim041', status: 'traded', legs: [], entry: { side: 'Buy', price: 30400, ts: at('2026-09-28T13:30:01Z') },
    exit: { price: 30405, ts: at('2026-09-28T13:40:00Z'), kind: 'flat' }, pnl_usd: 96 },                         // today: drawn live when sim041 has live fills
];

test('past runs -> markers: entry arrow + exit circle per traded run, a grey flag for the rest, loaded range only', () => {
  const s = { ...NQ930, book: { sim041: 1, sim047: 10 } };
  const list = T.pastRunMarkers(RUNS, { key: 'nq930', s, state: STATE, tick: 0.25, pv: 20, P,
    from: at('2026-09-20T00:00:00Z'), to: at('2026-09-29T00:00:00Z'), today: '2026-09-28', liveAccounts: ['sim041'] });
  assert.deepEqual(list.map((m) => [m.shape, m.ms, m.price ?? null, m.position]), [
    ['arrowUp', at('2026-09-21T13:30:01Z'), 30120.25, 'atPriceBottom'],
    ['circle', at('2026-09-21T13:44:10Z'), 30135.25, 'atPriceMiddle'],
    ['arrowDown', at('2026-09-22T13:30:01Z'), 30200, 'atPriceTop'],
    ['circle', at('2026-09-22T13:33:20Z'), 30205, 'atPriceMiddle'],
    ['square', at('2026-09-23T13:30:00Z'), null, 'aboveBar'],          // no legs: the 09:30 ET session open
    ['square', at('2026-09-24T13:30:00.088Z'), null, 'aboveBar'],      // placed, never filled: where it placed
    ['square', at('2026-09-25T13:30:00Z'), null, 'aboveBar']]);
  // the qty comes from the P&L (exact); without one it is left out (fix round 1, M2: never today's book size)
  assert.equal(list[0].tip, '2026-09-21 · …047 · Buy 10 @ 30,120.25 → TP 30,135.25 · +$2,960');
  assert.equal(list[1].tip, list[0].tip);
  assert.equal(list[2].tip, '2026-09-22 · …041 · Sell @ 30,200.00 → SL 30,205.00 · P&L unknown');
  assert.deepEqual([list[1].color, list[3].color], [P.up, P.warn]);   // a win green; unknown P&L in the bot colour
  assert.equal(list[4].tip, '2026-09-23 · …041, …047 · Skipped — gate chop');   // no account: every booked account
  assert.equal(list[5].tip, '2026-09-24 · …041 · No fill');
  assert.equal(list[6].tip, '2026-09-25 · …041, …047 · Refused — bad spread');
  assert.ok(list.slice(4).every((m) => m.color === list[4].color && m.color !== P.warn));   // grey
  assert.equal(new Set(list.map((m) => m.id)).size, list.length);
  // a loss is red; a killed run says so; an entry without an exit says so
  const more = T.pastRunMarkers([
    { date: '2026-09-21', account: 'sim041', status: 'killed', legs: [], entry: { side: 'Buy', price: 30100, ts: at('2026-09-21T13:30:01Z') },
      exit: { price: 30090, ts: at('2026-09-21T13:35:00Z'), kind: 'flat' }, pnl_usd: -204 },
    { date: '2026-09-22', account: 'sim041', status: 'error', reason: 'both_filled', legs: [], entry: { side: 'Buy', price: 30100, ts: at('2026-09-22T13:30:01Z') } }],
  { key: 'nq930', s, state: STATE, tick: 0.25, pv: 20, P, from: 0, to: Infinity, today: '2026-09-28' });
  assert.equal(more[0].tip, '2026-09-21 · …041 · Buy 1 @ 30,100.00 → Flat 30,090.00 · −$204 · killed');
  assert.equal(more[1].color, P.down);
  assert.equal(more[2].tip, '2026-09-22 · …041 · Buy @ 30,100.00 · no exit · error — both filled');
  // no point value yet: no qty either
  assert.equal(T.pastRunMarkers([RUNS[1]], { key: 'nq930', s, state: STATE, tick: 0.25, pv: null, P, from: 0, to: Infinity, today: '' })[0].tip,
    '2026-09-21 · …047 · Buy @ 30,120.25 → TP 30,135.25 · +$2,960');
  // today's run: left to the live overlay only for an account that has live bot fills today (report concern 5)
  const today = (live) => T.pastRunMarkers(RUNS, { key: 'nq930', s, state: STATE, tick: 0.25, pv: 20, P, from: at('2026-09-28T00:00:00Z'), to: Infinity,
    today: '2026-09-28', liveAccounts: live }).length;
  assert.equal(today([]), 2);             // no live fills: today's history row is drawn (entry + exit)
  assert.equal(today(['sim041']), 0);     // the live overlay draws it
  assert.equal(today(['sim047']), 2);     // another account's fills don't cover sim041's run
  assert.equal(more.length, 3);
  assert.deepEqual(T.pastRunMarkers(null, { key: 'nq930', s, state: STATE, tick: 0.25, pv: 20, P, from: 0, to: Infinity, today: '' }), []);
});

const PAPER_STRATS = [{ id: 'gc_nfpcpi', name: 'GC NFP/CPI (paper)', root: 'GC', params: { offset_pts: 2, sl_pts: 3, tp_pts: 6, qty: 1 } }];

test('paper: the algo key round-trips, and its strategies list becomes an algoForRoot map (2026-09-27 paper plan, Task 2)', () => {
  assert.equal(T.paperKey('gc_nfpcpi'), 'paper:gc_nfpcpi');
  assert.equal(T.isPaperAlgo('paper:gc_nfpcpi'), true);
  assert.equal(T.isPaperAlgo('nq930'), false);
  assert.equal(T.isPaperAlgo('paper:'), false);   // the prefix alone names nothing
  assert.equal(T.isPaperAlgo(null), false);
  assert.equal(T.paperStrategyId('paper:gc_nfpcpi'), 'gc_nfpcpi');
  assert.equal(T.paperStrategyId('nq930'), null);
  assert.deepEqual(T.paperStrategiesMap(PAPER_STRATS), { 'paper:gc_nfpcpi': { symbol: 'GC' } });
  assert.deepEqual(T.paperStrategiesMap([{ id: '', root: 'GC' }, { id: 'x' }, null, 'garbage']), {});
  assert.deepEqual(T.paperStrategiesMap(null), {});
});

test('paper: algoForRoot confirms a paper algo\'s root from the merged map, clearing only on a confirmed mismatch', () => {
  const merged = { ...STATE.bot.strategies, ...T.paperStrategiesMap(PAPER_STRATS) };
  assert.equal(T.algoForRoot('paper:gc_nfpcpi', 'GC', merged), 'paper:gc_nfpcpi');   // confirmed: kept
  assert.equal(T.algoForRoot('paper:gc_nfpcpi', 'NQ', merged), null);                // confirmed mismatch: cleared
  assert.equal(T.algoForRoot('paper:gc_nfpcpi', 'GC', {}), 'paper:gc_nfpcpi');        // not listed yet: kept
  assert.equal(T.algoForRoot('paper:gc_nfpcpi', 'GC', null), 'paper:gc_nfpcpi');      // no state at all: kept
});

test('paper: the Settings dialog\'s Algo choices include the paper strategies for the chart\'s root', () => {
  assert.deepEqual(T.algoChoices(STATE, 'GC', null, PAPER_STRATS), [{ value: '', text: 'None' },
    { value: 'paper:gc_nfpcpi', text: 'GC NFP/CPI (paper)' }]);
  assert.deepEqual(T.algoChoices(STATE, 'NQ', null, PAPER_STRATS), [{ value: '', text: 'None' },
    { value: 'nq930', text: 'NQ 9:30 Straddle · …041' }, { value: 'nq10am', text: 'NQ 10:00 Continuation' }]);   // GC paper: not on NQ
  // the chart's current paper algo stays pickable while the list hasn't loaded yet (null / [])
  assert.deepEqual(T.algoChoices(STATE, 'GC', 'paper:gc_nfpcpi', null), [{ value: '', text: 'None' },
    { value: 'paper:gc_nfpcpi', text: 'GC NFP/CPI (paper)' }]);   // ALGO_NAMES fallback text, not listed twice
  assert.deepEqual(T.algoChoices(STATE, 'GC', 'paper:gc_nfpcpi', PAPER_STRATS).length, 2);   // listed already: not twice
  // the list CONFIRMS it trades GC: not offered as a fallback on another root
  assert.deepEqual(T.algoChoices(STATE, 'NQ', 'paper:gc_nfpcpi', PAPER_STRATS), [{ value: '', text: 'None' },
    { value: 'nq930', text: 'NQ 9:30 Straddle · …041' }, { value: 'nq10am', text: 'NQ 10:00 Continuation' }]);
});

test('paper: the badge state pill from the latest /ws message', () => {
  assert.deepEqual([T.paperPill(null).state, T.paperPill(null).tone], ['waiting', 'idle']);
  assert.deepEqual([T.paperPill({ state: 'waiting' }).state, T.paperPill({ state: 'waiting' }).tone], ['waiting', 'idle']);
  assert.deepEqual([T.paperPill({ state: 'armed' }).state, T.paperPill({ state: 'armed' }).tone], ['armed', 'live']);
  assert.deepEqual([T.paperPill({ state: 'in_trade' }).state, T.paperPill({ state: 'in_trade' }).tone], ['in trade', 'live']);
  assert.deepEqual([T.paperPill({ state: 'done', status: 'traded' }).state, T.paperPill({ state: 'done', status: 'traded' }).tone], ['done', 'idle']);
  // an error tone wins whatever state it arrived with
  assert.deepEqual([T.paperPill({ state: 'done', status: 'error', error: 'boom' }).tone, T.paperPill({ state: 'done', status: 'error', error: 'boom' }).tip], ['err', 'boom']);
  assert.match(T.paperPill({ state: 'done', status: 'no_data' }).tip, /Feed gap/);
  assert.match(T.paperPill({ state: 'done', status: 'calendar_missing' }).tip, /No calendar/);
});

test('paper: today\'s P&L -- the finished run\'s, else the open mark; the label with today\'s event', () => {
  assert.equal(T.paperToday(null), null);
  assert.equal(T.paperToday({ state: 'armed' }), null);
  assert.equal(T.paperToday({ state: 'in_trade', open_pnl_usd: 120.5 }), 120.5);
  assert.equal(T.paperToday({ state: 'done', status: 'traded', pnl_usd: -84 }), -84);
  assert.equal(T.paperToday({ state: 'done', status: 'traded', pnl_usd: 12, open_pnl_usd: 999 }), 12);   // finished wins
  assert.equal(T.paperLabel('GC NFP/CPI (paper)', null), 'GC NFP/CPI (paper)');
  assert.equal(T.paperLabel('GC NFP/CPI (paper)', { event: 'CPI' }), 'GC NFP/CPI (paper) · CPI');
});

test('paper: dashed lines -- both simulated stop entries while armed, SL/TP once in a simulated position, none waiting/done', () => {
  assert.deepEqual(T.paperLines(null, 0.1, P), []);
  assert.deepEqual(T.paperLines({ state: 'waiting', legs: [] }, 0.1, P), []);
  const armed = { state: 'armed', legs: [{ side: 'Buy', price: 3902 }, { side: 'Sell', price: 3898 }] };
  assert.deepEqual(T.paperLines(armed, 0.1, P).map((l) => [l.kind, l.side, l.text, l.editable, l.paper]),
    [['entry', 'Buy', 'PAPER BUY STP @ 3,902.0', false, true], ['entry', 'Sell', 'PAPER SELL STP @ 3,898.0', false, true]]);
  assert.deepEqual(T.paperLines(armed, 0.1, P).map((l) => l.color), [P.accent, P.down]);
  const inTrade = { state: 'in_trade', entry: { side: 'Buy', price: 3902, sl: 3899, tp: 3908 } };
  assert.deepEqual(T.paperLines(inTrade, 0.1, P).map((l) => [l.kind, l.side, l.text]),
    [['tp', 'Sell', 'PAPER TP @ 3,908.0'], ['sl', 'Sell', 'PAPER SL @ 3,899.0']]);
  assert.deepEqual(T.paperLines(inTrade, 0.1, P).map((l) => l.color), [P.up, P.down]);
  assert.deepEqual(T.paperLines({ state: 'done', status: 'traded' }, 0.1, P), []);
  assert.ok(T.paperLines(armed, 0.1, P).every((l) => T.canDrag(l) === true && l.editable === false));   // dashed, but never draggable from a chip since editable is false
});

test('paper: today\'s fill markers -- entry arrow, exit circle with the P&L, tagged PAPER', () => {
  assert.deepEqual(T.paperMarkers(null, 0.1, P), []);
  assert.deepEqual(T.paperMarkers({ state: 'armed' }, 0.1, P), []);
  const live = { date: '2026-09-26', state: 'in_trade', entry: { side: 'Buy', price: 3902, ts: at('2026-09-26T12:30:01Z') } };
  const m1 = T.paperMarkers(live, 0.1, P);
  assert.deepEqual(m1.map((x) => [x.shape, x.price, x.position, x.tip]), [['arrowUp', 3902, 'atPriceBottom', 'PAPER · Buy @ 3,902.0']]);
  assert.equal(m1[0].color, P.warn);
  const done = { ...live, state: 'done', status: 'traded', exit: { price: 3908, ts: at('2026-09-26T12:44:00Z'), kind: 'tp' }, pnl_usd: 600 };
  const m2 = T.paperMarkers(done, 0.1, P);
  assert.deepEqual(m2.map((x) => [x.shape, x.price, x.color, x.text, x.tip]),
    [['arrowUp', 3902, P.warn, '', 'PAPER · Buy @ 3,902.0'], ['circle', 3908, P.up, '+$600', 'PAPER · TP @ 3,908.0 · +$600']]);
  assert.equal(new Set(m2.map((x) => x.id)).size, 2);
  const loss = { ...done, pnl_usd: -300 };
  assert.equal(T.paperMarkers(loss, 0.1, P)[1].color, P.down);
});

test('paper overlay: only for a listed paper algo confirmed on its own root; combines pill, label, lines and markers', () => {
  assert.equal(T.paperOverlay({ strategies: PAPER_STRATS, current: {} }, null, 'GC', 0.1, P), null);            // not a paper algo
  assert.equal(T.paperOverlay({ strategies: PAPER_STRATS, current: {} }, 'nq930', 'GC', 0.1, P), null);         // a desk algo, not paper
  assert.equal(T.paperOverlay({ strategies: [], current: {} }, 'paper:gc_nfpcpi', 'GC', 0.1, P), null);         // not listed yet
  assert.equal(T.paperOverlay({ strategies: PAPER_STRATS, current: {} }, 'paper:gc_nfpcpi', 'NQ', 0.1, P), null);   // another root
  assert.equal(T.paperOverlay(null, 'paper:gc_nfpcpi', 'GC', 0.1, P), null);
  const msg = { strategy: 'gc_nfpcpi', date: '2026-09-26', event: 'CPI', state: 'armed', status: null,
    legs: [{ side: 'Buy', price: 3902 }, { side: 'Sell', price: 3898 }] };
  const o = T.paperOverlay({ strategies: PAPER_STRATS, current: { gc_nfpcpi: msg } }, 'paper:gc_nfpcpi', 'GC', 0.1, P);
  assert.equal(o.name, 'GC NFP/CPI (paper)');
  assert.equal(o.label, 'GC NFP/CPI (paper) · CPI');
  assert.equal(o.event, 'CPI');
  assert.deepEqual(o.pill, T.paperPill(msg));
  assert.equal(o.pnl, null);
  assert.equal(o.lines.length, 2);
  assert.deepEqual(o.markers, []);
  // no message yet at all (a fresh load, before the first /ws push): still shown, waiting
  const o2 = T.paperOverlay({ strategies: PAPER_STRATS, current: {} }, 'paper:gc_nfpcpi', 'GC', 0.1, P);
  assert.equal(o2.pill.state, 'waiting');
  assert.deepEqual(o2.lines, []);
});

const PAPER_RUNS = [
  { date: '2026-09-12', strategy: 'gc_nfpcpi', event: 'NFP', status: 'traded', legs: [],
    entry: { side: 'Buy', price: 3900, ts: at('2026-09-12T12:30:01Z') }, exit: { price: 3906, ts: at('2026-09-12T12:35:00Z'), kind: 'tp' }, pnl_usd: 596 },
  { date: '2026-09-13', strategy: 'gc_nfpcpi', event: 'CPI', status: 'no_fill', legs: [{ side: 'Buy', price: 3910 }, { side: 'Sell', price: 3904 }] },
  { date: '2026-09-14', strategy: 'gc_nfpcpi', event: 'NFP', status: 'no_data', legs: [], error: 'feed gap' },
  { date: '2026-09-15', strategy: 'gc_nfpcpi', event: 'CPI', status: 'calendar_missing', legs: [] },
  { date: '2026-09-26', strategy: 'gc_nfpcpi', event: 'NFP', status: 'traded', legs: [],   // today: left to the live overlay
    entry: { side: 'Sell', price: 3920, ts: at('2026-09-26T12:30:01Z') }, exit: { price: 3914, ts: at('2026-09-26T12:35:00Z'), kind: 'tp' }, pnl_usd: 596 },
];

test('paper: past runs -> markers, account-less; a grey flag at 08:30 ET for a day with no entry; today left to the live overlay', () => {
  const list = T.paperRunMarkers(PAPER_RUNS, { tick: 0.1, P, from: 0, to: Infinity, today: '2026-09-26' });
  assert.deepEqual(list.map((m) => [m.shape, m.ms, m.price ?? null]), [
    ['arrowUp', at('2026-09-12T12:30:01Z'), 3900],
    ['circle', at('2026-09-12T12:35:00Z'), 3906],
    ['square', T.etMs('2026-09-13', '08:30'), null],
    ['square', T.etMs('2026-09-14', '08:30'), null],
    ['square', T.etMs('2026-09-15', '08:30'), null],
  ]);
  assert.equal(list[0].tip, '2026-09-12 · PAPER NFP · Buy @ 3,900.0 → TP 3,906.0 · +$596');
  assert.equal(list[1].tip, list[0].tip);
  assert.equal(list[2].tip, '2026-09-13 · PAPER CPI · No fill');
  assert.equal(list[3].tip, '2026-09-14 · PAPER NFP · No data');
  assert.equal(list[4].tip, '2026-09-15 · PAPER CPI · No calendar');
  assert.deepEqual(list.slice(2).every((m) => m.color === '#9598A1'), true);
  assert.equal(new Set(list.map((m) => m.id)).size, list.length);
  assert.deepEqual(T.paperRunMarkers(null, { tick: 0.1, P, from: 0, to: Infinity, today: '' }), []);
  // range: only markers inside [from, to)
  const narrow = T.paperRunMarkers(PAPER_RUNS, { tick: 0.1, P, from: at('2026-09-13T00:00:00Z'), to: at('2026-09-14T00:00:00Z'), today: '2026-09-26' });
  assert.equal(narrow.length, 1);
});

test('paper: the stats line under the badge, exactly as specified', () => {
  const stats = { paper: { n: 3, wr: 66.7, avg: 203, net: 608 }, backtest: { window: '2021-2024', n: 76, wr: 67.6, avg: 296, net: 22496 } };
  assert.equal(T.paperStatsText(stats), 'Paper 3 · WR 67% · avg +$203 | Backtest 21–24: 76 · WR 68% · avg +$296');
  assert.equal(T.paperStatsText({ paper: { n: 0, wr: null, avg: null, net: 0 }, backtest: null }), 'Paper 0 · WR — · avg —');
  assert.equal(T.paperStatsText({ paper: { n: 1, wr: 0, avg: -50, net: -50 } }), 'Paper 1 · WR 0% · avg −$50');
  assert.equal(T.paperStatsText(null), '');
  assert.equal(T.paperStatsText({}), '');   // no `paper` key at all: nothing to show either
});

test('ET wall-clock to epoch ms (DST both sides), and the nearest marker under the mouse', () => {
  assert.equal(T.etMs('2026-09-24', '09:30'), at('2026-09-24T13:30:00Z'));
  assert.equal(T.etMs('2026-12-01', '09:30'), at('2026-12-01T14:30:00Z'));
  assert.equal(T.etMs('2026-03-09', '09:30'), at('2026-03-09T13:30:00Z'));   // the day after the spring change
  assert.ok(Number.isNaN(T.etMs('garbage', '09:30')));
  const pts = [{ x: 100, y: 50, tip: 'a' }, { x: 108, y: 52, tip: 'b' }, { x: 300, y: 50, tip: 'c' }];
  assert.equal(T.nearestTip(pts, 106, 52, 8), 'b');
  assert.equal(T.nearestTip(pts, 200, 50, 8), null);
  assert.equal(T.nearestTip([], 1, 1, 8), null);
});

test('Kill: the confirm text, and one toast per account -- "check it" is a warning, never a success', () => {
  const s = { ...NQ930, book: { sim047: 1 }, accounts: {} };
  const c = T.killConfirm('nq930', s, STATE);
  assert.equal(c.text, 'Kill NQ 9:30 Straddle — cancel its orders and flatten its NQ position on …047. The desk stays armed for other strategies.');
  assert.equal(c.title, 'Kill NQ 9:30 Straddle');
  assert.equal(c.note, 'Cancel its orders and flatten its NQ position on …047. The desk stays armed for other strategies.');
  assert.deepEqual(c.rows, [{ id: 'sim047', label: 'SIM0000047', env: 'demo' }]);
  assert.deepEqual([c.accounts, c.live], [['sim047'], false]);
  const both = T.killConfirm('nq930', { ...NQ930, book: { sim041: 1, live099: 1 } }, STATE);   // plus an account it acted on today
  assert.deepEqual([both.accounts, both.live], [['sim041', 'live099'], true]);
  assert.match(both.text, /on …041, …099\./);
  // fix round 1, M1: an account the desk does not list is '?', never DEMO
  const unk = T.killConfirm('nq930', { ...NQ930, book: { acct123456: 1 }, accounts: {} }, STATE);
  assert.deepEqual(unk.rows, [{ id: 'acct123456', label: 'acct123456', env: '?' }]);
  // ... and blocks the Kill (fail closed), like an unarmed LIVE account
  assert.equal(T.killBlock(STATE, ['sim041'], new Set()), null);
  assert.equal(T.killBlock(STATE, ['sim041', 'live099'], new Set()), 'Arm LIVE account FAKELIVE099 in the Trade menu first');
  assert.equal(T.killBlock(STATE, ['sim041', 'live099'], new Set(['live099'])), null);
  assert.equal(T.killBlock(STATE, ['acct123456'], new Set(['acct123456'])), "Account acct123456 is not on the desk's list — nothing sent");
  assert.equal(T.killBlock(STATE, [], new Set()), 'This algo has no accounts on the desk — nothing sent');
  // exactly what the desk sends (engine.kill_strategy -> _kill_one; `sold` never reaches the answer): a sale is its
  // "market Sell 1: ok" action (fix round 1, I1)
  const data = { ok: false, results: {
    sim041: { ok: true, acted: true, actions: ['cancel entry 11: ok', 'cancel entry 12: ok', 'market Sell 1: ok', 'cancel 13: ok', 'cancel 14: ok'] },
    sim047: { ok: false, acted: true, actions: ['cancel entry 2: ok', 'check it — position unreadable (boom); position not fully attributed; stops left working'] },
    live099: { ok: true, note: 'the bot has not acted on this account today — nothing to do' },
    acct9: { ok: false, error: 'account not connected', actions: [] },
    acct8: { ok: true, acted: true, pending: true, note: 'its orders are not acknowledged yet — they are cancelled and its position flattened as soon as they are' },
    acct7: { ok: true, acted: true, actions: ['cancel entry 1: ok', 'cancel entry 2: ok', 'the account is already flat', 'cancel 3: ok'] },
    acct6: { ok: false, actions: ['order 5: status unknown — check it'] },
    acct5: { ok: true, actions: ['cancel 9: ok'] },
    acct4: { ok: true, actions: [] },
    acct3: { ok: true, note: 'already killed — nothing to do' },
    acct2: { ok: false, acted: true, actions: ['cancel entry 1: ok', 'market Buy 2: broker said no', 'check it — market-out reported failure; verify the position; position not fully attributed; stops left working'] },
    acct1: { ok: false, error: 'internal error: RuntimeError: x', actions: [] } } };
  assert.deepEqual(T.resultToasts('bot-kill', 200, data, STATE), [
    { tone: 'ok', text: '…041 · killed — position flattened' },
    { tone: 'warn', text: '…047 · CHECK IT — position unreadable (boom); position not fully attributed; stops left working' },
    { tone: 'ok', text: '…099 · the bot has not acted on this account today — nothing to do' },
    { tone: 'err', text: 'acct9 · kill failed — account not connected' },
    { tone: 'warn', text: 'acct8 · kill pending — its orders are not acknowledged yet — they are cancelled and its position flattened as soon as they are' },
    { tone: 'ok', text: 'acct7 · killed — its orders cancelled' },
    { tone: 'warn', text: 'acct6 · CHECK IT — order 5: status unknown — check it' },
    { tone: 'ok', text: 'acct5 · killed — its leftover orders cancelled' },
    { tone: 'ok', text: 'acct4 · killed — nothing was working' },
    { tone: 'ok', text: 'acct3 · already killed — nothing to do' },
    { tone: 'warn', text: 'acct2 · CHECK IT — market-out reported failure; verify the position; position not fully attributed; stops left working' },
    { tone: 'err', text: 'acct1 · kill failed — internal error: RuntimeError: x' }]);
  assert.equal(T.killSold(['market Sell 1: ok']), true);
  assert.equal(T.killSold(['market Sell 1: broker said no', 'cancel 3: ok']), false);
  assert.equal(T.killSold(['smarket Sell 1: ok']), false);
  assert.equal(T.killSold(null), false);
  assert.deepEqual(T.resultToasts('bot-kill', 200, { ok: false, results: {}, error: 'internal error: KeyError: x' }, STATE),
    [{ tone: 'err', text: 'internal error: KeyError: x' }]);
  assert.deepEqual(T.resultToasts('bot-kill', 503, { detail: 'desk unreachable' }, STATE), [{ tone: 'err', text: 'desk unreachable' }]);
});

test('bot history is refetched when an exit fill or a skip shows on the bot view', () => {
  const sig = (patch, accts) => T.historySig(botState(patch, accts).bot.strategies.nq930);
  const base = sig({});
  assert.equal(sig({}), base);
  assert.equal(sig({ timer: { ...NQ930.timer, adx: 99 } }), base);                        // noise: no refetch
  assert.notEqual(sig({ timer: { stage: 'skipped', gate: false } }), base);                 // a skip
  assert.notEqual(sig({}, { sim041: { ...NQ930.accounts.sim041, status: 'done', exit_fill: 30925 } }), base);   // an exit fill
  assert.notEqual(sig({ killed: true }), base);
  assert.equal(T.historySig(null), '');
});

test('table rows', () => {
  const q = { NQ: { last: 30910 } };
  assert.deepEqual(T.positionRows(STATE, q)[0], { key: 'sim041:NQZ6', account: 'sim041', who: 'SIM0000041', env: 'demo', symbol: 'NQZ6', root: 'NQ',
    side: 'Long', qty: 2, avg: '30,900.00', last: '30,910.00', pnl: '+$400', tone: 'up' });
  assert.equal(T.positionRows(STATE, {})[2].pnl, '—');
  const o = T.orderRows(STATE);
  assert.deepEqual(o.find((r) => r.order_id === '14'), { key: 'sim041:14', account: 'sim041', who: 'SIM0000041', symbol: 'NQZ6', side: 'Sell', type: 'Stop', qty: 1,
    price: '30,890.00', status: '', owner: '9:30 bot', order_id: '14', cancellable: false });
  assert.deepEqual(T.fillRows(STATE).map((r) => r.time), ['09:31:12', '09:30:01']);
  assert.deepEqual(T.fillRows(STATE).map((r) => r.key), ['sim041:1', 'sim041:2']);
  const a = T.accountRows(STATE, q)[0];
  assert.deepEqual([a.who, a.env, a.balance, a.realized, a.open, a.strategies, a.status], ['SIM0000041', 'demo', '$50,000', '$0', '+$400', '9:30 bot', 'Ready']);
});

test('diffRows: a key present before and after is neither added nor removed (a DOM row keyed on it is never torn down)', () => {
  const rows = [{ k: 'a' }, { k: 'b' }, { k: 'c' }];
  assert.deepEqual(T.diffRows(['a', 'b'], rows, (r) => r.k), { keys: ['a', 'b', 'c'], add: ['c'], remove: [] });
  assert.deepEqual(T.diffRows(['a', 'b', 'z'], [{ k: 'b' }], (r) => r.k), { keys: ['b'], add: [], remove: ['a', 'z'] });
  assert.deepEqual(T.diffRows([], [], () => 'x'), { keys: [], add: [], remove: [] });
  // every key common to both lists is absent from both add and remove
  const prev = ['a', 'b', 'c'], next = [{ k: 'b' }, { k: 'c' }, { k: 'd' }];
  const d = T.diffRows(prev, next, (r) => r.k);
  for (const k of ['b', 'c']) { assert.ok(!d.add.includes(k)); assert.ok(!d.remove.includes(k)); }
});

test('enterConfirms: only the primary button or a non-button element, and never a held key', () => {
  const yes = { tagName: 'BUTTON' }, no = { tagName: 'BUTTON' }, x = { tagName: 'BUTTON' }, ck = { tagName: 'INPUT' };
  assert.equal(T.enterConfirms(yes, yes), true);     // the primary button itself
  assert.equal(T.enterConfirms(no, yes), false);     // Cancel
  assert.equal(T.enterConfirms(x, yes), false);      // × (any other button)
  assert.equal(T.enterConfirms(ck, yes), true);      // a non-button element (the checkbox, a row: M7 keeps this)
  assert.equal(T.enterConfirms(null, yes), false);
  assert.equal(T.enterConfirms(yes, yes, true), false);   // I3: a held (auto-repeat) Enter never confirms
  assert.equal(T.enterConfirms(ck, yes, true), false);    // repeat wins even over a non-button target
});

test('resolveConfirmedAccounts: send only the shown ∩ fresh accounts; an ADDED account aborts entirely', () => {
  assert.deepEqual(T.resolveConfirmedAccounts(['sim041', 'sim047'], ['sim041', 'sim047']), { ok: true, accounts: ['sim041', 'sim047'] });
  assert.deepEqual(T.resolveConfirmedAccounts(['sim041', 'sim047'], ['sim041']), { ok: true, accounts: ['sim041'] });   // shrank: fine
  assert.deepEqual(T.resolveConfirmedAccounts(['sim041'], ['sim041', 'sim047']), { ok: false, accounts: [] });          // grew: abort
  assert.deepEqual(T.resolveConfirmedAccounts([], []), { ok: true, accounts: [] });
});

test('armedTicked: an unarmed LIVE account is dropped; demo and armed-LIVE accounts pass through; a missing id fails CLOSED', () => {
  assert.deepEqual(T.armedTicked(STATE, ['sim041', 'sim047', 'live099'], new Set()), ['sim041', 'sim047']);
  assert.deepEqual(T.armedTicked(STATE, ['sim041', 'live099'], new Set(['live099'])), ['sim041', 'live099']);
  assert.deepEqual(T.armedTicked(STATE, ['sim041', 'live099'], []), ['sim041']);
  assert.deepEqual(T.armedTicked(null, ['sim041'], new Set()), ['sim041']);   // no state at all: nothing to check against
  // review M6: state EXISTS but doesn't recognize the id -- fails closed (dropped), not assumed armed
  assert.deepEqual(T.armedTicked(STATE, ['sim041', 'ghost-account'], new Set()), ['sim041']);
  assert.equal(T.unarmedLiveMessage({ id: 'live099', label: 'FAKELIVE099' }), 'Arm LIVE account FAKELIVE099 in the Trade menu first');
});

test('freshQuote: a quote older than 10 s (default) counts as no quote', () => {
  const q = { bid: 30900, ask: 30900.25, last: 30900.25, ts_ms: 1000 };
  assert.deepEqual(T.freshQuote(q, 1000), q);          // age 0
  assert.deepEqual(T.freshQuote(q, 11000), q);         // age 10,000 ms: still fresh (<=)
  assert.equal(T.freshQuote(q, 11001), null);          // age 10,001 ms: stale
  assert.equal(T.freshQuote(q, 5000, 2000), null);     // a tighter maxAgeMs
  assert.equal(T.freshQuote(null, 1000), null);
  assert.equal(T.freshQuote({ last: 1 }, 1000), null); // no ts_ms at all
});

test('needsQuoteForBracket (N1): only a Market order with a nonzero SL or TP tick pref needs one', () => {
  assert.equal(T.needsQuoteForBracket('Market', 20, 0), true);
  assert.equal(T.needsQuoteForBracket('Market', 0, 40), true);
  assert.equal(T.needsQuoteForBracket('Market', 0, 0), false);   // no bracket wanted: no quote needed
  assert.equal(T.needsQuoteForBracket('Limit', 20, 40), false);  // not a Market order
  assert.equal(T.needsQuoteForBracket('Stop', 20, 0), false);
});

test('refuseIfMarketable (N2/I1): the LAST KNOWN quote at any age, refuse outright with none at all', () => {
  const q = { bid: 30900, ask: 30900.25, last: 30900.25, ts_ms: 1 };   // ancient, but present
  // no quote at all: refused regardless of side/price/kind
  assert.equal(T.refuseIfMarketable('Sell', 30880, null, 'Limit'), "No price yet — can't check the move");
  // a stale-but-present quote is still used (freshness is a display/menu-only gate, not a refusal one)
  assert.equal(T.refuseIfMarketable('Sell', 30905, q, 'Limit'), null);           // 30905 above the bid: still passive, fine
  assert.equal(T.refuseIfMarketable('Sell', 30900, q, 'Limit'), 'Price moved through your level — re-check the order');   // AT the bid: marketable now
  assert.equal(T.refuseIfMarketable('Buy', 30900.25, q, 'Limit'), 'Price moved through your level — re-check the order'); // AT the ask
  assert.equal(T.refuseIfMarketable('Buy', 30905, q, 'Stop'), null);             // above the ask: still a genuine Stop, fine
});

test('placeMarkers: on the bar holding the time, inside the loaded bars, sorted', () => {
  const bars = [0, 1, 2].map((i) => ({ ms: 60000 * (10 + i), tt: 100 + i }));
  const out = D.placeMarkers(bars, [{ id: 'b', ms: 60000 * 11 + 5, x: 1 }, { id: 'a', ms: 60000 * 10 }, { id: 'early', ms: 1 },
    { id: 'late', ms: 60000 * 13 }], 60000);
  assert.deepEqual(out, [{ id: 'a', time: 100 }, { id: 'b', x: 1, time: 101 }]);
  assert.equal(D.placeMarkers(bars, [{ id: 'late', ms: 60000 * 99 }], 0).length, 1);   // non-time bars: the last bar holds the rest
  assert.deepEqual(D.placeMarkers([], [{ ms: 1 }]), []);
});

test('Stop Limit + TIF: the order body and the confirm text', () => {
  const b = T.orderBody({ clientId: 'c', accounts: ['sim041'], root: 'NQ', side: 'Buy', qty: 1, type: 'StopLimit',
    price: 30900, trigger: 30895, tif: 'GTC' });
  assert.deepEqual(b, { client_id: 'c', accounts: ['sim041'], root: 'NQ', side: 'Buy', qty: 1, type: 'StopLimit',
    price: 30900, trigger_price: 30895, tif: 'GTC' });
  assert.equal(T.confirmOrder(b, STATE, null, 20, 0.25).title, 'Buy 1 NQ Stop Limit @ 30,900.00 (trigger 30,895.00) · GTC');
  // a trigger is only sent with a Stop Limit; no tif given -> none sent (the desk defaults to Day)
  assert.deepEqual(T.orderBody({ clientId: 'c', accounts: ['a'], root: 'NQ', side: 'Sell', qty: 1, type: 'Limit', price: 5, trigger: 4 }),
    { client_id: 'c', accounts: ['a'], root: 'NQ', side: 'Sell', qty: 1, type: 'Limit', price: 5 });
  const day = T.orderBody({ clientId: 'c', accounts: ['sim041'], root: 'NQ', side: 'Sell', qty: 2, type: 'Limit', price: 30950, tif: 'Day' });
  assert.equal(day.tif, 'Day');
  assert.equal(T.confirmOrder(day, STATE, null, 20, 0.25).title, 'Sell 2 NQ Limit @ 30,950.00 · Day');
  // a Stop Limit's risk is measured from its limit: the worst fill, labelled as such
  const br = T.orderBody({ clientId: 'c', accounts: ['sim041'], root: 'NQ', side: 'Buy', qty: 1, type: 'StopLimit',
    price: 30900, trigger: 30895, sl: 30890, tp: 30920 });
  assert.equal(T.confirmOrder(br, STATE, null, 20, 0.25).bracket,
    `SL 30,890.00 risk (worst fill) ${M}$200 · TP 30,920.00 +$400 · RR 1:2`);
  // GTC: a note, never a refusal; Day and no tif: none
  assert.equal(T.confirmOrder(b, STATE, null, 20, 0.25).warn,
    "GTC stays working overnight — if it's still working at 09:28 the 9:30 bot skips this account");
  assert.equal(T.confirmOrder(day, STATE, null, 20, 0.25).warn, '');
  assert.equal(T.confirmOrder(br, STATE, null, 20, 0.25).warn, '');
});

test('Stop Limit lines: limit and trigger in the label, never draggable', () => {
  const st = { ...STATE, accounts: [acct('sim041', 'SIM0000041', 'demo', { orders: [
    { order_id: '31', symbol: 'NQZ6', side: 'Buy', type: 'StopLimit', qty: 1, price: 30905, stop_price: 30902, trigger: 30902, owner: null },
    { order_id: '32', symbol: 'NQZ6', side: 'Buy', type: 'StopLimit', qty: 1, price: 30906, stop_price: 30902, trigger: 30902, owner: null },
    { order_id: '33', symbol: 'NQZ6', side: 'Buy', type: 'Limit', qty: 1, price: 30880, stop_price: null, owner: null }] })] };
  const lines = T.linesFor(st, 'NQ', ['sim041']);
  assert.equal(lines.length, 3);                                   // a different limit is a different line
  assert.deepEqual(lines.map((g) => g.price), [30902, 30902, 30880]);   // drawn at the trigger
  assert.equal(T.lineLabel(lines[0]), 'BUY STP LMT 30,905.00 (trig 30,902.00) 1');
  assert.equal(T.lineText(lines[1], 30900), 'BUY STP LMT 30,906.00 (trig 30,902.00) 1 · …041');
  assert.deepEqual(lines.map((g) => T.canDrag(g)), [false, false, true]);
  assert.equal(T.canDrag(T.linesFor(STATE, 'NQ', ['sim041', 'sim047'])[0]), false);   // positions never drag
  assert.equal(T.canDrag(T.linesFor(STATE, 'NQ', ['sim041', 'sim047'])[1]), true);    // an SL does
});

/* ---- the order panel's pure helpers (2026-09-27 order-panel plan, Task 3) ---- */
const NOW = Date.UTC(2026, 8, 28, 14, 0, 0);
const Q = { bid: 30900, ask: 30900.25, last: 30900, ts_ms: NOW - 1000 };
const NQ = { tick: 0.25, pv: 20 };

test('exitTriple: ticks / $ / price, SL below a buy and above a sell, TP the other way; $ for the whole qty', () => {
  const t = (o) => T.exitTriple({ entry: 30900, ...NQ, qty: 1, ...o });
  assert.deepEqual(t({ unit: 'ticks', value: 20, side: 'Buy', kind: 'sl' }), { usd: 100, ticks: 20, price: 30895 });
  assert.deepEqual(t({ unit: 'ticks', value: 40, side: 'Buy', kind: 'tp' }), { usd: 200, ticks: 40, price: 30910 });
  assert.deepEqual(t({ unit: 'ticks', value: 20, side: 'Sell', kind: 'sl' }), { usd: 100, ticks: 20, price: 30905 });
  assert.deepEqual(t({ unit: 'ticks', value: 20, side: 'Sell', kind: 'tp' }), { usd: 100, ticks: 20, price: 30895 });
  // $ is the whole order's: 2 contracts x 20 ticks x $5 = $200
  assert.deepEqual(t({ unit: 'ticks', value: 20, side: 'Buy', kind: 'sl', qty: 2 }), { usd: 200, ticks: 20, price: 30895 });
  // from $: whole ticks, at least 1
  assert.deepEqual(t({ unit: 'usd', value: 100, side: 'Buy', kind: 'sl' }), { usd: 100, ticks: 20, price: 30895 });
  assert.deepEqual(t({ unit: 'usd', value: 100, side: 'Buy', kind: 'sl', qty: 2 }), { usd: 100, ticks: 10, price: 30897.5 });
  assert.deepEqual(t({ unit: 'usd', value: 7, side: 'Sell', kind: 'tp' }), { usd: 5, ticks: 1, price: 30899.75 });
  assert.deepEqual(t({ unit: 'usd', value: 8, side: 'Sell', kind: 'tp' }), { usd: 10, ticks: 2, price: 30899.5 });   // a TP: nearest
  // fix round 1 (review Minor 3): an SL in $ floors to whole ticks -- never more than the typed dollars
  assert.deepEqual(t({ unit: 'usd', value: 8, side: 'Buy', kind: 'sl' }), { usd: 5, ticks: 1, price: 30899.75 });
  assert.deepEqual(t({ unit: 'usd', value: 32, side: 'Buy', kind: 'sl', entry: 6500, tick: 0.25, pv: 50 }), { usd: 25, ticks: 2, price: 6499.5 });
  assert.deepEqual(t({ unit: 'usd', value: 99.99, side: 'Sell', kind: 'sl' }), { usd: 95, ticks: 19, price: 30904.75 });
  assert.equal(t({ unit: 'usd', value: 4.99, side: 'Buy', kind: 'sl' }), null);   // under one tick: no SL (never rounded up)
  assert.deepEqual(t({ unit: 'usd', value: 1, side: 'Buy', kind: 'tp' }), { usd: 5, ticks: 1, price: 30900.25 });
  // from a price: tick-rounded; on the wrong side (or AT the entry) there is no exit
  assert.deepEqual(t({ unit: 'price', value: 30895.1, side: 'Buy', kind: 'sl' }), { usd: 100, ticks: 20, price: 30895 });
  assert.deepEqual(t({ unit: 'price', value: 30910, side: 'Sell', kind: 'sl' }), { usd: 200, ticks: 40, price: 30910 });
  // fix round 1 (review Minor 4): an off-tick SL price rounds AWAY from the entry; a TP to the nearest tick
  assert.deepEqual(t({ unit: 'price', value: 30895.2, side: 'Buy', kind: 'sl' }), { usd: 100, ticks: 20, price: 30895 });
  assert.deepEqual(t({ unit: 'price', value: 30899.9, side: 'Buy', kind: 'sl' }), { usd: 5, ticks: 1, price: 30899.75 });
  assert.deepEqual(t({ unit: 'price', value: 30905.05, side: 'Sell', kind: 'sl' }), { usd: 105, ticks: 21, price: 30905.25 });
  assert.deepEqual(t({ unit: 'price', value: 30900.1, side: 'Sell', kind: 'sl' }), { usd: 5, ticks: 1, price: 30900.25 });
  assert.deepEqual(t({ unit: 'price', value: 30910.1, side: 'Buy', kind: 'tp' }), { usd: 200, ticks: 40, price: 30910 });
  assert.deepEqual(t({ unit: 'price', value: 30889.9, side: 'Sell', kind: 'tp' }), { usd: 200, ticks: 40, price: 30890 });
  assert.equal(t({ unit: 'price', value: 30905, side: 'Buy', kind: 'sl' }), null);
  assert.equal(t({ unit: 'price', value: 30900, side: 'Buy', kind: 'tp' }), null);
  assert.equal(t({ unit: 'price', value: 30899, side: 'Sell', kind: 'sl' }), null);
  // whole ticks >= 1; nothing typed / garbage / no entry -> no exit
  assert.deepEqual(t({ unit: 'ticks', value: 2.6, side: 'Buy', kind: 'tp' }), { usd: 15, ticks: 3, price: 30900.75 });
  for (const value of [0, -3, NaN, null, '', 0.4]) assert.equal(t({ unit: 'ticks', value, side: 'Buy', kind: 'sl' }), null, String(value));
  assert.equal(t({ unit: 'usd', value: 0, side: 'Buy', kind: 'sl' }), null);
  assert.equal(t({ unit: 'ticks', value: 20, side: 'Buy', kind: 'sl', entry: null }), null);
  assert.equal(t({ unit: 'bogus', value: 20, side: 'Buy', kind: 'sl' }), null);
  // no point value: the ticks and price stand, the $ is unknown; a $ input can't be converted at all
  assert.deepEqual(t({ unit: 'ticks', value: 20, side: 'Buy', kind: 'sl', pv: null }), { usd: null, ticks: 20, price: 30895 });
  assert.equal(t({ unit: 'usd', value: 100, side: 'Buy', kind: 'sl', pv: null }), null);
});

test('qtyFromRisk: whole contracts, floored; 0 when the risk is under one contract', () => {
  assert.equal(T.qtyFromRisk(500, 20, 0.25, 20), 5);
  assert.equal(T.qtyFromRisk(499, 20, 0.25, 20), 4);
  assert.equal(T.qtyFromRisk(300, 20, 0.25, 20), 3);
  assert.equal(T.qtyFromRisk(0.3, 1, 0.1, 1), 3);            // float noise never floors 3 down to 2
  assert.equal(T.qtyFromRisk(99, 20, 0.25, 20), 0);          // $99 < $100 for one contract
  for (const bad of [[0, 20, 0.25, 20], [500, 0, 0.25, 20], [500, 20, 0, 20], [500, 20, 0.25, null], [NaN, 20, 0.25, 20]]) {
    assert.equal(T.qtyFromRisk(...bad), 0, JSON.stringify(bad));
  }
});

test('panelOrder: every type on each side versus the quote, prices tick-rounded, tif only on resting types', () => {
  const po = (o) => T.panelOrder({ side: 'Buy', type: 'Market', qty: 1, price: null, trigger: null, sl: null, tp: null,
    tif: 'Day', risk: null, quote: Q, nowMs: NOW, ...NQ, ...o });
  assert.deepEqual(po({}), { ok: true, side: 'Buy', type: 'Market', qty: 1, price: null, trigger: null, sl: null, tp: null, tif: null });
  assert.equal(po({ side: 'Sell', tif: 'GTC' }).tif, null);   // a Market order is Day only: none sent
  // Limit: a buy strictly below the ask, a sell strictly above the bid
  assert.deepEqual(po({ type: 'Limit', price: 30899.1 }),
    { ok: true, side: 'Buy', type: 'Limit', qty: 1, price: 30899, trigger: null, sl: null, tp: null, tif: 'Day' });
  assert.equal(po({ type: 'Limit', price: 30900.25 }).ok, false);
  assert.match(po({ type: 'Limit', price: 30900.25 }).error, /buy limit.*below/i);
  assert.equal(po({ type: 'Limit', side: 'Sell', price: 30901 }).ok, true);
  assert.match(po({ type: 'Limit', side: 'Sell', price: 30900 }).error, /sell limit.*above/i);
  // Stop: a buy above the market, a sell below it
  assert.equal(po({ type: 'Stop', price: 30901 }).ok, true);
  assert.match(po({ type: 'Stop', price: 30899 }).error, /buy stop.*above/i);
  assert.equal(po({ type: 'Stop', side: 'Sell', price: 30899 }).ok, true);
  assert.match(po({ type: 'Stop', side: 'Sell', price: 30901 }).error, /sell stop.*below/i);
  // a buy stop at the ask while the last trade is also there: the desk refuses a stop at the last trade
  assert.equal(po({ type: 'Stop', price: 30900, quote: { ...Q, ask: 30900 } }).ok, false);
  // Stop Limit: the trigger like a stop; a buy's limit at or above it, a sell's at or below, within 100 ticks
  assert.deepEqual(po({ type: 'StopLimit', trigger: 30901, price: 30902, tif: 'GTC' }),
    { ok: true, side: 'Buy', type: 'StopLimit', qty: 1, price: 30902, trigger: 30901, sl: null, tp: null, tif: 'GTC' });
  assert.equal(po({ type: 'StopLimit', trigger: 30901, price: 30901 }).ok, true);
  assert.match(po({ type: 'StopLimit', trigger: 30901, price: 30900.75 }).error, /limit.*at or above.*trigger/i);
  assert.match(po({ type: 'StopLimit', trigger: 30899, price: 30900 }).error, /trigger.*above/i);
  assert.match(po({ type: 'StopLimit', trigger: 30901, price: 30901 + 101 * 0.25 }).error, /within 100 ticks/);
  assert.equal(po({ type: 'StopLimit', side: 'Sell', trigger: 30899, price: 30898 }).ok, true);
  assert.match(po({ type: 'StopLimit', side: 'Sell', trigger: 30899, price: 30899.25 }).error, /limit.*at or below.*trigger/i);
  assert.match(po({ type: 'StopLimit', side: 'Sell', trigger: 30901, price: 30900 }).error, /trigger.*below/i);
  // a missing price
  assert.match(po({ type: 'Limit', price: null }).error, /price/i);
  assert.match(po({ type: 'StopLimit', trigger: null, price: 30902 }).error, /trigger/i);
  assert.match(po({ type: 'StopLimit', trigger: 30901, price: NaN }).error, /limit/i);
  // tif
  assert.equal(po({ type: 'Limit', price: 30899, tif: 'GTC' }).tif, 'GTC');
  assert.equal(po({ type: 'Limit', price: 30899, tif: 'IOC' }).ok, false);
  // bad side / type
  assert.equal(po({ side: 'Short' }).ok, false);
  assert.equal(po({ type: 'TrailingStop' }).ok, false);
});

test('panelOrder: the SL / TP side, a Stop Limit\'s SL beyond the TRIGGER and TP beyond the LIMIT', () => {
  const po = (o) => T.panelOrder({ side: 'Buy', type: 'Limit', qty: 1, price: 30899, trigger: null, sl: null, tp: null,
    tif: 'Day', risk: null, quote: Q, nowMs: NOW, ...NQ, ...o });
  const ok = po({ sl: 30895.2, tp: 30910 });
  assert.equal(ok.ok, true);
  assert.equal(ok.sl, 30895);   // away from the entry, never toward it (fix round 1)
  assert.equal(po({ side: 'Sell', price: 30901, sl: 30905.05 }).sl, 30905.25);
  assert.equal(ok.tp, 30910);
  assert.match(po({ sl: 30899 }).error, /stop loss.*below/i);
  assert.match(po({ tp: 30898 }).error, /take profit.*above/i);
  assert.equal(po({ side: 'Sell', price: 30901, sl: 30905, tp: 30890 }).ok, true);
  assert.match(po({ side: 'Sell', price: 30901, sl: 30900 }).error, /stop loss.*above/i);
  assert.match(po({ side: 'Sell', price: 30901, tp: 30902 }).error, /take profit.*below/i);
  // Market: measured from the (fresh) last trade
  assert.equal(po({ type: 'Market', price: null, sl: 30895, tp: 30910 }).ok, true);
  assert.match(po({ type: 'Market', price: null, sl: 30900 }).error, /stop loss/i);
  // Stop Limit buy, trigger 30901 / limit 30903: an SL between the two is refused, as is a TP under the limit
  const sl = (o) => po({ type: 'StopLimit', trigger: 30901, price: 30903, ...o });
  assert.match(sl({ sl: 30902 }).error, /stop loss.*trigger/i);
  assert.equal(sl({ sl: 30900 }).ok, true);
  assert.match(sl({ tp: 30902.5 }).error, /take profit.*limit/i);
  assert.equal(sl({ tp: 30904 }).ok, true);
  // ... and the mirror for a sell: trigger 30899 / limit 30897
  const ss = (o) => po({ side: 'Sell', type: 'StopLimit', trigger: 30899, price: 30897, ...o });
  assert.match(ss({ sl: 30898 }).error, /stop loss.*trigger/i);
  assert.equal(ss({ sl: 30900 }).ok, true);
  assert.match(ss({ tp: 30897.5 }).error, /take profit.*limit/i);
  assert.equal(ss({ tp: 30896 }).ok, true);
});

test('panelOrder: no quote refuses; a stale quote refuses only a Market with an exit; qty 1-10', () => {
  const po = (o) => T.panelOrder({ side: 'Buy', type: 'Market', qty: 1, price: null, trigger: null, sl: null, tp: null,
    tif: 'Day', risk: null, quote: Q, nowMs: NOW, ...NQ, ...o });
  for (const type of ['Market', 'Limit', 'Stop', 'StopLimit']) {
    const r = po({ type, quote: null, price: 30899, trigger: 30901 });
    assert.equal(r.ok, false, type);
    assert.match(r.error, /no price/i, type);
  }
  const stale = { ...Q, ts_ms: NOW - 20000 };
  assert.match(po({ quote: stale, sl: 30895 }).error, /no recent price/i);
  assert.match(po({ quote: stale, tp: 30910 }).error, /no recent price/i);
  assert.equal(po({ quote: stale }).ok, true);                                   // no exit: nothing to compute
  assert.equal(po({ quote: stale, type: 'Limit', price: 30899, sl: 30895 }).ok, true);   // measured from its own price
  // quantity: whole, 1-10
  assert.equal(po({ qty: 10 }).ok, true);
  for (const qty of [0, 11, 1.5, -1, NaN, null]) assert.match(po({ qty }).error, /quantity/i, String(qty));
  assert.equal(po({ qty: 4, qtyMax: 3 }).ok, false);
});

test('panelOrder: USD risk sizes from the stop; under one contract, no stop, or over the cap refuses', () => {
  const po = (o) => T.panelOrder({ side: 'Buy', type: 'Limit', qty: null, price: 30900, trigger: null, sl: 30895, tp: null,
    tif: 'Day', risk: 500, quote: Q, nowMs: NOW, ...NQ, ...o });   // SL 20 ticks = $100 a contract
  assert.equal(po({}).qty, 5);
  assert.equal(po({ risk: 499 }).qty, 4);
  assert.match(po({ risk: 50 }).error, /under one contract/i);
  assert.match(po({ sl: null }).error, /stop loss/i);
  for (const risk of [0, -5, NaN, '']) assert.match(po({ risk }).error, /enter the usd risk/i, String(risk));
  assert.match(po({ risk: 5000 }).error, /quantity/i);   // 50 contracts
  assert.match(po({ pv: null }).error, /point value/i);
  // Market: the stop measured from the last trade (30900 here, 20 ticks)
  assert.equal(po({ type: 'Market', price: null }).qty, 5);
  // Stop Limit: from the LIMIT (the worst fill), as the confirm's "risk (worst fill)": limit 30902 to SL 30896 =
  // 24 ticks = $120 a contract -> 4 (from the trigger it would have been 5)
  assert.equal(po({ type: 'StopLimit', trigger: 30901, price: 30902, sl: 30896 }).qty, 4);
  // fix round 1 (review Important 1): trigger 30901, limit 30926, SL 30896 = 120 ticks = $600 a contract: $500 -> 0
  const wide = po({ type: 'StopLimit', trigger: 30901, price: 30926, sl: 30896 });
  assert.equal(wide.ok, false);
  assert.match(wide.error, /under one contract/i);
});

test('sendLabel: "Buy 2 NQ LIMIT" -- the ROOT the body carries, never a guessed contract (fix round 1)', () => {
  assert.equal(T.sendLabel('Buy', 1, 'NQ', 'Market'), 'Buy 1 NQ MARKET');
  assert.equal(T.sendLabel('Buy', 2, 'NQ', 'Limit'), 'Buy 2 NQ LIMIT');
  assert.equal(T.sendLabel('Buy', 3, 'ES', 'StopLimit'), 'Buy 3 ES STOP LIMIT');
  assert.equal(T.sendLabel('Sell', 0, 'GC', 'Stop'), 'Sell GC STOP');   // no valid size: no number
  assert.equal(T.contractOf, undefined);
});

test('parseQty / parseUsd / parseDecimal: plain digits only -- no commas, hex, exponents or signs (fix round 1)', () => {
  assert.equal(T.parseQty('5'), 5);
  assert.equal(T.parseQty(' 12 '), 12);
  for (const s of ['0,5', '1,000', '0x5', '1e1', '+3', '-3', '2.', '2.0', '1.5', '', ' ', 'abc', '５', null, undefined]) {
    assert.ok(Number.isNaN(T.parseQty(s)), JSON.stringify(s));
  }
  assert.equal(T.parseUsd('500'), 500);
  assert.equal(T.parseUsd('31.25'), 31.25);
  assert.equal(T.parseUsd('.5'), 0.5);
  assert.equal(T.parseUsd('500.'), 500);
  for (const s of ['1,000', '1.2.3', '0x10', '1e3', '-5', '+5', '$5', '', '.', null]) assert.ok(Number.isNaN(T.parseUsd(s)), JSON.stringify(s));
  assert.equal(T.parseDecimal('30900.25'), 30900.25);
  assert.equal(T.parseDecimal('-12.5', true), -12.5);   // a price may be negative only when asked
  for (const s of ['30,900', '0x10', '1e5', '-12.5', 'Infinity', 'NaN']) assert.ok(Number.isNaN(T.parseDecimal(s)), JSON.stringify(s));
});
