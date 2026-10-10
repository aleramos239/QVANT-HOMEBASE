"""The daily match (labrun/match.py): did the Desk's shadow day equal the backtest of that day? `compare` is pure; the
backtest itself is run once for real (in the sandbox, on a synthetic archive in tmp_path) and, for the plumbing, through
a launcher that writes the bundle by hand. Nothing here talks to a service or writes outside tmp_path."""
from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from homebase.backtest import sandbox
from homebase.backtest.runner import read_json, write_json
from homebase.backtest.slots import Slots
from homebase.backtest.tape import et_ns
from homebase.labrun import host, match
from homebase.labrun.match import MatchUnavailable, compare, match_day
from tests.backtest_util import D1, D2, ms, nq_archive
from tests.charts_util import rows
from tests.test_labrun_host import HEAD, plain, rec

SEC = 1_000_000_000
TICK = 0.25
T0 = et_ns(D1, "09:30:02")


def trade(**kw) -> dict:
    """An engine Trade.to_dict() row, with the fields the match reads."""
    return {"side": "long", "qty": 1, "entry_ns": T0, "entry_price": 21450.25, "exit_ns": T0 + 60 * SEC,
            "exit_price": 21470.0, "exit_reason": "tp", **kw}


# ---------------------------------------------------------------- compare
def test_no_trades_on_both_sides_is_a_match():
    assert compare([], [], TICK) == {"ok": True, "text": "No trades, same as the backtest."}


def test_trades_that_agree_are_matched_with_a_count():
    both = [trade(), trade(entry_ns=T0 + 600 * SEC, exit_ns=T0 + 900 * SEC)]
    assert compare(both, [dict(t) for t in both], TICK) == {"ok": True, "text": "Matched the backtest: 2 of 2 trades."}
    assert compare([trade()], [trade()], TICK) == {"ok": True, "text": "Matched the backtest: 1 of 1 trade."}


@pytest.mark.parametrize("desk, tester, text", [
    (0, 3, "Did not match: the backtest took 3 trades, the Desk 0."),
    (2, 3, "Did not match: the backtest took 3 trades, the Desk 2."),
    (3, 1, "Did not match: the backtest took 1 trade, the Desk 3."),
])
def test_a_different_number_of_trades_says_both_counts(desk, tester, text):
    assert compare([trade()] * desk, [trade()] * tester, TICK) == {"ok": False, "text": text}


@pytest.mark.parametrize("change, text", [
    ({"side": "short"}, "side long on the Desk, short in the backtest."),
    ({"qty": 2}, "size 1 on the Desk, 2 in the backtest."),
    ({"entry_ns": T0 + 3 * SEC}, "entry time 09:30:02 on the Desk, 09:30:05 in the backtest."),
    ({"entry_price": 21451.0}, "entry price 21,450.25 on the Desk, 21,451.00 in the backtest."),
    ({"exit_ns": T0 + 70 * SEC}, "exit time 09:31:02 on the Desk, 09:31:12 in the backtest."),
    ({"exit_price": 21471.0}, "exit price 21,470.00 on the Desk, 21,471.00 in the backtest."),
    ({"exit_reason": "sl"}, "exit tp on the Desk, sl in the backtest."),
])
def test_each_field_that_differs_is_named(change, text):
    got = compare([trade()], [trade(**change)], TICK)
    assert got == {"ok": False, "text": f"Did not match at trade 1: {text}"}


def test_the_first_trade_that_differs_is_named_with_its_number_and_the_first_field_in_order():
    desk = [trade(), trade(entry_price=21450.25, exit_price=21470.0), trade()]
    tester = [trade(), trade(entry_price=21451.0, exit_price=21490.0, side="short"), trade(qty=5)]
    assert compare(desk, tester, TICK)["text"] == "Did not match at trade 2: side long on the Desk, short in the backtest."
    tester[1]["side"] = "long"
    assert compare(desk, tester, TICK)["text"] == ("Did not match at trade 2: entry price 21,450.25 on the Desk, "
                                                   "21,451.00 in the backtest.")


def test_times_agree_up_to_two_seconds_and_prices_up_to_two_ticks():
    edge = trade(entry_ns=T0 + 2 * SEC, exit_ns=T0 + 60 * SEC - 2 * SEC, entry_price=21450.25 + 0.5, exit_price=21470.0 - 0.5)
    assert compare([trade()], [edge], TICK)["ok"] is True
    assert compare([edge], [trade()], TICK)["ok"] is True
    assert compare([trade()], [trade(entry_ns=T0 + 2 * SEC + 1)], TICK)["ok"] is False
    assert compare([trade()], [trade(exit_ns=T0 + 60 * SEC - 2 * SEC - 1)], TICK)["ok"] is False
    assert compare([trade()], [trade(entry_price=21450.25 + 0.75)], TICK)["ok"] is False
    assert compare([trade()], [trade(exit_price=21470.0 - 0.75)], TICK)["ok"] is False


def test_two_ticks_is_two_ticks_whatever_the_float_noise():
    assert compare([trade(entry_price=64.01)], [trade(entry_price=64.01 + 0.02)], 0.01)["ok"] is True
    assert compare([trade(entry_price=64.01)], [trade(entry_price=64.01 + 0.03)], 0.01)["ok"] is False
    assert compare([trade(entry_price=64.01)], [trade(entry_price=64.04)], 0.01)["text"].endswith("64.01 on the Desk, 64.04 in the backtest.")


def test_a_summary_trade_row_reads_as_an_engine_row():
    row = {"side": "short", "qty": 2, "entry_t": "09:30:02", "entry_px": 21450.25, "exit_t": "09:31:02", "exit_px": 21440.0,
           "reason": "sl", "net": -5.0}
    assert match.from_summary([row], D1) == [{"side": "short", "qty": 2, "entry_ns": T0, "entry_price": 21450.25,
                                              "exit_ns": T0 + 60 * SEC, "exit_price": 21440.0, "exit_reason": "sl"}]


# ---------------------------------------------------------------- the tester on one day
SOURCE = HEAD + '''class M(Strategy):
    id = "m"
    name = "M"
    root = "NQ"
    session_independent = True

    def times(self):
        return ["09:30:00", "15:55"]

    def on_time(self, ctx, et_time):
        if et_time == "09:30:00":
            ctx.market("long", sl=ctx.last_price - 10, ref=ctx.last_price)
        else:
            ctx.flatten("time")
'''
RECORD = rec(SOURCE)
NEED_SANDBOX = pytest.mark.skipif(not sandbox.available(), reason="no working sandbox-exec on this machine")


def recorded(base, *days) -> None:
    """Mark the archive's day as the tick job leaves it once the day's recording is merged in: a `live` source in the
    manifest's merge log (tickarchive.merge_session)."""
    for d in days:
        (man,) = (Path(base) / "NQ" / str(d.year)).glob(f"{d.isoformat()}_*.json")
        man.write_text(json.dumps({**json.loads(man.read_text()), "sources": [
            {"kind": "history", "ticks": 5, "at_utc": "2024-03-05T15:00:00+00:00"},
            {"kind": "live", "file": man.name.replace(".json", ".live.csv.gz"), "bytes": 1, "mtime_ns": 1,
             "at_utc": "2024-03-05T21:10:00+00:00"}]}))


def dirs(tmp_path, stored: bool = True) -> dict:
    """Where a match works. stored: the archive holds D1 and D2 (nq_archive), merged with their recordings."""
    if stored and not (tmp_path / "ticks").exists():
        nq_archive(tmp_path / "ticks")
        recorded(tmp_path / "ticks", D1, D2)
    return {"base": tmp_path / "match", "archive": tmp_path / "ticks", "cache": tmp_path / "cache", "python": sys.executable}


class Fake:
    """A launcher that writes the finished bundle by hand and starts a harmless process, as runner.launch starts the
    backtest child. `run` is the request the validated run dir holds; `procs` the children it started."""

    def __init__(self, coverage=None, trades=(), status="done", child="pass"):
        self.coverage = coverage or {"sessions": 1, "used": 1, "skipped": [], "no_trade": []}
        self.trades, self.status, self.child = list(trades), status, child
        self.procs, self.requests = [], []

    def __call__(self, run_dir, python, archive, cache, slot, extra=()):
        run_dir = Path(run_dir)
        self.requests.append(read_json(run_dir / "request.json"))
        write_json(run_dir / "status.json", {"status": self.status, "error": "boom"})
        write_json(run_dir / "run.json", {"coverage": self.coverage})
        write_json(run_dir / "trades.json", [{**{k: v for k, v in t.items() if not k.endswith("_ns")},
                                              "entry_ms": t["entry_ns"] // 1_000_000, "exit_ms": t["exit_ns"] // 1_000_000}
                                             for t in self.trades])
        for f in ("equity.json", "plots.json", "propsim.json"):
            write_json(run_dir / f, {})
        self.procs.append(subprocess.Popen([sys.executable, "-c", self.child]))
        return self.procs[-1]

    def reap(self):
        for p in self.procs:
            if p.poll() is None:
                p.kill()
            p.wait()


@pytest.fixture
def fake():
    made = []

    def make(**kw):
        made.append(Fake(**kw))
        return made[-1]
    yield make
    for f in made:
        f.reap()


def free(slots=None) -> bool:
    """The machine's backtest slots are all free (the test's own shared dir)."""
    s = slots or Slots()
    held = [s.try_acquire() for _ in range(s.cap)]
    for h in held:
        if h is not None:
            h.close()
    return None not in held


def test_the_tester_is_asked_for_that_one_day_with_the_frozen_code_settings_and_size(tmp_path, fake):
    f = fake(trades=[trade()])
    record = rec(SOURCE, params={}, qty=3)
    got = match.tester_day(record, D1, launch=f, **dirs(tmp_path))
    (req,) = f.requests
    assert req["strategy"] == "draft_lab_x" and req["qty"] == 3 and req["draft_source"] == SOURCE
    assert (req["range"]["start"], req["range"]["end"]) == (D1.isoformat(), D1.isoformat())
    (t,) = got                                                               # (ms in the bundle, ns back out)
    assert (t["side"], t["entry_ns"], t["exit_ns"], t["exit_reason"]) == ("long", T0, T0 + 60 * SEC, "tp")


def test_the_run_lives_under_the_base_is_cleaned_up_and_the_slot_is_given_back(tmp_path, fake):
    f = fake()
    d = dirs(tmp_path)
    match.tester_day(RECORD, D1, launch=f, **d)
    assert list((d["base"] / "runs").iterdir()) == [] and free() and f.procs[0].poll() is not None


@pytest.mark.parametrize("coverage, why", [
    ({"sessions": 1, "used": 0, "skipped": [{"date": "2024-03-05", "reason": "no tape"}]}, "the day's prices are not stored yet"),
    ({"sessions": 1, "used": 0, "skipped": [{"date": "2024-03-05", "reason": "missing 13:00–16:00 ET"}]},
     "the stored prices for the day have a gap"),
])
def test_a_day_that_cannot_be_read_yet_is_unavailable_with_its_reason(tmp_path, fake, coverage, why):
    with pytest.raises(MatchUnavailable, match=why):
        match.tester_day(RECORD, D1, launch=fake(coverage=coverage), **dirs(tmp_path))
    assert free()


def test_a_run_that_fails_is_unavailable_and_its_folder_is_removed_after_the_error_is_logged(tmp_path, fake, capsys):
    d = dirs(tmp_path)
    with pytest.raises(MatchUnavailable, match="the backtest could not run"):
        match.tester_day(RECORD, D1, launch=fake(status="error"), **d)
    assert list((d["base"] / "runs").iterdir()) == [] and free()
    assert "boom" in capsys.readouterr().err                                 # (the child's own words, for the log)


def test_a_launcher_that_cannot_start_is_unavailable_and_leaves_no_run_folder(tmp_path):
    def broken(*a, **k):
        raise OSError("no such python")
    d = dirs(tmp_path)
    with pytest.raises(MatchUnavailable, match="the backtest could not run"):
        match.tester_day(RECORD, D1, launch=broken, **d)
    assert list((d["base"] / "runs").iterdir()) == [] and free()


def test_a_run_past_the_timeout_is_stopped_with_the_runners_stop_proc_and_unavailable(tmp_path, fake):
    f = fake(child="import time; time.sleep(60)")
    with pytest.raises(MatchUnavailable, match="the backtest took too long"):
        match.tester_day(RECORD, D1, launch=f, timeout_s=0.3, **dirs(tmp_path))
    assert f.procs[0].poll() is not None and free()


def test_no_free_slot_for_the_whole_wait_is_a_busy_tester_and_no_run_is_made(tmp_path, fake):
    """C1. The worker waits in line (it is in its own thread), but not for ever."""
    one = Slots(tmp_path / "slots", cap=1, poll=0.02)
    taken = one.try_acquire()
    f = fake()
    t = time.monotonic()
    try:
        with pytest.raises(MatchUnavailable, match="the tester is busy"):
            match.tester_day(RECORD, D1, launch=f, slots=one, slot_wait_s=0.3, **dirs(tmp_path))
    finally:
        taken.close()
    assert 0.3 <= time.monotonic() - t < 5.0
    assert f.procs == [] and not (dirs(tmp_path)["base"] / "runs").exists() and list(one.queue.iterdir()) == []


def test_a_slot_that_frees_while_the_worker_waits_is_taken_and_the_day_is_run(tmp_path, fake):
    one = Slots(tmp_path / "slots", cap=1, poll=0.02)
    taken = one.try_acquire()
    threading.Timer(0.2, taken.close).start()
    f = fake(trades=[trade()])
    got = match.tester_day(RECORD, D1, launch=f, slots=one, slot_wait_s=10, **dirs(tmp_path))
    assert len(got) == 1 and len(f.procs) == 1 and free(one)


def test_the_worker_waits_twenty_minutes_for_a_slot_by_default():
    import inspect
    assert match.SLOT_WAIT_S == 20 * 60
    assert inspect.signature(match.tester_day).parameters["slot_wait_s"].default == match.SLOT_WAIT_S


def test_no_backtest_starts_in_the_quiet_window_however_long_the_worker_waits(tmp_path, fake):
    quiet = Slots(tmp_path / "slots", cap=1, poll=0.02, clock=lambda: dt.datetime(2026, 9, 28, 9, 25, tzinfo=host.ET))
    f = fake()
    with pytest.raises(MatchUnavailable, match="the tester is busy"):
        match.tester_day(RECORD, D1, launch=f, slots=quiet, slot_wait_s=0.3, **dirs(tmp_path))
    assert f.procs == []


# ---------------------------------------------------------------- C1: the day must be in the archive first
def test_a_day_whose_recording_is_not_merged_into_the_archive_yet_is_not_stored_even_if_a_fragment_exists(tmp_path, fake):
    """The tick job merges the day's recording into the archive after the close and logs it in the manifest as a
    `live` source. Until then the file is a fragment (an hourly fill): the tester is not even started."""
    d = dirs(tmp_path, stored=False)
    f = fake(trades=[trade()])
    with pytest.raises(MatchUnavailable, match="the day's prices are not stored yet"):
        match.tester_day(RECORD, D1, launch=f, **d)                             # no archive at all
    nq_archive(d["archive"])                                                  # the file and its manifest, no `live` source
    assert match.stored("NQ", D1, d["archive"], d["cache"]) is False
    with pytest.raises(MatchUnavailable, match="the day's prices are not stored yet"):
        match.tester_day(RECORD, D1, launch=f, **d)
    assert match_day(RECORD, D1, [trade()], launch=f, **d) == {"ok": None, "text": "Not checked yet: the day's prices are not stored yet."}
    assert f.procs == [] and not (d["base"] / "runs").exists() and free()     # nothing was run, no slot was taken
    recorded(d["archive"], D1)                                                # the tick job merged the recording
    assert match.stored("NQ", D1, d["archive"], d["cache"]) is True
    assert match_day(RECORD, D1, [trade()], launch=f, **d) == {"ok": True, "text": "Matched the backtest: 1 of 1 trade."}


@pytest.mark.parametrize("sources", [None, [], "live", [{"kind": "history"}, {"kind": "massive"}], [None, "live", 5]])
def test_only_a_live_source_in_the_manifest_says_the_day_is_stored(tmp_path, sources):
    d = dirs(tmp_path, stored=False)
    nq_archive(d["archive"])
    (man,) = (d["archive"] / "NQ" / "2024").glob(f"{D1}_*.json")
    man.write_text(json.dumps({**json.loads(man.read_text()), "sources": sources}))
    assert match.stored("NQ", D1, d["archive"], d["cache"]) is False
    man.write_text("{not json")
    assert match.stored("NQ", D1, d["archive"], d["cache"]) is False


def test_no_sandbox_is_unavailable_and_nothing_is_launched(tmp_path, fake, monkeypatch):
    monkeypatch.setattr(sandbox, "available", lambda: False)
    f = fake()
    with pytest.raises(MatchUnavailable, match="the sandbox is not working"):
        match.tester_day(RECORD, D1, launch=f, **dirs(tmp_path))
    assert f.procs == [] and free()


@NEED_SANDBOX
def test_the_real_tester_runs_the_frozen_code_on_one_recorded_day_in_the_sandbox(tmp_path):
    d = dirs(tmp_path)
    got = match.tester_day(RECORD, D1, **d)
    (t,) = got
    assert (t["side"], t["qty"], t["exit_reason"]) == ("long", 1, "eod") and t["entry_ns"] == t["entry_ns"] // 1_000_000 * 1_000_000
    assert dt.datetime.fromtimestamp(t["entry_ns"] / SEC, host.ET).strftime("%H:%M") == "09:30"
    assert list((d["base"] / "runs").iterdir()) == [] and free()
    with pytest.raises(MatchUnavailable, match="the stored prices for the day have a gap"):
        match.tester_day(RECORD, dt.date(2024, 3, 6), **d)                         # prints stop at 12:59
    with pytest.raises(MatchUnavailable, match="not stored yet"):
        match.tester_day(RECORD, dt.date(2024, 3, 7), **d)                         # nothing recorded


@NEED_SANDBOX
def test_a_shadow_day_on_the_recorded_prints_matches_the_real_tester_on_them(tmp_path):
    """The whole check: the runner's day on the prints of nq_archive's D1, against the tester on the archive."""
    prints = rows(ms(D1, "09:25:00"), [100.0] * 290) + rows(ms(D1, "09:30:01"), [110.0, 112.0, 126.0]) \
        + rows(ms(D1, "09:31:00"), [120.0] * 1500, step_ms=15_000)
    shadow = host.run_day(RECORD, [(r["ts_ms"] * 1_000_000, r["price"], r["size"]) for r in prints], D1, spawn=plain)
    assert len(shadow["trades"]) == 1
    assert match_day(RECORD, D1, shadow["trades"], **dirs(tmp_path)) == {"ok": True, "text": "Matched the backtest: 1 of 1 trade."}
    assert match_day(RECORD, D1, [], **dirs(tmp_path))["text"] == "Did not match: the backtest took 1 trade, the Desk 0."


# ---------------------------------------------------------------- match_day
def test_match_day_compares_the_shadow_trades_with_the_testers(tmp_path, fake):
    kw = dirs(tmp_path)
    assert match_day(RECORD, D1, [trade()], launch=fake(trades=[trade()]), **kw) == {
        "ok": True, "text": "Matched the backtest: 1 of 1 trade."}
    assert match_day(RECORD, D1, [], launch=fake(trades=[trade()]), **kw) == {
        "ok": False, "text": "Did not match: the backtest took 1 trade, the Desk 0."}
    got = match_day(RECORD, D1, [trade(entry_price=21460.0)], launch=fake(trades=[trade()]), **kw)
    assert got["text"] == "Did not match at trade 1: entry price 21,460.00 on the Desk, 21,450.25 in the backtest."


@pytest.mark.parametrize("make, text", [
    (dict(coverage={"sessions": 1, "skipped": [{"date": "2024-03-05", "reason": "no tape"}]}),
     "Not checked yet: the day's prices are not stored yet."),
    (dict(status="error"), "Not checked yet: the backtest could not run."),
])
def test_match_day_turns_an_unavailable_day_into_not_checked_yet(tmp_path, fake, make, text):
    assert match_day(RECORD, D1, [], launch=fake(**make), **dirs(tmp_path)) == {"ok": None, "text": text}


# ---------------------------------------------------------------- a day the tester could not really run
def with_no_trade(reason: str) -> dict:
    return {"sessions": 1, "used": 1, "skipped": [], "no_trade": [{"date": D1.isoformat(), "reason": reason}]}


@pytest.mark.parametrize("shadow", [[], [trade()]])
def test_a_strategy_that_failed_in_the_backtest_is_a_mismatch_never_no_trades(tmp_path, fake, shadow):
    f = fake(coverage=with_no_trade("strategy error: division by zero"))
    with pytest.raises(match.StrategyFailed):
        match.tester_day(RECORD, D1, launch=f, **dirs(tmp_path))
    got = match_day(RECORD, D1, shadow, launch=fake(coverage=with_no_trade("strategy error: boom")), **dirs(tmp_path))
    assert got == {"ok": False, "text": "Did not match: the strategy failed in the backtest."}


def test_a_missing_print_at_a_fire_time_is_a_gap_in_the_prices_not_a_quiet_day(tmp_path, fake):
    with pytest.raises(MatchUnavailable, match="the day's prices have a gap"):
        match.tester_day(RECORD, D1, launch=fake(coverage=with_no_trade("no print before 09:30")), **dirs(tmp_path))
    got = match_day(RECORD, D1, [], launch=fake(coverage=with_no_trade("no print before 09:30")), **dirs(tmp_path))
    assert got == {"ok": None, "text": "Not checked yet: the day's prices have a gap."}


def test_a_strategys_own_skip_with_no_trades_is_a_real_no_trade_day(tmp_path, fake):
    f = fake(coverage=with_no_trade("outside the range today"))
    assert match_day(RECORD, D1, [], launch=f, **dirs(tmp_path)) == {"ok": True, "text": "No trades, same as the backtest."}
    assert match_day(RECORD, D1, [trade()], launch=fake(coverage=with_no_trade("outside the range today")),
                     **dirs(tmp_path))["text"] == "Did not match: the backtest took 0 trades, the Desk 1."


def test_a_day_the_strategy_does_not_trade_is_not_checked_and_not_retried(tmp_path, fake):
    none = {"sessions": 0, "used": 0, "skipped": [], "no_trade": []}
    with pytest.raises(match.DoesNotTrade):
        match.tester_day(RECORD, D1, launch=fake(coverage=none), **dirs(tmp_path))
    assert match_day(RECORD, D1, [], launch=fake(coverage=none), **dirs(tmp_path)) == {
        "ok": None, "text": "Not checked: it does not trade that day."}
    assert not match.retry(match_day(RECORD, D1, [], launch=fake(coverage=none), **dirs(tmp_path)))
    got = match_day(RECORD, dt.date(2024, 3, 7), [], launch=fake(coverage=none), **dirs(tmp_path))   # nothing recorded
    assert got["text"] == "Not checked yet: the day's prices are not stored yet." and match.retry(got)


def test_only_a_not_checked_yet_is_asked_again():
    assert match.retry({"ok": None, "text": "Not checked yet: the tester is busy."})
    assert not match.retry({"ok": None, "text": "Not checked: it was stopped."})
    assert not match.retry({"ok": True, "text": "Matched the backtest: 1 of 1 trade."})
    assert not match.retry({"ok": False, "text": "Did not match: the strategy failed in the backtest."})


RAISES = SOURCE.replace('ctx.market("long", sl=ctx.last_price - 10, ref=ctx.last_price)', 'raise RuntimeError("boom")')
OFF_TODAY = SOURCE.replace("    def times(self):", "    def trades_on(self, d):\n        return False\n\n    def times(self):")


@NEED_SANDBOX
def test_the_real_tester_reports_a_strategy_that_raises_and_one_that_does_not_trade_today(tmp_path):
    assert match_day(rec(RAISES), D1, [], **dirs(tmp_path)) == {
        "ok": False, "text": "Did not match: the strategy failed in the backtest."}
    assert match_day(rec(OFF_TODAY), D1, [], **dirs(tmp_path)) == {
        "ok": None, "text": "Not checked: it does not trade that day."}
    assert list((dirs(tmp_path)["base"] / "runs").iterdir()) == [] and free()


# ---------------------------------------------------------------- run folders
def test_a_folder_is_removed_only_from_inside_the_match_runs_folder(tmp_path):
    base = tmp_path / "match"
    inside, outside = base / "runs" / "r1", tmp_path / "elsewhere"
    inside.mkdir(parents=True)
    outside.mkdir()
    (outside / "keep.txt").write_text("x")
    match.drop(outside, base)
    match.drop(base / "runs" / ".." / ".." / "elsewhere", base)
    match.drop(base / "runs", base)                                          # not even the runs folder itself
    link = base / "runs" / "link"
    link.symlink_to(outside)
    match.drop(link, base)
    assert (outside / "keep.txt").exists() and base.joinpath("runs").is_dir() and inside.is_dir()
    match.drop(inside, base)
    assert not inside.exists()


def test_run_folders_older_than_seven_days_are_cleaned_and_nothing_else(tmp_path):
    import os
    base = tmp_path / "match"
    old, new, other = base / "runs" / "old", base / "runs" / "new", tmp_path / "other"
    for d in (old, new, other):
        d.mkdir(parents=True)
    (base / "runs" / "spends.txt").write_text("a file stays")
    link = base / "runs" / "oldlink"
    link.symlink_to(other)
    for d in (old, other):
        os.utime(d, (1, 1))
    os.utime(link, (1, 1), follow_symlinks=False)
    match.clean(base, now=8 * 86400 + 1)
    assert not old.exists() and new.is_dir() and other.is_dir() and (base / "runs" / "spends.txt").exists()
    match.clean(base / "nowhere")                                            # no folder: nothing to do
