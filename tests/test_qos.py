"""The QoS split (homebase/qos.py): desk, charts and the Lab's runner run Interactive under launchd; the batch
children they start (backtests, heat-map cells, exports, tick refreshes, bp.py runs) stay at the utility QoS on
macOS, through taskpolicy. Linux (the VPS) starts every child exactly as before."""
from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from homebase import qos

REPO = Path(__file__).resolve().parent.parent
PREFIX = [qos.TASKPOLICY, "-c", "utility"]
PY = sys.executable
REAL = pytest.mark.skipif(not (sys.platform == "darwin" and os.access(qos.TASKPOLICY, os.X_OK)), reason="macOS only")


@pytest.fixture(params=[True, False], ids=["darwin", "linux"])
def darwin(request, monkeypatch):
    monkeypatch.setattr(qos, "DARWIN", request.param)
    monkeypatch.setattr(qos, "TASKPOLICY", sys.executable)        # "there" on any machine
    return request.param


def want(argv: list, darwin: bool) -> list:
    return ([sys.executable, "-c", "utility"] + argv) if darwin else argv


def test_utility_prefixes_on_macos_only(darwin):
    argv = [PY, "-m", "x"]
    out = qos.utility(argv)
    assert out == want(argv, darwin) and out is not argv and argv == [PY, "-m", "x"]


def test_a_program_that_cannot_run_is_left_as_it_is(darwin, tmp_path):
    """Popen must raise the same FileNotFoundError / PermissionError as before: taskpolicy would exit 66 instead."""
    plain = tmp_path / "plain"
    plain.write_text("")
    for argv in (["/nowhere/python3", "-V"], [str(plain)], [str(tmp_path)], ["py", "-V"], ["./py"], []):
        out = qos.utility(argv)
        assert out == argv and out is not argv


def test_no_taskpolicy_no_prefix(monkeypatch):
    monkeypatch.setattr(qos, "DARWIN", True)
    monkeypatch.setattr(qos, "TASKPOLICY", "/nowhere/taskpolicy")
    assert qos.utility(["py"]) == ["py"]


def test_every_batch_child_is_clamped(darwin, tmp_path, monkeypatch):
    from homebase.backtest import runner
    from homebase.charts import export, paper
    from homebase.claude_mcp import blueprint_tools
    from homebase.claude_mcp.client import ToolError
    seen = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **kw: seen.append(argv) or SimpleNamespace())

    with open(tmp_path / "slot", "w") as slot:                        # a built-in strategy's backtest
        proc = runner.launch(tmp_path, PY, tmp_path / "a", tmp_path / "c", slot, ("--no-lock",))
        runner.finish_proc(proc)
        fd = str(slot.fileno())
    assert seen.pop() == want([PY, "-m", "homebase.backtest.runner", "exec", str(tmp_path), "--no-lock", "--archive",
                               str(tmp_path / "a"), "--cache", str(tmp_path / "c"), "--slot-fd", fd], darwin)

    from homebase.backtest import sandbox                             # a DRAFT's: the sandbox-exec command, clamped
    run, sbtmp = tmp_path / "draft", tmp_path / "sbtmp"
    run.mkdir()
    sbtmp.mkdir()
    (run / "request.json").write_text('{"strategy": "draft_x", "draft_source": ""}')
    monkeypatch.setattr(sandbox, "require", lambda: None)
    monkeypatch.setattr(sandbox, "private_tmp", lambda: sbtmp)
    monkeypatch.setattr(sandbox, "command", lambda argv, prm: [PY, "sandboxed", *argv])
    with open(tmp_path / "slot", "w") as slot:
        runner.finish_proc(runner.launch(run, PY, tmp_path / "a", tmp_path / "c", slot))
        fd = str(slot.fileno())
    assert seen.pop() == want([PY, "sandboxed", PY, "-m", "homebase.backtest.runner", "exec", str(run), "--archive",
                               str(tmp_path / "a"), "--cache", str(tmp_path / "c"), "--slot-fd", fd,
                               "--private-cache", str(sbtmp / "tape")], darwin)

    paper.spawn_backtest(tmp_path / "paper")
    assert seen.pop() == want([sys.executable, "-m", "homebase.charts.paper", "backtest", "--folder",
                               str(tmp_path / "paper")], darwin)

    m = export.ExportManager(tmp_path / "ex", archive=tmp_path / "t", depth_base=tmp_path / "d", python=PY,
                             out_dir=tmp_path / "out")
    (tmp_path / "job").mkdir()
    m._launch(tmp_path / "job").hb_log.close()
    assert seen.pop() == want([PY, "-m", "homebase.charts.export", "exec", str(tmp_path / "job"), "--archive",
                               str(tmp_path / "t"), "--depth-base", str(tmp_path / "d"), "--out-dir",
                               str(tmp_path / "out")], darwin)

    script = tmp_path / "bp.py"
    script.write_text("")
    monkeypatch.setenv(blueprint_tools.ENV_BP, str(script))
    monkeypatch.setenv(blueprint_tools.ENV_PYTHON, sys.executable)

    def run(argv, **kw):
        seen.append(argv)
        raise OSError("stop here")
    monkeypatch.setattr(subprocess, "run", run)
    with pytest.raises(ToolError):
        blueprint_tools.BlueprintMixin()._bp(["status", "x"], root=tmp_path)
    assert seen.pop() == want([sys.executable, str(script), "status", "x", f"--root={tmp_path}", "--json"], darwin)
    assert not seen


@REAL
def test_a_clamped_child_is_the_same_process_with_its_fds_output_and_exit_code(tmp_path):
    """taskpolicy execs: the pid Popen returns is the program's (terminate / killpg / wait reach it), an inherited fd
    (the backtest slot) is still open, stderr and the exit code come through, and the child runs at the utility tier."""
    r, w = os.pipe()
    code = ("import os, signal, sys, time\n"                       # the handler first: the test signals after the prints
            "signal.signal(signal.SIGTERM, lambda *a: sys.exit(7))\n"
            "os.fstat(int(sys.argv[1])); print(os.getpid(), flush=True); print('err', file=sys.stderr, flush=True)\n"
            "time.sleep(30)\n")
    p = subprocess.Popen(qos.utility([sys.executable, "-c", code, str(w)]), pass_fds=(w,), stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, start_new_session=True)
    try:
        assert p.stdout.readline().strip() == str(p.pid) and p.stdout.readline().strip() == "err"
        pri = subprocess.run(["ps", "-o", "pri=", "-p", str(p.pid)], capture_output=True, text=True).stdout.strip()
        assert int(pri) <= 20                                              # utility; the default tier is 31
        os.killpg(p.pid, 15)
        assert p.wait(10) == 7
    finally:
        p.kill()
        os.close(r)
        os.close(w)
    assert subprocess.run(qos.utility([sys.executable, "-c", "raise SystemExit(3)"])).returncode == 3


@REAL
def test_a_missing_program_still_raises_as_before(tmp_path):
    plain = tmp_path / "plain"
    plain.write_text("")
    with pytest.raises(FileNotFoundError):
        subprocess.Popen(qos.utility(["/nowhere/python3", "-V"]))
    with pytest.raises(PermissionError):
        subprocess.Popen(qos.utility([str(plain)]))


@pytest.mark.parametrize("label", ["com.ramosquant.homebase", "com.ramosquant.homebase-charts",
                                   "com.ramosquant.homebase-labrun"])
def test_the_app_services_run_interactive(label):
    job = plistlib.loads((REPO / "deploy" / f"{label}.plist.template").read_bytes().replace(b"__REPO__", b"/repo"))
    assert job["Label"] == label and job["ProcessType"] == "Interactive"
