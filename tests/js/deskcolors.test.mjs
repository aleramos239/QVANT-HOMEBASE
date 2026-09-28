import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

/* The desk page's status colours come from the theme (2026-09-28, Apple-design audit W6): the
   connectivity bulb and the System checks list used hard-coded hex (#22c55e / #f59e0b / #ef4444 /
   #94a3b8) that could drift from the rest of the page's good/bad language and ignored dark mode.
   They now read --pos / --warn / --neg (and --muted-foreground for info); --warn is a new token
   with a light and a dark value in shadcn.css. */
const HTML = readFileSync(new URL('../../homebase/static/index.html', import.meta.url), 'utf8');
const CSS = readFileSync(new URL('../../homebase/static/shadcn.css', import.meta.url), 'utf8');

test('no hard-coded status hex is left on the desk page', () => {
  for (const hex of ['#22c55e', '#f59e0b', '#ef4444', '#94a3b8']) {
    assert.ok(!HTML.toLowerCase().includes(hex), hex);
  }
  assert.doesNotMatch(HTML, /rgb\((34 197 94|245 158 11|239 68 68)/);
});

test('the bulb and the checks list read the theme tokens', () => {
  assert.match(HTML, /\.bulb\.ok\{ background:var\(--pos\)/);
  assert.match(HTML, /\.bulb\.warn\{ background:var\(--warn/);
  assert.match(HTML, /\.bulb\.bad\{ background:var\(--neg\)/);
  const chk = HTML.slice(HTML.indexOf('const CHK_COLOR'), HTML.indexOf('function bulbLevel'));
  assert.match(chk, /ok: "var\(--pos\)"/);
  assert.match(chk, /info: "var\(--muted-foreground\)"/);
  assert.match(chk, /warn: "var\(--warn/);
  assert.match(chk, /bad: "var\(--neg\)"/);
});

test('--warn is a theme token with its own light and dark values', () => {
  const light = CSS.slice(CSS.indexOf(':root,'), CSS.indexOf(':root[data-theme="dark"]'));
  const dark = CSS.slice(CSS.indexOf(':root[data-theme="dark"]'));
  const lw = /--warn: (oklch\([^)]*\));/.exec(light), dw = /--warn: (oklch\([^)]*\));/.exec(dark.slice(0, dark.indexOf('}')));
  assert.ok(lw && dw, 'defined in both themes');
  assert.notEqual(lw[1], dw[1], 'tuned per theme');
});
