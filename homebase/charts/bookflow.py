"""Level 2 book tracker for the charts: one resting order level's life, and a once-a-second sample of the book.

Pure and deterministic: no clock, no I/O. Input is the same stream in every place it runs (the live feed's
recorded lines, the recorded depth files replayed, a test): `on_book(ts_ms, bids, offers)` for each recorded
book line (top 10 levels each side, best first) and `on_print(ts_ms, price, size, side)` for each trade
(side +1 = the buyer lifted the ask, -1 = the seller hit the bid). Feed them in time order, a book before a
print that carries the same stamp.

Output is a list of plain dicts (JSON-ready), from every call:
  {"k": "sample", "t": ms, "row": [t, b10, a10, imb1, imb5, imb10, micro, spread_ticks]}   once per second
  {"k": "ep", ...episode...}   an order level's life: when it is first worth showing (>= TUNING["min_episode_ms"] old),
                               when it is flagged as absorbing, and when it ends
An episode is "big" when its level shows >= OPEN_RATIO x the median level size of the last MEDIAN_WINDOW_S
seconds of books (both sides pooled, top 10 each), and stays one until it falls under CLOSE_RATIO x.
A side with no levels at all on a book line (an empty or one-sided snapshot) says nothing about that side's
open episodes: they are left as they were. A missing level on a non-empty side reads as size 0.

Every number that decides a verdict is in TUNING: first-guess definitions the owner reviews on real days.
"""
from __future__ import annotations

from collections import deque

LEVELS = 10
OPEN_RATIO = 3.0
CLOSE_RATIO = 2.0
MEDIAN_WINDOW_S = 60
MIN_MEDIAN_SAMPLES = 10          # no episode opens before this many seconds of books
SAMPLE_MS = 1000
BUY, SELL = 1, -1

TUNING = {
    "min_episode_ms": 3000,        # an order level younger than this when it ends is noise, never emitted
    "pull_frac": 0.80,             # pulled: the size fell by >= this fraction ...
    "pull_ms": 2000,               # ... within this long ...
    "pull_traded_frac": 0.20,      # ... while prints at the level were < this fraction of what was removed ...
    "pull_ticks": 4,               # ... and the touch was within this many ticks of the level
    "traded_frac": 0.60,           # traded: prints at the level reached >= this fraction of the peak size
    "abs_mult": 2.0,               # absorbing: traded >= this x the size shown when it opened ...
    "abs_median_mult": 8.0,        # ... and >= this x the median level size ...
    "abs_min_ratio": 4.0,          # ... and the level was at least this x the median to begin with ...
    "abs_hold_frac": 0.50,         # ... and the level still shows >= this fraction of that size ...
    "abs_through_ticks": 1,        # ... and price never printed beyond it by more than this many ticks
}


def _sum(rows, n) -> float:
    return float(sum(r[1] for r in rows[:n]))


def _imb(bids, offers, n) -> float:
    b, a = _sum(bids, n), _sum(offers, n)
    return round((b - a) / (b + a), 4) if b + a > 0 else 0.0


def _median(xs: list) -> float:
    if not xs:
        return 0.0
    s = sorted(xs)
    m = len(s) // 2
    return float(s[m]) if len(s) % 2 else (s[m - 1] + s[m]) / 2.0


class _Ep:
    __slots__ = ("side", "px", "idx", "t0", "start", "size", "peak", "ratio", "traded", "beyond", "dist0",
                 "dist", "sizes", "prints", "abs_t", "sent", "t1", "end")

    def __init__(self, side, px, idx, t0, size, ratio, dist):
        self.side, self.px, self.idx, self.t0 = side, px, idx, t0
        self.start = self.size = self.peak = size
        self.ratio = ratio
        self.traded = 0
        self.beyond = 0
        self.dist0 = self.dist = dist
        self.sizes = deque([(t0, size)])      # (ts, size) of the last pull window
        self.prints = deque()                 # (ts, size) traded at the level within the last pull window
        self.abs_t = None
        self.sent = False
        self.t1 = None
        self.end = "open"

    @property
    def id(self) -> str:
        return f"{self.side}{self.idx}_{self.t0}"

    def wire(self) -> dict:
        """The event a consumer merges by `id`. "pk" is the peak size; "r" is the PEAK ratio to the trailing median
        over the episode's life (not the ratio when it opened); "d0" is the ticks from the touch when it opened."""
        return {"k": "ep", "id": self.id, "s": self.side, "p": self.px, "t0": self.t0, "t1": self.t1,
                "pk": self.peak, "r": round(self.ratio, 2), "tr": self.traded, "end": self.end,
                "ab": self.abs_t, "d0": self.dist0}


class BookTracker:
    def __init__(self, tick_size: float, tuning: dict | None = None):
        self.tick = float(tick_size)
        self.tune = {**TUNING, **(tuning or {})}
        self._sec = None              # the second (ms) of the pending sample
        self._last = None             # the last (bids, offers) of that second
        self._win: deque = deque()    # (second, [sizes]) of committed samples
        self._med = 0.0
        self._eps: dict = {}          # (side, tick index) -> _Ep
        self._ts = None               # the newest stamp seen

    # ---- the stream

    def on_book(self, ts: int, bids: list, offers: list) -> list:
        bids, offers = [list(r) for r in bids[:LEVELS]], [list(r) for r in offers[:LEVELS]]
        out = self._roll(ts)
        self._sec, self._last, self._ts = ts - ts % SAMPLE_MS, (bids, offers), ts
        out += self._update(ts, bids, offers)
        return out

    def on_print(self, ts: int, price: float, size: int, side: int) -> list:
        out = self._roll(ts)
        self._ts = ts if self._ts is None else max(self._ts, ts)
        i = self._idx(price)
        for (s, k), ep in list(self._eps.items()):
            if k == i and ((s == "b" and side == SELL) or (s == "a" and side == BUY)):
                ep.traded += size
                ep.prints.append((ts, size))
            elif (s == "b" and side == SELL and i < k) or (s == "a" and side == BUY and i > k):
                ep.beyond = max(ep.beyond, abs(i - k))
            else:
                continue
            out += self._after(ep, ts)
        return out

    def flush(self, ts: int) -> list:
        """Commit the samples of every second that ended before ts (the live loop calls it once a second)."""
        return self._roll(ts)

    def finish(self, ts: int | None = None) -> list:
        """The recording ended (a finished day): commit the pending sample and end every open level as faded."""
        out = self._roll((self._sec or 0) + SAMPLE_MS) if self._sec is not None else []
        t = self._ts if ts is None else ts
        for key, ep in list(self._eps.items()):
            out += self._close(ep, t, "faded")
            del self._eps[key]
        return out

    # ---- the samples

    def _idx(self, px: float) -> int:
        return round(px / self.tick)

    def _roll(self, ts: int) -> list:
        if self._sec is None or ts < self._sec + SAMPLE_MS:
            return []
        bids, offers = self._last
        sec = self._sec
        self._sec = self._last = None
        micro = None
        crossed = bool(bids and offers and bids[0][0] >= offers[0][0])
        if bids and offers and not crossed:
            bs, as_ = bids[0][1], offers[0][1]
            if bs + as_ > 0:
                micro = round((bids[0][0] * as_ + offers[0][0] * bs) / (bs + as_), 6)
        spread = round((offers[0][0] - bids[0][0]) / self.tick) if bids and offers and not crossed else None
        row = [sec, _sum(bids, LEVELS), _sum(offers, LEVELS), _imb(bids, offers, 1), _imb(bids, offers, 5),
               _imb(bids, offers, LEVELS), micro, spread]
        self._win.append((sec, [r[1] for r in bids] + [r[1] for r in offers]))
        while self._win and self._win[0][0] <= sec - MEDIAN_WINDOW_S * SAMPLE_MS:
            self._win.popleft()
        self._med = _median([x for _, v in self._win for x in v]) if len(self._win) >= MIN_MEDIAN_SAMPLES else 0.0
        return [{"k": "sample", "t": sec, "row": row}]

    # ---- the order levels

    def _update(self, ts: int, bids: list, offers: list) -> list:
        out, med, tick = [], self._med, self.tick
        present = {}
        for side, rows in (("b", bids), ("a", offers)):
            for px, sz in rows:
                present[(side, self._idx(px))] = (px, sz)
        best_bid = bids[0][0] if bids else None
        best_ask = offers[0][0] if offers else None
        for key, ep in list(self._eps.items()):
            if not (bids if ep.side == "b" else offers):
                continue              # a side with no levels on this line is no information: leave its episodes be
            cur = present.get(key)
            size = cur[1] if cur else 0
            ratio = size / med if med > 0 else 0.0
            if size > 0 and ratio >= CLOSE_RATIO:
                ep.size = size
                if size > ep.peak:
                    ep.peak = size
                ep.ratio = max(ep.ratio, ratio)
                ep.sizes.append((ts, size))
                touch = best_bid if ep.side == "b" else best_ask
                if touch is not None:
                    d = (touch - ep.px) / tick if ep.side == "b" else (ep.px - touch) / tick
                    ep.dist = max(0.0, round(d, 2))
                self._trim(ep, ts)
                out += self._after(ep, ts)
            else:
                ep.size = size
                end = self._classify(ep, ts, size)
                out += self._close(ep, ts, end)
                del self._eps[key]
        if med > 0:
            for key, (px, sz) in present.items():
                if key in self._eps or sz < OPEN_RATIO * med:
                    continue
                side = key[0]
                touch = best_bid if side == "b" else best_ask
                d = 0.0 if touch is None else max(0.0, round(((touch - px) if side == "b" else (px - touch)) / tick, 2))
                ep = self._eps[key] = _Ep(side, px, key[1], ts, sz, sz / med, d)
        return out

    def _trim(self, ep: _Ep, ts: int) -> None:
        cut = ts - self.tune["pull_ms"]
        while len(ep.sizes) > 1 and ep.sizes[0][0] < cut:
            ep.sizes.popleft()
        while ep.prints and ep.prints[0][0] < cut:
            ep.prints.popleft()

    def _classify(self, ep: _Ep, ts: int, size_now: float) -> str:
        t = self.tune
        if ep.traded >= t["traded_frac"] * ep.peak or ep.beyond >= 1:
            return "traded"
        self._trim(ep, ts)
        ref = max(s for _, s in ep.sizes)
        removed = ref - size_now
        recent = sum(s for _, s in ep.prints)
        if (ref > 0 and removed >= t["pull_frac"] * ref and recent < t["pull_traded_frac"] * removed
                and ep.dist <= t["pull_ticks"]):
            return "pulled"
        return "faded"

    def _flag(self, ep: _Ep, ts: int) -> bool:
        """True the first time the level qualifies as absorbing (and never again)."""
        t = self.tune
        if ep.abs_t is not None or ep.beyond > t["abs_through_ticks"]:
            return False
        need = max(t["abs_mult"] * ep.start, t["abs_median_mult"] * self._med)
        if ep.ratio >= t["abs_min_ratio"] and ep.traded >= need and ep.size >= t["abs_hold_frac"] * ep.start:
            ep.abs_t = ts
            return True
        return False

    def _after(self, ep: _Ep, ts: int) -> list:
        """An open level changed: it is sent the first time it is old enough to show, and again when flagged."""
        flagged = self._flag(ep, ts)
        if ts - ep.t0 >= self.tune["min_episode_ms"] and (not ep.sent or flagged):
            ep.sent = True
            return [ep.wire()]
        return []

    def _close(self, ep: _Ep, ts: int, end: str) -> list:
        ep.t1, ep.end = ts, end
        if ts - ep.t0 < self.tune["min_episode_ms"] and not ep.sent:
            return []
        ep.sent = True
        return [ep.wire()]
