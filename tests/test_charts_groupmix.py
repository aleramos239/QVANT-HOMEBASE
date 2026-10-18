"""The Lab's group builder (homebase/charts/groupmix.py and POST /api/tester/groupmix): build-days runs only, each member
at its size, cut to the days all cover, its numbers and the group's, and how alike their days are."""
from __future__ import annotations

import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from homebase.charts import groupmix as gm
from homebase.charts.server import create_app
from tests.backtest_util import D1, nq_archive

BUILD = {"start": "2021-09-22", "end": "2025-06-30", "holdout": False}


def trade(date, net, ms):
    return {"date": date, "net": net, "gross": net + 4, "commission": -4.0, "mae_usd": -50.0, "entry_ms": ms, "exit_ms": ms + 60_000}


def days(n, start=1):
    return [f"2024-01-{d:02d}" if d <= 28 else f"2024-02-{d - 28:02d}" for d in range(start, start + n)]


def test_the_build_run_is_the_newest_finished_one_that_ends_by_the_build_end():
    runs = [{"id": "c", "status": "running", "range": BUILD},
            {"id": "u", "status": "done", "range": {"start": "2025-07-01", "end": "2026-10-16"}},
            {"id": "h", "status": "done", "holdout": True, "range": BUILD},
            {"id": "b", "status": "done", "range": BUILD},
            {"id": "a", "status": "done", "range": BUILD}]
    assert gm.build_run(runs)["id"] == "b"
    assert gm.build_run(runs[:3]) is None


def test_scaled_multiplies_every_dollar_field_only():
    t = gm.scaled([trade("2024-01-02", 100.0, 1)], 2)[0]
    assert (t["net"], t["gross"], t["commission"], t["mae_usd"], t["entry_ms"]) == (200.0, 208.0, -8.0, -100.0, 1)


def test_correlation_of_daily_pnl_counts_a_day_off_as_zero():
    d = days(30)
    a = [trade(x, 100.0 if i % 2 else -50.0, i) for i, x in enumerate(d)]
    same = [trade(x, 2 * t["net"], i) for i, (x, t) in enumerate(zip(d, a))]
    flip = [trade(x, -t["net"], i) for i, (x, t) in enumerate(zip(d, a))]
    c = gm.correlation([("a", a), ("same", same), ("flip", flip)])
    assert c["matrix"][0][1] == 1.0 and c["matrix"][0][2] == -1.0 and c["matrix"][1][1] == 1.0
    assert c["both"][0][1] == 30 and c["days"] == 30
    few = gm.correlation([("a", a[:5]), ("b", same[:5])])
    assert few["matrix"][0][1] is None, "fewer than 20 days: no number"


def test_mix_cuts_to_the_shared_days_and_scales_each_member():
    a = [trade("2021-10-01", 100.0, 1), trade("2024-01-02", 100.0, 2)]
    b = [trade("2024-01-02", -40.0, 3), trade("2024-01-03", 60.0, 4)]
    got = gm.mix([{"name": "a", "size": 2, "run": {"id": "ra", "range": {"start": "2021-09-22", "end": "2025-06-30"}}, "trades": a},
                  {"name": "b", "size": 1, "run": {"id": "rb", "range": {"start": "2023-01-02", "end": "2025-06-30"}}, "trades": b}])
    assert got["window"] == {"start": "2023-01-02", "end": "2025-06-30"}
    assert got["members"][0]["summary"]["net"] == 200.0, "a's 2021 trade is outside the shared days; x2"
    assert got["group"]["net"] == 220.0 and got["group"]["together_days"] == 1 and got["group"]["trades"] == 3
    with pytest.raises(ValueError):
        gm.mix([{"name": "a", "size": 1, "run": {"id": "x", "range": {"start": "2021-01-01", "end": "2021-12-31"}}, "trades": a},
                {"name": "b", "size": 1, "run": {"id": "y", "range": {"start": "2023-01-02", "end": "2023-12-31"}}, "trades": b}])


def put_run(runs, rid, strategy, trades, rng=BUILD, status="done"):
    d = runs / rid
    d.mkdir(parents=True)
    (d / "request.json").write_text(json.dumps({"strategy": strategy, "range": rng}))
    (d / "status.json").write_text(json.dumps({"status": status}))
    (d / "trades.json").write_text(json.dumps({"trades": trades}))


def test_the_route_reads_saved_build_runs_and_names_who_is_left_out(tmp_path):
    runs = tmp_path / "state" / "tester" / "runs"
    d = days(30)
    put_run(runs, "20261018-100000-draft_a-0001", "draft_a", [trade(x, 100.0 if i % 3 else -80.0, i) for i, x in enumerate(d)])
    put_run(runs, "20261018-100100-draft_b-0002", "draft_b", [trade(x, -60.0 if i % 2 else 90.0, 1000 + i) for i, x in enumerate(d)])
    put_run(runs, "20261018-100200-draft_c-0003", "draft_c", [trade(d[0], 10.0, 5)], rng={"start": "2025-07-01", "end": "2026-10-16"})
    app = create_app(roots=["NQ"], base=nq_archive(tmp_path / "ticks"), replay=D1, speed=1,
                     start_et=dt.time(9, 30), state=tmp_path / "state")
    with TestClient(app, base_url="http://localhost:8852") as c:
        ok = {"origin": "http://localhost:8852"}
        r = c.post("/api/tester/groupmix", headers=ok, json={"members": [{"strategy": "draft_a", "size": 1},
                   {"strategy": "draft_b", "size": 0.5}, {"strategy": "draft_c", "size": 1}], "prop_rules": None})
        assert r.status_code == 200, r.text
        j = r.json()
        assert [m["name"] for m in j["members"]] == ["draft_a", "draft_b"]
        assert j["left_out"][0]["strategy"] == "draft_c" and "build-days" in j["left_out"][0]["why"]
        assert j["group"]["trades"] == 60 and j["correlation"]["names"] == ["draft_a", "draft_b"] and "ledger" not in j
        assert c.post("/api/tester/groupmix", headers=ok, json={"members": [{"strategy": "draft_a"}]}).status_code == 400
        assert c.post("/api/tester/groupmix", headers=ok, json={"members": [{"strategy": "draft_a", "size": 50},
                      {"strategy": "draft_b"}]}).status_code == 400
        assert c.post("/api/tester/groupmix", headers={"origin": "https://evil.example"},
                      json={"members": [{"strategy": "draft_a"}, {"strategy": "draft_b"}]}).status_code == 403
