"""deploy/linux/vpssync_plan.py: which server services a change of main restarts, read from the code (the owner,
2026-10-20: every commit on the Mac's main reaches the server by itself, restarting only what the change needs)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("vpssync_plan", REPO / "deploy" / "linux" / "vpssync_plan.py")
vp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vp)


def plan(*changed):
    return vp.plan(REPO, list(changed))


def test_a_page_file_restarts_nothing_it_is_served_from_disk():
    assert plan("homebase/static/index.html", "homebase/static/desklab.js") == []


def test_a_desk_route_restarts_the_desk_only_and_the_shared_store_restarts_all_three_in_order():
    assert plan("homebase/routes/control.py") == ["service homebase"]
    assert plan("homebase/labrun/store.py") == ["service homebase-charts", "service homebase", "service homebase-labrun"]
    assert plan("homebase/charts/tester_api.py") == ["service homebase-charts"]


def test_a_data_file_counts_against_the_nearest_folder_with_code():
    got = plan("homebase/backtest/propsim/rules/lucid-pro-50k@2026-10-02.json")
    assert got and all(x.startswith("service ") for x in got)
    assert got == plan("homebase/backtest/propsim/__init__.py")


def test_tests_tools_docs_and_research_restart_nothing():
    assert plan("tests/test_server.py", "tools/fake_desk.py", "README.md", "research/edge-library/bp.py") == []


def test_a_unit_file_is_installed_again_and_a_new_dependency_blocks_the_ship():
    assert plan("deploy/linux/homebase-charts.service") == ["unit homebase-charts.service", "service homebase-charts"]
    assert plan("deploy/linux/homebase-ticks.timer") == ["unit homebase-ticks.timer"]
    assert plan("requirements.txt")[0].startswith("block ")


def test_relative_imports_and_their_packages_are_followed(tmp_path):
    (tmp_path / "homebase" / "charts").mkdir(parents=True)
    (tmp_path / "homebase" / "labrun").mkdir()
    (tmp_path / "homebase" / "__init__.py").write_text("")
    (tmp_path / "homebase" / "server.py").write_text("from .a import thing\n")
    (tmp_path / "homebase" / "a.py").write_text("def f():\n    from . import b\n")       # inside a function: counts
    (tmp_path / "homebase" / "b.py").write_text("")
    (tmp_path / "homebase" / "charts" / "__init__.py").write_text("")
    (tmp_path / "homebase" / "charts" / "__main__.py").write_text("from ..labrun import store\n")
    (tmp_path / "homebase" / "labrun" / "__init__.py").write_text("")
    (tmp_path / "homebase" / "labrun" / "__main__.py").write_text("import os\n")
    (tmp_path / "homebase" / "labrun" / "store.py").write_text("")
    assert vp.plan(tmp_path, ["homebase/b.py"]) == ["service homebase"]
    assert vp.plan(tmp_path, ["homebase/labrun/store.py"]) == ["service homebase-charts"]
    assert vp.plan(tmp_path, ["homebase/__init__.py"]) == ["service homebase-charts", "service homebase", "service homebase-labrun"]
