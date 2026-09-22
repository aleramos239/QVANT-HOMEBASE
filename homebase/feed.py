"""Live bars from the broker's market data, for price-action strategies.

One md socket. For each (root, minutes) watched, a MinuteBar chart
subscription gives `warmup` bars of history and then streams the developing
bar; a push carrying a LATER timestamp closes the previous one. Closed bars
queue up and the server loop drains them into the strategy rules, so no
rule ever runs inside the socket reader.

    feed = MarketFeed(key, env, token_provider=...)
    await feed.connect(); await feed.watch_bars("NQ", 1, warmup=60)
    ...
    for root, minutes, bar in feed.tick(now): rule(feed.bars(root, minutes), ...)
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Optional

from .marketdata import TradovateMD

CLOSE_GRACE_S = 3.0        # a bar with no successor closes this long after its end


@dataclass(frozen=True)
class Bar:
    ts: dt.datetime          # bar START, aware UTC
    o: float
    h: float
    l: float
    c: float
    vol: int
    root: str
    minutes: int

    @property
    def end(self) -> dt.datetime:
        return self.ts + dt.timedelta(minutes=self.minutes)


def _parse_ts(s: str) -> dt.datetime:
    # "2026-09-22T13:58Z" (minute precision) or with seconds
    s = s.replace("Z", "+00:00")
    if len(s) == len("2026-09-22T13:58+00:00"):
        s = s[:16] + ":00" + s[16:]
    return dt.datetime.fromisoformat(s).astimezone(dt.timezone.utc)


class MarketFeed(TradovateMD):
    """TradovateMD (quotes) + live bars."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self._watch: dict[int, tuple[str, int]] = {}        # chart id -> (root, minutes)
        self._hist: dict[tuple[str, int], list[Bar]] = {}   # closed bars, ascending
        self._cur: dict[tuple[str, int], Optional[Bar]] = {}
        self._closed: list[tuple[str, int, Bar]] = []       # closed since last tick()
        self._warming: set[tuple[str, int]] = set()

    async def connect(self) -> None:
        await super().connect()
        self._ws.event_handlers.append(self._on_chart)

    # ----------------------------------------------------------- subscribe
    async def watch_bars(self, root: str, minutes: int, warmup: int = 60) -> str:
        """History warm-up + live updates for one (root, minutes)."""
        import asyncio
        key = (root, minutes)
        if key in self._watch.values():
            return self.resolve(root)
        sym = self.resolve(root)
        self._warming.add(key)
        self._hist.setdefault(key, [])
        self._cur.setdefault(key, None)
        body = {
            "symbol": sym,
            "chartDescription": {"underlyingType": "MinuteBar", "elementSize": minutes,
                                 "elementSizeUnit": "UnderlyingUnits", "withHistogram": False},
            "timeRange": {"asMuchAsElements": warmup + 1}}
        d = await self._ws.request("md/getChart", body)
        if isinstance(d, dict) and d.get("p-ticket"):
            # A rate-limit penalty is a STATE, not a timer: plain requests stay
            # refused until one is resent WITH the ticket after p-time
            # (verified live 2026-09-22 — a plain retry was still refused
            # 90 minutes after the burst; the ticket resend cleared at once).
            await asyncio.sleep(float(d.get("p-time") or 1) + 0.5)
            d = await self._ws.request("md/getChart", {**body, "p-ticket": d["p-ticket"]})
        if not isinstance(d, dict) or d.get("realtimeId") is None:
            self._warming.discard(key)
            raise RuntimeError(f"getChart {sym} {minutes}m: no subscription in {d!r}")
        for cid in {d.get("realtimeId"), d.get("historicalId")}:
            if cid is not None:
                self._watch[int(cid)] = key
        return sym

    def watching(self) -> dict[tuple[str, int], int]:
        return {k: len(v) for k, v in self._hist.items()}

    def bars(self, root: str, minutes: int) -> list[Bar]:
        return list(self._hist.get((root, minutes), []))

    def current(self, root: str, minutes: int) -> Optional[Bar]:
        return self._cur.get((root, minutes))

    # ----------------------------------------------------------- pushes
    def _on_chart(self, msg: dict) -> None:
        if msg.get("e") != "chart":
            return
        for ch in (msg.get("d") or {}).get("charts", []) or []:
            key = self._watch.get(ch.get("id"))
            if key is None:
                continue
            if ch.get("eoh"):
                self._warming.discard(key)
                continue
            root, minutes = key
            for b in sorted(ch.get("bars") or [], key=lambda b: b.get("timestamp", "")):
                try:
                    bar = Bar(ts=_parse_ts(b["timestamp"]), o=float(b["open"]),
                              h=float(b["high"]), l=float(b["low"]), c=float(b["close"]),
                              vol=int(b.get("upVolume", 0) or 0) + int(b.get("downVolume", 0) or 0),
                              root=root, minutes=minutes)
                except (KeyError, TypeError, ValueError):
                    continue
                self._take(key, bar)

    def _take(self, key: tuple[str, int], bar: Bar) -> None:
        cur = self._cur.get(key)
        if cur is None or bar.ts == cur.ts:
            self._cur[key] = bar                     # the developing bar, updated
        elif bar.ts > cur.ts:
            self._close(key, cur)                    # a later bar: the old one is final
            self._cur[key] = bar
        # an older bar than the current one: history out of order — ignore

    def _close(self, key: tuple[str, int], bar: Bar) -> None:
        hist = self._hist.setdefault(key, [])
        if hist and hist[-1].ts >= bar.ts:
            return
        hist.append(bar)
        if len(hist) > 2000:
            del hist[:-2000]
        if key not in self._warming:               # history closes are not events
            self._closed.append((key[0], key[1], bar))

    # ----------------------------------------------------------- the loop
    def tick(self, now: dt.datetime) -> list[tuple[str, int, Bar]]:
        """Newly closed bars since the last call. Also closes a developing
        bar whose end passed with no successor push (a quiet market)."""
        for key, cur in list(self._cur.items()):
            if cur is not None and key not in self._warming and \
                    (now - cur.end).total_seconds() >= CLOSE_GRACE_S:
                self._close(key, cur)
                self._cur[key] = None
        out, self._closed = self._closed, []
        return out

    def status(self) -> dict:
        return {"connected": self.connected,
                "watching": {f"{r}/{m}m": {"bars": len(self._hist.get((r, m), [])),
                                           "last_close": (self._hist[(r, m)][-1].ts.isoformat()
                                                          if self._hist.get((r, m)) else None),
                                           "current": (self._cur[(r, m)].c
                                                       if self._cur.get((r, m)) else None)}
                             for (r, m) in self._hist}}
