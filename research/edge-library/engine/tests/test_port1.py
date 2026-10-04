"""families/port1.py -- the old pilot's orb, straddle, donchian, squeeze, ib, lon_break, gap on l2sim.Template.

  registry        the seven entries carry rationale, complexity, screen tfs and the PRE-REGISTERED variants
  pre-registration the variants are the first axis of the family's heat-map in R/tune1.jsonl / tune2.jsonl; the inputs are the
                  tester draft's (R/family_inputs.json); the ported bodies are R's `class Fam` statement for statement (AST)
  tester match    every screen bundle of the seven (4 tfs each; the NQ pilot's and the ES pilot's) and every cell of the NQ
                  heat-maps the variants come from, on 10 BUILD days: identical trades (the whole-window gate is
                  port1_gate.py -> PORT1_VALIDATION.md)
  workers         every family x variant x tf x session instance gives the same trades at 1 and at 8 worker processes,
                  and with a fresh instance per day (no state survives a session)
  no look-ahead   every print at / after a cut time replaced by garbage: decisions up to the cut and trades closed before it
                  are unchanged
BUILD days only. Identity and counts only: no P&L is asserted on, printed or stored.
L2_TEST_WORKERS (default 8) lowers the worker count on a busy machine (8 days at >= 2 workers = one fresh instance per day)."""
import ast
import datetime as dt
import json
import os

import numpy as np
import pytest

import families
import l2ref
import l2sim as S
import port1_gate as G
import run_menus
from families import port1 as P

NAMES = ("orb", "straddle", "donchian", "squeeze", "ib", "lon_break", "gap")
PORTED = {"orb": P.Orb, "squeeze": P.Squeeze, "ib": P.Ib, "lon_break": P.LonBreak, "gap": P.Gap}       # bodies copied from R
REFS = {"straddle": (P.Straddle, l2ref.Straddle), "donchian": (P.Donchian, l2ref.Donchian)}           # l2ref subclasses
BOTH = {"orb": True, "straddle": True, "donchian": False, "squeeze": True, "ib": True, "lon_break": True, "gap": False}
# family -> (tune file, 1-based line, first-axis key, the registered values): the source lines quoted in families/port1.py
SRC = {"orb": ("tune1.jsonl", 9, "or_min", ["5", "15", "30"]),
       "straddle": ("tune2.jsonl", 1, "off_atr", [0.25, 0.5, 1.0]),
       "donchian": ("tune1.jsonl", 1, "n", [10, 20, 40, 60]),
       "squeeze": ("tune2.jsonl", 2, "sq_type", ["bbkc", "nr7", "inside"]),
       "ib": ("tune1.jsonl", 4, "mode", ["break", "fade"]),
       "lon_break": ("tune2.jsonl", 9, "min_rng_atr", [0.0, 1.0, 2.0]),
       "gap": ("tune2.jsonl", 8, "mode", ["fill", "go"])}
DAYS10 = list(run_menus.SMOKE_DAYS)                      # 10 fixed BUILD days (a roll day, two half days, an FOMC day, ...)
DAYS8 = DAYS10[:8]
W = max(2, min(int(os.environ.get("L2_TEST_WORKERS", "8")), S.MAX_WORKERS))
NY = ("nyam", "mid", "pm")


def need_tapes():
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")
    if S.load_tape(DAYS10[0]) is None:
        pytest.skip("the NQ tape cache is not available")


def tune_lines(name: str) -> list:
    """(file, line number, job) of every sizing heat-map of the family in R/tune1.jsonl / tune2.jsonl (the axes only)."""
    out = []
    for f in ("tune1.jsonl", "tune2.jsonl"):
        for i, ln in enumerate((S.R / f).read_text().splitlines(), 1):
            j = json.loads(ln)
            if j["strategy"] == f"draft_pp_{name}" and j["stage"] == "sizing":
                out.append((f, i, j))
    return out


# ---- registry ---------------------------------------------------------------------------------------------------------------
def test_the_seven_families_are_registered_as_edge_library_entries():
    assert not [k for k in families.ERRORS if k == "port1" or k in NAMES], families.ERRORS
    assert set(P.FAMILIES) == set(NAMES)
    for name in NAMES:
        cls, inputs, both, notes = families.REGISTRY[name]
        lib = families.library(name)
        assert families.MODULE_OF[name] == "port1" and cls.__module__ == "families.port1" and cls is P.FAMILIES[name][0]
        assert families.check_entry(name, P.FAMILIES[name]) == []
        assert inputs == {} and both is BOTH[name] and notes.startswith(f"C {name}:")
        assert cls.SCREEN_TFS == ("1", "5", "15", "30") and cls.FEATURES == () and cls.session_independent is True
        assert lib["roots"] == ("NQ", "ES", "GC") and lib["l2"] is False and lib["weak"] is False and lib["ported"] == name
        assert lib["rationale"].endswith(".") and len(lib["rationale"]) > 60 and lib["rationale"].count(". ") == 0      # ONE sentence
        assert isinstance(lib["complexity"], int) and 2 <= lib["complexity"] <= 6
        for tf in cls.SCREEN_TFS:
            for root in lib["roots"]:
                grid = families.unit_grid(name, root, tf)
                assert len(grid) == 32 * len(lib["variants"]) == len({c["id"] for c in grid})
                assert all(c["spec"][0] is cls and c["spec"][1]["tf"] == tf and c["spec"][1]["sess"] == "all" for c in grid)
    # EDGE_SPEC C: the favourite that failed on 2025-26 starts with a penalty; the old finalists' exam is a second look
    assert "FAILED on 2025-26" in families.library("donchian")["penalty"]
    assert [n for n in NAMES if families.library(n)["penalty"]] == ["donchian"]
    assert all("SECOND look" in families.REGISTRY[n][3] for n in ("orb", "straddle", "donchian"))
    assert [families.library(n)["complexity"] for n in NAMES] == [3, 5, 3, 5, 6, 4, 5]


def test_the_rationales_are_the_edge_spec_strings():
    """EDGE_SPEC C: 'opening range = first balance of the session; donchian = trend continuation; lon_break = NY resolves
    the London range'; the others carry the hypothesis of R/families/<fam>.py."""
    rat = {n: families.library(n)["rationale"] for n in NAMES}
    assert rat["orb"].startswith("Opening range = the first balance of the session")
    assert rat["donchian"].startswith("Trend continuation") and rat["lon_break"].startswith("NY resolves the London range")
    assert "Compression precedes expansion" in rat["squeeze"] and "initial balance (09:30-10:30)" in rat["ib"]
    assert "prior daily close" in rat["gap"] and "session start" in rat["straddle"]
    for n in ("orb", "squeeze", "ib", "lon_break", "gap", "straddle", "donchian"):
        assert "Hypothesis:" in (S.R / "families" / f"{n}.py").read_text()          # R wrote one before its screen


# ---- pre-registration -------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("name", NAMES)
def test_variants_are_the_first_axis_of_the_familys_tune_heat_maps(name):
    f, line, key, values = SRC[name]
    lines = tune_lines(name)
    assert lines and (f, line) in [(a, b) for a, b, _ in lines]
    assert {j["axes"][0]["key"] for _, _, j in lines} == {key}                       # one first axis for the family
    quoted = next(j for a, b, j in lines if (a, b) == (f, line))
    assert quoted["axes"][0]["values"] == values
    union = []
    for _, _, j in lines:
        union += [v for v in j["axes"][0]["values"] if v not in union]
    variants = families.library(name)["variants"]
    assert [list(v) for v in variants] == [[key]] * len(variants)                    # ONE key: the first axis, nothing else
    assert sorted(v[key] for v in variants) == sorted(union) and [v[key] for v in variants] == values
    # the quoted source line is in the module, above the entry
    src = (S.L / "families" / "port1.py").read_text()
    assert f"R/{f} line {line} " in src and f'"axes": [{{"key": "{key}", "values": {json.dumps(values)}}}' in src
    # the family's default is one of its variants (the tester-matched screen bundle is a cell of the menu's family axis)
    cls = families.REGISTRY[name][0]
    assert cls.defaults()[key] in values


@pytest.mark.parametrize("name", NAMES)
def test_inputs_defaults_and_ranges_are_the_tester_drafts(name):
    fi = json.loads((S.R / "family_inputs.json").read_text())
    cls = families.REGISTRY[name][0]
    own = {k: v for c in cls.__mro__ if c not in S.Template.__mro__ for k, v in c.__dict__.get("DEFAULTS", {}).items()}
    assert set(own) == {r[0] for r in fi[name]}
    for key, typ, default, spec in fi[name]:
        sch = cls.schema()[key]
        assert own[key] == default and type(own[key]) is type(default) and sch[0] == typ
        if typ == "choice":
            assert list(sch[1]) == spec
        elif typ != "bool":
            assert list(sch[1:]) == spec
    for key, default, spec in fi["common"]:                                         # the Template's common inputs
        assert cls.defaults()[key] == default
    assert cls.defaults()["f_book"] == cls.defaults()["x_book"] == cls.defaults()["f_thin"] == cls.defaults()["f_depth"] == "off"


def _class(tree, name):
    return next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)


@pytest.mark.parametrize("name", sorted(PORTED))
def test_ported_bodies_are_the_r_family_statement_for_statement(name):
    """ENGINE.md § 2: 'a port copies the R family's class Fam body verbatim' -- compared as syntax trees."""
    r = _class(ast.parse((S.R / "families" / f"{name}.py").read_text()), "Fam")
    p = _class(ast.parse((S.L / "families" / "port1.py").read_text()), PORTED[name].__name__)
    r_fn = {n.name: ast.dump(n) for n in r.body if isinstance(n, ast.FunctionDef)}
    p_fn = {n.name: ast.dump(n) for n in p.body if isinstance(n, ast.FunctionDef)}
    assert r_fn and p_fn == r_fn                                                      # the same methods, the same statements
    r_at = {n.targets[0].id: ast.dump(n.value) for n in r.body if isinstance(n, ast.Assign)}
    p_at = {n.targets[0].id: ast.dump(n.value) for n in p.body if isinstance(n, ast.Assign)}
    assert all(p_at.get(k) == v for k, v in r_at.items())                             # SPANS / WARM as in R
    assert set(p_at) - set(r_at) == {"DEFAULTS", "SCHEMA", "SCREEN_TFS", "FEATURES"}
    assert PORTED[name].__bases__ == (S.Template,)


@pytest.mark.parametrize("name", sorted(REFS))
def test_straddle_and_donchian_are_the_tester_matched_reference_classes(name):
    cls, ref = REFS[name]
    assert cls.__bases__ == (ref,) and set(vars(cls)) - {"__module__", "__doc__", "__firstlineno__", "__static_attributes__"} == {
        "SCREEN_TFS", "FEATURES"}                                                     # nothing overridden
    assert cls.defaults() == ref.defaults() and cls.schema() == ref.schema()
    r = _class(ast.parse((S.R / "families" / f"{name}.py").read_text()), "Fam")
    for fn in (n for n in r.body if isinstance(n, ast.FunctionDef)):
        assert callable(getattr(cls, fn.name))                                        # every R hook exists on the port


# ---- tester match (10 BUILD days; the whole in-sample window: port1_gate.py) -----------------------------------------------
def test_gate_tables_are_the_ledgers_screen_runs_and_heat_maps():
    led = G.ledger_ids()
    assert set(G.SCREEN) == set(NAMES)
    for name in NAMES:
        assert set(G.SCREEN[name]) == set(families.REGISTRY[name][0].SCREEN_TFS)      # every screen tf has its tester bundle
        assert all(led[(name, tf)] == rid for tf, rid in G.SCREEN[name].items())
    led_es = G.ledger_ids("ES")                                                       # the ES pilot ran the same screen
    assert set(G.SCREEN_ES) == set(NAMES) and all(set(G.SCREEN_ES[n]) == {"1", "5", "15", "30"} for n in NAMES)
    assert all(led_es[(n, tf)] == rid and "_es_" in rid for n in NAMES for tf, rid in G.SCREEN_ES[n].items())
    lg = G.ledger_grids()
    assert {fam for fam, _ in G.GRIDS.values()} == set(NAMES) and all(lg[k] == gid for k, (_, gid) in G.GRIDS.items())
    for key, (fam, gid) in G.GRIDS.items():                                           # each heat-map's first axis = the variants' key
        axes = json.loads((G.V.GRIDS / gid / "grid.json").read_text())["axes"]
        assert axes[0]["key"] == SRC[fam][2] and [a["key"] for a in axes[1:]] == ["stop_val", "tgt_r"]
    covered = {fam: set() for fam in NAMES}
    for key, (fam, gid) in G.GRIDS.items():
        covered[fam] |= set(json.loads((G.V.GRIDS / gid / "grid.json").read_text())["axes"][0]["values"])
    assert all(covered[n] == set(SRC[n][3]) for n in NAMES)                           # every registered variant has tester cells


def test_screen_bundles_are_reproduced_trade_for_trade_on_ten_build_days():
    need_tapes()
    rows = G.gate(workers=1, days=DAYS10)
    assert len(rows) == 28 and {(x["family"], x["tf"]) for x in rows} == {(n, tf) for n in NAMES for tf in ("1", "5", "15", "30")}
    for x in rows:
        assert x["n_ref"] == x["n_sim"] == x["matched"] == x["exact_all_fields"], x
        assert x["net_diff"] == 0.0 and x["skips_equal"] and x["skipped_by_error"] == 0 and x["pass"], x
        assert x["sessions"] == 10 and x["root"] == "NQ"
    n = {name: sum(x["n_ref"] for x in rows if x["family"] == name) for name in NAMES}
    assert all(v > 0 for v in n.values()) and sum(n.values()) == 848, n              # not an empty comparison (the bundles' count)


def test_es_screen_bundles_are_reproduced_trade_for_trade_on_ten_build_days():
    """The same classes on root ES against the ES pilot's tester bundles (drafts pp_es_<fam>): $50 / pt, the tester's tape."""
    need_tapes()
    days = [d for d in DAYS10 if S.hb_tape_path(S._date(d), "ES") is not None]
    if len(days) < 8:
        pytest.skip("the ES tape cache is not available")
    rows = G.gate(workers=1, days=days, root="ES")
    assert len(rows) == 28 and {x["root"] for x in rows} == {"ES"}
    for x in rows:
        assert x["n_ref"] == x["n_sim"] == x["matched"] == x["exact_all_fields"], x
        assert x["net_diff"] == 0.0 and x["skips_equal"] and x["skipped_by_error"] == 0 and x["pass"], x
    n = {name: sum(x["n_ref"] for x in rows if x["family"] == name) for name in NAMES}
    assert all(v > 0 for v in n.values()), n


@pytest.mark.parametrize("key", sorted(G.GRIDS))
def test_every_variant_cell_of_the_heat_maps_is_reproduced_on_ten_build_days(key):
    need_tapes()
    g = G.grid_gate(key, workers=1, days=DAYS10)
    assert g["pass"] and g["cells_identical"] == g["cells_pass"] == g["cells"] and g["skipped_by_error"] == 0, g
    assert g["n_ref"] == g["n_sim"] == g["exact_all_fields"] > 0 and g["max_abs_net_diff"] == 0.0, g
    assert g["axis"] == SRC[g["family"]][2] and g["cells"] == 12 * len(g["values"])


# ---- 1 worker = 8 workers = a fresh instance per day -------------------------------------------------------------------------
def all_specs() -> list:
    """Every family x registered variant x screen tf x the three instances run_menus runs (sess all / pre / eve)."""
    out = []
    for name in NAMES:
        cls = families.REGISTRY[name][0]
        for v in families.library(name)["variants"]:
            for tf in cls.SCREEN_TFS:
                for sess in run_menus.SESS_PASSES:
                    out.append((name, sess, (cls, {**v, "tf": tf, "sess": sess})))
    return out


@pytest.fixture(scope="module")
def one_worker():
    need_tapes()
    specs = all_specs()
    return specs, S.run_many([s for _, _, s in specs], days=DAYS8, workers=1)


def test_identical_trades_at_1_and_8_workers(one_worker):
    specs, a = one_worker
    b = S.run_many([s for _, _, s in specs], days=DAYS8, workers=W)
    assert len(specs) == 20 * 4 * 3 and a[0]["meta"]["workers"] == 1 and b[0]["meta"]["workers"] == W
    for (name, sess, _), x, y in zip(specs, a, b):
        assert x["trades"] == y["trades"], (name, sess, x["meta"]["inputs"])          # every field of every trade, in order
        assert x["skipped_by_error"] == y["skipped_by_error"] == 0, (name, x["no_trade"][:1], y["no_trade"][:1])
        assert x["both_sides_sessions"] == y["both_sides_sessions"] and x["skipped"] == y["skipped"]
        assert x["eve_skipped"] == y["eve_skipped"] and x["sessions"] == y["sessions"] == len(DAYS8)


def test_a_fresh_instance_per_day_gives_the_same_trades(one_worker):
    """What 8 workers do on 8 days, without a pool: no state of a family survives a session."""
    specs, a = one_worker
    per_day = [S.run_many([s for _, _, s in specs], days=[d], workers=1) for d in DAYS8]
    for k, ((name, sess, _), x) in enumerate(zip(specs, a)):
        key = lambda t: (t["exit_ms"], t["entry_ms"])                                 # noqa: E731
        fresh = sorted((t for day in per_day for t in day[k]["trades"]), key=key)
        assert sorted(x["trades"], key=key) == fresh, (name, sess, x["meta"]["inputs"])


def test_declared_sides_sessions_and_instances(one_worker):
    specs, a = one_worker
    tot = {}
    for (name, sess, _), x in zip(specs, a):
        tags = {S.session_of(t["entry_ms"]) for t in x["trades"]}
        t = tot.setdefault(name, {"all": 0, "pre": 0, "eve": 0, "two": 0})
        t[sess] += len(x["trades"])
        t["two"] += x["both_sides_sessions"]
        if sess == "all":
            assert tags <= set(S.ORDER), (name, tags)                                 # the tester's five, nothing else
        else:
            assert tags <= {sess}, (name, sess, tags)                                 # a pre / eve instance trades only its session
        if name == "ib":
            assert tags <= set(NY)
        if name in ("lon_break", "gap"):
            assert tags <= {"nyam"}
        if not BOTH[name]:                                                            # declared one direction: the simulator agrees
            assert x["both_sides_sessions"] == 0 and not any(t["oco"] or t["both_sides"] for t in x["trades"])
        assert all(t["qty"] == 1 and t["date"] in DAYS8 for t in x["trades"])
    assert all(tot[n]["all"] > 0 for n in NAMES), tot
    assert all(tot[n]["two"] > 0 for n in NAMES if BOTH[n]), tot                      # ... and the both-side families show it
    for n in ("ib", "lon_break", "gap"):                                              # NY-only families: no pre / eve session
        assert tot[n]["pre"] == tot[n]["eve"] == 0
    for n in ("orb", "donchian", "squeeze"):                                          # the new sessions work on the ports
        assert tot[n]["pre"] > 0 and tot[n]["eve"] > 0, (n, tot[n])
    assert tot["straddle"]["pre"] > 0                                                 # 08:25: the ATR is warm (bars since 00:00)


def warm_dead(name: str, v: dict, tf: int, sess: str) -> bool:
    """WARM-UP ARITHMETIC (no data): can this family variant NEVER enter in `sess` at this tf? Indicators restart at 00:00 ET
    (18:00 for the evening), an entry needs its bars since the restart, a tf close inside the session and >= 5 minutes left."""
    a, b = (x // 60 for x in S.SESS[sess])                                           # minutes after 00:00 ET of the trade date
    if sess == "eve":
        a, b = a + 360, b + 360                                                       # ... after the 18:00 restart
    if name in ("ib", "lon_break", "gap"):
        return sess not in (NY if name == "ib" else ("nyam",))                        # by design (fam_filter), not by warm-up
    if name == "straddle":
        return a // tf < 3                                                            # fires at the session start: ATR not warm
    if name == "orb":
        return (a + int(v["or_min"])) // tf < 3                                       # fires at start + or_min
    need = {"donchian": lambda: max(int(v.get("n", 20)) + 1, 5),
            "squeeze": lambda: {"bbkc": 23, "nr7": 7, "inside": 3}[v["sq_type"]]}[name]()
    first = max(need * tf, (a // tf + 1) * tf)                                        # the first tf close that may signal
    return not (first <= b and first < b - 5)


def test_cells_that_cannot_trade_by_warm_up_arithmetic_do_not_trade(one_worker):
    """A registered (variant, tf) that can never enter in a session is a cell WITHOUT A TRADE in that session's plateau table
    (library.plateau counts it as 'not > 0'): e.g. donchian n 40 / 60 at tf 30 in EVERY session. Documented, not judged."""
    specs, a = one_worker
    dead = live = 0
    for (name, sess, (cls, params)), x in zip(specs, a):
        v = {k: params[k] for k in families.library(name)["variants"][0]}
        n = {}
        for t in x["trades"]:
            k = S.session_of(t["entry_ms"])
            n[k] = n.get(k, 0) + 1
        for s_ in (S.ORDER if sess == "all" else (sess,)):
            if warm_dead(name, v, int(params["tf"]), s_):
                assert n.get(s_, 0) == 0, (name, v, params["tf"], s_)
                dead += 1
            else:
                live += 1
    assert dead + live == 20 * 4 * 7
    assert warm_dead("donchian", {"n": 40}, 30, "pm") and warm_dead("donchian", {"n": 60}, 30, "nyam")
    assert warm_dead("donchian", {"n": 60}, 15, "mid") and not warm_dead("donchian", {"n": 60}, 15, "pm")
    assert warm_dead("orb", {"or_min": "5"}, 5, "asia") and not warm_dead("orb", {"or_min": "15"}, 5, "asia")
    assert warm_dead("straddle", {"off_atr": 0.5}, 1, "eve") and not warm_dead("straddle", {"off_atr": 0.5}, 30, "pre")
    assert warm_dead("squeeze", {"sq_type": "bbkc"}, 30, "nyam") and not warm_dead("squeeze", {"sq_type": "bbkc"}, 30, "mid")


def test_run_menus_smoke_is_clean_for_a_port(capsys):
    need_tapes()
    out = run_menus.smoke("gap", "NQ", "15", 10, 1)
    assert out["ok"] and out["cells"] == 64 and out["skipped_by_error"] == 0 and out["worker_parity"] and out["both_sides_ok"]
    assert out["trades_total"] > 0 and set(out["by_session"]) == {"nyam"} and out["nulls"] == {}
    keys = lambda o: set(o) | {k for v in o.values() if isinstance(v, dict) for k in keys(v)}          # noqa: E731
    assert not keys(out) & {"net", "gross", "pnl", "exit_reason", "wr", "pf", "win_rate", "sharpe", "maxdd"}   # counts only


# ---- no look-ahead: garbage after a cut time ---------------------------------------------------------------------------------
class Rec:
    """Mixin: logs every decision (what was sent, when) and what each tf close could see."""

    def fam_update(self, ctx):
        super().fam_update(ctx)
        self.log.append((ctx.now_ns, "close", self.nb, self.atr, self.O[-1], self.H[-1], self.L[-1], self.C[-1], self.V[-1],
                         self.sid, self.sn, self.vw()))

    def _mkt(self, ctx, side, **kw):
        o = super()._mkt(ctx, side, **kw)
        self.log.append((ctx.now_ns, "mkt", side, None if o is None else (o.sl, o.tp, o.ref)))
        return o

    def _arm(self, ctx, legs, **kw):
        os_ = super()._arm(ctx, legs, **kw)
        self.log.append((ctx.now_ns, "arm", tuple((NAME(o.side), o.price, o.sl, o.tp) for o in os_)))
        return os_

    def _cancel(self, ctx):
        self.log.append((ctx.now_ns, "cancel", len(self.orders)))
        super()._cancel(ctx)


def NAME(side):
    return S.NAME.get(side, side)


REC = {name: type("Rec" + families.REGISTRY[name][0].__name__, (Rec, families.REGISTRY[name][0]), {}) for name in NAMES}
LA_DAYS = ("2023-03-15", "2022-09-21")                   # a plain day and an FOMC day (BUILD)
LA_CUTS = {"all": ("02:13", "03:00", "08:25", "09:30", "09:47", "10:30", "11:00", "13:30", "14:41"),
           "pre": ("08:25", "08:47", "09:30"), "eve": ("18:00", "19:13", "20:00", "22:31")}


def garbage_after(tape, cut_ns: int, seed: int):
    """The same tape with every print at / after cut_ns replaced by garbage (prices on the tick grid, hundreds of points away
    and jumping; random sizes). The timestamps stay (the event clock is not data)."""
    k = int(np.searchsorted(tape.ts, cut_ns, side="left"))
    rng = np.random.default_rng(seed)
    px, size = tape.px.copy(), tape.size.copy()
    n = len(px) - k
    px[k:] = np.round((px[k - 1 if k else 0] + 400.0 + rng.integers(-3000, 3000, n) * 0.25) / 0.25) * 0.25
    size[k:] = rng.integers(1, 500, n)
    return S.Tape(tape.root, tape.date, tape.contract, tape.ts, px, size), n


def play(cls, params, tape, prior, sess):
    st = cls(params)
    st.log = []
    if sess == "eve":
        if not st.eve_window:                                                         # NY-only families: no evening session
            return [], []
        res = S.run_session(st, tape, daily=prior, window=st.eve_window, segment="eve", on_error="raise")
    else:
        res = S.run_session(st, tape, daily=prior, on_error="raise")
    return st.log, res.trades


ENTRY = ("date", "side", "qty", "entry_price", "order_price", "entry_ns", "oco")


def before_cut(log, trades, cut):
    """What must not depend on any print at / after `cut`: every decision made up to the cut and everything a tf close up
    to the cut could see; the trades closed before the cut (every field); the entry of every trade entered before it."""
    return ([x for x in log if x[0] <= cut], [t for t in trades if t["exit_ns"] < cut],
            [[t[k] for k in ENTRY] for t in trades if t["entry_ns"] < cut])


@pytest.mark.parametrize("name", NAMES)
def test_no_look_ahead_garbage_after_a_cut_changes_nothing_before_it(name):
    need_tapes()
    daily = S.load_daily("NQ")
    changed = decisions = closed = 0
    for iso in LA_DAYS:
        d = dt.date.fromisoformat(iso)
        tape = S.load_tape(d)
        prior = [r for r in daily if r["date"] < iso]
        assert prior[-1]["date"] < iso and tape is not None
        for v in families.library(name)["variants"]:
            for tf in ("1", "5", "30"):
                for sess, cuts in LA_CUTS.items():
                    params = {**v, "tf": tf, "sess": sess}
                    log0, tr0 = play(REC[name], params, tape, prior, sess)
                    for i, hhmm in enumerate(cuts):
                        cut = S.et_ns(d - dt.timedelta(days=1) if sess == "eve" else d, hhmm)
                        bad, n_bad = garbage_after(tape, cut, seed=7 + i)
                        assert n_bad > 1000                                           # there IS data after the cut to corrupt
                        log1, tr1 = play(REC[name], params, bad, prior, sess)
                        b0, b1 = before_cut(log0, tr0, cut), before_cut(log1, tr1, cut)
                        assert b0 == b1, (name, params, iso, hhmm)
                        decisions += sum(1 for x in b0[0] if x[1] in ("mkt", "arm"))
                        closed += len(b0[1])
                        changed += [x for x in log0 if x[0] > cut] != [x for x in log1 if x[0] > cut]
    assert decisions > 0 and closed > 0 and changed > 0      # the comparison saw real decisions, and the garbage did bite later


class Peeker(Rec, P.Donchian):
    """BROKEN ON PURPOSE: at every tf close it reads a print 20 minutes in the FUTURE (straight from the simulator's arrays;
    no strategy can do this through ctx) and takes its side from it. The garbage test must catch it at every cut."""

    def _peek(self, ctx):
        s = ctx._s
        return float(s.px[min(int(np.searchsorted(s.ts, ctx.now_ns + 1200 * S.NS)), len(s.px) - 1)])

    def fam_update(self, ctx):
        super().fam_update(ctx)
        self.log.append((ctx.now_ns, "peek", self._peek(ctx)))

    def fam_signal(self, ctx):
        self._mkt(ctx, "long" if self._peek(ctx) > self.C[-1] else "short")


def test_the_garbage_test_catches_a_family_that_reads_the_future():
    need_tapes()
    iso = LA_DAYS[0]
    d = dt.date.fromisoformat(iso)
    tape, prior = S.load_tape(d), [r for r in S.load_daily("NQ") if r["date"] < iso]
    params = {"tf": "5", "sess": "all"}
    log0, tr0 = play(Peeker, params, tape, prior, "all")
    caught = flipped = 0
    for i, hhmm in enumerate(LA_CUTS["all"]):
        cut = S.et_ns(d, hhmm)
        log1, tr1 = play(Peeker, params, garbage_after(tape, cut, seed=7 + i)[0], prior, "all")
        b0, b1 = before_cut(log0, tr0, cut), before_cut(log1, tr1, cut)
        caught += b0 != b1
        flipped += [x for x in b0[0] if x[1] == "mkt"] != [x for x in b1[0] if x[1] == "mkt"] or b0[2] != b1[2]
    assert len(tr0) > 5 and caught == len(LA_CUTS["all"])               # every cut: a tf close before it saw a print after it
    assert flipped >= 1                                                  # ... and an order sent before a cut changed with it
