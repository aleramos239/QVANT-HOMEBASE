import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

/* The idea card by click (WP4): the pure half in labcode.js (the form -> the card tool's arguments, what is still missing, the words
   after a save), and source-text pins on lab.js for what the page may send: only the card tool and the code check tool, nothing
   that starts a heat map or a run, and no owner_said. */
const require = createRequire(import.meta.url);
const L = require('../../homebase/static/charts/labcode.js');
const lab = readFileSync(new URL('../../homebase/static/charts/lab.js', import.meta.url), 'utf8');

const FILLED = () => ({ ...L.bcForm(), name: 'nq_orb_pre', why: ' Early range breaks run. ', loser: 'Fades pay.', market: 'NQ', session: 'nyam', bar: '5',
  family: 'orb', main_setting: 'or_min', values: '5, 15 ,30', neighbors: '15, London', sides: 'both', sides_why: 'Both ways break.', loses_when: 'Chop days.' });

test('an empty form says what is missing, a whole one nothing', () => {
  assert.deepEqual(L.bcForm(), { name: '', why: '', loser: '', market: '', session: '', bar: '5', family: '', main_setting: '', values: '', neighbors: '', sides: 'both', sides_why: '', loses_when: '' });
  assert.deepEqual(L.bcNeeds(L.bcForm()), ['a name', 'why it should make money', 'who loses', 'a market', 'a time of day', 'an entry rule', 'its main setting', '3 or 4 values, each once', 'why both sides, or one']);
  assert.deepEqual(L.bcNeeds(FILLED()), []);
  const needs = (c) => L.bcNeeds({ ...FILLED(), ...c });
  assert.deepEqual(needs({ name: 'Bad Name' }), ['a name: small letters, numbers and _, a letter first']);
  assert.deepEqual(needs({ values: '5, 15' }), ['3 or 4 values, each once']);
  assert.deepEqual(needs({ values: '5, 15, 30, 45, 60' }), ['3 or 4 values, each once']);
  assert.deepEqual(needs({ values: '5, 15, 15' }), ['3 or 4 values, each once']);
  assert.deepEqual(needs({ values: '5, 15, 30, 45' }), []);
  assert.deepEqual(needs({ sides: 'long', sides_why: '' }), ['why both sides, or one']);
});

test('the card tool gets exactly the card and the settings, exits hm40, and nothing that starts a run', () => {
  const body = L.bcBody(FILLED());
  assert.deepEqual(body, {
    name: 'nq_orb_pre',
    card: { why: 'Early range breaks run.', loser: 'Fades pay.', home: { market: 'NQ', session: 'nyam', bar: '5' }, neighbors: ['15', 'London'], main_setting: 'or_min',
      sides: 'both', sides_why: 'Both ways break.', loses_when: 'Chop days.' },
    settings: { family: 'orb', params: { or_min: ['5', '15', '30'] }, exits: 'hm40' } });
  assert.equal('owner_said' in body, false);
  assert.deepEqual(L.bcBody({ ...FILLED(), neighbors: ' ' }).card.neighbors, [], 'neighbors are optional');
});

test('after a save: the toolkit\'s own next step is replaced by the one text line, nothing starts', () => {
  const said = L.bcSaid('Blueprint card · nq_orb_pre · IDEA · phase 0\nIDEA CARD of nq_orb_pre\nNext: When the owner says so: bp.py wf run nq_orb_pre --owner-said="<his words>" (blueprint_wf).\nSaved: a, b\nLab: draft_nq_orb_pre is now in the group "Ideas".');
  assert.equal(said.split('\n').filter((l) => l.startsWith('Next:')).length, 1);
  assert.match(said, /\nNext: ask for the in-sample table\.$/);
  assert.doesNotMatch(said, /bp\.py|owner-said/);
  assert.match(said, /Saved: a, b/);
});

test('the page posts only the card and the code check, with no owner_said, and the code check names the 3 trades', () => {
  const run = /async function bcRun\([^)]*\) \{[\s\S]*?\n\}/.exec(lab);
  assert.ok(run, 'one function posts to the blueprint tool route');
  assert.match(run[0], /'\/api\/tester\/blueprint\/run'/);
  assert.equal(/owner_said/.test(run[0]), false, 'a page never carries the owner\'s words here');
  assert.equal([...lab.matchAll(/\/api\/tester\/blueprint\/run/g)].length, 1, 'the only post to that route');
  const tools = [...lab.matchAll(/bcRun\('(blueprint_[a-z_]+)'/g)].map((m) => m[1]);
  assert.deepEqual([...new Set(tools)].sort(), ['blueprint_card', 'blueprint_code_check']);
  assert.match(lab, /looked: true/);
});

test('the sheet and the check sit where the page already puts such things', () => {
  assert.match(lab, /data-pick="card"/, 'New menu: Write an idea card');
  assert.match(lab, /data-act="bccheck"/);
  assert.match(lab, /data-pick="bccheck"/);
  assert.match(lab, /function cardSheet\(/);
  assert.match(lab, /function checkSheet\(/);
});

test('the code check text drops the toolkit\'s command words', () => {
  const t = 'CODE CHECK of x\n  #3 2024-01-02 09:35 -> 09:50 ET  long\nRESULT: fails 1.5.\nNext: Look at the 3 trades on the chart, then run the code check again with --looked.';
  assert.equal(L.bcLines(t), 'CODE CHECK of x\n  #3 2024-01-02 09:35 -> 09:50 ET  long\nRESULT: fails 1.5.');
});
