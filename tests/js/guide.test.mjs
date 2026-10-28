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

test('every TradingView study says it matches TradingView\'s built-in, and none is a copy of a house entry', () => {
  const tv = G.ids().filter((id) => id.startsWith('tv_'));
  assert.equal(tv.length, 90);
  for (const id of tv) {
    assert.match(G.get(id).watch || '', /^Matches TradingView's built-in [^.]+\./, `${id}: watch names the TradingView built-in`);
    assert.equal(C.def(id).group, 'TradingView', `${id}: lives in the TradingView group`);
  }
});

test('a TradingView entry only talks about a Source box and a drawing style its Settings and chart really have', () => {
  for (const id of G.ids().filter((x) => x.startsWith('tv_'))) {
    const e = G.get(id), d = C.def(id);
    if (/\bSource\b/.test(e.see.join(' '))) assert.ok(d.params.some((q) => q.key === 'source'), `${id}: its help names a Source box it does not have`);
    if (d.lines.some((l) => l.dots)) assert.doesNotMatch([...e.see, ...e.read, e.watch].join(' '), /joined line|\bthe line\b/, `${id}: drawn as dots, not a joined line`);
  }
});

test('every order-flow app says which app\'s documented behaviour it follows; the footprint and profile name the rules they can switch to', () => {
  for (const id of ['bigtrades', 'npoc', 'tpo', 'cstat', 'dturn', 'dstr', 'mwabs']) {
    assert.match(G.get(id).watch || '', /^Follows [^.]*(ATAS|Exocharts|Sierra|MotiveWave|Bookmap)/, `${id}: watch names the app`);
  }
  assert.match(G.get('footprint').use.join(' '), /ATAS, Exocharts or Sierra/);
  assert.match(G.get('profile').use.join(' '), /Sierra Chart or TradingView/);
});

test('a TradingView entry promises only the dashed reference lines its catalog entry draws (its refs)', () => {
  const NUM = '-?\\d+(?:\\.\\d+)?', re = new RegExp(`dashed lines? at (zero|${NUM}(?: and ${NUM})?)`);
  let seen = 0;
  for (const id of G.ids().filter((x) => x.startsWith('tv_'))) {
    const e = G.get(id), m = re.exec([e.what, ...e.see, ...e.read, ...e.use, e.watch || ''].join(' '));
    if (!m) continue;
    seen++;
    const want = m[1] === 'zero' ? [0] : m[1].split(' and ').map(Number);
    assert.deepEqual(want.filter((x) => !(C.refsOf(id) || []).includes(x)), [], `${id}: its help says "${m[0]}" but the chart draws ${JSON.stringify(C.refsOf(id))}`);
  }
  assert.ok(seen > 20, `the check found ${seen} entries that name a reference line: has the wording changed?`);
  assert.doesNotMatch(G.get('tv_rvgi').see.join(' '), /dashed/);
  assert.doesNotMatch(G.get('tv_cog').see.join(' '), /dashed/);
  assert.match(G.get('tv_bbtrend').see.join(' '), /dashed line at zero/, 'BBTrend draws its zero line');
});

test('a TradingView entry that says "Length N by default" says the length its catalog entry starts with', () => {
  for (const id of G.ids().filter((x) => x.startsWith('tv_'))) {
    const m = /\bLength (\d+) by default/.exec(G.get(id).see.join(' ')), q = C.def(id).params.find((x) => x.key === 'length');
    if (m && q) assert.equal(q.def, +m[1], `${id}: help says Length ${m[1]}, Settings start at ${q.def}`);
  }
  assert.equal(C.def('tv_kama').params[0].def, 10, "TradingView's KAMA starts at ER length 10");
});

test('Pivot HL and Fractals: the help says a bar that is both draws both arrows, as the chart does', () => {
  for (const id of ['tv_pivothl', 'tv_fractals']) {
    assert.match(G.get(id).watch, /\bboth arrows\b/, id);
    assert.doesNotMatch(G.get(id).watch, /One mark per bar|shows the (high|top)/, id);
  }
});

test('Bollinger Bandwidth: the help says the width is a percent of the middle line, as TradingView plots it', () => {
  assert.match(G.get('tv_bbw').what, /\bpercent\b/);
});

test('CVD, Volume Delta and Up/Down Volume say candle direction, the rule the code uses, not tick sides', () => {
  for (const id of ['tv_cvd', 'tv_vdelta', 'tv_updown']) {
    const e = G.get(id), text = [e.what, ...e.see, ...e.read, ...e.use, e.watch].join(' ');
    assert.match(text, /candle/i, id);
    assert.doesNotMatch(text, /uptick|downtick|buy volume minus sell volume/i, id);
  }
  assert.match(G.get('tv_cvd').watch, /Cumulative delta/, 'points to the real trade sides');
  assert.match(G.get('tv_vdelta').watch, /Delta/, 'points to the real trade sides');
});

test('the order-flow marks that read the candle in progress say so, and none claims to never repaint', () => {
  for (const id of ['stoprun', 'exhaust', 'dturn', 'dstr']) assert.match(G.get(id).watch, /close|progress|forming/i, `${id}: watch warns about the open candle`);
  assert.doesNotMatch(G.get('exhaust').read.join(' '), /never repaints/);
});
