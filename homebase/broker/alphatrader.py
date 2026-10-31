"""AlphaTrader (Alpha Futures) adapter: one desk account on one AlphaTrader login, traded over the CTS T4 socket.

One AtrSession and one AtrSocket serve every adapter on a login: the first adapter to connect makes the socket
(`session.socket`), the last one to close stops it, and each event / reconnect is fanned out to every adapter listed on
`session.adapters`; each adapter keeps only the events of its own `accountId`. The login's accounts (from loginResponse and
accountDetails) are kept on `session.accounts`, the resolved T4 markets on `session.markets`.

The caches (positions per marketId, orders per uniqueId, the balance) are seeded by the account's `accountSnapshot` and kept
by the pushes. Unknown is never flat: while the snapshot has not come, the socket is down or a fill's position has not landed,
`get_net_position` raises.

Built offline from the site's code: every guessed value below is a named constant marked `# unconfirmed`, so the read-only
spike's corrections touch this block only.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import logging
import math
import numbers
import re
import uuid
from decimal import ROUND_CEILING, ROUND_FLOOR
from typing import Optional

from .. import symbols
from ..contracts import root_of
from . import alphatrader_proto as proto
from .alphatrader_auth import AtrSession
from .alphatrader_ws import AtrSocket
from .base import AccountNotOnLogin, BrokerAdapter, FillCallback, OrderRequest, OrderResult

log = logging.getLogger(__name__)

EXCHANGE = {"NQ": "CME_Eq", "MNQ": "CME_Eq", "ES": "CME_Eq", "MES": "CME_Eq", "GC": "CME_CO", "MGC": "CME_CO"}
TICK = {"NQ": .25, "MNQ": .25, "ES": .25, "MES": .25, "GC": .1, "MGC": .1}
# Booking a strategy onto an AlphaTrader account is refused until the owner lifts this, after the read-only check and the
# first watched order (how the bracket legs report is unconfirmed until then).
ATR_BOOKING_OPEN = False
ATR_BOOKING_CLOSED = "AlphaTrader accounts can't be booked yet: waiting for the read-only check and the first watched order"
STOP_GRACE_S = 2.0              # after a fill, the order update of its stop leg has this long to show up
ATR_FLATTEN_IF_NO_STOP = False  # True: a position with no working stop seen after the grace is closed (after the spike)
ORDER_WAIT_S = 5.0              # an order's answer (its orderUpdate by ClOrdId) is awaited this long, never resent
CONNECT_WAIT_S = 15.0           # connect() waits this long for the socket to log in
PRACTICE_MODES: tuple = ()                          # unconfirmed: account `mode` values that mark an evaluation account
PRACTICE_WORDS = ("eval", "practice")               # unconfirmed: words in the display or group name of an evaluation account
SYMBOLS_PATH = "/api/v1/market/symbols/"
SYM_ROWS_FIELD = "results"                          # unconfirmed: the rows (the site reads `results`, or the answer is a list)
SYM_ROOT_FIELD = "contract_id"                      # unconfirmed: a row's root ("NQ"), as the site's symbol tabs name it
SYM_EXCHANGE_FIELD = "exchange_id"                  # unconfirmed: checked when the row has it
SYM_MARKET_FIELD = "market_id"                      # unconfirmed: the T4 marketId
SYM_MONTH_FIELDS = ("market_id", "name", "symbol")  # unconfirmed: text naming the month as <letter><yy>, e.g. "XCME_Eq NQ (Z26)"
# The socket's own all-accounts subscribe, sent again: unconfirmed that T4 answers it with every account's snapshot (a
# repeated snapshot is harmless to an adapter already seeded).
RESUBSCRIBE = {"subscribe": proto.ALL_UPDATES, "subscribeAllAccounts": True, "uplMode": proto.AVERAGE}
DIRTY_RESYNC_S = 5.0            # a market still dirty this long asks for the snapshots again, once per dirty episode
POS_ROOT_FIELD = "contractId"                       # unconfirmed: a position row's root
POS_BUYS_FIELD, POS_SELLS_FIELD = "buys", "sells"   # unconfirmed: net = buys - sells
ACCOUNT_FIELDS = ("accountNumber", "accountName", "displayName", "mode", "groupName", "enabled")
_DONE = (proto.FINISHED, proto.REJECTED)
_LIVE = (proto.WORKING, proto.HELD)
_ANSWERED = (proto.WORKING, proto.FINISHED, proto.REJECTED, proto.HELD)    # an order status that answers a submit
TYPE = {"Market": proto.MARKET, "Limit": proto.LIMIT, "Stop": proto.STOP_MARKET, "StopLimit": proto.STOP_LIMIT}
NOT_CONNECTED = "alphatrader: not connected"
SEND_LOST = "alphatrader: the socket closed during the send: it may have gone out, check the orders before sending again"
# T4 status -> the desk's words (homebase/desk/daystate.py); FINISHED reads Filled / Canceled by its fills
STATUS_WORDS = {proto.WORKING: "Working", proto.HELD: "Suspended", proto.REJECTED: "Rejected"}
FLATTEN_TAG = "homebase:flatten"
_ORDER_CAP = 5000
# T4 order message -> {cache key: its field}. proto3 leaves defaults off the wire, so every field a message carries is set
# (a missing one is its default), and the fields a message does not carry are kept from the earlier messages.
_ORDER_KEYS = {
    "orderUpdate": {"marketId": "marketId", "status": "status", "statusDetail": "statusDetail", "buySell": "buySell",
                    "priceType": "priceType", "volume": "currentVolume", "limitPrice": "currentLimitPrice",
                    "stopPrice": "currentStopPrice", "tag": "tag", "filled": "totalFillVolume", "working": "workingVolume",
                    "orderLink": "orderLink", "ordersLinked": "ordersLinked", "activationType": "activationType",
                    "clOrdId": "tagClOrdId"},
    "orderUpdateStatus": {"marketId": "marketId", "status": "status", "statusDetail": "statusDetail",
                          "priceType": "priceType", "volume": "currentVolume", "limitPrice": "currentLimitPrice",
                          "stopPrice": "currentStopPrice", "working": "workingVolume", "tag": "tag",
                          "clOrdId": "tagClOrdId"},
    "orderUpdateTrade": {"marketId": "marketId", "status": "status", "filled": "totalFillVolume", "working": "workingVolume"},
    "orderUpdateFailed": {"marketId": "marketId", "status": "status", "statusDetail": "statusDetail", "clOrdId": "tagClOrdId"},
}
_DEFAULT = {"string": "", "int32": 0, "int64": 0, "bool": False, "double": 0.0, "msg": None}


async def _pause(seconds: float) -> None:       # tests shorten the waits here
    await asyncio.sleep(seconds)


class _Refused(Exception):
    """An order refused before anything is sent."""


def _cl_ord_id() -> str:
    return f"HB_{uuid.uuid4().hex}"                 # unconfirmed: T4 takes a 35-character ClOrdId


def _same(a, b) -> bool:
    """Account ids compare case-blind (the site upper-cases them)."""
    return bool(a) and bool(b) and str(a).upper() == str(b).upper()


def _price(p) -> Optional[float]:
    v = p.get("value") if isinstance(p, dict) else None
    return float(v) if v else None


def _order_fields(kind: str, data: dict) -> dict:
    """The cache fields one order message carries (a missing field is its proto3 default)."""
    kinds = {name: k for name, k, _, _ in proto.SCHEMAS[kind[0].upper() + kind[1:]].values()}
    out = {}
    for key, field in _ORDER_KEYS[kind].items():
        v = data.get(field, _DEFAULT[kinds[field]])
        out[key] = _price(v) if kinds[field] == "msg" else v
    return out


def _net_of(row: dict) -> int:
    return int(row.get(POS_BUYS_FIELD, 0)) - int(row.get(POS_SELLS_FIELD, 0))


def _pos_root(contract, market) -> str:
    """A position row's root: "NQ", "NQZ26", "CME_Eq NQ" or "XCME_Eq NQ (Z26)" all read NQ; a plain root we do not trade
    (a hand-opened "CL") reads as itself; "" = unreadable (empty, or not a root at all)."""
    for v in (contract, market):
        for tok in str(v or "").upper().replace("(", " ").split():
            if root_of(tok) in EXCHANGE:
                return root_of(tok)
    c = root_of(str(contract or "").strip().upper())
    return c if re.fullmatch(r"[A-Z][A-Z0-9]{0,5}", c) else ""


async def _resubscribe(s: AtrSession) -> None:
    try:
        await s.socket.send("accountSubscribe", RESUBSCRIBE)
    except (ConnectionError, AttributeError):
        pass                                            # down (or gone): the next open sends every snapshot itself


def _hub(s: AtrSession) -> None:
    """The login's shared state, attached to the session once."""
    if not hasattr(s, "adapters"):
        s.adapters, s.accounts, s.markets, s.socket = [], {}, {}, None


def _keep_account(s: AtrSession, row: dict, *, details: bool = False) -> None:
    acct = row.get("accountId") if isinstance(row, dict) else None
    if not acct:
        return
    cur = s.accounts.setdefault(acct, {"accountId": acct})
    cur.update({k: row[k] for k in ACCOUNT_FIELDS if k in row})
    if details:
        cur["enabled"] = row.get("enabled", 0)      # proto3: 0 is left off the wire
        cur["groupName"] = row.get("groupName", "")


class AlphaTraderAdapter(BrokerAdapter):
    platform = "alphatrader"

    def __init__(self, account_id: str, *, keyring_key: str, account_name: str, session: AtrSession, live: bool = False):
        super().__init__(account_id, live=live)
        self.keyring_key = keyring_key
        self.account_name = account_name                # "" = probe: connect + list_accounts only
        self.session = session
        _hub(session)
        self.journal = lambda event, **kw: None         # the desk sets it later
        self._acct_id: Optional[str] = None
        self._acct_row: dict = {}
        self._on_fill: Optional[FillCallback] = None
        self._pos: dict[str, tuple[str, int]] = {}      # marketId -> (root, net), THIS account only
        self._pos_ok = False                            # seeded by this account's accountSnapshot since the socket opened
        self._dirty: set = set()                        # marketIds with a fill seen whose position has not landed
        self._orders: dict[str, dict] = {}              # uniqueId -> fields (see _ORDER_KEYS), THIS account only
        self._orders_ok = False
        self._balance: Optional[float] = None
        self._no_stop: set = set()                      # marketIds holding a position with no working stop seen (Task 6)
        self._resync: Optional[asyncio.Task] = None     # the wait before asking for the snapshots again
        self._resynced = False                          # this dirty episode already asked once
        self._waits: dict[str, asyncio.Future] = {}     # a sent ClOrdId, or "pull:<uniqueId>" -> its T4 answer
        self._unanswered: dict[str, str] = {}           # ClOrdId -> marketId of a submit with no answer in the wait
        self._closes: dict[str, str] = {}               # ClOrdId -> marketId of every flatten close still to be seen done
        self._flatten_lock = asyncio.Lock()             # one flatten at a time on this account

    @property
    def broker_key(self):
        return ("alphatrader", self._acct_id) if self._acct_id is not None else self.account_id

    @property
    def positions_known(self) -> bool:
        return self._pos_ok and not self._dirty and self._up()

    @property
    def orders_known(self) -> bool:
        return self._orders_ok and self._up()

    def _up(self) -> bool:
        return self.session.socket is not None and self.session.socket.up

    # ------------------------------------------------------------ lifecycle
    async def connect(self) -> None:
        s = self.session
        late = self not in s.adapters and s.socket is not None and s.socket.up   # its on_up will not run for this one
        if self not in s.adapters:
            s.adapters.append(self)
        if s.socket is None:
            s.socket = AtrSocket(s, _fan_events(s), on_up=_fan_up(s), on_taken=_session_taken(s))
        await s.socket.start()                          # a no-op while it runs; starts again after a stop
        loop = asyncio.get_running_loop()
        end = loop.time() + CONNECT_WAIT_S
        while not s.socket.up:
            if loop.time() >= end:
                await self.close()
                raise RuntimeError(f"alphatrader {self.account_id}: not connected ({s.lost or 'the T4 socket did not log in'})")
            await _pause(0.05)
        if not self.account_name:
            self._connected = True
            return
        found = self._pick() if self._acct_id is None else 1
        if found != 1:
            await self.close()
            self._connected, self.pinned_ok = False, False
            have = [str(a.get("accountName") or a.get("accountId")) for a in s.accounts.values()]
            if not have:                                # an empty list is not proof the account is gone
                raise RuntimeError(f"{self.account_id}: login exposes no accounts")
            err = AccountNotOnLogin(f"more than one account named {self.account_name} on this login" if found else
                                    f"account {self.account_name} not on this login (has: {', '.join(have)})")
            err.listed = have
            raise err
        self._connected = True
        if late:                                        # its snapshot went by before it listened: ask for them again
            self._pos_ok = self._orders_ok = False
            await _resubscribe(s)

    def _pick(self) -> int:
        """Pin the account by id, else by accountName (case-blind); only a single match pins. Returns the match count."""
        want = self.account_name.lower()
        rows = list(self.session.accounts.values())
        hits = [r for r in rows if str(r["accountId"]).lower() == want] \
            or [r for r in rows if str(r.get("accountName", "")).lower() == want]
        if len(hits) == 1:
            self._acct_id, self._acct_row, self.pinned_ok = hits[0]["accountId"], hits[0], True
        return len(hits)

    async def close(self) -> None:
        """Leaves the login: the socket stops with its last adapter, the session is never closed here."""
        self._connected = False
        self._pos_ok = self._orders_ok = False          # off the socket: whatever it sends next is missed
        s = self.session
        if self in s.adapters:
            s.adapters.remove(self)
        if not s.adapters and s.socket is not None:
            sock, s.socket = s.socket, None
            await sock.stop()

    async def _on_up(self) -> None:
        """The socket logged in (first time or again), before it reads anything: pick the account, and trust nothing until
        the fresh snapshot."""
        self._pos_ok = self._orders_ok = False
        if self._acct_id is None and self.account_name:
            self._pick()

    async def observe_fills(self, on_fill: FillCallback) -> None:
        self._on_fill = on_fill                         # delivery: Task 6

    # ------------------------------------------------------------ the socket's events
    def _on_event(self, name: str, data: dict) -> None:
        """One event from the shared socket (sync, from its reader): only this account's."""
        if self._acct_id is None or not isinstance(data, dict) or not _same(data.get("accountId"), self._acct_id):
            return
        if name == "accountSnapshot":
            self._on_snapshot(data)
        else:
            self._apply(name, data)

    def _apply(self, name: str, data: dict) -> None:
        if name == "accountPosition":
            mid = data.get("marketId", "")
            self._pos[mid] = (_pos_root(data.get(POS_ROOT_FIELD), mid), _net_of(data))
            self._dirty.discard(mid)
            if not self._dirty:
                self._resynced = False                  # the dirty episode is over
        elif name == "accountUpdate":
            if "balance" in data:                       # a status-only update carries no balance
                self._balance = data["balance"]
        elif name == "orderUpdateMulti":
            for u in data.get("updates", []):
                for kind, d in u.items():
                    self._apply(kind, d)
        elif name in _ORDER_KEYS:
            self._answer(name, data, self._on_order(name, data))

    def _answer(self, name: str, data: dict, row: Optional[dict]) -> None:
        """Wake whoever waits on this order message: a submit by its ClOrdId (an orderUpdateFailed may come before any
        uniqueId exists), a pull by its order's uniqueId once the order is gone."""
        failed = name == "orderUpdateFailed"
        cid = data.get("tagClOrdId", "")
        if cid in self._unanswered and (failed or data.get("status", 0) in _ANSWERED):
            self._unanswered.pop(cid)                   # the answer after the wait: on record, never acted on
            self.journal("atr_order_late_answer", clOrdId=cid, uniqueId=data.get("uniqueId", ""), failed=failed,
                         status=data.get("status", 0), statusDetail=data.get("statusDetail", ""))
        f = self._waits.get(cid)
        if f is not None and not f.done() and (failed or data.get("status", 0) in _ANSWERED):
            f.set_result((name, data))
        f = self._waits.get("pull:" + data.get("uniqueId", ""))
        if f is not None and not f.done() and (failed or (row is not None and row["status"] in _DONE)):
            f.set_result((name, data))

    def _on_snapshot(self, data: dict) -> None:
        """The account's whole book: positions replaced, the orders reseeded while unknown, then known."""
        self._pos, self._dirty = {}, set()
        if not self._orders_ok:
            self._orders = {}
        for m in data.get("messages", []):
            for name, d in m.items():
                self._apply(name, d)
        self._dirty, self._resynced = set(), False      # the snapshot's positions come after its trades
        self._pos_ok = self._orders_ok = True
        # a flatten close the whole book does not hold (and no submit still waits on) never reached T4: it no longer blocks
        for c, m in list(self._closes.items()):
            if self._by_cid(c) is not None or c in self._waits:
                continue
            # unconfirmed: a book row without its tagClOrdId is taken as our close by its flatten tag (a live one first)
            o = min((o for o in self._orders.values() if not o["clOrdId"] and o["tag"] == FLATTEN_TAG
                     and o["marketId"] == m), key=lambda o: o["status"] not in _LIVE, default=None)
            if o is None:
                del self._closes[c]
            else:
                o["clOrdId"] = c

    def _by_cid(self, cid: str) -> Optional[dict]:
        return next((o for o in self._orders.values() if o["clOrdId"] == cid), None)

    def _on_order(self, kind: str, data: dict) -> Optional[dict]:
        uid = data.get("uniqueId", "")
        if not uid:
            return None
        o = self._orders.setdefault(uid, {"uniqueId": uid, "buySell": 0, "priceType": 0, "volume": 0, "limitPrice": None,
                                          "stopPrice": None, "tag": "", "filled": 0, "working": 0, "orderLink": 0,
                                          "ordersLinked": "", "activationType": 0, "clOrdId": "", "statusDetail": ""})
        filled, mid, cid = o["filled"], o.get("marketId", ""), o["clOrdId"]
        o.update(_order_fields(kind, data))
        o["marketId"], o["clOrdId"] = o["marketId"] or mid, o["clOrdId"] or cid   # a message without them keeps them
        if o["filled"] > filled:                        # a new fill (a repeated update of the same trades is not)
            self._mark_dirty(o["marketId"])
        if len(self._orders) > _ORDER_CAP:              # forget the oldest finished orders, never a working one
            for k in [k for k, v in self._orders.items() if v["status"] in _DONE]:
                if len(self._orders) <= _ORDER_CAP:
                    break
                del self._orders[k]
        return o

    def _mark_dirty(self, mid: str) -> None:
        """A fill seen: the market's net is unknown until its accountPosition lands. Still dirty after DIRTY_RESYNC_S: the
        snapshots are asked for again, once per dirty episode."""
        if mid:
            self._dirty.add(mid)
        else:                                           # a fill with no market: every position unknown until the next snapshot
            self._pos_ok = False
        if not self._resynced and (self._resync is None or self._resync.done()):
            try:
                self._resync = asyncio.get_running_loop().create_task(self._resync_later())
            except RuntimeError:
                pass

    async def _resync_later(self) -> None:
        await _pause(DIRTY_RESYNC_S)
        if (self._dirty or not self._pos_ok) and not self._resynced:
            self._resynced = True
            await _resubscribe(self.session)

    # ------------------------------------------------------------ accounts and markets
    def list_accounts(self) -> list[dict]:
        out = []
        for a in self.session.accounts.values():
            marks = f"{a.get('displayName', '')} {a.get('groupName', '')}".lower()
            out.append({"id": a["accountId"],
                        "name": a.get("displayName") or a.get("accountName") or a.get("accountNumber") or a["accountId"],
                        "active": a.get("enabled", 1) != 0,
                        "practice": a.get("mode") in PRACTICE_MODES or any(w in marks for w in PRACTICE_WORDS)})
        return out

    async def market_id(self, symbol: str, today: Optional[dt.date] = None) -> str:
        """The T4 marketId of a root's front month (or of an explicit contract like NQH27), cached per root + month."""
        s = str(symbol or "").strip().upper()
        root = root_of(s)
        if root not in EXCHANGE:
            raise ValueError(f"alphatrader: unknown market {symbol!r}")
        if s != root:
            _, month, year = symbols.parse_tradovate_symbol(s)
        else:
            month = symbols.CODE_TO_MONTH[symbols.front_month(root, today)[len(root)]]
            now = today or dt.date.today()
            year = now.year + (month < now.month)       # the front month is never in the past
        key = (root, month, year)
        if key not in self.session.markets:
            self.session.markets[key] = await self._find_market(root, month, year)
        return self.session.markets[key]

    async def _find_market(self, root: str, month: int, year: int) -> str:
        resp = await self.session.request("GET", SYMBOLS_PATH, params={"page_size": 100, "search": root})
        if resp.status_code >= 400:
            raise RuntimeError(f"alphatrader: {SYMBOLS_PATH} answered HTTP {resp.status_code}")
        try:
            ans = resp.json()
        except ValueError:
            raise RuntimeError(f"alphatrader: {SYMBOLS_PATH} answer unreadable") from None
        rows = ans if isinstance(ans, list) else ans.get(SYM_ROWS_FIELD) if isinstance(ans, dict) else None
        month_re = re.compile(rf"{symbols.MONTH_TO_CODE[month]}{year % 100:02d}(?!\d)")
        found = {str(r[SYM_MARKET_FIELD]) for r in rows or [] if isinstance(r, dict) and r.get(SYM_MARKET_FIELD)
                 and str(r.get(SYM_ROOT_FIELD, "")).upper() == root
                 and r.get(SYM_EXCHANGE_FIELD, EXCHANGE[root]) == EXCHANGE[root]
                 and any(month_re.search(str(r.get(f) or "")) for f in SYM_MONTH_FIELDS)}
        if len(found) != 1:
            raise ValueError(f"alphatrader: {'no' if not found else 'more than one'} market for {root} "
                             f"{symbols.MONTH_TO_CODE[month]}{year % 100:02d}")
        return found.pop()

    # ------------------------------------------------------------ orders
    @staticmethod
    def _build(req: OrderRequest, *, bracket: bool) -> list[dict]:
        """The OrderSubmit orders: the entry, then (a bracket) the target and the stop. _Refused before anything is sent."""
        root = root_of(str(req.symbol or "").strip().upper())
        if root not in EXCHANGE:
            raise _Refused(f"alphatrader: unknown market {req.symbol!r}")
        side = {"buy": proto.BUY, "sell": proto.SELL}.get(str(req.side).lower())
        if side is None:
            raise _Refused(f"alphatrader: bad side {req.side!r}")
        if isinstance(req.qty, bool) or not isinstance(req.qty, numbers.Integral) or req.qty < 1:
            raise _Refused(f"alphatrader: qty must be a whole number above 0, not {req.qty!r}")
        for v in (req.price, req.stop_price, req.tp_price, req.trigger_price):
            if v is not None and (isinstance(v, bool) or not (isinstance(v, numbers.Real) and math.isfinite(v) and v > 0)):
                raise _Refused(f"alphatrader: bad price {v!r}")
        ot = req.order_type
        protective = ot == "Stop" and not bracket and req.stop_price is not None
        if ot not in TYPE:
            raise _Refused(f"alphatrader: unknown order type {ot!r}")
        if ot == "Limit":
            level = {"limitPrice": req.price}
        elif ot == "StopLimit":
            level = {"limitPrice": req.price, "stopPrice": req.trigger_price}
        elif ot == "Stop":     # a stop entry's trigger is its price; a bare protective Stop carries it in stop_price
            level = {"stopPrice": req.stop_price if protective else req.price}
        else:
            level = {}
        if any(v is None for v in level.values()):
            raise _Refused(f"alphatrader: a {ot.lower()} order needs a price")
        px = lambda v, *r: proto.price(float(v), TICK[root], *r)     # noqa: E731 -- float(): price() reads repr()
        tag = str(req.text or "")[:40]
        entry = {"buySell": side, "priceType": TYPE[ot], "timeType": proto.NORMAL, "volume": int(req.qty),
                 **{k: px(v) for k, v in level.items()}, "tag": tag, "ClOrdId": _cl_ord_id()}
        if protective:         # away from the position it guards (wider, never tighter): a sell stop down, a buy stop up
            entry["stopPrice"] = px(req.stop_price, ROUND_FLOOR if side == proto.SELL else ROUND_CEILING)
        if not bracket:
            return [entry]
        ref = req.trigger_price if ot == "StopLimit" else req.price
        if ref is None:
            raise _Refused(f"alphatrader: a bracketed {ot.lower()} entry needs a price")
        legs = []
        # the stop rounds AWAY from the entry (wider, never tighter: TopstepX's ceil); the target to the nearest tick
        away = ROUND_FLOOR if side == proto.BUY else ROUND_CEILING
        for name, level_px, want, ptype, key in (("target", req.tp_price, 1, proto.LIMIT, "limitPrice"),
                                                 ("stop", req.stop_price, -1, proto.STOP_MARKET, "stopPrice")):
            if level_px is None:
                continue
            p = px(level_px, away) if name == "stop" else px(level_px)
            if (float(p["value"]) - float(px(ref)["value"])) * side * want <= 0:   # on the tick, as sent
                raise _Refused(f"alphatrader: the {name} {level_px} is on the wrong side of the entry {ref}")
            legs.append({"buySell": -side, "priceType": ptype, "timeType": proto.GTC, "volume": 0, key: p,
                         "tag": tag, "activationType": proto.HOLD, "ClOrdId": _cl_ord_id()})
        return [entry, *legs]

    async def place_order(self, req: OrderRequest) -> OrderResult:
        return await self._place(req, bracket=False)

    async def place_bracket(self, req: OrderRequest) -> OrderResult:
        """Entry + target + stop in ONE orderSubmit (AUTO_OCO_P): T4 holds the legs and works them with the fill."""
        if req.stop_price is None and req.tp_price is None:
            return await self.place_order(req)
        return await self._place(req, bracket=True)

    async def _place(self, req: OrderRequest, *, bracket: bool) -> OrderResult:
        if self._acct_id is None or not self._up():
            return OrderResult(ok=False, error=NOT_CONNECTED)
        try:
            orders = self._build(req, bracket=bracket)
            mid = await self.market_id(req.symbol)
        except _Refused as e:
            return OrderResult(ok=False, error=str(e))
        except Exception as e:  # noqa: BLE001 -- the market lookup failed: nothing was sent
            return OrderResult(ok=False, error=f"alphatrader: market not resolved, nothing sent: {e or type(e).__name__}"[:300])
        return await self._submit(mid, orders, bracket=bracket)

    async def _submit(self, mid: str, orders: list[dict], *, bracket: bool = False) -> OrderResult:
        """ONE orderSubmit, answered by the orderUpdate* carrying the entry's ClOrdId within ORDER_WAIT_S. Never resent: no
        answer is outcome unknown (a late answer still lands in the order cache). A bracket's leg ids are those of the
        updates carrying the legs' own ClOrdIds, awaited within the same wait."""
        if not self._up():
            return OrderResult(ok=False, error=NOT_CONNECTED)
        loop = asyncio.get_running_loop()
        ids = [o["ClOrdId"] for o in orders]
        for i in ids:
            self._waits[i] = loop.create_future()
        try:
            try:
                await self.session.socket.send("orderSubmit", {
                    "accountId": self._acct_id, "marketId": mid, "orderLink": proto.AUTO_OCO_P if bracket else 0,
                    "manualOrderIndicator": False, "orders": orders})
            except (ConnectionError, AttributeError):       # it was up a moment ago: the frame may have gone out
                self._unanswered[ids[0]] = mid
                self.journal("atr_order_send_lost", clOrdId=ids[0], market=mid)
                return OrderResult(ok=False, raw={"outcome_unknown": True, "clOrdId": ids[0]}, error=SEND_LOST)
            log.info("alphatrader %s: order %s sent on %s (%d in the submit)", self.account_id, ids[0], mid, len(ids))
            end = loop.time() + ORDER_WAIT_S
            try:
                name, d = await asyncio.wait_for(self._waits[ids[0]], ORDER_WAIT_S)
            except asyncio.TimeoutError:
                self._unanswered[ids[0]] = mid
                while len(self._unanswered) > _ORDER_CAP:
                    self._unanswered.pop(next(iter(self._unanswered)))
                self.journal("atr_order_no_answer", clOrdId=ids[0], market=mid)
                log.warning("alphatrader %s: no answer to order %s", self.account_id, ids[0])
                return OrderResult(ok=False, raw={"outcome_unknown": True, "clOrdId": ids[0]},
                                   error=f"alphatrader: no answer within {ORDER_WAIT_S:g} s: the order may be working, "
                                         "check the orders before sending again")
            uid = d.get("uniqueId", "")
            if name == "orderUpdateFailed" or d.get("status") == proto.REJECTED:
                why = d.get("statusDetail") or "no reason given"
                return OrderResult(ok=False, order_id=uid or None, error=f"alphatrader: order refused: {why}"[:300],
                                   raw={"status": d.get("status", 0), "statusDetail": why, "clOrdId": ids[0]})
            raw = {"uniqueId": uid, "clOrdId": ids[0], "status": d.get("status")}
            if bracket:
                raw.update({"bracket": "attached", "sl_order_id": None, "tp_order_id": None})
                if loop.time() < end:
                    await asyncio.wait([self._waits[i] for i in ids[1:]], timeout=end - loop.time())
                for o in orders[1:]:
                    f, key = self._waits[o["ClOrdId"]], "tp_order_id" if o["priceType"] == proto.LIMIT else "sl_order_id"
                    if not f.done():
                        continue                        # unconfirmed that a held leg reports at once: left None
                    lname, ld = f.result()
                    if lname == "orderUpdateFailed" or ld.get("status") == proto.REJECTED:
                        raw.setdefault("protective_errors", []).append(f"{key[:2]}: {ld.get('statusDetail') or 'refused'}")
                        self.journal("atr_bracket_leg_refused", leg=key[:2], clOrdId=ids[0], market=mid)
                    else:
                        raw[key] = ld.get("uniqueId") or None
            return OrderResult(ok=True, order_id=uid or None, raw=raw)
        finally:
            for i in ids:
                self._waits.pop(i, None)

    # ------------------------------------------------------------ cancel / flatten
    async def _pull(self, o: dict) -> OrderResult:
        """One orderPull for one order, with its own marketId; ok once the order reads gone (pulled, or already taken
        by its OCO partner). Never resent."""
        if not self._up():
            return OrderResult(ok=False, error=NOT_CONNECTED)
        uid, key = o["uniqueId"], "pull:" + o["uniqueId"]
        f = self._waits[key] = asyncio.get_running_loop().create_future()
        try:
            try:
                await self.session.socket.send("orderPull", {"accountId": self._acct_id, "marketId": o["marketId"],
                                                             "manualOrderIndicator": False, "pulls": [{"uniqueId": uid}]})
            except (ConnectionError, AttributeError):       # it was up a moment ago: the pull may have gone out
                return OrderResult(ok=False, order_id=uid, raw={"outcome_unknown": True}, error=SEND_LOST)
            try:
                _, d = await asyncio.wait_for(f, ORDER_WAIT_S)
            except asyncio.TimeoutError:
                return OrderResult(ok=False, order_id=uid, raw={"outcome_unknown": True},
                                   error=f"alphatrader: no answer to the cancel of {uid} within {ORDER_WAIT_S:g} s")
        finally:
            self._waits.pop(key, None)
        if self._orders.get(uid, o)["status"] in _DONE:
            return OrderResult(ok=True, order_id=uid)
        return OrderResult(ok=False, order_id=uid,
                           error=f"alphatrader: cancel of {uid} refused: {d.get('statusDetail') or 'no reason given'}"[:300])

    async def _pull_all(self, rows: list[dict]) -> list[str]:
        """Every pull at once; their errors."""
        return [r.error for r in await asyncio.gather(*(self._pull(o) for o in rows)) if not r.ok]

    async def cancel_order_by_id(self, order_id: str) -> OrderResult:
        if self._acct_id is None or not self._up():
            return OrderResult(ok=False, error=NOT_CONNECTED)
        o = self._orders.get(str(order_id))
        if o is None or not o.get("marketId"):
            return OrderResult(ok=False, error=f"alphatrader: order {order_id} is not in the order book (its market is not "
                                               "known), nothing sent")
        if o["status"] in _DONE:
            return OrderResult(ok=False, order_id=str(order_id), error=f"alphatrader: order {order_id} is no longer working")
        return await self._pull(o)

    async def cancel_all(self) -> OrderResult:
        """Pull every working (or held) order of this account."""
        if self._acct_id is None or not self._up():
            return OrderResult(ok=False, error=NOT_CONNECTED)
        if not self.orders_known:
            return OrderResult(ok=False, error="alphatrader: working orders unknown, nothing pulled")
        rows = [o for o in self._orders.values() if o["status"] in _LIVE]
        errors = await self._pull_all(rows)
        return OrderResult(ok=not errors, error="; ".join(errors) or None, raw={"pulled": len(rows) - len(errors)})

    async def flatten_symbol(self, symbol: str) -> OrderResult:
        """Close every month of the root held (an older month after a roll, a hand-opened one), then pull the working
        orders of the root's markets that closed."""
        root = root_of(str(symbol or "").strip().upper())
        if root not in EXCHANGE:
            return OrderResult(ok=False, error=f"alphatrader: unknown market {symbol!r}")
        return await self._flatten(root)

    async def flatten_all(self) -> OrderResult:
        """Close every market held, then pull every working order of the markets that closed (or held nothing)."""
        return await self._flatten(None)

    def _root_of_market(self, mid: str) -> str:
        return self._pos[mid][0] if mid in self._pos else _pos_root("", mid)

    async def _until(self, cond) -> bool:
        """Wait up to ORDER_WAIT_S for cond() to hold (the socket's pushes land meanwhile)."""
        loop = asyncio.get_running_loop()
        end = loop.time() + ORDER_WAIT_S
        while not cond():
            if loop.time() >= end:
                return False
            await _pause(0.02)
        return True

    def _close_pending(self, mid: str) -> bool:
        """A flatten close of this market is still working, or was never answered: a second one could double it."""
        for cid, m in list(self._closes.items()):
            o = self._by_cid(cid)
            if o is not None and o["status"] not in _LIVE:
                del self._closes[cid]                   # done: it no longer counts
            elif m == mid:
                return True
        return False

    async def _flatten(self, root: Optional[str]) -> OrderResult:
        """One flatten at a time. Positions are read first (a just-filled market gets ORDER_WAIT_S to settle; still unknown:
        nothing is sent). A market with a flatten close still working or unanswered is not closed again. Each other held
        market gets ONE opposite MARKET of |net|, judged by its own fill and the position after it: flat → its working
        orders are pulled; flipped sign → closed again once, then judged the same way; anything else (refused, unanswered,
        not filled in the wait, finished unfilled, still held) → not ok, and its orders (its stop) are left working.
        A market in scope holding nothing has its working orders pulled. raw: net_before (the root's net; None for
        flatten_all), market (the first close: ok, order_id, error), closes (per market), flattened."""
        if self._acct_id is None or not self._up():
            return OrderResult(ok=False, error=NOT_CONNECTED)
        async with self._flatten_lock:
            unreadable = lambda: root and any(n and not r for r, n in self._pos.values())   # noqa: E731
            await self._until(lambda: self.positions_known and not unreadable())
            if not self.positions_known or unreadable():
                return OrderResult(ok=False, error="alphatrader: positions unknown, nothing sent")
            in_scope = lambda mid: root is None or self._root_of_market(mid) == root   # noqa: E731
            held = {mid: n for mid, (r, n) in self._pos.items() if n and (root is None or r == root)}
            raw: dict = {"net_before": sum(held.values()) if root else None, "closes": {}}
            busy = [mid for mid in held if self._close_pending(mid)]
            errors = [f"alphatrader: {mid}: a flatten close is still working or unanswered: nothing sent, check it"
                      for mid in busy]
            todo = {mid: n for mid, n in held.items() if mid not in busy}
            res = dict(zip(todo, await asyncio.gather(*(self._close_market(mid, n) for mid, n in todo.items()))))
            for mid, (first, r) in res.items():
                raw["closes"][mid] = {"ok": first.ok, "order_id": first.order_id, "error": first.error}
                raw.setdefault("market", raw["closes"][mid])
                if not r.ok:
                    errors.append(r.error)
            flat = {mid for mid, (_, r) in res.items() if r.ok}
            # read flat NOW, not at the start: a resting entry may have filled during the closes' waits
            due = lambda mid: in_scope(mid) and (mid in flat or mid not in held)   # noqa: E731
            now_flat = lambda mid: self._pos_ok and mid not in self._dirty and not self._pos.get(mid, ("", 0))[1]   # noqa: E731
            pulled: set = set()
            if self.orders_known:
                # a flat market's working orders all go, an earlier close still live there too (a market order on flat)
                rows = [o for o in self._orders.values() if o["status"] in _LIVE and due(o["marketId"])
                        and now_flat(o["marketId"])]
                pulled = {o["marketId"] for o in rows}
                errors += await self._pull_all(rows)
            else:
                errors.append("alphatrader: working orders unknown, none pulled")
            if not self._pos_ok:                        # a fill with no market: nothing more was pulled
                errors.append("alphatrader: positions unknown after the flatten: check them")
            for m in sorted({m for m in set(self._pos) | self._dirty | pulled
                             if self._pos_ok and due(m) and not now_flat(m)}):
                errors.append(f"alphatrader: {m} filled during the flatten: "
                              + ("its orders were being pulled, check its stop" if m in pulled else "its orders kept"))
            errors += [f"alphatrader: {m}: an earlier flatten close was never answered: it may be working, check it"
                       for m in sorted({m for c, m in self._closes.items()
                                        if m not in held and in_scope(m) and self._by_cid(c) is None})]
            raw["flattened"] = len(flat)
            return OrderResult(ok=not errors, error="; ".join(errors) or None, raw=raw)

    async def _close_market(self, mid: str, net: int) -> tuple[OrderResult, OrderResult]:
        """(the first close's answer, the verdict: ok only when the market reads flat after our own fills)."""
        first = r = await self._close(mid, net)
        for again in (False, True):                     # the close, then at most ONE re-close on a flipped sign
            if not r.ok:
                return first, r
            why = await self._filled(r.order_id, abs(net), mid)
            if why:
                return first, OrderResult(ok=False, error=f"alphatrader: {mid}: {why}: its orders are left working")
            self._closes.pop(r.raw.get("clOrdId"), None)   # filled: it no longer blocks a flatten
            now = self._pos.get(mid, ("", 0))[1]
            if not now:
                return first, OrderResult(ok=True)
            if again or now * net > 0:                  # same sign, or flipped after the re-close: never another close
                return first, OrderResult(ok=False, error=f"alphatrader: {mid}: still {now:+d} after its close"
                                          f"{' and one re-close' if again else ''} (not sent again): its orders are "
                                          "left working")
            net = now
            r = await self._close(mid, now)             # the net flipped (a stop filled too): close what is held now
        raise AssertionError("unreachable")

    async def _filled(self, uid: str, qty: int, mid: str) -> Optional[str]:
        """Wait for the close's own fill of `qty` and the market's position after it. None = both landed, else why not."""
        o = lambda: self._orders.get(uid) or {}         # noqa: E731
        done = lambda: (o().get("filled", 0) >= qty and mid not in self._dirty and self._pos_ok and self._up()) \
            or (o().get("status") in _DONE and o().get("filled", 0) < qty)   # noqa: E731
        if not await self._until(done):
            return (f"the close was not filled in {ORDER_WAIT_S:g} s (not sent again)" if o().get("filled", 0) < qty
                    else "its position after the close did not land")
        if o().get("filled", 0) < qty:
            return f"the close ended with {o().get('filled', 0)} of {qty} filled"
        return None

    async def _close(self, mid: str, net: int) -> OrderResult:
        cid = _cl_ord_id()
        self._closes[cid] = mid                         # before the send: a caller cancelled mid-wait leaves it on record
        r = await self._submit(mid, [{"buySell": proto.SELL if net > 0 else proto.BUY, "priceType": proto.MARKET,
                                      "timeType": proto.NORMAL, "volume": abs(net), "tag": FLATTEN_TAG, "ClOrdId": cid}])
        if r.raw.get("outcome_unknown"):
            await _resubscribe(self.session)            # the snapshots settle it: in the book (wait for it) or not (gone)
        elif not r.ok:
            self._closes.pop(cid, None)                 # not sent, or refused: never working
        if not r.ok:
            r.error = f"{mid}: {r.error}"
        return r

    # ------------------------------------------------------------ reads
    async def get_net_position(self, symbol: str) -> int:
        """Net position over every month of the symbol's root. RAISES while it is not known: unknown is never flat."""
        if self._acct_id is None:
            raise RuntimeError("adapter not connected")
        root = root_of(str(symbol or "").strip().upper())
        if root not in EXCHANGE:
            raise ValueError(f"alphatrader: unknown market {symbol!r}")
        if not self.positions_known or any(n and not r for r, n in self._pos.values()):
            raise RuntimeError("position unknown")      # a held row whose root we cannot read could be this market
        return sum(n for r, n in self._pos.values() if r == root)

    def _order_row(self, order_id) -> Optional[dict]:
        return self._orders.get(str(order_id)) if self.orders_known else None

    async def get_order_status(self, order_id: str) -> Optional[str]:
        """The desk's words (as TopstepX gives them) from the order cache. None = unknown: not seeded, the socket down,
        an order the cache does not hold or a status not known."""
        o = self._order_row(order_id)
        if o is None:
            return None
        if o["status"] == proto.FINISHED:               # a part fill then a cancel reads Filled: the position moved
            return "Filled" if o["filled"] else "Canceled"
        return STATUS_WORDS.get(o["status"])

    async def get_order_state(self, order_id: str) -> dict:
        o = self._order_row(order_id)
        return {"status": await self.get_order_status(order_id), "filled_qty": (o["filled"] or None) if o else None}

    async def get_balance(self) -> dict:
        return {"amount": self._balance} if self._balance is not None else {}

    async def get_metrics(self) -> dict:
        """No broker request here (the dashboard polls it): the numbers come from the snapshot and the pushes."""
        m = await super().get_metrics()
        m["account"] = self._acct_row.get("displayName") or self._acct_row.get("accountName") or None
        m["balance"] = self._balance
        known = m["positions_known"] = self.positions_known
        if known:
            by_root: dict[str, int] = {}
            for mid, (r, n) in self._pos.items():
                by_root[r or mid] = by_root.get(r or mid, 0) + n
            m["open_positions"] = [{"symbol": r, "net": n} for r, n in by_root.items() if n]
            m["open_position_count"] = len(m["open_positions"])
        else:
            m["open_position_count"] = None             # unknown, never 0
        orders_known = self.orders_known
        m["working_orders"] = sum(1 for o in self._orders.values() if o["status"] in (proto.WORKING, proto.HELD)) \
            if orders_known else None
        m["cache_seeded"] = known and orders_known
        m["session_taken"] = self.session.taken
        m["no_stop"] = sorted({self._pos[mid][0] for mid in self._no_stop if self._pos.get(mid, ("", 0))[1]})
        words = ([f"no stop seen on {', '.join(m['no_stop'])}"] if m["no_stop"] else []) \
            + ([f"session taken {self.session.taken}x"] if self.session.taken else []) \
            + ([str(self.session.lost)] if self.session.lost else [])
        if words:
            m["notice"] = " · ".join(words)
        return m


def _fan_events(session: AtrSession):
    def on_event(name: str, data: dict) -> None:
        if name == "loginResponse":
            for a in data.get("accounts", []):
                _keep_account(session, a)
        elif name == "accountDetails":
            _keep_account(session, data, details=True)
        elif name == "accountSnapshot":
            for m in data.get("messages", []):
                if "accountDetails" in m:
                    _keep_account(session, m["accountDetails"], details=True)
        for a in list(session.adapters):
            try:
                a._on_event(name, data)
            except Exception as e:  # noqa: BLE001 -- one account's failure must not starve the others
                log.warning("alphatrader %s: event %s failed (%s)", a.account_id, name, type(e).__name__)
    return on_event


def _fan_up(session: AtrSession):
    async def on_up() -> None:
        for a in list(session.adapters):
            try:
                await a._on_up()
            except Exception as e:  # noqa: BLE001
                log.warning("alphatrader %s: on_up failed (%s)", a.account_id, type(e).__name__)
    return on_up


def _session_taken(session: AtrSession):
    """The login's handler for 'T4 ended this session for another login'. Task 6 counts and journals it; the socket logs in
    again by itself (through the budget) and the next snapshot reseeds the caches."""
    async def taken(why: str) -> None:
        for a in list(session.adapters):               # the book is stale until the next login's snapshot
            a._pos_ok = a._orders_ok = False
    return taken
