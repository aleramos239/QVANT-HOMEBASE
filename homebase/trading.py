"""Trading from the chart — the desk-side half.

Spec: docs/superpowers/specs/2026-09-26-desk-on-chart-trading-design.md

The chart page asks through the chart service; only the desk talks to the
broker. ChartDesk keeps a live view per account (from the adapters' pushed
caches: no broker call), a view of the bots, and publishes changes to the
SSE stream (desk_api). Every order, modify, cancel, flatten and reverse
starts from a user's click, passes the guards below (authoritative — the
page's checks are a convenience) and is journaled with its result as a
manual_* event. Those events never carry a "strategy" key, so the bots'
live metrics (metrics.py) never count them.

Guards, per account (a refusal is one sentence the page shows as-is):
  1. chart trading is enabled (config chart_trading.enabled, default off;
     the desk's Kill switches it off)
  2. the account exists, is connected, sits on its own pinned broker
     account (adapter.pinned_ok) and its position cache is loaded
  5. at most 5 actions a second per account (checked right after the
     account exists, before any broker work)
  4. the bot lock: an account booked to a strategy whose symbol matches the
     contract (the engine's own substring rule: NQ also claims MNQ) is
     locked 09:20-09:35 ET on weekdays; any account whose day state for
     that strategy is placing|placed|live is locked. Cancelling one of YOUR
     orders by id stays allowed (except while the bot is placing), so a
     manual order can always be cleared before the fire; the bots' own
     orders are never modified or cancelled from the chart.
  3. quantity: 1..max_order_qty per order; the worst-case |net| in the
     contract (position + every working order on that side + this order)
     <= max_position_qty
  6. prices: tick-rounded; a buy stop above / a sell stop below the last
     trade (a fresh quote from the chart service is required); bracket
     stop/target on the losing/winning side of the entry.

Controller ruling (P2, 2026-09-26): the 09:30:00.000 bot fire runs on this
same asyncio loop. ChartDesk's periodic view refresh (`run`), its
refresh-after-push (`_on_entity` scheduling `flush` via `call_soon`) and the
view rebuild + publish that `flush` does are paused 09:29:50-09:30:30 ET on
weekdays, and also while ANY bot day state is `placing` (a broker ack is
outstanding on this same loop). Fill events still publish immediately
during the pause — `_on_entity` never rebuilds a view inline, so it stays
O(1) regardless of the pause; a slow listener would delay the adapter's
websocket reader. `disable()` (the desk's Kill) is never paused: an
emergency switch-off must always take effect immediately.
"""
from __future__ import annotations

import asyncio
import copy
import datetime as dt
import math
import re
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Callable, Optional

from . import config as config_mod
from . import symbols
from .broker.base import OrderRequest, OrderResult
from .config import (HARD_MAX_ORDER_QTY, HARD_MAX_POSITION_QTY, AppCfg,
                     ChartTradingCfg, assignments)
from .contracts import point_value, root_of, round_to_tick, spec_for

LOCK_FROM, LOCK_UNTIL = dt.time(9, 20), dt.time(9, 35)
BOT_BUSY = ("placing", "placed", "live")
RATE_N, RATE_WINDOW_S = 5, 1.0
QUOTE_MAX_AGE_S = 30.0
FILLS_KEPT = 50
DEDUP_TTL_S = 600.0
SUB_QUEUE_MAX = 500
WATCH_S = 0.5
SIDES = ("Buy", "Sell")
TYPES = ("Market", "Limit", "Stop")
_ROOT = re.compile(r"[A-Z0-9]{1,6}")
_ORDER_ID = re.compile(r"[0-9]{1,20}")

# Controller ruling P2: protect the 09:30:00.000 fire on the desk's single
# asyncio loop. View refresh (periodic + push-triggered) is paused in this
# narrow window, on weekdays, regardless of what else is going on.
VIEW_PAUSE_FROM, VIEW_PAUSE_UNTIL = dt.time(9, 29, 50), dt.time(9, 30, 30)


def _log(msg: str) -> None:
    print(f"[trading] {msg}", file=sys.stderr, flush=True)


class Refused(Exception):
    """A guard said no. str(e) is the one sentence the page shows as-is."""


def state_view(st, s) -> dict:
    """One bot day state for the chart: status, the two entry triggers and
    the SL/TP the desk is working. A straddle measures them from the anchor,
    or from the average fill once its brackets were moved
    (engine._move_brackets); a bars rule has absolute levels."""
    sign = {"Buy": 1, "Sell": -1}.get(st.entry_side or "", 0)
    sl = tp = None
    if st.sl_px is not None or st.tp_px is not None:
        sl, tp = st.sl_px, st.tp_px
    elif sign and st.entry_anchor is not None:
        base = st.entry_fill if (st.brackets_moved and st.entry_fill is not None) \
            else st.entry_anchor
        sl = round_to_tick(s.symbol, base - sign * s.sl_pts)
        tp = round_to_tick(s.symbol, base + sign * s.tp_pts)
    return {"status": st.status, "qty": st.qty, "upper": st.upper_px, "lower": st.lower_px,
            "entry_side": st.entry_side, "entry_fill": st.entry_fill,
            "entry_qty": st.entry_qty, "sl": sl, "tp": tp, "exit_fill": st.exit_fill,
            "exit_reason": st.exit_reason, "pnl": st.pnl, "note": st.note}


# --- request parsing + pure guards (added in Task 4) ---


class ChartDesk:
    def __init__(self, cfg: AppCfg, engine, adapters: dict, acct_status: dict, *,
                 timer_status: Callable[[], dict] | None = None,
                 save: Callable[[AppCfg], None] | None = None,
                 mono: Callable[[], float] = time.monotonic):
        self.cfg, self.engine, self.adapters, self.acct_status = cfg, engine, adapters, acct_status
        self.timer_status = timer_status or (lambda: {"date": None, "strategies": {}})
        self._save = save or config_mod.save
        self._mono = mono
        self._hits: dict[str, deque] = {}              # account -> recent action times
        self._done: dict[tuple, tuple[float, dict]] = {}   # (action, client_id) -> (t, result)
        self._fills: dict[str, deque] = {}             # account -> recent fill views
        self._subs: set[asyncio.Queue] = set()
        self._attached: dict[str, object] = {}
        self._last_ids: list | None = None
        self._last_acct: dict[str, dict] = {}
        self._last_bot: dict | None = None
        self._flush_soon = False

    # --- pub/sub ------------------------------------------------------------
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=SUB_QUEUE_MAX)
        self._subs.add(q)
        return q

    def unsubscribe(self, q) -> None:
        self._subs.discard(q)

    def publish(self, event: str, data: dict) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait((event, data))
            except asyncio.QueueFull:
                # a reader this far behind is dropped with an end marker; it
                # reconnects and starts again from a fresh state
                self._subs.discard(q)
                while not q.empty():
                    q.get_nowait()
                q.put_nowait((None, None))

    def publish_state(self) -> None:
        snap = self.snapshot()
        self._last_ids = list(self.cfg.accounts)
        self._last_acct = {v["id"]: v for v in snap["accounts"]}
        self._last_bot = snap["bot"]
        self.publish("state", snap)

    # --- views ----------------------------------------------------------------
    def _label(self, aid: str) -> str:
        a = self.cfg.accounts.get(aid)
        return (a.label or a.account_name or aid) if a else aid

    def _bot_orders(self, aid: str) -> dict[str, str]:
        """order id -> strategy, for every order a bot placed on this account today."""
        out: dict[str, str] = {}
        for st in self.engine.day_states_for_account(aid):
            for i in (st.upper_id, st.lower_id, st.up_sl_id, st.up_tp_id, st.dn_sl_id, st.dn_tp_id):
                if i:
                    out[str(i)] = st.strategy
        return out

    def _booked(self, aid: str) -> list[str]:
        return [n for n in self.cfg.strategies
                if any(r.get("account") == aid for r in assignments(self.cfg, n))]

    def account_view(self, aid: str) -> dict:
        a = self.cfg.accounts[aid]
        ad = self.adapters.get(aid)
        lv = (ad.trade_view() if ad is not None else None) or {}
        bot = self._bot_orders(aid)
        connected = bool(ad is not None and ad.connected)
        return {
            "id": aid, "label": self._label(aid), "pinned": a.account_name,
            "broker_account": lv.get("broker_account"), "env": "live" if a.live else "demo",
            "connected": connected, "error": (self.acct_status.get(aid) or {}).get("error"),
            "tradable": (connected and bool(a.account_name)
                         and bool(getattr(ad, "pinned_ok", False)) and bool(lv.get("seeded"))),
            "balance": lv.get("balance"), "realized_pnl": lv.get("realized_pnl"),
            "positions": [{**p, "root": root_of(p["symbol"]) if p.get("symbol") else None,
                           "point_value": point_value(p["symbol"]) if p.get("symbol") else None}
                          for p in lv.get("positions", [])],
            "orders": [{**o, "owner": bot.get(str(o.get("order_id")))}
                       for o in lv.get("orders", [])],
            "fills": list(self._fills.get(aid, ())),
            "strategies": self._booked(aid),
        }

    def bot_view(self) -> dict:
        ts = self.timer_status() or {}
        out = {}
        for name, s in self.cfg.strategies.items():
            rows = assignments(self.cfg, name)
            if not rows:
                continue
            out[name] = {
                "symbol": s.symbol, "kind": s.kind, "enabled": s.enabled, "shadow": s.shadow,
                "offset_pts": s.offset_pts, "sl_pts": s.sl_pts, "tp_pts": s.tp_pts,
                "book": {r["account"]: int(r["qty"]) for r in rows},
                # a copy: the timer mutates its own dict, and flush() compares views
                "timer": copy.deepcopy((ts.get("strategies") or {}).get(name)),
                "day_status": self.engine.day_status(name),
                "accounts": {st.account: state_view(st, s) for st in self.engine.day_states(name)},
            }
        return {"date": ts.get("date"), "strategies": out}

    def snapshot(self) -> dict:
        ct = self.cfg.chart_trading
        return {"enabled": ct.enabled,
                "limits": {"max_order_qty": ct.max_order_qty,
                           "max_position_qty": ct.max_position_qty},
                "accounts": [self.account_view(a) for a in self.cfg.accounts],
                "bot": self.bot_view()}

    # --- controller ruling P2: protect the 9:30 fire from view work ------------
    def _views_paused(self) -> bool:
        """True while view refresh must yield the loop to the bot fire: the
        narrow window around 09:30:00 ET on weekdays, or while any bot day
        state (any strategy, any account) is `placing` — a broker ack is
        outstanding on this same loop. Cheap: a wall-clock compare plus a
        scan of today's day states (bounded by the strategy/account count)."""
        now = self.engine.now_et()
        if now.weekday() < 5 and VIEW_PAUSE_FROM <= now.time() < VIEW_PAUSE_UNTIL:
            return True
        return any(st.status == "placing"
                   for name in self.cfg.strategies
                   for st in self.engine.day_states(name))

    # --- change detection ------------------------------------------------------
    def flush(self) -> None:
        """Publish what changed since the last flush: the full state when the
        account list changed, else one `account` event per changed account
        and a `bot` event when the bot view changed. Nothing when nobody
        listens, and nothing while the 9:30 fire is protected (P2) — no view
        is rebuilt or serialized then; the next flush after the pause picks
        up whatever changed in the meantime."""
        self._flush_soon = False
        if not self._subs or self._views_paused():
            return
        if list(self.cfg.accounts) != self._last_ids:
            self.publish_state()
            return
        for aid in self.cfg.accounts:
            v = self.account_view(aid)
            if v != self._last_acct.get(aid):
                self._last_acct[aid] = v
                self.publish("account", v)
        b = self.bot_view()
        if b != self._last_bot:
            self._last_bot = b
            self.publish("bot", b)

    def _safe_flush(self) -> None:
        try:
            self.flush()
        except Exception as e:  # noqa: BLE001 — views must never take the desk down
            _log(f"flush: {type(e).__name__}: {e}")

    async def run(self, interval_s: float = WATCH_S) -> None:
        """Publish what the pushes do not announce (connection state, the
        bots' day states, the timer): in-memory reads, twice a second."""
        while True:
            self._safe_flush()
            await asyncio.sleep(interval_s)

    def attach(self, aid: str, ad) -> None:
        """Listen to one adapter's pushes (called on every (re)connect; idempotent)."""
        if self._attached.get(aid) is ad:
            return
        self._attached[aid] = ad
        ad.add_listener(lambda et, ent, aid=aid: self._on_entity(aid, et, ent))

    def _fill_view(self, aid: str, ent: dict) -> dict:
        ad = self.adapters.get(aid)
        cid = ent.get("contractId")
        oid = ent.get("orderId")
        oid = str(oid) if oid is not None else None
        return {"id": ent.get("id"), "order_id": oid,
                "symbol": ad.contract_name(cid) if (ad is not None and cid is not None) else None,
                "side": ent.get("action"), "qty": ent.get("qty"), "price": ent.get("price"),
                "time": ent.get("timestamp"),
                "owner": self._bot_orders(aid).get(oid) if oid else None}

    def _on_entity(self, aid: str, et: str, ent: dict) -> None:
        """The adapter's push listener: O(1), never rebuilds a view inline
        (P2) — a slow listener here delays the adapter's websocket reader.
        A fill is recorded and published straight away, cheaply; everything
        else only marks a flush pending (`call_soon`, run on a later tick of
        the loop, itself a no-op while `_views_paused()`)."""
        if et == "fill":
            fv = self._fill_view(aid, ent)
            self._fills.setdefault(aid, deque(maxlen=FILLS_KEPT)).append(fv)
            self.publish("fill", {"account": aid, "fill": fv})
        if not self._flush_soon:
            try:
                asyncio.get_running_loop().call_soon(self._safe_flush)
                self._flush_soon = True
            except RuntimeError:            # no running loop: the watch loop catches up
                pass

    # --- settings (the desk page) ----------------------------------------------
    def set_settings(self, body) -> dict:
        """{enabled?, max_order_qty?, max_position_qty?} -> the new settings.
        ValueError (the page shows it) on anything malformed; nothing changes then."""
        if not isinstance(body, dict):
            raise ValueError("the body is a JSON object")
        ct = self.cfg.chart_trading
        new = ChartTradingCfg(enabled=ct.enabled, max_order_qty=ct.max_order_qty,
                              max_position_qty=ct.max_position_qty)
        if "enabled" in body:
            if not isinstance(body["enabled"], bool):
                raise ValueError("enabled: true or false")
            new.enabled = body["enabled"]
        for k, hi in (("max_order_qty", HARD_MAX_ORDER_QTY),
                      ("max_position_qty", HARD_MAX_POSITION_QTY)):
            if k in body:
                v = body[k]
                if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= hi:
                    raise ValueError(f"{k}: a whole number 1-{hi}")
                setattr(new, k, v)
        self.cfg.chart_trading = new
        self._save(self.cfg)
        self.engine.journal("chart_trading_set", **asdict(new))
        self.publish_state()
        return asdict(new)

    def disable(self, cause: str) -> None:
        """Switch chart trading off (the desk's Kill). Never raises: the kill
        must finish; the flag is off in memory before anything can fail. Never
        paused by P2 either — an emergency switch-off always takes effect and
        is always announced, fire window or not."""
        self.cfg.chart_trading.enabled = False
        try:
            self._save(self.cfg)
        except Exception as e:  # noqa: BLE001
            _log(f"chart trading is off, but the config save failed: {e}")
        try:
            self.engine.journal("chart_trading_set", enabled=False, cause=cause)
            self.publish_state()
        except Exception as e:  # noqa: BLE001
            _log(f"disable: {type(e).__name__}: {e}")

    # --- actions: guards + order/modify/cancel/cancel-symbol/flatten/reverse (added in Task 4) ---
