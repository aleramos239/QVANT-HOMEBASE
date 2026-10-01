import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* The desk page's (homebase/static/index.html, :8850) plain-language pass (2026-09-28, Apple-design
   audit W4), run for real in a vm sandbox:
     - the Activity log reads as sentences ("Connected APEX…048 (login)") instead of
       `event key=value`, with the raw line one hover / click / Raw away, escaped, never blank;
     - a "no signal arrived" (or "no signal today") check for a strategy that could not have fired
       today -- not booked, switched on or added after the 9:30 fire, refused at the fire for having
       no accounts -- is shown as info with the reason, and never turns the page Not ready; when
       the journal can't show that, the alarm stands;
     - the strategy card's labels say what they mean. */
const HTML = readFileSync(new URL('../../homebase/static/index.html', import.meta.url), 'utf8');
const between = (a, b) => HTML.slice(HTML.indexOf(a), HTML.indexOf(b));
const BLOCK = between('/* ---- readiness, as the page shows it (W4) ----', '/* ---- render ---- */');
const HELPERS = between('const fmt = (v, d = 2)', '/* ---- theme ---- */') +
  between('function acctShort(', 'function liveBookingNote(') +
  between('const esc = (v) =>', 'async function chartPost(') +
  between('const killText = ', 'async function doKill(');

function fakeEl() {
  const listeners = {};
  let html = '', sets = 0;
  return {
    listeners, attrs: {},
    get innerHTML() { return html; },
    set innerHTML(v) { html = v; sets += 1; },
    get sets() { return sets; },
    addEventListener(t, f) { (listeners[t] ||= []).push(f); },
    setAttribute(k, v) { this.attrs[k] = String(v); },
  };
}

function load(st = {}) {
  const els = { feed: fakeEl(), feedRawBtn: fakeEl() };
  const ctx = vm.createContext({
    console,
    ST: { accounts: {}, ...st },
    $: (sel) => els[sel.replace(/^#/, '')] || null,
    window: { getSelection: () => '' },
  });
  vm.runInContext(HELPERS + BLOCK + `
    globalThis.api = { activityLine, activityRaw, renderActivity, readinessShown, outOfTodaysFire,
      set ST(v) { ST = v; } };`, ctx);
  return { api: ctx.api, els };
}

const ACCTS = {
  apex2941870000048: { label: 'APEX2941870000048', env: 'live' },
  '1234567049': { label: '1234567049', env: 'live' },
  'lucid-eval-1': { label: 'Lucid Eval #1', env: 'demo' },
};
const line = (row, prev, st = { accounts: ACCTS }) => load(st).api.activityLine(row, prev);

// ---- activity rows -----------------------------------------------------------------------------
test('the brief\'s three examples read as sentences', () => {
  assert.equal(line({ event: 'broker_connected', account: 'apex2941870000048', broker_account: 'APEX2941870000048', mode: 'login' }).text,
    'Connected APEX…048 (login)');
  const prev = { event: 'chart_trading_set', enabled: true, max_order_qty: 10, max_position_qty: 20 };
  assert.equal(line({ event: 'chart_trading_set', enabled: true, max_order_qty: 50, max_position_qty: 100 }, prev).text,
    'Chart-trading limits set to 50 / 100');
  assert.equal(line({ event: 'entry_fill', strategy: 'nq930', account: '1234567049', side: 'Buy', fill: 30726,
    anchor: 30726, fill_vs_anchor: 0, qty_filled: 3, sibling_cancelled: true, sibling_error: null }).text,
    'NQ930 bought 3 @ 30,726 on …049');
});

test('chart trading: a flip, a kill and an unknown previous state each say what happened', () => {
  const prev = { event: 'chart_trading_set', enabled: false, max_order_qty: 10, max_position_qty: 20 };
  assert.equal(line({ event: 'chart_trading_set', enabled: true, max_order_qty: 10, max_position_qty: 20 }, prev).text,
    'Chart trading turned ON');
  assert.deepEqual({ ...line({ event: 'chart_trading_set', enabled: false, cause: 'kill' }) },
    { text: 'Chart trading switched OFF by Kill everything', tone: 'warn' });
  assert.equal(line({ event: 'chart_trading_set', enabled: true, max_order_qty: 5, max_position_qty: 9 }, null).text,
    'Chart trading ON · limits 5 / 9');
});

test('money rows carry their prices, sizes, accounts and P&L; failures are marked', () => {
  assert.deepEqual({ ...line({ event: 'exit_fill', strategy: 'nq930', account: '1234567049', reason: 'tp', fill: 30741.25, pnl: 885 }) },
    { text: 'NQ930 exited on …049 at the target @ 30,741.25, +$885.00', tone: 'pos' });
  assert.deepEqual({ ...line({ event: 'exit_fill', strategy: 'nq930', account: '1234567049', reason: 'sl', fill: 30721, pnl: -300 }) },
    { text: 'NQ930 exited on …049 at the stop @ 30,721, -$300.00', tone: 'neg' });
  assert.equal(line({ event: 'placed', strategy: 'nq930', account: 'lucid-eval-1', source: 'timer', upper: 30726.25,
    lower: 30706.25, qty: 3, place_ms: 412 }).text,
    'NQ930 placed on Lucid Eval #1: Buy stop 30,726.25 / Sell stop 30,706.25 × 3 (412 ms)');
  const rej = line({ event: 'place_failed', strategy: 'nq930', account: '1234567049', leg: 'upper', error: 'Access is denied' });
  assert.deepEqual({ ...rej }, { text: 'NQ930 order REJECTED on …049 — upper leg — Access is denied', tone: 'neg' });
  const sib = line({ event: 'entry_fill', strategy: 'nq930', account: '1234567049', side: 'Sell', fill: 30706, qty_filled: 3,
    fill_vs_anchor: -0.25, sibling_cancelled: false, sibling_error: 'timeout' });
  assert.equal(sib.tone, 'neg');
  assert.match(sib.text, /^NQ930 sold 3 @ 30,706 on …049 \(-0\.25 vs trigger\) — the other side was NOT cancelled: timeout$/);
  const kill = line({ event: 'kill_switch', results: { apex2941870000048: { cancel_all: { ok: true }, flatten_all: { ok: false, error: 'x' } },
    b: { cancel_all: { ok: true }, flatten_all: { ok: true } } } });
  assert.deepEqual({ ...kill }, { text: 'Kill everything — FAILED on APEX…048 (FLATTEN FAILED: x); desk disarmed', tone: 'neg' });
  assert.deepEqual({ ...line({ event: 'kill_switch', results: { b: { cancel_all: { ok: true }, flatten_all: { ok: true } } } }) },
    { text: 'Kill everything — 1 account cancelled and flattened, desk disarmed', tone: 'warn' });
});

test('the desk\'s own events read plainly: arm, book, toggle, timer, refusals', () => {
  assert.equal(line({ event: 'armed_toggled', armed: true }).text, 'Desk ARMED — signals place real orders');
  assert.equal(line({ event: 'book_updated', strategy: 'nq930_1030', assignments: [{ account: '1234567049', qty: 3 }] }).text,
    'NQ930_1030 booked on …049 ×3');
  assert.equal(line({ event: 'book_updated', strategy: 'nq930', assignments: [] }).text, 'NQ930 unbooked from every account');
  assert.equal(line({ event: 'strategy_toggled', strategy: 'nq930', enabled: false, cause: 'manual_flatten' }).text,
    'NQ930 switched OFF (Flatten & turn off)');
  assert.equal(line({ event: 'timer_fired', strategy: 'nq930', anchor: 30716.25, result: true, note: 'disarmed — journaled only' }).text,
    'NQ930 fired at 9:30 — anchor 30,716.25 · disarmed — journaled only');
  assert.deepEqual({ ...line({ event: 'alert_refused', strategy: 'nq930', reason: 'no_assignments', source: 'timer' }) },
    { text: 'NQ930 signal refused — no accounts are booked', tone: 'warn' });
  assert.equal(line({ event: 'timer_gate', strategy: 'nq930', gate: false, adx: 14.2, bars: 119 }).text,
    'NQ930 gate closed — chop day (ADX 14.2), no trade today');
});

test('an event the table does not know, or a row it cannot read, still reads as words', () => {
  assert.deepEqual({ ...line({ event: 'brand_new_thing', strategy: 'nq930', account: '1234567049' }) },
    { text: 'Brand new thing — NQ930 on …049', tone: '' });
  assert.equal(line({ event: 'weird_error' }).tone, 'neg');
  const broken = line({ event: 'book_updated', strategy: 'nq930', assignments: [null] });   // the formatter throws
  assert.equal(broken.text, 'Book updated — NQ930');
});

test('the raw line is kept exactly as the old log showed it', () => {
  const { api } = load();
  assert.equal(api.activityRaw({ ts: 1, et: 'x', event: 'broker_connected', account: 'a1', mode: 'login', extra: { k: 1 } }),
    'broker_connected  account=a1  mode=login  extra={"k":1}');
});

test('rows render escaped, with the raw line on hover, and open to it on a click', () => {
  const { api, els } = load({ accounts: ACCTS });
  const journal = [
    { ts: 2, et: '2026-09-28T09:30:01-04:00', event: 'place_failed', strategy: 'nq930', account: '1234567049', error: '<img src=x onerror=alert(1)>' },
    { ts: 1, et: '2026-09-28T09:20:04-04:00', event: 'broker_connected', account: 'apex2941870000048', mode: 'login' },
  ];
  api.renderActivity(journal);
  const html = els.feed.innerHTML;
  assert.doesNotMatch(html, /<img/);
  assert.match(html, /&lt;img src=x onerror=alert\(1\)&gt;/);
  assert.match(html, /<span class="t">09:30:01<\/span><span class="h neg">NQ930 order REJECTED on …049 — /);
  assert.match(html, /title="broker_connected  account=apex2941870000048  mode=login"/);
  assert.doesNotMatch(html, /class="raw"/, 'closed by default');
  const row = { getAttribute: () => '1|2026-09-28T09:20:04-04:00|broker_connected|apex2941870000048' };
  els.feed.listeners.click[0]({ target: { closest: () => row } });
  assert.match(els.feed.innerHTML, /<span class="raw">broker_connected  account=apex2941870000048  mode=login<\/span>/);
  assert.equal((els.feed.innerHTML.match(/class="raw"/g) || []).length, 1, 'only the clicked row opens');
  els.feed.listeners.click[0]({ target: { closest: () => row } });
  assert.doesNotMatch(els.feed.innerHTML, /class="raw"/, 'a second click closes it');
});

test('Raw shows every row\'s raw line, and an unchanged journal is never re-rendered', () => {
  const { api, els } = load({ accounts: ACCTS });
  const journal = [{ ts: 1, et: '2026-09-28T09:20:04-04:00', event: 'armed_toggled', armed: false },
                   { ts: 0, et: '2026-09-28T09:10:00-04:00', event: 'feed_started', watching: ['NQ:1'] }];
  api.renderActivity(journal);
  const n = els.feed.sets;
  api.renderActivity(JSON.parse(JSON.stringify(journal)));
  assert.equal(els.feed.sets, n, 'the same rows again: the DOM (and a hovered tooltip) is left alone');
  els.feedRawBtn.listeners.click[0]();
  assert.equal(els.feedRawBtn.attrs['aria-pressed'], 'true');
  assert.equal((els.feed.innerHTML.match(/class="raw"/g) || []).length, 2);
  assert.match(HTML, /id="feedRawBtn" aria-pressed="false"/);
});

test('an empty or missing journal says it is waiting', () => {
  const { api, els } = load();
  api.renderActivity(undefined);
  assert.match(els.feed.innerHTML, /Waiting for events…/);
});

// ---- "no signal arrived" for a strategy that could not have fired ------------------------------
const NOSIG = { level: 'bad', label: 'nq930_1030', detail: 'no signal arrived — this strategy trades every day' };
const OTHER = { level: 'ok', label: 'Price feed', detail: 'live bars flowing' };
function state({ book = { nq930_1030: [{ account: '1234567049', qty: 3 }] }, journal = [], checks = [NOSIG, OTHER] } = {}) {
  return { et_now: '2026-09-28T14:30:00-04:00', accounts: ACCTS, book,
    strategies: { nq930_1030: { cfg: { enabled: true } }, nq930: { cfg: { enabled: true } } },
    journal, readiness: { ready: !checks.some((c) => c.level === 'bad'), checks } };
}
const shown = (st) => { const { api } = load(st); return api.readinessShown(st.readiness, st); };
const row = (et, event, extra = {}) => ({ ts: 0, et: `2026-09-28T${et}-04:00`, event, ...extra });

test('not booked on any account: info with the reason, and the page is ready again', () => {
  const r = shown(state({ book: {} }));
  assert.equal(r.checks[0].level, 'info');
  assert.equal(r.checks[0].detail, 'not booked on any account — nothing could fire');
  assert.equal(r.ready, true);
});

test('switched on after the 9:30 fire: info; switched on before it: the alarm stands', () => {
  const after = shown(state({ journal: [row('10:05:00', 'strategy_toggled', { strategy: 'nq930_1030', enabled: true })] }));
  assert.equal(after.checks[0].level, 'info');
  assert.match(after.checks[0].detail, /switched on after today's 9:30 fire/);
  const before = shown(state({ journal: [row('09:05:00', 'strategy_toggled', { strategy: 'nq930_1030', enabled: true })] }));
  assert.equal(before.checks[0].level, 'bad');
  assert.equal(before.ready, false);
  // on at the fire (its first flip after 9:30 is OFF), then back on: the missed fire was real
  const offOn = shown(state({ journal: [row('10:10:00', 'strategy_toggled', { strategy: 'nq930_1030', enabled: true }),
                                         row('10:00:00', 'strategy_toggled', { strategy: 'nq930_1030', enabled: false })] }));
  assert.equal(offOn.checks[0].level, 'bad');
  // off before the fire, on after it
  const offBefore = shown(state({ journal: [row('10:10:00', 'strategy_toggled', { strategy: 'nq930_1030', enabled: true }),
                                             row('09:00:00', 'strategy_toggled', { strategy: 'nq930_1030', enabled: false })] }));
  assert.equal(offBefore.checks[0].level, 'info');
});

test('the fire itself refused it for having no accounts: info (booked since); a dry-run test fire proves nothing', () => {
  const fired = shown(state({ journal: [row('09:30:00', 'alert_refused', { strategy: 'nq930_1030', reason: 'no_assignments', source: 'timer' })] }));
  assert.equal(fired.checks[0].level, 'info');
  assert.match(fired.checks[0].detail, /not booked \(or was off\) at today's 9:30 fire/);
  const test_ = shown(state({ journal: [row('09:31:00', 'alert_refused', { strategy: 'nq930_1030', reason: 'no_assignments', source: 'test' })] }));
  assert.equal(test_.checks[0].level, 'bad');
});

test('added after the fire (the timer first saw it after its window, on a day the desk did fire): info', () => {
  const added = [
    row('14:19:15', 'timer_missed', { strategy: 'nq930_1030', window_end: '09:45' }),
    row('14:19:15', 'timer_missed', { strategy: 'nq930', window_end: '09:45' }),
    row('09:30:00', 'timer_fired', { strategy: 'nq930', anchor: 30716.25, result: true }),
    row('09:20:00', 'broker_connected', { account: '1234567049', mode: 'login' }),
  ];
  const r = shown(state({ journal: added }));
  assert.equal(r.checks[0].level, 'info');
  assert.match(r.checks[0].detail, /added after today's 9:30 fire/);
  // the journal in view does not reach back past 9:30: nothing is proven, the alarm stands
  assert.equal(shown(state({ journal: added.slice(0, 3).map((x) => ({ ...x, et: x.et.replace('09:30:00', '09:31:00') })) })).checks[0].level, 'bad');
  // the desk did not fire anything at 9:30 (it may have been down): the alarm stands
  assert.equal(shown(state({ journal: [added[0], added[3]] })).checks[0].level, 'bad');
  // it WAS in the fire (the timer staged it): the alarm stands
  assert.equal(shown(state({ journal: [added[0], added[2], row('09:28:31', 'prestage_rtt', { strategy: 'nq930_1030' }), added[3]] })).checks[0].level, 'bad');
});

test('every other check is untouched: a real red stays red, and a gated amber is judged the same way', () => {
  const real = { level: 'bad', label: 'APEX…048', detail: 'not connected' };
  const r = shown(state({ book: {}, checks: [NOSIG, real] }));
  assert.equal(r.checks[0].level, 'info');
  assert.deepEqual({ ...r.checks[1] }, real);
  assert.equal(r.ready, false, 'still not ready: something else is really wrong');
  const gated = { level: 'warn', label: 'nq930_1030', detail: 'no signal today — gated day (expected) or the pipe is broken' };
  assert.equal(shown(state({ book: {}, checks: [gated] })).checks[0].level, 'info');
  const labelNotAStrategy = { level: 'bad', label: 'Mode', detail: 'no signal arrived — this strategy trades every day' };
  assert.equal(shown(state({ book: {}, checks: [labelNotAStrategy] })).checks[0].level, 'bad');
  const same = state();
  assert.equal(shown(same), same.readiness, 'nothing to change: the desk\'s own object, as is');
});

test('the bulb, the Not-ready strip and the checks list all read the shown readiness', () => {
  const render = between('function render() {', 'async function refresh()');
  assert.match(render, /const r = readinessShown\(s\.readiness, s\);/);
  assert.match(render, /renderBulb\(r\);/);
  assert.match(between('function renderChecks()', 'function openChecks()'), /readinessShown\(ST\.readiness, ST\)/);
});

// ---- labels ------------------------------------------------------------------------------------
test('the card labels say what they mean', () => {
  assert.match(HTML, /No live trades yet/);   // the strategy page says it plainly when there is nothing to show
  assert.doesNotMatch(HTML, /this strip earns itself/);
  assert.match(HTML, />Flatten &amp; turn off<\/button>/);
  assert.doesNotMatch(HTML, /Flatten · off/);
  assert.match(between('async function flattenStrat(', '/* ---- accounts popup ---- */'), /"Flatten & turn off", true/);
});

// ---- a failed flatten or cancel never reads as success (review M3) -------------------------------
test('a flatten whose steps say it failed reads FLATTEN FAILED, with the reason, in red', () => {
  const unread = line({ event: 'manual_flatten', strategy: 'nq930', results: {
    '1234567049': ['position unreadable (timeout) — stop/target left working'] } });
  assert.deepEqual({ ...unread }, { text: 'NQ930 flatten — FLATTEN FAILED on …049 — position unreadable (timeout) — ' +
    'stop/target left working', tone: 'neg' });
  const refused = line({ event: 'manual_flatten', strategy: 'nq930', results: {
    '1234567049': ['market Sell 3: Access is denied', 'not flat — stop/target left working'] } });
  assert.equal(refused.text, 'NQ930 flatten — FLATTEN FAILED on …049 — market Sell 3 refused: Access is denied; ' +
    'not flat — stop/target left working');
  assert.equal(refused.tone, 'neg');
});

test('a flatten that went out but left an order behind reads CANCEL FAILED; a clean one reads flattened', () => {
  const leftover = line({ event: 'manual_flatten', strategy: 'nq930', results: {
    '1234567049': ['market Sell 3: ok', 'cancel 123: ok', 'cancel 124: order not found'],
    'lucid-eval-1': ['cancel 7: ok'] } });
  assert.deepEqual({ ...leftover }, { text: 'NQ930 flatten — CANCEL FAILED on …049 — order 124: order not found', tone: 'neg' });
  assert.deepEqual({ ...line({ event: 'manual_flatten', strategy: 'nq930', results: {
    '1234567049': ['market Sell 3: ok', 'cancel 123: ok'] } }) }, { text: 'NQ930 flattened on 1 account', tone: '' });
  assert.equal(line({ event: 'manual_flatten', strategy: 'nq930', results: {} }).text, 'NQ930 flatten — nothing of its was open today');
  const odd = line({ event: 'manual_flatten', strategy: 'nq930', results: { '1234567049': { weird: true } } });
  assert.deepEqual({ ...odd }, { text: 'NQ930 flatten — CHECK IT on …049 — its result is unreadable', tone: 'neg' },
    'a result it cannot read is never called a success');
});

test('the clock, the kill and the emergency paths read their steps too', () => {
  const eod = line({ event: 'clock_flat', strategy: 'nq930', account: '1234567049', actions: ['market Sell 3: ok', 'cancel 9: rejected'] });
  assert.deepEqual({ ...eod }, { text: 'NQ930 flattened on …049 at the end-of-day time · CANCEL FAILED — order 9: rejected', tone: 'neg' });
  assert.deepEqual({ ...line({ event: 'clock_flat', strategy: 'nq930', account: '1234567049', actions: ['market Sell 3: ok'] }) },
    { text: 'NQ930 flattened on …049 at the end-of-day time', tone: '' });
  assert.equal(line({ event: 'clock_flat_failed', strategy: 'nq930', account: '1234567049',
    actions: ['position unreadable (x) — stop/target left working'] }).text,
    'NQ930 end-of-day FLATTEN FAILED on …049 — position unreadable (x) — stop/target left working');
  assert.equal(line({ event: 'killed_run_entries_cancelled', strategy: 'nq930', account: '1234567049',
    actions: ['cancel 5: ok', 'cancel 6: timeout'] }).text, "NQ930 on …049: the killed run's entries — CANCEL FAILED — order 6: timeout");
  const killed = line({ event: 'strategy_killed', strategy: 'nq930', results: {
    '1234567049': { ok: false, actions: ['cancel entry 5: ok', 'check it — position unreadable (x); position not fully attributed; stops left working'] },
    'lucid-eval-1': { ok: true, note: 'nothing to do' } } });
  assert.equal(killed.tone, 'neg');
  assert.match(killed.text, /^NQ930 killed for today — CHECK …049: CHECK IT — check it — position unreadable/);
  const emergency = line({ event: 'both_filled_emergency', strategy: 'nq930', account: '1234567049',
    actions: ['market Buy 3: Access is denied', 'not flat — stop/target left working'] });
  assert.match(emergency.text, /emergency flatten · FLATTEN FAILED — market Buy 3 refused: Access is denied/);
  assert.match(line({ event: 'both_filled_emergency', strategy: 'nq930', account: '1234567049',
    actions: ['market Buy 3: ok', 'cancel 1: ok'] }).text, /emergency flatten done$/);
  assert.deepEqual({ ...line({ event: 'sibling_cancel_retry', strategy: 'nq930', account: '1234567049', ok: false, error: 'x' }) },
    { text: 'NQ930: CANCEL FAILED on …049 — the other entry is still working: x', tone: 'neg' });
});

test('the chart\'s own flatten / cancel lead with FAILED when they fail', () => {
  assert.deepEqual({ ...line({ event: 'manual_flatten', source: 'chart', account: '1234567049', contract: 'NQZ6', ok: false, error: 'timeout' }) },
    { text: 'Chart: FLATTEN FAILED on …049 (NQZ6) — timeout', tone: 'neg' });
  assert.deepEqual({ ...line({ event: 'manual_cancel', source: 'chart', scope: 'order', account: '1234567049', contract: 'NQZ6', ok: false, error: 'gone' }) },
    { text: 'Chart: CANCEL FAILED on …049 (NQZ6) — gone', tone: 'neg' });
  assert.equal(line({ event: 'manual_flatten', source: 'chart', account: '1234567049', contract: 'NQZ6', ok: true }).text,
    'Chart: flattened NQZ6 on …049');
});

test('a step reads as done only in one of the engine\'s OK forms; a multi-line error or an unknown step never passes (second review)', () => {
  const multi = line({ event: 'manual_flatten', strategy: 'nq930', results: {
    '1234567049': ['market Sell 3: ok', 'cancel 11: Client error 404\nFor more information check: https://x'] } });
  assert.deepEqual({ ...multi }, { text: 'NQ930 flatten — CANCEL FAILED on …049 — order 11: Client error 404 For more information check: https://x',
    tone: 'neg' });
  const eod = line({ event: 'clock_flat', strategy: 'nq930', account: '1234567049', actions: ['market Buy 2: ok', 'cancel entry 12: rejected\nsecond line'] });
  assert.deepEqual({ ...eod }, { text: 'NQ930 flattened on …049 at the end-of-day time · CANCEL FAILED — order 12: rejected second line', tone: 'neg' });
  const unknown = line({ event: 'manual_flatten', strategy: 'nq930', results: { '1234567049': ['market Sell 3: ok', 'something new happened'] } });
  assert.deepEqual({ ...unknown }, { text: 'NQ930 flatten — CHECK IT on …049 — something new happened', tone: 'neg' });
  const refusedMulti = line({ event: 'manual_flatten', strategy: 'nq930', results: { '1234567049': ['market Sell 3: rejected\nby risk', 'not flat — stop/target left working'] } });
  assert.match(refusedMulti.text, /FLATTEN FAILED on …049 — market Sell 3 refused: rejected by risk; not flat/);
  const flatAlready = line({ event: 'manual_flatten', strategy: 'nq930', results: { '1234567049': ['the account is already flat', 'cancel entry 5: ok'] } });
  assert.deepEqual({ ...flatAlready }, { text: 'NQ930 flattened on 1 account', tone: '' });
});

test("a kill step the engine reports as a no-op ('already killed — nothing to do') reads as done", () => {
  assert.deepEqual({ ...line({ event: 'manual_flatten', strategy: 'nq930', results: { '1234567049': ['already killed — nothing to do'] } }) },
    { text: 'NQ930 flattened on 1 account', tone: '' });
});
