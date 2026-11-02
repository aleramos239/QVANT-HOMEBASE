/* ---- the account settings sheet (per-account settings, owner 2026-10-29) ----
   A Lab strategy's size and stops are edited from each ACCOUNT row of its page: this strategy on this account (Size, Most
   contracts, Stop after) and the whole account (profit lock, loss lock, shared by every strategy on it). The pure helpers
   are AcctSet (tests/js/acctset.test.mjs); the sheet is static markup (#acctSetOverlay) that render() never rebuilds, so a
   repaint cannot wipe a field being typed in, like the Limits dialog. */
const AcctSet = (() => {
  const risk = (r) => !!r && r.size === "risk";
  /* "×N" or "$X risk" */
  const label = (r) => risk(r) ? "$" + r.risk_usd + " risk" : "×" + r.qty;
  const tag = (r) => [r && r.stop_after === "win" ? "stops after a win" : r && r.stop_after === "profit" ? "stops in profit" : "",
    r && r.hold === true ? "holds overnight" : ""].filter(Boolean).join(", ");
  /* "$500 risk, stops after a win": label, Most when asked (the Changes lines), then the tag */
  const words = (r, most) => [label(r), most && r.most != null ? "most " + r.most : "", tag(r)].filter(Boolean).join(", ");
  /* The sheet's fields for a row. A row written before the settings (no `size`) opens as "own" ("The strategy's own"): it
     stays a plain {account, qty} row until the owner picks Contracts or Risk. */
  const formOf = (row) => ({
    size: row.size ? row.size : "own", qty: row.qty || 1, risk_usd: risk(row) ? row.risk_usd : "",
    stop_after: row.stop_after || "none", most: row.size && row.most != null ? row.most : null, hold: row.hold === true});
  /* The book row for a filled sheet: "own" stays {account, qty} (never size or most); Most gone when removed, stop_after gone
     when "none", a risk row keeps the row's qty. */
  const rowFrom = (form, prev) => {
    const out = {account: prev.account, qty: form.size === "risk" ? (prev.qty || 1) : form.qty};
    if (form.size !== "own") out.size = form.size;
    if (form.size === "risk") out.risk_usd = form.risk_usd;
    if (form.stop_after && form.stop_after !== "none") out.stop_after = form.stop_after;
    if (form.size !== "own" && form.most != null) out.most = form.most;
    if (form.hold === true) out.hold = true;
    return out;
  };
  /* A LIVE account asks before anything that can send more: more contracts, more risk, a switch to risk, a plain row given a
     size (an own-size strategy may then send more), a risk row's Most raised or removed. Risk back to contracts asks too (the
     two sizes cannot be compared). Lower, same, or a non-live account never asks. */
  const needsAsk = (prev, next, live) => {
    if (!live) return false;
    if (!next.size) return !!prev.size || next.qty > prev.qty;          // a plain row: only a bigger qty (as editQty)
    if (!prev.size) return true;
    if (next.size !== "risk") return risk(prev) || next.qty > prev.qty;
    const mostUp = next.most == null ? prev.most != null : prev.most != null && next.most > prev.most;
    return !risk(prev) || next.risk_usd > prev.risk_usd || mostUp;
  };
  /* The book with this account's row replaced (added when new); every other row stays exactly as it is. */
  const withRow = (book, row) => book.some(r => r.account === row.account)
    ? book.map(r => r.account === row.account ? row : r) : [...book, row];
  return {label, tag, words, formOf, rowFrom, needsAsk, withRow};
})();

let ACCT_SET = {strategy: "", account: "", tok: 0};
let ACCT_SAVING = false;
const acctSetRow = (s, a) => (((ST && ST.book) || {})[s] || []).find(r => r.account === a);
function acctSetNote(msg) { const n = $("#asNote"); n.textContent = msg || ""; n.hidden = !msg; }
/* Show only the fields the choices need: contracts or risk, and the Most box while it is on. */
function paintAcctSet() {
  const size = $("#asSize").value, risky = size === "risk", on = ACCT_SET.most != null;
  $("#asQtyF").hidden = risky; $("#asRiskF").hidden = !risky;
  $("#asMostW").hidden = size === "own";                // Most applies only to Contracts and Risk rows
  $("#asMostF").hidden = !on;
  $("#asMostBtn").textContent = on ? "Remove" : "+ Add";
  $("#asMostOff").hidden = on;
}
/* The Size menu changed: a plain row given a size gets the Most box at the strategy's default. */
function acctSetSize() {
  if ($("#asSize").value !== "own" && !ACCT_SET.sized) {
    ACCT_SET.sized = true;
    ACCT_SET.most = ACCT_SET.mostDefault;
    $("#asMost").value = String(ACCT_SET.most);
  }
  paintAcctSet();
}
function toggleAcctMost() {
  ACCT_SET.most = ACCT_SET.most != null ? null : ACCT_SET.mostDefault;
  if (ACCT_SET.most != null) $("#asMost").value = String(ACCT_SET.most);
  paintAcctSet();
}
function openAcctSet(strategy, account) {
  const row = acctSetRow(strategy, account), s = ((ST && ST.strategies) || {})[strategy];
  if (!row || !s || !s.lab) return;
  const def = Number(s.lab.most_default) || 2, form = AcctSet.formOf(row);
  const day = (((ST && ST.accounts) || {})[account] || {}).day || {};
  ACCT_SET = {strategy, account, form, mostDefault: def, most: form.most, sized: !!row.size, take: Number(day.day_lock) || 0, loss: Number(day.day_loss) || 0, tok: ACCT_SET.tok + 1};
  $("#asTitle").textContent = `${stratLabel(strategy)} on ${acctShort(account)}`;
  const own = $("#asOwn");              // "own" is offered only for a row that has no size
  own.hidden = own.disabled = !!row.size;
  own.textContent = `The strategy's own (×${row.qty})`;
  $("#asMostOff").textContent = `No limit set here. One order never goes over ${def < 10 ? "10 minis" : "100 micros"}.`;
  $("#asSize").value = form.size;
  $("#asQty").value = String(form.qty);
  $("#asRisk").value = form.risk_usd === "" ? "" : String(form.risk_usd);
  $("#asMost").value = form.most != null ? String(form.most) : "";
  $("#asStop").value = form.stop_after;
  $("#asHold").value = form.hold ? "yes" : "no";
  $("#asTake").value = ACCT_SET.take || "";
  $("#asLoss").value = ACCT_SET.loss || "";
  const cyc = Object.values((ST && ST.groups) || {}).find(g => g && g.on && (Number((g.risk_by || {})[strategy]) || Number(g.risk_usd) || 0) > 0 && (g.members || []).includes(strategy)
    && (!Array.isArray(g.accounts) || g.accounts.includes(account)));
  const note = $("#asCycle");
  note.textContent = cyc ? "The account group sizes this strategy while it is on." : "";
  note.hidden = !cyc;
  acctSetNote("");
  paintAcctSet();
  $("#asSave").disabled = ACCT_SAVING;
  showOverlay("acctSetOverlay");
}
function acctSetKey(e) { if (e.key === "Enter" && !e.repeat) { e.preventDefault(); saveAcctSet(); } }      // Enter saves; a held key does not
function closeAcctSet() {
  hideOverlay("acctSetOverlay");
  ACCT_SET = {strategy: "", account: "", tok: ACCT_SET.tok + 1};
}
/* The sheet as numbers: {form, take, loss}, or {error} with the sentence. */
function readAcctSet() {
  const num = (v) => { const t = String(v == null ? "" : v).trim().replace(/^\$/, ""); return t === "" ? NaN : Number(t); };
  const whole = (v, lo, hi) => Number.isInteger(v) && v >= lo && v <= hi;
  const prev = acctSetRow(ACCT_SET.strategy, ACCT_SET.account) || {}, size = $("#asSize").value, risky = size === "risk";
  const form = {size: risky ? "risk" : size === "own" ? "own" : "contracts", qty: prev.qty || 1, risk_usd: "", stop_after: $("#asStop").value || "none", most: null, hold: $("#asHold").value === "yes"};
  if (risky) {
    form.risk_usd = num($("#asRisk").value);
    if (!(Number.isFinite(form.risk_usd) && form.risk_usd > 0 && form.risk_usd <= 100000)) return {error: "Risk is a dollar amount above 0, up to 100000."};
  } else {
    form.qty = num($("#asQty").value);
    if (!whole(form.qty, 1, 1000000)) return {error: "Contracts is a whole number above 0."};
  }
  if (ACCT_SET.most != null && size !== "own") {
    form.most = num($("#asMost").value);
    if (!whole(form.most, 1, 1000)) return {error: "Most contracts is a whole number from 1 to 1000."};
  }
  const lock = (id, top) => { const t = String($(id).value).trim(), v = t === "" ? 0 : num(t);
    return Number.isFinite(v) && v >= 0 && v <= top ? v : null; };
  const take = lock("#asTake", 100000), loss = lock("#asLoss", 100000);
  if (take == null) return {error: "The profit lock is a dollar amount from 0 (off) to 100000."};
  if (loss == null) return {error: "The loss lock is a dollar amount from 0 (off) to 100000."};
  return {form, take, loss};
}
async function saveAcctSet() {
  const S = ACCT_SET, tok = S.tok;
  if (!S.strategy || ACCT_SAVING) return;
  const got = readAcctSet();
  if (got.error) { acctSetNote(got.error); return; }
  acctSetNote("");
  const {strategy, account} = S, N = stratLabel(strategy), who = acctShort(account);
  let prev = acctSetRow(strategy, account);
  if (!prev) { toast(`${who} is no longer booked on ${N}.`, 5000); closeAcctSet(); return; }
  const rowChanged = JSON.stringify(got.form) !== JSON.stringify(S.form), next = AcctSet.rowFrom(got.form, prev);
  const lockBody = {};
  if (got.take !== S.take) lockBody.day_lock = got.take;
  if (got.loss !== S.loss) lockBody.day_loss = got.loss;
  if (!rowChanged && !Object.keys(lockBody).length) { closeAcctSet(); return; }
  ACCT_SAVING = true; $("#asSave").disabled = true;
  try {
    // asks first, before anything is sent: a bigger size on a LIVE account, or a lock switched off
    if (rowChanged && AcctSet.needsAsk(prev, next, isRealAcct(account)) && !await confirmDlg(
        `Book ${N} on ${who} LIVE, ${AcctSet.label(prev)} → ${AcctSet.label(next)}?`,
        liveBookingNote(strategy, account) + bookMachine(), "Book live", false)) return;
    if (rowChanged && next.hold === true && prev.hold !== true && !await confirmDlg(`Hold ${N} on ${who} overnight?`,
        "At its flat time the Desk leaves a filled trade open on its broker stop and target, through the 5 pm close and the night. " +
        "Until it closes, this strategy takes no new trade on this account, and other strategies on the same market here wait too. " +
        "A prop firm may close it or break a rule at its own cutoff.", "Hold overnight", false)) return;
    const off = [lockBody.day_lock === 0 ? "profit lock" : "", lockBody.day_loss === 0 ? "loss lock" : ""].filter(Boolean);
    if (off.length && !await confirmDlg(`Turn the ${off.join(" and ")} OFF for ${who}?`,
        "Nothing stops the account for the day by that amount: every strategy booked on it keeps taking new trades.", "Turn it off", false)) return;
    if (ACCT_SET.tok !== tok) return;                       // closed or opened again while it asked
    if (rowChanged) {
      const cur = ((ST.book && ST.book[strategy]) || []);    // read after the answer: a row removed meanwhile is never written back
      if (!cur.some(r => r.account === account)) { toast(`${who} is no longer booked on ${N}.`, 5000); closeAcctSet(); return; }
      const r = await post("/api/book", {strategy, assignments: AcctSet.withRow(cur, next)});
      if (!r || r.ok !== true) { if (ACCT_SET.tok === tok) acctSetNote(DeskLab.refusalText(r || {}) || "Could not save the size."); return; }
      if (ACCT_SET.tok === tok) ACCT_SET.form = got.form;     // saved: a second Save sends only what changes after it
    }
    if (Object.keys(lockBody).length) {
      const r = await post("/api/account-day-lock", {account, ...lockBody});
      if (!r || r.ok !== true) { if (ACCT_SET.tok === tok) acctSetNote((r && r.detail) || "Could not set the lock."); refresh(); return; }
      if (r.locked) toast(`${who} is already past a lock today, so it takes no new trade for the rest of the day. Open trades run to their stop or target.`, 8000);
    }
    if (ACCT_SET.tok === tok) closeAcctSet();
    toast(`${N} on ${who}: saved.`);
    refresh();
  } catch (e) { if (ACCT_SET.tok === tok) acctSetNote("The Desk did not answer. Try again."); refresh();
  } finally { ACCT_SAVING = false; if (ACCT_SET.strategy) $("#asSave").disabled = false; }
}
