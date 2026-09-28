"""Token renewal keeps socket drops out of 09:20-09:35 ET on weekdays (the 9:30 fire); it
renews early, 09:10-09:20, instead. No network: injected clocks, a fake socket, the auth's
renew/login replaced, and any real HTTP call fails the test (tests/conftest.py).

A renewal rolls the token, and a rolled token means the socket is closed and rebuilt by the
supervisor -- on 2026-09-27 that happened at 18:38, 19:48 and 21:51 (every ~70 min), so
nothing kept it away from 09:29:5x."""
from __future__ import annotations

import asyncio
import datetime as dt
import threading

import pytest

from homebase.broker import tradovate
from homebase.broker.tradovate import (ET, TradovateAdapter, reconnect_buffer_s,
                                       renewal_due)
from homebase.broker.tradovate_auth import TradovateAuth, TradovateTokens
from tests.test_adapter_caches import SyncWS

MON, SAT = dt.date(2026, 9, 14), dt.date(2026, 9, 19)       # EDT (UTC-4)
WINTER_MON = dt.date(2026, 12, 14)                           # EST (UTC-5)


def run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def at(h, m, s=0, day=MON) -> dt.datetime:
    return dt.datetime(day.year, day.month, day.day, h, m, s, tzinfo=ET)


def ts(h, m, s=0, day=MON) -> float:
    return at(h, m, s, day).timestamp()


# --- the rule (pure) -----------------------------------------------------------------
@pytest.mark.parametrize("now, expires, want", [
    # normal rule outside the windows: < 10 min left
    ((9, 0, 0), (9, 11, 0), (False, "normal")),
    ((9, 0, 0), (9, 9, 59), (True, "normal")),
    ((9, 9, 59), (9, 40, 0), (False, "normal")),          # 30 min left, early zone not open yet
    # early zone 09:10-09:20: renew if due (10 min left) before 09:36 = expires before 09:46
    ((9, 10, 0), (9, 40, 0), (True, "early")),
    ((9, 19, 59), (9, 45, 59), (True, "early")),          # 09:19:59 renew allowed
    ((9, 19, 59), (9, 46, 0), (False, "normal")),         # lasts: nothing due inside the window
    ((9, 15, 0), (10, 35, 0), (False, "normal")),         # a fresh token
    # quiet 09:20-09:35: held even with < 10 min left, if it lives past 09:36
    ((9, 20, 0), (9, 40, 0), (False, "quiet")),
    ((9, 27, 0), (9, 36, 30), (False, "quiet")),          # 9.5 min left: the old rule dropped here
    ((9, 29, 55), (9, 36, 0), (False, "quiet")),
    ((9, 34, 59), (9, 40, 0), (False, "quiet")),          # 5 min left, held to the window's end
    ((9, 35, 0), (9, 40, 0), (True, "normal")),           # window over: renewed at once
    # a token that would EXPIRE before 09:36 is renewed at once, outside the fire guard
    ((9, 20, 0), (9, 33, 0), (True, "expires_in_window")),
    ((9, 20, 0), (9, 35, 59), (True, "expires_in_window")),
    ((9, 27, 59), (9, 33, 0), (True, "expires_in_window")),
    # fire guard 09:28-09:31: a socket whose token lives past 09:31 is never dropped...
    ((9, 28, 0), (9, 33, 0), (False, "fire_guard")),
    ((9, 29, 0), (9, 31, 0), (False, "fire_guard")),
    ((9, 30, 59), (9, 33, 0), (False, "fire_guard")),
    ((9, 31, 0), (9, 33, 0), (True, "expires_in_window")),   # ...and is renewed right after
    # ...one that dies inside it: dropped while a rebuild still fits before the fire...
    ((9, 28, 0), (9, 30, 59), (True, "expires_in_guard")),
    ((9, 29, 44), (9, 30, 40), (True, "expires_in_guard")),
    ((9, 29, 0), (9, 28, 30), (True, "expires_in_guard")),   # already expired
    # ...from 09:29:45 only if it cannot carry the fire's acks (dies before 09:30:05)...
    ((9, 29, 45), (9, 30, 4), (True, "expires_in_guard")),
    ((9, 29, 59), (9, 30, 5), (False, "fire_guard")),
    ((9, 29, 45), (9, 30, 40), (False, "fire_guard")),
    # ...never under the fire's acks, 09:30:00-09:30:30...
    ((9, 30, 0), (9, 30, 2), (False, "fire_acks")),
    ((9, 30, 29), (9, 30, 45), (False, "fire_acks")),
    # ...and at once after them
    ((9, 30, 30), (9, 30, 45), (True, "expires_in_guard")),
])
def test_the_rule_on_a_weekday(now, expires, want):
    assert renewal_due(at(*now), ts(*expires)) == want


def test_an_unknown_expiry_is_never_renewed_inside_the_window():
    assert renewal_due(at(9, 25), 0.0) == (False, "quiet")
    assert renewal_due(at(12, 0), 0.0) == (True, "normal")        # as before, outside it


def test_weekends_have_no_window():
    assert renewal_due(at(9, 25, day=SAT), ts(9, 30, day=SAT)) == (True, "normal")
    assert renewal_due(at(9, 15, day=SAT), ts(9, 40, day=SAT)) == (False, "normal")


def test_the_window_is_eastern_time_in_winter_too():
    # 14:25 UTC is 09:25 EST (it would be 10:25 EDT)
    now = dt.datetime(2026, 12, 14, 14, 25, tzinfo=dt.timezone.utc)
    assert renewal_due(now, ts(9, 34, day=WINTER_MON)) == (True, "expires_in_window")
    assert renewal_due(now, ts(9, 40, day=WINTER_MON)) == (False, "quiet")
    early = dt.datetime(2026, 12, 14, 14, 15, tzinfo=dt.timezone.utc)   # 09:15 EST
    assert renewal_due(early, ts(9, 45, day=WINTER_MON)) == (True, "early")


def test_a_token_renewed_by_the_early_rule_never_comes_due_in_the_window():
    """Whatever time the early check runs, what it leaves (or renews to: 80 min) is never
    due before 09:36 -- so no quiet-window check ever wants a renewal."""
    for early_s in range(0, 600, 29):
        now = at(9, 10) + dt.timedelta(seconds=early_s)
        for exp_min in range(0, 100):
            exp = now.timestamp() + exp_min * 60
            due, _ = renewal_due(now, exp)
            left = now.timestamp() + 80 * 60 if due else exp       # renewed: a fresh 80-min token
            for check in range(20 * 60, 35 * 60, 60):              # every minute 09:20-09:34
                q = at(9, 0) + dt.timedelta(seconds=check)
                assert renewal_due(q, left) == (False, "quiet"), (now, exp_min, q)


@pytest.mark.parametrize("now, want", [
    ((9, 9, 59), 600.0),
    ((9, 10, 0), 26 * 60 + 600.0),        # a rebuilt socket must carry the window: expiry >= 09:46
    ((9, 15, 0), 21 * 60 + 600.0),
    ((9, 30, 0), 6 * 60 + 600.0),
    ((9, 35, 59), 1 + 600.0),
    ((9, 36, 0), 600.0),
])
def test_a_rebuilt_socket_starts_with_a_token_that_carries_the_window(now, want):
    assert reconnect_buffer_s(at(*now)) == pytest.approx(want)
    assert reconnect_buffer_s(at(*now, day=SAT)) == 600.0


# --- the adapter ---------------------------------------------------------------------
class Sock:
    """A socket that remembers the token it was authorized with (as TradovateWS does)."""

    def __init__(self, token="old"):
        self.token, self.closed, self.connected = token, 0, True

    async def close(self):
        self.closed += 1


def iso(when: dt.datetime) -> str:
    return when.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


class Auth:
    """The adapter's real TradovateAuth with renew/login faked: its real refresh() and
    ensure_valid() run on top. `renew_error` makes every renew fail; logins always fail
    (and are counted): a test that logs in says so."""

    def __init__(self, ad, now_fn, expires, renew_error=None):
        self.ad, self.now_fn, self.renew_error = ad, now_fn, renew_error
        self.renews, self.logins = 0, 0
        auth = ad._auth
        auth.tokens = TradovateTokens(access_token="old", expiration_time=iso(expires))
        auth._username, auth._password = "u", "p"
        auth.renew, auth.login = self.renew, self.login

    def renew(self):
        self.renews += 1
        if self.renew_error:
            raise RuntimeError(self.renew_error)
        t = self.ad._auth.tokens
        t.access_token = f"new{self.renews}"
        t.expiration_time = iso(self.now_fn() + dt.timedelta(minutes=80))
        return t

    def login(self, u, p):
        self.logins += 1
        raise RuntimeError("Login failed: p-ticket")


def mkadapter(tmp_path, now, expires, *, renew_error=None):
    """An adapter whose socket rides the auth's token 'old', expiring at `expires`."""
    ad = TradovateAdapter("acct", env="demo", keyring_key="k", state_dir=tmp_path)
    clock = {"now": now}
    ad._ws, ad._connected, ad._now = Sock(), True, (lambda: clock["now"])
    ad._ws_expires = expires.timestamp()          # as _new_socket() records it
    return ad, Auth(ad, ad._now, expires, renew_error), clock


def test_the_old_rule_would_have_dropped_the_socket_at_0927_now_it_holds(tmp_path):
    ad, auth, _ = mkadapter(tmp_path, at(9, 27), at(9, 36, 30))     # 9.5 min left
    assert run(ad._renew_if_needed()) is False
    assert auth.renews == 0 and ad._ws.closed == 0 and ad._auth.access_token == "old"


def test_an_early_renewal_at_091959_rolls_the_token_and_drops_the_socket(tmp_path):
    ad, auth, clock = mkadapter(tmp_path, at(9, 19, 59), at(9, 40))
    assert run(ad._renew_if_needed()) is True
    assert auth.renews == 1 and ad._ws.closed == 1 and ad._auth.access_token == "new1"
    # the rebuilt token lives to 10:39:59: nothing more is due until after the window
    clock["now"] = at(9, 29, 59)
    assert run(ad._renew_if_needed()) is False and auth.renews == 1


def test_an_early_renewal_never_spends_a_login(tmp_path):
    """The token is still valid 09:10-09:20: a failed renew is retried at the next check,
    never turned into a (rate-limited) login."""
    ad, auth, _ = mkadapter(tmp_path, at(9, 15), at(9, 40), renew_error="HTTP 502")
    with pytest.raises(RuntimeError, match="502"):
        run(ad._renew_if_needed())
    assert (auth.renews, auth.logins) == (1, 0)
    assert ad._ws.closed == 0 and ad._auth.access_token == "old"   # a failure drops nothing
    # < 10 min left: the old rule would renew here, login fallback included -- unchanged
    ad, auth, _ = mkadapter(tmp_path, at(9, 15), at(9, 22), renew_error="HTTP 502")
    with pytest.raises(RuntimeError, match="p-ticket"):
        run(ad._renew_if_needed())
    assert (auth.renews, auth.logins) == (1, 1)


def test_a_token_that_would_expire_in_the_window_is_renewed_at_its_first_check(tmp_path):
    ad, auth, _ = mkadapter(tmp_path, at(9, 20, 3), at(9, 33))
    assert run(ad._renew_if_needed()) is True
    assert ad._ws.closed == 1 and ad._auth.access_token == "new1"


def test_a_socket_that_carries_the_fire_guard_is_never_dropped_inside_it(tmp_path):
    for now in (at(9, 28), at(9, 29, 59), at(9, 30), at(9, 30, 59)):
        ad, auth, _ = mkadapter(tmp_path, now, at(9, 33))           # lives past 09:31
        assert run(ad._renew_if_needed()) is False
        assert auth.renews == 0 and ad._ws.closed == 0


def test_a_socket_that_dies_inside_the_fire_guard_is_renewed_at_once(tmp_path):
    ad, auth, _ = mkadapter(tmp_path, at(9, 28), at(9, 29, 59))     # would die before the fire
    assert run(ad._renew_if_needed()) is True
    assert ad._ws.closed == 1 and ad._auth.access_token == "new1"


def test_a_late_answer_inside_the_guard_keeps_a_socket_that_carries_it(tmp_path):
    """Decided at 09:27:59 (outside the guard), answered at 09:28:00.4 (a slow renewal):
    the old token lives past 09:31, so the socket is NOT dropped inside the guard -- it
    stays on that still valid token."""
    ad, auth, clock = mkadapter(tmp_path, at(9, 27, 59), at(9, 33))
    fast = auth.renew

    def slow():
        clock["now"] = at(9, 28) + dt.timedelta(milliseconds=400)
        return fast()

    ad._auth.renew = slow
    assert run(ad._renew_if_needed()) is False
    assert ad._auth.access_token == "new1" and ad._ws.closed == 0


def test_a_late_answer_inside_the_guard_drops_a_socket_that_dies_in_it(tmp_path):
    """Same, but the old token dies at 09:29:59: keeping it would lose the fire -- the
    socket is dropped at once and rebuilt on the new token well before 09:30."""
    ad, auth, clock = mkadapter(tmp_path, at(9, 27, 59), at(9, 29, 59))
    fast = auth.renew

    def slow():
        clock["now"] = at(9, 28) + dt.timedelta(milliseconds=200)
        return fast()

    ad._auth.renew = slow
    assert run(ad._renew_if_needed()) is True
    assert ad._ws.closed == 1


def test_a_late_answer_under_the_fires_acks_never_drops_the_socket(tmp_path):
    """Due at 09:29:44 (dies at 09:30:40, a rebuild still fits), but the answer lands at
    09:30:00.1 -- the fire's orders may be in flight: the socket is kept, and dropped by the
    first check after the acks (09:30:30) without renewing again."""
    ad, auth, clock = mkadapter(tmp_path, at(9, 29, 44), at(9, 30, 40))
    fast = auth.renew

    def slow():
        clock["now"] = at(9, 30) + dt.timedelta(milliseconds=100)
        return fast()

    ad._auth.renew = slow
    assert run(ad._renew_if_needed()) is False
    assert ad._ws.closed == 0 and ad._auth.access_token == "new1"
    clock["now"] = at(9, 30, 15)
    assert run(ad._renew_if_needed()) is False and ad._ws.closed == 0     # still under the acks
    clock["now"] = at(9, 30, 30)
    assert run(ad._renew_if_needed()) is True
    assert ad._ws.closed == 1 and auth.renews == 1                         # no second renewal


def test_a_kept_socket_is_dropped_at_0931_by_its_own_tokens_expiry(tmp_path):
    """A late answer kept the socket on 'old' (dies 09:33); the auth already holds 'new1'.
    The keepalive judges the SOCKET's token: held through the guard, dropped at 09:31."""
    ad, auth, clock = mkadapter(tmp_path, at(9, 27, 59), at(9, 33))
    fast = auth.renew

    def slow():
        clock["now"] = at(9, 28) + dt.timedelta(milliseconds=400)
        return fast()

    ad._auth.renew = slow
    assert run(ad._renew_if_needed()) is False and ad._ws.closed == 0
    clock["now"] = at(9, 30, 59)
    assert run(ad._renew_if_needed()) is False and ad._ws.closed == 0
    clock["now"] = at(9, 31)
    assert run(ad._renew_if_needed()) is True
    assert ad._ws.closed == 1 and auth.renews == 1


def test_a_socket_left_on_an_older_token_follows_its_own_expiry(tmp_path):
    """A renewal the socket never saw (a reconnect's renewal that answered after its 5 s
    cap): the socket rides 'old' (dies 09:30:20), the auth holds 'new'. Judged by the
    auth's token nothing would ever drop it; judged by its own it is dropped at the next
    check the rule allows, with no renewal."""
    ad, auth, clock = mkadapter(tmp_path, at(9, 15, 10), at(9, 30, 20))
    ad._auth.tokens = TradovateTokens(access_token="new", expiration_time=iso(at(10, 34, 41)))
    assert run(ad._renew_if_needed()) is True
    assert ad._ws.closed == 1 and auth.renews == 0
    # one that carries the window is held through it, then dropped when due
    ad, auth, clock = mkadapter(tmp_path, at(9, 25), at(9, 40))
    ad._auth.tokens = TradovateTokens(access_token="new", expiration_time=iso(at(10, 45)))
    assert run(ad._renew_if_needed()) is False and ad._ws.closed == 0
    clock["now"] = at(9, 35)
    assert run(ad._renew_if_needed()) is True
    assert ad._ws.closed == 1 and auth.renews == 0


def test_a_renewal_that_raced_a_rebuild_drops_the_rebuild_only_if_it_rides_the_old_token(tmp_path):
    # 'new2': the rebuild's own renewal produced another fresh token -- healthy, left alone
    for rebuilt_on, dropped in (("old", True), ("new1", False), ("new2", False), (None, False)):
        ad, auth, _ = mkadapter(tmp_path, at(18, 38), at(18, 45))
        first = ad._ws
        fast = auth.renew

        def renew_while_rebuilt(rebuilt_on=rebuilt_on):
            ad._ws = Sock(rebuilt_on)          # the supervisor rebuilt it meanwhile
            return fast()

        ad._auth.renew = renew_while_rebuilt
        assert run(ad._renew_if_needed()) is dropped, rebuilt_on
        assert ad._ws.closed == int(dropped) and first.closed == 0


def test_a_healthy_rebuild_on_another_fresh_token_survives_a_late_answer_before_the_fire(tmp_path):
    """Due at 09:29:20 (the token dies 09:29:30); the socket dies, the supervisor rebuilds
    at ~09:29:33 on 'new2' (its own renew/login); the keepalive's slow renewal answers at
    09:29:50 with 'new1'. The rebuild is healthy and must survive: no rebuild would fit
    before 09:30:00 again."""
    ad, auth, clock = mkadapter(tmp_path, at(9, 29, 20), at(9, 29, 30))
    fast = auth.renew

    def slow():
        ad._ws = Sock("new2")
        ad._ws_expires = at(10, 49, 33).timestamp()
        clock["now"] = at(9, 29, 50)
        return fast()

    ad._auth.renew = slow
    assert run(ad._renew_if_needed()) is False
    assert ad._ws.token == "new2" and ad._ws.closed == 0
    # from then on it is judged on its own token: never due in the window
    clock["now"] = at(9, 30, 10)
    assert run(ad._renew_if_needed()) is False and ad._ws.closed == 0


def test_the_normal_rule_is_unchanged_outside_the_windows(tmp_path):
    ad, auth, _ = mkadapter(tmp_path, at(18, 38), at(18, 47, 59))
    assert run(ad._renew_if_needed()) is True and ad._ws.closed == 1
    ad, auth, _ = mkadapter(tmp_path, at(18, 38), at(18, 48, 1))
    assert run(ad._renew_if_needed()) is False and auth.renews == 0
    # a failed renewal falls back to a login there, as it always did
    ad, auth, _ = mkadapter(tmp_path, at(18, 38), at(18, 45), renew_error="HTTP 502")
    with pytest.raises(RuntimeError, match="p-ticket"):
        run(ad._renew_if_needed())
    assert (auth.renews, auth.logins, ad._ws.closed) == (1, 1, 0)


# --- reconnect: a rebuilt socket starts on a token that carries the window, best effort ----
def reconnect_at(tmp_path, monkeypatch, now, expires, *, renew_error=None, renew=None):
    monkeypatch.setattr(tradovate, "TradovateWS", SyncWS)
    ad = TradovateAdapter("acct", env="demo", keyring_key="k", state_dir=tmp_path,
                          account_selector={"account_name": "APEX"})
    ad._now = lambda: now
    auth = Auth(ad, ad._now, expires, renew_error)
    if renew is not None:
        ad._auth.renew = renew

    async def go():
        await ad.reconnect()
        up = ad.connected
        await ad.close()
        return up

    return run(go()), ad, auth


@pytest.mark.parametrize("now, expires, renews", [
    (at(9, 15), at(9, 45, 59), 1),       # would come due in the window: renewed now
    (at(9, 15), at(9, 46), 0),           # carries the window
    (at(9, 25), at(9, 44), 1),           # would be due at 09:34
    (at(9, 29), at(9, 44), 0),           # inside the fire guard: the rebuild never waits
    (at(12, 0), at(12, 11), 0),          # the normal rule outside
    (at(12, 0), at(12, 9, 59), 1),
])
def test_reconnect_renews_a_token_that_would_come_due_in_the_window(tmp_path, monkeypatch,
                                                                   now, expires, renews):
    up, ad, auth = reconnect_at(tmp_path, monkeypatch, now, expires)
    assert up is True and auth.renews == renews and auth.logins == 0
    assert ad._auth.access_token == ("new1" if renews else "old")


@pytest.mark.parametrize("now", [at(9, 28), at(9, 29, 59), at(9, 30, 59)])
def test_a_rebuild_inside_the_fire_guard_never_renews_a_token_that_outlives_it(
        tmp_path, monkeypatch, now):
    """09:34 is < 10 min away: outside the guard the rebuild would renew (else log in),
    unbounded. Inside it the token outlives 09:31:30: rebuilt on it as it is; the
    keepalive renews it after the guard."""
    up, ad, auth = reconnect_at(tmp_path, monkeypatch, now, at(9, 34))
    assert up is True and (auth.renews, auth.logins) == (0, 0)
    assert ad._auth.access_token == "old" and ad._ws_expires == ts(9, 34)


def test_outside_the_guard_the_same_token_is_renewed_as_before(tmp_path, monkeypatch):
    for now in (at(9, 27, 59), at(9, 31)):
        up, ad, auth = reconnect_at(tmp_path, monkeypatch, now, at(9, 34))
        assert up is True and auth.renews == 1 and ad._auth.access_token == "new1"


def test_inside_the_guard_a_token_dying_before_093130_is_renewed_never_logged_in(
        tmp_path, monkeypatch):
    up, ad, auth = reconnect_at(tmp_path, monkeypatch, at(9, 29), at(9, 31, 29))
    assert up is True and (auth.renews, auth.logins) == (1, 0) and ad._auth.access_token == "new1"
    # the renew fails: rebuilt on the current (still valid) token -- no login
    up, ad, auth = reconnect_at(tmp_path, monkeypatch, at(9, 29), at(9, 31, 29),
                                renew_error="HTTP 503")
    assert up is True and (auth.renews, auth.logins) == (1, 0) and ad._auth.access_token == "old"
    # already expired, the renew fails: still no login from the rebuild
    up, ad, auth = reconnect_at(tmp_path, monkeypatch, at(9, 29), at(9, 28),
                                renew_error="HTTP 401")
    assert (auth.renews, auth.logins) == (1, 0)


def test_inside_the_guard_a_slow_renewal_is_capped(tmp_path, monkeypatch):
    monkeypatch.setattr(tradovate, "GUARD_RENEW_S", 0.05)
    release = threading.Event()

    def hangs():
        release.wait(5)
        raise RuntimeError("late")

    try:
        up, ad, auth = reconnect_at(tmp_path, monkeypatch, at(9, 29, 50), at(9, 30, 40),
                                    renew=hangs)
    finally:
        release.set()
    assert up is True and ad._auth.access_token == "old" and auth.logins == 0


def test_a_failed_best_effort_renewal_still_rebuilds_on_the_current_token(tmp_path, monkeypatch):
    """09:25, a token good to 09:44: the renew fails -- the socket is rebuilt on the valid
    token anyway, with no login spent (the old 10-minute rule's behaviour)."""
    up, ad, auth = reconnect_at(tmp_path, monkeypatch, at(9, 25), at(9, 44),
                                renew_error="HTTP 503")
    assert up is True and (auth.renews, auth.logins) == (1, 0)
    assert ad._auth.access_token == "old"


def test_a_slow_best_effort_renewal_never_holds_the_rebuild(tmp_path, monkeypatch):
    monkeypatch.setattr(tradovate, "RECONNECT_RENEW_S", 0.05)
    release = threading.Event()

    def hangs():
        release.wait(5)
        raise RuntimeError("late")

    try:
        up, ad, auth = reconnect_at(tmp_path, monkeypatch, at(9, 25), at(9, 44), renew=hangs)
    finally:
        release.set()
    assert up is True and ad._auth.access_token == "old" and auth.logins == 0


class TokWS(SyncWS):
    """SyncWS that remembers the token it was built on, as TradovateWS does."""

    def __init__(self, token=None, environment="demo"):
        super().__init__(token, environment)
        self.token = token


def test_a_renewal_answering_after_its_cap_leaves_a_socket_the_keepalive_still_drops(
        tmp_path, monkeypatch):
    """09:14:33 rebuild; the best-effort renew answers after RECONNECT_RENEW_S and SUCCEEDS:
    the socket rides 'old' (dies 09:30:20, under the fire's acks) while the auth holds the
    new token. The socket's own expiry was recorded at build, so the next keepalive check
    drops it (early rule) with no second renewal."""
    monkeypatch.setattr(tradovate, "TradovateWS", TokWS)
    monkeypatch.setattr(tradovate, "RECONNECT_RENEW_S", 0.05)
    clock = {"now": at(9, 14, 33)}
    ad = TradovateAdapter("acct", env="demo", keyring_key="k", state_dir=tmp_path,
                          account_selector={"account_name": "APEX"})
    ad._now = lambda: clock["now"]
    auth = Auth(ad, ad._now, at(9, 30, 20))
    gate, done = threading.Event(), threading.Event()
    fast = auth.renew

    def late():
        gate.wait(5)
        try:
            return fast()
        finally:
            done.set()

    ad._auth.renew = late

    async def go():
        await ad.reconnect()                               # the renewal hit its cap
        sock, expires = ad._ws, ad._ws_expires
        gate.set()
        await asyncio.to_thread(done.wait, 5)              # ...then rolled the token anyway
        clock["now"] = at(9, 15, 10)
        dropped = await ad._renew_if_needed()
        await ad.close()
        return sock, expires, dropped

    sock, expires, dropped = run(go())
    assert sock.token == "old" and expires == ts(9, 30, 20) and ad._auth.access_token == "new1"
    assert dropped is True and auth.renews == 1                # no second renewal


def test_a_token_too_close_to_expiry_is_still_renewed_as_before(tmp_path, monkeypatch):
    """< 10 min left: the normal rule (renew, else log in) runs as it always did, and a
    reconnect whose renew and login both fail still fails."""
    with pytest.raises(RuntimeError, match="p-ticket"):
        reconnect_at(tmp_path, monkeypatch, at(9, 25), at(9, 34), renew_error="HTTP 503")


# --- the suite's broker guard (tests/conftest.py) can't be swallowed --------------------
def test_a_real_renewal_inside_a_best_effort_path_fails_the_test(tmp_path, monkeypatch):
    """_renew_before_the_window catches Exception (a failed renewal must never fail the
    rebuild): the guard raises pytest's Failed, a BaseException, so a test that reached
    the real renew endpoint through it still fails."""
    monkeypatch.setattr(tradovate, "TradovateWS", SyncWS)
    ad = TradovateAdapter("acct", env="demo", keyring_key="k", state_dir=tmp_path,
                          account_selector={"account_name": "APEX"})
    ad._now = lambda: at(9, 25)
    ad._auth.tokens = TradovateTokens(access_token="old", expiration_time=iso(at(9, 44)))
    with pytest.raises(pytest.fail.Exception, match="real Tradovate HTTP"):
        run(ad.reconnect())                                # the REAL renew(): refused


def test_a_real_broker_websocket_fails_the_test():
    from homebase.broker.tradovate_ws import TradovateWS
    with pytest.raises(pytest.fail.Exception, match="real broker websocket"):
        run(TradovateWS(token="t").connect())


# --- the auth: ensure_valid / refresh, no network --------------------------------------
def test_ensure_valid_reads_the_given_clock_and_refresh_falls_back_to_a_login(tmp_path):
    auth = TradovateAuth(env="demo", token_persist_path=tmp_path / "t.json",
                         device_persist_path=tmp_path / "d.json")
    auth.tokens = TradovateTokens(access_token="old", expiration_time=iso(at(9, 40)))
    events = []

    def renew():
        events.append("renew")
        raise RuntimeError("Renew failed: expired")

    def login(u, p):
        events.append(("login", u))
        auth.tokens = TradovateTokens(access_token="relogged", expiration_time=iso(at(11, 0)))
        return auth.tokens

    auth.renew, auth.login = renew, login
    assert auth.ensure_valid(600, ts(9, 29)).access_token == "old"          # 11 min left
    assert events == []
    with pytest.raises(RuntimeError, match="expired"):                       # no credentials kept
        auth.ensure_valid(600, ts(9, 31))
    auth._username, auth._password = "u", "p"
    assert auth.ensure_valid(600, ts(9, 31)).access_token == "relogged"
    assert events == ["renew", "renew", ("login", "u")]
