/* The indicator guide: every catalog indicator has a plain-words entry of the right shape and size. */
import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import { readdirSync } from 'node:fs';
const require = createRequire(import.meta.url);
const DIR = new URL('../../homebase/static/charts/', import.meta.url).pathname;
global.window = global;                       // the guide files register on window.HBGuide when there is one
const G = require(DIR + 'guide.js');
window.HBGuide = G;
for (const f of readdirSync(DIR).filter((n) => /^guide-.*\.js$/.test(n)).sort()) require(DIR + f);
const C = require(DIR + 'catalog.js');

const LINES = ['see', 'read', 'use'];
test('every catalog indicator has a guide entry', () => {
  const missing = C.CATALOG.map((d) => d.id).filter((id) => !G.get(id));
  assert.deepEqual(missing, []);
  const extra = G.ids().filter((id) => !C.def(id));
  assert.deepEqual(extra, [], 'a guide entry for an indicator that does not exist');
});

test('a guide entry: one sentence, then short lines, nothing empty, nothing long', () => {
  for (const id of G.ids()) {
    const e = G.get(id);
    assert.equal(typeof e.what, 'string', `${id}: what`);
    assert.ok(e.what.length >= 20 && e.what.length <= 110, `${id}: what is 20-110 characters (${e.what.length})`);
    assert.doesNotMatch(e.what, /\n/, `${id}: what is one line`);
    for (const k of LINES) {
      assert.ok(Array.isArray(e[k]) && e[k].length >= 1 && e[k].length <= 5, `${id}: ${k} has 1-5 lines`);
      for (const t of e[k]) {
        assert.equal(typeof t, 'string');
        assert.ok(t.length >= 8 && t.length <= 120, `${id}: ${k} line 8-120 characters (${t.length}): ${t}`);
        assert.equal(t, t.trim(), `${id}: ${k} no stray spaces`);
      }
    }
    if (e.watch !== undefined) assert.ok(typeof e.watch === 'string' && e.watch.length >= 8 && e.watch.length <= 140, `${id}: watch`);
    const all = [e.what, ...LINES.flatMap((k) => e[k]), e.watch || ''].join(' ');
    assert.doesNotMatch(all, /\b(TODO|TBD|FIXME)\b/, `${id}: no placeholders`);
  }
});

test('every entry says something of its own (no two share a what-line)', () => {
  const seen = new Set();
  for (const id of G.ids()) { const w = G.get(id).what; assert.ok(!seen.has(w), `${id}: its own words`); seen.add(w); }
});
