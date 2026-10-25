"""jj_fifty_accounts -- JJ Simon's step 2-3 of the $1,000 plan (video 4Zj4xKiQHQk): "back test 50 complete prop firm evaluations and
funded accounts ... 50 completely distinct attempts ... payouts minus eval fees is the only thing that matters" (the owner, 2026-10-19:
"lets follow the $1000 plan and perfectly execute it").

THE TEST. One taught cell's trades (the run store's cells.npz), resized to k micros, through one prop rule file
(homebase/backtest/propsim/rules/, e.g. lucid-flex-25k-dll@2026-10-19):
  * 50 accounts, each started on its own weekday, evenly spaced over the ledger's weekdays minus the last `runway` (so the late ones
    have room to finish); every account walks the REAL days in order (no reshuffle) -- his "50 distinct historical attempts".
  * EVAL: propsim's own run_eval (EOD trailing, lock, consistency, minimum days, open losses via the day's worst point, the soft daily
    loss limit cut at trade level by propsim.limit_trades).
  * FUNDED, from the next weekday: EVERY payout, not the first only (propsim.run_funded stops at the first): the rule file's own
    _cheque (5 days of win_day, net > 0 in the cycle, 50 % of profit, min / cap); after a payout the profit falls by the cheque, the
    cycle's win days start again, and the floor moves to lock_floor and stays (Lucid: "on a payout request the floor moves straight to
    start + $100" -- the 50K file's note). Up to `max_payouts` (5: then Lucid moves the account to live -- not valued here).
  * MONEY: payouts x split (0.9) - accounts x fee. Unpaid balances count for nothing (his rule).

RESIZING (my pick, said with every result): the ledger is 1 NQ (the engine: $4 a round turn, 1 tick of slippage in the fill prices).
k micros = k / 10 of the gross (net + $4) minus `micro_cost` x k a round turn; the adverse excursion scales by k / 10.

Run: .venv-research/bin/python research/edge-library/taught/jj_fifty_accounts.py --store ~/.homebase/taught/<name>/runs/<name>-NQ-tf1
     [--cell pts25-r1p52] [--rules lucid-flex-25k-dll@2026-10-19] [--micros 2,5,10] [--fee 50,70,100]"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import functools
import json
import sys
import zoneinfo
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
from homebase.backtest import propsim as P                    # noqa: E402
from homebase.backtest.propsim import propsim as E            # noqa: E402

NY = zoneinfo.ZoneInfo("America/New_York")


@functools.lru_cache(maxsize=1)
def _arrays(store: Path) -> dict:
    # an NpzFile re-reads the whole array from the zip on every z[k]: read once per store (per trade it was quadratic)
    z = np.load(store / "cells.npz", allow_pickle=True)
    return {k: z[k] for k in z.files}


def ledger(store: Path, cell: str) -> list[dict]:
    """The cell's trades as propsim reads them: date, net and mae_usd for 1 NQ, in the store's order."""
    z = _arrays(Path(store))
    cells = [r["cell"] for r in csv.DictReader(open(store / "table.csv")) if r["sess"] == "all"]
    i = cells.index(cell)
    a, b = int(z["off"][i]), int(z["off"][i + 1])
    out = []
    for j in range(a, b):
        t0 = dt.datetime.fromtimestamp(int(z["entry_ms"][j]) / 1000, NY)
        out.append({"date": t0.date().isoformat(), "entry_ms": int(z["entry_ms"][j]), "net": float(z["net"][j]),
                    "mae_usd": abs(float(z["mae"][j])), "side": int(z["side"][j]),
                    "risk_pts": float(z["risk"][j]) if "risk" in z else None})
    return out


def wf_ledger(name: str) -> list[dict]:
    """A taught sheet's 3:1 block walk-forward as one ledger: each test month = the trades of that month's picked exit cell (build-day
    months from the build store, months from 2025-07 from wf/test_cells.npz), 1 NQ, real dates. The months add up to the WF's own."""
    base = Path.home() / ".homebase" / "taught" / name
    res = json.load(open(base / "wf" / "result.json"))
    store = next(p for p in sorted((base / "runs").glob(f"{name}-*")) if p.is_dir() and "__ctl" not in p.name)
    tz = np.load(base / "wf" / "test_cells.npz", allow_pickle=True)
    test = {}
    out = []
    for m in res["months"]:
        if not m["cell"]:
            continue
        c = m["cell"]
        if c not in test:
            test[c] = {k: tz[f"{c}|{k}"] for k in ("date", "entry_ms", "net", "mae")} if f"{c}|date" in tz.files else None
        if test[c] is not None and m["month"] >= "2025-07":
            z = test[c]
            rows = [{"date": dt.date.fromordinal(int(z["date"][j])).isoformat(), "entry_ms": int(z["entry_ms"][j]), "net": float(z["net"][j]),
                     "mae_usd": abs(float(z["mae"][j])), "side": 0, "risk_pts": None} for j in range(len(z["date"]))]
        else:
            rows = ledger(store, c)
        got = [t for t in rows if t["date"][:7] == m["month"]]
        assert len(got) == m["trades"] and abs(sum(t["net"] for t in got) - m["net"]) < 1.0, (name, m, len(got), sum(t["net"] for t in got))
        out += got
    return sorted(out, key=lambda t: t["entry_ms"])


def back_to_back(trades: list[dict]) -> list[dict]:
    """The traded months put back to back: every weekday of a month with a trade, in order, mapped onto consecutive weekdays from the
    first, so an account trades every month instead of idling through the months the walk-forward did not trade."""
    months = sorted({t["date"][:7] for t in trades})
    wd = []
    for mo in months:
        d = dt.date.fromisoformat(mo + "-01")
        while d.strftime("%Y-%m") == mo:
            if d.weekday() < 5:
                wd.append(d)
            d += dt.timedelta(1)
    new, d = {}, wd[0]
    for old in wd:
        new[old.isoformat()] = d
        d += dt.timedelta(3 if d.weekday() == 4 else 1)
    out = []
    for t in trades:
        n = new[t["date"]]                                     # a weekend trade date would raise here: none in the day sessions
        shift = (n - dt.date.fromisoformat(t["date"])).days * 86_400_000
        out.append({**t, "date": n.isoformat(), "entry_ms": t["entry_ms"] + shift})
    return out


def set_risk(trades: list[dict], risk_usd: float, micro_cost: float, cap: int = 5, max_risk_pts: float = 0.0) -> list[dict]:
    """The reviewers' idea (2026-10-20): size each trade so that its planned stop risks `risk_usd` -- micros = risk / (stop points x $2),
    at most `cap`; a trade whose stop is wider than risk / $2 (or than max_risk_pts) is skipped. A 1-NQ ledger with a 'risk_pts' field."""
    out = []
    for t in trades:
        r = t.get("risk_pts")
        if r is None or r <= 0:
            continue
        if max_risk_pts and r > max_risk_pts:
            continue
        m = min(cap, int(risk_usd // (r * 2.0)))
        if m < 1:
            continue
        k = m / 10.0
        out.append({**t, "net": (t["net"] + 4.0) * k - micro_cost * m, "mae_usd": t["mae_usd"] * k, "micros": m})
    return out


def day_box(trades: list[dict], take: float, stop: float, r: dict) -> list[dict]:
    """The reviewers' idea 3 (2026-10-20), an account rule on SIZED trades in ledger order: no new entry once the day's closed net
    reaches `take` (one Lucid win day), and the day cut at -`stop` (propsim's own daily-loss walk at a smaller number). 0 = off."""
    if stop:
        trades = P.limit_trades(trades, {**r, "daily_loss_limit": float(stop)})
    if take:
        out, cum, day = [], 0.0, None
        for t in trades:
            if t["date"] != day:
                day, cum = t["date"], 0.0
            if cum < take:
                out.append(t)
                cum += t["net"]
        trades = out
    return trades


def resize(trades: list[dict], micros: int, micro_cost: float, halve_big: bool = False) -> list[dict]:
    """k micros of a 1-NQ ledger. halve_big = JJ's "cut my contracts in half" on a 50 / 76 trade: a trade whose 1-NQ result is bigger
    than a 25 / 38 outcome can be (|net| > $900: a 50-point stop or a 76-point target) is taken at half the micros (at least 1)."""
    out = []
    for t in trades:
        m = max(1, micros // 2) if halve_big and abs(t["net"]) > 900.0 else micros
        k = m / 10.0
        out.append({**t, "net": (t["net"] + 4.0) * k - micro_cost * m, "mae_usd": t["mae_usd"] * k})
    return out


def days(trades: list[dict], r: dict) -> list[tuple]:
    """The weekday path (pnl, traded, worst open loss) after the soft daily limit, every weekday in the span."""
    lim = P.limit_trades(trades, r)
    pnls, flags, dates = P.weekday_grid(lim)
    opens = P.day_opens(lim, dates, r) or [0.0] * len(pnls)
    return [(p, f, o) for p, f, o in zip(pnls, flags, opens)], dates


def funded(path: list[tuple], r: dict, max_payouts: int) -> dict:
    """Every payout of one funded account until it busts, reaches max_payouts or the data ends."""
    profit, peak, floor, locked = 0.0, 0.0, -r["trailing_mll"], False
    win_days, big, start, cheques, bust = 0, 0.0, 0.0, [], None
    for n, (pnl, traded, opn) in enumerate(path, 1):
        pnl = E._cap_day(pnl, r)
        if opn > 0 and profit - opn <= floor:
            bust = n
            break
        profit += pnl
        big = max(big, pnl)
        if r.get("win_day") is not None and pnl >= r["win_day"]:
            win_days += 1
        if profit <= floor:
            bust = n
            break
        if profit > peak:
            peak = profit
            if not locked:
                floor = E._floor(peak, r)
        due = E._cheque(profit, win_days, big, r) if profit - start > 0 else None
        if due is not None:
            cheques.append((n, due))
            profit -= due
            win_days, big, start = 0, 0.0, profit
            floor, locked = r["lock_floor"], True       # the floor moves to start + lock_floor on a payout request
            if len(cheques) >= max_payouts:
                break
    return {"cheques": cheques, "bust_at": bust, "days": n if path else 0}


def fullport_eval(base: list[dict], dates: list, start: int, r: dict, micro_cost: float) -> dict:
    """The owner's reading of JJ on an eval WITHOUT a consistency rule (2026-10-19): the whole max loss on one trade at 1:1.5, so the
    first decided trade IS the eval. Each 1-NQ trade is sized so that its stop = the max loss (a 25-point stop -> trailing_mll / 50
    micros; a 50-point stop, read as |net| > $900 at 1 NQ, -> half that); a target hit (1.52 x the stop >= the eval target) passes, a stop
    busts, a time exit decides nothing and the next trade is sized the same way again. -> run_eval's shape: outcome, day."""
    d0 = dates[start]
    for t in base:
        if t["date"] < d0:
            continue
        stop_pts = 50.0 if abs(t["net"]) > 900.0 else 25.0
        m = int(r["trailing_mll"] / (stop_pts * 2.0))
        net = (t["net"] + 4.0) * m / 10.0 - micro_cost * m
        day = dates.index(t["date"]) - start + 1 if t["date"] in dates else None
        if net <= -0.9 * r["trailing_mll"]:
            return {"outcome": "bust", "day": day}
        if net >= r["eval_target"]:
            return {"outcome": "pass", "day": day}
    return {"outcome": "timeout", "day": None}


def fifty(trades: list[dict], r: dict, n: int, runway: int, max_payouts: int, fullport: list | None = None, micro_cost: float = 1.0,
          funded_trades: list | None = None, r_eval: dict | None = None) -> dict:
    """50 accounts; `trades` sized for the eval, `funded_trades` (default the same) sized for the funded phase (JJ sizes the two apart);
    `r_eval` = the eval's own rules when they differ from the funded account's (the Pro eval has no daily limit)."""
    re_ = r_eval or r
    path, dates = days(trades, re_)
    fpath = days(funded_trades, r)[0] if funded_trades is not None else days(trades, r)[0]
    span = len(path) - runway
    starts = [round(i * span / n) for i in range(n)]
    rows = []
    for s in starts:
        ev = fullport_eval(fullport, dates, s, re_, micro_cost) if fullport is not None else E.run_eval(path[s:], re_)
        row = {"start": dates[s], "eval": ev["outcome"], "eval_days": ev["day"], "cheques": [], "funded_bust": None}
        if ev["outcome"] == "pass":
            f = funded(fpath[s + (ev["day"] or 0):], r, max_payouts)
            row["cheques"] = [c for _, c in f["cheques"]]
            row["funded_bust"] = f["bust_at"]
        rows.append(row)
    passed = [x for x in rows if x["eval"] == "pass"]
    paid = [x for x in passed if x["cheques"]]
    gross = sum(sum(x["cheques"]) for x in rows)
    return {"accounts": n, "passed": len(passed), "paid": len(paid), "payouts": sum(len(x["cheques"]) for x in rows),
            "gross_payouts": gross, "busted_eval": sum(1 for x in rows if x["eval"] == "bust"),
            "timeout": sum(1 for x in rows if x["eval"] == "timeout"), "rows": rows}


def kelly(rows: list[dict], fee: float, bankroll: float, split: float = 0.9, paths: int = 20000, seed: int = 7) -> dict:
    """The bankroll's Kelly fraction for 'one eval' as a bet: R = (payouts x split - fee) / fee per account (the 50 rows are the
    distribution); f* maximizes mean log(1 + f R) over f in (0, 1]; half Kelly beside it; evals at a time = f x bankroll / fee.
    Risk of ruin: the chance the bankroll falls under one fee before it doubles, buying evals one after another at that fraction
    (draws from the same 50 outcomes; the accounts are treated as independent, which they are not: a correlated run of simultaneous
    accounts is worse than this says)."""
    import math
    import random
    R = [(sum(x["cheques"]) * split - fee) / fee for x in rows]
    best, f_star = -1e9, 0.0
    for i in range(1, 1001):
        f = i / 1000.0
        if any(1 + f * x <= 0 for x in R):
            break
        g = sum(math.log(1 + f * x) for x in R) / len(R)
        if g > best:
            best, f_star = g, f
    out = {"mean_R": sum(R) / len(R), "p_payout": sum(1 for x in R if x > 0) / len(R), "f_star": f_star, "growth_per_eval": best}
    rng = random.Random(seed)
    for name, f in (("full", f_star), ("half", f_star / 2)):
        ruined = 0
        for _ in range(paths):
            b = bankroll
            while fee <= b < 2 * bankroll:
                stake = max(fee, f * b)
                b += stake * rng.choice(R)
            ruined += b < fee
        out[name] = {"f": f, "evals_at_once": max(1, int(f * bankroll / fee)), "ruin_before_double": ruined / paths}
    return out


def sweep(base: list[dict], r: dict, a, fees: list, sizes: tuple = (2, 3, 5, 7, 10, 15, 20)) -> None:
    """Eval size x funded size, 50 accounts each; the fee's net per eval and the Kelly read of the best cell."""
    print(f"\nSWEEP eval micros (rows) x funded micros (columns): net per eval at ${fees[0]:.0f}, 50 accounts, split {a.split}"
          + (" (half size on 50 / 76 trades)" if a.halve_big else "") + (" EVAL FULL-PORTED" if a.fullport_eval else ""))
    head = "eval / funded"
    print(f"{head:>13} " + " ".join(f"{m:>7}" for m in sizes) + "   pass%")
    best = None
    for e in sizes:
        ev = resize(base, e, a.micro_cost, a.halve_big)
        cells = []
        for f in sizes:
            fu = resize(base, f, a.micro_cost, a.halve_big)
            res = fifty(ev, r, a.n, a.runway, a.max_payouts, fullport=base if a.fullport_eval else None, micro_cost=a.micro_cost, funded_trades=fu,
                        r_eval=a.r_eval)
            net = (res["gross_payouts"] * a.split - fees[0] * a.n) / a.n
            cells.append((net, res))
            if best is None or net > best[0]:
                best = (net, e, f, res)
        print(f"{e:>13} " + " ".join(f"{c[0]:>7,.0f}" for c in cells) + f"   {100 * cells[0][1]['passed'] / a.n:4.0f}%")
    net, e, f, res = best
    print(f"best: eval {e} micros, funded {f} micros: {res['passed']} pass, {res['paid']} paid, {res['payouts']} payouts, net per eval ${net:,.0f}")
    k = kelly(res["rows"], fees[0], a.bankroll, a.split)
    print(f"KELLY on that cell: mean return per eval {k['mean_R']:+.2f}x the fee, payout chance {100 * k['p_payout']:.0f}%, f* = {k['f_star']:.2f} of the bankroll "
          f"(growth {k['growth_per_eval']:+.3f} log per eval)")
    for name in ("full", "half"):
        x = k[name]
        print(f"  {name:4} Kelly: {100 * x['f']:.0f}% of ${a.bankroll:,.0f} per eval = {x['evals_at_once']} eval(s) at a time; "
              f"risk of ruin before doubling {100 * x['ruin_before_double']:.1f}% (independent accounts: the real number is higher)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--store")
    ap.add_argument("--wf", help="taught sheet name(s), comma-separated: their 3:1 walk-forward trades (out of sample), months back to back")
    ap.add_argument("--cell", default="pts25-r1p52")
    ap.add_argument("--rules", default="lucid-flex-25k-dll@2026-10-19")
    ap.add_argument("--micros", default="2,5,10")
    ap.add_argument("--fee", default="50,70,100")
    ap.add_argument("--micro-cost", type=float, default=1.0)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--runway", type=int, default=120)
    ap.add_argument("--max-payouts", type=int, default=5)
    ap.add_argument("--split", type=float, default=0.9)
    ap.add_argument("--json")
    ap.add_argument("--halve-big", action="store_true", help="JJ's half size on the 50 / 76 trades (|net| > $900 at 1 NQ)")
    ap.add_argument("--fullport-eval", action="store_true", help="the eval = one trade with the whole max loss at 1:1.5 (no-consistency evals only)")
    ap.add_argument("--no-consistency", action="store_true", help="read the rule file with the eval consistency rule removed")
    ap.add_argument("--sweep", action="store_true", help="eval size x funded size table and the Kelly read of the best cell")
    ap.add_argument("--mc", action="store_true", help="the prop simulator's Monte Carlo per size instead of the 50 windows")
    ap.add_argument("--no-edge", action="store_true", help="control: every trade minus the ledger's average trade")
    ap.add_argument("--bankroll", type=float, default=1000.0)
    ap.add_argument("--together", help="EVAL,FUNDED micros: K accounts bought the same day, copy vs take turns")
    ap.add_argument("--eval-dll", help="the eval's own daily loss limit: 'none' or a $ amount (the Pro 25K eval has none)")
    ap.add_argument("--set-risk", help="size every trade to this $ risk from its planned stop (needs the store's risk points), cap 5 micros")
    ap.add_argument("--max-risk-pts", type=float, default=0.0, help="with --set-risk: skip trades whose stop is wider than this")
    ap.add_argument("--cap-micros", type=int, default=5)
    ap.add_argument("--day-take", type=float, default=0.0, help="account box: no new entry once the day's closed net reaches this ($)")
    ap.add_argument("--day-stop", type=float, default=0.0, help="account box: the day cut at -this ($, inside the daily loss limit)")
    a = ap.parse_args(argv)
    r = P.load_rules(a.rules)
    if a.no_consistency:
        r = {**r, "consistency": None}
    a.r_eval = None
    if a.eval_dll:
        a.r_eval = {**r, "daily_loss_limit": None if a.eval_dll.lower() == "none" else float(a.eval_dll)}
    if a.fullport_eval and (a.r_eval or r).get("consistency") is not None:
        raise SystemExit("--fullport-eval: this eval has a largest-day rule, one trade can never be the pass; add --no-consistency to read it as if it had none")
    # several legs on ONE account: --store a,b --cell x,y (one ledger in time order; propsim walks overlapping trades one after the other)
    if a.wf:
        base = back_to_back(sorted((t for n in a.wf.split(",") for t in wf_ledger(n)), key=lambda t: t["entry_ms"]))
    elif a.store:
        base = sorted((t for s, c in zip(a.store.split(","), a.cell.split(",")) for t in ledger(Path(s).expanduser(), c)), key=lambda t: t["entry_ms"])
    else:
        raise SystemExit("give --store (with --cell) or --wf")
    if a.no_edge:
        mu = sum(t["net"] for t in base) / len(base)
        base = [{**t, "net": t["net"] - mu} for t in base]    # the same trades, the average trade taken out: what the account's shape pays
        print(f"NO-EDGE CONTROL: ${mu:,.2f} taken off every 1-NQ trade")
    fees = [float(x) for x in a.fee.split(",")]
    print(f"{r['name']} ({a.rules}, confirmed {r.get('confirmed') is not False}){' -- EVAL FULL-PORTED, consistency rule removed' if a.fullport_eval else ''}; {len(base)} trades "
          f"{base[0]['date']} .. {base[-1]['date']}; {a.n} accounts, real days in order, runway {a.runway} weekdays")
    print(f"micros  passed  paid  payouts  payouts x {a.split}  " + "  ".join(f"net @ ${f:.0f}" for f in fees) + "   pass%  paid% of passed")
    if a.mc:
        # many random paths from the same days: steadier than 50 overlapping windows when the ledger is short (a walk-forward's months)
        print("MONTE CARLO (propsim.evaluate: 20,000 paths of weekdays drawn from this ledger; one rule file for eval and funded; FIRST cheque only)")
        print("micros   pass   bust  days to pass  payout  E[cheque]  " + "  ".join(f"net/eval @ ${f:.0f}" for f in fees))
        for m in [int(x) for x in a.micros.split(",")]:
            h = P.evaluate(day_box(resize(base, m, a.micro_cost, a.halve_big), a.day_take, a.day_stop, r), a.rules, rules=r)["headline"]
            nets = [h["eval_pass_p"] * h["funded_expected_cheque"] * a.split - f for f in fees]
            print(f"{m:>6}  {100 * h['eval_pass_p']:4.0f}%  {100 * h['bust_p']:4.0f}%  {h['median_days_to_pass'] or 0:>12}  {100 * h['funded_payout_p']:5.0f}%  "
                  f"${h['funded_expected_cheque']:>8,.0f}  " + "  ".join(f"${x:>14,.0f}" for x in nets))
        return 0
    if a.sweep:
        sweep(base, r, a, fees)
        return 0
    if a.together:
        a.together_sizes = tuple(int(x) for x in a.together.split(","))
        together_table(base, r, a, fees)
        return 0
    if a.set_risk:
        rows = {}
        for R in [float(x) for x in str(a.set_risk).split(",")]:
            tr = day_box(set_risk(base, R, a.micro_cost, a.cap_micros, a.max_risk_pts), a.day_take, a.day_stop, r)
            res = fifty(tr, r, a.n, a.runway, a.max_payouts, micro_cost=a.micro_cost, r_eval=a.r_eval)
            take = res["gross_payouts"] * a.split
            nets = [take - f * a.n for f in fees]
            kept = len(tr)
            print(f"risk ${R:>4,.0f} ({kept} of {len(base)} trades kept, cap {a.cap_micros} micros{', stops <= ' + str(a.max_risk_pts) + ' pts' if a.max_risk_pts else ''}): "
                  f"{res['passed']:>2} pass {res['paid']:>2} paid {res['payouts']:>3} payouts  ${take:>8,.0f}  " + "  ".join(f"net@{f:.0f} ${x:>7,.0f}" for f, x in zip(fees, nets)))
        return 0
    out = {}
    for m in [int(x) for x in a.micros.split(",")]:
        res = fifty(day_box(resize(base, m, a.micro_cost, a.halve_big), a.day_take, a.day_stop, r), r, a.n, a.runway, a.max_payouts,
                    fullport=base if a.fullport_eval else None, micro_cost=a.micro_cost, r_eval=a.r_eval)
        take = res["gross_payouts"] * a.split
        nets = [take - f * a.n for f in fees]
        print(f"{m:>6}  {res['passed']:>6}  {res['paid']:>4}  {res['payouts']:>7}  ${take:>15,.0f}  " +
              "  ".join(f"${x:>9,.0f}" for x in nets) +
              f"   {100 * res['passed'] / a.n:4.0f}%  {100 * res['paid'] / max(res['passed'], 1):4.0f}%")
        out[m] = res
    if a.json:
        Path(a.json).write_text(json.dumps(out, indent=1))
    return 0



# ---- bought together: copy vs take turns (the owner's rotation rule, 2026-10-19) --------------------------------------------------

def together(base: list[dict], r: dict, k: int, mode: str, eval_micros: int, funded_micros: int, fee: float, split: float, a,
             starts: int = 40) -> dict:
    """K accounts bought the SAME day. copy = every account takes every trade (one account K times bigger); turns = trade i goes to
    account i mod K (the Desk's rotation), each account then walks eval -> funded -> payouts on its own. Repeated over `starts`
    start days spread over the ledger -> the distribution of the K-account batch's net (payouts x split - K fees)."""
    dates_all = sorted({t["date"] for t in base})
    span = len(dates_all) - a.runway
    nets, ruined = [], 0
    for i in range(starts):
        d0 = dates_all[round(i * span / starts)]
        pool = [t for t in base if t["date"] >= d0]
        batch = 0.0
        for j in range(k):
            mine = pool if mode == "copy" else pool[j::k]
            ev = resize(mine, eval_micros, a.micro_cost, a.halve_big)
            fu = resize(mine, funded_micros, a.micro_cost, a.halve_big)
            path, dates = days(ev, a.r_eval or r)
            fpath = days(fu, r)[0]
            e = fullport_eval(mine, dates, 0, a.r_eval or r, a.micro_cost) if a.fullport_eval else E.run_eval(path, a.r_eval or r)
            cheques = funded(fpath[(e["day"] or 0):], r, a.max_payouts)["cheques"] if e["outcome"] == "pass" else []
            batch += sum(c for _, c in cheques) * split - fee
        nets.append(batch)
        ruined += batch <= -k * fee * 0.999
    nets.sort()
    n = len(nets)
    return {"mode": mode, "k": k, "mean": sum(nets) / n, "p10": nets[n // 10], "p50": nets[n // 2], "p90": nets[9 * n // 10],
            "all_lost": ruined / n, "share_losing": sum(1 for x in nets if x < 0) / n}


def together_table(base, r, a, fees) -> None:
    e, f = a.together_sizes
    print(f"\nBOUGHT TOGETHER: K accounts on the same day, eval {e} / funded {f} micros, fee ${fees[0]:.0f}, 40 start days"
          + (" EVAL FULL-PORTED" if a.fullport_eval else "") + ". net of the batch: mean, 10th / 50th / 90th percentile, share of batches that lose, share that lose every fee")
    print(f"{'K':>3} {'mode':>5} {'mean':>8} {'p10':>8} {'p50':>8} {'p90':>8} {'lose%':>6} {'wipe%':>6}")
    for k in (1, 2, 4, 10, 20):
        for mode in ("copy", "turns"):
            if k == 1 and mode == "turns":
                continue
            x = together(base, r, k, mode, e, f, fees[0], a.split, a)
            print(f"{k:>3} {mode:>5} {x['mean']:>8,.0f} {x['p10']:>8,.0f} {x['p50']:>8,.0f} {x['p90']:>8,.0f} {100 * x['share_losing']:>5.0f}% {100 * x['all_lost']:>5.0f}%")

if __name__ == "__main__":
    raise SystemExit(main())
