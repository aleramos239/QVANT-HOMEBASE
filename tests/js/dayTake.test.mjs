import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* The accounts popup (homebase/static/index.html) carries the account's own day take: closed profit of
   the day, in dollars, after which NO strategy booked on that account takes a new entry (open trades run
   on).  The box shows the take in force and where the day stands; setDayTake sends it to the desk. */
const HTML = readFileSync(new URL('../../homebase/static/index.html', import.meta.url), 'utf8');
const between = (a, b) => HTML.slice(HTML.indexOf(a), HTML.indexOf(b));
const ESC = between('const esc = (v) =>', 'async function chartPost(');
const CODE = between('/* ---- the account\'s day take (the group\'s) ----', '/* ---- accounts popup ---- */');

function ctx({ reply = { ok: true }, open = true } = {}) {
  const sent = [], toasts = [], reopened = [];
  const c = vm.createContext({
    usd: (v) => (v < 0 ? '-$' : '$') + Math.abs(v),
    toast: (m) => toasts.push(m),
    post: async (url, body) => { sent.push([url, body]); return reply; },
    refresh: async () => {},
    openAccts: (id) => reopened.push(id),
    $: () => ({ classList: { contains: () => open } }),
  });
  vm.runInContext(ESC + CODE + '\nglobalThis.dayTakeBox = dayTakeBox; globalThis.setDayTake = setDayTake;', c);
  return { c, sent, toasts, reopened };
}

test('the box shows the take in force and the day so far', () => {
  const { c } = ctx();
  const html = c.dayTakeBox('a1', { day: { day_lock: 1000, closed_net: 400, locked: null } });
  assert.match(html, /value="1000"/);
  assert.match(html, /\$400 of \$1000/);
  assert.doesNotMatch(html, /stopped for the day/);
});

test('a locked day says so; no take shows no counter', () => {
  const { c } = ctx();
  assert.match(c.dayTakeBox('a1', { day: { day_lock: 1000, closed_net: 1250, locked: 'day_lock' } }), /stopped for the day/);
  const off = c.dayTakeBox('a1', { day: { day_lock: 0, closed_net: 0, locked: null } });
  assert.match(off, /value="0"/);
  assert.doesNotMatch(off, /of \$/);
  assert.doesNotThrow(() => c.dayTakeBox('a1', {}));
});

test('the account id reaches the handlers as one JS string literal', () => {
  const { c } = ctx();
  const hostile = "x');alert(1);('";
  const html = c.dayTakeBox(hostile, { day: {} });
  const decode = (v) => v.replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
  const handlers = (html.match(/(?:onclick|onkeydown)="[^"]*"/g) || []).map((h) => decode(h.slice(h.indexOf('"') + 1, -1)));
  assert.equal(handlers.length, 2);
  for (const h of handlers) {
    const calls = [], alerts = [];
    new Function('setDayTake', 'alert', 'event', 'this_', h.replace(/this\.previousElementSibling\.value|this\.value/g, '"5"'))(
      (...a) => calls.push(a), (x) => alerts.push(x), { key: 'Enter' });
    assert.deepEqual(alerts, []);
    assert.deepEqual(calls, [[hostile, '5']]);
  }
});

test('Set sends the account and the number, then shows the popup again', async () => {
  const t = ctx();
  await t.c.setDayTake('a1', '1000');
  assert.deepEqual(JSON.parse(JSON.stringify(t.sent)), [['/api/account-day-lock', { account: 'a1', day_lock: 1000 }]]);
  assert.deepEqual(t.reopened, ['a1']);
  assert.match(t.toasts[0], /\$1000/);
});

test('0 turns it off; a bad value never reaches the desk', async () => {
  const t = ctx();
  await t.c.setDayTake('a1', '0');
  assert.equal(t.sent[0][1].day_lock, 0);
  assert.match(t.toasts[0], /off/);
  for (const bad of ['', 'abc', '-5', '100001']) await t.c.setDayTake('a1', bad);
  assert.equal(t.sent.length, 1);
});

test('the desk refusing it is shown in its own words', async () => {
  const t = ctx({ reply: { ok: false, detail: 'day_lock must be 0..100000' } });
  await t.c.setDayTake('a1', '500');
  assert.equal(t.toasts[0], 'day_lock must be 0..100000');
});
