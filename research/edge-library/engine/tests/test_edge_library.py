"""library.py: the capped ledger, plateau judging, admission (fail closed), member folders, daily series, the PICK seal.
Synthetic trade lists only (tmp_path for every file): nothing here reads a tape or a result."""
import csv
import datetime as dt
import json

import numpy as np
import pytest

import l2sim as S
import library as LB


# ---- the ledger: HARD caps --------------------------------------------------------------------------------------------------

def test_caps_are_the_spec_and_a_menu_grid_of_n_cells_counts_n_cells(tmp_path):
    assert LB.CAPS == {"runs": 2000, "cells": 80000, "wfs": 40} and LB.LEDGER == LB.W / "ledger.csv"
    led = tmp_path / "ledger.csv"
    assert LB.ledger_used(path=led) == {"runs": 0, "cells": 0, "wfs": 0}
    LB.ledger_add("build", "donchian-NQ-tf15", "grid", cells=128, family="donchian", root="NQ", tf="15", period="build", path=led)
    LB.ledger_add("null", "c1-NQ-tf15", "null", cells=64, control="c1", path=led)      # a null grid: tracked, NOT capped
    LB.ledger_add("member", "m1-build", "run", path=led)
    LB.ledger_add("member", "m1-wf", "wf", path=led)
    LB.ledger_add("smoke", "x", "smoke", path=led)                # a smoke row counts nothing
    assert LB.ledger_used(path=led) == {"runs": 1, "cells": 128, "wfs": 1} and LB.ledger_nulls(path=led) == 64
    assert LB.ledger_left(path=led) == {"runs": 1999, "cells": 79872, "wfs": 39}
    rows = LB.read_ledger(led)
    assert [r["cells"] for r in rows] == ["128", "0", "0", "0", "0"] and tuple(rows[0]) == LB.COLS and rows[0]["finished_utc"]
    assert [r["null_cells"] for r in rows] == ["0", "64", "0", "0", "0"]
    assert LB.ledger_has("donchian-NQ-tf15", "build", led) and not LB.ledger_has("donchian-NQ-tf15", "null", led)
    with pytest.raises(ValueError, match="already holds"):
        LB.ledger_add("build", "donchian-NQ-tf15", "grid", cells=128, path=led)
    with pytest.raises(ValueError):
        LB.ledger_add("build", "k", "grid", path=led)             # a grid without its cell count
    with pytest.raises(ValueError):
        LB.ledger_add("build", "k", "screen", path=led)
    with pytest.raises(ValueError):
        LB.ledger_add("build", "k", "run", net=5.0, path=led)     # no P&L column in the ledger


def test_a_row_or_batch_past_a_cap_is_refused_and_nothing_is_appended(tmp_path):
    led = tmp_path / "ledger.csv"
    caps = {"runs": 2, "cells": 100, "wfs": 1}
    LB.ledger_add("build", "a", "grid", cells=96, path=led, caps=caps)
    before = led.read_text()
    with pytest.raises(LB.CapExceeded, match="cells"):
        LB.ledger_add("build", "b", "grid", cells=5, path=led, caps=caps)
    with pytest.raises(LB.CapExceeded):
        LB.ledger_check(cells=5, path=led, caps=caps)             # the batch pre-check says the same before anything runs
    assert led.read_text() == before
    assert LB.ledger_check(cells=4, runs=2, wfs=1, path=led, caps=caps) == {"runs": 0, "cells": 0, "wfs": 0}
    LB.ledger_add("build", "c", "grid", cells=4, path=led, caps=caps)            # exactly at the cap is allowed
    LB.ledger_add("m", "r1", "run", path=led, caps=caps)
    LB.ledger_add("m", "r2", "run", path=led, caps=caps)
    with pytest.raises(LB.CapExceeded, match="runs"):
        LB.ledger_add("m", "r3", "run", path=led, caps=caps)
    LB.ledger_add("m", "w1", "wf", path=led, caps=caps)
    with pytest.raises(LB.CapExceeded, match="wfs"):
        LB.ledger_add("m", "w2", "wf", path=led, caps=caps)
    LB.ledger_add("build_error", "e", "grid", cells=0 + 1, path=tmp_path / "l2.csv", caps=caps)
    LB.ledger_add("build_error", "e", "grid", cells=1, path=tmp_path / "l2.csv", caps=caps)      # failed batches: every attempt counts
    assert LB.ledger_used(path=tmp_path / "l2.csv")["cells"] == 2
    with pytest.raises(LB.CapExceeded):                            # the real caps hold for the real numbers
        LB.ledger_check(cells=80001, path=tmp_path / "none.csv")
    assert LB.ledger_check(cells=80000, runs=2000, wfs=40, path=tmp_path / "none.csv") == {"runs": 0, "cells": 0, "wfs": 0}


# ---- plateau ----------------------------------------------------------------------------------------------------------------

def table(nets):
    return [{"id": f"c{k}", "vi": k // 4, "xi": k % 4, "net": v, "trades": 50} for k, v in enumerate(nets)]


def test_plateau_needs_a_positive_median_and_sixty_percent_of_the_cells_positive():
    ok = LB.plateau(table([100, 200, 300, 400, 500, 600, -50, -60, 0, 10]))
    assert ok["pass"] and ok["cells"] == 10 and ok["share_pos"] == 0.7 and ok["median_net"] == 150.0 and ok["positive"] == 7
    assert LB.plateau(table([100, 200, 300, 400, 500, 600, -50, -60, -70, -80]))["pass"]           # exactly 60 % and median > 0
    thin = LB.plateau(table([5000, 4000, 3000, 2000, 1, -1, -1, -1, -1, -1]))                    # one great corner is not a plateau
    assert not thin["pass"] and thin["share_pos"] == 0.5 and thin["median_net"] == 0.0
    neg = LB.plateau(table([1, 1, 1, 1, 1, 1, 1, -5000, -5000, -5000, -5000, -5000]))
    assert not neg["pass"] and neg["share_pos"] == round(7 / 12, 4)
    zero = LB.plateau(table([0, 0, 0, 0, 0]))                    # cells without a trade are not > 0
    assert not zero["pass"] and zero["member"] is None and zero["share_pos"] == 0.0
    e = LB.plateau([])
    assert {k: e[k] for k in ("pass", "cells", "median_net", "share_pos", "positive", "member", "member_net", "best", "best_net",
                              "worst_net")} == {"pass": False, "cells": 0, "median_net": None, "share_pos": None, "positive": 0,
                                                "member": None, "member_net": None, "best": None, "best_net": None, "worst_net": None}
    assert e["verdicts"] == {"60": False, "70": False, "80": False} and e["dead"] == 0 and e["duplicates"] == 0
    with pytest.raises(ValueError):
        LB.plateau([{"id": "a", "net": 1}, {"id": "a", "net": 2}])


def test_the_member_is_the_central_cell_never_the_best_and_ties_go_to_the_simplest():
    nets = [100, 900, 300, 5000, 250, 240, 260, -50, -60, 10]
    p = LB.plateau(table(nets))
    assert p["median_net"] == 245.0 and p["member"] == "c4" and p["member_net"] == 250.0          # 250 and 240 are both 5 away: c4 first
    assert p["best"] == "c3" and p["best_net"] == 5000.0 and p["member"] != p["best"] and p["worst_net"] == -60.0
    sym = LB.plateau(table([240, 250, 260, 250, 240, 260, 250]))
    assert sym["median_net"] == 250.0 and sym["member"] == "c1"   # three cells AT the median: the lowest (variant, exit) index
    rev = LB.plateau([{"id": "x", "vi": 2, "xi": 0, "net": 250}, {"id": "y", "vi": 0, "xi": 5, "net": 250}, {"id": "z", "vi": 0, "xi": 1, "net": 250}])
    assert rev["member"] == "z"
    one = LB.plateau(table([-10, -20, -30, 70]))                  # a failed unit still names its central positive cell
    assert not one["pass"] and one["member"] == "c3"
    assert LB.plateau(table([300] * 32))["member"] == "c0"


# ---- trades, daily series ---------------------------------------------------------------------------------------------------

def trade(date, hhmm, net, mae=50.0, mins=10, side="long", eve=False, reason="tp", sl=95.0):
    d = dt.date.fromisoformat(date)
    ms = S.et_ns(d - dt.timedelta(days=1) if eve else d, hhmm) // 1_000_000
    return {"date": date, "side": side, "qty": 1, "entry_price": 100.0, "exit_price": 100.0 + (net + 4.0) / 20.0, "exit_reason": reason,
            "order_price": None, "sl": sl, "tp": 110.0, "gross": net + 4.0, "commission": 4.0, "net": net, "mae_pts": mae / 20.0,
            "mfe_pts": 1.0, "mae_usd": mae, "mfe_usd": 20.0, "bars": mins, "seconds": mins * 60.0, "entry_ms": ms,
            "exit_ms": ms + mins * 60000}


def test_pack_and_stats():
    tr = [trade("2023-03-14", "18:30", 100.0, eve=True), trade("2023-03-14", "08:30", -40.0, side="short", reason="sl"),
          trade("2023-03-14", "13:35", 60.0, reason="book", sl=None)]
    p = LB.pack(tr)
    assert p["sess"].tolist() == [LB.SESS_CODE["eve"], LB.SESS_CODE["pre"], LB.SESS_CODE["pm"]] and p["side"].tolist() == [1, -1, 1]
    assert p["date"].tolist() == [dt.date(2023, 3, 14).toordinal()] * 3 and p["dur_s"].tolist() == [600] * 3
    assert [LB.REASONS[i] for i in p["reason"]] == ["tp", "sl", "book"] and p["risk"][0] == 5.0 and np.isnan(p["risk"][2])
    st = LB.stats(p["net"])
    x = np.array([100.0, -40.0, 60.0])
    assert st["trades"] == 3 and st["net"] == 120.0 and st["t"] == pytest.approx(x.mean() / (x.std(ddof=1) / np.sqrt(3)))
    assert st["pf"] == 4.0 and st["win"] == pytest.approx(2 / 3)
    assert LB.stats([]) == {"trades": 0, "net": 0.0, "t": None, "pf": None, "win": None} and LB.stats([5.0])["t"] is None
    assert LB.pack([])["net"].shape == (0,)


def test_daily_rows_count_open_losses_and_minutes():
    cal = ["2023-03-13", "2023-03-14", "2023-03-15"]
    tr = [trade("2023-03-14", "09:35", 200.0, mae=80.0, mins=20), trade("2023-03-14", "10:30", -300.0, mae=350.0, mins=5),
          trade("2023-03-15", "18:10", 50.0, mae=10.0, mins=30, eve=True)]
    rows = LB.daily_rows(tr, cal, "build")
    assert [r["date"] for r in rows] == cal and [r["net"] for r in rows] == [0.0, -100.0, 50.0]
    assert rows[0] == {"date": "2023-03-13", "period": "build", "net": 0.0, "worst_open_loss": 0.0, "minutes_in_market": 0.0}
    # day 2: first trade dips to -(80 + 4) = -84; after it +200 is realised; the second dips to 200 - (350 + 4) = -154
    assert rows[1]["worst_open_loss"] == 154.0 and rows[1]["minutes_in_market"] == 25.0
    assert rows[2]["worst_open_loss"] == 14.0 and rows[2]["minutes_in_market"] == 30.0          # the evening trade is on its trade date
    both = [trade("2023-03-14", "09:35", 10.0, mae=100.0, mins=30), trade("2023-03-14", "09:40", 10.0, mae=200.0, mins=30)]
    assert LB.daily_rows(both, cal)[1]["worst_open_loss"] == 308.0                              # overlapping: the MAEs add
    with pytest.raises(ValueError, match="off the calendar"):
        LB.daily_rows(tr, cal[:2])
    assert LB.calendar("build")[0] == "2021-09-22" and LB.calendar("pick", "ES")[-1] == "2024-12-31" and len(LB.calendar("build", "GC")) > 500
    with pytest.raises(S.HoldoutSealed):
        LB.calendar("exam")


# ---- admission --------------------------------------------------------------------------------------------------------------

def good_member(n=80):
    days_b = [d.isoformat() for d in S.sessions("2023-01-03", "2023-06-30")][:n]
    days_p = [d.isoformat() for d in S.sessions("2024-01-02", "2024-06-28")][:n]
    rng = np.random.default_rng(5)

    def block(days):
        tr = [trade(d, "13:35", float(round(60 + 150 * rng.standard_normal(), 2)), mae=float(abs(round(120 * rng.standard_normal(), 2))))
              for d in days]
        pool = [trade(d, hm, float(round(150 * rng.standard_normal(), 2))) for d in days for hm in ("13:40", "14:10", "14:40")]
        return {"trades": tr, "stress": [dict(t, net=t["net"] - 12.0) for t in tr], "c1_pool": pool, "calendar": days}
    b, p = block(days_b), block(days_p)
    return {"name": "nq_test_tf15_pm", "family": "donchian", "root": "NQ", "tf": "15", "sess": "pm", "cell": "n20_atr1p5-r2",
            "inputs": {"n": 20, "stop_mode": "atr", "stop_val": 1.5, "tgt_r": 2.0},
            "rationale": "trend continuation: a close beyond the recent channel forces late sellers to cover into the move",
            "complexity": 3, "weak": False, "l2": False, "penalty": None,
            "plateau": {"build": LB.plateau(table([100, 200, 300, 400, 500, 600, -50, -60, 0, 10]))},
            "nulls_bar": {"bar": 1.5, "stat": "t", "nulls": 40, "thin": False}, "build": b, "pick": p}


def test_admission_admits_a_member_that_passes_every_test_and_writes_its_folder(tmp_path):
    m = good_member()
    r = LB.admission(m, write=True, members_dir=tmp_path)
    assert r["admit"], r["failed"]
    assert set(r["tests"]) == {"net_build", "net_pick", "plateau_build", "beats_c1_build", "beats_c1_pick", "stress_build", "stress_pick",
                               "above_best_of_nulls_build", "min_trades", "open_loss_fits", "rationale"}
    assert r["tests"]["stress_build"]["base"] > r["tests"]["stress_build"]["stressed"] > 0      # base and stressed side by side
    assert r["tests"]["open_loss_fits"]["micros_fit_worst"] >= 1 and r["tests"]["min_trades"] == {"pass": True, "build": 80, "pick": 80, "need": 100}
    d = tmp_path / m["name"]
    assert sorted(x.name for x in d.iterdir()) == ["card.md", "daily.csv", "spec.json", "trades_build.json", "trades_pick.json"]
    assert json.loads((d / "trades_build.json").read_text()) == m["build"]["trades"]
    spec = json.loads((d / "spec.json").read_text())
    assert spec["admit"] and spec["contracts"] == 1 and spec["rationale"] == m["rationale"] and spec["complexity"] == 3
    rows = list(csv.DictReader((d / "daily.csv").open()))
    assert list(rows[0]) == ["date", "period", "net", "worst_open_loss", "minutes_in_market"] and len(rows) == 160
    assert {r_["period"] for r_ in rows} == {"build", "pick"} and round(sum(float(r_["net"]) for r_ in rows), 2) == round(
        sum(t["net"] for t in m["build"]["trades"] + m["pick"]["trades"]), 2)
    card = (d / "card.md").read_text()
    for needle in ("ADMITTED", "Rationale (written before testing)", "Complexity count", "## Plateau", "## Periods", "## Nulls",
                   "stressed net (2 ticks + 250 ms)", "EXAM (>= 2025-01-01) was not read"):
        assert needle in card, needle


@pytest.mark.parametrize("breaker,failed", [
    (lambda m: m["pick"].update(trades=[dict(t, net=-abs(t["net"])) for t in m["pick"]["trades"]]), "net_pick"),
    (lambda m: m["plateau"].update(build=LB.plateau(table([5000, 1, -1, -1, -1]))), "plateau_build"),
    (lambda m: m["build"].update(c1_pool=[dict(t, net=t["net"] + 400.0) for t in m["build"]["c1_pool"]]), "beats_c1_build"),
    (lambda m: m["pick"].pop("c1_pool"), "beats_c1_pick"),                                       # a missing input fails closed
    (lambda m: m.update(nulls_bar={"bar": 99.0, "stat": "t", "nulls": 40, "thin": False}), "above_best_of_nulls_build"),
    (lambda m: m.pop("nulls_bar"), "above_best_of_nulls_build"),
    (lambda m: m["build"].update(stress=[dict(t, net=t["net"] - 500.0) for t in m["build"]["trades"]]), "stress_build"),
    (lambda m: m["pick"].pop("stress"), "stress_pick"),
    (lambda m: m["build"]["trades"][0].update(mae_usd=25000.0), "open_loss_fits"),               # $2,501 open loss on ONE micro
    (lambda m: m.update(rationale="it works"), "rationale"),
    (lambda m: m.pop("complexity"), "rationale"),
    (lambda m: m.update(weak=True, nulls_bar={"bar": -9.0, "stat": "t", "nulls": 40, "thin": False},
                        build=dict(m["build"], trades=[dict(t, net=t["net"] - 45.0) for t in m["build"]["trades"]],
                                   stress=[dict(t, net=1.0) for t in m["build"]["trades"]],
                                   c1_pool=[dict(t, net=-50.0) for t in m["build"]["c1_pool"]])), "weak_margin"),
    (lambda m: m.update(penalty="in-sample favourite that FAILED on 2025-26"), "plateau_pick"),
    (lambda m: m.update(l2=True), "beats_c2_build"),
])
def test_admission_fails_closed_on_each_test(breaker, failed, tmp_path):
    m = good_member()
    breaker(m)
    r = LB.admission(m, write=True, members_dir=tmp_path)
    assert not r["admit"] and failed in r["failed"], r["failed"]
    d = tmp_path / "_rejected" / m["name"]
    assert sorted(x.name for x in d.iterdir()) == ["card.md", "spec.json"] and "REJECTED" in (d / "card.md").read_text()
    assert not (tmp_path / m["name"]).exists()                    # a rejected candidate never gets a member folder


def test_admission_needs_100_trades_and_an_l2_member_needs_both_c2_nulls():
    m = good_member(n=45)
    r = LB.admission(m)
    assert r["failed"] == ["min_trades"] and r["tests"]["min_trades"]["build"] == 45
    m = good_member()
    m["l2"] = True
    for per in ("build", "pick"):
        m[per]["c2"] = [[dict(t, net=t["net"] - 80.0) for t in m[per]["trades"]], [dict(t, net=t["net"] - 90.0) for t in m[per]["trades"]]]
    r = LB.admission(m)
    assert r["admit"] and r["tests"]["beats_c2_build"]["lift"] > 0 and len(r["tests"]["beats_c2_pick"]["c2_nets"]) == 2
    m["pick"]["c2"] = m["pick"]["c2"][:1]                          # one seed is not the pre-registered two
    assert LB.admission(m)["failed"] == ["beats_c2_pick"]


def test_pick_is_sealed_for_a_candidate_that_did_not_survive_build(monkeypatch):
    import fam_fixtures as FX
    import families
    monkeypatch.setitem(families.REGISTRY, "edge_donch", (FX.EdgeDonch, {}, False, "test"))
    monkeypatch.setitem(families.LIBRARY, "edge_donch", families.check_library("edge_donch", FX.EdgeDonch, {}, FX.EDGE_LIB)[1])
    x = S.menu("NQ")[0]
    for bad in (None, {}, {"pass": False}, {"pass": 1}):
        with pytest.raises(LB.PickSealed):
            LB.run_member("edge_donch", "NQ", "15", {"n": 20}, x, "pick", sess="pm", build_plateau=bad, days=["2024-03-05"])
    with pytest.raises(ValueError, match="EXAM"):
        LB.run_member("edge_donch", "NQ", "15", {"n": 20}, x, "exam", sess="pm", days=["2025-03-05"])
    with pytest.raises(ValueError, match="member's session"):
        LB.run_member("edge_donch", "NQ", "15", {"n": 20}, x, "build", days=["2023-03-14"])
    days = ["2023-03-14", "2023-03-15", "2023-03-16"]
    r = LB.run_member("edge_donch", "NQ", "15", {"n": 20}, x, "build", sess="pm", days=days)
    # the member's ONE session with the library's exit convention (hold_to day), as run_menus ran it
    assert r["meta"]["inputs"]["n"] == 20 and r["meta"]["inputs"]["sess"] == "pm" and r["meta"]["inputs"]["hold_to"] == "day"
    assert r["key"] == "edge_donch-NQ-tf15-pm-n20_atr1p5-r0-build"
    assert r["session"] == "pm" and r["trades"] and all(S.session_of(t["entry_ms"]) == "pm" for t in r["trades"])
    e = LB.run_member("edge_donch", "NQ", "15", {"n": 20}, x, "build", sess="eve", days=days)
    assert e["meta"]["inputs"]["sess"] == "eve" and e["meta"]["segments"] == ["eve"] and all(S.session_of(t["entry_ms"]) == "eve" for t in e["trades"])
    s = LB.run_member("edge_donch", "NQ", "15", {"n": 20}, x, "build", sess="pm", stress=True, days=days)
    assert s["meta"]["stress"] == {"slip_ticks": 2.0, "latency_ms": 250} and s["key"].endswith("-build-stress")
