/* The step tracker above a 3:1 result (plan 4.4): Idea card · Code check · In-sample table · Your pick · Test months · Verdict,
   from what the Lab already has. Locked steps say why in words. The code check ticks at the third trade stepped to. lab.js's own
   functions, run in a vm with a fake page around them. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const require = createRequire(import.meta.url);
const RL = require('../../homebase/static/charts/reallines.js');
const LAB = readFileSync(new URL('../../homebase/static/charts/lab.js', import.meta.url), 'utf8');
const SEEN = LAB.slice(LAB.indexOf('const STEP_TRADES'), LAB.indexOf('/* Click the count and type'));
const STEPS = LAB.slice(LAB.indexOf('function realRead(res, sid)'), LAB.indexOf('function perYearHtml'));

function lab() {
  const c = vm.createContext({
    RL, S: { tries: {}, three: {}, wf: {}, stepped: {}, run: null }, shownRid: null, ti: null, paints: 0,
    esc: (t) => String(t == null ? '' : t), ICON_LOCK: '<svg/>', paintRes() { c.paints++; },
    isDirty: (b) => b.code !== b.saved, triesOf: (sid) => c.S.tries[sid] || null,
    pickedNow: (f) => { const T = c.S.three[f.strategy], w = c.S.wf[f.strategy], t = c.S.tries[f.strategy];
      return !!((T && T.oos.result && T.oos.result.lock) || (w && w.result && w.result.lock) || (t && t.locked)); },
  });
  vm.runInContext(`${SEEN}\n${STEPS}\nObject.assign(globalThis, { seenTrade, steps, stepsHtml });`, c);
  return c;
}
const F = { strategy: 'draft_x' };
const DRAFT = { kind: 'draft', name: 'x', code: 'a', saved: 'a', valid: { ok: true } };
const cell = (i, net) => ({ i, is: { net, trades: 250 }, blocks: [] });
const plain = (v) => JSON.parse(JSON.stringify(v));       // the vm's arrays are another realm's
const states = (c, b = DRAFT) => plain(c.steps(b, F).map((x) => [x.name, x.ok ? 'done' : x.lock ? `locked: ${x.why}` : x.why]));

test('a new strategy: only the idea card is open; every later step is locked and says why', () => {
  const c = lab();
  assert.deepEqual(states(c, { kind: 'new', name: 'x', code: 'a', saved: '', valid: null }), [
    ['Idea card', 'save it'],
    ['Code check', 'step through 3 trades on the chart (0 of 3)'],
    ['In-sample table', 'locked: save it first'],
    ['Your pick', 'locked: run the in-sample table first'],
    ['Test months', 'locked: pick a box first'],
    ['Verdict', 'locked: test months not run (only when you say so)'],
  ]);
  const h = c.stepsHtml({ kind: 'new', name: 'x', code: 'a', saved: '', valid: null }, F);
  assert.match(h, /<li class="next"[^>]*>.*?Idea card/);
  assert.match(h, /<p>Idea card: save it · In-sample table: save it first · Your pick: run the in-sample table first · Test months: pick a box first · Verdict: test months not run \(only when you say so\)<\/p>/);
  // words on screen: never IS, OOS or cell
  assert.doesNotMatch(h.replace(/<[^>]+>/g, ' '), /\b(IS|OOS|cell)\b/);
});

test('saved, the table done, no pick: Your pick is next; the test months and the verdict stay locked', () => {
  const c = lab();
  c.S.wf.draft_x = { result: { scheme: 'fixed', lock: null, cells: [cell(0, 100), cell(1, -50)] } };
  assert.deepEqual(states(c).map((x) => x[1]), ['done', 'step through 3 trades on the chart (0 of 3)', 'done',
    'pick a box in the in-sample table', 'locked: pick a box first', 'locked: test months not run (only when you say so)']);
  // the in-sample table also counts from the tries' list (a finished fixed table of this strategy)
  const d = lab();
  d.S.tries.draft_x = { n: 2, cut: false, tabled: true, locked: false };
  assert.equal(d.steps(DRAFT, F)[2].ok, true);
  // an edited script is not the saved idea card: the table locks again
  assert.equal(c.steps({ ...DRAFT, code: 'b' }, F)[0].ok, false);
});

test('picked and the test months read: the verdict shows its word, from the six lines', () => {
  const c = lab();
  c.S.tries.draft_x = { n: 1, cut: false, tabled: true, locked: true };
  c.S.wf.draft_x = { result: { scheme: 'fixed', lock: { cell: 0 }, cells: [cell(0, 100), cell(1, 50)], oos: { state: 'done', record: { net: -10, trades: 70 } } } };
  const st = c.steps(DRAFT, F);
  assert.deepEqual(plain(st.slice(2).map((x) => x.ok)), [true, true, true, true]);
  assert.equal(st[5].name, 'Verdict: FAKE');           // the test months lost
  // a pick, no read yet: test months are next, not run, and say so
  const d = lab();
  d.S.tries.draft_x = { n: 1, cut: false, tabled: true, locked: true };
  assert.deepEqual(states(d).slice(4), [['Test months', 'not run (only when you say so)'], ['Verdict', 'locked: test months not run (only when you say so)']]);
  // a read found only in the saved walk-forwards (loadTries keeps it) still gives the verdict
  const e = lab();
  e.S.tries.draft_x = { n: 1, cut: false, tabled: true, locked: true, read: { lock: { cell: 0 }, cells: [cell(0, 100)], oos: { state: 'used' } } };
  assert.equal(e.steps(DRAFT, F)[4].ok, false);        // a read that did not finish is not a read result
});

test('the code check ticks at the third different trade stepped to, of the open strategy\'s run only', () => {
  const c = lab();
  c.S.run = { rid: 'r1', strategy: 'draft_x' };
  c.shownRid = 'r1';
  for (const i of [0, 1, 1, 0]) { vm.runInContext(`ti = ${i}`, c); c.seenTrade(); }
  assert.equal(c.S.stepped.draft_x.size, 2);
  assert.equal(c.paints, 0);
  vm.runInContext('ti = 7', c); c.seenTrade();
  assert.equal(c.paints, 1);                            // the tracker repaints once, at the third
  assert.equal(c.steps(DRAFT, F)[1].ok, true);
  vm.runInContext('ti = 8', c); c.seenTrade();
  assert.equal(c.paints, 1);
  // a run that is not on the chart counts nothing
  c.shownRid = 'other';
  vm.runInContext('ti = 9', c); c.seenTrade();
  assert.equal(c.S.stepped.draft_x.size, 4);
});
