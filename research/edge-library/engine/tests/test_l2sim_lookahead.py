"""The timestamp law of the feature access (ctx.feat / ctx.feat_window): no argument can reach a row that is not
usable yet, and the adapter's ABSOLUTE clock is checked against an independent one (the tape's own timestamps),
so a constant time shift in the adapter (a minute, an hour) cannot pass. In-sample days only."""
import datetime as dt

import numpy as np
import pytest

import l2ref
import l2sim as S

D = dt.date(2024, 3, 5)
T0 = S.et_ns(D, "09:30")


def synth():
    """10 feature rows, row i usable at 09:30 + (i+1) min, value float(i); one print per minute."""
    f = S.Features([T0 + 60 * S.NS * (i + 1) for i in range(10)], {"x": [float(i) for i in range(10)]})
    ts = [T0 + (60 * i + 1) * S.NS for i in range(12)] + [T0 + 1700 * S.NS]
    return f, S.Tape("NQ", D, "NQH4", ts, [100.0] * len(ts), [1] * len(ts))


class Call(S.Strategy):
    session_window = ("09:30", "10:00")

    def __init__(self, fn):
        super().__init__({})
        self.fn = fn

    def on_bar(self, ctx, bar):
        self.fn(ctx, bar)


# ---- the guard ------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("back", [-1, -2, -5, -10 ** 9, np.int64(-1), -1.0, 0.5, 1.0, True, "1", None])
def test_feat_rejects_a_negative_or_non_integer_back(back):
    """The reported hole: ctx.feat(name, -1) (the Python 'last item' idiom) returned the minute still forming."""
    f, tape = synth()
    seen = []

    def fn(ctx, bar):
        with pytest.raises(S.LookAheadError):
            ctx.feat("x", back)
        with pytest.raises(S.LookAheadError):
            ctx.feat("x", back=back, default=0.0)
        seen.append(ctx.now_ns)
    assert S.run_session(Call(fn), tape, features=f).skip is None
    assert len(seen) >= 10


@pytest.mark.parametrize("n", [-1, -3, -10 ** 9, np.int64(-2), 1.5, True, "3"])
def test_feat_window_rejects_a_negative_or_non_integer_n(n):
    f, tape = synth()
    seen = []

    def fn(ctx, bar):
        with pytest.raises(S.LookAheadError):
            ctx.feat_window("x", n)
        seen.append(1)
    assert S.run_session(Call(fn), tape, features=f).skip is None and len(seen) >= 10


def test_no_argument_returns_a_row_that_is_not_usable_yet():
    """Exhaustive on the synthetic table: every value any call returns belongs to a row with usable_ns <= now."""
    f, tape = synth()
    checked = []

    def fn(ctx, bar):
        n = ctx.feat_n()
        ok = (f.usable_ns <= ctx.now_ns)
        assert n == int(ok.sum()) and (f.usable_ns[:n] <= ctx.now_ns).all() and (f.usable_ns[n:] > ctx.now_ns).all()
        allowed = set(f.cols["x"][:n].tolist())
        for back in list(range(0, 15)) + [np.int64(0), np.int32(2)]:
            v = ctx.feat("x", back)
            want = f.cols["x"][n - 1 - int(back)] if n - 1 - int(back) >= 0 else None
            assert v == want and (v is None or v in allowed)
            assert ctx.feat("x", back, default=-7.0) == (-7.0 if want is None else want)
        for back in range(-12, 0):
            with pytest.raises(S.LookAheadError):
                ctx.feat("x", back)
        for nw in (None, 0, 1, 3, 9, 10, 11, 100, np.int64(2)):
            w = ctx.feat_window("x", nw).tolist()
            want = f.cols["x"][:n].tolist() if nw is None else f.cols["x"][max(0, n - int(nw)):n].tolist()
            assert w == want and set(w) <= allowed
        assert ctx.feat_window("x", 0).tolist() == []                # 0 = nothing (it used to mean everything)
        checked.append(n)
    assert S.run_session(Call(fn), tape, features=f).skip is None
    assert checked[:11] == list(range(1, 11)) + [10]                  # one more row per minute, never ahead


def test_the_newest_row_is_never_the_minute_still_forming():
    """At the close of minute M (decision M+60 s) the newest row is M's own; row M+1 (usable a minute later,
    value = M's value + 1) is what a negative back used to return."""
    f, tape = synth()
    got = []
    S.run_session(Call(lambda ctx, bar: got.append(((bar.end_ns - T0) // (60 * S.NS), ctx.feat("x")))), tape, features=f)
    assert got[:10] == [(m, float(m - 1)) for m in range(1, 11)]


class Peek(S.Template):
    """A family that tries to read the next minute (what the verifier's leak demo did)."""
    def fam_signal(self, ctx):
        nxt = ctx.feat("f_c", -1)
        if nxt is not None:
            self._mkt(ctx, "long" if nxt > self.C[-1] else "short")


class PeekQuiet(S.Strategy):
    """Swallowing the error inside the strategy yields nothing either: there is no value to get."""
    session_window = ("09:30", "10:00")

    def on_session(self, ctx):
        self.got = []

    def on_bar(self, ctx, bar):
        try:
            self.got.append(ctx.feat("x", -1))
        except S.LookAheadError:
            self.got.append("refused")


def test_a_look_ahead_attempt_aborts_the_run_and_is_never_booked_as_a_skipped_session():
    f, tape = synth()
    with pytest.raises(S.LookAheadError):
        S.run_session(Call(lambda ctx, bar: ctx.feat("x", -1)), tape, features=f)          # on_error="skip" default
    with pytest.raises(S.LookAheadError):
        S.run_session(Call(lambda ctx, bar: ctx.feat_window("x", -2)), tape, features=f)
    st = PeekQuiet()
    assert S.run_session(st, tape, features=f).skip is None and set(st.got) == {"refused"} and len(st.got) >= 10
    assert issubclass(S.LookAheadError, ValueError) and S._fatal(S.LookAheadError("x")) and S._fatal(S.HoldoutSealed("x"))
    if not (S.CACHE / "l2feat_NQ_2024.parquet").exists():
        pytest.skip("data-layer cache not built")
    with pytest.raises(S.LookAheadError):                             # through the runner too (one process)
        S.run(Peek, {"tf": "1", "sess": "nyam"}, "2024-06-05", "2024-06-05", workers=1, features=S.L2Features(["f_c"]))


# ---- the independent clock -------------------------------------------------------------------------------------
COLS = list(l2ref.ClockProbe.CLOCK_COLS)
CLOCK_DAYS = ["2021-11-05", "2021-11-08",      # Fri before / Mon after the 2021 DST end
              "2022-03-11", "2022-03-14",      # Fri before / Mon after the 2022 DST start (03-14 is a roll day too)
              "2022-06-13",                    # roll day
              "2023-11-24",                    # half day
              "2024-11-01", "2024-11-04",      # around the 2024 DST end
              "2024-12-31"]                    # last in-sample session


def need_cache():
    if not all((S.CACHE / f"l2feat_NQ_{y}.parquet").exists() for y in (2021, 2022, 2023, 2024)):
        pytest.skip("data-layer cache not built")


PROBE_59 = ["%02d:%02d:59" % (h, m) for h, m in [(9, m) for m in range(31, 60)] + [(10, m) for m in range(0, 60)]]


def tape_bar(tape, start_ns):
    """OHLCV of the prints stamped inside [start, start + 60 s): recomputed from the tape, no engine code."""
    a, z = np.searchsorted(tape.ts, [start_ns, start_ns + S.MIN_NS], side="left")
    seg = tape.px[a:z]
    return (seg[0], seg.max(), seg.min(), seg[-1], float(tape.size[a:z].sum())) if z > a else None


def clock_counts(iso, loader, shift_ns=0):
    """At each 1-minute bar close (decision M+60 s): is the newest visible flow row the bar the engine just built
    from the TAPE (same), the bar of the next minute (look-ahead) or of the previous one (stale)?
    At M+59 s (89 probes 09:31:59 .. 10:59:59): the newest visible row must still be minute M-1's (early_ok),
    i.e. minute M's row is NOT visible one second before its minute ends."""
    tape = S.load_tape(iso)
    f = loader(tape.date)
    if shift_ns:
        f = S.Features(f.usable_ns + shift_ns, f.cols)
    rows, early = [], []

    class P(S.Strategy):
        session_window = ("00:00", "16:10")

        def times(self):
            return PROBE_59

        def on_bar(self, ctx, bar):
            rows.append(((bar.o, bar.h, bar.l, bar.c, float(bar.v)), tuple(ctx.feat(c) for c in COLS), bar))

        def on_time(self, ctx, t):
            early.append((ctx.now_ns, tuple(ctx.feat(c) for c in COLS)))
    assert S.run_session(P(), tape, features=f, window=S.effective_session_window(tape.date, P.session_window)).skip is None
    for me, _, b in rows[::97]:                      # the engine's bars equal the independent recomputation
        assert me == tape_bar(tape, b.start_ns) and b.end_ns - b.start_ns == S.MIN_NS and b.start_ns % S.MIN_NS == 0
    assert len(early) == len(PROBE_59)
    return {"bars": len(rows), "same": sum(me == got for me, got, _ in rows),
            "next": sum(rows[n][1] == rows[n + 1][0] for n in range(len(rows) - 1)),
            "prev": sum(rows[n][1] == rows[n - 1][0] for n in range(1, len(rows))),
            "probes": len(early),
            "early_ok": sum(got == tape_bar(tape, now - 59 * S.NS - S.MIN_NS) for now, got in early),
            "early_leak": sum(got == tape_bar(tape, now - 59 * S.NS) for now, got in early)}


@pytest.mark.parametrize("iso", CLOCK_DAYS)
def test_feature_adapter_agrees_with_the_tape_clock_on_every_bar(iso):
    """INDEPENDENT CLOCK. The engine's bar clock comes from the tape's ts_ns; the feature rows come from the data
    layer's own usable_at index. At every bar close the newest visible flow row must BE that bar, and one second
    before a minute ends its row must not be visible yet -- on days either side of each DST change, a roll day, a
    half day. (The older real-data tests compare the adapter with the same index it reads, so they cannot see a
    constant shift.)"""
    need_cache()
    c = clock_counts(iso, S.L2Features(COLS))
    assert c["bars"] > 700 and c["same"] == c["bars"], (iso, c)
    assert c["early_ok"] == c["probes"] == 89 and c["early_leak"] == 0, (iso, c)


@pytest.mark.parametrize("shift_s", [-3600, -120, -60, -1, 1, 60, 3600])
def test_the_clock_check_catches_a_constant_time_shift(shift_s):
    """Power: the same check on a table shifted by a constant must go red. A minute EARLY shows the NEXT minute's
    bar at every close (look-ahead), a minute late the previous one (stale), an hour (time zone / DST slip) matches
    nothing; one second early leaves the closes right but leaks the forming minute at M+59 s; one second late
    makes every close stale."""
    need_cache()
    loader = S.L2Features(COLS)
    for iso in ("2022-03-11", "2022-03-14", "2024-11-04"):
        c = clock_counts(iso, loader, shift_s * S.NS)
        n = c["bars"]
        if shift_s == -1:
            assert c["same"] == n and c["early_ok"] == 0 and c["early_leak"] == c["probes"], (iso, c)
            continue
        assert c["same"] <= 0.02 * n, (iso, shift_s, c)
        if shift_s == -60:
            assert c["next"] >= 0.98 * (n - 1) and c["early_ok"] == 0
        elif shift_s in (1, 60):
            assert c["prev"] >= 0.98 * (n - 1)
        if shift_s < -1 or shift_s >= 60:
            assert c["early_ok"] <= 2, (iso, shift_s, c)


@pytest.mark.parametrize("shift_s", [-60, 3600])
def test_a_shift_inside_the_adapter_itself_is_caught(shift_s, monkeypatch):
    """Mutation of the adapter (features_from_frame as L2Features uses it): the clock check must go red."""
    need_cache()
    real = S.features_from_frame

    def shifted(df, columns=None):
        f = real(df, columns)
        return S.Features(f.usable_ns + shift_s * S.NS, f.cols)
    monkeypatch.setattr(S, "features_from_frame", shifted)
    monkeypatch.setattr(S, "_FRAMES", {})                            # a fresh per-process table through the mutant
    c = clock_counts("2024-11-04", S.L2Features(COLS))
    assert c["same"] <= 0.02 * c["bars"] and c["early_ok"] <= 2
    monkeypatch.undo()
    monkeypatch.setattr(S, "_FRAMES", {})
    c = clock_counts("2024-11-04", S.L2Features(COLS))
    assert c["same"] == c["bars"] and c["early_ok"] == c["probes"]


def test_the_clock_holds_through_worker_processes():
    """The same check where screening runs: S.run with worker processes (l2ref.ClockProbe reports per session)."""
    need_cache()
    res = S.run(l2ref.ClockProbe, {}, days=CLOCK_DAYS, workers=3, features=S.L2Features(COLS))
    assert res["meta"]["workers"] == min(3, S.MAX_WORKERS) and res["trades"] == [] and res["skipped_by_error"] == 0
    assert [n["date"] for n in res["no_trade"]] == CLOCK_DAYS
    for n in res["no_trade"]:
        a, b = n["reason"].replace("clock ", "").split("/")
        assert n["reason"].startswith("clock ") and a == b and int(b) > 700, n
    # without the columns the probe crashes -> every session is reported as dropped, never as a quiet pass
    bad = S.run(l2ref.ClockProbe, {}, days=CLOCK_DAYS[:2], workers=1, features=S.L2Features(["f_c"]))
    assert bad["skipped_by_error"] == 2 and all(n["reason"].startswith("strategy error: KeyError") for n in bad["no_trade"])
