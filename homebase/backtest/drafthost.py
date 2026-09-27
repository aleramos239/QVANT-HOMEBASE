"""DRAFT strategies in the tester: the catalog, validation and the backtest child's loader.

Listing and validating a draft NEVER runs its code (fix round 1, C1a). Both work from
draftstore.static_meta() -- an AST read of the file -- through a STUB class built here: a plain Strategy
subclass carrying the draft's literal metadata and Input schema, and no behaviour. runner.validate /
grid.validate_grid / walkforward.validate_wf resolve a `draft_*` id to that stub (resolve()), so the
request is checked exactly like a built-in's; the validated request carries the draft's source snapshot
(`draft_source` + sha256).

The code runs in one place only: the backtest child (`runner exec`), which the chart service launches
inside the macOS sandbox (sandbox.py + draft.sb) and which calls register_source() on that snapshot.
The chart service never calls register_source(); its strategies.REGISTRY never holds a draft.
"""
from __future__ import annotations

import hashlib
import sys
import threading
import types
from pathlib import Path

from .. import draftstore
from ..strategies.base import Input, Strategy


class DraftError(ValueError):
    """A draft could not be read or loaded. The message is shown to the user as is."""


# ---------------------------------------------------------------- static (the service side)

def _inputs(meta: dict) -> list[Input]:
    out = []
    for d in meta.get("inputs") or []:
        try:
            out.append(Input(d["key"], d["label"], d["type"], d["default"], d.get("min"), d.get("max"),
                             d.get("step"), tuple(d.get("choices") or ())))
        except (TypeError, KeyError) as e:
            raise DraftError(f"inputs(): {e}") from None
    return out


def stub_class(name: str, source: str) -> type[Strategy]:
    """A Strategy subclass with the draft's literal metadata and schema -- and none of its code."""
    try:
        meta = draftstore.static_meta(source)
    except ValueError as e:
        raise DraftError(str(e)) from None
    schema = _inputs(meta)
    attrs = {"id": draftstore.draft_id(name), "name": meta.get("name") or name, "root": meta["root"],
             "session_independent": bool(meta.get("session_independent", False)),
             "inputs": classmethod(lambda cls: list(schema)), "__doc__": meta.get("doc") or None,
             "__module__": __name__}
    for k in ("session_window", "bar_minutes", "bar_window", "placement_ms"):
        if k in meta:
            attrs[k] = tuple(meta[k]) if isinstance(meta[k], list) else meta[k]
    stub = type(f"Draft_{name}", (Strategy,), attrs)
    try:
        stub(None)                    # the defaults must validate against the schema
    except ValueError as e:
        raise DraftError(f"input defaults: {e}") from None
    return stub


def snapshot(sid: str) -> tuple[type[Strategy], str]:
    """(stub class, source text) for a draft id, read once from the drafts dir."""
    try:
        name = draftstore.name_of(str(sid))
    except ValueError as e:
        raise DraftError(str(e)) from None
    try:
        src = draftstore.read(name)
    except (FileNotFoundError, OSError):
        raise DraftError(f"no draft {name!r} in {draftstore.drafts_dir()}") from None
    return stub_class(name, src), src


def resolve(sid) -> type[Strategy]:
    """The class validation uses: a draft's STUB (never its code), else the built-in."""
    if draftstore.is_draft_id(sid):
        return snapshot(sid)[0]
    from .. import strategies
    return strategies.get(str(sid))


def stamp(req: dict, src: str) -> dict:
    req["draft_source"] = src
    req["draft_sha256"] = hashlib.sha256(src.encode("utf-8")).hexdigest()
    return req


def is_draft_req(req) -> bool:
    return isinstance(req, dict) and draftstore.is_draft_id(req.get("strategy")) and isinstance(
        req.get("draft_source"), str)


_cache: dict = {}
_cache_lock = threading.Lock()


def _stamp_of(base: Path) -> tuple:
    out = []
    for name, p in draftstore.list_files(base):
        try:
            st = p.stat()
        except OSError:
            continue
        out.append((name, st.st_mtime_ns, st.st_size))
    return tuple(out)


def catalog(base: Path | None = None, builtin_ids=()) -> list[dict]:
    """The drafts' catalog entries, read statically (no draft code runs), cached until a file changes --
    failures included. A draft whose metadata cannot be read statically is listed with `error`."""
    base = Path(base) if base is not None else draftstore.drafts_dir()
    stamp_ = _stamp_of(base)
    if not stamp_:
        return []
    key = (str(base), stamp_, tuple(sorted(builtin_ids)))
    with _cache_lock:
        if key in _cache:
            return _cache[key]
    out = []
    for name, p in draftstore.list_files(base):
        sid = draftstore.draft_id(name)
        entry = {"id": sid, "name": name, "draft": True, "file": str(p)}
        if sid in set(builtin_ids):
            continue                                   # never shadow a built-in
        try:
            cls = stub_class(name, p.read_text(encoding="utf-8"))
            out.append({**cls.describe(), "draft": True, "file": str(p),
                        "session_independent": cls.session_independent, "doc": cls.__doc__ or ""})
        except (DraftError, OSError, UnicodeDecodeError) as e:
            out.append({**entry, "error": str(e), "inputs": []})
    with _cache_lock:
        _cache.clear()
        _cache[key] = out
    return out


# ---------------------------------------------------------------- the backtest child ONLY

def register_source(name: str, source: str, origin: str | None = None):
    """Run a draft's source as a module and add its one Strategy subclass (id forced to draft_<name>) to
    THIS process's strategies.REGISTRY. Called only by `runner exec` inside the sandbox."""
    from .. import strategies
    draftstore.validate_name(name)
    modname = f"homebase_draft_{name}"
    mod = types.ModuleType(modname)
    mod.__file__ = origin or f"<draft {name}>"
    sys.modules[modname] = mod
    try:
        exec(compile(source, mod.__file__, "exec", dont_inherit=True), mod.__dict__)
    except SyntaxError as e:
        raise DraftError(f"SyntaxError: {e.msg} (line {e.lineno})") from None
    except Exception as e:  # noqa: BLE001 -- the author must see what broke
        raise DraftError(f"{type(e).__name__} while loading the draft: {e}") from None
    found = [v for v in vars(mod).values()
             if isinstance(v, type) and issubclass(v, Strategy) and v is not Strategy and v.__module__ == modname]
    if len(found) != 1:
        raise DraftError(f"a draft defines exactly one Strategy subclass (found {len(found)})")
    cls = found[0]
    cls.id = draftstore.draft_id(name)
    strategies.REGISTRY[cls.id] = cls
    return cls
