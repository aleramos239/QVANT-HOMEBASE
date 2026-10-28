import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
import { createRequire } from 'node:module';
import { HTML } from './deskpage.mjs';

/* Keyboard and focus (design package 3): the real stylesheets and scripts are read as text and the rules asserted.
     - a closed side pane leaves the Tab order (visibility hidden AFTER the slide, so the slide still plays), the Charts order dock excepted;
     - the Desk segmented buttons show the skin's ring and say which one is pressed;
     - the Lab menus walk with the arrow keys, and Escape closes only the menu on top;
     - one ring recipe: the global one, never a second ring beside it;
     - small targets reach 28 px by an invisible extension, their visible size untouched;
     - the Charts and Lab animations that lacked a prefers-reduced-motion line have one. */
const STATIC = new URL('../../homebase/static/', import.meta.url);
const rd = (p) => readFileSync(new URL(p, STATIC), 'utf8');

/* a stylesheet as [{ media, sels, d }]: comments stripped, @media entered (its text kept), @keyframes skipped; d is prop -> value */
function parse(css) {
  css = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const out = [];
  (function walk(s, media) {
    let i = 0;
    while (i < s.length) {
      const open = s.indexOf('{', i);
      if (open < 0) break;
      let depth = 1, j = open + 1;
      while (j < s.length && depth) { if (s[j] === '{') depth++; else if (s[j] === '}') depth--; j++; }
      const head = s.slice(i, open).trim(), body = s.slice(open + 1, j - 1);
      if (/^@(media|supports)\b/.test(head)) walk(body, head);
      else if (!head.startsWith('@')) {
        const d = {};
        for (const m of body.matchAll(/([\w-]+)\s*:\s*((?:[^;(]|\([^)]*\))*)/g)) d[m[1]] = m[2].trim();
        out.push({ media, sels: head.split(/,(?![^(]*\))/).map((x) => x.trim()), d });
      }
      i = j;
    }
  })(css, '');
  return out;
}
const REDUCE = /prefers-reduced-motion:\s*reduce/;
const rule = (css, sel, media) => parse(css).find((r) => r.sels.includes(sel) && (media === undefined || (media === 'reduce' ? REDUCE.test(r.media) : !r.media)));
const need = (css, sel, media) => { const r = rule(css, sel, media); assert.ok(r, `no rule for ${sel}${media === 'reduce' ? ' in a reduced-motion block' : ''}`); return r; };
const SLIDE = /transform 320ms var\(--a-spring\), opacity 200ms ease, visibility 0s linear 320ms/;

const SYSTEM = rd('apple/system.css'), ALAB = rd('apple/lab.css'), ACHARTS = rd('apple/charts.css'), DESKCSS = rd('apple/desk.css');
const LABCSS = rd('charts/lab.css'), CHARTSCSS = rd('charts/charts.css');

/* ---- closed panes leave the Tab order ------------------------------------------------------------------------------ */
test('a closed Mac sidebar and inspector are hidden AFTER their slide: out of the Tab order, the slide intact, the order dock untouched', () => {
  const side = need(SYSTEM, 'html.hb-apple.hb-side-off .hb-side', undefined);
  assert.equal(side.d.visibility, 'hidden');
  assert.match(side.d.transition, SLIDE, 'visibility waits for the 320 ms slide');
  assert.match(side.d.transform, /translateX/);
  assert.equal(side.d.opacity, '0');
  const insp = need(SYSTEM, 'html.hb-apple.hb-insp-off .hb-insp:not(#pdock)', undefined);
  assert.equal(insp.d.visibility, 'hidden');
  assert.match(insp.d.transition, SLIDE);
  assert.equal(insp.d.transform, 'translateX(100%)');
  // the Charts order dock is the .hb-insp there; it is not hidden by this rule
  assert.ok(!parse(SYSTEM).some((r) => r.sels.some((s) => /hb-insp-off \.hb-insp$/.test(s)) && r.d.visibility), 'a bare .hb-insp rule would hide the order dock');
  // opening again shows it at once: the base rules keep no visibility
  assert.equal(need(SYSTEM, 'html.hb-apple .hb-side', undefined).d.visibility, undefined);
  assert.equal(need(SYSTEM, 'html.hb-apple .hb-insp', undefined).d.visibility, undefined);
});

test('the Lab panes (Mac skin) hide the same way, and the reduced-motion blocks turn the delayed transition off again', () => {
  const lib = need(ALAB, 'html.hb-apple.hb-side-off #labLib.hb-side', undefined);
  assert.equal(lib.d.visibility, 'hidden');
  assert.match(lib.d.transition, SLIDE);
  const res = need(ALAB, 'html.hb-apple.hb-insp-off #labRes.hb-insp', undefined);
  assert.equal(res.d.visibility, 'hidden');
  assert.match(res.d.transition, SLIDE);
  assert.equal(res.d.transform, 'translateX(100%)', 'the slide-out is still there');
  // a rule that sets a transition on the off state must be switched off again for people who asked for less motion
  const reduce = (css, sel) => assert.equal(need(css, sel, 'reduce').d.transition, 'none', sel);
  reduce(SYSTEM, 'html.hb-apple.hb-side-off .hb-side');
  reduce(SYSTEM, 'html.hb-apple.hb-insp-off .hb-insp:not(#pdock)');
  reduce(ALAB, 'html.hb-apple.hb-side-off #labLib.hb-side');
  reduce(ALAB, 'html.hb-apple.hb-insp-off #labRes.hb-insp');
});

test('the plain Lab panes (no Mac skin) hide the same way', () => {
  const lib = need(LABCSS, '.lab[data-lib="0"] .lab-lib', undefined), res = need(LABCSS, '.lab[data-res="0"] #labRes', undefined);
  for (const r of [lib, res]) {
    assert.equal(r.d.visibility, 'hidden');
    assert.match(r.d.transition, /width 320ms var\(--hb-spring\), margin 320ms var\(--hb-spring\), opacity 180ms ease, transform 320ms var\(--hb-spring\), visibility 0s linear 320ms/);
  }
  assert.equal(need(LABCSS, '.lab[data-lib="0"] .lab-lib', 'reduce').d.transition, 'none');
  assert.equal(need(LABCSS, '.lab[data-res="0"] #labRes', 'reduce').d.transition, 'none');
});

/* ---- Desk segmented buttons ---------------------------------------------------------------------------------------- */
test('Desk segmented buttons keep the skin\'s one focus ring (no outline:none on .seg button) and the ring is the global one', () => {
  assert.equal(need(DESKCSS, 'html.hb-apple .seg button', undefined).d.outline, undefined);
  assert.equal(need(DESKCSS, 'html.hb-apple .seg button.sel', undefined).d.outline, undefined);
  assert.equal(need(SYSTEM, 'html.hb-apple :focus-visible', undefined).d.outline, '3.5px solid var(--a-focus)');
  assert.equal(need(DESKCSS, 'html.hb-apple .seg button.sel', undefined).d['box-shadow'], 'none', 'the selected look is unchanged');
});

test('Desk segmented buttons say which one is pressed: Demo/Live, market data (aria-pressed); the clock and Shadow/Live already did', () => {
  assert.match(HTML, /<button class="sel" type="button" id="envDemo" aria-pressed="true" onclick="setEnv\('demo'\)">/);
  assert.match(HTML, /<button type="button" id="envLive" aria-pressed="false" onclick="setEnv\('live'\)">/);
  // setEnv keeps it in step with .sel
  const f = HTML.slice(HTML.indexOf('function setEnv('), HTML.indexOf('function setEnv(') + 1200);
  const code = f.slice(0, f.indexOf('\n}\n') + 3);
  const els = {};
  const el = (id) => (els[id] ||= { _a: {}, classList: { toggle() {} }, setAttribute(k, v) { this._a[k] = v; }, style: {}, set textContent(v) {}, set innerHTML(v) {} });
  const ctx = vm.createContext({ WIZ: { env: 'demo', saved: null }, $: (s) => el(s.slice(1)), esc: (x) => x });
  vm.runInContext(`${code}\nglobalThis.setEnv = setEnv;`, ctx);
  ctx.setEnv('live');
  assert.equal(els.envLive._a['aria-pressed'], 'true');
  assert.equal(els.envDemo._a['aria-pressed'], 'false');
  ctx.setEnv('demo');
  assert.equal(els.envLive._a['aria-pressed'], 'false');
  assert.equal(els.envDemo._a['aria-pressed'], 'true');
  // the market-data choices
  const md = HTML.slice(HTML.indexOf('function marketDataSection()'), HTML.indexOf('let mdSig'));
  const c2 = vm.createContext({ MD_REACHABLE: true, MD: { md: 'paper', accounts: {} }, MD_STAGED: 'live', MD_BUSY: false, MD_ERR: '', MD_FEED: null, esc: (x) => String(x), machineWords: () => '',
    MD_CHOICES: [{ value: 'live', label: 'Live' }, { value: 'paper', label: 'Paper' }], labelOfMd: (x) => x });
  vm.runInContext(`${md}\nglobalThis.html = marketDataSection();`, c2);
  const btns = [...c2.html.matchAll(/<button type="button" class="([^"]*)" data-md="(\w+)"([^>]*)>/g)];
  assert.equal(btns.length, 2);
  for (const [, cls, v, rest] of btns) assert.match(rest, new RegExp(`aria-pressed="${v === 'live'}"`), `${v} (${cls})`);
});

test('Desk seg buttons keep keyboard focus after a press re-renders them (market data)', () => {
  const f = HTML.slice(HTML.indexOf('function renderMarketData()'), HTML.indexOf('/* The clock:'));
  const focused = [];
  const btn = { dataset: { md: 'live' }, focus(o) { focused.push(['live', o]); }, addEventListener(t, fn) { this.click = fn; } };
  const root = { set innerHTML(v) {}, querySelectorAll: () => [btn], querySelector: (q) => (q === 'button[data-md="live"]' ? btn : null) };
  const ctx = vm.createContext({ $: (s) => (s === '#settingsMarketData' ? root : null), MD_REACHABLE: true, MD: { md: 'paper' }, MD_STAGED: 'paper', MD_BUSY: false, MD_ERR: '', MD_FEED: null,
    machineWords: () => '', marketDataSection: () => '', applyMd() {} });
  vm.runInContext(`let mdSig = null;\n${f}\nglobalThis.render = renderMarketData; globalThis.staged = () => MD_STAGED;`, ctx);
  ctx.render();
  btn.click();
  assert.equal(ctx.staged(), 'live');
  assert.equal(focused.length, 1, 'the pressed button gets the keyboard back');
});

test('Desk seg buttons keep keyboard focus when the clock choice is rebuilt', () => {
  const f = HTML.slice(HTML.indexOf('function renderClock()'), HTML.indexOf('function renderSettings()'));
  let got = null;
  const btn = { dataset: { clock: '24h' }, focus() { got = '24h'; } };
  const root = { dataset: { f: '12h' }, set innerHTML(v) {}, contains: (x) => x === btn, querySelectorAll: () => [], querySelector: (q) => (q === 'button[data-clock="24h"]' ? btn : null) };
  const ctx = vm.createContext({ $: () => root, HBClock: { format: '24h' }, document: { activeElement: btn }, toast() {} });
  vm.runInContext(`${f}\nglobalThis.render = renderClock;`, ctx);
  ctx.render();
  assert.equal(got, '24h');
});

test('closing a side pane with the keyboard inside it moves focus to its toolbar button', () => {
  const sh = rd('apple/shell.js');
  const code = sh.slice(sh.indexOf('const PANES = '), sh.indexOf('// narrow windows start'));
  const cls = new Set();
  const H = { classList: { contains: (c) => cls.has(c), toggle: (c, on) => (on ? cls.add(c) : cls.delete(c)) } };
  const inPane = { contains: (x) => x === inside };
  const inside = {}, btn = { focus() { btn.got = true; }, setAttribute() {} };
  const D = { activeElement: inside, querySelector: (q) => (q === '.hb-side' ? inPane : null) };
  const ctx = vm.createContext({ H, D, set() {}, window: { dispatchEvent() {} }, Event: function () {}, setTimeout() {} });
  vm.runInContext(`${code}\nPANES.sidebar.btn = btn_; globalThis.toggle = toggle;`.replace('btn_', 'globalThis.btn'), Object.assign(ctx, { btn }));
  ctx.toggle('sidebar', false);
  assert.equal(btn.got, true);
  btn.got = false; D.activeElement = {};
  ctx.toggle('sidebar', true); ctx.toggle('sidebar', false);
  assert.equal(btn.got, false, 'focus elsewhere is left alone');
});

/* ---- Lab menus: arrows and Escape ---------------------------------------------------------------------------------- */
function labMenus() {
  const LAB = rd('charts/lab.js');
  const a = LAB.indexOf('let overlay = null, menuEl = null'), b = LAB.indexOf('async function newMenu');
  const code = LAB.slice(a, b);
  const handlers = [];
  const doc = { activeElement: null, body: { appendChild() {} }, addEventListener: (t, f) => handlers.push([t, f]), querySelectorAll: () => [],
    createElement: () => {
      const e = { className: '', style: { setProperty() {} }, isConnected: true, dataset: {},
        set innerHTML(html) { e._html = html; e.items = [...html.matchAll(/<button\b[^>]*>/g)].map((m) => ({ disabled: /\bdisabled\b/.test(m[0]), focus() { doc.activeElement = this; }, tag: m[0] })); },
        get innerHTML() { return e._html; },
        firstElementChild: { querySelector: () => null, setAttribute() {}, focus() { doc.activeElement = this; } },
        addEventListener() {}, remove() { e.isConnected = false; }, contains: (x) => e.items.includes(x),
        querySelectorAll: (s) => (s === 'button' ? e.items : []), getBoundingClientRect: () => ({ left: 10, right: 60, top: 10, bottom: 30, width: 50, height: 60 }) };
      return e;
    } };
  const ctx = vm.createContext({ document: doc, window: { HBChartMenu: { step: createRequire(import.meta.url)('../../homebase/static/charts/chartmenu.js').step } },
    innerWidth: 1400, innerHeight: 900, root: { querySelectorAll: () => [] }, SP: null });
  vm.runInContext(`${code}\nglobalThis.api = { menu, dialog, closeMenu, closeDialog, open: () => !!menuEl, sheet: () => !!overlay, items: () => menuEl.items };`, ctx);
  const key = (k, target = { closest: () => null }) => { const e = { key: k, target, prevented: false, preventDefault() { this.prevented = true; } };
    for (const [t, f] of handlers) if (t === 'keydown') f(e); return e; };
  return { api: ctx.api, doc, key };
}
const ANCHOR = { getBoundingClientRect: () => ({ left: 10, right: 60, top: 10, bottom: 30 }), focus() { this.doc.activeElement = this; }, isConnected: true };

test('Lab menus: ArrowDown/ArrowUp/Home/End walk the enabled items (and wrap), a typing target keeps its arrows', () => {
  const { api, doc, key } = labMenus();
  ANCHOR.doc = doc;
  api.menu(ANCHOR, '<button data-pick="a">A</button><button data-pick="b" disabled>B</button><button data-pick="c">C</button>', () => {});
  const [a, , c] = api.items();
  assert.equal(key('ArrowDown').prevented, true);
  assert.equal(doc.activeElement, a);
  key('ArrowDown');
  assert.equal(doc.activeElement, c, 'the disabled item is skipped');
  key('ArrowDown');
  assert.equal(doc.activeElement, a, 'wraps');
  key('ArrowUp');
  assert.equal(doc.activeElement, c);
  key('Home');
  assert.equal(doc.activeElement, a);
  key('End');
  assert.equal(doc.activeElement, c);
  const typing = key('ArrowDown', { closest: () => ({}) });
  assert.equal(typing.prevented, false, 'a text field keeps its own arrow keys');
  assert.equal(doc.activeElement, c);
});

test('Lab menus: arrows do nothing when no menu is open', () => {
  const { doc, key } = labMenus();
  const e = key('ArrowDown');
  assert.equal(e.prevented, false);
  assert.equal(doc.activeElement, null);
});

test('Lab menus: Escape closes only the menu on top (the sheet beneath stays), the next Escape closes the sheet; focus goes back to the opener', () => {
  const { api, doc, key } = labMenus();
  ANCHOR.doc = doc;
  api.dialog('<h2>x</h2>');
  assert.equal(api.sheet(), true);
  api.menu(ANCHOR, '<button data-pick="a">A</button><button data-pick="b">B</button>', () => {});
  key('ArrowDown');
  assert.equal(api.open(), true);
  key('Escape');
  assert.equal(api.open(), false, 'the menu closed');
  assert.equal(api.sheet(), true, 'the sheet did not');
  assert.equal(doc.activeElement, ANCHOR, 'the keyboard returns to the button that opened the menu');
  key('Escape');
  assert.equal(api.sheet(), false);
});

/* ---- one focus ring ------------------------------------------------------------------------------------------------ */
test('one ring: the Lab fields and rows no longer get the page\'s accent shadow beside the skin\'s ring', () => {
  const fields = '.bp-f select, .tk-find input, .lb-tools select, .mix-q, .mix-size, .mix-rule select, .ab-pick select, .ab-pick .ab-q'.split(', ');
  const sel = (f) => `html.hb-apple ${f}:focus:not(.bad):not(.none)`;
  const r = parse(ALAB).find((x) => x.sels.includes(sel(fields[0])));
  assert.ok(r, 'a field rule');
  for (const f of fields) assert.ok(r.sels.includes(sel(f)), f);
  assert.deepEqual([r.d.outline, r.d['outline-offset'], r.d['box-shadow']], ['3.5px solid var(--a-focus)', '0', 'none']);
  // the rows and chips of a scrolling list: the global ring, drawn inside so the list's edge does not cut it
  const rows = parse(ALAB).find((x) => x.sels.includes('html.hb-apple .tk-row:focus-visible'));
  assert.ok(rows, 'a row rule');
  for (const f of ['.tk-row', '.tk-jump button', '.tk-src']) assert.ok(rows.sels.includes(`html.hb-apple ${f}:focus-visible`), f);
  assert.deepEqual([rows.d['outline-offset'], rows.d['box-shadow']], ['-3px', 'none']);
  // a picked heat-map cell keeps its marker while focused: only the unpicked ones lose the shadow
  const heat = parse(ALAB).find((x) => x.sels.includes('html.hb-apple .heat-c:not(.sel):focus-visible'));
  assert.ok(heat);
  assert.deepEqual([heat.d['outline-offset'], heat.d['box-shadow']], ['-3px', 'none']);
  assert.ok(!parse(ALAB).some((x) => x.sels.some((s) => /\.heat-c\.sel/.test(s)) && x.d['box-shadow'] === 'none'));
});

test('one ring: a ring rule that only repeats the global one is gone; the owner\'s three per-component rings stay as they are', () => {
  const GLOBAL = '3.5px solid var(--a-focus)';
  const same = (css, sel) => parse(css).filter((r) => r.sels.includes(sel) && r.d.outline === GLOBAL && r.d['outline-offset'] === '0');
  assert.deepEqual(same(ALAB, 'html.hb-apple .lab-page .btn:focus-visible'), []);
  const btn = need(DESKCSS, 'html.hb-apple .btn:focus-visible', undefined);
  assert.equal(btn.d.outline, undefined);
  assert.deepEqual([btn.d['box-shadow'], btn.d['border-color']], ['none', 'transparent'], 'what else it does stays');
  // left alone on purpose (the owner decides): .sh-t, the calendar's picked cell, .lb-view
  assert.equal(need(DESKCSS, 'html.hb-apple .hb-side .sh-t:focus-visible', undefined).d.outline, '2px solid var(--a-accent)');
  assert.equal(need(DESKCSS, 'html.hb-apple .cal-cell.pick:focus-visible', undefined).d.outline, '2px solid var(--a-accent)');
  assert.equal(need(ALAB, 'html.hb-apple #labLib .lb-view:focus-visible', undefined).d.outline, '2px solid var(--a-accent)');
});

/* ---- small targets ------------------------------------------------------------------------------------------------- */
const px = (v) => parseFloat(v);
test('toast close, menu delete and the library "..." reach 28 px by an invisible ::after; their visible size does not move', () => {
  // toast close: 20 x 20, extension 4 on every side (charts.css serves the plain skin, the Mac skin and the Lab)
  const x = need(CHARTSCSS, '.toast-x', undefined), xa = need(CHARTSCSS, '.toast-x::after', undefined);
  assert.deepEqual([x.d.width, x.d.height, x.d.position], ['20px', '20px', 'relative']);
  assert.deepEqual([xa.d.content, xa.d.position, xa.d.inset], ['""', 'absolute', '-4px']);
  assert.ok(px(x.d.width) + 2 * 4 >= 28);
  // menu delete in the Mac skin: 20 x 20
  const del = need(ACHARTS, 'html.hb-apple .menu-del', undefined), dela = need(ACHARTS, 'html.hb-apple .menu-del::after', undefined);
  assert.deepEqual([del.d.width, del.d.height, del.d.position], ['20px', '20px', 'relative']);
  // up, down and right only: the label on its left is a different action (pick), so the delete never reaches over it
  assert.deepEqual([dela.d.content, dela.d.position, dela.d.inset], ['""', 'absolute', '-4px -4px -4px 0']);
  // library "...": 22 x 19 (rows), 28 x 28 with the extension; a section header's sits at the top edge, so it grows sideways and down only
  const more = need(ALAB, 'html.hb-apple #labLib .lb-more', undefined), morea = need(ALAB, 'html.hb-apple #labLib .lb-more::after', undefined);
  assert.deepEqual([more.d.width, more.d.height], ['22px', '19px']);
  assert.deepEqual([morea.d.content, morea.d.position, morea.d.inset], ['""', 'absolute', '-4.5px -3px']);
  const [v, h] = morea.d.inset.split(' ').map(px);
  assert.ok(22 + 2 * -h >= 28 && 19 + 2 * -v >= 28);
  const ghead = need(ALAB, 'html.hb-apple #labLib .lb-gh .lb-more::after', undefined);
  assert.equal(ghead.d.inset, '0 -3px -9px');
  // the ::after is the only thing added: no pointer-less or visible fill
  for (const r of [xa, dela, morea, ghead]) assert.equal(r.d.background, undefined);
});

/* ---- reduced motion ------------------------------------------------------------------------------------------------ */
test('reduced motion: the Charts and Lab switches, the run-settings chevron, the progress bar width, the news flash and the smooth scroll are covered', () => {
  const sel = (css, s) => need(css, s, 'reduce').d.transition;
  assert.equal(sel(ACHARTS, 'html.hb-apple .switch'), 'none');
  assert.equal(sel(ACHARTS, 'html.hb-apple .switch::after'), 'none');
  assert.equal(sel(CHARTSCSS, '.switch::after'), 'none');
  assert.equal(sel(CHARTSCSS, '.hb-news-row.breaking'), 'none');
  assert.equal(sel(ALAB, 'html.hb-apple #labRes .rs-set > summary::after'), 'none');
  assert.equal(sel(LABCSS, '.rs-bar i'), 'none');
  // every one of them really has a transition to switch off
  assert.match(need(ACHARTS, 'html.hb-apple .switch::after', undefined).d.transition, /240ms/);
  assert.match(need(ALAB, 'html.hb-apple #labRes .rs-set > summary::after', undefined).d.transition, /200ms/);
  assert.match(need(LABCSS, '.rs-bar i', undefined).d.transition, /300ms/);
  const LAB = rd('charts/lab.js');
  assert.match(LAB, /behavior: matchMedia\('\(prefers-reduced-motion: reduce\)'\)\.matches \? 'auto' : 'smooth'/);
  assert.doesNotMatch(LAB, /behavior: 'smooth'/);
});

test('the pins follow: every edited script and skin file has its new version', () => {
  const man = JSON.parse(rd('apple/manifest.json'));
  assert.equal(man.version, 55);
  assert.match(rd('backtest.html'), /charts\/lab\.js\?v=138"/);
  assert.match(rd('backtest.html'), /charts\/lab\.css\?v=89"/);
  assert.match(rd('backtest.html'), /charts\/charts\.css\?v=60"/);
  assert.match(rd('charts.html'), /charts\/charts\.css\?v=69"/);
});
