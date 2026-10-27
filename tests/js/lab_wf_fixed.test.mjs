/* The Lab's defaults since 2026-10-20 (the owner): hm40 is the heat map, the fixed 3:1 block walk-forward is the Range, the
   in-sample table comes back win rate first and sortable, the owner picks one box, and its test months run only on his typed
   words (owner_said). The pure half is tester.js; lab.js only paints it. */
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readFileSync } from 'node:fs';

const require = createRequire(import.meta.url);
const X = require('../../homebase/static/charts/tester.js');
const rd = (p) => readFileSync(new URL(`../../homebase/${p}`, import.meta.url), 'utf8');
const LAB = rd('static/charts/lab.js');
const STRAT = { id: 'draft_x', name: 'x', root: 'NQ', bar_minutes: 5, inputs: [] };
const OWN = { ...STRAT, own_stop: true };

/* the server's result.json of a fixed job (walkforward.fixed_result) + lock, two boxes, no read yet */
const IS = (wr, net) => ({ win_rate: wr, breakeven: 45, wr_minus_be: wr - 45, trades: 120, per_week: 1.5, avg_trade: net / 120, avg_r: 0.1,
  net, pf: 1.2, sharpe: 0.9, max_dd: -2500, months_pos: 60, months_wr60: 20, worst_month_wr: 30, long_net: net / 2, short_net: net / 2,
  skipped_by_error: 0 });
const RES = { scheme: 'fixed', step_months: 4, rolling: false, stitch: 's', window: { start: '2021-10', end: '2026-08' },
  months: ['2021-10', '2021-11', '2021-12'], blocks: [{ i: 0, is: ['2021-10', '2021-11', '2021-12'] }], n_cells: 2, looks: 2,
  cells: [{ i: 0, params: { 'ctl.stop': 'atr:0.5', 'ctl.target_rr': 0.5 }, is: IS(52, 1000), blocks: [] },
    { i: 1, params: { 'ctl.stop': 'atr:0.5', 'ctl.target_rr': 1 }, is: IS(48, 3000), blocks: [] }], lock: null };
const AXES = [{ key: 'ctl.stop', label: 'Stop', values: ['atr:0.5'], value_labels: ['ATR x0.5'] },
  { key: 'ctl.target_rr', label: 'Target (x stop)', values: [0.5, 1], value_labels: ['0.5', '1'] }];

test('the default range is the 3:1 blocks, and its Run sends the fixed scheme', () => {
  assert.deepEqual(X.LAB_RANGE, { id: 'all', start: '', end: '', wf: X.WF_ROLL, side: 'is' });
  assert.match(LAB, /if \(fresh\) f\.range = \{ \.\.\.X\.LAB_RANGE \}/);
  // the Range list: the 3:1 choices first, the fixed windows after
  const opts = LAB.slice(LAB.indexOf('function settingsHtml'), LAB.indexOf('const inputRow'));
  assert.ok(opts.indexOf('WF_RANGE_OPTS.map') < opts.indexOf('X.RANGES.filter'), 'the 3:1 options come first');
  const f = { ...X.defaults(STRAT), range: { ...X.LAB_RANGE } };
  const b = X.wfFixedBody(f, X.HM40_AXES);
  assert.equal(b.scheme, 'fixed');
  assert.equal(b.step_months, 4);
  for (const k of ['range', 'metric', 'min_trades', 'test_months', 'select_months', 'compare']) assert.ok(!(k in b), k);
  assert.deepEqual(b.axes, X.HM40_AXES);
  assert.equal(X.wfFixedBody({ ...f, range: { ...f.range, step: 1 } }, []).step_months, 1);    // rolling: by hand only
  assert.match(LAB, /X\.wfFixedBody\(f, /);                // the Lab's Run sends it
  // the chart panel's walk-forward (testerui.js) keeps the old pick body
  assert.equal(X.wfBody(f, [], 'net_profit', 5).select_months, 3);
});

test('the default heat map is hm40: the same 40 cells as grid.py, 20 for a strategy with no stop of its own', () => {
  const py = rd('backtest/grid.py'), m = /^HM40_AXES = (\[[\s\S]*?\}\])\n/m.exec(py);
  assert.ok(m, 'grid.py HM40_AXES');
  assert.deepEqual(X.HM40_AXES, JSON.parse(m[1]));
  assert.equal(X.DEFAULT_MAX_CELLS, 120);
  const own = X.gridAxes(X.hm40Rows(OWN), OWN, 120);
  assert.deepEqual(own.axes, X.HM40_AXES);
  assert.equal(X.gridCount(own.axes), 40);
  const atr = X.gridAxes(X.hm40Rows(STRAT), STRAT, 120);
  assert.deepEqual(atr.axes[0].values, ['atr:0.5', 'atr:1', 'atr:1.5', 'atr:2']);
  assert.equal(X.gridCount(atr.axes), 20);
  assert.equal(X.gridProblems(X.defaults(STRAT), STRAT, X.hm40Rows(STRAT)), null);
  assert.match(X.parseValues('own:1', X.axisInput(STRAT, 'ctl.stop'), 120).error, /Stop/);     // no own stop: no own cells
  assert.match(LAB, /rows: X\.hm40Rows\(/);        // the Lab's heat map starts on it
});

test('the run settings mirror controls.py: the own stop multiplier, its floor, the ATR of the strategy\'s bar', () => {
  assert.deepEqual(X.CONTROLS.stop_own_mult, ['float', 1, 0.05, 10]);
  assert.deepEqual(X.CONTROLS.own_floor, ['bool', false]);
  assert.deepEqual(X.CONTROLS.atr_minutes[2], [0, 1, 5, 15]);
  assert.deepEqual(X.controlsClean(X.setControl({}, 'stop_own_mult', '2')), { stop_own_mult: 2 });
  assert.deepEqual(X.controlsClean({ stop_mode: 'atr', stop_atr: 1, stop_own_mult: 2, own_floor: true }), { stop_mode: 'atr', stop_atr: 1 });
  assert.deepEqual(X.controlsClean({ own_floor: true, atr_minutes: 0 }), { own_floor: true, atr_minutes: 0 });
  assert.deepEqual(X.controlsClean(X.setControl({ stop_mode: 'atr', stop_atr: 1 }, 'atr_minutes', '0')), { stop_mode: 'atr', stop_atr: 1, atr_minutes: 0 });
  assert.equal(X.controlsError({ own_floor: true }), '');
});

test('the in-sample table: win rate first, every box one row, sortable, no test-month column before a read', () => {
  const t = X.wfFixedTable(RES, AXES);
  assert.equal(t.head[0].label, 'Box');
  assert.equal(t.head[1].key, 'win_rate');
  assert.equal(t.head[1].label, 'Win rate');
  assert.deepEqual(t.head.slice(1).map((h) => h.key), ['win_rate', 'breakeven', 'wr_minus_be', 'trades', 'per_week', 'avg_trade', 'avg_r',
    'net', 'pf', 'sharpe', 'max_dd', 'months_pos', 'months_wr60', 'worst_month_wr', 'long_net', 'short_net']);
  assert.ok(t.head.every((h) => !/test|out-of-sample|oos/i.test(`${h.key} ${h.label}`)));
  assert.deepEqual(t.rows.map((r) => r.i), [0, 1]);                       // the server's order until a header is clicked
  assert.equal(t.rows[0].label, 'Stop ATR x0.5 · Target (x stop) 0.5');
  assert.deepEqual(t.rows[0].cells.slice(0, 4).map((c) => c.text), ['52.0%', '45.0%', '+7.0', '120']);
  assert.equal(t.rows[1].cells[7].text, '+$3,000');
  assert.equal(t.rows[1].cells[7].tone, 'up');
  assert.equal(t.picked, null);
  assert.deepEqual(X.wfFixedTable(RES, AXES, { key: 'win_rate', dir: -1 }).rows.map((r) => r.i), [0, 1]);
  assert.deepEqual(X.wfFixedTable(RES, AXES, { key: 'net', dir: -1 }).rows.map((r) => r.i), [1, 0]);
  assert.deepEqual(X.wfFixedTable(RES, AXES, { key: 'net', dir: 1 }).rows.map((r) => r.i), [0, 1]);
  const gap = { ...RES, cells: [{ ...RES.cells[0], is: { ...RES.cells[0].is, pf: null } }, RES.cells[1]] };
  assert.deepEqual(X.wfFixedTable(gap, AXES, { key: 'pf', dir: 1 }).rows.map((r) => r.i), [1, 0]);   // no number sorts last
  assert.equal(X.wfFixedTable({ ...RES, cells: [RES.cells[0]] }, []).rows[0].label, 'As set');
  assert.equal(X.wfFixedSort(null, 'net').key, 'net');
  assert.equal(X.wfFixedSort({ key: 'net', dir: -1 }, 'net').dir, 1);
  assert.equal(X.wfFixedSort({ key: 'net', dir: -1 }, 'pf').dir, -1);
});

test('"Run test months" is shut until a box is picked and the owner has typed his words; they go out as typed', () => {
  assert.equal(X.wfFixedOos(RES, 'run it').canRun, false);                    // no pick yet
  const picked = { ...RES, lock: { cell: 1, params: RES.cells[1].params, at: '2026-10-20T15:00:00Z', who: 'owner' } };
  assert.equal(X.wfFixedTable(picked, AXES).picked, 1);
  assert.equal(X.wfFixedOos(picked, '').canRun, false);
  assert.equal(X.wfFixedOos(picked, '   ').canRun, false);
  const ok = X.wfFixedOos(picked, '  run box 1, go  ');
  assert.equal(ok.canRun, true);
  assert.deepEqual(ok.body, { cell: 1, owner_said: '  run box 1, go  ' });   // verbatim
  const read = { ...picked, oos: { state: 'running', cell: 1, done: 3, total: 15 } };
  assert.equal(X.wfFixedOos(read, 'again').canRun, false);                   // one read, never run again
  assert.equal(X.wfFixedOos(read, '').text, 'Test months running · 3 / 15');
  assert.equal(X.wfFixedOos({ ...picked, oos: { state: 'stopped', say: 'stopped: the read is used, no record' } }, '').text,
    'stopped: the read is used, no record');
  const done = X.wfFixedOos({ ...picked, oos: { state: 'done', cell: 1, months: ['2022-01'], record: IS(55, 800), blocks: [] } }, '');
  assert.equal(done.final, true);
  assert.equal(done.row.cells[0].text, '55.0%');
  // the table itself never grows a test-month column, even after the read
  assert.ok(X.wfFixedTable({ ...picked, oos: { state: 'done' } }, AXES).head.every((h) => !/test|oos/i.test(h.key)));
  // lab.js sends the box's words through this, as typed, and shows the server's refusal as it is
  assert.match(LAB, /\/oos`, o\.body\)/);
  assert.match(LAB, /w\.say = r\.error/);
});

/* ---- fix round 1 (review of Task 10) ---- */
const BLK = { i: 3, params: { 'ctl.stop': 'atr:1', 'ctl.target_rr': 2 }, is: IS(50, 500),
  blocks: [{ i: 0, is: ['2021-10', '2021-11', '2021-12'], trades: 30, win_rate: 50, net: 400 },
    { i: 1, is: ['2022-02', '2022-03', '2022-04'], trades: 25, win_rate: 40, net: -150 }] };

test('the owner sees boxes 1-based (#1 ...); the server keeps its 0-based cell', () => {
  assert.equal(X.boxNo(0), '#1');
  const t = X.wfFixedTable(RES, AXES);
  assert.equal(t.rows[0].box, '#1');
  assert.equal(t.rows[0].i, 0);                                    // data-i and {cell} stay 0-based
  for (const bad of ['#${row.i}', '#${t.picked}', 'Pick box #${i}', '#${esc(String(o.body.cell))}']) assert.ok(!LAB.includes(bad), bad);
  assert.match(LAB, /X\.boxNo\(/);
});

test('block by block: a box\'s in-sample blocks, and the picked box\'s test month beside each once read', () => {
  const b = X.wfFixedBlocks(BLK, null);
  assert.deepEqual(b.head, ['Block', 'In-sample months', 'Trades', 'Win rate', 'Net']);
  assert.deepEqual(b.rows[0].cells.map((c) => c.text), ['1', '2021-10 → 2021-12', '30', '50.0%', '+$400']);
  assert.equal(b.rows[1].cells[4].tone, 'down');
  const notDone = { state: 'running', cell: 3 };
  assert.equal(X.wfFixedBlocks(BLK, notDone).head.length, 5);       // nothing of a test month before the read is done
  const other = { state: 'done', cell: 7, blocks: [{ i: 0, oos: '2022-01', trades: 9, win_rate: 60, net: 90 }] };
  assert.equal(X.wfFixedBlocks(BLK, other).head.length, 5);         // another box's read is not this box's
  const read = { state: 'done', cell: 3, blocks: [{ i: 0, oos: '2022-01', trades: 9, win_rate: 60, net: 90 },
    { i: 1, oos: '2022-05', trades: 0, win_rate: null, net: 0 }] };
  const r = X.wfFixedBlocks(BLK, read);
  assert.deepEqual(r.head, ['Block', 'In-sample months', 'Trades', 'Win rate', 'Net', 'Test month', 'Trades', 'Win rate', 'Net']);
  assert.deepEqual(r.rows[0].cells.slice(5).map((c) => c.text), ['2022-01', '9', '60.0%', '+$90']);
  assert.deepEqual(r.rows[1].cells.slice(5).map((c) => c.text), ['2022-05', '0', '—', '$0']);
  assert.match(LAB, /X\.wfFixedBlocks\(/);
});

test('the Lab heat map runs only on the 3:1 in-sample months; the old one-read warning is gone', () => {
  assert.equal(X.heatSwitch({ range: { ...X.LAB_RANGE } }), null);
  const s = X.heatSwitch({ range: { id: 'research', start: '', end: '', wf: null } });
  assert.deepEqual(s.range, X.LAB_RANGE);
  assert.equal(s.say, 'Heat maps run on the 3:1 in-sample months.');
  assert.notStrictEqual(s.range, X.LAB_RANGE);                     // a copy: the form never shares the constant
  assert.match(LAB, /X\.heatSwitch\(/);
  assert.ok(!/one read, only for a locked strategy/.test(LAB));
  // the own-stop multiplier field only for a strategy with a stop of its own
  assert.match(LAB, /stopMode === 'own' && meta && meta\.own_stop \? num\('stop_own_mult'/);
});

test('a strategy with no own_stop says so in one line where its 20 boxes show (final review, 2026-10-21)', () => {
  const atr = X.gridAxes(X.hm40Rows(STRAT), STRAT, 120).axes;
  assert.equal(X.ownStopNote(STRAT, atr, 20), 'this strategy declares no stop of its own (own_stop): 20 boxes');
  assert.equal(X.ownStopNote(OWN, X.HM40_AXES, 40), '');                                    // own_stop: the 40, nothing to say
  assert.equal(X.ownStopNote(STRAT, [{ key: 'ctl.trail_pts', values: [0, 5] }], 2), '');    // no stop axis: not an hm40 table
  assert.equal((LAB.match(/X\.ownStopNote\(/g) || []).length, 2);      // the heat map's run count and the in-sample table's header
});

test('the in-sample table says how many boxes made money, a per-year row first, then the six lines and the verdict (plan 4.2)', async () => {
  const vm = await import('node:vm');
  const RL = require('../../homebase/static/charts/reallines.js');
  const a = LAB.indexOf('const curSid'), b = LAB.indexOf('function wfFixedHtml');
  const c = vm.createContext({ X, RL, S: { tries: {} }, buf: () => null, formOf: () => null,
    esc: (t) => String(t == null ? '' : t).replace(/&/g, '&amp;').replace(/</g, '&lt;') });
  vm.runInContext(`${LAB.slice(a, b)}\nglobalThis.realRead = realRead; globalThis.realHtml = realHtml; globalThis.perYearHtml = perYearHtml;`, c);
  const res = { ...RES, cells: RES.cells.map((x, k) => ({ ...x, is: k ? x.is : IS(52, -100), blocks: [{ i: 0, is: ['2022-02', '2022-03', '2022-04'], trades: 10, net: k ? 300 : -100 }] })) };
  const rd = c.realRead(res, 'draft_x');
  assert.equal(rd.up, 1);
  assert.equal(rd.n, 2);
  assert.equal(rd.verdict.word, 'LUCK');                     // 1 of 2 boxes is under 60%
  const h = c.realHtml(rd, 'draft_x');
  assert.match(h, /Real or luck/);
  assert.match(h, /FAIL<\/b><span>boxes: 1 of 2 boxes made money in-sample/);
  assert.match(h, /not run<\/b><span>picked box: not picked yet/);
  assert.match(h, /LUCK: 1 of 2 boxes/);
  assert.match(h, /Luck test: tries not counted yet/);
  assert.ok(!/\bIS\b|\bOOS\b|\bcell\b/.test(h.replace(/<[^>]+>/g, '')), 'no IS / OOS / cell on screen');
  assert.match(c.perYearHtml(res.cells, 'the average box'), /Per year · the average box.*2022 <b class="up">\+\$100<\/b>/s);
  // the order in the result: per year, the table, its count, the six lines, then the test months
  const w = LAB.slice(b, LAB.indexOf('\n}\n', b));
  const at = (s) => { const i = w.indexOf(s); assert.ok(i >= 0, s); return i; };
  assert.ok(at('${perYearHtml(yc') < at('In-sample table ·'));
  assert.ok(at('In-sample table ·') < at('boxes made money'));
  assert.ok(at('boxes made money') < at('${realHtml(rd, sid)}'));
  assert.ok(at('${realHtml(rd, sid)}') < at('<div class="rs-gh">Test months</div>'));
  assert.match(LAB, /perYearHtml\(cell \? \[cell\] : \[\], 'in-sample, as set'\)/);     // the test months view too
});
