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
  return { D, reply, toasts };
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
