"""The Desk's first results ask after a restart was ~16 prop sims (25-90 s). The chart service now scores the promoted
strategies' saved runs once, in a thread, after it is up (tester_router(...).warm). It reads saved runs only: it never
starts a run, whatever DESKLAB_AUTO_UNSEEN says."""
import datetime as dt

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from homebase.charts import tester_api
from homebase.labrun import store
from tests.test_tester_desklab import DESK, HEAD, at_et, c, draft, make_run, promote, wf_result, write_wf  # noqa: F401 -- fixtures and helpers


def test_warm_scores_the_saved_runs_once_and_starts_nothing(c, tmp_path, drafts_dir, make_run, monkeypatch):  # noqa: F811
    scored = []

    def fake(trades, req):
        scored.append(req["prop_rules"])
        return {"rules": {"label": "LucidFlex 50K"}, "headline": HEAD, "breach": {}}, False
    monkeypatch.setattr(tester_api, "_run_propsim", fake)
    draft(drafts_dir)
    build = make_run()
    (tmp_path / "state" / "tester" / "runs" / build / "trades.json").write_text("[]")
    assert promote(c, run_id=build, headers=DESK).json()["ok"] is True
    at_et(monkeypatch, 2026, 10, 18, 12, 0)
    write_wf(tmp_path, store.get("nq_bars"), dt.date(2026, 10, 18), result=wf_result())       # the card's 3:1, saved

    rt = tester_api.tester_router(lambda request: None, tmp_path / "ticks", tmp_path / "state" / "tester")
    started = []
    monkeypatch.setattr(rt.manager, "submit", lambda req: started.append(req))
    monkeypatch.setattr(tester_api, "DESKLAB_AUTO_UNSEEN", True)     # the ROUTE would start the unseen run now
    rt.warm()
    assert scored == [tester_api.DESKLAB_PROP] * 2, "the 3:1's two sides are scored once each, on the pipeline's account"
    assert started == [], "a warm-up reads saved runs; it starts none"

    monkeypatch.setattr(tester_api, "DESKLAB_AUTO_UNSEEN", False)
    fa = FastAPI()
    fa.include_router(rt)
    got = TestClient(fa, base_url="http://localhost:8852").get("/api/tester/desklab/results", headers=DESK)
    assert got.json()["results"]["nq_bars"]["prop"]["build"] == {"account": "LucidFlex 50K", **HEAD}
    assert scored == [tester_api.DESKLAB_PROP] * 2, "the first ask is a cache hit: nothing is scored again"


def test_warm_never_raises(tmp_path, monkeypatch):
    rt = tester_api.tester_router(lambda request: None, tmp_path / "ticks", tmp_path / "state" / "tester")

    def boom():
        raise OSError("the store is unreadable")
    monkeypatch.setattr(tester_api.store, "listing", boom)
    rt.warm()      # a warm-up must never take the service down
