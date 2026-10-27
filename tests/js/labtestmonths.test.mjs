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
const RUN = LAB.slice(LAB.indexOf('async function run(opts = {})'), LAB.indexOf('/* A "Blueprint record" file'));

const flush = async () => { for (let i = 0; i < 12; i++) await new Promise((r) => setImmediate(r)); };
const F = (range) => ({ strategy: 'draft_x', range });
const R31 = { ...X.LAB_RANGE };
/* NQ's in-sample months as backtest/wfmonths.blocks lays them out (Oct-Dec 2021, Feb-Apr 2022, ... Jun-Aug 2026) */
const NQ_IS = []; for (let y = 2021, m = 10, k = 0; k < 60; k++, m === 12 ? (y += 1, m = 1) : (m += 1)) if (k % 4 < 3) NQ_IS.push(`${y}-${String(m).padStart(2, '0')}`);
const LAYOUT = (strategy = 'draft_x', root = 'NQ', months = NQ_IS) => ({ strategy, status: 'done', range: { kind: 'wf_is', start: '2021-10-01', end: '2026-08-31', root, months } });
const NQ_DRAFT = { key: 'd:x', kind: 'draft', valid: { ok: true, meta: { root: 'NQ' } } };
function lab({ picked = false, runs = [], wfs = [], real = false } = {}) {
  const sent = [], logs = [], dialogs = [], did = [];
  const fixed = wfs.filter((w) => w.scheme === 'fixed');
  const c = vm.createContext({
    X, C, S: { tries: {}, three: {}, wf: {}, busy: false }, OOS_SAID: 'x',
    esc: (t) => String(t == null ? '' : t), log: (h) => logs.push(h), paintRes() {}, curSid: () => 'draft_x', triesOf: (sid) => c.S.tries[sid] || null,
    buf: () => c.cur || NQ_DRAFT, formOf: (b) => (c.forms && b ? c.forms[b.key] : c.form), is31: (f) => f.range.wf === X.WF_ROLL,
    threeState: () => ({ oos: { busy: false, result: null } }), threeResume: () => undefined, wfResume: () => undefined, oosGo: () => did.push('oosGo'), run: (o) => did.push(['run', o]),
    closeDialog() {}, dialog: (html) => { const d = { html, on: null, addEventListener(t, f) { d.on = f; } }; dialogs.push(d); return d; },
    send: async (m, url) => {
      sent.push(`${m} ${url}`);
      if (url.startsWith('/api/tester/runs?')) return { ok: true, json: runs };
      if (url.startsWith('/api/tester/walkforwards?')) return { ok: true, json: wfs };
      if (/\/walkforward\/w\d\/result$/.test(url)) return { ok: true, json: { lock: picked ? { cell: 0 } : null, oos: null } };
      return { ok: false, error: 'no' };
    },
  });
  if (real) Object.assign(c, { metaOf: () => ({ inputs: [] }), validateNow: async () => ({ ok: true }), wfRun() {}, paintHead() {}, isDirty: () => false,
    save: async () => true, release() {}, P: {}, setPanel() {}, poll() {}, threeKeep() {}, stopAsk() {}, threeRunBody: (f) => ({ ...X.body(f), range: { kind: 'wf_is' } }) });
  vm.runInContext(`${CODE}\n${real ? RUN : ''}\nObject.assign(globalThis, { runAll, oosRun, datedRunOk, loadTries, hasPick });`, c);
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
  const p = lab({ runs: [LAYOUT()] });
  assert.equal(await p.c.datedRunOk(F({ id: 'custom', start: '2022-01-03', end: '2022-01-31', wf: null }), () => p.did.push('again')), false);
  assert.match(p.logs.join(' '), /Pick a box first: 2022-01-03 → 2022-01-31 holds test months/);
  assert.equal(p.dialogs.length, 0);
  assert.equal(await p.c.datedRunOk(F({ id: 'custom', start: '2021-09-22', end: '2021-12-31', wf: null }), () => p.did.push('again')), true);
  assert.equal(await p.c.datedRunOk(F({ id: 'custom', start: '2022-02-01', end: '2022-04-30', wf: null }), () => p.did.push('again')), true);   // NQ in-sample
  assert.equal(await p.c.datedRunOk(F({ id: 'all', start: '', end: '', wf: null }), () => p.did.push('again')), false);    // to today
  assert.deepEqual(p.did, []);
  assert.equal(p.dialogs.length, 0);
});

test('before a pick: each market\'s own test months are refused -- 6E Feb 2023, BTC Mar 2026 after its gap; no months known = refused from Jan 2022', async () => {
  const E6 = ['2022-11', '2022-12', '2023-01', '2023-03', '2023-04', '2023-05'];
  const e = lab({ runs: [LAYOUT('draft_x', '6E', E6)] });
  e.c.cur = { key: 'd:x', kind: 'draft', valid: { ok: true, meta: { root: '6E' } } };
  assert.equal(await e.c.datedRunOk(F({ id: 'custom', start: '2023-02-01', end: '2023-02-28', wf: null }), () => e.did.push('again')), false);
  assert.match(e.logs.join(' '), /Pick a box first: 2023-02-01 → 2023-02-28 holds test months/);
  assert.equal(await e.c.datedRunOk(F({ id: 'custom', start: '2023-01-02', end: '2023-01-31', wf: null }), () => e.did.push('again')), true);   // 6E in-sample
  const btc = lab({ runs: [LAYOUT('draft_x', 'BTC', [...NQ_IS.slice(0, 27), '2026-04', '2026-05', '2026-06'])] });
  btc.c.cur = { key: 'd:x', kind: 'draft', valid: { ok: true, meta: { root: 'BTC' } } };
  assert.equal(await btc.c.datedRunOk(F({ id: 'custom', start: '2026-03-02', end: '2026-03-31', wf: null }), () => btc.did.push('again')), false);
  assert.equal(await btc.c.datedRunOk(F({ id: 'custom', start: '2025-06-02', end: '2025-06-30', wf: null }), () => btc.did.push('again')), false);  // the gap
  // the layout of another market, an unchecked edit, or none at all: every month from Jan 2022 may be a test month
  for (const [runs, cur] of [[[LAYOUT('draft_x', 'NQ')], { key: 'd:x', kind: 'draft', valid: { ok: true, meta: { root: '6E' } } }],
    [[LAYOUT()], { key: 'd:x', kind: 'draft', valid: { ok: true, stale: true, meta: { root: 'NQ' } } }], [[], NQ_DRAFT]]) {
    const q = lab({ runs }); q.c.cur = cur;
    assert.equal(await q.c.datedRunOk(F({ id: 'custom', start: '2022-02-01', end: '2022-04-30', wf: null }), () => q.did.push('again')), false);
    assert.match(q.logs.join(' '), /may hold test months \(run In-sample once and the Lab knows this market's months\)/);
    assert.equal(await q.c.datedRunOk(F({ id: 'custom', start: '2021-10-01', end: '2021-12-31', wf: null }), () => q.did.push('again')), true);
  }
  for (const p of [e, btc]) { assert.deepEqual(p.did, []); assert.equal(p.dialogs.length, 0); }
});

test('a yes runs only what it asked about: another strategy opened, or other dates, before the yes -- nothing of the first is sent', async () => {
  const A = { key: 'b:a', kind: 'builtin', id: 'a', meta: { root: 'NQ' } }, B = { key: 'b:b', kind: 'builtin', id: 'b', meta: { root: 'NQ' } };
  const form = (strategy, range) => ({ strategy, inputs: {}, range, qty: 1, commission: 4, slippage_ticks: 1, prop_rules: null, controls: {} });
  const jan = { id: 'custom', start: '2022-01-03', end: '2022-01-31', wf: null };
  const p = lab({ picked: true, real: true, runs: [LAYOUT('a'), LAYOUT('b')], wfs: [{ ...TABLE, strategy: 'a' }, { ...TABLE, id: 'w2', strategy: 'b' }] });
  const posts = () => p.sent.filter((x) => x.startsWith('POST '));
  p.c.forms = { 'b:a': form('a', jan), 'b:b': form('b', jan) };
  p.c.cur = A;
  await p.c.run(); await flush();
  assert.equal(p.dialogs.length, 1);
  assert.match(p.dialogs[0].html, /Strategy: <b>a<\/b>/);                  // the ask names the strategy
  p.c.cur = B;                                                              // B opened while the ask is up
  p.press('go'); await flush();
  assert.deepEqual(posts(), []);
  assert.equal(p.dialogs.length, 2);                                        // B gets its own ask
  assert.match(p.dialogs[1].html, /Strategy: <b>b<\/b>/);
  p.c.forms['b:b'] = form('b', { ...jan, end: '2022-05-31' });            // B's dates changed before the yes
  p.press('go'); await flush();
  assert.deepEqual(posts(), []);
  assert.equal(p.dialogs.length, 3);
  p.press('go'); await flush();
  assert.deepEqual(posts(), ['POST /api/tester/run']);                     // B, as set now, once
  // Run all years: a yes after another strategy was opened runs nothing
  const q = lab({ picked: true, real: true, runs: [LAYOUT('a')], wfs: [{ ...TABLE, strategy: 'a' }] });
  q.c.forms = { 'b:a': form('a', R31), 'b:b': form('b', R31) };
  q.c.cur = A;
  await q.c.runAll(); await flush();
  assert.match(q.dialogs[0].html, /Run all years\?.*Strategy: <b>a<\/b>/s);
  q.c.cur = B;
  q.press('go'); await flush();
  assert.ok(!q.sent.some((x) => x.startsWith('POST ')), q.sent.join(', '));
  assert.match(q.logs.join(' '), /Nothing ran: another strategy is open now\./);
});

test('dates changed while a dated Run got ready (the check, then a save) send nothing: the check read the dates of the click', async () => {
  const form = (range) => ({ strategy: 'draft_x', inputs: {}, range, qty: 1, commission: 4, slippage_ticks: 1, prop_rules: null, controls: {} });
  const p = lab({ real: true, runs: [LAYOUT()] }), D = { ...NQ_DRAFT, code: 'x', saved: 'x' };
  p.c.cur = D;
  p.c.forms = { 'd:x': form({ id: 'custom', start: '2022-02-01', end: '2022-04-30', wf: null }) };      // in-sample: no ask
  p.c.validateNow = async () => { p.c.forms['d:x'] = form({ id: 'custom', start: '2022-01-03', end: '2022-01-31', wf: null }); return { ok: true }; };
  await p.c.run(); await flush();
  assert.ok(!p.sent.some((x) => x.startsWith('POST ')), p.sent.join(', '));
  assert.match(p.logs.join(' '), /Nothing ran: the dates changed while it got ready\./);
  // the same dates all the way: it runs, once
  const q = lab({ real: true, runs: [LAYOUT()] });
  q.c.cur = D;
  q.c.forms = { 'd:x': form({ id: 'custom', start: '2022-02-01', end: '2022-04-30', wf: null }) };
  await q.c.run(); await flush();
  assert.deepEqual(q.sent.filter((x) => x.startsWith('POST ')), ['POST /api/tester/run']);
});

test('after a pick: one ask says the reads and the try; Not yet sends nothing, a yes runs what ran before', async () => {
  const runs = [LAYOUT(),
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
  assert.deepEqual(JSON.parse(JSON.stringify(p.did)), [['run', { tag: 'all', for: NQ_DRAFT }]]);       // the same call as before the ask, for this strategy only
  // a dated Run: the same ask, then run() again with asked (its body is X.body(f), as before)
  const again = [];
  assert.equal(await p.c.datedRunOk(F({ id: 'custom', start: '2023-05-01', end: '2023-05-31', wf: null }), () => again.push(1)), false);
  await flush();
  assert.match(p.dialogs.at(-1).html, /Run these dates\?.*2023-05-01 → 2023-05-31 holds test months/s);
  p.press('go');
  assert.deepEqual(again, [1]);
  assert.match(LAB, /await datedRunOk\(wf0, \(\) => run\(\{ \.\.\.opts, asked: ask \}\), b\)/);
  assert.ok(p.sent.every((x) => x.startsWith('GET ')));
});

test('a pick the list misses (it holds the newest 20 walk-forwards of ALL strategies) is found by the resume, waited for and counted', async () => {
  const p = lab({ wfs: Array.from({ length: 20 }, (_, i) => ({ id: `z${i}`, strategy: 'other', scheme: 'fixed', axes: [] })) });
  p.c.form = F(R31);
  let ends;
  p.c.wfResume = () => new Promise((res) => { ends = () => {
    p.c.S.wf.draft_x = { id: 'w9', job: { axes: [{ key: 'ctl.stop' }, { key: 'ctl.target_rr' }] }, result: { scheme: 'fixed', lock: { cell: 3 }, oos: null } };
    res();
  }; });
  const go = p.c.runAll(); await flush();
  assert.equal(p.dialogs.length, 0);                    // still waiting for the read-only match: no refusal, no ask yet
  assert.equal(p.logs.length, 0);
  ends(); await go; await flush();
  assert.equal(p.dialogs.length, 1);
  assert.match(p.dialogs[0].html, /Run all years\?/);
  const t = await p.c.loadTries('draft_x', true);
  assert.equal(t.locked, true);
  assert.equal(t.tables, 1);                            // the found heat map counts as a try
  assert.equal(t.cut, true);                            // the list is full: the count still says it may be short
  assert.ok(p.sent.every((x) => x.startsWith('GET ')), p.sent.join(', '));
  // nothing found: still refused
  const q = lab({ wfs: Array.from({ length: 20 }, (_, i) => ({ id: `z${i}`, strategy: 'other', scheme: 'fixed', axes: [] })) });
  q.c.form = F(R31);
  q.c.wfResume = async () => {};
  await q.c.runAll(); await flush();
  assert.equal(q.dialogs.length, 0);
  assert.match(q.logs.join(' '), /Pick a box first/);
  // a dated Run waits for an in-sample look already started, and starts none of its own
  const r = lab({ runs: [LAYOUT()] }), seen = [];
  r.c.threeResume = () => { seen.push('three'); };
  r.c.S.three.draft_x = { found: Promise.resolve().then(() => { r.c.S.three.draft_x.oos = { result: { lock: { cell: 0 } } }; }), oos: { result: null } };
  assert.equal(await r.c.datedRunOk(F({ id: 'custom', start: '2023-05-01', end: '2023-05-31', wf: null }), () => {}), false);
  await flush();
  assert.deepEqual(seen, []);
  assert.match(r.dialogs.at(-1).html, /Run these dates\?/);
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

test('Put it on the Desk: the confirm shows the verdict and the six lines of the run\'s own settings, lands OFF and no Trade rules; Not yet sends nothing (plan 4.7)', async () => {
  const RL = require('../../homebase/static/charts/reallines.js');
  const a = LAB.indexOf('function canon'), code = LAB.slice(LAB.indexOf('const curSid'), LAB.indexOf('function wfFixedHtml'))
    + LAB.slice(a, LAB.indexOf('function deskOffDialog', a));
  const sent = [], dialogs = [];
  const res = { cells: [{ i: 0, is: { net: 900, trades: 250 }, blocks: [] }, { i: 1, is: { net: -50, trades: 40 }, blocks: [] }], lock: { cell: 0 }, oos: null };
  const f = { strategy: 'draft_x', inputs: { len: 5 }, range: R31, qty: 1, commission: 4, slippage_ticks: 1, prop_rules: null, controls: {} };
  const ran = (inputs) => ({ run: { inputs, qty: 1, commission: 4, slippage_ticks: 1, range: { kind: 'wf_is' } } });
  const c = vm.createContext({ X, C, RL, esc: (t) => String(t == null ? '' : t), closeDialog() {}, paintRes() {}, paintLib() {}, log() {}, loadDesk: async () => {},
    S: { run: { key: 'd:x', rid: 'r1', bundle: ran({ len: 5 }) }, tries: {}, three: { draft_x: { oos: { result: res, set: '' } } }, wf: {} },
    buf: () => null, formOf: () => f, shaNow: (code) => (code === 'saved code' ? 'sha1' : ''),
    dialog: (html) => { const d = { html, on: null, addEventListener(t, fn) { d.on = fn; } }; dialogs.push(d); return d; },
    send: async (m, url, body) => { sent.push([m, url, body]); return { ok: true, json: { ok: true } }; } });
  vm.runInContext(`${code}\nObject.assign(globalThis, { promoteToDesk, setKey });`, c);
  c.S.three.draft_x.oos.set = c.setKey(f);                 // the one-box record was opened for these settings
  const press = (x) => dialogs.at(-1).on({ target: { closest: () => ({ dataset: { x } }) } });
  const POST = [['POST', '/api/tester/desklab/promote', { name: 'x', run_id: 'r1' }]];      // the same request as before, whatever the dialog says
  c.promoteToDesk({ key: 'd:x', name: 'x' });
  const h = dialogs[0].html;
  assert.match(h, /Put x on the Desk\?/);
  assert.match(h, /The six lines of this run's own settings \(its in-sample months and test months, as set\):/);
  assert.match(h, /<b>LUCK<\/b>: 1 of 2 boxes made money in-sample/);
  for (const ln of ['boxes', 'trades', 'luck', 'years', 'worse fills', 'test months']) assert.match(h, new RegExp(`<span>${ln}: `), ln);
  assert.match(h, /<b>FAIL<\/b><span>luck: t not saved in-sample/);                   // no t-statistic saved: it fails, as in real.py
  assert.match(h, /Lands OFF, no account\./);
  assert.match(h, /Trade rules are not applied on the Desk\./);
  press('cancel');
  assert.deepEqual(sent, []);
  c.promoteToDesk({ key: 'd:x', name: 'x' });
  press('go');
  await new Promise((r) => setImmediate(r));
  assert.deepEqual(JSON.parse(JSON.stringify(sent)), POST);
  // a run made with other settings than the open record (or a record of unknown settings): its lines are not shown as this run's
  for (const [bundle, set] of [[ran({ len: 6 }), c.setKey(f)], [ran({ len: 5 }), undefined], [{ run: { ...ran({ len: 5 }).run, qty: 2 } }, c.setKey(f)]]) {
    c.S.run = { key: 'd:x', rid: 'r1', bundle }; c.S.three.draft_x.oos.set = set; c.S.wf.draft_x = { result: { lock: { cell: 4 } } };
    c.promoteToDesk({ key: 'd:x', name: 'x' });
    const o = dialogs.at(-1).html;
    assert.match(o, /No in-sample record of this run's own settings and code is open: the six lines are not read\./);
    assert.match(o, /Your pick in the in-sample table, box #5, is not matched to this run\./);
    assert.ok(!/LUCK|PASS|FAIL/.test(o), o);
    assert.match(o, /Lands OFF, no account\./);
  }
  sent.length = 0; press('go'); await new Promise((r) => setImmediate(r));
  assert.deepEqual(JSON.parse(JSON.stringify(sent)), POST);
  // a draft: the record's lock must be of the code saved now (the code the Desk takes); other code or not hashed yet: none
  c.S.run = { key: 'd:x', rid: 'r1', bundle: ran({ len: 5 }) }; c.S.three.draft_x.oos.set = c.setKey(f); c.S.wf.draft_x = {};
  for (const [code, shown] of [['sha1', true], ['other sha', false]]) {
    c.S.three.draft_x.oos.result = { ...res, lock: { cell: 0, code } };
    for (const saved of ['saved code', 'not hashed yet']) {
      c.promoteToDesk({ key: 'd:x', name: 'x', kind: 'draft', saved });
      const o = dialogs.at(-1).html, want = shown && saved === 'saved code';
      assert.equal(/The six lines of this run's own settings/.test(o), want, `${code} ${saved}`);
      assert.equal(/No in-sample record of this run's own settings and code is open/.test(o), !want, `${code} ${saved}`);
    }
  }
  sent.length = 0; press('go'); await new Promise((r) => setImmediate(r));
  assert.deepEqual(JSON.parse(JSON.stringify(sent)), POST);                // the same request, whatever the dialog says
});

test('words (plan 4.10): a 3:1 run\'s All metrics says In-sample or Test months; the prop sim is not one of the six lines', () => {
  assert.match(LAB, /scopeName = wf \? \{ all: kind === 'wf_oos' \? 'Test months' : 'In-sample' \} : Object\.fromEntries\(AM\.SCOPES\)/);
  assert.equal((LAB.match(/More numbers · Prop sim[^<]*· not one of the six lines/g) || []).length, 2);
  const MIX = readFileSync(new URL('../../homebase/static/charts/labmix.js', import.meta.url), 'utf8');
  assert.match(MIX, /latest run to 2025-06-30, as one account · old runs that may hold test months/);
  assert.ok(!/build-days run/.test(MIX), 'the retired split\'s words are gone from the subtitle');
  assert.ok(!/nothing here can put one on the desk/.test(LAB.slice(0, 900)), 'the header no longer says the page cannot put one on the Desk');
  assert.match(LAB.slice(0, 900), /Put it on the Desk/);
  assert.match(readFileSync(new URL('../../homebase/static/charts/labcode.js', import.meta.url), 'utf8'), /Dead/);    // O4: the word stays
});
