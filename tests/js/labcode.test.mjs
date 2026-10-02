import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const L = require('../../homebase/static/charts/labcode.js');
const strip = (h) => h.replace(/<[^>]+>/g, '').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');

test('highlight returns every character of the source, in order (the caret must never drift)', () => {
  const src = 'from x import Y  # hi <b>\nclass A(Strategy):\n    """doc <x>"""\n    n = 1.5e3 & "a\\"b" \'c\'\n    @classmethod\n    def f(self): return None\n';
  assert.equal(strip(L.highlight(src)), src);
  assert.equal(strip(L.highlight('')), '');
  assert.equal(strip(L.highlight('x = "unterminated\ny = 2')), 'x = "unterminated\ny = 2');
});

test('highlight classes: comments, strings, numbers, keywords, defined and called names, decorators, builtins', () => {
  const h = L.highlight('@classmethod\ndef inputs(cls):\n    # c\n    return Input("k", 5, ctx.flatten())');
  assert.match(h, /<span class="d">@classmethod<\/span>/);
  assert.match(h, /<span class="k">def<\/span> <span class="f">inputs<\/span>/);
  assert.match(h, /<span class="c"># c<\/span>/);
  assert.match(h, /<span class="s">&quot;k&quot;|<span class="s">"k"<\/span>/);
  assert.match(h, /<span class="n">5<\/span>/);
  assert.match(h, /<span class="b">ctx<\/span>\.<span class="f">flatten<\/span>/);
  assert.match(L.highlight('class MyS(Strategy):'), /<span class="k">class<\/span> <span class="f">MyS<\/span>\(<span class="b">Strategy<\/span>\)/);
  // a # or a keyword inside a string is just string
  assert.equal(L.highlight('"a # b if"'), '<span class="s">"a # b if"</span>');
  assert.match(L.highlight('"""x\n if y\n"""'), /^<span class="s">"""x\n if y\n"""<\/span>$/);
});

test('Tab inserts to the next 4-column stop; with a multi-line selection it indents every line; Shift+Tab outdents', () => {
  assert.deepEqual(L.tab('ab', 2, 2, false), { value: 'ab  ', start: 4, end: 4 });
  assert.deepEqual(L.tab('', 0, 0, false), { value: '    ', start: 4, end: 4 });
  const r = L.tab('a\nb\nc', 0, 3, false);
  assert.equal(r.value, '    a\n    b\nc');
  const o = L.tab('    a\n  b\nc', 0, 11, true);
  assert.equal(o.value, 'a\nb\nc');
  assert.equal(L.tab('x', 1, 1, true).value, 'x');
});

test('Enter keeps the indent and adds one after a colon', () => {
  const a = L.enter('    x = 1', 9, 9);
  assert.equal(a.value, '    x = 1\n    ');
  assert.equal(a.start, 14);
  assert.equal(L.enter('def f():', 8, 8).value, 'def f():\n    ');
  assert.equal(L.enter('    if x:  # why', 16, 16).value, '    if x:  # why\n        ');
  assert.equal(L.enter('abc', 1, 1).value, 'a\nbc');
});

test('Cmd+/ comments every live line at the shallowest indent, and uncomments when all are commented', () => {
  const c = L.comment('    a\n\n      b', 0, 12);
  assert.equal(c.value, '    # a\n\n    #   b');
  assert.equal(L.comment(c.value, 0, c.value.length).value, '    a\n\n      b');
  assert.equal(L.comment('x', 0, 0).value, '# x');
});

test('a pasted script gets a name from its name = "..." , else its class, else my_strategy; never a taken or reserved one', () => {
  assert.equal(L.suggestName('class Foo(Strategy):\n    name = "ORB pullback"\n'), 'orb_pullback');
  assert.equal(L.suggestName('class OrbPullback(Strategy):\n    pass'), 'orb_pullback');
  assert.equal(L.suggestName('x = 1'), 'my_strategy');
  assert.equal(L.suggestName('class Strategy2(Strategy):\n    name = "123"'), 'my_123');
  assert.equal(L.suggestName('class A(Strategy):\n name = "orb"', ['orb']), 'orb_2');
  assert.equal(L.suggestName('class Base(Strategy):\n pass'), 'my_strategy');
});

test('name errors say what is wrong in plain words', () => {
  assert.equal(L.nameError('nq_orb_15'), null);
  assert.match(L.nameError('Bad-Name'), /2–40 letters/);
  assert.match(L.nameError('a'), /2–40/);
  assert.match(L.nameError('draft_x'), /reserved/);
  assert.match(L.nameError('main'), /reserved/);
});

test('the validation line: valid with what was found, or the line and the reason', () => {
  const meta = { inputs: [{}, {}, {}], root: 'NQ', session_window: ['09:25', '16:00'], bar_minutes: 5 };
  assert.deepEqual(L.statusOf({ ok: true, meta }), { tone: 'ok', text: 'Valid · 3 inputs · NQ · session 09:25–16:00 ET · 5-minute bars' });
  assert.deepEqual(L.statusOf({ ok: false, error: 'SyntaxError: invalid syntax (line 4)', line: 4 }),
    { tone: 'err', text: 'Line 4: SyntaxError: invalid syntax' });
  assert.equal(L.statusOf({ ok: false, error: 'a draft defines exactly one class', line: null }).text, 'a draft defines exactly one class');
  assert.equal(L.statusOf(null).text, '');
});

test('ago reads like a person says it', () => {
  assert.equal(L.ago(1000, 2000), 'just now');
  assert.equal(L.ago(0, 30000), '30 s ago');
  assert.equal(L.ago(0, 5 * 60000), '5 min ago');
  assert.equal(L.ago(0, 3 * 3600000), '3 h ago');
});
