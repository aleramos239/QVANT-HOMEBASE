"""Local sanity test of the pp_* drafts on the REAL engine (homebase.backtest.engine.run_session) with a
synthetic random-walk tape (9 days, 1 print / 3 s). No tester jobs. Usage: localcheck.py [fam ...] [-q]
Asserts per run: no strategy error, orders only at tf closes (or a family's clock times), SL/TP on the right
side of the entry ref, entries inside a session and before its last 5 min, exits by the session end, one
position at a time, entries per session <= max_tr, random is deterministic."""
import collections
import datetime as dt
import importlib.util
import math
import random as rnd
import sys
import time
from array import array
from pathlib import Path

REPO = Path.home() / "ramos-quant-homebase"
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import pilot as PL                                        # noqa: E402  (--pilot es / PP_PILOT=es: drafts pp_es_<fam>, root ES)
from homebase.backtest import engine                      # noqa: E402
from homebase.backtest.engine import Costs, run_session   # noqa: E402
from homebase.backtest.tape import Tape, et_ns            # noqa: E402

DRAFTS = Path.home() / ".homebase/strategies"
FAMS = ["orb", "straddle", "donchian", "squeeze", "ema_ribbon", "tema_slope", "ema_pullback", "supertrend",
        "rsi2", "vwap_band", "vwap_z", "vwap_flip", "pinbar", "sweep_rev", "ib", "gap", "tod_drift", "random",
        "lon_break", "first_bar_mom", "mid_fade"]
TIME_FAMS = {"orb", "straddle", "ib", "lon_break", "tod_drift"}
DAYS = ([dt.date(2024, 1, d) for d in (8, 9, 10, 11, 12, 16, 17, 18, 19, 31)]      # 01-11 = CPI day, 01-31 = FOMC day
        + [dt.date(2024, 3, 11)])                                                   # 03-11 = contract-roll day
COMMON_VAR = [{"stop_mode": "struct"}, {"stop_mode": "pts", "stop_val": 12.0}, {"trail_atr": 1.0, "exit_bars": 4},
              {"f_trend": "with"}, {"f_vwap": "against", "dir": "short"}, {"tgt_r": 0.0, "dir": "long"},
              {"max_tr": 1}, {"tf": "1", "stop_val": 3.0}]
FAM_VAR = {"orb": [{"or_min": "5"}, {"or_min": "30", "tf": "30"}],
           "straddle": [{"news_only": True}, {"delay_min": 10, "off_atr": 0.3}, {"news_only": True, "tf": "1"}],
           "squeeze": [{"sq_type": "nr7"}, {"sq_type": "inside"}, {"sq_type": "nr7", "tf": "1"}],
           "ib": [{"mode": "fade"}, {"mode": "fade", "tf": "1"}], "gap": [{"mode": "go", "min_gap_atr": 0.0}],
           "vwap_flip": [{"anchor": "rth", "hold": 1}], "sweep_rev": [{"levels": "pd"}, {"levels": "on"}],
           "rsi2": [{"trend_f": True, "th": 20.0}], "tod_drift": [{"dir": "short", "off_min": 15}],
           "random": [{"p_entry": 0.3}], "lon_break": [{"min_rng_atr": 1.0}], "first_bar_mom": [{"k": 0.5}],
           "mid_fade": [{"k": 0.0}], "pinbar": [{"wick": 0.5}], "vwap_band": [{"band": 1.0}],
           "vwap_z": [{"zth": 1.0}], "donchian": [{"n": 5}], "tema_slope": [{"n": 5}],
           "ema_pullback": [{"tf": "1"}], "supertrend": [{"tf": "1"}], "ema_ribbon": [{"tf": "15"}]}
BASE = ([{"tf": t} for t in ("1", "5", "15", "30")] + [{"sess": s} for s in ("asia", "london", "nyam", "mid", "pm")]
        + [{"tf": "15", "sess": "nyam"}])


def make_day(d, r, start_px, ctx_):
    t0 = et_ns(d, "00:00")
    n = (16 * 3600 + 10 * 60) // 3 + 1
    ts, px, sz = array("q"), array("d"), array("q")
    x, drift, anchor = start_px + r.gauss(0, 40), 0.0, start_px
    for i in range(n):
        s = i * 3
        vol = 0.5 if s < 34200 or s > 57600 else (2.0 if s < 36000 else 1.0)
        if i % 800 == 0:
            drift = r.gauss(0, 0.06)
        anchor += r.gauss(0, 0.03)
        x += drift + -0.003 * (x - anchor) + r.gauss(0, 0.9 * vol)
        ts.append(t0 + s * 1_000_000_000)
        px.append(round(x * 4) / 4)
        sz.append(r.randint(1, 4 if vol < 1 else 9))
    return Tape(PL.ROOT, d, PL.ROOT + "H4", ts, px, sz, {"h": max(px), "l": min(px), "c": px[-1]})


def build_world(seed=7):
    r = rnd.Random(seed)
    c, daily = {"NQ": 17000.0, "ES": 4700.0}.get(PL.ROOT, 17000.0), []
    for k in range(30):
        c += r.gauss(0, 90)
        daily.append({"date": (dt.date(2023, 12, 1) + dt.timedelta(days=k)).isoformat(),
                      "h": c + r.uniform(80, 220), "l": c - r.uniform(80, 220), "c": c})
    tapes, dl = [], list(daily)
    for d in DAYS:
        tp = make_day(d, r, dl[-1]["c"], None)
        tapes.append((tp, list(dl)))
        dl.append({"date": d.isoformat(), **tp.daily})
    return tapes


REC = []
_orig = engine.Ctx._entry


def _rec(self, kind, side, price, qty, sl, tp, tp_rr, ref):
    REC.append((self._s.now, self.date, kind, side, price, sl, tp, ref))
    return _orig(self, kind, side, price, qty, sl, tp, tp_rr, ref)


engine.Ctx._entry = _rec


def load_cls(fam):
    p = DRAFTS / f"{PL.PREFIX}{fam}.py"
    spec = importlib.util.spec_from_file_location(f"{PL.PREFIX}{fam}", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return next(v for v in vars(m).values() if isinstance(v, type) and issubclass(v, engine_base()) and v is not engine_base())


def engine_base():
    from homebase.strategies.base import Strategy
    return Strategy


def run(cls, params, world):
    st = cls(params)
    REC.clear()
    trades, skips = [], []
    for tape, prior in world:
        if not st.trades_on(tape.date):
            continue
        res = run_session(st, tape, Costs(4.0, 1.0), qty=1, daily=prior)
        trades += [(tape.date, t) for t in res.trades]
        if res.skip:
            skips.append((tape.date, res.skip))
    return st, list(REC), trades, skips


def problems(fam, st, recs, trades, skips):
    P = []
    p = st.p
    tf, acts = int(p["tf"]), st.sessions()
    tsecs = set()
    for t in st.times():
        h = [int(x) for x in t.split(":")] + [0]
        tsecs.add(h[0] * 3600 + h[1] * 60 + h[2])
    for d, s in skips:
        if s.startswith("strategy error"):
            P.append(f"{d} {s}")
    win = {s: SESS_[s] for s in acts}
    for now, d, kind, side, price, sl, tp, ref in recs:
        sec = (now - et_ns(d, "00:00")) // 1_000_000_000
        sd = 1 if side == "long" else -1
        if not (sec % (tf * 60) == 0 or (fam in TIME_FAMS and sec in tsecs)):
            P.append(f"{d} order at {sec}s not a tf close/time event ({kind} {side})")
        if not any(a <= sec < b - 300 for a, b in win.values()):
            P.append(f"{d} order at {sec}s outside session entry windows")
        if sl is not None and not (sl - ref) * sd < 0:
            P.append(f"{d} {side} sl {sl} wrong side of ref {ref}")
        if tp is not None and not (tp - ref) * sd > 0:
            P.append(f"{d} {side} tp {tp} wrong side of ref {ref}")
        if sl is None:
            P.append(f"{d} order without stop")
        if kind == "stop" and price != ref:
            P.append(f"{d} stop ref != price")
    per = collections.Counter()
    last_exit = {}
    for d, t in sorted(trades, key=lambda x: x[1].entry_ns):
        t0 = et_ns(d, "00:00")
        es, xs = (t.entry_ns - t0) / 1e9, (t.exit_ns - t0) / 1e9
        s = next((k for k, (a, b) in win.items() if a <= es < b), None)
        if s is None:
            P.append(f"{d} entry at {es:.0f}s in no active session")
            continue
        a, b = win[s]
        if es >= b - 300:
            P.append(f"{d} entry at {es:.0f}s in last 5 min of {s}")
        if xs > b + 10:
            P.append(f"{d} exit at {xs:.0f}s after {s} end")
        if d in last_exit and t.entry_ns < last_exit[d]:
            P.append(f"{d} overlapping positions")
        last_exit[d] = t.exit_ns
        per[(d, s)] += 1
        sd = 1 if t.side == "long" else -1
        if t.sl is not None and not (t.sl - t.entry_price) * sd < 0:
            P.append(f"{d} trade sl {t.sl} wrong side of fill {t.entry_price}")
        if t.tp is not None and not (t.tp - t.entry_price) * sd > 0:
            P.append(f"{d} trade tp {t.tp} wrong side of fill {t.entry_price}")
        if t.qty != 1:
            P.append("qty != 1")
        if t.exit_reason == "bars" and (t.exit_ns - t.entry_ns) / 1e9 > p["exit_bars"] * tf * 60 + 120:
            P.append(f"{d} exit_bars={p['exit_bars']} held {(t.exit_ns - t.entry_ns) / 60e9:.1f} min at tf {tf}")
    if fam == "straddle" and p["news_only"]:
        for d, t in trades:
            es = (t.entry_ns - et_ns(d, "00:00")) / 1e9
            if not (50370 <= es < 52200 if d == dt.date(2024, 1, 31) else 30570 <= es < 32400):
                P.append(f"{d} news straddle entry at {es:.0f}s on the wrong day/window")
    if fam in ("gap", "pinbar", "sweep_rev"):
        for d, t in trades:
            if d == dt.date(2024, 3, 11) and fam == "gap":
                P.append(f"{d} gap traded on a roll day")
    for k, n in per.items():
        if n > p["max_tr"]:
            P.append(f"{k} {n} entries > max_tr")
    return P


SESS_ = {"asia": (0, 10800), "london": (10800, 30300), "nyam": (34200, 39600), "mid": (39600, 48600),
         "pm": (48600, 57480), "news": (30570, 32400), "fomc": (50370, 52200)}


def main(argv):
    quiet = "-q" in argv
    fams = [a for a in argv if not a.startswith("-")] or FAMS
    world = build_world()
    bad = 0
    for fam in fams:
        cls = load_cls(fam)
        combos = BASE + COMMON_VAR + FAM_VAR.get(fam, [])
        tot, reasons, probs, t0, zero = 0, collections.Counter(), [], time.time(), 0
        for c in combos:
            st, recs, trades, skips = run(cls, c, world)
            pr = problems(fam, st, recs, trades, skips)
            tot += len(trades)
            zero += not trades
            reasons.update(t.exit_reason for _, t in trades)
            probs += [f"{c}: {x}" for x in pr[:3]]
        if fam == "random":                                   # determinism
            a = run(cls, {}, world)[2]
            b = run(cls, {}, world)[2]
            if [(d, t.entry_ns, t.exit_price) for d, t in a] != [(d, t.entry_ns, t.exit_price) for d, t in b]:
                probs.append("random is not deterministic")
        bad += bool(probs)
        print(f"{fam:14s} combos={len(combos):2d} zero-trade={zero:2d} trades={tot:5d} {dict(reasons)} "
              f"{time.time() - t0:4.0f}s {'OK' if not probs else 'PROBLEMS'}", flush=True)
        for x in probs[: (3 if quiet else 12)]:
            print("    ", x)
    print("ALL OK" if not bad else f"{bad} families with problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
