"""l2sim -- the offline tick execution simulator of the NQ Level-2 pilot.

A numpy port of the Homebase Strategy Tester's tick engine (homebase/backtest/engine.py, ENGINE "tick-2"),
replayed on the ofb_tick tape (print-identical to the tester's own tape cache for every in-sample session,
see SIM_VALIDATION.md). Same fill law, same event model, same trades.json schema, so the trade lists it
produces are consumed unchanged by R/evalcore.py and R/funded.py.

FILL LAW (pessimistic, identical to the tester)
  * STOP orders (stop entries and stop-losses) are market-on-touch: a buy stop triggers on the first print
    >= its price and fills at max(price, print) + slip; a sell stop on the first print <= its price at
    min(price, print) - slip. Gapping through the level costs the gap. slip = 1 tick.
  * LIMIT orders (limit entries and targets) need a 1-TICK TRADE-THROUGH: a buy limit fills only on a print
    <= price - tick, a sell limit only on a print >= price + tick, AT the limit price, no slip.
  * MARKET orders fill at the first print at/after they go live, +/- slip.
  * A position's SL/TP ride on the entry and can trigger from the print AFTER the entry print. A print that
    triggers both -> SL (the SL is the older order; orders that trigger on one print fill oldest first).
  * Orders go live `placement_ms` (85) after the event that sent them. ctx.cancel / ctx.flatten act at
    once: a flatten fills on the first print at/after the event time, -/+ slip.
  * NOT pessimistic in every session (tester conventions, see SIM_VALIDATION.md "Open risks"): the 1-tick
    market slip is about half the RTH spread and less overnight, cancels / flattens have no latency, and
    results move with the 85 ms figure. Stress a family with run(..., slip_ticks=2, latency_ms=250)
    (= **STRESS) and, for limit entries, strict_limit=True; see unrealistic_winners().
  * Commission $4.00 per round turn per NQ. qty 1 NQ (resize offline, R conventions).
  * MAE/MFE are measured from the entry PRINT's index to the exit print, against the (slipped) fill price.
  * Every order/SL/TP price is snapped to the tick grid; every touch comparison is epsilon-tolerant.

EVENT MODEL (decisions at minute boundaries only)
  on_session(ctx) at session_window[0]; on_bar(ctx, bar) at the END of every 1-minute bar that has prints
  (bar minute M -> the callback runs at M+1:00.000, BEFORE the first print at/after that time, and sees only
  prints strictly before it); on_time(ctx, "HH:MM[:SS]") at each time in times(). Same-time order:
  session, bar, time. Events at/after the session end never fire; at the end everything is flattened
  ("eod"). On CME half days the window is clamped to 13:15 ET.
  A strategy callback that raises costs that SESSION only (tester rule): its orders are cancelled, its
  trades dropped, the day is listed under no_trade as "strategy error: ..." and counted in the result's
  `skipped_by_error` (a warning is printed). HoldoutSealed / LookAheadError always propagate.
  Per-minute features (book / flow) are read ONLY through ctx.feat / ctx.feat_window, which enforce the
  timestamp law: a row is visible once its `usable_ns` <= the decision time. back / n must be integers
  >= 0: a negative index (the Python "last item" idiom) raises LookAheadError, it never reaches forward.

STRATEGY CONTRACT (the tester's): inputs are checked like the tester's resolve_inputs (unknown key, wrong
type, bad choice, out of range -> ValueError; whole floats -> int, ints -> float); declare choices / ranges
in SCHEMA, anything undeclared is typed by its default. `session_independent` defaults to False as in the
tester (one instance, days in order, one process); Template sets it True (all day state resets in
on_session), a raw Strategy subclass must opt in to run on several workers.

HOLDOUT: any session dated >= 2025-01-01 raises HoldoutSealed unless allow_holdout=True is passed
explicitly (the orchestrator's "holdout" stage only).

COMPUTE WINDOWS: every worker checks the ET clock before each session-day and sleeps through
09:18-09:36 ET on weekdays and Fri 2026-10-02 08:15-08:50 ET. <= 8 worker processes.

USE
    import l2sim as S
    class ImbFollow(S.Template):                       # the common inputs (tf, sess, dir, stop_mode, stop_val,
        DEFAULTS = {"k": 0.2}                          # tgt_r, trail_atr, exit_bars, max_tr, filters) come free
        def fam_signal(self, ctx):                     # called at each tf-bar close inside a session, when flat
            v = ctx.feat("imb10")                      # newest row usable NOW (never the minute still forming)
            if v is not None and v == v and abs(v) >= self.p["k"]:
                self._mkt(ctx, "long" if v > 0 else "short", tag={"imb": v})   # market + ATR/pts bracket
    res = S.run(ImbFollow, {"tf": "1", "sess": "all"}, features=S.L2Features(["imb10"]))        # in-sample, 8 workers
    grid = S.run_many([(ImbFollow, {"k": k}) for k in (1.5, 2, 3)], features=...)                # one tape pass
    S.write_bundle(res, S.L / "out" / "runs" / "imb_follow_tf1")       # trades.json + run.json for R/evalcore
    hard = S.run(ImbFollow, {...}, features=..., **S.STRESS)           # 2 ticks slip, 250 ms latency
    res["skipped_by_error"], res["unrealistic_winners"]                # both must be 0 before a result is used
    res["both_sides_sessions"], row["oco"], row["both_sides"]          # Apex one-direction EVIDENCE (see run_many)
  Template filter f_depth = off | thin | thick (SPEC B6, default off): needs "depth10_rel20d" in the features.
  Families of the screen live in families/ (README there): REGISTRY + screen.py run them.
  Template helpers: _mkt (market), _arm (stop entries, OCO when two legs), _lim (limit entry), ctx.cancel,
  ctx.flatten(reason), times()/fam_times() + fam_time for clock-time actions. Raw API: subclass S.Strategy
  (on_session / on_bar / on_time; ctx.market / stop_entry / limit_entry(sl=, tp=, tp_rr=, ref=, tag=), ctx.oco).

Writes nothing unless asked (write_bundle / build_daily -> under this directory only).
"""
from __future__ import annotations

import datetime as dt
import json
import math
import os
import sys
import time
from multiprocessing import get_context
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

L = Path(__file__).resolve().parent
R = L.parent / "2026-09-29"
TAPE_DIR = Path.home() / "futures_derived" / "ofb_tick"
CACHE = L / "cache"
ET = ZoneInfo("America/New_York")
ENGINE_VERSION = "l2sim-1 (port of tester tick-2)"

HOLDOUT_START = dt.date(2025, 1, 1)
IN_SAMPLE = (dt.date(2021, 9, 22), dt.date(2024, 12, 31))
SPECS = {"NQ": (20.0, 0.25)}                   # root -> (point value, tick)
MAX_WORKERS = 8
NS = 1_000_000_000
MIN_NS = 60 * NS
SIDE = {"long": 1, "short": -1}
NAME = {1: "long", -1: "short"}
CHUNK = 8192


class HoldoutSealed(RuntimeError):
    """A sealed (>= 2025-01-01) session was requested without allow_holdout=True."""


class LookAheadError(ValueError):
    """A strategy asked ctx.feat / ctx.feat_window for a row that is not usable yet (negative back / n).
    Never swallowed by the per-session error handler: it aborts the run."""


class PhaseGuardMissing(RuntimeError):
    """A holdout run reads book features of a month whose snapshot phase was never checked (no entry in
    cache/phase_guard.json): the holdout build (l2data.build_cache(allow_holdout=True)) writes it."""


STRESS = {"slip_ticks": 2.0, "latency_ms": 250}     # run(..., **STRESS): the pre-agreed execution stress
EXEC_GUARD_MS = 1000                                # the 1 s execution guard of a month that failed l2data.phase_check
PHASE_GUARD = CACHE / "phase_guard.json"            # written by l2data.persist_phase (in-sample CLI + the holdout build)
DEPTH_COL = "depth10_rel20d"                        # B6: top-10 depth / its 20-session same-minute median - 1
DEPTH_THIN, DEPTH_THICK = 0.8, 1.2                  # SPEC (pre-registered): thin = ratio <= 0.8, thick = ratio >= 1.2
CLOCK_COLS = frozenset({"t_utc", "et_min"})         # feature-table columns that carry no book / flow information


def depth_regime(v) -> str | None:
    """B6 regime of one `depth10_rel20d` value. The data layer stores the column as RATIO - 1 (0 = the median
    book); the SPEC thresholds are on the ratio: 'thin' = depth <= 0.8 x median (column <= -0.2), 'thick' =
    depth >= 1.2 x median (column >= +0.2), 'mid' between. None when the value is missing / NaN (no signal: a
    filtered family does not trade). The ONE definition: Template's f_depth and the G2 gate both call this."""
    if v is None or v != v:
        return None
    r = 1.0 + float(v)
    if r <= DEPTH_THIN + 1e-6:                      # float32 column: a ratio of exactly 0.8 / 1.2 is inside
        return "thin"
    if r >= DEPTH_THICK - 1e-6:
        return "thick"
    return "mid"


def phase_guard(path=None) -> dict:
    """The persisted phase-check verdicts (l2data.persist_phase): {"checked": {months}, "failed": {months}}.
    A missing file = nothing checked, nothing failed."""
    p = Path(path) if path is not None else PHASE_GUARD
    if not p.exists():
        return {"checked": frozenset(), "failed": frozenset()}
    j = json.loads(p.read_text())
    return {"checked": frozenset(j.get("months") or {}), "failed": frozenset(j.get("failed") or [])}


def needs_exec_guard(features) -> bool:
    """Does a `features=` loader read BOOK snapshot columns (the ones the snapshot-phase check is about)?
    Flow columns (f_*: our own tape, exact by construction) and the clock tags do not; a loader that does not
    name its columns is taken to read the book."""
    if features is None:
        return False
    cols = getattr(features, "columns", None)
    if cols is None:
        return True
    return any(not (str(c).startswith("f_") or c in CLOCK_COLS) for c in cols)


def _date(d) -> dt.date:
    return d if isinstance(d, dt.date) else dt.date.fromisoformat(str(d))


def check_holdout(d, allow_holdout: bool = False) -> None:
    if _date(d) >= HOLDOUT_START and allow_holdout is not True:
        raise HoldoutSealed(f"{d} is in the sealed holdout (>= {HOLDOUT_START}); pass allow_holdout=True "
                            "only when the orchestrator says 'holdout'")


# ---- compute windows --------------------------------------------------------------------------------------
def compute_window_end(now: dt.datetime | None = None) -> dt.datetime | None:
    """The end of the no-heavy-compute window `now` (ET) falls in, or None."""
    now = (now or dt.datetime.now(ET)).astimezone(ET)
    wins = []
    if now.weekday() < 5:
        wins.append((dt.time(9, 18), dt.time(9, 36)))
    if now.date() == dt.date(2026, 10, 2):
        wins.append((dt.time(8, 15), dt.time(8, 50)))
    for a, b in wins:
        if a <= now.time() < b:
            return now.replace(hour=b.hour, minute=b.minute, second=0, microsecond=0)
    return None


def wait_compute_window(sleep=time.sleep, clock=None) -> float:
    """Sleep until the current no-compute window (if any) is over. Returns the seconds slept.
    `clock` (tests) = a callable returning the current datetime; it must advance when `sleep` is called."""
    total = 0.0
    while True:
        cur = (clock() if clock else dt.datetime.now(ET)).astimezone(ET)
        end = compute_window_end(cur)
        if end is None:
            return total
        s = (end - cur).total_seconds() + 1.0
        sleep(s)
        total += s


# ---- time / calendar --------------------------------------------------------------------------------------
def et_ns(d: dt.date, hhmm: str) -> int:
    """'HH:MM' or 'HH:MM:SS' ET wall clock on calendar day d -> UTC epoch ns (the tester's et_ns)."""
    t = dt.time.fromisoformat(hhmm)
    return int(dt.datetime.combine(d, t, tzinfo=ET).timestamp()) * NS


EQUITY_EARLY_CLOSE_ET = "13:15"
_JULY_HALF = {2021: dt.date(2021, 7, 2), 2022: None, 2023: dt.date(2023, 7, 3), 2024: dt.date(2024, 7, 3),
              2025: dt.date(2025, 7, 3), 2026: dt.date(2026, 7, 3)}


def _early_closes(years) -> frozenset:
    out = set()
    for y in years:
        nov1 = dt.date(y, 11, 1)
        out.add(nov1 + dt.timedelta(days=(3 - nov1.weekday()) % 7) + dt.timedelta(weeks=3, days=1))
        if dt.date(y, 12, 24).weekday() < 5:
            out.add(dt.date(y, 12, 24))
        if _JULY_HALF.get(y) is not None:
            out.add(_JULY_HALF[y])
    return frozenset(out)


EARLY_CLOSES = _early_closes(range(2017, 2027))   # same rule as the tester (its table covers 2021-2026)


def effective_session_window(d: dt.date, window: tuple) -> tuple:
    """`window` clamped to the 13:15 ET early close on a CME equity half day (tester semantics)."""
    if d in EARLY_CLOSES and EQUITY_EARLY_CLOSE_ET < window[1]:
        return (window[0], EQUITY_EARLY_CLOSE_ET)
    return tuple(window)


def missing_hours(ts: np.ndarray, d: dt.date, window: tuple) -> list:
    """Runs of clock-hour pieces of the ET window with zero prints (the tester's coverage rule)."""
    t0 = dt.datetime.combine(d, dt.time.fromisoformat(window[0]))
    t1 = dt.datetime.combine(d, dt.time.fromisoformat(window[1]))
    cuts = [t0]
    h = t0.replace(minute=0, second=0) + dt.timedelta(hours=1)
    while h < t1:
        cuts.append(h)
        h += dt.timedelta(hours=1)
    cuts.append(t1)
    edges = np.array([et_ns(d, c.strftime("%H:%M:%S")) for c in cuts], np.int64)
    idx = np.searchsorted(ts, edges, side="left")
    out: list = []
    for a, b, ia, ib in zip(cuts, cuts[1:], idx, idx[1:]):
        if ib - ia > 0:
            continue
        sa, sb = a.strftime("%H:%M"), b.strftime("%H:%M")
        if out and out[-1][1] == sa:
            out[-1][1] = sb
        else:
            out.append([sa, sb])
    return [(a, b) for a, b in out]


# ---- tape -------------------------------------------------------------------------------------------------
class Tape:
    __slots__ = ("root", "date", "contract", "ts", "px", "size", "daily", "_bars")

    def __init__(self, root, date, contract, ts, px, size, daily=None):
        self.root, self.date, self.contract = root, date, contract
        self.ts = np.ascontiguousarray(ts, np.int64)
        self.px = np.ascontiguousarray(px, np.float64)
        self.size = np.ascontiguousarray(size, np.int64)
        self._bars = {}                               # (lo, hi, t0, t1, minutes) -> bars (read-only, shared by grid cells)
        self.daily = daily if daily is not None else (
            {"h": float(self.px.max()), "l": float(self.px.min()), "c": float(self.px[-1])} if len(self.px) else {})


def tape_path(d, root: str = "NQ") -> Path:
    d = _date(d)
    return TAPE_DIR / root / f"{d:%Y}" / f"{d:%m}" / f"{d:%Y-%m-%d}.parquet"


def load_tape(d, root: str = "NQ", allow_holdout: bool = False) -> Tape | None:
    """One session's execution tape (every print of the archive file, tape order). None = not cached.
    Raises HoldoutSealed for a 2025+ date unless allow_holdout=True."""
    d = _date(d)
    check_holdout(d, allow_holdout)
    p = tape_path(d, root)
    if not p.exists():
        return None
    import pyarrow.parquet as pq
    pf = pq.ParquetFile(p)
    t = pf.read(columns=["ts_ns", "price", "size"])
    contract = ""
    try:
        ci = pf.schema_arrow.names.index("contract")
        st = pf.metadata.row_group(0).column(ci).statistics
        contract = st.min if st is not None and st.has_min_max else ""
        contract = contract.decode() if isinstance(contract, bytes) else str(contract)
    except (ValueError, IndexError):
        pass
    if not contract:
        contract = pf.read_row_group(0, columns=["contract"])["contract"][0].as_py()
    return Tape(root, d, contract, t["ts_ns"].to_numpy(), t["price"].to_numpy(), t["size"].to_numpy())


def sessions(start, end, root: str = "NQ", allow_holdout: bool = False) -> list:
    """Weekday session dates in [start, end] that have a tape. A range reaching 2025+ raises unless
    allow_holdout=True."""
    start, end = _date(start), _date(end)
    check_holdout(end, allow_holdout)
    out = []
    for y in range(start.year, end.year + 1):
        for p in (TAPE_DIR / root / str(y)).glob("*/*.parquet"):
            try:
                d = dt.date.fromisoformat(p.name[:10])
            except ValueError:
                continue
            if start <= d <= end and d.weekday() < 5:
                out.append(d)
    return sorted(out)


def _daily_one(args):
    iso, root, allow = args
    wait_compute_window()
    t = load_tape(iso, root, allow_holdout=allow)
    return {"date": iso, **t.daily, "contract": t.contract}


def build_daily(root: str = "NQ", start=IN_SAMPLE[0], end=IN_SAMPLE[1], workers: int = MAX_WORKERS,
                allow_holdout: bool = False) -> Path:
    """(Re)build the daily-bar cache {date, h, l, c, contract} of the whole archive day (= the tester's
    store.daily). In-sample file: cache/daily_<root>.json; a holdout build goes to its own file."""
    days = sessions(start, end, root, allow_holdout)
    args = [(d.isoformat(), root, allow_holdout) for d in days]
    workers = max(1, min(int(workers), MAX_WORKERS))
    wait_compute_window()
    if workers == 1:
        rows = [_daily_one(a) for a in args]
    else:
        with get_context("spawn").Pool(workers) as p:
            rows = p.map(_daily_one, args, chunksize=16)
    out = _daily_path(root, allow_holdout)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"root": root, "start": str(start), "end": str(end), "rows": rows}))
    return out


def _daily_path(root: str, allow_holdout: bool) -> Path:
    return CACHE / (f"daily_{root}_holdout.json" if allow_holdout else f"daily_{root}.json")


def load_daily(root: str = "NQ", allow_holdout: bool = False, build: bool = True) -> list:
    """Daily bars [{date, h, l, c, contract}], ascending. The in-sample cache never holds a 2025+ row."""
    p = _daily_path(root, allow_holdout)
    if not p.exists():
        if not build:
            return []
        build_daily(root, IN_SAMPLE[0], (dt.date(2026, 12, 31) if allow_holdout else IN_SAMPLE[1]),
                    allow_holdout=allow_holdout)
    rows = json.loads(p.read_text())["rows"]
    if not allow_holdout:
        rows = [r for r in rows if r["date"] < HOLDOUT_START.isoformat()]
    return rows


def rolls(daily: list) -> frozenset:
    """Session dates whose front contract differs from the previous session's (prior-day levels unusable)."""
    out, prev = [], None
    for r in daily:
        if prev and r["contract"] != prev:
            out.append(r["date"])
        prev = r["contract"]
    return frozenset(out)


_DEFAULT_ROLLS: dict = {}


def default_rolls(root: str = "NQ") -> frozenset:
    """The roll dates of the cached IN-SAMPLE daily bars (never builds, never reads a 2025+ row); empty if the
    cache is absent."""
    if root not in _DEFAULT_ROLLS:
        _DEFAULT_ROLLS[root] = rolls(load_daily(root, allow_holdout=False, build=False))
    return _DEFAULT_ROLLS[root]


# ---- fill law ---------------------------------------------------------------------------------------------
def to_tick(px: float, tick: float) -> float:
    return round(round(px / tick) * tick, 6)


def first_at_or_above(px: np.ndarray, level: float, a: int, b: int, eps: float) -> int:
    """First index k in [a, b) with px[k] >= level (tick-grid tolerant), else b."""
    lv = level - eps
    while a < b:
        e = a + CHUNK if a + CHUNK < b else b
        m = px[a:e] >= lv
        k = int(m.argmax())
        if m[k]:
            return a + k
        a = e
    return b


def first_at_or_below(px: np.ndarray, level: float, a: int, b: int, eps: float) -> int:
    """First index k in [a, b) with px[k] <= level (tick-grid tolerant), else b."""
    lv = level + eps
    while a < b:
        e = a + CHUNK if a + CHUNK < b else b
        m = px[a:e] <= lv
        k = int(m.argmax())
        if m[k]:
            return a + k
        a = e
    return b


class Costs:
    """Commission and the execution conventions of a run. The defaults ARE the tester's (the validated law):
    slippage 1 tick, latency = the strategy's own placement_ms (85), strict_limit off.
    latency_ms: overrides every strategy's placement_ms (sensitivity runs only).
    guard_ms: extra placement latency on top of either (set by the runner on the sessions of a month that failed
    the snapshot-phase check: EXEC_GUARD_MS; 0 everywhere else).
    strict_limit: a LIMIT entry's stop-loss is live ON the fill print, so a print that trades through the
    limit and is already at/through the stop is a stop-out (the tester arms the stop one print later)."""
    __slots__ = ("commission_rt", "slippage_ticks", "latency_ms", "strict_limit", "guard_ms")

    def __init__(self, commission_rt: float = 4.00, slippage_ticks: float = 1.0, latency_ms: int | None = None,
                 strict_limit: bool = False, guard_ms: int = 0):
        self.commission_rt, self.slippage_ticks = float(commission_rt), float(slippage_ticks)
        self.latency_ms = None if latency_ms is None else int(latency_ms)
        self.strict_limit = bool(strict_limit)
        self.guard_ms = int(guard_ms)              # ADDED to the placement latency (the runner's execution guard)
        if not self.slippage_ticks >= 0 or (self.latency_ms is not None and self.latency_ms < 0) or self.guard_ms < 0:
            raise ValueError("slippage_ticks, latency_ms and guard_ms must be >= 0")


class Order:
    __slots__ = ("id", "side", "kind", "price", "qty", "min_i", "role", "sl", "tp", "tp_rr", "ref", "oco",
                 "status", "pos", "fill_px", "fill_sl", "fill_tp", "fill_ms", "tag", "two")

    def __init__(self, id, side, kind, price, qty, min_i, role="entry", sl=None, tp=None, tp_rr=None, ref=None,
                 pos=None, tag=None):
        self.id, self.side, self.kind, self.price, self.qty, self.min_i = id, side, kind, price, qty, min_i
        self.role, self.sl, self.tp, self.tp_rr, self.ref, self.pos, self.tag = role, sl, tp, tp_rr, ref, pos, tag
        self.oco = None
        self.two = False                        # True: member of an OCO group that holds orders of BOTH sides
        self.status = "working"                 # working | filled | cancelled
        self.fill_px = self.fill_sl = self.fill_tp = self.fill_ms = None


class Position:
    __slots__ = ("side", "qty", "entry_px", "entry_i", "order_price", "sl", "tp", "tag", "oco")

    def __init__(self, side, qty, entry_px, entry_i, order_price, tag=None, oco=False):
        self.side, self.qty, self.entry_px, self.entry_i, self.order_price = side, qty, entry_px, entry_i, order_price
        self.sl = self.tp = None
        self.tag = tag
        self.oco = bool(oco)                    # the entry order was one leg of a two-sided OCO pair


class Bar:
    __slots__ = ("start_ns", "end_ns", "o", "h", "l", "c", "v")

    def __init__(self, start_ns, end_ns, o, h, l, c, v):
        self.start_ns, self.end_ns, self.o, self.h, self.l, self.c, self.v = start_ns, end_ns, o, h, l, c, v


class SessionResult:
    __slots__ = ("date", "trades", "skip", "both_sides")

    def __init__(self, date):
        self.date, self.trades, self.skip = date, [], None
        self.both_sides = False                 # entry orders of opposite sides were working at the same time (see _Sim)


class Features:
    """Per-minute feature table of ONE session with the timestamp law built in.
    `usable_ns` (ascending int64) = the first instant each row may be used (a row stamped for minute M is
    usable at the END of M). cols: name -> array aligned with usable_ns."""
    __slots__ = ("usable_ns", "cols")

    def __init__(self, usable_ns, cols: dict):
        self.usable_ns = np.ascontiguousarray(usable_ns, np.int64)
        if len(self.usable_ns) > 1 and (np.diff(self.usable_ns) < 0).any():
            raise ValueError("Features.usable_ns must be ascending")
        self.cols = {k: np.asarray(v) for k, v in cols.items()}
        for k, v in self.cols.items():
            if len(v) != len(self.usable_ns):
                raise ValueError(f"feature {k!r}: {len(v)} rows, expected {len(self.usable_ns)}")

    def n_usable(self, now_ns: int) -> int:
        return int(np.searchsorted(self.usable_ns, now_ns, side="right"))


def features_from_frame(df, columns=None) -> Features:
    """A pandas frame indexed by `usable_at` (tz-aware / naive-UTC datetimes, or int64 ns) -> Features.
    Only numeric / bool columns are kept."""
    idx = df.index
    if hasattr(idx, "asi8"):
        idx = idx.as_unit("ns") if hasattr(idx, "as_unit") else idx
        usable = idx.asi8
    else:
        usable = np.asarray(idx, np.int64)
    cols = {}
    for c in (columns or df.columns):
        v = df[c].to_numpy()
        if v.dtype.kind in "fiub":
            cols[c] = v
    return Features(usable, cols)


_FRAMES: dict = {}                                  # per-process cache of the data layer's table
# First ET date of the feature table = the evening BEFORE the first in-sample session (Globex opens 18:00 ET on
# 2021-09-21), so the first session gets its `lookback_min` evening rows like every other one.
TABLE_START = IN_SAMPLE[0] - dt.timedelta(days=1)


class L2Features:
    """Picklable `features=` loader for run(): one session's slice of the data layer's table
    (l2data.load_features, indexed by usable_at), from `lookback_min` minutes before 00:00 ET of the session
    date (for trailing windows) to the end of that ET day. Name the columns you need (memory: one copy of
    the in-sample table per worker). The holdout seal is l2data's own plus check_holdout here."""

    def __init__(self, columns, lookback_min: int = 360, allow_holdout: bool = False, mask_bad_book: bool = True):
        self.columns = tuple(columns)
        self.lookback_min, self.allow_holdout, self.mask = int(lookback_min), allow_holdout, mask_bad_book

    def _frame(self):
        key = (self.columns, self.allow_holdout, self.mask)
        if key not in _FRAMES:
            import l2data
            end = dt.date(2026, 12, 31) if self.allow_holdout else IN_SAMPLE[1]
            df = l2data.load_features(TABLE_START, end, allow_holdout=self.allow_holdout,
                                      columns=list(self.columns), mask_bad_book=self.mask)
            f = features_from_frame(df, self.columns)
            _FRAMES[key] = f
        return _FRAMES[key]

    def __call__(self, d) -> Features | None:
        d = _date(d)
        check_holdout(d, self.allow_holdout)
        f = self._frame()
        lo = et_ns(d, "00:00") - self.lookback_min * MIN_NS
        hi = et_ns(d + dt.timedelta(days=1), "00:00")
        a, b = np.searchsorted(f.usable_ns, [lo, hi], side="left")
        if b <= a:
            return None
        return Features(f.usable_ns[a:b], {k: v[a:b] for k, v in f.cols.items()})


def _back(v, what: str) -> int:
    """`v` as a non-negative int, else LookAheadError (bools and non-integers are refused too). The sign is
    tested on the plain int VALUE (int's own __index__ / a numpy int64 copy), never through the object's own
    comparison operators: an int subclass with a lying `<` cannot get a negative index past this."""
    i = None
    if not isinstance(v, bool) and isinstance(v, (int, np.integer)):
        i = int.__index__(v) if isinstance(v, int) else int(np.int64(v))
    if i is None or i < 0:
        raise LookAheadError(f"ctx.feat: {what} must be an integer >= 0, not {v!r} -- rows after the newest "
                             "usable one are not visible to a decision (timestamp law)")
    return i


class Ctx:
    """What a strategy sees (the tester's Ctx + guarded feature access). Created per session."""

    def __init__(self, sim: "_Sim", qty: int, daily: list, feat: Features | None = None):
        self._s = sim
        self.root = sim.root
        self.date = sim.date
        self.tick = sim.tick
        self.point_value = sim.pv
        self.qty = qty
        self.daily = daily
        self.move_brackets_to_fill = False
        self._feat = feat

    @property
    def now_ns(self) -> int:
        return self._s.now

    @property
    def last_price(self):
        """The last print strictly before the current event time (in the window)."""
        s = self._s
        return float(s.px[s.i - 1]) if s.i > s.lo else None

    @property
    def flat(self) -> bool:
        return not self._s.positions

    # -- orders
    def _entry(self, kind, side, price, qty, sl, tp, tp_rr, ref, tag) -> Order:
        if side not in SIDE:
            raise ValueError(f"side must be 'long' or 'short', not {side!r}")
        tick = self._s.tick
        price = None if price is None else to_tick(price, tick)
        sl = None if sl is None else to_tick(sl, tick)
        tp = None if tp is None else to_tick(tp, tick)
        return self._s.new_order(SIDE[side], kind, price, int(qty or self.qty), sl=sl, tp=tp, tp_rr=tp_rr,
                                 ref=ref, tag=tag)

    def stop_entry(self, side, price, qty=None, sl=None, tp=None, tp_rr=None, tag=None) -> Order:
        return self._entry("stop", side, price, qty, sl, tp, tp_rr, price, tag)

    def limit_entry(self, side, price, qty=None, sl=None, tp=None, tp_rr=None, tag=None) -> Order:
        return self._entry("limit", side, price, qty, sl, tp, tp_rr, price, tag)

    def market(self, side, qty=None, sl=None, tp=None, tp_rr=None, ref=None, tag=None) -> Order:
        return self._entry("market", side, None, qty, sl, tp, tp_rr, ref, tag)

    def oco(self, *orders: Order) -> None:
        g = orders[0].id
        two = len({o.side for o in orders}) > 1
        for o in orders:
            o.oco = g
            if two and hasattr(o, "two"):
                o.two = True

    def cancel(self, order: Order) -> None:
        self._s.cancel(order)

    def flatten(self, reason: str = "time") -> None:
        self._s.flatten(reason)

    def skip(self, reason: str) -> None:
        self._s.res.skip = reason

    def plot(self, *a, **k) -> None:            # tester-API compatibility: charts are not simulated
        pass

    def hline(self, name, price, role="level") -> dict:
        return {"name": name, "price": price, "role": role}

    # -- features (timestamp law enforced here)
    def feat_n(self) -> int:
        """Rows usable at the current decision time."""
        return 0 if self._feat is None else self._feat.n_usable(self._s.now)

    def feat(self, name: str, back: int = 0, default=None):
        """Feature `name` from the newest usable row (back=1: the one before, ...). None/default if absent.
        back must be an integer >= 0: a negative back would index rows that are not usable yet (the minute
        still forming and later) and raises LookAheadError."""
        back = _back(back, "back")
        f = self._feat
        if f is None:
            return default
        n = f.n_usable(self._s.now)
        k = n - 1 - back
        if k < 0:
            return default
        if k >= n:                                  # the timestamp law: only rows [0, n) exist for a strategy
            raise LookAheadError(f"ctx.feat: row {k} is not usable yet ({n} usable rows at this decision)")
        v = f.cols[name][k]
        return v.item() if hasattr(v, "item") else v

    def feat_window(self, name: str, n: int | None = None) -> np.ndarray:
        """The last n usable values of `name` (all usable rows if n is None), oldest first (a copy).
        n must be an integer >= 0 (0 -> empty); a negative n raises LookAheadError."""
        if n is not None:
            n = _back(n, "n")
        f = self._feat
        if f is None:
            return np.empty(0)
        k = f.n_usable(self._s.now)
        return f.cols[name][0 if n is None else max(0, k - n):k].copy()


class _Sim:
    def __init__(self, tape: Tape, lo: int, hi: int, costs: Costs, placement_ms: int):
        self.root, self.date = tape.root, tape.date
        self.ts, self.px, self.lo, self.hi = tape.ts, tape.px, lo, hi
        self.pv, self.tick = SPECS[tape.root]
        self.eps = self.tick * 1e-6
        self.slip = costs.slippage_ticks * self.tick
        self.comm = costs.commission_rt
        lat = getattr(costs, "latency_ms", None)
        self.place_ns = (int(placement_ms if lat is None else lat) + int(getattr(costs, "guard_ms", 0))) * 1_000_000
        self.strict_limit = bool(getattr(costs, "strict_limit", False))
        self.i = lo                              # next print to process
        self.now = 0
        self.orders: list = []                   # working, in creation order
        self.positions: list = []
        self.res = SessionResult(tape.date.isoformat())
        self._ids = 0
        self._ctx: Ctx | None = None
        self.both_sides = False                  # EVIDENCE for the Apex one-direction rule (see new_order)

    def _bisect(self, t: int) -> int:
        """bisect_left(ts, t, self.i, self.hi)"""
        return self.i + int(np.searchsorted(self.ts[self.i:self.hi], t, side="left"))

    # ---- orders
    def new_order(self, side, kind, price, qty, **kw) -> Order:
        """A new ENTRY order (SL / TP orders are made in _fill). If an entry order of the OPPOSITE side is still
        working, the session has worked orders on both sides at once (an OCO straddle / bracket entry, or two
        independent opposite entries): `both_sides` is set for the whole session and stamped on every trade
        row of it. Exits (a position's own SL / TP) never count."""
        self._ids += 1
        if any(x.role == "entry" and x.side != side for x in self.orders):
            self.both_sides = True
        o = Order(self._ids, side, kind, price, qty, self._bisect(self.now + self.place_ns), **kw)
        self.orders.append(o)
        return o

    def cancel(self, o: Order) -> None:
        if o.status == "working":
            o.status = "cancelled"
            self.orders.remove(o)

    def _trigger(self, o: Order, a: int, b: int) -> int:
        if o.kind == "market":
            return a
        if o.kind == "stop":
            return (first_at_or_above(self.px, o.price, a, b, self.eps) if o.side > 0
                    else first_at_or_below(self.px, o.price, a, b, self.eps))
        lvl = (to_tick(o.price - self.tick, self.tick) if o.side > 0
               else to_tick(o.price + self.tick, self.tick))
        return (first_at_or_below(self.px, lvl, a, b, self.eps) if o.side > 0
                else first_at_or_above(self.px, lvl, a, b, self.eps))

    def _fill_price(self, o: Order, p: float) -> float:
        if o.kind == "limit":
            return o.price
        if o.kind == "stop":
            raw = max(o.price, p) + self.slip if o.side > 0 else min(o.price, p) - self.slip
        else:
            raw = p + o.side * self.slip
        return to_tick(raw, self.tick)

    def advance(self, j: int) -> None:
        """Process prints [i, j): fill whatever triggers, earliest print first (ties: oldest order)."""
        while self.orders and self.i < j:
            best_k, best = j, None
            for o in self.orders:
                a = self.i if self.i > o.min_i else o.min_i
                if a >= best_k:
                    continue
                k = self._trigger(o, a, best_k)
                if k < best_k:
                    best_k, best = k, o
            if best is None:
                break
            self._fill(best, best_k)
            self.i = best_k                       # other orders may still trigger on this same print
        if j > self.i:
            self.i = j

    def _fill(self, o: Order, k: int) -> None:
        fill = self._fill_price(o, float(self.px[k]))
        o.status = "filled"
        self.orders.remove(o)
        if o.role != "entry":
            self._close(o.pos, fill, k, o.role)
            return
        if o.oco is not None:
            for x in [x for x in self.orders if x.oco == o.oco]:
                self.cancel(x)
        pos = Position(o.side, o.qty, fill, k, o.price, o.tag, o.two)
        sl, tp = o.sl, o.tp
        # the SL moves first (keeping its distance to `ref`); only then is a tp_rr target derived
        if self._ctx.move_brackets_to_fill and o.ref is not None:
            d = fill - o.ref
            sl = None if sl is None else to_tick(sl + d, self.tick)
            if o.tp_rr is None:
                tp = None if tp is None else to_tick(tp + d, self.tick)
        if o.tp_rr is not None and sl is not None:
            tp = to_tick(fill + o.side * o.tp_rr * abs(fill - sl), self.tick)
        self._ids += 1
        if sl is not None:
            # tester law: the SL is live from the print AFTER the entry print. strict_limit: a limit entry's
            # SL is live ON the fill print (a fill print already through the stop is a stop-out, not a hold)
            live = k if (self.strict_limit and o.kind == "limit") else k + 1
            pos.sl = Order(self._ids, -o.side, "stop", sl, o.qty, live, role="sl", pos=pos)
            self.orders.append(pos.sl)
        self._ids += 1
        if tp is not None:
            pos.tp = Order(self._ids, -o.side, "limit", tp, o.qty, k + 1, role="tp", pos=pos)
            self.orders.append(pos.tp)
        o.fill_px, o.fill_sl, o.fill_tp = fill, sl, tp
        o.fill_ms = int(self.ts[k]) // 1_000_000
        self.positions.append(pos)

    def _close(self, pos: Position, fill: float, k: int, reason: str) -> None:
        for x in (pos.sl, pos.tp):
            if x is not None:
                self.cancel(x)
        self.positions.remove(pos)
        seg = self.px[pos.entry_i:k + 1]
        hi, lo = float(seg.max()), float(seg.min())
        s, e = pos.side, pos.entry_px
        mfe = max(0.0, (hi - e) if s > 0 else (e - lo))
        mae = max(0.0, (e - lo) if s > 0 else (hi - e))
        gross = s * (fill - e) * self.pv * pos.qty
        comm = self.comm * pos.qty
        t0, t1 = int(self.ts[pos.entry_i]), int(self.ts[k])
        tr = {"date": self.res.date, "side": NAME[s], "qty": pos.qty,
              "entry_price": e, "exit_price": fill, "exit_reason": reason,
              "order_price": pos.order_price,
              "sl": pos.sl.price if pos.sl else None, "tp": pos.tp.price if pos.tp else None,
              "gross": round(gross, 2), "commission": round(comm, 2), "net": round(gross - comm, 2),
              "mae_pts": round(mae, 6), "mfe_pts": round(mfe, 6),
              "mae_usd": round(mae * self.pv * pos.qty, 2), "mfe_usd": round(mfe * self.pv * pos.qty, 2),
              "bars": int(t1 // MIN_NS - t0 // MIN_NS + 1), "seconds": round((t1 - t0) / 1e9, 3),
              "entry_ms": t0 // 1_000_000, "exit_ms": t1 // 1_000_000,
              "entry_ns": t0, "exit_ns": t1,
              "oco": pos.oco, "both_sides": None}       # both_sides is stamped at the end of the session
        if pos.tag is not None:
            tr["tag"] = pos.tag
        self.res.trades.append(tr)

    def flatten(self, reason: str) -> None:
        for o in list(self.orders):
            if o.role == "entry":
                self.cancel(o)
        if not self.positions:
            return
        k = self.i if self.i < self.hi else self.hi - 1
        if k < self.i:
            reason = "eod"
        for pos in list(self.positions):
            self._close(pos, to_tick(float(self.px[k]) - pos.side * self.slip, self.tick), k, reason)


def build_bars(ts, px, size, lo: int, hi: int, t0: int, t1: int, minutes: int) -> list:
    """Time bars from prints [lo, hi), aligned to multiples of `minutes` in epoch time, covering [t0, t1).
    Empty buckets make no bar (the tester's build_bars, vectorised)."""
    step = minutes * MIN_NS
    b0 = t0 - t0 % step
    end = -(-t1 // step) * step                          # the last bar may run past t1 to its own close
    i0 = lo + int(np.searchsorted(ts[lo:hi], b0, side="left"))
    i1 = lo + int(np.searchsorted(ts[lo:hi], end, side="left"))
    if i1 <= i0:
        return []
    k = ts[i0:i1] // step
    st = np.flatnonzero(np.concatenate(([True], k[1:] != k[:-1])))
    seg = px[i0:i1]
    en = np.concatenate((st[1:], [i1 - i0]))
    o = seg[st].tolist()
    c = seg[en - 1].tolist()
    h = np.maximum.reduceat(seg, st).tolist()
    l = np.minimum.reduceat(seg, st).tolist()
    v = np.add.reduceat(size[i0:i1], st).tolist()
    b = (k[st] * step).tolist()
    return [Bar(b[n], b[n] + step, o[n], h[n], l[n], c[n], v[n]) for n in range(len(b))]


# ---- strategy contract (the tester's) ---------------------------------------------------------------------
def resolve_inputs(defaults: dict, schema: dict, values: dict | None) -> dict:
    """The tester's resolve_inputs (homebase/strategies/base.py) for DEFAULTS + SCHEMA: defaults overlaid with
    `values`, every value checked and coerced, never clamped. ValueError (naming the key) on an unknown key,
    a wrong type, a value that is not one of the choices or is outside [min, max].
    schema[key] = ("choice", (a, b, ...)) | ("int", min, max) | ("float", min, max) | ("bool",) | ("str",);
    min / max may be None. A key without a schema entry is typed by its default: bool -> bool, int -> whole
    number, float -> number, str -> str (anything else is passed through unchecked)."""
    values = dict(values or {})
    unknown = sorted(set(values) - set(defaults))
    if unknown:
        raise ValueError(f"unknown input(s): {', '.join(unknown)}")
    stray = sorted(set(schema) - set(defaults))
    if stray:
        raise ValueError(f"SCHEMA names input(s) without a default: {', '.join(stray)}")
    out: dict = {}
    for key, dflt in defaults.items():
        v = values.get(key, dflt)
        spec = schema.get(key)
        if spec is None:
            spec = (("bool",) if isinstance(dflt, bool) else ("int", None, None) if isinstance(dflt, int)
                    else ("float", None, None) if isinstance(dflt, float) else ("str",) if isinstance(dflt, str)
                    else ("any",))
        kind = spec[0]
        if kind == "bool":
            if not isinstance(v, bool):
                raise ValueError(f"{key}: expected true/false")
        elif kind == "choice":
            if isinstance(v, bool) or v not in spec[1]:
                raise ValueError(f"{key}: one of {', '.join(map(str, spec[1]))} (got {v!r})")
        elif kind == "str":
            if not isinstance(v, str):
                raise ValueError(f"{key}: expected a string")
        elif kind in ("int", "float"):
            if isinstance(v, bool) or not isinstance(v, (int, float, np.integer, np.floating)):
                raise ValueError(f"{key}: expected a number")
            if kind == "int":
                if float(v) != int(v):
                    raise ValueError(f"{key}: expected a whole number")
                v = int(v)
            else:
                v = float(v)
            lo, hi = (tuple(spec[1:3]) + (None, None))[:2]
            if v != v or (lo is not None and v < lo) or (hi is not None and v > hi):
                raise ValueError(f"{key}: must be within [{lo}, {hi}]")
        elif kind != "any":
            raise ValueError(f"{key}: unknown input type {kind!r}")
        out[key] = v
    return out


class Strategy:
    """Same contract as homebase.strategies.base.Strategy. Subclasses: on_session / on_bar / on_time, times().
    `DEFAULTS` = {input key: default} and `SCHEMA` = {input key: type spec} (both merged over the MRO) stand
    for the tester's inputs(); params are validated and coerced by resolve_inputs (bad value -> ValueError)."""
    root = "NQ"
    session_window = ("00:00", "16:10")       # ET [start, end)
    bar_minutes = 1                            # on_bar gets bars of this size (0 = none)
    bar_window = None
    placement_ms = 85                          # the tester's measured order-placement latency
    # As the tester (opt-in): True = every session is independent, ALL state resets in on_session and anything
    # older comes from ctx.daily. Only then may run() split the days over worker processes (each chunk gets
    # its own instance); False = one instance sees every day in order, in one process.
    session_independent = False
    DEFAULTS: dict = {}
    SCHEMA: dict = {}

    def __init__(self, params: dict | None = None):
        self.p = resolve_inputs(self.defaults(), self.schema(), params)

    @classmethod
    def defaults(cls) -> dict:
        out: dict = {}
        for k in reversed(cls.__mro__):
            out.update(getattr(k, "DEFAULTS", {}))
        return out

    @classmethod
    def schema(cls) -> dict:
        out: dict = {}
        for k in reversed(cls.__mro__):
            out.update(getattr(k, "SCHEMA", {}))
        return out

    def times(self) -> list:
        return []

    def trades_on(self, d: dt.date) -> bool:
        return True

    def needs_daily(self) -> bool:
        return False

    def on_session(self, ctx) -> None:
        pass

    def on_time(self, ctx, et_time: str) -> None:
        pass

    def on_bar(self, ctx, bar) -> None:
        pass


def _fatal(e: BaseException) -> bool:
    """Exceptions that must abort a run instead of costing one session: the holdout seal (ours and the data
    layer's), a look-ahead attempt, memory."""
    return (isinstance(e, (HoldoutSealed, LookAheadError, PermissionError, MemoryError))
            or any(c.__name__ == "HoldoutSealed" for c in type(e).__mro__))


def run_session(strategy, tape: Tape, costs: Costs | None = None, qty: int = 1, daily: list | None = None,
                features: Features | None = None, window: tuple | None = None,
                on_error: str = "skip") -> SessionResult:
    """Replay one session's tape through one strategy instance (the tester's run_session).
    A callback that raises: on_error="skip" (the tester's rule) cancels every working order, flattens at the
    current print, DROPS the session's trades and returns skip="strategy error: ..."; "raise" propagates."""
    costs = costs or Costs()
    d = tape.date
    if daily and hasattr(strategy, "ROLLS"):
        # a roll day the strategy's roll list does not know (run_session called directly, or a date outside
        # the cached list): the prior daily bar is another contract -> the prior-day levels are unusable
        prev = daily[-1].get("contract")
        if prev and tape.contract and prev != tape.contract and d.isoformat() not in strategy.ROLLS:
            strategy.ROLLS = frozenset(strategy.ROLLS) | {d.isoformat()}
    w0, w1 = window or strategy.session_window
    t0, t1 = et_ns(d, w0), et_ns(d, w1)
    ts, px = tape.ts, tape.px
    lo, hi = int(np.searchsorted(ts, t0, side="left")), int(np.searchsorted(ts, t1, side="left"))
    sim = _Sim(tape, lo, hi, costs, strategy.placement_ms)
    ctx = sim._ctx = Ctx(sim, qty, daily or [], features)
    events: list = [(t0, 0, 0, "session", None)]
    if strategy.bar_minutes:
        b0, b1 = strategy.bar_window or (w0, w1)
        key = (lo, hi, et_ns(d, b0), et_ns(d, b1), strategy.bar_minutes)
        bars = tape._bars.get(key)
        if bars is None:
            bars = tape._bars[key] = build_bars(ts, px, tape.size, *key)
        for n, b in enumerate(bars):
            events.append((b.end_ns, 1, n, "bar", b))
    for n, t in enumerate(strategy.times()):
        events.append((et_ns(d, t), 2, n, "time", t))
    events.sort(key=lambda e: e[:3])
    for t, _, _, kind, arg in events:
        if t >= t1:
            break
        sim.advance(sim._bisect(t))
        sim.now = t
        try:
            if kind == "session":
                strategy.on_session(ctx)
            elif kind == "bar":
                strategy.on_bar(ctx, arg)
            else:
                strategy.on_time(ctx, arg)
        except Exception as e:                      # noqa: BLE001 - one bad session, not a crashed run (tester)
            if on_error != "skip" or _fatal(e):
                raise
            sim.flatten("strategy error")          # nothing keeps trading; the whole session is dropped
            sim.res.trades = []
            sim.res.skip = f"strategy error: {type(e).__name__}: {e}"
            sim.res.both_sides = sim.both_sides
            return sim.res
    sim.advance(hi)
    sim.i = hi
    sim.flatten("eod")
    sim.res.both_sides = sim.both_sides
    for t in sim.res.trades:                        # Apex one-direction evidence, on every row of the session:
        t["both_sides"] = sim.both_sides            # opposite-side entry orders were working at the same time
    return sim.res


# ---- the shared template (R/template.py, re-implemented for l2sim) ----------------------------------------
SESS = {"asia": (0, 10800), "london": (10800, 30300), "nyam": (34200, 39600),
        "mid": (39600, 48600), "pm": (48600, 57480), "news": (30570, 32400),
        "fomc": (50370, 52200)}                # seconds after 00:00 ET; news 08:29:30-09:00, fomc 13:59:30-14:30
ORDER = ("asia", "london", "nyam", "mid", "pm")


def _hms(s: int) -> str:
    return "%02d:%02d:%02d" % (s // 3600, s % 3600 // 60, s % 60)


def _sec(t: str) -> int:
    p = [int(x) for x in t.split(":")]
    return p[0] * 3600 + p[1] * 60 + (p[2] if len(p) > 2 else 0)


def _sid_at(s: int):
    for k in ORDER:
        if SESS[k][0] <= s < SESS[k][1]:
            return k
    return None


def _tagkw(tag) -> dict:
    """`tag=` only when set: an untagged Template then also runs on the tester's own Ctx (differential tests)."""
    return {} if tag is None else {"tag": tag}


def session_of(entry_ms: int) -> str | None:
    """Session key of a trade by its ET entry minute (the offline split, as R/evalcore.load)."""
    a = dt.datetime.fromtimestamp(entry_ms / 1000, ET)
    return _sid_at(a.hour * 3600 + a.minute * 60)


class Template(Strategy):
    """The pilot's common strategy shape (R/SPEC.md "The shared template"), same semantics as the tester
    drafts pp_<fam>: 1-minute engine bars aggregated into tf bars aligned to ET clock multiples of tf; a
    signal is evaluated ONLY at a tf-bar close on completed bars; indicators run over every tf bar since
    00:00 ET and reset daily; session objects reset at each session start; sess=all trades each session
    independently, flat at each session end, entries cancelled and none placed in the last 5 minutes; one
    position at a time; max_tr entries per session. Stops: atr | pts | struct (floored at 0.25 ATR). Target
    = tgt_r x stop distance. trail_atr / exit_bars are close-based market exits.
    Filters (all default off, applied to every entry in `allowed`): f_trend, f_vwap (R's) and f_depth = SPEC B6
    depth_regime: off | thin | thick -- an entry is allowed only while the newest usable `depth10_rel20d` row
    (ctx.feat, the decision's own minute) is thin (depth <= 0.8 x its 20-session same-minute median) / thick
    (>= 1.2 x); a missing value blocks the entry. Needs features=L2Features([..., "depth10_rel20d"]).
    Family hooks: fam_filter, sess_on, fam_day, fam_session, fam_update, fam_signal, fam_times, fam_time."""
    DEFAULTS = {"tf": "5", "sess": "all", "dir": "both", "stop_mode": "atr", "stop_val": 1.5, "tgt_r": 2.0,
                "trail_atr": 0.0, "exit_bars": 0, "max_tr": 3, "f_trend": "off", "f_vwap": "off", "f_depth": "off"}
    SCHEMA = {"tf": ("choice", ("1", "5", "15", "30")),                    # the tester drafts' inputs (R/gen_drafts COMMON)
              "sess": ("choice", ("all", "asia", "london", "nyam", "mid", "pm")),
              "dir": ("choice", ("both", "long", "short")), "stop_mode": ("choice", ("atr", "pts", "struct")),
              "stop_val": ("float", 0.1, 1000), "tgt_r": ("float", 0, 20), "trail_atr": ("float", 0, 10),
              "exit_bars": ("int", 0, 500), "max_tr": ("int", 1, 20),
              "f_trend": ("choice", ("off", "with", "against")), "f_vwap": ("choice", ("off", "with", "against")),
              "f_depth": ("choice", ("off", "thin", "thick"))}                 # NEW in l2sim (SPEC B6), not a tester input
    session_independent = True                 # every bit of state is reset in on_session (as the pp_* drafts)
    SPANS = ()                                 # extra EMA spans the family reads as self.E[span]
    WARM = 3                                   # min tf bars since 00:00 before any entry

    @property
    def ROLLS(self) -> frozenset:
        """Contract-roll session dates (prior-day levels unusable). The runner sets the roll list of its own
        daily bars; unset (run_session called directly) = the cached in-sample list, which equals the list
        embedded in the tester drafts. run_session also adds a roll day it detects from `daily`."""
        r = self.__dict__.get("_rolls")
        return default_rolls(self.root) if r is None else r

    @ROLLS.setter
    def ROLLS(self, v) -> None:
        self.__dict__["_rolls"] = frozenset(v)

    # ---- family hooks (defaults)
    def fam_filter(self, ids):
        return ids

    def sess_on(self, s):
        return True

    def fam_day(self, ctx):
        pass

    def fam_session(self, ctx, s):
        pass

    def fam_update(self, ctx):
        pass

    def fam_signal(self, ctx):
        pass

    def fam_times(self):
        return []

    def fam_time(self, ctx, sec):
        pass

    # ---- schedule
    def sessions(self):
        s = self.p["sess"]
        return self.fam_filter(list(ORDER) if s == "all" else [s])

    def needs_daily(self):
        return True

    def times(self):
        ts = set(self.fam_times())
        for s in self.sessions():
            a, b = SESS[s]
            ts.update((_hms(a), _hms(b), _hms(b - 300)))
        return sorted(ts)

    def on_session(self, ctx):
        self._cx = ctx                             # for `allowed` (f_depth reads ctx.feat at the decision)
        self.t0 = ctx.now_ns                       # ET midnight of the session date
        self.day = ctx.date.isoformat()
        self.held = 0                              # tf closes since the current position filled
        self.tf = int(self.p["tf"])
        self.step = self.tf * 60 * NS
        self.spans = sorted(set(self.SPANS) | {50})
        self.O, self.H, self.L, self.C, self.V, self.TR = [], [], [], [], [], []
        self.nb = 0
        self.atr = self.atr_p = None
        self.E, self.Ep = {}, {}
        self.cur = None
        self.M = []                                # completed 1m bars: (start_sec, o, h, l, c, v)
        self.vs, self.vr, self.vsid = [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], None
        self.sid, self.sn, self.n_ent = None, 0, 0
        self.orders = []                           # [order, expires_at_nb | None, counted]
        self.fill_ns, self.side, self.best = None, 0, 0.0
        self.onh = self.onl = None
        self.dl = ctx.daily
        d1 = self.dl[-1] if self.dl else None
        # prior-day levels are unusable on a contract-roll day (the prior bar is the old contract)
        self.pdh, self.pdl, self.pdc = ((d1["h"], d1["l"], d1["c"]) if d1 and self.day not in self.ROLLS
                                        else (None, None, None))
        self._datr = None
        self.fam_day(ctx)

    def on_time(self, ctx, et_time):
        sec = _sec(et_time)
        self._sync(ctx)
        acts = [s for s in self.sessions() if self.sess_on(s)]
        for s in acts:
            a, b = SESS[s]
            if sec == b:
                ctx.flatten("time")
                self.orders, self.sid = [], None
            elif sec == b - 300 and self.sid == s:
                self._cancel(ctx)
        for s in acts:
            if sec == SESS[s][0]:
                self._start(ctx, s)
        self.fam_time(ctx, sec)

    def _start(self, ctx, s):
        self.sid, self.sn, self.n_ent, self.orders, self.fill_ns = s, 0, 0, [], None
        cut = 10800 if s == "london" else 34200 if s in ("nyam", "mid", "pm") else None
        r = self.rng(0, cut) if cut else None
        self.onh, self.onl = r if r else (None, None)
        self.fam_session(ctx, s)

    def _cancel(self, ctx):
        for r in self.orders:
            if r[0].status == "working":
                ctx.cancel(r[0])
        self.orders = []

    # ---- bars
    def on_bar(self, ctx, bar):
        k = bar.start_ns // self.step
        if self.cur is not None and self.cur[0] != k:
            self._close(ctx)                        # the bucket's last minute had no print
        s = (bar.start_ns - self.t0) // NS
        self.M.append((s, bar.o, bar.h, bar.l, bar.c, bar.v))
        sid = _sid_at(s)
        if sid != self.vsid:
            self.vsid = sid
            self.vs = [0.0, 0.0, 0.0]
            if sid in ("asia", "london", "nyam"):
                self.vr = [0.0, 0.0, 0.0]          # rth anchor: 00:00 / 03:00 / 09:30
        if sid and bar.v > 0:
            v, tp = bar.v, (bar.h + bar.l + bar.c) / 3.0
            for a in (self.vs, self.vr):
                a[0] += v
                a[1] += v * tp
                a[2] += v * tp * tp
        cur = self.cur
        if cur is None:
            self.cur = [k, bar.o, bar.h, bar.l, bar.c, bar.v]
        else:
            if bar.h > cur[2]:
                cur[2] = bar.h
            if bar.l < cur[3]:
                cur[3] = bar.l
            cur[4] = bar.c
            cur[5] += bar.v
        if bar.end_ns % self.step == 0:
            self._close(ctx)

    def _close(self, ctx):
        k, o, h, l, c, v = self.cur
        self.cur = None
        end = ((k + 1) * self.step - self.t0) // NS          # nominal close (a late close never counts as in-session)
        n = self.nb
        tr = h - l if n == 0 else max(h - l, abs(h - self.C[-1]), abs(l - self.C[-1]))
        self.O.append(o)
        self.H.append(h)
        self.L.append(l)
        self.C.append(c)
        self.V.append(v)
        self.TR.append(tr)
        self.nb = n = n + 1
        self.atr_p = self.atr
        self.atr = sum(self.TR) / n if n <= 14 else (self.atr * 13.0 + tr) / 14.0
        for sp in self.spans:
            e = self.E.get(sp)
            self.Ep[sp] = e
            self.E[sp] = c if e is None else e + 2.0 / (sp + 1) * (c - e)
        s = self.sid
        inn = s is not None and SESS[s][0] < end <= SESS[s][1]
        if inn:
            self.sn += 1
        self.fam_update(ctx)
        if self._manage(ctx) or not inn:
            return
        if self.can_enter(ctx):
            self.fam_signal(ctx)

    # ---- state / gating
    def _sync(self, ctx):
        for r in self.orders:
            o = r[0]
            if o.status == "filled" and not r[2]:
                r[2] = True
                self.n_ent += 1
                self.side, self.best, self.held = o.side, o.fill_px, 0
                self.fill_ns = o.fill_ms * 1_000_000
        if ctx.flat:
            self.fill_ns = None
        self.orders = [r for r in self.orders if r[0].status == "working"]

    def _manage(self, ctx):
        """Expire stale pending orders, then the close-based exits. True = flattened this close."""
        self._sync(ctx)
        for r in self.orders:
            if r[1] is not None and self.nb >= r[1]:
                ctx.cancel(r[0])
        if ctx.flat or self.fill_ns is None or ctx.now_ns <= self.fill_ns:
            return False
        c, sd = self.C[-1], self.side
        self.best = max(self.best, c) if sd > 0 else min(self.best, c)
        self.held += 1
        tr, eb = self.p["trail_atr"], self.p["exit_bars"]
        if tr > 0 and self.atr and (self.best - c) * sd > tr * self.atr:
            ctx.flatten("trail")
            return True
        if eb and self.held >= eb:
            ctx.flatten("bars")
            return True
        return False

    def can_enter(self, ctx):
        self._sync(ctx)
        if self.sid is None or self.atr is None or self.nb < self.WARM:
            return False
        if not ctx.flat or self.orders or self.n_ent >= self.p["max_tr"]:
            return False
        return ctx.now_ns - self.t0 < (SESS[self.sid][1] - 300) * NS

    def allowed(self, side):
        d = self.p["dir"]
        if d != "both" and d != side:
            return False
        sd = 1 if side == "long" else -1
        fd = self.p["f_depth"]
        if fd != "off" and depth_regime(self._cx.feat(DEPTH_COL)) != fd:
            return False
        ft = self.p["f_trend"]
        if ft != "off":
            e, ep = self.E[50], self.Ep[50]
            if ep is None or (e - ep) * sd * (1 if ft == "with" else -1) <= 0:
                return False
        fv = self.p["f_vwap"]
        if fv != "off":
            w = self.vw()
            if w is None or (self.C[-1] - w[0]) * sd * (1 if fv == "with" else -1) <= 0:
                return False
        return True

    # ---- data helpers for families
    def vw(self):
        """(session VWAP, volume-weighted stdev of typical price) or None."""
        return self._vw(self.vs)

    def vwr(self):
        """Same, anchored at the rth anchor (00:00 asia, 03:00 london, 09:30 NY sessions)."""
        return self._vw(self.vr)

    @staticmethod
    def _vw(a):
        if a[0] <= 0:
            return None
        m = a[1] / a[0]
        return m, math.sqrt(max(a[2] / a[0] - m * m, 0.0))

    def rng(self, a, b):
        """(high, low) of completed 1m bars inside [a, b) seconds after 00:00 ET, or None."""
        xs = [m for m in self.M if a <= m[0] and m[0] + 60 <= b]
        return (max(m[2] for m in xs), min(m[3] for m in xs)) if xs else None

    def mo(self, a):
        """Open of the first 1m bar starting at/after second a."""
        return next((m[1] for m in self.M if m[0] >= a), None)

    def mc(self, a, b):
        """Close of the last 1m bar starting inside [a, b)."""
        xs = [m[4] for m in self.M if a <= m[0] < b]
        return xs[-1] if xs else None

    def datr(self):
        """Wilder ATR(14) of the daily bars before today."""
        if self._datr is None and len(self.dl) >= 15:
            dl = self.dl
            trs = [max(dl[i]["h"] - dl[i]["l"], abs(dl[i]["h"] - dl[i - 1]["c"]),
                       abs(dl[i]["l"] - dl[i - 1]["c"])) for i in range(1, len(dl))]
            a = sum(trs[:14]) / 14.0
            for x in trs[14:]:
                a = (a * 13.0 + x) / 14.0
            self._datr = a
        return self._datr

    # ---- orders
    def _dist(self, ctx, ref, struct):
        m, a = self.p["stop_mode"], self.atr
        if m == "pts":
            d = self.p["stop_val"]
        elif m == "struct" and struct is not None:
            d = max(abs(ref - struct), 0.25 * a)
        else:
            d = self.p["stop_val"] * a
        return max(d, 2 * ctx.tick)

    def _tp(self, sd, ref, d, tp_px):
        if tp_px is not None:
            return tp_px if (tp_px - ref) * sd > 0 else None
        r = self.p["tgt_r"]
        return ref + sd * r * d if r > 0 else None

    def _mkt(self, ctx, side, struct=None, tp_px=None, ref=None, tag=None):
        """Market entry at the signal close (or `ref`), brackets re-priced to the fill."""
        if not self.allowed(side):
            return None
        sd = 1 if side == "long" else -1
        ref = self.C[-1] if ref is None else ref
        if tp_px is not None and (tp_px - ref) * sd < 2 * ctx.tick:
            return None                             # the target is already reached / behind us: no trade
        d = self._dist(ctx, ref, struct)
        ctx.move_brackets_to_fill = True
        o = ctx.market(side, sl=ref - sd * d, tp=self._tp(sd, ref, d, tp_px), ref=ref, **_tagkw(tag))
        self.orders.append([o, None, False])
        return o

    def _arm(self, ctx, legs, ttl=None, imm=False, tag=None):
        """Resting stop entries [(side, price, struct, tp_px)], OCO when two. A leg whose level is already
        through the last print is skipped (it would fill at once) unless imm. ttl = tf bars it lives."""
        lp = ctx.last_price
        if lp is None:
            return []
        os_ = []
        for side, px, struct, tp_px in legs:
            sd = 1 if side == "long" else -1
            if not self.allowed(side) or (not imm and (px - lp) * sd <= 0):
                continue
            d = self._dist(ctx, px, struct)
            ctx.move_brackets_to_fill = True
            os_.append(ctx.stop_entry(side, px, sl=px - sd * d, tp=self._tp(sd, px, d, tp_px), **_tagkw(tag)))
        if len(os_) == 2:
            ctx.oco(*os_)
        exp = self.nb + ttl if ttl else None
        self.orders += [[o, exp, False] for o in os_]
        return os_

    def _lim(self, ctx, side, px, struct=None, tp_px=None, ttl=None, tag=None):
        """Resting LIMIT entry at px (fills only on a 1-tick trade-through, at px). Skipped when px is not
        on the passive side of the last print. NEW in l2sim (not in R/template.py): for B4 wall_bounce.
        The stop is armed one print AFTER the fill print (tester law): check result["unrealistic_winners"]
        and re-run with strict_limit=True when the stop is tight (SIM_VALIDATION.md, open risk 4)."""
        lp = ctx.last_price
        if lp is None or not self.allowed(side):
            return None
        sd = 1 if side == "long" else -1
        if (lp - px) * sd <= 0:
            return None
        d = self._dist(ctx, px, struct)
        o = ctx.limit_entry(side, px, sl=px - sd * d, tp=self._tp(sd, px, d, tp_px), **_tagkw(tag))
        self.orders.append([o, self.nb + ttl if ttl else None, False])
        return o


# ---- runner -----------------------------------------------------------------------------------------------
def _run_days(job):
    """Worker: every spec (cls, params) on every day of the chunk; ONE tape / feature load per day.
    -> per spec {"trades", "skipped", "no_trade", "sessions", "both_sides", "guarded"}."""
    from bisect import bisect_left
    specs, root, days, costs, qty, allow_holdout, daily, roll_set, feat_loader, keep_ns = job[:10]
    on_error = job[10] if len(job) > 10 else "skip"
    guard_months = job[11] if len(job) > 11 else frozenset()
    costs_guard = Costs(costs.commission_rt, costs.slippage_ticks, costs.latency_ms, costs.strict_limit,
                        costs.guard_ms + EXEC_GUARD_MS) if guard_months else costs
    strats = []
    for cls, params in specs:
        st = cls(params)
        if roll_set is not None and hasattr(st, "ROLLS"):
            st.ROLLS = roll_set
        strats.append(st)
    dates = [r["date"] for r in daily] if daily else []
    out = [{"trades": [], "skipped": [], "no_trade": [], "sessions": 0, "both_sides": 0, "guarded": 0} for _ in specs]
    for iso in days:
        wait_compute_window()
        d = dt.date.fromisoformat(iso)
        check_holdout(d, allow_holdout)
        active = [k for k, st in enumerate(strats) if st.trades_on(d)]
        if not active:
            continue
        tape = load_tape(d, root, allow_holdout=allow_holdout)
        feats = feat_loader(d) if feat_loader is not None and tape is not None else None
        prior = daily[:bisect_left(dates, iso)] if daily else []
        gaps_of: dict = {}
        guarded = iso[:7] in guard_months            # a month that failed the snapshot-phase check: + 1 s placement
        for k in active:
            st, o = strats[k], out[k]
            trades, skipped, no_trade = o["trades"], o["skipped"], o["no_trade"]
            o["sessions"] += 1
            if tape is None or len(tape.ts) == 0:
                skipped.append({"date": iso, "reason": "no tape"})
                continue
            window = effective_session_window(d, tuple(type(st).session_window))
            if window not in gaps_of:
                gaps_of[window] = missing_hours(tape.ts, d, window)
            if gaps_of[window]:
                skipped.append({"date": iso, "reason": "missing " + ", ".join(
                    f"{a}–{b}" for a, b in gaps_of[window]) + " ET"})
                continue
            res = run_session(st, tape, costs_guard if guarded else costs, qty=qty,
                              daily=prior if st.needs_daily() else [], features=feats, window=window, on_error=on_error)
            o["both_sides"] += bool(res.both_sides)
            o["guarded"] += guarded
            for t in res.trades:
                t["_k"] = (t["exit_ns"], t["entry_ns"]) if keep_ns else (t.pop("exit_ns"), t.pop("entry_ns"))
            trades += res.trades
            if res.skip:
                no_trade.append({"date": iso, "reason": res.skip})
    return out


ERROR_PREFIX = "strategy error"                    # no_trade reasons that are crashes (the tester's HOLE_REASONS[0])


def pool_usable() -> bool:
    """Can worker processes be started? 'spawn' workers re-run the parent's main module FROM ITS FILE: a script fed on
    stdin (`python - <<EOF`) has none, every worker dies while starting and the pool respawns them for ever (a job that
    hangs at full CPU). True when the main module has no file (`python -c`, an interactive session) or the file exists."""
    f = getattr(sys.modules.get("__main__"), "__file__", None)
    return f is None or os.path.exists(f)


def unrealistic_winners(trades: list, tick: float = 0.25, limit_only: bool = True) -> list:
    """Trades booked as TARGET wins although a print reached the stop: exit_reason 'tp' with mae_pts >= the
    stop distance |entry_price - sl|. Under the tester's law the stop is armed one print AFTER the entry
    print, so this can only be the fill print itself already trading at/through the stop -- live, a loser.
    It happens to LIMIT entries with tight stops (B4 wall_bounce). limit_only keeps the limit entries (filled
    exactly at order_price; a stop entry pays >= 1 tick of slip, a market entry has no order_price -- so run
    with slippage > 0 for this test to be exact). A family with more than a handful of these must be re-run
    with strict_limit=True and judged on that result."""
    out = []
    for t in trades:
        if t.get("exit_reason") != "tp" or t.get("sl") is None:
            continue
        if t["mae_pts"] < abs(t["entry_price"] - t["sl"]) - tick * 1e-6:
            continue
        if limit_only and t.get("order_price") != t["entry_price"]:
            continue
        out.append(t)
    return out


def run_many(specs: list, start=IN_SAMPLE[0], end=IN_SAMPLE[1], *, root: str = "NQ", workers: int = MAX_WORKERS,
             costs: Costs | None = None, qty: int = 1, allow_holdout: bool = False, features=None,
             days: list | None = None, keep_ns: bool = False, slip_ticks: float | None = None,
             latency_ms: int | None = None, strict_limit: bool | None = None, on_error: str = "skip") -> list:
    """Run several (strategy class, params) specs in ONE pass over the tapes (a grid: each session's tape,
    bars and features are loaded once and shared by every cell). Returns one result dict per spec, in order:
    {"trades": [...R trades.json schema...], "skipped": [...], "no_trade": [...], "sessions": n, "used": n,
    "skipped_by_error": n, "unrealistic_winners": n, "elapsed_s": s (the whole pass), "meta": {...}}; trades
    sorted by (exit, entry) like a tester bundle.
    `features`: optional picklable callable date -> Features | None (e.g. L2Features([...])).
    SENSITIVITY (defaults = the tester's validated law; any change is recorded in meta and meta["stress"]):
      slip_ticks   slippage of market / stop / flatten fills in ticks (tester 1; stress 2)
      latency_ms   order-placement latency for every spec (tester: the strategy's placement_ms = 85; stress 250)
      strict_limit a limit entry whose fill print is already at/through its stop is stopped out on that print
    ERRORS (the tester's rule): a session whose strategy callback raises is dropped -- no trades from it, listed
    under no_trade as "strategy error: <type>: <msg>" and counted in "skipped_by_error" (`used` is unchanged,
    as in the tester's coverage block); a warning goes to stderr. on_error="raise" propagates instead (debugging).
    A result with skipped_by_error > 0 is not a clean screen: fix the family first.
    "unrealistic_winners" = len(unrealistic_winners(trades)): limit-entry target wins whose fill print was through
    the stop.
    ONE-DIRECTION EVIDENCE (Apex): every trade row carries `oco` (its entry was a leg of a two-sided OCO pair) and
    `both_sides` (entry orders of opposite sides were working at the same time at some point of that session);
    "both_sides_sessions" counts those sessions, with or without a fill. apex300 / score read them as proof.
    EXECUTION GUARD (automatic, not a sensitivity): when `features` reads book columns, the sessions of a month
    that failed l2data's snapshot-phase check (cache/phase_guard.json) run with EXEC_GUARD_MS (1 s) of extra
    placement latency -> meta["exec_guard"] = {"ms", "months", "sessions"}. A HOLDOUT run on book features
    raises PhaseGuardMissing unless every month of it has a persisted check (the holdout build writes it).
    elapsed_s excludes any time slept in a no-compute window."""
    t_start = time.monotonic()
    start, end = _date(start), _date(end)
    check_holdout(end, allow_holdout)
    if on_error not in ("skip", "raise"):
        raise ValueError("on_error: 'skip' or 'raise'")
    costs = costs or Costs()
    costs = Costs(costs.commission_rt, costs.slippage_ticks if slip_ticks is None else slip_ticks,
                  costs.latency_ms if latency_ms is None else latency_ms,
                  costs.strict_limit if strict_limit is None else strict_limit)
    specs = [(c, dict(p or {})) for c, p in specs]
    probes = [c(p) for c, p in specs]                 # validates the inputs before any process starts
    fcols = getattr(features, "columns", None)
    for st in probes:
        if getattr(st, "p", {}).get("f_depth", "off") != "off" and (features is None or (fcols is not None
                                                                                          and DEPTH_COL not in fcols)):
            raise ValueError(f"f_depth={st.p['f_depth']!r} needs features=L2Features([..., {DEPTH_COL!r}]): the filter "
                             "reads that column through ctx.feat")
    all_days = sessions(start, end, root, allow_holdout) if days is None else sorted(_date(d) for d in days)
    for d in all_days:
        check_holdout(d, allow_holdout)
    guard_months: frozenset = frozenset()
    if needs_exec_guard(features):
        pg = phase_guard()
        months = {d.isoformat()[:7] for d in all_days}
        unchecked = sorted(d.isoformat()[:7] for d in all_days if d >= HOLDOUT_START and d.isoformat()[:7] not in pg["checked"])
        if unchecked:
            raise PhaseGuardMissing(f"holdout months {sorted(set(unchecked))} have no persisted snapshot-phase check "
                                    f"({PHASE_GUARD.name}): build the holdout cache first (l2data.build_cache(allow_holdout="
                                    "True) runs phase_check and persists the months that need the 1 s guard)")
        guard_months = frozenset(months & pg["failed"])
    daily = load_daily(root, allow_holdout) if any(s.needs_daily() for s in probes) else None
    roll_set = rolls(daily) if daily else None
    workers = max(1, min(int(workers), MAX_WORKERS, len(all_days) or 1))
    if not all(getattr(c, "session_independent", False) for c, _ in specs):
        workers = 1                                  # state carried across days: one instance, in order
    if workers > 1 and not pool_usable():
        print("l2sim: the main script was read from stdin, worker processes cannot start from it -> running on ONE process "
              "(put the script in a file, or use python -c, to use workers)", file=sys.stderr, flush=True)
        workers = 1
    iso = [d.isoformat() for d in all_days]
    t_start += wait_compute_window()                 # a wait in a no-compute window is not run time
    if workers == 1:
        parts = [_run_days((specs, root, iso, costs, qty, allow_holdout, daily, roll_set, features, keep_ns,
                            on_error, guard_months))]
    else:
        n_chunks = min(len(iso), workers * 6)
        jobs = [(specs, root, iso[i::n_chunks], costs, qty, allow_holdout, daily, roll_set, features, keep_ns,
                 on_error, guard_months) for i in range(n_chunks)]
        with get_context("spawn").Pool(workers) as p:
            parts = list(p.imap_unordered(_run_days, jobs))
    elapsed = round(time.monotonic() - t_start, 2)
    results = []
    for k, (cls, _) in enumerate(specs):
        trades, skipped, no_trade, n_sess, n_two, n_guard = [], [], [], 0, 0, 0
        for part in parts:
            o = part[k]
            trades += o["trades"]
            skipped += o["skipped"]
            no_trade += o["no_trade"]
            n_sess += o["sessions"]
            n_two += o["both_sides"]
            n_guard += o["guarded"]
        trades.sort(key=lambda t: t["_k"])
        for t in trades:
            del t["_k"]
        skipped.sort(key=lambda s: s["date"])
        no_trade.sort(key=lambda s: s["date"])
        errors = [n for n in no_trade if n["reason"].startswith(ERROR_PREFIX)]
        if errors:
            print(f"l2sim: {cls.__name__} {probes[k].p}: {len(errors)} of {n_sess} sessions DROPPED by a strategy "
                  f"error (first: {errors[0]['date']} {errors[0]['reason']})", file=sys.stderr, flush=True)
        place = cls.placement_ms if costs.latency_ms is None else costs.latency_ms
        stress = {key: v for key, v, base in (("slip_ticks", costs.slippage_ticks, 1.0),
                                              ("latency_ms", place, cls.placement_ms),
                                              ("strict_limit", costs.strict_limit, False)) if v != base}
        results.append({
            "trades": trades, "skipped": skipped, "no_trade": no_trade, "sessions": n_sess,
            "used": n_sess - len(skipped), "skipped_by_error": len(errors), "both_sides_sessions": n_two,
            "unrealistic_winners": len(unrealistic_winners(trades, SPECS[root][1])), "elapsed_s": elapsed,
            "meta": {"engine": ENGINE_VERSION, "fill_law": "tick replay (ofb_tick tape)",
                     "strategy": f"{cls.__module__}.{cls.__name__}", "inputs": probes[k].p, "root": root,
                     "range": {"start": start.isoformat(), "end": end.isoformat(), "holdout": end >= HOLDOUT_START},
                     "qty": qty, "commission": costs.commission_rt, "slippage_ticks": costs.slippage_ticks,
                     "placement_ms": place, "strict_limit": costs.strict_limit, "stress": stress or None,
                     "workers": workers, "cells_in_pass": len(specs),
                     "days_subset": days is not None,
                     "exec_guard": ({"ms": EXEC_GUARD_MS, "months": sorted(guard_months), "sessions": n_guard}
                                    if guard_months else None),
                     "features": list(getattr(features, "columns", [])) if features is not None else None,
                     "features_loader": type(features).__name__ if features is not None else None}})
    return results


def run(cls, params: dict | None = None, start=IN_SAMPLE[0], end=IN_SAMPLE[1], **kw) -> dict:
    """Run ONE strategy class with `params` over every session in [start, end] (see run_many for the
    keyword arguments and the result). Sensitivity: run(cls, params, slip_ticks=2, latency_ms=250) or
    **STRESS; strict_limit=True for limit-entry families."""
    return run_many([(cls, params)], start, end, **kw)[0]


def write_bundle(result: dict, out_dir, run_id: str | None = None) -> Path:
    """Write a tester-shaped bundle (trades.json + run.json) under this pilot directory, so
    R/evalcore.load(path) and R/funded read it unchanged."""
    out = Path(out_dir).resolve()
    if L not in out.parents and out != L:
        raise ValueError(f"bundles are written under {L} only")
    out.mkdir(parents=True, exist_ok=True)
    (out / "trades.json").write_text(json.dumps(result["trades"], separators=(",", ":")))
    meta = dict(result["meta"])
    meta.update(id=run_id or out.name, coverage={"sessions": result["sessions"], "used": result["used"],
                                                 "skipped": result["skipped"], "no_trade": result["no_trade"],
                                                 "skipped_by_error": result.get("skipped_by_error", 0)},
                unrealistic_winners=result.get("unrealistic_winners", 0),
                both_sides_sessions=result.get("both_sides_sessions"),
                elapsed_s=result["elapsed_s"], trades=len(result["trades"]),
                net=round(sum(t["net"] for t in result["trades"]), 2))
    (out / "run.json").write_text(json.dumps(meta, indent=1))
    return out


def _resolve(spec: str):
    """'module:Class' -> the class (module importable from this directory)."""
    import importlib
    mod, name = spec.split(":")
    if str(L) not in sys.path:
        sys.path.insert(0, str(L))
    return getattr(importlib.import_module(mod), name)


def main(argv=None) -> int:
    """python l2sim.py run l2ref:Donchian --inputs '{"tf": "15"}' [--start D --end D --workers 8]
                           [--features imb10,depth10] [--out out/runs/<id>]
                           [--slip-ticks 2 --latency-ms 250 --strict-limit]     (sensitivity; default = tester law)
       python l2sim.py daily            (re)build the in-sample daily-bar cache"""
    import argparse
    ap = argparse.ArgumentParser(prog="l2sim.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("strategy")
    r.add_argument("--inputs", default="{}")
    r.add_argument("--start", default=IN_SAMPLE[0].isoformat())
    r.add_argument("--end", default=IN_SAMPLE[1].isoformat())
    r.add_argument("--workers", type=int, default=MAX_WORKERS)
    r.add_argument("--features", default="")
    r.add_argument("--out", default="")
    r.add_argument("--slip-ticks", type=float, default=None)
    r.add_argument("--latency-ms", type=int, default=None)
    r.add_argument("--strict-limit", action="store_true")
    sub.add_parser("daily")
    a = ap.parse_args(argv)
    if a.cmd == "daily":
        print(build_daily())
        return 0
    feats = L2Features([c for c in a.features.split(",") if c]) if a.features else None
    res = run(_resolve(a.strategy), json.loads(a.inputs), a.start, a.end, workers=a.workers, features=feats,
              slip_ticks=a.slip_ticks, latency_ms=a.latency_ms, strict_limit=a.strict_limit or None)
    tr = res["trades"]
    print(json.dumps({"strategy": a.strategy, "inputs": res["meta"]["inputs"], "sessions": res["sessions"],
                      "used": res["used"], "skipped_by_error": res["skipped_by_error"],
                      "unrealistic_winners": res["unrealistic_winners"], "stress": res["meta"]["stress"],
                      "trades": len(tr), "net": round(sum(t["net"] for t in tr), 2),
                      "elapsed_s": res["elapsed_s"], "out": str(write_bundle(res, a.out)) if a.out else None}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
