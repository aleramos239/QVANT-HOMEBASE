"""The GLOBEX-DAY CLOCK (EDGE_SPEC family A + "PROPER RE-RUN" 5): fire times anywhere in 18:00 -> 17:00 ET, the evening as its own
segment of the NEXT trade date, the sessions eve / pre for every Template family, the ATR30 carry and the time-shuffle null.
The tester cannot run any of this, so it is proven here:
  * a straddle fired at 03:00 / 09:30 / 13:30 through the clock path = the existing (tester-matched) straddle, trade for trade;
  * no trade spans midnight or the 17:00-18:00 break; indicators restart at 18:00; a sess=globex run contains the tester's five
    sessions unchanged;
  * what an 18:00 / 00:00 decision reads (daily bars, the ATR30 carry, the anchor price) is prior data only.
Real BUILD tapes, identity / timing / counts only: no result is judged."""
import datetime as dt

import numpy as np
import pytest

import l2ref
import l2sim as S

DAYS = ["2022-03-14", "2022-03-15", "2022-03-16", "2022-06-10", "2022-06-13", "2022-11-25", "2022-11-28", "2023-03-13",
        "2023-03-14", "2023-07-03"]             # a Monday (Sunday evening), roll days, two half days, a DST week: all BUILD
EXITS = [{"stop_mode": "atr", "stop_val": 1.5, "tgt_r": 2.0}, {"stop_mode": "pts", "stop_val": 20.0, "tgt_r": 1.0},
         {"stop_mode": "pct", "stop_val": 0.10, "tgt_r": 0.0}]


def et_of(ms):
    return dt.datetime.fromtimestamp(ms / 1000, S.ET)


def test_clock_helpers_place_every_listed_time():
    assert S.LISTED_TIMES == ("18:00", "20:00", "00:00", "02:00", "03:00", "08:30", "09:30", "11:05", "13:30")
    assert [S.clock_sec(t) for t in ("18:00", "23:59", "00:00", "08:30", "17:00")] == [-21600, -60, 0, 30600, 61200]
    for bad in ("17:30", "17:00:01", "24:00"):
        with pytest.raises(ValueError):
            S.clock_sec(bad)
    assert [S.clock_session(t) for t in S.LISTED_TIMES] == ["eve", "eve", "asia", "asia", "london", "pre", "nyam", "mid", "pm"]
    # 'flat at the next listed time or the session end, whichever is first'
    assert [S.clock_flat(t) for t in S.LISTED_TIMES] == ["20:00:00", "23:59:00", "02:00:00", "03:00:00", "08:25:00", "09:30:00",
                                                         "11:00:00", "13:30:00", "15:58:00"]
    assert S.SESS["eve"] == (-21600, -60) and S.SESS["pre"] == (30300, 34200) and S.ORDER == ("asia", "london", "nyam", "mid", "pm")
    assert S.ORDER7 == ("eve", "asia", "london", "pre", "nyam", "mid", "pm") and S._hms(-21600) == "18:00:00" and S._hms(-60) == "23:59:00"
    d = dt.date(2023, 3, 13)                                     # a Monday right after the DST change: its evening is SUNDAY 18:00 EDT
    t0, t1 = S.segment_ns(d, S.EVE_WINDOW, "eve")
    assert et_of(t0 // 10**6).strftime("%Y-%m-%d %a %H:%M") == "2023-03-12 Sun 18:00" and t1 == S.et_ns(d, "00:00")
    assert S.segment_ns(d, ("00:00", "16:10")) == (S.et_ns(d, "00:00"), S.et_ns(d, "16:10"))
    with pytest.raises(ValueError):
        S.segment_ns(d, ("09:30", "16:00"), "eve")


@pytest.mark.parametrize("at,flat,sess", [("03:00", "08:25", "london"), ("09:30", "11:00", "nyam"), ("13:30", "15:58", "pm")])
def test_a_straddle_through_the_clock_path_equals_the_existing_straddle(at, flat, sess):
    specs = []
    for x in EXITS:
        specs.append((l2ref.Straddle, {"tf": "30", "sess": sess, "off_atr": 0.5, **x}))
        specs.append((l2ref.StraddleT, {"at": at, "flat": flat, "cancel_min": 0, "off_mode": "atr", "off_val": 0.5, "max_tr": 3, **x}))
    res = S.run_many(specs, days=DAYS, workers=1)
    for k in range(len(EXITS)):
        a, b = res[2 * k], res[2 * k + 1]
        assert a["trades"] == b["trades"] and len(a["trades"]) >= 8 and a["skipped"] == b["skipped"]
        assert b["skipped_by_error"] == 0 and b["meta"]["segments"] == ["day"] and b["both_sides_sessions"] == a["both_sides_sessions"]
    assert S.clock_flat(at) == flat + ":00"                      # the spec's own flat rule gives these session ends
    spec = S.run(l2ref.StraddleT, {"at": at, **EXITS[0]}, days=DAYS, workers=1)["trades"]          # cancel after 60 min (EDGE_SPEC)
    assert 0 < len(spec) <= len(res[1]["trades"]) and all((t["entry_ms"] - S.et_ns(dt.date.fromisoformat(t["date"]), at) // 10**6)
                                                           < 3600_000 for t in spec)


def test_globex_run_keeps_the_five_sessions_and_adds_eve_and_pre():
    five = S.run(l2ref.Random, {"tf": "5", "sess": "all", "p_entry": 0.3}, days=DAYS, workers=1)
    glob = S.run(l2ref.Random, {"tf": "5", "sess": "globex", "p_entry": 0.3}, days=DAYS, workers=1)
    assert five["meta"]["segments"] == ["day"] and glob["meta"]["segments"] == ["eve", "day"] and glob["skipped_by_error"] == 0
    by = {}
    for t in glob["trades"]:
        by.setdefault(S.session_of(t["entry_ms"]), []).append(t)
    assert set(by) == set(S.ORDER7) and [t for t in glob["trades"] if S.session_of(t["entry_ms"]) in S.ORDER] == five["trades"]
    for s in ("eve", "pre"):                                    # a single-session run = that part of the globex run
        one = S.run(l2ref.Random, {"tf": "5", "sess": s, "p_entry": 0.3}, days=DAYS, workers=1)
        assert one["trades"] == by[s] and len(one["trades"]) >= 10
        assert one["meta"]["segments"] == (["eve"] if s == "eve" else ["day"])
    for t in by["eve"]:                                         # the evening BEFORE the trade date, carried on the trade date
        d = dt.date.fromisoformat(t["date"])
        a, x = et_of(t["entry_ms"]), et_of(t["exit_ms"])
        assert a.date() == x.date() == d - dt.timedelta(days=1) and "18:00" <= a.strftime("%H:%M") < "23:54"
        assert x.strftime("%H:%M:%S") < "23:59:59" and (t["exit_reason"] != "time" or x.strftime("%H:%M") == "23:59")
    for t in by["pre"]:
        a, x = et_of(t["entry_ms"]), et_of(t["exit_ms"])
        assert "08:25" <= a.strftime("%H:%M") < "09:25" and x.strftime("%H:%M:%S") <= "09:30:59" and a.date().isoformat() == t["date"]
    mon = [t for t in by["eve"] if t["date"] == "2023-03-13"]
    assert mon and all(et_of(t["entry_ms"]).strftime("%a") == "Sun" for t in mon)


def test_no_trade_spans_midnight_or_the_17_to_18_break():
    class Wide(l2ref.Random):
        """Sessions up to the very end of each segment: 18:00 -> 23:59 and 00:00 -> 17:00."""
        def fam_sessions(self):
            return {"whole": (0, 61200)}

        def fam_filter(self, ids):
            return ["eve", "whole"]
    st = Wide({"tf": "15", "p_entry": 0.5, "max_tr": 20, "stop_val": 50.0, "tgt_r": 0.0, "exit_bars": 6})
    assert st.eve_window == S.EVE_WINDOW and st.session_window == ("00:00", "17:00")
    daily = S.load_daily("NQ")
    n = 0
    for iso in DAYS:
        d = dt.date.fromisoformat(iso)
        tape = S.load_tape(d)
        prior = [r for r in daily if r["date"] < iso]
        trades = []
        for seg, w in (("eve", st.eve_window), ("day", S.effective_session_window(d, st.session_window, "NQ"))):
            trades += S.run_session(st, tape, daily=prior, window=w, segment=seg, on_error="raise").trades
        lo, mid, hi = S.et_ns(d - dt.timedelta(days=1), "18:00"), S.et_ns(d, "00:00"), S.et_ns(d, "17:00")
        for t in trades:
            a, x = t["entry_ms"] * 10**6, t["exit_ms"] * 10**6
            assert lo <= a <= x < hi and (a < mid) == (x < mid)       # inside its own Globex day, never across 00:00
            n += 1
        assert any(t["exit_ms"] * 10**6 >= S.et_ns(d, w := S.effective_session_window(d, ("00:00", "16:30"), "NQ")[1]) - 31 * 60 * S.NS
                   for t in trades), w                            # the day really ran to its end
    assert n > 100
    with pytest.raises(ValueError, match="span 00:00"):

        class Across(l2ref.Random):
            def fam_sessions(self):
                return {"x": (-3600, 3600)}

            def fam_filter(self, ids):
                return ["x"]
        Across({"tf": "5"})


class Probe(S.Template):
    """Records what a decision could see: at every tf close the bar count, the ATR and the newest daily bar."""
    seen: list = []

    def fam_update(self, ctx):
        Probe.seen.append((ctx.segment, ctx.date.isoformat(), ctx.now_ns, self.nb, self.atr, ctx.daily[-1]["date"] if ctx.daily else None,
                           self.pdc, ctx.atr_carry))


def test_indicators_restart_at_1800_and_the_evening_sees_only_prior_daily_bars():
    d = dt.date(2023, 3, 14)
    daily = S.with_eve_atr(S.load_daily("NQ"), "NQ")
    prior = [r for r in daily if r["date"] < d.isoformat()]
    tape = S.load_tape(d)
    Probe.seen = []
    st = Probe({"tf": "30", "sess": "globex"})
    S.run_session(st, tape, daily=prior, window=st.eve_window, segment="eve", carry=prior[-1]["atr30e"], on_error="raise")
    eve = list(Probe.seen)
    assert [x[3] for x in eve] == list(range(1, len(eve) + 1)) and len(eve) == 11       # 18:30 .. 23:30: bars count from 18:00
    assert et_of(eve[0][2] // 10**6).strftime("%Y-%m-%d %H:%M") == "2023-03-13 18:30"
    assert all(x[5] == "2023-03-13" and x[1] == "2023-03-14" for x in eve)             # newest daily bar = the previous trade date
    assert prior[-1]["date"] == "2023-03-13" and eve[0][6] == prior[-1]["c"]           # prior close = that bar's close
    # the previous trade date's whole-day bar ended at 16:59:59 ET, before this evening began
    prev = S.load_tape("2023-03-13")
    assert prev.ts[-1] < S.et_ns(dt.date(2023, 3, 13), "18:00") <= tape.ts[0] and prior[-1]["c"] == float(prev.px[-1])
    assert S.eve_atr(tape) == eve[-1][4]                         # the cached "evening close ATR30" IS the engine's value
    Probe.seen = []
    S.run_session(st, tape, daily=prior, on_error="raise")
    day = list(Probe.seen)
    assert day[0][3] == 1 and et_of(day[0][2] // 10**6).strftime("%H:%M") == "00:30"   # ... and restart again at 00:00 (the tester's day)


def test_the_atr_carry_is_the_last_ended_evenings_closing_atr30_prior_data_only():
    d = dt.date(2023, 3, 15)
    tape = S.load_tape(d)
    cache = S.load_eve_atr("NQ")
    assert cache[d.isoformat()] == S.eve_atr(tape) and set(cache) == {x.isoformat() for x in S.sessions(*S.IN_SAMPLE)}
    # computed from the prints before 00:00 ET of the trade date only: a tape cut at midnight gives the same number
    k = int(np.searchsorted(tape.ts, S.et_ns(d, "00:00")))
    cut = S.Tape("NQ", d, tape.contract, tape.ts[:k], tape.px[:k], tape.size[:k])
    assert S.eve_atr(cut) == S.eve_atr(tape) and S.eve_atr(cut) > 0
    daily = S.with_eve_atr(S.load_daily("NQ"), "NQ")
    assert [r for r in daily if r["date"] == d.isoformat()][0]["atr30e"] == cache[d.isoformat()]

    class Carry(l2ref.StraddleT):
        seen: dict = {}

        def fam_time(self, ctx, sec):
            if sec == self.S["t"][0]:
                Carry.seen[(ctx.date.isoformat(), self.p["at"])] = (self.atr, self.nb, ctx.atr_carry, ctx.last_price, ctx.prev_price, self.pdc)
            super().fam_time(ctx, sec)
    res = S.run_many([(Carry, {"at": t}) for t in ("18:00", "00:00", "20:00", "02:00")], days=[d.isoformat()], workers=1)
    assert all(r["skipped_by_error"] == 0 for r in res)
    prev = "2023-03-14"
    atr18, nb18, c18, lp18, pp18, pdc18 = Carry.seen[(d.isoformat(), "18:00")]
    assert nb18 == 0 and atr18 == c18 == cache[prev]             # 18:00: the PREVIOUS trade date's evening (ended 24 h ago)
    assert lp18 is None and pp18 is None and pdc18 == float(S.load_tape(prev).px[-1])     # no print of this Globex day yet: the 17:00 close
    atr00, nb00, c00, lp00, pp00, _ = Carry.seen[(d.isoformat(), "00:00")]
    assert nb00 == 0 and atr00 == c00 == cache[d.isoformat()]    # 00:00: the evening that has just ended
    assert lp00 is None and pp00 == float(tape.px[k - 1]) and tape.ts[k - 1] < S.et_ns(d, "00:00")    # the last evening print
    atr20, nb20, c20 = Carry.seen[(d.isoformat(), "20:00")][:3]
    assert nb20 == 4 and atr20 != c20                            # warm: the running ATR of the four bars since 18:00
    assert Carry.seen[(d.isoformat(), "02:00")][1] == 4


def test_the_1800_straddle_anchors_on_the_prior_close_and_skips_roll_days():
    days = ["2023-03-10", "2023-03-13", "2023-03-14", "2023-03-15", "2023-03-16"]        # 2023-03-13 = NQ roll day
    assert "2023-03-13" in S.default_rolls("NQ")
    r = S.run(l2ref.StraddleT, {"at": "18:00", "off_mode": "pts", "off_val": 10.0, "stop_mode": "pts", "stop_val": 20.0, "tgt_r": 1.0},
              days=days, workers=1)
    assert r["skipped_by_error"] == 0 and r["meta"]["segments"] == ["eve"] and len(r["trades"]) >= 2
    daily = {x["date"]: x for x in S.load_daily("NQ")}
    order = sorted(daily)
    for t in r["trades"]:
        assert t["date"] != "2023-03-13"                         # the prior close is another contract: no anchor, no trade
        pc = daily[order[order.index(t["date"]) - 1]]["c"]
        assert abs(t["order_price"] - pc) == 10.0 and S.session_of(t["entry_ms"]) == "eve" and t["oco"] and t["both_sides"]
        a = et_of(t["entry_ms"])
        assert "18:00:00" <= a.strftime("%H:%M:%S") < "19:00:00" and a.date() == dt.date.fromisoformat(t["date"]) - dt.timedelta(days=1)
        assert et_of(t["exit_ms"]).strftime("%H:%M:%S") < "20:00:59"                    # flat at the next listed time (20:00)


def test_time_shuffle_null_fires_the_same_straddle_at_a_seeded_random_minute():
    base = {"at": "09:30", "off_mode": "pts", "off_val": 10.0}
    st1, st2 = l2ref.StraddleT({**base, "shift_seed": 1}), l2ref.StraddleT({**base, "shift_seed": 2})
    assert st1.shifts() == list(range(-90, 91)) and l2ref.StraddleT(base).shift_of(dt.date(2023, 3, 14)) == 0
    assert l2ref.StraddleT({"at": "18:00", "shift_seed": 1}).shifts() == list(range(0, 91))        # never before the 18:00 open
    assert l2ref.StraddleT({"at": "20:00", "shift_seed": 1}).shifts() == list(range(-90, 1))       # flat 23:59 stays in the evening
    assert l2ref.StraddleT({"at": "00:00", "shift_seed": 1}).shifts() == list(range(0, 91))
    assert l2ref.StraddleT({"at": "13:30", "shift_seed": 1}).shifts() == list(range(-90, 1))       # flat 15:58 is the day's last end
    days = [d.isoformat() for d in S.sessions("2022-03-01", "2022-05-31")]
    s1 = [st1.shift_of(d) for d in days]
    assert s1 == [l2ref.StraddleT({**base, "shift_seed": 1, "off_val": 20.0, "stop_val": 3.0}).shift_of(d) for d in days]     # cell-independent
    assert s1 != [st2.shift_of(d) for d in days] and min(s1) >= -90 and max(s1) <= 90 and len(set(s1)) > 30
    assert abs(float(np.mean(s1))) < 20                                                              # uniform around the listed time
    sub = days[:12]
    real = S.run(l2ref.StraddleT, base, days=sub, workers=1)
    null = S.run(l2ref.StraddleT, {**base, "shift_seed": 1}, days=sub, workers=1)
    again = S.run(l2ref.StraddleT, {**base, "shift_seed": 1}, days=sub, workers=2)
    assert null["trades"] == again["trades"] and null["skipped_by_error"] == 0 and len(null["trades"]) >= 8
    assert S.run(l2ref.StraddleT, {**base, "shift_seed": 0}, days=sub, workers=1)["trades"] == real["trades"]
    for t in null["trades"]:                                     # armed at 09:30 + the day's shift, cancelled 60 min later, flat 90 min later
        d = dt.date.fromisoformat(t["date"])
        fire = S.et_ns(d, "09:30") + st1.shift_of(d) * S.MIN_NS
        assert fire <= t["entry_ms"] * 10**6 < fire + 60 * S.MIN_NS and t["exit_ms"] * 10**6 <= fire + 91 * S.MIN_NS
    assert [t["entry_ms"] for t in null["trades"]] != [t["entry_ms"] for t in real["trades"]]
