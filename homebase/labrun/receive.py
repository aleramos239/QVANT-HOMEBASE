"""The server's side of "send a strategy to the server" (the Mac's deploy/linux/send_strategy.py runs it over ssh).

    python -m homebase.labrun.receive --check                       is this code here, which store, which folder
    python -m homebase.labrun.receive NAME --show                   what this store has under NAME
    python -m homebase.labrun.receive NAME [--go] [--replace] < record.json
                                                                    judge the Mac's record; with --go, write it

One JSON line out: {"verdict": "new" | "same" | "replace" | "refused", "why": ..., "wrote": bool, ...}. Exit 0 for a
verdict that is not a refusal, 2 for a refusal. Without --go nothing is written.

What lands is the Mac's record (frozen code, settings, window, costs) and nothing else, ALWAYS switched OFF and with no
account: the days, the journal and the desk's sidecar (its limits and book) belong to the server and are never touched.
The judging and the write are one step under the store's own lock (store.write_lock), the same one Promote takes.

Refused, in plain words: a record that is not the strategy's own or whose code no longer matches its hash; one the Desk
could not make a strategy of (labcfg.usable); one that is in the server's Archive; a DIFFERENT version of one the server
already has, unless --replace -- and even then not while it is ON or has accounts booked (a record written over a
booked one drops its book). The record it replaces is first kept in <store>/.replaced/.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import sys

from ..desk import labcfg
from . import store

KEPT = ".replaced"      # a dot first: never a strategy's name (store.NAME_RE), never listed as one


def _same(a: dict, b: dict) -> bool:
    """One strategy: every field but the switch (the server's own may be ON; the Mac's is never what counts)."""
    return {k: v for k, v in a.items() if k != "enabled"} == {k: v for k, v in b.items() if k != "enabled"}


def _differs(old: dict, new: dict) -> str:
    bits = [f"{k} {str(old.get(k))[:12]} -> {str(new.get(k))[:12]}" for k in ("sha256", "params", "qty", "session_window", "promoted_utc")
            if old.get(k) != new.get(k)]
    return ", ".join(bits) or "other fields"


def judge(name: str, rec, replace: bool = False, at=None) -> dict:
    """{"verdict", "why"} for sending `rec` under `name` into the store `at`. Reads only."""
    def no(why: str) -> dict:
        return {"verdict": "refused", "why": why}
    if not isinstance(name, str) or not store.NAME_RE.fullmatch(name) or f"{name}.json" == store.RUNNER_FILE:
        return no("That is not a strategy name (a-z, 0-9 and _, a letter first).")
    if not isinstance(rec, dict) or rec.get("name") != name or rec.get("id") != f"draft_{name}":
        return no("The record is not this strategy's own.")
    src = rec.get("source")
    if not isinstance(src, str) or hashlib.sha256(src.encode("utf-8")).hexdigest() != rec.get("sha256"):
        return no("Its code does not match its hash: it was changed after it was promoted. Promote it again on the Mac.")
    if not labcfg.usable(rec):
        return no("The Desk could not make a strategy of this record (its market, or the market its orders go to, is not one it knows).")
    cur = store.get(name, at)
    if cur is None:
        if any(r.get("name") == name for r in store.archived(at)):
            return no("It is in the server's Archive. Restore it there first.")
        return {"verdict": "new", "why": "Not on the server yet. It will land OFF, with no account."}
    on = "ON" if cur.get("enabled") is True else "OFF"
    if _same(cur, rec):
        return {"verdict": "same", "why": f"Already on the server, same code and settings (it is {on} there). Nothing to send."}
    diff = _differs(cur, rec)
    if not replace:
        return no(f"The server already has a DIFFERENT version ({diff}). Nothing was changed. Send with --replace only if you mean to replace it.")
    if cur.get("enabled") is True:
        return no(f"The server's version is ON ({diff}). Switch it off there first.")
    if store.booked(name, at):
        return no(f"Accounts are booked on the server's version ({diff}). Take it off the accounts there first: a new record drops its book.")
    return {"verdict": "replace", "why": f"Replaces the server's OFF version ({diff}); that one is kept in {KEPT}/."}


def receive(name: str, rec, go: bool = False, replace: bool = False, at=None) -> dict:
    """judge(), and with go the write -- both under one lock, then read back from disk."""
    with store.write_lock(at, wait_s=10):
        out = judge(name, rec, replace, at)
        out["wrote"] = False
        if go and out["verdict"] in ("new", "replace"):
            if out["verdict"] == "replace":
                old = store.get(name, at)
                keep = store.root(at) / KEPT
                keep.mkdir(parents=True, exist_ok=True)
                stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
                (keep / f"{name}-{stamp}.json").write_text(json.dumps(old), encoding="utf-8")
            store.put({**rec, "enabled": False}, at)
            back = store.get(name, at) or {}
            if back.get("sha256") != rec.get("sha256") or back.get("enabled") is not False:
                return {"verdict": "refused", "why": "The write did not read back as sent. Check the server by hand.", "wrote": True}
            out["wrote"] = True
    return out


def show(name: str, at=None) -> dict:
    rec = store.get(name, at)
    if rec is None:
        return {"present": False, "archived": any(r.get("name") == name for r in store.archived(at))}
    return {"present": True, "enabled": rec.get("enabled") is True, "booked": store.booked(name, at), "sha256": rec.get("sha256"),
            "qty": rec.get("qty"), "params": rec.get("params"), "promoted_utc": rec.get("promoted_utc")}


def main(argv=None, stdin=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m homebase.labrun.receive")
    ap.add_argument("name", nargs="?")
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--show", action="store_true")
    ap.add_argument("--go", action="store_true")
    ap.add_argument("--replace", action="store_true")
    ap.add_argument("--root", help="a store folder, for tests; else the machine's own")
    a = ap.parse_args(argv)
    at = a.root
    if a.check:
        print(json.dumps({"ok": True, "store": str(store.root(at))}))
        return 0
    if not a.name:
        ap.error("a strategy name (or --check)")
    if a.show:
        print(json.dumps(show(a.name, at)))
        return 0
    try:
        rec = json.loads((stdin or sys.stdin).read())
    except ValueError:
        print(json.dumps({"verdict": "refused", "why": "The record did not arrive as JSON.", "wrote": False}))
        return 2
    try:
        out = receive(a.name, rec, a.go, a.replace, at)
    except TimeoutError:
        out = {"verdict": "refused", "why": "The Lab store is busy (another write is going). Try again.", "wrote": False}
    print(json.dumps({**out, "store": str(store.root(at))}))
    return 2 if out["verdict"] == "refused" else 0


if __name__ == "__main__":
    raise SystemExit(main())
