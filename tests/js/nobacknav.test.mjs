import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const G = require('../../homebase/static/nobacknav.js');

const el = (tagName, o = {}) => ({ nodeType: 1, tagName, isContentEditable: false, ...o });
const key = (k, target) => { const e = { key: k, target, prevented: false, preventDefault() { this.prevented = true; } }; return e; };

test('Backspace / Delete outside a text field are cancelled (no WebKit history-back)', () => {
  const body = el('BODY');
  for (const k of ['Backspace', 'Delete']) {
    const e = key(k, body);
    assert.equal(G.guard(e, { activeElement: body }), true);
    assert.equal(e.prevented, true);
  }
  const btn = el('BUTTON');
  assert.equal(G.guard(key('Backspace', btn), { activeElement: btn }), true);
  const box = el('INPUT', { type: 'checkbox' });
  assert.equal(G.guard(key('Backspace', box), { activeElement: box }), true);
});

test('text fields keep Backspace / Delete', () => {
  for (const t of [el('INPUT', { type: 'text' }), el('INPUT', { type: 'number' }), el('INPUT', {}),
    el('TEXTAREA'), el('DIV', { isContentEditable: true })]) {
    const e = key('Backspace', t);
    assert.equal(G.guard(e, { activeElement: t }), false);
    assert.equal(e.prevented, false);
  }
  const ro = el('INPUT', { type: 'text', readOnly: true });
  assert.equal(G.guard(key('Backspace', ro), { activeElement: ro }), true, 'a read-only field edits nothing');
});

test('other keys are never touched', () => {
  const body = el('BODY');
  for (const k of ['a', 'Enter', 'Escape', ' ', 'ArrowLeft']) {
    const e = key(k, body);
    assert.equal(G.guard(e, { activeElement: body }), false);
    assert.equal(e.prevented, false);
  }
});
