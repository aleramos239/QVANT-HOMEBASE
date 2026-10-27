"""homebase/data, homebase/desk and homebase/store hold what used to be flat homebase/*.py modules. Every module that existed before
the move keeps an old-name stub: the SAME module object under both names (sys.modules, as homebase/charts/session.py is for
core/session), so a monkeypatch through either name, `from homebase.engine import ...` and `python -m homebase.ticks` still reach
the one module. The four modules made on this branch (tickjob, engine_rotation, engine_dayrules, engine_kill) have no old name.
Do not delete a stub: tools/, research/ and the launchd jobs import and run them."""
import importlib
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FOLDERS = {
    "data": "ticks tickarchive tickcoverage tickmassive datawatch marketdata feed atrbars tickjob".split(),
    "desk": ("engine engine_lab engine_groups engine_rotation engine_dayrules engine_kill daystate labdesk labcfg timer leveltimer "
             "levels dayrules rules inactive risk trading desk_api equity bothistory metrics review").split(),
    "store": "draftstore ideastore secrets_store arsenal".split(),
}
NO_OLD_NAME = {"tickjob", "engine_rotation", "engine_dayrules", "engine_kill"}
WITH_OLD_NAME = [(pkg, m) for pkg, ms in FOLDERS.items() for m in ms if m not in NO_OLD_NAME]
STAY_TOP_LEVEL = "server paths config contracts symbols netguard gate qos".split()


@pytest.mark.parametrize("pkg,mod", WITH_OLD_NAME)
def test_the_old_name_is_the_same_module_object(pkg, mod):
    new = importlib.import_module(f"homebase.{pkg}.{mod}")
    old = importlib.import_module(f"homebase.{mod}")
    assert old is new and sys.modules[f"homebase.{mod}"] is new and getattr(sys.modules["homebase"], mod) is new


@pytest.mark.parametrize("pkg,mod", [(p, m) for p, ms in FOLDERS.items() for m in ms])
def test_the_file_lives_in_its_folder(pkg, mod):
    assert (ROOT / "homebase" / pkg / f"{mod}.py").is_file()
    stub = ROOT / "homebase" / f"{mod}.py"
    assert stub.is_file() is ((pkg, mod) in WITH_OLD_NAME)
    assert stub.is_file() is False or stub.stat().st_size < 1500          # a stub, not a second copy of the module


@pytest.mark.parametrize("mod", sorted(NO_OLD_NAME))
def test_a_module_made_on_this_branch_has_no_old_name(mod):
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(f"homebase.{mod}")


@pytest.mark.parametrize("mod", STAY_TOP_LEVEL)
def test_these_stay_top_level(mod):
    assert (ROOT / "homebase" / f"{mod}.py").read_text().count("sys.modules[__name__]") == 0
    assert importlib.import_module(f"homebase.{mod}").__name__ == f"homebase.{mod}"


def test_a_patch_through_the_old_name_reaches_the_moved_module(monkeypatch):
    import homebase.desk.timer as timer
    monkeypatch.setattr("homebase.timer.PRESTAGE_READ_S", 123.5)
    assert timer.PRESTAGE_READ_S == 123.5


def test_the_old_name_imported_first_in_a_fresh_interpreter_is_the_same_module():
    code = ("import homebase.engine as a, homebase.ticks as b, homebase.draftstore as c, "
            "homebase.desk.engine as d, homebase.data.ticks as e, homebase.store.draftstore as f; "
            "assert a is d and b is e and c is f")
    subprocess.run([sys.executable, "-c", code], check=True, cwd=ROOT, timeout=60)


def test_the_command_lines_still_run_under_the_old_names():
    for mod in ("ticks", "review", "secrets_store"):
        r = subprocess.run([sys.executable, "-m", f"homebase.{mod}", "--help"], cwd=ROOT, capture_output=True, text=True, timeout=60)
        assert "Traceback" not in r.stderr and "RuntimeWarning" not in r.stderr, (mod, r.stderr)
        assert r.stdout.strip() or r.stderr.strip(), mod
