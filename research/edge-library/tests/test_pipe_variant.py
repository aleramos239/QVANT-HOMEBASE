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
BOX_ROWS, HOLDING = ST._box_rows, ST._holding            # the real readings of a box (qualify() cans ST._box_rows for the stages)
REAL_NEED = PR.need


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


SAME = {"eval": 0.0, "payout": 0.0, "size": None, "payout_size": None, "account": {"id": "the-account", "name": "the account"}}


def qualify(mp, five=None, one=0, hold=None, odds=None) -> None:
    """G.variant_map answers by bar size: the 5-minute map passes with `five` boxes at the floor (None = all of its boxes), the 1-minute one with `one`
    (0 = it fails). The cells are the first ones of each table. The rows are the real gate's. THE PICK'S TWO READINGS are canned too (3 build days
    hold no line of a box): a box at the floor holds every line unless `hold` names the boxes that do (the others miss line 3.5), and every box has
    the same prop odds unless `odds` = {box: (eval, payout)} says otherwise -- so with neither the pick is the middle box by build net, the tie rule's."""
    real = G.variant_map
    mp.setattr(ST, "_box_rows", lambda t, c, days=None: [] if hold is None or c in hold else [{"line": "3.5", "passed": False}])
    mp.setattr(ST, "_odds", lambda t, cells, days=None: {c: {**SAME, **dict(zip(("eval", "payout"), (odds or {}).get(c, (0.0, 0.0))))} for c in cells})

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
    assert [(t["sub"], t["bar"], t["result"], t["qualifying"], t["holding"]) for t in c["tables"]] == [(A1, "1", "fail", 0, 0), (A5, "5", "pass", len(ids), len(ids))]
    assert c["rules"] == {"mode": "variant", "variant": PR.need("variant"), "floor": 70}
    assert TS.lines(c) == ["P1.1", "P1.2", "P1.1", "P1.2", "P1.3"]                             # P1.3 only of a map that passed the loose check
    p13 = c["lines"][-1]
    assert (p13["passed"], p13["number"], p13["need"], p13["sub"]) == (True, len(ids), PR.need("variant", "pick_boxes"), A5)
    assert c["box"]["holding"] == len(ids) and c["box"]["odds"] == {"account": "the-account", "eval": 0.0, "payout": 0.0, "size": None, "payout_size": None}


def test_the_pick_is_the_middle_box_by_prop_odds_never_the_best_then_the_tie_rule():
    rows = [{"id": f"c{i}", "net": n, "vi": 0, "xi": i} for i, n in enumerate((500.0, 100.0, 300.0, 200.0, 400.0))]
    odds = {"c0": (0.10, 0.5), "c1": (0.40, 0.1), "c2": (0.20, 0.2), "c3": (0.30, 0.9), "c4": (0.50, 0.0)}
    assert ST._pick(rows, odds) == "c3"                                                        # eval odds .10 .20 .30 .40 .50: the middle one -- not the best net (c0), not the best odds (c4)
    assert ST._pick(rows, {k: odds[k] for k in ("c0", "c1", "c2", "c4")}) == "c2"              # .10 .20 .40 .50: an even count takes the LOWER middle
    assert ST._pick(rows, {"c0": (0.3, 0.1), "c1": (0.3, 0.3), "c2": (0.3, 0.2)}) == "c2"      # equal eval odds: the payout odds decide
    same = {k: (0.0, 0.0) for k in odds}
    assert ST._pick(rows, same) == ST._middle(rows, list(same))                                # equal odds: the judge's tie rule, the middle by build net
    assert ST._pick(rows, {"c1": (0.4, 0.1)}) == "c1" and ST._pick(rows, {}) is None
    assert all(ST._pick(rows, {k: odds[k] for k in ks}) != max(ks, key=lambda k: odds[k]) for ks in (("c0", "c1", "c2"), ("c1", "c4"), tuple(odds)))


def test_stage_1_picks_among_the_boxes_that_hold_every_line_of_a_box_by_their_prop_odds(world):
    """The owner, 2026-10-09: a box at the floor that misses a line of a box is no candidate; of those that hold every line the middle one by the odds
    to pass the eval is picked. Each box's lines are read off its own build trades (_box_rows: stage 3's rows and the lock's 3.3-3.8)."""
    first(world)                                                                               # the stores are on file now
    rows, ids = table_rows()
    a, b, c3 = ids[:3]
    qualify(world, hold=(a, b, c3), odds={a: (0.5, 0.0), b: (0.1, 0.0), c3: (0.3, 0.0)})
    c = TS.whole(ST.stage1(NAME, CTX), 1)
    assert c["passed"] is True and c["picked"]["cell"] == c3 and c["box"]["holding"] == 3 and c["box"]["odds"]["eval"] == 0.3
    assert "the middle, by its odds to pass the eval on the account, of the 3 boxes" in c["text"] and f"(of {len(ids)} at the floor)" in c["text"] and "never the best" in c["text"]
    p13 = c["lines"][-1]
    assert (p13["line"], p13["passed"], p13["number"]) == ("P1.3", True, 3) and p13["missed"] == {"3.5": len(ids) - 3} and f"3.5 by {len(ids) - 3}" in p13["text"]
    qualify(world, hold=(b,))
    c = TS.whole(ST.stage1(NAME, CTX), 1)
    assert c["picked"]["cell"] == b and f"the one box of its {len(ids)} at the floor that holds every line" in c["text"] and "never the best" not in c["text"]


def test_the_lines_of_a_box_are_stage_3s_rows_and_the_locks(world):
    first(world)                                                                               # the stores are on file (the canned readings are not used below)
    _, ids = table_rows()
    kw = ST._kw(NAME, CTX)
    _, plan, specs = ST._idea(A5, kw)
    t = ST._table(specs[0], plan, kw)
    got = BOX_ROWS(t, ids[0], TINY["days"])
    assert [x["line"] for x in got] == ["P3.2", "P3.3", "P3.4", "P3.6", "P3.7", "P3.8", "P3.9", "P3.10", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8"]
    assert [x["text"] for x in got[:8]] == [x["text"] for x in G.variant_rows(ST._one_box(t, ids[0]), [])]                    # stage 3's own rows of that box
    assert [x["text"] for x in got[8:]] == [x["text"] for x in ST._box(t["_u"], kw, ids[0])[1]] if ST._box(t["_u"], kw, ids[0]) else True
    good, missed = HOLDING(t, ids, TINY["days"])
    assert set(good) <= set(ids) and all(v <= len(ids) for v in missed.values()) and sum(missed.values()) >= len(ids) - len(good)


def test_stage_1_takes_the_map_with_more_boxes_that_hold_and_stops_an_idea_with_none(world):
    zero()
    qualify(world, five=5, one=4)
    t1 = lambda t: t["_u"]["tf"] == "1"  # noqa: E731
    world.setattr(ST, "_box_rows", lambda t, c, days=None: [] if t1(t) and c == t["ids"][0] else [{"line": "P3.7", "passed": False}])
    c = TS.whole(ST.stage1(NAME, CTX), 1)                                                      # 1 box holds on the 1-minute map, none on the 5-minute one (which has more at the floor)
    assert c["passed"] is True and c["picked"]["sub"] == A1 and [(t["qualifying"], t["holding"]) for t in c["tables"]] == [(4, 1), (5, 0)]
    world.setattr(ST, "_box_rows", lambda t, c, days=None: [{"line": "P3.7", "passed": False}, {"line": "3.6", "passed": False}] if c == t["ids"][0] else [{"line": "P3.7", "passed": False}])
    c = TS.whole(ST.stage1(NAME, CTX), 1)
    assert (c["passed"], c["result"], c["picked"]) == (False, "fail", None) and "code_problem" not in c
    assert "no heat map has a box to pick" in c["text"] and A5 in c["text"] and "P3.7 by 5, 3.6 by 1" in c["text"] and "the idea is dropped" in c["text"]
    bad = [x for x in c["lines"] if x["line"] == "P1.3"]                                       # (the loose check's own rows are the real gate's on 3 days: canned to pass)
    assert [x["passed"] for x in bad] == [False, False] and bad[0]["need"] == PR.need("variant", "pick_boxes") == 1


def test_stage_1_takes_the_owners_pick_when_it_is_one_of_the_boxes_at_the_floor(world):
    """The owner may name the box (`bp.py pipe pick <name> <cell> --why=TEXT`, 2026-10-09): it must be one of the qualifying boxes of the best map;
    the card says so; with none named the middle box is picked as before; a box that is not at the floor stops the idea with the way out."""
    first(world)                                                                                        # the stores are on file now
    rows, ids = table_rows()
    middle = by_hand_middle(rows, ids)
    other = next(c for c in ids if c != middle)
    PS.set_owner_pick(NAME, other, "the only boxes that passed every build-day line", ROOT)
    c = TS.whole(ran(1, ST.stage1(NAME, CTX)), 1)
    assert c["passed"] is True and c["picked"]["cell"] == other and c["picked"]["by"] == "owner" and c["box"]["cell"] == other
    assert f"THE PICK: box {other} -- chosen by the owner (the only boxes that passed every build-day line)" in c["text"] and "never the best" not in c["text"]
    PS.clear_owner_pick(NAME, ROOT)
    assert TS.whole(ran(1, ST.stage1(NAME, CTX)), 1)["picked"].get("by") is None                       # none named: the middle again
    PS.set_owner_pick(NAME, "not_a_cell", "a box that does not exist", ROOT)
    c = TS.whole(ran(1, ST.stage1(NAME, CTX)), 1)
    assert c["passed"] is False and "not_a_cell" in c["text"] and "not one of the" in c["text"] and "bp.py pipe pick" in c["text"]
    for bad in ("", "  ", None):
        with pytest.raises(J.Refuse, match="why"):
            PS.set_owner_pick(NAME, other, bad, ROOT)
    with pytest.raises(J.Refuse, match="cell"):
        PS.set_owner_pick(NAME, "", "why", ROOT)
    PS.clear_owner_pick(NAME, ROOT)
    assert PS.owner_pick(NAME, ROOT) is None


def test_stage_1_takes_the_map_with_more_qualifying_boxes(world):
    zero()
    qualify(world, five=3, one=4)                                                              # the 1-minute map has more boxes at the floor
    c = ST.stage1(NAME, CTX)
    assert c["picked"]["sub"] == A1 and c["picked"]["bar"] == "1" and c["picked"]["cell"] and [t["qualifying"] for t in c["tables"]] == [4, 3]
    qualify(world, five=5, one=4)
    assert ST.stage1(NAME, CTX)["picked"]["sub"] == A5


def test_boxes_that_never_traded_are_named_with_their_setting_value(world):
    """A value that cannot trade on a bar size (a 160-bar channel on 5-minute bars) leaves its boxes out of the judged map: stage 1 says so."""
    st = {"meta": {"cells": [{"id": "a", "variant": {"n": 40}}, {"id": "b", "variant": {"n": 160}}, {"id": "c", "variant": {"n": 160}}]}, "_idx": {"a": 0, "b": 1, "c": 2}}
    world.setattr(ST.J, "table", lambda st_, u: [{"id": "a", "trades": 5}, {"id": "b", "trades": 0}, {"id": "c", "trades": 0}])
    assert ST._left_out({"_st": st, "_u": {}}) == {"boxes": 2, "values": ["n 160"], "text": "2 of its 3 boxes never traded and are left out (n 160)"}
    world.setattr(ST.J, "table", lambda st_, u: [{"id": k, "trades": 1} for k in "abc"])
    assert ST._left_out({"_st": st, "_u": {}}) is None


# ================================================================ 2b. the next box (the owner, 2026-10-09)

def test_the_boxes_are_tried_from_the_middle_outward_and_the_best_one_last():
    rows = [{"id": f"c{i}", "net": float(i), "vi": 0, "xi": i} for i in range(5)]
    odds = {"c0": (0.10, 0.0), "c1": (0.20, 0.0), "c2": (0.30, 0.0), "c3": (0.40, 0.0), "c4": (0.50, 0.0)}
    assert ST._outward(rows, odds) == ["c2", "c1", "c3", "c0", "c4"]                           # the middle, the next lower, the next higher, ... the best one last
    assert ST._outward(rows, {k: odds[k] for k in ("c0", "c1", "c2", "c3")}) == ["c1", "c0", "c2", "c3"]      # an even count: the lower middle first
    assert ST._outward(rows, {"c3": odds["c3"]}) == ["c3"] and ST._outward(rows, {}) == []
    assert all(ST._pick(rows, {k: odds[k] for k in ks}) == ST._outward(rows, {k: odds[k] for k in ks})[0] for ks in (tuple(odds), ("c0", "c4"), ("c1",)))


def test_stage_1_keeps_every_box_that_holds_as_a_candidate_in_the_order_they_are_tried(world):
    zero()
    qualify(world, five=3, one=2)
    c = TS.whole(ST.stage1(NAME, CTX), 1)
    assert c["picked"]["sub"] == A5 and c["tried"] == [] and [(x["sub"], x["bar"]) for x in c["candidates"]] == [(A5, "5")] * 3 + [(A1, "1")] * 2
    assert c["candidates"][0]["cell"] == c["picked"]["cell"] and len({(x["sub"], x["cell"]) for x in c["candidates"]}) == 5
    assert all(set(x) == {"sub", "bar", "way", "cell", "account", "eval", "payout", "size", "payout_size"} for x in c["candidates"])
    assert "the next of 4 more boxes that hold every line is tried, each one more try of the random bar" in c["text"]
    with world.context() as m:
        m.setattr(PR, "need", lambda *k: 2 if k == ("variant", "box_tries") else REAL_NEED(*k))
        assert "the next of 1 more box that holds every line is tried" in ST.stage1(NAME, CTX)["text"]         # the file's cap on the boxes an idea may try
    qualify(world, five=1, one=0)
    c = ST.stage1(NAME, CTX)
    assert len(c["candidates"]) == 1 and "more box" not in c["text"]
    PS.set_owner_pick(NAME, c["picked"]["cell"], "the owner's own", ROOT)
    assert ST.stage1(NAME, CTX)["candidates"] == []                                            # the owner named the box: no other is tried
    PS.clear_owner_pick(NAME, ROOT)


def test_the_next_box_becomes_the_pick_with_one_more_try_until_none_is_left(world):
    """A stage that says no to the PICKED BOX (stage 4's proof, stage 5's worse fills) does not stop the idea while a box that holds is left."""
    zero()
    qualify(world, five=2, one=1)
    one = ran(1, ST.stage1(NAME, CTX))
    a, b, c3 = one["candidates"]
    failed = {"stage": 4, "passed": False, "next_box": True, "lines": [{"line": "P4.1", "passed": False, "text": "P4.1 FAIL 61 % of the runs"}], "text": "the proof fails"}
    two = ST.next_box(NAME, CTX, failed)
    assert two["picked"] == {"sub": b["sub"], "bar": b["bar"], "way": b["way"], "filter": None, "cell": b["cell"], "variant": two["box"]["variant"]}
    assert two["tries"] == one["tries"] + 1 and two["passed"] is True and two["candidates"] == one["candidates"]
    assert two["tried"] == [{"sub": a["sub"], "cell": a["cell"], "stage": 4, "why": "P4.1 FAIL 61 % of the runs"}]
    assert two["box"]["cell"] == b["cell"] and two["box"]["odds"]["account"] == "the-account" and two["box"]["holding"] == 2
    assert f"THE PICK: box {b['cell']} of {b['sub']} -- box 2 of at most 3" in two["text"] and f"{a['cell']} did not hold at stage 4 (P4.1 FAIL 61 % of the runs)" in two["text"]
    assert f"at the random bar of try {one['tries'] + 1}" in two["text"] and two["text"].startswith(one["text"].split(" THE PICK:")[0])
    ran(1, two)
    three = ST.next_box(NAME, CTX, {**failed, "stage": 5, "lines": [], "text": "the picked box does not make money with worse fills\nmore"})
    assert (three["picked"]["sub"], three["picked"]["cell"], three["tries"]) == (c3["sub"], c3["cell"], one["tries"] + 2)      # the other map's box, after this map's
    assert three["tried"][-1] == {"sub": b["sub"], "cell": b["cell"], "stage": 5, "why": "the picked box does not make money with worse fills"}
    ran(1, three)
    assert ST.next_box(NAME, CTX, failed) is None                                              # none is left: the stage's own verdict stands
    ran(1, one)
    with world.context() as m:
        m.setattr(PR, "need", lambda *k: 1 if k == ("variant", "box_tries") else REAL_NEED(*k))
        assert ST.next_box(NAME, CTX, failed) is None                                          # the cap: one box an idea
    ran(1, {**one, "picked": {**one["picked"], "by": "owner"}})
    assert ST.next_box(NAME, CTX, failed) is None                                              # the owner's pick is not replaced
    ran(1, {k: v for k, v in one.items() if k != "candidates"})
    assert ST.next_box(NAME, CTX, failed) is None                                              # a stage 1 from before this existed
    with world.context() as m:
        m.setattr(PR, "mode", lambda: "map")
        ran(1, one)
        assert ST.next_box(NAME, CTX, failed) is None                                          # map mode has no picked box


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
    assert TS.lines(c) == ["P3.2", "P3.3", "P3.4", "P3.6", "P3.7", "P3.8", "P3.9", "P3.10"] and "no indicator is tried in variant mode (the card names 1)" in c["text"]
    assert len(calls) == 1 and calls[0]["keys"] == [f"{A5}-ES-tf5", f"{A5}-GC-tf5"]           # the other markets' stores are still run: the build reads them
    (b, others), = rows_in
    assert b["ids"] == [cell] and b["net"].shape[0] == 1 and b["sides"] == "both" and len(others) == 2          # the picked box alone
    assert c["rules"] == {"mode": "variant", "variant": PR.need("variant"), "floor": 70, "2.6": R.need("2.6")}
    assert "the other markets are shown, not asked" in c["text"]


def test_stage_3_a_picked_box_that_misses_a_row_stops_the_idea_with_its_line(world):
    one = first(world)
    c = TS.whole(ST.stage3(NAME, CTX), 3)                                                      # the real rows on 3 days: far under 200 trades
    assert c["passed"] is False and c["result"] == "fail" and "code_problem" not in c and TS.lines(c) == ["P3.2", "P3.3", "P3.4", "P3.6", "P3.7", "P3.8", "P3.9", "P3.10"]
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
    assert c["next_box"] is True                                                               # the box's verdict, not the idea's: another box that holds may be tried
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
    assert calls["lock"][0]["waive"] == ("2.1", "2.2", "2.3", "2.4", "2.6", "2.8")


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
    assert c["next_box"] is True
    assert f"the picked box {cell} of {name}_a5 does not make money with normal AND with worse fills" in c["text"]
    six = [TF.row(k, k != "3.4") for k in TF.BOXL]
    world.setattr(ST, "_box", lambda u, kw, pick=None: (cell, six))
    c = TS.whole(ST.stage5(name, CTX), 5)
    assert (c["result"], c["default"]) == ("box failed", cell) and f"the picked box {cell} of {name}_a5 does not meet 3.4" in c["text"]
    assert c["next_box"] is True and "no second box" not in c["text"]


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
