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


def build(path: Path) -> None:
    art = json.loads(path.read_text())
    pts = art["points"]
    dates = [p[0] for p in pts]
    cum = [p[1] for p in pts]
    pnl = [cum[0]] + [round(cum[i] - cum[i - 1], 2) for i in range(1, len(cum))]
    n = len(pnl)

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
    sharpe = davg / dstd * math.sqrt(252) if dstd else 0.0
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

    # streaks
    mx_w = mx_l = cw = cl = 0
    for p in pnl:
        if p > 0:
            cw, cl = cw + 1, 0
        elif p < 0:
            cl, cw = cl + 1, 0
        mx_w, mx_l = max(mx_w, cw), max(mx_l, cl)

    # monthly stability — the house wr_stability phi (chi2/df vs one coin)
    months: dict[str, list[float]] = {}
    for d, p in zip(dates, pnl):
        months.setdefault(d[:7], []).append(p)
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
    add("Risk", "Sharpe (daily, ann.)", f"{sharpe:.2f}")
    add("Streaks", "max win streak", str(mx_w))
    add("Streaks", "max loss streak", str(mx_l))
    add("Stability", "WR stability φ", f"{phi:.2f} ({verdict})")
    add("Stability", "green months",
        f"{green_m}/{len(msum)} ({pct(green_m / len(msum))})")
    add("Stability", "best month", f"{best_m} {money(msum[best_m])}")
    add("Stability", "worst month", f"{worst_m} {money(msum[worst_m])}")
    mwr = {m: sum(1 for p in v if p > 0) / len(v) for m, v in mrows.items()}
    if mwr:
        bw, ww = max(mwr, key=mwr.get), min(mwr, key=mwr.get)
        add("Stability", "best month WR",
            f"{bw} {pct(mwr[bw])} ({len(mrows[bw])} trades)")
        add("Stability", "worst month WR",
            f"{ww} {pct(mwr[ww])} ({len(mrows[ww])} trades)")

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
    add("Prop sim", "ruleset", rules_name + " · i.i.d. weekday bootstrap · 20k paths")
    add("Prop sim", "eval pass", pct(ev["p"]))
    add("Prop sim", "median days to pass", str(md(ev.get("days"))))
    add("Prop sim", "eval bust", pct(ev["bust_p"]))
    add("Prop sim", "funded payout", pct(fu["payout_p"]))
    add("Prop sim", "median days to payout", str(md(fu.get("days"))))
    add("Prop sim", "funded bust", pct(fu["bust_p"]))
    if "max_payout_p" in fu:
        add("Prop sim", "max payout reached", pct(fu["max_payout_p"]))

    art["table"] = T
    art["table_note"] = ("every number computed from this export's trade list; "
                        "prop sim = the house engine on the same ledger")
    path.write_text(json.dumps(art) + "\n")
    print(f"{path.name}: {len(T)} metrics written")
    for s, l, v in T:
        print(f"  {s:10} {l:24} {v}")


if __name__ == "__main__":
    build(HERE / sys.argv[1])
