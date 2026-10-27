"""The account day rules: day books (closed P&L, day_take / day_lock / target_take, eval standing) and the take checks.

Engine (engine.py) inherits DayRulesMixin; the methods moved here from engine.py unchanged. They read the Engine's
cfg, adapters, states, books, balance_history, _root, _today, _take_seen, _mono, journal, _save and the kill/flatten
methods, and own self.books (set in Engine.__init__, kept in <state>/daybook-<date>.json)."""
from __future__ import annotations

import asyncio
import json
import sys
from typing import Optional

from ..broker.base import BrokerAdapter
from ..config import StrategyCfg, assignments
from ..contracts import point_value
from .dayrules import LOCK_LOCK, LOCK_TAKE, DayBook, DayRules, merge_rules, standing, take_level
from .daystate import DayState

TAKE_GRACE_S = 2.0      # a day_take touch the resting limit has not filled for this long is market-flattened


class DayRulesMixin:
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
        acct = self.cfg.accounts.get(account)
        own = float(getattr(acct, "day_lock", 0.0) or 0.0)         # the account's own (group) day take
        if own > 0:
            rs.append(DayRules(0.0, own, False))
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
                    from ..backtest.propsim import load_rules
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

    def day_view(self, account: str) -> dict:
        """What the account's day stands at, for the page: the day take in force, the day's closed net P&L, the lock.
        Reads only (a day that has not started has no book: zeros)."""
        b = self.books.get(account)
        today = b is not None and b.date == self._today()
        return {"day_lock": self.rules_for(account).day_lock, "closed_net": b.closed_net if today else 0.0,
                "closes": b.closes if today else 0, "locked": b.locked if today else None}

    async def apply_day_lock(self, account: str) -> Optional[str]:
        """The account's day take was just set or lowered: a day whose closed P&L is already at it locks NOW (a lock
        is otherwise taken when a trade closes). A lock already taken stays for the day -- never lifted here.
        -> the lock in force (None: none)."""
        b = self.books.get(account)
        if b is None or b.date != self._today():
            return None
        rules = self.rules_for(account)
        if not b.locked and b.closes and rules.day_lock and b.closed_net >= rules.day_lock - 1e-9:
            await self._lock_account(account, LOCK_LOCK, why="the day take was set at or below the day's closed P&L")
        return b.locked

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
