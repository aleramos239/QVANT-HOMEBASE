"""The desk page carries the chart-trading switch + limits, and switching
it ON goes through the confirm dialog before the POST."""
from __future__ import annotations

from pathlib import Path

HTML = (Path(__file__).resolve().parent.parent / "homebase" / "static" / "index.html").read_text()


def test_the_desk_page_has_the_chart_trading_switch_and_limits():
    for needle in ('id="ctSwitch"', 'id="ctState"', 'id="ctMaxOrder"', 'id="ctMaxPos"',
                   'id="ctSave"', 'post("/api/chart-trading"', "renderChartTrading(s.chart_trading)"):
        assert needle in HTML, needle


def test_switching_on_asks_first():
    fn = HTML[HTML.index("async function setChartTrading"):]
    fn = fn[:fn.index("\n}\n")]
    assert fn.index("confirmDlg(") < fn.index('post("/api/chart-trading"')


def test_the_preview_data_carries_chart_trading():
    demo = HTML[HTML.index("function demoStatus()"):]
    assert "chart_trading: {enabled: false, max_order_qty: 10, max_position_qty: 20}" in demo


def _fn(name):
    start = HTML.index(name)
    fn = HTML[start:]
    ends = [i for i in (fn.find("\n}\n"), fn.find("\n};\n")) if i != -1]
    return fn[:min(ends)]


def test_chart_trading_toasts_fall_back_to_r_error():
    """Fix round 1 item 5: the write guard's 403/415 refusals carry `error`,
    not `detail` — both the switch and Save-limits toasts must show it."""
    for fn in (_fn("async function setChartTrading"), _fn("$(\"#ctSave\").onclick")):
        assert "r.detail || r.error" in fn


def test_chart_trading_toasts_survive_post_throwing():
    """A network failure or a non-JSON 500 makes post() throw (fetch itself
    rejects, or r.json() fails to parse) — both handlers must catch it and
    tell the user, not leave an unhandled rejection with no feedback."""
    for fn in (_fn("async function setChartTrading"), _fn("$(\"#ctSave\").onclick")):
        assert "try {" in fn and "catch" in fn
        assert "Couldn't reach the desk" in fn
        # the catch must come after the post() call it's guarding
        assert fn.index('post("/api/chart-trading"') < fn.index("catch")
