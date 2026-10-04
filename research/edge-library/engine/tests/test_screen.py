"""screen.py: the job list, bundles + ledger rows, idempotence, the 400-run cap, the error path, the P&L-free smoke check.
Runs a toy family on 8 fixed in-sample days in one process, into a directory of the test's own (never L/runs, L/ledger.csv)."""
import csv
import json

import pytest

import fam_fixtures as FX
import l2sim
import screen

DAYS = list(screen.SMOKE_DAYS[:8])
REG = {"toy_imb": (FX.ToyImb, {"k": 0.15}, False, "test: follow imb10"), "toy_bracket": (FX.ToyBracket, {}, True, "test: OCO bracket")}


def test_job_list_is_one_real_and_two_c2_runs_per_family_and_tf():
    reg = {**REG, "two_tf": (type("TwoTf", (FX.ToyImb,), {"SCREEN_TFS": ("1", "5")}), {}, False, "test")}
    js = screen.jobs(reg)
    assert [j["key"] for j in js] == ["toy_bracket-tf5", "toy_bracket-tf5-c2s1", "toy_bracket-tf5-c2s2", "toy_imb-tf5", "toy_imb-tf5-c2s1",
                                      "toy_imb-tf5-c2s2", "two_tf-tf1", "two_tf-tf1-c2s1", "two_tf-tf1-c2s2", "two_tf-tf5", "two_tf-tf5-c2s1",
                                      "two_tf-tf5-c2s2"]
    assert all(j["stage"] == "screen" and j["inputs"]["sess"] == "all" and j["inputs"]["tf"] == j["tf"] for j in js)
    assert js[3]["inputs"] == {"k": 0.15, "tf": "5", "sess": "all"} and (js[4]["control"], js[4]["seed"]) == ("c2", 1)
    assert [j["key"] for j in screen.jobs(reg, "stress")] == ["toy_bracket-tf5-stress", "toy_imb-tf5-stress", "two_tf-tf1-stress", "two_tf-tf5-stress"]
    assert [j["family"] for j in screen.jobs(reg, only=["toy_imb"])] == ["toy_imb"] * 3
    with pytest.raises(KeyError):
        screen.jobs(reg, only=["nope"])
    assert screen.CAP == 400 and screen.C2_SEEDS == (1, 2) and screen.COUNTED == ("screen", "gate", "screen_error")


def test_runs_write_bundles_and_ledger_rows_and_are_idempotent(l_tmp):
    if l2sim.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")
    kw = dict(reg=REG, days=DAYS, runs_dir=l_tmp / "runs", ledger=l_tmp / "ledger.csv", log=l_tmp / "screen.log", workers=1)
    try:
        out = screen.run_all("test", **kw)
    except FileNotFoundError as e:
        pytest.skip(f"tape / feature cache not available: {e}")
    keys = [j["key"] for j in screen.jobs(REG, "test")]
    assert out == {"ran": keys, "skipped": [], "errors": [], "refused": 0} and len(keys) == 6
    with (l_tmp / "ledger.csv").open(newline="") as fh:
        rd = csv.reader(fh)
        assert tuple(next(rd)) == screen.COLS == ("stage", "key", "family", "tf", "inputs_json", "control", "seed", "trades", "net",
                                                   "elapsed_s", "finished_utc")
    rows = screen.read_ledger(l_tmp / "ledger.csv")
    assert [r["key"] for r in rows] == keys and {r["stage"] for r in rows} == {"test"}
    assert [(r["control"], r["seed"]) for r in rows[3:]] == [("", ""), ("c2", "1"), ("c2", "2")]
    for r in rows:
        b = l_tmp / "runs" / r["key"]
        trades, meta = json.loads((b / "trades.json").read_text()), json.loads((b / "run.json").read_text())
        assert int(r["trades"]) == len(trades) == meta["trades"] and float(r["net"]) == meta["net"] and meta["id"] == r["key"]
        assert json.loads(r["inputs_json"]) == meta["inputs"] and meta["inputs"]["sess"] == "all" and meta["inputs"]["tf"] == r["tf"]
        assert meta["coverage"]["sessions"] == len(DAYS) and meta["coverage"]["skipped_by_error"] == 0 and meta["stress"] is None
        assert meta["screen"]["family"] == r["family"] and meta["screen"]["control"] == r["control"] and meta["qty"] == 1
        assert meta["features_loader"] == ("C2Features" if r["control"] else "L2Features") and meta["features"] == ["imb10"]
        assert r["finished_utc"].endswith("+00:00") and float(r["elapsed_s"]) >= 0
    real, n1, n2 = (json.loads((l_tmp / "runs" / f"toy_imb-tf5{s}" / "trades.json").read_text()) for s in ("", "-c2s1", "-c2s2"))
    ents = lambda ts: [(t["entry_ms"], t["side"]) for t in ts]
    assert real and ents(n1) != ents(real) and ents(n1) != ents(n2)                 # the nulls really ran on shuffled features
    meta = json.loads((l_tmp / "runs" / "toy_bracket-tf5" / "run.json").read_text())   # the sim's evidence next to the declaration
    assert meta["screen"]["both_sides_declared"] is True and meta["both_sides_sessions"] > 0
    assert json.loads((l_tmp / "runs" / "toy_imb-tf5" / "run.json").read_text())["both_sides_sessions"] == 0
    # idempotent: a second call runs nothing and adds no row
    before = (l_tmp / "ledger.csv").read_text()
    again = screen.run_all("test", **kw)
    assert again["ran"] == [] and again["skipped"] == keys and (l_tmp / "ledger.csv").read_text() == before
    # a bundle of the screen is a score.py source as it is (a subset run needs its calendar: these 8 days)
    import score
    assert score.load_trades(str(l_tmp / "runs" / "toy_imb-tf5"), calendar=DAYS).n == len(real)
    assert score.load_trades(str(l_tmp / "runs" / "toy_imb-tf5"), calendar=DAYS).label == "toy_imb-tf5"
    log = (l_tmp / "screen.log").read_text()
    assert "6 jobs planned, 0 done, 6 to run" in log and "net" not in log and "$" not in log


def test_the_cap_refuses_a_batch_and_a_single_row(l_tmp, monkeypatch):
    led = l_tmp / "ledger.csv"
    for i in range(396):
        screen.append_row({"stage": "screen" if i % 3 else "gate", "key": f"old-{i}", "family": "old"}, led)
    screen.record_gate("G1-flex_eval", "gate_g1", {"gate": "G1"}, trades=100, net=12.5, path=led)
    screen.append_row({"stage": "stress", "key": "old-0-stress", "family": "old"}, led)          # stress rows are not counted
    screen.append_row({"stage": "screen_error", "key": "bad-tf5", "family": "bad"}, led)         # a failed full run is
    assert screen.cap_used(screen.read_ledger(led)) == 398
    ran = []
    monkeypatch.setattr(screen, "run_job", lambda *a, **k: ran.append(a) or {"stage": "screen", "trades": 0, "elapsed_s": 0})
    monkeypatch.setattr(screen, "LOG", l_tmp / "default.log")
    with pytest.raises(screen.CapExceeded, match="398 used \\+ 6 pending > cap 400"):
        screen.run_all("screen", reg=REG, ledger=led, runs_dir=l_tmp / "runs", log=l_tmp / "screen.log")
    assert ran == [] and not (l_tmp / "runs").exists() and "REFUSED" in (l_tmp / "screen.log").read_text()
    assert len(screen.read_ledger(led)) == 399                                                   # nothing was added
    # two rows fit, the third is refused whatever writes it (screen runner or gate runner)
    screen.append_row({"stage": "screen", "key": "a"}, led)
    screen.record_gate("G2-x", "gate_g2", {}, 1, 0.0, path=led)
    with pytest.raises(screen.CapExceeded):
        screen.append_row({"stage": "screen", "key": "b"}, led)
    with pytest.raises(screen.CapExceeded):
        screen.record_gate("G3-x", "gate_g3", {}, 1, 0.0, path=led)
    screen.append_row({"stage": "stress", "key": "a-stress"}, led)                               # not a screening run: still allowed
    assert screen.cap_used(screen.read_ledger(led)) == 400
    with pytest.raises(ValueError, match="already holds"):
        screen.append_row({"stage": "stress", "key": "a-stress"}, led)
    with pytest.raises(ValueError, match="unknown ledger columns"):
        screen.append_row({"stage": "screen", "key": "c", "pnl": 1}, led)
    with pytest.raises(ValueError, match="stage and a key"):
        screen.append_row({"stage": "screen"}, led)


def test_a_screen_run_is_every_session_and_stress_is_its_own_stage(l_tmp, monkeypatch):
    job = screen.jobs(REG)[3]
    for stage in ("screen", "stress"):
        with pytest.raises(ValueError, match="every in-sample session"):
            screen.run_job({**job, "stage": stage}, REG, days=DAYS, runs_dir=l_tmp / "runs", ledger=l_tmp / "l.csv")
    seen = {}

    def fake_run(cls, params, **kw):
        seen.update(kw, cls=cls, params=params)
        return {"trades": [], "skipped": [], "no_trade": [], "sessions": 825, "used": 820, "skipped_by_error": 0, "both_sides_sessions": 0,
                "unrealistic_winners": 0, "elapsed_s": 1.0, "meta": {"inputs": params, "range": {"start": "2021-09-22", "end": "2024-12-31"}}}

    monkeypatch.setattr(l2sim, "run", fake_run)
    monkeypatch.setattr(l2sim, "wait_compute_window", lambda *a, **k: seen.setdefault("waited", True) and 0.0)
    monkeypatch.setattr(screen, "LOG", l_tmp / "default.log")
    row = screen.run_job(job, REG, workers=99, runs_dir=l_tmp / "runs", ledger=l_tmp / "l.csv")
    assert row["stage"] == "screen" and seen["waited"] and seen["workers"] == l2sim.MAX_WORKERS and "days" not in seen         # <= 8 workers, all sessions
    assert "slip_ticks" not in seen and "latency_ms" not in seen and type(seen["features"]).__name__ == "L2Features"
    st = screen.jobs(REG, "stress")[1]
    row = screen.run_job(st, REG, runs_dir=l_tmp / "runs", ledger=l_tmp / "l.csv")
    assert row["stage"] == "stress" and row["key"] == "toy_imb-tf5-stress" and (seen["slip_ticks"], seen["latency_ms"]) == (2.0, 250)
    assert screen.cap_used(screen.read_ledger(l_tmp / "l.csv")) == 1                                           # the stress run is not counted
    strict = {"b4": (type("B4", (FX.ToyImb,), {"SCREEN_RUN": {"strict_limit": True}}), {}, False, "test")}
    seen.clear()
    screen.run_job(screen.jobs(strict)[1], strict, runs_dir=l_tmp / "runs", ledger=l_tmp / "l.csv")
    assert seen["strict_limit"] is True and type(seen["features"]).__name__ == "C2Features" and seen["features"].seed == 1


def test_a_run_with_dropped_sessions_is_an_error_row_without_a_bundle(l_tmp):
    if l2sim.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")
    reg = {"crashes": (FX.Crashes, {}, False, "test")}
    kw = dict(reg=reg, days=DAYS, runs_dir=l_tmp / "runs", ledger=l_tmp / "ledger.csv", log=l_tmp / "screen.log", workers=1, max_runs=1)
    try:
        out = screen.run_all("test", **kw)
    except FileNotFoundError as e:
        pytest.skip(f"tape / feature cache not available: {e}")
    assert out["errors"] == ["crashes-tf5"] and out["ran"] == [] and not (l_tmp / "runs" / "crashes-tf5").exists()
    rows = screen.read_ledger(l_tmp / "ledger.csv")
    assert [(r["stage"], r["key"], r["trades"], r["net"]) for r in rows] == [("test_error", "crashes-tf5", "", "")]
    assert "1 of 8 sessions dropped (strategy error: RuntimeError: boom)" in (l_tmp / "screen.log").read_text()
    assert screen.done_keys(rows, "test") == set()                           # still pending: fix the family, run again
    assert screen.run_all("test", **kw)["errors"] == ["crashes-tf5"] and len(screen.read_ledger(l_tmp / "ledger.csv")) == 2


def test_broken_registry_is_refused(monkeypatch):
    import families
    monkeypatch.setitem(families.ERRORS, "b_broken", "import failed: SyntaxError: x")
    with pytest.raises(screen.RegistryBroken, match="b_broken"):
        screen.registry()
    assert screen.registry(strict=False) is families.REGISTRY and screen.main(["run"]) == 2
    st = screen.status()
    assert st["registry_errors"] == {"b_broken": "import failed: SyntaxError: x"} and st["cap"] == 400


def test_smoke_reports_counts_only(l_tmp):
    if l2sim.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")
    try:
        o = screen.smoke("toy_imb", n_days=4, workers=1, reg=REG)
        b = screen.smoke("toy_bracket", n_days=3, workers=5, reg={"toy_bracket": (FX.ToyBracket, {}, False, "declared wrong")})
    except FileNotFoundError as e:
        pytest.skip(f"tape / feature cache not available: {e}")
    assert o["ok"] and o["days"] == 4 and o["sessions"] == 4 and o["skipped_by_error"] == 0 and o["worker_parity"] is True
    assert o["trades"] == o["long"] + o["short"] == sum(o["by_session"].values()) == sum(o["by_day"].values()) > 0
    assert o["entry_kind"] == {"market": o["trades"], "resting": 0} and o["both_sides_ok"] and o["c2_null"]["skipped_by_error"] == 0
    flat = json.dumps(o).lower()
    assert not any(w in flat for w in ("net", "gross", "pnl", "exit_reason", "win", "mae", "mfe", "price"))    # no P&L, no outcomes
    assert b["both_sides_declared"] is False and b["both_sides_sessions"] > 0 and b["both_sides_ok"] is False and b["ok"] is False
    with pytest.raises(KeyError):
        screen.smoke("nope", reg=REG)
    assert len(screen.SMOKE_DAYS) == 10 and max(screen.SMOKE_DAYS) < "2025-01-01"
