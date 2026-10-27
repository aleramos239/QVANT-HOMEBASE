"""Flatten and Kill: the exits that run per account side by side (each_account), the per-strategy Kill and its locks.

Engine (engine.py) inherits KillMixin; the methods moved here from engine.py unchanged. They read the Engine's cfg,
adapters, states, _killed, _kill_locks, _kill_sleep, _perf, journal, _save, _state and the Lab hooks."""
from __future__ import annotations

import asyncio
import contextlib
import sys
from typing import Optional

from ..broker.base import BrokerAdapter, OrderRequest
from ..config import StrategyCfg, assignments
from .daystate import KILL_POLL_N, KILL_POLL_S, MARKET_OUT_FAILED, TERMINAL, WORKING, DayState

# Accounts whose exits run side by side (each_account). A bound, not "all at once": the broker caps a
# login's requests per second / minute / hour (values unpublished), a 429 is never retried on the order
# path, and several desk entries ride one login. 4 accounts x (6 cancels at once) = 24 requests out
# together at most.
EXIT_CONCURRENCY = 4


class KillMixin:
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

    async def flatten_today(self, account: Optional[str] = None, reason: str = "killed",
                            close: bool = True) -> dict:
        """Kill switch: every strategy's footprint today, proven calls only. The
        accounts go side by side (each_account); one account's runs go one after
        another, in today's order -- _flatten_state sells the account's WHOLE net
        in a symbol. A run that raises is reported in its own actions; every
        other run still goes.
        `account`: that account's runs only (the Desk's per-account Flatten), ended
        with exit_reason `reason`. close=False: read and cancel each run's orders,
        never the market-out -- the caller's account sweep closes the positions at
        the broker (liquidateposition), so a stale read can never sell twice and
        flip a position (2026-10-23)."""
        states = [st for st in self.states.values() if account is None or st.account == account]
        by_account: dict[str, list[DayState]] = {}
        for st in states:
            by_account.setdefault(st.account, []).append(st)

        def lab_sym(st: DayState) -> Optional[str]:
            c = self.cfg.strategies.get(st.strategy)
            return str(c.symbol).upper() if c is not None and c.kind == "lab" else None

        async def account(a: str) -> dict:
            acts: dict = {}
            # a GROUP of Lab strategies shares the account: its net in a contract is sold ONCE, by the member whose
            # round is open -- or, with none open, by the first; a member's round that is over and checked is
            # then left out (it holds nothing, and a second read of the net could sell it twice)
            sold = {lab_sym(s) for s in by_account[a] if lab_sym(s) is not None and s.date == self._today()
                    and s.status in ("placing", "placed", "live") and not self._archived(s)}
            for st in by_account[a]:
                key = f"{st.strategy}@{st.account}"
                try:
                    cfg = self.cfg.strategies.get(st.strategy)
                    ad = self.adapters.get(st.account)
                    if cfg is None or ad is None or st.date != self._today() \
                            or st.status == "idle" or self._archived(st) \
                            or (cfg.kind == "lab" and self._lab_close_sent(st)) \
                            or (cfg.kind == "lab" and st.status == "done" and lab_sym(st) in sold
                                and self._lab_clean(st)):
                        continue
                    if cfg.kind == "lab":
                        sold.add(lab_sym(st))
                    flat, acts[key] = await self._flatten_state(st, cfg, ad, close=close)
                    if flat and st.status in ("placing", "placed", "live"):
                        st.status, st.exit_reason = "done", reason
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
                             ad: BrokerAdapter, close: bool = True) -> tuple[bool, list[str]]:
        """Close ONE strategy's footprint on one account using only calls
        proven live (position read, market order, single cancels). Market out
        of the net position FIRST — the stop/target keep protecting until the
        position is gone — then cancel every order this strategy placed: both
        entries and both legs' stop/target (GTC: a leftover could open a new
        position days later). Position unreadable or the market order refused
        -> NOTHING is cancelled; the stop/target stay working. close=False: the
        read and the cancels, never the market-out (flatten_today's close=False)."""
        acts: list[str] = []
        try:
            net = await ad.get_net_position(cfg.symbol)
        except Exception as e:  # noqa: BLE001 — unreadable is NOT flat
            return False, [f"position unreadable ({e}) — stop/target left working"]
        if net and close:
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
