from __future__ import annotations

import asyncio
import logging

import httpx
import pytest
import websockets
from websockets.asyncio.server import serve

from homebase.broker import alphatrader_proto as proto
from homebase.broker import alphatrader_ws, login_budget
from homebase.broker.alphatrader_auth import AtrLoginFailed, AtrSession, NeedsCode, T4Creds
from homebase.broker.alphatrader_ws import AtrSocket
from homebase.broker.login_budget import LoginBudget

KEY = "atr:o@x.com"
USER, PW = "t4user-SECRET-9", "t4pw-SECRET-7"
CREDS = T4Creds("AlphaFutures", USER, PW, "AlphaApp", "LIC-1")
_REAL_CONNECT = websockets.connect      # conftest blocks websockets.connect; these talk to 127.0.0.1 only


@pytest.fixture(autouse=True)
def fast(monkeypatch):
    """Waits are recorded and shortened; the ladder keeps its real values so a test can read them."""
    monkeypatch.setattr(websockets, "connect", _REAL_CONNECT)
    pauses: list[float] = []

    async def pause(s):
        pauses.append(s)
        await asyncio.sleep(0.005)
    monkeypatch.setattr(alphatrader_ws, "_pause", pause)
    return pauses


class Budget(LoginBudget):
    def __init__(self):
        super().__init__()
        self.slots = 0
        self.results: list = []

    def record_login(self, key):
        self.slots += 1
        super().record_login(key)

    def login_result(self, key, err=None):
        self.results.append(err)
        super().login_result(key, err)


@pytest.fixture
def roomy(monkeypatch):
    """A budget with room for a test that logs in many times."""
    monkeypatch.setattr(login_budget, "MAX_LOGINS_PER_HOUR", 100)


def make_session(creds_errors=()):
    """A real AtrSession and budget; only the credential fetch is faked (it never reaches Alpha)."""
    s = AtrSession(KEY, budget=Budget())
    errors = list(creds_errors)
    s.fetches = 0

    async def t4_creds():
        s.fetches += 1
        if errors:
            raise errors.pop(0)
        return CREDS
    s.t4_creds = t4_creds
    return s


def msg(payload, data):
    return proto.encode("ServerMessage", {payload: data})


class T4:
    """A local T4: answers each loginRequest with `answer(n)` (n = the connection), then runs `script(ws, n)`."""

    def __init__(self, script=None, answer=lambda n: {}):
        self.script, self.answer = script, answer
        self.got: list[list] = []            # per connection: (payload, dict) the client sent
        self.opens = 0

    def logins(self):
        return [d for c in self.got for p, d in c if p == "loginRequest"]

    async def _handle(self, ws):
        n = self.opens = self.opens + 1
        got: list = []
        self.got.append(got)
        tasks = []
        try:
            async for raw in ws:
                for name, data in proto.decode("ClientMessage", raw).items():
                    got.append((name, data))
                    if name == "loginRequest":
                        answer = self.answer(n)
                        await ws.send(msg("loginResponse", answer))
                        if not answer.get("result") and self.script:
                            tasks.append(asyncio.create_task(self.script(ws, n)))
        except websockets.ConnectionClosed:
            pass
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    def serving(self):
        return serve(self._handle, "127.0.0.1", 0)


def url_of(srv) -> str:
    return f"ws://127.0.0.1:{srv.sockets[0].getsockname()[1]}/v1"


async def until(pred, timeout=3.0):
    end = asyncio.get_running_loop().time() + timeout
    while not pred():
        assert asyncio.get_running_loop().time() < end, "timed out"
        await asyncio.sleep(0.01)


def test_login_then_account_subscribe_are_sent_and_up_after_success():
    ups = []

    async def on_up():
        ups.append(sock.up)

    async def go():
        nonlocal sock
        t4 = T4()
        s = make_session()
        s.lost = "deferred earlier"
        async with t4.serving() as srv:
            sock = AtrSocket(s, lambda p, d: None, url=url_of(srv), on_up=on_up)
            await sock.start()
            await until(lambda: ups)
            assert sock.up and s.lost is None
            await sock.stop()
            assert not sock.up
        assert t4.got[0][:2] == [
            ("loginRequest", {"firm": "AlphaFutures", "username": USER, "password": PW, "appName": "AlphaApp",
                              "appLicense": "LIC-1"}),
            ("accountSubscribe", {"subscribe": proto.ALL_UPDATES, "subscribeAllAccounts": True, "uplMode": 1})]
        assert ups == [True]
        assert s.budget.slots == 1 and s.budget.results == [None]       # the success is reported: it resets the backoff
    sock = None
    asyncio.run(go())


def test_payloads_reach_on_event_and_heartbeats_do_not(monkeypatch):
    monkeypatch.setattr(alphatrader_ws, "HEARTBEAT_S", 0.05)
    got = []

    async def script(ws, n):
        await ws.send(msg("heartbeat", {"timestamp": 123}))
        await ws.send(msg("accountUpdate", {"accountId": "A1", "balance": 50000.0}))
        await ws.send(b"")                                       # an empty frame is skipped
        await ws.send(msg("orderUpdate", {"uniqueId": "U1", "status": proto.WORKING}))
        await asyncio.sleep(1)

    async def go():
        t4 = T4(script)
        async with t4.serving() as srv:
            sock = AtrSocket(make_session(), lambda p, d: got.append((p, d)), url=url_of(srv))
            await sock.start()
            await until(lambda: len(got) >= 2 and any(p == "heartbeat" for p, _ in t4.got[0]))
            await sock.stop()
        beats = [d for p, d in t4.got[0] if p == "heartbeat"]
        assert beats[0]["timestamp"] > 1_700_000_000_000                # ms since the epoch
    asyncio.run(go())
    assert got == [("loginResponse", {}),                                # the successful login answer (result 0)
                   ("accountUpdate", {"accountId": "A1", "balance": 50000.0}),
                   ("orderUpdate", {"uniqueId": "U1", "status": proto.WORKING})]


@pytest.mark.parametrize("result", [proto.LOGGED_IN_ELSEWHERE, proto.LOGOUT])
def test_logged_in_elsewhere_calls_on_taken_and_logs_in_again_once(result, fast):
    taken, ups = [], []

    async def script(ws, n):
        if n == 1:
            await asyncio.sleep(0.05)
            await ws.send(msg("loginResponse", {"result": result}))
        await asyncio.sleep(1)

    async def on_taken(why):
        taken.append((why, sock.up))

    async def on_up():
        ups.append(1)

    async def go():
        nonlocal sock
        t4 = T4(script)
        s = make_session()
        async with t4.serving() as srv:
            sock = AtrSocket(s, lambda p, d: None, url=url_of(srv), on_up=on_up, on_taken=on_taken)
            await sock.start()
            await until(lambda: len(ups) == 2)
            await asyncio.sleep(0.1)
            await sock.stop()
        assert taken == [("logged in elsewhere", False)]
        assert len(t4.logins()) == 2 and s.fetches == 2 and s.budget.slots == 2
        assert s.budget.results == [None, None] and s.taken == 0
    sock = None
    asyncio.run(go())
    assert fast == []                                           # logged in again at once, no wait


def test_logged_in_elsewhere_with_the_budget_spent_waits_and_sets_lost(monkeypatch, fast):
    monkeypatch.setattr(login_budget, "MAX_LOGINS_PER_HOUR", 1)
    taken = []

    async def script(ws, n):
        await ws.send(msg("loginResponse", {"result": proto.LOGGED_IN_ELSEWHERE}))
        await asyncio.sleep(1)

    async def on_taken(why):
        taken.append(why)

    async def go():
        t4 = T4(script)
        s = make_session()
        async with t4.serving() as srv:
            sock = AtrSocket(s, lambda p, d: None, url=url_of(srv), on_taken=on_taken)
            await sock.start()
            await until(lambda: len(fast) >= 2)
            assert not sock.up
            await sock.stop()
        assert s.lost.startswith("1 logins on this user in the last hour")
        assert taken == ["logged in elsewhere"]
        assert len(t4.logins()) == 1 and s.budget.slots == 1
        assert t4.opens == 1                                    # no websocket opened while the budget says wait
    asyncio.run(go())
    assert set(fast) == {15}                                    # waits in 15 s steps


@pytest.mark.parametrize("result,lost", [
    (proto.LOGIN_FAILED, "T4 login failed: bad password"),
    (proto.UNAUTHORIZED, "T4 login unauthorized: bad password"),
    (proto.LOCKED_OUT, "T4 login locked out: bad password"),
    (proto.TWO_FACTOR_REQUIRED, "AlphaTrader needs a code")])
def test_a_failed_login_stops_without_a_loop(result, lost, fast):
    async def go():
        t4 = T4(answer=lambda n: {"result": result, "errorMessage": "bad password"})
        s = make_session()
        async with t4.serving() as srv:
            sock = AtrSocket(s, lambda p, d: None, url=url_of(srv))
            await sock.start()
            await until(lambda: s.lost is not None)
            await asyncio.sleep(0.2)
            assert sock._task.done() and not sock.up
            await sock.stop()
        assert s.lost == lost
        assert len(t4.logins()) == 1 and s.budget.slots == 1
        assert s.budget.results == [f"T4 login result {result}"]        # the failure is reported to the budget
    asyncio.run(go())
    assert fast == []


@pytest.mark.parametrize("err,lost", [(NeedsCode("AlphaTrader needs a code"), "AlphaTrader needs a code"),
                                      (AtrLoginFailed("T4 credentials refused (status 403)"),
                                       "T4 credentials refused (status 403)")])
def test_a_credentials_refusal_stops_without_a_loop(err, lost, fast):
    async def go():
        t4 = T4()
        s = make_session(creds_errors=[err])
        async with t4.serving() as srv:
            sock = AtrSocket(s, lambda p, d: None, url=url_of(srv))
            await sock.start()
            await until(lambda: s.lost is not None)
            await asyncio.sleep(0.1)
            assert sock._task.done()
            await sock.stop()
        assert s.lost == lost and t4.logins() == [] and s.fetches == 1 and s.budget.slots == 0
    asyncio.run(go())
    assert fast == []


def test_drops_back_off_1_2_4_8_then_15(fast, roomy):
    async def script(ws, n):
        await ws.close()

    async def go():
        t4 = T4(script)
        s = make_session(creds_errors=[httpx.ConnectError("no route")])     # a transport error is a drop too
        async with t4.serving() as srv:
            sock = AtrSocket(s, lambda p, d: None, url=url_of(srv))
            await sock.start()
            await until(lambda: len(fast) >= 7)
            await sock.stop()
        assert s.lost is None
    asyncio.run(go())
    assert fast[:7] == [1, 2, 4, 8, 15, 15, 15]


def test_a_failed_credential_fetch_books_no_slot():
    """At the default cap (4 an hour): a transport error on the fetch, then success, is ONE slot -- one real T4 login."""
    async def go():
        t4 = T4()
        s = make_session(creds_errors=[httpx.ConnectError("no route")])
        async with t4.serving() as srv:
            sock = AtrSocket(s, lambda p, d: None, url=url_of(srv))
            await sock.start()
            await until(lambda: sock.up)
            await sock.stop()
        assert s.fetches == 2 and len(t4.logins()) == 1 and s.budget.slots == 1
    asyncio.run(go())


def test_stop_during_a_backoff_pause_returns_at_once(monkeypatch):
    async def go():
        waiting = asyncio.Event()

        async def pause(s):
            waiting.set()
            await asyncio.sleep(30)
        monkeypatch.setattr(alphatrader_ws, "_pause", pause)
        s = make_session(creds_errors=[httpx.ConnectError("no route")])
        t4 = T4()
        async with t4.serving() as srv:
            sock = AtrSocket(s, lambda p, d: None, url=url_of(srv))
            await sock.start()
            await asyncio.wait_for(waiting.wait(), 3)
            await asyncio.wait_for(sock.stop(), 1)
        await asyncio.sleep(0.05)
        assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    asyncio.run(go())


def test_stop_from_inside_on_taken_ends_the_loop():
    async def script(ws, n):
        await ws.send(msg("loginResponse", {"result": proto.LOGGED_IN_ELSEWHERE}))
        await asyncio.sleep(1)

    async def on_taken(why):
        await sock.stop()

    async def go():
        nonlocal sock
        t4 = T4(script)
        async with t4.serving() as srv:
            sock = AtrSocket(make_session(), lambda p, d: None, url=url_of(srv), on_taken=on_taken)
            await sock.start()
            task = sock._task
            await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 2)
            assert task.cancelled() and not sock.up and len(t4.logins()) == 1
    sock = None
    asyncio.run(go())


def test_a_socket_up_past_STABLE_S_starts_the_ladder_over(monkeypatch, fast, roomy):
    monkeypatch.setattr(alphatrader_ws, "STABLE_S", 0.15)

    async def script(ws, n):
        if n in (3, 5):
            await asyncio.sleep(0.3)
        await ws.close()

    async def go():
        t4 = T4(script)
        async with t4.serving() as srv:
            sock = AtrSocket(make_session(), lambda p, d: None, url=url_of(srv))
            await sock.start()
            await until(lambda: len(fast) >= 6)
            await sock.stop()
    asyncio.run(go())
    assert fast[:6] == [1, 2, 1, 2, 1, 2]


def test_sixty_seconds_of_silence_reconnects(monkeypatch, fast):
    monkeypatch.setattr(alphatrader_ws, "SILENT_S", 0.2)

    async def go():
        t4 = T4()                                                # answers the login, then says nothing
        s = make_session()
        async with t4.serving() as srv:
            sock = AtrSocket(s, lambda p, d: None, url=url_of(srv))
            await sock.start()
            await until(lambda: len(t4.logins()) == 2)
            await sock.stop()
        assert s.budget.slots == 2
    asyncio.run(go())
    assert fast[0] == 1


def test_send_when_down_raises_ConnectionError():
    async def go():
        t4 = T4()
        async with t4.serving() as srv:
            sock = AtrSocket(make_session(), lambda p, d: None, url=url_of(srv))
            with pytest.raises(ConnectionError):
                await sock.send("orderPull", {"accountId": "A1"})
            await sock.start()
            await until(lambda: sock.up)
            await sock.send("orderPull", {"accountId": "A1", "marketId": "M1"})
            await until(lambda: ("orderPull", {"accountId": "A1", "marketId": "M1"}) in t4.got[0])
            await sock.stop()
            with pytest.raises(ConnectionError):
                await sock.send("orderPull", {"accountId": "A1"})
    asyncio.run(go())


def test_stop_ends_every_task():
    async def go():
        t4 = T4()
        async with t4.serving() as srv:
            sock = AtrSocket(make_session(), lambda p, d: None, url=url_of(srv))
            await sock.start()
            await until(lambda: sock.up)
            await sock.stop()
        await asyncio.sleep(0.05)
        assert not [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    asyncio.run(go())


def test_no_credential_reaches_the_log(capsys, caplog):
    caplog.set_level(logging.DEBUG)
    caplog.set_level(logging.DEBUG, logger="websockets")

    async def go():
        ok = T4()
        bad = T4(answer=lambda n: {"result": proto.LOGIN_FAILED, "errorMessage": f"bad login {USER} / {PW}"})
        async with ok.serving() as a, bad.serving() as b:
            s = make_session()
            sock = AtrSocket(s, lambda p, d: None, url=url_of(a))
            await sock.start()
            await until(lambda: sock.up)
            await sock.stop()
            s = make_session()
            sock = AtrSocket(s, lambda p, d: None, url=url_of(b))
            await sock.start()
            await until(lambda: s.lost is not None)
            await sock.stop()
            assert USER not in s.lost and PW not in s.lost
    asyncio.run(go())
    out = capsys.readouterr()
    mine = [r for r in caplog.records if not r.name.startswith("websockets.server")]     # not the fake T4's own lines
    text = out.out + out.err + "".join(f"{r.getMessage()} {r.args}" for r in mine)
    assert "logged in" in text
    for secret in (USER, PW):
        assert secret not in text


def test_a_successful_login_answer_reaches_on_event_before_on_up():
    """The adapter picks its account from loginResponse.accounts: the answer is forwarded before on_up runs."""
    seen = []

    async def on_up():
        seen.append(("on_up", None))

    async def go():
        t4 = T4(answer=lambda n: {"sessionId": "S1", "accounts": [{"accountId": "A1", "accountName": "Main"}]})
        async with t4.serving() as srv:
            sock = AtrSocket(make_session(), lambda p, d: seen.append((p, d)), url=url_of(srv), on_up=on_up)
            await sock.start()
            await until(lambda: ("on_up", None) in seen)
            await sock.stop()
    asyncio.run(go())
    assert seen[:2] == [("loginResponse", {"sessionId": "S1", "accounts": [{"accountId": "A1", "accountName": "Main"}]}),
                        ("on_up", None)]
