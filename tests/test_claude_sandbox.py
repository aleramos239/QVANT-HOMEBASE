"""The DRAFT backtest sandbox (homebase/backtest/sandbox.py + draft.sb): what a draft can NOT do, proven by
running drafts that try -- through the chart service's own run path -- plus fail-closed, the wall-clock
timeout and the process-group kill on cancel."""
from __future__ import annotations

import datetime as dt
import os
import socket
import subprocess
import sys
import sysconfig
import threading
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from homebase import draftstore
from homebase.backtest import runner, sandbox
from homebase.charts.server import create_app
from tests.backtest_util import D1, nq_archive

REPO = Path(__file__).resolve().parent.parent
MARCH = {"kind": "custom", "start": "2024-03-01", "end": "2024-03-31"}
HEAD = "from __future__ import annotations\nfrom homebase.strategies.base import Input, Strategy\n"
CLASS = ('\n\nclass Probe(Strategy):\n    name = "probe"\n    root = "NQ"\n    session_independent = True\n'
         '    def times(self):\n        return ["09:30:00"]\n')

pytestmark = pytest.mark.skipif(not sandbox.available(), reason="no working sandbox-exec on this machine")


def client(tmp_path):
    app = create_app(roots=["NQ"], base=nq_archive(tmp_path / "ticks"), replay=D1, speed=1,
                     start_et=dt.time(9, 30), state=tmp_path / "state")
    return TestClient(app, base_url="http://localhost:8852")


def poll(c, rid, s=60.0):
    t = time.monotonic() + s
    while time.monotonic() < t:
        st = c.get(f"/api/tester/run/{rid}").json()
        if st["status"] in ("done", "error", "cancelled"):
            return st
        time.sleep(0.05)
    raise AssertionError("never finished")


def probe_draft(name: str, body: str) -> None:
    """A draft whose import runs `body` (which must raise RuntimeError('probe:<outcome>'))."""
    draftstore.write(name, HEAD + body + CLASS)


def run_probe(tmp_path, name: str) -> str:
    with client(tmp_path) as c:
        r = c.post("/api/tester/run", json={"strategy": f"draft_{name}", "range": MARCH})
        assert r.status_code == 200, r.text
        st = poll(c, r.json()["id"])
    assert st["status"] == "error", st
    return st["error"]


ATTEMPT = '''
def _attempt(fn):
    try:
        fn()
    except PermissionError:
        raise RuntimeError("probe:PermissionError")
    except Exception as e:
        raise RuntimeError("probe:" + type(e).__name__)
    raise RuntimeError("probe:ALLOWED")
'''


def test_a_draft_cannot_read_the_desk_key_or_the_desk_state(tmp_path):
    """The checkout's own homebase/.state (a planted secret: the profile's explicit deny) and the LIVE desk's
    desk.key (outside every allow). A path must EXIST for the probe to mean anything: metadata lookups are
    allowed, so a missing file answers FileNotFoundError before any read is checked."""
    state = REPO / "homebase" / ".state"
    state.mkdir(exist_ok=True)
    planted = state / f"sandbox-secret-{uuid.uuid4().hex}"
    planted.write_text("secret")
    live_key = Path.home() / "ramos-quant-homebase" / "homebase" / ".state" / "desk.key"
    try:
        targets = [planted] + ([live_key] if live_key.exists() else [])
        for i, target in enumerate(targets):
            probe_draft(f"reads_key{i}", ATTEMPT + f"_attempt(lambda: open({str(target)!r}, 'rb').read())\n")
            assert "probe:PermissionError" in run_probe(tmp_path, f"reads_key{i}"), target
        probe_draft("lists_state", ATTEMPT + f"import os\n_attempt(lambda: os.listdir({str(state)!r}))\n")
        assert "probe:PermissionError" in run_probe(tmp_path, "lists_state")
    finally:
        planted.unlink()


@pytest.mark.parametrize("rel", [".zshrc", ".ssh", ".homebase"])
def test_a_draft_cannot_read_home_secrets(tmp_path, rel):
    p = Path.home() / rel
    if not p.exists():
        pytest.skip(f"no ~/{rel} on this machine")
    if p.is_dir():
        probe_draft("reads_home", ATTEMPT + f"import os\n_attempt(lambda: os.listdir({str(p)!r}))\n")
        assert "probe:PermissionError" in run_probe(tmp_path, "reads_home")
        return
    probe_draft("reads_home", ATTEMPT + f"_attempt(lambda: open({str(p)!r}, 'rb').read())\n")
    assert "probe:PermissionError" in run_probe(tmp_path, "reads_home")


def test_a_draft_cannot_open_a_socket_even_to_localhost(tmp_path):
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    srv.settimeout(0.2)
    port = srv.getsockname()[1]
    try:
        probe_draft("phones_home", ATTEMPT + "import socket\n"
                    f"_attempt(lambda: socket.create_connection(('127.0.0.1', {port}), timeout=2))\n")
        assert "probe:PermissionError" in run_probe(tmp_path, "phones_home")
        with pytest.raises(socket.timeout):
            srv.accept()                      # nothing ever connected
        probe_draft("desk_port", ATTEMPT + "import socket\n"
                    "_attempt(lambda: socket.create_connection(('127.0.0.1', 8850), timeout=2))\n")
        assert "probe:PermissionError" in run_probe(tmp_path, "desk_port")
    finally:
        srv.close()


def test_a_draft_cannot_write_into_the_venv_or_the_repo(tmp_path):
    site = Path(sysconfig.get_paths()["purelib"])
    target = site / "sitecustomize.py"
    existed = target.exists()
    probe_draft("plants_hook", ATTEMPT + f"_attempt(lambda: open({str(target)!r}, 'x').close())\n")
    try:
        assert "probe:PermissionError" in run_probe(tmp_path, "plants_hook")
    finally:
        if not existed and target.exists():      # never leave one behind, even when the test fails
            target.unlink()
            pytest.fail("the sandbox let a draft create sitecustomize.py in the venv")
    marker = REPO / "homebase" / f"sandbox_probe_{uuid.uuid4().hex}.py"
    probe_draft("writes_repo", ATTEMPT + f"_attempt(lambda: open({str(marker)!r}, 'x').close())\n")
    try:
        assert "probe:PermissionError" in run_probe(tmp_path, "writes_repo")
    finally:
        assert not marker.exists()


def test_a_draft_cannot_fork_or_exec(tmp_path):
    probe_draft("forks", ATTEMPT + "import subprocess\n_attempt(lambda: subprocess.run(['/bin/echo', 'hi']))\n")
    assert "probe:PermissionError" in run_probe(tmp_path, "forks")


def test_the_run_dir_is_writable_even_under_the_denied_state_dir():
    """Production run dirs live in homebase/.state/tester/runs/<id>: the profile's allow for RUNDIR must win
    over its deny for homebase/.state, while the rest of .state stays unreadable."""
    state = REPO / "homebase" / ".state"
    state.mkdir(exist_ok=True)
    rd = state / f"sandbox-probe-{uuid.uuid4().hex}"
    rd.mkdir()
    tmp = sandbox.private_tmp()
    try:
        code = ("import os, sys\n"
                "open(os.path.join(sys.argv[1], 'ok'), 'w').write('x')\n"
                "try:\n    os.listdir(sys.argv[2])\n    print('LISTED')\nexcept PermissionError:\n    print('denied')\n")
        p = subprocess.run(sandbox.command([sys.executable, "-c", code, str(rd), str(state)],
                                           sandbox.params(run_dir=rd, archive=tmp, cache=tmp, tmp=tmp)),
                           env=sandbox.env(tmp), capture_output=True, text=True, timeout=60, cwd=tmp)
        assert p.returncode == 0, p.stderr
        assert p.stdout.strip() == "denied" and (rd / "ok").read_text() == "x"
    finally:
        sandbox.drop_tmp(tmp)
        sandbox.drop_tmp(rd)


def test_draft_backtests_are_refused_without_a_sandbox(tmp_path, monkeypatch):
    draftstore.write("my_orb", draftstore.DRAFT_TEMPLATE)
    monkeypatch.setattr(sandbox, "available", lambda: False)
    with client(tmp_path) as c:
        r = c.post("/api/tester/run", json={"strategy": "draft_my_orb", "range": MARCH})
        assert r.status_code == 400 and "sandbox" in r.json()["detail"]
        assert c.post("/api/tester/run", json={"strategy": "nq930", "inputs": {"adx_gate": False},
                                               "range": MARCH}).status_code == 200   # built-ins unaffected


def test_runner_exec_refuses_a_draft_outside_the_sandbox(tmp_path):
    draftstore.write("my_orb", draftstore.DRAFT_TEMPLATE)
    rid = runner.prepare({"strategy": "draft_my_orb", "range": MARCH}, tmp_path)
    env = {k: v for k, v in os.environ.items() if k != "HOMEBASE_SANDBOXED"}
    p = subprocess.run([sys.executable, "-m", "homebase.backtest.runner", "exec", str(tmp_path / "runs" / rid),
                        "--archive", str(tmp_path / "a"), "--cache", str(tmp_path / "c")], cwd=REPO, env=env,
                       capture_output=True, text=True, timeout=60)
    assert p.returncode == 2 and "sandbox" in p.stderr


def _hang(name):
    draftstore.write(name, HEAD + CLASS + "    def on_session(self, ctx):\n        while True:\n            pass\n")


def test_a_hung_draft_times_out_its_group_dies_and_the_slot_is_released(tmp_path, monkeypatch):
    monkeypatch.setattr(sandbox, "DRAFT_TIMEOUT_S", 3)
    _hang("spins")
    with client(tmp_path) as c:
        rid = c.post("/api/tester/run", json={"strategy": "draft_spins", "range": MARCH}).json()["id"]
        st = poll(c, rid, 60)
        assert st["status"] == "error" and "timed out" in st["error"], st
        pid = st.get("pid")
        assert pid and not runner._alive(pid)
        # the slot came back: the next run (a built-in) starts and finishes
        rid2 = c.post("/api/tester/run", json={"strategy": "nq930", "inputs": {"adx_gate": False},
                                               "range": MARCH}).json()["id"]
        assert poll(c, rid2)["status"] == "done"


def test_cancel_kills_a_running_draft(tmp_path):
    _hang("spins")
    with client(tmp_path) as c:
        rid = c.post("/api/tester/run", json={"strategy": "draft_spins", "range": MARCH}).json()["id"]
        t = time.monotonic() + 30
        while c.get(f"/api/tester/run/{rid}").json()["status"] != "running":
            assert time.monotonic() < t
            time.sleep(0.05)
        pid = c.get(f"/api/tester/run/{rid}").json()["pid"]
        assert c.post(f"/api/tester/run/{rid}/cancel").json()["status"] == "cancelled"
        time.sleep(0.2)
        assert not runner._alive(pid)
