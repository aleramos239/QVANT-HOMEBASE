"""pay_score.py -- THE GROUP SCORE of the payout pipeline (design step 2): what a set of strategies pays the trader a week across the
funded accounts, each account walked FROM WHERE IT STANDS TODAY, through MANY payouts, with OPEN LOSSES COUNTED.

  blocks(n, paths, horizon, block, seed) -> (paths x horizon) day numbers
        whole days of a pool of n days, drawn in RUNS of `block` consecutive days (a run wraps at the pool's end): winning and losing
        streaks stay together (Conti: "losing attempts they do tend to cluster"). ONE matrix a pool length: every account, every size
        and every set are walked on the same days, so two rows differ by what is traded and never by the draw.
  walk(net, traded, open_, up, r, start=None, rule_id="", request=None) -> {"paid", "pays", "first", "bust"}
        ONE FUNDED ACCOUNT on (paths x days) arrays in dollars: a day's P&L, whether it traded, its WORST OPEN LOSS (how far under the
        day's start the account stood at its worst point), its HIGHEST POINT above the day's start. Walked as propodds.funded_walk
        walks a day (the daily cap, THE OPEN-LOSS RULE first, the bust at or under the floor, the floor trailing the peak and
        locking) and then ON PAST THE FIRST PAYOUT:
          a payout is due on the rule file's own conditions (winning days, traded days, cycle profit, consistency, buffer, minimum),
          read on the CYCLE (since the last payout) and asked for when pay_rules score.request says ("max": when the maximum can be
          had); it is taken out of the account, the cycle starts again, and what pay_rules.after(rule_id) says about later payouts
          holds (another cap, a last payout, another buffer).
        `r` with "trail": "intraday" (Apex Legacy): the floor trails the highest LIVE balance until it locks. The stores keep a
        trade's low, not its high, so the high used is the highest point of the day's CLOSED trades (`up`): the floor trails less
        than it truly does. THE FRIENDLY READING, and every result of such an account says so (FRIENDLY).
        start = {"profit", "peak"}: the account today, in dollars over its size (default: a new account). The cycle is taken as new.
        -> paid (the trader's dollars, after the firm's share), pays (how many), first (the day of the first payout, 0 = none),
           bust (the day the account was lost, 0 = never)
  account(day, r, idx, start=None, rule_id="") -> the walk of ONE account on the drawn days `idx` of its day pool
  said(paid, w, week) -> the numbers of one account or of the group: per_week, p_paid, median / low (10 %) / high (90 %) dollars
  group(walks, week) -> the group's numbers on the SAME paths: per_week (the main score), p_paid (any payout), survivors, each account

Not here: which strategies, which size (pay_build). Nothing is run and nothing is written. numpy + the app's rule files (read).
Locked by tests/test_pay_score.py.
"""
from __future__ import annotations

from functools import lru_cache

import numpy as np

from . import pay_rules as PY
from . import propodds as PO

FRIENDLY = ("this account's floor trails the INTRADAY high and the stores keep no trade's high: the floor here trails the day's closed "
            "trades only -- the friendly reading, the true odds are lower")


@lru_cache(maxsize=8)
def blocks(n: int, paths: int, horizon: int, block: int, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    runs = -(-horizon // block)
    first = rng.integers(0, n, size=(paths, runs))
    idx = (first[:, :, None] + np.arange(block)[None, None, :]) % n
    idx = idx.reshape(paths, runs * block)[:, :horizon]
    idx.setflags(write=False)
    return idx


def _later(r: dict, ex: dict, k: np.ndarray) -> tuple:
    """(the cap, the buffer) of each path's NEXT payout, k payouts made so far."""
    cap = np.where(k == 0, float(r["payout_cap"]), float(ex.get("cap_later", r["payout_cap"])))
    if ex.get("uncapped_from"):
        cap = np.where(k + 1 >= ex["uncapped_from"], np.inf, cap)
    buf = r.get("payout_buffer")
    if buf is not None and ex.get("buffer_later_from"):
        buf = np.where(k + 1 >= ex["buffer_later_from"], float(r[ex["buffer_later"]]), float(buf))
    return cap, buf


def walk(net, traded, open_, up, r: dict, start=None, rule_id: str = "", request=None) -> dict:
    net, traded, open_, up = np.asarray(net, np.float64), np.asarray(traded, bool), np.asarray(open_, np.float64), np.asarray(up, np.float64)
    n, st, ex = len(net), start or {}, PY.after(rule_id)
    share, request = float(PY.firm_need(rule_id).get("trader_share", 1.0)), request or PY.need("score", "request")
    dll, live_trail = PO.app().engine._dll(r), r.get("trail") == "intraday"
    profit, peak = np.full(n, float(st.get("profit", 0.0))), np.full(n, float(max(st.get("peak", 0.0), st.get("profit", 0.0), 0.0)))
    floor = np.where(peak >= r["lock_at"], float(r["lock_floor"]), peak - r["trailing_mll"])
    base, big, paid = np.zeros(n), np.zeros(n), np.zeros(n)
    wins, tdays, pays, first, bust = (np.zeros(n, np.int64) for _ in range(5))
    live, win_day, cons = np.ones(n, bool), r.get("win_day"), r.get("payout_consistency")
    top = float(max(r["payout_cap"], ex.get("cap_later", 0)))                 # what "the maximum" is where a later payout has no cap
    for d in range(net.shape[1]):
        if not live.any():
            break
        p, o = (np.maximum(net[:, d], -dll) if dll else net[:, d]), open_[:, d]
        hit = live & (o > 0) & (profit - o <= floor)                     # THE OPEN-LOSS RULE
        go = live & ~hit
        if live_trail:
            high = profit + up[:, d]
            peak, floor = PO._floor(go & (high > peak), high, peak, floor, r)
        profit = np.where(go, profit + p, profit)
        big = np.where(go, np.maximum(big, p), big)
        tdays += go & traded[:, d]
        if win_day is not None:
            wins += go & (p >= win_day)
        lost = go & (profit <= floor)
        ok = go & ~lost
        peak, floor = PO._floor(ok & (profit > peak), profit, peak, floor, r)
        cap, buf = _later(r, ex, pays)
        cyc = profit - base
        due = ok & (cyc > 0) & (wins >= (r.get("payout_win_days") or 0)) & (tdays >= (r.get("payout_min_days") or 0)) & (cyc >= (r.get("payout_min_profit") or 0))
        if cons is not None:
            due &= big <= cons * cyc
        amt = np.minimum(profit - buf if buf is not None else r["payout_share"] * profit, cap)
        due &= (amt > 0) & (amt >= (r.get("payout_min") or 0))
        if request == "max":
            due &= amt >= np.where(np.isfinite(cap), cap, top)
        amt = np.where(due, amt, 0.0)
        paid += amt * share
        profit -= amt
        base, big = np.where(due, profit, base), np.where(due, 0.0, big)
        wins, tdays = np.where(due, 0, wins), np.where(due, 0, tdays)
        floor = np.where(due, np.maximum(floor, float(r["lock_floor"])), floor)
        first = np.where(due & (first == 0), d + 1, first)
        pays += due
        bust[hit | lost] = d + 1
        live = ok & (pays < ex["max_count"] if ex.get("max_count") else True)
    return {"paid": paid, "pays": pays, "first": first, "bust": bust}


def account(day: dict, r: dict, idx: np.ndarray, start=None, rule_id: str = "") -> dict:
    """ONE account on the drawn days: `day` = its day pool {"net", "traded", "open", "up"} (one entry a session day, in dollars)."""
    return walk(day["net"][idx], day["traded"][idx], day["open"][idx], day["up"][idx], r, start, rule_id)


def said(paid: np.ndarray, days: int, week: int) -> dict:
    lo, mid, hi = (float(v) for v in np.percentile(paid, (10, 50, 90)))
    return {"per_week": float(paid.mean()) * week / days, "p_paid": float((paid > 0).mean()), "median": mid, "low": lo, "high": hi}


def group(walks: list, days: int, week: int) -> dict:
    """The accounts together, on the SAME paths -> the group's numbers and each account's. walks = [(account id, walk)]."""
    total = sum(w["paid"] for _, w in walks)
    alive = sum((w["bust"] == 0).astype(np.float64) for _, w in walks)
    each = [{"id": a, **said(w["paid"], days, week), "p_bust": float((w["bust"] > 0).mean()), "payouts": float(w["pays"].mean()),
             "first_day": float(np.median(w["first"][w["first"] > 0])) if (w["first"] > 0).any() else None} for a, w in walks]
    return {**said(total, days, week), "survivors": float(alive.mean()), "accounts": each, "days": days}
