import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* A/B compare (labab.js, the owner 2026-10-18): B against A, green where B is better, and what was set differently. */
const require = createRequire(import.meta.url);
const AB = require('../../homebase/static/charts/labab.js');

test('delta: B against A, the tone by which way is better', () => {
  assert.deepEqual(AB.delta(1000, 1500, 'money', 1), { text: '+$500', tone: 'up' });
  assert.deepEqual(AB.delta(-12000, -9000, 'money', 1), { text: '+$3,000', tone: 'up' }, 'a smaller drawdown is better');
  assert.deepEqual(AB.delta(13, 9, 'int', -1), { text: '-4', tone: 'up' }, 'fewer losses in a row is better');
  assert.deepEqual(AB.delta(33.7, 30.2, 'pctv', 1), { text: '-3.5 pts', tone: 'dn' });
  assert.deepEqual(AB.delta(0.28, 0.35, 'pct', 1), { text: '+7 pts', tone: 'up' });
  assert.deepEqual(AB.delta(703, 1069, 'int', 0), { text: '+366', tone: '' }, 'more trades is neither better nor worse');
  assert.deepEqual(AB.delta(5, 5, 'int', 1), { text: '=', tone: '' });
  assert.deepEqual(AB.delta(null, 5, 'int', 1), { text: '', tone: '' });
});

test('settingsDiff names only what differs: inputs, trade rules (off when unset), days and costs', () => {
  const a = { strategy: { name: 'Mid' }, range: { start: '2021-09-22', end: '2025-06-30' }, inputs: { k: 0.3, sl_pts: 30 }, qty: 1, commission: 4 };
  const b = { ...a, inputs: { k: 0.3, sl_pts: 40 }, controls: { rules: { be_after_pts: 10, trail_pts: 15 } } };
  assert.deepEqual(AB.settingsDiff(a, b), [['Input sl_pts', '30', '40'], ['Rule be after pts', 'off', '10'], ['Rule trail pts', 'off', '15']]);
  assert.deepEqual(AB.settingsDiff(a, a), []);
});

test('the curves are P&L from each run start, and the years are joined', () => {
  assert.deepEqual(AB.pnlCurve({ t_ms: [1, 2, 3], equity: [50000, 50100, 49900] }), [{ t: 1, v: 0 }, { t: 2, v: 100 }, { t: 3, v: -100 }]);
  assert.deepEqual(AB.pnlCurve(null), []);
  const y = AB.byYear({ report: { by_year: [{ period: '2022', net: 1 }] } }, { report: { by_year: [{ period: '2021', net: 2 }, { period: '2022', net: 3 }] } });
  assert.deepEqual(y.map(([p, x, z]) => [p, x && x.net, z && z.net]), [['2021', undefined, 2], ['2022', 1, 3]]);
});

test('matches: every word of the search must be in the name or the id, any case; empty keeps all', () => {
  const x = { id: 'draft_nq_candle_break_apex300', name: 'NQ CANDLE BREAK · APEX 300K' };
  assert.equal(AB.matches(x, ''), true);
  assert.equal(AB.matches(x, 'candle apex'), true);
  assert.equal(AB.matches(x, '  NQ   break '), true);
  assert.equal(AB.matches(x, 'apex300'), true, 'the id counts too');
  assert.equal(AB.matches(x, 'es candle'), false);
});

test('fill: the first strategy whose name begins with what was typed, any case; none for an empty or unmatched box', () => {
  const l = [{ id: 'a', name: 'NQ CANDLE BREAK' }, { id: 'b', name: 'NQ ORB 30' }, { id: 'c', name: 'ES ORB' }];
  assert.equal(AB.fill(l, 'nq o').id, 'b');
  assert.equal(AB.fill(l, '  es').id, 'c');
  assert.equal(AB.fill(l, ''), null);
  assert.equal(AB.fill(l, 'orb'), null, 'begins-with only: a word in the middle is for the narrowing, not the fill');
});

test('pickRuns: newest in-sample run and newest run from Sep 2021 or earlier; unfinished runs never count', () => {
  const r = (id, kind, start, status = 'done') => ({ id, status, range: { kind, start } });
  const p = AB.pickRuns([r('x', 'wf_is', null, 'running'), r('i1', 'wf_is'), r('c1', 'custom', '2024-01-01'), r('f1', 'custom', '2021-09-22'), r('f0', 'custom', '2021-01-01'), r('i0', 'wf_is')]);
  assert.equal(p.is.id, 'i1');
  assert.equal(p.all.id, 'f1');
  assert.deepEqual(AB.pickRuns([]), { is: null, all: null });
});

test('oosBundle: a done test-months read becomes a bundle the report reads; anything else is null', () => {
  const res = { oos: { state: 'done', months: ['2021-12', '2022-01'], params: { n: 3 }, record: { net: 500, trades: 9, win_rate: 55, pf: 1.4, avg_trade: 55.5, max_dd: -300, sharpe: 1.1 } } };
  const b = AB.oosBundle(res, 'S');
  assert.equal(b.run.report.summary.all.net_profit, 500);
  assert.equal(b.run.report.summary.all.max_drawdown, -300);
  assert.equal(b.run.range.end, '2022-01');
  assert.equal(AB.oosBundle({ oos: { state: 'running' } }, 'S'), null);
  assert.equal(AB.oosBundle(null, 'S'), null);
});
