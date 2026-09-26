"""Replay an archived session through the live path — for testing now and
on weekends. Rows go in raw (with quotes), exactly as the broker feed would
deliver them, so the classifier -> bars -> studies -> websocket path is the
live one. Never records. Time is the replay clock.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import time

from .session import ET, et_wall_s
from .store import TickStore, read_table


class ReplayFeed:
    def __init__(self, store: TickStore, roots, date: dt.date, on_ticks, speed: float = 10.0,
                 start_et: dt.time = dt.time(9, 25), sleep=asyncio.sleep, wall=time.monotonic):
        self.store, self.date = store, date
        self.roots = [r.upper() for r in roots]
        self.on_ticks, self.speed = on_ticks, float(speed)
        self._sleep, self._wall = sleep, wall
        day = date - dt.timedelta(days=1) if start_et >= dt.time(18, 0) else date
        self.start_ms = int(dt.datetime.combine(day, start_et, ET).timestamp() * 1000)
        self.rows: dict[str, list[dict]] = {}
        self.contracts: dict[str, str] = {}
        self.last_tick: dict[str, float] = {}
        self._w0: float | None = None
        self._stop = False
        self.done = False

    def load(self) -> dict[str, list[dict]]:
        """Read each root's session. Returns the rows BEFORE the start (the
        page's 'session so far'); the rest is kept for run()."""
        before: dict[str, list[dict]] = {}
        for r in self.roots:
            f = self.store.pick(r, self.date)
            if f is None:
                continue
            header, recs = read_table(f.path)
            allrows = [dict(zip(header, rec)) for rec in recs]
            allrows.sort(key=lambda x: (int(x["ts_ms"]), int(x.get("id") or 0)))
            self.contracts[r] = f.contract
            before[r] = [x for x in allrows if int(x["ts_ms"]) < self.start_ms]
            self.rows[r] = [x for x in allrows if int(x["ts_ms"]) >= self.start_ms]
        return before

    def now_ms(self) -> int:
        if self._w0 is None:
            return self.start_ms
        return int(self.start_ms + (self._wall() - self._w0) * 1000 * self.speed)

    async def run(self) -> None:
        self._w0 = self._wall()
        idx = {r: 0 for r in self.rows}
        while not self._stop and any(idx[r] < len(self.rows[r]) for r in self.rows):
            now = self.now_ms()
            for r, rs in self.rows.items():
                i = j = idx[r]
                while j < len(rs) and int(rs[j]["ts_ms"]) <= now:
                    j += 1
                if j > i:
                    self.on_ticks(r, self.contracts[r], rs[i:j])
                    idx[r] = j
                    self.last_tick[r] = self._wall()
            await self._sleep(0.05)
        self.done = True

    def stop(self) -> None:
        self._stop = True

    def budget_used(self) -> int:
        return 0

    def status(self) -> dict:
        w = self._wall()
        return {"mode": "replay", "date": self.date.isoformat(), "speed": self.speed,
                "clock_s": et_wall_s(self.now_ms()), "connected": True, "error": None,
                "reconnects": 0, "budget_hour": 0, "done": self.done,
                "roots": {r: {"contract": self.contracts.get(r),
                              "last_tick_age_s": (round(w - self.last_tick[r], 1)
                                                  if r in self.last_tick else None)}
                          for r in self.roots}}
