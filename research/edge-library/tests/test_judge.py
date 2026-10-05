"""REGRESSION LOCK of judge.py, two layers, from the stores on disk.

LAYER A (`--as-v2`: 200 draws, the first 2 control seeds, >= 60 %, a year de-duplicated again) -- judge.py must reproduce out/v2
(the ADMISSION v2 re-judge of 2026-10-04) EXACTLY, same draws, same seeds: verdicts, share positive, table average, lift, share of
random tables beaten, 2024 average / median / stressed average, default variant, surviving set -- for ALL 14 members, all 43 other
BUILD passers, a fixed-seed sample of BUILD failures across stages x unit types x failure reasons, the 168 placebo units, the 14
cards. LAYER B (the rule in force, EDGE_SPEC "ADMISSION v2 -- CHECKER FIXES" F1-F6) -- the 4,000 draws are the checker's own
(out/check_v2/chk_seed.json, draw for draw), every control seed on disk is used, 60 % is strict, both speed shares, the BUILD
variant list on a later year, every store logged; with JUDGE_FULL=1 also the exact list of BUILD verdicts that change versus v2.
Reads BUILD and 2024 stores only, from the six folders out/v2 read (runs/, runs_v2/, runs_admit*/, runs_deepen/, runs_events/): a
2025 store or an extra-seed folder that appears later cannot change it. The CHECK path is exercised as a dry run on the 2024
stores (no 2025 file is read or made). Temporary files live in tests/ and are removed.

  pytest tests/test_judge.py            (about 2 minutes)       python tests/test_judge.py        the same, with a count per block
  JUDGE_FULL=1 pytest tests/test_judge.py     + every one of the 1,916 BUILD rows at both settings (about 7 minutes more)

KNOWN, DOCUMENTED differences from out/v2 at `--as-v2` (JUDGE.md "Differences"), the only ones layer A lets through:
  a. out/v2/final.json lists test "6" as failed for a unit whose stress pass was never run (it failed (4) or (5) first);
     judge.py lists only tests that were judged and names the rest in `not_judged`. Same on a card's bar-size line.
  b. a card's "SAME IDEA as ..." names are in folder order here, in out/v2's judging order there (the same set).
  c. card layout after the checker fixes: the "Real edge" table (seeds, one decimal) and the "Speed" lines (two shares), the
     thin-control and FAST flags. Their numbers are locked against out/v2/members.json instead of the card text.
"""
from __future__ import annotations

import csv
import json
import math
import os
import random
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
import judge as J  # noqa: E402

V2 = W / "out" / "v2"
HERE = Path(__file__).resolve().parent
SEED = 20261005
PER_STRATUM = 2
B = {r["uid"]: r for r in json.loads((V2 / "build_units.json").read_text())}
P = json.loads((V2 / "pick_units.json").read_text())
FIN = json.loads((V2 / "final.json").read_text())
MEM = json.loads((V2 / "members.json").read_text())
MEMBERS = [uid for uid, f in FIN.items() if f["admit"]]
PASSERS = [uid for uid, r in B.items() if r["build_pass"]]
# LAYER B, pinned to the first 2 seeds (what is on disk today): the BUILD verdicts that change versus out/v2
TO_PASS = ["donchian-NQ-tf30|nyam|", "donchian-NQ-tf5|pm|", "vwap_z-NQ-tf30|mid|", "vol_spike_break-NQ-tf5|pm|"]          # F1: 4,000 draws
TO_FAIL_F1 = ["ema_pullback-NQ-tf1|nyam|", "flow_exhaust-NQ-tf1|eve|", "tema_slope-NQ-tf30|mid|", "vwap_band-NQ-tf30|eve|",
              "vwap_flip-NQ-tf15|pm|", "orb_confirm-ES-tf1|pm|dir=long"]                                                # opened on a lucky 200-draw seed
TO_FAIL_F3 = ["first_bar_mom-GC-tf30|mid|", "straddle_t_1105-NQ-tf30|mid|"]                                             # exactly 60 %
# the lock reads only the six store folders out/v2 read, and nothing after 2024, whatever else appears under runs*/
PIN = {"dirs": J.PRIORITY, "upto": "pick"}
NOW = {"draws": J.DRAWS, "seeds": 2, "strict": True, "dedup_year": False, **PIN}


@contextmanager
def rule(**kw):
    keep = dict(J.RULE)
    J.RULE.update(kw)
    try:
        yield
    finally:
        J.RULE.clear()
        J.RULE.update(keep)


def addr(r: dict) -> str:
    filt = r["group"] or r["side"]
    return f"{r['key']}-{r['sess']}" + (f":{r['label']}" if r["label"] else "") + (f"@{filt}" if filt else "")


def sample() -> list:
    """BUILD failures: PER_STRATUM per (stage, controls, failed tests, control drawn or not), fixed seed."""
    rng, strata = random.Random(SEED), {}
    for uid, r in B.items():
        if not r["build_pass"]:
            strata.setdefault((r["src"], r["controls"], r["fail"], r["t2"] is not None), []).append(uid)
    return [uid for k in sorted(strata) for uid in rng.sample(sorted(strata[k]), min(PER_STRATUM, len(strata[k])))]


def same(a, b) -> bool:
    """Equal; for a dict: every key of out/v2's (`b`) has the same value here (judge.py may carry more: seeds, stores)."""
    if isinstance(a, bool) or isinstance(b, bool) or a is None or b is None or isinstance(a, str) or isinstance(b, str):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=1e-12, abs_tol=1e-9)
    if isinstance(a, dict) and isinstance(b, dict):
        return all(k in a and same(a[k], b[k]) for k in b)
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return len(a) == len(b) and all(same(x, y) for x, y in zip(a, b))
    return a == b


def diff(uid: str, what: str, mine, theirs, out: list) -> None:
    if not same(mine, theirs):
        out.append(f"{uid}: {what}: judge.py {mine!r} != out/v2 {theirs!r}")


_J: dict = {}


def judged(uid: str) -> dict:
    """The unit judged on BUILD + 2024 under the rule now set (cached per rule)."""
    k = (uid, tuple(sorted(J.RULE.items(), key=str)))
    if k not in _J:
        _J[k] = J.judge(J.unit(addr(B[uid])), J.YEARS[:1])
    return _J[k]


BUILD_KEYS = ("cells", "dead", "dup", "share_pos", "avg_net", "median_net", "avg_trades", "days_build", "days_2024", "t1", "t2", "t3",
              "build_pass", "fail")
DRAWN_KEYS = ("v60", "v70", "v80", "exact60", "reach_trades", "fast_profit_share")


def check_build(uid: str, mine: dict) -> list:
    bad, r = [], B[uid]
    for k in ("uid", "key", "family", "root", "tf", "sess", "label", "group", "side", "timed", "l2", "stage_d", "weak", "penalty"):
        diff(uid, k, mine[k], r[k], bad)
    diff(uid, "controls of the unit type", mine["controls_used"], r["controls"], bad)
    for k in BUILD_KEYS + tuple(k for k in DRAWN_KEYS if k in r):
        diff(uid, f"BUILD {k}", mine.get(k), r[k], bad)
    det = json.loads(r.get("detail") or "{}")
    diff(uid, "BUILD controls drawn", sorted(mine["controls"]), sorted(det), bad)
    diff(uid, "BUILD control verdicts (lift, share of replicates beaten, ...)", mine["controls"], det, bad)
    return bad


def check_year(uid: str, j: dict) -> list:
    bad, o, f = [], P[uid], FIN[uid]
    if "pick" not in j:
        return [f"{uid}: judge.py did not judge 2024: {j.get('pick_refused')}"]
    y = j["pick"]
    for k in ("cells", "share_pos", "avg_net", "median_net", "avg_trades", "v60", "v70", "v80", "t4", "t5", "controls", "t3_final", "fast_profit_share"):
        diff(uid, f"2024 {k}", y[k], o[k], bad)
    diff(uid, "BUILD + 2024 trades", y["trades_total"], o["trades_build_plus_2024"], bad)
    diff(uid, "2024 store", y["store"].split("/")[1], o["store"], bad)
    if "t6" in o:                                           # out/v2 ran the stress pass for this unit
        for k in ("t6", "stress_avg_net", "stress_median_net", "stress_share_pos", "oco_cancel_ms"):
            diff(uid, f"2024 {k}", y[k], o[k], bad)
        diff(uid, "failed tests", y["failed"], f["failed"], bad)
    else:                                                   # known difference a.: out/v2 writes "6" although it never ran
        diff(uid, "failed tests (+ the unrun 6 of out/v2)", [k for k in y["failed"] if k != "6"] + ["6"], f["failed"], bad)
    diff(uid, "admit", y["admit"], f["admit"], bad)
    diff(uid, "member folder name", y["name"], f["name"], bad)
    diff(uid, "surviving set (in order)", y["survivors"] or [], f["survivors"], bad)
    diff(uid, "default variant", y["default"], f["default"], bad)
    if f["default"]:
        diff(uid, "default BUILD net", y["default_build_net"], f["default_build_net"], bad)
    return bad


def run_units(uids: list, year: bool) -> tuple:
    bad, ok = [], 0
    for uid in uids:
        j = judged(uid)
        b = check_build(uid, j["build"]) + (check_year(uid, j) if year else [])
        ok += not b
        bad += b
    return ok, len(uids), bad


RESULTS: dict = {}


def lock(**kw):
    """A test runs under the rule `kw` and returns nothing to pytest; its (reproduced, total, mismatches) count is kept for
    the __main__ report."""
    def deco(fn):
        def test():
            with rule(**kw):
                RESULTS[fn.__name__] = fn()
        test.__name__, test.__doc__ = fn.__name__, fn.__doc__
        return test
    return deco


# ================================================================ LAYER A: out/v2 exactly

@lock(**J.AS_V2)
def test_catalog_and_unit_types():
    """All 1,916 units: the catalog is out/v2's, and each unit's type (hence its controls) derives from its store + the engine."""
    assert [J.unit(a)["uid"] for a in J.catalog("all")] == list(B), "catalog('all') is not the 1,916 units of out/v2 in order"
    bad = []
    for uid, r in B.items():
        u = J.unit(addr(r))
        for k in ("uid", "timed", "l2", "stage_d", "weak", "penalty"):
            diff(uid, k, u[k], r[k], bad)
        diff(uid, "controls", "+".join(u["controls"]), r["controls"], bad)
        if "|" in uid:
            diff(uid, "v2 uid accepted as an address", J.unit(uid)["addr"], u["addr"], bad)
    assert not bad, "\n".join(bad)
    return len(B), len(B), bad


@lock(**J.AS_V2)
def test_event_days_are_stage_3():
    """The day filters A / B / C are EDGE_SPEC STAGE 3's (out/events/ev.py) on BUILD + 2024, and never reach the EXAM."""
    import datetime as dt
    sys.path.insert(0, str(W / "out" / "events"))
    import ev as E
    seal = dt.date(2025, 1, 1).toordinal()
    for g in "ABC":
        mine = J.event_ords(g)
        assert list(mine[mine < seal]) == list(E.ords(g)), g
        assert mine.max() < dt.date.fromisoformat(J.EXAM_START).toordinal()
    return 3, 3, []


@lock(**J.AS_V2)
def test_members_all_six():
    ok, n, bad = run_units(MEMBERS, True)
    assert len(MEMBERS) == 14 and not bad, "\n".join(bad)
    return ok, n, bad


@lock(**J.AS_V2)
def test_other_build_passers_fail_2024_the_same_way():
    uids = [u for u in PASSERS if u not in MEMBERS]
    ok, n, bad = run_units(uids, True)
    assert len(uids) == 43 and not bad, "\n".join(bad)
    assert not any(judged(u)["pick"]["admit"] for u in uids)
    return ok, n, bad


@lock(**J.AS_V2)
def test_sampled_build_failures():
    uids = sample()
    ok, n, bad = run_units(uids, False)
    assert n >= 40 and not bad, "\n".join(bad)
    for uid in uids:                                        # a unit that fails BUILD is never read on 2024
        assert "pick" not in judged(uid)
        try:
            J.year(J.unit(addr(B[uid])), "pick", judged(uid)["build"])
            raise AssertionError(f"{uid}: 2024 was judged for a unit that fails BUILD")
        except J.Refuse:
            pass
    return ok, n, bad


@lock(**J.AS_V2)
def test_placebo_one_of_168():
    """The whole procedure on the random-entry stores (out/v2/placebo.py): the same counts, the same single passer."""
    rows = {r["uid"]: r for r in csv.DictReader((V2 / "placebo.csv").open())}
    want = json.loads((V2 / "placebo_counts.json").read_text())
    bad, got, ok = [], {"units": 0, "t1": 0, "build_pass": 0, "t4": 0, "t4_t5": 0, "t6": 0, "all_six": 0, "passers": []}, 0
    tb = lambda v: v == "True"  # noqa: E731
    for a in J.catalog("placebo"):
        u = J.unit(a)
        r, j, n0 = rows[u["uid"]], J.judge(u, J.YEARS[:1]), len(bad)
        b, y = j["build"], j.get("pick")
        for k in ("cells", "share_pos", "avg_net", "avg_trades"):
            diff(u["uid"], k, b[k], float(r[k]), bad)
        for k in ("t1", "t3", "build_pass"):
            diff(u["uid"], k, b[k], tb(r[k]), bad)
        diff(u["uid"], "t2", bool(b["t2"]), tb(r["t2"]), bad)
        if r["lift"]:
            diff(u["uid"], "lift", b["controls"]["c1"]["lift"], float(r["lift"]), bad)
            diff(u["uid"], "p_beat", b["controls"]["c1"]["p_beat"], float(r["p_beat"]), bad)
            diff(u["uid"], "control = the other seed", b["controls"]["c1"]["seeds"], [3 - u["placebo"]], bad)
        diff(u["uid"], "opened on 2024", y is not None, tb(r["opened_2024"]), bad)
        if y:
            diff(u["uid"], "t4", y["t4"], tb(r["t4"]), bad)
            diff(u["uid"], "t5", y["t4"] and y["t5"], tb(r["t4"]) and tb(r["t5"]), bad)
            diff(u["uid"], "t6", bool(y["t6"]), tb(r["t6"]), bad)
            diff(u["uid"], "survivors", len(y["survivors"] or []), int(r["survivors"]), bad)
        diff(u["uid"], "passes all six", bool(y and y["admit"]), tb(r["passed"]), bad)
        got["units"] += 1
        got["t1"] += b["t1"]
        got["build_pass"] += b["build_pass"]
        got["t4"] += bool(y and y["t4"])
        got["t4_t5"] += bool(y and y["t4"] and y["t5"])
        got["t6"] += bool(y and y["t6"])
        got["all_six"] += bool(y and y["admit"])
        got["passers"] += [u["uid"]] if y and y["admit"] else []
        ok += len(bad) == n0
    assert got == want and not bad, f"{got} != {want}\n" + "\n".join(bad)
    return ok, 168, bad


def _norm(line: str) -> str:
    """Known differences a. and b. on a card line."""
    line = line.replace(" (6 not run)", ", 6")
    if "SAME IDEA as " in line:
        head, tail = line.split("SAME IDEA as ", 1)
        names, rest = tail.split(": one strategy", 1)
        line = head + "SAME IDEA as " + ", ".join(sorted(names.split(", "))) + ": one strategy" + rest
    return line


def _sections(text: str) -> dict:
    out, cur = {"top": []}, "top"
    for line in text.split("\n"):
        if line.startswith("## "):
            cur = line[3:].split(" (")[0].split(":")[0]
            out[cur] = []
        elif not line.startswith("**Flags:**"):
            out[cur].append(_norm(line))
    return out


@lock(**J.AS_V2)
def test_cards_and_surviving_sets():
    """`judge.py card` (written to a temp folder, members/ is not touched) = the 14 cards and surviving sets on disk, section by
    section (known difference c.: the Real edge and Speed sections and two flags changed layout), and the numbers of
    out/v2/members.json."""
    bad, ok = [], 0
    groups = {n: sorted(g) for g in MEM["groups"] for n in g}
    odd = lambda f: f.startswith(("thin control", "FAST"))  # noqa: E731
    with tempfile.TemporaryDirectory(dir=HERE) as tmp:
        for v in MEM["members"]:
            uid, n0 = v["uid"], len(bad)
            u = J.unit(addr(B[uid]))
            m = J.member(u, periods=J.YEARS[:1])            # BUILD + 2024 only: what out/v2 wrote
            d = J.card(u, tmp, m=m)
            ref = J.LB.MEMBERS / v["name"]
            if "share of gross profit from trades held under 5 s: BUILD" in (ref / "card.md").read_text():   # still out/v2's card
                diff(uid, "surviving_set.csv", (d / "surviving_set.csv").read_text(), (ref / "surviving_set.csv").read_text(), bad)
                mine, theirs = _sections((d / "card.md").read_text()), _sections((ref / "card.md").read_text())
                for s in ("top", "Average variant and default variant, per year then combined", "Share of variants profitable", "Stress", "Size"):
                    diff(uid, f"card.md section {s!r}", mine[s], theirs[s], bad)
            for k in ("avg_rows", "worst_open_loss", "variants_judged", "default", "idea", "rule", "rationale"):
                diff(uid, k, m[k], v[k], bad)
            diff(uid, "flags", [f for f in m["flags"] if not odd(f)], [f for f in v["flags"] if not odd(f)], bad)
            diff(uid, "thin-control flags of out/v2 kept", [f for f in v["flags"] if f.startswith("thin") and f not in m["flags"]], [], bad)
            diff(uid, "FAST by gross share (out/v2's flag)", (m["fast_avg"]["all"]["fast_profit_share"] or 0) > 0.5, any(f.startswith("FAST") for f in v["flags"]), bad)
            diff(uid, "FAST flag = net share > 50 %", any(f.startswith("FAST") for f in m["flags"]), (m["fast_avg"]["all"]["fast_net_share"] or 0) > 0.5, bad)
            diff(uid, "default per year", [{k: r[k] for k in ("period", "trades", "net", "win", "pf", "max_dd", "avg_trade")} for r in m["default_rows"]],
                 [{k: r[k] for k in ("period", "trades", "net", "win", "pf", "max_dd", "avg_trade")} for r in v["default_rows"]], bad)
            diff(uid, "default under stress", m["default_stress"], v["default_stress"], bad)
            diff(uid, "controls BUILD", m["judge"]["build"]["controls"], v["controls_build"], bad)
            diff(uid, "controls 2024", m["judge"]["pick"]["controls"], v["controls_pick"], bad)
            diff(uid, "siblings", [_norm(s) for s in m["siblings"]], v["siblings"], bad)
            diff(uid, "same idea", sorted(m["same"] + [m["name"]]), groups[v["name"]], bad)
            diff(uid, "surviving-set size", len(m["surviving"]), v["survivors"], bad)
            for p in ("build", "pick", "all"):
                diff(uid, f"fast share {p}", m["fast_avg"][p], v["fast_avg"][p], bad)
            diff(uid, "default fast share", m["fast_default"], v["fast_default"], bad)
            ok += len(bad) == n0
    assert not bad, "\n".join(bad)
    return ok, len(MEM["members"]), bad


@lock(**J.AS_V2)
def test_refusals():
    """No simulation, no sealed period, no year for a unit that failed before it; a missing year names what to run."""
    u, keep = J.unit("orb-NQ-tf15-pre"), {p: dict(J.PERIODS[p]) for p in J.YEARS}
    b = judged("orb-NQ-tf15|pre|")["build"]
    try:
        for p in J.YEARS:                                   # an empty date range stands for "no store of that year": none is looked at
            J.PERIODS[p] = {**keep[p], "range": ("1990-01-01", "1990-12-31")}
        try:                                                # a BUILD passer whose 2024 menu was never run: refused, with the jobs
            J.year(u, "pick", b)
            raise AssertionError("2024 was judged without a store")
        except J.Refuse as e:
            assert "2024 store orb-NQ-tf15-pre-pick is not on disk" in str(e) and len(e.jobs) == 2 and len(e.jobs[0]["cells"]) == 96
        J.PERIODS["pick"] = keep["pick"]
        for period, word in (("check", "2025 store orb-NQ-tf15-pre-check is not on disk"), ("exam", "sealed")):
            try:
                J.year(u, period, b)
                raise AssertionError(f"{period} was judged")
            except J.Refuse as e:
                assert word in str(e), str(e)
                if period == "check":
                    assert e.jobs and all(j["period"] == "check" for j in e.jobs)
                    assert e.jobs[1] == {"c1": True, "root": "NQ", "tf": "15", "sess": "pre", "period": "check"}
    finally:
        J.PERIODS.update(keep)
    for a in ("orb-NQ-tf15-pre@Z", "nonsense", "no_such_family-NQ-tf5-pm", "c1-NQ-tf1-eve"):
        try:
            J.unit(a)
            raise AssertionError(a)
        except J.Refuse:
            pass
    assert not any(r["dir"].name in J.VOID for r in J.index()), "a VOID store is in the index"
    return 8, 8, []


@lock(**J.AS_V2)
def test_check_path_dry_run_on_2024():
    """CHECK runs the SAME code as PICK. Dry run: point the check period at the 2024 stores (nothing dated 2025 is read) ->
    tests (4) and (6) repeat the 2024 numbers, every member is CONFIRMED, its saved default and variants are reported, and
    the card grows a row per period."""
    keep = dict(J.PERIODS["check"])
    bad = []
    try:
        J.PERIODS["check"] = {**J.PERIODS["pick"], "name": "2025"}
        for uid in ("orb-NQ-tf15|pre|", "E1-A-GC", "straddle_t_1800-NQ-tf30|eve|"):
            u, j = J.unit(addr(B[uid])), judged(uid)
            y, c = j["pick"], J.year(J.unit(addr(B[uid])), "check", j["build"])
            for k in ("cells", "avg_net", "median_net", "share_pos", "t4", "t6", "stress_avg_net", "survivors", "default"):
                diff(uid, f"check dry run {k}", c[k], y[k], bad)
            diff(uid, "check verdict", c["verdict"], "CONFIRMED", bad)
            diff(uid, "saved variants profitable", c["saved_profitable"], len(y["survivors"]), bad)
            diff(uid, "default net", c["default_net"], float(J.cellx(J.find(J.skey(u["key"], u, "pick"), "pick")[0], y["default"], u["sess"], u)["net"].sum()), bad)
        md = J.card_md(J.member(J.unit("orb-NQ-tf15-pre"), periods=J.YEARS))
        assert "| 2025 under stress |" in md and "**2025 (read once, after choosing; nothing re-tuned): CONFIRMED**" in md and "2026+ was never read" in md
    finally:
        J.PERIODS["check"] = keep
        J._CAL.clear()
    assert not bad, "\n".join(bad)
    return 3, 3, bad


def _full(expect_pass: list, expect_fail: list) -> tuple:
    rows = J.table_rows(J.catalog("all"), 8)
    bad, ok = [], 0
    for r, (uid, v) in zip(rows, B.items()):
        n0 = len(bad)
        diff(uid, "uid", r["uid"], uid, bad)
        want = (v["build_pass"] or uid in expect_pass) and uid not in expect_fail
        diff(uid, "BUILD verdict", r["build_pass"], want, bad)
        if not (expect_pass or expect_fail):                # layer A: every number
            for k in BUILD_KEYS + tuple(k for k in DRAWN_KEYS if k in v):
                diff(uid, f"BUILD {k}", r.get(k), v[k], bad)
            for c, d in json.loads(v.get("detail") or "{}").items():
                for k in ("pass", "lift", "p_beat", "ctl_mean", "lift_per_trade", "per_trade", "why"):
                    if k in d:
                        diff(uid, f"BUILD {c} {k}", r.get(f"{c}_{k}"), d[k], bad)
            if v["build_pass"]:
                diff(uid, "2024 average", r.get("pick_avg_net"), P[uid]["avg_net"], bad)
        if v["build_pass"] and want:
            diff(uid, "admit", bool(r.get("admit")), FIN[uid]["admit"], bad)
        ok += len(bad) == n0
    adm = {r["uid"] for r in rows if r.get("admit")}       # the 14 stay; a new BUILD passer may join them once its 2024 stores are complete
    assert set(MEMBERS) <= adm and adm - set(MEMBERS) <= set(expect_pass) and not bad, f"members {sorted(adm ^ set(MEMBERS))}\n" + "\n".join(bad[:60])
    assert not any(k.startswith("check_") for r in rows for k in r), "a 2025 store was read"
    return ok, len(rows), bad


def _skip_unless_full():
    if not os.environ.get("JUDGE_FULL"):
        import pytest
        pytest.skip("set JUDGE_FULL=1")


@lock(**J.AS_V2)
def test_full_build_table_as_v2():
    """JUDGE_FULL=1: every one of the 1,916 BUILD rows of out/v2, through `judge.py table`'s own code path (8 workers)."""
    _skip_unless_full()
    return _full([], [])


# ================================================================ LAYER B: the rule in force (CHECKER FIXES F1-F6)

@lock(**NOW)
def test_f1_4000_draws_are_the_checkers():
    """F1: the 4,000 draws are the checker's 20 seeds x 200 (out/check_v2/chk_seed.json) draw for draw, so the ten units whose
    BUILD verdict hangs on the number of draws flip exactly as the checker found: 4 to pass, 6 (lucky 200-draw seed) to fail."""
    chk = json.loads((W / "out" / "check_v2" / "chk_seed.json").read_text())
    bad = []
    for uid in TO_PASS + TO_FAIL_F1:
        b = J.build(J.unit(addr(B[uid])))
        c = b["controls"]["c1"]
        diff(uid, "share of 4,000 random tables beaten (checker)", c["p_beat"], round(chk[uid]["p_4000"], 4), bad)
        diff(uid, "lift at 4,000 draws (checker)", c["lift"], round(chk[uid]["lift_4000"], 2), bad)
        diff(uid, "replicates / seeds", (c["replicates"], c["seeds"]), (4000, [1, 2]), bad)
        diff(uid, "BUILD verdict", b["build_pass"], uid in TO_PASS, bad)
        diff(uid, "BUILD verdict of out/v2 was the opposite", B[uid]["build_pass"], uid not in TO_PASS, bad)
    assert not bad, "\n".join(bad)
    return 10, 10, bad


def _copy_store(src: Path, dst: Path, seed_map: dict, inputs: dict | None = None, add_net: float = 0.0, rename: bool = True) -> None:
    """A synthetic control store for the seed tests: the same cells under other seed numbers (optionally other inputs / nets;
    rename=False keeps the ids s1_ / s2_ and changes only the cells' seed input)."""
    dst.mkdir(parents=True)
    m = json.loads((src / "run.json").read_text())
    for c in m["cells"]:
        s, rest = c["id"].split("_", 1)
        new = seed_map[int(s[1:])]
        c["id"] = f"s{new}_{rest}" if rename else c["id"]
        for k in ("seed", "shift_seed"):
            if k in c["inputs"]:
                c["inputs"][k] = new
        c["inputs"].update(inputs or {})
    m["key"] = dst.name
    (dst / "run.json").write_text(json.dumps(m))
    z = dict(np.load(src / "cells.npz"))
    z["net"] = z["net"] + add_net
    np.savez(dst / "cells.npz", **z)


@lock(draws=200, seeds=None, strict=True, dedup_year=False, **PIN)
def test_f2_every_seed_on_disk():
    """F2: more control seeds in ANY store folder are found and used (synthetic stores in a temp folder: seeds 3-4 = copies of
    seeds 1-2; seeds 7-8 = the same under the ids s1_ / s2_), a store that is not the same control is not, the first-2-seeds
    result is kept beside the new one, `--seeds 2` is out/v2 again, and a member that fails (2) with every seed is DEMOTED."""
    orb, ev = J.unit("orb-NQ-tf15-pre"), J.unit("straddle_tight_0830-NQ-tf30-pre@A")
    v2 = json.loads(B["orb-NQ-tf15|pre|"]["detail"])["c1"]
    with tempfile.TemporaryDirectory(dir=HERE) as tmp:
        tmp = Path(tmp)
        try:
            _copy_store(J.LB.RUNS / "c1-NQ-tf15", tmp / "a" / "c1-NQ-tf15-seeds3-4", {1: 3, 2: 4})
            _copy_store(J.LB.RUNS / "c1-NQ-tf15", tmp / "a" / "c1-NQ-tf15-long-only", {1: 5, 2: 6}, inputs={"dir": "long"})
            _copy_store(J.LB.RUNS / "c1-NQ-tf15", tmp / "a" / "c1-NQ-tf15-same-ids", {1: 7, 2: 8}, rename=False)
            _copy_store(J.LB.RUNS / "straddle_tight_0830-NQ-tf30-shift", tmp / "a" / "straddle_tight_0830-NQ-tf30-shift-more", {1: 3, 2: 4})
            J.EXTRA_DIRS.append(tmp / "a")
            J.reset()
            c = J.build(orb)["controls"]["c1"]
            assert c["seeds"] == [1, 2, 3, 4, 7, 8] and c["real_replicates"] == 6 and len(c["stores"]) == 3, c      # 5, 6 (long only): not the same control
            assert c["two_seed"] == {"pass": v2["pass"], "lift": v2["lift"], "p_beat": v2["p_beat"]}, (c["two_seed"], v2)
            s = J.build(ev)["controls"]["shift"]
            assert s["seeds"] == [1, 2, 3, 4] and len(s["raw"]) == 4 and s["raw"][:2] == s["raw"][2:], s
            with rule(seeds=2):
                c2 = J.build(orb)["controls"]["c1"]
                assert c2["seeds"] == [1, 2] and "two_seed" not in c2 and same(c2, v2), c2
            # a pool whose extra seeds earn $400 more a trade: random entries now beat the table -> fails (2), was a member -> DEMOTED
            J.EXTRA_DIRS[-1] = tmp / "b"
            _copy_store(J.LB.RUNS / "c1-NQ-tf15", tmp / "b" / "c1-NQ-tf15-rich", {1: 3, 2: 4}, add_net=400.0)
            J.reset()
            j = J.judge(orb, J.YEARS[:1])
            b, y = j["build"], j["pick"]
            assert not b["build_pass"] and b["fail"] == "2" and b["two_seed_pass"] and b["controls"]["c1"]["two_seed"]["pass"], b
            assert y["demoted"] and not y["admit"] and y["verdict"].startswith("DEMOTED") and len(y["survivors"]) == 50, y["verdict"]
            md = J.card_md(J.member(orb, periods=J.YEARS[:1]))
            assert "**DEMOTED: luck not excluded (BUILD test (2) fails" in md and "| 4 (THIN) |" in md
            # the same on the year: a richer 2024 pool -> BUILD still passes, 2024 lift < 0 with every seed, > 0 with the first 2
            J.EXTRA_DIRS[-1] = tmp / "c"
            _copy_store(J.W / "runs_v2" / "c1-NQ-tf15-pre-pick", tmp / "c" / "c1-NQ-tf15-pre-pick-rich", {1: 3, 2: 4}, add_net=400.0)
            J.reset()
            j = J.judge(orb, J.YEARS[:1])
            b, y = j["build"], j["pick"]
            assert b["build_pass"] and not y["t5"] and y["t5_two_seed"] and y["failed"] == ["5"] and y["demoted"] and not y["admit"], y["verdict"]
            assert y["verdict"].startswith("DEMOTED: luck not excluded (2024 test (5) fails") and len(y["survivors"]) == 50
        finally:
            J.EXTRA_DIRS.clear()
            J.reset()
    assert J.build(orb)["controls"]["c1"]["seeds"] == [1, 2]
    return 11, 11, []


@lock(draws=200, seeds=2, strict=True, dedup_year=False, **PIN)
def test_f3_f4_f5_f6():
    """F3: exactly 60 % no longer passes (1). F4: both speed shares. F5: a year is judged on the BUILD variant list.
    F6: every store a year's verdict used is listed and logged, new or re-used."""
    for uid in TO_FAIL_F3:                                  # F3
        b = J.build(J.unit(addr(B[uid])))
        assert b["exact60"] and not b["t1"] and not b["build_pass"] and "1" in b["fail"] and B[uid]["build_pass"], uid
    uid = "donchian_thin-NQ-tf30|nyam|"                     # F5: 63 BUILD variants; out/v2 judged 59 on 2024
    u = J.unit(addr(B[uid]))
    j = J.judge(u, J.YEARS[:1])
    ids = J.table_stats(J.table(J.build_store(u)[0], u))["ids"]
    yst = J.find(J.skey(u["key"], u, "pick"), "pick")[0]
    nets = [float(J.cellx(yst, c, u["sess"], u)["net"].sum()) for c in ids]
    assert j["pick"]["cells"] == j["build"]["cells"] == len(ids) == 63 and P[uid]["cells"] == 59
    assert same(j["pick"]["avg_net"], float(np.mean(nets))) and same(j["pick"]["median_net"], float(np.median(nets)))
    y = judged("E1-A-NQ")["pick"]                           # F6 (+ F4)
    roles = [s["role"] for s in y["stores"]]
    assert roles == ["BUILD menu", "2024 menu", "2024 control shift", "2024 stress", "BUILD stress"], roles
    assert y["stores"][1] == {"role": "2024 menu", "store": "runs_admit_r1/straddle_tight_0830-NQ-tf30-pre-pick", "seeds": [], "origin": "re-used"}
    assert y["stores"][2]["seeds"] == [1, 2] and y["stores"][3]["origin"] == "new" and y["second_look"]
    with tempfile.TemporaryDirectory(dir=HERE) as tmp:
        J.log_reads(y, Path(tmp) / "reads.csv")
        J.log_reads(y, Path(tmp) / "reads.csv")
        rows = list(csv.DictReader((Path(tmp) / "reads.csv").open()))
        assert len(rows) == 2 * len(y["stores"]) and rows[2]["seeds"] == "1 2" and rows[1]["origin"] == "re-used" and rows[0]["verdict"] == "MEMBER"
    x = {"net": np.array([100.0, -30.0, 50.0, -20.0]), "dur_s": np.array([2, 3, 60, 70])}        # F4: 2 fast trades (+100, -30), 2 slow
    f = J.fast_share([x])
    assert f["fast_profit_share"] == round(100 / 150, 4) and f["fast_net_share"] == 0.7 and f["n_fast"] == 2, f
    assert J.fast_share([{"net": np.array([-5.0]), "dur_s": np.array([1])}])["fast_net_share"] is None
    return 6, 6, []


@lock(**NOW)
def test_full_build_table_now():
    """JUDGE_FULL=1: all 1,916 units under the rule in force (first 2 seeds): the BUILD verdicts that differ from out/v2 are
    exactly the 4 new passers (F1), the 6 lucky-seed units (F1) and the 2 units at exactly 60 % (F3); the 14 members stay."""
    _skip_unless_full()
    return _full(TO_PASS, TO_FAIL_F1 + TO_FAIL_F3)


# ================================================================ the EXAM seal (2026): flag + allowed list, nothing else

def test_exam_is_sealed_without_the_flag_and_off_the_allowed_list():
    """EDGE_SPEC "FULL OUT-OF-SAMPLE FOR THE SAVED STRATEGIES": 2026 is judged only with the explicit exam flag AND only for a unit
    on out/exam2026/allowed.json. Both refusals come BEFORE any store is looked at; the engine refuses a 2026 date without
    allow_exam; the 2026 runner refuses a whole job list that holds one job of a unit off the list. No 2026 file is read here."""
    import datetime as dt
    on, off, demoted = "first_bar_mom-NQ-tf15-mid", "orb-NQ-tf15-pre", "straddle_t_1800-NQ-tf30-eve"
    keep_allowed, keep_find, keep_build = J.ALLOWED, J.find, J.build
    tmp = Path(tempfile.mkdtemp(dir=W / "tests"))

    def no_store(*a, **k):
        raise AssertionError("a store was looked at before the EXAM seal answered")

    def refused(fn, word):
        try:
            fn()
        except J.Refuse as e:
            assert word in str(e), str(e)
            return 1
        raise AssertionError(f"not refused ({word})")

    n = 0
    try:
        J.ALLOWED = tmp / "allowed.json"
        J.ALLOWED.write_text(json.dumps({"units": [on], "period": {"start": "2026-01-01", "end": {"NQ": "2026-01-30"}}}))
        J.find = J.build = no_store
        assert J.RULE["exam"] is False                                         # the default rule: sealed
        n += refused(lambda: J.year(J.unit(on), "exam"), "explicit exam flag")           # on the list, no flag
        assert J.main(["year", on, "--period", "exam", "--log", ""]) == 2 and J.RULE["exam"] is False
        with rule(exam=True):
            for a in (off, demoted, on + "@A"):                                 # the flag alone opens nothing off the list
                n += refused(lambda a=a: J.year(J.unit(a), "exam"), "not on the allowed list")
            J.ALLOWED.unlink()                                                  # no list = nothing allowed
            n += refused(lambda: J.year(J.unit(on), "exam"), "does not exist")
        assert J.main(["year", off, "--period", "exam", "--exam", "--log", ""]) == 2      # the command line, same answer
        J.RULE["exam"] = False
        for g in "ABC":                                                         # no flag: no 2026 calendar row
            assert J.event_ords(g).max() < dt.date.fromisoformat(J.EXAM_START).toordinal()
        n += 1
    finally:
        J.ALLOWED, J.find, J.build = keep_allowed, keep_find, keep_build
        J.RULE["exam"] = False
        J._EV.clear()
        J._CAL.clear()
        for f in tmp.glob("*"):
            f.unlink()
        tmp.rmdir()
    # the engine: a 2026 date raises without the exam key, and under the CHECK key (before any tape is opened)
    sys.path.insert(0, str(W / "engine"))
    sys.path.insert(0, str(W / "out" / "exam2026"))
    import l2sim as S
    import run_exam as RX
    for kw in ({}, {"allow_check": True}):
        for call in (lambda kw=kw: S.sessions("2026-01-02", "2026-01-30", "NQ", **kw), lambda kw=kw: S.load_tape("2026-01-05", "NQ", **kw),
                     lambda kw=kw: S.run_many([], "2026-01-02", "2026-01-30", root="NQ", **kw)):
            try:
                call()
                raise AssertionError("the engine read the EXAM period without allow_exam")
            except S.HoldoutSealed:
                n += 1
    # the runner: the allowed list on disk decides; one job off it (or of another period) refuses the whole list before any run
    a = RX.allowed()
    assert a["units"] and all("@" not in k[0] for k in a["menus"])
    good = {"family": "first_bar_mom", "root": "NQ", "tf": "15", "sess": "mid", "period": "exam"}
    RX.guard(good, a)
    RX.guard({"c1": True, "root": "NQ", "tf": "15", "sess": "mid", "period": "exam"}, a)
    for j in ({**good, "family": "orb", "sess": "pre"}, {**good, "family": "straddle_t_1800", "tf": "30", "sess": "eve"}, {**good, "tf": "30"},
              {**good, "root": "ES"}, {**good, "period": "check"}, {"c1": True, "root": "NQ", "tf": "30", "sess": "mid", "period": "exam"}):
        for fn in (lambda j=j: RX.guard(j, a), lambda j=j: RX.run([good, j]), lambda j=j: RX.check([good, j])):
            try:
                fn()
                raise AssertionError(f"the 2026 runner accepted {j}")
            except RX.Sealed:
                n += 1
    RESULTS["test_exam_is_sealed_without_the_flag_and_off_the_allowed_list"] = (n, n, [])


if __name__ == "__main__":
    import time
    tests = [test_catalog_and_unit_types, test_event_days_are_stage_3, test_members_all_six, test_other_build_passers_fail_2024_the_same_way,
             test_sampled_build_failures, test_placebo_one_of_168, test_cards_and_surviving_sets, test_refusals, test_check_path_dry_run_on_2024,
             test_full_build_table_as_v2, test_f1_4000_draws_are_the_checkers, test_f2_every_seed_on_disk, test_f3_f4_f5_f6, test_full_build_table_now,
             test_exam_is_sealed_without_the_flag_and_off_the_allowed_list]
    rc = 0
    for t in tests:
        if t.__name__.startswith("test_full") and not os.environ.get("JUDGE_FULL"):
            print(f"SKIP {t.__name__} (set JUDGE_FULL=1)")
            continue
        t0 = time.monotonic()
        try:
            t()
            ok, n, bad = RESULTS[t.__name__]
            print(f"PASS {t.__name__}: {ok} of {n} reproduce exactly ({time.monotonic() - t0:.0f} s)", flush=True)
        except AssertionError as e:
            rc = 1
            print(f"FAIL {t.__name__} ({time.monotonic() - t0:.0f} s)\n{e}", flush=True)
    sys.exit(rc)
