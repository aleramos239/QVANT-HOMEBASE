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

test('marks, a card\'s lines in words, and the toolkit\'s own command line left out', () => {
  assert.deepEqual([true, false, null, undefined].map((p) => L.plMark(p).text), ['PASS', 'FAIL', '—', '—']);
  assert.deepEqual([true, false, null].map((p) => L.plMark(p).tone), ['ok', 'err', '']);
  assert.equal(L.plWayLine({ family: 'fvg', main_setting: 'gap_atr', values: ['0.1', '0.25', '0.5'], fixed: { mode: 'touch' } }), 'fvg: gap_atr 0.1 / 0.25 / 0.5 (mode touch)');
  assert.equal(L.plWayLine({ family: 'orb', main_setting: 'or_min', values: [5, 15, 30] }), 'orb: or_min 5 / 15 / 30');
  assert.equal(L.plIndLine({ block: 'momentum', side: 'with', why: 'trades with the push' }), 'momentum with: trades with the push');
  assert.equal(L.plPlain('x waits for the owner\'s look: 9 months won (bp.py pipe approve x, or bp.py pipe refuse x --why=TEXT)'), 'x waits for the owner\'s look: 9 months won');
  assert.equal(L.plPlain('over 60 % of boxes (61 %)'), 'over 60 % of boxes (61 %)', 'any other bracket stays');
  assert.equal(L.plPlain(null), '');
  assert.deepEqual([L.plSession('nyam'), L.plSession('pre'), L.plSession('eve'), L.plSession(null), L.plSide('long'), L.plSide('both')],
    ['New York morning', 'Pre-market', 'eve', '—', 'Long only', 'Both']);
  assert.deepEqual(L.PL_SESSIONS.map(([k]) => k), ['asia', 'london', 'pre', 'nyam', 'mid', 'pm'], 'the six sessions, as they are sent');
});

/* ---- the add-idea form ---- */
const FILLED = () => ({ name: '  fvg_open ', why: ' Gaps at the open  fill fast. ', loser: 'Late chasers pay for it.', market: 'NQ', session: 'nyam', sides: 'both', sides_why: 'not read',
  ways: [{ family: 'fvg', main_setting: ' gap_atr ', values: [' 0.1', '0.25 ', '0.5'] }, { family: '', main_setting: '', values: ['', '', ''] }],
  indicators: [{ block: 'momentum', side: 'with', why: ' trades with  the push ' }, { block: '', side: 'with', why: '' }] });

test('the form starts empty: one way, no indicator, both sides, no market and no time of day chosen', () => {
  assert.deepEqual(L.plForm(), { name: '', why: '', loser: '', market: '', session: '', sides: 'both', sides_why: '', ways: [{ family: '', main_setting: '', values: ['', '', ''] }], indicators: [] });
  assert.notEqual(L.plForm().ways, L.plForm().ways, 'each form is its own');
  assert.deepEqual(L.plCanSend(L.plForm()).needs, ['a name', 'why it should make money', 'who loses', 'a market', 'a time of day', 'an entry rule']);
});

test('the card that is posted: trimmed, values as text, empty ways and indicators dropped, the owner as its source', () => {
  assert.deepEqual(L.plCard(FILLED()), { name: 'fvg_open', why: 'Gaps at the open fill fast.', loser: 'Late chasers pay for it.', source: 'owner', market: 'NQ', session: 'nyam', sides: 'both',
    ways: [{ family: 'fvg', main_setting: 'gap_atr', values: ['0.1', '0.25', '0.5'] }], indicators: [{ block: 'momentum', side: 'with', why: 'trades with the push' }] });
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

test('the form\'s lists come from the arsenal\'s catalog: what runs, on the chosen market; a rule\'s settings only when the catalog gives them', () => {
  const groups = [
    { id: 'families', items: [{ name: 'fvg', words: 'a gap of three bars', markets: ['NQ', 'ES', 'GC'], runs: true }, { name: 'nq_only', words: 'w', markets: ['NQ'], runs: true },
      { name: 'later', words: 'w', markets: ['NQ'], runs: false }, { name: 'with_list', words: 'w', markets: ['NQ'], runs: true, settings: ['n', { name: 'k' }, { key: 'z' }, null] }] },
    { id: 'filters', items: [{ name: 'momentum', markets: ['NQ', 'ES', 'GC'], runs: true, sides: [{ side: 'with', words: 'RSI points the trade\'s way' }, { side: 'against', words: 'RSI points against' }] },
      { name: 'book', markets: ['NQ'], runs: false, sides: [{ side: 'agree', words: 'w' }] }, { name: 'no_sides', markets: ['NQ'], runs: true }] },
    { id: 'sessions', items: [{ name: 'asia', words: 'Asia (00:00-03:00 ET)', markets: [], runs: true }] },
    { id: 'other', items: [{ name: 'absorption', markets: ['NQ'], runs: false }] }];
  const nq = L.plCatalog(groups, 'NQ');
  assert.deepEqual(nq.rules.map((r) => r.name), ['fvg', 'nq_only', 'with_list'], 'what does not run yet is not offered');
  assert.deepEqual([nq.rules[0].words, nq.rules[0].settings], ['a gap of three bars', null], 'no settings list in the catalog: the form takes text');
  assert.deepEqual(nq.rules[2].settings, ['n', 'k', 'z']);
  assert.deepEqual(L.plCatalog(groups, 'ES').rules.map((r) => r.name), ['fvg']);
  assert.deepEqual(L.plCatalog(groups, '').rules.length, 3, 'no market chosen yet: every rule that runs');
  assert.deepEqual(nq.blocks, [{ name: 'momentum', sides: [{ side: 'with', words: 'RSI points the trade\'s way' }, { side: 'against', words: 'RSI points against' }] }]);
  assert.deepEqual(nq.hours, { asia: 'Asia (00:00-03:00 ET)' });
  assert.deepEqual(L.plCatalog(null, 'NQ'), { rules: [], blocks: [], hours: {} }, 'no catalog: empty lists (the form then takes text)');
});

/* ---- the book ---- */
const BOOK = { name: 'fvg_open', sub: 'fvg_open_a5', family: 'fvg', source: 'owner', why: 'Gaps at the open fill fast.', market: 'NQ', session: 'nyam', bar: '5', filter: null,
  rule: { spec: {}, default: 's10_t2', lock: 'abc123' }, label: 'stands alone',
  prop: { 'lucidpro-50k': { name: 'LucidPro 50K', confirmed: true, size: 5, payout_size: 1, eval: 0.584, payout: 0.52, label: 'stands alone' },
    'apex-300k': { name: 'Apex 300K', confirmed: false, size: 10, payout_size: null, eval: 0.4, payout: null, label: 'helper' } },
  hours: ['09:31', '11:42'], trades: 1234, days_traded: 210, win_days_month: 9.26, winning_months: [31, 45], biggest_day_share: 0.118, fast_profit_share: 0.004,
  worst_day: -812.4, worst_drawdown: 1890, avg_trade: 71.6, profit_factor: 1.3149, net: 88357.2, tries: 2,
  stages: { 1: { passed: true, result: 'strict', text: 'a5 moved on' }, 0: { passed: true, result: 'pass', text: 'the card is whole' }, 6: { passed: true, result: 'proven on history', text: 'PROVEN (bp.py pipe show x)' } } };

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
  assert.deepEqual(full.stages.map((s) => [s.n, s.name, s.mark.text, s.text]), [[0, 'Idea card', 'PASS', 'the card is whole'], [1, 'Raw heat map', 'PASS', 'a5 moved on'], [6, 'Unseen days', 'PASS', 'PROVEN']],
    'in the order of the stages, without the toolkit\'s command line');
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
  assert.match(LAB, /const plOpen = \(\) => PIPE_VIEWS\.includes\(S\.view\) && !document\.hidden && P\.lib;/);
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
  const raw = holes.filter((h) => /^[A-Za-z_$][\w$]*(\.[A-Za-z_$][\w$]*)+$/.test(h) && !/\.(n|tone)$|^C\.PL_/.test(h));
  assert.deepEqual(raw, [], 'a value in a template without esc()');
  assert.doesNotMatch(PIPE, /innerHTML = (?!`|'<)/, 'what becomes HTML is a template of this file, never a string that came from elsewhere');
  assert.doesNotMatch(PIPE, /insertAdjacentHTML|outerHTML|document\.write/);
});
