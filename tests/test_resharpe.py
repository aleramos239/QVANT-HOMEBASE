"""resharpe: a saved run's Sharpe is re-read on its traded days, and nothing else in the file moves."""
from __future__ import annotations

import json
import math

from homebase.backtest import report, resharpe
from homebase.backtest.runner import read_json, write_json
from tests.test_backtest_report import _trade


def test_a_saved_run_gets_the_traded_days_sharpe_and_nothing_else_moves(tmp_path, capsys):
    trades = [_trade("2022-01-03", 300.0), _trade("2022-01-10", -100.0), _trade("2022-01-17", 300.0)]
    rep = report.build(trades)
    rep["summary"]["all"]["sharpe"] = 0.5                     # as a $0-day grid wrote it
    rep["summary"]["all"]["sharpe_traded_days"] = 9.9
    rep["by_year"][0]["sharpe"] = 0.5
    d = tmp_path / "runs" / "r1"
    d.mkdir(parents=True)
    write_json(d / "run.json", {"finished": "x", "label": "kept", "report": rep})
    write_json(d / "trades.json", report.to_ms(trades))
    before = read_json(d / "run.json")

    resharpe.main([str(tmp_path)])                            # a dry run writes nothing
    assert read_json(d / "run.json") == before
    resharpe.main([str(tmp_path), "--write"])
    assert "wrote 1 files" in capsys.readouterr().out

    after = read_json(d / "run.json")
    traded = [300.0, -100.0, 300.0]
    m = sum(traded) / 3
    sd = math.sqrt(sum((x - m) ** 2 for x in traded) / 2)
    a = after["report"]["summary"]["all"]
    assert a["sharpe"] == after["report"]["by_year"][0]["sharpe"] == m / sd * math.sqrt(252)
    assert "sharpe_traded_days" not in a
    strip = lambda r: json.dumps(resharpe._merge(r, r), sort_keys=True)  # noqa: E731
    del before["report"]["summary"]["all"]["sharpe_traded_days"]
    for k in ("sharpe", "sortino"):
        before["report"]["summary"]["all"][k] = a[k]
    before["report"]["by_year"][0]["sharpe"] = a["sharpe"]
    before["report"]["sharpe_basis"] = after["report"]["sharpe_basis"]
    assert strip(after) == strip(before)


def test_a_file_whose_other_numbers_would_move_is_left_alone():
    assert resharpe._holds({"net": 1.0, "sharpe": 2.0, "note": "old words"}, {"net": 1.0, "sharpe": 3.0, "note": "new", "rr": 1})
    assert not resharpe._holds({"net": 1.0, "sharpe": 2.0}, {"net": 1.5, "sharpe": 3.0})
    assert resharpe._merge({"net": 1.0, "sharpe": 2.0, "sharpe_traded_days": 4.0}, {"net": 1.0, "sharpe": 3.0, "rr": 1}) \
        == {"net": 1.0, "sharpe": 3.0}
