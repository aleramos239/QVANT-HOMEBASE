import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* The readiness list lets the owner check a concern off (2026-10-28): amber goes grey and leaves the bulb, red is only marked
   seen and keeps the bulb red; the check is kept for the trading day by label + words, so a changed detail brings it back. */
import { HTML } from './deskpage.mjs';
const between = (a, b) => HTML.slice(HTML.indexOf(a), HTML.indexOf(b));
const BANNER = between('const FIRE_AT', "/* ---- the desk's notices ----");
const esc = (v) => String(v == null ? '' : v).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

function load(day = '2026-10-28') {
  const store = {};
  const ST = { et_now: day + 'T10:00:00-04:00', book: {}, strategies: {}, journal: [] };
  const ctx = vm.createContext({ ST, esc, window: {}, Date, JSON, Set,
    localStorage: { getItem: (k) => store[k] ?? null, setItem: (k, v) => { store[k] = v; } } });
  vm.runInContext(BANNER + `globalThis.api = { readinessShown, chkKey, ackSet };`, ctx);
  const set = (keys) => { store['hb.chk.ack'] = JSON.stringify({ day: ST.et_now.slice(0, 10), keys }); };
  return { api: ctx.api, ST, store, set };
}
const WARN = { level: 'warn', label: 'Disk', detail: '90 % full' };
const BAD = { level: 'bad', label: 'Clock', detail: 'off by 4 s' };
const R = { ready: false, checks: [WARN, BAD, { level: 'ok', label: 'Feed', detail: 'flowing' }] };

test('nothing checked off: the list is as the desk sent it', () => {
  const { api, ST } = load();
  assert.equal(api.readinessShown(R, ST), R);
});

test('a checked-off amber turns grey info and is marked; a checked-off red stays red and is marked', () => {
  const { api, ST, set } = load();
  set([api.chkKey(WARN), api.chkKey(BAD)]);
  const [w, b, ok] = api.readinessShown(R, ST).checks;
  assert.deepEqual([w.level, w.acked], ['info', true]);
  assert.deepEqual([b.level, b.acked], ['bad', true]);
  assert.equal(ok.acked, undefined);
  assert.equal(api.chkKey(w), api.chkKey(WARN), 'the grey row keeps its key, so the switch can turn it back on');
});

test('a changed detail, or another day, brings the concern back', () => {
  const { api, ST, set } = load();
  set([api.chkKey(WARN)]);
  const moved = { ...R, checks: [{ ...WARN, detail: '95 % full' }] };
  assert.equal(api.readinessShown(moved, ST).checks[0].level, 'warn');
  ST.et_now = '2026-10-29T10:00:00-04:00';
  assert.equal(api.readinessShown(R, ST).checks[0].level, 'warn');
});

test('every concern row has a switch, wired to one handler', () => {
  const body = between('function renderChecks()', 'function openChecks()');
  assert.match(body, /role="switch"/);
  assert.match(body, /data-ack=/);
  assert.match(HTML, /closest\("\[data-ack\]"\)/);
});

test('the Desk checkbox is the same on/off switch as the rest (apple skin), a row account value is today\'s P&L', () => {
  const css = readFileSync(new URL('../../homebase/static/apple/desk.css', import.meta.url), 'utf8');
  assert.match(css, /input\[type="checkbox"\]\) \{ appearance: none;[^}]*width: 36px; height: 16px/);
  assert.match(css, /input\[type="checkbox"\]:checked\)::after \{ transform: translateX\(11px\)/);
  const row = between('function acctRow(', '/* ---- the book (assignments) ---- */');
  assert.match(row, /const pnl = a\.day_pnl/);
});
