"""LOCK of THE TAUGHT LANE (blueprint/taught.py; `bp.py taught check | run | show | list`): a rule run EXACTLY AS A VIDEO TAUGHT IT --
its own entry rule with its own settings, ONE exit cell with its own stop and target in points, its own trade cap -- with a
small neighbourhood (the stop and the target at 75 / 100 / 125 %: nine cells) and the pipeline's honest controls. No heat map,
no pick, no search.

1. THE SHEET (`check`, nothing is run): every refusal names its part -- an unknown family or setting, a value outside the
   family's range, a market the family does not trade, a pass it never trades, a stop that is not a tick multiple, a target
   past the engine's limit, neighbours that fall on one another, a clock window the engine cannot cut, a sheet that does not
   say what was left out. It prints what runs (the "Run" lines) beside the taught list and the not_run list; a sheet whose
   not_run is empty says so in words. The two sheets of the conti video on file are whole.
2. THE CELLS: the taught cell and its eight neighbours, stop x {0.75, 1, 1.25} crossed with target x {0.75, 1, 1.25} rounded to
   the tick, in a fixed order, the centre in the middle; every engine input is the sheet's own (`pts`, the cap, the side, the
   family's settings), hold_to day, one run per bar.
3. THE SEAL: a day from 2025-07-01 on is refused before anything is read; a store whose range is not inside the build days is
   refused by the reader.
4. THE READS, on hand-made stores (no tape): per-cell metrics, the lines of the pipeline's own functions on the centre box, the
   neighbours, the random line against the lane's own control per session, the steadiness rows marked, one verdict line.
5. A SMALL REAL RUN on named build days (2 workers at most): stores for the unit and the controls per bar, a result file, the
   text, a second run that does no work, a changed sheet under the same name refused.

  pytest tests/test_taught.py -q
"""
from __future__ import annotations

import contextlib
import copy
import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

import numpy as np
import pytest

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import judge as J  # noqa: E402
import l2sim as S  # noqa: E402
import library as LB  # noqa: E402
import run_menus as RM  # noqa: E402
from blueprint import cli  # noqa: E402
from blueprint import runner as RUN  # noqa: E402
from blueprint import taught as TT  # noqa: E402

SHEETS = W / "taught"
SAT = dt.datetime(2026, 10, 3, 11, 0, tzinfo=S.ET)           # a Saturday: no desk hours, no no-start window
DAYS = ["2022-03-15", "2022-09-14", "2023-03-22", "2024-05-14", "2025-06-30"]       # five build days, the last one the last build day

SHEET = {
    "name": "conti_vwap_pullback_long",
    "source": {"video": "wm4A6qo0g3I", "title": "Ex-Market Maker Shows the Exact VWAP Setup", "channel": "IQCapital", "url": "https://youtu.be/wm4A6qo0g3I"},
    "market": "NQ", "bars": ["5", "15"], "sessions": ["nyam", "mid", "pm"], "dir": "long",
    "entry": {"family": "vwap_trend_pull", "settings": {"x": 0.1, "max_loss": 2}, "words": "long when the close is above a rising VWAP and the price is up 0.1 % on the hour"},
    "exits": {"stop_pts": 80, "target_pts": 40, "exit_bars": 0, "max_trades": 4},
    "taught": ["[14:18] trend is true when the close is above VWAP, VWAP is higher than 15 minutes ago and the price is up 0.1 % on the hour",
               "[24:26] enter the first red candle at the next open", "[25:00] stop 80 points, target 40 points"],
    "not_run": ["the flat time is 15:55 in the video, 15:58 here"],
    "control": "random",
}


def sheet(**more) -> dict:
    out = copy.deepcopy(SHEET)
    for k, v in more.items():
        if v is None:
            out.pop(k, None)
        elif isinstance(v, dict) and isinstance(out.get(k), dict) and k not in ("source",):
            out[k] = {**out[k], **v}
        else:
            out[k] = v
    return out


def refused(s, *words):
    """check() says no, and every word is in the reasons."""
    r = TT.check(s)
    assert r["ok"] is False, r["text"]
    said = " ".join(r["problems"]).lower()
    for w in words:
        assert w.lower() in said, (w, r["problems"])
    return r


# ================================================================ 1. the sheet

def test_the_two_sheets_on_file_are_whole():
    names = sorted(p.name for p in SHEETS.glob("*.json"))
    assert "conti_vwap_pullback_long.json" in names and "conti_vwap_pullback_short.json" in names
    for n in ("conti_vwap_pullback_long", "conti_vwap_pullback_short"):
        r = TT.check(SHEETS / f"{n}.json")
        assert r["ok"], r["text"]
        p = r["plan"]
        assert p["name"] == n and p["family"] == "vwap_trend_pull" and p["market"] == "NQ" and p["bars"] == ["5", "15"]
        assert p["exits"]["stop_pts"] == 80.0 and p["exits"]["target_pts"] == (40.0 if n.endswith("long") else 50.0)
        assert p["dir"] == ("long" if n.endswith("long") else "short") and p["not_run"] and p["taught"]


def test_a_good_sheet_prints_what_runs_beside_what_was_taught():
    r = TT.check(sheet())
    assert r["ok"] is True and r["problems"] == [] and r["command"] == "taught check" and r["name"] == SHEET["name"]
    t = r["text"]
    for part in ("TAUGHT", "RUN", "NOT RUN", "[14:18] trend is true", "vwap_trend_pull", "x 0.1", "max_loss 2", "stop 80 points", "target 40 points",
                 "tgt_r 0.5", "at most 4 trades", "long only", "5 and 15", "nyam mid pm", "the flat time is 15:55"):
        assert part in t, part
    assert "nothing was left out" not in t
    p = r["plan"]
    assert p["effective"]["x"] == 0.1 and p["effective"]["max_loss"] == 2 and p["tick"] == 0.25


def test_an_empty_not_run_says_so_in_words():
    r = TT.check(sheet(not_run=[]))
    assert r["ok"] and "nothing was left out: the person who wrote the sheet says so" in r["text"]
    assert r["plan"]["nothing_left_out"] is True
    assert TT.check(sheet())["plan"]["nothing_left_out"] is False


def test_the_trade_cap_is_said_to_be_a_cap_of_each_pass():
    """The family's day is ONE session pass: three passes mean up to three times the cap. The lane says it beside the Run lines."""
    t = TT.check(sheet())["text"]
    assert "each pass" in t and "12" in t                       # 4 trades x 3 passes
    one = TT.check(sheet(sessions=["nyam"]))["text"]
    assert "up to 12" not in one


def test_every_refusal_names_its_part():
    refused(sheet(name="Conti Long"), "name")
    refused(sheet(name="a__b"), "name")
    refused(sheet(source=None), "source")
    refused(sheet(taught=[]), "taught")
    refused(sheet(taught=["", "x"]), "taught")
    refused(sheet(not_run=None), "not_run")
    refused(sheet(control="shuffle"), "control", "random")
    refused({**sheet(), "extra": 1}, "extra")
    refused(sheet(market="XX"), "market")
    refused(sheet(dir="sideways"), "dir")
    refused(sheet(bars=[]), "bars")
    refused(sheet(bars=["7"]), "bars", "7")
    refused(sheet(sessions=["asia"]), "asia", "vwap_trend_pull")          # the family never trades there
    refused(sheet(sessions=["nyam", "lunch"]), "lunch")
    refused(sheet(sessions=None), "sessions", "window")
    refused(sheet(entry={"family": "no_such_family"}), "no_such_family", "needs a rule that: long when the close is above a rising VWAP")
    refused(sheet(entry={"settings": {"nope": 1}}), "nope", "vwap_trend_pull")
    refused(sheet(entry={"settings": {"x": 9.0}}), "x", "5")                # outside the family's range 0 .. 5
    refused(sheet(entry={"settings": {"max_loss": 1.5}}), "max_loss", "whole")
    refused(sheet(entry={"settings": {"max_tr": 2}}), "max_tr")            # an exit setting: it belongs under exits
    refused(sheet(entry={"words": ""}), "words")


def test_exit_numbers_are_positive_tick_multiples_inside_the_engine():
    refused(sheet(exits={"stop_pts": 0}), "stop")
    refused(sheet(exits={"stop_pts": 80.1}), "stop", "tick", "0.25")
    refused(sheet(exits={"target_pts": -5}), "target")
    refused(sheet(exits={"stop_pts": None, "stop_ticks": None}), "stop")
    refused(sheet(exits={"stop_ticks": 320}), "stop_pts", "stop_ticks")    # both given
    refused(sheet(exits={"stop_pts": 1, "target_pts": 100}), "target", "20")     # target / stop = 100 > 20
    refused(sheet(exits={"max_trades": 0}), "max_trades")
    refused(sheet(exits={"exit_bars": -1}), "exit_bars")
    refused(sheet(exits={"exit_bars": 3, "exit_minutes": 30}), "exit_bars", "exit_minutes")
    refused(sheet(exits={"exit_minutes": 40}), "exit_minutes", "15")         # 40 minutes is not a multiple of 15
    refused(sheet(exits={"stop_pts": 0.25}), "stop", "two ticks")
    refused(sheet(exits={"stop_pts": 0.5, "target_pts": 1}), "neighbour")     # 75 % and 125 % of 0.5 fall on the same tick
    refused(sheet(exits={"bogus": 1}), "bogus")


def test_ticks_and_points_are_the_same_number():
    a = TT.check(sheet(exits={"stop_pts": None, "target_pts": None, "stop_ticks": 320, "target_ticks": 160}))
    assert a["ok"], a["text"]
    assert a["plan"]["exits"]["stop_pts"] == 80.0 and a["plan"]["exits"]["target_pts"] == 40.0 and a["plan"]["exits"]["stop_ticks"] == 320
    assert [c["id"] for c in a["plan"]["cells"]] == [c["id"] for c in TT.check(sheet())["plan"]["cells"]]
    m = TT.check(sheet(exits={"exit_bars": None, "exit_minutes": 30}))
    assert m["ok"] and m["plan"]["exits"]["exit_bars"] == {"5": 6, "15": 2}      # minutes become bars of each bar size


def test_windows_are_honoured_by_a_pass_or_by_the_family_or_refused():
    ok = TT.check(sheet(window="10:30-15:30"))                  # the family's own written entry window
    assert ok["ok"], ok["text"]
    assert "family's own entry window" in ok["text"] and ok["plan"]["window"]["text"] == "10:30-15:30"
    derived = TT.check(sheet(sessions=None, window="10:30-15:30"))        # the passes are the ones that cover it
    assert derived["ok"] and derived["plan"]["sessions"] == ["nyam", "mid", "pm"]
    refused(sheet(window="10:45-15:00"), "window", "10:45")
    refused(sheet(window="09:30-11:00", sessions=None), "window", "10:30")          # the family never enters before 10:30
    refused(sheet(window="late"), "window")
    refused(sheet(window="10:30-15:30", sessions=["nyam"]), "window", "cover")      # the passes do not reach 15:30
    # a family without a window of its own: exactly the named passes, or refused
    orb = {"entry": {"family": "orb", "settings": {}, "words": "the break of the opening range"}, "sessions": None, "exits": {"stop_pts": 20, "target_pts": 40}}
    one = TT.check(sheet(window="09:30-11:00", **orb))
    assert one["ok"], one["text"]
    assert one["plan"]["sessions"] == ["nyam"] and "session passes nyam" in one["plan"]["window"]["by"]
    refused(sheet(window="09:45-11:00", **orb), "window", "cut")


def test_a_structure_stop_is_the_familys_level_or_refused():
    """A family that never hands the engine a structure level would be stopped at stop_val x ATR: refused, in words."""
    for fam in ("vwap_trend_pull", "sfp"):
        assert TT.passes_structure(fam) is False, fam
    for fam in ("open_fvg", "fvg", "orb_confirm", "pullback"):
        assert TT.passes_structure(fam) is True, fam
    s = sheet(exits={"stop_pts": None, "target_pts": None, "stop": "struct", "target_r": 2.0})
    refused(s, "struct", "vwap_trend_pull", "never passes a structure level")
    fvg = {"entry": {"family": "open_fvg", "settings": {"oc_min": "15"}, "words": "the gap through the first candle"}, "bars": ["5"], "sessions": ["nyam"], "dir": "both"}
    ok = TT.check(sheet(exits={"stop_pts": None, "target_pts": None, "stop": "struct", "target_r": 2.0, "max_trades": 1}, **fvg))
    assert ok["ok"], ok["text"]
    c = ok["plan"]["cells"]
    assert [x["id"] for x in c] == ["struct-r1p5", "struct-r2", "struct-r2p5"] and [x["centre"] for x in c] == [False, True, False]
    p = ok["plan"]["engine"]["5"][1]["params"]
    assert p == {"oc_min": "15", "tf": "5", "sess": "all", "dir": "both", "max_tr": 1, "exit_bars": 0, "stop_mode": "struct", "tgt_r": 2.0}
    assert "structure level" in ok["text"] and "ONE session pass" in ok["text"]
    base = {"stop": "struct", "stop_pts": None, "target_pts": None, "target_r": 2.0}
    refused(sheet(exits={**base, "stop_pts": 80}, **fvg), "stop_pts", "target_r")
    refused(sheet(exits={**base, "target_r": None}, **fvg), "target_r")
    refused(sheet(exits={**base, "target_r": 17}, **fvg), "target_r", "20")        # 125 % of 17 is over the engine's 20
    refused(sheet(exits={**base, "stop": "wide"}, **fvg), "stop", "struct")
    refused(sheet(exits={"target_r": 2.0}), "target_r", "struct")           # a target in R without a structure stop


def test_neighbours_are_a_fixed_rule():
    c = TT.check(sheet())["plan"]["cells"]
    assert len(c) == 9 and [x["centre"] for x in c].count(True) == 1 and c[4]["centre"]
    assert [x["stop_pts"] for x in c] == [60.0] * 3 + [80.0] * 3 + [100.0] * 3
    assert [x["target_pts"] for x in c] == [30.0, 40.0, 50.0] * 3
    assert [round(x["tgt_r"], 6) for x in c[3:6]] == [0.375, 0.5, 0.625]
    assert len({x["id"] for x in c}) == 9 and c[4]["id"] == "pts80-r0p5"
    odd = TT.check(sheet(exits={"stop_pts": 7.5, "target_pts": 3.25}))["plan"]["cells"]      # the tick rule: nearest tick, halves up
    assert [x["stop_pts"] for x in odd][::3] == [5.75, 7.5, 9.5] and [x["target_pts"] for x in odd][:3] == [2.5, 3.25, 4.0]


def test_engine_inputs_are_the_sheets_own():
    p = TT.check(sheet())["plan"]
    for tf in ("5", "15"):
        eng = p["engine"][tf]
        assert len(eng) == 9
        c = next(e for e in eng if e["id"] == "pts80-r0p5")
        assert c["params"] == {"x": 0.1, "max_loss": 2, "tf": tf, "sess": "all", "dir": "long", "max_tr": 4, "exit_bars": 0,
                               "stop_mode": "pts", "stop_val": 80.0, "tgt_r": 0.5}
        assert c["sessions"] == ["nyam", "mid", "pm"] and c["hold_to"] == "day"
    assert p["control"] == {"kind": "random", "p_entry": RM.C1_P_ENTRY, "seeds": 10, "sides": ["both", "long"]}
    both = TT.check(sheet(dir="both"))["plan"]
    assert both["control"]["sides"] == ["both"]


# ================================================================ 3. the seal

def test_a_day_of_the_unseen_period_is_refused_before_anything_is_read(tmp_path, monkeypatch):
    monkeypatch.setattr(RUN, "clock", lambda: SAT)
    boom = {n: getattr(S, n) for n in ("run_many", "load_tape", "sessions", "load_daily")}

    def no(*a, **k):
        raise AssertionError("the engine was reached")
    for n in boom:
        monkeypatch.setattr(S, n, no)
    for bad in (["2025-07-01"], ["2024-05-14", "2025-07-01"], ["2026-01-05"], ["2021-09-21"]):
        with pytest.raises(J.Refuse, match="build"):
            TT.run(sheet(), root=tmp_path, days=bad, workers=1)
    assert not any(tmp_path.rglob("*.npz"))


def test_a_store_that_reaches_the_unseen_days_is_not_read(tmp_path):
    d = tmp_path / "runs" / "x-NQ-tf5"
    d.mkdir(parents=True)
    (d / "run.json").write_text(json.dumps({"range": {"start": "2021-09-22", "end": "2025-07-01"}, "cells": []}))
    from blueprint import tables as T
    with pytest.raises(J.Refuse, match="build"):
        T._open(tmp_path / "runs", "x-NQ-tf5")


# ================================================================ 5. a small real run on named build days

_RUNS: dict = {}
TINY_DAYS = ["2022-03-15", "2022-09-14", "2023-03-22", "2024-05-14", "2025-06-30"]
FEB = ["2023-02-01", "2023-02-02", "2023-02-03", "2023-02-06", "2023-02-07", "2023-02-08", "2023-02-09", "2023-02-10"]
REPO_PLACES = (RUN.RUNS, RUN.TESTS)


def _listing(d: Path) -> dict:
    return {str(p.relative_to(d)): p.stat().st_mtime_ns for p in d.rglob("*")} if d.exists() else {}


@pytest.fixture()
def world(monkeypatch):
    monkeypatch.setattr(RUN, "clock", lambda: SAT)
    monkeypatch.setenv(TT.ENV, str(Path(tempfile.gettempdir()) / "never_used_taught_root"))
    yield


def _once(key: str, fn):
    if key not in _RUNS:
        _RUNS[key] = fn()
    return _RUNS[key]


@pytest.fixture(scope="module")
def tmp_root():
    with tempfile.TemporaryDirectory(prefix="taught_") as d:
        yield Path(d).resolve()


def test_a_taught_rule_runs_as_taught_on_named_days(tmp_root, world, monkeypatch):
    s = sheet(bars=["5"])
    before = {str(p): _listing(p) for p in REPO_PLACES}
    led = (W / "ledger.csv").stat().st_mtime_ns
    r = _once("conti", lambda: TT.run(s, root=tmp_root, days=TINY_DAYS, workers=2, draws=200))
    assert r["ok"] and r["status"] == "smoke" and r["dry_run"] is True
    base = tmp_root / s["name"] / "smoke"
    assert (base / "result.json").exists() and (base / "sheet.json").exists() and not (tmp_root / s["name"] / "result.json").exists()
    keys = sorted(p.name for p in (base / "runs").iterdir() if p.is_dir())
    assert keys == [f"{s['name']}-NQ-tf5", f"{s['name']}__ctl-NQ-tf5", f"{s['name']}__ctl_long-NQ-tf5"]
    doc = r["result"]
    assert doc["smoke"] is True and doc["days"] == TINY_DAYS and doc["text"].splitlines()[0] == doc["headline"]
    head = doc["headline"]
    for part in ("SMOKE RUN, no verdict", "vwap_trend_pull", "stop 80 / target 40 points", "up to 4 trades a session pass", "leaves out 1 thing", "verdict: 5-minute bars make"):
        assert part in head, part
    b = doc["bars"]["5"]
    assert len(b["cells"]) == 9 and b["centre"]["id"] == "pts80-r0p5" and [r_["line"] for r_ in b["lines"]][-2:] == ["P4.2", "P4.2s"]
    assert doc["code"]["l2sim.py"] and doc["code"]["blueprint/taught.py"] and doc["code"]["families/round1.py"]
    # the engine's inputs are the sheet's own: the store's cells carry them
    unit = json.loads((base / "runs" / keys[0] / "run.json").read_text())
    cell = next(c for c in unit["cells"] if c["id"] == "pts80-r0p5")
    assert cell["inputs"]["stop_mode"] == "pts" and cell["inputs"]["stop_val"] == 80.0 and cell["inputs"]["tgt_r"] == 0.5
    assert cell["inputs"]["max_tr"] == 4 and cell["inputs"]["max_loss"] == 2 and cell["inputs"]["dir"] == "long" and cell["inputs"]["hold_to"] == "day"
    assert unit["range"]["end"] <= "2025-06-30" and unit["period"] == "bp_build" and unit["days"] == TINY_DAYS
    # no day of the unseen period anywhere in the stores
    for k in keys:
        z = np.load(base / "runs" / k / "cells.npz")
        assert len(z["date"]) == 0 or int(z["date"].max()) <= dt.date(2025, 6, 30).toordinal()
    # nothing of the repo's was written
    assert {str(p): _listing(p) for p in REPO_PLACES} == before and (W / "ledger.csv").stat().st_mtime_ns == led
    assert not (Path(tempfile.gettempdir()) / "never_used_taught_root").exists()


def test_a_second_run_does_no_work_and_a_changed_sheet_is_a_new_sheet(tmp_root, world):
    s = sheet(bars=["5"])
    _once("conti", lambda: TT.run(s, root=tmp_root, days=TINY_DAYS, workers=2, draws=200))
    again = TT.run(s, root=tmp_root, days=TINY_DAYS, workers=2, draws=200)
    assert all(x["skipped"] for x in again["result"]["stores"])                 # every store was there with the same inputs: no work
    assert again["result"]["headline"] == _RUNS["conti"]["result"]["headline"]
    with pytest.raises(J.Refuse, match="new sheet"):
        TT.run(sheet(bars=["5"], exits={"stop_pts": 60}), root=tmp_root, days=TINY_DAYS, workers=2)
    shown = TT.show(s["name"], tmp_root)
    assert shown["text"] == _RUNS["conti"]["text"] and shown["status"] == "smoke"
    mine = [x for x in TT.listing(tmp_root)["rows"] if x["name"] == s["name"]]
    assert len(mine) == 1 and mine[0]["status"] == "smoke only" and mine[0]["headline"] == shown["result"]["headline"]
    with pytest.raises(J.Refuse, match="no result"):
        TT.show("never_run", tmp_root)


def test_the_command_line_checks_runs_nothing_and_says_no_in_json(tmp_root, capsys):
    rc = cli.main(["taught", "check", str(SHEETS / "conti_vwap_pullback_short.json"), "--json"])
    d = json.loads(capsys.readouterr().out)
    assert rc == 0 and d["ok"] and d["command"] == "taught check" and d["plan"]["exits"]["target_pts"] == 50.0
    bad = tmp_root / "bad.json"
    bad.write_text(json.dumps(sheet(market="XX")))
    rc = cli.main(["taught", "check", str(bad), "--json"])
    d = json.loads(capsys.readouterr().out)
    assert rc == 2 and d["ok"] is False and "market" in d["error"]
    rc = cli.main(["taught", "check", str(tmp_root / "missing.json")])
    assert rc == 2 and "sheet" in capsys.readouterr().out
    rc = cli.main(["taught", "list", f"--root={tmp_root}", "--json"])
    assert rc == 0 and json.loads(capsys.readouterr().out)["command"] == "taught list"


def test_a_structure_stop_runs_with_the_taught_trades_own_stop_size_in_the_control(tmp_root, world):
    s = json.loads((SHEETS / "casper_open_fvg_daytrade.json").read_text())
    r = _once("casper", lambda: TT.run(s, root=tmp_root, days=FEB, workers=2, draws=200))
    doc = r["result"]
    b = doc["bars"]["5"]
    assert [c["id"] for c in b["cells"]] == ["struct-r1p5", "struct-r2", "struct-r2p5"] and b["centre"]["id"] == "struct-r2"
    base = tmp_root / s["name"] / "smoke" / "runs"
    unit = json.loads((base / f"{s['name']}-NQ-tf5" / "run.json").read_text())
    c = next(x for x in unit["cells"] if x["id"] == "struct-r2")
    assert c["inputs"]["stop_mode"] == "struct" and c["inputs"]["tgt_r"] == 2.0 and c["inputs"]["max_tr"] == 1 and c["inputs"]["oc_min"] == "15"
    assert b["centre"]["metrics"]["trades"] > 0, "the eight February days of 2023 hold at least one gap through the opening candle"
    stop = b["control_stop_pts"]
    assert stop and stop > 0 and round(stop / 0.25) == pytest.approx(stop / 0.25)          # a size, a tick multiple
    ctl = json.loads((base / f"{s['name']}__ctl-NQ-tf5" / "run.json").read_text())
    assert ctl["cells"][0]["inputs"]["stop_mode"] == "pts" and ctl["cells"][0]["inputs"]["stop_val"] == stop
    assert f"the random entries used the median stop of the taught trades, {stop:g} points" in doc["text"]
    assert [r_["line"] for r_ in b["lines"]][-2:] == ["P4.1", "P4.2"]                       # a both-sided rule: one control only
