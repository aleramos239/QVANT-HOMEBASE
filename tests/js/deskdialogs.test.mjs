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
      for (const k of kids) this.append(k);
    }
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
    focus() { doc.activeElement = this; }
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
  const dialog = (id, label, kids) => h('div', { class: 'overlay', id }, h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', tabindex: '-1', 'aria-label': label }, ...kids));
  const trigger = body.append(h('button', { id: 'gear', onclick: 'openSettings()' }));
  const other = body.append(h('button', { id: 'other' }));
  const settings = body.append(dialog('settingsOverlay', 'Settings', [
    h('button', { id: 'sx', 'aria-label': 'Close' }), h('input', { id: 'ctMaxOrder' }), h('button', { id: 'ctSave' })]));
  const confirm = body.append(h('div', { class: 'overlay', id: 'confirmOverlay' },
    h('div', { class: 'modal', role: 'dialog', 'aria-modal': 'true', tabindex: '-1' },
      h('h2', { id: 'cfTitle' }), h('p', { id: 'cfBody' }),
      h('button', { id: 'cfCancel', 'data-autofocus': '' }), h('button', { id: 'cfGo' }))));
  const card = body.append(h('div', { class: 'card' }));
  const plus = card.append(h('button', { id: 'plus', onclick: "toggleAsgMenu('nq930')" }));
  const menu = card.append(h('div', { class: 'amenu', id: 'amenu-nq930', role: 'menu', hidden: '' },
    h('button', { class: 'mi2', role: 'menuitem', id: 'i1' }), h('button', { class: 'mi2', role: 'menuitem', id: 'i2' }),
    h('button', { class: 'mi2', role: 'menuitem', id: 'i3' })));
  const closes = [];
  const ctx = vm.createContext({
    console, document: doc,
    $: (sel) => doc.getElementById(sel.replace(/^#/, '')),
    closeSettings: () => { closes.push('settings'); ctx.hideOverlay('settingsOverlay'); },
    closeConnect() {}, closeRes() {}, closeAccts() {}, closeAlgoMgr() {}, closeLive() {}, closeChecks() {}, closePine() {}, closeCal() {},
  });
  vm.runInContext(OVERLAYS + CONFIRM + BOOK + `
    globalThis.showOverlay = showOverlay; globalThis.hideOverlay = hideOverlay;
    globalThis.api = { showOverlay, hideOverlay, confirmDlg, cfDone, toggleAsgMenu, closeAsgMenus,
      get open() { return OVERLAYS.map((o) => o.el.id); }, get asg() { return ASG_OPEN; } };`, ctx);
  return { api: ctx.api, doc, h, body, trigger, other, settings, confirm, card, plus, menu, closes };
}

// ---- the markup ---------------------------------------------------------------------------------
test('every dialog is role="dialog" aria-modal and has a name', () => {
  const overlays = HTML.match(/<div class="overlay" id="\w+"[^>]*>\s*<div class="modal"[^>]*>/g) || [];
  assert.equal(overlays.length, 10);
  for (const o of overlays) {
    assert.match(o, /role="dialog" aria-modal="true" tabindex="-1"/, o);
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
