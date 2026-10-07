"""TWO FILTERS ON TOGETHER: the helpers of families/blocks.py (parts, reads, combine, plain, filter_inputs for a combined pair) and the engine's
rule that a combined unit is the AND of its filters. No net, win rate or profit factor is read."""
import pytest

from families import blocks as B
from test_zones import leg_day, run


def test_a_combined_pair_is_one_unit_with_both_filters_inputs():
    c = B.combine([("pdz", "with"), ("ote", "in")])
    assert c == ("ote+pdz", "in+with")                                                         # blocks sorted: the same two filters, the same unit
    assert B.combine([("ote", "in"), ("pdz", "with")]) == c and B.combine([("news", "no")]) == ("news", "no")
    assert B.parts(c) == [("ote", "in"), ("pdz", "with")] == B.parts("ote+pdz_in+with") and B.parts(("news", "no")) == [("news", "no")] and B.parts(None) == []
    assert B.reads(c, ("pdz", "volume")) and not B.reads(c, ("book", "volume")) and B.reads("book_agree", B.L2_BLOCKS) and not B.reads(None, ("pdz",))
    assert B.filter_inputs(*c) == {"f_ote": "in", "f_pdz": "with"} == {**B.filter_inputs("ote", "in"), **B.filter_inputs("pdz", "with")}
    assert B.plain(c) == B.PLAIN[("ote", "in")] + " AND " + B.PLAIN[("pdz", "with")] and B.plain(("news", "no")) == B.PLAIN[("news", "no")]


def test_a_pair_needs_two_different_blocks_known_sides_and_at_most_two_filters():
    for bad in (("news+news", "no+yes"), ("news+momentum+volume", "no+with+high"), ("news+momentum", "no"), ("news+bogus", "no+with"), ("news+momentum", "no+bogus")):
        with pytest.raises(ValueError):
            B.filter_inputs(*bad)
    with pytest.raises(ValueError):                                                            # Level 2 stays NQ only, also inside a pair
        B.filter_inputs("book+news", "agree+no", "ES")
    assert B.filter_inputs("book+news", "agree+no", "NQ") == {"f_book": "on", "f_news": "no"}


@pytest.mark.parametrize("up", [True, False])
def test_a_pair_allows_a_side_exactly_when_both_filters_do(up):
    for px in (14950.0, 14960.0, 15000.0, 15030.0, 15040.0, 15050.0, 15057.0):
        bars = leg_day(px, up)
        a = run({"f_pdz": "with"}, bars)[0][1:]
        b = run({"f_ote": "in"}, bars)[0][1:]
        both = run({"f_pdz": "with", "f_ote": "in"}, bars)[0][1:]
        assert both == (a[0] and b[0], a[1] and b[1]), (px, a, b, both)
