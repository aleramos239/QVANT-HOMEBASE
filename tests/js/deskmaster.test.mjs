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
    textContent: '', className: '', title: '', onclick: null, disabled: false, attrs: {},
    setAttribute(k, v) { this.attrs[k] = String(v); },
    removeAttribute(k) { delete this.attrs[k]; },
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
  const els = { statusPill: fakeEl(), armBtn: fakeEl(), killBtn: fakeEl(), alertBar: fakeEl(), alertText: fakeEl() };
  els.alertBar.hidden = false;
  const posts = [], toasts = [], confirms = [], refreshes = [], fetched = [], alerts = [], hides = [];
  const win = fakeEl(), doc = fakeEl();
  let settle = null;              // answer === 'later': the test resolves / rejects the Kill's POST itself
  doc.hidden = false;
  // a fake clock: setTimeout/clearTimeout run only when the test advances time
  let now = 1_000_000, seq = 0;
  const timers = new Map();
  const clock = {
    get now() { return now; },
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
    STALE_WHY: '',
    $: (sel) => els[sel.replace(/^#/, '')] || null,
    toast: (t) => toasts.push(t),
    toastHide: () => hides.push(true),
    alertBar: (t) => { alerts.push(t); els.alertText.textContent = t; els.alertBar.hidden = false; },
    Date: { now: () => now },
    DOUBLE_CLICK_MS: 400,
    acctShort: (id) => '…' + String(id).slice(-3),
    DEMO: demo,
    confirmDlg: async (title, body, action, destructive) => { confirms.push({ title, body, action, destructive }); return confirm; },
    post: async (url, body) => {
      posts.push(body === undefined ? { url } : { url, body });
      if (answer instanceof Error) throw answer;
      if (answer === 'later') return new Promise((res, rej) => { settle = { res, rej }; });
      if (typeof answer === 'function') return answer(url, body);
      if (url === '/api/arm' && answer === KILL_OK) return { ok: true, armed: body.armed };   // the desk, doing as asked
      return JSON.parse(JSON.stringify(answer));
    },
    refresh: () => refreshes.push(true),
    fetch: async (url) => { fetched.push(url); throw new Error('the master controls must never fetch'); },
    setTimeout: (fn, ms) => { const id = ++seq; timers.set(id, { at: now + ms, fn }); return id; },
    clearTimeout: (id) => { timers.delete(id); },
    window: win,
    document: doc,
  });
  const bounce = HTML.slice(HTML.indexOf('const SWITCH_AT = {};'), HTML.indexOf('function cfDone('));
  vm.runInContext(bounce + BLOCK + `
    globalThis.api = { renderMaster, doArm, doDisarm, doKill, holdToFire, HOLD_MS,
      get ST() { return ST; }, set ST(v) { ST = v; },
      get DESK_STALE() { return DESK_STALE; }, set DESK_STALE(v) { DESK_STALE = v; } };`, ctx);
  const ev = (type, props = {}) => ({ type, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, ...props });
  const fire = (el, type, props) => { const e = ev(type, props); for (const fn of el.listeners[type] || []) fn(e); return e; };
  const kill = els.killBtn;
  return { api: ctx.api, els, kill, fire, clock, posts, toasts, confirms, refreshes, fetched, alerts, hides, win, doc,
    answer: (v) => settle.res(JSON.parse(JSON.stringify(v))), fail: (e) => settle.rej(e) };
}

const plain = (v) => JSON.parse(JSON.stringify(v));

// ---- where the controls live ------------------------------------------------------------------
test('the top bar holds the master controls -- status, Arm/Disarm and a press-and-hold Kill with its ring', () => {
  const header = HTML.slice(HTML.indexOf('<header class="inset-topbar hb-bar">'), HTML.indexOf('</header>'));
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
  assert.ok(els.armBtn.classList.contains('gone'), 'hidden -- by visibility, its space kept');
  assert.equal(els.armBtn.disabled, true);
  assert.equal(els.armBtn.attrs['aria-hidden'], 'true');
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
  assert.ok(!els.armBtn.classList.contains('gone'));
  assert.equal(els.armBtn.disabled, false);
  assert.equal(els.armBtn.attrs['aria-hidden'], undefined);
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
  assert.match(els.statusPill.title, /Last known state — the desk is not answering\./);
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

test('a network failure never claims "NOT sent" (the desk may have got it and disarmed): NOT confirmed, flatten at the broker', async () => {
  const s = await kill({ answer: new TypeError('Failed to fetch') });
  assert.deepEqual(plain(s.posts), [{ url: '/api/kill' }], 'the same one call');
  assert.equal(s.alerts.length, 1);
  assert.equal(s.alerts[0], "Kill NOT confirmed — the desk didn't answer (Failed to fetch). Check the broker / flatten there now.");
  assert.deepEqual(s.toasts, ['Kill sent — waiting for the desk…'], 'the only toast is the one that went up as it was sent');
  assert.ok(s.hides.length >= 1, 'and it came down when the alert went up');
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
  assert.deepEqual(s.toasts, ['Kill sent — waiting for the desk…'], 'no success toast');
});

test('a clean Kill with no connected account still says what happened; preview mode says nothing more', async () => {
  const s = await kill({ answer: { ok: true, results: {} } });
  assert.equal(s.toasts[s.toasts.length - 1], 'Kill sent — the desk is disarmed (no connected account to flatten).');
  const d = await kill({ demo: true, answer: { ok: false } });
  assert.deepEqual(plain(d.posts), [{ url: '/api/kill' }], 'the same call (post() itself refuses in preview)');
  assert.deepEqual(d.alerts, [], 'preview: post() already said nothing is sent');
  assert.deepEqual(d.toasts, []);
});

test('nits: a missing error reads "no reason given" (no stray quotes); ok with no results is NOT confirmed, not "refused"', async () => {
  const s = await kill({ answer: { ok: true, results: { acct041: { cancel_all: { ok: false, error: null }, flatten_all: { ok: true } } } } });
  assert.equal(s.alerts[0], 'Kill FAILED on …041 (CANCEL FAILED: no reason given). Flatten it at the broker now.');
  const s2 = await kill({ answer: { ok: true, armed: false } });
  assert.equal(s2.alerts[0], 'Kill NOT confirmed — the desk said ok but sent no account results. ' +
    'Check every account and flatten at the broker now.');
});

// ---- a Kill in flight (second review) -------------------------------------------------------------
test('a Kill in flight says so at once; no answer in 6 s escalates to the red alert, and it keeps waiting', async () => {
  const s = load({ answer: 'later' });
  const done = s.api.doKill();
  await tick();
  assert.deepEqual(plain(s.posts), [{ url: '/api/kill' }]);
  assert.deepEqual(s.toasts, ['Kill sent — waiting for the desk…']);
  s.clock.advance(5999);
  assert.deepEqual(s.alerts, []);
  s.clock.advance(1);
  assert.deepEqual(s.alerts, ["Kill NOT confirmed — the desk hasn't answered in 6 s. Check the broker and flatten there now."]);
  s.clock.advance(2000);
  s.answer(KILL_OK);                                  // the desk answers after 8 s
  await done;
  assert.equal(s.toasts[s.toasts.length - 1],
    'Kill sent — orders cancelled and positions flattened on 2 accounts; the desk is disarmed. (the desk answered after 8 s)');
  assert.equal(s.els.alertBar.hidden, true, 'its "hasn\'t answered" alert comes down: it is no longer true');
});

test('a late Kill success never takes down a DIFFERENT failure that replaced the timeout alert', async () => {
  const s = load({ answer: 'later' });
  const done = s.api.doKill();
  await tick();
  s.clock.advance(7000);                              // the timeout alert is up ...
  s.els.alertText.textContent = 'Disarm NOT confirmed — the desk refused it: x.';   // ... then another failure replaces it
  s.answer(KILL_OK);
  await done;
  assert.equal(s.els.alertBar.hidden, false, 'the Disarm failure stays up');
});

test('a late FAILURE replaces the "hasn\'t answered" alert with what failed', async () => {
  const s = load({ answer: 'later' });
  const done = s.api.doKill();
  await tick();
  s.clock.advance(7000);
  s.answer({ ok: true, results: { acct048: { cancel_all: { ok: true }, flatten_all: { ok: false, error: 'timeout' } } } });
  await done;
  assert.equal(s.alerts[s.alerts.length - 1], 'Kill FAILED on …048 (FLATTEN FAILED: timeout). Flatten it at the broker now.');
  assert.equal(s.els.alertBar.hidden, false);
});

test('a late success takes the "hasn\'t answered" alert down; a late failure replaces it', () => {
  const fn = HTML.slice(HTML.indexOf('function killReport('), HTML.indexOf('const killRunning'));
  assert.match(fn, /if \(lateSecs && \$\("#alertText"\)\.textContent === KILL_SLOW_TEXT\) \$\("#alertBar"\)\.hidden = true;/);
  assert.ok(fn.indexOf('return alertBar(`Kill FAILED') < fn.indexOf('if (lateSecs && '),
    'a failure is reported before any take-down');
});

test('while a Kill is in flight a second hold sends nothing and says "Kill already running" -- no second confirm', async () => {
  const s = load({ answer: 'later' });
  const first = s.api.doKill();
  await tick();
  s.clock.advance(3000);
  await s.api.doKill();                               // a second hold completes
  assert.equal(s.confirms.length, 1, 'no second "Kill everything?"');
  assert.equal(s.posts.length, 1);
  assert.equal(s.toasts[s.toasts.length - 1], 'Kill already running — sent 3 s ago; waiting for the desk. Nothing more sent.');
  s.answer(KILL_OK);
  await first;
  const second = s.api.doKill();                      // answered: a new Kill is a new Kill
  await tick();
  assert.equal(s.confirms.length, 2);
  assert.equal(s.posts.length, 2);
  s.answer(KILL_OK);
  await second;
});

test('a dead connection never locks Kill out: after 30 s with no answer a new Kill may go out', async () => {
  const s = load({ answer: 'later' });
  const first = s.api.doKill();
  await tick();
  s.clock.advance(29_999);
  await s.api.doKill();
  assert.equal(s.posts.length, 1);
  s.clock.advance(1);
  const again = s.api.doKill();
  await tick();
  assert.equal(s.posts.length, 2, 'the second request goes out (the desk serialises Kills)');
  s.answer(KILL_OK);
  await again;
  void first;                                         // the dead request never answers -- and holds nothing up
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
  assert.match(css, /position:fixed; bottom:84px;/, 'never over the top bar, however tall it wraps -- Kill stays reachable');
  assert.match(css, /background:var\(--card\);/);
  assert.match(css, /border:1\.5px solid var\(--neg\);/);
  assert.doesNotMatch(css, /backdrop-filter|glass/, 'money-critical text never goes translucent');
  const fn = HTML.slice(HTML.indexOf('function alertBar('), HTML.indexOf('async function post('));
  assert.doesNotMatch(fn, /setTimeout/, 'no auto-hide');
  assert.match(fn, /\$\("#alertX"\)\.onclick = \(\) => \{ \$\("#alertBar"\)\.hidden = true; \};/);
});

// ---- nothing in the top bar moves Kill when a status text changes (review minor) ---------------
test('the pill, Arm and the clock have fixed widths, and Arm hides without giving up its space', () => {
  const css = (sel) => { const i = HTML.indexOf('  ' + sel + '{'); assert.ok(i >= 0, sel); return HTML.slice(i, HTML.indexOf('}', i) + 1); };
  assert.match(css('.pill-slot'), /width:7\.75rem; flex:none;/, 'fits "desk unreachable", the longest pill text');
  assert.match(css('#armBtn'), /width:4\.75rem; flex:none;/, 'fits "Disarm"');
  assert.match(css('#armBtn.gone'), /visibility:hidden;/);
  assert.match(css('.clock'), /display:inline-block; width:11rem;/);
  assert.match(css('.inset-topbar > *'), /flex-shrink:0;/);
  assert.match(HTML, /<span class="pill-slot"><span id="statusPill"/);
  const fn = HTML.slice(HTML.indexOf('function renderMaster('), HTML.indexOf('/* Press-and-hold:'));
  assert.doesNotMatch(fn, /style\.display/, 'never display:none -- that would reflow the bar under a held Kill');
});

test('the bar sheds the clock, then the brand tag, then the wordmark, then wraps -- never overflowing its right end', () => {
  // the page switcher (Desk / Charts / Backtest, ~190px) sits in the bar: each breakpoint keeps >= 15px of margin
  // over the width the bar needs (the classic 15px scrollbar is inside a media query's width)
  const at = (px) => HTML.indexOf(`@media (max-width:${px}px)`);
  assert.ok(at(1120) > 0 && /@media \(max-width:1120px\)\{ \.clock\{ display:none; \} \}/.test(HTML));
  assert.ok(/@media \(max-width:930px\)\{ \.brand-tag\{ display:none; \} \}/.test(HTML));
  assert.ok(/@media \(max-width:820px\)\{ \.wordmark\{ display:none; \} \}/.test(HTML));
  const narrow = HTML.slice(at(740), HTML.indexOf('\n  }\n', at(740)));
  assert.match(narrow, /\.inset-topbar\{ height:auto; min-height:52px; flex-wrap:wrap;/);
  assert.match(narrow, /\.master\{ flex-wrap:wrap; justify-content:flex-end;/);
});

test('the page switcher: three plain links, the current page marked, hrefs built from the host with ?v=33', () => {
  const nav = HTML.slice(HTML.indexOf('<nav class="pgsw"'), HTML.indexOf('</nav>', HTML.indexOf('<nav class="pgsw"')));
  assert.deepEqual([...nav.matchAll(/data-page="(\w+)"/g)].map((m) => m[1]), ['desk', 'charts', 'backtest']);
  assert.equal([...nav.matchAll(/aria-current="page"/g)].length, 1);
  assert.match(nav, /data-page="desk" aria-current="page"/);
  assert.doesNotMatch(HTML, /chartsLink/);
  const js = HTML.slice(HTML.indexOf("var sw = document.getElementById('pgSw')"));
  assert.match(js, /':8850\/'/);
  assert.match(js, /':8852\/' \+ V/);
  assert.match(js, /':8852\/backtest' \+ V/);
  assert.match(js, /V = '\?v=33'/);
});

test('the stale pill is never faded: a dashed edge, full-strength text (measured >= 5.4:1 in both themes)', () => {
  const rule = (sel) => { const i = HTML.indexOf('  ' + sel + '{'); assert.ok(i >= 0, sel); return HTML.slice(i, HTML.indexOf('}', i) + 1); };
  assert.equal(rule('.master .pill.stale'), '  .master .pill.stale{ border-style:dashed; }');
  assert.match(rule('.master .pill.idle.stale'), /color:var\(--foreground\);/);
  assert.match(rule('.master .pill.armed.stale'), /border-color:var\(--destructive-foreground\);/);
  assert.doesNotMatch(HTML, /\.pill\.stale\{[^}]*opacity/, 'opacity would pull the text under 4.5:1');
});

// ---- an open menu or size edit holds updates, but never leaves the pill asserting a state ------
const REFRESH = HTML.slice(HTML.indexOf('const FREEZE_STALE_MS'), HTML.indexOf('/* ---- PREVIEW MODE'));
function loadRefresh({ st = { armed: true }, reply = () => ({ ok: true, status: 200, body: { armed: true } }), freezeInFlight = false } = {}) {
  const clock = { now: 0 }, fetched = [], masters = [], renders = [];
  const clockEl = { textContent: '', classList: { contains: () => false } };
  const ctx = vm.createContext({
    Date: { now: () => clock.now }, FREEZE: false, DEMO: false, ST: st, DESK_STALE: false, STALE_WHY: '',
    fetch: async (u) => {
      fetched.push(u);
      const a = reply();
      if (freezeInFlight) ctx.api.freeze = true;   // a menu / size edit opens while this request is in flight
      if (a instanceof Error) throw a;
      return { ok: a.ok, status: a.status, json: async () => { if (a.body instanceof Error) throw a.body; return a.body; } };
    },
    render: () => renders.push(1), renderMaster: () => masters.push(1), renderSettings() {},
    $: (sel) => (sel === '#clock' ? clockEl : { textContent: '', classList: { contains: () => false } }),
  });
  vm.runInContext(REFRESH + `
    globalThis.api = { refresh, get stale() { return DESK_STALE; }, get why() { return STALE_WHY; },
      get ST() { return ST; }, set freeze(v) { FREEZE = v; } };`, ctx);
  return { api: ctx.api, clock, fetched, masters, renders, clockEl };
}

test('while a menu or size edit holds updates, the pill goes stale after 5 s -- with no extra request', async () => {
  const s = loadRefresh();
  await s.api.refresh();                         // a fresh status at t=0
  assert.equal(s.fetched.length, 1);
  s.api.freeze = true;                           // + Assign menu opens
  s.clock.now = 2500; await s.api.refresh();
  s.clock.now = 5000; await s.api.refresh();
  assert.equal(s.api.stale, false, 'not yet: 5 s is the limit');
  s.clock.now = 7500; await s.api.refresh();
  assert.equal(s.api.stale, true);
  assert.equal(s.api.why, 'updates pause while a menu or a size edit is open');
  assert.equal(s.masters.length, 1, 'the top bar is repainted, the cards (and the open menu) are not');
  assert.equal(s.renders.length, 1);
  assert.equal(s.fetched.length, 1, 'no request while frozen');
  s.api.freeze = false;                          // the menu closes: the next tick is fresh again
  s.clock.now = 10000; await s.api.refresh();
  assert.equal(s.api.stale, false);
  assert.equal(s.fetched.length, 2);
});

// ---- Arm / Disarm believe only the desk's answer (second review) -----------------------------------
test('a refused Disarm (403) is the red alert, never "Disarmed"', async () => {
  const s = load({ st: { armed: true }, answer: { error: 'origin not allowed' } });
  s.api.renderMaster();
  await s.els.armBtn.onclick();
  assert.deepEqual(plain(s.posts), [{ url: '/api/arm', body: { armed: false } }]);
  assert.deepEqual(s.toasts, []);
  assert.deepEqual(s.alerts, ['Disarm NOT confirmed — the desk refused it: origin not allowed. The desk may still be ARMED: ' +
    'press Kill, or disarm again.']);
});

test('a Disarm whose connection drops is the red alert -- never an uncaught error', async () => {
  const s = load({ st: { armed: true }, answer: new TypeError('Failed to fetch') });
  s.api.renderMaster();
  await s.els.armBtn.onclick();
  assert.match(s.alerts[0], /^Disarm NOT confirmed — the desk didn't answer \(Failed to fetch\)\./);
  assert.equal(s.refreshes.length, 1);
});

test('a desk that answers ok but still says ARMED is not a Disarm', async () => {
  const s = load({ st: { armed: true }, answer: () => ({ ok: true, armed: true }) });
  await s.api.doDisarm();
  assert.match(s.alerts[0], /^Disarm NOT confirmed — the desk says it is still ARMED\./);
});

test('a refused or dropped Arm says NOT armed (the safe side: a toast), never "Armed"', async () => {
  const s = load({ st: { armed: false }, answer: { error: 'origin not allowed' } });
  await s.api.doArm();
  assert.deepEqual(s.toasts, ['NOT armed — the desk refused it: origin not allowed.']);
  assert.deepEqual(s.alerts, []);
  const d = load({ st: { armed: false }, answer: new TypeError('Failed to fetch') });
  await d.api.doArm();
  assert.deepEqual(d.toasts, ["NOT armed — the desk didn't answer (Failed to fetch)."]);
  const u = load({ st: { armed: false }, answer: new SyntaxError('Unexpected token <') });
  await u.api.doArm();
  assert.deepEqual(u.toasts, ["NOT armed — the desk's answer was unreadable."]);
});

test('double-clicking Disarm is one flip: the re-painted Arm under the second click never pops "Arm the desk?"', async () => {
  const s = load({ st: { armed: true } });
  s.api.renderMaster();
  await s.els.armBtn.onclick();                        // click 1: Disarm
  s.api.ST = { armed: false };
  s.api.renderMaster();                                // the button is Arm now
  s.clock.advance(250);
  await s.els.armBtn.onclick();                        // click 2 lands on Arm
  assert.equal(s.confirms.length, 0, 'no "Arm the desk?"');
  assert.deepEqual(plain(s.posts), [{ url: '/api/arm', body: { armed: false } }]);
  s.clock.advance(400);
  const later = s.api.doArm();                         // a deliberate Arm later asks as usual
  await tick();
  assert.equal(s.confirms.length, 1);
  await later;
});

test('a JSON error from /api/status never becomes the state: the last-known one stays, marked stale with the reason', async () => {
  const s = loadRefresh({ reply: () => ({ ok: false, status: 403, body: { error: 'host not allowed' } }) });
  await s.api.refresh();
  assert.deepEqual(plain(s.api.ST), { armed: true }, 'ST is not replaced by {error: ...} (which read as DISARMED)');
  assert.equal(s.api.stale, true);
  assert.equal(s.api.why, 'the desk answered HTTP 403: host not allowed');
  assert.equal(s.clockEl.textContent, 'status error');
  assert.equal(s.renders.length, 0);
  assert.equal(s.masters.length, 1);
});

test('a 200 without a boolean "armed" is not a status either; a first load that fails keeps ST null (unknown)', async () => {
  const s = loadRefresh({ reply: () => ({ ok: true, status: 200, body: { detail: 'weird' } }) });
  await s.api.refresh();
  assert.deepEqual(plain(s.api.ST), { armed: true });
  assert.equal(s.api.why, "the desk's status was unreadable");
  const f = loadRefresh({ st: null, reply: () => ({ ok: false, status: 500, body: new SyntaxError('Unexpected token I') }) });
  await f.api.refresh();
  assert.equal(f.api.ST, null, 'never assert a state it does not know');
  assert.equal(f.api.stale, true);
  assert.equal(f.api.why, 'the desk answered HTTP 500', 'a plain-text 500 says what it was, not "not answering"');
  const n = loadRefresh({ reply: () => new TypeError('Failed to fetch') });
  await n.api.refresh();
  assert.equal(n.api.why, 'the desk is not answering');
  assert.equal(n.clockEl.textContent, 'server unreachable');
});

test('a space-taking scrollbar appearing never shifts the top bar: the column reserves its gutter', () => {
  const i = HTML.indexOf('  .app-main{');
  const rule = HTML.slice(i, HTML.indexOf('}', i) + 1);
  assert.match(rule, /overflow-y:auto;\s*scrollbar-gutter:stable;/);
});

test('a menu or size edit that opens while a status is in flight is never wiped: only the top bar repaints', async () => {
  const s = loadRefresh({ freezeInFlight: true, reply: () => ({ ok: true, status: 200, body: { armed: false } }) });
  await s.api.refresh();
  assert.equal(s.renders.length, 0, 'the cards (and the open menu / edit in them) are left alone');
  assert.equal(s.masters.length, 1, 'the top bar still shows the fresh state');
  assert.deepEqual(plain(s.api.ST), { armed: false });
  assert.equal(s.api.stale, false);
});

test('when the cards are rebuilt anyway, an + Assign menu that lived in them lets go of the update hold', () => {
  const fn = HTML.slice(HTML.indexOf('function render() {'), HTML.indexOf('async function refresh()'));
  assert.match(fn, /if \(ASG_OPEN && !document\.contains\(ASG_OPEN\.menu\)\) \{\s*ASG_OPEN = null;\s*if \(!document\.getElementById\("qedit"\)\) FREEZE = false;/);
});
