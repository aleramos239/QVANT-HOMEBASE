"""A promoted strategy carries its own limits (2026-10-10, owner: "the strategy should be copy paste ... i dont want
limits per strategy"). A record that holds `auto_limits` (written at Promote from its backtest) needs nothing typed:
the size is the tested size, the trades a day the most it took in one day, any entry inside its own window, flat when the
window ends. What was typed is never overwritten; an older record without `auto_limits` behaves exactly as before."""
from __future__ import annotations

from homebase import labcfg
from homebase.labcfg import LabLimits
from homebase.labrun import store
from tests.test_labcfg import LIMITS, MARK, desk_cfg, rec, side

OWN = {"max_trades_day": 1}


def own_rec(**kw):
    return rec(**{"session_window": ["08:20", "15:55"], "qty": 4, "auto_limits": OWN, **kw})


def test_derive_limits_from_the_record():
    got = labcfg.derive_limits(own_rec())
    assert got == LabLimits(1, 4, 0.0, "15:54", "15:55")
    # the window may end later than the Desk's flat time: flat is cut at 15:55, last entry is a minute before it
    assert labcfg.derive_limits(own_rec(session_window=["09:25", "16:00"])) == LabLimits(1, 4, 0.0, "15:54", "15:55")
    # a window that ends earlier: flat is the window's end
    assert labcfg.derive_limits(own_rec(session_window=["09:25", "11:30"])) == LabLimits(1, 4, 0.0, "11:29", "11:30")
    # no cap of 10 any more (owner, 2026-10-11): the tested size stands, up to the tester's own largest (100)
    assert labcfg.derive_limits(own_rec(qty=40)).max_qty == 40
    assert labcfg.derive_limits(own_rec(qty=400)).max_qty == 100


def test_a_record_without_them_has_none_and_a_bad_one_has_none():
    assert labcfg.derive_limits(rec()) is None
    for bad in (None, [], {"max_trades_day": 0}, {"max_trades_day": 21}, {"max_trades_day": "1"}, {"max_trades_day": True}):
        assert labcfg.derive_limits(own_rec(auto_limits=bad)) is None, bad
    assert labcfg.derive_limits(own_rec(qty=None)) is None
    assert labcfg.derive_limits(own_rec(session_window=["15:55", "15:55"])) is None          # no room for an entry


def test_overlay_gives_the_strategy_its_own_limits_and_an_account_can_be_assigned():
    cfg = desk_cfg()
    store.put(own_rec())
    labcfg.overlay(cfg)
    assert labcfg.limits_of(cfg, "lab_pp_orb") == LabLimits(1, 4, 0.0, "15:54", "15:55")
    assert labcfg.auto_of(cfg, "lab_pp_orb") is True
    s = cfg.strategies["lab_pp_orb"]
    assert (s.qty, s.flat_et, s.accept_until_et, s.accept_from_et) == (4, "15:55", "15:54", "08:20")
    assert labcfg.window_note(labcfg.record_of(cfg, "lab_pp_orb"), labcfg.limits_of(cfg, "lab_pp_orb")) is None


def test_its_own_limits_are_never_written_as_if_typed():
    cfg = desk_cfg()
    store.put(own_rec())
    labcfg.overlay(cfg)
    labcfg.persist_all(cfg)
    assert store.get_desk("pp_orb") is None                    # nothing to say: nothing is written
    # a booking writes the book, and the limits stay empty in the file
    sc = labcfg.sidecar(cfg, "lab_pp_orb", labcfg.limits_of(cfg, "lab_pp_orb"), [{"account": "main", "qty": 2}])
    assert sc["limits"] is None and sc["book"] == [{"account": "main", "qty": 2}]
    labcfg.commit(cfg, "lab_pp_orb", labcfg.limits_of(cfg, "lab_pp_orb"), [{"account": "main", "qty": 2}], None)
    assert labcfg.auto_of(cfg, "lab_pp_orb") is True
    labcfg.persist_all(cfg)
    got = store.get_desk("pp_orb")
    assert got is not None and got["limits"] is None and got["book"] == [{"account": "main", "qty": 2}]


def test_what_the_owner_typed_wins_and_stays():
    cfg = desk_cfg()
    store.put(own_rec())
    store.put_desk("pp_orb", side(limits=LIMITS))
    labcfg.overlay(cfg)
    assert labcfg.limits_of(cfg, "lab_pp_orb") == LabLimits(2, 1, 300.0, "11:00", "15:55")
    assert labcfg.auto_of(cfg, "lab_pp_orb") is False


def test_typing_limits_over_its_own_turns_the_flag_off_and_writes_them():
    cfg = desk_cfg()
    store.put(own_rec())
    labcfg.overlay(cfg)
    typed = labcfg.parse_limits(LIMITS, labcfg.record_of(cfg, "lab_pp_orb"))
    sc = labcfg.sidecar(cfg, "lab_pp_orb", typed, [])
    assert sc["limits"] == LIMITS | {"max_risk_usd": 300.0}
    labcfg.commit(cfg, "lab_pp_orb", typed, [], sc)
    assert labcfg.auto_of(cfg, "lab_pp_orb") is False


def test_promoted_again_derives_again_from_the_new_record():
    cfg = desk_cfg()
    store.put(own_rec())
    labcfg.overlay(cfg)
    store.put(own_rec(session_window=["08:20", "12:00"], promoted="2026-10-10T16:00:00+00:00", auto_limits={"max_trades_day": 3}))
    labcfg.overlay(cfg)
    assert labcfg.limits_of(cfg, "lab_pp_orb") == LabLimits(3, 4, 0.0, "11:59", "12:00")
    assert labcfg.auto_of(cfg, "lab_pp_orb") is True


def test_an_older_record_promoted_again_with_its_own_limits_picks_them_up():
    cfg = desk_cfg()
    store.put(rec())
    labcfg.overlay(cfg)
    assert labcfg.limits_of(cfg, "lab_pp_orb") is None
    store.put(own_rec(promoted="2026-10-10T16:00:00+00:00"))
    labcfg.overlay(cfg)
    assert labcfg.limits_of(cfg, "lab_pp_orb") == LabLimits(1, 4, 0.0, "15:54", "15:55")
    assert labcfg.auto_of(cfg, "lab_pp_orb") is True
    s = cfg.strategies["lab_pp_orb"]
    assert (s.qty, s.flat_et) == (4, "15:55")


def test_an_older_record_is_as_before():
    cfg = desk_cfg()
    store.put(rec())
    labcfg.overlay(cfg)
    assert labcfg.limits_of(cfg, "lab_pp_orb") is None and labcfg.auto_of(cfg, "lab_pp_orb") is False


def test_the_store_reads_the_trade_list_into_auto_limits():
    trades = [{"date": "2025-01-02"}, {"date": "2025-01-02"}, {"date": "2025-01-03"}, {"date": 5}, "junk"]
    assert store.auto_limits(trades) == {"max_trades_day": 2}
    assert store.auto_limits([]) is None and store.auto_limits(None) is None
    assert store.auto_limits([{"date": "d"}] * 99) == {"max_trades_day": 20}
    snap = store.snapshot("pp", "x", {"root": "NQ"}, {"run": {"qty": 4}, "trades": trades}, "r1", [])
    assert snap["auto_limits"] == {"max_trades_day": 2}
    # no trade list, or no trades in it: held to what the Desk holds any strategy to, never to a limit the owner must fill in
    assert store.snapshot("pp", "x", {"root": "NQ"}, {"run": {"qty": 4}}, "r1", [])["auto_limits"] == {"max_trades_day": 20}
    assert store.snapshot("pp", "x", {"root": "NQ"}, {"run": {"qty": 4}, "trades": []}, "r1", [])["auto_limits"] == {"max_trades_day": 20}


def test_the_runner_derives_the_same_limits_as_the_desk():
    from dataclasses import asdict

    from homebase.labrun import deskside
    cases = [own_rec(), own_rec(session_window=["09:25", "16:00"]), own_rec(session_window=["09:25", "11:30"]), own_rec(qty=40),
             own_rec(session_window=["15:55", "15:55"]), own_rec(auto_limits={"max_trades_day": 20}),
             own_rec(auto_limits={"max_trades_day": 21}), own_rec(auto_limits={"max_trades_day": True}),
             own_rec(auto_limits=None), own_rec(qty=None), own_rec(session_window=None), rec()]
    for r in cases:
        want = labcfg.derive_limits(r)
        got = deskside.own_limits(r)
        assert got == (asdict(want) if want else None), r


def test_the_runner_books_a_strategy_with_its_own_limits_and_lets_typed_ones_win():
    from homebase.labrun import deskside
    r = own_rec()
    book = [{"account": "main", "qty": 2}]
    s = {"mark": store.mark_of(r), "limits": None, "book": book}
    assert deskside.booked(s, r) == ["main"]
    assert deskside.limits_of(s, r)["flat_et"] == "15:55"
    assert deskside.booked(s, rec()) is None                               # no auto_limits on the record: no limits, no book
    typed = {**s, "limits": LIMITS}
    assert deskside.limits_of(typed, r) == LIMITS
    assert deskside.booked({**s, "limits": {**LIMITS, "flat_et": "16:30"}}, r) is None     # typed and unreadable: not the own ones
