"""LOCK of the hand-over from phases 3 and 4 to phases 5 and 6: what the REAL freeze (blueprint/freeze.py) and the REAL
out-of-sample test (blueprint/oos.py) leave on disk -- lock.json, test.json, the stores of the read -- is what `bp.py sim` and
`bp.py eval-card` read (propodds.handed). The other tests of phases 5 and 6 build those files by hand (blueprint_synth.py);
here they are written by the toolkit's own commands.

TINY RUNS ONLY, the way the tests of the freeze and of the read make them (tests/blueprint_frozen.py): a lead built on 3
named BUILD days and 2 exit cells with 1 worker, frozen for real; the test days are NOT replayed -- the read's stores are
written from hand-made trades by that helper's stand-in for runner.run_test, in the format the real read writes.
Everything goes to that helper's temp folder.

  pytest tests/test_blueprint_handover.py -q          python tests/test_blueprint_handover.py     the same, one line per test
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(W), str(Path(__file__).resolve().parent)]
import blueprint_frozen as F  # noqa: E402
from blueprint import evalcard as EC  # noqa: E402
from blueprint import oos as OOS  # noqa: E402
from blueprint import propodds as PO  # noqa: E402
from blueprint import runner as RUN  # noqa: E402

NAME, PRO = "bpl_orb", "lucid-pro-50k@2026-09-27b"
IS = F.IS


def setup_function(_=None):
    F.env_on()


def teardown_function(_=None):
    F.env_off()


def test_a_frozen_and_tested_idea_hands_its_test_period_trades_to_the_simulator_and_the_eval_card():
    root, lock = F.frozen(NAME, "p56")
    F.refused(lambda: PO.sim(NAME, PRO, 3, 345.0, root, paths=200), "out-of-sample test is not on file")      # frozen is not tested
    with F.reading("p56"):                           # every locked variant makes $150 a test day, $60 with worse fills
        t = OOS.test(NAME, confirm=True, root=root)
    assert t["status"] == "proven_on_history" == IS.status(NAME, root)
    h = PO.handed(NAME, root)
    K = RUN.test_keys(lock["home"]["key"], lock["store"], "NQ", "15", "nyam")
    assert (h["market"], h["session"], h["bar"], h["lock"]) == ("NQ", "nyam", "15", lock["hash"]) and h["where"] == f"{F.read_out('p56').name}/{K['table']}"
    assert h["span"] == tuple(lock["test_range"]["NQ"][k] for k in ("start", "end")) and h["calendar"] == F.TEST_DAYS
    assert [v["id"] for v in h["variants"]] == lock["variants"] and all((v["test"], v["worse"]) == (8 * 150.0, 8 * 60.0) for v in h["variants"])
    assert [v["id"] for v in h["variants"] if v["frozen"]] == [v for v in lock["variants"] if v in lock["survivors"]]
    assert h["survivors"] and set(h["survivors"]) <= set(lock["survivors"]), "a variant the freeze did not keep never reaches phase 5"
    with F.no_engine():                              # phases 5 and 6 read what is on disk: nothing is run, no tape is opened
        r, c = PO.sim(NAME, PRO, 3, 345.0, root, paths=400), EC.card(NAME, None, root)
    assert [x["line"] for x in r["lines"]] == ["5.1", "5.2", "5.3", "5.4", "5.5"]
    assert (r["lock"], r["locked"], r["survivors"]) == (lock["hash"], len(lock["variants"]), len(h["survivors"]))
    assert r["pool"] == {"days": 8, "traded": 8} and r["chosen"]["variant"] in h["survivors"] and r["status"] == "proven_on_history"
    assert (root / NAME / "sim" / f"{PRO}.json").is_file()
    assert [x["line"] for x in c["lines"]] == [f"6.{i}" for i in range(1, 10)] and c["variant"] == r["chosen"]["variant"] and c["history"]["trades"] == 8
    assert c["size"]["stage_b"] == r["chosen"]["eval"]["size"] and IS.read_idea(NAME, root)["phase"] == 6
    # the command line, as the connector writes it, on the same files
    q = subprocess.run([sys.executable, str(W / "bp.py"), "sim", NAME, f"--account={PRO}", "--attempts=2", "--fee-budget=230", f"--root={root}", "--json"],
                       capture_output=True, text=True, timeout=280, cwd=str(W), stdin=subprocess.DEVNULL)
    got = json.loads(q.stdout)
    assert q.returncode == 0 and got["chosen"]["variant"] == r["chosen"]["variant"] and got["attempts"] == 2, (q.stdout[-300:], q.stderr[-800:])


def test_a_read_that_failed_hands_nothing_over():
    root, _ = F.frozen(NAME, "p56x")
    with F.reading("p56x", worse=lambda cell, i, day: -10.0):                     # line 4.5 fails: NOT PROVEN
        t = OOS.test(NAME, confirm=True, root=root)
    assert t["status"] == "shelved"
    F.refused(lambda: PO.sim(NAME, PRO, 3, 345.0, root, paths=200), "did not pass")
    F.refused(lambda: EC.card(NAME, None, root), "did not pass")
    assert not (root / NAME / "sim").exists() and not (root / NAME / "eval.json").exists()


def test_nothing_was_written_outside_the_temp_folder():
    F.clean()


if __name__ == "__main__":
    import time
    rc = 0
    for name, t in [(k, v) for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]:
        t0 = time.monotonic()
        setup_function()
        try:
            t()
            print(f"PASS {name} ({time.monotonic() - t0:.1f} s)", flush=True)
        except AssertionError as e:
            rc = 1
            print(f"FAIL {name}\n{e}", flush=True)
        finally:
            teardown_function()
    sys.exit(rc)
