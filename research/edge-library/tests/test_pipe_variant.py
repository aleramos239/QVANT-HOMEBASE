"""LOCK of the pipeline's VARIANT MODE (blueprint/pipe_stages.py with pipeline.json "mode": "variant"; the owner, 2026-10-08).

The map gets a LOOSE check and ONE box is picked right after it; every hard rule is judged on that box. What is locked here:

1. the pick: the MIDDLE qualifying box by build net -- never the best; an even count takes the lower of the two middle ones
2. stage 1: the loose check (a tiny real map cannot hold 25 boxes at the floor, so it FAILS by its rows; the pass is canned), the best
   map by qualifying boxes, the pick on the card and in `picked` (cell, variant)
3. stage 2: the price check reads the PICKED box
4. stage 3: no indicator is tried; the picked box's rows P3.2, P3.3, P3.4, P3.6 (the other markets shown)
5. stage 4: the picked box reshuffled; its random entries (the same box of the control pool) held to the bar of the tries
6. stage 5: the toolkit's whole-map build lines (the sides line too) are shown and ask nothing, a code problem is still a code
   problem, and the lock takes the PICKED box as its default (once for real, tiny)
7. an idea whose stage 1 picked no box is refused by the later stages, with the way out (pipe rerun)

Same harness as tests/test_pipe_stages.py and tests/test_pipe_finish.py: tiny REAL runs (3 named build days, 2 exit cells, 1 worker) in
temp folders of this file's own; the gates that need 25 boxes are canned. No day from 2025-07-01 on is opened.

  pytest tests/test_pipe_variant.py -q
"""
from __future__ import annotations

import copy
import sys
import tempfile
from pathlib import Path

import pytest

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import judge as J  # noqa: E402
import l2sim as S  # noqa: E402
import run_menus as RM  # noqa: E402
import test_blueprint_ideas as TI  # noqa: E402
import test_pipe_end_to_end as TE  # noqa: E402
import test_pipe_finish as TF  # noqa: E402
import test_pipe_stages as TS  # noqa: E402
from blueprint import api  # noqa: E402
from blueprint import freeze as FRZ  # noqa: E402
from blueprint import pipe_card as PC  # noqa: E402
from blueprint import pipe_gates as G  # noqa: E402
from blueprint import pipe_rules as PR  # noqa: E402
from blueprint import pipe_stages as ST  # noqa: E402
from blueprint import pipe_store as PS  # noqa: E402
from blueprint import records as REC  # noqa: E402
from blueprint import rules as R  # noqa: E402
from blueprint import runner as RUN  # noqa: E402
from blueprint import tables as T  # noqa: E402

NAME = "pvt_orb"
A1, A5 = f"{NAME}_a1", f"{NAME}_a5"
HOME = f"{A5}-NQ-tf5"
_T: dict = {"keep": tempfile.TemporaryDirectory(prefix="pipe_variant_")}
D = Path(_T["keep"].name).resolve()
ROOT, POOLS = D / "pipe", D / "pools"
TINY = {"days": TI.DAYS, "cells": TI.CELLS, "workers": 1, "draws": 200}
CTX = {"root": ROOT, "tiny": TINY}
_DONE: dict = {}


@pytest.fixture(autouse=True)
def world(monkeypatch):
    """Temp folders for all the toolkit writes, an empty pools folder to link from, a Saturday, VARIANT MODE."""
    TI.setup_function()
    POOLS.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(PS, "pools", lambda: POOLS)
    monkeypatch.setattr(RUN, "clock", lambda: TI.SAT)
    monkeypatch.setattr(RM, "auto_workers", lambda n=None: n)
    monkeypatch.setattr(PR, "mode", lambda: "variant")
    yield monkeypatch
    TI.teardown_function()


# ---------------------------------------------------------------- the runner's part, played by the tests

def add(name: str = NAME, max_tr: int | None = None) -> str:
    if name not in _DONE:
        way = {**TS.CARD["ways"][0], **({"limits": {"max_tr": max_tr}} if max_tr else {})}
        card = {**copy.deepcopy(TS.CARD), "name": name, "ways": [way]}
        PS.add(card, PC.check(card)[1], ROOT, sig=PC.signature(card), family=PC.family_of(card))
        _DONE[name] = True
    return name


def ran(n: int, card: dict, name: str = NAME) -> dict:
    PS.write_stage(name, n, card, ROOT)
    return card


def zero(name: str = NAME) -> dict:
    return ran(0, ST.stage0(add(name), CTX), name)


def qualify(mp, five=None, one=0) -> None:
    """G.variant_map answers by bar size: the 5-minute map passes with `five` boxes at the floor (None = all of its boxes), the 1-minute one with `one`
    (0 = it fails). The cells are the first ones of each table. The rows are the real gate's."""
    real = G.variant_map

    def canned(t):
        r = real(t)
        k = len(t["ids"]) if (five is None and t["_u"]["tf"] == "5") else five if t["_u"]["tf"] == "5" else one
        cells = list(t["ids"])[:k]
        return {**r, "result": "pass" if k else "fail", "qualifying": k, "cells": cells}
    mp.setattr(G, "variant_map", canned)


def first(mp, **kw) -> dict:
    """Stage 0 and stage 1 (variant mode, the map check canned) on file -> the card of stage 1."""
    zero()
    qualify(mp, **kw)
    return ran(1, ST.stage1(NAME, CTX))


def table_rows() -> tuple:
    """The 5-minute home table as the judge reads it -> (its rows, its judged ids)."""
    st = J.store({"dir": ROOT / "runs", "key": HOME})
    u = T.bp_unit({"name": A5, "family": "orb"}, "NQ", "5", "nyam")
    rows = J.table(st, u)
    return rows, J.table_stats(rows)["ids"]


def by_hand_middle(rows: list, cells: list) -> str:
    order = sorted((r for r in rows if r["id"] in cells), key=lambda r: (round(r["net"], 2), r["vi"], r["xi"]))
    return order[(len(order) - 1) // 2]["id"]


# ================================================================ 1. the pick

def test_the_pick_is_the_middle_box_by_build_net_never_the_best():
    rows = [{"id": f"c{i}", "net": n, "vi": v, "xi": x} for i, (n, v, x) in enumerate([(500.0, 0, 0), (100.0, 0, 1), (300.0, 1, 0), (200.0, 1, 1), (400.0, 2, 0)])]
    assert ST._middle(rows, [r["id"] for r in rows]) == "c2"                                   # 100 200 300 400 500: the middle one, 300
    assert ST._middle(rows, ["c0", "c1", "c3", "c4"]) == "c3"                                  # 100 200 400 500: an even count takes the LOWER middle, 200 (never 400)
    assert ST._middle(rows, ["c0"]) == "c0" and ST._middle(rows, ["c0", "c2"]) == "c2" and ST._middle(rows, []) is None
    best = max(rows, key=lambda r: r["net"])["id"]
    assert all(ST._middle(rows, c) != best for c in (["c0", "c1", "c2"], ["c0", "c3"], ["c0", "c1", "c2", "c3", "c4"]))      # never the best
    tie = [{"id": "t0", "net": 50.004, "vi": 1, "xi": 0}, {"id": "t1", "net": 50.0, "vi": 0, "xi": 1}, {"id": "t2", "net": 50.0, "vi": 0, "xi": 0}]
    assert ST._middle(tie, ["t0", "t1", "t2"]) == "t1"                                         # the judge's tie rule: by net to the cent, then by variant order
    order_ = ST._middle(rows, [r["id"] for r in rows])
    assert order_ == REC.middle(rows, [r["id"] for r in rows])[0]                              # (the toolkit's own middle survivor, when every box is profitable)


def test_a_card_without_a_picked_box_is_refused_by_the_later_stages_with_the_way_out(world):
    """An idea whose stage 1 ran before variant mode (or in map mode) has no `cell`: its stages 2-5 do not guess one."""
    zero()
    TS.raw(world, b1=("fail", None), b5=("low", 40.0))
    with world.context() as m:
        m.setattr(PR, "mode", lambda: "map")
        ran(1, ST.stage1(NAME, CTX))                                                           # a stage 1 of the old kind
    for stage in (ST.stage2, ST.stage3, ST.stage4):
        if stage is ST.stage4:
            ran(3, {**PS.stages(NAME, ROOT)[1], "stage": 3})
        if stage is ST.stage3:
            ran(2, {**PS.stages(NAME, ROOT)[1], "stage": 2})
        with pytest.raises(J.Refuse) as e:
            stage(NAME, CTX)
        assert "picked no box" in str(e.value) and "bp.py pipe rerun" in str(e.value), stage.__name__


# ================================================================ 2. stage 1

def test_stage_1_in_variant_mode_fails_a_tiny_map_by_its_two_rows():
    """The real gate on 3 days: far fewer than 25 boxes at the floor, so the loose check says so, with the rows -- and nothing is picked."""
    zero()
    c = TS.whole(ST.stage1(NAME, CTX), 1)
    assert (c["passed"], c["result"], c["picked"], c["tries"]) == (False, "fail", None, 2) and "code_problem" not in c
    assert TS.lines(c) == ["P1.1", "P1.2"] * 2 and [x["sub"] for x in c["lines"]] == [A1] * 2 + [A5] * 2
    assert c["rules"] == {"mode": "variant", "variant": PR.need("variant"), "floor": 70}
    bad = [x for x in c["lines"] if x["passed"] is False]
    assert bad and all(x["text"].startswith(f"{A5}: P1.") or x["text"].startswith(f"{A1}: P1.") for x in c["lines"]) and "FAIL" in bad[0]["text"]
    assert "every one of the 2 heat maps failed the loose check of the map" in c["text"] and [t["qualifying"] for t in c["tables"]] == [0, 0]


def test_stage_1_picks_the_middle_qualifying_box_and_writes_it_into_the_card(world):
    c = TS.whole(first(world), 1)
    rows, ids = table_rows()
    cell = by_hand_middle(rows, ids)
    assert (c["passed"], c["result"], c["tries"]) == (True, "pass", 2)                         # one level: "pass", no strict / low
    assert c["picked"] == {"sub": A5, "bar": "5", "way": 0, "filter": None, "cell": cell, "variant": c["box"]["variant"]}
    vi = next(r for r in rows if r["id"] == cell)["vi"]
    assert c["box"]["cell"] == cell and c["box"]["variant"] == J.store({"dir": ROOT / "runs", "key": HOME})["meta"]["cells"][[r["id"] for r in rows].index(cell)]["variant"][c["box"]["setting"]]
    assert vi in (0, 1, 2) and c["box"]["qualifying"] == len(ids) and c["box"]["trades"] >= 0
    st = J.store({"dir": ROOT / "runs", "key": HOME})
    x = J.cellx(st, cell, "nyam")
    up = x["side"] > 0
    assert c["box"]["trades"] == len(x["net"]) and c["box"]["net"] == pytest.approx(float(x["net"].sum()))
    assert c["box"]["long"] == pytest.approx(float(x["net"][up].sum())) and c["box"]["short"] == pytest.approx(float(x["net"][~up].sum()))
    assert f"THE PICK: box {cell}" in c["text"] and "never the best" in c["text"] and c["text"].startswith(f"{A5} moves on")
    assert [(t["sub"], t["bar"], t["result"], t["qualifying"]) for t in c["tables"]] == [(A1, "1", "fail", 0), (A5, "5", "pass", len(ids))]
    assert c["rules"] == {"mode": "variant", "variant": PR.need("variant"), "floor": 70}
    assert TS.lines(c) == ["P1.1", "P1.2"] * 2


def test_stage_1_takes_the_map_with_more_qualifying_boxes(world):
    zero()
    qualify(world, five=3, one=4)                                                              # the 1-minute map has more boxes at the floor
    c = ST.stage1(NAME, CTX)
    assert c["picked"]["sub"] == A1 and c["picked"]["bar"] == "1" and c["picked"]["cell"] and [t["qualifying"] for t in c["tables"]] == [4, 3]
    qualify(world, five=5, one=4)
    assert ST.stage1(NAME, CTX)["picked"]["sub"] == A5


# ================================================================ 3. stage 2

def test_stage_2_reads_the_price_check_of_the_picked_box(world):
    one = first(world)
    cell = one["picked"]["cell"]
    c = TS.whole(ST.stage2(NAME, CTX), 2)
    assert TS.lines(c) == ["1.1", "1.2", "1.3", "1.4", "P2.5"] and c["passed"] is True
    p = c["lines"][4]
    assert p["cell"] == cell and p["text"].startswith(f"P2.5 PASS the picked box ({cell}): every entry and exit price")
    assert c["picked"] == one["picked"] and "the middle box" not in p["text"]


def test_stage_2_refuses_a_picked_box_the_table_no_longer_has(world):
    one = first(world)
    ran(1, {**one, "picked": {**one["picked"], "cell": "no_such_box-r9"}})
    with pytest.raises(J.Refuse) as e:
        ST.stage2(NAME, CTX)
    assert "no_such_box-r9" in str(e.value) and "bp.py pipe rerun" in str(e.value)


# ================================================================ 4. stage 3

def test_stage_3_tries_no_indicator_and_judges_the_picked_box(world):
    one = first(world)
    cell = one["picked"]["cell"]
    calls, rows_in = TS.spy(world), TS.gate(world, "variant_rows")
    world.setattr(G, "indicator", lambda *a: (_ for _ in ()).throw(AssertionError("an indicator was tried in variant mode")))
    seen, real = [], REC.card
    world.setattr(REC, "card", lambda *a, **k: seen.append(a[0]) or real(*a, **k))
    c = TS.whole(ST.stage3(NAME, CTX), 3)
    assert (c["passed"], c["result"], c["picked"], c["tries"]) == (True, "pass", one["picked"], 2) and c["indicators"] == [] and seen == []
    assert TS.lines(c) == ["P3.2", "P3.3", "P3.4", "P3.6"] and "no indicator is tried in variant mode (the card names 1)" in c["text"]
    assert len(calls) == 1 and calls[0]["keys"] == [f"{A5}-ES-tf5", f"{A5}-GC-tf5"]           # the other markets' stores are still run: the build reads them
    (b, others), = rows_in
    assert b["ids"] == [cell] and b["net"].shape[0] == 1 and b["sides"] == "both" and len(others) == 2          # the picked box alone
    assert c["rules"] == {"mode": "variant", "variant": PR.need("variant"), "floor": 70, "2.6": R.need("2.6")}
    assert "the other markets are shown, not asked" in c["text"]


def test_stage_3_a_picked_box_that_misses_a_row_stops_the_idea_with_its_line(world):
    one = first(world)
    c = TS.whole(ST.stage3(NAME, CTX), 3)                                                      # the real rows on 3 days: far under 200 trades
    assert c["passed"] is False and c["result"] == "fail" and "code_problem" not in c and TS.lines(c) == ["P3.2", "P3.3", "P3.4", "P3.6"]
    assert c["lines"][1]["passed"] is False and c["lines"][1]["text"].startswith("P3.3 FAIL ") and c["lines"][3]["passed"] is None
    assert f"the picked box {one['picked']['cell']} fails" in c["text"] and "P3.3" in c["text"]
    assert c["picked"] == one["picked"] and c["tries"] == 2


# ================================================================ 5. stage 4

def three(mp) -> dict:
    first(mp)
    TS.gate(mp, "variant_rows")
    return ran(3, ST.stage3(NAME, CTX))


def test_stage_4_runs_no_pool_when_the_picked_boxs_reshuffled_runs_fail(world):
    t3 = three(world)
    calls, shuffled = TS.spy(world), TS.gate(world, "reshuffle_box", fail=("P4.1",))
    world.setattr(G, "random", lambda *a: (_ for _ in ()).throw(AssertionError("the random entries were read")))
    world.setattr(G, "reshuffle", lambda *a: (_ for _ in ()).throw(AssertionError("the whole map was reshuffled in variant mode")))
    c = TS.whole(ST.stage4(NAME, CTX), 4)
    assert (c["passed"], c["result"], c["picked"], c["tries"]) == (False, "fail", t3["picked"], 2) and TS.lines(c) == ["P4.1"] and calls == []
    assert f"the reshuffled runs of the picked box {t3['picked']['cell']} do not hold" in c["text"]
    (b,), = shuffled
    assert b["ids"] == [t3["picked"]["cell"]] and c["rules"]["mode"] == "variant" and c["rules"]["random_bar"] == PR.random_bar(2)


def test_stage_4_holds_the_same_box_of_the_random_entries_to_the_bar_of_the_tries(world):
    t3 = three(world)
    cell = t3["picked"]["cell"]
    calls, draws = TS.spy(world), J.RULE["draws"]
    TS.gate(world, "reshuffle_box")
    beat = TS.gate(world, "random")
    c = TS.whole(ST.stage4(NAME, CTX), 4)
    assert (c["passed"], c["result"], c["tries"]) == (True, "pass", 2) and TS.lines(c) == ["P4.1", "P4.2"] and c["text"].startswith(f"the proof holds for the picked box {cell}")
    assert len(calls) == 1 and calls[0]["stage"] == "pools" and calls[0]["keys"] == ["c1-NQ-tf5"]
    (p_beat, tries, what), = beat
    assert tries == 2 and what == "random-entry runs of the same box" and 0.0 <= p_beat <= 1.0 and J.RULE["draws"] == draws
    # the share is the judge's own c1 draws for THAT ONE BOX: the pool of its exit cell, its days, the table's draw seed
    kw = ST._kw(NAME, CTX)
    spec, plan, specs = ST._idea(A5, kw)
    tab = T.built(specs[0], plan["home"]["table"], None, kw["out"], kw["days"], 1, control=False)
    need = sorted({i.rsplit("_", 1)[-1] for i in tab["ids"]})
    pool = T.pool_seeds(kw["out"], RUN.pool_key("NQ", "5", specs[0]["exits"]), need, R.template("control")["seeds"])
    with ST._draws(200):
        ctl = J.c1_table(tab["_st"], tab["_u"], [cell], pool, J.seed_of(tab["_u"]["uid"], f"{RUN.PERIOD}-c1"))
    mine = float(tab["net"][tab["ids"].index(cell)].sum())
    assert p_beat == round(float((mine > ctl["draws"]).mean()), 4) and c["lines"][1]["replicates"] == 200 == ctl["replicates"]
    with pytest.raises(J.Refuse, match="no judged variant"):
        T.built(specs[0], plan["home"]["table"], None, kw["out"], kw["days"], 1, control=True, box="nobody-r1")
    with TI.no_engine():                                                                       # the pool is there: read, never run twice
        TS.gate(world, "random", fail=("P4.2",))
        c = TS.whole(ST.stage4(NAME, CTX), 4)
    assert c["passed"] is False and c["text"].startswith(f"the proof fails for the picked box {cell}: P4.2") and "code_problem" not in c


# ================================================================ 6. stage 5

FNAME = "pvt_fin"                                       # the card the canned stage 5 tests work on


def four(mp) -> dict:
    """Stages 0-1 for real (variant), 3 and 4 by hand, on a card of its own: the toolkit's commands then answer canned."""
    name = FNAME
    add(name, 3)
    zero(name)
    qualify(mp)
    one = ran(1, ST.stage1(name, CTX), name)
    rows = [{"line": f"P3.{i}", "passed": True, "number": 1.0, "need": 0, "text": f"P3.{i} PASS by hand"} for i in (2, 3, 4)]
    ran(3, TF.hand(3, one["picked"], 2, rows), name)
    ran(4, TF.hand(4, one["picked"], 2, [{"line": f"P4.{i}", "passed": True, "number": 0.99, "need": 0.95, "text": f"P4.{i} PASS by hand"} for i in (1, 2)]), name)
    return PS.stages(name, ROOT)[4]


def test_stage_5_shows_the_whole_map_lines_and_the_lock_takes_the_picked_box(world):
    f4 = four(world)
    name, cell = FNAME, f4["picked"]["cell"]
    ok = J.Refuse("a job of the idea is still running")                                        # the lock's own word goes up: all that is asked here is how it was called
    calls = TF.fakes(world, build=("2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.8"), lock=ok)
    with pytest.raises(J.Refuse, match="still running"):
        ST.stage5(name, CTX)
    (k,), (b,) = calls["lock"], calls["build"]
    assert k["waive"] == ST.WHOLE == ("2.1", "2.2", "2.3", "2.4", "2.5", "2.6", "2.8") and k["default"] == cell and b["name"] == f"{name}_a5"
    calls = TF.fakes(world, lock=ok)                                                           # nothing failed: the lock is still told which lines are not asked, and the pick
    with pytest.raises(J.Refuse, match="still running"):
        ST.stage5(name, CTX)
    assert calls["lock"][0]["default"] == cell and calls["lock"][0]["waive"] == ST.WHOLE
    world.setattr(G, "others_bar", lambda: 0.5)                                                # if the other markets ever get a bar again, 2.5 is asked in variant mode too
    calls = TF.fakes(world, lock=ok)
    with pytest.raises(J.Refuse, match="still running"):
        ST.stage5(name, CTX)
    assert calls["lock"][0]["waive"] == ST.WHOLE


def test_stage_5_the_sides_line_of_the_whole_table_is_shown_and_asks_nothing(world):
    """The owner, 2026-10-08: the hard rules are the picked variant's; the sides of the PICKED box are P3.4, the whole table's 2.6 only shows."""
    four(world)
    name = FNAME
    stop = J.Refuse("a job of the idea is still running")                  # the lock's own word goes up: all that is asked is how it was called
    calls = TF.fakes(world, build=("2.1", "2.6"), lock=stop)
    with pytest.raises(J.Refuse, match="still running"):
        ST.stage5(name, CTX)
    assert len(calls["lock"]) == 1 and "2.6" in calls["lock"][0]["waive"] and "2.1" in calls["lock"][0]["waive"]
    calls = TF.fakes(world, build=("2.7",))                                  # a line the variant mode does not read is still a code problem
    c = TS.whole(ST.stage5(name, CTX), 5)
    assert c["code_problem"] is True and calls["lock"] == []


def test_stage_5_any_other_false_line_is_still_a_code_problem(world):
    four(world)
    name = FNAME
    calls = TF.fakes(world, build=("2.1", "2.9", "2.7"))
    c = TS.whole(ST.stage5(name, CTX), 5)
    assert (c["passed"], c["result"]) == (False, "fail") and c["code_problem"] is True and calls["lock"] == []
    assert "fails 2.7, 2.9" in c["text"] and "2.1 FAIL" not in c["text"].split("a line no gate")[0]
    calls = TF.fakes(world, check=("1.3",))                                                    # the code check is as it was
    c = ST.stage5(name, CTX)
    assert c["code_problem"] is True and calls["build"] == [] and c["text"].startswith("CODE PROBLEM (")


def test_stage_5_the_locks_refusal_of_the_picked_box_is_the_verdict(world):
    f4 = four(world)
    name, cell = FNAME, f4["picked"]["cell"]
    TF.fakes(world, lock=J.Refuse("the box that the pipeline picked is not a variant that makes money on build AND on build with worse fills"))
    seen = []
    world.setattr(ST, "_box", lambda u, kw, pick=None: seen.append(pick) or (None, []))
    c = TS.whole(ST.stage5(name, CTX), 5)
    assert (c["passed"], c["result"], c["lines"]) == (False, "no box", []) and seen == [cell] and "code_problem" not in c
    assert f"the picked box {cell} of {name}_a5 does not make money with normal AND with worse fills" in c["text"]
    six = [TF.row(k, k != "3.4") for k in TF.BOXL]
    world.setattr(ST, "_box", lambda u, kw, pick=None: (cell, six))
    c = TS.whole(ST.stage5(name, CTX), 5)
    assert (c["result"], c["default"]) == ("box failed", cell) and f"the picked box {cell} of {name}_a5 does not meet 3.4" in c["text"]


def test_stage_5_a_locked_idea_says_the_picked_box(world):
    f4 = four(world)
    name, cell = FNAME, f4["picked"]["cell"]
    home = f"{name}_a5-NQ-tf5"
    lock = {"home": {"folder": str(ROOT / "runs"), "key": home, "session": "nyam", "market": "NQ", "bar": "5"}, "default": cell, "survivors": [cell, "x"], "hash": TF.HASH,
            "box": [TF.row(k, True) for k in TF.BOXL], "waived": ["2.1", "2.5"]}
    TF.fakes(world, lock={"ok": True, "lock": lock, "lines": [TF.row("3.1", True), TF.row("3.2", True), *lock["box"]]})
    c = TS.whole(ST.stage5(name, CTX), 5)
    assert (c["passed"], c["result"]) == (True, "locked") and c["locked"]["default"] == cell and TS.lines(c) == [*TF.BOXL, "P5.9"]
    assert f"is locked: the picked box {cell} (of 2 that make money" in c["text"] and "shown, not asked: 2.1, 2.5" in c["text"]


def test_a_tiny_real_stage_5_locks_the_picked_survivor_and_refuses_a_box_that_is_none(world):
    """Real code check, real build (its lines forced: 3 days prove no edge), real lock. A pick that is no survivor is the lock's own verdict ("no box");
    a pick that is one is the lock's default, and default_rule says the pipeline picked it."""
    name, said = "pvt_real", {**CTX, "tiny": {**TINY, "box": "said", "build_avg_trade": 100.0}}
    add(name, 2)
    zero(name)
    qualify(world)
    one = ran(1, ST.stage1(name, CTX), name)
    TF.chart(world)
    sub, kw = f"{name}_a5", ST._kw(name, CTX)
    d, hand = ROOT / "ideas" / sub, lambda cell: {**one["picked"], "cell": cell}  # noqa: E731

    def picked(cell: str) -> None:
        ran(1, {**one, "picked": hand(cell)}, name)
        ran(3, TF.hand(3, hand(cell), 2), name)
        ran(4, TF.hand(4, hand(cell), 2), name)

    _, plan, specs = ST._idea(sub, kw)
    u = T.bp_unit(specs[0], "NQ", "5", "nyam")
    st, _ = T._open(kw["out"], u["key"])
    T._labels(st, u)
    ids = J.table_stats(J.table(st, u))["ids"]
    # (1) a box that does not make money both ways -- the worse-fills table is not there yet, so the stage's first (refused) lock writes it
    middle = REC.middle
    world.setattr(REC, "middle", lambda rows, ids, worse=None: middle(rows, ids) if worse is None else (None, []))      # (nothing survives)
    picked(one["picked"]["cell"])
    with TI.passing():
        c = TS.whole(ST.stage5(name, said), 5)
    assert (c["passed"], c["result"], c["lines"]) == (False, "no box", []) and "code_problem" not in c and not (d / "lock.json").exists()
    assert f"the picked box {one['picked']['cell']} of {sub} does not make money with normal AND with worse fills" in c["text"]
    world.setattr(REC, "middle", middle)
    # (2) a box the table does not hold is no survivor either: the lock refuses it, and that is the box's verdict
    picked("no_such_box-r9")
    with TI.no_engine():
        c = ST.stage5(name, said)
    assert (c["passed"], c["result"]) == (False, "no box") and "no_such_box-r9" in c["text"] and not (d / "lock.json").exists()
    # (3) the survivor, read off the lock's own two stores: picked, locked, and the lock says so
    wst, _ = T._open(kw["out"], RUN.worse_key(u["key"], "nyam"))
    surv = middle(J.table(st, u), ids, {x: float(J.cellx(wst, x, "nyam", u)["net"].sum()) for x in ids})[1]
    assert surv
    picked(surv[-1])                                                                           # (the last survivor: not the toolkit's middle when there are several)
    with TI.no_engine():
        c = TS.whole(ST.stage5(name, said), 5)
    lock = TI.read(d / "lock.json")
    assert (c["passed"], c["result"]) == (True, "locked") and c["locked"]["default"] == surv[-1] == lock["default"] and lock["survivors"] == surv
    assert "picked by the pipeline" in lock["default_rule"] and lock["default_rule"] != J.TIE_RULE and FRZ.verify(lock, TI.read(d / "spec.json")) == []
    assert f"the picked box {surv[-1]} (of {len(surv)} that make money" in c["text"]
    # (4) and on: the unseen days are read once for that lock (two named test days, the read's lines forced -- tests/test_pipe_end_to_end.py's way), then the book card
    if not (hasattr(S, "ALLOW_BT") and all(S.tape_path(d, "NQ").exists() for d in TE.TEST_DAYS)):
        pytest.skip("the read of the unseen days needs the engine's test switch and the NQ tapes of " + ", ".join(TE.TEST_DAYS))
    ran(5, c, name)
    TE.proven(world)
    ctx6 = {"root": ROOT, "tiny": {**said["tiny"], "test_days": TE.TEST_DAYS}}
    c6 = TS.whole(ST.stage6(name, ctx6), 6)
    ran(6, c6, name)
    c7 = TS.whole(ST.stage7(name, ctx6), 7)
    assert c6["passed"] is True and c6["picked"]["cell"] == surv[-1] and c7["picked"]["cell"] == surv[-1]
    assert c7["book"]["rule"]["default"] == surv[-1] == lock["default"] and c7["book"]["rule"]["lock"] == lock["hash"] and surv[-1] in c7["text"]
