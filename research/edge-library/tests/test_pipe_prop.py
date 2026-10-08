"""LOCK of the pipeline's prop check (blueprint/pipe_prop.py) -- pipeline plan A, task 6; spec section 3, stage 5.
HAND-MADE TRADES ONLY (tests/blueprint_synth.py): no tape is read, no engine run is made, nothing is written but a temp copy
of pipeline.json. Few paths and a fixed seed: seconds.

1. The shape of the answer; the account, the days and the two bars are pipeline.json's.
2. A strong steady strategy STANDS ALONE; a flat coin flip is a HELPER; the label asks BOTH numbers strictly over their bar.
3. The numbers are the walks of propodds on the "live is worse" row, cut at the days: path for path a pass inside the days
   is a pass without a day limit, so the number is never above line 5.5's at the same size -- and for a slow strategy it is
   far below it. More days in pipeline.json = a higher number.
4. The eval is read at its best size of the eval's steps (a tie: the smaller); the payout at its best size of the FUNDED
   account's steps -- a step above the size the funded account starts at has no payout.
5. Open losses count.
6. The account argument: the default is pipeline.json's, another rule file gives that account's name and its own numbers,
   an id the app does not have is refused by name.
7. No trade, or no calendar: nothing to read, a helper, and nothing is raised.
8. No number is typed in the module.

  pytest tests/test_pipe_prop.py -q          python tests/test_pipe_prop.py     the same, one line per test
"""
from __future__ import annotations

import contextlib
import copy
import json
import sys
import tempfile
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(W), str(Path(__file__).resolve().parent)]
import judge as J  # noqa: E402
from blueprint import pipe_prop as PP  # noqa: E402
from blueprint import pipe_rules as P  # noqa: E402
from blueprint import propodds as PO  # noqa: E402

import blueprint_synth as SY  # noqa: E402
import library as LB  # noqa: E402

PS = PO.app()
FILE = P.FILE
PRO_FREE, FLEX = "lucid-pro-50k-no-dll@2026-09-27b", "lucid-flex-50k@2026-09-27"
CAL = SY.weekdays("2024-01-01", "2024-10-04")        # 200 hand-made session days
N, SEED = 2000, 7                                   # the paths of a test, and their seed
KEYS = {"account", "days", "size", "payout_size", "eval", "payout", "label", "need", "table", "text"}


def teardown_function(_=None):
    P.FILE = FILE
    P._all.cache_clear()


def cells(rows: list) -> dict:
    """Hand-made trades as the packed arrays of a store's cell (what judge.cellx hands over)."""
    return LB.pack(sorted(rows, key=lambda t: (t["exit_ms"], t["entry_ms"])))


def weekly(win: float, loss: float, mae: float = 2.0, every: int = 5) -> dict:
    """One trade a session day: `win` dollars a micro, and every `every`-th day `loss` (a negative number)."""
    return cells([SY.trade(d, loss if i % every == every - 1 else win, mae) for i, d in enumerate(CAL)])


STRONG = weekly(20.0, -6.0)                          # four winning days of five, small losses
FLAT = weekly(10.0, -10.0, 10.0, every=2)            # a coin flip: up $10, down $10
SLOW = weekly(4.0, -2.0)                             # it gets there, but not inside the days
LUMPY = weekly(-5.0, 70.0, every=5)                  # one big winning day a week, four small losing ones


def odds(x, **kw) -> dict:
    return PP.odds(x, CAL, paths=N, seed=SEED, **kw)


def free(x, size: int, rid: str = PRO_FREE) -> dict:
    """propodds' own odds at a size on the "live is worse" row: `free` = WITHOUT A DAY LIMIT (line 5.5)."""
    r = PS.load_rules(rid)
    net, traded, opn, _ = PO.days(PO.ledger(x, size, r), r, CAL)
    wnet, wopn = PO.worse(net, traded, opn)
    return PO.odds(wnet, traded, wopn, r, N, SEED)


@contextlib.contextmanager
def with_file(**prop):
    """While it is open, pipeline.json is a temp copy with other `prop` numbers."""
    p = copy.deepcopy(json.loads(FILE.read_text(encoding="utf-8")))
    p["prop"].update(prop)
    with tempfile.TemporaryDirectory() as tmp:
        P.FILE = Path(tmp) / "pipeline.json"
        P.FILE.write_text(json.dumps(p), encoding="utf-8")
        P._all.cache_clear()
        try:
            yield
        finally:
            teardown_function()


# ================================================================ 1. the shape

def test_the_answer_and_where_its_numbers_come_from():
    r, got = PS.load_rules(PRO_FREE), odds(STRONG)
    assert set(got) == KEYS
    assert P.need("prop") == {"account": PRO_FREE, "days": 30, "eval": 0.5, "payout": 0.5}
    assert got["account"] == {"id": PRO_FREE, "name": r["name"], "confirmed": True} and got["days"] == 30 and got["need"] == {"eval": 0.5, "payout": 0.5}
    ev, fu = PO.steps(r)
    assert [x["size"] for x in got["table"]] == ev and all(set(x) == {"size", "eval", "payout"} for x in got["table"])
    assert [x["size"] for x in got["table"] if x["payout"] is not None] == fu and fu[-1] < ev[-1], "no payout above the size the funded account starts at"
    assert all(0.0 <= x["eval"] <= 1.0 and (x["payout"] is None or 0.0 <= x["payout"] <= 1.0) for x in got["table"])
    json.dumps(got)                                 # plain JSON: it goes on a stage card
    assert got == odds(STRONG), "the same paths, the same answer"
    assert got["eval"] != PP.odds(STRONG, CAL, paths=N, seed=SEED + 1)["eval"] or got["table"] != PP.odds(STRONG, CAL, paths=N, seed=SEED + 1)["table"]


# ================================================================ 2. the label

def test_a_strong_steady_strategy_stands_alone():
    got = odds(STRONG)
    assert got["label"] == "stands alone" and got["eval"] > 0.9 and got["payout"] > 0.9, got
    assert f"{100 * got['eval']:.1f} %" in got["text"] and f"{100 * got['payout']:.1f} %" in got["text"] and "STANDS ALONE" in got["text"]
    assert "30 trading days" in got["text"] and r_name() in got["text"] and "open losses count" in got["text"] and "\n" not in got["text"]


def r_name() -> str:
    return PS.load_rules(PRO_FREE)["name"]


def test_a_flat_coin_flip_is_a_helper():
    got = odds(FLAT)
    assert got["label"] == "helper" and got["eval"] < 0.5 and got["payout"] < 0.5, got
    assert "HELPER" in got["text"] and f"{100 * got['eval']:.1f} %" in got["text"] and f"{100 * got['payout']:.1f} %" in got["text"]


def test_the_label_asks_both_numbers_strictly_over_their_bars():
    got = odds(STRONG)
    with with_file(eval=got["eval"]):               # exactly at the bar is not over it
        assert odds(STRONG)["label"] == "helper" and odds(STRONG)["need"]["eval"] == got["eval"]
    with with_file(payout=got["payout"]):
        assert odds(STRONG)["label"] == "helper"
    with with_file(eval=got["eval"] - 0.001, payout=got["payout"] - 0.001):
        assert odds(STRONG)["label"] == "stands alone"
    assert PP.label(0.6, 0.4) == "helper" and PP.label(0.4, 0.6) == "helper" and PP.label(0.5, 0.9) == "helper" and PP.label(0.51, 0.51) == "stands alone"


# ================================================================ 3. the day limit

def test_the_day_limit_bites_a_slow_strategy():
    got = odds(SLOW)
    size, f = got["size"], free(SLOW, got["size"])
    assert f["eval"]["free"]["p"] > 0.9, "without a day limit it passes"
    assert got["eval"] < 0.3 and got["eval"] < f["eval"]["free"]["p"] - 0.5, (got["eval"], f["eval"]["free"]["p"])
    assert got["label"] == "helper"
    for x in got["table"]:                          # at every size, on the same paths: a pass inside the days is a pass without a limit
        g = free(SLOW, x["size"])
        assert x["eval"] <= g["eval"]["free"]["p"], x
        assert x["eval"] >= g["eval"]["p"], "30 days hold every pass of line 5.3's 10"
    with with_file(days=60):
        more = odds(SLOW)
        assert more["days"] == 60 and "60 trading days" in more["text"]
        at = {x["size"]: x for x in more["table"]}[size]
        assert at["eval"] > got["eval"] + 0.3 and more["eval"] >= at["eval"] and more["payout"] >= got["payout"], (at, got["eval"])
        assert all(a["eval"] >= b["eval"] and (a["payout"] is None or a["payout"] >= b["payout"]) for a, b in zip(more["table"], got["table"]))


def test_the_numbers_are_propodds_walks_cut_at_the_days():
    r, got = PS.load_rules(PRO_FREE), odds(STRONG)
    for x in got["table"]:
        net, traded, opn, _ = PO.days(PO.ledger(STRONG, x["size"], r), r, CAL)
        wnet, wopn = PO.worse(net, traded, opn)
        idx = PO.draws(len(net), N, PO.horizon(r), SEED)
        P_, T_, O_ = wnet[idx], traded[idx], wopn[idx]
        e, f = PO.eval_walk(P_, T_, O_, r), PO.funded_walk(P_, O_, r)        # the whole walk, read at the day
        assert x["eval"] == float(((e["outcome"] == PO.PASS) & (e["day"] <= 30)).mean()), x
        assert x["payout"] is None or x["payout"] == float(((f["max_payout_at"] > 0) & (f["max_payout_at"] <= 30)).mean()), x


# ================================================================ 4. the sizes

def test_each_phase_is_read_at_its_own_best_size_and_a_tie_takes_the_smaller():
    got = odds(STRONG)
    t = got["table"]
    assert got["eval"] == max(x["eval"] for x in t) and got["size"] == next(x["size"] for x in t if x["eval"] == got["eval"])
    paid = [x for x in t if x["payout"] is not None]
    assert got["payout"] == max(x["payout"] for x in paid) and got["payout_size"] == next(x["size"] for x in paid if x["payout"] == got["payout"])
    assert f"{got['size']} micro" in got["text"] and f"{got['payout_size']} micro" in got["text"]
    always = cells([SY.trade(d, 40.0) for d in CAL])                    # $40 a micro every day: several sizes pass every time
    got = odds(always)
    full = [x["size"] for x in got["table"] if x["eval"] == 1.0]
    assert len(full) > 1 and got["size"] == full[0] and got["eval"] == 1.0, "equal odds: the smaller size"
    dead = cells([SY.trade(d, -10.0, 10.0) for d in CAL])               # it loses every day: nothing passes at any size
    got = odds(dead)
    assert (got["eval"], got["payout"], got["size"], got["payout_size"], got["label"]) == (0.0, 0.0, 1, 1, "helper")


# ================================================================ 5. open losses count

def test_open_losses_count():
    r = PS.load_rules(PRO_FREE)
    under = cells([SY.trade(d, 20.0 if i % 5 < 4 else -6.0, r["trailing_mll"] + 1.0) for i, d in enumerate(CAL)])       # STRONG, but every trade is a micro's whole drawdown under water first
    got = odds(under)
    assert (got["eval"], got["payout"], got["label"]) == (0.0, 0.0, "helper"), "busted on the first day at every size, whatever the days close at"
    assert odds(STRONG)["label"] == "stands alone"


# ================================================================ 6. the account

def test_the_account_is_the_files_or_the_one_asked_for():
    assert odds(LUMPY)["account"]["id"] == P.need("prop", "account") == PRO_FREE and odds(LUMPY) == odds(LUMPY, account=PRO_FREE)
    pro, flex = odds(LUMPY), odds(LUMPY, account=FLEX)
    assert flex["account"] == {"id": FLEX, "name": PS.load_rules(FLEX)["name"], "confirmed": True} and flex["account"]["name"] in flex["text"]
    assert flex["eval"] < pro["eval"], "one big day is most of the profit: the consistency rule of the other account holds the pass back"
    with with_file(account=FLEX):
        assert odds(LUMPY) == flex and odds(LUMPY, account=PRO_FREE) == pro
    for bad in ("no-such-account@2026-01-01", "lucid"):
        try:
            odds(STRONG, account=bad)
        except J.Refuse as e:
            assert repr(bad) in str(e) and PRO_FREE in str(e), str(e)
        else:
            raise AssertionError(f"{bad} was not refused")


# ================================================================ 7. nothing to read

def test_no_trade_or_no_calendar_is_nothing_to_read():
    for x, cal in ((cells([]), CAL), ({"net": np.zeros(0)}, CAL), (STRONG, []), (STRONG, None)):
        got = PP.odds(x, cal, paths=N, seed=SEED)
        assert set(got) == KEYS and got["account"]["id"] == PRO_FREE and got["days"] == 30 and got["need"] == {"eval": 0.5, "payout": 0.5}
        assert (got["size"], got["payout_size"], got["eval"], got["payout"], got["label"], got["table"]) == (None, None, 0.0, 0.0, "helper", [])
        assert "nothing to read" in got["text"]
    assert "no trade" in odds(cells([]))["text"] and "no session day" in PP.odds(STRONG, [], paths=N, seed=SEED)["text"]


# ================================================================ 8. no number in the module

def test_no_number_is_typed_in_the_module():
    src = (W / "blueprint" / "pipe_prop.py").read_text(encoding="utf-8").split('"""', 2)[2]       # the code under the docstring
    for number in ("30", "0.5", "50", "lucid", "@20"):
        assert number not in src, f"{number} is typed in pipe_prop.py"


if __name__ == "__main__":
    import time
    rc = 0
    for name, t in [(k, v) for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]:
        t0 = time.monotonic()
        try:
            t()
            print(f"PASS {name} ({time.monotonic() - t0:.1f} s)", flush=True)
        except AssertionError as e:
            rc = 1
            print(f"FAIL {name}\n{e}", flush=True)
        finally:
            teardown_function()
    sys.exit(rc)
