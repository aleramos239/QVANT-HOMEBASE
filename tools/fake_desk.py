"""A FAKE desk for browser checks of chart trading: never the real desk, never a broker.

    .venv/bin/python -m tools.fake_desk [--port 8859]

It speaks the desk's /api/trade/* (homebase/desk_api.py + trading.py):
  * the X-Homebase-Key header, with ITS OWN key, written fresh to homebase/.state/fake-desk.key
    (mode 0600) at start; the real desk.key is never read or written;
  * no Origin;
  * GET /state, and the SSE /stream: state first, then account / bot / fill / result, and a
    heartbeat every 15 s;
  * POST order / modify / cancel / cancel-symbol / flatten / reverse, answering
    {"results": {account: {ok, order_id, error[, refused]}}}.
Bodies go through the desk's own parsers (homebase.trading.parse_*), so a malformed body gets
the same 400. Everything lives in memory: nothing is journaled, and no broker code is imported.

Fills:
  * A Market order fills at once at the chart service's quote (body["quotes"][root]): the ask for
    a buy, the bid for a sell, else the last trade.
  * A Limit or Stop order rests until POST /fake/fill.
  * A StopLimit rests (price = its limit, stop_price and trigger = its trigger). It triggers once a
    quote's last trade reaches the trigger, then fills AT THE LIMIT on the first quote where the limit
    is marketable (buy: last <= limit, sell: last >= limit; both may happen on one quote). Quotes come
    from POST /fake/quote and from the quotes block of every action body. /fake/fill fills it at the limit.
  * An entry's sl_price / tp_price become working Stop / Limit exits when it fills. The first
    exit to fill cancels the other (OCO).
  * tif (Day | GTC, default Day) is stored and shown on each order row; exits are GTC, like the real
    OSO brackets. POST /fake/session-end drops every working Day order (nothing else models a session).

Controls (no key; the process binds 127.0.0.1 only):
    POST /fake/enabled {"on": bool}                       chart trading on/off (a state event)
    POST /fake/refuse {"reason": "..." | null}            every action is refused with this sentence
    POST /fake/fill {"account", "order_id", "price"?}     fill a working order
    POST /fake/quote {"root": "NQ", "last": 30901.0, "ts_ms"?}   a last trade: triggers/fills StopLimits
    POST /fake/session-end                                drop every working Day order
    POST /fake/bot {"scenario": "idle|placed|live|done", "anchor": 30900.0}   the NQ 9:30 bot on sim041
    POST /fake/drop                                       end every SSE stream (the chart service reconnects)
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import itertools
import json
import os
import secrets
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from homebase.contracts import point_value, round_to_tick
from homebase.paths import state_dir
from homebase.trading import (Refused, check_prices, parse_cancel, parse_modify, parse_order,
                              parse_symbol_action)

PORT = 8859
FORBIDDEN_PORTS = frozenset({8850, 8852, 8853, 8854})   # the real desk, the chart service, the replays
KEY_FILE = "fake-desk.key"
MAX_ORDER, MAX_POSITION = 10, 20
HEARTBEAT_S = 15.0
MONTH = "Z6"
ACCOUNTS = (("sim041", "SIM0000041", "demo"), ("sim047", "SIM0000047", "demo"),
            ("live099", "FAKELIVE099", "live"))
SCENARIOS = ("idle", "placed", "live", "done")
OFF = "chart trading is off — switch it on on the desk page"


def now_iso(ts_ms: float | int | None = None) -> str:
    """Wall-clock time, or `ts_ms` (epoch milliseconds) when given -- a fill stamped from a quote's own
    `ts_ms`, or an explicit `/fake/fill` `ts_ms`, lands on the REPLAY clock instead of real wall-clock time, so
    it shows up on a replay chart's loaded bars (2026-09-27 review of Task 5-6: fills used to be stamped with
    real time even in --replay, landing outside every loaded bar's range)."""
    d = dt.datetime.now(dt.timezone.utc) if ts_ms is None else dt.datetime.fromtimestamp(ts_ms / 1000, dt.timezone.utc)
    return d.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


class FakeDesk:
    def __init__(self):
        self.enabled = True
        self.refuse: str | None = None
        self.ids = itertools.count(1001)
        self.subs: set[asyncio.Queue] = set()
        self.acct = {aid: {"id": aid, "label": label, "env": env, "realized": 0.0, "pos": {},
                           "orders": {}, "legs": {}, "fills": []}
                     for aid, label, env in ACCOUNTS}
        self.bot: dict = {"date": None, "strategies": {}}
        self.set_bot("idle", 30900.0)
        self.seen: dict[tuple[str, str], dict] = {}   # (action, client_id) -> the {"results": ...} already returned
                                                       # for it (idempotent retries: review item 6, matching
                                                       # the real desk's (action, client_id) dedup contract)

    # ---- views: the desk's own shapes (trading.ChartDesk.account_view / snapshot) ----
    def account_view(self, aid: str) -> dict:
        a = self.acct[aid]
        return {"id": aid, "label": a["label"], "pinned": a["label"], "broker_account": a["label"],
                "env": a["env"], "connected": True, "error": None, "tradable": True,
                "balance": 50_000.0 + a["realized"], "realized_pnl": a["realized"],
                "positions": [{"contract_id": 1, "symbol": sym, "net": p["net"], "avg_price": p["avg"],
                               "root": sym[:-len(MONTH)], "point_value": point_value(sym)}
                              for sym, p in sorted(a["pos"].items()) if p["net"]],
                "orders": [dict(o) for _, o in sorted(a["orders"].items())],
                "fills": list(a["fills"][-50:]),
                "strategies": ["nq930"] if aid == "sim041" else []}

    def snapshot(self) -> dict:
        return {"enabled": self.enabled,
                "limits": {"max_order_qty": MAX_ORDER, "max_position_qty": MAX_POSITION},
                "accounts": [self.account_view(aid) for aid in self.acct], "bot": self.bot}

    def publish(self, event: str, data) -> None:
        for q in list(self.subs):
            q.put_nowait((event, data))

    def changed(self, aid: str) -> None:
        self.publish("account", self.account_view(aid))

    # ---- book-keeping ----
    def fill(self, aid: str, symbol: str, side: str, qty: int, price: float, order_id: str,
             owner: str | None = None, ts_ms: float | int | None = None) -> None:
        a = self.acct[aid]
        p = a["pos"].setdefault(symbol, {"net": 0, "avg": None})
        s = 1 if side == "Buy" else -1
        net0, avg0 = p["net"], p["avg"]
        closing = min(qty, abs(net0)) if net0 and (net0 > 0) != (s > 0) else 0
        if closing:
            a["realized"] += (price - avg0) * (1 if net0 > 0 else -1) * closing * (point_value(symbol) or 0.0)
        net1 = net0 + s * qty
        if net1 == 0:
            avg1 = None
        elif closing == 0:
            avg1 = round(((avg0 or 0.0) * abs(net0) + price * qty) / abs(net1), 6)
        elif closing < abs(net0):
            avg1 = avg0
        else:
            avg1 = price                              # flipped: the rest opens at the fill price
        p.update(net=net1, avg=avg1)
        f = {"id": next(self.ids), "order_id": order_id, "symbol": symbol, "side": side, "qty": qty,
             "price": price, "time": now_iso(ts_ms), "owner": owner}
        a["fills"].append(f)
        self.publish("fill", {"account": aid, "fill": f})

    def rest(self, aid, symbol, side, qty, typ, price, sl=None, tp=None, owner=None,
             trigger=None, tif="Day") -> str:
        oid = str(next(self.ids))
        price = round_to_tick(symbol, price)
        row = {"order_id": oid, "symbol": symbol, "side": side, "type": typ, "qty": qty,
               "price": price if typ in ("Limit", "StopLimit") else None,
               "stop_price": price if typ == "Stop" else None,
               "status": "Working", "owner": owner, "tif": tif}
        if typ == "StopLimit":
            row["stop_price"] = row["trigger"] = round_to_tick(symbol, trigger)
        self.acct[aid]["orders"][oid] = row
        self.acct[aid]["legs"][oid] = {"sl": sl, "tp": tp}
        return oid

    def brackets(self, aid, symbol, side, qty, leg) -> None:
        out = "Sell" if side == "Buy" else "Buy"
        sl = self.rest(aid, symbol, out, qty, "Stop", leg["sl"], tif="GTC") if leg.get("sl") else None
        tp = self.rest(aid, symbol, out, qty, "Limit", leg["tp"], tif="GTC") if leg.get("tp") else None
        if sl and tp:
            legs = self.acct[aid]["legs"]
            legs[sl]["oco"], legs[tp]["oco"] = tp, sl

    def drop_order(self, aid: str, oid: str) -> dict:
        self.acct[aid]["legs"].pop(oid, None)
        return self.acct[aid]["orders"].pop(oid)

    def fill_order(self, aid: str, oid: str, price=None, ts_ms=None) -> None:
        a = self.acct[aid]
        leg = dict(a["legs"].get(oid) or {})
        o = self.drop_order(aid, oid)
        px = float(price) if price is not None else \
            (o["price"] if o["type"] in ("Limit", "StopLimit") else o["stop_price"])
        self.fill(aid, o["symbol"], o["side"], o["qty"], px, oid, ts_ms=ts_ms)
        if leg.get("oco") in a["orders"]:
            self.drop_order(aid, leg["oco"])
        self.brackets(aid, o["symbol"], o["side"], o["qty"], leg)
        self.changed(aid)

    def on_quote(self, root: str, last, ts_ms=None) -> None:
        """A last trade in `root`: trigger StopLimits it reaches, fill (at the limit) those whose limit
        is marketable once triggered."""
        if last is None:
            return
        symbol = root + MONTH
        for aid, a in self.acct.items():
            for oid, o in list(a["orders"].items()):
                if o["type"] != "StopLimit" or o["symbol"] != symbol or oid not in a["orders"]:
                    continue
                buy, leg = o["side"] == "Buy", a["legs"][oid]       # "triggered" lives off the shown row
                if not leg.get("triggered") and (last >= o["trigger"] if buy else last <= o["trigger"]):
                    leg["triggered"] = True
                if leg.get("triggered") and (last <= o["price"] if buy else last >= o["price"]):
                    self.fill_order(aid, oid, ts_ms=ts_ms)

    def session_end(self) -> int:
        n = 0
        for aid, a in self.acct.items():
            day = [oid for oid, o in a["orders"].items() if o.get("tif", "Day") == "Day"]
            for oid in day:
                self.drop_order(aid, oid)
            n += len(day)
            if day:
                self.changed(aid)
        return n

    # ---- actions ----
    def gate(self, aid: str) -> str | None:
        if not self.enabled:
            return OFF
        if aid not in self.acct:
            return f"unknown account {aid!r}"
        return self.refuse

    @staticmethod
    def refused(reason: str) -> dict:
        return {"ok": False, "order_id": None, "error": reason, "refused": True}

    @staticmethod
    def ok(oid=None) -> dict:
        return {"ok": True, "order_id": oid, "error": None}

    def finish(self, action: str, cid: str, results: dict) -> dict:
        out = {"results": results}
        self.seen[(action, cid)] = out   # review item 6: (action, client_id) retried is idempotent
        self.publish("result", {"client_id": cid, "action": action, **out})
        return out

    def order(self, body) -> dict:
        it = parse_order(body)
        if ("order", it.client_id) in self.seen:
            return self.seen[("order", it.client_id)]
        symbol = it.root + MONTH
        q = (body.get("quotes") or {}).get(it.root) or {}
        last, ts_ms = q.get("last"), q.get("ts_ms")
        self.on_quote(it.root, last, ts_ms)
        res = {}
        for aid in it.accounts:
            why, px = self.gate(aid), None
            if why is None and not 1 <= it.qty <= MAX_ORDER:
                why = f"quantity must be 1-{MAX_ORDER}"
            if why is None and it.type == "Stop" and last is not None:
                if it.side == "Buy" and it.price <= last:
                    why = f"a buy stop must be above the last price ({last:,})"
                if it.side == "Sell" and it.price >= last:
                    why = f"a sell stop must be below the last price ({last:,})"
            if why is None and it.type == "StopLimit":
                try:        # the desk's own rule and sentences
                    check_prices(it.side, it.type, it.price, it.sl_price, it.tp_price, symbol,
                                 {"last": float(last)} if last is not None else None,
                                 trigger=it.trigger_price)
                except Refused as e:
                    why = str(e)
            if why is None and it.type == "Market":
                px = q.get("ask" if it.side == "Buy" else "bid") or last
                if px is None:
                    why = f"fake desk: no quote for {it.root} to fill a market order at"
            if why:
                res[aid] = self.refused(why)
                continue
            leg = {"sl": it.sl_price, "tp": it.tp_price}
            if it.type == "Market":
                oid = str(next(self.ids))
                self.fill(aid, symbol, it.side, it.qty, float(px), oid, ts_ms=ts_ms)
                self.brackets(aid, symbol, it.side, it.qty, leg)
            else:
                oid = self.rest(aid, symbol, it.side, it.qty, it.type, it.price, it.sl_price, it.tp_price,
                                trigger=it.trigger_price, tif=it.tif)
            self.changed(aid)
            res[aid] = self.ok(oid)
        return self.finish("order", it.client_id, res)

    def modify(self, body) -> dict:
        cid, aid, oid, price = parse_modify(body)
        if ("modify", cid) in self.seen:
            return self.seen[("modify", cid)]
        why = self.gate(aid)
        o = self.acct[aid]["orders"].get(oid) if why is None else None
        if why is None and o is None:
            why = f"order {oid} is not working on {self.acct[aid]['label']}"
        if why is None and o["type"] == "StopLimit":
            why = "Stop Limit orders can't be moved — cancel and place again"
        if why:
            return self.finish("modify", cid, {aid: self.refused(why)})
        o["price" if o["type"] == "Limit" else "stop_price"] = round_to_tick(o["symbol"], price)
        self.changed(aid)
        return self.finish("modify", cid, {aid: self.ok(oid)})

    def cancel(self, body) -> dict:
        cid, aid, oid = parse_cancel(body)
        if ("cancel", cid) in self.seen:
            return self.seen[("cancel", cid)]
        why = self.gate(aid)
        if why is None and oid not in self.acct[aid]["orders"]:
            why = f"order {oid} is not working on {self.acct[aid]['label']}"
        if why:
            return self.finish("cancel", cid, {aid: self.refused(why)})
        self.drop_order(aid, oid)
        self.changed(aid)
        return self.finish("cancel", cid, {aid: self.ok(oid)})

    def _per_symbol(self, action: str, body, fn) -> dict:
        cid, accounts, root = parse_symbol_action(body)
        if (action, cid) in self.seen:
            return self.seen[(action, cid)]
        q = (body.get("quotes") or {}).get(root) or {}
        self.on_quote(root, q.get("last"), q.get("ts_ms"))
        res = {}
        for aid in accounts:
            why = self.gate(aid)
            if why:
                res[aid] = self.refused(why)
                continue
            fn(aid, root + MONTH, q.get("last"), q.get("ts_ms"))
            self.changed(aid)
            res[aid] = self.ok()
        return self.finish(action, cid, res)

    def _cancel_symbol(self, aid, symbol, last, ts_ms=None) -> None:
        for oid in [k for k, o in self.acct[aid]["orders"].items() if o["symbol"] == symbol and not o["owner"]]:
            self.drop_order(aid, oid)

    def _flatten(self, aid, symbol, last, ts_ms=None) -> int:
        self._cancel_symbol(aid, symbol, last)
        p = self.acct[aid]["pos"].get(symbol)
        net = p["net"] if p else 0
        if net:
            self.fill(aid, symbol, "Sell" if net > 0 else "Buy", abs(net), float(last or p["avg"]),
                      str(next(self.ids)), ts_ms=ts_ms)
        return net

    def _reverse(self, aid, symbol, last, ts_ms=None) -> None:
        net = self._flatten(aid, symbol, last, ts_ms)
        if net:
            px = float(last or self.acct[aid]["fills"][-1]["price"])
            self.fill(aid, symbol, "Buy" if net < 0 else "Sell", abs(net), px, str(next(self.ids)), ts_ms=ts_ms)

    def cancel_symbol(self, body) -> dict:
        return self._per_symbol("cancel-symbol", body, self._cancel_symbol)

    def flatten(self, body) -> dict:
        return self._per_symbol("flatten", body, self._flatten)

    def reverse(self, body) -> dict:
        return self._per_symbol("reverse", body, self._reverse)

    # ---- the NQ 9:30 bot on sim041 (bot view = trading.ChartDesk.bot_view) ----
    def set_bot(self, scenario: str, anchor: float) -> None:
        a = self.acct["sim041"]
        for oid in [k for k, o in a["orders"].items() if o["owner"] == "nq930"]:
            self.drop_order("sim041", oid)
        x = round_to_tick("NQZ6", anchor)
        up, dn = x + 10.0, x - 10.0
        st = {"status": "idle", "qty": 1, "upper": None, "lower": None, "entry_side": None,
              "entry_fill": None, "entry_qty": None, "sl": None, "tp": None, "exit_fill": None,
              "exit_reason": None, "pnl": None, "note": None}
        timer, day = {"stage": "idle", "gate": None, "adx": None, "anchor": None}, "idle"
        if scenario != "idle":
            timer = {"stage": "done", "gate": True, "adx": 23.4, "anchor": x}
            st.update(status="placed", upper=up, lower=dn)
            day = "placed"
        if scenario == "placed":
            self.rest("sim041", "NQZ6", "Buy", 1, "Stop", up, owner="nq930")
            self.rest("sim041", "NQZ6", "Sell", 1, "Stop", dn, owner="nq930")
        if scenario in ("live", "done"):
            st.update(status="live", entry_side="Buy", entry_fill=up, entry_qty=1, sl=up - 5, tp=up + 15)
            day = "live"
            self.fill("sim041", "NQZ6", "Buy", 1, up, str(next(self.ids)), owner="nq930")
        if scenario == "done":
            st.update(status="done", exit_fill=up + 15, exit_reason="tp", pnl=15 * 20 - 4.0)
            day = "done"
            self.fill("sim041", "NQZ6", "Sell", 1, up + 15, str(next(self.ids)), owner="nq930")
        self.bot = {"date": dt.date.today().isoformat(), "strategies": {"nq930": {
            "symbol": "NQ", "kind": "straddle", "enabled": True, "shadow": False,
            "offset_pts": 10.0, "sl_pts": 5.0, "tp_pts": 15.0, "book": {"sim041": 1},
            "timer": timer, "day_status": day, "accounts": {"sim041": st}}}}


async def stream(desk: FakeDesk, heartbeat_s: float = HEARTBEAT_S):
    q: asyncio.Queue = asyncio.Queue()
    desk.subs.add(q)
    try:
        yield sse("state", desk.snapshot())
        while True:
            try:
                event, data = await asyncio.wait_for(q.get(), heartbeat_s)
            except asyncio.TimeoutError:
                yield sse("heartbeat", {"ts": dt.datetime.now().timestamp()})
                continue
            if event is None:
                return
            yield sse(event, data)
    finally:
        desk.subs.discard(q)


def create_fake_desk(key: str, desk: FakeDesk | None = None) -> FastAPI:
    desk = desk or FakeDesk()
    app = FastAPI(title="fake desk (browser checks only)")
    app.state.desk = desk

    def check(request: Request) -> None:
        if request.headers.get("origin") is not None:
            raise HTTPException(403, "browser requests are refused — trade through the chart service")
        if request.headers.get("x-homebase-key", "") != key:
            raise HTTPException(401, "bad or missing X-Homebase-Key")

    @app.get("/api/trade/state")
    async def trade_state(request: Request):
        check(request)
        return desk.snapshot()

    @app.get("/api/trade/stream")
    async def trade_stream(request: Request):
        check(request)
        return StreamingResponse(stream(desk), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    def route(fn):
        async def handler(request: Request):
            check(request)
            try:
                body = await request.json()
            except ValueError:
                raise HTTPException(400, "the body is not JSON") from None
            try:
                return fn(body)
            except ValueError as e:
                raise HTTPException(400, str(e)) from None
        return handler

    for name, fn in (("order", desk.order), ("modify", desk.modify), ("cancel", desk.cancel),
                     ("cancel-symbol", desk.cancel_symbol), ("flatten", desk.flatten),
                     ("reverse", desk.reverse)):
        app.add_api_route(f"/api/trade/{name}", route(fn), methods=["POST"], name=f"trade_{name}")

    @app.post("/fake/enabled")
    async def fake_enabled(body: dict):
        desk.enabled = bool(body.get("on"))
        desk.publish("state", desk.snapshot())
        return {"enabled": desk.enabled}

    @app.post("/fake/refuse")
    async def fake_refuse(body: dict):
        desk.refuse = str(body["reason"]) if body.get("reason") else None
        return {"refuse": desk.refuse}

    @app.post("/fake/fill")
    async def fake_fill(body: dict):
        aid, oid = str(body.get("account")), str(body.get("order_id"))
        if oid not in desk.acct.get(aid, {}).get("orders", {}):
            raise HTTPException(404, "no such working order")
        # ts_ms (epoch ms, optional): stamp the fill on a replay's own clock instead of real wall-clock time,
        # so a manually-triggered fill lands inside the replay's loaded bars (review item 7).
        desk.fill_order(aid, oid, body.get("price"), body.get("ts_ms"))
        return {"ok": True}

    @app.post("/fake/quote")
    async def fake_quote(body: dict):
        root, last = str(body.get("root") or "").upper(), body.get("last")
        if not root or not isinstance(last, (int, float)) or isinstance(last, bool):
            raise HTTPException(400, "root and a numeric last are required")
        desk.on_quote(root, float(last), body.get("ts_ms"))
        return {"ok": True}

    @app.post("/fake/session-end")
    async def fake_session_end():
        return {"dropped": desk.session_end()}

    @app.post("/fake/bot")
    async def fake_bot(body: dict):
        if body.get("scenario") not in SCENARIOS:
            raise HTTPException(400, f"scenario: one of {', '.join(SCENARIOS)}")
        desk.set_bot(body["scenario"], float(body.get("anchor") or 30900.0))
        desk.publish("bot", desk.bot)
        desk.changed("sim041")
        return desk.bot

    @app.post("/fake/drop")
    async def fake_drop():
        n = len(desk.subs)
        for q in list(desk.subs):
            q.put_nowait((None, None))
        return {"dropped": n}

    return app


def write_key(path: Path) -> str:
    key = secrets.token_hex(32)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(key + "\n")
    os.chmod(path, 0o600)
    return key


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.fake_desk")
    ap.add_argument("--port", type=int, default=PORT)
    a = ap.parse_args(argv)
    if a.port in FORBIDDEN_PORTS:
        ap.error(f"port {a.port} belongs to the real desk or the chart service")
    key = write_key(state_dir() / KEY_FILE)
    uvicorn.run(create_fake_desk(key), host="127.0.0.1", port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
