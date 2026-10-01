import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* The desk page's (homebase/static/index.html, :8850) status tokens, 2026-09-28 (Apple-design audit
   S4). One solid pill (.pill.live) used to mean four things: the desk is ARMED, an account trades
   real money, a strategy holds a position, a strategy is switched on. Each now has its own look:
     ARMED        .pill.armed -- solid red with a light (the page's only solid red token)
     LIVE account .tag-live   -- a red outline tag, never filled
     in position  .pill.inpos -- solid black/white, labelled "in position" (the desk's "live")
     ON           .pill.on    -- an outline with a dot */
const HTML = readFileSync(new URL('../../homebase/static/index.html', import.meta.url), 'utf8');
const STYLE = HTML.slice(HTML.indexOf('<style>'), HTML.indexOf('</style>'));
const rule = (sel) => {
  const i = STYLE.indexOf(sel + '{');
  assert.ok(i >= 0, `no ${sel} rule`);
  return STYLE.slice(i, STYLE.indexOf('}', i) + 1);
};

test('the overloaded .pill.live is gone -- no rule, no use', () => {
  assert.doesNotMatch(HTML, /\.pill\.live\b/);
  assert.doesNotMatch(HTML, /class="pill live"|"pill live"/);
});

test('ARMED, LIVE, in position and ON each have their own, different look', () => {
  const armed = rule('.pill.armed'), live = rule('.tag-live'), inpos = rule('.pill.inpos'), on = rule('.pill.on');
  assert.match(armed, /background:color-mix\(in oklch, var\(--destructive\)/, 'ARMED is filled red');
  assert.match(rule('.pill.armed::before'), /border-radius:9999px/, 'ARMED carries a light');
  assert.match(live, /background:var\(--card\)/, 'LIVE is an outline, never filled with red (solid card behind it on the glass)');
  assert.doesNotMatch(live, /background:[^;]*destructive/);
  assert.match(live, /border:1px solid color-mix\(in oklch, var\(--destructive\)/);
  assert.match(inpos, /background:var\(--primary\)/, 'a position is solid black/white, not red');
  assert.doesNotMatch(inpos, /destructive|--neg/);
  assert.match(on, /background:transparent/);
  assert.doesNotMatch(on, /destructive|--neg/);
  assert.equal(new Set([armed, live, inpos, on].map((r) => r.slice(r.indexOf('{')))).size, 4);
});

test('the day status: "live" reads "in position", "placed" reads "orders working"; the desk\'s word stays in the tooltip', () => {
  const block = HTML.slice(HTML.indexOf("/* A strategy's day status as a pill"), HTML.indexOf('/* ===== Desk views'));
  const ctx = vm.createContext({});
  vm.runInContext(block + '\nglobalThis.dayPill = dayPill;', ctx);
  assert.equal(ctx.dayPill('live'), '<span class="pill inpos" title="Today: live">in position</span>');
  assert.equal(ctx.dayPill('placed'), '<span class="pill" title="Today: placed">orders working</span>');
  assert.equal(ctx.dayPill('placing'), '<span class="pill" title="Today: placing">placing</span>');
  assert.equal(ctx.dayPill('error'), '<span class="pill lost" title="Today: error">error</span>');
  assert.equal(ctx.dayPill('idle'), '<span class="pill idle" title="Today: idle">idle</span>');
});

test('a live account carries the LIVE tag, a demo account none; the algo manager\'s ON is the ON pill', () => {
  const block = HTML.slice(HTML.indexOf('/* ---- account row (rendered inside strategy cards) ---- */'),
    HTML.indexOf('/* ---- the book (assignments) ---- */'));
  const ctx = vm.createContext({
    ST: { accounts: { a: { label: 'APEX1', env: 'live', connected: true, balance: 1, realized_pnl: 0 },
                      b: { label: 'Sim', env: 'demo', connected: true, balance: 1, realized_pnl: 0 } } },
    usd: (v) => '$' + v,
  });
  const escDefs = HTML.slice(HTML.indexOf('const esc = (v) =>'), HTML.indexOf('async function chartPost('));
  vm.runInContext(escDefs + block + '\nglobalThis.acctRow = acctRow;', ctx);
  assert.match(ctx.acctRow('a', {}), /<span class="tag-live" title="A live account — real money">LIVE<\/span>/);
  assert.doesNotMatch(ctx.acctRow('b', {}), /LIVE/);
  assert.match(HTML, /`<span class="pill on" title="Switched on">ON<\/span>`/);
  assert.match(HTML, /<span class="tag-live" style="vertical-align:middle" title="A live login — real money">LIVE<\/span>/,
    "the connect wizard's LIVE login tag is the account tag too");
});
