"""tester_api's routes moved to homebase/charts/tester_routes/ (2026-10-26): a name a moved route needs and its module lacks
would only show as a NameError when that branch runs. Every global the code loads must exist, and every `api.<name>` it
reads at call time (the names tests patch on tester_api) must be on tester_api."""
from __future__ import annotations

import ast
import builtins
import dis
import importlib
import types
from pathlib import Path

import pytest

MODULES = ["homebase.charts.tester_api"] + [f"homebase.charts.tester_routes.{m}" for m in ("common", "lab", "desklab", "jobs")]


@pytest.mark.parametrize("name", MODULES)
def test_every_global_the_code_loads_is_defined(name):
    m = importlib.import_module(name)
    todo, seen = [compile(Path(m.__file__).read_text(encoding="utf-8"), m.__file__, "exec")], set()
    while todo:
        c = todo.pop()
        seen |= {i.argval if isinstance(i.argval, str) else i.argrepr.split()[-1]
                 for i in dis.get_instructions(c) if i.opname in ("LOAD_GLOBAL", "LOAD_NAME")}
        todo += [k for k in c.co_consts if isinstance(k, types.CodeType)]
    assert sorted(n for n in seen if n not in vars(m) and not hasattr(builtins, n)) == []


def test_every_name_read_through_api_is_on_tester_api():
    from homebase.charts import tester_api
    read = set()
    for m in MODULES[1:]:
        tree = ast.parse(Path(importlib.import_module(m).__file__).read_text(encoding="utf-8"))
        read |= {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "api"}
    assert read == {"desk_strategy_ids", "DESKLAB_AUTO_UNSEEN", "_run_propsim"}
    assert all(hasattr(tester_api, n) for n in read)
