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
import datetime as dt
import json
import sys
import time
from dataclasses import asdict, dataclass
from typing import Callable, Optional
from zoneinfo import ZoneInfo

from .broker.base import BrokerAdapter, FillEvent, OrderRequest, OrderResult
from .config import AppCfg, StrategyCfg, assignments
from .contracts import point_value, tick_size
from .levels import AccountLeg, Geometry, account_leg
from .paths import state_dir
from .dayrules import LOCK_TAKE, DayBook, DayRules, merge_rules, standing, take_level

ET = ZoneInfo("America/New_York")
SPREAD_TOL_PTS = 0.05
WORKING = {"Working", "PendingNew", "Pending", "Suspended", "PendingReplace"}
TERMINAL = {"Filled", "Canceled", "Rejected", "Expired"}    # an order that can never fill (more)
KILL_POLL_S, KILL_POLL_N = 0.25, 12     # the kill waits up to 3 s for its entry cancels to settle
# Accounts whose exits run side by side (each_account). A bound, not "all at once": the broker caps a
# login's requests per second / minute / hour (values unpublished), a 429 is never retried on the order
# path, and several desk entries ride one login. 4 accounts x (6 cancels at once) = 24 requests out
# together at most.
EXIT_CONCURRENCY = 4
MARKET_OUT_FAILED = "check it — market-out reported failure; verify the position"
PLACING_UNKNOWN = "placement outcome unknown after a restart — check the broker"
SIBLING_RETRY_S = 2.0
TAKE_GRACE_S = 2.0      # a day_take touch the resting limit has not filled for this long is market-flattened


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
    # kind "levels": this account's geometry today (points from the trigger / the fill), set at placement
    sl_pts: Optional[float] = None
    sl_sell_pts: Optional[float] = None   # the sell leg's stop distance when it differs from sl_pts (levels.leg_stop)
    tp_pts: Optional[float] = None
    take_usd: Optional[float] = None   # the net $ the take is sized for (None: the fallback target)
    take_src: str = ""                 # day_take | target_take | fallback
    take_px: Optional[float] = None    # the take price the broker-side limit rests at (from the fill)


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

    # --- account day books (day_take / day_lock / target_take) ---------------------------
    def _books_path(self):
        return self._root / f"daybook-{self._today()}.json"

    def _load_books(self) -> None:
        """Restart safety: today's closed P&L, locks and morning standing come back from disk.  An
        unreadable file means a fresh day, said on stderr -- never a crash."""
        p = self._books_path()
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text())
            self.books = {a: DayBook.from_dict(d) for a, d in data.items()
                          if isinstance(d, dict) and d.get("date") == self._today()}
        except Exception as e:  # noqa: BLE001
            print(f"homebase engine: reading {p.name} failed: {e!r}", file=sys.stderr)

    def _save_books(self) -> None:
        self._books_path().write_text(json.dumps({a: b.to_dict() for a, b in self.books.items()},
                                                 indent=2) + "\n")

    def book(self, account: str) -> DayBook:
        today = self._today()
        b = self.books.get(account)
        if b is None or b.date != today:
            b = self.books[account] = DayBook(account=account, date=today)
        return b

    def rules_for(self, account: str) -> DayRules:
        """The daily rules in force on an account: the tightest of every ENABLED strategy booked on it."""
        rs = [DayRules(s.day_take, s.day_lock, s.target_take)
              for n, s in self.cfg.strategies.items()
              if s.enabled and any(a.get("account") == account for a in assignments(self.cfg, n))]
        return merge_rules(rs)

    def account_locked(self, account: str) -> Optional[str]:
        """"day_take" / "day_lock" when the account is stopped for the day, else None."""
        b = self.books.get(account)
        return b.locked if b is not None and b.date == self._today() else None

    async def prepare_account(self, account: str) -> DayBook:
        """Read the account's eval standing once a day, before its first fire: EOD profit (balance - start
        balance), the largest winning day and trading days so far (the desk's daily balance record + the
        account's seeds), and target_take's level for today.  Missing facts leave the level None (an
        account that needs one sits out) and the profit None (tiers use their smallest size)."""
        b = self.book(account)
        if b.prepared:
            return b
        acct = self.cfg.accounts.get(account)
        prop = dict(getattr(acct, "prop", None) or {})
        today = self._today()
        profit = None
        if prop.get("start_balance") is not None:
            start = float(prop["start_balance"])
            hist: dict = {}
            try:
                hist = (self.balance_history(account) if self.balance_history else None) or {}
            except Exception as e:  # noqa: BLE001
                self.journal("prepare_account_warn", account=account, error=f"balance history: {e}"[:200])
            prior = {d: v for d, v in hist.items() if d < today}
            bal = None
            ad = self.adapters.get(account)
            if ad is not None and ad.connected and not any(
                    s.status != "idle" for s in self.day_states_for_account(account)):
                try:
                    m = await ad.get_metrics()
                    bal = None if m.get("balance") is None else float(m["balance"])
                except Exception as e:  # noqa: BLE001
                    self.journal("prepare_account_warn", account=account, error=f"balance: {e}"[:200])
            if bal is not None:
                profit = bal - start
            elif prior:
                profit = float(prior[max(prior)]) - start
            largest, days = standing(prior, today, seed_largest=float(prop.get("largest_day") or 0),
                                     seed_days=int(prop.get("days") or 0))
            b.largest_day, b.days = largest, days
            if self.rules_for(account).target_take and profit is not None and prop.get("rules") \
                    and prop.get("mode", "eval") == "eval":
                try:
                    from .backtest.propsim import load_rules
                    r = load_rules(str(prop["rules"]))
                    b.target_level = take_level(r["eval_target"], profit, largest, days,
                                                min_days=int(r.get("eval_min_days") or 1),
                                                consistency=r.get("consistency"))
                except Exception as e:  # noqa: BLE001
                    self.journal("prepare_account_warn", account=account, error=f"rules: {e}"[:200])
        b.morning_profit, b.prepared = profit, True
        self._save_books()
        self.journal("account_prepared", account=account, profit=profit, largest_day=b.largest_day,
                     days=b.days, target_level=b.target_level, closed_net=b.closed_net)
        return b

    def _save(self) -> None:
        p = self._day_path(self._today())
        p.write_text(json.dumps({k: asdict(v) for k, v in self.states.items()},
                                indent=2) + "\n")

    def journal(self, event: str, **data) -> None:
        rec = {"ts": time.time(), "et": self.now_et().isoformat(timespec="seconds"),
               "event": event, **data}
        with open(self._root / "journal.jsonl", "a") as f:
            f.write(json.dumps(rec) + "\n")

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
        stats = {s.status for s in self.day_states(strategy)}
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
        return strategy in self._killed.get(self._today(), ())

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
        t0 = time.time()
        order = list(legs)
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
                     sl_pts: float | None = None, sl_sell_pts: float | None = None) -> dict:
        locked = self.account_locked(account)
        if locked:                       # day_take / day_lock: stopped for the day -- nothing new goes out
            self.journal("place_skipped", strategy=name, account=account, reason=f"locked:{locked}")
            return {"ok": False, "reason": f"account stopped for the day ({locked})"}
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
        buy, sell = self._legs(cfg, upper, lower, qty, st.sl_pts, st.tp_pts, st.sl_sell_pts)
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
            if survivor.ok:
                await ad.cancel_order_by_id(survivor.order_id)
            st.status, st.exit_reason, st.note = "error", "error", f"{leg} leg: {err}"
            self._save()
            self.journal("place_failed", strategy=name, account=account, leg=leg,
                         error=err, cancelled=survivor.order_id if survivor.ok else None,
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
                    and ev.side != st.entry_side:
                st.status = "done"
                st.exit_fill = ev.price
                st.exit_reason = self._grade_exit(st, ev.price)
                st.pnl = self._gross_pnl(st, cfg)
                self._save()
                self.journal("exit_fill", strategy=st.strategy, account=st.account,
                             reason=st.exit_reason, fill=ev.price, pnl=st.pnl)
                await self._book_close(st, cfg)
                return
        # Nothing matched. An entry fill can beat the placement acks — the
        # order is live at the broker before we know its id — so while this
        # account is placing, hold it; _place replays it once the ids are in.
        if any(s.status == "placing" and s.account == ev.account_id
               for s in self.states.values()):
            self._early.append(ev)

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
        return round(sign * (st.exit_fill - st.entry_fill) * pv * st.qty, 2)

    # --- daily rules: day_take / day_lock (risk.DayBook) ----------------------------------
    def _fee(self, st: DayState, cfg: StrategyCfg) -> float:
        return float(cfg.fee_rt) * int(st.entry_qty or st.qty or 0)

    def _net_pnl(self, st: DayState, cfg: StrategyCfg, gross: Optional[float]) -> Optional[float]:
        return None if gross is None else round(gross - self._fee(st, cfg), 2)

    async def _book_close(self, st: DayState, cfg: StrategyCfg) -> None:
        """A trade closed (an exit fill): its net P&L goes into the account's day.  The day_take / day_lock
        thresholds may stop the account for the rest of the day (no new entry anywhere on it, resting
        entries cancelled).  Never raises into on_fill."""
        try:
            net = self._net_pnl(st, cfg, st.pnl)
            if net is None:
                return
            rules, book = self.rules_for(st.account), self.book(st.account)
            lock = book.record_close(net, rules)
            self._save_books()
            self.journal("day_booked", strategy=st.strategy, account=st.account, net=net,
                         closed_net=book.closed_net, locked=book.locked)
            if lock:
                await self._lock_account(st.account, lock, why="a trade closed")
        except Exception as e:  # noqa: BLE001 — the fill is already in
            print(f"homebase engine: day book for {st.strategy}@{st.account} failed: {e!r}", file=sys.stderr)

    async def _lock_account(self, account: str, reason: str, *, why: str = "") -> None:
        """The account is stopped for the day: cancel every entry still resting on it (a later fill would
        be a new entry).  Open positions are left to their own stop / take (day_take's market-out is
        check_takes), except none remain after a take."""
        book = self.book(account)
        book.locked = book.locked or reason
        self._save_books()
        ad = self.adapters.get(account)
        cancelled = []
        for st in self.day_states_for_account(account):
            if st.status != "placed" or ad is None:
                continue
            for oid in (st.upper_id, st.lower_id, st.up_sl_id, st.up_tp_id, st.dn_sl_id, st.dn_tp_id):
                if oid:
                    r = await ad.cancel_order_by_id(oid)
                    cancelled.append(f"{oid}: {'ok' if r.ok else r.error}")
            st.status, st.exit_reason = "done", reason
        self._save()
        self.journal("day_rule_lock", account=account, reason=reason, why=why,
                     closed_net=book.closed_net, cancelled=cancelled)

    def _open_net(self, st: DayState, cfg: StrategyCfg, px: float) -> float:
        sign = 1 if st.entry_side == "Buy" else -1
        pv = point_value(cfg.symbol) or 0.0
        qty = int(st.entry_qty or st.qty or 0)
        return sign * (px - float(st.entry_fill)) * pv * qty - self._fee(st, cfg)

    async def _cancel_state_orders(self, st: DayState, ad: BrokerAdapter) -> tuple[bool, list[str]]:
        """Cancel every order one run placed (entries and brackets) -- no market order.  -> (all cancelled, acts)"""
        ids = [i for i in (st.upper_id, st.lower_id, st.up_sl_id, st.up_tp_id, st.dn_sl_id, st.dn_tp_id) if i]
        res = await asyncio.gather(*(ad.cancel_order_by_id(i) for i in ids), return_exceptions=True)
        acts, ok = [], True
        for i, r in zip(ids, res):
            good = not isinstance(r, Exception) and r.ok
            ok = ok and good
            acts.append(f"cancel {i}: " + ("ok" if good else str(r if isinstance(r, Exception) else r.error)))
        return ok, acts

    async def check_takes(self, prices: dict) -> list[dict]:
        """The day_take price watcher -- the backstop to the broker-side take limit.  `prices` maps a
        strategy symbol (cfg.symbol, "NQ") to the latest print.  Per account with a take in force: the
        day's closed P&L + the open P&L at that price, both net of fees, has TOUCHED the take (the tester's
        limit needs a tick of penetration; day_take does not).  The resting limit gets TAKE_GRACE_S to fill
        by itself; if the position is still open after that, the account's positions are market-flattened,
        its resting entries cancelled and it is stopped for the day.  _flatten_state reads the position
        first, so a limit that filled in the meantime is never sold twice.  Never polls equity.
        -> what it did (for the log / tests)."""
        out: list[dict] = []
        now = self._mono()
        for account in {s.account for s in self.states.values() if s.status == "live"
                        and s.date == self._today()}:
            rules = self.rules_for(account)
            if not (rules.day_take or rules.target_take):
                continue
            book = self.book(account)
            live = [s for s in self.day_states_for_account(account)
                    if s.status == "live" and s.entry_side and s.entry_fill is not None]
            total, known = 0.0, bool(live)
            for s in live:
                cfg = self.cfg.strategies.get(s.strategy)
                px = prices.get(cfg.symbol) if cfg is not None else None
                if px is None:
                    known = False
                    break
                total += self._open_net(s, cfg, float(px))
            if not (known and book.take_hit(total, rules)):
                self._take_seen.pop(account, None)
                continue
            first = self._take_seen.setdefault(account, now)
            if now - first < TAKE_GRACE_S:
                continue
            self._take_seen.pop(account, None)
            ad = self.adapters.get(account)
            if ad is None:
                continue
            acts: dict = {}
            booked = 0.0
            sold: set = set()           # _flatten_state sells the account's WHOLE net in the symbol: once per symbol
            for s in sorted(self.day_states_for_account(account), key=lambda x: x.status != "live"):
                cfg = self.cfg.strategies.get(s.strategy)
                if cfg is None or s.status not in ("placed", "live"):
                    continue
                was_live = s.status == "live" and s.entry_fill is not None
                if cfg.symbol in sold:  # the market-out is already sent: this run only has orders to cancel
                    flat, acts[s.strategy] = await self._cancel_state_orders(s, ad)
                else:
                    flat, acts[s.strategy] = await self._flatten_state(s, cfg, ad)
                    if flat:
                        sold.add(cfg.symbol)
                if flat:
                    if was_live:               # the market-out's fill arrives after the state is done
                        px = prices.get(cfg.symbol)
                        s.exit_fill = px
                        s.pnl = self._gross_pnl(s, cfg)
                        booked += self._open_net(s, cfg, float(px))
                        book.closes += 1
                    s.exit_reason, s.status = "day_take", "done"
            book.closed_net = round(book.closed_net + booked, 2)
            book.locked = book.locked or LOCK_TAKE
            self._save()
            self._save_books()
            self.journal("day_take_flatten", account=account, open_net=round(total, 2),
                         closed_net=book.closed_net, take=book.take_net(rules), actions=acts)
            out.append({"account": account, "open_net": total, "actions": acts})
        return out

    async def each_account(self, accounts, fn) -> tuple[dict, dict]:
        """fn(account) for every account, the accounts side by side (asyncio.gather) instead of one
        after another: the Kill, the clock and the strategy flatten. At most EXIT_CONCURRENCY at
        once. Desk entries that trade ONE broker account (adapter.broker_key) share a turn, in the
        order given: each reads that account's net and sells all of it, so they must never read it
        together. One account's raise never stops or cancels another's.
        -> ({account: fn's result, or the exception it raised}, {account: ms it took -- timing only})"""
        turns: dict = {}
        for a in accounts:
            turns.setdefault(getattr(self.adapters.get(a), "broker_key", a), []).append(a)
        gate = asyncio.Semaphore(EXIT_CONCURRENCY)
        out: dict = {}
        took: dict = {}

        async def turn(group: list) -> None:
            async with gate:
                for a in group:
                    t = self._perf()
                    try:
                        out[a] = await fn(a)
                    except Exception as e:  # noqa: BLE001 — this account failed; the others still run
                        out[a] = e
                    took[a] = round((self._perf() - t) * 1000, 1)

        ends = await asyncio.gather(*(turn(g) for g in turns.values()), return_exceptions=True)
        lost = {a: e for g, e in zip(turns.values(), ends) if isinstance(e, BaseException) for a in g}
        return {a: out.get(a, lost.get(a)) for a in accounts}, {a: took.get(a) for a in accounts}

    async def flatten_strategy(self, name: str) -> dict:
        """Manual flatten for ONE strategy on every account it acted on today
        (see _flatten_state), the accounts side by side (each_account).
        Symbol-scoped per account: another strategy holding the same symbol
        on the same account would be flattened too."""
        cfg = self.cfg.strategies.get(name)
        states = {st.account: st for st in self.day_states(name)}

        async def account(a: str) -> Optional[list]:
            st = states[a]
            ad = self.adapters.get(st.account)
            if ad is None or cfg is None or st.status == "idle":
                return None
            flat, acts = await self._flatten_state(st, cfg, ad)
            if flat and st.status in ("placing", "placed", "live"):
                st.status, st.exit_reason = "done", "manual_flat"
            return acts

        t0 = self._perf()
        got, took = await self.each_account(states, account)
        results = {a: (g if isinstance(g, list) else [f"internal error: {type(g).__name__}: {g}"])
                   for a, g in got.items() if g is not None}
        self._save()
        self.journal("manual_flatten", strategy=name, results=results,
                     # timing only: the whole flatten, and each account's own part of it
                     flatten_ms={"total": round((self._perf() - t0) * 1000, 1),
                                 "accounts": {a: took[a] for a in results}})
        return results

    async def flatten_today(self) -> dict:
        """Kill switch: every strategy's footprint today, proven calls only. The
        accounts go side by side (each_account); one account's runs go one after
        another, in today's order -- _flatten_state sells the account's WHOLE net
        in a symbol. A run that raises is reported in its own actions; every
        other run still goes."""
        states = list(self.states.values())
        by_account: dict[str, list[DayState]] = {}
        for st in states:
            by_account.setdefault(st.account, []).append(st)

        async def account(a: str) -> dict:
            acts: dict = {}
            for st in by_account[a]:
                key = f"{st.strategy}@{st.account}"
                try:
                    cfg = self.cfg.strategies.get(st.strategy)
                    ad = self.adapters.get(st.account)
                    if cfg is None or ad is None or st.date != self._today() \
                            or st.status == "idle":
                        continue
                    flat, acts[key] = await self._flatten_state(st, cfg, ad)
                    if flat and st.status in ("placing", "placed", "live"):
                        st.status, st.exit_reason = "done", "killed"
                except Exception as e:  # noqa: BLE001 — the Kill always finishes
                    acts[key] = [f"internal error: {type(e).__name__}: {e}"]
            return acts

        got, _ = await self.each_account(by_account, account)
        done = {k: v for g in got.values() if isinstance(g, dict) for k, v in g.items()}
        out = {k: done[k] for k in (f"{st.strategy}@{st.account}" for st in states) if k in done}
        self._save()
        return out

    def _kill_lock(self, name: str) -> asyncio.Lock:
        """One kill per strategy at a time: a second kill (another chart, a
        re-click) waits, then finds the run killed and does nothing."""
        loop = asyncio.get_running_loop()
        held = self._kill_locks.get(name)
        if held is None or held[0] is not loop:
            held = self._kill_locks[name] = (loop, asyncio.Lock())
        return held[1]

    @contextlib.asynccontextmanager
    async def all_kill_locks(self):
        """Every strategy's kill lock, taken in a fixed (sorted) order -- the
        desk's global Kill holds them all while it flattens, so it never runs
        alongside a per-strategy Kill (both read the net and market-sell). A
        per-strategy Kill holds only its own, so the fixed order cannot deadlock."""
        async with contextlib.AsyncExitStack() as stack:
            for name in sorted(self.cfg.strategies):
                await stack.enter_async_context(self._kill_lock(name))
            yield

    async def kill_strategy(self, name: str, **journal_extra) -> dict:
        """The per-strategy Kill. Marks `name` killed for today FIRST (no
        alert, signal or timer fire places it again today) and journals
        `strategy_kill_requested` (a restart honours it), then, under the
        strategy's own lock, per account -- its booked accounts plus any
        account it acted on today -- and nothing else:
          idle        nothing to do (never flatten a position the bot did not open)
          placing     the acks are outstanding: _place finishes the kill once
                      they land (_kill_after_ack)
          placed / live / both-filled error   _kill_state: never more than
                      the bot's own filled quantity, only on its side
          done (killed already)   nothing
          done, or a failed placement   cancel its own orders still
                      working; no market order
        Never the account-wide cancel_all / flatten_all, never another
        strategy's orders, never the desk's arm or chart trading. Journals
        `strategy_killed` with every account's result. {account: result};
        "acted": True marks an account where the kill ended a running run."""
        cfg = self.cfg.strategies[name]
        self.kill_today(name)
        try:
            self.journal("strategy_kill_requested", strategy=name, **journal_extra)
        except Exception as e:  # noqa: BLE001 — the kill goes on; it is marked in memory
            print(f"homebase engine: journal strategy_kill_requested failed: {e!r}", file=sys.stderr)
        async with self._kill_lock(name):
            states = {st.account: st for st in self.day_states(name)}    # read INSIDE the lock
            accounts = list(dict.fromkeys([a["account"] for a in assignments(self.cfg, name)]
                                          + list(states)))
            outs = await asyncio.gather(*(self._kill_one(cfg, a, states.get(a)) for a in accounts),
                                        return_exceptions=True)
            results = {a: (o if isinstance(o, dict) else
                           {"ok": False, "error": f"internal error: {type(o).__name__}: {o}",
                            "actions": []})
                       for a, o in zip(accounts, outs)}
            self._save()
            self.journal("strategy_killed", strategy=name, results=results, **journal_extra)
        return results

    async def _kill_one(self, cfg: StrategyCfg, account: str,
                        st: Optional[DayState]) -> dict:
        if st is None or st.status == "idle":
            return {"ok": True, "note": "the bot has not acted on this account today — nothing to do"}
        if st.status == "done" and st.exit_reason == "killed":
            return {"ok": True, "note": "already killed — nothing to do"}
        ad = self.adapters.get(account)
        if ad is None:
            return {"ok": False, "error": "account not connected", "actions": []}
        if st.status == "placing":
            return {"ok": True, "acted": True, "pending": True,
                    "note": "its orders are not acknowledged yet — they are cancelled and its "
                            "position flattened as soon as they are"}
        if st.status == "done" or (st.status == "error" and st.exit_reason != "both_filled"):
            # flat already (or it never got in: a failed placement) -- a position
            # here now is not the bot's; only its own leftover orders are cancelled
            acts, ok = [], True
            for i in (st.upper_id, st.lower_id, st.up_sl_id, st.up_tp_id, st.dn_sl_id, st.dn_tp_id):
                if not i:
                    continue
                try:
                    status = await ad.get_order_status(i)
                except Exception as e:  # noqa: BLE001
                    status, ok = None, False
                    acts.append(f"order {i}: status unreadable ({e}) — check it")
                    continue
                if status in WORKING:
                    r = await ad.cancel_order_by_id(i)
                    ok = ok and r.ok
                    acts.append(f"cancel {i}: " + ("ok" if r.ok else str(r.error)))
                elif status is None:
                    ok = False
                    acts.append(f"order {i}: status unknown — check it")
            return {"ok": ok, "actions": acts}
        res = await self._kill_state(st, cfg, ad)
        return {"ok": res["ok"], "acted": True, "actions": res["actions"]}

    @staticmethod
    def _killable(st: DayState) -> bool:
        """A run the kill may still act on: placed or live, or a both-filled
        error. Done (killed or not), idle and placing are never acted on here."""
        return st.status in ("placed", "live") or \
            (st.status == "error" and st.exit_reason == "both_filled")

    async def _entry_states(self, ad: BrokerAdapter, ids: list) -> dict:
        """After the entry cancels: each entry's (status, filled_qty), re-read
        every KILL_POLL_S up to KILL_POLL_N times (3 s) until every entry is
        terminal (Filled / Canceled / Rejected / Expired). A cancel "ok" only
        means the broker accepted the command: the order can still fill."""
        out: dict = {}
        for attempt in range(KILL_POLL_N + 1):
            for i in ids:
                if i in out and out[i][0] in TERMINAL:
                    continue
                try:
                    got = await ad.get_order_state(i) or {}
                except Exception:  # noqa: BLE001 — unknown, polled again
                    got = {}
                out[i] = (got.get("status"), got.get("filled_qty"))
            if all(out[i][0] in TERMINAL for i in ids) or attempt == KILL_POLL_N:
                break
            await self._kill_sleep(KILL_POLL_S)
        return out

    def _kill_check(self, st: DayState, acts: list, why: str) -> dict:
        """When in doubt: nothing (more) sold, the bot's stop/target left
        working, and it says so -- journaled."""
        acts.append(f"check it — {why}; position not fully attributed; stops left working")
        try:
            self.journal("strategy_kill_check", strategy=st.strategy, account=st.account,
                         reason=why, actions=acts)
        except Exception as e:  # noqa: BLE001
            print(f"homebase engine: journal strategy_kill_check failed: {e!r}", file=sys.stderr)
        return {"ok": False, "sold": False, "actions": acts}

    async def _cancel_brackets(self, st: DayState, ad: BrokerAdapter, acts: list) -> None:
        ids = [i for i in (st.up_sl_id, st.up_tp_id, st.dn_sl_id, st.dn_tp_id) if i]
        res = await asyncio.gather(*(ad.cancel_order_by_id(i) for i in ids), return_exceptions=True)
        for i, r in zip(ids, res):
            ok = not isinstance(r, Exception) and r.ok
            acts.append(f"cancel {i}: " + ("ok" if ok else
                        str(r if isinstance(r, Exception) else r.error)))

    async def _kill_state(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter) -> dict:
        """The per-strategy kill's own flatten (the global Kill keeps
        _flatten_state, unchanged). Called under the strategy's kill lock.
        When in doubt it leaves the bot's stop/target working and says "check
        it"; it never removes protection from a position it cannot fully
        attribute, and never sells twice (a run it sold is done/killed, and a
        run that is not placed/live/both-filled is left alone).
          1. cancel both entries;
          2. wait (3 s max) for each entry to be terminal. Filled -> the bot
             holds st.qty on that side (never entry_qty: it can be stale);
             Canceled/Rejected with a fill -> partial, unsure; not terminal ->
             unsure. Unsure -> check it;
          3. both entries filled -> the both-filled path (never sells);
          4. read the account's net: unreadable -> check it. The bot holds
             nothing but the account does -> check it. The net on the other
             side -> check it. Flat -> cancel the (dead) stop/target;
          5. market out min(net on the bot's side, the bot's qty); then the run
             is done/killed and its stop/target are cancelled.
        -> {ok, sold, actions}"""
        acts: list[str] = []
        if not self._killable(st):
            return {"ok": True, "sold": False, "actions": ["already killed — nothing to do"]}
        if st.status == "error":
            return await self._kill_both_filled(st, cfg, ad, acts)
        entries = [(i, sign) for i, sign in ((st.upper_id, 1), (st.lower_id, -1)) if i]
        res = await asyncio.gather(*(ad.cancel_order_by_id(i) for i, _ in entries),
                                   return_exceptions=True)
        for (i, _), r in zip(entries, res):
            ok = not isinstance(r, Exception) and r.ok
            acts.append(f"cancel entry {i}: " + ("ok" if ok else
                        str(r if isinstance(r, Exception) else r.error)))
        states = await self._entry_states(ad, [i for i, _ in entries])
        # the poll yielded (250 ms sleeps): the run may have moved on by itself
        if st.status == "error" and st.exit_reason == "both_filled":
            return await self._kill_both_filled(st, cfg, ad, acts)
        if not self._killable(st):
            return self._kill_check(st, acts, f"the run ended on its own ({st.exit_reason}) "
                                              "during the kill")
        held, unsure = {1: 0, -1: 0}, []
        for i, sign in entries:
            status, filled = states[i]
            if status == "Filled":
                held[sign] += int(st.qty or 0)
            elif status in TERMINAL:
                if filled:
                    unsure.append(f"entry {i} {status.lower()} after {filled} filled")
            else:
                unsure.append(f"entry {i} not cancelled or filled ({status or 'status unknown'})")
        if unsure:
            return self._kill_check(st, acts, "; ".join(unsure))
        if held[1] and held[-1]:
            return await self._kill_both_filled(st, cfg, ad, acts)
        bot = held[1] - held[-1]
        try:
            net = int(await ad.get_net_position(cfg.symbol) or 0)
        except Exception as e:  # noqa: BLE001 — unreadable is NOT flat
            return self._kill_check(st, acts, f"position unreadable ({e})")
        if not bot and net:
            return self._kill_check(st, acts, f"the bot holds nothing here but the account holds "
                                              f"{net:+d} {cfg.symbol}")
        if bot and net and (net > 0) != (bot > 0):
            return self._kill_check(st, acts, f"the account's {net:+d} {cfg.symbol} is not on the "
                                              f"bot's side ({bot:+d})")
        # the position read yielded too: the run is re-checked right before any sale
        if st.status == "error" and st.exit_reason == "both_filled":
            return await self._kill_both_filled(st, cfg, ad, acts)
        if not self._killable(st):
            return self._kill_check(st, acts, f"the run ended on its own ({st.exit_reason}) "
                                              "during the kill")
        sold = False
        if bot and net:
            qty, side = min(abs(net), abs(bot)), ("Sell" if net > 0 else "Buy")
            r = await ad.place_order(OrderRequest(symbol=cfg.symbol, side=side, qty=qty,
                                                  order_type="Market", text="homebase:kill"))
            acts.append(f"market {side} {qty}: {'ok' if r.ok else r.error}")
            if not r.ok:
                # it may have gone out anyway: never send it again -- the run is
                # killed, its stop/target stay working, a human verifies
                st.status, st.exit_reason = "done", "killed"
                st.note = MARKET_OUT_FAILED
                self._save()
                return self._kill_check(st, acts, "market-out reported failure; verify the position")
            sold = True
        elif bot:
            acts.append("the account is already flat")
        st.status, st.exit_reason = "done", "killed"        # never acted on again
        self._save()
        if bot and abs(bot) != int(st.qty or 0):
            return {**self._kill_check(st, acts, f"sold for {abs(bot)} of the bot's {st.qty}"),
                    "sold": sold}
        await self._cancel_brackets(st, ad, acts)
        return {"ok": True, "sold": sold, "actions": acts}

    async def _kill_both_filled(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter,
                                acts: list) -> dict:
        """Both entries filled: the engine's both-filled emergency owns the
        flatten. The kill never sells here; it cancels the stop/target only
        once the account is flat in the bot's symbol."""
        try:
            net = int(await ad.get_net_position(cfg.symbol) or 0)
        except Exception as e:  # noqa: BLE001
            return self._kill_check(st, acts, f"both entries filled; position unreadable ({e})")
        if net:
            return self._kill_check(st, acts, f"both entries filled and the account still holds "
                                              f"{net:+d} {cfg.symbol}")
        await self._cancel_brackets(st, ad, acts)
        return {"ok": True, "sold": False, "actions": acts}

    async def _kill_after_ack(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter) -> None:
        """A kill that landed while this run was placing, finished now, under
        the kill lock -- and only if the run is still one to act on (another
        kill may have finished it meanwhile). Never raises into _place: the
        placement stands as placed either way."""
        try:
            async with self._kill_lock(st.strategy):
                res = await self._kill_state(st, cfg, ad)
                self._save()
                self.journal("strategy_killed_after_ack", strategy=st.strategy, account=st.account,
                             ok=res["ok"], actions=res["actions"])
        except Exception as e:  # noqa: BLE001
            try:
                self.journal("strategy_kill_failed", strategy=st.strategy, account=st.account,
                             error=f"{type(e).__name__}: {e}"[:300])
            except Exception as e2:  # noqa: BLE001
                print(f"homebase engine: kill after ack failed ({e!r}); journal failed ({e2!r})",
                      file=sys.stderr)

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
