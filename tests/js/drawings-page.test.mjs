import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';

/* The chart page's drawing keys and switches (2026-10-27): Alt + key tools, Stay in drawing mode, Cmd+C / Cmd+V, Hide all
   drawings, and the Objects list's Delete on a locked drawing. Functions lifted from app.js and run against stand-ins. */
const require = createRequire(import.meta.url);
const C = require('../../homebase/static/charts/catalog.js');
const SRC = readFileSync(new URL('../../homebase/static/charts/app.js', import.meta.url), 'utf8');
const lift = (name) => {
  const m = new RegExp(`^function ${name}\\(`, 'm').exec(SRC);
  assert.ok(m, `app.js defines ${name}`);
  return SRC.slice(m.index, SRC.indexOf('\n}\n', m.index) + 2);
};
const key = (code, o = {}) => ({ code, altKey: false, metaKey: false, ctrlKey: false, shiftKey: false, repeat: false, prevented: false,
  preventDefault() { this.prevented = true; }, ...o });

function page({ stay = false, hidden = false } = {}) {
  const log = [], store = {};
  const dc = (list) => ({ root: 'NQ', sel: null, refreshed: 0, selected: null, pasted: [],
    copySelected() { return this.selected; }, paste(d) { this.pasted.push(d); return d.alert ? null : { ...d, id: 'new' }; },
    refresh() { this.refreshed += 1; } });
  const cells = [{ dc: dc() }, { dc: dc() }, { dc: null }];
  const ctx = vm.createContext({ C, cells, log, store, localStorage: { setItem: (k, v) => { store[k] = v; } },
    setTool: (t) => log.push(['setTool', t]), pickTool: (t) => log.push(['pickTool', t]), sbNote: (t) => log.push(['note', t]),
    markDirty: () => log.push(['dirty']), menuEl: null, hotkeyBox: null,
    $: () => ({ setAttribute() {}, title: '' }), drawingsPatch: [] });
  vm.runInContext(`let stayDrawing = ${stay}, drawingsHidden = ${hidden}, copiedDrawing = null; const STAY_KEY = 'hb_stay_draw';
    ${lift('toolDone')}
    ${lift('toolHotkey')}
    ${lift('drawingClipboard')}
    ${lift('toggleDrawingsHidden')}
    globalThis.api = { toolDone, toolHotkey, drawingClipboard, toggleDrawingsHidden, get hidden() { return drawingsHidden; }, get copied() { return copiedDrawing; } };`, ctx);
  return { api: ctx.api, log, cells, store };
}

test('after a placement the tool goes back to the cursor; with Stay in drawing mode it stays', () => {
  const off = page();
  off.api.toolDone();
  assert.deepEqual(off.log, [['setTool', 'cursor']]);
  const on = page({ stay: true });
  on.api.toolDone();
  assert.deepEqual(on.log, []);
});

test('Alt + a tool key picks that tool and eats the key; Alt+R, other Alt keys, Cmd/Ctrl/Shift combos and repeats do not', () => {
  const p = page();
  const t = key('KeyT', { altKey: true });
  assert.equal(p.api.toolHotkey(t), true);
  assert.equal(t.prevented, true);
  assert.deepEqual(p.log, [['pickTool', 'trend']]);
  for (const e of [key('KeyR', { altKey: true }), key('KeyT'), key('KeyT', { altKey: true, metaKey: true }), key('KeyT', { altKey: true, ctrlKey: true }),
    key('KeyT', { altKey: true, shiftKey: true }), key('KeyT', { altKey: true, repeat: true }), key('KeyQ', { altKey: true })]) {
    assert.equal(p.api.toolHotkey(e), false);
    assert.equal(e.prevented, false);
  }
  assert.equal(p.log.length, 1);
});

test('Cmd+C copies the selected drawing; Cmd+V pastes a clone onto the same symbol only', () => {
  const p = page();
  const dc = p.cells[0].dc, trend = { id: 'a', type: 'trend', points: [] };
  const copy = key('KeyC', { metaKey: true });
  assert.equal(p.api.drawingClipboard(copy, p.cells[0]), false, 'nothing selected: the browser keeps its copy');
  assert.equal(copy.prevented, false);
  dc.selected = trend;
  assert.equal(p.api.drawingClipboard(key('KeyC', { metaKey: true }), p.cells[0]), true);
  assert.equal(p.api.copied.d, trend);
  assert.equal(p.api.drawingClipboard(key('KeyV', { ctrlKey: true }), p.cells[1]), true);   // Ctrl on Windows
  assert.deepEqual(dc.pasted.length + p.cells[1].dc.pasted.length, 1);
  assert.deepEqual(p.log.filter((x) => x[0] === 'dirty').length, 1);
  p.cells[1].dc.root = 'ES';
  assert.equal(p.api.drawingClipboard(key('KeyV', { metaKey: true }), p.cells[1]), true);
  assert.deepEqual(p.cells[1].dc.pasted.length, 1, 'ES chart: nothing pasted');
  assert.match(p.log.at(-1)[1], /NQ/);
  assert.equal(p.api.drawingClipboard(key('KeyV', { metaKey: true, altKey: true }), p.cells[0]), false);
  assert.equal(p.api.drawingClipboard(key('KeyV'), p.cells[0]), false, 'no modifier: not ours');
  assert.equal(p.api.drawingClipboard(key('KeyV', { metaKey: true }), p.cells[2]), false, 'a chart with no drawing layer');
});

test('a price alert is not copied', () => {
  const p = page();
  p.cells[0].dc.selected = { id: 'al', type: 'hline', alert: { dir: 'up', fired: false }, points: [] };
  assert.equal(p.api.drawingClipboard(key('KeyC', { metaKey: true }), p.cells[0]), true);
  assert.equal(p.api.copied, null);
  assert.match(p.log.at(-1)[1], /alert/i);
});

test('Hide all drawings flips for the session (not saved) and redraws every chart', () => {
  const p = page();
  p.api.toggleDrawingsHidden();
  assert.equal(p.api.hidden, true);
  assert.deepEqual(p.cells.map((c) => c.dc && c.dc.refreshed), [1, 1, null]);
  p.api.toggleDrawingsHidden();
  assert.equal(p.api.hidden, false);
  assert.deepEqual(p.store, {}, 'nothing written to storage: a reload shows the drawings again');
});

test('the Objects list: Delete is off for a locked drawing, Hide / Show is there, and the host hands the controller the switch', () => {
  assert.match(SRC, /del\.disabled = !!d\.locked/);
  assert.match(SRC, /hidden: !d\.hidden/);
  assert.match(SRC, /drawingsHidden: \(\) => drawingsHidden/);
  assert.match(SRC, /toolDone,/);
  assert.match(SRC, /allDrawingsHidden: drawingsHidden/);
});
