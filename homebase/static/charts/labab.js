/* Homebase Lab — A/B compare (the owner, 2026-10-18): two saved runs side by side -- their equity curves on one chart,
   every headline number with the difference (green where B is better), the net per year, the prop sim, and what was
   set differently between them (inputs, trade rules, days, costs). Any two runs of any strategies; it opens on the open
   strategy's two latest finished runs. Each side is a strategy plus one of three windows (owner, 2026-10-24): 3:1 IS, 3:1 OOS, 3:1 FULL SAMPLE -- the strategy's latest saved
   run on the in-sample months, its latest finished test-months read, its latest run from Sep 2021 to now. Reads saved results only
   (GET /api/tester/runs, /run/{id}/bundle, /walkforwards, /walkforward/{id}/result); nothing is run.
   Opened from the Compare button in the top bar. Browser only; the pure parts are exported for tests. */
(() => {
'use strict';
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const money = (v) => (v == null || !Number.isFinite(v) ? '—' : `${v < 0 ? '−' : ''}$${Math.abs(Math.round(v)).toLocaleString('en-US')}`);

/* the search box over a strategy pop-up: every word of the query must be in the name or the id (any case); '' keeps everything */
function matches(x, q) {
  const hay = `${x.name} ${x.id}`.toLowerCase();
  return String(q || '').toLowerCase().split(/\s+/).filter(Boolean).every((w) => hay.includes(w));
}

/* the smart search: the first strategy whose name BEGINS with what was typed (the text to fill in), else null */
function fill(list, q) {
  const t = String(q || '').replace(/^\s+/, '').toLowerCase();
  return t ? list.find((x) => String(x.name).toLowerCase().startsWith(t)) || null : null;
}

/* the three windows: [key, label] */
const WINDOWS = [['is', '3:1 IS'], ['oos', '3:1 OOS'], ['all', '3:1 FULL SAMPLE']];
const FULL_FROM = '2021-09-22';
/* the newest finished run of each kind in a strategy's runs (newest first): in-sample = range wf_is; full sample = a custom range from Sep 2021 or earlier */
function pickRuns(runs) {
  const done = (runs || []).filter((r) => r.status === 'done'), kind = (r) => (r.range || {}).kind;
  return {
    is: done.find((r) => kind(r) === 'wf_is') || null,
    all: done.find((r) => kind(r) === 'custom' && String((r.range || {}).start) <= FULL_FROM) || null,
  };
}
/* a finished test-months read (walk-forward result.oos) as a run bundle the report below can read; the numbers it does not hold show as - */
function oosBundle(res, name) {
  const oo = res && res.oos;
  if (!oo || oo.state !== 'done' || !oo.record) return null;
  const rec = oo.record, ms = oo.months || [];
  return { run: { partial: true, strategy: { name }, range: { start: ms[0] || '', end: ms[ms.length - 1] || '' },
    report: { summary: { all: { net_profit: rec.net, trades: rec.trades, win_rate: rec.win_rate, profit_factor: rec.pf, avg_trade: rec.avg_trade,
      max_drawdown: rec.max_dd, sharpe: rec.sharpe } } } }, equity: oo.equity || null, propsim: null };
}

/* the numbers compared: [key, label, format, which way is better (+1 higher, -1 lower, 0 neither)] */
const METRICS = [
  ['net_profit', 'Net', 'money', 1], ['trades', 'Trades', 'int', 0], ['win_rate', 'Win rate', 'pctv', 1],
  ['profit_factor', 'Profit factor', 'num', 1], ['avg_trade', 'Avg trade', 'money', 1], ['max_drawdown', 'Max drawdown', 'money', 1],
  ['sharpe', 'Sharpe', 'num', 1], ['t_stat', 't-stat', 'num', 1], ['max_consec_losses', 'Losses in a row', 'int', -1],
  ['largest_loss', 'Largest loss', 'money', 1], ['days', 'Days traded', 'int', 0],
];
const PROP = [['eval_pass_p', 'Pass the eval', 'pct', 1], ['bust_p', 'Bust', 'pct', -1], ['median_days_to_pass', 'Days to pass', 'int', -1],
  ['funded_payout_p', 'Funded payout', 'pct', 1], ['funded_expected_cheque', 'Expected cheque', 'money', 1]];
function fmt(v, kind) {
  if (v == null || !Number.isFinite(v)) return '—';
  if (kind === 'money') return money(v);
  if (kind === 'pctv') return `${v.toFixed(1)} %`;
  if (kind === 'pct') return `${Math.round(v * 100)} %`;
  if (kind === 'int') return String(Math.round(v));
  return v.toFixed(2);
}
/* B against A: {text, tone} -- tone 'up' when B is better, 'dn' when worse, '' when neither way is better or equal */
function delta(a, b, kind, better) {
  if (a == null || b == null || !Number.isFinite(a) || !Number.isFinite(b)) return { text: '', tone: '' };
  const d = b - a;
  if (Math.abs(d) < 1e-9) return { text: '=', tone: '' };
  const text = kind === 'money' ? `${d > 0 ? '+' : '−'}${money(Math.abs(d)).replace('−', '')}` : kind === 'pctv' ? `${d > 0 ? '+' : ''}${d.toFixed(1)} pts`
    : kind === 'pct' ? `${d > 0 ? '+' : ''}${Math.round(d * 100)} pts` : `${d > 0 ? '+' : ''}${kind === 'int' ? Math.round(d) : d.toFixed(2)}`;
  return { text, tone: better === 0 ? '' : d * better > 0 ? 'up' : 'dn' };
}
/* what was set differently: [[label, A's, B's]] over the strategy, inputs, trade rules, days and costs */
function settingsDiff(a, b) {
  const show = (v) => (v === undefined || v === null || v === '' ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v));
  const rows = [];
  const one = (label, x, y) => { if (show(x) !== show(y)) rows.push([label, show(x), show(y)]); };
  one('Strategy', a.strategy && a.strategy.name, b.strategy && b.strategy.name);
  const ra = a.range || {}, rb = b.range || {};
  one('Days', `${ra.start} → ${ra.end}`, `${rb.start} → ${rb.end}`);
  if (a.partial || b.partial) return rows;           // a test-months read keeps only its numbers: no inputs, rules or costs to compare
  for (const k of [...new Set([...Object.keys(a.inputs || {}), ...Object.keys(b.inputs || {})])].sort()) one(`Input ${k}`, (a.inputs || {})[k], (b.inputs || {})[k]);
  const ca = (a.controls && a.controls.rules) || {}, cb = (b.controls && b.controls.rules) || {};
  for (const k of [...new Set([...Object.keys(ca), ...Object.keys(cb)])].sort()) one(`Rule ${k.replace(/_/g, ' ')}`, ca[k] ?? 'off', cb[k] ?? 'off');
  for (const [k, label] of [['qty', 'Contracts'], ['commission', 'Commission'], ['slippage_ticks', 'Slippage (ticks)'], ['prop_rules', 'Prop rules']]) one(label, a[k], b[k]);
  return rows;
}
/* the two curves as P&L from each run's start: [{t, v}] (equity minus its first value) */
function pnlCurve(eq) {
  const t = (eq && eq.t_ms) || [], e = (eq && eq.equity) || [];
  return t.length && e.length ? t.map((x, i) => ({ t: x, v: e[i] - e[0] })) : [];
}
function byYear(a, b) {
  const ya = new Map(((a.report || {}).by_year || []).map((r) => [r.period, r])), yb = new Map(((b.report || {}).by_year || []).map((r) => [r.period, r]));
  return [...new Set([...ya.keys(), ...yb.keys()])].sort().map((y) => [y, ya.get(y), yb.get(y)]);
}

/* ---- the sheet (browser only) ---- */
let el = null, query = { A: '', B: '' }, list = [], side = { A: { sid: '', win: 'is' }, B: { sid: '', win: 'oos' } }, found = new Map(), got = null, why = '', err = '', busy = false;
async function call(path) {
  const r = await fetch(`/api/tester${path}`);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : `the server answered ${r.status}`);
  return j;
}
/* what a strategy has saved, once per strategy: {is: run, all: run, oos: walk-forward result} (null where it was never run) */
async function lookup(sid) {
  if (!sid) return { is: null, all: null, oos: null };
  if (found.has(sid)) return found.get(sid);
  const q = encodeURIComponent(sid), got3 = pickRuns(await call(`/runs?limit=300&strategy=${q}`));
  let oos = null;
  for (const w of (await call(`/walkforwards?limit=30&strategy=${q}`)).filter((x) => x.strategy === sid && x.scheme === 'fixed' && x.status === 'done')) {
    const res = await call(`/walkforward/${encodeURIComponent(w.id)}/result`).catch(() => null);
    if (oosBundle(res, '')) { oos = res; break; }
  }
  const out = { ...got3, oos };
  found.set(sid, out);
  return out;
}
function openStrategy() {
  const m = /strategy=([^&]+)/.exec(location.hash), n = m ? decodeURIComponent(m[1]) : '';
  return list.find((s) => s.id === `draft_${n}` || s.id === n)?.id || '';
}
async function open() {
  if (el) return;
  el = document.createElement('div');
  el.className = 'mix ab';
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-label', 'Compare two runs');
  document.body.appendChild(el);
  el.addEventListener('click', (e) => { const a = e.target.closest('[data-act]'); if (!a) { if (e.target === el) close(); } else if (a.dataset.act === 'close') close(); else if (a.dataset.act === 'swap') swap(); });
  el.addEventListener('change', onChange);
  el.addEventListener('input', onSearch);
  el.addEventListener('keydown', onSearchKey);
  document.addEventListener('keydown', onKey);
  el.innerHTML = '<div class="mix-in"><p class="mix-note" style="padding:16px">Loading…</p></div>';
  try {
    const [d, b] = await Promise.all([call('/drafts'), call('/strategies')]);
    const all = [...(d || []).map((x) => ({ id: x.id, name: (x.meta && x.meta.name) || x.name })), ...(b || []).map((x) => ({ id: x.id, name: x.name || x.id }))];
    list = all.filter((x, i) => all.findIndex((y) => y.id === x.id) === i);       // /strategies lists every draft again
    const sid = openStrategy() || (list[0] || {}).id || '';
    side = { A: { sid, win: 'is' }, B: { sid, win: 'oos' } };
    await load();
  } catch (e) { err = e.message; paint(); }
}
function close() { if (!el) return; document.removeEventListener('keydown', onKey); el.remove(); el = null; got = null; }
function onKey(e) { if (e.key === 'Escape') close(); }
async function onChange(e) {
  const t = e.target, k = t.dataset.side;
  if (!k) return;
  if (t.dataset.pick === 'strategy') side[k].sid = t.value;
  else side[k].win = t.value;
  await load();
}
/* a search box narrows its own strategy pop-up in place (no repaint: the box keeps the cursor); the chosen strategy always stays in it */
function strategyOptions(k) {
  const s = side[k], hits = list.filter((x) => x.id === s.sid || matches(x, query[k]));
  return hits.map((x) => `<option value="${esc(x.id)}"${x.id === s.sid ? ' selected' : ''}>${esc(x.name)}</option>`).join('');
}
function onSearch(e) {
  const t = e.target, k = t.dataset.q;
  if (!k) return;
  query[k] = t.value;
  const sel = el.querySelector(`select[data-side="${k}"][data-pick="strategy"]`);
  sel.innerHTML = strategyOptions(k);
  t.classList.toggle('none', !!query[k].trim() && !list.some((x) => matches(x, query[k])));         // red: nothing matches
  // fill in the rest of the name as it is typed (selected, so the next key replaces it and Backspace takes it away)
  const hit = e.inputType && e.inputType.startsWith('insert') ? fill(list, query[k]) : null;
  if (hit && hit.name.length > t.value.length && t.selectionStart === t.value.length) {
    const n = t.value.length;
    t.value = hit.name.slice(0, n) + hit.name.slice(n);          // keep what was typed, add the rest
    t.setSelectionRange(n, hit.name.length);
  }
}
/* the strategy the box points at: the filled-in name, else the first match */
const picked = (k, text) => fill(list, text) || list.find((x) => matches(x, text));
/* Enter takes it */
function onSearchKey(e) {
  const k = e.target.dataset && e.target.dataset.q;
  if (!k || e.key !== 'Enter' || e.repeat) return;
  e.preventDefault();
  const hit = picked(k, query[k]);
  if (!hit) return;
  query[k] = '';
  onChange({ target: { dataset: { side: k, pick: 'strategy' }, value: hit.id } });
}
function swap() { side = { A: side.B, B: side.A }; load(); }
/* one side's result: its bundle, or why there is none */
async function resolve(k) {
  const x = side[k], f = await lookup(x.sid), label = (WINDOWS.find(([w]) => w === x.win) || [])[1];
  if (x.win === 'oos') {
    const b = oosBundle(f.oos, (list.find((y) => y.id === x.sid) || {}).name);
    return b ? { bundle: b } : { why: `${label}: no finished test-months read for this strategy yet. Run it from the Lab (Show > Test months).` };
  }
  const r = f[x.win];
  return r ? { bundle: await call(`/run/${encodeURIComponent(r.id)}/bundle`) } : { why: `${label}: this strategy has no saved ${x.win === 'is' ? 'in-sample run' : 'run from Sep 2021 to now'} yet. Run it from the Lab.` };
}
async function load() {
  err = ''; got = null; why = '';
  busy = true; paint();
  try {
    const [a, b] = await Promise.all([resolve('A'), resolve('B')]);
    if (a.bundle && b.bundle) got = { a: a.bundle, b: b.bundle }; else why = [a.why && `A, ${a.why}`, b.why && `B, ${b.why}`].filter(Boolean).join(' ');
  } catch (e) { err = e.message; }
  busy = false;
  paint();
}
function picker(k) {
  const x = side[k];
  return `<div class="ab-pick ab-${k}"><b class="ab-tag">${k}</b>
    <input type="search" class="ab-q" data-q="${k}" value="${esc(query[k])}" placeholder="Search ${list.length} strategies" aria-label="Search strategies ${k}" autocomplete="off" spellcheck="false">
    <select data-side="${k}" data-pick="strategy" aria-label="Strategy ${k}">${strategyOptions(k)}</select>
    <select data-side="${k}" data-pick="run" aria-label="Window ${k}">${WINDOWS.map(([w, l]) => `<option value="${w}"${w === x.win ? ' selected' : ''}>${l}</option>`).join('')}</select></div>`;
}
function paint() {
  if (!el) return;
  el.innerHTML = `<div class="mix-in">
    <div class="mix-head"><h2>Compare two runs</h2><span class="mix-sub">B against A: green where B is better</span>
      <button class="hb-ib mix-x" data-act="close" aria-label="Close" title="Close (Esc)">✕</button></div>
    <div class="ab-picks">${picker('A')}<button class="btn btn-sm btn-outline" data-act="swap" title="Swap A and B">⇅</button>${picker('B')}</div>
    <section class="mix-out">${err ? `<p class="mix-err">${esc(err)}</p>` : busy ? '<p class="mix-note">Loading…</p>' : got ? report(got.a, got.b) : `<p class="mix-note">${esc(why || 'Pick two windows to compare.')}</p>`}</section></div>`;
}
function report(A, B) {
  const a = A.run || {}, b = B.run || {}, sa = ((a.report || {}).summary || {}).all || {}, sb = ((b.report || {}).summary || {}).all || {};
  const row = ([k, label, kind, better], x, y) => { const d = delta(x[k], y[k], kind, better); return `<tr><td>${label}</td><td>${fmt(x[k], kind)}</td><td>${fmt(y[k], kind)}</td><td class="${d.tone}">${esc(d.text)}</td></tr>`; };
  const pa = (A.propsim || {}).headline || null, pb = (B.propsim || {}).headline || null;
  const diff = settingsDiff(a, b);
  const years = byYear(a, b);
  return `${curve(pnlCurve(A.equity), pnlCurve(B.equity))}
    <h3>Numbers</h3><table class="mix-t ab-t"><thead><tr><th></th><th>A</th><th>B</th><th>B − A</th></tr></thead><tbody>${METRICS.map((m) => row(m, sa, sb)).join('')}</tbody></table>
    ${pa || pb ? `<h3>Prop sim${a.prop_rules === b.prop_rules ? ` · ${esc(((A.propsim || {}).rules || {}).label || ((A.propsim || {}).rules || {}).name || a.prop_rules || '')}` : ' (different rule sets)'}</h3>
      <table class="mix-t ab-t"><thead><tr><th></th><th>A</th><th>B</th><th>B − A</th></tr></thead><tbody>${PROP.map((m) => row(m, pa || {}, pb || {})).join('')}</tbody></table>` : ''}
    <h3>Net per year</h3><table class="mix-t ab-t"><thead><tr><th>Year</th><th>A</th><th>B</th><th>B − A</th></tr></thead><tbody>${years.map(([y, x, z]) => { const d = delta(x && x.net, z && z.net, 'money', 1); return `<tr><td>${esc(y)}</td><td>${fmt(x && x.net, 'money')}</td><td>${fmt(z && z.net, 'money')}</td><td class="${d.tone}">${esc(d.text)}</td></tr>`; }).join('')}</tbody></table>
    <h3>What is different</h3>${diff.length ? `<table class="mix-t ab-t ab-diff"><thead><tr><th></th><th>A</th><th>B</th></tr></thead><tbody>${diff.map(([l, x, y]) => `<tr><td>${esc(l)}</td><td>${esc(x)}</td><td>${esc(y)}</td></tr>`).join('')}</tbody></table>` : '<p class="mix-note">The same settings: the runs differ only by when they ran (code or data changed between them).</p>'}`;
}
function curve(ca, cb) {
  if (!ca.length && !cb.length) return '<p class="mix-note">No equity saved.</p>';
  const all = [...ca, ...cb], t0 = Math.min(...all.map((p) => p.t)), t1 = Math.max(...all.map((p) => p.t));
  const lo = Math.min(0, ...all.map((p) => p.v)), hi = Math.max(0, ...all.map((p) => p.v)), span = hi - lo || 1, W = 720, H = 220, P = 8;
  const x = (t) => P + ((t - t0) / Math.max(1, t1 - t0)) * (W - 2 * P), y = (v) => H - P - ((v - lo) / span) * (H - 2 * P);
  const path = (c) => c.map((p, i) => `${i ? 'L' : 'M'}${x(p.t).toFixed(1)},${y(p.v).toFixed(1)}`).join('');
  return `<svg class="mix-curve" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Equity A and B">
      <line x1="${P}" x2="${W - P}" y1="${y(0)}" y2="${y(0)}" class="mix-zero"/>
      <path d="${path(ca)}" stroke="#2962FF" stroke-width="1.8" fill="none"/><path d="${path(cb)}" stroke="#E8A23A" stroke-width="1.8" fill="none"/></svg>
    <div class="mix-legend"><span><i style="background:#2962FF"></i>A</span><span><i style="background:#E8A23A"></i>B</span><span class="mix-range">${money(lo)} … ${money(hi)}</span></div>`;
}

const api = { matches, fill, pickRuns, oosBundle, WINDOWS, METRICS, fmt, delta, settingsDiff, pnlCurve, byYear };
if (typeof module !== 'undefined' && module.exports) module.exports = api;
if (typeof document !== 'undefined') {
  const btn = document.getElementById('tbAB');
  if (btn) btn.addEventListener('click', open);
  window.HBLabAB = { open, close, ...api };
}
})();
