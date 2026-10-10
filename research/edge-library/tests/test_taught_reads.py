"""LOCK of THE TAUGHT LANE'S READS (blueprint/taught.py), on HAND-MADE STORES: no tape, no engine run. The stores are written by the
library's own `write_unit` (what the runner writes), so the reader is held to the real format.

1. THE CENTRE CELL is read with library.metrics (trades, net, win rate, profit factor, drawdown, Sharpe), average win / average loss,
   per year then combined.
2. THE LINES are the pipeline's own functions on the centre box -- P3.2 P3.3 P3.4 P3.7 P3.8 P3.9 P3.10, the lock's 3.3-3.8, the
   reshuffled runs P4.1 -- each kept with its kind (the steadiness rows are marked).
3. THE RANDOM LINES: no control on disk is "not run", never a pass; with the controls on disk the cell is drawn against them pass by
   pass (judge.c1_table), and a one-sided rule is held against the same-side drift as well as against the pipeline's both-sided entries.
4. THE NEIGHBOURS and the average of the nine are shown, never picked; the whole read is plain JSON.
5. A store of other days is not read. The headline and the text say what ran, what was left out, the verdict and the limits.

  pytest tests/test_taught_reads.py -q
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path

import pytest

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import judge as J  # noqa: E402
import l2sim as S  # noqa: E402
import library as LB  # noqa: E402
import test_taught as TK  # noqa: E402
from blueprint import pipe_rules as PR  # noqa: E402
from blueprint import runner as RUN  # noqa: E402
from blueprint import tables as T  # noqa: E402
from blueprint import taught as TT  # noqa: E402

HAND = [d.isoformat() for d in (dt.date(2022, 1, 3) + dt.timedelta(days=k) for k in range(70)) if d.weekday() < 5][:40]       # 40 weekdays
TF = "5"
EXPECT = ["P3.2", "P3.3", "P3.4", "P3.7", "P3.8", "P3.9", "P3.10", "3.3", "3.4", "3.5", "3.6", "3.7", "3.8", "P4.1", "P4.2", "P4.2s"]


def _trade(day: str, hhmm: str, net: float, side: str = "long", risk: float = 80.0) -> dict:
    ms = S.et_ns(dt.date.fromisoformat(day), hhmm) // 1_000_000
    return {"date": day, "entry_ms": ms, "exit_ms": ms + 600_000, "net": net, "mae_usd": 60.0, "side": side, "entry_price": 15000.0,
            "sl": 15000.0 - risk if side == "long" else 15000.0 + risk, "exit_reason": "tp" if net > 0 else "sl", "commission": 4.0}


def _result(trades: list) -> dict:
    return {"trades": trades, "meta": {"inputs": {}, "range": {"start": HAND[0], "end": HAND[-1]}}, "sessions": len(HAND), "used": len(HAND), "skipped": [],
            "no_trade": [], "elapsed_s": 0.0}


def _store(out: Path, key: str, cells: list, nets_by_cell: list, side: str = "long", hhmm: str = "10:35") -> None:
    """One store: `cells` = ids, nets_by_cell[i] = the net of the cell's trade on each of the 40 days."""
    grid = [{"id": c, "vi": 0, "xi": k, "variant": {}, "exit": {"stop_mode": "pts", "tgt_r": 0.5}} for k, c in enumerate(cells)]
    res = [_result([_trade(d, hhmm, n, side) for d, n in zip(HAND, nets)]) for nets in nets_by_cell]
    LB.write_unit(key, {"period": RUN.PERIOD, "days": HAND, "family": "vwap_trend_pull", "tf": TF}, grid, res, out)


def _pool(out: Path, key: str, cells: list, net: float, side: str = "long") -> None:
    ids = [f"s{sd}_{c}" for sd in range(1, 11) for c in cells]
    grid = [{"id": i, "vi": 0, "xi": k, "variant": {"seed": 1}, "exit": {"stop_mode": "pts", "tgt_r": 0.5}} for k, i in enumerate(ids)]
    res = [_result([_trade(d, "10:05", net, side) for d in HAND]) for _ in ids]
    LB.write_unit(key, {"period": RUN.PERIOD, "days": HAND, "family": "random", "tf": TF}, grid, res, out)


@pytest.fixture()
def hand(tmp_path, monkeypatch):
    """A plan (NQ, 5-minute bars, the conti rule) and its unit store made by hand: the centre cell wins $100 on 30 days and loses $150 on 10;
    each other cell is the centre's nets times its own factor. No random-entry pool yet. The prop odds are a stand-in (their own lock is
    tests/test_pipe_prop.py)."""
    monkeypatch.setattr(TT, "_prop", lambda x, cal: {"account": "hand", "confirmed": True, "size": 1, "payout_size": 1, "eval": 0.5, "payout": 0.4, "label": "helper",
                                                    "days": 30, "need": {}, "stress": {"size": 1, "payout_size": 1, "eval": 0.3, "payout": 0.2}})
    plan = TT.check(TK.sheet(bars=[TF]))["plan"]
    ids = [c["id"] for c in plan["cells"]]
    centre = [100.0 if i % 4 else -150.0 for i in range(len(HAND))]                  # 30 wins, 10 losses
    nets = [[round(n * (0.5 + 0.125 * k), 2) for n in centre] for k in range(9)]       # the centre is cell 4: factor 1.0
    J.reset()
    _store(tmp_path / "runs", f"{plan['name']}-NQ-tf{TF}", ids, nets)
    return plan, tmp_path / "runs", ids


def _read(plan, out, pools=None, stop=None):
    J.reset()
    return TT._read_bar(plan, TF, out, HAND, pools or {}, stop)


def test_the_centre_cell_is_read_with_the_librarys_own_metrics(hand):
    plan, out, ids = hand
    b = _read(plan, out)
    c = b["centre"]
    assert c["id"] == "pts80-r0p5" and len(b["cells"]) == 9
    m = c["metrics"]
    assert m["trades"] == 40 and m["net"] == 1500.0 and m["avg_trade"] == 37.5 and m["win"] == 0.75
    assert m["pf"] == pytest.approx(2.0) and m["avg_win"] == 100.0 and m["avg_loss"] == -150.0 and m["win_loss"] == pytest.approx(2 / 3)
    assert [y["period"] for y in c["years"]][-1] == "combined" and c["years"][-1]["trades"] == 40
    st, _ = T._open(out, f"{plan['name']}-NQ-tf{TF}")
    lib = LB.metrics(J.cellx(st, "pts80-r0p5", None), LB._ordinals(HAND))
    assert (m["max_dd"], m["sharpe"], m["worst_open_loss"]) == (lib["max_dd"], lib["sharpe"], lib["worst_open_loss"])
    assert m["dd_open"] >= m["max_dd"]                        # open losses can only make the fall larger


def test_the_lines_are_the_pipelines_own_on_the_centre_box(hand):
    plan, out, ids = hand
    rows = {r["line"]: r for r in _read(plan, out)["lines"]}
    assert list(rows) == EXPECT
    assert rows["P3.2"]["passed"] is False and rows["P3.2"]["number"] == 37.5 and rows["P3.2"]["need"] == 70.0       # NQ's cost floor, rules.json 2.2
    assert rows["P3.3"]["passed"] is False and rows["P3.3"]["number"] == 40 and rows["P3.3"]["need"] == PR.need("variant", "region_trades")
    assert rows["3.3"]["passed"] is True and rows["3.3"]["number"] == pytest.approx(2.0)
    assert rows["P3.4"]["passed"] is True and rows["P3.4"]["text"].startswith("P3.4 PASS long only by its card")
    assert [rows[k]["kind"] for k in ("P3.8", "P3.9", "P3.10")] == ["steadiness"] * 3
    assert rows["P3.2"]["kind"] == "gate" and rows["3.3"]["kind"] == "lock" and rows["P4.1"]["kind"] == "proof"
    assert "P3.6" not in rows                                       # one market: the other-markets row does not apply


def test_no_control_on_disk_is_not_a_pass(hand):
    plan, out, ids = hand
    rows = {r["line"]: r for r in _read(plan, out)["lines"]}
    for k in ("P4.2", "P4.2s"):
        assert rows[k]["passed"] is None and "not run" in rows[k]["text"]
    b = _read(plan, out)
    assert b["centre"]["held"] + len(b["centre"]["failed"]) == b["centre"]["of"] == 14       # the two random lines are not counted: they did not run


def test_beating_random_entries_is_read_per_pass_against_the_lanes_own_control(hand):
    plan, out, ids = hand
    both, long_ = f"{plan['name']}__ctl-NQ-tf{TF}", f"{plan['name']}__ctl_long-NQ-tf{TF}"
    _pool(out, both, ids, -40.0, "long")                     # random entries lose $40 a trade every day
    _pool(out, long_, ids, 200.0, "long")                    # random LONG entries make $200 a trade: the market's drift
    pools = {"both": T.pool_seeds(out, both, ids, 10), "long": T.pool_seeds(out, long_, ids, 10)}
    with TT._draws(300):
        rows = {r["line"]: r for r in _read(plan, out, pools)["lines"]}
    assert rows["P4.2"]["passed"] is True and rows["P4.2"]["number"] == 1.0
    assert rows["P4.2s"]["passed"] is False and rows["P4.2s"]["number"] == 0.0           # a long rule must beat random LONGS: the drift beats it
    assert "both sides" in rows["P4.2"]["text"] and "long entries only" in rows["P4.2s"]["text"] and rows["P4.2"]["seeds"] == 10
    assert rows["P4.2"]["need"] == pytest.approx(0.95)             # tries = 1: the first bar of the law's ladder


def test_the_neighbours_and_the_average_are_shown_not_picked(hand):
    plan, out, ids = hand
    b = _read(plan, out)
    nets = [c["metrics"]["net"] for c in b["cells"]]
    assert nets == sorted(nets) and len(set(nets)) == 9                  # the hand-made factors rise cell by cell
    assert b["average"]["net"] == pytest.approx(sum(nets) / 9) and b["average"]["trades"] == 40
    assert b["average"]["avg_trade"] == pytest.approx(sum(nets) / 9 / 40)
    neigh = [c for c in b["cells"] if not c["centre"]]
    assert b["neighbours"]["net"] == pytest.approx(sum(c["metrics"]["net"] for c in neigh) / 8)
    assert [c["id"] for c in b["cells"] if c["centre"]] == ["pts80-r0p5"]
    assert b["centre"]["held"] == sum(r["passed"] is True for r in b["centre"]["lines"])
    assert b["average"]["prop"]["eval"] == 0.5 and b["centre"]["prop"]["stress"]["eval"] == 0.3
    json.dumps(TT._clean(b), allow_nan=False)                              # the whole read is plain, strict JSON


def test_a_store_of_other_days_is_not_read(hand):
    plan, out, ids = hand
    with pytest.raises(J.Refuse, match="not the store asked for"):
        TT._read_bar(plan, TF, out, HAND[:10], {}, None)


def test_the_headline_says_what_ran_what_was_left_out_and_the_verdict(hand):
    plan, out, ids = hand
    bars = {TF: _read(plan, out)}
    head = TT._headline(plan, bars, True)
    for part in ("SMOKE RUN, no verdict", "vwap_trend_pull", "x 0.1", "long only", "5-minute bars", "stop 80 / target 40 points", "up to 4 trades a session pass",
                 "leaves out 1 thing", "5-minute bars make $38 a trade on 40 trades", "hold ", " of 14 lines", "the neighbours average"):
        assert part in head, part
    assert "\n" not in head
    text = TT._text_run(plan, bars, head, HAND)
    assert text.splitlines()[0] == head
    for part in ("THE NINE CELLS", "PER YEAR, then combined", "HONEST LIMITS", "not read", "NOT RUN", "CAPPED PER SESSION PASS", "LINES on the taught cell"):
        assert part in text, part
    assert "bug" not in text.lower()
