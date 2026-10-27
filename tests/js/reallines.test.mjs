/* The six real-or-luck lines in the Lab (reallines.js) are research blueprint/real.py check() copied line by line. The fixture is
   real.check()'s own output (tools/real_parity_fixture.py, run on the Mac): every line, every word and every verdict must match. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

const require = createRequire(import.meta.url);
const R = require('../../homebase/static/charts/reallines.js');
const FX = JSON.parse(readFileSync(new URL('./fixtures/real_parity.json', import.meta.url), 'utf8'));

test('the constants are real.py\'s', () => {
  const c = FX.constants;
  assert.deepEqual([R.MIN_TRADES_IS, R.MIN_TRADES_OOS, R.MIN_YEARS_GREEN, R.MAX_BEST_YEAR, R.MIN_BOXES_PROFIT, R.T_BAR, R.T_PER_TRY],
    [c.MIN_TRADES_IS, c.MIN_TRADES_OOS, c.MIN_YEARS_GREEN, c.MAX_BEST_YEAR, c.MIN_BOXES_PROFIT, c.T_BAR, c.T_PER_TRY]);
});

test('every line and every verdict matches real.check() on the fixture', () => {
  assert.ok(FX.cases.length >= 30);
  for (const c of FX.cases) {
    const got = R.lines(c.s, c.tries);
    assert.deepEqual(got, c.lines, c.name);
    assert.deepEqual(R.verdict(got, c.s, c.cut), c.verdict, c.name);
  }
});

test('the fixture covers every line passing, failing and not run, and all four verdicts', () => {
  const seen = (ln) => new Set(FX.cases.flatMap((c) => c.lines.filter((x) => x.line === ln).map((x) => x.ok)));
  for (const ln of ['boxes', 'trades', 'luck', 'years', 'worse fills', 'test months']) {
    assert.ok(seen(ln).has(true) && seen(ln).has(false), ln);
  }
  for (const ln of ['boxes', 'worse fills', 'test months', 'picked box']) assert.ok(seen(ln).has(null), ln);
  assert.deepEqual(new Set(FX.cases.map((c) => c.verdict.word)), new Set(['REAL', 'LUCK', 'FAKE', 'NOT YET']));
  assert.deepEqual(new Set(FX.cases.map((c) => c.tries)), new Set([0, 1, 2, 4, 500]));
});

test('a cut tries count never lets the luck line pass, and a low t still fails', () => {
  const pass = FX.cases.find((c) => c.name === 'all six pass but the tries count is cut');
  assert.deepEqual(R.verdict(R.lines(pass.s, 500), pass.s, true), { word: 'NOT YET', why: 'next, a full count of tries' });
  assert.equal(R.verdict(R.lines(pass.s, 500), pass.s, false).word, 'REAL');
  assert.match(R.barText(500, true), /^Luck test: needs 126\.75 or more \(2\.0, plus 0\.25 for each of the 499 tries after the first\) · tries 500\+, count incomplete$/);
  assert.equal(R.barText(4, false), 'Luck test: needs 2.75 or more (2.0, plus 0.25 for each of the 3 tries after the first)');
  assert.equal(R.barText(1, false), 'Luck test: needs 2 or more (the first try)');
});

/* the Lab's saved result (walkforward.fixed_result + lock + oos) */
const BL = (is0, trades, net) => ({ i: 0, is: [is0, '', ''], trades, win_rate: 50, net });
const RES = {
  scheme: 'fixed', cells: [
    { i: 0, params: {}, is: { trades: 240, net: 3000 }, blocks: [BL('2021-10', 20, 500), BL('2022-02', 30, 900), BL('2022-06', 10, -200), BL('2023-02', 0, 0), BL('2023-06', 15, 400)] },
    { i: 1, params: {}, is: { trades: 210, net: -100 }, blocks: [] },
    { i: 2, params: {}, is: { trades: 205, net: 50 }, blocks: [] },
    { i: 3, params: {}, is: null, blocks: [] }],
  lock: { cell: 0, params: {}, code: 'x', at: 't', who: 'owner' } };

test('fromLab: boxes, the picked box, the years from the in-sample blocks, and the test months', () => {
  const s = R.fromLab(RES);
  assert.deepEqual(s.is[0], { box: 0, net: 3000, trades: 240, t_stat: null, years_n: 3, years_green: 3, best_year_share: 700 / 1600, split: false, worse_fills_net: null, beats_random: null });
  assert.equal(s.is[3].net, null);                 // a box with no numbers is left out of the count
  assert.deepEqual(s.lock, { box: 0 });
  assert.equal(s.oos, null);
  assert.deepEqual(R.fromLab({ ...RES, oos: { state: 'running', cell: 0 } }).oos, { state: 'running' });
  assert.deepEqual(R.fromLab({ ...RES, oos: { state: 'done', cell: 0, record: { trades: 70, net: 800, pf: 1.3 } } }).oos, { record: { net: 800, trades: 70 } });
  assert.deepEqual(R.fromLab({ ...RES, lock: null }).lock, null);
});

test('labRead: worse fills is not run in the Lab, an unsaved t is not read, so the Lab alone never says REAL', () => {
  const r = R.labRead({ ...RES, oos: { state: 'done', record: { trades: 70, net: 800 } } }, 1, false);
  assert.equal(r.up, 2); assert.equal(r.n, 3);
  const by = Object.fromEntries(r.lines.map((x) => [x.line, x]));
  assert.deepEqual(by['worse fills'], { line: 'worse fills', ok: null, said: 'not run in the Lab' });
  assert.equal(by.luck.ok, null);
  assert.match(by.luck.said, /^not checked in the Lab: the t-statistic is not saved with a 3:1 result$/);
  assert.equal(by.years.ok, true);                      // 3 of 3 green (a block with no trades is no year), best year 44% of the net
  assert.deepEqual(r.verdict, { word: 'NOT YET', why: 'the luck line is not checked in the Lab (no saved t-statistic), so the Lab cannot say REAL' });
  // a saved t that passes: still NOT YET (worse fills)
  const t = { ...RES, cells: RES.cells.map((c) => (c.i === 0 ? { ...c, is: { ...c.is, t_stat: 3.2 }, blocks: [BL('2021-10', 20, 500), BL('2022-02', 30, 900), BL('2023-02', 30, 800), BL('2024-02', 30, 700)] } : c)),
    oos: { state: 'done', record: { trades: 70, net: 800 } } };
  const ok = R.labRead(t, 1, false);
  assert.deepEqual(ok.verdict, { word: 'NOT YET', why: 'next, worse fills' });
  // a losing box with no t fails the luck line, as real.py does
  const lose = R.labRead({ ...RES, lock: { cell: 1 } }, 1, false);
  assert.equal(lose.lines.find((x) => x.line === 'luck').ok, false);
  // a cut tries count: a t over the bar shows as not read, never PASS, and the verdict asks for a full count
  const cut = R.labRead({ ...t, cells: t.cells.map((c) => (c.i === 0 ? { ...c, is: { ...c.is, t_stat: 300 } } : c)) }, 500, true);
  const lk = cut.lines.find((x) => x.line === 'luck');
  assert.equal(lk.ok, null);
  assert.match(lk.said, /tries count is incomplete/);
  assert.equal(cut.verdict.word, 'NOT YET');
  // test months that lose: FAKE, whatever else
  assert.equal(R.labRead({ ...t, oos: { state: 'done', record: { trades: 70, net: -10 } } }, 1, false).verdict.word, 'FAKE');
});

/* A saved 3:1 result as walkforward.fixed_result writes it: `is` is is_numbers' 17 keys -- no t-statistic among them. */
const IS17 = (net, trades) => ({ win_rate: 55, breakeven: 50, wr_minus_be: 5, trades, per_week: 1.2, avg_trade: net / trades, avg_r: 0.1, net, pf: 1.3,
  sharpe: 1.1, max_dd: -2000, months_pos: 60, months_wr60: 40, worst_month_wr: 20, long_net: net / 2, short_net: net / 2, skipped_by_error: 0 });
const B3 = (ms, trades, net) => ({ i: 0, is: ms, trades, win_rate: 50, net });
const SAVED = { scheme: 'fixed', months: [], blocks: [],
  cells: [{ i: 0, params: {}, is: IS17(1700, 250), blocks: [B3(['2021-10', '2021-11', '2021-12'], 50, 500), B3(['2022-02', '2022-03', '2022-04'], 50, 600),
    B3(['2023-02', '2023-03', '2023-04'], 50, 400), B3(['2024-02', '2024-03', '2024-04'], 50, 300), B3(['2025-02', '2025-03', '2025-04'], 50, -100)] },
  { i: 1, params: {}, is: IS17(200, 240), blocks: [] }, { i: 2, params: {}, is: IS17(100, 230), blocks: [] }, { i: 3, params: {}, is: IS17(-50, 210), blocks: [] }],
  lock: { cell: 0, params: {}, code: 'x', at: 't', who: 'owner' }, oos: { state: 'done', cell: 0, record: { trades: 70, net: 800 } } };

test('a saved 3:1 result carries no t-statistic: real.py fails that luck line; the Lab says it is not checked and never says REAL', () => {
  assert.equal(Object.keys(SAVED.cells[0].is).length, 17);
  assert.ok(!('t_stat' in SAVED.cells[0].is));
  // real.py's own read of it: a t of None fails the luck line (pinned by the fixture case "t not on file, all else passes, test months won")
  const py = FX.cases.find((c) => c.name === 't not on file, all else passes, test months won');
  assert.deepEqual([py.lines.find((x) => x.line === 'luck').ok, py.verdict.word], [false, 'LUCK']);
  const s = R.fromLab(SAVED), raw = R.lines(s, 1);
  assert.equal(raw.find((x) => x.line === 'luck').ok, false);                           // the copy of real.py says the same
  // the Lab: every other line read as real.py reads it; luck and worse fills not checked; so NOT YET, never REAL
  const r = R.labRead(SAVED, 1, false), ok = Object.fromEntries(r.lines.map((x) => [x.line, x.ok]));
  assert.deepEqual(ok, { boxes: true, trades: true, luck: null, years: true, 'worse fills': null, 'test months': true });
  assert.equal(r.lines.find((x) => x.line === 'luck').gap, 'the luck line is not checked in the Lab (no saved t-statistic), so the Lab cannot say REAL');
  assert.deepEqual(r.verdict, { word: 'NOT YET', why: 'the luck line is not checked in the Lab (no saved t-statistic), so the Lab cannot say REAL' });
  // any line that fails still says LUCK, and test months that lose say FAKE, as real.py does
  const thin = { ...SAVED, cells: SAVED.cells.map((c) => (c.i === 0 ? { ...c, is: IS17(1700, 150) } : c)) };
  assert.equal(R.labRead(thin, 1, false).verdict.word, 'LUCK');
  assert.equal(R.labRead({ ...SAVED, oos: { state: 'done', cell: 0, record: { trades: 70, net: -5 } } }, 1, false).verdict.word, 'FAKE');
  for (const tries of [1, 4, 500]) for (const cut of [false, true]) assert.notEqual(R.labRead(SAVED, tries, cut).verdict.word, 'REAL');
});

test('a 3:1 block across New Year (6E\'s start in Nov): its year is "2022-23", and the Lab does not read the years line', () => {
  const E6 = { ...SAVED, cells: SAVED.cells.map((c) => (c.i === 0 ? { ...c, blocks: [B3(['2022-11', '2022-12', '2023-01'], 60, 900), B3(['2023-03', '2023-04', '2023-05'], 60, 400),
    B3(['2023-07', '2023-08', '2023-09'], 60, 300), B3(['2024-03', '2024-04', '2024-05'], 70, 100)] } : c)) };
  assert.deepEqual(R.perYear([E6.cells[0]]), [['2022-23', 900], ['2023', 700], ['2024', 100]]);
  assert.equal(R.fromLab(E6).is[0].split, true);
  const y = R.labRead(E6, 1, false).lines.find((x) => x.line === 'years');
  assert.deepEqual([y.ok, y.said], [null, 'not checked in the Lab: a 3:1 block runs across New Year']);
  assert.equal(R.fromLab(SAVED).is[0].split, false);
});

test('perYear: one box, or the average box of the whole table, from the in-sample blocks that traded', () => {
  assert.deepEqual(R.perYear([RES.cells[0]]), [['2021', 500], ['2022', 700], ['2023', 400]]);
  assert.deepEqual(R.perYear(RES.cells.slice(0, 2)), [['2021', 250], ['2022', 350], ['2023', 200]]);
  assert.deepEqual(R.perYear([]), []);
});
