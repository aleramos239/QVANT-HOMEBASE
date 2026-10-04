"""ADVERSARIAL VERIFIER (look-ahead + fidelity) of family group new_l2 -- parts B and C.

  C  STAGE D OPTIONS (f_book / x_book / f_thin on orb, donchian, straddle, straddle_t_<HHMM>): every `allowed` verdict and
     every x_book counter step of the engine against an oracle that reads the raw feature table by ROW STAMP; every book
     exit against the tape (first print at / after the trigger + 85 ms).
  B  NO LOOK-AHEAD AT THE BOUNDARY: every print stamped >= CUT and every feature row usable AFTER CUT is replaced by
     garbage; CUT sits EXACTLY on a decision instant (a tf close / a clock fire). Every decision at now <= CUT (D1 / D5
     signals, the option verdicts, the x_book counter), every trade closed before CUT and the entry of every trade
     entered before CUT must be unchanged. A LEAK CONTROL garbles one row / one minute too early and must be caught.

10 BUILD days the author did not use, 1 worker, in-process. Identity, counts and timing only: no P&L is printed.
"""
import datetime as dt
import json
import sys
import zoneinfo
from collections import Counter
from pathlib import Path

import numpy as np

ENG = Path(__file__).resolve().parents[2]
for p in (str(ENG), str(ENG.parent)):
    if p not in sys.path:
        sys.path.insert(0, p)

import l2data as D          # noqa: E402
import l2sim as S           # noqa: E402
import families             # noqa: E402
from families import l2ideas as L2      # noqa: E402

DAYS = ["2021-11-08", "2021-11-26", "2022-03-14", "2022-03-16", "2022-08-17", "2022-11-07", "2023-01-03", "2023-03-15",
        "2023-06-20", "2023-11-24"]
ET = zoneinfo.ZoneInfo("America/New_York")
NS = S.NS
LAT = 85_000_000
COLS = ("imb10", "bid10_rel15", "ask10_rel15", "f_delta", "t_utc", "book_ok")
EXITS = ({"stop_mode": "pts", "stop_val": 10.0, "tgt_r": 1.0}, {"stop_mode": "atr", "stop_val": 3.0, "tgt_r": 0.0})
PLAN = (("donchian", "5", [{"n": 20}]), ("orb", "5", [{"or_min": "15"}]), ("straddle", "5", [{"off_atr": 0.5}]),
        ("straddle_t_0930", "30", [{"off": "atr0p5"}]), ("straddle_t_2000", "30", [{"off": "atr0p5"}]),
        ("straddle_t_0000", "30", [{"off": "ptsA"}]), ("straddle_t_0300", "30", [{"off": "atr0p25"}]),
        ("straddle_t_0830", "30", [{"off": "ptsB"}]), ("straddle_t_1800", "30", [{"off": "atr0p5"}]))
REC = []
SPIES = {}


def label(st):
    return getattr(st, "_lab", None) or (type(st).__name__ + "|" + json.dumps(st.p, sort_keys=True, default=str))


class Lab:
    def __init__(self, params=None):
        super().__init__(params)
        self._lab = type(self).__name__ + "|" + json.dumps(self.p, sort_keys=True, default=str)


class SpyOpt(Lab):
    def allowed(self, side):
        v = super().allowed(side)
        REC.append(("allow", label(self), self.day, int(self._cx.now_ns), side, bool(v)))
        return v

    def _xbook(self, ctx):
        self._sync(ctx)
        inpos = not (ctx.flat or self.fill_ns is None or ctx.now_ns <= self.fill_ns)
        before, side = self.xb, self.side
        n0 = len(ctx._s.orders)
        super()._xbook(ctx)
        fired = any(o.role == "book" for o in ctx._s.orders[n0:])
        REC.append(("xb", label(self), self.day, int(ctx.now_ns), inpos, int(side), int(before), int(self.xb), fired))


class SpySig(Lab):
    def _mkt(self, ctx, side, **kw):
        REC.append(("sig", label(self), self.day, int(ctx.now_ns), side))


def spy(cls, mix):
    key = (cls, mix)
    if key not in SPIES:
        SPIES[key] = type(("Sig" if mix is SpySig else "Opt") + cls.__name__, (mix, cls), {})
    return SPIES[key]


def specs():
    out = []
    for base, tf, variants in PLAN:
        for sfx in ("fbook", "xbook", "thin"):
            for c in L2.variant_grid(f"{base}_{sfx}", "NQ", tf, variants):
                if c["exit"] not in EXITS:
                    continue
                cls, prm = c["spec"]
                import run_menus as RM
                for k, p in RM.cell_specs({"spec": (cls, prm)}):
                    out.append((spy(k, SpyOpt), p))
    d1, d5 = L2.BimbFollowD1, L2.FlowExhaust
    for s in ("all", "pre", "eve"):
        out.append((spy(d1, SpySig), {"tf": "5", "sess": s, "k": 2.0}))
        for tf in ("1", "5"):
            out.append((spy(d5, SpySig), {"tf": tf, "sess": s, "q": 90.0}))
        for x in EXITS:                              # the real families too (orders placed): their trades around the cut
            out.append((d1, {"tf": "5", "sess": s, "k": 2.0, **x}))
            out.append((d5, {"tf": "1", "sess": s, "q": 90.0, **x}))
            out.append((d5, {"tf": "5", "sess": s, "q": 90.0, **x}))
    return out


def et_ns(d, hh, mm=0):
    return int(dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=ET).timestamp()) * NS


# ---- garbage after a cut ------------------------------------------------------------------------------------
REAL_TAPE = S.load_tape


class Garble:
    """features loader + tape patch: everything AFTER the day's cut is noise. early_rows / early_s: the LEAK CONTROL."""

    def __init__(self, inner, cuts: dict, early_rows: bool = False, early_s: int = 0):
        self.inner, self.cuts, self.early_rows, self.early_s = inner, cuts, early_rows, early_s
        self.columns = inner.columns

    def __call__(self, d):
        f = self.inner(d)
        cut = self.cuts.get(d.isoformat())
        if f is None or cut is None:
            return f
        rng = np.random.default_rng(int(cut % 2 ** 31))
        bad = (f.usable_ns >= cut) if self.early_rows else (f.usable_ns > cut)
        n = int(bad.sum())
        cols = {k: v.copy() for k, v in f.cols.items()}
        for k, v in cols.items():
            if k == "t_utc" or n == 0:
                continue
            if k == "book_ok":
                v[bad] = rng.random(n) < 0.9
            elif k == "imb10":
                v[bad] = rng.choice([-0.95, 0.95, -0.5, 0.5], n).astype(v.dtype)
            elif k == "f_delta":
                v[bad] = (rng.choice([-1, 1], n) * rng.integers(2000, 9000, n)).astype(v.dtype)
            else:
                v[bad] = rng.choice([-0.9, -0.5, 0.0, 1.5], n).astype(v.dtype)
        return S.Features(f.usable_ns, cols)

    def tape(self, d, root="NQ", **kw):
        t = REAL_TAPE(d, root, **kw)
        cut = self.cuts.get(d.isoformat())
        if t is None or cut is None:
            return t
        cut -= self.early_s * NS
        i = int(np.searchsorted(t.ts, cut, side="left"))
        if i == 0 or i >= len(t.ts):
            return t
        rng = np.random.default_rng(int(cut % 2 ** 31) + 7)
        n = len(t.ts) - i
        px = t.px.copy()
        px[i:] = px[i - 1] + 0.25 * np.cumsum(rng.integers(-24, 25, n))
        size = t.size.copy()
        size[i:] = rng.integers(1, 60, n)
        return S.Tape(t.root, t.date, t.contract, t.ts, px, size, t.daily)


def one_pass(sp, feats, tape=None):
    REC.clear()
    S.load_tape = tape or REAL_TAPE
    try:
        res = S.run_many(sp, days=DAYS, workers=1, features=feats, keep_ns=True, on_error="raise")
    finally:
        S.load_tape = REAL_TAPE
    return list(REC), res


# ---- oracle by row stamp ---------------------------------------------------------------------------------------
class Table:
    def __init__(self):
        df = D.load_features(dt.date(2021, 9, 21), S.BUILD[1], columns=["imb10", "bid10_rel15", "ask10_rel15", "book_ok", "t_utc"])
        self.t = df["t_utc"].to_numpy(np.int64)
        self.imb, self.b, self.a = (df[c].to_numpy() for c in ("imb10", "bid10_rel15", "ask10_rel15"))
        self.day = {}

    def rows(self, iso, now_ns):
        """Index range [lo, hi) of the session slice's rows usable at now (stamp + 60 s <= now)."""
        if iso not in self.day:
            d = dt.date.fromisoformat(iso)
            m0 = et_ns(d, 0) // NS
            self.day[iso] = int(np.searchsorted(self.t, m0 - 360 * 60 - 60, side="left"))
        lo = self.day[iso]
        hi = int(np.searchsorted(self.t, now_ns // NS - 60, side="right"))
        if hi > lo and (self.t[hi - 1] + 60) * NS > now_ns:      # a non-boundary now: the row must be usable in ns
            hi -= 1
        return lo, max(lo, hi)

    def fresh(self, iso, now_ns):
        lo, hi = self.rows(iso, now_ns)
        if hi <= lo:
            return None
        age = now_ns - (int(self.t[hi - 1]) + 60) * NS
        return (lo, hi) if 0 <= age < 60 * NS else None

    def mean5(self, iso, now_ns):
        r = self.fresh(iso, now_ns)
        if r is None or r[1] - r[0] < 5:
            return None
        lo, hi = r
        w, t = self.imb[hi - 5:hi], self.t[hi - 5:hi]
        if not np.isfinite(w).all() or int(t[-1]) - int(t[0]) != 240:
            return None
        return float(sum(float(x) for x in w) / 5.0)

    def thin(self, iso, now_ns, sd):
        r = self.fresh(iso, now_ns)
        if r is None:
            return None
        v = float((self.a if sd > 0 else self.b)[r[1] - 1])
        if v != v:
            return None
        return 1.0 + v <= 0.8 + 1e-6


def check_options(rec, res, sp, tab):
    out = {"allow_checked": 0, "allow_true": 0, "allow_mismatch": [], "xb_checked": 0, "xb_inpos": 0, "xb_mismatch": [],
           "fired": 0, "book_exits": 0, "book_exit_mismatch": [], "allow_by_variant": {}}
    prm, trades = {}, {}
    for (c, p), r in zip(sp, res):
        st = c(p)
        assert label(st) not in prm, label(st)
        prm[label(st)] = dict(st.p)
        trades[label(st)] = r["trades"]
    tapes = {}
    for r in rec:
        if r[0] == "allow":
            _, lab, iso, now, side, v = r
            p = prm[lab]
            sd = 1 if side == "long" else -1
            want = True
            if p["f_book"] == "on":
                m = tab.mean5(iso, now)
                want = want and m is not None and not m * sd < 0
            if p["f_thin"] == "on":
                want = want and tab.thin(iso, now, sd) is True
            out["allow_checked"] += 1
            out["allow_true"] += bool(v)
            opt = "fbook" if p["f_book"] == "on" else "thin" if p["f_thin"] == "on" else "xbook"
            k = lab.split("|")[0] + ":" + str(p.get("at", "")) + ":" + opt
            a = out["allow_by_variant"].setdefault(k, [0, 0])
            a[0] += 1
            a[1] += bool(v)
            if bool(want) != v:
                out["allow_mismatch"].append([lab, iso, now, side, v, want])
        elif r[0] == "xb":
            _, lab, iso, now, inpos, side, before, after, fired = r
            out["xb_checked"] += 1
            out["xb_inpos"] += bool(inpos)
            if not inpos:
                want, wf = 0, False
            else:
                m = tab.mean5(iso, now)
                if m is None:
                    want, wf = before, False
                elif m * side < 0:
                    want, wf = (0, True) if before + 1 >= 2 else (before + 1, False)
                else:
                    want, wf = 0, False
            if want != after or wf != fired:
                out["xb_mismatch"].append([lab, iso, now, inpos, side, before, after, fired, want, wf])
            if fired:
                out["fired"] += 1
                if iso not in tapes:
                    tapes[iso] = REAL_TAPE(dt.date.fromisoformat(iso))
                ts = tapes[iso].ts
                k = int(np.searchsorted(ts, now + LAT, side="left"))
                tr = [t for t in trades[lab] if t["date"] == iso and t["entry_ns"] < now <= t["exit_ns"]]
                ok = len(tr) == 1 and ((tr[0]["exit_reason"] == "book" and k < len(ts) and tr[0]["exit_ns"] == int(ts[k]))
                                       or (tr[0]["exit_reason"] != "book" and (k >= len(ts) or tr[0]["exit_ns"] <= int(ts[k]))))
                if not ok:
                    out["book_exit_mismatch"].append([lab, iso, now, [(t["exit_reason"], t["exit_ns"]) for t in tr]])
    books = [(lab, t) for lab, ts_ in trades.items() for t in ts_ if t["exit_reason"] == "book"]
    out["book_exits"] = len(books)
    fired = {(r[1], r[2]): [] for r in rec if r[0] == "xb" and r[8]}
    for r in rec:
        if r[0] == "xb" and r[8]:
            fired[(r[1], r[2])].append(r[3])
    for lab, t in books:                               # every book exit has its trigger
        if not any(t["entry_ns"] < now <= t["exit_ns"] for now in fired.get((lab, t["date"]), [])):
            out["book_exit_mismatch"].append([lab, t["date"], "book exit without a trigger", t["exit_ns"]])
    return out


def before_cut(rec, res, cuts):
    r = [x for x in rec if x[3] <= cuts[x[2]]]
    closed = [[t for t in x["trades"] if t["exit_ns"] < cuts[t["date"]]] for x in res]
    ent = [[(t["date"], t["side"], t["entry_price"], t["order_price"], t["entry_ns"], t["oco"]) for t in x["trades"]
            if t["entry_ns"] < cuts[t["date"]]] for x in res]
    return r, closed, ent


def main():
    import run_menus as RM
    assert not set(DAYS) & set(RM.SMOKE_DAYS) and all(S.BUILD[0].isoformat() <= x <= S.BUILD[1].isoformat() for x in DAYS)
    sp = specs()
    feats = S.L2Features(COLS)
    rec0, res0 = one_pass(sp, feats)
    assert all(not r["skipped"] and r["skipped_by_error"] == 0 for r in res0), [r["skipped"] for r in res0 if r["skipped"]][:2]
    rep = {"specs": len(sp), "days": DAYS, "records": dict(Counter(r[0] for r in rec0)), "trades": sum(len(r["trades"]) for r in res0),
           "exit_reasons_counted": None}
    tab = Table()
    c = check_options(rec0, res0, sp, tab)
    rep["C"] = {k: (v if not isinstance(v, list) else {"n": len(v), "first": v[:5]}) for k, v in c.items()}
    # ---- B: cuts exactly on decision instants
    rep["B"] = {}
    dd = [dt.date.fromisoformat(x) for x in DAYS]
    CUTS = {"10:15:00": {d.isoformat(): et_ns(d, 10, 15) for d in dd}, "09:30:00": {d.isoformat(): et_ns(d, 9, 30) for d in dd},
            "03:00:00": {d.isoformat(): et_ns(d, 3, 0) for d in dd}, "00:00:00": {d.isoformat(): et_ns(d, 0, 0) for d in dd},
            "eve 20:00:00": {d.isoformat(): et_ns(d - dt.timedelta(days=1), 20, 0) for d in dd},
            "eve 18:00:00": {d.isoformat(): et_ns(d - dt.timedelta(days=1), 18, 0) for d in dd},
            "08:30:00": {d.isoformat(): et_ns(d, 8, 30) for d in dd}}
    for name, cuts in CUTS.items():
        g = Garble(feats, cuts)
        rec1, res1 = one_pass(sp, g, g.tape)
        a, b = before_cut(rec0, res0, cuts), before_cut(rec1, res1, cuts)
        at_cut = sum(1 for x in a[0] if x[3] == cuts[x[2]])
        after_same = sum(1 for x, y in zip(res0, res1) if x["trades"] == y["trades"])
        rep["B"][name] = {"records_before_or_at_cut": len(a[0]), "records_exactly_at_cut": at_cut, "records_equal": a[0] == b[0],
                          "closed_trades": sum(len(x) for x in a[1]), "closed_equal": a[1] == b[1],
                          "entries_before_cut": sum(len(x) for x in a[2]), "entries_equal": a[2] == b[2],
                          "specs_with_identical_full_day (garbage was not vacuous if < specs)": after_same}
        if name == "10:15:00":                        # LEAK CONTROL: the row usable exactly AT the cut is garbage too
            g2 = Garble(feats, cuts, early_rows=True)
            rec2, res2 = one_pass(sp, g2, g2.tape)
            c2 = before_cut(rec2, res2, cuts)
            rep["B"]["leak control: the row usable AT the cut garbled"] = {"records_equal (must be False)": a[0] == c2[0]}
            g3 = Garble(feats, cuts, early_s=60)
            rec3, res3 = one_pass(sp, g3, g3.tape)
            c3 = before_cut(rec3, res3, cuts)
            rep["B"]["leak control: the last minute of prints before the cut garbled"] = {
                "records_equal (must be False)": a[0] == c3[0], "entries_equal": a[2] == c3[2]}
    Path(__file__).with_name("bc_options.json").write_text(json.dumps(rep, indent=1, default=str))
    print(json.dumps(rep, indent=1, default=str))


if __name__ == "__main__":
    main()
