"""The chart service's desk link: SSE parsing, fan-out, backoff, the key,
the proxy's POST, and quotes from the ticks. No network: every DeskLink
gets an httpx.MockTransport; the real desk is never reached."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

import homebase.charts
from homebase.charts.desk import LINE_MAX, NO_LINK, PAUSED, DeskLink, Fanout, Quotes, SSEParser, register
from homebase.charts.server import origin_ok


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


KEY = "ab" * 32
STATE = ["event: state", 'data: {"enabled": true, "accounts": [{"id": "a1", "n": 0}], "bot": {}}', ""]
ACCT = ["event: account", 'data: {"id": "a1", "n": 1}', ""]
BEAT = ["event: heartbeat", 'data: {"ts": 1}', ""]


def key_file(tmp_path, key=KEY):
    p = tmp_path / "desk.key"
    if key is not None:
        p.write_text(key + "\n")
    return p


def mklink(tmp_path, script, key=KEY):
    """script: one item per stream attempt — an exception to raise, or
    (status, lines). The link stops itself once the script is used up."""
    fanned, seen, slept = [], [], []

    def handler(request):
        seen.append(request)
        item = script.pop(0)
        if isinstance(item, Exception):
            raise item
        status, lines = item
        return httpx.Response(status, content=("\n".join(lines) + "\n").encode(),
                              headers={"content-type": "text/event-stream"})

    async def sleep(s):
        slept.append(s)
        if not script:
            link.stop()

    link = DeskLink(fanned.append, key_path=key_file(tmp_path, key),
                    transport=httpx.MockTransport(handler), sleep=sleep)
    return link, fanned, seen, slept


def test_sse_parser():
    p = SSEParser()
    lines = ["event: state", 'data: {"a":', "data: 1}", "", ": a comment", "data: x", "", ""]
    assert [p.feed(x) for x in lines] == \
        [None, None, None, ("state", '{"a":\n1}'), None, None, ("message", "x"), None]


def test_link_fans_out_events_with_the_key_and_says_when_the_desk_goes(tmp_path):
    link, fanned, seen, slept = mklink(tmp_path, [(200, STATE + ACCT + BEAT)])
    run(link.run())
    assert str(seen[0].url) == "http://127.0.0.1:8850/api/trade/stream"
    assert seen[0].headers["x-homebase-key"] == KEY and "origin" not in seen[0].headers
    assert fanned == [
        {"type": "desk", "event": "state",
         "data": {"enabled": True, "accounts": [{"id": "a1", "n": 0}], "bot": {}}},
        {"type": "desk", "event": "account", "data": {"id": "a1", "n": 1}},
        {"type": "desk", "down": "the desk closed the stream"},        # heartbeats never fan out
    ]
    assert link.hello() == {"type": "desk", "down": "the desk closed the stream"}


def test_hello_is_the_latest_state_or_the_down_reason(tmp_path):
    link, *_ = mklink(tmp_path, [])
    assert link.hello() == {"type": "desk", "down": "connecting to the desk"}
    link.on_event("account", '{"id": "a1", "n": 9}')              # before any state: ignored
    link.on_event("state", '{"accounts": [{"id": "a1", "n": 0}], "bot": {"x": 0}}')
    link.on_event("account", '{"id": "a1", "n": 1}')
    link.on_event("account", '{"id": "a2", "n": 5}')
    link.on_event("bot", '{"x": 1}')
    link.on_event("fill", "not json")                             # ignored
    assert link.hello() == {"type": "desk", "event": "state", "data": {
        "accounts": [{"id": "a1", "n": 1}, {"id": "a2", "n": 5}], "bot": {"x": 1}}}


def test_link_backs_off_1_to_30_s_and_resets_after_a_state(tmp_path):
    refused = httpx.ConnectError("refused")
    link, fanned, seen, slept = mklink(tmp_path, [refused] * 7 + [(200, STATE)] + [refused])
    run(link.run())
    assert slept == [1, 2, 4, 8, 16, 30, 30, 1, 2]
    assert [m["down"] for m in fanned if "down" in m] == [
        "desk unreachable: ConnectError: refused",       # announced once, not per retry
        "the desk closed the stream",
        "desk unreachable: ConnectError: refused"]


def test_an_oversized_line_or_event_drops_it_and_reconnects(tmp_path):
    huge = "x" * (LINE_MAX + 1)
    link, fanned, seen, slept = mklink(tmp_path, [(200, ["event: state", f"data: {huge}", ""])])
    run(link.run())
    assert fanned == [{"type": "desk", "down": "desk stream line too large (over 256 KB) — reconnecting"}]
    assert slept == [1]

    # under the per-line cap individually, but their joined data is not
    chunks = [f"data: {'y' * 60000}" for _ in range(5)]
    link, fanned, seen, slept = mklink(tmp_path, [(200, ["event: state", *chunks, ""])])
    run(link.run())
    assert fanned == [{"type": "desk",
                       "down": "desk stream event too large (over 256 KB) — reconnecting"}]


def test_a_deliberate_pause_close_is_paused_not_down(tmp_path):
    """desk_api.py's END_HELD comment (more than HELD_MAX events held across the
    9:29:50-09:30:30 pause) ends the stream on purpose; the page must not be
    told the desk is "down" for what is an expected, momentary pause."""
    end_held = ": end: more than 200 events held in the 9:30 pause; reconnect for a fresh state"
    link, fanned, seen, slept = mklink(tmp_path, [(200, STATE + [end_held, ""])])
    run(link.run())
    assert fanned[-1] == {"type": "desk", "down": PAUSED}


def test_a_refused_stream_and_a_missing_key_are_down_with_the_reason(tmp_path):
    link, fanned, seen, _ = mklink(tmp_path, [(401, [])])
    run(link.run())
    assert fanned == [{"type": "desk", "down": "desk refused the stream: HTTP 401"}]
    link, fanned, seen, _ = mklink(tmp_path / "nokey", [], key=None)    # no key file at all
    run(link.run())
    assert seen == [] and fanned == [{"type": "desk", "down":
                                      "desk key missing — start the desk (it creates homebase/.state/desk.key)"}]


def test_a_corrupt_or_unreadable_key_is_down_and_never_sent(tmp_path):
    for bad in ("not-a-key", "AB" * 32, KEY + "00"):
        link, fanned, seen, _ = mklink(tmp_path, [], key=bad)
        run(link.run())
        assert seen == [] and fanned == [{"type": "desk", "down": "desk key unreadable"}]
    d = tmp_path / "dir"
    (d / "desk.key").mkdir(parents=True)                               # read raises an OSError
    link = DeskLink(lambda m: None, key_path=d / "desk.key")
    status, body = run(link.post("order", {}))
    assert status == 503 and body["detail"].startswith("desk link unavailable")


def test_the_key_never_leaves_through_the_page_side(tmp_path):
    """The key is read per request and held nowhere the page can see:
    not in hello, not in a down reason, not on the link object."""
    link, fanned, *_ = mklink(tmp_path, [(200, STATE + ACCT)])
    run(link.run())
    dumped = json.dumps([fanned, link.hello(), {k: repr(v) for k, v in vars(link).items()}])
    assert KEY not in dumped


def test_post_adds_the_key_and_maps_failures(tmp_path):
    seen = []

    def handler(req):
        seen.append(req)
        if req.url.path == "/api/trade/order":
            return httpx.Response(200, json={"results": {"a1": {"ok": True}}})
        if req.url.path == "/api/trade/flatten":
            raise httpx.ReadTimeout("slow")
        raise httpx.ConnectError("refused")

    link = DeskLink(lambda m: None, key_path=key_file(tmp_path),
                    transport=httpx.MockTransport(handler))
    assert run(link.post("order", {"client_id": "c"})) == (200, {"results": {"a1": {"ok": True}}})
    assert seen[0].headers["x-homebase-key"] == KEY and "origin" not in seen[0].headers
    assert json.loads(seen[0].content) == {"client_id": "c"}
    status, body = run(link.post("flatten", {}))
    assert status == 504 and "check the Orders tab" in body["detail"]
    assert run(link.post("cancel", {})) == (502, {"detail": "desk unreachable: ConnectError"})
    nokey = DeskLink(lambda m: None, key_path=tmp_path / "missing.key")
    status, body = run(nokey.post("order", {}))
    assert status == 503 and body["detail"].startswith("desk link unavailable")


def test_quotes_keep_the_last_sane_bid_ask_and_drain_changes_once():
    q = Quotes()
    q.note("NQ", [{"ts_ms": 1, "price": 100.0, "bid": 99.75, "ask": 100.0},
                  {"ts_ms": 2, "price": 100.25, "bid": "", "ask": ""}])
    assert q.snapshot() == {"NQ": {"bid": 99.75, "ask": 100.0, "last": 100.25, "ts_ms": 2}}
    q.note("NQ", [{"ts_ms": 3, "price": 100.5, "bid": 100.75, "ask": 100.5}])   # crossed: kept
    assert q.drain() == [{"type": "quote", "root": "NQ", "bid": 99.75, "ask": 100.0,
                          "last": 100.5, "ts_ms": 3, "asof": "last_trade"}]
    assert q.drain() == []
    q.note("ES", [])
    assert "ES" not in q.snapshot()


def test_quote_of_is_the_last_sane_pair_as_fresh_as_its_own_row():
    """fast-paper: the paper book's read of the quote. A later row with no (or a crossed) quote keeps the old pair --
    and must not make it look newer than the row that carried it."""
    q = Quotes()
    assert q.quote_of("NQ") is None
    q.note("NQ", [{"ts_ms": 1, "price": 100.0, "bid": "", "ask": ""}])
    assert q.quote_of("NQ") is None                                          # a trade, never a quote yet
    q.note("NQ", [{"ts_ms": 2, "price": 100.0, "bid": 99.75, "ask": 100.0},
                  {"ts_ms": 3, "price": 100.25, "bid": "", "ask": ""},
                  {"ts_ms": 4, "price": 100.5, "bid": 100.75, "ask": 100.5}])
    assert q.quote_of("NQ") == {"bid": 99.75, "ask": 100.0, "ts_ms": 2}
    assert q.snapshot() == {"NQ": {"bid": 99.75, "ask": 100.0, "last": 100.5, "ts_ms": 4}}   # the desk's shape: unchanged


def test_the_chart_service_never_subscribes_quotes():
    """Ruling 2026-09-26: bid/ask come from the ticks. An md quote
    subscription could spend the budget of the login the 9:30 anchor uses."""
    pkg = Path(homebase.charts.__file__).parent
    assert not any("md/subscribeQuote" in p.read_text() for p in pkg.glob("*.py"))


# ---- fan-out: a slow page never blocks the reader or another page ----------

class Page:
    """A page socket as the fan-out sees it: send() never waits; `room`
    says whether its own send queue can take more right now."""

    def __init__(self, room=True):
        self.got, self.room = [], room

    def send(self, msg):
        self.got.append(msg)


def test_fanout_greets_each_page_with_hello_then_relays():
    hello = {"type": "desk", "event": "state", "data": {"n": 0}}
    fan = Fanout(hello=lambda: hello, maxlen=4)
    a = Page()
    fan.attach(a, a.send, lambda: a.room)
    fan.publish({"type": "desk", "event": "account", "data": {"n": 1}})
    assert a.got == [hello, {"type": "desk", "event": "account", "data": {"n": 1}}]
    fan.detach(a)
    fan.publish({"type": "desk", "event": "bot", "data": {}})
    assert len(a.got) == 2


def test_fanout_without_a_link_says_so():
    fan = Fanout()
    a = Page()
    fan.attach(a, a.send, lambda: True)
    assert a.got == [{"type": "desk", "down": NO_LINK}]


def test_a_slow_page_drops_its_oldest_and_resyncs_with_a_full_state():
    state = {"n": 0}
    fan = Fanout(hello=lambda: {"type": "desk", "event": "state", "data": dict(state)}, maxlen=3)
    slow, fast = Page(), Page()
    fan.attach(slow, slow.send, lambda: slow.room)
    fan.attach(fast, fast.send, lambda: fast.room)
    slow.got.clear()
    fast.got.clear()
    slow.room = False                                      # greeted, then it falls behind
    for n in range(1, 11):                                 # the reader never waits on `slow`
        state["n"] = n
        fan.publish({"type": "desk", "event": "account", "data": {"n": n}})
        if n == 5:
            fan.publish({"type": "desk", "event": "fill", "data": {"id": "f"}})
    assert slow.got == [] and [m["data"]["n"] for m in fast.got if m["event"] == "account"] == \
        list(range(1, 11))
    assert len(fan._boxes[slow].q) == 3                    # bounded
    slow.room = True
    fan.flush()                                            # e.g. the pump's next tick
    # it lost every stale "account" (a fresh state carries them all instead);
    # the "fill" is not dropped, because a view event is always evicted first
    # while any is left to give -- it survives to follow the resync
    assert slow.got == [{"type": "desk", "event": "state", "data": {"n": 10}},
                        {"type": "desk", "event": "fill", "data": {"id": "f"}}]


def test_a_dropped_notice_is_lost_but_a_kept_one_follows_the_resync():
    fan = Fanout(hello=lambda: {"type": "desk", "event": "state", "data": {}}, maxlen=2)
    p = Page(room=False)
    fan.attach(p, p.send, lambda: p.room)
    for m in ({"event": "account"}, {"event": "account"}, {"event": "fill", "data": 1}):
        fan.publish({"type": "desk", **m})
    p.room = True
    fan.flush()
    assert p.got == [{"type": "desk", "event": "state", "data": {}},
                     {"type": "desk", "event": "fill", "data": 1}]


def test_once_only_notices_remain_the_oldest_notice_is_dropped():
    fan = Fanout(hello=lambda: {"type": "desk", "event": "state", "data": {}}, maxlen=2)
    p = Page(room=False)
    fan.attach(p, p.send, lambda: p.room)
    for m in ({"event": "fill", "data": 1}, {"event": "fill", "data": 2},
             {"event": "fill", "data": 3}):
        fan.publish({"type": "desk", **m})
    p.room = True
    fan.flush()
    # both slots already held notices (nothing to evict but a notice), so
    # the third fill dropped the oldest one -- 1 is gone, 2 and 3 survive
    assert p.got == [{"type": "desk", "event": "state", "data": {}},
                     {"type": "desk", "event": "fill", "data": 2},
                     {"type": "desk", "event": "fill", "data": 3}]


def test_a_page_whose_send_raises_is_dropped_and_the_others_still_get_it():
    fan = Fanout(hello=lambda: {"type": "desk", "down": "x"})
    good = Page()

    def boom(msg):
        raise RuntimeError("socket gone")

    fan.attach("bad", boom, lambda: True)
    fan.attach(good, good.send, lambda: True)
    fan.publish({"type": "desk", "event": "bot", "data": {}})
    assert good.got[-1] == {"type": "desk", "event": "bot", "data": {}}
    assert "bad" not in fan._boxes


def test_the_link_feeds_the_fanout_without_waiting_on_pages(tmp_path):
    fan = Fanout(maxlen=2)
    link, *_ = mklink(tmp_path, [(200, STATE + ACCT * 20)])
    link.fanout = fan.publish
    fan.hello = link.hello
    stuck = Page(room=False)
    fan.attach(stuck, stuck.send, lambda: stuck.room)
    run(link.run())                                        # completes: never blocked on `stuck`
    stuck.room = True
    fan.flush()
    assert stuck.got == [{"type": "desk", "down": "the desk closed the stream"}]


# ---- the proxy: Host (netguard), Origin (browser_write_ok), JSON, 4 KB ------

def proxy_app(tmp_path, *, link="default", posted=None, write_ok=None):
    posted = [] if posted is None else posted

    def handler(req):
        posted.append((req.url.path, req.headers.get("x-homebase-key"), json.loads(req.content)))
        return httpx.Response(200, json={"results": {}})

    if link == "default":
        link = DeskLink(lambda m: None, key_path=key_file(tmp_path),
                        transport=httpx.MockTransport(handler))
    quotes = Quotes()
    quotes.note("NQ", [{"ts_ms": 5, "price": 100.25, "bid": 100.0, "ask": 100.25}])

    def browser_write_ok(request: Request) -> None:      # as in charts/server.py
        if not origin_ok(request.headers.get("origin"), request.headers.get("host")):
            raise HTTPException(403, "writes from another site are refused")

    app = FastAPI()
    register(app, link=link, quotes=quotes, browser_write_ok=write_ok or browser_write_ok)
    return TestClient(app, base_url="http://127.0.0.1:8852"), posted


def test_proxy_forwards_json_with_the_key_and_our_quotes(tmp_path):
    c, posted = proxy_app(tmp_path)
    r = c.post("/api/desk/order", json={"client_id": "c", "quotes": {"NQ": {"last": 1}}},
               headers={"origin": "http://localhost:8852"})
    assert r.status_code == 200 and r.json() == {"results": {}}
    assert KEY not in r.text
    path, key, body = posted[-1]
    assert (path, key) == ("/api/trade/order", KEY)
    assert body == {"client_id": "c",                                  # the page's quotes replaced
                    "quotes": {"NQ": {"bid": 100.0, "ask": 100.25, "last": 100.25, "ts_ms": 5}}}
    for action in ("modify", "cancel", "cancel-symbol", "flatten", "reverse"):
        assert c.post(f"/api/desk/{action}", json={}).status_code == 200
        assert posted[-1][0] == f"/api/trade/{action}"


def test_proxy_refuses_a_rebinding_host(tmp_path):
    c, posted = proxy_app(tmp_path)
    for host in ("evil.example", "evil.example:8852", "localhost.evil.com", "127.0.0.1.nip.io",
                 "", "127.0.0.1:8852 "):
        r = c.post("/api/desk/order", json={}, headers={"host": host})
        assert r.status_code == 403, host
    for host in ("127.0.0.1", "localhost:8852", "LOCALHOST"):
        assert c.post("/api/desk/order", json={}, headers={"host": host}).status_code == 200, host
    assert len(posted) == 3


def test_proxy_refuses_other_origins(tmp_path):
    c, posted = proxy_app(tmp_path)
    for origin in ("https://evil.example", "null", "http://127.0.0.1.nip.io"):
        assert c.post("/api/desk/order", json={}, headers={"origin": origin}).status_code == 403
    assert posted == []


def test_proxy_applies_the_chart_services_own_origin_rule(tmp_path):
    def refuse(request):
        raise HTTPException(403, "writes from another site are refused")

    c, posted = proxy_app(tmp_path, write_ok=refuse)
    assert c.post("/api/desk/order", json={}).status_code == 403
    assert posted == []


def test_proxy_requires_json_and_caps_the_body(tmp_path):
    c, posted = proxy_app(tmp_path)
    for ct in (None, "text/plain", "application/x-www-form-urlencoded", "multipart/form-data"):
        h = {"content-type": ct} if ct else {}
        assert c.post("/api/desk/order", content=b"{}", headers=h).status_code == 415, ct
    j = {"content-type": "application/json"}
    assert c.post("/api/desk/order", content=b"{" + b" " * 5000 + b"}", headers=j).status_code == 413
    assert c.post("/api/desk/order", content=b"{" + b" " * 4094 + b"}", headers=j).status_code == 200
    assert c.post("/api/desk/order", content=b"[1]", headers=j).status_code == 400
    assert c.post("/api/desk/order", content=b"{nope", headers=j).status_code == 400
    assert c.post("/api/desk/bogus", json={}).status_code == 404
    assert len(posted) == 1


def test_proxy_rejects_nan_and_infinity(tmp_path):
    """json.loads accepts NaN/Infinity/-Infinity by default (non-standard
    JSON); the desk's own body parsing must not silently pass one through."""
    c, posted = proxy_app(tmp_path)
    j = {"content-type": "application/json"}
    for bad in (b'{"x": NaN}', b'{"x": Infinity}', b'{"x": -Infinity}'):
        r = c.post("/api/desk/order", content=bad, headers=j)
        assert r.status_code == 400 and r.json()["detail"] == "invalid number", bad
    assert posted == []


def test_proxy_without_a_link_or_a_key_answers_503(tmp_path):
    c, _ = proxy_app(tmp_path, link=None)                      # replay: no desk link at all
    r = c.post("/api/desk/order", json={})
    assert r.status_code == 503 and r.json()["detail"] == NO_LINK
    nokey = DeskLink(lambda m: None, key_path=tmp_path / "gone" / "desk.key",
                     transport=httpx.MockTransport(lambda req: httpx.Response(200, json={})))
    c, posted = proxy_app(tmp_path, link=nokey)
    r = c.post("/api/desk/order", json={})
    assert r.status_code == 503 and r.json()["detail"].startswith("desk link unavailable")
    assert posted == []


def test_proxy_leaves_the_layout_delete_alone(tmp_path):
    """The page's body-less DELETE /api/layouts/... is not the proxy's."""
    c, _ = proxy_app(tmp_path)
    assert c.delete("/api/desk/order").status_code == 405


# --- the bots: history (GET) and the per-strategy kill (POST) ---------------------------------
def bot_app(tmp_path, *, link="default"):
    seen = []

    def handler(req):
        seen.append(req)
        if req.method == "GET":
            return httpx.Response(200, json={"strategy": "nq930", "symbol": "NQ", "runs": []})
        return httpx.Response(200, json={"ok": True, "results": {}})

    if link == "default":
        link = DeskLink(lambda m: None, key_path=key_file(tmp_path),
                        transport=httpx.MockTransport(handler))

    def browser_write_ok(request: Request) -> None:
        if not origin_ok(request.headers.get("origin"), request.headers.get("host")):
            raise HTTPException(403, "writes from another site are refused")

    app = FastAPI()
    register(app, link=link, quotes=Quotes(), browser_write_ok=browser_write_ok)
    return TestClient(app, base_url="http://127.0.0.1:8852"), seen


def test_bot_kill_is_proxied_like_every_desk_action(tmp_path):
    c, seen = bot_app(tmp_path)
    assert c.post("/api/desk/bot-kill", json={"client_id": "k", "strategy": "nq930"},
                  headers={"origin": "https://evil.example"}).status_code == 403
    r = c.post("/api/desk/bot-kill", json={"client_id": "k", "strategy": "nq930"},
               headers={"origin": "http://localhost:8852"})
    assert r.status_code == 200 and r.json() == {"ok": True, "results": {}}
    req = seen[-1]
    assert (req.method, req.url.path, req.headers["x-homebase-key"]) == ("POST", "/api/trade/bot-kill", KEY)
    assert json.loads(req.content)["strategy"] == "nq930"


def test_bot_history_is_proxied_with_the_key_and_only_its_own_params(tmp_path):
    c, seen = bot_app(tmp_path)
    r = c.get("/api/desk/bot-history?strategy=nq930&days=30&evil=1")
    assert r.status_code == 200 and r.json()["runs"] == []
    assert KEY not in r.text
    req = seen[-1]
    assert (req.method, req.url.path, req.headers["x-homebase-key"]) == ("GET", "/api/trade/bot-history", KEY)
    assert dict(req.url.params) == {"strategy": "nq930", "days": "30"}
    assert "origin" not in req.headers
    c.get("/api/desk/bot-history?strategy=nq930")
    assert dict(seen[-1].url.params) == {"strategy": "nq930"}


def test_bot_history_refuses_a_rebinding_host_and_needs_the_link(tmp_path):
    c, seen = bot_app(tmp_path)
    assert c.get("/api/desk/bot-history?strategy=nq930", headers={"host": "evil.example"}).status_code == 403
    assert seen == []
    c2, _ = bot_app(tmp_path, link=None)
    assert c2.get("/api/desk/bot-history?strategy=nq930").status_code == 503


def test_link_get_maps_failures(tmp_path):
    def handler(req):
        if req.url.params.get("strategy") == "slow":
            raise httpx.ReadTimeout("slow")
        raise httpx.ConnectError("refused")

    link = DeskLink(lambda m: None, key_path=key_file(tmp_path), transport=httpx.MockTransport(handler))
    status, body = run(link.get("bot-history", {"strategy": "slow"}))
    assert status == 504
    assert run(link.get("bot-history", {"strategy": "x"})) == (502, {"detail": "desk unreachable: ConnectError"})
    nokey = DeskLink(lambda m: None, key_path=tmp_path / "missing.key")
    status, body = run(nokey.get("bot-history", {}))
    assert status == 503 and body["detail"].startswith("desk link unavailable")
