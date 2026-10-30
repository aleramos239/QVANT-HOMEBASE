/* ---- sidebar ---- */
function renderSide(names, hiddenCount, issues) {
  /* A section header: a button that folds its rows (chevron, title, a count while it is shut) and, beside it, the section's own action. */
  const head = (k, title, n, action) => {
    const shut = !!SIDE_FOLD[k];
    return `<div class="sh${shut ? " shut" : ""}"><button class="sh-t" onclick="toggleSide('${k}')" aria-expanded="${!shut}" title="${shut ? "Show" : "Hide"} ${title}">
      <svg class="sh-chev" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 5.5l6.5 6.5L9 18.5"/></svg><span>${title}</span>${shut && n ? `<i>${n}</i>` : ""}</button>${action}</div>`;
  };
  const sel = (k, n) => VIEW.k === k && ((k !== "strat" && k !== "lab" && k !== "group" && k !== "family") || VIEW.name === n) ? " sel" : "";
  /* every strategy's row by its id (a Desk name, or lab_<name> for a Lab one the Desk does not hold yet), so a group can take it */
  const rowOf = {};
  for (const n of names) {
    const s = ST.strategies[n], state = stratState(n, s), sh = s.cfg.kind === "lab" ? labSafe(() => labShadowNet(n, s), null) : null, p = sh ? sh.net : todayPnl(s);
    rowOf[n] = `<button class="item one${sel("strat", n)}" onclick="setView('strat','${n}')" aria-current="${sel("strat", n) ? "page" : "false"}" title="${esc(state)}">
      <i class="sd ${stratDotCls(s, state, (ST.book && ST.book[n]) || [])}"></i><span class="it"><b>${esc(famShort(n) || stratLabel(n))}</b></span>
      <span class="ir mono${p == null || sh ? " dim" : ""}">${p == null ? "" : usdS(p)}</span></button>`;
  }
  const labIds = labSafe(() => DESKLAB.strategies.filter(w => !labOnDesk(w)).map(w => {
    const id = "lab_" + w.name;
    rowOf[id] = labSafe(() => labSideRow(w, sel, famShort(id)), "");
    return id;
  }), []);
  /* families fold their variants under one row, each by its short name (owner 2026-10-29); the strategies in no family follow.
     Account cycles (the Desk groups) are their own section below: a variant can be in a family and a cycle at once. */
  const inFam = new Set(DESKFAM.families.flatMap(f => f.members));
  const loose = names.concat(labIds).filter(id => !inFam.has(id)).map(id => rowOf[id] || "").join("");
  const famBlocks = DESKFAM.families.filter(f => !famArchived(f)).map(f => {      // a family all in the Archive sits there, not here
    const k = "f:" + f.id, rows = f.members.map(id => rowOf[id]).filter(Boolean);
    const opened = sel("family", f.id) !== "";
    const open = `<button class="sh-btn" title="Open ${esc(f.name)}" aria-label="Open ${esc(f.name)}"${opened ? ' aria-current="page" style="color:var(--foreground)"' : ""} onclick="setView('family',${jsArg(f.id)})">›</button>`;
    return head(k, esc(f.name), rows.length, open).replace('class="sh', 'class="sh sub') + (SIDE_FOLD[k] ? "" : rows.join("") || `<button class="side-more" onclick="openGroupMgr()">Empty · add strategies</button>`);
  }).join("");
  const cycRows = DESKGROUPS.groups.map(g => {
    const on = !!((ST.groups || {})[g.id] || {}).on, n = g.members.length;
    return `<button class="item one${sel("group", g.id)}" onclick="setView('group',${jsArg(g.id)})" aria-current="${sel("group", g.id) ? "page" : "false"}" title="${on ? "Its account cycle is on" : "Its account cycle is off"}">
      <i class="sd ${on ? "ok" : "off"}"></i><span class="it"><b>${esc(g.name)}${on ? '<span class="tag">cycle</span>' : ""}</b></span>
      <span class="ir mono dim">${n}</span></button>`;
  }).join("") || `<button class="side-more" onclick="openGroupMgr()">None yet · add one</button>`;
  // LIVE as isDemoAcct says: an account the desk does not mark demo or paper is LIVE
  const rank = ([id, a]) => !isDemoAcct(id) ? 0 : a.env === "paper" ? 2 : 1;
  const accts = Object.entries(ST.accounts || {}).sort((a, b) => rank(a) - rank(b));
  const inTrade = (a) => Array.isArray(a.open_positions) && a.open_positions.length > 0;
  const shown = SIDE_ALL ? accts : accts.filter(([, a], i) => i < 12 || inTrade(a));     // one in a trade is never under the cut
  const envTag = (id, a) => !isDemoAcct(id) ? '<span class="tag-live">LIVE</span>' : a.env === "paper" ? '<span class="tag-paper" style="margin-left:6px">PAPER</span>'
    : '<span class="tag" style="margin-left:6px">DEMO</span>';
  const shortId = (t) => { t = String(t); return /^[A-Za-z0-9]{12,}$/.test(t) ? t.slice(0, 4) + " ··" + t.slice(-4) : t; };
  const acctRows = shown.map(([id, a]) => `<button class="item one" onclick="openAccts(${jsArg(id)})" title="${esc((a.label || id) + " · " + (!isDemoAcct(id) ? "Live" : a.env === "paper" ? "Paper" : "Demo") + (a.connected ? "" : " · offline"))}">
      <i class="sd ${a.connected ? "ok" : "warn"}"></i><span class="it"><b>${esc(shortId(a.label || id))}${envTag(id, a)}${a.connected ? "" : '<span class="tag">offline</span>'}</b>${a.connected && a.day_pnl != null ? `<small>today <span class="${a.day_pnl > 0 ? "pos" : a.day_pnl < 0 ? "neg" : ""}">${DAY_PNL_WORDS(a.day_pnl)}</span></small>` : tradeWords(a) ? `<small>${esc(tradeWords(a))}</small>` : ""}</span>
      <span class="ir mono${a.connected ? "" : " dim"}">${a.connected && a.balance != null ? "$" + fmt(a.balance, 0) : ""}</span></button>`).join("");
  const more = (SIDE_ALL ? accts.length > 12 : shown.length < accts.length)
    ? `<button class="side-more" onclick="SIDE_ALL=!SIDE_ALL;render()">${SIDE_ALL ? "Show fewer" : `Show ${accts.length - shown.length} more`}</button>` : "";
  const last = journalNews(ST.journal)[0];
  $("#side").innerHTML = `
    <button class="nav${sel("today")}" onclick="setView('today')" aria-current="${sel("today") ? "page" : "false"}">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>
      <span>Today</span><span></span></button>
    ${head("strat", "Strategies", names.length + labIds.length, `<span class="sh-acts"><button class="sh-btn grp-new" title="Families and account cycles: new, delete, add or remove strategies" aria-label="Manage families and account cycles" onclick="openGroupMgr()">+</button><button class="sh-btn" title="Manage algos" aria-label="Manage algos" onclick="openAlgoMgr()">⋯</button></span>`)}
    ${SIDE_FOLD.strat ? "" : famBlocks + loose + (hiddenCount ? `<button class="side-more" onclick="openAlgoMgr()">${hiddenCount} hidden · Manage</button>` : "")
      + ((DESKLAB.archived || []).length || VIEW.k === "archive" ? `<button class="side-more${sel("archive")}" onclick="setView('archive')">Archive · ${(DESKLAB.archived || []).length}</button>` : "")}
    ${head("cyc", "Account cycles", DESKGROUPS.groups.length, `<button class="sh-btn" title="Account cycles: new, delete, add or remove strategies" aria-label="Manage account cycles" onclick="openGroupMgr()">+</button>`)}
    ${SIDE_FOLD.cyc ? "" : cycRows}
    ${head("accts", "Accounts", accts.length, `<button class="sh-btn" title="Add account" aria-label="Add account" onclick="openConnect()">+</button>`)}
    ${SIDE_FOLD.accts ? "" : acctRows + more}
    ${head("act", "Activity", 0, "")}
    ${SIDE_FOLD.act ? "" : `<button class="item${sel("activity")}" onclick="setView('activity')" aria-current="${sel("activity") ? "page" : "false"}">
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
function labSideRow(w, sel, short) {      // short: its name inside a family ("1.5R"), else its own label
  const net = DeskLab.todayNet(w);
  return `<button class="item one${sel("lab", w.name)}" onclick="setView('lab',${jsArg(w.name)})" aria-current="${sel("lab", w.name) ? "page" : "false"}" title="${esc(DeskLab.stateText(w, DESKLAB.runner))}">
      <i class="sd ${esc(DeskLab.dotClass(w, DESKLAB.runner))}"></i><span class="it"><b>${esc(short || DeskLab.label(w))}</b></span>
      <span class="ir mono dim">${net == null ? "" : esc(usdS(net))}</span></button>`;
}
/* A Lab strategy's research, as two blocks of a strategy page: its saved run on the unseen days and the prop sim of its runs
   (DESKRES; the words and numbers are DeskLab.results). The skin moves them into the inspector; `view` is the page's own name
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
  const prop = !v.prop.rows.length ? note(v.prop.note)
    : v.prop.head ? f("", v.prop.head, true) + v.prop.rows.map(r => f(r.k, [r.build, r.unseen])).join("")
    : v.prop.rows.map(r => f(r.k, [r.v])).join("");
  return `<div class="labres" data-for="${esc(view)}">
    <div class="sec"><h2>${esc(v.unseen.title)}</h2><div class="figs labres-unseen${v.unseen.full ? " full" : ""}" data-h="${esc(v.unseen.title)}">${unseen}</div></div>
    <div class="sec"><h2>${esc(v.prop.title)}</h2><div class="figs labres-prop" data-h="${esc(v.prop.title)}">${prop}</div></div></div>`;
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
      <button class="btn btn-outline btn-sm" onclick="archiveLabStrat(${jsArg(w.name)})"${busy ? " disabled" : ""} title="Off the Desk and kept. Restore it from Archive any time.">Archive</button>
      <button class="btn btn-outline btn-sm" onclick="removeLabRow(${jsArg(w.name)})"${busy ? " disabled" : ""} title="Takes it off the Desk. Its history is kept. Archive keeps it to restore from the Desk.">Remove from Desk</button></div>`;
}

function stratView(name) {
  const s = ST.strategies[name];
  if (!s) return `<div class="feed-empty">That strategy is not on the desk any more.</div>`;
  if (s.cfg && s.cfg.kind === "lab") return labSafe(() => labDeskView(name, s), `<button class="back" onclick="setView('today')">‹ Today</button><div class="feed-empty">${LAB_FAULT}</div>`);
  const c = s.cfg, state = stratState(name, s), lv = s.live, p = todayPnl(s);
  const execTxt = (c.kind === "bars" ? "A price-action rule on the app's own live bars."
    : c.self_fire ? "The app computes and fires this signal itself." : "Self-fire is off: nothing fires this strategy.")
    + (c.shadow ? " Shadow: signals are journaled, nothing is placed — even when armed." : "");
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
  const hide = hideInfo(name);
  const sw = `<button class="switch" role="switch" aria-label="${esc(stratLabel(name))} on or off" aria-checked="${c.enabled}"
    title="${c.enabled ? "ON — this strategy runs and executes" : "OFF — ignores all signals"}"
    onclick="toggleStrat('${name}', ${!c.enabled})"></button>`;
  return `<button class="back" onclick="setView('today')">‹ Today</button>
    <div class="sd-top"><div><h1 class="sd-title">${esc(stratLabel(name))}</h1><div class="sp mono">${esc(specOf(c, name))}</div></div>${sw}</div>
    <div class="sd-state"><b>${esc(state)}</b>${p != null ? ` · today ${usdS(p)}` : ""}</div>
    <div class="sd-note">${esc(execTxt)}</div>
    ${setupHtml(name, s)}
    ${eqChart(name)}${figs}${links}
    ${twin ? labCurveHtml(name) + labResHtml(name, name) : ""}
    <div class="sec"><h2>Accounts</h2>${rows ? `<div class="agroup">${rows}</div><div class="mcap acct-note">An account's balance and its green or red figure are the whole account: every strategy and every manual trade on it, not this strategy alone.</div>` : ""}${rotationHtml(name)}${addForm}</div>
    ${deskChangesHtml("s:" + name)}
    <div class="sd-actions"><button class="btn btn-outline btn-sm" onclick="flattenStrat('${name}')" title="Flattens its positions and switches it off">Flatten &amp; turn off</button>
      ${twin && deskMachine() !== "server" ? `<button class="btn btn-outline btn-sm" onclick="openBuiltinInLab(${jsArg(name)})" title="The Lab page, on this strategy's tester twin (it follows the Desk's setting)">Open in the Lab</button>
      <button class="btn btn-outline btn-sm" onclick="openBuiltinInLab(${jsArg(name)}, true)"${hasRun ? "" : " disabled"} title="Its twin's run on the unseen days, on the chart, trade by trade">Show on chart</button>` : ""}
      <button class="btn btn-outline btn-sm" onclick="archiveBuiltin(${jsArg(name)})"${DESKLAB_BUSY || ((ST.book && ST.book[name]) || []).length ? " disabled" : ""} title="Switched off and off the Desk's list, kept. Restore it from Archive any time.">Archive</button>
      <button class="btn btn-outline btn-sm" onclick="removeBuiltin(${jsArg(name)})"${hide.locked ? " disabled" : ""} title="${esc(hide.locked ? hide.reason + ". Switch it off first." : "Takes it off the Desk's list. Bring it back from Manage algos; its settings and history stay.")}">Remove from Desk</button>${test}</div>
    ${hide.locked ? `<div class="mcap">Remove from Desk: ${esc(hide.reason)}. Switch it off first.</div>` : ""}`;
}

/* WP1.14 The Setup summary at the top of a strategy's page: the whole setup in one place, read only. The window and the days are
   shown, never edited here (editing them would change what it trades). Red lines first: what still stops it trading. */
function setupHtml(name, s) {
  const c = s.cfg || {}, lab = c.kind === "lab" ? (s.lab || {}) : null, book = (ST.book && ST.book[name]) || [], accts = ST.accounts || {};
  const kind = (id) => isDemoAcct(id) ? accts[id].env : "live", word = (id) => kind(id) === "live" ? "LIVE" : kind(id);   // as isDemoAcct
  const red = [...(lab && DeskLab.accountsLock(s).caption === DeskLab.LIMITS_CAPTION ? ["Limits needed first"] : []),
    ...(ST.armed ? [] : ["Desk not armed"])];
  const cyc = Object.values(ST.groups || {}).find(g => (g.members || []).includes(name));
  const dg = cyc ? null : DESKGROUPS.groups.find(g => g.members.includes(name));
  const qs = [...new Set(book.map(a => +a.qty || 1))], whole = (v) => usd(v).replace(/\.00$/, "");
  const n = (e) => book.filter(a => kind(a.account) === e).length, set = book.some(a => a.size);   // a row with its own size wins
  const own = (a) => a.size || a.stop_after ? AcctSet.words(a) : `×${+a.qty || 1}`;
  const rows = [
    ["Accounts", book.map(a => `${acctShort(a.account)} ${word(a.account)} ${own(a)}`.replace("  ", " ")).join(" · ") || "none yet"],
    ["LIVE / paper", book.length ? [["LIVE", n("live")], ["demo", n("demo")], ["paper", n("paper")]].filter(x => x[1]).map(x => `${x[0]} on ${x[1]}`).join(" · ") || "—"
      : lab ? "no account: it runs in shadow" : "no account"],
    ["Size", lab && cyc && cyc.on && cyc.risk_usd > 0 ? `${whole(cyc.risk_usd)} at risk a trade (the ${cyc.name} group sizes it)`
      : lab && set ? "set on each account (see Accounts)"
      : lab && lab.own_size === true ? (Number((lab.params || {}).risk) > 0 ? `${whole(Number(lab.params.risk))} at risk a trade` : "it sizes each trade itself")   // as DeskLab.ordersGo
      : qs.length === 1 ? `${qs[0]} contract${qs[0] === 1 ? "" : "s"} an account` : qs.length ? `${Math.min(...qs)}-${Math.max(...qs)} contracts an account` : "—"],
    ...(lab && lab.limits ? [["Limits", DeskLab.limitsRows(lab.limits).map(x => `${x.k} ${x.v}`).join(" · ")]] : []),
    ["Window", lab ? specOf(c, name) : [c.kind === "bars" ? `${c.bar_minutes}-minute bars` : c.fire_et ? `fires ${String(c.fire_et).slice(0, 5)} ET` : "",
      c.flat_et ? `flat by ${c.flat_et} ET` : "", (c.only_dates || []).length ? `only on ${c.only_dates.length} set day${c.only_dates.length === 1 ? "" : "s"}` : "every weekday"]
      .filter(Boolean).join(" · ")],
    ["Group", cyc ? `${cyc.name} (account cycle ${cyc.on ? "ON" : "OFF"}${cyc.on && cyc.next ? `, next ${acctShort(cyc.next)}` : ""})` : dg ? dg.name : "none"],
    ...(machineWords() ? [["Machine", machineWords().replace(/^on /, "")]] : []),
  ];
  return `<div class="sec setup"><h2>Setup</h2>${red.map(t => `<div class="mcap warn">${esc(t)}</div>`).join("")}
    <div class="agroup feed static">${rows.map(([k, v]) => `<div class="feed-row"><span class="t">${esc(k)}</span><span class="h">${esc(v)}</span></div>`).join("")}</div></div>`;
}
