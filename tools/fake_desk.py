"""A FAKE desk for browser checks of chart trading: never the real desk, never a broker.

    .venv/bin/python -m tools.fake_desk [--port 8859]

It speaks the desk's /api/trade/* (homebase/desk_api.py + trading.py):
  * the X-Homebase-Key header, with ITS OWN key, written fresh to homebase/.state/fake-desk.key
    (mode 0600) at start; the real desk.key is never read or written;
  * no Origin;
  * GET /state, and the SSE /stream: state first, then account / bot / fill / result, and a
    heartbeat every 15 s;
  * POST order / modify / cancel / exits / cancel-symbol / flatten / reverse, answering
    {"results": {account: {ok, order_id, error[, refused]}}}.
  * GET bot-history?strategy=nq930&days=N: past runs built by the desk's own homebase.bothistory from a
    SEEDED journal (a few weekdays before today: TP, SL, skipped, a whole-day gate skip, no fill, refused).
  * POST bot-kill {client_id, strategy}: the NQ 9:30 bot only -- its own orders cancelled, its own position
    flattened (at the body's quote, else its entry), `killed` shown on the bot view; idempotent per client_id.
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
import functools
import itertools
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse

from homebase import bothistory
from homebase.contracts import point_value, round_to_tick
from homebase.paths import state_dir
from homebase.trading import (Refused, check_prices, exit_levels, parse_cancel, parse_exits, parse_modify,
                              parse_order, parse_symbol_action)

PORT = 8859
FORBIDDEN_PORTS = frozenset({8850, 8852, 8853, 8854})   # the real desk, the chart service, the replays
KEY_FILE = "fake-desk.key"
MAX_ORDER, MAX_POSITION = 10, 20
HEARTBEAT_S = 15.0
MONTH = "Z6"
ET = ZoneInfo("America/New_York")
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
        self.journal: list[dict] = seed_journal(dt.date.today())
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

    def exits(self, body) -> dict:
        """The desk's `exits` (trading.ChartDesk._exits_one): its pure rule (exit_levels) on this fake's own
        book -- the kept exit dropped, the final SL/TP rested GTC as one OCO pair (the first to fill drops the
        other)."""
        it = parse_exits(body)
        if ("exits", it.client_id) in self.seen:
            return self.seen[("exits", it.client_id)]
        symbol = it.root + MONTH
        q = (body.get("quotes") or {}).get(it.root) or {}
        res = {}
        for aid in it.accounts:
            why = self.gate(aid)
            a = self.acct.get(aid)
            p = a["pos"].get(symbol) if why is None else None
            net = p["net"] if p else 0
            if why is None and not net:
                why = f"no {symbol} position on {a['label']} to protect"
            if why is None and net != it.expected(aid):
                why = (f"the {symbol} position on {a['label']} changed since you confirmed "
                       f"({it.expected(aid):+d} → {net:+d}) — nothing done")
            if why is None and any((a["legs"].get(oid) or {}).get("sl") or (a["legs"].get(oid) or {}).get("tp")
                                   for oid, o in a["orders"].items() if o["symbol"] == symbol):
                # a pending entry here still carries its bracket (the desk: a Suspended OSO leg)
                why = (f"a pending order's bracket is waiting in {symbol} on {a['label']} — "
                       "cancel it or let it fill first")
            if why is None:
                out = "Sell" if net > 0 else "Buy"
                ex = [o for o in a["orders"].values() if o["symbol"] == symbol and o["side"] == out]
                if any(o["owner"] for o in ex):
                    why = "the nq930 bot's exits protect this position — they can't be changed from the chart"
                else:
                    try:
                        rnd = (lambda v: None if v is None else round_to_tick(symbol, v))
                        ex_sl, ex_tp, sl, tp = exit_levels(net, ex, rnd(it.sl_price), rnd(it.tp_price),
                                                           q.get("last"))
                    except Refused as e:
                        why = str(e)
            if why:
                res[aid] = self.refused(why)
                continue
            for kept in (ex_sl, ex_tp):
                if kept is not None:
                    self.drop_order(aid, kept["order_id"])
            sid = self.rest(aid, symbol, out, abs(net), "Stop", sl, tif="GTC") if sl is not None else None
            tid = self.rest(aid, symbol, out, abs(net), "Limit", tp, tif="GTC") if tp is not None else None
            if sid and tid:
                a["legs"][sid]["oco"], a["legs"][tid]["oco"] = tid, sid
            self.changed(aid)
            res[aid] = self.ok(sid or tid)
        return self.finish("exits", it.client_id, res)

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
            "timer": timer, "day_status": day, "killed": False, "accounts": {"sim041": st}}}}

    # ---- the bots: history + the per-strategy kill (trading.ChartDesk.bot_history / bot_kill) ----
    def _strategy(self, name) -> str:
        if not isinstance(name, str) or name not in self.bot["strategies"]:
            raise ValueError(f"unknown strategy {name!r}")
        return name

    def bot_history(self, strategy, days=None) -> dict:
        name, n = self._strategy(strategy), bothistory.parse_days(days)
        sym = self.bot["strategies"][name]["symbol"]
        return {"strategy": name, "symbol": sym,
                "runs": bothistory.runs(self.journal, name, symbol=sym,
                                        today=dt.date.today().isoformat(), days=n)}

    def bot_kill(self, body) -> dict:
        if not isinstance(body, dict):
            raise ValueError("the body is a JSON object")
        cid = body.get("client_id")
        if not isinstance(cid, str) or not 1 <= len(cid) <= 64:
            raise ValueError("client_id: a string of 1-64 characters")
        name = self._strategy(body.get("strategy"))
        if ("bot-kill", cid) in self.seen:
            return self.seen[("bot-kill", cid)]
        s = self.bot["strategies"][name]
        s["killed"] = True
        q = (body.get("quotes") or {}).get(s["symbol"]) or {}
        results = {}
        for aid, st in s["accounts"].items():
            if st["status"] == "idle":
                results[aid] = {"ok": True, "note": "the bot has not acted on this account today — nothing to do"}
                continue
            acts = []
            if st["status"] == "live":
                px = float(q.get("last") or st["entry_fill"])
                out = "Sell" if st["entry_side"] == "Buy" else "Buy"
                self.fill(aid, "NQZ6", out, st["entry_qty"], px, str(next(self.ids)), owner=name,
                          ts_ms=q.get("ts_ms"))
                acts.append(f"market {out} {st['entry_qty']}: ok")
                sign = 1 if st["entry_side"] == "Buy" else -1
                st.update(exit_fill=px, pnl=round(sign * (px - st["entry_fill"]) * 20 * st["entry_qty"], 2))
            for oid in [k for k, o in self.acct[aid]["orders"].items() if o["owner"] == name]:
                self.drop_order(aid, oid)
                acts.append(f"cancel {oid}: ok")
            if st["status"] in ("placed", "live"):
                st.update(status="done", exit_reason="killed")
            results[aid] = {"ok": True, "acted": True, "actions": acts}
            self.changed(aid)
        if s["day_status"] in ("placed", "live"):
            s["day_status"] = "done"
        self.journal.append({"ts": dt.datetime.now().timestamp(),
                             "et": dt.datetime.now().astimezone().isoformat(timespec="seconds"),
                             "event": "strategy_killed", "strategy": name, "results": results})
        self.publish("bot", self.bot)
        out = {"ok": all(r["ok"] for r in results.values()), "results": results}
        self.seen[("bot-kill", cid)] = out
        self.publish("result", {"client_id": cid, "action": "bot-kill", **out})
        return out


def seed_journal(today: dt.date) -> list[dict]:
    """A few past NQ 9:30 runs on sim041, in the desk journal's own event shapes, on the weekdays
    before `today`: TP, SL, a manual-position skip, a whole-day gate skip, no fill, a refused alert."""
    days, d = [], today
    while len(days) < 8:
        d -= dt.timedelta(days=1)
        if d.weekday() < 5:
            days.append(d)
    days.reverse()

    def rec(day, hms, event, **data):
        t = dt.datetime.combine(day, dt.time.fromisoformat(hms), tzinfo=ET)
        return {"ts": t.timestamp(), "et": t.isoformat(timespec="seconds"), "event": event,
                "strategy": "nq930", **data}

    out = []
    for i, day in enumerate(days):
        a = 30700.0 + 25 * i                        # the anchor drifts a little day to day
        up, dn = a + 10, a - 10
        kind = ("tp", "sl", "skip", "tp", "chop", "no_fill", "refused", "sl")[i]
        if kind == "skip":
            out.append(rec(day, "09:28:31", "timer_skipped", account="sim041", reason="manual_position",
                           net=1, orders=[]))
            continue
        if kind == "chop":
            out.append(rec(day, "09:30:00", "timer_skipped", reason="gate_chop", adx=14.2))
            continue
        if kind == "refused":
            out.append(rec(day, "09:30:00", "alert_refused", reason="bad_spread", upper=up, lower=dn))
            continue
        out.append(rec(day, "09:30:00", "placed", account="sim041", source="timer", upper=up, lower=dn,
                       qty=1, upper_id=f"u{i}", lower_id=f"l{i}", place_ms=88))
        if kind == "no_fill":
            out.append(rec(day, "12:55:00", "cancelled_unfilled", account="sim041"))
            continue
        side = "Buy" if i % 2 == 0 else "Sell"
        fill = (up + 0.25) if side == "Buy" else (dn - 0.25)
        sign = 1 if side == "Buy" else -1
        exit_px = fill + sign * 15 if kind == "tp" else fill - sign * 5
        out.append(rec(day, "09:30:01", "entry_fill", account="sim041", side=side, fill=fill,
                       anchor=up if side == "Buy" else dn, qty_filled=1))
        out.append(rec(day, "09:44:10" if kind == "tp" else "09:33:20", "exit_fill", account="sim041",
                       reason=kind, fill=exit_px, pnl=round(sign * (exit_px - fill) * 20, 2)))
    return out


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

    @app.get("/api/trade/bot-history")
    async def trade_bot_history(request: Request):
        check(request)
        try:
            return desk.bot_history(request.query_params.get("strategy"), request.query_params.get("days"))
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

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
                     ("exits", desk.exits), ("cancel-symbol", desk.cancel_symbol), ("flatten", desk.flatten),
                     ("reverse", desk.reverse), ("bot-kill", desk.bot_kill)):
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


# =====================================================================================================================
# LAB MODE (Step B, task B5): python -m tools.fake_desk --lab --ticks http://127.0.0.1:8853 --store <dir> [--port 8859]
#                                                        [--resume <engine dir>]
#
# A whole practice Desk for rehearsing a promoted Lab strategy on accounts: the REAL engine (homebase.engine.Engine),
# the REAL intake and config half (homebase.labdesk.LabDesk), the REAL runner routes (desk_api.labdesk_router behind
# desk_api.runner_gate) and the REAL write guard (desk_api.WriteGuard), on three SIMULATED accounts
# (tools/sim_adapter.py: two demo, one marked live) whose orders fill by the tester's fill law on the prints of a
# private chart service (--ticks, labrun.tickclient). The Desk page is served from homebase/static.
#
#   its own state   an in-memory AppCfg (config.json is never read or written), the engine's files in a temp folder
#                   (printed at the start; --resume <that folder> starts again on it), the Lab store given by --store,
#                   its own key homebase/.state/fake-lab.key (mode 0600, written fresh at every start: give it to the
#                   runner with --desk-key). The Lab side is on without the flag file.
#   its clock       the tick stream's (a replayed day): the engine's `now` is the stream's clock, so "today", the
#                   session window and the flat time are the replayed day's.
#   never           port 8850 or 8852 (its own port, --ticks, and every address in the page and the static files it
#                   serves), a broker, ~/.homebase, the main checkout (asked of git; a folder is refused however it
#                   is spelled or linked), a real Desk's key file, config.json (a save of this config raises).
#   a restart       --resume: each simulated account is reconciled by the engine right after it connects, as the real
#                   Desk does (engine.reconcile_account), and once more when the stream's backlog is in.
#
# The page routes below are the real server's bodies for a Lab strategy, calling the same LabDesk / Engine methods
# (homebase/server.py cannot be imported for them: it builds the real app, from config.json, at import). What differs
# is said at each route.
#
#   POST /fake/lab   (the runner's gate: loopback Host, no Origin, X-Homebase-Key = fake-lab.key; JSON)
#       {"account": "sim047"}?            the account the adapter faults below go to (default: all three)
#       {"reject_next": n, "reject_words": "..."}   the next n entries are refused by the broker, in these words
#       {"partial_next": qty}             the next entry fill gives only qty contracts
#       {"fill_both": bool}               both entries of a pair fill
#       {"ack_delay_ms": n}               a broker answer comes n ms late (the order is live meanwhile)
#       {"order_status_unknown": id | true | null}   that order's (every order's) status cannot be read
#       {"position_unreadable": bool}     the position read before an entry (and before a close) fails
#       {"close_refused": bool}           the one market close is refused
#       {"legs_outlive": bool}            a cancelled entry's stop and target stay until cancelled themselves
#       {"stream_drop": true}             every reader of GET /api/lab/stream is ended (the runner reconnects)
#       {"silent_s": n}                   that stream says nothing, not even its heartbeat, for n seconds
#       {"timer_placing_s": n}            a strategy that is not from the Lab reads `placing` for n seconds
#       {"chart_kill": "lab_<name>"}      the chart's per-strategy Kill (engine.kill_strategy), with no chart link
#   GET /fake/lab    the simulated accounts as a person would see them, and the faults that are on
# =====================================================================================================================
LAB_KEY_FILE = "fake-lab.key"
LAB_STATE_FILE = "fake-desk.json"            # in the engine folder: what the real Desk keeps in config.json (armed)
LAB_CLOCK_S, LAB_SIBLING_S = 1, 0.25         # server.CLOCK_INTERVAL_S / SIBLING_INTERVAL_S
LAB_JOURNAL_TAIL = 60                        # server.JOURNAL_TAIL
LAB_FIRST_CLOCK_S = 30.0                     # the start waits this long for the tick stream's first clock
TICKS_REFUSED = frozenset({8850, 8852})      # the real desk and the real chart service: never read from
PAGE_CHART_LINE = 'const CHART = location.protocol + "//" + location.hostname + ":8852";'
PAGE_CHART_SWAP = 'const CHART = location.origin + "/chart";'
CHART_GETS = ("api/tester/desklab", "api/tester/watch", "api/paper/accounts", "api/status", "api/settings")
RIG_FAULTS = ("stream_drop", "silent_s", "timer_placing_s", "chart_kill", "account")
TIMER_STATE = "fake_timer@timer"             # the made-up state of timer_placing_s (no such strategy, no such account)


@functools.lru_cache(maxsize=None)
def main_checkout(start: Path | None = None) -> Path:
    """The checkout the live services run from, ASKED OF GIT (never guessed from where this file sits: this
    repository keeps worktrees in two places): the folder that holds the repository's common git dir, as
    `git rev-parse --git-common-dir` answers from the tool's own folder (`start`: another folder, for the tests).
    ValueError when git cannot say: the practice Desk then does not start."""
    here = Path(start) if start is not None else Path(__file__).resolve().parent
    out = ""
    try:
        r = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=here,
                           capture_output=True, text=True, timeout=10,
                           env={k: v for k, v in os.environ.items() if not k.startswith("GIT_")})
        out = r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        pass
    common = Path(out) if out else None
    if common is None or not common.is_absolute() or not common.is_dir():
        raise ValueError("git could not say where this repository's main checkout is: the practice Desk does not start")
    common = common.resolve()
    return common.parent if common.name == ".git" else common


WORKTREE_DIRS = (Path(".claude") / "worktrees", Path(".worktrees"))     # inside the main checkout: where worktrees live


def _same(a: Path, b: Path) -> bool:
    try:
        return a.exists() and b.exists() and os.path.samefile(a, b)
    except OSError:
        return False


def _inside(p: Path, root: Path, *, loose: bool, strict: bool = False) -> bool:
    """Is `p` the folder `root` or under it (strict: under it only)? Asked twice. By IDENTITY: one of p's own
    folders is that folder, whatever it is called here -- another spelling on a disk that ignores case, a link.
    And by TEXT, for folders that do not exist yet: loose compares without case (a refusal errs towards refusing),
    else exactly (an allowance never does)."""
    chain = list(p.parents) if strict else [p, *p.parents]
    if any(_same(q, root) for q in chain):
        return True
    fold = (lambda x: x.casefold()) if loose else (lambda x: x)
    a, b = [fold(c) for c in p.parts], [fold(c) for c in root.parts]
    return a[:len(b)] == b and (len(a) > len(b) or not strict)


def refused_folder(path, main: Path | None = None, home: Path | None = None) -> str | None:
    """Why this folder may not hold a practice Desk's store or engine files, or None. Refused: anything that IS, or
    lies under, ~/.homebase (the real store is ~/.homebase/desklab) or the main checkout -- however it is spelled
    and through whatever link it is reached (the path is resolved first, then compared by identity and without
    case). Allowed inside the main checkout: only what lies under one of its worktree folders (.claude/worktrees/,
    .worktrees/). ValueError when git cannot say where the main checkout is."""
    p = Path(path).expanduser().resolve()
    real = ((home or Path.home()) / ".homebase").resolve()
    if _inside(p, real, loose=True):
        return f"{p} is inside {real}: the real Desk's own folder"
    main = (main or main_checkout()).resolve()
    if _inside(p, main, loose=True) and not any(_inside(p, main / t, loose=False, strict=True) for t in WORKTREE_DIRS):
        return f"{p} is inside the main checkout ({main}): the live services run from it"
    return None


def guard_config_save() -> None:
    """config.json is the real Desk's. Put ONCE on homebase.config.save, for this process: a config marked as a
    practice Desk's is never saved (RuntimeError, nothing written); every other config goes to the real save as
    it is. Nothing the practice Desk runs calls save today; this holds if something one day does."""
    import homebase.config as config_mod
    real = config_mod.save
    if getattr(real, "_practice_guard", False):
        return

    @functools.wraps(real)
    def save(cfg):
        if getattr(cfg, "__dict__", {}).get("_practice_desk"):      # its own mark only: a Mock answers every getattr
            raise RuntimeError("the practice Desk's config is never saved: config.json is the real Desk's")
        return real(cfg)
    save._practice_guard = True
    config_mod.save = save


def swap_ports(data: bytes, own_port: int, ticks_port: int | None) -> bytes:
    """Every ":8852" (the real chart service) becomes the --ticks service's port, every ":8850" (the real Desk) this
    tool's own: nothing the practice Desk serves names a real port."""
    return data.replace(b":8852", f":{ticks_port if ticks_port else own_port}".encode()).replace(b":8850", f":{own_port}".encode())


STATIC_TEXT = frozenset({".html", ".js", ".mjs", ".css", ".json", ".svg", ".txt", ".map"})


def bind_port(port: int):
    """This tool's own port on 127.0.0.1, bound now -- or None when it is taken. Lab mode holds the port BEFORE it
    writes its key file: a second start beside a running practice Desk must not write a new key over the one the
    running Desk answers to."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)      # as uvicorn binds: a restart right after a stop works
        s.bind(("127.0.0.1", port))
        s.listen(128)                    # listening at once: a second start cannot bind it before the server runs
    except OSError:
        s.close()
        return None
    return s


def serve_lab(app, sock) -> None:
    """Serve on the socket bind_port holds (127.0.0.1 only: it was bound there)."""
    uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[sock])


def lab_key_path() -> Path:
    """The ONE key file Lab mode touches: its own, in this checkout's state folder, written fresh at each start.
    The real Desk's key files (desk_api.KEY_FILE, desk_api.LAB_KEY_FILE) are never opened by this tool, in any
    checkout, for reading or for writing: nothing here calls desk_api.ensure_key, and a name that is one of theirs
    is refused here."""
    from homebase import desk_api
    if LAB_KEY_FILE in (desk_api.KEY_FILE, desk_api.LAB_KEY_FILE) or not LAB_KEY_FILE.startswith("fake-"):
        raise ValueError(f"{LAB_KEY_FILE} is a real Desk's key file: the practice Desk only writes its own")
    return state_dir() / LAB_KEY_FILE


def ticks_url(url: str, own_port: int) -> str:
    """--ticks, or ValueError: http, this machine, a port -- never 8850 or 8852, never this tool's own."""
    from homebase.labrun.__main__ import local_url          # the runner's own rule for --charts (loopback, not 8850)
    from urllib.parse import urlsplit
    out = local_url(url)
    port = urlsplit(out).port
    if port is None:
        raise ValueError("it must name a port")
    if port in TICKS_REFUSED:
        raise ValueError(f"port {port} belongs to the real desk or the real chart service")
    if port == own_port:
        raise ValueError("that is this tool's own port")
    return out


class StreamClock:
    """The practice Desk's clock: the tick stream's. Until the stream has said anything, the wall clock."""

    def __init__(self):
        self.ms: int | None = None

    def heard(self, now_ms: int) -> None:        # the stream's own clock (it may go back: a replay that starts again)
        self.ms = int(now_ms)

    def saw(self, ts_ms: int) -> None:           # a print: time only goes on
        if self.ms is None or ts_ms > self.ms:
            self.ms = int(ts_ms)

    def __call__(self) -> dt.datetime:
        if self.ms is None:
            return dt.datetime.now(dt.timezone.utc)
        return dt.datetime.fromtimestamp(self.ms / 1000, dt.timezone.utc)


class LabRig:
    """The practice Desk's parts: the config in memory, three simulated accounts, the real engine and the real
    LabDesk. `store`: the Lab store; `root`: the engine's folder (also the simulated accounts' books)."""

    def __init__(self, store, root, *, clock=None, placement_ms: int | None = None):
        from homebase import labdesk as labdesk_mod
        from homebase.config import AccountCfg, AppCfg
        from homebase.engine import Engine
        from tools.sim_adapter import PLACEMENT_MS, SimAdapter
        for d in (store, root):
            why = refused_folder(d)
            if why:
                raise ValueError(why)
        self.store, self.root = Path(store), Path(root)
        self.store.mkdir(parents=True, exist_ok=True)
        self.root.mkdir(parents=True, exist_ok=True)
        self.clock = clock or StreamClock()
        saved = {}
        try:
            saved = json.loads((self.root / LAB_STATE_FILE).read_text())
        except (OSError, ValueError):
            pass
        self.cfg = AppCfg(armed=saved.get("armed") is not False, book={}, strategies={},
                          accounts={aid: AccountCfg(account_name=label, label=label, live=env == "live")
                                    for aid, label, env in ACCOUNTS})
        self.cfg.__dict__["_practice_desk"] = True           # config.save refuses it (guard_config_save)
        guard_config_save()
        self.adapters = {aid: SimAdapter(aid, self.root, live=env == "live", label=label, first_id=(i + 1) * 100_000 + 1,
                                         placement_ms=PLACEMENT_MS if placement_ms is None else placement_ms)
                         for i, (aid, label, env) in enumerate(ACCOUNTS)}
        labdesk_mod.attach(self.cfg, self.store)             # the promoted strategies join the config in memory
        self.engine = Engine(self.cfg, self.adapters, now_fn=self.clock, root=self.root)
        self.labdesk = labdesk_mod.LabDesk(self.cfg, self.engine, self.adapters, at=self.store, on=True)
        self.silent_until = 0.0                              # time.monotonic: the runner's stream says nothing until then
        self.mono = time.monotonic
        self.sleep = asyncio.sleep
        self._timer: asyncio.Task | None = None
        self.journal_cache = bothistory.JournalCache()
        self._live: dict = {"recs": None, "live": {}}

    async def start(self) -> None:
        for aid, ad in self.adapters.items():
            await ad.connect()
            await ad.observe_fills(self.engine.on_fill)
            await self.reconcile(aid)                        # where the real Desk does it: right after the connect
        self.labdesk.start()

    async def reconcile(self, aid: str) -> None:
        """server.py `_connect_account_locked`, its last step: engine.reconcile_account, and a failure of it is
        journaled, never the end of the connect."""
        try:
            await self.engine.reconcile_account(aid)
        except Exception as e:  # noqa: BLE001 -- never block the connect on it
            self.engine.journal("reconcile_error", account=aid, error=str(e)[:200])

    def roots(self) -> list:
        """The markets the tick stream is asked for: every Lab strategy's, and any a simulated account still holds."""
        out = {str(s.symbol).upper() for s in list(self.cfg.strategies.values()) if getattr(s, "kind", "") == "lab"}
        for ad in self.adapters.values():
            out |= {o.market for o in list(ad.orders.values()) if o.status in ("Working", "Suspended")}
            out |= {m for m, p in list(ad.pos.items()) if p["net"]}
        return sorted(out)

    async def take(self, item: tuple) -> None:
        """One item of the tick client (labrun.tickclient.TickClient): the clock, the prints, `live`."""
        if item[0] == "clock":
            self.clock.heard(item[1])
            for ad in self.adapters.values():
                await ad.on_clock(item[1])
        elif item[0] == "ticks":
            for row in item[2]:                              # one print at a time on every account: the engine's clock
                self.clock.saw(int(row[0]))                  # is that print's time when it hears of a fill
                for ad in self.adapters.values():
                    await ad.on_ticks(item[1], [row])
        elif item[0] == "live":                              # the backlog is in: a fill is told to the engine again
            for aid, ad in self.adapters.items():
                was_away = ad.away
                ad.back()
                if was_away:                                 # a start on a saved book: only now does the account know
                    await self.reconcile(aid)                # what a broker knows at connect -- reconciled again

    def silent(self) -> bool:
        return self.mono() < self.silent_until

    def save_state(self) -> None:
        (self.root / LAB_STATE_FILE).write_text(json.dumps({"armed": bool(self.cfg.armed)}) + "\n")

    async def _timer_placing(self, seconds: float) -> None:
        try:
            await self.sleep(seconds)
        finally:
            self.engine.states.pop(TIMER_STATE, None)

    async def fault(self, body) -> dict:
        """POST /fake/lab. ValueError: the body does not read (nothing is changed then)."""
        from tools.sim_adapter import Faults
        if not isinstance(body, dict):
            raise ValueError("a JSON object of faults")
        acct = body.get("account")
        if acct is not None and acct not in self.adapters:
            raise ValueError(f"unknown account {acct!r}")
        mine = {k: v for k, v in body.items() if k not in RIG_FAULTS}
        Faults().set(mine)                                   # every field is checked before any is set
        for k in ("silent_s", "timer_placing_s"):
            v = body.get(k)
            if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float)) or not 0 <= v <= 3600):
                raise ValueError(f"{k}: seconds, 0 to 3600")
        if "stream_drop" in body and body["stream_drop"] is not True:
            raise ValueError("stream_drop: true")
        kill = body.get("chart_kill")
        if kill is not None and not self.labdesk.is_lab(kill):
            raise ValueError("chart_kill: a Lab strategy on this Desk (lab_<name>)")
        for aid, ad in self.adapters.items():
            if acct in (None, aid):
                ad.faults.set(mine)
        out: dict = {"ok": True}
        if body.get("stream_drop") is True:
            # what LabDesk._publish does to a reader that fell behind: its queue is emptied and ends
            subs = list(self.labdesk._subs)
            for q in subs:
                self.labdesk.unsubscribe(q)
                while not q.empty():
                    q.get_nowait()
                q.put_nowait((None, None))
            out["dropped"] = len(subs)
        if body.get("silent_s") is not None:
            self.silent_until = self.mono() + float(body["silent_s"])
        if body.get("timer_placing_s") is not None:
            if self._timer is not None:
                self._timer.cancel()
            self.engine.states.pop(TIMER_STATE, None)
            if body["timer_placing_s"]:
                from homebase.engine import DayState
                # a state of a strategy that is not from the Lab, placing: what LabDesk.held() looks for. No such
                # strategy and no such account exist here, so nothing else of the engine acts on it
                self.engine.states[TIMER_STATE] = DayState(strategy="fake_timer", account="timer",
                                                            date=self.engine._today(), status="placing")
                self._timer = asyncio.ensure_future(self._timer_placing(float(body["timer_placing_s"])))
        if kill is not None:                                 # trading.ChartDesk.bot_kill's own engine call
            out["chart_kill"] = await self.engine.kill_strategy(kill, source="chart", client_id="fake-lab")
        return {**out, "faults": self.view()["faults"]}

    def view(self) -> dict:
        from dataclasses import asdict as _asdict
        return {"accounts": [ad.book() for ad in self.adapters.values()],
                "faults": {**{aid: _asdict(ad.faults) for aid, ad in self.adapters.items()},
                           "silent_s": round(max(0.0, self.silent_until - self.mono()), 1),
                           "timer_placing": TIMER_STATE in self.engine.states},
                "et_now": self.engine.now_et().isoformat(timespec="seconds"), "engine_root": str(self.root),
                "store": str(self.store)}

    async def status(self) -> dict:
        """GET /api/status with the real route's keys (server.py `status`). The strategies block, the accounts
        block, the book and the journal tail are built as there, by the same calls. What is NOT the real thing:
        readiness holds only the Mode line and the two Lab lines (labdesk.readiness_line / orphan_line) -- the real
        compute_readiness lives in server.py; timer / levels / feed are empty (no timer, no feed here); no notices."""
        from dataclasses import asdict as _asdict
        from homebase import labdesk as labdesk_mod
        from homebase.metrics import live_metrics
        cfg, engine, labdesk = self.cfg, self.engine, self.labdesk
        accounts = {}
        for aid, a in cfg.accounts.items():
            ad = self.adapters.get(aid)
            try:
                m = await ad.get_metrics() if ad else {"connected": False}
            except Exception as e:  # noqa: BLE001
                m = {"connected": False, "error": f"metrics: {e}"}
            accounts[aid] = {"label": a.label or a.account_name or aid,
                             "env": "paper" if a.paper else "live" if a.live else "demo", "cooldown_s": 0, **m}
        recs = self.journal_cache.records(self.root / "journal.jsonl")
        if recs is not self._live["recs"]:
            self._live.update(recs=recs, live=live_metrics(recs))
        live = self._live["live"]
        checks = [c for c in (labdesk_mod.readiness_line(cfg), labdesk_mod.orphan_line(cfg, engine)) if c is not None]
        checks.append({"level": "info", "label": "Mode", "detail": "ARMED — signals place real orders" if cfg.armed
                       else "shadow — signals journal only"})
        date = engine.now_et().date().isoformat()
        return {
            "armed": cfg.armed,
            "chart_trading": _asdict(cfg.chart_trading),
            "et_now": engine.now_et().isoformat(timespec="seconds"),
            "readiness": {"ready": not any(c["level"] == "bad" for c in checks), "checks": checks},
            "timer": {"date": date, "strategies": {}},
            "levels": {"date": date, "strategies": {}},
            "feed": {"connected": False, "watching": {}, "error": None, "window": False},
            "accounts": accounts,
            "notices": [],
            "book": labdesk.book_view(),
            "strategies": {
                name: {
                    "cfg": {"symbol": s.symbol, "qty": s.qty,
                            "offset_pts": s.offset_pts, "sl_pts": s.sl_pts,
                            "tp_pts": s.tp_pts, "rr": s.rr, "label": s.label, "cancel_et": s.cancel_et,
                            "flat_et": s.flat_et, "fire_et": s.fire_et,
                            "only_dates": list(s.only_dates), "enabled": s.enabled,
                            "gated": s.gated, "self_fire": s.self_fire,
                            "kind": getattr(s, "kind", "straddle"),
                            "shadow": getattr(s, "shadow", False),
                            "rule": getattr(s, "rule", ""),
                            "bar_minutes": getattr(s, "bar_minutes", 1),
                            "shape": s.shape, "day_take": s.day_take,
                            "day_lock": s.day_lock, "target_take": s.target_take,
                            "size_tiers": s.size_tiers, "ack_open_loss": s.ack_open_loss},
                    "research": s.metrics,
                    "live": live.get(name),
                    "day_status": engine.day_status(name),
                    "killed": engine.killed_today(name),
                    "accounts": [{**vars(st), "check_it": engine.needs_check(st)}
                                 for st in engine.day_states(name)],
                    "lab": labdesk.status_view(name),
                } for name, s in list(cfg.strategies.items())
            },
            "journal": labdesk_mod.journal_tail(recs, LAB_JOURNAL_TAIL),   # without the intake's bookkeeping lines
        }


def lab_page(static: Path, own_port: int, ticks_port: int | None) -> str:
    """The Desk page as it is on disk, with every address that would leave this practice Desk pointed back at it:
    the chart-service line (the page's CHART) becomes this tool's own /chart pass-through, every other ":8852" the
    --ticks service's port and every ":8850" this tool's. ValueError when the page no longer has that one line: a
    page that would call the real chart service is never served."""
    text = (static / "index.html").read_text(encoding="utf-8")
    if text.count(PAGE_CHART_LINE) != 1:
        raise ValueError("the Desk page's chart-service line changed: tools/fake_desk.py (PAGE_CHART_LINE) must follow it")
    text = text.replace(PAGE_CHART_LINE, PAGE_CHART_SWAP)
    return text.replace(":8852", f":{ticks_port if ticks_port else own_port}").replace(":8850", f":{own_port}")


class _Silence:
    """Pure ASGI: while the rig is `silent`, nothing of GET /api/lab/stream reaches the reader -- not a snapshot, not
    the heartbeat. What was held goes out, in order, when the silence ends (the stream's own generator simply waits
    at its send, as for a reader that does not read: LabDesk drops one that falls 200 snapshots behind)."""

    def __init__(self, app, rig: LabRig, path: str = "/api/lab/stream"):
        self.app, self.rig, self.path = app, rig, path

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http" or scope["path"] != self.path:
            await self.app(scope, receive, send)
            return

        async def held(message) -> None:
            while message["type"] == "http.response.body" and self.rig.silent():
                await self.rig.sleep(0.05)
            await send(message)
        await self.app(scope, receive, held)


def create_lab_desk(store, root, *, key: str, clock=None, ticks: str | None = None, own_port: int = PORT,
                    inbox=None, placement_ms: int | None = None, background: bool = True,
                    chart_transport=None) -> FastAPI:
    """The practice Desk's app. key: what /api/lab/* and /fake/lab ask for (X-Homebase-Key). ticks: the private chart
    service, for the page's /chart pass-through; the tick client itself is started by main, which hands its queue in
    as `inbox`. background False (the tests): no clock loop, no LabDesk loop, no pump -- a test turns them by hand."""
    import contextlib
    import queue as queue_mod
    from urllib.parse import urlsplit

    import httpx
    from fastapi.responses import HTMLResponse, JSONResponse, Response

    from homebase import desk_api
    from homebase import labdesk as labdesk_mod

    rig = LabRig(store, root, clock=clock, placement_ms=placement_ms)
    cfg, engine, labdesk, adapters = rig.cfg, rig.engine, rig.labdesk, rig.adapters
    static = Path(__file__).resolve().parents[1] / "homebase" / "static"        # server.STATIC
    ticks_port = urlsplit(ticks).port if ticks else None
    chart = httpx.AsyncClient(base_url=ticks, trust_env=False, follow_redirects=False, timeout=5.0,
                              transport=chart_transport) if ticks else None

    async def _loop(step, every: float, event: str) -> None:
        while True:
            try:
                await step()
            except Exception as e:  # noqa: BLE001 -- as the real desk's loops: journaled, never the end of the loop
                with contextlib.suppress(Exception):
                    engine.journal(event, error=str(e)[:200])
            await asyncio.sleep(every)

    async def _pump() -> None:
        while True:
            try:
                item = await asyncio.to_thread(inbox.get, True, 0.5)
            except queue_mod.Empty:
                continue
            try:
                await rig.take(item)
            except Exception as e:  # noqa: BLE001 -- one bad item must not end the prints
                with contextlib.suppress(Exception):
                    engine.journal("fake_pump_error", error=f"{type(e).__name__}: {e}"[:200])

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        _app.state.lab_key = key                     # desk_api.runner_gate reads it (the real desk: its own key file)
        await rig.start()
        tasks = []
        if background:
            tasks = [asyncio.create_task(_loop(engine.clock_tick, LAB_CLOCK_S, "clock_error")),
                     asyncio.create_task(_loop(engine.sibling_tick, LAB_SIBLING_S, "sibling_loop_error")),
                     asyncio.create_task(labdesk.run())]
            if inbox is not None:
                tasks.append(asyncio.create_task(_pump()))
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            with contextlib.suppress(Exception):
                labdesk.close()
            for ad in adapters.values():
                with contextlib.suppress(Exception):
                    await ad.close()
            if chart is not None:
                with contextlib.suppress(Exception):
                    await chart.aclose()

    app = FastAPI(title="practice Desk (rehearsals only)", lifespan=lifespan)
    app.state.rig, app.state.engine, app.state.labdesk, app.state.cfg, app.state.adapters = rig, engine, labdesk, cfg, adapters
    app.state.chart = chart
    app.state.lab_key = key
    app.include_router(desk_api.labdesk_router(labdesk), prefix="/api/lab")     # the REAL runner routes and gate
    app.add_middleware(_Silence, rig=rig)
    app.add_middleware(desk_api.WriteGuard, hosts=lambda: cfg.allowed_hosts)    # the REAL guard of every page write
    static_root = static.resolve()

    @app.get("/static/{path:path}")
    async def static_file(path: str):
        """homebase/static as it is on disk -- except that a text file naming a real port (":8850", ":8852") is
        served with it swapped, as the page is (the chart pages do). Nothing outside that folder is served."""
        import mimetypes
        f = (static_root / path).resolve()
        if static_root not in f.parents or not f.is_file():
            raise HTTPException(404, "Not Found")
        data = f.read_bytes()
        if b":8850" in data or b":8852" in data:
            if f.suffix.lower() not in STATIC_TEXT:
                raise HTTPException(404, "Not Found")        # not text: it cannot be swapped, so it is not served
            data = swap_ports(data, own_port, ticks_port)
        return Response(content=data, media_type=mimetypes.guess_type(f.name)[0] or "application/octet-stream")

    def refused(e) -> HTTPException:
        return HTTPException(e.status, str(e))

    def known(body) -> str:
        name = str(body.get("strategy") or "")
        if name not in cfg.strategies:
            raise HTTPException(404, f"unknown strategy {name!r}")
        return name

    only_lab = HTTPException(409, "the practice Desk has Lab strategies only")   # the real route's other branch

    @app.get("/")
    async def index():
        try:
            return HTMLResponse(lab_page(static, own_port, ticks_port), headers={"Cache-Control": "no-store"})
        except (OSError, ValueError) as e:
            return JSONResponse({"detail": str(e)}, 500)

    @app.get("/chart/{path:path}")
    async def chart_get(path: str, request: Request):
        """The page's reads of the chart service, passed on to the PRIVATE one (--ticks): the page itself cannot
        reach it (that service answers the real Desk's origin only). Reads only, and only the five the page makes."""
        if chart is None or path not in CHART_GETS:
            raise HTTPException(404, "not passed on")
        try:
            r = await chart.get("/" + path, params=dict(request.query_params))
        except httpx.HTTPError:
            return JSONResponse({"detail": "the private chart service is not reachable"}, 502)
        return Response(content=r.content, status_code=r.status_code,
                        media_type=r.headers.get("content-type", "application/json"))

    @app.get("/api/status")
    async def status():
        return await rig.status()

    @app.post("/api/arm")
    async def arm(request: Request):
        """server.py `arm`. Differs: the switch is kept in the engine folder's fake-desk.json, not in config.json."""
        body = await request.json()
        cfg.armed = bool(body.get("armed"))
        rig.save_state()
        engine.journal("armed_toggled", armed=cfg.armed)
        return {"ok": True, "armed": cfg.armed}

    kill_lock_box: dict = {}

    def _kill_lock() -> asyncio.Lock:
        loop = asyncio.get_running_loop()
        held = kill_lock_box.get("lock")
        if held is None or held[0] is not loop:
            held = kill_lock_box["lock"] = (loop, asyncio.Lock())
        return held[1]

    @app.post("/api/kill")
    async def kill():
        """server.py `kill`: disarm, then engine.flatten_today and each account's cancel_all / flatten_all under the
        same locks. Differs: there is no chart trading to switch off, and the disarm goes to fake-desk.json."""
        cfg.armed = False
        rig.save_state()
        async with _kill_lock(), engine.all_kill_locks():
            strategies = await engine.flatten_today()

            async def sweep(ad) -> dict:
                r = {}
                for call in ("cancel_all", "flatten_all"):
                    try:
                        x = await getattr(ad, call)()
                        r[call] = {"ok": x.ok, "error": x.error}
                    except Exception as e:  # noqa: BLE001 -- kill always finishes
                        r[call] = {"ok": False, "error": str(e)}
                return r

            pool = dict(adapters)
            got, _ = await engine.each_account(pool, lambda aid: sweep(pool[aid]))
            results = {aid: (g if isinstance(g, dict) else {call: {"ok": False, "error": str(g)}
                                                            for call in ("cancel_all", "flatten_all")})
                       for aid, g in got.items()}
            engine.journal("kill_switch", results=results, strategies=strategies)
        return {"ok": True, "armed": False, "results": results, "strategies": strategies}

    @app.post("/api/strategy")
    async def strategy_toggle(request: Request):
        """server.py `strategy_toggle`, the Lab branch, line for line."""
        body = await request.json()
        name = known(body)
        if not labdesk.is_lab(name):
            raise only_lab
        on = bool(body.get("enabled"))
        if not on:
            await labdesk.stop(name, "off")
        try:
            if not await labdesk.set_enabled(name, on):
                raise HTTPException(409, labdesk_mod.RECORD_CHANGED)
        except labdesk_mod.Refused as e:
            raise refused(e) from None
        engine.journal("strategy_toggled", strategy=name, enabled=on)
        return {"ok": True, "strategy": name, "enabled": on}

    @app.post("/api/strategy-flatten")
    async def strategy_flatten(request: Request):
        """server.py `strategy_flatten`, the Lab branch, line for line."""
        body = await request.json()
        name = known(body)
        if not labdesk.is_lab(name):
            raise only_lab
        await labdesk.stop(name, "off")
        results = await engine.flatten_strategy(name)
        try:
            await labdesk.set_enabled(name, False)
        except Exception as e:  # noqa: BLE001 -- the flatten is done: its result is answered whatever the switch did
            engine.journal("lab_save_error", strategy=name, error=str(e)[:200], cause="manual_flatten")
            s = cfg.strategies.get(name)
            return {"ok": True, "enabled": bool(s is not None and s.enabled), "results": results,
                    **labdesk.flatten_check(name, results), "detail": labdesk_mod.SWITCH_NOT_OFF}
        engine.journal("strategy_toggled", strategy=name, enabled=False, cause="manual_flatten")
        return {"ok": True, "enabled": False, "results": results, **labdesk.flatten_check(name, results)}

    @app.post("/api/book")
    async def set_book(request: Request):
        """server.py `set_book`: the same reading of the rows, then LabDesk.set_book (a Lab strategy is the only
        kind here)."""
        body = await request.json()
        name = known(body)
        rows = []
        for a in body.get("assignments") or []:
            aid, qty = str(a.get("account") or ""), int(a.get("qty") or 0)
            if aid not in cfg.accounts:
                raise HTTPException(400, f"unknown account {aid!r}")
            if qty > 0:
                rows.append({"account": aid, "qty": qty})
        try:
            if labdesk.is_lab(name):
                await labdesk.set_book(name, rows)
                engine.journal("book_updated", strategy=name, assignments=rows)
                note = labdesk.window_note(name) if rows else None      # as the real route: a note, never a refusal
                return {"ok": True, "book": labdesk.book_view(), **({"note": note} if note else {})}
            labdesk.check_book(name, rows)
        except labdesk_mod.Refused as e:
            raise refused(e) from None
        raise only_lab

    def lab_route(path: str, shape: str, call) -> None:
        """server.py `lab_limits` / `lab_remove` / `lab_clear`: the body must be an object, LabDesk does the rest."""
        async def handler(request: Request):
            body = await request.json()
            if not isinstance(body, dict):
                raise HTTPException(400, shape)
            try:
                return await call(body)
            except labdesk_mod.Refused as e:
                raise refused(e) from None
            except ValueError as e:
                raise HTTPException(400, str(e)) from None
        app.add_api_route(path, handler, methods=["POST"], name=path.strip("/").replace("/", "_"))

    lab_route("/api/lab-limits", "{strategy, limits}",
              lambda b: labdesk.set_limits(str(b.get("strategy") or ""), b.get("limits")))
    lab_route("/api/lab-remove", "{strategy}", lambda b: labdesk.remove(str(b.get("strategy") or "")))
    lab_route("/api/lab-clear", "{strategy, account}",
              lambda b: labdesk.clear_block(str(b.get("strategy") or ""), str(b.get("account") or "")))

    # ---- what else the page reads: the real function where there is one, else an empty answer of the real shape
    @app.get("/api/strategy-live")
    async def strategy_live(strategy: str):
        """server.py `strategy_live`: metrics.strategy_live_detail on this Desk's own journal."""
        from homebase.metrics import strategy_live_detail
        if strategy not in cfg.strategies:
            raise HTTPException(404, f"unknown strategy {strategy!r}")
        return strategy_live_detail(rig.root / "journal.jsonl", strategy, cfg)

    @app.get("/api/research-equity")
    async def research_equity(strategy: str):
        return {"points": None}                      # (the real answer for a strategy with no research file)

    @app.get("/api/logins")
    async def logins():
        return {"logins": []}                        # no login exists here: the keyring is never read

    @app.get("/api/calendar")
    async def calendar(month: str, account: str = ""):
        return {"account": account, "month": month, "days": {}, "total": 0.0, "history_since": None}

    @app.get("/fake/lab")
    async def fake_lab_view(request: Request):
        desk_api.runner_gate(request)
        return rig.view()

    @app.post("/fake/lab")
    async def fake_lab(request: Request):
        desk_api.runner_gate(request)
        body = await desk_api.read_json(request, desk_api.BODY_MAX)
        try:
            return await rig.fault(body)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    return app


def first_clock(ticks: str, wait_s: float = LAB_FIRST_CLOCK_S) -> int | None:
    """The tick stream's clock, once (ms), or None when it does not come: the engine must be built ON the replayed
    day (it loads that day's files), so the practice Desk does not start before it knows what day it is."""
    import queue
    import threading

    from homebase.labrun.tickclient import TickClient
    box: queue.Queue = queue.Queue()
    stop = threading.Event()
    threading.Thread(target=TickClient(ticks, lambda: [], box.put).run, args=(stop,), name="fake-lab-probe", daemon=True).start()
    end = time.monotonic() + wait_s
    try:
        while time.monotonic() < end:
            try:
                item = box.get(timeout=0.5)
            except queue.Empty:
                continue
            if item[0] == "clock":
                return int(item[1])
        return None
    finally:
        stop.set()


def lab_main(ap, a) -> int:
    import queue
    import tempfile
    import threading

    if not a.ticks or not a.store:
        ap.error("--lab needs --ticks http://127.0.0.1:<port> (a private chart service) and --store <folder>")
    try:
        ticks = ticks_url(a.ticks, a.port)
    except ValueError as e:
        ap.error(f"--ticks {a.ticks}: {e}")
    for flag, d in (("--store", a.store), ("--resume", a.resume)):
        try:
            why = refused_folder(d) if d else None
        except ValueError as e:                              # git could not say where the main checkout is
            why = str(e)
        if why:
            ap.error(f"{flag}: {why}")
    if a.resume and not Path(a.resume).is_dir():
        ap.error(f"--resume {a.resume}: no such folder")
    sock = bind_port(a.port)                                 # held before anything else is touched (the key above all)
    if sock is None:
        print(f"Port {a.port} is taken: is a practice Desk already running? Nothing was started and its key file "
              "was not touched.", file=sys.stderr)
        return 1
    now_ms = first_clock(ticks)
    if now_ms is None:
        sock.close()
        print(f"No clock from {ticks} in {LAB_FIRST_CLOCK_S:.0f} s: is the private chart service running? "
              "The practice Desk did not start.", file=sys.stderr)
        return 1
    from homebase.labrun.tickclient import TickClient
    root = Path(a.resume) if a.resume else Path(tempfile.mkdtemp(prefix="fake-lab-desk-"))
    clock = StreamClock()
    clock.heard(now_ms)
    key_path = lab_key_path()
    key = write_key(key_path)
    inbox: queue.Queue = queue.Queue()
    app = create_lab_desk(a.store, root, key=key, clock=clock, ticks=ticks, own_port=a.port, inbox=inbox)
    stop = threading.Event()
    client = TickClient(ticks, app.state.rig.roots, inbox.put)
    threading.Thread(target=client.run, args=(stop,), name="fake-lab-ticks", daemon=True).start()
    print(f"practice Desk (Lab mode) -- http://127.0.0.1:{a.port}/\n"
          f"  prices      {ticks}  (the day is {clock().astimezone(ET).date()})\n"
          f"  Lab store   {Path(a.store).resolve()}\n"
          f"  engine      {root}   (start again on it: --resume {root})\n"
          f"  runner      --desk http://127.0.0.1:{a.port} --desk-key {key_path}",
          file=sys.stderr, flush=True)
    try:
        serve_lab(app, sock)
    finally:
        stop.set()
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m tools.fake_desk")
    ap.add_argument("--port", type=int, default=PORT)
    ap.add_argument("--lab", action="store_true",
                    help="a practice Desk for a promoted Lab strategy: the real engine on simulated accounts")
    ap.add_argument("--ticks", default=None, help="--lab: the PRIVATE chart service whose prints fill the orders")
    ap.add_argument("--store", default=None, help="--lab: the Lab store (a temp folder; never ~/.homebase/desklab)")
    ap.add_argument("--resume", default=None, metavar="DIR", help="--lab: start again on this engine folder")
    a = ap.parse_args(argv)
    if a.port in FORBIDDEN_PORTS:
        ap.error(f"port {a.port} belongs to the real desk or the chart service")
    if a.lab:
        return lab_main(ap, a)
    if a.ticks or a.store or a.resume:
        ap.error("--ticks, --store and --resume go with --lab")
    key = write_key(state_dir() / KEY_FILE)
    uvicorn.run(create_fake_desk(key), host="127.0.0.1", port=a.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
