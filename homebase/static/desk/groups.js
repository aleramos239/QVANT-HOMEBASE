/* ---- DESK GROUPS (2026-10-11): named sets of strategies that run together (an eval group, a funded group ...), kept by the chart
   service (GET /api/tester/deskgroups). A group trades only through its ACCOUNT CYCLE (cycleHtml below; the Desk's engine keeps it, and
   the chart service makes it follow every rename, move and delete, server side). Group ids are never reused. A
   strategy is in ONE group at most; the same code tried two ways (say for an eval and for a funded account) is two strategies, each
   in its own group. A group's combined results are its members' SAVED runs put together as one account's trades
   (GET /api/tester/deskgroups/results, asked only while a group's page is open). The words are DeskLab.groupPage. ---- */
let DESKGROUPS = {groups: [], ok: null}, DESKGROUPS_BUSY = false;       // ok: null = no read finished yet
let DESKGRES = {}, DESKGRES_BUSY = false;
const GROUP_ID = /^g\d{1,4}$/;
const groupOf = (id) => DESKGROUPS.groups.find(g => g.id === id) || null;
function takeGroups(list) {      // only well-formed groups are kept; a wrong shape is dropped, never thrown on
  return (Array.isArray(list) ? list : []).filter(g => g && typeof g === "object" && GROUP_ID.test(String(g.id)) && typeof g.name === "string")
    .map(g => ({id: g.id, name: g.name, kind: ["eval", "funded", "together"].includes(g.kind) ? g.kind : "together",
      members: (Array.isArray(g.members) ? g.members : []).filter(m => typeof m === "string")}));
}
async function loadDeskGroups() {
  if (DEMO || document.hidden || DESKGROUPS_BUSY) return;
  DESKGROUPS_BUSY = true;
  try {
    const r = await fetch(CHART + "/api/tester/deskgroups");
    if (!r.ok) throw new Error("HTTP " + r.status);
    const j = await r.json(), next = takeGroups(j && j.groups);
    const changed = DESKGROUPS.ok !== true || JSON.stringify(next) !== JSON.stringify(DESKGROUPS.groups);
    DESKGROUPS = {groups: next, ok: true};
    const famChanged = await loadDeskFamilies();
    if ((changed || famChanged) && ST && !FREEZE) render();
    if (VIEW.k === "group") loadDeskGroupRes();
  } catch (_) { /* the chart service does not answer: keep what was shown */ }
  finally { DESKGROUPS_BUSY = false; }
}
async function loadDeskGroupRes() {
  if (DEMO || document.hidden || DESKGRES_BUSY || VIEW.k !== "group") return;
  DESKGRES_BUSY = true;
  try {
    const r = await fetch(CHART + "/api/tester/deskgroups/results");
    if (!r.ok) throw new Error("HTTP " + r.status);
    const j = await r.json(), next = j && j.results && typeof j.results === "object" ? j.results : {};
    const changed = JSON.stringify(next) !== JSON.stringify(DESKGRES);
    DESKGRES = next;
    if (changed && ST && !FREEZE) render();
  } catch (_) { /* keep what was shown */ }
  finally { DESKGRES_BUSY = false; }
}
/* One change to the groups: create {name, kind} | rename {id, name} | kind {id, kind} | delete {id} | move {strategy, group|null}.
   The service answers with all the groups; a refusal says why in words and changes nothing. */
async function groupPost(action, body) {
  const r = await chartPost("/api/tester/deskgroups/" + action, body);
  if (r && r.ok === true && Array.isArray(r.groups)) {
    DESKGROUPS = {groups: takeGroups(r.groups), ok: true};
    if (VIEW.k === "group" && !groupOf(VIEW.name)) VIEW = {k: "today"};
    if (ST) render();
    renderGroupMgr(true);
    loadDeskGroupRes();
    return true;
  }
  if (!DEMO) toast(String((r && r.detail) || "The group could not be changed."), 6000);
  renderGroupMgr(true);          // put the controls back as they were
  return false;
}
/* ---- DESK FAMILIES (owner 2026-10-29): variants of one idea (the same code at other targets or stops) folded under one sidebar
   row, and one page that sets them side by side. Display only: each variant keeps its own switch, accounts and record, and may sit
   in an account cycle too. Kept by the chart service (GET /api/tester/deskfamilies, read with the groups). ---- */
let DESKFAM = {families: [], ok: null};
const FAMILY_ID = /^f\d{1,4}$/;
const FAMILY_FAULT = "The family could not be shown.";
const famOf = (id) => DESKFAM.families.find(f => f.id === id) || null;
const famOfStrat = (sid) => DESKFAM.families.find(f => f.members.includes(sid)) || null;
const famShort = (sid) => { const f = famOfStrat(sid); return (f && f.short[sid]) || ""; };
const archivedId = (w) => w.builtin === true ? w.name : "lab_" + w.name;      // an archived row's Desk id, as families list it
const famArchived = (f) => { const a = new Set((DESKLAB.archived || []).map(archivedId)); return f.members.length > 0 && f.members.every(m => a.has(m)); };
function takeFamilies(list) {      // only well-formed families are kept; a wrong shape is dropped, never thrown on
  return (Array.isArray(list) ? list : []).filter(f => f && typeof f === "object" && FAMILY_ID.test(String(f.id)) && typeof f.name === "string")
    .map(f => {
      const members = (Array.isArray(f.members) ? f.members : []).filter(m => typeof m === "string"), short = {};
      for (const m of members) if (f.short && typeof f.short[m] === "string" && f.short[m]) short[m] = f.short[m];
      return {id: f.id, name: f.name, members, short};
    });
}
async function loadDeskFamilies() {      // true when the families changed (the caller repaints)
  try {
    const r = await fetch(CHART + "/api/tester/deskfamilies");
    if (!r.ok) throw new Error("HTTP " + r.status);
    const j = await r.json(), next = takeFamilies(j && j.families);
    const changed = DESKFAM.ok !== true || JSON.stringify(next) !== JSON.stringify(DESKFAM.families);
    DESKFAM = {families: next, ok: true};
    return changed;
  } catch (_) { return false; }      // an older chart service has no families: the sidebar shows none
}
/* One change to the families: create {name} | rename {id, name} | delete {id} | move {strategy, family|null, short?} | short {strategy, short}. */
async function familyPost(action, body) {
  const r = await chartPost("/api/tester/deskfamilies/" + action, body);
  if (r && r.ok === true && Array.isArray(r.families)) {
    DESKFAM = {families: takeFamilies(r.families), ok: true};
    if (VIEW.k === "family" && !famOf(VIEW.name)) VIEW = {k: "today"};
    if (ST) render();
    renderGroupMgr(true);
    return true;
  }
  if (!DEMO) toast(String((r && r.detail) || "The family could not be changed."), 6000);
  renderGroupMgr(true);
  return false;
}
/* One variant as its family's page shows it, from what the page already holds (the Desk's status, the Lab list, DESKRES). */
function famVariant(sid) {
  const s = ST && ST.strategies && ST.strategies[sid], name = sid.indexOf("lab_") === 0 ? sid.slice(4) : sid;
  const res = DESKRES[name] || {}, side = (b) => b && b.net != null ? `${usdS(b.net)} · ${b.trades} tr` : "—";
  const v = {sid, short: famShort(sid), full: side(res.both)};      // the full sample only (owner 2026-10-30)
  if (s) {
    const book = (ST.book && ST.book[sid]) || [], sh = s.cfg.kind === "lab" ? labSafe(() => labShadowNet(sid, s), null) : null;
    v.state = stratState(sid, s);
    return Object.assign(v, {label: stratLabel(sid), today: sh ? sh.net : todayPnl(s), accts: book.length});
  }
  const w = labSafe(() => DESKLAB.strategies.find(x => x.name === name), null);
  if (!w) return null;      // not on the Desk any more
  return Object.assign(v, {label: DeskLab.label(w), state: DeskLab.stateText(w, DESKLAB.runner), today: DeskLab.todayNet(w), accts: 0});
}
function familyView(id) {
  const f = famOf(id);
  if (!f) return `<button class="back" onclick="setView('today')">‹ Today</button><div class="feed-empty">That family is not there any more.</div>`;
  const vs = f.members.map(famVariant), gone = f.members.filter((_, i) => !vs[i]);
  const rows = vs.filter(Boolean).map(v => `<div class="feed-row" role="button" tabindex="0" title="${esc(v.label)} · ${esc(v.state)}" onclick="openGroupMember(${jsArg(v.sid)})"
      onkeydown="if(event.target===event.currentTarget&&(event.key==='Enter'||event.key===' ')){event.preventDefault();openGroupMember(${jsArg(v.sid)})}">
      <span class="h">${esc(v.short || v.label)} · <span class="dim">${esc(v.state)}</span></span>
      <span class="t">${esc(v.full)}</span>
      <span class="t net">${v.today == null ? "—" : esc(usdS(v.today))}</span><span class="t dim">${v.accts || "none"}</span></div>`);
  return `<button class="back" onclick="setView('today')">‹ Today</button>
    <div class="sd-top"><div><h1 class="sd-title">${esc(f.name)}</h1><div class="sp mono">${rows.length} variant${rows.length === 1 ? "" : "s"}</div></div></div>
    <div class="sd-note">A family only puts these rows together. Each variant keeps its own switch, accounts and settings, and trades on its own.</div>
    ${rows.length ? `<div class="sec"><h2>Variants</h2><div class="agroup feed static fam-table">
      <div class="feed-row"><span class="h dim">Variant</span><span class="t dim">Full sample</span><span class="t dim">Today</span><span class="t dim">Accounts</span></div>
      ${rows.join("")}</div></div>` : `<div class="eq-empty">No variants yet. Add them in Manage.</div>`}
    ${gone.length ? `<div class="sec"><h2>Not on the Desk any more</h2><div class="agroup feed static">${gone.map(g => `<div class="feed-row"><span class="h">${esc(g)}</span></div>`).join("")}</div></div>` : ""}
    <div class="sd-actions"><button class="btn btn-outline btn-sm" onclick="openGroupMgr()">Manage</button>
      <button class="btn btn-outline btn-sm" onclick="archiveFamily(${jsArg(f.id)})"${DESKLAB_BUSY ? " disabled" : ""} title="All of them off the Desk, switched off, kept together in Archive">Archive family</button>
      <button class="btn btn-outline btn-sm" onclick="deleteFamily(${jsArg(f.id)})" title="The strategies stay on the Desk, in no family.">Delete family</button></div>`;
}
async function deleteFamily(id) {
  const f = famOf(id);
  if (f && await confirmDlg(`Delete the ${f.name} family?`, "Its strategies stay on the Desk as they are, in no family.", "Delete", false))
    await familyPost("delete", {id});
}

/* A group's page (VIEW {k: "group", name: <id>}): its members' saved runs put together -- the unseen days first (curve), the build days
   beside them, the prop sim on LucidPro -- then the members and any left out of the sum, with why. Nothing here runs a backtest. */
const GROUP_FAULT = "The group could not be shown.";
function openGroupMember(id) {      // a member's own page: the Desk's if it holds it, else the Lab strategy's
  id = String(id);
  if (ST && ST.strategies && ST.strategies[id]) setView("strat", id);
  else if (id.indexOf("lab_") === 0) setView("lab", id.slice(4));
  else setView("today");
}
function groupView(id) {
  const g = groupOf(id);
  if (!g) return `<button class="back" onclick="setView('today')">‹ Today</button><div class="feed-empty">${esc(DeskLab.GROUP_MISSING)}</div>`;
  const p = DeskLab.groupPage(g, DESKGRES[g.id]);
  const cell = (x) => `<div class="v mono">${esc(x)}</div>`;
  const f = (k, vals, head) => `<div class="${head ? "f fh" : "f"}"><div class="k">${esc(k)}</div>${vals.map(cell).join("")}</div>`;
  const note = (t) => `<div class="labres-note">${esc(t)}</div>`;
  const two = (b) => !b.rows.length ? note(b.note) : b.head ? f("", b.head, true) + b.rows.map(r => f(r.k, "both" in r ? [r.build, r.unseen, r.both] : [r.build, r.unseen])).join("")
    : b.rows.map(r => f(r.k, [r.v])).join("");      // the full sample (Both) only: one column, no head (owner 2026-10-30)
  const three = (b) => b.head && b.head.length === 3 ? " three" : "";
  const days = p.days.rows.length ? p.days.rows.map(r => f(r.k, [r.v])).join("") : note(p.figs.note);
  const members = p.members.map(m => `<div class="feed-row" role="button" tabindex="0" onclick="openGroupMember(${jsArg(m.strategy)})"
      onkeydown="if(event.target===event.currentTarget&&(event.key==='Enter'||event.key===' ')){event.preventDefault();openGroupMember(${jsArg(m.strategy)})}">
      <span class="h">${esc(m.label)}${m.state ? ` · <span class="dim">${esc(m.state)}</span>` : ""}</span>
      ${p.membersFull ? "" : `<span class="t dim">${esc(m.build)}</span>`}<span class="t net">${esc(p.membersFull ? m.full : m.unseen)}</span></div>`);
  const out = p.leftOut.map(x => `<div class="feed-row"><span class="h">${esc(x.label)}</span><span class="t dim">${esc(x.why)}</span></div>`);
  const curve = p.curve ? `<div class="sec"><h2>${esc(p.curve.title)}</h2>${eqPlot(p.curve.vals, p.curve.label, p.curve.total, p.curve.aria, p.curve.ends, p.curve.days, p.curve.notes, p.curve.build, p.curve.both)}</div>` : "";
  return `<button class="back" onclick="setView('today')">‹ Today</button>
    <div class="sd-top"><div><h1 class="sd-title">${esc(p.title)}</h1><div class="sp mono">${esc(p.lead)}</div></div></div>
    <div class="sd-state"><b>${esc(p.kind)}</b> · ${esc(p.kindNote)}</div>
    <div class="sd-note">${esc(p.note)}</div>
    ${actBtn("g:" + g.id)}
    ${p.empty ? `<div class="eq-empty">${esc(DeskLab.EMPTY_GROUP)}</div>` : ""}
    ${curve}
    <div class="figs labres-prop${p.figs.full ? "" : " grp-figs"}${three(p.figs)}" data-h="Combined, after costs">${two(p.figs)}</div>
    <div class="labres" data-for="${esc(g.id)}">
      <div class="sec"><h2>${esc(p.days.title)}</h2><div class="figs labres-unseen${p.figs.full ? " full" : ""}" data-h="${esc(p.days.title)}">${days}</div></div>
      <div class="sec"><h2>${esc(p.prop.title)}</h2><div class="figs labres-prop${three(p.prop)}" data-h="${esc(p.prop.title)}">${two(p.prop)}</div></div></div>
    ${members.length ? `<div class="sec"><h2>Strategies</h2><div class="agroup feed static">
      <div class="feed-row"><span class="h dim">Strategy</span>${p.membersFull ? `<span class="t dim">Full sample</span>` : `<span class="t dim">Build</span><span class="t dim">Unseen</span>`}</div>${members.join("")}</div></div>` : ""}
    ${out.length ? `<div class="sec"><h2>Left out of the sum</h2><div class="agroup feed static">${out.join("")}</div></div>` : ""}
    ${labSafe(() => cycleHtml(g), "")}
    ${labSafe(() => groupTodayHtml(g), "")}
    ${labSafe(() => deskChangesHtml("g:" + g.id), "")}
    <div class="sd-actions"><button class="btn btn-outline btn-sm" onclick="openGroupMgr()">Manage groups</button>
      <button class="btn btn-outline btn-sm" onclick="deleteGroup(${jsArg(g.id)})" title="The strategies stay on the Desk, in no group.">Delete group</button></div>`;
}
/* Account cycle (the owner, 2026-10-25): the group's strategies share ONE turn over the ticked accounts -- each trade goes to
   the next ticked account that is free, so two trades may be open at once but only on separate accounts; a trade opposite
   to one open on another of these accounts is skipped (no long on one while a short is on another); with a risk set,
   every order is sized to that many dollars at its own stop. Off by default. The engine keeps it (POST /api/groups).
   Each strategy must still be booked on the accounts (its own Accounts section): an account it is not booked on is
   not in its turn. */
function cycleMembers(g) {
  return (g.members || []).filter(m => ST.strategies[m] && ST.strategies[m].cfg.kind === "lab");
}
/* Risk, Most and the ticks save only on the card's one Save button, which reads old → new ("Save: Risk $1,000 → $1,500 ·
   +…026"). What is typed or ticked but not saved is kept here, per group, so a repaint never wipes it. */
let CYC_DRAFT = {};
const cycNum = (s) => Number(String(s).replace(/[$,\s]/g, ""));
// A member's dollars at risk in a cycle: its own amount (risk_by), else the cycle's (engine_groups.member_risk)
const cycRisk = (g, m) => Number(((g && g.risk_by) || {})[m]) || Number(g && g.risk_usd) || 0;   // "$1,500" -> 1500; the one parse for the body and the Save button
/* Three ways a group trades its accounts (owner, 2026-10-30); the hedge block covers its accounts in every one. */
const CYC_MODES = {cycle: "Take turns: one account a trade", share: "Every account takes every trade", split: "One strategy per account"};
const cycMode = (g) => (g && CYC_MODES[g.mode]) ? g.mode : "cycle";
const CYC_TITLES = {cycle: "Account cycle", share: "Every account, every trade", split: "One strategy per account"};
/* Split, as saved: one row per account of the group -- the strategy that trades it, its size, whether it is booked there. */
function splitRows(cyc, mem) {
  const by = Object.fromEntries(Object.entries(cyc.assign || {}).map(([m, a]) => [a, m]));
  const booked = (m, a) => ((ST.book || {})[m] || []).some(r => r.account === a);
  const rows = cyc.accounts.map(a => {
    const m = by[a], risk = m ? ((cyc.risk_by || {})[m] || cyc.risk_usd) : 0, acc = (ST.accounts || {})[a] || {}, p = acc.day_pnl;
    return `<div class="feed-row"><span class="h">${esc(acctShort(a))} <span class="dim">${esc(cycleEnvWord(a))}</span></span>
      <span class="t">${m ? `<b>${esc(stratLabel(m))}</b> · ${+risk > 0 ? "$" + (+risk).toLocaleString("en-US") + " a trade" : "its own size"}${booked(m, a) ? "" : ' · <span class="neg">not booked</span>'}`
        : '<span class="dim">no strategy</span>'}${p == null ? "" : ` <span class="mono ${p > 0 ? "pos" : p < 0 ? "neg" : ""}" title="Today, 18:00 to 16:00 ET">${DAY_PNL_WORDS(p)}</span>`}</span></div>`;
  }).join("");
  const none = cyc.members.filter(m => !(cyc.assign || {})[m]);
  return `<div class="agroup feed static">${rows}${none.length ? `<div class="feed-row"><span class="h neg">No account</span><span class="t">${esc(none.map(stratLabel).join(", "))}</span></div>` : ""}</div>`;
}
const cycUsd = (v) => Number.isFinite(v) ? "$" + v.toLocaleString("en-US") : "?";
const cycleEnvWord = (a) => !isDemoAcct(a) ? "LIVE" : ((((ST && ST.accounts) || {})[a] || {}).env === "paper" ? "PAPER" : "DEMO");
/* What a save would change, against what the desk has now (no cycle yet: the card's defaults, $1,000 and 17, no account).
   up: risk or Most goes up -- or risk goes to 0 ("each strategy's own size"), which may be bigger, so it counts as up. */
function cycleDiff(cyc, nw) {
  const old = cyc ? {risk: cyc.risk_usd, minis: cyc.max_minis, accounts: cyc.accounts || [], by: cyc.risk_by || {}, mode: cycMode(cyc), assign: cyc.assign || {}}
                  : {risk: 1000, minis: 17, accounts: [], by: {}, mode: "cycle", assign: {}};
  const mode = nw.mode || old.mode, assign = nw.assign || old.assign;     // no box sent: the desk's own stay
  const was = {risk_usd: old.risk, risk_by: old.by}, by = nw.risk_by || old.by;     // no boxes sent: the desk's own amounts stay
  // an account the Desk removed is not "gone" by a save: no tick can show it, and the save never sends it (cycleBody)
  const added = nw.accounts.filter(a => !old.accounts.includes(a)), gone = old.accounts.filter(a => a in ((ST && ST.accounts) || {}) && !nw.accounts.includes(a));
  const parts = [];
  if (nw.risk_usd !== old.risk) parts.push(`Risk ${cycUsd(old.risk)} → ${cycUsd(nw.risk_usd)}`);
  const own = [...new Set([...Object.keys(old.by), ...Object.keys(by)])].filter(m => (+old.by[m] || 0) !== (+by[m] || 0));
  for (const m of own) parts.push(`${stratLabel(m)} ${cycUsd(cycRisk(was, m))} → ${cycUsd(cycRisk(nw, m))}`);
  if (nw.max_minis !== old.minis) parts.push(`Most ${old.minis} → ${Number.isFinite(nw.max_minis) ? nw.max_minis : "?"}`);
  if (mode !== old.mode) parts.push(`${CYC_MODES[old.mode]} → ${CYC_MODES[mode]}`);
  const moved = [...new Set([...Object.keys(old.assign), ...Object.keys(assign)])].filter(m => (old.assign[m] || "") !== (assign[m] || ""));
  for (const m of moved) parts.push(`${stratLabel(m)} on ${old.assign[m] ? acctShort(old.assign[m]) : "no account"} → ${assign[m] ? acctShort(assign[m]) : "no account"}`);
  for (const a of added) parts.push("+" + acctShort(a));
  for (const a of gone) parts.push("−" + acctShort(a));
  const members = [...new Set([...((cyc && cyc.members) || []), ...(nw.members || []), ...Object.keys(by)])];
  const up = !(nw.risk_usd <= old.risk) || (old.risk > 0 && nw.risk_usd === 0) || !(nw.max_minis <= old.minis)
    || members.some(m => !(cycRisk(nw, m) <= cycRisk(was, m)) || (cycRisk(was, m) > 0 && cycRisk(nw, m) === 0))
    || (mode === "share" && old.mode !== "share") || moved.some(m => assign[m]);     // more accounts a trade, or a new account
  return {parts, up, liveIn: added.filter(isRealAcct)};
}
const cycByBody = (raw) => Object.fromEntries(Object.entries(raw || {}).filter(([, v]) => String(v).trim() !== "").map(([m, v]) => [m, cycNum(v)]));
const cycleDraftBody = (dr) => ({risk_usd: cycNum(dr.risk), risk_by: cycByBody(dr.by), max_minis: Math.round(cycNum(dr.minis)),
                                 ...(dr.mode ? {mode: dr.mode} : {}), ...(dr.assign ? {assign: dr.assign} : {}),
                                 accounts: dr.accounts.filter(a => a in ((ST && ST.accounts) || {}))});   // as cycleBody reads the ticks
function cycleSaveHtml(id, cyc, nw) {
  const d = nw ? cycleDiff(cyc, nw) : {parts: []};
  return d.parts.length ? `<div class="sd-actions"><button class="btn btn-default btn-sm" onclick="FREEZE=false;saveCycle(${jsArg(id)})">Save: ${esc(d.parts.join(" · "))}</button></div>` : "";
}
/* A keystroke or a tick: keep it as the draft and show (or hide) the Save button in place -- the inputs are never redrawn. */
function cycleEdit(id) {
  const root = document.querySelector("#viewStrat");
  if (!root) return;
  const raw = (sel) => { const el = root.querySelector(sel); return el ? String(el.value) : ""; };
  const b = cycleBody(id), cyc = ((ST && ST.groups) || {})[id] || null;
  const by = Object.fromEntries([...root.querySelectorAll(".cyc-risk-m")].map(el => [el.dataset.m, String(el.value)]));
  if (cycleDiff(cyc, b).parts.length) CYC_DRAFT[id] = {risk: raw(".cyc-risk"), minis: raw(".cyc-minis"), accounts: b.accounts, by,
                                                       ...(b.mode ? {mode: b.mode} : {}), ...(b.assign ? {assign: b.assign} : {})};
  else delete CYC_DRAFT[id];
  const slot = root.querySelector(".cyc-save");
  if (slot) slot.innerHTML = cycleSaveHtml(id, cyc, b);
}
function cycleHtml(g) {
  const cyc = ((ST && ST.groups) || {})[g.id] || null, mem = cycleMembers(g), dr = CYC_DRAFT[g.id] || null;
  if (!mem.length && !cyc) return `<div class="sec"><h2>Account cycle</h2><div class="mcap">Put this group's strategies in it first
    (Manage groups): then tick the accounts here and switch the cycle on.</div></div>`;
  const on = !!(cyc && cyc.on), chosen = new Set(dr ? dr.accounts : cyc ? cyc.accounts : []);
  const mode = (dr && dr.mode) || cycMode(cyc), assign = (dr && dr.assign) || (cyc && cyc.assign) || {};
  const turn = on ? labSafe(() => cycleLastTurn(g), "") : "";
  const tagCls = {LIVE: "tag-live", PAPER: "tag-paper", DEMO: "tag"};
  const boxes = Object.keys(ST.accounts || {}).map(a => `<label class="feed-row" style="cursor:pointer">
      <span class="h"><input type="checkbox" class="cyc-acct" data-acct="${esc(a)}" ${chosen.has(a) ? "checked" : ""}
        onchange="cycleEdit(${jsArg(g.id)})"> ${esc(acctShort(a))} <span class="${tagCls[cycleEnvWord(a)]}">${cycleEnvWord(a)}</span></span>
      ${(p => p == null ? "" : `<span class="mono ${p > 0 ? "pos" : p < 0 ? "neg" : ""}" style="margin-left:auto" title="Today, 18:00 to 16:00 ET">${DAY_PNL_WORDS(p)}</span>`)(ST.accounts[a].day_pnl)}</label>`).join("");
  const booked = (m, a) => ((ST.book || {})[m] || []).some(r => r.account === a);
  const missing = !cyc ? [] : cycMode(cyc) === "split"
    ? mem.map(m => (cyc.assign || {})[m] ? (booked(m, cyc.assign[m]) ? "" : `${stratLabel(m)} is not booked on ${acctShort(cyc.assign[m])}`)
                                         : `${stratLabel(m)} has no account: it never trades`).filter(Boolean)
    : cyc.accounts.map(a => [a, mem.filter(m => !booked(m, a)).length])
      .filter(x => x[1]).map(([a, n]) => `${acctShort(a)}: ${n} of ${mem.length} strategies not booked`);
  const pick = (m) => `<select class="cyc-assign" data-m="${esc(m)}" aria-label="${esc(stratLabel(m))} account" onfocus="FREEZE=true" onblur="FREEZE=false"
      onchange="cycleEdit(${jsArg(g.id)})"><option value="">no account</option>${[...chosen].map(a => `<option value="${esc(a)}"${assign[m] === a ? " selected" : ""}>${esc(acctShort(a))}</option>`).join("")}</select>`;
  const out = cyc ? cyc.members.filter(m => !mem.includes(m)) : [], add = cyc ? mem.filter(m => !cyc.members.includes(m)) : [];
  const num = (cls, v, ph, extra) => `<input class="${cls}"${extra || ""} type="text" inputmode="decimal" autocomplete="off" value="${esc(String(v))}"
      placeholder="${ph}" style="width:72px;max-width:100%;text-align:right" onfocus="FREEZE=true" onblur="FREEZE=false" oninput="cycleEdit(${jsArg(g.id)})">`;
  return `<div class="sec"><h2>${esc(CYC_TITLES[mode])}</h2>${cyc && cycMode(cyc) === "split" && on ? splitRows(cyc, mem) : ""}<div class="agroup feed static">
    <div class="feed-row"><span class="h">${esc(CYC_MODES[mode])}</span>
      <button class="switch" role="switch" aria-label="Account cycle" aria-checked="${on}"
        title="${on ? "ON — " + CYC_MODES[mode] : "OFF — each strategy trades its own booked accounts"}"
        onclick="toggleCycle(${jsArg(g.id)})"></button></div>
    ${on && cyc.next ? `<div class="feed-row"><span class="h">Next account: ${esc(acctShort(cyc.next))}</span></div>` : ""}
    ${turn ? `<div class="feed-row"><span class="h">${esc(turn)}</span></div>` : ""}
    <div class="feed-row"><span class="h">How it trades</span><span class="t"><select class="cyc-mode" aria-label="How the group trades its accounts"
      onfocus="FREEZE=true" onblur="FREEZE=false" onchange="FREEZE=false;cycleEdit(${jsArg(g.id)});render()">${Object.entries(CYC_MODES).map(([k, w]) =>
      `<option value="${k}"${k === mode ? " selected" : ""}>${esc(w)}</option>`).join("")}</select></span></div>
    <div class="feed-row"><span class="h">Risk per trade ($)</span><span class="t">${num("cyc-risk", dr ? dr.risk : cyc ? cyc.risk_usd : 1000, "1000")}</span></div>
    ${mem.map(m => `<div class="feed-row"><span class="h">&nbsp;&nbsp;${esc(stratLabel(m))} ($)</span><span class="t">${num("cyc-risk-m",
      dr && dr.by && m in dr.by ? dr.by[m] : ((cyc && cyc.risk_by) || {})[m] || "", "same", ` data-m="${esc(m)}" aria-label="${esc(stratLabel(m))} risk per trade"`)}${mode === "split" ? " " + pick(m) : ""}</span></div>`).join("")}
    <div class="feed-row"><span class="h">Most per trade (full contracts)</span><span class="t">${num("cyc-minis", dr ? dr.minis : cyc ? cyc.max_minis : 17, "17")}</span></div>
    ${boxes}</div>
    <div class="cyc-save">${dr ? cycleSaveHtml(g.id, cyc, cycleDraftBody(dr)) : ""}</div>
    <div class="mcap">${mode === "share" ? "Every trade goes to every ticked account the strategy is booked on."
      : mode === "split" ? "Each strategy trades only the account chosen beside it (it must be booked there)."
      : "One trade goes to one account, the next ticked one that is free."} A trade the opposite way to one open on
      another of these accounts is skipped. Risk 0 = each strategy's own size. A strategy's own amount (left empty: the same
      as the cycle's) sizes its trades instead.</div>
    ${cyc && cyc.outside && Object.keys(cyc.outside).length ? `<div class="mcap warn">${esc(Object.entries(cyc.outside).map(([m, as]) =>
      `${stratLabel(m)} is booked on ${as.map(acctShort).join(", ")}${cycMode(cyc) === "split" ? "" : " outside the cycle"}: it never trades there`).join(" · "))}.</div>` : ""}
    ${missing.length ? `<div class="mcap warn">${esc(missing.join(" · "))}.</div>
      ${on ? `<div class="sd-actions"><button class="btn btn-default btn-sm" onclick="bookCycle(${jsArg(g.id)})">${cycMode(cyc) === "split" ? "Book each strategy on its account" : "Book every strategy on these accounts"}</button></div>`
           : `<div class="mcap">Switch the cycle on first, then book its strategies here (booked with the cycle off, each strategy trades every account it is booked on).</div>`}` : ""}
    ${out.length || add.length ? `<div class="sd-actions"><button class="btn btn-outline btn-sm" onclick="syncCycle(${jsArg(g.id)})">Update the cycle to the group's strategies</button></div>` : ""}</div>`;
}
function cycleCopies(members) {     // the strategies that, out of the cycle, would send each trade to several accounts at once
  return members.filter(m => ((ST.book || {})[m] || []).length > 1 && !((((ST.strategies || {})[m]) || {}).rotation || {}).on);
}
function cycleLive(members) {        // ", 3 of them LIVE" for the accounts these strategies are booked on
  const live = new Set(members.flatMap(m => ((ST.book || {})[m] || []).map(r => r.account)).filter(isRealAcct)).size;
  return live ? `, ${live} of them LIVE` : "";
}
/* The cycle follows its Desk group: its strategies are the group's Lab strategies; a group deleted takes its cycle with it.
   A cycle left with no strategy goes off. */
async function syncCycle(id) {
  const cyc = ((ST && ST.groups) || {})[id];
  if (!cyc) return;
  const g = groupOf(id), members = g ? cycleMembers(g) : [];
  if (g && JSON.stringify(members) === JSON.stringify(cyc.members)) return;
  let r, err = null;
  try {
    r = g ? await post("/api/groups", {id, members, ...(members.length ? {} : {on: false})}) : await post("/api/groups/delete", {id});
  } catch (e) { err = e || new Error("no answer"); }
  refresh();
  const why = DEMO ? "" : answerWhy(r, err);
  if (why) toast(`Account cycle NOT updated — ${why}.`, 8000);
}
/* Book every strategy of an ON cycle on the cycle's accounts it is not booked on yet (size 1: the cycle sizes each order). Only
   while the cycle is on: booked with it off, each strategy would trade every account at once. */
async function bookCycle(id) {
  const cyc = ((ST && ST.groups) || {})[id];
  if (!cyc || !cyc.on) return;
  const split = cycMode(cyc) === "split", where = (m) => split ? ((cyc.assign || {})[m] ? [cyc.assign[m]] : []) : cyc.accounts;
  const todo = cyc.members.map(m => [m, where(m).filter(a => !((ST.book || {})[m] || []).some(r => r.account === a))]).filter(x => x[1].length);
  const n = todo.reduce((k, x) => k + x[1].length, 0), live = new Set(todo.flatMap(x => x[1]).filter(isRealAcct)).size;
  if (!n || !await confirmDlg(`Book ${n} account${n === 1 ? "" : "s"}?`, `${todo.length} strateg${todo.length === 1 ? "y" : "ies"} on the cycle's accounts` +
      `${live ? ` (${live} LIVE)` : ""}. ${{cycle: "Each trade still goes to ONE account, in turn", share: "Every trade goes to EVERY ticked account",
      split: "Each strategy trades only its own account"}[cycMode(cyc)]}, sized by the cycle.`, "Book", false)) return;
  const bad = [];
  for (const [m, add] of todo) {
    const rows = ((ST.book || {})[m] || []).concat(add.map(a => ({account: a, qty: 1})));     // a booked row keeps its settings
    let r = null;
    try { r = await post("/api/book", {strategy: m, assignments: rows}); } catch (_) { r = null; }
    if (!r || r.ok !== true) bad.push(`${stratLabel(m)}: ${labSafe(() => DeskLab.refusalText(r), "refused")}`);
  }
  refresh();
  if (!DEMO) toast(bad.length ? `Not all booked — ${bad.join(" · ")}` : "Every strategy is booked on the cycle's accounts.", bad.length ? 9000 : 4200);
}
function cycleBody(id) {
  const g = groupOf(id), root = document.querySelector("#viewStrat");
  const val = (sel, d) => { const el = root && root.querySelector(sel); return el ? cycNum(el.value) : d; };
  const byEls = [...(root ? root.querySelectorAll(".cyc-risk-m") : [])];   // one per Lab strategy of the card; none: risk_by not sent
  const modeEl = root && root.querySelector(".cyc-mode"), asEls = [...(root ? root.querySelectorAll(".cyc-assign") : [])];
  const accounts = [...(root ? root.querySelectorAll(".cyc-acct") : [])].filter(b => b.checked).map(b => b.dataset.acct);
  return {id, name: g ? g.name : id, members: g ? cycleMembers(g) : [], accounts,
          risk_usd: val(".cyc-risk", 0), max_minis: Math.round(val(".cyc-minis", 17)),
          ...(byEls.length ? {risk_by: cycByBody(Object.fromEntries(byEls.map(el => [el.dataset.m, el.value])))} : {}),
          ...(modeEl ? {mode: modeEl.value} : {}),
          // an account unticked takes its strategy with it (the server refuses an account outside the group)
          ...(asEls.length ? {assign: Object.fromEntries(asEls.filter(el => accounts.includes(el.value)).map(el => [el.dataset.m, el.value]))} : {})};
}
/* The card's Save (no `extra`) asks first ONLY while the cycle is ON on a LIVE account and the change sizes up (risk or Most
   goes up) or ticks a LIVE account in. Lowering, unticking and every demo/paper-only cycle save at once. The switch
   (setCycle, with `extra`) keeps its own questions and never saves a draft. */
async function saveCycle(id, extra) {
  const body = {...cycleBody(id), ...(extra || {})};
  const cyc = ((ST && ST.groups) || {})[id] || null;
  if (!extra && cyc && cyc.on) {
    const d = cycleDiff(cyc, body), live = body.accounts.filter(isRealAcct), where = machineWords();
    if (live.length && (d.up || d.liveIn.length) && !await confirmDlg("Change the LIVE account cycle?",
        `${d.parts.join(" · ")}.${d.liveIn.length ? ` LIVE account${d.liveIn.length === 1 ? "" : "s"} ticked in: ${d.liveIn.map(acctShort).join(", ")}.` : ""}` +
        ` The cycle is ON across ${live.length} LIVE account${live.length === 1 ? "" : "s"}${where ? " " + where : ""}: the next trade uses this.`,
        "Save", false)) { refresh(); return false; }
  }
  let r, err = null;
  try { r = await post("/api/groups", body); } catch (e) { err = e || new Error("no answer"); }
  const why = DEMO ? null : answerWhy(r, err);
  if (why === "" && !(extra && "accounts" in extra)) delete CYC_DRAFT[id];   // saved: the card shows the desk's values again
  refresh();
  if (DEMO) return false;
  if (why) toast(`Account cycle NOT changed — ${why}.`, 8000);
  return !why;
}
const toggleCycle = (id) => setCycle(id, !(((ST && ST.groups) || {})[id] || {}).on);
async function setCycle(id, on) {
  if (switchBounced("cycle:" + id)) return;
  /* A draft (typed or ticked, not saved) never rides on the switch: ON waits for Save; OFF sends the desk's own values and
     the draft stays for its Save button. */
  const cyc = ((ST && ST.groups) || {})[id] || null, dr = CYC_DRAFT[id];
  // A draft = what the card's Save button shows (cycleHtml), so ON never points at a Save that is not there. OFF sends the
  // desk's own values as the page ticks them: never an account the Desk removed (the server refuses one).
  const saved = cyc && dr && cycleDiff(cyc, cycleDraftBody(dr)).parts.length ? {accounts: Object.keys(ST.accounts || {}).filter(a => (cyc.accounts || []).includes(a)),
                                                                                 risk_usd: cyc.risk_usd, max_minis: cyc.max_minis, ...(cyc.risk_by ? {risk_by: cyc.risk_by} : {}),
                                                                                 ...(cyc.mode ? {mode: cyc.mode, assign: cyc.assign || {}} : {})} : null;
  if (saved && on) { toast("Save or undo your changes first, then switch the cycle on.", 6000); refresh(); return; }
  const b = {...cycleBody(id), ...saved};
  const copies = on ? [] : cycleCopies(b.members);
  if (copies.length && !await confirmDlg(`Stop the account cycle?`,
      `${copies.length} strateg${copies.length === 1 ? "y" : "ies"} then send each trade to EVERY account booked${cycleLive(copies)}.`, "Stop the cycle", true)) { refresh(); return; }
  if (on) {
    const live = b.accounts.filter(isRealAcct).length;
    const how = {cycle: "take turns across", share: "trade every one of", split: "each trade their own one of"}[b.mode || cycMode(cyc)];
    if (!await confirmDlg(`Start the account cycle?`, `${b.members.length} strateg${b.members.length === 1 ? "y" : "ies"} ${how} ${b.accounts.length} account${b.accounts.length === 1 ? "" : "s"}${live ? ` (${live} LIVE)` : ""}` +
        (b.members.some(m => cycRisk(b, m) > 0) ? `, each trade sized to ${b.members.map(m => `${stratLabel(m)} ${cycRisk(b, m) > 0 ? cycUsd(cycRisk(b, m)) : "its own size"}`).join(", ")} at risk, at most ${b.max_minis} full contracts.` : ", each at its own size."), "Start", false)) { refresh(); return; }
  }
  if (await saveCycle(id, {...saved, on})) toast(on ? `Account cycle ON: ${CYC_MODES[b.mode || cycMode(cyc)].toLowerCase()}.` : "Account cycle OFF.");
}
async function deleteGroup(id) {
  const g = groupOf(id);
  if (!g) return;
  const on = !!(((ST && ST.groups) || {})[id] || {}).on && cycleCopies(cycleMembers(g)).length > 0;
  if (!await confirmDlg(`Delete ${g.name}?`, on ? `Its account cycle stops too: ${cycleCopies(cycleMembers(g)).length} of its strategies then send each trade to EVERY account booked${cycleLive(cycleCopies(cycleMembers(g)))}. Its strategies stay on the Desk, in no group.`
                                             : "Its strategies stay on the Desk and go back under Strategies. Nothing is switched off.", "Delete", on)) return;
  if (await groupPost("delete", {id})) toast(`${g.name} is deleted. Its strategies are in no group.`);     // its cycle went first, server side
}

const hmin = (t) => { const m = /^(\d{1,2}):(\d\d)/.exec(String(t || "")); return m ? +m[1] * 60 + +m[2] : null; };
const etMin = (iso) => { const m = /T(\d\d):(\d\d)/.exec(String(iso || "")); return m ? +m[1] * 60 + +m[2] : null; };
const OPEN_MIN = 570;                                    // 09:30 ET, the cash open
const lenTxt = (m) => m >= 60 ? `${Math.floor(m / 60)} h${m % 60 ? " " + (m % 60) + " min" : ""}` : `${m} min`;
const usdS = (v) => v == null ? "—" : (v < 0 ? "−$" : v > 0 ? "+$" : "$") + fmt(Math.abs(v), 0);
const plural = (n, a, b) => `${n} ${n === 1 ? a : b}`;
/* The journal as the Today page and the sidebar read it: the Lab's named bookkeeping lines (DeskLab.HIDDEN_EVENTS: lab_event, lab_event_done, lab_added)
   are left out, so they never become the "Last event" time. Every other line is returned as it is. (The Activity list filters the same way.) */
/* A time of day as the app shows it: "HH:MM" or "HH:MM:SS" in, the owner's clock format out (hbclock.js; unchanged without it). */
const hbClock = (hms) => typeof HBClock !== "undefined" ? HBClock.text(hms) : hms;
const journalNews = (j) => journalShown(j).filter(r => !routineRow(r));      // "Last event": never a routine reconnect
const journalShown = (j) => (Array.isArray(j) ? j : []).filter(r => !(r && typeof r.event === "string" && r.event.indexOf("lab_") === 0 && typeof DeskLab !== "undefined" && DeskLab.hiddenEvent(r.event)));
const specOf = (c, name) => c.kind === "lab" ? labSafe(() => DeskLab.deskSpec(c, labRowOf(ST.strategies[name])), String(c.symbol || ""))
  : c.kind === "bars"
  ? `${c.symbol} · ${c.bar_minutes}m bars · ${c.rule}`
  : `${c.symbol} · ±${c.offset_pts} off · SL ${c.sl_pts} / TP ${c.tp_pts}`;

function todayPnl(s) {
  const d = String((ST && ST.et_now) || "").slice(0, 10);
  const rows = (s.accounts || []).filter(r => r && r.date === d && r.pnl != null);
  return rows.length ? rows.reduce((a, r) => a + r.pnl, 0) : null;
}
function stratState(name, s) {
  const c = s.cfg, st = s.day_status;
  if (c.kind === "lab") return labSafe(() => DeskLab.deskState(s, (ST.book && ST.book[name]) || []), "Check it");     // a promoted Lab strategy: the Desk's own words (lab.state / lab.why)
  if (!c.enabled) return "Off";
  if (st === "live") return "In position";
  if (st === "placed" || st === "placing") return "Orders working";
  if (st === "error") return "Needs a look";
  if (st === "done") return "Done today";
  const t = ST.timer && ST.timer.strategies && ST.timer.strategies[name];
  if (t && t.stage === "missed") return "Missed today";
  const now = etMin(ST.et_now), flat = hmin(c.flat_et) ?? 955;
  if (now != null && now >= flat) return "Idle";
  return now != null && now < OPEN_MIN ? "Ready" : "Watching";
}
const stratDotCls = (s, state, book) => s.cfg.kind === "lab" ? labSafe(() => DeskLab.deskDot(s, book), "warn")
  : !s.cfg.enabled ? "off" : s.cfg.shadow ? "shadow"
  : /Needs|Missed/.test(state) ? "warn" : (state === "In position" || state === "Orders working") ? "live" : "";

/* The day so far in money, LIVE apart from the rest: the sums of each account's closed P&L today (day.closed_net, which
   /api/status already sends). Closed trades only -- an open position's P&L is not in it, so it says so. The Mac's line
   names the machine (its accounts are not the server's). "" when no account says. */
function dayMoney() {
  const sums = {live: null, other: null}, kinds = new Set();
  for (const [id, a] of Object.entries((ST && ST.accounts) || {})) {
    const v = Number(a && a.day && a.day.closed_net);
    if (!a || !a.day || !Number.isFinite(v)) continue;
    const k = isDemoAcct(id) ? "other" : "live";
    sums[k] = (sums[k] || 0) + v;
    if (k === "other") kinds.add(a.env === "paper" ? "paper" : "demo");
  }
  const other = kinds.size === 2 ? "Demo + paper" : kinds.has("paper") ? "Paper" : "Demo";
  const parts = [sums.live != null ? `Live ${usdS(sums.live)}` : "", sums.other != null ? `${other} ${usdS(sums.other)}` : ""].filter(Boolean);
  if (!parts.length) return "";
  return `${deskMachine() === "mac" ? "This Mac: " : ""}${parts.join(" · ")} so far (strategies' closed trades).`;
}
/* the one sentence of the day -- two tones: what happens next, then what is armed */
function dayHeadline(names) {
  const strategies = Object.values(ST.strategies || {});
  // a Lab strategy with no account booked only runs in shadow: it is not "armed", and its times are never the day's
  const live = Object.entries(ST.strategies || {}).filter(([n, v]) => v.cfg.enabled && !v.cfg.shadow &&
    !(v.cfg.kind === "lab" && !((ST.book && ST.book[n]) || []).length)).map(([, v]) => v);
  const nonLab = strategies.filter(v => v.cfg.kind !== "lab");
  const n = live.length, now = etMin(ST.et_now);
  const dow = new Date(String(ST.et_now).slice(0, 10) + "T12:00:00Z").getUTCDay();
  const stale = DESK_STALE ? " Last known state." : "";
  if (!ST.armed) return ["Disarmed.", "Signals are journaled only. Nothing is sent to a broker." + stale];
  const onTxt = "Desk armed · " + plural(n, "strategy", "strategies") + " on." + stale;      // the desk is armed; strategies are on or off
  // Sunday from 18:00 ET the futures trade again: the Desk's day is the 9:30 session, so say when that is, not "closed"
  if (dow === 0 && now != null && now >= 18 * 60) return ["Futures are open. The Desk's day starts Monday at 9:30.", onTxt];
  if (dow === 0 || dow === 6) return ["Markets are closed.", onTxt];
  const flat = live.some(v => v.cfg.kind === "lab")      // a booked Lab strategy armed: the day ends at the latest armed flat time
    ? Math.max(...live.map(v => hmin(v.cfg.flat_et) ?? 955))
    : hmin((live[0] || nonLab[0] || strategies[0] || {cfg: {}}).cfg.flat_et) ?? 955;
  if (now == null) return ["Armed.", onTxt];
  if (now < OPEN_MIN) return [`Opens in ${lenTxt(OPEN_MIN - now)}.`, onTxt];
  if (now < flat) {
    const inPos = live.filter(v => v.day_status === "live").length;
    const working = live.filter(v => v.day_status === "placed" || v.day_status === "placing").length;
    const done = live.filter(v => v.day_status === "done").length;
    const l1 = inPos ? `${plural(inPos, "strategy", "strategies")} in a position.` : working ? "Orders are working." : "In session.";
    const money = dayMoney();
    return [l1, `${n} on · ${done} done today.` + (money ? " " + money : "") + stale];
  }
  const rows = strategies.map(todayPnl).filter(p => p != null);
  const tot = rows.reduce((a, p) => a + p, 0);
  return ["Session closed.", (rows.length ? `Today ${usdS(tot)}.` : "No trades today.") + stale];
}

/* The day bar's axis, in minutes ET: from the earliest window start to the latest window end (whole hours), with the
   9:30 open and the flat mark always on it; 9:00-16:00 when no window reads. A built-in's window is its fire time
   (9:30 when unsaid) to its flat time; a booked Lab strategy's is its record's session_window (an evening-before one,
   "-20:00", is left out: the bar is one day). */
function dayAxis(own, labs, flat) {
  const ws = own.map(v => [hmin(v.cfg.fire_et) ?? OPEN_MIN, hmin(v.cfg.flat_et) ?? 955]);
  for (const v of labs) {
    const w = labSafe(() => (labRowOf(v) || {}).session_window, null);
    if (Array.isArray(w) && w.length === 2 && !String(w[0]).startsWith("-")) ws.push([hmin(w[0]), hmin(w[1])]);
  }
  const ok = ws.filter(([a, b]) => a != null && b != null && b > a);
  if (!ok.length) return [540, 960];
  const lo = Math.floor(Math.min(OPEN_MIN, flat, ...ok.map(w => w[0])) / 60) * 60;
  const hi = Math.ceil(Math.max(OPEN_MIN, flat, ...ok.map(w => w[1])) / 60) * 60;
  return [lo, Math.max(hi, lo + 60)];
}
function dayTimeline(names) {
  const vis = new Set(names || Object.keys(ST.strategies || {}));      // only the strategies the page shows (an archived straddle is not)
  const strategies = Object.entries(ST.strategies || {}).filter(([n]) => vis.has(n)).map(([, v]) => v);
  const own = strategies.filter(v => v.cfg.kind !== "lab");      // a Lab strategy sets its own times: never the day bar's
  // when no Desk strategy is armed, a Lab strategy WITH an account booked is the bar's (its Flat mark only: it has no cancel time of its own)
  const armedOwn = own.find(v => v.cfg.enabled && !v.cfg.shadow);
  const labsOn = Object.entries(ST.strategies || {}).filter(([n, v]) => v.cfg.kind === "lab" && v.cfg.enabled && !v.cfg.shadow && ((ST.book && ST.book[n]) || []).length);
  const later = (a, b) => ((hmin(b.cfg.flat_et) ?? 955) > (hmin(a.cfg.flat_et) ?? 955) ? b : a);
  const labRef = armedOwn || !labsOn.length ? null : labsOn.map(([, v]) => v).reduce(later);
  const ref = (armedOwn || labRef || own[0] || strategies.find(v => v.cfg.enabled && !v.cfg.shadow) || strategies[0] || {cfg: {}}).cfg;
  // a booked Lab strategy armed: the bar's Flat mark is the latest armed flat time (with none, the reference's, as always)
  const flatEt = labsOn.length ? [armedOwn, ...own.filter(v => v.cfg.enabled && !v.cfg.shadow), ...labsOn.map(([, v]) => v)].filter(Boolean).reduce(later).cfg.flat_et : ref.flat_et;
  const cancel = hmin(ref.cancel_et) ?? 775, flat = hmin(flatEt) ?? 955;
  const [lo, hi] = dayAxis(own, labsOn.map(([, v]) => v), flat);
  const pct = (m) => Math.max(0, Math.min(100, (m - lo) / (hi - lo) * 100));
  const noCancel = !!labRef || !own.length;      // a Lab strategy has no cancel time of its own: only a built-in straddle draws one
  const oneMark = !noCancel && cancel === flat;      // the cancel and the flat time are one moment: one label, one tick
  const now = etMin(ST.et_now) ?? lo;
  const date = new Date(String(ST.et_now).slice(0, 10) + "T12:00:00Z")
    .toLocaleDateString("en-US", {weekday: "long", month: "long", day: "numeric", timeZone: "UTC"});
  const lab = (m, t, cls) => `<span class="${cls}" style="left:${pct(m).toFixed(2)}%">${esc(t)}</span>`;
  return `<div class="tl-head"><span><b>Today</b>${esc(date)}</span><span class="mono">${esc(hbClock(String(ST.et_now).slice(11, 16)))} ET</span></div>
    <div class="tl" role="img" aria-label="The trading day: open at 9:30, ${noCancel ? "" : `unfilled entries cancelled at ${esc(ref.cancel_et || "12:55")}, `}flat at ${esc(flatEt || "15:55")}">
      <div class="tl-track"><i class="tl-done" style="width:${pct(now).toFixed(2)}%"></i>${noCancel || oneMark ? "" : `<i class="tl-tick" style="left:${pct(cancel).toFixed(2)}%"></i>`}<i class="tl-tick" style="left:${pct(flat).toFixed(2)}%"></i><i class="tl-open" style="left:${pct(OPEN_MIN).toFixed(2)}%"></i><i class="tl-now" style="left:${pct(now).toFixed(2)}%"></i></div>
      <div class="tl-labels">${lab(OPEN_MIN, hbClock("9:30") + " Open", "tl-t strong at-start")}${noCancel || oneMark ? "" : lab(cancel, hbClock(ref.cancel_et || "12:55") + " Cancel unfilled", "tl-t")}${lab(flat, hbClock(flatEt || "15:55") + (oneMark ? " Cancel unfilled, flat" : " Flat"), "tl-t at-end")}</div>
    </div>`;
}

/* Today's journal for a few strategies (or a group), read from GET /api/journal at most once a minute -- not the /api/status
   tail, 60 lines for the whole desk, which would miss most of them. One slot a page part; a new query starts its slot afresh.
   Never in the demo or while the page is hidden. null until the first answer (the pieces that need it are then left out). */
const JREAD = {};
function journalToday(slot, q) {
  let c = JREAD[slot];
  if (!c || c.q !== q) c = JREAD[slot] = {q, at: 0, rows: null};
  // one read a minute, timed from its start; a read that hangs is cut off at 30 s, so it never holds a connection to the desk
  if (!DEMO && !document.hidden && Date.now() - c.at >= 60000) {
    const at = c.at = Date.now();
    fetch(q, {signal: AbortSignal.timeout(30000)}).then(r => r.ok ? r.json() : null).then(j => { if (j && JREAD[slot] === c && c.at === at) c.rows = Array.isArray(j.events) ? j.events : []; })
      .catch(() => {});
  }
  return c.rows;
}
const SIGNAL_EVENTS = new Set(["placed", "levels_placed", "dry_run", "shadow_signal", "signal_refused", "alert_refused", "lab_round", "lab_refused"]);
const jHm = (r) => hbClock(String((r && r.et) || "").slice(11, 16));
/* A strategy's last signal today ("10:41"), from the newest signal line that names it; "" when none is known. */
function lastSignal(name, rows) {
  const r = (rows || []).find(x => x && x.strategy === name && SIGNAL_EVENTS.has(x.event) && x.et);
  return r ? jHm(r) : "";
}
const todaySignals = () => journalToday("today", "/api/journal?" + new URLSearchParams({strategy: Object.keys((ST && ST.strategies) || {}).sort().join(","), limit: "2000"}));
/* A strategy's open trades now, from its own day rows (a Lab strategy: its rounds): [{side: "Long" | "Short", qty, account}]. */
function stratOpen(s) {
  const rows = s && s.cfg && s.cfg.kind === "lab" && s.lab && Array.isArray(s.lab.rounds) ? s.lab.rounds : (s && s.accounts) || [];
  return rows.filter(r => r && r.status === "live" && (r.side || r.entry_side)).map(r => ({
    side: /^(buy|long)/i.test(r.side || r.entry_side) ? "Long" : "Short", account: r.account,
    qty: Number(r.entry_qty) > 0 ? Number(r.entry_qty) - (Number(r.exit_qty) || 0) : Number(r.qty)})).filter(p => p.qty > 0);
}
function openText(s) {      // "Long 2" (both sides: "Long 1 · Short 1"); "" when flat
  const by = {};
  for (const p of stratOpen(s)) by[p.side] = (by[p.side] || 0) + p.qty;
  return ["Long", "Short"].filter(k => by[k]).map(k => `${k} ${by[k]}`).join(" · ");
}
/* LIVE when any booked account is live, PAPER when all are paper, else DEMO; nothing with no account. */
function bookEnvTag(name) {
  const accts = ((ST && ST.book && ST.book[name]) || []).map(r => r && r.account).filter(Boolean);
  if (!accts.length) return "";
  const w = accts.some(a => cycleEnvWord(a) === "LIVE") ? "LIVE" : accts.every(a => cycleEnvWord(a) === "PAPER") ? "PAPER" : "DEMO";
  const [cls, t] = {LIVE: ["tag-live", "Its orders go to a LIVE account: real money"], PAPER: ["tag-paper", "Paper accounts only: no money"],
                    DEMO: ["tag", "Demo accounts only: no money"]}[w];
  return `<span class="${cls}" title="${t}">${w}</span>`;
}
/* A group's page, live (WP1.19): today's lines of the group and its strategies (the Activity page's group read), each member
   on the Desk with its state, last signal, position and today, the group's P&L today, and the cycle's last turn. Anything
   with no data is left out, never shown as a guess. */
const groupJournal = (g) => journalToday("group", "/api/journal?" + new URLSearchParams({group: g.id, strategy: (g.members || []).join(","), limit: "2000"}));
function groupTodayHtml(g) {
  const live = (g.members || []).filter(m => ST.strategies && ST.strategies[m]);
  if (!live.length) return "";
  const rows = labSafe(() => groupJournal(g), null);
  const pnls = live.map(m => todayPnl(ST.strategies[m])).filter(p => p != null);
  const tot = pnls.length ? pnls.reduce((a, p) => a + p, 0) : null;
  const line = (m) => {
    const s = ST.strategies[m], p = todayPnl(s), sig = lastSignal(m, rows);
    const pos = stratOpen(s).map(x => `${x.side} ${x.qty} on ${acctShort(x.account)}`).join(", ");
    const bits = [sig ? "Last signal " + sig : "", pos].filter(Boolean).join(" · ");
    return `<div class="feed-row" role="button" tabindex="0" onclick="openGroupMember(${jsArg(m)})"
      onkeydown="if(event.target===event.currentTarget&&(event.key==='Enter'||event.key===' ')){event.preventDefault();openGroupMember(${jsArg(m)})}">
      <span class="h">${esc(stratLabel(m))} · <span class="dim">${esc(stratState(m, s))}</span></span>
      <span class="t dim">${esc(bits)}</span><span class="t net${p < 0 ? " neg" : p > 0 ? " pos" : ""}">${p == null ? "" : esc(usdS(p))}</span></div>`;
  };
  return `<div class="sec"><h2>Today</h2>${tot == null ? "" : `<div class="sd-state">The group today: <b>${esc(usdS(tot))}</b></div>`}
    <div class="agroup feed static">${live.map(line).join("")}</div></div>`;
}
/* The cycle's last turn today: the newest trade one of its strategies opened on one of its accounts, or the newest turn it
   skipped. "" until the journal answers, or with no turn today. */
function cycleLastTurn(g) {
  const cyc = ((ST && ST.groups) || {})[g.id], rows = groupJournal(g);
  if (!cyc || !rows) return "";
  const r = rows.find(x => x && x.et && ((x.event === "lab_round" && (cyc.members || []).includes(x.strategy) && (cyc.accounts || []).includes(x.account))
    || ((x.event === "group_skipped" || x.event === "group_hedge_skipped") && x.group === g.id)));
  if (!r) return "";
  const t = `Last turn ${jHm(r)}: ${stratLabel(r.strategy)}`;
  return r.event === "lab_round" ? `${t} on ${acctShort(r.account)}`
    : `${t} was skipped. ${r.event === "group_hedge_skipped" ? "It was the opposite way to a trade open on another of these accounts." : String(r.reason || "")}`.trim();
}
function todayRow(name, s) {
  const c = s.cfg, state = stratState(name, s), p = todayPnl(s);
  const sig = labSafe(() => lastSignal(name, todaySignals()), "");
  const extra = [openText(s), sig ? "Last signal " + sig : ""].filter(Boolean);      // the position and the last signal: each only when known
  const sh = c.kind === "lab" ? labSafe(() => labShadowNet(name, s), null) : null;      // a Lab strategy with no account: what the day would have made
  const sw = `<button class="switch" role="switch" aria-label="${esc(stratLabel(name))} on or off" aria-checked="${c.enabled}"
    title="${c.kind === "lab" ? esc(labSafe(() => DeskLab.deskSwitchTitle(s, (ST.book && ST.book[name]) || []), "")) : c.enabled ? "ON — this strategy runs and executes" : "OFF — ignores all signals"}"
    onclick="event.stopPropagation();toggleStrat('${name}', ${!c.enabled})"></button>`;
  const go = `setView('strat','${name}')`;
  return `<div class="srow" role="button" tabindex="0" onclick="${go}"
      onkeydown="if(event.target===event.currentTarget&&(event.key==='Enter'||event.key===' ')){event.preventDefault();${go}}">
    <div><div class="n">${esc(stratLabel(name))}${c.shadow ? '<span class="tag" title="Signals are journaled only — nothing is placed, even when armed">Shadow</span>' : (c.kind === "lab" ? labSafe(() => labShadowTag(name, s), "") : "") + labSafe(() => bookEnvTag(name), "")}</div>
      <div class="sp mono">${esc([specOf(c, name), ...extra].join(" · "))}</div></div>
    <div class="rs">${esc(state)}</div>
    <div class="rp mono${sh ? " dim" : p < 0 ? " neg" : p > 0 ? " pos" : ""}"${sh ? ` title="${esc(sh.title)}"` : ""}>${usdS(sh ? sh.net : p)}</div>${sw}</div>`;
}

let ISSUE_LVL = "warn";      // the sidebar's Activity row reads it
/* One line under Readiness: how many accounts are connected. The things that need a look are the bulb's and the Readiness
   row's (openChecks); the last event is the sidebar's Activity row -- neither is repeated here. */
function todayFoot() {
  const accts = Object.values(ST.accounts || {}), up = accts.filter(a => a.connected).length;
  return `<button class="foot-b" onclick="openAccts()">${up} of ${accts.length} accounts connected <u>›</u></button>`;
}

