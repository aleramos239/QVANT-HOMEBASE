"""DRAFT strategies, run only in a child process.

A draft is Python the user (or Claude) just wrote: it is NEVER imported into the chart service (or the
desk). Everything the service needs from one -- its catalog entry, a validated run / heat-map /
walk-forward request -- comes from a child:

    python -m homebase.backtest.drafthost <op>      JSON payload on stdin, one JSON answer on stdout
        describe       {dir}                        -> [catalog entry | {id, name, draft, error}]
        validate_run   {body}                       -> runner.validate(body)          (+ draft_source)
        validate_grid  {body}                       -> grid.validate_grid(body)       (+ draft_source per cell)
        validate_wf    {body}                       -> walkforward.validate_wf(body)  (+ draft_source per cell)

with a timeout (TIMEOUT_S), niced like a backtest child. The validated request carries the draft's SOURCE
(`draft_source`), so the `runner exec` child that executes the backtest runs exactly the code that was
validated -- a later edit of the file changes nothing about a queued run -- and registers it with
register_source() into ITS OWN strategies.REGISTRY. In the service process REGISTRY never holds a
draft: validate()/validate_grid()/validate_wf() see a draft id that is not registered and come here.
No child starts 09:20-09:35 ET on a weekday (slots.QUIET).
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import threading
import types
from pathlib import Path

from .. import draftstore
from ..paths import repo_root
from .slots import QUIET_REFUSAL, Slots

TIMEOUT_S = 30.0
OPS = ("describe", "validate_run", "validate_grid", "validate_wf")


class DraftError(ValueError):
    """A draft could not be loaded or validated. The message is shown to the user as is."""


def needs_child(sid) -> bool:
    """True for a draft id this process has not registered (i.e. always, in the chart service)."""
    if not draftstore.is_draft_id(sid):
        return False
    from .. import strategies
    return sid not in strategies.REGISTRY


# ---------------------------------------------------------------- the service side

def _python() -> str:
    return sys.executable


def in_child(op: str, payload: dict, *, timeout: float = TIMEOUT_S, python: str | None = None):
    """Run one op in a fresh child; its result, or DraftError with the child's message."""
    if op not in OPS:
        raise ValueError(f"unknown op {op!r}")
    if Slots().quiet():
        raise DraftError(QUIET_REFUSAL)
    env = dict(os.environ)
    env.setdefault(draftstore.ENV, str(draftstore.drafts_dir()))
    try:
        p = subprocess.run([python or _python(), "-m", "homebase.backtest.drafthost", op],
                           input=json.dumps(payload, default=str), capture_output=True, text=True,
                           timeout=timeout, cwd=repo_root(), env=env)
    except subprocess.TimeoutExpired:
        raise DraftError(f"the draft did not load within {timeout:g} s (an import-time loop?)") from None
    try:
        out = json.loads(p.stdout.strip().splitlines()[-1]) if p.stdout.strip() else None
    except ValueError:
        out = None
    if not isinstance(out, dict):
        tail = (p.stderr or p.stdout or "").strip()[-800:]
        raise DraftError(f"the draft host exited {p.returncode}: {tail or 'no output'}")
    if not out.get("ok"):
        raise DraftError(str(out.get("error") or "draft error"))
    return out.get("result")


_cache: dict = {}
_cache_lock = threading.Lock()


def _stamp(base: Path) -> tuple:
    out = []
    for name, p in draftstore.list_files(base):
        try:
            st = p.stat()
        except OSError:
            continue
        out.append((name, st.st_mtime_ns, st.st_size))
    return tuple(out)


def catalog(base: Path | None = None, builtin_ids=()) -> list[dict]:
    """The drafts' catalog entries, described in a child and cached until a file changes. A broken
    draft is listed with `error` (and no inputs) rather than dropped, so its author sees why. Never
    raises: a failed describe lists every draft with that error."""
    base = Path(base) if base is not None else draftstore.drafts_dir()
    stamp = _stamp(base)
    if not stamp:
        return []
    key = (str(base), stamp)
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    try:
        got = in_child("describe", {"dir": str(base)})
    except DraftError as e:
        return [{"id": draftstore.draft_id(n), "name": n, "draft": True, "error": str(e), "inputs": []}
                for n, *_ in stamp]
    out = []
    for d in got or []:
        if d.get("id") in set(builtin_ids):          # belt and braces: never shadow a built-in
            continue
        out.append(d)
    with _cache_lock:
        _cache.clear()
        _cache[key] = out
    return out


# ---------------------------------------------------------------- loading (child side only)

def _load(name: str, source: str, origin: str):
    """Exec `source` as a fresh module; its one Strategy subclass, with id forced to draft_<name>."""
    from ..strategies.base import Strategy
    draftstore.validate_name(name)
    modname = f"homebase_draft_{name}"
    mod = types.ModuleType(modname)
    mod.__file__ = origin
    sys.modules[modname] = mod
    try:
        exec(compile(source, origin, "exec", dont_inherit=True), mod.__dict__)
    except SyntaxError as e:
        raise DraftError(f"SyntaxError: {e.msg} (line {e.lineno})") from None
    except Exception as e:  # noqa: BLE001 -- the author must see what broke
        raise DraftError(f"{type(e).__name__} while loading the draft: {e}") from None
    found = [v for v in vars(mod).values()
             if isinstance(v, type) and issubclass(v, Strategy) and v is not Strategy
             and v.__module__ == modname]
    if len(found) != 1:
        raise DraftError(f"a draft defines exactly one Strategy subclass (found {len(found)})")
    cls = found[0]
    cls.id = draftstore.draft_id(name)
    if not cls.name:
        cls.name = name
    if not isinstance(cls.root, str) or not cls.root:
        raise DraftError("the strategy needs a `root` (e.g. \"NQ\")")
    try:
        cls.describe()
        cls(None)                  # the defaults must validate against the schema
    except Exception as e:  # noqa: BLE001
        raise DraftError(f"{type(e).__name__}: {e}") from None
    return cls


def register_source(name: str, source: str, origin: str | None = None):
    """Load a draft from source and add it to THIS process's strategies.REGISTRY. Child processes only
    (the draft host and a `runner exec` child); the chart service never calls it."""
    from .. import strategies
    cls = _load(name, source, origin or f"<draft {name}>")
    strategies.REGISTRY[cls.id] = cls
    return cls


def _describe(base: Path) -> list[dict]:
    from .. import strategies
    out = []
    for name, p in draftstore.list_files(base):
        sid = draftstore.draft_id(name)
        entry = {"id": sid, "name": name, "draft": True, "file": str(p)}
        if sid in strategies.REGISTRY:
            out.append({**entry, "error": "clashes with a built-in strategy id", "inputs": []})
            continue
        try:
            cls = _load(name, p.read_text(encoding="utf-8"), str(p))
            d = cls.describe()
            out.append({**d, "id": sid, "name": d.get("name") or name, "draft": True, "file": str(p),
                        "session_independent": bool(getattr(cls, "session_independent", False))})
        except Exception as e:  # noqa: BLE001
            out.append({**entry, "error": str(e), "inputs": []})
    return out


def _register_for(body) -> str:
    """Load the draft a request names from the drafts dir; its source (the snapshot every cell runs)."""
    if not isinstance(body, dict):
        raise ValueError("the body is a JSON object")
    name = draftstore.name_of(str(body.get("strategy", "")))
    try:
        src = draftstore.read(name)
    except FileNotFoundError:
        raise DraftError(f"no draft {name!r} in {draftstore.drafts_dir()}") from None
    register_source(name, src, str(draftstore.path_for(name)))
    return src


def _stamp_req(req: dict, src: str) -> dict:
    req["draft_source"] = src
    req["draft_sha256"] = hashlib.sha256(src.encode("utf-8")).hexdigest()
    return req


def _run_op(op: str, payload: dict):
    if op == "describe":
        return _describe(Path(payload.get("dir") or draftstore.drafts_dir()))
    body = payload.get("body")
    src = _register_for(body)
    if op == "validate_run":
        from . import runner
        return _stamp_req(runner.validate(body), src)
    if op == "validate_grid":
        from . import grid
        g = grid.validate_grid(body)
    else:
        from . import walkforward
        g = walkforward.validate_wf(body)
    for c in g["cells"]:
        _stamp_req(c["req"], src)
    return g


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    op = argv[0] if argv else ""
    try:
        os.nice(5)                     # like a backtest child: never competes with the desk
    except OSError:
        pass
    real_stdout = sys.stdout
    sys.stdout = sys.stderr            # a draft's print() never corrupts the one JSON answer
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        if op not in OPS:
            raise ValueError(f"unknown op {op!r}")
        out = {"ok": True, "result": _run_op(op, payload)}
    except Exception as e:  # noqa: BLE001
        out = {"ok": False, "error": str(e) if isinstance(e, ValueError) else f"{type(e).__name__}: {e}"}
    finally:
        sys.stdout = real_stdout
    real_stdout.write(json.dumps(out, default=str) + "\n")
    real_stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
