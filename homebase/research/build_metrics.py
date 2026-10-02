"""Build the full metrics table for a research equity artifact.

Reads the per-trade cumulative curve already in the artifact (extracted from
a real TV trade-list export), derives per-trade P&L, and computes EVERY
descriptive stat honestly from that one dataset — then runs the house
LucidFlex prop sim (onyx.report.propsim, i.i.d. weekday bootstrap) on the
same ledger. Nothing is typed in by hand; rerunning regenerates the table.

Run with the ONYX venv (needs the onyx package for the prop sim):
    "$ONYX/.venv/bin/python" build_metrics.py nq930_equity.json
"""
from __future__ import annotations

import datetime as dt
import json
import math
import sys
from pathlib import Path

ONYX = "/Users/ramoscapital/ONYX TRADING"
HERE = Path(__file__).resolve().parent


def money(v):  # matches the app's dollar style
    return ("-$" if v < 0 else "$") + f"{abs(v):,.2f}"


def pct(v):
    return f"{100 * v:.1f}%"


def ledger_table(dates, pnl, *, cum=None, period="month", sharpe=True) -> list:
    """The descriptive table [[section, key, value], ...] of ONE trade ledger: `dates` (ISO, one per
    trade) and `pnl` ($ per trade).  `cum` = the cumulative curve when the caller already has it (else
    the running sum).  `period` = the stability bucket: "month" (the default) or "year" for a ledger with
    about one trade a month.  `sharpe=False` leaves the annualised Sharpe row out (it assumes a trade most
    days).  Shared by build() below and build_algo_metrics.py."""
    if cum is None:
        cum, c = [], 0.0
        for p in pnl:
            c = round(c + p, 2)
            cum.append(c)
    n = len(pnl)
    cut = {"month": 7, "year": 4}[period]

    wins = [p for p in pnl if p > 0]
    losses = [p for p in pnl if p < 0]
    wr = len(wins) / n
    avg = sum(pnl) / n
    std = math.sqrt(sum((p - avg) ** 2 for p in pnl) / (n - 1))
    t_tr = avg / std * math.sqrt(n) if std else 0.0
    avg_w = sum(wins) / len(wins) if wins else 0.0
    avg_l = sum(losses) / len(losses) if losses else 0.0
    pf = (sum(wins) / -sum(losses)) if losses else float("inf")
    rr = (avg_w / -avg_l) if avg_l else float("inf")

    # daily series
    by_day: dict[str, float] = {}
    for d, p in zip(dates, pnl):
        by_day[d] = by_day.get(d, 0.0) + p
    dvals = list(by_day.values())
    dn = len(dvals)
    davg = sum(dvals) / dn
    dstd = math.sqrt(sum((v - davg) ** 2 for v in dvals) / (dn - 1))
    sharpe_v = davg / dstd * math.sqrt(252) if dstd else 0.0
    green_days = sum(1 for v in dvals if v > 0)

    # drawdown / runup on the trade-by-trade curve
    peak, mdd, mdd_date, runup, trough = 0.0, 0.0, "", 0.0, 0.0
    dd_start, dd_days, cur_dd_start = None, 0, None
    for d, c in zip(dates, cum):
        if c > peak:
            peak = c
            if cur_dd_start:
                dd_days = max(dd_days, (dt.date.fromisoformat(d)
                                        - dt.date.fromisoformat(cur_dd_start)).days)
                cur_dd_start = None
        else:
            cur_dd_start = cur_dd_start or d
        if peak - c > mdd:
            mdd, mdd_date = peak - c, d
        trough = min(trough, c)
        runup = max(runup, c - trough)
    if cur_dd_start:
        dd_days = max(dd_days, (dt.date.fromisoformat(dates[-1])
                                - dt.date.fromisoformat(cur_dd_start)).days)

    # streaks — max AND average length of completed win/loss streaks
    mx_w = mx_l = cw = cl = 0
    wstreaks, lstreaks = [], []
    for p in pnl:
        if p > 0:
            if cl:
                lstreaks.append(cl)
            cw, cl = cw + 1, 0
        elif p < 0:
            if cw:
                wstreaks.append(cw)
            cl, cw = cl + 1, 0
        mx_w, mx_l = max(mx_w, cw), max(mx_l, cl)
    if cw:
        wstreaks.append(cw)
    if cl:
        lstreaks.append(cl)
    avg_ws = sum(wstreaks) / len(wstreaks) if wstreaks else 0.0
    avg_ls = sum(lstreaks) / len(lstreaks) if lstreaks else 0.0

    # monthly stability — the house wr_stability phi (chi2/df vs one coin)
    months: dict[str, list[float]] = {}
    for d, p in zip(dates, pnl):
        months.setdefault(d[:cut], []).append(p)
    mrows = {m: v for m, v in months.items() if len(v) >= 5}
    k = len(mrows)
    chi2 = 0.0
    for v in mrows.values():
        wm = sum(1 for p in v if p > 0) / len(v)
        chi2 += len(v) * (wm - wr) ** 2 / (wr * (1 - wr))
    phi = chi2 / (k - 1) if k > 1 else 0.0
    verdict = "steady" if phi <= 1.3 else ("wobbly" if phi <= 2.0 else "regime-driven")
    msum = {m: sum(v) for m, v in months.items()}
    green_m = sum(1 for v in msum.values() if v > 0)
    best_m = max(msum, key=msum.get)
    worst_m = min(msum, key=msum.get)

    T = []
    add = lambda s, l, v: T.append([s, l, v])  # noqa: E731
    add("Trades", "window", f"{dates[0]} → {dates[-1]}")
    add("Trades", "trades", str(n))
    add("Trades", "trading days", str(dn))
    add("Trades", "wins / losses / flat",
        f"{len(wins)} / {len(losses)} / {n - len(wins) - len(losses)}")
    add("Trades", "win rate", pct(wr))
    add("P&L", "net", money(cum[-1]))
    add("P&L", "avg / trade", money(avg))
    add("P&L", "std / trade", money(std))
    add("P&L", "t-stat (trades)", f"{t_tr:.2f}")
    add("P&L", "profit factor", f"{pf:.2f}")
    add("P&L", "avg win", money(avg_w))
    add("P&L", "avg loss", money(avg_l))
    add("P&L", "realized RR", f"1:{rr:.2f}")
    add("P&L", "best / worst trade",
        f"{money(max(pnl))} / {money(min(pnl))}")
    add("P&L", "avg / day", money(davg))
    add("P&L", "green days", f"{green_days}/{dn} ({pct(green_days / dn)})")
    add("Risk", "max drawdown", money(-mdd) + f" ({mdd_date})")
    add("Risk", "longest drawdown", f"{dd_days} days")
    add("Risk", "max runup", money(runup))
    if sharpe:
        add("Risk", "Sharpe (daily, ann.)", f"{sharpe_v:.2f}")
    add("Streaks", "max win streak", str(mx_w))
    add("Streaks", "max loss streak", str(mx_l))
    add("Streaks", "avg win streak", f"{avg_ws:.2f}")
    add("Streaks", "avg loss streak", f"{avg_ls:.2f}")
    if k > 1 or period == "month":      # phi needs >= 2 buckets of >= 5 trades (always printed for months, as before)
        add("Stability", "WR stability φ", f"{phi:.2f} ({verdict})")
    add("Stability", f"green {period}s",
        f"{green_m}/{len(msum)} ({pct(green_m / len(msum))})")
    add("Stability", f"best {period}", f"{best_m} {money(msum[best_m])}")
    add("Stability", f"worst {period}", f"{worst_m} {money(msum[worst_m])}")
    mwr = {m: sum(1 for p in v if p > 0) / len(v) for m, v in mrows.items()}
    if mwr:
        bw, ww = max(mwr, key=mwr.get), min(mwr, key=mwr.get)
        add("Stability", f"best {period} WR",
            f"{bw} {pct(mwr[bw])} ({len(mrows[bw])} trades)")
        add("Stability", f"worst {period} WR",
            f"{ww} {pct(mwr[ww])} ({len(mrows[ww])} trades)")
    return T


def build(path: Path) -> None:
    art = json.loads(path.read_text())
    pts = art["points"]
    dates = [p[0] for p in pts]
    cum = [p[1] for p in pts]
    pnl = [cum[0]] + [round(cum[i] - cum[i - 1], 2) for i in range(1, len(cum))]
    n = len(pnl)
    T = ledger_table(dates, pnl, cum=cum)
    by_day: dict[str, float] = {}
    for d, p in zip(dates, pnl):
        by_day[d] = by_day.get(d, 0.0) + p

    # ---- Monte Carlo: full parallel metric set, 3 columns per row
    # (metric, median, 5-95% of runs) across 10,000 bootstrap resamples.
    # Sharpe is exact here because this strategy is one trade per day.
    # phi is computed on consecutive 20-trade blocks (pseudo-months).
    import random
    rng = random.Random(11)
    N = 10000
    ks = ("wr", "net", "avg", "t", "pf", "avgw", "avgl", "rr", "dd",
          "runup", "ddlen", "ws", "ls", "aws", "als", "sharpe", "phi")
    mc = {k: [] for k in ks}
    B = 20                      # phi block size (trades)
    for _ in range(N):
        s = s2 = wsum = lsum = 0.0
        wn = ln = 0
        peak_ = trough_ = dd_ = ru_ = 0.0
        cw = cl = mw = ml = 0
        wst_n = wst_sum = lst_n = lst_sum = 0
        cur = 0.0
        dl = mdl = 0
        blocks = []
        bw = bn = 0
        for _ in range(n):
            p = pnl[rng.randrange(n)]
            s += p
            s2 += p * p
            bw += 1 if p > 0 else 0
            bn += 1
            if bn == B:
                blocks.append(bw)
                bw = bn = 0
            if p > 0:
                if cl:
                    lst_n += 1; lst_sum += cl
                wsum += p; wn += 1
                cw += 1; cl = 0
            elif p < 0:
                if cw:
                    wst_n += 1; wst_sum += cw
                lsum += p; ln += 1
                cl += 1; cw = 0
            mw = cw if cw > mw else mw
            ml = cl if cl > ml else ml
            cur += p
            if cur > peak_:
                peak_ = cur
                dl = 0
            else:
                dl += 1
                mdl = dl if dl > mdl else mdl
            if peak_ - cur > dd_:
                dd_ = peak_ - cur
            if cur < trough_:
                trough_ = cur
            if cur - trough_ > ru_:
                ru_ = cur - trough_
        if cw:
            wst_n += 1; wst_sum += cw
        if cl:
            lst_n += 1; lst_sum += cl
        avg_ = s / n
        var_ = (s2 - n * avg_ * avg_) / (n - 1)
        std_ = math.sqrt(var_) if var_ > 0 else 0.0
        aw = wsum / wn if wn else 0.0
        al = lsum / ln if ln else 0.0
        wr_ = wn / n
        chi2_ = sum(B * ((b / B) - wr_) ** 2 / (wr_ * (1 - wr_))
                    for b in blocks) if 0 < wr_ < 1 else 0.0
        mc["wr"].append(wr_)
        mc["net"].append(s)
        mc["avg"].append(avg_)
        mc["t"].append(avg_ / std_ * math.sqrt(n) if std_ else 0.0)
        mc["pf"].append(wsum / -lsum if lsum else float("inf"))
        mc["avgw"].append(aw)
        mc["avgl"].append(al)
        mc["rr"].append(aw / -al if al else float("inf"))
        mc["dd"].append(-dd_)
        mc["runup"].append(ru_)
        mc["ddlen"].append(mdl)
        mc["ws"].append(mw)
        mc["ls"].append(ml)
        mc["aws"].append(wst_sum / wst_n if wst_n else 0.0)
        mc["als"].append(lst_sum / lst_n if lst_n else 0.0)
        mc["sharpe"].append(avg_ / std_ * math.sqrt(252) if std_ else 0.0)
        mc["phi"].append(chi2_ / (len(blocks) - 1) if len(blocks) > 1 else 0.0)
    for k in ks:
        mc[k].sort()
    q = lambda a, p: a[min(len(a) - 1, int(p * len(a)))]  # noqa: E731
    num = lambda v: f"{v:.2f}"  # noqa: E731
    whole = lambda v: str(int(v))  # noqa: E731
    def mrow(sec, label, key, f):
        a = mc[key]
        return [sec, label, f(q(a, 0.5)), f"{f(q(a, 0.05))} … {f(q(a, 0.95))}"]
    MC = [
        mrow("Trades", "win rate", "wr", pct),
        mrow("P&L", "net", "net", money),
        mrow("P&L", "avg / trade", "avg", money),
        mrow("P&L", "t-stat (trades)", "t", num),
        mrow("P&L", "profit factor", "pf", num),
        mrow("P&L", "avg win", "avgw", money),
        mrow("P&L", "avg loss", "avgl", money),
        mrow("P&L", "realized RR", "rr", lambda v: f"1:{v:.2f}"),
        mrow("Risk", "max drawdown", "dd", money),
        mrow("Risk", "longest drawdown (trades)", "ddlen", whole),
        mrow("Risk", "max runup", "runup", money),
        mrow("Risk", "Sharpe (ann., 1 trade/day)", "sharpe", num),
        ["Risk", "P(net ≤ 0)", pct(sum(1 for v in mc["net"] if v <= 0) / N), ""],
        ["Risk", "maxDD, worst resample", money(mc["dd"][0]), ""],
        mrow("Streaks", "max win streak", "ws", whole),
        mrow("Streaks", "max loss streak", "ls", whole),
        mrow("Streaks", "avg win streak", "aws", num),
        mrow("Streaks", "avg loss streak", "als", num),
        mrow("Stability", "WR stability φ (20-trade blocks)", "phi", num),
    ]
    art["mc_table"] = MC
    art["mc_note"] = (f"{N:,} bootstrap resamples of the trade list (order "
                      "shuffled, i.i.d.). Median = the typical run; the band "
                      "holds 90% of runs. Example: max loss streak median 7, "
                      "band 5…11 = half the runs saw a worst losing streak of "
                      "7+, and only 5% saw worse than 11. Sharpe uses 1 "
                      "trade = 1 day (exact for this strategy); φ uses "
                      "20-trade blocks as pseudo-months.")

    # ---- prop sim: the house engine on this exact ledger ----
    sys.path.insert(0, ONYX)
    from onyx.report import ledger as L  # noqa: PLC0415
    from onyx.report import propsim  # noqa: PLC0415
    rules_name = "lucid-flex-50k@2026-08"
    rules = json.loads(Path(ONYX, "onyx/report/rules", rules_name + ".json")
                       .read_text())
    epoch = {(dt.date.fromisoformat(d) - dt.date(1970, 1, 1)).days: v
             for d, v in by_day.items()}
    grid, flags = L.weekday_grid_from_by_day(epoch)
    sim = propsim.run(grid, trade_flags=flags, rules=rules, n_paths=20000,
                      sweep=(), degradation=())
    ev, fu = sim["eval"], sim["funded"]
    md = lambda t: (t or {}).get("median")  # noqa: E731
    P = []
    P.append(["ruleset", "Lucid Flex 50K"])
    P.append(["eval pass", pct(ev["p"])])
    P.append(["median days to pass", str(md(ev.get("days")))])
    P.append(["eval bust", pct(ev["bust_p"])])
    P.append(["funded payout", pct(fu["payout_p"])])
    P.append(["median days to payout", str(md(fu.get("days")))])
    P.append(["funded bust", pct(fu["bust_p"])])
    if "max_payout_p" in fu:
        P.append(["max payout reached", pct(fu["max_payout_p"])])
    art["prop_table"] = P
    art.pop("prop_note", None)

    art["table"] = T
    art["table_note"] = "every number computed from this export's trade list"
    path.write_text(json.dumps(art) + "\n")
    print(f"{path.name}: {len(T)} metrics, {len(MC)} MC rows, {len(P)} prop rows")
    for sec, l, m, b in MC:
        print(f"  MC {sec:9} {l:30} {m:>14}  {b}")


if __name__ == "__main__":
    build(HERE / sys.argv[1])
