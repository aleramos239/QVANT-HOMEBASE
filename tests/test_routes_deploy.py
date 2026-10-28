"""GET /api/deploy-status: the Settings card "Server updates". Fake state files and a fake git; read-only."""
from __future__ import annotations

import subprocess

from fastapi import FastAPI
from fastapi.testclient import TestClient

from homebase.routes import deploy

MAIN = "d4d4f851" + "0" * 32
OLD = "e48e1e6d" + "1" * 32
WAIT = ("2026-10-27 19:56:23 d4d4f851: 398 files, 2 deleted, units [], restart [homebase] -- waits: "
        "no: lab_nq_x is booked on an account (a runner restart would end its day)")
SHIP = f"2026-10-27 18:05:06 e48e1e6d: 2 files, 0 deleted, units [], restart [homebase] -- shipped. OK {OLD} units=[] restarted=[]"


def fake_git(main=MAIN, ahead="3"):
    def git(repo, *a):
        if a[0] == "log":
            return f"{main}\tfeat: a thing"
        return ahead if a[0] == "rev-list" else None
    return git


def setup(tmp_path, lines=None, plist=True):
    repo, state = tmp_path / "repo", tmp_path / "state"
    (repo / ".git").mkdir(parents=True)
    state.mkdir()
    if lines is not None:
        (state / "vpssync.log").write_text("\n".join(lines) + "\n")
    pl = tmp_path / "x.plist"
    if plist:
        pl.write_text("")
    return repo, state, pl


def test_waiting_says_why_in_plain_words(tmp_path):
    repo, state, pl = setup(tmp_path, [SHIP, WAIT])
    (state / "vpssync.gatewait").write_text("no: lab_nq_x is booked on an account (a runner restart would end its day)\n48\n")
    d = deploy.read(repo, state, pl, fake_git())
    assert d["state"] == "waiting" and d["main"] == {"hash": "d4d4f851", "subject": "feat: a thing"}
    assert d["reason"] == "a Lab strategy (lab_nq_x) is booked on an account: a restart would end its day"
    assert d["server"]["hash"] == "e48e1e6d" and d["ahead"] == 3 and d["waiting_min"] == 96
    assert d["last_attempt"] == "2026-10-27 19:56:23" and d["log"][-1] == WAIT


def test_shipped_means_up_to_date(tmp_path):
    repo, state, pl = setup(tmp_path, [WAIT, SHIP.replace("e48e1e6d", "d4d4f851")])
    d = deploy.read(repo, state, pl, fake_git())
    assert (d["state"], d["ahead"], d["server"]["hash"]) == ("shipped", 0, "d4d4f851")


def test_failed_and_not_imported(tmp_path):
    f = "2026-10-27 19:00:00 d4d4f851: 1 files, 0 deleted, units [], restart [homebase] -- FAILED: the chart service did not come back"
    d = deploy.read(*setup(tmp_path, [SHIP, f]), fake_git())
    assert d["state"] == "failed" and d["reason"] == "the chart service did not come back"
    n = "2026-10-27 19:00:00 d4d4f851: NOT SHIPPED -- it does not import: ImportError: no module x"
    d = deploy.read(*setup(tmp_path / "b", [SHIP, n]), fake_git())
    assert d["state"] == "failed" and d["reason"] == "the commit does not import (ImportError: no module x)"


def test_other_gate_reasons(tmp_path):
    for raw, words in [("no: 09:10-09:35 ET", "it is 09:10-09:35 ET, the Desk is busy at the open"),
                       ("no: APEX 1 has a position or working orders", "an account is not flat: APEX 1 has a position or working orders"),
                       ("block requirements.txt changed: install the new packages on the server by hand first",
                        "new Python packages must be installed on the server by hand first")]:
        assert deploy.plain(raw) == words


def test_a_commit_not_tried_yet_waits(tmp_path):
    d = deploy.read(*setup(tmp_path, [SHIP]), fake_git())
    assert d["state"] == "waiting" and "not tried yet" in d["reason"] and d["ahead"] == 3


def test_not_set_up_and_not_on_this_machine(tmp_path):
    d = deploy.read(*setup(tmp_path, None, plist=False), fake_git())
    assert d["state"] == "not_set_up"
    (tmp_path / "srv").mkdir()
    d = deploy.read(tmp_path / "srv", tmp_path, tmp_path / "none", fake_git())
    assert d["available"] is False and "Not on this machine" in d["reason"]


def test_odd_files_never_raise(tmp_path):
    repo, state, pl = setup(tmp_path, ["garbage", "\xff", "2026-10-27 19:00:00 d4d4f851: waits -- the plan could not be read"])
    (state / "vpssync.gatewait").write_text("x\nnot a number\n")
    assert deploy.read(repo, state, pl, fake_git())["reason"] == "the plan could not be read"
    assert deploy.read(repo, state, pl, lambda *a: None)["reason"] == "main could not be read"
    (state / "vpssync.log").write_bytes(b"\xff\xfe\x00")
    assert deploy.read(repo, state, pl, fake_git())["state"] == "waiting"


def test_the_route_is_read_only(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    (repo / "homebase" / "static").mkdir(parents=True)
    (repo / ".git").mkdir()
    state = repo / "homebase" / ".state"
    state.mkdir()
    (state / "vpssync.log").write_text(WAIT + "\n")
    monkeypatch.setattr(deploy.Path, "home", lambda: tmp_path)
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, f"{MAIN}\tsubject" if cmd[3] == "log" else "2", "")
    monkeypatch.setattr(deploy.subprocess, "run", run)
    app = FastAPI()
    deploy.register(app, STATIC=repo / "homebase" / "static")
    before = sorted(p.name for p in tmp_path.rglob("*"))
    r = TestClient(app).get("/api/deploy-status")
    assert r.status_code == 200 and r.json()["state"] == "waiting"
    assert sorted(p.name for p in tmp_path.rglob("*")) == before
    assert calls and all(c[:3] == ["git", "-C", str(repo)] and c[3] in ("log", "rev-list") for c in calls)
    assert TestClient(app).post("/api/deploy-status").status_code == 405


def test_a_doubled_waits_prefix_from_the_copy_time_gate_reads_plain(tmp_path):
    w = WAIT.replace("-- waits: no:", "-- waits: waits: no:")
    d = deploy.read(*setup(tmp_path, [SHIP, w]), fake_git())
    assert d["reason"] == "a Lab strategy (lab_nq_x) is booked on an account: a restart would end its day"


def test_a_long_wait_keeps_the_last_shipped_row_found(tmp_path):
    d = deploy.read(*setup(tmp_path, [SHIP] + [WAIT] * 400), fake_git())    # ~130 KB of waits after it
    assert d["state"] == "waiting" and d["server"]["hash"] == "e48e1e6d" and d["ahead"] == 3
