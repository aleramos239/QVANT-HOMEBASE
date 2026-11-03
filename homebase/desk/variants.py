"""Variant sets (owner, 2026-11-02): several versions of one Lab strategy (nq_cb_r1 / _r15 / _r2) folded under one name on the
Desk. The Desk only SUGGESTS a set; nothing combines by itself, the owner says yes. Display only: a set never touches a booking.
A strategy is in one set at most and never in a team too. Kept in <state>/variants.json (written whole)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from ..core.jsonio import write_json

TAILS = ("_r075", "_r1", "_r15", "_r2", "_fast", "_flex", "_desk", "_apex300", "_s25", "_s60", "_g10", "_g25")
ACTIONS = ("create", "rename", "label", "split", "dismiss")
_R = {"_r075": "0.75R", "_r1": "1R", "_r15": "1.5R", "_r2": "2R"}
MAX_LABEL = 12


class VariantError(ValueError):
    """A refusal in words the page may show."""


def _path(root: Path) -> Path:
    return root / "variants.json"


def _read(root: Path) -> dict:
    d = {"sets": [], "dismissed": [], "next": 1}
    try:
        data = json.loads(_path(root).read_text())
        if isinstance(data, dict):
            d.update(sets=[s for s in data.get("sets") or [] if isinstance(s, dict) and isinstance(s.get("members"), list)],
                     dismissed=[m for m in data.get("dismissed") or [] if isinstance(m, list)],
                     next=int(data.get("next") or 1))
    except FileNotFoundError:
        pass
    except Exception as e:  # noqa: BLE001 -- the Desk must still start (no sets)
        print(f"homebase desk: reading {_path(root).name} failed: {e!r}", file=sys.stderr)
    return d


def load(root: Path, names: set | None = None) -> dict:
    """The file; with `names` (non-empty), members no longer there are dropped and a set left under 2 dissolves (written only then)."""
    d = _read(root)
    if names:                       # no names (Lab side off, or not loaded yet) shrinks nothing: it could not be undone
        sets = []
        for s in d["sets"]:
            m = [x for x in s["members"] if x in names]
            if len(m) >= 2:
                sets.append({**s, "members": m, "labels": {k: v for k, v in (s.get("labels") or {}).items() if k in m}})
        if sets != d["sets"]:
            d["sets"] = sets
            write_json(_path(root), d)
    return d


def set_of(root: Path, name: str) -> dict | None:
    return next((s for s in _read(root)["sets"] if name in s["members"]), None)


def _split(name: str) -> tuple:
    """(stem, [tails in name order])."""
    tails = []
    while (t := next((t for t in TAILS if name.endswith(t) and len(name) > len(t)), None)):
        tails.insert(0, t)
        name = name[:-len(t)]
    return name, tails


def _label(tails: list) -> str:
    return " ".join(_R.get(t, t.replace("_", "")) for t in tails)


def suggest(names: list, *, in_team: set, sets: list, dismissed: list) -> list:
    taken = in_team | {m for s in sets for m in s["members"]}
    by: dict = {}
    for n in names:
        stem, tails = _split(n)
        if tails and n not in taken:
            by.setdefault(stem, []).append(n)
    return [{"stem": stem, "members": m, "labels": {n: _label(_split(n)[1]) for n in m}}
            for stem, m in by.items() if len(m) >= 2 and sorted(m) not in dismissed]


def _label_ok(v) -> str:
    if not isinstance(v, str) or not 1 <= len(v) <= MAX_LABEL:
        raise VariantError(f"A label is 1 to {MAX_LABEL} characters.")
    return v


def apply(root: Path, action: str, body: dict, *, teams: dict, names: set) -> dict:
    d = _read(root)
    sets = d["sets"]
    sid = body.get("id")
    cur = next((s for s in sets if s["id"] == sid), None) if action != "create" and action != "dismiss" else None
    if action in ("rename", "label", "split") and cur is None:
        raise VariantError("No such set.")
    if action == "create":
        members = body.get("members")
        if not isinstance(members, list) or len(set(members)) != len(members) or len(members) < 2:
            raise VariantError("A set is 2 or more strategies, each once.")
        for m in members:
            if m not in names:
                raise VariantError(f"{m} is not a strategy on this Desk.")
            if (s := next((s for s in sets if m in s["members"]), None)):
                raise VariantError(f"{m} is already in the set {s['name']}.")
            if (t := next((g for g in teams.values() if m in g.get("members", [])), None)):
                raise VariantError(f"It is in the team {t.get('name')}.")
        given = body.get("labels") if isinstance(body.get("labels"), dict) else {}
        stem = _split(members[0])[0].removeprefix("lab_")
        name = str(body.get("name") or stem).strip()[:40]
        sets.append({"id": f"v{d['next']}", "name": name,
                     "members": members, "labels": {m: _label_ok(given.get(m) or _label(_split(m)[1]) or m[:MAX_LABEL]) for m in members}})
        d["next"] += 1
    elif action == "rename":
        name = str(body.get("name") or "").strip()[:40]
        if not name:
            raise VariantError("A set needs a name.")
        cur["name"] = name
    elif action == "label":
        if body.get("member") not in cur["members"]:
            raise VariantError("That strategy is not in this set.")
        cur["labels"][body["member"]] = _label_ok(body.get("label"))
    elif action == "split":
        sets.remove(cur)
    elif action == "dismiss":
        m = body.get("members")
        if not isinstance(m, list) or len(m) < 2 or not all(isinstance(x, str) for x in m):
            raise VariantError("Not these: 2 or more strategies.")
        if sorted(m) not in d["dismissed"]:
            d["dismissed"].append(sorted(m))
    else:
        raise VariantError("No such action.")
    write_json(_path(root), d)
    return d
