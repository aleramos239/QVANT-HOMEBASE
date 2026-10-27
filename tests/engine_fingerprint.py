"""Fingerprint of the live Engine for move-only refactors (methods moved between engine.py and its mixins).

For every name on Engine (dir(Engine), resolved through the MRO the way Python does): its bytecode with file, line
numbers and qualname dropped, defaults, closure contents, and the object every global it loads is bound to in ITS
module; plus the homebase.engine namespace. Two trees whose code differs only by where the methods live give the
same JSON, except the new mixin names in the namespace.

    cd <tree> && PYTHONHASHSEED=0 python tests/engine_fingerprint.py > fp.json      (set reprs are seed-ordered)
"""
from __future__ import annotations

import builtins
import dis
import inspect
import json
import sys
import types

sys.path.insert(0, ".")
import homebase.engine as engine_mod  # noqa: E402
from homebase.engine import Engine  # noqa: E402

SKIP = {"__dict__", "__weakref__", "__module__", "__doc__", "__qualname__", "__firstlineno__", "__static_attributes__"}
GLOBAL_OPS = {"LOAD_GLOBAL", "LOAD_NAME", "STORE_GLOBAL", "DELETE_GLOBAL"}


def obj_id(o) -> str:
    if isinstance(o, types.ModuleType):
        return f"module:{o.__name__}"
    if isinstance(o, (type, types.FunctionType, types.BuiltinFunctionType)):
        return f"{getattr(o, '__module__', '?')}:{getattr(o, '__qualname__', o)}"
    if isinstance(o, (int, float, str, bytes, bool, type(None), tuple, frozenset, set, dict, list)):
        return f"value:{o!r}"
    return f"{type(o).__module__}.{type(o).__qualname__}"


def code(c: types.CodeType) -> dict:
    return {"code": c.co_code.hex(), "names": list(c.co_names), "vars": list(c.co_varnames), "free": list(c.co_freevars),
            "cell": list(c.co_cellvars), "flags": c.co_flags,
            "args": [c.co_argcount, c.co_posonlyargcount, c.co_kwonlyargcount], "exc": c.co_exceptiontable.hex(),
            "consts": [code(k) if isinstance(k, types.CodeType) else repr(k) for k in c.co_consts]}


def globals_read(c: types.CodeType) -> set:
    """Every name the code (and the code nested in it) looks up as a global, plus __package__ for a relative import."""
    out = set()
    for ins in dis.get_instructions(c):
        if ins.opname in GLOBAL_OPS:
            out.add(ins.argval if isinstance(ins.argval, str) else ins.argval[1])
        elif ins.opname == "IMPORT_NAME":
            out.add("__package__")                  # what a relative import resolves against
    for k in c.co_consts:
        if isinstance(k, types.CodeType):
            out |= globals_read(k)
    return out


def bound(g: dict, n: str) -> str:
    if n in g:
        return obj_id(g[n])
    return f"builtin:{n}" if hasattr(builtins, n) else "<MISSING>"


def fn_print(raw):
    if isinstance(raw, property):
        return {"property": [fn_print(x) if x else None for x in (raw.fget, raw.fset, raw.fdel)]}
    kind = type(raw).__name__
    f = raw.__func__ if isinstance(raw, (staticmethod, classmethod)) else raw
    f = inspect.unwrap(f)
    if not isinstance(f, types.FunctionType):
        return {"value": obj_id(f)}
    g = f.__globals__
    cells = dict(zip(f.__code__.co_freevars, (obj_id(c.cell_contents) for c in (f.__closure__ or ()))))
    return {"kind": kind, "code": code(f.__code__), "defaults": repr(f.__defaults__), "kwdefaults": repr(f.__kwdefaults__),
            "closure": cells, "globals": {n: bound(g, n) for n in sorted(globals_read(f.__code__))}}


methods = {n: fn_print(inspect.getattr_static(Engine, n)) for n in sorted(dir(Engine)) if n not in SKIP}
ns = {n: obj_id(v) for n, v in sorted(vars(engine_mod).items()) if not n.startswith("__") and n != "Engine"}
json.dump({"methods": methods, "engine_namespace": ns}, sys.stdout, indent=1, sort_keys=True)
