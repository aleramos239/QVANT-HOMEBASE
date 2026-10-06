"""importrun: a finished run bundle written from a plain trade list (a result of the research engine), read
back through the page's own reader (RunManager) and its own routes, in a temp runs folder."""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from homebase.backtest import importrun, propsim, runner
from homebase.backtest.runner import RUN_ID, RunManager, read_json
from homebase.charts.server import create_app
from tests.backtest_util import D1, ms, nq_archive

REPO = Path(__file__).resolve().parent.parent
SID = "draft_nq_orb_pre"
DAYS = [dt.date(2024, 3, 5), dt.date(2024, 3, 6), dt.date(2024, 3, 7)]


def plain(day: dt.date, t_in: str, t_out: str, side: str, entry: float, exit_: float, net: float, qty: int = 1, **more):
    """The plain row: entry time, exit time, side, qty, entry price, exit price, net (times = New York wall clock)."""
    return {"entry_time": f"{day}T{t_in}", "exit_time": f"{day}T{t_out}", "side": side, "qty": qty,
            "entry_price": entry, "exit_price": exit_, "net": net, **more}


TRADES = [plain(DAYS[0], "09:30:01", "09:30:03", "long", 110.25, 125.25, 296.0),
          plain(DAYS[1], "09:31:00", "09:32:00", "short", 99.0, 104.0, -104.0),
          plain(DAYS[2], "10:00:00", "10:05:30", "long", 100.0, 110.0, 196.0, qty=2)]


def imported(tmp_path, trades=TRADES, **kw):
    base = tmp_path / "tester"
    rid = importrun.write_run(trades, strategy=SID, root="NQ", base=base, **kw)
    return base, rid


def folders(base: Path) -> list[str]:
    return sorted(p.name for p in (base / "runs").iterdir()) if (base / "runs").exists() else []


# ---------------------------------------------------------------- the bundle, through the page's reader

def test_an_imported_run_is_listed_and_opened_like_any_run(tmp_path):
    base, rid = imported(tmp_path, name="NQ pre-market ORB", note="code check of round 1")
    assert RUN_ID.match(rid) and folders(base) == [rid]
    m = RunManager(base)
    [row] = m.runs_list()
    assert row == {"id": rid, "strategy": SID, "created": row["created"], "status": "done", "range": row["range"],
                   "holdout": False, "trades": 3, "net_profit": 388.0}
    assert m.status(rid)["status"] == "done"
    b = m.bundle(rid)
    assert set(b) == {"run", "trades", "equity", "plots", "propsim"}
    run = b["run"]
    assert run["id"] == rid and run["strategy"] == {"id": SID, "name": "NQ pre-market ORB", "root": "NQ"}
    a = run["report"]["summary"]["all"]
    assert (a["trades"], a["wins"], a["losses"], a["net_profit"], a["avg_trade"]) == (3, 2, 1, 388.0, pytest.approx(388 / 3))
    assert (run["report"]["summary"]["long"]["trades"], run["report"]["summary"]["short"]["net_profit"]) == (2, -104.0)
    assert [(y["period"], y["trades"], y["net"]) for y in run["report"]["by_year"]] == [("2024", 3, 388.0)]
    assert b["equity"] == {"t_ms": [ms(DAYS[0], "09:30:03"), ms(DAYS[1], "09:32:00"), ms(DAYS[2], "10:05:30")],
                           "equity": [296.0, 192.0, 388.0], "drawdown": [0.0, -104.0, 0.0]}
    assert b["plots"] == {"plots": {}, "hlines": []}
    assert run["coverage"] == {"sessions": 3, "used": 3, "skipped": [], "skipped_by_reason": {}, "no_trade": [],
                               "skipped_by_error": 0, "skipped_by_data": 0}
    assert (run["qty"], run["commission"], run["slippage_ticks"], run["capital"]) == (2, 4.0, 1.0, 50_000.0)
    assert run["inputs"] == {} and run["holdout"] is False and run["propsim_error"] is False


def test_it_says_everywhere_that_it_came_from_the_research_engine(tmp_path):
    base, rid = imported(tmp_path, note="code check of round 1")
    b = RunManager(base).bundle(rid)
    run = b["run"]
    assert run["range"] == {"kind": "custom", "start": "2024-03-05", "end": "2024-03-07", "holdout": False,
                            "label": "Research engine · 2024-03-05 → 2024-03-07"}
    assert RunManager(base).runs_list()[0]["range"]["label"].startswith("Research engine · ")   # the Recent runs row
    assert run["engine"] == "research engine (imported)" and "research engine" in run["fill_law"]
    assert "tick" not in run["engine"] and "replay" not in run["engine"]
    assert run["imported"] == {"source": "research engine", "note": "code check of round 1", "trades": 3}
    assert read_json(base / "runs" / rid / "request.json")["imported"] == run["imported"]
    # no prop eval is made up for it: the page offers its own re-score, the blueprint's odds are another tool
    assert run["prop_rules"] is None and set(b["propsim"]) == {"skipped"} and "research engine" in b["propsim"]["skipped"]


def test_the_trade_rows_are_a_runs_rows(tmp_path):
    base, rid = imported(tmp_path)
    rows = RunManager(base).bundle(rid)["trades"]
    assert rows[0] == {"date": "2024-03-05", "side": "long", "qty": 1, "entry_ms": ms(DAYS[0], "09:30:01"),
                       "entry_price": 110.25, "exit_ms": ms(DAYS[0], "09:30:03"), "exit_price": 125.25,
                       "exit_reason": "", "order_price": None, "sl": None, "tp": None, "gross": 296.0,
                       "commission": 0.0, "net": 296.0, "mae_pts": None, "mfe_pts": None, "mae_usd": None,
                       "mfe_usd": None, "bars": 1, "seconds": 2.0}
    assert (rows[2]["bars"], rows[2]["seconds"], rows[2]["qty"]) == (6, 330.0, 2)
    assert all("entry_ns" not in t and "exit_ns" not in t for t in rows)     # the page's numbers: ms, never ns


def test_times_are_taken_as_ns_ms_or_iso_and_mean_the_same(tmp_path):
    t_in, t_out = ms(DAYS[0], "09:30:01"), ms(DAYS[0], "09:30:03")
    rest = {"side": "long", "qty": 1, "entry_price": 110.25, "exit_price": 125.25, "net": 296.0}
    forms = [{"entry_ns": t_in * 1_000_000, "exit_ns": t_out * 1_000_000}, {"entry_ms": t_in, "exit_ms": t_out},
             {"entry_time": "2024-03-05T09:30:01", "exit_time": "2024-03-05T09:30:03"},
             {"entry_time": "2024-03-05T14:30:01Z", "exit_time": "2024-03-05T09:30:03-05:00"},
             {"entry_time": "2024-03-05 09:30:01.000", "exit_time": "2024-03-05T14:30:03+00:00"}]
    got = []
    for i, f in enumerate(forms):
        base, rid = imported(tmp_path / str(i), [{**f, **rest}])
        got.append(RunManager(base).bundle(rid)["trades"])
    assert all(g == got[0] for g in got) and (got[0][0]["entry_ms"], got[0][0]["exit_ms"]) == (t_in, t_out)
    assert got[0][0]["date"] == "2024-03-05"


def test_the_engines_own_rows_keep_what_they_know_and_lose_what_a_run_has_no_place_for(tmp_path):
    t_in, t_out = ms(DAYS[0], "09:30:01"), ms(DAYS[0], "09:30:03")
    engine_row = {"date": "2024-03-05", "side": "short", "qty": 1, "entry_price": 125.25, "exit_price": 110.25,
                  "exit_reason": "tp", "order_price": 125.0, "sl": 130.25, "tp": 110.25, "gross": 300.0,
                  "commission": 4.0, "net": 296.0, "mae_pts": 1.5, "mfe_pts": 15.0, "mae_usd": 30.0, "mfe_usd": 300.0,
                  "bars": 1, "seconds": 2.0, "entry_ms": t_in, "exit_ms": t_out, "oco": True, "both_sides": None,
                  "tag": "s3_t2", "_k": [t_out, t_in]}
    base, rid = imported(tmp_path, [engine_row])
    [row] = RunManager(base).bundle(rid)["trades"]
    assert row == {k: v for k, v in engine_row.items() if k not in ("oco", "both_sides", "tag", "_k")}
    assert RunManager(base).bundle(rid)["run"]["report"]["summary"]["all"]["commission_paid"] == 4.0


def test_trades_are_stored_in_a_runs_order_whatever_order_they_came_in(tmp_path):
    base, rid = imported(tmp_path, [TRADES[2], TRADES[0], TRADES[1]])
    b = RunManager(base).bundle(rid)
    assert [t["date"] for t in b["trades"]] == ["2024-03-05", "2024-03-06", "2024-03-07"]
    assert b["equity"]["equity"] == [296.0, 192.0, 388.0]


# ---------------------------------------------------------------- the dates it says it covers

def test_the_build_days_read_as_the_build_days_and_the_test_days_are_a_fact_on_the_run(tmp_path):
    base, rid = imported(tmp_path, start="2021-09-22", end="2025-06-30", sessions=940)
    run = RunManager(base).bundle(rid)["run"]
    assert run["range"] == {"kind": "research", "start": "2021-09-22", "end": "2025-06-30", "holdout": False,
                            "label": "Research engine · Build · Sep 2021 – Jun 2025"}
    assert (run["coverage"]["sessions"], run["coverage"]["used"]) == (940, 940)
    assert not (base / "spends.jsonl").exists()
    late = [plain(dt.date(2025, 7, 1), "09:30:01", "09:30:03", "long", 100.0, 101.0, 16.0),
            plain(dt.date(2026, 9, 29), "09:31:00", "09:32:00", "short", 99.0, 98.0, 16.0)]
    base, rid = imported(tmp_path / "late", late)
    b = RunManager(base)
    assert b.runs_list()[0]["holdout"] is True and b.bundle(rid)["run"]["holdout"] is True
    assert b.bundle(rid)["run"]["range"]["label"] == "Research engine · Test · Jul 2025 → 2026-09-29"
    [spend] = [json.loads(x) for x in (base / "spends.jsonl").read_text().splitlines()]      # recorded, as any run is
    assert spend["run_id"] == rid and spend["strategy"] == SID and spend["range"]["holdout"] is True


def test_a_spend_log_that_cannot_be_written_never_fails_the_import(tmp_path, capsys):
    late = [plain(dt.date(2025, 7, 1), "09:30:01", "09:30:03", "long", 100.0, 101.0, 16.0)]
    (tmp_path / "tester").mkdir()
    (tmp_path / "tester" / "spends.jsonl").mkdir()
    base, rid = imported(tmp_path, late)
    assert RunManager(base).bundle(rid)["run"]["holdout"] is True and "spend log" in capsys.readouterr().err


# ---------------------------------------------------------------- what is refused, and nothing half-written

BAD_LISTS = [
    (None, "a list"), ({"trades": TRADES}, "a list"), ([], "no trades"), (["x"], "trade 1"),
    ([{**TRADES[0], "side": "buy"}], "trade 1: side"), ([TRADES[0], {**TRADES[1], "qty": 0}], "trade 2: qty"),
    ([{**TRADES[0], "qty": 1.5}], "trade 1: qty"), ([{**TRADES[0], "qty": True}], "trade 1: qty"),
    ([{k: v for k, v in TRADES[0].items() if k != "net"}], "trade 1: net"),
    ([{**TRADES[0], "net": float("nan")}], "trade 1: net"), ([{**TRADES[0], "entry_price": "110"}], "trade 1: entry_price"),
    ([{**TRADES[0], "exit_price": None}], "trade 1: exit_price"), ([{**TRADES[0], "sl": "tight"}], "trade 1: sl"),
    ([{**TRADES[0], "exit_time": "2024-03-05T09:29:00"}], "trade 1: it exits before"),
    ([{**TRADES[0], "entry_time": "yesterday"}], "trade 1: entry"), ([{**TRADES[0], "entry_ms": 1.5}], "trade 1: entry"),
    ([{k: v for k, v in TRADES[0].items() if k != "exit_time"}], "trade 1: exit"),
    ([{**TRADES[0], "date": "5 March"}], "trade 1: date"),
]


@pytest.mark.parametrize("trades,msg", BAD_LISTS)
def test_a_trade_list_that_does_not_read_is_refused_and_nothing_is_written(trades, msg, tmp_path):
    with pytest.raises(ValueError, match=msg):
        imported(tmp_path, trades)
    assert folders(tmp_path / "tester") == []


@pytest.mark.parametrize("kw,msg", [
    ({"strategy": "Bad Id"}, "strategy"), ({"strategy": ""}, "strategy"), ({"strategy": "draft-x"}, "strategy"),
    ({"root": "nq"}, "root"), ({"root": ""}, "root"), ({"name": "two\nlines"}, "name"),
    ({"start": "2024-03-06"}, "2024-03-05"), ({"end": "2024-03-06"}, "2024-03-07"),
    ({"start": "2024-04-01", "end": "2024-03-01"}, "start"), ({"start": "March"}, "date"),
    ({"qty": 0}, "qty"), ({"capital": 0}, "capital"), ({"commission": -1}, "commission"),
    ({"sessions": 2}, "sessions"), ({"inputs": ["or_min"]}, "inputs")])
def test_what_it_is_labelled_with_is_checked_too(kw, msg, tmp_path):
    args = {"strategy": SID, "root": "NQ", "base": tmp_path / "tester", **kw}
    with pytest.raises(ValueError, match=msg):
        importrun.write_run(TRADES, **args)
    assert folders(tmp_path / "tester") == []


def test_a_failed_write_leaves_no_run_folder(tmp_path, monkeypatch):
    real = importrun.write_json

    def boom(path, data):
        if path.name == "run.json":
            raise OSError("disk full")
        real(path, data)

    monkeypatch.setattr(importrun, "write_json", boom)
    with pytest.raises(OSError):
        imported(tmp_path)
    assert folders(tmp_path / "tester") == [] and RunManager(tmp_path / "tester").runs_list() == []


def test_the_run_appears_whole_or_not_at_all(tmp_path, monkeypatch):
    """The page lists the runs folder on every call: a run being written is never there half-done."""
    base, seen, real = tmp_path / "tester", [], importrun.write_json

    def watching(path, data):
        seen.append(RunManager(base).runs_list())
        real(path, data)

    monkeypatch.setattr(importrun, "write_json", watching)
    rid = importrun.write_run(TRADES, strategy=SID, root="NQ", base=base)
    assert len(seen) >= 6 and all(x == [] for x in seen)
    assert [r["id"] for r in RunManager(base).runs_list()] == [rid]


# ---------------------------------------------------------------- the page's own routes, and the command line

def test_the_page_routes_list_it_open_it_and_score_it(tmp_path):
    app = create_app(roots=["NQ"], base=nq_archive(tmp_path / "ticks"), replay=D1, speed=1,
                     start_et=dt.time(9, 30), state=tmp_path / "state")
    with TestClient(app, base_url="http://localhost:8852") as c:
        rid = importrun.write_run(TRADES, strategy=SID, root="NQ", base=tmp_path / "state" / "tester")
        listed = c.get("/api/tester/runs").json()
        assert [r["id"] for r in listed] == [rid] and listed[0]["status"] == "done" and listed[0]["trades"] == 3
        assert c.get(f"/api/tester/run/{rid}").json()["status"] == "done"
        b = c.get(f"/api/tester/run/{rid}/bundle")
        assert b.status_code == 200 and b.json()["run"]["imported"]["source"] == "research engine"
        mc = c.post("/api/tester/montecarlo", json={"run_id": rid, "paths": 200})
        assert mc.status_code == 200, mc.text
        assert (mc.json()["n_trades"], mc.json()["n_days"]) == (3, 3) and mc.json()["p_prop_pass"] is None
        scored = c.post("/api/tester/propsim", json={"run_id": rid, "prop_rules": propsim.DEFAULT_RULES})
        assert scored.status_code == 200 and "headline" in scored.json()                 # the page's own re-score
        assert c.post(f"/api/tester/run/{rid}/cancel").json()["status"] == "done"       # finished: left as it is


def test_the_command_line_writes_the_same_bundle(tmp_path):
    src = tmp_path / "trades.json"
    src.write_text(json.dumps({"trades": TRADES}))
    cmd = [sys.executable, "-m", "homebase.backtest.importrun", str(src), "--strategy", SID, "--root", "NQ",
           "--name", "NQ pre-market ORB", "--note", "from the command line", "--base", str(tmp_path / "tester")]
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, p.stderr
    rid = p.stdout.strip()
    b = RunManager(tmp_path / "tester").bundle(rid)
    assert len(b["trades"]) == 3 and b["run"]["imported"]["note"] == "from the command line"
    assert b["run"]["strategy"]["name"] == "NQ pre-market ORB"
    src.write_text(json.dumps([{**TRADES[0], "side": "buy"}]))                              # a bare list reads too
    p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=60)
    assert p.returncode == 2 and "trade 1: side" in p.stderr and p.stdout == ""
    assert folders(tmp_path / "tester") == [rid]


def test_the_default_runs_folder_is_the_testers_own():
    assert runner.default_base().name == "tester"
    assert importrun.write_run.__kwdefaults__["base"] is None      # None = runner.default_base(), where the page looks
