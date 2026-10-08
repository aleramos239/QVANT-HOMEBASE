"""LOCK of the blueprint templates (blueprint/templates/*.json, read by blueprint/rules.py) -- toolkit plan, step 1.

1. rules.json IS BLUEPRINT.md section 2: every numbered line of its tables (0.1 .. 6.8) has an entry, no entry is extra, the
   order is the law's, and each entry's `text` / `number` are that line's cells word for word. The prose quotes of the other
   templates occur in BLUEPRINT.md too (line wrapping aside). AHEAD = the lines that are in force in rules.json and not
   yet in BLUEPRINT.md's text: exactly those may differ, and each MUST still differ (or be new). EMPTY since 2026-10-07: the
   four lines the strategy pipeline changed (3.7, 3.8, 4.6, 4.7) are in the law's text, and the word-for-word lock holds for
   every line again.
2. The machine numbers say what the quoted words say: every number under `need` is found in the entry's own quote, and `op`
   follows the wording ("above" / "more than" = >, "or more" / "at least" = >=, "at most" / "or less" = <=).
3. The exit menu and the costs ARE the engine's: rules.exit_menu(root) == l2sim.menu(root) cell for cell (and the cells of
   run_menus' random-entry pool), the hold and flat times, Costs() defaults, STRESS, the judge's late cancel, SPECS.
4. The templates say one thing: a number two files carry is the same in both, the test days start the day after the build
   days end, and a template that disagrees refuses to load.
Reads BLUEPRINT.md, the templates and engine CODE only: no store, no tape, no simulation. About a second.

  pytest tests/test_blueprint_rules.py -q          python tests/test_blueprint_rules.py     the same, one line per test
"""
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
from blueprint import rules as R  # noqa: E402

MD = (W / "BLUEPRINT.md").read_text(encoding="utf-8")
FLAT = " ".join(MD.split())                                  # the law without its line wrapping
MARKETS = ("NQ", "ES", "GC")
WORDS = {0: ("no ",), 1: ("one ",), 3: ("three ",), 0.5: ("half",)}      # numbers the law writes as words
OP_WORDS = {">": ("above", "more than"), ">=": ("or more", "at least"), "<=": ("at most", "or less")}
AHEAD = ()                                # the lines rules.json is ahead of BLUEPRINT.md's text on (module docstring, 1): none
PIPELINE = ("3.7", "3.8", "4.6", "4.7")   # the lines the strategy pipeline changed (80 % of the runs, the best 1 % of days): the law's text since 2026-10-07


def law_lines() -> dict:
    """{line number: [requirement cell, number cell]} (a phase without a number column: one cell) from the tables of section 2."""
    sec = MD[MD.index("## 2. Written requirements for each phase"):MD.index("\n## 3. ")]
    out = {}
    for ln in sec.splitlines():
        m = re.match(r"^\|\s*(\d\.\d)\s*\|", ln)
        if m:
            assert m[1] not in out, f"line {m[1]} is twice in section 2"
            out[m[1]] = [c.strip() for c in ln.strip().strip("|").split("|")][1:]
    return out


def leaves(x) -> list:
    return [v for y in (x.values() if isinstance(x, dict) else x) for v in leaves(y)] if isinstance(x, (dict, list)) else [x]


def said(v, quote: str) -> bool:
    """Is the number `v` in the quoted words? A share may be written in percent (0.6 = "60 %"), a few numbers as words; a
    number counts only as a whole number (20 is not found in 200, 6 not in 60)."""
    q = quote.lower()
    if isinstance(v, str):
        return v.lower() in q
    forms = [f"{round(100 * v, 6):g}"] if 0 < abs(v) < 1 else [f"{v:g}"]
    return any(w in q for w in WORDS.get(v, ())) or any(re.search(rf"(?<![\d.]){re.escape(f)}(?!\d)", q) for f in forms)


# ================================================================ 1. rules.json is section 2, word for word

def test_every_numbered_line_of_section_2_has_its_entry_and_its_quote():
    law = law_lines()
    assert {k[0] for k in law} == set("0123456") and len(law) >= 42, f"section 2 was not parsed: {sorted(law)}"
    assert [k for k in R.lines() if k not in AHEAD or k in law] == list(law) and R.lines() == sorted(R.lines()) and set(AHEAD) <= set(R.lines()), \
        f"rules.json and BLUEPRINT.md section 2 differ: {sorted(set(R.lines()) ^ set(law))}"
    for k in R.lines():
        e, cells = R.rule(k), law.get(k)
        assert set(e) <= {"text", "number", "need", "op", "also", "note"}, f"{k}: unknown keys {sorted(e)}"
        if k in AHEAD:                                          # ahead of the law's text: it must still differ (or be new), else it is no longer ahead
            assert cells is None or [e["text"], e.get("number")] != (cells + [None])[:2], f"{k}: BLUEPRINT.md says what rules.json says now: take it out of AHEAD"
            continue
        assert e["text"] == cells[0] and e["text"] in MD, f"{k}: text is not the law's: {e['text']!r}"
        assert e.get("number") == (cells[1] if len(cells) > 1 else None), f"{k}: number is not the law's: {e.get('number')!r}"
        assert "number" not in e or e["number"] in MD
    assert not set(PIPELINE) & set(AHEAD) and all(law[k] == [R.rule(k)["text"], R.rule(k)["number"]] for k in PIPELINE)     # the pipeline's four lines: cell for cell
    assert [law[k][1] for k in PIPELINE] == ["80 % of the runs or more", "above $0", "above $0", "80 % of the runs or more"] and "best 1 % of days" in law["3.8"][0]
    for bad in ("9.9", "_about", "2"):
        try:
            R.rule(bad)
            raise AssertionError(f"line {bad!r} was answered")
        except R.RuleError:
            pass


def test_the_other_templates_quote_the_law():
    for name in ("exit_menu", "control", "montecarlo"):
        assert " ".join(R.template(name)["text"].split()) in FLAT, f"{name}.json: its text is not in BLUEPRINT.md"
    rg = R.template("ranges")
    for part in ("build", "test", "stored_build"):
        assert rg[part]["text"] in FLAT, f"ranges.json {part}: its text is not in BLUEPRINT.md"
    assert all(p["name"] in R.rule("4.1")["text"] for p in rg["test"]["parts"]), "the two test parts are not line 4.1's"


# ================================================================ 2. the numbers say what the words say

def test_every_number_is_in_its_own_quote_and_op_follows_the_wording():
    n = 0
    for k in R.lines():
        e = R.rule(k)
        quote = e["text"] + " | " + e.get("number", "")
        for v in leaves(e.get("need", [])):
            assert said(v, quote), f"{k}: the number {v!r} is not in its quote {quote!r}"
            n += 1
        if "op" in e:
            assert e["op"] in R.OPS and "need" in e, k
            assert any(w in quote for w in OP_WORDS[e["op"]]), f"{k}: op {e['op']} does not follow the wording {quote!r}"
            assert not any(w in quote for o, ws in OP_WORDS.items() if o != e["op"] for w in ws), f"{k}: the wording fits another op"
    assert n >= 50
    assert not said(20, "200 or more") and not said(0.06, "more than 60 %") and said(0.983, "98.3 %") and said(-0.05, "win rate -5 points")


def test_the_lines_the_build_reads():
    """The numbers lines.py takes for 2.1-2.8, read the way it reads them (a wrong key or type fails here, not in a run)."""
    assert R.need("2.1") == 0.60 and R.meets("2.1", 0.61) and not R.meets("2.1", 0.60)           # more than: strict
    assert [R.need("2.2", m) for m in MARKETS] == [70, 75, 140] == [R.need("4.3", m) for m in MARKETS]
    assert R.meets("2.2", 70.0, "NQ") and not R.meets("2.2", 69.99, "NQ")                          # or more
    assert [R.need("2.3", k) for k in (1, 2, 3, 4, 5)] == [0.95, 0.975, 0.983, 0.9875, 0.99]
    assert R.meets("2.3", 0.9503, 1) and not R.meets("2.3", 0.95, 1) and not R.meets("2.3", 0.96, 2)   # above: strict; by round
    assert R.need("2.4") == 200 and R.meets("2.4", 200) and not R.meets("2.4", 199.9)
    assert R.need("2.5") == 0.5 and R.meets("2.5", 0.5) and not R.meets("2.5", 0.49)
    assert R.need("2.6") == 0 and R.meets("2.6", 0.5) and not R.meets("2.6", 0.0)
    assert R.need("2.8") == 0.75 and R.meets("2.8", 0.75) and R.need("4.7") == 0.80 == R.need("3.7") and R.need("2.9") == 5
    assert R.rule("2.1")["also"]["profitable_above"] == 0 == R.rule("4.7")["also"]["above"] and R.rule("2.8")["also"]["lines"] == ["2.1", "2.2"]
    for line, key in (("2.3", 6), ("2.2", "CL")):               # a round after the fifth, a market without a floor: refused
        try:
            R.need(line, key)
            raise AssertionError(f"{line} answered for {key!r}")
        except R.RuleError:
            pass


# ================================================================ 3. the exit menu and the costs are the engine's

def test_exit_menu_is_the_engines():
    import l2sim as S
    import run_menus as RM
    from blueprint import runner as RUNNER
    RM.registry()
    m = R.template("exit_menu")
    for root in MARKETS:
        mine = R.exit_menu(root)
        from families import blocks
        assert mine == blocks.menu_blueprint(root) == blocks.exits("blueprint", root, "orb"), f"{root}: exit_menu.json is not the engine's blueprint table"
        assert mine[:32] == S.menu(root), f"{root}: the first 32 cells are not l2sim.menu (a store of the old table keeps its cells and their order)"
        assert len(mine) == m["cells"] == 48 and len({S.cell_id(x) for x in mine}) == 48
        assert [x["tgt_r"] for x in mine[32:34]] == m["small_targets_r"] == list(blocks.BP_TGT_R) == [0.5, 0.75] and {x["tgt_r"] for x in mine[32:]} == {0.5, 0.75}
        assert [(x["stop_mode"], x["stop_val"]) for x in mine[32::2]] == [(x["stop_mode"], x["stop_val"]) for x in S.menu_stops(root)]
        pool = RUNNER.c1_grid(root, "5")                        # the random-entry pool runs the same 48 cells per seed, run_menus' 32 first
        assert [c["exit"] for c in pool if c["variant"]["seed"] == 1] == mine and pool[:len(RM.c1_grid(root, "5"))] == RM.c1_grid(root, "5")
        assert [c["xi"] for c in pool if c["variant"]["seed"] == 1] == list(range(48)) and len({c["id"] for c in pool}) == len(pool)
    assert set(m["stops"]["pts"]) == set(S.MENU_STOP_PTS) == set(MARKETS)
    assert (m["stops"]["atr"], m["stops"]["pct"], m["targets_r"]) == (list(S.MENU_STOP_ATR), list(S.MENU_STOP_PCT), list(S.MENU_TGT_R))
    assert (m["hold"], m["flat_et"], m["flat_et_half_day"]) == (S.LIBRARY_HOLD, S.DAY_FLAT, S.HALF_DAY_FLAT) and RM.HOLD == m["hold"]
    try:
        R.exit_menu("CL")
        raise AssertionError("a market without a menu was answered")
    except R.RuleError:
        pass


def test_costs_are_the_engines():
    import judge as J
    import l2sim as S
    c = R.template("costs")
    eng = S.Costs()
    assert {k: c["normal"][k] for k in S.Costs.__slots__} == {k: getattr(eng, k) for k in S.Costs.__slots__}, "normal fills are not Costs()"
    assert set(c["normal"]) == set(S.Costs.__slots__) | {"placement_ms"} and c["normal"]["placement_ms"] == S.Strategy.placement_ms
    assert {k: c["worse"][k] for k in S.STRESS} == S.STRESS and c["worse"]["oco_cancel_ms"] == J.OCO_MS, "worse fills are not STRESS + the late cancel"
    assert set(c["worse"]) == set(S.STRESS) | {"oco_cancel_ms", "oco_for"}
    S.Costs(oco_cancel_ms=c["worse"]["oco_cancel_ms"])          # the engine takes it
    assert {r: (v["point_value"], v["tick"]) for r, v in c["contract"].items()} == S.SPECS
    assert c["floor"] == {"NQ": 70, "ES": 75, "GC": 140} == R.need("2.2") == R.need("4.3")
    assert R.need("4.5") == {k: c["worse"][k] for k in ("slip_ticks", "latency_ms", "oco_cancel_ms")}


# ================================================================ 4. the templates say one thing

def test_control_montecarlo_ranges_sizes_idea():
    import judge as J
    import l2sim as S
    import library as LB
    import run_idea as RI
    ctl, mc, rg, sz, idea = (R.template(n) for n in ("control", "montecarlo", "ranges", "sizes", "idea"))
    assert (ctl["seeds"], ctl["draws"], ctl["kind"]) == (10, 4000, "c1") == (J.THIN_BELOW, J.DRAWS, "c1") and J.DRAWS % J.BLOCK == 0
    assert said(ctl["seeds"], ctl["text"]) and "4,000 draws" in ctl["text"]
    assert mc["runs"] == 1000 and "1,000" in mc["text"] and mc["replace"] is True and mc["same_days_for_every_variant"] is True
    assert isinstance(mc["seed"], int) and (mc["build"], mc["test"]) == ({"line": "2.8", "need": 0.75}, {"line": "4.7", "need": 0.80})
    assert (rg["build"]["start"], rg["build"]["end"]) == ("2021-09-22", "2025-06-30") == tuple(d.isoformat() for d in S.BP_BUILD)   # the engine's switch
    assert rg["test"]["start"] == "2025-07-01"
    assert rg["test"]["end"] == "latest" and [(p["start"], p["end"]) for p in rg["test"]["parts"]] == [("2025-07-01", "2025-12-31"), ("2026-01-01", "latest")]
    assert all(said(rg[p]["months"], rg[p]["text"]) for p in ("build", "test", "stored_build")) and rg["build"]["months"] == 45
    stored = (rg["stored_build"]["start"], rg["stored_build"]["end"])
    assert stored == J.PERIODS["build"]["range"] == tuple(d.isoformat() for d in S.BUILD), "stored_build is not the engine's BUILD"
    assert R.need("2.4") * rg["stored_build"]["months"] / rg["build"]["months"] == 120                  # "on pace" on the stored days
    assert sz["steps"] == sorted(set(sz["steps"])) and all(isinstance(s, int) and s > 0 for s in sz["steps"])
    assert sz["stage_a"] == sz["steps"][0] == R.need("6.2")["micros"] and sz["micros_per_contract"] == LB.MICRO_DIV and sz["unit"] == "micros"
    assert set(idea["card"]) == {"why", "loser", "home", "neighbors", "not_here", "main_setting", "sides", "sides_why", "loses_when"}     # plan section 3 + line 0.7
    assert set(idea["card"]["home"]) == {"market", "session", "bar"} and set(idea["_card_lines"]) == set(idea["card"])
    assert set(idea["_card_lines"].values()) == {"0.1", "0.3", "0.4", "0.5", "0.6", "0.7"} <= set(R.lines())             # 0.2 = `run`
    assert set(idea["run"]) == {"family", "params", "fixed", "filters", "exits", "limits"} <= set(RI.KEYS)
    assert idea["run"]["exits"] == R.need("0.2")["exits"] == "standard" and (idea["name"], idea["version"]) == ("", 1)
    assert not any(leaves(idea["card"])) and not any(leaves({k: v for k, v in idea["run"].items() if k != "exits"})), "idea.json is not empty"


def test_templates_that_disagree_do_not_load():
    t = {n: R.template(n) for n in R.NAMES}
    assert R.check(t) == [] and set(R.NAMES) == {p.stem for p in R.T.glob("*.json")} - {"pipeline"}      # (pipeline.json: the pipeline's own, pipe_rules.py)

    def broken(name, path, value, word):
        c = copy.deepcopy(t)
        d = c[name]
        for k in path[:-1]:
            d = d[k]
        d[path[-1]] = value
        bad = R.check(c)
        assert len(bad) == 1 and word in bad[0], f"{name} {path} = {value!r}: {bad}"

    broken("costs", ("floor", "NQ"), 60, "cost floor")
    broken("rules", ("4.3", "need"), {"NQ": 70, "ES": 75, "GC": 100}, "cost floor")
    broken("montecarlo", ("build", "need"), 0.5, "Monte Carlo line 2.8")
    broken("rules", ("4.7", "need"), 0.95, "Monte Carlo line 4.7")
    broken("costs", ("worse", "latency_ms"), 100, "worse fills")
    broken("exit_menu", ("flat_et",), "16:00", "flat time")
    broken("ranges", ("test", "start"), "2025-06-30", "the ranges")          # the test would share a day with the build
    broken("ranges", ("build", "end"), "2025-07-31", "the ranges")
    broken("ranges", ("test", "parts", 1, "start"), "2026-01-02", "the ranges")
    broken("ranges", ("stored_build", "end"), "2025-12-31", "stored build days")
    keep = R.T
    try:                                                        # the loader itself: a folder whose costs.json disagrees raises
        import tempfile
        with tempfile.TemporaryDirectory(dir=Path(__file__).resolve().parent) as tmp:
            for n in R.NAMES:
                d = copy.deepcopy(t[n])
                if n == "costs":
                    d["floor"]["GC"] = 1
                (Path(tmp) / f"{n}.json").write_text(json.dumps(d), encoding="utf-8")
            R.T = Path(tmp)
            R._all.cache_clear()
            try:
                R.template("rules")
                raise AssertionError("templates that disagree were loaded")
            except R.RuleError as e:
                assert "cost floor" in str(e)
    finally:
        R.T = keep
        R._all.cache_clear()
    assert R.need("2.2", "GC") == 140


if __name__ == "__main__":
    import time
    rc = 0
    for name, t in [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]:
        t0 = time.monotonic()
        try:
            t()
            print(f"PASS {name} ({time.monotonic() - t0:.1f} s)", flush=True)
        except AssertionError as e:
            rc = 1
            print(f"FAIL {name}\n{e}", flush=True)
    sys.exit(rc)
