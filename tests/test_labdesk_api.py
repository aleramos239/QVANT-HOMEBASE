"""Step B (B3): /api/lab/* -- the runner's door into the desk. Its gate (a loopback Host, no Origin, the runner's OWN
key in lab.key), run against the trade router's gate with the same cases; the four routes; the page route
/api/lab-clear. The real desk app on fake adapters: no network, no broker, a temp state folder and store."""
from __future__ import annotations

import asyncio
import json
import os
import re
import stat

import pytest
from fastapi.testclient import TestClient

import homebase.config as config_mod
from homebase import desk_api
from homebase.config import AccountCfg, AppCfg, StrategyCfg
from homebase.labrun import store
from homebase.server import create_app
from tests.labdesk_util import DATE, LAB, LIMITS, MARK, entry, rec
from tests.test_engine import Clock, FakeAdapter
from tests.test_engine_lab import LabAdapter, quick

DESK = "http://127.0.0.1:8850"
OFF = "Lab strategies are switched off on this Desk."
LAB_ROUTES = [("get", "/api/lab/state"), ("get", "/api/lab/stream"), ("post", "/api/lab/intent"),
              ("post", "/api/lab/heartbeat")]
TRADE_ROUTES = [("get", "/api/trade/state"), ("get", "/api/trade/stream"), ("post", "/api/trade/order")]


@pytest.fixture()
def paths(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.engine.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.server.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.secrets_store.state_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    # the real clock would pause the chart views at 09:29:50-09:30:30 ET: never flake then
    monkeypatch.setattr("homebase.trading.ChartDesk._views_paused", lambda self: False)
    return tmp_path


def make_app(lab=True, booked=True):
    """The desk at 10:00 ET on a Monday, armed, one account; with the Lab side on: pp promoted, on, limits set, booked."""
    store.put(rec())
    cfg = AppCfg(armed=True, accounts={"a1": AccountCfg(keyring_key="k", account_name="A1", label="A1")},
                 book={}, strategies={"nq930": StrategyCfg(symbol="ES", qty=1, offset_pts=10.0, sl_pts=5.0, tp_pts=15.0,
                                                           enabled=False)})
    adapters = {"a1": LabAdapter("a1")}
    app = create_app(cfg, adapters, background=False, adapter_factory=lambda aid, a: FakeAdapter(aid), lab=lab)
    clock = Clock()
    clock.set_et(10, 0)
    app.state.engine._now = clock
    quick(app.state.engine)
    if lab:
        ld = app.state.labdesk
        asyncio.run(ld.refresh())
        asyncio.run(ld.set_limits(LAB, LIMITS))
        if booked:
            asyncio.run(ld.set_book(LAB, [{"account": "a1", "qty": 1}]))
    return app, clock


@pytest.fixture()
def client(paths):
    app, clock = make_app()
    with TestClient(app, base_url=DESK) as c:
        c.app, c.tmp, c.clock, c.adapters = app, paths, clock, app.state.adapters
        c.H = {"X-Homebase-Key": (paths / "lab.key").read_text().strip()}
        c.T = {"X-Homebase-Key": (paths / "desk.key").read_text().strip()}
        yield c
        app.state.labdesk.close()


def event(c, intents, seq=1, **over):
    ms = int(c.clock().timestamp() * 1000)
    return {"strategy": LAB, "date": DATE, "mark": list(MARK), "seq": seq, "t_ns": ms * 1_000_000,
            "state": {"last_price": 100.0, "last_ms": ms, "prices_late": False}, "intents": intents, **over}


def jl(tmp, name):
    p = tmp / "journal.jsonl"
    return [r for r in map(json.loads, p.read_text().splitlines()) if r["event"] == name] if p.exists() else []


# ---------------------------------------------------------------- the key
def test_the_runners_key_is_its_own_file_0600_and_never_the_chart_services(client):
    p = client.tmp / "lab.key"
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    assert re.fullmatch(r"[0-9a-f]{64}", client.H["X-Homebase-Key"])
    assert client.H != client.T and desk_api.LAB_KEY_FILE == "lab.key"
    assert client.H["X-Homebase-Key"] not in (client.tmp / "journal.jsonl").read_text()      # never written down


# ---------------------------------------------------------------- the gate, against both routers
def gate_cases(c, routes, key, other):
    """The same refusals, whatever the router: no key, a wrong key, the OTHER router's key, a browser, a rebound Host."""
    for m, url in routes:
        send = getattr(c, m)
        kw = {"json": {}} if m == "post" else {}
        assert send(url, **kw).status_code == 401, url
        assert send(url, headers={"X-Homebase-Key": "0" * 64}, **kw).status_code == 401, url
        assert send(url, headers=other, **kw).status_code == 401, url
        assert send(url, headers={**key, "Origin": DESK}, **kw).status_code == 403, url
        assert send(url, headers={**key, "Origin": "https://evil.example"}, **kw).status_code == 403, url
        for host in ("evil.example:8850", "127.0.0.1.evil.example", "localhost.evil.example:8850"):
            assert send(url, headers={**key, "host": host}, **kw).status_code == 403, (url, host)


def test_the_same_refusals_at_the_runners_gate_and_at_the_chart_services(client):
    gate_cases(client, LAB_ROUTES, client.H, client.T)
    gate_cases(client, TRADE_ROUTES, client.T, client.H)
    assert client.adapters["a1"].brackets == [] and client.adapters["a1"].orders == []
    assert client.get("/api/lab/state", headers={**client.H, "host": "localhost:8850"}).status_code == 200
    assert client.get("/api/trade/state", headers={**client.T, "host": "localhost:8850"}).status_code == 200


def test_the_chart_services_key_cannot_send_a_strategy_order(client):      # design D9
    r = client.post("/api/lab/intent", headers=client.T, json=event(client, [entry()]))
    assert r.status_code == 401 and client.adapters["a1"].brackets == []


def test_both_gates_answer_503_when_their_key_cannot_be_read(client):
    client.app.state.lab_key = None
    for m, url in LAB_ROUTES:
        assert getattr(client, m)(url, headers=client.H, **({"json": {}} if m == "post" else {})).status_code == 503, url
    client.app.state.desk_key = None
    assert client.get("/api/trade/state", headers=client.T).status_code == 503


def test_a_key_file_that_holds_no_key_is_journaled_and_the_desk_still_starts(paths):
    (paths / "lab.key").write_text("nope\n")
    app, _ = make_app()
    with TestClient(app, base_url=DESK) as c:
        assert c.get("/api/status").status_code == 200
        assert c.get("/api/lab/state", headers={"X-Homebase-Key": "nope"}).status_code == 503
        errs = jl(paths, "lab_key_error")
        assert len(errs) == 1 and "lab.key" in errs[0]["error"] and "nope" not in json.dumps(errs)
        app.state.labdesk.close()


def test_the_page_guard_applies_to_the_runners_routes_too(client):
    """/api/lab/* is not skipped by WriteGuard (only /api/trade/ is): a write must be JSON, whatever its key."""
    r = client.post("/api/lab/intent", headers={**client.H, "content-type": "text/plain"}, content=b"{}")
    assert r.status_code == 415
    r = client.post("/api/lab/heartbeat", headers={**client.H, "content-type": "text/plain"}, content=b"{}")
    assert r.status_code == 415


# ---------------------------------------------------------------- the Lab side off
def test_with_the_lab_side_off_every_route_says_so_behind_the_gate(paths):
    app, clock = make_app(lab=False)
    with TestClient(app, base_url=DESK) as c:
        H = {"X-Homebase-Key": (paths / "lab.key").read_text().strip()}
        for m, url in LAB_ROUTES:
            send = getattr(c, m)
            kw = {"json": {}} if m == "post" else {}
            assert send(url, **kw).status_code == 401, url                       # the gate comes first
            r = send(url, headers=H, **kw)
            assert (r.status_code, r.json()["detail"]) == (409, OFF), url
        r = c.post("/api/lab-clear", json={"strategy": LAB, "account": "a1"})
        assert (r.status_code, r.json()["detail"]) == (409, OFF)
        assert jl(paths, "lab_side") == [] and jl(paths, "lab_open_without_cfg") == []   # an OFF desk journals no Lab line
        assert not (paths / "labday-2026-09-14.json").exists()                   # the store and the Lab files: untouched
        assert app.state.adapters["a1"].brackets == []


def test_one_journal_line_at_start_says_the_lab_side_is_on(client):
    lines = jl(client.tmp, "lab_side")
    assert len(lines) == 1 and lines[0]["on"] is True


# ---------------------------------------------------------------- the four routes
def test_intent_places_the_entry_and_answers_results_and_the_brain(client):
    r = client.post("/api/lab/intent", headers=client.H, json=event(client, [entry()]))
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["ok"] is True and out["results"][0]["status"] == "working" and out["results"][0]["refused"] is None
    assert out["results"][0]["accounts"]["a1"]["ok"] is True and out["results"][0]["accounts"]["a1"]["round"] == 1
    assert out["brain"] == {"flat": True, "working": 1, "entries_today": 1, "orders": {"1": {"status": "working"}}}
    b = client.adapters["a1"].brackets
    assert [(q.side, q.order_type, q.price, q.stop_price, q.tp_price, q.qty) for q in b] == [("Buy", "Stop", 110.0, 105.0, 120.0, 1)]


def test_intent_refuses_a_body_that_does_not_read_with_400_and_one_too_large_with_413(client):
    post = lambda **kw: client.post("/api/lab/intent", **{"headers": client.H, **kw})       # noqa: E731
    assert post(content=b"not json", headers={**client.H, "content-type": "application/json"}).status_code == 400
    assert post(json=[1, 2]).status_code == 400
    assert post(json=event(client, [{"op": "entry", "id": 1}])).status_code == 400
    assert post(json=event(client, [entry()], seq="1")).status_code == 400
    assert post(json=event(client, [{"op": "cancel", "id": i} for i in range(21)])).status_code == 400   # 20 at most
    big = event(client, [entry()], pad="x" * 20000)
    assert post(json=big).status_code == 413
    assert client.adapters["a1"].brackets == []


def test_intent_answers_429_when_the_strategy_sends_too_many_entries_a_second(client):
    codes = [client.post("/api/lab/intent", headers=client.H, json=event(client, [entry(i)], seq=i)).status_code
             for i in range(1, 8)]
    assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]
    r = client.post("/api/lab/intent", headers=client.H, json=event(client, [entry(9)], seq=9))
    assert r.json()["detail"] == "Too many orders at once."
    assert len(client.adapters["a1"].brackets) == 1                              # ... and only the first was a trade


def test_heartbeat_answers_what_the_runner_needs_to_know(client):
    r = client.post("/api/lab/heartbeat", headers=client.H,
                    json={"pid": 4242, "strategies": {LAB: {"state": "running", "why": None, "mode": "desk"},
                                                      "lab_nope": {"state": "running", "why": None, "mode": "shadow"}}})
    assert r.status_code == 200
    assert r.json() == {"ok": True, "armed": True, "strategies": {LAB: {"enabled": True, "killed": False, "stopped": None}}}
    assert client.post("/api/lab/heartbeat", headers=client.H, json={"pid": "x"}).status_code == 400
    assert client.post("/api/lab/heartbeat", headers=client.H, json=[]).status_code == 400


def test_state_is_the_snapshot_and_is_held_back_while_the_930_orders_are_placing(client):
    client.post("/api/lab/intent", headers=client.H, json=event(client, [entry()]))
    s = client.get("/api/lab/state", headers=client.H).json()
    assert s["date"] == DATE and s["armed"] is True and list(s["strategies"]) == [LAB]
    one = s["strategies"][LAB]
    assert (one["strategy"], one["mark"], one["date"], one["enabled"], one["armed"], one["killed"], one["stopped"]) == \
        (LAB, MARK, DATE, True, True, False, None)
    assert one["brain"]["orders"] == {"1": {"status": "working"}} and one["answered"] == [1]
    assert [(r["account"], r["round"], r["status"], r["iid"], r["qty"]) for r in one["rounds"]] == \
        [("a1", 1, "placed", {"Buy": 1}, 1)]
    st = client.app.state.engine._state("nq930", "a1")
    st.status = "placing"                                                        # the 9:30 bot's acks are out
    r = client.get("/api/lab/state", headers=client.H)
    assert (r.status_code, r.json()) == (503, {"error": "paused around the 9:30 fire"})
    st.status = "placed"
    assert client.get("/api/lab/state", headers=client.H).status_code == 200


def test_the_stream_sends_the_state_first(client):
    async def first():
        gen = desk_api.lab_stream(client.app.state.labdesk, heartbeat_s=0.05)
        try:
            return [await gen.__anext__(), await gen.__anext__()]
        finally:
            await gen.aclose()
    state, beat = asyncio.run(first())
    assert state.startswith("event: state\ndata: ") and json.loads(state.split("data: ", 1)[1])["strategies"][LAB]["enabled"]
    assert beat.startswith("event: heartbeat\n")
    assert client.app.state.labdesk._subs == set()                               # the reader is forgotten when it ends
    assert desk_api.LAB_HEARTBEAT_S == 5.0


# ---------------------------------------------------------------- the page route: clear a carried block
def test_lab_clear_answers_the_engines_sentence(client):
    r = client.post("/api/lab-clear", json={"strategy": LAB, "account": "a1"})
    assert (r.status_code, r.json()["detail"]) == (409, "This account has no block to clear.")
    r = client.post("/api/lab-clear", json={"strategy": "nq930", "account": "a1"})
    assert (r.status_code, r.json()["detail"]) == (404, "That strategy is not on the Desk.")
    assert client.post("/api/lab-clear", json=[]).status_code == 400
    assert client.post("/api/lab-clear", content=b"{}", headers={"content-type": "text/plain"}).status_code == 415
    assert client.post("/api/lab-clear", json={"strategy": LAB, "account": "a1"},
                       headers={"origin": "https://evil.example"}).status_code == 403


def test_lab_clear_removes_a_block_and_needs_no_store_ownership(client):
    eng, ld = client.app.state.engine, client.app.state.labdesk
    eng.lab_open(LAB)
    assert eng._lab_carry_make((LAB, "a1"), {"date": "2026-09-11", "status": "live", "orders": []}, DATE) is True
    assert eng.lab_open(LAB) == ["a1"]
    ld.close()                                                                   # the store is no longer this desk's
    client.adapters["a1"].net = 1
    r = client.post("/api/lab-clear", json={"strategy": LAB, "account": "a1"})
    assert (r.status_code, r.json()["detail"]) == (409, "The account already holds NQ. Check it.")
    client.adapters["a1"].net = 0
    r = client.post("/api/lab-clear", json={"strategy": LAB, "account": "a1"})
    assert r.status_code == 200 and r.json() == {"ok": True, "cleared": ["2026-09-11"]}
    assert eng.lab_open(LAB) == [] and client.adapters["a1"].orders == []        # it sent nothing


def test_the_file_modes_of_the_two_keys_never_loosen(client):
    for f in ("lab.key", "desk.key"):
        os.chmod(client.tmp / f, 0o644)
        assert desk_api.ensure_key(client.tmp / f)[1] is None
        assert stat.S_IMODE((client.tmp / f).stat().st_mode) == 0o600


# ================================================================ fix round 1 (task-b3-review.md)
def test_the_runners_gate_refuses_a_host_the_page_allows(paths):                         # I7: runner_gate's own Host check
    """cfg.allowed_hosts lets the PAGE be opened by another name; the runner's door stays loopback only."""
    app, clock = make_app()
    app.state.cfg.allowed_hosts = ["desk.lan", "100.64.0.7"]
    with TestClient(app, base_url=DESK) as c:
        c.clock = clock
        H = {"X-Homebase-Key": (paths / "lab.key").read_text().strip()}
        T = {"X-Homebase-Key": (paths / "desk.key").read_text().strip()}
        assert c.get("/api/status", headers={"host": "desk.lan:8850"}).status_code == 200
        assert c.get("/api/lab/state", headers={**H, "host": "desk.lan:8850"}).status_code == 403
        assert c.post("/api/lab/intent", headers={**H, "host": "100.64.0.7:8850"}, json=event(c, [entry()])).status_code == 403
        assert c.get("/api/trade/state", headers={**T, "host": "desk.lan:8850"}).status_code == 403
        assert app.state.adapters["a1"].brackets == []
        app.state.labdesk.close()


def calls_of(client):
    """Spy on the three steps of the two switch-off routes, in the order they run."""
    ld, eng, order = client.app.state.labdesk, client.app.state.engine, []
    real_stop, real_flat, real_set = ld.stop, eng.flatten_strategy, ld.set_enabled

    async def stop(name, why, flatten=False):
        order.append(("stop", why))
        return await real_stop(name, why, flatten)

    async def flat(name):
        order.append(("flatten", ld._rec(name)["stopped"]))
        return await real_flat(name)

    async def set_enabled(name, on):
        order.append(("write", on))
        return await real_set(name, on)
    ld.stop, eng.flatten_strategy, ld.set_enabled = stop, flat, set_enabled
    return order


def test_flatten_and_turn_off_ends_the_day_before_anything_else(client):                 # m3
    client.post("/api/lab/intent", headers=client.H, json=event(client, [entry()]))
    order = calls_of(client)
    r = client.post("/api/strategy-flatten", json={"strategy": LAB})
    assert r.status_code == 200 and r.json()["enabled"] is False
    assert order == [("stop", "off"), ("flatten", "off"), ("write", False)]
    assert client.app.state.labdesk._rec(LAB)["stopped"] == "off"
    assert [(x["why"], x["cause"]) for x in jl(client.tmp, "lab_stopped")] == [("off", "desk")]
    st = client.app.state.engine.states[f"{LAB}@a1"]
    assert (st.status, st.exit_reason) == ("done", "cancelled")
    out = client.post("/api/lab/intent", headers=client.H, json=event(client, [entry(2)], seq=2)).json()
    assert out["results"][0]["refused"] in ("It is off.", "Stopped for today.")


def test_a_switch_off_stops_the_day_before_the_store_is_written_even_when_the_write_fails(client):   # m3
    from homebase.labdesk import NOT_SAVED, Refused
    client.post("/api/lab/intent", headers=client.H, json=event(client, [entry()]))
    order = calls_of(client)
    ld = client.app.state.labdesk
    inner = ld.set_enabled

    async def cannot(name, on):
        await inner(name, on) if False else order.append(("write", on))
        raise Refused(NOT_SAVED)
    ld.set_enabled = cannot
    r = client.post("/api/strategy", json={"strategy": LAB, "enabled": False})
    assert (r.status_code, r.json()["detail"]) == (409, "Could not save it. Try again.")
    assert order == [("stop", "off"), ("write", False)]
    st = client.app.state.engine.states[f"{LAB}@a1"]
    assert (st.status, st.exit_reason) == ("done", "cancelled")                    # the resting entry is gone all the same
    assert ld._rec(LAB)["stopped"] == "off"


def test_switching_on_never_stops_the_day_and_another_kind_is_never_asked(client):
    order = calls_of(client)
    assert client.post("/api/strategy", json={"strategy": LAB, "enabled": True}).status_code == 200
    assert client.post("/api/strategy", json={"strategy": "nq930", "enabled": False}).status_code == 200
    assert client.post("/api/strategy-flatten", json={"strategy": "nq930"}).status_code == 200
    assert order == [("write", True), ("flatten", None)] and jl(client.tmp, "lab_stopped") == []


def test_a_start_call_that_raises_never_stops_the_desk_from_starting(paths, monkeypatch):   # m4
    app, _ = make_app()

    def boom():
        raise RuntimeError("the start blew up")
    monkeypatch.setattr(app.state.labdesk, "start", boom)
    with TestClient(app, base_url=DESK) as c:
        assert c.get("/api/status").status_code == 200
        errs = jl(paths, "lab_start_error")
        assert len(errs) == 1 and "the start blew up" in errs[0]["error"]
        app.state.labdesk.close()


def test_a_key_that_cannot_be_made_never_stops_the_desk_from_starting(paths, monkeypatch):   # m4
    real = desk_api.ensure_key

    def flaky(path):
        if path.name == "lab.key":
            raise OSError(28, "No space left on device")
        return real(path)
    monkeypatch.setattr(desk_api, "ensure_key", flaky)
    app, _ = make_app()
    with TestClient(app, base_url=DESK) as c:
        assert c.get("/api/status").status_code == 200
        assert c.get("/api/lab/state", headers={"X-Homebase-Key": "0" * 64}).status_code == 503
        assert c.get("/api/trade/state", headers={"X-Homebase-Key": (paths / "desk.key").read_text().strip()}).status_code == 200
        assert len(jl(paths, "lab_start_error")) == 1 and jl(paths, "lab_side") == [{**jl(paths, "lab_side")[0], "on": True}]
        app.state.labdesk.close()
