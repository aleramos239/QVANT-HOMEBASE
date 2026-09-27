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

test('Limit or Stop from the clicked price (TradingView), and the menu text', () => {
  const q = { bid: 30900, ask: 30900.25, last: 30900.25 };
  assert.equal(T.inferType('Buy', 30901, q), 'Stop');
  assert.equal(T.inferType('Buy', 30900.25, q), 'Limit');
  assert.equal(T.inferType('Sell', 30899.75, q), 'Stop');
  assert.equal(T.inferType('Sell', 30900, q), 'Limit');
  assert.equal(T.inferType('Buy', 30901, null), null);
  assert.equal(T.inferType('Buy', 30901, { last: 30902 }), 'Limit');   // no ask: the last trade
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

test('trade mode: down, off, none, on', () => {
  assert.deepEqual(T.tradeMode({ state: null, down: 'desk unreachable' }, TICKED), { mode: 'down', reason: 'desk unreachable', accounts: [] });
  assert.equal(T.tradeMode({ state: { ...STATE, enabled: false } }, TICKED).mode, 'off');
  assert.equal(T.tradeMode({ state: STATE }, { ...TICKED, ticked: [] }).reason, 'Tick an account in the Trade menu');
  const odd = { ...STATE, accounts: STATE.accounts.map((a) => ({ ...a, tradable: false })) };
  assert.equal(T.tradeMode({ state: odd }, TICKED).mode, 'none');
  assert.deepEqual(T.tradeMode({ state: STATE }, TICKED), { mode: 'on', reason: '', accounts: ['sim041', 'sim047'] });
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

test('lines: merged positions, SL/TP legs with dollars, plain orders, bots\' orders left out, ticked accounts only', () => {
  const lines = T.linesFor(STATE, 'NQ', TICKED);
  assert.deepEqual(lines.map((g) => g.kind), ['position', 'sl', 'tp', 'order']);
  assert.deepEqual(lines.map((g) => T.lineText(g, 30910)),
    ['LONG 3 · +$600 · 2 accts', `SL 3 · ${M}$900 · 2 accts`, 'TP 2 · +$1,200 · …041', 'BUY LMT 1 · …041']);
  assert.equal(T.lineText(lines[0], null), 'LONG 3 · 2 accts');
  assert.deepEqual(lines[1].legs.map((l) => [l.account, l.order_id]), [['sim041', '11'], ['sim047', '21']]);
  assert.deepEqual(lines.map((g) => T.lineColor(g, P)), [P.up, P.down, P.up, P.accent]);
  assert.equal(T.lineText(T.withPrice(lines[1], 30880), 30910), `SL 3 · ${M}$1,200 · 2 accts`);
  assert.deepEqual(T.linesFor(STATE, 'NQ', { ...TICKED, ticked: [] }), []);
  assert.deepEqual(T.linesFor(null, 'NQ', TICKED), []);
  assert.deepEqual(T.lineLabel(lines[3]), 'BUY LMT 1');
});

test('confirm: title, bracket dollars and RR, accounts, LIVE flag', () => {
  const b = T.orderBody({ clientId: 'c', accounts: ['sim041', 'sim047'], root: 'NQ', side: 'Buy', qty: 2, type: 'Limit', price: 30900, sl: 30885, tp: 30930 });
  assert.deepEqual(T.confirmOrder(b, STATE, null, 20, 0.25), {
    title: 'Buy 2 NQ Limit @ 30,900.00',
    accounts: [{ id: 'sim041', label: 'SIM0000041', env: 'demo' }, { id: 'sim047', label: 'SIM0000047', env: 'demo' }],
    bracket: `SL 30,885.00 ${M}$600 · TP 30,930.00 +$1,200 · RR 1:2`, each: 'each of 2 accounts', live: false });
  const m = T.orderBody({ clientId: 'c', accounts: ['live099'], root: 'NQ', side: 'Sell', qty: 1, type: 'Market' });
  const c = T.confirmOrder(m, STATE, { last: 30910 }, 20, 0.25);
  assert.equal(c.title, 'Sell 1 NQ at market');
  assert.equal(c.live, true);
  assert.equal(c.bracket, '');
  const sl = T.linesFor(STATE, 'NQ', TICKED)[1];
  assert.equal(T.actionTitle('modify', { root: 'NQ', line: sl, from: 30885, to: 30880 }, 0.25), 'Move SL 3 30,885.00 → 30,880.00');
  assert.equal(T.actionTitle('cancel', { root: 'NQ', line: sl }, 0.25), 'Cancel SL 3 @ 30,885.00 · 2 accts');
  assert.equal(T.actionTitle('reverse', { root: 'NQ' }, 0.25), 'Reverse NQ');
  assert.equal(T.actionTitle('cancel-symbol', { root: 'NQ' }, 0.25), 'Cancel all NQ orders');
  assert.equal(T.actionTitle('flatten', { root: 'NQ', line: T.linesFor(STATE, 'NQ', TICKED)[0] }, 0.25), 'Flatten NQ · 2 accts');
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

test('execution markers: ticked accounts, manual fills only, at the fill price', () => {
  assert.deepEqual(T.fillMarkers(STATE, 'NQ', TICKED, P), [{ id: 'fsim041:1', ms: Date.parse('2026-09-22T13:31:12.000Z'), price: 30900,
    position: 'atPriceBottom', shape: 'arrowUp', color: P.accent, text: '' }]);
});

test('bots: badge, entry lines merged across accounts, markers from the bot\'s fills', () => {
  const [b, ten] = T.botsFor(STATE, 'NQ', 0.25, P);
  assert.deepEqual(b.badge, { text: '9:30 bot · TREND ADX 23.4 · placed', tone: 'live' });
  assert.deepEqual(b.lines.map((l) => l.text), ['9:30 BUY STOP 10 @ 30,910.00', '9:30 SELL STOP 10 @ 30,890.00']);
  assert.deepEqual(b.markers.map((m) => [m.shape, m.price, m.text]), [['arrowUp', 30910, '']]);
  assert.deepEqual(ten.badge, { text: '10am bot · idle · shadow', tone: 'idle' });
  assert.equal(T.botsFor(STATE, 'YM', 1, P)[0].badge.text, '9:30 bot · off');
  const done = structuredClone(STATE);
  Object.assign(done.bot.strategies.nq930, { day_status: 'done' });
  done.bot.strategies.nq930.accounts.sim041 = { status: 'done', qty: 1, entry_side: 'Buy', pnl: 876 };
  assert.equal(T.botsFor(done, 'NQ', 0.25, P)[0].badge.text, '9:30 bot · TREND ADX 23.4 · done +$876');
  assert.deepEqual(T.botsFor(done, 'NQ', 0.25, P)[0].lines, []);
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

test('enterConfirms: only the primary button or a non-button element', () => {
  const yes = { tagName: 'BUTTON' }, no = { tagName: 'BUTTON' }, x = { tagName: 'BUTTON' }, ck = { tagName: 'INPUT' };
  assert.equal(T.enterConfirms(yes, yes), true);     // the primary button itself
  assert.equal(T.enterConfirms(no, yes), false);     // Cancel
  assert.equal(T.enterConfirms(x, yes), false);      // × (any other button)
  assert.equal(T.enterConfirms(ck, yes), true);      // a non-button element (the checkbox, a row)
  assert.equal(T.enterConfirms(null, yes), false);
});

test('resolveConfirmedAccounts: send only the shown ∩ fresh accounts; an ADDED account aborts entirely', () => {
  assert.deepEqual(T.resolveConfirmedAccounts(['sim041', 'sim047'], ['sim041', 'sim047']), { ok: true, accounts: ['sim041', 'sim047'] });
  assert.deepEqual(T.resolveConfirmedAccounts(['sim041', 'sim047'], ['sim041']), { ok: true, accounts: ['sim041'] });   // shrank: fine
  assert.deepEqual(T.resolveConfirmedAccounts(['sim041'], ['sim041', 'sim047']), { ok: false, accounts: [] });          // grew: abort
  assert.deepEqual(T.resolveConfirmedAccounts([], []), { ok: true, accounts: [] });
});

test('armedTicked: an unarmed LIVE account is dropped; demo and armed-LIVE accounts pass through', () => {
  assert.deepEqual(T.armedTicked(STATE, ['sim041', 'sim047', 'live099'], new Set()), ['sim041', 'sim047']);
  assert.deepEqual(T.armedTicked(STATE, ['sim041', 'live099'], new Set(['live099'])), ['sim041', 'live099']);
  assert.deepEqual(T.armedTicked(STATE, ['sim041', 'live099'], []), ['sim041']);
  assert.deepEqual(T.armedTicked(null, ['sim041'], new Set()), ['sim041']);   // no state: nothing to check against
  assert.equal(T.unarmedLiveMessage({ id: 'live099', label: 'FAKELIVE099' }), 'Arm LIVE account FAKELIVE099 in the Trade menu first');
});

test('placeMarkers: on the bar holding the time, inside the loaded bars, sorted', () => {
  const bars = [0, 1, 2].map((i) => ({ ms: 60000 * (10 + i), tt: 100 + i }));
  const out = D.placeMarkers(bars, [{ id: 'b', ms: 60000 * 11 + 5, x: 1 }, { id: 'a', ms: 60000 * 10 }, { id: 'early', ms: 1 },
    { id: 'late', ms: 60000 * 13 }], 60000);
  assert.deepEqual(out, [{ id: 'a', time: 100 }, { id: 'b', x: 1, time: 101 }]);
  assert.equal(D.placeMarkers(bars, [{ id: 'late', ms: 60000 * 99 }], 0).length, 1);   // non-time bars: the last bar holds the rest
  assert.deepEqual(D.placeMarkers([], [{ ms: 1 }]), []);
});
