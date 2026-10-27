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
  * a strategy killed today (kill_strategy, the chart's per-bot Kill) is
    never signalled again today: alerts/signals are refused, the timer skips
    it, and a placement already in flight is flattened once its acks land

Exits journal a gross P&L (points × point value × qty) so live metrics can
be aggregated straight from the journal. State survives restarts.
"""
from __future__ import annotations

import asyncio
import contextlib
import dataclasses
import datetime as dt
import json
import sys
import time
from dataclasses import asdict
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from ..broker.base import BrokerAdapter, FillEvent, OrderRequest, OrderResult
from ..config import AppCfg, StrategyCfg, assignments
from ..contracts import point_value, tick_size
from .levels import AccountLeg, Geometry, account_leg
from ..core import atomic
from ..paths import state_dir
from .dayrules import LOCK_LOCK, LOCK_TAKE, DayBook, DayRules, merge_rules, standing, take_level
from .daystate import (KILL_POLL_N, KILL_POLL_S, MARKET_OUT_FAILED, PLACING_UNKNOWN, TERMINAL, WORKING, DayState,
                       _hhmm, _to_tick)
# The Lab half of the engine. labdesk.py and the tests read the Lab words as engine.LAB_* / engine.LabLeg.
from .engine_groups import GroupMixin
from .engine_lab import (LAB, LAB_ACCOUNT_STOPPED, LAB_BAD_ORDER, LAB_CANNOT_CHECK, LAB_CLEAR_REJECTS,  # noqa: F401
                         LAB_CLOCK_POLLS, LAB_CLOSE_UNCONFIRMED, LAB_DISARMED, LAB_KILLED, LAB_NO_BLOCK,
                         LAB_NO_POSITION_READ, LAB_NO_STOP, LAB_NOT_A_PAIR, LAB_NOT_CONNECTED, LAB_NOT_ON_DESK,
                         LAB_NOT_WRITTEN, LAB_OFF, LAB_OLD_ORDER_WORKING, LAB_ONE_AT_A_TIME, LAB_PREFIX,
                         LAB_SLOT_BUSY, LAB_TAKE_RULE, LAB_TOO_LATE, LAB_WRONG_SIDE, LabLeg, LabMixin)
# The engine's other halves, each a mixin of Engine (methods moved from here unchanged).
from .engine_rotation import ROTATION_NONE, RotationMixin  # noqa: F401
from .engine_dayrules import TAKE_GRACE_S, TAKE_PRINT_NOTE, DayRulesMixin  # noqa: F401
from .engine_kill import EXIT_CONCURRENCY, KillMixin  # noqa: F401

ET = ZoneInfo("America/New_York")
SPREAD_TOL_PTS = 0.05
SIBLING_RETRY_S = 2.0
# Right after an entry fill the other entry is watched closely (sibling_tick): for SIBLING_WATCH_S its
# cancel is sent again every SIBLING_FAST_S while the broker still reads it as working.
SIBLING_FAST_S, SIBLING_WATCH_S = 0.5, 3.0


def _bracket_ids(r: OrderResult) -> tuple[Optional[str], Optional[str]]:
    raw = r.raw or {}
    return tuple(str(raw[k]) if raw.get(k) is not None else None   # type: ignore
                 for k in ("sl_order_id", "tp_order_id"))



class Engine(LabMixin, GroupMixin, RotationMixin, DayRulesMixin, KillMixin):
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
        self._sib_watch: dict[str, float] = {}  # "strategy@account" -> its entry fill, while sibling_tick watches
        # (date, strategy) -> accounts the 9:30 bot skips today: they held a
        # manual position or working order in its symbol at the prestage
        # (timer.STAGE_T)
        self._skips: dict[tuple[str, str], set[str]] = {}
        # date: today's day file / day book was unreadable (state lost): nothing new is placed today (killed_today)
        self._day_unreadable: Optional[str] = None
        # date -> strategies killed that day (the per-strategy Kill); rebuilt
        # from today's `strategy_killed` journal lines on a restart
        self._killed: dict[str, set[str]] = {}
        self._kill_locks: dict[str, tuple] = {}    # strategy -> (loop, asyncio.Lock)
        self._kill_sleep = asyncio.sleep           # the kill's poll wait (tests replace it)
        self._perf = time.perf_counter             # the legs' round-trip clock (tests replace it)
        self._needs_check_said: set = set()        # (date, strategy, account, at) journaled
        self._check_it_cancelled: set = set()      # (date, strategy, account): 12:55 entry cancels sent
        self._inactive: dict[str, dict[str, str]] = {}   # strategy -> {code: why}, today (inactive.py)
        self._inactive_date: Optional[str] = None
        self._signalled: set = set()               # (date, strategy): a bar rule produced a signal
        self.books: dict[str, DayBook] = {}        # account -> today's closed P&L / lock / eval standing
        self._take_seen: dict[str, float] = {}     # account -> when a day_take touch was first seen
        self._mono = time.monotonic                # the take backstop's clock (tests replace it)
        # account -> {date: closing balance}: the desk's daily balance record (server.equity_by_day);
        # target_take's largest day / day count come from it
        self.balance_history: Optional[Callable[[str], dict]] = None
        # strategy -> {"on": take turns, "last": the account that took its last trade}; kept across days
        self.rotation: dict[str, dict] = {}
        self._load_today()
        self._load_rotation()
        # account cycle groups: {group id: {name, members, accounts, risk_usd, max_minis, on, last}}; kept across days
        self.groups: dict[str, dict] = {}
        self._load_groups()

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
            self.states = {}
            try:
                data = json.loads(p.read_text())
                if not isinstance(data, dict):
                    raise ValueError("not an object")
            except Exception as e:  # noqa: BLE001 — a bad day file must never stop the desk starting
                # keep the bad file for a human, start the day with no states (stderr: the journal may be what failed)
                print(f"homebase engine: reading {p.name} failed: {e!r}", file=sys.stderr)
                with contextlib.suppress(OSError):
                    p.replace(p.with_name(p.name + ".corrupt"))
                self._day_unreadable_now(p.name, e)
                data = {}
            for k, v in data.items():        # one bad record never drops the others
                try:
                    if "account" in v:       # drop pre-book records
                        self.states[k] = DayState(**v)
                except Exception as e:  # noqa: BLE001
                    self._day_unreadable_now(f"day record {k!r}", e)
            # "placing" saved by a desk that died with the acks outstanding: nothing will
            # ever settle it here (it would pause the chart views, park fills and keep a
            # Kill "pending" all day). Not idle, so never fired again: an error to check.
            unknown = [st for st in self.states.values()
                       if st.status == "placing" and st.date == self._today()]
            for st in unknown:
                st.status, st.exit_reason = "error", "error"
                st.note = PLACING_UNKNOWN
                self.journal("place_failed", strategy=st.strategy, account=st.account,
                             error=PLACING_UNKNOWN, after_restart=True)
            if unknown:
                self._save()
        self._load_skips_from_journal()
        self._load_books()

    def _load_skips_from_journal(self) -> None:
        """Restart safety: a desk restart after the 09:28:30 prestage must
        not forget today's skips, or a retry/alert could place onto an
        account that already holds the bot's symbol. `_skips` is otherwise
        only in memory, so rebuild it from today's `timer_skipped` journal
        lines (the only durable record); a missing/unreadable journal just
        means no skips are known yet.

        A malformed journal must never crash construction — the desk must
        still start. A per-line JSON error (including a line that parses to
        something other than an object: a bare number, null, a list) is
        skipped; a non-UTF-8 byte is replaced, never raised; and anything
        else unexpected here is logged and yields no skips for today,
        rather than raising into __init__."""
        try:
            p = self._root / "journal.jsonl"
            if not p.exists():
                return
            today = self._today()
            try:
                lines = p.read_text(errors="replace").splitlines()
            except (OSError, ValueError, UnicodeError):
                return
            for line in lines:
                try:
                    rec = json.loads(line)
                except (json.JSONDecodeError, ValueError):
                    continue
                if not isinstance(rec, dict):
                    continue
                if rec.get("event") in ("strategy_killed", "strategy_kill_requested") \
                        and str(rec.get("et", "")).startswith(today) and rec.get("strategy"):
                    self._killed.setdefault(today, set()).add(str(rec["strategy"]))
                    continue
                if rec.get("event") == "day_state_unreadable" and str(rec.get("et", "")).startswith(today):
                    self._day_unreadable = today
                    continue
                if rec.get("event") == "inactive_today" and str(rec.get("et", "")).startswith(today) \
                        and rec.get("strategy") and rec.get("code"):
                    self._inactive.setdefault(str(rec["strategy"]), {})[str(rec["code"])] = str(rec.get("reason", ""))
                    self._inactive_date = today
                    continue
                if rec.get("event") != "timer_skipped":
                    continue
                if not str(rec.get("et", "")).startswith(today):
                    continue
                strategy, account = rec.get("strategy"), rec.get("account")
                if strategy and account:        # gate_chop skips carry no account
                    self._skips.setdefault((today, strategy), set()).add(account)
        except Exception as e:  # noqa: BLE001 — the desk must still start
            print(f"homebase engine: _load_skips_from_journal failed: {e!r}",
                  file=sys.stderr)

    @property
    def journal_path(self):
        return self._root / "journal.jsonl"

    def _save(self) -> None:
        p = self._day_path(self._today())
        atomic.write_text(p, json.dumps({k: asdict(v) for k, v in self.states.items()},
                                        indent=2) + "\n")      # never half a file: a torn day file stops the desk

    def journal(self, event: str, **data) -> None:
        rec = {"ts": time.time(), "et": self.now_et().isoformat(timespec="seconds"),
               "event": event, **data}
        try:        # a full disk must never kill a watch loop that journals its own errors
            with open(self._root / "journal.jsonl", "a") as f:
                f.write(json.dumps(rec, default=str) + "\n")
        except OSError as e:
            print(f"homebase engine: journal {event} failed: {e!r}", file=sys.stderr)

    def note_inactive(self, strategy: str, code: str, why: str, **kw) -> bool:
        """A booked strategy will not trade today: say so ONCE per (day, strategy, code) -- the journal event
        `inactive_today` and the readiness line.  True when this call journaled it."""
        today = self._today()
        if self._inactive_date != today:
            self._inactive, self._inactive_date = {}, today
        codes = self._inactive.setdefault(strategy, {})
        if code in codes:
            return False
        codes[code] = why
        self.journal("inactive_today", strategy=strategy, code=code, reason=why, **kw)
        return True

    def inactive_today(self, strategy: str) -> dict:
        """{code: why} the strategy was said inactive today (empty: nothing said)."""
        return dict(self._inactive.get(strategy, {})) if self._inactive_date == self._today() else {}

    def signalled_today(self, strategy: str) -> bool:
        return (self._today(), strategy) in self._signalled

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
        stats = {s.status for s in self.day_states(strategy) if not self._archived(s)}
        for s in ("error", "live", "placing", "placed", "done"):
            if s in stats:
                return s
        return "idle"

    def skip_today(self, strategy: str, account: str) -> None:
        self._skips.setdefault((self._today(), strategy), set()).add(account)

    def skipped_today(self, strategy: str) -> set[str]:
        return set(self._skips.get((self._today(), strategy), ()))

    def kill_today(self, strategy: str) -> None:
        self._killed.setdefault(self._today(), set()).add(strategy)

    def killed_today(self, strategy: str) -> bool:
        # an unreadable day file means runs we no longer know about may be at the broker: no new placement today
        return strategy in self._killed.get(self._today(), ()) or self._day_unreadable == self._today()

    def _day_unreadable_now(self, what: str, err) -> None:
        """A day file / record / book was unreadable: say so loudly, journal it (a restart rebuilds the block from it)."""
        self._day_unreadable = self._today()
        print(f"homebase engine: {what} unreadable ({err!r}): nothing new is placed today", file=sys.stderr)
        self.journal("day_state_unreadable", what=what, error=repr(err)[:200])

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
        if self.killed_today(name):
            self.journal("alert_refused", strategy=name, reason="killed", source=source)
            return {"ok": False, "reason": f"{name} was killed today — nothing is placed"}
        if not cfg.trades_on(self.now_et().date()):      # an event-day strategy on another day
            self.journal("alert_refused", strategy=name, reason="not_a_trading_day", source=source)
            return {"ok": False, "reason": f"{name} does not trade today"}

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
        if self.rotating(name):                  # one account takes today's straddle: the one whose turn it is
            turn = self._one_turn(name, cfg, [a["account"] for a in asg])
            if turn is None:
                return {"ok": False, "reason": ROTATION_NONE}
            asg = [a for a in asg if a["account"] == turn]

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
        self._signalled.add((self._today(), name))
        cfg = self.cfg.strategies.get(name)
        if cfg is None or not cfg.enabled:
            self.journal("signal_refused", strategy=name, reason="unknown_or_disabled")
            return {"ok": False, "reason": f"unknown or disabled strategy: {name!r}"}
        if self.killed_today(name):
            self.journal("signal_refused", strategy=name, reason="killed", source=source)
            return {"ok": False, "reason": f"{name} was killed today — nothing is placed"}
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
        if self.rotating(name):
            turn = self._one_turn(name, cfg, [a["account"] for a in asg])
            if turn is None:
                return {"ok": False, "reason": ROTATION_NONE}
            asg = [a for a in asg if a["account"] == turn]
        t0 = time.time()
        outs = await asyncio.gather(
            *(self._place_one(name, cfg, a["account"], int(a["qty"]), sig, source, t0)
              for a in asg), return_exceptions=True)
        results = {a["account"]: (o if isinstance(o, dict) else {"ok": False, "reason": str(o)})
                   for a, o in zip(asg, outs)}
        return {"ok": any(r.get("ok") for r in results.values()), "armed": True,
                "accounts": results}

    async def handle_levels(self, name: str, geo: Geometry, *, source: str = "leveltimer",
                            info: dict | None = None) -> dict:
        """A "levels" strategy's day: one OCO pair of stop entries at geo.upper / geo.lower on every booked
        account, each with ITS OWN size and take (levels.account_leg: qty by profit tier, take = the lower
        of day_take and target_take net of the day's closed P&L), the stop geo.sl_pts from the trigger.
        Same guards as an alert: enabled, not killed, one per day, the accept window, the book -- plus the
        daily rules: an account stopped for the day (day_take / day_lock) sits out, one that needs a
        target_take level and has none sits out, and a REAL account sits out until the strategy's
        ack_open_loss says the 3 x ATR stop (several times a prop account's max loss) is accepted.
        Disarmed / shadow -> journaled only."""
        info = info or {}
        cfg = self.cfg.strategies.get(name)
        if cfg is None or not cfg.enabled or cfg.kind != "levels":
            self.journal("levels_refused", strategy=name, reason="unknown_or_disabled")
            return {"ok": False, "reason": f"unknown, disabled or not a levels strategy: {name!r}"}
        if self.killed_today(name):
            self.journal("levels_refused", strategy=name, reason="killed", source=source)
            return {"ok": False, "reason": f"{name} was killed today — nothing is placed"}
        if self.day_status(name) != "idle":
            self.journal("levels_refused", strategy=name, reason="already_traded",
                         status=self.day_status(name), source=source)
            return {"ok": False, "reason": f"already acted today ({self.day_status(name)})"}
        now = self.now_et().time()
        if not (_hhmm(cfg.accept_from_et) <= now <= _hhmm(cfg.accept_until_et)):
            self.journal("levels_refused", strategy=name, reason="outside_window",
                         at=str(now), source=source)
            self.note_inactive(name, "outside_window", f"fired at {now}, outside its accept window")
            return {"ok": False, "reason": f"outside accept window at {now}"}
        if not (geo.upper > geo.lower and geo.sl_pts > 0):
            self.journal("levels_refused", strategy=name, reason="bad_geometry", geometry=geo.to_dict())
            self.note_inactive(name, "bad_geometry", "the day's geometry was unusable")
            return {"ok": False, "reason": "bad geometry"}
        skipped = self.skipped_today(name)
        asg = [a for a in assignments(self.cfg, name) if a["account"] not in skipped]
        if not asg:
            self.journal("levels_refused", strategy=name, reason="no_assignments",
                         skipped=sorted(skipped), source=source)
            self.note_inactive(name, "no_assignments", "no accounts booked (or every one skipped today)")
            return {"ok": False, "reason": "no accounts booked (or every one is skipped today)"}
        legs: dict[str, AccountLeg] = {}
        sat_out: dict[str, str] = {}
        for a in asg:
            aid = a["account"]
            acct = self.cfg.accounts.get(aid)
            if not cfg.ack_open_loss and not (acct is not None and acct.paper):
                sat_out[aid] = "open-loss rule not acknowledged (ack_open_loss)"
                continue
            book = await self.prepare_account(aid)
            leg, why = account_leg(cfg, aid, int(a["qty"]), self.rules_for(aid), book, geo,
                                   book.morning_profit)
            if leg is None:
                sat_out[aid] = why
            else:
                legs[aid] = leg
        base = {"upper": geo.upper, "lower": geo.lower, "sl_pts": geo.sl_pts, "atr": geo.atr,
                "geometry": geo.to_dict(), **info}
        if not legs:
            self.journal("levels_refused", strategy=name, reason="every_account_sat_out",
                         sat_out=sat_out, source=source, **base)
            self.note_inactive(name, "every_account_sat_out",
                               "; ".join(f"{k}: {v}" for k, v in sat_out.items()) or "every account sat out")
            return {"ok": False, "reason": "every account sat out", "sat_out": sat_out}
        if not self.cfg.armed or cfg.shadow:
            ev = "shadow_signal" if (self.cfg.armed and cfg.shadow) else "dry_run"
            for aid, leg in legs.items():
                self.journal(ev, strategy=name, source=source, account=aid, qty=leg.qty,
                             tp_pts=leg.tp_pts, take_usd=leg.take_usd, take_src=leg.take_src,
                             stop_usd=leg.stop_usd, sat_out=sat_out, **base)
            return {"ok": True, "armed": False, "accounts": len(legs), "sat_out": sat_out,
                    "note": ("shadow — journaled only" if ev == "shadow_signal"
                             else "disarmed — journaled only")}
        order = list(legs)
        if self.rotating(name):
            turn = self._one_turn(name, cfg, order)
            if turn is None:
                return {"ok": False, "reason": ROTATION_NONE, "sat_out": sat_out}
            order = [turn]
        t0 = time.time()
        outs = await asyncio.gather(
            *(self._place(name, cfg, aid, legs[aid].qty, geo.upper, geo.lower, source, t0,
                          leg=legs[aid], sl_pts=geo.sl_pts, sl_sell_pts=geo.sl_sell_pts) for aid in order),
            return_exceptions=True)
        results = {aid: (o if isinstance(o, dict) else {"ok": False, "reason": str(o)})
                   for aid, o in zip(order, outs)}
        self.journal("levels_placed", strategy=name, source=source, sat_out=sat_out,
                     accounts={aid: {"qty": legs[aid].qty, "tp_pts": legs[aid].tp_pts,
                                     "take_usd": legs[aid].take_usd, "take_src": legs[aid].take_src,
                                     "stop_usd": legs[aid].stop_usd,
                                     "ok": bool(results[aid].get("ok"))} for aid in order}, **base)
        return {"ok": any(r.get("ok") for r in results.values()), "armed": True,
                "accounts": results, "sat_out": sat_out}

    async def _place_one(self, name: str, cfg: StrategyCfg, account: str, qty: int,
                         sig, source: str, t0: float) -> dict:
        locked = self.account_locked(account)
        if locked:                       # day_take / day_lock: stopped for the day -- nothing new goes out
            self.journal("place_skipped", strategy=name, account=account, reason=f"locked:{locked}")
            return {"ok": False, "reason": f"account stopped for the day ({locked})"}
        if cfg.kind != LAB and self._slot_busy(name, cfg, account, lab_only=True):
            # a Lab round (or another built-in) of this market is open on the account: one trade at a time. A
            # straddle sits the account out for the day -- placed late it would trade stale levels.
            self.journal("place_skipped", strategy=name, account=account, reason=LAB_SLOT_BUSY)
            if cfg.kind == "straddle":
                self.skip_today(name, account)
            return {"ok": False, "reason": LAB_SLOT_BUSY}
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
        if self.killed_today(name):          # killed while the acks were outstanding
            await self._kill_after_ack(st, cfg, ad)
        return {"ok": True, "order_id": r.order_id}

    @staticmethod
    def _legs(cfg: StrategyCfg, upper: float, lower: float, qty: int,
              sl_pts: float | None = None, tp_pts: float | None = None,
              sl_sell_pts: float | None = None) -> list[OrderRequest]:
        sl = cfg.sl_pts if sl_pts is None else sl_pts      # "levels": this account's geometry today
        sl_sell = sl if sl_sell_pts is None else sl_sell_pts
        tp = cfg.tp_pts if tp_pts is None else tp_pts
        return [
            OrderRequest(symbol=cfg.symbol, side="Buy", qty=qty,
                         order_type="Stop", price=upper,
                         stop_price=upper - sl, tp_price=upper + tp,
                         text="homebase:entry"),
            OrderRequest(symbol=cfg.symbol, side="Sell", qty=qty,
                         order_type="Stop", price=lower,
                         stop_price=lower + sl_sell, tp_price=lower - tp,
                         text="homebase:entry"),
        ]

    async def _place(self, name: str, cfg: StrategyCfg, account: str, qty: int,
                     upper: float, lower: float, source: str,
                     t0: float | None = None, leg: AccountLeg | None = None,
                     sl_pts: float | None = None, sl_sell_pts: float | None = None,
                     reqs: tuple[OrderRequest, OrderRequest] | None = None) -> dict:
        locked = self.account_locked(account)
        if locked:                       # day_take / day_lock: stopped for the day -- nothing new goes out
            self.journal("place_skipped", strategy=name, account=account, reason=f"locked:{locked}")
            return {"ok": False, "reason": f"account stopped for the day ({locked})"}
        if cfg.kind != LAB and self._slot_busy(name, cfg, account, lab_only=True):
            # a Lab round (or another built-in) of this market is open on the account: one trade at a time. A
            # straddle sits the account out for the day -- placed late it would trade stale levels.
            self.journal("place_skipped", strategy=name, account=account, reason=LAB_SLOT_BUSY)
            if cfg.kind == "straddle":
                self.skip_today(name, account)
            return {"ok": False, "reason": LAB_SLOT_BUSY}
        st = self._state(name, account)
        ad = self.adapters.get(account)
        if ad is None or not ad.connected:
            st.status, st.exit_reason = "error", "error"
            st.note = "account not connected"
            self._save()
            self.journal("place_failed", strategy=name, account=account,
                         error="account not connected")
            return {"ok": False, "reason": "account not connected"}
        if leg is not None:              # kind "levels": the account's own stop / take, kept for the fill
            st.sl_pts, st.sl_sell_pts, st.tp_pts = sl_pts, sl_sell_pts, leg.tp_pts
            st.take_usd, st.take_src = leg.take_usd, leg.take_src
        st.qty = qty
        # from here a second signal is refused, and an entry fill that beats
        # the acks is held instead of dropped (on_fill -> _replay_early)
        st.status = "placing"
        self._save()     # durable before the legs go out: a restart mid-flight sees a day that acted
        buy, sell = reqs or self._legs(cfg, upper, lower, qty, st.sl_pts, st.tp_pts, st.sl_sell_pts)
        rtt: dict = {}

        async def timed_leg(name: str, req: OrderRequest) -> OrderResult:
            # timing only: each leg's OWN round trip (sent -> the broker's answer),
            # journaled as leg_ms beside the prestage's prestage_rtt_ms
            t = self._perf()
            try:
                return await ad.place_bracket(req)
            finally:
                rtt[name] = round((self._perf() - t) * 1000, 1)

        # Both legs go out together — the second no longer waits a full round
        # trip for the first. A leg that raises counts as rejected.
        r_up, r_dn = [r if isinstance(r, OrderResult) else OrderResult(ok=False, error=str(r))
                      for r in await asyncio.gather(timed_leg("upper", buy),
                                                    timed_leg("lower", sell),
                                                    return_exceptions=True)]
        leg_ms = {"upper": rtt.get("upper"), "lower": rtt.get("lower")}
        if not (r_up.ok and r_dn.ok):
            # never leave half a straddle: cancel whichever leg did go in
            leg, err = ("upper", r_up.error) if not r_up.ok else ("lower", r_dn.error)
            survivor = r_dn if not r_up.ok else r_up
            failed = r_up if not r_up.ok else r_dn
            cancelled, cancel_err = None, None
            if survivor.ok:
                for _ in range(3):         # a refused cancel is retried, and read back: it may have gone anyway
                    try:
                        c = await ad.cancel_order_by_id(survivor.order_id)
                        cancelled, cancel_err = (survivor.order_id if c.ok else None), (None if c.ok else c.error)
                    except Exception as e:  # noqa: BLE001 — a raise is a refused cancel
                        cancelled, cancel_err = None, str(e)
                    if cancelled is not None:
                        break
                    with contextlib.suppress(Exception):
                        if await ad.get_order_status(survivor.order_id) in ("Canceled", "Rejected", "Expired"):
                            cancelled = survivor.order_id
                            break
            st.status, st.exit_reason, st.note = "error", "error", f"{leg} leg: {err}"
            if survivor.ok and cancelled is None:     # the other leg is still working at the broker
                st.upper_id, st.lower_id = (survivor.order_id, None) if leg == "lower" else (None, survivor.order_id)
                st.note += f" — check it: the other leg {survivor.order_id} is still working ({cancel_err})"
                # still resting: "placed", so its fill is tracked and booked, 12:55 cancels it and the day lock sees it
                st.status, st.exit_reason = "placed", None
            if (failed.raw or {}).get("outcome_unknown"):        # no answer: that leg may be working too
                st.note += " — its outcome is unknown, check the broker"
            self._save()
            self.journal("place_failed", strategy=name, account=account, leg=leg,
                         error=err, cancelled=cancelled, survivor_cancel_error=cancel_err,
                         outcome_unknown=bool((failed.raw or {}).get("outcome_unknown")),
                         leg_ms=leg_ms)
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
                     **({"sl_pts": st.sl_pts, "sl_sell_pts": st.sl_sell_pts, "tp_pts": st.tp_pts, "take_usd": st.take_usd,
                         "take_src": st.take_src, "stop_usd": leg.stop_usd} if leg is not None else {}),
                     upper_id=st.upper_id, lower_id=st.lower_id,
                     # anchor -> both legs acknowledged by the broker; the
                     # only latency the strategy is actually exposed to
                     place_ms=(None if t0 is None
                               else round((time.time() - t0) * 1000)),
                     # each leg's own round trip: legs far apart = the broker
                     # queues them; both far above prestage_rtt_ms = the open
                     leg_ms=leg_ms)
        await self._replay_early(account)
        if self.killed_today(name):          # killed while the acks were outstanding
            await self._kill_after_ack(st, cfg, ad)
        return {"ok": True, "upper_id": st.upper_id, "lower_id": st.lower_id}

    async def _replay_early(self, account: str) -> None:
        """Entry fills that arrived before this account's acks: run them now."""
        mine = [e for e in self._early if e.account_id == account]
        self._early = [e for e in self._early if e.account_id != account]
        for ev in mine:
            await self.on_fill(ev)

    # --- broker fills ---------------------------------------------------------
    async def on_fill(self, ev: FillEvent) -> None:
        got = self._perf()                   # timing only (_fill_timing)
        oid = str((ev.raw or {}).get("orderId") or "")
        remainder = 0                        # a flatten fill's contracts no done run took
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
                self._set_take_px(st, cfg)
                self._save()
                tm: dict = {}

                async def timed_cancel(coro) -> OrderResult:
                    # timing only: when the sibling cancel went out and when the broker
                    # answered it, journaled in entry_fill's fill_ms
                    tm["cancel_sent"] = self._perf()
                    try:
                        return await coro
                    finally:
                        tm["cancel_ack"] = self._perf()

                jobs = [timed_cancel(ad.cancel_order_by_id(sibling)) if sibling
                        else asyncio.sleep(0, result=OrderResult(ok=True))]
                if st.entry_qty >= st.qty:          # whole entry in: SL/TP to the fill
                    jobs.append(self._move_brackets(st, cfg, ad))
                r, *moved = await asyncio.gather(*jobs, return_exceptions=True)
                if isinstance(r, Exception):
                    r = OrderResult(ok=False, error=str(r))
                if r.ok and sibling:   # let the broker confirm before the backstop re-checks
                    self._retry_at[f"sib:{st.strategy}@{st.account}"] = time.time()
                if sibling:            # accepted is not cancelled: sibling_tick asks until it is
                    self._sib_watch[f"{st.strategy}@{st.account}"] = time.time()
                self.journal("entry_fill", strategy=st.strategy, account=st.account,
                             side=st.entry_side, fill=ev.price, anchor=st.entry_anchor,
                             fill_vs_anchor=(None if ev.price is None or st.entry_anchor is None
                                             else round(ev.price - st.entry_anchor, 4)),
                             qty_filled=st.entry_qty,
                             sibling_cancelled=r.ok, sibling_error=r.error,
                             **self._fill_timing(ev, got, tm))
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
                self._set_take_px(st, cfg)
                self._save()
                self.journal("entry_fill", strategy=st.strategy, account=st.account,
                             side=st.entry_side, fill=st.entry_fill, anchor=st.entry_anchor,
                             fill_vs_anchor=(None if st.entry_fill is None or st.entry_anchor is None
                                             else round(st.entry_fill - st.entry_anchor, 4)),
                             qty_filled=n, **self._fill_timing(ev, got, {}))
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
                    and ev.side != st.entry_side and not self._owned_by_other(oid, st):
                # an exit can come in pieces, and before the whole entry is in (gc_nfp 2026-10-02:
                # 1 contract in, 1 out, then the other 3): keep the AVERAGE exit and stay live
                # until every contract that went in is out again (_close_if_out)
                q = int(ev.qty or 0) or max(st.entry_qty - st.exit_qty, 1)
                if st.entry_qty and st.entry_qty >= st.qty:   # a whole entry: never more out than went in -- a
                    if st.exit_qty >= st.entry_qty:     # stray or repeated exit fill is not this run's
                        continue
                    q = min(q, st.entry_qty - st.exit_qty)
                if ev.price is not None:
                    st.exit_fill = (ev.price if st.exit_fill is None or not st.exit_qty else
                                    (st.exit_fill * st.exit_qty + ev.price * q) / (st.exit_qty + q))
                st.exit_qty += q
                if not await self._close_if_out(st, cfg, ad):
                    self._save()
                    self.journal("exit_part", strategy=st.strategy, account=st.account,
                                 fill=ev.price, qty=q, out=st.exit_qty, entered=st.entry_qty)
                return
            if st.status == "done" and st.entry_fill is not None and cfg.kind != "lab" \
                    and ev.symbol and cfg.symbol.upper() in ev.symbol.upper() \
                    and ev.side != st.entry_side and not self._owned_by_other(oid, st) \
                    and (took := await self._book_flat_fill(st, cfg, ev)):
                # one market-out sells the account's WHOLE net: what this run did not hold goes to the next done run
                left = int(ev.qty or 0) - took
                if left <= 0:
                    return
                ev = dataclasses.replace(ev, qty=left)
                remainder = left
        if remainder:
            self.journal("exit_fill_remainder", account=ev.account_id, symbol=ev.symbol, qty=remainder, fill=ev.price)
            return
        # Nothing matched. An entry fill can beat the placement acks — the
        # order is live at the broker before we know its id — so while this
        # account is placing, hold it; _place replays it once the ids are in.
        if any(s.status == "placing" and s.account == ev.account_id
               for s in self.states.values()):
            self._early.append(ev)

    @staticmethod
    def _ids(st: DayState) -> set:
        return {i for i in (st.upper_id, st.lower_id, st.up_sl_id, st.up_tp_id, st.dn_sl_id, st.dn_tp_id) if i}

    def _owned_by_other(self, oid: str, st: DayState) -> bool:
        """The fill's order is one another run of this account placed (its entry or its stop / target)."""
        if not oid:
            return False
        mine = self._ids(st)
        return oid not in mine and any(o is not st and o.account == st.account and oid in self._ids(o)
                                       for o in self.states.values())

    async def _book_flat_fill(self, st: DayState, cfg: StrategyCfg, ev: FillEvent) -> int:
        """The market-out of a flatten / kill / clock-flat, or of the day_take watcher, fills AFTER the run was
        closed (status done at once): book its real fill. A flatten-type exit with no P&L yet takes the fill
        into exit_fill / exit_qty and books the trade when every contract is out; a day_take run booked at the
        last print is trued up to the fill. -> the contracts of the fill this run took (0: none)."""
        entered = int(st.entry_qty or st.qty or 0)
        q = int(ev.qty or 0)
        if ev.price is None or q <= 0 or entered <= 0:
            return 0
        if any(o is not st and o.account == st.account and o.status == "live"
               and (c := self.cfg.strategies.get(o.strategy)) is not None and c.symbol == cfg.symbol
               for o in self.states.values()):
            return 0                         # another live run here owns that fill as much as this one: not told apart
        if st.exit_reason == "day_take" and st.note == TAKE_PRINT_NOTE and st.pnl is not None:
            if q < entered:
                return 0                     # a piece of it: the print booking stands
            old = self._net_pnl(st, cfg, st.pnl)
            st.exit_fill, st.note = ev.price, ""
            st.pnl = self._gross_pnl(st, cfg)
            book = self.book(st.account)
            book.closed_net = round(book.closed_net + (self._net_pnl(st, cfg, st.pnl) or 0.0) - (old or 0.0), 2)
            self._save()
            self._save_books()
            self.journal("exit_fill", strategy=st.strategy, account=st.account, reason="day_take",
                         fill=st.exit_fill, qty=entered, pnl=st.pnl, trued_up=True)
            return entered
        if st.pnl is not None or st.exit_reason not in ("flat", "manual_flat", "killed") or st.exit_qty >= entered:
            return 0
        q = min(q, entered - st.exit_qty)
        st.exit_fill = (ev.price if st.exit_fill is None or not st.exit_qty else
                        (st.exit_fill * st.exit_qty + ev.price * q) / (st.exit_qty + q))
        st.exit_qty += q
        if st.exit_qty < entered:
            self._save()
            self.journal("exit_part", strategy=st.strategy, account=st.account, fill=ev.price, qty=q,
                         out=st.exit_qty, entered=entered)
            return q
        st.pnl = self._gross_pnl(st, cfg)
        self._save()
        self.journal("exit_fill", strategy=st.strategy, account=st.account, reason=st.exit_reason,
                     fill=st.exit_fill, qty=st.exit_qty, pnl=st.pnl)
        await self._book_close(st, cfg)
        return q

    def _fill_timing(self, ev: FillEvent, got: float, tm: dict) -> dict:
        """Timing only, journaled on entry_fill.  fill_seen_ts: when the fill was first seen (epoch
        seconds) -- its push on the socket, or on_fill for an adapter that stamps none.  fill_ms: ms
        after that until a broker read had filled the push in (None: none was needed) and until the
        sibling cancel went out and was answered (None: no sibling to cancel)."""
        seen = got if ev.seen is None else ev.seen

        def ms(t):
            return None if t is None else round((t - seen) * 1000, 1)

        return {"fill_seen_ts": round(time.time() - (self._perf() - seen), 3),
                "fill_ms": {"enriched": ms(ev.enriched), "cancel_sent": ms(tm.get("cancel_sent")),
                            "cancel_ack": ms(tm.get("cancel_ack"))}}

    async def _move_brackets(self, st: DayState, cfg: StrategyCfg,
                             ad: BrokerAdapter) -> dict:
        """The research measures SL/TP from the ACTUAL (average) fill, not the
        trigger. Once the whole entry is in, move both brackets there. A fill
        at the trigger moves nothing; a failed move leaves the trigger
        brackets working — still protected, just not re-priced."""
        if cfg.kind == "lab":
            return await self._lab_move(st, cfg, ad)
        st.brackets_moved = True                  # once per trade
        if st.entry_fill is None:
            return {"moved": False, "error": "no fill price"}
        sign = 1 if st.entry_side == "Buy" else -1
        tick = tick_size(cfg.symbol) or 0.25
        sl_id, tp_id = ((st.up_sl_id, st.up_tp_id) if st.entry_side == "Buy"
                        else (st.dn_sl_id, st.dn_tp_id))
        # a rule whose config gives SL/TP points (open_long/open_short) moves
        # both levels to the fill below, like a straddle
        sl_pts = cfg.sl_pts if st.sl_pts is None else st.sl_pts      # "levels": the account's own, today
        if sign < 0 and st.sl_sell_pts is not None:
            sl_pts = st.sl_sell_pts                                   # the sell leg's own stop distance
        tp_pts = cfg.tp_pts if st.tp_pts is None else st.tp_pts
        fixed = st.tp_rr is None and sl_pts > 0 and tp_pts > 0
        if st.sl_px is not None and not fixed:
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
        sl = _to_tick(st.entry_fill - sign * sl_pts, tick)
        tp = _to_tick(st.entry_fill + sign * tp_pts, tick)
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
        if st.sl_px is not None:             # a fixed-distance rule: record the levels that moved
            for k, px, r in zip(("sl_px", "tp_px"), (sl, tp), res):
                if not isinstance(r, Exception) and r.ok:
                    setattr(st, k, px)
            self._save()
        return {**out, "moved": not errs, **({"error": "; ".join(errs)} if errs else {})}

    def _journal_moved(self, st: DayState, moved) -> None:
        if isinstance(moved, Exception):
            moved = {"moved": False, "error": str(moved)}
        self.journal("brackets_moved", strategy=st.strategy, account=st.account, **moved)

    def _entry_id(self, st: DayState) -> Optional[str]:
        return st.upper_id if st.entry_side == "Buy" else st.lower_id

    def _set_take_px(self, st: DayState, cfg: StrategyCfg) -> None:
        """A "levels" trade's take price, where its broker-side limit rests: the fill (the trigger when no
        fill price is known) plus tp_pts on the entry's side.  The price watcher (check_takes) reads it."""
        if st.tp_pts is None or st.entry_side is None:
            return
        base = st.entry_fill if st.entry_fill is not None else st.entry_anchor
        if base is None:
            return
        sign = 1 if st.entry_side == "Buy" else -1
        st.take_px = _to_tick(base + sign * st.tp_pts, tick_size(cfg.symbol) or 0.25)

    def _grade_exit(self, st: DayState, px: Optional[float]) -> str:
        cfg = self.cfg.strategies[st.strategy]
        if cfg.kind == "lab":
            return self._lab_grade(st, px)
        if px is None:
            return "exit"
        if st.tp_pts is not None and st.sl_pts is not None and st.entry_fill is not None:
            sign = 1 if st.entry_side == "Buy" else -1           # "levels": this account's own geometry
            sl_pts = st.sl_sell_pts if (sign < 0 and st.sl_sell_pts is not None) else st.sl_pts
            return ("tp" if abs(px - (st.entry_fill + sign * st.tp_pts))
                    <= abs(px - (st.entry_fill - sign * sl_pts)) else "sl")
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
        return round(sign * (st.exit_fill - st.entry_fill) * pv * (st.exit_qty or st.qty), 2)

    async def _close_if_out(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter) -> bool:
        """A live run with exit fills: is the trade over? Only when every contract that went in is
        out again and the entry order can fill no more. An entry the broker already reads Filled
        counts whole, though its fill pushes may still be on their way. True = closed and booked."""
        entered = st.entry_qty
        if st.entry_qty < st.qty:
            entry = await ad.get_order_status(self._entry_id(st))
            if entry in WORKING:
                return False
            if entry == "Filled":
                entered = st.qty
        if st.exit_qty < entered:
            return False
        st.status = "done"
        st.exit_reason = self._grade_exit(st, st.exit_fill)
        st.pnl = self._gross_pnl(st, cfg)
        self._save()
        self.journal("exit_fill", strategy=st.strategy, account=st.account,
                     reason=st.exit_reason, fill=st.exit_fill, qty=st.exit_qty, pnl=st.pnl)
        await self._book_close(st, cfg)
        return True

    async def _guard_sibling(self, st: DayState, cfg: StrategyCfg,
                             ad: BrokerAdapter, gap: float = SIBLING_RETRY_S) -> Optional[str]:
        """After the entry the OTHER stop must be gone. Still working -> the
        cancel was refused or raced: cancel again (every `gap` s at most). Filled
        -> it opened a second, unmanaged position (even after the trade
        ended): close it and every bracket. Returns the sibling's status."""
        sib = st.lower_id if st.entry_side == "Buy" else st.upper_id
        if not sib:
            return None
        status = await ad.get_order_status(sib)
        if status == "Filled":
            st.status, st.exit_reason = "error", "both_filled"
            self._save()
            _, acts = await self._flatten_state(st, cfg, ad)
            self.journal("both_filled_emergency", strategy=st.strategy,
                         account=st.account, order_id=sib,
                         found_by="sibling_check", actions=acts)
            return status
        if status in WORKING:
            key = f"sib:{st.strategy}@{st.account}"
            if time.time() - self._retry_at.get(key, 0.0) < gap:
                return status
            self._retry_at[key] = time.time()
            r = await ad.cancel_order_by_id(sib)
            self.journal("sibling_cancel_retry", strategy=st.strategy,
                         account=st.account, order_id=sib, ok=r.ok, error=r.error)
        return status

    async def sibling_tick(self) -> None:
        """The fast half of the sibling backstop (the server calls it 4 times a second; the clock's
        own check runs once a second and re-sends every 2 s). For SIBLING_WATCH_S after an entry
        fill: is the other entry really gone? Still working -> its cancel goes out again every
        SIBLING_FAST_S. One journal line says how it ended. 2026-10-02 gc_nfp: the broker accepted
        the sell stop's cancel and the order kept working until it was cancelled by hand."""
        for key, t0 in list(self._sib_watch.items()):
            st = self.states.get(key)
            cfg = self.cfg.strategies.get(st.strategy) if st is not None else None
            ad = self.adapters.get(st.account) if st is not None else None
            if cfg is None or ad is None or not st.entry_side:
                del self._sib_watch[key]
                continue
            if not ad.connected:       # a dead socket's cache is stale; reconnect reconciles
                continue
            status, error = None, None
            try:
                status = await self._guard_sibling(st, cfg, ad, gap=SIBLING_FAST_S)
            except Exception as e:  # noqa: BLE001 — one account's read never stops the others
                error = str(e)[:200]
            waited = time.time() - t0
            if status in TERMINAL or waited >= SIBLING_WATCH_S:
                del self._sib_watch[key]
                if status != "Filled":             # a fill is told by both_filled_emergency
                    self.journal("sibling_cancel_confirmed" if status in TERMINAL
                                 else "sibling_cancel_unconfirmed", strategy=st.strategy,
                                 account=st.account, status=status, error=error,
                                 after_ms=round(waited * 1000))

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
        self._set_take_px(st, cfg)          # no fill price is known: the take rests from the trigger
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
            else:
                try:
                    net = await ad.get_net_position(cfg.symbol)
                except Exception as e:  # noqa: BLE001 — unreadable is not flat; the next reconnect asks again
                    self.journal("exit_recovery_unreadable", strategy=st.strategy, account=account, error=str(e)[:200])
                    continue
                if net:
                    continue
                st.status = "done"
                st.exit_reason = st.exit_reason or "closed_while_disconnected"
                px = await self._recovered_exit_px(st, cfg, ad)
                booked = False
                if px is not None and st.entry_fill is not None:
                    st.exit_fill, st.exit_qty = px, int(st.entry_qty or st.qty or 0)
                    st.exit_reason = self._grade_exit(st, px)
                    st.pnl = self._gross_pnl(st, cfg)
                    booked = st.pnl is not None
                if not booked:
                    st.note = "closed while disconnected — check it: its P&L was not booked"
                self._save()
                self.journal("exit_recovered_on_reconnect", strategy=st.strategy,
                             account=account, fill=st.exit_fill, pnl=st.pnl, booked=booked)
                if booked:
                    await self._book_close(st, cfg)
                out[st.strategy] = "exit_recovered"
        return out

    async def _recovered_exit_px(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter) -> Optional[float]:
        """A run the bracket closed while the socket was down: its exit price is its target / stop when exactly one of
        them reads Filled at the broker (an estimate: a stop can slip). None: not known -- nothing is booked."""
        if st.entry_fill is None or not st.entry_side:
            return None
        buy = st.entry_side == "Buy"
        sl_id, tp_id = (st.up_sl_id, st.up_tp_id) if buy else (st.dn_sl_id, st.dn_tp_id)
        try:
            sl_s = await ad.get_order_status(sl_id) if sl_id else None
            tp_s = await ad.get_order_status(tp_id) if tp_id else None
        except Exception:  # noqa: BLE001
            return None
        if (sl_s == "Filled") == (tp_s == "Filled"):
            return None                      # neither, or both: not told apart
        if st.sl_px is not None and st.tp_px is not None:           # a rule's absolute levels
            return st.tp_px if tp_s == "Filled" else st.sl_px
        sign = 1 if buy else -1
        sl_pts = st.sl_pts if st.sl_pts is not None else cfg.sl_pts
        if not buy and st.sl_sell_pts is not None:
            sl_pts = st.sl_sell_pts
        tp_pts = st.tp_pts if st.tp_pts is not None else cfg.tp_pts
        if not (sl_pts > 0 and tp_pts > 0):
            return None
        return st.entry_fill + sign * tp_pts if tp_s == "Filled" else st.entry_fill - sign * sl_pts

    def day_states_for_account(self, account: str) -> list[DayState]:
        today = self._today()
        return [s for s in self.states.values()
                if s.account == account and s.date == today]

    # --- the clock ------------------------------------------------------------
    def needs_check(self, st: DayState) -> bool:
        """A run of a strategy killed today that is still placed or live, or
        whose kill market-out reported failure."""
        if not self.killed_today(st.strategy):
            return False
        return st.status in ("placed", "live") or \
            (st.status == "done" and st.note == MARKET_OUT_FAILED)

    def _journal_needs_check(self, st: DayState, cfg: StrategyCfg, now: dt.time) -> None:
        """killed_run_needs_check, once at cancel_et (12:55) and once at
        flat_et (15:55), for each such run."""
        for at in (cfg.cancel_et, cfg.flat_et):
            key = (st.date, st.strategy, st.account, at)
            if now >= _hhmm(at) and key not in self._needs_check_said:
                self._needs_check_said.add(key)
                self.journal("killed_run_needs_check", strategy=st.strategy, account=st.account,
                             status=st.status, at=at)

    async def clock_tick(self) -> None:
        """One tick of the clock for every run of today. The accounts go side by
        side (each_account); one account's runs go one after another, each with
        its steps in the order below. A run whose tick raises is journaled
        (`clock_error`) and never holds back another run's cancel or flatten."""
        now = self.now_et().time()

        async def tick(st: DayState) -> None:
            cfg = self.cfg.strategies.get(st.strategy)
            ad = self.adapters.get(st.account)
            if cfg is None or ad is None or st.date != self._today():
                return
            if cfg.kind == "lab":
                return await self._lab_tick(st, cfg, ad, now)
            # A run of a strategy KILLED today that is still placed/live is a
            # "check it" run (the kill could not attribute its position): a
            # human's job. Its stop/target stay working; it is never promoted
            # at 12:55 nor flattened at 15:55 on the account-wide net.
            check_it = self.needs_check(st)
            if check_it:
                self._journal_needs_check(st, cfg, now)
            if st.status == "placed" and now < _hhmm(cfg.cancel_et):
                if ad.connected:   # a dead socket's cache is stale; reconnect reconciles
                    await self._guard_placed(
                        st, cfg, ad, check_position=False,
                        event="entry_found_by_check",
                        note="fill push missed — entry found by the order-status check")
            elif st.status == "placed" and now >= _hhmm(cfg.cancel_et) and not check_it:
                refused = []
                for oid in (st.upper_id, st.lower_id):
                    if oid:
                        c = await ad.cancel_order_by_id(oid)
                        if not c.ok and await ad.get_order_status(oid) in WORKING:
                            refused.append(f"{oid}: {c.error}")
                if refused:                  # an entry still rests: the day is not over, the next tick cancels again
                    key = f"cancelfail:{st.strategy}@{st.account}"
                    if time.time() - self._retry_at.get(key, 0.0) >= 60.0:      # one line a minute, not one a tick
                        self._retry_at[key] = time.time()
                        self.journal("cancel_entries_failed", strategy=st.strategy, account=st.account,
                                     errors=refused)
                    return
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
            elif st.status == "placed" and now >= _hhmm(cfg.cancel_et):
                # a killed "check it" run: its entries are still cancelled at
                # 12:55 (once), but it is never promoted to live on the net
                key = (st.date, st.strategy, st.account)
                if key not in self._check_it_cancelled:
                    self._check_it_cancelled.add(key)
                    acts = []
                    for oid in (st.upper_id, st.lower_id):
                        if oid:
                            r = await ad.cancel_order_by_id(oid)
                            acts.append(f"cancel {oid}: " + ("ok" if r.ok else str(r.error)))
                    self.journal("killed_run_entries_cancelled", strategy=st.strategy,
                                 account=st.account, actions=acts)
            elif st.status == "live" and now >= _hhmm(cfg.flat_et) and not check_it:
                key = f"flat:{st.strategy}@{st.account}"
                if time.time() - self._retry_at.get(key, 0.0) < 5.0:
                    return                            # a failed flat retries every 5 s
                self._retry_at[key] = time.time()
                t = self._perf()
                flat, acts = await self._flatten_state(st, cfg, ad)
                if flat:
                    st.status, st.exit_reason = "done", st.exit_reason or "flat"
                    self._save()
                self.journal("clock_flat" if flat else "clock_flat_failed",
                             strategy=st.strategy, account=st.account, actions=acts,
                             flat_ms=round((self._perf() - t) * 1000, 1))      # timing only
            if st.status == "live" and st.exit_qty and ad.connected:
                await self._close_if_out(st, cfg, ad)   # out, and the rest of the entry was cancelled
            if st.status in ("live", "done") and st.entry_side and ad.connected:
                await self._guard_sibling(st, cfg, ad)

        by_account: dict[str, list[DayState]] = {}
        for st in list(self.states.values()):
            by_account.setdefault(st.account, []).append(st)

        async def account(a: str) -> None:
            for st in by_account[a]:
                try:
                    await tick(st)
                except Exception as e:  # noqa: BLE001 — the other runs still get their tick
                    self.journal("clock_error", strategy=st.strategy, account=a, error=str(e))

        got, _ = await self.each_account(by_account, account)
        for g in got.values():
            if isinstance(g, BaseException):         # the journal itself failed: the clock loop says so
                raise g
