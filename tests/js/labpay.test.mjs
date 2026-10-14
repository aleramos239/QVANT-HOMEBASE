import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

/* The Payout page of the Lab (2026-10-13): the pure half in labcode.js, and source-text pins on lab.js for what the page may do.
   Every number is the server's (GET /api/tester/pipeline/payout). THE LOCK is the owner's: disabled, the page shows one button. */
const require = createRequire(import.meta.url);
const L = require('../../homebase/static/charts/labcode.js');
const LAB = readFileSync(new URL('../../homebase/static/charts/lab.js', import.meta.url), 'utf8');
const PAY = LAB.slice(LAB.indexOf('/* ---- the Payout page (2026-10-13)'), LAB.indexOf('/* Both halves painted:'));

const member = (name, more = {}) => ({ name, cell: 'k0p3_pts30-r0p5', win_rate: 0.7, adds: 120.4, read: true, bench: [], ...more });
const SET = {
  slots: [{ id: 'evening', label: 'Evening', from: '20:00', to: '00:00' }, { id: 'night', label: 'Overnight', from: '02:00', to: '09:25' }, { id: 'day', label: 'New York', from: '09:30', to: '16:00' }],
  accounts: [{ id: 'LTF1', on: true, assumed: true, balance: 50003 }, { id: 'PAAPEX2', on: true, assumed: false, balance: 300000 }, { id: 'OLD3', on: false, balance: 49000 }],
  sets: {
    'lucid-pro': { account_name: 'LucidPro 50K', accounts: ['LTF1'], rules: 'lucid-pro', confirmed: true, mll: 2000, size: 5, gain: 0.25, loss: null, rotation: null, per_week: 56.3,
      slots: { evening: null, night: null, day: member('nq_noise', { bench: [{ name: 'nq_onr' }] }) }, friendly: null },
    'apex-300': { account_name: 'Apex Legacy 300K', accounts: ['PAAPEX2'], rules: 'apex-300', confirmed: false, mll: 7500, size: 1, gain: null, loss: null,
      rotation: { lookback: 20, within: 5 }, per_week: 111, slots: { evening: null, night: null, day: member('nq_donch', { read: null, adds: null }) }, friendly: 'x' } },
  group: { per_week: 167.3, p_paid: 0.833, survivors: 1.4, accounts: [{ id: 'LTF1', per_week: 56.3, p_paid: 0.32, p_bust: 0.4 }, { id: 'PAAPEX2', per_week: 111, p_paid: 0.33, p_bust: 0.43 }] },
  worse: 48.2, unseen: null, proven: false, waiting: [{ name: 'nq_donch', why: 'it has not read the unseen days yet' }], notes: ['a limit'] };

test('the chip says whether the set is proven, and why not', () => {
  assert.deepEqual(L.payProof(null), { label: 'No set', tone: '', text: '' });
  assert.deepEqual(L.payProof(SET), { label: 'Not proven yet', tone: '', text: 'nq_donch: it has not read the unseen days yet. It may not go on a real account.' });
  assert.deepEqual(L.payProof({ ...SET, proven: true, unseen: { per_week: 90.6 }, waiting: [] }), { label: 'Proven', tone: 'ok', text: 'On the unseen days it pays $91 a week.' });
  assert.equal(L.payProof({ ...SET, unseen: { per_week: 0 }, waiting: [] }).label, 'Not proven');
  assert.equal(L.payProof({ ...SET, sets: { a: { size: null } } }).label, 'No set');
});

test('the four numbers on top are the group\'s own', () => {
  assert.deepEqual(L.payTiles(SET), [{ k: 'Expected payout a week', v: '$167', tone: 'pos' }, { k: 'With worse fills', v: '$48', tone: '' },
    { k: 'Any payout in 12 weeks', v: '83 %', tone: '' }, { k: 'Accounts that survive', v: '1.4 of 2', tone: '' }]);
  assert.deepEqual(L.payTiles({}), []);
});

test('a set in words: each slot, its size, its day rule, its rotation, its rule file', () => {
  const [a, b] = L.paySets(SET);
  assert.equal(a.title, 'LucidPro 50K × 1');
  assert.deepEqual(a.slots, [['Evening (20:00–00:00)', 'Nobody'], ['Overnight (02:00–09:25)', 'Nobody'],
    ['New York (09:30–16:00)', 'nq_noise (k0p3_pts30-r0p5), wins 70 % of its trades, adds $120 a week. Reserves: nq_onr']]);
  assert.deepEqual(a.facts, [['Size', '5 micros for each strategy'], ['Day rule', 'Stop for the day once it is up $500'], ['Rotation', 'None: it did not beat no rule'],
    ['Expected payout a week', '$56'], ['Rule file', 'lucid-pro']]);
  assert.equal(a.note, '');
  assert.equal(b.slots[2][1], 'nq_donch (k0p3_pts30-r0p5), wins 70 % of its trades, not read on the unseen days yet');
  assert.deepEqual(b.facts.slice(0, 3), [['Size', '1 micro for each strategy'], ['Day rule', 'Always trade'], ['Rotation', 'Trade a strategy only after a 20-day equity high within 5 days']]);
  assert.equal(b.facts[4][1], 'apex-300 (not confirmed by you)');
  assert.match(b.note, /friendly reading/);
  assert.equal(L.paySets({ ...SET, sets: { x: { ...SET.sets['lucid-pro'], size: null } } })[0].facts[0][1], 'No size keeps the account alive often enough');
});

test('the accounts: what each is expected to pay, how often it pays, how often it is lost', () => {
  assert.deepEqual(L.payAccounts(SET), [['LTF1 (type assumed)', '$50,003 · $56 a week, pays in 32 %, lost in 40 %'],
    ['PAAPEX2', '$300,000 · $111 a week, pays in 33 %, lost in 43 %'], ['OLD3', '$49,000 · Off']]);
});

test('tonight: who trades each slot, or the slot stands down; a switch is the notice to act on', () => {
  const t = { slots: { 'lucid-pro': { day: { trades: 'nq_noise' }, night: { trades: null } } } };
  assert.deepEqual(L.payTonight(t, SET), [['LucidPro 50K, New York', 'nq_noise'], ['LucidPro 50K, Overnight', 'Stand down']]);
  assert.deepEqual(L.payTonight(null, SET), []);
  const n = L.payNotice({ kind: 'switch', utc: '2026-10-14T21:15:00+00:00', text: 'SWITCH: the set changed.' });
  assert.equal(n.title, 'Switch the set'); assert.equal(n.tone, 'run'); assert.equal(n.text, 'SWITCH: the set changed.'); assert.ok(n.when);
  assert.equal(L.payNotice({ kind: 'built', utc: 'nonsense' }).when, '');
  assert.deepEqual(L.payCurve([{ utc: 'a', per_week: 10 }, { utc: 'b' }, { utc: 'c', per_week: 12.5 }]), [['a', null, 10], ['c', null, 12.5]]);
});

/* ---- the page: what lab.js may do (source-text pins) ---- */
test('disabled, the page shows one button and nothing of the set; every server string is escaped', () => {
  assert.ok(PAY.length > 1500, 'the section is there');
  assert.match(PAY, /if \(!D\.enabled\) \{\s+return `<div class="pp-empty"><h2>Payout<\/h2><p>The payout pipeline is disabled\. Nothing of it runs, for you or for Claude, until you enable it here\.<\/p>\s+<button class="btn btn-default" data-act="paydo" data-a="enable"/);
  assert.match(PAY, /if \(!P\.data\.enabled\) return '<div class="lb-empty">Disabled\.<\/div>';/);
  const raw = [...PAY.matchAll(/\$\{(?!esc\(|plKv\(|plChip\(|EQ_|g\.dot|busy|armed|tiles\.|g \?|tonight\.|sets |acts|proof\.text \?|x\.when \?|s\.note \?|ns\.map|\(d\.notes|t\.tone|g\.up|P\.error)([^}]+)\}/g)].map((m) => m[1]);
  assert.deepEqual(raw, [], 'a value written into the page without esc()');
});

test('the page posts one action a press, and sending the ideas round again takes two', () => {
  assert.match(PAY, /send\('POST', '\/api\/tester\/pipeline\/payout', \{ action: a \}\)/);
  assert.match(PAY, /if \(a === 'requeue' && S\.plArmed !== 'pay:requeue'\) \{ S\.plArmed = 'pay:requeue'; paintLib\(\); return; \}/);
  assert.deepEqual([...new Set([...PAY.matchAll(/data-a="(\w+)"/g)].map((m) => m[1]))].sort(), ['build', 'disable', 'enable', 'requeue']);
  assert.match(LAB, /else if \(name === 'paydo'\) payDo\(el\.dataset\.a\);/);
  assert.doesNotMatch(PAY, /\/api\/(desk|orders|accounts)|setInterval/, 'it reaches no account and keeps no timer of its own');
  assert.match(PAY, /Date\.now\(\) - S\.payAt < 20000/, 'at most one look every 20 s');
});
