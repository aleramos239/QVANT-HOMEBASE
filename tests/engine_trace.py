"""Opt-in pytest plugin for move-only engine refactors: per test, every broker-adapter call and its answer and every
Engine.journal line, in order, plus the engine's files under tmp_path at teardown, written to
$ENGINE_TRACE_DIR/<sha1(nodeid)>.json. Compare two trees with tools/engine_parity.py.

    ENGINE_TRACE_DIR=/tmp/trace_a python -m pytest -p tests.engine_trace tests/test_engine.py ...

Not a test module (no test_ prefix): it only loads with -p."""
import dataclasses
import hashlib
import inspect
import json
import os

import pytest

_cur = None
OUT = os.environ.get("ENGINE_TRACE_DIR")
FILES = ("day-", "labday-", "daybook-", "rotation.json", "groups.json")


def _j(v):
    if dataclasses.is_dataclass(v) and not isinstance(v, type):
        return {"_": type(v).__name__, **{k: _j(x) for k, x in dataclasses.asdict(v).items()}}
    if isinstance(v, dict):
        return {str(k): _j(x) for k, x in sorted(v.items(), key=lambda kv: str(kv[0]))}
    if isinstance(v, (list, tuple, set, frozenset)):
        xs = [_j(x) for x in v]
        return sorted(xs, key=repr) if isinstance(v, (set, frozenset)) else xs
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    return f"<{type(v).__name__}>"


def _wrap(cls, name, fn):
    if inspect.iscoroutinefunction(fn):
        async def w(self, *a, **k):
            if _cur is not None:
                _cur.append(["call", cls.__name__, getattr(self, "account_id", None), name, _j(a), _j(k)])
            r = await fn(self, *a, **k)
            if _cur is not None:
                _cur.append(["ret", cls.__name__, getattr(self, "account_id", None), name, _j(r)])
            return r
    else:
        def w(self, *a, **k):
            if _cur is not None:
                _cur.append(["call", cls.__name__, getattr(self, "account_id", None), name, _j(a), _j(k)])
            return fn(self, *a, **k)
    w.__wrapped__ = fn
    return w


def _subs(c):
    for s in c.__subclasses__():
        yield s
        yield from _subs(s)


def pytest_collection_finish(session):
    from homebase import engine as engine_mod
    from homebase.broker.base import BrokerAdapter
    api = [n for n, f in vars(BrokerAdapter).items() if callable(f) and not n.startswith("__")]
    for c in [BrokerAdapter, *_subs(BrokerAdapter)]:
        for n in api:
            f = c.__dict__.get(n)
            if callable(f) and not isinstance(f, (staticmethod, classmethod)):
                setattr(c, n, _wrap(c, n, f))
    real = engine_mod.Engine.journal

    def journal(self, event, **data):
        if _cur is not None:
            _cur.append(["journal", event, _j(data)])
        return real(self, event, **data)
    engine_mod.Engine.journal = journal


@pytest.hookimpl(tryfirst=True)         # before the fixtures: an Engine a fixture builds journals too
def pytest_runtest_setup(item):
    global _cur
    _cur = []


def pytest_runtest_teardown(item):
    global _cur
    rows, _cur = _cur, None
    if not OUT or rows is None:
        return
    files = {}
    tp = item.funcargs.get("tmp_path") if hasattr(item, "funcargs") else None
    if tp is not None:
        for p in sorted(tp.rglob("*")):
            if p.is_file() and p.name.startswith(FILES):
                try:
                    files[str(p.relative_to(tp))] = json.loads(p.read_text())
                except Exception:  # noqa: BLE001
                    files[str(p.relative_to(tp))] = "<unreadable>"
    if not rows and not files:
        return
    os.makedirs(OUT, exist_ok=True)
    h = hashlib.sha1(item.nodeid.encode()).hexdigest()[:16]
    with open(os.path.join(OUT, h + ".json"), "w") as f:
        json.dump({"nodeid": item.nodeid, "rows": rows, "files": files}, f)
