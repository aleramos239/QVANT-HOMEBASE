"""Token renewal never drops the broker socket 09:20-09:35 ET on weekdays (the 9:30 fire);
it renews early, 09:10-09:20, instead. No network: injected clocks, a fake socket, and the
auth's renew/login replaced.

A renewal rolls the token, and a rolled token means the socket is closed and rebuilt by the
supervisor -- on 2026-09-27 that happened at 18:38, 19:48 and 21:51 (every ~70 min), so
nothing kept it away from 09:29:5x."""
from __future__ import annotations

import asyncio
import datetime as dt

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
    ((9, 28, 0), (9, 33, 0), (False, "fire_guard")),      # never inside 09:28-09:31
    ((9, 29, 59), (9, 30, 5), (False, "fire_guard")),
    ((9, 30, 59), (9, 33, 0), (False, "fire_guard")),
    ((9, 31, 0), (9, 33, 0), (True, "expires_in_window")),
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
    def __init__(self):
        self.closed = 0
        self.connected = True

    async def close(self):
        self.closed += 1


def iso(when: dt.datetime) -> str:
    return when.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")


def mkadapter(tmp_path, now, expires, *, refresh_error=None):
    ad = TradovateAdapter("acct", env="demo", keyring_key="k", state_dir=tmp_path)
    ad._ws, ad._connected, ad._now = Sock(), True, (lambda: now)
    ad._auth.tokens = TradovateTokens(access_token="old", expiration_time=iso(expires))
    calls = []

    def refresh():
        calls.append(now)
        if refresh_error:
            raise RuntimeError(refresh_error)
        ad._auth.tokens.access_token = f"new{len(calls)}"
        ad._auth.tokens.expiration_time = iso(now + dt.timedelta(minutes=80))
        return ad._auth.tokens

    ad._auth.refresh = refresh
    return ad, calls


def test_the_old_rule_would_have_dropped_the_socket_at_0927_now_it_holds(tmp_path):
    ad, calls = mkadapter(tmp_path, at(9, 27), at(9, 36, 30))     # 9.5 min left
    assert run(ad._renew_if_needed()) is False
    assert calls == [] and ad._ws.closed == 0 and ad._auth.access_token == "old"


def test_an_early_renewal_at_091959_rolls_the_token_and_drops_the_socket(tmp_path):
    ad, calls = mkadapter(tmp_path, at(9, 19, 59), at(9, 40))
    assert run(ad._renew_if_needed()) is True
    assert len(calls) == 1 and ad._ws.closed == 1 and ad._auth.access_token == "new1"
    # the rebuilt token lives to 10:39:59: nothing more is due until after the window
    ad._now = lambda: at(9, 29, 59)
    assert run(ad._renew_if_needed()) is False and len(calls) == 1


def test_a_token_that_would_expire_in_the_window_is_renewed_at_its_first_check(tmp_path):
    ad, calls = mkadapter(tmp_path, at(9, 20, 3), at(9, 33))
    assert run(ad._renew_if_needed()) is True
    assert ad._ws.closed == 1 and ad._auth.access_token == "new1"


def test_nothing_is_ever_dropped_inside_the_fire_guard(tmp_path):
    for now in (at(9, 28), at(9, 29, 59), at(9, 30), at(9, 30, 59)):
        ad, calls = mkadapter(tmp_path, now, at(9, 30, 30))          # expires inside the guard
        assert run(ad._renew_if_needed()) is False
        assert calls == [] and ad._ws.closed == 0


def test_a_failed_renewal_drops_nothing(tmp_path):
    ad, calls = mkadapter(tmp_path, at(9, 15), at(9, 40), refresh_error="HTTP 502")
    with pytest.raises(RuntimeError, match="502"):
        run(ad._renew_if_needed())
    assert len(calls) == 1 and ad._ws.closed == 0 and ad._auth.access_token == "old"


def test_the_normal_rule_is_unchanged_outside_the_windows(tmp_path):
    ad, calls = mkadapter(tmp_path, at(18, 38), at(18, 47, 59))
    assert run(ad._renew_if_needed()) is True and ad._ws.closed == 1
    ad, calls = mkadapter(tmp_path, at(18, 38), at(18, 48, 1))
    assert run(ad._renew_if_needed()) is False and calls == []


def test_reconnect_renews_a_token_that_would_come_due_in_the_window(tmp_path, monkeypatch):
    """09:10-09:36 the socket is being rebuilt anyway: it gets a token that carries the
    window, so no renewal drop follows it inside the window."""
    monkeypatch.setattr(tradovate, "TradovateWS", SyncWS)
    got = []
    for now, expires, renews in ((at(9, 15), at(9, 45, 59), True),
                                 (at(9, 15), at(9, 46), False),
                                 (at(9, 25), at(9, 44), True),       # would be due at 09:34
                                 (at(12, 0), at(12, 11), False),     # normal rule outside
                                 (at(12, 0), at(12, 9, 59), True)):
        ad = TradovateAdapter("acct", env="demo", keyring_key="k", state_dir=tmp_path,
                              account_selector={"account_name": "APEX"})
        ad._now = lambda now=now: now
        ad._auth.tokens = TradovateTokens(access_token="old", expiration_time=iso(expires))
        seen = []

        def refresh(ad=ad, now=now, seen=seen):
            seen.append(1)
            ad._auth.tokens.access_token = "fresh"
            ad._auth.tokens.expiration_time = iso(now + dt.timedelta(minutes=80))
            return ad._auth.tokens

        ad._auth.refresh = refresh

        async def go(ad=ad):
            await ad.reconnect()
            await ad.close()

        run(go())
        got.append((bool(seen), ad._auth.access_token))
        assert bool(seen) is renews, (now, expires)
    assert got[0] == (True, "fresh") and got[1] == (False, "old")


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
