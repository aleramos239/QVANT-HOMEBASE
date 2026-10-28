"""The five new drawing tools (2026-10-28): horizontal ray, fib extension, arrow stamps, price label, range.
The server keeps exactly the points and style fields each takes and refuses everything else."""
import pytest

from homebase.charts.server import check_drawings

PT = {"t": 1_790_000_000_000, "p": 100.5}


def drawing(kind, n, **extra):
    return {"id": "a", "type": kind, "points": [dict(PT, t=PT["t"] + i * 60_000, p=PT["p"] + i) for i in range(n)], **extra}


COUNTS = {"hray": 1, "fibext": 3, "arrowup": 1, "arrowdown": 1, "plabel": 1, "range": 2}


@pytest.mark.parametrize("kind,n", COUNTS.items())
def test_each_new_tool_saves_with_exactly_its_point_count(kind, n):
    out = check_drawings([drawing(kind, n)])
    assert out[0]["type"] == kind and len(out[0]["points"]) == n
    assert all(set(p) == {"t", "p"} for p in out[0]["points"])
    for wrong in (n - 1, n + 1):
        with pytest.raises(ValueError, match="exactly"):
            check_drawings([drawing(kind, wrong)])


@pytest.mark.parametrize("kind,n", COUNTS.items())
def test_new_tool_points_must_be_finite_numbers_and_whole_ms(kind, n):
    for bad in ({"t": PT["t"], "p": float("nan")}, {"t": PT["t"], "p": "1"}, {"t": 1.5, "p": 1.0}, {"t": True, "p": 1.0}, {"p": 1.0}):
        d = drawing(kind, n)
        d["points"][0] = bad
        with pytest.raises(ValueError):
            check_drawings([d])


def test_the_type_message_names_the_new_tools():
    with pytest.raises(ValueError) as e:
        check_drawings([drawing("gann", 2)])
    for kind in COUNTS:
        assert kind in str(e.value)


STYLES = {
    "hray": {"width": 3, "lineStyle": "dashed", "priceLabel": True, "text": "lvl", "fontSize": 14, "textColor": "#FF0000",
             "bold": True, "labelPos": "below"},
    "fibext": {"width": 2, "lineStyle": "dotted", "extendRight": True, "showLevels": True, "showPrices": False, "fill": True,
               "fillOpacity": 20, "fontSize": 12, "levels": [{"v": 1.618, "on": True, "color": "#2962FF"}, {"v": 2.618, "on": False}]},
    "arrowup": {"fontSize": 20},
    "arrowdown": {"fontSize": 28},
    "plabel": {"fontSize": 16, "textColor": "#000000", "bold": True, "fillColor": "rgba(255,255,0,0.5)"},
    "range": {"show": "price"},
}


@pytest.mark.parametrize("kind", COUNTS)
def test_new_tool_style_roundtrips(kind):
    assert check_drawings([drawing(kind, COUNTS[kind], style=STYLES[kind], color="#112233")])[0]["style"] == STYLES[kind]


@pytest.mark.parametrize("kind,bad", [
    ("hray", {"extendLeft": True}), ("hray", {"startCap": "arrow"}), ("hray", {"width": 99}), ("hray", {"labelPos": "top"}),
    ("fibext", {"reverse": True}), ("fibext", {"levels": []}), ("fibext", {"levels": [{"v": 99, "on": True}]}), ("fibext", {"text": "x"}),
    ("arrowup", {"width": 2}), ("arrowup", {"text": "x"}), ("arrowup", {"fontSize": 5}), ("arrowdown", {"fillColor": "#000000"}),
    ("plabel", {"text": "x"}), ("plabel", {"fontSize": "big"}), ("plabel", {"fillColor": "red"}),
    ("range", {"show": "both-ish"}), ("range", {"show": 1}), ("range", {"width": 2}), ("range", {"junk": 1}),
])
def test_new_tool_refuses_a_style_field_it_does_not_take_or_a_bad_value(kind, bad):
    with pytest.raises(ValueError):
        check_drawings([drawing(kind, COUNTS[kind], style=bad)])


@pytest.mark.parametrize("show", ["both", "price", "date"])
def test_range_show_choices(show):
    assert check_drawings([drawing("range", 2, style={"show": show})])[0]["style"] == {"show": show}


def test_only_a_horizontal_line_carries_an_alert_so_a_ray_does_not():
    with pytest.raises(ValueError):
        check_drawings([drawing("hray", 1, alert={"dir": "up", "fired": False})])


def test_junk_input_is_refused():
    for body in ({"type": "hray"}, [None], [[]], [{"id": "a", "type": "hray", "points": "x"}], [{"id": "a", "type": "fibext", "points": [PT]}]):
        with pytest.raises(ValueError):
            check_drawings(body)
    out = check_drawings([{**drawing("range", 2), "qty": 3}])      # qty is for positions only: dropped
    assert "qty" not in out[0]
