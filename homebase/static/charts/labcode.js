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

/* ---- the toolkit's blocks: every block of the blueprint toolkit with the code that implements it ----
   The server (bp.py blockcode) sends {groups: [{id, title, words, items}], sources: {id: {file, start, end, code}}}; an item is
   {id, name, sub, words, sides?: [{side, words}], markets, runs, why_not, parts: [{label, src}]}. */
const tkText = (it) => [it.name, it.sub, it.words, ...(it.sides || []).map((x) => `${x.side} ${x.words}`), ...(it.markets || [])].join(' ').toLowerCase();
/* The groups that have a block matching every word of the search; with no search, all of them. */
function tkFilter(groups, q) {
  const words = String(q || '').toLowerCase().split(/\s+/).filter(Boolean);
  if (!words.length) return groups;
  return groups.map((g) => ({ ...g, items: g.items.filter((it) => { const t = tkText(it); return words.every((w) => t.includes(w)); }) })).filter((g) => g.items.length);
}
const tkFind = (groups, id) => { for (const g of groups || []) { const it = g.items.find((x) => x.id === id); if (it) return it; } return null; };
/* "runs" or "not yet: why" */
const tkStatus = (it) => (it.runs ? { tone: 'ok', text: 'runs' } : { tone: 'no', text: it.why_not ? `not yet: ${it.why_not}` : 'not yet' });
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
    return { n: i + 1, label: p.label, span: tkSpan(s), file: s.file, start: s.start, end: s.end, lines: s.end - s.start + 1, code: tkDedent(s.code) };
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

const api = { highlight, tab, enter, comment, nameError, suggestName, metaLine, statusOf, lineCount, ago, sections, INDENT,
  bpTitle, bpPhase, bpStarter, bpFields, bpArgs, bpJob, bpIdeaLine,
  tkFilter, tkFind, tkStatus, tkMarkets, tkSpan, tkParts, tkGutter, tkClip, tkDedent };
if (typeof window !== 'undefined') window.HBLabCode = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
