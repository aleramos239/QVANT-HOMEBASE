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

import datetime as dt
import logging
import math
import uuid
from typing import Optional

import httpx

from .. import symbols
from ..contracts import root_of
from .base import AccountNotOnLogin, BrokerAdapter, FillCallback, OrderRequest, OrderResult
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
POSITION_FIELD = "positionSize"                         # unconfirmed: signed, + long / - short


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
        if self not in s.listeners:
            s.listeners.append(self)
        if s.hub is None:
            s.hub = TsxHub(s, _fan_events(s), on_up=_fan_up(s))
            await s.hub.start()

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
        self._on_fill = on_fill                         # the socket's fills feed it (a later task)

    def _on_event(self, target: str, arg: dict) -> None:
        """One pushed event from the shared socket (a later task)."""

    async def _on_up(self) -> None:
        """The shared socket (re)opened (a later task)."""

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
            held = [cid for cid, n in await self._held(symbol) if n]
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
    async def _held(self, symbol: str) -> list[tuple[str, int]]:
        """[(contract id, signed size)] of this account's positions in the symbol's market (a root = every month)."""
        s = str(symbol or "").strip().upper()
        root = root_of(s)
        if root not in CODES:
            raise ValueError(f"topstepx: unknown market {symbol!r}")
        prefix = f"CON.F.US.{CODES[root]}."
        exact = None if s == root else self.contract_id(s)
        out = []
        for p in await self._read(POSITIONS_PATH.format(account_id=self._acct_id), "positions"):
            cid = str(p.get("contractId", ""))
            if (cid == exact) if exact else cid.startswith(prefix):
                if p.get(POSITION_FIELD) is None:
                    raise RuntimeError(f"topstepx: position row has no {POSITION_FIELD}")
                out.append((cid, int(p[POSITION_FIELD])))
        return out

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
                    return {"amount": a.get(BALANCE_FIELD)}
        except Exception:  # noqa: BLE001
            pass
        return {}

    async def get_metrics(self) -> dict:
        """No broker request here (the dashboard polls it): the numbers come from the socket's pushes (a later task)."""
        m = await super().get_metrics()
        m["account"] = self._acct_row.get("name") or None
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


def _fan_up(session: TsxSession):
    async def on_up() -> None:
        for a in list(session.listeners):
            try:
                await a._on_up()
            except Exception as e:  # noqa: BLE001
                log.warning("topstepx %s: on_up failed (%s)", a.account_id, type(e).__name__)
    return on_up
