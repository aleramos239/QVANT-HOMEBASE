"""The library's exit convention hold_to='day' (EDGE_SPEC "ORCHESTRATOR DECISIONS 2026-10-03" 1, "flat by 4pm"): a trade runs
to its stop / target or is flattened at 15:58 ET of its TRADE date (13:13 on an equity half day), never at the session end;
entries stay inside the session window; one position at a time per session instance; an evening entry is held through
midnight; nothing is open across 17:00. hold_to='session' (the class default) is the tester's rule, untouched.
Synthetic tapes (no market data) except the last test, which asserts COUNTS only. Nothing here looks at a result."""
import datetime as dt

import numpy as np
import pytest

import l2ref
import l2sim as S
import library as LB
import run_menus as RM

D = dt.date(2023, 3, 14)                      # a BUILD weekday (EDT)
HALF = dt.date(2022, 11, 25)                  # the day after Thanksgiving: a CME equity half day (13:15 ET close)


def mk(d, start, end, px=15000.0, root="NQ", path=None, eve=False):
    """A print every 10 s from `start` to `end` ET of d (eve=True: from `start` of the evening BEFORE d), a one-tick wiggle
    around `px`; path = [(HH:MM on d, level)]: from that minute on the price sits at that level."""
    t0 = S.et_ns(d - dt.timedelta(days=1), start) if eve else S.et_ns(d, start)
    ts = np.arange(t0, S.et_ns(d, end), 10 * S.NS, dtype=np.int64)
    base = np.full(len(ts), float(px))
    for hhmm, lvl in (path or []):
        base[ts >= S.et_ns(d, hhmm)] = float(lvl)
    tick = S.SPECS[root][1]
    return S.Tape(root, d, "X", ts, base + tick * (np.arange(len(ts)) % 3), np.ones(len(ts), np.int64))


class Always(S.Template):
    """Enters `go` at market at every tf-bar close the Template allows."""
    DEFAULTS = {"go": "long"}
    SCHEMA = {"go": ("choice", ("long", "short"))}

    def fam_signal(self, ctx):
        self._mkt(ctx, self.p["go"])


class FarStop(S.Template):
    """Rests ONE far stop entry at the session start + 1 minute (never filled inside a quiet session)."""
    DEFAULTS = {"far": 40.0}
    SCHEMA = {"far": ("float", 1, 1000)}

    def fam_times(self):
        return [S._hms(self.S[s][0] + 60) for s in self.sessions()]

    def fam_time(self, ctx, sec):
        s = self.sid
        if s is not None and sec == self.S[s][0] + 60 and self.can_enter(ctx):
            self._arm(ctx, [("long", ctx.last_price + self.p["far"], None, None)])


BASE = {"tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "max_tr": 20}
DAY = {**BASE, "hold_to": "day"}


def hm(ms):
    return dt.datetime.fromtimestamp(ms / 1000, S.ET).strftime("%H:%M")


def run(cls, params, tape, **kw):
    st = cls(params)
    if st.session_window is None or kw.get("segment") == "eve":
        kw = {"window": st.eve_window, "segment": "eve", **kw}
    return S.run_session(st, tape, daily=[], on_error="raise", **kw).trades


# ---- the input ---------------------------------------------------------------------------------------------------------------

def test_hold_to_defaults_to_the_testers_rule_and_day_takes_one_session_per_instance():
    assert S.Template.defaults()["hold_to"] == "session" and S.LIBRARY_HOLD == "day" and RM.HOLD == "day"
    assert Always(BASE).hold_day is False and Always(DAY).hold_day is True
    assert "15:58:00" not in Always({**BASE, "sess": "asia"}).times()                  # the old convention gets no new event
    assert {"13:08:00", "13:13:00", "15:53:00", "15:58:00"} <= set(Always({**DAY, "sess": "asia"}).times())
    with pytest.raises(ValueError, match="ONE session per instance"):
        Always({**DAY, "sess": "all"})
    with pytest.raises(ValueError, match="ONE session per instance"):
        Always({**DAY, "sess": "globex"})
    with pytest.raises(ValueError, match="hold_to"):
        Always({**BASE, "hold_to": "week"})
    assert l2ref.StraddleT({"at": "09:30", "hold_to": "day"}).hold_day                 # a clock window is one session


def test_day_flat_is_1558_and_1313_on_an_equity_half_day_only():
    assert S.day_flat(D) == "15:58" and S.day_flat(HALF, "NQ") == S.day_flat(HALF, "ES") == "13:13"
    assert S.day_flat(HALF, "GC") == "15:58"                                           # GC has no equity half day (as the window clamp)
    assert all(S.day_flat(d, "NQ") == "13:13" for d in S.EARLY_CLOSES)


# ---- the flatten time ---------------------------------------------------------------------------------------------------------

def test_a_session_trade_is_held_past_its_session_end_to_1558_and_no_second_entry_is_taken_while_it_is_open():
    tape = mk(D, "09:00", "16:10")
    old, new = run(Always, BASE, tape), run(Always, DAY, tape)
    assert [(hm(t["entry_ms"]), hm(t["exit_ms"]), t["exit_reason"]) for t in old] == [("09:31", "11:00", "time")]
    assert [(hm(t["entry_ms"]), hm(t["exit_ms"]), t["exit_reason"]) for t in new] == [("09:31", "15:58", "time")]
    # the signal fires at EVERY bar close and max_tr is 20: one trade, because the first one is still open (and no entry
    # is ever taken after the session end 11:00)
    assert new[0]["entry_ms"] == old[0]["entry_ms"] and new[0]["entry_price"] == old[0]["entry_price"]
    assert new[0]["exit_ms"] * 1_000_000 == S.et_ns(D, "15:58") and new[0]["date"] == D.isoformat()


@pytest.mark.parametrize("sess,first", [("asia", "00:03"), ("london", "03:01"), ("pre", "08:26"), ("nyam", "09:31"),
                                        ("mid", "11:01"), ("pm", "13:31")])
def test_every_day_session_holds_to_1558_of_the_trade_date(sess, first):
    tr = run(Always, {**DAY, "sess": sess}, mk(D, "00:00", "16:10"))
    assert [(hm(t["entry_ms"]), hm(t["exit_ms"]), t["exit_reason"]) for t in tr] == [(first, "15:58", "time")]
    assert S.session_of(tr[0]["entry_ms"]) == sess


def test_half_day_flatten_is_1313_for_equity_roots_and_no_entry_is_taken_in_its_last_five_minutes():
    tape = mk(HALF, "09:00", "13:15")
    win = S.effective_session_window(HALF, S.Template.session_window, "NQ")
    assert win == ("00:00", "13:15")
    tr = run(Always, DAY, tape, window=win)
    assert [(hm(t["entry_ms"]), hm(t["exit_ms"]), t["exit_reason"]) for t in tr] == [("09:31", "13:13", "time")]
    # mid (11:00-13:30) on the half day: after a stop-out at 13:00 the Template re-enters (13:01); after one at 13:09 it does
    # not -- no entry in the last five minutes before the day's flatten time (the session's own line would be 13:25)
    mid = {**DAY, "sess": "mid", "stop_val": 50.0}
    a = run(Always, mid, mk(HALF, "09:00", "13:15", path=[("13:00", 14900.0)]), window=win)
    assert [(hm(t["entry_ms"]), hm(t["exit_ms"]), t["exit_reason"]) for t in a] == [("11:01", "13:00", "sl"), ("13:01", "13:13", "time")]
    b = run(Always, mid, mk(HALF, "09:00", "13:15", path=[("13:09", 14900.0)]), window=win)
    assert [(hm(t["entry_ms"]), hm(t["exit_ms"]), t["exit_reason"]) for t in b] == [("11:01", "13:09", "sl")]
    assert run(Always, {**DAY, "sess": "pm"}, tape, window=win) == []                  # pm starts after the flatten time
    # GC keeps its full day on an equity half day (no clamp): 15:58
    g = run(Always, {**DAY, "stop_val": 50.0}, mk(HALF, "09:00", "16:10", px=1800.0, root="GC"),
            window=S.effective_session_window(HALF, S.Template.session_window, "GC"))
    assert [(hm(t["entry_ms"]), hm(t["exit_ms"])) for t in g] == [("09:31", "15:58")]


@pytest.mark.parametrize("d,utc_hour", [(dt.date(2022, 3, 14), 19), (dt.date(2022, 11, 7), 20), (dt.date(2023, 1, 10), 20),
                                        (dt.date(2023, 3, 13), 19), (dt.date(2023, 11, 6), 20), (dt.date(2023, 7, 12), 19)])
def test_the_flatten_time_is_1558_ET_wall_clock_on_both_sides_of_a_DST_change(d, utc_hour):
    """The first session after the clocks change (spring 2022-03-14 / 2023-03-13, autumn 2022-11-07 / 2023-11-06), a winter
    and a summer day: always 15:58 ET = 19:58 UTC in summer time, 20:58 UTC in winter time."""
    tr = run(Always, DAY, mk(d, "09:00", "16:10"))
    assert len(tr) == 1 and hm(tr[0]["exit_ms"]) == "15:58" and tr[0]["exit_ms"] * 1_000_000 == S.et_ns(d, "15:58")
    u = dt.datetime.fromtimestamp(tr[0]["exit_ms"] / 1000, dt.timezone.utc)
    assert (u.hour, u.minute) == (utc_hour, 58)
    # an evening entry of that trade date (the Sunday evening after the change) is held to the same instant
    ev = run(Always, {**DAY, "sess": "eve"}, mk(d, "18:00", "16:10", eve=True))
    assert len(ev) == 1 and ev[0]["exit_ms"] == tr[0]["exit_ms"] and hm(ev[0]["entry_ms"]) == "18:03"


# ---- the evening ---------------------------------------------------------------------------------------------------------------

def test_an_evening_entry_is_held_through_midnight_to_1558_of_its_trade_date_and_never_across_1700():
    st = Always({**DAY, "sess": "eve"})
    assert st.eve_window == ("18:00", "16:10") and st.session_window is None and S.eve_runs_on(st.eve_window)
    assert Always({**BASE, "sess": "eve"}).eve_window == S.EVE_WINDOW and not S.eve_runs_on(S.EVE_WINDOW)
    assert S.segment_ns(D, st.eve_window, "eve") == (S.et_ns(D - dt.timedelta(days=1), "18:00"), S.et_ns(D, "16:10"))
    assert S.segment_ns(D, S.EVE_WINDOW, "eve") == (S.et_ns(D - dt.timedelta(days=1), "18:00"), S.et_ns(D, "00:00"))
    with pytest.raises(ValueError):
        S.segment_ns(D, ("18:00", "17:30"), "eve")                                     # inside the 17:00-18:00 break
    tape = mk(D, "18:00", "16:10", eve=True)
    old = run(Always, {**BASE, "sess": "eve"}, tape)
    new = run(Always, {**DAY, "sess": "eve"}, tape)
    assert [(hm(t["entry_ms"]), hm(t["exit_ms"]), t["exit_reason"]) for t in old] == [("18:03", "23:59", "time")]
    assert [(hm(t["entry_ms"]), hm(t["exit_ms"]), t["exit_reason"]) for t in new] == [("18:03", "15:58", "time")]
    t = new[0]
    assert t["date"] == D.isoformat() and t["entry_ms"] == old[0]["entry_ms"]          # the trade carries the TRADE date
    assert t["entry_ms"] * 1_000_000 < S.et_ns(D, "00:00") < t["exit_ms"] * 1_000_000 < S.et_ns(D, "17:00")
    assert S.session_of(t["entry_ms"]) == "eve" and t["seconds"] > 21 * 3600
    # an equity half day: the held evening ends at 13:13 (the runner clamps the window to 13:15)
    h = run(Always, {**DAY, "sess": "eve"}, mk(HALF, "18:00", "13:15", eve=True), window=("18:00", "13:15"))
    assert [(hm(x["entry_ms"]), hm(x["exit_ms"])) for x in h] == [("18:03", "13:13")]


def test_the_runner_skips_a_held_evening_whose_day_has_a_coverage_hole(monkeypatch):
    """hold_to='day': an evening trade needs the day's prints too -- a trade date with an empty clock hour before the day
    window's end is skipped for the evening instance (the day's own coverage rule), not flattened at a stale price."""
    full = mk(D, "18:00", "16:10", eve=True)
    keep = (full.ts < S.et_ns(D, "10:00")) | (full.ts >= S.et_ns(D, "12:00"))          # no print 10:00-12:00
    holed = S.Tape("NQ", D, "X", full.ts[keep], full.px[keep], full.size[keep])
    tapes = {"ok": full, "hole": holed}
    out = {}
    for name, tp in tapes.items():
        monkeypatch.setattr(S, "load_tape", lambda d, root="NQ", allow_holdout=False, allow_exam=False, tp=tp: tp)
        job = lambda p: S._run_days(([(Always, p)], "NQ", [D.isoformat()], S.Costs(), 1, False, [], frozenset(), None, False))[0]  # noqa: E731
        out[name] = (job({**DAY, "sess": "eve"}), job({**BASE, "sess": "eve"}))
    assert len(out["ok"][0]["trades"]) == 1 and out["ok"][0]["skipped"] == []
    assert out["hole"][0]["trades"] == [] and "10:00" in out["hole"][0]["skipped"][0]["reason"]
    assert len(out["hole"][1]["trades"]) == 1                                         # the old convention needs the evening only


# ---- entries stay inside the session; exits keep working after it ------------------------------------------------------------------

def test_unfilled_entries_are_cancelled_with_the_session_and_nothing_enters_after_it():
    """A far resting entry of the nyam session (never reached before 11:00) must NOT fill when the price runs through its
    level at 12:00; with the level reached at 10:00 it fills and is held to 15:58."""
    late = mk(D, "09:00", "16:10", path=[("12:00", 15100.0)])
    assert run(FarStop, {**DAY, "far": 40.0}, late) == [] and run(FarStop, {**BASE, "far": 40.0}, late) == []
    early = mk(D, "09:00", "16:10", path=[("10:00", 15100.0)])
    tr = run(FarStop, {**DAY, "far": 40.0}, early)
    assert [(hm(t["entry_ms"]), hm(t["exit_ms"]), t["exit_reason"]) for t in tr] == [("10:00", "15:58", "time")]
    assert [hm(t["exit_ms"]) for t in run(FarStop, {**BASE, "far": 40.0}, early)] == ["11:00"]


def test_stop_target_and_bar_exits_act_after_the_session_end():
    dip = mk(D, "09:00", "16:10", path=[("14:00", 14900.0)])                           # -100 points at 14:00, long after nyam
    sl = run(Always, {**DAY, "stop_val": 50.0}, dip)
    assert [(hm(t["entry_ms"]), hm(t["exit_ms"]), t["exit_reason"]) for t in sl] == [("09:31", "14:00", "sl")]
    assert [t["exit_reason"] for t in run(Always, {**BASE, "stop_val": 50.0}, dip)] == ["time"]      # the old rule left at 11:00
    up = mk(D, "09:00", "16:10", path=[("14:00", 15100.0)])
    tp = run(Always, {**DAY, "stop_val": 50.0, "tgt_r": 1.0}, up)
    assert [(hm(t["exit_ms"]), t["exit_reason"]) for t in tp] == [("14:00", "tp")]
    bars = run(Always, {**DAY, "exit_bars": 200}, mk(D, "09:00", "16:10"))             # 200 one-minute closes after the fill
    assert [(hm(t["entry_ms"]), hm(t["exit_ms"]), t["exit_reason"]) for t in bars] == [("09:31", "12:51", "bars")]


def test_a_new_entry_is_possible_only_after_the_first_trade_closed_and_only_inside_the_session():
    # stopped out at 09:45 -> the next close re-enters (inside nyam); that second trade is then held to 15:58
    tape = mk(D, "09:00", "16:10", path=[("09:45", 14900.0)])
    tr = run(Always, {**DAY, "stop_val": 50.0}, tape)
    assert [(hm(t["entry_ms"]), hm(t["exit_ms"]), t["exit_reason"]) for t in tr] == [("09:31", "09:45", "sl"), ("09:46", "15:58", "time")]
    assert all(b["entry_ms"] >= a["exit_ms"] for a, b in zip(tr, tr[1:]))              # never two positions of one instance
    # stopped out at 12:00, after the session: no re-entry
    tr = run(Always, {**DAY, "stop_val": 50.0}, mk(D, "09:00", "16:10", path=[("12:00", 14900.0)]))
    assert [(hm(t["entry_ms"]), hm(t["exit_ms"]), t["exit_reason"]) for t in tr] == [("09:31", "12:00", "sl")]


def test_straddle_t_cancels_its_unfilled_leg_after_60_minutes_and_holds_the_filled_side_to_1558():
    p = {"at": "09:30", "off_mode": "pts", "off_val": 20.0, "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0}
    assert l2ref.StraddleT(p).p["cancel_min"] == 60
    hit = mk(D, "07:00", "16:10", path=[("10:00", 15050.0)])                           # the long leg fills at 10:00
    old, new = run(l2ref.StraddleT, p, hit), run(l2ref.StraddleT, {**p, "hold_to": "day"}, hit)
    assert [(t["side"], hm(t["entry_ms"]), hm(t["exit_ms"])) for t in old] == [("long", "10:00", "11:00")]
    assert [(t["side"], hm(t["entry_ms"]), hm(t["exit_ms"]), t["exit_reason"]) for t in new] == [("long", "10:00", "15:58", "time")]
    assert new[0]["oco"] is True and new[0]["entry_price"] == old[0]["entry_price"]
    miss = mk(D, "07:00", "16:10", path=[("10:31", 15050.0)])                          # 61 minutes after the fire: cancelled
    assert run(l2ref.StraddleT, {**p, "hold_to": "day"}, miss) == []
    edge = mk(D, "07:00", "16:10", path=[("10:29", 15050.0)])                          # 59 minutes: still working
    assert [hm(t["entry_ms"]) for t in run(l2ref.StraddleT, {**p, "hold_to": "day"}, edge)] == ["10:29"]
    # an 18:00 / 20:00 fire is a HELD evening segment; the time-shuffle null keeps the convention
    ev = l2ref.StraddleT({**p, "at": "20:00", "hold_to": "day"})
    assert ev.eve_window == ("18:00", "16:10") and ev.session_window is None
    tr = run(l2ref.StraddleT, {**p, "at": "20:00", "hold_to": "day"}, mk(D, "18:00", "16:10", eve=True, path=[("02:00", 15050.0)]))
    assert tr == []                                                                    # the level is reached after the 60 minutes
    tape = mk(D, "18:00", "16:10", eve=True)
    tape = S.Tape("NQ", D, "X", tape.ts, np.where(tape.ts >= S.et_ns(D - dt.timedelta(days=1), "20:30"), tape.px + 50.0, tape.px), tape.size)
    tr = S.run_session(ev, tape, daily=[], window=ev.eve_window, segment="eve", on_error="raise", carry=10.0).trades
    assert [(t["side"], hm(t["entry_ms"]), hm(t["exit_ms"])) for t in tr] == [("long", "20:30", "15:58")] and tr[0]["date"] == D.isoformat()


def test_the_early_stop_changes_no_trade(monkeypatch):
    """EARLY_STOP ends a day's replay once the instance's session is over and it is flat: same trades with it off."""
    tapes = [mk(D, "00:00", "16:10"), mk(D, "09:00", "16:10", path=[("09:45", 14900.0), ("12:00", 14800.0)]),
             mk(D, "09:00", "16:10", path=[("10:15", 15100.0)])]
    params = [{**DAY, "sess": s, "stop_val": v, "tgt_r": r} for s in ("asia", "nyam", "mid", "pm") for v, r in ((50.0, 0.0), (20.0, 2.0))]
    st = Always({**DAY, "stop_val": 20.0, "tgt_r": 1.0, "max_tr": 1})
    assert st.day_done.__func__ is S.Template.day_done and Always(BASE).hold_day is False
    on = [run(Always, p, t) for t in tapes for p in params]
    monkeypatch.setattr(S, "EARLY_STOP", False)
    off = [run(Always, p, t) for t in tapes for p in params]
    assert on == off and sum(len(x) for x in on) > 10
    # the old convention never stops early: day_done is False whatever happened
    class Ctx:                                                                          # noqa: E306
        _s = type("s", (), {"positions": [], "orders": []})()
    old = Always(BASE)
    old.over = True
    assert old.day_done(Ctx()) is False


# ---- the open-loss accounting covers the longer hold ------------------------------------------------------------------------------

def test_worst_open_loss_per_day_covers_a_trade_held_past_its_session_and_an_evening_trade():
    """A nyam long dips 60 points at 14:00 (after the session) and recovers by 15:58: under hold_to='day' the trade's MAE, the
    day's worst open loss and the metric set carry that dip (the old rule had left at 11:00, before it)."""
    tape = mk(D, "09:00", "16:10", path=[("14:00", 14940.0), ("15:00", 15000.0)])
    old, new = run(Always, BASE, tape), run(Always, DAY, tape)
    assert old[0]["mae_usd"] < 100 and 1150 <= new[0]["mae_usd"] <= 1250               # ~60 points x $20
    cal = [D.isoformat()]
    row = LB.daily_rows(new, cal, "build")[0]
    assert row["worst_open_loss"] == pytest.approx(new[0]["mae_usd"] + new[0]["commission"]) and row["worst_open_loss"] > 1150
    assert row["minutes_in_market"] == pytest.approx(387, abs=1)                       # 09:31 -> 15:58
    assert LB.daily_rows(old, cal)[0]["worst_open_loss"] < 110
    m = LB.metrics(LB.pack(new), cal)
    assert m["worst_open_loss"] == pytest.approx(row["worst_open_loss"]) and m["trades"] == 1
    # an EVENING entry held to 15:58: the dip at 02:00 belongs to the trade date the trade carries
    ev = run(Always, {**DAY, "sess": "eve"}, mk(D, "18:00", "16:10", eve=True, path=[("02:00", 14940.0), ("03:00", 15000.0)]))
    r2 = LB.daily_rows(ev, cal)[0]
    assert ev[0]["date"] == cal[0] and r2["worst_open_loss"] == pytest.approx(ev[0]["mae_usd"] + ev[0]["commission"])
    assert r2["worst_open_loss"] > 1150
    assert r2["minutes_in_market"] > 21 * 60
    # two members open at once (an asia trade still open when the nyam trade enters): their open losses ADD (conservative)
    both = LB.daily_rows(ev + new, cal)[0]
    assert both["worst_open_loss"] == pytest.approx(r2["worst_open_loss"] + row["worst_open_loss"])
    # ... and a trade that closed before the next one entered is realised P&L, not an open loss
    a = {"date": cal[0], "entry_ms": 1000, "exit_ms": 2000, "net": -300.0, "mae_usd": 350.0, "commission": 4.0}
    b = {"date": cal[0], "entry_ms": 3000, "exit_ms": 9000, "net": 100.0, "mae_usd": 200.0, "commission": 4.0}
    assert LB.daily_rows([a, b], cal)[0]["worst_open_loss"] == pytest.approx(300.0 + 204.0)
    assert LB.daily_rows([a, {**b, "entry_ms": 1500}], cal)[0]["worst_open_loss"] == pytest.approx(354.0 + 204.0)


# ---- run_menus runs every unit and null with it -------------------------------------------------------------------------------------

def test_run_menus_runs_seven_session_instances_per_cell_with_hold_to_day():
    import families
    g = families.unit_grid("donchian", "NQ", "5")
    specs = RM.cell_specs(g[0])
    assert [p["sess"] for _, p in specs] == list(RM.DAY_PASSES) == ["asia", "london", "pre", "nyam", "mid", "pm", "eve"]
    assert all(p["hold_to"] == "day" for _, p in specs) and all(len(cls(p).sessions()) == 1 for cls, p in specs)
    old = RM.cell_specs(g[0], "session")                                               # the old convention: gates / regression
    assert [p["sess"] for _, p in old] == ["all", "pre", "eve"] and all("hold_to" not in p for _, p in old)
    # a family that trades NY only gets no instance for the sessions it never trades
    assert [p["sess"] for _, p in RM.cell_specs(families.unit_grid("ib", "NQ", "5")[0])] == ["nyam", "mid", "pm"]
    assert [p["sess"] for _, p in RM.cell_specs(families.unit_grid("mid_fade", "NQ", "5")[0])] == ["mid"]
    # a time-fired family is one instance; its time-shuffle null and the C1 pool keep the convention
    t = families.unit_grid("straddle_t_1800", "NQ", "30")
    assert [p["hold_to"] for _, p in RM.cell_specs(t[0])] == ["day"]
    assert all(p["hold_to"] == "day" and p["shift_seed"] in (1, 2) for c in RM.shift_grid(t[:2]) for _, p in RM.cell_specs(c))
    c1 = RM.cell_specs(RM.c1_grid("NQ", "5")[0])
    assert [p["sess"] for _, p in c1] == list(RM.DAY_PASSES) and all(p["hold_to"] == "day" for _, p in c1)
    with pytest.raises(ValueError):
        RM.cell_specs(g[0], "week")


def test_real_tapes_counts_only_hold_checks_worker_parity_and_the_entries_are_the_old_conventions():
    """Three smoke days of NQ, a few cells of three registered families through run_menus.run_grid: nothing ends after the
    day's flatten minute, no two trades of a cell-session overlap, 1 worker == 2 workers -- and the new convention changes
    NOTHING but the exits the old rule forced by the clock: every entry (date, side, time, price) is an entry of the old
    convention and vice versa, and a trade the old rule closed by its stop / target / bar exit is identical in every field.
    (Stated exceptions, both on an equity half day: the old rule still entered in the 5 minutes before 13:13, and a stop /
    target it hit between 13:13 and the 13:15 close is a 13:13 flatten now.) COUNTS / identities only."""
    import families
    days = list(RM.SMOKE_DAYS[3:6])                                                    # 2022-09-21 (FOMC), 2022-11-25 (half day), 2023-03-22
    ent = lambda t: (t["date"], t["side"], t["entry_ms"], t["entry_price"])            # noqa: E731
    held = 0
    for name, tf in (("donchian", "15"), ("straddle_t_0930", "30"), ("vwap_band", "5")):
        grid = families.unit_grid(name, "NQ", tf)[::37][:4]
        a = RM.run_grid(grid, "NQ", features=None, workers=1, days=days)
        b = RM.run_grid(grid, "NQ", features=None, workers=2, days=days)
        assert [r["trades"] for r in a] == [r["trades"] for r in b]
        assert RM.hold_checks(a, "NQ") == {"exit_after_day_flat": 0, "overlap_in_session": 0, "entry_in_no_session": 0}
        assert sum(len(r["trades"]) for r in a) > 0 and all(r["skipped_by_error"] == 0 for r in a)
        old = RM.run_grid(grid, "NQ", features=None, workers=1, days=days, hold="session")
        for x, y in zip(a, old):
            new_by = {ent(t): t for t in x["trades"]}
            assert len(new_by) == len(x["trades"])
            gone = [t for t in y["trades"] if ent(t) not in new_by]
            for t in gone:                                                             # only the half day's last five minutes
                d = S._date(t["date"])
                assert d in S.EARLY_CLOSES and t["entry_ms"] >= S.et_ns(d, "13:08") // 1_000_000, (name, t["date"], hm(t["entry_ms"]))
            assert set(new_by) <= {ent(t) for t in y["trades"]}                        # no entry the old convention did not take
            for t in y["trades"]:
                d = S._date(t["date"])
                if ent(t) in new_by and t["exit_reason"] not in ("time", "eod"):
                    if d in S.EARLY_CLOSES and t["exit_ms"] >= S.et_ns(d, "13:13") // 1_000_000:
                        assert new_by[ent(t)]["exit_reason"] == "time"                 # hit after 13:13 on a half day: flat at 13:13 now
                    else:
                        assert new_by[ent(t)] == t                                     # same trade, every field
                elif ent(t) in new_by and S._date(t["date"]) not in S.EARLY_CLOSES:    # (a half day: 13:13 instead of the 13:15 close)
                    n = new_by[ent(t)]
                    assert n["exit_ms"] >= t["exit_ms"] and n["mae_usd"] >= t["mae_usd"] and n["mfe_usd"] >= t["mfe_usd"]
                    held += n["exit_ms"] > t["exit_ms"]
            half = [t for t in x["trades"] if t["date"] == "2022-11-25"]
            assert all(t["exit_ms"] < S.et_ns(dt.date(2022, 11, 25), "13:14") // 1_000_000 for t in half)      # flat by 13:13
    assert held > 0                                                                    # some trades really are held past their session
