"""One Set-up save for a team or a solo strategy (owner, 2026-11-02: "easy to set up impossible to get confused and mess it up").

A team is one record, kept by the Desk (engine_groups.py, <state>/groups.json); "team": "" makes a new one. A solo strategy
is one Lab strategy on its own accounts. The page sends the whole set-up in one call. It is checked as a whole first (one
refusal, nothing written), then written in a safe order: the account group -> each strategy's accounts (the final rows at once, so a book is never emptied on the way)
-> Take turns -> each strategy ON or OFF (OFF ends its day first, as the Desk's own switch does).

Rules built in: a team member is booked ONLY on its team's accounts (split: only its own one); a strategy that leaves a team
loses the team's accounts; the account group is on whenever it has a strategy and an account (the one switch the owner
sees is Trading ON / OFF, every member's own); Team OFF ends each member's Take turns, ON in Take turns mode starts it
again; a member of another team leaves that team in the same Save (its book is written once, from the new team). A team
drops the per-account extras (size per account, stop after, most; owner, 2026-11-02) and keeps only each row's contract;
Hold overnight stays, one choice per strategy. A solo save keeps every row's size / risk / most / contract and takes new ones from `settings`."""
from __future__ import annotations

import contextlib

from fastapi import HTTPException, Request

from ..desk import labdesk as labdesk_mod, variants
from ..desk.engine_groups import GroupError
from .strategies import book_rows, short

IN_TEAM = "It is in the team {}: set it up on the team's page."
IN_SET = "It is in the set {}: set it up on the set's page."
QTY = "Contracts: a whole number above 0."


def _whole(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 1


def _settings(body: dict) -> dict:
    """The gear's {account: {qty?, size?, ...}}, checked: a qty that is sent is a whole number above 0 (book_rows drops a row of 0)."""
    settings = body.get("settings") or {}
    if not isinstance(settings, dict) or not all(isinstance(v, dict) for v in settings.values()):
        raise HTTPException(400, "settings: a dict of settings for each account.")
    if not all(_whole(v["qty"]) for v in settings.values() if v.get("qty") is not None):
        raise HTTPException(400, QTY)
    return settings


def _cur(cfg, name: str) -> list:
    """`name`'s rows on this Desk's accounts, as the book holds them."""
    return [dict(r) for r in cfg.book.get(name) or [] if r.get("account") in cfg.accounts]


KEPT = ("size", "risk_usd", "most", "contract", "stop_after")


def _rows(cur: list, accounts: list, hold, qty=None, settings=None) -> list:
    """Rows on `accounts`: a booked account keeps its own qty (unless the gear's `settings` change it), a new one gets `qty` or 1; Hold overnight as `hold` (None: a booked row keeps its own, a new one is held as the strategy holds now). A solo save (`settings` a dict, maybe empty) also keeps each row's size / risk / most / contract
    and lets `settings[account]` change them (and qty); a team (None) keeps only the contract, its own size rules win."""
    by = {r["account"]: r for r in cur}
    h = any(r.get("hold") is True for r in cur) if hold is None else hold is True
    out = []
    for a in accounts:
        old, new = by.get(a) or {}, (settings or {}).get(a) or {}
        h_a = h if hold is not None or a not in by else old.get("hold") is True      # None: a booked row keeps ITS OWN hold (never spread to the others)
        row = {"account": a, "qty": int(new.get("qty") or old.get("qty") or qty or 1)}
        for k in KEPT if settings is not None else ("contract",):
            v = new.get(k, old.get(k))
            if v is not None:
                row[k] = v
        out.append({**row, **({"hold": True} if h_a else {})})
    return out


def team_books(cfg, old: dict, new: dict, hold: dict | None = None) -> dict:
    """{strategy: rows} for the books a team change makes: each member on the team's accounts (split: its own one, or none);
    a strategy that left loses the old team's accounts. Only the books that change."""
    out = {}
    for m in dict.fromkeys([*new["members"], *old.get("members", [])]):
        cur = _cur(cfg, m)
        if m in new["members"]:
            want = ([new["assign"][m]] if new["assign"].get(m) else []) if new["mode"] == "split" else list(new["accounts"])
        else:
            want = [r["account"] for r in cur if r["account"] not in old.get("accounts", [])]
        rows = _rows(cur, want, (hold or {}).get(m))
        if rows != cur:
            out[m] = rows
    return out


def register(app, *, cfg, engine, labdesk) -> None:

    def label(name: str) -> str:
        s = cfg.strategies.get(name)
        return (s and s.label) or (name[4:] if name.startswith("lab_") else name)

    def checked(books: dict, on: dict) -> dict:
        """Every write's own checks before any write: the rows as /api/book reads them, then each book and each switch ON."""
        books = {m: book_rows(cfg, labdesk, m, rows) for m, rows in books.items()}
        try:
            for m, rows in books.items():
                labdesk.can_book(m, rows)
            for m, v in on.items():
                if v and not cfg.strategies[m].enabled:
                    labdesk.can_enable(m)
        except labdesk_mod.Refused as e:
            raise HTTPException(e.status, f"{label(m)}: {e}") from None
        return books

    async def write(books: dict, turns: dict, on: dict) -> None:
        """Accounts, then Take turns, then ON / OFF. A write that fails stops there, said in words (what came before stays)."""
        m = ""
        try:
            for m, rows in books.items():
                previous = _cur(cfg, m)
                await labdesk.set_book(m, rows)
                engine.journal("book_updated", strategy=m, assignments=rows, previous=previous, cause="setup")
            for m, v in turns.items():
                if bool(engine.rotating(m)) != v:
                    engine.set_rotation(m, v)
            for m, v in on.items():
                if bool(cfg.strategies[m].enabled) == v:
                    continue
                if not v:
                    await labdesk.stop(m, "off")          # its unfilled entries go and its day ends (never raises)
                if not await labdesk.set_enabled(m, v):
                    raise labdesk_mod.Refused(labdesk_mod.RECORD_CHANGED, 409)
                engine.journal("strategy_toggled", strategy=m, enabled=v, cause="setup")
        except labdesk_mod.Refused as e:
            raise HTTPException(e.status, f"{label(m)}: {e} Nothing after it was saved.") from None

    async def save_set(body: dict, accounts: list, on: bool):
        """A variant set {set, accounts, pick: {account: strategy}, settings?, turns?, hold?, on}: each account runs exactly one
        variant. Each member's book is the accounts that picked it, through the solo path; checked whole, new accounts written
        before removals, so an account is never without its variant on the way."""
        vs = next((s for s in variants.load(engine._root)["sets"] if s["id"] == body["set"]), None)
        if vs is None:
            raise HTTPException(404, "No such set.")
        pick = body.get("pick")
        turns, hold = body.get("turns", False), body.get("hold")
        for m in vs["members"]:
            if not labdesk.is_lab(m) or m not in cfg.strategies:
                raise HTTPException(409, f"{m} is no longer on the Desk; open the set again.")
        if not isinstance(pick, dict) or set(pick) != set(accounts) or not all(isinstance(v, str) for v in pick.values()) \
                or not set(pick.values()) <= set(vs["members"]):
            raise HTTPException(400, "Each account picks one variant of the set.")
        settings = _settings(body)
        if not isinstance(turns, bool) or not (hold is None or isinstance(hold, bool)):
            raise HTTPException(400, "turns and hold must be true or false")
        for m in vs["members"]:
            for r in _cur(cfg, m):
                if pick.get(r["account"], m) != m and engine.lab_open_on(m, r["account"]):
                    raise HTTPException(409, f"{short(r['account'])} has an open trade on {vs['labels'].get(m, m)}; change it once it is flat.")
        books = {}
        for m in vs["members"]:
            cur = _cur(cfg, m)
            rows = _rows(cur, [a for a in accounts if pick[a] == m], hold, None, settings)
            if rows != cur:
                books[m] = rows
        books = checked(dict(sorted(books.items(), key=lambda kv: len(kv[1]) <= len(_cur(cfg, kv[0])))), {m: on for m in vs["members"]})
        await write(books, {m: turns for m in vs["members"]}, {m: on for m in vs["members"]})
        engine.journal("setup_saved", set=vs["id"], pick=pick, on=on)
        return {"ok": True, "set": vs["id"], "book": labdesk.book_view()}

    @app.post("/api/setup")
    async def setup_save(request: Request):
        """Team {team, name?, members, accounts, mode, assign?, risk_usd, risk_by?, max_minis, hold?: {strategy: bool}, on}
        or solo {strategy, accounts, qty, turns, hold?, on}: the whole set-up in one go (module docstring). A team's on may be
        null (a Save with the Trading switch not flipped): each member keeps its own ON / OFF and its own Take turns."""
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, "a JSON object")
        on = body.get("on")
        if not isinstance(on, bool) and not (on is None and "team" in body and "set" not in body):
            raise HTTPException(400, "on must be true or false")
        accounts = body.get("accounts")
        if not isinstance(accounts, list) or not all(isinstance(a, str) for a in accounts) or len(set(accounts)) != len(accounts):
            raise HTTPException(400, "Accounts: a list of accounts, each once.")
        if "set" in body:
            return await save_set(body, accounts, on)
        if "team" in body:
            gid = engine.new_team_id() if body["team"] == "" else body["team"]
            keys = ("name", "members", "mode", "assign", "risk_usd", "risk_by", "max_minis")
            gbody = {k: body[k] for k in keys if k in body}
            members = gbody.get("members", [])
            gbody.update(accounts=accounts, on=bool(members and accounts))     # the group routes whenever it can
            hold = body.get("hold")
            if hold is not None and not (isinstance(hold, dict) and all(isinstance(v, bool) for v in hold.values())):
                raise HTTPException(400, "Hold overnight: yes or no for each strategy.")
            if not isinstance(members, list):
                raise HTTPException(400, "Members: a list of strategies, each once.")
            for m in members:
                vs = variants.set_of(engine._root, m)
                if vs:
                    raise HTTPException(409, f"It is in the set {vs['name']}.")
            saved, others = dict(engine.groups), []
            try:            # a member of another team leaves it in this same Save: checked with the movers out (memory only)
                for oid, g in saved.items():
                    left = [m for m in g["members"] if m not in members]
                    if oid != gid and left != g["members"]:
                        engine.groups[oid] = {**g, "members": left}
                        others.append((oid, *engine.group_checked(oid, {"members": left, "on": g["on"] and bool(left)})))
                        engine.groups[oid] = others[-1][2]
                old, new = engine.group_checked(gid, gbody)
            except GroupError as e:
                raise HTTPException(400, str(e)) from None
            finally:
                engine.groups.clear()
                engine.groups.update(saved)
            # the movers' books come from the new team only: one write each, never empty on the way
            sw = {} if on is None else {m: on for m in new["members"]}      # on null: no member switched, no Take turns touched
            books = checked(team_books(cfg, old, new, hold), sw)
            done = []
            try:
                for oid, _, o_new in others:
                    engine.write_group(oid, saved[oid], o_new)
                    done.append(oid)
                view = engine.write_group(gid, old, new)
            except Exception:       # never a mover out of its old team and not in the new one: the old teams come back
                for oid in done:
                    engine.groups[oid] = saved[oid]
                with contextlib.suppress(Exception):
                    engine._save_groups()
                raise
            # Team OFF ends Take turns; ON in Take turns mode starts it again (after write_group's own switch-on)
            await write(books, {m: on and new["mode"] == "cycle" for m in sw}, sw)
            engine.journal("setup_saved", team=gid, members=new["members"], accounts=accounts, mode=new["mode"], on=on)
            return {"ok": True, "team": gid, "group": view}
        name = str(body.get("strategy") or "")
        if not labdesk.is_lab(name):
            raise HTTPException(404, "That strategy is not on the Desk.")
        team = next((g for g in engine.groups.values() if name in g["members"]), None)
        if team is not None:
            raise HTTPException(409, IN_TEAM.format(team["name"]))
        vs = variants.set_of(engine._root, name)
        if vs:
            raise HTTPException(409, IN_SET.format(vs["name"]))
        qty, turns, hold = body.get("qty"), body.get("turns", False), body.get("hold")
        if qty is not None and not _whole(qty):
            raise HTTPException(400, QTY)
        if not isinstance(turns, bool) or not (hold is None or isinstance(hold, bool)):
            raise HTTPException(400, "turns and hold must be true or false")
        settings = _settings(body)
        cur = _cur(cfg, name)
        rows = _rows(cur, accounts, hold, qty, settings)
        books = checked({name: rows} if rows != cur else {}, {name: on})
        await write(books, {name: turns}, {name: on})
        engine.journal("setup_saved", strategy=name, accounts=accounts, qty=qty, turns=turns, on=on)
        return {"ok": True, "strategy": name, "book": labdesk.book_view()}
