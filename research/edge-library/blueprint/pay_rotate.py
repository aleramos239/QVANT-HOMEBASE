"""pay_rotate.py -- THE ROTATION RULE of the payout pipeline (design step 4): a FIXED rule in code says each evening which strategy of a
slot trades the next day. Conti: run the strategy whose equity is making new highs, stand the one in a drawdown down, keep about three
that take turns. The AI tunes and tests the rule (pay_build does, on the build days); it never decides a day by hand.

  form(net, lookback, within) -> one bool a day: IS THE STRATEGY IN FORM FOR THAT DAY?
        Its own equity (the running sum of `net`, one entry a session day) closed at a `lookback`-day high on one of the `within`
        session days BEFORE that day. Nothing of the day itself, or of a later one, is read. The first `within` days have no history
        to read and are in form.
  pick(flags) -> one number a day: the FIRST strategy of the slot's list that is in form (0 = the slot's first choice, 1 = its first
        reserve ...), or -1: none is, and the slot stands down that day. flags = [form() of each, the first choice first]
  rotated(options, flags) -> the slot's day arrays {"net", "open", "up", "n"} with each day taken from the strategy pick() names
  tonight(the_set, series) -> {"asof", "slots": {rule id: {slot id: {"trades": name | None, "in_form": {name: bool}}}}}
        what trades the NEXT session, from each strategy's results so far. series(name) -> (net a day, the last day as an ISO date)
  evening(root=None) -> the notice written, or None
        tonight() for the set on file, on every result on file (the build days, then the unseen days of a member whose one read is on
        file). It is saved (<pipeline root>/payout/tonight.json). When what trades differs from the last evening's, ONE notice is
        added to notices.jsonl: the owner switches, and until he does the old set keeps running (his word, 2026-10-13).

numpy only. Locked by tests/test_pay_rotate.py.
"""
from __future__ import annotations

import datetime as dt
import json

import numpy as np

from . import pay_accounts as PA
from . import pipe_store as PS

TONIGHT, NOTICES = "tonight.json", "notices.jsonl"


def form(net, lookback: int, within: int) -> np.ndarray:
    eq = np.cumsum(np.asarray(net, np.float64))
    n = len(eq)
    if n == 0:
        return np.zeros(0, bool)
    pad = np.concatenate([np.full(lookback - 1, -np.inf), eq])
    high = eq >= np.lib.stride_tricks.sliding_window_view(pad, lookback).max(axis=1)        # day j closed at its lookback-day high
    recent = np.concatenate([np.zeros(within, bool), high])                                # day t reads days t-within .. t-1
    out = np.lib.stride_tricks.sliding_window_view(recent, within)[:n].any(axis=1)
    out[:within] = True
    return out


def pick(flags: list) -> np.ndarray:
    sel = np.full(len(flags[0]), -1, np.int64)
    for j in range(len(flags) - 1, -1, -1):
        sel = np.where(flags[j], j, sel)
    return sel


def rotated(options: list, flags: list) -> dict:
    sel = pick(flags)
    return {k: sum(np.where(sel == j, o[k], 0.0) for j, o in enumerate(options)) for k in ("net", "open", "up", "n")}


def tonight(the_set: dict, series) -> dict:
    out, asof = {}, None
    for rid, s in (the_set.get("sets") or {}).items():
        rot, slots = s.get("rotation"), {}
        for slot, m in (s.get("slots") or {}).items():
            if not m:
                slots[slot] = {"trades": None, "in_form": {}}
                continue
            names = [m["name"], *[b["name"] for b in m.get("bench") or []]]
            if not rot:
                slots[slot] = {"trades": m["name"], "in_form": {}}
                continue
            ok = {}
            for name in names:
                net, last = series(name)
                asof = last if asof is None else min(asof, last)
                # the NEXT day's flag: one more day at the end, which reads the days before it
                ok[name] = bool(form(np.append(net, 0.0), rot["lookback"], rot["within"])[-1]) if len(net) else True
            slots[slot] = {"trades": next((n for n in names if ok[n]), None), "in_form": ok}
        out[rid] = slots
    return {"asof": asof, "slots": out}


def _read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def notices(root=None, last: int = 30) -> list:
    try:
        rows = [json.loads(x) for x in (PS.root(root) / "payout" / NOTICES).read_text(encoding="utf-8").splitlines() if x.strip()]
    except (OSError, ValueError):
        return []
    return rows[-last:]


def notice(root, kind: str, text: str, **more) -> dict:
    row = {"utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "kind": kind, "text": text, **more}
    with open(PA.folder(root) / NOTICES, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _words(now: dict, the_set: dict) -> list:
    lines = []
    for rid, slots in now["slots"].items():
        s = (the_set.get("sets") or {}).get(rid) or {}
        parts = [f"{slot} {v['trades'] or 'stand down'}" for slot, v in slots.items() if (s.get("slots") or {}).get(slot)]      # a slot the set has nobody for is no news
        lines.append(f"{s.get('account_name') or rid}: " + (", ".join(parts) if parts else "nobody trades"))
    return lines


def evening(root=None, series=None) -> dict | None:
    d = PA.folder(root)
    the_set = _read(d / "set.json")
    if not the_set or not the_set.get("sets"):
        return None
    if series is None:
        from . import pay_build
        series = pay_build.series(root)
    now, was = tonight(the_set, series), _read(d / TONIGHT)
    PS._write(d / TONIGHT, {**now, "set": the_set.get("built_utc")})
    same = was is not None and was.get("slots") == now["slots"]
    if same:
        return None
    first = was is None
    text = ("Tonight's set" if first else "SWITCH: the set changed") + (f" (results through {now['asof']})" if now["asof"] else "") + ". " + "; ".join(_words(now, the_set))
    return notice(root, "set" if first else "switch", text, slots=now["slots"])
