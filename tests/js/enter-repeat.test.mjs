import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

/* S7 (2026-09-28 safety pass): every Enter key handler on the chart page ignores a held key's auto-repeat --
   GOTCHAS.md: "Any Enter/Space that confirms or sends must ignore e.repeat. A held key has sent duplicate orders here
   before." A static sweep of every homebase/static/charts/*.js: each line that tests for the Enter key must read
   `repeat` on that line or the next two (tradeui.js's confirm reads it one line down, through enterConfirms). A new
   Enter handler without the guard fails here, whatever it submits. The behaviour itself is exercised in
   presets.test.mjs and settings-dialog.test.mjs (Save as… saves once per press), tradeui.test.mjs (the confirm). */
const DIR = path.join(path.dirname(fileURLToPath(import.meta.url)), '../../homebase/static/charts');
const ENTER = /\bkey\s*[!=]==?\s*['"]Enter['"]/;

test('S7: every Enter key handler in the chart page ignores e.repeat', () => {
  const seen = [], misses = [];
  for (const f of readdirSync(DIR).filter((n) => n.endsWith('.js')).sort()) {
    const lines = readFileSync(path.join(DIR, f), 'utf8').split('\n');
    lines.forEach((line, i) => {
      if (!ENTER.test(line.replace(/\/\/ .*$/, ''))) return;   // code only: a trailing "// ..." comment is not a handler
      seen.push(`${f}:${i + 1}`);
      if (!/\brepeat\b/.test(lines.slice(i, i + 3).join('\n'))) misses.push(`${f}:${i + 1}: ${line.trim()}`);
    });
  }
  // the sweep itself must still be finding the handlers (app.js alone has eight)
  assert.ok(seen.length >= 15, `the sweep found only ${seen.length} Enter handlers: ${seen.join(', ')}`);
  assert.deepEqual(misses, [], 'Enter handlers with no e.repeat guard');
});
