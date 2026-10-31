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
import re
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


def _pos_root(v) -> str:
    """A position row's root: "NQ", "NQZ26", "CME_Eq NQ" or "XCME_Eq NQ (Z26)" all read NQ; "" when no traded root is in it."""
    for tok in str(v or "").upper().replace("(", " ").split():
        if root_of(tok) in EXCHANGE:
            return root_of(tok)
    return ""


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
            self._pos[mid] = (_pos_root(data.get(POS_ROOT_FIELD)) or _pos_root(mid), _net_of(data))
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
            self._on_order(name, data)

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

    def _on_order(self, kind: str, data: dict) -> Optional[dict]:
        uid = data.get("uniqueId", "")
        if not uid:
            return None
        o = self._orders.setdefault(uid, {"uniqueId": uid, "buySell": 0, "priceType": 0, "volume": 0, "limitPrice": None,
                                          "stopPrice": None, "tag": "", "filled": 0, "working": 0, "orderLink": 0,
                                          "ordersLinked": "", "activationType": 0, "clOrdId": "", "statusDetail": ""})
        filled, mid = o["filled"], o.get("marketId", "")
        o.update(_order_fields(kind, data))
        o["marketId"] = o["marketId"] or mid
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

    # ------------------------------------------------------------ orders (Task 5)
    async def place_order(self, req: OrderRequest) -> OrderResult:
        return OrderResult(ok=False, error="alphatrader: orders are not built yet")

    async def cancel_all(self) -> OrderResult:
        return OrderResult(ok=False, error="alphatrader: orders are not built yet")

    async def flatten_all(self) -> OrderResult:
        return OrderResult(ok=False, error="alphatrader: orders are not built yet")

    # ------------------------------------------------------------ reads
    async def get_net_position(self, symbol: str) -> int:
        """Net position over every month of the symbol's root. RAISES while it is not known: unknown is never flat."""
        if self._acct_id is None:
            raise RuntimeError("adapter not connected")
        root = root_of(str(symbol or "").strip().upper())
        if root not in EXCHANGE:
            raise ValueError(f"alphatrader: unknown market {symbol!r}")
        if not self.positions_known or any(n and r not in EXCHANGE for r, n in self._pos.values()):
            raise RuntimeError("position unknown")      # a held row whose root we cannot read could be this market
        return sum(n for r, n in self._pos.values() if r == root)

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
