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

const api = { highlight, tab, enter, comment, nameError, suggestName, metaLine, statusOf, lineCount, ago, sections, INDENT };
if (typeof window !== 'undefined') window.HBLabCode = api;
if (typeof module !== 'undefined' && module.exports) module.exports = api;
})();
