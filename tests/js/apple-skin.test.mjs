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
                    'viewToday', 'viewStrat', 'viewActivity', 'themeToggle'])
    assert.ok(page.includes(`id="${id}"`) && skin.includes(`#${id}`), `#${id} is expected by the skin and present in the page`);
  for (const cls of ['pill-slot', 'app-main', 'frame', 'inset-topbar']) assert.ok(page.includes(cls), `.${cls} is in the page`);
  for (const fn of ['openChecks', 'setStratRr']) assert.match(page, new RegExp(`function ${fn}\\(`), `${fn}() is the page's own`);
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
  vm.runInContext(DESK_SKIN.slice(i, j) + '\nglobalThis.W = { machineWord, readyWord, chartWords };', c);
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
  assert.match(DESK_SKIN, /el\('span', \{ class: 'hb-machine', hidden: true \}\)/, 'the chip starts hidden');
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
  assert.match(DESK_SKIN, /el\('span', \{ class: 'hb-ct-chip', hidden: true/, 'the chip starts hidden');
});

// the straddle's RR field and stop menu (desk.js rrCtl), run on small fake nodes: what a pick and a Set send
function rrControls(setStratRr) {
  const i = DESK_SKIN.indexOf('    const rrCtl = {'), j = DESK_SKIN.indexOf("rrCtl.btn.addEventListener('click', setRr);");
  assert.ok(i >= 0 && j > i, 'the RR controls block');
  const el = (tag, attrs = {}, ...kids) => {
    const on = {};
    const n = { tag, hidden: !!attrs.hidden, disabled: false, textContent: attrs.text || '', value: attrs.value || '', options: [], children: kids,
      addEventListener: (t, f) => { (on[t] = on[t] || []).push(f); }, fire: async (t, e = {}) => { for (const f of on[t] || []) await f(e); },
      append: (...k) => { n.children.push(...k); if (tag === 'select') n.options.push(...k); } };
    if (tag === 'select') { n.options = [...kids]; n.value = kids[0].value; }
    return n;
  };
  const c = vm.createContext({ el, window: { setStratRr } });
  vm.runInContext(DESK_SKIN.slice(i, j + "rrCtl.btn.addEventListener('click', setRr);".length) + '\nglobalThis.R = rrCtl;', c);
  return c.R;
}

test('desk skin: the stop menu no longer saves on change -- a Set button names the change and sends the same call', async () => {
  const calls = [];
  let answer = '';
  const R = rrControls(async (...a) => { calls.push(a); return answer; });
  R.name = 'nq930';
  R.follow('5');      // the Desk's stop, as setup() sees it
  assert.equal(R.sl.value, '5'); assert.equal(R.slBtn.hidden, true, 'nothing to set');
  R.sl.value = '10'; await R.sl.fire('change');
  assert.deepEqual(calls, [], 'a pick alone sends nothing');
  assert.equal(R.slBtn.hidden, false); assert.equal(R.slBtn.textContent, 'Set 5 pt → 10 pt');
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
