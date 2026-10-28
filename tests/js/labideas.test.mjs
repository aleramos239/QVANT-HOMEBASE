import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

/* The idea board (labideas.js, WP5): every saved idea with its stage and next step, and the three steps of the 3:1 route.
   Each step needs the owner's own typed words; the test months also need a second confirm; the pick needs the box. */
const require = createRequire(import.meta.url);
const I = require('../../homebase/static/charts/labideas.js');
const SRC = readFileSync(new URL('../../homebase/static/charts/labideas.js', import.meta.url), 'utf8');

const idea = (name, wf, extra = {}) => ({ name, status: 'idea', next: 'x', job: null, wf, ...extra });

test('stageOf: the three steps map to table / pick / oos, everything else has no button', () => {
  assert.equal(I.stageOf(idea('a', { stage: 'table' })).action, 'table');
  assert.equal(I.stageOf(idea('a', { stage: 'pick' })).action, 'pick');
  assert.equal(I.stageOf(idea('a', { stage: 'test', box: 'k1-r1' })).action, 'oos');
  for (const s of ['card', 'done', 'used', 'error']) assert.equal(I.stageOf(idea('a', { stage: s })).action, null, s);
  assert.equal(I.stageOf(idea('a', {})).action, null, 'off the 3:1 route: shown, no button');
  assert.equal(I.stageOf(idea('a', {})).key, 'old');
  assert.ok(I.stageOf(idea('a', { stage: 'table' })).label.length > 0);
});

test('canAct: the trading server, a running job and a missing step each give a plain reason', () => {
  const t = idea('a', { stage: 'table' });
  assert.deepEqual(I.canAct(t, true), { ok: true, reason: '' });
  const srv = I.canAct(t, false);
  assert.equal(srv.ok, false);
  assert.match(srv.reason, /trading server/i);
  const job = I.canAct(idea('a', { stage: 'table' }, { job: 'j1' }), true);
  assert.equal(job.ok, false);
  assert.match(job.reason, /running/i);
  const none = I.canAct(idea('a', { stage: 'done' }), true);
  assert.equal(none.ok, false);
  assert.ok(none.reason.length > 5);
});

test('stepBody: no words, no body; the words go on exactly as typed', () => {
  const t = idea('nq_a', { stage: 'table' });
  assert.equal(I.stepBody(t, '').error.length > 0, true);
  assert.equal(I.stepBody(t, '   \n ').error.length > 0, true);
  assert.equal(I.stepBody(t, 'x'.repeat(401)).error.length > 0, true);
  const said = '  run the in-sample table for nq_a  ';
  assert.deepEqual(I.stepBody(t, said), { body: { step: 'table', name: 'nq_a', owner_said: said } });
});

test('stepBody: the pick needs a whole box number from 1 up', () => {
  const p = idea('nq_a', { stage: 'pick' });
  for (const bad of ['', 'abc', '0', '-3', '2.5', null, undefined]) assert.ok(I.stepBody(p, 'pick box 7', { box: bad }).error, String(bad));
  assert.deepEqual(I.stepBody(p, 'pick box 7', { box: '7' }), { body: { step: 'pick', name: 'nq_a', owner_said: 'pick box 7', box: 7 } });
});

test('stepBody: the test months need the second confirm, and use the locked box', () => {
  const o = idea('nq_b', { stage: 'test', box: 'k1_own1-r1' });
  assert.ok(I.stepBody(o, 'read the test months').error);
  assert.ok(I.stepBody(o, 'read the test months', { confirmed: false }).error);
  assert.deepEqual(I.stepBody(o, 'read the test months', { confirmed: true }),
    { body: { step: 'oos', name: 'nq_b', owner_said: 'read the test months', box: 'k1_own1-r1', reads_test_months_once: true } });
});

test('stepBody: an idea with no step has no body', () => {
  assert.ok(I.stepBody(idea('a', { stage: 'done' }), 'go').error);
});

test('filterIdeas: stage and words; sortIdeas puts the ones waiting for the owner first', () => {
  const list = [idea('nq_c', { stage: 'done' }), idea('nq_a', { stage: 'table' }), idea('es_b', { stage: 'pick' }), idea('nq_old', {})];
  assert.deepEqual(I.filterIdeas(list, 'nq', 'all').map((x) => x.name), ['nq_c', 'nq_a', 'nq_old']);
  assert.deepEqual(I.filterIdeas(list, '', 'pick').map((x) => x.name), ['es_b']);
  assert.deepEqual(I.sortIdeas(list).map((x) => x.name), ['nq_a', 'es_b', 'nq_c', 'nq_old']);
});

test('the engine note says the buttons run the research engine, not the Lab tester', () => {
  assert.match(I.ENGINE_NOTE, /research engine/i);
  assert.match(I.ENGINE_NOTE, /differ/i);
});

test('source pins: one place starts a step, the look door only reads status, the words are never stored', () => {
  assert.equal((SRC.match(/req\('POST', '\/blueprint\/step'/g) || []).length, 1, 'one place starts a step');
  assert.equal((SRC.match(/\/blueprint\/run/g) || []).length > 0, true);
  assert.deepEqual([...SRC.matchAll(/tool: '(\w+)'/g)].map((m) => m[1]), ['blueprint_status'], 'the look door only asks for status');
  assert.doesNotMatch(SRC, /localStorage|sessionStorage/);
  assert.match(SRC, /const r = stepBody\([^]*?if \(r\.error\)[^]*?req\('POST', '\/blueprint\/step', r\.body\)/, 'the request is sent only after stepBody passed');
});
