"""Hub: history + today, live == fresh rebuild, per-subscriber cursors, reset, roll."""
from __future__ import annotations

import datetime as dt
import random
import time

import pytest

import homebase.charts.hub as hub_mod
from homebase.charts.bars import Bar, BarBuilder, BarSpec, build
from homebase.charts.history import History
from homebase.charts.hub import Hub, Stream, sessions_back, warm_bars
from homebase.charts.store import TickStore
from homebase.charts.studies import make
from homebase.charts.tick import SideClassifier, from_row
from tests.charts_util import D, rows, session_ms, weekdays_before, write_archive

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


def test_the_history_message_carries_the_point_value(tmp_path):
    """The page turns a position's price move into dollars with it (null: the page shows points only)."""
    hub, today, _ = setup(tmp_path)
    hub.start_today("NQ", D, ticks_of(today[:60]))
    assert open_stream(hub).payload()["point_value"] == 20.0
    unknown = Stream("ZZ", M1, 0.25, BarBuilder(M1, 0.25, "ZZ"))
    assert unknown.payload()["point_value"] is None


# ---- deep history: scroll-back chunks (spec §5) ----
def deep(tmp_path, n=8):
    """A hub over n completed weekday sessions before D (3 one-minute bars each, 09:30-09:32; session k
    trades around 100 + k) with D's first minutes as today's tape."""
    base = tmp_path / "ticks"
    days = weekdays_before(D, n)
    for k, d in enumerate(days):
        write_archive(base, "NQ", d, "NQZ6", rows(session_ms(d, 9, 30), [100 + k + 0.25 * (i % 4) for i in range(9)],
                                                  step_ms=20_000, first_id=1000 * (k + 1)))
    hub = Hub(History(TickStore(base), cache_dir=tmp_path / "cache"), lambda: session_ms(D, 9, 31))
    hub.start_today("NQ", D, ticks_of(rows(session_ms(D, 9, 30), [200 + 0.25 * (i % 5) for i in range(30)],
                                           first_id=90_000)))
    return hub, days


def test_the_default_depth_per_bar_type():
    assert [sessions_back(BarSpec(k, n)) for k, n in (("time", 5), ("time", 30), ("tick", 500), ("volume", 2000),
                                                        ("range", 10))] == [1, 1, 1, 1, 1]
    assert [sessions_back(BarSpec("time", n)) for n in (60, 300, 600, 3600, 14400, 86400)] == [5, 5, 20, 20, 250, 250]
    assert [warm_bars(k) for k in ("sma:50", "vwma:20", "ema:20", "adx:14", "vwap", "vwap:rth", "cumdelta",
                                   "levels")] == [50, 20, 100, 140, 0, 0, 0, 0]


def test_older_is_the_next_chunk_strictly_before_the_first_bar_and_ends_at_the_archive_start(tmp_path):
    hub, days = deep(tmp_path)                       # 8 sessions: the chart loads the newest 5
    s = open_stream(hub, keys=("ema:3", "vwap"))
    first = s.bars[0]
    assert first.session == days[3].isoformat()
    ans = hub.older(s, first.t)
    assert [x["date"] for x in ans["sessions"]] == [d.isoformat() for d in days[:3]]
    assert [b["s"] for b in ans["bars"]] == [d.isoformat() for d in days[:3] for _ in range(3)]
    assert all(b["ms"] < first.t for b in ans["bars"]) and ans["done"] is True
    assert set(ans["studies"]) == {"ema:3", "vwap"} and len(ans["studies"]["vwap"]) == 9


def test_older_walks_back_one_chunk_at_a_time(tmp_path):
    hub, days = deep(tmp_path, n=12)
    s = open_stream(hub)
    a = hub.older(s, s.bars[0].t)
    assert [x["date"] for x in a["sessions"]] == [d.isoformat() for d in days[2:7]] and a["done"] is False
    b = hub.older(s, a["bars"][0]["ms"])
    assert [x["date"] for x in b["sessions"]] == [d.isoformat() for d in days[:2]] and b["done"] is True
    c = hub.older(s, b["bars"][0]["ms"])
    assert c["bars"] == [] and c["sessions"] == [] and c["done"] is True


def test_older_respects_history_max_and_repairs_a_session_it_cuts(tmp_path, monkeypatch):
    hub, days = deep(tmp_path)
    s = open_stream(hub, keys=("vwap",))
    monkeypatch.setattr(hub_mod, "HISTORY_MAX", 4)
    a = hub.older(s, s.bars[0].t)                    # all of days[2] + the newest bar of days[1]
    assert [b["s"] for b in a["bars"]] == [days[1].isoformat()] + [days[2].isoformat()] * 3
    assert [x["date"] for x in a["sessions"]] == [days[1].isoformat(), days[2].isoformat()] and a["done"] is False
    b = hub.older(s, a["bars"][0]["ms"])             # the rest of days[1], then the newest 2 bars of days[0]
    assert [x["s"] for x in b["bars"]] == [days[0].isoformat()] * 2 + [days[1].isoformat()] * 2
    # the join is inside days[1]: its VWAP restarts only at the session's open, so the chart's days[1] bar
    # (which came first, alone) gets the value a whole-session run gives it
    vwap = make("vwap")
    want = [vwap.push(x) for x in hub.history.bars("NQ", M1, days[1])]
    assert b["repair"]["vwap"] == want[2:3]


def test_older_studies_run_on_across_the_join(tmp_path):
    """The chunk's values are a fresh run over it; `repair` continues that run through the chart's first bars
    for as long as a study remembers (ema:3 -> 15 bars; the longest wins): together, a full reload of the
    longer range."""
    hub, days = deep(tmp_path)
    s = open_stream(hub, keys=("ema:3", "sma:2", "vwap"))
    ans = hub.older(s, s.bars[0].t)
    every = [b for d in days for b in hub.history.bars("NQ", M1, d)]     # all 8 completed sessions, oldest first
    for key in ("ema:3", "sma:2", "vwap"):
        st = make(key)
        want = [st.push(b) for b in every]
        assert ans["studies"][key] == want[:9], key
        assert ans["repair"][key] == want[9:24], key


def test_older_tick_bars_come_one_session_at_a_time(tmp_path):
    hub, days = deep(tmp_path)
    s = open_stream(hub, spec=BarSpec("tick", 5), keys=())
    assert s.bars[0].session == days[-1].isoformat()             # tick bars load one session back
    ans = hub.older(s, s.bars[0].t)
    assert [x["date"] for x in ans["sessions"]] == [days[-2].isoformat()]
    assert [b["n"] for b in ans["bars"]] == [5, 4] and ans["done"] is False


def test_older_never_returns_todays_session(tmp_path):
    hub, days = deep(tmp_path, n=3)
    s = open_stream(hub)
    ans = hub.older(s, session_ms(D, 9, 45))                     # a `before` inside today's session
    assert D.isoformat() not in {b["s"] for b in ans["bars"]}
    assert [x["date"] for x in ans["sessions"]] == [d.isoformat() for d in days] and ans["done"] is True


def test_older_leaves_the_history_memo_alone(tmp_path):
    hub, days = deep(tmp_path, n=12)
    s = open_stream(hub)
    kept = set(hub.history.memo)
    hub.older(s, s.bars[0].t)
    assert set(hub.history.memo) == kept


def test_a_chart_finds_its_stream(tmp_path):
    hub, _ = deep(tmp_path, n=2)
    s = open_stream(hub, sub=("conn", "c9"))
    assert hub.stream_of(("conn", "c9")) is s and hub.stream_of(("conn", "nope")) is None


# ---- Fix round 1: a cold subscribe must never hang (deep history / warm-up bug) ----
def test_a_cold_subscribe_bounds_the_time_it_spends_building_fresh_sessions(tmp_path, monkeypatch):
    """time:86400 asks for 250 sessions (sessions_back). None are cached here, and each build is slow
    (a big or freshly-refilled archive file): prepare() must still answer promptly, with whatever it
    managed, instead of blocking on all 250 one by one -- the rest is what scroll-back is for."""
    hub, days = deep(tmp_path, n=300)
    real_bars = History.bars

    def slow_bars(self, root, spec, d, memo=True):
        time.sleep(0.01)
        return real_bars(self, root, spec, d, memo=memo)

    monkeypatch.setattr(History, "bars", slow_bars)
    monkeypatch.setattr(hub_mod, "BUILD_BUDGET_S", 0.05)
    t0 = time.monotonic()
    s = open_stream(hub, spec=BarSpec("time", 86400), keys=())
    elapsed = time.monotonic() - t0
    assert elapsed < 2.0                    # bounded: NOT anywhere near 300 * 0.01s = 3s
    assert 0 < len(s.sessions) < 250         # answered with what it had time to build, never nothing


def test_older_also_bounds_the_time_it_spends_on_a_cold_chunk(tmp_path, monkeypatch):
    """The same slow-archive scenario during scroll-back: older() answers within bounded time (done can
    stay False -- the page just asks again for the rest) rather than blocking on the whole chunk."""
    hub, days = deep(tmp_path, n=600)               # far more than one chunk's worth still behind the first
    s = open_stream(hub, spec=BarSpec("time", 86400), keys=())
    real_bars = History.bars

    def slow_bars(self, root, spec, d, memo=True):
        time.sleep(0.01)
        return real_bars(self, root, spec, d, memo=memo)

    monkeypatch.setattr(History, "bars", slow_bars)
    monkeypatch.setattr(hub_mod, "BUILD_BUDGET_S", 0.05)
    t0 = time.monotonic()
    ans = hub.older(s, s.bars[0].t)
    elapsed = time.monotonic() - t0
    assert elapsed < 2.0
    assert ans["bars"] != [] or ans["done"] is True   # never silently nothing without a reason


# ---- Fix round 2: a budget cutoff must never leave a HOLE -- it must drop the OLDEST end, not the newest ----
def test_a_cold_subscribe_fills_newest_first_and_stays_contiguous(tmp_path, monkeypatch):
    """A mix of cached (warmed ahead of time) and uncached sessions, with a tiny budget: the sessions that
    make it into the history are a CONTIGUOUS block ending at the newest completed session. The old bug
    built oldest-first and stopped at the budget, dropping the most recent months instead of the oldest."""
    hub, days = deep(tmp_path, n=20)
    spec = BarSpec("time", 86400)
    for d in days[:10]:                      # warm the OLDEST half; the newest half stays cold (slow to build)
        hub.history.bars("NQ", spec, d)
    real_bars = History.bars

    def slow_bars(self, root, spec, d, memo=True):
        if not self.cached(root, d):
            time.sleep(0.03)
        return real_bars(self, root, spec, d, memo=memo)

    monkeypatch.setattr(History, "bars", slow_bars)
    monkeypatch.setattr(hub_mod, "BUILD_BUDGET_S", 0.05)
    s = open_stream(hub, spec=spec, keys=())
    got = [x["date"] for x in s.sessions if x["date"] != D.isoformat()]     # exclude today's own entry
    all_dates = [d.isoformat() for d in days]
    assert 0 < len(got) < len(all_dates)
    assert got == all_dates[len(all_dates) - len(got):]        # contiguous, ends at the newest session
    assert s.partial is True


def test_older_walks_newest_first_and_stays_contiguous_across_two_calls(tmp_path, monkeypatch):
    """A mix of cached (already on the chart) and uncached sessions further back, with a tiny budget: each
    older() chunk is contiguous, and a second call continues it with no gap in between."""
    hub, days = deep(tmp_path, n=300)
    spec = BarSpec("time", 86400)
    s = open_stream(hub, spec=spec, keys=())     # loads (and so caches) the newest 250 of 300, real archive
    first_loaded = dt.date.fromisoformat(s.bars[0].session)
    idx = days.index(first_loaded)               # everything before `idx` is still uncached
    real_bars = History.bars

    def slow_bars(self, root, spec, d, memo=True):
        if not self.cached(root, d):
            time.sleep(0.02)
        return real_bars(self, root, spec, d, memo=memo)

    monkeypatch.setattr(History, "bars", slow_bars)
    monkeypatch.setattr(hub_mod, "BUILD_BUDGET_S", 0.05)
    expected_tail = [d.isoformat() for d in days[:idx]]    # oldest -> newest, right up to the chart's own

    a = hub.older(s, s.bars[0].t)
    a_dates = [x["date"] for x in a["sessions"]]
    assert a_dates
    assert a_dates == expected_tail[len(expected_tail) - len(a_dates):]     # contiguous, ends just before idx
    assert a["done"] is False                    # the budget cut it short: more remain further back

    b = hub.older(s, a["bars"][0]["ms"])
    b_dates = [x["date"] for x in b["sessions"]]
    assert b_dates
    cut = len(expected_tail) - len(a_dates)
    assert b_dates == expected_tail[max(0, cut - len(b_dates)):cut]         # continues with no gap


# ---- today's bars of a whole-minute chart: resampled from the kept 1-minute bars, never a replay of the tape ----
WHOLE_MINUTES = (60, 120, 300, 900, 1800, 3600, 14400, 86400)


def rough_rows(step: float, base: int) -> list[dict]:
    """Two sessions of irregular trades (D, then the next one from 18:00): quiet stretches of 47 minutes and
    three hours inside D, the 17:00-18:00 break between the two, minutes with no trade at all, prints that
    arrive late for an earlier minute or an earlier 5-minute bar, big prints, both sides."""
    rnd = random.Random(11)
    nxt = D + dt.timedelta(days=1)
    spans = [(session_ms(D, 18, 0), session_ms(D, 21, 13)), (session_ms(D, 22, 0), session_ms(D, 23, 30)),
             (session_ms(D, 2, 30), session_ms(D, 16, 59, 59)), (session_ms(nxt, 18, 0), session_ms(nxt, 20, 7))]
    out, n = [], base
    for a, b in spans:
        t = a
        while t < b:
            n += rnd.choice((-2, -1, 0, 0, 1, 2))
            p, buy = round(n * step, 6), rnd.random() < 0.5
            late = rnd.choice((61_000, 400_000)) if rnd.random() < 0.03 and t - a > 400_000 else 0
            out.append({"ts_ms": t - late, "price": p, "size": rnd.choice((1, 1, 2, 3, 7, 10, 25)),
                        "bid": p - step if buy else p, "ask": p if buy else p + step, "id": len(out) + 1})
            t += rnd.choice((40, 900, 7_000, 31_000, 95_000))
    return out


def every_field(b):
    return (b.t, b.session, b.o, b.h, b.l, b.c, b.v, b.buy, b.sell, b.n, b.pv, b.p2v,
            list(b.fp.items()), b.big, b.closed)


def replaying(hub):
    """A second hub on the same store that never uses the kept minutes: every chart replays the tape."""
    ref = Hub(hub.history, hub.now_ms)
    ref._minutes = lambda *a: None
    return ref


def test_a_whole_minute_chart_from_the_kept_minutes_is_the_tape_s_replay_field_for_field(tmp_path):
    hub, _, _ = setup(tmp_path)
    tape = ticks_of(rough_rows(0.25, 20_000))
    hub.start_today("ES", D, tape)
    for size in WHOLE_MINUTES:
        spec = BarSpec("time", size)
        s = hub.prepare("ES", spec, []).stream
        closed, cur = build(tape, spec, 0.25, "ES")
        assert len(closed) > 1 or size >= 86400
        assert [every_field(b) for b in s.bars] == [every_field(b) for b in closed]
        assert every_field(s.builder.cur) == every_field(cur)
    assert len({b.session for b in s.bars + [s.builder.cur]}) == 2          # the tape did cross a session
    assert hub.minutes["ES"].whole and hub.minutes["ES"].upto == len(tape)


def test_the_history_message_and_all_that_follows_it_match_a_replaying_hub(tmp_path):
    """The stream goes on from the resampled developing bar exactly as from a replayed one: the same history
    message, then the same updates tick for tick and clock for clock, through the 18:00 roll."""
    hub, _, _ = setup(tmp_path)
    ref = replaying(hub)
    rs = rough_rows(0.25, 20_000)
    cut = next(i for i, r in enumerate(rs) if r["ts_ms"] >= session_ms(D, 11, 3))
    keys = ["vwap", "vwap:rth", "cumdelta", "ema:5", "levels", "profile"]
    for size in WHOLE_MINUTES:
        spec = BarSpec("time", size)
        both = []
        for h in (hub, ref):
            h.start_today("ES", D, ticks_of(rs[:cut]))
            both.append(h.attach(h.prepare("ES", spec, keys)))
            h.subscribe(both[-1], ("conn", "c1"))
        assert both[0].payload() == both[1].payload() and both[0].payload()["live"] is True
        for i in range(cut, len(rs), 37):
            for h in (hub, ref):
                h.on_clock(rs[i]["ts_ms"] - 1500)        # the pump's clock comes before the next ticks
                h.on_ticks("ES", rs[i:i + 37])
            assert hub.drain() == ref.drain()
        assert both[0].payload() == both[1].payload()
        assert hub.today_date["ES"] == D + dt.timedelta(days=1)             # it did roll
        for h in (hub, ref):
            h.unsubscribe(("conn", "c1"))


def test_a_timeframe_change_replays_only_the_ticks_since_the_last_one(tmp_path, monkeypatch):
    hub, _, _ = setup(tmp_path)
    rs = rough_rows(0.25, 20_000)
    cut = len(rs) // 2
    hub.start_today("ES", D, ticks_of(rs[:cut]))
    hub.prepare("ES", M1, [])                        # the day's first chart goes through the tape once
    seen, real = [], BarBuilder.add
    monkeypatch.setattr(BarBuilder, "add", lambda self, tk: (seen.append(tk.id), real(self, tk))[1])
    hub.prepare("ES", BarSpec("time", 300), [])
    assert seen == []
    hub.on_ticks("ES", rs[cut:cut + 7])              # no stream yet: only the tape grows
    hub.prepare("ES", BarSpec("time", 900), [])
    assert seen == [r["id"] for r in rs[cut:cut + 7]]
    del seen[:]
    hub.prepare("ES", BarSpec("time", 30), [])       # 1-minute bars cannot give it: the tape, as before
    hub.prepare("ES", BarSpec("tick", 50), [])
    assert len(seen) == 2 * (cut + 7)


def test_a_print_at_the_session_close_sends_whole_minute_charts_back_to_the_replay(tmp_path):
    """A classic root's close is inclusive: a 17:00:00.000 print is in no 1-minute bar (its bucket starts at
    the close), but the tape's replay files it in a 4-hour or daily bar, whose last bucket runs over the
    close. The kept minutes cannot give that bar, so they step aside -- and stay aside when a late print
    for 16:59 follows it."""
    hub, _, _ = setup(tmp_path)
    rs = [r for r in rough_rows(0.25, 20_000) if r["ts_ms"] < session_ms(D, 17, 0)]
    rs += rows(session_ms(D, 17, 0), [4321.0], size=3, first_id=90_000)
    rs += rows(session_ms(D, 16, 59, 59), [4321.25], size=3, first_id=90_001)
    tape = ticks_of(rs)
    hub.start_today("ES", D, tape)
    for size in WHOLE_MINUTES:
        spec = BarSpec("time", size)
        s = hub.prepare("ES", spec, []).stream
        closed, cur = build(tape, spec, 0.25, "ES")
        assert [every_field(b) for b in s.bars] == [every_field(b) for b in closed]
        assert every_field(s.builder.cur) == every_field(cur)
    assert cur.l == 4321.0 and hub.minutes["ES"].whole is False             # the daily bar holds the print


def test_on_a_decimal_tick_every_bar_sent_is_still_the_replay_s(tmp_path):
    """0.1 is no binary fraction, so price * size sums round: a resampled bar adds them minute by minute, the
    replay tick by tick. Every field the page gets is exact either way; pv and p2v (VWAP's inputs, never
    sent) agree to float rounding -- what a completed session's resampled bars have always had."""
    hub, _, _ = setup(tmp_path)
    tape = ticks_of(rough_rows(0.1, 26_500))
    hub.start_today("GC", D, tape)
    for size in WHOLE_MINUTES:
        spec = BarSpec("time", size)
        s = hub.prepare("GC", spec, []).stream
        closed, cur = build(tape, spec, 0.1, "GC")
        got, want = s.bars + [s.builder.cur], closed + [cur]
        assert [b.wire(0.1) for b in got] == [b.wire(0.1) for b in want]
        assert [b.closed for b in got] == [b.closed for b in want]
        assert [b.pv for b in got] == pytest.approx([b.pv for b in want], rel=1e-12)
        assert [b.p2v for b in got] == pytest.approx([b.p2v for b in want], rel=1e-12)


def test_a_reseed_and_the_roll_drop_the_kept_minutes(tmp_path):
    hub, _, _ = setup(tmp_path)
    rs = rough_rows(0.25, 20_000)
    tape = ticks_of([r for r in rs if r["ts_ms"] < session_ms(D, 17, 0)])
    spec = BarSpec("time", 300)
    hub.start_today("ES", D, tape[:100])
    hub.prepare("ES", spec, [])
    stale = hub.minutes["ES"]
    assert stale.upto == 100
    hub.start_today("ES", D, tape[:400])             # a refill reseeds the tape
    assert "ES" not in hub.minutes
    hub.minutes["ES"] = stale                        # a prepare() that overlapped the reseed put the old ones back
    s = hub.prepare("ES", spec, []).stream
    closed, cur = build(tape[:400], spec, 0.25, "ES")
    assert [every_field(b) for b in s.bars + [s.builder.cur]] == [every_field(b) for b in closed + [cur]]
    assert hub.minutes["ES"] is not stale and hub.minutes["ES"].upto == 400
    hub.on_ticks("ES", rows(session_ms(D + dt.timedelta(days=1), 18, 1), [300.0], first_id=99_999))
    assert "ES" not in hub.minutes                   # the 18:00 roll starts a new tape


# ---- the footprint and the big prints ride in a history / scroll-back message only when the chart asks ----
def lean(bars):
    return [{k: v for k, v in b.items() if k not in ("fp", "big")} for b in bars]


def test_a_history_without_footprint_and_big_prints_is_the_same_message_minus_those_two(tmp_path):
    hub, today, _ = setup(tmp_path)
    big = [dict(r, size=12) if i % 7 == 0 else r for i, r in enumerate(today)]
    hub.start_today("NQ", D, ticks_of(big))
    s = open_stream(hub, keys=("vwap", "cumdelta", "profile"))
    full = s.payload()
    assert full == s.payload(True, True)
    assert all("fp" in b and "big" in b for b in full["bars"]) and any(b["big"] for b in full["bars"])
    assert s.payload(fp=False, big=False) == {**full, "bars": lean(full["bars"])}
    assert all("fp" not in b and "big" in b for b in s.payload(fp=False)["bars"])
    assert all("fp" in b and "big" not in b for b in s.payload(big=False)["bars"])


def test_older_without_footprint_and_big_prints_is_the_same_chunk_minus_those_two(tmp_path):
    hub, days = deep(tmp_path)
    s = open_stream(hub, keys=("ema:3",))
    full = hub.older(s, s.bars[0].t)
    assert full["bars"] and all("fp" in b and "big" in b for b in full["bars"])
    assert hub.older(s, s.bars[0].t, fp=False, big=False) == {**full, "bars": lean(full["bars"])}
