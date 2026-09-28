import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* The desk page's (homebase/static/index.html, :8850) dialogs and + Assign menu (2026-09-28,
   Apple-design audit W7), run for real in a vm sandbox over a small DOM: every dialog is
   role="dialog" aria-modal and labelled; opening moves focus in (the confirm's Cancel -- the safe
   default); closing gives it back to the trigger (or its re-rendered twin); Esc closes the topmost
   one exactly like Cancel, one layer per press; Tab stays inside; and a held Enter/Space never
   re-activates a control through auto-repeat. The menu gets Esc, focus in/out and arrow keys. */
const HTML = readFileSync(new URL('../../homebase/static/index.html', import.meta.url), 'utf8');
const between = (a, b) => HTML.slice(HTML.indexOf(a), HTML.indexOf(b));
const OVERLAYS = between('/* ---- overlays: one open/close path', '/* ---- confirmation popup');
const CONFIRM = between('/* ---- confirmation popup', '/* ---- master controls (top bar)');
const BOOK = between('let FREEZE = false;', 'function isDemoAcct(');

// ---- a small DOM: enough tree, selectors and focus for these handlers ---------------------------
function simpleMatch(el, sel) {
  const m = /^([a-z0-9]*)((?:\.[\w-]+)*)((?:\[[^\]]+\])*)((?::not\(\[[^\]]+\]\))*)$/i.exec(sel.trim());
  if (!m) throw new Error('selector not supported by the test DOM: ' + sel);
  const [, tag, classes, attrs, nots] = m;
  if (tag && el.tagName !== tag.toUpperCase()) return false;
  for (const c of classes.split('.').filter(Boolean)) if (!el.classList.contains(c)) return false;
  const attr = (a) => {
    const [k, v] = a.replace(/^\[|\]$/g, '').split('=');
    if (!(k in el.attrs)) return false;
    return v === undefined || el.attrs[k] === v.replace(/^['"]|['"]$/g, '');
  };
  for (const a of attrs.match(/\[[^\]]+\]/g) || []) if (!attr(a)) return false;
  for (const n of nots.match(/\[[^\]]+\]/g) || []) if (attr(n)) return false;
  return true;
}
function makeDom() {
  const doc = { activeElement: null };
  class El {
    constructor(tag, attrs = {}, kids = []) {
      this.tagName = tag.toUpperCase(); this.attrs = { ...attrs }; this.children = []; this.parent = null;
      const cls = new Set(String(attrs.class || '').split(/\s+/).filter(Boolean));
      this.classList = { add: (c) => cls.add(c), remove: (c) => cls.delete(c), contains: (c) => cls.has(c) };
      this.hidden = 'hidden' in attrs;
      this.style = {};
      for (const k of kids) this.append(k);
    }
    setAttribute(k, v) { this.attrs[k] = String(v); }
    removeAttribute(k) { delete this.attrs[k]; }
    hasAttribute(k) { return k in this.attrs; }
    getBoundingClientRect() { return this.rect || { left: 0, top: 0, width: 0, height: 0 }; }
    get offsetLeft() { return (this.pos || {}).left || 0; }
    get offsetTop() { return (this.pos || {}).top || 0; }
    append(k) { k.parent = this; this.children.push(k); return k; }
    addEventListener() {}   // the backdrop click-to-close: not exercised here
    remove() { if (this.parent) this.parent.children.splice(this.parent.children.indexOf(this), 1); this.parent = null; }
    get id() { return this.attrs.id || ''; }
    getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
    get previousElementSibling() { const s = this.parent.children; return s[s.indexOf(this) - 1] || null; }
    contains(x) { for (let n = x; n; n = n.parent) if (n === this) return true; return false; }
    *walk() { for (const c of this.children) { yield c; yield* c.walk(); } }
    matches(sel) { return sel.split(',').some((s) => simpleMatch(this, s)); }
    querySelector(sel) { for (const n of this.walk()) if (n.matches(sel)) return n; return null; }
    querySelectorAll(sel) { return [...this.walk()].filter((n) => n.matches(sel)); }
    closest(sel) { for (let n = this; n; n = n.parent) if (n.matches(sel)) return n; return null; }
    focus() {   // like a browser: nothing inside an inert subtree takes focus
      for (let n = this; n; n = n.parent) if ('inert' in n.attrs) return;
      doc.activeElement = this;
    }
    get offsetParent() {   // null when hidden, or inside a closed overlay / a hidden step
      for (let n = this; n; n = n.parent) {
        if (n.hidden || (n.attrs.style || '').includes('display:none')) return null;
        if (n.classList.contains('overlay') && !n.classList.contains('open')) return null;
      }
      return {};
    }
  }
  const h = (tag, attrs, ...kids) => new El(tag, attrs || {}, kids);
  const body = h('body', {});
  doc.body = body;
  doc.activeElement = body;
  doc.contains = (x) => body.contains(x);
  doc.querySelectorAll = (sel) => body.querySelectorAll(sel);
  doc.getElementById = (id) => body.querySelector(`[id=${id}]`);
  const listeners = [];
  doc.addEventListener = (type, fn, capture) => listeners.push({ type, fn, capture });
  doc.press = (target) => { for (const l of listeners) if (l.type === 'pointerdown') l.fn({ type: 'pointerdown', target }); };
  doc.click = (props) => {   // capture listeners first, like a browser; reports whether the click got through
    const e = { type: 'click', detail: 1, defaultPrevented: false, stopped: false,
      preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.stopped = true; }, ...props };
    for (const l of listeners) if (l.type === 'click' && l.capture) l.fn(e);
    return e;
  };
  doc.key = (props) => {
    const e = { type: 'keydown', repeat: false, shiftKey: false, target: doc.activeElement, defaultPrevented: false,
      preventDefault() { this.defaultPrevented = true; }, ...props };
    for (const l of listeners) if (l.type === 'keydown') l.fn(e);
    return e;
  };
  return { doc, h, body, El };
}

function load() {
  const { doc, h, body } = makeDom();
  const dialog = (id, label, kids) => h('div', { class: 'overlay', id }, h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', tabindex: '-1', inert: '', 'aria-label': label }, ...kids));
  const trigger = body.append(h('button', { id: 'gear', onclick: 'openSettings()' }));
  const other = body.append(h('button', { id: 'other' }));
  const settings = body.append(dialog('settingsOverlay', 'Settings', [
    h('button', { id: 'sx', 'aria-label': 'Close' }), h('input', { id: 'ctMaxOrder' }), h('button', { id: 'ctSave' })]));
  const confirm = body.append(h('div', { class: 'overlay', id: 'confirmOverlay' },
    h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', tabindex: '-1', inert: '' },
      h('h2', { id: 'cfTitle' }), h('p', { id: 'cfBody' }),
      h('button', { id: 'cfCancel', 'data-autofocus': '' }), h('button', { id: 'cfGo' }))));
  const card = body.append(h('div', { class: 'card' }));
  const plus = card.append(h('button', { id: 'plus', onclick: "toggleAsgMenu('nq930')" }));
  const menu = card.append(h('div', { class: 'amenu', id: 'amenu-nq930', role: 'menu', hidden: '' },
    h('button', { class: 'mi2', role: 'menuitem', id: 'i1' }), h('button', { class: 'mi2', role: 'menuitem', id: 'i2' }),
    h('button', { class: 'mi2', role: 'menuitem', id: 'i3' })));
  const closes = [];
  const clock = { now: 1_000_000 };
  const ctx = vm.createContext({
    console, document: doc, Date: { now: () => clock.now },
    $: (sel) => doc.getElementById(sel.replace(/^#/, '')),
    closeSettings: () => { closes.push('settings'); ctx.hideOverlay('settingsOverlay'); },
    closeConnect() {}, closeRes() {}, closeAccts() {}, closeAlgoMgr() {}, closeLive() {}, closeChecks() {}, closePine() {}, closeCal() {},
  });
  vm.runInContext(OVERLAYS + CONFIRM + BOOK + `
    globalThis.showOverlay = showOverlay; globalThis.hideOverlay = hideOverlay;
    globalThis.api = { showOverlay, hideOverlay, confirmDlg, cfDone, toggleAsgMenu, closeAsgMenus,
      get open() { return OVERLAYS.map((o) => o.el.id); }, get asg() { return ASG_OPEN; } };`, ctx);
  return { api: ctx.api, doc, h, body, trigger, other, settings, confirm, card, plus, menu, closes, clock };
}

// ---- the markup ---------------------------------------------------------------------------------
test('every dialog is role="dialog" aria-modal and has a name', () => {
  const overlays = HTML.match(/<div class="overlay" id="\w+"[^>]*>\s*<div class="modal"[^>]*>/g) || [];
  assert.equal(overlays.length, 10);
  for (const o of overlays) {
    assert.match(o, /role="dialog" aria-modal="true" tabindex="-1" inert/, o);   // inert until opened
    const named = /aria-label="[^"]+"/.exec(o) || /aria-labelledby="(\w+)"/.exec(o);
    assert.ok(named, o);
    if (named[1]) assert.match(HTML, new RegExp(`id="${named[1]}"`), `${named[1]} exists`);
  }
  assert.match(HTML, /id="cfCancel" data-autofocus onclick="cfDone\(false\)"/, 'the confirm opens on Cancel');
  assert.doesNotMatch(HTML, /title="Close">&times;/, 'every × has a name');
  assert.match(HTML, /class="amenu" id="amenu-\$\{name\}" role="menu" hidden/);
  assert.match(HTML, /class="mi2" role="menuitem"/);
});

test('every dialog opens and closes through the one path (no stray class flips)', () => {
  const flips = HTML.match(/classList\.(add|remove)\("open"\)/g) || [];
  assert.equal(flips.length, 2, 'only showOverlay/hideOverlay touch .open');
  for (const [open, close] of [['openChecks', 'closeChecks'], ['openConnect', 'closeConnect'], ['openSettings', 'closeSettings'],
    ['openRes', 'closeRes'], ['openAccts', 'closeAccts'], ['openAlgoMgr', 'closeAlgoMgr'], ['openLive', 'closeLive'],
    ['openPine', 'closePine'], ['openCal', 'closeCal']]) {
    const o = HTML.slice(HTML.indexOf(`function ${open}(`)), c = HTML.slice(HTML.indexOf(`function ${close}(`));
    assert.match(o.slice(0, o.indexOf('\n}') + 2), /showOverlay\("\w+Overlay"\)/, open);
    assert.match(c.slice(0, c.indexOf('}') + 1), /hideOverlay\("\w+Overlay"\)/, close);
  }
});

// ---- focus in, focus back -----------------------------------------------------------------------
test('opening moves focus into the dialog; closing gives it back to the trigger', () => {
  const s = load();
  s.trigger.focus();
  s.api.showOverlay('settingsOverlay');
  assert.ok(s.settings.classList.contains('open'));
  assert.equal(s.doc.activeElement, s.settings.children[0], 'the dialog itself takes focus');
  s.api.hideOverlay('settingsOverlay');
  assert.ok(!s.settings.classList.contains('open'));
  assert.equal(s.doc.activeElement, s.trigger);
});

test('the confirm opens on Cancel (the safe default) and gives focus back when answered', async () => {
  const s = load();
  s.other.focus();
  const answer = s.api.confirmDlg('Kill everything?', 'body', 'Kill', true);
  assert.equal(s.doc.activeElement.id, 'cfCancel');
  s.api.cfDone(true);
  assert.equal(await answer, true);
  assert.equal(s.doc.activeElement, s.other);
});

test('a trigger replaced by a re-render gets focus back through its twin (same onclick)', () => {
  const s = load();
  s.trigger.focus();
  s.api.showOverlay('settingsOverlay');
  s.trigger.remove();                                             // render() rebuilt it
  const twin = s.body.append(s.h('button', { id: 'gear2', onclick: 'openSettings()' }));
  s.api.hideOverlay('settingsOverlay');
  assert.equal(s.doc.activeElement, twin);
});

test('closing never steals focus the user already moved elsewhere', () => {
  const s = load();
  s.trigger.focus();
  s.api.showOverlay('settingsOverlay');
  s.other.focus();                                               // outside the dialog
  s.api.hideOverlay('settingsOverlay');
  assert.equal(s.doc.activeElement, s.other);
});

// ---- Esc ----------------------------------------------------------------------------------------
test('Esc on the confirm is exactly Cancel: it answers false and sends nothing', async () => {
  const s = load();
  const answer = s.api.confirmDlg('Book NQ930 on …885 LIVE × 3?', 'body', 'Book live', true);
  const e = s.doc.key({ key: 'Escape' });
  assert.equal(e.defaultPrevented, true);
  assert.equal(await answer, false);
  assert.ok(!s.confirm.classList.contains('open'));
});

test('Esc closes only the topmost dialog, one layer per press; a held Esc does not keep going', async () => {
  const s = load();
  s.trigger.focus();
  s.api.showOverlay('settingsOverlay');
  const answer = s.api.confirmDlg('Turn chart trading ON?', 'body', 'Turn on', false);
  assert.deepEqual([...s.api.open], ['settingsOverlay', 'confirmOverlay']);
  s.doc.key({ key: 'Escape' });
  assert.equal(await answer, false);
  assert.deepEqual([...s.api.open], ['settingsOverlay'], 'Settings is still open under it');
  s.doc.key({ key: 'Escape', repeat: true });
  assert.deepEqual([...s.api.open], ['settingsOverlay'], "the auto-repeat of the same Esc closes nothing more");
  s.doc.key({ key: 'Escape' });
  assert.deepEqual([...s.api.open], []);
  assert.deepEqual(s.closes, ['settings'], "Esc went through Settings' own close (it also stops its poll)");
  assert.equal(s.doc.activeElement, s.trigger);
});

test('Esc with nothing open does nothing', () => {
  const s = load();
  const e = s.doc.key({ key: 'Escape' });
  assert.equal(e.defaultPrevented, false);
});

// ---- Tab ----------------------------------------------------------------------------------------
test('Tab stays inside the open dialog, both ways', () => {
  const s = load();
  s.api.showOverlay('settingsOverlay');
  const [sx, , save] = s.settings.children[0].children;
  let e = s.doc.key({ key: 'Tab' });                         // from the dialog itself: to the first control
  assert.equal(e.defaultPrevented, true);
  assert.equal(s.doc.activeElement, sx);
  s.doc.key({ key: 'Tab', shiftKey: true });                  // from the first, backwards: wraps to the last
  assert.equal(s.doc.activeElement, save);
  s.doc.key({ key: 'Tab' });                                  // from the last, forwards: wraps to the first
  assert.equal(s.doc.activeElement, sx);
  e = s.doc.key({ key: 'Tab' });                              // in the middle: the browser's own move
  assert.equal(e.defaultPrevented, false);
});

// ---- a held key ---------------------------------------------------------------------------------
test('a held Enter/Space never re-activates a button (auto-repeat is swallowed), typing is untouched', () => {
  const s = load();
  const answer = s.api.confirmDlg('Arm the desk?', 'body', 'Arm', false);   // focus: Cancel
  const rep = s.doc.key({ key: 'Enter', repeat: true });
  assert.equal(rep.defaultPrevented, true, 'the held Enter that opened the dialog cannot press a button in it');
  assert.equal(s.doc.key({ key: ' ', repeat: true }).defaultPrevented, true);
  assert.equal(s.doc.key({ key: 'Enter', repeat: false }).defaultPrevented, false, 'a fresh press still works');
  s.api.cfDone(false);
  const input = s.settings.querySelector('input');
  assert.equal(s.doc.key({ key: ' ', repeat: true, target: input }).defaultPrevented, false, 'held Space in a text field still types');
  return answer;
});

// ---- the + Assign menu --------------------------------------------------------------------------
test('the + Assign menu: focus goes in, the arrows walk it, Esc closes it and gives focus back', () => {
  const s = load();
  s.api.toggleAsgMenu('nq930');
  assert.equal(s.menu.hidden, false);
  assert.equal(s.doc.activeElement.id, 'i1');
  s.doc.key({ key: 'ArrowDown' });
  assert.equal(s.doc.activeElement.id, 'i2');
  s.doc.key({ key: 'ArrowUp' });
  s.doc.key({ key: 'ArrowUp' });
  assert.equal(s.doc.activeElement.id, 'i3', 'wraps around');
  s.doc.key({ key: 'Home' });
  assert.equal(s.doc.activeElement.id, 'i1');
  const e = s.doc.key({ key: 'Escape' });
  assert.equal(e.defaultPrevented, true);
  assert.equal(s.menu.hidden, true);
  assert.equal(s.api.asg, null);
  assert.equal(s.doc.activeElement, s.plus, 'back on + Assign');
});

// ---- glass pass: live at once on open, inert at once on close -----------------------------------
const STYLE = HTML.slice(HTML.indexOf('<style>'), HTML.indexOf('</style>'));
const ruleOf = (sel) => { const i = STYLE.indexOf('  ' + sel + '{'); assert.ok(i >= 0, sel); return STYLE.slice(i, STYLE.indexOf('}', i) + 1); };

test('a dialog is live the moment it opens: not inert, and its safe default takes focus at once', () => {
  const s = load();
  const box = s.confirm.children[0];
  assert.ok(box.hasAttribute('inert'), 'closed: inert');
  s.api.confirmDlg('Kill everything?', 'body', 'Kill', true);
  assert.ok(!box.hasAttribute('inert'), 'open: live before any animation has run');
  assert.equal(s.doc.activeElement.id, 'cfCancel');
  assert.ok(s.confirm.classList.contains('open'));
});

test('a closing dialog is inert at once: nothing in it takes focus, no key reaches it, it cannot answer twice', async () => {
  const s = load();
  const box = s.confirm.children[0];
  let answers = 0;
  const p = s.api.confirmDlg('Arm the desk?', 'body', 'Arm', false).then((v) => { answers += 1; return v; });
  s.api.cfDone(true);                                        // Confirm pressed: the exit fade starts
  assert.ok(box.hasAttribute('inert'), 'inert the moment it starts closing, not when the fade ends');
  assert.ok(!s.confirm.classList.contains('open'));
  s.confirm.querySelector('[id=cfGo]').focus();              // a held key / stray focus aimed at it
  assert.notEqual(s.doc.activeElement.id, 'cfGo', 'nothing inside a closing dialog takes focus');
  assert.deepEqual([...s.api.open], [], 'no key handler treats it as open any more');
  assert.equal(s.doc.key({ key: 'Enter', repeat: true }).defaultPrevented, true,
    'a held Enter still presses nothing while it fades (the page-wide auto-repeat guard)');
  s.api.cfDone(true);                                        // a double click on Confirm during the fade
  s.api.cfDone(false);
  assert.equal(await p, true);
  await Promise.resolve();
  assert.equal(answers, 1, 'answered exactly once');
});

test('reopening a dialog makes it live again, and it grows from what opened it', () => {
  const s = load();
  const box = s.settings.children[0];
  box.pos = { left: 300, top: 200 };
  s.trigger.rect = { left: 900, top: 20, width: 40, height: 30 };
  s.trigger.focus();
  s.api.showOverlay('settingsOverlay');
  assert.equal(box.style.transformOrigin, '620px -165px', "the gear's centre, in the box's own coordinates");
  s.api.hideOverlay('settingsOverlay');
  assert.ok(box.hasAttribute('inert'));
  s.api.showOverlay('settingsOverlay');
  assert.ok(!box.hasAttribute('inert'));
});

test('with nothing focused (a mouse click), the dialog grows from what the pointer last pressed', () => {
  const s = load();
  const box = s.settings.children[0];
  box.pos = { left: 0, top: 0 };
  s.other.rect = { left: 100, top: 40, width: 20, height: 20 };
  s.doc.press(s.other);                                     // pointerdown on a button (WebKit leaves focus on body)
  s.api.showOverlay('settingsOverlay');
  assert.equal(box.style.transformOrigin, '110px 50px');
});

test('CSS: a closing dialog stops taking the pointer at once (its fade never swallows a click); it opens with no delay', () => {
  const closed = ruleOf('.overlay'), open = ruleOf('.overlay.open');
  assert.match(closed, /visibility:hidden; opacity:0;/);
  assert.match(closed, /pointer-events:none;/, 'the next deliberate click -- Kill included -- goes straight through');
  assert.match(closed, /transition:opacity 130ms var\(--ease-spring-in\), visibility 0s linear 130ms;/, 'it still fades');
  assert.match(open, /pointer-events:auto;/);
  assert.match(open, /visibility:visible; opacity:1;/);
  assert.match(open, /visibility 0s;/, 'opening is visible and clickable at once, never delayed');
  assert.match(ruleOf('.overlay .modal'), /transform:scale\(\.96\); filter:blur\(6px\)/);
  assert.match(ruleOf('.overlay.open .modal'), /transform:none; filter:none;/, 'at rest: no transform, no filter -- numbers stay crisp');
});

test('CSS: the glass tokens match the charts page (.50 / .62, 20 / 30px, 190%; dark .46 / .58, 170%)', () => {
  const light = STYLE.slice(STYLE.indexOf(':root, :root[data-theme="light"]{'), STYLE.indexOf(':root[data-theme="dark"]{'));
  const dark = STYLE.slice(STYLE.indexOf(':root[data-theme="dark"]{'), STYLE.indexOf('html, body'));
  assert.match(light, /--glass-bg: color-mix\(in srgb, var\(--card\) 50%, transparent\);/);
  assert.match(light, /--glass-bg-heavy: color-mix\(in srgb, var\(--card\) 62%, transparent\);/);
  assert.match(light, /--glass-blur: 20px; --glass-blur-heavy: 30px; --glass-saturate: 190%;/);
  assert.match(dark, /--glass-bg: color-mix\(in srgb, var\(--card\) 46%, transparent\);/);
  assert.match(dark, /--glass-bg-heavy: color-mix\(in srgb, var\(--card\) 58%, transparent\);/);
  assert.match(dark, /--glass-saturate: 170%;/);
  assert.match(light, /--ease-spring-out: cubic-bezier\(0\.23, 1, 0\.32, 1\);/, 'critically damped shape, no overshoot');
});

test('CSS: the top bar is sticky glass the page scrolls under; money stays solid on it', () => {
  assert.match(ruleOf('.app-main'), /overflow-y:auto;/);
  const bar = ruleOf('.inset-topbar');
  assert.match(bar, /position:sticky; top:0;/);
  assert.match(bar, /backdrop-filter:blur\(var\(--glass-blur\)\) saturate\(var\(--glass-saturate\)\);/);
  assert.match(bar, /-webkit-backdrop-filter:/, 'WKWebView needs the prefix');
  assert.match(bar, /border-top:1px solid var\(--glass-edge\);/);
  assert.match(ruleOf('.btn-kill'), /background:var\(--card\);/, 'Kill is a solid chip on the glass');
  assert.match(ruleOf('.pill.armed'), /background:color-mix\(in oklch, var\(--destructive\) 75%, black\);/, 'ARMED stays solid red');
  assert.doesNotMatch(STYLE, /\.master[^{]*\{[^}]*(transition|animation)/, 'the master controls are never animated');
});

test('CSS: nothing on the page ever covers the master controls -- a lifted card stays under the top bar, dialogs over it', () => {
  const z = (rule) => Number(/z-index:(\d+)/.exec(rule)[1]);
  const bar = z(ruleOf('.inset-topbar')), lifted = z(ruleOf('.card:has(.amenu:not([hidden]))'));
  const overlay = z(ruleOf('.overlay')), menu = z(ruleOf('.amenu'));
  assert.ok(lifted < bar, `a card with an open menu (${lifted}) stays under the top bar (${bar})`);
  assert.ok(menu < bar, 'the menu too');
  assert.ok(bar < overlay, `every dialog's scrim (${overlay}) covers the page, top bar included`);
  assert.ok(z(ruleOf('.overlay.open')) > overlay, 'a dialog opening while another fades out sits above it');
  assert.match(HTML, /id="confirmOverlay" style="z-index:70"/);
});

test('CSS: reduced transparency and more contrast go solid; reduced motion is a short cross-fade', () => {
  const block = (q) => STYLE.slice(STYLE.indexOf(q), STYLE.indexOf('\n  }\n', STYLE.indexOf(q)));
  const rt = block('@media (prefers-reduced-transparency: reduce){');
  assert.match(rt, /backdrop-filter:none; -webkit-backdrop-filter:none;/);
  assert.match(rt, /\.card, \.modal, \.amenu, #toast\{ background:var\(--card\); \}/);
  const hc = block('@media (prefers-contrast: more){');
  assert.match(hc, /backdrop-filter:none; -webkit-backdrop-filter:none;/);
  assert.match(hc, /border-color:var\(--foreground\)/, 'a defined border');
  const rm = block('@media (prefers-reduced-motion: reduce){');
  assert.match(rm, /\.overlay \.modal, \.overlay\.open \.modal\{ transform:none !important; filter:none !important; \}/);
  assert.match(rm, /\.overlay\{ transition:opacity 120ms ease, visibility 0s linear 120ms !important; \}/);
});

test('the toast materializes by class (glass, above any dialog) and is announced politely', () => {
  assert.match(HTML, /<div id="toast" role="status" aria-live="polite"><\/div>/);
  const fn = HTML.slice(HTML.indexOf('function toast('), HTML.indexOf('async function post('));
  assert.match(fn, /classList\.add\("show"\)/);
  assert.match(fn, /classList\.remove\("show"\)/);
  assert.match(ruleOf('#toast'), /z-index:80;/);
});

test('after a dialog closes, a double-click\'s second half is dropped for 400 ms; a single click always goes through', () => {
  const s = load();
  s.api.confirmDlg('Book NQ930 on …885 LIVE × 3?', 'body', 'Book live', false);
  s.api.cfDone(true);                                    // click 1 of a double-click: answered
  let e = s.doc.click({ detail: 2 });                   // click 2 lands wherever the button was
  assert.ok(e.stopped && e.defaultPrevented, 'it never reaches the page beneath the dialog');
  e = s.doc.click({ detail: 1 });
  assert.ok(!e.stopped && !e.defaultPrevented, 'a deliberate click is never delayed or dropped');
  s.clock.now += 400;
  e = s.doc.click({ detail: 2 });
  assert.ok(!e.stopped, 'after the window, clicks are the page\'s own business again');
});

test('a double-click never acts on the dialog its first half opened: repeat clicks are dropped for 400 ms after an open', () => {
  const s = load();
  const answer = s.api.confirmDlg('Turn ON ES_OPEN?', 'body', 'Turn on', false);   // click 1 opened it
  let e = s.doc.click({ detail: 2 });                   // click 2 lands on "Turn on", right where the switch was
  assert.ok(e.stopped && e.defaultPrevented, 'dropped before it reaches the button');
  s.clock.now += 399;
  assert.ok(s.doc.click({ detail: 3 }).stopped, 'a triple-click too');
  assert.ok(!s.doc.click({ detail: 1 }).stopped, 'a deliberate click is never dropped');
  s.clock.now += 1;
  assert.ok(!s.doc.click({ detail: 2 }).stopped, 'after 400 ms the dialog is the user\'s again');
  assert.match(HTML, /document\.addEventListener\("mousedown", \(e\) => \{ if \(secondHalf\(e\)\) e\.preventDefault\(\); \}, true\);/,
    "the second half's press never pulls focus off the dialog's Cancel");
  s.api.cfDone(false);
  return answer;
});

test("the scrim's own Cancel handler no longer special-cases double-clicks (the page-wide guard drops them first)", () => {
  const scrim = HTML.slice(HTML.indexOf('$("#confirmOverlay").addEventListener("click"'), HTML.indexOf('/* ---- master controls (top bar)'));
  assert.match(scrim, /if \(e\.target === e\.currentTarget\) cfDone\(false\);/);
  assert.doesNotMatch(scrim, /detail/);
  const show = HTML.slice(HTML.indexOf('function showOverlay('), HTML.indexOf('function hideOverlay('));
  assert.match(show, /OVERLAY_OPENED_AT = Date\.now\(\);/);
});

test('a touch hold that opens the confirm cannot answer it on lift: a click whose press began before the dialog opened is dropped', () => {
  const s = load();
  s.doc.press(s.body);                                   // the finger goes down (on Kill) ...
  s.clock.now += 1000;
  s.api.confirmDlg('Kill everything?', 'body', 'Kill', true);   // ... the hold completes: the confirm opens
  s.clock.now += 600;
  const scrim = s.confirm, go = s.confirm.querySelector('[id=cfGo]');
  let e = s.doc.click({ detail: 1, target: scrim });     // the lift's click lands on the scrim
  assert.ok(e.stopped, 'not a Cancel');
  e = s.doc.click({ detail: 1, target: go });            // or on the dialog's own button
  assert.ok(e.stopped, 'not a Kill either');
  assert.ok(!s.doc.click({ detail: 0, target: go }).stopped, 'the keyboard (no press) is never dropped');
  s.doc.press(go);                                      // a real tap, after the dialog opened
  assert.ok(!s.doc.click({ detail: 1, target: go }).stopped, 'a deliberate tap answers it');
  s.api.cfDone(false);
});
