"""run_menus.py + the edge-library registry contract: one tape pass per unit over every menu cell + its nulls, stores under
runs/<key>/, the ledger and its hard cap, idempotence, and the counts-only smoke test. 10 BUILD days, tmp_path for every file.
Counts and identity only: no result is judged."""
import json

import numpy as np
import pytest

import fam_fixtures as FX
import families
import l2ref
import l2sim as S
import library as LB
import run_menus as RM

DAYS = list(RM.SMOKE_DAYS)


@pytest.fixture
def reg(monkeypatch):
    """Two edge-library families as a family author would register them (no production name is taken)."""
    for name, cls, lib in (("edge_donch", FX.EdgeDonch, FX.EDGE_LIB), ("edge_straddle_t", FX.EdgeStraddleT, FX.EDGE_LIB_T)):
        entry = (cls, {}, name == "edge_straddle_t", "test entry", lib)
        assert families.check_entry(name, entry) == []
        monkeypatch.setitem(families.REGISTRY, name, entry[:4])
        monkeypatch.setitem(families.LIBRARY, name, families.check_library(name, cls, {}, lib)[1])
    return families


# ---- the registry contract ----------------------------------------------------------------------------------------------------

def test_a_library_entry_needs_a_rationale_and_a_complexity_count():
    ok = (FX.EdgeDonch, {}, False, "C: donchian", FX.EDGE_LIB)
    assert families.check_entry("edge_donch", ok) == []
    meta = families.check_library("edge_donch", FX.EdgeDonch, {}, FX.EDGE_LIB)[1]
    assert meta["roots"] == ("NQ", "ES", "GC") and meta["l2"] is False and meta["variants"] == [{"n": 10}, {"n": 20}] and not meta["weak"]

    def bad(**over):
        lib = {**FX.EDGE_LIB, **over}
        out = families.check_entry("edge_donch", (FX.EdgeDonch, {}, False, "C", {k: v for k, v in lib.items() if v is not None}))
        assert out, over
        return " | ".join(out)
    assert "'rationale' is mandatory" in bad(rationale=None) and "'rationale' is mandatory" in bad(rationale="works")
    assert "'complexity' is mandatory" in bad(complexity=None) and "'complexity' is mandatory" in bad(complexity=0)
    assert "'complexity' is mandatory" in bad(complexity=2.5) and "'complexity' is mandatory" in bad(complexity=True)
    assert "unknown library keys" in bad(notes="x") and "'roots' must be" in bad(roots=("NQ", "CL"))
    assert "refused by resolve_inputs" in bad(variants=[{"n": 1}]) and "duplicate variant" in bad(variants=[{"n": 10}, {"n": 10}])
    assert "may not set" in bad(variants=[{"tgt_r": 1.0}]) and "may not set" in bad(variants=[{"tf": "5"}]) and "may not set" in bad(variants=[{"f_book": "on"}])
    assert "'variants' must be" in bad(variants=[]) and "'weak' must be a bool" in bad(weak="yes")
    assert "must stay 'off'" in " | ".join(families.check_entry("x", (FX.EdgeDonch, {"x_book": "on"}, False, "C", FX.EDGE_LIB)))
    # a Level-2 family is NQ only; a 4-tuple (the L2 pilot's screen entries) is registered but is not a library family
    assert "NQ" in " | ".join(families.check_entry("toy", (FX.ToyImb, {}, False, "B1", {**FX.EDGE_LIB, "variants": [{}], "roots": ("NQ", "ES")})))
    assert families.check_library("toy", FX.ToyImb, {}, {**FX.EDGE_LIB, "variants": [{}]})[1]["roots"] == ("NQ",)
    assert families.check_entry("toy", (FX.ToyImb, {}, False, "B1")) == []
    assert "FEATURES" in " | ".join(families.check_entry("d", (FX.EdgeDonch, {}, False, "legacy 4-tuple without features")))
    with pytest.raises(KeyError, match="4-tuple"):
        families.library("bimb_follow")
    with pytest.raises(KeyError, match="not registered"):
        families.library("nope")


def test_unit_grid_is_variants_times_the_32_exit_cells(reg):
    g = reg.unit_grid("edge_donch", "ES", "15")
    assert len(g) == 64 and [c["exit"] for c in g[:32]] == S.menu("ES") and g[0]["spec"][1]["sess"] == "all"
    assert g[0]["spec"][0] is FX.EdgeDonch and g[33]["variant"] == {"n": 20} and g[33]["spec"][1]["n"] == 20
    assert reg.unit_inputs("edge_donch", "15") == {"tf": "15", "sess": "all"} and reg.features_for("edge_donch") is None
    # hold_to='day' (ORCHESTRATOR DECISIONS 1): a Template cell = SEVEN independent instances, one per session; a time-fired
    # cell = one. The old convention (three instances: the tester's five / pre / eve) stays available for the gates.
    assert [p["sess"] for _, p in RM.cell_specs(g[0])] == list(RM.DAY_PASSES) and all(p["hold_to"] == "day" for _, p in RM.cell_specs(g[0]))
    assert [p["sess"] for _, p in RM.cell_specs(g[0], "session")] == ["all", "pre", "eve"] and RM.SESS_PASSES == ("all", "pre", "eve")
    assert [p["hold_to"] for _, p in RM.cell_specs(reg.unit_grid("edge_straddle_t", "NQ", "30")[0])] == ["day"]
    with pytest.raises(ValueError, match="SCREEN_TFS"):
        reg.unit_grid("edge_donch", "NQ", "5")
    us = RM.units(only=["edge_donch", "edge_straddle_t"])
    assert [u["key"] for u in us] == ["edge_donch-NQ-tf15", "edge_straddle_t-NQ-tf30", "edge_donch-ES-tf15", "edge_straddle_t-ES-tf30",
                                      "edge_donch-GC-tf15", "edge_straddle_t-GC-tf30"]            # NQ first, then ES, then GC
    assert us[0]["cells"] == 64 and us[0]["null_cells"] == 0 and us[1]["cells"] == 32 and us[1]["null_cells"] == 64 and us[1]["time_fired"]
    assert len(RM.c1_grid("GC", "5")) == 64 and RM.c1_grid("GC", "5")[40]["spec"][1]["seed"] == 2


# ---- one unit over 10 BUILD days ------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_run_unit_writes_the_store_and_the_ledger_and_is_idempotent(reg, tmp_path, root):
    led, runs, log = tmp_path / "ledger.csv", tmp_path / "runs", tmp_path / "log.txt"
    days = [d for d in DAYS if S.hb_tape_path(d, root) is not None] if root != "NQ" else DAYS
    out = RM.run_unit("edge_donch", root, "15", workers=2, runs_dir=runs, ledger=led, log=log, days=days)
    key = f"edge_donch-{root}-tf15"
    assert out == [{"key": key, "ok": True, "cells": 64}]
    assert sorted(p.name for p in (runs / key).iterdir()) == ["cells.npz", "run.json", "table.csv"]
    u = LB.load_unit(key, runs)
    meta = u["meta"]
    assert meta["root"] == root and meta["stage"] == "build" and meta["period"] == "build" and meta["range"]["period"] == "insample"
    assert meta["rationale"] == FX.EDGE_LIB["rationale"] and meta["complexity"] == 3 and len(meta["cells"]) == 64
    assert meta["coverage"]["sessions"] == len(days) and meta["segments"] == ["eve", "day"]
    assert int(u["off"][-1]) == sum(c["trades"] for c in meta["cells"]) == len(u["net"]) > 100
    assert all(c["skipped_by_error"] == 0 for c in meta["cells"]) and set(np.unique(u["sess"])) <= set(range(7))
    cell = LB.unit_cell(u, "n20_pts%s-r1" % S._num(S.MENU_STOP_PTS[root][1]))
    assert len(cell["net"]) == next(c["trades"] for c in meta["cells"] if c["id"].startswith("n20_pts") and c["xi"] == 13)
    # the store holds exactly what direct runs of that cell give: the seven sessions, each its own instance, hold_to day
    assert meta["cells"][45]["inputs"]["sess"] == "+".join(RM.DAY_PASSES) and meta["passes"] == list(RM.DAY_PASSES)
    assert meta["cells"][45]["inputs"]["hold_to"] == "day" and meta["hold_to"] == "day"
    inp = {k: v for k, v in meta["cells"][45]["inputs"].items() if k != "sess"}
    parts = [S.run(FX.EdgeDonch, {**inp, "sess": s_}, days=days, root=root, workers=1) for s_ in RM.DAY_PASSES]
    direct = RM.merge(parts)
    for s_, part in zip(RM.DAY_PASSES, parts):                    # every instance trades its own session only
        assert all(S.session_of(t["entry_ms"]) == s_ for t in part["trades"])
        own = [t for t in direct["trades"] if S.session_of(t["entry_ms"]) == s_]
        assert sorted(own, key=lambda t: (t["exit_ms"], t["entry_ms"])) == part["trades"]
    assert RM.hold_checks([direct], root) == {"exit_after_day_flat": 0, "overlap_in_session": 0, "entry_in_no_session": 0}
    packed = LB.pack(direct["trades"])
    got = LB.unit_cell(u, 45)
    assert all(np.array_equal(got[k], packed[k], equal_nan=True) for k in LB.FIELDS)
    tab = LB.session_table(u, "all")
    assert len(tab) == 64 and [r["id"] for r in tab] == [c["id"] for c in meta["cells"]]
    assert tab[45]["net"] == round(sum(t["net"] for t in direct["trades"]), 2) and tab[45]["trades"] == len(direct["trades"])
    assert LB.plateau(tab)["cells"] == 64
    rows = LB.read_ledger(led)
    assert len(rows) == 1 and (rows[0]["stage"], rows[0]["key"], rows[0]["kind"], rows[0]["cells"], rows[0]["root"]) == ("build", key, "grid", "64", root)
    assert "net" not in rows[0] and LB.ledger_used(path=led)["cells"] == 64
    again = RM.run_unit("edge_donch", root, "15", workers=2, runs_dir=runs, ledger=led, log=log, days=days)
    assert again == [{"key": key, "skipped": True}] and len(LB.read_ledger(led)) == 1                # idempotent


def test_time_fired_unit_runs_its_time_shuffle_null_in_the_same_pass_and_c1_pool(reg, tmp_path):
    led, runs, log = tmp_path / "ledger.csv", tmp_path / "runs", tmp_path / "log.txt"
    out = RM.run_unit("edge_straddle_t", "NQ", "30", workers=2, runs_dir=runs, ledger=led, log=log, days=DAYS)
    assert out == [{"key": "edge_straddle_t-NQ-tf30", "ok": True, "cells": 32}, {"key": "edge_straddle_t-NQ-tf30-shift", "ok": True, "cells": 64}]
    real, null = LB.load_unit("edge_straddle_t-NQ-tf30", runs), LB.load_unit("edge_straddle_t-NQ-tf30-shift", runs)
    assert null["meta"]["control"] == "shift" and null["meta"]["stage"] == "null" and len(null["meta"]["cells"]) == 64
    assert {c["variant"]["shift_seed"] for c in null["meta"]["cells"]} == {1, 2} and null["meta"]["cells"][0]["id"].startswith("s1_")
    assert all(c["trades"] <= len(DAYS) for c in real["meta"]["cells"] + null["meta"]["cells"])       # one trade per time per day
    reps = LB.unit_null_replicates(null)
    assert len(reps) >= 2 and all(len(r) == 32 for r in reps) and LB.best_of_nulls(reps)["nulls"] == len(reps)
    c1 = RM.run_c1("NQ", "30", workers=2, runs_dir=runs, ledger=led, log=log, days=DAYS)
    assert c1 == {"key": "c1-NQ-tf30", "ok": True, "cells": 64}
    pool = LB.load_unit("c1-NQ-tf30", runs)
    assert pool["meta"]["control"] == "c1" and {c["variant"]["seed"] for c in pool["meta"]["cells"]} == {1, 2}
    assert set(np.unique(pool["sess"])) == set(range(7))             # the pool trades all seven sessions
    assert RM.run_c1("NQ", "30", runs_dir=runs, ledger=led, log=log, days=DAYS) == {"key": "c1-NQ-tf30", "skipped": True}
    # the 40,000 cap counts the candidate grid only; the time-shuffle null and the C1 pool are tracked apart (decision 6)
    assert LB.ledger_used(path=led) == {"runs": 0, "cells": 32, "wfs": 0} and LB.ledger_nulls(path=led) == 128
    assert sorted((r["key"], r["kind"]) for r in LB.read_ledger(led)) == [("c1-NQ-tf30", "null"), ("edge_straddle_t-NQ-tf30", "grid"),
                                                                           ("edge_straddle_t-NQ-tf30-shift", "null")]
    # a member cell against its day- and session-matched random pool (same exit cell): the plumbing end to end
    m = LB.unit_cell(real, 2)
    seeds = [i for i, c in enumerate(pool["meta"]["cells"]) if c["exit"] == real["meta"]["cells"][2]["exit"]]
    pl = {k: np.concatenate([LB.unit_cell(pool, i)[k] for i in seeds]) for k in LB.FIELDS}
    d = LB.c1_draws(m, pl, K=20)
    assert d["short"] == 0 and d["pool_trades"] > len(m["net"]) and len(d["nets"]) == 20


def test_a_batch_past_the_cell_cap_is_refused_before_anything_runs(reg, tmp_path, monkeypatch):
    led, runs = tmp_path / "ledger.csv", tmp_path / "runs"
    LB.ledger_add("build", "filler", "grid", cells=LB.CAPS["cells"] - 63, path=led)
    ran = []

    class Ran(Exception):
        pass

    def fake(*a, **k):
        ran.append(1)
        raise Ran()
    monkeypatch.setattr(S, "run_many", fake)
    with pytest.raises(LB.CapExceeded):                           # 64 candidate cells > the 63 left
        RM.run_unit("edge_donch", "NQ", "15", runs_dir=runs, ledger=led, log=tmp_path / "log", days=DAYS)
    assert ran == [] and not runs.exists() and len(LB.read_ledger(led)) == 1
    # null cells are not capped: a unit of 32 candidate cells + 64 null cells fits in the 63 left, and a C1 pool always runs
    with pytest.raises(Ran):
        RM.run_unit("edge_straddle_t", "NQ", "30", runs_dir=runs, ledger=led, log=tmp_path / "log", days=DAYS)
    with pytest.raises(Ran):
        RM.run_c1("NQ", "15", runs_dir=runs, ledger=led, log=tmp_path / "log", days=DAYS)
    assert ran == [1, 1] and len(LB.read_ledger(led)) == 1


def test_a_pass_that_dropped_a_session_writes_no_store_and_its_cells_still_count(tmp_path, monkeypatch):
    class Boom(FX.EdgeDonch):
        def fam_day(self, ctx):
            if self.day == "2022-06-13":
                raise RuntimeError("boom")
    monkeypatch.setitem(families.REGISTRY, "edge_boom", (Boom, {}, False, "test"))
    monkeypatch.setitem(families.LIBRARY, "edge_boom", families.check_library("edge_boom", Boom, {}, FX.EDGE_LIB)[1])
    Boom.session_independent = False                              # a class defined in a test cannot be re-imported by workers
    led, runs = tmp_path / "ledger.csv", tmp_path / "runs"
    out = RM.run_unit("edge_boom", "NQ", "15", workers=1, runs_dir=runs, ledger=led, log=tmp_path / "log", days=DAYS[:4])
    assert out[0]["ok"] is False and "boom" in out[0]["error"] and not (runs / "edge_boom-NQ-tf15").exists()
    rows = LB.read_ledger(led)
    assert rows[0]["stage"] == "build_error" and rows[0]["cells"] == "64" and not RM.done("edge_boom-NQ-tf15", runs, led)


def test_smoke_prints_counts_only(reg):
    o = RM.smoke("edge_donch", "NQ", "15", 10, 1)
    assert o["ok"] and o["cells"] == 64 and o["days"] == 10 and o["skipped_by_error"] == 0 and o["worker_parity"]
    assert o["segments"] == ["eve", "day"] and set(o["by_session"]) <= set(S.ORDER7) and o["both_sides_ok"] and o["nulls"] == {}
    assert o["hold_to"] == "day" and o["instances_per_cell"] == 7
    assert (o["exit_after_day_flat"], o["overlap_in_session"], o["entry_in_no_session"]) == (0, 0, 0)
    assert set(o["by_stop_mode"]) == {"atr", "pts", "pct"} and o["trades_total"] == o["long"] + o["short"] > 0
    t = RM.smoke("edge_straddle_t", "ES", None, 6, 2)
    assert t["ok"] and t["tf"] == "30" and t["root"] == "ES" and t["nulls"]["shift"]["skipped_by_error"] == 0 and t["both_sides_declared"]
    blob = json.dumps([o, t]).lower()
    for word in ("net", "pnl", "gross", "win", "exit_reason", "profit", "\"t\""):
        assert word not in blob, word                             # trade counts only: never a performance number
    assert all(d < "2024-01-01" for d in RM.SMOKE_DAYS) and len(RM.SMOKE_DAYS) == 10 and RM.PERIOD == "build"


def test_workers_never_exceed_the_cap_and_tapes_are_checked(monkeypatch):
    monkeypatch.setattr(RM, "busy_workers", lambda: 0)
    assert RM.auto_workers(64) <= 12 and RM.auto_workers(1) == 1
    monkeypatch.setattr(RM, "busy_workers", lambda: 999)
    assert RM.auto_workers(8) == 1
    assert RM.tapes_ready("NQ") == [] and RM.tapes_ready("ES") == []
    assert RM.unit_key("donchian", "GC", "15") == "donchian-GC-tf15" and RM.is_time_fired(l2ref.StraddleT) and not RM.is_time_fired(l2ref.Donchian)
