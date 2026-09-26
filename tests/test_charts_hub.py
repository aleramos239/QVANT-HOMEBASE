"""Hub: history + today, live == fresh rebuild, per-subscriber cursors, reset, roll."""
from __future__ import annotations

import datetime as dt

from homebase.charts.bars import Bar, BarBuilder, BarSpec
from homebase.charts.history import History
from homebase.charts.hub import Hub, Stream
from homebase.charts.store import TickStore
from homebase.charts.tick import SideClassifier, from_row
from tests.charts_util import D, rows, session_ms, write_archive

P = D - dt.timedelta(days=1)
M1 = BarSpec("time", 60)


def setup(tmp_path):
    base = tmp_path / "ticks"
    write_archive(base, "NQ", P, "NQZ6",
                  rows(session_ms(P, 9, 30), [100 + 0.25 * (i % 8) for i in range(300)]))
    clock = [session_ms(D, 9, 31)]
    hub = Hub(History(TickStore(base), cache_dir=tmp_path / "cache"), lambda: clock[0])
    today = rows(session_ms(D, 9, 30), [200 + 0.25 * (i % 5) for i in range(150)],
                 first_id=10_000, sides=[1 if i % 3 else -1 for i in range(150)])
    return hub, today, clock


def ticks_of(rs):
    clf = SideClassifier()
    return [from_row(r, clf) for r in rs]


def open_stream(hub, spec=M1, keys=("vwap", "cumdelta"), sub=("conn", "c1")):
    s = hub.attach(hub.prepare("NQ", spec, list(keys)))
    hub.subscribe(s, sub)
    return s


def test_payload_has_past_sessions_then_today(tmp_path):
    hub, today, _ = setup(tmp_path)
    hub.start_today("NQ", D, ticks_of(today[:60]), {"date": D.isoformat(), "contract": "NQZ6",
                                                    "source": "live", "approx": False, "gaps": []})
    p = open_stream(hub).payload()
    assert [b["s"] for b in p["bars"]] == [P.isoformat()] * 5 + [D.isoformat()]
    assert p["live"] is True and len(p["studies"]["vwap"]) == 6 and len(p["studies"]["cumdelta"]) == 6
    assert [s["date"] for s in p["sessions"]] == [P.isoformat(), D.isoformat()]
    assert p["tick_size"] == 0.25 and "fp" in p["bars"][0]


def test_live_ticks_end_where_a_fresh_rebuild_starts(tmp_path):
    hub, today, clock = setup(tmp_path)
    hub.start_today("NQ", D, [])
    s = open_stream(hub, keys=("vwap", "cumdelta", "ema:5", "profile"))
    for r in today:
        hub.on_ticks("NQ", [r])
        clock[0] = r["ts_ms"]
        hub.on_clock(r["ts_ms"] - 1500)
    fresh = hub.prepare("NQ", M1, ["vwap", "cumdelta", "ema:5", "profile"]).stream
    assert s.payload() == fresh.payload()


def test_updates_are_per_subscriber_and_coalesced(tmp_path):
    hub, today, _ = setup(tmp_path)
    hub.start_today("NQ", D, [])
    s = open_stream(hub)
    hub.on_ticks("NQ", today[:130])                 # 2 minutes close, a 3rd develops
    out = hub.drain()
    assert len(out) == 1 and out[0][0] == ("conn", "c1")
    msg = out[0][1]
    assert msg["type"] == "update" and len(msg["closed"]) == 2 and msg["live"] is not None
    assert len(msg["studies"]["vwap"]["closed"]) == 2 and msg["studies"]["vwap"]["live"]
    assert hub.drain() == []                       # nothing new
    late = hub.attach(hub.prepare("NQ", M1, ["vwap"]))
    assert late is s                               # one stream, shared
    hub.subscribe(s, ("conn2", "x"))
    hub.on_ticks("NQ", today[130:131])
    subs = {sub: m for sub, m in hub.drain()}
    assert subs[("conn", "c1")]["closed"] == [] and subs[("conn2", "x")]["closed"] == []


def test_attach_catches_up_ticks_that_arrived_during_prepare(tmp_path):
    hub, today, _ = setup(tmp_path)
    hub.start_today("NQ", D, ticks_of(today[:50]))
    prep = hub.prepare("NQ", M1, ["vwap"])
    hub.on_ticks("NQ", today[50:140])                # no stream yet: only the tape grows
    s = hub.attach(prep)
    want = hub.prepare("NQ", M1, ["vwap"]).stream
    assert s.payload() == want.payload()


def test_reseeding_today_resets_its_streams(tmp_path):
    hub, today, _ = setup(tmp_path)
    hub.start_today("NQ", D, [])
    open_stream(hub)
    hub.start_today("NQ", D, ticks_of(today))
    assert hub.drain() == [(("conn", "c1"), {"type": "reset"})]
    assert hub.streams == {}


def test_the_18_et_roll_starts_a_new_tape(tmp_path):
    hub, today, _ = setup(tmp_path)
    hub.start_today("NQ", D, ticks_of(today))
    nxt = D + dt.timedelta(days=1)
    hub.on_ticks("NQ", rows(session_ms(nxt, 18, 1), [300.0], first_id=99_999))
    assert hub.today_date["NQ"] == nxt and len(hub.today["NQ"]) == 1


def test_the_last_unsubscribe_drops_the_stream(tmp_path):
    hub, _, _ = setup(tmp_path)
    hub.start_today("NQ", D, [])
    open_stream(hub, sub=("a", "1"))
    open_stream(hub, sub=("b", "1"))
    hub.unsubscribe(("a", "1"))
    assert len(hub.streams) == 1
    hub.drop_conn("b")
    assert hub.streams == {}


def test_no_reset_loop_for_a_root_with_no_today_tape(tmp_path):
    """A root nobody has ticked yet (no file on a replay date; a recorded
    root that hasn't started ticking) must not be reset every drain forever:
    prepare() and attach() must see the SAME "no tape yet" state (None both
    times), not two distinct fresh empty-list objects."""
    hub, _, _ = setup(tmp_path)
    s = hub.attach(hub.prepare("ES", M1, ["vwap"]))
    hub.subscribe(s, ("conn", "c1"))
    for _ in range(3):
        assert hub.drain() == []
        assert hub.streams == {("ES", M1.key): s}


def test_attach_resets_when_the_roll_lands_inside_prepare(tmp_path):
    """prepare() reads self.today_date (the history cutoff) BEFORE the slow
    history load, and today's tape/info AFTER it. If the 18:00 roll lands in
    that gap, prepare() returns a stream built from a torn mix: the OLD
    cutoff (so the session that just closed is excluded from history) but
    the NEW tape/info (so that session's ticks aren't there either). The
    tape object itself never changes again before attach() runs, so the
    plain tape-identity check alone can't catch this -- attach() must also
    compare today_date."""
    hub, today, _ = setup(tmp_path)
    hub.start_today("NQ", D, ticks_of(today))

    class HookHistory(History):
        hook = None

        def bars(self, root, spec, d):
            hook, HookHistory.hook = HookHistory.hook, None
            if hook:
                hook()                                   # the loop runs on_ticks meanwhile
            return super().bars(root, spec, d)

    hub.history = HookHistory(hub.store, cache_dir=hub.history.cache_dir)
    nxt = D + dt.timedelta(days=1)
    HookHistory.hook = lambda: hub.on_ticks(
        "NQ", rows(session_ms(nxt, 18, 1), [300.0], first_id=99_999))
    p = hub.prepare("NQ", M1, ["vwap"])
    s = hub.attach(p)
    hub.subscribe(s, ("conn", "c1"))
    assert hub.drain() == [(("conn", "c1"), {"type": "reset"})]


def test_the_roll_resets_the_side_classifier_to_match_a_reload(tmp_path):
    """A reload classifies each session's ticks with a FRESH SideClassifier
    (store.ticks_from_table starts one per file). The live tape must match
    that at the 18:00 roll, not carry the previous session's last
    price/side across the boundary."""
    hub, today, _ = setup(tmp_path)
    hub.start_today("NQ", D, ticks_of(today))          # D's last trade: 201.0
    s = hub.attach(hub.prepare("NQ", M1, ["cumdelta"]))
    hub.subscribe(s, ("conn", "c1"))
    nxt = D + dt.timedelta(days=1)
    t0 = session_ms(nxt, 18, 0, 1)
    opening = [{"ts_ms": t0 + i * 1000, "price": 200.0, "size": 5,
                "bid": 200.25, "ask": 200.0, "bid_size": 5, "ask_size": 5,
                "id": 99_000 + i} for i in range(3)]     # crossed quote -> tick rule
    hub.on_ticks("NQ", opening)
    assert [t.side for t in hub.today["NQ"]] == [t.side for t in ticks_of(opening)]
    assert [x["date"] for x in s.sessions][-1] == nxt.isoformat()


def test_a_24_7_root_rolls_into_its_saturday_session(tmp_path):
    """Bitcoin trades 24/7: its 17:00 hour is still Friday's session and a
    Saturday print opens Saturday's own session. A classic root still
    files a weekend print into Monday."""
    hub, _, _ = setup(tmp_path)
    fri, sat, mon = (D + dt.timedelta(days=n) for n in (1, 2, 4))
    hub.start_today("BTC", fri, [])
    hub.on_ticks("BTC", rows(session_ms(fri, 17, 30), [100_000.0], first_id=1)
                 + rows(session_ms(sat, 10, 0), [100_005.0], first_id=2))
    assert hub.today_date["BTC"] == sat and [t.id for t in hub.today["BTC"]] == [2]
    hub.start_today("NQ", mon, [])
    hub.on_ticks("NQ", rows(session_ms(sat, 10, 0), [200.0], first_id=3))
    assert hub.today_date["NQ"] == mon and [t.id for t in hub.today["NQ"]] == [3]


def test_a_24_7_stream_runs_through_the_17_00_hour_without_duplicate_bars(tmp_path):
    """A stream's builder must know its root's trading day: with the classic
    17:00 close, on_clock would close every Bitcoin bar of the 17:00 hour
    at once and the next tick would reopen it -- one duplicate bar a tick."""
    hub, _, _ = setup(tmp_path)
    fri = D + dt.timedelta(days=1)
    hub.start_today("BTC", fri, [])
    s = hub.attach(hub.prepare("BTC", M1, []))
    hub.subscribe(s, ("conn", "c1"))
    for r in rows(session_ms(fri, 17, 10), [100_000.0 + 5 * (i % 3) for i in range(150)]):
        hub.on_ticks("BTC", [r])
        hub.on_clock(r["ts_ms"] - 1500)
    assert [b.t for b in s.bars] + [s.builder.cur.t] == [
        session_ms(fri, 17, 10), session_ms(fri, 17, 11), session_ms(fri, 17, 12)]


def test_a_late_print_at_a_24_7_roll_adds_no_bar_to_the_old_session(tmp_path):
    """The chart side of the roll edge: the clock closed Friday's 17:59 bar,
    then a 17:59:59.9 print arrives before Saturday's first. No extra 18:00
    candle for Friday, and Friday's cumulative delta does not take it."""
    hub, _, _ = setup(tmp_path)
    fri = D + dt.timedelta(days=1)
    sat = fri + dt.timedelta(days=1)
    hub.start_today("BTC", fri, [])
    s = hub.attach(hub.prepare("BTC", M1, ["vwap", "cumdelta"]))
    hub.subscribe(s, ("conn", "c1"))
    hub.on_ticks("BTC", rows(session_ms(fri, 17, 59, 30), [100_000.0], first_id=1))
    hub.on_clock(session_ms(sat, 18, 0))                      # the pump: clock - 1.5 s grace
    hub.on_ticks("BTC", rows(session_ms(fri, 17, 59, 59) + 900, [100_010.0], size=3, first_id=2))
    hub.on_ticks("BTC", rows(session_ms(sat, 18, 0) + 500, [100_020.0], first_id=3))
    assert [(b.session, b.t) for b in s.bars] == [(fri.isoformat(), session_ms(fri, 17, 59))]
    assert (s.builder.cur.session, s.builder.cur.t) == (sat.isoformat(), session_ms(sat, 18, 0))
    assert s.values["cumdelta"] == [1]


def test_a_previous_session_straggler_never_rolls_the_tape_back(tmp_path):
    """Only a FORWARD session change is a roll. A print from an older
    session (the one historical trade a weekend subscribe returns; an
    undeduped straggler) used to 'roll' the hub back: today's tape wiped,
    a bogus old-session bar on every open chart, History cleared -- and the
    next of today's ticks rolled it forward again, wiping the tape twice."""
    hub, today, _ = setup(tmp_path)
    hub.start_today("NQ", D, ticks_of(today))
    s = open_stream(hub)
    tape, bars, sessions = list(hub.today["NQ"]), len(s.bars), list(s.sessions)
    memo = dict(hub.history.memo)
    hub.on_ticks("NQ", rows(session_ms(P, 16, 59), [123.0], first_id=77_777))
    assert hub.today_date["NQ"] == D and hub.today["NQ"] == tape
    assert len(s.bars) == bars and s.builder.cur.session == D.isoformat()
    assert s.sessions == sessions and hub.history.memo == memo


def test_the_history_message_carries_the_most_recent_20000_bars(tmp_path):
    """A fine bar type over a long history was unbounded work on the event
    loop (tick:1: ~4 s of payload and ~185 MB of JSON per session): history
    carries the most recent 20,000 bars (the live one included), each
    study's values sliced to stay aligned; updates continue from the
    stream's own cursor as before."""
    hub, _, _ = setup(tmp_path)
    s = Stream("NQ", M1, 0.25, BarBuilder(M1, 0.25))
    s.add_study("ema:3")
    t0 = session_ms(D, 9, 30)
    for i in range(20_050):
        s.commit(Bar.open_at(t0 + i * 60_000, D.isoformat(), 100.0 + i % 7))
    s.builder.cur = Bar.open_at(t0 + 20_050 * 60_000, D.isoformat(), 105.0)
    p = s.payload()
    assert len(p["bars"]) == 20_000 and p["live"] is True
    assert p["bars"][0]["ms"] == s.bars[51].t and p["bars"][-2]["ms"] == s.bars[-1].t
    assert p["studies"]["ema:3"] == s.values["ema:3"][51:] + [s.studies["ema:3"].preview(s.builder.cur)]
    hub.streams[s.key] = s
    hub.subscribe(s, ("conn", "c1"))
    assert s.subs[("conn", "c1")] == 20_050
    s.commit(s.builder.cur)
    s.builder.cur, s.dirty = None, True
    [(_, up)] = hub.drain()
    assert len(up["closed"]) == 1 and up["closed"][0]["ms"] == t0 + 20_050 * 60_000
