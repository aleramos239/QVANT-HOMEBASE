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


/* ---- the strategy form's pure half (fm*): the schema is the server's, the page knows no rule by name ---- */
const FM = JSON.parse(readFileSync(new URL('./fixtures/form_schema.json', import.meta.url), 'utf8'));      // the server's own schema: tests/test_lab_forms.py keeps the file equal to lab_forms.schema()
const FM_TAKEN = ['nq_open_straddle', 'my_strategy'];

test('fm: the fields shown for a rule are the schema\'s, in its order, after name, market and the rule', () => {
  assert.deepEqual(L.fmShown(FM, 'open_straddle'), ['name', 'market', 'rule', 'side', 'time', 'distance', 'stop', 'target', 'last_entry', 'out_by']);
  assert.deepEqual(L.fmShown(FM, 'at_time'), ['name', 'market', 'rule', 'side', 'time', 'stop', 'target', 'out_by']);
  assert.deepEqual(L.fmShown(FM, 'bar_breakout'), ['name', 'market', 'rule', 'side', 'bar_min', 'lookback', 'from', 'last_entry', 'trades', 'stop', 'target', 'out_by']);
  assert.deepEqual(L.fmShown(FM, 'nope'), [], 'a rule the schema does not list shows nothing');
  // no rule is named: a made-up schema works the same
  const odd = { rules: [{ id: 'zz', fields: ['market', 'qq', 'out_by'] }], fields: {} };
  assert.deepEqual(L.fmShown(odd, 'zz'), ['name', 'market', 'rule', 'qq', 'out_by']);
  assert.deepEqual(L.fmKeys(odd, 'zz'), ['name', 'rule', 'market', 'qq', 'out_by']);
});

test('fm: the helper words of a field are the rule\'s own when the schema has them, else the field\'s', () => {
  assert.equal(L.fmWords(FM, 'at_time', 'side'), 'Buy or sell.');
  assert.equal(L.fmWords(FM, 'bar_breakout', 'side'), 'Buy, sell, or both.');
  assert.equal(L.fmWords(FM, 'open_straddle', 'last_entry'), 'No new entry after this time. An entry order not filled by then is cancelled.');
  assert.equal(L.fmWords(FM, 'opening_range', 'last_entry'), 'No new entry after this time. An entry order not filled by then is cancelled.');
  assert.equal(L.fmWords(FM, 'bar_breakout', 'last_entry'), 'No new entry after this time.');
  assert.equal(L.fmWords(FM, 'at_time', 'time'), FM.fields.time.words, 'a field with no words_by_rule shows its own words');
  // no rule is named: any schema works the same
  const odd = { fields: { qq: { words: 'plain', words_by_rule: { zz: 'for zz' } } } };
  assert.equal(L.fmWords(odd, 'zz', 'qq'), 'for zz');
  assert.equal(L.fmWords(odd, 'other', 'qq'), 'plain');
  assert.equal(L.fmWords(odd, 'zz', 'nope'), '');
});

test('fm: a new market gives the starting distance, stop and target of that market, to the boxes that still hold the old ones', () => {
  const st = L.fmFill(FM, { ...FM.defaults.open_straddle, name: 'x', target: { kind: 'points', value: 40 } });   // NQ: 15 / 50 / a points target of 40
  const es = L.fmSetMarket(FM, st, 'ES');
  assert.equal(es.market, 'ES');
  assert.equal(es.distance, 3.75);
  assert.deepEqual(es.stop, { kind: 'points', value: 12.5 });
  assert.deepEqual(es.target, { kind: 'points', value: 10 });
  assert.equal(st.market, 'NQ');
  assert.equal(st.distance, 15, 'the state it was given is not changed');
  assert.deepEqual(L.fmSetMarket(FM, es, 'SI').stop, { kind: 'points', value: 0.15 });
  assert.equal(L.fmSetMarket(FM, es, 'SI').distance, 0.045);
  assert.equal(L.fmSetMarket(FM, L.fmSetMarket(FM, es, 'SI'), 'NQ').distance, 15, 'and back again');
  for (const m of FM.markets) {                                      // every market\'s own numbers are what the schema says for the rule
    const got = L.fmSetMarket(FM, st, m), z = FM.sizes[m].open_straddle;
    assert.deepEqual([got.distance, got.stop.value], [z.distance, z.stop], m);
    assert.deepEqual(L.fmErrors(FM, got), {}, `${m}: the numbers pass the page's own tick check`);
  }
});

test('fm: every rule has its own starting numbers on every market', () => {
  for (const r of FM.rules) for (const m of FM.markets) {
    const nq = L.fmFill(FM, { ...FM.defaults[r.id], name: 'x' }), z = FM.sizes[m][r.id], got = L.fmSetMarket(FM, nq, m);
    if ('distance' in z) assert.equal(got.distance, z.distance, `${r.id} ${m}`);
    if ('stop' in z) assert.deepEqual(got.stop, { kind: 'points', value: z.stop }, `${r.id} ${m}`);
    if ('target_points' in z) assert.deepEqual(got.target, { kind: 'points', value: z.target_points }, `${r.id} ${m}`);
    assert.deepEqual(L.fmErrors(FM, got), {}, `${r.id} ${m}`);
  }
  const bb = L.fmSetMarket(FM, L.fmFill(FM, { ...FM.defaults.bar_breakout, name: 'x' }), 'SI');
  assert.deepEqual([bb.stop.value, bb.target.value], [0.06, 0.12]);
  // the range stop and the ratio target have no number to move
  const orr = L.fmSetMarket(FM, L.fmFill(FM, { ...FM.defaults.opening_range, name: 'x' }), 'SI');
  assert.deepEqual([orr.stop, orr.target], [{ kind: 'range' }, { kind: 'rr', value: 2 }]);
});

test('fm: a number he typed himself is never changed by a new market', () => {
  const st = L.fmFill(FM, { ...FM.defaults.open_straddle, name: 'x' });
  st.distance = '20'; st.stop = { kind: 'points', value: '60' }; st.target = { kind: 'points', value: '120' };
  const es = L.fmSetMarket(FM, st, 'ES');
  assert.equal(es.distance, '20');
  assert.deepEqual(es.stop, { kind: 'points', value: '60' });
  assert.deepEqual(es.target, { kind: 'points', value: '120' });
  // a box that holds the old starting number as typed text ("50", " 50.0 ") still counts as holding it
  st.stop = { kind: 'points', value: ' 50.0 ' };
  assert.deepEqual(L.fmSetMarket(FM, st, 'YM').stop, { kind: 'points', value: 100 });
  // a ratio target, the range stop and a box left empty are not points: nothing to fit
  const rr = L.fmFill(FM, { ...FM.defaults.opening_range, name: 'x' });
  assert.deepEqual(L.fmSetMarket(FM, rr, 'ES').stop, { kind: 'range' });
  assert.deepEqual(L.fmSetMarket(FM, rr, 'ES').target, { kind: 'rr', value: 2 });
  assert.equal(L.fmSetMarket(FM, { ...st, distance: '' }, 'ES').distance, '');
  // a rule with no distance box has none to fit
  assert.equal('distance' in L.fmSetMarket(FM, L.fmSwitch(FM, st, 'at_time'), 'ES'), false);
  // a market the schema has no sizes for only changes the market
  assert.equal(L.fmSetMarket(FM, L.fmStart(FM, []), 'CL').distance, 15);
  assert.equal(L.fmSetMarket({ ...FM, sizes: undefined }, st, 'ES').market, 'ES');
});

test('fm: a rule change on another market starts the new rule\'s own boxes at that market\'s numbers', () => {
  const es = L.fmSetMarket(FM, L.fmStart(FM, []), 'ES');
  const back = L.fmSwitch(FM, L.fmSwitch(FM, es, 'at_time'), 'open_straddle');
  assert.equal(back.market, 'ES');
  assert.equal(back.distance, 3.75, 'the straddle\'s distance box is the ES starting number, not NQ\'s');
  assert.deepEqual(back.stop, { kind: 'points', value: 12.5 }, 'the stop he carried across is kept as it was');
  const bb = L.fmSwitch(FM, es, 'bar_breakout');
  assert.deepEqual(bb.target, { kind: 'rr', value: 3 }, 'a carried target is kept');
  const fresh = L.fmSwitch(FM, { ...L.fmFill(FM, { ...FM.defaults.opening_range, name: 'x' }), market: 'ES' }, 'bar_breakout');
  assert.deepEqual([fresh.stop, fresh.target], [{ kind: 'points', value: 5 }, { kind: 'rr', value: 2 }], 'the range stop is not offered: the new rule\'s own stop at the ES number; the ratio carries');
  // what he typed in the old rule and the new rule has too is carried: a stop he typed survives the switch
  const typed = L.fmSetMarket(FM, L.fmStart(FM, []), 'ES');
  typed.stop = { kind: 'points', value: '50' };
  assert.deepEqual(L.fmSwitch(FM, typed, 'at_time').stop, { kind: 'points', value: '50' });
  // a points choice picked on a market starts at that market's number for the rule
  assert.equal(L.fmKindValue(FM, 'bar_breakout', 'target', 'points', 'ES'), 10);
  assert.equal(L.fmKindValue(FM, 'open_straddle', 'stop', 'points', 'ES'), 12.5);
  assert.equal(L.fmKindValue(FM, 'opening_range', 'stop', 'points', 'ES'), 12.5, 'a rule with no number of its own takes the first rule\'s (in the schema\'s rules order) that has one');
  assert.equal(L.fmKindValue(FM, 'open_straddle', 'target', 'points'), 40, 'no market given: as before');
  assert.equal(L.fmKindValue(FM, 'open_straddle', 'target', 'rr', 'ES'), 3, 'a ratio is the same on every market');
});

const fmSteps = (st, steps) => steps.reduce((s, [what, to]) => (what === 'market' ? L.fmSetMarket(FM, s, to) : L.fmSwitch(FM, s, to)), st);
const fmStop = (st) => st.stop && st.stop.value;

test('fm: the starting numbers fit the market and the rule on ANY click order', () => {
  const fresh = () => L.fmStart(FM, []);                                              // NQ stop straddle: 15 / 50
  // the reviewer\'s two orders: rule then market, and SI straddle -> Bar breakout -> NQ
  assert.equal(fmStop(fmSteps(fresh(), [['rule', 'bar_breakout']])), 20, 'NQ: the straddle\'s 50 is not the bar breakout\'s');
  assert.equal(fmStop(fmSteps(fresh(), [['rule', 'bar_breakout'], ['market', 'SI']])), 0.06);
  assert.equal(fmStop(fmSteps(fresh(), [['market', 'SI'], ['rule', 'bar_breakout'], ['market', 'NQ']])), 20);
  // the reverse orders
  assert.equal(fmStop(fmSteps(fresh(), [['market', 'SI'], ['rule', 'bar_breakout']])), 0.06);
  assert.equal(fmStop(fmSteps(fresh(), [['market', 'SI'], ['rule', 'at_time'], ['rule', 'open_straddle']])), 0.15);
  // every rule x rule x market x market, both orders: the boxes are the new rule\'s numbers for the new market and nothing is out of bounds
  for (const a of FM.rules) for (const b of FM.rules) for (const m1 of FM.markets) for (const m2 of FM.markets) {
    const start = L.fmSetMarket(FM, L.fmFill(FM, { ...FM.defaults[a.id], name: 'x' }), m1);
    for (const steps of [[['rule', b.id], ['market', m2]], [['market', m2], ['rule', b.id]]]) {
      const got = fmSteps(start, steps), z = FM.sizes[m2][b.id], tag = `${a.id}@${m1} ${JSON.stringify(steps)}`;
      assert.equal(got.market, m2, tag);
      if ('stop' in z && got.stop.kind === 'points') assert.equal(got.stop.value, z.stop, tag);
      if ('target_points' in z && got.target.kind === 'points') assert.equal(got.target.value, z.target_points, tag);
      if ('distance' in z && 'distance' in got) assert.equal(got.distance, z.distance, tag);
      assert.deepEqual(L.fmErrors(FM, got), {}, tag);
    }
  }
  // a number he typed that is no starting number of the market is never changed, on any step
  const typed = fresh();
  typed.stop = { kind: 'points', value: '60' }; typed.distance = '20';
  const moved = fmSteps(typed, [['rule', 'bar_breakout'], ['market', 'YM'], ['rule', 'open_straddle'], ['market', 'NQ']]);
  assert.equal(fmStop(moved), '60');
  assert.equal(moved.distance, 15, 'the distance box belongs to the straddle: it starts again each time the rule has one');
});

test('fm: the fallback number is the first rule\'s in the schema\'s rules order, whatever order the objects are in', () => {
  const rev = (o) => Object.fromEntries(Object.entries(o).reverse());
  const FR = { ...FM, defaults: rev(FM.defaults), sizes: Object.fromEntries(Object.entries(FM.sizes).reverse().map(([m, r]) => [m, rev(r)])) };
  assert.equal(FM.rules[0].id, 'open_straddle');
  for (const sc of [FM, FR]) {
    assert.equal(L.fmKindValue(sc, 'opening_range', 'stop', 'points', 'NQ'), 50);
    assert.equal(L.fmKindValue(sc, 'opening_range', 'stop', 'points'), 50);
    assert.equal(L.fmKindValue(sc, 'opening_range', 'target', 'points', 'NQ'), 40);
    assert.equal(L.fmKindValue(sc, 'opening_range', 'stop', 'points', 'SI'), 0.15);
    const orr = L.fmFill(sc, { ...sc.defaults.opening_range, name: 'x' });
    orr.stop = { kind: 'points', value: 50 };
    assert.equal(L.fmSetMarket(sc, orr, 'ES').stop.value, 12.5);
  }
});

test('fm: reading a file back uses the FILE\'s market for every starting number', () => {
  const si = (extra) => L.fmFill(FM, { ...FM.defaults.open_straddle, market: 'SI', name: 'x', distance: 0.045, ...extra });
  assert.deepEqual(si({ stop: { kind: 'range' } }).stop, { kind: 'points', value: 0.15 }, 'the straddle\'s SI stop, not the NQ 50');
  assert.deepEqual(si({ target: { kind: 'bogus' } }).target, { kind: 'rr', value: 3 });
  const thin = L.fmFill(FM, { name: 'x', rule: 'bar_breakout', market: 'SI' });          // a file that holds only a market
  assert.deepEqual([thin.stop, thin.target], [{ kind: 'points', value: 0.06 }, { kind: 'points', value: 0.12 }]);
  assert.equal(L.fmFill(FM, { name: 'x', rule: 'open_straddle', market: 'GC' }).distance, 1.9);
  assert.deepEqual(L.fmFill(FM, { name: 'x', rule: 'open_straddle', market: 'NQ' }).stop, { kind: 'points', value: 50 });
  assert.equal(L.fmFill(FM, { name: 'x', rule: 'open_straddle', market: 'CL' }).distance, 15, 'a market with no numbers: the defaults');
  // what the file holds is what the form shows
  assert.equal(si({ stop: { kind: 'points', value: 0.3 } }).stop.value, 0.3);
});

test('fm: a number too far for the market is caught on the page with the server\'s sentence', () => {
  const st = (market, over) => ({ ...L.fmFill(FM, { ...FM.defaults.open_straddle, name: 'x' }), market, ...over });
  const pts = (v) => ({ kind: 'points', value: v });
  assert.deepEqual(L.fmErrors(FM, st('NQ', { stop: pts(500) })), {});
  assert.deepEqual(L.fmErrors(FM, st('NQ', { stop: pts(500.25) })), { stop: 'Too far for this market: at most 500 points.' });
  assert.deepEqual(L.fmErrors(FM, st('NQ', { distance: '501' })), { distance: 'Too far for this market: at most 500 points.' });
  assert.deepEqual(L.fmErrors(FM, st('NQ', { target: pts(1500.25) })), { target: 'Too far for this market: at most 1500 points.' });
  assert.deepEqual(L.fmErrors(FM, st('SI', { stop: pts(10.005), distance: 0.05 })), { stop: 'Too far for this market: at most 10 points.' });
  assert.deepEqual(L.fmErrors(FM, st('GC', { stop: pts(200.1), distance: 2 })), { stop: 'Too far for this market: at most 200 points.' });
  assert.deepEqual(L.fmErrors(FM, st('YM', { stop: pts(2001), distance: 30 })), { stop: 'Too far for this market: at most 2000 points.' });
  // the tick sentence still comes first
  assert.deepEqual(L.fmErrors(FM, st('NQ', { stop: pts(500.1) })), { stop: 'Use a multiple of the tick (0.25).' });
  // the old NQ default on silver is out of bounds now
  assert.ok(L.fmErrors(FM, st('SI', {})).stop);
});

test('fm: a rule\'s answer keys are name, rule and its fields (nothing else belongs)', () => {
  assert.deepEqual(L.fmKeys(FM, 'at_time'), ['name', 'rule', 'market', 'side', 'time', 'stop', 'target', 'out_by']);
});

test('fm: which stop and target choices and which sides a rule offers', () => {
  assert.deepEqual(L.fmKinds(FM, 'at_time', 'target').map((k) => k.id), ['points', 'rr', 'none']);
  // the real schema: "Other side of the range" belongs to the opening range only
  assert.deepEqual(L.fmKinds(FM, 'opening_range', 'stop').map((k) => k.id), ['points', 'range']);
  for (const r of ['open_straddle', 'bar_breakout', 'at_time']) assert.deepEqual(L.fmKinds(FM, r, 'stop').map((k) => k.id), ['points'], r);
  for (const r of FM.rules) assert.deepEqual(L.fmKinds(FM, r.id, 'target').map((k) => k.id), ['points', 'rr', 'none'], 'a target choice with no rules list is offered to every rule');
  // a choice the schema limits to some rules is offered to those rules only
  const limited = { fields: { stop: { kinds: [{ id: 'points' }, { id: 'range', rules: ['opening_range'] }] } } };
  assert.deepEqual(L.fmKinds(limited, 'opening_range', 'stop').map((k) => k.id), ['points', 'range']);
  assert.deepEqual(L.fmKinds(limited, 'at_time', 'stop').map((k) => k.id), ['points']);
  assert.deepEqual(L.fmSides(FM, 'at_time'), [['long', 'Long only'], ['short', 'Short only']]);
  assert.deepEqual(L.fmSides(FM, 'open_straddle').map((s) => s[0]), ['both', 'long', 'short']);
  assert.equal(L.fmHasValue({ id: 'points', min_ticks: 2 }), true);
  assert.equal(L.fmHasValue({ id: 'rr', min: 0.25, max: 20 }), true);
  assert.equal(L.fmHasValue({ id: 'none' }), false);
  assert.equal(L.fmHasValue({ id: 'range' }), false);
});

test('fm: the value a choice starts from comes from the schema\'s defaults, never from a rule\'s name', () => {
  assert.equal(L.fmKindValue(FM, 'at_time', 'stop', 'points'), 20);
  assert.equal(L.fmKindValue(FM, 'open_straddle', 'stop', 'points'), 50);
  assert.equal(L.fmKindValue(FM, 'open_straddle', 'target', 'points'), 40, 'this rule\'s default is a ratio: the first points default of any rule');
  assert.equal(L.fmKindValue(FM, 'bar_breakout', 'target', 'rr'), 3);
  assert.equal(L.fmKindValue(FM, 'open_straddle', 'target', 'none'), '');
});

test('fm: the first state is the first rule\'s defaults with a suggested name', () => {
  const s = L.fmStart(FM, ['nq_open_straddle']);
  assert.equal(s.rule, 'open_straddle');
  assert.equal(s.market, 'NQ');
  assert.equal(s.name, 'nq_open_straddle_2');
  assert.deepEqual(s.stop, { kind: 'points', value: 50 });
  assert.equal('distance' in s, true);
  s.stop.value = 1;
  assert.equal(L.fmStart(FM, []).stop.value, 50, 'a state never shares an object with the schema');
  assert.equal(FM.defaults.open_straddle.stop.value, 50);
});

test('fm: a suggested name is the market and the rule, made unique the way a pasted script\'s is', () => {
  assert.equal(L.fmSuggest('NQ', 'open_straddle', []), 'nq_open_straddle');
  assert.equal(L.fmSuggest('GC', 'at_time', ['gc_at_time', 'gc_at_time_2']), 'gc_at_time_3');
  assert.equal(L.fmSuggest('RTY', 'bar_breakout', []), 'rty_bar_breakout');
  assert.equal(L.fmSuggest('', '', []), 'my_strategy');
  assert.equal(L.fmSuggest('NQ', 'x'.repeat(60), []).length <= 40, true);
  assert.equal(L.nameError(L.fmSuggest('NQ', 'x'.repeat(60), [])), null);
});

test('fm: changing the rule keeps name, market, side, stop, target and out by, and fills the rest from that rule\'s defaults', () => {
  const a = L.fmStart(FM, []);
  Object.assign(a, { name: 'mine', market: 'GC', side: 'short', out_by: '15:30', distance: '22', last_entry: '12:00', stop: { kind: 'points', value: '33' }, target: { kind: 'points', value: '77' } });
  const b = L.fmSwitch(FM, a, 'bar_breakout');
  assert.equal(b.rule, 'bar_breakout');
  assert.deepEqual([b.name, b.market, b.side, b.out_by], ['mine', 'GC', 'short', '15:30']);
  assert.deepEqual(b.stop, { kind: 'points', value: '33' });
  assert.deepEqual(b.target, { kind: 'points', value: '77' });
  assert.deepEqual([b.bar_min, b.lookback, b.from, b.trades, b.last_entry], [5, 6, '09:30', 1, '11:00'], 'the rule\'s own fields start from its defaults');
  assert.equal('distance' in b, false, 'a key the new rule does not have is gone');
  assert.deepEqual(Object.keys(L.fmAnswers(FM, b)).sort(), [...L.fmKeys(FM, 'bar_breakout')].sort());
  // a copy, not the same object
  b.stop.value = 'x';
  assert.equal(a.stop.value, '33');
});

test('fm: from the opening range with the range stop, any other rule starts from its own default stop and shows no error', () => {
  const a = L.fmFill(FM, { ...FM.defaults.opening_range, name: 'n' });
  assert.deepEqual(a.stop, { kind: 'range' });
  for (const r of ['open_straddle', 'bar_breakout', 'at_time']) {
    const b = L.fmSwitch(FM, a, r);
    assert.deepEqual(b.stop, FM.defaults[r].stop, r);
    assert.deepEqual(L.fmErrors(FM, b), {}, r);
    assert.equal(L.fmKinds(FM, r, 'stop').some((k) => k.id === b.stop.kind), true, 'the kind it lands on is one the rule offers');
  }
  // and the other way round a points stop is kept: a number he typed as it is, a starting number as the first rule\'s (the opening range has none)
  const p = L.fmSwitch(FM, L.fmStart(FM, []), 'bar_breakout');
  assert.deepEqual(L.fmSwitch(FM, p, 'opening_range').stop, { kind: 'points', value: 50 });
  p.stop = { kind: 'points', value: '33' };
  assert.deepEqual(L.fmSwitch(FM, p, 'opening_range').stop, { kind: 'points', value: '33' });
});

test('fm: a rule change drops a shared answer the new rule does not take', () => {
  const a = L.fmStart(FM, []);      // side: both
  const b = L.fmSwitch(FM, a, 'at_time');
  assert.equal(b.side, 'long', 'both is not offered here: the rule\'s default side');
  assert.equal('last_entry' in b, false);
  const limited = { rules: [{ id: 'r1', fields: ['market', 'stop'], sides: ['both'] }, { id: 'r2', fields: ['market', 'stop'], sides: ['both'] }],
    fields: { stop: { kinds: [{ id: 'points', min_ticks: 2 }, { id: 'range', rules: ['r1'] }] } },
    defaults: { r1: { rule: 'r1', market: 'NQ', stop: { kind: 'range' } }, r2: { rule: 'r2', market: 'NQ', stop: { kind: 'points', value: 9 } } } };
  const c = L.fmSwitch(limited, { rule: 'r1', name: 'n', market: 'ES', stop: { kind: 'range' } }, 'r2');
  assert.deepEqual(c.stop, { kind: 'points', value: 9 }, 'a stop kind the new rule does not offer falls back to its default');
  assert.equal(c.market, 'ES');
});

test('fm: a name that was suggested follows the market and rule; one he typed does not (the dialog decides which)', () => {
  const a = L.fmStart(FM, []);
  const b = L.fmSwitch(FM, a, 'at_time');
  assert.equal(b.name, a.name, 'switching keeps the name; the page re-suggests only while it is untouched');
});

test('fm: the page-side number check: empty, not a number, below the floor, not a multiple of the tick', () => {
  const dist = FM.fields.distance, tick = FM.ticks.NQ;
  assert.equal(L.fmNumberError(dist, '15', tick), '');
  assert.equal(L.fmNumberError(dist, 15, tick), '');
  assert.equal(L.fmNumberError(dist, ' 15.25 ', tick), '');
  assert.equal(L.fmNumberError(dist, '', tick), 'Type a number.');
  assert.equal(L.fmNumberError(dist, 'abc', tick), 'Type a number.');
  assert.equal(L.fmNumberError(dist, '1e3', tick), 'Type a number.', 'plain digits only');
  assert.equal(L.fmNumberError(dist, '0x10', tick), 'Type a number.');
  assert.equal(L.fmNumberError(dist, '0', tick), 'Use at least 0.25.');
  assert.equal(L.fmNumberError(dist, '-5', tick), 'Use at least 0.25.');
  assert.equal(L.fmNumberError(dist, '0.1', tick), 'Use at least 0.25.');
  assert.equal(L.fmNumberError(dist, '7.5', FM.ticks.YM), 'Use a multiple of the tick (1).');
  assert.equal(L.fmNumberError(dist, '7.3', tick), 'Use a multiple of the tick (0.25).');
  assert.equal(L.fmNumberError(dist, '7.25', tick), '');
  assert.equal(L.fmNumberError(dist, '0.3', FM.ticks.GC), '', '0.3 / 0.1 is whole within 1e-9');
  assert.equal(L.fmNumberError(dist, '0.015', FM.ticks.SI), '');
  const stop = FM.fields.stop.kinds[0];
  assert.equal(L.fmNumberError(stop, '0.25', tick), 'Use at least 0.5.', 'a stop is at least two ticks');
  assert.equal(L.fmNumberError(stop, '0.5', tick), '');
  assert.equal(L.fmNumberError(FM.fields.target.kinds[0], '0.25', tick), '');
});

test('fm: whole-number and ratio boxes carry their own limits, whatever the market', () => {
  const lb = FM.fields.lookback, rr = FM.fields.target.kinds[1];
  assert.equal(L.fmNumberError(lb, '6', 0.25), '');
  assert.equal(L.fmNumberError(lb, '2', 0.25), '');
  assert.equal(L.fmNumberError(lb, '40', 0.25), '');
  assert.equal(L.fmNumberError(lb, '1', 0.25), 'Between 2 and 40.');
  assert.equal(L.fmNumberError(lb, '41', 0.25), 'Between 2 and 40.');
  assert.equal(L.fmNumberError(lb, '6.5', 0.25), 'Between 2 and 40.', 'a whole number');
  assert.equal(L.fmNumberError(FM.fields.trades, '6', 0.25), 'Between 1 and 5.');
  assert.equal(L.fmNumberError(rr, '3', 0.25), '');
  assert.equal(L.fmNumberError(rr, '0.2', 0.25), 'Between 0.25 and 20.');
  assert.equal(L.fmNumberError(rr, '20.5', 0.25), 'Between 0.25 and 20.');
  assert.equal(L.fmNumberError(rr, '', 0.25), 'Type a number.');
});

test('fm: the page-side errors of a state are by field, for the boxes that are shown only', () => {
  const s = L.fmStart(FM, []);
  assert.deepEqual(L.fmErrors(FM, s), {});
  s.distance = '';
  s.stop = { kind: 'points', value: 'abc' };
  s.target = { kind: 'rr', value: '30' };
  assert.deepEqual(L.fmErrors(FM, s), { distance: 'Type a number.', stop: 'Type a number.', target: 'Between 0.25 and 20.' });
  s.stop = { kind: 'range' }; s.target = { kind: 'none' }; s.distance = '7.3';
  assert.deepEqual(L.fmErrors(FM, s), { distance: 'Use a multiple of the tick (0.25).' }, 'a kind with no number has no box to check');
  // a box of a field the rule does not have is not looked at
  const t = L.fmSwitch(FM, s, 'at_time');
  t.lookback = 'junk';
  assert.deepEqual(L.fmErrors(FM, t), {});
  // the market's tick is the one used
  const y = L.fmStart(FM, []); y.market = 'YM'; y.distance = '7.5';
  assert.deepEqual(L.fmErrors(FM, y), { distance: 'Use a multiple of the tick (1).' });
});

test('fm: the answers object has the rule\'s keys only, numbers as numbers, choices with their own type', () => {
  const s = L.fmStart(FM, []);
  Object.assign(s, { name: '  my_orb ', distance: '15.5', stop: { kind: 'points', value: '50' }, target: { kind: 'rr', value: '2.5' }, junk: 1, lookback: 9 });
  assert.deepEqual(L.fmAnswers(FM, s), { name: 'my_orb', rule: 'open_straddle', market: 'NQ', side: 'both', time: '09:30', distance: 15.5,
    stop: { kind: 'points', value: 50 }, target: { kind: 'rr', value: 2.5 }, last_entry: '11:00', out_by: '15:55' });
  const r = L.fmSwitch(FM, s, 'opening_range');
  r.range_min = '30';
  const a = L.fmAnswers(FM, r);
  assert.strictEqual(a.range_min, 30, 'the choice list holds numbers: the answer is a number');
  assert.deepEqual(Object.keys(a).sort(), [...L.fmKeys(FM, 'opening_range')].sort());
  const k = L.fmAnswers(FM, { ...r, stop: { kind: 'range', value: '12' }, target: { kind: 'none', value: '4' } });
  assert.deepEqual(k.stop, { kind: 'range' }, 'a kind with no number sends none');
  assert.deepEqual(k.target, { kind: 'none' });
  const bb = L.fmSwitch(FM, s, 'bar_breakout');
  bb.lookback = '12'; bb.trades = '3';
  assert.strictEqual(L.fmAnswers(FM, bb).lookback, 12);
  assert.strictEqual(L.fmAnswers(FM, bb).trades, 3);
  // a box that is not a number stays what was typed, for the server to refuse in its words
  bb.lookback = 'many';
  assert.strictEqual(L.fmAnswers(FM, bb).lookback, 'many');
});

test('fm: reading a file\'s answers back into a state fills what is missing from the rule\'s defaults and drops what does not belong', () => {
  const got = { name: 'x_y', rule: 'at_time', market: 'ES', side: 'short', time: '10:00', stop: { kind: 'points', value: 12 }, target: { kind: 'none' }, out_by: '15:00', distance: 4 };
  const s = L.fmFill(FM, got);
  assert.deepEqual(L.fmAnswers(FM, s), { name: 'x_y', rule: 'at_time', market: 'ES', side: 'short', time: '10:00', stop: { kind: 'points', value: 12 }, target: { kind: 'none' }, out_by: '15:00' });
  assert.equal(L.fmFill(FM, { name: 'a', rule: 'mystery' }), null, 'a rule this page does not know is not opened');
  assert.equal(L.fmFill(FM, null), null);
  const thin = L.fmFill(FM, { name: 'a', rule: 'at_time' });
  assert.equal(thin.time, '09:30');
});

test('fm: a hand-edited header cannot trap the dialog -- a stop or target the rule does not offer starts from the rule\'s own', () => {
  const straddle = { ...FM.defaults.open_straddle, name: 'x' };
  // the range stop belongs to the opening range only
  const s = L.fmFill(FM, { ...straddle, stop: { kind: 'range' } });
  assert.deepEqual(s.stop, FM.defaults.open_straddle.stop);
  assert.deepEqual(L.fmErrors(FM, s), {});
  assert.deepEqual(L.fmAnswers(FM, s).stop, { kind: 'points', value: 50 }, 'the read-back shows it');
  // a kind nobody offers, a stop that is not an object, a target with no kind
  assert.deepEqual(L.fmFill(FM, { ...straddle, target: { kind: 'bogus', value: 5 } }).target, FM.defaults.open_straddle.target);
  assert.deepEqual(L.fmFill(FM, { ...straddle, stop: 'wide' }).stop, FM.defaults.open_straddle.stop);
  assert.deepEqual(L.fmFill(FM, { ...straddle, target: {} }).target, FM.defaults.open_straddle.target);
  assert.deepEqual(L.fmFill(FM, { ...straddle, stop: null }).stop, FM.defaults.open_straddle.stop);
  // a side the rule does not offer (both on at_time) is the rule's default side
  assert.equal(L.fmFill(FM, { ...FM.defaults.at_time, name: 'x', side: 'both' }).side, 'long');
  assert.equal(L.fmFill(FM, { ...FM.defaults.at_time, name: 'x', side: 'short' }).side, 'short');
  assert.equal(L.fmFill(FM, { ...straddle, side: 'sideways' }).side, 'both');
  assert.equal(L.fmAnswers(FM, L.fmFill(FM, { ...FM.defaults.at_time, name: 'x', side: 'both' })).side, 'long');
  // what the rule offers is kept, with its number (also a number that is wrong: the server says so)
  assert.deepEqual(L.fmFill(FM, { ...straddle, stop: { kind: 'points', value: 7 } }).stop, { kind: 'points', value: 7 });
  assert.deepEqual(L.fmFill(FM, { ...straddle, target: { kind: 'none' } }).target, { kind: 'none' });
  const orange = { ...FM.defaults.opening_range, name: 'x' };
  assert.deepEqual(L.fmFill(FM, orange).stop, { kind: 'range' }, 'the opening range keeps its own');
  // the returned state is its own: changing it leaves the schema\'s defaults alone
  const t = L.fmFill(FM, { ...straddle, stop: { kind: 'range' } });
  t.stop.value = '1';
  assert.equal(FM.defaults.open_straddle.stop.value, 50);
});

test('fm: the time boxes stop at 15:55 and the server\'s sentences are shown as they come', () => {
  assert.equal(L.FM_LATEST, '15:55');
  assert.equal(L.fmFirstError({ stop: 'Every entry needs a stop.', name: 'bad' }, ['name', 'market', 'stop']), 'bad', 'the first in the order the fields are shown');
  assert.equal(L.fmFirstError({ form: 'The form is incomplete.' }, ['name']), 'The form is incomplete.', 'a key that is no field of the form comes last');
  assert.equal(L.fmFirstError({}, ['name']), '');
});

/* ---- the form's sheet in lab.js (source-text pins: the page has no DOM to run it in here) ---- */
import { readFileSync } from 'node:fs';
const LABJS = readFileSync(new URL('../../homebase/static/charts/lab.js', import.meta.url), 'utf8');
const CODEJS = readFileSync(new URL('../../homebase/static/charts/labcode.js', import.meta.url), 'utf8');
const CSS = readFileSync(new URL('../../homebase/static/charts/lab.css', import.meta.url), 'utf8');
const FMSEC = LABJS.slice(LABJS.indexOf('/* ---- the strategy form: "Fill in a form"'), LABJS.indexOf('function reviewDialog()'));
const FMPURE = CODEJS.slice(CODEJS.indexOf('/* ---- the strategy form ("Fill in a form"): the pure half'), CODEJS.indexOf('\nconst api = {'));

test('form sheet: the words the owner reads are the brief\'s', () => {
  assert.ok(FMSEC.length > 4000, 'the section is there');
  for (const t of ['<b>Fill in a form</b><small>Pick a market, an entry rule, a stop and a target. No code.</small>', "'Edit strategy' : 'New strategy'", "'Update' : 'Make it'",
    'Made from the form. Run it to see how it would have done.', 'Updated from the form. Run it again.',
    "This strategy was changed by hand. Updating it from the form replaces the code with the form's version.", 'Open the form', 'Edit in the form…']) assert.ok(LABJS.includes(t), t);
  assert.match(LABJS, /menu\(anchor, `<button data-pick="form">/, 'the form is the first item of the + menu');
});

test('form sheet: only the three form routes, and the page names no rule', () => {
  const urls = [...FMSEC.matchAll(/['"`](\/api\/[^'"`$?]*)/g)].map((m) => m[1]);
  assert.deepEqual([...new Set(urls)].sort(), ['/api/tester/drafts/form', '/api/tester/drafts/form/build', '/api/tester/drafts/form/read']);
  for (const src of [FMSEC, FMPURE]) assert.doesNotMatch(src.replace(/\/\*[\s\S]*?\*\//g, ''), /open_straddle|opening_range|bar_breakout|at_time|straddle|breakout/);
  assert.doesNotMatch(FMSEC, /setInterval/, 'nothing polls');
});

test('form sheet: asked at most every 400 ms, never while an answer is out; Make it waits for the answer to this very form', () => {
  assert.match(FMSEC, /timer = setTimeout\(ask, 400\)/);
  assert.match(FMSEC, /if \(!d\.isConnected \|\| flying\) return;/);
  assert.match(FMSEC, /const ready = \(\) => !making && !stale && !failed && !flying && !timer && !!built && built\.ver === ver/);
  assert.match(FMSEC, /edit \? \{ answers, replace: true \} : \{ answers \}/);
  assert.match(FMSEC, /openScript\(built\.code, built\.name\)/);
  assert.equal((FMSEC.match(/'\/api\/tester\/drafts\/form\/read'/g) || []).length, 1, 'one place asks for the read, cached by code');
});

test('form sheet: nothing is rebuilt under a focused box -- only the part under the rule, redrawn from the rule\'s own list', () => {
  assert.equal((FMSEC.match(/\.innerHTML = /g) || []).length, 2, 'the sheet once, and the part below the rule: nothing else is redrawn');
  assert.match(FMSEC, /rest\.innerHTML = restHtml\(\)/);
  assert.match(FMSEC, /h\.textContent = e\[f\] \|\| words\(f\)/, 'helper words and errors are patched in place');
  assert.match(FMSEC, /say\.textContent = first \|\| \(failed \? FM_FAILED : lastSay\)/);
  assert.match(FMSEC, /max="\$\{C\.FM_LATEST\}"/, 'the time boxes stop at 15:55');
});

test('form sheet: every value from the network reaches the page escaped', () => {
  const holes = [...FMSEC.matchAll(/\$\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}/g)].map((m) => m[1].trim());
  const raw = holes.filter((h) => /^[A-Za-z_$][\w$]*(\.[A-Za-z_$][\w$]*)+$/.test(h) && !/^C\.FM_/.test(h));
  assert.deepEqual(raw, [], 'a plain value in a template without esc()');
  assert.doesNotMatch(FMSEC, /insertAdjacentHTML\([^)]*(?:got|answers|r\.json)|outerHTML|document\.write/);
});

test('form sheet: a schema value goes into markup only through esc() or the [a-z0-9_] helper; every other hole is one of the page\'s own', () => {
  assert.match(FMSEC, /const id = C\.fmId;/);
  const holes = [...FMSEC.matchAll(/\$\{([^{}]*(?:\{[^{}]*\}[^{}]*)*)\}/g)].map((m) => m[1].trim());
  const own = new Set(["edit ? 'Edit strategy' : 'New strategy'", "edit ? 'Update' : 'Make it'", 'String(v) === String(cur) ? \' selected\' : \'\'', 'more', 'desc', 'kind',
    "opts.map(([v, t]) => opt(v, t, cur)).join('')", "edit ? ' readonly' : ''", 'C.FM_LATEST', "sel(f, C.fmKinds(sc, F.rule, f).map((x) => [x.id, x.label]), (F[f] || {}).kind, ' data-part=\"kind\"')",
    "C.fmHasValue(k) ? '' : ' hidden'", "def.type === 'int' ? 'numeric' : 'decimal'", 'control(f)', "['name', 'market', 'rule'].map(field).join('')", 'restHtml()']);
  const loose = holes.filter((h) => !/^(esc|id)\(/.test(h) && !own.has(h));
  assert.deepEqual(loose, [], 'a hole that is neither escaped, nor the id helper, nor one of the page\'s own pieces');
  assert.equal(holes.filter((h) => h === 'f' || h === 'v' || h === 'cur').length, 0, 'no bare schema value in a hole');
  assert.ok(holes.filter((h) => h === 'id(f)').length >= 14, 'every id, for and data- attribute is written through the helper');
  assert.doesNotMatch(FMSEC, /querySelector(All)?\(`[^`]*\$\{f\}/, 'nor in a selector');
});

test('form sheet (fix round 1): dimmed and busy while a newer build is pending; a failed or silent request says so and can be retried; a stale Update changes nothing', () => {
  assert.match(FMSEC, /const pending = !!\(timer \|\| flying\);/);
  assert.match(FMSEC, /say\.setAttribute\('aria-busy', 'true'\)/);
  assert.match(FMSEC, /say\.removeAttribute\('aria-busy'\)/);
  assert.match(FMSEC, /const FM_FAILED = 'The form could not be checked\. Try again\.';/);
  assert.match(FMSEC, /data-x="retry" hidden>Try again<\/button>/);
  assert.match(FMSEC, /ms = 10000/);
  assert.match(FMSEC, /finally \{ flying = false; \}/, 'a request is never still out');
  assert.match(FMSEC, /const FM_STALE = 'The code changed while the form was open\. Open the form again\.';/);
  assert.match(FMSEC, /if \(b\.code !== edit\.code\) \{ stale = true; paintState\(\); return; \}/);
  assert.match(FMSEC, /serverErr = C\.fmKeepErrors\(serverErr, served, C\.fmAnswers\(sc, F\)\)/);
  assert.match(CODEJS + LABJS, /data-act="new" data-fk="new-welcome">Start from a template/, 'the empty state\'s button gets the keyboard back too');
  assert.match(CSS, /p\.fm-say\[aria-busy="true"\] \{ color: var\(--pl-ink2\); \}/);
});

test('form sheet: Enter submits nothing and a held key presses nothing twice', () => {
  assert.doesNotMatch(FMSEC, /<form\b/);
  assert.match(FMSEC, /e\.repeat && \(e\.key === 'Enter' \|\| e\.key === ' '\)/);
  assert.match(FMSEC, /if \(e\.detail === 0\) swallowRepeats\(\)/);
});


test('fm: a schema value written into markup is cut down to [a-z0-9_]', () => {
  assert.equal(L.fmId('last_entry'), 'last_entry');
  assert.equal(L.fmId('range_min'), 'range_min');
  assert.equal(L.fmId('a"><img src=x onerror=alert(1)>'), 'aimgsrcxonerroralert1');
  assert.equal(L.fmId("x' onfocus='y"), 'xonfocusy');
  assert.equal(L.fmId(null), '');
  assert.equal(L.fmId(42), '42');
  for (const f of Object.keys(FM.fields)) assert.equal(L.fmId(f), f, `${f} is already that shape`);
  for (const r of FM.rules) assert.equal(L.fmId(r.id), r.id);
});

test('fm: a server error stays only under a box whose value is what was sent', () => {
  const asked = { name: 'a', distance: 15, stop: { kind: 'points', value: 50 }, out_by: '15:55' };
  const errs = { name: 'That name is taken.', stop: 'Every entry needs a stop.', out_by: 'It must be after the last entry, and 15:55 at the latest.', form: 'The form is incomplete.' };
  assert.deepEqual(L.fmKeepErrors(errs, asked, { ...asked }), errs, 'nothing changed: all stay');
  assert.deepEqual(L.fmKeepErrors(errs, asked, { ...asked, name: 'b' }), { stop: errs.stop, out_by: errs.out_by, form: errs.form });
  assert.deepEqual(L.fmKeepErrors(errs, asked, { ...asked, stop: { kind: 'points', value: 51 } }).stop, undefined, 'a nested value is compared whole');
  assert.deepEqual(L.fmKeepErrors(errs, asked, { ...asked, stop: { kind: 'points', value: 50 } }).stop, errs.stop);
  assert.deepEqual(L.fmKeepErrors(errs, asked, { name: 'a', distance: 15 }), { name: errs.name, form: errs.form }, 'a box that is gone from the form has no error to show');
  assert.deepEqual(L.fmKeepErrors({}, asked, asked), {});
  assert.deepEqual(L.fmKeepErrors(errs, null, asked), { form: errs.form }, 'no record of what was sent: only what is not a box stays');
});
