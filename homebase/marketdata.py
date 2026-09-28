"""Tradovate market data: live quote + daily bars, for the self-fire timer.

Separate socket from trading (md hosts), authorized with the md_access_token
the login already returns. Reuses the broker's TradovateWS protocol client
and the persisted tokens, so no extra credentials exist anywhere.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import math
import time
from collections import deque
from typing import Optional

from .broker.tradovate_auth import TradovateAuth
from .broker.tradovate_ws import TradovateWS
from .paths import state_dir
from . import symbols
from .secrets_store import get_credentials

MD_DEMO = "wss://md-demo.tradovateapi.com/v1/websocket"
MD_LIVE = "wss://md.tradovateapi.com/v1/websocket"
TRADE_HISTORY = 4096       # trade pushes kept per contract, for last(before=...)

from zoneinfo import ZoneInfo  # noqa: E402

ET = ZoneInfo("America/New_York")


def _stamp(v) -> Optional[float]:
    """A quote push's `timestamp` as unix seconds: an ISO string with a zone
    ("2026-09-14T13:29:59.950Z") or an epoch-ms number. None when it is
    missing, unparseable or has no zone. For the journal only: no live
    morning has shown this field yet, so the anchor never rides on it
    (last() goes by the time a push was RECEIVED)."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v / 1000.0 if math.isfinite(v) else None
    if not isinstance(v, str):
        return None
    s = v.strip()
    if s[-1:] in ("Z", "z"):
        s = s[:-1] + "+00:00"
    try:
        t = dt.datetime.fromisoformat(s)
    except ValueError:
        return None
    return t.timestamp() if t.tzinfo is not None else None


class TradovateMD:
    """Quote stream + daily bars. One instance per session; fails loudly."""

    def __init__(self, keyring_key: str, env: str = "demo",
                 token_provider=None):
        # token_provider: () -> md token from an ALREADY-authenticated adapter.
        # Reusing it avoids a second login (Tradovate rate-limits auth at ~5/h,
        # and 9:20 is the worst possible moment to spend one).
        self.keyring_key = keyring_key
        self.env = env
        self._token_provider = token_provider
        sd = state_dir()
        # own token cache — never race the trading adapter's file
        self._auth = TradovateAuth(
            env=env,
            token_persist_path=sd / "tradovate-md.tokens.json",
            device_persist_path=sd / "tradovate.device.json")
        self._ws: Optional[TradovateWS] = None
        self._trades: dict[str, tuple[float, float]] = {}  # contract -> (price, unix ts)
        # contract -> (unix time RECEIVED, price, the push's raw `timestamp`), oldest first.
        # Not `_hist`: MarketFeed (a subclass) keeps its closed bars under that name.
        self._tape: dict[str, deque] = {}
        self._cid_sym: dict[int, str] = {}                  # contractId -> contract
        self._clock = time.time                             # receive time (tests replace it)

    @property
    def connected(self) -> bool:
        return self._ws is not None and self._ws.connected

    def rides_older_token(self) -> bool:
        """True when this socket was authorized with an md token its login no longer
        hands out (the login renewed since): it dies at the OLD token's expiry. False
        when unknown (no socket, no provider, the provider gives nothing or raises)."""
        if self._ws is None or self._token_provider is None:
            return False
        try:
            current = self._token_provider() or ""
        except Exception:  # noqa: BLE001 — unknown is not "older"
            return False
        return bool(current) and getattr(self._ws, "token", current) != current

    async def connect(self) -> None:
        md_token = ""
        if self._token_provider is not None:
            try:
                md_token = self._token_provider() or ""
            except Exception:  # noqa: BLE001 — fall through to a real login
                md_token = ""
        if not md_token:
            creds = get_credentials(self.keyring_key)
            if not creds or not creds.get("username"):
                raise RuntimeError(f"no credentials for {self.keyring_key!r}")
            await asyncio.to_thread(self._auth.login, creds["username"],
                                    creds["password"])
            md_token = getattr(self._auth.tokens, "md_access_token", "") or \
                self._auth.access_token
        ws = TradovateWS(md_token, self.env)
        ws.url = MD_LIVE if self.env == "live" else MD_DEMO
        await ws.connect()
        await ws.authorize()
        ws.event_handlers.append(self._on_event)
        self._ws = ws

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            finally:
                self._ws = None

    def _on_event(self, msg: dict) -> None:
        if msg.get("e") != "md":
            return
        for q in (msg.get("d") or {}).get("quotes", []) or []:
            tr = (q.get("entries") or {}).get("Trade") or {}
            px = tr.get("price")
            sym = self._cid_sym.get(q.get("contractId"))
            if px is not None and sym:
                px, seen = float(px), self._clock()
                self._trades[sym] = (px, seen)
                tape = self._tape.get(sym)
                if tape is None:
                    tape = self._tape[sym] = deque(maxlen=TRADE_HISTORY)
                tape.append((seen, px, q.get("timestamp")))

    def last(self, sym: str, before: Optional[float] = None) -> tuple[Optional[float], float]:
        """(latest trade price, unix time received) for one subscribed
        contract — never another contract's price.

        With `before` (unix seconds): the latest trade from a push RECEIVED
        strictly before that instant, however late this is asked — by the
        local clock the fire runs on, never the push's own `timestamp` (kept
        for the journal: trade_push). (None, 0.0) when none is kept: nothing
        arrived before it, or TRADE_HISTORY later pushes have already pushed
        it out."""
        if before is None:
            return self._trades.get(sym, (None, 0.0))
        p = self.trade_push(sym, before)
        return (p[1], p[0]) if p is not None else (None, 0.0)

    def trade_push(self, sym: str, before: Optional[float] = None) -> Optional[tuple]:
        """The kept trade push last(sym, before) answers from, for the journal:
        (unix time received, price, the push's raw `timestamp`, that parsed to
        unix seconds or None). None when there is none."""
        for seen, px, raw in reversed(self._tape.get(sym, ())):
            if before is None or seen < before:
                return seen, px, raw, _stamp(raw)
        return None

    @staticmethod
    def resolve(canonical: str) -> str:
        """Canonical root -> tradable front-month contract (NQ -> NQZ6)."""
        return symbols.resolve_contract(canonical)

    async def subscribe_quote(self, canonical: str) -> str:
        sym = self.resolve(canonical)
        d = await self._ws.request("md/subscribeQuote", {"symbol": sym})
        if isinstance(d, dict) and d.get("errorText"):
            raise RuntimeError(f"subscribeQuote {sym}: {d['errorText']}")
        # the reply's subscriptionId is the contractId every quote push carries
        # (verified live 2026-09-21: NQZ6 -> 3267315, YMZ6 -> 4706811)
        cid = d.get("subscriptionId") if isinstance(d, dict) else None
        if cid is None:
            raise RuntimeError(f"subscribeQuote {sym}: no subscriptionId in {d!r}")
        self._cid_sym[int(cid)] = sym
        return sym

    async def unsubscribe_quote(self, sym: str) -> None:
        try:
            await self._ws.request("md/unsubscribeQuote", {"symbol": sym})
        except Exception:  # noqa: BLE001 — best-effort cleanup
            pass

    async def daily_bars(self, canonical: str, n: int = 60,
                         timeout_s: float = 20.0) -> list[dict]:
        """Last `n` COMPLETED daily bars as [{date,h,l,c}] ASC (ET session
        date). Collects the chart push until its end-of-history marker."""
        sym = self.resolve(canonical)
        bars: dict[str, dict] = {}
        done = asyncio.get_event_loop().create_future()

        def on_chart(msg: dict) -> None:
            if msg.get("e") != "chart":
                return
            for ch in (msg.get("d") or {}).get("charts", []) or []:
                if ch.get("eoh") and not done.done():
                    done.set_result(True)
                for b in ch.get("bars", []) or []:
                    ts = b.get("timestamp")
                    if ts is None:
                        continue
                    # session date: shift +6h like the research engine so the
                    # 18:00 ET open lands on the next trading day
                    t = dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                    et = t.astimezone(ET)
                    date = (et + dt.timedelta(hours=6)).date().isoformat()
                    bars[date] = {"date": date, "h": float(b["high"]),
                                  "l": float(b["low"]), "c": float(b["close"])}

        self._ws.event_handlers.append(on_chart)
        try:
            d = await self._ws.request("md/getChart", {
                "symbol": sym,
                "chartDescription": {"underlyingType": "DailyBar",
                                     "elementSize": 1,
                                     "elementSizeUnit": "UnderlyingUnits",
                                     "withHistogram": False},
                "timeRange": {"asMuchAsElements": n + 3}})
            try:
                await asyncio.wait_for(done, timeout_s)
            except asyncio.TimeoutError:
                if not bars:
                    raise RuntimeError("daily bars: no data before timeout")
            rt = (d or {}).get("realtimeId")
            if rt is not None:
                try:
                    await self._ws.request("md/cancelChart", {"subscriptionId": rt})
                except Exception:  # noqa: BLE001
                    pass
        finally:
            self._ws.event_handlers.remove(on_chart)
        return sorted(bars.values(), key=lambda b: b["date"])[-n:]
