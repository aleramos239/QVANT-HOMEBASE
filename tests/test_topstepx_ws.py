from __future__ import annotations

import asyncio
import json
from http import HTTPStatus

import pytest
import websockets
from websockets.asyncio.server import serve

from homebase.broker import topstepx_ws
from homebase.broker.login_budget import LoginDeferred
from homebase.broker.topstepx_ws import RS, TsxHub

TOKEN = "TOK-SECRET-123"
_REAL_CONNECT = websockets.connect      # conftest blocks websockets.connect for every test; these talk to 127.0.0.1 only


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    monkeypatch.setattr(websockets, "connect", _REAL_CONNECT)
    monkeypatch.setattr(topstepx_ws, "RECONNECT_S", (0.01, 0.01, 0.02))


class FakeSession:
    def __init__(self, relogin_error=None):
        self.relogins: list[str] = []
        self.relogin_error = relogin_error

    async def token(self) -> str:
        return TOKEN

    async def relogin(self, why: str) -> None:
        self.relogins.append(why)
        if self.relogin_error:
            raise self.relogin_error


class Server:
    """A local SignalR-ish server: `script(ws, n)` runs on the n-th good connection; the first `refuse` connections get 401."""

    def __init__(self, script=None, refuse=0):
        self.script, self.refuse = script, refuse
        self.paths: list[str] = []
        self.headers: list = []
        self.got: list[list[str]] = []        # per connection: the records the client sent
        self.opens = 0

    async def _gate(self, conn, request):
        self.paths.append(request.path)
        self.headers.append(request.headers)
        if len(self.paths) <= self.refuse:
            return conn.respond(HTTPStatus.UNAUTHORIZED, "no\n")

    async def _handle(self, ws):
        n = self.opens = self.opens + 1
        recs: list[str] = []
        self.got.append(recs)

        async def read():
            async for m in ws:
                recs.extend(r for r in m.split(RS) if r)
        reader = asyncio.create_task(read())
        try:
            await asyncio.sleep(0.05)         # the client's two opening records
            if self.script:
                await self.script(ws, n)
            await reader
        except Exception:
            pass
        finally:
            reader.cancel()

    def serving(self):
        return serve(self._handle, "127.0.0.1", 0, process_request=self._gate)


def url_of(srv) -> str:
    return f"ws://127.0.0.1:{srv.sockets[0].getsockname()[1]}/hubs/account"


async def until(pred, timeout=3.0):
    end = asyncio.get_running_loop().time() + timeout
    while not pred():
        assert asyncio.get_running_loop().time() < end, "timed out"
        await asyncio.sleep(0.01)


def test_handshake_then_SubscribeAccounts_is_sent():
    async def go():
        server = Server()
        async with server.serving() as srv:
            hub = TsxHub(FakeSession(), lambda t, a: None, url=url_of(srv))
            await hub.start()
            await until(lambda: server.got and len(server.got[0]) >= 2)
            assert hub.up
            await hub.stop()
        assert [json.loads(r) for r in server.got[0][:2]] == [
            {"protocol": "json", "version": 1},
            {"type": 1, "target": "SubscribeAccounts", "arguments": []}]
        assert server.paths[0].endswith(f"?access_token={TOKEN}")
        assert server.headers[0]["Origin"] == "https://topstepx.com"
    asyncio.run(go())


def test_invocations_reach_on_event_and_pings_are_answered():
    got = []

    async def script(ws, n):
        two = [{"type": 1, "target": "GatewayUserTrade", "arguments": [{"id": 1}]},
               {"type": 1, "target": "GatewayUserOrder", "arguments": [{"id": 2}, {"id": 3}]}]
        await ws.send("".join(json.dumps(m) + RS for m in two) + json.dumps({"type": 6}) + RS)
        await asyncio.sleep(0.3)

    async def go():
        server = Server(script)
        async with server.serving() as srv:
            hub = TsxHub(FakeSession(), lambda t, a: got.append((t, a)), url=url_of(srv))
            await hub.start()
            await until(lambda: len(got) >= 3 and '{"type": 6}' in server.got[0])
            await hub.stop()
    asyncio.run(go())
    assert got == [("GatewayUserTrade", {"id": 1}), ("GatewayUserOrder", {"id": 2}), ("GatewayUserOrder", {"id": 3})]


@pytest.mark.parametrize("how", ["close frame", "type 7"])
def test_a_close_reconnects_and_calls_on_up(how):
    ups = []

    async def script(ws, n):
        if n == 1:
            if how == "type 7":
                await ws.send(json.dumps({"type": 7}) + RS)
                await asyncio.sleep(0.3)
            else:
                await ws.close()
        else:
            await asyncio.sleep(0.5)

    async def on_up():
        ups.append(1)

    async def go():
        server = Server(script)
        async with server.serving() as srv:
            hub = TsxHub(FakeSession(), lambda t, a: None, url=url_of(srv), on_up=on_up)
            await hub.start()
            await until(lambda: server.opens >= 2 and len(ups) >= 2)
            await hub.stop()
            assert not hub.up
    asyncio.run(go())


def test_a_401_at_open_relogs_in_through_the_session_once():
    async def go():
        session = FakeSession()
        server = Server(refuse=1)
        async with server.serving() as srv:
            hub = TsxHub(session, lambda t, a: None, url=url_of(srv))
            await hub.start()
            await until(lambda: hub.up)
            await hub.stop()
        assert session.relogins == ["socket 401"]
        assert len(server.paths) == 2
    asyncio.run(go())


def test_on_auth_lost_replaces_the_relogin_and_a_deferral_does_not_spin(capsys):
    async def go():
        session = FakeSession()
        calls = []

        async def lost():
            calls.append(1)
            raise LoginDeferred("cap reached")
        server = Server(refuse=3)
        async with server.serving() as srv:
            hub = TsxHub(session, lambda t, a: None, url=url_of(srv), on_auth_lost=lost)
            await hub.start()
            await until(lambda: hub.up)
            await hub.stop()
        assert session.relogins == []
        assert len(calls) == 3          # once per failed open, not more
    asyncio.run(go())
    assert "re-login deferred: cap reached" in capsys.readouterr().err


def test_the_token_is_never_logged(capsys):
    async def go():
        session = FakeSession(relogin_error=RuntimeError(f"boom {TOKEN}"))
        server = Server(refuse=1)
        async with server.serving() as srv:
            hub = TsxHub(session, lambda t, a: None, url=url_of(srv))
            await hub.start()
            await until(lambda: hub.up)
            await hub.stop()
        hub = TsxHub(session, lambda t, a: None, url="ws://127.0.0.1:1/hubs/account")     # nothing listens: a connect error
        await hub.start()
        await asyncio.sleep(0.1)
        await hub.stop()
    asyncio.run(go())
    err = capsys.readouterr().err
    assert "socket up" in err and "open refused" in err
    assert TOKEN not in err


def test_stop_ends_the_loop_cleanly():
    async def go():
        server = Server()
        async with server.serving() as srv:
            hub = TsxHub(FakeSession(), lambda t, a: None, url=url_of(srv))
            await hub.start()
            await until(lambda: hub.up)
            task = hub._task
            await hub.stop()
            assert task.done() and not hub.up
        await asyncio.sleep(0.05)
        assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    asyncio.run(go())


def _record_pauses(monkeypatch, schedule=(0.01, 0.02, 0.03, 0.04)):
    monkeypatch.setattr(topstepx_ws, "RECONNECT_S", schedule)
    pauses: list[float] = []

    async def pause(s):
        pauses.append(s)
        await asyncio.sleep(0.001)
    monkeypatch.setattr(topstepx_ws, "_pause", pause)
    return pauses


def test_a_socket_closed_right_after_open_does_not_reset_the_backoff(monkeypatch):
    pauses = _record_pauses(monkeypatch)
    ups = []

    async def script(ws, n):
        await ws.close()

    async def on_up():
        ups.append(1)

    async def go():
        server = Server(script)
        async with server.serving() as srv:
            hub = TsxHub(FakeSession(), lambda t, a: None, url=url_of(srv), on_up=on_up)
            await hub.start()
            await until(lambda: len(pauses) >= 6)
            await hub.stop()
    asyncio.run(go())
    assert pauses[:6] == [0.01, 0.02, 0.03, 0.04, 0.04, 0.04]      # escalates, then holds the last step
    assert len(ups) >= 6


def test_a_socket_that_lived_past_the_threshold_starts_the_backoff_over(monkeypatch):
    pauses = _record_pauses(monkeypatch)
    monkeypatch.setattr(topstepx_ws, "STABLE_S", 0.15)

    async def script(ws, n):
        if n in (3, 5):                     # the third and fifth sockets live long enough, the others die at once
            await asyncio.sleep(0.3)
        await ws.close()

    async def go():
        server = Server(script)
        async with server.serving() as srv:
            hub = TsxHub(FakeSession(), lambda t, a: None, url=url_of(srv))
            await hub.start()
            await until(lambda: len(pauses) >= 6)
            await hub.stop()
    asyncio.run(go())
    assert pauses[:6] == [0.01, 0.02, 0.01, 0.02, 0.01, 0.02]


def test_a_handshake_error_reply_is_logged_without_the_token(capsys):
    async def script(ws, n):
        await ws.send(json.dumps({"error": f"Requested protocol 'x' is not available {TOKEN}"}) + RS)
        await asyncio.sleep(0.2)

    async def go():
        server = Server(script)
        async with server.serving() as srv:
            hub = TsxHub(FakeSession(), lambda t, a: None, url=url_of(srv))
            await hub.start()
            await asyncio.sleep(0.2)
            await hub.stop()
    asyncio.run(go())
    err = capsys.readouterr().err
    assert "server error: Requested protocol 'x' is not available ***" in err
    assert TOKEN not in err
