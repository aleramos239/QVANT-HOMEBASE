"""Sending a promoted strategy from the Mac's Desk to the server's (homebase/labrun/receive.py on the server,
deploy/linux/send_strategy.py on the Mac). Two throwaway stores stand for the two machines: never the real folders, never ssh."""
import contextlib
import hashlib
import importlib.util
import io
import json
import shlex
from pathlib import Path

import pytest

from homebase.labrun import receive, store

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("send_strategy", REPO / "deploy" / "linux" / "send_strategy.py")
ss = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ss)

SRC = "class X: pass\n"
SHA = hashlib.sha256(SRC.encode()).hexdigest()


def rec(name="nq_x", **kw):
    return {"name": name, "id": f"draft_{name}", "label": name, "root": "NQ", "source": SRC, "sha256": SHA, "params": {"rr": 1.0},
            "qty": 1, "run": {"id": "r1"}, "notes": [], "promoted_utc": "2026-10-28T20:00:00+00:00", "enabled": True,
            "session_window": ["09:25", "16:00"], "bar_minutes": 1, **kw}


@pytest.fixture
def machines(tmp_path):
    mac, srv = tmp_path / "mac", tmp_path / "srv"
    mac.mkdir(), srv.mkdir()

    def run(cmd, stdin=None):        # what the server would answer: the receiver, in this process, on the server's store
        args = shlex.split(cmd.split("homebase.labrun.receive", 1)[1]) + ["--root", str(srv)]
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = receive.main(args, io.StringIO(stdin or ""))
        return rc, out.getvalue().strip()
    return mac, srv, run


def put_mac(mac, **kw):
    store.put(rec(**kw), str(mac))


def go(machines, name="nq_x", **kw):
    mac, srv, run = machines
    return ss.send(name, run=run, mac_at=str(mac), **kw)


def test_a_new_strategy_lands_off_with_nothing_but_its_record(machines):
    mac, srv, _ = machines
    put_mac(mac, enabled=True)                               # the Mac's copy is ON: only the server's switch is forced OFF
    ok, say = go(machines, go=True)
    got = store.get("nq_x", str(srv))
    assert ok and "SENT" in say[-1] and "WARNING" in say[0]  # the Mac's own ON copy is warned about
    assert got["enabled"] is False and {**got, "enabled": True} == rec()
    assert sorted(p.name for p in srv.iterdir()) == ["nq_x.json"]    # no days, journal, sidecar, heartbeat


def test_a_dry_run_writes_nothing(machines):
    mac, srv, _ = machines
    put_mac(mac)
    ok, say = go(machines)
    assert ok and "dry run" in say[-1] and not list(srv.iterdir())


def test_sending_again_is_a_no_op_even_when_the_server_switched_it_on(machines):
    mac, srv, _ = machines
    put_mac(mac)
    go(machines, go=True)
    store.set_enabled("nq_x", True, str(srv))
    ok, say = go(machines, go=True)
    assert ok and "Already on the server" in say[-1] and store.get("nq_x", str(srv))["enabled"] is True


def test_a_different_version_is_refused_unless_replace_and_then_only_while_off_and_unbooked(machines):
    mac, srv, _ = machines
    put_mac(mac)
    go(machines, go=True)
    src2 = "class Y: pass\n"
    put_mac(mac, source=src2, sha256=hashlib.sha256(src2.encode()).hexdigest(), promoted_utc="2026-10-29T20:00:00+00:00")
    ok, say = go(machines, go=True)
    assert not ok and "DIFFERENT" in say[-1] and store.get("nq_x", str(srv))["sha256"] == SHA     # untouched
    store.set_enabled("nq_x", True, str(srv))
    ok, say = go(machines, go=True, replace=True)
    assert not ok and "is ON" in say[-1]
    store.set_enabled("nq_x", False, str(srv))
    (srv / "nq_x.desk.json").write_text(json.dumps({"book": [{"account": "A1", "qty": 1}]}))
    ok, say = go(machines, go=True, replace=True)
    assert not ok and "booked" in say[-1] and store.get("nq_x", str(srv))["sha256"] == SHA
    (srv / "nq_x.desk.json").write_text(json.dumps({"book": []}))
    ok, say = go(machines, go=True, replace=True)
    assert ok and store.get("nq_x", str(srv))["source"] == src2 and store.get("nq_x", str(srv))["enabled"] is False
    assert len(list((srv / receive.KEPT).glob("nq_x-*.json"))) == 1                               # the old one is kept


def test_code_that_no_longer_matches_its_hash_never_leaves_the_mac_and_is_refused_there_too(machines):
    mac, srv, run = machines
    put_mac(mac, source="class Z: pass\n")                                                      # hash is of SRC: tampered
    ok, say = go(machines, go=True)
    assert not ok and "hash" in say[-1] and not list(srv.iterdir())
    rc, out = run("x homebase.labrun.receive nq_x --go", json.dumps(rec(source="class Z: pass\n")))   # the receiver judges alone, too
    assert rc == 2 and "hash" in json.loads(out)["why"] and not list(srv.iterdir())


def test_the_receiver_refuses_what_the_desk_could_not_make_a_strategy_of_and_what_is_archived(machines):
    mac, srv, run = machines
    rc, out = run("x homebase.labrun.receive nq_x --go", json.dumps(rec(root="ZZ", exec_root="QQ")))
    assert rc == 2 and "could not make a strategy" in json.loads(out)["why"]
    rc, out = run("x homebase.labrun.receive nq_x --go", json.dumps(rec(id="draft_other")))
    assert rc == 2 and "not this strategy's own" in json.loads(out)["why"]
    store.put(rec(), str(srv))
    store.archive_copy("nq_x", str(srv))
    store.remove("nq_x", str(srv))
    put_mac(mac)
    ok, say = go(machines, go=True)
    assert not ok and "Archive" in say[-1] and store.get("nq_x", str(srv)) is None


def test_a_name_that_is_not_on_this_macs_desk_says_so(machines):
    ok, say = go(machines, name="nq_missing", go=True)
    assert not ok and "Promote" in say[0]
    ok, say = go(machines, name="../etc/passwd", go=True)
    assert not ok


def test_the_server_must_have_the_receiver_the_store_and_main(monkeypatch):
    monkeypatch.setattr(ss, "main_rev", lambda: "abcdef1234567890")
    right = lambda c, s=None: (0, "abcdef1234567890\n\n" + json.dumps({"ok": True, "store": ss.SERVER_STORE}))
    assert ss.server_ready(right) is None
    assert "did not answer" in ss.server_ready(lambda c, s=None: (255, ""))
    assert "receiving code" in ss.server_ready(lambda c, s=None: (0, "abcdef1234567890\n\nNo module named homebase.labrun.receive"))
    assert "not the server's own store" in ss.server_ready(
        lambda c, s=None: (0, "abcdef1234567890\n\n" + json.dumps({"ok": True, "store": "/root/.homebase/desklab"})))
    behind = lambda c, s=None: (0, "0000000000000000\n\n" + json.dumps({"ok": True, "store": ss.SERVER_STORE}))
    assert "not caught up" in ss.server_ready(behind) and ss.server_ready(behind, behind_ok=True) is None
