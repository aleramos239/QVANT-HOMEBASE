import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

/* The "Homebase Next" skin (homebase/static/apple/) is PRESENTATION ONLY and must never reach the classic pages:
     - the manifest names all three tabs and only files that exist (the app loads all of the skin or none of it);
     - every style rule is scoped under html.hb-apple (only the new app adds that class);
     - the skin scripts never talk to a server and never swallow an event: a click on Arm, Kill or a strategy
       switch reaches the page's own handler exactly as on the classic page. */
const STATIC = path.join(path.dirname(fileURLToPath(import.meta.url)), '../../homebase/static');
const read = (p) => readFileSync(path.join(STATIC, p.replace(/^\/static\//, '')), 'utf8');
const manifest = JSON.parse(read('apple/manifest.json'));
const TABS = ['desk', 'charts', 'lab'];
const files = (kind) => [...new Set([...(manifest.shared[kind] || []), ...TABS.flatMap((t) => manifest.tabs[t][kind] || [])])];

test('apple skin: the manifest names every tab and only files that exist', () => {
  for (const t of TABS) assert.ok(manifest.tabs[t], `tab ${t} missing from the manifest`);
  for (const f of [...files('css'), ...files('js'), ...(manifest.samples || []).map((s) => s.url)]) {
    assert.ok(f.startsWith('/static/apple/'), `${f}: skin files live under /static/apple/`);
    assert.ok(existsSync(path.join(STATIC, f.replace(/^\/static\//, ''))), `${f} does not exist`);
  }
});

/* top-level selectors of a stylesheet (comments stripped; @media / @supports are entered, @keyframes / @font-face skipped) */
function selectors(css) {
  css = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const out = [];
  (function walk(s) {
    let i = 0;
    while (i < s.length) {
      const open = s.indexOf('{', i);
      if (open < 0) break;
      let depth = 1, j = open + 1;
      while (j < s.length && depth) { if (s[j] === '{') depth++; else if (s[j] === '}') depth--; j++; }
      const head = s.slice(i, open).trim(), body = s.slice(open + 1, j - 1);
      if (/^@(media|supports|container|layer)\b/.test(head)) walk(body);
      else if (!head.startsWith('@')) out.push(head);
      i = j;
    }
  })(css);
  return out;
}

test('apple skin: every rule is scoped under html.hb-apple', () => {
  const bad = [];
  for (const f of files('css')) {
    if (f.endsWith('/symbols.css')) continue;       // generated: only the .sf mask classes, which exist nowhere else
    for (const sel of selectors(read(f))) {
      for (const one of sel.split(',')) if (!/^html\.hb-apple\b/.test(one.trim())) bad.push(`${f}: ${one.trim().slice(0, 90)}`);
    }
  }
  assert.deepEqual(bad, [], 'rules that could reach the classic page');
});

test('apple skin: symbols.css only defines the mask variables and the .sf classes', () => {
  for (const sel of selectors(read('apple/symbols.css')))
    for (const one of sel.split(',')) assert.match(one.trim(), /^(html\.hb-apple|\.sf(-[a-z0-9-]+)?)$/, `symbols.css: ${one}`);
});

test('apple skin: the scripts never talk to a server and never swallow an event', () => {
  const BANNED = [/\bfetch\s*\(/, /XMLHttpRequest/, /sendBeacon/, /\bWebSocket\b/, /EventSource/, /['"`]\/api\//, /stopPropagation/, /stopImmediatePropagation/, /preventDefault/,
                  /\.onclick\s*=/, /removeEventListener/];
  const bad = [];
  for (const f of files('js')) {
    const lines = read(f).split('\n');
    lines.forEach((line, i) => {
      const code = line.replace(/\/\/.*$/, '');
      for (const re of BANNED) if (re.test(code)) bad.push(`${f}:${i + 1}: ${line.trim().slice(0, 110)}`);
    });
  }
  assert.deepEqual(bad, [], 'skin scripts must stay presentation-only');
});

test('apple skin: the Desk skin leans only on things the Desk page still has', () => {
  const page = read('index.html'), skin = read('apple/desk.js');
  for (const id of ['pgSw', 'bulb', 'clock', 'armBtn', 'killBtn', 'settingsBtn', 'side', 'readyStrip', 'todayFoot', 'noticeStrip', 'stratList', 'dayTl',
                    'viewToday', 'viewStrat', 'viewActivity', 'themeToggle'])
    assert.ok(page.includes(`id="${id}"`) && skin.includes(`#${id}`), `#${id} is expected by the skin and present in the page`);
  for (const cls of ['pill-slot', 'app-main', 'frame', 'inset-topbar']) assert.ok(page.includes(cls), `.${cls} is in the page`);
  for (const fn of ['openChecks']) assert.match(page, new RegExp(`function ${fn}\\(`), `${fn}() is the page's own`);
  // the nodes the inspector borrows from a strategy's render
  for (const cls of ['figs', 'qlinks', 'sd-actions']) assert.ok(page.includes(`class="${cls}"`), `.${cls} is rendered by the page`);
});
