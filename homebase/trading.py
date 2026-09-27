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
     orders by id stays allowed in the window, so a manual order can always
     be cleared before the fire; while the bot is placing it is refused, and
     while it is placed|live only an order placed FROM THE CHART (its id
     remembered here) may be cancelled — a bot leg whose id the desk does
     not know must not be taken for a manual order. The bots' own orders
     are never modified or cancelled from the chart. A reverse re-checks
     guards 1 and 4 before its flatten and again before its open.
  3. quantity: 1..max_order_qty per order; the worst-case |net| in the
     contract (position + every working order on that side + chart orders
     the broker accepted in the last 10 s whose id the cache does not show
     — yet, or any more: one that filled before its position update counts
     again — + this order; an order of unknown side counts both ways)
     <= max_position_qty. A flatten also cancels those not-shown ids in its
     contract first (the adapter's symbol flatten only sees the cache).
  An account runs one action at a time (a per-account asyncio.Lock over its
  guards and broker calls), so two quick clicks cannot both pass guard 3 on
  the same stale cache; different accounts still run concurrently. An
  account pinned twice in config is refused on both. A journal write that
  fails after the broker accepted is reported as `journal_error` on an ok
  result, never as a failed order; any other error is journaled
  `manual_error`.
  6. prices: tick-rounded; a buy stop above / a sell stop below the last
     trade (a fresh quote from the chart service is required); bracket
     stop/target on the losing/winning side of the entry. A Stop Limit's
     trigger is checked like a stop; its limit sits on the fill-allowing side
     of the trigger, within 100 ticks; its SL sits beyond the trigger and
     its TP beyond the limit. A Market order is Day only.

Controller ruling (P2, 2026-09-26): the 09:30:00.000 bot fire runs on this
same asyncio loop. ChartDesk's periodic view refresh (`run`), its
refresh-after-push (`_on_entity` scheduling `flush` via `call_soon`) and the
view rebuild + publish that `flush` does are paused 09:29:50-09:30:30 ET on
weekdays, and also while ANY bot day state is `placing` (a broker ack is
outstanding on this same loop). Fill events still publish immediately
during the pause — `_on_entity` never rebuilds a view inline, so it stays
O(1) regardless of the pause; a slow listener would delay the adapter's
websocket reader. A settings change (`set_settings`: a disk write, a
rebuild and a publish) is refused in the same pause, except one whose only
effect is switching chart trading off. `disable()` (the desk's Kill) is
never paused: an emergency switch-off must always take effect immediately.

Guard 2 reads the adapter's pushed cache (`trade_view`), never the broker:
an account whose cache is missing or not seeded yet (the seed still
retrying after a (re)connect) is refused — never read as flat.
"""
from __future__ import annotations

import asyncio
import contextlib
import copy
import datetime as dt
import math
import re
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Callable, Optional

from . import bothistory
from . import config as config_mod
from . import symbols
from .broker.base import OrderRequest, OrderResult
from .config import (HARD_MAX_ORDER_QTY, HARD_MAX_POSITION_QTY, AppCfg,
                     ChartTradingCfg, assignments)
from .contracts import point_value, root_of, round_to_tick, spec_for, tick_size

LOCK_FROM, LOCK_UNTIL = dt.time(9, 20), dt.time(9, 35)
BOT_BUSY = ("placing", "placed", "live")
RATE_N, RATE_WINDOW_S = 5, 1.0
QUOTE_MAX_AGE_S = 30.0
QUOTE_MAX_FUTURE_S = 5.0          # a quote stamped further ahead than this is not trusted
RESERVE_S = 10.0                  # a chart order counts against the limit until the cache shows it
CHART_IDS_KEPT = 1000             # per account: order ids placed from the chart (positively manual)
FILLS_KEPT = 50
DEDUP_TTL_S = 600.0
SUB_QUEUE_MAX = 500
WATCH_S = 0.5
SIDES = ("Buy", "Sell")
TYPES = ("Market", "Limit", "Stop", "StopLimit")
TIFS = ("Day", "GTC")
STOPLIMIT_MAX_TICKS = 100       # a Stop Limit's limit sits at most this far from its trigger
_ROOT = re.compile(r"[A-Z0-9]{1,6}")
_ORDER_ID = re.compile(r"[0-9]{1,20}")

# Controller ruling P2: protect the 09:30:00.000 fire on the desk's single
# asyncio loop. View refresh (periodic + push-triggered) is paused in this
# narrow window, on weekdays, regardless of what else is going on.
VIEW_PAUSE_FROM, VIEW_PAUSE_UNTIL = dt.time(9, 29, 50), dt.time(9, 30, 30)
# bot-history (a journal parse in a thread) keeps clear of the fire for longer:
# a request started just before 09:29:50 must not still be parsing at 09:30
HISTORY_PAUSE_FROM = dt.time(9, 29)
SETTINGS_PAUSED = ("settings can't change 09:29:50–09:30:30 or while the bot is placing "
                   "— try again in a moment")


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


# --- request parsing (ValueError -> HTTP 400 in desk_api) --------------------------
def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _price(v, name: str, *, required: bool = False) -> Optional[float]:
    if v is None:
        if required:
            raise ValueError(f"{name} is required")
        return None
    if not _finite(v) or v <= 0:
        raise ValueError(f"{name}: a positive number")
    return float(v)


def _obj(body) -> dict:
    if not isinstance(body, dict):
        raise ValueError("the body is a JSON object")
    return body


def _client_id(body: dict) -> str:
    cid = body.get("client_id")
    if not isinstance(cid, str) or not 1 <= len(cid) <= 64:
        raise ValueError("client_id: a string of 1-64 characters")
    return cid


def _account(body: dict) -> str:
    a = body.get("account")
    if not isinstance(a, str) or not 1 <= len(a) <= 64:
        raise ValueError("account: an account id")
    return a


def _accounts(body: dict) -> tuple:
    a = body.get("accounts")
    if not isinstance(a, list) or not 1 <= len(a) <= 20 \
            or not all(isinstance(x, str) and 1 <= len(x) <= 64 for x in a):
        raise ValueError("accounts: a list of 1-20 account ids")
    return tuple(dict.fromkeys(a))                    # de-duplicated, order kept


def _root(body: dict) -> str:
    r = body.get("root")
    if not isinstance(r, str) or not _ROOT.fullmatch(r.upper()):
        raise ValueError("root: a symbol root such as NQ")
    return r.upper()


def _order_id(body: dict) -> str:
    o = body.get("order_id")
    if isinstance(o, int) and not isinstance(o, bool):
        o = str(o)
    if not isinstance(o, str) or not _ORDER_ID.fullmatch(o):
        raise ValueError("order_id: the broker's numeric order id")
    return o


@dataclass(frozen=True)
class OrderIntent:
    client_id: str
    accounts: tuple
    root: str
    side: str
    qty: int
    type: str
    price: Optional[float]
    sl_price: Optional[float]
    tp_price: Optional[float]
    trigger_price: Optional[float] = None     # StopLimit only; `price` is then its limit
    tif: str = "Day"


def parse_order(body) -> OrderIntent:
    body = _obj(body)
    side, typ, qty = body.get("side"), body.get("type"), body.get("qty")
    if side not in SIDES:
        raise ValueError("side: Buy or Sell")
    if typ not in TYPES:
        raise ValueError("type: Market, Limit, Stop or StopLimit")
    if isinstance(qty, bool) or not isinstance(qty, int):
        raise ValueError("qty: a whole number")
    price = _price(body.get("price"), "price", required=typ != "Market")
    if typ == "Market" and price is not None:
        raise ValueError("a Market order carries no price")
    if typ != "StopLimit" and body.get("trigger_price") is not None:
        raise ValueError("only a Stop Limit order carries a trigger_price")
    trigger = _price(body.get("trigger_price"), "trigger_price", required=typ == "StopLimit")
    tif = body.get("tif", "Day")
    if tif not in TIFS:
        raise ValueError("tif: Day or GTC")
    if typ == "Market" and tif != "Day":
        raise ValueError("a Market order is Day only")
    return OrderIntent(_client_id(body), _accounts(body), _root(body), side, qty, typ, price,
                       _price(body.get("sl_price"), "sl_price"),
                       _price(body.get("tp_price"), "tp_price"), trigger, tif)


def parse_modify(body) -> tuple:
    body = _obj(body)
    return (_client_id(body), _account(body), _order_id(body),
            _price(body.get("price"), "price", required=True))


def parse_cancel(body) -> tuple:
    body = _obj(body)
    return _client_id(body), _account(body), _order_id(body)


def parse_symbol_action(body) -> tuple:
    body = _obj(body)
    return _client_id(body), _accounts(body), _root(body)


# --- pure guards ---------------------------------------------------------------------
def in_lock_window(now_et: dt.datetime) -> bool:
    """09:20:00 <= t < 09:35:00 ET on a weekday. `now_et` is ET-aware
    (engine.now_et()), so DST is the zone's business, not ours."""
    return now_et.weekday() < 5 and LOCK_FROM <= now_et.time() < LOCK_UNTIL


def contract_matches(strategy_symbol: str, contract: str) -> bool:
    """engine.on_fill gives a fill to a strategy when the strategy's symbol
    is a SUBSTRING of the fill's contract (NQ claims MNQZ6). The lock uses
    the same rule, never a narrower one."""
    return bool(strategy_symbol) and strategy_symbol.upper() in str(contract or "").upper()


def fresh_quote(body: dict, root: str, now_s: float) -> Optional[dict]:
    """The chart service's latest quote for `root` (body["quotes"]), if its
    last trade is at most QUOTE_MAX_AGE_S old and at most QUOTE_MAX_FUTURE_S
    ahead of the desk's clock; else None."""
    qs = body.get("quotes") if isinstance(body, dict) else None
    q = qs.get(root) if isinstance(qs, dict) else None
    if not isinstance(q, dict):
        return None
    last, ts = q.get("last"), q.get("ts_ms")
    if not _finite(last) or not _finite(ts) or now_s - ts / 1000.0 > QUOTE_MAX_AGE_S \
            or ts / 1000.0 - now_s > QUOTE_MAX_FUTURE_S:
        return None
    return {"last": float(last),
            "bid": float(q["bid"]) if _finite(q.get("bid")) else None,
            "ask": float(q["ask"]) if _finite(q.get("ask")) else None}


def check_prices(side: str, typ: str, price, sl, tp, contract: str,
                 quote: Optional[dict], trigger=None) -> tuple:
    """Tick-round every price; refuse a stop on the wrong side of the last
    trade, and a bracket whose stop/target sit on the wrong side of the
    entry. A Stop Limit's trigger is checked like a stop; its limit (`price`)
    must be on the fill-allowing side of the trigger (buy: at or above,
    sell: at or below) and within STOPLIMIT_MAX_TICKS of it; its bracket's
    SL must sit beyond the TRIGGER (it may fill there) and its TP beyond the
    LIMIT. Returns (price, sl, tp, trigger) rounded."""
    def rnd(p):
        return None if p is None else round_to_tick(contract, p)

    price, sl, tp, trigger = rnd(price), rnd(sl), rnd(tp), rnd(trigger)
    last = quote["last"] if quote else None
    fresh = f"no trade in {contract} in the last {QUOTE_MAX_AGE_S:.0f} s"
    if typ == "Stop":
        if last is None:
            raise Refused(f"{fresh} — a stop order needs a fresh price")
        if side == "Buy" and price <= last:
            raise Refused(f"a buy stop must be above the last price ({last:,})")
        if side == "Sell" and price >= last:
            raise Refused(f"a sell stop must be below the last price ({last:,})")
    if typ == "StopLimit":
        if last is None:
            raise Refused(f"{fresh} — a stop limit order needs a fresh price")
        if side == "Buy" and trigger <= last:
            raise Refused(f"a buy stop limit's trigger must be above the last price ({last:,})")
        if side == "Sell" and trigger >= last:
            raise Refused(f"a sell stop limit's trigger must be below the last price ({last:,})")
        if side == "Buy" and price < trigger:
            raise Refused("a buy stop limit's limit must be at or above its trigger")
        if side == "Sell" and price > trigger:
            raise Refused("a sell stop limit's limit must be at or below its trigger")
        if round(abs(price - trigger) / tick_size(contract)) > STOPLIMIT_MAX_TICKS:
            raise Refused(f"a stop limit's limit must be within {STOPLIMIT_MAX_TICKS} ticks "
                          "of its trigger")
    if sl is not None or tp is not None:
        ref = price if typ != "Market" else last
        if ref is None:
            raise Refused(f"{fresh} — a bracket on a market order needs a fresh price")
        sign = 1 if side == "Buy" else -1
        if typ == "StopLimit" and sl is not None and not sign * (trigger - sl) > 0:
            # it may fill at the trigger, not the limit: an SL between the two
            # would sit on the wrong side of the market right after the fill
            raise Refused("the stop loss must be beyond the trigger price")
        if sl is not None and not sign * (ref - sl) > 0:
            raise Refused("the stop loss must be on the losing side of the entry")
        if tp is not None and not sign * (tp - ref) > 0:
            raise Refused("the target must be on the winning side of the entry")
    return price, sl, tp, trigger


def worst_net(view: dict, contract: str, side: str, qty: int, reserved=()) -> int:
    """Worst-case |net| in `contract` if this order AND every working order
    on its side fill. An OCO pair counts twice (conservative). `reserved`
    are chart orders the broker accepted that the cache does not show yet
    ({contract, side, qty}); they count like working orders. An order with
    an unknown side counts on BOTH sides (whichever grows |net|)."""
    net = sum(int(p.get("net") or 0) for p in view.get("positions", [])
              if p.get("symbol") == contract)
    legs = [(o.get("side"), int(o.get("qty") or 0)) for o in view.get("orders", [])
            if o.get("symbol") == contract]
    legs += [(r.get("side"), int(r.get("qty") or 0)) for r in reserved
             if r.get("contract") == contract]
    legs.append((side, qty))
    buys = sum(q for sd, q in legs if sd != "Sell")
    sells = sum(q for sd, q in legs if sd != "Buy")
    return max(abs(net + buys), abs(net - sells))


async def _call(coro) -> OrderResult:
    """A broker call whose raise is a failed result, never an exception."""
    try:
        return await coro
    except Exception as e:  # noqa: BLE001
        return OrderResult(ok=False, error=str(e))


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
        self._inflight: dict[tuple, asyncio.Future] = {}   # (action, client_id) -> running action
        self._locks: dict[str, tuple] = {}             # account -> (loop, asyncio.Lock)
        self._reserved: dict[str, list] = {}           # account -> accepted chart orders not yet cached
        self._chart_ids: dict[str, dict] = {}          # account -> ordered set of chart-placed ids
        self._fills: dict[str, deque] = {}             # account -> recent fill views
        self._subs: set[asyncio.Queue] = set()
        self._attached: dict[str, object] = {}
        self._last_ids: list | None = None
        self._last_acct: dict[str, dict] = {}
        self._last_bot: dict | None = None
        self._flush_soon = False
        self._journal_cache = bothistory.JournalCache()

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
            "tradable": (connected and bool(a.account_name) and not self._pinned_twice(aid)
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
                "killed": self.engine.killed_today(name),
                "accounts": {st.account: ({**state_view(st, s), "check_it": True}
                                          if self.engine.needs_check(st) else state_view(st, s))
                             for st in self.engine.day_states(name)},
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
    def views_paused(self) -> bool:
        """Public: desk_api's stream holds its serialization on this (P2)."""
        return self._views_paused()

    def history_paused(self) -> bool:
        """bot-history answers 503 from 09:29:00 to 09:30:30 ET on weekdays,
        and whenever the views are paused (a bot placing)."""
        now = self.engine.now_et()
        if now.weekday() < 5 and HISTORY_PAUSE_FROM <= now.time() < VIEW_PAUSE_UNTIL:
            return True
        return self._views_paused()

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
        ValueError (the page shows it) on anything malformed; nothing changes then.
        Inside the P2 pause (09:29:50-09:30:30 ET weekdays, or any bot
        `placing`) a change is refused unwritten and unpublished, except one
        whose only effect is switching chart trading off: like the Kill,
        that always applies at once."""
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
        switch_off_only = (not new.enabled and new.max_order_qty == ct.max_order_qty
                           and new.max_position_qty == ct.max_position_qty)
        if not switch_off_only and self._views_paused():
            raise ValueError(SETTINGS_PAUSED)
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

    # --- guards -------------------------------------------------------------------
    def _pinned_twice(self, aid: str) -> bool:
        """Two config accounts on the same login pinned to the same broker
        account: neither may trade from the chart (orders, limits and the
        bot lock are all per config account, so they would not add up)."""
        a = self.cfg.accounts.get(aid)
        if a is None or not a.account_name:
            return False
        key = (a.keyring_key, a.account_name.strip().lower())
        return sum(1 for b in self.cfg.accounts.values()
                   if (b.keyring_key, (b.account_name or "").strip().lower()) == key) > 1

    def _gate(self, aid: str) -> tuple:
        """Guards 1, 2 and 5. Returns (adapter, live view, label)."""
        if not self.cfg.chart_trading.enabled:
            raise Refused("chart trading is off — switch it on on the desk page")
        a = self.cfg.accounts.get(aid)
        if a is None:
            raise Refused(f"unknown account {aid!r}")
        label = self._label(aid)
        now = self._mono()
        hits = self._hits.setdefault(aid, deque())
        while hits and now - hits[0] >= RATE_WINDOW_S:
            hits.popleft()
        if len(hits) >= RATE_N:
            raise Refused(f"too fast — at most {RATE_N} actions a second on {label}")
        hits.append(now)
        if self._pinned_twice(aid):
            raise Refused(f"{label}: account pinned twice in config — chart trading refuses it")
        ad = self.adapters.get(aid)
        if ad is None or not ad.connected:
            err = (self.acct_status.get(aid) or {}).get("error")
            raise Refused(f"{label} is not connected" + (f" ({err})" if err else ""))
        if not a.account_name or not getattr(ad, "pinned_ok", False):
            raise Refused(f"{label} is not on its own pinned broker account — "
                          "chart trading refuses it")
        view = ad.trade_view()
        if not view or not view.get("seeded"):
            raise Refused(f"{label}'s positions are not loaded yet — try again in a moment")
        return ad, view, label

    def _contract(self, root: str) -> str:
        if not spec_for(root).known:
            raise Refused(f"{root} has no contract spec on the desk — not tradable from the chart")
        try:
            return symbols.resolve_contract(root)
        except ValueError as e:
            raise Refused(f"{root}: no front contract ({e})") from None

    def _day_state(self, aid: str, name: str):
        return next((s for s in self.engine.day_states_for_account(aid) if s.strategy == name), None)

    def _is_chart_order(self, aid: str, oid: str) -> bool:
        return str(oid) in self._chart_ids.get(aid, {})

    def _not_the_bots(self, aid: str, oid: str, label: str, name: str, status: str,
                      contract: Optional[str]) -> None:
        """While a bot is placed/live, its legs' ids may not be known to the
        desk: only an order placed FROM THE CHART is positively manual."""
        if not self._is_chart_order(aid, oid):
            where = f" in {contract}" if contract else ""
            raise Refused(f"order {oid} on {label} was not placed from the chart and the {name} "
                          f"bot is {status}{where} — it may be one of the bot's; "
                          "use the desk's Kill in an emergency")

    def _lock(self, aid: str, contract: str, label: str, *, cancel_oid: Optional[str] = None) -> None:
        """Guard 4. A cancel by id (`cancel_oid`) skips the window, but while
        a matching bot is placing it is refused, and while it is placed/live
        it is allowed only for an order placed from the chart."""
        for name, s in self.cfg.strategies.items():
            if not contract_matches(s.symbol, contract):
                continue
            st = self._day_state(aid, name)
            if st is not None and st.status in BOT_BUSY:
                if cancel_oid is None or st.status == "placing":
                    raise Refused(f"{contract} on {label} belongs to the {name} bot right now "
                                  f"({st.status}) — use the desk's Kill in an emergency")
                self._not_the_bots(aid, cancel_oid, label, name, st.status, contract)
            if cancel_oid is not None:
                continue
            if in_lock_window(self.engine.now_et()) \
                    and any(r.get("account") == aid for r in assignments(self.cfg, name)):
                raise Refused(f"{contract} on {label} is locked 09:20-09:35 ET for the {name} bot")

    @staticmethod
    def _unresolved(view: dict) -> None:
        if any(p.get("symbol") is None for p in view.get("positions", [])) \
                or any(o.get("symbol") is None for o in view.get("orders", [])):
            raise Refused("a position or order's contract is not resolved yet — try again in a moment")

    def _not_bot_order(self, aid: str, oid: str) -> None:
        owner = self._bot_orders(aid).get(oid)
        if owner:
            raise Refused(f"order {oid} belongs to the {owner} bot — it cannot be changed from the chart")

    def _now_s(self) -> float:
        return self.engine.now_et().timestamp()

    # --- reservations: accepted chart orders the cache does not show yet -------------------
    def _kept_reservations(self, aid: str) -> list:
        """Every accepted chart order of the last RESERVE_S (older ones dropped)."""
        now = self._mono()
        keep = [r for r in self._reserved.get(aid, []) if now - r["t"] < RESERVE_S]
        self._reserved[aid] = keep
        return keep

    @staticmethod
    def _shown(view: dict) -> set:
        return {str(o.get("order_id")) for o in view.get("orders", [])}

    def _reservations(self, aid: str, view: dict) -> list:
        """The reservations that COUNT: kept the full RESERVE_S, counted only
        while the cache does not show their order id. Shown, the cached order
        counts instead; gone again (it filled before its position update
        came in), the reservation counts again rather than the order
        vanishing from the limit for a moment."""
        shown = self._shown(view)
        return [r for r in self._kept_reservations(aid)
                if r["order_id"] is None or r["order_id"] not in shown]

    def _placed(self, aid: str, contract: str, side: str, qty: int, r: OrderResult) -> None:
        """After the broker's ok: reserve the qty and remember the ids as
        positively manual. Never raises — the order is already at the broker."""
        try:
            raw = r.raw if isinstance(r.raw, dict) else {}
            known = self._chart_ids.setdefault(aid, {})
            for i in (r.order_id, raw.get("sl_order_id"), raw.get("tp_order_id")):
                if i:
                    known[str(i)] = None
            while len(known) > CHART_IDS_KEPT:
                known.pop(next(iter(known)))
            self._reserved.setdefault(aid, []).append(
                {"order_id": str(r.order_id) if r.order_id else None, "contract": contract,
                 "side": side, "qty": qty, "t": self._mono(),
                 "ids": [str(i) for i in (r.order_id, raw.get("sl_order_id"),
                                          raw.get("tp_order_id")) if i]})
        except Exception as e:  # noqa: BLE001
            _log(f"{aid}: reservation bookkeeping failed: {type(e).__name__}: {e}")

    def _acct_lock(self, aid: str):
        """One action at a time per account: its guards and broker calls see
        a settled account (a second click waits, then counts the first's
        reservation). Different accounts still run concurrently."""
        if aid not in self.cfg.accounts:
            return contextlib.nullcontext()          # refused by _gate at once; no lock to grow
        loop = asyncio.get_running_loop()
        held = self._locks.get(aid)
        if held is None or held[0] is not loop:
            held = self._locks[aid] = (loop, asyncio.Lock())
        return held[1]

    # --- bookkeeping ------------------------------------------------------------------
    def _dedup(self, action: str, cid: str) -> Optional[dict]:
        now = self._mono()
        for k in [k for k, (t, _) in self._done.items() if now - t > DEDUP_TTL_S]:
            del self._done[k]
        hit = self._done.get((action, cid))
        return hit[1] if hit else None

    async def _once(self, action: str, cid: str, work) -> dict:
        """Run `work()` once per (action, client_id): a repeat gets the first
        result, and a repeat that arrives while the first is still at the
        broker (a double click, a proxy retry) waits for it instead of
        placing again. Shielded: a caller that goes away does not cancel an
        action already at the broker."""
        hit = self._dedup(action, cid)
        if hit is not None:
            return hit
        key = (action, cid)
        task = self._inflight.get(key)
        if task is None:
            task = asyncio.ensure_future(work())
            self._inflight[key] = task
            task.add_done_callback(lambda _t, key=key: self._inflight.pop(key, None))
        return await asyncio.shield(task)

    def _finish(self, action: str, cid: str, results: dict) -> dict:
        out = {"results": results}
        self._done[(action, cid)] = (self._mono(), out)
        self.publish("result", {"client_id": cid, "action": action, **out})
        return out

    def _jsafe(self, event: str, **data) -> Optional[str]:
        """Journal; a failed write is returned (and logged), never raised —
        it must not turn an order the broker accepted into a 'failure'."""
        try:
            self.engine.journal(event, **data)
            return None
        except Exception as e:  # noqa: BLE001
            _log(f"journal {event} failed: {type(e).__name__}: {e}")
            return f"{type(e).__name__}: {e}"

    @staticmethod
    def _result(ok: bool, order_id, error, jerr: Optional[str]) -> dict:
        out = {"ok": ok, "order_id": order_id, "error": error}
        if jerr:
            out["journal_error"] = jerr
        return out

    def _refuse(self, action: str, cid: str, aid: str, reason: str) -> dict:
        jerr = self._jsafe("manual_refused", source="chart", action=action, client_id=cid,
                           account=aid, reason=reason)
        return {**self._result(False, None, reason, jerr), "refused": True}

    async def _one(self, action: str, cid: str, aid: str, fn) -> dict:
        """One account's part of an action, under that account's lock. A
        guard's Refused -> manual_refused; anything else -> manual_error."""
        try:
            async with self._acct_lock(aid):
                return await fn()
        except Refused as e:
            return self._refuse(action, cid, aid, str(e))
        except Exception as e:  # noqa: BLE001
            msg = f"internal error: {type(e).__name__}: {e}"
            jerr = self._jsafe("manual_error", source="chart", action=action, client_id=cid,
                               account=aid, error=msg)
            return self._result(False, None, msg, jerr)

    @staticmethod
    def _gathered(accounts: tuple, outs: list) -> dict:
        return {aid: (o if isinstance(o, dict) else
                      {"ok": False, "order_id": None, "error": f"internal error: {o}"})
                for aid, o in zip(accounts, outs)}

    # --- order ------------------------------------------------------------------------
    async def order(self, body) -> dict:
        it = parse_order(body)

        async def work():
            quote = fresh_quote(body, it.root, self._now_s())
            outs = await asyncio.gather(
                *(self._one("order", it.client_id, aid,
                            lambda aid=aid: self._order_one(it, aid, quote))
                  for aid in it.accounts), return_exceptions=True)
            return self._finish("order", it.client_id, self._gathered(it.accounts, outs))

        return await self._once("order", it.client_id, work)

    async def _order_one(self, it: OrderIntent, aid: str, quote: Optional[dict]) -> dict:
        ad, view, label = self._gate(aid)
        contract = self._contract(it.root)
        self._lock(aid, contract, label)
        lim = self.cfg.chart_trading
        if not 1 <= it.qty <= lim.max_order_qty:
            raise Refused(f"quantity must be 1-{lim.max_order_qty}")
        self._unresolved(view)
        worst = worst_net(view, contract, it.side, it.qty, self._reservations(aid, view))
        if worst > lim.max_position_qty:
            raise Refused(f"that could take {contract} on {label} to {worst} contracts "
                          f"(limit {lim.max_position_qty})")
        price, sl, tp, trigger = check_prices(it.side, it.type, it.price, it.sl_price,
                                              it.tp_price, contract, quote,
                                              trigger=it.trigger_price)
        req = OrderRequest(symbol=contract, side=it.side, qty=it.qty, order_type=it.type,
                           price=price, stop_price=sl, tp_price=tp, text="homebase:chart",
                           trigger_price=trigger, time_in_force=it.tif)
        bracket = sl is not None or tp is not None
        r = await _call(ad.place_bracket(req) if bracket else ad.place_order(req))
        if r.ok:
            self._placed(aid, contract, it.side, it.qty, r)
        jerr = self._jsafe("manual_order", source="chart", client_id=it.client_id, account=aid,
                           root=it.root, contract=contract, side=it.side, qty=it.qty,
                           type=it.type, price=price, trigger=trigger, tif=it.tif,
                           sl=sl, tp=tp, ok=r.ok,
                           order_id=r.order_id, error=r.error)
        return self._result(r.ok, r.order_id, r.error, jerr)

    # --- modify / cancel (one account, one order) ---------------------------------------
    def _find_order(self, view: dict, oid: str, label: str) -> dict:
        o = next((o for o in view.get("orders", []) if str(o.get("order_id")) == oid), None)
        if o is None:
            raise Refused(f"order {oid} is not working on {label}")
        return o

    async def modify(self, body) -> dict:
        cid, aid, oid, price = parse_modify(body)

        async def work():
            res = await self._one("modify", cid, aid,
                                  lambda: self._modify(body, cid, aid, oid, price))
            return self._finish("modify", cid, {aid: res})

        return await self._once("modify", cid, work)

    async def _modify(self, body, cid: str, aid: str, oid: str, price: float) -> dict:
        ad, view, label = self._gate(aid)
        o = self._find_order(view, oid, label)
        self._not_bot_order(aid, oid)
        contract = o.get("symbol")
        if not contract:
            raise Refused("that order's contract is not resolved yet — try again in a moment")
        self._lock(aid, contract, label)      # a busy bot refuses EVERY modify in its contract
        typ = o.get("type")
        if typ == "StopLimit":
            raise Refused("Stop Limit orders can't be moved — cancel and place again")
        if typ not in ("Limit", "Stop"):
            raise Refused(f"only Limit and Stop orders can be moved (this one is {typ})")
        px = round_to_tick(contract, price)
        if typ == "Stop":
            check_prices(o.get("side"), "Stop", px, None, None, contract,
                         fresh_quote(body, root_of(contract), self._now_s()))
        r = await _call(ad.modify_order(oid, typ,
                                        price=px if typ == "Limit" else None,
                                        stop_price=px if typ == "Stop" else None,
                                        qty=int(o.get("qty") or 0) or None))
        jerr = self._jsafe("manual_modify", source="chart", client_id=cid, account=aid,
                           order_id=oid, contract=contract, type=typ, price=px,
                           ok=r.ok, error=r.error)
        return self._result(r.ok, oid, r.error, jerr)

    async def cancel(self, body) -> dict:
        cid, aid, oid = parse_cancel(body)

        async def work():
            res = await self._one("cancel", cid, aid, lambda: self._cancel(cid, aid, oid))
            return self._finish("cancel", cid, {aid: res})

        return await self._once("cancel", cid, work)

    async def _cancel(self, cid: str, aid: str, oid: str) -> dict:
        ad, view, label = self._gate(aid)
        o = self._find_order(view, oid, label)
        self._not_bot_order(aid, oid)
        contract = o.get("symbol")
        if contract:
            self._lock(aid, contract, label, cancel_oid=oid)
        else:                                  # unknown contract: any busy bot may own it
            busy = [s for s in self.engine.day_states_for_account(aid) if s.status in BOT_BUSY]
            if any(s.status == "placing" for s in busy):
                raise Refused("a bot is placing on this account — try again in a second")
            if busy:
                self._not_the_bots(aid, oid, label, busy[0].strategy, busy[0].status, None)
        r = await _call(ad.cancel_order_by_id(oid))
        jerr = self._jsafe("manual_cancel", source="chart", scope="order", client_id=cid,
                           account=aid, order_id=oid, contract=contract, ok=r.ok, error=r.error)
        return self._result(r.ok, oid, r.error, jerr)

    # --- the bots: history and the per-strategy Kill -------------------------------------------
    def _strategy(self, name) -> str:
        if not isinstance(name, str) or name not in self.cfg.strategies:
            raise ValueError(f"unknown strategy {name!r}")
        return name

    async def bot_history(self, strategy, days=None) -> dict:
        """GET /api/trade/bot-history: the strategy's past runs from the
        journal (homebase.bothistory). The read AND the rebuild run in a
        thread, so the desk's loop (the 9:30 fire) never waits on them."""
        name, n = self._strategy(strategy), bothistory.parse_days(days)
        symbol = self.cfg.strategies[name].symbol
        today = self.engine.now_et().date().isoformat()
        path = self.engine.journal_path

        def build():
            recs = self._journal_cache.records(path)
            return bothistory.runs(recs, name, symbol=symbol, today=today, days=n)

        return {"strategy": name, "symbol": symbol, "runs": await asyncio.to_thread(build)}

    async def bot_kill(self, body) -> dict:
        """POST /api/trade/bot-kill {client_id, strategy}: kill ONE strategy
        for today (engine.kill_strategy: its own orders and its own contract
        on its own accounts). Not the desk's Kill: the desk stays armed,
        chart trading stays on, other strategies keep running. Never gated
        by chart trading or paused (an emergency stop); idempotent per
        client_id. -> {ok, results: {account: {...}}}"""
        body = _obj(body)
        cid = _client_id(body)
        name = self._strategy(body.get("strategy"))

        async def work():
            try:
                results = await self.engine.kill_strategy(name, source="chart", client_id=cid)
                out = {"ok": all(r.get("ok") for r in results.values()), "results": results}
            except Exception as e:  # noqa: BLE001 — the kill mark is already set in memory
                _log(f"bot-kill {name}: {type(e).__name__}: {e}")
                out = {"ok": False, "results": {}, "error": f"internal error: {type(e).__name__}: {e}"}
            self._done[("bot-kill", cid)] = (self._mono(), out)
            self.publish("result", {"client_id": cid, "action": "bot-kill", **out})
            return out

        return await self._once("bot-kill", cid, work)

    # --- per-symbol actions (many accounts) -------------------------------------------------
    async def _per_symbol(self, action: str, body, fn) -> dict:
        cid, accounts, root = parse_symbol_action(body)

        async def work():
            outs = await asyncio.gather(
                *(self._one(action, cid, aid,
                            lambda aid=aid: self._symbol_one(cid, aid, root, fn))
                  for aid in accounts), return_exceptions=True)
            return self._finish(action, cid, self._gathered(accounts, outs))

        return await self._once(action, cid, work)

    async def _symbol_one(self, cid: str, aid: str, root: str, fn) -> dict:
        ad, view, label = self._gate(aid)
        contract = self._contract(root)
        self._lock(aid, contract, label)
        return await fn(cid, aid, ad, view, contract, label)

    async def cancel_symbol(self, body) -> dict:
        return await self._per_symbol("cancel-symbol", body, self._do_cancel_symbol)

    async def flatten(self, body) -> dict:
        return await self._per_symbol("flatten", body, self._do_flatten)

    async def reverse(self, body) -> dict:
        return await self._per_symbol("reverse", body, self._do_reverse)

    async def _do_cancel_symbol(self, cid, aid, ad, view, contract, label) -> dict:
        r = await _call(ad.cancel_symbol(contract))
        jerr = self._jsafe("manual_cancel", source="chart", scope="symbol", client_id=cid,
                           account=aid, contract=contract, ok=r.ok, error=r.error,
                           cancelled=(r.raw or {}).get("cancelled"))
        return self._result(r.ok, None, r.error, jerr)

    async def _do_flatten(self, cid, aid, ad, view, contract, label) -> dict:
        """The adapter's symbol flatten cancels what the cache shows; a chart
        order the broker accepted in the last RESERVE_S whose id (or bracket
        leg id) the cache does not show would survive it and could fill
        after. Those are cancelled first; a failed cancel (e.g. it already
        filled — the flatten's own position read then covers it) never stops
        the flatten."""
        shown = self._shown(view)
        pending = list(dict.fromkeys(
            i for rv in self._kept_reservations(aid) if rv["contract"] == contract
            for i in rv.get("ids", ()) if i not in shown))
        cancels = {}
        if pending:
            outs = await asyncio.gather(*(_call(ad.cancel_order_by_id(i)) for i in pending))
            cancels = {i: {"ok": c.ok, "error": c.error} for i, c in zip(pending, outs)}
        r = await _call(ad.flatten_symbol(contract))
        extra = {"reserved_cancels": cancels} if cancels else {}
        jerr = self._jsafe("manual_flatten", source="chart", client_id=cid, account=aid,
                           contract=contract, ok=r.ok, error=r.error, detail=r.raw, **extra)
        return self._result(r.ok, None, r.error, jerr)

    def _still_allowed(self, aid: str, contract: str, label: str, done: str) -> None:
        """Re-run guards 1 and 4 between a reverse's awaits: the desk's Kill
        or the 09:20 lock may have landed while the broker answered."""
        if not self.cfg.chart_trading.enabled:
            raise Refused(f"chart trading was switched off during the reverse — {done}")
        try:
            self._lock(aid, contract, label)
        except Refused as e:
            raise Refused(f"{e} — {done}") from None

    async def _do_reverse(self, cid, aid, ad, view, contract, label) -> dict:
        if any(r["contract"] == contract for r in self._reservations(aid, view)):
            raise Refused(f"an order sent from the chart in {contract} on {label} is not "
                          "confirmed yet — try again in a moment")
        try:
            net = await ad.get_net_position(contract)
        except Exception as e:  # noqa: BLE001 — unreadable is not flat
            raise Refused(f"the {contract} position on {label} is unreadable ({e}) — nothing done") from None
        if not net:
            raise Refused(f"no {contract} position on {label} to reverse")
        lim = self.cfg.chart_trading
        if abs(net) > lim.max_order_qty or abs(net) > lim.max_position_qty:
            raise Refused(f"reversing {abs(net)} is over the per-order limit ({lim.max_order_qty})")
        self._still_allowed(aid, contract, label, "nothing done")
        f = await _call(ad.flatten_symbol(contract))
        jerr = self._jsafe("manual_reverse", source="chart", step="flatten", client_id=cid,
                           account=aid, contract=contract, net_before=net, ok=f.ok, error=f.error)
        if not f.ok:
            return self._result(False, None, f"flatten failed: {f.error} — not reversed", jerr)
        self._still_allowed(aid, contract, label, "flattened only")
        side = "Sell" if net > 0 else "Buy"
        r = await _call(ad.place_order(OrderRequest(symbol=contract, side=side, qty=abs(net),
                                                    order_type="Market",
                                                    text="homebase:chart-reverse")))
        if r.ok:
            self._placed(aid, contract, side, abs(net), r)
        jerr = self._jsafe("manual_reverse", source="chart", step="open", client_id=cid,
                           account=aid, contract=contract, side=side, qty=abs(net), ok=r.ok,
                           order_id=r.order_id, error=r.error) or jerr
        return self._result(r.ok, r.order_id, r.error, jerr)
