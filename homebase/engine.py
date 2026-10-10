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
# Right after an entry fill the other entry is watched closely (sibling_tick): for SIBLING_WATCH_S its
# cancel is sent again every SIBLING_FAST_S while the broker still reads it as working.
SIBLING_FAST_S, SIBLING_WATCH_S = 0.5, 3.0
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
    exit_qty: int = 0                  # contracts out again so far (exit fills)
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
        self._sib_watch: dict[str, float] = {}  # "strategy@account" -> its entry fill, while sibling_tick watches
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
                     sl_pts: float | None = None, sl_sell_pts: float | None = None,
                     reqs: tuple[OrderRequest, OrderRequest] | None = None) -> dict:
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
                    and ev.side != st.entry_side:
                # an exit can come in pieces, and before the whole entry is in (gc_nfp 2026-10-02:
                # 1 contract in, 1 out, then the other 3): keep the AVERAGE exit and stay live
                # until every contract that went in is out again (_close_if_out)
                q = int(ev.qty or 0) or max(st.entry_qty - st.exit_qty, 1)
                if ev.price is not None:
                    st.exit_fill = (ev.price if st.exit_fill is None or not st.exit_qty else
                                    (st.exit_fill * st.exit_qty + ev.price * q) / (st.exit_qty + q))
                st.exit_qty += q
                if not await self._close_if_out(st, cfg, ad):
                    self._save()
                    self.journal("exit_part", strategy=st.strategy, account=st.account,
                                 fill=ev.price, qty=q, out=st.exit_qty, entered=st.entry_qty)
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
        if cfg is not None and cfg.kind == "lab":
            return await self._lab_flatten_strategy(name)
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
                            or st.status == "idle" or self._archived(st) \
                            or (cfg.kind == "lab" and self._lab_close_sent(st)):
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
        if cfg.kind == "lab" and st is not None and self._lab_hands_off(st):
            return await self._lab_kill_readonly(st, cfg, account)
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

    # ==================================================================================================
    # THE LAB SECTION (Step B, task B2): several trades a day, for kind "lab" ONLY.
    #
    # A promoted Lab strategy trades in ROUNDS. The open round of a (strategy, account) pair keeps the
    # plain key "strategy@account", so everything above works on it unchanged; a round that is over AND
    # clean is archived under "strategy@account#n" and never acted on again. Eight hooks above reach
    # this section, each only for cfg.kind == "lab" (or, for _archived, a state the plain key no longer
    # holds -- never true of another kind's state). Nothing here is reached by a straddle, bars or
    # levels strategy.
    #
    #   I-1  one open round per pair, at the plain key
    #   I-2  a new round only when the last one is terminal AND clean: every order id it placed reads
    #        terminal at the broker. Otherwise no new entry on that account, and it says so
    #   I-3  the open (or last) round is the last-inserted state of its pair
    #   I-4  an archived round is never acted on again
    #
    # What a round needs beyond its DayState (the strategy's own order ids, its legs, how it is being
    # closed, whether its orders were checked) lives in self._lab, saved to labday-<date>.json beside
    # the day file. It is read at the first Lab call, never at construction: a missing or unreadable
    # file cannot stop the desk from starting, and a round whose extras are lost is never clean.
    # ==================================================================================================
    def _archived(self, st: DayState) -> bool:
        """A closed Lab round filed under "strategy@account#n". False for every state the plain key holds --
        so for every state of every other kind."""
        return self.states.get(f"{st.strategy}@{st.account}") is not st

    # --- the extras ---------------------------------------------------------------------------------
    def _lab_path(self):
        return self._root / f"labday-{self._today()}.json"

    def _lab_mem(self) -> dict:
        """{state key: extras}, read from today's file at the first Lab call. Never raises."""
        mem = self.__dict__.get("_lab")
        if mem is None:
            mem = {}
            try:
                p = self._lab_path()
                if p.exists():
                    data = json.loads(p.read_text())
                    if isinstance(data, dict):
                        mem = {str(k): v for k, v in data.items() if isinstance(v, dict)}
                        for k, v in mem.items():
                            self._lab_coerce(v, carried_key="#c" in k)
            except Exception as e:  # noqa: BLE001 -- lost extras mean "not clean", never a crash
                print(f"homebase engine: reading the Lab rounds file failed: {e!r}", file=sys.stderr)
            self._lab = mem
        return mem

    @staticmethod
    def _lab_coerce(x: dict, carried_key: bool = False) -> None:
        """A file is only text: every value the section leans on is given its type back, and a number must be
        finite. One that is wrong takes the safe value AND makes the round not clean (never an exception on every
        tick). The safe value of "this round's close was sent" is YES: a mark that does not read, that is not a
        time, or that is missing beside a closing reason / an unconfirmed marker / the older key (closing_ms)
        means a close MAY be out, and no second one is ever sent."""
        inf = float("inf")

        def num(v) -> bool:
            return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != inf

        def whole(v) -> bool:
            return isinstance(v, int) and not isinstance(v, bool)

        bad = False
        if any(k not in x for k in ("round", "iid", "legs", "cancelled", "clean", "closing", "placed_ms")):
            # not a round's extras at all (every build wrote these keys): this trade's record is LOST (hands off)
            x["lost"], bad = True, True
        for k, typ in (("cancelled", list), ("legs", dict), ("iid", dict)):
            if k in x and not isinstance(x[k], typ):
                x[k], bad = typ(), True
        if any(v not in ("Buy", "Sell") for v in x.get("cancelled") or []):
            x["cancelled"], bad = [v for v in x["cancelled"] if v in ("Buy", "Sell")], True
        # O-1: what a file says was cancelled is a hint. `cancelled` holds only what THIS process read at the
        # broker; every path that skips an "already cancelled" entry therefore asks the broker again after a start
        hint = x.get("cancelled_hint") if isinstance(x.get("cancelled_hint"), list) else []
        x["cancelled_hint"] = sorted({v for v in list(x.get("cancelled") or []) + hint if v in ("Buy", "Sell")})
        x["cancelled"] = []
        if any(not isinstance(v, dict) for v in (x.get("legs") or {}).values()):
            x["legs"], bad = {k: v for k, v in x["legs"].items() if isinstance(v, dict)}, True
        for leg in (x.get("legs") or {}).values():
            for k in ("entry_price", "sl_px", "tp_px", "tp_rr", "ref_px"):
                if leg.get(k) is not None and not num(leg[k]):
                    leg[k], bad = None, True
            if "move" in leg and not isinstance(leg["move"], bool):
                leg["move"], bad = False, True
        if any(not whole(v) for v in (x.get("iid") or {}).values()):
            x["iid"], bad = {k: v for k, v in x["iid"].items() if whole(v)}, True
        if "round" in x and not whole(x["round"]):
            x["round"], bad = None, True
        for k in ("placed_ms", "entry_ms", "exit_ms"):
            if x.get(k) is not None and not num(x[k]):
                x[k], bad = None, True
        for k in ("clean", "check", "unconfirmed", "close_ok", "blind", "move", "lost", "lost_said"):
            if k in x and not isinstance(x[k], bool):
                x[k], bad = k not in ("clean", "move", "lost_said"), True
        if "net_bad" in x and not (whole(x["net_bad"]) and x["net_bad"] >= 0):
            x["net_bad"], bad = 0, True
        if x.get("net_bad_ms") is not None and not num(x["net_bad_ms"]):
            x["net_bad_ms"], bad = None, True
        if "closing_ms" in x:                        # the key of the first build of this section
            old = x.pop("closing_ms")
            if x.get("close_sent_ms") is None:
                x["close_sent_ms"] = old
        if x.get("closing") is not None and not isinstance(x["closing"], str):
            x["closing"] = str(x["closing"])
        sent = x.get("close_sent_ms")
        hint = bool(x.get("closing") or x.get("unconfirmed") or x.get("close_ok") or x.get("close_id"))
        if num(sent) and sent > 0:
            pass
        elif hint or (sent is not None and not (num(sent) and sent <= 0)):
            x["close_sent_ms"], bad = 1, True        # it may have been sent: never a second one
            if not x.get("close_ok"):
                x["unconfirmed"] = True
        elif sent is not None:
            x["close_sent_ms"], bad = None, True     # a zero with nothing that says a close was ever asked for
        if x.get("gone_ms") is not None and not (num(x["gone_ms"]) and x["gone_ms"] > 0):
            x["gone_ms"], bad = 1, True
        if x.get("carry") is not None and not isinstance(x["carry"], dict):
            # under a block's own key it stays a block; on a round of today it is no block (the round is its own)
            x["carry"], bad = ({"date": None, "status": None, "orders": []} if carried_key else None), True
        elif isinstance(x.get("carry"), dict):
            c = x["carry"]
            if not (isinstance(c.get("orders"), list) and all(isinstance(i, str) for i in c["orders"])):
                c["orders"] = [i for i in c["orders"] if isinstance(i, str)] if isinstance(c.get("orders"), list) else []
                c["unread"], bad = True, True        # its orders cannot all be named: cleared by hand only
            for k in ("sides", "was"):
                if not isinstance(c.get(k), dict):
                    c[k] = {}
            if c.get("filled") is not None and not isinstance(c["filled"], list):
                c["filled"] = None
            if not isinstance(c.get("date"), str):
                c["date"], c["unread"], bad = None, True, True
        if x.get("why") is not None and not isinstance(x["why"], str):
            x["why"] = None
        if x.get("close_id") is not None and not isinstance(x["close_id"], str):
            x["close_id"] = str(x["close_id"])
        if bad:
            x["check"], x["clean"], x["why"] = True, False, LAB_CANNOT_CHECK

    def _lab_save(self, strict: bool = False) -> None:
        """Write the extras whole (a temp file, then a rename). strict: raise when it cannot be written (a new
        round must be on disk before its order leaves); otherwise say so on stderr and go on."""
        try:
            p = self._lab_path()
            tmp = p.with_name(p.name + ".tmp")
            tmp.write_text(json.dumps(self._lab_mem(), indent=2) + "\n")
            tmp.replace(p)
        except Exception as e:  # noqa: BLE001
            if strict:
                raise
            print(f"homebase engine: writing the Lab rounds file failed: {e!r}", file=sys.stderr)

    def _lab_ms(self) -> int:
        return int(self._now().timestamp() * 1000)

    def _lab_key(self, st: DayState) -> Optional[str]:
        key = f"{st.strategy}@{st.account}"
        if self.states.get(key) is st:
            return key
        return next((k for k, s in self.states.items() if s is st), None)

    @staticmethod
    def _lab_blank(n: int) -> dict:
        # close_sent_ms: THE fact that this round's one market-out was sent (written to disk before it leaves;
        # never judged by `closing`, which is only the reason text). close_ok / close_id: the broker accepted it.
        return {"round": n, "iid": {}, "legs": {}, "move": False, "closing": None, "close_sent_ms": None,
                "close_ok": False, "close_id": None, "gone_ms": None, "cancelled": [], "clean": False,
                "check": False, "unconfirmed": False, "blind": False, "carry": None,
                "lost": False, "lost_said": False, "net_bad": 0, "net_bad_ms": None,
                # sides a FILE said were cancelled: a hint, never a fact, until the broker is read (_lab_hints)
                "cancelled_hint": [],
                "placed_ms": None, "entry_ms": None, "exit_ms": None, "why": None}

    def _lab_round_no(self, st: DayState) -> int:
        """A round's number when its extras do not say: an archived one from its key, the open one after them."""
        key = self._lab_key(st) or ""
        tail = key.rsplit("#", 1)[-1] if "#" in key else ""
        if self._archived(st) and tail.isdigit():
            return int(tail)
        return 1 + sum(1 for s in self.states.values()
                       if s is not st and s.strategy == st.strategy and s.account == st.account
                       and s.date == st.date and self._archived(s))

    def _lab_x(self, st: DayState) -> dict:
        """The round's extras. A round that acted and has none (the file was lost) gets a blank set that can
        never be clean: its orders cannot be checked."""
        mem = self._lab_mem()
        key = self._lab_key(st)
        x = mem.get(key) if key is not None else None
        if x is None:
            x = self._lab_blank(self._lab_round_no(st))
            if st.status != "idle":
                x["check"], x["why"], x["lost"] = True, LAB_CANNOT_CHECK, True
            if key is not None:
                mem[key] = x
        for k, v in self._lab_blank(0).items():          # a file written by an older build: fill what it lacks
            if k not in x:
                x[k] = v
        if x.get("round") is None:
            x["round"] = self._lab_round_no(st)
        if x.get("lost") and not x.get("lost_said"):
            # This trade's record was lost (its extras are missing or do not read). The Desk stops owning what it
            # cannot account for: from here the Lab section sends nothing and cancels nothing for it, in any
            # status; it is never clean, and it is carried as a block at the day roll. Said once.
            x["lost_said"], x["check"], x["clean"], x["why"] = True, True, False, LAB_CANNOT_CHECK
            try:
                self.journal("lab_check", strategy=st.strategy, account=st.account, round=x.get("round"),
                             reason="this trade's record was lost: nothing is sent or cancelled for it by the "
                                    "strategy's own controls; the desk-wide Kill still works", actions=[])
                self._lab_save()
            except Exception as e:  # noqa: BLE001 -- never out of a read
                print(f"homebase engine: journal lab_check failed: {e!r}", file=sys.stderr)
        return x

    def _lab_stamp(self, st: DayState, x: dict) -> bool:
        """When the entry and the exit were first seen here (there is no hook inside on_fill). True = changed."""
        changed = False
        if st.entry_side and not x.get("entry_ms"):
            x["entry_ms"], changed = self._lab_ms(), True
        if st.status in ("done", "error") and not x.get("exit_ms"):
            x["exit_ms"], changed = self._lab_ms(), True
        return changed

    def _lab_levels(self, st: DayState, x: dict) -> tuple:
        """(stop, target) of the round's trade: the state's own, else the filled leg's as it was sent."""
        leg = (x.get("legs") or {}).get(st.entry_side or "") or {}
        return (st.sl_px if st.sl_px is not None else leg.get("sl_px"),
                st.tp_px if st.tp_px is not None else leg.get("tp_px"))

    # --- hook 3: the brackets after the fill (the tester's law, backtest/engine.py _fill) ---------
    async def _lab_move(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter) -> dict:
        """With `move` and a ref the stop shifts by fill - ref, and so does a target that has no RR; with an RR
        the target is fill +/- rr x |fill - stop| (the moved stop). Only an order whose price changed by half a
        tick or more, and whose id is known, is modified. st.sl_px / st.tp_px end as the levels that REST at the
        broker. Never raises (on_fill journals what it returns as `brackets_moved`), and always returns both
        `sl` and `tp` (metrics reads them together)."""
        st.brackets_moved = True                  # once per trade
        out = {"fill": None, "sl": st.sl_px, "tp": st.tp_px, "moved": False}
        if self._archived(st):                    # a block carried from an earlier day: read only, always
            return {**out, "error": "a carried round: nothing is moved"}
        try:
            x = self._lab_x(st)
            if x.get("lost"):                     # hands off: its stop and target stay where the broker has them
                return {**out, "error": "this trade's record was lost: nothing is moved"}
            leg = (x.get("legs") or {}).get(st.entry_side or "") or {}
            sl0, tp0 = self._lab_levels(st, x)
            rr = leg.get("tp_rr") if leg else st.tp_rr
            st.sl_px, st.tp_px, st.tp_rr = sl0, tp0, rr
            out.update(sl=sl0, tp=tp0)
            if self._lab_stamp(st, x):
                self._lab_save()
            if st.entry_fill is None:
                self._save()
                return {**out, "error": "no fill price"}
            fill = float(st.entry_fill)
            out["fill"] = round(fill, 6)
            sign = 1 if st.entry_side == "Buy" else -1
            tick = tick_size(cfg.symbol) or 0.25
            sl, tp = sl0, tp0
            if leg.get("move") and leg.get("ref_px") is not None:
                d = fill - float(leg["ref_px"])
                sl = None if sl is None else _to_tick(sl + d, tick)
                if rr is None:
                    tp = None if tp is None else _to_tick(tp + d, tick)
            if rr is not None and sl is not None:
                tp = _to_tick(fill + sign * float(rr) * abs(fill - sl), tick)
            sl_id, tp_id = ((st.up_sl_id, st.up_tp_id) if st.entry_side == "Buy"
                            else (st.dn_sl_id, st.dn_tp_id))
            jobs, errs = [], []
            for name, new, old, oid in (("sl", sl, sl0, sl_id), ("tp", tp, tp0, tp_id)):
                if new is None or (old is not None and abs(new - old) < tick / 2):
                    continue
                if not oid:
                    errs.append(f"{name}: order id unknown")
                    continue
                jobs.append((name, new, ad.modify_order(oid, "Stop", stop_price=new, qty=st.qty) if name == "sl"
                             else ad.modify_order(oid, "Limit", price=new, qty=st.qty)))
            if not jobs and not errs:
                self._save()
                return {**out, "moved": "not needed — levels unchanged"}
            res = await asyncio.gather(*(j[2] for j in jobs), return_exceptions=True)
            for (name, new, _), r in zip(jobs, res):
                if not isinstance(r, Exception) and r.ok:
                    setattr(st, f"{name}_px", new)
                else:
                    errs.append(f"{name}: {r if isinstance(r, Exception) else r.error}")
            self._save()
            return {**out, "sl": st.sl_px, "tp": st.tp_px, "moved": not errs,
                    **({"error": "; ".join(errs)} if errs else {})}
        except Exception as e:  # noqa: BLE001 -- the fill is already in; the brackets rest where they were
            return {**out, "error": f"{type(e).__name__}: {e}"[:200]}

    # --- hook 4: why the trade ended ------------------------------------------------------------------
    def _lab_grade(self, st: DayState, px: Optional[float]) -> str:
        """The reason the round is being closed for (a flatten) when there is one; else "sl" or "tp" by the
        nearer level that exists; else "exit". Never raises: it runs inside on_fill."""
        try:
            x = self._lab_x(st)
            if not x.get("exit_ms"):
                x["exit_ms"] = self._lab_ms()
            self._lab_save()                      # an unconfirmed close stays unconfirmed: only the settle, with
                                                  # the orders AND the net read, may call this round clean
            if x.get("close_sent_ms") and x.get("closing"):
                return str(x["closing"])          # (a close that only MAY be out has no reason: graded by level)
            sl, tp = self._lab_levels(st, x)
            if px is None or (sl is None and tp is None):
                return "exit"
            if sl is None or tp is None:
                return "sl" if tp is None else "tp"
            return "tp" if abs(px - tp) <= abs(px - sl) else "sl"
        except Exception as e:  # noqa: BLE001
            print(f"homebase engine: grading a Lab exit failed: {e!r}", file=sys.stderr)
            return "exit"

    # --- the rounds: what the Desk reads -----------------------------------------------------------
    def _lab_roll(self) -> None:
        """The first Lab call of a day, and the first after a start: yesterday's Lab rounds leave the day. One
        that is NOT resolved (placing / placed / live, or its orders never read ended) is carried as a block
        for its (strategy, account): see _lab_carry. Never raises."""
        today = self._today()
        names = frozenset(n for n, c in self.cfg.strategies.items()
                          if isinstance(n, str) and getattr(c, "kind", None) == LAB)
        seen = self.__dict__.get("_lab_names")
        if self.__dict__.get("_lab_day") == today and seen is not None and names <= seen:
            return
        # N-1: a Lab strategy that was not in the config at the roll (its record did not read at that moment)
        # was left completely alone. When it is there again, the roll runs once more, for it only.
        only = None if self.__dict__.get("_lab_day") != today or seen is None else names - seen
        self._lab_day, self._lab_names = today, (names if only is None else seen | names)
        try:
            self._lab_roll_day(today, only)
        except Exception as e:  # noqa: BLE001 -- the position read in front of every entry still stands
            print(f"homebase engine: the Lab day roll failed: {e!r}", file=sys.stderr)

    @staticmethod
    def _lab_unresolved(rec: dict, x) -> bool:
        """A round (its state as a dict, its extras) that an account may not trade past."""
        if isinstance(x, dict) and isinstance(x.get("carry"), dict):
            return True                               # a block that never cleared
        status = rec.get("status")
        if status in ("placing", "placed", "live"):
            return True
        if status in (None, "idle"):
            return False
        return not (isinstance(x, dict) and x.get("clean") is True and not x.get("check")
                    and not x.get("unconfirmed"))

    def _lab_last_files(self, today: str) -> tuple:
        """(date, extras, states) of the most recent earlier day that has a Lab file, at most 7 days back. A file
        that is missing or does not read carries nothing: (None, {}, {})."""
        try:
            now, best = dt.date.fromisoformat(today), None
            for f in self._root.glob("labday-*.json"):
                try:
                    d = dt.date.fromisoformat(f.name[len("labday-"):-len(".json")])
                except ValueError:
                    continue
                if d < now and (now - d).days <= 7 and (best is None or d > best):
                    best = d
            if best is None:
                return None, {}, {}
            lab = json.loads((self._root / f"labday-{best.isoformat()}.json").read_text())
            day = json.loads(self._day_path(best.isoformat()).read_text())
            if not isinstance(lab, dict) or not isinstance(day, dict):
                return None, {}, {}
            return best.isoformat(), lab, day
        except Exception as e:  # noqa: BLE001
            print(f"homebase engine: an earlier day's Lab files do not read: {e!r}", file=sys.stderr)
            return None, {}, {}

    @staticmethod
    def _lab_rec_ok(rec) -> bool:
        """A day state as a file gives it (a dict): every field the Lab section -- or on_fill -- would lean on has
        its type and a sane value. A quantity below zero once divided by zero inside on_fill."""
        inf = float("inf")

        def num(v) -> bool:
            return v is None or (isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != inf)

        def count(v) -> bool:
            return isinstance(v, int) and not isinstance(v, bool) and v >= 0

        return (isinstance(rec, dict) and isinstance(rec.get("strategy"), str) and isinstance(rec.get("account"), str)
                and isinstance(rec.get("date"), str)
                and rec.get("status") in ("idle", "placing", "placed", "live", "done", "error")
                and all(rec.get(k) is None or isinstance(rec[k], str) for k in ("exit_reason", "note", "take_src"))
                and count(rec.get("qty")) and count(rec.get("entry_qty", 0)) and count(rec.get("exit_qty", 0))
                and rec.get("entry_side") in (None, "Buy", "Sell")
                and all(rec.get(k) is None or isinstance(rec[k], str) for k in LAB_ID_FIELDS)
                # every number on_fill, _close_if_out, _gross_pnl, _fee and _set_take_px do arithmetic on, for any
                # kind: the levels fields too (tp_pts makes _set_take_px compute a take price at the entry fill)
                and all(num(rec.get(k)) for k in ("entry_fill", "exit_fill", "entry_anchor", "sl_px", "tp_px", "tp_rr",
                                                  "upper_px", "lower_px", "pnl", "sl_pts", "sl_sell_pts", "tp_pts",
                                                  "take_usd", "take_px")))

    def _lab_roll_day(self, today: str, only=None) -> None:
        """`only`: None for the day's roll; else the names of Lab strategies that came (back) into the config
        after it -- the roll is run again for their states and rows alone.
        Whose is a key? By its strategy name in self.cfg, three ways (N-1):
          kind "lab"            the Lab section's: checked, carried, pruned;
          another kind          foreign: never looked at; extras a Lab file holds for it are dropped, said once;
          not in the config     nobody's just now: its state, its extras in memory and its entry in the Lab file
                                all stay exactly as they are, with no journal line, until the strategy is back."""
        mem = self._lab_mem()
        if only is None:
            first_today = not self._lab_path().exists()   # this day's file is written below: a later restart skips the disk
            if first_today:
                self._lab_disk_day = today
        else:                                         # a strategy that came back: the disk too, if this process read it
            first_today = self.__dict__.get("_lab_disk_day") == today
        found: dict = {}                              # (strategy, account) -> the round to carry
        unread: dict = {}                             # (strategy, account) -> a record that does not read

        def lab(name) -> bool:
            if not isinstance(name, str):            # O-3: a damaged name (a list, a number) is not a Lab strategy,
                return False                         # and is never used as a dict key here
            cfg = self.cfg.strategies.get(name)
            return cfg is not None and cfg.kind == LAB and (only is None or name in only)

        def foreign(name) -> bool:                   # in the config, and of another kind
            cfg = self.cfg.strategies.get(name) if isinstance(name, str) else None
            return cfg is not None and cfg.kind != LAB

        def strange(key) -> None:                    # extras a Lab file holds for another kind's state
            del mem[key]
            self.journal("lab_foreign_key", key=key, note="the Lab file named a state that is not a Lab strategy's")

        def pair_of(key) -> tuple:
            name, _, rest = str(key).partition("@")
            return name, rest.split("#", 1)[0]

        def blind(key, rec, date) -> None:
            """A row that does not read: carried all the same (fail closed), with whatever order ids it names."""
            pair = pair_of(key)
            if pair[0] and pair[1]:
                u = unread.setdefault(pair, {"date": date if isinstance(date, str) else today, "orders": []})
                if isinstance(rec, dict):
                    u["orders"] += [rec[k] for k in LAB_ID_FIELDS
                                    if isinstance(rec.get(k), str) and rec[k] and rec[k] not in u["orders"]]

        def take(key, rec, x, date) -> None:
            """One row of an earlier day, on its own; it never stops the rows of the other accounts."""
            pair = pair_of(key)
            try:
                x = x if isinstance(x, dict) else None
                if x is not None:
                    self._lab_coerce(x, carried_key="#c" in str(key))
                if not self._lab_rec_ok(rec) or (rec["strategy"], rec["account"]) != pair:
                    raise ValueError("a field is missing or of the wrong type")
                if rec["status"] == "idle" and x is not None and (x.get("iid") or x.get("legs") or x.get("carry")):
                    raise ValueError("an idle state beside a round's extras")
                if not self._lab_unresolved(rec, x):
                    return
                was = x.get("carry") if x is not None and isinstance(x.get("carry"), dict) else None
                if was is not None and was.get("unread"):
                    u = unread.setdefault(pair, {"date": was.get("date") or date, "orders": []})
                    u["orders"] += [i for i in was.get("orders") or [] if i not in u["orders"]]
                    return
                c = found.setdefault(pair, {
                    "date": (was or {}).get("date") or date, "status": (was or {}).get("status") or rec["status"],
                    "round": (x or {}).get("round"), "iid": (x or {}).get("iid"), "placed_ms": (x or {}).get("placed_ms"),
                    "orders": [], "sides": {}, "filled": (was or {}).get("filled"), "was": dict((was or {}).get("was") or {})})
                if was is not None:
                    c["orders"] += [i for i in was.get("orders") or [] if i not in c["orders"]]
                    c["sides"].update(was.get("sides") or {})
                    return
                for k, side in (("upper_id", "Buy"), ("lower_id", "Sell"), ("up_sl_id", "Sell"), ("up_tp_id", "Sell"),
                                ("dn_sl_id", "Buy"), ("dn_tp_id", "Buy")):
                    if rec.get(k) and rec[k] not in c["orders"]:
                        c["orders"].append(rec[k])
                        c["sides"][rec[k]] = side
                if not c["was"] or rec.get("entry_side"):         # what was known of the trade, for the owner
                    leg = ((x or {}).get("legs") or {}).get(rec.get("entry_side") or "") or {}
                    c["was"] = {"status": rec["status"], "entry_side": rec.get("entry_side"), "qty": rec.get("qty"),
                                "entry_qty": rec.get("entry_qty", 0), "entry_fill": rec.get("entry_fill"),
                                "exit_qty": rec.get("exit_qty", 0), "exit_fill": rec.get("exit_fill"),
                                "sl": rec.get("sl_px") if rec.get("sl_px") is not None else leg.get("sl_px"),
                                "tp": rec.get("tp_px") if rec.get("tp_px") is not None else leg.get("tp_px")}
            except Exception as e:  # noqa: BLE001
                blind(key, rec, date)
                print(f"homebase engine: a Lab record of {date} does not read ({key}): {e!r}", file=sys.stderr)

        changed = False
        for k, st in list(self.states.items()):
            pair = pair_of(k)
            if not lab(pair[0]):
                # O-2: the Lab section never looks at, changes or deletes a state of another kind, whatever a
                # labday file names. A state is the Lab section's by its KEY (what _state built it under).
                # N-1: and a name that is in NO config is left completely alone, its extras too
                if k in mem and foreign(pair[0]):
                    strange(k)
                continue
            if st.date != today and isinstance(st.date, str):    # 1. what this engine still holds of an earlier day
                take(k, asdict(st), mem.get(k), st.date)
            elif st.date == today and (self._lab_carried(st) or (
                    self._lab_rec_ok(asdict(st)) and (st.strategy, st.account) == pair)):
                continue
            else:                                     # G1: a state of TODAY whose fields do not read (a damaged
                blind(k, asdict(st), today)           # day file): out of on_fill's way, a block from here on
            del self.states[k]
            changed = True
        for k in [k for k in mem if k not in self.states]:
            name = pair_of(k)[0]
            if lab(name):                             # a Lab strategy's extras with no state: gone with the day
                del mem[k]
            elif foreign(name):
                strange(k)                            # (a name in no config: left as it is)
        if first_today:                               # 2. what the files of the last Lab day say (a restart)
            date, lab_old, day_old = self._lab_last_files(today)
            for k, rec in day_old.items():
                pair = pair_of(k)
                if not lab(pair[0]) or pair in unread:
                    continue                          # (O-2: never a row of another kind)
                d = rec.get("date") if isinstance(rec, dict) else None
                if d != date:
                    try:
                        older = isinstance(d, str) and dt.date.fromisoformat(d) < dt.date.fromisoformat(date)
                    except ValueError:
                        older = False
                    if k in lab_old or not older:     # M3: not a state of a day before: a row that does not read
                        blind(k, rec, date)
                    continue
                take(k, rec, lab_old.get(k), date)
        for pair in list(found):
            if pair in unread:                        # one row of the pair did not read: the whole pair is unread
                u = unread[pair]
                u["orders"] += [i for i in found.pop(pair)["orders"] if i not in u["orders"]]
        for pair, c in found.items():                 # 3. a block per pair, as a state of today under its own key
            try:
                changed = self._lab_carry_make(pair, c, today) or changed
            except Exception as e:  # noqa: BLE001 -- this row does not read after all: carried unread
                unread.setdefault(pair, {"date": c.get("date"), "orders": list(c.get("orders") or [])})
                print(f"homebase engine: a Lab round of {c.get('date')} could not be carried as it is: {e!r}",
                      file=sys.stderr)
        for pair, u in unread.items():
            changed = self._lab_carry_make(pair, {"date": u["date"] if isinstance(u["date"], str) else today,
                                                  "status": None, "orders": u["orders"], "unread": True}, today) or changed
        if only is None:
            self.__dict__.pop("_lab_tries", None)     # G2: a new day reads on the fast schedule again
        if changed:
            self._save()
        self._lab_save()                              # always: the file says "this day was rolled"

    def _lab_carry_make(self, pair: tuple, c: dict, today: str) -> bool:
        """One carried block: a state of today under "strategy@account#c<date>", and NOTHING but a block. Its
        status is `error` (never live, placed or placing), it holds no order id and no entry fact, so no path of
        the engine, the chart's bot lock, reconcile_account or check_takes sees a busy bot or a position in it,
        and on_fill can book no fill to it. What was known of the trade (side, size, entry fill, its order ids,
        its day) is kept in the extras for the owner. A block whose record did not read (`unread`) clears by
        hand only."""
        name, account = pair
        cfg = self.cfg.strategies.get(name)
        if cfg is None or cfg.kind != LAB or any(
                self._lab_carried(s) for s in self.states.values()
                if s.strategy == name and s.account == account and s.date == today):
            return False
        key = f"{name}@{account}#c{c['date']}"
        while key in self.states:
            key += "+"
        why = LAB_BAD_RECORD if c.get("unread") else LAB_CANNOT_CHECK
        was = c.get("was") if isinstance(c.get("was"), dict) else {}
        qty = was.get("qty")
        st = DayState(strategy=name, account=account, date=today,
                      qty=qty if isinstance(qty, int) and not isinstance(qty, bool) and qty >= 0 else 0,
                      status="error", exit_reason="carried", note=why)
        n = c.get("round")
        n = n if isinstance(n, int) and not isinstance(n, bool) else 1
        x = self._lab_blank(n)
        x.update(check=True, clean=False, why=why, iid=c["iid"] if isinstance(c.get("iid"), dict) else {},
                 placed_ms=c.get("placed_ms"),
                 carry={"date": c["date"], "status": c.get("status"), "since_ms": self._lab_ms(),
                        "orders": [i for i in c.get("orders") or [] if isinstance(i, str)],
                        "sides": dict(c.get("sides") or {}), "was": dict(was),
                        "filled": c["filled"] if isinstance(c.get("filled"), list) else None,
                        "unread": bool(c.get("unread"))})
        self._lab_coerce(x, carried_key=True)
        x["why"] = why
        self.states[key] = st
        self._lab_mem()[key] = x
        self.journal("lab_carry", strategy=name, account=account, round=n, date=c["date"], status=c.get("status"),
                     orders=x["carry"]["orders"], **({"unread": True} if c.get("unread") else {}))
        return True

    def _lab_carried(self, st: DayState) -> bool:
        """A block carried from an earlier day: a state of today that only says "this account is not resolved"."""
        x = self._lab_mem().get(self._lab_key(st) or "")
        return isinstance(x, dict) and isinstance(x.get("carry"), dict)

    async def _lab_carry_check(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter, x: dict) -> None:
        """Read only, never an order. An order of the block that newly reads Filled is written down
        (`lab_carry_fill`) and changes nothing. The block clears when every known order reads ended at the broker
        AND the account's net in the market reads zero. Every 5 s for a minute, then every 30 s. A block whose
        record did not read is cleared by hand only."""
        key = self._lab_key(st)
        tries = self.__dict__.setdefault("_lab_tries", {})
        rk = f"carry:{key}"
        gap = LAB_FLAT_RETRY_S if tries.get(rk, 0) < 12 else LAB_CHECK_RETRY_S
        carry = x["carry"]
        if key is None or not ad.connected or carry.get("unread") \
                or time.time() - self._retry_at.get(rk, 0.0) < gap:
            return
        self._retry_at[rk] = time.time()
        tries[rk] = tries.get(rk, 0) + 1
        orders = [i for i in carry.get("orders") or [] if isinstance(i, str)]
        status: dict = {}
        for i in orders:
            try:
                status[i] = await ad.get_order_status(i)
            except Exception:  # noqa: BLE001 -- unread: asked again
                status[i] = None
        if self.states.get(key) is not st:
            return
        filled = [i for i in orders if status[i] == "Filled"]
        if not isinstance(carry.get("filled"), list):
            carry["filled"] = filled                  # the first read: what had filled before anyone looked
            self._lab_save()
        else:
            for i in [i for i in filled if i not in carry["filled"]]:
                try:
                    qty = (await ad.get_order_state(i) or {}).get("filled_qty")
                except Exception:  # noqa: BLE001
                    qty = None
                carry["filled"].append(i)
                self._lab_save()
                self.journal("lab_carry_fill", strategy=st.strategy, account=st.account, round=x.get("round"),
                             date=carry.get("date"), order_id=i, side=(carry.get("sides") or {}).get(i), qty=qty,
                             price=None, seen="the order's status at the broker")
        if any(status[i] not in TERMINAL for i in orders):
            return
        try:
            net = await ad.get_net_position(cfg.symbol)
        except Exception:  # noqa: BLE001 -- unreadable is NOT flat
            return
        if net is None or isinstance(net, bool) or int(net) != 0 or self.states.get(key) is not st:
            return
        del self.states[key]
        self._lab_mem().pop(key, None)
        tries.pop(rk, None)
        self._save()
        self._lab_save()
        self.journal("lab_carry_cleared", strategy=st.strategy, account=st.account, round=x.get("round"),
                     date=carry.get("date"))

    async def lab_clear_block(self, name: str, account: str) -> dict:
        """The owner's explicit "this account is fine": remove the block carried for (strategy, account). Only when
        the account's net in the strategy's market reads exactly 0 AND none of the block's known orders reads
        working or pending (one that cannot be read does not stop it: that is what the by-hand clear is for). A
        position, a read that fails or a working old order: refused with the sentence, nothing changes. It sends
        nothing and cancels nothing.
        -> {"ok": True, "cleared": [dates]} | {"ok": False, "reason": sentence[, "orders": [the working ones]]}"""
        cfg = self.cfg.strategies.get(name)
        if cfg is None or cfg.kind != LAB:
            return {"ok": False, "reason": LAB_NOT_ON_DESK}
        self._lab_roll()

        def blocks() -> list:
            return [(k, s) for k, s in self.states.items() if s.strategy == name and s.account == account
                    and s.date == self._today() and self._lab_carried(s)]

        if not blocks():
            return {"ok": False, "reason": LAB_NO_BLOCK}
        why = await self._lab_position(name, cfg, account, said=False)
        if why is not None:
            return {"ok": False, "reason": why}
        ad = self.adapters.get(account)
        working = []
        for k, st in blocks():
            for i in (self._lab_x(st).get("carry") or {}).get("orders") or []:
                try:
                    status = await ad.get_order_status(i)
                except Exception:  # noqa: BLE001 -- an order that does not read does not stop a clear by hand
                    status = None
                if status is not None and status not in TERMINAL and i not in working:
                    working.append(i)            # any status that reads and is not ended: it could still fill
        if working:                                  # it could still fill, into a trade that is not this one's
            return {"ok": False, "reason": LAB_OLD_ORDER_WORKING, "orders": sorted(working)}
        cleared = []
        for k, st in blocks():                       # read again: the reads yielded
            x = self._lab_mem().pop(k, None) or {}
            del self.states[k]
            self.__dict__.get("_lab_tries", {}).pop(f"carry:{k}", None)
            date = (x.get("carry") or {}).get("date")
            cleared.append(date)
            self.journal("lab_carry_cleared", strategy=name, account=account, round=x.get("round"), date=date,
                         why="by hand")
        if cleared:
            self._save()
            self._lab_save()
        return {"ok": True, "cleared": cleared} if cleared else {"ok": False, "reason": LAB_NO_BLOCK}

    def _lab_mark_check(self, st: DayState, x: dict, reason: str, *, why: Optional[str] = None,
                        actions: Optional[list] = None, detail: Optional[str] = None) -> None:
        """This round's orders cannot be checked: it is never clean today, so the account takes no new Lab trade.
        Journaled once (`lab_check`)."""
        if x.get("check"):
            return
        x["check"], x["clean"], x["why"] = True, False, why or LAB_CANNOT_CHECK
        self._lab_save()
        try:
            self.journal("lab_check", strategy=st.strategy, account=st.account, round=x.get("round"),
                         reason=reason, actions=actions or [], **({"detail": detail} if detail else {}))
        except Exception as e:  # noqa: BLE001
            print(f"homebase engine: journal lab_check failed: {e!r}", file=sys.stderr)

    def _lab_stuck(self, st: DayState, x: dict) -> bool:
        """A round that can never be clean: its extras were lost, its placement outcome is unknown, both of its
        entries filled, or a kill's market-out reported failure."""
        if not x.get("check"):
            if st.note == PLACING_UNKNOWN:
                self._lab_mark_check(st, x, PLACING_UNKNOWN)
            elif st.status == "error" and st.exit_reason == "both_filled":
                self._lab_mark_check(st, x, "both entries filled")
            elif st.note == MARKET_OUT_FAILED:
                self._lab_mark_check(st, x, MARKET_OUT_FAILED)
            elif x.get("blind"):                     # a stop order the Desk does not know: never clean
                self._lab_mark_check(st, x, "the Desk does not know this trade's stop order", why=LAB_NO_STOP_ID)
        return bool(x.get("check"))

    def _lab_clean(self, st: DayState) -> bool:
        """I-2: may a new round follow this one? Idle: yes. Otherwise only once it is over and its orders were
        read terminal (a `clean` mark on a round that is not over is not believed)."""
        if st.status == "idle":
            return True
        x = self._lab_x(st)
        if self._lab_stuck(st, x) or x.get("unconfirmed"):
            return False
        return bool(x.get("clean")) and st.status in ("done", "error")

    def lab_rounds(self, name: str) -> list[dict]:
        """Today's rounds of a Lab strategy, oldest first: one row per round per account; a block carried from an
        earlier day is a row too (`carried`, with its own `date`). No broker call. It is not memory only: the
        first call of a day runs the day roll (it may read the last Lab day's two files, and writes today's), and
        an entry or exit time seen here for the first time is written to the Lab file."""
        out = []
        cfg = self.cfg.strategies.get(name)
        if cfg is None or cfg.kind != LAB:           # never extras for a strategy of another kind
            return out
        self._lab_roll()
        for st in self.day_states(name):
            if st.status == "idle":
                continue
            x = self._lab_x(st)
            if self._lab_stamp(st, x):
                self._lab_save()
            sl, tp = self._lab_levels(st, x)
            carry = x.get("carry") if isinstance(x.get("carry"), dict) else None
            out.append({"account": st.account, "round": x.get("round"), "status": st.status,
                        "date": (carry or {}).get("date") or st.date, "carried": carry is not None,
                        "iid": dict(x.get("iid") or {}), "qty": st.qty, "entry_side": st.entry_side,
                        "entry_qty": st.entry_qty, "entry_fill": st.entry_fill, "exit_qty": st.exit_qty,
                        "exit_fill": st.exit_fill, "exit_reason": st.exit_reason, "sl": sl, "tp": tp,
                        "pnl": st.pnl, "clean": self._lab_clean(st), "entry_ms": x.get("entry_ms"),
                        "exit_ms": x.get("exit_ms"), "why": x.get("why") or (st.note or None if st.status == "error" else None),
                        "cancelled": list(x.get("cancelled") or []), "closing": x.get("closing"),
                        "placed_ms": x.get("placed_ms"),
                        "orders": [i for i in (st.upper_id, st.lower_id, st.up_sl_id, st.up_tp_id, st.dn_sl_id,
                                               st.dn_tp_id) if i]})
            if carry is not None:                    # a block: what was known of the trade when it was carried
                was = carry.get("was") if isinstance(carry.get("was"), dict) else {}
                out[-1].update(entry_side=was.get("entry_side"), qty=was.get("qty", st.qty),
                               entry_qty=was.get("entry_qty", 0), entry_fill=was.get("entry_fill"),
                               exit_qty=was.get("exit_qty", 0), exit_fill=was.get("exit_fill"),
                               sl=was.get("sl"), tp=was.get("tp"), orders=list(carry.get("orders") or []))
        out.sort(key=lambda r: (r["placed_ms"] or 0, r["round"] or 0, r["account"]))
        return out

    def lab_open(self, name: str) -> list[str]:
        """Accounts with a round of this strategy that is placing, placed or live, or whose orders are not checked
        (a block carried from an earlier day is one)."""
        cfg = self.cfg.strategies.get(name)
        if cfg is None or cfg.kind != LAB:
            return []
        self._lab_roll()
        return sorted({st.account for st in self.day_states(name)
                       if st.status in ("placing", "placed", "live") or not self._lab_clean(st)})

    # --- lab_enter ------------------------------------------------------------------------------------
    @staticmethod
    def _lab_num(v) -> bool:
        return isinstance(v, (int, float)) and not isinstance(v, bool) and v == v and abs(v) != float("inf")

    def _lab_bad_legs(self, legs) -> Optional[str]:
        """The sentence for a set of legs the engine will not place; None when it will. One entry, or one buy
        stop and one sell stop; every entry with a stop on its losing side."""
        if not isinstance(legs, (list, tuple)) or not 1 <= len(legs) <= 2:
            return LAB_BAD_ORDER
        num = self._lab_num
        for g in legs:
            if not isinstance(g, LabLeg) or not isinstance(g.move, bool):
                return LAB_BAD_ORDER
            if not isinstance(g.iid, int) or isinstance(g.iid, bool) or g.side not in ("Buy", "Sell") \
                    or g.entry not in ("Market", "Stop"):
                return LAB_BAD_ORDER
            if g.entry == "Stop" and not (num(g.entry_price) and g.entry_price > 0):
                return LAB_BAD_ORDER
            if g.entry == "Market" and g.entry_price is not None:
                return LAB_BAD_ORDER
            if not (num(g.sl_px) and g.sl_px > 0):
                return LAB_NO_STOP
            if (g.tp_px is not None and not num(g.tp_px)) or (g.ref_px is not None and not num(g.ref_px)) \
                    or (g.tp_rr is not None and not (num(g.tp_rr) and g.tp_rr > 0)):
                return LAB_BAD_ORDER
            if g.tp_rr is not None and g.tp_px is None:      # the first target is sent priced; the fill re-prices it
                return LAB_BAD_ORDER
            sign = 1 if g.side == "Buy" else -1
            base = g.ref_px if g.ref_px is not None else g.entry_price
            if base is not None:
                if not sign * (base - g.sl_px) > 0:
                    return LAB_WRONG_SIDE
                if g.tp_px is not None and not sign * (g.tp_px - base) > 0:
                    return LAB_BAD_ORDER
        if len(legs) == 2:
            a, b = legs
            if {a.side, b.side} != {"Buy", "Sell"} or a.entry != "Stop" or b.entry != "Stop" or a.iid == b.iid:
                return LAB_NOT_A_PAIR
            buy, sell = (a, b) if a.side == "Buy" else (b, a)
            if not buy.entry_price > sell.entry_price:
                return LAB_BAD_ORDER
        return None

    @staticmethod
    def _lab_clear_reject(err) -> bool:
        """Did the broker (or the adapter, before sending) clearly refuse this entry? Only the adapters' own fixed
        phrases count. Anything else -- no words, None, an exception's text, a phrase nobody listed -- is
        OUTCOME UNKNOWN: the order may exist at the broker under an id nobody recorded."""
        e = str(err if err is not None else "").strip()
        return e in LAB_CLEAR_REJECTS and not any(w in e.lower() for w in LAB_UNKNOWN_WORDS)

    def _lab_market_taken(self, name: str, cfg: StrategyCfg, account: str) -> Optional[str]:
        """Design A5, at placement: the symbol of another strategy that is booked on this account, or busy on it
        today, in the same market (the engine's own substring rule, on_fill's exit match)."""
        mine = str(cfg.symbol).upper()
        for other, so in self.cfg.strategies.items():
            theirs = str(so.symbol).upper()
            if other == name or not mine or not theirs or not (mine in theirs or theirs in mine):
                continue
            if any(a.get("account") == account for a in assignments(self.cfg, other)) or any(
                    s.strategy == other and s.status in ("placing", "placed", "live")
                    for s in self.day_states_for_account(account)):
                return so.symbol
        return None

    def _lab_archive(self, key: str, st: DayState) -> None:
        """A terminal, clean round leaves the plain key (I-3: the next state made for the pair is inserted last)."""
        mem = self._lab_mem()
        x = mem.pop(key, None)
        n = int((x or {}).get("round") or self._lab_round_no(st))
        new = f"{key}#{n}"
        while new in self.states:                     # never write over a round
            n += 1
            new = f"{key}#{n}"
        del self.states[key]
        self.states[new] = st
        if x is not None:
            mem[new] = x

    def _lab_sits_out(self, name: str, cfg: StrategyCfg, account: str, qty, max_rounds: int) -> Optional[str]:
        """Steps 1-3 of lab_enter for one account, as one read with no side effect: the sentence when the account
        sits this trade out, None when a round may be opened. It is asked twice: before the position read (an
        account that sits out anyway costs no broker request) and again in the same run that opens the round."""
        if not isinstance(qty, int) or isinstance(qty, bool) or qty < 1 or "#" in str(account) \
                or not any(a.get("account") == account for a in assignments(self.cfg, name)):
            return LAB_BAD_ORDER
        if self.account_locked(account):                                    # 1
            return LAB_ACCOUNT_STOPPED
        ad = self.adapters.get(account)
        if ad is None or not ad.connected:
            return LAB_NOT_CONNECTED
        rules = self.rules_for(account)
        if rules.day_take or rules.target_take:     # check_takes needs a price for every live state on the account
            return LAB_TAKE_RULE
        taken = self._lab_market_taken(name, cfg, account)                  # 2
        if taken is not None:
            return f"Another strategy trades {taken} on this account."
        today = self._today()                                               # 3
        if any(self._archived(s) and (self._lab_carried(s) or not self._lab_clean(s))
               for s in self.day_states(name) if s.account == account):
            return LAB_CANNOT_CHECK                 # an earlier round (of today or of a day before) is not resolved
        cur = self.states.get(f"{name}@{account}")
        if cur is not None and cur.date == today and cur.status != "idle":
            if cur.status in ("placing", "placed", "live"):
                return LAB_ONE_AT_A_TIME
            if not self._lab_clean(cur):
                return LAB_CANNOT_CHECK
        n = 1 + max([int(self._lab_x(s).get("round") or 0) for s in self.day_states(name)
                     if s.account == account and s.status != "idle"], default=0)
        if n > max_rounds:
            return f"Daily limit reached ({max_rounds} trade{'' if max_rounds == 1 else 's'})."
        return None

    async def _lab_position(self, name: str, cfg: StrategyCfg, account: str, said: bool = True) -> Optional[str]:
        """Before EVERY Lab entry: the account's net in the strategy's market, read at the broker. Not zero, or
        not readable -> the sentence, and the account sits the trade out (it uses no round). A round of an
        earlier day that nobody carried, a position opened by hand, an order nobody recorded: none of them is
        traded on top of."""
        ad = self.adapters.get(account)
        try:
            net = await ad.get_net_position(cfg.symbol) if ad is not None and ad.connected else None
            net = None if net is None or isinstance(net, bool) else int(net)
        except Exception:  # noqa: BLE001 -- unreadable is NOT flat
            net = None
        why = LAB_NO_POSITION_READ if net is None else (
            f"The account already holds {cfg.symbol}. Check it." if net else None)
        if why is not None and said:
            self.journal("place_skipped", strategy=name, account=account, reason=why,
                         **({"net": net} if net is not None else {}))
        return why

    def _lab_may_enter(self, name: str) -> tuple:
        """Every strategy-level precondition of an entry, as one read with no side effect: (cfg | None, the
        sentence | None). Asked when lab_enter is called AND again, with no await in between, in the run that
        opens each account's round: a Kill, a disarm, the switch or the clock can move while the position is read."""
        cfg = self.cfg.strategies.get(name)
        if cfg is None or cfg.kind != LAB:
            return None, LAB_NOT_ON_DESK
        if not cfg.enabled:
            return cfg, LAB_OFF
        if self.killed_today(name):
            return cfg, LAB_KILLED
        now = self.now_et()
        hhmm = now.strftime("%H:%M")                 # the door's own rule, by the minute (labrun/door.py)
        if now.time() >= _hhmm(cfg.flat_et) or hhmm > cfg.accept_until_et or hhmm < cfg.accept_from_et:
            return cfg, LAB_TOO_LATE
        if not self.cfg.armed or cfg.shadow:
            return cfg, LAB_DISARMED
        return cfg, None

    def _lab_open_round(self, name: str, account: str, qty, legs: list, max_rounds: int, source: str) -> tuple:
        """Steps 0-4 of lab_enter for one account, in ONE run with no await: EVERY precondition (the strategy's
        and the account's), the archive of the last round and the new round written to disk can never be
        interleaved with another entry, a fill, a Kill or a disarm.
        -> (the new round's state | None, the answer, the strategy's cfg as it is now, the pair's requests | None)"""
        cfg, why = self._lab_may_enter(name)
        if why is None:
            why = self._lab_sits_out(name, cfg, account, qty, max_rounds)
        if why is not None:
            if why == LAB_DISARMED:                 # written down only, as the disarmed path of lab_enter does
                self.journal("shadow_signal" if (self.cfg.armed and cfg.shadow) else "dry_run", strategy=name,
                             source=source, account=account, qty=qty, legs=[asdict(g) for g in legs])
            else:
                self.journal("place_skipped", strategy=name, account=account, reason=why)
            return None, {"ok": False, "round": None, "reason": why}, cfg, None
        key, today = f"{name}@{account}", self._today()
        cur = self.states.get(key)
        n = 1 + max([int(self._lab_x(s).get("round") or 0) for s in self.day_states(name)
                     if s.account == account and s.status != "idle"], default=0)
        x = self._lab_blank(n)                      # everything is built BEFORE anything changes: a failure here
        x["iid"] = {g.side: g.iid for g in legs}    # leaves no state behind, and never one that is "placing"
        x["legs"] = {g.side: asdict(g) for g in legs}
        x["move"] = any(g.move for g in legs)
        x["placed_ms"] = self._lab_ms()
        reqs = None
        if len(legs) == 2:
            pair = legs if legs[0].side == "Buy" else legs[::-1]
            reqs = tuple(OrderRequest(symbol=cfg.symbol, side=g.side, qty=qty, order_type=g.entry,
                                      price=g.entry_price, stop_price=g.sl_px, tp_price=g.tp_px,
                                      text="homebase:entry") for g in pair)
        if cur is not None and cur.date == today and cur.status != "idle":
            self._lab_archive(key, cur)
        else:
            self.states.pop(key, None)              # an idle or older state: the new one must be the pair's last
            self._lab_mem().pop(key, None)
        st = self._state(name, account)                                     # 4
        st.qty, st.status = qty, "placing"
        self._lab_mem()[key] = x
        self.__dict__.get("_lab_tries", {}).pop(key, None)   # the new round reads on the fast schedule again
        for k2 in (f"settle:{key}", f"flat:{key}", f"wait:{key}"):
            self.__dict__.get("_lab_said", {}).pop(k2, None)
            self._retry_at.pop(k2, None)
        try:                                        # durable BEFORE the order leaves
            self._save()
            self._lab_save(strict=True)
            self.journal("lab_round", strategy=name, account=account, round=n, qty=qty, source=source,
                         iid=x["iid"], legs=list(x["legs"].values()))
        except Exception as e:  # noqa: BLE001 -- nothing was sent
            st.status, st.exit_reason, st.note = "error", "error", f"not written: {e}"[:200]
            x["clean"] = True
            print(f"homebase engine: a Lab round could not be written: {e!r}", file=sys.stderr)
            return None, {"ok": False, "round": n, "reason": LAB_NOT_WRITTEN}, cfg, None
        return st, {"ok": True, "round": n, "reason": None}, cfg, reqs

    async def _lab_enter_one(self, name: str, account: str, qty, legs: list, max_rounds: int, source: str,
                             t0: float) -> dict:
        cfg = self.cfg.strategies.get(name)
        why = LAB_NOT_ON_DESK if cfg is None or cfg.kind != LAB else \
            self._lab_sits_out(name, cfg, account, qty, max_rounds)
        if why is not None:
            self.journal("place_skipped", strategy=name, account=account, reason=why)
            return {"ok": False, "round": None, "reason": why}
        why = await self._lab_position(name, cfg, account)
        if why is not None:
            return {"ok": False, "round": None, "reason": why}
        # the read yielded: from here to the placement nothing awaits, and everything is asked again
        st, ans, cfg, reqs = self._lab_open_round(name, account, qty, legs, max_rounds, source)
        if st is None:
            return ans
        x = self._lab_x(st)
        try:                                                                # 5
            if reqs is None:
                got = await self._place_one(name, cfg, account, qty, legs[0], source, t0)
            else:
                got = await self._place(name, cfg, account, qty, reqs[0].price, reqs[1].price, source, t0,
                                        reqs=reqs)
        except Exception as e:  # noqa: BLE001 -- the outcome is unknown
            got = e
        words = ""                                  # the venue's own words for a failure (W1)
        if st.status == "placing":                                          # 6: never left as "placing"
            st.status, st.exit_reason = "error", "error"
            st.note = f"placement did not finish: {got}"[:200]
            words = (f"{type(got).__name__}: {got}" if isinstance(got, Exception) else str(got))[:200]
            self._lab_mark_check(st, x, st.note, detail=words)
            self._save()
        if st.status == "error":
            note = str(st.note or "")
            words = words or (note.split(": ", 1)[1] if note.startswith(("entry: ", "upper leg: ", "lower leg: "))
                              else note)
            if any(i for i in (st.upper_id, st.lower_id, st.up_sl_id, st.up_tp_id, st.dn_sl_id, st.dn_tp_id)):
                pass                                # ids are known: the clock reads them (_lab_settle)
            elif note == "account not connected":   # refused before anything left
                x["clean"] = True
            elif len(legs) == 2:                    # _place cancels the survivor and keeps no id: unreadable
                self._lab_mark_check(st, x, f"a pair's placement failed ({note}); the other leg's id is not kept",
                                     detail=words)
            elif not self._lab_clear_reject(note[len("entry: "):] if note.startswith("entry: ") else note):
                # no answer, an empty one, or words nobody has proven to be a reject: the order may be there
                self._lab_mark_check(st, x, f"the entry's outcome is unknown ({note})", detail=words)
            elif not x.get("check"):                # a clear refusal: nothing is at the broker
                x["clean"] = True
            self._lab_stamp(st, x)
            self._lab_save()
        if st.status in ("placed", "live"):
            for g in legs:                          # I1: every entry has a stop, and the desk must know its order
                sl_id, tp_id = (st.up_sl_id, st.up_tp_id) if g.side == "Buy" else (st.dn_sl_id, st.dn_tp_id)
                if not sl_id or (g.tp_px is not None and not tp_id):
                    x["blind"] = True
            if x["blind"]:
                self._lab_mark_check(st, x, "the broker's answer named no stop order (or no target order)",
                                     why=LAB_NO_STOP_ID)
                ans = {**ans, "warning": LAB_NO_STOP_ID}
        if isinstance(got, dict) and got.get("ok"):
            return ans
        if isinstance(got, Exception) and st.status in ("placed", "live", "done"):
            # S3: the broker acknowledged it and a later step here raised: it IS a trade of this round
            return {**ans, "warning": f"placed; a later step failed: {type(got).__name__}: {got}"[:200]}
        if st.status == "error" and st.note == "account not connected":
            return {"ok": False, "round": ans["round"], "reason": LAB_NOT_CONNECTED}
        if len(legs) == 1 and x.get("check"):       # outcome unknown: "refused" would be a guess. The venue's
            return {"ok": False, "round": ans["round"], "reason": LAB_BAD_ORDER,     # words ride along
                    **({"detail": words} if words and words != "None" else {})}
        if isinstance(got, dict) and "rejected: " in str(got.get("reason")):
            return {"ok": False, "round": ans["round"],
                    "reason": "The broker refused it: " + str(got["reason"]).split("rejected: ", 1)[1]}
        if isinstance(got, dict) and str(got.get("reason", "")).startswith("account stopped"):
            return {"ok": False, "round": ans["round"], "reason": LAB_ACCOUNT_STOPPED}
        return {"ok": False, "round": ans["round"], "reason": LAB_BAD_ORDER,
                **({"detail": words} if words and words != "None" else {})}

    async def lab_enter(self, name: str, legs: list, sizes: dict, *, max_rounds: int,
                        source: str = "lab") -> dict:
        """A Lab strategy's entry (one LabLeg, or a buy-stop / sell-stop pair) on every account in `sizes`
        ({account: contracts}), each as a new ROUND: one position at a time per account, a new round only after
        the last one's orders were read terminal, the account's position read first, the round on disk before
        its order leaves. The accounts go side by side. Disarmed: journaled only (`dry_run`), no state.
        -> {"armed": bool, "accounts": {account: {"ok", "round", "reason"[, "detail"][, "warning"]}}}
           (+ "reason" when the whole call was refused)"""
        sizes = dict(sizes or {})

        def refused(reason: str, armed: Optional[bool] = None) -> dict:
            return {"armed": bool(self.cfg.armed) if armed is None else armed, "reason": reason,
                    "accounts": {a: {"ok": False, "round": None, "reason": reason} for a in sizes}}

        cfg, why = self._lab_may_enter(name)
        if why in (LAB_NOT_ON_DESK, LAB_OFF, LAB_KILLED):
            return refused(why)
        bad = self._lab_bad_legs(legs)
        if bad is not None:
            return refused(bad)
        if why == LAB_TOO_LATE:
            return refused(why)
        legs = list(legs)
        if why == LAB_DISARMED:
            ev = "shadow_signal" if (self.cfg.armed and cfg.shadow) else "dry_run"
            for a, q in sizes.items():
                self.journal(ev, strategy=name, source=source, account=a, qty=q, legs=[asdict(g) for g in legs])
            return refused(LAB_DISARMED, armed=False)
        self._lab_roll()
        t0 = time.time()
        order = list(sizes)
        outs = await asyncio.gather(*(self._lab_enter_one(name, a, sizes[a], legs, max_rounds, source, t0)
                                      for a in order), return_exceptions=True)
        return {"armed": bool(self.cfg.armed),
                "accounts": {a: (o if isinstance(o, dict) else {"ok": False, "round": None, "reason": LAB_BAD_ORDER})
                             for a, o in zip(order, outs)}}

    # --- a closed round's orders (I-2) -------------------------------------------------------------
    async def _lab_settle(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter) -> None:
        """Read every order id a terminal round placed. All terminal -> the round is clean (`lab_settled`) and a
        new one may follow. A working ENTRY leftover is cancelled (a later fill would be a new entry); a working
        stop / target only when the account's net in the market reads zero -- protection is never taken from a
        position. An entry that filled on a side the round never held, or anything unread: not clean, `lab_check`."""
        x = self._lab_x(st)
        if st.status not in ("done", "error") or x.get("clean") or not ad.connected:
            return
        if self._lab_stuck(st, x):
            return
        key = self._lab_key(st) or f"{st.strategy}@{st.account}"
        tries = self.__dict__.setdefault("_lab_tries", {})
        gap = LAB_SETTLE_S if tries.get(key, 0) < LAB_SETTLE_FAST else LAB_CHECK_RETRY_S
        if tries.get(key) and time.time() - self._retry_at.get(f"settle:{key}", 0.0) < gap:
            return
        self._retry_at[f"settle:{key}"] = time.time()
        tries[key] = tries.get(key, 0) + 1
        work_e, work_b, unread, filled_b, entries_open = [], [], [], [], False
        for i, side in ((st.upper_id, "Buy"), (st.lower_id, "Sell")):
            if not i:
                continue
            try:
                got = await ad.get_order_state(i) or {}
            except Exception:  # noqa: BLE001 -- unread, asked again
                got = {}
            status, filled = got.get("status"), got.get("filled_qty")
            if status == "Filled" or (status in TERMINAL and filled):
                if st.entry_side != side:
                    return self._lab_mark_check(st, x, f"entry {i} filled ({status}) on a side this round never held")
            elif status in WORKING:
                work_e.append(i)
                entries_open = True
            elif status not in TERMINAL:
                unread.append(i)
                entries_open = True
        for i in (st.up_sl_id, st.up_tp_id, st.dn_sl_id, st.dn_tp_id):
            if not i:
                continue
            try:
                status = await ad.get_order_status(i)
            except Exception:  # noqa: BLE001
                status = None
            if status in WORKING:
                work_b.append(i)
            elif status == "Filled":
                filled_b.append(i)
            elif status not in TERMINAL:
                unread.append(i)
        if self._archived(st) or st.status not in ("done", "error") or x.get("clean"):
            return                                   # it moved on while the reads ran
        sent = bool(x.get("close_sent_ms"))
        if (sent and filled_b) or len(filled_b) > 1:
            # a close was SENT (its answer may never have come) and a stop / target filled, or both of them did:
            # the account may hold the other side now, with no stop. Never clean; a person looks.
            return self._lab_mark_check(
                st, x, f"exit orders filled: {', '.join(filled_b)}" + (" and a close order was sent" if sent else ""),
                why=LAB_EXIT_TWICE)
        if not (work_e or work_b or unread):
            if x.get("unconfirmed"):
                # the close was sent and never confirmed: clean needs BOTH facts, every order ended (read above)
                # AND the account flat in the market. Not flat: the close and an exit may both have filled.
                try:
                    net = await ad.get_net_position(cfg.symbol)
                    net = None if net is None or isinstance(net, bool) else int(net)
                except Exception:  # noqa: BLE001 -- unreadable is NOT flat: asked again
                    net = None
                if self._archived(st) or st.status not in ("done", "error") or x.get("clean"):
                    return
                if net is None:
                    return
                if net:
                    # M2: one position read can lag. Three in a row, at least 2 s apart, before it is for good
                    now, last = self._lab_ms(), x.get("net_bad_ms")
                    if last is None or now - last >= LAB_NET_AGAIN_MS:
                        x["net_bad"], x["net_bad_ms"] = int(x.get("net_bad") or 0) + 1, now
                        self._lab_save()
                    if x["net_bad"] < 3:
                        return
                    return self._lab_mark_check(
                        st, x, f"a close was sent and never confirmed, and the account holds {net:+d} {cfg.symbol}",
                        why=LAB_EXIT_TWICE)
                x["unconfirmed"], x["net_bad"], x["net_bad_ms"] = False, 0, None
            x["clean"], x["why"] = True, None
            tries.pop(key, None)
            self.__dict__.get("_lab_said", {}).pop(f"settle:{key}", None)
            self._lab_stamp(st, x)
            self._lab_save()
            self.journal("lab_settled", strategy=st.strategy, account=st.account, round=x.get("round"))
            return
        acts: list[str] = []
        for i in work_e:
            try:
                r = await ad.cancel_order_by_id(i)
            except Exception as e:  # noqa: BLE001 -- asked again on the next read
                r = OrderResult(ok=False, error=str(e))
            acts.append(f"cancel entry {i}: " + ("ok" if r.ok else str(r.error)))
        if work_b and entries_open:
            # R-C: never on a position read alone. While an entry of the round is not read ended it can still
            # fill, and its stop / target are what it would fill with
            acts.append("an entry of this trade is not ended at the broker — stop/target left working")
        elif work_b:
            try:
                net = int(await ad.get_net_position(cfg.symbol) or 0)
            except Exception as e:  # noqa: BLE001 -- unreadable is NOT flat
                net = None
                acts.append(f"position unreadable ({e}) — stop/target left working")
            if net == 0:
                await self._cancel_brackets(st, ad, acts)
            elif net is not None:
                acts.append(f"the account holds {net:+d} {cfg.symbol} — stop/target left working")
        acts += [f"order {i}: status unknown" for i in unread]
        said = self.__dict__.setdefault("_lab_said", {})
        if said.get(f"settle:{key}") != acts:
            said[f"settle:{key}"] = acts
            x["why"] = LAB_CANNOT_CHECK
            self._lab_save()
            self.journal("lab_check", strategy=st.strategy, account=st.account, round=x.get("round"),
                         reason="orders of the last trade are not all ended", actions=acts)

    # --- lab_cancel -----------------------------------------------------------------------------------
    async def _lab_acked(self, st: DayState) -> bool:
        """Wait (3 s at most) for a round whose placement acks are still out. True = its ids are known."""
        for _ in range(KILL_POLL_N):
            if st.status != "placing":
                break
            await self._kill_sleep(KILL_POLL_S)
        return st.status != "placing"

    async def _lab_hints(self, st: DayState, ad: BrokerAdapter, x: dict) -> None:
        """O-1: the sides a file said were cancelled, read at the broker (every 5 s until each one reads). Ended
        with no fill: it becomes a fact again. Anything else that reads: the hint is dropped. Reads only."""
        hints = [s for s in x.get("cancelled_hint") or [] if s in ("Buy", "Sell")]
        key = f"hint:{st.strategy}@{st.account}"
        if not hints or not ad.connected or time.time() - self._retry_at.get(key, 0.0) < LAB_FLAT_RETRY_S:
            return
        self._retry_at[key] = time.time()
        for s in hints:
            i = st.upper_id if s == "Buy" else st.lower_id
            if i:
                try:
                    got = await ad.get_order_state(i) or {}
                except Exception:  # noqa: BLE001 -- unread: asked again
                    continue
                status, filled = got.get("status"), got.get("filled_qty")
                if status is None:
                    continue
                if status in TERMINAL and status != "Filled" and not filled \
                        and not (st.entry_side == s and st.entry_qty) and s not in x["cancelled"]:
                    x["cancelled"].append(s)
            if s in x["cancelled_hint"]:
                x["cancelled_hint"].remove(s)
        self._lab_save()

    async def _lab_end_unfilled(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter, acts: list) -> bool:
        """Every entry of the round ended with no fill: the round is done / "cancelled". R-C: first every entry is
        READ ended with no fill at the broker, here, whatever the caller or a file believes; one that is not:
        "check it", nothing is ended and nothing cancelled (False). Its stop and target died with their entries;
        they are cancelled for good measure ONLY when the account's net in the market reads zero (a fill push
        can be missed: never take a stop from a position), as the kill does. True = the round was ended."""
        x = self._lab_x(st)
        if not await self._lab_entries_ended(st, ad, x, acts, unfilled=True):
            return False
        if self._archived(st) or st.status not in ("placed", "live"):
            return False                             # the read yielded: it moved on by itself
        st.status, st.exit_reason = "done", "cancelled"
        self._lab_stamp(st, x)
        self._save()
        try:
            net = int(await ad.get_net_position(cfg.symbol) or 0)
        except Exception as e:  # noqa: BLE001 -- unreadable is NOT flat
            acts.append(f"position unreadable ({e}) — stop/target left alone")
            return True
        if net:
            acts.append(f"the account holds {net:+d} {cfg.symbol} — stop/target left alone")
            return True
        await self._cancel_brackets(st, ad, acts)
        return True

    async def _lab_cancel_one(self, st: DayState, cfg: StrategyCfg, iid: Optional[int], why: str) -> dict:
        acts: list[str] = []
        ad = self.adapters.get(st.account)
        if ad is None:
            return {"ok": st.status not in ("placing", "placed"), "state": "working" if st.status in
                    ("placing", "placed") else "none", "actions": ["account not connected"]}
        if not await self._lab_acked(st):
            return {"ok": False, "state": "working", "actions": ["its orders are not acknowledged yet"]}
        x = self._lab_x(st)
        if x.get("lost") and st.status in ("placed", "live"):
            return {"ok": False, "state": "working", "actions": [LAB_LOST_ACT]}
        ids = {"Buy": st.upper_id, "Sell": st.lower_id}
        asked = [s for s in ("Buy", "Sell") if ids[s] and (iid is None or (x.get("iid") or {}).get(s) == iid)]
        if not asked or st.status not in ("placed", "live"):
            return {"ok": True, "state": "none", "actions": acts}
        seen = {s: "cancelled" for s in asked if s in x["cancelled"]}
        part = 0
        if st.status == "live" and st.entry_side in asked and st.qty and st.entry_qty >= st.qty:
            seen[st.entry_side] = "filled"           # every contract is in: nothing of it is left to cancel
        todo = [s for s in asked if s not in seen]
        res = await asyncio.gather(*(ad.cancel_order_by_id(ids[s]) for s in todo), return_exceptions=True)
        for s, r in zip(todo, res):
            ok = not isinstance(r, Exception) and r.ok
            acts.append(f"cancel entry {ids[s]}: " + ("ok" if ok else str(r if isinstance(r, Exception) else r.error)))
        states = await self._entry_states(ad, [ids[s] for s in todo]) if todo else {}
        # the poll yielded: from here to the end of the block nothing awaits, so what is read is what is written
        done_now = []
        for s in todo:
            status, filled = states[ids[s]]
            got = int(filled or 0) or (int(st.entry_qty or 0) if st.entry_side == s else 0)
            if status == "Filled":
                seen[s] = "filled"                   # the fill beat the cancel: on_fill / the clock take it live
                self.journal("lab_cancel_raced_fill", strategy=st.strategy, account=st.account,
                             round=x.get("round"), iid=(x.get("iid") or {}).get(s), order_id=ids[s],
                             status=status, filled=filled)
            elif status in TERMINAL and got:
                seen[s], part = "part", part + got   # the rest is cancelled; what is in keeps its stop
                self.journal("lab_cancelled", strategy=st.strategy, account=st.account, round=x.get("round"),
                             sides=[s], iids=[(x.get("iid") or {}).get(s)], why=why, ended=False,
                             part=got, actions=list(acts))
            elif status in TERMINAL:
                seen[s] = "cancelled"
                if s not in x["cancelled"]:
                    x["cancelled"].append(s)
                    done_now.append(s)
            else:
                seen[s] = "working"                  # not resolved: the round stays as it is, and it says so
                self.journal("lab_check", strategy=st.strategy, account=st.account, round=x.get("round"),
                             reason=f"entry {ids[s]} not cancelled or filled ({status or 'status unknown'})",
                             actions=list(acts))
        ended = (not self._archived(st) and st.status == "placed"
                 and all(s in x["cancelled"] for s in ("Buy", "Sell") if ids[s]))
        if ended:
            ended = await self._lab_end_unfilled(st, cfg, ad, acts)
            if not ended and st.status == "placed":  # an entry did not read ended with no fill after all
                seen = {s: "working" for s in seen}
        self._lab_save()
        if done_now or ended:
            self.journal("lab_cancelled", strategy=st.strategy, account=st.account, round=x.get("round"),
                         sides=done_now, iids=[(x.get("iid") or {}).get(s) for s in done_now], why=why,
                         ended=ended, actions=acts)
        state = next(k for k in ("working", "part", "filled", "cancelled") if k in seen.values())
        return {"ok": state != "working", "state": state, "actions": acts,
                **({"filled": part} if state == "part" else {})}

    async def lab_cancel(self, name: str, iid: Optional[int] = None, *, why: str = "cancel") -> dict:
        """Cancel a Lab strategy's unfilled entry (its own order id `iid`; None = every unfilled entry) on every
        account with an open round. A cancel "ok" is not cancelled: each entry is read back (3 s at most).
        Ended with no fill -> that leg is cancelled, and a round with no working leg left is done / "cancelled".
        Filled -> nothing more (the position keeps its broker stop). Neither -> the round stays, `lab_check`.
        Never a market order. -> {account: {"ok", "state": "cancelled|filled|working|none", "actions"}}"""
        cfg = self.cfg.strategies.get(name)
        if cfg is None or cfg.kind != LAB:
            return {}
        self._lab_roll()
        rounds = {st.account: st for st in self.day_states(name)
                  if not self._archived(st) and st.status != "idle"}

        async def account(a: str) -> dict:
            return await self._lab_cancel_one(rounds[a], cfg, iid, why)

        got, _ = await self.each_account(rounds, account)
        return {a: (g if isinstance(g, dict) else
                    {"ok": False, "state": "working", "actions": [f"internal error: {type(g).__name__}: {g}"]})
                for a, g in got.items()}

    # --- the capped flatten ---------------------------------------------------------------------------
    def _lab_unconfirmed(self, st: DayState, x: dict, acts: list, reason: str) -> None:
        """The one market-out was refused, or its outcome is not known: "check it". Nothing more is sold for this
        round by the engine; its stop stays. Journaled once (`lab_check`)."""
        acts.append("check it — the close order was not confirmed; its stop is still working")
        if x.get("unconfirmed"):
            return
        x["unconfirmed"], x["why"] = True, LAB_CLOSE_UNCONFIRMED
        self._lab_save()
        try:
            self.journal("lab_check", strategy=st.strategy, account=st.account, round=x.get("round"),
                         reason=reason, actions=list(acts))
        except Exception as e:  # noqa: BLE001
            print(f"homebase engine: journal lab_check failed: {e!r}", file=sys.stderr)

    async def _lab_finish(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter, x: dict, acts: list,
                          reason: str, *, cancel: bool) -> None:
        """The round's position is gone and no exit fill closed it here: done, with no fill price to book
        (`lab_exit_unconfirmed`). cancel: the account read flat just now, so the stop / target go too."""
        st.status, st.exit_reason = "done", reason
        if st.exit_fill is not None and st.pnl is None:
            st.pnl = self._gross_pnl(st, cfg)       # the part whose exit fills were seen
        x["unconfirmed"] = False
        if x.get("why") == LAB_CLOSE_UNCONFIRMED:
            x["why"] = None
        self._lab_mark_check(st, x, "the round ended with no exit fill seen")
        self._lab_stamp(st, x)
        self._save()
        self._lab_save()
        self.journal("lab_exit_unconfirmed", strategy=st.strategy, account=st.account, round=x.get("round"),
                     reason=reason, entered=st.entry_qty, out=st.exit_qty)
        if cancel:
            await self._cancel_brackets(st, ad, acts)

    async def _lab_entries_ended(self, st: DayState, ad: BrokerAdapter, x: dict, acts: list,
                                 unfilled: bool = False) -> bool:
        """R-C: before a round is ended, or its stop / target cancelled, on a position read: every entry of the
        round must READ ended at the broker, now (only one whose every contract was seen filled here is not asked:
        it can fill no more). One that does not: "check it", and the caller ends and cancels nothing. A cancel that
        was accepted is not a cancelled order, and a mark in a file is not a read."""
        for s, i in (("Buy", st.upper_id), ("Sell", st.lower_id)):
            if not i or (st.entry_side == s and st.qty and st.entry_qty >= st.qty):
                continue
            try:
                got = await ad.get_order_state(i) or {}
            except Exception:  # noqa: BLE001 -- unread is not ended
                got = {}
            if got.get("status") not in TERMINAL:
                acts.append(f"check it — entry {i} is not ended at the broker ({got.get('status') or 'status unknown'}); "
                            "nothing is ended or cancelled")
                return False
            if unfilled and (got.get("status") == "Filled" or got.get("filled_qty")):
                acts.append(f"check it — entry {i} filled ({got.get('status')}); nothing is ended or cancelled")
                return False
        return True

    async def _lab_close_retry(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter, x: dict,
                               acts: list) -> dict:
        """A flatten of a round whose ONE market-out already left (or that already read flat): reads only, never
        a second order. Flat for LAB_UNCONFIRMED_S with no exit fill, and every entry read ended -> the round
        ends. Still holding after that, or after a refused close -> "check it", stops left working."""
        def ans(ok: bool) -> dict:
            return {"ok": ok, "sold": 0, "actions": acts}

        now = self._lab_ms()
        if not x.get("close_sent_ms"):               # it read flat with every entry ended: nothing was sent
            if now - int(x.get("gone_ms") or now) < LAB_UNCONFIRMED_S * 1000:
                acts.append("the account is already flat")
                return ans(True)
            if not await self._lab_entries_ended(st, ad, x, acts):
                return ans(False)
            if st.status in ("placed", "live"):
                await self._lab_finish(st, cfg, ad, x, acts, "exit", cancel=False)
            return ans(True)
        try:
            net = int(await ad.get_net_position(cfg.symbol) or 0)
        except Exception as e:  # noqa: BLE001 -- unreadable is NOT flat
            acts.append(f"check it — position unreadable ({e}); stops left working")
            return ans(False)
        if st.status not in ("placed", "live"):
            acts.append("This trade had already ended.")     # its exit fill closed it meanwhile
            return ans(True)
        waited = now - int(x.get("close_sent_ms") or now) >= LAB_UNCONFIRMED_S * 1000
        if net == 0:
            if x.get("unconfirmed") or waited:
                if not await self._lab_entries_ended(st, ad, x, acts):
                    return ans(False)
                if st.status in ("placed", "live"):
                    await self._lab_finish(st, cfg, ad, x, acts, str(x.get("closing") or "flat"), cancel=True)
            else:
                acts.append("the account is already flat")
            return ans(True)
        if not x.get("unconfirmed") and not waited:
            acts.append("the close order is out: waiting for its fill")
            return ans(True)
        self._lab_unconfirmed(st, x, acts, "the close order is out and the position is still there")
        return ans(False)

    async def _lab_entry_states(self, ad: BrokerAdapter, ids: list, quick: bool) -> dict:
        """_entry_states for a flatten asked for by hand (3 s at most). quick, for the clock: LAB_CLOCK_POLLS
        re-reads at most (half a second) -- the clock comes back every 5 s by itself, and every other
        strategy's tick waits for this one."""
        if not quick:
            return await self._entry_states(ad, ids)
        out: dict = {}
        for attempt in range(LAB_CLOCK_POLLS + 1):
            for i in ids:
                if i in out and out[i][0] in TERMINAL:
                    continue
                try:
                    got = await ad.get_order_state(i) or {}
                except Exception:  # noqa: BLE001 -- unknown, asked again
                    got = {}
                out[i] = (got.get("status"), got.get("filled_qty"))
            if all(out[i][0] in TERMINAL for i in ids) or attempt == LAB_CLOCK_POLLS:
                break
            await self._kill_sleep(KILL_POLL_S)
        return out

    async def _lab_flatten_one(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter, reason: str,
                               quick: bool = False) -> dict:
        """Close ONE round's own position (called under the strategy's kill lock). Never more than its own filled
        quantity, only on its side, never the account-wide calls, and ONE market order per round, ever.
          1. cancel every entry not known ended; read each back (3 s at most). One that is neither cancelled
             nor filled -> "check it": nothing sold, stops stay;
          2. own quantity: the round's size for an entry that reads Filled, the broker's filled quantity for one
             cancelled after a part fill, less the exit fills seen. Nothing ever filled -> the round is done /
             "cancelled" and no order is sent;
          3. read the net: unreadable or on the other side -> "check it". Zero -> the stop / target go, the round
             waits for its exit fill;
          4. market out min(|net|, own), text homebase:lab-flat. `closing` is on disk before it leaves. Refused
             -> "check it", stops stay, never sent again;
          5. accepted -> the stop / target are cancelled; the round stays live until the exit fill books it.
        -> {"ok", "sold": contracts, "actions"}"""
        acts: list[str] = []
        x = self._lab_x(st)
        reason = str(reason or "flat")               # never empty: it becomes the round's exit reason

        def ans(ok: bool, sold: int = 0) -> dict:
            return {"ok": ok, "sold": sold, "actions": acts}

        def unsure(why: str) -> dict:
            acts.append(f"check it — {why}; nothing sold; stops left working")
            return ans(False)

        if st.status not in ("placed", "live"):
            return ans(True)
        if x.get("lost"):                            # R-B: nothing is sent or cancelled for a trade whose record is lost
            acts.append(LAB_LOST_ACT)
            return ans(False)
        if x.get("close_sent_ms") or x.get("gone_ms"):
            await self._lab_cancel_entries(st, ad, x, acts)      # a cancel is always safe; never a second close
            return await self._lab_close_retry(st, cfg, ad, x, acts)
        ids = {"Buy": st.upper_id, "Sell": st.lower_id}                     # 1
        held = {"Buy": 0, "Sell": 0}
        ask = []
        bound = False                                # own quantity is the broker's count for a part fill: a lower bound
        for s in ("Buy", "Sell"):
            if not ids[s] or (s in x["cancelled"] and not (st.entry_side == s and st.entry_qty)):
                continue                             # ended with no fill (a mark that the fills contradict is not believed)
            if st.entry_side == s and st.qty and st.entry_qty >= st.qty:
                held[s] = int(st.qty)                # every contract's fill was seen here: it can fill no more
            else:
                ask.append(s)
        res = await asyncio.gather(*(ad.cancel_order_by_id(ids[s]) for s in ask), return_exceptions=True)
        for s, r in zip(ask, res):
            ok = not isinstance(r, Exception) and r.ok
            acts.append(f"cancel entry {ids[s]}: " + ("ok" if ok else str(r if isinstance(r, Exception) else r.error)))
        states = await self._lab_entry_states(ad, [ids[s] for s in ask], quick) if ask else {}
        if st.status not in ("placed", "live"):      # the poll yielded: the round may have ended by itself
            acts.append("This trade had already ended.")
            return ans(True)
        doubt = []
        for s in ask:                                                       # 2
            status, filled = states[ids[s]]
            if status == "Filled":
                held[s] = int(st.qty or 0)
            elif status in TERMINAL and filled:
                held[s], bound = int(filled), True
            elif status in TERMINAL and st.entry_side == s and st.entry_qty:
                doubt.append(f"entry {ids[s]} {status.lower()}, its filled quantity is not known")
            elif status in TERMINAL:
                if s not in x["cancelled"]:
                    x["cancelled"].append(s)
            else:
                doubt.append(f"entry {ids[s]} not cancelled or filled ({status or 'status unknown'})")
        if doubt:
            return unsure("; ".join(doubt))
        if held["Buy"] and held["Sell"]:
            return unsure("both entries filled")
        side = "Buy" if held["Buy"] else "Sell" if held["Sell"] else None
        if side is None:                             # nothing of this round ever filled
            if not await self._lab_end_unfilled(st, cfg, ad, acts):
                if st.status not in ("placed", "live"):      # it ended by itself during the read
                    acts.append("This trade had already ended.")
                    return ans(True)
                return ans(False)
            self._lab_save()
            self.journal("lab_cancelled", strategy=st.strategy, account=st.account, round=x.get("round"),
                         sides=list(x["cancelled"]), iids=list((x.get("iid") or {}).values()), why=reason,
                         ended=True, actions=acts)
            return ans(True)
        if x.get("blind"):
            return unsure("the Desk does not know this trade's stop order and could not cancel it")
        try:                                                                # 3
            net = int(await ad.get_net_position(cfg.symbol) or 0)
        except Exception as e:  # noqa: BLE001 -- unreadable is NOT flat
            return unsure(f"position unreadable ({e})")
        if st.status not in ("placed", "live"):      # the read yielded too: re-checked right before any sale
            acts.append("This trade had already ended.")
            return ans(True)
        if st.status == "placed" or st.entry_side != side:    # the entry is in and its fill push never came
            st.status, st.entry_side = "live", side
            st.entry_anchor = st.upper_px if side == "Buy" else st.lower_px
            st.note = "fill push missed — entry found by the flatten"
            self._save()
        own = held[side] - int(st.exit_qty or 0)
        if own <= 0:                                 # every contract that went in is out again
            await self._close_if_out(st, cfg, ad)
            acts.append("nothing of its own is left to close")
            return ans(True)
        if net == 0:
            acts.append("the account is already flat")
            x["gone_ms"] = self._lab_ms()
            self._lab_save()
            await self._cancel_brackets(st, ad, acts)
            return ans(True)
        if (net > 0) != (side == "Buy"):
            return unsure(f"the account's {net:+d} {cfg.symbol} is not on its side")
        if bound and abs(net) != own:
            # a fill push without its order id is not counted (broker/tradovate.py _count_fill): selling the
            # count and cancelling the stop could leave a contract with nothing behind it
            return unsure(f"the entry was cancelled part filled: {own} counted, the account holds {net:+d} {cfg.symbol}")
        qty, out_side = min(abs(net), own), ("Sell" if side == "Buy" else "Buy")     # 4
        x["closing"], x["close_sent_ms"] = reason, self._lab_ms()
        try:
            self._lab_save(strict=True)              # on disk first: a restart must not send it a second time
        except Exception as e:  # noqa: BLE001 -- nothing was sent
            x["closing"] = x["close_sent_ms"] = None
            return unsure(f"the close could not be written down ({e})")
        try:
            r = await ad.place_order(OrderRequest(symbol=cfg.symbol, side=out_side, qty=qty,
                                                  order_type="Market", text=LAB_FLAT_TEXT))
        except Exception as e:  # noqa: BLE001 -- it may have gone out anyway
            r = OrderResult(ok=False, error=str(e))
        acts.append(f"market {out_side} {qty}: {'ok' if r.ok else r.error}")
        if not r.ok:
            self._lab_unconfirmed(st, x, acts, "the market-out reported failure")
            return ans(False)
        x["close_ok"], x["close_id"] = True, r.order_id
        self._lab_save()
        if st.status not in ("placed", "live"):      # the send yielded: the round's own stop / target ended it
            acts.append(f"the round ended while the close was sent ({st.exit_reason})")
            return ans(True, qty)                    # nothing is cancelled; the settle sees a double exit
        await self._cancel_brackets(st, ad, acts)                           # 5
        return ans(True, qty)

    async def lab_flatten(self, name: str, *, reason: str = "flat") -> dict:
        """Close a Lab strategy's OWN position on every account with an open round (see _lab_flatten_one), under
        the strategy's kill lock, the accounts side by side. `reason` becomes the round's exit reason when its
        exit fill arrives. -> {account: {"ok", "sold", "actions"}}; journals `lab_flatten`."""
        cfg = self.cfg.strategies.get(name)
        if cfg is None or cfg.kind != LAB:
            return {}
        reason = str(reason or "flat")
        self._lab_roll()
        async with self._kill_lock(name):
            rounds = {st.account: st for st in self.day_states(name)     # read INSIDE the lock
                      if not self._archived(st) and st.status != "idle"}

            async def account(a: str) -> dict:
                st = rounds[a]
                ad = self.adapters.get(a)
                if ad is None:
                    return {"ok": st.status not in ("placing", "placed", "live"), "sold": 0,
                            "actions": ["account not connected"]}
                if not await self._lab_acked(st):
                    return {"ok": False, "sold": 0, "actions": ["check it — its orders are not acknowledged yet"]}
                return await self._lab_flatten_one(st, cfg, ad, reason)

            got, _ = await self.each_account(rounds, account)
            results = {a: (g if isinstance(g, dict) else
                           {"ok": False, "sold": 0, "actions": [f"internal error: {type(g).__name__}: {g}"]})
                       for a, g in got.items()}
            if results:
                self._save()
                self._lab_save()
                self.journal("lab_flatten", strategy=name, reason=reason, results=results)
        return results

    # --- hooks 6 and 8: a Kill never sends a second market order for a round whose close is out ------
    def _lab_close_sent(self, st: DayState) -> bool:
        """An open round the global Kill's per-strategy pass leaves to its own account sweep: its ONE market-out
        has been sent (accepted, refused or unknown), or its record was lost (hands off)."""
        if st.status not in ("placed", "live"):
            return False
        x = self._lab_x(st)
        return bool(x.get("close_sent_ms") or x.get("lost"))

    def _lab_hands_off(self, st: DayState) -> bool:
        """A round the per-strategy Kill takes through its Lab path: its close is out (or may be), or it read flat
        with its entries ended (a position on the account now is not its own), or it is filed away (I-4), or
        the Desk does not know its stop order, or its record was lost."""
        if self._archived(st):
            return True
        x = self._lab_x(st)
        return st.status in ("placed", "live") and bool(
            x.get("close_sent_ms") or x.get("gone_ms") or x.get("blind") or x.get("lost"))

    async def _lab_cancel_entries(self, st: DayState, ad: BrokerAdapter, x: dict, acts: list) -> None:
        """Cancel the round's entries that are not known ended. Never an order that could open or close anything."""
        for s, i in (("Buy", st.upper_id), ("Sell", st.lower_id)):
            if not i or s in x["cancelled"] or (st.entry_side == s and st.qty and st.entry_qty >= st.qty):
                continue
            try:
                r = await ad.cancel_order_by_id(i)
            except Exception as e:  # noqa: BLE001
                r = OrderResult(ok=False, error=str(e))
            acts.append(f"cancel entry {i}: " + ("ok" if r.ok else str(r.error)))

    async def _lab_kill_readonly(self, st: DayState, cfg: StrategyCfg, account: str) -> dict:
        """The per-strategy Kill's Lab path (hook 8).
          a carried block            nothing is sent: "check it";
          a close that is (or may be) out, or a round that read flat
                                     cancel its unfilled entries, read, "check it". Never a market order, never
                                     _kill_state;
          a stop order the Desk does not know (and no close sent)
                                     the Kill closes the position as a Kill does (_kill_state, unchanged), and
                                     its answer is ok False: that stop may still be working at the broker."""
        acts: list[str] = []
        if self._archived(st):
            return {"ok": False, "actions": ["check it — an earlier trade of this strategy is not resolved on this "
                                             "account; nothing is sent"]}
        x = self._lab_x(st)
        if x.get("lost"):                            # R-B: hands off -- nothing is cancelled, nothing is sent
            return {"ok": False, "actions": [LAB_LOST_ACT]}
        ad = self.adapters.get(account)
        if ad is None:
            return {"ok": False, "error": "account not connected", "actions": acts}
        if not (x.get("close_sent_ms") or x.get("gone_ms")):     # blind, no close sent
            res = await self._kill_state(st, cfg, ad)
            acts = list(res["actions"]) + ["check it — this trade's stop order is unknown to the Desk and may still "
                                           "be working"]
            try:
                self.journal("lab_check", strategy=st.strategy, account=account, round=x.get("round"),
                             reason="a kill of a round whose stop order the Desk does not know", actions=acts)
            except Exception as e:  # noqa: BLE001
                print(f"homebase engine: journal lab_check failed: {e!r}", file=sys.stderr)
            return {"ok": False, "acted": True, "actions": acts}
        await self._lab_cancel_entries(st, ad, x, acts)
        await self._lab_close_retry(st, cfg, ad, x, acts)        # reads only; ends the round if the account is flat
        if st.status in ("placed", "live") and not any(a.startswith("check it") for a in acts):
            acts.append("check it — its close order is already out; nothing more is sold")
        return {"ok": st.status not in ("placed", "live"), "acted": True, "actions": acts}

    # --- hook 5: the Desk's "Flatten & turn off" --------------------------------------------------
    async def _lab_flatten_strategy(self, name: str) -> dict:
        """flatten_strategy for kind lab: the capped flatten, answered in flatten_strategy's own shape
        ({account: [actions]}) and journaled as `manual_flatten`."""
        t0 = self._perf()
        results = {a: r["actions"] for a, r in (await self.lab_flatten(name, reason="manual_flat")).items()}
        self.journal("manual_flatten", strategy=name, results=results,
                     flatten_ms={"total": round((self._perf() - t0) * 1000, 1)})
        return results

    # --- hook 7: the clock, for the open round only -----------------------------------------------
    async def _lab_tick_flat(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter, x: dict, key: str) -> None:
        """The clock's capped flatten: every LAB_FLAT_RETRY_S (a "check it" close: LAB_CHECK_RETRY_S), and only
        when the strategy's kill lock is free -- a Kill or a flatten in progress is never waited for here, so
        another strategy's tick on this account is not held up behind it."""
        said = self.__dict__.setdefault("_lab_said", {})
        if not ad.connected:                         # nothing is sent blind: the one close is not used up
            if said.get(f"wait:{key}") != x.get("round"):
                said[f"wait:{key}"] = x.get("round")
                self.journal("clock_flat_waiting", strategy=st.strategy, account=st.account,
                             round=x.get("round"), reason="account not connected")
            return
        gap = LAB_CHECK_RETRY_S if x.get("unconfirmed") else LAB_FLAT_RETRY_S
        rk = f"flat:{key}"
        lock = self._kill_lock(st.strategy)
        if time.time() - self._retry_at.get(rk, 0.0) < gap or lock.locked():
            return
        self._retry_at[rk] = time.time()
        t = self._perf()
        async with lock:                             # free: taken at once, with no wait
            res = await self._lab_flatten_one(st, cfg, ad, "flat", quick=True)
        self._save()
        self._lab_save()
        told = ("ok", x.get("round")) if res["ok"] else ("failed", x.get("round"), tuple(res["actions"]))
        if said.get(rk) == told or (res["ok"] and not res["actions"]):
            return                                   # said already: one line per round that closed, one per new failure
        said[rk] = told
        self.journal("clock_flat" if res["ok"] else "clock_flat_failed", strategy=st.strategy,
                     account=st.account, actions=res["actions"],
                     flat_ms=round((self._perf() - t) * 1000, 1))      # timing only

    async def _lab_tick(self, st: DayState, cfg: StrategyCfg, ad: BrokerAdapter, now: dt.time) -> None:
        """One clock tick of a Lab strategy's OPEN round (an archived one is never acted on: I-4).
          placed, before flat_et      the order-status backstop for a missed fill push (_guard_placed)
          placed or live at flat_et   the capped flatten (never a "check it" run of a killed strategy)
          a close already under way   read again every 5 s, also before flat_et; never a second order
          live with exit fills        is the trade over? (_close_if_out)
          live or done, a sibling     is the other entry really gone? (_guard_sibling)
          done or error               are its orders all ended? (_lab_settle)"""
        if self._archived(st):
            if self._lab_carried(st):
                await self._lab_carry_check(st, cfg, ad, self._lab_x(st))
            return
        if st.status == "idle":
            return
        x = self._lab_x(st)
        if self._lab_stamp(st, x):
            self._lab_save()
        if x.get("lost"):
            # R-B: this trade's record was lost. The clock does nothing of the Lab's with it: no flat time, no
            # capped flatten, no cancel, no settle. L-1: ONE thing stays, and it is the engine's own -- while it is
            # placed, before the flat time and with the adapter connected, the order-status backstop that adopts a
            # fill whose push was missed and cancels the pair's other entry, exactly as a healthy placed round has it
            if st.status == "placed" and now < _hhmm(cfg.flat_et) and ad.connected:
                await self._guard_placed(st, cfg, ad, check_position=False, event="entry_found_by_check",
                                         note="fill push missed — entry found by the order-status check")
            return
        await self._lab_hints(st, ad, x)             # O-1: what the file said was cancelled, read at the broker
        key = f"{st.strategy}@{st.account}"
        check_it = self.needs_check(st)              # killed today and still placed / live: a human's job
        if check_it:
            self._journal_needs_check(st, cfg, now)
        late = now >= _hhmm(cfg.flat_et)
        closing = bool(x.get("close_sent_ms") or x.get("gone_ms"))
        if st.status == "placed" and not late and not closing:
            if ad.connected:       # a dead socket's cache is stale; reconnect reconciles
                await self._guard_placed(st, cfg, ad, check_position=False, event="entry_found_by_check",
                                         note="fill push missed — entry found by the order-status check")
        elif st.status in ("placed", "live") and (closing or (late and not check_it)):
            await self._lab_tick_flat(st, cfg, ad, x, key)
        elif st.status == "placed" and late:
            # a killed "check it" run: its entries are still cancelled at the flat time (once); it is never
            # flattened by the clock (as the clock above does for every other kind)
            k = (st.date, st.strategy, st.account)
            if k not in self._check_it_cancelled:
                self._check_it_cancelled.add(k)
                acts = []
                for oid in (st.upper_id, st.lower_id):
                    if oid:
                        r = await ad.cancel_order_by_id(oid)
                        acts.append(f"cancel {oid}: " + ("ok" if r.ok else str(r.error)))
                self.journal("killed_run_entries_cancelled", strategy=st.strategy, account=st.account,
                             actions=acts)
        if st.status == "live" and st.exit_qty and ad.connected:
            await self._close_if_out(st, cfg, ad)   # out, and the rest of the entry was cancelled
        if st.status in ("live", "done") and st.entry_side and ad.connected:
            other = "Sell" if st.entry_side == "Buy" else "Buy"
            if (st.lower_id if st.entry_side == "Buy" else st.upper_id) and other not in x["cancelled"]:
                status = await self._guard_sibling(st, cfg, ad)
                if status in TERMINAL and status != "Filled":
                    x["cancelled"].append(other)     # read ended: never asked again
                    self._lab_save()
        if st.status in ("done", "error"):
            await self._lab_settle(st, cfg, ad)

    # --- (the Lab methods end here) ---


# ---- the Lab section, module level --------------------------------------------------------------------
LAB = "lab"                                    # StrategyCfg.kind
LAB_FLAT_TEXT = "homebase:lab-flat"            # the capped market-out's order text
LAB_FLAT_RETRY_S = 5.0                         # the flat time's retry (cancels and reads only)
LAB_CHECK_RETRY_S = 30.0                       # ... once a round is "check it"
LAB_SETTLE_S = 2.0                             # a closed round's orders are re-read this often
LAB_SETTLE_FAST = 5                            # ... for this many reads, then every LAB_CHECK_RETRY_S
LAB_UNCONFIRMED_S = 5.0                        # a close with no exit fill is given this long
LAB_CLOCK_POLLS = 2                            # the clock's flatten re-reads an entry this often (250 ms apart)
# The sentences the owner reads (design, section E). The door's own are repeated here so the engine never
# imports the runner's code; tests/test_engine_lab.py holds them equal.
LAB_NOT_ON_DESK = "That strategy is not on the Desk."
LAB_OFF = "It is off."
LAB_KILLED = "Killed today."
LAB_DISARMED = "The desk is disarmed: written down only."
LAB_NOT_CONNECTED = "The account is not connected."
LAB_ACCOUNT_STOPPED = "This account is stopped for the day."
LAB_TAKE_RULE = "This account has a daily take rule. A Lab strategy cannot share it."
LAB_ONE_AT_A_TIME = "One position at a time."
LAB_CANNOT_CHECK = "The Desk cannot check the last trade's orders."
LAB_CLOSE_UNCONFIRMED = "Check it: the close order was not confirmed. Its stop is still working."
LAB_EXIT_TWICE = "Check it: this trade's exit may have filled twice."
LAB_NO_POSITION_READ = "The Desk cannot read this account's position."
LAB_NO_STOP_ID = "Check it: the Desk does not know this trade's stop order."
LAB_BAD_RECORD = "The Desk cannot read yesterday's record for this account."
LAB_OLD_ORDER_WORKING = "An old order of this trade is still working. Cancel it first."
LAB_LOST_ACT = "check it — this trade's record was lost: nothing is sent or cancelled for it"
LAB_NET_AGAIN_MS = 2000                        # a position read that disagrees counts again after this long (M2)
LAB_ID_FIELDS = ("upper_id", "lower_id", "up_sl_id", "up_tp_id", "dn_sl_id", "dn_tp_id")
LAB_NO_BLOCK = "This account has no block to clear."
# The ONLY failures of a single entry that leave its round clean: the adapters' own fixed phrases for a path that
# sends nothing, or for a broker answer that carries no order (homebase/broker/). Everything else is unknown.
LAB_CLEAR_REJECTS = (
    "adapter not connected",                                        # tradovate.py place_bracket / place_order: no socket
    "OSO rejected (no orderId returned)",                           # tradovate.py place_bracket: answered, no order
    "order rejected (no orderId returned)",                         # tradovate.py place_order: answered, no order
    "a Stop Limit order needs both a limit price and a trigger",    # tradovate.py STOPLIMIT_INCOMPLETE: not sent
    "bracketed stop entries need a broker OSO",                     # base.py place_bracket (legged fallback): not sent
)
LAB_BAD_ORDER = "The Desk cannot check this order."
LAB_NO_STOP = "Every entry needs a stop held at the broker."
LAB_WRONG_SIDE = "The stop must sit on the losing side of the entry."
LAB_NOT_A_PAIR = "Only a buy-stop and sell-stop pair can be linked."
LAB_TOO_LATE = "Too late for a new trade today."
LAB_NOT_WRITTEN = "The Desk could not write this trade down. Nothing was sent."
# A refused entry whose words say the answer never came: the order may exist at the broker (broker/tradovate.py
# place_bracket: "incl. a timeout, where the OSO may exist"). Such a round is never clean.
LAB_UNKNOWN_WORDS = ("oso failed", "timeout", "timed out", "unreachable", "outcome unknown")


@dataclass
class LabLeg:
    """One entry of a Lab strategy, as the engine places it. Duck-types rules.Signal for _place_one."""
    iid: int                            # the strategy's own order id
    side: str                           # "Buy" | "Sell"
    entry: str                          # "Market" | "Stop"
    entry_price: Optional[float]
    sl_px: float
    tp_px: Optional[float]              # None = no target order
    tp_rr: Optional[float]
    ref_px: Optional[float]
    move: bool = False                  # move_brackets_to_fill
