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
