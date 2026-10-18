"""THE FORWARD CHECK of the pipeline's locked boxes on the sessions AFTER the one unseen read (2026-10-17, the owner's audit).

The one read of the unseen days stopped at 2026-09-22 (the last session the locks froze). The sessions after it, to the archive's
latest complete one, were never opened by any read: they are the only clean days left. This reads EACH LOCKED BOX ONCE on them,
exactly as the lock has it (its home store's settings, its default cell, its session; no other cell, no re-tune), beside the
10-seed random-entry pool of the same session on the same days -- the control of line 4.4.

READ-ONLY of the pipeline: no read is claimed in the one-read log, no test.json, no stage card, no ledger row; nothing of the
blueprint's own test range (2025-07-01 .. 2026-09-22) is opened. It writes its table here (forward_check.json, forward_check.md)
and the engine's own caches (swing bars, family caches) for the new days. The engine's switch for the test days (ALLOW_BT) opens
the sessions from 2025-07-01 on; the dates asked are all after the lock's end.

  .venv-research/bin/python out/forward2026/forward_check.py [--end YYYY-MM-DD] [--workers N] [--only name,name]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

W = Path(__file__).resolve().parents[2]              # the edge-library root
sys.path[:0] = [str(W), str(W / "engine")]

import l2sim as S  # noqa: E402
import run_idea as RI  # noqa: E402
import run_menus as RM  # noqa: E402
from blueprint import pipe_store as PS  # noqa: E402
from blueprint import records as REC  # noqa: E402
from blueprint import runner as RUN  # noqa: E402
from blueprint import rules as R  # noqa: E402

HERE = Path(__file__).resolve().parent
LOCKED = ("book", "awaiting_owner")                 # the pipeline ideas whose box was locked and read: the forward check is theirs


def locked_subs() -> list:
    """(idea, sub, status) of every pipeline idea in the book or awaiting the owner."""
    return [(x["name"], x["picked"]["sub"], x["status"]) for x in PS.ideas(None) if x.get("status") in LOCKED and x.get("picked")]


def nets(cells: list, res: list, cut: list, sess: str) -> dict:
    """cell id -> (net, trades) of ONE pass's results, the session's trades only."""
    out = {}
    for c, x, y in zip(cells, cut, cut[1:]):
        r = RM.merge(res[x:y])
        t = [t for t in r["trades"] if S.session_of(t["entry_ms"]) == sess]
        out[c["id"]] = (float(sum(t_["net"] for t_ in t)), t)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2026-09-23")
    ap.add_argument("--end", default=None, help="the last session read (default: the latest tape)")
    ap.add_argument("--workers", type=int, default=None)
    ap.add_argument("--only", default=None, help="idea names, comma-separated")
    a = ap.parse_args(argv)
    sw = S.ALLOW_BT
    ideas_root = PS.ideas_root(None)
    seeds = list(range(1, R.template("control")["seeds"] + 1))
    blocks = RUN._blocks()
    n = RM.auto_workers(RUN.default_workers() if a.workers is None else a.workers)
    rows, pools = [], {}
    want = set(a.only.split(",")) if a.only else None
    for idea, sub, status in locked_subs():
        if want and idea not in want:
            continue
        t0 = time.monotonic()
        lock = REC._json(REC._carded(sub, ideas_root) / "lock.json")
        test = REC._json(REC._carded(sub, ideas_root) / "test.json") or {}
        h, cell = lock["home"], lock["default"]
        sp = RUN.checked(REC.engine(lock["spec"], lock["plan"], lock["store"])[0])
        u = next(x for x in RI.spec_units(sp) if x["key"] == h["key"])
        root, tf, sess = u["root"], u["tf"], h["session"]
        row = {"idea": idea, "status": status, "sub": sub, "box": cell, "market": root, "session": sess, "bar": str(tf),
               "unseen_box_net": (test.get("gates") or {}).get("box"), "unseen_sessions": (test.get("days") or {}).get("sessions"),
               "unseen_beat": next((x.get("number") for x in test.get("lines", []) if x.get("line") == "4.4"), None)}
        if blocks.reads(u["filter"], blocks.L2_BLOCKS):
            rows.append({**row, "note": "a Level 2 filter: not read here (the Level 2 table ends before these days)"})
            continue
        end = a.end or max(d.isoformat() for d in S.sessions(a.start, dt.date.today(), root, allow_holdout=sw))
        days = [d.isoformat() for d in S.sessions(a.start, end, root, allow_holdout=sw)]
        if not days:
            rows.append({**row, "note": f"no session of {root} in {a.start} .. {end}"})
            continue
        A, B = S._date(days[0]), S._date(days[-1])
        # the engine's caches for the new days, as the one read makes them (runner.run_test)
        for rt in RUN.bar_roots(root, sp["family"], u["filter"]):
            RUN._levels().build_bars_cache(rt, (A, B), n, allow_holdout=sw)
        if u["filter"] and blocks.reads(u["filter"], ("volume", "rvol")):
            blocks.build_minvol(root, (A, B), n, allow_holdout=sw)
        if getattr(blocks.WRAPPED[sp["family"]], "prepare", None):
            RUN.prepare_family(sp["family"], root, (A, B), n, sw)
        base = dict(getattr(blocks.WRAPPED[sp["family"]], "SCREEN_RUN", {}))
        grid = [c for c in u["grid"] if c["id"] == cell]
        part = RUN._part(f"fwd-{sub}", "filter" if u["filter"] else "unit", root, tf, grid, [sess], None, {}, sp["family"], base, u["filter"])
        specs, cut = [], [0]
        for one in part["runs"]:
            specs += one
            cut.append(len(specs))
        res = S.run_many(specs, A, B, days=days, root=root, workers=n, allow_holdout=sw, **RUN._engine(part["kw"]))
        net, trades = nets(grid, res, cut, sess)[cell]
        # the random-entry pool of the same session and days (line 4.4's control), once per market / bar / session / table
        pk = (root, str(tf), sess, sp["exits"])
        if pk not in pools:
            pgrid = RUN._seeded(RUN.c1_grid_open if sp["exits"] == RUN.OPEN else RUN.c1_grid, seeds, root, str(tf))
            ppart = RUN._part(f"fwd-pool-{root}-tf{tf}-{sess}", "pool", root, tf, pgrid, [sess], None, {})
            pspecs, pcut = [], [0]
            for one in ppart["runs"]:
                pspecs += one
                pcut.append(len(pspecs))
            pres = S.run_many(pspecs, A, B, days=days, root=root, workers=n, allow_holdout=sw, **RUN._engine(ppart["kw"]))
            pools[pk] = {k: v[0] for k, v in nets(pgrid, pres, pcut, sess).items()}
        pool = pools[pk]
        same_exit = [v for k, v in pool.items() if k.split("_", 1)[1] == cell.split("-", 1)[-1] or k.endswith("_" + cell)]
        wins = sum(t["net"] > 0 for t in trades)
        row.update(start=days[0], end=days[-1], sessions=len(days), trades=len(trades), net=round(net, 2),
                   win_rate=round(wins / len(trades), 4) if trades else None, avg_trade=round(net / len(trades), 2) if trades else None,
                   per_session=round(net / len(days), 2), unseen_per_session=(round(row["unseen_box_net"] / row["unseen_sessions"], 2)
                                                                          if row["unseen_box_net"] is not None and row["unseen_sessions"] else None),
                   beat_random=round(sum(net > v for v in pool.values()) / len(pool), 4), random_tables=len(pool),
                   beat_same_exit=round(sum(net > v for v in same_exit) / len(same_exit), 4) if same_exit else None,
                   random_median=round(float(sorted(pool.values())[len(pool) // 2]), 2), seconds=round(time.monotonic() - t0))
        rows.append(row)
        print(f"{idea:34} {cell:24} {len(days)} d  trades {len(trades):3}  net {net:9.2f}  beat {row['beat_random']:.0%} of {len(pool)}  ({row['seconds']} s)", flush=True)
    out = {"utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "start": a.start, "rows": rows}
    (HERE / "forward_check.json").write_text(json.dumps(out, indent=1))
    (HERE / "forward_check.md").write_text(table(rows))
    print(table(rows))
    return 0


def pct(v) -> str:
    return "" if v is None else f"{100 * v:.0f}"


def table(rows: list) -> str:
    head = "| idea | status | box | session | days | trades | net | win % | $/session (unseen) | beats random | note |\n|---|---|---|---|---|---|---|---|---|---|---|"
    lines = [head] + [f"| {r['idea']} | {r['status']} | {r['box']} | {r['session']} {r['bar']}m | {r.get('sessions', '')} | {r.get('trades', '')} | "
                      f"{r.get('net', '')} | {pct(r.get('win_rate'))} | {r.get('per_session', '')} ({r.get('unseen_per_session', '')}) | "
                      + ("" if r.get("beat_random") is None else f"{pct(r['beat_random'])} % of {r['random_tables']}") + f" | {r.get('note', '')} |" for r in rows]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
