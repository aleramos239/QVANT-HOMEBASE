"""runs_list and same_done keep what they read and read a run dir's files again only when one changed (2026-10-26): the
answers are the ones a fresh read gives, the files are not read twice."""
from __future__ import annotations

import json
import os
import types

import pytest

from homebase.backtest import runner
from homebase.backtest.runner import RunManager, prepare, write_json
from tests.test_backtest_runner import body


@pytest.fixture(autouse=True)
def settled(monkeypatch):
    """Files count as settled at once here (the 2 s rule has its own test)."""
    monkeypatch.setattr(runner, "SETTLED_NS", 0)


def reads(monkeypatch):
    seen = []
    real = runner.read_json

    def counting(path, default=None):
        seen.append(path.name)
        return real(path, default)
    monkeypatch.setattr(runner, "read_json", counting)
    return seen


def run_dir(runs, name, strategy, status="done", trades=None):
    d = runs / name
    d.mkdir(parents=True)
    (d / "request.json").write_text(json.dumps({"strategy": strategy, "created": "c", "range": {"holdout": False}}))
    (d / "status.json").write_text(json.dumps({"status": status}))
    if trades is not None:
        (d / "run.json").write_text(json.dumps({"report": {"summary": {"all": {"trades": trades, "net_profit": 1.5}}}}))
    return d


def test_a_row_is_read_again_only_when_one_of_its_files_changed(tmp_path, monkeypatch):
    me = types.SimpleNamespace(runs=tmp_path / "runs")
    a = run_dir(me.runs, "20261026-100000-draft_a-aaaa", "draft_a", trades=3)
    run_dir(me.runs, "20261026-110000-draft_b-bbbb", "draft_b", status="running")
    first = RunManager.runs_list(me)
    seen = reads(monkeypatch)
    assert RunManager.runs_list(me) == first and seen == []
    assert first[1] == {"id": a.name, "strategy": "draft_a", "created": "c", "status": "done", "range": {"holdout": False},
                        "holdout": False, "trades": 3, "net_profit": 1.5}
    first[1]["range"]["holdout"] = True                      # a caller changing its copy changes nothing kept
    write_json(me.runs / "20261026-110000-draft_b-bbbb" / "status.json", {"status": "done"})
    got = RunManager.runs_list(me)
    assert seen == ["request.json", "status.json", "run.json"] and got[0]["status"] == "done" and got[1]["range"] == {"holdout": False}
    RunManager.runs_list(me, 50, "draft_a")
    seen.clear()
    assert [r["id"] for r in RunManager.runs_list(me, 50, "draft_a")] == [a.name] and seen == []


def test_a_file_that_does_not_read_is_never_kept(tmp_path, monkeypatch):
    me = types.SimpleNamespace(runs=tmp_path / "runs")
    d = run_dir(me.runs, "20261026-100000-draft_a-aaaa", "draft_a")
    (d / "status.json").write_text("{not json")
    assert RunManager.runs_list(me)[0]["status"] is None
    seen = reads(monkeypatch)
    RunManager.runs_list(me)
    assert seen == ["request.json", "status.json", "run.json"]


def later(runs, rid, at="20991231-235959"):
    """The run renamed to a later moment (two prepares in one second sort by their random suffix)."""
    (runs / rid).rename(runs / (at + rid[15:]))
    return at + rid[15:]


def test_same_done_is_read_again_when_a_run_is_added_finishes_or_changes(tmp_path, monkeypatch):
    me = types.SimpleNamespace(runs=tmp_path / "runs")
    old = prepare(body(), tmp_path)
    assert RunManager.same_done(me, body()) is None
    write_json(me.runs / old / "status.json", {"id": old, "status": "done"})
    assert RunManager.same_done(me, body()) == old
    seen = reads(monkeypatch)
    assert RunManager.same_done(me, body()) == old and seen == []          # kept: nothing read again
    new = later(me.runs, prepare(body(), tmp_path))                          # newer, queued: not finished
    assert RunManager.same_done(me, body()) == old
    write_json(me.runs / new / "status.json", {"id": new, "status": "done"})
    assert RunManager.same_done(me, body()) == new
    write_json(me.runs / new / "status.json", {"id": new, "status": "error"})
    assert RunManager.same_done(me, body()) == old
    assert RunManager.same_done(me, body(qty=2)) is None
    other = later(me.runs, prepare(body(qty=2), tmp_path), "20991231-235958")  # a run added after "none" was kept
    write_json(me.runs / other / "status.json", {"id": other, "status": "done"})
    assert RunManager.same_done(me, body(qty=2)) == other


def test_files_written_in_the_last_2_seconds_are_read_again(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "SETTLED_NS", 2_000_000_000)
    me = types.SimpleNamespace(runs=tmp_path / "runs")
    d = run_dir(me.runs, "20261026-100000-draft_a-aaaa", "draft_a", trades=3)
    RunManager.runs_list(me)
    seen = reads(monkeypatch)
    RunManager.runs_list(me)
    assert seen == ["request.json", "status.json", "run.json"]
    for f in runner.LISTED:
        old = (d / f).stat().st_mtime_ns - 3_000_000_000
        os.utime(d / f, ns=(old, old))
    RunManager.runs_list(me)
    seen.clear()
    RunManager.runs_list(me)
    assert seen == []
