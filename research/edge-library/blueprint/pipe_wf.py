"""pipe_wf.py -- STAGE 6 AS A 3:1 WALK-FORWARD (the owner, 2026-10-18: "the 3 month is the new build days and the 1 month is the new
unseen days, it should still be 75% in and 25% out of sample"; docs/superpowers/specs/2026-10-18-one-pipeline-two-tags-design.md, addendum).

Every box of the locked table on every day: its build store (2021-09-22 .. 2025-06-30) and the one read of the test days (2025-07-01 ..
latest), joined. Step k picks on months k..k+2 and trades the pick in month k+3; the month steps on by one, so every month from the 4th on
is tested once, by a box picked only on the three months before it.

  months(calendar) -> ["2021-10", ...]          the calendar's months; the first is dropped when it starts after its 7th day
  holds(net, need)  -> bool                     the pipeline's box rows on one window: P3.2 (average trade above $0), P3.3 (`need`
                                                trades or more) and P3.15 (pipe_gates.wr_rr)
  walk(boxes, rows, ms, select, need, today)    -> {"picks": [{month, window, cell | None}], "next": {month, window, cell | None}}
                                                the pick of a window = the MIDDLE of the boxes that hold, by average trade
                                                (pipe_stages._pick: never the best); no box holds = the month stands aside
  stitch(boxes, picks)  -> one box's trade arrays: each month's pick, in that month
  against_random(boxes, picks, pool, seeds, draws, net)   the random tables of the stitched record: each month's pick's exit cell,
                                                drawn day by day from that month's pool (judge.c1_cell), summed over the months
  rows(x, beat, need_total)  -> rows P6.1 (net above $0), P6.2 (beats random), P6.3 (P3.15 on the stitched trades), P6.4 (trades)
  run(spec, lock, build_out, test_out, sess, unit, build_days)   all of the above off the stores (stage 6 and stage 7 call it)

numpy + the package. Locked by tests/test_pipe_wf.py.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np

import judge as J

from . import lines as L
from . import pipe_gates as G
from . import pipe_rules as PR
from . import rules as R
from . import runner as RUN
from . import tables as T

FIELDS = ("date", "entry_ms", "dur_s", "net", "mae")


def _month(ordinals) -> np.ndarray:
    return np.array([dt.date.fromordinal(int(d)).strftime("%Y-%m") for d in ordinals], dtype="<U7")


def months(calendar) -> list:
    """The months of a calendar of ISO session dates, in order; the first is left out when its first session is after the 7th."""
    ms = sorted({d[:7] for d in calendar})
    if ms and min(d for d in calendar if d.startswith(ms[0]))[8:10] > "07":
        ms = ms[1:]
    return ms


def holds(net, need: int) -> bool:
    t = np.asarray(net, np.float64)
    return bool(len(t) >= need and t.mean() > 0 and G.wr_rr(t)["passed"])


def _window_pick(boxes: dict, rows: list, window: list, need: int):
    """The pick on one window (a list of months) -> a cell id or None."""
    from . import pipe_stages as ST                # (stage 6 is in pipe_stages: the pick is its own, read when it is asked for)
    by = {r["id"]: r for r in rows}
    good, wrows = {}, []
    for c, x in boxes.items():
        t = x["net"][np.isin(x["month"], window)]
        if c in by:
            wrows.append({**by[c], "net": float(t.sum()), "trades": len(t)})
            if holds(t, need):
                good[c] = (float(t.mean()),)
    return ST._pick(wrows, good) if good else None


def _after(month: str) -> str:
    y, m = map(int, month.split("-"))
    return f"{y + m // 12}-{m % 12 + 1:02d}"


def walk(boxes: dict, rows: list, ms: list, select: int, need: int, today: str) -> dict:
    """The picks of every step and `next`: the pick on the last `select` months of data before `today`'s month, for the month after them
    (`stale` when that is not today's month: the data ends earlier)."""
    picks = [{"month": ms[k + select], "window": ms[k:k + select], "cell": _window_pick(boxes, rows, ms[k:k + select], need)}
             for k in range(max(0, len(ms) - select))]
    done = [m for m in ms if m < today[:7]][-select:]
    month = _after(done[-1]) if done else today[:7]
    nxt = {"month": month, "window": done, "cell": _window_pick(boxes, rows, done, need) if len(done) == select else None, "stale": month != today[:7]}
    return {"picks": picks, "next": nxt}


def stitch(boxes: dict, picks: list) -> dict:
    parts = [{k: x[k][x["month"] == p["month"]] for k in FIELDS}
             for p in picks if p["cell"] is not None for x in (boxes[p["cell"]],)]
    return {k: (np.concatenate([q[k] for q in parts]) if parts else np.zeros(0)) for k in FIELDS}


def against_random(boxes: dict, picks: list, pool, seeds: list, draws: int, net: float, real: int = 0) -> dict:
    """judge.verdict of the stitched net against its random tables. `pool(xid, month)` = judge.pool_arrays of that exit cell in that month's
    pool; seeds = judge.block_seeds of the draw seed; real = the real seeds behind the pools. A month that stood aside adds nothing to either side."""
    total, short, n = np.zeros(J.BLOCK * len(seeds)), 0, 0
    for p in picks:
        if p["cell"] is None:
            continue
        x = boxes[p["cell"]]
        md = x["date"][x["month"] == p["month"]]
        d, _, s = J.c1_cell(md, pool(p["cell"].rsplit("_", 1)[-1], p["month"]), seeds)
        total, short, n = total + d, short + s, n + len(md)
    d = total[:draws]
    ctl = {"draws": d, "mean": float(d.mean()), "sd": float(d.std(ddof=1)) if len(d) > 1 else 0.0, "p95": float(np.percentile(d, 95)),
           "replicates": len(d), "real_replicates": int(real), "short": int(short)}
    return J.verdict(net, ctl, True)


def rows(x: dict, beat, need_total: int) -> list:
    net, n = float(np.sum(x["net"])), len(x["net"])
    bar = R.need(G.RANDOM)
    wr = {**G.wr_rr(x["net"]), "line": "P6.3"}
    wr["text"] = "P6.3" + wr["text"][len(G.WR_RR):] + " (row P3.15 on the stitched months)"
    p = None if beat is None else beat["p_beat"]
    return [L._row("P6.1", bool(net > 0), net, 0, f"the 3:1 walk-forward made ${net:,.0f} on its test months, one contract after costs (need above $0)"),
            L._row("P6.2", None if p is None else bool(R.meets(G.RANDOM, p) and not beat.get("short")), p, bar,
                   "no random tables" if p is None else f"beats {L._pc(p)} of {beat['replicates']:,} random tables, each month its pick's exit cell "
                   f"(need above {L._pc(bar)})" + (f"; {beat['short']:,} trades had no random match" if beat.get("short") else "")),
            wr,
            L._row("P6.4", bool(n >= need_total), n, need_total, f"{n:,} trades on the test months (need {need_total:,})")]


def _cells(st: dict, ids: list, sess: str, u: dict) -> dict:
    return {c: {k: np.asarray(v) for k, v in J.cellx(st, c, sess, u).items() if k in FIELDS} for c in ids}


def run(spec: dict, lock: dict, build_out, test_out, u: dict, build_days: list, today=None) -> dict:
    """The walk-forward off the stores of a locked idea -> {"months", "picks", "next", "stood_aside", "x" (the stitched trades), "calendar"
    (the test months' session days), "random", "rows", "passed"}. Refused (judge.Refuse): a store the seals refuse, a box a store lacks."""
    h, sess = lock["home"], lock["home"]["session"]
    root, tf = h["market"], str(h["bar"])
    st_b, _ = T._open(Path(build_out), h["key"])
    rng, K = lock["test_range"][root], RUN.test_keys(h["key"], lock["store"], root, tf, sess)
    st_t, _ = T.test_store(test_out, K["table"], rng, lock["hash"])
    pst, pwhere = T.test_store(test_out, K["pool"], rng, lock["hash"])
    ids = list(lock["variants"])
    for s_, w_ in ((st_b, h["key"]), (st_t, K["table"])):
        gone = [c for c in ids if c not in s_["_idx"]]
        if gone:
            raise J.Refuse(f"store {w_} lacks the locked variant {gone[0]}: no walk-forward of this lock")
    b, t = _cells(st_b, ids, sess, u), _cells(st_t, ids, sess, u)
    boxes = {c: {k: np.concatenate([b[c][k], t[c][k]]) for k in FIELDS} for c in ids}
    for x in boxes.values():
        x["month"] = _month(x["date"])
    calendar = sorted({*build_days, *(st_t["meta"].get("calendar") or [])})
    wf = PR.need("walkforward")
    ms = months(calendar)
    got = walk(boxes, J.table(st_b, u), ms, wf["select_months"], wf["window_trades"], today or RUN.clock().date().isoformat())
    x = stitch(boxes, got["picks"])
    tested = {p["month"] for p in got["picks"]}
    c, need = lock["control"], sorted({i.rsplit("_", 1)[-1] for i in ids})
    bpool = T.pool_seeds(Path(build_out), RUN.pool_key(root, tf, spec["exits"]), need)
    tpool = {int(sd): ({"dir": Path(test_out), "key": K["pool"]}, f"s{sd}_") for sd in c["seeds"] if all(f"s{sd}_{q}" in pst["_idx"] for q in need)}
    if len(tpool) < len(c["seeds"]):
        raise J.Refuse(f"control pool {pwhere} holds {len(tpool)} of the {len(c['seeds'])} seeds the lock froze (with every exit cell of the table)")
    first = rng["start"][:7]                        # a month from the first test day on draws from the read's own pool; before it, the build pool
    cache: dict = {}

    def pool(xid, month):
        side = "test" if month >= first else "build"
        if (xid, side) not in cache:
            cache[(xid, side)] = J.pool_arrays(tpool if side == "test" else bpool, sess, xid)
        return cache[(xid, side)]

    keep = J.RULE["draws"]
    try:
        J.RULE["draws"] = int(c["draws"])
        beat = against_random(boxes, got["picks"], pool, J.block_seeds(int(c["draw_seed"]["test"])), int(c["draws"]), float(np.sum(x["net"])),
                              min(len(bpool), len(tpool)))
    finally:
        J.RULE["draws"] = keep
    out = rows(x, beat, PR.need("variant", "region_trades"))
    late = np.array([m >= first for m in _month(x["date"])], bool) if len(x["date"]) else np.zeros(0, bool)
    split = {k: {"net": float(x["net"][m].sum()), "trades": int(m.sum())} for k, m in (("build_days", ~late), ("test_days", late))}
    return {"months": [p["month"] for p in got["picks"]], "picks": got["picks"], "next": got["next"],
            "stood_aside": [p["month"] for p in got["picks"] if p["cell"] is None], "x": x, "split": split,
            "calendar": [d for d in calendar if d[:7] in tested], "random": beat, "rows": out, "passed": all(r["passed"] is True for r in out),
            "stores": {"build": str(Path(build_out) / h["key"]), "test": pwhere}}
