import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const L = require('../../homebase/static/charts/labcode.js');

/* the list as it is painted: a saved strategy is 'd:<name>' (id draft_<name>), a built-in 'b:<id>' and locked */
const d = (n) => ({ key: `d:${n}`, id: `draft_${n}`, name: n });
const b = (n) => ({ key: `b:${n}`, id: n, name: n, lock: true });
const unsaved = { key: 'n:1', name: 'Untitled' };
const keys = (rows) => rows.map((r) => r.key);

const groups = { groups: ['Fades', 'Empty'], members: { draft_a: 'Fades', draft_c: 'Fades', draft_e: 'Fades' } };
const rows = [d('a'), d('b'), d('c'), d('d'), d('e'), unsaved, b('nq930'), b('es_orb')];

test('shownRows: the list in the order it is shown, groups first, and what a folded group holds is not shown', () => {
  const secs = L.sections(rows, groups);
  assert.deepEqual(keys(L.shownRows(secs, new Set())), ['d:a', 'd:c', 'd:e', 'd:b', 'd:d', 'n:1', 'b:nq930', 'b:es_orb']);
  assert.deepEqual(keys(L.shownRows(secs, new Set(['Fades']))), ['d:b', 'd:d', 'n:1', 'b:nq930', 'b:es_orb']);
  assert.deepEqual(keys(L.shownRows(secs, new Set(['']))), ['d:a', 'd:c', 'd:e']);      // Ungrouped folds too
});

test('canPick: a saved strategy only -- a locked one, an unsaved one and a tool are never picked', () => {
  assert.equal(L.canPick(d('a')), true);
  assert.equal(L.canPick(b('nq930')), false);
  assert.equal(L.canPick(unsaved), false);
  assert.equal(L.canPick(null), false);
  assert.equal(L.canPick({ key: 'd:x', lock: true }), false);
});

test('pickRange: from the anchor to the clicked row, in the shown order, locked rows skipped, either direction', () => {
  const shown = L.shownRows(L.sections(rows, groups), new Set());       // a c e b d n b: nq930 es_orb
  assert.deepEqual(L.pickRange(shown, 'd:c', 'd:d'), ['d:c', 'd:e', 'd:b', 'd:d']);       // across the group edge
  assert.deepEqual(L.pickRange(shown, 'd:d', 'd:c'), ['d:c', 'd:e', 'd:b', 'd:d']);       // upward: same rows, shown order
  assert.deepEqual(L.pickRange(shown, 'd:d', 'b:es_orb'), ['d:d']);                         // the unsaved and locked rows are skipped
  assert.deepEqual(L.pickRange(shown, 'b:nq930', 'd:b'), ['d:b', 'd:d']);                   // a locked anchor adds nothing of its own
  assert.deepEqual(L.pickRange(shown, 'd:a', 'd:a'), ['d:a']);
});

test('pickRange: no anchor (or one that is not shown) picks the clicked row alone; a locked click with no anchor picks nothing', () => {
  const shown = L.shownRows(L.sections(rows, groups), new Set(['Fades']));
  assert.deepEqual(L.pickRange(shown, '', 'd:d'), ['d:d']);
  assert.deepEqual(L.pickRange(shown, 'd:a', 'd:d'), ['d:d']);          // d:a is folded away: not an anchor
  assert.deepEqual(L.pickRange(shown, '', 'b:nq930'), []);
  assert.deepEqual(L.pickRange(shown, 'd:b', 'd:zzz'), []);             // not in the list at all
});

test('a range never reaches into a folded group', () => {
  const shown = L.shownRows(L.sections(rows, groups), new Set(['Fades']));       // b d n nq930 es_orb
  assert.deepEqual(L.pickRange(shown, 'd:b', 'd:d'), ['d:b', 'd:d']);
});

test('rowClick, plain: opens the strategy, clears the picks, and the row is the new anchor', () => {
  const shown = L.shownRows(L.sections(rows, groups), new Set());
  const got = L.rowClick({ picks: ['d:a', 'd:c'], anchor: 'd:a', cur: 'd:a' }, shown, 'd:b', {});
  assert.deepEqual(got, { picks: [], anchor: 'd:b', open: true });
  assert.deepEqual(L.rowClick({ picks: [], anchor: '', cur: null }, shown, 'b:nq930', {}), { picks: [], anchor: 'b:nq930', open: true });
});

test('rowClick, shift: the range from the last picked row, or the open row when nothing is picked; it opens nothing', () => {
  const shown = L.shownRows(L.sections(rows, groups), new Set());
  const open = L.rowClick({ picks: [], anchor: '', cur: 'd:c' }, shown, 'd:d', { shift: true });
  assert.deepEqual(open, { picks: ['d:c', 'd:e', 'd:b', 'd:d'], anchor: 'd:c', open: false });
  const again = L.rowClick({ picks: ['d:c', 'd:e', 'd:b', 'd:d'], anchor: 'd:c', cur: 'd:c' }, shown, 'd:e', { shift: true });
  assert.deepEqual(again, { picks: ['d:c', 'd:e'], anchor: 'd:c', open: false });       // the range shrinks to the new end
  const none = L.rowClick({ picks: [], anchor: '', cur: null }, shown, 'd:b', { shift: true });
  assert.deepEqual(none, { picks: ['d:b'], anchor: 'd:b', open: false });
});

test('rowClick, cmd or ctrl: adds or removes one row; a locked row does nothing', () => {
  const shown = L.shownRows(L.sections(rows, groups), new Set());
  let st = { picks: [], anchor: '', cur: 'd:a' };
  let got = L.rowClick(st, shown, 'd:d', { meta: true });
  assert.deepEqual(got, { picks: ['d:d'], anchor: 'd:d', open: false });
  got = L.rowClick({ ...st, ...got }, shown, 'd:b', { meta: true });
  assert.deepEqual(got.picks, ['d:b', 'd:d']);                                          // always in the shown order
  got = L.rowClick({ ...st, ...got }, shown, 'd:d', { meta: true });
  assert.deepEqual(got, { picks: ['d:b'], anchor: 'd:d', open: false });
  assert.deepEqual(L.rowClick({ picks: ['d:a'], anchor: 'd:a', cur: null }, shown, 'b:nq930', { meta: true }), { picks: ['d:a'], anchor: 'd:a', open: false });
});

test('prunePicks: a pick that is no longer shown (folded, deleted, a tool view) drops out', () => {
  const secs = L.sections(rows, groups);
  assert.deepEqual(L.prunePicks(['d:b', 'd:a', 'd:gone'], L.shownRows(secs, new Set())), ['d:a', 'd:b']);
  assert.deepEqual(L.prunePicks(['d:b', 'd:a'], L.shownRows(secs, new Set(['Fades']))), ['d:b']);
});

test('the delete item reads "Delete…", or "Delete N strategies…" on a picked row when two or more are picked', () => {
  assert.equal(L.deleteItem(['d:a', 'd:b'], 'd:a'), 'Delete 2 strategies…');
  assert.equal(L.deleteItem(['d:a', 'd:b', 'd:c'], 'd:c'), 'Delete 3 strategies…');
  assert.equal(L.deleteItem(['d:a', 'd:b'], 'd:z'), 'Delete…');            // a row that is not picked deletes itself only
  assert.equal(L.deleteItem(['d:a'], 'd:a'), 'Delete…');
  assert.equal(L.deleteItem([], 'd:a'), 'Delete…');
});

test('deleteTargets: the picked names for a picked row of a pick of two or more, else the row alone', () => {
  assert.deepEqual(L.deleteTargets(['d:a', 'd:b'], 'd:b'), ['a', 'b']);
  assert.deepEqual(L.deleteTargets(['d:a', 'd:b'], 'd:z'), ['z']);
  assert.deepEqual(L.deleteTargets(['d:a'], 'd:a'), ['a']);
  assert.deepEqual(L.deleteTargets([], 'd:a'), ['a']);
});

test('the confirm for one strategy is the words the single delete has always had', () => {
  const c = L.deleteConfirm(['nq_orb']);
  assert.equal(c.title, 'Delete nq_orb?');
  assert.equal(c.body, 'Its file is removed from your strategies. Past backtests of it stay in Recent runs.');
  assert.deepEqual([c.keep, c.go], ['Keep it', 'Delete']);
  assert.deepEqual(c.names, []);
});

test('the confirm for several: title, the names (at most 8, then "and M more"), the line, the buttons', () => {
  const c = L.deleteConfirm(['a', 'b', 'c']);
  assert.equal(c.title, 'Delete 3 strategies?');
  assert.deepEqual(c.names, ['a', 'b', 'c']);
  assert.equal(c.more, '');
  assert.equal(c.body, 'Their files are removed from your strategies. Past backtests of them stay in Recent runs.');
  assert.deepEqual([c.keep, c.go], ['Keep them', 'Delete']);
  const eight = L.deleteConfirm(Array.from({ length: 8 }, (_, i) => `s${i}`));
  assert.equal(eight.names.length, 8); assert.equal(eight.more, '');
  const nine = L.deleteConfirm(Array.from({ length: 9 }, (_, i) => `s${i}`));
  assert.equal(nine.names.length, 8); assert.equal(nine.more, 'and 1 more');
  assert.equal(L.deleteConfirm(Array.from({ length: 20 }, (_, i) => `s${i}`)).more, 'and 12 more');
});

test('deleteConfirmHtml escapes every name and says what it says', () => {
  const html = L.deleteConfirmHtml(['a<b>', 'c&d']);
  assert.ok(html.includes('a&lt;b&gt;') && html.includes('c&amp;d') && !/a<b>/.test(html));
  assert.match(html, /<h2>Delete 2 strategies\?<\/h2>/);
  assert.match(html, /data-x="cancel">Keep them<\/button>/);
  assert.match(html, /data-x="go">Delete<\/button>/);
  const one = L.deleteConfirmHtml(['x<y']);
  assert.match(one, /<h2>Delete x&lt;y\?<\/h2>/);
  assert.match(one, /data-x="cancel">Keep it<\/button>/);
  assert.ok(L.deleteConfirmHtml(Array.from({ length: 10 }, (_, i) => `s${i}`)).includes('and 2 more'));
});

test('deleteLine: "Deleted N." or "Deleted N. Not deleted: name (reason), ..." with the server\'s own sentence', () => {
  assert.equal(L.deleteLine(3, []), 'Deleted 3.');
  assert.equal(L.deleteLine(1, [{ name: 'b', error: 'It is on the Desk. Remove it from the Desk first.' }]),
    'Deleted 1. Not deleted: b (It is on the Desk. Remove it from the Desk first.)');
  assert.equal(L.deleteLine(0, [{ name: 'a', error: 'x' }, { name: 'b', error: 'y' }]), 'Deleted 0. Not deleted: a (x), b (y)');
  assert.equal(L.deleteLine(2, [{ name: 'a' }]), 'Deleted 2. Not deleted: a (it could not be deleted)');
});

test('deleteKey: Delete or Backspace while the list has the keyboard and something is picked; never while typing, never held', () => {
  const ok = { picked: 2, inList: true, typing: false };
  assert.equal(L.deleteKey({ key: 'Delete' }, ok), true);
  assert.equal(L.deleteKey({ key: 'Backspace' }, ok), true);
  assert.equal(L.deleteKey({ key: 'Backspace', metaKey: true }, ok), true);        // ⌘⌫, as Finder
  assert.equal(L.deleteKey({ key: 'Delete', repeat: true }, ok), false);
  assert.equal(L.deleteKey({ key: 'Delete', ctrlKey: true }, ok), false);
  assert.equal(L.deleteKey({ key: 'Delete', altKey: true }, ok), false);
  assert.equal(L.deleteKey({ key: 'Enter' }, ok), false);
  assert.equal(L.deleteKey({ key: 'Delete' }, { ...ok, typing: true }), false);
  assert.equal(L.deleteKey({ key: 'Delete' }, { ...ok, inList: false }), false);
  assert.equal(L.deleteKey({ key: 'Delete' }, { ...ok, picked: 0 }), false);
  assert.equal(L.deleteKey({ key: 'Delete' }, { ...ok, dialog: true }), false);
});

test('isTyping: an input, a text area, a select, or editable text', () => {
  assert.equal(L.isTyping({ tagName: 'INPUT' }), true);
  assert.equal(L.isTyping({ tagName: 'TEXTAREA' }), true);
  assert.equal(L.isTyping({ tagName: 'SELECT' }), true);
  assert.equal(L.isTyping({ tagName: 'DIV', isContentEditable: true }), true);
  assert.equal(L.isTyping({ tagName: 'BUTTON' }), false);
  assert.equal(L.isTyping(null), false);
});

/* ---- the page: lab.js run against a small fake document, driven through the handlers it registers ---- */
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const LAB_SRC = readFileSync(new URL('../../homebase/static/charts/lab.js', import.meta.url), 'utf8');

function page({ drafts, groups, refuse = {} }) {
  const stub = (name) => new Proxy(function () {}, {
    get: (t, k) => (k === Symbol.toPrimitive ? () => '' : k === 'then' ? undefined : stub(`${name}.${String(k)}`)),
    set: () => true, apply: () => stub(`${name}()`), construct: () => stub('new') });
  const on = { root: {}, doc: [] };
  const lib = { innerHTML: '', scrollTop: 0 };
  const rec = (extra = {}) => {            // an element made by the page: it keeps what is put in it and what listens to it
    const el = { innerHTML: '', className: '', dataset: {}, listeners: {}, classList: { add() {}, remove() {}, toggle() {}, contains: () => false }, style: { setProperty() {} }, isConnected: true,
      addEventListener(t, f) { (el.listeners[t] = el.listeners[t] || []).push(f); }, remove() { el.isConnected = false; },
      getBoundingClientRect: () => ({ left: 10, right: 110, top: 10, bottom: 40, width: 100, height: 100 }),
      querySelector: () => null, querySelectorAll: () => [], setAttribute() {}, focus() {}, contains: () => false, appendChild() {}, ...extra };
    return el;
  };
  const made = [];
  const rootEl = { dataset: {}, style: stub('style'), classList: { add() {}, remove() {}, toggle() {}, contains: () => false },
    addEventListener: (t, f) => { (on.root[t] = on.root[t] || []).push(f); }, contains: () => false,
    querySelector: (s) => (s === '#labLib .in' ? lib : stub(`r ${s}`)), querySelectorAll: () => [] };
  const document = { getElementById: (id) => (id === 'lab' ? rootEl : stub(`#${id}`)), querySelector: (s) => (s === '.lab-bar' ? null : stub(s)),
    querySelectorAll: () => [], addEventListener: (t, f, cap) => on.doc.push({ t, f, cap }), body: rec(), activeElement: null, documentElement: stub('html'),
    createElement: () => {
      const el = rec();
      const inner = rec();
      Object.defineProperty(inner, 'innerHTML', { get: () => el.innerHTML });
      inner.querySelector = (s) => (s === 'h2' ? { id: '' } : null);
      el.firstElementChild = inner;
      made.push(el);
      return el;
    } };
  const requests = [];
  let list = drafts.map((n) => ({ name: n, id: `draft_${n}`, ok: true }));
  const route = (url, method) => {
    let m;
    if (method === 'GET' && url === '/api/tester/strategies') return [200, [{ id: 'nq930', name: 'NQ 930', root: 'NQ' }]];
    if (method === 'GET' && url === '/api/tester/drafts') return [200, list];
    if (method === 'GET' && url === '/api/tester/groups') return [200, groups];
    if (method === 'GET' && (m = /^\/api\/tester\/strategies\/draft_(\w+)\/source$/.exec(url))) return [200, { files: [{ path: `${m[1]}.py`, text: `# ${m[1]}\n` }] }];
    if (method === 'GET' && url === '/api/tester/runs') return [200, []];
    if (method === 'DELETE' && (m = /^\/api\/tester\/drafts\/(\w+)$/.exec(url))) {
      if (refuse[m[1]]) return [409, { detail: refuse[m[1]] }];
      list = list.filter((d) => d.name !== m[1]);
      return [200, { deleted: true }];
    }
    return [200, {}];
  };
  const win = { HBTester: stub('HBTester'), HBLabCode: L, addEventListener() {}, innerWidth: 1400, innerHeight: 900 };
  const ctx = { window: win, document, location: { hash: '', pathname: '/backtest', search: '' }, history: { replaceState() {} },
    localStorage: { getItem: () => null, setItem() {} }, setTimeout: () => 0, setInterval: () => 0, clearTimeout() {}, console,
    innerWidth: 1400, innerHeight: 900, Event: function () {}, CustomEvent: function () {}, performance: { now: () => 0 },
    matchMedia: () => ({ matches: false, addEventListener() {} }), getComputedStyle: () => ({ getPropertyValue: () => '' }),
    requestAnimationFrame: () => 0, ResizeObserver: function () { return { observe() {}, disconnect() {} }; },
    fetch: async (url, o) => { const method = (o && o.method) || 'GET'; requests.push(`${method} ${url}`); const [status, body] = route(url, method);
      return { ok: status < 400, status, json: async () => body }; } };
  Object.assign(win, { document, location: ctx.location, localStorage: ctx.localStorage, history: ctx.history, fetch: ctx.fetch });
  vm.createContext(ctx);
  vm.runInContext(LAB_SRC, ctx, { filename: 'lab.js' });
  const flush = async () => { for (let i = 0; i < 12; i++) await new Promise((r) => setImmediate(r)); };
  const lookup = (map) => ({ closest: (sel) => (sel in map ? map[sel] : null), tagName: 'DIV' });
  const fire = (type, e) => { for (const f of on.root[type] || []) f(e); };
  const keydown = (e) => { for (const h of [...on.doc.filter((x) => x.cap), ...on.doc.filter((x) => !x.cap)]) if (h.t === 'keydown') h.f({ preventDefault() { e.prevented = true; }, repeat: false, ...e }); };
  const pointerdown = (insideList) => { for (const h of on.doc) if (h.t === 'pointerdown') h.f({ target: lookup(insideList ? { '#labLib': {} } : {}) }); };
  const row = (key) => ({ dataset: { key } });
  return {
    S: win.HBLab.state, picks: () => [...win.HBLab.state.picks], lib, requests, made, flush, keydown, pointerdown, fire,
    clickRow(key, mods = {}) { fire('click', { target: lookup({ '[data-key]': row(key) }), shiftKey: !!mods.shift, metaKey: !!mods.meta, ctrlKey: !!mods.ctrl }); },
    clickMore(id, name, rowKey) { const dataset = { act: 'file', id, name, ...(rowKey ? { row: rowKey } : {}) };
      fire('click', { target: lookup({ '[data-act]': { dataset, getBoundingClientRect: () => ({ left: 5, right: 25, top: 5, bottom: 25 }) } }) }); },
    menu() { return made.filter((m) => m.className === 'lab-menu' && m.isConnected).pop(); },
    sheet() { return made.filter((m) => m.className === 'lab-ov' && m.isConnected).pop(); },
    pick(menuEl, what) { const btn = { dataset: { pick: what } }; for (const f of menuEl.listeners.click || []) f({ target: lookup({ '[data-pick]': btn }) }); },
    press(sheetEl, x) { for (const f of sheetEl.firstElementChild.listeners.click || []) f({ target: lookup({ '[data-x]': { dataset: { x } } }) }); },
    picked() { return [...lib.innerHTML.matchAll(/class="lb-item[^"]*\bpicked\b[^"]*" data-key="([^"]+)"/g)].map((m) => m[1]); },
  };
}
const G = { groups: ['Fades'], members: { draft_a: 'Fades', draft_c: 'Fades' } };   // shown: a c | b d e | nq930

test('page: shift-click picks the range in the shown order, marks it, and opens nothing', async () => {
  const p = page({ drafts: ['a', 'b', 'c', 'd', 'e'], groups: G });
  await p.flush();
  assert.deepEqual(p.picked(), []);
  p.clickRow('d:c');                                   // a plain click opens it (and is the range's start)
  await p.flush();
  assert.equal(p.S.cur, 'd:c');
  p.clickRow('d:d', { shift: true });
  assert.deepEqual(p.picks(), ['d:c', 'd:b', 'd:d']);
  assert.deepEqual(p.picked(), ['d:c', 'd:b', 'd:d']);
  assert.equal(p.S.cur, 'd:c', 'a shift-click opens nothing');
  assert.match(p.lib.innerHTML, /data-key="d:b"[^>]*aria-selected="true"/);
  assert.match(p.lib.innerHTML, /data-key="d:a"[^>]*aria-selected="false"/);
  assert.doesNotMatch(p.lib.innerHTML, /data-key="b:nq930"[^>]*aria-selected/, 'a locked row is not selectable');
});

test('page: cmd-click adds and removes, a locked row is never picked, a plain click and Escape clear the picks', async () => {
  const p = page({ drafts: ['a', 'b', 'c', 'd', 'e'], groups: G });
  await p.flush();
  p.clickRow('d:a', { meta: true });
  p.clickRow('d:e', { ctrl: true });
  p.clickRow('b:nq930', { meta: true });
  assert.deepEqual(p.picks(), ['d:a', 'd:e']);
  p.clickRow('d:a', { meta: true });
  assert.deepEqual(p.picked(), ['d:e']);
  p.keydown({ key: 'Escape', target: { tagName: 'BODY' } });
  assert.deepEqual(p.picks(), []);
  assert.deepEqual(p.picked(), []);
  p.clickRow('d:a', { meta: true }); p.clickRow('d:b', { meta: true });
  p.clickRow('d:e');                                   // plain
  await p.flush();
  assert.deepEqual(p.picks(), []);
  assert.equal(p.S.cur, 'd:e');
});

test('page: the row ⋯ deletes one strategy from the list, after a divider, last; a built-in row has no Delete', async () => {
  const p = page({ drafts: ['a', 'b'], groups: G });
  await p.flush();
  assert.match(p.lib.innerHTML, /data-act="file" data-id="draft_a" data-name="a" data-row="d:a"/);
  assert.doesNotMatch(p.lib.innerHTML, /data-act="file" data-id="nq930"[^>]*data-row/);
  p.clickMore('draft_b', 'b', 'd:b');
  const html = p.menu().innerHTML;
  assert.match(html, /<hr><button class="row" data-pick="delete"><span>Delete…<\/span><\/button>$/);
  p.pick(p.menu(), 'delete');
  const sheet = p.sheet();
  assert.match(sheet.innerHTML, /<h2>Delete b\?<\/h2>/);
  assert.match(sheet.innerHTML, /Keep it/);
  p.press(sheet, 'go');
  await p.flush();
  assert.ok(p.requests.includes('DELETE /api/tester/drafts/b'));
  assert.deepEqual(p.S.drafts.map((d) => d.name), ['a']);
  p.clickMore('nq930', 'NQ 930', '');                  // a built-in's ⋯ only moves it to a group
  assert.doesNotMatch(p.menu().innerHTML, /data-pick="delete"/);
});

test('page: the ⋯ of a picked row deletes every picked row, one request each, one confirm, one line afterwards', async () => {
  const p = page({ drafts: ['a', 'b', 'c', 'd', 'e'], groups: G, refuse: { d: 'It is on the Desk. Remove it from the Desk first.' } });
  await p.flush();
  p.clickRow('d:b', { meta: true }); p.clickRow('d:d', { meta: true }); p.clickRow('d:e', { meta: true });
  p.clickMore('draft_d', 'd', 'd:d');
  assert.match(p.menu().innerHTML, /<span>Delete 3 strategies…<\/span>/);
  p.clickMore('draft_a', 'a', 'd:a');                  // a row that is not picked deletes itself only
  assert.match(p.menu().innerHTML, /<span>Delete…<\/span>/);
  p.clickMore('draft_d', 'd', 'd:d');
  p.pick(p.menu(), 'delete');
  const sheet = p.sheet();
  assert.match(sheet.innerHTML, /<h2>Delete 3 strategies\?<\/h2>/);
  assert.match(sheet.innerHTML, /<li>b<\/li><li>d<\/li><li>e<\/li>/);
  assert.match(sheet.innerHTML, /Their files are removed from your strategies\. Past backtests of them stay in Recent runs\./);
  assert.match(sheet.innerHTML, /Keep them/);
  p.press(sheet, 'go');
  await p.flush();
  assert.deepEqual(p.requests.filter((r) => r.startsWith('DELETE')), ['DELETE /api/tester/drafts/b', 'DELETE /api/tester/drafts/d', 'DELETE /api/tester/drafts/e']);
  assert.deepEqual(p.S.drafts.map((d) => d.name), ['a', 'c', 'd']);
  assert.equal(p.S.log.at(-1).html, '<span class="err">Deleted 2. Not deleted: d (It is on the Desk. Remove it from the Desk first.)</span>');
  assert.deepEqual(p.picks(), ['d:d'], 'what was not deleted stays picked');
});

test('page: "Keep them" deletes nothing', async () => {
  const p = page({ drafts: ['a', 'b'], groups: G });
  await p.flush();
  p.clickRow('d:a', { meta: true }); p.clickRow('d:b', { meta: true });
  p.clickMore('draft_a', 'a', 'd:a');
  p.pick(p.menu(), 'delete');
  p.press(p.sheet(), 'cancel');
  await p.flush();
  assert.equal(p.requests.filter((r) => r.startsWith('DELETE')).length, 0);
  assert.deepEqual(p.picks(), ['d:a', 'd:b']);
});

test('page: Delete or Backspace deletes the picked while the list has the keyboard, not while typing', async () => {
  const p = page({ drafts: ['a', 'b', 'c', 'd', 'e'], groups: G });
  await p.flush();
  p.pointerdown(true);                                 // a touch on the list
  p.clickRow('d:b', { meta: true }); p.clickRow('d:d', { meta: true });
  const typing = { key: 'Delete', target: { tagName: 'TEXTAREA' } };
  p.keydown(typing);
  assert.equal(p.sheet(), undefined, 'typing in the editor');
  p.pointerdown(false);                                // a touch on the editor
  p.keydown({ key: 'Delete', target: { tagName: 'BODY' } });
  assert.equal(p.sheet(), undefined, 'the list has not the keyboard');
  p.pointerdown(true);
  p.keydown({ key: 'Backspace', target: { tagName: 'BODY' } });
  assert.match(p.sheet().innerHTML, /<h2>Delete 2 strategies\?<\/h2>/);
  p.keydown({ key: 'Escape', target: { tagName: 'BODY' } });
  assert.deepEqual(p.picks(), ['d:b', 'd:d'], 'Escape with a sheet open closes the sheet and keeps the picks');
});

test('page: folding a group lets go of the rows picked in it', async () => {
  const p = page({ drafts: ['a', 'b', 'c', 'd', 'e'], groups: G });
  await p.flush();
  p.clickRow('d:a', { meta: true }); p.clickRow('d:c', { meta: true }); p.clickRow('d:d', { meta: true });
  assert.deepEqual(p.picks(), ['d:a', 'd:c', 'd:d']);
  const header = { dataset: { act: 'fold', g: 'Fades' }, setAttribute() {}, closest: () => ({ classList: { toggle() {} } }) };
  // the click handler of the page, with the fold header as its target
  const ev = { target: { closest: (s) => (s === '[data-act]' ? header : null) } };
  p.fire('click', ev);
  assert.deepEqual(p.picks(), ['d:d']);
  assert.deepEqual(p.picked(), ['d:d']);
});
