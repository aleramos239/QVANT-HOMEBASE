import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

/* The strategy pipeline in the Lab (its Queue, Book and Guide): the pure half in labcode.js, and source-text pins on lab.js for what
   the page may do with it. The verdicts, the reasons and the numbers are the server's (GET /api/tester/pipeline): nothing here judges. */
const require = createRequire(import.meta.url);
const L = require('../../homebase/static/charts/labcode.js');
const rd = (p) => readFileSync(new URL(`../../homebase/static/${p}`, import.meta.url), 'utf8');

const COUNTS0 = { Waiting: 0, Running: 0, Stopped: 0, Problem: 0, Passed: 0, 'In the book': 0, Refused: 0 };
const STAGES = ['Idea card', 'Raw heat map', 'Machine check', 'Indicators', 'Proof', 'Pick one box and lock', 'Unseen days', "The owner's look"]
  .map((name, n) => ({ n, name, words: `${name}?` }));
const idea = (name, label, stage = null, stopped_at = null, why = '') => ({ name, label, stage, stopped_at, why, family: 'fvg' });
const state = (ideas, runner = {}) => {
  const counts = { ...COUNTS0 };
  for (const i of ideas) counts[i.label] += 1;
  return { runner: { running: false, paused: false, ...runner }, counts, ideas, book: [], stages: STAGES };
};

test('the count sentence names only what is there, in the server\'s order', () => {
  assert.equal(L.plCount({ ...COUNTS0, Waiting: 3, Running: 1, Stopped: 8 }), '12 ideas: 3 waiting, 1 running, 8 stopped');
  assert.equal(L.plCount({ ...COUNTS0, Waiting: 1 }), '1 idea: 1 waiting');
  assert.equal(L.plCount({ ...COUNTS0, Problem: 2, Passed: 1, 'In the book': 4, Refused: 1 }), '8 ideas: 2 with a problem, 1 passed, 4 in the book, 1 refused');
  assert.equal(L.plCount(COUNTS0), 'No ideas yet');
  assert.equal(L.plCount(null), 'No ideas yet');
  assert.equal(L.plCount({ 'A new status': 2 }), '2 ideas: 2 a new status', 'a label the page does not know yet is shown as it came');
});

test('the Queue\'s one button says what it will do: Start testing, Pause or Resume', () => {
  const waits = [idea('a', 'Waiting')];
  assert.deepEqual(L.plControl(state(waits)), { label: 'Start testing', actions: ['start'], enabled: true, line: 'Testing is off.' });
  assert.deepEqual(L.plControl(state([])), { label: 'Start testing', actions: ['start'], enabled: false, line: 'Nothing to test. Add an idea first.' });
  assert.deepEqual(L.plControl(state([idea('a', 'Stopped', 1, 1)])).enabled, false, 'a stopped idea is nothing to test');
  assert.deepEqual(L.plControl(state(waits, { running: true })), { label: 'Pause', actions: ['pause'], enabled: true, line: 'Testing is on.' });
  assert.equal(L.plControl(state([], { running: true })).line, 'Testing is on. Nothing is waiting.');
  assert.deepEqual(L.plControl(state(waits, { running: true, paused: true })), { label: 'Resume', actions: ['resume'], enabled: true, line: 'Paused. It stops after the stage it is on.' });
  assert.deepEqual(L.plControl(state(waits, { paused: true })).actions, ['resume', 'start'], 'Resume with no runner working starts one too: the label must not lie');
  assert.deepEqual(L.plControl(state([], { paused: true })).actions, ['resume'], 'with nothing to test, nothing is started');
  assert.equal(L.plControl(state([idea('a', 'Running', 2)])).enabled, true, 'an idea left as running by a runner that ended can be started again');
  assert.equal(L.plControl(null).enabled, false);
});

test('the dots: finished = done, the stage that stopped it = stop, the one in hand = now, the rest hollow', () => {
  assert.deepEqual(L.plDots(idea('a', 'Stopped', 3, 3)), { dots: ['done', 'done', 'done', 'stop', '', '', '', ''], label: 'Reached stage 3 of 7, stopped at stage 3' });
  assert.deepEqual(L.plDots(idea('a', 'Problem', 1, 2)).dots, ['done', 'done', 'stop', '', '', '', '', ''], 'a stage that crashed: stopped_at is one past the last finished');
  assert.deepEqual(L.plDots(idea('a', 'Stopped', null, 0)), { dots: ['stop', '', '', '', '', '', '', ''], label: 'Reached stage 0 of 7, stopped at stage 0' });
  assert.deepEqual(L.plDots(idea('a', 'Waiting')), { dots: ['', '', '', '', '', '', '', ''], label: 'No stage run yet' });
  assert.deepEqual(L.plDots(idea('a', 'Running')), { dots: ['now', '', '', '', '', '', '', ''], label: 'Testing stage 0 of 7' });
  assert.deepEqual(L.plDots(idea('a', 'Running', 2)), { dots: ['done', 'done', 'done', 'now', '', '', '', ''], label: 'Reached stage 2 of 7, testing stage 3' });
  assert.deepEqual(L.plDots(idea('a', 'Waiting', 2)), { dots: ['done', 'done', 'done', '', '', '', '', ''], label: 'Reached stage 2 of 7' });
  assert.deepEqual(L.plDots(idea('a', 'Passed', 7)), { dots: Array(8).fill('done'), label: 'Passed every stage, 0 to 7' });
  assert.equal(L.plDots(idea('a', 'In the book', 7)).dots.length, 8);
  assert.equal(L.plDots(undefined).label, 'No stage run yet');
  assert.equal(L.plDots({ label: 'Stopped', stage: '3', stopped_at: 'x' }).label, 'No stage run yet', 'what is no stage number is not read as one');
});

test('a chip\'s colour goes with its word; an unknown word is plain', () => {
  assert.deepEqual(['Waiting', 'Running', 'Stopped', 'Problem', 'Passed', 'In the book', 'Refused', 'New'].map(L.plTone), ['', 'run', 'err', 'warn', 'ok', 'ok', '', '']);
});

test('what is running now: only while the runner works', () => {
  assert.equal(L.plRunning(state([idea('fvg_open', 'Running', 2)], { running: true })), 'Testing fvg_open — stage 3 of 7');
  assert.equal(L.plRunning(state([idea('fvg_open', 'Running')], { running: true })), 'Testing fvg_open — stage 0 of 7');
  assert.equal(L.plRunning(state([idea('fvg_open', 'Running', 2)])), 'Nothing is running', 'the runner ended: nothing is being tested');
  assert.equal(L.plRunning(state([idea('a', 'Waiting')], { running: true })), 'Nothing is running');
  assert.equal(L.plRunning(null), 'Nothing is running');
});

test('the Guide: six steps, a button grey until its step makes sense, with the reason in words', () => {
  const by = (P) => Object.fromEntries(L.plGuide(P).map((s) => [s.n, s]));
  const none = by(state([]));
  assert.deepEqual(L.plGuide(state([])).map((s) => s.title), ['Write the idea', 'Press Start', 'Wait', 'Read the Queue', 'Look at a green one', 'Build a portfolio']);
  assert.deepEqual([1, 2, 3, 4, 5, 6].map((n) => none[n].enabled), [true, false, false, false, false, false]);
  assert.deepEqual([2, 4, 5, 6].map((n) => none[n].reason), ['Add an idea first.', 'No ideas yet.', 'No idea has passed everything yet.', 'Not built yet']);
  assert.equal(none[3].button, null, 'step 3 has no button');
  assert.equal(none[3].status, 'Nothing is running');
  assert.deepEqual(L.plGuide(state([])).filter((s) => s.primary).map((s) => s.n), [1], 'with no idea, the one to press is step 1');

  const waiting = by(state([idea('a', 'Waiting')]));
  assert.deepEqual([waiting[2].enabled, waiting[2].button, waiting[2].actions, waiting[2].primary], [true, 'Start testing', ['start'], true]);
  assert.deepEqual([waiting[4].enabled, waiting[4].reason], [true, '']);

  const on = by(state([idea('a', 'Running', 1), idea('b', 'Stopped', 1, 1)], { running: true }));
  assert.deepEqual([on[2].enabled, on[2].reason, on[2].actions], [false, 'Testing is already on.', []]);
  assert.equal(on[3].status, 'Testing a — stage 2 of 7');
  assert.equal(on[4].primary, true, 'while it tests, the next thing is to read the Queue');

  const paused = by(state([idea('a', 'Waiting')], { paused: true }));
  assert.deepEqual([paused[2].button, paused[2].enabled, paused[2].actions], ['Resume', true, ['resume', 'start']]);

  const green = by(state([idea('a', 'Waiting'), idea('fvg_open', 'Passed', 7)]));
  assert.deepEqual([green[5].enabled, green[5].button, green[5].name, green[5].primary], [true, 'Look at fvg_open', 'fvg_open', true]);
  assert.equal(green[2].primary, false, 'one primary button at a time');
  for (const P of [state([]), state([idea('a', 'Passed', 7)], { running: true })]) {
    assert.deepEqual([by(P)[6].enabled, by(P)[6].reason], [false, 'Not built yet'], 'the portfolio is never open');
    assert.equal(L.plGuide(P).filter((s) => s.primary).length, 1);
  }
  assert.equal(L.plGuide(null).length, 6);
});

test('the ladder: the server\'s eight stages, each with the ideas that are at it now', () => {
  const P = state([idea('w', 'Waiting'), idea('r', 'Running', 0), idea('q', 'Waiting', 0), idea('s', 'Stopped', 3, 3), idea('c', 'Problem', 1, 2), idea('p', 'Passed', 7),
    idea('b', 'In the book', 7), idea('x', 'Refused', 7)]);
  const lad = L.plLadder(P);
  assert.deepEqual(lad.map((s) => s.ideas), [1, 2, 1, 1, 0, 0, 0, 1], 'an idea in the book or refused is at no stage');
  assert.deepEqual([lad[0].count, lad[1].count, lad[4].count], ['1 idea', '2 ideas', 'None']);
  assert.deepEqual([lad[3].n, lad[3].name, lad[3].words], [3, 'Indicators', 'Indicators?'], 'the name and the sentence are the server\'s');
  assert.deepEqual(L.plLadder(null), []);
  assert.equal(L.plAt(idea('a', 'Running', 7)), 7, 'never past the last stage');
});

test('marks, and a card\'s lines in words', () => {
  assert.deepEqual([true, false, null, undefined].map((p) => L.plMark(p).text), ['PASS', 'FAIL', '—', '—']);
  assert.deepEqual([true, false, null].map((p) => L.plMark(p).tone), ['ok', 'err', '']);
  assert.equal(L.plWayLine({ family: 'fvg', main_setting: 'gap_atr', values: ['0.1', '0.25', '0.5'], fixed: { mode: 'touch' } }), 'fvg: gap_atr 0.1 / 0.25 / 0.5 (mode touch)');
  assert.equal(L.plWayLine({ family: 'orb', main_setting: 'or_min', values: [5, 15, 30] }), 'orb: or_min 5 / 15 / 30');
  assert.equal(L.plIndLine({ block: 'momentum', side: 'with', why: 'trades with the push' }), 'momentum with: trades with the push');
  assert.equal(L.plPlain, undefined, 'the server sends plain text: the page takes nothing out of it');
  assert.deepEqual([L.plSession('nyam'), L.plSession('pre'), L.plSession('eve'), L.plSession(null), L.plSide('long'), L.plSide('both')],
    ['New York morning', 'Pre-market', 'eve', '—', 'Long only', 'Both']);
  assert.deepEqual(L.PL_SESSIONS.map(([k]) => k), ['asia', 'london', 'pre', 'nyam', 'mid', 'pm'], 'the six sessions, as they are sent');
});

/* ---- the add-idea form ---- */
const FILLED = () => ({ name: '  fvg_open ', why: ' Gaps at the open  fill fast. ', loser: 'Late chasers pay for it.', market: 'NQ', session: 'nyam', sides: 'both', sides_why: 'not read',
  ways: [{ family: 'fvg', main_setting: ' min_gap ', values: [' 0.1', '0.25 ', '0.5'] }, { family: '', main_setting: '', values: ['', '', ''] }],
  indicators: [{ block: 'momentum', side: 'with', why: ' trades with  the push ' }, { block: '', side: 'with', why: '' }] });

test('the form starts empty: one way, no indicator, both sides, no market and no time of day chosen', () => {
  assert.deepEqual(L.plForm(), { name: '', why: '', loser: '', market: '', session: '', sides: 'both', sides_why: '', ways: [{ family: '', main_setting: '', values: ['', '', ''] }], indicators: [] });
  assert.notEqual(L.plForm().ways, L.plForm().ways, 'each form is its own');
  assert.deepEqual(L.plCanSend(L.plForm()).needs, ['a name', 'why it should make money', 'who loses', 'a market', 'a time of day', 'an entry rule']);
});

test('the card that is posted: trimmed, values as text, empty ways and indicators dropped, the owner as its source', () => {
  assert.deepEqual(L.plCard(FILLED()), { name: 'fvg_open', why: 'Gaps at the open fill fast.', loser: 'Late chasers pay for it.', source: 'owner', market: 'NQ', session: 'nyam', sides: 'both',
    ways: [{ family: 'fvg', main_setting: 'min_gap', values: ['0.1', '0.25', '0.5'] }], indicators: [{ block: 'momentum', side: 'with', why: 'trades with the push' }] });
  const one = L.plCard({ ...FILLED(), sides: 'long', sides_why: ' shorts squeeze ', indicators: [], ways: [{ family: 'orb', main_setting: 'or_min', values: [5, 15, 30] }] });
  assert.deepEqual([one.sides, one.sides_why], ['long', 'shorts squeeze']);
  assert.equal('indicators' in one, false, 'no indicator: the key is left out');
  assert.deepEqual(one.ways[0].values, ['5', '15', '30'], 'a number is sent as text: the server types it');
  assert.equal('sides_why' in L.plCard(FILLED()), false, 'both sides: no reason is sent');
  const f = FILLED(); L.plCard(f);
  assert.equal(f.name, '  fvg_open ', 'the form is not changed');
});

test('the form can be sent only when the card could pass: what is missing is named in plain words', () => {
  assert.deepEqual(L.plCanSend(FILLED()), { ok: true, needs: [] });
  const needs = (change) => L.plCanSend({ ...FILLED(), ...change }).needs;
  assert.deepEqual(needs({ name: 'Fvg Open' }), ['a name of small letters, numbers and _ (2 to 34, a letter first)']);
  assert.deepEqual(needs({ name: 'a' }), ['a name of small letters, numbers and _ (2 to 34, a letter first)']);
  assert.deepEqual(needs({ why: 'Gaps fill.', loser: 'Chasers.' }), ['8 words or more in those two sentences together']);
  assert.deepEqual(needs({ market: 'CL' }), ['a market']);
  assert.deepEqual(needs({ session: 'eve' }), ['a time of day']);
  assert.deepEqual(needs({ sides: 'long', sides_why: '  ' }), ['why one side only']);
  assert.deepEqual(needs({ sides: 'short', sides_why: 'longs get trapped' }), []);
  assert.deepEqual(needs({ ways: [{ family: '', main_setting: '', values: ['', '', ''] }] }), ['an entry rule']);
  assert.deepEqual(needs({ ways: [{ family: 'fvg', main_setting: '', values: ['1', '', ''] }] }), ['way 1: its main setting', 'way 1: three values']);
  assert.deepEqual(needs({ ways: [{ family: 'fvg', main_setting: 'gap', values: ['1', '1 ', '2'] }] }), ['way 1: three different values']);
  assert.deepEqual(needs({ ways: [{ family: '', main_setting: '', values: ['', '', ''] }, { family: '', main_setting: 'gap', values: ['1', '2', '3'] }] }), ['way 2: an entry rule'],
    'a way is named by its place in the form');
  const way = (k) => ({ family: `f${k}`, main_setting: 's', values: ['1', '2', '3'] });
  assert.deepEqual(needs({ ways: [1, 2, 3, 4].map(way) }), ['3 ways at most']);
  assert.deepEqual(needs({ indicators: [{ block: 'momentum', side: '', why: '' }] }), ['indicator 1: its side', 'indicator 1: why it should help']);
  assert.deepEqual(needs({ indicators: [{ block: '', side: 'with', why: 'it helps' }] }), ['indicator 1: which one']);
  const ind = (b) => ({ block: b, side: 'with', why: 'it helps' });
  assert.deepEqual(needs({ indicators: [ind('ema20'), ind('ema20')] }), ['each indicator once']);
  assert.deepEqual(needs({ indicators: ['a', 'b', 'c', 'd', 'e', 'f'].map(ind) }), ['5 indicators at most']);
  assert.deepEqual(needs({ indicators: ['a', 'b', 'c', 'd', 'e'].map(ind) }), []);
});

/* The server's lists, as GET /api/tester/pipeline sends them (homebase/claude_mcp/pipeline_tools.py parts()). */
const set = (name, kind, more = {}) => ({ name, kind, min: null, max: null, choices: [], default: null, tried: [], ...more });
const RULES = [
  { name: 'fvg', words: 'a three-bar gap forms', markets: ['NQ', 'ES', 'GC'], sessions: ['asia', 'london', 'pre', 'nyam', 'mid', 'pm', 'eve'], bars: ['1', '5', '15'],
    settings: [set('min_gap', 'number', { min: 0, max: 10, default: 0.25, tried: [0.1, 0.25, 0.5] }), set('mode', 'choice', { choices: ['touch', 'mid', 'go'], default: 'touch' }),
      set('new_gap', 'choice', { choices: ['replace', 'stop'], default: 'replace' })] },
  { name: 'gap', words: 'the open gaps', markets: ['NQ', 'ES'], sessions: ['nyam'], bars: ['1', '5'], settings: [set('min_gap_atr', 'number', { min: 0, max: 3, default: 0.1 }), set('mode', 'choice', { choices: ['fill', 'go'], default: 'fill', tried: ['fill', 'go'] })] },
  { name: 'donchian', words: 'a channel breaks', markets: ['NQ'], sessions: ['nyam', 'mid', 'pm'], bars: ['5', '15'], settings: [set('n', 'whole', { min: 2, max: 200, default: 20, tried: [10, 20, 40, 60] })] },
  { name: 'supertrend', words: 'it flips', markets: ['NQ', 'ES', 'GC'], sessions: ['nyam'], bars: ['1', '5'], settings: [] },
  { name: 'ib', words: 'the first hour breaks', markets: ['NQ', 'ES', 'GC'], sessions: ['nyam'], bars: ['1', '5'], settings: [set('mode', 'choice', { choices: ['break', 'fade'], default: 'break' })] },
  { name: 'slow', words: 'only on 15 and 30', markets: ['NQ'], sessions: ['nyam'], bars: ['15', '30'], settings: [set('n', 'whole', { min: 1, max: 9, default: 3 })] }];
const INDS = [{ block: 'momentum', sides: [{ side: 'with', words: 'RSI points the trade\'s way' }, { side: 'against', words: 'RSI points against' }], markets: ['NQ', 'ES', 'GC'] },
  { block: 'book', sides: [{ side: 'agree', words: 'the book agrees' }], markets: ['NQ'] }, { block: 'empty', sides: [], markets: ['NQ'] }];

test('the entry rules the form offers: on the chosen market, at 1 or 5 minutes, with a setting that can take three values', () => {
  const nq = L.plRules(RULES, 'NQ');
  assert.deepEqual(nq.rules.map((r) => r.name), ['fvg', 'gap', 'donchian'], 'a rule only on 15 and 30 minutes is no rule of a card');
  assert.equal(nq.hidden, 2, 'supertrend has no setting and ib only a choice of two: they are counted, not listed');
  assert.deepEqual(nq.rules[0].settings.map((x) => x.name), ['min_gap', 'mode'], 'a choice of two cannot be a main setting');
  assert.deepEqual(nq.rules[1].settings.map((x) => x.name), ['min_gap_atr']);
  assert.deepEqual(L.plRules(RULES, 'GC').rules.map((r) => r.name), ['fvg']);
  assert.deepEqual(nq.rules.map(L.plMainSetting), ['min_gap', 'min_gap_atr', 'n'], 'a way starts on the rule\'s only setting, or on the one the library ran three values of');
  assert.equal(L.plMainSetting({ settings: [set('a', 'number'), set('b', 'number')] }), '', 'several, none of them run: the person picks');
  assert.equal(L.plMainSetting(null), '');
  assert.deepEqual(L.plRules(RULES, '').rules.length, 3, 'no market chosen yet: every market');
  assert.deepEqual(L.plRules(null, 'NQ'), { rules: [], hidden: 0 }, 'no list from the server: the form takes text');
  assert.equal(RULES[0].settings.length, 3, 'the server\'s list is not changed');
  assert.deepEqual([set('a', 'bool'), set('a', 'choice', { choices: ['x', 'y', 'z'] }), set('a', 'whole', { min: 1, max: 2 }), set('a', 'whole', { min: 1, max: 3 }), set('a', 'number', { min: 1, max: 1 }),
    set('a', 'number', { min: 0, max: 1 }), set('a', 'text'), null].map(L.plUsable), [false, true, false, true, false, true, true, false]);
});

test('the indicators on the chosen market, and the times of day the chosen rules run in', () => {
  assert.deepEqual(L.plIndicators(INDS, 'ES').map((x) => x.block), ['momentum']);
  assert.deepEqual(L.plIndicators(INDS, 'NQ').map((x) => x.block), ['momentum', 'book'], 'a block without a side is not offered');
  assert.deepEqual(L.plIndicators(null, 'NQ'), []);
  assert.deepEqual(L.plSessionsFor([]).map(([k]) => k), ['asia', 'london', 'pre', 'nyam', 'mid', 'pm'], 'no rule chosen: the pipeline\'s six (never the evening)');
  assert.deepEqual(L.plSessionsFor([RULES[0]]).map(([k]) => k), ['asia', 'london', 'pre', 'nyam', 'mid', 'pm']);
  assert.deepEqual(L.plSessionsFor([RULES[2]]), [['nyam', 'New York morning'], ['mid', 'Midday'], ['pm', 'Afternoon']]);
  assert.deepEqual(L.plSessionsFor([RULES[2], null, RULES[1]]).map(([k]) => k), ['nyam'], 'several ways: the times every one of them runs in');
});

test('three values to start from: what the library ran, around the default; else the default and its neighbours inside the limits', () => {
  const pre = (kind, more) => L.plPrefill(set('x', kind, more));
  assert.deepEqual(pre('number', { min: 0, max: 10, default: 0.25, tried: [0.1, 0.25, 0.5] }), ['0.1', '0.25', '0.5']);
  assert.deepEqual(pre('whole', { min: 2, max: 200, default: 20, tried: [60, 10, 20, 40, 20] }), ['10', '20', '40'], 'four were run: the three around the default, in order');
  assert.deepEqual(pre('whole', { min: 2, max: 200, default: 60, tried: [10, 20, 40, 60] }), ['20', '40', '60']);
  assert.deepEqual(pre('choice', { choices: ['5', '15', '30', '60'], default: '60', tried: ['5', '15', '30', '60'] }), ['15', '30', '60']);
  assert.deepEqual(pre('choice', { choices: ['9', '21', '50'], default: 21, tried: [9, 21, 50] }), ['9', '21', '50'], 'a number the library ran is the choice of the same name');
  assert.deepEqual(pre('choice', { choices: ['touch', 'mid', 'go'], default: 'touch' }), ['touch', 'mid', 'go'], 'nothing was run: three of its choices');
  assert.deepEqual(pre('choice', { choices: ['a', 'b', 'c', 'd'], default: 'd' }), ['b', 'c', 'd']);
  assert.deepEqual(pre('number', { min: 0, max: 3, default: 0.1 }), ['0.05', '0.1', '0.15'], 'half the default each way');
  assert.deepEqual(pre('number', { min: 0, max: 20, default: 0, tried: [0, 1] }), ['0', '2', '4'], 'a default at the lower limit: upwards');
  assert.deepEqual(pre('number', { min: 0.5, max: 0.95, default: 0.9 }), ['0.5', '0.725', '0.95'], 'limits too close for the step: the two ends and the middle');
  assert.deepEqual(pre('whole', { min: 1, max: 20, default: 2 }), ['1', '2', '3']);
  assert.deepEqual(pre('whole', { min: 0, max: 120, default: 0 }), ['0', '1', '2']);
  assert.deepEqual(pre('whole', { min: 1, max: 6, default: 6 }), ['1', '4', '6']);
  for (const s of [set('x', 'whole', { min: 1, max: 6, default: 6 }), set('x', 'number', { min: 0.2, max: 10, default: 1.5 }), set('x', 'whole', { min: 3, max: 100, default: 100 })]) {
    const got = L.plPrefill(s);
    assert.equal(new Set(got).size, 3, JSON.stringify(got));
    assert.deepEqual(got.map((v) => L.plValueError(s, v)), ['', '', ''], 'what is prefilled is always a value the setting takes');
  }
  assert.deepEqual(pre('text'), ['', '', '']);
  assert.deepEqual(pre('bool'), ['', '', '']);
  assert.deepEqual(pre('choice', { choices: ['a', 'b'] }), ['', '', '']);
});

test('a value is checked against the setting\'s limits or choices, and the message says what it must be', () => {
  const num = set('min_gap', 'number', { min: 0, max: 10 }), whole = set('n', 'whole', { min: 2, max: 200 }), choice = set('mode', 'choice', { choices: ['touch', 'mid', 'go'] });
  assert.deepEqual(['0', '0.25', ' 10 ', '', '-0'].map((v) => L.plValueError(num, v)), ['', '', '', '', '']);
  assert.deepEqual(['11', '-1', 'abc', '1e3', '0,5', '.5'].map((v) => L.plValueError(num, v)), Array(6).fill('a number from 0 to 10'));
  assert.deepEqual(['2', '200', '20'].map((v) => L.plValueError(whole, v)), ['', '', '']);
  assert.deepEqual(['1', '201', '2.5', 'ten'].map((v) => L.plValueError(whole, v)), Array(4).fill('a whole number from 2 to 200'));
  assert.deepEqual(['touch', 'go', 'Touch', 'fade'].map((v) => L.plValueError(choice, v)), ['', '', 'one of: touch, mid, go', 'one of: touch, mid, go']);
  assert.equal(L.plValueError(set('x', 'number'), '7'), '', 'no limits sent: any number');
  assert.equal(L.plValueError(set('x', 'number'), 'x'), 'a number');
  assert.equal(L.plValueError(set('x', 'text'), 'anything'), '');
  assert.equal(L.plValueError(null, 'anything'), '');
  assert.equal(L.plSettingWords(RULES[2].settings[0]), 'A whole number from 2 to 200. The library ran 10, 20, 40, 60.');
  assert.equal(L.plSettingWords(RULES[0].settings[1]), 'One of: touch, mid, go.');
  assert.equal(L.plSettingWords(set('x', 'number', { min: 0, max: 3 })), 'A number from 0 to 3.');
});

test('with the server\'s lists the form can be sent only for a rule it offers, a setting of that rule, values it takes and a time it runs in', () => {
  const needs = (change) => L.plCanSend({ ...FILLED(), ...change }, RULES, INDS).needs;
  const way = (more) => [{ family: 'fvg', main_setting: 'min_gap', values: ['0.1', '0.25', '0.5'], ...more }];
  const base = { ways: way({}), indicators: [] };
  assert.deepEqual(needs(base), []);
  assert.deepEqual(needs({ ...base, ways: way({ family: 'supertrend' }) }), ['way 1: an entry rule'], 'a rule the form does not offer');
  assert.deepEqual(needs({ ...base, market: 'GC', ways: way({ family: 'gap', main_setting: 'min_gap_atr' }) }), ['way 1: an entry rule'], 'gap does not run on GC');
  assert.deepEqual(needs({ ...base, ways: way({ main_setting: 'new_gap' }) }), ['way 1: its main setting'], 'a setting that cannot take three values');
  assert.deepEqual(needs({ ...base, ways: way({ values: ['0.1', '11', 'x'] }) }), ['way 1: value 2 must be a number from 0 to 10', 'way 1: value 3 must be a number from 0 to 10']);
  assert.deepEqual(needs({ ...base, ways: way({ main_setting: 'mode', values: ['touch', 'mid', 'fade'] }) }), ['way 1: value 3 must be one of: touch, mid, go']);
  assert.deepEqual(needs({ ...base, session: 'asia', ways: [{ family: 'donchian', main_setting: 'n', values: ['10', '20', '40'] }] }), ['a time of day donchian runs in']);
  assert.deepEqual(needs({ ...base, indicators: [{ block: 'momentum', side: 'with', why: 'it helps' }] }), []);
  assert.deepEqual(needs({ ...base, indicators: [{ block: 'nope', side: 'with', why: 'it helps' }] }), ['indicator 1: which one']);
  assert.deepEqual(needs({ ...base, indicators: [{ block: 'momentum', side: 'high', why: 'it helps' }] }), ['indicator 1: its side']);
  assert.deepEqual(needs({ ...base, market: 'ES', indicators: [{ block: 'book', side: 'agree', why: 'it helps' }] }), ['indicator 1: which one'], 'book is for NQ only');
  assert.deepEqual(L.plCanSend({ ...FILLED(), ways: way({ family: 'anything', main_setting: 'typed', values: ['a', 'b', 'c'] }), indicators: [] }, [], []), { ok: true, needs: [] },
    'no lists from the server: what is typed goes to the server, which checks it');
});

test('beside the Guide: what is happening now, and the selection of a list', () => {
  assert.deepEqual(L.plSummary(state([idea('a', 'Running', 2), idea('b', 'Passed', 7), idea('c', 'Passed', 7)], { running: true })),
    ['3 ideas: 1 running, 2 passed', 'Testing a — stage 3 of 7', '2 ideas passed and wait for your look.']);
  assert.deepEqual(L.plSummary(state([idea('b', 'Passed', 7)])), ['1 idea: 1 passed', 'Nothing is running', '1 idea passed and waits for your look.']);
  assert.deepEqual(L.plSummary(state([])), ['No ideas yet', 'Nothing is running']);
  assert.deepEqual([L.plPick(['a', 'b'], 'b'), L.plPick(['a', 'b'], 'gone'), L.plPick(['a', 'b'], ''), L.plPick([], 'x')], ['b', 'a', 'a', ''], 'the one that was while it is there, else the first');
});

/* ---- the book ---- */
const BOOK = { name: 'fvg_open', sub: 'fvg_open_a5', family: 'fvg', source: 'owner', why: 'Gaps at the open fill fast.', market: 'NQ', session: 'nyam', bar: '5', filter: null,
  rule: { spec: {}, default: 's10_t2', lock: 'abc123' }, label: 'stands alone',
  prop: { 'lucidpro-50k': { name: 'LucidPro 50K', confirmed: true, size: 5, payout_size: 1, eval: 0.584, payout: 0.52, label: 'stands alone' },
    'apex-300k': { name: 'Apex 300K', confirmed: false, size: 10, payout_size: null, eval: 0.4, payout: null, label: 'helper' } },
  hours: ['09:31', '11:42'], trades: 1234, days_traded: 210, win_days_month: 9.26, winning_months: [31, 45], biggest_day_share: 0.118, fast_profit_share: 0.004,
  worst_day: -812.4, worst_drawdown: 1890, avg_trade: 71.6, profit_factor: 1.3149, net: 88357.2, tries: 2,
  stages: { 1: { passed: true, result: 'strict', text: 'a5 moved on' }, 0: { passed: true, result: 'pass', text: 'the card is whole' }, 6: { passed: true, result: 'proven on history', text: 'PROVEN (4.1-4.9)' } } };

test('percent and money as a person reads them; what is missing shows a dash', () => {
  assert.deepEqual([0.584, 0.52, 0, 1, 0.004].map(L.plPct), ['58 %', '52 %', '0 %', '100 %', '0 %']);
  assert.deepEqual([null, undefined, 'x', NaN].map(L.plPct), ['—', '—', '—', '—']);
  assert.deepEqual([88357.2, -812.4, 0, null].map(L.plMoney), ['$88,357', '−$812', '$0', '—']);
});

test('a book card in the list: its label, where it trades, the two 30-day odds on the pipeline\'s own account, and four facts', () => {
  assert.deepEqual(L.plBookCard(BOOK), { name: 'fvg_open', label: 'Stands alone', tone: 'ok', sub: 'NQ · New York morning · 5-minute bars', account: 'LucidPro 50K',
    rows: [['Pass the eval in 30 days', '58 %'], ['Full payout in 30 days', '52 %'], ['Hours it trades', '09:31 – 11:42'], ['Winning months', '31 of 45'],
      ['Biggest day, share of profit', '12 %'], ['Trades under 5 seconds, share of profit', '0 %']] });
  const helper = L.plBookCard({ ...BOOK, label: 'helper', prop: { x: { name: 'LucidPro 50K', confirmed: false, eval: 0.3, payout: 0.1 } } });
  assert.deepEqual([helper.label, helper.tone, helper.account], ['Helper', '', 'LucidPro 50K (rules not confirmed)']);
  const bare = L.plBookCard({ name: 'x' });
  assert.deepEqual(bare.rows.map(([, v]) => v), ['—', '—', '—', '—', '—', '—'], 'a card with nothing on it still reads');
  assert.deepEqual([bare.label, bare.sub, bare.account], ['—', '— · — · —', '']);
  assert.deepEqual(L.plBookCard({ biggest_day_share: null, hours: null, winning_months: [3] }).rows.slice(2, 5).map(([, v]) => v), ['—', '—', '—']);
  assert.equal(L.plBookCard(null).name, '—');
});

test('the whole book card: every fact, every account (one whose rules are not confirmed says so), each stage\'s first line', () => {
  const full = L.plBookFull(BOOK, STAGES), fact = Object.fromEntries(full.facts);
  assert.equal(full.why, 'Gaps at the open fill fast.');
  assert.deepEqual([fact['Entry rule'], fact.Indicator, fact.Bars, fact['Stop and target'], fact.Trades, fact['Winning days a month'], fact['Average trade'], fact['Profit factor'], fact['Net profit'],
    fact['Worst day'], fact['Worst drawdown'], fact['Heat maps tried'], fact['Came from']],
  ['fvg', 'None', '5-minute bars', 's10_t2', '1,234', '9.3', '$72', '1.31', '$88,357', '−$812', '$1,890', '2', 'owner']);
  assert.deepEqual(full.accounts, [
    { name: 'LucidPro 50K', rows: [['Pass the eval in 30 days', '58 % at 5 micros'], ['Full payout in 30 days', '52 % at 1 micro'], ['Label', 'Stands alone']] },
    { name: 'Apex 300K (rules not confirmed)', rows: [['Pass the eval in 30 days', '40 % at 10 micros'], ['Full payout in 30 days', '—'], ['Label', 'Helper']] }]);
  assert.deepEqual(full.stages.map((s) => [s.n, s.name, s.mark.text, s.text]), [[0, 'Idea card', 'PASS', 'the card is whole'], [1, 'Raw heat map', 'PASS', 'a5 moved on'], [6, 'Unseen days', 'PASS', 'PROVEN (4.1-4.9)']],
    'in the order of the stages, each text as the server sent it');
  assert.equal(Object.fromEntries(L.plBookFull({ ...BOOK, filter: 'momentum_with' }, STAGES).facts).Indicator, 'momentum_with');
  const bare = L.plBookFull({}, null);
  assert.deepEqual([bare.why, bare.accounts, bare.stages, bare.facts.filter(([k]) => k !== 'Indicator').every(([, v]) => v === '—')], ['—', [], [], true]);
});

/* ---- the page: what lab.js may do with the pipeline (source-text pins) ---- */
const LAB = rd('charts/lab.js');
const PIPE = LAB.slice(LAB.indexOf('/* ---- the strategy pipeline in the sidebar ----'), LAB.indexOf('function paintEditor()'));

test('the view switcher lists the six views: Strategies, Blueprint, Arsenal, then Queue, Book, Guide', () => {
  assert.match(LAB, /\['lib', 'Strategies'\], \['bp', 'Blueprint'\], \['tk', 'Arsenal'\]/);
  assert.match(LAB, /\['pq', 'Queue'\], \['pb', 'Book'\], \['pg', 'Guide'\]/);
});

test('the pipeline pages talk to three routes only, and post nothing but the six actions', () => {
  assert.ok(PIPE.length > 2000, 'the section is there');
  const urls = [...LAB.matchAll(/['"`](\/api\/tester\/pipeline[^'"`$?]*)/g)].map((m) => m[1]);
  assert.deepEqual([...new Set(urls)].sort(), ['/api/tester/pipeline', '/api/tester/pipeline/idea/', '/api/tester/pipeline/run']);
  const actions = [...PIPE.matchAll(/action: '(\w+)'/g)].map((m) => m[1]);
  assert.deepEqual([...new Set(actions)].sort(), ['add', 'approve', 'refuse']);
  assert.match(PIPE, /pipeRun\(\{ action: a \}\)/, 'start, pause and resume are posted as the helper names them');
});

test('one timer for the three views: never while hidden, never two requests at once, the last state kept when the app cannot be reached', () => {
  assert.equal((LAB.match(/setInterval\(loadPipeline, 5000\)/g) || []).length, 1);
  assert.match(LAB, /const pipeOn = \(\) => PIPE_VIEWS\.includes\(S\.view\);/);
  assert.match(LAB, /const plOpen = \(\) => pipeOn\(\) && !document\.hidden;/);
  assert.match(LAB, /document\.addEventListener\('visibilitychange', plSync\)/);
  assert.match(PIPE, /if \(plLoading\) \{ plAgain = plAgain \|\| force; return; \}/);
  assert.match(PIPE, /Can’t reach the app\. Showing the last known state\./);
  assert.match(PIPE, /was\.text !== text/, 'it paints again only when the answer changed');
});

test('the words on the pipeline pages are plain: none of the toolkit\'s own', () => {
  const shown = PIPE.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '');
  for (const word of ['sub-idea', 'signature', 'stage card', 'awaiting_owner', 'code_problem', 'toolkit', 'store']) assert.doesNotMatch(shown, new RegExp(`\\b${word}s?\\b`, 'i'), word);
  for (const text of ['No ideas yet. Add one from the Guide, or tell Claude your idea in any chat.', 'The book is empty. A strategy lands here after it passes every stage and you approve it.',
    'Not sure how? Tell Claude your idea in any chat and it fills this in.']) assert.ok(PIPE.includes(text), text);
});

test('every string of the server or the person reaches the page escaped', () => {
  const holes = [...PIPE.matchAll(/\$\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}/g)].map((m) => m[1].trim());
  assert.ok(holes.length > 120, 'the templates were read');
  // a hole that is nothing but a value (x.name, st.label, F.why ...) must go through esc(); a stage number, a helper's tone and a limit are the page's own
  const raw = holes.filter((h) => /^[A-Za-z_$][\w$]*(\.[A-Za-z_$][\w$]*)+$/.test(h) && !/\.(n|tone)$|^C\.PL_|^S\.view$/.test(h));
  assert.deepEqual(raw, [], 'a value in a template without esc()');
  assert.doesNotMatch(PIPE, /innerHTML = (?!`|'<|html;|head \+ pipeSide\(\);)/, 'what becomes HTML is a template of this file, never a string that came from elsewhere');
  assert.doesNotMatch(PIPE, /insertAdjacentHTML|outerHTML|document\.write/);
});

test('while a pipeline view is open the middle is its own: the editor, the chart and the result are hidden, never rebuilt, and come back as they were', () => {
  const HTML = rd('backtest.html'), CSS = rd('charts/lab.css');
  assert.ok(HTML.indexOf('id="labLib"') < HTML.indexOf('id="labPipe"') && HTML.indexOf('id="labPipe"') < HTML.indexOf('id="labEd"'), 'its page sits where the editor does');
  const panels = LAB.slice(LAB.indexOf('function applyPanels('), LAB.indexOf('function setPanel('));
  assert.match(panels, /for \(const k of PANELS\) root\.dataset\[k\] = P\[k\] && !\(pipe && k !== 'lib'\) \? '1' : '0';/, 'shown as switched off, by the rules of a panel that is off');
  assert.match(panels, /root\.dataset\.pipe = pipe \? '1' : '0';/);
  assert.doesNotMatch(panels.replace(/P\[k\] && /, ''), /P\[\w+\] = |P\.(code|chart|res) = /, 'the person\'s own panels are not touched');
  assert.match(CSS, /\.lab-pipe \{ display: none;/);
  assert.match(CSS, /\.lab\[data-pipe="1"\] \.lab-pipe \{ display: block; \}/);
  const view = PIPE.slice(PIPE.indexOf('function setView('), PIPE.indexOf('function plSelect('));
  assert.match(view, /applyPanels\(false\);/);
  assert.doesNotMatch(PIPE, /paintEditor\(|paintAll\(|paintRes\(|S\.bufs|S\.cur\b/, 'nothing of the editor is painted or changed from here');
  assert.match(LAB, /if \(inChart\(e\) \|\| pipeOn\(\)\) return;/, 'the editor\'s keys save and run nothing from behind the page');
  assert.equal((PIPE.match(/dialog\(/g) || []).length, 2, 'two sheets only: the add-idea form and the reason of a no');
});
