import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

const require = createRequire(import.meta.url);
const R = require('../../homebase/static/charts/replay.js');

test('parseState: the server\'s replay_state, normalised; garbage in is null', () => {
  assert.deepEqual(R.parseState({ type: 'replay_state', id: 'c1', date: '2024-03-08', cursor_ms: 1000, speed: 5,
    playing: true, done: false }), { id: 'c1', date: '2024-03-08', cursorMs: 1000, speed: 5, playing: true, done: false, stopped: false });
  assert.deepEqual(R.parseState({ id: 'c1', date: '2024-03-08', cursor_ms: 1, speed: 'bar', playing: false, done: true, stopped: true }),
    { id: 'c1', date: '2024-03-08', cursorMs: 1, speed: 'bar', playing: false, done: true, stopped: true });
  assert.equal(R.parseState(null), null);
  assert.equal(R.parseState('nope'), null);
  // a garbage speed defaults to 1 rather than propagating something the UI cannot label
  assert.equal(R.parseState({ id: 'c1', date: '2024-03-08', cursor_ms: 1, speed: 99, playing: false, done: false }).speed, 1);
  // a non-string id/date/non-finite cursor all fall back to safe defaults, never throwing
  assert.deepEqual(R.parseState({}), { id: '', date: '', cursorMs: 0, speed: 1, playing: false, done: false, stopped: false });
});

test('fmtCursor: cursor_ms as an ET date + time (2024-03-08 is EST, UTC-5)', () => {
  // 2024-03-08 14:31:05 UTC = 09:31:05 EST
  const ms = Date.UTC(2024, 2, 8, 14, 31, 5);
  assert.equal(R.fmtCursor(ms), '2024-03-08 09:31:05 ET');
  // 2024-07-08 13:31:05 UTC = 09:31:05 EDT (daylight saving)
  const dst = Date.UTC(2024, 6, 8, 13, 31, 5);
  assert.equal(R.fmtCursor(dst), '2024-07-08 09:31:05 ET');
  assert.equal(R.fmtCursor(null), '');
  assert.equal(R.fmtCursor(NaN), '');
});

test('validStart: the archive window (2021-09-22 to yesterday), HH:MM only', () => {
  assert.equal(R.validStart('2024-03-08', '09:30', '2024-03-09'), true);
  assert.equal(R.validStart('2021-09-22', '00:00', '2024-03-09'), true);   // the archive's first session
  assert.equal(R.validStart('2021-09-21', '09:30', '2024-03-09'), false);  // before the archive
  assert.equal(R.validStart('2024-03-09', '09:30', '2024-03-09'), false);  // today is not a completed session
  assert.equal(R.validStart('2024-03-10', '09:30', '2024-03-09'), false);  // after today
  assert.equal(R.validStart('2024-03-08', '24:00', '2024-03-09'), false);  // hour out of range
  assert.equal(R.validStart('2024-03-08', '09:60', '2024-03-09'), false);  // minute out of range
  assert.equal(R.validStart('2024-03-08', '9:30', '2024-03-09'), false);   // must be zero-padded
  assert.equal(R.validStart('03/08/2024', '09:30', '2024-03-09'), false);
  assert.equal(R.validStart(null, '09:30', '2024-03-09'), false);
  assert.equal(R.validStart('2024-03-08', null, '2024-03-09'), false);
});

test('speedLabel: 1x .. 60x, and Bar', () => {
  assert.equal(R.speedLabel(1), '1×');
  assert.equal(R.speedLabel(2), '2×');
  assert.equal(R.speedLabel(60), '60×');
  assert.equal(R.speedLabel('bar'), 'Bar');
});

test('startOp: always speed "bar" (the floating bar\'s speed menu changes it after)', () => {
  assert.deepEqual(R.startOp('c1', '2024-03-08', '09:30'), { op: 'replay_start', id: 'c1', date: '2024-03-08', start_et: '09:30', speed: 'bar' });
  assert.deepEqual(R.startOp(2, '2024-03-08', '09:30'), { op: 'replay_start', id: '2', date: '2024-03-08', start_et: '09:30', speed: 'bar' });
});

test('ctlOp: play / pause / step take no extra fields; speed / jump carry theirs', () => {
  assert.deepEqual(R.ctlOp('c1', 'play'), { op: 'replay_ctl', id: 'c1', action: 'play' });
  assert.deepEqual(R.ctlOp('c1', 'pause'), { op: 'replay_ctl', id: 'c1', action: 'pause' });
  assert.deepEqual(R.ctlOp('c1', 'step'), { op: 'replay_ctl', id: 'c1', action: 'step' });
  assert.deepEqual(R.ctlOp('c1', 'speed', { speed: 5 }), { op: 'replay_ctl', id: 'c1', action: 'speed', speed: 5 });
  assert.deepEqual(R.ctlOp('c1', 'jump', { to_et: '10:00' }), { op: 'replay_ctl', id: 'c1', action: 'jump', to_et: '10:00' });
});

test('stopOp', () => {
  assert.deepEqual(R.stopOp('c1'), { op: 'replay_stop', id: 'c1' });
});

test('SPEEDS / FIRST_DATE are exported for the UI\'s speed menu and date field', () => {
  assert.deepEqual(R.SPEEDS, [1, 2, 5, 10, 30, 60, 'bar']);
  assert.equal(R.FIRST_DATE, '2021-09-22');
});

/* ================================================================================================
   Task 2: practice trading -- the fill law, ported from homebase/backtest/engine.py, and the
   practice simulator. Every rule below is cited to the exact engine.py lines it mirrors.
   ================================================================================================ */

test('toTick / tickCmp: snap to the grid, epsilon-tolerant compare (engine.py:52-66)', () => {
  assert.equal(R.toTick(100.3, 0.25), 100.25);
  assert.equal(R.toTick(100.4, 0.25), 100.5);
  const noisy = 64.01 + 0.01;             // 64.020000000000003 in IEEE-754 -- engine.py's own docstring warning
  assert.notEqual(noisy, 64.02);          // the float noise is real, not a typo
  assert.equal(R.tickCmp(noisy, 64.02, 0.01), 0);
  assert.equal(R.tickCmp(100.5, 100.25, 0.25), 1);
  assert.equal(R.tickCmp(100, 100.25, 0.25), -1);
});

test('firstAtOrAbove / firstAtOrBelow: the trigger scan (engine.py:69-92)', () => {
  assert.equal(R.firstAtOrAbove([99, 99.5, 100], 100, 0.25), 2);
  assert.equal(R.firstAtOrAbove([99, 99.5], 100, 0.25), 2);          // never reached -> px.length
  assert.equal(R.firstAtOrBelow([101, 100.5, 100], 100, 0.25), 2);
  assert.equal(R.firstAtOrBelow([101, 100.5], 100, 0.25), 2);
});

test('triggerIndex + fillPrice: a Market order fills at the next print, +/- slip (engine.py:278-279,293-295)', () => {
  const tick = 0.25, slip = 0.25;
  const buy = { side: 1, kind: 'market', price: null };
  assert.equal(R.triggerIndex(buy, [100, 101], tick), 0);
  assert.equal(R.fillPrice(buy, 100, tick, slip), 100.25);
  const sell = { side: -1, kind: 'market', price: null };
  assert.equal(R.fillPrice(sell, 100, tick, slip), 99.75);
});

test('triggerIndex + fillPrice: a stop fills ON TOUCH and PAYS THE GAP (engine.py:280-282,291-292)', () => {
  const tick = 0.25, slip = 0.25;
  const buyStop = { side: 1, kind: 'stop', price: 101 };
  assert.equal(R.triggerIndex(buyStop, [100.75, 101, 101.25], tick), 1);      // an ordinary touch
  assert.equal(R.fillPrice(buyStop, 101, tick, slip), 101.25);               // trigger + slip
  assert.equal(R.triggerIndex(buyStop, [100.75, 102], tick), 1);             // gaps straight through 101
  assert.equal(R.fillPrice(buyStop, 102, tick, slip), 102.25);               // fills at the WORSE print, not the trigger
  const sellStop = { side: -1, kind: 'stop', price: 99 };
  assert.equal(R.triggerIndex(sellStop, [99.25, 98.5], tick), 1);            // gaps through 99 down to 98.5
  assert.equal(R.fillPrice(sellStop, 98.5, tick, slip), 98.25);
});

test('triggerIndex + fillPrice: a limit needs 1-TICK PENETRATION and fills AT the limit, no slip (engine.py:283-286,289-290)', () => {
  const tick = 0.25, slip = 0.25;
  const buyLimit = { side: 1, kind: 'limit', price: 100 };
  assert.equal(R.triggerIndex(buyLimit, [100.5, 100], tick), 2);             // touching exactly is NOT enough
  assert.equal(R.triggerIndex(buyLimit, [100.5, 99.75], tick), 1);           // one tick through
  assert.equal(R.fillPrice(buyLimit, 99.75, tick, slip), 100);               // AT the limit, not the penetrated print
  const sellLimit = { side: -1, kind: 'limit', price: 100 };
  assert.equal(R.triggerIndex(sellLimit, [99.5, 100], tick), 2);
  assert.equal(R.triggerIndex(sellLimit, [99.5, 100.25], tick), 1);
  assert.equal(R.fillPrice(sellLimit, 100.25, tick, slip), 100);
});

test('a stop-loss is a plain stop order under the hood: fills on touch, the same law', () => {
  const tick = 0.25, slip = 0.25;
  const sl = { side: -1, kind: 'stop', price: 99, role: 'sl' };   // a long position's SL
  assert.equal(R.triggerIndex(sl, [99.5, 99], tick), 1);
  assert.equal(R.fillPrice(sl, 99, tick, slip), 98.75);
});

test('PracticeSim: $4 commission per round turn per contract (engine.py:97,358)', () => {
  const sim = new R.PracticeSim(0.25, 20, { commissionRt: 4, slippageTicks: 0 });
  sim.enter(1, 'market', null, 2, null, null);
  sim.feed([20000], 1000);
  sim.flatten();
  sim.feed([20010], 2000);
  assert.equal(sim.trades.length, 1);
  assert.equal(sim.trades[0].commission, 8);
});

test('PracticeSim: P&L uses the point value (engine.py:357: gross = side*(fill-entry)*pv*qty)', () => {
  const sim = new R.PracticeSim(0.25, 20, { commissionRt: 4, slippageTicks: 0 });   // NQ: $20/point
  sim.enter(1, 'market', null, 1, null, null);
  sim.feed([20000], 1000);
  sim.flatten();
  sim.feed([20010], 2000);
  const t = sim.trades[0];
  assert.equal(t.entryPrice, 20000);
  assert.equal(t.exitPrice, 20010);
  assert.equal(t.gross, 200);
  assert.equal(t.net, 196);
});

test('PracticeSim: SL/TP bracket a fill, and closing either cancels the sibling (engine.py:338-344,347-351)', () => {
  const costs = { commissionRt: 4, slippageTicks: 0 };
  const sim = new R.PracticeSim(0.25, 20, costs);
  sim.enter(1, 'market', null, 1, 19990, 20020);   // long, SL 19990, TP 20020
  sim.feed([20000], 1000);
  assert.equal(sim.orders.length, 2);              // sl + tp both working
  sim.feed([20020.25], 2000);                      // 1-tick through the TP (a sell limit @ 20020)
  assert.equal(sim.orders.length, 0);              // the SL went with it
  assert.equal(sim.trades[0].exitReason, 'tp');
  assert.equal(sim.trades[0].exitPrice, 20020);    // AT the limit

  const sim2 = new R.PracticeSim(0.25, 20, costs);
  sim2.enter(1, 'market', null, 1, 19990, 20020);
  sim2.feed([20000], 1000);
  sim2.feed([19990], 2000);                        // the SL is a stop: touch is enough
  assert.equal(sim2.orders.length, 0);
  assert.equal(sim2.trades[0].exitReason, 'sl');
  assert.equal(sim2.trades[0].exitPrice, 19990);
});

test('PracticeSim: flatten closes at the market; enter() refuses a second entry while one is pending or filled', () => {
  const costs = { commissionRt: 4, slippageTicks: 0 };
  const sim = new R.PracticeSim(0.25, 20, costs);
  assert.notEqual(sim.enter(1, 'market', null, 1), null);
  assert.equal(sim.enter(-1, 'market', null, 1), null);   // a pending entry already exists
  sim.feed([20000], 1000);
  assert.equal(sim.enter(1, 'market', null, 1), null);    // already in a position
  assert.notEqual(sim.flatten(), null);
  sim.feed([19995], 2000);
  assert.equal(sim.trades.length, 1);
  assert.equal(sim.trades[0].exitReason, 'flat');
  assert.equal(sim.trades[0].net, (19995 - 20000) * 20 - 4);
  assert.equal(sim.position, null);
});

test('PracticeSim.cancel: removes a working order by id, once', () => {
  const sim = new R.PracticeSim(0.25, 20);
  const o = sim.enter(1, 'limit', 19990, 1);
  assert.equal(sim.cancel(o.id), true);
  assert.equal(sim.orders.length, 0);
  assert.equal(sim.cancel(o.id), false);
});

test('PracticeSim: open / realised P&L and trade count feed the P&L strip', () => {
  const costs = { commissionRt: 4, slippageTicks: 0 };
  const sim = new R.PracticeSim(0.25, 20, costs);
  sim.enter(1, 'market', null, 1);
  sim.feed([20000], 1000);
  assert.equal(sim.openPnl(20005), 100);        // +5 pts * $20, unrealised
  assert.equal(sim.openPnl(null), 0);
  sim.flatten();
  sim.feed([20010], 2000);
  assert.equal(sim.openPnl(20010), 0);          // flat again
  assert.equal(sim.realizedPnl(), 196);
  assert.equal(sim.tradeCount(), 1);
});

test('barPrints: a closed OHLC bar as an ordered path -- a bullish bar dips then rallies, a bearish bar rallies then dips; a tick bar is one print', () => {
  assert.deepEqual(R.barPrints({ o: 100, h: 105, l: 98, c: 103 }), [100, 98, 105, 103]);   // c >= o
  assert.deepEqual(R.barPrints({ o: 103, h: 105, l: 98, c: 100 }), [103, 105, 98, 100]);   // c < o
  assert.deepEqual(R.barPrints({ o: 50, h: 50, l: 50, c: 50 }), [50]);                      // a tick bar: o===h===l===c
});

test('BarFeed: a closed bar feeds its whole path once and resets the live tracker for the next bar', () => {
  const sim = new R.PracticeSim(0.25, 20, { commissionRt: 4, slippageTicks: 0 });
  const feed = new R.BarFeed(sim);
  sim.enter(1, 'stop', 105, 1);
  feed.closedBar({ o: 100, h: 106, l: 98, c: 103 }, 1000);
  assert.equal(sim.orders.length, 0);        // 106 >= 105: the stop entry fired
  assert.equal(sim.position.side, 1);
});

test('BarFeed: a live bar chains from the last close; an order placed AFTER an extreme was already seen does not re-fire on it', () => {
  const sim = new R.PracticeSim(0.25, 20, { commissionRt: 4, slippageTicks: 0 });
  const feed = new R.BarFeed(sim);
  feed.liveBar({ o: 100, h: 105, l: 100, c: 102 }, 1000);     // the 105 high is already "seen" by the sim
  const stop = sim.enter(1, 'stop', 106, 1);                  // placed only now, above that already-seen high
  feed.liveBar({ o: 100, h: 105, l: 98, c: 103 }, 2000);      // h UNCHANGED at 105, l extends to 98
  assert.equal(sim.orders.includes(stop), true);              // still working: 105 was not re-fed as if new
  feed.liveBar({ o: 100, h: 107, l: 98, c: 106 }, 3000);      // h genuinely extends past 106 now
  assert.equal(sim.orders.includes(stop), false);             // fires for real this time
});

test('pointValue: USD per 1.00 move, per contract -- homebase/contracts.py, verified for these 8 roots', () => {
  assert.deepEqual([['NQ', 20], ['ES', 50], ['YM', 5], ['RTY', 50], ['GC', 100], ['SI', 5000], ['CL', 1000], ['BTC', 5]]
    .map(([r, v]) => [R.pointValue(r), v]).map(([a]) => a), [20, 50, 5, 50, 100, 5000, 1000, 5]);
  assert.equal(R.pointValue('nq'), 20);     // case-insensitive
  assert.equal(R.pointValue('ZZZZ'), null);
  assert.equal(R.pointValue(), null);
});

test('practiceSession / pushPracticeSession: {date, root, trades[], net}, capped at 200, oldest dropped first', () => {
  const sim = new R.PracticeSim(0.25, 20, { commissionRt: 4, slippageTicks: 0 });
  sim.enter(1, 'market', null, 1);
  sim.feed([20000], 1000);
  sim.flatten();
  sim.feed([20010], 2000);
  const sess = R.practiceSession('2024-03-08', 'NQ', sim);
  assert.equal(sess.date, '2024-03-08');
  assert.equal(sess.root, 'NQ');
  assert.equal(sess.trades.length, 1);
  assert.equal(sess.net, 196);

  let list = [];
  for (let i = 0; i < 205; i++) list = R.pushPracticeSession(list, { i });
  assert.equal(list.length, R.PRACTICE_MAX);
  assert.equal(R.PRACTICE_MAX, 200);
  assert.equal(list[0].i, 5);
  assert.equal(list[199].i, 204);
  assert.deepEqual(R.pushPracticeSession('garbage', { i: 1 }), [{ i: 1 }]);   // a corrupt existing value -> fresh
  assert.equal(R.PRACTICE_KEY, 'hb.practice');
});

test('isolation (2026-09-27 plan, Task 2): the practice path never references the desk client, /api/desk, or an HBTradeUI SEND function', () => {
  const files = {
    'replay.js': new URL('../../homebase/static/charts/replay.js', import.meta.url),
    'replayui.js': new URL('../../homebase/static/charts/replayui.js', import.meta.url),
  };
  // setCellTrade/effectiveMode/disarmPick etc. are fine (local UI state, no network); these are the ones that
  // actually reach the desk (tradeui.js's guardedSend-backed actions) or the desk client / its REST endpoint.
  const forbidden = ['HBDeskClient', '/api/desk', '.placeOrder(', '.symbolAction(', '.flattenAccount(',
    '.cancelOrder(', '.closeLine(', '.moveLine(', 'guardedSend'];
  for (const [name, url] of Object.entries(files)) {
    const text = readFileSync(url, 'utf8');
    for (const bad of forbidden) assert.equal(text.includes(bad), false, `${name} references ${JSON.stringify(bad)}`);
  }
});
