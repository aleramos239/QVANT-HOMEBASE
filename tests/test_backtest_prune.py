import json
import os
import time

from homebase.backtest import prune

RID = "20260920-101010-nq930-abcd"
RID2 = "20260921-101010-nq930-beef"


def _dir(base, kind, name, age_days, status="done", files=None):
    d = base / kind / name
    d.mkdir(parents=True)
    (d / "status.json").write_text(json.dumps({"status": status}))
    for f, text in (files or {}).items():
        (d / f).write_text(text)
    t = time.time() - age_days * 86400
    for p in [d, *d.iterdir()]:
        os.utime(p, (t, t))
    return d


def test_only_old_unreferenced_finished_folders_are_candidates(tmp_path):
    old = _dir(tmp_path, "runs", RID, 30)
    _dir(tmp_path, "runs", "20261010-101010-nq930-1111", 1)                     # recent
    _dir(tmp_path, "runs", RID2, 30)                                            # referenced
    _dir(tmp_path, "runs", "20260901-101010-nq930-2222", 30, status="running")  # still running
    got = prune.candidates(tmp_path, {RID2}, days=7)
    assert [c[1] for c in got] == [old]
    assert got[0][0] == "runs" and got[0][3] > 7


def test_referenced_finds_ids_in_json_and_skips_caches(tmp_path):
    (tmp_path / "a.json").write_text(json.dumps({"run": RID}))
    (tmp_path / "cache").mkdir()
    (tmp_path / "cache" / "b.json").write_text(json.dumps({"run": RID2}))
    assert prune.referenced([tmp_path]) == {RID}


def test_a_walkforwards_own_spends_move_to_the_shared_ledger(tmp_path):
    line = json.dumps({"ts": "2026-09-28T19:11:30+00:00", "strategy": "nq930", "run_id": RID + "-c00"})
    d = _dir(tmp_path, "walkforward", RID, 30, files={"spends.jsonl": line + "\n"})
    ledger = tmp_path / "spends.jsonl"
    ledger.write_text('{"keep": 1}\n')
    assert prune.keep_spends(d, ledger) == 1
    assert ledger.read_text().splitlines() == ['{"keep": 1}', line]
