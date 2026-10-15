"""LOCK of THE FUNDED PIPELINE (the owner, 2026-10-15: "the unseen data metrics must fall into at least one of" the rows of
docs/superpowers/findings/2026-10-15-75pct-payout-20-weekdays-win-rate-by-rr.txt). blueprint/pipe_funded.py, templates/pipeline_funded.json,
and where the line asks: the build-day pick (P3.14), the one read of the unseen days (P6.2), the portfolio (PF.1). Hand-made trades only.

 1. The profile: its name, its 21 rows (the finding's table), the group's bar (max payout in 20 days at 75 % on a funded LucidFlex 50K).
    No other profile has the line.
 2. A box's numbers in R: win rate, reward (average win / average loss), edge, trades a day; a trade without a stop has no R.
 3. One strategy falls into a row on its win rate and reward alone (the trades a day are the group's); a higher reward or win rate only helps.
 4. Too few trades: no row. A reward under every row's: no row.
 5. The build-day row P3.14 asks under the FUNDED PIPELINE and does not exist under another.
 6. The portfolio: the funded account alone, a member off the line is left out, a mix must fall into a row WITH its trades a day.

  pytest tests/test_pipe_funded.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

W = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(W), str(Path(__file__).resolve().parent)]
from blueprint import pipe_funded as F  # noqa: E402
from blueprint import pipe_gates as G  # noqa: E402
from blueprint import pipe_portfolio as PF  # noqa: E402
from blueprint import pipe_rules as P  # noqa: E402

import blueprint_synth as SY  # noqa: E402
import library as LB  # noqa: E402

FLEX = "lucid-flex-50k@2026-10-11"
CAL = SY.weekdays()                                 # 44 hand-made session days
RISK, PV = 20.0, 20.0                               # NQ: a 20-point stop is $400 a contract: 1 R
TABLE = [(0.5, 4, .8), (0.5, 6, .8), (0.5, 8, .8), (0.75, 4, .725), (0.75, 6, .7), (0.75, 8, .7), (1, 4, .65), (1, 6, .65), (1, 8, .625),
         (1.25, 4, .6), (1.25, 6, .575), (1.25, 8, .575), (1.5, 4, .55), (1.5, 6, .55), (1.5, 8, .525), (2, 4, .475), (2, 6, .475), (2, 8, .45),
         (2.5, 4, .425), (2.5, 6, .4), (2.5, 8, .4)]


@pytest.fixture()
def funded(monkeypatch):
    """The FUNDED PIPELINE's file, by its profile (P.FILE at the LIVE path = "read the profile's file", whatever another module left it at)."""
    monkeypatch.setenv("HB_PIPELINE", "funded")
    monkeypatch.setattr(P, "FILE", P.R.T / P.PROFILES["live"][1])
    P._all.cache_clear()
    yield
    P._all.cache_clear()


def box(rs: list, per_day: int = 1, risk: float = RISK) -> dict:
    """A box's trades as judge.cellx hands them: `rs` = each trade in R, `per_day` of them a session day of CAL."""
    d = [LB._ordinals([CAL[(i // per_day) % len(CAL)]])[0] for i in range(len(rs))]
    return {"net": np.array(rs, np.float64) * risk * PV, "risk": np.full(len(rs), risk), "date": np.array(d, np.int64)}


def mix(win: int, n: int, w: float = 1.0, lo: float = -1.0) -> list:
    """n trades, `win` of them +w R and the rest `lo` R, the wins spread through the list."""
    return [w if (i + 1) * win // n > i * win // n else lo for i in range(n)]


# ================================================================ 1. the profile

def test_the_profile_carries_the_findings_table_and_the_groups_bar(funded):
    assert P.label() == "FUNDED PIPELINE" and P.funded() and P.gates() == "prop" and P.winlane() == "off"
    assert [(r["rr"], r["trades_day"], r["win"]) for r in P.need("funded", "rows")] == TABLE
    assert P.need("funded", "account") == FLEX and P.need("funded", "min_trades") == 30
    assert P.need("funded", "labels") == {"daily_sharpe": 0.5, "correlation": 0.3, "worst_day_floor": 0.4}
    assert P.need("portfolio", "payout") == {"days": 20, "odds": 0.75} and FLEX in P.need("portfolio", "funded_only")
    assert PF.accounts() == [FLEX] and PF._account(None)[0] == FLEX


@pytest.mark.parametrize("profile", ["live", "wr", "payout"])
def test_no_other_profile_has_the_line(monkeypatch, profile):
    monkeypatch.setenv("HB_PIPELINE", profile)
    monkeypatch.setattr(P, "FILE", P.R.T / P.PROFILES["live"][1])
    P._all.cache_clear()
    assert not P.funded() and G.funded({"root": "NQ", "trade_net": np.ones(40), "trade_risk": np.ones(40), "trade_date": np.arange(40)}) == []
    P._all.cache_clear()


# ================================================================ 2. the numbers

def test_a_boxs_numbers_in_r_and_a_trade_without_a_stop_has_none(funded):
    x = box(mix(66, 100))
    x["risk"][0] = np.nan                           # (the first trade is a loss)
    s = F.stats(x, "NQ")
    assert (s["trades"], s["no_stop"]) == (99, 1) and s["win"] == pytest.approx(66 / 99, abs=1e-6) and s["rr"] == pytest.approx(1.0)
    assert s["edge"] == pytest.approx(2 * 66 / 99 - 1, abs=1e-6) and s["days"] == 44 and s["trades_day"] == pytest.approx(99 / 44)
    s2 = F.stats(box([1.0, -0.5] * 20), "NQ", CAL)
    assert s2["rr"] == pytest.approx(2.0) and s2["win"] == 0.5 and s2["days"] == len(CAL)


# ================================================================ 3-4. one strategy and its row

@pytest.mark.parametrize("rs, row", [(mix(66, 100), (1, 8, .625)),                    # 66 % at 1 : 1
                                     (mix(80, 100, 0.5), (0.5, 8, .8)),               # 80 % at 1 : 0.5
                                     (mix(41, 100, 2.5), (2.5, 8, .4)),               # 41 % at 1 : 2.5
                                     (mix(56, 100, 1.6), (1.5, 8, .525))])           # a reward between two rows: the lower row's need
def test_one_strategy_falls_into_a_row_on_its_win_rate_and_reward(funded, rs, row):
    """One strategy is not held to the trades a day: of the rows that fit, the highest reward, then the most trades a day (the easiest win rate)."""
    got = F.row("P6.2", box(rs), "NQ")
    assert got["passed"] is True and (got["fits"]["rr"], got["fits"]["trades_day"], got["fits"]["win"]) == row and "falls into the row" in got["text"]


@pytest.mark.parametrize("rs, words", [(mix(60, 100), "nearest row, 1 : 1 at 8 trades a day needs 62.5 % wins"),
                                       (mix(90, 100, 0.4), "under every row"),
                                       (mix(15, 20), "too few trades")])
def test_off_the_line(funded, rs, words):
    got = F.row("P6.2", box(rs), "NQ")
    assert got["passed"] is False and words in got["text"]


def test_a_group_must_also_trade_the_rows_trades_a_day(funded):
    rs = mix(123, 176)                              # 70 %
    assert F.row("PF.1", box(rs, per_day=4), "NQ", CAL, group=True)["fits"] == {"rr": 1, "trades_day": 4, "win": 0.65}
    two = F.row("PF.1", box(rs[:88], per_day=2), "NQ", CAL, group=True)
    assert two["passed"] is False and "the group trades 2.00 a day" in two["text"]


# ================================================================ 5. the build-day row

def test_the_build_day_row_asks_under_the_funded_pipeline(funded):
    x = box(mix(70, 100))
    b = {"root": "NQ", "trade_net": x["net"], "trade_risk": x["risk"], "trade_date": x["date"]}
    assert [(r["line"], r["passed"]) for r in G.funded(b)] == [("P3.14", True)]
    y = box(mix(55, 100))
    assert G.funded({**b, "trade_net": y["net"]})[0]["passed"] is False
    assert G.funded({**b, "trade_risk": None})[0]["passed"] is False


# ================================================================ 6. the portfolio

def strat(name: str, rs_day: list, times: tuple, market: str = "NQ") -> dict:
    """A book strategy (pipe_portfolio.member's shape): `rs_day[i]` = the R of each of its trades on session day i, at `times`."""
    rows = [SY.trade(d, (r * RISK * PV + LB.COMM_RT) / 10 - LB.MICRO_RT_USD, 5.0, at=t) for d, rs in zip(CAL, rs_day) for r, t in zip(rs, times)]
    return {"name": name, "family": name, "market": market, "session": "nyam", "bar": "5", "box": "v", "trades": len(rows),
            "x": LB.pack(sorted(rows, key=lambda t: (t["exit_ms"], t["entry_ms"]))), "calendar": list(CAL)}


def test_the_group_is_judged_on_the_funded_account_and_its_row(funded):
    good = [[1.0 if (i + k) % 10 < 7 else -1.0 for k in range(2)] for i in range(len(CAL))]
    a, b = strat("fvg", good, ("09:45", "10:30")), strat("rsi2", good[::-1], ("11:00", "13:00"))
    off = strat("gap", [[1.0 if (i + k) % 2 else -1.0 for k in range(2)] for i in range(len(CAL))], ("14:00", "14:30"))
    r = PF.build(FLEX, members=[a, b, off], paths=500, seed=7)
    assert r["judged"] == ["payout"] and r["rules"]["biggest_day"] is None and r["rules"]["funded_line"] is True
    assert [x["name"] for x in r["left_out"]] == ["gap"] and "off the funded line" in r["left_out"][0]["why"]
    pair = next(m for m in r["mixes"] if m["members"] == ["fvg", "rsi2"])
    assert pair["funded"]["row"]["line"] == "PF.1" and pair["funded"]["row"]["passed"] is True and pair["on_line"] is True
    assert pair["funded"]["row"]["fits"] == {"rr": 1, "trades_day": 4, "win": 0.65}
    assert set(pair["funded"]["labels"]) == {"daily_sharpe", "correlation", "worst_day_floor"}
    alone = next(m for m in r["mixes"] if m["members"] == ["fvg"])
    assert alone["on_line"] is False and alone["meets"] is False and "the group trades 2.00 a day" in alone["funded"]["row"]["text"]
    assert "the funded line: PF.1" in r["text"]
