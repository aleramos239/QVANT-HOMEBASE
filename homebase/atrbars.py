"""Bars built from ticks, and the research's ATR -- for the strategies whose geometry is a new number every day.

The NQ prop strategies (homebase/strategies/prop_nq.py, config kind "levels") size their stops and entry offsets
from ATR(14, Wilder) of N-minute bars, and one of them reads a 5-minute opening range.  The research (the
pp_* drafts) built those from the tester's 1-minute bars, from 00:00 ET of the day, so this module does the same:

  * a minute bar is one ET minute [m, m + 60 s) of prints: open = first, high/low, close = last;
    a minute with no print makes no bar;
  * an N-minute bar is the minute bars of one bucket aligned to ET midnight (a bucket with no print makes
    no bar); a bucket counts as CLOSED once its end <= the event time (the 09:00-09:30 bar is closed at the
    09:30:00 fire -- exactly as the tester delivers it BEFORE the 09:30 event);
  * ATR restarts at 00:00 ET every day: the first true range is high - low, the first 14 bars average
    (so 19 bars at 09:30 for 30-minute bars, 27 at 13:30, 133 5-minute bars at 11:05, the 11:00-11:05 bar included), then Wilder's
    (atr * 13 + tr) / 14.  A chart's ATR (which runs over many days) will differ -- that is expected.

Two ways in, one result:
  add_tick(ts_ms, px, size)   live prints, as the desk's market-data socket delivers them;
  add_minute(start_ms, ...)   a finished 1-minute bar (the tester's on_bar, or the broker's chart history).
A history bar is exact and wins over the same minute built from live prints (a quote push can coalesce
prints; the difference is recorded in `parity`, never silent).  The live feed must not leave a hole:
`coverage()` says whether history + live prints leave no minute unseen up to the event.

Stdlib only; no I/O.
"""
from __future__ import annotations

import datetime as dt
from collections import deque
from typing import Optional
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
MIN_MS = 60_000
ATR_N = 14
WARM_BARS = 3                 # = the research's WARM: no entry before 3 closed bars of the day
HISTORY_REACHES_MIN = 10      # history must start within this many minutes of 00:00 ET
TAIL = 4000                   # prints kept for last_before()
LIVE_GAP_MS = 120_000         # NQ prints many times a second: two minutes of silence on a live feed is a hole


def et_midnight_ms(d: dt.date) -> int:
    return int(dt.datetime.combine(d, dt.time(0), tzinfo=ET).timestamp()) * 1000


def et_ms(d: dt.date, hhmmss: str) -> int:
    """'HH:MM' or 'HH:MM:SS' ET on day d -> unix ms."""
    return int(dt.datetime.combine(d, dt.time.fromisoformat(hhmmss), tzinfo=ET).timestamp()) * 1000


def wilder_atr(highs, lows, closes) -> Optional[float]:
    """ATR(14) the way the research computes it over a day's bars: first TR = high - low, then
    max(h - l, |h - prev close|, |l - prev close|); the mean of the first 14 TRs, then Wilder."""
    atr = None
    trs: list[float] = []
    for i, (h, l) in enumerate(zip(highs, lows)):
        tr = h - l if i == 0 else max(h - l, abs(h - closes[i - 1]), abs(l - closes[i - 1]))
        trs.append(tr)
        n = i + 1
        atr = sum(trs) / n if n <= ATR_N else (atr * (ATR_N - 1) + tr) / ATR_N
    return atr


class TickBars:
    """One ET day's prints, as minute bars, for one contract."""

    def __init__(self, date: dt.date):
        self.date = date
        self.t0 = et_midnight_ms(date)
        self.t1 = et_midnight_ms(date + dt.timedelta(days=1))
        self.minutes: dict[int, list] = {}      # minute start ms -> [o, h, l, c, v]
        self.exact: set[int] = set()            # minutes that came from a finished bar (history / the tester)
        self.hist_start: Optional[int] = None   # first / end of the finished bars handed in
        self.hist_end: Optional[int] = None
        self.live_from: Optional[int] = None    # the moment live prints began to be received
        self.last_tick_ms: Optional[int] = None
        self.ticks = 0
        self.tail: deque = deque(maxlen=TAIL)   # (ts_ms, px) in arrival order
        self.parity: list[dict] = []            # a live minute that history later disagreed with
        self.live_gaps: list[tuple[int, int]] = []   # (last print, next print) more than LIVE_GAP_MS apart

    # ----------------------------------------------------------------- feeding
    def start_live(self, ts_ms: int, reset: bool = False) -> None:
        """Prints are received from `ts_ms` on (call when the subscription is acknowledged).  reset=True:
        the feed was down and came back -- continuity restarts HERE (what it missed is a hole the
        history read has to close)."""
        if reset or self.live_from is None or ts_ms < self.live_from:
            self.live_from = int(ts_ms)

    def add_tick(self, ts_ms: int, px: float, size: float = 0) -> None:
        ts_ms = int(ts_ms)
        if not (self.t0 <= ts_ms < self.t1):
            return
        if self.live_from is None:
            self.live_from = ts_ms
        self.ticks += 1
        if self.last_tick_ms is not None and ts_ms - self.last_tick_ms > LIVE_GAP_MS:
            self.live_gaps.append((self.last_tick_ms, ts_ms))
        self.last_tick_ms = ts_ms if self.last_tick_ms is None else max(self.last_tick_ms, ts_ms)
        self.tail.append((ts_ms, float(px)))
        m = ts_ms - ts_ms % MIN_MS
        if m in self.exact:
            return                                  # a finished bar is exact: prints do not edit it
        b = self.minutes.get(m)
        if b is None:
            self.minutes[m] = [px, px, px, px, size]
            return
        b[1] = max(b[1], px)
        b[2] = min(b[2], px)
        b[3] = px
        b[4] += size

    def add_minute(self, start_ms: int, o: float, h: float, l: float, c: float, v: float = 0) -> None:
        """A FINISHED 1-minute bar.  Replaces whatever live prints built for that minute."""
        start_ms = int(start_ms)
        if start_ms % MIN_MS or not (self.t0 <= start_ms < self.t1):
            return
        old = self.minutes.get(start_ms)
        if old is not None and start_ms not in self.exact \
                and (abs(old[1] - h) > 1e-9 or abs(old[2] - l) > 1e-9 or abs(old[3] - c) > 1e-9):
            self.parity.append({"minute": start_ms, "live": [old[1], old[2], old[3]], "history": [h, l, c]})
        self.minutes[start_ms] = [o, h, l, c, v]
        self.exact.add(start_ms)
        self.hist_start = start_ms if self.hist_start is None else min(self.hist_start, start_ms)
        end = start_ms + MIN_MS
        self.hist_end = end if self.hist_end is None else max(self.hist_end, end)

    # ----------------------------------------------------------------- reading
    def last_print_before(self, ts_ms: int) -> Optional[tuple[int, float]]:
        """(stamp, price) of the last print stamped strictly before ts_ms (the anchor).  Falls back to the
        close of the last finished minute (stamped at its end) when the tail no longer holds one."""
        best = None
        for t, p in self.tail:
            if t < ts_ms and (best is None or t >= best[0]):
                best = (t, p)
        if best is not None:
            return best
        before = [m for m in self.minutes if m + MIN_MS <= ts_ms]
        return (max(before) + MIN_MS - 1, self.minutes[max(before)][3]) if before else None

    def last_before(self, ts_ms: int) -> Optional[float]:
        got = self.last_print_before(ts_ms)
        return None if got is None else got[1]

    def tf_bars(self, tf_min: int, upto_ms: int) -> list[tuple]:
        """Closed tf-minute bars (start_ms, o, h, l, c, v): buckets from ET midnight whose end <= upto_ms."""
        step = tf_min * MIN_MS
        out: dict[int, list] = {}
        for m in sorted(self.minutes):
            b = self.t0 + (m - self.t0) // step * step
            if b + step > upto_ms:
                continue
            o, h, l, c, v = self.minutes[m]
            cur = out.get(b)
            if cur is None:
                out[b] = [o, h, l, c, v]
            else:
                cur[1] = max(cur[1], h)
                cur[2] = min(cur[2], l)
                cur[3] = c
                cur[4] += v
        return [(b, *out[b]) for b in sorted(out)]

    def atr(self, tf_min: int, upto_ms: int) -> tuple[Optional[float], int]:
        """(ATR(14) of the closed tf-minute bars of the day so far, how many bars it ran over)."""
        bars = self.tf_bars(tf_min, upto_ms)
        if not bars:
            return None, 0
        return wilder_atr([b[2] for b in bars], [b[3] for b in bars], [b[4] for b in bars]), len(bars)

    def range(self, a_ms: int, b_ms: int) -> tuple[Optional[float], Optional[float], int]:
        """(high, low, bars) of the 1-minute bars that lie wholly inside [a_ms, b_ms)."""
        xs = [self.minutes[m] for m in self.minutes if a_ms <= m and m + MIN_MS <= b_ms]
        if not xs:
            return None, None, 0
        return max(x[1] for x in xs), min(x[2] for x in xs), len(xs)

    # ----------------------------------------------------------------- trust
    def coverage(self, upto_ms: int) -> tuple[bool, str]:
        """Is every minute of the day up to `upto_ms` accounted for?  Finished bars cover [hist_start,
        hist_end); live prints cover [live_from, ...).  The day's first bars must exist (history reaches
        00:00 ET), and live must begin no later than the first minute history does not cover."""
        if self.hist_start is None:
            return False, "no history bars"
        if self.hist_start > self.t0 + HISTORY_REACHES_MIN * MIN_MS:
            return False, "history does not reach the start of the ET day"
        if self.hist_end >= upto_ms:
            return True, "history covers it"
        if self.live_from is None:
            return False, "no live prints after the history"
        if self.live_from > self.hist_end:
            return False, "a hole between the history and the live prints"
        if self.last_tick_ms is None:
            return False, "no live prints after the history"
        if any(end > self.hist_end for _, end in self.live_gaps):
            return False, "a gap in the live prints that the history does not cover"
        return True, "history + live prints"
