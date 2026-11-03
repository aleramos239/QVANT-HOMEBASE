/* ---- per-account settings: the pure helpers (tests/js/acctset.test.mjs). A Lab strategy's size and stops on one account
   (Size, Most contracts, Stop after) and the whole account's profit lock and loss lock (owner 2026-10-29). ---- */
const AcctSet = (() => {
  const risk = (r) => !!r && r.size === "risk";
  /* "×N" or "$X risk" */
  const label = (r) => risk(r) ? "$" + r.risk_usd + " risk" : "×" + r.qty;
  const tag = (r) => [r && r.stop_after === "win" ? "stops after a win" : r && r.stop_after === "profit" ? "stops in profit" : "",
    r && r.hold === true ? "holds overnight" : ""].filter(Boolean).join(", ");
  /* "FLEX · 1 NQ", "FAST · $500 risk · MNQ", "3 MNQ · most 20": variant, size, the contract after a $ risk, Most when asked, the tag */
  const words = (r, variant, most) => {
    const c = r && r.contract;
    return [variant, risk(r) ? "$" + r.risk_usd + " risk" : c ? (+r.qty || 1) + " " + c : "×" + r.qty, risk(r) ? c : "",
      most && r.most != null ? "most " + r.most : "", tag(r)].filter(Boolean).join(" · ");
  };
  const ownWords = (usd) => "its own $" + usd + " a trade";
  /* Another contract: Contracts back to 1, Most to that contract's default, $ risk kept */
  const switchContract = (form, to, mostBy) => ({...form, contract: to, qty: 1, most: mostBy[to] != null ? mostBy[to] : form.most});
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
  const needsAsk = (prev, next, live, contracts = []) => {
    if (!live) return false;
    const ix = (r) => contracts.indexOf(r.contract || contracts[0]);
    if (ix(next) > ix(prev)) return true;                                // the bigger contract is later (MNQ -> NQ)
    if (next.size === "contracts" && prev.size === "contracts" && (next.most == null ? prev.most != null : prev.most != null && next.most > prev.most)) return true;
    if (!next.size) return !!prev.size || next.qty > prev.qty;          // a plain row: only a bigger qty (as editQty)
    if (!prev.size) return true;
    if (next.size !== "risk") return risk(prev) || next.qty > prev.qty;
    const mostUp = next.most == null ? prev.most != null : prev.most != null && next.most > prev.most;
    return !risk(prev) || next.risk_usd > prev.risk_usd || mostUp;
  };
  /* The book with this account's row replaced (added when new); every other row stays exactly as it is. */
  const withRow = (book, row) => book.some(r => r.account === row.account)
    ? book.map(r => r.account === row.account ? row : r) : [...book, row];
  return {label, tag, words, ownWords, switchContract, formOf, rowFrom, needsAsk, withRow};
})();
