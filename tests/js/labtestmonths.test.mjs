/* No test month before a pick (the owner, O15; plan 4.3, 4.5): runAll and a Run on dates that hold a test month are refused until
   a box of the strategy is picked; after a pick one ask (testMonthsAsk) says the reads and the try, and a yes sends what was sent
   before the ask existed. The tries come from read-only GETs. lab.js's own functions, run in a vm with a fake page around them. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const require = createRequire(import.meta.url);
const C = require('../../homebase/static/charts/labcode.js');
const X = require('../../homebase/static/charts/tester.js');
const LAB = readFileSync(new URL('../../homebase/static/charts/lab.js', import.meta.url), 'utf8');
const CODE = LAB.slice(LAB.indexOf('async function runAll'), LAB.indexOf('async function oosGo'));

const flush = async () => { for (let i = 0; i < 12; i++) await new Promise((r) => setImmediate(r)); };
const F = (range) => ({ strategy: 'draft_x', range });
const R31 = { ...X.LAB_RANGE };
function lab({ picked = false, runs = [], wfs = [] } = {}) {
  const sent = [], logs = [], dialogs = [], did = [];
  const fixed = wfs.filter((w) => w.scheme === 'fixed');
  const c = vm.createContext({
    X, C, S: { tries: {}, three: {}, wf: {}, busy: false }, OOS_SAID: 'x',
    esc: (t) => String(t == null ? '' : t), log: (h) => logs.push(h), paintRes() {}, curSid: () => 'draft_x', triesOf: (sid) => c.S.tries[sid] || null,
    buf: () => ({ key: 'd:x' }), formOf: () => c.form, is31: (f) => f.range.wf === X.WF_ROLL,
    threeState: () => ({ oos: { busy: false, result: null } }), oosGo: () => did.push('oosGo'), run: (o) => did.push(['run', o]),
    closeDialog() {}, dialog: (html) => { const d = { html, on: null, addEventListener(t, f) { d.on = f; } }; dialogs.push(d); return d; },
    send: async (m, url) => {
      sent.push(`${m} ${url}`);
      if (url.startsWith('/api/tester/runs?')) return { ok: true, json: runs };
      if (url === '/api/tester/walkforwards') return { ok: true, json: wfs };
      if (/\/walkforward\/w\d\/result$/.test(url)) return { ok: true, json: { lock: picked ? { cell: 0 } : null, oos: null } };
      return { ok: false, error: 'no' };
    },
  });
  vm.runInContext(`${CODE}\nObject.assign(globalThis, { runAll, oosRun, datedRunOk, loadTries, hasPick });`, c);
  const press = (x) => dialogs.at(-1).on({ target: { closest: () => ({ dataset: { x } }) } });
  return { c, sent, logs, dialogs, did, press, fixed };
}
const TABLE = { id: 'w1', strategy: 'draft_x', scheme: 'fixed', axes: ['ctl.stop', 'ctl.target_rr'] };

test('before a pick: Run all years is refused, no dialog, nothing runs; only read-only GETs went out', async () => {
  const p = lab({ wfs: [TABLE] });
  p.c.form = F(R31);
  await p.c.runAll(); await flush();
  assert.equal(p.dialogs.length, 0);
  assert.deepEqual(p.did, []);
  assert.match(p.logs.join(' '), /Pick a box first/);
  assert.ok(p.sent.every((x) => x.startsWith('GET ')), p.sent.join(', '));
  assert.ok(p.sent.includes('GET /api/tester/runs?limit=500&strategy=draft_x'));
  assert.ok(p.sent.includes('GET /api/tester/walkforward/w1/result'));
});

test('before a pick: a Run on Other dates that hold a test month is refused; dates without one run at once', async () => {
  const p = lab();
  assert.equal(await p.c.datedRunOk(F({ id: 'custom', start: '2022-01-03', end: '2022-01-31', wf: null }), () => p.did.push('again')), false);
  assert.match(p.logs.join(' '), /Pick a box first: 2022-01-03 → 2022-01-31 holds test months/);
  assert.equal(p.dialogs.length, 0);
  assert.equal(await p.c.datedRunOk(F({ id: 'custom', start: '2021-09-22', end: '2021-12-31', wf: null }), () => p.did.push('again')), true);
  assert.equal(await p.c.datedRunOk(F({ id: 'all', start: '', end: '', wf: null }), () => p.did.push('again')), false);    // to today
  assert.deepEqual(p.did, []);
  assert.equal(p.dialogs.length, 0);
});

test('after a pick: one ask says the reads and the try; Not yet sends nothing, a yes runs what ran before', async () => {
  const runs = [{ strategy: 'draft_x', status: 'done', range: { kind: 'wf_is', start: '2021-10-01', end: '2026-08-31' } },
    { strategy: 'draft_x', status: 'done', range: { kind: 'custom', start: '2022-01-01', end: '2022-01-31' } }];
  const p = lab({ picked: true, runs, wfs: [TABLE] });
  p.c.form = F(R31);
  await p.c.runAll(); await flush();
  assert.equal(p.dialogs.length, 1);
  assert.match(p.dialogs[0].html, /Run all years\?/);
  // tries: 1 setting + 1 table = 2; 1 read so far, so this read is try 3; the walk-forward list is not full
  assert.match(p.dialogs[0].html, /They count as seen: test months read 1 time for this strategy; this is try 3\./);
  p.press('cancel');
  assert.deepEqual(p.did, []);
  await p.c.runAll(); await flush();
  p.press('go');
  assert.deepEqual(JSON.parse(JSON.stringify(p.did)), [['run', { tag: 'all' }]]);       // the same call as before the ask
  // a dated Run: the same ask, then run() again with asked (its body is X.body(f), as before)
  const again = [];
  assert.equal(await p.c.datedRunOk(F({ id: 'custom', start: '2023-05-01', end: '2023-05-31', wf: null }), () => again.push(1)), false);
  await flush();
  assert.match(p.dialogs.at(-1).html, /Run these dates\?.*2023-05-01 → 2023-05-31 holds test months/s);
  p.press('go');
  assert.deepEqual(again, [1]);
  assert.match(LAB, /await datedRunOk\(wf0, \(\) => run\(\{ \.\.\.opts, asked: true \}\)\)/);
  assert.ok(p.sent.every((x) => x.startsWith('GET ')));
});

test('the test months of the strategy as set: the same ask, which says it locks box #1; a full list says the count is short', async () => {
  const p = lab({ wfs: Array.from({ length: 20 }, (_, i) => ({ id: `z${i}`, strategy: 'other', scheme: 'fixed', axes: [] })) });
  p.c.form = F(R31);
  p.c.oosRun(); await flush();
  assert.match(p.dialogs[0].html, /Run the test months\?/);
  assert.match(p.dialogs[0].html, /This locks the strategy as set as box #1\./);
  assert.match(p.dialogs[0].html, /test months read 0\+ times for this strategy; this is try 1\+\./);
  p.press('go');
  assert.deepEqual(p.did, ['oosGo']);
  assert.match(LAB, /Run the test months \(the owner clicked it in the Lab\)/);     // OOS_SAID stays
});

test('Put it on the Desk: the confirm shows the verdict, the six lines, lands OFF and no Trade rules; Not yet sends nothing (plan 4.7)', async () => {
  const RL = require('../../homebase/static/charts/reallines.js');
  const a = LAB.indexOf('function promoteToDesk'), code = LAB.slice(LAB.indexOf('const curSid'), LAB.indexOf('function wfFixedHtml'))
    + LAB.slice(a, LAB.indexOf('function deskOffDialog', a));
  const sent = [], dialogs = [];
  const res = { cells: [{ i: 0, is: { net: 900, trades: 250 }, blocks: [] }, { i: 1, is: { net: -50, trades: 40 }, blocks: [] }], lock: { cell: 0 }, oos: null };
  const c = vm.createContext({ X, C, RL, esc: (t) => String(t == null ? '' : t), closeDialog() {}, paintRes() {}, paintLib() {}, log() {}, loadDesk: async () => {},
    S: { run: { key: 'd:x', rid: 'r1', bundle: {} }, tries: {}, three: { draft_x: { oos: { result: res } } }, wf: {} },
    buf: () => null, formOf: () => ({ strategy: 'draft_x' }),
    dialog: (html) => { const d = { html, on: null, addEventListener(t, f) { d.on = f; } }; dialogs.push(d); return d; },
    send: async (m, url, body) => { sent.push([m, url, body]); return { ok: true, json: { ok: true } }; } });
  vm.runInContext(`${code}\nglobalThis.promoteToDesk = promoteToDesk;`, c);
  const press = (x) => dialogs.at(-1).on({ target: { closest: () => ({ dataset: { x } }) } });
  c.promoteToDesk({ key: 'd:x', name: 'x' });
  const h = dialogs[0].html;
  assert.match(h, /Put x on the Desk\?/);
  assert.match(h, /<b>LUCK<\/b>: 1 of 2 boxes made money in-sample/);
  for (const ln of ['boxes', 'trades', 'luck', 'years', 'worse fills', 'test months']) assert.match(h, new RegExp(`<span>${ln}: `), ln);
  assert.match(h, /Lands OFF, no account\./);
  assert.match(h, /Trade rules are not applied on the Desk\./);
  press('cancel');
  assert.deepEqual(sent, []);
  c.promoteToDesk({ key: 'd:x', name: 'x' });
  press('go');
  await new Promise((r) => setImmediate(r));
  assert.deepEqual(JSON.parse(JSON.stringify(sent)), [['POST', '/api/tester/desklab/promote', { name: 'x', run_id: 'r1' }]]);   // the same request as before
});
