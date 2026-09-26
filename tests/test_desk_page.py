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
