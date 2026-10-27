import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* Take turns (account rotation, the owner 2026-10-19): a strategy's Accounts section carries a switch -- each trade to
   ONE booked account, in turn -- and, while on, "Next account: X". Off is the default. Turning it OFF with a live
   account booked asks first (the next trade then goes to every account). */
import { HTML } from './deskpage.mjs';
const between = (a, b) => HTML.slice(HTML.indexOf(a), HTML.indexOf(b));
const ESC = between('const esc = (v) =>', 'async function chartPost(');
const CODE = between('/* Take turns (account rotation', 'function removeAsg(');

function ctx({ rotation = { on: false, next: null }, book = ['a', 'b'], live = false, yes = true, reply, groups } = {}) {
  const sent = [], toasts = [], asked = [];
  const c = vm.createContext({
    ST: { strategies: { s1: { rotation } }, book: { s1: book.map((account) => ({ account, qty: 1 })) }, groups },
    DEMO: false,
    acctShort: (id) => id.toUpperCase(),
    stratLabel: (n) => n,
    isDemoAcct: () => !live,
    isRealAcct: () => live,
    switchBounced: () => false,
    confirmDlg: async (title) => { asked.push(title); return yes; },
    post: async (url, body) => { sent.push([url, body]); return reply || { ok: true, ...body }; },
    refresh: () => {},
    toast: (m) => toasts.push(m),
    answerWhy: (r) => (r && r.ok ? '' : 'the desk refused it'),
  });
  vm.runInContext(ESC + CODE + '\nglobalThis.rotationHtml = rotationHtml; globalThis.setRotation = setRotation;', c);
  return { c, sent, toasts, asked };
}

test('off by default: the switch shows off, no next account', () => {
  const html = ctx().c.rotationHtml('s1');
  assert.match(html, /Take turns/);
  assert.match(html, /aria-checked="false"/);
  assert.doesNotMatch(html, /Next account/);
});

test('on: the switch shows on and names the next account', () => {
  const html = ctx({ rotation: { on: true, next: 'b' } }).c.rotationHtml('s1');
  assert.match(html, /aria-checked="true"/);
  assert.match(html, /Next account: B/);
});

test('one account booked and off: nothing to take turns with, nothing shown', () => {
  assert.equal(ctx({ book: ['a'] }).c.rotationHtml('s1'), '');
  assert.match(ctx({ book: ['a'], rotation: { on: true, next: 'a' } }).c.rotationHtml('s1'), /Take turns/);
});

test('the switch sends {strategy, on} to /api/rotation', async () => {
  const t = ctx();
  await t.c.setRotation('s1', true);
  assert.deepEqual(JSON.parse(JSON.stringify(t.sent)), [['/api/rotation', { strategy: 's1', on: true }]]);
  assert.deepEqual(t.asked, []);
  assert.match(t.toasts[0], /takes turns/);
});

test('turning it off with a live account booked asks first; Cancel sends nothing', async () => {
  const no = ctx({ rotation: { on: true, next: 'a' }, live: true, yes: false });
  await no.c.setRotation('s1', false);
  assert.equal(no.asked.length, 1);
  assert.deepEqual(no.sent, []);
  const demo = ctx({ rotation: { on: true, next: 'a' } });
  await demo.c.setRotation('s1', false);
  assert.deepEqual(demo.asked, []);
  assert.equal(demo.sent.length, 1);
});

test('a refusal is said', async () => {
  const t = ctx({ reply: { ok: false, detail: 'nope' } });
  await t.c.setRotation('s1', true);
  assert.match(t.toasts[0], /NOT changed/);
});

test('the strategy name reaches the handler as one JS string literal', () => {
  const t = ctx();
  t.c.ST.strategies["x');alert(1);('"] = { rotation: {} };
  t.c.ST.book["x');alert(1);('"] = [{ account: 'a' }, { account: 'b' }];
  const html = t.c.rotationHtml("x');alert(1);('");
  const h = html.match(/onclick="([^"]*)"/)[1].replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
  const calls = [], alerts = [];
  new Function('setRotation', 'alert', h)((...a) => calls.push(a), (x) => alerts.push(x));
  assert.deepEqual(alerts, []);
  assert.deepEqual(calls, [["x');alert(1);('", true]]);
});

test('in an ON account cycle the page says the cycle picks the account', () => {
  const groups = { g4: { name: 'apex 300k', on: true, members: ['s1'], next: 'b' } };
  const h = ctx({ rotation: { on: true, next: 'a' }, groups }).c.rotationHtml('s1');
  assert.match(h, /In the apex 300k account cycle: it picks the account \(next: B\)/);
  assert.doesNotMatch(ctx({ groups: { g4: { ...groups.g4, on: false } } }).c.rotationHtml('s1'), /account cycle/);
});
