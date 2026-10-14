"""_flat -- A FLAT TIME OF ITS OWN (owner 2026-10-12: three sessions on one account, each flat before the next one starts: Asia by 01:55 ET,
London by 09:25 ET, New York by 15:58 ET).

One setting is put on EVERY wrapped family (families/blocks.py WRAPPED), the way the open layer's nine are (families/_flex.py): `FlatMods` is
added to the front of each class's bases at import. Nothing of a hashed file is edited (l2sim, l2ref, blocks, _flex, the family's module), so no
earlier store or lock is marked "written by other code", and the setting is OFF by default: a family without it is trade for trade what it was
(engine/tests/test_flat.py holds that, family by family, against a class without the mixin).

  w_flat   "HH:MM" on the Globex-day clock (18:00-23:59 = the evening before; "" = none). Under hold_to = 'day' the instance's flatten time
           becomes the EARLIER of w_flat and the day's own (15:58 ET, 13:13 on an equity half day). It is the Template's own flatten, moved:
             * at w_flat the open position is closed at market (exit reason 'time') and every working entry is cancelled;
             * in the 5 minutes before it no entry is placed and working entries are cancelled (as before 15:58);
             * nothing is entered at or after it, and a session that would start at or after it does not start.
           It can only move the flatten time EARLIER. Refused when the instance is built: not a clock time, a time at or after 15:58, an
           evening time on an instance that holds no evening session, or a time that leaves no room to enter (within 5 minutes of the
           start of the instance's session, or before it). Refused when a session is RUN: hold_to 'session' (that convention flattens at
           each session end already; a card's check builds a class with the default hold, so this one is held at the run).

THE CONTROL. `RandomFlat` is l2ref.Random (the C1 random-entry control, unchanged) with the same setting, so a control pool of an idea that is
flat at w_flat is flat at w_flat too: random entries with the same exits AND the same flatten time.

HOMEBASE_FLAT=0 in the environment switches the mixin off (the parity test and a store check use it); the setting then does not exist.
"""
from __future__ import annotations

import os

import l2ref
from l2sim import DAY_FLAT, DAY_S, EVE_S, _hms, _sec, clock_sec

KEYS = ("w_flat",)
LEAD = 300                                           # the Template's own no-entry lead before a flatten time, in seconds


def flat_sec(txt: str):
    """A flat time "HH:MM" -> seconds after 00:00 ET of the trade date (negative: the evening before); "" -> None."""
    t = (txt or "").strip()
    if not t:
        return None
    try:
        return clock_sec(t if t.count(":") else f"{t}:00")
    except Exception as e:                           # noqa: BLE001 - one message for every bad shape
        raise ValueError(f"w_flat: a clock time HH:MM on the Globex day (got {txt!r}): {e}") from None


class FlatMods:
    """The flat time of its own (module docstring), in front of a wrapped family class or of the control."""
    DEFAULTS = {"w_flat": ""}
    SCHEMA = {"w_flat": ("str",)}

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self._fl = flat_sec(self.p["w_flat"])
        if self._fl is None:
            return
        txt = self.p["w_flat"]
        if self._fl >= _sec(DAY_FLAT):
            raise ValueError(f"w_flat {txt!r} is not before the day's own flatten time {DAY_FLAT}: it can only move the flat time earlier")
        ids = self.sessions()
        if ids:                                      # (a family whose own session filter left nothing never trades: nothing to hold against)
            a = min(self.S[x][0] for x in ids)
            if self._fl < 0 and a >= 0:
                raise ValueError(f"w_flat {txt!r} is the evening before, and session(s) {ids} hold no evening")
            if self._fl - LEAD <= a:
                raise ValueError(f"w_flat {txt!r} leaves no room to enter: session(s) {ids} start at {_hms(a)[:5]} and no entry is placed in "
                                 f"the last {LEAD // 60} minutes before a flat time")

    def times(self):
        ts = super().times()
        if self._fl is None:
            return ts
        w = self._fl % DAY_S                         # the wall-clock second: on_time turns an evening time back into a negative one
        return sorted(set(ts) | {_hms(w), _hms(w - LEAD)})

    def on_session(self, ctx):
        super().on_session(ctx)
        if self._fl is None:
            return
        if self.flat_s is None:                      # hold_to 'session' has no flatten time to move: a run must not go on as if it had one
            raise ValueError(f"w_flat {self.p['w_flat']!r} needs hold_to 'day': hold_to 'session' is flat at each session end already")
        self.flat_s = min(self.flat_s, self._fl)     # a half day (13:13) stays the earlier one when it is


class RandomFlat(FlatMods, l2ref.Random):
    """The C1 random-entry control (l2ref.Random) that takes `w_flat`: the control of an idea with a flat time of its own."""


def apply() -> int:
    """Put FlatMods in front of every wrapped class that has not got it yet -> how many were changed. Idempotent; a class keeps its module,
    its qualified name and its pickle reference, so a store's fingerprint (class path + inputs) is what it was."""
    if os.environ.get("HOMEBASE_FLAT") == "0":
        return 0
    from . import blocks
    n = 0
    for cls in blocks.WRAPPED.values():
        if FlatMods not in cls.__mro__:
            cls.__bases__ = (FlatMods,) + cls.__bases__
            n += 1
    return n


assert EVE_S == 18 * 3600                            # the evening split the module's words rely on
