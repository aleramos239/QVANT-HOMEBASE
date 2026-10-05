"""INDEPENDENT CHECKER, stage 4, item 1 + 3: LOOK-AHEAD AUDIT of engine/families/round2.py on real BUILD tapes, and a
from-scratch re-run of chosen cells compared trade for trade with the stores. BUILD only (2021-09-22..2023-12-31): the engine's
own loader refuses 2025+, and no 2024 date is ever requested here.
What is proved per (root, release day, X) for event_dir:
  RAW   my own reading of the tape (numpy only): anchor = last print with ts < T, decision print = last print with ts <= T + X,
        side = sign(decision - anchor), order live at T + X + 85 ms, fill = first print with ts >= that, price = print +/- 1 tick.
        The engine's trade must have the same side, the same entry time and the same entry price.
  REWRITE  every print stamped AFTER the decision instant is rewritten three ways -- 'mirror' (price reflected around the
        decision print: the future goes the other way), 'late' (timestamps pushed 3 s later), 'cut' (all of them deleted) -- and
        the engine is run again: the decision instant, the anchor, the decision print, the direction and the first print index
        the order may fill on (as a TIME: T + X + 85 ms) must be unchanged, and any fill must be stamped >= T + X + 85 ms.
For straddle_wide: the anchor handed to the bracket must equal the last print with ts < (clock time - 1 s), the legs must be
anchor +/- the written offset, live from that instant + 85 ms; rewriting every print from the arming instant on must leave the
anchor and the leg prices unchanged; the engine's fill is compared with my own first-touch reading of the tape.
  python out/check_entries/lookahead_audit.py [workers]   -> out/check_entries/lookahead_<root>.json (restartable per root)"""
import csv
import datetime as dt
import json
import sys
from multiprocessing import Pool
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

HERE = Path(__file__).resolve().parent
W = HERE.parents[1]
sys.path.insert(0, str(W / "engine"))
import l2sim as S  # noqa: E402
from families import round2 as R2  # noqa: E402

NY = ZoneInfo("America/New_York")
BUILD = (dt.date(2021, 9, 22), dt.date(2023, 12, 31))
TICK = {"NQ": 0.25, "ES": 0.25, "GC": 0.10}
OFFS = {"NQ": (10.0, 15.0, 20.0, 30.0), "ES": (2.5, 4.0, 5.0, 8.0), "GC": (2.0, 3.0, 4.0, 6.0)}      # the spec text, typed again
LAT = 85_000_000
XS = (0.25, 5.0, 60.0)
# cells re-run from scratch on EVERY BUILD day and compared with the store (the units' central variants + the audit cells)
SCRATCH = {
    "NQ": {"event_dir_0830": ["x0p25_atr1p5-r0", "x5_atr1p5-r0", "x60_atr1p5-r0", "x5_pts10-r1", "x0p25_atr1p5-r2"],
           "event_dir_1000": ["x0p25_atr1p5-r0", "x5_atr1p5-r0", "x60_atr1p5-r0", "x0p25_pts30-r0"],
           "straddle_wide_0830": ["offB_offx0p5-r2", "offD_offx0p5-r3"], "straddle_wide_1000": ["offA_offx0p5-r2"]},
    "GC": {"event_dir_0830": ["x0p25_atr1p5-r0", "x5_atr1p5-r0", "x60_atr1p5-r0", "x2_pct0p1-r1", "x60_pct0p1-r0"],
           "event_dir_1000": ["x0p25_atr1p5-r0", "x5_atr1p5-r0", "x60_atr1p5-r0", "x2_pts7-r2"],
           "straddle_wide_0830": ["offB_offx1p5-r3", "offB_offx0p5-r1"], "straddle_wide_1000": ["offC_offx1-r2"]},
    "ES": {"event_dir_0830": ["x0p25_pts2p5-r0", "x5_atr1p5-r2"], "event_dir_1000": ["x5_pct0p1-r0"],
           "straddle_wide_0830": ["offA_offx1p5-r1", "offD_offx1-r1"], "straddle_wide_1000": ["offA_offx1-r1"]},
}


def t_ns(d, hh, mm):
    return int(dt.datetime(d.year, d.month, d.day, hh, mm, tzinfo=NY).timestamp()) * 1_000_000_000


class DirProbe(R2.EventDir):
    def decide(self, ctx):
        before = {id(o) for o in ctx._s.orders}
        self.probe = {"now": int(ctx.now_ns), "anchor": self.anchor}
        super().decide(ctx)
        new = [o for o in ctx._s.orders if id(o) not in before]
        self.probe.update(dec_px=self.dec_px, side=new[0].side if new else 0,
                          live_ns=(int(ctx.now_ns) + int(ctx._s.place_ns)) if new else None, min_i=new[0].min_i if new else None)


class WideProbe(R2.StraddleWide):
    def _arm(self, ctx, legs, ttl=None, imm=False, tag=None, lp=None):
        os_ = super()._arm(ctx, legs, ttl=ttl, imm=imm, tag=tag, lp=lp)
        self.probe = {"now": int(ctx.now_ns), "lp": lp, "prices": sorted(float(o.price) for o in os_), "min_i": [o.min_i for o in os_],
                      "n": len(os_)}
        return os_


def cells_of(root):
    out = {}
    for fam, ids in SCRATCH[root].items():
        meta = json.loads((W / "runs" / f"{fam}-{root}-tf30" / "run.json").read_text())
        by = {c["id"]: c["inputs"] for c in meta["cells"]}
        out[fam] = [(cid, by[cid]) for cid in ids]
    return out


def run(cls, inputs, root, tape, window, d):
    st = cls(dict(inputs))
    st.root = root
    b = getattr(st, "begin_day", None)
    if b is not None:
        b(d)
    res = S.run_session(st, tape, S.Costs(), qty=1, daily=[], window=window, carry=None)
    return st, res


def rewrite(tape, cut_ns, how, pivot, tick, inclusive=False):
    """A copy of the tape whose prints stamped after cut_ns (inclusive=True: at or after) are rewritten."""
    ts, px, size = tape.ts.copy(), tape.px.copy(), tape.size.copy()
    fut = ts >= cut_ns if inclusive else ts > cut_ns
    if how == "mirror":
        px[fut] = np.round((2.0 * pivot - px[fut]) / tick) * tick
    elif how == "late":
        ts[fut] = ts[fut] + 3_000_000_000
    elif how == "cut":
        ts, px, size = ts[~fut], px[~fut], size[~fut]
    return S.Tape(tape.root, tape.date, tape.contract, ts, px, size)


def day_job(job):
    root, iso, cells, rel0830, rel1000 = job
    d = dt.date.fromisoformat(iso)
    tape = S.load_tape(d, root)
    out = {"date": iso, "scratch": {}, "dir": [], "wide": [], "skip": None}
    if tape is None or len(tape.ts) == 0:
        out["skip"] = "no tape"
        return out
    window = S.effective_session_window(d, ("00:00", "16:10"), root)
    gaps = S.missing_hours(tape.ts, d, window)
    if gaps:
        out["skip"] = "missing hours"
        return out
    ts, px, tick = tape.ts, tape.px, TICK[root]
    for fam, lst in cells.items():
        cls = DirProbe if fam.startswith("event_dir") else WideProbe
        hh, mm = (8, 30) if fam.endswith("0830") else (10, 0)
        T = t_ns(d, hh, mm)
        release = rel0830 if (hh, mm) == (8, 30) else rel1000
        for cid, inputs in lst:
            st, res = run(cls, inputs, root, tape, window, d)
            out["scratch"][f"{fam}|{cid}"] = [(t["entry_ms"], max(0, (t["exit_ms"] - t["entry_ms"]) // 1000), t["net"], 1 if t["side"] == "long" else -1)
                                              for t in res.trades]
            pr = getattr(st, "probe", None)
            if cls is DirProbe:
                x_ns = int(round(float(inputs["x"]) * 1e9))
                # ---- RAW: my own reading of the tape
                ia = int(np.searchsorted(ts, T, side="left")) - 1
                ic = int(np.searchsorted(ts, T + x_ns, side="right")) - 1
                day0 = int(np.searchsorted(ts, t_ns(d, 0, 0), side="left"))
                raw_side = 0
                if ia >= day0:
                    mv = float(px[ic]) - float(px[ia])
                    raw_side = 0 if abs(mv) < tick / 2 else (1 if mv > 0 else -1)
                live = T + x_ns + LAT
                k = int(np.searchsorted(ts, live, side="left"))
                rec = {"fam": fam, "cid": cid, "x": inputs["x"], "release": release, "raw_side": raw_side, "n_at_instant": int((ts == T + x_ns).sum()),
                       "eng_trades": len(res.trades), "probe": pr is not None}
                if pr is not None:
                    rec.update(now_ok=pr["now"] == T + x_ns, anchor_ok=(ia >= day0 and abs(pr["anchor"] - float(px[ia])) < 1e-9),
                               dec_ok=pr["dec_px"] is not None and abs(pr["dec_px"] - float(px[ic])) < 1e-9, side_ok=pr["side"] == raw_side,
                               live_ok=(pr["live_ns"] == live) if pr["side"] else True)
                if res.trades:
                    t = res.trades[0]
                    sd = 1 if t["side"] == "long" else -1
                    rec.update(tr_side_ok=sd == raw_side, tr_time_ok=(k < len(ts) and t["entry_ms"] == int(ts[k]) // 1_000_000),
                               tr_px_ok=(k < len(ts) and abs(t["entry_price"] - (float(px[k]) + sd * tick)) < 1e-6),
                               fill_after_live=(k < len(ts) and int(ts[k]) >= live), fill_gap_ms=round((int(ts[k]) - (T + x_ns)) / 1e6, 3) if k < len(ts) else None,
                               prev_print_before_live=(k == 0 or int(ts[k - 1]) < live))
                # ---- REWRITE the future (release days, the three audit waits, the plain ATR cell only)
                if release and float(inputs["x"]) in XS and cid.endswith("atr1p5-r0") and pr is not None:
                    rw = {}
                    for how in ("mirror", "late", "cut"):
                        t2 = rewrite(tape, T + x_ns, how, float(px[ic]), tick)
                        st2, res2 = run(DirProbe, inputs, root, t2, window, d)
                        p2 = getattr(st2, "probe", None)
                        same = (p2 is not None and p2["now"] == pr["now"] and p2["anchor"] == pr["anchor"] and p2["dec_px"] == pr["dec_px"]
                                and p2["side"] == pr["side"] and p2["live_ns"] == pr["live_ns"])
                        late_ok = all(int(t2.ts[np.searchsorted(t2.ts, tt["entry_ms"] * 1_000_000, side="left")]) >= live for tt in res2.trades) if res2.trades else True
                        rw[how] = {"same": bool(same), "fill_after_live": bool(late_ok), "trades": len(res2.trades),
                                   "side_trade_same": (not res2.trades or not res.trades or res2.trades[0]["side"] == res.trades[0]["side"])}
                    rec["rewrite"] = rw
                out["dir"].append(rec)
            else:
                Tarm = T - 1_000_000_000
                ia = int(np.searchsorted(ts, Tarm, side="left")) - 1
                off = OFFS[root]["ABCD".index(inputs["off"])]
                rec = {"fam": fam, "cid": cid, "release": release, "probe": pr is not None, "eng_trades": len(res.trades)}
                if pr is not None:
                    lp = float(px[ia])
                    up, dn = round((lp + off) / tick) * tick, round((lp - off) / tick) * tick
                    live = Tarm + LAT
                    k0 = int(np.searchsorted(ts, live, side="left"))
                    k1 = int(np.searchsorted(ts, Tarm + 300_000_000_000, side="left"))      # cancelled 5 minutes after it was placed
                    rec.update(now_ok=pr["now"] == Tarm, anchor_ok=abs(pr["lp"] - lp) < 1e-9, anchor_age_ms=round((Tarm - int(ts[ia])) / 1e6, 1),
                               legs_ok=(pr["n"] == 2 and abs(pr["prices"][0] - dn) < 1e-6 and abs(pr["prices"][1] - up) < 1e-6),
                               live_ok=all(m == k0 for m in pr["min_i"]))
                    seg = px[k0:k1]
                    hu, hd = np.flatnonzero(seg >= up - 1e-9), np.flatnonzero(seg <= dn + 1e-9)
                    fu, fd = (int(hu[0]) if len(hu) else None), (int(hd[0]) if len(hd) else None)
                    if fu is None and fd is None:
                        rec["raw_fill"] = None
                        rec["fill_ok"] = len(res.trades) == 0
                    else:
                        longf = fd is None or (fu is not None and fu < fd)
                        kk = k0 + (fu if longf else fd)
                        price = (max(up, float(px[kk])) + tick) if longf else (min(dn, float(px[kk])) - tick)
                        rec["raw_fill"] = [int(ts[kk]) // 1_000_000, 1 if longf else -1]
                        t = res.trades[0] if res.trades else None
                        rec["fill_ok"] = bool(t is not None and t["entry_ms"] == int(ts[kk]) // 1_000_000 and (t["side"] == "long") == longf
                                              and abs(t["entry_price"] - price) < 1e-6 and int(ts[kk]) >= live)
                    if release:
                        rw = {}
                        for how in ("mirror", "late", "cut"):
                            t2 = rewrite(tape, Tarm, how, lp, tick, inclusive=True)
                            st2, _ = run(WideProbe, inputs, root, t2, window, d)
                            p2 = getattr(st2, "probe", None)
                            rw[how] = bool(p2 is not None and p2["now"] == pr["now"] and p2["lp"] == pr["lp"] and p2["prices"] == pr["prices"])
                        rec["rewrite"] = rw
                out["wide"].append(rec)
    return out


def store_rows(root, fam, cid):
    d = W / "runs" / f"{fam}-{root}-tf30"
    meta = json.loads((d / "run.json").read_text())
    assert meta["period"] == "build"
    z = np.load(d / "cells.npz")
    i = next(k for k, c in enumerate(meta["cells"]) if c["id"] == cid)
    a, b = int(z["off"][i]), int(z["off"][i + 1])
    by = {}
    for o, e, du, n, s in zip(z["date"][a:b], z["entry_ms"][a:b], z["dur_s"][a:b], z["net"][a:b], z["side"][a:b]):
        by.setdefault(dt.date.fromordinal(int(o)).isoformat(), []).append((int(e), int(du), float(n), int(s)))
    return by, {s["date"] for s in meta["coverage"]["skipped"]}


def main():
    workers = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    assert workers <= 8
    ev = [r for r in csv.DictReader((W / "engine" / "cache" / "events.csv").open()) if r["date"] <= "2023-12-31"]
    r0830 = {r["date"] for r in ev if r["time_et"] == "08:30"}
    r1000 = {r["date"] for r in ev if r["time_et"] == "10:00"}
    for root in ("NQ", "GC", "ES"):
        dst = HERE / f"lookahead_{root}.json"
        if dst.exists():
            print(root, "already done")
            continue
        cells = cells_of(root)
        days = [d.isoformat() for d in S.sessions(BUILD[0], BUILD[1], root)]
        assert days and days[-1] <= "2023-12-31" and days[0] >= "2021-09-22"
        jobs = [(root, iso, cells, iso in r0830, iso in r1000) for iso in days]
        with Pool(workers) as p:
            res = p.map(day_job, jobs, chunksize=4)
        dst.write_text(json.dumps(res))
        print(root, "days", len(days), "skipped", sum(1 for r in res if r["skip"]), flush=True)


if __name__ == "__main__":
    main()
