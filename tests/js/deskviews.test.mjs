import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* The Desk page's views (homebase/static/index.html), design/apple-pass: Today · Strategy · Activity.
   The headline of the day and a strategy's state are sentences a trader reads before arming and at
   the open, so they must stay true: Armed vs Disarmed, what happens next, who is in a position, and
   a loss with a real minus sign. These helpers only READ the status the desk sends. */
const HTML = readFileSync(new URL('../../homebase/static/index.html', import.meta.url), 'utf8');
const BLOCK = HTML.slice(HTML.indexOf('/* ===== Desk views'), HTML.indexOf('/* ---- sidebar ---- */'));
const FMT = HTML.slice(HTML.indexOf('const fmt = '), HTML.indexOf('const usd = '));

function load(ST, stale = false) {
  const ctx = vm.createContext({ ST, DESK_STALE: stale, esc: (v) => String(v ?? '') });
  vm.runInContext(FMT + 'const usd = (v) => v == null ? "—" : (v < 0 ? "-$" : "$") + fmt(Math.abs(v));\n' + BLOCK +
    '\nglobalThis.api = { dayHeadline, stratState, todayPnl, usdS, specOf, hmin, etMin };', ctx);
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
  assert.equal(a, 'Disarmed.');
  assert.match(b, /journaled only/);
});

test('armed before the open: how long until 9:30 and how many strategies are armed', () => {
  const api = load(status('2026-10-01T09:12:00-0400'));
  assert.deepEqual([...api.dayHeadline([])], ['Opens in 18 min.', '1 strategy armed.']);
  const early = load(status('2026-10-01T07:00:00-0400')).dayHeadline([]);
  assert.equal(early[0], 'Opens in 2 h 30 min.');
});

test('a shadow strategy is not counted as armed; an off one neither', () => {
  const st = status('2026-10-01T09:12:00-0400', { strategies: { a: strat(), b: strat({ shadow: true }), c: strat({ enabled: false }) } });
  assert.equal(load(st).dayHeadline([])[1], '1 strategy armed.');
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
  for (const h of ["toggleStrat('${name}'", "flattenStrat('${name}')", "testFire('${name}')", "openRes('${name}')",
    "openLive('${name}')", "openPine('${name}')", "toggleAsgMenu('${name}')", "pickAsg('${name}'"]) {
    assert.ok(HTML.includes(h), `a control no longer calls ${h}`);
  }
  assert.match(HTML, /acctRow\(a\.account, \{qty: a\.qty, strategy: name\}\)/);
});

test('the switch on a row never also opens the strategy', () => {
  assert.match(HTML, /onclick="event\.stopPropagation\(\);toggleStrat\('\$\{name\}', \$\{!c\.enabled\}\)"/);
  assert.match(HTML, /if\(event\.target===event\.currentTarget&&/, 'a key on the inner switch must not navigate the row');
});
