import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* paperclient.js is the PAPER account's only way out of the page (2026-09-27 accounts/paper plan, Task 2): it must
   never know the desk. Loaded for real in a sandbox whose fetch records every request -- nothing is sent anywhere. */
const SRC = readFileSync(new URL('../../homebase/static/charts/paperclient.js', import.meta.url), 'utf8');

function load() {
  const fetched = [];
  const window = {};
  const ctx = vm.createContext({
    window, console,
    fetch: async (url, opts) => {
      fetched.push({ url, opts });
      return { status: 200, json: async () => ({ results: { paper: { ok: true, order_id: '7', error: null } } }) };
    },
  });
  vm.runInContext(SRC, ctx);
  return { P: window.HBPaperClient, fetched };
}

test('the paper send path has no desk client reference and no desk URL', () => {
  const code = SRC.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/.*$/gm, '');   // comments may say "desk"
  assert.doesNotMatch(code, /HBDeskClient/);
  assert.doesNotMatch(code, /\/api\/desk/);
  assert.doesNotMatch(code, /\bdesk\b/i, 'no code path in this file names the desk at all');
  for (const m of code.matchAll(/fetch\(\s*`([^`]*)`/g)) assert.match(m[1], /^\/api\/paper\//);
});

test('send posts JSON to /api/paper/{action} only, and refuses anything that is not a book action unsent', async () => {
  const { P, fetched } = load();
  const body = { client_id: 'c1', accounts: ['paper'], root: 'NQ', side: 'Buy', qty: 1, type: 'Market' };
  const r = await P.send('order', body);
  assert.equal(r.status, 200);
  assert.equal(fetched.length, 1);
  assert.equal(fetched[0].url, '/api/paper/order');
  assert.equal(fetched[0].opts.method, 'POST');
  assert.deepEqual(JSON.parse(fetched[0].opts.body), body);
  const k = await P.send('bot-kill', { client_id: 'k', strategy: 'nq930' });
  assert.equal(k.status, 0);
  assert.equal(fetched.length, 1, 'a Kill never leaves through the paper client');
  for (const a of ['modify', 'cancel', 'exits', 'cancel-symbol', 'flatten', 'reverse']) await P.send(a, {});
  assert.deepEqual(fetched.map((f) => f.url), ['/api/paper/order', '/api/paper/modify', '/api/paper/cancel',
    '/api/paper/exits', '/api/paper/cancel-symbol', '/api/paper/flatten', '/api/paper/reverse']);
});

test('the book push keeps every paper account, and only a new fill of our own order is announced', async () => {
  const { P } = load();
  const seen = [];
  P.onFill((f) => seen.push([f.account, f.id]));
  const acc = (id, fills) => ({ id, env: 'paper', fills });
  const push = (list) => P.onBook({ type: 'paperbook', accounts: list, limits: { max_order_qty: 10 } });
  push([acc('paper', [{ id: 1, order_id: '3' }]), acc('paper-2', [{ id: 1, order_id: '7' }])]);   // history: never announced
  assert.deepEqual(P.accounts().map((a) => a.id), ['paper', 'paper-2']);
  assert.deepEqual(P.limits(), { max_order_qty: 10 });
  await P.send('order', {});                                  // the page places order 7 (on "paper", per the fake answer)
  push([acc('paper', [{ id: 1, order_id: '3' }, { id: 2, order_id: '7' }]),
    acc('paper-2', [{ id: 1, order_id: '7' }, { id: 2, order_id: '7' }])]);   // paper-2's order 7 is not ours
  assert.deepEqual(seen, [['paper', 2]]);
  push([acc('paper', []), { id: 'sim047', env: 'demo' }, { id: 'paper:gc_nfpcpi' }]);   // only paper ACCOUNT ids are kept
  assert.deepEqual(P.accounts().map((a) => a.id), ['paper']);
});

test('createAccount posts a name and a starting balance to the chart service\'s own route', async () => {
  const { P, fetched } = load();
  await P.createAccount('Scalps', 25000);
  assert.equal(fetched[0].url, '/api/paper/accounts/create');
  assert.deepEqual(JSON.parse(fetched[0].opts.body), { name: 'Scalps', start_balance: 25000 });
});
