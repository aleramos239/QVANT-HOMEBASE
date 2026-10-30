"""Desk families (owner, 2026-10-29): variants of one idea (the same code at other targets or stops) folded under one row of the
Desk's sidebar, with one page that sets them side by side. Display only: a family never trades, books or switches anything --
each variant keeps its own switch, accounts and record, and may sit in an account cycle (deskgroups.py) as well.
Kept in one small file beside the Lab strategies' records (<desklab root>/../deskfamilies.json). A strategy is in one family
at most; `short` is the few words its row shows inside the family ("25 pts · 1.5R").
"""
import re
import threading
from pathlib import Path

from ..core.jsonio import read_dict, write_json
from ..labrun import store
from .deskgroups import STRATEGY_RE, GroupError

MAX_FAMILIES = 40
MAX_NAME = 40
MAX_SHORT = 24
FAMILY_ID = re.compile(r"f\d{1,4}")
ACTIONS = ("create", "rename", "delete", "move", "short")
_lock = threading.Lock()


def path(at=None) -> Path:
    return store.root(at).parent / "deskfamilies.json"


def _words(raw, most: int, what: str, empty_ok=False) -> str:
    s = " ".join(raw.split()) if isinstance(raw, str) else ""
    if (not s and not empty_ok) or len(s) > most or any(ord(c) < 32 for c in s):
        raise GroupError(f"{what} is {'up to' if empty_ok else '1 to'} {most} characters.")
    return s


def load(at=None) -> list[dict]:
    """The families as they may be trusted from the file: a wrong shape is dropped, never raised. A strategy listed twice
    stays in the first family only."""
    out, seen, taken = [], set(), set()
    for f in read_dict(path(at)).get("families") or []:
        if not (isinstance(f, dict) and isinstance(f.get("id"), str) and FAMILY_ID.fullmatch(f["id"])
                and isinstance(f.get("name"), str)) or f["id"] in seen:
            continue
        seen.add(f["id"])
        members = [m for m in dict.fromkeys(f.get("members") or []) if isinstance(m, str) and STRATEGY_RE.fullmatch(m) and m not in taken]
        taken.update(members)
        short = f.get("short") if isinstance(f.get("short"), dict) else {}
        out.append({"id": f["id"], "name": f["name"], "members": members,
                    "short": {m: short[m] for m in members if isinstance(short.get(m), str) and short[m]}})
    return out


def _find(fams, fid) -> dict:
    for f in fams:
        if f["id"] == fid:
            return f
    raise GroupError("That family is not there any more.")


def _strategy(raw) -> str:
    if not isinstance(raw, str) or not STRATEGY_RE.fullmatch(raw):
        raise GroupError("That is not a strategy.")
    return raw


def apply(action: str, body: dict, at=None) -> list[dict]:
    """create {name} | rename {id, name} | delete {id} | move {strategy, family: id | null, short?} | short {strategy, short}
    -> all families. One write at a time; a refusal raises GroupError and writes nothing."""
    with _lock:
        fams = load(at)
        if action == "create":
            name = _words(body.get("name"), MAX_NAME, "A family's name")
            if len(fams) >= MAX_FAMILIES:
                raise GroupError(f"There are {MAX_FAMILIES} families already.")
            if any(f["name"].casefold() == name.casefold() for f in fams):
                raise GroupError("There is a family with that name already.")
            n = max([0] + [int(f["id"][1:]) for f in fams]) + 1
            fams.append({"id": f"f{n}", "name": name, "members": [], "short": {}})
        elif action == "rename":
            f, name = _find(fams, body.get("id")), _words(body.get("name"), MAX_NAME, "A family's name")
            if any(o is not f and o["name"].casefold() == name.casefold() for o in fams):
                raise GroupError("There is a family with that name already.")
            f["name"] = name
        elif action == "delete":
            fams.remove(_find(fams, body.get("id")))        # its strategies are simply in no family again
        elif action == "move":
            sid, target = _strategy(body.get("strategy")), body.get("family")
            target = _find(fams, target) if target is not None else None
            short = _words(body.get("short", ""), MAX_SHORT, "A variant's short name", empty_ok=True)
            for f in fams:
                if sid in f["members"]:
                    f["members"].remove(sid)
                    f["short"].pop(sid, None)
            if target is not None:
                target["members"].append(sid)
                if short:
                    target["short"][sid] = short
        elif action == "short":
            sid = _strategy(body.get("strategy"))
            short = _words(body.get("short", ""), MAX_SHORT, "A variant's short name", empty_ok=True)
            f = next((f for f in fams if sid in f["members"]), None)
            if f is None:
                raise GroupError("That strategy is in no family.")
            if short:
                f["short"][sid] = short
            else:
                f["short"].pop(sid, None)
        else:
            raise GroupError("unknown family action")
        write_json(path(at), {"families": fams})
        return fams
