"""homebase/desk_app/: the parts of the desk server moved out of homebase/server.py (2026-10-26). Guards for the move."""
from __future__ import annotations

import builtins
import dis
import importlib
import importlib.util
import re
import subprocess
import sys
import types
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
DESK_APP = sorted((REPO / "homebase" / "desk_app").glob("*.py"))
MODULES = ["homebase.server"] + [f"homebase.desk_app.{p.stem}" for p in DESK_APP if p.stem != "__init__"] + \
          [f"homebase.routes.{p.stem}" for p in sorted((REPO / "homebase" / "routes").glob("*.py")) if p.stem != "__init__"]


def _codes(co):
    yield co
    for c in co.co_consts:
        if isinstance(c, types.CodeType):
            yield from _codes(c)


def test_every_global_a_moved_body_reads_exists():
    """A name a moved closure reads but its new module lacks would raise NameError only when that line runs."""
    bad = []
    for name in MODULES:
        m = importlib.import_module(name)
        for co in _codes(compile(Path(m.__file__).read_text(), m.__file__, "exec")):
            for ins in dis.get_instructions(co):
                if ins.opname in ("LOAD_GLOBAL", "LOAD_NAME") and ins.argval not in vars(m) \
                        and not hasattr(builtins, ins.argval):
                    bad.append((name, co.co_name, ins.argval))
    assert bad == []


def test_no_desk_app_module_reads_state_dir_itself():
    """Tests point homebase.server.state_dir at a temp dir: a part importing paths would write the real .state."""
    for p in DESK_APP:
        assert not re.search(r"from \.\.paths|import paths|homebase\.paths", p.read_text()), p.name


def test_no_desk_app_module_references_drafts():
    for p in DESK_APP:
        assert not re.search(r"draftstore|drafthost|HOMEBASE_DRAFTS_DIR|\.homebase/strategies", p.read_text()), p.name


def test_a_desk_app_change_restarts_the_desk_only():
    spec = importlib.util.spec_from_file_location("vpssync_plan", REPO / "deploy" / "linux" / "vpssync_plan.py")
    vp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vp)
    for p in DESK_APP:
        assert vp.plan(REPO, [f"homebase/desk_app/{p.name}"]) == ["service homebase"], p.name


def test_the_runner_and_the_chart_paper_never_load_the_desk_parts():
    code = ("import sys, homebase.labrun.host, homebase.labrun.deskside, homebase.labrun.deskclient, "
            "homebase.labrun.__main__, homebase.charts.paper; "
            "print([m for m in sys.modules if m.startswith('homebase.desk_app')])")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, cwd=REPO, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]"
