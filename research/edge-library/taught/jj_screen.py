"""jj_screen -- MANY VERSIONS OF JJ'S RULE OVER THE BUILD DAYS IN ONE PASS (the owner, 2026-10-19: "work on the strategy until you get the
minimum 40 % win rate in sample ... there's many different ways to trade it ... I'm looking for the extremely high trade frequency").

Each variant is a pre-registered reading of his words (families/jj_fair.py: entry disp / bos / both, fair open / vwap / adapt, wick,
room, swing, end), all at the same 25 / 38 cell, 1 NQ, the engine's costs (1 tick of slippage, $4 a round turn). One tape load a day
serves every variant (the taught lane would reload it per sheet). In-sample: the build days only (2021-09-22 .. 2025-06-30). No
control, no pick: a screen, so that the owner sees every version side by side; the one he picks goes through `bp.py taught run`
(with its random control) and the 3:1 walk-forward once.

Run: .venv-research/bin/python research/edge-library/taught/jj_screen.py [--variants FILE.json] [--workers 3] [--out FILE.json]
     [--days N]  (N = the first N build days, a smoke)"""
from __future__ import annotations

import argparse
import itertools
import json
import multiprocessing as mp
import os
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve()
ENGINE = HERE.parents[1] / "engine"
sys.path.insert(0, str(ENGINE))
sys.path.insert(0, str(HERE.parents[1]))

import l2sim as S                                              # noqa: E402

BASE = {"hold_to": "day", "tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 25.0, "tgt_r": 38.0 / 25.0, "max_tr": 20}
ROOT = "NQ"
_DAILY = None


def grid() -> dict:
    """Batch 1 (pre-registered 2026-10-19): entry x fair x wick x room, opp on, swing 1, max_loss 3, end 11:00."""
    out = {}
    for e, f, w, room in itertools.product(("disp", "bos", "both"), ("open", "vwap", "adapt"), ("on", "off"), (30.0, 15.0)):
        if e == "bos" and w == "off":
            continue                                           # the wick test is the displacement's
        out[f"{e}-{f}-wick_{w}-room{int(room)}"] = {"entry": e, "fair": f, "wick": w, "min_room": room}
    return out


def _init():
    global _DAILY
    import families  # noqa: F401  (registers every family, jj_fair among them)
    _DAILY = S.load_daily(ROOT, allow_holdout=S.ALLOW_BP)


def _day(args):
    d, variants = args
    from families import jj_fair as JJ
    tape = S.load_tape(d, ROOT, allow_holdout=S.ALLOW_BP)
    if tape is None:
        return d, {}
    daily = [x for x in _DAILY if x["date"] < d]            # prior days only (a reviewer caught the whole list being handed over: the
    out = {}                                                 # Template reads daily[-1] as the prior day; only cgap read it, 2026-10-19)
    for k, v in variants.items():
        st = JJ.JjFair({**BASE, **v})
        res = S.run_session(st, tape, daily=daily, on_error="raise")
        out[k] = [(t["date"], float(t["net"]), t["side"], int(t.get("entry_ms") or 0), str(t.get("exit_reason") or "")) for t in res.trades]
    return d, out


def summarise(trades: list, n_days: int) -> dict:
    n = len(trades)
    if not n:
        return {"trades": 0}
    wins = [t for t in trades if t[1] > 0]
    gp = sum(t[1] for t in wins)
    gl = -sum(t[1] for t in trades if t[1] <= 0)
    net = gp - gl
    by_year = {}
    for t in trades:
        y = t[0][:4]
        by_year.setdefault(y, [0, 0])
        by_year[y][0] += 1
        by_year[y][1] += t[1] > 0
    tgt = sum(1 for t in trades if len(t) > 4 and t[4] in ("tp", "target"))
    stp = sum(1 for t in trades if len(t) > 4 and t[4] in ("sl", "stop"))
    nets = [t[1] for t in trades]
    mean = net / n
    sd = (sum((x - mean) ** 2 for x in nets) / max(n - 1, 1)) ** 0.5
    return {"trades": n, "per_day": n / n_days, "win": len(wins) / n, "net": net, "avg": mean, "se_avg": sd / n ** 0.5,
            "bracket_win": tgt / (tgt + stp) if tgt + stp else None, "time_exits": n - tgt - stp if tgt + stp else None,
            "pf": (gp / gl) if gl else None, "win_by_year": {y: round(w / c, 3) for y, (c, w) in sorted(by_year.items())}}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--variants")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--out")
    ap.add_argument("--days", type=int)
    a = ap.parse_args(argv)
    variants = {k: v for k, v in json.loads(Path(a.variants).read_text()).items() if not k.startswith("_")} if a.variants else grid()
    days = [d.isoformat() for d in S.sessions(*S.period(S.ALLOW_BP), ROOT, allow_holdout=S.ALLOW_BP)]
    if a.days:
        days = days[: a.days]
    t0 = time.time()
    per = {k: [] for k in variants}
    with mp.get_context("fork").Pool(a.workers, initializer=_init) as pool:
        for i, (d, res) in enumerate(pool.imap_unordered(_day, [(d, variants) for d in days], chunksize=4), 1):
            for k, tr in res.items():
                per[k].extend(tr)
            if i % 100 == 0:
                print(f"  {i} of {len(days)} days, {time.time() - t0:.0f} s", file=sys.stderr, flush=True)
    rows = {k: {**summarise(sorted(v), len(days)), "settings": variants[k]} for k, v in per.items()}
    print(f"{len(days)} build days {days[0]} .. {days[-1]}, 1 NQ after costs. 'win' = net > 0 (time exits included); 'tgt/stp' = targets / "
          f"(targets + stops), the bracket's own win rate; break-even ~40.4 % at 25 / 38, ~41.6 % at 50 / 76; +-SE = one standard error of the average trade")
    print(f"{'variant':34} {'trades':>6} {'/day':>5} {'win':>6} {'tgt/stp':>7} {'avg':>7} {'+-SE':>5} {'net':>9} {'PF':>5}  win by year")
    for k, r in sorted(rows.items(), key=lambda kv: -(kv[1].get("win") or 0)):
        if not r["trades"]:
            print(f"{k:34} {0:>6}")
            continue
        yrs = " ".join(f"{y[2:]}:{int(round(100 * w))}" for y, w in r["win_by_year"].items())
        bw = f"{100 * r['bracket_win']:>6.1f}%" if r.get("bracket_win") is not None else f"{'':>7}"
        print(f"{k:34} {r['trades']:>6} {r['per_day']:>5.1f} {100 * r['win']:>5.1f}% {bw} {r['avg']:>7.0f} {r['se_avg']:>5.0f} {r['net']:>9,.0f} "
              f"{(r['pf'] or 0):>5.2f}  {yrs}")
    if a.out:
        Path(a.out).write_text(json.dumps({"days": len(days), "first": days[0], "last": days[-1], "cell": "25/38", "rows": rows,
                                           "trades": {k: v for k, v in per.items()}}, indent=0))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
