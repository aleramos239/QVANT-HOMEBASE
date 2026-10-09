"""LOCK of the pipeline's PORTFOLIO BUILDER (blueprint/pipe_portfolio.py, `bp.py pipe portfolio`) -- the design's stage 8.
HAND-MADE TRADES (tests/blueprint_synth.py): no tape is read and no engine run is made. Parts 1-9 hand the builder its
strategies as plain lists typed here; part 10 reads a hand-made book from a temp pipeline root (the library's own store
format, dated by hand); part 11 reads the ONE strategy the end-to-end test's tiny real run leaves, with that test's own
harness. Few paths and a fixed seed: seconds.

 1. The shape of the answer; the bar, the days and the account rules are pipeline.json's and the account's rule file's.
 2. ONE strategy: the "mix" is that strategy alone, held against the bar. Its numbers are propodds' walks on the "live is
    worse" row cut at the bar's days -- with the prop check's day count they ARE the prop check's (pipe_prop.odds).
 3. A pair that covers each other's losing days: each member raises the eval odds, the pair is the best mix, it meets the bar.
    The members are read on the session days they share.
 4. A member that does not raise the mix's eval odds is left out: the mix with it is not allowed, the best mix is without it.
 5. No two from the same family on the same market: that mix is never tried. Another market, or another family: it is.
 6. The fast-trades rule: at most the file's share of the profit from trades held the file's seconds or less.
 7. The biggest-day rule of an account whose rule file has one (LucidFlex); an account without one asks nothing.
 8. Ranking: the mixes that are allowed and hold the account's rules first, then the one nearest the bar on its weaker
    number; the distance from the bar; the bar is "or more".
 9. Apex (pipeline.json portfolio.one_side and funded_only, the design's section 13): a strategy whose entry rule rests
    orders on both sides (the block list's word) is left out there and nowhere else; the mix is judged on the payout odds
    alone, and those are what a member must raise. An empty book says so.
10. The command, on a hand-made book in a temp root: every account of the book cards, or the one asked for; one file an
    account under <root>/portfolios and nothing else; a card whose trades cannot be read is named, not fatal.
11. The real tiny book of tests/test_pipe_end_to_end.py: its one strategy, read without a write.
12. No number is typed in the module.

  pytest tests/test_pipe_portfolio.py -q
"""
from __future__ import annotations

import contextlib
import copy
import io
import json
import sys
import tempfile
from pathlib import Path

import pytest

W = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(W), str(Path(__file__).resolve().parent)]
import judge as J  # noqa: E402
import run_menus as RM  # noqa: E402
from blueprint import api  # noqa: E402
from blueprint import blocklist  # noqa: E402
from blueprint import cli as C  # noqa: E402
from blueprint import pipe_portfolio as PF  # noqa: E402
from blueprint import pipe_prop as PP  # noqa: E402
from blueprint import pipe_rules as P  # noqa: E402
from blueprint import pipe_runner as RN  # noqa: E402
from blueprint import pipe_store as PS  # noqa: E402
from blueprint import propodds as PO  # noqa: E402
from blueprint import runner as RUN  # noqa: E402

import blueprint_synth as SY  # noqa: E402
import library as LB  # noqa: E402

APP = PO.app()
IS = api.ideastore()
FILE = P.FILE
PRO, FLEX, APEX = "lucid-pro-50k-no-dll@2026-09-27b", "lucid-flex-50k@2026-09-27", "apex-legacy-300k@2026-09-28"
CAL = SY.weekdays()                                 # 44 hand-made session days
N, SEED = 2000, 7                                   # the paths of a test, and their seed
KEYS = {"account", "need", "judged", "rules", "notes", "members", "left_out", "unread", "twins", "skipped", "mixes", "best", "gap", "meets", "paths", "seed", "text"}
MIX = {"members", "days", "size", "payout_size", "eval", "payout", "table", "rules", "without", "drags", "allowed", "rules_hold", "margin", "meets"}
NO_GAP = {"eval": 0.0, "payout": 0.0, "rules": [], "drags": []}
FAMILY = {"up": "fvg", "down": "gap", "drag": "liq", "weak": "pinbar", "steady": "rsi2", "lumpy": "supertrend", "fast": "vwap_z", "slow": "donchian"}      # each its own: no two are kept apart by accident


@pytest.fixture(autouse=True)
def nowhere_real(monkeypatch, tmp_path):
    """A call that forgets its root lands in the temp folder: the app's idea folder, its Lab drafts and the pipeline root."""
    monkeypatch.setenv("HOMEBASE_IDEAS_ROOT", str(tmp_path / "ideas_env"))
    monkeypatch.setenv(IS.draftstore.ENV, str(tmp_path / "drafts"))
    monkeypatch.setenv(PS.ENV, str(tmp_path / "stray"))
    yield
    P.FILE = FILE
    P._all.cache_clear()


@contextlib.contextmanager
def with_file(**portfolio):
    """While it is open, pipeline.json is a temp copy with other `portfolio` numbers."""
    p = copy.deepcopy(json.loads(FILE.read_text(encoding="utf-8")))
    p["portfolio"].update(portfolio)
    with tempfile.TemporaryDirectory() as tmp:
        P.FILE = Path(tmp) / "pipeline.json"
        P.FILE.write_text(json.dumps(p), encoding="utf-8")
        P._all.cache_clear()
        try:
            yield
        finally:
            P.FILE = FILE
            P._all.cache_clear()


def cells(rows: list) -> dict:
    """Hand-made trades as the packed arrays of a store's cell (what judge.cellx hands over)."""
    return LB.pack(sorted(rows, key=lambda t: (t["exit_ms"], t["entry_ms"])))


def secs(rows: list, s: int) -> list:
    """The same trades, each held `s` seconds."""
    return [{**t, "exit_ms": t["entry_ms"] + s * 1000} for t in rows]


def M(name: str, rows: list, family: str = None, market: str = "NQ", cal=CAL) -> dict:
    """A book strategy as the builder reads it (pipe_portfolio.member's shape), its unseen-day trades typed by hand."""
    return {"name": name, "family": family or FAMILY[name], "market": market, "session": "nyam", "bar": "5", "box": "v", "trades": len(rows), "x": cells(rows),
            "calendar": list(cal)}


def each(win: float, loss: float, odd: bool, at: str, mae: float = 10.0) -> list:
    """One trade a session day: `win` dollars a micro on every other day (the odd ones, or the even ones), `loss` on the rest."""
    return [SY.trade(d, win if (i % 2 == 1) == odd else loss, mae, at=at) for i, d in enumerate(CAL)]


UP = each(110.0, -70.0, True, "09:45")              # +$110 a micro, then -$70: $20 a day on average, a losing day every other day
DOWN = each(110.0, -70.0, False, "10:15")           # the same on the OTHER days: together +$40 a micro-pair EVERY day
DRAG = [SY.trade(d, 6.0 if i % 2 else -5.0, 120.0, at="10:40") for i, d in enumerate(CAL)]      # next to nothing a day, far under water first
WEAK = [SY.trade(d, 4.0 if i % 5 else -2.0, 2.0) for i, d in enumerate(CAL)]                    # it makes money, far too slowly for 5 days
STEADY = [SY.trade(d, 40.0, 2.0, at="11:00") for d in CAL]                                      # +$40 a micro every day
LUMPY = [SY.trade(d, 500.0 if i == 20 else 5.0, 2.0) for i, d in enumerate(CAL)]                # one day is most of its profit


def build(members: list, account: str = PRO) -> dict:
    return PF.build(account, members=members, paths=N, seed=SEED)


def mix(r: dict, *names) -> dict:
    """The mix of exactly these members among the ones tried."""
    return next(m for m in r["mixes"] if m["members"] == list(names))


def in_order(m: dict) -> bool:
    return m["allowed"] and m["rules_hold"]


# ================================================================ 1. the shape, and where the numbers come from

def test_the_answer_and_where_its_numbers_come_from():
    r, rules = build([M("up", UP), M("down", DOWN)]), APP.load_rules(PRO)
    assert set(r) == KEYS and all(set(m) == MIX for m in r["mixes"])
    assert r["need"] == {k: P.need("portfolio", k) for k in ("eval", "payout")} == {"eval": {"days": 5, "odds": 0.6}, "payout": {"days": 14, "odds": 0.75}}
    assert r["account"] == {"id": PRO, "name": rules["name"], "confirmed": True} and (r["paths"], r["seed"], r["judged"]) == (N, SEED, ["eval", "payout"])
    assert r["rules"] == {"fast": {"seconds": P.need("box", "fast_seconds"), "share": P.need("portfolio", "fast_share")}, "biggest_day": rules["consistency"],
                          "one_side": False, "funded_only": False} and r["notes"] == []
    assert (P.need("box", "fast_seconds"), P.need("portfolio", "fast_share"), rules["consistency"]) == (5, 0.5, None)
    assert [m["name"] for m in r["members"]] == ["up", "down"] and all("x" not in m and "calendar" not in m for m in r["members"])
    assert set(r["members"][0]) == {"name", "family", "market", "session", "bar", "box", "trades", "both_sides"}
    assert sorted(m["members"] for m in r["mixes"]) == [["down"], ["up"], ["up", "down"]]      # every subset is tried
    assert r["best"] == r["mixes"][0] and r["meets"] == r["best"]["meets"] and (r["left_out"], r["unread"], r["twins"], r["skipped"]) == ([], [], [], [])
    json.dumps(r)                                   # plain JSON: it is saved as a file
    assert r == build([M("up", UP), M("down", DOWN)]), "the same paths, the same answer"
    assert PF.build(members=[M("up", UP)], paths=N, seed=SEED)["account"]["id"] == P.need("prop", "account") == PRO      # no account: the pipeline's own
    assert PF.build(members=[M("up", UP)])["paths"] == APP.N_PATHS and PF.build(members=[M("up", UP)])["seed"] == APP.SEED      # the app's own paths and seed


def test_the_accounts_are_the_pipelines_own_first_then_the_book_cards():
    assert PF.accounts() == [PRO, FLEX, APEX] == list(dict.fromkeys([P.need("prop", "account"), *P.need("prop", "book_accounts")]))
    for bad in ("no-such-account@2026-01-01", "lucid"):
        with pytest.raises(J.Refuse) as e:
            build([M("up", UP)], bad)
        assert repr(bad) in str(e.value) and PRO in str(e.value)


# ================================================================ 2. one strategy

def test_one_strategy_is_a_mix_of_one_held_against_the_bar():
    r = build([M("up", UP)])
    assert len(r["mixes"]) == 1 and r["best"] == r["mixes"][0]
    b, need = r["best"], r["need"]
    assert (b["members"], b["days"], b["without"], b["drags"], b["allowed"], b["rules_hold"]) == (["up"], len(CAL), {}, [], True, True)
    assert 0.2 < b["eval"] < 0.6 and 0.0 < b["payout"] < 0.75 and b["meets"] is False and r["meets"] is False
    assert b["margin"] == pytest.approx(min(b["eval"] / 0.6, b["payout"] / 0.75))
    assert r["gap"] == {"eval": pytest.approx(need["eval"]["odds"] - b["eval"]), "payout": pytest.approx(need["payout"]["odds"] - b["payout"]), "rules": [], "drags": []}
    text = r["text"].splitlines()
    assert text[0].startswith(f"{APP.load_rules(PRO)['name']} [{PRO}]: the best mix found does not meet the bar. It is up alone ({b['size']} micros for the eval, ")
    assert text[1] == (f"  eval: it passes the eval within 5 trading days {100 * b['eval']:.1f} % of the time (the bar: 60 % or more) -- "
                       f"{100 * (0.6 - b['eval']):.1f} points short")
    assert text[2] == (f"  payout: it reaches the maximum payout within 14 trading days {100 * b['payout']:.1f} % of the time (the bar: 75 % or more) -- "
                       f"{100 * (0.75 - b['payout']):.1f} points short")
    assert text[4] == f"  missing: {100 * (0.6 - b['eval']):.1f} points of eval odds; {100 * (0.75 - b['payout']):.1f} points of payout odds"
    assert text[5] == "  tried: 1 mix of 1 strategy" and len(text) == 6
    slow = build([M("weak", WEAK)])["best"]         # money, far too slowly: nothing inside the bar's days
    assert (slow["eval"], slow["payout"], slow["margin"], slow["meets"]) == (0.0, 0.0, 0.0, False)


def test_the_numbers_are_propodds_walks_on_the_live_is_worse_row_cut_at_the_bars_days():
    rules, x = APP.load_rules(PRO), cells(UP)
    b = build([M("up", UP)])["best"]
    ev, fu = PO.steps(rules)
    assert [t["size"] for t in b["table"]] == ev and [t["size"] for t in b["table"] if t["payout"] is not None] == fu
    for t in b["table"]:
        net, traded, opn, _ = PO.days(PO.ledger(x, t["size"], rules), rules, CAL)
        wnet, wopn = PO.worse(net, traded, opn)     # the "live is worse" row
        idx = PO.draws(len(net), N, PO.horizon(rules), SEED)
        p, tr, o = wnet[idx], traded[idx], wopn[idx]
        e, f = PO.eval_walk(p, tr, o, rules), PO.funded_walk(p, o, rules)       # the whole walk, read at the day
        assert t["eval"] == float(((e["outcome"] == PO.PASS) & (e["day"] <= 5)).mean()), t
        assert t["payout"] is None or t["payout"] == float(((f["max_payout_at"] > 0) & (f["max_payout_at"] <= 14)).mean()), t
    assert b["eval"] == max(t["eval"] for t in b["table"]) and b["size"] == next(t["size"] for t in b["table"] if t["eval"] == b["eval"])       # a tie: the smaller
    paid = [t for t in b["table"] if t["payout"] is not None]
    assert b["payout"] == max(t["payout"] for t in paid) and b["payout_size"] == next(t["size"] for t in paid if t["payout"] == b["payout"])


def test_with_the_prop_checks_day_count_one_strategy_reads_as_the_prop_check_reads_one_box():
    days = P.need("prop", "days")
    with with_file(eval={"days": days, "odds": 0.6}, payout={"days": days, "odds": 0.75}):
        for rows, rid in ((UP, PRO), (STEADY, PRO), (LUMPY, FLEX), (UP, APEX)):
            b, o = build([M("up", rows)], rid)["best"], PP.odds(cells(rows), CAL, rid, paths=N, seed=SEED)
            assert (b["eval"], b["payout"], b["size"], b["payout_size"], b["table"]) == (o["eval"], o["payout"], o["size"], o["payout_size"], o["table"]), rid
            assert o["eval"] + o["payout"] > 0.0, "(a reading with something in it)"


def test_open_losses_count():
    mll = APP.load_rules(PRO)["trailing_mll"]
    under = [SY.trade(d, 40.0, mll + 1.0, at="11:00") for d in CAL]     # STEADY, but every trade is a micro's whole drawdown under water first
    assert build([M("steady", STEADY)])["best"]["payout"] > 0.75
    b = build([M("steady", under)])["best"]
    assert (b["eval"], b["payout"]) == (0.0, 0.0), "busted on the first day at every size, whatever the days close at"


# ================================================================ 3. a pair that helps each other

def test_a_pair_that_covers_each_others_losing_days_is_the_best_mix_and_meets_the_bar():
    r = build([M("up", UP), M("down", DOWN)])
    pair, up, down = mix(r, "up", "down"), mix(r, "up"), mix(r, "down")
    assert pair["without"] == {"up": down["eval"], "down": up["eval"]}, "without a member = the rest, on the same days, at its own best size"
    assert pair["eval"] > max(up["eval"], down["eval"]) + 0.2 and pair["drags"] == [] and pair["allowed"] is True
    assert r["best"] == pair and pair["meets"] is True and r["meets"] is True and pair["eval"] >= 0.6 and pair["payout"] >= 0.75 and pair["margin"] >= 1.0
    assert r["gap"] == NO_GAP and up["meets"] is False and down["meets"] is False
    # every member at the same size step, inside the account's maximum FOR BOTH: 40 micros in the eval, 20 from the funded account's start
    assert [t["size"] for t in pair["table"]] == [1, 2, 3, 5, 7, 10, 15, 20] and [t["size"] for t in pair["table"] if t["payout"] is not None] == [1, 2, 3, 5, 7, 10]
    text = r["text"].splitlines()
    assert text[0].endswith(f"the best mix found MEETS THE BAR. It is up + down ({pair['size']} micros each for the eval, {pair['payout_size']} micros each on the funded "
                            "account; read on 44 session days they share).")
    assert text[1].endswith("-- at the bar") and text[2].endswith("-- at the bar")
    assert text[4] == (f"  each member must raise the eval odds: without up {100 * down['eval']:.1f} %, without down {100 * up['eval']:.1f} %; with all "
                       f"{100 * pair['eval']:.1f} %") and text[5:] == ["  missing: nothing", "  tried: 3 mixes of 2 strategies"]
    # ONE ledger: together no losing day, alone every other (the odds of the pair are read off that ledger)
    rules = APP.load_rules(PRO)
    both = PO.days(PO.together([cells(UP), cells(DOWN)], 5, rules, CAL), rules, CAL)[0]
    assert both.min() > 0 and PO.days(PO.ledger(cells(UP), 5, rules), rules, CAL)[0].min() < 0
    assert pair["table"] == PF.odds([cells(UP), cells(DOWN)], CAL, rules, N, SEED)["table"]


def test_the_members_are_read_on_the_session_days_they_share():
    half = CAL[:22]
    r = build([M("up", UP), M("down", [t for t in DOWN if t["date"] in half], cal=half)])
    pair = mix(r, "up", "down")
    assert (mix(r, "up")["days"], mix(r, "down")["days"], pair["days"]) == (44, 22, 22)
    alone = PF.odds([cells(UP)], half, APP.load_rules(PRO), N, SEED)["eval"]
    assert pair["without"]["down"] == alone != mix(r, "up")["eval"], "without a member: the rest ON THE MIX'S OWN DAYS, not on its own"
    r = build([M("up", UP, cal=CAL[:22]), M("down", DOWN, cal=CAL[22:])])                      # no day in common
    assert sorted(m["members"] for m in r["mixes"]) == [["down"], ["up"]] and [s["members"] for s in r["skipped"]] == [["up", "down"]]
    assert r["skipped"][0]["why"] == "they share no session day of their reads" and "nothing to read of: up + down (they share no session day" in r["text"]


# ================================================================ 4. a member that does not raise the eval odds

def test_a_member_that_does_not_raise_the_eval_odds_is_left_out():
    r = build([M("up", UP), M("down", DOWN), M("drag", DRAG)])
    assert len(r["mixes"]) == 7                                                                # every subset of three
    three, pair = mix(r, "up", "down", "drag"), mix(r, "up", "down")
    assert three["without"]["drag"] == pair["eval"] > three["eval"] and "drag" in three["drags"]
    assert three["allowed"] is False and three["meets"] is False
    assert mix(r, "up", "drag")["drags"] == ["drag"] and mix(r, "down", "drag")["drags"] == ["drag"]       # it drags whoever it is put with
    assert r["best"] == pair and r["best"]["allowed"] is True and "drag" not in r["best"]["members"] and r["meets"] is True
    order = [in_order(m) for m in r["mixes"]]
    assert order == sorted(order, reverse=True) and order.count(True) == 4, "the mixes that are not allowed come after every one that is"
    assert all(m["allowed"] is (not m["drags"]) for m in r["mixes"]) and all(m["allowed"] and m["without"] == {} for m in r["mixes"] if len(m["members"]) == 1)
    for m in r["mixes"]:                                                                       # the rule, as the module's docstring states it
        assert m["drags"] == [k for k in m["members"] if m["without"] and not m["eval"] > m["without"][k]]
    same = build([M("up", UP), M("copy", UP, "orb")])                                          # the same trades twice: equal odds are not higher odds
    twice = mix(same, "up", "copy")
    assert twice["eval"] == mix(same, "up")["eval"] == mix(same, "copy")["eval"] and twice["drags"] == ["up", "copy"] and twice["allowed"] is False
    assert same["best"]["members"] == ["up"], "equal odds: the smaller mix, and the first tried"
    lone = build([M("up", UP), M("drag", DRAG)])                                               # the best mix is still shown when a mix is not allowed
    assert lone["best"]["members"] == ["up"] and "drag" not in lone["gap"]["drags"]


# ================================================================ 5. the same family on the same market

def test_two_of_the_same_family_on_the_same_market_are_never_mixed():
    r = build([M("up", UP, "fvg", "NQ"), M("down", DOWN, "fvg", "NQ"), M("steady", STEADY, "gap", "NQ")])
    assert r["twins"] == [{"a": "up", "b": "down", "family": "fvg", "market": "NQ"}]
    tried = [m["members"] for m in r["mixes"]]
    assert sorted(tried) == sorted([["up"], ["down"], ["steady"], ["up", "steady"], ["down", "steady"]]), "neither the pair nor the three with the pair in it"
    assert "  tried: 5 mixes of 3 strategies; never together (the same family on the same market): up and down (fvg on NQ)" in r["text"].splitlines()
    r = build([M("up", UP, "fvg", "NQ"), M("down", DOWN, "fvg", "ES")])                        # the same family on ANOTHER market
    assert r["twins"] == [] and r["best"]["members"] == ["up", "down"]
    r = build([M("up", UP, "fvg", "NQ"), M("down", DOWN, "gap", "NQ")])                        # another family on the same market
    assert r["twins"] == [] and r["best"]["members"] == ["up", "down"]


# ================================================================ 6. the fast-trades rule

def test_at_most_half_the_profit_from_trades_held_5_seconds_or_less():
    r = build([M("fast", secs(UP, 4)), M("down", DOWN)])                                       # UP + DOWN again, UP's trades held 4 seconds
    fast, down, both = mix(r, "fast"), mix(r, "down"), mix(r, "fast", "down")
    assert fast["rules"]["fast"] == {"share": pytest.approx(1.0), "holds": False} and fast["rules_hold"] is False and fast["meets"] is False
    assert down["rules"]["fast"] == {"share": 0.0, "holds": True} and down["rules_hold"] is True
    assert both["rules"]["fast"] == {"share": pytest.approx(0.5), "holds": True} and both["rules_hold"] is True, "at most half: exactly half holds"
    assert r["best"] == both and both["meets"] is True and r["mixes"][-1] == fast, "a mix that breaks an account rule comes after the ones that hold them"
    assert fast["eval"] == build([M("up", UP)])["best"]["eval"], "the same money as held for ten minutes: only the rule sets them apart"
    edge = [{**t, "exit_ms": t["entry_ms"] + s * 1000} for t, s in zip(STEADY, [5, 6] * 22)]   # 5 seconds is fast, 6 is not
    assert build([M("steady", edge)])["best"]["rules"]["fast"] == {"share": pytest.approx(0.5), "holds": True}
    alone = build([M("fast", secs(STEADY, 4))])                                                # high odds, and the rule broken
    b = alone["best"]
    assert b == alone["mixes"][0] and b["eval"] >= 0.6 and b["payout"] >= 0.75 and b["meets"] is False and alone["meets"] is False      # the best mix found is still shown ...
    assert alone["gap"] == {**NO_GAP, "rules": ["fast"]}                                                                               # ... with what is missing
    text = alone["text"].splitlines()
    assert text[0].split(": ")[1].startswith("the best mix found does not meet the bar") and text[4] == "  missing: the fast-trades rule"
    assert text[3] == "  the account's rules: trades held 5 s or less make 100.0 % of the profit (at most 50 %): does NOT hold; no biggest-day rule on this account"
    with with_file(fast_share=1.0):
        assert build([M("fast", secs(STEADY, 4))])["meets"] is True
    loser = build([M("weak", [SY.trade(d, -5.0, 2.0) for d in CAL])])["best"]                  # no profit: no share of it, and the rule does not hold
    assert loser["rules"] == {"fast": {"share": None, "holds": False}, "biggest_day": {"share": None, "holds": None}} and loser["rules_hold"] is False


# ================================================================ 7. the biggest-day rule (LucidFlex)

def test_on_flex_the_biggest_day_is_at_most_half_the_profit_and_another_account_asks_nothing():
    cons = APP.load_rules(FLEX)["consistency"]
    assert cons == 0.5 and APP.load_rules(PRO)["consistency"] is None
    share = 500.0 / (500.0 + 43 * 5.0)                                                         # LUMPY's biggest day of its profit, at any size
    book = [M("lumpy", LUMPY), M("steady", STEADY)]
    flex, pro = build(book, FLEX), build(book, PRO)
    assert flex["rules"]["biggest_day"] == cons and pro["rules"]["biggest_day"] is None
    lone = mix(flex, "lumpy")
    assert lone["rules"]["biggest_day"] == {"share": pytest.approx(share), "holds": False} and lone["rules_hold"] is False and lone["meets"] is False
    both = mix(flex, "lumpy", "steady")
    assert both["rules"]["biggest_day"] == {"share": pytest.approx(540.0 / (715.0 + 44 * 40.0)), "holds": True} and both["rules_hold"] is True
    assert mix(pro, "lumpy")["rules"]["biggest_day"] == {"share": pytest.approx(share), "holds": None} and mix(pro, "lumpy")["rules_hold"] is True
    assert flex["mixes"][-1] == lone and flex["best"]["members"] == ["steady"], "a mix that breaks an account rule comes last"
    only = build([M("lumpy", LUMPY)], FLEX)
    assert only["gap"]["rules"] == ["biggest_day"] and only["meets"] is False and "the biggest-day rule" in only["text"].splitlines()[4]
    assert only["text"].splitlines()[3].endswith(f"; the biggest day is {100 * share:.1f} % of the profit (at most 50 %): does NOT hold")
    assert build([M("lumpy", LUMPY)], PRO)["text"].splitlines()[3].endswith("; no biggest-day rule on this account")
    with with_file(fast_share=0.5):                                                            # (the rule file's share, not pipeline.json's)
        assert build([M("lumpy", LUMPY)], FLEX)["rules"]["biggest_day"] == cons


# ================================================================ 8. ranking, and the distance from the bar

def test_the_mixes_are_ranked_in_order_first_then_nearest_the_bar_on_the_weaker_number():
    r = build([M("up", UP), M("down", DOWN), M("weak", WEAK), M("fast", secs(STEADY, 4))])
    assert len(r["mixes"]) == 15
    key = lambda m: (not in_order(m), -m["margin"], -m["eval"], -m["payout"], len(m["members"]))  # noqa: E731
    assert [key(m) for m in r["mixes"]] == sorted(key(m) for m in r["mixes"]) and r["best"] == r["mixes"][0]
    for m in r["mixes"]:
        assert m["margin"] == pytest.approx(min(m["eval"] / 0.6, m["payout"] / 0.75))
        assert m["meets"] is (in_order(m) and m["eval"] >= 0.6 and m["payout"] >= 0.75)
    order = [in_order(m) for m in r["mixes"]]
    assert order == sorted(order, reverse=True) and True in order and False in order
    fast = mix(r, "fast")
    assert r["best"]["members"] == ["up", "down"] and fast["margin"] > r["best"]["margin"] and fast["rules_hold"] is False, "nearer the bar, but out of order: after"


def test_the_bar_is_or_more_and_the_distance_is_what_is_missing():
    book = lambda: [M("up", UP), M("down", DOWN)]  # noqa: E731
    was = build(book())["best"]
    with with_file(eval={"days": 5, "odds": was["eval"]}, payout={"days": 14, "odds": was["payout"]}):        # exactly at the bar
        r = build(book())
        assert r["meets"] is True and r["gap"] == NO_GAP and r["best"]["margin"] == pytest.approx(1.0)
    more = min(1.0, was["eval"] + 0.125)
    with with_file(eval={"days": 5, "odds": more}):
        r = build(book())
        assert r["best"]["members"] == ["up", "down"] and r["meets"] is False and r["gap"] == {**NO_GAP, "eval": pytest.approx(more - was["eval"])}
        assert r["text"].splitlines()[1].endswith(f"(the bar: {100 * more:.4g} % or more) -- {100 * (more - was['eval']):.1f} points short")
        assert r["text"].splitlines()[2].endswith("-- at the bar") and r["text"].splitlines()[5] == f"  missing: {100 * (more - was['eval']):.1f} points of eval odds"
    with with_file(eval={"days": 3, "odds": 0.6}):                                             # fewer days: a lower chance
        r = build(book())
        assert r["best"]["eval"] < was["eval"] and "within 3 trading days" in r["text"]


# ================================================================ 9. Apex: one side only, no eval to pass -- and an empty book

def test_a_strategy_that_rests_orders_on_both_sides_is_left_out_where_orders_may_rest_on_one_side_only():
    book = [M("brk", UP, "orb"), M("gapper", DOWN, "gap"), M("odd", STEADY, "no_such_family")]
    assert P.need("portfolio", "one_side") == [APEX] and (PF.both_sides("orb"), PF.both_sides("gap"), PF.both_sides("no_such_family")) == (True, False, None)
    said = {f["name"]: f["bracket"] for f in blocklist.families()}                             # the block list's own word, family by family
    assert all(PF.both_sides(k) is v for k, v in said.items()) and {k for k, v in said.items() if v} >= {"orb", "straddle", "ib"}
    apex, pro = build(book, APEX), build(book, PRO)
    assert apex["rules"]["one_side"] is True and pro["rules"]["one_side"] is False
    assert [m["name"] for m in apex["members"]] == ["gapper"] and [x["name"] for x in apex["left_out"]] == ["brk", "odd"]
    assert apex["left_out"][0]["why"] == "its entry rule (orb) rests orders on both sides (the block list), and on this account orders may rest on one side only"
    assert apex["left_out"][1]["why"].startswith("the block list does not know its entry rule (no_such_family)")
    assert [m["members"] for m in apex["mixes"]] == [["gapper"]] and f"  left out on this account: brk -- {apex['left_out'][0]['why']}" in apex["text"].splitlines()
    assert any("one side only" in n and "rule file does not say so" in n for n in apex["notes"]), "the rule is the design's, not the account's own file's: said"
    assert apex["account"]["confirmed"] is False and "unconfirmed rules" in apex["text"].splitlines()[0] and any("not confirmed" in n for n in apex["notes"])
    assert [m["name"] for m in pro["members"]] == ["brk", "gapper", "odd"] and pro["left_out"] == [] and len(pro["mixes"]) == 7
    assert [(m["name"], m["both_sides"]) for m in pro["members"]] == [("brk", True), ("gapper", False), ("odd", None)]
    only = build([M("brk", UP, "orb")], APEX)                                                  # nothing is left to mix
    assert (only["mixes"], only["best"], only["gap"], only["meets"]) == ([], None, None, False)
    assert only["text"].splitlines()[0].endswith("no strategy of the book can go in a mix on this account.") and "brk" in only["text"]


def test_an_account_without_an_eval_is_judged_on_the_payout_odds_alone():
    assert P.need("portfolio", "funded_only") == [APEX]
    book = lambda: [M("up", UP), M("down", DOWN)]  # noqa: E731
    r = build(book(), APEX)
    pair, up, down = mix(r, "up", "down"), mix(r, "up"), mix(r, "down")
    assert r["judged"] == ["payout"] and r["rules"]["funded_only"] is True and any("no eval to pass" in n and "payout odds alone" in n for n in r["notes"])
    assert pair["eval"] == up["eval"] == 0.0, "the rule file's eval ($20,000 in 5 days) is out of reach: judged on it, no pair would ever be allowed"
    assert pair["without"] == {"up": down["payout"], "down": up["payout"]} and pair["payout"] > max(up["payout"], down["payout"]), "the number a member must raise: the payout odds"
    assert pair["drags"] == [] and pair["allowed"] is True and pair["margin"] == pytest.approx(pair["payout"] / 0.75)
    assert r["best"] == pair and pair["meets"] is True and r["gap"] == {**NO_GAP, "eval": None}
    text = r["text"].splitlines()
    assert text[1].endswith("-- not judged: this account has no eval to pass") and text[2].endswith("-- at the bar") and text[4].startswith("  each member must raise the payout odds:")
    key = lambda m: (not in_order(m), -m["margin"], -m["payout"], len(m["members"]))  # noqa: E731
    assert [key(m) for m in r["mixes"]] == sorted(key(m) for m in r["mixes"])
    with with_file(funded_only=[]):                                                            # held to the eval of the rule file on file: nothing is allowed together
        r = build(book(), APEX)
        assert r["judged"] == ["eval", "payout"] and mix(r, "up", "down")["allowed"] is False and r["meets"] is False and r["gap"]["eval"] == 0.6
    assert build(book(), PRO)["judged"] == ["eval", "payout"] == build(book(), FLEX)["judged"]


def test_an_empty_book_says_so_and_raises_nothing(tmp_path):
    r = build([])
    assert set(r) == KEYS and (r["members"], r["mixes"], r["best"], r["gap"], r["meets"]) == ([], [], None, None, False)
    assert r["text"] == f"{APP.load_rules(PRO)['name']} [{PRO}]: the book is empty: there is no strategy to mix."
    root = tmp_path / "pipeline"
    rc, out = run(["pipe", "portfolio", f"--root={root}", "--json"])
    assert rc == 0 and out["ok"] is True and (out["command"], out["book"], out["saved"]) == ("pipe portfolio", [], [])
    assert out["text"].splitlines()[0].startswith("THE PORTFOLIO (stage 8): 0 strategies in the book. A mix must pass the eval within 5 trading days 60 % of the time or more")
    assert [a["account"]["id"] for a in out["accounts"]] == [PRO, FLEX, APEX] and all("the book is empty" in a["text"] for a in out["accounts"])
    assert not root.exists(), "an empty book writes nothing, not even its folder"


# ================================================================ 10. the command, on a hand-made book in a temp root

def run(argv: list) -> tuple:
    """The command line in this process -> (exit code, the one object, or its text without --json)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        rc = C.main(argv)
    return rc, json.loads(out.getvalue()) if "--json" in argv else out.getvalue()


def booked(root: Path, name: str, rows: list, family: str, market: str = "NQ") -> dict:
    """A strategy in the book of a temp pipeline root: its idea locked and read on hand-made "unseen" days (blueprint_synth.proven:
    the lock, the read's two stores, a passed test), and its book card."""
    SY.proven(IS, PS.ideas_root(root), name, folder=PS.runs_test(root), cells={"v": rows}, lock_more={"spec": {"run": {"family": family}}})
    c = {"name": name, "sub": name, "family": family, "market": market, "session": "nyam", "bar": "15", "rule": {"spec": {}, "default": "v", "lock": SY.LOCK}, "label": "helper"}
    PS.write_book(name, c, root)
    return c


def tree(d: Path) -> dict:
    """Every file of a pipeline root but the builder's own folder, with its time."""
    return {str(p.relative_to(d)): p.stat().st_mtime_ns for p in sorted(d.rglob("*")) if p.is_file() and "portfolios" not in p.relative_to(d).parts}


def test_the_command_reads_the_book_for_every_account_and_saves_one_file_an_account(tmp_path):
    root = tmp_path / "pipeline"
    booked(root, "pf_up", UP, "fvg")
    booked(root, "pf_down", DOWN, "gap")
    before = tree(root)
    with SY.no_engine():
        r = PF.portfolio(root, paths=N, seed=SEED)
    assert (r["ok"], r["command"], r["book"]) == (True, "pipe portfolio", ["pf_down", "pf_up"]) and [a["account"]["id"] for a in r["accounts"]] == [PRO, FLEX, APEX]
    files = [root / "portfolios" / f"{a}.json" for a in (PRO, FLEX, APEX)]
    assert r["saved"] == [str(f) for f in files] and sorted(p.name for p in (root / "portfolios").iterdir()) == sorted(f.name for f in files)
    for a, f in zip(r["accounts"], files):
        assert json.loads(f.read_text(encoding="utf-8")) == json.loads(json.dumps(a)) and a["best"]["members"] == ["pf_down", "pf_up"] and a["text"] in r["text"]
        assert [m["name"] for m in a["members"]] == ["pf_down", "pf_up"] and a["members"][0]["trades"] == 44 and a["best"]["days"] == 44 and a["unread"] == []
    hand = build([M("pf_down", DOWN, "gap"), M("pf_up", UP, "fvg")])                           # the same trades, handed over by hand
    assert r["accounts"][0]["best"] == hand["best"] and r["accounts"][0]["mixes"] == hand["mixes"], "the book's trades are each card's box on the days its read replayed"
    assert tree(root) == before, "nothing of the book, the ideas or the stores was touched"
    assert sorted(p.name for p in tmp_path.iterdir()) == ["pipeline"], "and nothing beside the root (no stray root, no idea folder of the app, no Lab draft)"
    assert r["text"].splitlines()[0].startswith("THE PORTFOLIO (stage 8): 2 strategies in the book (pf_down, pf_up). A mix must pass the eval within 5 trading days")
    one = PF.portfolio(root, FLEX, paths=N, seed=SEED)                                         # one account: the one asked for, and its file alone
    assert [a["account"]["id"] for a in one["accounts"]] == [FLEX] and one["saved"] == [str(files[1])] and one["accounts"][0] == r["accounts"][1]


def test_the_command_line_and_what_it_refuses(tmp_path, capsys):
    root = tmp_path / "pipeline"
    booked(root, "pf_up", UP, "orb")
    rc, r = run(["pipe", "portfolio", f"--account={FLEX}", f"--root={root}", "--json"])
    assert rc == 0 and r["command"] == "pipe portfolio" and [a["account"]["id"] for a in r["accounts"]] == [FLEX] and r["accounts"][0]["paths"] == APP.N_PATHS
    assert r["accounts"][0]["best"]["members"] == ["pf_up"] and r["accounts"][0]["meets"] is False and r["next"] == ""
    rc, text = run(["pipe", "portfolio", f"--root={root}"])                                    # for a person: every account
    lines = text.splitlines()
    assert rc == 0 and lines[0].startswith("THE PORTFOLIO (stage 8): 1 strategy in the book (pf_up).") and "NEXT" not in text
    names = [APP.load_rules(a)["name"] for a in (PRO, FLEX, APEX)]
    assert [x.strip() for x in lines[1].split("  ") if x.strip()] == ["account", "best mix", "eval in 5 days", "max payout in 14 days", "at the bar"]      # the answer first: one row an account
    full = RN.command("portfolio", root=root)["accounts"]
    assert [[c.strip() for c in x.split("  ") if c.strip()] for x in lines[2:5]] == [
        *[[n, "pf_up", f"{100 * a['best']['eval']:.1f} % of 60 %", f"{100 * a['best']['payout']:.1f} % of 75 %", "no"] for n, a in zip(names[:2], full)], [names[2], "none", "-", "-", "no"]]
    assert [x.split(" [")[0] for x in lines[5:] if not x.startswith(" ")] == names                                 # then each account in full
    assert sum("It is pf_up alone" in x for x in lines) == 2 and "  left out on this account: pf_up -- its entry rule (orb) rests orders on both sides" in text
    with capsys.disabled():
        print("\n--- bp.py pipe portfolio, a book of one strategy (hand-made trades) ---\n" + text)
    rc, r = run(["pipe", "portfolio", "--account=nobody@1", f"--root={root}", "--json"])
    assert rc == 2 and r["ok"] is False and r["command"] == "pipe portfolio" and "'nobody@1'" in r["error"] and PRO in r["error"]
    assert sorted(p.name for p in (root / "portfolios").iterdir()) == sorted(f"{a}.json" for a in (PRO, FLEX, APEX))
    assert "portfolio" in RN.SUBS and RN.command("portfolio", root=root, account=PRO)["accounts"][0]["account"]["id"] == PRO
    with pytest.raises(J.Refuse):
        PS.write_portfolio("../x", {}, root)


def test_a_book_card_whose_trades_cannot_be_read_is_named_and_the_rest_is_still_mixed(tmp_path):
    root = tmp_path / "pipeline"
    booked(root, "pf_up", UP, "fvg")
    PS.write_book("pf_ghost", {"name": "pf_ghost", "sub": "pf_ghost", "family": "gap", "market": "NQ", "rule": {"default": "v", "lock": SY.LOCK}}, root)       # no idea on file
    moved = booked(root, "pf_moved", DOWN, "liq")
    PS.write_book("pf_moved", {**moved, "rule": {"default": "v", "lock": "feedfeedfeedfeed"}}, root)       # another lock than the one on file
    PS.write_book("pf_bare", {"name": "pf_bare"}, root)                                                   # a card that says nothing
    r = PF.portfolio(root, PRO, paths=N, seed=SEED)
    a = r["accounts"][0]
    assert r["ok"] is True and r["book"] == ["pf_bare", "pf_ghost", "pf_moved", "pf_up"] and [m["name"] for m in a["members"]] == ["pf_up"]
    why = {x["name"]: x["why"] for x in a["unread"]}
    assert set(why) == {"pf_bare", "pf_ghost", "pf_moved"} and "no idea pf_ghost" in why["pf_ghost"] and "feedfeedfeedfeed" in why["pf_moved"] and "does not say" in why["pf_bare"]
    assert a["best"]["members"] == ["pf_up"] and f"  not read: pf_ghost -- {why['pf_ghost']}" in a["text"].splitlines()
    assert PF.build(PRO, root, paths=N, seed=SEED) == a, "build() reads the book of the root it is given"


def test_the_help_and_the_command_list_name_it():
    out = io.StringIO()
    with contextlib.redirect_stdout(out), pytest.raises(SystemExit):
        C._parser().parse_args(["pipe", "--help"])
    assert "portfolio" in out.getvalue() and C._parser().parse_args(["pipe", "portfolio", "--account=x@1", "--root=/x"]).account == "x@1"
    assert "bp.py pipe portfolio [--account=ID]" in C.__doc__ and C._parser().parse_args(["pipe", "portfolio"]).account is None


# ================================================================ 11. the real tiny book of the end-to-end test

@pytest.fixture()
def tiny(monkeypatch):
    """The world of tests/test_pipe_end_to_end.py, line for line (its temp folders, its Saturday, its look at the places outside
    before its first run), so its ONE whole run can be made here or read where that file left it."""
    import test_blueprint_ideas as TI
    import test_pipe_end_to_end as E2E
    TI.setup_function()
    E2E.POOLS.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(PS, "pools", lambda: E2E.POOLS)
    monkeypatch.setattr(RUN, "clock", lambda: TI.SAT)
    monkeypatch.setattr(RM, "auto_workers", lambda n=None: n)
    monkeypatch.setattr(P, "mode", lambda: "map")
    monkeypatch.setenv(PS.ENV, str(E2E.STRAY))
    if "before" not in E2E._T:
        E2E._T["before"] = E2E.snapshot()
    yield E2E, monkeypatch
    TI.teardown_function()


def test_the_one_strategy_of_the_tiny_real_book_is_read_without_a_write(tiny):
    E2E, mp = tiny
    E2E.whole(mp)                                   # the end-to-end test's own run (made once a session, skipped without its tapes)
    card = PS.stages(E2E.A, E2E.ROOT)[7]["book"]    # the book card the owner's yes files (that file's own test approves it)
    before = sorted(p.name for p in E2E.ROOT.iterdir())
    with SY.no_engine():
        m = PF.member(card, E2E.ROOT)
        r = PF.build(members=[m], paths=N, seed=SEED)
        apex = PF.build(APEX, members=[m], paths=N, seed=SEED)
    assert (m["name"], m["family"], m["market"], m["box"], m["trades"], m["calendar"]) == (E2E.A, "orb", "NQ", card["rule"]["default"], card["trades"], E2E.TEST_DAYS)
    b = r["best"]
    assert r["account"]["id"] == E2E.OWN and len(r["mixes"]) == 1 and b["members"] == [E2E.A] and b["days"] == 2 and b["allowed"] is True
    assert 0.0 <= b["eval"] <= 1.0 and 0.0 <= b["payout"] <= 1.0 and r["members"][0]["both_sides"] is True and f"{E2E.A} alone" in r["text"]
    o = PF.odds([m["x"]], m["calendar"], APP.load_rules(E2E.OWN), N, SEED)
    assert (b["eval"], b["payout"], b["size"], b["payout_size"]) == (o["eval"], o["payout"], o["size"], o["payout_size"])
    assert [x["name"] for x in apex["left_out"]] == [E2E.A] and apex["best"] is None, "an opening-range break rests orders on both sides"
    assert sorted(p.name for p in E2E.ROOT.iterdir()) == before and "portfolios" not in before, "the builder itself writes nothing: only the command saves"


# ================================================================ 12. no number in the module

def test_no_number_is_typed_in_the_module():
    src = (W / "blueprint" / "pipe_portfolio.py").read_text(encoding="utf-8").split('"""', 2)[2]      # the code under the docstring
    for number in ("0.5", "0.6", "0.75", "14", "60", "75", "30", "lucid", "apex", "@20"):
        assert number not in src, f"{number} is typed in pipe_portfolio.py"


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q", "-p", "no:cacheprovider"]))
