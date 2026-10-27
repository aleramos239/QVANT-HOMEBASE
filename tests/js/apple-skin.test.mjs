import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, existsSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import vm from 'node:vm';

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
      for (const one of sel.split(',')) if (!/^(html\.hb-apple\b|:where\(html\.hb-apple\) )/.test(one.trim())) bad.push(`${f}: ${one.trim().slice(0, 90)}`);
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
                    'viewToday', 'viewStrat', 'viewActivity', 'themeToggle', 'statusPill'])
    assert.ok(page.includes(`id="${id}"`) && skin.includes(`#${id}`), `#${id} is expected by the skin and present in the page`);
  for (const cls of ['pill-slot', 'app-main', 'frame', 'inset-topbar']) assert.ok(page.includes(cls), `.${cls} is in the page`);
  for (const fn of ['openChecks', 'setStratRr', 'readinessShown']) assert.match(page, new RegExp(`function ${fn}\\(`), `${fn}() is the page's own`);
  // the page's own state the skin reads by name (a rename would leave the toolbar words stuck, with no error)
  for (const v of ['ST', 'DESK_STALE', 'STALE_WHY', 'DESKRES', 'DESKGRES']) assert.match(page, new RegExp(`\\blet ${v}\\b`), `${v} is the page's own`);
  // the nodes the inspector borrows from a strategy's render
  for (const cls of ['figs', 'qlinks', 'sd-actions']) assert.ok(page.includes(`class="${cls}"`), `.${cls} is rendered by the page`);
});

/* The Desk toolbar's words (apple/desk.js, the "toolbar words" block), run for real in a vm sandbox: the plain functions
   the skin's sync() writes into the toolbar. */
const DESK_SKIN = read('apple/desk.js');
function toolbarWords(ctx = {}) {
  const i = DESK_SKIN.indexOf('/* ---- toolbar words'), j = DESK_SKIN.indexOf('/* ---- end toolbar words ---- */');
  assert.ok(i >= 0 && j > i, 'the toolbar words block');
  const c = vm.createContext({ window: {}, ...ctx });
  vm.runInContext(DESK_SKIN.slice(i, j) + '\nglobalThis.W = { machineWord, readyWord, chartWords, recordOf, researchWord, words };', c);
  return c.W;
}

test('desk skin: the machine chip reads ONE value -- the shell\'s HB_MACHINE, else /api/status machine -- and is absent when unknown', () => {
  const chip = (win, st) => toolbarWords({ window: win, location: { hostname: 'localhost' } }).machineWord(st);
  assert.equal(chip({ HB_MACHINE: 'mac' }, null), 'This Mac');
  assert.equal(chip({ HB_MACHINE: 'server' }, null), 'Server · Chicago');
  assert.equal(chip({}, { machine: 'server' }), 'Server · Chicago');
  assert.equal(chip({}, { machine: 'mac' }), 'This Mac');
  assert.equal(chip({ HB_MACHINE: 'mac' }, { machine: 'server' }), 'This Mac', 'the shell\'s value wins: one reader, no mix');
  // missing or unknown: no chip -- never "This Mac" from a localhost address
  for (const [win, st] of [[{}, null], [{}, {}], [{}, undefined], [{ HB_MACHINE: 'vps' }, null], [{}, { machine: 'chicago' }]]) assert.equal(chip(win, st), '');
  assert.doesNotMatch(DESK_SKIN, /location\.(hostname|host)\b/, 'the skin never guesses the machine from the address');
  assert.match(DESK_SKIN, /el\('span', \{ class: 'hb-machine', hidden: true \}[,)]/, 'the chip starts hidden');
  // a narrow window's words: the server keeps its name and colour, the Mac its words
  assert.equal(toolbarWords({ window: { HB_MACHINE: 'server' } }).machineWord(null, true), 'Server');
  assert.equal(toolbarWords({ window: { HB_MACHINE: 'mac' } }).machineWord(null, true), 'This Mac');
  assert.equal(toolbarWords({ window: {} }).machineWord(null, true), '');
});

test('desk skin: readiness in words comes from the page\'s own readinessShown -- the list openChecks opens', () => {
  const seen = [];
  const shown = (r, st) => { seen.push([r, st]); return r && { ...r, checks: r.checks.map((c) => (c.label === 'nq930' ? { ...c, level: 'info' } : c)) }; };
  const word = (st, fn = shown) => [...toolbarWords({ window: { readinessShown: fn } }).readyWord(st)];      // (out of the vm's realm)
  assert.deepEqual(word(null), ['', 'Checking…'], 'no status yet');
  assert.deepEqual(word({ readiness: null }), ['', 'Checking…']);
  assert.deepEqual(word({ readiness: { checks: [] } }, null), ['', 'Checking…'], 'without the page helper: still checking, never "Ready"');
  const st = { readiness: { checks: [{ label: 'feed', level: 'ok' }, { label: 'nq930', level: 'bad', detail: 'no signal arrived' }] } };
  assert.deepEqual(word(st), ['ok', 'Ready'], 'a check the page shows as info does not count');
  assert.equal(seen.at(-1)[0], st.readiness); assert.equal(seen.at(-1)[1], st);
  assert.deepEqual(word({ readiness: { checks: [{ label: 'feed', level: 'warn' }] } }), ['warn', '1 thing needs a look']);
  assert.deepEqual(word({ readiness: { checks: [{ label: 'a', level: 'warn' }, { label: 'b', level: 'bad' }, { label: 'c', level: 'info' }] } }), ['bad', '2 things need a look']);
  // while the page's state is old (its DESK_STALE) the last answer is not current: never a stale "Ready" (nor a mild "Checking…")
  const stale = (s, why) => [...toolbarWords({ window: { readinessShown: shown } }).readyWord(s, true, why)];
  const okSt = { readiness: { checks: [{ label: 'feed', level: 'ok' }] } };
  for (const why of ['the desk is not answering', 'the desk answered HTTP 403: write guard', "the desk's status was unreadable", '', undefined])
    assert.deepEqual(stale(okSt, why), ['bad', 'Desk not answering']);
  assert.deepEqual(stale(null, 'the desk is not answering'), ['bad', 'Desk not answering'], 'never answered at all');
  assert.deepEqual(stale(okSt, 'updates pause while a menu or a size edit is open'), ['', 'Updates paused'], 'only an open menu holds the page');
  assert.match(DESK_SKIN, /readyWord\(st, stale, staleWhy_\(\)\)/, 'the toolbar word passes the page\'s stale flag and reason');
  assert.match(DESK_SKIN, /const stale_ = \(\) => \{ try \{ return DESK_STALE === true; \}/);
  assert.match(DESK_SKIN, /const staleWhy_ = \(\) => \{ try \{ return String\(STALE_WHY \|\| ''\); \}/);
  assert.match(read('index.html'), /DESK_STALE = true; STALE_WHY = "updates pause while a menu or a size edit is open";/, 'the page\'s pause reason, as the skin reads it');
  assert.match(DESK_SKIN, /new MutationObserver\(words\)\.observe\(pill, \{ attributes: true, attributeFilter: \['class'\] \}\)/, 'the word follows the pill going stale');
  // the inspector's row keeps its own words, from the bulb the page paints (not the toolbar's count)
  assert.match(DESK_SKIN, /const txt = lvl === 'ok' \? 'Ready to trade' : lvl === 'warn' \? 'Needs attention' : lvl === 'bad' \? 'Not ready' : 'Checking…';/);
  assert.match(DESK_SKIN, /class: 'hb-ready-word'[^\n]*window\.openChecks\(\)/, 'the word opens the page\'s own System checks');
});

test('desk skin: the chart-trading chip shows whenever the switch is ON, armed or not, with the live accounts the page tags LIVE', () => {
  const words = (st) => toolbarWords().chartWords(st);
  const acc = { a: { env: 'live' }, b: { env: 'live', connected: false }, c: { env: 'demo' }, d: { env: 'paper' }, e: null };
  for (const st of [null, {}, { chart_trading: null }, { chart_trading: { enabled: false }, accounts: acc }]) assert.equal(words(st), '', 'off or unknown: no chip');
  const on = { enabled: true, max_order_qty: 10, max_position_qty: 20 };
  assert.equal(words({ chart_trading: on }), 'Chart trading ON');
  assert.equal(words({ chart_trading: on, accounts: { c: { env: 'demo' } } }), 'Chart trading ON');
  assert.equal(words({ chart_trading: on, accounts: { a: { env: 'live' } } }), 'Chart trading ON · 1 live account');
  assert.equal(words({ chart_trading: on, accounts: acc }), 'Chart trading ON · 2 live accounts', 'an offline live account still counts');
  // the Arm state plays no part (Disarm does not stop the chart page)
  for (const armed of [true, false]) assert.equal(words({ armed, status: armed ? 'armed' : 'disarmed', chart_trading: on, accounts: acc }), 'Chart trading ON · 2 live accounts');
  // the short words a narrow window keeps: the count stays
  const short = (st) => toolbarWords().chartWords(st, true);
  assert.equal(short({ chart_trading: on, accounts: acc }), 'Chart ON · 2 live');
  assert.equal(short({ chart_trading: on, accounts: { a: { env: 'live' } } }), 'Chart ON · 1 live');
  assert.equal(short({ chart_trading: on }), 'Chart ON');
  assert.equal(short({ chart_trading: { enabled: false }, accounts: acc }), '');
  assert.match(DESK_SKIN, /el\('span', \{ class: 'hb-ct-chip', hidden: true/, 'the chip starts hidden');
});

// what words() writes into the toolbar and the inspector's readiness row, run on small fake nodes
function wordsOn({ st = null, stale = false, why = '', win = {}, bulbLvl = '' } = {}) {
  const node = () => ({ textContent: '', hidden: false, title: '', dataset: {}, attrs: {}, setAttribute(k, v) { this.attrs[k] = v; } });
  const n = { machine: node(), mLong: node(), mShort: node(), readyBtn: node(), ctLong: node(), ctShort: node(), ctChip: node(), sum: node(), row: node() };
  n.machine.hidden = n.ctChip.hidden = true;      // as the skin builds them
  const bulb = { classList: { contains: (c) => c === bulbLvl } };
  const W = toolbarWords({ window: { readinessShown: (r) => r, ...win }, ...n, bulb, $: (q) => (q === '#hbReadyTxt' ? n.row : null),
    status_: () => st, stale_: () => stale, staleWhy_: () => why });
  W.words();
  return n;
}

test('desk skin: words() writes the machine chip, the readiness words and the chart-trading chip', () => {
  const acc = { a: { env: 'live' }, b: { env: 'live' }, c: { env: 'demo' } };
  const warn = { readiness: { checks: [{ label: 'feed', level: 'warn' }] } };
  let n = wordsOn({ st: { machine: 'server', chart_trading: { enabled: true }, accounts: acc, ...warn }, bulbLvl: 'warn' });
  assert.equal(n.machine.hidden, false); assert.equal(n.machine.dataset.m, 'server', 'the blue one');
  assert.equal(n.mLong.textContent, 'Server · Chicago'); assert.equal(n.mShort.textContent, 'Server'); assert.equal(n.machine.title, 'Server · Chicago');
  assert.equal(n.ctChip.hidden, false);
  assert.equal(n.ctLong.textContent, 'Chart trading ON · 2 live accounts'); assert.equal(n.ctShort.textContent, 'Chart ON · 2 live');
  assert.equal(n.readyBtn.textContent, '1 thing needs a look'); assert.equal(n.readyBtn.dataset.lvl, 'warn');
  assert.equal(n.readyBtn.attrs['aria-label'], 'Readiness: 1 thing needs a look');
  assert.equal(n.row.textContent, 'Needs attention', 'the inspector row: the bulb the page painted'); assert.equal(n.sum.dataset.lvl, 'warn');
  n = wordsOn({ st: { machine: 'server' }, win: { HB_MACHINE: 'mac' } });
  assert.equal(n.machine.hidden, false); assert.equal(n.machine.dataset.m, 'mac', 'the grey one'); assert.equal(n.mLong.textContent, 'This Mac');
  n = wordsOn({ st: { chart_trading: { enabled: false }, accounts: acc } });
  assert.equal(n.machine.hidden, true, 'no machine value: no chip'); assert.equal(n.ctChip.hidden, true, 'chart trading off: no chip');
  assert.match(DESK_SKIN, /syncing = true;\n      try \{\n        words\(\);/, 'every sync() writes the words first, before any view can throw');
  // the page's state is old: the toolbar word and the inspector's row say the same, whatever the bulb last said
  n = wordsOn({ st: { ...warn }, bulbLvl: 'ok', stale: true, why: 'the desk is not answering' });
  assert.equal(n.readyBtn.textContent, 'Desk not answering'); assert.equal(n.readyBtn.dataset.lvl, 'bad');
  assert.equal(n.row.textContent, 'Desk not answering', 'not "Ready to trade"'); assert.equal(n.sum.dataset.lvl, 'bad');
  n = wordsOn({ st: { ...warn }, bulbLvl: 'ok', stale: true, why: 'updates pause while a menu or a size edit is open' });
  assert.equal(n.readyBtn.textContent, 'Updates paused'); assert.equal(n.row.textContent, 'Updates paused'); assert.equal(n.sum.dataset.lvl, '');
});

// the straddle's RR field and stop menu (desk.js rrCtl), run on small fake nodes: what a pick and a Set send
function rrControls(setStratRr, D = { activeElement: null }) {
  const i = DESK_SKIN.indexOf('    const rrCtl = {'), j = DESK_SKIN.indexOf("rrCtl.btn.addEventListener('click', setRr);");
  assert.ok(i >= 0 && j > i, 'the RR controls block');
  const el = (tag, attrs = {}, ...kids) => {
    const on = {};
    const n = { tag, hidden: !!attrs.hidden, disabled: false, textContent: attrs.text || '', value: attrs.value || '', options: [], children: kids,
      isConnected: true, focus: () => { D.activeElement = n; }, addEventListener: (t, f) => { (on[t] = on[t] || []).push(f); }, fire: async (t, e = {}) => { for (const f of on[t] || []) await f(e); },
      append: (...k) => { n.children.push(...k); if (tag === 'select') n.options.push(...k); } };
    if (tag === 'select') { n.options = [...kids]; n.value = kids[0].value; }
    return n;
  };
  const c = vm.createContext({ el, D, window: { setStratRr } });
  vm.runInContext(DESK_SKIN.slice(i, j + "rrCtl.btn.addEventListener('click', setRr);".length) + '\nglobalThis.R = rrCtl;', c);
  return c.R;
}

/* every rule of the Desk tab's stylesheets, in load order, with the window widths it applies at
   (a width-free @media such as prefers-* is taken to apply at every width: the strict reading) */
function deskRules() {
  const out = [];
  for (const f of [...manifest.shared.css, ...manifest.tabs.desk.css]) {
    const css = read(f).replace(/\/\*[\s\S]*?\*\//g, '');
    (function walk(s, lo, hi) {
      let i = 0;
      while (i < s.length) {
        const open = s.indexOf('{', i);
        if (open < 0) break;
        let depth = 1, j = open + 1;
        while (j < s.length && depth) { if (s[j] === '{') depth++; else if (s[j] === '}') depth--; j++; }
        const head = s.slice(i, open).trim(), body = s.slice(open + 1, j - 1);
        if (/^@media\b/.test(head)) {
          const mx = head.match(/max-width:\s*(\d+)px/), mn = head.match(/min-width:\s*(\d+)px/);
          walk(body, mn ? Math.max(lo, +mn[1]) : lo, mx ? Math.min(hi, +mx[1]) : hi);
        } else if (!head.startsWith('@')) for (const sel of head.split(',')) out.push({ sel: sel.trim(), body, lo, hi });
        i = j;
      }
    })(css, 0, Infinity);
  }
  return out;
}

test('desk skin: the chart-trading chip and its count never hide at any window width the app allows (980 px up), and the column never changes width with its words', () => {
  const MIN_W = 980;   // the Mac app's window minimum (deploy/macapp main_apple.swift)
  const rules = deskRules();
  const on = (re, w) => rules.filter((r) => re.test(r.sel) && w >= r.lo && w <= r.hi);
  const last = (re, w, prop) => {
    let v = null;
    for (const r of on(re, w)) { const m = r.body.match(new RegExp(`(?:^|;|\\s)${prop}\\s*:\\s*([^;]+)`)); if (m) v = m[1].trim(); }
    return v;
  };
  // the chip, its column and every box around it: no display:none at any width the window can have
  for (const cls of ['hb-ct-chip', 'hb-rd-col', 'hb-rd-top', 'hb-desk-status', 'hb-status', 'hb-tb-r']) {
    const hid = rules.filter((r) => new RegExp(`\\.${cls}(?![\\w-])[^\\s]*$`).test(r.sel) && r.hi >= MIN_W && /display\s*:\s*none/.test(r.body));
    assert.deepEqual(hid.map((r) => `${r.sel} (to ${r.hi}px)`), [], `.${cls} is never hidden from ${MIN_W} px up`);
  }
  for (let w = MIN_W; w <= 2400; w += 1) {
    const long = last(/\.hb-ct-long$/, w, 'display'), short = last(/\.hb-ct-short$/, w, 'display');
    assert.equal([long !== 'none', short !== 'none'].filter(Boolean).length, 1, `${w} px: exactly one of the chip's long / short words shows`);
    assert.match(last(/\.hb-rd-col$/, w, 'width') || '', /^\d+px$/, `${w} px: the readiness column has a fixed width, so Arm and Kill never move`);
  }
  // the short words still carry the live-account count (the chip's whole point)
  assert.match(DESK_SKIN, /if \(short\) return 'Chart ON' \+ \(n \? ' · ' \+ n \+ ' live' : ''\)/);
  // the readiness word is what goes first in a narrow window, never the chip
  assert.equal(last(/\.hb-ready-word$/, MIN_W, 'display'), 'none');
  assert.notEqual(last(/\.hb-ready-word$/, 1440, 'display'), 'none');
});

/* The Desk toolbar, added up from its stylesheets: lead (sidebar corner) + main bar (padding, gaps, page switch, the right-hand group)
   + the gear corner's own items (machine chip, gear, inspector button) must fit the window with 8 px to spare, so Arm and Kill never
   reach the chip, the gear or the inspector button. Text widths: the system font at the CSS sizes, measured with CoreText (NSString size, 2026-10-27),
   rounded up. The window buttons' room (--hb-native-tl) is taken generous. */
test('desk skin: the toolbar fits at every window width from 980 px, either pane open or shut, with the widest machine chip', () => {
  const TXT = { Desk: 32, Charts: 41, Lab: 23, 'Server · Chicago': 91, Server: 36, 'This Mac': 49, '12 things need a look': 133, 'Desk not answering': 125,
                'Chart trading ON · 12 live accounts': 175, 'Chart ON · 12 live': 88 };
  const ICON = 24, TL = 92;      // a toolbar symbol (symbols.css --sf-sidebar-right-w), the window buttons' room
  const rules = deskRules();
  const htmlOk = (sel, on) => {      // the <html> state a selector asks for: pane classes only (a theme or other state: not the default)
    const h = sel.split(/\s+/)[0], not = [...h.matchAll(/:not\(\.([\w-]+)\)/g)].map((m) => m[1]), rest = h.replace(/:not\([^)]*\)/g, '');
    if (/[[:]/.test(rest)) return false;
    return [...rest.matchAll(/\.([\w-]+)/g)].every((m) => on.has(m[1])) && not.every((c) => !on.has(c));
  };
  const decls = (re, w, on) => rules.filter((r) => re.test(r.sel) && w >= r.lo && w <= r.hi && htmlOk(r.sel, on)).flatMap((r) => r.body.split(';'));
  const get = (re, w, on, prop) => { let v = null; for (const d of decls(re, w, on)) { const m = d.match(/^\s*([\w-]+)\s*:\s*(.+?)\s*$/); if (m && m[1] === prop) v = m[2].replace(/\s*!important$/, ''); } return v; };
  const ON = new Set(['hb-apple']);
  const cssVar = (n) => get(/^html\.hb-apple$/, 1400, ON, n);
  const px = (v) => {      // "12px", "calc(var(--a-side-w) + 8px)"
    v = String(v).replace(/var\((--a-(?:side|insp)-w)\)/g, (_, n) => cssVar(n)).replace(/var\(--hb-native-tl[^)]*\)/g, TL + 'px');
    const m = v.match(/^calc\((.+)\)$/);
    const n = (m ? m[1].split('+') : [v]).reduce((a, x) => a + parseFloat(x), 0);
    assert.ok(Number.isFinite(n), `a width the test can add up: ${v}`);
    return n;
  };
  const pad = (re, w, on) => {      // [left, right]
    let l = 0, r = 0;
    for (const d of decls(re, w, on)) {
      const m = d.match(/^\s*(padding(?:-left|-right)?)\s*:\s*(.+?)\s*$/);
      if (!m) continue;
      const v = m[2].split(/\s+/).map(parseFloat);
      if (m[1] === 'padding') { const [t, rr = t, , ll = rr] = v; l = ll; r = rr; } else if (m[1] === 'padding-left') l = v[0]; else r = v[0];
    }
    return [l, r];
  };
  const W = toolbarWords();
  // between two breakpoints every width is the same and the room left only grows with the window: each range's narrowest width
  const widths = [...new Set([980, ...rules.flatMap((r) => [r.lo, r.hi + 1])])].filter((w) => w >= 980 && w <= 2400).sort((x, y) => x - y);
  assert.ok(widths.includes(1201) && widths.includes(1021), 'the narrow windows\' breakpoints are read');
  for (const sideOff of [false, true]) for (const inspOff of [false, true]) for (const chip of [null, 'mac', 'server']) {
    const on = new Set(['hb-apple', ...(sideOff ? ['hb-side-off'] : []), ...(inspOff ? ['hb-insp-off'] : [])]);
    const state = `sidebar ${sideOff ? 'shut' : 'open'}, inspector ${inspOff ? 'shut' : 'open'}, chip ${chip || 'none'}`;
    for (const w of widths) {
      const g = (re, prop) => get(re, w, on, prop);
      // the page switch: three tabs (the Mac's Desk; the server app hides it)
      const [tl, tr] = pad(/\.hb-seg > a$/, w, on), tabMin = px(g(/\.hb-seg > a$/, 'min-width'));
      const seg = pad(/\.hb-seg$/, w, on).reduce((a, b) => a + b) + 2 * px(g(/\.hb-seg$/, 'gap')) + ['Desk', 'Charts', 'Lab'].reduce((a, t) => a + Math.max(tabMin, TXT[t] + tl + tr), 0);
      const centred = g(/\.hb-tb-c$/, 'position') === 'absolute';
      // the right-hand group: the readiness column and the armed state, then Arm, then Kill
      const rd = px(g(/\.hb-rd-col$/, 'width')), stc = px(g(/\.hb-st-col$/, 'width'));
      const rgap = px(g(/\.hb-tb-r$/, 'gap')), right = rd + px(g(/\.hb-(?:desk-)?status$/, 'gap')) + stc + rgap + px(g(/#armBtn$/, 'width')) + rgap + px(g(/#killBtn$/, 'width'));
      const [ml, mr] = pad(/\.hb-tb-main$/, w, on), mgap = px(g(/\.hb-tb-main$/, 'gap'));
      const inFlow = (g(/\.hb-tb-l$/, 'display') === 'none' ? 0 : 1) + (centred ? 0 : 1) + 1;
      const need = ml + mr + (inFlow - 1) * mgap + (centred ? 0 : seg) + right;
      // the gear corner's own items: the machine chip (long or short words), the gear, the inspector button
      const short = g(/\.hb-m-long$/, 'display') === 'none';
      assert.notEqual(short, g(/\.hb-m-short$/, 'display') === 'none', `${w} px: exactly one of the machine chip's words shows`);
      const [il, ir] = pad(/\.hb-tb-insp$/, w, on), igap = px(g(/\.hb-tb-insp$/, 'gap'));
      // the chip keeps one fixed room whatever it shows (none, This Mac, Server): Arm and Kill never move when it appears
      const chipW = px(g(/\.hb-machine$/, 'width'));
      assert.ok(chipW >= pad(/\.hb-machine$/, w, on).reduce((a, b) => a + b) + Math.max(...['mac', 'server'].map((m) => TXT[W.machineWord({ machine: m }, short)])), `${w} px: the chip's room holds its widest words`);
      const items = il + ir + chipW + igap + px(g(/#settingsBtn$/, 'width')) + igap + (ICON + pad(/\.hb-tbtn$/, w, on).reduce((a, b) => a + b));
      const zone = inspOff ? items : px(g(/\.hb-tb-insp$/, 'width'));
      const lead = px(g(/\.hb-tb-lead$/, 'width'));
      assert.ok(items <= zone, `${w} px, ${state}: the gear corner holds its own items`);
      // the room left between Kill and the gear corner's first item (the bar's own padding on both sides counts): 8 px at least
      const clear = w - lead - (need - mr) - (items - il);
      assert.ok(clear >= 8, `${w} px, ${state}: ${clear} px between Kill and the gear corner`);
      if (centred) assert.ok(w / 2 + seg / 2 + mgap <= w - zone - mr - right, `${w} px, ${state}: the centred page switch clears the right-hand group`);
      // the readiness column holds its widest words (anything wider would spill left over the page switch)
      assert.ok(rd >= (short ? TXT['Chart ON · 12 live'] : TXT['Chart trading ON · 12 live accounts']) + pad(/\.hb-ct-chip$/, w, on).reduce((a, b) => a + b), `${w} px: the chip fits its column`);
      if (g(/\.hb-ready-word$/, 'display') !== 'none') assert.ok(rd >= px(g(/\.bulb$/, 'width')) + px(g(/\.hb-rd-top$/, 'gap')) + Math.max(TXT['12 things need a look'], TXT['Desk not answering']), `${w} px: the readiness word fits its column`);
    }
  }
});

test('desk skin: the stop menu no longer saves on change -- a Set button names the change and sends the same call', async () => {
  const calls = [];
  let answer = '';
  const R = rrControls(async (...a) => { calls.push(a); return answer; });
  R.name = 'nq930';
  R.follow('5');      // the Desk's stop, as setup() sees it
  assert.equal(R.sl.value, '5'); assert.equal(R.slBtn.hidden, true, 'nothing to set');
  R.sl.value = '10'; await R.sl.fire('change');
  assert.deepEqual(calls, [], 'a pick alone sends nothing');
  assert.equal(R.slBtn.hidden, false); assert.equal(R.slBtn.textContent, 'Set 5 pts → 10 pts', 'the menu\'s own unit word');
  R.follow('5');      // a repaint while the pick waits keeps it
  assert.equal(R.sl.value, '10'); assert.equal(R.slBtn.hidden, false);
  await R.slBtn.fire('click');
  assert.deepEqual(calls.map((a) => [...a]), [['nq930', null, 10]], 'the same setStratRr(name, null, stop) as before');
  assert.equal(R.slBtn.hidden, true, 'saved: nothing left to set'); assert.equal(R.err.hidden, true);
  R.follow('10');
  assert.equal(R.sl.value, '10'); assert.equal(R.slBtn.hidden, true);
  // picking the Desk's own stop again hides the button; a refusal says why and goes back to the Desk's stop
  R.sl.value = '5'; await R.sl.fire('change'); R.sl.value = '10'; await R.sl.fire('change');
  assert.equal(R.slBtn.hidden, true);
  answer = 'the desk is armed';
  R.sl.value = '5'; await R.sl.fire('change'); await R.slBtn.fire('click');
  assert.deepEqual([...calls[1]], ['nq930', null, 5]);
  assert.equal(R.err.hidden, false); assert.equal(R.err.textContent, 'the desk is armed');
  assert.equal(R.sl.value, '10'); assert.equal(R.slBtn.hidden, true);
  // a stop set elsewhere (not 5 or 10) shows as it is; the RR field's Set is unchanged: setStratRr(name, rr)
  R.follow('7.5'); assert.equal(R.sl.value, '7.5');
  R.input.value = '2'; await R.btn.fire('click');
  assert.deepEqual([...calls[2]], ['nq930', 2]);
});

test('desk skin: a stop pick waiting for its Set never carries over to another strategy, and a keyboard Set keeps the focus', async () => {
  const calls = [], D = { activeElement: null };
  const R = rrControls(async (...a) => { calls.push(a); return ''; }, D);
  R.name = 'nq930'; R.follow('5');
  R.sl.value = '10'; await R.sl.fire('change');
  assert.equal(R.slBtn.hidden, false, 'nq930: a pick waits');
  // another strategy opens: setup() forgets the Desk's stop it last saw, then follows the new one's
  assert.match(DESK_SKIN, /if \(rrCtl\.name !== name\) \{ rrCtl\.name = name; rrCtl\.dirty = false; rrCtl\.err\.hidden = true; rrCtl\.slCur = null; \}/);
  R.name = 'es930'; R.slCur = null; R.follow('5');
  assert.equal(R.sl.value, '5', 'es930 shows its own stop, not nq930\'s pick'); assert.equal(R.slBtn.hidden, true, 'nothing to set');
  assert.deepEqual(calls, []);
  // a Set reached by keyboard: once saved the button hides, and the focus goes back to the menu (never lost to the page)
  R.sl.value = '10'; await R.sl.fire('change');
  R.slBtn.focus(); await R.slBtn.fire('click');
  assert.deepEqual([...calls[0]], ['es930', null, 10]);
  assert.equal(R.slBtn.hidden, true); assert.equal(D.activeElement, R.sl);
  // a mouse Set (the focus elsewhere) leaves the focus where it is
  R.follow('10'); R.sl.value = '5'; await R.sl.fire('change');
  D.activeElement = null; await R.slBtn.fire('click');
  assert.equal(D.activeElement, null);
});

test('desk skin: the research heading names the route from the record itself -- 3:1 test months or the old record, never "OOS"', () => {
  const { researchWord } = toolbarWords();
  assert.equal(researchWord({ walkforward: true, unseen: {} }, false), '3:1 test months');
  assert.equal(researchWord({ walkforward: true, unseen_state: 'pending' }, false), '3:1 test months', 'a 3:1 record still running is still the 3:1');
  assert.equal(researchWord({ walkforward: true, build: {}, both: {} }, true), '3:1 in-sample · test months', 'with its in-sample column');
  for (const rec of [{ unseen: {} }, { walkforward: false, unseen: {} }, { walkforward: 'true', build: {} }, { build: {} }]) {
    for (const cols of [false, true]) assert.equal(researchWord(rec, cols), 'Old record (before 3:1)');
  }
  for (const rec of [undefined, null, 'x']) assert.equal(researchWord(rec, false), 'Results', 'not read yet: no route claimed');
  // an old-route record with no run at all (a built-in twin never run) is no record: no "Old record" over "Not run…"
  for (const rec of [{ unseen: null, manual: true }, { walkforward: false }, { unseen_state: 'pending' }]) assert.equal(researchWord(rec, false), 'Results');
  assert.doesNotMatch(DESK_SKIN, /OOS|Unseen days/, 'the retired route\'s words are gone from the skin');
  assert.match(DESK_SKIN, /researchWord\(recordOf\(grp, dl, name\), !!\$\('\.fh', u\)\)/, 'the heading comes from the record, not the page\'s old title');
});

test('desk skin: the research heading reads the record the page drew -- a group by id, a Desk Lab strategy by its Lab name, the rest by name', () => {
  const DESKRES = { nq930: { walkforward: false, unseen: {} }, vbp_mid5: { walkforward: true, unseen: {} }, lab_vbp_mid5: { unseen: {} } };
  const DESKGRES = { g5: { walkforward: true, unseen: {} }, nq930: { walkforward: true } };
  const { recordOf } = toolbarWords({ DESKRES, DESKGRES });
  assert.equal(recordOf({ id: 'g5' }, null, 'g5'), DESKGRES.g5, 'a group: DESKGRES by its id (groupView)');
  assert.equal(recordOf(null, { lab: { name: 'vbp_mid5' } }, 'lab_vbp_mid5'), DESKRES.vbp_mid5, 'a Desk Lab strategy: by its Lab name, not its desk id');
  assert.equal(recordOf(null, null, 'vbp_mid5'), DESKRES.vbp_mid5, 'a Lab strategy: by the view\'s name');
  assert.equal(recordOf(null, null, 'nq930'), DESKRES.nq930, 'a built-in twin: by its name, never the group of the same name');
  assert.equal(recordOf(null, null, 'gone'), null);
  assert.equal(recordOf({ id: 'gone' }, null, 'gone'), null);
  assert.equal(toolbarWords().recordOf(null, null, 'nq930'), null, 'before the page has its records: none, no throw');
  // the page still keys them so
  const page = read('index.html');
  assert.match(page, /DeskLab\.groupPage\(g, DESKGRES\[g\.id\]\)/);
  assert.match(page, /labResHtml\(row\.name, name\)/);
  assert.match(page, /DeskLab\.results\(DESKRES\[lab\]\)/);
});

test('desk skin: the sidebar hides its rows\' second lines but the Activity row\'s ("N things need a look")', () => {
  const css = read('apple/desk.css');
  assert.match(css, /html\.hb-apple \.hb-side \.item \.it small \{ display: none; \}/, 'other rows stay one line');
  assert.match(css, /html\.hb-apple \.hb-side \.item\[onclick\^="setView\('activity'\)"\] \.it small \{ display: block;/, 'the Activity row shows it');
  assert.match(read('index.html'), /onclick="setView\('activity'\)"[^`]*<small>\$\{issues \? plural\(issues, "thing needs", "things need"\) \+ " a look"/, 'the page still writes it there');
});
