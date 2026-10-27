"""/desklab/results keeps each done walk-forward's card block and works it out again only when one of its files changed
(2026-10-26); a prop sim that failed is never kept. The warm-up also scores the Desk groups, so their first ask is a hit."""
import datetime as dt
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

from homebase.backtest import runner
from homebase.charts import deskgroups, tester_api
from homebase.labrun import store
from tests.test_tester_desklab import DESK, HEAD, at_et, c, draft, make_run, promote, wf_result, write_wf  # noqa: F401 -- fixtures and helpers


def age(d, s=1000.0):
    for p in d.iterdir():
        if p.is_file():
            t = p.stat().st_mtime_ns - int(s * 1e9)
            os.utime(p, ns=(t, t))


def setup(c, tmp_path, drafts_dir, make_run, monkeypatch):  # noqa: F811
    scored, fail = [], []

    def fake(trades, req):
        if fail:
            raise ValueError("no prop sim now")
        scored.append(len(trades))
        return {"rules": {"label": "LucidFlex 50K"}, "headline": HEAD, "breach": {}}, False
    monkeypatch.setattr(tester_api, "_run_propsim", fake)
    draft(drafts_dir)
    build = make_run()
    (tmp_path / "state" / "tester" / "runs" / build / "trades.json").write_text("[]")
    assert promote(c, run_id=build, headers=DESK).json()["ok"] is True
    at_et(monkeypatch, 2026, 10, 18, 12, 0)
    write_wf(tmp_path, store.get("nq_bars"), dt.date(2026, 10, 18), result=wf_result())
    wdir = next((tmp_path / "state" / "tester" / "walkforward").iterdir())
    rt = tester_api.tester_router(lambda request: None, tmp_path / "ticks", tmp_path / "state" / "tester")
    reads = []
    real = rt.wfs.result
    monkeypatch.setattr(rt.wfs, "result", lambda gid, *a: reads.append(gid) or real(gid, *a))
    fa = FastAPI()
    fa.include_router(rt)
    ask = TestClient(fa, base_url="http://localhost:8852")
    return rt, wdir, scored, fail, reads, lambda: ask.get("/api/tester/desklab/results", headers=DESK).json()["results"]["nq_bars"]


def test_a_done_walkforwards_block_is_kept_until_a_file_changes(c, tmp_path, drafts_dir, make_run, monkeypatch):  # noqa: F811
    rt, wdir, scored, fail, reads, ask = setup(c, tmp_path, drafts_dir, make_run, monkeypatch)
    first = ask()
    assert first["unseen"]["net"] == 1234.5 and first["prop"]["both"] == {"account": "LucidFlex 50K", **HEAD}
    assert ask() == first and len(reads) == 2, "files under 2 s old: read again each time"
    age(wdir)
    ask()
    assert ask() == first and len(reads) == 3 and len(scored) == 3, "settled: kept, nothing read or scored again"
    (wdir / "result.json").write_text(__import__("json").dumps(wf_result(oos_net=99.0)))
    age(wdir)
    got = ask()
    assert got["unseen"]["net"] == 99.0 and len(reads) == 4, "its result changed: worked out again"
    first["unseen"]["net"] = 0.0                                        # a caller's copy changes nothing kept
    assert ask()["unseen"]["net"] == 99.0 and len(reads) == 4


def test_a_failed_prop_sim_is_not_kept(c, tmp_path, drafts_dir, make_run, monkeypatch):  # noqa: F811
    monkeypatch.setattr(runner, "SETTLED_NS", 0)
    rt, wdir, scored, fail, reads, ask = setup(c, tmp_path, drafts_dir, make_run, monkeypatch)
    fail.append(True)
    assert ask()["prop"]["unseen"] is None
    fail.clear()
    assert ask()["prop"]["unseen"] == {"account": "LucidFlex 50K", **HEAD} and len(reads) == 2
    ask()
    assert len(reads) == 2, "scored this time: kept"


def test_the_warm_up_scores_the_groups_and_starts_nothing(c, tmp_path, drafts_dir, make_run, monkeypatch):  # noqa: F811
    rt, wdir, scored, fail, reads, ask = setup(c, tmp_path, drafts_dir, make_run, monkeypatch)
    deskgroups.apply("create", {"name": "Eval group", "kind": "eval"})           # the store itself: no Desk is asked
    for sid in ("lab_nq_bars", "nq930"):
        deskgroups.apply("move", {"strategy": sid, "group": "g1"})
    started = []
    monkeypatch.setattr(rt.wfs, "submit", lambda req: started.append(req))
    monkeypatch.setattr(rt.manager, "submit", lambda req: started.append(req))
    monkeypatch.setattr(tester_api, "DESKLAB_AUTO_UNSEEN", True)
    rt.warm()
    assert sorted(scored) == [1, 1, 2, 2, 3, 3], "the card's three and the group's three (one member: the same trades)"
    assert started == []
    monkeypatch.setattr(tester_api, "DESKLAB_AUTO_UNSEEN", False)
    fa = FastAPI()
    fa.include_router(rt)
    g = TestClient(fa, base_url="http://localhost:8852").get("/api/tester/deskgroups/results", headers=DESK).json()["results"]["g1"]
    assert g["prop"]["both"] == {"account": "LucidFlex 50K", **HEAD} and len(scored) == 6, "the first ask is a hit"
