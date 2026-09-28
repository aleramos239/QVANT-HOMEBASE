import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

/* The desk page's (homebase/static/index.html, :8850) master controls -- ARMED/DISARMED, Arm/Disarm
   and the press-and-hold Kill everything -- un-buried from Settings into the top bar (2026-09-28,
   Apple-design audit S2). The inline block runs for real in a vm sandbox (the deskpaper /
   desksettings technique) with a fake clock, so a hold is driven event by event:
     - the handlers are the SAME as before: Arm confirms, Disarm is immediate, Kill keeps its
       confirm; the same POSTs to /api/arm and /api/kill, nothing else, never fetch;
     - Kill fires only after HOLD_MS held without a break, exactly once per hold: letting go,
       dragging off, pointercancel, lost buttons, a context menu, blur and a hidden page cancel;
     - a key's auto-repeat never starts, restarts or fires a hold (GOTCHAS: a held key has sent
       duplicate orders here before). */
const HTML = readFileSync(new URL('../../homebase/static/index.html', import.meta.url), 'utf8');
const BLOCK = HTML.slice(
  HTML.indexOf('/* ---- master controls (top bar)'),
  HTML.indexOf('/* ---- the bulb ---- */'));

async function tick(n = 12) { for (let i = 0; i < n; i++) await Promise.resolve(); }

function fakeEl() {
  const listeners = {};
  return {
    listeners,
    textContent: '', className: '', title: '', onclick: null,
    style: { _p: {}, display: '', setProperty(k, v) { this._p[k] = v; } },
    classList: {
      _s: new Set(),
      add(c) { this._s.add(c); },
      remove(c) { this._s.delete(c); },
      contains(c) { return this._s.has(c); },
    },
    addEventListener(type, fn) { (listeners[type] ||= []).push(fn); },
  };
}

const KILL_OK = { ok: true, armed: false, strategies: {}, results: {
  a1: { cancel_all: { ok: true, error: null }, flatten_all: { ok: true, error: null } },
  a2: { cancel_all: { ok: true, error: null }, flatten_all: { ok: true, error: null } } } };

function load({ st = { armed: false }, stale = false, confirm = true, answer = KILL_OK, demo = false } = {}) {
  const els = { statusPill: fakeEl(), armBtn: fakeEl(), killBtn: fakeEl() };
  const posts = [], toasts = [], confirms = [], refreshes = [], fetched = [], alerts = [];
  const win = fakeEl(), doc = fakeEl();
  doc.hidden = false;
  // a fake clock: setTimeout/clearTimeout run only when the test advances time
  let now = 0, seq = 0;
  const timers = new Map();
  const clock = {
    advance(ms) {
      const until = now + ms;
      for (;;) {
        const due = [...timers.entries()].filter(([, t]) => t.at <= until).sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        timers.delete(due[0]);
        now = due[1].at;
        due[1].fn();
      }
      now = until;
    },
    get pending() { return timers.size; },
  };
  const ctx = vm.createContext({
    console,
    ST: st,
    DESK_STALE: stale,
    $: (sel) => els[sel.replace(/^#/, '')] || null,
    toast: (t) => toasts.push(t),
    alertBar: (t) => alerts.push(t),
    acctShort: (id) => '…' + String(id).slice(-3),
    DEMO: demo,
    confirmDlg: async (title, body, action, destructive) => { confirms.push({ title, body, action, destructive }); return confirm; },
    post: async (url, body) => {
      posts.push(body === undefined ? { url } : { url, body });
      if (answer instanceof Error) throw answer;
      return typeof answer === 'function' ? answer(url) : JSON.parse(JSON.stringify(answer));
    },
    refresh: () => refreshes.push(true),
    fetch: async (url) => { fetched.push(url); throw new Error('the master controls must never fetch'); },
    setTimeout: (fn, ms) => { const id = ++seq; timers.set(id, { at: now + ms, fn }); return id; },
    clearTimeout: (id) => { timers.delete(id); },
    window: win,
    document: doc,
  });
  vm.runInContext(BLOCK + `
    globalThis.api = { renderMaster, doArm, doDisarm, doKill, holdToFire, HOLD_MS,
      get ST() { return ST; }, set ST(v) { ST = v; },
      get DESK_STALE() { return DESK_STALE; }, set DESK_STALE(v) { DESK_STALE = v; } };`, ctx);
  const ev = (type, props = {}) => ({ type, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...props });
  const fire = (el, type, props) => { const e = ev(type, props); for (const fn of el.listeners[type] || []) fn(e); return e; };
  const kill = els.killBtn;
  return { api: ctx.api, els, kill, fire, clock, posts, toasts, confirms, refreshes, fetched, alerts, win, doc };
}

const plain = (v) => JSON.parse(JSON.stringify(v));

// ---- where the controls live ------------------------------------------------------------------
test('the top bar holds the master controls -- status, Arm/Disarm and a press-and-hold Kill with its ring', () => {
  const header = HTML.slice(HTML.indexOf('<header class="inset-topbar">'), HTML.indexOf('</header>'));
  assert.match(header, /id="statusPill"/);
  assert.match(header, /id="armBtn"/);
  assert.match(header, /<button class="btn btn-sm btn-kill holdbtn" type="button" id="killBtn"/);
  assert.match(header, /class="hold-ring"[\s\S]*class="hold-fill"/);
  assert.match(header, /press and hold/i);
  assert.equal((HTML.match(/id="killBtn"/g) || []).length, 1, 'exactly one Kill control on the page');
  assert.doesNotMatch(HTML, /tradeKillBtn|tradeArmBtn/, 'the Settings copies are gone -- one obvious place');
});

test('the status pill is a plain status (it no longer opens Settings), and render()/refresh() repaint the bar', () => {
  assert.doesNotMatch(HTML, /id="statusPill"[^>]*onclick/);
  const render = HTML.slice(HTML.indexOf('function render() {'), HTML.indexOf('async function refresh()'));
  assert.match(render, /renderMaster\(\);/);
  const refresh = HTML.slice(HTML.indexOf('async function refresh()'), HTML.indexOf('/* ---- PREVIEW MODE'));
  assert.match(refresh, /catch \{[\s\S]*renderMaster\(\);/, 'a failing refresh marks the top bar stale');
});

// ---- the armed state and Arm / Disarm ----------------------------------------------------------
test('ST == null: the pill asserts nothing, no Arm/Disarm (fail closed), and Kill is still wired', () => {
  const { api, els, kill } = load({ st: null });
  api.renderMaster();
  assert.equal(els.statusPill.textContent, 'connecting…');
  assert.equal(els.armBtn.style.display, 'none');
  assert.equal(els.armBtn.onclick, null);
  assert.ok((kill.listeners.pointerdown || []).length && (kill.listeners.keydown || []).length, 'Kill works regardless');
  api.DESK_STALE = true;
  api.renderMaster();
  assert.equal(els.statusPill.textContent, 'desk unreachable');
});

test('disarmed: the pill says DISARMED and the button is Arm -- the SAME confirm and POST as before', async () => {
  const { api, els, confirms, posts, refreshes, toasts } = load({ st: { armed: false } });
  api.renderMaster();
  assert.equal(els.statusPill.textContent, 'DISARMED');
  assert.equal(els.statusPill.className, 'pill idle');
  assert.equal(els.armBtn.style.display, '');
  assert.equal(els.armBtn.textContent, 'Arm');
  assert.equal(els.armBtn.onclick, api.doArm);
  await els.armBtn.onclick();
  assert.equal(confirms.length, 1);
  assert.equal(confirms[0].title, 'Arm the desk?');
  assert.deepEqual(plain(posts), [{ url: '/api/arm', body: { armed: true } }]);
  assert.equal(refreshes.length, 1);
  assert.match(toasts[0], /Armed/);
});

test('a declined Arm confirm never POSTs', async () => {
  const { api, els, posts } = load({ st: { armed: false }, confirm: false });
  api.renderMaster();
  await els.armBtn.onclick();
  assert.deepEqual(posts, []);
});

test('armed: the pill says ARMED and the button is Disarm -- immediate, no confirm, same POST', async () => {
  const { api, els, confirms, posts, refreshes } = load({ st: { armed: true } });
  api.renderMaster();
  assert.equal(els.statusPill.textContent, 'ARMED');
  assert.equal(els.statusPill.className, 'pill armed', 'ARMED has its own unmistakable look');
  assert.equal(els.armBtn.textContent, 'Disarm');
  assert.equal(els.armBtn.onclick, api.doDisarm);
  await els.armBtn.onclick();
  assert.equal(confirms.length, 0, 'Disarm only makes things safer: it never asks');
  assert.deepEqual(plain(posts), [{ url: '/api/arm', body: { armed: false } }]);
  assert.equal(refreshes.length, 1);
});

test('a stale desk keeps the last-known state but says it is stale', () => {
  const { api, els } = load({ st: { armed: true }, stale: true });
  api.renderMaster();
  assert.equal(els.statusPill.textContent, 'ARMED · stale');
  assert.match(els.statusPill.className, /\bstale\b/);
  assert.match(els.statusPill.title, /not answering/);
});

test('the master controls never call fetch -- they only talk to the desk (post/refresh)', async () => {
  const { api, fetched } = load({ st: { armed: false } });
  await api.doArm();
  await api.doDisarm();
  await api.doKill();
  assert.deepEqual(fetched, []);
});

// ---- the press-and-hold Kill ------------------------------------------------------------------
test('a pointer hold fires Kill once after HOLD_MS -- the SAME confirm and POST /api/kill as before', async () => {
  const { api, kill, fire, clock, confirms, posts, refreshes, toasts } = load();
  assert.equal(api.HOLD_MS, 1000);
  assert.equal(kill.style._p['--hold-ms'], '1000ms', 'the ring runs on the same clock as the timer');
  fire(kill, 'pointerdown', { button: 0, isPrimary: true });
  assert.ok(kill.classList.contains('holding'), 'the ring starts filling on the press itself');
  clock.advance(999);
  await tick();
  assert.equal(confirms.length, 0, 'nothing before the hold completes');
  clock.advance(1);
  await tick();
  assert.equal(confirms.length, 1);
  assert.equal(confirms[0].title, 'Kill everything?');
  assert.equal(confirms[0].destructive, true);
  assert.deepEqual(plain(posts), [{ url: '/api/kill' }]);
  assert.equal(refreshes.length, 1);
  assert.equal(toasts[toasts.length - 1],
    'Kill sent — orders cancelled and positions flattened on 2 accounts; the desk is disarmed.', 'words, not raw JSON');
  assert.ok(!kill.classList.contains('holding'));
  clock.advance(5000);   // still held down: never a second fire from the same hold
  await tick();
  assert.equal(confirms.length, 1);
  fire(kill, 'pointerup');
  assert.equal(toasts.filter((t) => /not sent/.test(t)).length, 0, 'letting go after it fired is not an early release');
});

test('letting go early cancels: nothing is sent, the ring runs back, and it says so', async () => {
  const { kill, fire, clock, confirms, posts, toasts } = load();
  fire(kill, 'pointerdown', { button: 0 });
  clock.advance(600);
  fire(kill, 'pointerup');
  assert.ok(!kill.classList.contains('holding'));
  assert.equal(clock.pending, 0);
  clock.advance(5000);
  await tick();
  assert.equal(confirms.length, 0);
  assert.deepEqual(posts, []);
  assert.match(toasts[0], /Kill not sent — press and hold/);
});

test('every way a pointer hold can break cancels it: leave, pointercancel, lost buttons, context menu, blur, hidden page', async () => {
  const breaks = [
    (s) => s.fire(s.kill, 'pointerleave'),
    (s) => s.fire(s.kill, 'pointercancel'),
    (s) => s.fire(s.kill, 'pointermove', { buttons: 0 }),
    (s) => s.fire(s.kill, 'contextmenu'),
    (s) => s.fire(s.kill, 'blur'),
    (s) => s.fire(s.win, 'blur'),
    (s) => { s.doc.hidden = true; s.fire(s.doc, 'visibilitychange'); },
  ];
  for (const brk of breaks) {
    const s = load();
    s.fire(s.kill, 'pointerdown', { button: 0 });
    s.clock.advance(500);
    brk(s);
    s.clock.advance(5000);
    await tick();
    assert.equal(s.confirms.length, 0, brk.toString());
    assert.ok(!s.kill.classList.contains('holding'), brk.toString());
  }
  const s = load();   // a move WITH the button still down is not a break
  s.fire(s.kill, 'pointerdown', { button: 0 });
  s.fire(s.kill, 'pointermove', { buttons: 1 });
  s.clock.advance(1000);
  await tick();
  assert.equal(s.confirms.length, 1);
});

test('only the primary button holds: a right-click or a second touch never starts one', async () => {
  const s = load();
  s.fire(s.kill, 'pointerdown', { button: 2 });
  s.fire(s.kill, 'pointerdown', { button: 0, isPrimary: false });
  s.clock.advance(3000);
  await tick();
  assert.equal(s.confirms.length, 0);
});

test('keyboard: holding Space fires once after HOLD_MS; its auto-repeat neither restarts nor re-fires it', async () => {
  const { kill, fire, clock, confirms, posts } = load();
  const down = fire(kill, 'keydown', { key: ' ', repeat: false });
  assert.equal(down.defaultPrevented, true, 'no page scroll, no native click');
  for (let t = 0; t < 40; t++) {        // ~33 ms auto-repeat for 1.3 s
    clock.advance(33);
    const rep = fire(kill, 'keydown', { key: ' ', repeat: true });
    assert.equal(rep.defaultPrevented, true);
  }
  await tick();
  assert.equal(confirms.length, 1, 'fired exactly once');
  assert.deepEqual(plain(posts), [{ url: '/api/kill' }]);
  fire(kill, 'keyup', { key: ' ' });
  clock.advance(5000);
  await tick();
  assert.equal(confirms.length, 1);
});

test('keyboard: an auto-repeat alone (a key already held when focus arrived) never fires', async () => {
  const { kill, fire, clock, confirms } = load();
  for (let t = 0; t < 100; t++) {
    fire(kill, 'keydown', { key: 'Enter', repeat: true });
    clock.advance(33);
  }
  await tick();
  assert.equal(confirms.length, 0);
  assert.ok(!kill.classList.contains('holding'));
});

test('keyboard: releasing Enter early cancels; releasing some other key does not', async () => {
  const s = load();
  const down = s.fire(s.kill, 'keydown', { key: 'Enter', repeat: false });
  assert.equal(down.defaultPrevented, true, "Enter's native click never happens");
  s.clock.advance(300);
  s.fire(s.kill, 'keyup', { key: 'Shift' });
  assert.ok(s.kill.classList.contains('holding'), 'another key coming up is not a release');
  s.clock.advance(300);
  s.fire(s.kill, 'keyup', { key: 'Enter' });
  s.clock.advance(5000);
  await tick();
  assert.equal(s.confirms.length, 0);
  assert.match(s.toasts[0], /Kill not sent/);
});

test('each hold fires at most once; a fresh press after it fires again (one confirm per hold)', async () => {
  const s = load();
  s.fire(s.kill, 'pointerdown', { button: 0 });
  s.clock.advance(1000);
  await tick();
  s.fire(s.kill, 'pointerup');
  s.fire(s.kill, 'pointerdown', { button: 0 });
  s.clock.advance(1000);
  await tick();
  assert.equal(s.confirms.length, 2);
  assert.deepEqual(plain(s.posts), [{ url: '/api/kill' }, { url: '/api/kill' }]);
});

test('a declined confirm after the hold sends nothing, and says so', async () => {
  const s = load({ confirm: false });
  s.fire(s.kill, 'pointerdown', { button: 0 });
  s.clock.advance(1000);
  await tick();
  assert.equal(s.confirms.length, 1);
  assert.deepEqual(s.posts, []);
  assert.deepEqual(s.toasts, ['Kill cancelled — nothing sent.']);
  assert.deepEqual(s.alerts, []);
});

test('a mouse click is not a hold; an assistive-tech click (no pointer, no key) goes to the confirm', async () => {
  const s = load();
  s.fire(s.kill, 'click', { detail: 1 });
  await tick();
  assert.equal(s.confirms.length, 0, 'a plain click never kills');
  s.fire(s.kill, 'click', { detail: 0 });
  await tick();
  assert.equal(s.confirms.length, 1, 'VoiceOver cannot hold: it gets the same confirm');
  assert.equal(s.confirms[0].title, 'Kill everything?');
});

// ---- a Kill that did not go through is never silent (review M1) ---------------------------------
async function kill(opts) {
  const s = load(opts);
  await s.api.doKill();
  return s;
}

test('no answer from the desk: a lasting red alert says Kill was NOT sent and to flatten at the broker', async () => {
  const s = await kill({ answer: new TypeError('Failed to fetch') });
  assert.deepEqual(plain(s.posts), [{ url: '/api/kill' }], 'the same one call');
  assert.equal(s.alerts.length, 1);
  assert.equal(s.alerts[0], 'Kill NOT sent — the desk did not answer (Failed to fetch). Flatten at the broker now.');
  assert.equal(s.toasts.length, 0, 'never a reassuring toast');
});

test('an unreadable answer: NOT confirmed, check and flatten at the broker', async () => {
  const s = await kill({ answer: new SyntaxError('Unexpected token <') });
  assert.match(s.alerts[0], /^Kill NOT confirmed — the desk's answer was unreadable\. .*flatten at the broker now\.$/);
});

test('a refusal (the write guard\'s 403): NOT sent, with the desk\'s own reason -- never "Kill: undefined"', async () => {
  const s = await kill({ answer: { error: 'origin not allowed' } });
  assert.equal(s.alerts[0], 'Kill NOT sent — the desk refused it: origin not allowed. Flatten at the broker now.');
  const s2 = await kill({ answer: { detail: [{ msg: 'bad body' }] } });
  assert.match(s2.alerts[0], /refused it: \[\{"msg":"bad body"\}\]/);
  for (const t of [...s.toasts, ...s2.toasts]) assert.doesNotMatch(t, /undefined/);
});

test('an account whose flatten or cancel failed: Kill FAILED on it, with the reason, and flatten it at the broker', async () => {
  const s = await kill({ answer: { ok: true, results: {
    acct048: { cancel_all: { ok: true, error: null }, flatten_all: { ok: false, error: 'timeout' } },
    acct049: { cancel_all: { ok: true, error: null }, flatten_all: { ok: true, error: null } },
    acct050: { cancel_all: { ok: false, error: 'rejected' }, flatten_all: { ok: true, error: null } } } } });
  assert.equal(s.alerts[0], 'Kill FAILED on …048 (FLATTEN FAILED: timeout) · …050 (CANCEL FAILED: rejected). ' +
    'Flatten them at the broker now.');
  assert.equal(s.toasts.length, 0);
});

test('a clean Kill with no connected account still says what happened; preview mode says nothing more', async () => {
  const s = await kill({ answer: { ok: true, results: {} } });
  assert.equal(s.toasts[0], 'Kill sent — the desk is disarmed (no connected account to flatten).');
  const d = await kill({ demo: true, answer: { ok: false } });
  assert.deepEqual(d.alerts, [], 'preview: post() already said nothing is sent');
  assert.deepEqual(d.toasts, []);
});

test('the unknown-state tooltip no longer promises that Kill "works regardless"', () => {
  const { api, els } = load({ st: null });
  api.renderMaster();
  assert.doesNotMatch(els.statusPill.title, /works regardless/);
  assert.match(els.statusPill.title, /only the desk can carry it out: if it does not answer, flatten at the broker/);
  assert.doesNotMatch(HTML, /works regardless/);
});

test('the alert is solid, red, above every dialog, and stays until dismissed', () => {
  assert.match(HTML, /<div id="alertBar" role="alert" hidden>/);
  const css = HTML.slice(HTML.indexOf('  #alertBar{'), HTML.indexOf('  #alertBar[hidden]'));
  assert.match(css, /z-index:85;/);
  assert.match(css, /background:var\(--card\);/);
  assert.match(css, /border:1\.5px solid var\(--neg\);/);
  assert.doesNotMatch(css, /backdrop-filter|glass/, 'money-critical text never goes translucent');
  const fn = HTML.slice(HTML.indexOf('function alertBar('), HTML.indexOf('async function post('));
  assert.doesNotMatch(fn, /setTimeout/, 'no auto-hide');
  assert.match(fn, /\$\("#alertX"\)\.onclick = \(\) => \{ \$\("#alertBar"\)\.hidden = true; \};/);
});
