"""PUT/GET /api/settings (Task 4, 2026-09-27 accounts-paper-layouts-appsettings plan): the
market-data login switch end to end -- refusal windows, a failed re-login falling back and
keeping the old setting, and depth re-subscribing after a successful switch. Fakes only: no
broker, no tokens, nothing written under ~/futures_ticks or ~/futures_depth."""
from __future__ import annotations

import asyncio
import threading
import time

from fastapi.testclient import TestClient

from homebase import symbols
from homebase.charts.server import create_app
from tests.charts_util import D, session_ms
from tests.test_charts_server import archive

BASE_URL = "http://127.0.0.1:8852"      # the Host guard refuses TestClient's default "testserver"


class FakeMdWS:
    """A minimal md socket: answers every md/getChart with a fresh realtimeId (so subscribe()
    always succeeds) and md/subscribeDOM with a subscriptionId, like test_charts_depth.py's."""

    def __init__(self, name=""):
        self.name = name
        self.connected = True
        self.event_handlers = []
        self.sent = []

    async def request(self, ep, body=""):
        self.sent.append((ep, body))
        if ep == "md/subscribeDOM":
            sym = body.get("symbol") if isinstance(body, dict) else None
            return {"mode": "RealTime", "subscriptionId": hash((self.name, sym)) & 0xFFFF}
        n = len(self.sent)
        return {"historicalId": 10 + n, "realtimeId": 100 + n}

    async def close(self):
        self.connected = False


class FakeLink:
    """The desk link (desk.py): only .state (bot_placing reads it), .hello/.run/.stop
    (server.py's lifespan/desk_fan need them). No broker, no SSE, no key file."""

    def __init__(self, publish):
        self.publish = publish
        self.state = None
        self._stop = False

    def hello(self):
        return {"type": "desk", "down": "test link"} if self.state is None else \
            {"type": "desk", "event": "state", "data": self.state}

    async def run(self):
        while not self._stop:
            await asyncio.sleep(0.01)

    def stop(self):
        self._stop = True


def wait_for(cond, timeout=5.0):
    deadline = time.time() + timeout
    while not cond() and time.time() < deadline:
        time.sleep(0.02)
    assert cond()


def app_with(tmp_path, connects, *, now_ms=None, link_box=None, depth_roots=None):
    """connects: {"demo": ws, "live": ws} -- md_connect returns them by env, recording every
    call in connects["calls"] (a list of env strings)."""
    calls = connects.setdefault("calls", [])

    async def md_connect(env):
        calls.append(env)
        v = connects[env]
        if isinstance(v, Exception):
            raise v
        return v

    def desk_factory(publish):
        link = FakeLink(publish)
        if link_box is not None:
            link_box.append(link)
        return link

    return create_app(roots=["NQ", "ES"], base=archive(tmp_path), state=tmp_path / "state",
                      now_ms=now_ms or (lambda: session_ms(D, 9, 45)),
                      md_connect=md_connect, desk_factory=desk_factory,
                      depth_roots=depth_roots, depth_base=tmp_path / "depth")


def test_get_settings_reads_the_env_default_with_no_file(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEBASE_CHARTS_MD", "demo")
    ws = FakeMdWS("demo")
    app = app_with(tmp_path, {"demo": ws})
    with TestClient(app, base_url=BASE_URL) as c:
        assert c.get("/api/settings").json() == {"md": "demo"}


def test_switching_md_persists_and_is_reflected_in_status(tmp_path):
    demo_ws, live_ws = FakeMdWS("demo"), FakeMdWS("live")
    app = app_with(tmp_path, {"demo": demo_ws, "live": live_ws})
    with TestClient(app, base_url=BASE_URL) as c:
        assert c.get("/api/settings").json()["md"] == "demo"
        r = c.put("/api/settings", json={"md": "live"})
        assert r.status_code == 200 and r.json() == {"md": "live"}
        assert c.get("/api/settings").json() == {"md": "live"}
        st = c.get("/api/status").json()
        assert st["md"] == "live"
        # a fresh store over the same state dir reads back the persisted choice
        from homebase.charts.settings_store import SettingsStore
        assert SettingsStore(tmp_path / "state" / "settings.json").get() == {"md": "live"}


def test_a_bad_md_value_is_refused(tmp_path):
    app = app_with(tmp_path, {"demo": FakeMdWS()})
    with TestClient(app, base_url=BASE_URL) as c:
        assert c.put("/api/settings", json={"md": "paper"}).status_code == 400
        assert c.put("/api/settings", json={}).status_code == 400


def test_refused_inside_the_0920_0935_et_window_on_a_weekday(tmp_path):
    app = app_with(tmp_path, {"demo": FakeMdWS(), "live": FakeMdWS()},
                   now_ms=lambda: session_ms(D, 9, 25))   # D is a Thursday
    with TestClient(app, base_url=BASE_URL) as c:
        r = c.put("/api/settings", json={"md": "live"})
        assert r.status_code == 423
        assert "09:35" in r.json()["detail"]
        assert c.get("/api/settings").json()["md"] == "demo"   # untouched


def test_refused_while_the_desk_reports_a_bot_placing(tmp_path):
    link_box = []
    app = app_with(tmp_path, {"demo": FakeMdWS(), "live": FakeMdWS()}, link_box=link_box)
    with TestClient(app, base_url=BASE_URL) as c:
        wait_for(lambda: link_box)
        link_box[0].state = {"bot": {"strategies": {
            "nq930": {"accounts": {"acct1": {"status": "placing"}}}}}}
        r = c.put("/api/settings", json={"md": "live"})
        assert r.status_code == 423
        assert "09:35" in r.json()["detail"]
        assert c.get("/api/settings").json()["md"] == "demo"
        # a status OTHER than placing (placed/live/flat) does not refuse
        link_box[0].state = {"bot": {"strategies": {
            "nq930": {"accounts": {"acct1": {"status": "flat"}}}}}}
        assert c.put("/api/settings", json={"md": "live"}).status_code == 200


def test_a_failed_relogin_falls_back_and_keeps_the_old_setting(tmp_path):
    demo_ws = FakeMdWS("demo")
    app = app_with(tmp_path, {"demo": demo_ws, "live": RuntimeError("no token on disk")})
    with TestClient(app, base_url=BASE_URL) as c:
        r = c.put("/api/settings", json={"md": "live"})
        assert r.status_code == 502
        assert c.get("/api/settings").json() == {"md": "demo"}
        st = c.get("/api/status").json()
        assert st["md"] == "demo" and st["connected"]           # the old (demo) socket kept running
        # the old socket is still usable -- unaffected by the failed switch attempt
        r2 = c.put("/api/settings", json={"md": "demo"})
        assert r2.status_code == 200


def test_depth_resubscribes_on_every_watched_root_after_a_successful_switch(tmp_path):
    demo_ws, live_ws = FakeMdWS("demo"), FakeMdWS("live")
    app = app_with(tmp_path, {"demo": demo_ws, "live": live_ws}, depth_roots=("NQ",))
    with TestClient(app, base_url=BASE_URL) as c:
        wait_for(lambda: any(ep == "md/subscribeDOM" for ep, _ in demo_ws.sent))
        r = c.put("/api/settings", json={"md": "live"})
        assert r.status_code == 200

        def resubscribed():
            syms = [b.get("symbol") for ep, b in live_ws.sent if ep == "md/subscribeDOM"]
            return symbols.resolve_contract("NQ") in syms
        wait_for(resubscribed)
        # never asked on the OLD socket again after the switch (no duplicate/lingering subscribe)
        before = len([1 for ep, _ in demo_ws.sent if ep == "md/subscribeDOM"])
        time.sleep(0.1)
        after = len([1 for ep, _ in demo_ws.sent if ep == "md/subscribeDOM"])
        assert after == before


def test_switching_to_the_login_already_active_is_a_cheap_noop(tmp_path):
    demo_ws = FakeMdWS("demo")
    connects = {"demo": demo_ws, "live": FakeMdWS("live")}
    app = app_with(tmp_path, connects)
    with TestClient(app, base_url=BASE_URL) as c:
        wait_for(lambda: demo_ws.sent)   # the feed connected and subscribed once already
        n = len(demo_ws.sent)
        r = c.put("/api/settings", json={"md": "demo"})
        assert r.status_code == 200
        assert len(demo_ws.sent) == n            # no re-subscribe, no new getChart burst
        assert connects["calls"] == ["demo"]     # the "live" login was never even connected


def test_a_second_put_while_one_is_in_flight_is_refused_with_409(tmp_path):
    """Serialized (TickFeed.switch_md, tests/test_charts_tickfeed.py): a switch already
    connecting refuses a second one rather than queuing it. Driven with real threads against a
    live TestClient so the two PUTs genuinely overlap, the same shape as the 24/7-refill gate
    test in test_charts_server.py."""
    entered = threading.Event()
    release = threading.Event()

    async def md_connect(env):
        if env == "live":
            entered.set()
            await asyncio.get_event_loop().run_in_executor(None, release.wait)
        return FakeMdWS(env)

    app = create_app(roots=["NQ", "ES"], base=archive(tmp_path), state=tmp_path / "state",
                     now_ms=lambda: session_ms(D, 9, 45), md_connect=md_connect)
    with TestClient(app, base_url=BASE_URL) as c:
        results = {}

        def first():
            results["first"] = c.put("/api/settings", json={"md": "live"})

        t = threading.Thread(target=first)
        t.start()
        assert entered.wait(5.0)
        second = c.put("/api/settings", json={"md": "live"})   # same target: still hits switch_md while the first is in flight
        release.set()
        t.join(5.0)

        assert second.status_code == 409
        assert results["first"].status_code == 200
        assert c.get("/api/settings").json() == {"md": "live"}
