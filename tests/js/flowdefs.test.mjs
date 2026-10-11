import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
const require = createRequire(import.meta.url);
const D = require('../../homebase/static/charts/flowdefs.js');

test('every definition has the fields catalog.js reads', () => {
  for (const d of [...D.ta, ...D.catalog]) {
    assert.ok(d.id && d.group && d.name && Array.isArray(d.params) && d.desc, d.id);
  }
  for (const d of D.ta) {
    assert.equal(typeof d.key, 'function', d.id);
    assert.equal(typeof d.label, 'function', d.id);
    const p = Object.fromEntries(d.params.map((x) => [x.key, x.def]));
    assert.match(d.key(p), /^[a-z0-9:]+$/, d.id);
    assert.ok(Array.isArray(d.lines), d.id);
  }
  assert.equal(new Set([...D.ta, ...D.catalog].map((d) => d.id)).size, D.ta.length + D.catalog.length);
});

test('book series keys start with bk: and name a store column; server studies do not', () => {
  const byId = Object.fromEntries(D.ta.map((d) => [d.id, d]));
  assert.equal(byId.bkimb.key({ levels: '5' }), 'bk:imb5');
  assert.equal(byId.bkdepth.key({}), 'bk:depth');
  assert.deepEqual(byId.bkdepth.lines.map((l) => l.col), ['b10', 'a10']);
  assert.equal(byId.bkmicro.key({}), 'bk:micro');
  assert.equal(byId.tspeed.key({ length: 200 }), 'tspeed:200');
  assert.equal(byId.ddiv.key({ length: 5 }), 'ddiv:5');
});

test('ddiv marks: a divergence at the swing, nothing otherwise', () => {
  const m = D.ta.find((d) => d.id === 'ddiv').marks;
  assert.equal(m(null, {}), null);
  assert.equal(m({}, {}), null);
  assert.deepEqual(m({ dir: -1, ago: 5, px: 12 }, {}), { position: 'aboveBar', color: '#F23645', shape: 'arrowDown', text: 'Δ', size: 1, ago: 5 });
  assert.equal(m({ dir: 1, ago: 5, px: 4 }, {}).position, 'belowBar');
});

test('bookValue: a number for one column, an object for the depth pair, null while the store has nothing', () => {
  const mean = (m) => (col) => (col in m ? m[col] : null);
  assert.equal(D.bookValue('bk:imb5', mean({ imb5: 0.25 })), 0.25);
  assert.equal(D.bookValue('bk:micro', mean({})), null);
  assert.deepEqual(D.bookValue('bk:depth', mean({ b10: 10, a10: 30 })), { b10: 10, a10: 30 });
  assert.deepEqual(D.bookValue('bk:depth', mean({ b10: 10 })), { b10: 10, a10: null });
  assert.equal(D.bookValue('bk:depth', mean({})), null);
});

test('only the tape speed histograms keep a colour of their own', () => {
  const t = D.ta.find((d) => d.id === 'tspeed');
  assert.deepEqual(t.lines.map((l) => [l.part, !!l.fixed]), [['rate', true], ['hot', true], ['burst', false]]);
  assert.ok(D.ta.filter((d) => d.id !== 'tspeed').every((d) => d.lines.every((l) => !l.fixed)));
});
