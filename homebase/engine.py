"""One signal in, bracketed straddles out across the BOOK, clock-guarded flat.

A validated signal fans out to every account assigned to the strategy in
cfg.book, at that assignment's qty. Each (strategy, account) pair gets its
own day state; the one-trade-per-day rule is per strategy across the whole
book (a second signal is refused even if only some accounts placed).

Per (strategy, account), all times ET:

    idle --signal(armed)--> placing --acks--> placed --entry fill--> live
         --SL/TP/flat--> done       (live: SL/TP re-priced to the actual fill)
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

import asyncio
import datetime as dt
import json
import time
from dataclasses import asdict, dataclass
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from .broker.base import BrokerAdapter, FillEvent, OrderRequest, OrderResult
from .config import AppCfg, StrategyCfg, assignments
from .contracts import point_value, tick_size
from .paths import state_dir

ET = ZoneInfo("America/New_York")
SPREAD_TOL_PTS = 0.05
WORKING = {"Working", "PendingNew", "Pending", "Suspended", "PendingReplace"}
SIBLING_RETRY_S = 2.0


def _hhmm(s: str) -> dt.time:
    h, m = s.split(":")
    return dt.time(int(h), int(m))


def _to_tick(px: float, tick: float) -> float:
    return round(round(px / tick) * tick, 6)


def _bracket_ids(r: OrderResult) -> tuple[Optional[str], Optional[str]]:
    raw = r.raw or {}
    return tuple(str(raw[k]) if raw.get(k) is not None else None   # type: ignore
                 for k in ("sl_order_id", "tp_order_id"))


@dataclass
class DayState:
    strategy: str
    account: str
    date: str
    qty: int = 0
    status: str = "idle"               # idle|placing|placed|live|done|error
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
    entry_qty: int = 0                 # entry contracts filled so far
    sl_px: Optional[float] = None      # bars strategies: absolute stop / target
    tp_px: Optional[float] = None
    tp_rr: Optional[float] = None      # bars: TP re-derived from the fill at this RR
    up_sl_id: Optional[str] = None     # each leg's OSO stop / target order,
    up_tp_id: Optional[str] = None     # re-priced to the actual fill
    dn_sl_id: Optional[str] = None
    dn_tp_id: Optional[str] = None
    brackets_moved: bool = False


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
        self._early: list[FillEvent] = []   # fills that beat the placement acks
        self._retry_at: dict[str, float] = {}   # last sibling-cancel attempt
        # (date, strategy) -> accounts the 9:30 bot skips today: they held a
        # manual position or working order in its symbol at the prestage
        # (timer.STAGE_T)
        self._skips: dict[tuple[str, str], set[str]] = {}
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
        self._load_skips_from_journal()

    def _load_skips_from_journal(self) -> None:
        """Restart safety: a desk restart after the 09:28:30 prestage must
        not forget today's skips, or a retry/alert could place onto an
        account that already holds the bot's symbol. `_skips` is otherwise
        only in memory, so rebuild it from today's `timer_skipped` journal
        lines (the only durable record); a missing/unreadable journal just
        means no skips are known yet."""
        p = self._root / "journal.jsonl"
        if not p.exists():
            return
        today = self._today()
        try:
            lines = p.read_text().splitlines()
        except OSError:
            return
        for line in lines:
            try:
                rec = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if rec.get("event") != "timer_skipped":
                continue
            if not str(rec.get("et", "")).startswith(today):
                continue
            strategy, account = rec.get("strategy"), rec.get("account")
            if strategy and account:            # gate_chop skips carry no account
                self._skips.setdefault((today, strategy), set()).add(account)

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
        for s in ("error", "live", "placing", "placed", "done"):
            if s in stats:
                return s
        return "idle"

    def skip_today(self, strategy: str, account: str) -> None:
        self._skips.setdefault((self._today(), strategy), set()).add(account)

    def skipped_today(self, strategy: str) -> set[str]:
        return set(self._skips.get((self._today(), strategy), ()))

    # --- the signal ----------------------------------------------------------
    async def handle_alert(self, payload: dict, *, force_window: bool = False,
                           source: str = "tv") -> dict:
        name = str(payload.get("strategy") or "")
        cfg = self.cfg.strategies.get(name)
        if cfg is None or not cfg.enabled:
            self.journal("alert_refused", strategy=name, reason="unknown_or_disabled")
            return {"ok": False, "reason": f"unknown or disabled strategy: {name!r}"}
        if getattr(cfg, "kind", "straddle") != "straddle":
            self.journal("alert_refused", strategy=name, reason="not_a_straddle")
            return {"ok": False, "reason": f"{name} runs off the price feed, not alerts"}

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
        skipped = self.skipped_today(name)
        if skipped:                              # the prestage skip (timer._prestage_skip)
            asg = [a for a in asg if a["account"] not in skipped]
            if not asg:
                self.journal("alert_refused", strategy=name, reason="all_accounts_skipped",
                             skipped=sorted(skipped), source=source)
                return {"ok": False,
                        "reason": "every booked account holds a manual position or order"
                                  " — skipped today"}
        if not asg:
            self.journal("alert_refused", strategy=name, reason="no_assignments",
                         source=source)
            return {"ok": False,
                    "reason": "no accounts assigned to this strategy in the book"}

        if not self.cfg.armed or getattr(cfg, "shadow", False):
            ev = "shadow_signal" if (self.cfg.armed and cfg.shadow) else "dry_run"
            for a in asg:
                self.journal(ev, strategy=name, source=source,
                             account=a["account"], qty=int(a["qty"]),
                             upper=upper, lower=lower,
                             would_place=[asdict(r) for r in
                                          self._legs(cfg, upper, lower, int(a["qty"]))])
            return {"ok": True, "armed": False,
                    "note": ("shadow — journaled only" if ev == "shadow_signal"
                             else "disarmed — journaled only"), "accounts": len(asg)}

        t0 = time.time()
        # every account at once — none waits behind another's round trip
        outs = await asyncio.gather(
            *(self._place(name, cfg, a["account"], int(a["qty"]), upper, lower,
                          source, t0) for a in asg),
            return_exceptions=True)
        results = {a["account"]: (o if isinstance(o, dict) else
                                  {"ok": False, "reason": str(o)})
                   for a, o in zip(asg, outs)}
        ok = any(r.get("ok") for r in results.values())
        return {"ok": ok, "armed": True, "accounts": results}

    async def handle_signal(self, name: str, sig, *, source: str = "feed") -> dict:
        """A price-action rule's Signal -> ONE bracketed leg per assigned
        account (entry Market or Stop, absolute SL/TP). Same guards as an
        alert: enabled, one per day, the accept window, the book. Shadow or
        disarmed -> journaled only."""
        cfg = self.cfg.strategies.get(name)
        if cfg is None or not cfg.enabled:
            self.journal("signal_refused", strategy=name, reason="unknown_or_disabled")
            return {"ok": False, "reason": f"unknown or disabled strategy: {name!r}"}
        if self.day_status(name) != "idle":
            self.journal("signal_refused", strategy=name, reason="already_traded",
                         status=self.day_status(name), source=source)
            return {"ok": False, "reason": f"already acted today ({self.day_status(name)})"}
        now = self.now_et().time()
        if not (_hhmm(cfg.accept_from_et) <= now <= _hhmm(cfg.accept_until_et)):
            self.journal("signal_refused", strategy=name, reason="outside_window",
                         at=str(now), source=source)
            return {"ok": False, "reason": f"outside accept window at {now}"}
        if sig.side not in ("Buy", "Sell") or not sig.sl_px or not sig.tp_px:
            self.journal("signal_refused", strategy=name, reason="bad_signal",
                         signal=asdict(sig))
            return {"ok": False, "reason": "signal needs a side, a stop and a target"}
        sign = 1 if sig.side == "Buy" else -1
        ref = sig.ref_px if sig.ref_px is not None else sig.entry_price
        if ref is not None and not (sign * (ref - sig.sl_px) > 0 and sign * (sig.tp_px - ref) > 0):
            self.journal("signal_refused", strategy=name, reason="levels_wrong_side",
                         signal=asdict(sig))
            return {"ok": False, "reason": "stop/target on the wrong side of the entry"}
        asg = assignments(self.cfg, name)
        if not asg:
            self.journal("signal_refused", strategy=name, reason="no_assignments",
                         source=source)
            return {"ok": False, "reason": "no accounts assigned to this strategy in the book"}
        pv = point_value(cfg.symbol) or 0.0
        if not self.cfg.armed or cfg.shadow:
            ev = "shadow_signal" if (self.cfg.armed and cfg.shadow) else "dry_run"
            for a in asg:
                self.journal(ev, strategy=name, source=source, account=a["account"],
                             qty=int(a["qty"]), side=sig.side, entry=sig.entry,
                             entry_price=sig.entry_price, ref_px=ref,
                             sl=sig.sl_px, tp=sig.tp_px,
                             risk_usd=(round(abs(ref - sig.sl_px) * pv * int(a["qty"]), 2)
                                       if ref is not None else None),
                             **{f"rule_{k}": v for k, v in (sig.note or {}).items()})
            return {"ok": True, "armed": False,
                    "note": ("shadow — journaled only" if ev == "shadow_signal"
                             else "disarmed — journaled only"), "accounts": len(asg)}
        t0 = time.time()
        outs = await asyncio.gather(
            *(self._place_one(name, cfg, a["account"], int(a["qty"]), sig, source, t0)
              for a in asg), return_exceptions=True)
        results = {a["account"]: (o if isinstance(o, dict) else {"ok": False, "reason": str(o)})
                   for a, o in zip(asg, outs)}
        return {"ok": any(r.get("ok") for r in results.values()), "armed": True,
                "accounts": results}

    async def _place_one(self, name: str, cfg: StrategyCfg, account: str, qty: int,
                         sig, source: str, t0: float) -> dict:
        st = self._state(name, account)
        ad = self.adapters.get(account)
        if ad is None or not ad.connected:
            st.status, st.exit_reason, st.note = "error", "error", "account not connected"
            self._save()
            self.journal("place_failed", strategy=name, account=account,
                         error="account not connected")
            return {"ok": False, "reason": "account not connected"}
        st.qty, st.status = qty, "placing"
        req = OrderRequest(symbol=cfg.symbol, side=sig.side, qty=qty,
                           order_type=sig.entry, price=sig.entry_price,
                           stop_price=sig.sl_px, tp_price=sig.tp_px, text="homebase:entry")
        try:
            r = await ad.place_bracket(req)
        except Exception as e:  # noqa: BLE001 — a raise is a reject
            r = OrderResult(ok=False, error=str(e))
        if not r.ok:
            st.status, st.exit_reason, st.note = "error", "error", f"entry: {r.error}"
            self._save()
            self.journal("place_failed", strategy=name, account=account, error=r.error)
            await self._replay_early(account)
            return {"ok": False, "reason": f"entry rejected: {r.error}"}
        ref = sig.ref_px if sig.ref_px is not None else sig.entry_price
        if sig.side == "Buy":
            st.upper_id, st.upper_px = r.order_id, ref
            st.up_sl_id, st.up_tp_id = _bracket_ids(r)
        else:
            st.lower_id, st.lower_px = r.order_id, ref
            st.dn_sl_id, st.dn_tp_id = _bracket_ids(r)
        st.sl_px, st.tp_px, st.tp_rr = sig.sl_px, sig.tp_px, sig.tp_rr
        st.status = "placed"
        self._save()
        self.journal("placed", strategy=name, account=account, source=source, kind="bars",
                     side=sig.side, entry=sig.entry, entry_price=sig.entry_price,
                     ref_px=ref, sl=sig.sl_px, tp=sig.tp_px, qty=qty, order_id=r.order_id,
                     place_ms=round((time.time() - t0) * 1000))
        await self._replay_early(account)
        return {"ok": True, "order_id": r.order_id}

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
        # from here a second signal is refused, and an entry fill that beats
        # the acks is held instead of dropped (on_fill -> _replay_early)
        st.status = "placing"
        buy, sell = self._legs(cfg, upper, lower, qty)
        # Both legs go out together — the second no longer waits a full round
        # trip for the first. A leg that raises counts as rejected.
        r_up, r_dn = [r if isinstance(r, OrderResult) else OrderResult(ok=False, error=str(r))
                      for r in await asyncio.gather(ad.place_bracket(buy),
                                                    ad.place_bracket(sell),
                                                    return_exceptions=True)]
        if not (r_up.ok and r_dn.ok):
            # never leave half a straddle: cancel whichever leg did go in
            leg, err = ("upper", r_up.error) if not r_up.ok else ("lower", r_dn.error)
            survivor = r_dn if not r_up.ok else r_up
            if survivor.ok:
                await ad.cancel_order_by_id(survivor.order_id)
            st.status, st.exit_reason, st.note = "error", "error", f"{leg} leg: {err}"
            self._save()
            self.journal("place_failed", strategy=name, account=account, leg=leg,
                         error=err, cancelled=survivor.order_id if survivor.ok else None)
            await self._replay_early(account)
            return {"ok": False, "reason": f"{leg} leg rejected: {err}"}

        st.status = "placed"
        st.upper_id, st.lower_id = r_up.order_id, r_dn.order_id
        st.up_sl_id, st.up_tp_id = _bracket_ids(r_up)
        st.dn_sl_id, st.dn_tp_id = _bracket_ids(r_dn)
        st.upper_px, st.lower_px = upper, lower
        self._save()
        self.journal("placed", strategy=name, account=account, source=source,
                     upper=upper, lower=lower, qty=qty,
                     upper_id=st.upper_id, lower_id=st.lower_id,
                     # anchor -> both legs acknowledged by the broker; the
                     # only latency the strategy is actually exposed to
                     place_ms=(None if t0 is None
                               else round((time.time() - t0) * 1000)))
        await self._replay_early(account)
        return {"ok": True, "upper_id": st.upper_id, "lower_id": st.lower_id}

    async def _replay_early(self, account: str) -> None:
        """Entry fills that arrived before this account's acks: run them now."""
        mine = [e for e in self._early if e.account_id == account]
        self._early = [e for e in self._early if e.account_id != account]
        for ev in mine:
            await self.on_fill(ev)

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
                st.entry_fill, st.entry_qty = ev.price, ev.qty
                self._save()
                jobs = [ad.cancel_order_by_id(sibling) if sibling
                        else asyncio.sleep(0, result=OrderResult(ok=True))]
                if st.entry_qty >= st.qty:          # whole entry in: SL/TP to the fill
                    jobs.append(self._move_brackets(st, cfg, ad))
                r, *moved = await asyncio.gather(*jobs, return_exceptions=True)
                if isinstance(r, Exception):
                    r = OrderResult(ok=False, error=str(r))
                if r.ok and sibling:   # let the broker confirm before the backstop re-checks
                    self._retry_at[f"sib:{st.strategy}@{st.account}"] = time.time()
                self.journal("entry_fill", strategy=st.strategy, account=st.account,
                             side=st.entry_side, fill=ev.price, anchor=st.entry_anchor,
                             fill_vs_anchor=(None if ev.price is None or st.entry_anchor is None
                                             else round(ev.price - st.entry_anchor, 4)),
                             qty_filled=st.entry_qty,
                             sibling_cancelled=r.ok, sibling_error=r.error)
                if moved:
                    self._journal_moved(st, moved[0])
                return
            if st.status == "live" and oid and oid == self._entry_id(st) \
                    and st.entry_qty < st.qty:
                # the rest of a split entry, or the push after the order-status
                # check adopted it: keep the AVERAGE fill, as the research does,
                # and re-price SL/TP once the whole entry is in
                n = st.entry_qty + ev.qty
                if ev.price is not None:
                    st.entry_fill = (ev.price if st.entry_fill is None else
                                     (st.entry_fill * st.entry_qty + ev.price * ev.qty) / n)
                st.entry_qty = n
                self._save()
                self.journal("entry_fill", strategy=st.strategy, account=st.account,
                             side=st.entry_side, fill=st.entry_fill, anchor=st.entry_anchor,
                             fill_vs_anchor=(None if st.entry_fill is None or st.entry_anchor is None
                                             else round(st.entry_fill - st.entry_anchor, 4)),
                             qty_filled=n)
                if n >= st.qty and not st.brackets_moved:
                    try:
                        moved = await self._move_brackets(st, cfg, ad)
                    except Exception as e:  # noqa: BLE001 — the fill is already in
                        moved = e
                    self._journal_moved(st, moved)
                return
            if st.status == "live" and oid and oid in (st.upper_id, st.lower_id) \
                    and oid != self._entry_id(st):
                st.status, st.exit_reason = "error", "both_filled"
                self._save()
                _, acts = await self._flatten_state(st, cfg, ad)
                self.journal("both_filled_emergency", strategy=st.strategy,
                             account=st.account, order_id=oid, actions=acts)
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
        # Nothing matched. An entry fill can beat the placement acks — the
        # order is live at the broker before we know its id — so while this
        # account is placing, hold it; _place replays it once the ids are in.
        if any(s.status == "placing" and s.account == ev.account_id
               for s in self.states.values()):
            self._early.append(ev)

    async def _move_brackets(self, st: DayState, cfg: StrategyCfg,
                             ad: BrokerAdapter) -> dict:
        """The research measures SL/TP from the ACTUAL (average) fill, not the
        trigger. Once the whole entry is in, move both brackets there. A fill
        at the trigger moves nothing; a failed move leaves the trigger
        brackets working — still protected, just not re-priced."""
        st.brackets_moved = True                  # once per trade
        if st.entry_fill is None:
            return {"moved": False, "error": "no fill price"}
        sign = 1 if st.entry_side == "Buy" else -1
        tick = tick_size(cfg.symbol) or 0.25
        sl_id, tp_id = ((st.up_sl_id, st.up_tp_id) if st.entry_side == "Buy"
                        else (st.dn_sl_id, st.dn_tp_id))
        if st.sl_px is not None:
            # a rule's absolute stop stays; the target follows the fill at the
            # rule's RR (a rule without tp_rr keeps its absolute target too)
            if st.tp_rr is None:
                return {"fill": round(st.entry_fill, 6), "sl": st.sl_px, "tp": st.tp_px,
                        "moved": "not needed — absolute levels"}
            tp = _to_tick(st.entry_fill + sign * st.tp_rr * abs(st.entry_fill - st.sl_px), tick)
            out = {"fill": round(st.entry_fill, 6), "sl": st.sl_px, "tp": tp}
            if abs(tp - (st.tp_px or 0)) < tick / 2:
                return {**out, "moved": "not needed — target unchanged"}
            if not tp_id:
                return {**out, "moved": False, "error": "target order id unknown"}
            st.tp_px = tp
            self._save()
            r = await ad.modify_order(tp_id, "Limit", price=tp, qty=st.qty)
            return {**out, "moved": r.ok, **({"error": r.error} if not r.ok else {})}
        sl = _to_tick(st.entry_fill - sign * cfg.sl_pts, tick)
        tp = _to_tick(st.entry_fill + sign * cfg.tp_pts, tick)
        out = {"fill": round(st.entry_fill, 6), "sl": sl, "tp": tp}
        if st.entry_anchor is not None and abs(st.entry_fill - st.entry_anchor) < tick / 2:
            return {**out, "moved": "not needed — filled at the trigger"}
        if not (sl_id and tp_id):
            return {**out, "moved": False, "error": "bracket order ids unknown"}
        res = await asyncio.gather(
            ad.modify_order(sl_id, "Stop", stop_price=sl, qty=st.qty),
            ad.modify_order(tp_id, "Limit", price=tp, qty=st.qty),
            return_exceptions=True)
        errs = [f"{k}: {r if isinstance(r, Exception) else r.error}"
                for k, r in zip(("sl", "tp"), res)
                if isinstance(r, Exception) or not r.ok]
        return {**out, "moved": not errs, **({"error": "; ".join(errs)} if errs else {})}

    def _journal_moved(self, st: DayState, moved) -> None:
        if isinstance(moved, Exception):
            moved = {"moved": False, "error": str(moved)}
        self.journal("brackets_moved", strategy=st.strategy, account=st.account, **moved)

    def _entry_id(self, st: DayState) -> Optional[str]:
        return st.upper_id if st.entry_side == "Buy" else st.lower_id

    def _grade_exit(self, st: DayState, px: Optional[float]) -> str:
        cfg = self.cfg.strategies[st.strategy]
        if px is None:
            return "exit"
        if st.sl_px is not None and st.tp_px is not None:
            return "tp" if abs(px - st.tp_px) <= abs(px - st.sl_px) else "sl"
        if st.entry_anchor is None:
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
        """Manual flatten for ONE strategy on every account it acted on today
        (see _flatten_state). Symbol-scoped per account: another strategy
        holding the same symbol on the same account would be flattened too."""
        cfg = self.cfg.strategies.get(name)
        results: dict = {}
        for st in self.day_states(name):
            ad = self.adapters.get(st.account)
            if ad is None or cfg is None or st.status == "idle":
                continue
            flat, results[st.account] = await self._flatten_state(st, cfg, ad)
            if flat and st.status in ("placing", "placed", "live"):
                st.status, st.exit_reason = "done", "manual_flat"
        self._save()
        self.journal("manual_flatten", strategy=name, results=results)
        return results

    async def flatten_today(self) -> dict:
        """Kill switch: every strategy's footprint today, proven calls only."""
        out: dict = {}
        for st in list(self.states.values()):
            cfg = self.cfg.strategies.get(st.strategy)
            ad = self.adapters.get(st.account)
            if cfg is None or ad is None or st.date != self._today() \
                    or st.status == "idle":
                continue
            flat, out[f"{st.strategy}@{st.account}"] = await self._flatten_state(st, cfg, ad)
            if flat and st.status in ("placing", "placed", "live"):
                st.status, st.exit_reason = "done", "killed"
        self._save()
        return out

    async def _flatten_state(self, st: DayState, cfg: StrategyCfg,
                             ad: BrokerAdapter) -> tuple[bool, list[str]]:
        """Close ONE strategy's footprint on one account using only calls
        proven live (position read, market order, single cancels). Market out
        of the net position FIRST — the stop/target keep protecting until the
        position is gone — then cancel every order this strategy placed: both
        entries and both legs' stop/target (GTC: a leftover could open a new
        position days later). Position unreadable or the market order refused
        -> NOTHING is cancelled; the stop/target stay working."""
        try:
            net = await ad.get_net_position(cfg.symbol)
        except Exception as e:  # noqa: BLE001 — unreadable is NOT flat
            return False, [f"position unreadable ({e}) — stop/target left working"]
        acts: list[str] = []
        if net:
            side = "Sell" if net > 0 else "Buy"
            r = await ad.place_order(OrderRequest(
                symbol=cfg.symbol, side=side, qty=abs(net), order_type="Market",
                text="homebase:flat"))
            acts.append(f"market {side} {abs(net)}: {'ok' if r.ok else r.error}")
            if not r.ok:
                acts.append("not flat — stop/target left working")
                return False, acts
        ids = [i for i in (st.upper_id, st.lower_id, st.up_sl_id, st.up_tp_id,
                           st.dn_sl_id, st.dn_tp_id) if i]
        res = await asyncio.gather(*(ad.cancel_order_by_id(i) for i in ids),
                                   return_exceptions=True)
        for i, r in zip(ids, res):
            ok = not isinstance(r, Exception) and r.ok
            acts.append(f"cancel {i}: " + ("ok" if ok else
                        str(r if isinstance(r, Exception) else r.error)))
        return True, acts

    async def _guard_sibling(self, st: DayState, cfg: StrategyCfg,
                             ad: BrokerAdapter) -> None:
        """After the entry the OTHER stop must be gone. Still working -> the
        cancel was refused or raced: cancel again (every 2 s at most). Filled
        -> it opened a second, unmanaged position (even after the trade
        ended): close it and every bracket."""
        sib = st.lower_id if st.entry_side == "Buy" else st.upper_id
        if not sib:
            return
        status = await ad.get_order_status(sib)
        if status == "Filled":
            st.status, st.exit_reason = "error", "both_filled"
            self._save()
            _, acts = await self._flatten_state(st, cfg, ad)
            self.journal("both_filled_emergency", strategy=st.strategy,
                         account=st.account, order_id=sib,
                         found_by="sibling_check", actions=acts)
            return
        if status in WORKING:
            key = f"sib:{st.strategy}@{st.account}"
            if time.time() - self._retry_at.get(key, 0.0) < SIBLING_RETRY_S:
                return
            self._retry_at[key] = time.time()
            r = await ad.cancel_order_by_id(sib)
            self.journal("sibling_cancel_retry", strategy=st.strategy,
                         account=st.account, order_id=sib, ok=r.ok, error=r.error)

    async def _guard_placed(self, st: DayState, cfg: StrategyCfg,
                            ad: BrokerAdapter, *, check_position: bool,
                            event: str, note: str) -> Optional[str]:
        """Backstop for the sibling cancel. on_fill is the fast path, but it
        only fires if the fill PUSH arrives and parses — on 2026-09-21 it
        arrived, was dropped, and the sell stop kept resting after the buy
        stop filled. Ask the broker instead: an entry ORDER that reads Filled
        means that side is in, even if the trade already went flat again
        (which a position check alone would miss). check_position adds the
        net-position read. Returns "entry_recovered", "both_filled" or None."""
        up = await ad.get_order_status(st.upper_id) if st.upper_id else None
        dn = await ad.get_order_status(st.lower_id) if st.lower_id else None
        side, net = None, None
        if up == "Filled" and dn == "Filled":
            if st.status != "placed":
                return None
            st.status, st.exit_reason = "error", "both_filled"
            self._save()
            _, acts = await self._flatten_state(st, cfg, ad)
            self.journal("both_filled_emergency", strategy=st.strategy,
                         account=st.account, found_by=event, actions=acts)
            return "both_filled"
        if "Filled" in (up, dn):
            side = "Buy" if up == "Filled" else "Sell"
        elif check_position:
            net = await ad.get_net_position(cfg.symbol)
            if net:
                side = "Buy" if net > 0 else "Sell"
        if side is None or st.status != "placed":   # on_fill may have won meanwhile
            return None
        entry_id = st.upper_id if side == "Buy" else st.lower_id
        sibling = st.lower_id if side == "Buy" else st.upper_id
        st.status, st.entry_side = "live", side
        st.entry_anchor = st.upper_px if side == "Buy" else st.lower_px
        st.note = note
        self._save()
        r = await ad.cancel_order_by_id(sibling) if sibling else None
        self.journal(event, strategy=st.strategy, account=st.account, side=side,
                     net=net, entry_id=entry_id, sibling_cancelled=bool(r and r.ok),
                     sibling_error=(r.error if r else None))
        return "entry_recovered"

    async def reconcile_account(self, account: str) -> dict:
        """Run after every (re)connect. A fill that lands while the socket is
        down arrives in the reconnect's user sync, where it is marked seen and
        NEVER dispatched — so on_fill never hears of it and the opposite entry
        stop would keep resting. Ask the broker instead.

        placed + filled entry / position -> an entry filled while we were
                               away: adopt it and cancel the sibling
        live   + flat       -> the bracket closed it while we were away
        """
        ad = self.adapters.get(account)
        out: dict = {}
        if ad is None:
            return out
        for st in list(self.day_states_for_account(account)):
            cfg = self.cfg.strategies.get(st.strategy)
            if cfg is None or st.status not in ("placed", "live"):
                continue
            if st.status == "placed":
                got = await self._guard_placed(
                    st, cfg, ad, check_position=True,
                    event="fill_recovered_on_reconnect",
                    note="entry filled while disconnected — recovered on reconnect")
                if got:
                    out[st.strategy] = got
            elif not await ad.get_net_position(cfg.symbol):
                st.status = "done"
                st.exit_reason = st.exit_reason or "closed_while_disconnected"
                self._save()
                self.journal("exit_recovered_on_reconnect", strategy=st.strategy,
                             account=account)
                out[st.strategy] = "exit_recovered"
        return out

    def day_states_for_account(self, account: str) -> list[DayState]:
        today = self._today()
        return [s for s in self.states.values()
                if s.account == account and s.date == today]

    # --- the clock ------------------------------------------------------------
    async def clock_tick(self) -> None:
        now = self.now_et().time()
        for st in list(self.states.values()):
            cfg = self.cfg.strategies.get(st.strategy)
            ad = self.adapters.get(st.account)
            if cfg is None or ad is None or st.date != self._today():
                continue
            if st.status == "placed" and now < _hhmm(cfg.cancel_et):
                if ad.connected:   # a dead socket's cache is stale; reconnect reconciles
                    await self._guard_placed(
                        st, cfg, ad, check_position=False,
                        event="entry_found_by_check",
                        note="fill push missed — entry found by the order-status check")
            elif st.status == "placed" and now >= _hhmm(cfg.cancel_et):
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
                key = f"flat:{st.strategy}@{st.account}"
                if time.time() - self._retry_at.get(key, 0.0) < 5.0:
                    continue                          # a failed flat retries every 5 s
                self._retry_at[key] = time.time()
                flat, acts = await self._flatten_state(st, cfg, ad)
                if flat:
                    st.status, st.exit_reason = "done", st.exit_reason or "flat"
                    self._save()
                self.journal("clock_flat" if flat else "clock_flat_failed",
                             strategy=st.strategy, account=st.account, actions=acts)
            if st.status in ("live", "done") and st.entry_side and ad.connected:
                await self._guard_sibling(st, cfg, ad)
