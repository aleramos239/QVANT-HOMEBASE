"""EXAM (2026) price tapes for the allowed units' markets -- nothing else (EDGE_SPEC "FULL OUT-OF-SAMPLE FOR THE SAVED STRATEGIES").
ES / GC replay the tester's tape format; l2sim.build_tapes never takes the EXAM key, so the same worker is repeated here with it:
the tester's own TapeStore code, written under engine/cache/tape only (the archive and the tester's cache are never written).
Only sessions 2026-01-01 .. allowed.json period.end[ROOT] of a market that an ALLOWED unit trades; NQ needs none (ofb_tick).
Restartable: a session that already has a tape is skipped. No price, trade or P&L is printed -- counts only.
  python out/exam2026/build_data.py tapes <ROOT> [workers]"""
import datetime as dt
import json
import sys
import time
from multiprocessing import get_context
from pathlib import Path

W = Path(__file__).resolve().parents[2]
sys.dont_write_bytecode = True
sys.path.insert(0, str(W))
sys.path.insert(0, str(W / "engine"))
import l2sim as S  # noqa: E402

ALLOWED = W / "out" / "exam2026" / "allowed.json"
START = dt.date(2026, 1, 1)


def allowed_roots() -> dict:
    a = json.loads(ALLOWED.read_text())
    roots = {u.split("-")[1] for u in a["units"]}
    return {r: dt.date.fromisoformat(a["period"]["end"][r]) for r in sorted(roots)}


def _one(args) -> tuple:
    iso, root = args
    S.wait_compute_window()
    d = dt.date.fromisoformat(iso)
    S.check_holdout(d, True)                          # the EXAM key, explicit: this file exists for the exam stage only
    if S.hb_tape_path(d, root) is not None:
        return iso, "cached"
    if str(S.REPO) not in sys.path:
        sys.path.append(str(S.REPO))
    from homebase.backtest.tape import OverlayTapeStore
    store = OverlayTapeStore(S.ARCHIVE, S.HB_TAPE, S.OWN_TAPE)
    return iso, ("built" if store.build(root, d) is not None else "no tape")


def tapes(root: str, workers: int = 2) -> dict:
    ends = allowed_roots()
    if root not in ends:
        raise SystemExit(f"{root}: no allowed unit trades it (allowed.json) -- no 2026 tape is built")
    if root == "NQ":
        raise SystemExit("NQ replays the ofb_tick parquet tapes: nothing to build")
    days = [d.isoformat() for d in S.sessions(START, ends[root], root, allow_exam=True)]
    todo = [(iso, root) for iso in days]
    with get_context("spawn").Pool(max(1, min(int(workers), S.MAX_WORKERS))) as p:
        res = p.map(_one, todo, chunksize=4)
    out = {"built": 0, "cached": 0, "no tape": 0}
    for _, what in res:
        out[what] += 1
    return {"root": root, "first": days[0], "last": days[-1], "sessions": len(days), **out,
            "no_tape_days": [iso for iso, what in res if what == "no tape"]}


if __name__ == "__main__":
    t0 = time.monotonic()
    if sys.argv[1] == "tapes":
        print(tapes(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 2), f"{time.monotonic() - t0:.0f} s", flush=True)
