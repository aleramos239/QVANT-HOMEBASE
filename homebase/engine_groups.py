"""Account cycle groups (the owner, 2026-10-25): "a system where i can add group strategies and accounts where it runs
and trades on the accounts one at a time in a cycle".

A group is a set of Lab strategies and a set of accounts that share ONE take-turns pointer: every entry of any member
goes to the next account of the group (in the group's order) that can take it -- an account still in a trade passes
the turn on, so two trades may be open at once but only on separate accounts. Never a long on one of its accounts
while a short is open or working on another (the owner: "we can trade multiple accounts at once but we can [not]
enter long and short on another"; Apex: no hedging across accounts): such an entry is skipped and the turn does not
move. With `risk_usd` set, every member's order is sized to that many dollars at its own stop (labdesk._group_size),
never above `max_minis` full contracts' worth (labdesk.GROUP_NO_SIZE when not one contract fits).

Off by default. Kept in <state>/groups.json (atomic, NOT per day: the turn carries to the next day). Only Lab
strategies; a strategy is in one group at most. A member's accounts must still be booked to it on the Desk: an account
of the group the member is not booked on is simply not in its turn."""
from __future__ import annotations

import json
import re
import sys
from typing import Optional

from .engine_lab import GROUP_HEDGE, LAB, LAB_BAD_ORDER

GROUP_NONE = "No account of its group could take this trade."
GROUP_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,39}")
MAX_GROUPS = 12
MAX_NAME = 40
RISK_MOST = 100_000.0
MINIS_MOST = 100
MINIS_DEFAULT = 17             # Apex 300K PA: half size (17 minis = 170 micros) until the account is past +$7,600


class GroupError(ValueError):
    """A refusal in words the page may show."""


def _opposite(open_sides: set, new_sides: set) -> bool:
    """A new entry on `new_sides` ({"Buy"}, {"Sell"} or a pair's both) against what is open or working: any side
    that differs is a hedge (a pair meets anything open; anything meets a working pair)."""
    return any(o != n for o in open_sides for n in new_sides)


class GroupMixin:
    # --- the file ---------------------------------------------------------------------------------------------
    def _groups_path(self):
        return self._root / "groups.json"

    def _load_groups(self) -> None:
        self.groups = {}
        p = self._groups_path()
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text())
            for gid, g in (data.items() if isinstance(data, dict) else ()):
                if GROUP_ID_RE.fullmatch(str(gid)) and isinstance(g, dict):
                    self.groups[gid] = {"name": str(g.get("name") or gid)[:MAX_NAME],
                                        "members": [m for m in g.get("members") or [] if isinstance(m, str)],
                                        "accounts": [a for a in g.get("accounts") or [] if isinstance(a, str)],
                                        "risk_usd": float(g.get("risk_usd") or 0.0),
                                        "max_minis": int(g.get("max_minis") or MINIS_DEFAULT),
                                        "on": g.get("on") is True,
                                        "last": g.get("last") if isinstance(g.get("last"), str) else None}
        except Exception as e:  # noqa: BLE001 -- the desk must still start (every group reads off)
            self.groups = {}
            print(f"homebase engine: reading {p.name} failed: {e!r}", file=sys.stderr)

    def _save_groups(self) -> None:
        p = self._groups_path()
        tmp = p.with_suffix(".tmp")                   # never half a file: a lost switch would trade every account
        tmp.write_text(json.dumps(self.groups, indent=2) + "\n")
        tmp.replace(p)

    # --- reads ------------------------------------------------------------------------------------------------
    def group_of(self, name: str) -> Optional[tuple]:
        """(group id, group) of the ON group `name` is a member of, else None (an off group changes nothing)."""
        for gid, g in self.groups.items():
            if g["on"] and name in g["members"]:
                return gid, g
        return None

    def group_turn(self, g: dict) -> list:
        """The group's accounts in its order, starting after the one that took the last trade (wrapping)."""
        accts = list(g["accounts"])
        i = accts.index(g["last"]) + 1 if g.get("last") in accts else 0
        return accts[i:] + accts[:i]

    def groups_view(self) -> dict:
        return {gid: {**{k: v for k, v in g.items() if k != "last"},
                      "next": (self.group_turn(g) or [None])[0] if g["on"] else None}
                for gid, g in self.groups.items()}

    def group_open_sides(self, g: dict, symbol: str) -> set:
        """"Buy" / "Sell" of every trade in `symbol`'s market that is open, or whose entry is working, on any of the
        group's accounts today -- the desk's own rounds (any strategy, member or not) and, where the adapter keeps
        one, the broker's cached positions. A working entry whose side cannot be read counts as both."""
        today = self._today()

        def broker(a: str):
            return getattr(self.adapters.get(a), "broker_key", a)

        keys = {broker(a) for a in g["accounts"]}
        sides: set = set()
        for s in self.states.values():
            if s.date != today or s.status == "idle" or broker(s.account) not in keys:
                continue
            so = self.cfg.strategies.get(s.strategy)
            if so is not None and not self._same_market(so.symbol, symbol):
                continue
            went_in = (s.entry_qty or s.qty or 0) if s.entry_side else 0
            if s.entry_side and (s.exit_qty or 0) < went_in:
                sides.add(s.entry_side)                       # a position is open
            elif s.status in ("placing", "placed") and not s.entry_side:
                got = set((self._lab_x(s).get("iid") or {}).keys()) if so is not None and so.kind == LAB else set()
                sides |= got or {"Buy", "Sell"}               # an entry is working
        for a in g["accounts"]:
            ad = self.adapters.get(a)
            try:
                view = ad.trade_view() if ad is not None else None
            except Exception:  # noqa: BLE001 -- a cache that cannot be read adds nothing; the rounds above still count
                view = None
            for p in (view or {}).get("positions") or []:
                if p.get("symbol") and self._same_market(p["symbol"], symbol) and p.get("net"):
                    sides.add("Buy" if p["net"] > 0 else "Sell")
        return sides

    def group_hedged(self, g: dict, symbol: str, legs: list) -> bool:
        return _opposite(self.group_open_sides(g, symbol), {leg.side for leg in legs})

    # --- the switch and the settings ----------------------------------------------------------------------------
    def set_group(self, gid: str, body: dict) -> dict:
        """Create or change one group from the page's form. Every field is checked; nothing is half written."""
        if not isinstance(gid, str) or not GROUP_ID_RE.fullmatch(gid):
            raise GroupError("A group id is lowercase letters, digits, - or _.")
        if gid not in self.groups and len(self.groups) >= MAX_GROUPS:
            raise GroupError(f"At most {MAX_GROUPS} groups.")
        old = self.groups.get(gid, {})
        name = body.get("name", old.get("name") or gid)
        members = body.get("members", old.get("members", []))
        accounts = body.get("accounts", old.get("accounts", []))
        risk = body.get("risk_usd", old.get("risk_usd", 0.0))
        minis = body.get("max_minis", old.get("max_minis", MINIS_DEFAULT))
        on = body.get("on", old.get("on", False))
        if not isinstance(name, str) or not name.strip() or len(name) > MAX_NAME:
            raise GroupError(f"A name of 1 to {MAX_NAME} characters.")
        if not isinstance(members, list) or not all(isinstance(m, str) for m in members) \
                or len(set(members)) != len(members):
            raise GroupError("Members: a list of strategies, each once.")
        for m in members:
            s = self.cfg.strategies.get(m)
            if s is None or s.kind != LAB:
                raise GroupError(f"{m} is not a Lab strategy on this Desk.")
            for other, g in self.groups.items():
                if other != gid and m in g["members"]:
                    raise GroupError(f"{m} is already in the group {g['name']}.")
        if not isinstance(accounts, list) or not all(isinstance(a, str) for a in accounts) \
                or len(set(accounts)) != len(accounts):
            raise GroupError("Accounts: a list of accounts, each once.")
        for a in accounts:
            if a not in self.cfg.accounts:
                raise GroupError(f"{a} is not an account on this Desk.")
        if isinstance(risk, bool) or not isinstance(risk, (int, float)) or not 0 <= risk <= RISK_MOST:
            raise GroupError(f"Risk per trade: a dollar amount from 0 to {RISK_MOST:,.0f} (0 = each strategy's own size).")
        if isinstance(minis, bool) or not isinstance(minis, int) or not 1 <= minis <= MINIS_MOST:
            raise GroupError(f"Most per trade: 1 to {MINIS_MOST} full contracts.")
        if not isinstance(on, bool):
            raise GroupError("on must be true or false.")
        if on and (not members or not accounts):
            raise GroupError("A group needs a strategy and an account before it can go on.")
        self.groups[gid] = {"name": name.strip(), "members": members, "accounts": accounts, "risk_usd": float(risk),
                            "max_minis": minis, "on": on,
                            "last": old.get("last") if old.get("last") in accounts else None}
        self._save_groups()
        self.journal("group_set", group=gid, **{k: v for k, v in self.groups[gid].items() if k != "last"})
        return self.groups_view()[gid]

    def delete_group(self, gid: str) -> None:
        if gid not in self.groups:
            raise GroupError("No such group.")
        del self.groups[gid]
        self._save_groups()
        self.journal("group_deleted", group=gid)

    # --- an entry ---------------------------------------------------------------------------------------------
    async def _group_enter(self, grp: tuple, name: str, cfg, legs: list, sizes: dict, max_rounds: int,
                           source: str, t0: float) -> dict:
        """lab_enter for a member of an ON group: the first account of the group, in turn, that opens a round takes
        it (one that sits out passes the turn on). An entry opposite to a trade open on any of the group's accounts
        is refused whole: no account is asked and the turn stays."""
        gid, g = grp

        def hedge() -> dict:
            self.journal("group_hedge_skipped", group=gid, strategy=name, sides=sorted({x.side for x in legs}),
                         open=sorted(self.group_open_sides(g, cfg.symbol)))
            return {"armed": bool(self.cfg.armed), "reason": GROUP_HEDGE,
                    "accounts": {a: {"ok": False, "round": None, "reason": GROUP_HEDGE} for a in sizes}}

        if self.group_hedged(g, cfg.symbol, legs):
            return hedge()
        tried = {}
        for a in (a for a in self.group_turn(g) if a in sizes):
            try:
                tried[a] = await self._lab_enter_one(name, a, sizes[a], legs, max_rounds, source, t0)
                went = tried[a].get("round") is not None
            except Exception:  # noqa: BLE001 -- the outcome is unknown: the turn is that account's, no other is asked
                tried[a], went = {"ok": False, "round": None, "reason": LAB_BAD_ORDER}, True
            if not went and tried[a].get("reason") == GROUP_HEDGE:
                return hedge()                       # a trade opened elsewhere in the group while this one waited
            if went:
                g["last"] = a
                self._save_groups()
                break
        else:
            self.journal("group_skipped", group=gid, strategy=name, reason=GROUP_NONE,
                         accounts={a: r.get("reason") for a, r in tried.items()})
        return {"armed": bool(self.cfg.armed), "accounts": tried}
