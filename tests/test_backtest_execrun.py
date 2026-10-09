"""execrun: a research-engine trade list without prices, priced from the 1-minute bars and written as a tester run."""
from __future__ import annotations

import json

from homebase.backtest import execrun, runner

M = 60_000
T0 = 1_751_554_800_000          # a whole minute, epoch ms


def trade(entry_ms, net, side=1, dur_s=600, date="2025-07-03", reason="tp"):
    return {"date": date, "entry_ms": entry_ms, "dur_s": dur_s, "side": side, "net": net, "reason": reason}


def test_entry_is_the_filled_minutes_open_and_the_exit_follows_the_net():
    opens = {"2025-07-03": {T0: 23000.0, T0 + M: 23010.0}}
    rows = execrun.priced([trade(T0 + 85, 596.0), trade(T0 + M + 200, -604.0, reason="sl"), trade(T0 + 85, 396.0, side=-1)], opens, 20.0)
    long_win, long_loss, short_win = rows
    assert (long_win["entry_price"], long_win["exit_price"]) == (23000.0, 23030.0)        # (596 + 4) / 20 = 30 points up
    assert (long_loss["entry_price"], long_loss["exit_price"]) == (23010.0, 22980.0)      # (-604 + 4) / 20 = 30 points down
    assert (short_win["side"], short_win["exit_price"]) == ("short", 22980.0)             # a short wins below its entry
    assert long_win["exit_ms"] == T0 + 85 + 600_000 and long_win["net"] == 596.0 and long_win["qty"] == 1
    assert long_loss["exit_reason"] == "sl"


def test_a_trade_whose_minute_has_no_bar_is_left_out():
    rows = execrun.priced([trade(T0 + 85, 100.0), trade(T0 + 5 * M, 100.0), trade(T0, 1.0, date="2025-07-04")], {"2025-07-03": {T0: 100.0}}, 20.0)
    assert len(rows) == 1 and rows[0]["entry_ms"] == T0 + 85


def test_main_writes_a_run_the_tester_lists(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(execrun, "minute_opens", lambda root, dates, base=None: {"2025-07-03": {T0: 23000.0}})
    f = tmp_path / "t.json"
    f.write_text(json.dumps({"trades": [trade(T0 + 85, 596.0), trade(T0 + 9 * M, 5.0)]}))
    assert execrun.main([str(f), "--strategy", "pipe_nq_x", "--root", "NQ", "--name", "nq_x: box", "--start", "2025-07-03", "--end", "2025-07-03",
                         "--sessions", "1", "--note", "n", "--base", str(tmp_path / "tester")]) == 0
    got = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert got["priced"] == 1 and got["of"] == 2
    meta = runner.read_json(tmp_path / "tester" / "runs" / got["run_id"] / "run.json")
    assert meta["strategy"] == {"id": "pipe_nq_x", "name": "nq_x: box", "root": "NQ"} and meta["imported"]["trades"] == 1


def test_main_says_so_when_nothing_can_be_priced(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(execrun, "minute_opens", lambda root, dates, base=None: {})
    f = tmp_path / "t.json"
    f.write_text(json.dumps([trade(T0, 1.0)]))
    assert execrun.main([str(f), "--strategy", "pipe_nq_x", "--root", "NQ", "--base", str(tmp_path / "tester")]) == 2
    assert "could be priced" in capsys.readouterr().err and not (tmp_path / "tester").exists()
