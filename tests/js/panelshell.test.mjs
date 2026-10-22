import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* panelshell.js is "Browser only" (its own header comment) and has no module.exports -- it wires real DOM
   listeners (pointer events, resize) that the pure half (panellayout.js, fully Node-tested already) never
   touches. This is a minimal DOM good enough to run it for real: real classList/style/addEventListener/
   dispatchEvent, so a synthetic pointerdown/pointermove/pointerup drives the SAME code path a real drag
   would, rather than reaching into panelshell.js's private state (mount() is the only way in -- nothing
   below is exposed except window.HBPanelShell, on purpose). requestAnimationFrame never auto-fires its
   callback (nothing here needs a spring to actually tick a frame to be worth testing -- only whether a
   *stale* one gets stopped before losing its handle matters), just returns a fresh truthy id each time so
   Spring's own "am I running" bookkeeping (and Spring.prototype.stop, spied on below) behaves exactly as it
   does in a browser. */
const SPRING_SRC = readFileSync(new URL('../../homebase/static/charts/spring.js', import.meta.url), 'utf8');
const LAYOUT_SRC = readFileSync(new URL('../../homebase/static/charts/panellayout.js', import.meta.url), 'utf8');
const SHELL_SRC = readFileSync(new URL('../../homebase/static/charts/panelshell.js', import.meta.url), 'utf8');

class El {
  constructor(tag, registry) {
    this.tagName = String(tag || 'div').toUpperCase();
    this.children = [];
    this.parentElement = null;
    this.className = '';
    this.style = {};
    this.dataset = {};
    this._attrs = {};
    this._listeners = {};
    this._rect = { x: 0, y: 0, left: 0, top: 0, right: 0, bottom: 0, width: 100, height: 40 };
    this._registry = registry;
    this._id = '';
    this.hidden = false;
    this.tabIndex = -1;
  }
  // a real DOM auto-indexes an element by id the moment it's set (long before, and independent of, whether
  // it's actually inserted anywhere) -- getElementById below relies on exactly that, same as buildChrome()
  // setting `root.id = "panel-${id}"` right after creating it.
  get id() { return this._id; }
  set id(v) { if (this._registry && this._id) delete this._registry[this._id]; this._id = v; if (this._registry && v) this._registry[v] = this; }
  get classList() {
    const self = this;
    const set = () => new Set(self.className.split(' ').filter(Boolean));
    return {
      add: (...cs) => { const s = set(); cs.forEach((c) => s.add(c)); self.className = [...s].join(' '); },
      remove: (...cs) => { const s = set(); cs.forEach((c) => s.delete(c)); self.className = [...s].join(' '); },
      toggle: (c, force) => { const s = set(); const on = force == null ? !s.has(c) : force; on ? s.add(c) : s.delete(c); self.className = [...s].join(' '); return on; },
      contains: (c) => set().has(c),
    };
  }
  append(...ns) { for (const n of ns) this.appendChild(n); }
  appendChild(n) { n.parentElement = this; this.children.push(n); return n; }
  insertBefore(n, before) {
    n.parentElement = this;
    const i = this.children.indexOf(before);
    if (i < 0) this.children.push(n); else this.children.splice(i, 0, n);
    return n;
  }
  replaceChildren(...ns) { for (const c of this.children) c.parentElement = null; this.children = []; this.append(...ns); }
  remove() { if (this.parentElement) { this.parentElement.children = this.parentElement.children.filter((c) => c !== this); this.parentElement = null; } }
  contains(node) { if (node === this) return true; return this.children.some((c) => c.contains(node)); }
  closest(sel) {   // only the ".class" shape panelshell.js actually uses (head.closest('.rail-split'))
    const cls = sel.replace(/^\./, '');
    let n = this;
    while (n) { if (n.classList.contains(cls)) return n; n = n.parentElement; }
    return null;
  }
  querySelector() { return null; }
  setAttribute(k, v) { this._attrs[k] = String(v); }
  removeAttribute(k) { delete this._attrs[k]; }
  getAttribute(k) { return k in this._attrs ? this._attrs[k] : null; }
  addEventListener(type, fn) { (this._listeners[type] ||= []).push(fn); }
  removeEventListener(type, fn) { if (this._listeners[type]) this._listeners[type] = this._listeners[type].filter((f) => f !== fn); }
  dispatchEvent(ev) { (this._listeners[ev.type] || []).slice().forEach((fn) => fn(ev)); return true; }
  setPointerCapture() {}
  releasePointerCapture() {}
  focus() {}
  blur() {}
  getBoundingClientRect() { return this._rect; }
  // a real element's offset box is its layout box: a transform (a panel springing into place) moves its
  // getBoundingClientRect() but not this. place() below sets _box once; a test shifts _rect alone to model a transform.
  get offsetLeft() { return (this._box || this._rect).left; }
  get offsetWidth() { return (this._box || this._rect).width; }
  get offsetHeight() { return (this._box || this._rect).height; }
  get isConnected() { let n = this; while (n.parentElement) n = n.parentElement; return n._isRoot === true; }
  set innerHTML(_) {}
}

function pointerEvent(type, x, y, extra) {
  return { type, clientX: x, clientY: y, pointerId: 1, buttons: 1, timeStamp: (extra && extra.t) || 0,
    preventDefault() {}, stopPropagation() {}, target: (extra && extra.target) || null, ...extra };
}

function makeEnv() {
  const registry = {};
  const mkRoot = (id) => { const e = new El('div', registry); e.id = id; e._isRoot = true; return e; };
  mkRoot('pdock'); mkRoot('floatLayer');
  const tbOrder = mkRoot('tbOrder'), tbDom = mkRoot('tbDom'), tbTape = mkRoot('tbTape');
  const document_ = {
    getElementById: (id) => registry[id] || null,
    createElement: (t) => new El(t, registry),
  };
  let rafId = 0;
  const stopSpies = [];
  const window_ = {
    innerWidth: 1200, innerHeight: 800,
    HBIcons: new Proxy({}, { get: () => '' }),   // icon(name) just needs window.HBIcons[name] to not throw
    _listeners: {},
    addEventListener(type, fn) { (window_._listeners[type] ||= []).push(fn); },
    removeEventListener(type, fn) { if (window_._listeners[type]) window_._listeners[type] = window_._listeners[type].filter((f) => f !== fn); },
    _fire(type) { (window_._listeners[type] || []).slice().forEach((fn) => fn({ type })); },
  };
  const ctx = vm.createContext({
    window: window_, document: document_, console,
    localStorage: { getItem: () => null, setItem: () => {}, removeItem: () => {} },
    requestAnimationFrame: () => (++rafId), cancelAnimationFrame: () => {},
    performance: { now: () => Date.now() },
    setTimeout: () => 0, clearTimeout: () => {},
  });
  vm.runInContext(SPRING_SRC, ctx);
  vm.runInContext(LAYOUT_SRC, ctx);
  // spy on every Spring instance's own stop(), regardless of which one -- simplest way to assert
  // "was some in-flight animation told to stop" without reaching into panelshell.js's private floatAnim/
  // flipAnim (deliberately not exposed; mount() + the public toggle/setOpen/setDocked are the real surface).
  const realStop = window_.HBSpring.Spring.prototype.stop;
  window_.HBSpring.Spring.prototype.stop = function (...args) { stopSpies.push(this); return realStop.apply(this, args); };
  vm.runInContext(SHELL_SRC, ctx);
  window_.HBPanelShell.mount({}, {});
  return { window: window_, document: document_, tbOrder, tbDom, tbTape, stopSpies };
}

function findByClass(root, cls) {
  if (root.classList && root.classList.contains(cls)) return root;
  for (const c of root.children) { const f = findByClass(c, cls); if (f) return f; }
  return null;
}

/* Drags a floating panel's header by (dx, dy) and releases -- the SAME pointerdown/pointermove/pointerup
   sequence a real drag fires, so it goes through wireHeaderDrag's real `end()` and, since the panel is
   already floating and lands somewhere still legal, settleFloat() -- which is what actually populates a
   live Spring for the panel (there is no other way to seed one without reaching into private state). */
function dragFloatingHeader(env, id, dx, dy) {
  const root = env.document.getElementById(`panel-${id}`);
  const head = root.children[0];   // buildChrome(): root.append(head, body) -- head is always child 0
  const start = { x: 300, y: 300 };
  head.dispatchEvent(pointerEvent('pointerdown', start.x, start.y, { target: head, t: 0 }));
  head.dispatchEvent(pointerEvent('pointermove', start.x + dx, start.y + dy, { t: 16 }));
  head.dispatchEvent(pointerEvent('pointerup', start.x + dx, start.y + dy, { t: 32 }));
}

test('sanity: mount() builds every panel\'s chrome and wires the toolbar toggles', () => {
  const env = makeEnv();
  assert.ok(env.document.getElementById('panel-order'));
  assert.ok(env.document.getElementById('panel-dom'));
  assert.ok(env.document.getElementById('panel-tape'));
  assert.equal(typeof env.tbOrder.onclick, 'function');
  assert.equal(typeof env.tbDom.onclick, 'function');
  assert.equal(typeof env.tbTape.onclick, 'function');
  env.tbTape.onclick();
  assert.equal(env.window.HBPanelShell.isOpen('tape'), true);
  assert.equal(env.tbTape.getAttribute('aria-pressed'), 'true');
});

test('three docked panels stack: side-by-side is only ever a pair', () => {
  const env = makeEnv();
  const { HBPanelShell: shell } = env.window;
  for (const id of ['order', 'dom', 'tape']) shell.setOpen(id, true);   // docked by default
  const dockEl = env.document.getElementById('pdock');
  assert.equal(dockEl.hidden, false);
  assert.ok(!dockEl.classList.contains('side'));
  assert.deepEqual(dockEl.children.filter((c) => c.classList.contains('hbpanel')).map((c) => c.dataset.panel), ['order', 'dom', 'tape']);
  assert.equal(dockEl.children.filter((c) => c.classList.contains('pdock-split')).length, 2);
});

test('onWindowResize: stops a floating panel\'s in-flight settle spring before writing the corrected rect', () => {
  const env = makeEnv();
  const { HBPanelShell: shell } = env.window;
  shell.setOpen('order', true);
  shell.setDocked('order', false);       // float it -- clampFloatRect seeds a legal on-screen rect
  dragFloatingHeader(env, 'order', 220, 40);   // a real drag-release: populates a live settleFloat() spring
  const before = env.stopSpies.length;
  // shrink the viewport so the panel's current (post-drag) rect is now off-screen and needs re-clamping
  env.window.innerWidth = 200; env.window.innerHeight = 200;
  env.window._fire('resize');
  assert.ok(env.stopSpies.length > before, 'the settle spring\'s own stop() should have been called by the resize correction');
});

test('onWindowResize: a panel that needs no correction is left alone (nothing spurious stopped)', () => {
  const env = makeEnv();
  const { HBPanelShell: shell } = env.window;
  shell.setOpen('order', true);
  shell.setDocked('order', false);
  // no drag: the panel is already exactly where layoutFloats() put it, well inside the (unchanged) viewport
  const before = env.stopSpies.length;
  env.window._fire('resize');   // same size -- clampFloatRect returns the identical rect
  assert.equal(env.stopSpies.length, before);
});

test('setOpen(id, false): stops a panel\'s own in-flight settle spring before closing it (no rAF loop left running on a removed element)', () => {
  const env = makeEnv();
  const { HBPanelShell: shell } = env.window;
  shell.setOpen('order', true);
  shell.setDocked('order', false);
  dragFloatingHeader(env, 'order', 150, 30);   // seeds a live settleFloat() spring
  const before = env.stopSpies.length;
  shell.setOpen('order', false);
  assert.ok(env.stopSpies.length > before, 'closing the panel should have stopped its own settle spring');
});

test('setDocked(id, true): stops a floating panel\'s in-flight settle spring before handing it to the dock', () => {
  const env = makeEnv();
  const { HBPanelShell: shell } = env.window;
  shell.setOpen('order', true);
  shell.setDocked('order', false);
  dragFloatingHeader(env, 'order', 150, 30);   // seeds a live settleFloat() spring
  const before = env.stopSpies.length;
  shell.setDocked('order', true);
  assert.ok(env.stopSpies.length > before, 're-docking should have stopped the still-running float spring, not raced it');
});

test('the dock width grip drops its own release snap-back class on a fresh grab (a re-grab must track 1:1, not inherit the CSS transition)', () => {
  const env = makeEnv();
  const { HBPanelShell: shell } = env.window;
  shell.setOpen('order', true);   // docked by default -- the width grip only exists while something's docked
  const dockEl = env.document.getElementById('pdock');
  const grip = findByClass(dockEl, 'pdock-widthgrip');
  assert.ok(grip, 'the dock width grip should exist once a panel is docked');
  // a normal drag-release: snapAxisCSS (panelshell.js) always adds the class at release, relying on
  // transitionend/its own timeout to remove it again later -- neither ever fires in this sandbox, so it
  // lingers exactly the way a real ~220ms window would right after a real release.
  grip.dispatchEvent(pointerEvent('pointerdown', 300, 100, { target: grip, t: 0 }));
  grip.dispatchEvent(pointerEvent('pointermove', 260, 100, { t: 16 }));
  grip.dispatchEvent(pointerEvent('pointerup', 260, 100, { t: 32 }));
  assert.ok(dockEl.classList.contains('pdock-snap-w'), 'setup: the release should have left the snap-back class on');
  // the re-grab itself -- before any pointermove -- must already have dropped it
  grip.dispatchEvent(pointerEvent('pointerdown', 260, 100, { target: grip, t: 40 }));
  assert.ok(!dockEl.classList.contains('pdock-snap-w'), 'a fresh grab should drop the lingering snap-back class immediately, not carry it into the new drag');
});

/* ---- dock drops with THREE panels: dockOrder lists every panel (a closed or floating one keeps its slot), so a
   drop that names only the panels showing must not drop the third from it (review 2026-10-22). ---- */
function place(env, rects) {
  for (const [id, r] of Object.entries(rects)) {
    const el = env.document.getElementById(id);
    el._rect = { x: r.left, y: r.top, left: r.left, top: r.top, right: r.left + r.width, bottom: r.top + r.height, width: r.width, height: r.height };
    el._box = el._rect;
  }
}
const dockedIds = (env) => env.document.getElementById('pdock').children.filter((c) => c.classList.contains('hbpanel')).map((c) => c.dataset.panel);
/* A drag from `from` to `to` that ends at rest (the last two samples sit still), so the momentum projection adds nothing. */
function dragHeader(env, id, from, to) {
  const head = env.document.getElementById(`panel-${id}`).children[0];
  head.dispatchEvent(pointerEvent('pointerdown', from.x, from.y, { target: head, t: 0 }));
  head.dispatchEvent(pointerEvent('pointermove', to.x, to.y, { t: 16 }));
  head.dispatchEvent(pointerEvent('pointermove', to.x, to.y, { t: 300 }));
  head.dispatchEvent(pointerEvent('pointerup', to.x, to.y, { t: 316 }));
}
const DOCK = { pdock: { left: 900, top: 0, width: 300, height: 800 } };
const TOP_HALF = { 'panel-order': { left: 900, top: 0, width: 300, height: 400 } };
const BOTTOM_HALF = (id) => ({ [`panel-${id}`]: { left: 900, top: 400, width: 300, height: 400 } });

test('a zone drop beside one docked panel keeps the closed Tape in the dock order: opening it shows it in the dock', () => {
  const env = makeEnv();
  const shell = env.window.HBPanelShell;
  shell.setOpen('order', true); shell.setOpen('dom', true);
  place(env, { ...DOCK, ...TOP_HALF, ...BOTTOM_HALF('dom') });
  dragHeader(env, 'dom', { x: 1000, y: 410 }, { x: 920, y: 200 });      // DOM's header onto Order's left band
  assert.deepEqual(dockedIds(env), ['dom', 'order']);
  shell.setOpen('tape', true);
  assert.deepEqual(dockedIds(env), ['dom', 'order', 'tape']);
});

test('a floating panel dropped on the only docked one keeps the closed third panel too (float-drop path)', () => {
  const env = makeEnv();
  const shell = env.window.HBPanelShell;
  shell.setOpen('order', true); shell.setOpen('tape', true);
  shell.setDocked('tape', false);                                        // Tape floats, DOM is closed
  place(env, { ...DOCK, ...TOP_HALF });
  dragHeader(env, 'tape', { x: 300, y: 300 }, { x: 1180, y: 200 });     // onto Order's right band
  assert.deepEqual(dockedIds(env), ['order', 'tape']);
  shell.setOpen('dom', true);
  assert.deepEqual(dockedIds(env), ['order', 'tape', 'dom']);
});

test('a small drag inside the dock does not jump over a closed panel that sits first in the dock order', () => {
  const env = makeEnv();
  const shell = env.window.HBPanelShell;
  shell.setOpen('order', true); shell.setOpen('dom', true);
  place(env, { ...DOCK, ...TOP_HALF, ...BOTTOM_HALF('dom') });
  dragHeader(env, 'dom', { x: 1000, y: 410 }, { x: 920, y: 200 });      // dockOrder is now [dom, order, tape]
  shell.setOpen('dom', false);                                           // DOM is closed but still first
  shell.setOpen('tape', true);
  place(env, { ...BOTTOM_HALF('tape') });
  assert.deepEqual(dockedIds(env), ['order', 'tape']);
  dragHeader(env, 'tape', { x: 1000, y: 410 }, { x: 1000, y: 450 });   // inside Tape's own panel: no zone, a plain reorder
  assert.deepEqual(dockedIds(env), ['order', 'tape']);
});

/* ---- the drop slot counts the OTHER docked panels only (review 2026-10-22): with two or more others there is no
   zone to arrange against, so the Y-index path is the normal one, and it must not count the dragged panel. ---- */
const THIRDS = { 'panel-order': { left: 900, top: 0, width: 300, height: 266 }, 'panel-dom': { left: 900, top: 266, width: 300, height: 266 },
  'panel-tape': { left: 900, top: 532, width: 300, height: 268 } };

test('three docked: dragging a panel down into a middle slot lands it there, not one slot too low', () => {
  const env = makeEnv();
  const shell = env.window.HBPanelShell;
  for (const id of ['order', 'dom', 'tape']) shell.setOpen(id, true);
  place(env, { ...DOCK, ...THIRDS });
  dragHeader(env, 'order', { x: 1000, y: 100 }, { x: 1000, y: 480 });   // lower half of DOM, above Tape's middle
  assert.deepEqual(dockedIds(env), ['dom', 'order', 'tape']);
});

test('three docked: dragging a panel up still lands in the slot under the pointer', () => {
  const env = makeEnv();
  const shell = env.window.HBPanelShell;
  for (const id of ['order', 'dom', 'tape']) shell.setOpen(id, true);
  place(env, { ...DOCK, ...THIRDS });
  dragHeader(env, 'tape', { x: 1000, y: 600 }, { x: 1000, y: 100 });
  assert.deepEqual(dockedIds(env), ['tape', 'order', 'dom']);
});

test('a floating panel dropped on a dock holding two others lands at the pointer, whatever its own floating rect says', () => {
  const env = makeEnv();
  const shell = env.window.HBPanelShell;
  for (const id of ['order', 'dom', 'tape']) shell.setOpen(id, true);
  shell.setDocked('order', false);                                       // Order floats; its dock slot is still first
  place(env, { ...DOCK, 'panel-order': { left: 280, top: 0, width: 300, height: 480 },   // its (stale) floating rect: midpoint 240
    'panel-dom': { left: 900, top: 0, width: 300, height: 400 }, 'panel-tape': { left: 900, top: 400, width: 300, height: 400 } });
  dragHeader(env, 'order', { x: 300, y: 12 }, { x: 1000, y: 500 });     // lower half of DOM's slot ... above Tape's middle (600)
  assert.deepEqual(dockedIds(env), ['dom', 'order', 'tape']);
});

/* ---- side by side (review 2026-10-22): a click on a header never reorders; the slot of a plain drag is read off
   X when the panels sit in a row, off Y when they sit in a column ---- */
const ROW_DOCK = { pdock: { left: 600, top: 0, width: 600, height: 800 } };
const ROW = { ...ROW_DOCK, 'panel-dom': { left: 600, top: 0, width: 300, height: 800 }, 'panel-order': { left: 900, top: 0, width: 300, height: 800 } };
/* Order + DOM docked side by side, DOM on the left, laid out as the browser would lay a row out. */
function sideDock(env) {
  const shell = env.window.HBPanelShell;
  shell.setOpen('order', true); shell.setOpen('dom', true);
  place(env, { ...DOCK, ...TOP_HALF, ...BOTTOM_HALF('dom') });
  dragHeader(env, 'dom', { x: 1000, y: 410 }, { x: 920, y: 200 });      // DOM's header onto Order's left band
  assert.deepEqual(dockedIds(env), ['dom', 'order']);
  assert.ok(env.document.getElementById('pdock').classList.contains('side'));
  place(env, ROW);
}
function press(env, id, at, to, ms = 16) {   // a press that ends at `to` (or, with no `to`, where it started), `ms` after it began
  const head = env.document.getElementById(`panel-${id}`).children[0];
  head.dispatchEvent(pointerEvent('pointerdown', at.x, at.y, { target: head, t: 0 }));
  if (to) head.dispatchEvent(pointerEvent('pointermove', to.x, to.y, { t: ms }));
  head.dispatchEvent(pointerEvent('pointerup', (to || at).x, (to || at).y, { t: ms + 16 }));
}

test('side by side: a click on a header (even with a 3px jitter) does not swap the panels', () => {
  const env = makeEnv();
  sideDock(env);
  press(env, 'order', { x: 1100, y: 12 });                                // the RIGHT header: used to jump to slot 0
  assert.deepEqual(dockedIds(env), ['dom', 'order']);
  press(env, 'order', { x: 1100, y: 12 }, { x: 1102, y: 14 });
  assert.deepEqual(dockedIds(env), ['dom', 'order']);
  press(env, 'dom', { x: 700, y: 12 });
  assert.deepEqual(dockedIds(env), ['dom', 'order']);
});

test('stacked: a click on a header does not reorder either', () => {
  const env = makeEnv();
  const shell = env.window.HBPanelShell;
  for (const id of ['order', 'dom', 'tape']) shell.setOpen(id, true);
  place(env, { ...DOCK, ...THIRDS });
  press(env, 'tape', { x: 1000, y: 540 });
  press(env, 'dom', { x: 1000, y: 274 });
  assert.deepEqual(dockedIds(env), ['order', 'dom', 'tape']);
});

test('side by side: a plain drag lands in the slot under the pointer\'s X (inside its own panel, or past the dock edge)', () => {
  const env = makeEnv();
  sideDock(env);
  press(env, 'order', { x: 1000, y: 12 }, { x: 1100, y: 60 });          // wanders inside its own panel, right of DOM's middle: stays second
  assert.deepEqual(dockedIds(env), ['dom', 'order']);
  press(env, 'dom', { x: 700, y: 12 }, { x: 1210, y: 12 });            // DOM thrown past the right edge: lands after Order
  assert.deepEqual(dockedIds(env), ['order', 'dom']);
  place(env, { ...ROW_DOCK, 'panel-order': { left: 600, top: 0, width: 300, height: 800 }, 'panel-dom': { left: 900, top: 0, width: 300, height: 800 } });
  press(env, 'dom', { x: 1000, y: 12 }, { x: 590, y: 12 });            // and back, just short of floating: before Order
  assert.deepEqual(dockedIds(env), ['dom', 'order']);
});

test('a side dock squeezed into a column (narrow viewport) still reads the slot off Y', () => {
  const env = makeEnv();
  sideDock(env);                                                         // dockOrientation is "side" ...
  place(env, { ...DOCK, 'panel-dom': { left: 900, top: 0, width: 300, height: 400 }, 'panel-order': { left: 900, top: 400, width: 300, height: 400 } });   // ... the media query lays a column
  press(env, 'order', { x: 1100, y: 410 }, { x: 920, y: 700 });        // left of DOM's middle in X, below it in Y
  assert.deepEqual(dockedIds(env), ['dom', 'order']);
});

test('a stale "side" orientation with three docked panels still reorders the stack by Y', () => {
  const env = makeEnv();
  const shell = env.window.HBPanelShell;
  sideDock(env);
  shell.setOpen('tape', true);                                           // a third panel: the dock is a stack again
  assert.ok(!env.document.getElementById('pdock').classList.contains('side'));
  place(env, { ...DOCK, 'panel-dom': { left: 900, top: 0, width: 300, height: 266 }, 'panel-order': { left: 900, top: 266, width: 300, height: 266 },
    'panel-tape': { left: 900, top: 532, width: 300, height: 268 } });
  dragHeader(env, 'dom', { x: 1000, y: 100 }, { x: 1000, y: 480 });
  assert.deepEqual(dockedIds(env), ['order', 'dom', 'tape']);
});

/* The three ways round the click guard (review 2026-10-22, skeptic): a window blur mid-press carries no pointer at
   all (NaN), and a twitch of a few px at speed is projected far by the release momentum. Neither is a drag. */
test('a window blur in the middle of a press leaves the dock as it was (it used to throw the panel to the end)', () => {
  const env = makeEnv();
  const shell = env.window.HBPanelShell;
  for (const id of ['order', 'dom', 'tape']) shell.setOpen(id, true);
  place(env, { ...DOCK, ...THIRDS });
  const head = env.document.getElementById('panel-order').children[0];
  head.dispatchEvent(pointerEvent('pointerdown', 1000, 100, { target: head, t: 0 }));
  env.window._fire('blur');
  head.dispatchEvent(pointerEvent('pointerup', 1000, 100, { t: 40 }));   // the press is over: this one is nobody's
  assert.deepEqual(dockedIds(env), ['order', 'dom', 'tape']);
  const side = makeEnv();
  sideDock(side);
  const left = side.document.getElementById('panel-dom').children[0];
  left.dispatchEvent(pointerEvent('pointerdown', 700, 12, { target: left, t: 0 }));
  side.window._fire('blur');
  assert.deepEqual(dockedIds(side), ['dom', 'order']);
});

test('a twitch under 4px at speed is still a click: the release momentum never reorders a stack', () => {
  const env = makeEnv();
  const shell = env.window.HBPanelShell;
  for (const id of ['order', 'dom', 'tape']) shell.setOpen(id, true);
  place(env, { ...DOCK, ...THIRDS });
  press(env, 'dom', { x: 1000, y: 274 }, { x: 1000, y: 272 }, 4);       // 2px up in 4ms = 500px/s: projected 250px, over Order's middle (133)
  assert.deepEqual(dockedIds(env), ['order', 'dom', 'tape']);
});

test('a twitch under 4px at speed does not drop the panel on the other one\'s band either (no stack<->side switch)', () => {
  const env = makeEnv();
  sideDock(env);
  press(env, 'order', { x: 910, y: 12 }, { x: 907, y: 12 }, 9);         // 3px left in 9ms = 333px/s: projected 166px, onto the middle of DOM (a "top" band)
  assert.deepEqual(dockedIds(env), ['dom', 'order']);
  assert.ok(env.document.getElementById('pdock').classList.contains('side'), 'still side by side');
  dragHeader(env, 'order', { x: 910, y: 12 }, { x: 750, y: 12 });       // a real drag onto the middle of DOM, at rest, does
  assert.ok(!env.document.getElementById('pdock').classList.contains('side'), 'a real drag onto DOM stacks the pair');
});

test('side by side: at rest, the slot is the pointer\'s X against the other panel\'s middle (not its Y, not a bare number)', () => {
  const env = makeEnv();
  sideDock(env);                                                         // DOM 600-900 (middle 750), Order 900-1200 (middle 1050); heads at y=12, panel middles at y=400
  dragHeader(env, 'dom', { x: 700, y: 12 }, { x: 800, y: 12 });         // right of the dock's left edge, left of Order's middle: stays first
  assert.deepEqual(dockedIds(env), ['dom', 'order']);
  dragHeader(env, 'dom', { x: 700, y: 12 }, { x: 590, y: 12 });         // just short of floating, off to the left: first
  assert.deepEqual(dockedIds(env), ['dom', 'order']);
  dragHeader(env, 'dom', { x: 700, y: 12 }, { x: 1210, y: 12 });        // past Order's middle (and the dock's edge): last
  assert.deepEqual(dockedIds(env), ['order', 'dom']);
  place(env, { ...ROW_DOCK, 'panel-order': { left: 600, top: 0, width: 300, height: 800 }, 'panel-dom': { left: 900, top: 0, width: 300, height: 800 } });
  dragHeader(env, 'dom', { x: 1000, y: 12 }, { x: 1190, y: 12 });       // right of Order's middle (750): stays last
  assert.deepEqual(dockedIds(env), ['order', 'dom']);
  dragHeader(env, 'dom', { x: 1000, y: 12 }, { x: 590, y: 12 });        // left of it: first
  assert.deepEqual(dockedIds(env), ['dom', 'order']);
});

test('side by side: the other panel still springing into place (it wears a transform) does not turn the row into a column', () => {
  const env = makeEnv();
  sideDock(env);                                                         // DOM 600-900, Order 900-1200: laid out in a row
  const dom = env.document.getElementById('panel-dom');
  dom._rect = { ...dom._rect, x: 720, left: 720, right: 1020 };          // DOM's drop spring is 120px from home: it overlaps Order for the moment
  dragHeader(env, 'order', { x: 1000, y: 12 }, { x: 1040, y: 12 });     // a plain 40px drag inside Order's own panel
  assert.deepEqual(dockedIds(env), ['dom', 'order']);
});

/* Where the click ends and the drag begins (CLICK_PX = 4, drawings.js MOVE_PX): exactly 4px is a drag, and a drag is
   judged at the point the release momentum carries it to -- in a column by Y, in a row by X. A flick this short only
   lands anywhere because of the projection, so each of these also fails if the projection is dropped. */
test('exactly 4px is a drag: a 4px flick up a stack lands where the momentum carries it (Y, not the raw release point)', () => {
  const env = makeEnv();
  const shell = env.window.HBPanelShell;
  for (const id of ['order', 'dom', 'tape']) shell.setOpen(id, true);
  place(env, { ...DOCK, ...THIRDS });
  press(env, 'tape', { x: 1000, y: 540 }, { x: 1000, y: 536 }, 4);     // 1000px/s: projected 499px up, over Order's middle (133); released at 536, it would stay last
  assert.deepEqual(dockedIds(env), ['tape', 'order', 'dom']);
});

test('exactly 4px is a drag: a 4px flick along a row lands where the momentum carries it (X, not the raw release point)', () => {
  const env = makeEnv();
  sideDock(env);                                                         // DOM 600-900 (middle 750), Order 900-1200
  press(env, 'order', { x: 904, y: 12 }, { x: 900, y: 12 }, 4);         // 1000px/s: projected to x=401, left of DOM's middle; released at 900, it would stay last
  assert.deepEqual(dockedIds(env), ['order', 'dom']);
});

test('exactly 4px is a drag: a 4px flick onto the other panel\'s band drops on it (stack<->side), where 3px does not', () => {
  const env = makeEnv();
  sideDock(env);
  press(env, 'order', { x: 910, y: 12 }, { x: 906, y: 12 }, 12);       // 333px/s: projected to x=740, the middle of DOM (a "top" band)
  assert.ok(!env.document.getElementById('pdock').classList.contains('side'), 'the pair is stacked');
  assert.deepEqual(dockedIds(env), ['order', 'dom']);
});

/* A neighbour that is still springing into place is judged where it is DRAWN: the drop highlight paints on that same
   element, so the band the user aims at is the band that counts. (The row-or-column question above is the one thing
   read off the layout box: that is structure, not where the pointer is.) */
test('a neighbour still springing into place is a drop target where it is drawn, as its highlight shows', () => {
  const env = makeEnv();
  sideDock(env);                                                         // DOM 600-900 laid out, Order 900-1200
  const dom = env.document.getElementById('panel-dom');
  dom._rect = { ...dom._rect, x: 900, left: 900, right: 1200 };          // DOM is drawn over Order's header for the moment
  dragHeader(env, 'order', { x: 1000, y: 12 }, { x: 1010, y: 12 });
  assert.ok(!env.document.getElementById('pdock').classList.contains('side'), 'a drag onto the panel drawn under the pointer stacks the pair');
  assert.deepEqual(dockedIds(env), ['order', 'dom']);
});
