import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const T = require('../../homebase/static/charts/trade.js');
const M = '−';

const acct = (id, label, extra = {}) => ({ id, label, env: 'live', connected: true, tradable: true, error: null,
  balance: 50000, realized_pnl: 0, positions: [], orders: [], fills: [], strategies: [], ...extra });
const ROOM = { daily: 700, drawdown: 1500, contracts: 4 };
const body = (o) => T.orderBody({ clientId: 'c', accounts: ['p1'], root: 'NQ', side: 'Buy', qty: 1, type: 'Market', ...o });

test('account rows: the room line, with an open loss taken off, and nothing without a room', () => {
  const st = { accounts: [acct('p1', 'PA-1', { room: ROOM }), acct('p2', 'PA-2')] };
  const [a, b] = T.accountRows(st, {});
  assert.equal(a.room, 'daily $700 · drawdown $1,500 · max 4 contracts');
  assert.equal(b.room, '');
  // 2 NQ long from 30,900, last 30,890: open loss $400 comes off daily and drawdown
  const held = { accounts: [acct('p1', 'PA-1', { room: ROOM, positions: [{ symbol: 'NQZ6', net: 2, avg_price: 30900, root: 'NQ', point_value: 20 }] })] };
  assert.equal(T.accountRows(held, { NQ: { last: 30890 } })[0].room, 'daily $300 · drawdown $1,100 · max 4 contracts');
  assert.equal(T.accountRows(held, { NQ: { last: 30910 } })[0].room, 'daily $700 · drawdown $1,500 · max 4 contracts');   // a gain is not added
});

test('confirm: the room line is shown and a stop that loses more than the room warns, never blocks', () => {
  const st = { accounts: [acct('p1', 'PA-1', { room: ROOM })] };
  const fine = T.confirmOrder(body({ sl: 30990, tp: 31020 }), st, { last: 31000 }, 20, 0.25);   // risk $200
  assert.equal(fine.bracket, `SL 30,990.00 ${M}$200 · TP 31,020.00 +$400 · RR 1:2 · room: daily $700 · drawdown $1,500 · max 4 contracts`);
  assert.equal(fine.warn, '');
  const big = T.confirmOrder(body({ sl: 30960 }), st, { last: 31000 }, 20, 0.25);              // risk $800 > daily $700
  assert.match(big.warn, /stop-out loses \$800.*daily loss \$700/);
  assert.ok(!/drawdown/.test(big.warn));
  assert.equal(big.accounts.length, 1);                                                          // the order is still the order
  // no stop: nothing to compare while there is room; no room left at all warns
  assert.equal(T.confirmOrder(body({}), st, { last: 31000 }, 20, 0.25).warn, '');
  const none = { accounts: [acct('p1', 'PA-1', { room: { daily: -50, drawdown: 900, contracts: 4 } })] };
  assert.match(T.confirmOrder(body({}), none, { last: 31000 }, 20, 0.25).warn, /no room left.*daily loss −\$50/);
});

test('confirm: an order that closes the position never warns; two accounts are told apart', () => {
  const long = acct('p1', 'PA-1', { room: { daily: 0, drawdown: 100, contracts: 4 }, positions: [{ symbol: 'NQZ6', net: 1, avg_price: 31000, root: 'NQ', point_value: 20 }] });
  const sell = T.confirmOrder(body({ side: 'Sell', sl: 31100 }), { accounts: [long] }, { last: 31000 }, 20, 0.25);
  assert.ok(sell.bracket.includes('room: daily $0'));
  assert.equal(sell.warn, '');
  const two = { accounts: [acct('p1', 'PA-ONE', { room: ROOM }), acct('p2', 'PA-TWO', { room: { daily: 100, drawdown: 1500, contracts: 4 } })] };
  const c = T.confirmOrder(body({ accounts: ['p1', 'p2'], sl: 30980 }), two, { last: 31000 }, 20, 0.25);   // risk $400 each
  assert.ok(c.bracket.includes('…ONE room: daily $700') && c.bracket.includes('…TWO room: daily $100'));
  assert.ok(c.warn.includes('…TWO') && !c.warn.includes('…ONE'));
});

test('confirm: an account with no room keeps the confirm exactly as it was', () => {
  const st = { accounts: [acct('p1', 'PA-1')] };
  assert.deepEqual(T.confirmOrder(body({ sl: 30960 }), st, { last: 31000 }, 20, 0.25),
    { title: 'Buy 1 NQ at market', accounts: [{ id: 'p1', label: 'PA-1', env: 'live' }], bracket: `SL 30,960.00 ${M}$800`, each: '', live: true, warn: '' });
});
