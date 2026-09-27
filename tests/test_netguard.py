"""Desk-wide write protection (Task 5b): the shared Host/Origin allowlist
(homebase/netguard.py) and the write guard on the desk's MAIN app. A web
page must not arm, kill or place a self-test order through a CORS "simple
request" (text/plain, no preflight), a foreign Origin, or a DNS-rebound
Host. The public hook app on :8851 is untouched. No network, no broker."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

import homebase.config as config_mod
from homebase import netguard
from homebase.config import AccountCfg, AppCfg, StrategyCfg
from homebase.desk_api import same_origin_json
from homebase.server import create_app
from tests.test_engine import FakeAdapter

DESK = "http://127.0.0.1:8850"
TS = "desk.tail1234.ts.net"                 # a configured Tailscale MagicDNS name
LOOP = netguard.allowlist([])
WITH_TS = netguard.allowlist([TS, "100.101.102.103"])


# --- netguard: pure --------------------------------------------------------------------
@pytest.mark.parametrize("host,ok", [
    ("127.0.0.1", True), ("127.0.0.1:8850", True), ("localhost", True),
    ("localhost:8852", True), ("LocalHost:8850", True), ("[::1]", True), ("[::1]:8850", True),
    (None, False), ("", False), (" localhost", False), ("localhost:8850 ", False),
    ("localhost.evil.com", False), ("localhost.evil.com:8850", False),
    ("127.0.0.1.nip.io", False), ("127.0.0.1.nip.io:8850", False),
    ("evil.example", False), ("127.0.0.2", False), ("0.0.0.0:8850", False),
    ("::1", False), ("[::2]:8850", False), ("[::1]x", False),
    ("localhost:", False), ("localhost:88500", False), ("localhost:65536", False),
    ("user@localhost", False), ("127.0.0.1:8850/x", False), ("localhost.", False),
    (TS, False),                                     # not configured: refused
])
def test_host_allowed_loopback_only_by_default(host, ok):
    assert netguard.host_allowed(host, LOOP) is ok


@pytest.mark.parametrize("host,ok", [
    (TS, True), (f"{TS}:8850", True), (TS.upper(), True), ("100.101.102.103:8850", True),
    ("localhost:8850", True),
    (f"{TS}.evil.com", False), (f"x.{TS}", False), ("100.101.102.104", False),
])
def test_a_configured_tailscale_name_is_allowed_exactly(host, ok):
    assert netguard.host_allowed(host, WITH_TS) is ok


@pytest.mark.parametrize("origin,ok", [
    ("http://127.0.0.1:8850", True), ("http://localhost:8850", True), ("http://localhost", True),
    ("https://localhost:8850", True), ("http://[::1]:8850", True), ("HTTP://LOCALHOST:8850", True),
    (None, False), ("", False), ("null", False), ("https://evil.example", False),
    ("http://localhost.evil.com", False), ("http://127.0.0.1.nip.io:8850", False),
    ("file://localhost", False), ("http://user@localhost:8850", False),
    ("http://localhost:8850/path", False), ("localhost:8850", False),
    (f"https://{TS}", False),
])
def test_origin_allowed(origin, ok):
    assert netguard.origin_allowed(origin, LOOP) is ok


def test_origin_allowed_for_a_configured_name():
    assert netguard.origin_allowed(f"https://{TS}", WITH_TS)
    assert not netguard.origin_allowed(f"https://{TS}.evil.com", WITH_TS)


def test_allowlist_normalizes_and_drops_what_cannot_match():
    got = netguard.allowlist([" Desk.Tail1234.TS.net ", "100.64.0.1", "", None, 7,
                              "host:8850", "*", "a b", "[::1]"])
    assert got == frozenset({"127.0.0.1", "localhost", "::1",
                             "desk.tail1234.ts.net", "100.64.0.1"})
    assert netguard.allowlist(None) == netguard.LOOPBACK


@pytest.mark.parametrize("ctype,ok", [
    ("application/json", True), ("application/json; charset=utf-8", True),
    ("Application/JSON;charset=UTF-8", True),
    (None, False), ("", False), ("text/plain", False), ("text/plain; charset=utf-8", False),
    ("application/x-www-form-urlencoded", False), ("multipart/form-data; boundary=x", False),
    ("application/jsonp", False), ("application/json, text/plain", False),
])
def test_json_content_type(ctype, ok):
    assert netguard.is_json(ctype) is ok


# --- the write guard on the desk's main app ----------------------------------------------
@pytest.fixture()
def desk(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.engine.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.server.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.secrets_store.state_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    monkeypatch.setattr("homebase.trading.ChartDesk._views_paused", lambda self: False)
    cfg = AppCfg(armed=False, webhook_secret="tv-secret",
                 accounts={"main": AccountCfg(keyring_key="k", account_name="MAIN")},
                 book={"nq930": [{"account": "main", "qty": 3}]},
                 strategies={"nq930": StrategyCfg(symbol="NQ", qty=3, offset_pts=10.0,
                                                  sl_pts=5.0, tp_pts=15.0, enabled=True)},
                 allowed_hosts=[TS])
    adapters = {"main": FakeAdapter("main")}
    app = create_app(cfg, adapters, background=False,
                     adapter_factory=lambda aid, a: FakeAdapter(aid))
    with TestClient(app, base_url=DESK) as c:
        c.app, c.cfg, c.adapter, c.tmp = app, cfg, adapters["main"], tmp_path
        yield c


def _journal(tmp: Path) -> list:
    p = tmp / "journal.jsonl"
    return [json.loads(l) for l in p.read_text().splitlines()] if p.exists() else []


# each route with a body that would act if the guard let it through
WRITES = [
    ("/api/arm", {"armed": True}),
    ("/api/kill", {}),
    ("/api/selftest-order", {"account": "main", "symbol": "NQ", "ref_price": 24500.0,
                             "plain": True}),
]


def _untouched(c) -> None:
    assert c.cfg.armed is False
    assert c.adapter.orders == [] and c.adapter.brackets == []
    assert c.adapter.cancel_all_calls == 0 and c.adapter.flatten_calls == 0
    events = {e["event"] for e in _journal(c.tmp)}
    assert not events & {"armed_toggled", "kill_switch", "selftest_order"}


@pytest.mark.parametrize("url,body", WRITES)
def test_a_text_plain_simple_request_is_refused_415(desk, url, body):
    """fetch(url, {method: "POST", mode: "no-cors", body: '{"armed":true}'})
    goes out as text/plain with no preflight."""
    r = desk.post(url, content=json.dumps(body),
                  headers={"content-type": "text/plain;charset=UTF-8"})
    assert r.status_code == 415 and "error" in r.json()
    for ctype in (None, "application/x-www-form-urlencoded", "multipart/form-data; boundary=b"):
        h = {} if ctype is None else {"content-type": ctype}
        assert desk.post(url, content=json.dumps(body), headers=h).status_code == 415, ctype
    _untouched(desk)


@pytest.mark.parametrize("url,body", WRITES)
def test_a_foreign_origin_is_refused_403(desk, url, body):
    for origin in ("https://evil.example", "http://localhost.evil.com", "null",
                   "http://127.0.0.1.nip.io:8850"):
        r = desk.post(url, json=body, headers={"origin": origin})
        assert r.status_code == 403, origin
        assert r.json() == {"error": "origin not allowed"}
    _untouched(desk)


@pytest.mark.parametrize("url,body", WRITES)
def test_a_rebinding_host_is_refused_403(desk, url, body):
    for host in ("evil.example:8850", "localhost.evil.com:8850", "127.0.0.1.nip.io:8850"):
        for h in ({"host": host}, {"host": host, "origin": f"http://{host}"}):
            r = desk.post(url, json=body, headers=h)
            assert r.status_code == 403, h
            assert r.json() == {"error": "host not allowed"}
    _untouched(desk)


def test_host_is_checked_before_origin_and_content_type(desk):
    r = desk.post("/api/arm", content="x", headers={"host": "evil.example",
                                                   "origin": "https://evil.example",
                                                   "content-type": "text/plain"})
    assert (r.status_code, r.json()) == (403, {"error": "host not allowed"})
    r = desk.post("/api/arm", content="x", headers={"origin": "https://evil.example",
                                                   "content-type": "text/plain"})
    assert (r.status_code, r.json()) == (403, {"error": "origin not allowed"})


def test_a_proper_local_json_arm_still_works(desk):
    for host in ("127.0.0.1:8850", "localhost:8850", "[::1]:8850", f"{TS}:8850"):
        r = desk.post("/api/arm", json={"armed": True},
                      headers={"host": host, "origin": f"http://{host}",
                               "content-type": "application/json; charset=utf-8"})
        assert r.status_code == 200 and r.json()["armed"] is True, host
        desk.post("/api/arm", json={"armed": False})
    assert desk.post("/api/arm", json={"armed": True}).json()["armed"] is True  # no Origin: curl


def test_a_proper_local_json_kill_still_works(desk):
    desk.post("/api/arm", json={"armed": True})
    r = desk.post("/api/kill", json={}, headers={"origin": DESK})
    assert r.status_code == 200 and r.json()["armed"] is False
    assert desk.adapter.cancel_all_calls == 1 and desk.adapter.flatten_calls == 1


def test_a_proper_local_json_selftest_still_works_on_the_fake(desk):
    r = desk.post("/api/selftest-order", headers={"origin": DESK},
                  json={"account": "main", "symbol": "NQ", "ref_price": 24500.0, "plain": True})
    assert r.status_code == 200 and r.json()["ok"] is True
    assert [o.text for o in desk.adapter.orders] == ["homebase:selftest"]   # the fake, not a broker
    assert desk.adapter.cancelled == ["plain"]


def test_duplicate_guarded_headers_are_refused(desk):
    """Two Host / Origin / Content-Type headers are ambiguous: refuse, never
    pick the friendly one."""
    t = desk.app

    def raw(headers: list) -> int:
        out: dict = {}

        async def go():
            sent = []

            async def receive():
                return {"type": "http.request", "body": b'{"armed": true}', "more_body": False}

            async def send(m):
                sent.append(m)
            await t({"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1",
                     "method": "POST", "scheme": "http", "path": "/api/arm",
                     "raw_path": b"/api/arm", "root_path": "", "query_string": b"",
                     "client": ("127.0.0.1", 5), "server": ("127.0.0.1", 8850),
                     "headers": headers}, receive, send)
            out["status"] = sent[0]["status"]
        desk.portal.call(go)
        return out["status"]

    j = (b"content-type", b"application/json")
    h = (b"host", b"127.0.0.1:8850")
    assert raw([h, (b"host", b"evil.example"), j]) == 403
    assert raw([h, (b"origin", b"http://localhost"), (b"origin", b"https://evil.example"), j]) == 403
    assert raw([h, j, (b"content-type", b"text/plain")]) == 415
    assert raw([j]) == 403                                   # no Host at all
    assert desk.cfg.armed is False
    assert raw([h, j]) == 200 and desk.cfg.armed is True


REBOUND = ("evil.example:8850", "localhost.evil.com:8850", "127.0.0.1.nip.io")


@pytest.mark.parametrize("url", ["/api/tv-setup", "/api/status", "/api/logins", "/",
                                 "/static/index.html", "/api/calendar", "/docs", "/openapi.json"])
def test_a_rebinding_host_cannot_read_the_desk(desk, url):
    """Fix round 1 (CRITICAL): a rebound page must not GET /api/tv-setup —
    the webhook secret + the public tunnel URL would let it forge a /hook
    alert. The Host is checked on EVERY method, the /static mount included."""
    for host in REBOUND:
        r = desk.get(url, headers={"host": host})
        assert (r.status_code, r.json()) == (403, {"error": "host not allowed"}), (url, host)
        assert "tv-secret" not in r.text
        assert desk.head(url, headers={"host": host}).status_code == 403
        assert desk.options(url, headers={"host": host}).status_code == 403


def test_reads_from_an_allowed_host_still_work(desk):
    """GET/HEAD/OPTIONS skip only the Origin and Content-Type checks."""
    for host in ("127.0.0.1:8850", "localhost:8850", "[::1]:8850", f"{TS}:8850"):
        r = desk.get("/api/tv-setup", headers={"host": host})
        assert r.status_code == 200 and r.json()["secret"] == "tv-secret", host
    assert desk.get("/", headers={"origin": "https://evil.example"}).status_code == 200
    assert desk.get("/api/status", headers={"origin": "https://evil.example",
                                            "content-type": "text/plain"}).status_code == 200
    assert desk.get("/api/logins").status_code == 200
    assert desk.get("/static/index.html").status_code == 200
    assert desk.head("/").status_code in (200, 405)
    assert desk.get("/api/trade/state", headers={"host": "evil.example"}).status_code == 403


def test_every_post_route_on_the_main_app_is_guarded(desk):
    """No write route escapes: every POST path except /api/trade/* (stricter:
    loopback Host only, any Origin refused, desk key) refuses text/plain."""
    posts = sorted({r.path for r in desk.app.routes if "POST" in getattr(r, "methods", set())}
                   | {"/api/chart-trading"})           # included via its router
    assert {"/api/arm", "/api/kill", "/api/selftest-order", "/hook"} <= set(posts)
    for p in posts:
        assert desk.post(p, content="{}", headers={"content-type": "text/plain"}).status_code \
            == 415, p


def test_the_trade_routes_keep_their_stricter_rules(desk):
    """The guard skips /api/trade/*: its own gate is stricter — a configured
    Tailscale name does NOT open it, any Origin (even local) is refused."""
    key = (desk.tmp / "desk.key").read_text().strip()
    H = {"X-Homebase-Key": key}
    order = {"client_id": "x", "accounts": ["main"], "root": "NQ", "side": "Buy", "qty": 1,
             "type": "Market"}
    assert desk.post("/api/trade/order", json=order,
                     headers={**H, "host": f"{TS}:8850"}).status_code == 403
    assert desk.post("/api/trade/order", json=order,
                     headers={**H, "origin": DESK}).status_code == 403
    assert desk.post("/api/trade/order", json=order).status_code == 401
    assert desk.get("/api/trade/state", headers={**H, "host": "[::1]:8850"}).status_code == 403


def test_chart_trading_uses_the_shared_allowlist(desk):
    """/api/chart-trading's own check (same_origin_json) follows the same
    allowlist: a configured Tailscale name passes, a rebound one does not."""
    ok = desk.post("/api/chart-trading", json={"max_position_qty": 7},
                   headers={"host": f"{TS}:8850", "origin": f"https://{TS}"})
    assert ok.status_code == 200 and ok.json()["chart_trading"]["max_position_qty"] == 7
    bad = desk.post("/api/chart-trading", json={"max_position_qty": 3},
                    headers={"host": f"{TS}.evil.com:8850"})
    assert bad.status_code == 403
    assert desk.cfg.chart_trading.max_position_qty == 7


def test_same_origin_json_alone_uses_the_allowlist(tmp_path):
    """The route's own check, without the middleware in front of it."""
    app = FastAPI()

    @app.post("/x")
    async def x(request: Request):
        same_origin_json(request, WITH_TS)
        return {"ok": True}
    c = TestClient(app, base_url=DESK)
    assert c.post("/x", json={}).status_code == 200
    assert c.post("/x", json={}, headers={"host": f"{TS}:443", "origin": f"https://{TS}"}) \
        .status_code == 200
    assert c.post("/x", json={}, headers={"host": "evil.example"}).status_code == 403
    assert c.post("/x", json={}, headers={"origin": "https://evil.example"}).status_code == 403
    assert c.post("/x", content="{}", headers={"content-type": "text/plain"}).status_code == 415


# --- the public hook app on :8851 is untouched ---------------------------------------------
def test_the_hook_app_is_unaffected_by_the_guard(desk):
    """TradingView reaches /hook through the tunnel with its own Host, maybe
    text/plain: the hook app answers exactly as before (the secret gates it)."""
    hc = TestClient(desk.app.state.hook_app, base_url="https://abc-def.trycloudflare.com")
    body = json.dumps({"secret": "tv-secret", "strategy": "nq930",
                       "upper": 24510.0, "lower": 24490.0})
    r = hc.post("/hook", content=body, headers={"content-type": "text/plain; charset=utf-8",
                                               "origin": "https://evil.example"})
    assert r.status_code == 200 and r.json()["ok"] in (True, False)
    assert hc.post("/hook", content=body.replace("tv-secret", "nope"),
                   headers={"content-type": "text/plain"}).status_code == 401
    mw = [m.cls.__name__ for m in desk.app.state.hook_app.user_middleware]
    assert mw == []


# --- config ------------------------------------------------------------------------------------
def test_allowed_hosts_round_trips_through_config(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    assert config_mod.load().allowed_hosts == []
    cfg = config_mod.load()
    cfg.allowed_hosts = [TS, "100.101.102.103"]
    config_mod.save(cfg)
    assert json.loads((tmp_path / "config.json").read_text())["allowed_hosts"] == \
        [TS, "100.101.102.103"]
    assert config_mod.load().allowed_hosts == [TS, "100.101.102.103"]


@pytest.mark.parametrize("raw,usable,dropped", [
    ([], set(), []),
    ([" Desk.TS.net ", "", 5, "h:1", "ok-host"], {"desk.ts.net", "ok-host"}, ["''", "5", "'h:1'"]),
    ("desk.ts.net", set(), ["'desk.ts.net'"]),
    (None, set(), ["None"]),
    (7, set(), ["7"]),
])
def test_bad_allowed_hosts_warn_at_load_and_survive_a_save(tmp_path, monkeypatch, caplog,
                                                          raw, usable, dropped):
    """Fix round 1: a bad entry never vanishes silently and is never erased
    from disk — the raw value round-trips through save(); only the
    in-memory allowlist uses the cleaned entries; each drop is a warning."""
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    (tmp_path / "config.json").write_text(json.dumps({"allowed_hosts": raw}))
    with caplog.at_level("WARNING", logger="homebase.config"):
        cfg = config_mod.load()
    assert cfg.allowed_hosts == raw
    assert netguard.allowlist(cfg.allowed_hosts) == netguard.LOOPBACK | usable
    warned = [r.getMessage() for r in caplog.records if r.name == "homebase.config"]
    assert len(warned) == len(dropped)
    for w, d in zip(warned, dropped):
        assert "allowed_hosts" in w and d in w
    config_mod.save(cfg)
    assert json.loads((tmp_path / "config.json").read_text())["allowed_hosts"] == raw


def test_a_clean_allowed_hosts_list_warns_nothing(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    (tmp_path / "config.json").write_text(json.dumps({"allowed_hosts": [TS, "100.64.0.1"]}))
    with caplog.at_level("WARNING", logger="homebase.config"):
        config_mod.load()
    assert not [r for r in caplog.records if r.name == "homebase.config"]


def test_the_write_guard_ignores_bad_entries_but_keeps_good_ones(desk):
    desk.cfg.allowed_hosts = ["*", "evil.example:8850", TS]
    assert desk.post("/api/arm", json={"armed": False},
                     headers={"host": "evil.example:8850"}).status_code == 403
    assert desk.post("/api/arm", json={"armed": False},
                     headers={"host": f"{TS}:8850"}).status_code == 200


# --- the reusable check (Task 8's proxy) ---------------------------------------------------------
def _h(**kw) -> list:
    return [(k.replace("_", "-").encode(), v.encode()) for k, v in kw.items()]


def test_refusal_is_the_shared_combined_check():
    ok = _h(host="127.0.0.1:8852", content_type="application/json")
    assert netguard.refusal("POST", ok, LOOP) is None
    assert netguard.refusal("POST", _h(host="evil.example"), LOOP) == (403, "host not allowed")
    assert netguard.refusal("GET", _h(host="evil.example"), LOOP) == (403, "host not allowed")
    assert netguard.refusal("GET", _h(host="localhost", origin="https://evil.example"), LOOP) is None
    assert netguard.refusal("POST", _h(host="localhost", origin="https://evil.example",
                                       content_type="application/json"), LOOP) == \
        (403, "origin not allowed")
    assert netguard.refusal("POST", _h(host="localhost"), LOOP)[0] == 415


def test_refusal_can_skip_the_json_rule_for_a_bodyless_delete():
    """The chart page sends DELETE /api/layouts/... with no Content-Type:
    require_json=False keeps the Host and Origin checks and drops only the
    Content-Type one."""
    bare = _h(host="localhost:8852", origin="http://localhost:8852")
    assert netguard.refusal("DELETE", bare, LOOP)[0] == 415
    assert netguard.refusal("DELETE", bare, LOOP, require_json=False) is None
    assert netguard.refusal("DELETE", _h(host="evil.example"), LOOP, require_json=False) == \
        (403, "host not allowed")
    assert netguard.refusal("DELETE", _h(host="localhost", origin="https://evil.example"), LOOP,
                            require_json=False) == (403, "origin not allowed")


# --- the desk page -------------------------------------------------------------------------------
def test_the_desk_page_sends_every_post_as_json():
    """Every POST on the desk page goes through post() -- or, for the chart service's paper-account routes
    (Task 2b), chartPost() -- and both always send Content-Type: application/json and a JSON body."""
    html = (Path(__file__).resolve().parent.parent / "homebase" / "static" / "index.html").read_text()
    assert len(re.findall(r"method:\s*\"POST\"", html, re.I)) == 2
    for name in ("post(url, body)", "chartPost(path, body)"):
        helper = re.search(r"async function " + re.escape(name) + r" \{(.*?)\n\}", html, re.S).group(1)
        assert '"Content-Type": "application/json"' in helper
        assert "JSON.stringify(body || {})" in helper


# --- WebSockets on the main app (Task 5b re-review, carried to Task 6) -----------------------
def test_websocket_scopes_get_the_host_and_origin_checks(desk):
    """The main app mounts no WebSocket today, but the guard must not let a
    websocket scope through unchecked the day one is added: a cross-site page
    can open a WebSocket with no CORS at all. Host on the allowlist always;
    an Origin, when sent (every browser sends one), on the allowlist too.
    A refusal closes the handshake with 1008 before accept (HTTP 403)."""
    from starlette.websockets import WebSocketDisconnect

    async def echo(ws):
        await ws.accept()
        await ws.send_text("hello")
        await ws.close()
    desk.app.router.add_websocket_route("/ws-probe", echo)
    LOCAL = {"host": "127.0.0.1:8850"}        # TestClient sockets default to Host: testserver
    for host in REBOUND:
        with pytest.raises(WebSocketDisconnect) as e:
            with desk.websocket_connect("/ws-probe", headers={"host": host}):
                pass
        assert (e.value.code, e.value.reason) == (1008, "host not allowed"), host
    for origin in ("https://evil.example", "null", "http://localhost.evil.com:8850"):
        with pytest.raises(WebSocketDisconnect) as e:
            with desk.websocket_connect("/ws-probe", headers={**LOCAL, "origin": origin}):
                pass
        assert (e.value.code, e.value.reason) == (1008, "origin not allowed"), origin
    with pytest.raises(WebSocketDisconnect):          # /api/trade/* is not exempt for sockets
        with desk.websocket_connect("/api/trade/ws", headers={"host": "evil.example"}):
            pass
    for headers in (LOCAL, {**LOCAL, "origin": DESK},
                    {"host": f"{TS}:8850", "origin": f"https://{TS}"}):
        with desk.websocket_connect("/ws-probe", headers=headers) as ws:
            assert ws.receive_text() == "hello", headers
