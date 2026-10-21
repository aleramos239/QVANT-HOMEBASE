"""LOCK of the taught lane's 3:1 walk-forward (blueprint/taught_wf.py; the owner, 2026-10-19 / 2026-10-20). Every cell of the sheet -- its
own cells, as taught, not hm40 -- is run FIXED on the in-sample months of the 3:1 blocks (no cell changes between blocks, no pick by code);
the owner picks a cell from that table (hmwf.pick on the sheet's store) and its test months run once, on his words (hmwf.run_oos). A sheet
whose OLD walk-forward is on file is shown, never run again. The calendar is synthetic and the engine a fake: no tape is opened.

  pytest tests/test_taught_wf.py -q
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(HERE), str(HERE / "engine")]

import judge as J  # noqa: E402
import l2sim as S  # noqa: E402
import library as LB  # noqa: E402
from blueprint import api  # noqa: E402
from blueprint import cli as CLI  # noqa: E402
from blueprint import hmwf as H  # noqa: E402
from blueprint import runner as RUN  # noqa: E402
from blueprint import taught as TA  # noqa: E402
from blueprint import taught_wf as W  # noqa: E402
from blueprint import wfmonths as WM  # noqa: E402

CAL = ["2021-10-01", "2021-11-01", "2021-12-01", "2022-01-03"]      # Oct-Dec 2021 in-sample, Jan 2022 the test month
IS_DAYS = CAL[:3]
SHEET = {
    "name": "conti_vwap_pullback_long",
    "source": {"video": "wm4A6qo0g3I", "title": "Ex-Market Maker Shows the Exact VWAP Setup", "channel": "IQCapital", "url": "https://youtu.be/wm4A6qo0g3I"},
    "market": "NQ", "bars": ["5"], "sessions": ["nyam", "mid", "pm"], "dir": "long",
    "entry": {"family": "vwap_trend_pull", "settings": {"x": 0.1, "max_loss": 2}, "words": "long when the close is above a rising VWAP"},
    "exits": {"stop_pts": 80, "target_pts": 40, "exit_bars": 0, "max_trades": 4},
    "taught": ["[25:00] stop 80 points, target 40 points"], "not_run": ["the flat time is 15:55 in the video, 15:58 here"], "control": "random",
}
NAME, CENTRE = SHEET["name"], "pts80-r0p5"


def _fake_run_many(calls):
    def run_many(specs, *a, days=None, root="NQ", allow_holdout=False, **kw):
        calls.append({"days": list(days or []), "allow_holdout": allow_holdout, "inputs": [dict(p) for _, p in specs]})
        out = []
        for cls, p in specs:
            trades = []
            for d in days:
                if p.get("sess") != "nyam":
                    continue
                h = int(hashlib.sha256(f"{cls.__name__}|{sorted(p.items())}|{d}".encode()).hexdigest()[:8], 16)
                ent = S.et_ns(dt.date.fromisoformat(d), "10:00") // 1_000_000
                trades.append({"date": d, "entry_ms": ent, "exit_ms": ent + 60_000, "net": float(h % 700 - 300), "mae_usd": 50.0,
                               "side": "long", "exit_reason": "tp", "entry_price": 100.0, "sl": 90.0})
            out.append({"trades": trades, "skipped": [], "no_trade": [], "sessions": len(days), "used": len(days), "skipped_by_error": 0,
                        "unrealistic_winners": 0, "both_sides_sessions": 0, "elapsed_s": 0.0,
                        "meta": {"inputs": dict(p), "root": root, "engine": "fake",
                                 "range": {"start": min(days), "end": max(days), "holdout": True, "period": allow_holdout}}})
        return out
    return run_many


@pytest.fixture
def wf(monkeypatch, tmp_path):
    monkeypatch.setattr(WM, "_sessions", lambda root, today: (tuple(CAL), "2022-02-01"))
    WM._sets.cache_clear()
    calls = []
    monkeypatch.setattr(S, "run_many", _fake_run_many(calls))
    monkeypatch.setattr(RUN, "RUNS", tmp_path / "runs_bp")
    monkeypatch.setattr(H, "RUNS", tmp_path / "runs_wf")
    monkeypatch.setattr(RUN, "clock", lambda: dt.datetime(2026, 10, 3, 11, 0, tzinfo=S.ET))     # a Saturday: no start window
    monkeypatch.setattr(LB, "LEDGER", tmp_path / "ledger.csv")              # never the real ledger.csv
    monkeypatch.setenv("HOMEBASE_IDEAS_ROOT", str(tmp_path / "ideas"))
    monkeypatch.delenv("HOMEBASE_OLD_ROUTE_END", raising=False)
    root = tmp_path / "taught"
    plan, bad = TA._plan(SHEET)
    assert plan and not bad, bad
    (root / NAME).mkdir(parents=True)
    (root / NAME / "result.json").write_text(json.dumps({"plan": plan}))   # the sheet's build-day run on file (only its plan is read)
    yield {"calls": calls, "root": root, "plan": plan}
    WM._sets.cache_clear()


def _bp(capsys, *argv):
    rc = CLI.main([*argv, "--json"])
    return rc, json.loads(capsys.readouterr().out)


def _oos_calls(wf):
    return [c for c in wf["calls"] if c["allow_holdout"] == S.ALLOW_WF_OOS]


def _log():
    return [r for r in api.ideastore().reads() if r.get("kind") == "wf_oos"]


def test_the_test_days_stop_at_the_last_whole_month(monkeypatch):
    days = [dt.date(2026, 9, 29), dt.date(2026, 9, 30), dt.date(2026, 10, 1), dt.date(2026, 10, 16)]
    monkeypatch.setattr(W.RUN, "test_range", lambda m: {"start": "2026-09-29", "end": "2026-10-16"})
    monkeypatch.setattr(W.S, "sessions", lambda a, b, m, allow_holdout=None: days)
    assert W._test_days("NQ", dt.date(2026, 10, 19)) == ["2026-09-29", "2026-09-30"]


def test_taught_wf_runs_each_cell_fixed(wf):
    r = W.run(NAME, wf["root"], workers=1, owner_said="run the taught sheet on the blocks")
    home = W.home(NAME, wf["root"])
    assert home.name == f"{NAME}__taught-NQ-tf5"                            # not an hm40 idea's store name (the read log's key)
    u = LB.load_unit("is", home)
    ids = [c["id"] for c in wf["plan"]["cells"]]
    assert [c["id"] for c in u["meta"]["cells"]] == ids and len(ids) == 9 and CENTRE in ids    # the sheet's own cells, not hm40
    assert u["meta"]["period"] == S.ALLOW_WF_IS and u["meta"]["days"] == IS_DAYS
    # every engine call: the in-sample switch, in-sample days only; each cell keeps ONE set of inputs over every block
    assert wf["calls"] and all(c["allow_holdout"] == S.ALLOW_WF_IS and set(c["days"]) <= set(IS_DAYS) for c in wf["calls"])
    ran: dict = {}
    for c in wf["calls"]:
        for p in c["inputs"]:
            ran.setdefault(json.dumps({k: v for k, v in p.items() if k != "sess"}, sort_keys=True), set()).update(c["days"])
    assert len(ran) == 9 and all(d == set(IS_DAYS) for d in ran.values())   # 9 input sets, each on every in-sample day
    for e in wf["plan"]["engine"]["5"]:                                      # ... each one the sheet's own cell
        want = {k: v for k, v in e["params"].items() if k != "sess"}
        assert sum(want.items() <= json.loads(x).items() for x in ran) == 1, want
    # the table the owner picks from: one row a cell, no pick, no test month
    assert r["command"] == "taught wf" and r["owner_said"] == "run the taught sheet on the blocks"
    assert sorted(x["box"] for x in r["wf"]["is"]) == sorted(ids) and r["wf"]["lock"] is None and r["wf"]["oos"] is None
    assert all(x["beats_random"] is None for x in r["wf"]["is"])             # hm40's random pool is not the sheet's control
    assert "pick" in r["next"] and not _oos_calls(wf)
    n = len(wf["calls"])
    again = W.run(NAME, wf["root"], workers=1, owner_said="again")         # a rerun does no work
    assert len(wf["calls"]) == n and again["wf"]["is"] == r["wf"]["is"]


def test_taught_wf_oos_needs_pick_and_owner_said(wf, capsys):
    for said in ([], ["--owner-said="], ["--owner-said=   "]):                # the in-sample run is a heat map: the owner's words first
        rc, no = _bp(capsys, "taught", "wf", NAME, f"--root={wf['root']}", *said)
        assert rc == 2 and no["ok"] is False and "owner" in no["error"]
    assert not wf["calls"] and not W.home(NAME, wf["root"]).exists()
    for sub in (["wf-show", NAME], ["wf-pick", NAME, CENTRE]):              # nothing to show or pick before the in-sample run
        rc, no = _bp(capsys, "taught", *sub, f"--root={wf['root']}")
        assert rc == 2 and "no 3:1 in-sample run" in no["error"]
    rc, r = _bp(capsys, "taught", "wf", NAME, f"--root={wf['root']}", "--owner-said=run the sheet", "--workers=1")
    assert rc == 0 and r["wf"]["lock"] is None
    rc, no = _bp(capsys, "taught", "wf-oos", NAME, CENTRE, f"--root={wf['root']}", "--owner-said=run it")
    assert rc == 2 and "picked" in no["error"]                                # no pick yet
    rc, r = _bp(capsys, "taught", "wf-pick", NAME, CENTRE, f"--root={wf['root']}")
    assert rc == 0 and r["wf"]["lock"]["box"] == CENTRE and r["wf"]["oos"] is None and "owner says" in r["next"]
    rc, no = _bp(capsys, "taught", "wf-pick", NAME, "pts60-r0p5", f"--root={wf['root']}")
    assert rc == 2 and "picked already" in no["error"]                        # the pick never changes
    rc, no = _bp(capsys, "taught", "wf-oos", NAME, CENTRE, f"--root={wf['root']}", "--owner-said=  ")
    assert rc == 2 and "owner" in no["error"]
    assert not _oos_calls(wf) and not _log()
    rc, r = _bp(capsys, "taught", "wf-oos", NAME, CENTRE, f"--root={wf['root']}", "--owner-said= run the centre", "--workers=1")
    assert rc == 0 and r["wf"]["oos"]["record"]["box"] == CENTRE and r["owner_said"] == " run the centre"
    oc = _oos_calls(wf)
    assert oc and all(c["days"] == ["2022-01-03"] for c in oc)                 # the test month only, one month a call
    assert len({json.dumps({k: v for k, v in p.items() if k != "sess"}, sort_keys=True) for c in oc for p in c["inputs"]}) == 1   # the picked cell only
    (line,) = _log()
    assert line["owner_said"] == " run the centre" and line["store"] == W.home(NAME, wf["root"]).name and line["box"] == CENTRE
    rc, no = _bp(capsys, "taught", "wf-oos", NAME, CENTRE, f"--root={wf['root']}", "--owner-said=again")
    assert rc == 2 and len(_log()) == 1                                       # once
    rc, s = _bp(capsys, "taught", "wf-show", NAME, f"--root={wf['root']}")
    assert rc == 0 and s["wf"]["oos"]["record"]["box"] == CENTRE


def test_an_old_walk_forward_on_file_is_shown_never_run(wf):
    old = wf["root"] / NAME / "wf"
    old.mkdir()
    (old / "result.json").write_text(json.dumps({"name": NAME, "text": "the old walk-forward"}))
    r = W.run(NAME, wf["root"], workers=1)                                   # shown: no words needed, nothing runs
    assert r["status"] == "on file" and r["text"].startswith("the old walk-forward") and "already seen" in r["text"]
    assert not wf["calls"] and not W.home(NAME, wf["root"]).exists()
    (old / "result.json").unlink()
    (old / "claim.json").write_text(json.dumps({"utc": "2026-10-19T12:00:00+00:00"}))   # an old read that stopped: its months are seen too
    with pytest.raises(J.Refuse, match="already seen"):
        W.run(NAME, wf["root"], workers=1, owner_said="run it")
    assert not wf["calls"]
