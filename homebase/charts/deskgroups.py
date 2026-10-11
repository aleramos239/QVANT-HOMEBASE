"""Desk groups: named sets of Desk strategies that run together (an eval group, a funded group, ...). Kept in one small file
beside the Lab strategies' records (<desklab root>/../deskgroups.json). A strategy is in ONE group at most: the same code
tried two ways (say for an eval and for a funded account) is two strategies, each in its own group.

Display and bookkeeping only: a group never books an account, switches a strategy on or sends an order. Its combined
results are read off the members' SAVED runs (see combine / summarize): nothing here runs a backtest.
"""
import datetime as dt
import json
import os
import re
import tempfile
import threading
from pathlib import Path

from ..labrun import store

KINDS = ("eval", "funded", "together")        # what the group's page leads with: pass odds, payout odds, or both
MAX_GROUPS = 12
MAX_NAME = 40
STRATEGY_RE = re.compile(r"[a-z][a-z0-9_]{0,59}")      # a Desk strategy id: nq930, lab_nq_vault_break_micro
_lock = threading.Lock()


class GroupError(ValueError):
    """A refusal in words the page may show."""


def path(at=None) -> Path:
    return store.root(at).parent / "deskgroups.json"


def _clean(raw) -> list[dict]:
    """The groups as they may be trusted from the file: a wrong shape is dropped, never raised."""
    out, seen = [], set()
    for g in (raw.get("groups") if isinstance(raw, dict) else None) or []:
        if not isinstance(g, dict) or not isinstance(g.get("id"), str) or not isinstance(g.get("name"), str) or g["id"] in seen:
            continue
        seen.add(g["id"])
        members = [m for m in (g.get("members") or []) if isinstance(m, str) and STRATEGY_RE.fullmatch(m)]
        out.append({"id": g["id"], "name": g["name"], "kind": g.get("kind") if g.get("kind") in KINDS else "together",
                    "members": list(dict.fromkeys(members))})
    return out


def load(at=None) -> list[dict]:
    try:
        return _clean(json.loads(path(at).read_text()))
    except (OSError, ValueError):
        return []


def _save(groups: list[dict], at=None) -> None:
    p = path(at)
    p.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".deskgroups.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump({"groups": groups}, f, separators=(",", ":"))
        os.replace(tmp, p)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _name(raw) -> str:
    name = " ".join(str(raw).split()) if isinstance(raw, str) else ""
    if not name or len(name) > MAX_NAME or any(ord(c) < 32 for c in name):
        raise GroupError(f"A group's name is 1 to {MAX_NAME} characters.")
    return name


def _kind(raw) -> str:
    if raw not in KINDS:
        raise GroupError("A group is for an eval, a funded account, or running together.")
    return raw


def _find(groups, gid) -> dict:
    for g in groups:
        if g["id"] == gid:
            return g
    raise GroupError("That group is not there any more.")


def _taken(groups, name, but=None) -> None:
    if any(g["id"] != but and g["name"].casefold() == name.casefold() for g in groups):
        raise GroupError("There is a group with that name already.")


def apply(action: str, body: dict, at=None) -> list[dict]:
    """create {name, kind?} | rename {id, name} | kind {id, kind} | delete {id} | move {strategy, group: id | null} -> all groups.
    One write at a time; a refusal raises GroupError and writes nothing."""
    with _lock:
        groups = load(at)
        if action == "create":
            name = _name(body.get("name"))
            if len(groups) >= MAX_GROUPS:
                raise GroupError(f"There are {MAX_GROUPS} groups already.")
            _taken(groups, name)
            used = {g["id"] for g in groups}
            n = 1
            while f"g{n}" in used:
                n += 1
            groups.append({"id": f"g{n}", "name": name, "kind": _kind(body.get("kind", "together")), "members": []})
        elif action == "rename":
            g = _find(groups, body.get("id"))
            name = _name(body.get("name"))
            _taken(groups, name, g["id"])
            g["name"] = name
        elif action == "kind":
            _find(groups, body.get("id"))["kind"] = _kind(body.get("kind"))
        elif action == "delete":
            g = _find(groups, body.get("id"))
            groups.remove(g)            # its strategies are simply in no group again
        elif action == "move":
            sid = body.get("strategy")
            if not isinstance(sid, str) or not STRATEGY_RE.fullmatch(sid):
                raise GroupError("That is not a strategy.")
            target = body.get("group")
            if target is not None:
                target = _find(groups, target)
            for g in groups:
                if sid in g["members"]:
                    g["members"].remove(sid)
            if target is not None:
                target["members"].append(sid)
        else:
            raise GroupError("unknown group action")
        _save(groups, at)
        return groups


# ---- combined results -------------------------------------------------------------------------------------------------

def _num(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def merged(named: list[tuple[str, list[dict]]]) -> tuple[list[dict], list[str]]:
    """Several members' trades as one ledger, in the order they closed, and each trade's owner in that same order. (The sim
    reads the ledger as one account's trades; trades open at once are counted together by its own open-loss rule.)"""
    rows = [(owner, t) for owner, ledger in named for t in ledger
            if isinstance(t, dict) and _num(t.get("net")) is not None and isinstance(t.get("date"), str)]
    rows.sort(key=lambda r: (r[1].get("exit_ms") or 0, r[1].get("entry_ms") or 0))
    return [t for _, t in rows], [o for o, _ in rows]


def summarize(trades: list[dict], owners: list[str] | None = None) -> dict | None:
    """What a ledger made, after costs: {net, trades, win_rate, profit_factor, max_drawdown, days, worst_day, best_day,
    together_days (days two or more members traded; needs `owners`, one name per trade, in the ledger's order),
    curve: {days, vals}}. None for an empty ledger. max_drawdown is a loss (negative), on closed trades."""
    if not trades:
        return None
    net = [float(t["net"]) for t in trades]
    wins, losses = sum(x for x in net if x > 0), -sum(x for x in net if x < 0)
    by_day: dict[str, float] = {}
    who: dict[str, set] = {}
    for i, t in enumerate(trades):
        by_day[t["date"]] = by_day.get(t["date"], 0.0) + float(t["net"])
        if owners is not None and i < len(owners):
            who.setdefault(t["date"], set()).add(owners[i])
    peak = cum = worst = 0.0
    for x in net:
        cum += x
        peak = max(peak, cum)
        worst = min(worst, cum - peak)
    days, run, vals = sorted(by_day), 0.0, []
    for d in days:
        run += by_day[d]
        vals.append(round(run, 2))
    return {"net": round(sum(net), 2), "trades": len(net), "win_rate": round(100.0 * sum(x > 0 for x in net) / len(net), 2),
            "profit_factor": round(wins / losses, 3) if losses > 0 else None, "max_drawdown": round(worst, 2),
            "days": len(days), "worst_day": round(min(by_day.values()), 2), "best_day": round(max(by_day.values()), 2),
            "together_days": sum(1 for d in days if len(who.get(d, ())) >= 2) if owners is not None else None,
            "curve": {"days": days, "vals": vals}}


def stamp() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
