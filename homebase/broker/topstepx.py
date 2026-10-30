"""TopstepX (Topstep) adapter: one desk account on one TopstepX login.

Every entry that has a stop carries it ON the entry order (`stopLoss` / `takeProfit`, in ticks from the fill), never as a
later separate order, so a position cannot exist without its stop. The answer and field shapes below come from the site's
code and are NOT yet confirmed against the live API: each guess is a named constant or one small function.

One TsxSession and one account socket (TsxHub) serve every adapter on a login: the first adapter to connect starts the hub,
the last one to close stops it, and each event / reconnect is fanned out to every adapter listed on the session.

An order whose call timed out or dropped after sending is NEVER sent again: it is looked up by its customTag and reported as
found, or as outcome unknown.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import math
import time
import uuid
from collections import deque
from typing import Optional

import httpx

from .. import symbols
from ..contracts import root_of
from .base import AccountNotOnLogin, BrokerAdapter, FillCallback, FillEvent, OrderRequest, OrderResult
from .login_budget import LoginDeferred
from .topstepx_auth import TsxSession
from .topstepx_ws import TsxHub

log = logging.getLogger(__name__)

CODES = {"NQ": "ENQ", "MNQ": "MNQ", "ES": "EP", "MES": "MES", "GC": "GCE", "MGC": "MGC"}
TICK = {"NQ": .25, "MNQ": .25, "ES": .25, "MES": .25, "GC": .1, "MGC": .1}
TYPE = {"Limit": 1, "Market": 2, "StopLimit": 3, "Stop": 4}
BRACKET_UNIT = {"type": 0}                              # 0 = ticks (1 = dollars)
PRACTICE_PREFIXES = ("PRAC",)                           # unconfirmed: a practice account's name starts like this
ACCOUNTS_PATH = "/TradingAccount"
ORDERS_PATH = "/Order/account/{account_id}"             # unconfirmed shape: the timeout lookup by customTag
POSITIONS_PATH = "/Position/all/account/{account_id}"
CANCEL_ONE = "/Order/cancel/{account_id}/id/{order_id}"
CANCEL_ALL = "/Order/cancel/{account_id}/all"
CLOSE_ALL = "/Position/close/{account_id}"
CLOSE_ONE = "/Position/close/{account_id}/contract/{contract_id}"
ACTION_METHOD = "POST"                                  # unconfirmed verb of the cancel / close calls
BALANCE_FIELD = "balance"                               # unconfirmed
TRADES_PATH = "/Trade/id/{account_id}"                  # unconfirmed: the account's trades (today's)
ROOTS = {code: root for root, code in CODES.items()}    # contract id code -> root
TRADE_SIDE = {0: "Buy", 1: "Sell"}                      # unconfirmed (ProjectX): a trade row's `side`
POSITION_TYPE = {1: 1, 2: -1}                           # unconfirmed (ProjectX): a position row's `type`: long / short
VIOLATIONS = ("RealTimeTradingAccountViolation", "RealTimeRiskSettingsLockout")
_SEEN_FILL_CAP = 20000


class _Refused(Exception):
    """A request refused before any network call."""


def _json(resp: httpx.Response):
    try:
        return resp.json()
    except ValueError:
        return None


def _rows(ans, key: str) -> list:
    if isinstance(ans, list):
        return ans
    inner = ans.get(key) if isinstance(ans, dict) else None
    return inner if isinstance(inner, list) else []


def _order_answer(ans: dict) -> tuple[bool, Optional[str], Optional[str]]:
    """(ok, order id, error). Unconfirmed shape: ok when `result` is 0 or `success` is true AND an id comes back. An answer
    that is neither ok nor carries an error is ambiguous: the caller looks the order up."""
    oid = ans.get("orderId") if ans.get("orderId") is not None else ans.get("id")
    accepted = ans.get("result") == 0 or ans.get("success") is True
    if accepted and oid is not None:
        return True, str(oid), None
    err = ans.get("errorMessage")
    refused = ans.get("success") is False or ans.get("result") not in (None, 0)
    return False, None, str(err) if err else ("order refused" if refused else None)


def _refusal(resp: httpx.Response) -> Optional[str]:
    """Why a cancel / close call was not accepted (None = accepted)."""
    ans = _json(resp)
    err = ans.get("errorMessage") if isinstance(ans, dict) else None
    if resp.status_code >= 400:
        return f"HTTP {resp.status_code}" + (f": {err}" if err else "")
    if isinstance(ans, dict) and (ans.get("success") is False or ans.get("result") not in (None, 0)):
        return str(err or "refused")
    return None


def _snap(root: str, px: float) -> float:
    t = TICK[root]
    return round(round(px / t) * t, 6)


def _whole(v) -> int:
    """A whole number from a row field; anything else raises (a size we cannot read is never 0)."""
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v != int(v):
        raise ValueError("not a whole number")
    return int(v)


def _net_of(row) -> int:
    """Signed net of a position row (a push or a REST row; the ONE place that reads its shape). A row it cannot read RAISES:
    unreadable is never flat."""
    if not isinstance(row, dict):
        raise ValueError("position row unreadable")
    kind = row.get("type")
    if kind in POSITION_TYPE and row.get("size") is not None:     # a direction plus an unsigned size
        n = _whole(row["size"])
        if n < 0:
            raise ValueError("position size contradicts its type")
        return POSITION_TYPE[kind] * n
    signed = row.get("positionSize") if row.get("positionSize") is not None else row.get("size")
    if signed is None:
        raise ValueError("position row has no size")
    n = _whole(signed)
    if kind is not None and row.get("positionSize") is None and n:    # a type that is not long / short: `size` is not signed
        raise ValueError("position direction unreadable")
    return n


def _trade_fields(arg) -> Optional[dict]:
    """The fields of a trade row (a push or a REST row; the ONE place that reads its shape). None = a voided trade.
    A row it cannot read RAISES."""
    if not isinstance(arg, dict):
        raise ValueError("trade row unreadable")
    if arg.get("voided"):
        return None
    tid, cid, side = arg.get("id"), arg.get("contractId"), TRADE_SIDE.get(arg.get("side"))
    size, price = _whole(arg.get("size")), arg.get("price")
    if not isinstance(tid, (int, str)) or isinstance(tid, bool) or not cid or side is None or size < 1:
        raise ValueError("trade row unreadable")
    if price is not None:
        price = float(price)
    return {"id": tid, "accountId": arg.get("accountId"), "contractId": str(cid), "price": price, "size": size,
            "side": side, "creationTimestamp": arg.get("creationTimestamp")}


def _code_of(contract_id: str) -> str:
    """The market code of CON.F.US.<code>.<mY> ("" when the id is not of that shape)."""
    p = str(contract_id).split(".")
    return p[3] if len(p) >= 5 and p[:3] == ["CON", "F", "US"] else ""


def _same(a, b) -> bool:
    return a is not None and b is not None and str(a) == str(b)


class TopstepXAdapter(BrokerAdapter):
    platform = "topstepx"

    def __init__(self, account_id: str, *, keyring_key: str, account_name: str, session: TsxSession, live: bool = False):
        super().__init__(account_id, live=live)
        self.keyring_key = keyring_key
        self.account_name = account_name                # "" = probe: connect + list_accounts only, no orders, no socket
        self.session = session
        self.journal = lambda event, **kw: None         # the desk sets it later
        self._all: list[dict] = []
        self._acct_id = None
        self._acct_row: dict = {}
        self._on_fill: Optional[FillCallback] = None
        self._pos: dict[str, int] = {}                  # contract id -> net, THIS account only
        self._pos_ok = False                            # the book was read whole from the broker and pushes kept it since
        self._pos_pushed: set = set()                   # contracts pushed while a seed read was in flight
        self._seen: set = set()                         # trade ids already delivered (or in the seeded history)
        self._seen_order: deque = deque(maxlen=_SEEN_FILL_CAP)
        self._trades_seeded = False                     # the first on_up seeds the seen-set and delivers nothing
        self._out: deque = deque(maxlen=1000)           # FillEvents waiting for the callback, oldest first
        self._pump: Optional[asyncio.Task] = None
        self._balance = None
        self._violation: Optional[str] = None

    @property
    def broker_key(self):
        return ("topstepx", self._acct_id) if self._acct_id is not None else self.account_id

    # ------------------------------------------------------------ lifecycle
    async def connect(self) -> None:
        await self.session.token()
        self._all = await self._read(ACCOUNTS_PATH, "accounts")
        if not self.account_name:
            self._connected = True
            return
        want = self.account_name.lower()
        row = next((a for a in self._all if str(a.get("name", "")).lower() == want), None)
        if row is None:
            self._connected, self._acct_id, self._acct_row, self.pinned_ok = False, None, {}, False
            if not self._all:               # an empty list is not proof the account is gone
                raise RuntimeError(f"{self.account_id}: login exposes no accounts")
            have = [str(a.get("name") or a.get("id")) for a in self._all]
            err = AccountNotOnLogin(f"account {self.account_name} not on this login (has: {', '.join(have)})")
            err.listed, err.user_id = have, self.session.user_id
            raise err
        self._acct_id, self._acct_row, self.pinned_ok, self._connected = row.get("id"), row, True, True
        s = self.session
        joined = self not in s.listeners
        if joined:
            s.listeners.append(self)
        if s.hub is None:
            s.hub = TsxHub(s, _fan_events(s), on_up=_fan_up(s), on_auth_lost=_session_taken(s))
            await s.hub.start()
        elif joined and getattr(s.hub, "up", False):
            await self._on_up()         # the socket is already open: its on_up will not run for this late joiner

    async def close(self) -> None:
        """Leaves the login: the socket stops with its last listener, the session is never closed here."""
        self._connected = False
        s = self.session
        if self in s.listeners:
            s.listeners.remove(self)
        if not s.listeners and s.hub is not None:
            hub, s.hub = s.hub, None
            await hub.stop()

    async def observe_fills(self, on_fill: FillCallback) -> None:
        self._on_fill = on_fill
        self._kick()                                    # fills that came before the callback was set

    # ------------------------------------------------------------ the socket's pushes
    def _on_event(self, target: str, arg: dict) -> None:
        """One pushed event from the shared socket (sync, from the hub's reader)."""
        if self._acct_id is None or not isinstance(arg, dict):
            return
        s = self.session
        if target == "RealTimeSession":
            # NOT acted on (it may arrive on every connect, and acting would loop logins): keys only, once per login.
            if s.listeners[:1] == [self]:
                log.info("topstepx %s: session event", s.key)
                s.journal("tsx_session_event", keys=sorted(arg))
        elif target in VIOLATIONS:
            if arg.get("accountId") is None or _same(arg["accountId"], self._acct_id):    # unsure whose: it is ours
                self._violation = target
                log.warning("topstepx %s: %s", self.account_id, target)
                self._journal("tsx_violation", kind=target, keys=sorted(arg))
        elif target == "RealTimeAccount":
            if _same(arg.get("id"), self._acct_id) and BALANCE_FIELD in arg:
                self._balance = arg[BALANCE_FIELD]
        elif target == "RealTimePosition":
            self._on_position(arg)
        elif target == "RealTimeTrade":
            self._on_trade(arg)
        elif target == "RealTimeOrder":
            if _same(arg.get("accountId"), self._acct_id):
                self._notify("order", arg)

    def _on_position(self, arg: dict) -> None:
        if arg.get("accountId") is not None and not _same(arg["accountId"], self._acct_id):
            return
        try:
            if arg.get("accountId") is None:
                raise ValueError("no account")
            cid, net = str(arg["contractId"]), _net_of(arg)
        except Exception as e:  # noqa: BLE001 -- we cannot tell what changed: the next read goes to the broker
            self._pos_ok = False
            log.warning("topstepx %s: position push unreadable (%s)", self.account_id, type(e).__name__)
            self._journal("tsx_position_unreadable", keys=sorted(arg))
            return
        self._pos[cid] = net
        self._pos_pushed.add(cid)
        self._notify("position", arg)

    def _on_trade(self, arg: dict) -> None:
        try:
            t = _trade_fields(arg)
            if t is None or not _same(t["accountId"], self._acct_id):    # voided, another account's, or not provably ours
                return
            if not self._take(t, arg):      # position_after stays None until the spike shows whether a trade push
                return              # comes before or after its position push (a cached net could be one fill stale)
        except Exception as e:  # noqa: BLE001 -- the next on_up reads the account's trades and finds it
            log.warning("topstepx %s: trade push unreadable (%s)", self.account_id, type(e).__name__)
            self._journal("tsx_trade_unreadable", keys=sorted(arg))
            return
        self._notify("fill", arg)
        self._kick()

    def _mark_seen(self, tid) -> bool:
        """Record a trade id; True if it was not seen before."""
        if tid in self._seen:
            return False
        if len(self._seen_order) == self._seen_order.maxlen:
            self._seen.discard(self._seen_order[0])
        self._seen_order.append(tid)
        self._seen.add(tid)
        return True

    def _take(self, t: dict, row: dict) -> bool:
        """Queue a trade for the fill callback unless it was already seen (True = queued)."""
        if not self._mark_seen(t["id"]):
            return False
        code = _code_of(t["contractId"])
        self._out.append(FillEvent(account_id=self.account_id, symbol=ROOTS.get(code) or code or t["contractId"],
                                   side=t["side"], qty=t["size"], price=t["price"], ts=time.time(), raw=dict(row),
                                   seen=time.perf_counter()))
        return True

    def _kick(self) -> Optional[asyncio.Task]:
        """Start delivering queued fills, oldest first, one at a time."""
        if self._on_fill is None or not self._out:
            return None
        if self._pump is None or self._pump.done():
            try:
                self._pump = asyncio.get_running_loop().create_task(self._drain())
            except RuntimeError:
                return None
        return self._pump

    async def _drain(self) -> None:
        while self._out and self._on_fill is not None:
            ev = self._out.popleft()
            try:
                await self._on_fill(ev)
            except Exception as e:  # noqa: BLE001 -- one failing callback must not stop the fills behind it
                log.warning("topstepx %s: fill callback failed (%s)", self.account_id, type(e).__name__)

    async def _on_up(self) -> None:
        """The shared socket opened (first time or again). Never raises into the hub."""
        if self._acct_id is None:
            return
        self._pos_ok = False                            # not trusted until the fresh read below returns
        try:
            await self._seed_positions()                # a fresh book after every open: pushes may have been missed
        except Exception as e:  # noqa: BLE001
            self._pos_ok = False
            log.warning("topstepx %s: positions not read on open (%s)", self.account_id, self._words(e))
        try:
            rows = await self._read(TRADES_PATH.format(account_id=self._acct_id), "trades")
        except Exception as e:  # noqa: BLE001
            log.warning("topstepx %s: trades not read on open (%s)", self.account_id, self._words(e))
            return
        found, bad = [], 0
        for row in rows:
            try:
                t = _trade_fields(row)
            except Exception:  # noqa: BLE001
                bad += 1
                continue
            if t is not None and (t["accountId"] is None or _same(t["accountId"], self._acct_id)):
                found.append((t, row))
        if bad:
            log.warning("topstepx %s: %d trade rows unreadable", self.account_id, bad)
            self._journal("tsx_trade_unreadable", rows=bad)
        if not self._trades_seeded:         # the day's history is not "outside fills": remember it, deliver nothing
            for t, _ in found:
                self._mark_seen(t["id"])
            self._trades_seeded = True
            return
        found.sort(key=lambda p: (str(p[0]["creationTimestamp"] or ""), str(p[0]["id"]).zfill(20)))
        for t, row in found:
            if self._take(t, row):      # position_after unknown: the book holds the net AFTER all of them
                self._notify("fill", row)
        pump = self._kick()
        if pump is not None:
            await pump

    async def _seed_positions(self) -> dict:
        """Read the whole book from the broker into the cache (a push that lands during the read wins over the read)."""
        self._pos_pushed = set()
        book: dict[str, int] = {}
        for p in await self._read(POSITIONS_PATH.format(account_id=self._acct_id), "positions"):
            cid = str(p.get("contractId", "")) if isinstance(p, dict) else ""
            if not cid:
                raise ValueError("position row has no contract")
            book[cid] = book.get(cid, 0) + _net_of(p)
        for cid in self._pos_pushed:
            book[cid] = self._pos[cid]
        self._pos, self._pos_ok = book, True
        return book

    def _hub_up(self) -> bool:
        h = self.session.hub
        return h is not None and getattr(h, "up", True)

    # ------------------------------------------------------------ accounts and contracts
    def list_accounts(self) -> list[dict]:
        return [{"id": a.get("id"), "name": a.get("name") or str(a.get("id")), "active": a.get("active", True),
                 "practice": str(a.get("name", "")).upper().startswith(PRACTICE_PREFIXES)} for a in self._all]

    def contract_id(self, symbol: str, today: Optional[dt.date] = None) -> str:
        """CON.F.US.<code>.<letter><yy> for a root's front month (or for an explicit contract like NQH27)."""
        s = str(symbol or "").strip().upper()
        root = root_of(s)
        if root not in CODES:
            raise ValueError(f"topstepx: unknown market {symbol!r}")
        if s != root:
            _, month, year = symbols.parse_tradovate_symbol(s)
        else:
            month = symbols.CODE_TO_MONTH[symbols.front_month(root, today)[len(root)]]
            now = today or dt.date.today()
            year = now.year + (month < now.month)       # the front month is never in the past
        return f"CON.F.US.{CODES[root]}.{symbols.MONTH_TO_CODE[month]}{year % 100:02d}"

    async def _read(self, path: str, key: str) -> list:
        """A GET that must be readable: a failed read raises (an unreadable list is not an empty one)."""
        resp = await self.session.request("GET", path)
        if resp.status_code >= 400:
            raise RuntimeError(f"topstepx: {path.split('?')[0]} answered HTTP {resp.status_code}")
        ans = _json(resp)
        if not isinstance(ans, (list, dict)):
            raise RuntimeError(f"topstepx: {path} answer unreadable")
        return _rows(ans, key)

    # ------------------------------------------------------------ orders
    def _build(self, req: OrderRequest, *, bracket: bool) -> dict:
        """The POST /Order body, or _Refused before anything is sent."""
        root = root_of(req.symbol)
        if root not in CODES:
            raise _Refused(f"topstepx: unknown market {req.symbol!r}")
        side = {"buy": 1, "sell": -1}.get(str(req.side).lower())
        if side is None or req.qty < 1:
            raise _Refused(f"topstepx: bad side / qty {req.side!r} {req.qty!r}")
        ot = req.order_type
        if ot not in TYPE:
            raise _Refused(f"topstepx: unknown order type {ot!r}")
        body = {"accountId": self._acct_id, "contractId": self.contract_id(req.symbol), "type": TYPE[ot],
                "positionSize": side * req.qty, "customTag": f"{req.text}:{uuid.uuid4().hex[:12]}"}
        if ot == "Limit":
            level = {"limitPrice": req.price}
        elif ot == "StopLimit":
            level = {"limitPrice": req.price, "stopPrice": req.trigger_price}
        elif ot == "Stop":     # a stop entry's trigger is its price; a bare protective Stop carries it in stop_price
            level = {"stopPrice": req.price if bracket or req.stop_price is None else req.stop_price}
        else:
            level = {}
        if any(v is None for v in level.values()):
            raise _Refused(f"topstepx: a {ot.lower()} order needs a price")
        body.update({k: _snap(root, v) for k, v in level.items()})
        if not bracket:
            return body
        ref = req.trigger_price if ot == "StopLimit" else req.price
        if ref is None:
            raise _Refused(f"topstepx: a bracketed {ot.lower()} entry needs a price")
        for key, name, level_px, want in (("stopLoss", "stop", req.stop_price, -1), ("takeProfit", "target", req.tp_price, 1)):
            if level_px is None:
                continue
            if (level_px - ref) * side * want <= 0:     # a stop sits against the trade, a target with it
                raise _Refused(f"topstepx: the {name} {level_px} is on the wrong side of the entry {ref}")
            ticks = math.ceil(abs(level_px - _snap(root, ref)) / TICK[root] - 1e-9)
            body[key] = {"ticks": max(1, ticks), **BRACKET_UNIT}
        return body

    async def place_order(self, req: OrderRequest) -> OrderResult:
        return await self._place(req, bracket=False)

    async def place_bracket(self, req: OrderRequest) -> OrderResult:
        """Entry + stop / target as ONE order: TopstepX places the protection with the fill."""
        if req.stop_price is None and req.tp_price is None:
            return await self.place_order(req)
        return await self._place(req, bracket=True)

    async def _place(self, req: OrderRequest, *, bracket: bool) -> OrderResult:
        if self._acct_id is None:
            return OrderResult(ok=False, error="adapter not connected")
        try:
            body = self._build(req, bracket=bracket)
        except _Refused as e:
            return OrderResult(ok=False, error=str(e))
        extra = {"sl_order_id": None, "tp_order_id": None, "bracket": "attached"} if bracket else {}
        tag = body["customTag"]
        if self.live:
            log.info("topstepx %s: LIVE %s %s %s", self.account_id, "BRACKET" if bracket else "ORDER", req.side,
                     body["contractId"])
        try:
            await self.session.token()      # a login failure is before the send
        except Exception as e:  # noqa: BLE001
            return OrderResult(ok=False, error=f"topstepx: no session before sending: {self._words(e)}")
        try:
            resp = await self.session.request("POST", "/Order", json=body)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as e:     # never reached TopstepX
            return OrderResult(ok=False, error=f"topstepx: order not sent: {self._words(e)}")
        except Exception as e:  # noqa: BLE001 -- a timeout or a drop after the send: it may be working
            return await self._lost(tag, extra, self._words(e))
        ans = _json(resp)
        if resp.status_code >= 500 or (resp.status_code < 400 and not isinstance(ans, dict)):
            return await self._lost(tag, extra, f"HTTP {resp.status_code}")
        if not isinstance(ans, dict):
            return OrderResult(ok=False, error=f"topstepx: order refused (HTTP {resp.status_code})")
        ok, oid, err = _order_answer(ans)
        if ok:
            return OrderResult(ok=True, order_id=oid, raw={**ans, **extra})
        if err is None:
            return await self._lost(tag, extra, "answer neither accepted nor refused")
        return OrderResult(ok=False, error=f"topstepx: {self._clean(err)[:200]}", raw=ans)

    async def _lost(self, tag: str, extra: dict, why: str) -> OrderResult:
        """The order may be at TopstepX: look it up by its customTag. Never resend."""
        found = None
        try:
            for o in await self._read(ORDERS_PATH.format(account_id=self._acct_id), "orders"):
                if isinstance(o, dict) and o.get("customTag") == tag:
                    oid = o.get("id") if o.get("id") is not None else o.get("orderId")
                    found = None if oid is None else str(oid)
                    break
        except Exception as e:  # noqa: BLE001 -- a failed lookup is unknown
            why = f"{why}; lookup failed: {self._words(e)}"
        self._journal("tsx_order_after_error", tag=tag, found=found, why=why)
        log.warning("topstepx %s: order %s after %s", self.account_id, "found" if found else "NOT found", why)
        if found:
            return OrderResult(ok=True, order_id=found, raw={"found_by_tag": True, **extra})
        return OrderResult(ok=False, raw={"outcome_unknown": True, "custom_tag": tag},
                           error=f"topstepx: order outcome unknown ({why}): it may be working, check the orders "
                                 "before sending again")

    # ------------------------------------------------------------ cancel / flatten
    async def _act(self, path: str, what: str) -> OrderResult:
        if self._acct_id is None:
            return OrderResult(ok=False, error="adapter not connected")
        try:
            resp = await self.session.request(ACTION_METHOD, path)
        except Exception as e:  # noqa: BLE001
            return OrderResult(ok=False, error=f"topstepx: {what} failed: {self._words(e)}")
        why = _refusal(resp)
        if why:
            return OrderResult(ok=False, error=f"topstepx: {what} refused: {self._clean(why)[:200]}")
        ans = _json(resp)
        return OrderResult(ok=True, raw=ans if isinstance(ans, dict) else {})

    async def cancel_order_by_id(self, order_id: str) -> OrderResult:
        try:
            oid = int(order_id)
        except (TypeError, ValueError):
            return OrderResult(ok=False, error=f"topstepx: bad order id {order_id!r}")
        return await self._act(CANCEL_ONE.format(account_id=self._acct_id, order_id=oid), f"cancel {oid}")

    async def cancel_all(self) -> OrderResult:
        return await self._act(CANCEL_ALL.format(account_id=self._acct_id), "cancel all")

    async def flatten_all(self) -> OrderResult:
        return await self._act(CLOSE_ALL.format(account_id=self._acct_id), "flatten")

    async def flatten_symbol(self, symbol: str) -> OrderResult:
        """Close what is HELD in the market (an older contract after a roll too), as the broker lists it."""
        if self._acct_id is None:
            return OrderResult(ok=False, error="adapter not connected")
        try:
            held = [cid for cid, n in await self._held(symbol, fresh=True) if n]    # what the broker holds NOW
        except Exception as e:  # noqa: BLE001
            return OrderResult(ok=False, error=f"topstepx: positions unreadable: {self._words(e)}")
        errors, n = [], 0
        for cid in held:
            r = await self._act(CLOSE_ONE.format(account_id=self._acct_id, contract_id=cid), f"flatten {cid}")
            if r.ok:
                n += 1
            else:
                errors.append(r.error)
        return OrderResult(ok=not errors, error="; ".join(errors) or None, raw={"flattened": n})

    # ------------------------------------------------------------ reads
    async def _held(self, symbol: str, *, fresh: bool = False) -> list[tuple[str, int]]:
        """[(contract id, signed size)] of this account's positions in the symbol's market (a root = every month).
        From the socket-kept cache once it was read whole and the socket is up; else (or `fresh`) from the broker."""
        s = str(symbol or "").strip().upper()
        root = root_of(s)
        if root not in CODES:
            raise ValueError(f"topstepx: unknown market {symbol!r}")
        prefix = f"CON.F.US.{CODES[root]}."
        exact = None if s == root else self.contract_id(s)
        book = self._pos if (self._pos_ok and not fresh and self._hub_up()) else await self._seed_positions()
        return [(cid, n) for cid, n in book.items() if ((cid == exact) if exact else cid.startswith(prefix))]

    async def get_net_position(self, symbol: str) -> int:
        """Net position in the symbol's market. RAISES when it cannot be read: unreadable is not flat."""
        if self._acct_id is None:
            raise RuntimeError("adapter not connected")
        return sum(n for _, n in await self._held(symbol))

    async def get_balance(self) -> dict:
        if self._acct_id is None:
            return {}
        try:
            for a in await self._read(ACCOUNTS_PATH, "accounts"):
                if a.get("id") == self._acct_id:
                    self._balance = a.get(BALANCE_FIELD)
                    return {"amount": self._balance}
        except Exception:  # noqa: BLE001
            pass
        return {}

    async def get_metrics(self) -> dict:
        """No broker request here (the dashboard polls it): the numbers come from what the socket and reads already left."""
        m = await super().get_metrics()
        m["account"] = self._acct_row.get("name") or None
        m["balance"] = self._balance if self._balance is not None else self._acct_row.get(BALANCE_FIELD)
        m["positions_known"] = self._pos_ok
        if self._pos_ok:
            by_root: dict[str, int] = {}
            for cid, n in self._pos.items():
                if n:
                    code = _code_of(cid)
                    root = ROOTS.get(code) or code or cid
                    by_root[root] = by_root.get(root, 0) + n
            m["open_positions"] = [{"symbol": r, "net": n} for r, n in by_root.items() if n]
            m["open_position_count"] = len(m["open_positions"])
        m["session_taken"] = self.session.taken
        m["tsx_violation"] = self._violation
        return m

    # ------------------------------------------------------------ helpers
    def _clean(self, text: str) -> str:
        tok = getattr(self.session, "_token", None)
        return text.replace(tok, "***") if tok else text

    def _words(self, e: Exception) -> str:
        return self._clean(f"{type(e).__name__}: {e}".rstrip(": "))[:200]

    def _journal(self, event: str, **kw) -> None:
        try:
            self.journal(event, account=self.account_id, **kw)
        except Exception as e:  # noqa: BLE001 -- a journal failure never stops an order path
            log.warning("topstepx %s: journal failed (%s)", self.account_id, type(e).__name__)


def _fan_events(session: TsxSession):
    def on_event(target: str, arg: dict) -> None:
        for a in list(session.listeners):
            try:
                a._on_event(target, arg)
            except Exception as e:  # noqa: BLE001 -- one account's failure must not starve the others
                log.warning("topstepx %s: event %s failed (%s)", a.account_id, target, type(e).__name__)
    return on_event


DEFER_PAUSE_S = 60.0        # after a refused login the handler waits this long, so the hub's retries are paced


async def _pause(seconds: float) -> None:       # tests shorten the wait here
    await asyncio.sleep(seconds)


def _session_taken(session: TsxSession):
    """The login's ONE handler for 'TopstepX ended this session' (the hub calls it on a socket 401 at open): one kick = one
    count, one journal line, at most one login (through the budget). It runs inside the hub's own task, so it never stops the
    hub. It takes the session's login lock, so a REST call that re-logs in at the same moment cannot make a second login:
    if the token was already replaced, the kick is counted and no login is sent. A refused login (LoginDeferred) is
    remembered by the token it was refused for: the hub's next refusal with that same token only asks the budget again (no
    count, no journal line) after a pause."""
    deferred: Optional[str] = None

    async def taken() -> None:
        nonlocal deferred
        hub = session.hub
        refused = getattr(hub, "_token", "") or session._token      # the token the socket was refused with
        wait = False
        async with session._lock:                   # relogin() itself takes no lock
            again = refused == deferred
            names = [a.account_name for a in list(session.listeners)]
            if not again:
                session.taken += 1
                session.journal("tsx_session_taken", accounts=names, count=session.taken)
            if session._token != refused:           # another path already logged in
                deferred = None
                return
            try:
                await session.relogin("taken")
                deferred = None
            except LoginDeferred as e:
                deferred, wait = refused, True
                log.warning("topstepx %s: session taken, login deferred", session.key)
                if not again:
                    session.journal("tsx_session_taken", accounts=names, count=session.taken, deferred=str(e))
            except Exception as e:  # noqa: BLE001 -- the hub logs it; the journal gets the class only (no text)
                session.journal("tsx_session_taken", accounts=names, count=session.taken, failed=type(e).__name__)
                raise
        if wait:
            await _pause(DEFER_PAUSE_S)
    return taken


def _fan_up(session: TsxSession):
    async def on_up() -> None:
        for a in list(session.listeners):
            try:
                await a._on_up()
            except Exception as e:  # noqa: BLE001
                log.warning("topstepx %s: on_up failed (%s)", a.account_id, type(e).__name__)
    return on_up
