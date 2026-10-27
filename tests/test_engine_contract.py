"""The Engine is one class built from mixins (engine.py + engine_lab, engine_groups, engine_rotation, engine_dayrules,
engine_kill). Their contract, made explicit: no name in two of them (a second one would silently win by MRO order),
every self.<name> a mixin reads exists on a built Engine, and the Lab's lazy memory is never made in __init__."""
from __future__ import annotations

import ast
import inspect
import textwrap

from homebase.config import AccountCfg, AppCfg, StrategyCfg
from homebase.desk.engine import Engine
from tests.test_engine import FakeAdapter

# Made by the Lab through self.__dict__ on first use, never in __init__: _lab_mem reads labday-<date>.json only while
# self.__dict__.get("_lab") is None, so an empty one made at start would forget the open rounds' order ids on a restart.
LAB_LAZY = ("_lab", "_lab_day", "_lab_names", "_lab_disk_day", "_lab_tries", "_lab_said")


def _engine(tmp_path):
    cfg = AppCfg(armed=True, accounts={"a": AccountCfg(keyring_key="k", account_name="A")},
                 book={"nq930": [{"account": "a", "qty": 1}]},
                 strategies={"nq930": StrategyCfg(symbol="NQ", qty=1, offset_pts=10.0, sl_pts=5.0, tp_pts=15.0,
                                                  enabled=True)})
    return Engine(cfg, {"a": FakeAdapter("a")}, root=tmp_path)


def _upward(cls) -> set:
    """self.<name> the mixin reads but neither defines nor assigns itself."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(cls)))
    used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
            and n.value.id == "self"}
    stored = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name)
              and n.value.id == "self" and isinstance(n.ctx, ast.Store)}
    return used - set(vars(cls)) - stored


def test_no_name_is_defined_twice_in_the_engine():
    seen: dict = {}
    for c in Engine.__mro__[:-1]:
        for n in vars(c):
            if not n.startswith("__"):
                assert n not in seen, f"{n}: in {seen[n]} and {c.__name__}"
                seen[n] = c.__name__


def test_every_name_a_mixin_reads_exists_on_the_engine(tmp_path):
    eng = _engine(tmp_path)
    for mixin in Engine.__mro__[1:-1]:
        missing = sorted(n for n in _upward(mixin) if n not in LAB_LAZY and not hasattr(eng, n))
        assert not missing, f"{mixin.__name__} reads {missing}, which no Engine has"


def test_the_labs_lazy_memory_is_not_made_at_start(tmp_path):
    assert not set(LAB_LAZY) & set(vars(_engine(tmp_path)))
