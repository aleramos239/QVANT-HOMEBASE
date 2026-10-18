"""A Lab strategy that reads one market and trades its micro (2026-10-11, owner: "it reads the chart from NQ but when
its time to execute this one executes on mnq"), and one that sizes its own orders ("risking the same amount per trade
with micros"). `exec_root = "MNQ"`: bars, levels and fills are NQ's; the dollars, the Desk's order, its position read
and the paper fill are the micro's. `own_size = True`: the Desk sends the order's own size, never above the size set
on the account. A strategy that declares neither behaves exactly as before."""
from __future__ import annotations

import pytest

from homebase import contracts, draftstore, labcfg
from homebase.backtest import drafthost
from homebase.backtest.engine import Costs, run_session
from homebase.charts import paperbook as pb
from homebase.charts.paperbook import PAPER_ID, PaperBook
from homebase.labrun import deskside, door, store
from homebase.labrun.deskside import DeskSide
from homebase.labrun.host import StrategyDay, sized, well_set
from tests.labdesk_util import DATE, LAB, MARK, entry, mkdesk, rec as desk_rec, send
from tests.test_backtest_engine import D, Script, tape
from tests.test_charts_paperbook import T0, order
from tests.test_engine import run
from tests.test_labrun_host import HEAD, MARKET_930, ms_of, plain, rec as host_rec, ticks

MICRO_930 = MARKET_930.replace('id, name, root = "m", "M", "NQ"', 'id, name, root = "m", "M", "NQ"\n    exec_root = "MNQ"')
OWN = {"max_trades_day": 3, "max_qty": 10, "max_risk_usd": 5000, "last_entry_et": "11:00", "flat_et": "15:55"}


# ---------------------------------------------------------------- the pairs
def test_only_a_markets_own_micro_may_take_its_orders():
    assert contracts.exec_ok("NQ", "MNQ") and contracts.exec_ok("ES", "MES") and contracts.exec_ok("GC", "MGC")
    # (RTY's M2K: its name does not resolve to a contract here -- not a pair)
    for root, ex in (("NQ", "MES"), ("NQ", "NQ"), ("MNQ", "NQ"), ("NQ", ""), ("NQ", None), ("CL", "MCL"), ("RTY", "M2K")):
        assert not contracts.exec_ok(root, ex), (root, ex)
    for root, micro in contracts._MICRO_OF.items():          # a level of the market is a level of its micro
        assert contracts.tick_size(root) == contracts.tick_size(micro)
        assert contracts.point_value(micro) < contracts.point_value(root)
    assert [contracts.price_root(s) for s in ("MNQ", "MNQZ6", "NQ", "NQZ6", "CL")] == ["NQ", "NQ", "NQ", "NQ", "CL"]
    assert contracts.micro_of("NQ") == "MNQ" and contracts.micro_of("CL") is None


def test_a_micro_rolls_with_its_market():
    import datetime as dt
    from homebase.symbols import front_month
    for root, micro in contracts._MICRO_OF.items():
        for day in (dt.date(2026, 1, 5), dt.date(2026, 3, 12), dt.date(2026, 6, 19), dt.date(2026, 9, 25), dt.date(2026, 12, 18)):
            assert front_month(micro, day)[len(micro):] == front_month(root, day)[len(root):], (root, day)
        from homebase.symbols import resolve_contract
        got = resolve_contract(micro)                       # a real contract, never the bare root (the broker refuses that)
        assert got.startswith(micro) and len(got) > len(micro), got


# ---------------------------------------------------------------- the draft
def draft(*lines) -> str:
    return HEAD + 'class X(Strategy):\n    name = "x"\n    root = "NQ"\n' + "".join(f"    {x}\n" for x in lines)


def test_a_draft_names_the_micro_and_its_own_size_as_literals():
    meta = draftstore.static_meta(draft('exec_root = "MNQ"', "own_size = True"))
    assert meta["exec_root"] == "MNQ" and meta["own_size"] is True
    assert "exec_root" not in draftstore.static_meta(draft()) and "own_size" not in draftstore.static_meta(draft())
    for bad in ('exec_root = "MES"', 'exec_root = "NQ"', "exec_root = 3", 'own_size = "yes"'):
        with pytest.raises(draftstore.StaticError):
            draftstore.static_meta(draft(bad))
    stub = drafthost.stub_class("x", draft('exec_root = "MNQ"', "own_size = True"))
    assert stub.exec_root == "MNQ" and stub.own_size is True and stub.describe()["exec_root"] == "MNQ"
    plain_stub = drafthost.stub_class("x", draft())
    assert plain_stub.exec_root == "" and "exec_root" not in plain_stub.describe() and "own_size" not in plain_stub.describe()


# ---------------------------------------------------------------- the tester
ROWS = [("09:29:59", 21000.0), ("09:30:01", 21000.0), ("09:30:02", 21010.0), ("15:55:01", 21050.0)]


def buy(qty):
    return {"09:30:00": lambda ctx, s: ctx.market("long", qty=qty, sl=20900.0), "15:55": lambda ctx, s: ctx.flatten("time")}


def test_the_tester_prices_a_micro_strategy_in_the_micros_dollars_on_the_markets_prints():
    full = run_session(Script(buy(1)), tape(ROWS), Costs(4.0, 1.0)).trades
    micro = Script(buy(5))
    micro.exec_root = "MNQ"
    got = run_session(micro, tape(ROWS), Costs(1.0, 1.0)).trades
    (a,), (b,) = full, got
    assert (a.entry_price, a.exit_price) == (b.entry_price, b.exit_price)                # NQ's fills, both
    pts = a.exit_price - a.entry_price
    assert a.gross == pts * 20 and a.net == pts * 20 - 4
    assert b.qty == 5 and b.gross == pts * 2 * 5 and b.net == pts * 2 * 5 - 5 * 1.0
    assert b.mae_usd == pytest.approx(a.mae_usd / 10 * 5) and b.mfe_usd == pytest.approx(a.mfe_usd / 10 * 5)


# ---------------------------------------------------------------- the door
STATE = {"flat": True, "working_entries": 0, "entries_today": 0, "last_price": 100.0, "now_hhmm": "10:00", "prices_late": False}
LIM = {"max_trades_day": 3, "max_qty": 10, "max_risk_usd": 0, "last_entry_et": "11:00", "session_from_et": "09:25",
       "point_value": 2.0, "tick": 0.25}


def test_the_door_lets_a_strategy_size_its_own_order_only_when_the_record_says_so():
    it = entry(kind="market", price=None, ref=100.0, sl=95.0, tp=None, qty=7, own_qty=True)
    assert door.check(it, STATE, LIM) == door.OWN_SIZE
    assert door.check(it, STATE, {**LIM, "own_size": False}) == door.OWN_SIZE
    assert door.check(it, STATE, {**LIM, "own_size": 1}) == door.OWN_SIZE                # true, not truthy
    assert door.check(it, STATE, {**LIM, "own_size": True}) is None
    # the dollars at risk are the micro's: 5 points x $2 x 7
    assert door.check(it, STATE, {**LIM, "own_size": True, "max_risk_usd": 69}) == "Stop too far: $70 at risk, limit $69."
    assert door.check(it, STATE, {**LIM, "own_size": True, "max_risk_usd": 70}) is None


def test_the_note_at_promote_says_which_size_rule_holds():
    src = HEAD + "class X(Strategy):\n{}    def f(self, ctx):\n        ctx.market('long', qty=3, sl=1.0)\n"
    assert door.read_source(src.format("")) == ["It sets its own size: size is set on the Desk."]
    assert door.read_source(src.format("    own_size = True\n")) == [
        "It sets its own size: the size set on an account is the most it sends there."]
    assert door.read_source(src.format("    own_size = False\n")) == ["It sets its own size: size is set on the Desk."]


# ---------------------------------------------------------------- the record and its limits
def test_promote_keeps_the_micro_and_the_own_size_only_when_declared():
    meta = draftstore.static_meta(draft('exec_root = "MNQ"', "own_size = True"))
    snap = store.snapshot("x", "src", meta, {"run": {"qty": 1}, "trades": []}, "r1", [])
    assert snap["root"] == "NQ" and snap["exec_root"] == "MNQ" and snap["own_size"] is True
    old = store.snapshot("x", "src", draftstore.static_meta(draft()), {"run": {"qty": 1}, "trades": []}, "r1", [])
    assert "exec_root" not in old and "own_size" not in old


def lab_rec(**kw):
    return {"name": "x", "root": "NQ", "qty": 1, "session_window": ["09:25", "15:55"], "auto_limits": {"max_trades_day": 1}, **kw}


def test_the_desks_order_symbol_is_the_micro_and_everything_else_is_unchanged():
    assert labcfg.exec_symbol(lab_rec()) == "NQ"
    assert labcfg.exec_symbol(lab_rec(exec_root="MNQ")) == "MNQ"
    for bad in ("MES", "NQ", "", None, 5, ["MNQ"]):          # a name nobody checked is never an order's market
        assert labcfg.exec_symbol(lab_rec(exec_root=bad)) == "NQ", bad
    assert labcfg.strategy_cfg(lab_rec(exec_root="MNQ"), None).symbol == "MNQ"
    assert labcfg.strategy_cfg(lab_rec(), None).symbol == "NQ"
    # ... and such a record is not a strategy on the Desk at all: its sizes are counted in a contract nobody checked
    assert labcfg.usable(lab_rec()) and labcfg.usable(lab_rec(exec_root="MNQ"))
    for bad in ("MES", "NQ", "", 5, ["MNQ"]):
        assert not labcfg.usable(lab_rec(exec_root=bad)), bad


def test_a_strategy_that_sizes_itself_is_capped_by_the_desks_most_in_both_derivations():
    for r in (lab_rec(), lab_rec(qty=4), lab_rec(own_size=True), lab_rec(own_size=True, qty=None), lab_rec(own_size="yes", qty=3)):
        a, b = labcfg.derive_limits(r), deskside.own_limits(r)
        assert (a is None) == (b is None), r
        if a is not None:
            assert (a.max_trades_day, a.max_qty, a.last_entry_et, a.flat_et) == (
                b["max_trades_day"], b["max_qty"], b["last_entry_et"], b["flat_et"]), r
    assert labcfg.derive_limits(lab_rec(own_size=True)).max_qty == store.OWN_SIZE_MOST == 10 ** 6   # no cap: the account's size is its most
    assert labcfg.derive_limits(lab_rec()).max_qty == 1
    assert labcfg.derive_limits(lab_rec(own_size="yes", qty=3)).max_qty == 3       # true, not truthy


def test_a_desk_days_match_runs_a_self_sizing_strategy_at_its_own_sizes():
    r = lab_rec(own_size=True)
    assert sized(r, [{"qty": 7}]) is r
    assert sized(lab_rec(), [{"qty": 7}])["qty"] == 7


# ---------------------------------------------------------------- the runner
def test_the_child_must_agree_with_the_record_about_the_market_its_orders_go_to():
    meta = {"root": "NQ", "session_window": ["09:30", "16:00"], "bar_minutes": 0, "bar_window": None, "placement_ms": 85,
            "times": [], "needs_daily": False, "trades_on": True}
    assert well_set(meta, "NQ") and well_set({**meta, "exec_root": "MNQ"}, "NQ", "MNQ")
    assert not well_set({**meta, "exec_root": "MNQ"}, "NQ") and not well_set(meta, "NQ", "MNQ")


def shadow_net(source, **kw):
    day = StrategyDay(host_rec(source, **kw), D, spawn=plain, daily=[], deadline_s=0.3)
    try:
        day.on_ticks(ticks("09:29:50", [21000.0] * 9))
        day.on_clock(ms_of("09:30:01", 1))
        day.on_ticks(ticks("09:30:02", [21001.0]))
        day.on_clock(ms_of("16:00:02", 1))
        s = day.summary()
        return s["state"], [(t["entry_px"], t["exit_px"], t["net"]) for t in s["trades"]]
    finally:
        day.kill()


def test_the_shadow_day_of_a_micro_strategy_is_in_the_micros_dollars():
    assert shadow_net(MARKET_930) == ("done", [(21001.25, 21000.75, -14.0)])               # 0.5 pt x $20 + $4
    assert shadow_net(MICRO_930, exec_root="MNQ", commission=1.0) == ("done", [(21001.25, 21000.75, -2.0)])   # 0.5 x $2 + $1
    # the record and its code must say the same market: neither is hosted otherwise
    assert shadow_net(MICRO_930)[0] == "stopped" and shadow_net(MARKET_930, exec_root="MNQ")[0] == "stopped"
    assert shadow_net(MARKET_930, exec_root="MES")[0] == "stopped"


# ---------------------------------------------------------------- the Desk
def placed(d, a="a1"):
    return [(q.symbol, q.side, q.order_type, q.qty) for q in d.ads[a].brackets]


def test_the_desk_sends_the_micro_at_the_strategys_own_size_never_above_the_accounts(tmp_path):
    d = mkdesk(tmp_path, accounts=("a1", "a2"), limits=OWN, rec_kw={"exec_root": "MNQ", "own_size": True})
    assert d.cfg.strategies[LAB].symbol == "MNQ"
    run(d.ld.set_book(LAB, [{"account": "a1", "qty": 10}, {"account": "a2", "qty": 4}]))
    out = send(d, entry(kind="market", price=None, ref=100.0, sl=95.0, tp=115.0, qty=6, own_qty=True))
    assert out["results"][0]["refused"] is None, out
    assert placed(d, "a1") == [("MNQ", "Buy", "Market", 6)]            # the order's own size
    assert placed(d, "a2") == [("MNQ", "Buy", "Market", 4)]            # capped at the account's


def test_a_strategy_that_does_not_declare_it_is_still_refused_its_own_size(tmp_path):
    d = mkdesk(tmp_path, limits=OWN, qty=5)
    out = send(d, entry(kind="market", price=None, ref=100.0, sl=95.0, tp=115.0, qty=3, own_qty=True))
    assert out["results"][0]["refused"] == door.OWN_SIZE and placed(d) == []
    out = send(d, entry(kind="market", price=None, ref=100.0, sl=95.0, tp=115.0, qty=3), seq=2)
    assert out["results"][0]["refused"] is None and placed(d) == [("NQ", "Buy", "Market", 5)]     # the account's size, on NQ


def test_the_dollar_cap_of_a_micro_strategy_is_counted_in_the_micros_dollars(tmp_path):
    lim = {**OWN, "max_risk_usd": 100}
    d = mkdesk(tmp_path, limits=lim, qty=10, rec_kw={"exec_root": "MNQ", "own_size": True})
    # 5 points x $2 x 10 = $100: allowed (on NQ's $20 it would read $1,000)
    out = send(d, entry(kind="market", price=None, ref=100.0, sl=95.0, tp=115.0, qty=10, own_qty=True))
    assert out["results"][0]["refused"] is None and placed(d) == [("MNQ", "Buy", "Market", 10)]


def test_a_micro_strategy_may_share_an_account_with_one_that_trades_the_market(tmp_path):
    """Since 2026-10-11: NQ and MNQ are one market to on_fill, so they trade one at a time (engine._slot_busy)."""
    from homebase.config import StrategyCfg
    extra = {"nq930": StrategyCfg(symbol="NQ", qty=1, offset_pts=5.0, sl_pts=5.0, tp_pts=15.0, enabled=True)}
    d = mkdesk(tmp_path, limits=OWN, qty=0, extra=extra, book={"nq930": [{"account": "a1", "qty": 1}]},
               rec_kw={"exec_root": "MNQ", "own_size": True})
    run(d.ld.set_book(LAB, [{"account": "a1", "qty": 5}]))


# ---------------------------------------------------------------- the paper book
def rows_at(ns, *prices):
    return [{"ts_ms": (ns + i * 1_000_000) // 1_000_000, "ts_ns": ns + i * 1_000_000, "price": p} for i, p in enumerate(prices)]


def test_a_paper_account_fills_a_micro_order_from_the_markets_prints_at_the_micros_dollars():
    b = PaperBook(None, roots=["NQ"], clock_ms=lambda: T0 // 1_000_000)
    b.on_ticks("NQ", rows_at(T0, 21000.0))
    assert b.last["MNQ"] == 21000.0 and b.seq["MNQ"] == b.seq["NQ"] == 1
    got = order(b, "Buy", "Market", qty=5, sl=20990.0, tp=21020.0, root="MNQ")
    assert got["ok"] is True, got
    b.on_ticks("NQ", rows_at(T0 + 10 ** 9, 21001.0))          # the entry fills on the next NQ print
    assert b.pos["MNQ"]["net"] == 5 and b.pos["MNQ"]["symbol"].startswith("MNQ") and "NQ" not in b.pos
    b.on_ticks("NQ", rows_at(T0 + 2 * 10 ** 9, 21019.0, 21020.25))   # the target: one tick through
    assert b.pos["MNQ"]["net"] == 0
    fill = b.fills[-1]
    # entry 21001.25 (a tick of slippage), target 21020.00: 18.75 points x $2 x 5 - 5 micro round turns
    assert fill["pnl"] == pytest.approx(18.75 * 2 * 5 - 5 * pb.MICRO_COMMISSION_RT)
    assert b.commission == pytest.approx(5 * pb.MICRO_COMMISSION_RT)


def test_a_micro_of_a_market_that_is_not_streamed_is_refused_and_nq_is_as_before():
    b = PaperBook(None, roots=["ES"], clock_ms=lambda: T0 // 1_000_000)
    assert "not streamed" in order(b, "Buy", "Market", root="MNQ")["error"]
    b = PaperBook(None, roots=["NQ"], clock_ms=lambda: T0 // 1_000_000)
    b.on_ticks("NQ", rows_at(T0, 21000.0))
    order(b, "Buy", "Market", qty=1, root="NQ")
    b.on_ticks("NQ", rows_at(T0 + 10 ** 9, 21001.0))
    assert b.pos["NQ"]["net"] == 1 and not (b.pos.get("MNQ") or {}).get("net")
    order(b, "Sell", "Market", qty=1, root="NQ")
    b.on_ticks("NQ", rows_at(T0 + 2 * 10 ** 9, 21011.0))
    assert b.fills[-1]["pnl"] == pytest.approx((21010.75 - 21001.25) * 20 - 4.0)      # the full contract's fee, as before


# ---------------------------------------------------------------- the 2026-10-11 review's findings
def test_the_runner_believes_only_a_desk_that_sends_the_orders_to_the_same_market(tmp_path):
    """A Desk started before it knew of micros reads the record as NQ: the runner must send it no entry."""
    d = mkdesk(tmp_path, limits=OWN, qty=10, rec_kw={"exec_root": "MNQ", "own_size": True})
    snap = d.ld.snapshot()["strategies"][LAB]
    assert snap["symbol"] == "MNQ"
    side = DeskSide(LAB, MARK, DATE, ["a1"], symbol="MNQ")
    assert side.take(snap) is True and side.silent() is False
    for old in ({k: v for k, v in snap.items() if k != "symbol"}, {**snap, "symbol": "NQ"}, {**snap, "symbol": None}):
        side = DeskSide(LAB, MARK, DATE, ["a1"], symbol="MNQ")
        assert side.take(old) is False and side.silent() is True, old.get("symbol", "(none)")
    plain = DeskSide(LAB, MARK, DATE, ["a1"])                    # a strategy that names no micro: as before
    assert plain.take({k: v for k, v in snap.items() if k != "symbol"}) is True and plain.silent() is False


def test_a_record_whose_market_changes_under_the_same_promotion_is_not_followed(tmp_path):
    d = mkdesk(tmp_path, limits=OWN, qty=2)
    assert d.cfg.strategies[LAB].symbol == "NQ" and d.cfg.strategies[LAB].enabled is True
    store.put(desk_rec(enabled=True, session_window=["09:25", "15:55"], exec_root="MNQ"))     # edited by hand: same mark
    labcfg.overlay(d.cfg)
    s = d.cfg.strategies[LAB]
    assert s.symbol == "NQ" and s.enabled is False              # kept as it last read, and switched off


def test_a_pair_of_a_self_sizing_strategy_goes_out_whole_or_not_at_all(tmp_path):
    def legs(a, b):
        return [entry(3, side="long", price=110.0, sl=105.0, tp=120.0, qty=a, own_qty=True),
                entry(4, side="short", price=90.0, sl=95.0, tp=80.0, qty=b, own_qty=True), {"op": "oco", "ids": [3, 4]}]
    d = mkdesk(tmp_path, accounts=("a1", "a2"), limits=OWN, rec_kw={"own_size": True})
    run(d.ld.set_book(LAB, [{"account": "a1", "qty": 10}, {"account": "a2", "qty": 2}]))
    out = send(d, legs(5, 2))
    assert [r.get("refused") for r in out["results"][:2]] == ["A linked pair must be the same size on both sides."] * 2
    assert placed(d, "a1") == [] and placed(d, "a2") == []
    out = send(d, legs(5, 5), seq=2)
    assert [r.get("refused") for r in out["results"]] == [None, None, None]
    assert placed(d, "a1") == [("NQ", "Buy", "Stop", 5), ("NQ", "Sell", "Stop", 5)]
    assert placed(d, "a2") == [("NQ", "Buy", "Stop", 2), ("NQ", "Sell", "Stop", 2)]     # capped, both legs alike


def test_the_fee_nobody_typed_is_the_fee_of_the_contract_the_orders_go_to():
    assert contracts.commission_rt("MNQ") == contracts.commission_rt("MNQZ6") == 1.0
    assert contracts.commission_rt("NQ") == contracts.commission_rt("CL") == 4.0
    assert labcfg.strategy_cfg(lab_rec(exec_root="MNQ"), None).fee_rt == 1.0
    assert labcfg.strategy_cfg(lab_rec(), None).fee_rt == 4.0
    assert labcfg.strategy_cfg(lab_rec(exec_root="MNQ", commission=0.5), None).fee_rt == 0.5      # the run's own, when frozen
    assert pb.MICRO_COMMISSION_RT == contracts.MICRO_COMMISSION_RT


def test_the_tester_refuses_to_price_on_a_contract_that_is_not_the_markets_micro():
    bad = Script(buy(1))
    bad.exec_root = "MES"
    with pytest.raises(ValueError, match="exec_root"):
        run_session(bad, tape(ROWS), Costs(1.0, 1.0))


def test_promote_says_when_the_backtest_traded_more_than_the_desk_sends():
    meta = draftstore.static_meta(draft('exec_root = "MNQ"', "own_size = True"))
    snap = store.snapshot("x", "src", meta, {"run": {"qty": 1}, "trades": [{"date": "2025-01-02", "qty": 120}]}, "r1", ["n"])
    assert snap["notes"] == ["n"], "no cap, so no note: the account's size is the only limit (owner 2026-10-18)"
    snap = store.snapshot("x", "src", meta, {"run": {"qty": 1}, "trades": [{"date": "2025-01-02", "qty": 10}]}, "r1", [])
    assert snap["notes"] == []


def test_a_micro_that_is_streamed_itself_keeps_its_own_prints_and_an_annotated_own_size_reads():
    b = PaperBook(None, roots=["NQ", "MNQ"], clock_ms=lambda: T0 // 1_000_000)
    b.on_ticks("NQ", rows_at(T0, 21000.0))
    assert "MNQ" not in b.last
    b.on_ticks("MNQ", rows_at(T0, 21000.5))
    assert b.last == {"NQ": 21000.0, "MNQ": 21000.5} and b.seq == {"NQ": 1, "MNQ": 1}
    src = HEAD + "class X(Strategy):\n    own_size: bool = True\n    def f(self, ctx):\n        ctx.market('long', qty=3, sl=1.0)\n"
    assert door.read_source(src) == ["It sets its own size: the size set on an account is the most it sends there."]
