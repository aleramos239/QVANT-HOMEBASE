"""One Set-up save for a team or a solo strategy (owner, 2026-11-02: "easy to set up impossible to get confused and mess it up").

A team is a Desk group and its account group, always together; a solo strategy is one Lab strategy on its own accounts. The
page sends the whole set-up in one call. It is checked as a whole first (one refusal, nothing written), then written in a
safe order: the account group -> each strategy's accounts (the final rows at once, so a book is never emptied on the way)
-> Take turns -> each strategy ON or OFF (OFF ends its day first, as the Desk's own switch does).

Rules built in: a team member is booked ONLY on its team's accounts (split: only its own one); a strategy that leaves a team
loses the team's accounts; the account group is on whenever it has a strategy and an account (the one switch the owner
sees is Trading ON / OFF, every member's own). A team drops the per-account extras (size per account, stop after, most;
owner, 2026-11-02) and keeps only each row's contract; Hold overnight stays, one choice per strategy. A solo save keeps every
row's size / risk / most / contract and takes new ones from `settings`."""
from __future__ import annotations

from fastapi import HTTPException, Request

from ..desk import labdesk as labdesk_mod
from ..desk.engine_groups import GroupError
from .strategies import book_rows

IN_TEAM = "It is in the team {}: set it up on the team's page."


def _cur(cfg, name: str) -> list:
    """`name`'s rows on this Desk's accounts, as the book holds them."""
    return [dict(r) for r in cfg.book.get(name) or [] if r.get("account") in cfg.accounts]


KEPT = ("size", "risk_usd", "most", "contract")


def _rows(cur: list, accounts: list, hold, qty=None, settings=None) -> list:
    """Rows on `accounts`: a booked account keeps its size (unless `qty`), a new one is 1; Hold overnight as `hold` (None: as
    the strategy holds now). A solo save (`settings` a dict, maybe empty) also keeps each row's size / risk / most / contract
    and lets `settings[account]` change them (and qty); a team (None) keeps only the contract, its own size rules win."""
    by = {r["account"]: r for r in cur}
    h = any(r.get("hold") is True for r in cur) if hold is None else hold is True
    out = []
    for a in accounts:
        old, new = by.get(a) or {}, (settings or {}).get(a) or {}
        row = {"account": a, "qty": int(new.get("qty") or qty or old.get("qty") or 1)}
        for k in KEPT if settings is not None else ("contract",):
            v = new.get(k, old.get(k))
            if v is not None:
                row[k] = v
        out.append({**row, **({"hold": True} if h else {})})
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

    @app.post("/api/setup")
    async def setup_save(request: Request):
        """Team {team, name?, members, accounts, mode, assign?, risk_usd, risk_by?, max_minis, hold?: {strategy: bool}, on}
        or solo {strategy, accounts, qty, turns, hold?, on}: the whole set-up in one go (module docstring)."""
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, "a JSON object")
        on = body.get("on")
        if not isinstance(on, bool):
            raise HTTPException(400, "on must be true or false")
        accounts = body.get("accounts")
        if not isinstance(accounts, list) or not all(isinstance(a, str) for a in accounts) or len(set(accounts)) != len(accounts):
            raise HTTPException(400, "Accounts: a list of accounts, each once.")
        if "team" in body:
            gid = body["team"]
            keys = ("name", "members", "mode", "assign", "risk_usd", "risk_by", "max_minis")
            gbody = {k: body[k] for k in keys if k in body}
            members = gbody.get("members", [])
            gbody.update(accounts=accounts, on=bool(members and accounts))     # the group routes whenever it can
            hold = body.get("hold")
            if hold is not None and not (isinstance(hold, dict) and all(isinstance(v, bool) for v in hold.values())):
                raise HTTPException(400, "Hold overnight: yes or no for each strategy.")
            try:
                old, new = engine.group_checked(gid, gbody)
            except GroupError as e:
                raise HTTPException(400, str(e)) from None
            books = checked(team_books(cfg, old, new, hold), {m: on for m in new["members"]})
            view = engine.set_group(gid, gbody)
            await write(books, {}, {m: on for m in new["members"]})
            engine.journal("setup_saved", team=gid, members=new["members"], accounts=accounts, mode=new["mode"], on=on)
            return {"ok": True, "team": gid, "group": view}
        name = str(body.get("strategy") or "")
        if not labdesk.is_lab(name):
            raise HTTPException(404, "That strategy is not on the Desk.")
        team = next((g for g in engine.groups.values() if name in g["members"]), None)
        if team is not None:
            raise HTTPException(409, IN_TEAM.format(team["name"]))
        qty, turns, hold = body.get("qty", 1), body.get("turns", False), body.get("hold")
        if isinstance(qty, bool) or not isinstance(qty, int) or qty < 1:
            raise HTTPException(400, "Contracts: a whole number above 0.")
        if not isinstance(turns, bool) or not (hold is None or isinstance(hold, bool)):
            raise HTTPException(400, "turns and hold must be true or false")
        settings = body.get("settings") or {}
        if not isinstance(settings, dict) or not all(isinstance(v, dict) for v in settings.values()):
            raise HTTPException(400, "settings: a dict of settings for each account.")
        cur = _cur(cfg, name)
        rows = _rows(cur, accounts, hold, qty, settings)
        books = checked({name: rows} if rows != cur else {}, {name: on})
        await write(books, {name: turns}, {name: on})
        engine.journal("setup_saved", strategy=name, accounts=accounts, qty=qty, turns=turns, on=on)
        return {"ok": True, "strategy": name, "book": labdesk.book_view()}

    @app.post("/api/groups/follow")
    async def group_follow(request: Request):
        """{groups: [{id, name?, members?}, ...]} (or one group's {id, name?, members?}): the charts service's Desk groups
        changed -- their account groups follow, and so do the books: a strategy that joins is booked on its team's accounts,
        one that leaves loses them. A move from one team to another is ONE book write (never empty on the way, which would
        end its day). Checked as a whole first: a refusal refuses the Desk group change, so the two never fall out of step.
        In the list form a group with no account group is skipped; alone it is a 404."""
        body = await request.json()
        if not isinstance(body, dict):
            raise HTTPException(400, "a JSON object")
        alone = "groups" not in body
        asked = [body] if alone else body["groups"]
        if not isinstance(asked, list) or not all(isinstance(g, dict) for g in asked):
            raise HTTPException(400, "groups: a list of groups")
        if alone and body.get("id") not in engine.groups:
            raise HTTPException(404, "No such group.")
        saved, changes = dict(engine.groups), []
        asked = [g for g in asked if g.get("id") in engine.groups]
        try:                                     # checked with every leaver out first (memory only), so a move checks in any order
            for g in asked:
                if isinstance(g.get("members"), list):
                    engine.groups[g["id"]] = {**saved[g["id"]], "members": [m for m in saved[g["id"]]["members"] if m in g["members"]]}
            for g in asked:
                fbody = engine.follow_body(g["id"], g.get("name"), g.get("members"))
                old, new = saved[g["id"]], engine.group_checked(g["id"], fbody)[1]
                engine.groups[g["id"]] = new
                changes.append((g["id"], fbody, old, new))
        except GroupError as e:
            raise HTTPException(400, str(e)) from None
        finally:
            engine.groups.clear()
            engine.groups.update(saved)
        books: dict = {}
        for _, _, old, new in changes:
            if new["on"] or old.get("on"):       # an off group never moved books
                for m, rows in team_books(cfg, old, new).items():
                    if m in new["members"] or m not in books:      # where it joins wins over where it left
                        books[m] = rows
        books = checked(books, {})
        views = {gid: engine.write_group(gid, old, new) for gid, _, old, new in changes}     # checked together above, no await between
        await write(books, {}, {})
        if alone:
            return {"ok": True, "id": body["id"], **views[body["id"]]}
        return {"ok": True, "groups": views}
