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
  assert.deepEqual(s.is[0], { box: 0, net: 3000, trades: 240, t_stat: null, years_n: 3, years_green: 3, best_year_share: 700 / 1600, worse_fills_net: null, beats_random: null });
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
  assert.equal(by.years.ok, true);                      // 3 of 3 green (a block with no trades is no year), best year 44% of the net
  assert.deepEqual(r.verdict, { word: 'NOT YET', why: 'next, the luck test' });
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

test('perYear: one box, or the average box of the whole table, from the in-sample blocks that traded', () => {
  assert.deepEqual(R.perYear([RES.cells[0]]), [['2021', 500], ['2022', 700], ['2023', 400]]);
  assert.deepEqual(R.perYear(RES.cells.slice(0, 2)), [['2021', 250], ['2022', 350], ['2023', 200]]);
  assert.deepEqual(R.perYear([]), []);
});
