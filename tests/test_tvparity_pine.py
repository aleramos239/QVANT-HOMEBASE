"""The P3 Pine twin (tools/pine/hb_parity_p3.pine) against the Homebase studies it mirrors, on made-up bars.

The twin runs through the chart page's own Pine Worker (tools/pine/parity.mjs loadWorker, PineTS from ~/.homebase/pine,
outside the repo); each plot is then compared with the study cell by cell in BOTH directions (parity.mjs itself skips the
cells the CSV leaves empty). Skipped where node or the runtime is not installed.

The bars sit inside 13:30-20:00 UTC of each weekday: PineTS's timeframe.change("D") flips at UTC midnight and Homebase's
session at 18:00 ET, and those two only agree while no bar is between 22:00 and 24:00 UTC."""
from __future__ import annotations

import datetime as dt
import json
import os
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from homebase.charts.bars import Bar
from homebase.charts.session import session_date
from homebase.paths import repo_root
from tools import tvparity as tp

PINE = Path(repo_root(), "tools", "pine")
PINE_DIR = Path(os.environ.get("HOMEBASE_PINE_DIR") or Path.home() / ".homebase" / "pine")
pytestmark = pytest.mark.skipif(
    shutil.which("node") is None or not (PINE_DIR / "runtime" / "node_modules" / "pinets").exists(),
    reason="node or the Pine runtime (~/.homebase/pine/runtime) is not installed")

RUN = """import { loadWorker } from %s;
import { readFileSync, writeFileSync } from 'node:fs';
const [pine, barsPath, tf, outPath] = process.argv.slice(2);
const w = loadWorker();
w.post({ type: 'init', source: readFileSync(pine, 'utf8'), root: 'NQ', tf_s: +tf, tick_size: 0.25, point_value: 20,
         bars: JSON.parse(readFileSync(barsPath, 'utf8')), maxBars: 20000 });
const r = await w.next(170000);
writeFileSync(outPath, JSON.stringify(r.type === 'result' ? { plots: r.plots } : { error: r.message }));
process.exit(0);
"""


def sessions(n, start=dt.date(2026, 9, 1)):
    d, out = start, []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += dt.timedelta(days=1)
    return out


def make_bars(n_sessions, per, step_s, seed, shape):
    """Bars on a 0.25 grid from 13:30Z of each weekday. shape(rng, i, px) -> (open move, range) per bar."""
    rng, px, out, i = random.Random(seed), 20000.0, [], 0
    for d in sessions(n_sessions):
        t0 = int(dt.datetime(d.year, d.month, d.day, 13, 30, tzinfo=dt.timezone.utc).timestamp() * 1000)
        for k in range(per):
            move, rng_pts = shape(rng, i, px)
            o = px
            c = round((o + move) * 4) / 4
            h = round((max(o, c) + rng_pts * rng.random()) * 4) / 4
            l = round((min(o, c) - rng_pts * rng.random()) * 4) / 4
            t = t0 + k * step_s * 1000
            out.append(Bar(t=t, session=session_date(t).isoformat(), o=o, h=h, l=l, c=c, v=100 + (i % 7), closed=True))
            px, i = c, i + 1
    return out


def pine_plots(tmp_path, pine_file, bars, tf_s):
    (tmp_path / "bars.json").write_text(json.dumps([{"ms": b.t, "o": b.o, "h": b.h, "l": b.l, "c": b.c, "v": b.v} for b in bars]))
    js = tmp_path / "run.mjs"
    js.write_text(RUN % json.dumps((PINE / "parity.mjs").as_uri()))
    p = subprocess.run(["node", str(js), str(PINE / pine_file), str(tmp_path / "bars.json"), str(tf_s), str(tmp_path / "out.json")],
                       capture_output=True, text=True, timeout=240)
    assert p.returncode == 0, p.stderr
    out = json.loads((tmp_path / "out.json").read_text())
    assert "error" not in out, out
    return {t: {pt["time"]: pt["value"] for pt in pts} for t, pts in out["plots"].items()}


def mismatches(plots, bars, key, fields, ignore_first=0):
    """{title: (n cells that differ, first differing bar index, the study value, the twin's)} for every field of the study."""
    vals = tp.run(key, bars, 0.25)
    bad, seen = {}, 0
    for fld in fields:
        title = f"tv|{key}|{fld}"
        got = plots[title]
        diff = []
        for i, (b, v) in enumerate(zip(bars, vals)):
            a, g = tp.field(v, fld), got.get(b.t)
            g = None if g is None or g != g else float(g)
            if i >= ignore_first and not tp.same(a, g, 6):
                diff.append((i, a, g))
            seen += a is not None
        if diff:
            bad[title] = (len(diff), *diff[0])
    return bad, seen


def impulses(rng, i, px):
    """Quiet bars with an impulse of several ranges every so often: gaps of every size, some under the 0.25 x ATR floor."""
    if rng.random() < 0.08:
        return rng.choice((-1, 1)) * rng.uniform(8, 60), rng.uniform(1, 6)
    return rng.uniform(-3, 3), rng.uniform(0.5, 3)


def test_the_p3_fvg_twin_sizes_a_gap_with_the_atr_through_the_bar_before_it_like_homebase(tmp_path):
    bars = make_bars(14, 78, 300, 5, impulses)
    plots = pine_plots(tmp_path, "hb_parity_p3.pine", bars, 300)
    bad, seen = mismatches(plots, bars, "fvg:0.25:14", ("uh", "ul", "dh", "dl"))
    assert seen > 100, "the made-up bars must form gaps, or this test proves nothing"
    assert not bad, bad


def tie_shape(rng, i, px):
    return rng.uniform(-1.5, 1.5), rng.uniform(0.25, 1.5)


def test_the_p3_swing_twin_has_no_pivot_where_an_equal_value_stands_within_the_n_bars_before_it(tmp_path):
    bars = make_bars(2, 390, 60, 3, tie_shape)                      # 1m bars, two sessions
    for j in (270, 300):                                            # two equal highs 30 bars apart: no swing, either of them
        bars[j].h = 21000.0
    for j in (120, 150):                                            # and two equal lows
        bars[j].l = 19000.0
    plots = pine_plots(tmp_path, "hb_parity_p3.pine", bars, 60)
    for key, flds in (("swing:50", ("hi", "lo")), ("equal:50:10", ("hi", "lo")),
                      ("rswing:50", ("hi", "lo", "mid", "ote1", "ote2", "dir"))):
        bad, _ = mismatches(plots, bars, key, flds)
        assert not bad, (key, bad)
    assert tp.field(tp.run("swing:50", bars, 0.25)[-1], "hi") != 21000.0     # the tie bar really is no swing for Homebase


def test_the_p3_twin_still_agrees_with_homebase_on_tie_heavy_bars(tmp_path):
    bars = make_bars(8, 78, 300, 11, tie_shape)                     # 0.25 grid: equal highs and lows are common
    plots = pine_plots(tmp_path, "hb_parity_p3.pine", bars, 300)
    for key, flds in (("swing:50", ("hi", "lo")), ("equal:50:10", ("hi", "lo")),
                      ("rswing:50", ("hi", "lo", "mid", "ote1", "ote2", "dir"))):
        bad, seen = mismatches(plots, bars, key, flds)
        assert not bad, (key, bad)
        assert seen > 0, key
