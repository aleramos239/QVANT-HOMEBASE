/* ---- account row (rendered inside strategy cards) ---- */
const DAY_PNL_WORDS = (v) => v == null ? "—" : (v > 0 ? "+" : "") + usd(v);   // an account's day, signed
/* "in a trade 1 · 2 working": the broker's count of open positions and of resting orders; "" when neither. */
function tradeWords(a) {
  const n = Array.isArray(a && a.open_positions) ? a.open_positions.length : 0, w = Number(a && a.working_orders) || 0;
  return [n ? "in a trade " + n : "", w ? w + " working" : ""].filter(Boolean).join(" · ");
}
const DEMO_TAG = '<span class="tag" title="A demo account — the broker\'s practice money">DEMO</span>';
function acctRow(id, extra) {
  const a = (ST.accounts || {})[id] || {label: id};   // LIVE unless demo or paper, as isDemoAcct (an unknown env is LIVE)
  const pnl = a.day_pnl;          // today: the balance now minus the balance at the 18:00 ET open (broker figures are lifetime or on their own clock)
  const err = (!a.connected && a.error)
    ? `<span class="kvi neg" style="font-size:11px;text-align:left;min-width:0">${esc(String(a.error).slice(0, 46))}…</span>` : "";
  return `<div class="acct">
    <span class="dot ${a.connected ? "on" : "off"}" data-ro="dot"></span>
    <span class="nm">${esc(a.label)}</span>
    ${a.env !== "demo" && a.env !== "paper" ? '<span class="tag-live" title="A live account — real money">LIVE</span>' : ""}
    ${a.env === "paper" ? '<span class="tag-paper" title="A paper account — simulated fills on the live prints, no money">PAPER</span>' : ""}
    ${a.env === "demo" ? DEMO_TAG : ""}
    ${extra.qty ? (extra.strategy && !extra.locked
      ? `<span class="strats qty-edit" title="Click to change size"
           onclick="editQty(event,'${extra.strategy}',${jsArg(id)},${extra.qty})">×${extra.qty}</span>`
      : `<span class="strats">×${extra.qty}</span>`) : ""}
    ${err}<span class="spacer"></span>
    <span class="kvi" data-ro="bal">${usd(a.balance)}</span>
    <span class="kvi ${pnl > 0 ? "pos" : pnl < 0 ? "neg" : ""}" data-ro="pnl" title="Today, 18:00 to 16:00 ET: balance now minus balance at 18:00">${DAY_PNL_WORDS(pnl)}</span>
    <button class="btn btn-outline btn-sm" onclick="openCal(${jsArg(a.account || a.label)})">Calendar</button>
    ${extra.strategy ? `<button class="x"${extra.locked ? " disabled" : ""} style="border:none;background:none;color:var(--muted-foreground);cursor:pointer;font-size:14px"
      ${extra.locked ? "" : `onclick="removeAsg('${extra.strategy}',${jsArg(id)})" `}title="Unassign">&times;</button>` : ""}
  </div>`;
}

/* ---- the book (assignments) ---- */
async function setBook(strategy, assignments) {
  const lab = ((ST.strategies || {})[strategy] || {cfg: {}}).cfg.kind === "lab", before = lab ? ((ST.book && ST.book[strategy]) || []) : [];
  const r = await post("/api/book", {strategy, assignments});
  if (lab) {      // a promoted Lab strategy: the Desk's own sentence, no prefix; an account added mid-session starts once it has no open trade
    if (!r.ok) toast(unbookRefusal(strategy, before, assignments, r) || DeskLab.refusalText(r), 8000);
    else if (DeskLab.bookedNext(ST.strategies[strategy], before, assignments)) toast(DeskLab.BOOKED_NEXT, 5000);
    else if (DeskLab.bookedJoins(ST.strategies[strategy], before, assignments)) toast(DeskLab.BOOKED_JOINS, 5000);
    refresh();
    return;
  }
  if (!r.ok) toast("Book update failed — " + (r.detail || "unknown"), 5000);
  refresh();
}
/* Take turns (account rotation, the owner 2026-10-19): each trade goes to ONE booked account, the next in the list that
   can take it. Off (the default) = every booked account takes every trade. Shown once two accounts are booked, or while on.
   Turning it OFF with a live account booked asks first: the next trade then goes to every account. */
function rotationHtml(name) {
  const rot = (((ST.strategies || {})[name]) || {}).rotation || {}, n = ((ST.book && ST.book[name]) || []).length;
  const cyc = Object.values((ST && ST.groups) || {}).find(g => g.on && (g.members || []).includes(name)) || null;
  if (n < 2 && !rot.on && !cyc) return "";
  return `<div class="agroup feed static"><div class="feed-row"><span class="h">Take turns: one account a trade</span>
    <button class="switch" role="switch" aria-label="Take turns" aria-checked="${!!rot.on}"
      title="${rot.on ? "ON — each trade goes to the next account in the list" : "OFF — every trade goes to every account"}"
      onclick="setRotation(${jsArg(name)}, ${!rot.on})"></button></div>
    ${cyc ? `<div class="feed-row"><span class="h">In the ${esc(cyc.name)} account cycle: it picks the account (next: ${esc(acctShort(cyc.next || ""))})</span></div>`
          : rot.on && rot.next ? `<div class="feed-row"><span class="h">Next account: ${esc(acctShort(rot.next))}</span></div>` : ""}</div>`;
}
async function setRotation(name, on) {
  if (switchBounced("rotation:" + name)) return;
  const book = (ST.book && ST.book[name]) || [], N = stratLabel(name);
  if (!on && book.length > 1 && book.some(a => isRealAcct(a.account)) && !await confirmDlg(
      `Stop taking turns on ${N}?`, `Its next trade goes to all ${book.length} booked accounts, LIVE ones included.`,
      "Stop taking turns", false)) { refresh(); return; }
  let r, err = null;
  try { r = await post("/api/rotation", {strategy: name, on}); } catch (e) { err = e || new Error("no answer"); }
  refresh();
  if (DEMO) return;
  const why = answerWhy(r, err);
  if (why) toast(`${N}: take turns NOT changed — ${why}.`, 8000);
  else toast(on ? `${N} takes turns: one account a trade.` : `${N}: every account takes every trade.`);
}
/* Unbooking one account of a Lab strategy that is in a trade there: the Desk refuses ("Flatten it first."); say which account
   and what it holds, in words. null: not that refusal. */
function unbookRefusal(strategy, before, after, r) {
  const gone = before.filter(a => !after.some(b => b.account === a.account));
  if (gone.length !== 1 || !r || r.detail !== "Flatten it first.") return null;
  const s = (ST.strategies || {})[strategy] || {}, id = gone[0].account;
  const trade = ((s.lab && s.lab.rounds) || []).find(x => x && x.account === id && ["placing", "placed", "live"].includes(x.status));
  const holds = trade && trade.qty ? `holds ${trade.qty} ${(s.cfg && s.cfg.symbol) || ""}`.trim() : "is in a trade";
  return `${acctShort(id)} ${holds} for ${stratLabel(strategy)}: flatten it or wait for the exit first. It stays booked.`;
}
function removeAsg(strategy, account) {
  const cur = (ST.book[strategy] || []).filter(a => a.account !== account);
  setBook(strategy, cur);
}
let FREEZE = false;               // pause re-render while a menu/edit is open
let ASG_OPEN = null;              // the open + Assign menu: {menu, trigger} (W7: Esc, focus, arrows)
function toggleAsgMenu(strategy) {
  const m = $("#amenu-" + strategy);
  const open = m.hidden;
  document.querySelectorAll(".amenu").forEach(x => x.hidden = true);
  m.hidden = !open;
  FREEZE = !m.hidden;
  ASG_OPEN = m.hidden ? null : {menu: m, trigger: m.previousElementSibling};
  if (ASG_OPEN) { const first = m.querySelector(".mi2"); if (first) first.focus(); }   // focus goes in
}
/* Close any open + Assign menu; `refocus` (Esc) hands focus back to its + Assign button. */
function closeAsgMenus(refocus) {
  const was = ASG_OPEN;
  document.querySelectorAll(".amenu").forEach(x => x.hidden = true);
  ASG_OPEN = null;
  if (!document.getElementById("qedit")) FREEZE = false;
  if (refocus && was && was.trigger && document.contains(was.trigger)) was.trigger.focus();
  return !!was;
}
/* Booking a LIVE account onto a strategy asks first (2026-09-28, Apple-design audit S3): it is the
   step that makes a live account trade real money, so it gets the same dialog as connecting one
   or arming the desk. A demo account books at once, exactly as before. The account's environment
   is re-read at click time, and one the desk does not list counts as live (fail closed: ask).
   The dialog names the strategy, the account and the size that will be sent -- frozen from the
   click. The rest of the book is read after the answer, so a change that landed meanwhile (an
   account unbooked in another window) is never written back. Cancel sends nothing. Raising a
   live booking's size asks the same way -- but only from Enter: a blur (a click anywhere else,
   Kill included) never opens a dialog, it reverts the raise and says so (review M2). Lowering a
   size, or unbooking (removeAsg), never asks -- the safer direction (the desk's one confirm
   policy). "Book live" is the neutral primary button, never Kill's red. */
function isDemoAcct(id) {
  const a = ((ST && ST.accounts) || {})[id];
  return !!a && (a.env === "demo" || a.env === "paper");     // paper: no money at all
}
/* The confirms' check (booking, a size raise, the cycle): real money unless the account is paper. Funded PA/LTF prop
   accounts are live=False, so the desk sends them as env "demo" and a demo account cannot be told from a funded one
   (audit 2026-10-27, waits on a stake field): isDemoAcct stays the display word, this asks wherever money may be at stake. */
function isRealAcct(id) {
  const a = ((ST && ST.accounts) || {})[id];
  return !(a && a.env === "paper");
}
/* "APEX…048" / "…885": a broker's long numbered name shortened the way the chart page shows it,
   keeping a short letter prefix when there is one; a plain label ("Lucid Funded") stays whole. */
function acctShort(id) {
  const a = ((ST && ST.accounts) || {})[id];
  const s = String((a && a.label) || id || "");
  if (s.length < 10 || (s.match(/[0-9]/g) || []).length < 5) return s;
  const pre = (/^[A-Za-z]+/.exec(s) || [""])[0];
  return (pre.length <= 8 ? pre.toUpperCase() : "") + "…" + s.slice(-3);
}
/* a strategy's fire moment for display ("9:30", "8:30"): its cfg.fire_et, 9:30 when the desk does not say */
function fireHM(strategy) {
  const f = String(((((ST && ST.strategies) || {})[strategy]) || {}).cfg?.fire_et || "09:30:00");
  return hbClock(String(parseInt(f.slice(0, 2), 10)) + ":" + f.slice(3, 5));
}
function liveBookingNote(strategy, account) {
  const c = ((((ST && ST.strategies) || {})[strategy]) || {}).cfg || {};
  const a = ((ST && ST.accounts) || {})[account];
  const full = String((a && a.label) || account || "");
  const acct = full !== acctShort(account) ? ` Account ${full}.` : "";
  if (!a) return `This account is not in the desk's list right now, so it is treated as LIVE.${acct}`;
  if (c.kind === "lab") return DeskLab.LIVE_NOTE + acct;
  if (c.shadow) return "It is a SHADOW strategy: its signals are journaled, never placed — the booking " +
    `stands if that changes.${acct}`;
  const when = c.kind === "bars" ? "on its next signal" : c.self_fire ? `at the next ${fireHM(strategy)} fire` : "on its next signal";
  const idle = [];
  if (!c.enabled) idle.push(stratLabel(strategy) + " is off");
  if (ST && !ST.armed) idle.push("the desk is disarmed");
  return `It will trade real money ${when}.` +
    (idle.length ? ` Right now ${idle.join(" and ")}, so nothing is placed until that changes.` : "") + acct;
}
const bookMachine = () => machineWords() ? ` It runs ${machineWords()}.` : "";     // the one machine reader (core.js)
async function pickAsg(strategy, account, qty) {
  FREEZE = false;
  closeAsgMenus(false);
  const was = ((ST.book[strategy] || []).find(a => a.account === account) || {}).qty;
  if (isRealAcct(account) && !await confirmDlg(
      `Book ${stratLabel(strategy)} on ${acctShort(account)} LIVE, qty ${was ? was + " → " : ""}${qty}?`,
      liveBookingNote(strategy, account) + bookMachine(), "Book live", false)) { refresh(); return; }
  const cur = (ST.book[strategy] || []).filter(a => a.account !== account);
  cur.push({account, qty});
  setBook(strategy, cur);
}
function editQty(ev, strategy, account, qty) {
  ev.stopPropagation();
  const span = ev.currentTarget;
  FREEZE = true;
  span.outerHTML = `<input class="qty-input" id="qedit" type="number" min="1" value="${qty}">`;
  const inp = $("#qedit");
  inp.focus(); inp.select();
  let done = false;                 // one commit per edit, however many blurs follow
  // explicit: Enter. A blur -- a click anywhere else, Kill included -- never opens a dialog under
  // the pointer: a live raise is reverted instead, and the page says so (review M2).
  const commit = async (explicit) => {
    if (done) return;
    done = true;
    FREEZE = false;
    const v = parseInt(inp.value || "0", 10);
    if (v > 0 && v !== qty) {
      if (v > qty && isRealAcct(account)) {
        if (!explicit) {
          toast(`${stratLabel(strategy)} on ${acctShort(account)} stays × ${qty} — ` +
                "press Enter to raise a LIVE booking.");
          refresh(); return;
        }
        if (!await confirmDlg(
            `Book ${stratLabel(strategy)} on ${acctShort(account)} LIVE, qty ${qty} → ${v}?`,
            liveBookingNote(strategy, account) + bookMachine(), "Book live", false)) { refresh(); return; }
      }
      const cur = (ST.book[strategy] || []).map(a =>
        a.account === account ? {account, qty: v} : a);
      setBook(strategy, cur);
    } else refresh();
  };
  inp.addEventListener("blur", () => commit(false));
  inp.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      // (review M4) Enter's own default action would land on whatever has focus AFTER this handler
      // -- the confirm's Cancel, which the dialog just focused -- and cancel it. Stop it first.
      e.preventDefault();
      if (e.repeat) return;
      commit(true);
      if (document.activeElement === inp) inp.blur();   // no dialog opened: leave the field as before
    }
    if (e.key === "Escape") { inp.value = qty; inp.blur(); }
  });
}
document.addEventListener("click", (e) => {
  if (!e.target.closest(".amenu") && !String(e.target.getAttribute?.("onclick") || "").includes("toggleAsgMenu")) {
    closeAsgMenus(false);
  }
});
function mstrip(rows) {
  return `<div class="mstrip">` + Object.entries(rows).map(([k, v]) =>
    `<span class="mi"><b>${k}</b>${v}</span>`).join("") + `</div>`;
}

/* ---- connect wizard ---- */
let WIZ = {saved: null, key: null, accounts: [], picks: new Set(), env: "demo", broker: "tv", busy: false};
function openConnect() {
  wizBroker("tv"); wizGoto(1); showOverlay("connectOverlay");
}
/* Step 1's broker choice. Vest is a wallet login that lists its demo and funded accounts together, so the Demo/Live
   switch is hidden for it (WIZ.env "vest" is what its saved logins carry) and comes back for Tradovate. */
function wizBroker(b) {
  WIZ.broker = b === "vest" ? "vest" : "tv";
  $("#optTv").classList.toggle("sel", WIZ.broker === "tv");
  $("#optVest").classList.toggle("sel", WIZ.broker === "vest");
  setEnv(WIZ.broker === "vest" ? "vest" : "demo");
  if (WIZ.broker === "vest") vestWarm();
}
function setEnv(env) {
  if (WIZ.env !== env) WIZ.saved = null;          // saved logins are per env
  WIZ.env = env;
  $("#envSeg").style.display = env === "vest" ? "none" : "";
  $("#envDemo").classList.toggle("sel", env === "demo");
  $("#envLive").classList.toggle("sel", env === "live");
  $("#envDemo").setAttribute("aria-pressed", String(env === "demo"));
  $("#envLive").setAttribute("aria-pressed", String(env === "live"));
  const n = $("#envNote");
  n.textContent = env === "vest"
    ? "A Vest login lists its demo and funded accounts together. A funded account is never ticked for you."
    : env === "live"
    ? "LIVE — real money. Orders on a live account are real. It won't trade until you assign it to a strategy."
    : "Demo is the safe default.";
  n.style.color = env === "live" ? "var(--destructive)" : "";
  $("#envTag2").innerHTML = env === "live"
    ? '<span class="tag-live" style="vertical-align:middle" title="A live login — real money">LIVE</span>' : "";
}
async function wizNext1() {
  if (WIZ.env === "live" && !(await confirmDlg("Connect a LIVE account?",
      `This account trades real money${machineWords() ? " " + machineWords() : ""}. Adding it does not start trading — it ` +
      "only trades after you assign it to a strategy.", "Yes, connect live", true)))
    return;
  wizGoto(2);
}
function closeConnect() {
  hideOverlay("connectOverlay");
  const p = $("#cPass"); if (p) p.value = "";
  VW.typed = null; VW.addr = null;
}
function wizGoto(n) {
  $("#wstepP").style.display = "none";
  const vest = WIZ.broker === "vest";
  $("#wstep2v").style.display = n === 2 && vest ? "" : "none";
  for (const i of [1, 2, 3, 4]) {
    $("#wstep" + i).style.display = i === n && !(i === 2 && vest) ? "" : "none";
    const st = $("#ws" + i);
    if (st) st.className = "st" + (i === n || (i === 3 && n === 4) ? " cur" : i < n ? " done" : "");
  }
  if (n === 2) { VW.typed = null; VW.addr = null; loadLogins(); }
}
async function loadLogins() {
  const d = await (await fetch("/api/logins")).json();
  d.logins = d.logins.filter(l => l.env === WIZ.env);   // demo, live OR vest logins
  const box = $(WIZ.broker === "vest" ? "#savedLoginsV" : "#savedLogins");
  if (!d.logins.length) { box.innerHTML =
    `<p class="wnote" style="margin:0 0 10px">none yet — type a login below</p>`;
    pickLogin(null); return; }
  // a saved login's key and label are text the user typed (second review): escaped, the key passed to
  // the handlers as a JS string literal (jsArg), and read back for the selection from data-login
  box.innerHTML = d.logins.map(l => `
    <div class="opt ${WIZ.saved === l.key ? "sel" : ""}" data-login="${esc(l.key)}" onclick="pickLogin(${jsArg(l.key)})">
      <span><span class="t">${esc(l.label)}</span><br>
      <span class="sub">${esc(l.env === "vest" ? "wallet" : l.env)}${l.in_use ? " · connected now" : ""}</span></span>
      <span class="spacer"></span>
      <button class="x" onclick="event.stopPropagation();delLogin(${jsArg(l.key)})" title="Forget this login"><svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><use href="#ic-trash"/></svg></button>
      <span class="radio"></span>
    </div>`).join("");
  if (WIZ.saved === null && d.logins.length) pickLogin(d.logins[0].key);
}
function pickLogin(key) {
  WIZ.saved = key;
  if (WIZ.broker === "vest") { loadLoginsPaint(); vestPaint(); return; }
  $("#newLoginFields").style.display = key === null ? "" : "none";
  $("#optNew").classList.toggle("sel", key === null);
  loadLoginsPaint();
  if (key === null) $("#cUser").focus();
}
function loadLoginsPaint() {
  document.querySelectorAll("#savedLogins .opt, #savedLoginsV .opt").forEach(el => {
    el.classList.toggle("sel", WIZ.saved === el.getAttribute("data-login"));
  });
}
async function delLogin(key) {
  const r = await post("/api/logins/delete", {key});
  if (r.ok) { if (WIZ.saved === key) WIZ.saved = null; loadLogins(); }
  else toast("Can't delete — " + (r.detail || "in use"), 5000);
}
/* A good /api/connect answer (either broker): its login key and accounts, then step 3. */
function wizAccepted(r) {
  WIZ.key = r.key;
  WIZ.accounts = r.accounts || [];
  WIZ.picks = new Set();                // nothing is pre-ticked, a funded Vest account least of all
  renderAcctList(); wizGoto(3);
  const first = document.querySelector("#acctList input:not([disabled])");
  (first || document.querySelector("#wstep3 .btn-outline")).focus();
}
async function doConnect() {
  if (WIZ.broker === "vest") return vestGo();
  const btn = $("#cGo"); btn.disabled = true; btn.textContent = "Connecting…";
  try {
    const body = WIZ.saved ? {saved_key: WIZ.saved}
      : {username: $("#cUser").value, password: $("#cPass").value, env: WIZ.env};
    const r = await post("/api/connect", body);
    if (r.ok) wizAccepted(r);
    else toast("Connect failed — " + (r.error || r.detail || "unknown"), 6000);
  } finally { btn.disabled = false; btn.textContent = "Find my accounts"; refresh(); }
}
/* ---- Vest: the wallet signs Vest's EIP-712 login message once (the working spike, 2026-10-29). Two clicks, because
   Safari blocks a second wallet pop-up that no click started: 1. Connect (eth_requestAccounts, then the challenge)
   and 2. Sign (eth_signTypedData_v4, then /api/connect). The signature lives in one local variable of vestSign, only
   until the POST returns: never a global, never storage, never logged. The Coinbase SDK (vendored, one file) is
   loaded only once Vest is chosen, and started then so the click that connects needs no download first. */
const VW = {eth: null, addr: null, typed: null, sdk: null, found: [], busy: false};
function vestWarm() {
  if (!VW.sdk) VW.sdk = import("/static/vendor/coinbase-wallet-sdk-4.3.7.js").catch(() => null);
  if (VW.listening) return;
  VW.listening = true;                  // EIP-6963: wallets announce themselves even when window.ethereum is not set
  window.addEventListener("eip6963:announceProvider", (e) => VW.found.push(e.detail));
  window.dispatchEvent(new Event("eip6963:requestProvider"));
}
function vestBrowserProvider() {
  const ok = VW.found.find(d => /meta|rabby|coinbase|phantom|okx|trust|rainbow|zerion|brave/i.test(d.info.name)) || VW.found[0];
  return ok ? ok.provider : (window.ethereum || (window.phantom && window.phantom.ethereum) || window.coinbaseWalletExtension || null);
}
function vestSay(t, bad) {
  const el = $("#vStatus"); el.textContent = t; el.style.color = bad ? "var(--destructive)" : "";
}
const vestShort = (a) => a.slice(0, 6) + "…" + a.slice(-4);
function vestPaint() {
  const fresh = WIZ.saved === null;
  $("#optNewV").classList.toggle("sel", fresh);
  $("#vWallet").style.display = fresh ? "" : "none";
  const go = $("#vGo");
  go.textContent = fresh ? "2. Sign" : "Find my accounts";
  go.disabled = fresh && !VW.typed;
}
async function vestConnect(kind) {
  if (VW.busy) return;
  VW.busy = true; VW.typed = null; vestPaint();
  try {
    vestSay("Waiting for your wallet…");
    let eth = null;
    if (kind === "coinbase") {
      const m = await VW.sdk;
      if (!m) { vestSay("Coinbase Wallet could not load. Try the browser wallet.", true); return; }
      eth = m.createCoinbaseWalletSDK({appName: "Homebase", appChainIds: [8453], preference: {options: "all"}}).getProvider();
    } else eth = vestBrowserProvider();
    if (!eth) { vestSay("No browser wallet found. Use the Coinbase Wallet button.", true); return; }
    const accts = await eth.request({method: "eth_requestAccounts"});
    const addr = Array.isArray(accts) && typeof accts[0] === "string" ? accts[0] : "";
    if (!addr) { vestSay("The wallet gave no address.", true); return; }
    const r = await post("/api/vest/challenge", {address: addr});
    if (!r.ok) { const why = r.error || r.detail || "unknown"; vestSay("Connect failed — " + why, true); toast("Connect failed — " + why, 6000); return; }
    VW.eth = eth; VW.addr = addr; VW.typed = r.typed_data;
    vestSay("Wallet " + vestShort(addr) + " connected. Now click 2. Sign.");
  } catch (e) { vestSay("Wallet: " + ((e && e.message) || "no answer"), true); }
  finally { VW.busy = false; vestPaint(); }
}
async function vestGo() {
  if (WIZ.saved !== null) return vestSaved();
  if (VW.busy || !VW.typed || !VW.eth) return;
  VW.busy = true;
  const btn = $("#vGo"); btn.disabled = true; btn.textContent = "Waiting for your wallet…";
  const typed = VW.typed, addr = VW.addr, eth = VW.eth;
  VW.typed = null;                      // a challenge is good for one try: a new Connect is needed after this
  let sig = null;
  try {
    sig = await eth.request({method: "eth_signTypedData_v4", params: [addr, typed]});
    btn.textContent = "Connecting…";
    const r = await post("/api/connect", {broker: "vest", address: addr, signature: sig});
    sig = null;
    if (r.ok) { vestSay(""); wizAccepted(r); }
    else { const why = r.error || r.detail || "unknown"; vestSay("Connect failed — " + why + ". Connect the wallet again.", true); toast("Connect failed — " + why, 6000); }
  } catch (e) { vestSay("Wallet: " + ((e && e.message) || "no answer") + ". Connect the wallet again.", true); }
  finally { sig = null; VW.busy = false; vestPaint(); refresh(); }
}
/* a saved Vest login: its session may renew itself; if it needs a new signature the route says so */
async function vestSaved() {
  if (VW.busy) return;
  VW.busy = true;
  const btn = $("#vGo"); btn.disabled = true; btn.textContent = "Connecting…";
  try {
    const r = await post("/api/connect", {saved_key: WIZ.saved});
    if (r.ok) { vestSay(""); wizAccepted(r); }
    else {
      const why = r.error || r.detail || "unknown";
      toast("Connect failed — " + why, 6000);
      if (/new wallet signature/.test(why)) { pickLogin(null); vestSay("This login needs a new wallet signature. Connect your wallet below.", true); }
      else vestSay("Connect failed — " + why, true);
    }
  } catch (_) { vestSay("Connect failed — the desk didn't answer.", true); }
  finally { VW.busy = false; vestPaint(); refresh(); }
}
/* The accounts step: every account under the login, one checkbox each plus Select all. The server says
   which are already on the desk (on_desk, by the broker account the entry is pinned to or rides); those
   can't be ticked. Every broker-supplied name is escaped, and reaches its handler through jsArg. */
const wizOnDesk = (a) => a.on_desk !== undefined ? !!a.on_desk
  : Object.keys((ST && ST.accounts) || {}).includes(String(a.name).toLowerCase());
/* A Vest row's kind in words (Demo / Funded / Primary); a Tradovate row has none. */
const vestKind = (a) => WIZ.broker !== "vest" ? "" : ({demo: "Demo", funded: "Funded", primary: "Primary"}[a.kind]
  || (a.demo === undefined ? "" : a.demo ? "Demo" : "Funded"));
const wizAddable = () => WIZ.accounts.filter(a => !wizOnDesk(a));
function renderAcctList() {
  const el = $("#acctList");
  if (!WIZ.accounts.length) { el.innerHTML =
    `<p class="wnote">the login verified but exposed no account list — if it
     should have accounts, check the login on the broker side.</p>`; wizCount(); return; }
  const rows = WIZ.accounts.map(a => {
    const added = wizOnDesk(a);
    return `
    <label class="copt ${added ? "disabled" : ""}">
      <input type="checkbox" ${added ? "disabled" : ""} ${!added && WIZ.picks.has(a.name) ? "checked" : ""}
             onchange="wizTick(${jsArg(a.name)}, this.checked)">
      <span><span class="t">${esc(a.name)}</span><br>
      <span class="sub">${added ? "already added" : vestKind(a) || (a.active === false ? "inactive" : "active")}</span></span>
    </label>`;
  }).join("");
  el.innerHTML = `<label class="copt all ${wizAddable().length ? "" : "disabled"}">
      <input type="checkbox" id="wAll" ${wizAddable().length ? "" : "disabled"} onchange="wizAll(this.checked)">
      <span class="t">Select all</span></label>` + rows;
  wizCount();
}
function wizTick(name, on) {
  if (on) WIZ.picks.add(name); else WIZ.picks.delete(name);
  wizCount();
}
function wizAll(on) {
  WIZ.picks = new Set(on ? wizAddable().map(a => a.name) : []);
  document.querySelectorAll("#acctList .copt:not(.all) input:not([disabled])").forEach(c => { c.checked = on; });
  wizCount();
}
function wizCount() {
  const n = wizAddable().filter(a => WIZ.picks.has(a.name)).length, all = wizAddable().length;
  const btn = $("#cUse");
  btn.disabled = n === 0;
  btn.textContent = n === 0 ? "Add accounts" : n === 1 ? "Add 1 account" : "Add " + n + " accounts";
  const box = $("#wAll");
  if (box) { box.checked = all > 0 && n === all; box.indeterminate = n > 0 && n < all; }
}
/* One line per account, in plain words. `r` is the desk's answer, or a refusal ({detail}). */
function wizResult(r) {
  const rows = (r && r.results) || [];
  const said = {
    added: (x) => x.connected
      ? ["Added and connected" + (x.mode === "login" ? " — it had to log in again." : "."), ""]
      : ["Added, but not connected yet" + (x.error ? ": " + x.error : "."), "bad"],
    exists: () => ["Already on the desk.", ""],
    failed: (x) => /^not tried — /.test(x.error || "")
      ? ["Not tried: " + x.error.replace(/^not tried — /, "") + ". Add it again later.", "bad"]
      : ["Not added: " + (x.error || "unknown reason"), "bad"],
  };
  const nAdd = rows.filter(x => x.status === "added").length;
  const title = !rows.length ? "Nothing was added"
    : nAdd ? "Added " + nAdd + (nAdd === 1 ? " account" : " accounts")
    : rows.every(x => x.status === "exists") ? "Already on the desk" : "Nothing was added";
  const sub = !rows.length ? (r && (r.detail || r.error)) || "The desk didn't answer — check it and try again."
    : "None of them is booked to a strategy yet — book them on a strategy's page when you're ready." +
      (WIZ.env === "live" ? " These are LIVE accounts." : "");
  return {title, sub, html: rows.map(x => {
    const [text, cls] = (said[x.status] || said.failed)(x);
    return `<li><span class="t">${esc(x.name)}</span><span class="why ${cls}">${esc(text)}</span></li>`;
  }).join("")};
}
async function addSelected() {
  const names = wizAddable().filter(a => WIZ.picks.has(a.name)).map(a => a.name);
  if (!names.length || WIZ.busy) return;
  if (WIZ.broker === "vest") {          // a funded account is real money: asked every time, like a LIVE Tradovate login
    const live = wizAddable().filter(a => WIZ.picks.has(a.name) && vestKind(a) !== "Demo").map(a => a.name);
    if (live.length && !(await confirmDlg("Add a funded Vest account?",
        `${live.join(", ")} trade${live.length === 1 ? "s" : ""} real money${machineWords() ? " " + machineWords() : ""}. Adding it does not start ` +
        "trading — it only trades after you assign it to a strategy.", "Yes, add it", true)))
      return;
  }
  WIZ.busy = true;
  const btn = $("#cUse"); btn.disabled = true; btn.textContent = "Adding…";
  let r;
  try { r = await post("/api/accounts/add-many", {key: WIZ.key, accounts: names}); }
  catch (_) { r = null; }
  finally { WIZ.busy = false; refresh(); }
  const out = wizResult(r);
  if (!$("#connectOverlay").classList.contains("open")) {      // closed with Esc while it ran
    toast(out.title + (out.sub && !(r && r.results) ? " — " + out.sub : ""), 6000);
    return;
  }
  $("#wresTitle").textContent = out.title;
  $("#wresSub").textContent = out.sub;
  $("#wresList").innerHTML = out.html;
  WIZ.picks = new Set();
  wizGoto(4);
  $("#wDone").focus();                                          // focus follows the step; Esc / Done close it
}
$("#connectOverlay").addEventListener("click", (e) => {
  if (e.target === e.currentTarget) closeConnect();
});

