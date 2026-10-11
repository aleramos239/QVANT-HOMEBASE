"""The Setup panel's adjustable settings (2026-10-10, owner: "have it as a adjustable setting in the setup panel"). A
strategy names the inputs the Desk may change (`desk_settings`); Promote carries their specs in the record (`settings`);
the Desk shows them in its status block and writes a changed value into the record's `params`, for the runner's next
session. Never during the strategy's session, the 09:20-09:35 window or an open round; a value outside its spec is a 400."""
from __future__ import annotations

import datetime as dt

import pytest

from homebase import draftstore, labcfg
from homebase.labrun import store
from tests.test_server_lab import (FLATTEN_FIRST, LAB, NOT_ON_DESK, ET, client, journal, no_lab_in_config, open_round,  # noqa: F401
                                   paths, rec, status)

SPEC = [{"key": "open_min", "label": "Opening candle (minutes)", "type": "choice", "default": "5", "min": None, "max": None,
         "step": None, "choices": ["1", "5"]},
        {"key": "big_body", "label": "Big candle: body over (pts)", "type": "float", "default": 25.0, "min": 1, "max": 500,
         "step": 1, "choices": None}]
AFTER_CLOSE = dt.datetime(2026, 9, 30, 17, 0, tzinfo=ET)            # a Wednesday, after the 15:55 window end
BEFORE_OPEN = dt.datetime(2026, 9, 30, 8, 0, tzinfo=ET)


def post(c, settings, name=LAB):
    return c.post("/api/lab-settings", json={"strategy": name, "settings": settings})


@pytest.fixture()
def sc(paths):
    """The desk with one promoted strategy that declares both settings, at 17:00 ET (after its window)."""
    from fastapi.testclient import TestClient
    from tests.test_server_lab import make_client
    store.put(rec(settings=SPEC, params={"open_min": "5", "big_body": 25.0}))
    app = make_client()
    app.state.engine.now_et = lambda: AFTER_CLOSE
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.app, c.cfg, c.engine, c.labdesk, c.tmp = app, app.state.cfg, app.state.engine, app.state.labdesk, paths
        yield c
        app.state.labdesk.close()


# ---------------------------------------------------------------- parsing (labcfg.parse_settings)
def test_parse_settings_checks_each_value_against_its_spec():
    r = {"settings": SPEC}
    assert labcfg.parse_settings({"open_min": "1", "big_body": 30}, r) == {"open_min": "1", "big_body": 30.0}
    assert labcfg.parse_settings({"open_min": 1}, r) == {"open_min": "1"}                  # a number for a choice is read as text
    for bad, why in (({"open_min": "3"}, "one of 1, 5"), ({"open_min": True}, "one of 1, 5"), ({"big_body": 0}, "from 1 to 500"),
                     ({"big_body": 501}, "from 1 to 500"), ({"big_body": "30"}, "a number"), ({"big_body": True}, "a number"),
                     ({"big_body": float("nan")}, "a number"), ({"nope": 1}, "cannot be changed"), ({}, "settings:"),
                     ("x", "settings:")):
        with pytest.raises(ValueError, match=why):
            labcfg.parse_settings(bad, r)
    with pytest.raises(ValueError, match="cannot be changed"):
        labcfg.parse_settings({"open_min": "1"}, {"settings": []})                          # a record that declares none
    with pytest.raises(ValueError, match="cannot be changed"):
        labcfg.parse_settings({"open_min": "1"}, None)


def test_parse_settings_reads_an_on_off_setting():
    r = {"settings": [{"key": "red_5m", "label": "Red-folder days: 5-minute candle", "type": "bool", "default": False}]}
    assert labcfg.parse_settings({"red_5m": True}, r) == {"red_5m": True}
    assert labcfg.parse_settings({"red_5m": False}, r) == {"red_5m": False}
    for bad in ("true", 1, 0, None):
        with pytest.raises(ValueError, match="on or off"):
            labcfg.parse_settings({"red_5m": bad}, r)


# ---------------------------------------------------------------- what Promote keeps (store.snapshot / draftstore)
def test_the_snapshot_carries_the_declared_settings_and_a_draft_without_them_none():
    meta = {"root": "NQ", "name": "X", "desk_settings": ("open_min", "big_body", "gone"),
            "inputs": [{"key": "open_min", "label": "Opening candle (minutes)", "type": "choice", "default": "5",
                        "choices": ("1", "5"), "min": None, "max": None, "step": None, "extra": 1},
                       {"key": "big_body", "label": "Big", "type": "float", "default": 25.0, "min": 1, "max": 500, "step": 1},
                       {"key": "m_prev", "label": "m", "type": "float", "default": 6.0}]}
    got = store.snapshot("x", "src", meta, {"run": {"qty": 4}}, "r1", [])["settings"]
    assert [s["key"] for s in got] == ["open_min", "big_body"]                              # `gone` is not an input: dropped
    assert got[0]["choices"] == ("1", "5") and "extra" not in got[0]
    assert "settings" not in store.snapshot("x", "src", {"root": "NQ", "inputs": meta["inputs"]}, {"run": {"qty": 4}}, "r1", [])


SRC = '''
class S(Strategy):
    name = "S"
    root = "NQ"
    desk_settings = {names}
    @staticmethod
    def inputs():
        return [Input("a", "A", "float", 1.0, 0, 10, 1), Input("b", "B", "choice", "x", None, None, None, ("x", "y"))]
'''


def test_static_meta_checks_desk_settings():
    ok = draftstore.static_meta(SRC.format(names='("a", "b")'))
    assert ok["desk_settings"] == ("a", "b") or list(ok["desk_settings"]) == ["a", "b"]
    assert "desk_settings" not in draftstore.static_meta(SRC.replace("    desk_settings = {names}\n", ""))
    for bad in ('("c",)', '("a", "a")', '(1,)', '("a","b","a","b","a","b","a")'):
        with pytest.raises(draftstore.StaticError, match="desk_settings"):
            draftstore.static_meta(SRC.format(names=bad))


# ---------------------------------------------------------------- the status block
def test_the_status_block_lists_the_adjustable_settings_and_the_values_in_use(sc):
    lab = status(sc)["lab"]
    assert [s["key"] for s in lab["settings"]] == ["open_min", "big_body"]
    assert lab["params"]["open_min"] == "5" and lab["params"]["big_body"] == 25.0


def test_a_record_with_no_settings_shows_an_empty_list(client):
    assert status(client)["lab"]["settings"] == []


# ---------------------------------------------------------------- the route
def test_a_setting_is_written_into_the_record_and_journaled(sc):
    r = post(sc, {"open_min": "1"})
    assert r.status_code == 200 and r.json() == {"ok": True, "strategy": LAB, "settings": {"open_min": "1"}, "changed": True}
    got = store.get("pp_orb")
    assert got["params"] == {"open_min": "1", "big_body": 25.0}                           # the other one is untouched
    assert store.mark_of(got) == ["ab", "2026-10-09T12:00:00+00:00"]                      # same strategy: its mark is the same
    assert status(sc)["lab"]["params"]["open_min"] == "1"
    ev = journal(sc, "lab_settings_set")[-1]
    assert ev["strategy"] == LAB and ev["settings"] == {"open_min": "1"} and ev["previous"] == {"open_min": "5"}
    assert no_lab_in_config(sc)


def test_the_same_value_again_changes_nothing_and_says_so(sc):
    before = store.get("pp_orb")
    r = post(sc, {"open_min": "5", "big_body": 25})
    assert r.status_code == 200 and r.json()["changed"] is False
    assert store.get("pp_orb") == before and journal(sc, "lab_settings_set") == []


def test_a_bad_value_is_a_400_with_its_sentence_and_nothing_changes(sc):
    for body, why in (({"open_min": "3"}, "Opening candle (minutes): one of 1, 5."),
                      ({"big_body": 9999}, "Big candle: body over (pts): from 1 to 500."),
                      ({"zzz": 1}, "That setting cannot be changed here.")):
        r = post(sc, body)
        assert r.status_code == 400 and r.json()["detail"] == why
    assert store.get("pp_orb")["params"] == {"open_min": "5", "big_body": 25.0}
    assert sc.post("/api/lab-settings", json=[1]).status_code == 400


def test_not_a_lab_strategy_is_a_404(sc):
    r = post(sc, {"open_min": "1"}, name="nq930")
    assert r.status_code == 404 and r.json()["detail"] == NOT_ON_DESK


def test_refused_while_its_session_runs_the_930_window_or_a_round_is_open(sc):
    sc.engine.now_et = lambda: dt.datetime(2026, 9, 30, 10, 0, tzinfo=ET)                 # inside 09:25-15:55
    r = post(sc, {"open_min": "1"})
    assert r.status_code == 409 and r.json()["detail"] == "Not while it is in session. Change it before 09:25 or after 15:55 ET."
    sc.engine.now_et = lambda: dt.datetime(2026, 9, 30, 9, 25, tzinfo=ET)
    assert post(sc, {"open_min": "1"}).status_code == 409
    for ok in (BEFORE_OPEN, AFTER_CLOSE, dt.datetime(2026, 10, 3, 10, 0, tzinfo=ET)):    # before, after, a Saturday
        sc.engine.now_et = lambda ok=ok: ok
        assert post(sc, {"open_min": "1" if store.get("pp_orb")["params"]["open_min"] == "5" else "5"}).status_code == 200
    open_round(sc, "eval1", "live")
    r = post(sc, {"big_body": 40})
    assert r.status_code == 409 and r.json()["detail"] == FLATTEN_FIRST


def test_a_record_that_changed_under_it_is_refused(sc):
    store.put(rec(promoted="2026-10-10T16:00:00+00:00", settings=SPEC, params={"open_min": "5", "big_body": 25.0}))
    r = post(sc, {"open_min": "1"})                                                        # the desk has not read the new one yet
    assert r.status_code == 409
    assert store.get("pp_orb")["params"]["open_min"] == "5"


def test_the_runner_hosts_the_day_again_when_a_setting_changes():
    from homebase.labrun import host
    a = rec(params={"open_min": "5"})
    b = rec(params={"open_min": "1"})
    assert host._key(a) != host._key(b)
