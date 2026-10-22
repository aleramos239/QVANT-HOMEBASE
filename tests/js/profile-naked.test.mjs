import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

/* The dashed ("naked") pPOC line of the profile follows the POC that is DRAWN -- the chosen method and share (Profile.levels) --
   not the server's own. Cell.prototype on a bare object, with primitives.js loaded so the real Profile.levels is there
   (orderflow-cell.test.mjs leaves HBLayers empty, so it tests the fallback to the server's POC). */
const require = createRequire(import.meta.url);
globalThis.window = globalThis;
globalThis.HBLayers = {};
for (const f of ['flowdefs', 'flowmath', 'bookstore', 'catalog', 'primitives', 'cell']) require(`../../homebase/static/charts/${f}.js`);
const { Cell } = globalThis.HBCell;
const stub = (more = {}) => Object.assign(Object.create(Cell.prototype), { P: {}, cfg: { indicators: [] }, bars: [], tick: 1, ...more });

/* the server's POC is 99; sierra draws it at 101 (the tied row nearest the middle) */
const rows = [[99, 9], [100, 5], [101, 9], [102, 5], [103, 9]];
const prev = { poc: 99, vah: 102, val: 99, rows };
const profile = { poc: 99, prev };

test('priorNaked tests the POC that is drawn for the chosen method, not the server one', () => {
  const touched99 = stub({ profile, bars: [{ s: 'A', l: 90, h: 110 }, { s: 'B', l: 99, h: 99 }] });
  assert.equal(touched99.priorNaked(), false);                                        // no ex: the server POC 99 was traded
  assert.equal(touched99.priorNaked({ method: 'homebase' }), false);
  assert.equal(touched99.priorNaked({ method: 'sierra' }), true);                     // drawn at 101: not traded today
  const touched101 = stub({ profile, bars: [{ s: 'A', l: 90, h: 110 }, { s: 'B', l: 101, h: 101 }] });
  assert.equal(touched101.priorNaked(), true);                                        // the other way round
  assert.equal(touched101.priorNaked({ method: 'sierra' }), false);
});

test('syncProfile hands the profile layer the method, and a naked flag worked out under it', () => {
  const sets = [];
  const c = stub({ profile, bars: [{ s: 'A', l: 90, h: 110 }, { s: 'B', l: 99, h: 99 }], prof: { set: (...a) => sets.push(a) } });
  c.visible = () => [{ params: { prior: true, lines: true, method: 'sierra' } }];
  c.syncProfile();
  assert.equal(sets[0][2].method, 'sierra');
  assert.equal(sets[0][2].naked, true);
  c.visible = () => [{ params: { prior: true, lines: true } }];
  c.syncProfile();
  assert.equal(sets[1][2].naked, false);
  c.visible = () => [];
  c.syncProfile();
  assert.deepEqual(sets[2].slice(0, 3), [null, 1, null]);                             // no Profile indicator: the layer is cleared
});
