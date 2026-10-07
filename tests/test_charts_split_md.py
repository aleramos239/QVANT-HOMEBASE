"""Two market-data logins at once (2026-10-07): the live login has CME only (NQ ES RTY, with
Level 2); the Apex / eval logins have COMEX and CBOT too (GC SI YM). The markets named in the
settings file's "md_other_roots" ride a second socket on the OTHER login. Fakes only."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from homebase.charts.settings_store import SettingsStore
from tests.test_charts_settings_server import BASE_URL, FakeMdWS, app_with, wait_for


def charted(ws) -> set:
    """The roots this socket was asked to chart (md/getChart symbols, without the month)."""
    return {body["symbol"][:2] for ep, body in ws.sent if ep == "md/getChart"}


def settings(tmp_path, **keys):
    p = tmp_path / "state" / "settings.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(keys))


def test_the_named_markets_ride_the_other_login(tmp_path):
    settings(tmp_path, md="live", md_other_roots=["ES"])
    live, demo = FakeMdWS("live"), FakeMdWS("demo")
    connects = {"live": live, "demo": demo}
    with TestClient(app_with(tmp_path, connects), base_url=BASE_URL) as c:
        wait_for(lambda: charted(live) and charted(demo))
        assert charted(live) == {"NQ"} and charted(demo) == {"ES"}
        st = c.get("/api/status").json()
        assert st["md"] == "live" and set(st["roots"]) == {"NQ", "ES"}
        assert st["roots"]["ES"]["contract"]                       # the second socket's market, in the one list
        assert st["md_other"] == {"md": "demo", "roots": ["ES"], "connected": True,
                                  "error": None, "md_mismatch": None}
        assert c.get("/api/settings").json()["md"] == "live"       # the Settings choice is the main login's


def test_no_named_market_means_one_socket_as_before(tmp_path):
    settings(tmp_path, md="live")
    live = FakeMdWS("live")
    connects = {"live": live, "demo": RuntimeError("the other login is never asked")}
    with TestClient(app_with(tmp_path, connects), base_url=BASE_URL) as c:
        wait_for(lambda: charted(live) == {"NQ", "ES"})
        assert connects["calls"] == ["live"]
        assert "md_other" not in c.get("/api/status").json()


def test_a_second_login_that_fails_never_takes_the_first_one_down(tmp_path):
    settings(tmp_path, md="live", md_other_roots=["ES"])
    live = FakeMdWS("live")
    connects = {"live": live, "demo": RuntimeError("no valid md token")}
    with TestClient(app_with(tmp_path, connects), base_url=BASE_URL) as c:
        wait_for(lambda: charted(live) == {"NQ"})
        wait_for(lambda: (c.get("/api/status").json()["md_other"]["error"] or "") != "")
        st = c.get("/api/status").json()
        assert st["connected"] is True and st["md_other"]["connected"] is False
        assert "ES" in st["error"] and "no valid md token" in st["error"]   # said on the page, not hidden


def test_the_store_reads_only_a_clean_list(tmp_path):
    s = SettingsStore(tmp_path / "settings.json")
    assert s.other_roots() == []
    (tmp_path / "settings.json").write_text(json.dumps({"md": "live", "md_other_roots": ["gc", "SI", 7, "GC"]}))
    assert s.other_roots() == ["GC", "SI"]
    assert s.get() == {"md": "live"}                               # the md choice reads as before
    (tmp_path / "settings.json").write_text(json.dumps({"md_other_roots": "GC"}))
    assert s.other_roots() == []
    s.set_md("demo")                                               # setting md keeps the list
    (tmp_path / "settings.json").write_text(json.dumps({"md": "live", "md_other_roots": ["YM"]}))
    s.set_md("demo")
    assert s.other_roots() == ["YM"]
