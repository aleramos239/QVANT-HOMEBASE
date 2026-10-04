"""PORT GROUP 3 (families/port3.py): vwap_band, vwap_z, vwap_flip, pinbar, sweep_rev -- EDGE_SPEC family C.

  * registry: library entries (rationale, complexity, roots, tfs of the old screen), the family-parameter variants ARE the
    first axis of the family's heat-map in R/tune1.jsonl / tune2.jsonl, DEFAULTS / SCHEMA are the tester draft's inputs;
  * the class bodies are R/families/<fam>.py `class Fam` VERBATIM (syntax trees compared method by method);
  * trigger semantics on scripted bars (no market data);
  * tester-match: one in-sample month (with a contract-roll day) of all 20 NQ and 20 ES screen bundles and of one heat-map
    cell per registered variant, trade for trade; the full-window gate is port3_validate.py -> PORT3_VALIDATION.md, whose
    report must be a PASS for the port3.py that is on disk;
  * an INDEPENDENT oracle (numpy, from the raw prints) of each family's first signal of every session -- all seven
    sessions, i.e. also `pre` and `eve`, which the tester cannot run;
  * no look-ahead: every print after a cut time replaced by garbage -> the entries before the cut and every trade closed
    before it are unchanged;
  * the same trades at 1 and at 8 worker processes (L2_TEST_WORKERS lowers the count), the three menu instances
    (sess all / pre / eve) of every family x tf; the counts-only smoke of run_menus.
Identity and counts only: no result is judged, no bundle P&L is read into an assertion or printed. BUILD days only, except
the tester-match month (in-sample bundles, trade identity)."""
import ast
import datetime as dt
import hashlib
import inspect
import json
import os
import textwrap
import warnings

import numpy as np
import pytest

import edge_validate as EV
import families
import l2sim as S
import run_menus as RM
import sim_validate as V
from families import port3 as P3

FAMS = ("vwap_band", "vwap_z", "vwap_flip", "pinbar", "sweep_rev")
CLS = {"vwap_band": P3.VwapBand, "vwap_z": P3.VwapZ, "vwap_flip": P3.VwapFlip, "pinbar": P3.Pinbar, "sweep_rev": P3.SweepRev}
TFS = ("1", "5", "15", "30")
INST = ("all", "pre", "eve")                           # the three independent instances run_menus runs per menu cell
W = max(2, min(int(os.environ.get("L2_TEST_WORKERS", "8")), S.MAX_WORKERS))
DAYS = list(RM.SMOKE_DAYS)                             # 10 fixed BUILD days (roll day, roll + 1, two half days, FOMC, plain)
FULL = ["2022-03-15", "2022-06-13", "2022-09-21", "2023-03-22", "2023-08-09", "2023-10-17"]   # of them: no half day; 06-13 = Monday + roll
ENGINE = S.L


def _window():
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")


# ---- registry ---------------------------------------------------------------------------------------------------------------

def _tune_lines(fam):
    """The sizing heat-map lines of a family in R/tune1.jsonl and R/tune2.jsonl: [(raw text, job)]."""
    out = []
    for name in ("tune1.jsonl", "tune2.jsonl"):
        for raw in (S.R / name).read_text().splitlines():
            if raw.strip():
                j = json.loads(raw)
                if j["strategy"] == f"draft_pp_{fam}" and j["stage"] == "sizing":
                    out.append((raw, j))
    return out


def test_the_five_are_registered_as_edge_library_families():
    assert "port3" not in families.ERRORS and not [f for f in FAMS if f in families.ERRORS], families.ERRORS
    for fam in FAMS:
        cls, inputs, both, notes = families.REGISTRY[fam]
        lib = families.library(fam)
        assert families.MODULE_OF[fam] == "port3" and cls is CLS[fam] and inputs == {} and both is False
        assert families.check_entry(fam, P3.FAMILIES[fam]) == []
        assert cls.FEATURES == () and lib["l2"] is False and lib["roots"] == ("NQ", "ES", "GC") and lib["ported"] == fam
        assert lib["weak"] is False and lib["penalty"] is None
        assert isinstance(lib["complexity"], int) and 2 <= lib["complexity"] <= 5
        rat = lib["rationale"]
        assert rat.endswith(".") and rat.count(". ") == 0 and len(rat) > 80, rat          # ONE sentence
        assert notes.startswith("C / R#")
    # EDGE_SPEC C names the rationale of the VWAP fades and of sweep_rev: the entries carry those strings
    spec = " ".join((S.W / "EDGE_SPEC.md").read_text().split())
    assert "vwap fades = mean reversion to fair price" in spec and "sweep_rev = stop-run exhaustion at prior-day / overnight extremes" in spec
    for fam in ("vwap_band", "vwap_z"):
        assert families.library(fam)["rationale"].startswith("VWAP fade = mean reversion to fair price (EDGE_SPEC C)")
    assert families.library("sweep_rev")["rationale"].startswith("Stop-run exhaustion at prior-day / overnight extremes (EDGE_SPEC C)")
    assert sorted(families.library(f)["complexity"] for f in FAMS) == [2, 3, 4, 4, 5]


@pytest.mark.parametrize("fam", FAMS)
def test_variants_are_the_first_axis_of_the_familys_heat_map_in_the_tune_files(fam):
    lines = _tune_lines(fam)
    assert lines, fam
    src = inspect.getsource(P3)
    for raw, j in lines:
        ax = j["axes"][0]
        assert ax["key"] not in ("stop_val", "tgt_r", "max_tr")                       # a family parameter, not an exit / max_tr
        assert families.library(fam)["variants"] == [{ax["key"]: v} for v in ax["values"]], j["key"]
        quote = raw[raw.index('"axes": ['):raw.index("}", raw.index('"axes": [')) + 1]     # '"axes": [{"key": ..., "values": [...]}'
        assert quote in src and f'"{j["key"]}"' in src                                # the source line is quoted in the module
    for v in families.library(fam)["variants"]:
        CLS[fam]({**v, "tf": "5"})                                                    # every variant is a valid input set
    assert {} not in families.library(fam)["variants"] and CLS[fam].defaults()[ax["key"]] in ax["values"]   # the default is one of them


@pytest.mark.parametrize("fam", FAMS)
def test_screen_tfs_are_the_old_screens_and_inputs_are_the_tester_drafts(fam):
    keys = {json.loads(ln)["key"] for ln in (S.R / "jobs.jsonl").read_text().splitlines() if ln.strip()}
    old = tuple(tf for tf in TFS if f"screen-{fam}-tf{tf}" in keys)
    assert CLS[fam].SCREEN_TFS == old == TFS
    spec = json.loads((S.R / "family_inputs.json").read_text())
    own = CLS[fam].__dict__["DEFAULTS"]
    assert list(own) == [row[0] for row in spec[fam]]
    for key, kind, default, rng in spec[fam]:
        assert own[key] == default and type(own[key]) is type(default)
        assert CLS[fam].SCHEMA[key] == (("choice", tuple(rng)) if kind == "choice" else (kind, rng[0], rng[1]))
    common = {row[0]: row[1] for row in spec["common"]}                               # the Template's defaults are the draft's
    assert {k: CLS[fam].defaults()[k] for k in common} == common


def _methods(src, name):
    cls = next(n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == name)
    return {n.name: ast.dump(n) for n in cls.body if isinstance(n, ast.FunctionDef)}


@pytest.mark.parametrize("fam", FAMS)
def test_the_class_body_is_the_r_family_verbatim(fam):
    ref = _methods((S.R / "families" / f"{fam}.py").read_text(), "Fam")
    got = _methods(textwrap.dedent(inspect.getsource(CLS[fam])), CLS[fam].__name__)
    assert ref and got == ref                                 # the same methods, the same syntax tree, nothing added
    assert CLS[fam].__bases__ == (S.Template,) and CLS[fam].session_independent is True
    extra = set(CLS[fam].__dict__) - set(ref) - {"__module__", "__doc__", "__qualname__", "__firstlineno__", "__static_attributes__",
                                                 "DEFAULTS", "SCHEMA", "SCREEN_TFS", "FEATURES"}
    assert not extra, extra                                   # no WARM / SPANS / placement override, no extra hook


@pytest.mark.parametrize("fam", FAMS)
@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_unit_grid_is_variants_times_the_32_exit_cells(fam, root):
    for tf in TFS:
        grid = families.unit_grid(fam, root, tf)
        nv = len(families.library(fam)["variants"])
        assert len(grid) == nv * 32 and len({c["id"] for c in grid}) == len(grid)
        assert [c["exit"] for c in grid[:32]] == S.menu(root) and {c["vi"] for c in grid} == set(range(nv))
        for c in grid:
            cls, p = c["spec"]
            assert cls is CLS[fam] and p["tf"] == tf and p["sess"] == "all" and set(c["variant"]) <= set(cls.__dict__["DEFAULTS"])
            st = cls(p)
            assert st.p["max_tr"] == 3 and st.p["dir"] == "both" and all(st.p[k] == "off" for k in ("f_trend", "f_vwap", *families.L2_OPTIONS))


# ---- trigger semantics on scripted bars (no market data) --------------------------------------------------------------------

def _mk(fam, params=None, sid="nyam", vwap=100.0, sigma=1.0):
    """An instance with a session VWAP of (vwap, sigma) and a recorder instead of the order call."""
    st = CLS[fam]({"tf": "5", **(params or {})})
    st.sid, st.sn, st.atr = sid, 3, 1.0
    st.vs = [1.0, vwap, sigma * sigma + vwap * vwap]          # -> vw() == (vwap, sigma)
    st.O, st.H, st.L, st.C = [], [], [], []
    st.pdh = st.pdl = st.pdc = st.onh = st.onl = None
    st.calls = []
    st._mkt = lambda ctx, side, **kw: st.calls.append((side, kw))
    if hasattr(st, "fam_day"):
        st.fam_day(None)
    st.fam_session(None, sid)
    return st


def _closes(st, closes):
    """Feed tf closes: fam_update + fam_signal at each -> the side entered at each close ('' = none)."""
    out = []
    for c in closes:
        st.C.append(c)
        st.calls.clear()
        st.fam_update(None)
        st.fam_signal(None)
        out.append(st.calls[0][0] if st.calls else "")
    return out


def test_vwap_z_fades_a_close_zth_sigma_from_vwap():
    st = _mk("vwap_z")                                         # zth 2: VWAP 100, sigma 1
    assert _closes(st, [101.9, 102.0, 103.0, 100.0, 98.1, 98.0, 96.0]) == ["", "short", "short", "", "", "long", "long"]
    st.sn = 2
    assert _closes(st, [105.0]) == [""]                        # fewer than 3 tf bars in the session
    st = _mk("vwap_z", sigma=0.0)
    assert _closes(st, [105.0]) == [""]                        # no dispersion yet
    assert _closes(_mk("vwap_z", {"zth": 3.0}), [102.9, 103.0, 97.0]) == ["", "short", "long"]


def test_vwap_band_fades_the_close_back_inside_after_a_close_outside():
    st = _mk("vwap_band")                                      # band 2: 98 .. 102
    #                   in     out+   out+   back    out-  on the band = inside   in
    assert _closes(st, [101.0, 102.5, 104.0, 101.5, 97.0, 98.0, 99.0]) == ["", "", "", "short", "", "long", ""]
    assert _closes(st, [103.0, 97.0, 99.0]) == ["", "short", "long"]     # through the whole band: fade the upper side, then the lower
    st = _mk("vwap_band")
    assert _closes(st, [102.0, 101.0]) == ["", ""]             # ON the band is not outside
    st = _mk("vwap_band")
    st.sn = 2
    assert _closes(st, [105.0]) == [""] and st.pout == 0       # before the 3rd bar nothing is tracked
    st.sn = 3
    assert _closes(st, [101.0]) == [""]
    assert _closes(_mk("vwap_band", {"band": 3.0}), [102.5, 103.5, 102.9]) == ["", "", "short"]


def test_vwap_flip_enters_after_the_cross_has_held_for_hold_bars():
    st = _mk("vwap_flip")                                      # hold 2
    assert _closes(st, [101.0, 99.0, 98.0, 97.0, 96.0]) == ["", "", "", "short", ""]
    st = _mk("vwap_flip")                                      # a re-cross while pending restarts the count on the other side
    assert _closes(st, [101.0, 99.0, 101.0, 102.0, 103.0]) == ["", "", "", "", "long"]
    st = _mk("vwap_flip")                                      # a close ON VWAP is ignored: it neither counts nor resets
    assert _closes(st, [99.0, 101.0, 100.0, 102.0, 100.0, 103.0]) == ["", "", "", "", "", "long"]
    assert _closes(_mk("vwap_flip", {"hold": 1}), [99.0, 101.0, 102.0, 103.0]) == ["", "", "long", ""]
    assert _closes(_mk("vwap_flip", {"hold": 3}), [99.0, 101.0, 102.0, 103.0, 104.0]) == ["", "", "", "", "long"]
    assert _closes(_mk("vwap_flip"), [101.0, 102.0, 103.0, 104.0]) == [""] * 4      # no cross, no trade
    st = _mk("vwap_flip", {"anchor": "rth"})                   # the anchored VWAP is read instead
    st.vr = [1.0, 50.0, 2501.0]
    assert _closes(st, [49.0, 51.0, 52.0, 53.0]) == ["", "", "", "long"]


def _bar(st, o, h, l, c):
    st.O.append(o), st.H.append(h), st.L.append(l), st.C.append(c)
    st.calls.clear()
    st.fam_update(None)
    st.fam_signal(None)
    return list(st.calls)


def test_pinbar_needs_the_wick_and_a_key_level_within_a_quarter_atr():
    st = _mk("pinbar", vwap=50.0)                              # VWAP far away; ATR 1 -> tolerance 0.25
    st.pdl = 97.2
    assert _bar(st, 100.0, 100.5, 97.0, 100.25) == [("long", {"struct": 97.0})]      # lower wick 3.0 / 3.5, low 0.2 from PDL
    st.pdl = 97.3
    assert _bar(st, 100.0, 100.5, 97.0, 100.25) == []                                # 0.3 away: no level
    st.pdl, st.pdh = None, 103.25
    assert _bar(st, 100.0, 103.0, 99.5, 99.75) == [("short", {"struct": 103.0})]     # upper wick 3.0 / 3.5 at PDH
    assert _bar(st, 100.0, 103.0, 99.5, 101.5) == []                                 # wick 1.5 / 3.5 < 0.667
    assert _bar(st, 100.0, 100.0, 100.0, 100.0) == []                                # no range
    st.pdh, st.pdc = None, 97.0
    assert _bar(st, 100.0, 100.5, 97.0, 100.25)[0][0] == "long"                      # the prior close is a level too
    # the overnight high / low count in the NY sessions only (R: "NY sessions only"); VWAP counts everywhere
    for sid, on in (("nyam", True), ("mid", True), ("pm", True), ("asia", False), ("london", False), ("pre", False), ("eve", False)):
        st = _mk("pinbar", sid=sid, vwap=50.0)
        st.onl = 97.0
        assert bool(_bar(st, 100.0, 100.5, 97.0, 100.25)) is on, sid
        st = _mk("pinbar", sid=sid, vwap=97.1)
        assert _bar(st, 100.0, 100.5, 97.0, 100.25) == [("long", {"struct": 97.0})], sid
    st = _mk("pinbar", {"wick": 0.75}, vwap=97.0)
    assert _bar(st, 100.0, 100.5, 97.0, 99.5) == [] and _bar(st, 100.0, 100.5, 97.0, 100.0)[0][0] == "long"   # 2.5 / 3.5, 3.0 / 3.5


def test_sweep_rev_fades_the_close_back_inside_once_per_level():
    st = _mk("sweep_rev")
    st.pdh, st.pdl, st.onh, st.onl = 110.0, 90.0, 105.0, 95.0
    st.fam_session(None, "nyam")
    assert list(st.lv) == ["pdh", "pdl", "onh", "onl"]
    assert _bar(st, 104.0, 104.9, 103.0, 104.5) == []                                # nothing swept
    assert _bar(st, 104.5, 106.0, 104.0, 105.5) == []                                # beyond ONH, closed beyond: armed
    assert _bar(st, 105.5, 107.0, 105.0, 105.0) == [("short", {"struct": 107.0})]    # close back AT the level = inside; extreme 107
    assert _bar(st, 105.0, 106.0, 104.0, 104.0) == []                                # that level is done for the session
    assert _bar(st, 96.0, 96.0, 94.0, 96.0) == [("long", {"struct": 94.0})]          # sweep and close back within ONE bar
    assert _bar(st, 108.0, 111.0, 89.0, 100.0) == [("short", {"struct": 111.0})]     # two levels on one bar: the first one (PDH)
    assert st.lv["pdl"][3] is True                                                   # ... and the other is used up too
    for mode, want in (("pd", ["pdh", "pdl"]), ("on", ["onh", "onl"]), ("both", ["pdh", "pdl", "onh", "onl"])):
        st = _mk("sweep_rev", {"levels": mode})
        st.pdh, st.pdl, st.onh, st.onl = 110.0, 90.0, 105.0, 95.0
        st.fam_session(None, "london")
        assert list(st.lv) == want
    st = _mk("sweep_rev")                                      # a roll day (no prior-day levels) in asia / eve (no overnight range)
    st.fam_session(None, "eve")
    assert st.lv == {} and _bar(st, 100.0, 120.0, 80.0, 100.0) == []
    st.sid = None                                              # between sessions nothing is tracked
    st.lv = {"pdh": [110.0, 1, None, False]}
    assert _bar(st, 100.0, 120.0, 80.0, 100.0) == [] and st.lv["pdh"][2] is None


# ---- tester match ------------------------------------------------------------------------------------------------------------
MONTH = ("2022-03-01", "2022-03-31")                         # in-sample; holds a contract-roll day on both roots


def _jobs(root):
    import port3_validate as PV
    return PV.bundles(root)


@pytest.mark.parametrize("root", ["NQ", "ES"])
def test_one_month_of_every_screen_bundle_is_reproduced_trade_for_trade(root):
    _window()
    a, b = MONTH
    assert any(a <= d <= b for d in S.default_rolls(root))
    runs = _jobs(root)["runs"]
    assert [(f, tf) for _, f, tf, _ in runs] == [(f, tf) for f in FAMS for tf in TFS]
    loaded = [EV.load_run(rid) for _, _, _, rid in runs]             # refuses a bundle that reaches 2025; in-sample rows only
    assert all(ld[3] == root for ld in loaded)
    res = S.run_many([(CLS[f], ld[0]) for (_, f, _, _), ld in zip(runs, loaded)], a, b, root=root, workers=1)
    for (key, fam, tf, _), (inputs, ref, cov, _), r in zip(runs, loaded, res):
        ref = [t for t in ref if a <= t["date"] <= b]
        c = V.compare(r["trades"], ref)
        assert c["n_sim"] == c["n_ref"] == c["matched"] == c["exact_all_fields"] and c["net_diff"] == 0.0, (root, key)
        assert r["skipped_by_error"] == 0 and r["both_sides_sessions"] == 0 and c["n_ref"] > 0, (root, key)
        assert [s["date"] for s in r["skipped"]] == [s["date"] for s in cov["skipped"] if a <= s["date"] <= b]


def test_one_month_of_a_heat_map_cell_per_registered_variant_is_reproduced():
    _window()
    a, b = MONTH
    cells = []
    for key, fam, gid in _jobs("NQ")["grids"]:
        g = json.loads((V.GRIDS / gid / "grid.json").read_text())
        if g["axes"][0]["key"] in ("stop_val", "tgt_r"):
            continue                                              # a fixed-point exit map (full gate only)
        n2 = len(g["axes"][1]["values"]) * len(g["axes"][2]["values"])
        for i in range(len(g["axes"][0]["values"])):
            cells.append((fam, key, V.load_bundle(f"{gid}#{i * n2 + 5}")))      # one exit cell of each first-axis value
    seen = {f: [] for f in FAMS}
    res = S.run_many([(CLS[f], c[0]) for f, _, c in cells], a, b, workers=1)
    for (fam, key, (inputs, ref, cov, cost, engine)), r in zip(cells, res):
        c = V.compare(r["trades"], [t for t in ref if a <= t["date"] <= b])
        assert c["n_sim"] == c["n_ref"] == c["exact_all_fields"] and c["net_diff"] == 0.0 and r["skipped_by_error"] == 0, (key, inputs)
        own = {k: inputs[k] for k in CLS[fam].__dict__["DEFAULTS"] if k != "anchor"}
        seen[fam].append(own)
    for fam in FAMS:                                               # every registered variant was one of the matched cells
        assert all(v in seen[fam] for v in families.library(fam)["variants"]), fam


def test_the_full_window_gate_report_is_a_pass_for_the_module_on_disk():
    p = ENGINE / "out" / "port3_validation.json"
    assert p.exists(), "run `python port3_validate.py` (the tester-match gate of port group 3)"
    out = json.loads(p.read_text())
    now = hashlib.sha256((ENGINE / "families" / "port3.py").read_bytes()).hexdigest()[:16]
    assert out["sha"]["families/port3.py"] == out["sha_end"]["families/port3.py"] == now, "families/port3.py changed: re-run port3_validate.py"
    for f in ("l2sim.py", "l2ref.py"):
        if out["sha"][f] != hashlib.sha256((ENGINE / f).read_bytes()).hexdigest()[:16]:
            warnings.warn(f"{f} changed since the port3 gate ran: re-run port3_validate.py (and edge_validate.py)")
    assert out["pass"] is True and out["range"] == [V.START, V.END]
    for root in ("NQ", "ES"):
        g = out["roots"][root]
        assert [(x["family"], x["tf"]) for x in g["runs"]] == [(f, tf) for f in FAMS for tf in TFS]
        for x in g["runs"]:                                            # 100 %: every field of every trade
            assert x["pass"] and x["n_sim"] == x["n_ref"] == x["exact_all_fields"] > 0 and x["net_diff"] == 0.0 and x["skips_equal"], x["id"]
        for x in g["grids"]:
            assert x["pass"] and x["cells_identical"] == x["cells"] and x["max_abs_net_diff"] == 0.0 and x["skipped_by_error"] == 0, x["id"]
    assert len(out["roots"]["NQ"]["grids"]) == 9 and len(out["roots"]["ES"]["grids"]) == 6
    assert set(out["variants"]) == set(FAMS) and all(v["pass"] and v["variants"] == families.library(f)["variants"]
                                                     for f, v in out["variants"].items())


# ---- an independent oracle of the first signal of every session (all seven sessions) --------------------------------------
MIN = 60 * S.NS
ON_CUT = {"london": 10800, "pre": 30300, "nyam": 34200, "mid": 34200, "pm": 34200}       # overnight range = 00:00 -> cut


def _world(d, seg):
    """1-minute bars of one segment, straight from the prints: minute index relative to 00:00 ET of the trade date
    (negative in the evening), o / h / l / c / v. The evening = the 6 hours before that midnight."""
    tape = S.load_tape(d)
    mid = S.et_ns(dt.date.fromisoformat(d), "00:00")
    t0, t1 = (mid - 6 * 3600 * S.NS, mid) if seg == "eve" else (mid, S.et_ns(dt.date.fromisoformat(d), "16:10"))
    lo, hi = np.searchsorted(tape.ts, [t0, t1])
    ts, px, sz = tape.ts[lo:hi], tape.px[lo:hi], tape.size[lo:hi]
    k = (ts - mid) // MIN
    first = np.flatnonzero(np.r_[True, k[1:] != k[:-1]])
    last = np.r_[first[1:] - 1, len(k) - 1]
    return {"tape": tape, "mid": mid, "m": k[first], "o": px[first], "c": px[last], "h": np.maximum.reduceat(px, first),
            "l": np.minimum.reduceat(px, first), "v": np.add.reduceat(sz, first).astype(np.float64), "m0": -360 if seg == "eve" else 0}


def _prior(d):
    """(high, low, close) of the previous session's whole tape, None on a contract-roll day or the first day."""
    days = [x.isoformat() for x in S.sessions(S.BUILD[0], d)]
    if len(days) < 2:
        return None
    prev, cur = S.load_tape(days[-2]), S.load_tape(d)
    if prev.contract != cur.contract:
        return None
    return float(prev.px.max()), float(prev.px.min()), float(prev.px[-1])


def _first_signal(fam, p, w, sess, tf, pd):
    """The first tf close of session `sess` at which the family may and does enter: (side, close second) | None |
    'skip' (a minute without a print before the session end: the tf closes are then not on the clock)."""
    a, b = S.SESS[sess]
    m, o, h, l, c, v = (w[k] for k in ("m", "o", "h", "l", "c", "v"))
    need = np.arange(w["m0"], b // 60)
    if len(m) < len(need) or not np.array_equal(m[:len(need)], need):
        return "skip"
    q = m // tf                                                    # tf buckets on the ET clock
    cut = np.flatnonzero(np.r_[True, q[1:] != q[:-1]])
    end = np.r_[cut[1:], len(m)]
    O, C = o[cut], c[end - 1]
    H, L = np.maximum.reduceat(h, cut), np.minimum.reduceat(l, cut)
    E = (q[cut] + 1) * tf * 60                                     # close second of each tf bar
    tp = (h + l + c) / 3.0
    ins = (m * 60 >= a) & (m * 60 < b)                             # minutes of the session
    s0, s1, s2 = np.cumsum(np.where(ins, v, 0.0)), np.cumsum(np.where(ins, v * tp, 0.0)), np.cumsum(np.where(ins, v * tp * tp, 0.0))
    tr = np.r_[H[0] - L[0], np.maximum(H[1:] - L[1:], np.maximum(np.abs(H[1:] - C[:-1]), np.abs(L[1:] - C[:-1])))]
    atr = np.empty(len(tr))
    for i in range(len(tr)):
        atr[i] = sum(tr[:i + 1].tolist()) / (i + 1) if i < 14 else (atr[i - 1] * 13.0 + tr[i]) / 14.0     # Wilder ATR(14)
    onr = None
    if sess in ON_CUT:
        on = (m * 60 >= 0) & (m * 60 + 60 <= ON_CUT[sess])
        onr = (float(h[on].max()), float(l[on].min())) if on.any() else None
    idx = [i for i in range(len(E)) if a < E[i] <= b]              # the tf closes that belong to the session
    state = {"sn": 0, "pout": 0, "sides": [], "lv": None}
    if fam == "sweep_rev":
        lv = []
        if p["levels"] != "on" and pd is not None:
            lv += [[pd[0], 1, None, False], [pd[1], -1, None, False]]
        if p["levels"] != "pd" and onr is not None:
            lv += [[onr[0], 1, None, False], [onr[1], -1, None, False]]
        state["lv"] = lv
    for i in idx:
        state["sn"] += 1
        j = end[i] - 1                                             # the last minute of the bar: the session sums up to here
        vw = s1[j] / s0[j] if s0[j] > 0 else None
        sg = float(np.sqrt(max(s2[j] / s0[j] - vw * vw, 0.0))) if vw is not None else None
        side = None
        if fam == "vwap_z":
            if state["sn"] >= 3 and sg:
                z = (C[i] - vw) / sg
                side = "short" if z >= p["zth"] else "long" if z <= -p["zth"] else None
        elif fam == "vwap_band":
            if state["sn"] >= 3 and sg:
                hi_, lo_ = vw + p["band"] * sg, vw - p["band"] * sg
                side = "short" if state["pout"] == 1 and C[i] <= hi_ else "long" if state["pout"] == -1 and C[i] >= lo_ else None
                state["pout"] = 1 if C[i] > hi_ else -1 if C[i] < lo_ else 0
        elif fam == "vwap_flip":
            if vw is not None and C[i] != vw:
                s = state["sides"]
                s.append(1 if C[i] > vw else -1)
                n = p["hold"]                                      # a cross n closes ago, the new side ever since
                if len(s) >= n + 2 and s[-n - 1] != s[-n - 2] and all(x == s[-1] for x in s[-n - 1:]):
                    side = "long" if s[-1] > 0 else "short"
        elif fam == "pinbar":
            rg = H[i] - L[i]
            lv = list(pd or ()) + (list(onr) if onr is not None and sess in ("nyam", "mid", "pm") else []) + ([vw] if vw is not None else [])
            near = lambda x: any(abs(x - z) <= 0.25 * atr[i] for z in lv)       # noqa: E731
            if rg > 0:
                if (min(O[i], C[i]) - L[i]) / rg >= p["wick"] and near(L[i]):
                    side = "long"
                elif (H[i] - max(O[i], C[i])) / rg >= p["wick"] and near(H[i]):
                    side = "short"
        else:
            for r in state["lv"]:
                if r[3]:
                    continue
                if (H[i] > r[0]) if r[1] > 0 else (L[i] < r[0]):
                    r[2] = True
                if r[2] and ((C[i] <= r[0]) if r[1] > 0 else (C[i] >= r[0])):
                    r[3] = True
                    side = side or ("short" if r[1] > 0 else "long")
        if side and i + 1 >= 3 and E[i] < b - 300:                 # 3 tf bars since the restart, not in the last 5 minutes
            return side, int(E[i])
    return None


ORACLE = ([(f, {}, tf) for f in FAMS for tf in TFS]
          + [(f, v, tf) for f in FAMS for v in families.library(f)["variants"] if v != {k: CLS[f].defaults()[k] for k in v} for tf in ("5", "15")])


def test_first_signal_of_every_session_equals_an_independent_oracle_in_all_seven_sessions():
    """max_tr 1: the only trade of a session is its first signal. Expected from the raw prints (minute bars, session VWAP
    and sigma, Wilder ATR, prior-day and overnight levels) without the Template; the entry must be the first print
    85 ms after that tf close, one tick worse."""
    _window()
    specs = [(CLS[f], {**v, "tf": tf, "sess": inst, "max_tr": 1}) for f, v, tf in ORACLE for inst in INST]
    res = S.run_many(specs, days=FULL, workers=1)
    assert all(r["skipped_by_error"] == 0 and not r["skipped"] and not r.get("eve_skipped") for r in res)
    got = {}
    for k, r in enumerate(res):
        f, v, tf = ORACLE[k // 3]
        for t in r["trades"]:
            key = (k // 3, t["date"], S.session_of(t["entry_ms"]))
            inst = INST[k % 3]
            assert key not in got and key[2] in (S.ORDER if inst == "all" else (inst,)), key     # one trade per session, in its instance
            got[key] = t
    worlds = {(d, seg): _world(d, seg) for d in FULL for seg in ("day", "eve")}
    prior = {d: _prior(d) for d in FULL}
    assert prior["2022-06-13"] is None and prior["2022-03-15"] is not None          # the roll day has no prior-day levels
    n = {s: [0, 0, 0] for s in S.ORDER7}                           # per session: checked, expected trades, skipped
    for k, (f, v, tf) in enumerate(ORACLE):
        p = {**CLS[f].defaults(), **v}
        for d in FULL:
            for sess in S.ORDER7:
                w = worlds[(d, "eve" if sess == "eve" else "day")]
                exp = _first_signal(f, p, w, sess, int(tf), prior[d])
                t = got.pop((k, d, sess), None)
                if exp == "skip":
                    n[sess][2] += 1
                    continue
                n[sess][0] += 1
                assert (t is None) == (exp is None), (f, v, tf, d, sess, exp, t and (t["side"], t["entry_ms"]))
                if exp is None:
                    continue
                n[sess][1] += 1
                side, e = exp
                tp = w["tape"]
                i = int(np.searchsorted(tp.ts, w["mid"] + e * S.NS + 85 * 1_000_000, side="left"))
                assert t["side"] == side and t["entry_ms"] == int(tp.ts[i]) // 1_000_000, (f, v, tf, d, sess, exp)
                assert t["entry_price"] == float(tp.px[i]) + (0.25 if side == "long" else -0.25) and t["order_price"] is None
                assert t["date"] == d
                if sess == "eve":                                  # the evening before, booked on the trade date, flat by midnight
                    assert t["entry_ms"] * 1_000_000 < w["mid"] and t["exit_ms"] * 1_000_000 < w["mid"]
                if sess == "pre":
                    assert t["exit_ms"] * 1_000_000 < w["mid"] + (S.SESS["pre"][1] + 60) * S.NS
    assert not got, list(got)[:5]                                  # no trade the oracle did not expect
    for sess in S.ORDER7:                                          # not vacuous: every session checked and traded, few skips
        assert n[sess][0] >= 0.8 * len(ORACLE) * len(FULL) and n[sess][1] >= 20, (sess, n[sess])


def test_sweep_rev_overnight_levels_cannot_trade_where_there_is_no_overnight_range():
    _window()
    res = S.run_many([(P3.SweepRev, {"tf": "5", "levels": "on", "sess": s}) for s in ("eve", "asia", "london", "pre", "nyam")],
                     days=FULL, workers=1)
    assert [bool(r["trades"]) for r in res] == [False, False, True, True, True]
    assert all(r["skipped_by_error"] == 0 for r in res)


# ---- no look-ahead: garbage after a cut time changes nothing before it ------------------------------------------------------
LA_DAYS = ["2022-09-21", "2023-08-09"]
CUTS = [("eve", "20:30:00"), ("day", "04:00:00"), ("day", "09:02:11"), ("day", "10:05:00"), ("day", "12:31:40"), ("day", "14:13:07")]
ENTRY = ("date", "side", "qty", "entry_price", "order_price", "sl", "tp", "entry_ms")


def _garbled(tape, cut_ns, seed):
    k = int(np.searchsorted(tape.ts, cut_ns, side="left"))
    rng = np.random.default_rng(seed)
    px, size = tape.px.copy(), tape.size.copy()
    n = len(px) - k
    px[k:] = np.round((px[k - 1] + 150.0 * rng.choice([-1.0, 1.0]) + np.cumsum(rng.normal(0.0, 6.0, n))) * 4) / 4
    size[k:] = rng.integers(1, 400, n)
    return S.Tape(tape.root, tape.date, tape.contract, tape.ts, px, size)


def test_garbage_after_a_cut_time_changes_no_earlier_entry_and_no_trade_closed_before_it(monkeypatch):
    _window()
    specs = [(CLS[f], {**v, "tf": tf, "sess": inst}) for f in FAMS for v in ({}, families.library(f)["variants"][0])
             for tf in ("1", "5") for inst in INST]
    real_load = S.load_tape
    n_before = n_closed = n_open = n_changed = 0
    for d in LA_DAYS:
        real = S.run_many(specs, days=[d], workers=1)
        for ci, (seg, hms) in enumerate(CUTS):
            day = dt.date.fromisoformat(d)
            cut = S.et_ns(day - dt.timedelta(days=1) if seg == "eve" else day, hms)

            def fake(dd, root="NQ", allow_holdout=False, allow_exam=False, cut=cut, ci=ci):
                return _garbled(real_load(dd, root, allow_holdout=allow_holdout, allow_exam=allow_exam), cut, 100 + ci)
            monkeypatch.setattr(S, "load_tape", fake)
            try:
                bad = S.run_many(specs, days=[d], workers=1)
            finally:
                monkeypatch.setattr(S, "load_tape", real_load)
            cut_ms = cut // 1_000_000
            for a, b in zip(real, bad):
                assert a["skipped_by_error"] == 0 and b["skipped_by_error"] == 0 and not b["skipped"]
                A = [t for t in a["trades"] if t["entry_ms"] < cut_ms]
                B = [t for t in b["trades"] if t["entry_ms"] < cut_ms]
                assert len(A) == len(B), (d, hms, a["meta"]["strategy"], a["meta"]["inputs"])
                for x, y in zip(sorted(A, key=lambda t: t["entry_ms"]), sorted(B, key=lambda t: t["entry_ms"])):
                    assert [x[k] for k in ENTRY] == [y[k] for k in ENTRY]
                    if x["exit_ms"] < cut_ms:
                        assert x == y                              # closed before the cut: every field
                        n_closed += 1
                    else:
                        assert y["exit_ms"] >= cut_ms              # still open at the cut: it cannot have closed earlier
                        n_open += 1
                n_before += len(A)
                n_changed += a["trades"] != b["trades"]
    counts = (n_before, n_closed, n_open, n_changed)               # 1742, 1660, 82, 342 of 720 spec runs (2026-10-02)
    assert n_before > 1500 and n_closed > 1400 and n_open > 60, counts       # the comparison is not vacuous ...
    assert n_changed > 300, counts                                 # ... and the garbage did reach the strategies


# ---- worker parity and the smoke -----------------------------------------------------------------------------------------------

def test_identical_trades_at_1_and_8_workers_for_every_family_tf_and_instance():
    _window()
    specs = [(CLS[f], {"tf": tf, "sess": inst}) for f in FAMS for tf in TFS for inst in INST]
    specs += [(CLS[f], {**v, "tf": "5", "sess": "globex"}) for f in FAMS for v in families.library(f)["variants"]]
    a = S.run_many(specs, days=DAYS, workers=1)
    b = S.run_many(specs, days=DAYS, workers=W)
    assert a[0]["meta"]["workers"] == 1 and b[0]["meta"]["workers"] == W and a[0]["sessions"] == b[0]["sessions"] == len(DAYS)
    per = {f: 0 for f in FAMS}
    for (cls, p), x, y in zip(specs, a, b):
        assert x["trades"] == y["trades"], (cls.__name__, p)             # every field of every trade, in order
        assert x["skipped_by_error"] == y["skipped_by_error"] == 0 and x["skipped"] == y["skipped"]
        assert x["both_sides_sessions"] == y["both_sides_sessions"] == 0 and not any(t["oco"] or t["both_sides"] for t in x["trades"])
        assert all(t["order_price"] is None for t in x["trades"])        # market entries only
        if p["sess"] in ("pre", "eve"):
            assert {S.session_of(t["entry_ms"]) for t in x["trades"]} <= {p["sess"]}
        per[next(f for f in FAMS if CLS[f] is cls)] += len(x["trades"])
    assert all(n > 0 for n in per.values()), per


def test_the_three_instances_of_a_cell_are_the_seven_sessions_of_one_globex_run_for_the_stateless_family():
    """vwap_z keeps no state: its all + pre + eve instances must equal ONE globex instance, session by session, except that
    the globex instance tags the 08:25-09:30 minutes as `pre` (same VWAP), so even the NY sessions are identical."""
    _window()
    r = S.run_many([(P3.VwapZ, {"tf": "5", "sess": s}) for s in (*INST, "globex")], days=FULL, workers=1)
    key = lambda t: (t["entry_ms"], t["exit_ms"])                        # noqa: E731
    assert sorted(r[0]["trades"] + r[1]["trades"] + r[2]["trades"], key=key) == sorted(r[3]["trades"], key=key)
    assert len(r[1]["trades"]) > 0 and len(r[2]["trades"]) > 0


@pytest.mark.parametrize("fam,root,tf", [("vwap_band", "NQ", "5"), ("vwap_z", "ES", "15"), ("vwap_flip", "GC", "30"),
                                         ("pinbar", "NQ", "15"), ("sweep_rev", "ES", "5")])
def test_the_counts_only_smoke_is_clean(fam, root, tf):
    _window()
    out = RM.smoke(fam, root, tf, n_days=3, workers=1)
    assert out["ok"] and out["skipped_by_error"] == 0 and out["worker_parity"] and out["both_sides_sessions"] == 0
    assert out["cells"] == len(families.library(fam)["variants"]) * 32 and out["sessions"] == out["days"] == 3
    assert out["trades_total"] > 0 and out["entry_kind"]["resting"] == 0 and out["nulls"] == {}
    assert set(out["by_stop_mode"]) == {"atr", "pts", "pct"} and out["segments"] == ["eve", "day"]
    assert not any(k in out for k in ("net", "pnl", "wr", "pf"))          # counts only
