import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

/* The Settings card "Server updates" (static/desk/settings.js): the one line first, in simple words, per state; a small
   table; the log collapsed; read-only (it only ever GETs /api/deploy-status). Run in a sandbox like desksettings.test.mjs. */
import { HTML } from './deskpage.mjs';
const BLOCK = HTML.slice(HTML.indexOf('/* ---- Server updates (read-only)'), HTML.indexOf('function openSettings()'));
const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function load({ answer = { ok: true, body: {} }, demo = false } = {}) {
  const root = { innerHTML: '' }, fetched = [];
  const ctx = vm.createContext({
    DEMO: demo, esc, $: (s) => (s === '#settingsDeploy' ? root : null),
    fetch: async (url, opts) => { fetched.push({ url, opts }); if (answer instanceof Error) throw answer; return { ok: answer.ok, json: async () => answer.body }; },
  });
  vm.runInContext(BLOCK + 'globalThis.api = { deployWords, renderDeploy, loadDeploy };', ctx);
  return { api: ctx.api, root, fetched };
}
const main = { hash: 'd4d4f851', subject: 'feat: a <b>thing</b>' };

test('the verdict for each state, in simple words', () => {
  const { api } = load();
  assert.equal(api.deployWords({ available: true, state: 'shipped' }), 'Server is up to date');
  assert.equal(api.deployWords({ available: true, state: 'waiting', reason: 'it is 09:10-09:35 ET, the Desk is busy at the open' }),
    'Waiting: it is 09:10-09:35 ET, the Desk is busy at the open');
  assert.equal(api.deployWords({ available: true, state: 'waiting', reason: 'a Lab strategy (x) is booked on an account: a restart would end its day', waiting_min: 96 }),
    'Waiting: a Lab strategy (x) is booked on an account: a restart would end its day (for 1 h 36 min)');
  assert.equal(api.deployWords({ available: true, state: 'waiting', reason: 'r', waiting_min: 20 }), 'Waiting: r (for 20 min)');
  assert.equal(api.deployWords({ available: true, state: 'failed', reason: 'the commit does not import (x)' }), 'Failed: the commit does not import (x)');
  assert.equal(api.deployWords({ available: true, state: 'not_set_up' }), 'Not set up here');
  assert.equal(api.deployWords({ available: false, reason: 'Not on this machine: only the Mac' }), 'Not on this machine');
  assert.equal(api.deployWords(null), 'Could not read it');
});

test('the card shows the verdict, the table and a collapsed log, all escaped', () => {
  const { api, root } = load();
  api.renderDeploy({ available: true, state: 'waiting', reason: 'r', main, server: { hash: 'e48e1e6d' }, ahead: 1,
                     last_attempt: '2026-10-27 19:56:23', log: ['a <i>line</i>'] });
  const h = root.innerHTML;
  assert.match(h, /SERVER UPDATES/);
  assert.match(h, /Waiting: r/);
  assert.match(h, /d4d4f851 feat: a &lt;b&gt;thing&lt;\/b&gt;/);
  assert.match(h, /e48e1e6d/);
  assert.match(h, /1 commit</);
  assert.match(h, /2026-10-27 19:56:23/);
  assert.match(h, /<details style="[^"]*">/);       // collapsed: no `open`
  assert.match(h, /a &lt;i&gt;line&lt;\/i&gt;/);
  assert.doesNotMatch(h, /<button|onclick/);
});

test('not on this machine draws no table', () => {
  const { api, root } = load();
  api.renderDeploy({ available: false, reason: 'Not on this machine: x' });
  assert.match(root.innerHTML, /Not on this machine/);
  assert.doesNotMatch(root.innerHTML, /<table/);
});

test('an unchanged answer does not repaint (an open log stays open)', () => {
  const { api, root } = load();
  const d = { available: true, state: 'shipped', main, log: ['x'] };
  api.renderDeploy(d);
  root.innerHTML = 'MARK';
  api.renderDeploy({ ...d });
  assert.equal(root.innerHTML, 'MARK');
});

test('loadDeploy only GETs the one route; an error says so and a preview asks nothing', async () => {
  let t = load({ answer: { ok: true, body: { available: true, state: 'shipped', main } } });
  await t.api.loadDeploy();
  assert.deepEqual(t.fetched.map((f) => [f.url, f.opts]), [['/api/deploy-status', undefined]]);
  assert.match(t.root.innerHTML, /up to date/);
  t = load({ answer: new Error('down') });
  await t.api.loadDeploy();
  assert.match(t.root.innerHTML, /Could not read it/);
  t = load({ demo: true });
  await t.api.loadDeploy();
  assert.deepEqual(t.fetched, []);
});
