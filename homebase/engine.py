"""One alert in, one bracketed straddle out, clock-guarded to flat.

Day lifecycle per strategy (all times ET):

    idle --alert(armed)--> placed --entry fill--> live --SL/TP/flat--> done
                     \\--cancel_et, no fill--> done

Safety invariants:
  * geometry comes from the FROZEN config (offset/SL/TP/qty); the alert only
    carries the two entry prices and must match the config's offset spread
  * one trade per strategy per ET day, ever
  * disarmed => everything is journaled, nothing is placed
  * both legs place or neither does (a lone survivor is cancelled)
  * SL/TP ride ON the entry as a broker-side OSO — a dead app never leaves a
    naked position; brackets are anchored at the entry trigger price (a
    slipped fill shifts them by the slip — journaled as fill_vs_anchor)
  * the sibling entry is cancelled the moment one side fills; if the broker
    reports BOTH parents filled anyway, flatten + cancel everything
  * after flat_et the clock force-flattens whatever is open

State survives restarts: every mutation is written to
state_dir()/day-YYYY-MM-DD.json and reloaded on boot.
"""
from __future__ import annotations

import datetime as dt
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from .broker.base import BrokerAdapter, FillEvent, OrderRequest
from .config import AppCfg, StrategyCfg
from .paths import state_dir

ET = ZoneInfo("America/New_York")

# The alert's (upper-lower) spread may differ from 2*offset by at most this
# many points — anything larger is a malformed or stale alert, refused.
SPREAD_TOL_PTS = 0.05


def _hhmm(s: str) -> dt.time:
    h, m = s.split(":")
    return dt.time(int(h), int(m))


@dataclass
class DayState:
    strategy: str
    date: str                          # ET date this state belongs to
    status: str = "idle"               # idle|placed|live|done|error
    upper_id: Optional[str] = None     # buy-stop parent order id
    lower_id: Optional[str] = None     # sell-stop parent order id
    upper_px: Optional[float] = None
    lower_px: Optional[float] = None
    entry_side: Optional[str] = None   # "Buy" | "Sell" once filled
    entry_anchor: Optional[float] = None   # intended trigger price
    entry_fill: Optional[float] = None     # actual fill price (first fill)
    exit_reason: Optional[str] = None  # tp|sl|no_fill|flat|both_filled|error
    exit_fill: Optional[float] = None
    note: str = ""


class Engine:
    """Wires alerts + broker fills + a clock into DayStates and orders.

    `now_fn` is injectable for tests; it must return an aware UTC datetime.
    """

    def __init__(self, cfg: AppCfg, adapter: BrokerAdapter, *,
                 now_fn: Callable[[], dt.datetime] | None = None,
                 root=None):
        self.cfg = cfg
        self.adapter = adapter
        self._now = now_fn or (lambda: dt.datetime.now(dt.timezone.utc))
        self._root = root or state_dir()
        self.states: dict[str, DayState] = {}
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
            self.states = {k: DayState(**v) for k, v in data.items()}

    def _save(self) -> None:
        p = self._day_path(self._today())
        p.write_text(json.dumps({k: asdict(v) for k, v in self.states.items()},
                                indent=2) + "\n")

    def journal(self, event: str, **data) -> None:
        rec = {"ts": time.time(), "et": self.now_et().isoformat(timespec="seconds"),
               "event": event, **data}
        with open(self._root / "journal.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")

    def _state(self, strategy: str) -> DayState:
        today = self._today()
        st = self.states.get(strategy)
        if st is None or st.date != today:      # day rollover => fresh state
            st = DayState(strategy=strategy, date=today)
            self.states[strategy] = st
        return st

    # --- the alert ----------------------------------------------------------
    async def handle_alert(self, payload: dict) -> dict:
        """Validated-payload entry point (the server has already checked the
        webhook secret). Returns a dict the HTTP layer can serialize."""
        name = str(payload.get("strategy") or "")
        cfg = self.cfg.strategies.get(name)
        if cfg is None or not cfg.enabled:
            self.journal("alert_refused", strategy=name, reason="unknown_or_disabled")
            return {"ok": False, "reason": f"unknown or disabled strategy: {name!r}"}

        st = self._state(name)
        if st.status != "idle":
            self.journal("alert_refused", strategy=name, reason="already_traded",
                         status=st.status)
            return {"ok": False, "reason": f"already acted today (status={st.status})"}

        now = self.now_et().time()
        if not (_hhmm(cfg.accept_from_et) <= now <= _hhmm(cfg.accept_until_et)):
            self.journal("alert_refused", strategy=name, reason="outside_window",
                         at=str(now))
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

        legs = self._legs(cfg, upper, lower)
        if not self.cfg.armed:
            self.journal("dry_run", strategy=name, would_place=[asdict(r) for r in legs])
            return {"ok": True, "armed": False,
                    "note": "disarmed — journaled only", "would_place": len(legs)}

        return await self._place(name, cfg, st, upper, lower, legs)

    @staticmethod
    def _legs(cfg: StrategyCfg, upper: float, lower: float) -> list[OrderRequest]:
        """The two OSO stop-entry legs. `price` is the Stop trigger; SL/TP are
        absolute bracket prices anchored at the trigger."""
        return [
            OrderRequest(symbol=cfg.symbol, side="Buy", qty=cfg.qty,
                         order_type="Stop", price=upper,
                         stop_price=upper - cfg.sl_pts, tp_price=upper + cfg.tp_pts,
                         text="homebase:entry"),
            OrderRequest(symbol=cfg.symbol, side="Sell", qty=cfg.qty,
                         order_type="Stop", price=lower,
                         stop_price=lower + cfg.sl_pts, tp_price=lower - cfg.tp_pts,
                         text="homebase:entry"),
        ]

    async def _place(self, name: str, cfg: StrategyCfg, st: DayState,
                     upper: float, lower: float,
                     legs: list[OrderRequest]) -> dict:
        buy, sell = legs
        r_up = await self.adapter.place_bracket(buy)
        if not r_up.ok:
            st.status, st.exit_reason, st.note = "error", "error", f"upper leg: {r_up.error}"
            self._save()
            self.journal("place_failed", strategy=name, leg="upper", error=r_up.error)
            return {"ok": False, "reason": f"upper leg rejected: {r_up.error}"}
        r_dn = await self.adapter.place_bracket(sell)
        if not r_dn.ok:
            # both-or-nothing: kill the lone survivor before reporting failure
            await self.adapter.cancel_order_by_id(r_up.order_id)
            st.status, st.exit_reason, st.note = "error", "error", f"lower leg: {r_dn.error}"
            self._save()
            self.journal("place_failed", strategy=name, leg="lower",
                         error=r_dn.error, cancelled_upper=r_up.order_id)
            return {"ok": False, "reason": f"lower leg rejected: {r_dn.error}"}

        st.status = "placed"
        st.upper_id, st.lower_id = r_up.order_id, r_dn.order_id
        st.upper_px, st.lower_px = upper, lower
        self._save()
        self.journal("placed", strategy=name, upper=upper, lower=lower,
                     qty=cfg.qty, upper_id=st.upper_id, lower_id=st.lower_id)
        return {"ok": True, "armed": True, "upper_id": st.upper_id,
                "lower_id": st.lower_id}

    # --- broker fills ---------------------------------------------------------
    async def on_fill(self, ev: FillEvent) -> None:
        oid = str((ev.raw or {}).get("orderId") or "")
        for st in self.states.values():
            cfg = self.cfg.strategies.get(st.strategy)
            if cfg is None:
                continue
            if st.status == "placed" and oid in (st.upper_id, st.lower_id):
                sibling = st.lower_id if oid == st.upper_id else st.upper_id
                st.status = "live"
                st.entry_side = "Buy" if oid == st.upper_id else "Sell"
                st.entry_anchor = st.upper_px if oid == st.upper_id else st.lower_px
                st.entry_fill = ev.price
                self._save()
                r = await self.adapter.cancel_order_by_id(sibling)
                self.journal("entry_fill", strategy=st.strategy, side=st.entry_side,
                             fill=ev.price, anchor=st.entry_anchor,
                             fill_vs_anchor=(None if ev.price is None or st.entry_anchor is None
                                             else round(ev.price - st.entry_anchor, 4)),
                             sibling_cancelled=r.ok, sibling_error=r.error)
                return
            if st.status == "live" and oid and oid in (st.upper_id, st.lower_id) \
                    and oid != self._entry_id(st):
                # The sibling filled before our cancel landed: flatten everything.
                st.status, st.exit_reason = "error", "both_filled"
                self._save()
                await self.adapter.cancel_all()
                await self.adapter.flatten_all()
                self.journal("both_filled_emergency", strategy=st.strategy, order_id=oid)
                return
            if st.status == "live" and ev.symbol and cfg.symbol.upper() in ev.symbol.upper() \
                    and ev.side != st.entry_side:
                # Opposite-side fill that isn't the sibling parent: the bracket
                # exit (TP or SL) or the 15:55 flatten.
                st.status = "done"
                st.exit_fill = ev.price
                st.exit_reason = self._grade_exit(st, ev.price)
                self._save()
                self.journal("exit_fill", strategy=st.strategy, reason=st.exit_reason,
                             fill=ev.price)
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

    # --- the clock ------------------------------------------------------------
    async def clock_tick(self) -> None:
        """Called every few seconds. Enforces cancel_et and flat_et."""
        now = self.now_et().time()
        for st in list(self.states.values()):
            cfg = self.cfg.strategies.get(st.strategy)
            if cfg is None or st.date != self._today():
                continue
            if st.status == "placed" and now >= _hhmm(cfg.cancel_et):
                for oid in (st.upper_id, st.lower_id):
                    if oid:
                        await self.adapter.cancel_order_by_id(oid)
                # A fill can race the cancel: only close the day if we're flat.
                net = await self.adapter.get_net_position(cfg.symbol)
                if net == 0:
                    st.status, st.exit_reason = "done", "no_fill"
                    self.journal("cancelled_unfilled", strategy=st.strategy)
                else:
                    st.status = "live"
                    st.note = "fill raced the 12:55 cancel"
                    self.journal("cancel_raced_fill", strategy=st.strategy, net=net)
                self._save()
            elif st.status == "live" and now >= _hhmm(cfg.flat_et):
                await self.adapter.cancel_all()
                await self.adapter.flatten_all()
                st.status, st.exit_reason = "done", st.exit_reason or "flat"
                self._save()
                self.journal("clock_flat", strategy=st.strategy)
