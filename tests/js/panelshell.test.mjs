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
  get offsetWidth() { return this._rect.width; }
  get offsetHeight() { return this._rect.height; }
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
  const tbOrder = mkRoot('tbOrder'), tbDom = mkRoot('tbDom');
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
  return { window: window_, document: document_, tbOrder, tbDom, stopSpies };
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

test('sanity: mount() builds both panels\' chrome and wires the toolbar toggles', () => {
  const env = makeEnv();
  assert.ok(env.document.getElementById('panel-order'));
  assert.ok(env.document.getElementById('panel-dom'));
  assert.equal(typeof env.tbOrder.onclick, 'function');
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
