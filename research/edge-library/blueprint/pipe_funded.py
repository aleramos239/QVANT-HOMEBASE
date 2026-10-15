"""pipe_funded.py -- THE FUNDED PIPELINE's line (the owner, 2026-10-15: "the unseen data metrics must fall into at least one of" the rows of
docs/superpowers/findings/2026-10-15-75pct-payout-20-weekdays-win-rate-by-rr.txt: the lowest win rate that still gives a 75 % chance of the
MAXIMUM payout within 20 weekdays on a funded LucidFlex 50K, at each reward-to-risk and number of trades a day). PURE FUNCTIONS on a box's
trades (judge.cellx's arrays: `net` one contract after costs, `risk` the stop distance in points, `date` ordinals): no store, no engine.

  r_of(x, root) -> R per trade        net / (risk x the full contract's point value): the trade in units of what it risked. A trade
                                      without a stop (risk NaN or 0) has no R and is left out (counted in stats' `no_stop`)
  stats(x, root, calendar=None)       {trades, no_stop, win, rr, edge, avg_r, days, trades_day, sharpe_day, worst_day_r, losing_days}
                                        win  = the share of trades with R above 0 (a win is a net above $0 after costs, as P3.11 reads it)
                                        rr   = the average win over the average loss, both in R (None: no win or no loss)
                                        edge = win x rr - (1 - win): the average trade in units of the average loss (what the table's
                                               "Edge/trade" is: the finding's losses were 1 R each)
                                        days = the session days of `calendar` (none given: the days with a trade); a day without a trade
                                               counts $0, so trades_day and the daily numbers are over EVERY session day
  fits(s, rows, group=False) -> row | None    THE ROW THE NUMBERS FALL INTO: one with rr <= the box's rr AND win <= the box's win (a
                                      higher reward or a higher win rate only helps); `group` also asks trades_day <= the group's (the
                                      table's trades a day are the WHOLE portfolio's, so one strategy is never held to them). Of the
                                      rows that fit, the one with the highest rr, then the most trades a day. None: no row
  near(s, rows) -> row | None         when none fits: the row of the highest rr at or under the box's rr (what it would need)
  row(line, x, root, calendar=None, group=False) -> lines._row   the gate row: passed = a row fits AND the box has funded.min_trades
                                      trades with a stop (fewer: passed False, "too few trades to say"). The row carries `stats`, `fits`
  group(members, calendar) -> (x, r, per)    several members as one trade list (each trade's R at its own market's point value) and
                                      each member's R a day, for the group's row and its correlation
  correlation(series) -> float | None the highest correlation of daily P&L between any two members (series: equal-length day arrays)

EVERY NUMBER IS READ: the rows, min_trades and the labels come from the profile's rules file (pipe_rules.need("funded"));
the point values from l2sim.SPECS. Locked by tests/test_pipe_funded.py.
"""
from __future__ import annotations

import numpy as np

from . import lines as L
from . import pipe_rules as PR

EPS = 1e-9                                          # a share read as equal to the table's (0.575 is 0.575)


def _pv(root: str) -> float:
    import l2sim
    return float(l2sim.SPECS[root][0])


def r_of(x: dict, root: str) -> np.ndarray:
    """R per trade (NaN for a trade without a stop): net / (stop points x the full contract's point value)."""
    risk, net = np.asarray(x["risk"], np.float64), np.asarray(x["net"], np.float64)
    ok = np.isfinite(risk) & (risk > 0)
    out = np.full(len(net), np.nan)
    out[ok] = net[ok] / (risk[ok] * _pv(root))
    return out


def stats(x: dict, root: str, calendar=None, r=None) -> dict:
    """The box's numbers in R (module docstring). `r` = R per trade already read (a group of several markets: each member's own point value)."""
    r = r_of(x, root) if r is None else np.asarray(r, np.float64)
    ok = np.isfinite(r)
    rv, dates = r[ok], np.asarray(x["date"], np.int64)[ok]
    n = int(len(rv))
    days = sorted({*(_ords(calendar) if calendar is not None else []), *dates.tolist()})
    out = {"trades": n, "no_stop": int((~ok).sum()), "days": len(days), "win": None, "rr": None, "edge": None, "avg_r": None, "trades_day": None,
           "sharpe_day": None, "worst_day_r": None, "losing_days": None}
    if not n:
        return out
    w, lo = rv[rv > 0], rv[rv <= 0]
    win = round(float(len(w) / n), 9)
    rr = round(float(w.mean() / -lo.mean()), 9) if len(w) and len(lo) and lo.mean() < 0 else None
    at = {d: i for i, d in enumerate(days)}
    day = np.bincount([at[d] for d in dates.tolist()], weights=rv, minlength=len(days))
    sd = float(day.std())
    return {**out, "win": win, "rr": rr, "edge": None if rr is None else round(win * rr - (1 - win), 9), "avg_r": float(rv.mean()),
            "trades_day": n / len(days), "sharpe_day": float(day.mean()) / sd if sd > 0 else None, "worst_day_r": float(day.min()),
            "losing_days": float((day < 0).mean())}


def _ords(calendar) -> list:
    import library as LB
    return [int(v) for v in LB._ordinals(list(calendar)).tolist()] if len(calendar) else []


def _rows() -> list:
    return sorted(PR.need("funded", "rows"), key=lambda r: (-r["rr"], -r["trades_day"], r["win"]))


def fits(s: dict, rows=None, group: bool = False):
    """The row the numbers fall into, or None (module docstring)."""
    if s.get("win") is None:
        return None
    rr = float("inf") if s.get("rr") is None and s["win"] >= 1 else s.get("rr")      # every trade a winner: no loss to divide by, any reward fits
    if rr is None:
        return None
    for r in (rows if rows is not None else _rows()):
        if r["rr"] <= rr + EPS and r["win"] <= s["win"] + EPS and (not group or r["trades_day"] <= (s.get("trades_day") or 0) + EPS):
            return dict(r)
    return None


def near(s: dict, rows=None):
    """The row of the highest rr at or under the box's own (what it would need), or None (a reward under every row's)."""
    rr = s.get("rr")
    if rr is None:
        return None
    under = [r for r in (rows if rows is not None else _rows()) if r["rr"] <= rr + EPS]
    return dict(min(under, key=lambda r: (-r["rr"], r["win"]))) if under else None


def _said_row(r: dict) -> str:
    return f"1 : {r['rr']:g} at {r['trades_day']:g} trades a day needs {L._pc(r['win'])} wins"


def row(line: str, x: dict, root: str, calendar=None, group: bool = False, r=None) -> dict:
    """THE GATE ROW (module docstring): `line` (P3.14 on the build days, P6.2 on the unseen days, PF.1 for a group; `r` as stats reads it)."""
    s, least = stats(x, root, calendar, r), PR.need("funded", "min_trades")
    got = fits(s) if not group else fits(s, group=True)
    num = (f"win {L._pc(s['win'])} at 1 : {s['rr']:.2f} (edge {s['edge']:+.2f} R a trade), {s['trades']} trades, {s['trades_day']:.2f} a day"
           if s["win"] is not None and s["rr"] is not None else f"{s['trades']} trades" + (f", win {L._pc(s['win'])}" if s["win"] is not None else ""))
    if s["trades"] < least:
        return L._row(line, False, s["trades"], least, f"{num}: too few trades with a stop to say (need {least} or more)", stats=s, fits=None)
    if got:
        return L._row(line, True, s["win"], got["win"], f"{num}: falls into the row {_said_row(got)}", stats=s, fits=got)
    n = near(s)
    why = (f"the nearest row, {_said_row(n)}" + (f" and the group trades {s['trades_day']:.2f} a day" if group else "")) if n else \
        "its reward is under every row's (the lowest is 1 : 0.5)"
    return L._row(line, False, s["win"], None if n is None else n["win"], f"{num}: falls into no row ({why})", stats=s, fits=None)


def group(members: list, calendar) -> tuple:
    """SEVERAL MEMBERS AS ONE TRADE LIST: members = [(x, root)] -> (x with every trade, R per trade (each at its own point value), [each member's
    R a day on `calendar`]). The days of `calendar` only."""
    days = _ords(calendar)
    at, keep = {d: i for i, d in enumerate(days)}, set(days)
    xs, rs, per = [], [], []
    for x, root in members:
        d = np.asarray(x["date"], np.int64)
        m = np.array([int(v) in keep for v in d.tolist()], bool) if len(d) else np.zeros(0, bool)
        r = r_of(x, root)[m]
        xs.append({k: np.asarray(x[k])[m] for k in ("net", "risk", "date")})
        rs.append(r)
        ok = np.isfinite(r)
        per.append(np.bincount([at[int(v)] for v in d[m][ok].tolist()], weights=r[ok], minlength=len(days)))
    x = {k: np.concatenate([v[k] for v in xs]) if xs else np.zeros(0) for k in ("net", "risk", "date")}
    return x, (np.concatenate(rs) if rs else np.zeros(0)), per


def correlation(series: list):
    """The highest correlation of daily P&L between two members (None: fewer than two, or a member that never moves)."""
    best = None
    for i in range(len(series)):
        for j in range(i + 1, len(series)):
            a, b = np.asarray(series[i], np.float64), np.asarray(series[j], np.float64)
            if a.std() > 0 and b.std() > 0:
                c = float(np.corrcoef(a, b)[0, 1])
                best = c if best is None else max(best, c)
    return best
