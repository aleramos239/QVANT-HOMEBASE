/* Homebase Lab — A/B compare (the owner, 2026-10-18): two saved runs side by side -- their equity curves on one chart,
   every headline number with the difference (green where B is better), the net per year, the prop sim, and what was
   set differently between them (inputs, trade rules, days, costs). Any two runs of any strategies; it opens on the open
   strategy's two latest finished runs. Reads saved runs only (GET /api/tester/runs, /run/{id}/bundle); nothing is run.
   Opened from the Compare button in the top bar. Browser only; the pure parts are exported for tests. */
(() => {
'use strict';
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const money = (v) => (v == null || !Number.isFinite(v) ? '—' : `${v < 0 ? '−' : ''}$${Math.abs(Math.round(v)).toLocaleString('en-US')}`);

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
let el = null, list = [], side = { A: { sid: '', runs: [], rid: '' }, B: { sid: '', runs: [], rid: '' } }, got = null, err = '', busy = false;
async function call(path) {
  const r = await fetch(`/api/tester${path}`);
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : `the server answered ${r.status}`);
  return j;
}
async function runsOf(sid) { return sid ? (await call(`/runs?limit=40&strategy=${encodeURIComponent(sid)}`)).filter((r) => r.status === 'done') : []; }
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
  document.addEventListener('keydown', onKey);
  el.innerHTML = '<div class="mix-in"><p class="mix-note" style="padding:16px">Loading…</p></div>';
  try {
    const [d, b] = await Promise.all([call('/drafts'), call('/strategies')]);
    list = [...(d || []).map((x) => ({ id: x.id, name: (x.meta && x.meta.name) || x.name })), ...(b || []).map((x) => ({ id: x.id, name: x.name || x.id }))];
    const sid = openStrategy() || (list[0] || {}).id || '';
    const runs = await runsOf(sid);
    side = { A: { sid, runs, rid: (runs[1] || runs[0] || {}).id || '' }, B: { sid, runs, rid: (runs[0] || {}).id || '' } };
    await load();
  } catch (e) { err = e.message; paint(); }
}
function close() { if (!el) return; document.removeEventListener('keydown', onKey); el.remove(); el = null; got = null; }
function onKey(e) { if (e.key === 'Escape') close(); }
async function onChange(e) {
  const t = e.target, k = t.dataset.side;
  if (!k) return;
  if (t.dataset.pick === 'strategy') { side[k].sid = t.value; side[k].runs = await runsOf(t.value); side[k].rid = (side[k].runs[0] || {}).id || ''; }
  else side[k].rid = t.value;
  await load();
}
function swap() { side = { A: side.B, B: side.A }; load(); }
async function load() {
  err = ''; got = null;
  if (side.A.rid && side.B.rid) {
    busy = true; paint();
    try { const [a, b] = await Promise.all([call(`/run/${side.A.rid}/bundle`), call(`/run/${side.B.rid}/bundle`)]); got = { a, b }; } catch (e) { err = e.message; }
    busy = false;
  }
  paint();
}
const RUN_DAY = new Intl.DateTimeFormat('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
function runLabel(r) {
  const rg = r.range || {}, when = r.created ? RUN_DAY.format(new Date(r.created)) : r.id;
  return `${when} · ${rg.label || `${rg.start} → ${rg.end}`} · ${money(r.net_profit)} · ${r.trades ?? '?'} trades`;
}
function picker(k) {
  const s = side[k];
  return `<div class="ab-pick ab-${k}"><b class="ab-tag">${k}</b>
    <select data-side="${k}" data-pick="strategy" aria-label="Strategy ${k}">${list.map((x) => `<option value="${esc(x.id)}"${x.id === s.sid ? ' selected' : ''}>${esc(x.name)}</option>`).join('')}</select>
    <select data-side="${k}" data-pick="run" aria-label="Run ${k}">${s.runs.length ? s.runs.map((r) => `<option value="${esc(r.id)}"${r.id === s.rid ? ' selected' : ''}>${esc(runLabel(r))}</option>`).join('') : '<option value="">No finished run yet</option>'}</select></div>`;
}
function paint() {
  if (!el) return;
  el.innerHTML = `<div class="mix-in">
    <div class="mix-head"><h2>Compare two runs</h2><span class="mix-sub">B against A: green where B is better</span>
      <button class="hb-ib mix-x" data-act="close" aria-label="Close" title="Close (Esc)">✕</button></div>
    <div class="ab-picks">${picker('A')}<button class="btn btn-sm btn-outline" data-act="swap" title="Swap A and B">⇅</button>${picker('B')}</div>
    <section class="mix-out">${err ? `<p class="mix-err">${esc(err)}</p>` : busy ? '<p class="mix-note">Loading…</p>' : got ? report(got.a, got.b) : '<p class="mix-note">Pick two finished runs.</p>'}</section></div>`;
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

const api = { METRICS, fmt, delta, settingsDiff, pnlCurve, byYear };
if (typeof module !== 'undefined' && module.exports) module.exports = api;
if (typeof document !== 'undefined') {
  const btn = document.getElementById('tbAB');
  if (btn) btn.addEventListener('click', open);
  window.HBLabAB = { open, close, ...api };
}
})();
