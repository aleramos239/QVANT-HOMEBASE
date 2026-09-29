"""Login budget per Tradovate USER (the keyring login key), not per desk entry.

2026-09-29: five desk entries ride one Apex user, each with its own socket and token.
Their reconnects fell back to a full login independently -- 56 logins in a day, a dead
entry (account closed at Apex) every 5 minutes -- until Tradovate answered 429 to
everything on that user, the 09:30 order included, and the holder's own web app said
"You have reached your API request limit".

What this budgets: username/password logins (the supervisor's fallback and retries, the
token refresh's login fallback) and the non-essential reads the desk makes on its own
(equity snapshots). What it never budgets: placing, modifying, cancelling or flattening
orders, and the in-place socket rebuild on the token an entry already holds -- that is
the order path's socket.

Rules, per login key:
  * a 429 (or a p-ticket penalty) from that user starts a cool-down: its p-time when the
    answer carries one, else COOLDOWN_DEFAULT_S. No login and no budgeted read while it
    lasts. One journal line when it starts, one when it ends; a 429 inside it extends it
    quietly.
  * at most MAX_LOGINS_PER_HOUR logins in any rolling hour (Tradovate allows ~5 per user;
    the desk keeps one spare for the holder's own web/app login). An entry's FIRST login
    in this process is exempt from the cap and the backoff (it cannot trade without one),
    never from a cool-down.
  * after a failed login, exponential backoff: BACKOFF_BASE_S doubling to BACKOFF_CAP_S,
    reset by a successful one. A manual Reconnect skips the backoff, not the cap or a
    cool-down.
"""
from __future__ import annotations

import datetime as dt
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

MAX_LOGINS_PER_HOUR = 4
BACKOFF_BASE_S = 300.0
BACKOFF_CAP_S = 1800.0
COOLDOWN_DEFAULT_S = 900.0
COOLDOWN_MAX_S = 3600.0         # a p-time beyond this is clamped, never trusted blindly
_HOUR = 3600.0

_RATE = re.compile(r"(status=|HTTP |['\"]s['\"]:\s*)429\b|p-ticket|too many requests"
                   r"|request limit", re.IGNORECASE)
_P_TIME = re.compile(r"""p-time['"]?\s*[:=]\s*['"]?(\d+(?:\.\d+)?)""")


class LoginDeferred(RuntimeError):
    """A login the user's budget refused for now (429 cool-down, hourly cap, backoff)."""


def is_rate_limited(err) -> bool:
    """A 429 / penalty answer from Tradovate, as the adapters surface it: the WS
    'status=429', the REST 'HTTP 429', an authorize '"s": 429', a p-ticket login."""
    return bool(_RATE.search(str(err or "")))


def penalty_seconds(err) -> Optional[float]:
    """Tradovate's own wait (p-time, seconds) when the answer carries one."""
    m = _P_TIME.search(str(err or ""))
    return float(m.group(1)) if m else None


def _hhmm(ts: float) -> str:
    return dt.datetime.fromtimestamp(ts).strftime("%H:%M:%S")


@dataclass
class _User:
    logins: deque = field(default_factory=deque)   # login timestamps, last hour
    streak: int = 0                                # failed logins in a row
    next_at: float = 0.0                           # backoff: no retry before this
    cool_until: float = 0.0                        # 429 cool-down end (0 = none)


class LoginBudget:
    def __init__(self, clock: Callable[[], float] = None,
                 journal: Optional[Callable[..., None]] = None):
        self._clock = clock or (lambda: time.time())
        self.journal = journal or (lambda event, **kw: None)
        self._users: dict[str, _User] = {}
        self._lock = threading.RLock()     # the refresh's login fallback runs in a thread

    def _u(self, key: str) -> _User:
        u = self._users.get(key)
        if u is None:
            u = self._users[key] = _User()
        return u

    def _expire(self, key: str, u: _User, now: float) -> None:
        if u.cool_until and now >= u.cool_until:
            u.cool_until = 0.0
            self.journal("login_cooldown_ended", login=key)
        while u.logins and now - u.logins[0] >= _HOUR:
            u.logins.popleft()

    def tick(self) -> None:
        """Close cool-downs that have run out (their one 'ended' journal line)."""
        with self._lock:
            now = self._clock()
            for key, u in self._users.items():
                self._expire(key, u, now)

    def cooling(self, key: str) -> float:
        """Seconds left in this user's 429 cool-down (0 = none)."""
        with self._lock:
            now = self._clock()
            u = self._u(key)
            self._expire(key, u, now)
            return max(0.0, u.cool_until - now) if u.cool_until else 0.0

    def note_error(self, key: str, err) -> bool:
        """Feed any error from this user's traffic in; a 429 / penalty starts (or quietly
        extends) the cool-down. Returns True if it was one."""
        if not is_rate_limited(err):
            return False
        with self._lock:
            now = self._clock()
            u = self._u(key)
            self._expire(key, u, now)
            wait = penalty_seconds(err)
            wait = COOLDOWN_DEFAULT_S if wait is None else min(max(wait, 1.0), COOLDOWN_MAX_S)
            until = now + wait
            if not u.cool_until:
                self.journal("login_cooldown_started", login=key, seconds=round(wait),
                             until=_hhmm(until), error=str(err)[:200])
            u.cool_until = max(u.cool_until, until)
            return True

    def blocked(self, key: str, *, first: bool = False, manual: bool = False) -> Optional[str]:
        """Why a login on this user may not happen now (None = it may)."""
        with self._lock:
            now = self._clock()
            u = self._u(key)
            self._expire(key, u, now)
            if u.cool_until:
                return (f"Tradovate rate-limited this login (429) — logins paused until "
                        f"{_hhmm(u.cool_until)}")
            if first:
                return None
            if len(u.logins) >= MAX_LOGINS_PER_HOUR:
                return (f"{len(u.logins)} logins on this user in the last hour — next "
                        f"allowed at {_hhmm(u.logins[0] + _HOUR)}")
            if not manual and now < u.next_at:
                return (f"backing off after {u.streak} failed login(s) — next try at "
                        f"{_hhmm(u.next_at)}")
            return None

    def record_login(self, key: str) -> None:
        with self._lock:
            self._u(key).logins.append(self._clock())

    def login_result(self, key: str, err=None) -> None:
        """A login finished: a failure grows the backoff (and a 429 cools the user down),
        a success resets it."""
        with self._lock:
            u = self._u(key)
            if err is None:
                u.streak, u.next_at = 0, 0.0
                return
            u.streak += 1
            u.next_at = self._clock() + min(BACKOFF_BASE_S * 2 ** (u.streak - 1), BACKOFF_CAP_S)
        self.note_error(key, err)

    def guard(self, key: str) -> "LoginGuard":
        return LoginGuard(self, key)


class LoginGuard:
    """Hook for TradovateAuth.refresh's login fallback (it runs in a worker thread)."""

    def __init__(self, budget: LoginBudget, key: str):
        self.budget, self.key = budget, key

    def allow(self, err) -> bool:
        b = self.budget
        with b._lock:
            b.note_error(self.key, err)
            if b.blocked(self.key) is not None:
                return False
            b.record_login(self.key)
            return True

    def done(self, err=None) -> None:
        self.budget.login_result(self.key, err)
