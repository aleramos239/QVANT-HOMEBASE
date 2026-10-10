/* Homebase Lab -- the editor's pure half: Python highlighting, the keystroke edits a code editor owes you
   (Tab, Shift+Tab, Enter, Cmd+/), a name for a pasted script, the one-line status of a validation, and the
   library's rows under their groups.
   No DOM, no fetch: tests/js/labcode.test.mjs runs it headless. lab.js (the page) uses it. */
(function () {
'use strict';

const KEYWORDS = new Set(['False', 'None', 'True', 'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue',
  'def', 'del', 'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is', 'lambda',
  'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'try', 'while', 'with', 'yield']);
const BUILTINS = new Set(['self', 'cls', 'ctx', 'Strategy', 'Input', 'abs', 'all', 'any', 'bool', 'dict', 'enumerate', 'float',
  'int', 'len', 'list', 'max', 'min', 'print', 'range', 'round', 'set', 'sorted', 'str', 'sum', 'tuple', 'zip']);
const TOKEN = new RegExp([
  '(#[^\\n]*)',                                                                       // 1 comment
  '((?:[rRbBfFuU]{1,2})?(?:"""[\\s\\S]*?(?:"""|$)|\'\'\'[\\s\\S]*?(?:\'\'\'|$)|"(?:\\\\.|[^"\\\\\\n])*(?:"|$)|\'(?:\\\\.|[^\'\\\\\\n])*(?:\'|$)))', // 2 string
  '(@[A-Za-z_][\\w.]*)',                                                              // 3 decorator
  '(\\b\\d[\\d_]*(?:\\.\\d+)?(?:[eE][+-]?\\d+)?\\b)',                                  // 4 number
  '([A-Za-z_]\\w*)',                                                                  // 5 name
].join('|'), 'g');

const esc = (t) => t.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

/* Python source -> HTML with <span class="c|s|d|n|k|f|b"> (comment, string, decorator, number, keyword, name being
   defined or called, builtin/self). Every character of the source comes back, escaped, in order: the textarea
   above the overlay and this text must stay the same length or the caret drifts. */
function highlight(src) {
  let out = '', last = 0, prevKw = '';
  const text = String(src == null ? '' : src);
  TOKEN.lastIndex = 0;
  let m;
  while ((m = TOKEN.exec(text))) {
    out += esc(text.slice(last, m.index));
    last = m.index + m[0].length;
    const [tok, com, str, dec, num, name] = m;
    let cls = '';
    if (com) cls = 'c';
    else if (str) cls = 's';
    else if (dec) cls = 'd';
    else if (num) cls = 'n';
    else if (name) {
      if (KEYWORDS.has(name)) cls = 'k';
      else if (prevKw === 'def' || prevKw === 'class') cls = 'f';
      else if (BUILTINS.has(name)) cls = 'b';
      else if (text[last] === '(') cls = 'f';
      prevKw = KEYWORDS.has(name) ? name : '';
    }
    if (!name) prevKw = '';
    out += cls ? `<span class="${cls}">${esc(tok)}</span>` : esc(tok);
  }
  return out + esc(text.slice(last));
}

/* ---- keystrokes. Each takes the value and the selection and returns {value, start, end}. ---- */
const INDENT = '    ';
function lineBounds(v, s, e) {
  const a = v.lastIndexOf('\n', s - 1) + 1;
  let b = v.indexOf('\n', e > s && v[e - 1] === '\n' ? e - 1 : e);
  if (b < 0) b = v.length;
  return [a, b];
}
function tab(v, s, e, shift) {
  const multi = v.slice(s, e).includes('\n');
  if (!multi && !shift) {                               // a plain Tab: to the next 4-column stop
    const col = s - (v.lastIndexOf('\n', s - 1) + 1), n = 4 - (col % 4);
    return { value: v.slice(0, s) + ' '.repeat(n) + v.slice(e), start: s + n, end: s + n };
  }
  const [a, b] = lineBounds(v, s, e);
  const lines = v.slice(a, b).split('\n');
  let first = 0, total = 0;
  const next = lines.map((ln, i) => {
    if (!shift) { if (i === 0) first = INDENT.length; total += INDENT.length; return INDENT + ln; }
    const k = Math.min(INDENT.length, ln.length - ln.trimStart().length);
    if (i === 0) first = -k;
    total -= k;
    return ln.slice(k);
  });
  const value = v.slice(0, a) + next.join('\n') + v.slice(b);
  return { value, start: Math.max(a, s + first), end: Math.max(a, e + total) };
}
function enter(v, s, e) {
  const a = v.lastIndexOf('\n', s - 1) + 1, before = v.slice(a, s);
  let pad = /^[ \t]*/.exec(before)[0];
  if (/:\s*(#.*)?$/.test(before.trimEnd() ? before : '') && before.trim()) pad += INDENT;
  const ins = '\n' + pad;
  return { value: v.slice(0, s) + ins + v.slice(e), start: s + ins.length, end: s + ins.length };
}
function comment(v, s, e) {
  const [a, b] = lineBounds(v, s, e);
  const lines = v.slice(a, b).split('\n');
  const live = lines.filter((l) => l.trim());
  const allOff = live.length > 0 && live.every((l) => l.trimStart().startsWith('#'));
  const pad = allOff ? 0 : Math.min(...(live.length ? live : ['']).map((l) => l.length - l.trimStart().length));
  let total = 0, first = 0;
  const next = lines.map((ln, i) => {
    if (!ln.trim()) return ln;
    let r;
    if (allOff) { const k = ln.length - ln.trimStart().length; r = ln.slice(0, k) + ln.slice(k).replace(/^# ?/, ''); }
    else r = ln.slice(0, pad) + '# ' + ln.slice(pad);
    if (i === 0) first = r.length - ln.length;
    total += r.length - ln.length;
    return r;
  });
  return { value: v.slice(0, a) + next.join('\n') + v.slice(b), start: Math.max(a, s + first), end: Math.max(a, e + total) };
}

/* ---- names ---- */
const NAME_RE = /^[a-z][a-z0-9_]{1,39}$/;
const RESERVED = new Set(['draft', 'drafts', 'base', 'strategy', 'strategies', 'test', 'tests', 'init', 'main', 'homebase',
  'sitecustomize', 'usercustomize', 'conftest', 'setup']);
/* The name checks a person can do before the server does (it still has the last word: built-in and module names). */
function nameError(name) {
  if (!NAME_RE.test(String(name || ''))) return 'Use 2–40 letters, digits or _, starting with a letter (nq_orb_15)';
  if (name.startsWith('draft_') || RESERVED.has(name)) return `“${name}” is reserved`;
  return null;
}
const snake = (t) => String(t).replace(/([a-z0-9])([A-Z])/g, '$1_$2').replace(/[^A-Za-z0-9]+/g, '_').replace(/^_+|_+$/g, '').toLowerCase();
/* A name for a script someone just pasted: its `name = "..."`, else its class name, else my_strategy. */
function suggestName(code, taken = []) {
  const text = String(code || '');
  const lit = /^\s{0,8}name\s*=\s*["']([^"'\n]+)["']/m.exec(text);
  const cls = /^class\s+(\w+)\s*\(\s*(?:\w+\.)?Strategy\s*\)/m.exec(text);
  let base = snake((lit && lit[1]) || (cls && cls[1]) || '') || 'my_strategy';
  if (!/^[a-z]/.test(base)) base = 'my_' + base;
  base = base.slice(0, 36);
  if (base.length < 2 || nameError(base)) base = 'my_strategy';
  let n = base, i = 2;
  while (taken.includes(n)) n = `${base.slice(0, 36)}_${i++}`;
  return n;
}

/* ---- the one line under the editor ---- */
function metaLine(meta) {
  if (!meta) return '';
  const n = (meta.inputs || []).length, w = meta.session_window;
  return [`${n} input${n === 1 ? '' : 's'}`, meta.root, w ? `session ${w[0]}–${w[1]} ET` : null,
    meta.bar_minutes ? `${meta.bar_minutes}-minute bars` : null].filter(Boolean).join(' · ');
}
function statusOf(v) {
  if (!v) return { tone: '', text: '' };
  if (v.ok) return { tone: 'ok', text: `Valid · ${metaLine(v.meta)}` };
  return { tone: 'err', text: v.line ? `Line ${v.line}: ${String(v.error).replace(/\s*\(line \d+\)\s*$/, '')}` : String(v.error || 'Could not be read') };
}
const lineCount = (t) => String(t || '').split('\n').length;
function ago(ms, now) {
  const s = Math.max(0, Math.round((now - ms) / 1000));
  return s < 5 ? 'just now' : s < 60 ? `${s} s ago` : s < 3600 ? `${Math.floor(s / 60)} min ago` : s < 86400 ? `${Math.floor(s / 3600)} h ago` : `${Math.floor(s / 86400)} d ago`;
}

/* ---- the library's groups ---- */
/* The list's rows under their groups: [{name, rows}] for each group in its saved order (an empty one too), then the
   rest under name '' (the list calls it Ungrouped). `groups` is the server's {groups: [names], members: {strategy
   id: group}}; a row with no id (a script not saved yet) cannot be in a group. */
function sections(rows, groups) {
  const out = groups.groups.map((name) => ({ name, rows: [] })), rest = { name: '', rows: [] };
  const by = new Map(out.map((s) => [s.name, s]));
  for (const r of rows) (by.get(groups.members[r.id]) || rest).rows.push(r);
  return [...out, rest];
}

/* ---- picking strategies in the list, and deleting them ----
   A shift-click picks the rows from the last picked (or the open) row to the clicked one, in the order the list shows
   them; a cmd/ctrl-click adds or removes one; a plain click opens the strategy and clears the picks. Only a saved
   strategy is ever picked: a locked built-in, an unsaved script and anything not shown (a folded group) never is.
   A saved strategy with changes not saved (`dirty` on its row) is picked by cmd-click or deleted alone, never by a range:
   the confirm tells of the ones that are picked. A locked or unsaved row is not where a range starts. */
/* the rows as shown, top to bottom: `secs` is sections()' answer; a folded group's rows are not shown */
const shownRows = (secs, folded) => secs.filter((s) => !folded.has(s.name)).flatMap((s) => s.rows);
const canPick = (r) => !!r && !r.lock && typeof r.key === 'string' && r.key.startsWith('d:');
/* the keys a range may take: a saved strategy whose edits are all saved */
const rangeable = (r) => canPick(r) && !r.dirty;
/* the pickable keys from `anchor` to `to` (either way round), in shown order. An anchor that is not shown picks `to` alone. */
function pickRange(shown, anchor, to) {
  const at = (k) => shown.findIndex((r) => r.key === k), j = at(to);
  if (j < 0) return [];
  const i = anchor ? at(anchor) : -1, lo = i < 0 ? j : Math.min(i, j), hi = i < 0 ? j : Math.max(i, j);
  return shown.slice(lo, hi + 1).filter(rangeable).map((r) => r.key);
}
const prunePicks = (picks, shown) => shown.filter((r) => canPick(r) && picks.includes(r.key)).map((r) => r.key);
/* a click on a row. st = {picks, anchor, cur}; mods = {shift, meta}. -> {picks, anchor, open}: `open` is true when the
   strategy is to be opened (a plain click only) */
function rowClick(st, shown, key, mods) {
  const m = mods || {}, row = shown.find((r) => r.key === key);
  if (m.shift) {
    const from = [st.anchor, st.cur].find((k) => k && shown.some((r) => r.key === k && canPick(r))) || '';
    return { picks: pickRange(shown, from, key), anchor: from || (canPick(row) ? key : ''), open: false };
  }
  if (m.meta) {
    if (!canPick(row)) return { picks: st.picks, anchor: st.anchor, open: false };
    const had = st.picks.includes(key);
    return { picks: prunePicks(had ? st.picks.filter((k) => k !== key) : [...st.picks, key], shown), anchor: key, open: false };
  }
  return { picks: [], anchor: key, open: true };
}
const draftName = (key) => String(key).slice(2);
/* the row menu's item: "Delete N strategies…" on a picked row while two or more are picked, else "Delete…" */
const deleteItem = (picks, key) => (picks.length >= 2 && picks.includes(key) ? `Delete ${picks.length} strategies…` : 'Delete…');
/* the names that item deletes */
const deleteTargets = (picks, key) => (picks.length >= 2 && picks.includes(key) ? picks : [key]).map(draftName);
const DELETE_SHOWN = 8;
/* the one line about the strategies that go with changes not saved: "2 of these have changes you have not saved (a, b): ...";
   the names only when there are at most 3. `dirty` = the names among those about to go. */
function unsavedLine(dirty) {
  const n = (dirty || []).length;
  if (!n) return '';
  return `${n} of these ${n === 1 ? 'has' : 'have'} changes you have not saved${n <= 3 ? ` (${dirty.join(', ')})` : ''}: they will be lost.`;
}
function deleteConfirm(names, dirty) {
  const unsaved = unsavedLine((dirty || []).filter((n) => names.includes(n)));
  if (names.length === 1) return { title: `Delete ${names[0]}?`, names: [], more: '', keep: 'Keep it', go: 'Delete', unsaved,
    body: 'Its file is removed from your strategies. Past backtests of it stay in Recent runs.' };
  return { title: `Delete ${names.length} strategies?`, names: names.slice(0, DELETE_SHOWN),
    more: names.length > DELETE_SHOWN ? `and ${names.length - DELETE_SHOWN} more` : '', keep: 'Keep them', go: 'Delete', unsaved,
    body: 'Their files are removed from your strategies. Past backtests of them stay in Recent runs.' };
}
function deleteConfirmHtml(names, dirty) {
  const c = deleteConfirm(names, dirty);
  return `<h2>${esc(c.title)}</h2>${c.names.length ? `<ul class="lb-dellist">${c.names.map((n) => `<li>${esc(n)}</li>`).join('')}${c.more ? `<li class="more">${esc(c.more)}</li>` : ''}</ul>` : ''}<p>${esc(c.body)}</p>${c.unsaved ? `<p class="lb-unsaved">${esc(c.unsaved)}</p>` : ''}
    <div class="acts"><button class="btn btn-outline" data-x="cancel">${esc(c.keep)}</button><button class="btn btn-default" data-x="go">${esc(c.go)}</button></div>`;
}
/* the names the server said were not there any more (not counted as deleted) */
const goneLine = (gone) => `Already gone: ${gone.join(', ')}.`;
/* the log line after a delete of several: how many went, the ones already gone, and each that did not with the server's own sentence */
function deleteLine(done, failed, gone) {
  return `Deleted ${done}.${gone && gone.length ? ` ${goneLine(gone)}` : ''}${failed.length ? ` Not deleted: ${failed.map((f) => `${f.name} (${f.error || 'it could not be deleted'})`).join(', ')}` : ''}`;
}
/* Delete / Backspace deletes the picked while the list has the keyboard: never held down, never while a sheet is open
   or something is being typed into */
function deleteKey(e, ctx) {
  return (e.key === 'Delete' || e.key === 'Backspace') && !e.repeat && !e.ctrlKey && !e.altKey
    && ctx.picked > 0 && !!ctx.inList && !ctx.typing && !ctx.dialog;
}
const isTyping = (el) => !!el && (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || el.isContentEditable === true);

/* ---- the blueprint toolkit: the tools every chat has, as the Lab lists them and fills them in ---- */
const BP_TITLES = { blueprint_blocks: 'Blocks', blueprint_card: 'Idea card', blueprint_code_check: 'Code check', blueprint_build: 'Build',
  blueprint_lock: 'Pick and lock', blueprint_test: 'Out-of-sample test', blueprint_sim: 'Simulator: one strategy',
  blueprint_portfolio: 'Simulator: portfolio', blueprint_eval_card: 'Eval card', blueprint_status: 'Status',
  blueprint_heatmap: 'Heat map', blueprint_mc: 'Monte Carlo' };
const bpTitle = (name) => BP_TITLES[name] || String(name).replace(/^blueprint_/, '').replace(/_/g, ' ');
/* "Blueprint phase 2, the build" -> "Phase 2"; "Blueprint, before the card" -> "Before the card" */
function bpPhase(head) {
  const m = /phase (\d)/.exec(String(head || ''));
  if (m) return `Phase ${m[1]}`;
  const rest = String(head || '').replace(/^Blueprint,?\s*/, '').replace(/:.*$/, '');
  return rest ? rest[0].toUpperCase() + rest.slice(1) : '';
}
/* An empty value of the shape a schema asks for: what a JSON field starts as. */
function bpStarter(prop) {
  const t = Array.isArray(prop.type) ? prop.type[0] : prop.type;
  if (t === 'object') return Object.fromEntries(Object.entries(prop.properties || {}).map(([k, v]) => [k, bpStarter(v)]));
  if (t === 'array') return [];
  if (t === 'integer' || t === 'number') return 0;
  if (t === 'boolean') return false;
  return '';
}
/* A tool's inputs as form fields, in the schema's own order: [{key, kind, required, help, options?, starter?}].
   kind: text | choice | int | number | bool | list (several names) | json (a card, settings, fills). */
function bpFields(schema) {
  const req = new Set((schema && schema.required) || []);
  return Object.entries((schema && schema.properties) || {}).map(([key, p]) => {
    const t = Array.isArray(p.type) ? p.type[0] : p.type, f = { key, required: req.has(key), help: p.description || '' };
    if (t === 'string') return p.enum ? { ...f, kind: 'choice', options: p.enum } : { ...f, kind: 'text' };
    if (t === 'integer') return { ...f, kind: 'int' };
    if (t === 'number') return { ...f, kind: 'number' };
    if (t === 'boolean') return { ...f, kind: 'bool' };
    if (t === 'array' && p.items && p.items.type === 'string') return { ...f, kind: 'list' };
    return { ...f, kind: 'json', starter: JSON.stringify(bpStarter(p), null, 1) };
  });
}
/* What the form holds -> the tool's arguments: {args} or {error, key}. An empty optional field is left out, so the
   tool's own default applies; a required one that is empty is named. values: {key: string | boolean}. */
function bpArgs(fields, values) {
  const args = {};
  for (const f of fields) {
    const v = values[f.key], miss = () => ({ error: `${f.key} is needed`, key: f.key });
    if (f.kind === 'bool') { if (v || f.required) args[f.key] = !!v; continue; }
    const t = String(v == null ? '' : v).trim();
    if (!t) { if (f.required) return miss(); continue; }
    if (f.kind === 'int' || f.kind === 'number') {
      const n = Number(t);
      if (!Number.isFinite(n) || (f.kind === 'int' && !Number.isInteger(n))) return { error: `${f.key}: a ${f.kind === 'int' ? 'whole ' : ''}number`, key: f.key };
      args[f.key] = n;
    } else if (f.kind === 'list') {
      const xs = t.split(/[\s,]+/).filter(Boolean);
      if (!xs.length) { if (f.required) return miss(); continue; }
      args[f.key] = xs;
    } else if (f.kind === 'json') {
      try { args[f.key] = JSON.parse(t); } catch (e) { return { error: `${f.key} does not read as JSON (${e.message})`, key: f.key }; }
    } else args[f.key] = t;
  }
  return { args };
}
/* The job a tool's answer says is still going ("... job_id='b3f1' ..."), or '' */
const bpJob = (text) => { const m = /is still going[\s\S]*?job_id=['"]?([A-Za-z0-9_.-]+)/.exec(String(text || '')); return m ? m[1] : ''; };
/* An idea's one line under its name: "LEAD · phase 2 · round 1" */
function bpIdeaLine(i) {
  return [String(i.status || 'idea').replace(/_/g, ' ').toUpperCase(), i.phase == null ? null : `phase ${i.phase}`, i.round ? `round ${i.round}` : null].filter(Boolean).join(' · ');
}

/* ---- the arsenal: every tool we have, with the code that implements it (blocks, chat tools, skills, scripts) ----
   The server (homebase/arsenal.py) sends {groups: [{id, title, words, items}], sources: {id: {file, start, end, code}}}; an item is
   {id, name, sub, words, sides?: [{side, words}], markets, runs, why_not, parts: [{label, src}]}. */
const tkText = (it) => [it.name, it.sub, it.words, ...(it.sides || []).map((x) => `${x.side} ${x.words}`), ...(it.markets || [])].join(' ').toLowerCase();
/* The groups that have a block matching every word of the search; with no search, all of them. */
function tkFilter(groups, q) {
  const words = String(q || '').toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return groups;
  return groups.map((g) => ({ ...g, items: g.items.filter((it) => { const t = tkText(it); return words.every((w) => t.includes(w)); }) })).filter((g) => g.items.length);
}
const tkFind = (groups, id) => { for (const g of groups || []) { const it = g.items.find((x) => x.id === id); if (it) return it; } return null; };
/* "runs" or "not yet: why"; null for a tool that is not a thing that runs on the build days (a skill, a script, a chat tool) */
const tkStatus = (it) => (it.runs == null ? null : it.runs ? { tone: 'ok', text: 'runs' } : { tone: 'no', text: it.why_not ? `not yet: ${it.why_not}` : 'not yet' });
/* The markets a block is for; '' when it is for none in particular (a limit, a session). */
const tkMarkets = (it) => (it.markets || []).join(' ');
/* "engine/zones.py:190–198" (the repository's research folder left out) */
const tkSpan = (s) => `${String(s.file).replace(/^research\/edge-library\//, '')}:${s.start}${s.end > s.start ? `–${s.end}` : ''}`;
/* A source cut out of the middle of a file starts deep in its indentation: take off what every line shares. */
function tkDedent(code) {
  const lines = String(code || '').split('\n'), live = lines.filter((l) => l.trim());
  const k = live.length ? Math.min(...live.map((l) => /^[ \t]*/.exec(l)[0].length)) : 0;
  return k ? lines.map((l) => l.slice(Math.min(k, /^[ \t]*/.exec(l)[0].length))).join('\n') : lines.join('\n');
}
/* An item's code, part by part, in the order the server gave them; a part whose source did not come is left out. */
function tkParts(it, sources) {
  return (it.parts || []).filter((p) => sources && sources[p.src]).map((p, i) => {
    const s = sources[p.src];
    return { n: i + 1, label: p.label, span: tkSpan(s), file: s.file, start: s.start, end: s.end, lines: s.end - s.start + 1, plain: !!s.plain, note: s.note || '', code: s.plain ? s.code : tkDedent(s.code) };
  });
}
/* The line numbers beside a source, one a line: start .. end. */
const tkGutter = (start, end) => Array.from({ length: Math.max(0, end - start + 1) }, (_, i) => start + i).join('\n');
/* One line for the list under a block's name: its plain words, cut at a word. */
function tkClip(text, n = 150) {
  const t = String(text || '').replace(/^only when /, '').replace(/\s+/g, ' ').trim();
  if (t.length <= n) return t;
  const cut = t.slice(0, n), sp = cut.lastIndexOf(' ');
  return `${cut.slice(0, sp > n * 0.6 ? sp : n)}…`;
}

/* ---- the strategy pipeline: the Lab's Queue, Book and Guide ----
   The server (GET /api/tester/pipeline) sends {runner: {running, paused}, counts: {label: n}, ideas: [an idea's state: name, family, label,
   stage (the last one it finished), stopped_at, why], book: [book cards], stages: [{n, name, words}]}. Nothing here judges anything: a
   verdict, a reason and a number are the server's. These only choose the words, the marks and what a button may do. */
const PL_LAST = 7;                                  // the last stage (the owner's look)
const PL_MARKETS = ['NQ', 'ES', 'GC'];
const PL_SESSIONS = [['asia', 'Asia'], ['london', 'London'], ['pre', 'Pre-market'], ['nyam', 'New York morning'], ['mid', 'Midday'], ['pm', 'Afternoon']];
const PL_SIDES = [['both', 'Both'], ['long', 'Long only'], ['short', 'Short only']];
const PL_NAME = /^[a-z][a-z0-9_]{1,33}$/;           // a card's name, as the toolkit takes it
const PL_WAYS = 3, PL_INDS = 5, PL_WORDS = 8;       // the card's limits (the server checks them again: these only save a round trip)
const PL_COUNT = { Problem: 'with a problem' };     // a label inside the count sentence, when its lower case does not read
const PL_TONE = { Running: 'run', Stopped: 'err', Problem: 'warn', Passed: 'ok', 'In the book': 'ok' };
const DASH = '—';
const plInt = (v) => (Number.isInteger(v) ? v : null);
const plNum = (v) => (typeof v === 'number' && Number.isFinite(v) ? v : null);
const plOf = (pairs, id) => { const hit = pairs.find(([k]) => k === id); return hit ? hit[1] : id == null || id === '' ? DASH : String(id); };
const plSession = (id) => plOf(PL_SESSIONS, id);
const plSide = (id) => plOf(PL_SIDES, id);
/* The colour a status chip takes ('' = plain). The chip always carries its word: the colour is never the only sign. */
const plTone = (label) => PL_TONE[label] || '';
/* "12 ideas: 3 waiting, 1 running, 8 stopped" -- only what is there, in the server's order. */
function plCount(counts) {
  const parts = Object.entries(counts || {}).filter(([, n]) => n > 0), total = parts.reduce((a, [, n]) => a + n, 0);
  if (!total) return 'No ideas yet';
  return `${total} idea${total === 1 ? '' : 's'}: ${parts.map(([k, n]) => `${n} ${PL_COUNT[k] || String(k).toLowerCase()}`).join(', ')}`;
}
/* The ideas the runner still has work on. */
const plLive = (P) => { const c = (P && P.counts) || {}; return (c.Waiting || 0) + (c.Running || 0); };
/* The Queue's ONE button: what it says is what it does. -> {label, actions: what is posted, in order, enabled, line: which it is}.
   Resume with no runner working also starts one, or "Resume" would resume nothing. */
function plControl(P) {
  const r = (P && P.runner) || {}, live = plLive(P);
  if (r.paused) return { label: 'Resume', actions: !r.running && live ? ['resume', 'start'] : ['resume'], enabled: true, line: r.running ? 'Paused. It stops after the stage it is on.' : 'Paused. Nothing is being tested.' };
  if (r.running) return { label: 'Pause', actions: ['pause'], enabled: true, line: live ? 'Testing is on.' : 'Testing is on. Nothing is waiting.' };
  return { label: 'Start testing', actions: ['start'], enabled: live > 0, line: live ? 'Testing is off.' : 'Nothing to test. Add an idea first.' };
}
/* The eight dots of an idea, stage 0 to 7: 'done' (finished), 'stop' (the one that stopped it), 'now' (being tested), '' (not reached)
   -- and the same in words, for someone who cannot see them. */
function plDots(row) {
  const r = row || {}, stage = plInt(r.stage), stop = plInt(r.stopped_at), on = r.label === 'Running', next = stage == null ? 0 : stage + 1;
  const dots = Array.from({ length: PL_LAST + 1 }, (_, i) => (stop != null ? (i < stop ? 'done' : i === stop ? 'stop' : '') : stage != null && i <= stage ? 'done' : on && i === next ? 'now' : ''));
  const label = stop != null ? `Reached stage ${stop} of ${PL_LAST}, stopped at stage ${stop}`
    : stage != null && stage >= PL_LAST ? `Passed every stage, 0 to ${PL_LAST}`
      : on ? (stage == null ? `Testing stage 0 of ${PL_LAST}` : `Reached stage ${stage} of ${PL_LAST}, testing stage ${Math.min(PL_LAST, next)}`)
        : stage == null ? 'No stage run yet' : `Reached stage ${stage} of ${PL_LAST}`;
  return { dots, label };
}
/* What is being tested now, in one line. An idea is only being tested while the runner works. */
function plRunning(P) {
  const it = P && P.runner && P.runner.running ? (P.ideas || []).find((x) => x.label === 'Running') : null;
  if (!it) return 'Nothing is running';
  const stage = plInt(it.stage);
  return `Testing ${it.name} ${DASH} stage ${Math.min(PL_LAST, stage == null ? 0 : stage + 1)} of ${PL_LAST}`;
}
/* The Guide's six steps (the design's section 6). Each: {n, title, words, button: its label or null, enabled, reason: why it is grey,
   primary: the one to press next, status: step 3's line, actions: step 2's, name: step 5's idea}. */
function plGuide(P) {
  const ideas = (P && P.ideas) || [], r = (P && P.runner) || {}, live = plLive(P), c = plControl(P), green = ideas.find((x) => x.label === 'Passed');
  const start = !live ? { enabled: false, reason: 'Add an idea first.' } : r.paused ? { enabled: true, reason: '' } : r.running ? { enabled: false, reason: 'Testing is already on.' } : { enabled: true, reason: '' };
  const steps = [
    { n: 1, title: 'Write the idea', words: 'Fill the card, or tell Claude the idea and it fills the card.', button: 'Write an idea', enabled: true, reason: '' },
    { n: 2, title: 'Press Start', words: 'The computer starts testing your ideas.', button: r.paused && live ? 'Resume' : 'Start testing', ...start, actions: start.enabled ? c.actions : [] },
    { n: 3, title: 'Wait', words: 'The computer tests it. This can take a night.', button: null, enabled: false, reason: '', status: plRunning(P) },
    { n: 4, title: 'Read the Queue', words: 'Red = stopped, and it says why in one line. Green = it passed everything.', button: 'Open the Queue', enabled: ideas.length > 0, reason: ideas.length ? '' : 'No ideas yet.' },
    { n: 5, title: 'Look at a green one', words: 'Read its card. Press Approve to put it in the Book, or Refuse.', button: green ? `Look at ${green.name}` : 'Look at a green one', enabled: !!green, reason: green ? '' : 'No idea has passed everything yet.', name: green ? green.name : '' },
    { n: 6, title: 'Build a portfolio', words: 'Mix strategies from the Book. This comes later.', button: 'Build a portfolio', enabled: false, reason: 'Not built yet' },
  ];
  const next = green ? 5 : steps[1].enabled ? 2 : !ideas.length ? 1 : 4;
  return steps.map((s) => ({ ...s, primary: s.n === next }));
}
/* Beside the Guide: what is happening now, in three lines at most (the count, what is being tested, who waits for the owner). */
function plSummary(P) {
  const n = ((P && P.counts) || {}).Passed || 0;
  return [plCount(P && P.counts), plRunning(P), n ? `${n} idea${n === 1 ? '' : 's'} passed and wait${n === 1 ? 's' : ''} for your look.` : ''].filter(Boolean);
}
/* The one that is selected in a list: the one that was, while it is still there; else the first (the server lists what can run first). */
const plPick = (names, cur) => (names.includes(cur) ? cur : names.length ? names[0] : '');
/* The stage an idea is AT now: where it stopped; else, while it waits or runs, the next one; a finisher sits at the owner's look.
   An idea that is in the book or was refused is at none (null). */
function plAt(row) {
  const stage = plInt(row.stage), stop = plInt(row.stopped_at);
  if (row.label === 'In the book' || row.label === 'Refused') return null;
  if (stop != null) return stop;
  if (row.label === 'Waiting' || row.label === 'Running') return Math.min(PL_LAST, stage == null ? 0 : stage + 1);
  return stage == null ? 0 : Math.min(PL_LAST, stage);
}
/* The ladder under the Guide: the server's stages, each with how many ideas are at it now. */
function plLadder(P) {
  const at = ((P && P.ideas) || []).map(plAt);
  return ((P && P.stages) || []).map((s) => { const n = at.filter((a) => a === s.n).length; return { n: s.n, name: s.name, words: s.words, ideas: n, count: n ? `${n} idea${n === 1 ? '' : 's'}` : 'None' }; });
}
/* PASS / FAIL / — for a stage or one of its lines, as the server judged it. */
const plMark = (passed) => (passed === true ? { text: 'PASS', tone: 'ok' } : passed === false ? { text: 'FAIL', tone: 'err' } : { text: DASH, tone: '' });
/* A way and an indicator of a card, in words. */
function plWayLine(w) {
  const fixed = Object.entries((w && w.fixed) || {}).map(([k, v]) => `${k} ${v}`).join(', ');
  return `${w.family}: ${w.main_setting} ${(w.values || []).join(' / ')}${fixed ? ` (${fixed})` : ''}`;
}
const plIndLine = (x) => `${x.block} ${x.side}: ${x.why}`;

/* -- the add-idea form -- */
const plT = (v) => String(v == null ? '' : v).replace(/\s+/g, ' ').trim();
const plWay = () => ({ family: '', main_setting: '', values: ['', '', ''] });
const plInd = () => ({ block: '', side: '', why: '' });
/* An empty form. Market and time of day start unchosen: a guess there would cost a night of testing. */
const plForm = () => ({ name: '', why: '', loser: '', market: '', session: '', sides: 'both', sides_why: '', ways: [plWay()], indicators: [] });
const plWayEmpty = (w) => !plT(w.family) && !plT(w.main_setting) && !(w.values || []).some(plT);
const plIndEmpty = (x) => !plT(x.block) && !plT(x.why);          // a side alone is the list's first choice, not an indicator
/* The form's values -> the card that is posted: trimmed, every value as text (the server types it), an empty way or indicator left
   out, the owner as its source. */
function plCard(F) {
  const card = { name: plT(F.name), why: plT(F.why), loser: plT(F.loser), source: 'owner', market: plT(F.market), session: plT(F.session), sides: plT(F.sides) || 'both' };
  if (card.sides !== 'both') card.sides_why = plT(F.sides_why);
  card.ways = (F.ways || []).filter((w) => !plWayEmpty(w)).map((w) => ({ family: plT(w.family), main_setting: plT(w.main_setting), values: (w.values || []).map(plT) }));
  const inds = (F.indicators || []).filter((x) => !plIndEmpty(x)).map((x) => ({ block: plT(x.block), side: plT(x.side), why: plT(x.why) }));
  if (inds.length) card.indicators = inds;
  return card;
}
/* -- the form's lists: the server's `rules` ({name, words, markets, sessions, bars, settings: [{name, kind, min, max, choices, default,
   tried}]}) and `indicators` ({block, sides: [{side, words}], markets}), read off the toolkit's own block list -- */
const PL_BARS = ['1', '5'];                         // a card is always run on 1-minute and on 5-minute bars
const plHas = (v) => plNum(v) != null;
/* Can a setting be a card's MAIN setting? It must be able to take three different values: a switch and a choice of two cannot. */
const plUsable = (s) => !!s && (s.kind === 'choice' ? (s.choices || []).length >= 3
  : s.kind === 'whole' ? !plHas(s.min) || !plHas(s.max) || s.max - s.min >= 2
    : s.kind === 'number' ? !plHas(s.min) || !plHas(s.max) || s.max > s.min : s.kind === 'text');
/* The entry rules the form offers: those that run on the chosen market (any, while none is chosen) and on 1- or 5-minute bars, each
   with the settings that can be a main setting. hidden: how many more would fit but have no such setting. */
function plRules(all, market) {
  const fit = (all || []).filter((r) => r && (!market || !(r.markets || []).length || r.markets.includes(market))
    && (!(r.bars || []).length || r.bars.some((x) => PL_BARS.includes(String(x)))));
  const rules = fit.map((r) => ({ ...r, settings: (r.settings || []).filter(plUsable) })).filter((r) => r.settings.length);
  return { rules, hidden: fit.length - rules.length };
}
/* The setting a rule's way starts on: its only one; of several, the first the library ran three values of; else none (the person picks). */
function plMainSetting(rule) {
  const xs = (rule && rule.settings) || [], ran = xs.find((s) => new Set((s.tried || []).map(String)).size >= 3);
  return xs.length === 1 ? xs[0].name : ran ? ran.name : '';
}
const plIndicators = (all, market) => (all || []).filter((x) => x && (x.sides || []).length && (!market || !(x.markets || []).length || x.markets.includes(market)));
/* The times of day the form offers: the pipeline's six, less those a chosen rule does not run in. */
const plSessionsFor = (rules) => PL_SESSIONS.filter(([k]) => (rules || []).every((r) => !r || !(r.sessions || []).length || r.sessions.includes(k)));
const plRange = (s) => (plHas(s.min) && plHas(s.max) ? ` from ${s.min} to ${s.max}` : '');
/* What a value of this setting must be, in words ("a number from 0 to 10"). */
const plNeed = (s) => (s.kind === 'number' ? `a number${plRange(s)}` : s.kind === 'whole' ? `a whole number${plRange(s)}` : s.kind === 'choice' ? `one of: ${s.choices.join(', ')}` : 'a value');
/* Is this text a value the setting takes? -> '' (yes, or nothing typed yet), else what it must be. */
function plValueError(s, text) {
  const t = plT(text);
  if (!t || !s) return '';
  if (s.kind === 'choice') return s.choices.map(String).includes(t) ? '' : plNeed(s);
  if (s.kind !== 'number' && s.kind !== 'whole') return '';
  const v = /^-?\d+(\.\d+)?$/.test(t) ? Number(t) : NaN;
  return Number.isFinite(v) && (s.kind !== 'whole' || Number.isInteger(v)) && (!plHas(s.min) || v >= s.min) && (!plHas(s.max) || v <= s.max) ? '' : plNeed(s);
}
/* The line under a chosen setting: what it takes, and what the library ran. */
function plSettingWords(s) {
  const ran = [...new Set((s.tried || []).map(String))];
  return `${plNeed(s).replace(/^./, (c) => c.toUpperCase())}.${ran.length ? ` The library ran ${ran.join(', ')}.` : ''}`;
}
/* Three values to start from, as text: three the library ran (those around the default) when it ran three; else the default and
   its neighbours inside the setting's limits; for a choice, three of its choices. ['', '', ''] when nothing can be said. */
function plPrefill(s) {
  const around = (xs, d) => { const i = Math.max(0, xs.indexOf(String(d))), a = Math.max(0, Math.min(xs.length - 3, i - 1)); return xs.slice(a, a + 3); };
  const num = s.kind === 'number' || s.kind === 'whole';
  let ran = [...new Set((s.tried || []).map(String))].filter((v) => !plValueError(s, v));
  if (num) ran = ran.sort((x, y) => Number(x) - Number(y));
  if (ran.length >= 3) return around(ran, s.default);
  if (s.kind === 'choice') return s.choices.length >= 3 ? around(s.choices.map(String), s.default) : ['', '', ''];
  if (!num) return ['', '', ''];
  const lo = plHas(s.min) ? s.min : -Infinity, hi = plHas(s.max) ? s.max : Infinity, whole = s.kind === 'whole';
  const d = Math.min(hi, Math.max(lo, plHas(Number(s.default)) && s.default !== null && s.default !== '' ? Number(s.default) : plHas(s.min) ? s.min : 0));
  const step = whole ? Math.max(1, Math.round(Math.abs(d) / 2)) : d ? Math.abs(d) / 2 : Number.isFinite(hi - lo) ? (hi - lo) / 10 : 1;
  const tidy = (v) => String(whole ? Math.round(v) : Number(v.toPrecision(6)));
  let xs = d - step < lo ? [d, d + step, d + 2 * step] : d + step > hi ? [d - 2 * step, d - step, d] : [d - step, d, d + step];
  if (xs[0] < lo || xs[2] > hi) xs = [lo, (lo + hi) / 2, hi];             // limits too close together for the step: the two ends and the middle
  xs = xs.map(tidy);
  return new Set(xs).size === 3 && xs.every((v) => !plValueError(s, v)) ? xs : ['', '', ''];
}

/* May the form be sent? -> {ok, needs: what is still missing, in plain words}. With the server's lists (`rules`, `indicators`) a way
   must also be a rule the form offers, its main setting one of that rule's, each value one the setting takes, and the time of day one
   the rule runs in. The server checks the card in full; this only keeps a card that cannot pass from being sent. */
function plCanSend(F, rules, indicators) {
  const c = plCard(F), needs = [], offered = (rules || []).length ? plRules(rules, c.market).rules : null;
  if (!c.name) needs.push('a name');
  else if (!PL_NAME.test(c.name)) needs.push('a name of small letters, numbers and _ (2 to 34, a letter first)');
  if (!c.why) needs.push('why it should make money');
  if (!c.loser) needs.push('who loses');
  if (c.why && c.loser && `${c.why} ${c.loser}`.split(' ').length < PL_WORDS) needs.push(`${PL_WORDS} words or more in those two sentences together`);
  if (!PL_MARKETS.includes(c.market)) needs.push('a market');
  if (!PL_SESSIONS.some(([k]) => k === c.session)) needs.push('a time of day');
  if (!PL_SIDES.some(([k]) => k === c.sides)) needs.push('the sides');
  else if (c.sides !== 'both' && !c.sides_why) needs.push('why one side only');
  if (!c.ways.length) needs.push('an entry rule');
  if (c.ways.length > PL_WAYS) needs.push(`${PL_WAYS} ways at most`);
  (F.ways || []).forEach((w, i) => {
    if (plWayEmpty(w)) return;
    const n = `way ${i + 1}`, values = (w.values || []).map(plT), vs = values.filter(Boolean), family = plT(w.family);
    const rule = offered && family ? offered.find((r) => r.name === family) : null, setting = rule ? rule.settings.find((x) => x.name === plT(w.main_setting)) : null;
    if (!family || (offered && !rule)) needs.push(`${n}: an entry rule`);
    if (!plT(w.main_setting) || (rule && !setting)) needs.push(`${n}: its main setting`);
    if (vs.length < 3) needs.push(`${n}: three values`);
    else if (new Set(vs).size < 3) needs.push(`${n}: three different values`);
    if (setting) values.forEach((v, k) => { const bad = plValueError(setting, v); if (bad) needs.push(`${n}: value ${k + 1} must be ${bad}`); });
    if (rule && c.session && (rule.sessions || []).length && !rule.sessions.includes(c.session)) needs.push(`a time of day ${family} runs in`);
  });
  const inds = c.indicators || [], blocks = (indicators || []).length ? plIndicators(indicators, c.market) : null;
  if (inds.length > PL_INDS) needs.push(`${PL_INDS} indicators at most`);
  (F.indicators || []).forEach((x, i) => {
    if (plIndEmpty(x)) return;
    const n = `indicator ${i + 1}`, block = blocks && plT(x.block) ? blocks.find((k) => k.block === plT(x.block)) : null;
    if (!plT(x.block) || (blocks && !block)) needs.push(`${n}: which one`);
    if (!plT(x.side) || (block && !block.sides.some((k) => k.side === plT(x.side)))) needs.push(`${n}: its side`);
    if (!plT(x.why)) needs.push(`${n}: why it should help`);
  });
  if (new Set(inds.map((x) => x.block).filter(Boolean)).size < inds.filter((x) => x.block).length) needs.push('each indicator once');
  return { ok: !needs.length, needs };
}

/* -- the book -- */
const plPct = (v) => (plNum(v) == null ? DASH : `${Math.round(v * 100)} %`);                 // a share 0 .. 1 -> "58 %"
const plMoney = (v) => (plNum(v) == null ? DASH : `${v < 0 ? '−' : ''}$${Math.abs(Math.round(v)).toLocaleString('en-US')}`);
const plText = (v) => (v == null || v === '' ? DASH : String(v));
const plCap = (v) => { const t = plText(v); return t.charAt(0).toUpperCase() + t.slice(1); };
const plFixed = (v, d) => (plNum(v) == null ? DASH : v.toFixed(d));
const plWhole = (v) => (plNum(v) == null ? DASH : Math.round(v).toLocaleString('en-US'));
const plPair = (v, join) => (Array.isArray(v) && v.length === 2 && v.every((x) => x != null && x !== '') ? `${v[0]} ${join} ${v[1]}` : DASH);
const plBar = (v) => (v == null || v === '' ? DASH : `${v}-minute bars`);
const plMicros = (v) => (plNum(v) == null ? '' : ` at ${v} micro${v === 1 ? '' : 's'}`);
/* The accounts of a book card, the pipeline's own first (the order the card keeps them in). */
const plAccounts = (card) => Object.values((card && card.prop && typeof card.prop === 'object' && card.prop) || {}).filter((p) => p && typeof p === 'object');
const plAccountName = (p) => `${plText(p.name)}${p.confirmed === false ? ' (rules not confirmed)' : ''}`;
/* A book card as the Book lists it: {name, label, tone, sub, account, rows: [[what, value]]}. A value that is missing shows "—". */
function plBookCard(card) {
  const c = card || {}, own = plAccounts(c)[0] || {};
  return { name: plText(c.name), label: plCap(c.label), tone: c.label === 'stands alone' ? 'ok' : '',
    sub: [plText(c.market), plSession(c.session), plBar(c.bar)].join(' · '), account: own.name ? plAccountName(own) : '',
    rows: [['Pass the eval in 30 days', plPct(own.eval)], ['Full payout in 30 days', plPct(own.payout)], ['Hours it trades', plPair(c.hours, '–')],
      ['Winning months', plPair(c.winning_months, 'of')], ['Biggest day, share of profit', plPct(c.biggest_day_share)],
      ['Trades under 5 seconds, share of profit', plPct(c.fast_profit_share)]] };
}
/* The whole book card, for its sheet: {why, facts: [[what, value]], accounts: [{name, rows}], stages: [{n, name, mark, text}]}.
   stages: the server's (their names). Every money fact is at one contract, after costs. */
function plBookFull(card, stages) {
  const c = card || {}, names = Object.fromEntries((stages || []).map((s) => [String(s.n), s.name]));
  return { why: plText(c.why),
    facts: [['Entry rule', plText(c.family)], ['Indicator', c.filter ? String(c.filter) : 'None'], ['Market', plText(c.market)], ['Time of day', plSession(c.session)],
      ['Bars', plBar(c.bar)], ['Stop and target', plText(c.rule && c.rule.default)], ['Hours it trades', plPair(c.hours, '–')], ['Trades', plWhole(c.trades)],
      ['Days it traded', plWhole(c.days_traded)], ['Winning days a month', plFixed(c.win_days_month, 1)], ['Winning months', plPair(c.winning_months, 'of')],
      ['Average trade', plMoney(c.avg_trade)], ['Profit factor', plFixed(c.profit_factor, 2)], ['Net profit', plMoney(c.net)], ['Worst day', plMoney(c.worst_day)],
      ['Worst drawdown', plMoney(c.worst_drawdown)], ['Biggest day, share of profit', plPct(c.biggest_day_share)],
      ['Trades under 5 seconds, share of profit', plPct(c.fast_profit_share)], ['Heat maps tried', plWhole(c.tries)], ['Came from', plText(c.source)]],
    accounts: plAccounts(c).map((p) => ({ name: plAccountName(p), rows: [['Pass the eval in 30 days', `${plPct(p.eval)}${plNum(p.eval) == null ? '' : plMicros(p.size)}`],
      ['Full payout in 30 days', `${plPct(p.payout)}${plNum(p.payout) == null ? '' : plMicros(p.payout_size)}`], ['Label', plCap(p.label)]] })),
    stages: Object.entries((c.stages && typeof c.stages === 'object' && c.stages) || {}).sort((a, b) => Number(a[0]) - Number(b[0]))
      .map(([n, s]) => ({ n: Number(n), name: names[n] || '', mark: plMark(s && s.passed), text: String((s && s.text) || '') })) };
}

/* -- what a Book strategy did: its row's one line, its numbers as tiles, its equity curve (2026-10-09) -- */
const plSigned = (v) => (plNum(v) == null ? DASH : `${v > 0 ? '+' : v < 0 ? '−' : ''}$${Math.abs(Math.round(v)).toLocaleString('en-US')}`);
const plTone$ = (v) => (plNum(v) == null || v === 0 ? '' : v > 0 ? 'pos' : 'neg');
/* The line under a Book row's name: its net, then trades and profit factor. One contract, after costs, on the unseen days. */
function plBookLine(card) {
  const c = card || {}, rest = [];
  if (plNum(c.trades) != null) rest.push(`${plWhole(c.trades)} trade${c.trades === 1 ? '' : 's'}`);
  if (plNum(c.profit_factor) != null) rest.push(`PF ${c.profit_factor.toFixed(2)}`);
  return { net: plSigned(c.net), tone: plTone$(c.net), rest: rest.join(' · ') };
}
/* A curve's numbers as tiles, in the order a person asks: [{k, v, tone}]. `cv` = GET /pipeline/curve/<name> (or a watch snapshot). */
function plCurveTiles(cv) {
  const c = cv || {};
  return [{ k: 'Net profit', v: plSigned(c.net), tone: plTone$(c.net) }, { k: 'Trades', v: plWhole(c.trades), tone: '' },
    { k: 'Win rate', v: plPct(c.win_rate), tone: '' }, { k: 'Average trade', v: plSigned(c.avg_trade), tone: plTone$(c.avg_trade) },
    { k: 'Profit factor', v: plFixed(c.profit_factor, 2), tone: '' }, { k: 'Worst day', v: plMoney(c.worst_day), tone: '' },
    { k: 'Deepest drawdown', v: plNum(c.max_drawdown) == null ? DASH : plMoney(-Math.abs(c.max_drawdown)), tone: '' },
    { k: 'Days traded', v: plWhole(c.days), tone: '' }];
}
/* The equity curve as SVG geometry in a w x h box with `pad` inside it: the running total, one point a traded day, starting from 0
   the day before the first. -> {line, area, zero (y of $0), dot [x, y], min, max, last, up} or null with fewer than 2 days.
   x is spread by POSITION (a traded day each step), so a quiet month does not flatten the line. */
function plCurvePath(curve, w, h, pad = 6) {
  const pts = (Array.isArray(curve) ? curve : []).filter((p) => Array.isArray(p) && plNum(p[2]) != null);
  if (pts.length < 2) return null;
  const ys = [0, ...pts.map((p) => p[2])], min = Math.min(...ys), max = Math.max(...ys), span = max - min || 1;
  const X = (i) => pad + (i / (ys.length - 1)) * (w - 2 * pad), Y = (v) => pad + (1 - (v - min) / span) * (h - 2 * pad);
  const r = (n) => Math.round(n * 10) / 10;
  const xy = ys.map((v, i) => [r(X(i)), r(Y(v))]);
  const line = xy.map(([x, y], i) => `${i ? 'L' : 'M'}${x} ${y}`).join(' '), zero = r(Y(0));
  return { line, area: `${line} L${xy[xy.length - 1][0]} ${zero} L${xy[0][0]} ${zero} Z`, zero, dot: xy[xy.length - 1], min, max,
    last: ys[ys.length - 1], up: ys[ys.length - 1] >= 0 };
}
/* The day under a pointer at x (0 .. w) on that curve: its index into `curve`, or -1 left of the first day (the $0 start). */
function plCurveAt(curve, x, w, pad = 6) {
  const n = (Array.isArray(curve) ? curve : []).length;
  if (n < 2) return -1;
  const i = Math.round(((x - pad) / (w - 2 * pad)) * n);
  return Math.max(0, Math.min(n, i)) - 1;
}

/* The words beside the curve for the day under the pointer (i = plCurveAt: -1 is the $0 start; null = no pointer: the last value). Plain text. */
function plCurveRead(cv, i) {
  const c = cv || {}, pts = Array.isArray(c.curve) ? c.curve : [];
  if (i == null) return `${plText(c.end)} · ${plSigned(c.net)}`;
  if (i < 0 || !pts[i]) return `before ${plText(c.start)} · $0`;
  return `${pts[i][0]} · ${plSigned(pts[i][2])} (${plSigned(pts[i][1])} that day)`;
}
/* One plain sentence after Show executions on chart: `j` = the server's answer {trades, of, start, end}; `shown` = this page's chart took the run. */
function plExecSaid(name, j, shown) {
  const r = j || {}, n = plNum(r.trades) || 0, lost = plNum(r.of) != null && r.of > n ? r.of - n : 0;
  return `${n} execution${n === 1 ? '' : 's'} of ${name} (${plText(r.start)} to ${plText(r.end)})${lost ? `, ${lost} could not be priced` : ''}. `
    + (shown ? 'They are on the chart, at the last day it traded: the list under it steps through every trade.'
      : 'The chart did not take them: turn Chart off and on, then press this again.');
}
/* One plain sentence after a strategy goes on, or comes off, the Desk's watch list. */
function plWatchSaid(what, name) {
  return what === 'promote' ? `${name} is on the Desk page now, under Strategies. It is watch-only: it shows its results there and places no orders.`
    : `${name} is off the Desk page. It stays in the Book and can be promoted again.`;
}

/* ---- Promote to Desk (2026-10-09): the row under a finished run of a draft ----
   `row` = this draft's record on the Desk (GET /desklab) or null; `sha` = the hash of the open code ('' when it cannot be worked out);
   `hasRun` = a finished run of this draft is open; `dirty` = unsaved edits. Returns {label, hint, disabled, action: 'promote' | 'open' | null},
   or null where there is no such row (a built-in, or a script not saved yet).

     on the Desk?            code                      run open, saved     label                  action
     no                      -                         no, or unsaved      Promote to Desk        none (disabled: run first)
     no                      -                         yes                 Promote to Desk        promote
     yes, same code (hash)   -                         -                   On the Desk            open
     yes, other code         hash differs              no, or unsaved      Promote again          none (disabled: run first)
     yes, other code         hash differs              yes                 Promote again          promote ("The Desk runs an older version.")
     yes                     hash cannot be worked out no, or unsaved      Promote again          none (disabled: run first)
     yes                     hash cannot be worked out yes                 Promote again          promote ("Promoting again puts this one there, switched off.")

   A promoted strategy lands on the Desk switched OFF (also one promoted again while it was on): the owner turns it on there.

   The hash only tells "same code" from "other code". It never gates Promote: with a saved draft and a finished run open the row is
   enabled, and the Desk is the authority -- it refuses a run of other code in words (shown as the error line). */
function promoteState(state) {
  const { kind, dirty, hasRun, row, sha } = state || {};
  if (kind !== 'draft') return null;
  if (row && sha && row.sha256 === sha) return { label: 'On the Desk', hint: 'Open it on the Desk page.', disabled: false, action: 'open' };
  const label = row ? 'Promote again' : 'Promote to Desk';
  if (dirty || !hasRun) return { label, hint: 'Run a backtest of this exact code first.', disabled: true, action: null };
  const hint = !row ? 'Puts it on the Desk, switched off. It places no orders.'
    : sha ? 'The Desk runs an older version. Promoting again puts this one there, switched off.' : 'Promoting again puts this one there, switched off.';
  return { label, hint, disabled: false, action: 'promote' };
}
/* The lines after a promote went through: that it is on the Desk and off, then one for each thing the Desk would refuse on an account. */
function deskSaid(answer) {
  const notes = Array.isArray(answer && answer.notes) ? answer.notes.filter((n) => typeof n === 'string' && n) : [];
  return ['On the Desk, switched off. Turn it on there to run it in shadow.', ...notes.map((n) => `The Desk would refuse: ${n}`)];
}

/* ---- the strategy form ("Fill in a form"): the pure half ----
   The schema is the server's (GET /api/tester/drafts/form, homebase/charts/lab_forms.py): the rules, their fields, labels, words,
   choices, limits and defaults. Nothing here names a rule. A state is an answers-shaped object whose number boxes may still hold what
   was typed (a string); fmAnswers turns it into the object the build route takes. The server is the authority on every answer: the
   checks here only spare a request for a box that is plainly not a number. */
const FM_LATEST = '15:55';                 // the latest "out by" the server takes: the time boxes stop here
const FM_KEEP = ['name', 'market', 'side', 'stop', 'target', 'out_by'];      // what a rule change keeps when the new rule has it
const fmClone = (x) => JSON.parse(JSON.stringify(x));
const fmRule = (sc, id) => ((sc && sc.rules) || []).find((r) => r.id === id) || null;
const fmField = (sc, id) => (sc && sc.fields && sc.fields[id]) || null;
const fmNum = (x) => String(Math.round(x * 1e6) / 1e6);
/* what the form draws for a rule: name, market and the rule first, then the rule's own fields in the schema's order */
function fmShown(sc, rule) {
  const r = fmRule(sc, rule);
  return r ? ['name', 'market', 'rule', ...r.fields.filter((f) => f !== 'market')] : [];
}
/* the keys of an answers object for the rule: nothing else belongs in it */
function fmKeys(sc, rule) {
  const r = fmRule(sc, rule);
  return r ? ['name', 'rule', ...r.fields] : [];
}
/* the choices of a stop or target the rule offers: all of them, unless the schema limits a choice to some rules (`rules`) */
function fmKinds(sc, rule, field) {
  const f = fmField(sc, field);
  return ((f && f.kinds) || []).filter((k) => !Array.isArray(k.rules) || k.rules.includes(rule));
}
function fmSides(sc, rule) {
  const r = fmRule(sc, rule), all = (sc && sc.sides) || [];
  return r && Array.isArray(r.sides) ? all.filter((s) => r.sides.includes(s[0])) : all;
}
/* a choice that asks for a number has limits in the schema (points: min_ticks; a ratio: min / max) */
const fmHasValue = (k) => !!k && (k.min_ticks != null || k.min != null || k.max != null || k.max_ticks != null);
/* the number a stop or target choice starts from: this rule's default if it has that choice, else the field's, else the first rule's
   (in the schema's rules order). With a market and the schema's starting numbers, a points choice starts at that market's own. */
function fmKindValue(sc, rule, field, kind, market) {
  const key = FM_SIZE[field], size = kind === 'points' && key ? fmSize(sc, market, rule, key) : null;
  if (size != null) return size;
  const f = fmField(sc, field), d = (sc && sc.defaults) || {};
  const hit = [d[rule] && d[rule][field], f && f.default, ...fmRuleIds(sc).map((r) => d[r] && d[r][field])].find((x) => x && x.kind === kind && x.value != null);
  return hit ? hit.value : '';
}
/* ---- starting numbers that fit the market: schema.sizes[market][rule] = { distance?, stop?, target_points? } ----
   Whichever of the schema's objects comes first, "the first rule" is the first in the schema's `rules` list. */
const FM_SIZE = { stop: 'stop', target: 'target_points' };       // the size each points choice starts at
const fmRuleIds = (sc) => ((sc && sc.rules) || []).map((r) => r.id);
/* the starting number for a box in a market: the rule's own, or (a rule whose default has none, like a range stop) the first rule's that has one */
function fmSize(sc, market, rule, key) {
  const m = sc && sc.sizes && sc.sizes[market];
  if (!m) return null;
  const own = m[rule] && m[rule][key];
  if (typeof own === 'number') return own;
  const first = fmRuleIds(sc).find((r) => m[r] && typeof m[r][key] === 'number');
  return first ? m[first][key] : null;
}
/* every rule's starting number for a box in a market: a box holding one of these was never typed by hand */
function fmStarts(sc, market, key) {
  const m = sc && sc.sizes && sc.sizes[market];
  return m ? fmRuleIds(sc).map((r) => m[r] && m[r][key]).filter((x) => typeof x === 'number') : [];
}
/* A copy of the state whose distance, points stop and points target that hold ANY rule's starting number for the `from` market hold
   `rule`'s starting number for the `to` market instead. Only such a box changes: a number typed by hand, a ratio, the range stop and
   an empty box are left as they are. */
function fmFit(sc, st, from, to, rule = st.rule) {
  const next = fmClone(st);
  const fit = (raw, key) => {
    const b = fmSize(sc, to, rule, key), v = fmParse(raw);
    return b != null && v !== undefined && fmStarts(sc, from, key).includes(v) ? b : raw;
  };
  if ('distance' in next) next.distance = fit(next.distance, 'distance');
  for (const f of ['stop', 'target']) {
    if (next[f] && next[f].kind === 'points') next[f].value = fit(next[f].value, FM_SIZE[f]);
  }
  return next;
}
/* the market changed: the boxes still holding a starting number of the old market take the rule's starting number for the new one */
function fmSetMarket(sc, st, market) {
  const next = fmFit(sc, st, st.market, market);
  next.market = market;
  return next;
}
/* the words under a field: the rule's own when the schema has some for it (words_by_rule), else the field's */
function fmWords(sc, rule, field) {
  const f = fmField(sc, field);
  if (!f) return '';
  const own = f.words_by_rule && Object.prototype.hasOwnProperty.call(f.words_by_rule, rule) ? f.words_by_rule[rule] : null;
  return typeof own === 'string' && own ? own : String(f.words == null ? '' : f.words);
}
function fmSuggest(market, rule, taken = []) {
  let base = snake(`${market || ''}_${rule || ''}`) || 'my_strategy';
  if (!/^[a-z]/.test(base)) base = 'my_' + base;
  base = base.slice(0, 36);
  if (base.length < 2 || nameError(base)) base = 'my_strategy';
  let n = base, i = 2;
  while (taken.includes(n)) n = `${base.slice(0, 36)}_${i++}`;
  return n;
}
function fmStart(sc, taken = []) {
  const first = sc && sc.rules && sc.rules[0];
  if (!first || !sc.defaults || !sc.defaults[first.id]) return null;
  const s = fmClone(sc.defaults[first.id]);
  s.rule = first.id;
  s.name = fmSuggest(s.market, s.rule, taken);
  return s;
}
/* the rule changed: the rule's own defaults, with what both rules share carried over when the new rule takes it */
function fmSwitch(sc, st, rule) {
  const d = sc && sc.defaults && sc.defaults[rule];
  if (!d) return st;
  const keys = fmKeys(sc, rule), next = fmFit(sc, d, d.market, st.market, rule);      // the rule's own boxes start at this market's numbers
  next.market = d.market;
  next.rule = rule;
  for (const k of FM_KEEP) {
    if (st[k] === undefined || (k !== 'name' && !keys.includes(k))) continue;
    if (k === 'side' && !fmSides(sc, rule).some((s) => s[0] === st.side)) continue;
    if ((k === 'stop' || k === 'target') && !fmKinds(sc, rule, k).some((x) => x.id === (st[k] || {}).kind)) continue;
    next[k] = fmClone(st[k]);
  }
  return fmFit(sc, next, st.market, st.market, rule);        // a carried stop or target that is a starting number becomes this rule's
}
/* a state from the answers a file carries: the rule's defaults under them, and only the keys that belong.
   A stop, target or side the rule does not offer (a hand-edited header) is the rule's own default instead. */
function fmFill(sc, answers) {
  if (!answers || typeof answers !== 'object' || !sc || !sc.defaults || !sc.defaults[answers.rule]) return null;
  const d = sc.defaults[answers.rule], s = fmFit(sc, d, d.market, answers.market, answers.rule), own = fmClone(s);      // the file's market, not NQ's
  const keys = fmKeys(sc, answers.rule);
  for (const k of keys) if (answers[k] !== undefined) s[k] = fmClone(answers[k]);
  for (const k of ['stop', 'target']) {
    if (keys.includes(k) && !fmKinds(sc, answers.rule, k).some((x) => x.id === (s[k] || {}).kind)) s[k] = fmClone(own[k]);
  }
  if (keys.includes('side') && !fmSides(sc, answers.rule).some((x) => x[0] === s.side)) s.side = d.side;
  s.rule = answers.rule;
  if (typeof s.name !== 'string') s.name = '';
  return s;
}
function fmParse(raw) {
  if (typeof raw === 'number') return Number.isFinite(raw) ? raw : undefined;
  const t = String(raw == null ? '' : raw).trim();
  return /^[+-]?(\d+\.?\d*|\.\d+)$/.test(t) ? Number(t) : undefined;
}
/* The page-side check of one number box against the box's limits (a schema field or a stop / target choice) and the market's tick:
   '' when it can go to the server. The sentence for a multiple of the tick is the server's own. */
function fmNumberError(spec, raw, tick) {
  const v = fmParse(raw), t = Number(tick) > 0 ? Number(tick) : 0;
  if (v === undefined) return 'Type a number.';
  if (spec.min_ticks && t && v < spec.min_ticks * t - 1e-9) return `Use at least ${fmNum(spec.min_ticks * t)}.`;
  if (spec.tick_multiple && t) { const q = v / t; if (Math.abs(q - Math.round(q)) > 1e-9) return `Use a multiple of the tick (${fmNum(t)}).`; }
  if (spec.max_ticks && t && v > spec.max_ticks * t + 1e-9) return `Too far for this market: at most ${fmNum(spec.max_ticks * t)} points.`;
  const bad = (spec.min != null && v < spec.min) || (spec.max != null && v > spec.max) || (spec.type === 'int' && !Number.isInteger(v));
  if (!bad) return '';
  return spec.min != null && spec.max != null ? `Between ${spec.min} and ${spec.max}.` : spec.type === 'int' ? 'Use a whole number.' : spec.min != null ? `Use at least ${spec.min}.` : `Use at most ${spec.max}.`;
}
/* the number boxes of the state that is shown, checked: { field: sentence } */
function fmErrors(sc, st) {
  const out = {}, tick = sc && sc.ticks && sc.ticks[st.market];
  for (const f of fmKeys(sc, st.rule)) {
    const def = fmField(sc, f);
    if (!def) continue;
    if (def.type === 'number' || def.type === 'int') { const e = fmNumberError(def, st[f], tick); if (e) out[f] = e; }
    else if (def.type === 'stop' || def.type === 'target') {
      const k = (def.kinds || []).find((x) => x.id === (st[f] || {}).kind);
      if (fmHasValue(k)) { const e = fmNumberError(k, st[f].value, tick); if (e) out[f] = e; }
    }
  }
  return out;
}
/* the object the build route takes: the rule's keys only, numbers as numbers, a choice as the schema's own value */
function fmAnswers(sc, st) {
  const out = {};
  for (const k of fmKeys(sc, st.rule)) {
    const v = st[k], def = fmField(sc, k);
    if (v === undefined) continue;
    if (k === 'name') out[k] = String(v).trim();
    else if (!def) out[k] = v;
    else if (def.type === 'stop' || def.type === 'target') {
      const kind = (def.kinds || []).find((x) => x.id === (v || {}).kind), a = { kind: (v || {}).kind };
      if (fmHasValue(kind)) { const n = fmParse(v.value); a.value = n === undefined ? v.value : n; }
      out[k] = a;
    } else if (def.type === 'number' || def.type === 'int') { const n = fmParse(v); out[k] = n === undefined ? v : n; }
    else if (def.type === 'choice') out[k] = (def.choices || []).find((c) => String(c) === String(v)) ?? v;
    else out[k] = v;
  }
  return out;
}
/* A schema value that is written into markup (an id, a for, a data- attribute): cut down to [a-z0-9_], the shape every field id has. */
const fmId = (x) => String(x == null ? '' : x).replace(/[^a-z0-9_]/g, '');
/* The server errors that may still be shown: a box keeps its error only while its value is what was sent (a corrected box shows none). */
function fmKeepErrors(errors, asked, now) {
  const out = {};
  for (const [k, v] of Object.entries(errors || {})) if (JSON.stringify(asked ? asked[k] : undefined) === JSON.stringify(now ? now[k] : undefined)) out[k] = v;
  return out;
}
/* the sentence to show for a set of errors: the first of the fields in the order they are drawn, then any other key */
function fmFirstError(errors, order) {
  const e = errors || {}, keys = [...order.filter((k) => e[k]), ...Object.keys(e).filter((k) => !order.includes(k) && e[k])];
  return keys.length ? e[keys[0]] : '';
}

const api = { highlight, tab, enter, comment, nameError, suggestName, metaLine, statusOf, lineCount, ago, sections, INDENT,
  shownRows, canPick, pickRange, prunePicks, rowClick, draftName, deleteItem, deleteTargets, deleteConfirm, deleteConfirmHtml, deleteLine, goneLine, unsavedLine, deleteKey, isTyping,
  bpTitle, bpPhase, bpStarter, bpFields, bpArgs, bpJob, bpIdeaLine,
  tkFilter, tkFind, tkStatus, tkMarkets, tkSpan, tkParts, tkGutter, tkClip, tkDedent,
  PL_LAST, PL_MARKETS, PL_SESSIONS, PL_SIDES, PL_WAYS, PL_INDS, plSession, plSide, plTone, plCount, plLive, plControl, plDots, plRunning, plGuide,
  plSummary, plPick, plAt, plLadder, plMark, plWayLine, plIndLine, plWay, plInd, plForm, plCard, plCanSend,
  plUsable, plRules, plMainSetting, plIndicators, plSessionsFor, plNeed, plValueError, plSettingWords, plPrefill,
  FM_LATEST, fmShown, fmKeys, fmKinds, fmSides, fmWords, fmHasValue, fmKindValue, fmFit, fmSetMarket, fmStarts, fmSize, fmSuggest, fmStart, fmSwitch, fmFill, fmNumberError, fmErrors, fmAnswers, fmFirstError, fmId, fmKeepErrors,
  plPct, plMoney, plBookCard, plBookFull, plSigned, plBookLine, plCurveTiles, plCurvePath, plCurveAt, plCurveRead, plExecSaid, plWatchSaid, promoteState, deskSaid };
if (typeof window !== 'undefined') window.HBLabCode = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
