"""Stage A hardening of l2sim (2026-10-02): one-direction evidence on the trade rows, the look-ahead bound as an error,
the first session's evening lookback, the B6 depth filter (default off = bit-identical), the phase-check execution guard.
Synthetic tapes where possible; real data = a few in-sample days, one process. No P&L is asserted or printed."""
import datetime as dt
import json

import numpy as np
import pytest

import l2ref
import l2sim as S

D = dt.date(2024, 3, 5)
T0 = S.et_ns(D, "09:30")


def tape(prints, d=D):
    ts = [T0 + int(round(p[0] * 1e9)) for p in prints]
    return S.Tape("NQ", d, "NQH4", ts, [p[1] for p in prints], [1] * len(prints))


class Script(S.Strategy):
    session_window = ("09:30", "10:00")
    bar_minutes = 1

    def __init__(self, fn):
        super().__init__({})
        self.fn = fn

    def on_session(self, ctx):
        self.fn(ctx, "session")

    def on_bar(self, ctx, bar):
        self.fn(ctx, "bar")


def sess(prints, fn):
    return S.run_session(Script(fn), tape(prints))


def once(action):
    def fn(ctx, kind):
        if kind == "session":
            action(ctx)
    return fn


UP = [(1, 100.0), (5, 101.0), (10, 102.0), (20, 103.0), (1700, 103.0)]            # rises through 101 / 102


# ---- (a) evidence of two-sided resting orders -----------------------------------------------------------------------
def test_oco_pair_is_stamped_on_the_row_and_the_session():
    def straddle(c):
        a, b = c.stop_entry("long", 101.0, sl=99.0, tp=103.0), c.stop_entry("short", 99.0, sl=101.0, tp=97.0)
        c.oco(a, b)
    r = sess(UP, once(straddle))
    assert len(r.trades) == 1 and r.trades[0]["oco"] is True and r.trades[0]["both_sides"] is True and r.both_sides is True


def test_two_independent_opposite_entries_are_both_sides_without_an_oco_group():
    def two(c):
        c.stop_entry("long", 101.0, sl=99.0)
        c.stop_entry("short", 99.0, sl=101.0)                              # no ctx.oco: still orders working on both sides
    r = sess(UP, once(two))
    assert len(r.trades) == 1 and r.trades[0]["oco"] is False and r.trades[0]["both_sides"] is True


def test_one_sided_orders_market_entries_and_same_side_oco_are_not_stamped():
    r = sess(UP, once(lambda c: c.market("long", sl=99.0, tp=110.0)))       # the position's own SL / TP are exits, not entries
    assert [(t["oco"], t["both_sides"]) for t in r.trades] == [(False, False)] and r.both_sides is False

    def ladder(c):                                                          # two entries on the SAME side, one cancels the other
        c.oco(c.stop_entry("long", 101.0, sl=99.0), c.limit_entry("long", 99.0, sl=97.0))
    r = sess(UP, once(ladder))
    assert len(r.trades) == 1 and (r.trades[0]["oco"], r.trades[0]["both_sides"]) == (False, False)

    def flip(c, kind, st={}):                                               # long entry cancelled, THEN a short entry: never both at once
        if kind == "session":
            st["o"] = c.limit_entry("long", 90.0, sl=88.0)
        elif "done" not in st:
            st["done"] = True
            c.cancel(st["o"])
            c.market("short", sl=120.0)
    r = sess(UP, flip)
    assert len(r.trades) == 1 and r.trades[0]["side"] == "short" and r.trades[0]["both_sides"] is False


def test_the_stamp_covers_every_trade_of_the_session_and_sessions_without_a_fill():
    def late(c, kind, st={"n": 0}):
        st["n"] += 1
        if kind == "session":
            c.market("long", sl=90.0, tp=101.5)                             # trade 1: closed long before the straddle is armed
        elif st["n"] == 3:
            c.oco(c.stop_entry("long", 200.0), c.stop_entry("short", 50.0))  # never fills
    pr = [(1, 100.0), (5, 101.0), (10, 102.0), (70, 102.0), (130, 102.0), (190, 102.0), (1700, 102.0)]
    r = sess(pr, late)
    assert len(r.trades) == 1 and r.trades[0]["oco"] is False
    assert r.trades[0]["both_sides"] is True and r.both_sides is True       # "at any time during the session"
    r = sess(pr, once(lambda c: c.oco(c.stop_entry("long", 200.0), c.stop_entry("short", 50.0))))
    assert r.trades == [] and r.both_sides is True                          # no fill, no row: the session flag still says so


def test_runner_counts_both_side_sessions_and_the_bundle_carries_them(l_tmp):
    days = ["2024-03-05", "2024-03-06", "2024-03-07"]
    st = S.run(l2ref.Straddle, {"tf": "30", "stop_val": 3.0, "off_atr": 0.25}, days=days, workers=1)
    assert st["both_sides_sessions"] == 3 and st["trades"] and all(t["oco"] and t["both_sides"] for t in st["trades"])
    assert all(t["order_price"] is not None for t in st["trades"])
    dn = S.run(l2ref.Donchian, {"tf": "15"}, days=days, workers=1)
    assert dn["both_sides_sessions"] == 0 and dn["trades"] and not any(t["oco"] or t["both_sides"] for t in dn["trades"])
    assert all(t["order_price"] is None for t in dn["trades"]) and dn["meta"]["days_subset"] is True
    meta = json.loads((S.write_bundle(st, l_tmp / "straddle") / "run.json").read_text())
    assert meta["both_sides_sessions"] == 3 and meta["coverage"]["sessions"] == 3
    # the gate reads it: the simulator's rows PROVE one direction for donchian and disprove it for the straddle, whatever is declared
    A = pytest.importorskip("apex300")
    assert A.trade_checks(dn["trades"])["stamped"] == len(dn["trades"]) and A.trade_checks(st["trades"])["both_side_orders"] == len(st["trades"])


# ---- (d) the look-ahead bound is an error, not an assert --------------------------------------------------------------
class Liar(int):
    """An int whose comparisons lie: `-3 < 0` is False. The old guard tested the sign with the object's own `<`."""

    def __lt__(self, other):
        return False

    def __ge__(self, other):
        return True


def test_a_lying_int_subclass_raises_lookahead_error_and_aborts_the_run():
    f = S.Features([T0 + 60 * S.NS * (i + 1) for i in range(10)], {"x": [float(i) for i in range(10)]})
    ts = [T0 + (60 * i + 1) * S.NS for i in range(12)] + [T0 + 1700 * S.NS]
    tp = S.Tape("NQ", D, "NQH4", ts, [100.0] * len(ts), [1] * len(ts))
    seen = []

    def fn(ctx, kind):
        if kind != "bar":
            return
        for bad in (Liar(-1), Liar(-3)):
            with pytest.raises(S.LookAheadError):
                ctx.feat("x", bad)
            with pytest.raises(S.LookAheadError):
                ctx.feat_window("x", bad)
        assert ctx.feat("x", Liar(0)) == ctx.feat("x") and ctx.feat("x", Liar(1)) == ctx.feat("x", 1)       # honest values still work
        seen.append(ctx.feat_n())
    assert S.run_session(Script(fn), tp, features=f).skip is None and len(seen) >= 10

    class Peek(S.Strategy):                                                  # not swallowed as a 'strategy error' session
        session_window = ("09:30", "10:00")

        def on_bar(self, ctx, bar):
            ctx.feat("x", Liar(-1))
    with pytest.raises(S.LookAheadError):
        S.run_session(Peek(), tp, features=f)
    src = open(S.__file__).read()
    assert "assert k < n" not in src and S._fatal(S.LookAheadError("x"))


# ---- (d) the first session keeps its evening lookback -----------------------------------------------------------------
def test_first_in_sample_session_has_the_prior_evening_rows():
    pytest.importorskip("l2data")
    try:
        ld = S.L2Features(["imb10", "f_delta", "t_utc"])
        first, second = ld(dt.date(2021, 9, 22)), ld(dt.date(2021, 9, 23))
    except FileNotFoundError as e:
        pytest.skip(f"feature cache not built: {e}")
    for f, d in ((first, dt.date(2021, 9, 22)), (second, dt.date(2021, 9, 23))):
        assert f.usable_ns[0] == S.et_ns(d, "00:00") - 359 * S.MIN_NS      # 18:01 ET the evening before: the 18:00 stamp
        assert f.n_usable(S.et_ns(d, "00:00")) == 360                       # 360 rows already usable at the asia open
        assert (np.diff(f.usable_ns[:360]) == S.MIN_NS).all()
    assert S.TABLE_START == dt.date(2021, 9, 21) and np.isfinite(first.cols["f_delta"][:360]).sum() > 100


# ---- 2. Template filter B6 f_depth --------------------------------------------------------------------------------------
def test_depth_regime_thresholds_are_on_the_ratio():
    f32 = lambda x: float(np.float32(x))
    assert S.depth_regime(None) is None and S.depth_regime(float("nan")) is None
    assert S.depth_regime(0.0) == "mid" and S.depth_regime(-0.19) == "mid" and S.depth_regime(0.19) == "mid"
    assert S.depth_regime(-0.21) == "thin" and S.depth_regime(-0.9) == "thin" and S.depth_regime(0.21) == "thick" and S.depth_regime(3.0) == "thick"
    # the column is ratio - 1 in float32: a depth of exactly 0.8 x / 1.2 x the median is inside (<= / >=)
    assert S.depth_regime(f32(0.8 - 1.0)) == "thin" and S.depth_regime(f32(1.2 - 1.0)) == "thick"
    assert S.depth_regime(f32(80 / 100 - 1.0)) == "thin" and S.depth_regime(f32(81 / 100 - 1.0)) == "mid"
    assert S.depth_regime(f32(120 / 100 - 1.0)) == "thick" and S.depth_regime(f32(119 / 100 - 1.0)) == "mid"
    assert (S.DEPTH_THIN, S.DEPTH_THICK, S.DEPTH_COL) == (0.8, 1.2, "depth10_rel20d")                   # SPEC, pre-registered


class DepthTag(l2ref.Donchian):
    """Donchian that tags every entry with the depth value its decision saw (test only)."""

    def fam_signal(self, ctx):
        n = int(self.p["n"])
        if self.nb <= n:
            return
        hh, ll, c = max(self.H[-n - 1:-1]), min(self.L[-n - 1:-1]), self.C[-1]
        if c > hh or c < ll:
            self._mkt(ctx, "long" if c > hh else "short", struct=ll if c > hh else hh, tag={"d": ctx.feat(S.DEPTH_COL)})


DAYS = ["2024-03-05", "2024-03-06", "2024-03-07", "2024-04-10", "2024-04-11", "2024-11-06"]
KEYS = ("date", "side", "entry_price", "exit_price", "exit_reason", "entry_ms", "exit_ms", "sl", "tp", "net")


def test_f_depth_default_off_is_bit_identical_and_thin_thick_filter_at_the_decision():
    pytest.importorskip("l2data")
    p = {"tf": "5", "n": 10}
    base = S.run(l2ref.Donchian, p, days=DAYS, workers=1)                    # no features at all: the validated path
    assert base["meta"]["inputs"]["f_depth"] == "off" and len(base["trades"]) > 20
    try:
        feats = S.L2Features([S.DEPTH_COL])
        off = S.run(l2ref.Donchian, {**p, "f_depth": "off"}, days=DAYS, workers=1, features=feats)
    except FileNotFoundError as e:
        pytest.skip(f"feature cache not built: {e}")
    assert off["trades"] == base["trades"]                                   # default off: every field of every trade identical
    seen = {}
    for mode in ("off", "thin", "thick"):
        r = S.run(DepthTag, {**p, "f_depth": mode}, days=DAYS, workers=1, features=feats)
        assert r["skipped_by_error"] == 0
        seen[mode] = [t["tag"]["d"] for t in r["trades"]]
    tagged = S.run(DepthTag, p, days=DAYS, workers=1, features=feats)["trades"]
    assert [tuple(t[k] for k in KEYS) for t in tagged] == [tuple(t[k] for k in KEYS) for t in base["trades"]]
    assert seen["thin"] and all(S.depth_regime(d) == "thin" and 1.0 + d <= 0.8 + 1e-6 for d in seen["thin"])
    assert seen["thick"] and all(S.depth_regime(d) == "thick" and 1.0 + d >= 1.2 - 1e-6 for d in seen["thick"])
    regimes = {S.depth_regime(d) for d in seen["off"]}
    assert "mid" in regimes and len(seen["thin"]) < len(seen["off"]) and len(seen["thick"]) < len(seen["off"])
    # the filter cannot run blind: no loader, or a loader without the column, is refused before anything runs
    for bad in (None, S.L2Features(["imb10"])):
        with pytest.raises(ValueError, match="f_depth"):
            S.run(l2ref.Donchian, {**p, "f_depth": "thin"}, days=DAYS[:1], workers=1, features=bad)
    with pytest.raises(ValueError, match="f_depth"):
        l2ref.Donchian({"f_depth": "deep"})
    # a missing value (roll block: book masked) blocks the entry instead of passing it
    roll = S.run(DepthTag, {**p, "f_depth": "thin"}, days=["2022-06-13"], workers=1, features=feats)
    assert roll["trades"] == [] and roll["skipped_by_error"] == 0


# ---- (e) the execution guard of a month that failed the phase check -----------------------------------------------------
def _guard_file(tmp_path, failed, checked=()):
    p = tmp_path / "phase_guard.json"
    months = {m: {"ok": m not in failed} for m in set(failed) | set(checked)}
    p.write_text(json.dumps({"guard_ms": 1000, "months": months, "failed": sorted(failed)}))
    return p


def test_failed_phase_months_run_with_the_one_second_guard(tmp_path, monkeypatch):
    pytest.importorskip("l2data")
    days = ["2024-03-05", "2024-03-06", "2024-04-10", "2024-04-11"]
    book = S.L2Features(["imb10", "f_delta"])
    try:
        clean = S.run(l2ref.FeatureProbe, {}, days=days, workers=1, features=book)
    except FileNotFoundError as e:
        pytest.skip(f"feature cache not built: {e}")
    assert clean["meta"]["exec_guard"] is None and len(clean["trades"]) == 4          # the real file: no in-sample month failed
    monkeypatch.setattr(S, "PHASE_GUARD", _guard_file(tmp_path, ["2024-03"], ["2024-04"]))
    assert S.phase_guard() == {"checked": frozenset({"2024-03", "2024-04"}), "failed": frozenset({"2024-03"})}
    for workers in (1, 2):                                                   # the parent resolves the months: workers agree
        g = S.run(l2ref.FeatureProbe, {}, days=days, workers=workers, features=book)
        assert g["meta"]["exec_guard"] == {"ms": 1000, "months": ["2024-03"], "sessions": 2}
        assert len(g["trades"]) == 4
        for t, c in zip(g["trades"], clean["trades"]):
            decision = S.et_ns(dt.date.fromisoformat(t["date"]), "10:00") // 1_000_000
            assert t["tag"] == c["tag"] and c["entry_ms"] >= decision + 85   # the decision (what it saw) is the same ...
            if t["date"].startswith("2024-03"):
                assert t["entry_ms"] >= decision + 1085 and t["entry_ms"] > c["entry_ms"]      # ... the order goes live 1 s later
            else:
                assert t == c
        assert g["meta"]["stress"] is None                                   # the guard is not a caller's stress setting
    # runs that read no BOOK column are not touched: no features, or the own-tape flow columns only
    assert S.run(l2ref.Donchian, {"tf": "15"}, days=days, workers=1)["meta"]["exec_guard"] is None
    class FlowProbe(l2ref.FeatureProbe):                                     # reads the own-tape flow only

        def on_time(self, ctx, t):
            if t == self.p["at"]:
                ctx.market("long", tag={"f_delta": ctx.feat("f_delta")})
            else:
                ctx.flatten("time")
    flow = S.run(FlowProbe, {}, days=days, workers=1, features=S.L2Features(["f_delta"]))
    assert flow["meta"]["exec_guard"] is None and [t["entry_ms"] for t in flow["trades"]] == [t["entry_ms"] for t in clean["trades"]]
    assert not S.needs_exec_guard(None) and not S.needs_exec_guard(S.L2Features(["f_delta", "f_c", "t_utc", "et_min"]))
    assert S.needs_exec_guard(S.L2Features(["f_delta", "bid_px"])) and S.needs_exec_guard(lambda d: None)      # unknown loader: guarded
    assert S.Costs(guard_ms=1000).guard_ms == 1000 and S.phase_guard(tmp_path / "absent.json")["failed"] == frozenset()
    with pytest.raises(ValueError):
        S.Costs(guard_ms=-1)


def test_holdout_run_on_book_features_is_refused_without_a_persisted_phase_check(tmp_path, monkeypatch):
    """Mechanical, not an honour flag: a holdout month that the holdout build never measured cannot be run on book features.
    Nothing sealed is read here: the refusal comes before any tape / feature load (the loaders are stubbed to prove it)."""
    def no_read(*a, **k):
        raise AssertionError("a holdout tape / feature was read before the phase-guard check")

    monkeypatch.setattr(S, "load_tape", no_read)
    monkeypatch.setattr(S, "load_daily", no_read)
    hold = ["2025-03-03", "2025-04-01"]
    book = S.L2Features(["imb10"], allow_holdout=True)
    monkeypatch.setattr(S, "PHASE_GUARD", tmp_path / "absent.json")
    with pytest.raises(S.HoldoutSealed):                                     # the seal comes first
        S.run(l2ref.FeatureProbe, {}, days=hold, workers=1, features=S.L2Features(["imb10"]))
    with pytest.raises(S.PhaseGuardMissing, match="2025-03"):
        S.run(l2ref.FeatureProbe, {}, days=hold, workers=1, features=book, allow_holdout=True)
    monkeypatch.setattr(S, "PHASE_GUARD", _guard_file(tmp_path, [], ["2025-03"]))
    with pytest.raises(S.PhaseGuardMissing, match="2025-04"):                # every month of the run must have been measured
        S.run(l2ref.FeatureProbe, {}, days=hold, workers=1, features=book, allow_holdout=True)
    monkeypatch.setattr(S, "PHASE_GUARD", _guard_file(tmp_path, ["2025-04"], ["2025-03"]))
    with pytest.raises(AssertionError, match="was read before"):             # checked: the run proceeds (and hits the stub)
        S.run(l2ref.FeatureProbe, {}, days=hold, workers=1, features=book, allow_holdout=True)


# ---- a script on stdin cannot start worker processes -------------------------------------------------------------------
def test_a_stdin_script_runs_on_one_process_instead_of_hanging(monkeypatch, capsys):
    """`python - <<EOF` + workers > 1: every spawn worker died on start (no main file to re-import) and the pool respawned
    them for ever. The runner now falls back to one process and says so."""
    import sys
    import types
    assert S.pool_usable()                                                   # pytest's main module is a real file
    fake = types.ModuleType("__main__")
    fake.__file__ = str(S.L / "<stdin>")
    monkeypatch.setitem(sys.modules, "__main__", fake)
    assert not S.pool_usable()
    r = S.run(l2ref.Donchian, {"tf": "15"}, days=["2024-03-05", "2024-03-06", "2024-03-07"], workers=8)
    assert r["meta"]["workers"] == 1 and r["sessions"] == 3 and "ONE process" in capsys.readouterr().err
    del fake.__file__                                                        # python -c / interactive: no file, spawn copes
    assert S.pool_usable()
