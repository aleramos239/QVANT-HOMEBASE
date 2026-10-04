"""ADVERSARIAL VERIFIER, new_time / straddle_t: an oracle written from the raw prints (no Template code) for
  * the fire instant (ET wall clock, DST days), * the anchor (the last print STRICTLY before the fire), * ATR30 at the fire
  (Wilder 14 on 30-minute ET buckets since the restart, completed bars only; carry for 18:00 / 00:00), * the two legs,
  * the entry fill (first print at / after fire + 85 ms through a level, inside the 60-minute / flat-5-minute life),
  * the flat time, half days, roll days, the 17:00-18:00 break.
Identity / timing / prices of ORDERS only. No P&L is printed or judged. BUILD days only, <= 10 days, 1 worker.
usage: t1_straddle_oracle.py ROOT day,day,..."""
import sys
import datetime as dt
from zoneinfo import ZoneInfo

sys.dont_write_bytecode = True
ENG = "/Users/ramoscapital/ramos-quant-homebase/research/edge-library/engine"
sys.path.insert(0, "/Users/ramoscapital/ramos-quant-homebase/research/edge-library")
sys.path.insert(0, ENG)
import numpy as np  # noqa: E402
import l2sim as S  # noqa: E402
import families  # noqa: E402
from families import timed as T  # noqa: E402

NY = ZoneInfo("America/New_York")
NS = 10**9
TIMES = ("18:00", "20:00", "00:00", "02:00", "03:00", "08:30", "09:30", "11:05", "13:30")
FLAT = {"18:00": "20:00", "20:00": "23:59", "00:00": "02:00", "02:00": "03:00", "03:00": "08:25", "08:30": "09:30",
        "09:30": "11:00", "11:05": "13:30", "13:30": "15:58"}
PTS = {"NQ": (10.0, 20.0), "ES": (2.5, 5.0), "GC": (2.0, 4.0)}
TICK = {"NQ": 0.25, "ES": 0.25, "GC": 0.10}


class Spy(T.StraddleT):
    log: list = []

    def _arm(self, ctx, legs, **kw):
        out = super()._arm(ctx, legs, **kw)
        Spy.log.append({"date": ctx.date.isoformat(), "at": self.p["at"], "off": self._menu, "seed": self.p["shift_seed"],
                        "now": ctx.now_ns, "lp": kw.get("lp"), "atr": self.atr, "nb": self.nb,
                        "legs": [(s, p) for s, p, _, _ in legs], "orders": [(o.side, o.price, o.sl, o.tp) for o in out],
                        "stop": (self.p["stop_mode"], self.p["stop_val"], self.p["tgt_r"])})
        return out


def wall(d, hhmm, eve):
    """ET wall clock -> UTC ns, computed with datetime (not l2sim.et_ns)."""
    base = d - dt.timedelta(days=1) if eve else d
    h, m = int(hhmm[:2]), int(hhmm[3:5])
    return int(dt.datetime(base.year, base.month, base.day, h, m, tzinfo=NY).timestamp()) * NS


def bars30(ts, px, t0, t_fire):
    """30-minute ET-clock bars from the prints in [t0, t_fire): only buckets that are COMPLETE at t_fire (nominal end <= t_fire).
    -> list of (h, l, c). Buckets are aligned to the UTC half hour (ET offsets are whole hours: the same grid)."""
    a, b = np.searchsorted(ts, [t0, t_fire])
    t, p = ts[a:b], px[a:b]
    step = 30 * 60 * NS
    k = t // step
    out = []
    for kk in np.unique(k):
        if (kk + 1) * step > t_fire:
            continue
        seg = p[k == kk]
        out.append((float(seg.max()), float(seg.min()), float(seg[-1])))
    return out


def wilder(bars, n=14):
    atr, pc, trs = None, None, []
    for i, (h, l, c) in enumerate(bars):
        tr = h - l if i == 0 else max(h - l, abs(h - pc), abs(l - pc))
        trs.append(tr)
        atr = sum(trs) / (i + 1) if i + 1 <= n else (atr * (n - 1) + tr) / n
        pc = c
    return atr


def eve_close_atr(tape):
    """Closing ATR30 of the evening 18:00 -> 24:00 before the tape's trade date: the 30-minute bars 18:00 .. 23:30 only
    (the 23:30 bar closes AT 00:00 = the segment end, where no event fires -> it is not counted)."""
    d = tape.date
    t0, t1 = wall(d, "18:00", True), wall(d, "00:00", False)
    return wilder(bars30(tape.ts, tape.px, t0, t1 - 1))          # t_fire = 00:00 - 1 ns: the 23:30 bucket (end 00:00) is excluded


def main(root, days):
    pts = PTS[root]
    tick = TICK[root]
    offs = {"atr0p25": ("atr", 0.25), "atr0p5": ("atr", 0.5), "atr1": ("atr", 1.0), "ptsA": ("pts", pts[0]), "ptsB": ("pts", pts[1])}
    names = ["straddle_t_" + t.replace(":", "") for t in TIMES]
    specs, meta = [], []
    for name, at in zip(names, TIMES):
        g = families.unit_grid(name, root, "30")
        for c in g[::23]:                                       # 7 cells per time: every offset, mixed exits
            cls, p = c["spec"]
            assert cls is T.StraddleT and p["at"] == at
            specs.append((Spy, p))
            meta.append((at, c["variant"]["off"], c["exit"]))
    Spy.log = []
    res = S.run_many(specs, days=days, root=root, workers=1)
    assert all(r["skipped_by_error"] == 0 for r in res), [r["no_trade"] for r in res if r["skipped_by_error"]]
    log = Spy.log
    sess_all = S.sessions(S.BUILD[0], S.BUILD[1], root)
    rolls = S.rolls(S.load_daily(root))
    tapes, prevs = {}, {}
    for iso in days:
        d = dt.date.fromisoformat(iso)
        tapes[iso] = S.load_tape(d, root)
        i = sess_all.index(d)
        prevs[iso] = S.load_tape(sess_all[i - 1], root) if i > 0 else None
    bad, n_arm, n_tr, n_fill_chk = [], 0, 0, 0
    armed = {(r["date"], r["at"]) for r in log}
    summary = {}
    # ---- 1. every arm against the oracle
    for r in log:
        iso, at, off = r["date"], r["at"], r["off"]
        d = dt.date.fromisoformat(iso)
        tp = tapes[iso]
        eve = at >= "18:00"
        fire = wall(d, at, eve)
        n_arm += 1
        if r["now"] != fire:
            bad.append((iso, at, "fire instant", r["now"], fire))
        k = int(np.searchsorted(tp.ts, fire, side="left"))       # prints [0, k) are strictly before the fire
        if k > 0:
            want_lp, src = float(tp.px[k - 1]), "tape"
            assert tp.ts[k - 1] < fire
        else:
            pv = prevs[iso]
            want_lp, src = float(pv.px[-1]), "prev-close"
            assert pv.ts[-1] < fire and pv.date < d
            if pv.contract != tp.contract:
                bad.append((iso, at, "armed on a roll day from another contract's close", pv.contract, tp.contract))
        if r["lp"] != want_lp:
            bad.append((iso, at, "anchor", r["lp"], want_lp, src))
        # ATR30 at the fire
        restart = wall(d, "18:00", True) if eve else wall(d, "00:00", False)
        bs = bars30(tp.ts, tp.px, restart, fire)
        if len(bs) >= 3:
            want_atr, asrc = wilder(bs), "running"
        elif eve:
            pv = prevs[iso]
            want_atr, asrc = eve_close_atr(pv), "carry prev trade date's evening"
        else:
            want_atr, asrc = eve_close_atr(tp), "carry this trade date's evening"
        if want_atr is None or abs(r["atr"] - want_atr) > 1e-9:
            bad.append((iso, at, "ATR30", r["atr"], want_atr, asrc, len(bs), r["nb"]))
        mode, val = offs[off]
        dist = val * want_atr if mode == "atr" else val
        if abs(r["legs"][0][1] - (want_lp + dist)) > 1e-9 or abs(r["legs"][1][1] - (want_lp - dist)) > 1e-9:
            bad.append((iso, at, off, "legs", r["legs"], want_lp, dist))
        if len(r["orders"]) != 2:
            bad.append((iso, at, off, "orders placed", r["orders"]))
        # the stop / target of each resting order: distance from ITS OWN level, from the menu cell and prior data only
        sm, sv, tg = r["stop"]
        for side, opx, sl, tpx in r["orders"]:
            lvl = round(round((want_lp + side * dist) / tick) * tick, 6)
            sd = sv if sm == "pts" else sv / 100.0 * abs(want_lp + side * dist) if sm == "pct" else sv * want_atr
            sd = max(sd, 2 * tick)
            wsl = round(round((want_lp + side * dist - side * sd) / tick) * tick, 6)
            wtp = None if not tg else round(round((want_lp + side * dist + side * tg * sd) / tick) * tick, 6)
            if abs(opx - lvl) > 1e-9 or abs(sl - wsl) > 1e-9 or (wtp is None) != (tpx is None) or (wtp is not None and abs(tpx - wtp) > 1e-9):
                bad.append((iso, at, off, "order / bracket prices", (side, opx, sl, tpx), (lvl, wsl, wtp)))
        summary.setdefault(at, {"arms": 0, "src": set(), "atr": set()})
        summary[at]["arms"] += 1
        summary[at]["src"].add(src)
        summary[at]["atr"].add(asrc)
    # ---- 2. which (day, time) armed at all: roll days (18:00), half days (13:30), coverage skips
    for iso in days:
        d = dt.date.fromisoformat(iso)
        tp = tapes[iso]
        for at in TIMES:
            got = (iso, at) in armed
            why = []
            if at == "18:00" and iso in rolls and int(np.searchsorted(tp.ts, wall(d, at, True))) == 0:
                why.append("roll day (no anchor)")
            if root in ("NQ", "ES") and d in S.EARLY_CLOSES and at == "13:30":
                why.append("half day")
            summary.setdefault("_days", {})[(iso, at)] = (got, why)
    # ---- 3. every trade against the fill oracle
    for (cls, p), (at, off, ex), r in zip(specs, meta, res):
        per = {}
        for t in r["trades"]:
            n_tr += 1
            iso = t["date"]
            d = dt.date.fromisoformat(iso)
            tp = tapes[iso]
            eve = at >= "18:00"
            fire = wall(d, at, eve)
            flat = wall(d, FLAT[at], eve)
            half = root in ("NQ", "ES") and d in S.EARLY_CLOSES
            if half and not eve:
                flat = min(flat, wall(d, "13:15", False))
            per[iso] = per.get(iso, 0) + 1
            arm = next(x for x in log if x["date"] == iso and x["at"] == at and x["off"] == off and x["stop"] == (p["stop_mode"], p["stop_val"], p["tgt_r"]))
            up, dn = arm["orders"][0][1], arm["orders"][1][1]
            live = fire + 85 * 10**6
            dead = min(fire + 3600 * NS, flat - 300 * NS)       # 60-minute cancel, or the Template's cancel 5 min before flat
            a, b = np.searchsorted(tp.ts, [live, dead])
            seg = tp.px[a:b]
            hit = np.flatnonzero((seg >= up - 1e-9) | (seg <= dn + 1e-9))
            if not len(hit):
                bad.append((iso, at, off, "a trade although no print reached a level inside the order's life", t["entry_ms"]))
                continue
            j = a + int(hit[0])
            side = "long" if tp.px[j] >= up - 1e-9 else "short"
            want_px = (max(up, float(tp.px[j])) + tick) if side == "long" else (min(dn, float(tp.px[j])) - tick)
            n_fill_chk += 1
            if (t["side"], t["entry_ms"], round(t["entry_price"], 6)) != (side, int(tp.ts[j]) // 10**6, round(want_px, 6)):
                bad.append((iso, at, off, "entry fill", (t["side"], t["entry_ms"], t["entry_price"]), (side, int(tp.ts[j]) // 10**6, want_px)))
            # exit: sl / tp strictly before the flat instant; 'time' = the FIRST print at / after the flat instant (the engine's
            # flatten law); 'eod' = the last print of the window (half day 13:15, or no print between flat and the segment end)
            kf = int(np.searchsorted(tp.ts, flat))
            seg_end = wall(d, "00:00", False) if eve else (wall(d, "13:15", False) if half else wall(d, "16:10", False))
            ke = int(np.searchsorted(tp.ts, seg_end))
            if t["exit_reason"] in ("sl", "tp"):
                ok_exit = t["exit_ms"] * 10**6 < flat
            elif t["exit_reason"] == "time":
                ok_exit = kf < ke and t["exit_ms"] == int(tp.ts[kf]) // 10**6
            else:
                ok_exit = t["exit_reason"] == "eod" and t["exit_ms"] == int(tp.ts[ke - 1]) // 10**6 and (half or kf >= ke)
            if not (ok_exit and t["entry_ms"] >= live // 10**6):
                bad.append((iso, at, off, "exit / entry outside the window law", t["exit_reason"], t["entry_ms"], t["exit_ms"], flat // 10**6))
            # never inside the 17:00-18:00 break, never across 00:00 ET
            e0 = dt.datetime.fromtimestamp(t["entry_ms"] / 1000, NY)
            e1 = dt.datetime.fromtimestamp(t["exit_ms"] / 1000, NY)
            if eve != (e0.hour >= 18) or eve != (e1.hour >= 18) or (not eve and (e0.date() != d or e1.date() != d)) or 17 <= e0.hour < 18 or 17 <= e1.hour < 18:
                bad.append((iso, at, off, "segment / break", str(e0), str(e1)))
            if not t["oco"]:
                bad.append((iso, at, off, "not OCO"))
        if any(v > 1 for v in per.values()):
            bad.append((at, off, "more than one trade per time per day", per))
        # a day that armed but did not trade: no print may have reached a level in the order's life
        for arm in [x for x in log if x["at"] == at and x["off"] == off and x["stop"] == (p["stop_mode"], p["stop_val"], p["tgt_r"])]:
            if arm["date"] in per or len(arm["orders"]) != 2:
                continue
            iso = arm["date"]
            d = dt.date.fromisoformat(iso)
            tp = tapes[iso]
            eve = at >= "18:00"
            fire, flat = wall(d, at, eve), wall(d, FLAT[at], eve)
            if root in ("NQ", "ES") and d in S.EARLY_CLOSES and not eve:
                flat = min(flat, wall(d, "13:15", False))
            a, b = np.searchsorted(tp.ts, [fire + 85 * 10**6, min(fire + 3600 * NS, flat - 300 * NS)])
            seg = tp.px[a:b]
            if len(np.flatnonzero((seg >= arm["orders"][0][1] - 1e-9) | (seg <= arm["orders"][1][1] + 1e-9))):
                bad.append((iso, at, off, "armed, a level was reached in the order's life, but no trade"))
    print(f"{root} days={len(days)} specs={len(specs)} arms={n_arm} trades={n_tr} fills checked={n_fill_chk} MISMATCHES={len(bad)}")
    for at in TIMES:
        s = summary.get(at)
        print(f"  {at}: arms={s['arms'] if s else 0} anchor src={sorted(s['src']) if s else None} atr src={sorted(s['atr']) if s else None}")
    print("  (day, time) NOT armed:")
    for (iso, at), (got, why) in sorted(summary["_days"].items()):
        if not got:
            print(f"    {iso} {dt.date.fromisoformat(iso):%a} {at}: expected-by-calendar={why}")
    sk = {}
    for (cls, p), r in zip(specs, res):
        for s in r["skipped"] + r.get("eve_skipped", []):
            sk.setdefault((p["at"], s["date"]), s["reason"])
    print("  skipped:", sorted(sk.items()))
    for b in bad[:40]:
        print("  BAD", b)
    return bad


if __name__ == "__main__":
    root = sys.argv[1]
    days = sys.argv[2].split(",")
    assert len(days) <= 10 and all(S.BUILD[0] <= dt.date.fromisoformat(x) <= S.BUILD[1] for x in days)
    sys.exit(1 if main(root, days) else 0)
