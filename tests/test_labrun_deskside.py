"""DeskSide (Step B, task B4): one strategy's day as the Desk tells it -- the latest whole snapshot, and what the
strategy's child has been told so far. Pure: no network, no files, no clock but the one handed in."""
from __future__ import annotations

from homebase.labrun.deskside import DeskSide

MARK = ["ab", "2026-10-09T12:00:00+00:00"]
DATE = "2024-03-05"
WORKING = {"status": "working"}
CANCELLED = {"status": "cancelled"}


def filled(px=110.25, sl=105.25, tp=120.25, ms=1000):
    return {"status": "filled", "fill_px": px, "fill_sl": sl, "fill_tp": tp, "fill_ms": ms}


def snap(orders=None, flat=True, answered=(), rounds=(), **kw):
    orders = orders or {}
    return {"strategy": "lab_pp", "mark": list(MARK), "date": DATE, "enabled": True, "armed": True, "killed": False,
            "stopped": None, "rounds": list(rounds), "answered": list(answered),
            "brain": {"flat": flat, "working": sum(1 for o in orders.values() if o["status"] == "working"),
                      "entries_today": 0, "orders": {str(k): v for k, v in orders.items()}}, **kw}


def entry(i, **kw):
    return {"op": "entry", "id": i, "kind": "stop", "side": "long", "price": 110.0, "qty": 1, "own_qty": False,
            "sl": 105.0, "tp": None, "tp_rr": None, "ref": 110.0, "move": False, **kw}


def side(accounts=("a1",), **kw):
    wall = [100.0]
    s = DeskSide("lab_pp", MARK, DATE, list(accounts), wall=lambda: wall[0], **kw)
    s.clock = wall
    return s


def up(i, status, px=None, sl=None, tp=None, ms=None):
    return {"id": i, "status": status, "fill_px": px, "fill_sl": sl, "fill_tp": tp, "fill_ms": ms}


# ---------------------------------------------------------------- what the child is told
def test_an_order_is_working_then_filled_exactly_as_the_brain_says_and_is_told_once():
    s = side()
    s.take(snap())
    s.sent(1, [entry(1)])
    assert s.updates() == [] and s.working() == [1]                          # the child believes it is working: no news
    s.take(snap({1: WORKING}, answered=[1]))
    assert s.updates() == []
    s.take(snap({1: filled()}, flat=False, answered=[1]))
    assert s.updates() == [up(1, "filled", 110.25, 105.25, 120.25, 1000)] and s.flat is False and s.working() == []
    assert s.updates() == []                                                 # told once
    s.take(snap({1: filled(sl=110.25)}, flat=False, answered=[1]))            # the stop was moved after the fill
    assert s.updates() == [up(1, "filled", 110.25, 110.25, 120.25, 1000)]
    s.take(snap({1: filled(sl=110.25)}, flat=True, answered=[1]))
    assert s.updates() == [] and s.flat is True


def test_a_snapshot_older_than_the_send_says_nothing_about_the_order():
    """The stream is its own thread: a snapshot built before the Desk answered event 3 does not know order 1 yet.
    That is not "cancelled"."""
    s = side()
    s.sent(3, [entry(1)])
    s.take(snap(answered=[1, 2]))
    assert s.updates() == [] and s.working() == [1]
    s.take(snap({1: WORKING}, answered=[1, 2, 3]))
    assert s.updates() == []


def test_an_entry_the_desk_never_answered_is_told_nothing_until_the_stream_says_what_happened():
    s = side()
    s.sent(3, [entry(1)])                                                    # its answer never came
    s.take(snap(answered=[2]))
    assert s.updates() == []                                                 # the Desk has not seen event 3: no news
    s.take(snap({1: filled()}, flat=False, answered=[2, 3]))                 # it did get there, and it filled
    assert s.updates() == [up(1, "filled", 110.25, 105.25, 120.25, 1000)]

    s = side()
    s.sent(3, [entry(1)])
    s.take(snap(answered=[2, 3]))                                            # answered, and no account holds it
    assert s.updates() == [up(1, "cancelled")]

    s = side()
    s.sent(3, [entry(1)])
    s.take(snap(answered=[2, 4]))                                            # a later event was answered: 3 can never
    assert s.updates() == [up(1, "cancelled")]                               # be taken any more (the Desk's own rule)


def test_an_entry_that_never_left_or_that_the_desk_refused_is_cancelled_to_the_child_at_once():
    s = side()
    s.sent(1, [entry(1), entry(2)])
    s.dead([1])
    assert s.updates() == [up(1, "cancelled")] and s.working() == [2]
    assert s.updates() == []
    s.take(snap({1: WORKING, 2: WORKING}, answered=[1]))                     # whatever is said later: it stays dead
    assert s.updates() == []


def test_a_cancel_the_child_sent_is_cancelled_in_its_own_mind_and_a_fill_that_beat_it_is_told():
    s = side()
    s.sent(1, [entry(1)])
    s.take(snap({1: WORKING}, answered=[1]))
    s.sent(2, [{"op": "cancel", "id": 1}])
    assert s.working() == [] and s.updates() == []
    s.take(snap({1: WORKING}, answered=[1]))                                 # older than the cancel: no news
    assert s.updates() == []
    s.take(snap({1: CANCELLED}, answered=[1, 2]))
    assert s.updates() == []                                                 # as the child already believes
    t = side()
    t.sent(1, [entry(1)])
    t.sent(2, [{"op": "cancel", "id": 1}])
    t.take(snap({1: filled()}, flat=False, answered=[1, 2]))                 # the fill beat the cancel
    assert t.updates() == [up(1, "filled", 110.25, 105.25, 120.25, 1000)]
    u = side()
    u.sent(1, [entry(1)])
    u.sent(2, [{"op": "cancel", "id": 1}])
    u.take(snap({1: WORKING}, answered=[1, 2]))                              # the cancel was applied and did not take
    assert u.updates() == [up(1, "working")] and u.working() == [1]


def test_a_flatten_cancels_every_working_order_in_the_childs_mind():
    s = side()
    s.sent(1, [entry(1), entry(2), {"op": "oco", "ids": [1, 2]}])
    s.take(snap({1: filled(), 2: CANCELLED}, flat=False, answered=[1]))
    s.updates()
    s.sent(2, [entry(3), {"op": "flatten", "reason": "time"}])
    assert s.working() == []
    s.take(snap({1: filled(), 2: CANCELLED, 3: CANCELLED}, flat=True, answered=[1, 2]))
    assert s.updates() == []


def test_a_filled_order_never_turns_cancelled_because_a_snapshot_leaves_it_out():
    s = side()
    s.sent(1, [entry(1)])
    s.take(snap({1: filled()}, flat=False, answered=[1]))
    s.updates()
    s.take(snap({}, answered=[1]))
    assert s.updates() == []


def test_an_order_the_child_never_made_and_a_status_that_does_not_read_are_no_news():
    s = side()
    s.sent(1, [entry(1)])
    s.take(snap({1: {"status": "exploded"}, 9: filled(), "x": WORKING}, answered=[1]))
    assert s.updates() == []
    s.take({**snap({1: WORKING}, answered=[1]), "brain": None})              # a brain that does not read: no news
    assert s.updates() == [] and s.flat is True
    s.take({**snap(answered=[1]), "brain": {"flat": "yes", "orders": []}})
    assert s.updates() == []


# ---------------------------------------------------------------- flat
def test_flat_is_the_brains_and_before_any_snapshot_it_is_what_the_day_started_with():
    assert side().flat is True and side(flat=False).flat is False
    s = side(flat=False)
    s.take(snap(flat=True))
    assert s.flat is True
    s.take(snap(flat=False))
    assert s.flat is False


# ---------------------------------------------------------------- a snapshot of another day or another promotion
def test_a_snapshot_with_another_mark_or_date_is_ignored_and_counts_as_silence():
    s = side()
    assert s.silent() is True                                                # nothing heard yet
    assert s.take(snap({}, flat=False)) is True and s.silent() is False and s.flat is False
    assert s.take({**snap(flat=True, killed=True, stopped="x"), "mark": ["ab", "another promotion"]}) is False
    assert s.flat is False and s.killed is False and s.stopped is None       # nothing of it is believed
    assert s.silent() is True                                                # ... and the Desk is not answering for us
    assert s.take({**snap(flat=True), "date": "2024-03-04"}) is False and s.silent() is True and s.flat is False
    assert s.take(snap(flat=True)) is True and s.silent() is False and s.flat is True
    for bad in (None, [], {"mark": MARK}, {**snap(), "strategy": "lab_other"}):
        assert s.take(bad) is False


def test_the_desk_is_silent_when_the_stream_is_down_or_nothing_was_heard_for_fifteen_seconds():
    s = side()
    s.take(snap())
    s.clock[0] += 15.0
    assert s.silent() is False
    s.clock[0] += 0.1
    assert s.silent() is True
    s.heard()                                                                # the stream's own heartbeat
    assert s.silent() is False
    s.down()
    assert s.silent() is True
    s.heard()                                                                # the stream is back, but it has not said
    assert s.silent() is True                                                # anything about this strategy yet
    s.take(snap())
    assert s.silent() is False
    s.gone()                                                                 # a whole state that does not list it
    assert s.silent() is True


def test_what_the_desk_said_before_its_stream_dropped_is_still_told_and_nothing_newer_is_made_up():
    s = side()
    s.sent(1, [entry(1), entry(2)])
    s.take(snap({1: filled(), 2: WORKING}, flat=False, answered=[1]))
    s.down()                                                                 # before the child's next event
    assert s.updates() == [up(1, "filled", 110.25, 105.25, 120.25, 1000)] and s.flat is False
    assert s.updates() == [] and s.working() == [2]                          # order 2: still what was last said
    s.take({**snap({1: CANCELLED, 2: CANCELLED}, answered=[1]), "mark": ["other", "promotion"]})
    assert s.updates() == []                                                 # a snapshot that is ignored tells nothing


def test_killed_and_stopped_are_read_from_a_snapshot_of_this_day_only():
    s = side()
    s.take(snap(killed=True))
    assert s.killed is True and s.stopped is None
    s.take(snap(stopped="Stopped for today."))
    assert s.killed is False and s.stopped == "Stopped for today."
    assert s.answered == []
    s.take(snap(answered=[3, 1, "x", True, 2]))
    assert s.answered == [1, 2, 3]


# ---------------------------------------------------------------- the day's real trades
def rnd(account="a1", n=1, status="done", side_="Buy", qty=1, entry=110.25, exit_=120.25, reason="tp", pnl=200.0,
        entry_ms=1_709_649_000_000, exit_ms=1_709_649_600_000, **kw):
    return {"account": account, "round": n, "status": status, "date": DATE, "carried": False, "iid": {side_: n},
            "qty": qty, "entry_side": side_, "entry_qty": qty, "entry_fill": entry, "exit_qty": qty, "exit_fill": exit_,
            "exit_reason": reason, "sl": 105.25, "tp": 120.25, "pnl": pnl, "clean": True, "entry_ms": entry_ms,
            "exit_ms": exit_ms, "why": None, **kw}


def test_the_lead_accounts_finished_rounds_are_the_days_trades_in_the_testers_shape():
    s = side(accounts=("a1", "a2"))
    s.take(snap(rounds=[rnd("a2", pnl=180.0, entry=110.5), rnd(), rnd(n=2, side_="Sell", entry=100.0, exit_=101.0,
                                                                     reason="sl", pnl=-20.0, qty=2)]))
    assert s.lead() == "a1"
    assert s.trades() == [
        {"side": "long", "qty": 1, "entry_ns": 1_709_649_000_000_000_000, "entry_price": 110.25,
         "exit_ns": 1_709_649_600_000_000_000, "exit_price": 120.25, "exit_reason": "tp", "net": 200.0},
        {"side": "short", "qty": 2, "entry_ns": 1_709_649_000_000_000_000, "entry_price": 100.0,
         "exit_ns": 1_709_649_600_000_000_000, "exit_price": 101.0, "exit_reason": "sl", "net": -20.0}]
    assert s.unpriced() == 0


def test_the_lead_is_the_first_booked_account_that_has_a_round_today():
    s = side(accounts=("a1", "a2"))
    assert s.lead() is None and s.trades() == []
    s.take(snap(rounds=[rnd("a2")]))                                         # a1 sat the trade out
    assert s.lead() == "a2" and len(s.trades()) == 1
    s.take(snap(rounds=[rnd("a9")]))                                         # an account that is not in the book
    assert s.lead() is None and s.trades() == []
    s.accounts = ["a9"]
    assert s.lead() == "a9"


def test_a_carried_row_is_an_old_block_never_a_trade_and_never_makes_the_lead():
    s = side(accounts=("a1", "a2"))
    s.take(snap(rounds=[rnd("a1", carried=True, date="2024-03-04"), rnd("a2")]))
    assert s.lead() == "a2" and [t["net"] for t in s.trades()] == [200.0]
    s.take(snap(rounds=[rnd("a1", carried=True, date="2024-03-04")]))
    assert s.lead() is None and s.trades() == [] and s.unpriced() == 0
    s.take(snap(rounds=[rnd("a1", date="2024-03-04")]))                      # a row of another date is not today's either
    assert s.lead() is None and s.trades() == []
    s.take(snap(rounds=[rnd("a1", carried=True)]))                           # carried is carried, whatever its date reads
    assert s.lead() is None and s.trades() == [] and s.unpriced() == 0


def test_a_round_that_is_not_a_finished_trade_is_not_a_trade():
    s = side()
    rows = [rnd(n=1, status="live", exit_=None, exit_ms=None, pnl=None, reason=None),          # still open
            rnd(n=2, status="done", entry=None, entry_ms=None, exit_=None, exit_ms=None, reason="cancelled", pnl=None,
                entry_qty=0),                                                                  # never filled
            rnd(n=3, status="error", entry=None, entry_qty=0, exit_=None, pnl=None),           # a failed entry
            rnd(n=4)]
    s.take(snap(rounds=rows, flat=False))
    assert [t["exit_reason"] for t in s.trades()] == ["tp"] and s.unpriced() == 0
    s.take(snap(rounds=[rnd(n=1, exit_=None, exit_ms=None, pnl=None, reason="flat")]))         # out, price unknown
    assert s.trades() == [] and s.unpriced() == 1
    s.take(snap(rounds=[rnd(pnl=None), "not a row", {"account": "a1"}]))
    assert [t["net"] for t in s.trades()] == [0.0]


# ---------------------------------------------------------------- a runner that starts again
def test_what_the_child_was_told_before_is_put_back_and_only_the_difference_is_told_after():
    """The replay of the tell-log: the fresh child is fed the logged updates, so DeskSide must believe what it
    believes; the first event after the log then carries only what changed since."""
    s = side(flat=False)
    s.sent(1, [entry(1), entry(2), {"op": "oco", "ids": [1, 2]}])
    s.told([up(1, "filled", 110.25, 105.25, 120.25, 1000), up(2, "cancelled")])
    s.sent(2, [entry(3)])
    s.dead([3])
    s.told([up(3, "cancelled")])
    s.take(snap({1: filled(), 2: CANCELLED}, flat=True, answered=[1]))
    assert s.updates() == [] and s.flat is True
    s.take(snap({1: filled(tp=121.0), 2: CANCELLED}, flat=True, answered=[1]))
    assert s.updates() == [up(1, "filled", 110.25, 105.25, 121.0, 1000)]


# ---------------------------------------------------------------- the Desk's name for it, and the Desk's book
def test_the_desk_id_is_built_with_the_desks_own_prefix_and_the_runner_never_imports_the_desks_module():
    import subprocess
    import sys
    from homebase import labcfg
    from homebase.labrun import deskside
    assert deskside.PREFIX == labcfg.PREFIX and deskside.desk_id("pp_orb") == labcfg.desk_id("pp_orb") == "lab_pp_orb"
    assert deskside.FLAT_LATEST == labcfg.FLAT_LATEST
    code = ("import sys; import homebase.labrun.host, homebase.labrun.deskside, homebase.labrun.deskclient, "
            "homebase.labrun.__main__; "
            "bad = [m for m in sys.modules if m in ('homebase.labcfg', 'homebase.labdesk', 'homebase.engine', "
            "'homebase.server', 'homebase.desk_api', 'homebase.trading')]; print(bad)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=120)
    assert out.stdout.strip() == "[]", out.stdout + out.stderr              # the runner loads nothing the Desk owns


REC = {"name": "pp", "sha256": "ab", "promoted_utc": MARK[1], "session_window": ["09:25", "16:00"]}
LIMITS = {"max_trades_day": 3, "max_qty": 2, "max_risk_usd": 300, "last_entry_et": "11:00", "flat_et": "15:55"}
LIMIT_CASES = [
    LIMITS, {**LIMITS, "max_risk_usd": 300.5}, {**LIMITS, "max_trades_day": 20, "max_qty": 10},
    {**LIMITS, "last_entry_et": "09:25"}, {**LIMITS, "last_entry_et": "09:24"}, {**LIMITS, "last_entry_et": "15:55"},
    {**LIMITS, "flat_et": "15:56"}, {**LIMITS, "flat_et": "11:00"}, {**LIMITS, "flat_et": "25:00"}, {**LIMITS, "flat_et": 1555},
    {**LIMITS, "max_trades_day": 0}, {**LIMITS, "max_trades_day": 21}, {**LIMITS, "max_trades_day": 2.0},
    {**LIMITS, "max_trades_day": True}, {**LIMITS, "max_qty": 0}, {**LIMITS, "max_qty": 11}, {**LIMITS, "max_qty": "1"},
    {**LIMITS, "max_risk_usd": 0}, {**LIMITS, "max_risk_usd": -5}, {**LIMITS, "max_risk_usd": float("nan")},
    {**LIMITS, "max_risk_usd": float("inf")}, {**LIMITS, "max_risk_usd": 10 ** 400}, {**LIMITS, "max_risk_usd": None},
    {**LIMITS, "max_risk_usd": 2e9}, {**LIMITS, "max_risk_usd": 1e9},
    {k: v for k, v in LIMITS.items() if k != "flat_et"}, {}, None, [], "limits", 5,
]


def test_limits_read_exactly_when_the_desk_itself_would_take_them():
    from homebase import labcfg
    from homebase.labrun import deskside

    def desk_takes(limits, rec):
        try:
            labcfg.parse_limits(limits, rec)
            return True
        except ValueError:
            return False
    recs = [REC, {**REC, "session_window": ["10:00", "12:00"]}, {**REC, "session_window": None},
            {**REC, "session_window": ["nine", "ten"]}, {k: v for k, v in REC.items() if k != "session_window"}]
    seen = set()
    for rec in recs:
        for limits in LIMIT_CASES:
            want = desk_takes(limits, rec)
            assert deskside.limits_read(limits, rec) is want, (limits, rec)
            seen.add(want)
    assert seen == {True, False}


def test_a_sidecar_gives_a_book_only_when_it_reads_is_this_promotions_has_limits_and_has_accounts():
    from homebase.labrun.deskside import booked
    side_ = {"mark": list(MARK), "limits": dict(LIMITS), "book": [{"account": "a1", "qty": 1}, {"account": "a2", "qty": 2}],
             "written_utc": "x"}
    assert booked(side_, REC) == ["a1", "a2"]                                # the book's own order: a1 leads
    assert booked({**side_, "book": list(reversed(side_["book"]))}, REC) == ["a2", "a1"]
    assert booked(None, REC) is None                                         # no sidecar, or one that does not read
    assert booked([], REC) is None and booked("x", REC) is None
    assert booked({**side_, "mark": ["ab", "promoted again"]}, REC) is None  # another promotion's
    assert booked({k: v for k, v in side_.items() if k != "mark"}, REC) is None
    assert booked({**side_, "book": []}, REC) is None                        # no account: shadow
    assert booked({**side_, "book": None}, REC) is None
    assert booked({**side_, "limits": None}, REC) is None                    # no limits: no book
    assert booked({**side_, "limits": {**LIMITS, "flat_et": "16:30"}}, REC) is None      # limits that do not read
    rows = [{"account": "a1", "qty": 0}, {"account": "", "qty": 1}, {"account": 5, "qty": 1}, "row", {"account": "a3", "qty": True},
            {"account": "a4", "qty": 1}, {"account": "a4", "qty": 2}]
    assert booked({**side_, "book": rows}, REC) == ["a4"]                    # only a row that is a booking, once
    assert booked({**side_, "book": rows[:5]}, REC) is None
