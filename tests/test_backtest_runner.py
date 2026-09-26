"""Runner: validation + spends, the bundle, one-at-a-time child processes, cancel, recovery."""
from __future__ import annotations

import datetime as dt
import fcntl
import json
import time

import pytest

from homebase.backtest import runner
from homebase.backtest.discipline import DisciplineError
from homebase.backtest.runner import RunManager, execute, prepare, read_json, validate
from homebase.backtest.tape import TapeStore
from tests.backtest_util import D1, D2, ms, nq_archive
from tests.charts_util import rows, write_archive

RANGE = {"kind": "custom", "start": "2024-03-01", "end": "2024-03-31"}
D_HALF = dt.date(2024, 12, 24)     # a Tuesday: Dec 24 half day (Item 2)


def body(**kw):
    return {"strategy": "nq930", "inputs": {"adx_gate": False}, "range": RANGE, **kw}


def wait(m: RunManager, rid: str, want=("done", "error", "cancelled"), s=30.0) -> dict:
    t = time.monotonic() + s
    while time.monotonic() < t:
        st = m.status(rid)
        if st.get("status") in want:
            return st
        time.sleep(0.05)
    raise AssertionError(f"{rid} stuck at {m.status(rid)}")


def test_validate_fills_defaults_and_refuses_bad_requests():
    v = validate({"strategy": "nq930"})
    assert v["range"]["kind"] == "research" and v["range"]["start"] == "2021-01-01"
    assert (v["qty"], v["commission"], v["slippage_ticks"], v["capital"]) == (1, 4.0, 1.0, 50_000.0)
    assert v["holdout"] is None and v["inputs"]["sl_pts"] == 5.0
    for bad, msg in (({"strategy": "zz"}, "unknown strategy"), (body(qty=0), "qty"),
                     (body(qty=1.5), "whole"), (body(commission=-1), "commission"),
                     (body(slippage_ticks="1"), "number"), (body(extra=1), "unknown field"),
                     (body(inputs={"sl_pts": -1}), "sl_pts"), ("x", "JSON object")):
        with pytest.raises(ValueError, match=msg):
            validate(bad)


def test_a_holdout_range_needs_the_switch_and_every_accepted_run_is_a_spend(tmp_path):
    late = {"kind": "custom", "start": "2024-12-01", "end": "2025-02-01"}
    with pytest.raises(DisciplineError):
        prepare(body(range=late), tmp_path)
    assert not (tmp_path / "spends.jsonl").exists()
    rid = prepare(body(range=late, holdout={"reason": "forward check"}), tmp_path)
    [spend] = [json.loads(x) for x in (tmp_path / "spends.jsonl").read_text().splitlines()]
    assert spend["strategy"] == "nq930" and spend["reason"] == "forward check"
    assert spend["range"]["end"] == "2025-02-01" and spend["inputs"]["adx_gate"] is False
    req = read_json(tmp_path / "runs" / rid / "request.json")
    assert req["holdout"] == {"reason": "forward check"}
    prepare(body(), tmp_path)
    assert len((tmp_path / "spends.jsonl").read_text().splitlines()) == 1     # research: no spend


def test_is_months_reaching_2025_also_needs_the_holdout_switch(tmp_path):
    """Carry (Task 6 review): the holdout rule keys off the range's END date, not
    its kind — an IS-months range with an explicit 2025 end is holdout data too,
    and must be refused without the switch, and record exactly one spend when
    accepted."""
    late = {"kind": "is_months", "start": "2024-10-01", "end": "2025-04-30"}
    with pytest.raises(DisciplineError):
        prepare(body(range=late), tmp_path)
    assert not (tmp_path / "spends.jsonl").exists()
    rid = prepare(body(range=late, holdout={"reason": "IS-months forward check"}), tmp_path)
    [spend] = [json.loads(x) for x in (tmp_path / "spends.jsonl").read_text().splitlines()]
    assert spend["range"]["kind"] == "is_months" and spend["reason"] == "IS-months forward check"
    req = read_json(tmp_path / "runs" / rid / "request.json")
    assert req["range"]["kind"] == "is_months" and req["holdout"] == {"reason": "IS-months forward check"}


def test_execute_writes_the_bundle_and_lists_skipped_sessions(tmp_path):
    store = TapeStore(nq_archive(tmp_path / "ticks"), tmp_path / "cache")
    rid = prepare(body(qty=2), tmp_path / "t")
    d = tmp_path / "t" / "runs" / rid
    meta = execute(d, store)
    assert meta["engine"] == "tick-1" and meta["fill_law"] == "tick replay" and meta["holdout"] is False
    cov = meta["coverage"]
    assert (cov["sessions"], cov["used"]) == (2, 1)
    assert cov["skipped"] == [{"date": D2.isoformat(), "reason": "missing 13:00–16:00 ET"}]
    assert cov["skipped_by_reason"] == {"missing 13:00–16:00 ET": 1}
    assert cov["skipped_by_error"] == 0 and cov["skipped_by_data"] == 1
    [t] = read_json(d / "trades.json")
    assert (t["date"], t["side"], t["qty"], t["exit_reason"]) == (D1.isoformat(), "long", 2, "tp")
    assert t["net"] == round(15 * 20 * 2 - 8.0, 2)
    # Item 6: trades.json is JS-facing -- ms timestamps, no raw ts_ns.
    assert "entry_ns" not in t and "exit_ns" not in t
    assert t["entry_ms"] < t["exit_ms"] and t["exit_ms"] < 10 ** 15   # Number.MAX_SAFE_INTEGER headroom
    assert meta["report"]["summary"]["all"]["net_profit"] == t["net"]
    assert meta["report"]["skipped_by_error"] == 0 and meta["report"]["skipped_by_data"] == 1
    assert read_json(d / "equity.json")["equity"] == [t["net"]]
    assert read_json(d / "plots.json")["hlines"][0]["name"] == "anchor"
    assert read_json(d / "status.json")["status"] == "done"
    # Item 4: the resolved strategy config is snapshotted in BOTH request.json and
    # run.json, so a bundle is reproducible even after config.json later changes.
    req = read_json(d / "request.json")
    assert req["strategy_config"]["fire"] == "09:30:00" and "desk_cfg" in req["strategy_config"]
    assert meta["strategy_config"] == req["strategy_config"]


def half_day_archive(base):
    """A CME half day (Item 2): NQ trades a normal morning but the tape ends at
    the equity index's 13:15 ET early close -- no afternoon, and that must not
    be read as a coverage hole."""
    span_s = int((dt.datetime.combine(D_HALF, dt.time(13, 14))
                 - dt.datetime.combine(D_HALF, dt.time(9, 25))).total_seconds())
    day = rows(ms(D_HALF, "09:25:00"), [100.0] * (span_s // 10 + 1), step_ms=10_000)
    write_archive(base, "NQ", D_HALF, "NQZ4", day)
    return base


def test_a_half_day_tape_ending_at_the_early_close_is_used_not_skipped(tmp_path):
    store = TapeStore(half_day_archive(tmp_path / "ticks"), tmp_path / "cache")
    b = body(range={"kind": "custom", "start": D_HALF.isoformat(), "end": D_HALF.isoformat()})
    rid = prepare(b, tmp_path / "t")
    meta = execute(tmp_path / "t" / "runs" / rid, store)
    cov = meta["coverage"]
    assert cov["sessions"] == 1 and cov["used"] == 1 and cov["skipped"] == []


def test_execute_refuses_a_tampered_request_reaching_the_holdout(tmp_path):
    rid = prepare(body(), tmp_path)
    p = tmp_path / "runs" / rid / "request.json"
    req = read_json(p)
    req["range"] = {"kind": "custom", "start": "2024-12-01", "end": "2025-03-01"}
    p.write_text(json.dumps(req))
    with pytest.raises(DisciplineError):
        execute(tmp_path / "runs" / rid, TapeStore(tmp_path / "ticks", tmp_path / "cache"))


def test_manager_runs_a_child_process_to_done(tmp_path):
    m = RunManager(tmp_path / "t", archive=nq_archive(tmp_path / "ticks"), cache=tmp_path / "cache")
    rid = m.submit(body())
    st = wait(m, rid)
    assert st["status"] == "done", (tmp_path / "t" / "runs" / rid / "log.txt").read_text()
    assert st["pid"] != __import__("os").getpid()             # a separate process
    b = m.bundle(rid)
    assert b["run"]["coverage"]["used"] == 1 and len(b["trades"]) == 1
    assert m.runs_list()[0]["id"] == rid and m.runs_list()[0]["trades"] == 1


def test_runs_queue_one_at_a_time_and_cancel(tmp_path):
    m = RunManager(tmp_path / "t", archive=nq_archive(tmp_path / "ticks"), cache=tmp_path / "cache")
    (tmp_path / "t" / "runs").mkdir(parents=True, exist_ok=True)
    with open(tmp_path / "t" / "runs" / ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)                         # a "script run" holds the desk
        a, b = m.submit(body()), m.submit(body())
        log = tmp_path / "t" / "runs" / a / "log.txt"
        t = time.monotonic() + 10
        while not log.exists() and time.monotonic() < t:         # the manager launched a's child
            time.sleep(0.02)
        time.sleep(0.2)
        assert m.status(a)["status"] == "queued"                 # ...which waits on the lock
        assert m.status(b)["queue_position"] == 1
        assert m.cancel(b)["status"] == "cancelled"
        assert m.cancel(a)["status"] == "cancelled"
    c = m.submit(body())
    assert wait(m, c)["status"] == "done"
    assert m.status(a)["status"] == m.status(b)["status"] == "cancelled"
    with pytest.raises(ValueError):
        m.bundle(a)
    with pytest.raises(KeyError):
        m.dir("../../etc")


def test_a_restart_marks_orphaned_runs_as_interrupted(tmp_path):
    rid = prepare(body(), tmp_path)
    p = tmp_path / "runs" / rid / "status.json"
    p.write_text(json.dumps({**read_json(p), "status": "running", "pid": 999_999_999}))
    m = RunManager(tmp_path)
    assert m.status(rid)["status"] == "error" and "restarted" in m.status(rid)["error"]


def test_cli_run_prints_a_summary(tmp_path, capsys):
    arch = nq_archive(tmp_path / "ticks")
    assert runner.main(["run", "--strategy", "nq930", "--input", "adx_gate=false",
                        "--range", "2024-03-01:2024-03-31", "--base", str(tmp_path / "t"),
                        "--archive", str(arch), "--cache", str(tmp_path / "cache")]) == 0
    assert "1 trades" in capsys.readouterr().out
