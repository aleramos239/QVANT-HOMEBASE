/* Homebase Lab -- the idea board (WP5): every saved idea with where it stands on the 3:1 route and its next step, and the three
   steps of a saved idea as buttons: the in-sample table, the pick (needs the box number), the test months (needs a second confirm:
   it reads them once). Each button starts ONLY from the owner's own typed words, sent as typed (owner_said); with no words, nothing
   is sent. The board reads GET /api/tester/blueprint/board; "Show the table" is a look (POST /blueprint/run, blueprint_status);
   the steps go through the one guarded door POST /api/tester/blueprint/step. The trading server shows the board and never runs.
   Opened from the Ideas button in the strategy list (lab.js). Browser only; the pure parts are exported for tests. */
(() => {
'use strict';
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const SAID_MAX = 400;     // = BP_SAID_MAX in tester_api.py
const REFRESH_MS = 8000;

/* where an idea stands -> its label, its one button, and the order the board lists it in (waiting for the owner first) */
const STAGES = {
  table: { label: 'In-sample table next', action: 'table', order: 0 },
  pick: { label: 'Waiting for your pick', action: 'pick', order: 1 },
  test: { label: 'Box picked, test months next', action: 'oos', order: 2 },
  card: { label: 'Card not written yet', action: null, order: 3, why: 'There is no card yet: a chat writes it.' },
  done: { label: 'Test months read', action: null, order: 4, why: 'Nothing is left on the 3:1 route for this idea.' },
  used: { label: 'Test months used', action: null, order: 4, why: 'The one read of the test months is used.' },
  error: { label: 'Saved results unreadable', action: null, order: 5, why: 'The saved results cannot be read: ask in a chat.' },
  old: { label: 'Old route', action: null, order: 6, why: 'This idea is not on the 3:1 route: it is shown here, with no button.' },
};
const ENGINE_NOTE = 'These buttons run the research engine, the same as the chat tools. The Lab\'s own tester is a different engine: month layouts are the same, but fills, exits and flat times differ, so numbers from the two are not the same and are not mixed here. The Lab\'s 3:1 button is not wired to a saved idea.';
const BTN = { table: 'Run the in-sample table', pick: 'Lock this pick', oos: 'Read the test months once' };
const ASK = { table: 'Type the words that tell it to run the in-sample table', pick: 'Type the words that name your pick', oos: 'Type the words that tell it to read the test months' };

function stageOf(idea) {
  const wf = (idea && idea.wf) || {};
  const key = STAGES[wf.stage] ? wf.stage : 'old';
  return { key, ...STAGES[key] };
}

/* may this idea's button start now? ok, or the plain reason it is off */
function canAct(idea, machineRuns) {
  const s = stageOf(idea);
  if (!s.action) return { ok: false, reason: s.why };
  if (!machineRuns) return { ok: false, reason: 'This is the trading server: it never runs tests. Open the Lab on the Mac.' };
  if (idea.job) return { ok: false, reason: `A job is running for this idea (${idea.job}): wait for it to finish.` };
  return { ok: true, reason: '' };
}

/* the request for a step, or {error}: no words, no request. The words go on exactly as typed. */
function stepBody(idea, words, opt = {}) {
  const s = stageOf(idea);
  if (!s.action) return { error: s.why };
  if (typeof words !== 'string' || !words.trim()) return { error: 'Type your own words that say to do it.' };
  if (words.length > SAID_MAX) return { error: `Your words are too long (${SAID_MAX} characters at most).` };
  const body = { step: s.action, name: idea.name, owner_said: words };
  if (s.action === 'pick') {
    const t = String(opt.box == null ? '' : opt.box).trim();
    if (!/^[0-9]+$/.test(t) || Number(t) < 1) return { error: 'Type the box number you pick (a whole number from 1).' };
    body.box = Number(t);
  } else if (s.action === 'oos') {
    if (opt.confirmed !== true) return { error: 'Tick the box: this reads the test months once and cannot be taken back.' };
    body.box = idea.wf.box;
    body.reads_test_months_once = true;
  }
  return { body };
}

function filterIdeas(list, q, stage) {
  const words = String(q || '').toLowerCase().split(/\s+/).filter(Boolean);
  return list.filter((i) => (stage === 'all' || !stage || stageOf(i).key === stage) && words.every((w) => i.name.toLowerCase().includes(w)));
}
const sortIdeas = (list) => list.map((i, n) => [i, n]).sort((a, b) => stageOf(a[0]).order - stageOf(b[0]).order || a[1] - b[1]).map((x) => x[0]);

const api = { stageOf, canAct, stepBody, filterIdeas, sortIdeas, ENGINE_NOTE, STAGES };
if (typeof module !== 'undefined' && module.exports) module.exports = api;
if (typeof document === 'undefined') return;

/* ---- the board (browser) ---- */
let el = null, S = null, timer = 0;
const fresh = () => ({ ideas: [], machine: false, err: '', q: '', stage: 'all', sel: null, words: '', box: '', ok: false, shown: null, out: null, busy: false, loading: true });

async function req(method, path, body) {
  try {
    const r = await fetch(`/api/tester${path}`, { method, headers: body ? { 'content-type': 'application/json' } : undefined, body: body ? JSON.stringify(body) : undefined });
    let j = null; try { j = await r.json(); } catch (_) { /* no body */ }
    return { ok: r.ok, json: j, error: r.ok ? '' : (j && (j.detail || j.error)) || `HTTP ${r.status}` };
  } catch (_) { return { ok: false, json: null, error: 'The chart service is not reachable' }; }
}
async function load() {
  const r = await req('GET', '/blueprint/board');
  if (!S) return;
  S.loading = false;
  if (r.ok) { S.ideas = sortIdeas(r.json.ideas || []); S.machine = !!r.json.machine_runs; S.err = ''; } else S.err = typeof r.error === 'string' ? r.error : 'The board could not be read.';
  paint();
}
const selIdea = () => S.ideas.find((i) => i.name === S.sel) || null;

function formHtml(i) {
  const s = stageOf(i), can = canAct(i, S.machine);
  if (!can.ok) return `<p class="mix-note" data-why>${esc(can.reason)}</p>`;
  return `<div class="bp-form ib-form">
    <div class="bp-f"><label for="ibWords">${esc(ASK[s.action])}</label><textarea id="ibWords" data-f="words" rows="2" maxlength="${SAID_MAX}" placeholder="In your own words" spellcheck="false">${esc(S.words)}</textarea>
      <small>Sent exactly as you type it. Nothing starts without it.</small></div>
    ${s.action === 'pick' ? `<div class="bp-f"><label for="ibBox">Box number</label><input id="ibBox" data-f="box" inputmode="numeric" value="${esc(S.box)}" placeholder="the # in the in-sample table" autocomplete="off"></div>` : ''}
    ${s.action === 'oos' ? `<label class="mix-keep"><input type="checkbox" data-f="ok"${S.ok ? ' checked' : ''}> This reads the test months once for box ${esc(i.wf.box)} and cannot be taken back.</label>` : ''}
    <div><button class="btn btn-sm btn-default" data-act="go">${esc(BTN[s.action])}</button></div></div>`;
}
function detail(i) {
  const s = stageOf(i);
  return `<div class="ib-detail"><p class="mix-note"><b>${esc(s.label)}.</b> ${esc(i.next || '')}</p>
    <div><button class="btn btn-sm btn-outline" data-act="show">${S.shown && S.shown.name === i.name ? 'Refresh' : 'Show'} the saved status</button></div>
    ${S.shown && S.shown.name === i.name ? `<pre class="ib-pre">${esc(S.shown.text)}</pre>` : ''}
    ${formHtml(i)}
    ${S.out && S.out.name === i.name ? `<p class="${S.out.ok ? 'mix-note' : 'mix-err'}">${esc(S.out.text)}</p>` : ''}</div>`;
}
function paint() {
  if (!el) return;
  const rows = filterIdeas(S.ideas, S.q, S.stage);
  const stages = [['all', 'All'], ...Object.entries(STAGES).map(([k, v]) => [k, v.label])];
  el.innerHTML = `<div class="mix-in">
    <div class="mix-head"><h2>Ideas</h2><span class="mix-sub">${S.ideas.length} saved · where each stands and what is next</span>
      <button class="hb-ib mix-x" data-act="close" aria-label="Close" title="Close (Esc)">✕</button></div>
    <div class="ib-bar"><input type="search" class="mix-q" data-f="q" value="${esc(S.q)}" placeholder="Search ideas" aria-label="Search ideas" autocomplete="off" spellcheck="false">
      <select class="mix-size" data-f="stage" aria-label="Stage">${stages.map(([k, l]) => `<option value="${k}"${k === S.stage ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select></div>
    <p class="mix-note ib-note">${esc(ENGINE_NOTE)}${S.machine ? '' : ' This is the trading server: it shows the board and never runs a test.'}</p>
    <section class="mix-out">${S.err ? `<p class="mix-err">${esc(S.err)}</p>` : S.loading ? '<p class="mix-note">Loading…</p>' : !rows.length ? '<p class="mix-note">No idea matches.</p>' :
      `<table class="mix-t ib-t"><thead><tr><th>Idea</th><th>Stage</th><th>Next step</th></tr></thead><tbody>${rows.map((i) => `<tr class="ib-row${i.name === S.sel ? ' on' : ''}" data-open="${esc(i.name)}"><td>${esc(i.name)}${i.job ? ' <small>(running)</small>' : ''}</td><td>${esc(stageOf(i).label)}</td><td>${esc(i.next || '')}</td></tr>${i.name === S.sel ? `<tr><td colspan="3">${detail(i)}</td></tr>` : ''}`).join('')}</tbody></table>`}</section></div>`;
}
/* typing must not repaint (the cursor would jump): the submit button only follows what is typed */
function syncGo() {
  const i = selIdea(), b = el && el.querySelector('[data-act="go"]');
  if (b && i) b.disabled = !!stepBody(i, S.words, { box: S.box, confirmed: S.ok }).error;
}
async function go() {
  const i = selIdea(); if (!i || S.busy) return;
  const r = stepBody(i, S.words, { box: S.box, confirmed: S.ok });
  if (r.error) { S.out = { name: i.name, ok: false, text: r.error }; paint(); return; }
  S.busy = true; S.out = { name: i.name, ok: true, text: 'Sending…' }; paint();
  const got = await req('POST', '/blueprint/step', r.body);
  S.busy = false;
  const j = got.json || {};
  S.out = { name: i.name, ok: got.ok && j.ok === true, text: got.ok ? j.text || '' : got.error };
  if (S.out.ok) { S.words = ''; S.box = ''; S.ok = false; }
  await load();
}
async function show(name) {
  const got = await req('POST', '/blueprint/run', { tool: 'blueprint_status', args: { name } });
  S.shown = { name, text: got.ok ? (got.json && got.json.text) || '' : got.error };
  paint();
}
function onClick(e) {
  const a = e.target.closest('[data-act]'), row = e.target.closest('[data-open]');
  if (a) {
    if (a.dataset.act === 'close') close(); else if (a.dataset.act === 'go') go(); else if (a.dataset.act === 'show' && S.sel) show(S.sel);
  } else if (row) {
    S.sel = S.sel === row.dataset.open ? null : row.dataset.open; S.words = ''; S.box = ''; S.ok = false; S.out = null; paint();
  } else if (e.target === el) close();
}
function onInput(e) {
  const f = e.target.dataset && e.target.dataset.f;
  if (f === 'q') { S.q = e.target.value; paint(); const q = el.querySelector('[data-f="q"]'); q.focus(); q.setSelectionRange(q.value.length, q.value.length); }
  else if (f === 'stage') { S.stage = e.target.value; paint(); }
  else if (f === 'words') { S.words = e.target.value; syncGo(); }
  else if (f === 'box') { S.box = e.target.value; syncGo(); }
  else if (f === 'ok') { S.ok = e.target.checked; syncGo(); }
}
const onKey = (e) => { if (e.key === 'Escape') close(); };
function open() {
  if (el) return;
  S = fresh();
  el = document.createElement('div');
  el.className = 'mix ib';
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-label', 'Ideas');
  document.body.appendChild(el);
  el.addEventListener('click', onClick);
  el.addEventListener('input', onInput);
  el.addEventListener('change', onInput);
  document.addEventListener('keydown', onKey);
  timer = setInterval(() => { if (!S.busy && S.ideas.some((i) => i.job)) load(); }, REFRESH_MS);   // a running job: look again
  paint(); load();
}
function close() {
  if (!el) return;
  clearInterval(timer); document.removeEventListener('keydown', onKey); el.remove(); el = null; S = null;
}
window.HBLabIdeas = { open, close, ...api };
})();
