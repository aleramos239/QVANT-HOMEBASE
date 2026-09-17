"""One signal in, bracketed straddles out across the BOOK, clock-guarded flat.

A validated signal fans out to every account assigned to the strategy in
cfg.book, at that assignment's qty. Each (strategy, account) pair gets its
own day state; the one-trade-per-day rule is per strategy across the whole
book (a second signal is refused even if only some accounts placed).

Per (strategy, account), all times ET:

    idle --signal(armed)--> placed --entry fill--> live --SL/TP/flat--> done
                      \\--cancel_et, no fill--> done

Safety invariants (unchanged from the single-account engine):
  * geometry comes from the FROZEN config; the signal only carries prices
  * disarmed => everything is journaled, nothing is placed
  * both legs place or neither does (per account; a lone survivor is
    cancelled and that account's day is an error)
  * SL/TP ride ON the entry as a broker-side OSO — a dead app never leaves
    a naked position
  * the sibling entry is cancelled the moment one side fills; both-filled
    => flatten + cancel THAT account
  * after flat_et the clock force-flattens whatever is open, per account

Exits journal a gross P&L (points × point value × qty) so live metrics can
be aggregated straight from the journal. State survives restarts.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from dataclasses import asdict, dataclass
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from .broker.base import BrokerAdapter, FillEvent, OrderRequest
from .config import AppCfg, StrategyCfg, assignments
from .contracts import point_value
from .paths import state_dir

ET = ZoneInfo("America/New_York")
SPREAD_TOL_PTS = 0.05


def _hhmm(s: str) -> dt.time:
    h, m = s.split(":")
    return dt.time(int(h), int(m))


@dataclass
class DayState:
    strategy: str
    account: str
    date: str
    qty: int = 0
    status: str = "idle"               # idle|placed|live|done|error
    upper_id: Optional[str] = None
    lower_id: Optional[str] = None
    upper_px: Optional[float] = None
    lower_px: Optional[float] = None
    entry_side: Optional[str] = None
    entry_anchor: Optional[float] = None
    entry_fill: Optional[float] = None
    exit_reason: Optional[str] = None
    exit_fill: Optional[float] = None
    pnl: Optional[float] = None        # gross $, set at exit
    note: str = ""


class Engine:
    """Signals + broker fills + a clock -> DayStates and orders, per account.

    `adapters` maps account id -> BrokerAdapter (may grow at runtime as
    accounts connect). `now_fn` is injectable for tests (aware UTC)."""

    def __init__(self, cfg: AppCfg, adapters: dict[str, BrokerAdapter], *,
                 now_fn: Callable[[], dt.datetime] | None = None,
                 root=None):
        self.cfg = cfg
        self.adapters = adapters
        self._now = now_fn or (lambda: dt.datetime.now(dt.timezone.utc))
        self._root = root or state_dir()
        self.states: dict[str, DayState] = {}   # "strategy@account" -> state
        self._load_today()

    # --- time & persistence -------------------------------------------------
    def now_et(self) -> dt.datetime:
        return self._now().astimezone(ET)

    def _today(self) -> str:
        return self.now_et().date().isoformat()

    def _day_path(self, date: str):
        return self._root / f"day-{date}.json"

    def _load_today(self) -> None:
        p = self._day_path(self._today())
        if p.exists():
            data = json.loads(p.read_text())
            self.states = {k: DayState(**v) for k, v in data.items()
                           if "account" in v}   # drop pre-book records

    def _save(self) -> None:
        p = self._day_path(self._today())
        p.write_text(json.dumps({k: asdict(v) for k, v in self.states.items()},
                                indent=2) + "\n")

    def journal(self, event: str, **data) -> None:
        rec = {"ts": time.time(), "et": self.now_et().isoformat(timespec="seconds"),
               "event": event, **data}
        with open(self._root / "journal.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")

    def _state(self, strategy: str, account: str) -> DayState:
        today = self._today()
        key = f"{strategy}@{account}"
        st = self.states.get(key)
        if st is None or st.date != today:
            st = DayState(strategy=strategy, account=account, date=today)
            self.states[key] = st
        return st

    def day_states(self, strategy: str) -> list[DayState]:
        today = self._today()
        return [s for s in self.states.values()
                if s.strategy == strategy and s.date == today]

    def day_status(self, strategy: str) -> str:
        """Aggregate day status across the book, for the one-per-day rule
        and the timer: idle only when NOTHING has happened yet today."""
        stats = {s.status for s in self.day_states(strategy)}
        for s in ("error", "live", "placed", "done"):
            if s in stats:
                return s
        return "idle"

    # --- the signal ----------------------------------------------------------
    async def handle_alert(self, payload: dict, *, force_window: bool = False,
                           source: str = "tv") -> dict:
        name = str(payload.get("strategy") or "")
        cfg = self.cfg.strategies.get(name)
        if cfg is None or not cfg.enabled:
            self.journal("alert_refused", strategy=name, reason="unknown_or_disabled")
            return {"ok": False, "reason": f"unknown or disabled strategy: {name!r}"}

        if self.day_status(name) != "idle":
            self.journal("alert_refused", strategy=name, reason="already_traded",
                         status=self.day_status(name), source=source)
            return {"ok": False,
                    "reason": f"already acted today (status={self.day_status(name)})"}

        now = self.now_et().time()
        if not force_window and \
                not (_hhmm(cfg.accept_from_et) <= now <= _hhmm(cfg.accept_until_et)):
            self.journal("alert_refused", strategy=name, reason="outside_window",
                         at=str(now), source=source)
            return {"ok": False, "reason": f"outside accept window at {now}"}

        try:
            upper = float(payload["upper"])
            lower = float(payload["lower"])
        except (KeyError, TypeError, ValueError):
            self.journal("alert_refused", strategy=name, reason="bad_prices",
                         payload=payload)
            return {"ok": False, "reason": "missing/invalid upper/lower"}
        if not (upper > lower):
            self.journal("alert_refused", strategy=name, reason="inverted_prices",
                         upper=upper, lower=lower)
            return {"ok": False, "reason": "upper must exceed lower"}
        spread_err = abs((upper - lower) - 2 * cfg.offset_pts)
        if spread_err > SPREAD_TOL_PTS:
            self.journal("alert_refused", strategy=name, reason="bad_spread",
                         upper=upper, lower=lower, expected=2 * cfg.offset_pts)
            return {"ok": False,
                    "reason": f"spread {upper - lower:g} != 2*offset {2 * cfg.offset_pts:g}"}

        asg = assignments(self.cfg, name)
        if not asg:
            self.journal("alert_refused", strategy=name, reason="no_assignments",
                         source=source)
            return {"ok": False,
                    "reason": "no accounts assigned to this strategy in the book"}

        if not self.cfg.armed:
            for a in asg:
                self.journal("dry_run", strategy=name, source=source,
                             account=a["account"], qty=int(a["qty"]),
                             upper=upper, lower=lower,
                             would_place=[asdict(r) for r in
                                          self._legs(cfg, upper, lower, int(a["qty"]))])
            return {"ok": True, "armed": False,
                    "note": "disarmed — journaled only", "accounts": len(asg)}

        results = {}
        t0 = time.time()
        for a in asg:
            results[a["account"]] = await self._place(
                name, cfg, a["account"], int(a["qty"]), upper, lower, source, t0)
        ok = any(r.get("ok") for r in results.values())
        return {"ok": ok, "armed": True, "accounts": results}

    @staticmethod
    def _legs(cfg: StrategyCfg, upper: float, lower: float,
              qty: int) -> list[OrderRequest]:
        return [
            OrderRequest(symbol=cfg.symbol, side="Buy", qty=qty,
                         order_type="Stop", price=upper,
                         stop_price=upper - cfg.sl_pts, tp_price=upper + cfg.tp_pts,
                         text="homebase:entry"),
            OrderRequest(symbol=cfg.symbol, side="Sell", qty=qty,
                         order_type="Stop", price=lower,
                         stop_price=lower + cfg.sl_pts, tp_price=lower - cfg.tp_pts,
                         text="homebase:entry"),
        ]

    async def _place(self, name: str, cfg: StrategyCfg, account: str, qty: int,
                     upper: float, lower: float, source: str,
                     t0: float | None = None) -> dict:
        st = self._state(name, account)
        ad = self.adapters.get(account)
        if ad is None or not ad.connected:
            st.status, st.exit_reason = "error", "error"
            st.note = "account not connected"
            self._save()
            self.journal("place_failed", strategy=name, account=account,
                         error="account not connected")
            return {"ok": False, "reason": "account not connected"}
        st.qty = qty
        buy, sell = self._legs(cfg, upper, lower, qty)
        r_up = await ad.place_bracket(buy)
        if not r_up.ok:
            st.status, st.exit_reason, st.note = "error", "error", f"upper leg: {r_up.error}"
            self._save()
            self.journal("place_failed", strategy=name, account=account,
                         leg="upper", error=r_up.error)
            return {"ok": False, "reason": f"upper leg rejected: {r_up.error}"}
        r_dn = await ad.place_bracket(sell)
        if not r_dn.ok:
            await ad.cancel_order_by_id(r_up.order_id)
            st.status, st.exit_reason, st.note = "error", "error", f"lower leg: {r_dn.error}"
            self._save()
            self.journal("place_failed", strategy=name, account=account,
                         leg="lower", error=r_dn.error, cancelled_upper=r_up.order_id)
            return {"ok": False, "reason": f"lower leg rejected: {r_dn.error}"}

        st.status = "placed"
        st.upper_id, st.lower_id = r_up.order_id, r_dn.order_id
        st.upper_px, st.lower_px = upper, lower
        self._save()
        self.journal("placed", strategy=name, account=account, source=source,
                     upper=upper, lower=lower, qty=qty,
                     upper_id=st.upper_id, lower_id=st.lower_id,
                     # anchor -> both legs acknowledged by the broker; the
                     # only latency the strategy is actually exposed to
                     place_ms=(None if t0 is None
                               else round((time.time() - t0) * 1000)))
        return {"ok": True, "upper_id": st.upper_id, "lower_id": st.lower_id}

    # --- broker fills ---------------------------------------------------------
    async def on_fill(self, ev: FillEvent) -> None:
        oid = str((ev.raw or {}).get("orderId") or "")
        for st in self.states.values():
            if ev.account_id and st.account != ev.account_id:
                continue
            cfg = self.cfg.strategies.get(st.strategy)
            ad = self.adapters.get(st.account)
            if cfg is None or ad is None:
                continue
            matches_leg = oid in (st.upper_id, st.lower_id)
            # Fallback: a partial fill push with no usable order id would
            # otherwise leave the opposite entry resting. If it is our symbol,
            # our account and an entry side, attribute it by side — cancelling
            # the wrong sibling only costs a trade, leaving one costs a
            # position.
            if st.status == "placed" and not matches_leg and not oid \
                    and ev.symbol and cfg.symbol.upper() in ev.symbol.upper() \
                    and ev.side in ("Buy", "Sell"):
                oid = st.upper_id if ev.side == "Buy" else st.lower_id
                matches_leg = bool(oid)
                self.journal("fill_matched_by_side", strategy=st.strategy,
                             account=st.account, side=ev.side, order_id=oid)
            if st.status == "placed" and matches_leg:
                sibling = st.lower_id if oid == st.upper_id else st.upper_id
                st.status = "live"
                st.entry_side = "Buy" if oid == st.upper_id else "Sell"
                st.entry_anchor = st.upper_px if oid == st.upper_id else st.lower_px
                st.entry_fill = ev.price
                self._save()
                r = await ad.cancel_order_by_id(sibling)
                self.journal("entry_fill", strategy=st.strategy, account=st.account,
                             side=st.entry_side, fill=ev.price, anchor=st.entry_anchor,
                             fill_vs_anchor=(None if ev.price is None or st.entry_anchor is None
                                             else round(ev.price - st.entry_anchor, 4)),
                             sibling_cancelled=r.ok, sibling_error=r.error)
                return
            if st.status == "live" and oid and oid in (st.upper_id, st.lower_id) \
                    and oid != self._entry_id(st):
                st.status, st.exit_reason = "error", "both_filled"
                self._save()
                await ad.cancel_all()
                await ad.flatten_all()
                self.journal("both_filled_emergency", strategy=st.strategy,
                             account=st.account, order_id=oid)
                return
            if st.status == "live" and ev.symbol and cfg.symbol.upper() in ev.symbol.upper() \
                    and ev.side != st.entry_side:
                st.status = "done"
                st.exit_fill = ev.price
                st.exit_reason = self._grade_exit(st, ev.price)
                st.pnl = self._gross_pnl(st, cfg)
                self._save()
                self.journal("exit_fill", strategy=st.strategy, account=st.account,
                             reason=st.exit_reason, fill=ev.price, pnl=st.pnl)
                return

    def _entry_id(self, st: DayState) -> Optional[str]:
        return st.upper_id if st.entry_side == "Buy" else st.lower_id

    def _grade_exit(self, st: DayState, px: Optional[float]) -> str:
        cfg = self.cfg.strategies[st.strategy]
        if px is None or st.entry_anchor is None:
            return "exit"
        sign = 1 if st.entry_side == "Buy" else -1
        tp = st.entry_anchor + sign * cfg.tp_pts
        sl = st.entry_anchor - sign * cfg.sl_pts
        return "tp" if abs(px - tp) <= abs(px - sl) else "sl"

    def _gross_pnl(self, st: DayState, cfg: StrategyCfg) -> Optional[float]:
        if st.entry_fill is None or st.exit_fill is None:
            return None
        sign = 1 if st.entry_side == "Buy" else -1
        pv = point_value(cfg.symbol) or 0.0
        return round(sign * (st.exit_fill - st.entry_fill) * pv * st.qty, 2)

    async def flatten_strategy(self, name: str) -> dict:
        """Manual flatten for ONE strategy: cancel its resting entries and
        market-flatten its symbol on every account it acted on today.
        Note: the position flatten is symbol-scoped per account — another
        strategy holding the same symbol on the same account would be
        flattened too (journaled)."""
        cfg = self.cfg.strategies.get(name)
        results: dict = {}
        for st in self.day_states(name):
            ad = self.adapters.get(st.account)
            if ad is None or cfg is None:
                continue
            acts = []
            if st.status == "placed":
                for oid in (st.upper_id, st.lower_id):
                    if oid:
                        r = await ad.cancel_order_by_id(oid)
                        acts.append(f"cancel {oid}: {'ok' if r.ok else r.error}")
            if st.status in ("placed", "live", "error"):
                try:
                    net = await ad.get_net_position(cfg.symbol)
                except Exception as e:  # noqa: BLE001
                    net, _ = 0, acts.append(f"net check failed: {e}")
                if net:
                    side = "Sell" if net > 0 else "Buy"
                    r = await ad.place_order(OrderRequest(
                        symbol=cfg.symbol, side=side, qty=abs(net),
                        order_type="Market", text="homebase:manual-flat"))
                    acts.append(f"flatten {net}: {'ok' if r.ok else r.error}")
            if st.status in ("placed", "live"):
                st.status, st.exit_reason = "done", "manual_flat"
            results[st.account] = acts
        self._save()
        self.journal("manual_flatten", strategy=name, results=results)
        return results

    # --- the clock ------------------------------------------------------------
    async def clock_tick(self) -> None:
        now = self.now_et().time()
        for st in list(self.states.values()):
            cfg = self.cfg.strategies.get(st.strategy)
            ad = self.adapters.get(st.account)
            if cfg is None or ad is None or st.date != self._today():
                continue
            if st.status == "placed" and now >= _hhmm(cfg.cancel_et):
                for oid in (st.upper_id, st.lower_id):
                    if oid:
                        await ad.cancel_order_by_id(oid)
                net = await ad.get_net_position(cfg.symbol)
                if net == 0:
                    st.status, st.exit_reason = "done", "no_fill"
                    self.journal("cancelled_unfilled", strategy=st.strategy,
                                 account=st.account)
                else:
                    st.status = "live"
                    st.note = "fill raced the 12:55 cancel"
                    self.journal("cancel_raced_fill", strategy=st.strategy,
                                 account=st.account, net=net)
                self._save()
            elif st.status == "live" and now >= _hhmm(cfg.flat_et):
                await ad.cancel_all()
                await ad.flatten_all()
                st.status, st.exit_reason = "done", st.exit_reason or "flat"
                self._save()
                self.journal("clock_flat", strategy=st.strategy, account=st.account)
