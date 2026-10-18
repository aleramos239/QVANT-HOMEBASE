/* Homebase Lab — the group builder (the owner, 2026-10-18): pick strategies and a size for each, and see them as ONE
   account: the group's numbers and each member's, the daily equity curves, how alike their days are (correlation of
   daily P&L), and the prop sim of the merged trades on the picked rule set. The server does the work (POST
   /api/tester/groupmix, homebase/charts/groupmix.py) from each member's latest BUILD-DAYS run: nothing is run here.
   Opened from the Group button in the top bar; the last picks are kept in this browser. */
(() => {
'use strict';
const KEY = 'hb.labMix';
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
const money = (v) => (v == null ? '—' : `${v < 0 ? '−' : ''}$${Math.abs(Math.round(v)).toLocaleString('en-US')}`);
const pct = (v) => (v == null ? '—' : `${Math.round(v * 100)} %`);     // a 0..1 odds
const pctv = (v) => (v == null ? '—' : `${Math.round(v)} %`);         // already a percent (win rate)
const num = (v, d = 2) => (v == null ? '—' : Number(v).toFixed(d));

let st = (() => { try { return { picks: {}, rule: '', keepOnly: true, q: '', ...JSON.parse(localStorage.getItem(KEY) || '{}') }; } catch (_) { return { picks: {}, rule: '', keepOnly: true, q: '' }; } })();
const save = () => { try { localStorage.setItem(KEY, JSON.stringify(st)); } catch (_) { /* this session only */ } };
let list = [], rules = [], marks = {}, result = null, busy = false, err = '', el = null;

async function call(path, body) {
  const r = await fetch(`/api/tester${path}`, body === undefined ? {} : { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify(body) });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(typeof j.detail === 'string' ? j.detail : `the server answered ${r.status}`);
  return j;
}

async function load() {
  const [b, d, g, p] = await Promise.all([call('/strategies'), call('/drafts'), call('/groups').catch(() => ({})), call('/prop-rules')]);
  marks = (g && g.status) || {};
  list = [...(d || []).map((x) => ({ id: x.id, name: (x.meta && x.meta.name) || x.name, root: (x.meta && x.meta.root) || '' })),
    ...(b || []).map((x) => ({ id: x.id, name: x.name || x.id, root: x.root || '' }))];
  rules = (p || []).map((r) => ({ id: r.id, name: r.name }));
  if (!st.rule || !rules.some((r) => r.id === st.rule)) st.rule = (rules.find((r) => /lucid-flex-50k@/.test(r.id)) || rules[0] || {}).id || '';
}

/* ---- the sheet ---- */
function open() {
  if (el) return;
  el = document.createElement('div');
  el.className = 'mix';
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-label', 'Group builder');
  document.body.appendChild(el);
  el.addEventListener('click', onClick);
  el.addEventListener('input', onInput);
  document.addEventListener('keydown', onKey);
  el.innerHTML = '<div class="mix-in"><p class="mix-note">Loading…</p></div>';
  load().then(paint).catch((e) => { err = e.message; paint(); });
}
function close() {
  if (!el) return;
  document.removeEventListener('keydown', onKey);
  el.remove();
  el = null;
}
function onKey(e) { if (e.key === 'Escape') close(); }

function picked() { return Object.keys(st.picks).filter((id) => list.some((s) => s.id === id)); }

function paint() {
  if (!el) return;
  const q = st.q.trim().toLowerCase();
  const shown = list.filter((s) => (!st.keepOnly || marks[s.id] === 'keep' || st.picks[s.id]) && (!q || `${s.name} ${s.id}`.toLowerCase().includes(q)));
  const row = (s) => {
    const on = s.id in st.picks;
    return `<label class="mix-pick${on ? ' on' : ''}"><input type="checkbox" data-pick="${esc(s.id)}"${on ? ' checked' : ''}>
      <span class="mix-nm"><b>${esc(s.name)}</b><small>${esc([s.root, marks[s.id] ? marks[s.id][0].toUpperCase() + marks[s.id].slice(1) : ''].filter(Boolean).join(' · '))}</small></span>
      ${on ? `<input class="mix-size" data-size="${esc(s.id)}" value="${esc(st.picks[s.id])}" inputmode="decimal" aria-label="Size of ${esc(s.name)}" title="Size: 1 = as it was run, 0.5 = half, 2 = double">` : ''}</label>`;
  };
  const n = picked().length;
  el.innerHTML = `<div class="mix-in">
    <div class="mix-head"><h2>Group builder</h2><span class="mix-sub">Each strategy's latest build-days run, as one account</span>
      <button class="hb-ib mix-x" data-act="close" aria-label="Close" title="Close (Esc)">✕</button></div>
    <div class="mix-body">
      <aside class="mix-side">
        <input class="mix-q" data-q type="search" placeholder="Find a strategy" value="${esc(st.q)}" aria-label="Find a strategy">
        <label class="mix-keep"><input type="checkbox" data-keeponly${st.keepOnly ? ' checked' : ''}> Only “Keep”</label>
        <div class="mix-list">${shown.map(row).join('') || `<p class="mix-note">${st.keepOnly ? 'No strategy has the Keep status yet: set it from a row’s ⋯ in the list, or untick “Only Keep”.' : 'No strategy matches.'}</p>`}</div>
        <label class="mix-rule">Prop rules <select data-rule>${rules.map((r) => `<option value="${esc(r.id)}"${r.id === st.rule ? ' selected' : ''}>${esc(r.name)}</option>`).join('')}</select></label>
        <button class="btn btn-default mix-go" data-act="go"${n < 2 || busy ? ' disabled' : ''}>${busy ? 'Working…' : n < 2 ? 'Pick 2 or more' : `Combine ${n}`}</button>
      </aside>
      <section class="mix-out">${err ? `<p class="mix-err">${esc(err)}</p>` : ''}${result ? report(result) : '<p class="mix-note">Pick two or more strategies and press Combine.</p>'}</section>
    </div></div>`;
}

/* ---- the answer ---- */
function report(r) {
  if (r.error) return `<p class="mix-err">${esc(r.error)}</p>${leftOut(r)}`;
  const g = r.group || {}, p = r.prop || null;
  const tile = (k, v, tone = '') => `<div class="mix-tile"><span>${k}</span><b class="${tone}">${v}</b></div>`;
  const tiles = [tile('Net', money(g.net), g.net >= 0 ? 'up' : 'dn'), tile('Trades', g.trades ?? '—'), tile('Win rate', pctv(g.win_rate)),
    tile('Profit factor', num(g.profit_factor)), tile('Max drawdown', money(g.max_drawdown), 'dn'), tile('Worst day', money(g.worst_day), 'dn'),
    tile('Days', g.days ?? '—'), tile('Days together', g.together_days ?? '—')].join('');
  const prop = p ? `<h3>${esc(p.account || 'Prop sim')}</h3><div class="mix-tiles">${[tile('Pass the eval', pct(p.eval_pass_p)), tile('Bust', pct(p.bust_p), 'dn'),
    tile('Days to pass (median)', p.median_days_to_pass ?? '—'), tile('Funded payout', pct(p.funded_payout_p)), tile('Expected cheque', money(p.funded_expected_cheque))].join('')}</div>` : '';
  const names = r.members.map((m) => list.find((s) => s.id === m.name)?.name || m.name);
  const mrows = r.members.map((m, i) => { const s = m.summary || {}; return `<tr><td>${esc(names[i])}</td><td>×${esc(m.size)}</td><td class="${s.net >= 0 ? 'up' : 'dn'}">${money(s.net)}</td><td>${s.trades ?? '—'}</td><td>${pctv(s.win_rate)}</td><td>${num(s.profit_factor)}</td><td class="dn">${money(s.max_drawdown)}</td></tr>`; }).join('');
  return `<p class="mix-note">Build days ${esc(r.window.start)} → ${esc(r.window.end)} (the days every member's run covers)</p>
    <div class="mix-tiles">${tiles}</div>${prop}
    <h3>Equity</h3>${curve(r, names)}
    <h3>Members</h3><table class="mix-t"><thead><tr><th>Strategy</th><th>Size</th><th>Net</th><th>Trades</th><th>Win</th><th>PF</th><th>Max DD</th></tr></thead><tbody>${mrows}</tbody></table>
    <h3>How alike their days are</h3>${corr(r.correlation, names)}${leftOut(r)}`;
}
function leftOut(r) {
  return (r.left_out || []).length ? `<h3>Left out</h3><ul class="mix-left">${r.left_out.map((x) => `<li><b>${esc(list.find((s) => s.id === x.strategy)?.name || x.strategy)}</b>: ${esc(x.why)}</li>`).join('')}</ul>` : '';
}
const COLORS = ['#2962FF', '#E8A23A', '#1F9D55', '#9C27B0', '#F23645', '#00897B', '#8D6E63', '#5C6BC0', '#C0CA33', '#EC407A', '#26A69A', '#78909C'];
function curve(r, names) {
  const g = r.group && r.group.curve;
  if (!g || !g.days.length) return '<p class="mix-note">No trades in the shared days.</p>';
  const days = g.days, W = 720, H = 220, P = 8;
  const series = [{ vals: g.vals, color: 'var(--hb-fg)', w: 2.2, name: 'Group' },
    ...r.members.map((m, i) => {
      const c = (m.summary && m.summary.curve) || { days: [], vals: [] }, at = new Map(c.days.map((d, k) => [d, c.vals[k]]));
      let last = 0;
      return { vals: days.map((d) => (at.has(d) ? (last = at.get(d)) : last)), color: COLORS[i % COLORS.length], w: 1.2, name: names[i] };
    })];
  const all = series.flatMap((s) => s.vals), lo = Math.min(0, ...all), hi = Math.max(0, ...all), span = hi - lo || 1;
  const x = (i) => P + (i / Math.max(1, days.length - 1)) * (W - 2 * P), y = (v) => H - P - ((v - lo) / span) * (H - 2 * P);
  const path = (v) => v.map((val, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(val).toFixed(1)}`).join('');
  return `<svg class="mix-curve" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Equity curves">
      <line x1="${P}" x2="${W - P}" y1="${y(0)}" y2="${y(0)}" class="mix-zero"/>
      ${series.slice(1).map((s) => `<path d="${path(s.vals)}" stroke="${s.color}" stroke-width="${s.w}" fill="none" opacity=".75"/>`).join('')}
      <path d="${path(series[0].vals)}" stroke="${series[0].color}" stroke-width="${series[0].w}" fill="none"/></svg>
    <div class="mix-legend">${series.map((s) => `<span><i style="background:${s.color}"></i>${esc(s.name)}</span>`).join('')}<span class="mix-range">${money(lo)} … ${money(hi)}</span></div>`;
}
function corr(c, names) {
  if (!c || !c.names.length) return '';
  const cell = (v, i, j) => {
    if (i === j) return '<td class="mix-c self">—</td>';
    if (v == null) return `<td class="mix-c" title="Too few days to say">·</td>`;
    const a = Math.min(1, Math.abs(v)), bg = v >= 0 ? `rgb(242 54 69 / ${(a * 0.55).toFixed(2)})` : `rgb(41 98 255 / ${(a * 0.55).toFixed(2)})`;
    return `<td class="mix-c" style="background:${bg}" title="${esc(names[i])} vs ${esc(names[j])}: ${v} · both traded on ${c.both[i][j]} days">${v.toFixed(2)}</td>`;
  };
  return `<table class="mix-t mix-corr"><thead><tr><th></th>${names.map((n, i) => `<th title="${esc(n)}">${i + 1}</th>`).join('')}</tr></thead><tbody>
    ${c.matrix.map((row, i) => `<tr><th title="${esc(names[i])}">${i + 1}. ${esc(names[i])}</th>${row.map((v, j) => cell(v, i, j)).join('')}</tr>`).join('')}</tbody></table>
    <p class="mix-note">Correlation of daily P&amp;L on ${c.days} days (a day off counts as 0). Near 0: they make and lose money on different days, which smooths the account. Red, near 1: the same trade twice.</p>`;
}

/* ---- events ---- */
function onClick(e) {
  const a = e.target.closest('[data-act]');
  if (!a) { if (e.target === el) close(); return; }
  if (a.dataset.act === 'close') close();
  if (a.dataset.act === 'go') go();
}
function onInput(e) {
  const t = e.target;
  if (t.dataset.pick !== undefined) { if (t.checked) st.picks[t.dataset.pick] = st.picks[t.dataset.pick] || 1; else delete st.picks[t.dataset.pick]; save(); paint(); return; }
  if (t.dataset.size !== undefined) { st.picks[t.dataset.size] = t.value; save(); return; }
  if (t.dataset.keeponly !== undefined) { st.keepOnly = t.checked; save(); paint(); return; }
  if (t.dataset.rule !== undefined) { st.rule = t.value; save(); return; }
  if (t.dataset.q !== undefined) { st.q = t.value; save(); const at = t.selectionStart; paint(); const n = el.querySelector('[data-q]'); n.focus(); n.setSelectionRange(at, at); }
}
async function go() {
  const members = picked().map((id) => ({ strategy: id, size: Number(st.picks[id]) }));
  const bad = members.find((m) => !(m.size >= 0.1 && m.size <= 20));
  if (bad) { err = 'A size is 0.1 to 20 (1 = as it was run).'; paint(); return; }
  busy = true; err = ''; paint();
  try { result = await call('/groupmix', { members, prop_rules: st.rule || null }); } catch (e2) { err = e2.message; }
  busy = false; paint();
}

const b = document.getElementById('tbMix');
if (b) b.addEventListener('click', open);
window.HBLabMix = { open, close };
})();
