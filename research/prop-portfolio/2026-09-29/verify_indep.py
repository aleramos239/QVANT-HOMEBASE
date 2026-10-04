#!/usr/bin/python3
"""Adversarial verification of the Stage B portfolios: an INDEPENDENT merged-trade walk + eval race.

Shares with portfolio.py / evalcore.py ONLY: E.load (trade loader), E.tape_sessions (calendar manifest) and the rule JSON
(PKG.load_rules). The day walk, the take / stop / lock rules, the three breach models, the target_take / target_stop pass
logic and the rolling-start race are re-implemented here from the docstring of evalcore.py (scalar python, event style),
so any coding slip in evalcore/portfolio shows up as a mismatch.

Usage (library): import verify_indep as V ; V.run_spec(spec) -> dict(model -> (outcome[S], day[S])) etc.
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

R = Path(__file__).resolve().parent
sys.path.insert(0, str(R))
sys.path.insert(0, str(R.parents[2]))
import evalcore as E            # noqa: E402  (loader + calendar manifest only)
from homebase.backtest import propsim as PKG   # noqa: E402

ET = ZoneInfo("America/New_York")
TICK = E.PL.TICK_USD             # 1 tick on ONE micro: NQ $0.50, ES $1.25 (pilot-aware; NQ unchanged)
SESS_MIN = {"asia": (0, 180), "london": (180, 505), "nyam": (570, 660), "mid": (660, 810), "pm": (810, 958)}   # SPEC.md table
MODELS = ("eod", "realized", "intraday")
H = 5


def cost(n: int) -> float:
    return (n // 10) * 4.0 + (n % 10) * 1.0


def sess_of(ms: int) -> str | None:
    a = dt.datetime.fromtimestamp(ms / 1000, ET)
    m = a.hour * 60 + a.minute
    for k, (lo, hi) in SESS_MIN.items():
        if lo <= m < hi:
            return k
    return None


# ------------------------------------------------------------------ trades
_T: dict = {}


def member_trades(src, sess: str):
    """List of (date_ord, te, tx, side, g, mae, mfe) of one (source, session); session assigned HERE from entry time."""
    k = (str(src), sess)
    if k not in _T:
        t = E.load(src)
        out = []
        for i in range(t.n):
            s = sess_of(int(t.te[i]))
            if sess == "all" or s == sess:
                out.append((int(t.date[i]), int(t.te[i]), int(t.tx[i]), int(t.side[i]), float(t.g[i]), float(t.mae[i]), float(t.mfe[i])))
        _T[k] = out
    return _T[k]


def calendar(extra_dates=()) -> list:
    cal = {dt.date.fromisoformat(d).toordinal() for d in E.tape_sessions("2021-01-01", "2024-12-31")}
    return sorted(cal | {int(x) for x in extra_dates})


# ------------------------------------------------------------------ the day walk (independent)

class Day:
    __slots__ = ("tot", "worst", "wreal", "traded", "execd", "ck", "stat")


def walk_day(trs, cap, mt, ds, dl, tk, tt, record=False, take_buf=0.0):
    """trs = [(te, tx, side, g, mae, mfe, n, member)] sorted by (te, member). Rules: mt max entries, ds day stop (rule-file DLL folded in by the
    caller), dl day lock (stop for the day once a CLOSED balance >= dl), tk day_take X, tt target_take level L (0 = off).
    take_buf = extra ticks per contract the MFE must exceed the take trigger by (sensitivity; 0 = the evalcore convention)."""
    realised, nent, stopped, rmin = 0.0, 0, False, 0.0
    open_ = []                                # (tx, p, w, side, n)
    ep, ee, execd = [], [], []
    ck = []                                   # checkpoints for target_stop: (realised, entries so far, lowest realised so far)
    st = dict(overlap=0, conflicts=0, max_conc=0, cap_viol=0, skipped=0, clipped=0)

    def settle(t):
        nonlocal realised, stopped, rmin, open_
        due = sorted(o for o in open_ if o[0] <= t)
        if due:
            open_ = [o for o in open_ if o[0] > t]
            for o in due:
                realised += o[1]
                if dl and realised >= dl:
                    stopped = True
                rmin = min(rmin, realised)
                if record:
                    ck.append((realised, nent, rmin))

    for (te, tx, sd, g, mae, mfe, m, mem) in trs:
        settle(te)
        if stopped or (mt and nent >= mt):
            st["skipped"] += 1
            continue
        n = m
        if n > cap:
            n, st["clipped"] = cap, st["clipped"] + 1
        c = cost(n)
        p = n * g / 10.0 - c
        w = min(p, -mae * n / 10.0 - c)
        ow = sum(o[2] for o in open_)
        op = sum(o[1] for o in open_)
        conc = n + sum(o[4] for o in open_)
        opp = any(o[3] != sd for o in open_)
        flat = False
        e = realised + ow + w
        if ds and e <= -ds:
            p = -ds - (realised + op) - TICK * n
            w, stopped, flat = p, True, True
            e = realised + ow + w
        elif tk or tt:
            lv = []
            if tk:
                lv.append((tk, tk - TICK * n))
            if tt:
                lv.append((tt + TICK * n, tt))
            trig, fin = min(lv)
            best = max(n * mfe / 10.0 - c, p)
            if realised + op + best >= trig + take_buf * TICK * n:
                p = fin - (realised + op)
                w, stopped, flat = min(w, p), True, True
                e = realised + ow + w
        if open_:
            st["overlap"] += 1
        st["conflicts"] += int(opp)
        st["max_conc"] = max(st["max_conc"], conc)
        st["cap_viol"] += int(conc > cap)
        nent += 1
        ep.append(p)
        ee.append(e)
        execd.append((te, tx, sd, n, p, mem))
        if flat:
            realised += op + p
            rmin = min(rmin, realised)
            open_ = []
            if record:
                ck.append((realised, nent, rmin))
        else:
            open_.append((tx, p, w, sd, n))
    settle(float("inf"))
    d = Day()
    d.stat, d.execd = st, execd
    if not ep:
        d.tot = d.worst = d.wreal = 0.0
        d.traded, d.ck = False, []
        return d
    tot = sum(ep)
    d.tot, d.traded = tot, True
    d.worst = min(min(ee), tot)
    d.wreal = min(rmin, tot)
    d.ck = []
    if record:
        cum, pm, run = [], [], 0.0
        lo = float("inf")
        for a, b in zip(ep, ee):
            run += a
            lo = min(lo, b)
            cum.append(run)
            pm.append(lo)
        for (cr, k, rm) in ck:
            ct = cum[k - 1]
            cw = min(pm[k - 1], ct)
            cwr = min(max(rm, cw), ct)
            d.ck.append((cr, ct, cw, cwr))
    return d


# ------------------------------------------------------------------ spec -> daily series

class Spec:
    """members = [(src, sess, micros)], rules dict (day_lock, day_take, day_stop, max_day_tr, target_take), firm short name or rule id."""

    def __init__(self, firm: str, members: list, rules: dict, cal: list | None = None, take_buf: float = 0.0):
        self.firm = firm
        self.rid, self.r = E.firm_rules(firm)
        self.members, self.rules = members, rules
        self.take_buf = take_buf
        trs = []
        for mi, (src, sess, n) in enumerate(members):
            for (d, te, tx, sd, g, mae, mfe) in (src if isinstance(src, list) else member_trades(src, sess)):
                trs.append((d, te, mi, tx, sd, g, mae, mfe, n))
        self.cal = list(cal) if cal is not None else calendar({t[0] for t in trs})
        miss = {t[0] for t in trs} - set(self.cal)
        assert not miss, f"trade dates off the calendar: {sorted(miss)[:3]}"
        pos = {o: i for i, o in enumerate(self.cal)}
        self.days = [[] for _ in self.cal]
        for (d, te, mi, tx, sd, g, mae, mfe, n) in sorted(trs, key=lambda t: (t[0], t[1], t[2])):
            self.days[pos[d]].append((te, tx, sd, g, mae, mfe, n, mi))
        self.D = len(self.cal)
        self.S = self.D - H + 1
        dll = self.r.get("daily_loss_limit") or 0.0
        self.dll = float(dll)
        self.cap = int(self.r["cap_micros"])
        ds = float(rules.get("day_stop") or 0.0)
        self.ds = min(ds, self.dll) if (ds and self.dll) else (ds or self.dll)
        self.dl = float(rules.get("day_lock") or 0.0)
        self.tk = float(rules.get("day_take") or 0.0)
        self.mt = int(rules.get("max_day_tr") or 0)
        self.ttake = bool(rules.get("target_take"))
        self._base, self._tt = {}, {}

    def day(self, i):
        if i not in self._base:
            self._base[i] = walk_day(self.days[i], self.cap, self.mt, self.ds, self.dl, self.tk, 0.0, record=True, take_buf=self.take_buf)
        return self._base[i]

    def day_tt(self, i, L):
        k = (i, round(L, 6))
        if k not in self._tt:
            self._tt[k] = walk_day(self.days[i], self.cap, self.mt, self.ds, self.dl, self.tk, L, take_buf=self.take_buf)
        return self._tt[k]

    # -- the eval race for one start, one breach model
    def race(self, s: int, model: str):
        r = self.r
        tgt, mind, cons = r["eval_target"], r["eval_min_days"], r.get("consistency")
        mll, lock_at, lock_floor = r["trailing_mll"], r["lock_at"], r["lock_floor"]
        profit = peak = largest = 0.0
        floor, td = -float(mll), 0
        self.used = []
        for k in range(H):
            i = s + k
            d = self.day(i)
            pnl, wst, wrl, tr = d.tot, d.worst, d.wreal, d.traded
            if tr and self.ttake:                                          # target_take: flatten at the level that passes today
                L = tgt - profit
                if cons is not None:
                    L = max(L, largest / cons - profit)
                    if not (L <= (cons * profit / (1 - cons) if cons < 1 else float("inf")) + 1e-9):
                        L = float("nan")
                if td + 1 < mind:
                    L = float("nan")
                if L == L and L > 0:
                    x = self.day_tt(i, L)
                    pnl, wst, wrl, tr = x.tot, x.worst, x.wreal, x.traded
            elif tr:                                                       # target_stop (always on in the search): truncate at the first
                for (cr, ct, cw, cwr) in d.ck:                             # checkpoint where the realised balance passes the eval
                    if profit + cr >= tgt and td + 1 >= mind and (cons is None or max(largest, cr) <= cons * (profit + cr)):
                        pnl, wst, wrl = ct, cw, cwr
                        break
            if self.dll:
                pnl = max(pnl, -self.dll)
            self.used.append((pnl, tr))
            new = profit + pnl
            bust = new <= floor
            if model == "intraday":
                bust = bust or profit + wst <= floor
            elif model == "realized":
                bust = bust or profit + wrl <= floor
            if bust:
                return 2, k + 1
            profit = new
            td += int(tr)
            largest = max(largest, pnl)
            if new > peak:
                peak = new
            floor = lock_floor if peak >= lock_at else peak - mll
            if new >= tgt and td >= mind and (cons is None or largest <= cons * new):
                return 1, k + 1
        return 0, 0

    def arrays(self, models=MODELS):
        out = {}
        for m in models:
            o, dd = np.zeros(self.S, np.int8), np.zeros(self.S, np.int16)
            for s in range(self.S):
                o[s], dd[s] = self.race(s, m)
            out[m] = (o, dd)
        return out


def pk(o, d, k):
    return float(((o == 1) & (d <= k)).mean())


def metrics(o, d):
    return {"p1": pk(o, d, 1), "p2": pk(o, d, 2), "p3": pk(o, d, 3), "p5": pk(o, d, 5), "bust5": float((o == 2).mean())}


def raw_overlap(sp: Spec):
    """Raw (before day rules) concurrency of the merged trades: max concurrent micros, opposite-side overlaps, cap violations."""
    mc = opp = cv = ov = 0
    for trs in sp.days:
        op = []
        for (te, tx, sd, g, mae, mfe, n, mi) in trs:
            op = [o for o in op if o[0] > te]
            if op:
                ov += 1
                opp += any(o[1] != sd for o in op)
            conc = n + sum(o[2] for o in op)
            mc = max(mc, conc)
            cv += conc > sp.cap
            op.append((tx, sd, n))
    return {"max_concurrent_micros": mc, "opposite_overlaps": int(opp), "cap_violations": int(cv), "overlap_entries": int(ov), "cap": sp.cap}


def member_nets(sp: Spec):
    """Raw sized net P&L of each member (no day rules), and standalone-under-rules net."""
    raw = []
    for (src, sess, n) in sp.members:
        raw.append(sum(n * t[4] / 10.0 - cost(n) for t in member_trades(src, sess)))
    return raw
