import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

/* WP1.13: the Desk says things in words: no "portfolio"; and no 09:20-09:35 refusal is left anywhere on the page (the owner removed that window 2026-10-16). */
import { HTML } from './deskpage.mjs';
const between = (a, b) => { const i = HTML.indexOf(a); return HTML.slice(i, HTML.indexOf(b, i)); };

test('no "portfolio" copy in the Desk scripts', () => {
  assert.doesNotMatch(HTML, />Backtest metrics</);
  assert.doesNotMatch(between('/* ---- connect wizard ---- */', '/* ---- accounts popup ---- */'), /portfolio/);
});

test('no 09:20 / 09:35 refusal is left on the Desk page', () => {
  // the demo journal's 09:20:04 timer line is sample data, not a refusal
  const hits = [...HTML.matchAll(/[^\n]*\b0?9:(20|35)\b[^\n]*/g)].map((m) => m[0].trim())
    .filter((l) => !/et: "2026-09-16T09:20:04", event: "timer_gate"/.test(l));
  assert.deepEqual(hits, []);
});

test('acctTag: PAPER, PROP, LIVE (also an unknown account), else DEMO', () => {
  const ctx = vm.createContext({ ST: { accounts: { p: { env: 'paper' }, q: { env: 'demo', prop: true }, l: { env: 'live' }, d: { env: 'demo' } } } });
  vm.runInContext(between('function acctTag(', '/* The size on an account row') + ';this.acctTag = acctTag;', ctx);
  assert.deepEqual(['p', 'q', 'l', 'zz', 'd'].map((id) => ctx.acctTag(id)), ['PAPER', 'PROP', 'LIVE', 'LIVE', 'DEMO']);
});

test('the page uses one word per thing', () => {
  const code = HTML.replace(/\/\*[\s\S]*?\*\//g, '').replace(/<!--[\s\S]*?-->/g, '').replace(/^\s*\/\/.*$/gm, '').replace(/\s\/\/ .*$/gm, '')
    .replace(/\.practice\b/g, '');
  assert.doesNotMatch(code, /\bdisarm/i, 'no "disarm"');
  const words = code.replace(/\/api\/arm\b|\.armed\b|\barmed:|pill armed|\(armed \?|armed\)/g, '')
    .replace(/\barm\b(?=\s*[=.)])/g, '').replace(/\barmed\b(?=\s*[=?:])/g, '');      // identifiers, routes and CSS classes
  assert.doesNotMatch(words, /\barm(ed|s)?\b/i, 'no "arm" / "armed"');
  for (const w of ['account group', 'account cycle', 'ARMED', 'DISARMED', 'Remove from Desk', 'Day take', 'practice'])
    assert.ok(!(w === w.toUpperCase() ? code.includes(w) : code.toLowerCase().includes(w.toLowerCase())), `the page still says "${w}"`);
});

test('an account row shows the tag acctTag says (live + prop is PROP, demo + prop is PROP)', () => {
  const ST = { accounts: { l: { env: 'live', label: 'L', prop: true }, d: { env: 'demo', label: 'D', prop: true }, p: { env: 'paper', label: 'P' }, o: { env: 'demo', label: 'O' } } };
  const ctx = vm.createContext({ ST, esc: (x) => x, usd: (x) => x, AcctSet: { label: () => '', tag: () => '' }, DAY_PNL_WORDS: () => '', jsArg: (x) => x });
  vm.runInContext(between('const PROP_TAG', '/* The size on an account row') +
    between('function acctRow(', '</div>`;\n}') + '</div>`;\n}' + ';this.f = {acctTag, acctRow};', ctx);
  for (const id of ['l', 'd', 'p', 'o', 'zz']) {
    const w = ctx.f.acctTag(id);
    assert.ok(ctx.f.acctRow(id, {}).includes('>' + w + '</span>'), id + ' shows ' + w);
  }
  assert.equal(ctx.f.acctTag('l'), 'PROP');
});
