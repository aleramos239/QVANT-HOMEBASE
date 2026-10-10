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

test('the library in sections: each group in its saved order with its rows, then the rest under no name', () => {
  const rows = [{ key: 'n:1' }, { id: 'draft_a' }, { id: 'draft_b' }, { id: 'nq930' }, { id: 'gc_nfp' }];
  const groups = { groups: ['Gold', 'Empty', 'Nasdaq'],
    members: { draft_b: 'Nasdaq', gc_nfp: 'Gold', nq930: 'Nasdaq', draft_deleted: 'Gold', draft_a: 'A group that is gone' } };
  assert.deepEqual(L.sections(rows, groups), [
    { name: 'Gold', rows: [{ id: 'gc_nfp' }] },                       // a filed strategy that is no longer listed is not a row
    { name: 'Empty', rows: [] },                                      // an empty group is still a section
    { name: 'Nasdaq', rows: [{ id: 'draft_b' }, { id: 'nq930' }] },   // rows keep the order they came in
    { name: '', rows: [{ key: 'n:1' }, { id: 'draft_a' }] },          // an unsaved script has no id: it cannot be filed
  ]);
  assert.deepEqual(L.sections(rows, { groups: [], members: {} }), [{ name: '', rows }]);
  assert.deepEqual(L.sections([], { groups: ['Gold'], members: {} }), [{ name: 'Gold', rows: [] }, { name: '', rows: [] }]);
});

/* ---- the blueprint toolkit in the Lab: a tool's inputs as a form, and the form as the tool's arguments ---- */
const SCHEMA = { type: 'object', required: ['name', 'confirm'], properties: {
  name: { type: 'string', description: "The idea's name" }, confirm: { type: 'boolean' }, wait_s: { type: 'integer' }, fee_budget: { type: 'number' },
  on: { type: 'string', enum: ['build', 'test'] }, names: { type: 'array', items: { type: 'string' } },
  card: { type: 'object', properties: { why: { type: 'string' }, home: { type: 'object', properties: { market: { type: 'string' }, bar: { type: 'string' } } }, neighbors: { type: 'array', items: { type: 'string' } } } },
  fills: { type: 'array', items: { type: 'object' } }, exit_time: { type: ['string', 'number'] } } };

test('a blueprint tool has a plain title and its phase', () => {
  assert.equal(L.bpTitle('blueprint_card'), 'Idea card');
  assert.equal(L.bpTitle('blueprint_portfolio'), 'Simulator: portfolio');
  assert.equal(L.bpTitle('blueprint_new_thing'), 'new thing');          // a tool the page has no name for yet is still listed
  assert.equal(L.bpPhase('Blueprint phase 2, the build (2021-09-22 to 2025-06-30)'), 'Phase 2');
  assert.equal(L.bpPhase('Blueprint, before the card'), 'Before the card');
  assert.equal(L.bpPhase('Blueprint, a view of what is saved: the heat map'), 'A view of what is saved');
  assert.equal(L.bpPhase(''), '');
});

test("a tool's inputs become form fields in the schema's order, each of the kind its type asks for", () => {
  const f = L.bpFields(SCHEMA);
  assert.deepEqual(f.map((x) => [x.key, x.kind, x.required]), [['name', 'text', true], ['confirm', 'bool', true], ['wait_s', 'int', false],
    ['fee_budget', 'number', false], ['on', 'choice', false], ['names', 'list', false], ['card', 'json', false], ['fills', 'json', false], ['exit_time', 'text', false]]);
  assert.deepEqual(f[4].options, ['build', 'test']);
  assert.equal(f[0].help, "The idea's name");
  assert.deepEqual(JSON.parse(f[6].starter), { why: '', home: { market: '', bar: '' }, neighbors: [] });   // an empty card of the right shape to fill in
  assert.equal(f[7].starter, '[]');
  assert.deepEqual(L.bpFields({ type: 'object', properties: {} }), []);
  assert.deepEqual(L.bpFields(null), []);
});

test('the form becomes the arguments: an empty optional field is left out, a missing required one is named', () => {
  const f = L.bpFields(SCHEMA);
  assert.deepEqual(L.bpArgs(f, { name: ' nq_orb ', confirm: false, wait_s: '', fee_budget: '345.5', on: 'test', names: 'a, b  c', card: '{"why": "x"}', fills: ' ' }),
    { args: { name: 'nq_orb', confirm: false, fee_budget: 345.5, on: 'test', names: ['a', 'b', 'c'], card: { why: 'x' } } });
  assert.deepEqual(L.bpArgs(f, { name: '', confirm: true }), { error: 'name is needed', key: 'name' });
  assert.deepEqual(L.bpArgs(f, { name: 'x', wait_s: '1.5' }), { error: 'wait_s: a whole number', key: 'wait_s' });
  assert.deepEqual(L.bpArgs(f, { name: 'x', fee_budget: 'a lot' }), { error: 'fee_budget: a number', key: 'fee_budget' });
  const bad = L.bpArgs(f, { name: 'x', card: '{why: 1}' });
  assert.equal(bad.key, 'card');
  assert.match(bad.error, /^card does not read as JSON/);
  assert.deepEqual(L.bpArgs(f, { name: 'x' }).args, { name: 'x', confirm: false }, 'a required checkbox is sent as it stands: false is an answer');
  assert.deepEqual(L.bpArgs(L.bpFields({ type: 'object', properties: { looked: { type: 'boolean' } } }), { looked: false }), { args: {} });
});

test('a job that is still going is read off the answer, and an idea has one line', () => {
  assert.equal(L.bpJob("Blueprint build: job j1 is still going (running · pass 1 of 2). Call blueprint_build(name='nq_orb', job_id='j1') to keep waiting."), 'j1');
  assert.equal(L.bpJob('Blueprint build · nq_orb · LEAD · phase 2 · round 1'), '');
  assert.equal(L.bpJob("a finished answer that names job_id='j9' in passing"), '', 'only an answer that says it is still going');
  assert.equal(L.bpIdeaLine({ status: 'proven_on_history', phase: 4, round: 1 }), 'PROVEN ON HISTORY · phase 4 · round 1');
  assert.equal(L.bpIdeaLine({ status: 'idea', phase: 0, round: null }), 'IDEA · phase 0');
});

/* ---- the toolkit's blocks ---- */
const TK = [
  { id: 'families', title: 'Entry triggers', words: '', items: [
    { id: 'family:orb', name: 'orb', sub: 'bars 5, 15', words: 'at session start + or_min, OCO stop entries beyond the opening range', markets: ['NQ', 'ES', 'GC'], runs: true, parts: [{ label: 'The family', src: 'a:1-3' }, { label: 'Gone', src: 'zz:1-1' }] }] },
  { id: 'filters', title: 'Filters', words: '', items: [
    { id: 'filter:pdz_move', name: 'pdz_move', sub: 'with | against', words: 'only when the close is cheap for the trade inside the move in progress', sides: [{ side: 'with', words: 'cheap' }, { side: 'against', words: 'dear' }], markets: ['NQ'], runs: true, parts: [] },
    { id: 'filter:book', name: 'book', sub: 'agree | disagree', words: 'Level 2 book agrees', markets: ['NQ'], runs: false, why_not: 'NQ only', parts: [] }] },
];

test('the toolkit list is searched by every word, in a name, its plain words, a side or a market; no search keeps it whole', () => {
  assert.equal(L.tkFilter(TK, ''), TK);
  assert.equal(L.tkFilter(TK, '   '), TK);
  assert.deepEqual(L.tkFilter(TK, 'pdz').map((g) => [g.id, g.items.map((i) => i.name)]), [['filters', ['pdz_move']]], 'a group with no match is dropped');
  assert.deepEqual(L.tkFilter(TK, 'DEAR move').map((g) => g.items.map((i) => i.name)), [['pdz_move']], 'a side\'s words count, case does not');
  assert.deepEqual(L.tkFilter(TK, 'es gc').map((g) => g.id), ['families']);
  assert.deepEqual(L.tkFilter(TK, 'nothing like this'), []);
  assert.equal(TK[1].items.length, 2, 'the input is not changed');
});

test('a block is found by its id; its status and markets read as plain words', () => {
  assert.equal(L.tkFind(TK, 'filter:book').name, 'book');
  assert.equal(L.tkFind(TK, 'filter:nope'), null);
  assert.equal(L.tkFind(null, 'x'), null);
  assert.deepEqual(L.tkStatus(TK[0].items[0]), { tone: 'ok', text: 'runs' });
  assert.deepEqual(L.tkStatus(TK[1].items[1]), { tone: 'no', text: 'not yet: NQ only' });
  assert.deepEqual(L.tkStatus({ runs: false }), { tone: 'no', text: 'not yet' });
  assert.equal(L.tkStatus({ runs: null }), null, 'a skill, a script or a chat tool has no run status');
  assert.equal(L.tkMarkets(TK[0].items[0]), 'NQ ES GC');
  assert.equal(L.tkMarkets({}), '');
});

test('the parts of a block are its sources in order, numbered, with their span; a source that did not come is left out', () => {
  const sources = { 'a:1-3': { file: 'research/edge-library/engine/zones.py', start: 190, end: 192, code: '        def f():\n            return 1\n' } };
  const parts = L.tkParts(TK[0].items[0], sources);
  assert.equal(parts.length, 1);
  assert.deepEqual({ n: parts[0].n, label: parts[0].label, span: parts[0].span, lines: parts[0].lines }, { n: 1, label: 'The family', span: 'engine/zones.py:190–192', lines: 3 });
  assert.equal(parts[0].code, 'def f():\n    return 1\n', 'the indentation every line shares is taken off');
  assert.equal(L.tkSpan({ file: 'homebase/x.py', start: 5, end: 5 }), 'homebase/x.py:5');
  assert.deepEqual(L.tkParts({ parts: [] }, sources), []);
  const md = L.tkParts({ parts: [{ label: 'skill', src: 'm' }] }, { m: { file: '~/.claude/skills/x/SKILL.md', start: 1, end: 2, code: '  # not code\n  text', plain: true, note: 'The first 500 of 900 lines.' } })[0];
  assert.deepEqual([md.plain, md.note, md.code], [true, 'The first 500 of 900 lines.', '  # not code\n  text'], 'text keeps its indentation and is not coloured as Python');
  assert.deepEqual(L.tkParts({}, null), []);
});

test('line numbers, dedent and the one-line clip', () => {
  assert.equal(L.tkGutter(277, 281), '277\n278\n279\n280\n281');
  assert.equal(L.tkGutter(5, 5), '5');
  assert.equal(L.tkGutter(6, 5), '');
  assert.equal(L.tkDedent('    a\n\n      b\n    c'), 'a\n\n  b\nc');
  assert.equal(L.tkDedent('x\n  y'), 'x\n  y');
  assert.equal(L.tkDedent(''), '');
  assert.equal(L.tkClip('only when the close is cheap'), 'the close is cheap');
  const long = L.tkClip('word '.repeat(60), 40);
  assert.ok(long.endsWith('…') && long.length <= 41 && !/ …$/.test(long), long);
});

/* ---- Promote to Desk: the row under a finished run (2026-10-09) ---- */
test('promoteState: no finished run of this code, or unsaved edits: the row is there and cannot be used yet', () => {
  const off = { label: 'Promote to Desk', hint: 'Run a backtest of this exact code first.', disabled: true, action: null };
  assert.deepEqual({ ...L.promoteState({ kind: 'draft', dirty: false, hasRun: false, row: null, sha: 'aa' }) }, off);
  assert.deepEqual({ ...L.promoteState({ kind: 'draft', dirty: true, hasRun: true, row: null, sha: 'aa' }) }, off, 'unsaved edits');
  assert.deepEqual({ ...L.promoteState({ kind: 'draft', dirty: true, hasRun: false, row: null, sha: '' }) }, off);
});

test('promoteState: a finished run, not on the Desk: promote', () => {
  assert.deepEqual({ ...L.promoteState({ kind: 'draft', dirty: false, hasRun: true, row: null, sha: 'aa' }) },
    { label: 'Promote to Desk', hint: 'Puts it on the Desk, switched off. It places no orders.', disabled: false, action: 'promote' });
  assert.equal(L.promoteState({ kind: 'draft', dirty: false, hasRun: true, row: undefined, sha: '' }).action, 'promote', 'a missing hash does not stop a run that finished');
});

test('promoteState: on the Desk with this same code: open it there', () => {
  const open = { label: 'On the Desk', hint: 'Open it on the Desk page.', disabled: false, action: 'open' };
  assert.deepEqual({ ...L.promoteState({ kind: 'draft', dirty: false, hasRun: true, row: { sha256: 'aa' }, sha: 'aa' }) }, open);
  assert.deepEqual({ ...L.promoteState({ kind: 'draft', dirty: false, hasRun: false, row: { sha256: 'aa' }, sha: 'aa' }) }, open, 'it is on the Desk whether or not a run is open');
});

test('promoteState: on the Desk with other code: promote again, the Desk judges the run', () => {
  assert.deepEqual({ ...L.promoteState({ kind: 'draft', dirty: false, hasRun: true, row: { sha256: 'bb' }, sha: 'aa' }) },
    { label: 'Promote again', hint: 'The Desk runs an older version. Promoting again puts this one there, switched off.', disabled: false, action: 'promote' });
  assert.deepEqual({ ...L.promoteState({ kind: 'draft', dirty: true, hasRun: true, row: { sha256: 'bb' }, sha: '' }) },
    { label: 'Promote again', hint: 'Run a backtest of this exact code first.', disabled: true, action: null });
  assert.equal(L.promoteState({ kind: 'draft', dirty: false, hasRun: false, row: { sha256: 'bb' }, sha: 'aa' }).disabled, true);
});

test('promoteState: the hash never gates Promote (a saved draft with a finished run open is enabled), it only tells the same code from other code', () => {
  // no hash (no crypto.subtle, or not worked out yet): not on the Desk -> promote; on the Desk -> "Promote again", with its own hint
  assert.deepEqual({ ...L.promoteState({ kind: 'draft', dirty: false, hasRun: true, row: null, sha: '' }) },
    { label: 'Promote to Desk', hint: 'Puts it on the Desk, switched off. It places no orders.', disabled: false, action: 'promote' });
  assert.deepEqual({ ...L.promoteState({ kind: 'draft', dirty: false, hasRun: true, row: { sha256: 'bb' }, sha: '' }) },
    { label: 'Promote again', hint: 'Promoting again puts this one there, switched off.', disabled: false, action: 'promote' });
  assert.equal(L.promoteState({ kind: 'draft', dirty: false, hasRun: true, row: { sha256: '' }, sha: '' }).action, 'promote', 'two unknowns are not the same code');
  // a hash that cannot be worked out never opens the Desk page as if it were the same code
  assert.equal(L.promoteState({ kind: 'draft', dirty: false, hasRun: false, row: { sha256: 'bb' }, sha: '' }).action, null);
  // a restored run (any run open) after a reload allows Promote without a fresh run: hasRun is "a finished run is open", nothing more
  assert.equal(L.promoteState({ kind: 'draft', dirty: false, hasRun: true, row: null, sha: 'aa' }).disabled, false);
});

test('promoteState: a built-in strategy (or a script not saved yet) has no such row', () => {
  assert.equal(L.promoteState({ kind: 'builtin', dirty: false, hasRun: true, row: null, sha: 'aa' }), null);
  assert.equal(L.promoteState({ kind: 'new', dirty: true, hasRun: true, row: null, sha: '' }), null);
  assert.equal(L.promoteState(null), null);
});

test('deskSaid: the lines after a promote, in the words of the page', () => {
  assert.deepEqual(L.deskSaid({ ok: true, notes: ['1 order can go out with no stop.', 'It sets its own size.'] }),
    ['On the Desk, switched off. Turn it on there to run it in shadow.', 'The Desk would refuse: 1 order can go out with no stop.', 'The Desk would refuse: It sets its own size.']);
  assert.deepEqual(L.deskSaid({ ok: true }), ['On the Desk, switched off. Turn it on there to run it in shadow.']);
  assert.deepEqual(L.deskSaid({ ok: true, notes: 'x' }), ['On the Desk, switched off. Turn it on there to run it in shadow.'], 'notes is a list or nothing');
  assert.deepEqual(L.deskSaid({ ok: true, notes: [1, null, ''] }), ['On the Desk, switched off. Turn it on there to run it in shadow.']);
});
