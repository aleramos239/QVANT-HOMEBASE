import { test } from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';

/* The Settings card "Backtests" (static/desk/settings.js): read-only, from /api/status `backtests`. The Mac says how many
   run at once and how many run now; the server says plainly it never runs backtests. No button, no field. */
import { HTML } from './deskpage.mjs';
const BLOCK = HTML.slice(HTML.indexOf('/* ---- Backtests (read-only)'), HTML.indexOf('/* ---- Server updates (read-only)'));
const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function load() {
  const root = { innerHTML: '' };
  const ctx = vm.createContext({ esc, $: (s) => (s === '#settingsBacktests' ? root : null) });
  vm.runInContext(BLOCK + 'globalThis.api = { backtestWords, renderBacktests };', ctx);
  return { api: ctx.api, root };
}
const mac = { off: false, cap: 12, until: '2027-01-01T00:00:00-05:00', then: { desk: 2, other: 4 }, running: 3, quiet: false };

test('the Mac says how many run at once and how many run now', () => {
  const { api } = load();
  assert.equal(api.backtestWords(mac), 'Up to 12 at once · 3 running now');
  assert.equal(api.backtestWords({ ...mac, running: 1, quiet: true }), 'Up to 12 at once · 1 running now · paused for a quiet window');
  assert.equal(api.backtestWords({ ...mac, running: 0 }), 'Up to 12 at once · none running now');
});

test('the server never runs backtests', () => {
  const { api } = load();
  assert.equal(api.backtestWords({ off: true }), 'This server never runs backtests. Run them on the Mac.');
});

test('the card: the line first, the date the cap ends, no button, nothing when the answer is missing', () => {
  const { api, root } = load();
  api.renderBacktests(mac);
  assert.match(root.innerHTML, /BACKTESTS/);
  assert.match(root.innerHTML, /Up to 12 at once · 3 running now/);
  assert.match(root.innerHTML, /until 2027-01-01.*2 in desk hours, 4 other times/);
  assert.doesNotMatch(root.innerHTML, /<button|<input|onclick/);
  api.renderBacktests({ off: true });
  assert.match(root.innerHTML, /never runs backtests/);
  assert.doesNotMatch(root.innerHTML, /until/);
  api.renderBacktests(undefined);
  assert.equal(root.innerHTML, '');
});

test('an unchanged answer does not repaint', () => {
  const { api, root } = load();
  api.renderBacktests(mac);
  root.innerHTML = 'kept';
  api.renderBacktests({ ...mac });
  assert.equal(root.innerHTML, 'kept');
});
