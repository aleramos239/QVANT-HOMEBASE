"""The store of promoted Lab strategies (~/.homebase/desklab): whole-file writes, history that outlives a removal, and a
file that does not read left out of a listing. Every test works in tmp_path: never the real folder."""
import datetime as dt
import hashlib
import json

import pytest

from homebase.labrun import store

BUNDLE = {"run": {"inputs": {"sl_pts": 20.0}, "qty": 2, "range": {"kind": "custom", "start": "2024-03-01", "end": "2024-03-31"},
                  "commission": 2.5, "slippage_ticks": 2.0,
                  "report": {"summary": {"all": {"net_profit": 1234.5, "trades": 41, "win_rate": 48.8, "profit_factor": 1.31,
                                                 "max_drawdown": -2100.0, "sharpe": 1.0}}}}}
META = {"name": "Bar breakout", "root": "NQ"}
SRC = "class X: pass\n"
NOW = dt.datetime(2026, 10, 9, 12, 0, 5, 777, tzinfo=dt.timezone.utc)


def rec(name="nq_x", promoted="2026-10-09T12:00:00+00:00", **kw):
    return {"name": name, "id": f"draft_{name}", "label": name, "root": "NQ", "source": SRC, "sha256": "ab", "params": {}, "qty": 1,
            "run": {"id": "r1"}, "notes": [], "promoted_utc": promoted, "enabled": True, **kw}


def day(date, **kw):
    return {"date": date, "sha256": "ab", "state": "done", "why": None, "orders": [], "trades": [], "net": 0.0, "match": None,
            "updated_utc": "2026-10-09T20:00:00+00:00", **kw}


def test_snapshot_is_the_record_the_runner_reads():
    s = store.snapshot("nq_x", SRC, META, BUNDLE, "20261009-1-draft_nq_x-ab12", ["It sets its own size."], now=NOW)
    assert s == {"name": "nq_x", "id": "draft_nq_x", "label": "Bar breakout", "root": "NQ", "source": SRC,
                 "sha256": hashlib.sha256(SRC.encode("utf-8")).hexdigest(), "params": {"sl_pts": 20.0}, "qty": 2,
                 "run": {"id": "20261009-1-draft_nq_x-ab12", "range": BUNDLE["run"]["range"], "net": 1234.5, "trades": 41,
                         "win_rate": 48.8, "profit_factor": 1.31, "max_drawdown": -2100.0},
                 "notes": ["It sets its own size."], "promoted_utc": "2026-10-09T12:00:05+00:00", "enabled": False,
                 "commission": 2.5, "slippage_ticks": 2.0,                              # D1: the run's costs, frozen
                 "session_window": ["09:25", "16:00"], "bar_minutes": 0}                 # (the Strategy defaults)


def test_snapshot_carries_the_session_window_and_the_bar_size_the_page_shows():
    meta = {**META, "session_window": ["09:30", "11:30"], "bar_minutes": 5}
    s = store.snapshot("nq_x", SRC, meta, BUNDLE, "r1", [], now=NOW)
    assert s["session_window"] == ["09:30", "11:30"] and s["bar_minutes"] == 5


def test_snapshot_leaves_a_missing_number_none_and_falls_back_to_the_name():
    s = store.snapshot("nq_x", SRC, {"root": "NQ"}, {"run": {"inputs": {}, "qty": 1, "range": {}}}, "r1", [])
    assert s["label"] == "nq_x" and s["run"]["net"] is None and s["run"]["profit_factor"] is None and s["run"]["trades"] is None
    assert s["params"] == {} and s["promoted_utc"] and s["enabled"] is False
    assert s["commission"] is None and s["slippage_ticks"] is None              # a run that does not say: the defaults, later


def test_a_promoted_strategy_lands_off_and_so_does_one_promoted_again_while_it_was_on(tmp_path):
    """The owner, 2026-10-09: it is on the Desk and automatically off; he turns it on."""
    store.put(store.snapshot("nq_x", SRC, META, BUNDLE, "r1", [], now=NOW), tmp_path)
    assert store.get("nq_x", tmp_path)["enabled"] is False
    assert store.set_enabled("nq_x", True, tmp_path)["enabled"] is True
    store.put(store.snapshot("nq_x", SRC + "# newer\n", META, BUNDLE, "r2", [], now=NOW), tmp_path)     # promoted again
    assert store.get("nq_x", tmp_path)["enabled"] is False                      # new code starts off


def test_put_get_round_trip_and_replace(tmp_path):
    assert store.get("nq_x", tmp_path) is None
    store.put(rec(qty=1), tmp_path)
    store.put(rec(qty=3), tmp_path)
    assert store.get("nq_x", tmp_path)["qty"] == 3
    assert (tmp_path / "nq_x.json").is_file() and not list(tmp_path.glob(".*.tmp"))


def test_listing_is_latest_promoted_first_and_skips_what_does_not_read(tmp_path):
    assert store.listing(tmp_path) == []
    store.put(rec("a_old", "2026-10-01T00:00:00+00:00"), tmp_path)
    store.put(rec("b_new", "2026-10-09T00:00:00+00:00"), tmp_path)
    (tmp_path / "broken.json").write_text("{not json")
    (tmp_path / "Other Name.json").write_text("{}")
    (tmp_path / "wrong_name.json").write_text(json.dumps(rec("other")))        # the file name must match the record
    (tmp_path / "runner.json").write_text(json.dumps({"pid": 1}))               # the heartbeat is not a strategy
    assert [s["name"] for s in store.listing(tmp_path)] == ["b_new", "a_old"]


def test_remove_keeps_the_history(tmp_path):
    store.put(rec(), tmp_path)
    store.put_day("nq_x", day("2026-10-08"), tmp_path)
    store.journal("nq_x", {"at": "x"}, tmp_path)
    assert store.remove("nq_x", tmp_path) is True
    assert store.get("nq_x", tmp_path) is None and store.listing(tmp_path) == []
    assert store.get_day("nq_x", "2026-10-08", tmp_path)["date"] == "2026-10-08"
    assert (tmp_path / "nq_x" / "journal.jsonl").is_file()
    assert store.remove("nq_x", tmp_path) is False                              # already gone: not an error


def test_set_enabled(tmp_path):
    store.put(rec(), tmp_path)
    assert store.set_enabled("nq_x", False, tmp_path)["enabled"] is False
    assert store.get("nq_x", tmp_path)["enabled"] is False
    assert store.set_enabled("nq_x", True, tmp_path)["enabled"] is True
    assert store.set_enabled("nq_none", True, tmp_path) is None


def test_day_round_trip_days_order_and_limit(tmp_path):
    assert store.get_day("nq_x", "2026-10-08", tmp_path) is None and store.days("nq_x", 10, tmp_path) == []
    for d in ("2026-10-06", "2026-10-08", "2026-10-07"):
        store.put_day("nq_x", day(d), tmp_path)
    assert store.day_path("nq_x", "2026-10-08", tmp_path) == tmp_path / "nq_x" / "days" / "2026-10-08.json"
    assert [d["date"] for d in store.days("nq_x", 10, tmp_path)] == ["2026-10-08", "2026-10-07", "2026-10-06"]
    assert [d["date"] for d in store.days("nq_x", 2, tmp_path)] == ["2026-10-08", "2026-10-07"]
    (tmp_path / "nq_x" / "days" / "2026-10-09.json").write_text("{not json")
    assert [d["date"] for d in store.days("nq_x", 10, tmp_path)] == ["2026-10-08", "2026-10-07", "2026-10-06"]
    assert not list((tmp_path / "nq_x" / "days").glob(".*.tmp"))


def test_journal_appends_one_json_line_a_call(tmp_path):
    store.journal("nq_x", {"n": 1}, tmp_path)
    store.journal("nq_x", {"n": 2}, tmp_path)
    lines = (tmp_path / "nq_x" / "journal.jsonl").read_text().splitlines()
    assert [json.loads(x) for x in lines] == [{"n": 1}, {"n": 2}]


def test_runner_status_round_trip(tmp_path):
    assert store.get_runner(tmp_path) is None
    st = {"pid": 7, "seen_utc": "2026-10-09T12:00:00+00:00", "source": "http://127.0.0.1:8852", "prices": {}, "hosting": []}
    store.put_runner(st, tmp_path)
    assert store.get_runner(tmp_path) == st
    (tmp_path / "runner.json").write_text("{not json")
    assert store.get_runner(tmp_path) is None


@pytest.mark.parametrize("bad", ["", "Bad", "../x", "a/b", "x", 5, None, "runner"])
def test_bad_names_raise(tmp_path, bad):
    with pytest.raises(ValueError):
        store.get(bad, tmp_path)
    with pytest.raises(ValueError):
        store.remove(bad, tmp_path)
    with pytest.raises(ValueError):
        store.days(bad, 10, tmp_path)
    with pytest.raises(ValueError):
        store.journal(bad, {}, tmp_path)
    with pytest.raises(ValueError):
        store.put({"name": bad}, tmp_path)


@pytest.mark.parametrize("bad", ["2026-10-8", "../2026-10-08", "x", "", None])
def test_bad_dates_raise(tmp_path, bad):
    with pytest.raises(ValueError):
        store.day_path("nq_x", bad, tmp_path)
    with pytest.raises(ValueError):
        store.get_day("nq_x", bad, tmp_path)
    with pytest.raises(ValueError):
        store.put_day("nq_x", day(bad), tmp_path)


def test_the_root_comes_from_the_env_and_never_the_real_folder(tmp_path, monkeypatch):
    monkeypatch.setenv(store.ENV_ROOT, str(tmp_path / "env"))
    assert store.root() == tmp_path / "env" and store.root(tmp_path / "x") == tmp_path / "x"
    store.put(rec())
    assert (tmp_path / "env" / "nq_x.json").is_file()
    monkeypatch.delenv(store.ENV_ROOT)
    assert store.root() == store.Path.home() / ".homebase" / "desklab"


def test_same_promotion_is_the_code_and_the_moment_it_was_promoted():
    """B1. The one place that says whether a day file belongs to a record: the runner and the Desk's list both ask it."""
    r = rec()
    assert store.same_promotion(day("2026-10-08", promoted_utc=r["promoted_utc"]), r) is True
    assert store.same_promotion(day("2026-10-08", promoted_utc="2026-10-01T00:00:00+00:00"), r) is False    # promoted again
    assert store.same_promotion(day("2026-10-08", sha256="cd", promoted_utc=r["promoted_utc"]), r) is False   # other code
    assert store.same_promotion(day("2026-10-08"), r) is True                   # no promoted_utc: by its code alone
    assert store.same_promotion(day("2026-10-08", sha256="cd"), r) is False
    for not_a_day in (None, [], "x", {}):
        assert store.same_promotion(not_a_day, r) is False


def test_every_test_works_in_a_temp_store_without_asking(desklab_root):
    """C3. The conftest points HOMEBASE_DESKLAB_ROOT at a temp folder for every test: none can write the real store."""
    real = store.Path.home() / ".homebase"
    assert store.root() == desklab_root and real not in store.root().parents and list(desklab_root.iterdir()) == []
    store.put(rec())
    store.put_day("nq_x", day("2026-10-08"))
    store.put_runner({"pid": 1})
    assert sorted(x.name for x in desklab_root.iterdir()) == ["nq_x", "nq_x.json", "runner.json"]


# ---- Step B (B1): the desk's sidecar (limits, book, mark), the write lock, the on/off switch's mark check
SIDE = {"mark": ["ab", "2026-10-09T12:00:00+00:00"], "limits": None, "book": [{"account": "main", "qty": 1}],
        "written_utc": "2026-10-10T00:00:00+00:00"}


def test_the_sidecar_round_trips_and_is_never_listed_as_a_strategy(tmp_path):
    assert store.get_desk("nq_x", tmp_path) is None and store.remove_desk("nq_x", tmp_path) is False
    store.put(rec(), tmp_path)
    assert store.put_desk("nq_x", SIDE, tmp_path) == SIDE
    assert (tmp_path / "nq_x.desk.json").is_file() and not list(tmp_path.glob(".*.tmp"))
    assert store.get_desk("nq_x", tmp_path) == SIDE
    assert [s["name"] for s in store.listing(tmp_path)] == ["nq_x"]            # the sidecar is not a record
    assert store.remove("nq_x", tmp_path) is True                               # the record goes; the sidecar is the desk's
    assert store.get_desk("nq_x", tmp_path) == SIDE
    assert store.remove_desk("nq_x", tmp_path) is True and store.get_desk("nq_x", tmp_path) is None
    (tmp_path / "nq_x.desk.json").write_text("{not json")
    assert store.get_desk("nq_x", tmp_path) is None                             # a file that does not read: no sidecar


def test_booked_is_a_sidecar_with_book_rows(tmp_path):
    assert store.booked("nq_x", tmp_path) is False
    store.put_desk("nq_x", {**SIDE, "book": []}, tmp_path)
    assert store.booked("nq_x", tmp_path) is False
    store.put_desk("nq_x", SIDE, tmp_path)
    assert store.booked("nq_x", tmp_path) is True


@pytest.mark.parametrize("bad", ["", "Bad", "../x", "x", 5, None, "runner"])
def test_bad_names_raise_for_the_sidecar_too(tmp_path, bad):
    for call in (lambda: store.get_desk(bad, tmp_path), lambda: store.put_desk(bad, SIDE, tmp_path),
                 lambda: store.remove_desk(bad, tmp_path), lambda: store.booked(bad, tmp_path)):
        with pytest.raises(ValueError):
            call()


def test_mark_of_is_the_code_and_the_moment_it_was_promoted():
    assert store.mark_of(rec()) == ["ab", "2026-10-09T12:00:00+00:00"]
    assert store.mark_of({}) == [None, None]


def test_set_enabled_with_a_mark_refuses_a_record_promoted_again(tmp_path):
    store.put(rec(enabled=False), tmp_path)
    old = store.mark_of(store.get("nq_x", tmp_path))
    assert store.set_enabled("nq_x", True, tmp_path, mark=old)["enabled"] is True
    assert store.set_enabled("nq_x", True, tmp_path, mark=tuple(old))["enabled"] is True      # a tuple is the same mark
    store.put(rec(promoted="2026-10-10T08:00:00+00:00", enabled=False), tmp_path)             # promoted again: lands off
    assert store.set_enabled("nq_x", True, tmp_path, mark=old) is None                        # the old mark: refused
    assert store.get("nq_x", tmp_path)["enabled"] is False                                    # and nothing was written
    assert store.set_enabled("nq_x", True, tmp_path)["enabled"] is True                       # no mark: as before
    assert store.set_enabled("nq_none", True, tmp_path, mark=old) is None


def test_a_thread_may_take_the_write_lock_twice_and_it_leaves_no_file_behind(tmp_path):
    with store.write_lock(tmp_path):
        with store.write_lock(tmp_path):                                        # the same thread: no deadlock
            store.put(rec(), tmp_path)                                          # put takes it again itself
            store.put_desk("nq_x", SIDE, tmp_path)
            assert store.set_enabled("nq_x", False, tmp_path)["enabled"] is False
            assert store.remove("nq_x", tmp_path) is True and store.remove_desk("nq_x", tmp_path) is True
    assert list(tmp_path.iterdir()) == [] and store.listing(tmp_path) == []     # the lock is the folder itself


def test_a_second_writer_waits_for_the_lock_and_a_bounded_wait_gives_up(tmp_path):
    import threading
    inside, release, got = threading.Event(), threading.Event(), []

    def holder():
        with store.write_lock(tmp_path):
            inside.set()
            release.wait(5)

    t = threading.Thread(target=holder)
    t.start()
    assert inside.wait(5)
    with pytest.raises(TimeoutError):                                           # held by another thread: a bounded wait ends
        store.put_desk("nq_x", SIDE, tmp_path, wait_s=0.05)
    assert store.get_desk("nq_x", tmp_path) is None                             # and nothing was written

    def writer():
        store.put_desk("nq_x", SIDE, tmp_path)                                  # no bound: it waits its turn
        got.append(True)

    w = threading.Thread(target=writer)
    w.start()
    w.join(0.1)
    assert got == []                                                            # still waiting
    release.set()
    t.join(5), w.join(5)
    assert got == [True] and store.get_desk("nq_x", tmp_path) == SIDE


def test_the_lock_is_held_across_processes(tmp_path):
    """flock on the root folder: the chart service (Promote) and the desk (the sidecar) are two processes."""
    import subprocess
    import sys
    code = ("import sys; from homebase.labrun import store\n"
            "try:\n    store.put_desk('nq_x', {'book': []}, sys.argv[1], wait_s=0.05)\n    print('wrote')\n"
            "except TimeoutError:\n    print('busy')\n")
    with store.write_lock(tmp_path):
        out = subprocess.run([sys.executable, "-c", code, str(tmp_path)], capture_output=True, text=True, timeout=30)
    assert out.stdout.strip() == "busy", out.stderr
    out = subprocess.run([sys.executable, "-c", code, str(tmp_path)], capture_output=True, text=True, timeout=30)
    assert out.stdout.strip() == "wrote", out.stderr


def test_the_store_keeps_the_drafts_name_rule_without_importing_the_draft_helper():
    """The desk process reads this store (Step B) and must never load homebase.draftstore
    (tests/test_claude_drafts.py::test_importing_the_desk_never_loads_a_draft): the store carries the rule itself."""
    import subprocess
    import sys

    from homebase import draftstore
    assert store.NAME_RE.pattern == draftstore.NAME_RE.pattern and store.NAME_RE.flags == draftstore.NAME_RE.flags
    code = ("import sys, homebase.labrun.store, homebase.labcfg, homebase.labdesk\n"
            "bad = sorted(m for m in sys.modules if m == 'homebase.draftstore' or m.startswith('homebase.backtest'))\n"
            "print(bad); sys.exit(1 if bad else 0)\n")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stdout + out.stderr


# ---- fix round 1: the desk's own lock, the sidecars' names, a bounded wait on the switch
def test_desk_names_are_the_sidecars_whatever_became_of_their_records(tmp_path):
    assert store.desk_names(tmp_path) == []
    store.put(rec("a_one"), tmp_path)
    store.put_desk("a_one", SIDE, tmp_path)
    store.put_desk("b_gone", SIDE, tmp_path)                                    # its record is no longer there
    (tmp_path / "Bad Name.desk.json").write_text("{}")
    (tmp_path / "runner.json").write_text("{}")
    assert store.desk_names(tmp_path) == ["a_one", "b_gone"]


def test_one_desk_holds_the_stores_desk_lock_until_it_lets_go(tmp_path):
    a = store.desk_lock(tmp_path / "new-store")                                 # the folder is made
    assert a is not None and (tmp_path / "new-store" / "desk.lock").is_file()
    assert store.desk_lock(tmp_path / "new-store") is None                      # a second desk, even in this process
    assert store.listing(tmp_path / "new-store") == [] and store.desk_names(tmp_path / "new-store") == []   # not a record
    store.put(rec(), tmp_path / "new-store")                                    # the desk's lock is not the write lock
    store.desk_unlock(a)
    b = store.desk_lock(tmp_path / "new-store")
    assert b is not None
    store.desk_unlock(b)


def test_the_desk_lock_is_held_across_processes_and_ends_with_the_process(tmp_path):
    import subprocess
    import sys
    code = ("import sys, time; from homebase.labrun import store\n"
            "fd = store.desk_lock(sys.argv[1]); print('held' if fd is not None else 'busy', flush=True); time.sleep(30)\n")
    p = subprocess.Popen([sys.executable, "-c", code, str(tmp_path)], stdout=subprocess.PIPE, text=True)
    try:
        assert p.stdout.readline().strip() == "held"
        assert store.desk_lock(tmp_path) is None
    finally:
        p.kill()
        p.wait(10)
    fd = store.desk_lock(tmp_path)                                              # the OS gave it back
    assert fd is not None
    store.desk_unlock(fd)


def test_set_enabled_with_a_bounded_wait_gives_up_and_writes_nothing(tmp_path):
    import threading
    store.put(rec(enabled=False), tmp_path)
    inside, release = threading.Event(), threading.Event()

    def holder():
        with store.write_lock(tmp_path):
            inside.set()
            release.wait(5)
    t = threading.Thread(target=holder)
    t.start()
    assert inside.wait(5)
    try:
        with pytest.raises(TimeoutError):
            store.set_enabled("nq_x", True, tmp_path, wait_s=0.05)
    finally:
        release.set()
        t.join(5)
    assert store.get("nq_x", tmp_path)["enabled"] is False
    assert store.set_enabled("nq_x", True, tmp_path, wait_s=0.05)["enabled"] is True


def test_a_wait_of_zero_never_sleeps(tmp_path):
    import threading
    import time
    inside, release = threading.Event(), threading.Event()

    def holder():
        with store.write_lock(tmp_path):
            inside.set()
            release.wait(5)
    t = threading.Thread(target=holder)
    t.start()
    assert inside.wait(5)
    try:
        t0 = time.perf_counter()
        with pytest.raises(TimeoutError):
            store.put_desk("nq_x", SIDE, tmp_path, wait_s=0.0)
        assert time.perf_counter() - t0 < 0.05
    finally:
        release.set()
        t.join(5)
