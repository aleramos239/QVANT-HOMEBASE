#!/usr/bin/python3
"""Adversarial verification of funded.py: an INDEPENDENT lifecycle reference (written from FUNDED_RULES.md in ABSOLUTE balance
terms, $50,000 start, not funded.py's profit space) and an independent scalar day walk (event-timeline style, written from
the evalcore docstring + the Apex MAE-cut spec). Shares with funded.py ONLY: E.load / E.tape_sessions (trade loader, calendar manifest),
evalcore.firm_rules (rule JSON) and the candidate-source resolver (funded_search.load_cands / A3 sources) used to find a trade file.

Library use: ref_life(kind, src, s, H, T, model, **opt) -> (bust_day, [(day, gross, net)]) ; RefWalk(trades, ...) -> .get(i, cap, dll, lim)
CLI (real configs):  PYTHONPATH=~/ramos-quant-homebase /usr/bin/python3 verify_funded_indep.py [--firm flex ...] [--n 3]
"""
from __future__ import annotations

import datetime as dt
import math
import sys
from pathlib import Path

import numpy as np

R = Path(__file__).resolve().parent
sys.path.insert(0, str(R))

START = 50000.0


# ------------------------------------------------------------------ lifecycle reference (absolute balances)

def ref_life(kind, src, s, H, T, model, dll=0.0, apex_sticky=True, apex_cons_base="balance", apex_days="traded", pro_sticky=False):
    """kind 'flex'|'pro'|'apex'. src.get(i, cap, dll, lim) -> dict(tot, worst, wreal, n, pts) (pts = equity points relative to day start,
    in time order, used for Apex). model: lucid 'eod'|'realized'|'intraday', apex 'pess'|'opt'|'nat' (src chooses points by model via
    src.get(..., order=)). Returns (bust_day or 0, [(day, gross, net)], cuts)."""
    bal, hi_close = START, START
    pays, bust, cuts = [], 0, 0
    if kind in ("flex", "pro"):
        floor, locked = START - 2000.0, False
        wins, cyc_net, cyc_max, cyc_start = 0, 0.0, 0.0, START
        dll_on = dll > 0
        for k in range(H):
            prof = bal - START
            if kind == "flex":
                cap = 20 if prof < 1000 else (30 if prof < 2000 else 40)
            else:
                cap = 40
            if kind == "pro" and dll > 0 and not pro_sticky:
                dll_on = bal < START + 2100.0                  # literal reading: the DLL applies while balance < 52,100
            d = src.get(s + k, cap, dll if dll_on else 0.0, 0.0)
            pnl = d["tot"]
            if dll_on and pnl < -dll:
                pnl = -dll
            new = bal + pnl
            lows = [new]
            if model == "realized":
                lows.append(bal + d["wreal"])
            elif model == "intraday":
                lows.append(bal + d["worst"])
            if min(lows) <= floor:
                bust = k + 1
                break
            bal = new
            hi_close = max(hi_close, bal)
            if not locked:
                floor = hi_close - 2000.0
                if hi_close >= START + 2100.0:
                    floor, locked = START + 100.0, True
            if kind == "pro" and dll_on and pro_sticky and bal - START > 2100.0:
                dll_on = False                                # as funded.py (sticky); the literal reading is a separate probe
            if T is None:
                continue
            if kind == "flex":
                wins += pnl >= 150.0
                cyc_net += pnl
                if wins >= 5 and cyc_net > 0:
                    amt = min(0.5 * (bal - START), 2000.0)
                    need = 2000.0 if T == "max" else float(T)
                    if amt >= 500.0 and amt >= need - 1e-9:
                        pays.append((k + 1, amt, amt * 0.9))
                        bal -= amt
                        floor, locked = START + 100.0, True
                        wins, cyc_net = 0, 0.0
                        if len(pays) == 5:
                            break
            else:
                cyc_max = max(cyc_max, pnl)
                cprof = bal - cyc_start
                if cprof >= 500.0 and cyc_max <= 0.4 * cprof + 1e-9:
                    capn = 2000.0 if not pays else 2500.0
                    amt = min(capn, bal - (START + 2100.0))
                    need = capn if T == "max" else float(T)
                    if amt >= 500.0 and amt >= need - 1e-9:
                        pays.append((k + 1, amt, amt * 0.9))
                        bal -= amt
                        cyc_start, cyc_max = bal, 0.0
        return bust, pays, 0, 0
    # ---- apex
    full, peak = False, START                                      # peak = highest equity (incl. open P&L)
    days, wins50, cyc_max, cyc_start, paid = 0, 0, 0.0, START, 0.0
    ex = 0
    for k in range(H):
        prof = bal - START
        cap = 100 if full else 50
        pct = 0.5 if prof >= 5200.0 else 0.3
        lim = max(pct * prof, 750.0)
        d = src.get(s + k, cap, 0.0, lim, order=model)
        dead = False
        for kind, v in d["pts"]:
            x = bal + v
            if kind:                                       # a best point: moves the peak, cannot breach
                peak = max(peak, x)
                continue
            fl = START + 100.0 if peak >= START + 2600.0 else peak - 2500.0
            if x <= fl:                                    # a worst point: tested against the floor set by the peak so far
                dead = True
                break
        if dead:
            bust = k + 1
            break
        pnl = d["tot"]
        bal += pnl
        cuts += d["cut"]
        ex += d["n"]
        if bal - START > 2600.0:
            full = True
        elif not apex_sticky:
            full = False
        if apex_days == "all" or d["n"] > 0:
            days += 1
        wins50 += pnl >= 50.0
        cyc_max = max(cyc_max, pnl)
        if T is None or days < 8 or wins50 < 5:
            continue
        idx = len(pays) + 1
        tot_profit = bal - START
        base = tot_profit if apex_cons_base == "balance" else bal - cyc_start
        if idx <= 5 and cyc_max > 0.3 * base + 1e-9:
            continue
        post_min = START + (2100.0 if idx <= 3 else 200.0)
        amt = bal - post_min
        if idx <= 5:
            amt = min(amt, 2000.0)
        need = 2000.0 if T == "max" else float(T)
        if amt >= 500.0 and amt >= need - 1e-9:
            part = min(amt, max(0.0, 25000.0 - paid))
            pays.append((k + 1, amt, part + (amt - part) * 0.9))
            paid += amt
            bal -= amt
            days = wins50 = 0
            cyc_max, cyc_start = 0.0, bal
    return bust, pays, cuts, ex


# ------------------------------------------------------------------ independent day walk (timeline style)

def cost(n):
    return (n // 10) * 4.0 + (n % 10) * 1.0


class RefWalk:
    """Per-session independent walk of one trade set.
    trades[i] = list of dicts (te, tx, side, g, mae, mfe, m) per 1 NQ/ES (g = gross $ per full contract, mae/mfe >= 0 $ per full contract).
    get(i, cap, dll, lim, order) -> dict(tot, worst, wreal, n, pts, cut). Rules: micros (fixed size), max_day_tr, day_stop, day_lock,
    day_take, after_loss/after_win not supported (not searched). tick = $ per tick on ONE micro."""

    def __init__(self, trades, micros, rules, tick):
        self.tr, self.micros, self.tick = trades, micros, tick
        rules = rules or {}
        self.mt = int(rules.get("max_day_tr") or 0)
        self.ds = float(rules.get("day_stop") or 0.0)
        self.dl = float(rules.get("day_lock") or 0.0)
        self.tk = float(rules.get("day_take") or 0.0)
        self.n_days = len(trades)
        self._m = {}

    def get(self, i, cap, dll=0.0, lim=0.0, order="pess"):
        k = (i, cap, dll, lim, order)
        if k not in self._m:
            self._m[k] = self._walk(i, cap, dll, lim, order)
        return self._m[k]

    def _walk(self, i, cap, dll, lim, order):
        tick = self.tick
        ds = self.ds
        if dll and (not ds or dll < ds):
            ds = dll
        realised, stopped, nent, rmin, cuts = 0.0, False, 0, 0.0, 0
        open_ = []                     # dict(tx, p, w, best, n)
        pts = []                       # (kind, value rel. day start): kind 1 = high candidate, 0 = low
        ep, ee = [], []

        def settle(t):
            nonlocal realised, stopped, rmin
            due = sorted([o for o in open_ if o["tx"] <= t], key=lambda o: o["tx"])
            for o in due:
                open_.remove(o)
                realised += o["p"]
                if self.dl and realised >= self.dl:
                    stopped = True
                rmin = min(rmin, realised)

        for t in self.tr[i]:
            settle(t["te"])
            if stopped or (self.mt and nent >= self.mt):
                continue
            n = min(self.micros or t["m"], cap)
            c = cost(n)
            p0 = n * t["g"] / 10.0 - c
            p = p0
            w = min(p, -t["mae"] * n / 10.0 - c)
            cut = False
            if lim and n * t["mae"] / 10.0 >= lim:
                p = -lim - tick * n - c
                w, cut = p, True
                cuts += 1
            ow = sum(o["w"] for o in open_)
            op = sum(o["p"] for o in open_)
            ob = sum(o["best"] for o in open_)
            e = realised + ow + w
            flat, took, trunc = False, False, cut
            if ds and e <= -ds:
                p = -ds - (realised + op) - tick * n
                w, stopped, flat, trunc = p, True, True, True
                e = realised + ow + w
            elif self.tk and not cut:
                best = max(n * t["mfe"] / 10.0 - c, p)
                if realised + op + best >= self.tk:
                    p = self.tk - tick * n - (realised + op)
                    w, stopped, flat, took = min(w, p), True, True, True
                    e = realised + ow + w
            braw = max(n * t["mfe"] / 10.0 - c, p0)
            if took:
                pts += [(0, e), (1, realised + op + p)]
            else:
                winner = p0 > 0
                if order == "pess":
                    pts += [(1, realised + ob + braw), (0, e)]
                elif order == "opt":
                    pts += [(0, e)] + ([] if trunc else [(1, realised + op + braw)])
                else:                              # nat: winners MAE then MFE, losers / truncated MFE then MAE
                    pts += [(1, realised + op + braw), (0, e)] if (trunc or not winner) else [(0, e), (1, realised + op + braw)]
            nent += 1
            ep.append(p)
            ee.append(e)
            if flat:
                realised += op + p
                rmin = min(rmin, realised)
                open_.clear()
            else:
                open_.append(dict(tx=t["tx"], p=p, w=w, best=max(p, n * t["mfe"] / 10.0 - c), n=n))
        settle(float("inf"))
        if not ep:
            return dict(tot=0.0, worst=0.0, wreal=0.0, n=0, pts=[], cut=0)
        tot = sum(ep)
        pts += [(1, tot), (0, tot)]
        return dict(tot=tot, worst=min(min(ee), tot), wreal=min(rmin, tot), n=nent, pts=pts, cut=cuts)


class PtsAdapter:
    """RefWalk.get for ref_life (apex wants a flat list of equity points, kind-tagged: high points only move the peak, low points are
    breach-tested; as in funded.py's event semantics, a high point cannot breach and a low point cannot raise the peak)."""

    def __init__(self, w):
        self.w = w
        self.n_days = w.n_days

    def get(self, i, cap, dll=0.0, lim=0.0, order="pess"):
        d = self.w.get(i, cap, dll, lim, order)
        return d


# ------------------------------------------------------------------ real-config re-walk

def day_trades(src, sess, cal_ords):
    """Per-session trade dicts for one (source, session) on a calendar (ordinals). Session assigned HERE from the entry minute (SPEC table)."""
    import evalcore as E
    from zoneinfo import ZoneInfo
    ET = ZoneInfo("America/New_York")
    SM = {"asia": (0, 180), "london": (180, 505), "nyam": (570, 660), "mid": (660, 810), "pm": (810, 958)}
    t = E.load(src)
    pos = {o: i for i, o in enumerate(cal_ords)}
    days = [[] for _ in cal_ords]
    miss = 0
    for j in range(t.n):
        a = dt.datetime.fromtimestamp(int(t.te[j]) / 1000, ET)
        m = a.hour * 60 + a.minute
        if sess != "all" and not (SM[sess][0] <= m < SM[sess][1]):
            continue
        o = int(t.date[j])
        if o not in pos:
            miss += 1
            continue
        days[pos[o]].append(dict(te=int(t.te[j]), tx=int(t.tx[j]), side=int(t.side[j]), g=float(t.g[j]), mae=float(t.mae[j]),
                                 mfe=float(t.mfe[j]), m=10, mem=0))
    for d in days:
        d.sort(key=lambda x: x["te"])
    return days, miss


def ref_metrics(kind, W, T, model, H=60, dll=0.0, starts=None, **opt):
    class S:                                              # adapter: ref_life wants dict days with 'cut'
        n_days = W.n_days
        get = staticmethod(W.get)
    res = []
    for s in (range(W.n_days - H + 1) if starts is None else starts):
        res.append(ref_life(kind, S, s, H, T, model, dll=dll, **opt))
    N = len(res)
    first = np.array([r[1][0][0] if r[1] else 0 for r in res])
    paid = first > 0
    bust = np.array([r[0] for r in res])
    g1 = np.array([r[1][0][1] if r[1] else 0.0 for r in res])

    def net_by(k):
        return float(np.mean([sum(p[2] for p in r[1] if p[0] <= k) for r in res]))

    cuts = sum(r[2] for r in res)
    return dict(n=N, p_pay_20=float(((first > 0) & (first <= 20)).mean()), p_pay_40=float(((first > 0) & (first <= 40)).mean()),
                p_pay_60=float(paid.mean()), med_days_first=float(np.median(first[paid])) if paid.any() else None,
                e_first_gross=float(g1.mean()), e_net_40=net_by(40), e_net_60=net_by(H),
                p_bust_pre_first=float(((bust > 0) & ~paid).mean()), p_bust_any=float((bust > 0).mean()),
                e_npay_60=float(np.mean([len(r[1]) for r in res])), cuts=cuts)


def parse_cell(s):
    d = {}
    for tok in s.split():
        d[tok[0]] = tok[1:]
    pol = d["P"]
    return dict(micros=int(d["m"]), day_take=float(d["K"]), day_lock=float(d["L"]), day_stop=float(d["S"]), max_day_tr=int(d["T"]),
                policy=pol if pol == "max" else int(float(pol)))


def top_rows(df, variant, k=3, cap=2):
    rs = df[(df.stage == "full") & (df.variant == variant)].sort_values("score_e_net_40", ascending=False)
    out, cnt, seen = [], {}, set()
    for r in rs.to_dict("records"):
        g = (r["fam"], r["sess"])
        sig = (g, r["tf"], round(r["e_net_40"], 1), round(r["p_pay_20"], 4), round(r["e_net_60"], 1))
        if sig in seen or cnt.get(g, 0) >= cap:
            continue
        seen.add(sig)
        cnt[g] = cnt.get(g, 0) + 1
        out.append(r)
        if len(out) >= k:
            break
    return out


def main(argv=None):
    import argparse
    import pandas as pd
    import evalcore as E
    import funded_search as FS
    ap = argparse.ArgumentParser()
    ap.add_argument("--firm", default="flex,flex_dll,pro_dll,pro_nodll,apex")
    ap.add_argument("--n", type=int, default=3)
    ap.add_argument("--csv", default=str(E.D / "out" / "funded_candidates.csv"))
    ap.add_argument("--cands", default=None)
    a = ap.parse_args(argv)
    df = pd.read_csv(a.csv, low_memory=False)
    cands = {c["cid"]: c for c in FS.load_cands()}
    kinds = {"flex": ("flex", 0.0), "flex_dll": ("flex", 1200.0), "pro_dll": ("pro", 1200.0), "pro_nodll": ("pro", 0.0), "apex": ("apex", 0.0)}
    keys = ("p_pay_20", "p_pay_40", "p_pay_60", "med_days_first", "e_first_gross", "e_net_40", "e_net_60", "p_bust_pre_first", "e_npay_60")
    worst = 0.0
    for v in a.firm.split(","):
        kind, dll = kinds[v]
        for r in top_rows(df, v, a.n):
            c = cands[r["cid"]]
            cell = parse_cell(r["e40_stable_cell"])
            cal = sorted({dt.date.fromisoformat(d).toordinal() for d in E.tape_sessions("2021-01-01", "2024-12-31")})
            tmp, _ = day_trades(c["src"], c["sess"], cal)
            # add trade dates that are off the tape manifest (as the candidate calendar does)
            tt = E.load(c["src"])
            extra = sorted(set(int(x) for x in tt.date) - set(cal))
            if extra:
                cal = sorted(set(cal) | set(extra))
            days, miss = day_trades(c["src"], c["sess"], cal)
            W = RefWalk(days, cell["micros"], {k: cell[k] for k in ("day_take", "day_lock", "day_stop", "max_day_tr")}, E.PL.TICK_USD)
            model = "pess" if kind == "apex" else "realized"
            m = ref_metrics(kind, W, cell["policy"], model, dll=dll)
            diffs = {k: (m[k], r[k]) for k in keys}
            bad = {k: (x, y) for k, (x, y) in diffs.items()
                   if (x is None) != (y != y) or (x is not None and y == y and abs(x - y) > 1e-6 * max(1.0, abs(y)))}
            worst = max([worst] + [abs(x - y) for k, (x, y) in diffs.items() if x is not None and y == y])
            print(f"[{v}] {r['cid']} {r['e40_stable_cell']}: n={m['n']} E$40 ref={m['e_net_40']:.3f} csv={r['e_net_40']:.3f} "
                  f"P20 {m['p_pay_20']:.4f}/{r['p_pay_20']:.4f} med {m['med_days_first']}/{r['med_days_first']} cal={len(cal)} miss={miss} "
                  + ("OK" if not bad else f"MISMATCH {bad}"), flush=True)
    print("max abs diff", worst)


if __name__ == "__main__":
    main()
