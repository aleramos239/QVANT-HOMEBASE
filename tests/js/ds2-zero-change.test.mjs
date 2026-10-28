/* Package 2 (tokens and zero-change cleanup): the stylesheets must RESOLVE to the same thing as on the pinned base.
   No browser here, so the text is compared: every declaration of every rule of a bundle (skin shared + the tab's css, or the plain
   page sheets) on the base commit against the branch, var() tokens expanded. A declaration only on the base side must be PROVEN dead
   (an !important rule of the skin that always matches whenever it does, or a later rule of the very same selector). A declaration
   only on the branch side must be a published token. The hoisted button core must not meet an element that also carries a class
   whose rule it could now outrank by order. */
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { parse, inlineStyles, tokenMaps, resolve, importantDominator, laterSameSelector, spec, sameSpec, subject, tokens } from './cssproof.mjs';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
const STATIC = path.join(ROOT, 'homebase', 'static');
const git = (...a) => execFileSync('git', a, { cwd: ROOT, encoding: 'utf8', maxBuffer: 1 << 26 });
/* The proof compares the commit that added this test with its own parent (the package, nothing else), so another package
   merging into the same sheets later never trips it. `live` is the working tree, for the checks that guard the sheets going forward. */
const ADD = git('log', '--diff-filter=A', '-1', '--format=%H', '--', 'tests/js/ds2-zero-change.test.mjs').trim();
const BASE = ADD + '^';
const rel = (f) => 'homebase/static/' + f;
const live = (f) => fs.readFileSync(path.join(ROOT, rel(f)), 'utf8');
const now = (f) => git('show', `${ADD}:${rel(f)}`);
const was = (f) => git('show', `${BASE}:${rel(f)}`);

const SKIN = { desk: ['apple/symbols.css', 'apple/system.css', 'apple/desk.css'], charts: ['apple/symbols.css', 'apple/system.css', 'apple/charts.css'], lab: ['apple/symbols.css', 'apple/system.css', 'apple/lab.css'] };
const PLAIN = { desk: ['shadcn.css', 'index.html', 'apple.css', 'hb.css'], charts: ['charts/charts.css', 'charts/apple-charts.css'], lab: ['charts/charts.css', 'charts/apple-charts.css', 'charts/lab.css'] };
const sheetText = (get, f) => (f.endsWith('.html') ? (/index\.html$/.test(f) ? inlineStyles(get(f)) : '') : get(f));
const sheets = (get, files) => files.map((f) => ({ file: f, ...parse(sheetText(get, f)) }));
const flat = (shs) => { let n = 0; return shs.flatMap((s) => s.rules.map((r) => ({ ...r, file: s.file, seq: n++ }))); };

/* custom properties the package adds, on the skin root only */
const NEW_TOKEN = /^--(sp-(2|4|6|8|10|12|14|16|20|24)|hb-r-ctl|hb-r-mini|hb-menu-r|a-field-shadow|a-field-shadow-strong)$/;
const isRoot = (p) => p === 'html.hb-apple' || p === 'html.hb-apple[data-theme="dark"]';

/* the declarations of a bundle as a multiset of "media | selector part | prop | important | light-resolved | dark-resolved" */
/* the three spinners turn the same way (one keyframe body, proven below); a rename onto the one that stays is not a change */
const SPIN = (v) => v.replace(/\b(hb-lab-spin|tst-eval-spin)\b/g, 'hb-spin');
function declSet(shs, mapsOf) {
  const rules = flat(shs), { light, dark } = mapsOf(rules), out = new Map();
  for (const r of rules) for (const p of r.parts) for (const d of r.decls) {
    const key = [r.media, p, d.prop, d.important ? '!' : '', d.prop.startsWith('--') ? d.value : SPIN(resolve(d.value, light)), d.prop.startsWith('--') ? '' : SPIN(resolve(d.value, dark))].join(' | ');
    (out.get(key) ?? out.set(key, []).get(key)).push({ rule: r, part: p, decl: d });
  }
  return out;
}
const skinMaps = (rules) => tokenMaps(rules);
const plainMaps = () => ({ light: {}, dark: {} });

function diff(baseSets, branchSets) {
  const onlyBase = [], onlyBranch = [];
  for (const [k, v] of baseSets) { const n = (branchSets.get(k) || []).length; if (v.length > n) onlyBase.push(...v.slice(0, v.length - n).map((x) => ({ k, ...x }))); }
  for (const [k, v] of branchSets) { const n = (baseSets.get(k) || []).length; if (v.length > n) onlyBranch.push(...v.slice(n).map((x) => ({ k, ...x }))); }
  return { onlyBase, onlyBranch };
}


/* is an icon mask referenced by name anywhere in the app: sf('name'), an sf-name class, a var(--sf-name), or the name quoted */
let CORPUS = null;
function corpus() {
  if (CORPUS === null) {
    const files = execFileSync('git', ['ls-files', 'homebase', 'deploy'], { cwd: ROOT, encoding: 'utf8' }).trim().split('\n')
      .filter((f) => /\.(js|css|html|py|swift)$/.test(f) && !/symbols\.css$|gen_symbols\.swift$|vendor\//.test(f) && fs.existsSync(path.join(ROOT, f)));
    CORPUS = files.map((f) => fs.readFileSync(path.join(ROOT, f), 'utf8')).join('\n');
  }
  return CORPUS;
}
const maskUsed = (n) => new RegExp(`(?<![\\w-])(--)?sf-${n}(-w|-h)?(?![\\w-])|['"\`]${n}['"\`]`).test(corpus());
const genRows = (text) => [...text.matchAll(/^([a-z0-9-]+)\s+[a-z0-9.]+\s+\d+\s+\w+$/gm)].map((m) => m[1]);
let BR = null;
const BASE_ROWS = () => (BR ??= genRows(git('show', `${BASE}:deploy/macapp/gen_symbols.swift`)));
const branchRows = () => genRows(git('show', `${ADD}:deploy/macapp/gen_symbols.swift`));

/* ---- the structural asks (these fail on the base) ---------------------------------------------------------------- */
test('system.css publishes the spacing steps, the radius tokens and the field shadows', () => {
  const sys = parse(live('apple/system.css')), root = sys.rules.filter((r) => !r.media && r.parts.includes('html.hb-apple')).flatMap((r) => r.decls);
  const get = (n) => root.find((d) => d.prop === n)?.value;
  for (const n of [2, 4, 6, 8, 10, 12, 14, 16, 20, 24]) assert.equal(get('--sp-' + n), n + 'px', '--sp-' + n);
  assert.equal(get('--hb-r-ctl'), '6px');
  assert.equal(get('--hb-r-mini'), '5px');
  assert.equal(get('--hb-menu-r'), '13px');
  assert.equal(get('--a-field-shadow'), '0 0 0 1px var(--a-field-edge), 0 .5px 1.5px rgb(0 0 0 / .08)');
  assert.equal(get('--a-field-shadow-strong'), '0 0 0 1px var(--a-field-edge), 0 .5px 1.5px rgb(0 0 0 / .1)');
});

test('the rules this package touched use the radius and spacing tokens it published', () => {
  const all = ['apple/system.css', 'apple/desk.css', 'apple/charts.css', 'apple/lab.css'].map(live).join('\n');
  for (const t of ['--hb-r-ctl', '--hb-r-mini', '--sp-2', '--sp-6', '--sp-10']) assert.ok(all.includes(`var(${t})`), t + ' is published but nothing uses it');
  // every field whose shadow is the named one also names its corner
  for (const f of ['apple/system.css', 'apple/desk.css', 'apple/charts.css', 'apple/lab.css'])
    for (const r of parse(live(f)).rules) if (r.decls.some((d) => /^var\(--a-field-shadow/.test(d.value))) {
      const br = r.decls.find((d) => d.prop === 'border-radius');
      if (br) assert.match(br.value, /^var\(--hb-(r-ctl|r-mini|bubble-r)\)$/, `${f}: ${r.sel}`);
    }
});

test('the field shadow tokens stay resolvable: --a-field-edge is only ever declared on the skin root', () => {
  for (const f of ['apple/system.css', 'apple/desk.css', 'apple/charts.css', 'apple/lab.css'])
    for (const r of parse(live(f)).rules) if (r.decls.some((d) => d.prop === '--a-field-edge')) assert.ok(r.parts.every(isRoot), `${f}: ${r.sel}`);
});

test('the button skin is written once for the Desk and Charts: system.css, not each tab file', () => {
  const core = /^0 14\.5px$/;
  const count = (f) => parse(live(f)).rules.filter((r) => r.parts.includes('html.hb-apple .btn') && r.decls.some((d) => d.prop === 'padding' && core.test(d.value))).length;
  assert.equal(count('apple/system.css'), 1);
  assert.equal(count('apple/desk.css'), 0);
  assert.equal(count('apple/charts.css'), 0);
});

test('the menu radius, the field shadows and the spinner are named once', () => {
  for (const f of ['apple/desk.css', 'apple/charts.css', 'apple/lab.css']) {
    const t = live(f);
    assert.ok(!/0 0 0 1px var\(--a-field-edge\), 0 \.5px 1\.5px/.test(t), f + ' repeats the field shadow');
    assert.ok(!/border-radius: 13px/.test(t.replace(/\.hbpanel\.floating[^\n]*/g, '')), f + ' repeats the menu radius');
  }
  const spins = [...['apple/lab.css', 'charts/charts.css', 'charts/apple-charts.css'].map(now).join('\n').matchAll(/@keyframes ([\w-]*spin)\b/g)].map((m) => m[1]);
  assert.deepEqual(spins, ['hb-spin']);
  assert.ok(!/hb-lab-spin|tst-eval-spin\s+\.8s/.test(live('apple/lab.css') + live('charts/charts.css')));
});

test('the plain Desk says which colour scheme it is', () => {
  const css = parse(live('shadcn.css'));
  const val = (sel) => css.rules.find((r) => r.parts.includes(sel) && r.decls.some((d) => d.prop === 'color-scheme'))?.decls.find((d) => d.prop === 'color-scheme').value;
  assert.equal(val(':root, :root[data-theme="light"]') ?? css.rules.find((r) => r.parts.includes(':root') && r.decls.some((d) => d.prop === 'color-scheme'))?.decls.find((d) => d.prop === 'color-scheme').value, 'light');
  assert.equal(val(':root[data-theme="dark"]'), 'dark');
  // the skin sets none of its own on the root, so the system sheet decides; the plain page is never loaded under it with a different value
  for (const f of ['apple/system.css', 'apple/desk.css']) assert.ok(!parse(live(f)).rules.some((r) => r.decls.some((d) => d.prop === 'color-scheme' && r.parts.some((p) => !isRoot(p) && !/hb-apple/.test(p)))), f);
});

test('the dead plain-skin Desk rules are gone', () => {
  const apple = parse(live('apple.css')), inline = parse(inlineStyles(live('index.html')));
  assert.ok(!apple.rules.some((r) => !r.media && r.parts.some((p) => /^\.btn(-sm|:active)?$/.test(p))), 'apple.css .btn / .btn-sm / .btn:active');
  const scrollPads = apple.rules.filter((r) => r.parts.includes('.scroll') && r.decls.some((d) => d.prop === 'padding'));
  assert.equal(scrollPads.length, 1, 'one .scroll padding is left in apple.css');
  assert.ok(!inline.rules.some((r) => r.parts.includes('.scroll') && r.decls.some((d) => d.prop === 'padding')), 'index.html inline .scroll padding');
  assert.ok(!inline.rules.some((r) => r.parts.includes('.view-wrap') && r.decls.some((d) => d.prop === 'max-width')), 'index.html inline .view-wrap max-width');
});

test('the unused icon masks are dropped from the generator and from symbols.css, and none that was dropped is named anywhere', () => {
  const rows = branchRows();
  const css = now('apple/symbols.css'), have = [...css.matchAll(/^\s+--sf-([a-z0-9-]+): url\(/gm)].map((m) => m[1]);
  assert.deepEqual(have, rows, 'symbols.css holds exactly the generator rows');
  assert.equal(BASE_ROWS().length - rows.length, 37);
  for (const n of BASE_ROWS().filter((x) => !rows.includes(x))) assert.ok(!maskUsed(n), 'a dropped mask is used: ' + n);
});

/* ---- the zero-change proof ---------------------------------------------------------------------------------------- */
/* the hoisted .btn core now sits ahead of every rule of the tab file. A rule that was BEFORE the old core with the same specificity and
   a property in common lost to it; now it would win the tie. So no element may carry `btn` with a class from such a rule. The class
   set is read off the base sheets (not typed), and every quoted class string in the app is checked. */
const TIES = () => {
  const out = new Set();
  for (const f of ['apple/desk.css', 'apple/charts.css']) {
    const rules = flat(sheets(was, [f])), cores = rules.filter((r) => r.parts.some((p) => /^html\.hb-apple \.btn(:\w+)?$/.test(p)) && r.decls.some((d) => d.prop === 'padding' || d.prop === 'background'));
    for (const core of cores) for (const cp of core.parts.filter((p) => /^html\.hb-apple \.btn(:\w+)?$/.test(p))) {
      const props = new Set(core.decls.map((d) => d.prop));
      for (const r of rules) {
        if (r.seq >= core.seq || !r.decls.some((d) => props.has(d.prop))) continue;
        for (const p of r.parts) if (sameSpec(spec(p), spec(cp))) for (const t of tokens(subject(p) || '')) if (t[0] === '.' && t !== '.btn') out.add(t.slice(1));
      }
    }
  }
  return out;
};
test('no element carries .btn together with a class that sat before the old button core', () => {
  const ties = TIES();
  assert.ok(ties.size > 20 && ties.has('menu-input') && ties.has('dtb-btn'), 'the tie set is read off the base sheets: ' + [...ties]);
  const walk = (d, acc = []) => { for (const e of fs.readdirSync(d, { withFileTypes: true })) { const p = path.join(d, e.name); if (e.isDirectory()) { if (e.name !== 'vendor') walk(p, acc); } else if (/\.(js|html)$/.test(e.name)) acc.push(p); } return acc; };
  const lit = /(["'`])((?:(?!\1)[^\n\\]|\\.)*)\1/g, bad = [];
  for (const f of walk(STATIC)) fs.readFileSync(f, 'utf8').split('\n').forEach((l, i) => {
    for (const m of l.matchAll(lit)) { const w = m[2].split(/\s+/); if (w.includes('btn') && w.some((c) => ties.has(c))) bad.push(`${path.relative(STATIC, f)}:${i + 1}`); }
  });
  assert.deepEqual(bad, []);
});

/* a proof that a base-only declaration never applied; null = not proven */
function deadReason(baseShs, bundle, item) {
  const { rule, part, decl } = item, sysRules = flat(baseShs.filter((s) => s.file === 'apple/system.css'));
  if (rule.file === 'apple/symbols.css') {          // an icon mask nothing names, and the class that points at it
    const names = BASE_ROWS(), m = /^--sf-(.+?)(-w|-h)?$/.exec(decl.prop), c = /^\.sf-(.+)$/.exec(part);
    const n = c ? c[1] : m && (names.includes(m[1] + (m[2] || '')) ? m[1] + (m[2] || '') : m[1]);
    return n && names.includes(n) && !branchRows().includes(n) && !maskUsed(n) ? 'unused mask ' + n : null;
  }
  if (decl.important || decl.prop.startsWith('--')) return null;
  if (bundle === 'skin') {
    const dom = importantDominator(sysRules, part, decl.prop);
    if (dom) return 'important ' + dom;
  }
  const later = laterSameSelector(baseShs, rule.file, part, rule.media, decl.prop, rule.order);
  return later ? 'later ' + later : null;
}

/* in the Lab bundle the hoisted .btn core is new text, but the Lab's own `.lab-page .btn` sets the same property at a higher specificity,
   and every Lab element sits under <body class="lab-page"> (asserted above), so the core never decides anything there */
function shadowedInLab(shs, x) {
  if (x.rule.file !== 'apple/system.css' || !/^html\.hb-apple \.btn(:\w+)?$/.test(x.part)) return false;
  const own = x.part.replace('html.hb-apple .btn', 'html.hb-apple .lab-page .btn'), a = spec(x.part), b = spec(own);
  const higher = b[0] > a[0] || (b[0] === a[0] && (b[1] > a[1] || (b[1] === a[1] && b[2] > a[2])));
  return higher && flat(shs).some((r) => r.file === 'apple/lab.css' && !r.media && r.parts.includes(own) && r.decls.some((d) => d.prop === x.decl.prop && !d.important));
}
const PROOFS = {};
for (const [tab, files] of Object.entries(SKIN)) {
  test(`skin bundle ${tab}: every changed declaration is a published token or proven dead`, () => {
    const b = sheets(was, files), n = sheets(now, files);
    const { onlyBase, onlyBranch } = diff(declSet(b, skinMaps), declSet(n, skinMaps));
    const unproven = onlyBase.filter((x) => !deadReason(b, 'skin', x)).map((x) => `${x.rule.file}: ${x.part} { ${x.decl.prop}: ${x.decl.value} }`);
    assert.deepEqual(unproven, [], 'removed or changed and not proven dead');
    const stray = onlyBranch.filter((x) => !(NEW_TOKEN.test(x.decl.prop) && isRoot(x.part)) && !(tab === 'lab' && shadowedInLab(n, x))).map((x) => `${x.rule.file}: ${x.part} { ${x.decl.prop}: ${x.decl.value} }`);
    assert.deepEqual(stray, [], 'added and not a published token');
    PROOFS[tab] = onlyBase.length;
  });
  test(`skin bundle ${tab}: every selector that was there still is, unless listed and all its declarations are dead`, () => {
    const b = sheets(was, files), n = sheets(now, files);
    const keys = (shs) => new Set(flat(shs).flatMap((r) => r.parts.map((p) => r.media + ' | ' + p)));
    const nk = keys(n), gone = [...keys(b)].filter((k) => !nk.has(k));
    for (const k of gone) {
      const [media, ...p] = k.split(' | '), part = p.join(' | ');
      const items = flat(b).filter((r) => r.media === media && r.parts.includes(part)).flatMap((r) => r.decls.map((decl) => ({ rule: r, part, decl })));
      for (const it of items) assert.ok(deadReason(b, 'skin', it), `removed selector ${k} has a live declaration ${it.decl.prop}`);
    }
  });
}

for (const [tab, files] of Object.entries(PLAIN)) {
  test(`plain sheets ${tab}: every removed declaration is shadowed by a later rule of the same selector`, () => {
    const b = sheets(was, files), n = sheets(now, files);
    const { onlyBase, onlyBranch } = diff(declSet(b, plainMaps), declSet(n, plainMaps));
    const unproven = onlyBase.filter((x) => !deadReason(b, 'plain', x)).map((x) => `${x.rule.file}: ${x.part} { ${x.decl.prop}: ${x.decl.value} }`);
    assert.deepEqual(unproven, [], 'removed and not proven dead');
    // color-scheme (shadcn.css) is the only thing the plain sheets may gain
    const stray = onlyBranch.filter((x) => x.decl.prop !== 'color-scheme').map((x) => `${x.rule.file}: ${x.part} { ${x.decl.prop}: ${x.decl.value} }`);
    assert.deepEqual(stray, []);
  });
}

test('the three spinner keyframes were the same turn, so one of them can serve all three', () => {
  const frames = { ...parse(was('apple/lab.css')).frames, ...parse(was('charts/charts.css')).frames, ...parse(was('charts/apple-charts.css')).frames };
  assert.equal(frames['hb-lab-spin'], frames['hb-spin']);
  assert.equal(frames['tst-eval-spin'], frames['hb-spin']);
  assert.equal(frames['hb-spin'], 'to { transform: rotate(360deg); }');
  // and hb-spin is on both pages that load these sheets, so a name moved onto it always finds it
  for (const page of ['charts.html', 'backtest.html']) assert.match(live(page), /charts\/apple-charts\.css/);
});

test('the Lab keeps every property the hoisted .btn core sets, at a higher specificity than the core', () => {
  const lab = parse(now('apple/lab.css')).rules.filter((r) => !r.media), core = parse(now('apple/system.css')).rules.filter((r) => r.parts.some((p) => /^html\.hb-apple \.btn(:\w+)?$/.test(p)) && !r.decls.some((d) => d.important));
  assert.equal(core.length, 4);
  for (const c of core) {
    const state = c.parts[0].replace('html.hb-apple .btn', ''), own = lab.filter((r) => r.parts.includes('html.hb-apple .lab-page .btn' + state)).flatMap((r) => r.decls.map((d) => d.prop));
    for (const d of c.decls) assert.ok(own.includes(d.prop), `.lab-page .btn${state} must set ${d.prop}`);
  }
  assert.match(fs.readFileSync(path.join(STATIC, 'backtest.html'), 'utf8'), /<body class="lab-page">/);
});

test('the !important BUBBLES block and every other important declaration are untouched', () => {
  for (const f of ['apple/system.css', 'apple/desk.css', 'apple/charts.css', 'apple/lab.css']) {
    const imp = (t) => parse(t).rules.flatMap((r) => r.parts.flatMap((p) => r.decls.filter((d) => d.important).map((d) => `${r.media}|${p}|${d.prop}|${d.value}`))).sort();
    assert.deepEqual(imp(now(f)), imp(was(f)), f);
  }
});

test('no font-family, font-size, colour or border-radius value changed anywhere in the touched sheets', () => {
  const guard = /^(font-family|font-size|color|background(-color)?|border-radius|border-(top|bottom)-(left|right)-radius)$/;
  for (const [tab, files] of Object.entries(SKIN)) {
    const b = sheets(was, files), n = sheets(now, files), { onlyBase, onlyBranch } = diff(declSet(b, skinMaps), declSet(n, skinMaps));
    const changed = new Set(onlyBranch.filter((x) => guard.test(x.decl.prop) && !(tab === 'lab' && shadowedInLab(n, x))).map((x) => x.part + '|' + x.decl.prop));
    assert.deepEqual([...changed], [], tab + ': a value of a guarded property was added or changed');
    for (const x of onlyBase.filter((x) => guard.test(x.decl.prop))) assert.ok(deadReason(b, 'skin', x), `${tab}: ${x.part} ${x.decl.prop} removed but live`);
  }
});
