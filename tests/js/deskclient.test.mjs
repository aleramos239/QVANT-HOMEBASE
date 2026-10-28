import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import vm from 'node:vm';

/* deskclient.js's fill toasts (fast-paper): a desk market order can fill BEFORE its POST's answer names the order.
   The real file, loaded in a sandbox: a fake toast root records every toast, fetch answers when the test says so --
   nothing is sent anywhere. */
const require = createRequire(import.meta.url);
const T = require('../../homebase/static/charts/trade.js');
const SRC = readFileSync(new URL('../../homebase/static/charts/deskclient.js', import.meta.url), 'utf8');
// the real thing, loaded into the same sandbox (script order: spring.js loads before deskclient.js in
// charts.html too) -- toast() calls window.HBSpring.materialize()/dematerialize() since the 2026-09-28 feel
// pass, so a fake toast root needs enough of a DOM (.style, add/removeEventListener) for those to run.
const SPRING_SRC = readFileSync(new URL('../../homebase/static/charts/spring.js', import.meta.url), 'utf8');

class El {
  constructor(tag) { this.tagName = tag; this.children = []; this.parent = null; this.className = ''; this.textContent = ''; this.style = {}; }
  setAttribute() {}
  removeAttribute() {}
  addEventListener() {}
  removeEventListener() {}
  append(...n) { for (const c of n) { c.parent = this; this.children.push(c); } }
  prepend(n) { n.parent = this; this.children.unshift(n); }
  remove() { if (this.parent) this.parent.children = this.parent.children.filter((c) => c !== this); }
  get lastChild() { return this.children[this.children.length - 1]; }
  get classList() { return { contains: (c) => this.className.split(' ').includes(c) }; }
}

function load() {
  const root = new El('div'), answers = [];
  const window = { HBTrade: T, HBIcons: { x: '' } };
  const ctx = vm.createContext({
    window, console, setTimeout: () => 0, requestAnimationFrame: () => 0,
    document: { getElementById: (id) => (id === 'toastRoot' ? root : null), createElement: (t) => new El(t) },
    fetch: () => new Promise((resolve) => answers.push(resolve)),
  });
  vm.runInContext(SPRING_SRC, ctx);
  vm.runInContext(SRC, ctx);
  const D = window.HBDeskClient;
  const reply = (orderId) => answers.shift()({ status: 200,
    json: async () => ({ results: { sim041: { ok: true, order_id: orderId, error: null } } }) });
  // newest first, as the page shows them
  const toasts = () => root.children.map((el) => el.children[0].textContent);
  D.onMessage({ type: 'desk', event: 'state', data: { enabled: true, bot: {}, accounts: [{ id: 'sim041', label: 'SIM0000041', env: 'demo' }] } });
  return { D, reply, toasts, window, root, answers };
}
const fill = (id, orderId, price = 30000.25) => ({ type: 'desk', event: 'fill',
  data: { account: 'sim041', fill: { id, order_id: orderId, symbol: 'NQZ6', side: 'Buy', qty: 1, price } } });

test('a desk fill that lands before its order\'s answer is toasted once the answer names the order, and only once', async () => {
  const { D, reply, toasts } = load();
  const sent = D.send('order', { client_id: 'c1', accounts: ['sim041'] });      // in flight...
  D.onMessage(fill(1, 7001));                                                     // ...and already filled
  D.onMessage(fill(2, 9999));                                                     // another page's (or a bot's) order
  assert.deepEqual(toasts(), [], 'not ours yet: no toast');
  reply(7001);
  await sent;
  assert.deepEqual(toasts(), ['…041 · order accepted', 'Filled 1 @ 30,000.25 · …041'], 'one fill toast -- only ours');
  D.onMessage(fill(3, 7001, 30000.5));                                            // a later fill of it: the usual way
  assert.equal(toasts().length, 3);
  assert.equal(toasts()[0], 'Filled 1 @ 30,000.50 · …041');
  const again = D.send('order', { client_id: 'c2', accounts: ['sim041'] });       // an answer never re-toasts a claimed fill
  reply(7001);
  await again;
  assert.deepEqual(toasts().filter((t) => t.startsWith('Filled')).length, 2);
});

test('the order of the answer and the fill does not matter: a fill after the answer is toasted as before', async () => {
  const { D, reply, toasts } = load();
  const sent = D.send('order', { client_id: 'c1', accounts: ['sim041'] });
  reply(8001);
  await sent;
  D.onMessage(fill(1, 8001));
  assert.deepEqual(toasts(), ['Filled 1 @ 30,000.25 · …041', '…041 · order accepted']);
});

test('fills waiting for an answer are bounded: only the last 50 are kept', async () => {
  const { D, reply, toasts } = load();
  const sent = D.send('order', { client_id: 'c1', accounts: ['sim041'] });
  D.onMessage(fill(1, 5000));                                                     // ours -- but pushed out by 50 others
  for (let i = 0; i < 50; i++) D.onMessage(fill(100 + i, 6000 + i));
  reply(5000);
  await sent;
  assert.deepEqual(toasts(), ['…041 · order accepted']);
});

test('only an order / flatten / reverse answer claims a held fill -- a modify or cancel answer never does', async () => {
  const { D, reply, toasts } = load();
  D.onMessage(fill(1, 7001));                                                     // another page's order, partly filled
  D.onMessage(fill(2, 7002));
  for (const [action, id] of [['modify', 7001], ['cancel', 7002]]) {              // this page then moves / cancels it
    const sent = D.send(action, { client_id: action, account: 'sim041', order_id: id });
    reply(id);
    await sent;
  }
  assert.deepEqual(toasts().filter((t) => t.startsWith('Filled')), [], 'no fill claimed by a modify or cancel');
  D.onMessage(fill(3, 7001, 30001.0));                                            // ours from now on: its next fill
  assert.equal(toasts()[0], 'Filled 1 @ 30,001.00 · …041');
  for (const [action, fid, oid] of [['flatten', 21, 9101], ['reverse', 22, 9102]]) {   // these name orders they
    const sent = D.send(action, { client_id: action, accounts: ['sim041'], root: 'NQ' });  // just sent: a fill held
    D.onMessage(fill(fid, oid));                                                            // before the answer is
    assert.equal(toasts().filter((t) => t.startsWith('Filled')).length, fid === 21 ? 1 : 2);   // claimed by it
    reply(oid);
    await sent;
  }
  assert.equal(toasts().filter((t) => t.startsWith('Filled')).length, 3);
});

test('a burst of more than TOAST_MAX toasts in one synchronous tick evicts each excess toast exactly once', () => {
  // TOAST_MAX is 5 (deskclient.js) -- not exported, so this pins the known value the same way the other
  // tests here pin concrete counts. dematerialize's real removal never actually runs in this sandbox
  // (setTimeout/addEventListener are stubs that never fire their callback -- deskclient.js's own header
  // comment), which is exactly the condition that exposed the bug: every evicted toast stays in
  // root.children for the rest of the burst, so a naive re-count of root.children.length on each call
  // would re-select (and hand to dematerialize) the same still-present toasts over and over instead of
  // reaching for genuinely new ones.
  const { D, window, root } = load();
  const calls = new Map();   // element -> how many times HBSpring.dematerialize was handed it
  const realDematerialize = window.HBSpring.dematerialize;
  window.HBSpring.dematerialize = (el, onDone) => { calls.set(el, (calls.get(el) || 0) + 1); return realDematerialize(el, onDone); };
  for (let i = 0; i < 8; i++) D.toast('ok', `msg ${i}`);
  assert.equal(root.children.length, 8, 'nothing physically removed yet -- dematerialize never completes in this sandbox');
  const counts = [...calls.values()];
  assert.equal(counts.length, 3, `8 toasts - TOAST_MAX 5 = 3 should have been handed to dematerialize, got ${counts.length}`);
  assert.ok(counts.every((c) => c === 1), `no toast should be handed to dematerialize more than once: ${counts}`);
  // the 3 oldest (first-sent) are the ones evicted -- msg0/msg1/msg2, never the newest
  const evictedText = [...calls.keys()].map((el) => el.children[0].textContent).sort();
  assert.deepEqual(evictedText, ['msg 0', 'msg 1', 'msg 2']);
});

/* WP5 5.12 (2026-10-27): a modify / cancel the desk refused with "order … is not working" marks that order (its line
   greys, display only); the request itself is the same; the mark lasts until the desk's next word on that account
   (its list is the same view the refusal read: still listed = working again, gone = no line), or a later send on it
   is accepted. */
test('5.12 a "not working" refusal marks the order; the request is unchanged; the mark goes with the order', async () => {
  const sentReq = [];
  const root = new El('div'), answers = [];
  const window = { HBTrade: T, HBIcons: { x: '' } };
  const ctx = vm.createContext({
    window, console, setTimeout: () => 0, requestAnimationFrame: () => 0,
    document: { getElementById: (id) => (id === 'toastRoot' ? root : null), createElement: (t) => new El(t) },
    fetch: (url, init) => { sentReq.push([url, init.method, JSON.parse(init.body)]); return new Promise((resolve) => answers.push(resolve)); },
  });
  vm.runInContext(SPRING_SRC, ctx);
  vm.runInContext(SRC, ctx);
  const D = window.HBDeskClient;
  const state = (orders) => ({ type: 'desk', event: 'state',
    data: { enabled: true, bot: {}, accounts: [{ id: 'sim041', label: 'SIM0000041', env: 'demo', orders }] } });
  const answer = (r) => answers.shift()({ status: 200, json: async () => ({ results: { sim041: r } }) });
  D.onMessage(state([{ order_id: '7', type: 'Stop' }]));
  const body = { client_id: 'c1', account: 'sim041', order_id: '7', price: 29990 };
  const p = D.send('modify', body);
  answer({ ok: false, order_id: null, error: 'order 7 is not working on SIM0000041' });
  assert.deepEqual(await p, { results: { sim041: { ok: false, order_id: null, error: 'order 7 is not working on SIM0000041' } } },
    'send answers what the desk answered, as before');
  assert.deepEqual(sentReq, [['/api/desk/modify', 'POST', body]], 'the same request as before');
  assert.deepEqual([...D.notWorking()], ['sim041:7']);
  const q = D.send('modify', { ...body, client_id: 'c2' });   // a later try the desk accepts: the mark goes
  answer({ ok: true, order_id: '7', error: null });
  await q;
  assert.deepEqual([...D.notWorking()], []);
  const r = D.send('cancel', { client_id: 'c3', account: 'sim041', order_id: '7' });
  answer({ ok: false, order_id: null, error: 'order 7 is not working on SIM0000041' });
  await r;
  assert.deepEqual([...D.notWorking()], ['sim041:7']);
  D.onMessage(state([]));                                      // the desk's list caught up: no order, no line, no mark
  assert.deepEqual([...D.notWorking()], []);
  const other = D.send('modify', { ...body, client_id: 'c4' });   // another refusal reason marks nothing
  answer({ ok: false, order_id: null, error: 'Stop Limit orders can\'t be moved — cancel and place again' });
  await other;
  D.onMessage(state([{ order_id: '7', type: 'Stop' }]));
  assert.deepEqual([...D.notWorking()], []);
  const refuse = async () => {
    const x = D.send('modify', { ...body, client_id: `c${sentReq.length + 1}` });
    answer({ ok: false, order_id: null, error: 'order 7 is not working on SIM0000041' });
    await x;
    assert.deepEqual([...D.notWorking()], ['sim041:7']);
  };
  await refuse();
  D.onMessage(state([{ order_id: '7', type: 'Stop' }]));        // the desk's next word still lists it: working, no mark
  assert.deepEqual([...D.notWorking()], []);
  await refuse();
  D.onMessage({ type: 'desk', event: 'account', data: { id: 'sim099', orders: [] } });   // another account's word: kept
  assert.deepEqual([...D.notWorking()], ['sim041:7']);
  D.onMessage({ type: 'desk', event: 'account', data: { id: 'sim041', label: 'SIM0000041', env: 'demo', orders: [{ order_id: '7', type: 'Stop' }] } });
  assert.deepEqual([...D.notWorking()], [], 'its own account\'s word decides');
  await refuse();
  D.onMessage({ down: 'chart service unreachable' });
  assert.deepEqual([...D.notWorking()], [], 'the desk down: no lines, no marks');
});

/* c-30: a dropped link keeps the last desk state for DISPLAY (heldState / stale); the gate and state stay null, so
   nothing that sends reads it. A new full state clears it. */
const posState = { enabled: true, bot: {}, accounts: [{ id: 'sim041', label: 'SIM0000041', env: 'demo', positions: [{ symbol: 'NQZ6', root: 'NQ', net: 1, avg_price: 30000 }], orders: [] }] };

test('c-30: the desk link drops -- state and gate say down, the last state is held for display, a new state clears it', () => {
  const { D } = load();
  D.onMessage({ type: 'desk', event: 'state', data: posState });
  assert.equal(D.stale, null);
  D.onMessage({ type: 'desk', down: 'no link to the desk' });
  assert.equal(D.state, null, 'the sending side sees nothing');
  assert.equal(D.gate().mode, 'down');
  assert.equal(D.stale, 'desk');
  assert.equal(D.heldState.accounts[0].positions[0].net, 1);
  D.onMessage({ type: 'desk', down: 'no link to the desk' });   // a second word of "down" keeps what was held
  assert.equal(D.heldState.accounts[0].id, 'sim041');
  D.onMessage({ type: 'desk', event: 'state', data: { ...posState, accounts: [] } });
  assert.equal(D.stale, null);
  assert.equal(D.heldState, null);
  assert.equal(D.state.accounts.length, 0);
});

test('c-30: the chart service socket drops -- the lines are marked stale, back when the socket is', () => {
  const { D } = load();
  D.onMessage({ type: 'desk', event: 'state', data: posState });
  D.socket(false);
  assert.equal(D.stale, 'service');
  assert.equal(D.state.accounts.length, 1, 'state untouched: only the mark is new');
  D.socket(true);
  assert.equal(D.stale, null);
  D.socket(false);
  D.onMessage({ type: 'desk', down: 'no link to the desk' });
  assert.equal(D.stale, 'desk', 'the desk word wins');
});

test('cj-5: a refused answer sounds "problem", an accepted one does not; a toast returns its element and can be dismissed', async () => {
  const { D, window, reply, answers } = load();
  const heard = [];
  window.HBSounds = { event: (k) => heard.push(k) };
  const ok = D.send('order', { client_id: 'c1', accounts: ['sim041'] });
  reply(1);
  await ok;
  assert.deepEqual(heard, [], 'an accepted order is silent');
  const bad = D.send('order', { client_id: 'c2', accounts: ['sim041'] });
  answers.shift()({ status: 400, json: async () => ({ detail: 'refused' }) });
  await bad;
  assert.deepEqual(heard, ['problem']);
  const el = D.toast('warn', 'x');
  assert.equal(el.children[0].textContent, 'x');
  D.dismiss(el);
  D.dismiss(el);   // twice is harmless (evict is the one path)
});
