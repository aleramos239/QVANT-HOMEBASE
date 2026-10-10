"""The store of promoted Lab strategies (~/.homebase/desklab): whole-file writes, history that outlives a removal, and a
file that does not read left out of a listing. Every test works in tmp_path: never the real folder."""
import datetime as dt
import hashlib
import json

import pytest

from homebase.labrun import store

BUNDLE = {"run": {"inputs": {"sl_pts": 20.0}, "qty": 2, "range": {"kind": "custom", "start": "2024-03-01", "end": "2024-03-31"},
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
                 "session_window": ["09:25", "16:00"], "bar_minutes": 0}                 # (the Strategy defaults)


def test_snapshot_carries_the_session_window_and_the_bar_size_the_page_shows():
    meta = {**META, "session_window": ["09:30", "11:30"], "bar_minutes": 5}
    s = store.snapshot("nq_x", SRC, meta, BUNDLE, "r1", [], now=NOW)
    assert s["session_window"] == ["09:30", "11:30"] and s["bar_minutes"] == 5


def test_snapshot_leaves_a_missing_number_none_and_falls_back_to_the_name():
    s = store.snapshot("nq_x", SRC, {"root": "NQ"}, {"run": {"inputs": {}, "qty": 1, "range": {}}}, "r1", [])
    assert s["label"] == "nq_x" and s["run"]["net"] is None and s["run"]["profit_factor"] is None and s["run"]["trades"] is None
    assert s["params"] == {} and s["promoted_utc"] and s["enabled"] is False


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
