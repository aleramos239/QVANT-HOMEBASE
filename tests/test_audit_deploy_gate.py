"""Audit 2026-10-27, deploy group: the vpssync gate fails closed, is asked again on the server before the files and the
restarts, and the units / installers carry the priority and OOM fixes."""
from __future__ import annotations

import importlib.util
import os
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

REPO = Path(__file__).resolve().parents[1]
L = REPO / "deploy" / "linux"
spec = importlib.util.spec_from_file_location("vpssync_gate", L / "vpssync_gate.py")
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)
ET = ZoneInfo("America/New_York")
TUE_NOON = datetime(2026, 10, 27, 12, 0, tzinfo=ET)
FLAT = {"connected": True, "working_orders": 0, "open_position_count": 0, "cache_seeded": True}


def v(accounts, now=TUE_NOON, runner=False, book=None):
    return g.verdict({"accounts": accounts, "book": book or {}}, now, runner)


def test_flat_and_seeded_ships():
    assert v({"a": FLAT}) == "ok"


def test_unreadable_status_waits():
    assert g.verdict(None, TUE_NOON, False).startswith("no:")
    assert g.verdict({}, TUE_NOON, False).startswith("no:")


def test_disconnected_or_unseeded_account_waits():
    assert v({"a": {"connected": False}}, book={"s": [{"account": "a"}]}).startswith("no:")   # booked: its position is unknown
    assert v({"a": {**FLAT, "working_orders": None}}).startswith("no:")
    assert v({"a": {**FLAT, "cache_seeded": False}}).startswith("no:")
    assert v({"a": {**FLAT, "open_position_count": 1}}).startswith("no:")


def test_runner_restart_blocks_on_a_booked_strategy_at_night_but_not_on_the_weekend():
    book = {"lab_x": ["acct"]}
    night = datetime(2026, 10, 27, 21, 0, tzinfo=ET)
    sat = datetime(2026, 10, 24, 12, 0, tzinfo=ET)
    assert v({"a": FLAT}, night, True, book).startswith("no:")
    assert v({"a": FLAT}, sat, True, book) == "ok"
    assert v({"a": FLAT}, night, False, book) == "ok"


def test_the_owners_force_file_skips_only_the_booked_rule_and_expires(tmp_path, monkeypatch):
    book, night = {"lab_x": ["acct"]}, datetime(2026, 10, 27, 21, 0, tzinfo=ET)
    assert g.verdict({"accounts": {"a": FLAT}, "book": book}, night, True, True) == "ok"
    assert g.verdict({"accounts": {"a": {**FLAT, "open_position_count": 1}}, "book": book}, night, True, True).startswith("no:")
    f = tmp_path / "force_runner"
    monkeypatch.setattr(g, "FORCE_RUNNER", str(f))
    assert g.forced() is False
    f.write_text("")
    assert g.forced() is True
    old = f.stat().st_mtime - 3600
    os.utime(f, (old, old))
    assert g.forced() is False


def test_the_gate_script_exits_closed_when_the_desk_is_down(monkeypatch):
    def boom(*a, **k):
        raise OSError("refused")
    monkeypatch.setattr(g.urllib.request, "urlopen", boom)
    assert g.main(["x", "0"]).startswith("no:")


def _remote(tmp_path, gate_cmd):
    """run vpssync_remote.sh with stub systemctl/chown/id against a temp tree; returns (rc, out, dest)"""
    dest = tmp_path / "dest"; dest.mkdir(exist_ok=True)
    (dest / "a.txt").write_text("old")
    stage_src = tmp_path / "src"; stage_src.mkdir(); (stage_src / "a.txt").write_text("new")
    tar = tmp_path / "x.tar"
    subprocess.run(["tar", "-cf", str(tar), "-C", str(stage_src), "a.txt"], check=True)
    dele = tmp_path / "x.del"; dele.write_text("")
    bin_ = tmp_path / "bin"; bin_.mkdir()
    for n in ("systemctl", "chown"):
        (bin_ / n).write_text("#!/bin/sh\necho $0 $@ >> %s/calls\n" % tmp_path); (bin_ / n).chmod(0o755)
    (bin_ / "curl").write_text("#!/bin/sh\nexit 0\n"); (bin_ / "curl").chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_}:{os.environ['PATH']}", "VPSSYNC_DEST": str(dest), "VPSSYNC_SYNC": str(tmp_path / "sync"),
           "VPSSYNC_USER": os.environ.get("USER", "root")}
    (tmp_path / "gate.sh").write_text("#!/bin/sh\n" + gate_cmd + "\n")
    env["VPSSYNC_SETTLE"] = "1"
    env["VPSSYNC_GATE"] = f"sh {tmp_path / 'gate.sh'} --"
    r = subprocess.run(["bash", str(L / "vpssync_remote.sh"), "rev1", str(tar), str(dele), "", "homebase"],
                       env=env, capture_output=True, text=True)
    return r, dest, tmp_path


def test_remote_waits_and_touches_nothing_when_the_gate_says_no(tmp_path):
    r, dest, _ = _remote_with_gate(tmp_path, "echo 'no: a position'")
    assert r.returncode == 3, r.stdout + r.stderr
    assert (dest / "a.txt").read_text() == "old"
    assert not (tmp_path / "sync" / "rev").exists() and not (tmp_path / "sync" / "failed").exists()
    assert "restart" not in (tmp_path / "calls").read_text() if (tmp_path / "calls").exists() else True


def test_remote_ships_when_the_gate_says_ok(tmp_path):
    r, dest, _ = _remote_with_gate(tmp_path, "echo ok")
    assert r.returncode == 0, r.stdout + r.stderr
    assert (dest / "a.txt").read_text() == "new"
    assert (tmp_path / "sync" / "rev").read_text().strip() == "rev1"
    chowns = [l for l in (tmp_path / "calls").read_text().splitlines() if "chown" in l]
    assert chowns and all(str(dest) not in l for l in chowns)       # the stage only, never the whole checkout


def _remote_with_gate(tmp_path, gate_out):
    d = tmp_path / "dest"; (d / "deploy" / "linux").mkdir(parents=True)
    (d / "deploy" / "linux" / "vpssync_gate.py").write_text("")
    return _remote(tmp_path, gate_out)


def test_the_unit_files_carry_the_priority_and_oom_settings():
    t = lambda n: (L / n).read_text()
    assert "Nice=0" in t("homebase-labrun.service") and "Nice=10" not in t("homebase-labrun.service")
    assert "OOMScoreAdjust=-900" in t("homebase.service")
    assert "OOMScoreAdjust=300" in t("homebase-charts.service")
    assert "ExecCondition=" in t("homebase-ticks.service")
    assert "nice -n 10 ionice -c3 rsync" in t("tickpull.sh")


def test_ticks_exec_condition_skips_the_trading_day():
    line = next(x for x in (L / "homebase-ticks.service").read_text().splitlines() if x.startswith("ExecCondition="))
    cmd = line.split("/bin/sh -c ", 1)[1].strip("'").replace("%%", "%")
    def run(t, u):
        c = cmd.replace("$(date +%H%M)", t).replace("$(date +%u)", u)
        return subprocess.run(["sh", "-c", c]).returncode
    assert run("1100", "2") != 0 and run("1700", "2") == 0 and run("0500", "2") == 0 and run("1100", "6") == 0


def test_the_mac_installer_never_installs_the_tick_job_and_cleans_an_old_one():
    s = (REPO / "deploy" / "install.sh").read_text()
    labels = [l for l in s.splitlines() if l.startswith(("LABELS=", "  LABELS="))]
    assert labels and all("homebase-ticks" not in l for l in labels)
    assert "RETIRED=(" in s and "homebase-ticks)" in s.split("RETIRED=(", 1)[1].split("\n", 1)[0]


def test_vpssync_uses_the_gate_file_and_tells_once_about_a_blocked_requirements_change():
    s = (L / "vpssync.sh").read_text()
    assert "vpssync_gate.py" in s and "not answering" not in s and "vpssync.blocked" in s
    for t in ("homebase", "homebase-charts", "homebase-labrun"):
        assert "ProcessType" in (REPO / "deploy" / ("com.ramosquant.%s.plist.template" % t)).read_text()


# --- repair pass ---------------------------------------------------------------------------------------------------
def test_an_idle_disconnected_account_does_not_wedge_the_gate_but_a_booked_or_used_one_does():
    gone = {"connected": False, "day": {"closes": 0}}
    assert v({"a": FLAT, "old": gone}) == "ok"                                       # parked / expired, nothing uses it
    assert v({"a": FLAT, "old": gone}, book={"s": [{"account": "old", "qty": 1}]}).startswith("no:")
    assert g.verdict({"accounts": {"a": FLAT, "old": gone},
                      "strategies": {"s": {"accounts": [{"account": "old"}]}}}, TUE_NOON, False).startswith("no:")
    assert v({"a": FLAT, "old": {"connected": False, "day": {"closes": 2}}}).startswith("no:")   # it traded today


def test_remote_gate_that_says_ok_then_no_leaves_files_in_place_but_restarts_nothing(tmp_path):
    flag = tmp_path / "asked"
    r, dest, _ = _remote_with_gate(
        tmp_path, "if [ -f %s ]; then echo 'no: a position'; else touch %s; echo ok; fi" % (flag, flag))
    assert r.returncode == 3 and "waits: no: a position" in r.stdout, r.stdout + r.stderr
    assert (dest / "a.txt").read_text() == "new"                 # the accepted window: copied, not restarted
    calls = (tmp_path / "calls").read_text() if (tmp_path / "calls").exists() else ""
    assert "restart" not in calls
    assert not (tmp_path / "sync" / "rev").exists() and not (tmp_path / "sync" / "failed").exists()


def test_vpssync_tells_once_when_the_gate_has_said_no_for_90_passes():
    s = (L / "vpssync.sh").read_text()
    fn = s[s.index("gate_waits()"):s.index("\nif [ \"${GATE")]
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        script = ('STATE=%s REV=abcdef12345\ntell() { echo TOLD >> "$STATE/told"; }\n%s\n'
                  'for i in $(seq 1 100); do gate_waits "no: x has a position"; done\ngate_waits "no: other"\n') % (d, fn)
        subprocess.run(["bash", "-c", script], check=True)
        assert (Path(d) / "told").read_text().count("TOLD") == 1
