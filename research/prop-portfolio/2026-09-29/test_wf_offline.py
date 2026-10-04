"""wf_offline: window logic (no leakage) and the walk-forward search reproduces the pass-2 full-window pick."""
import datetime as dt
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import evalcore as E     # noqa: E402


def _W():
    """Lazy import: wf_offline registers the LucidPro firms in evalcore.FIRMS (would change other tests' firm loops)."""
    import wf_offline
    return wf_offline


def test_windows_no_leakage():
    W = _W()
    cal = np.array([d.toordinal() for d in (dt.date(2021, 9, 22) + dt.timedelta(days=i) for i in range(1200)) if d.weekday() < 5])
    Wt, tests, oos = W.windows(cal)
    S = len(cal) - E.H_EVAL + 1
    assert Wt.shape == (S, len(W.QUARTERS))
    for j, (y, q) in enumerate(W.QUARTERS):
        a, b, lo = W.q_bounds(y, q)
        tr = np.flatnonzero(Wt[:, j] > 0)
        assert abs(Wt[:, j].sum() - 1) < 1e-5      # the csv keeps 6 digits
        assert cal[tr].min() >= lo and cal[tr + E.H_EVAL - 1].max() < a          # attempts end before the test quarter
        assert (cal[tests[j]] >= a).all() and (cal[tests[j]] < b).all()
    assert cal[oos[0]] >= dt.date(2022, 7, 1).toordinal()


def test_full_window_pick_matches_pass2():
    import csv
    W = _W()
    rows = [r for r in csv.DictReader((W.OUT / "a3p2_rules.csv").open()) if r["firm"] == "lucid" and r["model"] == "eod"
            and r["key"] == "hm-orb-tf5#10" and r["sess"] == "mid"]
    if not rows:
        return
    grid = [g for g in W.gather() if g[0] == "hm-orb-tf5" and g[1] == "mid"][0]
    o = W.task((grid[0], grid[1], "lucid", grid[2], 0))[0]
    f = o["reps"][0]["eod"]["full"]
    assert o["members"][f["cfg"]] == "hm-orb-tf5#10" and abs(f["p5"] - float(rows[0]["st_p5"])) < 1e-5      # the csv keeps 6 digits


def test_zz_restore_firms():
    for k in ("lucidpro", "lucidpro_nodll"):
        E.FIRMS.pop(k, None)
