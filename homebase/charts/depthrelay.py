"""The Mac's live Level 2 book on the server's charts (the owner, 2026-10-19: "build the relay so the Mac's live book
also shows on the VPS DOM").

Level 2 comes only with the live login's market data, and Tradovate gives that to ONE connection at a time: the Mac's
charts hold it (settings_store.md_only keeps the server on the demo login). So the server takes its book from the Mac:

    Mac charts  /ws (a 1-minute chart of NQ and ES, like any page: its depth follows)
      -> the pusher (python -m homebase.charts.depthrelay, on the Mac: launchd homebase-depthrelay)
      -> ssh -L 127.0.0.1:18852 (launchd homebase-depthtunnel)
      -> the server's charts  /ws/depth-in  ->  RelaySocket  ->  the server's own Depth

The Mac's chart service needs nothing new (no restart). The Mac only sends: nothing on it is reachable from the
server (its chart service can reach the armed Desk). On the
server (HOMEBASE_DEPTH_RELAY_IN=1) RelaySocket stands in for the md socket Depth subscribes on: subscribeDOM always
answers, each book the pusher sends becomes a DOM push, and while no pusher is attached the socket is "disconnected",
so every page's book empties at once (the DOM says Book stale) rather than freezing on an old one.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import sys
import time

from .. import symbols


class RelaySocket:
    """The md socket Depth sees on the server: books from the Mac instead of Tradovate."""

    environment = "relay"

    def __init__(self):
        self.event_handlers: list = []
        self.pushers = 0
        self._ids: dict[str, int] = {}          # root -> the subscriptionId Depth binds its book to

    @property
    def connected(self) -> bool:
        return self.pushers > 0

    async def request(self, path: str, body: dict | None = None) -> dict:
        if path == "md/subscribeDOM":
            root = symbols.parse_tradovate_symbol(str((body or {}).get("symbol", "")))[0]
            return {"subscriptionId": self._ids.setdefault(root, len(self._ids) + 1), "mode": "RealTime"}
        return {}                               # md/unsubscribeDOM: the Mac sends what it sends; Depth drops the rest

    def push(self, msg) -> None:
        """One page book from the Mac ({"type": "depth", root, ts, bids: [[p, s]], offers}) as a Tradovate DOM push.
        A book with no ts (the Mac lost its md socket) goes through empty, so the server's pages empty too."""
        if not isinstance(msg, dict) or msg.get("type") != "depth":
            return
        cid = self._ids.get(str(msg.get("root", "")).upper())
        if cid is None:
            return
        ts = msg.get("ts")

        def side(k):
            if ts is None:
                return []
            return [{"price": lv[0], "size": lv[1]} for lv in msg.get(k) or () if isinstance(lv, list) and len(lv) == 2]
        dom = {"contractId": cid, "timestamp": ts, "bids": side("bids"), "offers": side("offers")}
        for h in list(self.event_handlers):
            h({"e": "md", "d": {"doms": [dom]}})


class RelayFeed:
    """What Depth reads of a feed: its socket and the contracts it trades (none: Depth resolves the front month)."""

    def __init__(self):
        self.ws = RelaySocket()
        self.contracts: dict = {}


# ---------------------------------------------------------------- the pusher (on the Mac)

async def pump(src: str, dst: str, roots, connect=None, on_open=lambda: None) -> None:
    """Forward every book of `roots` from `src` (this Mac's page socket /ws, as a 1-minute chart of each root: the
    page's depth follows its chart) to `dst` (the server's /ws/depth-in), until either closes."""
    if connect is None:
        import websockets
        connect = websockets.connect
    async with connect(src, open_timeout=10, max_size=None) as a, connect(dst, open_timeout=10) as b:
        for r in roots:
            await a.send(json.dumps({"op": "sub", "id": f"relay-{r}", "root": r, "spec": "time:60"}))
        on_open()
        async for raw in a:
            if '"depth"' in raw and json.loads(raw).get("type") == "depth":   # bars, ticks, status: not ours
                await b.send(raw)


def _log(m: str) -> None:
    print(f"[depthrelay] {dt.datetime.now():%m-%d %H:%M:%S} {m}", flush=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Send this Mac's live Level 2 book to the server's charts")
    ap.add_argument("--roots", default="NQ,ES")
    ap.add_argument("--src", default="ws://127.0.0.1:8852/ws", help="this Mac's charts")
    ap.add_argument("--dst", default="ws://127.0.0.1:18852/ws/depth-in", help="the server's charts, through the ssh tunnel")
    a = ap.parse_args(argv)
    roots = [r.strip().upper() for r in a.roots.split(",") if r.strip()]
    last = None

    def opened():
        nonlocal last
        _log(f"forwarding {a.roots} to {a.dst}")
        last = None
    while True:
        try:
            asyncio.run(pump(a.src, a.dst, roots, on_open=opened))
            why = "a socket closed"
        except Exception as e:  # noqa: BLE001 — either end down (the Mac's charts restarting, the tunnel reconnecting)
            why = f"{type(e).__name__}: {e}"
        if why != last:                             # said once per change, not every 5 s
            _log(f"{why} -- retrying every 5 s")
            last = why
        time.sleep(5)


if __name__ == "__main__":
    sys.exit(main())
