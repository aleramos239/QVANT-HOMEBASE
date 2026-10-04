#!/usr/bin/env python3
"""L2 pilot scoring adapter: trade lists from the offline tick sim -> R's eval / funded / control machinery, UNCHANGED.

R = ../2026-09-29 (read-only). Nothing in R is edited, nothing is written into R (no __pycache__ either: bytecode writing is
switched off before R is imported). Everything numeric is done by R's own functions (evalcore.load / walk / race / block_ci /
daymatched_controls, portfolio.Base / PV / norm_key / make_A / Firm, funded.make_spec / DaySrc / lifecycle / metrics / search);
this module only (1) turns `L/trades/<config>.json` (or an in-memory list of trade dicts, tester trades.json schema) into R's TR
object through R's own loader, (2) pins the session calendar, (3) seals the holdout, (4) wraps the calls in four functions.

Run with "~/ONYX TRADING/.venv/bin/python" or /usr/bin/python3 (numpy; pandas only for the C2 helper).

TRADE SOURCES (`trades` argument everywhere; `load_trades`)
  'file:<config>' | '<config>'           -> L/trades/<config>.json   (list of trade dicts, or {"trades": [...]})
  '/path/to/x.json' | {'path': ...}      -> that file; a bundle DIRECTORY (l2sim.write_bundle: trades.json + run.json) works too
  [ {trade dict}, ... ] | {'trades': []} -> in-memory list; a whole l2sim.run() result dict works too (its run range is
                                            honoured; a result with skipped_by_error > 0 is refused: not a clean run)
  R run id | 'grid_id#cell' | {'run'|'grid'+'cell'} -> R's native bundle (homebase/.state/tester/...), through evalcore.load
  an evalcore TR                          -> used as is
  [ {'src': <any of the above>, 'sess': 'nyam', 'micros': 40}, ... ] -> a multi-member portfolio (score_eval / score_funded)
The config sources also work INSIDE R: importing this module wraps `evalcore.load` / `evalcore._src_dir`, so a member
{'src': 'file:<config>', 'sess': ..., 'micros': ...} (or a bare config name of L/trades) is accepted by evalcore.build /
evaluate / search and portfolio.Ctx.base. Sources R already resolves itself (run ids, grid cells, lists, real paths) keep R's
own loader and semantics inside R; only THIS module's functions validate and seal those.
Required keys per trade (SPEC "Execution"): date, side, qty, entry_price, exit_price, exit_reason, gross, commission, net,
mae_usd, mfe_usd, entry_ms, exit_ms (mae_pts / mfe_pts / sl / tp optional; `sl` gives the cost/risk ratio). gross is per the
row's qty with slippage already in the prices; R re-sizes it (n micros: n*gross/10 - cost(n)) and ignores commission / net.

HOLDOUT (sealed): any row dated >= 2025-01-01 (by `date`, entry_ms or exit_ms), any calendar day >= 2025-01-01 and any R bundle
whose run range reaches 2025 RAISES HoldoutError unless allow_holdout=True is passed explicitly. A native bundle is refused from
its run.json BEFORE its trades are read. (R's own loader silently drops such rows; this one refuses.)

CALENDAR: the in-sample session calendar is R's `bundles_cache/nq_sessions.json` = 825 weekday tape sessions 2021-09-22 ->
2024-12-31 (no-trade weekdays are sessions with 0 P&L). It is read, never rebuilt. A bundle whose run.json covers a shorter
range is scored on that range only (R: evalcore.build); a plain trade file / list is taken to cover the whole window. A trade dated off the calendar raises
(off_calendar='raise'; R's own convention 'union' adds the date, 'drop' discards the trade). Rolling starts: every session with
a full horizon (5 sessions eval -> 821 starts, 60 funded -> 766 starts). The same 825 sessions are l2sim.sessions() (the tape
files), the data layer's Globex sessions that the sim trades, and apex300.default_calendar (tests/test_score_controls.py).

EVAL FIRMS: lucid | lucidpro | lucidpro_nodll | apex | apex_eod (R's rule files, 5-session horizon) and 'apex300_eval' = the Apex
Legacy 300K evaluation ($20,000 goal, $7,500 intraday trail on the live balance, 35 minis, 7 traded days; L/apex300.eval_sim):
`score_eval(trades, 'apex300_eval', rules, micros=)` -> P(pass <= 10 / 20 trading days) + bust; `search_rules(trades,
'apex300_eval')` -> its rule grid (APEX300_EVAL_GRID).

RULES dict (all R dims): micros, day_lock, day_take, day_stop, max_day_tr, target_take (eval only), plus target_stop (default
True = R's pass-2/3 + portfolio convention; R's bare evaluate.py default is False), after_loss / after_win (default 1.0).
BREACH MODELS: eval + Lucid funded 'eod' | 'realized' | 'intraday'; Apex PA funded 'pess' | 'nat' | 'opt'. Primary (default):
lucid / lucidpro / lucidpro_nodll = realized, apex / apex_eod = intraday, Apex PA = pess. All models are always returned.

CONTROLS
  C1 `lift_vs_control(trades, pool, firm, rules)`: K day-matched random ledgers drawn from `pool` (random-entry runs with the
     same exit profile) by evalcore.daymatched_controls (same (date, session) trade counts), scored at IDENTICAL micros + rules;
     lift = P5(real) - mean_k P5(control k); CI = block bootstrap of the paired per-start difference (R: portfolio.control_lift).
     mode='direct' takes K ready-made control ledgers instead (used for C2).
  C2 FEATURE-SHUFFLE null (`c2_donor_map`, `c2_shuffle`, `c2_null`, `C2Features` = the l2sim loader): documented in the
     C2 section near the bottom of this file. Price-carrying columns (f_o/f_h/f_l/f_c, bid_px/ask_px), tags and flags
     can not be shuffled; C2Features shuffles every other column it loads.

FUNDED FIRMS: flex | flex_dll | pro_dll | pro_nodll | apex (R/funded.py, R's frozen semantics) and apex300_pa | apex50_pa
(L/apex300.py: start states `start_states(firm)`, conservative rule readings + the other consistency reading as `cons_alt`,
Apex commissions, and THE Apex compliance gate: one direction / stop <= 5x target / MAE rule, fail closed). `search_funded`
on an apex300 firm runs apex300.search on apex300.GRID and keeps apex300.compliant(rows) only. `score_baseline_apex300()`
scores the approved picks' strategies on the 300K PA (the in-sample bar for that account); `score.py baseline` writes all
baseline numbers to L/out/baseline_insample.json. HOW-TO: L/SCORING.md.

WALK-FORWARD: `walk_forward(configs, firm, control_pool=...)` = R's offline quarterly walk-forward (wf_offline.py) on a family
grid of trade sources; `search_rules(..., keep_arrays=True)` returns the per-start pass flags in wf_offline's layout.

OFFLINE COMPUTE WINDOWS: `desk_window_wait()` sleeps out 09:18-09:36 ET on weekdays and Fri 2026-10-02 08:15-08:50 ET (with a
60 s lead); it is called before every uncached walk of a search and replaces funded.desk_window_wait / portfolio.gate.
Bare module names owned by R once this is imported: evalcore, funded, portfolio, pilot (do not reuse them for L modules).
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True          # never drop __pycache__ into R or homebase/

import datetime as dt                   # noqa: E402
import json                             # noqa: E402
import os                               # noqa: E402
import re                               # noqa: E402
import time                             # noqa: E402
import zlib                             # noqa: E402
from pathlib import Path                # noqa: E402
from types import SimpleNamespace       # noqa: E402

import numpy as np                      # noqa: E402

L = Path(__file__).resolve().parent
REPO = L.parents[2]
R = REPO / "research" / "prop-portfolio" / "2026-09-29"            # the old NQ pilot (READ-ONLY)
TRADES = L / "trades"
OUT = L / "out"
IS_START, IS_END, HOLDOUT = "2021-09-22", "2024-12-31", "2025-01-01"
N_IS_SESSIONS = 825

for _k in ("PP_PILOT", "PP_ROOT", "PP_DIR"):          # R's pilot selector: this adapter is NQ / R only
    if os.environ.get(_k) and not (_k == "PP_PILOT" and os.environ[_k].lower() == "nq") \
            and not (_k == "PP_ROOT" and os.environ[_k].upper() == "NQ"):
        raise RuntimeError(f"{_k}={os.environ[_k]!r} is set: the L2 scoring adapter only runs on the NQ pilot (unset it)")
if any(a == "--pilot" or a.startswith("--pilot=") or a == "--dir" or a.startswith("--dir=") for a in sys.argv[1:]):
    raise RuntimeError("--pilot / --dir are R pilot-selector flags; not supported by the L2 scoring adapter")

sys.path.insert(0, str(R))
import evalcore as E                    # noqa: E402
import funded as F                      # noqa: E402
import portfolio as P                   # noqa: E402

for _p in (str(R), str(REPO)):          # R / repo stay importable (R imports lazily) but no longer shadow other modules
    while _p in sys.path:
        sys.path.remove(_p)
    sys.path.append(_p)

if E.PL.NAME != "nq" or E.D.resolve() != R.resolve() or E.ROOT != "NQ" or E.HOLDOUT != HOLDOUT:
    raise RuntimeError(f"unexpected R pilot context: {E.PL.NAME} {E.D} {E.ROOT} {E.HOLDOUT}")

# ---- the session tagger (EDGE_SPEC "PROPER RE-RUN" 5): R's evalcore tags a trade by its ET entry minute with the five
# tester sessions. Two more are added IN THIS PROCESS (R's files are untouched; the five keep their codes 0..4 and their
# windows, so every old trade is tagged exactly as before): 'pre' 08:25-09:30 and 'eve' 18:00-23:59 -- an evening trade
# carries the NEXT trade date in its `date` field, so it is scored on the day it belongs to.
SESS5 = tuple(E.SESS)                                       # ('asia', 'london', 'nyam', 'mid', 'pm')
if SESS5 != ("asia", "london", "nyam", "mid", "pm") or [E.SESS_CODE[k] for k in SESS5] != [0, 1, 2, 3, 4]:
    raise RuntimeError(f"unexpected R session table: {E.SESS} {E.SESS_CODE}")
E.SESS.update({"pre": (505, 570), "eve": (1080, 1439)})     # minutes after 00:00 ET, [a, b)
E.SESS_CODE.update({"pre": 5, "eve": 6})
SESS7 = ("eve", "asia", "london", "pre", "nyam", "mid", "pm")           # the Globex day in clock order

ET = E.ET
MODELS = E.MODELS                                           # ('eod', 'realized', 'intraday')
EVAL_FIRMS = ("lucid", "lucidpro", "lucidpro_nodll", "apex", "apex_eod")
H_EVAL, H_FUNDED = E.H_EVAL, F.H_LIFE                       # 5, 60
PV_USD = float(E.PL.PV)                                     # $ per point of ONE NQ (20)
_HOLDOUT_MS = int(dt.datetime(2025, 1, 1, tzinfo=ET).timestamp() * 1000)


class HoldoutError(RuntimeError):
    """A row / calendar day / bundle dated >= 2025-01-01 was reached without allow_holdout=True."""


# ------------------------------------------------------------------ offline compute windows

SPECIAL_WINDOWS = {dt.date(2026, 10, 2): [(dt.time(8, 15), dt.time(8, 50))]}       # live NFP trade
DAILY_WINDOW = (dt.time(9, 18), dt.time(9, 36))                                    # weekdays: the desk trades at 09:30


def blackout_wait_s(now: dt.datetime | None = None, lead_s: float = 60.0) -> float:
    """Seconds to sleep before heavy compute may run (0.0 = clear). `lead_s`: also wait when a window starts within lead_s."""
    t = now or dt.datetime.now(ET)
    if t.tzinfo is None:
        t = t.replace(tzinfo=ET)
    t = t.astimezone(ET)
    wins = list(SPECIAL_WINDOWS.get(t.date(), []))
    if t.weekday() < 5:
        wins.append(DAILY_WINDOW)
    for a, b in wins:
        lo = t.replace(hour=a.hour, minute=a.minute, second=0, microsecond=0) - dt.timedelta(seconds=lead_s)
        hi = t.replace(hour=b.hour, minute=b.minute, second=0, microsecond=0)
        if lo <= t < hi:
            return (hi - t).total_seconds() + 5.0
    return 0.0


def desk_window_wait(now: dt.datetime | None = None, sleep=time.sleep) -> float:
    """Sleep out the offline-compute windows. Returns the seconds slept. Same signature as funded.desk_window_wait."""
    tot = 0.0
    while True:
        s = blackout_wait_s(now)
        if not s:
            return tot
        print(f"[score] offline compute window: sleeping {s:.0f}s", flush=True)
        sleep(s)
        tot += s
        if now is not None:                 # explicit clock (tests): one pass
            return tot


# ------------------------------------------------------------------ calendar

class Cal:
    """Session calendar (ordinals) + rolling-start index matrices."""

    def __init__(self, ords):
        self.cal = np.asarray(sorted(int(o) for o in ords), np.int64)
        self.D = len(self.cal)
        self.S = max(self.D - H_EVAL + 1, 0)
        self.idx5 = np.arange(self.S)[:, None] + np.arange(H_EVAL)
        self.iso = [dt.date.fromordinal(int(o)).isoformat() for o in self.cal]

    @property
    def window(self) -> dict:
        return {"start": self.iso[0] if self.D else None, "end": self.iso[-1] if self.D else None, "sessions": self.D,
                "starts5": int(self.S), "starts60": int(max(self.D - H_FUNDED + 1, 0))}


_CAL_FILE = R / "bundles_cache" / "nq_sessions.json"
_CAL_IS: list = []


def in_sample_sessions() -> list[str]:
    """R's tape calendar clipped to the in-sample window: 825 ISO dates 2021-09-22 .. 2024-12-31 (read-only; never rebuilt)."""
    if not _CAL_IS:
        if not _CAL_FILE.exists():
            raise FileNotFoundError(f"{_CAL_FILE} is missing: R's session calendar cache must exist (this adapter never writes it)")
        ds = [d for d in json.loads(_CAL_FILE.read_text()) if IS_START <= d <= IS_END]
        if len(ds) != N_IS_SESSIONS or ds[0] != IS_START or ds[-1] != IS_END or ds != sorted(set(ds)) \
                or any(dt.date.fromisoformat(d).weekday() > 4 for d in ds):
            raise RuntimeError(f"R session calendar changed: {len(ds)} sessions {ds[:1]}..{ds[-1:]} (expected {N_IS_SESSIONS}, "
                               f"{IS_START}..{IS_END})")
        _CAL_IS.extend(ds)
    return list(_CAL_IS)


def _ord(d) -> int:
    if isinstance(d, (int, np.integer)):
        return int(d)
    if isinstance(d, dt.datetime):
        return d.date().toordinal()
    if isinstance(d, dt.date):
        return d.toordinal()
    return dt.date.fromisoformat(str(d)[:10]).toordinal()


_HOLDOUT_ORD = dt.date.fromisoformat(HOLDOUT).toordinal()


PERIODS = {"build": ("2021-09-22", "2023-12-31"), "pick": ("2024-01-01", "2024-12-31"), "insample": (IS_START, IS_END)}


def period_sessions(period: str = "insample") -> list[str]:
    """The NQ session calendar of ONE period (EDGE_SPEC user rule 3): 'build' = 2021-09-22 .. 2023-12-31, 'pick' = 2024,
    'insample' = both (the old pilots' window: tester-match gates only). Cut from R's tape calendar (never rebuilt).
    'exam' raises: the EXAM calendar is explicit by construction (allow_holdout=True + its dates)."""
    key = str(period).lower()
    if key == "exam":
        raise HoldoutError("the EXAM period (>= 2025-01-01) is sealed: pass its dates and allow_holdout=True explicitly")
    if key not in PERIODS:
        raise KeyError(f"period {period!r}: one of {sorted(PERIODS)}")
    lo, hi = PERIODS[key]
    return [d for d in in_sample_sessions() if lo <= d <= hi]


def make_calendar(calendar=None, allow_holdout: bool = False) -> Cal:
    """None -> the in-sample calendar; a PERIOD NAME ('build' | 'pick' | 'insample') -> that period's calendar
    (period_sessions); else an iterable of ISO dates / dates / ordinals (a sub-window, or the holdout calendar with
    allow_holdout=True). Every score_* / search_* / lift_* function takes `calendar=` and hands it here."""
    if isinstance(calendar, Cal):
        c = calendar
    else:
        if isinstance(calendar, str):
            calendar = period_sessions(calendar)
        c = Cal([_ord(d) for d in (in_sample_sessions() if calendar is None else calendar)])
    if c.D and int(c.cal[-1]) >= _HOLDOUT_ORD and not allow_holdout:
        raise HoldoutError(f"calendar reaches {c.iso[-1]} (holdout starts {HOLDOUT}); pass allow_holdout=True explicitly")
    return c


def tape_sessions(start: str, end: str, allow_holdout: bool = False) -> list[str]:
    """Weekday sessions with a tick-archive manifest in [start, end] (homebase TapeStore; file names only, read-only) =
    how R builds its calendars (in-sample: equals the cache; holdout: holdout_score.calendar). Refuses 2025+ unless allowed."""
    if end >= HOLDOUT and not allow_holdout:
        raise HoldoutError(f"end {end} reaches the holdout ({HOLDOUT}); pass allow_holdout=True explicitly")
    from homebase.backtest.tape import TapeStore
    return [d.isoformat() for d in TapeStore().sessions(E.ROOT, dt.date.fromisoformat(start), dt.date.fromisoformat(end))]


# ------------------------------------------------------------------ trade sources

REQUIRED = ("date", "side", "qty", "entry_price", "exit_price", "exit_reason", "gross", "commission", "net", "mae_usd", "mfe_usd",
            "entry_ms", "exit_ms")
_R_LOAD, _R_SRC_DIR, _R_SAVE = E.load, E._src_dir, E.save       # R's originals (the wrappers below delegate to them)
_FILE_CACHE: dict = {}


def trade_file(name: str) -> Path:
    """L/trades/<name>.json for a config name ('file:' prefix and '.json' suffix optional)."""
    n = name[5:] if name.startswith("file:") else name
    return TRADES / (n if n.endswith(".json") else n + ".json")


def _is_rows(x) -> bool:
    return isinstance(x, (list, tuple)) and (len(x) == 0 or (isinstance(x[0], dict) and "entry_ms" in x[0]))


def _is_members(x) -> bool:
    return isinstance(x, (list, tuple)) and len(x) > 0 and isinstance(x[0], dict) and "src" in x[0]


def _is_tr(x) -> bool:
    return isinstance(x, E.TR) or all(hasattr(x, a) for a in ("date", "te", "tx", "g", "mae", "mfe", "sess", "n"))


def _classify(src):
    """-> (kind, payload): 'tr' | 'rows' | 'file' (Path) | 'native' (R source)."""
    if _is_tr(src):
        return "tr", src
    if _is_rows(src):
        return "rows", list(src)
    if isinstance(src, dict):
        if "trades" in src:                                   # {'trades': [...]} or a whole l2sim.run result (see load_trades)
            return "rows", list(src["trades"])
        if "file" in src:
            return "file", trade_file(str(src["file"]))
        if "path" in src:
            p = Path(str(src["path"])).expanduser()
            return "file", (p / "trades.json" if p.is_dir() else p)
        if "run" in src or "grid" in src:
            return "native", src
        raise ValueError(f"unknown trade source dict {sorted(src)}")
    if isinstance(src, Path):
        return "file", (src / "trades.json" if src.is_dir() else src)
    if isinstance(src, str):
        if src.startswith("file:"):
            return "file", trade_file(src)
        p = Path(src).expanduser()
        if src.endswith(".json") or p.is_file():
            return "file", p
        if trade_file(src).exists():
            return "file", trade_file(src)
        if p.is_dir() and (p / "trades.json").exists() and not _in_tester_state(p):
            return "file", p / "trades.json"                  # a bundle directory of the offline sim (l2sim.write_bundle)
        d = _R_SRC_DIR(src)
        if d is None or not Path(d).exists():
            raise FileNotFoundError(f"unknown trade source {src!r}: no {trade_file(src)}, no such path, no R run / grid cell")
        return "native", src
    raise TypeError(f"unsupported trade source type {type(src).__name__}")


def _in_tester_state(p: Path) -> bool:
    rp = p.resolve()
    return any(base.resolve() in rp.parents or base.resolve() == rp for base in (E.RUNS, E.GRIDS))


def is_file_source(src) -> bool:
    """True for the source types R does not know (file:<config>, config names, {'file'|'path'|'trades'}, row lists)."""
    try:
        return _classify(src)[0] in ("file", "rows")
    except (FileNotFoundError, ValueError, TypeError):
        return False


def validate_trades(rows: list, pv: float = PV_USD) -> list[str]:
    """Schema / consistency problems of a trade list (empty = OK). Checks the keys R reads and the sim contract: ISO date equal
    to the ET date of entry_ms (or, for an evening entry at / after 18:00 ET, the calendar day after it), exit >= entry, side long|short, qty >= 1, gross == side*(exit-entry)*$20*qty, net == gross - commission."""
    bad = []
    for i, x in enumerate(rows):
        miss = [k for k in REQUIRED if x.get(k) is None]
        if miss:
            bad.append(f"row {i}: missing {miss}")
            continue
        try:
            d = dt.date.fromisoformat(x["date"])
            te, tx, q = int(x["entry_ms"]), int(x["exit_ms"]), float(x["qty"])
            if x["side"] not in ("long", "short"):
                bad.append(f"row {i}: side {x['side']!r}")
            if q < 1:
                bad.append(f"row {i}: qty {q} < 1 (R normalises by max(1, qty))")
            if tx < te:
                bad.append(f"row {i}: exit_ms < entry_ms")
            a = dt.datetime.fromtimestamp(te / 1000, ET)
            # an EVENING entry (18:00-23:59 ET) belongs to the NEXT trade date's session: its `date` is the calendar day after
            if a.date() != d and not (a.hour >= 18 and a.date() + dt.timedelta(days=1) == d):
                bad.append(f"row {i}: date {x['date']} != ET date of entry_ms")
            sgn = 1.0 if x["side"] == "long" else -1.0
            g = sgn * (float(x["exit_price"]) - float(x["entry_price"])) * pv * q
            if abs(g - float(x["gross"])) > 0.011:
                bad.append(f"row {i}: gross {x['gross']} != side*(exit-entry)*{pv:g}*qty = {g:.2f}")
            if abs(float(x["gross"]) - float(x["commission"]) - float(x["net"])) > 0.011:
                bad.append(f"row {i}: net != gross - commission")
            float(x["mae_usd"]), float(x["mfe_usd"])                       # magnitudes (R takes abs())
        except (TypeError, ValueError) as e:
            bad.append(f"row {i}: {e}")
        if len(bad) >= 20:
            bad.append("... (stopped after 20 problems)")
            break
    return bad


def _guard_rows(rows: list, label: str, allow_holdout: bool) -> None:
    if allow_holdout or not rows:
        return
    mx = max(str(x.get("date", "")) for x in rows)
    ms = max(max(int(x.get("entry_ms") or 0), int(x.get("exit_ms") or 0)) for x in rows)
    if mx >= HOLDOUT or ms >= _HOLDOUT_MS:
        raise HoldoutError(f"{label}: trades reach the sealed holdout (latest date {mx}); pass allow_holdout=True explicitly")


def _tr_from_rows(rows: list, label: str, allow_holdout: bool, strict: bool):
    _guard_rows(rows, label, allow_holdout)
    if strict:
        bad = validate_trades(rows)
        if bad:
            raise ValueError(f"{label}: invalid trade list:\n  " + "\n  ".join(bad))
    t = _R_LOAD(rows, allow_holdout)                           # R's own loader on the in-memory list (per 1 NQ, sessions tagged)
    if t.n != len(rows):
        raise RuntimeError(f"{label}: R's loader kept {t.n} of {len(rows)} rows")
    t.label = label
    t.range = (None, None) if allow_holdout else (IS_START, IS_END)
    q = np.array([max(1.0, float(x.get("qty") or 1)) for x in rows])
    t.net = np.array([float(x["net"]) for x in rows]) / q if all("net" in x for x in rows) else None      # a3_pass2.load_src extras
    t.year = np.array([int(x["date"][:4]) for x in rows], np.int16)
    t.rows = rows                                              # raw rows: the Apex per-trade checks (sl / tp / side overlap)
    return t


def _read_rows(path: Path) -> list:
    rows = json.loads(Path(path).read_text())
    return rows if isinstance(rows, list) else rows.get("trades", [])


def _native_guard(src, allow_holdout: bool) -> None:
    """Refuse an R bundle whose run reaches the holdout BEFORE its trades are read."""
    if allow_holdout:
        return
    d = _R_SRC_DIR(src)
    rj = (d if d.is_dir() else d.parent) / "run.json"
    if not rj.exists():
        raise HoldoutError(f"{src}: no run.json next to the bundle, cannot prove it is in-sample; pass allow_holdout=True explicitly")
    r = json.loads(rj.read_text())
    end = str((r.get("range") or {}).get("end") or "9999")
    if end >= HOLDOUT or r.get("holdout") or (r.get("range") or {}).get("holdout"):
        raise HoldoutError(f"{src}: the run covers {r.get('range')} (holdout starts {HOLDOUT}); pass allow_holdout=True explicitly")


def sim_label(meta) -> str | None:
    """Default name of an in-memory l2sim result: '<StrategyClass>|k=v,...' from meta.strategy + meta.inputs (sorted keys), so
    two different configs never share the 'inline' label (and with it one C1 seed). None when the meta does not name a strategy."""
    if not isinstance(meta, dict) or not meta.get("strategy"):
        return None
    inp = {k: v for k, v in (meta.get("inputs") or {}).items() if not (k in _NEW_OFF and v == "off")}
    return str(meta["strategy"]).rsplit(".", 1)[-1] + "|" + ",".join(f"{k}={inp[k]}" for k in sorted(inp))


_NEW_OFF = ("f_book", "x_book", "f_thin")       # Template options added for the edge library: left out of a label while
#                                                 'off', so a config's name (and with it its C1 seed) is what it was before


def _check_sim_coverage(n_sessions, rg: dict, label: str, calendar) -> None:
    """Refuse an l2sim result / bundle that simulated FEWER sessions than the session calendar of its own run range holds (a
    run made with days=<subset>, or a strategy that only trades some days): scored on the default calendar its unsimulated
    days would count as flat days. An explicit calendar (the days the run covered, or in_sample_sessions() when the missing
    days really are no-trade days) lifts the refusal."""
    if calendar is not None or n_sessions is None:
        return
    lo, hi = str(rg.get("start") or IS_START), str(rg.get("end") or IS_END)
    if hi >= HOLDOUT or rg.get("holdout"):
        return                                                # holdout stage: the calendar is explicit there by construction
    exp = sum(1 for d in in_sample_sessions() if lo <= d <= hi)
    if int(n_sessions) < exp:
        raise ValueError(f"{label}: the sim run covered {int(n_sessions)} sessions, the calendar {lo}..{hi} has {exp} -- a run on a "
                         f"subset of the days must be scored with calendar=<those days> (pass calendar=in_sample_sessions() "
                         f"only if the other days are genuine no-trade days of the strategy)")


def load_trades(src, allow_holdout: bool = False, strict: bool = True, label: str | None = None, calendar=None):
    """Any trade source (module docstring) -> R's TR (arrays per 1 NQ: date, te, tx, side, g, mae, mfe, risk, sess, iso).
    Raises HoldoutError on any 2025+ content unless allow_holdout=True; `strict` validates the schema of file / in-memory lists.
    An l2sim result / bundle whose session count is below the calendar of its run range is refused unless `calendar` (the
    explicit calendar the caller scores on) is given; an in-memory l2sim result is labelled from its meta (`sim_label`)."""
    kind, x = _classify(src)
    if kind == "tr":
        if not allow_holdout and x.n and int(np.max(x.date)) >= _HOLDOUT_ORD:
            raise HoldoutError("TR object reaches the sealed holdout; pass allow_holdout=True explicitly")
        return x
    if kind == "rows":
        meta = src.get("meta") if isinstance(src, dict) else None
        rg = (meta.get("range") or {}) if isinstance(meta, dict) else {}
        if isinstance(src, dict) and "skipped_by_error" in src:          # an l2sim.run / run_many result
            if strict and src.get("skipped_by_error"):
                raise ValueError(f"l2sim result: {src['skipped_by_error']} sessions were DROPPED by a strategy error; not a clean "
                                 f"run (fix the family; strict=False scores it anyway)")
            if not allow_holdout and (str(rg.get("end") or "") >= HOLDOUT or rg.get("holdout")):
                raise HoldoutError(f"l2sim result covers {rg} (holdout starts {HOLDOUT}); pass allow_holdout=True explicitly")
            if strict:
                _check_sim_coverage(src.get("sessions"), rg, label or sim_label(meta) or "l2sim result", calendar)
        t = _tr_from_rows(x, label or sim_label(meta) or "inline", allow_holdout, strict)
        if rg.get("start") or rg.get("end"):                             # as a bundle: never scored outside the span the run covered
            t.range = (rg.get("start"), rg.get("end"))
        if isinstance(src, dict):
            t.both_sides_sessions = src.get("both_sides_sessions")       # l2sim's run-level one-direction evidence (Apex gate)
        return t
    if kind == "file":
        p = Path(x)
        if not p.exists():
            raise FileNotFoundError(f"no trade file {p}")
        rj, rng, two = p.parent / "run.json", None, None
        if p.name == "trades.json" and rj.exists():           # a bundle: its run range is checked BEFORE the rows are read
            r = json.loads(rj.read_text())
            rg = r.get("range") or {}
            if not allow_holdout and (str(rg.get("end") or "") >= HOLDOUT or r.get("holdout") or rg.get("holdout")):
                raise HoldoutError(f"{p.parent}: the run covers {rg} (holdout starts {HOLDOUT}); pass allow_holdout=True explicitly")
            rng = (rg.get("start"), rg.get("end"))
            if strict and str(r.get("engine", "")).startswith("l2sim"):
                _check_sim_coverage((r.get("coverage") or {}).get("sessions"), rg, label or p.parent.name, calendar)
            two = r.get("both_sides_sessions")
        stt = p.stat()
        key = (str(p.resolve()), stt.st_mtime_ns, stt.st_size, bool(allow_holdout), bool(strict), rng, label)
        if key not in _FILE_CACHE:
            t = _tr_from_rows(_read_rows(p), label or (p.parent.name if p.name == "trades.json" else p.stem), allow_holdout, strict)
            if rng and (rng[0] or rng[1]):
                t.range = rng                               # as R: a member is never evaluated outside the span its run covered
            t.both_sides_sessions = two
            _FILE_CACHE[key] = t
        return _FILE_CACHE[key]
    _native_guard(x, allow_holdout)
    t = _R_LOAD(x, allow_holdout)
    if not hasattr(t, "rows"):                                 # raw rows of the bundle (R's loader keeps arrays only)
        d = _R_SRC_DIR(x)
        t.rows = [r for r in _read_rows(d if d.is_file() else d / "trades.json") if allow_holdout or r["date"] < HOLDOUT]
    return t


# ---- make R itself understand the new source types (in-process wrappers; R's files are untouched)

def _wrapped(src):
    """The source types the evalcore.load wrapper takes over = the ones R cannot resolve itself: 'file:<config>',
    {'file': <config>} and a bare config name that exists in L/trades. Everything R already supports (run ids, grid cells,
    in-memory lists, real paths incl. sim bundle directories) stays with R's own loader, semantics untouched. -> Path | None."""
    if isinstance(src, dict):
        return trade_file(str(src["file"])) if "file" in src else None
    if not isinstance(src, str):
        return None
    if src.startswith("file:"):
        return trade_file(src)
    if "#" not in src and not Path(src).expanduser().exists() and trade_file(src).exists():
        return trade_file(src)
    return None


def _load_wrapper(src, holdout: bool = False):
    """evalcore.load + the L config sources. Those go through load_trades (validated, holdout raises); R's tester bundles go
    to R's loader unchanged after the holdout guard (R alone would read a 2025+ bundle and drop its rows; here it is refused
    unread); in-memory lists and real paths are R's own business (R semantics: 2025+ rows dropped unless holdout=True)."""
    if _wrapped(src) is not None:
        return load_trades(src, allow_holdout=holdout)
    if isinstance(src, (str, dict)) and not holdout:
        d = _R_SRC_DIR(src)
        if d is not None and Path(d).is_dir() and _in_tester_state(Path(d)):
            _native_guard(src, False)
    return _R_LOAD(src, holdout)


def _src_dir_wrapper(src):
    w = _wrapped(src)
    return w if w is not None else _R_SRC_DIR(src)


def _save_wrapper(res: dict, out_dir: Path | None = None) -> Path:
    """evalcore.save with the default directory moved from R/out to L/out (this pilot never writes into R)."""
    return _R_SAVE(res, out_dir or OUT)


def install() -> None:
    """Wrap evalcore.load / _src_dir / save and the desk-window gates (idempotent). Called at import."""
    E.load, E._src_dir, E.save = _load_wrapper, _src_dir_wrapper, _save_wrapper
    F.desk_window_wait = desk_window_wait
    P.gate = lambda: desk_window_wait()


def uninstall() -> None:
    E.load, E._src_dir, E.save = _R_LOAD, _R_SRC_DIR, _R_SAVE


install()


# ------------------------------------------------------------------ members / ports

def _members(trades, sess, micros, news, allow_holdout: bool, strict: bool = True, calendar=None) -> list[dict]:
    """-> [{tr, label, sess, micros, news}]. `trades` = one source, or a list of member dicts {'src', 'sess', 'micros', 'news'}."""
    if _is_members(trades):
        out = []
        for m in trades:
            tr = load_trades(m["src"], allow_holdout, strict, calendar=calendar)
            out.append({"tr": tr, "label": m.get("label") or getattr(tr, "label", "inline"), "sess": m.get("sess", sess),
                        "micros": int(m["micros"]) if m.get("micros") else (int(micros) if micros else None), "news": m.get("news", news)})
        return out
    tr = load_trades(trades, allow_holdout, strict, calendar=calendar)
    return [{"tr": tr, "label": getattr(tr, "label", "inline"), "sess": sess, "micros": int(micros) if micros else None, "news": news}]


def _mask(tr, sess, news) -> np.ndarray:
    m = E._sess_mask(tr, sess)
    if news != "all":
        nd = E.news_days()
        isn = np.isin(tr.date, list(nd)) if nd else np.zeros(tr.n, bool)
        m = m & (~isn if news == "skip" else isn)
    return m


def _on_calendar(tr, m: np.ndarray, cal: Cal, off_calendar: str, label: str):
    """Mask after the calendar policy; -> (mask, Cal)."""
    off = m & ~np.isin(tr.date, cal.cal)
    if not off.any():
        return m, cal
    days = sorted({dt.date.fromordinal(int(o)).isoformat() for o in tr.date[off]})
    if off_calendar == "raise":
        raise ValueError(f"{label}: {int(off.sum())} trades on {len(days)} dates off the session calendar ({days[:5]}...); "
                         f"off_calendar='union' (R's convention) adds the dates, 'drop' discards the trades")
    if off_calendar == "drop":
        return m & ~off, cal
    if off_calendar == "union":
        return m, Cal(set(cal.cal.tolist()) | set(tr.date[off].tolist()))
    raise ValueError(f"off_calendar {off_calendar!r}")


def _prep(trades, sess, micros, news, calendar, allow_holdout, off_calendar, strict=True):
    """-> (members with masks, Cal). The calendar is shared by every member (union policy widens it for all)."""
    cal = make_calendar(calendar, allow_holdout)
    mem = _members(trades, sess, micros, news, allow_holdout, strict, calendar)
    lo = max([m["tr"].range[0] for m in mem if getattr(m["tr"], "range", (None, None))[0]] or [None], key=lambda x: x or "")
    hi = min([m["tr"].range[1] for m in mem if getattr(m["tr"], "range", (None, None))[1]] or [None], key=lambda x: x or "9999")
    if cal.D and ((lo and lo > cal.iso[0]) or (hi and hi < cal.iso[-1])):       # evalcore.build: clip to the span the runs covered
        cal = Cal([o for o, d in zip(cal.cal, cal.iso) if (not lo or d >= lo) and (not hi or d <= hi)])
    for m in mem:
        m["mask"], cal = _on_calendar(m["tr"], _mask(m["tr"], m["sess"], m["news"]), cal, off_calendar, m["label"])
    if cal.D and int(cal.cal[-1]) >= _HOLDOUT_ORD and not allow_holdout:
        raise HoldoutError("calendar reaches the holdout")
    return mem, cal


def _base(m: dict, cal: Cal) -> P.Base:
    tr, k = m["tr"], m["mask"]
    return P.Base(f"{m['label']}|{m['sess']}", cal.cal, tr.date[k], tr.te[k], tr.tx[k], tr.side[k], tr.g[k], tr.mae[k], tr.mfe[k],
                  tr.risk[k], {"sess": m["sess"]})


class Port10:
    """Port-like (days of walk tuples + parallel mfe lists) at 10 micros on a calendar; the walk rescales to the cell's micros.
    Same construction as holdout_score.Port2 / a3_pass2.P2 (incl. P2's per-day take upper bound U(m))."""

    def __init__(self, date, te, tx, side, g, mae, mfe, risk, cal):
        o = np.lexsort((te, date))
        pos = np.searchsorted(cal, date[o])
        self.days, self.mfe = [[] for _ in cal], [[] for _ in cal]
        for j, p in zip(o, pos):
            self.days[p].append((int(te[j]), int(tx[j]), int(side[j]), float(g[j]), float(mae[j]), 10, float(risk[j]), 0))
            self.mfe[p].append(float(mfe[j]))
        self.mx = max((len(d) for d in self.days), default=0)
        self.n_trades = int(len(date))
        self._U: dict = {}

    def U(self, m: int) -> np.ndarray:
        if m not in self._U:
            c = E.cost(m)
            self._U[m] = np.array([sum(max(m * f / 10.0 - c, 0.0) for f in fs) for fs in self.mfe])
        return self._U[m]


def _port10(mem: list, cal: Cal) -> Port10:
    arr = {a: np.concatenate([getattr(m["tr"], a)[m["mask"]] for m in mem]) for a in ("date", "te", "tx", "side", "g", "mae", "mfe", "risk")}
    return Port10(arr["date"], arr["te"], arr["tx"], arr["side"], arr["g"], arr["mae"], arr["mfe"], arr["risk"], cal.cal)


def norm_rules(rules: dict | None, micros=None) -> dict:
    """Canonical rules dict (0 = off). target_stop defaults to True (R's pass-2/3 + portfolio convention)."""
    d = dict(rules or {})
    unknown = set(d) - {"micros", "day_lock", "day_take", "day_stop", "max_day_tr", "target_take", "target_stop", "after_loss", "after_win", "policy"}
    if unknown:
        raise ValueError(f"unknown rule keys {sorted(unknown)}")
    return {"micros": int(micros or d.get("micros") or 0) or None, "day_lock": float(d.get("day_lock") or 0.0),
            "day_take": float(d.get("day_take") or 0.0), "day_stop": float(d.get("day_stop") or 0.0),
            "max_day_tr": int(d.get("max_day_tr") or 0), "target_take": bool(d.get("target_take", False)),
            "target_stop": bool(d.get("target_stop", True)), "after_loss": float(d.get("after_loss", 1.0) or 1.0),
            "after_win": float(d.get("after_win", 1.0) or 1.0)}


def _make_A(pv, fm: P.Firm, rl: dict) -> E.DayArr:
    """Day walk of a PV under one rules cell. Default rules -> portfolio.make_A itself (R's path); after_loss / after_win /
    target_stop=False -> the same evalcore.walk call with those values (+ the same exact re-walk shortcut)."""
    if rl["after_loss"] == 1.0 and rl["after_win"] == 1.0 and rl["target_stop"]:
        return P.make_A(pv, fm, P.norm_key(pv, rl["day_lock"], rl["day_take"], rl["day_stop"], rl["max_day_tr"]))
    A = E.walk(pv, fm.cap, (rl["max_day_tr"], rl["day_stop"], rl["day_lock"], rl["after_loss"], rl["after_win"], rl["target_stop"]),
               want_chk=True, micros=None, dll=fm.dll, day_take=rl["day_take"])
    orig, U = A.rewalk, pv.U
    scaled = rl["after_loss"] != 1.0 or rl["after_win"] != 1.0             # sizes may grow: the U bound no longer holds

    def rw(i, tt):
        if not scaled and tt > U[i] + 1e-6:
            return float(A.tot[i]), float(A.worst[i]), bool(A.trd[i]), float(A.wreal[i])
        return orig(i, tt)

    A.rewalk = rw
    return A


def _detail(o, d, boots: int, seed: int = E.SEED) -> dict:
    ps, bs = o == 1, o == 2
    x = {f"p{k}": float((ps & (d <= k)).mean()) for k in range(1, H_EVAL + 1)}
    x["bust5"] = float(bs.mean())
    x["bust_by"] = [float((bs & (d <= k)).mean()) for k in range(1, H_EVAL + 1)]
    x["neither5"] = float((o == 0).mean())
    x["med_days"] = float(np.median(d[ps])) if ps.any() else None
    if boots:
        cis = E.block_ci([ps & (d <= k) for k in range(1, H_EVAL + 1)] + [bs], boots=boots, seed=seed)
        for k in range(1, H_EVAL + 1):
            x[f"ci_p{k}"] = cis[k - 1]
        x["ci_bust5"] = cis[-1]
    return x


def _firm(firm: str) -> P.Firm:
    if firm not in EVAL_FIRMS:
        raise ValueError(f"eval firm {firm!r} not in {EVAL_FIRMS}")
    return P.firm(firm)


# ------------------------------------------------------------------ eval

def score_eval(trades, firm: str, rules: dict | None = None, model: str | None = None, *, micros: int | None = None, sess="all",
               news: str = "all", boots: int = 2000, calendar=None, allow_holdout: bool = False, off_calendar: str = "raise",
               arrays: bool = False, strategy: str | None = None, inputs: dict | None = None, both_sides: bool | None = None) -> dict:
    """P(pass <= k days) k=1..5, bust and block-bootstrap CIs of one config (or portfolio) under a firm's eval rules.

    trades: any trade source, or a member list [{'src', 'sess', 'micros'}]. firm: lucid | lucidpro | lucidpro_nodll | apex |
    apex_eod (R's rule files, 5-session horizon) or 'apex300_eval' (the Apex Legacy 300K evaluation: P(pass <= 10 / 20 trading
    days) and bust, see `score_apex300_eval`; strategy / inputs / both_sides feed its one-direction check and are ignored by
    R's firms). rules: see norm_rules (micros may be given there or as the keyword; default 10 = R's member default).
    model: headline breach model (default = the firm's primary); every model is in out['models'].
    -> {p1..p5, bust5, bust_by, med_days, ci_p1..ci_p5, ci_bust5 (headline model), models: {eod, realized, intraday}, walk, ...}.
    Rolling starts on the session calendar, 5-session horizon; CI = moving-block bootstrap (block 20, `boots` resamples)."""
    if firm == APEX300_EVAL:
        return score_apex300_eval(trades, rules, model, micros=micros, sess=sess, news=news, boots=boots, calendar=calendar,
                                  allow_holdout=allow_holdout, off_calendar=off_calendar, arrays=arrays, strategy=strategy,
                                  inputs=inputs, both_sides=both_sides)
    fm = _firm(firm)
    model = model or fm.prim
    if model not in MODELS:
        raise ValueError(f"breach model {model!r} not in {MODELS}")
    rl = norm_rules(rules, micros)
    mem, cal = _prep(trades, sess, rl["micros"], news, calendar, allow_holdout, off_calendar)
    for m in mem:
        m["micros"] = m["micros"] or rl["micros"] or 10
    members = [(_base(m, cal), m["micros"]) for m in mem]
    pv = P.PV(members, cal.D)
    out = {"firm": firm, "rules_id": fm.rid, "unconfirmed": not fm.confirmed, "primary": fm.prim, "model": model,
           "rules": {k: v for k, v in rl.items() if k != "micros"},
           "members": [{"label": m["label"], "sess": m["sess"], "micros": m["micros"], "trades": int(m["mask"].sum())} for m in mem],
           "window": cal.window, "n_trades": int(pv.n_trades)}
    if cal.D < H_EVAL or not pv.n_trades:
        out["skipped"] = "no trades or window shorter than 5 sessions"
        return out
    A = _make_A(pv, fm, rl)
    races = {b: E.race(cal.idx5, A, fm.r, b, rl["target_stop"], rl["target_take"]) for b in MODELS}
    out["models"] = {b: _detail(o, d, boots) for b, (o, d) in races.items()}
    out.update(out["models"][model])
    st = A.st
    out["walk"] = {"executed": st["executed"], "skipped": st["skipped"], "clipped": st["clipped"], "overlap_entries": st["overlap"],
                   "opposite_conflicts": int(st["conflicts"]), "max_concurrent_micros": st["max_conc"], "cap_violations": int(st["cap_viol"]),
                   "cap_ok": st["cap_viol"] == 0 and st["clipped"] == 0}
    out["cost"] = {"rt_over_risk": (st["cost"] / st["risk"]) if st["risk"] else None, "ok_lt_3pct": bool(st["risk"] and st["cost"] / st["risk"] < 0.03)}
    out["series"] = E._series(A)
    if arrays:
        out["arrays"] = {b: races[b] for b in MODELS}            # (outcome[S] 0 timeout | 1 pass | 2 bust, day[S]) per model
        out["daily"] = A
    return out


# ---- Apex Legacy 300K EVALUATION (L/apex300.py `eval_sim`; APEX300_RULES.md section 2b)

APEX300_EVAL = "apex300_eval"
APEX300_EVAL_H = 20                     # the attempt horizon simulated; P(pass) is reported at 10 and at 20 trading days
APEX300_EVAL_GRID = {"micros": [50, 100, 150, 200, 250, 300, 350], "day_lock": [0, 2000, 4000], "day_take": [0, 3000, 5000, 7500],
                     "day_stop": [0, 1500, 3000], "max_day_tr": [1, 0], "target_take": [0, 1]}        # pre-declared 2026-10-02


def _apex300_eval_prep(trades, rules, micros, sess, news, calendar, allow_holdout, off_calendar):
    """-> (apex300 module, norm rules, members, Cal, port, micros of the walk)."""
    ax = _ext()
    if ax is None or not hasattr(ax, "make_eval_spec"):
        raise RuntimeError("apex300.py (make_eval_spec / eval_sim) is not available")
    rl = norm_rules(rules, micros)
    mem, cal = _prep(trades, sess, rl["micros"], news, calendar, allow_holdout, off_calendar)
    if len(mem) == 1:
        port, mic = _port10(mem, cal), int(rl["micros"] or mem[0]["micros"] or 10)
    else:                                                        # portfolio: every member at its own micros
        for m in mem:
            m["micros"] = m["micros"] or rl["micros"] or 10
        port, mic = P.PV([(_base(m, cal), m["micros"]) for m in mem], cal.D), None
    return ax, rl, mem, cal, port, mic


def score_apex300_eval(trades, rules: dict | None = None, model: str | None = None, *, micros: int | None = None, sess="all",
                       news: str = "all", boots: int = 2000, calendar=None, allow_holdout: bool = False, off_calendar: str = "raise",
                       arrays: bool = False, strategy: str | None = None, inputs: dict | None = None, both_sides: bool | None = None,
                       coast: int = 0, variants: bool = True, **spec_over) -> dict:
    """The Apex Legacy 300K EVALUATION (firm 'apex300_eval'): profit goal $20,000 at a close, $7,500 threshold trailing the
    highest LIVE balance (intraday, open P&L included, never locks), 35 minis (350 micros), 7 traded days minimum, no daily
    limit, Apex commissions (apex300.make_eval_spec; conservative help-centre reading). Rolling starts with a full 20-session
    horizon; the 5-day criterion of the other firms cannot apply (7 days minimum), so the result is

      p_pass_10 / p_pass_20 (also p10 / p20), bust_10 / bust_20, neither_*, med_days, ci_p10 / ci_p20 / ci_bust20 (headline
      model), models: {pess (primary), nat, opt} = the intraday event orders of the Apex PA model.

    rules: day_take / day_lock / day_stop / max_day_tr / after_loss / after_win as everywhere (R's walk_day), target_take =
    flatten the day at the level that reaches the goal once the day count allows a pass; target_stop is not modelled (a pass is
    tested at the close). coast = n micros: once the goal is reached but days are missing, trade n micros (default 0 = keep the
    size; the result always carries `coast1`, the headline model with coast = 1 micro).
    `variants` (headline model): 'holder_rule_file' = the account holder's wording in homebase's apex-legacy-300k@2026-09-28
    (EOD trail locking at +$100, 1 day, R's costs), 'min_days_1', 'trail_eod'. spec_over: apex300.make_eval_spec overrides.
    Compliance: the prohibited-activities list applies to evaluations too -> `compliance` = {'one_direction': ok | FAIL |
    UNCHECKED} (apex300.static_checks: proven by the rows), `compliant`; the MAE / 5:1 / half-size rules are PA rules."""
    ax, rl, mem, cal, port, mic = _apex300_eval_prep(trades, rules, micros, sess, news, calendar, allow_holdout, off_calendar)
    S = ax.make_eval_spec(**spec_over)
    model = model or S.primary
    if model not in FUNDED_MODELS["apex"]:
        raise ValueError(f"model {model!r} not in {FUNDED_MODELS['apex']} for {S.name}")
    if mic is not None and mic > S.cap:
        raise ValueError(f"{mic} micros exceeds the {S.name} limit of {S.cap}")
    H = APEX300_EVAL_H
    frl = _funded_rules(rl)
    out = {"firm": APEX300_EVAL, "variant": S.name, "primary": S.primary, "model": model, "micros": mic, "horizons": list(ax.EVAL_H),
           "rules": {**{k: frl[k] for k in ("day_take", "day_lock", "day_stop", "max_day_tr")}, "target_take": rl["target_take"]},
           "coast": int(coast), "window": cal.window, "n_starts": int(max(cal.D - H + 1, 0)),
           "n_trades": int(sum(int(m["mask"].sum()) for m in mem)),
           "members": [{"label": m["label"], "sess": m["sess"], "micros": m["micros"] or mic, "trades": int(m["mask"].sum())} for m in mem],
           "spec": {k: getattr(S, k) for k in ("target", "mll", "trail", "lock_at", "cap", "min_days", "commission")},
           "unconfirmed": sorted(ax.EVAL_UNCONFIRMED), "eval300": dict(ax.EVAL300)}
    stc = ax.static_checks(port, strategy, inputs, both_sides, _raw_members(mem), allow_holdout=allow_holdout)
    out["compliance"] = {"one_direction": stc["one_direction"]}
    out["one_direction_basis"] = stc.get("one_direction_basis")
    out["compliant"] = stc["one_direction"] == "ok"
    out["warnings"] = [w for w in ax.ACCOUNT_WARNINGS if w.startswith(("AUTOMATION", "CROSS_ACCOUNT", "COPY"))]
    if cal.D < H or not out["n_trades"]:
        out["skipped"] = f"no trades or window shorter than {H} sessions"
        return out
    desk_window_wait()

    def run(spec, order, c=coast):
        return ax.eval_lifecycle(spec, ax.eval_src(spec, port, frl, mic), H, order, target_take=rl["target_take"], coast=c)

    out["models"] = {}
    for m in FUNDED_MODELS["apex"]:
        o, d = run(S, m)
        mm = ax.eval_metrics(o, d)
        if boots:
            cis = E.block_ci([(o == 1) & (d <= 10), o == 1, o == 2], block=2 * H, boots=boots)
            mm["ci_p10"], mm["ci_p20"], mm["ci_bust20"] = cis
        out["models"][m] = mm
        if arrays:
            out.setdefault("arrays", {})[m] = (o, d)
    out.update(out["models"][model])
    out.update(p10=out["p_pass_10"], p20=out["p_pass_20"], bust10=out["bust_10"], bust20=out["bust_20"])
    out["coast1"] = ax.eval_metrics(*run(S, model, 1))
    if variants:
        out["variants"] = {k: ax.eval_metrics(*run(ax.make_eval_spec(**{**spec_over, **v}), model)) for k, v in ax.EVAL_VARIANTS.items()}
    return out


def search_apex300_eval(trades, *, sess="all", news: str = "all", grid: dict | None = None, model: str | None = None, boots: int = 2000,
                        calendar=None, allow_holdout: bool = False, off_calendar: str = "raise", out_csv=None, strategy: str | None = None,
                        inputs: dict | None = None, both_sides: bool | None = None, **spec_over) -> dict:
    """Rule grid of the Apex Legacy 300K evaluation for one config: APEX300_EVAL_GRID (micros x day_lock x day_take x day_stop x
    max_day_tr x target_take; `grid` overrides axes), headline model only (default the primary 'pess'), single process.
    rows: one per cell {micros, ..., n_rules, p10, p20, bust10, bust20, stab_p20, stab_p10}. picks (search_rules conventions:
    the cell maximising the STABLE value = median of the cell and its +-1-step neighbours; ties fewer rules, then smaller
    size): 'primary' = stable P(pass <= 20 d), 'p10' = stable P(pass <= 10 d); each pick carries the full
    score_apex300_eval result of its cell (`detail`: all models, CIs, coast1, variants, one-direction check)."""
    ax = _ext()
    g = {a: list((grid or {}).get(a, APEX300_EVAL_GRID[a])) for a in AX}
    S = ax.make_eval_spec(**spec_over)
    model = model or S.primary
    _, _, mem, cal, port, _ = _apex300_eval_prep(trades, None, None, sess, news, calendar, allow_holdout, off_calendar)
    if len(mem) != 1:
        raise ValueError("search_apex300_eval takes ONE trade source (the grid sets the micros)")
    shape = tuple(len(g[a]) for a in AX)
    H = APEX300_EVAL_H
    V = {k: np.full(shape, np.nan) for k in ("p10", "p20", "bust10", "bust20")}
    nr = np.zeros(shape)
    cache: dict = {}
    for ci in np.ndindex(*shape):
        m, dl, dtk, ds, mt, tt = (g[a][i] for a, i in zip(AX, ci))
        nr[ci] = (dl > 0) + (dtk > 0) + (ds > 0) + (mt > 0) + tt
        if m > S.cap or cal.D < H:
            continue
        key = _norm_walk(port, m, dl, dtk, ds, mt) + (int(bool(tt)),)
        if key not in cache:
            desk_window_wait()
            src = ax.eval_src(S, port, {"day_lock": key[1], "day_take": key[2], "day_stop": key[3], "max_day_tr": key[4]}, int(m))
            mm = ax.eval_metrics(*ax.eval_lifecycle(S, src, H, model, target_take=bool(tt)))
            cache[key] = (mm["p_pass_10"], mm["p_pass_20"], mm["bust_10"], mm["bust_20"])
        for k, v in zip(("p10", "p20", "bust10", "bust20"), cache[key]):
            V[k][ci] = v
    scored = bool(np.isfinite(V["p20"]).any())                   # no cell scored (sizes above the cap, window too short): no rows
    stab = {k: (_stable_masked(V[k]) if scored else V[k]) for k in ("p20", "p10")}
    rows = []
    for ci in np.ndindex(*shape):
        if np.isnan(V["p20"][ci]):
            continue
        rows.append({"firm": APEX300_EVAL, "model": model, **{a: g[a][i] for a, i in zip(AX, ci)}, "n_rules": int(nr[ci]),
                     **{k: float(V[k][ci]) for k in V}, "stab_p20": float(stab["p20"][ci]), "stab_p10": float(stab["p10"][ci])})
    picks = {}
    if rows:
        for nm, k in (("primary", "p20"), ("p10", "p10")):
            ci = pick(stab[k], nr)
            cell = {a: g[a][i] for a, i in zip(AX, ci)}
            det = score_apex300_eval(trades, {x: cell[x] for x in AX[1:]}, model, micros=cell["micros"], sess=sess, news=news, boots=boots,
                                     calendar=calendar, allow_holdout=allow_holdout, off_calendar=off_calendar, strategy=strategy,
                                     inputs=inputs, both_sides=both_sides, **spec_over)
            picks[nm] = {"rules": cell, "index": list(ci), "stab": float(stab[k][ci]), "raw_max": float(np.nanmax(V[k])),
                         "n_rules": int(nr[ci]), "detail": det}
    out = {"firm": APEX300_EVAL, "primary": S.primary, "model": model, "grid": g, "axes": list(AX), "shape": list(shape),
           "cells": int(np.prod(shape)), "walks": len(cache), "window": cal.window, "n_trades": port.n_trades, "rows": rows, "picks": picks}
    if out_csv:
        _write_csv(rows, out_csv)
    return out


# ---- rule search (R pass-2/3 grids; a3p3.search3 conventions)

AX = ("micros", "day_lock", "day_take", "day_stop", "max_day_tr", "target_take")
_LP = {"micros": [10, 20, 30, 40], "day_lock": [0, 1000, 2000], "day_take": [0, 1500, 2000, 3000], "day_stop": [0, 1000, 2000],
       "max_day_tr": [1, 0], "target_take": [0, 1]}
EVAL_GRIDS = {          # copies of a3_pass2.GR (lucid, apex), a3p2_lp._G (lucidpro*), a3p3 (apex_eod); tests assert they equal R's
    "lucid": {"micros": [10, 20, 30, 40], "day_lock": [0, 750, 1000, 1500], "day_take": [0, 1000, 1250, 1500],
              "day_stop": [0, 1000, 2000], "max_day_tr": [1, 0], "target_take": [0, 1]},
    "lucidpro": _LP, "lucidpro_nodll": _LP,
    "apex": {"micros": [20, 40, 60, 80, 100], "day_lock": [0, 1000, 2000], "day_take": [0, 1500, 2000, 3000],
             "day_stop": [0, 1000, 2000, 3000], "max_day_tr": [1, 0], "target_take": [0, 1]},
    "apex_eod": {"micros": [20, 30, 40, 50, 60], "day_lock": [0, 1000, 2000], "day_take": [0, 1500, 2000, 3000],
                 "day_stop": [0, 500, 1000], "max_day_tr": [1, 0], "target_take": [0, 1]},
}


def stable(v: np.ndarray) -> np.ndarray:
    """Median of a cell and its +-1-step neighbours on every axis (= a3_rules.stable / portfolio.stable)."""
    return P.stable(v)


def pick(v: np.ndarray, nr: np.ndarray) -> tuple:
    """argmax of v; ties -> fewer active rules, then smaller size (= a3_pass2.pick; NaN cells are never picked)."""
    mi = np.arange(v.shape[0]).reshape((-1,) + (1,) * (v.ndim - 1))
    x = v - 1e-7 * nr - 1e-9 * mi
    return tuple(int(i) for i in np.unravel_index(int(np.argmax(np.where(np.isnan(x), -np.inf, x))), v.shape))


def _stable_masked(v: np.ndarray) -> np.ndarray:
    sv = stable(v)
    sv[np.isnan(v)] = np.nan                    # a cell that was not scored (size above the cap) has no stable value
    return sv


def _norm_walk(port, m, dl, dtk, ds, mt) -> tuple:
    """= a3_pass2.norm_walk: rules that cannot matter are zeroed (cache key only; the results are identical)."""
    mt_e = 0 if mt >= port.mx else mt
    dl_e = 0 if (port.mx <= 1 or mt_e == 1) else dl
    if port.mx <= 1:
        mt_e = 0
    return (m, dl_e, dtk, ds, mt_e)


def _make_A10(port: Port10, r: dict, dll: float, m, dl, dtk, ds, mt) -> E.DayArr:
    """= a3_pass2.make_A: evalcore.walk at m micros, target_stop on; re-walks of days that cannot reach the level are skipped (exact)."""
    A = E.walk(port, r["cap_micros"], (int(mt), float(ds), float(dl), 1.0, 1.0, True), want_chk=True, micros=int(m), dll=dll, day_take=float(dtk))
    orig, U = A.rewalk, port.U(int(m))

    def rw(i, tt):
        if tt > U[i] + 1e-6:
            return float(A.tot[i]), float(A.worst[i]), bool(A.trd[i]), float(A.wreal[i])
        return orig(i, tt)

    A.rewalk = rw
    return A


def search_rules(trades, firm: str, *, sess="all", news: str = "all", grid: dict | None = None, boots: int = 2000, calendar=None,
                 allow_holdout: bool = False, off_calendar: str = "raise", keep_arrays: bool = False, out_csv=None) -> dict:
    """Rule grid search for one config under a firm, R pass-3 conventions (a3p3.search3 + a3_rules.stable + a3_pass2.pick):
    axes micros x day_lock x day_take x day_stop x max_day_tr x target_take (EVAL_GRIDS[firm]; `grid` overrides axes; target_stop
    always on, the rule file's soft daily limit applies automatically), all three breach models per cell, rolling 5-day starts.
    Picks: p5_<model> = the cell maximising the STABLE P5 (median of the cell and its +-1-step neighbours; ties fewer rules, then
    smaller size) per model, speed_p1 / speed_p3 = same on P(pass<=1d) / P(pass<=3d) under the primary model, 'primary' = p5_<primary>.
    -> {firm, primary, grid, shape, rows: [one dict per cell], picks: {name: {rules, stab, raw_max, n_rules, models: {..detail..}}}}
    (+ PS [3, cells, S] bool pass flags, nr, for R's wf_offline.reduce_cfg when keep_arrays). A member list gets the grid's
    micros on every member (R's evalcore.search convention). firm 'apex300_eval' -> `search_apex300_eval` (its own grid, picks
    on P(pass <= 20 d) / P(pass <= 10 d))."""
    if firm == APEX300_EVAL:
        return search_apex300_eval(trades, sess=sess, news=news, grid=grid, boots=boots, calendar=calendar, allow_holdout=allow_holdout,
                                   off_calendar=off_calendar, out_csv=out_csv)
    fm = _firm(firm)
    g = {a: list((grid or {}).get(a, EVAL_GRIDS[firm][a])) for a in AX}
    mem, cal = _prep(trades, sess, None, news, calendar, allow_holdout, off_calendar)
    port = _port10(mem, cal)
    r, dll, prim = fm.r, fm.dll, fm.prim
    shape = tuple(len(g[a]) for a in AX)
    S = cal.S
    P5, B5 = (np.full((3,) + shape, np.nan) for _ in range(2))
    PK = {k: np.full((3,) + shape, np.nan) for k in (1, 2, 3)}
    nr = np.zeros(shape)
    PSa = np.zeros((3, int(np.prod(shape)), S), bool) if keep_arrays else None
    cache: dict = {}
    for flat, ci in enumerate(np.ndindex(*shape)):
        m, dl, dtk, ds, mt, tt = (g[a][i] for a, i in zip(AX, ci))
        nr[ci] = (dl > 0) + (dtk > 0) + (ds > 0) + (mt > 0) + tt
        if m > fm.cap:                                            # custom grids only: sizes above the firm cap are not scored
            continue
        key = _norm_walk(port, m, dl, dtk, ds, mt)
        if key not in cache:
            desk_window_wait()
            A = _make_A10(port, r, dll, *key)
            res = {}
            for t_ in (0, 1):
                res[t_] = []
                for mod in MODELS:
                    o, d = E.race(cal.idx5, A, r, mod, True, bool(t_))
                    ps = o == 1
                    res[t_].append((float(ps.mean()), float((o == 2).mean()), float((ps & (d <= 1)).mean()), float((ps & (d <= 2)).mean()),
                                    float((ps & (d <= 3)).mean()), ps if keep_arrays else None))
            cache[key] = res
        v = cache[key][int(bool(tt))]
        for k in range(3):
            P5[(k,) + ci], B5[(k,) + ci] = v[k][0], v[k][1]
            PK[1][(k,) + ci], PK[2][(k,) + ci], PK[3][(k,) + ci] = v[k][2], v[k][3], v[k][4]
            if keep_arrays:
                PSa[k, flat] = v[k][5]
    pk = MODELS.index(prim)
    stab = {mod: _stable_masked(P5[k]) for k, mod in enumerate(MODELS)}
    sel = {f"p5_{mod}": (pick(stab[mod], nr), stab[mod], float(np.nanmax(P5[k]))) for k, mod in enumerate(MODELS)}
    for nm, kk in (("speed_p1", 1), ("speed_p3", 3)):
        sv = _stable_masked(PK[kk][pk])
        sel[nm] = (pick(sv, nr), sv, float(np.nanmax(PK[kk][pk])))
    rows = []
    for ci in np.ndindex(*shape):
        if np.isnan(P5[(0,) + ci]):
            continue
        row = {"firm": firm, **{a: g[a][i] for a, i in zip(AX, ci)}, "n_rules": int(nr[ci])}
        for k, mod in enumerate(MODELS):
            row[f"p5_{mod}"], row[f"bust5_{mod}"], row[f"stab_{mod}"] = float(P5[(k,) + ci]), float(B5[(k,) + ci]), float(stab[mod][ci])
        row["p1"], row["p2"], row["p3"] = (float(PK[kk][(pk,) + ci]) for kk in (1, 2, 3))
        rows.append(row)
    picks = {}
    for nm, (ci, sv, raw) in sel.items():
        cell = {a: g[a][i] for a, i in zip(AX, ci)}
        A = _make_A10(port, r, dll, *_norm_walk(port, *[cell[a] for a in AX[:5]]))
        det = {mod: _detail(*E.race(cal.idx5, A, r, mod, True, bool(cell["target_take"])), boots) for mod in MODELS}
        picks[nm] = {"rules": cell, "index": list(ci), "stab": float(sv[ci]), "raw_max": raw, "n_rules": int(nr[ci]), "models": det,
                     "net_rules": float(A.tot.sum()), "executed": int(A.st["executed"])}
    picks["primary"] = picks[f"p5_{prim}"]
    out = {"firm": firm, "rules_id": fm.rid, "primary": prim, "grid": g, "axes": list(AX), "shape": list(shape), "cells": int(np.prod(shape)),
           "walks": len(cache), "window": cal.window, "n_trades": port.n_trades, "rows": rows, "picks": picks}
    if keep_arrays:
        out["PS"], out["nr"], out["P5"], out["B5"], out["P1"], out["P3"], out["cal"] = PSa, nr, P5, B5, PK[1][pk], PK[3][pk], cal.cal
    if out_csv:
        _write_csv(rows, out_csv)
    return out


def _write_csv(rows: list, path) -> Path:
    import csv
    p = Path(path)
    if not p.is_absolute():
        p = OUT / p
    if R in p.resolve().parents:
        raise ValueError("refusing to write into R")
    p.parent.mkdir(parents=True, exist_ok=True)
    cols = [k for k in rows[0] if not k.startswith("_")] if rows else []
    with p.open("w", newline="") as fh:
        w = csv.DictWriter(fh, cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
    return p


# ------------------------------------------------------------------ funded

FUNDED_VARIANTS = {"flex": ("flex", None), "flex_dll": ("flex", 1200), "pro_dll": ("pro", 1200), "pro_nodll": ("pro", 0), "apex": ("apex", None)}
FUNDED_MODELS = {"lucid": ("realized", "eod", "intraday"), "apex": ("pess", "nat", "opt")}
EXT_MODULE = "apex300"                 # L/apex300.py: Apex Legacy 300K PA ('apex300_pa') and the 50K PA with start states ('apex50_pa')
_EXT: dict = {}


def _ext():
    """L/apex300.py (another component of this pilot), imported lazily: its own account loop (start states, 300K rules) on
    R's day walk. None when the module is absent."""
    if "m" not in _EXT:
        _EXT["m"] = None
        if (L / f"{EXT_MODULE}.py").exists():
            import importlib
            if str(L) not in sys.path:
                sys.path.insert(0, str(L))
            _EXT["m"] = importlib.import_module(EXT_MODULE)
    return _EXT["m"]


def _ext_firms() -> tuple:
    m = _ext()
    return tuple(getattr(m, "EXT_FIRMS", ())) if m else ()


def funded_variants() -> list[str]:
    return list(FUNDED_VARIANTS) + list(_ext_firms())


def funded_spec(firm, **over) -> F.Spec:
    """'flex' | 'flex_dll' | 'pro_dll' | 'pro_nodll' | 'apex' (R's funded rule sets), 'apex300_pa' | 'apex50_pa' (L/apex300.py),
    or a funded.Spec (returned as is)."""
    if isinstance(firm, F.Spec):
        if getattr(firm, "kind", None) == "apex_eval":
            raise ValueError("an apex300_eval spec is an EVALUATION: score it with score_eval(trades, 'apex300_eval', ...)")
        return firm
    if firm in FUNDED_VARIANTS:
        f, dll = FUNDED_VARIANTS[firm]
        return F.make_spec(f, dll, **over)
    if firm in _ext_firms():
        return _ext().make_spec(firm, **over)
    raise ValueError(f"funded firm {firm!r} not in {funded_variants()}")


def start_states(firm="apex300_pa") -> tuple:
    """Named start states of a funded firm: ('fresh', 'plus3000', 'plus7600') for the L/apex300.py firms (a profit in $ and
    apex300.Start(...) work too; apex300.resolve_start validates them), ('fresh',) for R's firms (fresh account only)."""
    S = funded_spec(firm)
    return tuple(_ext().STARTS) if getattr(S, "ext", False) else ("fresh",)


def _raw_members(mem: list):
    """The members' raw trade rows for apex300's per-trade checks (stop, target, 5:1, opposite-side overlap): -> [{'src': rows,
    'sess': ...}] or None when a member carries no rows (a bare TR object)."""
    out = []
    for m in mem:
        rows = getattr(m["tr"], "rows", None)
        if rows is None:
            return None
        out.append({"src": rows, "sess": m["sess"], "both_sides_sessions": getattr(m["tr"], "both_sides_sessions", None)})
    return out


def apex_gate(S, port, mem: list, *, micros, rules: dict, cut_share, start="fresh", strategy=None, inputs=None, both_sides=None,
              allow_holdout: bool = False) -> dict:
    """THE Apex compliance gate (L/apex300.compliance, scaled to the spec: its trailing threshold, half-size cap, MAE limit;
    never R's 50K constants) for one config: -> {flags, noncompliant, compliance: {one_direction, stop_5x_target, mae_rule:
    'ok' | 'FAIL' | 'UNCHECKED'}, trade_checks, ...}. Fail closed: UNCHECKED counts as non-compliant, so pass
    strategy / inputs / both_sides (False = the family never works orders on both sides)."""
    return _ext().compliance(S, port, micros=micros, rules=rules, cut_share=cut_share, start=start, strategy=strategy, inputs=inputs,
                             both_sides=both_sides, trades=_raw_members(mem), allow_holdout=allow_holdout)


def _lifecycle(S, src, policy, H, model, start="fresh") -> list:
    """Attempt tuples of every rolling start: R's funded.lifecycle, or L/apex300.lifecycle for its extended specs (start states,
    the spec's own commission schedule)."""
    if getattr(S, "ext", False):
        return _ext().lifecycle(S, src, policy, H, model, start)
    if start not in ("fresh", 0, 0.0, None):
        raise ValueError(f"start={start!r}: R's funded firms are modelled from a fresh account only")
    return F.lifecycle(S, src, policy, H, model)


def _funded_rules(rl: dict) -> dict:
    return {k: rl[k] for k in ("day_take", "day_lock", "day_stop", "max_day_tr", "after_loss", "after_win")}


def _start_arrays(res: list) -> dict:
    n = len(res)
    a = {k: np.zeros(n) for k in ("first", "n40", "bust")}
    for i, (b, pays, _cuts, _ex) in enumerate(res):
        a["bust"][i] = b
        if pays:
            a["first"][i] = pays[0][0]
            a["n40"][i] = sum(p[2] for p in pays if p[0] <= 40)
    return a


def score_funded(trades, firm, policy=500, *, micros: int | None = None, rules: dict | None = None, sess="all", news: str = "all",
                 model: str | None = None, boots: int = 2000, H: int = H_FUNDED, calendar=None, allow_holdout: bool = False,
                 off_calendar: str = "raise", strategy: str | None = None, inputs: dict | None = None, both_sides: bool | None = None,
                 start="fresh", arrays: bool = False, **spec_over) -> dict:
    """Funded / PA lifecycle of one config (rolling starts, H = 60 sessions) under R's funded.py, or L/apex300.py for
    'apex300_pa' / 'apex50_pa'.

    firm: flex | flex_dll | pro_dll | pro_nodll | apex | apex300_pa | apex50_pa | a funded.Spec. policy: payout-request threshold
    (500 | 1000 | 1500 | 'max' | None = never; apex300_pa: 500 | 1500 | 2500 | 'max'). rules: day_take / day_lock / day_stop /
    max_day_tr (+ micros); target_take is eval-only and ignored. model: headline (default the Spec's primary: Lucid realized,
    Apex PA pess); every model is returned. start: 'fresh' (default) | 'plus3000' | 'plus7600' | profit $ | apex300.Start(...)
    (apex300 firms only; start_states(firm)). spec_over: spec options, e.g. cons_base='balance', **apex300.r_compat(firm).
    -> {e_net_40 (E[$ to trader in 40 trading days]), e_net_40_ci, p_bust_pre_first, p_pay_20/40/60, med_days_first, ...
        (headline model), models: {..}}.
    Apex kinds add the compliance gate (SPEC: mandatory): apex_flags, compliance {one_direction, stop_5x_target, mae_rule},
    noncompliant (any criterion FAILED or UNCHECKED), compliant, trade_checks, mae_over_limit_share ...; apex300 firms also
    cons_base + cons_alt (the same metrics under the OTHER reading of the unconfirmed consistency base), commission, warnings.
    `strategy` / `inputs` / `both_sides` feed the gate: both_sides=True for OCO / straddle entries, False to DECLARE one direction."""
    S = funded_spec(firm, **spec_over)
    apex = S.kind == "apex"
    ext = bool(getattr(S, "ext", False))
    models = FUNDED_MODELS["apex" if apex else "lucid"]
    model = model or S.primary
    if model not in models:
        raise ValueError(f"model {model!r} not in {models} for {S.name}")
    rl = norm_rules(rules, micros)
    mem, cal = _prep(trades, sess, rl["micros"], news, calendar, allow_holdout, off_calendar)
    frl = _funded_rules(rl)
    if len(mem) == 1:
        port, mic = _port10(mem, cal), int(rl["micros"] or mem[0]["micros"] or 10)
    else:                                                        # portfolio: every member at its own micros
        for m in mem:
            m["micros"] = m["micros"] or rl["micros"] or 10
        port, mic = P.PV([(_base(m, cal), m["micros"]) for m in mem], cal.D), None
    if mic is not None and mic > S.cap:
        raise ValueError(f"{mic} micros exceeds the {S.name} limit of {S.cap}")
    out = {"variant": S.name, "kind": S.kind, "primary": S.primary, "model": model, "policy": policy, "micros": mic,
           "start": _ext().start_name(start) if ext else start,
           "rules": {k: frl[k] for k in ("day_take", "day_lock", "day_stop", "max_day_tr")}, "window": cal.window,
           "n_starts": int(max(cal.D - H + 1, 0)), "trades": int(sum(int(m["mask"].sum()) for m in mem)),
           "members": [{"label": m["label"], "sess": m["sess"], "micros": m["micros"] or mic, "trades": int(m["mask"].sum())} for m in mem]}
    if cal.D < H:
        out["skipped"] = f"window shorter than {H} sessions"
        return out
    src = F.DaySrc(port, frl, mic, events=apex)                  # apex300 re-bases it on the spec's commission schedule
    desk_window_wait()
    out["models"] = {}
    for m in models:
        res = _lifecycle(S, src, policy, H, m, start)
        mm = F.metrics(res, H)
        a = _start_arrays(res)
        if boots:
            mm["e_net_40_ci"] = E.block_ci([a["n40"]], block=60, boots=boots)[0]
            mm["p_pay_20_ci"] = E.block_ci([((a["first"] > 0) & (a["first"] <= 20)).astype(float)], block=60, boots=boots)[0]
        out["models"][m] = mm
        if arrays:
            out.setdefault("arrays", {})[m] = a
    out.update(out["models"][model])
    if not apex:
        return out
    cut = out["models"][S.primary]["cut_share"]
    ax = _ext()
    if ext:
        S2 = ax.other_cons(S)
        out.update(cons_base=S.cons_base, commission=S.commission, warnings=list(ax.ACCOUNT_WARNINGS), unconfirmed=sorted(ax.UNCONFIRMED),
                   cons_alt={"cons_base": S2.cons_base, **{m: F.metrics(_lifecycle(S2, src, policy, H, m, start), H) for m in models}})
        gate = apex_gate(S, port, mem, micros=mic, rules=frl, cut_share=cut, start=start, strategy=strategy, inputs=inputs,
                         both_sides=both_sides, allow_holdout=allow_holdout)
        out.update({k: v for k, v in gate.items() if k != "flags"}, apex_flags=gate["flags"])
    else:                                                        # R's 50K 'apex': R's own flags + R's static MAE screen
        out["apex_flags"] = F.apex_flags(strategy, inputs, frl, cut)
        if both_sides and "OCO_both_side_orders" not in out["apex_flags"]:
            out["apex_flags"].insert(0, "OCO_both_side_orders")
        out["mae_over_limit_share"] = F.mae_over_limit_share(port, mic, S.half, S.mae_min)
        out["noncompliant"] = bool(cut > 0.02)                   # R's MAE-only screen, used when apex300.py is absent
        if ax is not None:                                       # the full gate, on the 50K spec of L/apex300.py
            gate = apex_gate(ax.make_spec("apex50_pa", **ax.r_compat("apex50_pa")), port, mem, micros=mic, rules=frl, cut_share=cut,
                             strategy=strategy, inputs=inputs, both_sides=both_sides, allow_holdout=allow_holdout)
            out.update(compliance=gate["compliance"], trade_checks=gate["trade_checks"], gate_flags=gate["flags"],
                       noncompliant=gate["noncompliant"], one_direction_basis=gate.get("one_direction_basis"))
    out["compliant"] = not out["noncompliant"]
    return out


def score_funded_starts(trades, firm="apex300_pa", policy=500, starts=None, **kw) -> dict:
    """score_funded from every start state of the firm (default start_states(firm): fresh / plus3000 / plus7600) -> {start: result}."""
    out = {}
    for s in (starts or start_states(firm)):
        r = score_funded(trades, firm, policy, start=s, **kw)
        out[r["start"]] = r
    return out


def funded_grid(firm, grid: dict | None = None) -> dict:
    """The search grid of a funded firm with `grid` overrides: R's funded.GRID (+ default micros) for R's firms and apex50_pa,
    L/apex300.GRID (300K-scaled: sizes to the half cap, day rules to $3,000, policies 500 / 1500 / 2500 / max) for apex300_pa."""
    S = funded_spec(firm)
    if getattr(S, "ext", False) and S.name != "apex50_pa":
        ax = _ext()
        g = {**ax.GRID, **(grid or {})}
        if not grid or "policy" not in grid:
            g["policy"] = list(ax.POLICIES.get(S.name, ax.POLICIES["apex300_pa"]))
    else:
        g = {**F.GRID, **(grid or {})}
        g["micros"] = g["micros"] or F.default_micros(S)
    g["micros"] = [m for m in g["micros"] if m <= S.cap]
    return {a: list(g[a]) for a in F.AXES}


def search_funded(trades, firm, *, sess="all", news: str = "all", grid: dict | None = None, model: str | None = None, workers: int = 1,
                  H: int = H_FUNDED, calendar=None, allow_holdout: bool = False, off_calendar: str = "raise", out_csv=None,
                  cut_ok: float = 0.02, start="fresh", strategy: str | None = None, inputs: dict | None = None,
                  both_sides: bool | None = None, **spec_over) -> dict:
    """Funded grid search (micros x day_take x day_lock x day_stop x max_day_tr x policy, + stability columns): R's funded.search
    for R's firms, L/apex300.search for apex300_pa / apex50_pa (start states; grid = funded_grid(firm, grid), i.e. apex300.GRID
    for the 300K; both consistency readings as `<metric>_cons_<other>` columns).
    Picks = funded.pick_cells over the ELIGIBLE rows:
      R's apex      MAE-rule cut share <= cut_ok (as R's funded_search);
      apex300 firms apex300.compliant(rows): every row carries the SAME gate as score_funded (apex_one_direction /
                    apex_stop_5x_target / apex_mae_rule, apex_flags from apex300.flags, apex_noncompliant), 300K-scaled.
                    Fail closed: pass strategy / inputs / both_sides or NO row is eligible.
    workers <= 8 (fork pool; every cell honours the offline compute windows)."""
    if workers > 8:
        raise ValueError("<= 8 worker processes (house rule)")
    S = funded_spec(firm, **spec_over)
    mem, cal = _prep(trades, sess, None, news, calendar, allow_holdout, off_calendar)
    port = _port10(mem, cal)
    desk_window_wait()
    out = {"variant": S.name, "model": model or S.primary, "start": start, "window": cal.window}
    if getattr(S, "ext", False):
        ax = _ext()
        g = funded_grid(S, grid)
        rows = ax.search(port, S, g, model, H, workers, start, strategy=strategy, inputs=inputs, both_sides=both_sides,
                         trades=_raw_members(mem), allow_holdout=allow_holdout)
        ok = ax.compliant(rows)
        gate = {k: sorted({r[k] for r in rows}) for k in ("apex_one_direction", "apex_stop_5x_target", "apex_mae_rule")}
        out.update(start=ax.start_name(start), grid=g, cons_base=S.cons_base, commission=S.commission, gate=gate,
                   warnings=list(ax.ACCOUNT_WARNINGS), unconfirmed=sorted(ax.UNCONFIRMED))
    else:
        if start not in ("fresh", 0, 0.0, None):
            raise ValueError(f"start={start!r}: R's funded firms are modelled from a fresh account only")
        rows = F.search(port, S, grid, model, H, workers)
        ok = [r for r in rows if not (S.kind == "apex" and r.get("cut_share", 0.0) > cut_ok)]
    out.update(rows=rows, eligible=len(ok), picks=F.pick_cells(ok))
    if out_csv:
        _write_csv(rows, out_csv)
    return out


# ------------------------------------------------------------------ controls (C1 day-matched random, C2 direct ledgers)

def _pool_tr(control_trades, allow_holdout: bool):
    srcs = control_trades if (isinstance(control_trades, (list, tuple)) and not _is_rows(control_trades)) else [control_trades]
    trs = [load_trades(s, allow_holdout) for s in srcs]
    return trs[0] if len(trs) == 1 else E.concat_tr(trs)


def c1_pool(inputs: dict | None = None, fam: str | None = None) -> dict:
    """The C1 random-entry pool for a config's EXIT PROFILE (tf, stop_mode, stop_val, tgt_r, exit_bars, trail_atr), resolved by
    R's own catalog (evalcore.profile_from + resolve_pool on R's ledger: the tester's random-entry runs, in-sample bundles).
    inputs: the family's Template inputs (missing keys = the template defaults: atr 1.5 x 2R). The screen defaults at tf 1 / 5 /
    15 have exact pools (6 runs each). -> {'srcs': [R sources for lift_vs_control / walk_forward], 'exact': bool, 'flag': '' or
    'NEAREST profile ...' (a pool with another exit profile: report the flag with the lift), 'profile': the pool's profile}."""
    pl = E.resolve_pool(E.profile_from(fam, dict(inputs or {})))
    if not pl["srcs"]:
        raise RuntimeError(f"no C1 control pool: {pl['flag']}")
    return {"srcs": list(pl["srcs"]), "exact": bool(pl["exact"]), "flag": pl["flag"], "profile": pl["profile"], "dist": pl["dist"]}


def best_of_nulls(batch, q: float = 95.0, stat: str = "t") -> dict:
    """THE BEST-OF-NULLS BAR of a batch (EDGE_SPEC E) = library.best_of_nulls (edge-library root; numpy only, every root): the
    95th percentile, over the batch's null replicates (one null run of one unit-session over the menu: a seed of the random
    control, the time-shuffle null or the C2 feature shuffle), of each replicate's BEST cell. A claim must beat it."""
    if str(L.parent) not in sys.path:
        sys.path.insert(0, str(L.parent))
    import library
    return library.best_of_nulls(batch, q=q, stat=stat)


def sess_name(sess) -> str:
    """'nyam' | 'nyam+pm' | ['nyam', 'pm'] | None -> 'nyam' | 'nyam+pm' | 'nyam+pm' | 'all' (R's spelling of a session set)."""
    return "+".join(sess) if isinstance(sess, (list, tuple)) else str(sess or "all")


def default_seed(label: str, sess, kind: str = "eval") -> int:
    """R's control seeds: eval crc32('<cfg>|<sess>') % 100000 (portfolio.Ctx.controls), funded crc32('fund|<cfg>|<sess>')."""
    cid = f"{label}|{sess_name(sess)}"
    return zlib.crc32(cid.encode()) % 100000 if kind == "eval" else zlib.crc32(f"fund|{cid}".encode())


def daymatched(trades, pool, *, sess="all", news: str = "all", K: int = 10, seed: int | None = None, allow_holdout: bool = False,
               no_overlap: bool = True, label: str | None = None) -> list[dict]:
    """K day-matched control ledgers for a config from a random-entry pool (evalcore.daymatched_controls, unchanged): for every
    (date, session) with k config trades, k pool trades of the same date + session (uniform, without replacement, no overlap);
    shortfalls come from the same session on the nearest dates (flagged `fb`). -> list of dicts of arrays (date, te, tx, side, g,
    mae, mfe, risk, sess, fb, fb_share, short, n). seed default: default_seed(label or the source's label, sess)."""
    tr = load_trades(trades, allow_holdout, label=label)
    m = _mask(tr, sess, news)
    sub = SimpleNamespace(date=tr.date[m], sess=tr.sess[m], n=int(m.sum()))
    pl = _pool_tr(pool, allow_holdout)
    seed = default_seed(label or getattr(tr, "label", "inline"), sess) if seed is None else seed
    return E.daymatched_controls(sub, pl, K=K, seed=seed, mask=None, no_overlap=no_overlap, carry=("side", "g", "mae", "mfe", "risk", "sess"))


def _ctl_tr(c: dict):
    t = E.TR()
    t.n, t.label, t.range = int(len(c["date"])), "control", (None, None)
    for a in ("date", "te", "tx", "side", "g", "mae", "mfe", "risk", "sess"):
        setattr(t, a, np.asarray(c[a]))
    return t


def lift_vs_control(trades, control_trades, firm, rules: dict | None = None, model: str | None = None, *, micros: int | None = None,
                    sess="all", news: str = "all", mode: str = "daymatched", K: int = 10, seed: int | None = None, kind: str = "eval",
                    policy=500, start="fresh", boots: int = 2000, calendar=None, allow_holdout: bool = False,
                    off_calendar: str = "raise", label: str | None = None, **spec_over) -> dict:
    """Lift of ONE config (one trade source, not a member list) over its controls at IDENTICAL micros + rules (R:
    portfolio.control_lift / holdout_score.score_funded).

    mode='daymatched' (C1): control_trades = the random-entry pool (one source or a list, pooled); K seeded day-matched draws.
    mode='direct' (C2 or any ready-made null): control_trades = a LIST of sources, each a complete control ledger.
    kind='eval': per breach model lift = P5(real) - mean_k P5(control k), CI = block bootstrap of the paired per-start difference;
                 also the k = 1..5 pass lifts and the bust difference. kind='funded' (firm = funded variant, `policy`, `start`):
                 lift_e40 = E$40(real) - mean_k E$40(control k) (+ P(payout <= 20 / 40 d) of the controls), per funded model.
    seed default: R's (crc32 of '<label>|<sess>'), so equal labels reproduce R's draws; `label` = the config's name (an
    in-memory list is labelled 'inline': name it, or every list of a session shares one seed). A control ledger without a
    trade on the calendar counts as never passing (eval; 'ctrl_empty' reports how many). C1 quality: 'fallback_share' (control
    trades taken from the same session on a NEARBY date because the pool had too few that day) and 'short' (unfilled) are
    returned; a draw with short > 0 has fewer trades than the config. -> {..., 'lift', 'lift_gt0'}."""
    if kind not in ("eval", "funded"):
        raise ValueError("kind must be 'eval' or 'funded'")
    if _is_members(trades):
        raise ValueError("lift_vs_control scores ONE config (a trade source); for a portfolio score each member's lift")
    tr = load_trades(trades, allow_holdout, calendar=calendar)
    _, cal = _prep(tr, sess, None, news, calendar, allow_holdout, off_calendar)      # the config's calendar (run span, union policy)
    if mode == "daymatched":
        seed = default_seed(label or getattr(tr, "label", "inline"), sess, kind) if seed is None else seed
        m = _mask(tr, sess, news)
        sub = SimpleNamespace(date=tr.date[m], sess=tr.sess[m], n=int(m.sum()))
        cs = E.daymatched_controls(sub, _pool_tr(control_trades, allow_holdout), K=K, seed=seed, mask=None,
                                   carry=("side", "g", "mae", "mfe", "risk", "sess"))
        ctl = [(_ctl_tr(c), "all", "all") for c in cs]
        info = {"mode": mode, "K": len(cs), "seed": int(seed), "fallback_share": float(np.mean([c["fb_share"] for c in cs])) if cs else 0.0,
                "short": int(sum(c["short"] for c in cs)), "ctrl_trades": [int(c["n"]) for c in cs]}
    elif mode == "direct":
        if _is_rows(control_trades) or not isinstance(control_trades, (list, tuple)) or not control_trades:
            raise ValueError("mode='direct' needs a non-empty LIST of control ledgers (each a trade source)")
        ctl = [(load_trades(s, allow_holdout, calendar=calendar), sess, news) for s in control_trades]
        info = {"mode": mode, "K": len(ctl), "ctrl_trades": [int(_mask(t, s, n).sum()) for t, s, n in ctl]}
    else:
        raise ValueError("mode must be 'daymatched' or 'direct'")
    kw = dict(calendar=cal, allow_holdout=allow_holdout, off_calendar=off_calendar)
    if kind == "eval":
        fm = _firm(firm)
        model = model or fm.prim
        real = score_eval(tr, firm, rules, model, micros=micros, sess=sess, news=news, boots=0, arrays=True, **kw)
        cps = [score_eval(t, firm, rules, model, micros=micros, sess=s, news=n, boots=0, arrays=True, **kw) for t, s, n in ctl]
        if "arrays" not in real:
            return {**info, "kind": kind, "firm": firm, "skipped": "the config has no trades on the calendar"}
        if any(c["window"] != real["window"] for c in cps):
            raise ValueError("a control ledger covers a different span than the config (bundle run ranges differ)")
        n_st = len(real["arrays"][MODELS[0]][0])
        never = {b: (np.zeros(n_st, np.int8), np.full(n_st, H_EVAL, np.int16)) for b in MODELS}      # no trades: never passes, never busts
        info["ctrl_empty"] = int(sum("arrays" not in c for c in cps))
        cps = [c if "arrays" in c else {"arrays": never} for c in cps]
        out = {**info, "kind": kind, "firm": firm, "model": model, "primary": fm.prim, "models": {}}
        for b in MODELS:
            ro, rd = real["arrays"][b]
            c = np.mean(np.stack([x["arrays"][b][0] == 1 for x in cps]), 0)
            diff = (ro == 1).astype(float) - c
            ci = E.block_ci([diff], boots=boots)[0] if boots else [None, None]
            cp5 = [float((x["arrays"][b][0] == 1).mean()) for x in cps]
            o = {"real_p5": float((ro == 1).mean()), "ctrl_p5": float(c.mean()), "ctrl_p5_sd": float(np.std(cp5)), "lift": float(diff.mean()), "ci": ci,
                 "ctrl_p5_each": cp5, "real_bust5": float((ro == 2).mean()),
                 "ctrl_bust5": float(np.mean([(x["arrays"][b][0] == 2).mean() for x in cps]))}
            for k in range(1, H_EVAL + 1):
                o[f"lift_p{k}"] = float(((ro == 1) & (rd <= k)).mean() - np.mean([((x["arrays"][b][0] == 1) & (x["arrays"][b][1] <= k)).mean() for x in cps]))
            out["models"][b] = o
        out.update(out["models"][model])
        out["lift_gt0"] = bool(out["lift"] > 0)
        return out
    S = funded_spec(firm, **spec_over)
    model = model or S.primary
    fkw = dict(micros=micros, rules=rules, boots=0, start=start, **kw)
    real = score_funded(tr, S, policy, sess=sess, news=news, **fkw)
    cps = [score_funded(t, S, policy, sess=s, news=n, **fkw) for t, s, n in ctl]
    if "models" not in real or any("models" not in c for c in cps):
        return {**info, "kind": kind, "variant": S.name, "skipped": real.get("skipped") or "control window too short"}
    if any(c["window"] != real["window"] for c in cps):
        raise ValueError("a control ledger covers a different span than the config (bundle run ranges differ)")
    out = {**info, "kind": kind, "variant": S.name, "model": model, "primary": S.primary, "policy": policy, "start": start, "models": {}}
    for b in real["models"]:
        ce = np.array([[c["models"][b]["e_net_40"], c["models"][b]["p_pay_40"], c["models"][b]["p_pay_20"], c["models"][b]["p_bust_pre_first"]] for c in cps])
        out["models"][b] = {"real_e40": real["models"][b]["e_net_40"], "ctrl_e40": float(ce[:, 0].mean()),
                            "ctrl_e40_sd": float(ce[:, 0].std(ddof=1)) if len(ce) > 1 else None, "ctrl_p40": float(ce[:, 1].mean()),
                            "ctrl_p20": float(ce[:, 2].mean()), "ctrl_bust_pre": float(ce[:, 3].mean()),
                            "lift_e40": float(real["models"][b]["e_net_40"] - ce[:, 0].mean()), "ctrl_e40_each": ce[:, 0].tolist()}
    out.update(out["models"][model])
    out["lift"] = out["lift_e40"]
    out["lift_gt0"] = bool(out["lift"] > 0)
    return out


# ------------------------------------------------------------------ offline walk-forward (R: wf_offline.task + agg_task)

def walk_forward(configs, firm: str, *, sess="all", control_pool=None, kc: int = 5, models=None, grid: dict | None = None,
                 label: str = "l2", names: list | None = None, allow_holdout: bool = False, off_calendar: str = "raise") -> dict:
    """R's offline quarterly walk-forward of the (config, rules) search for ONE family grid, unchanged (wf_offline.windows /
    reduce_cfg / pick_across / agg_task run on this module's search arrays).

    configs: the family grid = a list of trade sources (the tuned cells of one family x tf; one source = a one-config grid).
    Test quarters 2022Q3..2024Q4; each quarter SELECTS the (config, rules cell) with the best stable rolling-start P5 on the
    trailing 12 months (attempts END before the quarter) and TESTS on the attempts starting in it; stitched -> OOS P5 + CI.
    control_pool (C1): random-entry pool; rep k = every config replaced by its k-th day-matched control (seed
    crc32('<name>|<sess>'), as R; pass `names` for in-memory lists, else they are 'cfg0', 'cfg1', ...), the SAME selection
    procedure re-run -> OOS control P5, OOS lift, paired block CI.
    models: default ('eod', primary). -> {'task': R's raw record (reps, per-quarter picks), 'rows': agg rows, one per model
    (is_p5, oos_p5, oos_ci, drop, ctrl_oos_p5, oos_lift, lift_ci, survive, survive_strict, per-year OOS P5 ...)}.
    Importing R's wf_offline registers lucidpro* in evalcore.FIRMS (R's own side effect)."""
    import wf_offline as WF
    fm = _firm(firm)
    mods = tuple(models or dict.fromkeys(("eod", fm.prim)))
    srcs = list(configs) if (isinstance(configs, (list, tuple)) and not _is_rows(configs)) else [configs]
    trs = [load_trades(c, allow_holdout) for c in srcs]
    names = list(names) if names else [lb if lb != "inline" else f"cfg{i}" for i, lb in enumerate(getattr(t, "label", "inline") for t in trs)]
    g = {a: list((grid or {}).get(a, EVAL_GRIDS[firm][a])) for a in AX}
    kw = dict(grid=g, boots=0, keep_arrays=True, allow_holdout=allow_holdout, off_calendar=off_calendar)
    ledgers = [[(t, sess)] for t in trs]                              # per config: rep 0 = the real ledger, 1..kc = controls
    if control_pool is not None and kc:
        pool = _pool_tr(control_pool, allow_holdout)
        for t, nm, lst in zip(trs, names, ledgers):
            m = _mask(t, sess, "all")
            sub = SimpleNamespace(date=t.date[m], sess=t.sess[m], n=int(m.sum()))
            cs = E.daymatched_controls(sub, pool, K=kc, seed=zlib.crc32(f"{nm}|{sess_name(sess)}".encode()), mask=None,
                                       carry=("side", "g", "mae", "mfe", "risk", "sess"))
            lst += [(_ctl_tr(c), "all") for c in cs]
    reps_n = 1 + (kc if control_pool is not None else 0)
    out, W = None, None
    for rep in range(reps_n):
        per_cfg, walks = [], 0
        for lst in ledgers:
            t, ss = lst[rep]
            r = search_rules(t, firm, sess=ss, **kw)
            if out is None:
                W, tests, oos = WF.windows(r["cal"])
                out = {"grid": label, "sess": sess_name(sess), "firm": firm, "members": names,
                       "D": int(len(r["cal"])), "n_starts": int(len(r["cal"]) - H_EVAL + 1), "models": list(mods),
                       "test_dates": [[int(r["cal"][i]) for i in tt] for tt in tests], "reps": []}
            elif len(r["cal"]) != out["D"]:
                raise ValueError("the configs of a family grid must share one calendar (bundle run ranges differ)")
            shape = tuple(r["shape"])
            per_cfg.append(WF.reduce_cfg(r["PS"][[MODELS.index(m) for m in mods]], r["nr"], shape, W, tests, oos, mods))
            walks += r["walks"]
        sel = WF.pick_across(per_cfg, mods)
        sel["rep"], sel["walks"] = rep, walks
        for mod in mods:
            for x in [sel[mod]["full"]] + sel[mod]["q"]:
                x["rules"] = [g[ax][i] for ax, i in zip(AX, np.unravel_index(x["cell"], shape))]
        out["reps"].append(sel)
    return {"task": out, "rows": WF.agg_task(out)}


# ------------------------------------------------------------------ R bundle export / approved baseline

BASELINE = {      # R's approved picks (R/desk_review.md, R/out/holdout_manifest.json), in-sample tester bundles
    "flex_eval": dict(kind="eval", firm="lucid", key="hm2-straddle-tf30#10", src="20260930-001526-draft_pp_straddle-67c2#10", sess="nyam",
                      micros=40, rules={"day_lock": 750, "day_take": 1500, "day_stop": 0, "max_day_tr": 0, "target_take": 1}),
    # Pro noDLL eval = straddle-tf30#10 nyam (L/SPEC.md "Build findings that OVERRIDE": R's manifest / desk review single; #9 ties).
    "pro_nodll_eval": dict(kind="eval", firm="lucidpro_nodll", key="hm2-straddle-tf30#10", src="20260930-001526-draft_pp_straddle-67c2#10",
                           sess="nyam", micros=40, rules={"day_lock": 1000, "day_take": 0, "day_stop": 0, "max_day_tr": 0, "target_take": 1}),
    "flex_funded": dict(kind="funded", firm="flex", key="hm2-straddle-tf30#32", src="20260930-001526-draft_pp_straddle-67c2#32", sess="pm",
                        micros=40, rules={"day_take": 600, "day_lock": 300, "day_stop": 0, "max_day_tr": 0}, policy=1500),
    "pro_nodll_funded": dict(kind="funded", firm="pro_nodll", key="hm-orb-tf5#10", src="20260929-231930-draft_pp_orb-5276#10", sess="mid",
                             micros=40, rules={"day_take": 1000, "day_lock": 300, "day_stop": 0, "max_day_tr": 0}, policy=1000),
    "pro_dll_funded": dict(kind="funded", firm="pro_dll", key="fp-donchian-tf15#10", src="20260930-111627-draft_pp_donchian-cd3c#10", sess="pm",
                           micros=30, rules={"day_take": 0, "day_lock": 600, "day_stop": 0, "max_day_tr": 0}, policy=1500),
    "apex_pa_funded": dict(kind="funded", firm="apex", key="fp-donchian-tf15#1", src="20260930-111627-draft_pp_donchian-cd3c#1", sess="nyam",
                           micros=30, rules={"day_take": 1000, "day_lock": 1000, "day_stop": 0, "max_day_tr": 0}, policy=1000),
}


BASELINE_ALT = {  # NOT the bar: straddle-tf30#9 nyam, the config the SPEC text named before the override (ties #10 in-sample, P5 .7065)
    "pro_nodll_eval_s9": dict(kind="eval", firm="lucidpro_nodll", key="hm2-straddle-tf30#9", src="20260930-001526-draft_pp_straddle-67c2#9",
                              sess="nyam", micros=40, rules={"day_lock": 1000, "day_take": 0, "day_stop": 0, "max_day_tr": 1, "target_take": 1}),
}
BASELINE_META = {  # tester family + inputs of the approved sources (R manifest) -> the Apex compliance flags
    "hm2-straddle-tf30#10": dict(strategy="straddle", inputs={"tf": "30", "stop_val": 3.0, "tgt_r": 2.0, "off_atr": 0.25}, both_sides=True),
    "hm2-straddle-tf30#9": dict(strategy="straddle", inputs={"tf": "30", "stop_val": 3.0, "tgt_r": 1.0, "off_atr": 0.25}, both_sides=True),
    "hm2-straddle-tf30#32": dict(strategy="straddle", inputs={"tf": "30", "stop_val": 3.0, "tgt_r": 0.5, "off_atr": 1.0}, both_sides=True),
    "hm-orb-tf5#10": dict(strategy="orb", inputs={"tf": "5", "or_min": "5", "stop_val": 3.0, "tgt_r": 2.0}, both_sides=True),
    "fp-donchian-tf15#10": dict(strategy="donchian", inputs={"tf": "15", "stop_mode": "pts", "stop_val": 30.0, "tgt_r": 0.6}, both_sides=False),
    "fp-donchian-tf15#1": dict(strategy="donchian", inputs={"tf": "15", "stop_mode": "pts", "stop_val": 10.0, "tgt_r": 0.4}, both_sides=False),
}


def export_name(key: str) -> str:
    """'hm2-straddle-tf30#10' -> 'R__hm2-straddle-tf30_c10' (file name of an exported R bundle in L/trades)."""
    return "R__" + key.replace("#", "_c")


def export_bundle(src, name: str, overwrite: bool = True, out_dir=None) -> Path:
    """Copy an IN-SAMPLE R tester bundle's trades (rows verbatim) to L/trades/<name>.json (or <out_dir>/<name>.json: tests).
    Refuses bundles reaching the holdout. Atomic, with a temp name of its own per process (concurrent exports never share one)."""
    _native_guard(src, False)
    d = _R_SRC_DIR(src)
    rows = _read_rows(d if d.is_file() else d / "trades.json")
    _guard_rows(rows, str(src), False)
    p = trade_file(name) if out_dir is None else Path(out_dir) / trade_file(name).name
    if R in p.resolve().parents:
        raise ValueError("refusing to write into R")
    if p.exists() and not overwrite:
        return p
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f"{p.name}.{os.getpid()}.{time.monotonic_ns()}.tmp")
    tmp.write_text(json.dumps(rows))
    tmp.replace(p)
    return p


def export_baseline(overwrite: bool = True) -> dict:
    """Export every approved pick's in-sample bundle (+ the BASELINE_ALT sources) -> {key: path}."""
    return {b["key"]: export_bundle(b["src"], export_name(b["key"]), overwrite) for b in {**BASELINE, **BASELINE_ALT}.values()}


def _baseline_src(b: dict, source: str):
    if source == "native":
        return b["src"]
    if not trade_file(export_name(b["key"])).exists():
        export_bundle(b["src"], export_name(b["key"]))
    return "file:" + export_name(b["key"])


def score_baseline(name: str, source: str = "file", **kw) -> dict:
    """Score one approved pick (BASELINE / BASELINE_ALT) under ITS OWN firm, approved micros + rules, in-sample, from its
    exported file (source='file') or R's native bundle ('native')."""
    b = {**BASELINE, **BASELINE_ALT}[name]
    src = _baseline_src(b, source)
    if b["kind"] == "eval":
        return score_eval(src, b["firm"], b["rules"], micros=b["micros"], sess=b["sess"], **kw)
    gate = {**BASELINE_META.get(b["key"], {}), **kw}        # strategy / inputs / both_sides of the approved source -> the Apex gate
    return score_funded(src, b["firm"], b["policy"], micros=b["micros"], rules=b["rules"], sess=b["sess"], **gate)


# ---- the approved picks on the Apex Legacy 300K PA (the user's five accounts): the in-sample bar for 'apex300_pa'

APEX300_BASE_CELLS = {      # fixed, pre-declared cells (no search): the 50K Apex PA pick's cell as approved ('x1') and scaled x3 ('x3':
    "x1": dict(micros=30, rules={"day_take": 1000, "day_lock": 1000, "day_stop": 0, "max_day_tr": 0}, policy=500),    # the 300K's threshold,
    "x3": dict(micros=90, rules={"day_take": 3000, "day_lock": 3000, "day_stop": 0, "max_day_tr": 0}, policy=2500),   # MAE floor and caps are 3x)
}


def baseline_sources() -> dict:
    """The distinct (source, session) pairs of the approved picks -> {'<key>|<sess>': {key, sess, src, picks: [BASELINE names],
    strategy, inputs, both_sides}}."""
    out: dict = {}
    for name, b in BASELINE.items():
        e = out.setdefault(f"{b['key']}|{b['sess']}", {"key": b["key"], "sess": b["sess"], "src": b["src"], "picks": [],
                                                      **BASELINE_META.get(b["key"], {})})
        e["picks"].append(name)
    return out


def _apex300_row(r: dict, alt: str) -> dict:
    """Compact record of a score_funded result or a search row (headline = the spec's consistency reading; alt = the other)."""
    keep = ("e_net_40", "e_net_60", "p_pay_20", "p_pay_40", "p_pay_60", "med_days_first", "p_bust_pre_first", "p_bust_any", "cut_share")
    if "models" in r:                                            # score_funded
        a = r["cons_alt"][r["model"]]
        return {**{k: r.get(k) for k in keep}, "micros": r["micros"], "policy": r["policy"], "rules": r["rules"],
                "models_e40": {m: v["e_net_40"] for m, v in r["models"].items()}, f"e_net_40_cons_{alt}": a["e_net_40"],
                f"p_bust_pre_first_cons_{alt}": a["p_bust_pre_first"], "compliant": r["compliant"], "compliance": r["compliance"],
                "apex_flags": r["apex_flags"]}
    return {**{k: r.get(k) for k in keep}, "micros": r["micros"], "policy": r["policy"],
            "rules": {k: r[k] for k in ("day_take", "day_lock", "day_stop", "max_day_tr")}, "stab_e_net_40": r.get("stab_e_net_40"),
            f"e_net_40_cons_{alt}": r.get(f"e_net_40_cons_{alt}"), f"p_bust_pre_first_cons_{alt}": r.get(f"p_bust_pre_first_cons_{alt}"),
            "compliant": r.get("apex_noncompliant") is False,
            "compliance": {k: r.get("apex_" + k) for k in ("one_direction", "stop_5x_target", "mae_rule")}, "apex_flags": r.get("apex_flags")}


def score_baseline_apex300(starts=None, search: bool = False, workers: int = 1, grid: dict | None = None, firm: str = "apex300_pa",
                           source: str = "file", boots: int = 0, search_starts=("fresh",), **spec_over) -> dict:
    """In-sample scoring of the approved picks' strategies on the Apex Legacy 300K PA from every start state, under the
    module's default (conservative) rule readings; every record also carries E$40 / bust under the OTHER consistency reading.

    Per (source|session, start): `cells` = the fixed APEX300_BASE_CELLS ('x1', 'x3'); with search=True also, for the sources
    that can be compliant and the starts in `search_starts` (default 'fresh' = the user's five accounts as the desk shows them;
    None = every start), `search` = the e40_stable / e40_raw picks of search_funded over apex300.GRID among the cells that
    PASS the compliance gate (None when no cell passes) and `best_ignoring_compliance` (reference only).
    Straddle / ORB sources work orders on both sides (OCO): NON-COMPLIANT at Apex whatever the cell, scored for reference only.
    -> {'rows': {'<key>|<sess>': {picks, strategy, both_sides, starts: {start: {cells, search}}}},
        'bar': {start: the best COMPLIANT E$40 (model pess, conservative readings) and where it came from, or None}}."""
    starts = tuple(starts or start_states(firm))
    S = funded_spec(firm, **spec_over)
    alt = _ext().other_cons(S).cons_base
    out = {"firm": S.name, "cons_base": S.cons_base, "cons_alt": alt, "commission": S.commission, "starts": [], "search": bool(search),
           "cells": APEX300_BASE_CELLS, "rows": {}, "bar": {}}
    for sid, b in baseline_sources().items():
        src = _baseline_src(b, source)
        ckw = dict(strategy=b.get("strategy"), inputs=b.get("inputs"), both_sides=b.get("both_sides"))
        row = out["rows"][sid] = {"picks": b["picks"], "strategy": b.get("strategy"), "both_sides": b.get("both_sides"), "starts": {}}
        for st in starts:
            e = {"cells": {}}
            for cn, c in APEX300_BASE_CELLS.items():
                r = score_funded(src, firm, c["policy"], micros=c["micros"], rules=c["rules"], sess=b["sess"], start=st, boots=boots,
                                 **ckw, **spec_over)
                e["cells"][cn] = _apex300_row(r, alt)
            if search and not b.get("both_sides") and (search_starts is None or r["start"] in search_starts):      # an OCO source fails the gate in every cell
                sr = search_funded(src, firm, sess=b["sess"], grid=grid, workers=workers, start=st, **ckw, **spec_over)
                e["search"] = {"eligible": sr["eligible"], "cells": len(sr["rows"]), "gate": sr["gate"],
                               **{k: (_apex300_row(sr["picks"][k], alt) if sr["picks"].get(k) else None) for k in ("e40_stable", "e40_raw")},
                               "best_ignoring_compliance": _apex300_row(max(sr["rows"], key=lambda x: x["e_net_40"]), alt)}
            row["starts"][r["start"]] = e
            if r["start"] not in out["starts"]:
                out["starts"].append(r["start"])
    for st in out["starts"]:
        best = None
        for sid, row in out["rows"].items():
            e = row["starts"][st]
            cands = [(f"{sid} cell {cn}", c) for cn, c in e["cells"].items() if c["compliant"]]
            if e.get("search") and e["search"].get("e40_stable"):
                cands.append((f"{sid} search e40_stable", e["search"]["e40_stable"]))
            for where, c in cands:
                if best is None or c["e_net_40"] > best[1]["e_net_40"]:
                    best = (where, c)
        out["bar"][st] = None if best is None else {"from": best[0], **best[1]}
    return out


# ------------------------------------------------------------------ C2: feature-shuffle null
#
# WHAT IT TESTS. A family is a function  f(features) -> signals  evaluated at minute boundaries on a per-minute feature table
# (book / flow features of the last COMPLETED minute + whatever price / time inputs the family also reads). The C2 null keeps
# everything about the family except the information content of its L2 features: for every session s the L2 FEATURE COLUMNS
# are replaced by the values the same columns had AT THE SAME TIME OF DAY in another in-sample session donor(s). Price, time,
# ATR, session structure, exits, max entries per session and the feature's own time-of-day profile + intraday dynamics (the
# donor's series is transplanted whole, so its autocorrelation, z-scores and spikes stay intact) are preserved; only the link
# between THIS session's book / flow and THIS session's price path is cut. If the real family does not beat this null, its
# P&L comes from timing / structure / exit geometry, not from order-book information (SPEC: promotion needs lift > 0 vs C1
# AND C2).
#
# HOW. donor() is a seeded, deterministic BIJECTION of the sessions with no fixed point (every session receives one donor and
# donates once, so the pooled feature distribution is EXACTLY the real one), with |index(s) - index(donor(s))| >= min_gap
# sessions (default 5 = a trading week: book regimes persist over adjacent days, a neighbour donor would leak the regime).
# Optional `strata` (e.g. the year) permutes inside groups, for features with a secular level drift used against absolute
# thresholds. Sessions in which NO shuffled feature has a valid row are 'dead': the real family cannot use them either, they
# keep their own (empty) features and take no part in the permutation. Sessions in which SOME shuffled features are dead all
# session (roll block: book columns masked by the data layer while the flow columns are live; the first sessions of a 20-day
# normalisation) are permuted among sessions with the SAME dead pattern: they never keep a real feature (a null that kept the
# real flow on ~5% of the sessions would dilute every lift) and a live session never receives a dead donor. With `sessions=`
# only the listed sessions are permuted (C2Features: the simulator's 825-session calendar, so holiday stubs of the Globex grid
# are neither donors nor receivers). Same (seed, session list, min_gap, strata, dead patterns) -> same map on any machine (numpy default_rng([C2_SEED, seed])).
# Rows are matched on the time-of-day key (same stamp convention as the data layer: a row stays at its own `usable_at`, so the
# timestamp law is untouched). Where the donor has no row at that minute (half days, gaps) the feature is NaN, and with
# keep_nan (default) a row whose real feature is NaN stays NaN (the null never trades where the real family cannot): the
# family must treat NaN as "no signal". .attrs reports c2_coverage (rows that found a donor row), c2_valid_real / c2_valid_null
# (share of rows with a non-NaN first feature) so an opportunity-set mismatch is visible.
#
# SESSION KEY for the data layer (l2data.load_features): session_col='globex_date', tod_col='et_min'. The Globex session
# (18:00 ET the evening before -> 17:00) is the unit, so the sim's lookback into the previous evening and the day itself come
# from ONE donor (shuffling by ET calendar date would stitch two donors together at midnight). `C2Features` is that loader
# for l2sim.run(features=...): the null of l2sim.L2Features, picklable, same slicing.
#
# RULES OF USE. (1) Shuffle only features that are relative / level-free (imbalance, depth ratios, tick distances from the
# best price, deltas): never absolute prices (a transplanted wall is "x ticks from the best bid", re-anchored on the receiving
# session's price by the family). Flow columns that carry price (f_o / f_h / f_l / f_c), the price anchors (bid_px / ask_px),
# tags and flags are NOT L2 features: c2_shuffle REFUSES them (c2_fixed_columns; + a level check that catches an unlisted
# absolute-price column), and C2Features shuffles every OTHER column it loads, so a family cannot keep one real feature by
# accident (allow_partial=True is the explicit diagnostic exception). (2) Shuffle the FINISHED feature columns the family consumes (after cross-day normalisations
# such as depth10_rel20d), so real and null use the same feature marginals; trailing intraday windows computed inside the
# family then run on the donor's series. (3) Roll-day exclusions and every non-feature filter stay keyed on the RECEIVING
# session. (4) Run the null through the SAME simulator, sessions, params and exits, K >= 5 seeds, then
# `lift_vs_control(real, [null_1..null_K], firm, rules, mode='direct')`. (5) Donors are in-sample sessions only (rows dated
# >= 2025-01-01 raise); for the one-off holdout run the map is built over the holdout sessions (allow_holdout=True).

C2_SEED = 20261001
C2_NEVER = frozenset({                     # price-carrying columns, tags and flags: the RECEIVING session's own, never shuffled
    "f_o", "f_h", "f_l", "f_c", "bid_px", "ask_px", "mid", "mid_px",                              # tape OHLC of the minute, price anchors
    "t_utc", "date", "globex_date", "et_min", "session", "contract",                              # tags
    "book_valid", "in_tape", "roll_block", "ofb_mismatch", "book_ok", "c2_donor"})                # flags
_C2_PRICE_NAME = re.compile(r"(^|_)(px|price|prices|open|high|low|close|ohlc|vwap|mid)($|_)")


def _c2_never() -> frozenset:
    """C2_NEVER + whatever the data layer itself declares as price anchors / tags / flags (l2data.PX_COLS, TAG_COLS, FLAG_COLS)."""
    out = set(C2_NEVER)
    m = sys.modules.get("l2data")
    if m is None and (L / "l2data.py").exists():
        try:
            if str(L) not in sys.path:
                sys.path.insert(0, str(L))
            import l2data as m
        except Exception:                  # the data layer is optional here (synthetic tables); the static list still applies
            m = None
    for nm in ("PX_COLS", "TAG_COLS", "FLAG_COLS"):
        out |= set(getattr(m, nm, ()) or ())
    return frozenset(out)


def c2_is_fixed(col: str) -> bool:
    """True for a column the C2 null must NOT shuffle: prices (tape OHLC f_o/f_h/f_l/f_c, bid_px/ask_px, anything named like a
    price), tags (date / time keys, contract) and flags (book_ok ...)."""
    return col in _c2_never() or bool(_C2_PRICE_NAME.search(col))


def c2_fixed_columns(columns) -> list:
    return [c for c in columns if c2_is_fixed(c)]


def _looks_like_price(v) -> bool:
    """Level check for an unlisted absolute-price column: every finite value above 1,000 and within a factor 4 (an index-future
    price level; sizes, volumes, imbalances, deltas, tick distances all reach small values)."""
    v = np.asarray(v)
    if v.dtype.kind not in "fiu":
        return False
    v = v[np.isfinite(v.astype(float))]
    return len(v) >= 50 and float(v.min()) > 1000.0 and float(v.max()) < 4.0 * float(v.min())


def _iso(x) -> str:
    return x.isoformat()[:10] if hasattr(x, "isoformat") else str(x)[:10]


def c2_donor_map(sessions, seed: int, *, min_gap: int = 5, strata=None, fixed=(), allow_holdout: bool = False, soft=None) -> dict:
    """Seeded donor session for every session: a derangement (bijection, no session keeps its own features) with at least
    `min_gap` sessions between a session and its donor (index distance in the sorted session list; 1 = any other session).
    strata: None | dict {session: label} | callable(session iso) -> label; donors come from the same stratum.
    fixed: sessions that keep their own features (dead sessions; they are not donors either).
    soft: None | callable(label) -> bool: a stratum for which it is True and that cannot be deranged at min_gap is deranged
    at the widest smaller gap that works (down to 1 = any other session of the stratum); a one-session stratum keeps its own
    features. Strata that are not soft raise.
    -> {iso date: donor iso date}. Raises HoldoutError on 2025+ sessions unless allow_holdout."""
    ss = sorted({_iso(s) for s in sessions})
    if ss and ss[-1] >= HOLDOUT and not allow_holdout:
        raise HoldoutError(f"C2 donor map: sessions reach {ss[-1]} (holdout); pass allow_holdout=True explicitly")
    min_gap = max(1, int(min_gap))
    fx = {_iso(s) for s in fixed}
    lab = (lambda s: 0) if strata is None else ((lambda s: strata[s]) if isinstance(strata, dict) else strata)
    groups: dict = {}
    for i, s in enumerate(ss):
        if s not in fx:
            groups.setdefault(lab(s), []).append(i)
    rng = np.random.default_rng([C2_SEED, int(seed)])
    donor = np.arange(len(ss), dtype=np.int64)

    def derange(idx, gap):
        n = len(idx)
        if n < 2 or int(idx[-1] - idx[0]) < gap:
            return None
        perm = rng.permutation(n)
        for _ in range(200):
            bad = np.flatnonzero(np.abs(idx[perm] - idx) < gap)
            if not len(bad):
                return perm
            for i in bad:
                j = int(rng.integers(n))
                if abs(int(idx[perm[j]] - idx[i])) >= gap and abs(int(idx[perm[i]] - idx[j])) >= gap:
                    perm[i], perm[j] = perm[j], perm[i]
        return perm if not len(np.flatnonzero(np.abs(idx[perm] - idx) < gap)) else None

    for key in sorted(groups, key=str):
        idx = np.array(groups[key], np.int64)
        n = len(idx)
        perm = derange(idx, min_gap)
        if perm is None and soft and soft(key):               # a small special group: the widest gap that works, down to "any
            for gap in range(min_gap - 1, 0, -1):             # other session of the group"; a single session keeps its own
                perm = derange(idx, gap)
                if perm is not None:
                    break
            if perm is None:
                continue
        if perm is None:
            if n < 2 or int(idx[-1] - idx[0]) < min_gap:
                raise ValueError(f"C2 donor map: stratum {key!r} has {n} sessions, too few for min_gap={min_gap}")
            raise RuntimeError(f"C2 donor map: no derangement with min_gap={min_gap} found for stratum {key!r} ({n} sessions)")
        donor[idx] = idx[perm]
    return {ss[i]: ss[int(donor[i])] for i in range(len(ss))}


def c2_shuffle(features, feature_cols, seed: int, *, session_col: str = "globex_date", tod_col: str = "et_min", min_gap: int = 5,
               strata=None, sessions=None, donor_map: dict | None = None, keep_nan: bool = True, guard_col: str = "date",
               allow_holdout: bool = False, level_check: bool = True):
    """The C2 null feature table: same rows, same index, same order, same non-feature columns; `feature_cols` at (session s,
    time-of-day m) replaced by the original values at (donor(s), m); NaN where the donor has no such minute and (keep_nan)
    where the real row is NaN. Adds column 'c2_donor'.

    features: pandas DataFrame, one row per (session, time-of-day key). Defaults fit l2data.load_features: session_col
    'globex_date', tod_col 'et_min'. Any pair of columns works (session: ISO str / date / Timestamp; tod: any hashable equal
    across sessions); if either is missing and the index is a tz-aware DatetimeIndex both are derived from it in ET (calendar
    date, minute of day). sessions: the sessions that take part in the permutation (e.g. the simulator's session calendar);
    every other session, every DEAD session (no shuffled feature has a valid row) and, in-sample, any session label
    >= 2025-01-01 keeps its own features. A PARTLY dead session (some shuffled features have no valid row all session: the
    roll block for book columns, the first sessions of a 20-day normalisation) is permuted with sessions of the SAME dead
    pattern, so it never keeps a real feature and never hands a hole to a live session (a pattern group too small for min_gap
    uses the widest gap that works; a group of one keeps its own features, reported in c2_fixed). The holdout guard looks at `guard_col` (the row's ET date) when present, else at the session key.
    PRICE-CARRYING columns, tags and flags (c2_is_fixed: f_o / f_h / f_l / f_c, bid_px / ask_px, *_px / *_price ..., date keys,
    book_ok ...) can NOT be shuffled: ValueError. A column whose values look like an absolute price level is refused too
    (level_check=False only for a non-price column that trips that check).
    .attrs: c2_seed, c2_min_gap, c2_coverage, c2_valid_real, c2_valid_null (first column), c2_valid (per column: [real, null]),
    c2_dead, c2_partial ({dead columns: n sessions}) + c2_partial_sessions, c2_fixed (every session that kept its own
    features), c2_map."""
    import pandas as pd
    df = features
    cols = [feature_cols] if isinstance(feature_cols, str) else list(feature_cols)
    miss = [c for c in cols if c not in df.columns]
    if miss or not cols:
        raise ValueError(f"feature columns missing / empty: {miss}")
    bad = c2_fixed_columns(cols)
    if bad:
        raise ValueError(f"C2 shuffle refused: {bad} carry price / are tags or flags, not L2 features (they stay the receiving "
                         f"session's own; a transplanted price would leak another day's level into the null)")
    if level_check:
        lv = [c for c in cols if _looks_like_price(df[c].to_numpy())]
        if lv:
            raise ValueError(f"C2 shuffle refused: {lv} look like absolute price levels (all values > 1,000 within a factor 4); "
                             f"express the feature relative to the best price, or pass level_check=False if it is not a price")
    if session_col in df.columns and tod_col in df.columns:
        sess = df[session_col].map(_iso).to_numpy()
        tod = df[tod_col].to_numpy()
    elif isinstance(df.index, pd.DatetimeIndex) and df.index.tz is not None:
        ix = df.index.tz_convert("America/New_York")
        sess = np.array([d.isoformat() for d in ix.date])
        tod = np.asarray(ix.hour * 60 + ix.minute)
    else:
        raise ValueError(f"need columns {session_col!r} + {tod_col!r}, or a tz-aware DatetimeIndex")
    if set(cols) & {session_col, tod_col, guard_col}:
        raise ValueError("the session / time-of-day / date keys cannot be shuffled features")
    if not allow_holdout and len(df):
        latest = max(df[guard_col].map(_iso)) if guard_col in df.columns else max(sess)
        if latest >= HOLDOUT:
            raise HoldoutError(f"C2 shuffle: feature rows reach {latest} (holdout); pass allow_holdout=True explicitly")
    key = pd.DataFrame({"s": sess, "t": tod})
    if key.duplicated().any():
        raise ValueError("more than one row per (session, time of day): aggregate to the decision cadence first")
    vals = {c: df[c].to_numpy() for c in cols}
    isnan = {c: pd.isna(vals[c]) for c in cols}
    all_s = set(pd.unique(sess).tolist())
    live_c = {c: set(pd.unique(sess[~isnan[c]]).tolist()) for c in cols}
    pattern = {x: tuple(c for c in cols if x not in live_c[c]) for x in all_s}      # the shuffled features with no valid row all session
    dead = sorted(x for x in all_s if len(pattern[x]) == len(cols))
    fixed = set(dead)
    if sessions is not None:
        fixed |= all_s - {_iso(x) for x in sessions}
    if not allow_holdout:                                     # a Globex session label may fall after the last in-sample row date
        fixed |= {x for x in all_s if x >= HOLDOUT}
    partial: dict = {}
    for x in all_s - fixed:
        if pattern[x]:
            partial["+".join(pattern[x])] = partial.get("+".join(pattern[x]), 0) + 1
    if donor_map is None:                                     # rows are guarded above
        user = (lambda x: 0) if strata is None else ((lambda x: strata[x]) if isinstance(strata, dict) else strata)
        dm = c2_donor_map(all_s, seed, min_gap=min_gap, strata=lambda x: (user(x), pattern[x]), fixed=fixed, allow_holdout=True,
                          soft=lambda key: bool(key[1]))
    else:
        dm = {_iso(k): _iso(v) for k, v in donor_map.items()}
    left = pd.DataFrame({"s": pd.Series(sess).map(dm).to_numpy(), "t": tod})
    if left["s"].isna().any():
        raise ValueError("donor_map does not cover every session of the table")
    right = pd.DataFrame({"s": sess, "t": tod, "_have": True})
    for c in cols:
        right[c] = vals[c]
    mg = left.merge(right, how="left", on=["s", "t"], sort=False)
    out = df.copy()
    for c in cols:
        v = mg[c].to_numpy()
        if keep_nan:
            v = np.where(isnan[c], np.nan, v) if v.dtype.kind == "f" else pd.Series(v).where(~isnan[c]).to_numpy()
        out[c] = v
    out["c2_donor"] = left["s"].to_numpy()
    out.attrs.update(c2_seed=int(seed), c2_min_gap=int(min_gap), c2_coverage=float(mg["_have"].notna().mean()) if len(mg) else 0.0,
                     c2_valid_real=float((~isnan[cols[0]]).mean()) if len(df) else 0.0,
                     c2_valid_null=float(pd.notna(out[cols[0]]).mean()) if len(df) else 0.0, c2_dead=dead,
                     c2_partial=dict(sorted(partial.items())), c2_partial_sessions=sorted(x for x in all_s - fixed if pattern[x]),
                     c2_fixed=sorted(x for x in all_s if dm.get(x) == x), c2_map=dm,
                     c2_valid={c: [float((~isnan[c]).mean()), float(pd.notna(out[c]).mean())] for c in cols} if len(df) else {})
    return out


def c2_null(family_fn, features, feature_cols, seeds=(1, 2, 3, 4, 5), **kw) -> list:
    """Run the family on K feature-shuffled tables: -> [(seed, family_fn(c2_shuffle(features, feature_cols, seed, **kw)))].
    Feed each result to the SAME simulator as the real signals, then lift_vs_control(real, nulls, ..., mode='direct')."""
    return [(int(s), family_fn(c2_shuffle(features, feature_cols, int(s), **kw))) for s in seeds]


_C2_FRAMES: dict = {}                                  # per-process cache (one shuffled copy of the table per key)


class C2Features:
    """Picklable `features=` loader for l2sim.run(): the C2 null of l2sim.L2Features. Same table, same columns, same per-session
    slice (it IS L2Features' own slicing: only the table behind it is swapped), with the L2 feature columns replaced by the
    same-time-of-day values of a seeded random other Globex session (c2_shuffle on globex_date x et_min).

    shuffle_cols=None (default): EVERY loaded column that is an L2 feature is shuffled, i.e. all of `columns` except prices /
    anchors / tags / flags (c2_is_fixed: f_o f_h f_l f_c, bid_px ask_px, book_ok ...), which stay the receiving session's own.
    An explicit shuffle_cols must cover all of those too (a feature left real would leak this session's book into the null)
    unless allow_partial=True (diagnostic: which of two features carries the information). Price columns are refused.
    strata: None (SPEC: any other session >= min_gap away) | 'year' | 'half' (calendar half-year): donors from the same
    stratum, a stricter null that keeps the slow regime (thin 2022 books) and removes only the day-level information.

        cols = ["imb10", "depth10_rel20d", "f_delta", "f_c"]
        real = l2sim.run(Fam, params, features=l2sim.L2Features(cols))
        null = [l2sim.run(Fam, params, features=score.C2Features(cols, seed=k)) for k in range(1, 6)]
        score.lift_vs_control(real, null, firm, rules, mode="direct")"""

    STRATA = {None: None, "year": lambda s: s[:4], "half": lambda s: s[:4] + ("H1" if s[5:7] <= "06" else "H2")}

    def __init__(self, columns, shuffle_cols=None, seed: int = 1, lookback_min: int = 360, min_gap: int = 5, allow_holdout: bool = False,
                 mask_bad_book: bool = True, strata: str | None = None, allow_partial: bool = False):
        self.columns = tuple(columns)
        feats = tuple(c for c in self.columns if not c2_is_fixed(c))
        if shuffle_cols is None:
            self.shuffle_cols = feats
        else:
            self.shuffle_cols = tuple([shuffle_cols] if isinstance(shuffle_cols, str) else shuffle_cols)
        bad = [c for c in self.shuffle_cols if c not in self.columns]
        if bad or not self.shuffle_cols:
            raise ValueError(f"shuffle_cols must be a non-empty subset of columns: {bad} (columns holds no L2 feature?)")
        fixed = c2_fixed_columns(self.shuffle_cols)
        if fixed:
            raise ValueError(f"C2 null refused: {fixed} carry price / are tags or flags and cannot be shuffled")
        left = [c for c in feats if c not in self.shuffle_cols]
        if left and not allow_partial:
            raise ValueError(f"C2 null refused: feature columns {left} would stay REAL (the null would keep this session's own book / "
                             f"flow information); shuffle them too (shuffle_cols=None) or pass allow_partial=True for a diagnostic")
        if strata not in self.STRATA:
            raise ValueError(f"strata {strata!r} not in {list(self.STRATA)}")
        self.seed, self.lookback_min, self.min_gap = int(seed), int(lookback_min), int(min_gap)
        self.allow_holdout, self.mask, self.strata, self.partial = bool(allow_holdout), bool(mask_bad_book), strata, bool(left)

    def _mods(self):
        if str(L) not in sys.path:
            sys.path.insert(0, str(L))
        import l2data
        import l2sim
        return l2data, l2sim

    def real(self):
        """The real loader this is the null of (same columns / lookback / seal / mask)."""
        _, l2sim = self._mods()
        if not callable(getattr(l2sim.L2Features, "_frame", None)):
            raise RuntimeError("l2sim.L2Features no longer builds its table in _frame(): C2Features must be re-aligned with it")
        return l2sim.L2Features(self.columns, lookback_min=self.lookback_min, allow_holdout=self.allow_holdout, mask_bad_book=self.mask)

    def frame(self):
        """The shuffled table (pandas), for inspection: .attrs carries the donor map, coverage and per-column valid shares."""
        l2data, l2sim = self._mods()                             # same table (start, end, mask) as l2sim.L2Features._frame
        end = dt.date(2026, 12, 31) if self.allow_holdout else l2sim.IN_SAMPLE[1]
        cols = list(dict.fromkeys(list(self.columns) + ["globex_date", "et_min", "date"]))
        df = l2data.load_features(l2sim.TABLE_START, end, allow_holdout=self.allow_holdout, columns=cols, mask_bad_book=self.mask)
        st = self.STRATA[self.strata]
        if self.allow_holdout:               # holdout stage: in-sample and holdout sessions are permuted separately, all sessions
            sess, strata = None, (lambda x: (x >= HOLDOUT, st(x) if st else 0))
        else:                                # in-sample: permute the simulator's session calendar (R's 825 tape sessions)
            sess, strata = in_sample_sessions(), st
        return c2_shuffle(df, list(self.shuffle_cols), self.seed, session_col="globex_date", tod_col="et_min", min_gap=self.min_gap,
                          strata=strata, sessions=sess, allow_holdout=self.allow_holdout)

    def _features(self):
        key = (self.columns, self.shuffle_cols, self.seed, self.min_gap, self.allow_holdout, self.mask, self.strata)
        if key not in _C2_FRAMES:
            _, l2sim = self._mods()
            _C2_FRAMES[key] = l2sim.features_from_frame(self.frame(), self.columns)
        return _C2_FRAMES[key]

    def __call__(self, d):
        real = self.real()
        real._frame = self._features         # the ONLY difference to the real loader: the table (L2Features does the slicing)
        return real(d)


# ------------------------------------------------------------------ CLI

def _js(o):
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    return str(o)


def _brief_eval(r: dict) -> str:
    if "skipped" in r:
        return f"{r['firm']}: {r['skipped']}"
    ms = r["models"]
    return (f"{r['firm']} [{r['model']}] P1..P5 " + "/".join(f"{r[f'p{k}']:.3f}" for k in range(1, 6)) + f" bust5 {r['bust5']:.3f}"
            + (f" CI[{r['ci_p5'][0]:.2f},{r['ci_p5'][1]:.2f}]" if r.get("ci_p5") else "")
            + " | P5 eod/realized/intraday " + "/".join(f"{ms[b]['p5']:.3f}" for b in MODELS))


def _brief_funded(r: dict) -> str:
    if "skipped" in r:
        return f"{r['variant']}: {r['skipped']}"
    return (f"{r['variant']} [{r['model']}] E$40 {r['e_net_40']:.0f} P20/40/60 {r['p_pay_20']:.2f}/{r['p_pay_40']:.2f}/{r['p_pay_60']:.2f} "
            f"med {r['med_days_first']} bust-pre {r['p_bust_pre_first']:.2f} | E$40 " + " ".join(f"{m}={v['e_net_40']:.0f}" for m, v in r["models"].items()))


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="L2 scoring adapter (see the module docstring)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("export", help="export the approved picks' in-sample R bundles to L/trades/R__*.json")
    bl = sub.add_parser("baseline", help="score every approved pick in-sample (own firm, + the Apex 300K PA) -> L/out/baseline_insample.json")
    bl.add_argument("--no-apex300", action="store_true", help="skip the Apex Legacy 300K PA block")
    bl.add_argument("--search", action="store_true", help="apex300: also search apex300.GRID for the compliant sources (minutes)")
    bl.add_argument("--search-starts", default="fresh", help="apex300 search: comma list of start states, or 'all' (default fresh)")
    bl.add_argument("--workers", type=int, default=6)
    bl.add_argument("--boots", type=int, default=2000)
    bl.add_argument("--out", default="baseline_insample.json")
    e = sub.add_parser("eval", help="score_eval of one trade source")
    f = sub.add_parser("funded", help="score_funded of one trade source")
    s = sub.add_parser("search", help="search_rules of one trade source")
    for p in (e, f, s):
        p.add_argument("trades")
        p.add_argument("--firm", required=True)
        p.add_argument("--sess", default="all")
    for p in (e, f):
        p.add_argument("--micros", type=int, default=None)
        p.add_argument("--rules", default="{}", help='JSON, e.g. \'{"day_take":1500,"day_lock":750,"target_take":1}\'')
        p.add_argument("--model", default=None)
    f.add_argument("--policy", default="500")
    f.add_argument("--start", default="fresh", help="apex300_pa / apex50_pa: fresh | plus3000 | plus7600 | all | a profit in $")
    f.add_argument("--strategy", default=None, help="Apex gate: family name (straddle / orb / lon_break ... are OCO = non-compliant)")
    f.add_argument("--inputs", default=None, help="Apex gate: the family inputs as JSON (tgt_r ...)")
    f.add_argument("--one-direction", action="store_true", help="Apex gate: declare that the family never works orders on both sides")
    f.add_argument("--both-sides", action="store_true", help="Apex gate: the family works orders on both sides (non-compliant)")
    s.add_argument("--csv", default=None, help="write the grid rows to L/out/<csv>")
    a = ap.parse_args(argv)
    if a.cmd == "export":
        for k, p in export_baseline().items():
            print(k, "->", p)
        return 0
    if a.cmd == "baseline":
        res = {"window": make_calendar().window, "own_firm": {}, "alt": {}}
        for n, b in {**BASELINE, **BASELINE_ALT}.items():
            r = score_baseline(n, boots=a.boots)
            print(f"{n} ({b['key']} {b['sess']} m{b['micros']}): " + (_brief_eval(r) if b["kind"] == "eval" else _brief_funded(r)), flush=True)
            r.pop("series", None)
            res["alt" if n in BASELINE_ALT else "own_firm"][n] = {"pick": {k: v for k, v in b.items() if k != "src"}, **r}
        if not a.no_apex300 and "apex300_pa" in funded_variants():
            x = res["apex300_pa"] = score_baseline_apex300(search=a.search, workers=a.workers,
                                                             search_starts=None if a.search_starts == "all" else tuple(a.search_starts.split(",")))
            for st, v in x["bar"].items():
                print(f"apex300_pa bar [{st}; consistency base {x['cons_base']}]: " + ("no compliant cell" if v is None else
                      f"E$40 {v['e_net_40']:.0f} ({x['cons_alt']}: {v['e_net_40_cons_' + x['cons_alt']]:.0f}) P40 {v['p_pay_40']:.2f} "
                      f"bust-pre {v['p_bust_pre_first']:.2f} <- {v['from']} m{v['micros']} {v['rules']} T{v['policy']}"), flush=True)
        OUT.mkdir(exist_ok=True)
        (OUT / a.out).write_text(json.dumps(res, indent=1, default=_js))
        print("->", OUT / a.out)
        return 0
    if a.cmd == "eval":
        print(_brief_eval(score_eval(a.trades, a.firm, json.loads(a.rules), a.model, micros=a.micros, sess=a.sess)))
    elif a.cmd == "funded":
        pol = None if a.policy == "none" else ("max" if a.policy == "max" else int(a.policy))
        sts = start_states(a.firm) if a.start == "all" else [a.start if a.start in start_states(a.firm) else float(a.start)]
        bs = True if a.both_sides else (False if a.one_direction else None)
        for st in sts:
            r = score_funded(a.trades, a.firm, pol, micros=a.micros, rules=json.loads(a.rules), sess=a.sess, model=a.model, start=st,
                             strategy=a.strategy, inputs=json.loads(a.inputs) if a.inputs else None, both_sides=bs)
            print((f"[{r['start']}] " if len(sts) > 1 or st != "fresh" else "") + _brief_funded(r)
                  + (f" | compliant {r['compliant']} {r.get('compliance')} {r['apex_flags']}" if "compliant" in r else ""))
    else:
        r = search_rules(a.trades, a.firm, sess=a.sess, out_csv=a.csv)
        for nm, p in r["picks"].items():
            print(f"{nm}: {p['rules']} stab {p['stab']:.3f} P5 eod/realized/intraday " + "/".join(f"{p['models'][b]['p5']:.3f}" for b in MODELS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
