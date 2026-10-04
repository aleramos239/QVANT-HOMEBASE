"""ADVERSARIAL VERIFIER (look-ahead + fidelity) of family group new_l2 -- part A: D1 / D5 SIGNALS vs an independent oracle.

10 BUILD days the author did NOT use (DST Mondays, the week after a DST start, both remaining half days, a post-holiday
Tuesday, a roll day, a year's first session). 1 worker, in-process. COUNTS / IDENTITY ONLY: no P&L is computed or printed.

The spy subclasses replace `_mkt` by a recorder (no order is ever placed -> the instance is always flat, so `fam_signal`
runs at EVERY eligible tf close). The oracle recomputes every decision from the raw tape (S.load_tape) and the raw feature
table (l2data.load_features, by row STAMP), with its own bar builder, its own session clock (zoneinfo) and its own
percentile -- it never touches ctx or the family code.
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
HALF = {"2021-11-26", "2023-11-24"}
ET = zoneinfo.ZoneInfo("America/New_York")
SESS = {"asia": (0, 10800), "london": (10800, 30300), "pre": (30300, 34200), "nyam": (34200, 39600), "mid": (39600, 48600),
        "pm": (48600, 57480), "eve": (-21600, -60)}
INST = {"all": ("asia", "london", "nyam", "mid", "pm"), "pre": ("pre",), "eve": ("eve",)}
LOG = []


class SpyD5(L2.FlowExhaust):
    def _mkt(self, ctx, side, **kw):
        LOG.append(("d5", self.day, self.p["sess"], int(self.p["tf"]), float(self.p["q"]), int(ctx.now_ns // S.NS), side))


class SpyD1(L2.BimbFollowD1):
    def _mkt(self, ctx, side, **kw):
        LOG.append(("d1", self.day, self.p["sess"], int(self.p["tf"]), float(self.p["k"]), int(ctx.now_ns // S.NS), side))


def et_s(d, hh, mm=0):
    return int(dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=ET).timestamp())


def pct(vals, q):
    """Linear-interpolation percentile, written out (not numpy's)."""
    v = sorted(float(x) for x in vals)
    r = (len(v) - 1) * q / 100.0
    lo = int(np.floor(r))
    hi = min(lo + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (r - lo)


def closes(ts, px, t0, t1, tf):
    """Every tf-bar close of a segment [t0, t1) (seconds): [(now, nominal, h, l, c)] in the order the Template sees them."""
    a, b = np.searchsorted(ts, [t0 * S.NS, t1 * S.NS], side="left")
    mins = (ts[a:b] // (60 * S.NS)).astype(np.int64)
    p = px[a:b]
    out, cur = [], None
    if len(mins) == 0:
        return out
    cut = np.flatnonzero(np.concatenate(([True], mins[1:] != mins[:-1], [True])))
    for i, j in zip(cut[:-1], cut[1:]):
        m0 = int(mins[i]) * 60
        end = m0 + 60
        if end >= t1:                                  # an event at / after the window end is never delivered
            break
        seg = p[i:j]
        k = m0 // (tf * 60)
        if cur is not None and cur[0] != k:
            out.append((end, (cur[0] + 1) * tf * 60, cur[1], cur[2], cur[3]))
            cur = None
        if cur is None:
            cur = [k, float(seg.max()), float(seg.min()), float(seg[-1])]
        else:
            cur[1], cur[2], cur[3] = max(cur[1], float(seg.max())), min(cur[2], float(seg.min())), float(seg[-1])
        if end % (tf * 60) == 0:
            out.append((end, (cur[0] + 1) * tf * 60, cur[1], cur[2], cur[3]))
            cur = None
    return out


def oracle_day(iso, tab, tape):
    """-> list of the LOG tuples the families must produce on this day."""
    d = dt.date.fromisoformat(iso)
    m0 = et_s(d, 0)
    de = d - dt.timedelta(days=1)
    e0 = et_s(de, 18)
    day_end = et_s(d, 13, 15) if iso in HALF else et_s(d, 16, 10)
    lo_u, hi_u = m0 - 360 * 60, et_s(d + dt.timedelta(days=1), 0)
    stamp = tab["t_utc"]
    sel = (stamp + 60 >= lo_u) & (stamp + 60 < hi_u)
    st, fd, ok, imb = stamp[sel], tab["f_delta"][sel], tab["book_ok"][sel], tab["imb10"][sel]
    out = []
    for segname, t0, t1 in (("eve", e0, m0), ("day", m0, day_end)):
        for tf in (1, 5):
            cl = closes(tape.ts, tape.px, t0, t1, tf)
            for inst, ids in INST.items():
                if (inst == "eve") != (segname == "eve"):
                    continue
                for n, (now, nom, h, l, c) in enumerate(cl):
                    nb = n + 1
                    rn, rm = now - m0, nom - m0
                    sid = next((s for s in ids if SESS[s][0] < rn <= SESS[s][1]), None)
                    if sid is None:
                        continue
                    s0, s1 = SESS[sid]
                    if not (s0 < rm <= s1) or nb < 3 or not rn < s1 - 300:
                        continue
                    nu = int(np.searchsorted(st, now - 60, side="right"))      # rows usable at `now`: stamp + 60 <= now
                    if nu == 0:
                        continue
                    # ---- D5 (tf 1 and 5)
                    cut = (m0 + (13 * 3600 + 10 * 60 if iso in HALF else 16 * 3600 + 5 * 60)) if segname == "day" else None
                    earlier = [x for x in cl[:n] if s0 < x[1] - m0 <= s1]
                    if (now == nom and earlier and (cut is None or now < cut) and st[nu - 1] == now - 60 and bool(ok[nu - 1])):
                        step = tf * 60
                        sums, valid = [], []
                        for j in range(61):
                            a, b = now - (j + 1) * step, now - j * step
                            ia, ib = np.searchsorted(st[:nu], [a, b], side="left")
                            v = fd[ia:ib]
                            v = v[np.isfinite(v)]
                            valid.append(len(v) > 0)
                            sums.append(float(v.sum()) if len(v) else 0.0)
                        hist = [abs(sums[j]) for j in range(1, 61) if valid[j]]
                        if valid[0] and abs(sums[0]) > 0 and len(hist) >= 30:
                            for q in (85.0, 90.0, 95.0):
                                if abs(sums[0]) >= pct(hist, q):
                                    mid = (h + l) / 2.0
                                    if sums[0] > 0 and h > max(x[2] for x in earlier) and c < mid:
                                        out.append(("d5", iso, inst, tf, q, now, "short"))
                                    elif sums[0] < 0 and l < min(x[3] for x in earlier) and c > mid:
                                        out.append(("d5", iso, inst, tf, q, now, "long"))
                    # ---- D1 (tf 5 only): no on-time rule, no half-day cut (the L2 screen's B1 unchanged)
                    if tf == 5 and nu >= 31 and st[nu - 1] == now - 60 and bool(ok[nu - 1]) and np.isfinite(imb[nu - 1]):
                        a = max(0, nu - 61)
                        hs, hv, hk = st[a:nu - 1], imb[a:nu - 1], ok[a:nu - 1]
                        keep = hk.astype(bool) & np.isfinite(hv) & (hs >= st[nu - 1] - 3600)
                        hh = hv[keep].astype(np.float64)
                        if len(hh) >= 30:
                            mu = float(hh.sum() / len(hh))
                            sd = float(np.sqrt(((hh - mu) ** 2).sum() / len(hh)))
                            if sd > 0:
                                z = (float(imb[nu - 1]) - mu) / sd
                                for k in (1.5, 2.0, 2.5):
                                    if abs(z) >= k:
                                        out.append(("d1", iso, inst, tf, k, now, "long" if z > 0 else "short"))
    return out


def main():
    assert all(S.BUILD[0].isoformat() <= x <= S.BUILD[1].isoformat() for x in DAYS)
    import run_menus as RM
    assert not set(DAYS) & set(RM.SMOKE_DAYS), "days must differ from the author's"
    cols = ["f_delta", "imb10", "book_ok", "t_utc"]
    df = D.load_features(dt.date(2021, 9, 21), S.BUILD[1], columns=cols)
    tab = {"t_utc": df["t_utc"].to_numpy(np.int64), "f_delta": df["f_delta"].to_numpy(np.float64),
           "book_ok": df["book_ok"].to_numpy(bool), "imb10": df["imb10"].to_numpy()}
    assert (df.index.asi8 // (10 ** 9 if df.index.asi8.max() > 10 ** 15 else 1) == tab["t_utc"] + 60).all()
    print("imb10 dtype", tab["imb10"].dtype, "rows", len(df))
    # ---- the families (spied), exactly as run_menus runs a cell: three instances all / pre / eve
    d5 = [(SpyD5, {"tf": tf, "sess": s, "q": q}) for tf in ("1", "5") for q in (85.0, 90.0, 95.0) for s in ("all", "pre", "eve")]
    d1 = [(SpyD1, {"tf": "5", "sess": s, "k": k}) for k in (1.5, 2.0, 2.5) for s in ("all", "pre", "eve")]
    r5 = S.run_many(d5, days=DAYS, workers=1, features=families.features_for("flow_exhaust"), on_error="raise")
    r1 = S.run_many(d1, days=DAYS, workers=1, features=families.features_for("bimb_follow_d1"), on_error="raise")
    for r in r5 + r1:
        assert not r["trades"] and not r["skipped"] and not r["eve_skipped"], (r["skipped"], r["eve_skipped"])
    got = Counter(LOG)
    want = Counter()
    for iso in DAYS:
        tape = S.load_tape(dt.date.fromisoformat(iso))
        want.update(oracle_day(iso, tab, tape))
    only_got = sorted((got - want).elements())
    only_want = sorted((want - got).elements())
    rep = {"days": DAYS, "signals_family": sum(got.values()), "signals_oracle": sum(want.values()),
           "only_family": len(only_got), "only_oracle": len(only_want)}
    for fam in ("d5", "d1"):
        rep[fam] = {"family": sum(v for k, v in got.items() if k[0] == fam), "oracle": sum(v for k, v in want.items() if k[0] == fam),
                    "by_day": {iso: sum(v for k, v in got.items() if k[0] == fam and k[1] == iso) for iso in DAYS},
                    "by_inst": dict(Counter(k[2] for k in got.elements() if k[0] == fam)),
                    "by_tf": dict(Counter(k[3] for k in got.elements() if k[0] == fam)),
                    "by_side": dict(Counter(k[6] for k in got.elements() if k[0] == fam))}
    def hm(k):
        return dt.datetime.fromtimestamp(k[5], ET).strftime("%Y-%m-%d %H:%M:%S")
    rep["first_only_family"] = [list(k) + [hm(k)] for k in only_got[:15]]
    rep["first_only_oracle"] = [list(k) + [hm(k)] for k in only_want[:15]]
    # special-day evidence (counts): half-day signals at / after 13:10 ET, D1 vs D5
    late = Counter()
    for k in got.elements():
        if k[1] in HALF:
            t = dt.datetime.fromtimestamp(k[5], ET)
            if t.date().isoformat() == k[1] and (t.hour, t.minute) >= (13, 10):
                late[k[0]] += 1
    rep["half_day_signals_from_1310"] = dict(late)
    hours = Counter()
    for k in got.elements():
        hours[(k[0], k[3], dt.datetime.fromtimestamp(k[5], ET).hour)] += 1
    rep["by_fam_tf_hour"] = {f"{a}-tf{b}-h{c:02d}": v for (a, b, c), v in sorted(hours.items())}
    Path(__file__).with_name("a_signals.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: v for k, v in rep.items() if k != "by_fam_tf_hour"}, indent=1))
    print("OK" if not only_got and not only_want else "MISMATCH")


if __name__ == "__main__":
    main()
