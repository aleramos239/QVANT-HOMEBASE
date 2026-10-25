import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* Account cycle (the owner, 2026-10-25): a Desk group's page carries the cycle -- a switch, the accounts to tick, the risk
   per trade and the most per trade -- and, while on, "Next account: X". Turning it ON asks first, naming LIVE accounts. */
const HTML = readFileSync(new URL('../../homebase/static/index.html', import.meta.url), 'utf8');
const between = (a, b) => HTML.slice(HTML.indexOf(a), HTML.indexOf(b));
const ESC = between('const esc = (v) =>', 'async function chartPost(');
const CODE = between('/* Account cycle (the owner, 2026-10-25)', 'async function deleteGroup(');

function ctx({ cyc = null, live = false, yes = true, reply, ticked = ['a'], risk = '1000', minis = '17' } = {}) {
  const sent = [], toasts = [], asked = [];
  const el = (cls) => ({ value: cls === '.cyc-risk' ? risk : minis });
  const boxes = ['a', 'b'].map((acct) => ({ checked: ticked.includes(acct), dataset: { acct } }));
  const c = vm.createContext({
    ST: { strategies: { lab_x: { cfg: { kind: 'lab' } }, nq930: { cfg: { kind: 'straddle' } } },
          accounts: { a: {}, b: {} }, book: { lab_x: [{ account: 'a', qty: 1 }] }, groups: cyc ? { g1: cyc } : {} },
    DEMO: false, FREEZE: false,
    groupOf: (id) => ({ id, name: 'Apex', members: ['lab_x', 'nq930'] }),
    document: { querySelector: () => ({ querySelector: el, querySelectorAll: () => boxes }) },
    jsArg: (v) => JSON.stringify(v),
    acctShort: (id) => id.toUpperCase(),
    stratLabel: (n) => n,
    isDemoAcct: () => !live,
    switchBounced: () => false,
    confirmDlg: async (title, body) => { asked.push(body); return yes; },
    post: async (url, body) => { sent.push([url, body]); return reply || { ok: true, ...body }; },
    refresh: () => {},
    toast: (m) => toasts.push(m),
    answerWhy: (r) => (r && r.ok ? '' : 'the desk refused it'),
  });
  vm.runInContext(ESC + CODE + '\nglobalThis.cycleHtml = cycleHtml; globalThis.setCycle = setCycle;', c);
  return { c, sent, toasts, asked };
}

test('off: a switch, every account to tick, no next account', () => {
  const { c } = ctx();
  const h = c.cycleHtml({ id: 'g1', members: ['lab_x', 'nq930'] });
  assert.match(h, /Account cycle/);
  assert.match(h, /aria-checked="false"/);
  assert.equal((h.match(/class="cyc-acct"/g) || []).length, 2);
  assert.doesNotMatch(h, /Next account/);
});

test('on: next account, ticked accounts, a member not booked on one is named', () => {
  const cyc = { on: true, next: 'b', accounts: ['a', 'b'], members: ['lab_x'], risk_usd: 1000, max_minis: 17 };
  const h = ctx({ cyc }).c.cycleHtml({ id: 'g1', members: ['lab_x'] });
  assert.match(h, /aria-checked="true"/);
  assert.match(h, /Next account: B/);
  assert.match(h, /lab_x is not booked on B/);
});

test('turning it on asks first, naming live accounts, and sends the form', async () => {
  const { c, sent, asked } = ctx({ live: true, ticked: ['a', 'b'] });
  await c.setCycle('g1', true);
  assert.match(asked[0], /2 LIVE/);
  assert.match(asked[0], /\$1,000 at risk/);
  assert.deepEqual(JSON.parse(JSON.stringify(sent[0][1])), { id: 'g1', name: 'Apex', members: ['lab_x'], accounts: ['a', 'b'],
                                                              risk_usd: 1000, max_minis: 17, on: true });
});

test('a no at the question sends nothing', async () => {
  const { c, sent } = ctx({ yes: false });
  await c.setCycle('g1', true);
  assert.equal(sent.length, 0);
});

test('a refusal is said', async () => {
  const { c, toasts } = ctx({ reply: { detail: 'nope' } });
  await c.setCycle('g1', false);
  assert.match(toasts[0], /NOT changed/);
});
