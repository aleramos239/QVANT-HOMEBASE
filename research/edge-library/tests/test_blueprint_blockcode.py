"""LOCK of `bp.py blockcode` (blueprint/blockcode.py): the toolkit's blocks as a browsable list, each with the code that implements it
-- the Lab's Toolkit view.

(a) THE LIST IS THE BLOCK LIST: every family and filter block of `bp.py blocks` is in it, grouped, with its plain words, markets and whether it runs.
(b) EVERY BLOCK HAS ITS CODE, FOUND IN THE ENGINE'S SOURCE, NOT TYPED: each filter block has its FILTERS entry, its words, the check in
    `Blocks.allowed` and the engine functions that check calls; the owner's six range blocks end in zones.pdz_range / zones.ote_range.
(c) A SOURCE IS THE FILE'S OWN LINES: file, line range and text are the same as on disk.
(d) THE COMMAND: `bp.py blockcode --json` is one object with the toolkit's contract.

  pytest tests/test_blueprint_blockcode.py -q          python tests/test_blueprint_blockcode.py     the same, one line per test
"""
from __future__ import annotations

import contextlib
import io
import json
import sys
from pathlib import Path

W = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(W), str(Path(__file__).resolve().parent)]
from blueprint import blockcode as BC  # noqa: E402
from blueprint import blocklist as BL  # noqa: E402
from blueprint import cli as C  # noqa: E402

R = BC.toolkit()
G = {g["id"]: g for g in R["groups"]}
ITEMS = {i["id"]: i for g in R["groups"] for i in g["items"]}
B = BL.blocks()["blocks"]


def labels(item) -> list:
    return [p["label"] for p in item["parts"]]


def files(item) -> list:
    return [R["sources"][p["src"]]["file"].rsplit("/", 1)[-1] for p in item["parts"]]


def test_every_family_and_filter_block_of_the_list_is_here_with_its_words_markets_and_status():
    assert [i["name"] for i in G["families"]["items"]] == [f["name"] for f in B["families"]]
    assert sorted(i["name"] for i in G["filters"]["items"]) == sorted({f["block"] for f in B["filters"]})
    for i in ITEMS.values():
        assert i["words"] and isinstance(i["runs"], bool) and isinstance(i["markets"], list) and i["parts"], i["id"]
    for g in R["groups"]:
        assert g["title"] and g["words"] and g["items"], g["id"]
    for f in G["filters"]["items"]:                                       # both sides, each with its own words
        assert [s["side"] for s in f["sides"]] == [x["side"] for x in B["filters"] if x["block"] == f["name"]]
    assert ITEMS["filter:pdz_move"]["markets"] == ["NQ"] and ITEMS["filter:vwap"]["markets"] == ["NQ", "ES", "GC"]


def test_the_six_range_blocks_are_in_it_with_the_code_that_makes_them():
    for k in ("move", "swing", "leg"):
        pdz, ote = ITEMS[f"filter:pdz_{k}"], ITEMS[f"filter:ote_{k}"]
        assert any(x.startswith("zones.pdz_range") for x in labels(pdz)) and any(x.startswith("zones.ote_range") for x in labels(ote)), k
        assert "zones.range_of (called by the above)" in labels(pdz)        # the second level: what the range function calls
        for it, mine, other in ((pdz, "pdz_range", "ote_range"), (ote, "ote_range", "pdz_range")):
            assert any(x.startswith("The check") for x in labels(it)) and "blocks.py" in files(it)
            check = next(R["sources"][p["src"]]["code"] for p in it["parts"] if p["label"].startswith("The check"))
            assert mine in check and other not in check, it["id"]          # the loop over RG.KINDS holds both: each block gets only its own `if`


def test_every_filter_has_its_registration_its_words_and_its_check():
    for it in G["filters"]["items"]:
        ls = labels(it)
        assert ls[0].startswith("Registered") and any(x.startswith("Its words") for x in ls), it["id"]
        assert any(x.startswith("The check") for x in ls), it["id"]
    # a loop over blocks, a block of the simulator's own, a block whose function sits in another module
    assert any("LINE_BLOCKS" in R["sources"][p["src"]]["code"] for p in ITEMS["filter:ema20"]["parts"])
    assert "l2sim.py" in files(ITEMS["filter:book"]) and "indicators.py" in files(ITEMS["filter:bbw"])
    assert "levels.py" in files(ITEMS["filter:level"])


def test_a_family_shows_its_class_its_registration_and_the_other_parts_have_their_files():
    orb = ITEMS["family:orb"]
    assert labels(orb)[0].startswith("The family: class Orb") and any("FAMILIES" in x for x in labels(orb)) and any("HEIGHTS" in x for x in labels(orb))
    for f in B["families"]:
        assert ITEMS[f"family:{f['name']}"]["parts"][0]["label"].startswith("The family"), f["name"]
    assert "exit_menu.json" in files(ITEMS["exit:stops"]) and "rules.py" in files(ITEMS["exit:stops"])
    assert "ranges.json" in files(ITEMS["days:test"]) and "costs.json" in files(ITEMS["market:NQ"])


def test_the_library_families_that_are_no_blueprint_blocks_and_the_engines_helpers_are_listed_too():
    import run_menus as RM
    reg = RM.registry()
    assert sorted(i["name"] for i in G["other"]["items"]) == B["other_families"]
    assert len(G["families"]["items"]) + len(G["other"]["items"]) == len(reg.REGISTRY), "every family of the library is in the list"
    for i in G["other"]["items"]:
        assert i["runs"] is False and i["why_not"] and labels(i)[0].startswith("The family: class"), i["id"]
    helpers = {i["name"] for i in G["helpers"]["items"]}
    assert {"zones.pdz_range", "ranges.leg", "indicators.macd_dir", "levels.nearest", "flowtab.window"} <= helpers


def test_a_source_is_the_files_own_lines():
    assert R["sources"]
    for sid, s in R["sources"].items():
        text = (BC.REPO / s["file"]).read_text(encoding="utf-8").splitlines()
        assert sid == f"{s['file']}:{s['start']}-{s['end']}" and 1 <= s["start"] <= s["end"] <= len(text)
        assert s["code"] == "\n".join(text[s["start"] - 1:s["end"]]), sid
    for it in ITEMS.values():
        assert all(p["src"] in R["sources"] for p in it["parts"]), it["id"]


def test_the_command_prints_one_object_of_the_toolkits_contract():
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = C.main(["blockcode", "--json"])
    r = json.loads(out.getvalue())
    assert code == 0 and r["ok"] is True and r["command"] == "blockcode" and r["counts"] == {g["id"]: len(g["items"]) for g in R["groups"]}
    assert r["groups"] == R["groups"] and r["sources"] == R["sources"] and "THE TOOLKIT" in r["text"]


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"ok  {name}")
