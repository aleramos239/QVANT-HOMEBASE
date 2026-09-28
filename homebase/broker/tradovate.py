"""Tradovate adapter — binds one Tradovate account (demo or live).

MASTER role: `observe_fills` streams this account's fills via the WebSocket
entity push. FOLLOWER role: `place_order` / `flatten_all` / `cancel_all`.

Auth is the reverse-engineered web-client flow (no paid API). Credentials come
from the OS keychain via `secrets_store`, keyed by the account's `keyring_key`.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import sys
import time
from collections import deque
from pathlib import Path
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from .. import symbols
from ..paths import state_dir as _default_state_dir
from ..secrets_store import get_credentials
from .base import (AccountNotOnLogin, BrokerAdapter, FillCallback, FillEvent,
                   OrderRequest, OrderResult)
from .tradovate_auth import TradovateAuth
from .tradovate_ws import TradovateWS, _ws_is_closed

_SEEN_FILL_CAP = 20000
_SEED_BACKOFF_CAP = 60.0    # seconds between cache-seed retries, at most

# --- token renewal vs the 9:30 fire (2026-09-27) ------------------------------------------
# A renewal rolls the token and so DROPS the socket (_renew_if_needed); the supervisor
# (server._broker_loop, every 5 s) rebuilds it. Tokens live 80 min, so the old "renew with
# < 10 min left" rule dropped the socket every ~70 min, at whatever time that fell -- 09:29:5x
# included. renewal_due() keeps renewal drops out of 09:20-09:35 ET on weekdays.
ET = ZoneInfo("America/New_York")
RENEW_BUFFER_S = 600.0                                # the normal rule: renew with < 10 min left
RENEW_EARLY_FROM = dt.time(9, 10)                     # [09:10, 09:20): renew early if due before 09:36
RENEW_QUIET = (dt.time(9, 20), dt.time(9, 35))        # [from, until): no renewal drop
RENEW_CARRY_UNTIL = dt.time(9, 36)                    # a token must live past this: the first check after 09:35
RENEW_FIRE_GUARD = (dt.time(9, 28), dt.time(9, 31))   # [from, until): a socket living through it is never dropped
RECONNECT_RENEW_S = 5.0                               # a reconnect's best-effort renewal waits at most this


def _log(msg: str) -> None:
    print(f"[tradovate] {msg}", file=sys.stderr, flush=True)


def _et_at(day: dt.date, t: dt.time) -> float:
    return dt.datetime.combine(day, t, tzinfo=ET).timestamp()


def renewal_due(now: dt.datetime, expires_at: float) -> tuple[bool, str]:
    """Should the keepalive renew the token -- and so drop the socket -- at `now`?
    -> (due, why). `now` is timezone-aware; `expires_at` the token's expiry in unix seconds
    (0 = unknown). Checked once a minute. Weekdays, ET:

      09:10-09:20  "early": renew if the token would come due (RENEW_BUFFER_S left) before
                   09:36, i.e. it expires before 09:46 -- the drop and the reconnect land 10+
                   minutes before the fire, and nothing comes due inside the quiet window.
                   09:19:59 is still early. While 10+ min are left: renew only, never a
                   login (logins are rate-limited); a failure retries at the next check.
      09:20-09:35  "quiet": NO renewal, even with < 10 min left -- unless the token would
                   EXPIRE before 09:36 ("expires_in_window": Tradovate closes its socket at the
                   expiry anyway, and the first check after 09:35 may come too late): then at
                   once, i.e. at the window's first check (~09:20), 8+ minutes before the fire.
                   Only possible when every early renewal failed.
      09:28-09:31  "fire_guard": a socket whose token lives past 09:31 is never dropped here
                   -- it carries the prestage, the fire, the acks and the first fills, and is
                   renewed at 09:31. One whose token dies inside the guard (or already has)
                   dies anyway: renewed at once ("expires_in_guard"), because a rebuild done
                   before 09:30 lets the fire go out, and a fire refused as "not connected"
                   beats a socket dying under its acks. A renewal whose answer lands inside
                   the guard is re-checked the same way (_renew_if_needed).
      An unknown expiry is never renewed inside the quiet window.
    Any other time, and weekends: the normal rule, < RENEW_BUFFER_S left ("normal")."""
    et = now.astimezone(ET)
    if et.weekday() < 5:
        t = et.time()
        carry = _et_at(et.date(), RENEW_CARRY_UNTIL)
        if RENEW_QUIET[0] <= t < RENEW_QUIET[1]:
            if not expires_at or expires_at >= carry:
                return False, "quiet"
            if RENEW_FIRE_GUARD[0] <= t < RENEW_FIRE_GUARD[1]:
                if carries_the_guard(et, expires_at):
                    return False, "fire_guard"
                return True, "expires_in_guard"
            return True, "expires_in_window"
        if RENEW_EARLY_FROM <= t < RENEW_QUIET[0] and expires_at \
                and expires_at - RENEW_BUFFER_S < carry:
            return True, "early"
    return expires_at - et.timestamp() < RENEW_BUFFER_S, "normal"


def in_fire_guard(now: dt.datetime) -> bool:
    et = now.astimezone(ET)
    return et.weekday() < 5 and RENEW_FIRE_GUARD[0] <= et.time() < RENEW_FIRE_GUARD[1]


def carries_the_guard(now: dt.datetime, expires_at: float) -> bool:
    """Inside the fire guard, with a token (the socket's) that lives past its end."""
    et = now.astimezone(ET)
    return in_fire_guard(et) and expires_at >= _et_at(et.date(), RENEW_FIRE_GUARD[1])


def reconnect_buffer_s(now: dt.datetime) -> float:
    """The token life a socket being REBUILT (reconnect) should start with: normally
    RENEW_BUFFER_S; weekdays 09:10-09:36 ET, enough that it never comes due before 09:36, so
    the rebuilt socket needs no renewal drop inside the quiet window. Best effort only
    (TradovateAdapter._renew_before_the_window): never at the cost of the rebuild."""
    et = now.astimezone(ET)
    if et.weekday() < 5 and RENEW_EARLY_FROM <= et.time() < RENEW_CARRY_UNTIL:
        left_to_carry = _et_at(et.date(), RENEW_CARRY_UNTIL) - et.timestamp()
        return max(RENEW_BUFFER_S, left_to_carry + RENEW_BUFFER_S)
    return RENEW_BUFFER_S


STOPLIMIT_INCOMPLETE = "a Stop Limit order needs both a limit price and a trigger"


def _stoplimit_incomplete(req: OrderRequest) -> bool:
    return req.order_type == "StopLimit" and (req.price is None or req.trigger_price is None)


def _reject_reason(d) -> str:
    """Human-readable reason from an order/placeorder response that carried no
    orderId. Tradovate returns transport status 200 even on a logical reject and
    puts the cause in failureText / failureReason, so a missing orderId is the
    real failure signal — without this the engine reports a reject as success."""
    if isinstance(d, dict):
        return str(d.get("failureText") or d.get("failureReason") or "").strip()
    return ""


class TradovateAdapter(BrokerAdapter):
    platform = "tradovate"

    def __init__(
        self,
        account_id: str,
        *,
        env: str = "demo",
        keyring_key: str = "",
        account_selector: Optional[dict] = None,
        audit: Optional[Callable[[dict], None]] = None,
        state_dir: Optional[Path] = None,
    ):
        super().__init__(account_id, live=(env == "live"))
        self.env = env
        self.keyring_key = keyring_key or account_id
        self.account_selector = account_selector or {}
        self.audit = audit or (lambda e: None)
        state_dir = state_dir or _default_state_dir()
        state_dir.mkdir(parents=True, exist_ok=True)
        self._auth = TradovateAuth(
            env=env,
            token_persist_path=state_dir / f"{account_id}.tokens.json",
            device_persist_path=state_dir / f"{account_id}.device.json",
        )
        self._ws: Optional[TradovateWS] = None
        self._acct_num: Optional[int] = None
        self._acct_name: str = ""
        self._all_accounts: list = []   # every account the login exposes
        self._contracts: dict[int, str] = {}     # contractId -> symbol name
        self._orders: dict[int, dict] = {}        # orderId -> order entity
        self._order_versions: dict[int, dict] = {}  # orderId -> latest orderVersion
        self._order_symbols: dict[int, str] = {}  # orderId -> contract, orders WE placed
        self._order_filled: dict[int, int] = {}   # orderId -> contracts filled (fills seen)
        self._seen_fills: set[int] = set()
        self._seen_order: deque = deque(maxlen=_SEEN_FILL_CAP)
        self._on_fill: Optional[FillCallback] = None
        self._fill_q: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._consumer: Optional[asyncio.Task] = None
        self._keepalive: Optional[asyncio.Task] = None
        self._positions: dict[int, dict] = {}     # contractId -> position, THIS account only
        self._cash: dict = {}                     # cashBalance, THIS account only
        self._contract_lookups: set = set()       # contract ids being resolved in the background
        self._lookup_tasks: set = set()           # their tasks, cancelled by close()
        self._pos_pushed: set = set()             # contract ids pushed while a seed read is in flight
        self._cash_pushed = False                 # a cashBalance push landed while the seed read it
        self._seed_task: Optional[asyncio.Task] = None
        self._seed_sleep = asyncio.sleep          # the seed's retry backoff (tests replace it)
        self._now = lambda: dt.datetime.now(dt.timezone.utc)   # the renewal rule's clock (tests replace it)
        self.caches_seeded = False                # position/cash read after the last (re)connect

    @property
    def connected(self) -> bool:
        """True only while the WebSocket is actually live. ``_connected`` records
        that we finished login + connect, but the socket can drop silently
        afterwards; the reader flips ``ws.connected`` on exit and the close probe
        catches a wedged socket, so a dead link reports disconnected instead of a
        phantom green dot the dashboard would keep trusting."""
        ws = self._ws
        if not self._connected or ws is None:
            return False
        return bool(ws.connected) and not _ws_is_closed(ws)

    # ------------------------------------------------------------ lifecycle
    async def connect(self) -> None:
        self._stop_seed()
        creds = get_credentials(self.keyring_key)
        if not creds or not creds.get("username") or not creds.get("password"):
            raise RuntimeError(
                f"no credentials in keychain for key {self.keyring_key!r} — run: "
                f"python -m homebase.secrets_store set {self.keyring_key}"
            )
        await asyncio.to_thread(self._auth.login, creds["username"], creds["password"])
        self._ws = TradovateWS(token=self._auth.access_token, environment=self.env)
        self._ws.event_handlers.append(self._on_ws_event)
        await self._ws.connect()
        await self._ws.authorize()
        sync = await self._ws.user_sync()
        self._ingest_sync(sync)
        self._connected = True
        self._schedule_seed()
        # a repeat connect() used to stack a new keepalive on top of the old one
        # every time — a night of drops leaked dozens of them
        if self._keepalive is not None and not self._keepalive.done():
            self._keepalive.cancel()
        self._keepalive = asyncio.create_task(self._keepalive_loop())
        self.audit({"event": "adapter_connected", "account": self.account_id,
                    "platform": self.platform, "env": self.env,
                    "tradovate_account": self._acct_name, "tradovate_id": self._acct_num})
        _log(f"{self.account_id}: connected as {self._acct_name} "
             f"(#{self._acct_num}) env={self.env}")

    async def reconnect(self) -> None:
        """Rebuild the websocket and re-authorize in place, preserving the fill
        callback, dedup cache, and fill queue so mirroring resumes transparently.
        Recovery is driven by the engine's connection supervisor."""
        self._stop_seed()
        try:
            if self._ws:
                await self._ws.close()
        except Exception:
            pass
        now = self._now()
        await self._renew_before_the_window(now)
        await asyncio.to_thread(self._auth.ensure_valid, RENEW_BUFFER_S, now.timestamp())
        self._ws = TradovateWS(token=self._auth.access_token, environment=self.env)
        self._ws.event_handlers.append(self._on_ws_event)
        await self._ws.connect()
        await self._ws.authorize()
        sync = await self._ws.user_sync()
        self._ingest_sync(sync)
        self._connected = True
        self._schedule_seed()
        if self._consumer is None or self._consumer.done():
            self._consumer = asyncio.create_task(self._consume_fills())
        if self._keepalive is None or self._keepalive.done():
            self._keepalive = asyncio.create_task(self._keepalive_loop())
        self.audit({"event": "adapter_reconnected", "account": self.account_id})

    async def _renew_before_the_window(self, now: dt.datetime) -> None:
        """reconnect(), weekdays 09:10-09:36 ET: the socket is being rebuilt anyway, so
        start it on a token that carries the quiet window (reconnect_buffer_s) -- best
        effort only. Renew, never a login; never inside the fire guard (the rebuild must
        not wait); at most RECONNECT_RENEW_S. On any failure the socket is rebuilt on the
        current token, which ensure_valid's normal rule still checks -- exactly as before."""
        tokens = self._auth.tokens
        if tokens is None or in_fire_guard(now):
            return
        left = tokens.expires_at_unix - now.timestamp()
        if not RENEW_BUFFER_S <= left < reconnect_buffer_s(now):
            return          # it carries the window, or the normal rule renews it anyway
        try:
            await asyncio.wait_for(asyncio.to_thread(self._auth.renew), RECONNECT_RENEW_S)
        except Exception as e:  # noqa: BLE001 — incl. the timeout
            _log(f"{self.account_id}: renewal before the 9:30 window failed ({e}) — "
                 "rebuilding on the current token")

    async def close(self) -> None:
        self._connected = False
        self.caches_seeded = False
        for t in (self._keepalive, self._consumer, self._seed_task, *self._lookup_tasks):
            if t:
                t.cancel()
        self._lookup_tasks.clear()
        self._contract_lookups.clear()      # a reconnect may look them up again
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass

    # ------------------------------------------------------------ sync ingest
    def _ingest_sync(self, sync: dict) -> None:
        for c in sync.get("contracts", []) or []:
            if "id" in c and "name" in c:
                self._contracts[c["id"]] = c["name"]
        for o in sync.get("orders", []) or []:
            if "id" in o:
                self._orders[o["id"]] = o
        for ov in sync.get("orderVersions", []) or []:
            oid = ov.get("orderId")
            if oid is not None:
                self._order_versions[oid] = ov
        for f in sync.get("fills", []) or []:
            if "id" in f and self._mark_seen(f["id"]):   # historical fills must not be copied
                self._count_fill(f)
        self._resolve_account(sync.get("accounts", []) or [])

    def list_accounts(self) -> list[dict]:
        """Every account under the connected login (for the connect wizard)."""
        return [{"id": a.get("id"),
                 "name": a.get("name") or a.get("nickname") or str(a.get("id")),
                 "active": a.get("active", True)} for a in self._all_accounts]

    def _resolve_account(self, accounts: list) -> None:
        self._all_accounts = list(accounts)
        if not accounts:
            raise RuntimeError(f"{self.account_id}: login exposes no accounts")
        sel = self.account_selector
        chosen = None
        want_id = sel.get("tradovate_account_id")
        if want_id:
            chosen = next((a for a in accounts if a.get("id") == want_id), None)
        want_name = sel.get("account_name") or sel.get("tradovate_account_name")
        if chosen is None and want_name:
            w = str(want_name).lower()
            chosen = next((a for a in accounts
                           if str(a.get("name", "")).lower() == w
                           or str(a.get("nickname", "")).lower() == w), None)
        if chosen is None and (want_id or want_name):
            # A pin that is not on this login is an ERROR, never a fallback:
            # on 2026-09-26 pins ...044/...045 silently connected to ...047.
            # Drop the connected flag too, so a reconnect can never keep
            # reporting the OLD account as up on the new socket.
            self._connected = False
            self._acct_num, self._acct_name, self.pinned_ok = None, "", False
            have = ", ".join(str(a.get("name") or a.get("nickname") or a.get("id"))
                             for a in accounts)
            raise AccountNotOnLogin(
                f"account {want_name or want_id} not on this login (has: {have})")
        pinned = chosen is not None
        if chosen is None:
            active = [a for a in accounts if a.get("active", True)]
            chosen = (active or accounts)[0]
            if len(accounts) > 1:
                _log(f"{self.account_id}: {len(accounts)} accounts under this login; "
                     f"using {chosen.get('name')} (#{chosen.get('id')}). "
                     f"Pin one with extra.account_name in config.")
        self._acct_num = chosen.get("id")
        self._acct_name = chosen.get("name") or chosen.get("nickname") or str(self._acct_num)
        self.pinned_ok = pinned

    # ------------------------------------------------------------ fill stream
    def _count_fill(self, ent: dict) -> None:
        """Contracts filled per order id, from the fills this socket saw (a
        LOWER bound: a push can omit its orderId or qty). Only ever read by
        get_order_state for the per-strategy kill."""
        try:
            oid, qty = ent.get("orderId"), ent.get("qty")
            if oid is None or not isinstance(qty, (int, float)) or isinstance(qty, bool) or qty <= 0:
                return
            self._order_filled[int(oid)] = self._order_filled.get(int(oid), 0) + int(qty)
        except Exception:  # noqa: BLE001 — a count, never a reason to lose a fill
            return

    def _mark_seen(self, fid: int) -> bool:
        """Record a fill id; return True if it was not seen before."""
        if fid in self._seen_fills:
            return False
        if len(self._seen_order) == self._seen_order.maxlen:
            self._seen_fills.discard(self._seen_order[0])
        self._seen_order.append(fid)
        self._seen_fills.add(fid)
        return True

    def _on_ws_event(self, msg: dict) -> None:
        """Sync handler invoked from the WS reader for every unsolicited frame.
        The adapter's own caches take each push first; listeners (chart
        trading) hear about it after, and only for THIS account."""
        if msg.get("e") != "props":
            return
        d = msg.get("d") or {}
        et = d.get("entityType")
        ent = d.get("entity")
        if not et or not isinstance(ent, dict):
            return
        if et == "contract":
            if "id" in ent and "name" in ent:
                self._contracts[ent["id"]] = ent["name"]
        elif et == "order":
            if "id" in ent:
                self._orders[ent["id"]] = {**self._orders.get(ent["id"], {}), **ent}
                self._name_order_contract(et, ent["id"], self._orders[ent["id"]])
                self._notify_mine(et, self._orders[ent["id"]])
        elif et == "orderVersion":
            oid = ent.get("orderId")
            if oid is not None:
                self._order_versions[oid] = {**self._order_versions.get(oid, {}), **ent}
                self._name_order_contract(et, oid, self._order_versions[oid])
                self._notify_mine(et, self._order_versions[oid])
        elif et == "fill":
            fid = ent.get("id")
            if fid is None or not self._mark_seen(fid):
                return
            if self._on_fill is not None:     # this account is being observed as master
                self._enqueue_fill(ent)
            self._notify_mine(et, ent)
            self._count_fill(ent)             # after the dispatch, and it never raises
        elif et == "position":
            if self._ingest_position(ent):
                self._notify_mine(et, self._positions[ent["contractId"]])
        elif et == "cashBalance":
            if self._ingest_cash(ent):
                self._notify_mine(et, self._cash)

    def _owner(self, et: str, ent: dict):
        """The account an entity belongs to. orderVersion and fill pushes
        carry no accountId: their order's, or ours when WE placed it."""
        acct = ent.get("accountId")
        if acct is None and et in ("orderVersion", "fill"):
            oid = ent.get("orderId")
            acct = (self._orders.get(oid) or {}).get("accountId")
            if acct is None and oid in self._order_symbols:
                acct = self._acct_num
        return acct

    def _notify_mine(self, et: str, ent: dict) -> None:
        try:
            if self._listeners and self._acct_num is not None \
                    and self._owner(et, ent) == self._acct_num:
                self._notify(et, dict(ent))
        except Exception as e:  # noqa: BLE001 — never break the socket reader
            _log(f"{self.account_id}: listener dispatch error: {e}")

    def _name_order_contract(self, et: str, oid, ent: dict) -> None:
        """Name the contract of one of THIS account's orders the way the fill
        path does: an order WE placed names its own contract, else one
        contract/item lookup in the background. Left unresolved on failure:
        trade_view then shows it by what we placed, or with no symbol."""
        cid = ent.get("contractId")
        if cid is None or cid in self._contracts or self._acct_num is None:
            return
        if self._owner(et, ent) != self._acct_num:
            return
        sym = self._order_symbols.get(oid)
        if sym:
            self._contracts[cid] = sym
        else:
            self._want_contract(cid)

    def _ingest_position(self, ent: dict) -> bool:
        cid = ent.get("contractId")
        if self._acct_num is None or ent.get("accountId") != self._acct_num or cid is None:
            return False
        self._positions[cid] = {**self._positions.get(cid, {}), **ent}
        self._pos_pushed.add(cid)
        if cid not in self._contracts:
            self._want_contract(cid)
        return True

    def _ingest_cash(self, ent: dict) -> bool:
        if self._acct_num is None or ent.get("accountId") != self._acct_num:
            return False
        self._cash = {**self._cash, **ent}
        self._cash_pushed = True
        return True

    def _want_contract(self, cid) -> None:
        """Resolve an unseen contract name in the background (a position or
        order push may name only its contractId). No running loop -> leave it
        unresolved."""
        if cid in self._contract_lookups or self._ws is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._contract_lookups.add(cid)
        t = loop.create_task(self._lookup_contract(cid))
        self._lookup_tasks.add(t)
        t.add_done_callback(self._lookup_tasks.discard)

    async def _lookup_contract(self, cid, *, announce: bool = True) -> None:
        try:
            c = await self._ws.contract_item(cid)
            name = (c or {}).get("name")
            if name:
                self._contracts[cid] = name
                if not announce:
                    return
                if cid in self._positions:
                    self._notify_mine("position", self._positions[cid])
                for oid, o in list(self._orders.items()):
                    o_cid = o.get("contractId") or self._order_versions.get(oid, {}).get("contractId")
                    if o_cid == cid and o.get("ordStatus") in self._WORKING_STATUSES:
                        self._notify_mine("order", o)
        except Exception as e:  # noqa: BLE001 — shown unresolved; chart trading refuses meanwhile
            _log(f"{self.account_id}: contract/item {cid} failed: {e}")
        finally:
            self._contract_lookups.discard(cid)

    def _stop_seed(self) -> None:
        """Forget the caches' seeded state and stop any seed still reading the
        OLD socket, so a stale snapshot can never mark the new one seeded."""
        self.caches_seeded = False
        if self._seed_task is not None and not self._seed_task.done():
            self._seed_task.cancel()

    def _schedule_seed(self) -> None:
        """Positions + cash read in the BACKGROUND after a (re)connect: it
        never delays the connect the 9:30 bot is waiting on."""
        try:
            if self._seed_task is not None and not self._seed_task.done():
                self._seed_task.cancel()
            self._seed_task = asyncio.create_task(self._seed_caches())
        except Exception as e:  # noqa: BLE001 — chart trading stays unseeded, the connect stands
            _log(f"{self.account_id}: cache seed not scheduled: {e}")

    async def _seed_caches(self) -> None:
        """Positions and cash balance for THIS account, once per (re)connect;
        pushes keep them current after. A failed read is audited and retried
        (1 s, 2 s, 4 s ... at most 60 s apart; only the part that failed)
        until both landed or the adapter disconnects. caches_seeded stays
        False meanwhile, and chart trading refuses this account."""
        ws = self._ws
        pos_done = cash_done = False
        delay, attempt = 1.0, 0
        while True:
            attempt += 1
            try:
                if not pos_done:
                    self._pos_pushed.clear()
                    positions = await ws.position_list()
                    me = self._acct_num
                    snap = {p["contractId"]: p for p in positions or []
                            if isinstance(p, dict) and p.get("accountId") == me
                            and p.get("contractId") is not None}
                    # a push that landed while the read was in flight is NEWER
                    # than the snapshot: keep it (a fill must never read flat)
                    snap.update({c: self._positions[c] for c in self._pos_pushed
                                 if c in self._positions})
                    self._positions = snap
                    pos_done = True
                if not cash_done:
                    self._cash_pushed = False
                    cash = await ws.cash_balance_list()
                    me = self._acct_num
                    if not self._cash_pushed:
                        self._cash = next((b for b in cash or []
                                           if isinstance(b, dict) and b.get("accountId") == me), {})
                    cash_done = True
                break
            except Exception as e:  # noqa: BLE001
                _log(f"{self.account_id}: cache seed failed (attempt {attempt}, "
                     f"retry in {delay:g}s): {e}")
                self.audit({"event": "cache_seed_error", "account": self.account_id,
                            "attempt": attempt, "retry_in_s": delay,
                            "error": str(e)[:200]})
            await self._seed_sleep(delay)
            delay = min(delay * 2, _SEED_BACKOFF_CAP)
            if not self.connected or self._ws is not ws:
                return
        for cid in [c for c in self._positions if c not in self._contracts]:
            await self._lookup_contract(cid, announce=False)   # "sync" covers it
        if self._ws is not ws:
            return                         # the socket was replaced: its own seed runs
        self.caches_seeded = True
        self._notify("sync", {})

    def _enqueue_fill(self, ent: dict) -> None:
        """Queue a fill for the consumer; a full queue is surfaced as an audit
        event (a dropped fill = a silently un-copied trade), not just a log line."""
        try:
            self._fill_q.put_nowait(ent)
        except asyncio.QueueFull:
            fid = ent.get("id")
            _log(f"{self.account_id}: fill queue full, dropping fill {fid}")
            self.audit({"event": "fill_dropped", "account": self.account_id,
                        "fill_id": fid})

    async def observe_fills(self, on_fill: FillCallback) -> None:
        self._on_fill = on_fill
        if self._consumer is None:
            self._consumer = asyncio.create_task(self._consume_fills())
        self.audit({"event": "observing_fills", "account": self.account_id,
                    "tradovate_account": self._acct_name})

    async def _consume_fills(self) -> None:
        while True:
            ent = await self._fill_q.get()
            try:
                fe = await self._build_fill_event(ent)
                if fe and self._on_fill:
                    await self._on_fill(fe)
            except Exception as e:
                _log(f"{self.account_id}: fill dispatch error: {e}")
                self.audit({"event": "fill_error", "account": self.account_id,
                            "error": str(e)})

    async def _build_fill_event(self, ent: dict) -> Optional[FillEvent]:
        fid = ent.get("id")
        order_id = ent.get("orderId")
        order = await self._lookup_order(order_id)
        contract_id = ent.get("contractId") or (order or {}).get("contractId")

        # Real-time fill pushes are often partial — they can omit contractId
        # (and sometimes orderId/qty/action). Re-fetch the full fill entity to
        # recover the missing fields before giving up.
        if (contract_id is None or ent.get("qty") is None) and fid is not None:
            try:
                full = await self._ws.fill_item(fid)
            except Exception as e:
                _log(f"{self.account_id}: fill/item {fid} failed: {e}")
                full = None
            if isinstance(full, dict):
                ent = {**full, **{k: v for k, v in ent.items() if v is not None}}
                contract_id = contract_id or full.get("contractId")
                if order is None and full.get("orderId") is not None:
                    order_id = full.get("orderId")
                    order = await self._lookup_order(order_id)

        acct_id = (order or {}).get("accountId")
        if acct_id is not None and self._acct_num is not None and acct_id != self._acct_num:
            return None  # fill belongs to another account under the same login

        symbol = self._contracts.get(contract_id, "") if contract_id is not None else ""
        if not symbol and order_id is not None:
            # An order WE placed names its own contract — the sibling cancel
            # never waits on (or dies with) a network lookup.
            symbol = self._order_symbols.get(order_id, "")
            if symbol and contract_id is not None:
                self._contracts[contract_id] = symbol
        if not symbol and contract_id is not None:
            try:
                c = await self._ws.contract_item(contract_id)
                symbol = (c or {}).get("name", "")
                if symbol:
                    self._contracts[contract_id] = symbol
            except Exception as e:
                _log(f"{self.account_id}: contract/item {contract_id} failed: {e}")
        if not symbol:
            # Deliver it anyway: the engine matches its entry legs on the
            # order id, not the name. Dropping it here is how the 2026-09-21
            # sell stop kept resting after the buy stop filled.
            _log(f"{self.account_id}: unresolved symbol for fill {fid} "
                 f"(contractId={contract_id}, orderId={order_id}, "
                 f"keys={sorted(ent.keys())}) — delivering by order id")
        qty = int(ent.get("qty") or 0)
        if qty <= 0:
            return None
        return FillEvent(
            account_id=self.account_id,
            symbol=symbol,
            side="Buy" if str(ent.get("action", "")).lower() == "buy" else "Sell",
            qty=qty,
            price=ent.get("price"),
            ts=time.time(),
            # always carry the RESOLVED order id: real-time fill pushes are
            # partial and may omit it, and the engine matches the straddle's
            # entry legs on raw["orderId"] to cancel the sibling.
            raw={**ent, "orderId": order_id} if order_id is not None else ent,
        )

    async def _lookup_order(self, order_id) -> Optional[dict]:
        """Return the cached order for `order_id`, fetching it once if needed."""
        if order_id is None:
            return None
        order = self._orders.get(order_id)
        if order is not None:
            return order
        try:
            order = await self._ws.order_item(order_id)
        except Exception as e:
            _log(f"{self.account_id}: order/item {order_id} failed: {e}")
            return None
        if isinstance(order, dict) and "id" in order:
            self._orders[order["id"]] = order
            return order
        return None

    # ------------------------------------------------------------ follower ops
    async def place_order(self, req: OrderRequest) -> OrderResult:
        if self._ws is None or self._acct_num is None:
            return OrderResult(ok=False, error="adapter not connected")
        if _stoplimit_incomplete(req):
            return OrderResult(ok=False, error=STOPLIMIT_INCOMPLETE)
        sym = symbols.resolve_contract(req.symbol)
        if self.live:
            _log(f"{self.account_id}: LIVE ORDER {req.side} {req.qty} {sym}")
        # a StopLimit's stopPrice is its TRIGGER, never the bracket's SL
        stop = req.trigger_price if req.order_type == "StopLimit" else req.stop_price
        try:
            d = await self._ws.place_order(
                account_id=self._acct_num, symbol=sym, side=req.side,
                qty=req.qty, order_type=req.order_type,
                time_in_force=req.time_in_force, price=req.price,
                stop_price=stop, text=req.text,
                account_spec=self._acct_name or None,
            )
            oid = d.get("orderId") if isinstance(d, dict) else None
            if oid is None:
                reason = _reject_reason(d) or "order rejected (no orderId returned)"
                _log(f"{self.account_id}: order rejected: {reason}")
                return OrderResult(ok=False, error=reason,
                                   raw=d if isinstance(d, dict) else {})
            self._order_symbols[int(oid)] = sym
            return OrderResult(ok=True, order_id=str(oid),
                               raw=d if isinstance(d, dict) else {})
        except Exception as e:
            return OrderResult(ok=False, error=str(e))

    async def place_bracket(self, req: OrderRequest) -> OrderResult:
        """Entry + protective stop/target as a single Tradovate OSO, so the
        broker manages the one-cancels-other and the protection survives a
        disconnect. NEVER legs: the old legged fallback rested the protective
        stop at once — for a stop ENTRY that is the wrong side of price, an
        instant unwanted trade. A failed OSO is a failed leg; the engine then
        cancels the other leg."""
        if self._ws is None or self._acct_num is None:
            return OrderResult(ok=False, error="adapter not connected")
        if req.stop_price is None and req.tp_price is None:
            return await self.place_order(req)
        if _stoplimit_incomplete(req):
            return OrderResult(ok=False, error=STOPLIMIT_INCOMPLETE)
        sym = symbols.resolve_contract(req.symbol)
        if self.live:
            _log(f"{self.account_id}: LIVE BRACKET {req.side} {req.qty} {sym} "
                 f"stop={req.stop_price} tp={req.tp_price}")
        try:
            d = await self._ws.place_oso(
                account_id=self._acct_num, symbol=sym, side=req.side,
                qty=req.qty, stop_price=req.stop_price, tp_price=req.tp_price,
                entry_type=req.order_type, entry_price=req.price,
                entry_trigger_price=req.trigger_price,
                time_in_force=req.time_in_force, text=req.text,
                account_spec=self._acct_name or None)
            oid = d.get("orderId") if isinstance(d, dict) else None
            if oid is None:
                # a 200 with no orderId is a logical reject
                reason = _reject_reason(d) or "OSO rejected (no orderId returned)"
                _log(f"{self.account_id}: OSO rejected: {reason}")
                return OrderResult(ok=False, error=reason,
                                   raw=d if isinstance(d, dict) else {})
            # The OSO's brackets are broker-managed OCO. Their ids ride back so
            # the engine can re-price them to the actual fill: bracket1 is the
            # stop when there is one (see place_oso).
            self._order_symbols[int(oid)] = sym
            raw = d if isinstance(d, dict) else {}
            b1, b2 = raw.get("oso1Id"), raw.get("oso2Id")
            sl_id, tp_id = (b1, b2) if req.stop_price is not None else (None, b1)
            return OrderResult(ok=True, order_id=str(oid),
                               raw={**raw, "sl_order_id": sl_id, "tp_order_id": tp_id})
        except Exception as e:
            # incl. a timeout, where the OSO may exist at the broker — loud
            _log(f"{self.account_id}: OSO failed: {e}")
            return OrderResult(ok=False, error=f"OSO failed: {e}")

    async def place_oco(self, symbol: str, exit_side: str, qty: int, stop_price: float,
                        limit_price: float, *, text: str = "homebase:chart-exit",
                        time_in_force: str = "GTC") -> OrderResult:
        """An SL (Stop) + TP (Limit) pair for an existing position as ONE
        Tradovate OCO (order/placeoco): the broker cancels the survivor. A 200
        with no orderId is a logical reject; a reply with the Stop's id but no
        ocoId is reported NOT ok (the Limit's fate is unknown), with the Stop's
        id kept in raw so the caller can see what may be working. Whenever the
        pair MAY exist at the broker (an exception or timeout, or that half
        answer) raw["outcome_unknown"] is True: the caller must not assume
        nothing is working."""
        if self._ws is None or self._acct_num is None:
            return OrderResult(ok=False, error="adapter not connected")
        sym = symbols.resolve_contract(symbol)
        if self.live:
            _log(f"{self.account_id}: LIVE OCO {exit_side} {qty} {sym} "
                 f"stop={stop_price} limit={limit_price}")
        try:
            d = await self._ws.place_oco(
                account_id=self._acct_num, symbol=sym, exit_side=exit_side, qty=qty,
                stop_price=stop_price, limit_price=limit_price,
                time_in_force=time_in_force, text=text,
                account_spec=self._acct_name or None)
        except Exception as e:
            # incl. a timeout, where the pair may exist at the broker — loud
            _log(f"{self.account_id}: OCO failed: {e}")
            return OrderResult(ok=False, error=f"OCO failed: {e}", raw={"outcome_unknown": True})
        raw = d if isinstance(d, dict) else {}
        oid, other = raw.get("orderId"), raw.get("ocoId")
        if oid is None:
            reason = _reject_reason(raw) or "OCO rejected (no orderId returned)"
            _log(f"{self.account_id}: OCO rejected: {reason}")
            return OrderResult(ok=False, error=reason, raw=raw)
        self._order_symbols[int(oid)] = sym
        if other is None:
            _log(f"{self.account_id}: OCO answered without its Limit's id: {raw}")
            return OrderResult(ok=False, order_id=str(oid),
                               error="OCO answered without the target's id — check the orders",
                               raw={**raw, "sl_order_id": str(oid), "tp_order_id": None,
                                    "outcome_unknown": True})
        self._order_symbols[int(other)] = sym
        return OrderResult(ok=True, order_id=str(oid),
                           raw={**raw, "sl_order_id": str(oid), "tp_order_id": str(other)})

    async def get_protective_orders(self, symbol: str) -> list[dict]:
        """Resting Stop/Limit orders on this account for `symbol`, read from the
        WS entity cache (order + latest orderVersion). Lets the engine mirror a
        Tradovate leader's stop/target onto the followers."""
        if self._ws is None or self._acct_num is None:
            return []
        try:
            c = await self._ws.contract_find(symbols.resolve_contract(symbol))
        except Exception:
            c = None
        cid = (c or {}).get("id")
        out: list[dict] = []
        for oid, o in list(self._orders.items()):
            if o.get("accountId") != self._acct_num:
                continue
            if o.get("ordStatus") not in self._WORKING_STATUSES:
                continue
            ov = self._order_versions.get(oid, {})
            o_cid = o.get("contractId") or ov.get("contractId")
            if cid is not None and o_cid is not None and o_cid != cid:
                continue
            otype = ov.get("orderType") or o.get("orderType")
            side = o.get("action") or ov.get("action")
            qty = ov.get("orderQty") or o.get("orderQty")
            if otype == "Stop":
                out.append({"order_id": str(oid), "kind": "stop", "side": side,
                            "price": ov.get("stopPrice") or o.get("stopPrice"),
                            "qty": qty})
            elif otype == "Limit":
                out.append({"order_id": str(oid), "kind": "target", "side": side,
                            "price": ov.get("price") or o.get("price"), "qty": qty})
        return out

    # ------------------------------------------------------------ chart trading
    def contract_name(self, contract_id) -> Optional[str]:
        return self._contracts.get(contract_id)

    async def contract_id(self, symbol: str) -> int:
        """The contract id for a root or contract, from the cache or one
        contract/find (cached after)."""
        name = symbols.resolve_contract(symbol)
        for cid, n in list(self._contracts.items()):
            if n == name:
                return cid
        c = await self._ws.contract_find(name)
        cid = (c or {}).get("id")
        if cid is None:
            raise RuntimeError(f"no contract found for {name}")
        self._contracts[cid] = name
        return cid

    def trade_view(self) -> dict:
        """Positions, working orders and cash for THIS account, from the pushed
        caches only (no broker call). `seeded` is False until the (re)connect's
        position/cash read landed. An order whose contract is still unnamed
        shows the contract WE placed it on, else symbol None."""
        me = self._acct_num
        positions = [{"contract_id": cid, "symbol": self._contracts.get(cid),
                      "net": int(p.get("netPos") or 0), "avg_price": p.get("netPrice")}
                     for cid, p in self._positions.items() if int(p.get("netPos") or 0)]
        orders = []
        for oid, o in self._orders.items():
            if me is None or o.get("accountId") != me \
                    or o.get("ordStatus") not in self._WORKING_STATUSES:
                continue
            ov = self._order_versions.get(oid, {})
            cid = o.get("contractId") or ov.get("contractId")
            row = {
                "order_id": str(oid),
                "symbol": ((self._contracts.get(cid) if cid is not None else None)
                           or self._order_symbols.get(oid)),
                "side": o.get("action") or ov.get("action"),
                "type": ov.get("orderType") or o.get("orderType"),
                "qty": ov.get("orderQty") or o.get("orderQty"),
                "price": ov.get("price") if ov.get("price") is not None else o.get("price"),
                "stop_price": (ov.get("stopPrice") if ov.get("stopPrice") is not None
                               else o.get("stopPrice")),
                "status": o.get("ordStatus"),
                "tif": ov.get("timeInForce") or o.get("timeInForce") or None}
            if o.get("parentId") is not None:
                # an OSO bracket leg's entry (Tradovate's Order.parentId): the page checks a pending leg's
                # move against that entry's price (review round 2, C); absent -> the page refuses the move
                row["parent_id"] = str(o["parentId"])
            if row["type"] == "StopLimit":
                row["trigger"] = row["stop_price"]     # price = the limit, trigger = stopPrice
            orders.append(row)
        return {"broker_account": self._acct_name or None, "pinned": self.pinned_ok,
                "seeded": self.caches_seeded, "balance": self._cash.get("amount"),
                "realized_pnl": self._cash.get("realizedPnL"),
                "positions": sorted(positions, key=lambda p: str(p["symbol"])),
                "orders": sorted(orders, key=lambda o: o["order_id"])}

    async def cancel_symbol(self, symbol: str, *, exclude=()) -> OrderResult:
        """Cancel THIS account's working orders in ONE contract (from the
        pushed order cache), except the ids in `exclude`. An order with no
        contract id is matched by the contract WE placed it on; one still
        unknown is left alone, counted in raw["unknown_contract"], and makes
        the result not ok (it may be this contract's)."""
        if self._ws is None or self._acct_num is None:
            return OrderResult(ok=False, error="adapter not connected")
        try:
            cid = await self.contract_id(symbol)
        except Exception as e:  # noqa: BLE001
            return OrderResult(ok=False, error=f"no contract for {symbol}: {e}")
        name = self._contracts.get(cid)
        skip = {str(x) for x in exclude}
        ids, unknown = [], 0
        for oid, o in list(self._orders.items()):
            if o.get("accountId") != self._acct_num \
                    or o.get("ordStatus") not in self._WORKING_STATUSES \
                    or str(oid) in skip:
                continue
            o_cid = o.get("contractId") or self._order_versions.get(oid, {}).get("contractId")
            if o_cid is None:
                placed_on = self._order_symbols.get(oid)
                if placed_on is None:
                    unknown += 1
                elif placed_on == name:
                    ids.append(oid)
            elif o_cid == cid:
                ids.append(oid)
        res = await asyncio.gather(*(self.cancel_order_by_id(str(i)) for i in ids),
                                   return_exceptions=True)
        errors = [f"{i}: {r if isinstance(r, Exception) else r.error}"
                  for i, r in zip(ids, res) if isinstance(r, Exception) or not r.ok]
        failed = len(errors)
        if unknown:
            errors.append(f"{unknown} working order(s) with an unknown contract left working")
        return OrderResult(ok=not errors, error="; ".join(errors) or None,
                           raw={"cancelled": len(ids) - failed,
                                "ids": [str(i) for i in ids], "unknown_contract": unknown})

    async def flatten_symbol(self, symbol: str) -> OrderResult:
        """Close THIS account's position in ONE contract, then cancel only that
        contract's working orders. Position read from the broker (unreadable is
        not flat -> nothing done); the market order must be accepted before
        anything is cancelled, so a refused order leaves the stop working."""
        if self._ws is None or self._acct_num is None:
            return OrderResult(ok=False, error="adapter not connected")
        try:
            net = await self.get_net_position(symbol)
        except Exception as e:  # noqa: BLE001
            return OrderResult(ok=False, error=f"position unreadable ({e}) — nothing done")
        raw: dict = {"net_before": net}
        if net:
            r = await self.place_order(OrderRequest(
                symbol=symbol, side="Sell" if net > 0 else "Buy", qty=abs(net),
                order_type="Market", text="homebase:chart-flat"))
            raw["market"] = {"ok": r.ok, "order_id": r.order_id, "error": r.error}
            if not r.ok:
                return OrderResult(ok=False, raw=raw,
                                   error=f"flatten order refused: {r.error} — orders left working")
        own = [r.order_id] if net and r.order_id else []
        c = await self.cancel_symbol(symbol, exclude=own)   # never its own market order
        raw["cancel"] = {"ok": c.ok, "error": c.error, **(c.raw or {})}
        return OrderResult(ok=c.ok, error=c.error, raw=raw)

    async def cancel_order_by_id(self, order_id: str) -> OrderResult:
        if self._ws is None:
            return OrderResult(ok=False, error="adapter not connected")
        try:
            d = await self._ws.cancel_order(int(order_id))
        except Exception as e:
            return OrderResult(ok=False, error=str(e))
        # a 200 carrying a failure text is a refused cancel, not a success
        raw = d if isinstance(d, dict) else {}
        reason = _reject_reason(raw) or str(raw.get("errorText") or "").strip()
        if reason:
            return OrderResult(ok=False, error=reason, raw=raw)
        return OrderResult(ok=True, raw=raw)

    async def modify_order(self, order_id: str, order_type: str, *,
                           price: Optional[float] = None,
                           stop_price: Optional[float] = None,
                           qty: Optional[int] = None) -> OrderResult:
        """Re-price one resting order. The qty sent is the order's OWN, from
        its pushed version, so a bracket is never resized by accident; `qty`
        is only the fallback. A 200 carrying a failure text is a reject."""
        if self._ws is None:
            return OrderResult(ok=False, error="adapter not connected")
        try:
            oid = int(order_id)
        except (TypeError, ValueError):
            return OrderResult(ok=False, error=f"bad order id {order_id!r}")
        q = (self._order_versions.get(oid) or {}).get("orderQty") or qty
        if not q:
            return OrderResult(ok=False, error="order qty unknown — not modifying")
        try:
            d = await self._ws.modify_order(oid, order_type=order_type, qty=int(q),
                                            price=price, stop_price=stop_price)
        except Exception as e:
            return OrderResult(ok=False, error=str(e))
        raw = d if isinstance(d, dict) else {}
        reason = _reject_reason(raw) or str(raw.get("errorText") or "").strip()
        if reason:
            return OrderResult(ok=False, error=reason, raw=raw)
        return OrderResult(ok=True, order_id=str(oid), raw=raw)

    async def flatten_all(self) -> OrderResult:
        if self._ws is None or self._acct_num is None:
            return OrderResult(ok=False, error="adapter not connected")
        try:
            errors: list[str] = []
            n = 0
            for p in await self._ws.position_list():
                if p.get("accountId") != self._acct_num:
                    continue
                if not (p.get("netPos") or 0):
                    continue
                try:
                    await self._ws.liquidate_position(
                        account_id=self._acct_num, contract_id=p.get("contractId"))
                    n += 1
                except Exception as e:
                    errors.append(str(e))
            if errors:
                return OrderResult(ok=False, error="; ".join(errors), raw={"flattened": n})
            return OrderResult(ok=True, raw={"flattened": n})
        except Exception as e:
            return OrderResult(ok=False, error=str(e))

    async def cancel_all(self) -> OrderResult:
        if self._ws is None or self._acct_num is None:
            return OrderResult(ok=False, error="adapter not connected")
        try:
            await self._ws.cancel_all_orders(self._acct_num)
            return OrderResult(ok=True)
        except Exception as e:
            return OrderResult(ok=False, error=str(e))

    # ------------------------------------------------------------ reads
    def request_rtts_ms(self, since: float) -> dict[str, float]:
        """Timing only: {endpoint: round trip ms} of this socket's requests answered
        after `since` (time.perf_counter), the latest per endpoint. No broker call."""
        ws = self._ws
        rtts = getattr(ws, "rtts", None) if ws is not None else None
        return {ep: ms for done, ep, ms in list(rtts or ()) if done >= since}

    async def get_net_position(self, symbol: str) -> int:
        """Net position in `symbol`. RAISES when it can't be read: an
        unreadable position is not flat (a swallowed 404 once read as 0 for a
        week, and would let a flatten cancel a live position's stop)."""
        if self._ws is None or self._acct_num is None:
            raise RuntimeError("adapter not connected")
        c = await self._ws.contract_find(symbols.resolve_contract(symbol))
        cid = (c or {}).get("id")
        if cid is None:
            raise RuntimeError(f"no contract found for {symbol}")
        for p in await self._ws.position_list():
            if p.get("accountId") == self._acct_num and p.get("contractId") == cid:
                return int(p.get("netPos") or 0)
        return 0

    async def get_order_status(self, order_id: str) -> Optional[str]:
        """ordStatus (Working / Filled / Canceled / ...) of one order: the
        pushed entity cache first, else one order/item read, cached after."""
        try:
            oid = int(order_id)
        except (TypeError, ValueError):
            return None
        o = self._orders.get(oid) or {}
        if not o.get("ordStatus") and self._ws is not None:
            try:
                full = await self._ws.order_item(oid)
            except Exception:
                return None
            if isinstance(full, dict) and "id" in full:
                o = self._orders[oid] = {**full, **o}
        return o.get("ordStatus")

    async def get_order_state(self, order_id: str) -> dict:
        """Status + contracts KNOWN filled: the fills seen for this order, or
        None when none were seen (no fill seen is not "no fill": a push can
        be missed). Only the per-strategy kill reads it."""
        status = await self.get_order_status(order_id)
        try:
            n = self._order_filled.get(int(order_id), 0)
        except (TypeError, ValueError):
            n = 0
        return {"status": status, "filled_qty": n or None}

    async def get_balance(self) -> dict:
        if self._ws is None or self._acct_num is None:
            return {}
        try:
            for b in await self._ws.cash_balance_list():
                if b.get("accountId") == self._acct_num:
                    return {"amount": b.get("amount"),
                            "realizedPnL": b.get("realizedPnL"),
                            "currencyId": b.get("currencyId")}
        except Exception:
            pass
        return {}

    _WORKING_STATUSES = {"Working", "PendingNew", "Pending", "Suspended", "PendingReplace"}

    async def get_metrics(self) -> dict:
        m = await super().get_metrics()
        m["account"] = self._acct_name or None
        if self._ws is None or self._acct_num is None:
            return m
        try:
            bal = await self.get_balance()
            m["balance"] = bal.get("amount")
            m["realized_pnl"] = bal.get("realizedPnL")
        except Exception:
            pass
        try:
            positions = []
            for p in await self._ws.position_list():
                if p.get("accountId") != self._acct_num:
                    continue
                net = int(p.get("netPos") or 0)
                if net == 0:
                    continue
                cid = p.get("contractId")
                symbol = self._contracts.get(cid, "") if cid is not None else ""
                if not symbol and cid is not None:
                    try:
                        c = await self._ws.contract_item(cid)
                        symbol = (c or {}).get("name", "")
                        if symbol:
                            self._contracts[cid] = symbol
                    except Exception:
                        pass
                positions.append({"symbol": symbol or f"#{cid}", "net": net})
            m["open_positions"] = positions
            m["open_position_count"] = len(positions)
        except Exception:
            pass
        # Working orders: count from the cache, scoped to this account.
        m["working_orders"] = sum(
            1 for o in self._orders.values()
            if o.get("accountId") == self._acct_num
            and o.get("ordStatus") in self._WORKING_STATUSES
        )
        return m

    # ------------------------------------------------------------ token refresh
    async def _renew_if_needed(self) -> bool:
        """Keep the access token fresh; drop the socket if it rolled.

        Tradovate ties a WebSocket session to the access token it was authorized
        with and rejects re-authorizing a *live* socket (``404 Not found:
        authorize``) — the previous in-place re-auth failed on every token cycle,
        so the refreshed token never reached the socket and Tradovate closed it
        at expiry, mid-trade. Instead, when the token rolls we close the
        stale-token socket so the engine's connection supervisor rebuilds it on
        the fresh token (a clean reconnect that also recovers any fill missed in
        the gap). Returns True if the socket was dropped for renewal.

        WHEN is renewal_due()'s rule: an early renewal 09:10-09:20 ET on weekdays
        so that none is due 09:20-09:35; in there only a token that would expire
        anyway is renewed, and a socket that lives through the 09:28-09:31 fire
        guard is never dropped. A failed renewal raises and drops nothing (the
        token did not roll); a socket the supervisor replaced meanwhile is left alone."""
        tokens = self._auth.tokens
        expires_at = tokens.expires_at_unix if tokens else 0.0
        now = self._now()
        due, why = renewal_due(now, expires_at)
        clock = now.astimezone(ET).strftime("%H:%M:%S ET")
        if not due:
            if why != "normal" and expires_at - now.timestamp() < RENEW_BUFFER_S:
                # held against the normal rule: only when every early renewal failed
                until = dt.datetime.fromtimestamp(expires_at, ET).strftime("%H:%M:%S") \
                    if expires_at else "an unknown time"
                _log(f"{self.account_id}: token renewal held at {clock} ({why}) — "
                     f"it expires at {until} ET")
            return False
        ws, before = self._ws, self._auth.access_token
        # a renewal only the early rule asks for (RENEW_BUFFER_S still left): renew only --
        # never spend a (rate-limited) login on it; a failure retries at the next check
        extra = why == "early" and expires_at - now.timestamp() >= RENEW_BUFFER_S
        await asyncio.to_thread(self._auth.renew if extra else self._auth.refresh)
        after = self._auth.access_token
        if not after or after == before or ws is None:
            return False
        landed = self._now()
        if carries_the_guard(landed, expires_at):
            # the answer came late (a slow renewal, a login fallback), inside the fire guard,
            # and the socket's old token lives past it: no drop here. The socket stays on
            # that token; it is rebuilt on the new one when Tradovate closes it at expiry.
            self.audit({"event": "token_renewed", "account": self.account_id, "why": why,
                        "socket_kept": True})
            _log(f"{self.account_id}: token renewed at {clock} ({why}), answered at "
                 f"{landed.astimezone(ET).strftime('%H:%M:%S')} ET inside the fire guard "
                 "— the socket stays on its old token until it expires")
            return False
        if ws is not self._ws:
            return False    # the supervisor rebuilt the socket meanwhile: not ours to drop
        self.audit({"event": "token_renewed", "account": self.account_id, "why": why})
        _log(f"{self.account_id}: token renewed at {clock} ({why}) — rebuilding the socket")
        try:
            await ws.close()
        except Exception:
            pass
        return True

    async def _keepalive_loop(self) -> None:
        try:
            while self._connected:
                await asyncio.sleep(60)
                if not self.connected:
                    continue   # socket down; the engine supervisor owns reconnect
                try:
                    await self._renew_if_needed()
                except Exception as e:
                    _log(f"{self.account_id}: keepalive error: {e}")
                    self.audit({"event": "keepalive_error",
                                "account": self.account_id, "error": str(e)})
        except asyncio.CancelledError:
            return
