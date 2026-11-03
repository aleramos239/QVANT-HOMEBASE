/* ---- sidebar ---- */
/* Which section a strategy is in: ON with an account = trading, ON with none = shadow, OFF = off. One that can trade (its day is
   placing, placed, live or error) counts as ON. The sidebar, the Today list and the Today headline all read this one rule. */
function sideKind(s, bk) {
  const on = !!(s.cfg.enabled || ["placing", "placed", "live", "error"].includes(s.day_status));
  return on && bk.length ? "trading" : on ? "shadow" : "off";
}
/* A strategy page's status line (owner 2026-11-02): its state in words, or red with EVERY reason. Reasons = its own checks that are not
   ok, and the Desk-wide warn / bad ones (no strategy, no account: Desk OFF, the feed, the Lab runner). An info line is listed, never red.
   Pure: checks as the page shows them (readinessShown), st = the status, stale = DESK_STALE. */
const STATUS_STALE = "The Desk is not answering: last known state.";
function statusLine(id, checks, st, stale) {      // id: a strategy, or the members of a variant set (picked variant first): one line for the set
  const red = {warn: 1, bad: 2}, reasons = [], ids = Array.isArray(id) ? id : [id], multi = Array.isArray(id);
  const who = (m) => labSafe(() => soloVarLabel(m), "") || m;
  let worst = 0;
  for (const c of checks || []) {
    if (!c || !(ids.includes(c.strategy) ? c.level !== "ok" : !c.strategy && !c.account && red[c.level])) continue;
    const text = c.label + ": " + c.detail;
    reasons.push({text: multi && c.strategy && !text.includes(who(c.strategy)) ? who(c.strategy) + " · " + text : text, fix: c.fix || "", account: c.account || ""});      // account: what Reconnect reconnects
    worst = Math.max(worst, red[c.level] || 0);
  }
  if (stale) return {level: "stale", text: STATUS_STALE, reasons};
  const rank = {trading: 0, shadow: 1, off: 2}, strategies = (st && st.strategies) || {}, book = (st && st.book) || {};
  const kinds = ids.filter(m => strategies[m]).map(m => sideKind(strategies[m], book[m] || []));      // a set is the best of its members, as in the sidebar
  const k = kinds.length ? kinds.reduce((a, b) => rank[b] < rank[a] ? b : a) : "off", s = strategies[ids[0]], bk = [...new Set(ids.flatMap(m => (book[m] || []).map(r => r.account)))];
  const lvl = worst === 2 ? "bad" : worst ? "warn" : null;
  if (k === "off") return {level: lvl || "off", text: "OFF", reasons};
  if (k === "shadow") {
    const sh = labSafe(() => labShadowNet(ids[0], s), null);      // a set: the picked variant's line, never a sum
    return {level: lvl || "shadow", text: "Shadow · no account" + (sh ? ` · would be ${usdS(sh.net)} today` : ""), reasons};
  }
  const p = multi ? setDayPnl({members: ids}, st.accounts, st.book) : todayPnl(s);      // a set's money is its accounts', never shadow dollars
  return {level: lvl || "ok", text: `${lvl ? "Not ready" : "Ready"} · trades on ${plural(bk.length, "account", "accounts")}${p != null ? " · today " + usdS(p) : ""}`, reasons};
}
function statusLineHtml(id) {
  const vs = labSafe(() => soloVs(id), null), pm = vs ? setPicked(vs) : null;      // a set page: all its members, the picked variant first
  const r = ST && readinessShown(ST.readiness, ST), L = statusLine(vs ? [pm, ...vs.members.filter(m => m !== pm)] : id, r ? r.checks : [], ST, DESK_STALE === true);
  const red = L.level === "bad" || L.level === "warn" || L.level === "stale";
  const row = (x) => `<div class="feed-row"><span class="h${red ? " warn" : ""}">${esc(x.text)}</span><span class="t">${LOOK_FIX[x.fix] && (x.fix !== "reconnect" || x.account)      // a reconnect with no account has nothing to reconnect
    ? `<button class="btn btn-outline btn-sm" onclick="lookFix(${jsArg(x.fix)},${jsArg(id)},${jsArg(x.account)})">${LOOK_FIX[x.fix]}</button>` : ""}</span></div>`;
  return `<div class="sd-state" data-level="${L.level}"><b>${esc(L.text)}</b></div>${L.reasons.length ? `<div class="agroup feed static">${L.reasons.map(row).join("")}</div>` : ""}`;
}
/* the status line alone, in place: when the Desk stops answering the page is not repainted, but this line must say so */
function renderStatusLine() {
  const el = typeof document !== "undefined" && document.querySelector ? document.querySelector("#viewStrat .sd-status") : null;
  if (el && VIEW.k === "strat") el.innerHTML = labSafe(() => statusLineHtml(VIEW.name), el.innerHTML);
}
/* The sidebar sorts itself: Trading = ON with an account, Shadow = ON with none, Off = OFF. A variant set is ONE row (its best member's
   state; its members have none). `labs` = Lab strategies the Desk does not hold yet (never trading). A-Z by label in a section. */
function sideSections(names, st, sets, labs) {
  const out = {trading: [], shadow: [], off: []}, strategies = (st && st.strategies) || {}, book = (st && st.book) || {};
  const warned = new Set();
  let r = st && st.readiness;
  try { r = readinessShown(r, st); } catch (_) { /* the raw checks stand */ }
  for (const c of (r && r.checks) || []) if (c && c.strategy && (c.level === "warn" || c.level === "bad")) warned.add(c.strategy);
  const one = (n) => {
    const s = strategies[n], bk = book[n] || [], isLab = s.cfg.kind === "lab";
    const k = sideKind(s, bk), sh = isLab ? labSafe(() => labShadowNet(n, s), null) : null;
    const state = stratState(n, s);
    return {k, row: {id: n, label: stratLabel(n), warn: warned.has(n), pnl: k === "off" ? null : sh ? sh.net : todayPnl(s), dot: stratDotCls(s, state, bk), title: state}};
  };
  const rank = {trading: 0, shadow: 1, off: 2}, inSet = new Set();
  for (const set of sets || []) {
    const ms = (set.members || []).filter(n => strategies[n] && names.includes(n));
    if (ms.length < 2) continue;
    ms.forEach(n => inSet.add(n));
    const parts = ms.map(one), k = parts.reduce((a, p) => rank[p.k] < rank[a] ? p.k : a, "off");      // its money: the accounts' P&L, never the variants' shadow dollars
    out[k].push({id: set.id, set: set.id, members: ms, label: String(set.name || set.id), warn: ms.some(n => warned.has(n)),
      pnl: k === "trading" ? setDayPnl({members: ms}, st.accounts, st.book) : null, dot: k === "trading" ? "ok" : k, title: ms.length + " variants"});
  }
  for (const n of names) if (strategies[n] && !inSet.has(n)) { const p = one(n); out[p.k].push(p.row); }
  for (const w of labs || []) out[w.on ? "shadow" : "off"].push({id: w.id, lab: w.lab, label: w.label, warn: false, pnl: w.pnl, dot: w.dot, title: w.title});
  for (const k in out) out[k].sort((a, b) => String(a.label).toLowerCase() < String(b.label).toLowerCase() ? -1 : String(a.label).toLowerCase() > String(b.label).toLowerCase() ? 1 : 0);
  return out;
}
/* Lab strategies the Desk does not hold yet: they only run in shadow (ON) or not at all (OFF). */
function sideLabs() {
  return labSafe(() => DESKLAB.strategies.filter(w => !labOnDesk(w)), []).map(w => labSafe(() => ({title: DeskLab.stateText(w, DESKLAB.runner),
    dot: DeskLab.dotClass(w, DESKLAB.runner), id: "lab_" + w.name, lab: w.name, label: DeskLab.label(w), on: w.enabled === true, pnl: DeskLab.todayNet(w)}), null)).filter(Boolean);
}
function renderSide(names, issues) {
  /* A section header: a button that folds its rows (chevron, title, a count while it is shut) and, beside it, the section's own action. */
  const head = (k, title, n, action) => {
    const shut = sideFolded(k);
    return `<div class="sh${shut ? " shut" : ""}"><button class="sh-t" onclick="toggleSide('${k}')" aria-expanded="${!shut}" title="${shut ? "Show" : "Hide"} ${title}">
      <svg class="sh-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 5.5l6.5 6.5L9 18.5"/></svg><span>${title}</span>${shut && n ? `<i>${n}</i>` : ""}</button>${action}</div>`;
  };
  const sel = (k, n) => VIEW.k === k && ((k !== "strat" && k !== "lab" && k !== "group") || VIEW.name === n) ? " sel" : "";
  const labs = sideLabs();
  const sec = sideSections(names, ST, (ST.variants && ST.variants.sets) || [], labs);
  const rowHtml = (r, k) => {
    const click = r.lab ? `setView('lab',${jsArg(r.lab)})` : `setView('strat','${r.set ? r.members[0] : r.id}')`, here = r.lab ? sel("lab", r.lab) : sel("strat", r.set ? r.members[0] : r.id);
    return `<button class="item one${here}" onclick="${click}" aria-current="${here ? "page" : "false"}" title="${esc(r.title || "")}">
      <i class="sd ${r.warn ? "warn" : r.dot}"></i><span class="it"><b>${esc(r.label)}</b></span>
      <span class="ir mono${r.pnl == null || k !== "trading" ? " dim" : ""}">${r.pnl == null ? "" : usdS(r.pnl)}</span></button>`;
  };
  const rowsOf = (k) => sec[k].map(r => rowHtml(r, k)).join("");
  const archN = (DESKLAB.archived || []).length;
  const cycRows = teams().map(g => {
    const gr = (ST.groups || {})[g.id] || {}, on = !!gr.on, n = g.members.length, word = {share: "shared", split: "split"}[gr.mode] || "cycle";
    return `<button class="item one${sel("group", g.id)}" onclick="setView('group',${jsArg(g.id)})" aria-current="${sel("group", g.id) ? "page" : "false"}" title="${on ? "Its team is on" : "Its team is off"}">
      <i class="sd ${on ? "ok" : "off"}"></i><span class="it"><b>${esc(g.name)}${on ? `<span class="tag">${word}</span>` : ""}</b></span>
      <span class="ir mono dim">${n}</span></button>`;
  }).join("") || `<button class="side-more" onclick="openGroupMgr()">None yet · add one</button>`;
  // LIVE as isDemoAcct says: an account the desk does not mark demo or paper is LIVE
  const rank = ([id, a]) => !isDemoAcct(id) ? 0 : a.env === "paper" ? 2 : 1;
  const accts = Object.entries(ST.accounts || {}).sort((a, b) => rank(a) - rank(b));
  const inTrade = (a) => Array.isArray(a.open_positions) && a.open_positions.length > 0;
  const shown = SIDE_ALL ? accts : accts.filter(([, a], i) => i < 12 || inTrade(a));     // one in a trade is never under the cut
  const envTag = (id) => ACCT_TAG_HTML[acctTag(id)];
  const shortId = (t) => { t = String(t); return /^[A-Za-z0-9]{12,}$/.test(t) ? t.slice(0, 4) + " ··" + t.slice(-4) : t; };
  const acctRows = shown.map(([id, a]) => `<button class="item one" onclick="openAccts(${jsArg(id)})" title="${esc((a.label || id) + " · " + (!isDemoAcct(id) ? "Live" : a.env === "paper" ? "Paper" : "Demo") + (a.connected ? "" : " · offline"))}">
      <i class="sd ${a.connected ? "ok" : "warn"}"></i><span class="it"><b>${esc(shortId(a.label || id))}${envTag(id)}${a.connected ? "" : '<span class="tag">offline</span>'}</b>${a.connected && a.day_pnl != null ? `<small>today <span class="${a.day_pnl > 0 ? "pos" : a.day_pnl < 0 ? "neg" : ""}">${DAY_PNL_WORDS(a.day_pnl)}</span></small>` : tradeWords(a) ? `<small>${esc(tradeWords(a))}</small>` : ""}</span>
      <span class="ir mono${a.connected ? "" : " dim"}">${a.connected && a.balance != null ? "$" + fmt(a.balance, 0) : ""}</span></button>`).join("");
  const more = (SIDE_ALL ? accts.length > 12 : shown.length < accts.length)
    ? `<button class="side-more" onclick="SIDE_ALL=!SIDE_ALL;render()">${SIDE_ALL ? "Show fewer" : `Show ${accts.length - shown.length} more`}</button>` : "";
  const last = journalNews(ST.journal)[0];
  $("#side").innerHTML = `
    <button class="nav${sel("today")}" onclick="setView('today')" aria-current="${sel("today") ? "page" : "false"}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
      <span>Today</span><span></span></button>
    ${labSafe(suggestLines, "")}
    ${head("trading", "Trading", sec.trading.length, "")}
    ${sideFolded("trading") ? "" : rowsOf("trading")}
    ${head("shadow", "Shadow", sec.shadow.length, "")}
    ${sideFolded("shadow") ? "" : rowsOf("shadow")}
    ${head("off", "Off", sec.off.length + archN, "")}
    ${sideFolded("off") ? "" : rowsOf("off") + (archN || VIEW.k === "archive" ? `<button class="side-more${sel("archive")}" onclick="setView('archive')">Archive · ${archN}</button>` : "")}
    ${head("teams", "Teams", teams().length, `<button class="sh-btn grp-new" title="Teams: new, delete, add or remove strategies" aria-label="Manage teams" onclick="openGroupMgr()">+</button>`)}
    ${sideFolded("teams") ? "" : cycRows}
    ${head("accts", "Accounts", accts.length, `<button class="sh-btn" title="Add account" aria-label="Add account" onclick="openConnect()">+</button>`)}
    ${sideFolded("accts") ? "" : acctRows + more}
    ${head("act", "Activity", 0, "")}
    ${sideFolded("act") ? "" : `<button class="item${sel("activity")}" onclick="setView('activity')" aria-current="${sel("activity") ? "page" : "false"}">
      <i class="sd ${issues ? (ISSUE_LVL === "bad" ? "bad" : "warn") : "off"}"></i><span class="it"><b>${last && last.et ? "Last event " + esc(hbClock(String(last.et).slice(11, 16))) : "Journal"}</b><small>${issues ? plural(issues, "thing needs", "things need") + " a look" : "Every alert, order and fill"}</small></span><span></span></button>`}`;
}

/* ---- strategy detail ---- */
const EQ = {};
function loadEq(name) {
  const e = EQ[name];
  if (e && (e.busy || Date.now() - e.t < 20000)) return;
  EQ[name] = {days: e ? e.days : null, t: e ? e.t : 0, busy: true};
  fetch(`/api/strategy-live?strategy=${encodeURIComponent(name)}`).then(r => r.ok ? r.json() : null).then(d => {
    EQ[name] = {days: d && d.days ? d.days : {}, t: Date.now()};
    if (VIEW.k === "strat" && VIEW.name === name && !FREEZE) render();
  }).catch(() => { EQ[name] = {days: e && e.days || {}, t: Date.now()}; });
}
/* A cumulative curve as the page draws it: `vals` = the running total a day, `label` the words on its left, `total` its last value. */
/* Cumulative P&L by day as straight steps -- a day's close holds flat until the next one, so the line never shows a dip or a
   hump that did not happen -- with a dollar scale on the left and the first and last day under it (`ends`). */
function eqPlot(vals, label, total, aria, ends, days, notes, second, third) {
  // second: a quieter line (the 3:1's build months beside its unseen ones); third: a dashed one (the two together). Each spans the
  // width on its OWN points, its traded days: never flat on a day it did not trade (owner 2026-10-23). days/notes are vals' own.
  // Each is a smooth line that never overshoots a day's total (DeskLab.smoothPath, owner 2026-10-24).
  const ok = (s) => Array.isArray(s) && s.length > 1;
  const both = vals.concat(ok(second) ? second : [], ok(third) ? third : []);
  const path = (s) => DeskLab.smoothPath(s.map((v, i) => [i / (s.length - 1) * 1000, Y(v)]));
  const lo = Math.min(0, ...both), hi = Math.max(0, ...both), span = hi - lo || 1;
  const Y = (v) => 176 - (v - lo) / span * 150;
  const d = path(vals);
  const mid = lo < 0 && hi > 0 ? 0 : (lo + hi) / 2;                       // zero when the curve crosses it, else halfway
  const ticks = [hi, mid, lo].filter((v, i, a) => a.indexOf(v) === i && (v === hi || v === lo || Math.min(Y(v) - Y(hi), Y(lo) - Y(v)) >= 22));
  const axis = (v) => (v < 0 ? "−$" : "$") + fmt(Math.abs(Math.round(v)), 0);
  const grid = ticks.map(v => `<line class="${v === 0 && lo < 0 ? "eq-zero" : "eq-grid"}" x1="0" y1="${Y(v).toFixed(1)}" x2="1000" y2="${Y(v).toFixed(1)}"/>`).join("");
  /* With the days (ISO dates, one a value): dates along the bottom -- a label a few weeks apart, or a month apart on a long run --
     and a hover that reads out the day under the pointer (see the .eq-plot handler below). `notes` adds a line a day. */
  let xt = "", hover = "", attrs = "";
  if (Array.isArray(days) && days.length === vals.length && vals.length > 1 && days.every((d) => /^\d{4}-\d\d-\d\d$/.test(d))) {
    const n = vals.length, dd = (iso, o) => new Date(iso + "T12:00:00Z").toLocaleDateString("en-US", {...o, timeZone: "UTC"});
    const spanD = (new Date(days[n - 1] + "T12:00:00Z") - new Date(days[0] + "T12:00:00Z")) / 864e5;
    const pct = (i) => i / (n - 1) * 100;
    let at = [];
    if (spanD > 62) {                                                   // a long run: the first trading day of each month
      let prev = "";
      days.forEach((d, i) => { if (d.slice(0, 7) !== prev) { at.push(i); prev = d.slice(0, 7); } });
      const step = Math.ceil(at.length / 6);
      at = at.filter((_, k) => k % step === 0);
    } else {                                                            // a short one: a day label every few days
      const k = Math.min(5, n);
      at = Array.from({length: k}, (_, j) => Math.round(j * (n - 1) / (k - 1)));
    }
    const labs = [];
    at.forEach((i) => {
      if (labs.length && pct(i) - labs[labs.length - 1].p < 15) return;
      const jan = days[i].slice(5, 7) === "01";
      labs.push({p: pct(i), t: spanD > 62 ? dd(days[i], {month: "short", ...(jan || !labs.length ? {year: "numeric"} : {})}) : dd(days[i], {month: "short", day: "numeric"})});
    });
    const endP = 100;
    if (spanD > 62 && endP - labs[labs.length - 1].p >= 18) labs.push({p: endP, t: dd(days[n - 1], {month: "short", day: "numeric"})});
    xt = `<div class="eq-x eq-xt">${labs.map((l) => `<span style="left:${l.p.toFixed(1)}%;transform:translateX(${l.p < 5 ? "0" : l.p > 95 ? "-100%" : "-50%"})">${esc(l.t)}</span>`).join("")}</div>`;
    const data = {d: days, v: vals.map((v) => Math.round(v * 100) / 100), y: vals.map((v) => +(Y(v) / 190 * 100).toFixed(1))};
    if (Array.isArray(notes) && notes.length === n) data.n = notes.map(String);
    attrs = ` data-eq="${esc(JSON.stringify(data))}"`;
    hover = `<i class="eq-rule" hidden></i><i class="eq-hov" hidden></i><div class="eq-tip" hidden></div>`;
  }
  return `<div class="eq"><div class="lb"><span>${esc(label)}</span><b class="mono">${usdS(total)}</b></div>
    <div class="eq-plot"${attrs}><svg viewBox="0 0 1000 190" preserveAspectRatio="none" role="img" aria-label="${esc(aria)}">
      <defs><linearGradient id="hbEqFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="currentColor" stop-opacity=".12"/><stop offset="1" stop-color="currentColor" stop-opacity="0"/></linearGradient></defs>
      ${grid}
      <path class="eq-area" d="${d} L 1000 190 L 0 190 Z"/>${ok(second) ? `<path class="eq-line2" d="${path(second)}"/>` : ""}${ok(third) ? `<path class="eq-line3" d="${path(third)}"/>` : ""}<path class="eq-line" d="${d}"/></svg>
    ${ticks.map(v => `<span class="eq-y" style="top:${(Y(v) / 190 * 100).toFixed(1)}%">${axis(v)}</span>`).join("")}
    <i class="eq-dot" style="left:100%;top:${(Y(vals[vals.length - 1]) / 190 * 100).toFixed(1)}%"></i>${hover}</div>
    ${xt || (ends ? `<div class="eq-x"><span>${esc(ends[0])}</span><span>${esc(ends[1])}</span></div>` : "")}</div>`;
}
const shortDay = (iso) => new Date(iso + "T12:00:00Z").toLocaleDateString("en-US", {month: "short", day: "numeric", timeZone: "UTC"});
function eqChart(name) {
  loadEq(name);
  const days = EQ[name] && EQ[name].days;
  if (!days) return `<div class="eq"><div class="eq-ph"></div></div>`;
  const ks = Object.keys(days).sort();
  if (ks.length < 2) return `<div class="eq-empty">Not enough Desk days yet for a curve.</div>`;
  let cum = 0;
  const vals = ks.map(k => (cum += (days[k].net || 0), cum));
  const notes = ks.map(k => { const t = days[k].trades || 0, w = days[k].wins || 0; return t ? `${t} trade${t === 1 ? "" : "s"} · ${w} win${w === 1 ? "" : "s"}` : ""; });
  return eqPlot(vals, `After fees since ${shortDay(ks[0])}`, cum, "Cumulative net P&L after fees, by day", [shortDay(ks[0]), shortDay(ks[ks.length - 1])], ks, notes);
}

/* The hover on an equity curve: the day under the pointer -- its date, that day's result and the running total. One handler for
   every curve on the page (the markup is painted again often); the numbers come from the plot's own data-eq. */
(function () {
  if (typeof document === "undefined" || typeof document.addEventListener !== "function") return;
  let cur = null;
  const hide = () => { if (!cur) return; for (const c of cur.el.querySelectorAll(".eq-rule, .eq-hov, .eq-tip")) c.hidden = true; cur = null; };
  document.addEventListener("pointermove", (e) => {
    const el = e.target && e.target.closest ? e.target.closest(".eq-plot[data-eq]") : null;
    if (!el) { hide(); return; }
    if (!cur || cur.el !== el) {
      hide();
      let d = null;
      try { d = JSON.parse(el.getAttribute("data-eq")); } catch (_) { return; }
      if (!d || !Array.isArray(d.v) || d.v.length < 2) return;
      cur = {el, d, rule: el.querySelector(".eq-rule"), dot: el.querySelector(".eq-hov"), tip: el.querySelector(".eq-tip")};
    }
    const r = el.getBoundingClientRect(), n = cur.d.v.length;
    const f = Math.max(0, Math.min(1, (e.clientX - r.left) / (r.width || 1))), i = Math.round(f * (n - 1)), x = i / (n - 1) * 100;
    const v = cur.d.v[i], day = v - (i ? cur.d.v[i - 1] : 0), iso = cur.d.d[i];
    const when = new Date(iso + "T12:00:00Z").toLocaleDateString("en-US", {weekday: "short", month: "short", day: "numeric", year: "numeric", timeZone: "UTC"});
    cur.rule.style.left = x + "%"; cur.dot.style.left = x + "%"; cur.dot.style.top = cur.d.y[i] + "%";
    cur.tip.innerHTML = `<b>${esc(when)}</b><span><i>Day</i><em class="mono ${day < 0 ? "neg" : day > 0 ? "pos" : ""}">${esc(usdS(day))}</em></span>`
      + `<span><i>Total</i><em class="mono">${esc(usdS(v))}</em></span>${cur.d.n && cur.d.n[i] ? `<small>${esc(cur.d.n[i])}</small>` : ""}`;
    cur.rule.hidden = cur.dot.hidden = cur.tip.hidden = false;
    const px = x / 100 * r.width, tw = cur.tip.offsetWidth;                  // the tip sits right of the line, left when it would run off, never past the card's edge
    cur.tip.style.left = Math.max(-10, Math.min(px + 12 > r.width - tw ? px - 12 - tw : px + 12, r.width - tw + 10)) + "px";
    cur.tip.style.transform = "none";
  });
  if (document.documentElement && typeof document.documentElement.addEventListener === "function") document.documentElement.addEventListener("pointerleave", hide);   // the pointer left the window
  document.addEventListener("scroll", hide, true);
})();

/* ---- Lab strategies: rows and page. Every value from the network goes through esc / jsArg. ---- */
/* A Lab strategy's research, as a block of a strategy page: its saved run on the unseen days (DESKRES; the words and numbers
   are DeskLab.results; no prop sim since the makeover, 2026-11-02). The skin moves them into the inspector; `view` is the page's own name
   for that strategy, so the skin never shows one strategy's blocks under another. */
function labResHtml(lab, view) {
  let v;
  try { v = DeskLab.results(DESKRES[lab]); } catch (_) { return ""; }
  const cell = (x) => `<div class="v mono">${esc(x)}</div>`;
  const f = (k, vals, head) => `<div class="${head ? "f fh" : "f"}"><div class="k">${esc(k)}</div>${vals.map(cell).join("")}</div>`;
  const note = (t) => `<div class="labres-note">${esc(t)}</div>`;
  // a Desk straddle's block has two columns (Build | Unseen) and keeps its note when the unseen run is missing; a 3:1 card with its
  // full sample (Both) has one column and no head (owner 2026-10-30)
  const unseen = v.unseen.head
    ? f("", v.unseen.head, true) + v.unseen.rows.map(r => f(r.k, [r.b, r.v])).join("") + (v.unseen.note ? note(v.unseen.note) : "")
    : v.unseen.rows.length ? v.unseen.rows.map(r => f(r.k, [r.v])).join("") + (v.unseen.note ? note(v.unseen.note) : "") : note(v.unseen.note);
  return `<div class="labres" data-for="${esc(view)}">
    <div class="sec"><h2>${esc(v.unseen.title)}</h2><div class="figs labres-unseen${v.unseen.full ? " full" : ""}" data-h="${esc(v.unseen.title)}">${unseen}</div></div></div>`;
}
/* The unseen run's running total as a curve in the page's own content (the Desk's eqPlot), under its Matched-the-backtest block:
   nothing while there is no run (the inspector's block says why). */
function labCurveHtml(lab) {
  let c;
  try { c = DeskLab.curve(DESKRES[lab]); } catch (_) { return ""; }
  if (!c) return "";
  return `<div class="sec"><h2>${esc(c.title)}</h2>${eqPlot(c.vals, c.label, c.total, c.aria, c.ends, c.days, c.notes, c.build, c.both)}</div>`;
}
function todayLabRow(w) {
  const on = w.enabled === true, net = DeskLab.todayNet(w), nm = DeskLab.label(w);
  const sw = `<button class="switch" role="switch" aria-label="${esc(nm)} on or off" aria-checked="${on}"
    title="${esc(DeskLab.switchTitle(on))}"
    onclick="event.stopPropagation();setDeskLab(${jsArg(w.name)}, ${!on})"></button>`;
  const go = `setView('lab',${jsArg(w.name)})`;
  return `<div class="srow" role="button" tabindex="0" onclick="${go}"
      onkeydown="if(event.target===event.currentTarget&&(event.key==='Enter'||event.key===' ')){event.preventDefault();${go}}">
    <div><div class="n">${esc(nm)}<span class="tag" title="${esc(DeskLab.TAG_TITLE)}">Shadow</span></div>
      <div class="sp mono">${esc(DeskLab.specLine(w))}</div></div>
    <div class="rs">${esc(DeskLab.stateText(w, DESKLAB.runner))}</div>
    <div class="rp mono dim" title="${esc(DeskLab.netTitle(w))}">${esc(usdS(net))}</div>${sw}</div>`;
}
/* A Lab strategy's page: built from the blocks of a strategy page (title and switch, state, note, figures, Accounts,
   actions). It shows what the strategy would have done today; nothing on it can send an order. */
function labView(name) {
  const w = DESKLAB.strategies.find(x => x.name === name);
  if (!w) return `<button class="back" onclick="setView('today')">‹ Today</button><div class="feed-empty">${esc(DeskLab.missingText(DESKLAB_OK))}</div>`;
  const on = w.enabled === true, net = DeskLab.todayNet(w), nm = DeskLab.label(w), t = w.today || {}, busy = DESKLAB_BUSY === name;
  const rebuilt = DeskLab.rebuiltNote(w, DESKLAB.runner);
  const isDay = (d) => /^\d{4}-\d\d-\d\d$/.test(String(d));
  const sw = `<button class="switch" role="switch" aria-label="${esc(nm)} on or off" aria-checked="${on}"
    title="${esc(DeskLab.switchTitle(on))}"
    onclick="setDeskLab(${jsArg(w.name)}, ${!on})"></button>`;
  const fig = (f) => `<div class="f"><div class="k">${esc(f.k)}</div><div class="v mono">${esc(f.v)}</div></div>`;
  const orders = (Array.isArray(t.orders) ? t.orders : []).map(DeskLab.orderLine).map(o =>
    `<div class="feed-row"><span class="t">${esc(o.t)}</span><span class="h${o.refused ? " warn" : ""}">${esc(o.text)}</span></div>`);
  const trades = (Array.isArray(t.trades) ? t.trades : []).map(DeskLab.tradeLine).map(x =>
    `<div class="feed-row"><span class="h">${esc(x.text)}</span><span class="t net">${esc(usdS(x.net))}</span></div>`);
  const today = orders.length + trades.length ? `<div class="agroup feed static">${orders.join("")}${trades.join("")}</div>` : `<div class="eq-empty">${esc(DeskLab.EMPTY_DAY)}</div>`;
  const days = (Array.isArray(w.days) ? w.days : []).map(DeskLab.matchLine).map(m =>
    `<div class="feed-row"><span class="t">${esc(isDay(m.date) ? shortDay(m.date) : m.date)}</span><span class="h${m.ok === false ? " warn" : ""}">${esc(m.text)}</span>${m.rebuilt ? '<span class="t dim">rebuilt</span>' : ""}<span class="t net">${esc(usdS(m.net))}</span></div>`);
  const notes = (Array.isArray(w.notes) ? w.notes : []).map(n => `<div class="feed-row"><span class="h">${esc(n)}</span></div>`);
  return `<button class="back" onclick="setView('today')">‹ Today</button>
    <div class="sd-top"><div><h1 class="sd-title">${esc(nm)}</h1><div class="sp mono">${esc(DeskLab.specLine(w))}</div></div>${sw}</div>
    <div class="sd-state"><b>${esc(DeskLab.stateText(w, DESKLAB.runner))}</b>${rebuilt ? ` · ${esc(rebuilt)}` : ""}${net != null ? ` · today would be ${esc(usdS(net))}` : ""}</div>
    <div class="sd-note">${esc(DeskLab.NOTE)}</div>
    <div class="sec"><h2>Today, in shadow</h2>${today}</div>${stratCal("", w.name)}
    <div class="sec"><h2>Matched the backtest</h2>${days.length ? `<div class="agroup feed static">${days.join("")}</div>` : `<div class="eq-empty">${esc(DeskLab.NOT_CHECKED)}</div>`}</div>
    <div class="figs">${DeskLab.figures(w).map(fig).join("")}</div>
    ${labCurveHtml(w.name)}
    ${labResHtml(w.name, w.name)}
    ${notes.length ? `<div class="sec"><h2>On an account the Desk would refuse:</h2><div class="agroup feed static">${notes.join("")}</div></div>` : ""}
    <div class="sec"><h2>Accounts</h2><div class="mcap">${esc(DeskLab.ACCOUNTS_CAPTION)}</div></div>
    <div class="sd-actions">${deskMachine() === "server" ? "" : `<button class="btn btn-outline btn-sm" onclick="openDeskLabInLab(${jsArg(w.name)})" title="The Lab page, on this strategy's 3:1 out-of-sample">Open in the Lab</button>`}
      <button class="btn btn-outline btn-sm" onclick="archiveLabStrat(${jsArg(w.name)})"${busy ? " disabled" : ""} title="Off the Desk and kept. Restore it from Archive any time.">Archive</button></div>`;
}

function stratView(name) {
  const s = ST.strategies[name];
  if (!s) return `<div class="feed-empty">That strategy is not on the desk any more.</div>`;
  if (s.cfg && s.cfg.kind === "lab") return labSafe(() => labDeskView(name, s), `<button class="back" onclick="setView('today')">‹ Today</button><div class="feed-empty">${LAB_FAULT}</div>`);
  const c = s.cfg, state = stratState(name, s), lv = s.live, p = todayPnl(s);
  const execTxt = (c.kind === "bars" ? "A price-action rule on the app's own live bars."
    : c.self_fire ? "The app computes and fires this signal itself." : "Self-fire is off: nothing fires this strategy.")
    + (c.shadow ? " Shadow: signals are journaled, nothing is placed — even when the Desk is ON." : "");
  const fig = (k, v, title) => `<div class="f"${title ? ` title="${esc(title)}"` : ""}><div class="k">${k}</div><div class="v mono">${v}</div></div>`;
  // the same trades as the curve above it, so the three add up: before fees - fees = after fees (the curve's total)
  const eqd = Object.values((EQ[name] && EQ[name].days) || {}), sum = (k) => eqd.reduce((a, d) => a + (d[k] || 0), 0);
  const money = eqd.length
    ? fig("Before fees", usdS(sum("gross")), "Every closed trade of this strategy, on every account, before commissions") +
      fig("Fees (est.)", usdS(sum("net") - sum("gross")), "An estimate: $3.10 a contract, in and out") +
      fig("After fees", usdS(sum("net")), "The total the curve shows")
    : fig("Before fees", usdS(lv ? lv.net : 0), "Every closed trade of this strategy, on every account, before commissions");
  const figs = lv && lv.trades
    ? `<div class="figs">${money}${fig("Win rate", lv.win_rate == null ? "—" : Math.round(lv.win_rate) + "%")}${fig("Trades", lv.trades)}${fig("Avg per trade", usd(lv.avg_trade), "Before fees, per trade")}${fig("Avg slip", (lv.avg_slip_pts ?? "—") + " pts")}</div>`
    : `<div class="eq-empty">No Desk trades yet.</div>`;
  const links = `<div class="qlinks">${s.research && s.research.rows ? `<button class="btn btn-quiet btn-sm" onclick="openRes('${name}')">Old backtest (before 3:1)</button>` : ""}
    <button class="btn btn-quiet btn-sm" onclick="openLive('${name}')">Desk calendar</button>${actBtn("s:" + name)}</div>`;
  const accts = ST.accounts || {}, asg = (ST.book && ST.book[name]) || [];
  const rows = asg.map(a => acctRow(a.account, {qty: a.qty, strategy: name})).join("");
  const free = Object.keys(accts).filter(id => !asg.some(a => a.account === id));
  const addForm = Object.keys(accts).length
    ? (free.length ? `<div style="position:relative;display:inline-block;margin-top:10px">
        <button class="btn btn-quiet noarrow btn-sm" onclick="toggleAsgMenu('${name}')" aria-haspopup="menu">+ Assign an account</button>
        <div class="amenu" id="amenu-${name}" role="menu" hidden>` +
        free.map(id => `<button class="mi2" role="menuitem" onclick="pickAsg('${name}',${jsArg(id)},${c.qty})">${esc(accts[id].label || id)}</button>`).join("") + `</div></div>` : "")
    : `<div class="mcap">Add an account to run this strategy.</div>`;
  const test = (ST && !ST.armed && c.enabled) ? `<button class="btn btn-outline btn-sm" onclick="testFire('${name}')">Test fire · dry</button>` : "";
  // the Desk's own straddles: the tester twin that mirrors them (its saved runs are the unseen metrics), and whether the card may be hidden
  const twin = DESKRES[name] && typeof DESKRES[name].twin === "string" ? DESKRES[name].twin : "";
  const hasRun = !!(DESKRES[name] && DESKRES[name].unseen && DESKRES[name].unseen.id);
  const sw = `<button class="switch" role="switch" aria-label="${esc(stratLabel(name))} on or off" aria-checked="${c.enabled}"
    title="${c.enabled ? "ON — this strategy runs and executes" : "OFF — ignores all signals"}"
    onclick="toggleStrat('${name}', ${!c.enabled})"></button>`;
  return `<button class="back" onclick="setView('today')">‹ Today</button>
    <div class="sd-top"><div><h1 class="sd-title">${esc(stratLabel(name))}</h1><div class="sp mono">${esc(specOf(c, name))}</div></div>${sw}</div>
    <div class="sd-state"><b>${esc(state)}</b>${p != null ? ` · today ${usdS(p)}` : ""}</div>
    <div class="sd-note">${esc(execTxt)}</div>
    ${eqChart(name)}${figs}${links}
    ${twin ? labCurveHtml(name) + labResHtml(name, name) : ""}
    <div class="sec"><h2>Accounts</h2>${rows ? `<div class="agroup">${rows}</div><div class="mcap acct-note">An account's balance and its green or red figure are the whole account: every strategy and every manual trade on it, not this strategy alone.</div>` : ""}${rotationHtml(name)}${addForm}</div>
    ${deskChangesHtml("s:" + name)}
    <div class="sd-actions"><button class="btn btn-outline btn-sm" onclick="flattenStrat('${name}')" title="Flattens its positions and switches it off">Flatten &amp; turn off</button>
      ${twin && deskMachine() !== "server" ? `<button class="btn btn-outline btn-sm" onclick="openBuiltinInLab(${jsArg(name)})" title="The Lab page, on this strategy's tester twin (it follows the Desk's setting)">Open in the Lab</button>
      <button class="btn btn-outline btn-sm" onclick="openBuiltinInLab(${jsArg(name)}, true)"${hasRun ? "" : " disabled"} title="Its twin's run on the unseen days, on the chart, trade by trade">Show on chart</button>` : ""}
      <button class="btn btn-outline btn-sm" onclick="archiveBuiltin(${jsArg(name)})"${DESKLAB_BUSY || ((ST.book && ST.book[name]) || []).length ? " disabled" : ""} title="Switched off and off the Desk's list, kept. Restore it from Archive any time.">Archive</button>${test}</div>`;
}

/* A dry run of a built-in straddle: what it would send, nothing sent. */
async function testFire(name) {
  const r = await post("/api/test-alert", {strategy: name});
  toast(testFireWords(r), 8000); refresh();
}
/* {sent:{upper, lower}, result:{ok, accounts}} or a refusal ({ok:false, reason} / a 404's {detail}) -> one sentence */
function testFireWords(r) {
  const res = (r && r.result) || r || {}, s = (r && r.sent) || {}, n = res.accounts;
  if (!res.ok) return `Dry run refused: ${res.reason || res.detail || "no answer"}.`;
  return `Dry run: it would have sent a buy stop at ${fmtPx(s.upper)} and a sell stop at ${fmtPx(s.lower)}` +
    `${typeof n === "number" ? ` on ${n} account${n === 1 ? "" : "s"}` : ""}. Nothing was sent.`;
}
