"""Port group 2 (families/port2.py): ema_ribbon, tema_slope, ema_pullback, supertrend, rsi2, first_bar_mom, tod_drift, mid_fade.

  * the registry entry of each (rationale, complexity, roots, the pre-registered family-parameter variants = the FIRST axis of
    the family's heat-map in R/tune1.jsonl / R/tune2.jsonl, the screen tfs of R/screen.jsonl);
  * the port is the old pilot's code: every method of R/families/<fam>.py `class Fam` is AST-identical in the port, the inputs
    and defaults are the tester draft's;
  * TESTER MATCH on 10 BUILD days (NQ and ES screen runs at tf 1 / 5 / 15 / 30, every NQ heat-map cell on 5 of them): every
    field of every trade. The full-window gate is port2_validate.py -> PORT2_VALIDATION.md;
  * the full-window gate report belongs to the trading code on disk (one hash for every row; every registered variant matched);
  * an INDEPENDENT ORACLE (numpy / plain Python straight from the prints, no Template) of every family's first signal in ALL
    SEVEN sessions on NQ, ES and GC -- entry print, fill, stop and target for the atr, pts and pct stop modes: the paths no
    tester bundle covers (`pre` / `eve`, percent stops, GC); and two broken families the oracle must catch;
  * the facts declared for the Admit / exam stages: tod_drift WEAK, SECOND_LOOK = the old holdout job keys, the cells that
    cannot trade by construction (can_trade), the pre-declared per-direction plateau sets of tod_drift;
  * the same trades at 1 and at W (8) worker processes, over the menu's shape (variants x exit cells x sess all / pre / eve);
  * NO LOOK-AHEAD: all data after a cut time replaced by garbage (and: removed) -> every earlier decision and trade unchanged;
  * the counts-only smoke on ES and GC.
Only identity and counts are asserted: no P&L is looked at, nothing after 2023-12-31 is read (bundle rows are filtered to the
test days before anything else touches them). L2_TEST_WORKERS (default 8) caps the worker count of the parity test; it is
also lowered by itself when the machine is busy (run_menus.auto_workers)."""
import ast
import datetime as dt
import importlib.util
import json
import os
import warnings
from collections import Counter

import numpy as np
import pytest

import edge_validate as EV
import families
import l2sim as S
import library
import port2_validate as PV
import run_menus as RM
import sim_validate as V
from families import port2

NAMES = ("ema_ribbon", "tema_slope", "ema_pullback", "supertrend", "rsi2", "first_bar_mom", "tod_drift", "mid_fade")
# <= 8 worker processes machine-wide for this project: never more than the idle cores (other research jobs share the machine)
W = max(2, min(int(os.environ.get("L2_TEST_WORKERS", "8")), S.MAX_WORKERS, RM.auto_workers()))
COMPLEXITY = {"ema_ribbon": 4, "tema_slope": 2, "ema_pullback": 4, "supertrend": 3, "rsi2": 3, "first_bar_mom": 3, "tod_drift": 5,
              "mid_fade": 3}
DAYS10 = ["2023-03-06", "2023-03-07", "2023-03-08", "2023-03-09", "2023-03-10", "2023-03-13", "2023-03-14", "2023-03-15",
          "2023-03-16", "2023-03-17"]                                    # 10 BUILD sessions; every family trades in them
DAYS8 = [d for d in RM.SMOKE_DAYS if d < "2023-10"][:8]                  # early sample, a roll day, half days, an FOMC day
EXITS = [{"stop_mode": "atr", "stop_val": 1.5, "tgt_r": 2.0}, {"stop_mode": "pts", "stop_val": 20.0, "tgt_r": 0.0},
         {"stop_mode": "pct", "stop_val": 0.10, "tgt_r": 1.0}]            # three cells of the menu: one per stop mode


def guard():
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")


def r_module(fam):
    spec = importlib.util.spec_from_file_location(f"r_fam_{fam}", S.R / "families" / f"{fam}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def tune_axes(fam) -> list:
    """The axes of every heat-map of the family in R/tune1.jsonl + R/tune2.jsonl, in file order."""
    out = []
    for fn in ("tune1.jsonl", "tune2.jsonl"):
        for line in (S.R / fn).read_text().splitlines():
            j = json.loads(line)
            if j.get("strategy") == f"draft_pp_{fam}":
                out.append(j["axes"])
    return out


# ---- the registry ---------------------------------------------------------------------------------------------------------

def test_the_eight_families_are_registered_as_edge_library_families():
    assert tuple(port2.FAMILIES) == NAMES
    assert not {k: v for k, v in families.ERRORS.items() if k == "port2" or k in NAMES or "port2.py" in v}
    for name in NAMES:
        entry = port2.FAMILIES[name]
        assert families.check_entry(name, entry) == [] and families.MODULE_OF[name] == "port2"
        cls, inputs, both, notes = families.REGISTRY[name]
        lib = families.library(name)
        assert inputs == {} and both is False and cls.FEATURES == () and cls.session_independent is True
        assert lib["roots"] == ("NQ", "ES", "GC") and lib["l2"] is False and lib["ported"] == name
        # WEAK RATIONALE (t >= 3 on BUILD): tod_drift by its author ("control for pure clock effects"); ema_ribbon, tema_slope,
        # ema_pullback, supertrend by EDGE_SPEC "ORCHESTRATOR DECISIONS 2026-10-03" 4 (the rationale only restates the trigger),
        # laid over the registry by families.load()
        assert lib["weak"] is (name in ("tod_drift", "ema_ribbon", "tema_slope", "ema_pullback", "supertrend")), name
        assert port2.FAMILIES[name][4].get("weak", False) is (name == "tod_drift")       # the author's own entry is untouched
        assert lib["complexity"] == COMPLEXITY[name], name               # counted before any run; pinned (it breaks ties)
        # the rationale is the hypothesis sentence of the old family's docstring (written before the old screen ran)
        doc = " ".join(r_module(name).__doc__.split())
        head = lib["rationale"].split(";")[0].split("(")[0].strip().rstrip(".")
        assert len(lib["rationale"]) >= 60 and head[1:] in doc, (name, head)
        assert families.features_for(name) is None                       # no Level-2 column is loaded for a port
        for root in lib["roots"]:
            for tf in cls.SCREEN_TFS:
                grid = families.unit_grid(name, root, tf)
                assert len(grid) == 32 * len(lib["variants"]) and len({c["id"] for c in grid}) == len(grid)
    assert families.library("first_bar_mom")["penalty"] and "2025-26" in families.library("first_bar_mom")["penalty"]
    assert all(families.library(n)["penalty"] is None for n in NAMES if n != "first_bar_mom")
    # families whose 2025-26 was already read by the old pilots (R / RE jobs.jsonl, stage holdout): labelled in the notes
    seen = set()
    for d, pre in ((S.R, "draft_pp_"), (S.RE, "draft_pp_es_")):
        for line in (d / "jobs.jsonl").read_text().splitlines():
            j = json.loads(line)
            if j.get("stage") == "holdout" and j.get("strategy", "").startswith(pre):
                seen.add(j["strategy"][len(pre):].removeprefix("es_"))
    for name in NAMES:
        assert ("SECOND look" in families.REGISTRY[name][3]) == (name in seen), name
    assert "WEAK RATIONALE" in families.REGISTRY["tod_drift"][3] and "control for pure clock effects" in r_module("tod_drift").__doc__


def test_second_look_table_is_exactly_the_old_holdout_job_keys():
    """EDGE_SPEC user rule 3 ("must be labelled"): port2.SECOND_LOOK = family -> root -> tfs of the `holdout`-stage jobs in
    the old pilots' job lists. Job KEYS only are read here: no holdout bundle, no result."""
    seen = {}
    for root, (d, pre) in PV.PILOTS.items():
        for line in (d / "jobs.jsonl").read_text().splitlines():
            j = json.loads(line)
            fam = j.get("strategy", "")[len(pre):] if j.get("strategy", "").startswith(pre) else None
            if j.get("stage") != "holdout" or fam not in NAMES:
                continue
            head, tf = j["key"].rsplit("-", 2)[0], j["key"].rsplit("-", 2)[1]
            assert head == f"ho-{fam}" and tf.startswith("tf"), j["key"]
            seen.setdefault(fam, {}).setdefault(root, set()).add(tf[2:])
    assert {f: {r: set(t) for r, t in v.items()} for f, v in port2.SECOND_LOOK.items()} == seen
    assert set(port2.SECOND_LOOK) == {"tema_slope", "ema_pullback", "rsi2", "first_bar_mom", "tod_drift"}
    for name in NAMES:
        label = port2.second_look(name)
        assert (label is None) == (name not in seen)
        if label:
            assert label.startswith("SECOND LOOK") and all(root in label for root in seen[name])
    assert "NQ tf 5 / 15 / 30; ES tf 5 / 15" in port2.second_look("tod_drift")


# 2026-10-08: settings added for the pipeline's cards. At their defaults the family is the old rule (the gate and the oracle
# say so); other values are checked by the oracle only, the old tester drafts have no such input.
NEW_SETTING = {"ema_ribbon": ("slow", (34, 55, 89)), "ema_pullback": ("n", (10, 20, 30)), "supertrend": ("mult", (2.0, 3.0, 4.0))}
CHANGED_BY_SETTING = {"ema_ribbon": {"SPANS", "fam_update"}, "ema_pullback": {"SPANS", "fam_signal"}, "supertrend": {"fam_update"}}


def test_variants_are_the_first_axis_of_the_old_heat_maps():
    """EDGE_SPEC 'PROPER RE-RUN' 4: the values of the FIRST axis of the family's heat-map in R/tune1.jsonl / tune2.jsonl;
    first axis max_tr or no grid -> defaults only; tod_drift = off_min x dir."""
    for name in NAMES:
        got, grids = families.library(name)["variants"], tune_axes(name)
        firsts = {(g[0]["key"], tuple(g[0]["values"])) for g in grids}
        assert len(firsts) <= 1, (name, firsts)                           # every heat-map of the family has the same first axis
        if not grids or next(iter(firsts))[0] == "max_tr":
            assert got == [{}], name
        elif name == "tod_drift":
            (key, vals), = firsts
            dirs = {tuple(a["values"]) for g in grids for a in g if a["key"] == "dir"}
            assert key == "off_min" and dirs == {("long", "short")}
            assert got == [{"off_min": m, "dir": d} for m in vals for d in ("long", "short")] and len(got) == 8
        else:
            (key, vals), = firsts
            assert got == [{key: v} for v in vals], name
    assert {n: len(families.library(n)["variants"]) for n in NAMES} == {
        "ema_ribbon": 1, "tema_slope": 3, "ema_pullback": 1, "supertrend": 1, "rsi2": 3, "first_bar_mom": 3, "tod_drift": 8, "mid_fade": 1}
    assert [v["n"] for v in families.library("tema_slope")["variants"]] == [10, 20, 40]
    assert [v["th"] for v in families.library("rsi2")["variants"]] == [5.0, 10.0, 15.0]
    assert [v["k"] for v in families.library("first_bar_mom")["variants"]] == [1.0, 1.5, 2.0]


def test_screen_tfs_are_those_of_the_old_screen():
    ran = {}
    for line in (S.R / "screen.jsonl").read_text().splitlines():
        j = json.loads(line)
        ran.setdefault(j["strategy"], []).append(j["inputs"]["tf"])
    for name in NAMES:
        assert tuple(ran[f"draft_pp_{name}"]) == families.REGISTRY[name][0].SCREEN_TFS == ("1", "5", "15", "30")


# ---- the port is the old code -----------------------------------------------------------------------------------------------

def _members(cls_node) -> dict:
    out = {}
    for n in cls_node.body:
        if isinstance(n, ast.FunctionDef):
            out[n.name] = ast.dump(n)
        elif isinstance(n, ast.Assign):
            out[n.targets[0].id] = ast.dump(n.value)
    return out


def test_every_method_of_the_old_family_is_ast_identical_in_the_port():
    tree = ast.parse((S.L / "families" / "port2.py").read_text())
    ported = {n.name: _members(n) for n in tree.body if isinstance(n, ast.ClassDef)}
    for name in NAMES:
        old = ast.parse((S.R / "families" / f"{name}.py").read_text())
        fam = _members(next(n for n in old.body if isinstance(n, ast.ClassDef) and n.name == "Fam"))
        new = ported[families.REGISTRY[name][0].__name__]
        skip = CHANGED_BY_SETTING.get(name, set())
        assert fam and all(new.get(k) == v for k, v in fam.items() if k not in skip), (name, [k for k, v in fam.items() if new.get(k) != v])
        assert set(new) - set(fam) <= {"DEFAULTS", "SCHEMA", "SCREEN_TFS", "FEATURES", "spans_used"}, name      # nothing else was added
    assert port2.SESS is S.SESS and port2._hms is S._hms                  # the names the old bodies read as module globals


def test_inputs_and_defaults_are_the_tester_drafts():
    kinds = {"int": int, "float": float, "bool": bool}
    for name in NAMES:
        cls, m = families.REGISTRY[name][0], r_module(name)
        d, sch = cls.defaults(), cls.schema()
        for key, _label, kind, default, lo, hi, _step in m.INPUTS:
            assert d[key] == default and type(d[key]) is kinds[kind], (name, key)
            assert sch[key][0] == kind and (kind == "bool" or tuple(sch[key][1:3]) == (lo, hi)), (name, key)
        for key, ov in getattr(m, "OVERRIDES", {}).items():
            assert d[key] == ov["default"], (name, key)
            if "choices" in ov:
                assert sch[key] == ("choice", tuple(ov["choices"]))
        own = {k for c in cls.__mro__ if c not in S.Template.__mro__ for k in c.__dict__.get("DEFAULTS", {})}
        extra = {NEW_SETTING[name][0]} if name in NEW_SETTING else set()
        assert own == {i[0] for i in m.INPUTS} | set(getattr(m, "OVERRIDES", {})) | extra, name
        # ... and the tester's own resolved inputs of the screen run (run.json: no trade is read)
        for key, fam, kind, tid in PV.bundles("NQ", [name]):
            if kind == "run":
                ref = json.loads((EV.RUNS / tid / "run.json").read_text())["inputs"]
                mine = cls({"tf": ref["tf"]}).p
                assert {k: mine[k] for k in ref} == ref, (name, key)
    with pytest.raises(ValueError):
        port2.TodDrift({"dir": "both"})                                  # pp_tod_drift: long | short only
    assert port2.TodDrift({}).p["max_tr"] == 1 and port2.TodDrift({}).p["exit_bars"] == 6 and port2.TodDrift({}).p["tgt_r"] == 0.0


# ---- tester match (identity only) ----------------------------------------------------------------------------------------------

def test_the_gate_reads_in_sample_stages_only():
    for root, n_runs, n_grids in (("NQ", 32, 16), ("ES", 32, 13)):
        items = PV.bundles(root)
        assert sum(k == "run" for _, _, k, _ in items) == n_runs and sum(k == "grid" for _, _, k, _ in items) == n_grids
        keys = [key for key, _, _, _ in items]
        assert all(k.startswith(("screen-", "hm-", "hm2-", "fp-")) for k in keys) and not any(k.startswith(("ho-", "wf-")) for k in keys)
        assert {f for _, f, _, _ in items} == set(NAMES)
        for key, fam, kind, tid in items:
            meta = json.loads(((EV.RUNS / tid / "run.json") if kind == "run" else (V.GRIDS / tid / "grid.json")).read_text())
            assert meta["range"]["end"] == "2024-12-31" and not meta["range"].get("holdout"), key
            assert (meta["strategy"]["id"] if kind == "run" else meta["strategy"]) == ("draft_pp_" if root == "NQ" else "draft_pp_es_") + fam


@pytest.mark.parametrize("root", ["NQ", "ES"])
def test_port_reproduces_the_tester_screen_runs_on_ten_build_days(root):
    guard()
    keep = set(DAYS10)
    rows = PV.load(root, [b for b in PV.bundles(root) if b[2] == "run"])
    assert len(rows) == 32
    for r in rows:
        r["ref"] = [t for t in r["ref"] if t["date"] in keep]             # only the test days ever leave the loader
    try:
        res = S.run_many([(PV.FAMS[r["family"]], r["inputs"]) for r in rows], days=DAYS10, root=root, workers=1)
    except FileNotFoundError as e:
        pytest.skip(f"tape cache not available: {e}")
    n = {}
    for r, x in zip(rows, res):
        c = V.compare(x["trades"], r["ref"])
        assert c["n_sim"] == c["n_ref"] == c["matched"] == c["exact_all_fields"], (root, r["key"], c["n_ref"], c["n_sim"], c["matched"])
        assert c["net_diff"] == 0.0 and x["skipped_by_error"] == 0 and x["both_sides_sessions"] == 0 and x["sessions"] == 10
        assert not any(t["oco"] or t["both_sides"] or t["order_price"] is not None for t in x["trades"])      # market entries only
        n[r["family"]] = n.get(r["family"], 0) + c["n_ref"]
    assert set(n) == set(NAMES) and all(v > 0 for v in n.values()), n      # every family is really compared


def test_port_reproduces_every_nq_heat_map_cell_on_five_build_days():
    guard()
    days = DAYS10[:5]
    keep = set(days)
    rows = PV.load("NQ", [b for b in PV.bundles("NQ") if b[2] == "grid"])
    assert len(rows) == 412
    assert {r["inputs"]["stop_mode"] for r in rows} == {"atr", "pts"} and {r["inputs"]["max_tr"] for r in rows} == {1, 3}
    res = S.run_many([(PV.FAMS[r["family"]], r["inputs"]) for r in rows], days=days, workers=1)
    total = 0
    for r, x in zip(rows, res):
        ref = [t for t in r["ref"] if t["date"] in keep]
        c = V.compare(x["trades"], ref)
        assert c["n_sim"] == c["n_ref"] == c["exact_all_fields"] and c["net_diff"] == 0.0, (r["key"], r["cell"], c["n_ref"], c["n_sim"])
        assert x["skipped_by_error"] == 0
        total += c["n_ref"]
    assert total > 5000


# ---- 1 worker = W workers, over the menu's shape -----------------------------------------------------------------------------

def menu_specs(name, exits=EXITS, tfs=None) -> list:
    """Every registered variant x `exits` x the three instances of the OLD exit convention (sess all / pre / eve: the
    tester-matched layout these port tests pin; run_menus now runs seven with hold_to day: tests/test_edge_hold.py), every tf."""
    cls = families.REGISTRY[name][0]
    out = []
    for tf in tfs or cls.SCREEN_TFS:
        for cell in S.menu_grid(cls, families.unit_inputs(name, tf), "NQ", families.library(name)["variants"], exits):
            out += RM.cell_specs(cell, "session")
    return out


@pytest.mark.parametrize("name", NAMES)
def test_port_gives_identical_trades_at_1_and_8_workers(name):
    guard()
    specs = menu_specs(name)
    assert len(specs) == 4 * len(families.library(name)["variants"]) * len(EXITS) * 3
    a = S.run_many(specs, days=DAYS8, workers=1)
    b = S.run_many(specs, days=DAYS8, workers=W)
    assert a[0]["meta"]["workers"] == 1 and b[0]["meta"]["workers"] == min(W, S.MAX_WORKERS, len(DAYS8))
    n = 0
    for (cls, p), x, y in zip(specs, a, b):
        assert x["trades"] == y["trades"], (name, p)                      # every field of every trade, in order
        assert x["skipped_by_error"] == y["skipped_by_error"] == 0, (name, p, x["no_trade"][:1])
        assert x["sessions"] == y["sessions"] == len(DAYS8) and x["both_sides_sessions"] == y["both_sides_sessions"] == 0
        assert x["skipped"] == y["skipped"] and x["eve_skipped"] == y["eve_skipped"]
        want = {"all": set(S.ORDER), "pre": {"pre"}, "eve": {"eve"}}[p["sess"]]
        assert {S.session_of(t["entry_ms"]) for t in x["trades"]} <= want, (name, p)     # an instance trades its own sessions only
        n += len(x["trades"])
    assert n > 0


# ---- no look-ahead ------------------------------------------------------------------------------------------------------------

LA_DAY = dt.date(2023, 3, 16)                    # a BUILD day on which every family trades
DAY_CUTS = ("01:30:17", "04:10:40", "09:47:20", "11:07:30", "14:20:10")
EVE_CUTS = ("19:10:30", "21:40:05")              # on the evening before LA_DAY
ENTRY = ("entry_ns", "side", "qty", "entry_price", "order_price", "sl", "tp")


@pytest.fixture(scope="module")
def la():
    guard()
    tape = S.load_tape(LA_DAY)
    if tape is None:
        pytest.skip("tape cache not available")
    daily = [r for r in S.load_daily("NQ") if r["date"] < LA_DAY.isoformat()]
    return tape, daily


def garbage(tape, cut_ns: int, seed: int):
    """The same tape with EVERY print at / after the cut replaced: prices on a random walk 300 points away, random sizes."""
    i = int(np.searchsorted(tape.ts, cut_ns, side="left"))
    rng = np.random.default_rng(seed)
    px, size = tape.px.copy(), tape.size.copy()
    px[i:] = np.round((px[i - 1] + 300.0 + np.cumsum(rng.integers(-60, 61, len(px) - i)) * 0.25) * 4) / 4
    size[i:] = rng.integers(1, 500, len(px) - i)
    return S.Tape(tape.root, tape.date, tape.contract, tape.ts, px, size, daily=tape.daily), i


def cut_off(tape, i: int):
    """The same tape with nothing at / after the cut."""
    return S.Tape(tape.root, tape.date, tape.contract, tape.ts[:i], tape.px[:i], tape.size[:i], daily=tape.daily)


def play(cls, params, tape, daily) -> list:
    st = cls(params)
    return S.run_session(st, tape, daily=daily, on_error="raise", segment="eve" if params["sess"] == "eve" else "day").trades


def la_check(specs, tape, daily, tag) -> tuple:
    """Every print after a cut replaced by garbage (and, second, removed): the trades closed before the cut must be identical
    in every field and every entry filled before the cut must be the same entry (time, side, fill, stop, target); else
    AssertionError. -> (trades closed before a cut, positions open across a cut, runs the garbage changed later on)."""
    eve0 = LA_DAY - dt.timedelta(days=1)
    cuts = [("day", S.et_ns(LA_DAY, c)) for c in DAY_CUTS] + [("eve", S.et_ns(eve0, c)) for c in EVE_CUTS]
    real = [play(cls, p, tape, daily) for cls, p in specs]
    changed = held = closed = 0
    for k, (seg, cut) in enumerate(cuts):
        fake, i = garbage(tape, cut, seed=k + 1)
        short = cut_off(tape, i)
        assert 0 < i < len(tape.ts) and (fake.px[:i] == tape.px[:i]).all() and (fake.px[i:] != tape.px[i:]).mean() > 0.99
        for (cls, p), base in zip(specs, real):
            if (p["sess"] == "eve") != (seg == "eve"):
                continue
            g, s = play(cls, p, fake, daily), play(cls, p, short, daily)
            done = [t for t in base if t["exit_ns"] < cut]
            assert [t for t in g if t["exit_ns"] < cut] == done, (tag, p, seg, k)
            assert s[:len(done)] == done, (tag, p, seg, k)
            ent = [tuple(t[f] for f in ENTRY) for t in base if t["entry_ns"] < cut]
            assert [tuple(t[f] for f in ENTRY) for t in g if t["entry_ns"] < cut] == ent, (tag, p, seg, k)
            assert [tuple(t[f] for f in ENTRY) for t in s if t["entry_ns"] < cut] == ent, (tag, p, seg, k)
            closed += len(done)
            held += len(ent) - len(done)
            changed += g != base
    return closed, held, changed


@pytest.mark.parametrize("name", NAMES)
def test_no_look_ahead_garbage_after_a_cut_changes_no_earlier_decision_or_trade(name, la):
    """Covers the bar-close decisions, the clock-time decisions (tod_drift: fam_time; mid_fade: the 09:30 -> 11:00 move) and
    the two new sessions, for every registered variant at every tf, on two exit cells."""
    tape, daily = la
    closed, held, changed = la_check(menu_specs(name, exits=EXITS[:2]), tape, daily, name)
    assert closed > 0 and changed > 0             # the test has teeth: trades exist before the cuts, and the garbage did move later ones
    if name != "mid_fade":
        assert held > 0                           # ... and positions were open across a cut (their entries stayed the same)


class Peek(S.Template):
    """BROKEN ON PURPOSE (never registered): reads the tape 20 minutes AHEAD of the decision through the simulator's state."""

    def fam_signal(self, ctx):
        s = ctx._s
        j = min(int(np.searchsorted(s.ts, ctx.now_ns + 20 * S.MIN_NS)), len(s.px) - 1)
        self._mkt(ctx, "long" if s.px[j] > self.C[-1] else "short")


def test_the_look_ahead_check_catches_a_family_that_peeks(la):
    tape, daily = la
    base = {"tf": "1", "stop_mode": "pts", "stop_val": 5.0, "tgt_r": 1.0, "max_tr": 20}
    with pytest.raises(AssertionError):
        la_check([(Peek, {**base, "sess": s}) for s in RM.SESS_PASSES], tape, daily, "peek")
    closed, held, changed = la_check([(port2.Rsi2, {**base, "sess": s, "th": 15.0}) for s in RM.SESS_PASSES], tape, daily, "rsi2")
    assert closed > 50 and changed > 0            # the same shape without the peek passes, on many trades


def test_clock_time_decisions_read_only_what_is_before_them(la):
    """tod_drift enters at session start + off_min on the last print BEFORE that time; mid_fade decides at the first tf close of
    mid from the 09:30 open and the last 1-minute close before 11:00. Garbage from the decision time on must not move the
    decision: the entry is the same order (side, reference stop / target distance), only its fill print differs."""
    tape, daily = la
    for off, tf in ((0, "5"), (15, "5"), (30, "15"), (60, "30")):
        p = {"tf": tf, "sess": "all", "off_min": off, "dir": "short", "stop_mode": "pts", "stop_val": 20.0, "tgt_r": 1.0}
        base = play(port2.TodDrift, p, tape, daily)
        mins = sorted((t["entry_ns"] - S.et_ns(LA_DAY, "00:00")) // S.NS // 60 for t in base)
        want = [S.SESS[s][0] // 60 + off for s in S.ORDER if not (s == "asia" and off * 60 < 3 * int(tf) * 60)]
        assert mins == want and all(t["side"] == "short" for t in base), (off, tf, mins)       # one per session, at its clock time
        for s in S.ORDER:
            at = S.et_ns(LA_DAY, "00:00") + (S.SESS[s][0] + off * 60) * S.NS
            fake, i = garbage(tape, at, seed=7)
            g = play(port2.TodDrift, p, fake, daily)
            a = [t for t in base if t["entry_ns"] >= at][:1]
            b = [t for t in g if t["entry_ns"] >= at][:1]
            assert len(a) == len(b) and [t for t in g if t["entry_ns"] < at] == [t for t in base if t["exit_ns"] < at]
            if a:                                                         # same decision; the fill is the (garbage) next print
                assert a[0]["side"] == b[0]["side"] and b[0]["entry_price"] != a[0]["entry_price"]
                assert round(abs(b[0]["entry_price"] - b[0]["sl"]), 6) == round(abs(a[0]["entry_price"] - a[0]["sl"]), 6) == 20.0
    for tf in ("1", "5", "15", "30"):
        p = {"tf": tf, "sess": "all", "k": 0.0}                           # k = 0: the fade fires whenever the AM move is not zero
        base = play(port2.MidFade, p, tape, daily)
        assert len(base) == 1 and S.session_of(base[0]["entry_ms"]) == "mid"
        fake, i = garbage(tape, S.et_ns(LA_DAY, "11:00"), seed=11)        # the 11:00 -> first-tf-close bar is garbage too
        g = play(port2.MidFade, p, fake, daily)
        assert len(g) == 1 and g[0]["side"] == base[0]["side"] and g[0]["entry_ms"] // 60000 == base[0]["entry_ms"] // 60000
        am = [m for m in S.build_bars(tape.ts, tape.px, tape.size, 0, len(tape.ts), S.et_ns(LA_DAY, "09:30"), S.et_ns(LA_DAY, "11:00"), 1)]
        assert base[0]["side"] == ("short" if am[-1].c > am[0].o else "long")      # the fade of the 09:30 open -> 11:00 close move


# ---- structure the registry docstring states ---------------------------------------------------------------------------------

def test_mid_fade_trades_mid_only_and_its_new_session_instances_never_trade():
    guard()
    specs = [(port2.MidFade, {"tf": tf, "sess": s, "k": 0.0}) for tf in ("1", "5", "15", "30") for s in RM.SESS_PASSES]
    res = S.run_many(specs, days=DAYS10, workers=1)
    for (cls, p), x in zip(specs, res):
        assert x["skipped_by_error"] == 0
        if p["sess"] == "all":
            assert len(x["trades"]) == 10 and {S.session_of(t["entry_ms"]) for t in x["trades"]} == {"mid"}      # one per day
            assert len({t["date"] for t in x["trades"]}) == 10
        else:
            assert x["trades"] == [] and port2.MidFade(p).sessions() == []


def test_smoke_on_es_and_gc_counts_only():
    guard()
    for name, root in (("mid_fade", "GC"), ("ema_ribbon", "ES"), ("first_bar_mom", "GC")):
        try:
            out = RM.smoke(name, root, tf="5", n_days=3, workers=1)
        except FileNotFoundError as e:
            pytest.skip(f"tape cache not available: {e}")
        assert out["ok"] and out["skipped_by_error"] == 0 and out["worker_parity"] and out["both_sides_ok"]
        assert out["cells"] == 32 * len(families.library(name)["variants"]) and out["days"] == 3 and out["nulls"] == {}
        assert out["entry_kind"]["resting"] == 0 and out["trades_total"] == out["long"] + out["short"]
        assert not any(k in json.dumps(out) for k in ("net", "gross", "pnl", "win"))          # counts only
        if name == "mid_fade":
            assert set(out["by_session"]) <= {"mid"}


# ---- the full-window gate report belongs to the code on disk ------------------------------------------------------------------

def test_the_full_window_gate_report_is_a_pass_for_the_trading_code_on_disk():
    """PORT2_VALIDATION.md / out/port2_validation.json: every row of the report was computed under ONE version of
    families/port2.py + l2sim.py (hashes read before each pass and checked after it), and that version's TRADING code
    (PV.code_sha: classes + registered default inputs) is the code on disk. A later edit of registry metadata or a
    docstring changes the file hash only: a warning, not a failure (it cannot change a trade)."""
    p = S.L / "out" / "port2_validation.json"
    assert p.exists(), "run `python port2_validate.py --fresh` (the tester-match gate of port group 2)"
    out = json.loads(p.read_text())
    assert out["pass"] is True and out["variants_pass"] is True and out["range"] == [V.START, V.END] and out["roots"] == ["NQ", "ES"]
    assert out["sha"] == out["sha_end"], "a file changed while the gate ran"
    stamp = out["sha"]["families/port2.py"] + out["sha"]["l2sim.py"]
    assert out["row_stamps"] == [stamp] and all(r.get("sha", stamp) == stamp for r in out["rows"])       # one version for EVERY row
    assert out["code_sha"] == PV.code_sha(), "the trading code of families/port2.py changed: re-run `port2_validate.py --fresh`"
    now = PV.shas()
    for f in ("families/port2.py", "l2sim.py", "sim_validate.py", "edge_validate.py"):
        if out["sha"][f] != now[f]:
            warnings.warn(f"{f} changed since the port2 gate ran (the trading code of port2.py did not): re-run port2_validate.py"
                          + (" and edge_validate.py" if f == "l2sim.py" else ""))
    rows = out["rows"]
    assert len(rows) == 93 and {r["family"] for r in rows} == set(NAMES)
    for root, n_runs, n_cells in (("NQ", 32, 412), ("ES", 32, 300)):
        xs = [r for r in rows if r["root"] == root]
        assert sum(r["kind"] == "run" for r in xs) == n_runs and sum(r["cells"] for r in xs if r["kind"] == "grid") == n_cells
        assert [(r["family"], r["key"]) for r in xs if r["kind"] == "run"] == [(f, f"screen-{f}-tf{tf}") for f in NAMES
                                                                              for tf in ("1", "5", "15", "30")]
    for r in rows:                                                       # 100 %: every field of every trade, no dropped session
        assert r["pass"] and r["cells_identical"] == r["cells"] and r["n_sim"] == r["n_ref"] == r["exact_all_fields"] > 0, r["key"]
        assert r["max_abs_net_diff"] == 0.0 and r["skips_equal"] and r["skipped_by_error"] == 0 and r["both_sides_sessions"] == 0, r["key"]
        assert not any(k in r for k in ("net", "pnl", "gross"))          # identity only: the report holds no result
    for name in NAMES:                                                   # every REGISTERED variant is one the tester ran
        vs = out["variants"][name]
        assert [v["variant"] for v in vs] == families.library(name)["variants"], name
        assert all(v["cells"] >= 1 and v["identical"] == v["cells"] and v["trades"] > 0 for v in vs), name


def test_the_code_hash_ignores_metadata_and_catches_a_trigger_change(tmp_path):
    src = (S.L / "families" / "port2.py").read_text()
    base = PV.code_sha()

    def sha_of(text):
        f = tmp_path / "x.py"
        f.write_text(text)
        return PV.code_sha(f)

    assert sha_of(src) == base
    for old, new in (('"ported": "tod_drift"', '"ported": "tod_drift", "penalty": "x"'), ('"complexity": 5,', '"complexity": 6,'),
                     ('"ported": "rsi2"', '"ported": "rsi2", "weak": True'), ("KNOWN, STRUCTURAL", "KNOWN STRUCTURE"),
                     ('"""EMA ribbon. Hypothesis', '"""EMA ribbon!! Hypothesis')):
        assert old in src and sha_of(src.replace(old, new)) == base, old              # metadata / docstrings: the same code
    for old, new in (("if r < th and", "if r <= th and"), ("if self.sn != 1 or not self.atr_p", "if self.sn != 2 or not self.atr_p"),
                     ("self.al = 1 if a > b > c", "self.al = 1 if a >= b > c"), ("- m * self.sa, (h + l)", "- 2 * self.sa, (h + l)"),
                     ('self._mkt(ctx, "short" if mv > 0 else "long")', 'self._mkt(ctx, "long" if mv > 0 else "short")'),
                     ("self._mkt(ctx, self.p[\"dir\"], ref=lp)", "self._mkt(ctx, self.p[\"dir\"])")):
        assert src.count(old) == 1 and sha_of(src.replace(old, new)) != base, old     # one token of a trigger: another code
    assert PV.variant_of("tod_drift", {"off_min": 15, "dir": "short", "exit_bars": 6, "max_tr": 1}) == "dirshort_off_min15"
    assert PV.variant_of("tod_drift", {"off_min": 15, "dir": "short", "exit_bars": 12}) is None      # not the registered family
    assert PV.variant_of("rsi2", {"th": 7.0}) is None and PV.variant_of("ema_ribbon", {"max_tr": 1, "stop_val": 3.0}) == "default"


# ---- structure declared for the Admit stage: the cells that cannot trade, the mirror ----------------------------------------------

def test_can_trade_is_the_structural_list_of_the_module_docstring():
    """port2.can_trade(family, variant, tf, session): False = zero trades by construction. The whole list, spelled out."""
    never = set()
    for name in NAMES:
        for tf in ("1", "5", "15", "30"):
            for s in S.ORDER7:
                ok = [port2.can_trade(name, v, tf, s) for v in families.library(name)["variants"]]
                if name != "tod_drift":
                    assert len(set(ok)) == 1, (name, tf, s)              # a parameter never opens or closes a session ...
                    if not ok[0]:
                        never.add((name, tf, s))
    want = {("first_bar_mom", tf, s) for tf in ("1", "5", "15", "30") for s in ("eve", "asia")}
    want |= {("mid_fade", tf, s) for tf in ("1", "5", "15", "30") for s in S.ORDER7 if s != "mid"}
    want |= {("ema_pullback", "15", "asia")} | {("ema_pullback", "30", s) for s in ("eve", "asia", "london", "pre")}
    want |= {(f, "30", "asia") for f in ("ema_ribbon", "supertrend", "tema_slope")}
    assert never == want
    # ... except tod_drift's clock offset: per (tf, session) the off_min values that can trade (both directions alike)
    offs = {(tf, s): sorted({v["off_min"] for v in families.library("tod_drift")["variants"] if port2.can_trade("tod_drift", v, tf, s)})
            for tf in ("1", "5", "15", "30") for s in S.ORDER7}
    for tf in ("1", "5", "15", "30"):
        for s in ("london", "nyam", "mid", "pm"):
            assert offs[(tf, s)] == [0, 15, 30, 60]
        assert offs[(tf, "pre")] == [0, 15, 30]                           # 08:25 + 60 min = the no-entry line
        for s in ("eve", "asia"):                                         # 3 tf bars since the 18:00 / 00:00 restart
            assert offs[(tf, s)] == {"1": [15, 30, 60], "5": [15, 30, 60], "15": [60], "30": []}[tf]
    for v in families.library("tod_drift")["variants"]:                   # the two directions of an offset: the same answer
        twin = {**v, "dir": "short" if v["dir"] == "long" else "long"}
        assert all(port2.can_trade("tod_drift", v, tf, s) == port2.can_trade("tod_drift", twin, tf, s)
                   for tf in ("1", "5", "15", "30") for s in S.ORDER7)


def test_a_cell_that_cannot_trade_never_trades_and_tod_drift_trades_wherever_it_can():
    """Counts only, 10 fixed BUILD days: no trade in any (variant, tf, session) that can_trade rules out; tod_drift (a clock
    entry, no trigger) trades on every full day in every cell it can; its long and short twins enter on the SAME prints."""
    guard()
    days = [d for d in RM.SMOKE_DAYS if d < "2024"]
    x = {"stop_mode": "pts", "stop_val": 20.0, "tgt_r": 1.0}
    specs, tags = [], []
    for name in NAMES:
        for tf in ("1", "5", "15", "30"):
            for vi, v in enumerate(families.library(name)["variants"]):
                for inst in RM.SESS_PASSES:
                    specs.append((families.REGISTRY[name][0], {**v, **x, "tf": tf, "sess": inst}))
                    tags.append((name, tf, vi))
    res = S.run_many(specs, days=days, workers=1)
    n, ents = Counter(), {}
    for (name, tf, vi), r in zip(tags, res):
        assert r["skipped_by_error"] == 0, (name, tf, r["no_trade"][:1])
        for t in r["trades"]:
            sess = S.session_of(t["entry_ms"])
            n[(name, tf, vi, sess)] += 1
            if name == "tod_drift":
                ents.setdefault((tf, vi, sess), []).append((t["date"], t["entry_ms"], t["side"]))
    half = {"2022-11-25", "2023-07-03"}                                   # the 13:15 ET closes: no pm session
    for name in NAMES:
        vs = families.library(name)["variants"]
        for tf in ("1", "5", "15", "30"):
            for vi, v in enumerate(vs):
                for s in S.ORDER7:
                    k, ok = n[(name, tf, vi, s)], port2.can_trade(name, v, tf, s)
                    assert ok or k == 0, (name, tf, v, s, k)
                    if name == "tod_drift" and ok:
                        assert k >= len(days) - (len(half) if s == "pm" else 1), (tf, v, s, k)     # 1: a roll / thin evening
    vs = families.library("tod_drift")["variants"]
    twins = 0
    for (tf, vi, sess), a in ents.items():
        if vs[vi]["dir"] != "long":
            continue
        b = ents[(tf, vs.index({**vs[vi], "dir": "short"}), sess)]
        assert [(d, ms) for d, ms, _ in a] == [(d, ms) for d, ms, _ in b], (tf, vs[vi], sess)        # the same entry prints
        assert {s for _, _, s in a} == {"long"} and {s for _, _, s in b} == {"short"}
        twins += len(a)
    assert twins > 500


def test_tod_drift_plateau_sets_split_by_direction_only_and_the_literal_rule_stays_the_default():
    """port2.plateau_sets / tradable are pure splits of a library.session_table. SYNTHETIC nets (no run is read): a pure
    one-direction drift cannot pass EDGE_SPEC's literal rule (all 256 cells), which is why the decision is the
    orchestrator's BEFORE the run; the pre-declared per-direction sets judge each direction on its own."""
    grid = families.unit_grid("tod_drift", "NQ", "5")
    vs = families.library("tod_drift")["variants"]
    assert port2.MIRROR_AXIS == {"tod_drift": "dir"} and len(grid) == 256
    table = [{"id": c["id"], "vi": c["vi"], "xi": c["xi"], "net": 100.0 if c["variant"]["dir"] == "long" else -140.0, "trades": 50}
             for c in grid]                                               # synthetic: every long cell +100, every short cell -140
    sets = port2.plateau_sets("tod_drift", table)
    assert list(sets) == ["long", "short"] and [len(v) for v in sets.values()] == [128, 128]
    assert sorted(r["id"] for v in sets.values() for r in v) == sorted(r["id"] for r in table)       # a split: nothing dropped
    assert all(vs[r["vi"]]["dir"] == k for k, v in sets.items() for r in v)
    lit = library.plateau(table)
    assert lit["pass"] is False and lit["share_pos"] == 0.5 and lit["cells"] == 256                  # the literal rule: 50 % < 60 %
    assert library.plateau(sets["long"])["pass"] is True and library.plateau(sets["short"])["pass"] is False
    for name in NAMES:                                                    # every other family: one set, EDGE_SPEC as written
        if name != "tod_drift":
            g = [{"id": c["id"], "vi": c["vi"], "xi": c["xi"], "net": 1.0} for c in families.unit_grid(name, "NQ", "5")]
            assert port2.plateau_sets(name, g) == {"all": g}
    # tradable: the rows whose variant can trade in that unit-session (eve tf 15: off_min 60 only; pre: not off_min 60)
    assert {vs[r["vi"]]["off_min"] for r in port2.tradable("tod_drift", table, "15", "eve")} == {60}
    assert len(port2.tradable("tod_drift", table, "15", "eve")) == 64 and port2.tradable("tod_drift", table, "30", "asia") == []
    assert len(port2.tradable("tod_drift", table, "5", "pre")) == 192 and len(port2.tradable("tod_drift", table, "5", "pm")) == 256
    empty_eve = [dict(r, net=0.0, trades=0) if vs[r["vi"]]["off_min"] == 0 else r for r in sets["long"]]
    assert library.plateau(empty_eve)["share_pos"] == 0.75               # a cell without a trade is "not > 0": the ceiling drops


# ---- an INDEPENDENT oracle of the first signal of every session: all seven sessions, NQ / ES / GC, atr / pts / pct stops -----
# Nothing below uses the Template: minute bars straight from the prints, tf bars on the ET clock, the indicators, the
# family's trigger, the gates (session window, warm-up, last 5 minutes), the fill print, the stop and the target.
ORACLE_DAYS = ["2022-03-15", "2022-06-13", "2022-09-21", "2023-03-22", "2023-08-09", "2023-10-17",     # no half day; 06-13 = a roll
               "2023-03-07", "2023-03-09", "2023-03-14", "2023-03-16"]
O_WARM = {"ema_ribbon": 10, "tema_slope": 8, "ema_pullback": 20, "supertrend": 10, "rsi2": 4, "first_bar_mom": 3, "tod_drift": 3,
          "mid_fade": 3}


def o_world(root, d, seg):
    """1-minute bars of one segment straight from the prints; minute index relative to 00:00 ET of the trade date (negative
    in the evening = the 6 hours before that midnight)."""
    tape = S.load_tape(d, root)
    day = dt.date.fromisoformat(d)
    mid = S.et_ns(day, "00:00")
    t0, t1 = (mid - 6 * 3600 * S.NS, mid) if seg == "eve" else (mid, S.et_ns(day, "16:10"))
    lo, hi = np.searchsorted(tape.ts, [t0, t1])
    ts, px = tape.ts[lo:hi], tape.px[lo:hi]
    k = (ts - mid) // S.MIN_NS
    first = np.flatnonzero(np.r_[True, k[1:] != k[:-1]])
    last = np.r_[first[1:] - 1, len(k) - 1]
    return {"tape": tape, "mid": int(mid), "t0": int(t0), "t1": int(t1), "m": k[first].tolist(), "o": px[first].tolist(),
            "c": px[last].tolist(), "h": np.maximum.reduceat(px, first).tolist(), "l": np.minimum.reduceat(px, first).tolist()}


def o_bars(w, tf):
    """tf bars on the ET clock: O, H, L, C, E (nominal close second) and D = the second the bar is DECIDED: its close, or --
    when the bucket's last minute has no print -- the end of the next minute that has one (a bar no print follows is never
    decided: dropped)."""
    m, have = w["m"], set(w["m"])
    out = {k: [] for k in "OHLCED"}
    i = 0
    while i < len(m):
        q, j = m[i] // tf, i
        while j + 1 < len(m) and m[j + 1] // tf == q:
            j += 1
        end = (q + 1) * tf
        if end - 1 not in have and j + 1 >= len(m):
            break
        out["O"].append(w["o"][i])
        out["H"].append(max(w["h"][i:j + 1]))
        out["L"].append(min(w["l"][i:j + 1]))
        out["C"].append(w["c"][j])
        out["E"].append(end * 60)
        out["D"].append(end * 60 if end - 1 in have else (m[j + 1] + 1) * 60)
        i = j + 1
    return out


def o_atr(b):
    """True ranges and the Wilder ATR(14) after each tf bar since the restart (the mean while <= 14 bars exist)."""
    H, L, C = b["H"], b["L"], b["C"]
    tr, atr = [], []
    for i in range(len(C)):
        tr.append(H[i] - L[i] if i == 0 else max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1])))
        atr.append(sum(tr) / (i + 1) if i < 14 else (atr[-1] * 13.0 + tr[i]) / 14.0)
    return tr, atr


def o_ema(C, span):
    out, e = [], None
    for c in C:
        e = c if e is None else e + 2.0 / (span + 1) * (c - e)
        out.append(e)
    return out


def o_signals(fam, p, b, tr):
    """The side the family's trigger gives at EVERY tf bar since the restart (None = none), before any gate."""
    H, L, C = b["H"], b["L"], b["C"]
    n = len(C)
    sig = [None] * n
    if fam == "ema_ribbon":                               # EMA 8 / 21 / 55 BECOME fully stacked on this bar
        e8, e21, e55 = o_ema(C, 8), o_ema(C, 21), o_ema(C, int(p.get("slow", 55)))
        prev = 0
        for i in range(n):
            al = 1 if e8[i] > e21[i] > e55[i] else -1 if e8[i] < e21[i] < e55[i] else 0
            if al and al != prev:
                sig[i] = "long" if al > 0 else "short"
            prev = al
    elif fam == "tema_slope":                             # the sign of TEMA(n)'s bar-to-bar change flips
        k = 2.0 / (int(p["n"]) + 1)
        t1 = t2 = t3 = last = None
        slope = 0
        for i in range(n):
            if t1 is None:
                t1 = t2 = t3 = C[i]
            else:
                t1 += k * (C[i] - t1)
                t2 += k * (t1 - t2)
                t3 += k * (t2 - t3)
            te = 3 * t1 - 3 * t2 + t3
            if last is not None and te != last:
                sg = 1 if te > last else -1
                if slope and sg != slope:
                    sig[i] = "long" if sg > 0 else "short"
                slope = sg
            last = te
    elif fam == "ema_pullback":                           # EMA50 rising and the bar dips to EMA20 and closes back above (mirror)
        e20, e50 = o_ema(C, int(p.get("n", 20))), o_ema(C, 50)
        for i in range(1, n):
            if e50[i] > e50[i - 1] and L[i] <= e20[i] < C[i]:
                sig[i] = "long"
            elif e50[i] < e50[i - 1] and H[i] >= e20[i] > C[i]:
                sig[i] = "short"
    elif fam == "supertrend":                             # Supertrend(10, 3): the close crosses the PREVIOUS bar's active band
        sa = up = dn = None
        dr = 1                                            # every restart begins "up"
        for i in range(n):
            sa = sum(tr[:i + 1]) / (i + 1) if i < 10 else (sa * 9.0 + tr[i]) / 10.0
            mu = float(p.get("mult", 3.0))
            u, d_ = (H[i] + L[i]) / 2.0 - mu * sa, (H[i] + L[i]) / 2.0 + mu * sa
            if up is not None:
                if C[i - 1] > up:
                    u = max(u, up)
                if C[i - 1] < dn:
                    d_ = min(d_, dn)
                if dr == -1 and C[i] > dn:
                    dr, sig[i] = 1, "long"
                elif dr == 1 and C[i] < up:
                    dr, sig[i] = -1, "short"
            up, dn = u, d_
    elif fam == "rsi2":                                   # RSI(2), Wilder smoothing of length 2, beyond th -> fade
        ag = al = None
        th = float(p["th"])
        for i in range(1, n):
            ch = C[i] - C[i - 1]
            g, ls = max(ch, 0.0), max(-ch, 0.0)
            ag, al = (g, ls) if ag is None else ((ag + g) / 2.0, (al + ls) / 2.0)
            r = 50.0 if ag + al == 0 else 100.0 if al == 0 else 100 - 100 / (1 + ag / al)
            sig[i] = "long" if r < th else "short" if r > 100 - th else None
    return sig


def o_daily_atr(root, d):
    """Wilder ATR(14) of the daily bars before the trade date (None before 15 exist)."""
    rows = [r for r in S.load_daily(root) if r["date"] < d]
    if len(rows) < 15:
        return None
    trs = [max(rows[i]["h"] - rows[i]["l"], abs(rows[i]["h"] - rows[i - 1]["c"]), abs(rows[i]["l"] - rows[i - 1]["c"]))
           for i in range(1, len(rows))]
    a = sum(trs[:14]) / 14.0
    for x in trs[14:]:
        a = (a * 13.0 + x) / 14.0
    return a


def o_expect(fam, p, w, b, atr, sig, sess, root, d, warm=O_WARM):
    """The ONE entry the family may take in session `sess` with max_tr 1 -> (side, decision second, reference price, ATR)."""
    a, e = S.SESS[sess]
    if fam == "tod_drift":                                # the clock: session start + off_min, on the last print before it
        t = a + int(p["off_min"]) * 60
        nb = sum(1 for x in b["D"] if x <= t)             # tf bars decided by then (a bar close comes before a clock event)
        i = int(np.searchsorted(w["tape"].ts, w["mid"] + t * S.NS, side="left"))
        if not (t < e - 300 and nb >= warm[fam]) or i == 0 or w["tape"].ts[i - 1] < w["t0"]:
            return None
        return p["dir"], t, float(w["tape"].px[i - 1]), atr[nb - 1]
    if fam == "mid_fade" and sess != "mid":
        return None
    own = [i for i in range(len(b["E"])) if a < b["E"][i] <= e and b["D"][i] <= e]       # the tf closes decided inside the session
    for n, i in enumerate(own):
        side = None
        if fam == "first_bar_mom":                        # the session's FIRST tf bar: range >= k x the ATR before it
            if n == 0 and i >= 1 and atr[i - 1] and b["H"][i] - b["L"][i] >= float(p["k"]) * atr[i - 1] and b["C"][i] != b["O"][i]:
                side = "long" if b["C"][i] > b["O"][i] else "short"
        elif fam == "mid_fade":                           # first tf close of mid: fade the 09:30 open -> last close before 11:00
            if n == 0:
                da = o_daily_atr(root, d)
                op = next((w["o"][j] for j, mm in enumerate(w["m"]) if mm * 60 >= 34200 and (mm + 1) * 60 <= b["D"][i]), None)
                cl = [w["c"][j] for j, mm in enumerate(w["m"]) if 34200 <= mm * 60 < 39600]
                if da and op is not None and cl:
                    mv = cl[-1] - op
                    if abs(mv) >= float(p["k"]) * da and mv != 0:
                        side = "short" if mv > 0 else "long"
        else:
            side = sig[i]
        if side and i + 1 >= warm[fam] and b["D"][i] < e - 300:           # warm since the restart; not in the last 5 minutes
            return side, b["D"][i], b["C"][i], atr[i]
    return None


def o_tick(x, tick):
    return round(round(x / tick) * tick, 6)


def o_trade(exp, p, w, sess, tick):
    """The trade row an expected entry must give: the first print 85 ms after the decision, one tick worse; the stop and
    the target at their distance from the REFERENCE price, moved by the slip of the fill. None when no print comes before
    the session's no-entry line (the order is cancelled there)."""
    side, t, ref, atr = exp
    sd = 1 if side == "long" else -1
    tp = w["tape"]
    i = int(np.searchsorted(tp.ts, w["mid"] + t * S.NS + 85 * 1_000_000, side="left"))
    if i >= len(tp.ts) or tp.ts[i] >= min(w["mid"] + (S.SESS[sess][1] - 300) * S.NS, w["t1"]):
        return None
    fill = o_tick(float(tp.px[i]) + sd * tick, tick)
    dist = {"pts": p["stop_val"], "pct": p["stop_val"] / 100.0 * abs(ref), "atr": p["stop_val"] * atr}[p["stop_mode"]]
    dist = max(dist, 2 * tick)
    return {"side": side, "entry_ms": int(tp.ts[i]) // 1_000_000, "entry_price": fill,
            "sl": o_tick(o_tick(ref - sd * dist, tick) + (fill - ref), tick),
            "tp": o_tick(o_tick(ref + sd * p["tgt_r"] * dist, tick) + (fill - ref), tick) if p["tgt_r"] > 0 else None}


def o_units(root):
    """(family, variant, tf, exit cell): every family at every tf with its defaults, every other registered variant at tf 5
    and 15, mid_fade also with k = 0 (it then fires every day); the exit cells rotate through the menu's 8 stops and 4 targets."""
    stops, tg = S.menu_stops(root), S.MENU_TGT_R
    units = [(f, {}, tf) for f in NAMES for tf in ("1", "5", "15", "30")]
    for f in NAMES:
        d = families.REGISTRY[f][0].defaults()
        units += [(f, v, tf) for v in families.library(f)["variants"] if v and v != {k: d[k] for k in v} for tf in ("5", "15")]
    units += [("mid_fade", {"k": 0.0}, tf) for tf in ("5", "30")]
    units += [(f, {k: v}, tf) for f, (k, vs) in NEW_SETTING.items() for v in vs if v != families.REGISTRY[f][0].defaults()[k] for tf in ("5", "15")]
    return [(f, v, tf, {**stops[j % len(stops)], "tgt_r": tg[j % len(tg)]}) for j, (f, v, tf) in enumerate(units)]


def o_check(root, units, classes, days, warm=O_WARM):
    """Run `classes[family]` for every unit x the three menu instances (max_tr 1) and compare EVERY session of EVERY day with
    the oracle -> (counts, mismatches)."""
    tick = S.SPECS[root][1]
    specs = [(classes[f], {**v, **x, "tf": tf, "sess": inst, "max_tr": 1}) for f, v, tf, x in units for inst in RM.SESS_PASSES]
    res = S.run_many(specs, days=days, root=root, workers=1)
    assert all(r["skipped_by_error"] == 0 for r in res), [r["no_trade"][:1] for r in res if r["skipped_by_error"]][:3]
    no_day = {s["date"] for s in res[0]["skipped"]}
    no_eve = {s["date"] for s in res[2].get("eve_skipped", []) + res[2]["skipped"]}
    got = {}
    for k, r in enumerate(res):
        inst = RM.SESS_PASSES[k % 3]
        for t in r["trades"]:
            key = (k // 3, t["date"], S.session_of(t["entry_ms"]))
            assert key not in got and key[2] in (S.ORDER if inst == "all" else (inst,)), key      # one per session, in its instance
            got[key] = t
    n, bad = Counter(), []
    for d in days:
        for seg in ("day", "eve"):
            if d in (no_eve if seg == "eve" else no_day):
                n["segments skipped"] += 1
                continue
            w = o_world(root, d, seg)
            bars = {}
            for k, (f, v, tf, x) in enumerate(units):
                p = {**classes[f].defaults(), **v, **x}
                if tf not in bars:
                    b = o_bars(w, int(tf))
                    bars[tf] = (b,) + o_atr(b)
                    n["late closes"] += sum(1 for e_, d_ in zip(b["E"], b["D"]) if d_ != e_)
                b, tr, atr = bars[tf]
                sig = o_signals(f, p, b, tr)
                for sess in (("eve",) if seg == "eve" else S.ORDER7[1:]):
                    exp = o_expect(f, p, w, b, atr, sig, sess, root, d, warm)
                    want = o_trade(exp, p, w, sess, tick) if exp else None
                    t = got.pop((k, d, sess), None)
                    n[("checked", sess)] += 1
                    if want is None:
                        if t is not None:
                            bad.append((f, v, tf, d, sess, "not expected", t["side"], t["entry_ms"]))
                        continue
                    n[("expected", sess)] += 1
                    n[("stop", p["stop_mode"])] += 1
                    n[("family", f)] += 1
                    if f == "first_bar_mom" and sess == "pre":            # 08:26 at tf 1; 08:30:00 -- the data release -- at tf 5 / 15 / 30
                        assert exp[1] == (30360 if tf == "1" else 30600)
                    if f == "tod_drift" and sess == "eve":                # 18:00 + off_min of the evening BEFORE the trade date
                        assert exp[1] == -21600 + p["off_min"] * 60 and want["entry_ms"] * 1_000_000 < w["mid"]
                    if t is None or any(t[c] != want[c] for c in want) or t["order_price"] is not None or t["date"] != d:
                        bad.append((f, v, tf, x, d, sess, want, t and {c: t[c] for c in want}))
                        continue
                    # flat by the session end (the flatten fills on the first print at / after it); the evening ends by 24:00
                    end_ns = w["mid"] + (S.SESS[sess][1] + 300) * S.NS
                    if t["exit_ms"] * 1_000_000 >= (min(end_ns, w["mid"]) if sess == "eve" else end_ns):
                        bad.append((f, v, tf, d, sess, "open past the session end", t["exit_ms"]))
                    if t["exit_reason"] == "bars":                        # tod_drift's time exit: the 6th tf close after the fill
                        closes = [c for c in b["D"] if w["mid"] + c * S.NS > want["entry_ms"] * 1_000_000 + 999_999]
                        tp_ = w["tape"]
                        j = int(np.searchsorted(tp_.ts, w["mid"] + closes[5] * S.NS, side="left")) if len(closes) >= 6 else None
                        sd = 1 if t["side"] == "long" else -1
                        n["bars exits"] += 1
                        if f != "tod_drift" or p["exit_bars"] != 6 or j is None or t["exit_ms"] != int(tp_.ts[j]) // 1_000_000 \
                                or t["exit_price"] != o_tick(float(tp_.px[j]) - sd * tick, tick):
                            bad.append((f, v, tf, d, sess, "bars exit", t["exit_ms"], t["exit_price"]))
    bad += [("a trade the oracle did not expect", k) for k in list(got)[:5]]
    return n, bad


@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_first_signal_of_every_session_equals_an_independent_oracle_in_all_seven_sessions(root):
    """max_tr 1: the only trade of a session is its first signal. For every family (every tf; every registered variant at
    tf 5 / 15), every one of the seven sessions and every day: the simulator's trade must be the oracle's -- the same side,
    entry print (ms), fill, stop and target -- or no trade where the oracle has none. Covers what no tester bundle can:
    `pre` / `eve`, the percent stop, GC."""
    guard()
    try:
        days = [d for d in ORACLE_DAYS if S._date(d) in set(S.sessions(*S.period("build"), root))]
        classes = {f: families.REGISTRY[f][0] for f in NAMES}
        n, bad = o_check(root, o_units(root), classes, days)
    except FileNotFoundError as e:
        pytest.skip(f"tape cache not available: {e}")
    assert not bad, (len(bad), bad[:5])
    assert len(days) >= 8 and n["segments skipped"] <= 2
    for sess in S.ORDER7:                                                 # not vacuous: every session, family and stop mode traded
        assert n[("checked", sess)] >= 60 * (len(days) - 2) and n[("expected", sess)] >= 150, (sess, n)
    assert all(n[("stop", m)] >= 300 for m in ("atr", "pts", "pct")), n
    assert all(n[("family", f)] >= (20 if f == "mid_fade" else 60) for f in NAMES), n
    assert n["bars exits"] >= 300, n                                      # tod_drift's 6-bar time exit, also in pre / eve


class _RsiSlow(port2.Rsi2):
    """BROKEN ON PURPOSE (never registered): the RSI smoothed over 3 bars instead of 2."""

    def fam_update(self, ctx):
        if self.nb < 2:
            return
        d = self.C[-1] - self.C[-2]
        g, ls = max(d, 0.0), max(-d, 0.0)
        if self.ag is None:
            self.ag, self.alo = g, ls
        else:
            self.ag, self.alo = (2 * self.ag + g) / 3.0, (2 * self.alo + ls) / 3.0
        self.rsi = 50.0 if self.ag + self.alo == 0 else 100.0 if self.alo == 0 else 100 - 100 / (1 + self.ag / self.alo)


class _TemaCold(port2.TemaSlope):
    """BROKEN ON PURPOSE (never registered): 3 tf bars of warm-up instead of 8."""
    WARM = 3


def test_the_oracle_catches_a_changed_trigger_and_a_changed_warm_up():
    guard()
    days = ORACLE_DAYS[:6]
    x = {"stop_mode": "pct", "stop_val": 0.10, "tgt_r": 1.0}
    units = [("rsi2", {"th": 15.0}, "1", x), ("rsi2", {}, "5", x), ("tema_slope", {}, "5", x), ("tema_slope", {"n": 10}, "15", x)]
    good = {f: families.REGISTRY[f][0] for f in NAMES}
    n, bad = o_check("NQ", units, good, days)
    assert not bad and n[("family", "rsi2")] > 50 and n[("family", "tema_slope")] > 50
    for fam, broken in (("rsi2", _RsiSlow), ("tema_slope", _TemaCold)):
        n, bad = o_check("NQ", [u for u in units if u[0] == fam], {**good, fam: broken}, days)
        assert len(bad) >= 5, (fam, len(bad))                             # the oracle sees the difference
    n, bad = o_check("NQ", units[2:], good, days, warm={**O_WARM, "tema_slope": 20})    # ... and a wrong oracle is seen too
    assert len(bad) >= 5
