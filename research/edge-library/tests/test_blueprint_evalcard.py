"""LOCK of phase 6, the eval (blueprint/evalcard.py; `bp.py eval-card <name> [--fills=-]`) -- toolkit plan, step 10.

(a) THE DRAWDOWN TABLE: whole days of the variant's own test-period trades, drawn with replacement (montecarlo.json: 1,000
    runs, the fixed seed), read after 10, 20, 30 and 40 trades at the 50th, 75th, 90th, 95th and 99th percentile -- drawdown,
    and P&L from the bad side. On hand-made lists every number is known.
(b) THE CARD BEFORE THE FIRST LIVE TRADE: refused until the simulator's result is on file; every line 6.1-6.9 is there as the
    rule to follow, none judged; the attempts and the fee budget of line 5.4 are on it; saved through the app's idea store.
(c) THE LINES ON LIVE FILLS, each at its threshold: 6.1 same entry time (within 5 s) and same exit reason, mismatches listed;
    6.2 average entry slip 2 ticks or less, no missed or rejected order; 6.3 stage A passed after 5 clean trades; 6.4 the
    live drawdown on the table after 10 / 20 / 30 / 40 trades at size (under the 75th: carry on, at the 75th: cut size,
    at the 95th: pause and review); 6.5 after 40 trades the average trade against half of the test's; 6.6-6.8 stated.
    Every line 6.1-6.5 TRUE = PROVEN LIVE, as the app's idea store reads the saved card.
(d) THE FILLS FORMAT: one text (evalcard.FILLS) in the module's docstring and in the command's help; what does not read is
    refused with the trade and the field named.
(e) THE COMMAND as the connector writes it (`eval-card <name> [--fills=-]`, {"fills": [...]} on stdin) -- and the app's own
    blueprint_eval_card against this toolkit.
EVERYTHING IS HAND-MADE (tests/blueprint_synth.py): no tape is read, no engine run is made, nothing leaves the temp folder.

  pytest tests/test_blueprint_evalcard.py -q          python tests/test_blueprint_evalcard.py     the same, one line per test
"""
from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

W = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(W), str(Path(__file__).resolve().parent)]
import judge as J  # noqa: E402
from blueprint import api as A  # noqa: E402
from blueprint import cli as C  # noqa: E402
from blueprint import evalcard as EC  # noqa: E402
from blueprint import mc as MC  # noqa: E402
from blueprint import propodds as PO  # noqa: E402
from blueprint import rules as R  # noqa: E402

import blueprint_synth as SY  # noqa: E402
import l2sim as S  # noqa: E402
import library as LB  # noqa: E402

PS = PO.app()
IS = A.ideastore()
FREE, FLEX = "lucid-pro-50k-no-dll@2026-09-27b", "lucid-flex-50k@2026-09-27"
CONTRACT = ("ok", "command", "name", "status", "phase", "round", "lines", "text", "next", "job", "saved", "error")      # plan section 8
SIX = [f"6.{i}" for i in range(1, 10)]
HOME = Path.home() / ".homebase"
APP_PYTHON = S.REPO / ".venv" / "bin" / "python"
_T = {"keep": tempfile.TemporaryDirectory(prefix="bp_card_")}
TMP = Path(_T["keep"].name).resolve()
ROOT, DRAFTS, STORES = TMP / "ideas", TMP / "drafts", TMP / "stores"
ENV = {"HOMEBASE_IDEAS_ROOT": str(TMP / "ideas_env"), "HOMEBASE_DRAFTS_DIR": str(DRAFTS)}        # never the real ~/.homebase
_KEPT: dict = {}
RESULTS: dict = {}
LIVE = SY.weekdays("2026-10-05", "2027-01-29")       # the days of a hand-made eval: one live trade a day


def _listing(p: Path):
    return sorted(x.name for x in p.iterdir()) if p.exists() else None


BEFORE = {"ideas": _listing(HOME / "ideas"), "drafts": _listing(HOME / "strategies")}


def setup_function(_=None):
    _KEPT.update({k: os.environ.get(k) for k in ENV})
    os.environ.update(ENV)


def teardown_function(_=None):
    for k, v in _KEPT.items():
        os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)


def refused(fn, *words) -> str:
    try:
        fn()
    except (J.Refuse, R.RuleError) as e:
        assert all(w in str(e) for w in words), str(e)
        return str(e)
    raise AssertionError(f"not refused ({words})")


def read(p) -> dict:
    return json.loads(Path(p).read_text(encoding="utf-8"))


def by(r: dict) -> dict:
    return {x["line"]: x for x in r["lines"]}


def marks(r: dict) -> list:
    return [x["passed"] for x in r["lines"]]


def cells(rows: list) -> dict:
    return LB.pack(sorted(rows, key=lambda t: (t["exit_ms"], t["entry_ms"])))


def iso(ms: int) -> str:
    return dt.datetime.fromtimestamp(ms / 1000, S.ET).isoformat(timespec="milliseconds")


def fill(i: int, net: float, size: int = 1, slip=1.0, reason: str = "tp", replay="same", late: float = 0.0, **more) -> dict:
    """Live trade number i of a hand-made eval (one a day, entered 09:45:02 New York time), in the FILLS format. replay
    "same" = the tester's replay has the same trade, entered `late` seconds earlier and ended the same way."""
    a = SY.ms(LIVE[i], "09:45") + 2000
    f = {"entry_time": iso(a), "exit_time": iso(a + 600_000), "side": "long", "size": size, "entry_price": 20000.25, "exit_price": 20010.0, "net": net,
         "exit_reason": reason, **({} if slip is None else {"entry_slip_ticks": slip})}
    if replay is not None:
        f["replay"] = {"entry_time": iso(a - round(late * 1000)), "exit_reason": reason} if replay == "same" else replay
    return {**f, **more}


def stage_a(n: int = 5, **kw) -> list:
    return [fill(i, 3.0, **kw) for i in range(n)]


def at_size(nets: list, size: int, start: int = 5) -> list:
    return [fill(start + k, v, size) for k, v in enumerate(nets)]


# ================================================================ (a) the drawdown table

def test_the_table_of_hand_made_runs_has_known_percentiles():
    need, mc = R.need("6.4"), R.template("montecarlo")
    assert (need["after_trades"], need["cut_percentile"], need["pause_percentile"]) == ([10, 20, 30, 40], 75, 95)
    assert mc["eval_card"] == {"line": "6.4", "percentiles": [50, 75, 90, 95, 99]} and (mc["runs"], mc["seed"]) == (1000, 20261005)
    paths = np.zeros((100, 40))
    paths[:, 0] = -np.arange(1.0, 101.0)             # run k loses $k on its first trade and nothing after: its drawdown is $k at every read
    t = EC.table(paths)
    assert (t["percentiles"], t["runs"], [x["after"] for x in t["rows"]]) == ([50, 75, 90, 95, 99], 100, [10, 20, 30, 40])
    for x in t["rows"]:                              # 1 .. 100, linear between the ranks -- the app's own percentile rule
        assert np.allclose(x["drawdown"], [50.5, 75.25, 90.1, 95.05, 99.01]) and np.allclose(x["pnl"], [-50.5, -75.25, -90.1, -95.05, -99.01])
        assert x["drawdown"] == [PS.engine._pct(sorted(-paths[:, 0]), q / 100) for q in t["percentiles"]]
    one = np.zeros((1, 40))
    one[0, :5] = [100.0, -50.0, -80.0, 200.0, -10.0]                              # up 100, down to -30, up to 170, 160
    one[0, 10:13] = [-400.0, 500.0, -100.0]                                       # after the 10th read: down to -240, 410 under the peak of 170; then a new peak
    t = EC.table(one)
    assert [x["drawdown"][0] for x in t["rows"]] == [130.0, 410.0, 410.0, 410.0] and [x["pnl"][0] for x in t["rows"]] == [160.0, 160.0, 160.0, 160.0]
    first = np.zeros((1, 40))
    first[0, :2] = [-40.0, 10.0]                     # a first trade that loses: the peak it falls from is the start
    assert EC.table(first)["rows"][0]["drawdown"] == [40.0] * 5 and EC.table(first)["rows"][0]["pnl"] == [-30.0] * 5


def test_the_runs_are_whole_days_drawn_with_replacement_with_the_fixed_seed():
    r = PS.load_rules(FREE)
    flat = PO.ledger(cells([SY.trade(d, -10.0, 10.0) for d in SY.weekdays()]), 7, r)             # every day one trade that loses $10 a micro
    p = EC.runs(flat)
    assert p.shape == (1000, 40) and set(np.unique(p)) == {-70.0}
    t = EC.table(p)
    assert [(x["after"], x["drawdown"], x["pnl"]) for x in t["rows"]] == [(n, [70.0 * n] * 5, [-70.0 * n] * 5) for n in (10, 20, 30, 40)]
    days = SY.weekdays()[:6]
    pairs = PO.ledger(cells([SY.trade(d, float(10 * k + 1), 0.0) for k, d in enumerate(days)]
                            + [SY.trade(d, float(10 * k + 2), 0.0, at="10:30") for k, d in enumerate(days)]), 1, r)
    p = EC.runs(pairs)                               # two trades a day, (10k + 1, 10k + 2): a run is made of whole days, in the day's own order
    assert p.shape == (1000, 40) and np.array_equal(p[:, 1::2], p[:, 0::2] + 1.0) and set(np.unique(p[:, 0::2])) == {1.0, 11.0, 21.0, 31.0, 41.0, 51.0}
    idx = MC.generator().integers(0, 6, size=(1000, 40))                          # the draw: the fixed seed of montecarlo.json, a fresh generator
    assert np.array_equal(p[:, 0], 10.0 * idx[:, 0] + 1.0) and np.array_equal(p[:, 2], 10.0 * idx[:, 1] + 1.0) and np.array_equal(p, EC.runs(pairs))
    assert not np.array_equal(p, EC.runs(pairs, np.random.default_rng(1)))


def test_where_a_live_drawdown_sits_on_the_table():
    row = {"after": 10, "drawdown": [200.0, 300.0, 400.0, 500.0, 600.0], "pnl": [0.0] * 5}       # the 75th = $300, the 95th = $500
    assert [EC.zone(v, row) for v in (0.0, 299.99, 300.0, 499.99, 500.0, 9000.0)] == ["carry on", "carry on", "cut size", "cut size", "the hard alarm", "the hard alarm"]
    none = {"after": 10, "drawdown": [0.0] * 5, "pnl": [0.0] * 5}                 # a history that never drew down inside 10 trades:
    assert EC.zone(0.0, none) == "carry on" and EC.zone(0.01, none) == "the hard alarm"            # no drawdown is never a pause; any is


# ================================================================ the hand-made idea of (b), (c), (e)

MIX = [SY.trade(d, -32.0 if i % 5 == 4 else 56.0, 35.0) for i, d in enumerate(SY.weekdays())]       # 36 winners, 8 losers: $40 a micro a trade on average
WEAK = [SY.trade(d, 30.0 if i % 2 else -28.0, 30.0) for i, d in enumerate(SY.weekdays())]           # $1 a micro a trade: odds under any bar
LOSS = [SY.trade(d, -10.0, 10.0) for d in SY.weekdays()[:4]]


def proven(name: str, weak: bool = False) -> Path:
    """An idea that is PROVEN ON HISTORY: two locked variants, of which v_mix survives (v_out loses with worse fills)."""
    return SY.proven(IS, ROOT, name, STORES, {"v_mix": WEAK if weak else MIX, "v_out": MIX[:4]}, worse={"v_mix": WEAK if weak else MIX, "v_out": LOSS})


def ready(name: str, account: str = FREE, weak: bool = False) -> dict:
    """... with its simulator result on file -> that result."""
    proven(name, weak)
    return PO.sim(name, account, 3, 345.0, ROOT, paths=400)


def card(name: str, fills=None, **kw) -> dict:
    return EC.card(name, None if fills is None else {"fills": fills}, ROOT, **kw)


# ================================================================ (b) the card before the first live trade

def test_refused_until_the_simulator_result_is_on_file():
    refused(lambda: card("ec_nobody"), "no idea ec_nobody")
    SY.proven(IS, ROOT, "ec_lead")
    refused(lambda: card("ec_lead"), "out-of-sample test is not on file")
    proven("ec_nosim")
    refused(lambda: card("ec_nosim"), "simulator", "not on file", "bp.py sim ec_nosim")
    refused(lambda: card("ec_nosim", [fill(0, 3.0)]), "bp.py sim ec_nosim")
    assert not (ROOT / "ec_nosim" / "eval.json").exists() and not (ROOT / "ec_lead" / "eval.json").exists()


def test_the_card_before_the_first_live_trade_is_the_rules_and_the_tables():
    sim = ready("ec_card")
    size = sim["chosen"]["eval"]["size"]
    with SY.no_engine():                             # the card reads the stores of the read: nothing is run, no tape is opened
        r = RESULTS["card"] = card("ec_card")
    assert tuple(r)[:len(CONTRACT)] == CONTRACT and (r["ok"], r["command"], r["name"], r["phase"], r["status"]) == (True, "eval-card", "ec_card", 6, "proven_on_history")
    json.dumps(r)
    assert [x["line"] for x in r["lines"]] == SIX and marks(r) == [None] * 9, "every line is there; none is judged before a live trade"
    L = by(r)
    for k in SIX[:5]:
        assert L[k]["text"].startswith(f"{k} n/a  not judged yet"), L[k]["text"]
    for k in SIX[5:]:
        assert L[k]["text"].startswith(f"{k} n/a  a rule to follow"), L[k]["text"]
    for k, words in (("6.1", ("same entry time", "within 5 s", "same exit reason", "bug")), ("6.2", ("1 micro", "2 ticks or less", "missed or rejected")),
                     ("6.3", ("5 clean trades", f"{size} micros")), ("6.4", ("10, 20, 30 and 40", "75th", "cut size", "95th", "the hard alarm")),
                     ("6.5", ("40 trades", "half", "$40 a micro", "$20 a micro")), ("6.6", ("the soft alarm is a review", "three yes", "carry on")), ("6.9", ("hard alarm", "not a deletion", "last 5 months positive", "last 12 months positive", "last 3 months above")),
                     ("6.7", ("only the size may change", "never the rule")),
                     ("6.8", ("3 attempts", "$345", "does not retire"))):
        assert all(w in L[k]["text"] for w in words), (k, L[k]["text"])
    assert (r["account"], r["variant"], r["attempts"], r["fee_budget"]) == (sim["account"], "v_mix", 3, 345.0)       # line 5.4, written on the card
    assert r["size"] == {"stage_a": 1, "stage_b": size} == {"stage_a": R.template("sizes")["stage_a"], "stage_b": size}
    hist = r["history"]
    assert (hist["trades"], hist["days"], hist["avg_trade_micro"], hist["avg_trade"]) == (44, 44, 40.0, 40.0 * size)
    t = r["table"]
    assert (t["percentiles"], t["runs"], t["size"], [x["after"] for x in t["rows"]]) == ([50, 75, 90, 95, 99], 1000, size, [10, 20, 30, 40])
    led = PO.ledger(PO.cell(PO.handed("ec_card", ROOT), "v_mix"), size, PS.load_rules(FREE))
    assert t["rows"] == EC.table(EC.runs(led))["rows"], "the table is the Monte Carlo of its own test-period trades at the simulator's size"
    for x in t["rows"]:
        assert x["drawdown"] == sorted(x["drawdown"]) and x["pnl"] == sorted(x["pnl"], reverse=True) and x["drawdown"][1] < x["drawdown"][3]
    text = r["text"].splitlines()
    assert text[0].startswith("EVAL CARD of ec_card") and sim["account"]["label"] in text[0] and all(x["text"] in text for x in r["lines"])
    assert any(ln.startswith("DRAWDOWN TABLE") for ln in text) and any(ln.startswith("P&L") for ln in text) and sum(ln.startswith("after ") for ln in text) == 8
    assert "3 attempts" in r["text"] and "Stage A: 1 micro" in r["text"] and f"Stage B: {size} micros" in r["text"] and r["notes"] == [] and "NOTE" not in r["text"]
    assert by(sim)["5.5"]["passed"] is True and by(sim)["5.3"]["passed"] is None
    f = ROOT / "ec_card" / "eval.json"
    assert r["saved"] == [str(f)] and read(f)["lines"] == r["lines"] and read(f)["table"] == t and r["fills"] == [] == read(f)["fills"]
    idea = IS.read_idea("ec_card", ROOT)
    assert (idea["status"], idea["phase"]) == ("proven_on_history", 6) and [x["line"] for x in idea["lines"]] == SIX and idea["next"] == r["next"]
    assert "1 micro" in r["next"] and "--fills" in r["next"]
    assert card("ec_card")["table"] == t, "the same seed, the same table"


def test_the_card_stands_on_one_account():
    ready("ec_two", FREE)
    assert card("ec_two")["account"]["id"] == FREE
    ready("ec_two", FLEX)                            # a later look at another account does not move the card ...
    assert card("ec_two")["account"]["id"] == FREE
    assert card("ec_two", account=FLEX)["account"]["id"] == FLEX and card("ec_two")["account"]["id"] == FLEX       # ... unless the owner says so
    refused(lambda: card("ec_two", account="apex-eod-50k@2026-09-27b"), "apex-eod-50k@2026-09-27b", "not on file")
    ready("ec_fresh", FREE)
    ready("ec_fresh", FLEX)
    assert card("ec_fresh")["account"]["id"] == FLEX, "no card yet: the simulator result saved last"
    assert by(ready("ec_weak", weak=True))["5.5"]["passed"] is False
    r = card("ec_weak")                              # on file is what the card asks for; odds under the bar are said on it, in so many words
    assert any(ln.startswith("NOTE: ") and "5.5" in ln and "under one strategy's bar" in ln for ln in r["text"].splitlines()) and r["notes"]


# ================================================================ (c) the lines on live fills

def test_line_6_1_live_equals_the_test():
    ready("ec_61")
    L = by(card("ec_61", stage_a(3)))
    assert L["6.1"]["passed"] is True and L["6.1"]["number"] == 0 and "3 live trades" in L["6.1"]["text"]
    assert R.rule("6.1")["also"]["entry_within_s"] == 5
    ok = card("ec_61", [fill(0, 3.0, late=5.0), fill(1, 3.0, late=-5.0),
                        fill(2, 3.0, reason="flat", replay={"entry_time": iso(SY.ms(LIVE[2], "09:45") + 2000), "exit_reason": "eod"}),
                        fill(3, 3.0, reason="time", replay={"entry_time": iso(SY.ms(LIVE[3], "09:45") + 2000), "exit_reason": "flat"})])
    assert by(ok)["6.1"]["passed"] is True and ok["mismatches"] == [], "5 seconds either way is the same entry; the clock is one exit reason"
    bad = card("ec_61", [fill(0, 3.0), fill(1, 3.0, late=5.001), fill(2, -4.0, reason="sl", replay={"entry_time": iso(SY.ms(LIVE[2], "09:45") + 2000), "exit_reason": "tp"}),
                         fill(3, 3.0, replay={"no_trade": True}), fill(4, 3.0, reason="trail", replay={"entry_time": iso(SY.ms(LIVE[4], "09:47")), "exit_reason": "bars"})])
    L = by(bad)
    assert L["6.1"]["passed"] is False and L["6.1"]["number"] == 4 and L["6.1"]["text"].startswith("6.1 FAIL ")
    assert [(m["trade"], m["fixed"]) for m in bad["mismatches"]] == [(2, None), (3, None), (4, None), (5, None)]
    why = {m["trade"]: m["why"] for m in bad["mismatches"]}
    assert why[2] == "entered 5.001 s after the test" and why[3] == "ended by its stop (sl), the test by its target (tp)" and "did not trade" in why[4]
    assert why[5] == "entered 118 s before the test; ended by trail, the test by bars"
    assert all(f"#{k}" in bad["text"] for k in (2, 3, 4, 5)) and "bug" in bad["next"]
    assert bad["live"]["stage_a"]["clean"] == 1, "a trade that does not equal the test is not a clean trade"
    part = by(card("ec_61", [fill(0, 3.0), fill(1, 3.0, replay=None)]))["6.1"]     # one replay is not on file yet: not judged, never a pass
    assert part["passed"] is None and "1 of the 2" in part["text"] and "no replay" in part["text"]
    mended = card("ec_61", [fill(0, 3.0), fill(1, 3.0, late=30.0, fixed="the desk clock was 30 s off; set right on 2026-10-07"), fill(2, 3.0)])
    assert by(mended)["6.1"]["passed"] is True and [(m["trade"], bool(m["fixed"])) for m in mended["mismatches"]] == [(2, True)]
    assert mended["live"]["stage_a"]["clean"] == 2, "a mismatch that was fixed stops failing the line; it is still not a clean trade"


def test_line_6_2_fills_are_close_to_the_test():
    ready("ec_62")
    need = R.need("6.2")
    assert (need["micros"], need["entry_slip_ticks"], need["missed_or_rejected"]) == (1, 2, 0)
    slips = lambda *v: [fill(i, 3.0, slip=s) for i, s in enumerate(v)]  # noqa: E731
    at = by(card("ec_62", slips(1.0, 2.0, 3.0, 2.0)))["6.2"]
    assert at["passed"] is True and at["number"] == 2.0 and "2 ticks" in at["text"], "2 ticks or less: 2.0 is a pass"
    over = by(card("ec_62", slips(1.0, 2.0, 3.0, 2.0, 2.5)))["6.2"]
    assert over["passed"] is False and over["number"] == 2.1 and over["text"].startswith("6.2 FAIL ")
    assert by(card("ec_62", slips(-1.0, 0.0, 4.0)))["6.2"]["number"] == 1.0, "a better fill counts for what it is"
    for word in ("missed", "rejected"):
        r = card("ec_62", [fill(0, 3.0), {"status": word, "entry_time": iso(SY.ms(LIVE[1], "09:45")), "side": "short"}, fill(2, 3.0)])
        L = by(r)
        assert L["6.2"]["passed"] is False and f"1 {word}" in L["6.2"]["text"] and L["6.1"]["passed"] is False and r["mismatches"][0]["trade"] == 2
        assert (r["live"]["trades"], r["live"]["orders"]) == (2, 1) and "start stage A again" in r["next"]
    unknown = by(card("ec_62", [fill(0, 3.0), fill(1, 3.0, slip=None)]))["6.2"]
    assert unknown["passed"] is None and "no entry slip" in unknown["text"]
    tick = card("ec_62", [fill(0, 3.0, slip=None, trigger_price=20000.0), fill(1, 3.0, slip=None, trigger_price=20000.75, side="short")])
    assert by(tick)["6.2"]["number"] == 1.5, "without the desk's number: the fill against its trigger, in ticks of the market, worse = positive"
    late = by(card("ec_62", stage_a() + at_size([5.0], 4)))["6.2"]
    assert late["passed"] is True and "5 trades" in late["text"], "line 6.2 is stage A's: a trade at size is not in its average"


def test_line_6_3_stage_a_is_passed_after_five_clean_trades():
    size = ready("ec_63")["chosen"]["eval"]["size"]
    assert R.need("6.3")["clean_trades"] == 5
    four = card("ec_63", stage_a(4))
    assert marks(four) == [True, True, None, None, None, None, None, None, None] and by(four)["6.3"]["number"] == 4 and "4 of 5" in by(four)["6.3"]["text"]
    assert four["live"]["stage_a"] == {"trades": 4, "clean": 4, "passed": False, "slip": 1.0} and "1 micro" in four["next"]
    five = card("ec_63", stage_a(5))
    assert marks(five)[:3] == [True, True, True] and by(five)["6.3"]["number"] == 5 and f"{size} micros" in by(five)["6.3"]["text"]
    assert five["live"]["stage_a"]["passed"] is True and five["live"]["stage_b"]["trades"] == 0 and f"{size} micros" in five["next"]
    big = card("ec_63", stage_a(4) + [fill(4, 30.0, size=10)] + [fill(5, 3.0)])
    assert by(big)["6.3"]["passed"] is True and big["live"]["stage_a"] == {"trades": 6, "clean": 5, "passed": True, "slip": 1.0}
    assert "not at 1 micro" in big["text"], "a trade at another size before stage A is passed is not one of the 5"
    wait = card("ec_63", [fill(i, 3.0, slip=4.0) for i in range(6)])               # 6 trades that equal the test, but the fills are not close to it
    assert marks(wait)[:3] == [True, False, None] and "6.2" in by(wait)["6.3"]["text"] and wait["live"]["stage_a"]["passed"] is False
    assert wait["live"]["stage_b"]["trades"] == 0, "no trade is read at size before stage A is passed"


def test_line_6_4_the_live_drawdown_on_the_table():
    sim = ready("ec_64")
    size = sim["chosen"]["eval"]["size"]
    t = {x["after"]: x for x in card("ec_64")["table"]["rows"]}
    cut, pause = t[10]["drawdown"][1], t[10]["drawdown"][3]
    assert 0 < cut < pause
    nine = card("ec_64", stage_a() + at_size([-1.0] * 9, size))
    assert by(nine)["6.4"]["passed"] is None and "9 of 10" in by(nine)["6.4"]["text"] and nine["live"]["stage_b"]["reads"] == []
    reads = lambda first: card("ec_64", stage_a() + at_size([first] + [1.0] * 9, size))  # noqa: E731
    under, at, over, most = reads(-(cut - 0.01)), reads(-cut), reads(-(pause - 0.01)), reads(-pause)
    for r, zone, passed in ((under, "carry on", None), (at, "cut size", None), (over, "cut size", None), (most, "the hard alarm", False)):
        got = r["live"]["stage_b"]["reads"]
        assert [(x["after"], x["zone"], x["cut"], x["pause"]) for x in got] == [(10, zone, cut, pause)] and by(r)["6.4"]["passed"] is passed, (zone, got)
        assert zone in by(r)["6.4"]["text"] and r["live"]["stage_b"]["trades"] == 10
    assert under["live"]["stage_b"]["reads"][0]["drawdown"] == cut - 0.01 and at["live"]["stage_b"]["reads"][0]["drawdown"] == cut
    assert by(most)["6.4"]["text"].startswith("6.4 FAIL ") and "6.9" in most["next"] and "SWITCH THE STRATEGY OFF" in most["next"] and "cut" in at["next"].lower()
    # a cut size reads on the same table: the live trades are scaled to the table's size
    small, between = max(1, size // 3), (cut + pause) / 2
    less = card("ec_64", stage_a() + at_size([-between * small / size] + [0.01] * 9, small))["live"]["stage_b"]
    assert less["reads"][0]["zone"] == "cut size" and abs(less["reads"][0]["drawdown"] - between) < 1e-6 and abs(less["drawdown"] - between) < 1e-6
    # the reads are after 10, 20, 30 and 40 trades, each against its own row; under the 95th at all four = the line is true
    deep = t[40]["drawdown"][3]
    slow = card("ec_64", stage_a() + at_size([0.0] * 25 + [-deep] + [1.0] * 14, size))
    got = slow["live"]["stage_b"]["reads"]
    assert [x["after"] for x in got] == [10, 20, 30, 40] and [x["zone"] for x in got[:2]] == ["carry on", "carry on"] and got[3]["zone"] == "the hard alarm"
    assert got[2]["drawdown"] == deep == got[3]["drawdown"] and by(slow)["6.4"]["passed"] is False
    fine = card("ec_64", stage_a() + at_size([-(cut - 0.01)] + [1.0] * 39, size))
    assert by(fine)["6.4"]["passed"] is True and [x["zone"] for x in fine["live"]["stage_b"]["reads"]] == ["carry on"] * 4
    trimmed = card("ec_64", stage_a() + at_size([-cut] + [cut + 1.0] + [1.0] * 38, size))
    assert by(trimmed)["6.4"]["passed"] is True and trimmed["live"]["stage_b"]["reads"][0]["zone"] == "cut size", "a cut is an order followed, not a failed line"


def test_line_6_9_the_recovery_after_a_hard_alarm_is_read_on_the_testers_replay():
    day = lambda y, m, d=15: dt.date(y, m, d)  # noqa: E731
    hist = [(day(2025, 7 + i) if i < 6 else day(2026, i - 5), 10.0) for i in range(15)]         # Jul 2025 .. Sep 2026: $10 a micro a month
    # recovered: the last 5 and the last 12 months above $0, and the last 3 months a month above the pace of the whole record
    r = EC.recovery(hist, [(day(2026, 10), 20.0), (day(2026, 11), 20.0), (day(2026, 12), 20.0)])
    assert r["passed"] is True and (r["end"], r["start"]) == ("2026-12-15", "2025-07-15") and r["positive"] == {"5": 80.0, "12": 150.0}
    assert r["pace"]["recent"] == 20.0 and 12.0 < r["pace"]["long_run"] < 13.0 and R.need("6.9") == {"positive_months": [5, 12], "above_pace_months": 3}
    # not recovered: a replay that loses (the last 5 months under $0), or one that only matches its old pace
    assert EC.recovery(hist, [(day(2026, 10), -30.0), (day(2026, 11), -30.0), (day(2026, 12), -10.0)])["passed"] is False
    slow = EC.recovery(hist, [(day(2026, 10), 5.0), (day(2026, 11), 5.0), (day(2026, 12), 5.0)])
    assert slow["passed"] is False and slow["positive"]["5"] > 0 and slow["pace"]["recent"] < slow["pace"]["long_run"]
    # a record shorter than the 12 months the line looks back over: not judged
    assert EC.recovery(hist[10:], [(day(2026, 10), 20.0)])["passed"] is None
    assert EC._back(dt.date(2026, 3, 31), 1) == dt.date(2026, 2, 28) and EC._back(dt.date(2026, 1, 15), 5) == dt.date(2025, 8, 15)
    # the replay as it is sent: beside the fills; a trade's New York date, its net a micro
    assert EC.since_stop([{"exit_time": "2026-10-06T15:30:00-04:00", "net": 60.0, "size": 3}, {"exit_time": "2026-10-05T23:30:00+00:00", "net": -8.0, "size": 2}]) == [
        (dt.date(2026, 10, 5), -4.0), (dt.date(2026, 10, 6), 20.0)]
    for bad in ([], [{"exit_time": "2026-10-06T15:30:00-04:00", "net": 1.0}], [{"exit_time": "2026-10-06T15:30:00", "net": 1.0, "size": 1}],
                [{"exit_time": "2026-10-06T15:30:00-04:00", "net": 1.0, "size": 0}], "none"):
        refused(lambda bad=bad: EC.since_stop(bad), "replay_since_stop")
    # on the card: a hard alarm stands (6.4), and line 6.9 is read on the replay sent with the fills
    sim = ready("ec_69")
    size = sim["chosen"]["eval"]["size"]
    t = {x["after"]: x for x in card("ec_69")["table"]["rows"]}
    stopped = stage_a() + at_size([-t[10]["drawdown"][3]] + [1.0] * 9, size)
    plain = card("ec_69", stopped)
    assert by(plain)["6.4"]["passed"] is False and by(plain)["6.9"]["passed"] is None and by(plain)["6.9"]["text"].startswith("6.9 n/a  a rule to follow")
    early = EC.card("ec_69", {"fills": stopped, "replay_since_stop": [{"exit_time": "2025-12-15T10:00:00-05:00", "net": 5.0 * size, "size": size}]}, ROOT)
    L = by(early)["6.9"]                                                           # the hand-made test range starts 2025-07-01: under 12 months on record
    assert L["passed"] is None and "not judged: the record is" in L["text"] and (L["recovery"]["end"], L["recovery"]["start"]) == ("2025-12-15", SY.SPAN[0])
    assert "SWITCH THE STRATEGY OFF" in early["next"] and "does not show it yet" in early["next"]
    sent = EC.card("ec_69", {"fills": stopped, "replay_since_stop": [{"exit_time": "2026-12-15T10:00:00-05:00", "net": -5.0 * size, "size": size}]}, ROOT)
    L = by(sent)["6.9"]
    assert L["passed"] is False and L["text"].startswith("6.9 FAIL the tester's replay since the stop, to 2026-12-15") and L["recovery"]["positive"] == {"5": -5.0, "12": -5.0}
    assert "does not show it yet" in sent["next"] and sent["status"] != "proven_live"
    back = EC.card("ec_69", {"fills": stopped, "replay_since_stop": [{"exit_time": f"2026-{m}-15T10:00:00-05:00", "net": 900.0 * size, "size": size} for m in (10, 11, 12)]}, ROOT)
    assert by(back)["6.9"]["passed"] is True and by(back)["6.4"]["passed"] is False and "may come back" in back["next"] and "new attempt" in back["next"]


def test_line_6_5_the_average_trade_against_half_of_the_tests():
    size = ready("ec_65")["chosen"]["eval"]["size"]
    need = R.need("6.5")
    assert (need["after_trades"], need["share_of_history"]) == (40, 0.5)
    early = card("ec_65", stage_a() + at_size([20.0 * size] * 39, size))
    assert by(early)["6.5"]["passed"] is None and "39 of 40" in by(early)["6.5"]["text"]
    with SY.no_engine():
        half = card("ec_65", stage_a() + at_size([20.0 * size] * 40, size))        # the test made $40 a micro a trade: half of it is $20
    L = by(half)
    assert L["6.5"]["passed"] is True and L["6.5"]["number"] == 20.0 and L["6.5"]["need"] == 20.0 and "half" in L["6.5"]["text"]
    less = card("ec_65", stage_a() + at_size([20.0 * size] * 39 + [20.0 * size - 1.0], size))
    assert by(less)["6.5"]["passed"] is False and by(less)["6.5"]["number"] < 20.0 and "6.6" in less["next"]
    more = card("ec_65", stage_a() + at_size([20.0 * size] * 40 + [-900.0 * size] * 3, size))
    assert by(more)["6.5"]["passed"] is True and by(more)["6.4"]["passed"] is True, "the lines are read on the first 40 trades at size"
    # every line that is read on live trades TRUE = PROVEN LIVE, as the app's idea store reads the saved card
    assert marks(half) == [True, True, True, True, True, None, None, None, None] and half["status"] == "proven_live" == IS.status("ec_65", ROOT)
    assert half["fills"] == stage_a() + at_size([20.0 * size] * 40, size) and read(ROOT / "ec_65" / "eval.json")["fills"] == more["fills"], "the orders read stay with the card"
    assert IS.read_idea("ec_65", ROOT)["phase"] == 6 and "PROVEN LIVE" in half["next"]
    assert (DRAFTS / "ec_65.py").read_text().splitlines()[1].startswith("# ec_65 · PROVEN LIVE · phase 6")
    assert card("ec_65", stage_a() + at_size([20.0 * size] * 39 + [20.0 * size - 1.0], size))["status"] == "proven_on_history", "the status is read off the card saved last"


# ================================================================ (d) the fills format

def test_the_fills_format_is_one_text_and_what_does_not_read_is_refused():
    for word in ("entry_time", "exit_time", "side", "size", "entry_price", "exit_price", "net", "exit_reason", "entry_slip_ticks", "trigger_price", "replay", "no_trade",
                 "missed", "rejected", "fixed", "oldest first", "UTC offset"):
        assert word in EC.FILLS, word
    assert EC.FILLS in EC.__doc__ and "%" not in EC.FILLS
    ready("ec_fmt")
    ok = fill(0, 3.0)
    for raw, words in (([ok], ("JSON object", "fills")), ({"trades": [ok]}, ("fills",)), ({"fills": ok}, ("list",)), ({"fills": ["a fill"]}, ("#1", "object")),
                       ({"fills": [{k: v for k, v in ok.items() if k != "net"}]}, ("#1", "net")), ({"fills": [{**ok, "size": 0}]}, ("#1", "size")),
                       ({"fills": [{**ok, "side": "up"}]}, ("#1", "side")), ({"fills": [{**ok, "entry_time": "2026-10-05 09:45"}]}, ("#1", "entry_time", "UTC offset")),
                       ({"fills": [{**ok, "net": "a lot"}]}, ("#1", "net")), ({"fills": [{**ok, "status": "maybe"}]}, ("#1", "status")),
                       ({"fills": [{**ok, "replay": {"entry_time": "soon", "exit_reason": "tp"}}]}, ("#1", "replay")),
                       ({"fills": [{**ok, "replay": {"exit_reason": "tp"}}]}, ("#1", "replay")),
                       ({"fills": [fill(1, 3.0), fill(0, 3.0)]}, ("#2", "oldest first")), ({"fills": [{**ok, "colour": "red"}]}, ("#1", "colour"))):
        refused(lambda: EC.card("ec_fmt", raw, ROOT), *words)
    assert not (ROOT / "ec_fmt" / "eval.json").exists(), "a refusal wrote a card"
    a, b = SY.ms(LIVE[0], "09:45") + 2000, SY.ms(LIVE[1], "09:45") + 2000
    desk = {**ok, "side": "Buy", "entry_time": a, "exit_time": a + 600_000, "replay": {"entry_time": a, "exit_reason": "TP "}}       # the desk's words; epoch milliseconds
    zulu = {**fill(1, 3.0, side="Sell"), "entry_time": dt.datetime.fromtimestamp(b / 1000, dt.timezone.utc).isoformat().replace("+00:00", "Z")}
    r = EC.card("ec_fmt", {"fills": [desk, zulu, {"status": "missed"}, {**fill(3, 3.0), "note": "a free word"}]}, ROOT)
    assert r["live"] == {**r["live"], "trades": 3, "orders": 1} and [m["trade"] for m in r["mismatches"]] == [3], "Buy / Sell, milliseconds, a Z and a bare missed order are read"
    assert EC.card("ec_fmt", {"fills": []}, ROOT)["live"]["trades"] == 0 and marks(EC.card("ec_fmt", {"fills": []}, ROOT)) == [None] * 9


# ================================================================ (e) the command

def _run(argv: list, stdin: str = "") -> tuple:
    out, keep = io.StringIO(), sys.stdin
    sys.stdin = io.StringIO(stdin)
    try:
        with contextlib.redirect_stdout(out):
            rc = C.main(argv)
    finally:
        sys.stdin = keep
    return rc, out.getvalue()


def test_the_command_line_as_the_connector_writes_it():
    size = ready("ec_cli")["chosen"]["eval"]["size"]
    tail = [f"--root={ROOT}", "--json"]
    q = subprocess.run([sys.executable, str(W / "bp.py"), "eval-card", "ec_cli", *tail], capture_output=True, text=True, timeout=280, cwd=str(W),
                       stdin=subprocess.DEVNULL, env={**os.environ})
    assert q.returncode == 0 and q.stdout.count("\n") == 1, (q.stdout[-400:], q.stderr[-1500:])
    r = json.loads(q.stdout)
    assert tuple(r)[:len(CONTRACT)] == CONTRACT and [x["line"] for x in r["lines"]] == SIX and marks(r) == [None] * 9 and r["size"]["stage_b"] == size
    fills = stage_a() + at_size([20.0 * size] * 40, size)
    q = subprocess.run([sys.executable, str(W / "bp.py"), "eval-card", "ec_cli", "--fills=-", *tail], capture_output=True, text=True, timeout=280, cwd=str(W),
                       input=json.dumps({"fills": fills}), env={**os.environ})
    assert q.returncode == 0 and q.stdout.count("\n") == 1, (q.stdout[-400:], q.stderr[-1500:])
    r = RESULTS["cli"] = json.loads(q.stdout)
    assert marks(r) == [True] * 5 + [None] * 4 and r["status"] == "proven_live" and r["live"]["trades"] == 45
    f = TMP / "fills.json"
    f.write_text(json.dumps({"fills": stage_a(2)}))
    rc, out = _run(["eval-card", "ec_cli", f"--fills={f}", f"--account={FREE}", *tail])
    assert rc == 0 and json.loads(out)["live"]["trades"] == 2 and json.loads(out)["status"] == "proven_on_history"
    for argv, stdin, word in ((["eval-card", "ec_cli", "--fills=-"], "", "no fills"), (["eval-card", "ec_cli", "--fills=-"], "{not json", "JSON"),
                              (["eval-card", "ec_cli", f"--fills={TMP / 'nowhere.json'}"], "", "not there"), (["eval-card", "ec_nobody"], "", "no idea"),
                              (["eval-card"], "", "name"), (["eval-card", "ec_cli", "--account=nobody@1"], "", "nobody@1")):
        rc, out = _run([*argv, *tail], stdin)
        got = json.loads(out)
        assert rc == 2 and got["ok"] is False and word in got["error"] and got["command"] == "eval-card" and "not built yet" not in got["error"], (argv, got["error"])
    rc, out = _run(["eval-card", "ec_cli", f"--root={ROOT}"])                      # for a person: the card, then the next step
    assert rc == 0 and out.startswith("EVAL CARD of ec_cli") and "\nNEXT: " in out and "DRAWDOWN TABLE" in out
    try:                                             # the help of the command carries the format, word for word
        with contextlib.redirect_stdout(io.StringIO()) as helped:
            C.main(["eval-card", "--help"])
    except SystemExit as e:
        assert e.code == 0
    assert EC.FILLS in helped.getvalue()


CONNECTOR = r'''
import json, sys
sys.path.insert(0, sys.argv[1])
from homebase.claude_mcp import tools
from homebase.claude_mcp.client import Client, ToolError
box, out = tools.Toolbox(Client("http://127.0.0.1:1"), sleep=lambda s: None), []
for tool, args in json.loads(sys.argv[2]):
    try:
        out.append(["ok", box.call(tool, args)])
    except ToolError as e:
        out.append(["error", str(e)])
print(json.dumps(out))
'''


def test_the_apps_connector_against_this_toolkit():
    if not APP_PYTHON.exists():
        import pytest
        pytest.skip("the app's Python is not there")
    size = ready("ec_conn")["chosen"]["eval"]["size"]
    proven("ec_bare")
    calls = [["blueprint_eval_card", {"name": "ec_conn"}], ["blueprint_eval_card", {"name": "ec_conn", "fills": stage_a() + at_size([20.0 * size] * 12, size)}],
             ["blueprint_eval_card", {"name": "ec_bare"}], ["blueprint_eval_card", {"name": "ec_conn", "fills": [{"date": "2026-10-01", "side": "long", "net": 120.0}]}]]
    q = subprocess.run([str(APP_PYTHON), "-B", "-c", CONNECTOR, str(S.REPO), json.dumps(calls)], capture_output=True, text=True, timeout=600, cwd=str(TMP),
                       env={**os.environ, "HOMEBASE_IDEAS_ROOT": str(ROOT), "HOMEBASE_DRAFTS_DIR": str(DRAFTS), "HOMEBASE_BP": str(W / "bp.py"),
                            "HOMEBASE_BP_PYTHON": sys.executable})
    assert q.returncode == 0, q.stderr[-2000:]
    (ok, text), (ok2, live), (bad, why), (bad2, why2) = RESULTS["connector"] = json.loads(q.stdout)
    out = text.splitlines()
    assert ok == "ok" and out[0] == "Blueprint eval-card · ec_conn · PROVEN ON HISTORY · phase 6" and "DRAWDOWN TABLE" in text
    assert "Lines: 0 passed · 0 FAILED · 9 not judged or do not apply (6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9)" in out      # (the connector's word for a line that is not judged yet)
    assert all(text.count(f"\n{k} n/a ") == 1 for k in SIX) and any(ln.startswith("Saved: ") and "eval.json" in ln for ln in out)
    assert ok2 == "ok" and "Lines: 3 passed · 0 FAILED · 6 not judged or do not apply (6.4, 6.5, 6.6, 6.7, 6.8, 6.9)" in live.splitlines() and "carry on" in live
    assert bad == "error" and why.startswith("Refused (blueprint eval-card): ") and "bp.py sim ec_bare" in why
    assert bad2 == "error" and "#1" in why2 and "entry_time" in why2, "a fill that is not in the format is refused with the field named"


def test_nothing_was_written_outside_the_temp_folder():
    assert BEFORE == {"ideas": _listing(HOME / "ideas"), "drafts": _listing(HOME / "strategies")}
    assert not (TMP / "ideas_env").exists(), "a command fell back to the environment's idea folder"


if __name__ == "__main__":
    import time
    rc = 0
    for name, t in [(k, v) for k, v in list(globals().items()) if k.startswith("test_") and callable(v)]:
        t0 = time.monotonic()
        setup_function()
        try:
            t()
            print(f"PASS {name} ({time.monotonic() - t0:.1f} s)", flush=True)
        except AssertionError as e:
            rc = 1
            print(f"FAIL {name}\n{e}", flush=True)
        except Exception as e:  # noqa: BLE001 - pytest.skip outside pytest, a crash: said, and the run goes on
            skip = type(e).__name__ == "Skipped"
            rc = rc if skip else 1
            print(f"{'SKIP' if skip else 'CRASH'} {name}: {type(e).__name__}: {e}", flush=True)
        finally:
            teardown_function()
    if "card" in RESULTS:
        print("\n" + RESULTS["card"]["text"] + "\nNEXT: " + RESULTS["card"]["next"])
    if "connector" in RESULTS:
        print("\nTHE CONNECTOR, blueprint_eval_card with 17 live fills:\n" + RESULTS["connector"][1][1])
    sys.exit(rc)
