import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* The Desk page's views (homebase/static/index.html), design/apple-pass: Today · Strategy · Activity.
   The headline of the day and a strategy's state are sentences a trader reads before arming and at
   the open, so they must stay true: Armed vs Disarmed, what happens next, who is in a position, and
   a loss with a real minus sign. These helpers only READ the status the desk sends. */
import { HTML } from './deskpage.mjs';
const BLOCK = HTML.slice(HTML.indexOf('/* ===== Desk views'), HTML.indexOf('/* ---- sidebar ---- */'));
const FMT = HTML.slice(HTML.indexOf('const fmt = '), HTML.indexOf('const usd = '));
const SIDE = HTML.slice(HTML.indexOf('function sideKind('), HTML.indexOf('function renderSide('));      // the one rule the headline counts by

function load(ST, stale = false, { machine = null } = {}) {
  const ctx = vm.createContext({ ST, DESK_STALE: stale, labSafe: (f, d) => { try { return f(); } catch (_) { return d; } }, labShadowNet: () => null,
    readinessShown: (r) => r, stratLabel: (n) => n, stratDotCls: () => '', esc: (v) => String(v ?? ''),
    isDemoAcct: (id) => { const a = (ST.accounts || {})[id]; return !!a && (a.env === 'demo' || a.env === 'paper'); },   // book.js's
    deskMachine: () => machine });
  vm.runInContext(FMT + 'const usd = (v) => v == null ? "—" : (v < 0 ? "-$" : "$") + fmt(Math.abs(v));\n' + BLOCK + SIDE +
    '\nconst dayHeadlineOf = dayHeadline; dayHeadline = (names) => dayHeadlineOf(names.length ? names : Object.keys(ST.strategies));      // the page passes every shown name\nglobalThis.api = { dayHeadline, dayCounts, stratState, todayPnl, usdS, specOf, hmin, etMin };', ctx);
  return ctx.api;
}
const strat = (over = {}, extra = {}) => ({
  cfg: { symbol: 'NQ', kind: 'straddle', offset_pts: 5, sl_pts: 5, tp_pts: 15, enabled: true, shadow: false,
    cancel_et: '12:55', flat_et: '15:55', ...over },
  day_status: 'idle', accounts: [], ...extra,
});
const status = (et, over = {}) => ({ armed: true, et_now: et, strategies: { nq930: strat() }, timer: { strategies: {} }, ...over });

test('a disarmed desk says so, and that nothing goes to a broker', () => {
  const [a, b] = load(status('2026-10-01T09:12:00-0400', { armed: false })).dayHeadline([]);
  assert.equal(a, 'Desk OFF.');
  assert.match(b, /journaled only/);
});

test('armed before the open: how long until 9:30 and how many strategies are armed', () => {
  const api = load(status('2026-10-01T09:12:00-0400'));
  assert.deepEqual([...api.dayHeadline([])], ['Opens in 18 min.', '0 strategies trading on 0 accounts · 1 in shadow']);
  const early = load(status('2026-10-01T07:00:00-0400')).dayHeadline([]);
  assert.equal(early[0], 'Opens in 2 h 30 min.');
});

test('a shadow strategy is counted in shadow, never as trading; an off one is not counted', () => {
  const st = status('2026-10-01T09:12:00-0400', { strategies: { a: strat(), b: strat({ shadow: true }), c: strat({ enabled: false }) } });
  assert.equal(load(st).dayHeadline([])[1], '0 strategies trading on 0 accounts · 2 in shadow');
});

test('in session: who is in a position, and a closed session reports the day with a real minus sign', () => {
  const inPos = status('2026-10-01T10:00:00-0400', { strategies: { nq930: strat({}, { day_status: 'live' }) } });
  assert.equal(load(inPos).dayHeadline([])[0], '1 strategy in a position.');
  const closed = status('2026-10-01T16:10:00-0400', { strategies: { nq930: strat({}, {
    day_status: 'done', accounts: [{ date: '2026-10-01', pnl: -210 }] }) } });
  assert.deepEqual([...load(closed).dayHeadline([])], ['Session closed.', 'Today −$210.']);
});

test('a weekend is "Markets are closed" even when armed', () => {
  assert.equal(load(status('2026-10-03T10:00:00-0400')).dayHeadline([])[0], 'Markets are closed.');
});

test('a stale desk says the state is the last known one', () => {
  const [, b] = load(status('2026-10-01T09:12:00-0400'), true).dayHeadline([]);
  assert.match(b, /Last known state/);
});

test('a strategy\'s state, in the words a trader uses', () => {
  const at = (hhmm, s, timer = {}) => load({ ...status(`2026-10-01T${hhmm}:00-0400`), timer: { strategies: timer } }).stratState('nq930', s);
  assert.equal(at('09:00', strat({ enabled: false })), 'Off');
  assert.equal(at('09:31', strat({}, { day_status: 'live' })), 'In position');
  assert.equal(at('09:31', strat({}, { day_status: 'placed' })), 'Orders working');
  assert.equal(at('09:31', strat({}, { day_status: 'placing' })), 'Orders working');
  assert.equal(at('10:30', strat({}, { day_status: 'done' })), 'Done today');
  assert.equal(at('10:30', strat({}, { day_status: 'error' })), 'Needs a look');
  assert.equal(at('09:00', strat()), 'Ready');
  assert.equal(at('11:00', strat()), 'Watching');
  assert.equal(at('16:05', strat()), 'Idle');
  assert.equal(at('10:00', strat(), { nq930: { stage: 'missed' } }), 'Missed today');
});

test('today\'s P&L counts only today\'s rows; none is null, not zero', () => {
  const api = load(status('2026-10-01T16:00:00-0400'));
  assert.equal(api.todayPnl({ accounts: [{ date: '2026-09-30', pnl: 500 }] }), null);
  assert.equal(api.todayPnl({ accounts: [{ date: '2026-10-01', pnl: -210 }, { date: '2026-10-01', pnl: 60 }, { date: '2026-09-30', pnl: 999 }] }), -150);
  assert.equal(api.todayPnl({ accounts: [{ date: '2026-10-01', pnl: null }] }), null);
});

test('money reads with a real minus sign and a plus for a gain; no figure reads as a dash', () => {
  const { usdS } = load(status('2026-10-01T09:00:00-0400'));
  assert.equal(usdS(-210), '−$210');
  assert.equal(usdS(1450), '+$1,450');
  assert.equal(usdS(0), '$0');
  assert.equal(usdS(null), '—');
});

test('the controls on the new views call the same handlers the old cards did', () => {
  for (const h of ["toggleStrat('${name}'", "flattenStrat(${jsArg(name)})"]) assert.ok(HTML.includes(h), `a control no longer calls ${h}`);
});

test('the switch on a row never also opens the strategy', () => {
  assert.match(HTML, /onclick="event\.stopPropagation\(\);\$\{vs \? `toggleSet\(\$\{jsArg\(vs\.id\)\}, \$\{!on\}\)` : `toggleStrat\('\$\{name\}', \$\{!c\.enabled\}\)`\}"/);
  assert.match(HTML, /if\(event\.target===event\.currentTarget&&/, 'a key on the inner switch must not navigate the row');
});

// ---- WP1.9: in session the headline says the day so far in money, LIVE apart from the rest ----
const acct = (env, net) => ({ env, connected: true, day: { day_lock: null, closed_net: net, closes: 1, locked: null } });
test('1.9: in session: "today ±$T (Live ±$X · Demo + paper ±$Y)" from each account\'s closed P&L', () => {
  const st = status('2026-10-01T10:00:00-0400', { accounts: { L1: acct('live', 120), L2: acct('live', -20), D1: acct('demo', 30), P1: acct('paper', -10) } });
  assert.equal(load(st).dayHeadline([])[1], '0 strategies trading on 0 accounts · 1 in shadow · today +$120 (Live +$100 · Demo + paper +$20)');
});

test('1.9: paper only says Paper; a loss has a real minus', () => {
  const st = status('2026-10-01T10:00:00-0400', { accounts: { L1: acct('live', -250.4), P1: acct('paper', 0) } });
  assert.equal(load(st, false, { machine: 'mac' }).dayHeadline([])[1], '0 strategies trading on 0 accounts · 1 in shadow · today −$250 (Live −$250 · Paper $0)');
  assert.equal(load(st, false, { machine: 'server' }).dayHeadline([])[1], '0 strategies trading on 0 accounts · 1 in shadow · today −$250 (Live −$250 · Paper $0)');
});

test('1.9: no account day figures: the line is what it was; out of session it is unchanged too', () => {
  assert.equal(load(status('2026-10-01T10:00:00-0400', { accounts: { L1: { env: 'live' } } })).dayHeadline([])[1], '0 strategies trading on 0 accounts · 1 in shadow');
  const pre = status('2026-10-01T09:12:00-0400', { accounts: { L1: acct('live', 50) } });
  assert.deepEqual([...load(pre).dayHeadline([])], ['Opens in 18 min.', '0 strategies trading on 0 accounts · 1 in shadow · today +$50 (Live +$50)']);
});

// ---- Task 13: the headline counts Trading and Shadow apart, by the sidebar's own rule ----
test('dayHeadline line 2: 2 trading on 2 accounts, 6 in shadow, the money', () => {
  const sh = Object.fromEntries([1, 2, 3, 4, 5, 6].map((i) => ['s' + i, strat()]));
  const st = status('2026-10-01T10:00:00-0400', {
    strategies: { t1: strat(), t2: strat(), off: strat({ enabled: false }), ...sh }, book: { t1: [{ account: 'L1' }, { account: 'D1' }], t2: [{ account: 'L1' }] },
    accounts: { L1: acct('live', 310), D1: acct('demo', 102) } });
  assert.equal(load(st).dayHeadline([])[1], '2 strategies trading on 2 accounts · 6 in shadow · today +$412 (Live +$310 · Demo +$102)');
});
test('dayHeadline line 2: singulars, and no money when no account says', () => {
  const st = status('2026-10-01T10:00:00-0400', { book: { nq930: [{ account: 'L1' }] } });
  assert.equal(load(st).dayHeadline([])[1], '1 strategy trading on 1 account · 0 in shadow');
});
test('dayCounts: a variant set is ONE strategy; a live-but-OFF one still trades', () => {
  const st = status('2026-10-01T10:00:00-0400', { strategies: { a: strat(), b: strat(), c: strat({ enabled: false }, { day_status: 'live' }) },
    book: { a: [{ account: 'L1' }], b: [{ account: 'L2' }], c: [{ account: 'L1' }] }, variants: { sets: [{ id: 'v', name: 'V', members: ['a', 'b'] }] } });
  assert.deepEqual({ ...load(st).dayCounts(['a', 'b', 'c'], st) }, { trading: 2, accounts: 2, shadow: 0 });
});
