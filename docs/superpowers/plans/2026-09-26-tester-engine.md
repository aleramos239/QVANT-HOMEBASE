# Strategy Tester — tick-accurate backend (engine, strategies, runs, API) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A backend that replays the exchange tape session by session through Python strategies shared with the desk, fills orders by the research "house law", and serves TradingView-style reports and run bundles to the chart page over the chart service's API.

**Architecture:** `homebase/strategies/` holds the strategy contract and the four v1 strategies (defaults read from the desk's own config, legs identical to `engine._legs`). `homebase/backtest/` holds `tape.py` (archive → per-session binary cache + coverage check), `engine.py` (one strict-row-order pass per session), `stats/` (vendored ONYX metrics) + `report.py`, `discipline.py` (research window / IS months / holdout spends), `runner.py` (validated runs executed one at a time in a child process, into `homebase/.state/tester/runs/<id>/`) and `propsim/` (the vendored ONYX prop-eval Monte Carlo, run on every run's daily net P&L → `propsim.json`). `homebase/charts/tester_api.py` exposes the runs as a FastAPI router that `server.py` includes with two lines.

**Tech Stack:** Python 3.14 stdlib (`array`, `bisect`, `csv`, `gzip`, `fcntl`, `subprocess`), FastAPI (already a dependency), pytest. No numpy / pandas / pyarrow in homebase (see Ruling R1). The golden fixture generator alone runs under the ONYX TRADING venv (pandas/numpy), read-only.

**Spec:** `docs/superpowers/specs/2026-09-26-strategy-tester-design.md` (APPROVED; the binding authority — where this plan and the spec differ, the Rulings below say why).

## Global Constraints

- Work only inside `/Users/ramoscapital/ramos-quant-homebase/.worktrees/tester` (branch `feat/tester-engine`). Never touch `/Users/ramoscapital/ramos-quant-homebase` outside `.worktrees/tester` — that checkout runs the LIVE trading desk.
- Never write under `~/futures_ticks`. It is read-only for everything in this plan: the loader, the tests, the fixture generator. The tape cache goes to `~/futures_derived/homebase_tape/` (tests: pytest's `tmp_path`).
- Tests never open broker connections or use tokens. Tests never write outside pytest's `tmp_path` (the golden test reads `~/futures_ticks` read-only and caches in `tmp_path`).
- Never restart services or run `deploy/install.sh`; never `launchctl`; never start the chart service from Bash.
- `.venv` is a symlink to the live desk's venv: never `pip install` into it. Everything in `homebase/` stays stdlib + the existing requirements (`requirements.txt` is unchanged).
- The desk's own code is read-only here: no edits to `homebase/engine.py`, `homebase/rules.py`, `homebase/config.py`, `homebase/gate.py`, `homebase/timer.py`, `homebase/contracts.py`, `homebase/symbols.py`. `homebase/charts/server.py` gets exactly two added lines (Task 9) — another branch is editing it.
- Commit on `feat/tester-engine` with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (as the last `-m` paragraph). Never push.
- The user's shell hook blocks `rm -rf` and blocks any single command containing both the words "live" and "tradovate". (Delete a scratch dir with `.venv/bin/python -c "import shutil; shutil.rmtree('...')"`; keep those two words out of one command line, commit messages included.)
- Python: `.venv/bin/python -m pytest -q` from the worktree root. The full suite must stay green after every task (281 tests pass at the start).
- Exact values, carried verbatim from the spec and the research:
  - **House law.** A stop entry fills market-on-touch at `max/min(trigger, print) ± slip`, so a gap is paid. The target is a resting limit that needs **1-tick penetration** and fills at its price with no slip. The stop-loss fills touch/market with slip. Commission is flat per round turn. Ties at one `ts_ns` resolve in row order.
  - Commission default **$4.00** per round turn per contract; slippage default **1 tick per side on market/stop fills, 0 on limits**.
  - Orders go live **85 ms** (`placement_ms`) after the event that sent them (the research's measured placement latency).
  - Performance: a full 2021–2024 `nq930` run with a warm cache in **≤ 30 s**.
  - Research window **2021-01-01 → 2024-12-31** (the default range); IS months **Jan/Apr/Jul/Oct**; holdout boundary **2025-01-01** (any range reaching it needs the Holdout switch + a one-line reason, logged to `homebase/.state/tester/spends.jsonl`).
  - Sharpe = daily P&L mean / sd × √252; every money figure in dollars; RR shown as **1:X**.

## Rulings (spec ambiguities resolved; executors follow these)

- **R1 — no numpy/pyarrow; the cache is `<date>.tape`, not `<date>.parquet`.** The desk venv is shared with the live app and must never be pip-installed into, and it has no pyarrow. The cache keeps the spec's idea and path (`~/futures_derived/homebase_tape/<ROOT>/<date>.tape`, one file per session, built on first use) in a stdlib binary layout (int64 `ts_ns`, float64 price, int32 size, ~20 B/print ≈ 7 MB per NQ session ≈ 6 GB for NQ 2021-09→2024-12). Measured while planning: warm `nq930` = **2.6 ms/session** (~3 s for 2021–2024); a cold build ≈ 0.2 s/session serial, 8 s for NQ 2024 with `--jobs 8`.
- **R2 — strategy defaults are read from the desk's config at call time** (`homebase.config.load()`: `config.json` over the frozen defaults). In this worktree (no `config.json`) that is off 10 / SL 5 / TP 15, gated, matching the spec table; on the desk today `config.json` says `nq930` off 5, ungated (amendment 2026-09-16), and the tester there shows exactly that. Parity tests pin defaults to `load()` and prove they follow the file.
- **R3 — a time exit fills on the first print at or after the flat time** (spec), not the research's last print at or before it. The golden fixture records both prices; the test asserts the spec's.
- **R4 — the anchor is the last print strictly before 09:30:00.000 ET** (the research and the desk's timer), reading the spec's "≤ 09:30:00" as "before the fire". In the engine: `ctx.last_price` = the last print before the current event time.
- **R5 — event timing.** Scheduled events (session start, bar closes, `on_time`) run before the first print at or after their time. Orders the strategy sends go live `placement_ms` (85) later. `ctx.cancel`/`ctx.flatten` act at once, so scheduled cancels and flats happen at the first print at or after the time. A position's SL/TP go live on the print after the entry print (strict row order; the research also let earlier rows sharing the entry's `ts_ns` exit — the golden sessions exclude that quirk).
- **R6 — limit entries need 1-tick penetration too** (same law as a target). Orders that trigger on one print fill oldest first. `ctx.flatten()` closes every position and cancels every working order; a position still open when the window's tape ends exits at the last print, reason `eod`.
- **R7 — the ADX gate** reads whole-session daily H/L/C from the tape cache (the last ≤ 250 completed sessions, like the timer's `GATE_BARS`); under 110 bars (`MIN_GATE_BARS`) the day is skipped "trend gate unknown", as the desk refuses to fire.
- **R8 — a holdout spend is written when the run is accepted** (before it executes), so a cancelled or failed look still counts. The Holdout switch on a range inside the research window writes nothing.
- **R9 — "IS months"** = Jan/Apr/Jul/Oct sessions inside the research window by default; start/end may be given, and the holdout rule applies whenever the end reaches 2025-01-01.
- **R10 — % metrics** (net %, drawdown %) are against a `capital` run input, default **$50,000** (the prop account size); shown in Properties.
- **R11 — `gc_nfpcpi` ships the 2021–2026 event calendar** (`research/data/gc_0830_redfolder_days_2021_2026.csv`, a superset of the 2021–2024 one) so a holdout run has its events; defaults are the research spec (off 2 / SL 3 / TP 6, 08:30 fire, 08:45 cancel, 09:55 flat).
- **R12 — `nq10am` calls the desk's `rules.nq_10am_continuation` verbatim** (one definition) and so has no tunable inputs in v1.
- **R13 — cancel from the page** works for runs the chart service launched; a script run (`python -m homebase.backtest.runner run …`) is stopped where it runs (Ctrl-C). An `fcntl` lock on `runs/.lock` keeps a script run and a page run from overlapping.
- **R14 — coverage** is checked per clock-hour piece of the strategy's `session_window`; half-days are skipped and listed like the known Massive holes.
- **R15 — Sharpe/Sortino days are ET session dates** that traded (flat days not padded, the vendored stats' convention). Sortino uses the downside deviation `sqrt(mean(min(day, 0)²))`. The t-stat is the per-trade mean over its standard error.
- **R16 — the prop sim samples ONYX's weekday grid by ET session date**: every Mon–Fri from the run's first to its last trading session, 0.0 on weekdays without a trade (calendar weekdays = the fee clock). A run with no trades writes `{"skipped": …}`. The runner uses the notebook defaults (20,000 paths, 250-weekday horizon, seed 20260801) with the sweep and degradation blocks off, as ONYX's web endpoints do. Measured while planning: ≤ 1.3 s on real `nq930` ledgers, under the spec's 3 s.
- **R17 — rule sets.** A rule file is *unconfirmed* iff it says `"confirmed": false`. `lucid-flex-50k@2026-08.json` ships byte-for-byte (confirmed by the account holder, per its `source`). `apex-50k@unconfirmed.json` has the same schema, with every rule number copied from LucidFlex, listed in `placeholder_fields` and flagged PLACEHOLDER; its results are labelled `Apex 50K · unconfirmed rules`. When the user confirms the real numbers, replace them, set `"confirmed": true` and rename the file `apex-50k@<YYYY-MM>.json`. `propsim.py` is untracked in ONYX's git, so its provenance is the path + sha256.

## File map

| File | Responsibility |
|---|---|
| `homebase/backtest/__init__.py` | package docstring (stdlib-only rule) |
| `homebase/backtest/tape.py` | `et_ns`; archive → `.tape` cache; front-contract pick; daily H/L/C; coverage; `warm` CLI |
| `homebase/backtest/engine.py` | `Costs`, `Order`, `Trade`, `Ctx`, `run_session`, `build_bars` — the house law |
| `homebase/backtest/stats/{__init__,ledger,stats}.py` | vendored ONYX metrics (generated, provenance header) |
| `homebase/backtest/report.py` | performance summary All/Long/Short, year/month tables, equity |
| `homebase/backtest/discipline.py` | ranges, holdout check, spend log |
| `homebase/backtest/runner.py` | validate/prepare, `execute` → bundle, `RunManager`, CLI |
| `homebase/backtest/propsim/propsim.py`, `propsim/rules/lucid-flex-50k@2026-08.json` | vendored ONYX prop-eval Monte Carlo + its rules (generated, provenance header) |
| `homebase/backtest/propsim/__init__.py`, `propsim/rules/apex-50k@unconfirmed.json` | rule listing/loading, weekday grid, `evaluate` → `propsim.json`; the Apex placeholder |
| `homebase/strategies/base.py` | `Input`, `resolve_inputs`, `Strategy` |
| `homebase/strategies/straddle.py` | `OpenStraddle`, `DeskStraddle`, `Leg`, `desk_cfg`, gate constants |
| `homebase/strategies/{nq930,ym930,nq10am,gc_nfpcpi}.py` | the v1 strategies |
| `homebase/strategies/data/gc_0830_redfolder_days_2021_2026.csv` | GC event calendar (copied) |
| `homebase/strategies/__init__.py` | `REGISTRY`, `get`, `catalog` |
| `homebase/charts/tester_api.py` | `make_router`, `tester_router` |
| `homebase/charts/server.py` | +2 lines: import + `include_router` |
| `tests/test_backtest_tape.py`, `test_strategy_contract.py`, `test_backtest_engine.py`, `test_strategies.py`, `test_backtest_golden.py`, `test_backtest_stats_vendored.py`, `test_backtest_report.py`, `test_backtest_discipline.py`, `test_backtest_runner.py`, `test_backtest_propsim.py`, `test_tester_api.py`, `backtest_util.py` | tests |
| `tests/fixtures/make_nq930_golden.py`, `tests/fixtures/nq930_golden.json` | golden fixture generator + its output |

---

### Task 1: Tape loader, per-session cache and coverage check

**Files:**
- Create: `homebase/backtest/__init__.py`, `homebase/backtest/tape.py`
- Test: `tests/test_backtest_tape.py`

**Interfaces:**
- Consumes: `tests/charts_util.py` (`FIELDS`, `rows`, `write_archive`, `write_gz`) — existing.
- Produces:
  - `et_ns(d: date, hhmm: str) -> int` ("HH:MM" or "HH:MM:SS" ET → UTC epoch ns)
  - `Tape(root, date, contract, ts: array('q'), px: array('d'), size: array('i'), daily: dict)`
  - `TapeStore(archive=ARCHIVE, cache=CACHE, min_ticks=MIN_TICKS)` with `.sessions(root, start, end) -> list[date]`, `.pick(root, d) -> (Path, contract) | None`, `.cache_path(root, d)`, `.cached(root, d) -> bool`, `.build(root, d) -> Path | None`, `.load(root, d) -> Tape | None`, `.daily(root, d) -> {"date","h","l","c"} | None`
  - `missing_hours(ts, d, window: (str, str)) -> list[(str, str)]`, `coverage_reason(gaps) -> str`
  - `read_archive_csv(path)`, `stable_sorted(ts, px, sz)`, `ARCHIVE`, `CACHE`, `MIN_TICKS = 1000`, `main()` (`python -m homebase.backtest.tape warm ROOT START END [--jobs N]`)

- [ ] **Step 1: Write the failing tests** — `tests/test_backtest_tape.py`:

```python
"""Tape loader: front-contract pick, cache, tape order, coverage — on a synthetic archive."""
from __future__ import annotations

import datetime as dt
import json
import os

import pytest

from homebase.backtest import tape as tape_mod
from homebase.backtest.tape import TapeStore, coverage_reason, et_ns, missing_hours
from tests.charts_util import FIELDS, rows, write_archive, write_gz

D = dt.date(2024, 3, 5)                                   # Tuesday


def ms(hms: str) -> int:
    return et_ns(D, hms) // 1_000_000


def archive(tmp_path, n=1500, contract="NQH4", start="09:00:00", step_ms=1000):
    base = tmp_path / "ticks"
    write_archive(base, "NQ", D, contract, rows(ms(start), [100.0 + (i % 8) * 0.25 for i in range(n)],
                                                step_ms=step_ms))
    return base


def listing(p):
    return sorted((str(q.relative_to(p)), q.stat().st_mtime_ns) for q in p.rglob("*"))


def test_front_contract_is_the_file_with_the_most_ticks(tmp_path):
    base = archive(tmp_path, n=1500, contract="NQH4")
    write_archive(base, "NQ", D, "NQM4", rows(ms("09:00:00"), [200.0] * 1200))
    s = TapeStore(base, tmp_path / "cache")
    assert s.pick("NQ", D)[1] == "NQH4"
    t = s.load("NQ", D)
    assert t.contract == "NQH4" and len(t.ts) == 1500 and t.px[0] == 100.0


def test_a_holiday_stub_under_min_ticks_has_no_tape(tmp_path):
    s = TapeStore(archive(tmp_path, n=999), tmp_path / "cache")
    assert s.pick("NQ", D) is None and s.load("NQ", D) is None


def test_live_recordings_are_never_used(tmp_path):
    base = tmp_path / "ticks"
    write_gz(base / "NQ" / "2024" / f"{D}_NQH4.live.csv.gz", rows(ms("09:00:00"), [1.0] * 2000))
    assert TapeStore(base, tmp_path / "cache").pick("NQ", D) is None


def test_ts_ns_is_used_when_present_and_ts_ms_otherwise(tmp_path):
    base = tmp_path / "ticks"
    rs = rows(ms("09:30:00"), [100.0] * 1200)
    for i, r in enumerate(rs):
        r["ts_ns"] = r["ts_ms"] * 1_000_000 + 7 + i
    p = write_gz(base / "NQ" / "2024" / f"{D}_NQH4.csv.gz", rs, fields=FIELDS + ["ts_ns"])
    p.with_name(f"{D}_NQH4.json").write_text(json.dumps({"ticks": 1200}))
    t = TapeStore(base, tmp_path / "cache").load("NQ", D)
    assert t.ts[0] == et_ns(D, "09:30:00") + 7
    t2 = TapeStore(archive(tmp_path / "b"), tmp_path / "cache2").load("NQ", D)
    assert t2.ts[0] == et_ns(D, "09:00:00")


def test_out_of_order_rows_are_stable_sorted_keeping_same_ts_row_order(tmp_path):
    base = tmp_path / "ticks"
    rs = rows(ms("09:30:00"), [float(i) for i in range(1200)])
    rs[5]["ts_ms"] = rs[3]["ts_ms"]                        # row 5 shares row 3's stamp...
    rs[1], rs[2] = rs[2], rs[1]                            # ...and rows 1/2 arrive swapped
    write_archive(base, "NQ", D, "NQH4", rs)
    t = TapeStore(base, tmp_path / "cache").load("NQ", D)
    assert list(t.px[:6]) == [0.0, 1.0, 2.0, 3.0, 5.0, 4.0]    # 5 sorts with 3, after it


def test_the_cache_is_built_once_and_rebuilt_when_the_source_changes(tmp_path, monkeypatch):
    base = archive(tmp_path)
    s = TapeStore(base, tmp_path / "cache")
    assert not s.cached("NQ", D)
    s.load("NQ", D)
    assert s.cache_path("NQ", D).exists() and s.cached("NQ", D)
    calls = []
    real = tape_mod.read_archive_csv
    monkeypatch.setattr(tape_mod, "read_archive_csv", lambda p: calls.append(p) or real(p))
    s.load("NQ", D)
    assert calls == []                                     # served from the cache
    src = base / "NQ" / "2024" / f"{D}_NQH4.csv.gz"
    os.utime(src, ns=(src.stat().st_atime_ns, src.stat().st_mtime_ns + 1_000_000_000))
    s.load("NQ", D)
    assert len(calls) == 1                                 # stale -> rebuilt


def test_nothing_is_ever_written_under_the_archive(tmp_path):
    base = archive(tmp_path)
    before = listing(base)
    s = TapeStore(base, tmp_path / "cache")
    s.load("NQ", D)
    s.daily("NQ", D)
    assert listing(base) == before
    with pytest.raises(ValueError):
        TapeStore(base, base / "NQ" / "cache")


def test_daily_bar_is_the_whole_session(tmp_path):
    s = TapeStore(archive(tmp_path), tmp_path / "cache")
    assert s.daily("NQ", D) == {"date": "2024-03-05", "h": 101.75, "l": 100.0, "c": 100.0 + (1499 % 8) * 0.25}


def test_sessions_lists_weekdays_with_a_manifest_in_range(tmp_path):
    base = archive(tmp_path)
    write_archive(base, "NQ", dt.date(2024, 3, 9), "NQH4", rows(ms("09:00:00"), [1.0] * 1500))   # Saturday
    write_archive(base, "NQ", dt.date(2024, 3, 7), "NQH4", rows(ms("09:00:00"), [1.0] * 1500))
    s = TapeStore(base, tmp_path / "cache")
    assert s.sessions("NQ", dt.date(2024, 3, 1), dt.date(2024, 3, 31)) == [D, dt.date(2024, 3, 7)]
    assert s.sessions("NQ", dt.date(2024, 3, 6), dt.date(2024, 3, 6)) == []


def test_missing_hours_lists_runs_of_empty_clock_hours(tmp_path):
    base = tmp_path / "ticks"
    rs = rows(ms("09:25:00"), [1.0] * 2100, step_ms=6000)          # 09:25 -> 12:55
    rs += rows(ms("15:10:00"), [1.0] * 100, step_ms=6000)          # 15:10 -> 15:20
    write_archive(base, "NQ", D, "NQH4", rs)
    t = TapeStore(base, tmp_path / "cache").load("NQ", D)
    gaps = missing_hours(t.ts, D, ("09:25", "16:00"))
    assert gaps == [("13:00", "15:00")]
    assert coverage_reason(gaps) == "missing 13:00–15:00 ET"
    assert missing_hours(t.ts, D, ("09:25", "13:00")) == []
    assert missing_hours(t.ts, D, ("08:20", "09:56")) == [("08:20", "09:00")]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_backtest_tape.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'homebase.backtest'`.

- [ ] **Step 3: Implement** — `homebase/backtest/__init__.py`:

```python
"""The Strategy Tester's backend: tick tapes, the house-law engine, reports, runs.

Stdlib only: the desk's venv (shared with the live trading app) carries no
numpy / pandas / pyarrow and is never pip-installed into.
"""
```

`homebase/backtest/tape.py`:

```python
"""Session tapes for the Strategy Tester.

Source: ~/futures_ticks/<ROOT>/<YYYY>/<date>_<contract>.csv.gz — READ-ONLY, never
written. The front contract of a session is the archive file whose manifest
counts the most ticks (the research rule; a session under MIN_TICKS is a
holiday stub and has no tape). The chart service's own `.live.csv.gz`
recordings are never used.

Cache: one binary file per session, ~/futures_derived/homebase_tape/<ROOT>/<date>.tape,
built on first use (the desk's venv has no pyarrow, so not parquet):
  MAGIC, u32 header length, JSON header {v, root, date, contract, src, src_mtime_ns,
  src_size, n, byteorder, daily: {h, l, c}}, then n x int64 ts_ns, n x float64
  price, n x int32 size. A cache whose source file changed is rebuilt.
Rows keep TAPE ORDER: a stable sort by ts_ns, applied only if the file is not
already sorted (prints sharing a nanosecond keep their row order).

Coverage: any clock hour inside a strategy's session window with zero prints
means the session is skipped and listed ("missing 13:00–15:00 ET").
"""
from __future__ import annotations

import csv
import datetime as dt
import gzip
import json
import os
import sys
import zlib
from array import array
from bisect import bisect_left
from dataclasses import dataclass
from operator import le
from pathlib import Path

from zoneinfo import ZoneInfo

ARCHIVE = Path.home() / "futures_ticks"
CACHE = Path.home() / "futures_derived" / "homebase_tape"
MIN_TICKS = 1000
MAGIC = b"HBTAPE1\n"
CACHE_VERSION = 1
ET = ZoneInfo("America/New_York")


def et_ns(d: dt.date, hhmm: str) -> int:
    """'HH:MM' or 'HH:MM:SS' ET wall clock on calendar day d -> UTC epoch ns."""
    t = dt.time.fromisoformat(hhmm)
    return int(dt.datetime.combine(d, t, tzinfo=ET).timestamp()) * 1_000_000_000


@dataclass
class Tape:
    root: str
    date: dt.date
    contract: str
    ts: array           # 'q' UTC epoch ns, tape order
    px: array           # 'd'
    size: array         # 'q'
    daily: dict         # the whole session's {"h", "l", "c"}


def _inside(p: Path, parent: Path) -> bool:
    try:
        p.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def read_archive_csv(path: Path) -> tuple[array, array, array]:
    """(ts_ns, price, size) in file order. ts_ns falls back to ts_ms * 1e6
    (desk recordings carry ms only). A torn gzip tail keeps what was read."""
    ts, px, sz = array("q"), array("d"), array("i")
    try:
        with gzip.open(path, "rt", newline="") as fh:
            rd = csv.reader(fh)
            head = next(rd, None) or []
            ix = {k: i for i, k in enumerate(head)}
            ip, isz, ims, ins = ix["price"], ix["size"], ix["ts_ms"], ix.get("ts_ns")
            n = len(head)
            for r in rd:
                if len(r) != n or r[0] == head[0]:
                    continue
                t = r[ins] if ins is not None else ""
                ts.append(int(t) if t else int(r[ims]) * 1_000_000)
                px.append(float(r[ip]))
                sz.append(int(r[isz] or 0))
    except (EOFError, zlib.error, OSError):
        pass
    return ts, px, sz


def stable_sorted(ts: array, px: array, sz: array) -> tuple[array, array, array]:
    if all(map(le, ts, ts[1:])):
        return ts, px, sz
    order = sorted(range(len(ts)), key=ts.__getitem__)       # list.sort is stable
    return (array("q", (ts[i] for i in order)), array("d", (px[i] for i in order)),
            array("i", (sz[i] for i in order)))


def missing_hours(ts, d: dt.date, window: tuple[str, str]) -> list[tuple[str, str]]:
    """Runs of clock-hour pieces of the ET window [start, end) with zero prints,
    e.g. [("13:00", "15:00")]. Pieces are cut at every o'clock."""
    t0 = dt.datetime.combine(d, dt.time.fromisoformat(window[0]))
    t1 = dt.datetime.combine(d, dt.time.fromisoformat(window[1]))
    cuts = [t0]
    h = t0.replace(minute=0, second=0) + dt.timedelta(hours=1)
    while h < t1:
        cuts.append(h)
        h += dt.timedelta(hours=1)
    cuts.append(t1)
    out: list[list[str]] = []
    for a, b in zip(cuts, cuts[1:]):
        na, nb = et_ns(d, a.strftime("%H:%M:%S")), et_ns(d, b.strftime("%H:%M:%S"))
        if bisect_left(ts, nb) - bisect_left(ts, na) > 0:
            continue
        sa, sb = a.strftime("%H:%M"), b.strftime("%H:%M")
        if out and out[-1][1] == sa:
            out[-1][1] = sb
        else:
            out.append([sa, sb])
    return [(a, b) for a, b in out]


def coverage_reason(gaps: list[tuple[str, str]]) -> str:
    return "missing " + ", ".join(f"{a}–{b}" for a, b in gaps) + " ET"


class TapeStore:
    def __init__(self, archive: Path = ARCHIVE, cache: Path = CACHE, min_ticks: int = MIN_TICKS):
        self.archive, self.cache, self.min_ticks = Path(archive), Path(cache), min_ticks
        if _inside(self.cache, self.archive):
            raise ValueError(f"the tape cache may never live under the tick archive ({self.archive})")

    def sessions(self, root: str, start: dt.date, end: dt.date) -> list[dt.date]:
        """Weekday session dates in [start, end] that have any archive manifest."""
        out = set()
        for y in range(start.year, end.year + 1):
            for man in (self.archive / root / str(y)).glob("*.json"):
                try:
                    d = dt.date.fromisoformat(man.name[:10])
                except ValueError:
                    continue
                if start <= d <= end and d.weekday() < 5:
                    out.add(d)
        return sorted(out)

    def pick(self, root: str, d: dt.date) -> tuple[Path, str] | None:
        """(csv.gz path, contract) of the session's front contract, or None."""
        best, best_n = None, 0
        for man in sorted((self.archive / root / str(d.year)).glob(f"{d.isoformat()}_*.json")):
            try:
                n = int(json.loads(man.read_text())["ticks"])
            except (OSError, ValueError, KeyError, TypeError):
                continue
            if n > best_n:
                best, best_n = man, n
        if best is None or best_n < self.min_ticks:
            return None
        gz = best.with_name(best.name[:-len(".json")] + ".csv.gz")
        return (gz, best.name[len("YYYY-MM-DD_"):-len(".json")]) if gz.exists() else None

    def cache_path(self, root: str, d: dt.date) -> Path:
        return self.cache / root / f"{d.isoformat()}.tape"

    def _header(self, p: Path) -> dict | None:
        try:
            with open(p, "rb") as f:
                if f.read(len(MAGIC)) != MAGIC:
                    return None
                n = int.from_bytes(f.read(4), "little")
                return json.loads(f.read(n))
        except (OSError, ValueError):
            return None

    def _fresh(self, head: dict | None, src: Path) -> bool:
        if not head or head.get("v") != CACHE_VERSION or head.get("byteorder") != sys.byteorder:
            return False
        st = src.stat()
        return head.get("src") == src.name and head.get("src_mtime_ns") == st.st_mtime_ns \
            and head.get("src_size") == st.st_size

    def cached(self, root: str, d: dt.date) -> bool:
        got = self.pick(root, d)
        return got is not None and self._fresh(self._header(self.cache_path(root, d)), got[0])

    def build(self, root: str, d: dt.date) -> Path | None:
        got = self.pick(root, d)
        if got is None:
            return None
        src, contract = got
        st = src.stat()
        ts, px, sz = stable_sorted(*read_archive_csv(src))
        if not ts:
            return None
        head = {"v": CACHE_VERSION, "root": root, "date": d.isoformat(), "contract": contract,
                "src": src.name, "src_mtime_ns": st.st_mtime_ns, "src_size": st.st_size,
                "n": len(ts), "byteorder": sys.byteorder,
                "daily": {"h": max(px), "l": min(px), "c": px[-1]}}
        p = self.cache_path(root, d)
        if _inside(p, self.archive):
            raise ValueError("refusing to write under the tick archive")
        p.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(head).encode()
        tmp = p.with_name(p.name + f".{os.getpid()}.tmp")
        with open(tmp, "wb") as f:
            f.write(MAGIC)
            f.write(len(raw).to_bytes(4, "little"))
            f.write(raw)
            ts.tofile(f)
            px.tofile(f)
            sz.tofile(f)
        os.replace(tmp, p)
        return p

    def load(self, root: str, d: dt.date) -> Tape | None:
        got = self.pick(root, d)
        if got is None:
            return None
        p = self.cache_path(root, d)
        if not self._fresh(self._header(p), got[0]):
            if self.build(root, d) is None:
                return None
        with open(p, "rb") as f:
            f.read(len(MAGIC))
            head = json.loads(f.read(int.from_bytes(f.read(4), "little")))
            n = head["n"]
            ts, px, sz = array("q"), array("d"), array("i")
            ts.fromfile(f, n)
            px.fromfile(f, n)
            sz.fromfile(f, n)
        return Tape(root, d, head["contract"], ts, px, sz, head["daily"])

    def daily(self, root: str, d: dt.date) -> dict | None:
        """The session's whole-day {"date", "h", "l", "c"} (builds the cache if needed)."""
        got = self.pick(root, d)
        if got is None:
            return None
        p = self.cache_path(root, d)
        head = self._header(p)
        if not self._fresh(head, got[0]):
            if self.build(root, d) is None:
                return None
            head = self._header(p)
        return {"date": d.isoformat(), **head["daily"]}


def _warm_one(args) -> str:
    archive, cache, root, d = args
    s = TapeStore(Path(archive), Path(cache))
    if not s.cached(root, d):
        s.build(root, d)
    return d.isoformat()


def main(argv: list[str] | None = None) -> None:
    """python -m homebase.backtest.tape warm NQ 2021-01-01 2024-12-31 [--jobs 4]"""
    import argparse
    from concurrent.futures import ProcessPoolExecutor
    ap = argparse.ArgumentParser(prog="python -m homebase.backtest.tape")
    ap.add_argument("cmd", choices=["warm"])
    ap.add_argument("root")
    ap.add_argument("start", type=dt.date.fromisoformat)
    ap.add_argument("end", type=dt.date.fromisoformat)
    ap.add_argument("--jobs", type=int, default=4)
    a = ap.parse_args(argv)
    store = TapeStore()
    days = store.sessions(a.root.upper(), a.start, a.end)
    jobs = [(str(store.archive), str(store.cache), a.root.upper(), d) for d in days]
    with ProcessPoolExecutor(max_workers=max(1, a.jobs)) as ex:
        for i, d in enumerate(ex.map(_warm_one, jobs), 1):
            if i % 50 == 0 or i == len(jobs):
                print(f"{i}/{len(jobs)} {d}", flush=True)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/test_backtest_tape.py` → Expected: 10 passed.
Run: `.venv/bin/python -m pytest -q` → Expected: all green (281 + 10).

- [ ] **Step 5: Commit**

```bash
git add homebase/backtest/__init__.py homebase/backtest/tape.py tests/test_backtest_tape.py
git commit -m "feat(tester): session tapes from the tick archive — read-only, a per-session binary cache, front contract by ticks, coverage check" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: The strategy contract and the house-law tick engine

**Files:**
- Create: `homebase/strategies/__init__.py` (minimal; Task 3 replaces it), `homebase/strategies/base.py`, `homebase/backtest/engine.py`
- Test: `tests/test_strategy_contract.py`, `tests/test_backtest_engine.py`

**Interfaces:**
- Consumes: `homebase.backtest.tape.et_ns`, `Tape` (Task 1); `homebase.contracts.point_value`, `tick_size` (existing).
- Produces:
  - `strategies.base.Input(key, label, type, default, min=None, max=None, step=None, choices=())` with `.to_dict()`; `resolve_inputs(schema, values) -> dict` (ValueError naming the key); `Strategy` with class attrs `id, name, root, session_window=("09:25","16:00"), bar_minutes=0, bar_window=None, placement_ms=85`, `__init__(params)` → `self.p`, classmethods `inputs()`, `describe()`, methods `times()`, `trades_on(d)`, `needs_daily()`, `on_session(ctx)`, `on_time(ctx, et_time)`, `on_bar(ctx, bar)`.
  - `engine.ENGINE_VERSION = "tick-1"`, `Costs(commission_rt=4.00, slippage_ticks=1.0)`, `Order`, `Trade` (fields: `date, side, qty, entry_ns, entry_price, exit_ns, exit_price, exit_reason ∈ {tp, sl, time, eod}, order_price, sl, tp, gross, commission, net, mae_pts, mfe_pts, mae_usd, mfe_usd, bars, seconds`; `.to_dict()`), `Bar(start_ns, end_ns, o, h, l, c, v)`, `SessionResult(date, trades, plots, hlines, skip)`, `to_tick(px, tick)`, `build_bars(ts, px, size, lo, hi, t0, t1, minutes)`, `run_session(strategy, tape, costs, qty=1, daily=None) -> SessionResult`.
  - `Ctx`: `root, date, tick, point_value, qty, daily, move_brackets_to_fill`, properties `now_ns`, `last_price`, `flat`; `stop_entry(side, price, qty=None, sl=None, tp=None, tp_rr=None)`, `limit_entry(...)`, `market(side, qty=None, sl=None, tp=None, tp_rr=None, ref=None)`, `oco(*orders)`, `cancel(order)`, `flatten(reason="time")`, `plot(name, t_ns, value)`, `hline(name, price)`, `skip(reason)`. Sides are `"long"`/`"short"`; `sl`/`tp` are absolute prices.

- [ ] **Step 1: Write the failing tests** — `tests/test_strategy_contract.py`:

```python
"""The strategy contract: the input schema and its validation."""
from __future__ import annotations

import pytest

from homebase.strategies.base import Input, Strategy, resolve_inputs


class Demo(Strategy):
    id, name, root = "demo", "Demo", "NQ"

    @classmethod
    def inputs(cls):
        return [Input("n", "N", "int", 3, 1, 10, 1)]


def test_resolve_inputs_validates_and_never_clamps():
    schema = [Input("n", "N", "int", 3, 1, 10, 1), Input("x", "X", "float", 1.5, 0.0, 2.0),
              Input("b", "B", "bool", False), Input("c", "C", "choice", "a", choices=("a", "b"))]
    assert resolve_inputs(schema, None) == {"n": 3, "x": 1.5, "b": False, "c": "a"}
    assert resolve_inputs(schema, {"n": 4.0, "x": 2}) == {"n": 4, "x": 2.0, "b": False, "c": "a"}
    for bad, msg in (({"zz": 1}, "unknown input"), ({"n": 11}, "within"), ({"n": 2.5}, "whole"),
                     ({"x": "1"}, "number"), ({"b": 1}, "true/false"), ({"c": "z"}, "one of"),
                     ({"n": True}, "number")):
        with pytest.raises(ValueError, match=msg):
            resolve_inputs(schema, bad)


def test_a_strategy_resolves_its_params_and_describes_itself():
    assert Demo().p == {"n": 3} and Demo({"n": 7}).p == {"n": 7}
    with pytest.raises(ValueError):
        Demo({"n": 0})
    d = Demo.describe()
    assert d == {"id": "demo", "name": "Demo", "root": "NQ", "session_window": ["09:25", "16:00"],
                 "bar_minutes": 0,
                 "inputs": [{"key": "n", "label": "N", "type": "int", "default": 3, "min": 1,
                             "max": 10, "step": 1, "choices": []}]}
    assert Demo.placement_ms == 85 and Demo().times() == [] and Demo().trades_on(None) is True
```

`tests/test_backtest_engine.py` (one test per fill-law case in the spec's Validation list):

```python
"""The tick engine's fill law, case by case, on synthetic tapes (no archive)."""
from __future__ import annotations

import datetime as dt
from array import array

from homebase.backtest.engine import Costs, build_bars, run_session, to_tick
from homebase.backtest.tape import Tape, et_ns
from homebase.strategies.base import Strategy

D = dt.date(2024, 3, 5)                      # a Tuesday
TICK = 0.25                                  # NQ; $20/pt


def tape(rows, root="NQ") -> Tape:
    """rows: [("HH:MM:SS.mmm", price), ...] in tape order."""
    ts, px = array("q"), array("d")
    for t, p in rows:
        hms, _, ms = t.partition(".")
        ts.append(et_ns(D, hms) + int(ms or 0) * 1_000_000)
        px.append(p)
    return Tape(root, D, "NQH4", ts, px, array("i", [1] * len(ts)), {})


class Script(Strategy):
    """A test strategy: {et_time: fn(ctx, self)} run by on_time."""
    id, root = "script", "NQ"
    session_window = ("09:25", "16:00")

    def __init__(self, plan, bars=0, move=True):
        super().__init__({})
        self.plan, self.bar_minutes, self.move, self.o = plan, bars, move, {}
        self.seen = []

    def times(self):
        return list(self.plan)

    def on_time(self, ctx, t):
        ctx.move_brackets_to_fill = self.move
        self.plan[t](ctx, self)

    def on_bar(self, ctx, bar):
        self.seen.append(bar)


def straddle(off=10.0, sl=5.0, tp=15.0):
    def fire(ctx, s):
        a = ctx.last_price
        s.o["buy"] = ctx.stop_entry("long", a + off, sl=a + off - sl, tp=a + off + tp)
        s.o["sell"] = ctx.stop_entry("short", a - off, sl=a - off + sl, tp=a - off - tp)
        ctx.oco(s.o["buy"], s.o["sell"])
    return fire


def cancel(ctx, s):
    for o in s.o.values():
        ctx.cancel(o)


def flat(ctx, s):
    ctx.flatten("time")


PLAN = lambda **kw: {"09:30:00": straddle(**kw), "12:55": cancel, "15:55": flat}  # noqa: E731


def one(rows, plan=None, slip=1.0, comm=4.0, **kw):
    res = run_session(Script(plan or PLAN(), **kw), tape(rows), Costs(comm, slip), qty=1)
    return res.trades


def test_gap_through_stop_entry_pays_the_gap_plus_slip():
    t, = one([("09:29:59", 100.0), ("09:30:01", 112.0), ("09:31", 140.0)])
    assert t.side == "long" and t.order_price == 110.0
    assert t.entry_price == 112.25                       # max(110, 112) + 1 tick
    assert (t.sl, t.tp) == (107.25, 127.25)              # brackets moved to the fill
    assert t.exit_reason == "tp" and t.exit_price == 127.25


def test_target_needs_one_tick_penetration():
    rows = [("09:29:59", 100.0), ("09:30:01", 110.0), ("09:31", 125.25), ("09:32", 125.25)]
    t, = one(rows + [("15:56", 120.0)])
    assert t.entry_price == 110.25 and t.tp == 125.25
    assert t.exit_reason == "time"                       # touched, never penetrated
    t, = one(rows + [("09:33", 125.5)])
    assert t.exit_reason == "tp" and t.exit_price == 125.25   # fills AT the limit, no slip


def test_stop_loss_is_touch_and_pays_slip_and_gap():
    t, = one([("09:29:59", 100.0), ("09:30:01", 110.0), ("09:31", 105.25)])
    assert (t.entry_price, t.sl) == (110.25, 105.25)
    assert t.exit_reason == "sl" and t.exit_price == 105.0          # min(105.25, 105.25) - 1 tick
    t, = one([("09:29:59", 100.0), ("09:30:01", 110.0), ("09:31", 104.0)])
    assert t.exit_price == 103.75                                    # the gap is paid too
    assert t.gross == round((103.75 - 110.25) * 20, 2) and t.net == t.gross - 4.0


def test_same_ts_prints_resolve_in_row_order():
    base = [("09:29:59", 100.0), ("09:30:01", 110.0)]
    t, = one(base + [("09:31", 125.5), ("09:31", 105.0)])
    assert t.exit_reason == "tp"
    t, = one(base + [("09:31", 105.0), ("09:31", 125.5)])
    assert t.exit_reason == "sl"


def test_oco_first_fill_cancels_the_other_leg():
    trades = one([("09:29:59", 100.0), ("09:30:01", 110.0), ("09:31", 125.5),
                  ("09:40", 85.0), ("09:41", 60.0)])
    assert [t.side for t in trades] == ["long"]


def test_orders_go_live_after_the_placement_latency():
    t, = one([("09:29:59", 100.0), ("09:30:00.050", 111.0), ("09:30:00.085", 110.5),
              ("09:31", 130.0)])
    assert t.entry_ns == et_ns(D, "09:30:00") + 85_000_000 and t.entry_price == 110.75


def test_anchor_is_the_last_print_strictly_before_the_fire():
    t, = one([("09:29:59", 100.0), ("09:30:00", 90.0), ("09:30:01", 110.0), ("09:31", 130.0)])
    assert t.order_price == 110.0                      # anchored at 100, not the 09:30:00 print


def test_unfilled_entries_are_cancelled_at_the_first_print_at_or_after_cancel_time():
    assert one([("09:29:59", 100.0), ("12:54:59", 105.0), ("12:55:00", 120.0)]) == []


def test_flat_fills_on_the_first_print_at_or_after_the_flat_time():
    t, = one([("09:29:59", 100.0), ("09:30:01", 110.0), ("15:54:59", 112.0),
              ("15:55:00.200", 113.0), ("15:56", 90.0)])
    assert t.exit_reason == "time" and t.exit_price == 112.75        # 113 - 1 tick
    assert t.exit_ns == et_ns(D, "15:55:00") + 200_000_000


def test_position_open_when_the_tape_ends_exits_eod_on_the_last_print():
    t, = one([("09:29:59", 100.0), ("09:30:01", 110.0), ("15:50", 112.0)])
    assert t.exit_reason == "eod" and t.exit_price == 111.75


def test_no_move_keeps_brackets_at_the_trigger():
    t, = one([("09:29:59", 100.0), ("09:30:01", 112.0), ("09:31", 125.5)], move=False)
    assert (t.sl, t.tp) == (105.0, 125.0) and t.exit_reason == "tp" and t.exit_price == 125.0


def test_slippage_zero_and_commission_inputs():
    t, = one([("09:29:59", 100.0), ("09:30:01", 110.0), ("09:31", 104.0)], slip=0, comm=2.5)
    assert (t.entry_price, t.exit_price) == (110.0, 104.0)
    assert t.net == round((104.0 - 110.0) * 20 - 2.5, 2)


def test_mae_mfe_bars_and_seconds():
    t, = one([("09:29:59", 100.0), ("09:30:01", 110.0), ("09:31:30", 108.0), ("09:32", 120.0),
              ("09:33", 125.5)])
    assert (t.mae_pts, t.mfe_pts) == (2.25, 15.25)
    assert (t.mae_usd, t.mfe_usd) == (45.0, 305.0)
    assert t.bars == 4 and t.seconds == 179.0


def test_market_entry_with_rr_target_rederived_from_the_fill():
    def go(ctx, s):
        ctx.market("short", sl=110.0, tp=95.0, tp_rr=0.75, ref=100.0)
    t, = one([("09:59:59", 100.0), ("10:00:00.100", 101.0), ("10:05", 93.5)],
             plan={"10:00": go, "15:55": flat})
    assert t.entry_price == 100.75                     # first print after 85 ms, minus 1 tick
    assert t.sl == 110.0 and t.tp == to_tick(100.75 - 0.75 * (110.0 - 100.75), TICK) == 93.75
    assert t.exit_reason == "tp" and t.exit_price == 93.75


def test_limit_entry_needs_penetration():
    def go(ctx, s):
        ctx.limit_entry("long", 99.0, sl=97.0, tp=103.0)
    assert one([("09:59:59", 100.0), ("10:01", 99.0), ("10:02", 99.0)],
               plan={"10:00": go, "15:55": flat}) == []
    t, = one([("09:59:59", 100.0), ("10:01", 98.75), ("10:02", 103.25)],
             plan={"10:00": go, "15:55": flat})
    assert t.entry_price == 99.0 and t.exit_reason == "tp"


def test_two_orders_triggered_by_one_print_both_fill_oldest_first():
    def go(ctx, s):
        ctx.stop_entry("long", 101.0, sl=90.0, tp=200.0)
        ctx.stop_entry("long", 102.0, sl=90.0, tp=200.0)
    trades = one([("09:59:59", 100.0), ("10:01", 103.0), ("10:30", 50.0)],
                 plan={"10:00": go, "15:55": flat}, move=False)
    assert [t.order_price for t in trades] == [101.0, 102.0]
    assert all(t.exit_reason == "sl" for t in trades)


def test_skip_is_recorded():
    def go(ctx, s):
        ctx.skip("gate")
    res = run_session(Script({"09:30:00": go}), tape([("09:29:59", 100.0)]), Costs())
    assert res.skip == "gate" and res.trades == []


def test_bars_close_before_the_next_print_and_are_built_from_ticks():
    tp = tape([("09:30:05", 100.0), ("09:30:40", 102.0), ("09:30:59", 101.0), ("09:32:10", 99.0)])
    bars = build_bars(tp.ts, tp.px, tp.size, 0, len(tp.ts), et_ns(D, "09:30"), et_ns(D, "09:35"), 1)
    assert [(b.o, b.h, b.l, b.c, b.v) for b in bars] == [(100.0, 102.0, 100.0, 101.0, 3),
                                                         (99.0, 99.0, 99.0, 99.0, 1)]
    assert bars[0].end_ns == et_ns(D, "09:31")
    s = Script({}, bars=1)
    run_session(s, tp, Costs())
    assert [b.c for b in s.seen] == [101.0, 99.0]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_strategy_contract.py tests/test_backtest_engine.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'homebase.strategies'`.

- [ ] **Step 3: Implement** — `homebase/strategies/__init__.py` (minimal for now):

```python
"""Strategies shared by the Strategy Tester and (later) the desk. See base.py."""
from __future__ import annotations

from .base import Input, Strategy, resolve_inputs

__all__ = ["Input", "Strategy", "resolve_inputs"]
```

`homebase/strategies/base.py`:

```python
"""The strategy contract shared by the Strategy Tester (now) and the desk (later).

A strategy is one class: metadata, an input schema, and event handlers that
act through a context (`ctx`) the tick engine provides. Stdlib only — the
chart service lists strategies in-process, so nothing here may import numpy
or the engine.

    class MyStraddle(Strategy):
        id, name, root = "x", "X straddle", "NQ"
        session_window = ("09:25", "16:00")        # ET [start, end) the tape must cover
        @classmethod
        def inputs(cls): return [Input("offset_pts", "Offset (pts)", "float", 10.0, 0.25, 100, 0.25)]
        def times(self): return ["09:30:00", "15:55"]
        def on_time(self, ctx, et_time): ...

Events (all times ET, all run BEFORE the first print at or after their time):
  on_session(ctx)            at session_window[0]
  on_bar(ctx, bar)           at each bar's close, when bar_minutes > 0
  on_time(ctx, et_time)      at each time in times(), et_time exactly as listed
Orders (see homebase/backtest/engine.py for the fill law):
  ctx.stop_entry / ctx.limit_entry / ctx.market -> Order;  ctx.oco(a, b);
  ctx.cancel(order);  ctx.flatten();  ctx.move_brackets_to_fill = True;
  ctx.plot(name, t_ns, value);  ctx.hline(name, price);  ctx.skip(reason)
"""
from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass, field
from typing import Any

TYPES = ("int", "float", "bool", "choice")


@dataclass(frozen=True)
class Input:
    key: str
    label: str
    type: str                       # int | float | bool | choice
    default: Any
    min: float | None = None
    max: float | None = None
    step: float | None = None
    choices: tuple = field(default_factory=tuple)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["choices"] = list(self.choices)
        return d


def resolve_inputs(schema: list[Input], values: dict | None) -> dict:
    """Defaults overlaid with `values`, each checked against its Input.
    ValueError (naming the key) on an unknown key, a wrong type or a value
    outside [min, max] — never clamped: a tester that silently moves a
    parameter reports a run nobody asked for."""
    values = dict(values or {})
    by_key = {i.key: i for i in schema}
    unknown = sorted(set(values) - set(by_key))
    if unknown:
        raise ValueError(f"unknown input(s): {', '.join(unknown)}")
    out: dict = {}
    for i in schema:
        v = values.get(i.key, i.default)
        if i.type == "bool":
            if not isinstance(v, bool):
                raise ValueError(f"{i.key}: expected true/false")
        elif i.type == "choice":
            if v not in i.choices:
                raise ValueError(f"{i.key}: one of {', '.join(map(str, i.choices))}")
        elif i.type in ("int", "float"):
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise ValueError(f"{i.key}: expected a number")
            if i.type == "int":
                if float(v) != int(v):
                    raise ValueError(f"{i.key}: expected a whole number")
                v = int(v)
            else:
                v = float(v)
            if v != v or (i.min is not None and v < i.min) or (i.max is not None and v > i.max):
                raise ValueError(f"{i.key}: must be within [{i.min}, {i.max}]")
        else:
            raise ValueError(f"{i.key}: unknown input type {i.type!r}")
        out[i.key] = v
    return out


class Strategy:
    id: str = ""
    name: str = ""
    root: str = ""
    session_window: tuple[str, str] = ("09:25", "16:00")   # ET [start, end)
    bar_minutes: int = 0                  # > 0: on_bar gets bars of this size
    bar_window: tuple[str, str] | None = None   # ET span bars are built over (default: session_window)
    placement_ms: int = 85                # measured order-placement latency (research)

    def __init__(self, params: dict | None = None):
        self.p = resolve_inputs(self.inputs(), params)

    @classmethod
    def inputs(cls) -> list[Input]:
        return []

    @classmethod
    def describe(cls) -> dict:
        return {"id": cls.id, "name": cls.name, "root": cls.root,
                "session_window": list(cls.session_window),
                "bar_minutes": cls.bar_minutes,
                "inputs": [i.to_dict() for i in cls.inputs()]}

    def times(self) -> list[str]:
        return []

    def trades_on(self, d: dt.date) -> bool:
        """False = the session is not even loaded (e.g. not an event day)."""
        return True

    def needs_daily(self) -> bool:
        """True = ctx.daily must carry the completed daily bars before today."""
        return False

    def on_session(self, ctx) -> None:
        pass

    def on_time(self, ctx, et_time: str) -> None:
        pass

    def on_bar(self, ctx, bar) -> None:
        pass
```

`homebase/backtest/engine.py`:

```python
"""The Strategy Tester's tick engine: one strict-order pass over a session's prints.

House fill law (research/nq_930_straddle_ticks.py L22-31, generalised):
  * STOP orders (stop entries and stop-losses) are market-on-touch. A buy stop
    triggers on the first print >= its price and fills at max(price, print) + slip;
    a sell stop on the first print <= its price, at min(price, print) - slip.
    Gapping through the level costs the gap.
  * LIMIT orders (limit entries and targets) are resting limits that need 1-TICK
    PENETRATION: a buy limit fills only on a print <= price - tick, a sell limit
    only on a print >= price + tick, AT the limit price, no slip.
  * MARKET orders fill at the first print at/after they go live, +/- slip.
  * Commission is flat per round turn per contract.
  * Prints sharing one ts_ns resolve in ROW ORDER (the tape is stable-sorted);
    orders that trigger on the same print fill oldest first.
Orders the strategy sends go live `placement_ms` after the event that sent them.
Scheduled events (session start, bar closes, on_time) run BEFORE the first print
at or after their time; ctx.cancel / ctx.flatten act at once, so a flat fills on
that first print at or after the time. A position's SL/TP ride on the entry (OSO)
and can trigger from the print AFTER the entry print.

Stdlib only (array + bisect): the desk's venv carries no numpy.
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import asdict, dataclass, field

from ..contracts import point_value, tick_size
from .tape import et_ns

ENGINE_VERSION = "tick-1"
SIDE = {"long": 1, "short": -1}
NAME = {1: "long", -1: "short"}
CHUNK = 4096                    # prefilter block for the trigger scan


def to_tick(px: float, tick: float) -> float:
    return round(round(px / tick) * tick, 6)


def first_at_or_above(px, level: float, a: int, b: int) -> int:
    """First index k in [a, b) with px[k] >= level, else b."""
    k = a
    while k < b:
        e = min(k + CHUNK, b)
        if max(px[k:e]) >= level:
            for i in range(k, e):
                if px[i] >= level:
                    return i
        k = e
    return b


def first_at_or_below(px, level: float, a: int, b: int) -> int:
    """First index k in [a, b) with px[k] <= level, else b."""
    k = a
    while k < b:
        e = min(k + CHUNK, b)
        if min(px[k:e]) <= level:
            for i in range(k, e):
                if px[i] <= level:
                    return i
        k = e
    return b


@dataclass
class Costs:
    commission_rt: float = 4.00     # USD per round turn per contract
    slippage_ticks: float = 1.0     # per side, on market and stop fills only


@dataclass(eq=False)
class Order:
    id: int
    side: int                       # +1 buy, -1 sell
    kind: str                       # "stop" | "limit" | "market"
    price: float | None             # trigger (stop) / limit price; None for market
    qty: int
    min_i: int                      # first print index this order may fill on
    role: str = "entry"             # "entry" | "sl" | "tp"
    sl: float | None = None         # entries: bracket levels, absolute prices
    tp: float | None = None
    tp_rr: float | None = None      # entries: TP re-derived from the fill at this RR
    ref: float | None = None        # entries: the price the brackets were sized from
    oco: int | None = None
    status: str = "working"         # working | filled | cancelled
    pos: "Position | None" = None   # exits: the position they close


@dataclass(eq=False)
class Position:
    side: int
    qty: int
    entry_px: float
    entry_i: int
    order_price: float | None
    sl: Order | None = None
    tp: Order | None = None


@dataclass
class Bar:
    start_ns: int
    end_ns: int
    o: float
    h: float
    l: float
    c: float
    v: int


@dataclass
class Trade:
    date: str
    side: str
    qty: int
    entry_ns: int
    entry_price: float
    exit_ns: int
    exit_price: float
    exit_reason: str                # tp | sl | time | eod
    order_price: float | None       # the entry's trigger / limit (None: market)
    sl: float | None                # the brackets as they rode the position
    tp: float | None
    gross: float
    commission: float
    net: float
    mae_pts: float
    mfe_pts: float
    mae_usd: float
    mfe_usd: float
    bars: int                       # 1-minute bars touched, entry to exit
    seconds: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SessionResult:
    date: str
    trades: list = field(default_factory=list)
    plots: dict = field(default_factory=dict)     # name -> [[t_ms, value], ...]
    hlines: list = field(default_factory=list)    # [{name, price, date}]
    skip: str | None = None                       # the strategy's reason for no trade


class Ctx:
    """What a strategy sees. Created per session by run_session."""

    def __init__(self, sim: "_Sim", qty: int, daily: list):
        self._s = sim
        self.root = sim.root
        self.date = sim.date
        self.tick = sim.tick
        self.point_value = sim.pv
        self.qty = qty
        self.daily = daily
        self.move_brackets_to_fill = False

    @property
    def now_ns(self) -> int:
        return self._s.now

    @property
    def last_price(self) -> float | None:
        """The last print strictly before the current event time (in the window)."""
        s = self._s
        return s.px[s.i - 1] if s.i > s.lo else None

    @property
    def flat(self) -> bool:
        return not self._s.positions

    def _entry(self, kind, side, price, qty, sl, tp, tp_rr, ref) -> Order:
        if side not in SIDE:
            raise ValueError(f"side must be 'long' or 'short', not {side!r}")
        return self._s.new_order(SIDE[side], kind, price, int(qty or self.qty),
                                 sl=sl, tp=tp, tp_rr=tp_rr, ref=ref)

    def stop_entry(self, side: str, price: float, qty: int | None = None, sl=None, tp=None,
                   tp_rr=None) -> Order:
        return self._entry("stop", side, price, qty, sl, tp, tp_rr, price)

    def limit_entry(self, side: str, price: float, qty: int | None = None, sl=None, tp=None,
                    tp_rr=None) -> Order:
        return self._entry("limit", side, price, qty, sl, tp, tp_rr, price)

    def market(self, side: str, qty: int | None = None, sl=None, tp=None, tp_rr=None,
               ref: float | None = None) -> Order:
        return self._entry("market", side, None, qty, sl, tp, tp_rr, ref)

    def oco(self, *orders: Order) -> None:
        g = orders[0].id
        for o in orders:
            o.oco = g

    def cancel(self, order: Order) -> None:
        self._s.cancel(order)

    def flatten(self, reason: str = "time") -> None:
        self._s.flatten(reason)

    def plot(self, name: str, t_ns: int, value: float) -> None:
        self._s.res.plots.setdefault(name, []).append([t_ns // 1_000_000, value])

    def hline(self, name: str, price: float) -> None:
        self._s.res.hlines.append({"name": name, "price": price, "date": self.date.isoformat()})

    def skip(self, reason: str) -> None:
        self._s.res.skip = reason


class _Sim:
    def __init__(self, root, d, ts, px, lo, hi, costs: Costs, placement_ms: int):
        self.root, self.date = root, d
        self.ts, self.px, self.lo, self.hi = ts, px, lo, hi
        self.tick = tick_size(root)
        self.pv = point_value(root) or 0.0
        self.slip = costs.slippage_ticks * self.tick
        self.comm = costs.commission_rt
        self.place_ns = placement_ms * 1_000_000
        self.i = lo                   # next print to process
        self.now = 0
        self.orders: list[Order] = []  # working, in creation order
        self.positions: list[Position] = []
        self.res = SessionResult(d.isoformat())
        self._ids = 0
        self._ctx: Ctx | None = None   # set by run_session

    # ---- orders
    def new_order(self, side, kind, price, qty, **kw) -> Order:
        self._ids += 1
        o = Order(self._ids, side, kind, price, qty,
                  bisect_left(self.ts, self.now + self.place_ns, self.i, self.hi), **kw)
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
            return (first_at_or_above(self.px, o.price, a, b) if o.side > 0
                    else first_at_or_below(self.px, o.price, a, b))
        return (first_at_or_below(self.px, o.price - self.tick, a, b) if o.side > 0
                else first_at_or_above(self.px, o.price + self.tick, a, b))

    def _fill_price(self, o: Order, p: float) -> float:
        if o.kind == "limit":
            return o.price
        if o.kind == "stop":
            return max(o.price, p) + self.slip if o.side > 0 else min(o.price, p) - self.slip
        return p + o.side * self.slip

    def advance(self, j: int) -> None:
        """Process prints [i, j): fill whatever triggers, earliest print first."""
        while self.orders and self.i < j:
            best_k, best = j, None
            for o in self.orders:
                a = max(self.i, o.min_i)
                if a >= best_k:
                    continue
                k = self._trigger(o, a, best_k)
                if k < best_k:
                    best_k, best = k, o
            if best is None:
                break
            self._fill(best, best_k)
            self.i = best_k           # other orders may still trigger on this same print
        self.i = max(self.i, j)

    def _fill(self, o: Order, k: int) -> None:
        fill = self._fill_price(o, self.px[k])
        o.status = "filled"
        self.orders.remove(o)
        if o.role != "entry":
            self._close(o.pos, fill, k, o.role)
            return
        if o.oco is not None:
            for x in [x for x in self.orders if x.oco == o.oco]:
                self.cancel(x)
        pos = Position(o.side, o.qty, fill, k, o.price)
        sl, tp = o.sl, o.tp
        if o.tp_rr is not None and sl is not None:
            tp = to_tick(fill + o.side * o.tp_rr * abs(fill - sl), self.tick)
        elif self._ctx.move_brackets_to_fill and o.ref is not None:
            d = fill - o.ref
            sl = None if sl is None else to_tick(sl + d, self.tick)
            tp = None if tp is None else to_tick(tp + d, self.tick)
        self._ids += 1
        if sl is not None:
            pos.sl = Order(self._ids, -o.side, "stop", sl, o.qty, k + 1, role="sl", pos=pos)
            self.orders.append(pos.sl)
        self._ids += 1
        if tp is not None:
            pos.tp = Order(self._ids, -o.side, "limit", tp, o.qty, k + 1, role="tp", pos=pos)
            self.orders.append(pos.tp)
        self.positions.append(pos)

    def _close(self, pos: Position, fill: float, k: int, reason: str) -> None:
        for x in (pos.sl, pos.tp):
            if x is not None:
                self.cancel(x)
        self.positions.remove(pos)
        seg = self.px[pos.entry_i:k + 1]
        hi, lo = max(seg), min(seg)
        s, e = pos.side, pos.entry_px
        mfe = max(0.0, (hi - e) if s > 0 else (e - lo))
        mae = max(0.0, (e - lo) if s > 0 else (hi - e))
        gross = s * (fill - e) * self.pv * pos.qty
        comm = self.comm * pos.qty
        t0, t1 = self.ts[pos.entry_i], self.ts[k]
        self.res.trades.append(Trade(
            date=self.date.isoformat(), side=NAME[s], qty=pos.qty,
            entry_ns=t0, entry_price=e, exit_ns=t1, exit_price=fill, exit_reason=reason,
            order_price=pos.order_price,
            sl=pos.sl.price if pos.sl else None, tp=pos.tp.price if pos.tp else None,
            gross=round(gross, 2), commission=round(comm, 2), net=round(gross - comm, 2),
            mae_pts=round(mae, 6), mfe_pts=round(mfe, 6),
            mae_usd=round(mae * self.pv * pos.qty, 2), mfe_usd=round(mfe * self.pv * pos.qty, 2),
            bars=int(t1 // 60_000_000_000 - t0 // 60_000_000_000 + 1),
            seconds=round((t1 - t0) / 1e9, 3)))

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
            self._close(pos, self.px[k] - pos.side * self.slip, k, reason)


def build_bars(ts, px, size, lo: int, hi: int, t0: int, t1: int, minutes: int) -> list[Bar]:
    """Time bars from prints [lo, hi), aligned to multiples of `minutes` in epoch
    time (ET-aligned: offsets are whole hours), covering [t0, t1). Empty buckets
    make no bar."""
    step = minutes * 60_000_000_000
    out = []
    b0 = t0 - t0 % step
    i0 = bisect_left(ts, b0, lo, hi)
    while b0 < t1:
        b1 = b0 + step
        i1 = bisect_left(ts, b1, i0, hi)
        if i1 > i0:
            seg = px[i0:i1]
            out.append(Bar(b0, b1, px[i0], max(seg), min(seg), px[i1 - 1], sum(size[i0:i1])))
        b0, i0 = b1, i1
    return out


def run_session(strategy, tape, costs: Costs, qty: int = 1, daily: list | None = None) -> SessionResult:
    """Replay one session's tape through one strategy instance."""
    d = tape.date
    w0, w1 = strategy.session_window
    t0, t1 = et_ns(d, w0), et_ns(d, w1)
    ts, px = tape.ts, tape.px
    lo, hi = bisect_left(ts, t0), bisect_left(ts, t1)
    sim = _Sim(tape.root, d, ts, px, lo, hi, costs, strategy.placement_ms)
    ctx = sim._ctx = Ctx(sim, qty, daily or [])
    events: list[tuple] = [(t0, 0, 0, "session", None)]
    if strategy.bar_minutes:
        b0, b1 = strategy.bar_window or strategy.session_window
        for n, b in enumerate(build_bars(ts, px, tape.size, lo, hi, et_ns(d, b0), et_ns(d, b1),
                                         strategy.bar_minutes)):
            events.append((b.end_ns, 1, n, "bar", b))
    for n, t in enumerate(strategy.times()):
        events.append((et_ns(d, t), 2, n, "time", t))
    events.sort(key=lambda e: e[:3])
    for t, _, _, kind, arg in events:
        if t >= t1:
            break
        sim.advance(bisect_left(ts, t, sim.i, hi))
        sim.now = t
        if kind == "session":
            strategy.on_session(ctx)
        elif kind == "bar":
            strategy.on_bar(ctx, arg)
        else:
            strategy.on_time(ctx, arg)
    sim.advance(hi)
    sim.i = hi
    sim.flatten("eod")
    return sim.res
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/test_strategy_contract.py tests/test_backtest_engine.py` → Expected: 20 passed.
Run: `.venv/bin/python -m pytest -q` → Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add homebase/strategies/__init__.py homebase/strategies/base.py homebase/backtest/engine.py tests/test_strategy_contract.py tests/test_backtest_engine.py
git commit -m "feat(tester): the strategy contract and the house-law tick engine — stop entries pay the gap, targets need 1-tick penetration, row-order ties" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: The four v1 strategies, pinned to the desk

**Files:**
- Create: `homebase/strategies/straddle.py`, `nq930.py`, `ym930.py`, `gc_nfpcpi.py`, `nq10am.py`, `homebase/strategies/data/gc_0830_redfolder_days_2021_2026.csv` (copied)
- Modify: `homebase/strategies/__init__.py` (replace with the registry version)
- Test: `tests/test_strategies.py`

**Interfaces:**
- Consumes: `Strategy`, `Input` (Task 2); `run_session`, `Costs`, `to_tick` (Task 2); `Tape`, `et_ns` (Task 1); desk (read-only): `homebase.config.load`, `homebase.engine.Engine._legs`, `homebase.gate.trend_gate/THRESHOLD`, `homebase.rules.RULES`, `homebase.feed.Bar`, `homebase.timer.MIN_GATE_BARS/GATE_BARS`.
- Produces:
  - `straddle.desk_cfg(name) -> StrategyCfg`, `Leg(side, trigger, sl, tp)`, `OpenStraddle` (`fire`, `cancel_et`, `flat_et`, `legs(anchor) -> [Leg long, Leg short]`), `DeskStraddle` (`desk_key`, `max_pts`), `MIN_GATE_BARS = 110`, `GATE_BARS = 250`.
  - `NQ930` (`id "nq930"`, root NQ), `YM930` (`"ym930"`, YM), `NQ10am` (`"nq10am"`, NQ, `bar_minutes 1`, `bar_window ("09:30","10:00")`), `GCNfpCpi` (`"gc_nfpcpi"`, GC, window `("08:20","09:56")`, input `events ∈ {"NFP+CPI","NFP","CPI"}`), `gc_nfpcpi.calendar() -> {date: frozenset(tags)}`.
  - `homebase.strategies.REGISTRY: dict[str, type[Strategy]]`, `get(id)` (ValueError "unknown strategy"), `catalog() -> list[describe() dicts]`.
  - Input keys for the desk straddles: `offset_pts, sl_pts, tp_pts, adx_gate, adx_min`.

- [ ] **Step 1: Copy the event calendar** (read-only source):

```bash
mkdir -p homebase/strategies/data
cp "/Users/ramoscapital/ONYX TRADING/research/data/gc_0830_redfolder_days_2021_2026.csv" homebase/strategies/data/
head -3 homebase/strategies/data/gc_0830_redfolder_days_2021_2026.csv   # date,tag / 2021-01-08,NFP / 2021-01-13,CPI
```

- [ ] **Step 2: Write the failing tests** — `tests/test_strategies.py`:

```python
"""Strategy contract + parity with the desk: defaults = the desk's geometry, legs = engine._legs."""
from __future__ import annotations

import datetime as dt
import json
from array import array
from pathlib import Path

import pytest

from homebase import config as desk_config
from homebase import timer
from homebase.backtest.engine import Costs, run_session, to_tick
from homebase.backtest.tape import Tape, et_ns
from homebase.engine import Engine
from homebase.gate import trend_gate
from homebase.strategies import REGISTRY, catalog, get
from homebase.strategies.gc_nfpcpi import GCNfpCpi, calendar
from homebase.strategies.nq10am import NQ10am
from homebase.strategies.nq930 import NQ930
from homebase.strategies.straddle import GATE_BARS, MIN_GATE_BARS
from homebase.strategies.ym930 import YM930

GATE_FIX = json.loads((Path(__file__).parent / "fixture_gate_nq2024.json").read_text())


@pytest.fixture(autouse=True)
def desk_file(monkeypatch, tmp_path):
    """Every test reads the desk config from a temp path (absent = frozen defaults)."""
    p = tmp_path / "config.json"
    monkeypatch.setattr(desk_config, "config_path", lambda: p)
    return p


def test_registry_has_the_four_v1_strategies_with_schemas():
    assert set(REGISTRY) == {"nq930", "ym930", "nq10am", "gc_nfpcpi"}
    cat = {c["id"]: c for c in catalog()}
    assert cat["nq930"]["root"] == "NQ" and cat["gc_nfpcpi"]["root"] == "GC"
    assert {i["key"] for i in cat["nq930"]["inputs"]} == {"offset_pts", "sl_pts", "tp_pts",
                                                         "adx_gate", "adx_min"}
    assert cat["nq10am"]["inputs"] == []
    with pytest.raises(ValueError, match="unknown strategy"):
        get("nope")


@pytest.mark.parametrize("cls", [NQ930, YM930])
def test_straddle_defaults_equal_the_desk_geometry(cls):
    cfg = desk_config.load().strategies[cls.desk_key]
    s = cls()
    assert (s.p["offset_pts"], s.p["sl_pts"], s.p["tp_pts"]) == (cfg.offset_pts, cfg.sl_pts, cfg.tp_pts)
    assert s.p["adx_gate"] == cfg.gated and s.p["adx_min"] == 20.0
    assert s.times() == ["09:30:00", cfg.cancel_et, cfg.flat_et] == ["09:30:00", "12:55", "15:55"]
    assert cls.root == cfg.symbol and s.placement_ms == 85


def test_defaults_follow_the_desk_config_file(desk_file):
    desk_file.write_text(json.dumps({"strategies": {"nq930": {"offset_pts": 5.0, "gated": False,
                                                              "flat_et": "15:50"}}}))
    s = NQ930()
    assert s.p["offset_pts"] == 5.0 and s.p["adx_gate"] is False and s.flat_et == "15:50"


@pytest.mark.parametrize("cls", [NQ930, YM930])
@pytest.mark.parametrize("anchor", [18250.0, 18250.25, 41000.0, 99.75])
def test_legs_equal_the_desk_engine_legs(cls, anchor):
    cfg = desk_config.load().strategies[cls.desk_key]
    s = cls()
    desk = Engine._legs(cfg, anchor + cfg.offset_pts, anchor - cfg.offset_pts, 2)
    ours = s.legs(anchor)
    assert [(("long" if r.side == "Buy" else "short"), r.price, r.stop_price, r.tp_price) for r in desk] \
        == [(g.side, g.trigger, g.sl, g.tp) for g in ours]
    assert all(r.order_type == "Stop" for r in desk)


def test_gate_constants_equal_the_desk_timer():
    assert (MIN_GATE_BARS, GATE_BARS) == (timer.MIN_GATE_BARS, timer.GATE_BARS)


def _tape(root, d, rows):
    ts, px = array("q"), array("d")
    for t, p in rows:
        hms, _, ms = t.partition(".")
        ts.append(et_ns(d, hms) + int(ms or 0) * 1_000_000)
        px.append(p)
    return Tape(root, d, "X", ts, px, array("i", [1] * len(ts)), {})


def test_trend_gate_runs_on_completed_daily_bars():
    d = dt.date(2024, 12, 31)
    tp = _tape("NQ", d, [("09:29:59", 100.0), ("09:30:01", 111.0), ("09:31", 140.0)])
    s = NQ930({"adx_gate": True})
    res = run_session(s, tp, Costs(), daily=GATE_FIX["bars"][:100])
    assert res.trades == [] and "unknown" in res.skip
    ok, adx = trend_gate(GATE_FIX["bars"][-GATE_BARS:])
    assert ok is True
    res = run_session(NQ930({"adx_gate": True}), tp, Costs(), daily=GATE_FIX["bars"])
    assert len(res.trades) == 1
    res = run_session(NQ930({"adx_gate": True, "adx_min": 30.0}), tp, Costs(), daily=GATE_FIX["bars"])
    assert res.trades == [] and res.skip.startswith("trend gate: ADX 22.42")


def test_gc_defaults_are_the_research_spec_and_it_trades_nfp_cpi_days_only():
    s = GCNfpCpi()
    assert (s.p["offset_pts"], s.p["sl_pts"], s.p["tp_pts"], s.p["events"]) == (2.0, 3.0, 6.0, "NFP+CPI")
    assert s.times() == ["08:30:00", "08:45", "09:55"] and s.session_window == ("08:20", "09:56")
    cal = calendar()
    assert cal[dt.date(2024, 1, 5)] == {"NFP"} and cal[dt.date(2024, 1, 11)] == {"CLAIMS", "CPI"}
    assert s.trades_on(dt.date(2024, 1, 5)) and s.trades_on(dt.date(2024, 1, 11))
    assert not s.trades_on(dt.date(2024, 1, 12))                    # PPI only
    assert not GCNfpCpi({"events": "NFP"}).trades_on(dt.date(2024, 1, 11))
    assert max(cal) >= dt.date(2026, 9, 1)                          # 2025-26 events for holdout runs


def test_gc_trade_through_the_engine():
    d = dt.date(2024, 1, 5)
    tp = _tape("GC", d, [("08:29:59", 2050.0), ("08:30:00.100", 2052.3), ("08:31", 2058.5)])
    t, = run_session(GCNfpCpi(), tp, Costs()).trades
    assert t.side == "long" and t.entry_price == 2052.4 and t.tp == 2058.4
    assert t.exit_reason == "tp" and t.net == round(6.0 * 100 - 4.0, 2)


def test_nq10am_uses_the_desk_rule_and_config():
    cfg = desk_config.load().strategies["nq10am"]
    s = NQ10am()
    assert s.rule.__name__ == cfg.rule == "nq_10am_continuation"
    assert s.bar_minutes == cfg.bar_minutes == 1 and s.times() == [cfg.flat_et]


def test_nq10am_trades_the_rule_signal_at_the_10am_open():
    d = dt.date(2024, 3, 5)
    rows = [(f"09:{30 + i}:10", 100.0 + i) for i in range(30)]       # 30 rising 1-min bars
    rows += [("10:00:00.090", 130.0), ("10:10", 200.0)]
    t, = run_session(NQ10am(), _tape("NQ", d, rows), Costs()).trades
    assert t.side == "long" and t.entry_price == 130.25              # market + 1 tick slip
    assert t.sl == 100.0                                            # the candle's low, absolute
    assert t.tp == to_tick(130.25 + 0.75 * (130.25 - 100.0), 0.25) == 153.0   # RR 1:0.75 from the FILL
    assert t.exit_reason == "tp"
```

- [ ] **Step 3: Run them to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_strategies.py`
Expected: FAIL — `ImportError: cannot import name 'REGISTRY' from 'homebase.strategies'`.

- [ ] **Step 4: Implement** — `homebase/strategies/straddle.py`:

```python
"""Open straddles: OCO stop entries at anchor +/- offset, brackets re-priced to the fill.

Mirrors the desk: the anchor is the last print BEFORE the fire time (the timer
fires at 09:30:00.000 on the last trade it has seen); the legs are exactly
engine._legs (buy stop at anchor + offset with SL trigger - sl / TP trigger + tp,
sell stop mirrored); after the fill both brackets move to the fill, like
engine._move_brackets; unfilled entries are cancelled at cancel_et; an open
position is flattened at flat_et.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..gate import THRESHOLD, trend_gate
from .base import Input, Strategy

MIN_GATE_BARS = 110       # = homebase.timer.MIN_GATE_BARS (pinned by a test)
GATE_BARS = 250           # = homebase.timer.GATE_BARS


def desk_cfg(name: str):
    """The desk's StrategyCfg as the desk would load it (config.json over the
    frozen defaults). Read at call time, so the tester follows the desk file."""
    from ..config import load
    return load().strategies[name]


@dataclass(frozen=True)
class Leg:
    side: str             # "long" | "short"
    trigger: float
    sl: float
    tp: float


class OpenStraddle(Strategy):
    fire = "09:30:00"
    cancel_et = "12:55"
    flat_et = "15:55"

    def legs(self, anchor: float) -> list[Leg]:
        off, sl, tp = self.p["offset_pts"], self.p["sl_pts"], self.p["tp_pts"]
        up, dn = anchor + off, anchor - off
        return [Leg("long", up, up - sl, up + tp), Leg("short", dn, dn + sl, dn - tp)]

    def times(self) -> list[str]:
        return [self.fire, self.cancel_et, self.flat_et]

    def needs_daily(self) -> bool:
        return bool(self.p.get("adx_gate"))

    def on_session(self, ctx) -> None:
        self.entries = ()

    def on_time(self, ctx, et_time: str) -> None:
        if et_time == self.fire:
            if self.p.get("adx_gate"):
                bars = ctx.daily[-GATE_BARS:]
                ok, adx = trend_gate(bars, self.p["adx_min"]) if len(bars) >= MIN_GATE_BARS \
                    else (None, None)
                if ok is None:
                    ctx.skip("trend gate unknown (under 110 daily bars)")
                    return
                if not ok:
                    ctx.skip(f"trend gate: ADX {adx} <= {self.p['adx_min']:g}")
                    return
            anchor = ctx.last_price
            if anchor is None:
                ctx.skip(f"no print before {self.fire}")
                return
            ctx.hline("anchor", anchor)
            ctx.move_brackets_to_fill = True
            self.entries = tuple(ctx.stop_entry(g.side, g.trigger, sl=g.sl, tp=g.tp)
                                 for g in self.legs(anchor))
            ctx.oco(*self.entries)
        elif et_time == self.cancel_et:
            for o in self.entries:
                ctx.cancel(o)
        elif et_time == self.flat_et:
            ctx.flatten("time")


class DeskStraddle(OpenStraddle):
    """A straddle the desk runs: defaults, cancel and flat come from its config."""
    desk_key = ""
    max_pts = 500.0

    def __init__(self, params: dict | None = None):
        cfg = desk_cfg(self.desk_key)
        self.cancel_et, self.flat_et = cfg.cancel_et, cfg.flat_et
        super().__init__(params)

    @classmethod
    def inputs(cls) -> list[Input]:
        c = desk_cfg(cls.desk_key)
        m = cls.max_pts
        return [
            Input("offset_pts", "Entry offset (pts)", "float", c.offset_pts, 0.0, m, 0.25),
            Input("sl_pts", "Stop loss (pts)", "float", c.sl_pts, 0.25, m, 0.25),
            Input("tp_pts", "Take profit (pts)", "float", c.tp_pts, 0.25, m, 0.25),
            Input("adx_gate", "ADX(14) trend gate", "bool", bool(c.gated)),
            Input("adx_min", "ADX threshold", "float", THRESHOLD, 0.0, 100.0, 0.5),
        ]
```

`homebase/strategies/nq930.py`:

```python
"""NQ 9:30 straddle — the desk's `nq930`."""
from __future__ import annotations

from .straddle import DeskStraddle


class NQ930(DeskStraddle):
    id = "nq930"
    name = "NQ 9:30 Straddle"
    root = "NQ"
    desk_key = "nq930"
    session_window = ("09:25", "16:00")
```

`homebase/strategies/ym930.py`:

```python
"""YM 9:30 straddle — the desk's `ym930`."""
from __future__ import annotations

from .straddle import DeskStraddle


class YM930(DeskStraddle):
    id = "ym930"
    name = "YM 9:30 Straddle"
    root = "YM"
    desk_key = "ym930"
    session_window = ("09:25", "16:00")
    max_pts = 2000.0
```

`homebase/strategies/gc_nfpcpi.py`:

```python
"""GC 08:30 NFP + CPI straddle (research/gc_0830_redfolder_straddle_ticks.py).

Not on the desk: its defaults are the research spec — off 2 / SL 3 / TP 6,
anchor = last print before 08:30:00.000 ET, live 85 ms later, unfilled
cancelled 08:45, open position flat 09:55 — and it trades only on the event
days of data/gc_0830_redfolder_days_2021_2026.csv (ForexFactory USD high-impact
08:30 events, scraped 2026-09-25; a day's tag may join several, e.g. CLAIMS+CPI).
"""
from __future__ import annotations

import csv
import datetime as dt
from functools import lru_cache
from pathlib import Path

from .base import Input
from .straddle import OpenStraddle

CALENDAR = Path(__file__).resolve().parent / "data" / "gc_0830_redfolder_days_2021_2026.csv"
EVENTS = {"NFP+CPI": {"NFP", "CPI"}, "NFP": {"NFP"}, "CPI": {"CPI"}}


@lru_cache(maxsize=1)
def calendar() -> dict[dt.date, frozenset]:
    with open(CALENDAR, newline="") as fh:
        return {dt.date.fromisoformat(r["date"]): frozenset(r["tag"].split("+"))
                for r in csv.DictReader(fh)}


class GCNfpCpi(OpenStraddle):
    id = "gc_nfpcpi"
    name = "GC 8:30 NFP + CPI Straddle"
    root = "GC"
    session_window = ("08:20", "09:56")
    fire, cancel_et, flat_et = "08:30:00", "08:45", "09:55"

    @classmethod
    def inputs(cls) -> list[Input]:
        return [
            Input("offset_pts", "Entry offset (pts)", "float", 2.0, 0.0, 100.0, 0.1),
            Input("sl_pts", "Stop loss (pts)", "float", 3.0, 0.1, 100.0, 0.1),
            Input("tp_pts", "Take profit (pts)", "float", 6.0, 0.1, 200.0, 0.1),
            Input("events", "Events", "choice", "NFP+CPI", choices=tuple(EVENTS)),
        ]

    def trades_on(self, d: dt.date) -> bool:
        return bool(calendar().get(d, frozenset()) & EVENTS[self.p["events"]])
```

`homebase/strategies/nq10am.py`:

```python
"""NQ 10:00 continuation — the desk's `nq10am`, through the desk's own rule.

The signal is homebase.rules.nq_10am_continuation itself (one definition): it
reads the 1-minute bars of 09:30-10:00 and, on the 09:59 bar's close, returns a
market entry with an absolute stop and a target re-derived from the fill at
RR 1:0.75. The rule has no tunable inputs, so neither does this strategy.
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

from ..feed import Bar as FeedBar
from ..rules import RULES
from .base import Strategy
from .straddle import desk_cfg

UTC = dt.timezone.utc
ET = ZoneInfo("America/New_York")


class NQ10am(Strategy):
    id = "nq10am"
    name = "NQ 10:00 Continuation"
    root = "NQ"
    desk_key = "nq10am"
    session_window = ("09:25", "16:00")
    bar_minutes = 1
    bar_window = ("09:30", "10:00")

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self.cfg = desk_cfg(self.desk_key)
        self.rule = RULES[self.cfg.rule]

    def times(self) -> list[str]:
        return [self.cfg.flat_et]

    def on_session(self, ctx) -> None:
        self.bars: list[FeedBar] = []

    def on_bar(self, ctx, bar) -> None:
        start = dt.datetime.fromtimestamp(bar.start_ns // 1_000_000_000, UTC)
        self.bars.append(FeedBar(start, bar.o, bar.h, bar.l, bar.c, bar.v, self.root, self.bar_minutes))
        sig = self.rule(self.bars, dt.datetime.fromtimestamp(bar.end_ns // 1_000_000_000, ET), self.cfg)
        if sig is None:
            return
        side = "long" if sig.side == "Buy" else "short"
        ctx.market(side, sl=sig.sl_px, tp=sig.tp_px, tp_rr=sig.tp_rr, ref=sig.ref_px)
        ctx.hline("stop", sig.sl_px)

    def on_time(self, ctx, et_time: str) -> None:
        if et_time == self.cfg.flat_et:
            ctx.flatten("time")
```

`homebase/strategies/__init__.py` (replace the whole file):

```python
"""Strategies shared by the Strategy Tester and (later) the desk. See base.py."""
from __future__ import annotations

from .base import Input, Strategy, resolve_inputs
from .gc_nfpcpi import GCNfpCpi
from .nq10am import NQ10am
from .nq930 import NQ930
from .ym930 import YM930

REGISTRY: dict[str, type[Strategy]] = {c.id: c for c in (NQ930, YM930, NQ10am, GCNfpCpi)}


def get(strategy_id: str) -> type[Strategy]:
    try:
        return REGISTRY[strategy_id]
    except KeyError:
        raise ValueError(f"unknown strategy {strategy_id!r}") from None


def catalog() -> list[dict]:
    return [c.describe() for c in REGISTRY.values()]


__all__ = ["Input", "Strategy", "resolve_inputs", "REGISTRY", "get", "catalog"]
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/test_strategies.py tests/test_strategy_contract.py tests/test_backtest_engine.py` → Expected: 38 passed.
Run: `.venv/bin/python -m pytest -q` → Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add homebase/strategies tests/test_strategies.py
git commit -m "feat(tester): nq930, ym930, nq10am and gc_nfpcpi strategies — defaults read from the desk config, legs equal engine._legs, the desk's own 10am rule" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Golden parity with the research replay

The tester's `nq930` must reproduce `research/nq_930_straddle_ticks.py` trade by trade (side, fill price, exit reason and price, net $) at the same slippage and commission. The expectations are produced ONCE by the research script's own functions and committed small (~8 KB).

**Files:**
- Create: `tests/fixtures/make_nq930_golden.py`, `tests/fixtures/nq930_golden.json` (generated), `tests/test_backtest_golden.py`

**Interfaces:**
- Consumes: `NQ930` (Task 3), `run_session`, `Costs` (Task 2), `TapeStore`, `missing_hours` (Task 1); read-only: `/Users/ramoscapital/ONYX TRADING/research/nq_930_straddle_ticks.py` (`front_month`, `load_day`, `replay_day`, `sessions`, `ns`, constants) and `~/futures_ticks/NQ/2022-2024`.
- Produces: `tests/fixtures/nq930_golden.json` = `{"source", "point_value": 20.0, "commission": 4.0, "placement_ms": 85, "cases": [{date, contract, offset, sl, tp, slip_ticks, anchor, filled, side?, entry_ns?, entry_price?, why?, exit_price?, net?, exit_price_spec?, net_spec?, category}]}`.

The 21 pinned sessions (chosen by `--select` while planning: a fixed-seed shuffle of 2022–2024, first matches per category, sessions with any empty clock hour in 09:25–16:00 or the research's same-`ts_ns` exit quirk excluded):

| category | n | geometry (off/SL/TP, slip) | what it proves |
|---|---|---|---|
| `tp_long`, `tp_short` | 2 + 2 | 10/5/15, 1 tick | clean fill, target by penetration |
| `sl_long`, `sl_short` | 2 + 2 | 10/5/15, 1 tick | touch stop + slip |
| `gap_entry` | 3 | 10/5/15, 1 tick | a stop entry paying the gap |
| `sl_gap` | 2 | 10/5/15, 1 tick | a stop-loss paying the gap |
| `no_fill` | 3 | 150/5/15, 1 tick | nothing fills before 12:55 |
| `time_exit` | 3 | 10/150/300, 1 tick | flat at 15:55 (Ruling R3) |
| `slip0_tp`, `slip0_sl` | 1 + 1 | 10/5/15, 0 ticks | the slippage input |

- [ ] **Step 1: Write the generator** — `tests/fixtures/make_nq930_golden.py`:

```python
"""Regenerate tests/fixtures/nq930_golden.json from the RESEARCH replay — read-only.

    "/Users/ramoscapital/ONYX TRADING/.venv/bin/python" tests/fixtures/make_nq930_golden.py
    "/Users/ramoscapital/ONYX TRADING/.venv/bin/python" tests/fixtures/make_nq930_golden.py --select

Runs research/nq_930_straddle_ticks.py's OWN functions (front_month, load_day,
replay_day) on the pinned CASES and writes what the research says, trade by trade.
It only reads ~/futures_ticks (2021-2024, the research window); it writes one
file, tests/fixtures/nq930_golden.json. --select re-scans 2022-2024 and prints a
fresh CASES list to paste below (pinned so the fixture never drifts).

Two research quirks the tester deliberately does not copy (spec rulings):
  * a time exit: research fills at the last print <= 15:55:00 ET; the tester at
    the FIRST print >= 15:55:00 ET (spec: "flats happen at the first print at or
    after the time"). Both prices are recorded; the test checks exit_price_spec.
  * research lets rows that share the entry's ts_ns but sit BEFORE the entry row
    trigger the exit; the tester is strict row order. --select skips such days.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import random
import sys
from pathlib import Path

import numpy as np

ONYX = Path("/Users/ramoscapital/ONYX TRADING")
sys.path.insert(0, str(ONYX / "research"))
import nq_930_straddle_ticks as R  # noqa: E402

OUT = Path(__file__).resolve().parent / "nq930_golden.json"
BASE = (10.0, 5.0, 15.0)            # offset / SL / TP — the research spec
WIDE = (10.0, 150.0, 300.0)         # forces time exits
NOFILL = (150.0, 5.0, 15.0)         # NQ always travels 10 pts by 12:55; 150 it rarely does
# (date, offset, sl, tp, slip_ticks, category) — pinned by --select, 2026-09-26
CASES: list[tuple] = [
    ("2023-01-30", 10.0, 5.0, 15.0, 1.0, "tp_long"),
    ("2023-12-13", 10.0, 5.0, 15.0, 1.0, "tp_long"),
    ("2022-10-07", 10.0, 5.0, 15.0, 1.0, "tp_short"),
    ("2024-09-16", 10.0, 5.0, 15.0, 1.0, "tp_short"),
    ("2024-08-07", 10.0, 5.0, 15.0, 1.0, "sl_long"),
    ("2024-09-25", 10.0, 5.0, 15.0, 1.0, "sl_long"),
    ("2024-03-21", 10.0, 5.0, 15.0, 1.0, "sl_short"),
    ("2024-12-17", 10.0, 5.0, 15.0, 1.0, "sl_short"),
    ("2022-07-05", 10.0, 5.0, 15.0, 1.0, "gap_entry"),
    ("2024-03-22", 10.0, 5.0, 15.0, 1.0, "gap_entry"),
    ("2023-03-13", 10.0, 5.0, 15.0, 1.0, "gap_entry"),
    ("2023-10-04", 10.0, 5.0, 15.0, 1.0, "sl_gap"),
    ("2022-10-24", 10.0, 5.0, 15.0, 1.0, "sl_gap"),
    ("2024-04-12", 150.0, 5.0, 15.0, 1.0, "no_fill"),
    ("2024-06-18", 150.0, 5.0, 15.0, 1.0, "no_fill"),
    ("2023-03-08", 150.0, 5.0, 15.0, 1.0, "no_fill"),
    ("2022-08-29", 10.0, 150.0, 300.0, 1.0, "time_exit"),
    ("2023-05-31", 10.0, 150.0, 300.0, 1.0, "time_exit"),
    ("2024-02-01", 10.0, 150.0, 300.0, 1.0, "time_exit"),
    ("2023-10-06", 10.0, 5.0, 15.0, 0.0, "slip0_tp"),
    ("2022-02-08", 10.0, 5.0, 15.0, 0.0, "slip0_sl"),
]


def replay(d: dt.date, off: float, sl: float, tp: float, slip_t: float) -> dict | None:
    path = R.front_month(R.ARCHIVE / str(d.year), d)
    if path is None:
        return None
    tape = R.load_day(path, R.ns(d, 9, 25), R.ns(d, 16, 0))
    if tape is None:
        return None
    slip = slip_t * R.TICK
    r = R.replay_day(tape, d, slip, sl, tp, off)
    if r is None:
        return None
    t_fire, t_flat = R.ns(d, *R.FIRE), R.ns(d, *R.FLAT)
    out = {"date": d.isoformat(), "contract": path.name.split("_")[1].split(".")[0],
           "offset": off, "sl": sl, "tp": tp, "slip_ticks": slip_t,
           "anchor": r["anchor"], "filled": r["filled"]}
    if not r["filled"]:
        return {**out, "_tape": tape}
    side = 1 if r["side"] == "long" else -1
    entry_ns = t_fire + round(r["entry_ms"] * 1e6)
    after = tape[tape[:, 0] >= t_flat]
    spec_px = float(after[0][1]) - side * slip if len(after) else None
    out.update({"side": r["side"], "entry_ns": int(entry_ns), "entry_price": r["entry_price"],
                "why": r["why"], "exit_price": r["exit_price"], "net": r["net"],
                "exit_price_spec": spec_px if r["why"] == "FLAT" else r["exit_price"],
                "net_spec": (round(side * (spec_px - r["entry_price"]) * R.PV - R.COMM, 2)
                             if r["why"] == "FLAT" else r["net"]),
                "_tape": tape})
    return out


def clean(rec: dict, d: dt.date) -> bool:
    """Every clock hour of 09:25-16:00 has prints, and no same-ts-before-entry exit."""
    tape = rec["_tape"]
    ts = tape[:, 0]
    cuts = [R.ns(d, 9, 25)] + [R.ns(d, h, 0) for h in range(10, 17)]
    if any(((ts >= a) & (ts < b)).sum() == 0 for a, b in zip(cuts, cuts[1:])):
        return False
    if not rec["filled"]:
        return True
    side = 1 if rec["side"] == "long" else -1
    sl = rec["entry_price"] - side * rec["sl"]
    tp = rec["entry_price"] + side * rec["tp"]
    same = tape[ts == rec["entry_ns"]]
    first = int(np.flatnonzero(ts == rec["entry_ns"])[0])
    entry_row = first + int(np.flatnonzero(
        (same[:, 1] >= rec["anchor"] + rec["offset"]) | (same[:, 1] <= rec["anchor"] - rec["offset"]))[0])
    for px in tape[first:entry_row, 1]:
        if (side == 1 and (px <= sl or px >= tp + R.TICK)) or (side == -1 and (px >= sl or px <= tp - R.TICK)):
            return False
    return True


def category(rec: dict) -> str | None:
    if not rec["filled"]:
        return "no_fill"
    side = 1 if rec["side"] == "long" else -1
    slip = rec["slip_ticks"] * R.TICK
    trig = rec["anchor"] + side * rec["offset"]
    if rec["why"] == "FLAT":
        return "time_exit"
    if abs(rec["entry_price"] - (trig + side * slip)) > 1e-9:
        return "gap_entry"
    sl_lvl = rec["entry_price"] - side * rec["sl"]
    if rec["why"] == "SL" and abs(rec["exit_price"] - (sl_lvl - side * slip)) > 1e-9:
        return "sl_gap"
    return f"{rec['why'].lower()}_{rec['side']}"


WANT = {"tp_long": 2, "tp_short": 2, "sl_long": 2, "sl_short": 2, "gap_entry": 3,
        "sl_gap": 2, "no_fill": 3}


def select() -> None:
    days = sorted(set(R.sessions(dt.date(2022, 1, 1), dt.date(2024, 12, 31))))
    random.Random(20260926).shuffle(days)
    got: dict[str, list] = {k: [] for k in [*WANT, "time_exit", "slip0_tp", "slip0_sl"]}
    for d in days:
        if all(len(got[k]) >= WANT.get(k, 3 if k == "time_exit" else 1) for k in got):
            break
        rec = replay(d, *BASE, 1.0)
        if rec is None or not clean(rec, d):
            continue
        c = category(rec)
        if c in WANT and len(got[c]) < WANT[c]:
            got[c].append((d.isoformat(), *BASE, 1.0, c))
            continue
        if len(got["no_fill"]) < WANT["no_fill"]:
            n = replay(d, *NOFILL, 1.0)
            if n and not n["filled"] and clean(n, d):
                got["no_fill"].append((d.isoformat(), *NOFILL, 1.0, "no_fill"))
                continue
        if len(got["time_exit"]) < 3:
            w = replay(d, *WIDE, 1.0)
            if w and w["filled"] and w["why"] == "FLAT" and clean(w, d):
                got["time_exit"].append((d.isoformat(), *WIDE, 1.0, "time_exit"))
                continue
        for k, why in (("slip0_tp", "TP"), ("slip0_sl", "SL")):
            if not got[k]:
                z = replay(d, *BASE, 0.0)
                if z and z["filled"] and z["why"] == why and clean(z, d):
                    got[k].append((d.isoformat(), *BASE, 0.0, k))
                    break
    for k, v in got.items():
        for c in v:
            print(f"    {c!r},")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--select", action="store_true")
    if ap.parse_args().select:
        select()
        return
    assert CASES, "run --select first and paste its output into CASES"
    rows = []
    for d, off, sl, tp, slip_t, cat in CASES:
        rec = replay(dt.date.fromisoformat(d), off, sl, tp, slip_t)
        assert rec is not None, d
        rec.pop("_tape")
        rows.append({**rec, "category": cat})
    OUT.write_text(json.dumps({"source": "research/nq_930_straddle_ticks.py replay_day",
                               "point_value": R.PV, "commission": R.COMM,
                               "placement_ms": R.PLACEMENT_MS, "cases": rows}, indent=1) + "\n")
    print(f"{len(rows)} cases -> {OUT}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Generate the fixture (read-only use of the archive)**

Run: `"/Users/ramoscapital/ONYX TRADING/.venv/bin/python" tests/fixtures/make_nq930_golden.py`
Expected: `21 cases -> …/tests/fixtures/nq930_golden.json`. Spot-check the first case: `2023-01-30`, `NQH3`, anchor `12083.5`, long, entry `12093.75`, `TP` at `12108.75`, net `296.0`.

How to regenerate later: the same command recomputes the pinned `CASES` (deterministic). To pick fresh sessions: run it with `--select`, paste the printed tuples into `CASES`, run it again, and commit both files together.

- [ ] **Step 3: Write the parity test** — `tests/test_backtest_golden.py`:

```python
"""Golden parity: the tester's nq930 reproduces the research replay trade by trade.

The expectations come from research/nq_930_straddle_ticks.py's own replay_day on
21 pinned 2022-2024 sessions (tests/fixtures/make_nq930_golden.py regenerates
them). This test reads the real archive, READ-ONLY; the tape cache goes to
pytest's tmp dir. Skipped on a machine without ~/futures_ticks/NQ.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest

from homebase.backtest.engine import Costs, run_session
from homebase.backtest.tape import TapeStore, missing_hours
from homebase.strategies.nq930 import NQ930

ARCHIVE = Path.home() / "futures_ticks"
FIX = json.loads((Path(__file__).parent / "fixtures" / "nq930_golden.json").read_text())
REASON = {"TP": "tp", "SL": "sl", "FLAT": "time"}

pytestmark = pytest.mark.skipif(not (ARCHIVE / "NQ").is_dir(), reason="needs ~/futures_ticks/NQ")


@pytest.fixture(scope="module")
def store(tmp_path_factory):
    return TapeStore(ARCHIVE, tmp_path_factory.mktemp("tape"))


@pytest.fixture(autouse=True)
def frozen_desk_defaults(monkeypatch, tmp_path):
    # cancel 12:55 / flat 15:55 come from the desk config: pin the frozen defaults
    monkeypatch.setattr("homebase.config.config_path", lambda: tmp_path / "absent.json")


def test_fixture_covers_every_fill_case():
    cats = {c["category"] for c in FIX["cases"]}
    assert {"tp_long", "tp_short", "sl_long", "sl_short", "gap_entry", "sl_gap",
            "no_fill", "time_exit", "slip0_tp", "slip0_sl"} <= cats
    assert len(FIX["cases"]) >= 20
    assert FIX["commission"] == 4.0 and FIX["placement_ms"] == NQ930.placement_ms == 85


@pytest.mark.parametrize("case", FIX["cases"], ids=lambda c: f"{c['date']}-{c['category']}")
def test_engine_reproduces_research_trade_by_trade(store, case):
    d = dt.date.fromisoformat(case["date"])
    tape = store.load("NQ", d)
    assert tape is not None and tape.contract == case["contract"]
    assert missing_hours(tape.ts, d, NQ930.session_window) == []
    strat = NQ930({"offset_pts": case["offset"], "sl_pts": case["sl"], "tp_pts": case["tp"],
                   "adx_gate": False})
    res = run_session(strat, tape, Costs(FIX["commission"], case["slip_ticks"]), qty=1)
    assert [h["price"] for h in res.hlines if h["name"] == "anchor"] == [case["anchor"]]
    if not case["filled"]:
        assert res.trades == []
        return
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t.side == case["side"]
    assert t.entry_price == case["entry_price"]
    assert abs(t.entry_ns - case["entry_ns"]) <= 1_000      # research stores ts as float64
    assert t.exit_reason == REASON[case["why"]]
    assert t.exit_price == case["exit_price_spec"]
    assert t.net == pytest.approx(case["net_spec"], abs=0.005)
```

- [ ] **Step 4: Run it to verify it passes**

Run: `.venv/bin/python -m pytest -q tests/test_backtest_golden.py` → Expected: 22 passed in ~5 s (it builds 21 session caches in `tmp_path`). Any mismatch is an engine bug — fix `engine.py`/`tape.py` (with a new unit test in `tests/test_backtest_engine.py` for the case), never the fixture.

- [ ] **Step 5: Commit**

```bash
git add tests/fixtures/make_nq930_golden.py tests/fixtures/nq930_golden.json tests/test_backtest_golden.py
git commit -m "test(tester): golden parity — nq930 reproduces the research tick replay trade by trade on 21 pinned 2022-2024 sessions" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Vendored metrics and the TradingView-parity report

**Files:**
- Create (generated by Step 1): `homebase/backtest/stats/__init__.py`, `homebase/backtest/stats/ledger.py`, `homebase/backtest/stats/stats.py`, `tests/test_backtest_stats_vendored.py`
- Create: `homebase/backtest/report.py`
- Test: `tests/test_backtest_report.py`

**Interfaces:**
- Consumes: engine `Trade.to_dict()` rows (Task 2).
- Produces: `report.build(trades: list[dict], capital=50_000.0) -> {"capital", "summary": {"all","long","short": column}, "by_year": [...], "by_month": [...]}`; `report.equity(trades) -> {"t_ms", "equity", "drawdown"}`; `column(trades, capital)` keys: `net_profit, net_profit_pct, gross_profit, gross_loss, commission_paid, max_drawdown, max_drawdown_pct, max_runup, profit_factor, trades, wins, losses, win_rate, avg_trade, avg_win, avg_loss, rr, rr_label, largest_win, largest_loss, avg_seconds_in_trade, avg_bars_in_trade, max_consec_losses, sharpe, sortino, t_stat, expectancy, days`; period rows: `period, trades, net, win_rate, profit_factor, max_drawdown, sharpe, avg_trade`; helpers `rr_label`, `sortino`, `t_stat`, `daily_pnl`, `drawdown_pct`, `to_ledger`.

- [ ] **Step 1: Vendor the ONYX metrics (read-only `git show` of committed versions)**

`onyx/report/ledger.py` has uncommitted edits in ONYX, so vendor the committed blobs: `ledger.py` @ `338b969`, `stats.py` @ `6ceffe2`, tests @ `c98121b` (the propsim5 tests are dropped — propsim is not vendored). Run from the worktree root:

```bash
.venv/bin/python - <<'EOF'
"""One-shot: vendor onyx/report/{ledger,stats}.py + their tests into homebase."""
import re
import subprocess
from pathlib import Path

ONYX = "/Users/ramoscapital/ONYX TRADING"
ROOT = Path.cwd()
SRC = {"homebase/backtest/stats/ledger.py": ("338b969", "onyx/report/ledger.py"),
       "homebase/backtest/stats/stats.py": ("6ceffe2", "onyx/report/stats.py")}


def show(rev: str, path: str) -> str:
    return subprocess.run(["git", "-C", ONYX, "show", f"{rev}:{path}"], check=True,
                          capture_output=True, text=True).stdout


for dst, (rev, src) in SRC.items():
    body = show(rev, src)
    head = (f"# VENDORED from ONYX TRADING {src} at commit {rev} (git -C \"{ONYX}\" show {rev}:{src}).\n"
            f"# Do not edit here: re-vendor instead. Stdlib only.\n")
    (ROOT / dst).parent.mkdir(parents=True, exist_ok=True)
    (ROOT / dst).write_text(head + body)
(ROOT / "homebase/backtest/stats/__init__.py").write_text(
    '"""Vendored trade-ledger metrics (ONYX TRADING onyx/report). See each file\'s header."""\n'
    "from . import ledger, stats\n\n__all__ = [\"ledger\", \"stats\"]\n")
t = show("c98121b", "tests/test_report_stats.py")
t = t.replace("from onyx.report import propsim5\n", "")
t = t.replace("from onyx.report import", "from homebase.backtest.stats import")
parts = re.split(r"(?m)^(?=def test_|# ---)", t)
t = "".join(p for p in parts if "propsim5" not in p)
(ROOT / "tests/test_backtest_stats_vendored.py").write_text(
    "# VENDORED from ONYX TRADING tests/test_report_stats.py at commit c98121b; the propsim5\n"
    "# tests were dropped (propsim is not vendored). Re-vendor instead of editing.\n" + t)
print("vendored")
EOF
```

Expected: `vendored`. Then `.venv/bin/python -m pytest -q tests/test_backtest_stats_vendored.py` → 33 passed. Check `head -2 homebase/backtest/stats/stats.py` shows the provenance header.

- [ ] **Step 2: Write the failing report tests** — `tests/test_backtest_report.py`:

```python
"""The report on a hand-computed four-trade ledger."""
from __future__ import annotations

import math

import pytest

from homebase.backtest.report import build, equity, rr_label, sortino, t_stat


def tr(date, side, net, hms_ns, seconds=60.0, bars=2, comm=4.0):
    day = {"2024-01-02": 1704205800, "2024-01-03": 1704292200, "2024-02-05": 1707143400}[date]
    t0 = (day + hms_ns) * 1_000_000_000
    return {"date": date, "side": side, "qty": 1, "entry_ns": t0, "exit_ns": t0 + int(seconds * 1e9),
            "net": net, "gross": net + comm, "commission": comm, "mfe_usd": 100.0, "mae_usd": 50.0,
            "seconds": seconds, "bars": bars}


LEDGER = [tr("2024-01-02", "long", 296.0, 60), tr("2024-01-02", "short", -104.0, 600, seconds=120, bars=3),
          tr("2024-01-03", "long", -204.0, 60), tr("2024-02-05", "short", 196.0, 60)]


def test_all_column_hand_computed():
    a = build(LEDGER, capital=50_000.0)["summary"]["all"]
    assert a["net_profit"] == 184.0 and a["net_profit_pct"] == pytest.approx(0.368)
    assert (a["gross_profit"], a["gross_loss"], a["commission_paid"]) == (492.0, -308.0, 16.0)
    assert a["profit_factor"] == pytest.approx(492 / 308)
    assert (a["trades"], a["wins"], a["losses"], a["win_rate"]) == (4, 2, 2, 50.0)
    assert (a["avg_trade"], a["avg_win"], a["avg_loss"]) == (46.0, 246.0, -154.0)
    assert a["rr"] == pytest.approx(246 / 154) and a["rr_label"] == "1:1.60"
    assert (a["largest_win"], a["largest_loss"]) == (296.0, -204.0)
    assert a["max_drawdown"] == -308.0 and a["max_runup"] == 296.0
    assert a["max_drawdown_pct"] == pytest.approx(-308 / 50_296 * 100)
    assert a["max_consec_losses"] == 2
    assert a["avg_seconds_in_trade"] == 75.0 and a["avg_bars_in_trade"] == 2.25
    daily = [192.0, -204.0, 196.0]                       # by session date
    m = sum(daily) / 3
    sd = math.sqrt(sum((d - m) ** 2 for d in daily) / 2)
    assert a["sharpe"] == pytest.approx(m / sd * math.sqrt(252)) and a["days"] == 3
    assert a["sortino"] == pytest.approx(m / math.sqrt(204.0 ** 2 / 3) * math.sqrt(252))
    assert a["t_stat"] == pytest.approx(46.0 / (math.sqrt(170000 / 3) / 2))


def test_long_and_short_columns_split_the_ledger():
    s = build(LEDGER)["summary"]
    assert (s["long"]["trades"], s["long"]["net_profit"]) == (2, 92.0)
    assert (s["short"]["trades"], s["short"]["net_profit"]) == (2, 92.0)
    assert s["long"]["largest_loss"] == -204.0 and s["short"]["largest_win"] == 196.0


def test_year_and_month_tables():
    r = build(LEDGER)
    assert [(y["period"], y["trades"], y["net"]) for y in r["by_year"]] == [("2024", 4, 184.0)]
    assert [(m["period"], m["trades"], m["net"]) for m in r["by_month"]] == [("2024-01", 3, -12.0),
                                                                             ("2024-02", 1, 196.0)]


def test_equity_and_drawdown_series():
    e = equity(LEDGER)
    assert e["equity"] == [296.0, 192.0, -12.0, 184.0]
    assert e["drawdown"] == [0.0, -104.0, -308.0, -112.0]
    assert e["t_ms"][0] == LEDGER[0]["exit_ns"] // 1_000_000


def test_empty_and_degenerate_ledgers():
    a = build([])["summary"]["all"]
    assert a["trades"] == 0 and a["win_rate"] is None and a["profit_factor"] is None
    assert a["rr_label"] == "—" and a["sharpe"] == 0.0 and a["t_stat"] is None
    assert rr_label(999.0) == "1:∞" and rr_label(0.75) == "1:0.75"
    assert sortino([10.0, 20.0]) is None and t_stat([5.0]) is None and t_stat([3.0, 3.0]) is None
```

- [ ] **Step 3: Run them to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_backtest_report.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'homebase.backtest.report'`.

- [ ] **Step 4: Implement** — `homebase/backtest/report.py`:

```python
"""The tester's report: TradingView's performance summary (All / Long / Short) on the
vendored stats (homebase/backtest/stats), plus the desk's own numbers.

Conventions (stated once):
  * every money figure is USD, net of commission and of the slippage already in the
    fill prices; drawdowns and losses keep their negative sign;
  * Sharpe = mean / sd(sample) of DAILY P&L x sqrt(252), days = session dates that
    traded (flat days not padded) — the house convention of the vendored stats;
    Sortino = mean / sqrt(mean(min(day, 0)^2)) x sqrt(252) over the same days;
  * t-stat = the per-trade mean over its standard error (sample sd / sqrt(n));
  * RR = avg win / |avg loss|, shown as "1:X";
  * % figures are against `capital` (the run's account size, default $50,000):
    net % = net / capital, drawdown % = the worst fall from an equity peak,
    equity = capital + cumulative net.
"""
from __future__ import annotations

import math

from .stats.ledger import Trade as LedgerTrade
from .stats.stats import _sharpe, pack

CAP = 999.0


def to_ledger(trades: list[dict]) -> list[LedgerTrade]:
    return [LedgerTrade(entry_ts=t["entry_ns"] // 1_000_000_000, exit_ts=t["exit_ns"] // 1_000_000_000,
                        side=t["side"], qty=t["qty"], pnl=t["net"], runup=t["mfe_usd"],
                        drawdown=t["mae_usd"], cost=t["commission"]) for t in trades]


def rr_label(rr: float | None) -> str:
    if rr is None:
        return "—"
    return "1:∞" if rr >= CAP else f"1:{rr:.2f}"


def daily_pnl(trades: list[dict]) -> list[float]:
    by: dict[str, float] = {}
    for t in trades:
        by[t["date"]] = by.get(t["date"], 0.0) + t["net"]
    return [by[d] for d in sorted(by)]


def sortino(daily: list[float]) -> float | None:
    if len(daily) < 2:
        return None
    dd = math.sqrt(sum(min(d, 0.0) ** 2 for d in daily) / len(daily))
    if not dd:
        return None
    return sum(daily) / len(daily) / dd * math.sqrt(252.0)


def t_stat(pnls: list[float]) -> float | None:
    n = len(pnls)
    if n < 2:
        return None
    m = sum(pnls) / n
    sd = math.sqrt(sum((p - m) ** 2 for p in pnls) / (n - 1))
    return m / (sd / math.sqrt(n)) if sd else None


def drawdown_pct(trades: list[dict], capital: float) -> float:
    eq = peak = capital
    worst = 0.0
    for t in trades:
        eq += t["net"]
        peak = max(peak, eq)
        worst = min(worst, (eq - peak) / peak * 100.0 if peak > 0 else 0.0)
    return worst


def column(trades: list[dict], capital: float) -> dict:
    p = pack(to_ledger(trades))
    n = p["n_trades"]
    daily = daily_pnl(trades)
    return {
        "net_profit": p["net"], "net_profit_pct": p["net"] / capital * 100.0,
        "gross_profit": p["gross_profit"], "gross_loss": p["gross_loss"],
        "commission_paid": sum(t["commission"] for t in trades),
        "max_drawdown": p["max_drawdown"], "max_drawdown_pct": drawdown_pct(trades, capital),
        "max_runup": p["max_runup"],
        "profit_factor": p["profit_factor"] if n else None,
        "trades": n, "wins": p["n_wins"], "losses": p["n_losses"],
        "win_rate": p["win_rate"] * 100.0 if n else None,
        "avg_trade": p["expectancy"] if n else None,
        "avg_win": p["avg_win"], "avg_loss": p["avg_loss"],
        "rr": p["payoff_ratio"], "rr_label": rr_label(p["payoff_ratio"]),
        "largest_win": p["largest_win"], "largest_loss": p["largest_loss"],
        "avg_seconds_in_trade": sum(t["seconds"] for t in trades) / n if n else None,
        "avg_bars_in_trade": sum(t["bars"] for t in trades) / n if n else None,
        "max_consec_losses": p["loss_streak_max"] or 0,
        "sharpe": _sharpe(daily), "sortino": sortino(daily),
        "t_stat": t_stat([t["net"] for t in trades]),
        "expectancy": p["expectancy"] if n else None,
        "days": len(daily),
    }


def summary(trades: list[dict], capital: float) -> dict:
    return {"all": column(trades, capital),
            "long": column([t for t in trades if t["side"] == "long"], capital),
            "short": column([t for t in trades if t["side"] == "short"], capital)}


def periods(trades: list[dict], width: int) -> list[dict]:
    """width 4 = years, 7 = months (prefixes of the session date)."""
    groups: dict[str, list[dict]] = {}
    for t in trades:
        groups.setdefault(t["date"][:width], []).append(t)
    out = []
    for k in sorted(groups):
        g = groups[k]
        p = pack(to_ledger(g))
        out.append({"period": k, "trades": p["n_trades"], "net": p["net"],
                    "win_rate": p["win_rate"] * 100.0, "profit_factor": p["profit_factor"],
                    "max_drawdown": p["max_drawdown"], "sharpe": _sharpe(daily_pnl(g)),
                    "avg_trade": p["expectancy"]})
    return out


def equity(trades: list[dict]) -> dict:
    t_ms, eq, dd = [], [], []
    run = peak = 0.0
    for t in trades:
        run += t["net"]
        peak = max(peak, run)
        t_ms.append(t["exit_ns"] // 1_000_000)
        eq.append(round(run, 2))
        dd.append(round(run - peak, 2))
    return {"t_ms": t_ms, "equity": eq, "drawdown": dd}


def build(trades: list[dict], capital: float = 50_000.0) -> dict:
    trades = sorted(trades, key=lambda t: (t["exit_ns"], t["entry_ns"]))
    return {"capital": capital, "summary": summary(trades, capital),
            "by_year": periods(trades, 4), "by_month": periods(trades, 7)}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/test_backtest_report.py tests/test_backtest_stats_vendored.py` → Expected: 38 passed.
Run: `.venv/bin/python -m pytest -q` → Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add homebase/backtest/stats homebase/backtest/report.py tests/test_backtest_stats_vendored.py tests/test_backtest_report.py
git commit -m "feat(tester): vendor ONYX ledger/stats and build the report — All/Long/Short summary in dollars, Sharpe, Sortino, t-stat, RR 1:X, year/month tables" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Discipline — research window, IS months, holdout spends

**Files:**
- Create: `homebase/backtest/discipline.py`
- Test: `tests/test_backtest_discipline.py`

**Interfaces:**
- Produces: `RESEARCH_START = 2021-01-01`, `RESEARCH_END = 2024-12-31`, `HOLDOUT_START = 2025-01-01`, `IS_MONTHS = (1, 4, 7, 10)`, `DisciplineError(ValueError)`, `Range(kind, start, end)` with `.includes(d)`, `.holdout`, `.label`, `.to_dict()`; `parse_range(obj) -> Range`; `check(rng, holdout: dict | None) -> str | None` (the reason, or None inside the research data); `record_spend(path, *, strategy, inputs, rng, reason, ts=None) -> dict`; `spends(path) -> list[dict]`.

- [ ] **Step 1: Write the failing tests** — `tests/test_backtest_discipline.py`:

```python
"""The data rules: research window default, IS months, the holdout switch + spend log."""
from __future__ import annotations

import datetime as dt

import pytest

from homebase.backtest.discipline import (HOLDOUT_START, IS_MONTHS, RESEARCH_END, RESEARCH_START,
                                          DisciplineError, check, parse_range, record_spend, spends)


def test_constants_are_the_users_rules():
    assert (RESEARCH_START, RESEARCH_END) == (dt.date(2021, 1, 1), dt.date(2024, 12, 31))
    assert HOLDOUT_START == dt.date(2025, 1, 1) and IS_MONTHS == (1, 4, 7, 10)


def test_default_range_is_the_research_window():
    r = parse_range(None)
    assert (r.kind, r.start, r.end, r.holdout) == ("research", RESEARCH_START, RESEARCH_END, False)
    assert r.label == "Research window 2021–2024"
    assert parse_range({"kind": "research", "end": "2026-01-01"}).end == RESEARCH_END   # fixed bounds
    assert check(r, None) is None


def test_is_months_keeps_jan_apr_jul_oct_only():
    r = parse_range({"kind": "is_months"})
    assert (r.start, r.end) == (RESEARCH_START, RESEARCH_END)
    assert r.includes(dt.date(2022, 4, 5)) and not r.includes(dt.date(2022, 5, 5))
    assert not r.includes(dt.date(2025, 1, 6))


def test_custom_range_validation():
    r = parse_range({"kind": "custom", "start": "2023-01-01", "end": "2023-06-30"})
    assert r.includes(dt.date(2023, 5, 5)) and not r.includes(dt.date(2023, 7, 3))
    for bad in ({"kind": "custom", "start": "2023-01-01"}, {"kind": "custom", "start": "x", "end": "2023-01-02"},
                {"kind": "custom", "start": "2023-02-01", "end": "2023-01-01"}, {"kind": "all"}, "research"):
        with pytest.raises(DisciplineError):
            parse_range(bad)


def test_a_2025_range_without_the_switch_is_refused():
    r = parse_range({"kind": "custom", "start": "2024-06-01", "end": "2025-01-01"})
    assert r.holdout
    for h in (None, {}, {"reason": "  "}, {"reason": "two\nlines"}, {"reason": "x" * 201}):
        with pytest.raises(DisciplineError):
            check(r, h)
    assert check(r, {"reason": " forward check of the OOS claim "}) == "forward check of the OOS claim"


def test_the_holdout_switch_inside_the_research_window_changes_nothing():
    assert check(parse_range(None), {"reason": "curious"}) is None


def test_a_spend_line_is_appended_never_rewritten(tmp_path):
    p = tmp_path / "tester" / "spends.jsonl"
    r = parse_range({"kind": "custom", "start": "2025-01-01", "end": "2025-06-30"})
    a = record_spend(p, strategy="nq930", inputs={"offset_pts": 5.0}, rng=r, reason="why", ts="T1")
    record_spend(p, strategy="ym930", inputs={}, rng=r, reason="again", ts="T2")
    p.write_text(p.read_text() + "{torn")
    got = spends(p)
    assert got[0] == a == {"ts": "T1", "strategy": "nq930", "inputs": {"offset_pts": 5.0},
                           "range": r.to_dict(), "reason": "why"}
    assert [s["strategy"] for s in got] == ["nq930", "ym930"]
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_backtest_discipline.py`
Expected: FAIL — `ModuleNotFoundError: No module named 'homebase.backtest.discipline'`.

- [ ] **Step 3: Implement** — `homebase/backtest/discipline.py`:

```python
"""The user's data rules, enforced for every tester run and shown on every report.

  * Ranges: "research" = the research window 2021-01-01 -> 2024-12-31 (the
    default); "is_months" = only Jan/Apr/Jul/Oct sessions (inside the research
    window unless start/end say otherwise); "custom" = start/end as given.
  * A range reaching 2025-01-01 or later is HOLDOUT data. It runs only with the
    Holdout switch on plus a one-line reason, and each such run appends
    {ts, strategy, inputs, range, reason} to spends.jsonl — when the run is
    accepted, so a cancelled or failed look is still a spend. The report carries
    an "Includes holdout" badge. The app never edits the vault: the assistant
    folds spends into the burned-data ledger note.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass
from pathlib import Path

RESEARCH_START = dt.date(2021, 1, 1)
RESEARCH_END = dt.date(2024, 12, 31)
HOLDOUT_START = dt.date(2025, 1, 1)
IS_MONTHS = (1, 4, 7, 10)
KINDS = ("research", "is_months", "custom")
REASON_MAX = 200


class DisciplineError(ValueError):
    """A run the data rules refuse. The message is shown to the user."""


@dataclass(frozen=True)
class Range:
    kind: str
    start: dt.date
    end: dt.date

    def includes(self, d: dt.date) -> bool:
        return self.start <= d <= self.end and (self.kind != "is_months" or d.month in IS_MONTHS)

    @property
    def holdout(self) -> bool:
        return self.end >= HOLDOUT_START

    @property
    def label(self) -> str:
        if self.kind == "research" and (self.start, self.end) == (RESEARCH_START, RESEARCH_END):
            return "Research window 2021–2024"
        span = f"{self.start.isoformat()} → {self.end.isoformat()}"
        return f"IS months (Jan/Apr/Jul/Oct) {span}" if self.kind == "is_months" else span

    def to_dict(self) -> dict:
        return {"kind": self.kind, "start": self.start.isoformat(), "end": self.end.isoformat(),
                "label": self.label, "holdout": self.holdout}


def _date(v, what: str) -> dt.date:
    try:
        return dt.date.fromisoformat(str(v))
    except ValueError:
        raise DisciplineError(f"{what}: a date YYYY-MM-DD") from None


def parse_range(obj) -> Range:
    """{"kind": "research"} | {"kind": "is_months"[, "start", "end"]} |
    {"kind": "custom", "start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}. None = research."""
    obj = obj or {"kind": "research"}
    if not isinstance(obj, dict) or obj.get("kind") not in KINDS:
        raise DisciplineError(f"range.kind: one of {', '.join(KINDS)}")
    kind = obj["kind"]
    if kind == "research":
        return Range(kind, RESEARCH_START, RESEARCH_END)
    if kind == "custom" and not (obj.get("start") and obj.get("end")):
        raise DisciplineError("a custom range needs start and end")
    start = _date(obj["start"], "range.start") if obj.get("start") else RESEARCH_START
    end = _date(obj["end"], "range.end") if obj.get("end") else RESEARCH_END
    if start > end:
        raise DisciplineError("range.start is after range.end")
    return Range(kind, start, end)


def check(rng: Range, holdout: dict | None) -> str | None:
    """The holdout reason when the run may read >= 2025-01-01 data, None when it
    stays inside the research data. DisciplineError when the rules refuse it."""
    if not rng.holdout:
        return None
    reason = (holdout or {}).get("reason") if isinstance(holdout, dict) else None
    if not isinstance(reason, str) or not reason.strip():
        raise DisciplineError("this range reaches 2025-01-01 or later (holdout data): "
                              "turn on Holdout and give a one-line reason")
    reason = reason.strip()
    if "\n" in reason or len(reason) > REASON_MAX:
        raise DisciplineError(f"the holdout reason is one line of at most {REASON_MAX} characters")
    return reason


def record_spend(path: Path, *, strategy: str, inputs: dict, rng: Range, reason: str,
                 ts: str | None = None) -> dict:
    """Append ONE spend line (never rewrites)."""
    rec = {"ts": ts or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "strategy": strategy, "inputs": inputs, "range": rng.to_dict(), "reason": reason}
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, separators=(",", ":")) + "\n")
        f.flush()
        os.fsync(f.fileno())
    return rec


def spends(path: Path) -> list[dict]:
    out = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return out
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue                     # a torn line: count what is valid
        if isinstance(rec, dict):
            out.append(rec)
    return out
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/test_backtest_discipline.py` → Expected: 7 passed. Then the full suite → all green.

- [ ] **Step 5: Commit**

```bash
git add homebase/backtest/discipline.py tests/test_backtest_discipline.py
git commit -m "feat(tester): data discipline — research window default, IS months, holdout switch with a reason and an append-only spend log" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The runner — one run at a time, in its own process, into a bundle (+ the ≤ 30 s benchmark)

**Requirements** (the code below meets each; keep them when editing):
1. `validate(body)` accepts only `strategy, inputs, range, qty, commission, slippage_ticks, capital, holdout`; defaults qty 1 (int 1–100), commission 4.00 (0–100), slippage_ticks 1.0 (0–20), capital 50,000; inputs via `resolve_inputs`; the range via `parse_range` + `check`. Every refusal is a `ValueError` whose message the page shows.
2. `prepare(body, base)` creates `runs/<id>/` (`id = YYYYMMDD-HHMMSS-<strategy>-<4 hex>`) with `request.json` + `status.json` (`queued`) and, for a holdout range, appends the spend (R8).
3. `execute(run_dir, store)` re-checks discipline (a hand-edited request cannot reach 2025+). It loads only sessions in range that the strategy trades on, skips and lists sessions with no tape or a coverage gap, and feeds the gate the prior daily bars (R7). It writes progress to `status.json` at most every 0.5 s (`phase`: `run` / `building cache` / `daily bars`, `done`/`total`). It writes `trades.json`, `equity.json`, `plots.json` and `run.json` (meta, engine version, fill law "tick replay", inputs, range, costs, capital, holdout flag + reason, coverage with `skipped_by_reason` and the strategy's `no_trade` reasons, report), and then `status: done`.
4. `RunManager(base, archive=, cache=, python=sys.executable)` is used from the chart service. It is thread-safe with no asyncio. It launches `python -m homebase.backtest.runner exec <run_dir> --archive … --cache …` with `cwd=repo_root()`, FIFO, one child at a time, and logs to `runs/<id>/log.txt`. A non-zero exit without a final status becomes `error` with the log tail. `cancel` removes a queued run or terminates the running child (then `cancelled`). It never overwrites a finished run: a run already `done`/`error`/`cancelled`, or one that finishes before the signal lands, keeps its status. The worker thread never reports a cancelled child's exit as `error`. A run it did not launch raises `ValueError` (R13). On start, runs left `queued`/`running` by a dead process become `error: interrupted`. `dir(id)` accepts only the id pattern (no path traversal).
5. Every executing child holds an exclusive `fcntl.flock` on `runs/.lock`, so a page run and a script run never overlap. The `exec` child also lowers its priority (`os.nice(5)`, on top of the chart job's nice 5) so a backtest never competes with the desk at 09:30.
6. The CLI is `python -m homebase.backtest.runner run --strategy ID [--input k=v …] [--range research|is_months|START:END] [--qty] [--commission] [--slippage-ticks] [--capital] [--holdout-reason] [--base] [--archive] [--cache]`. It prepares and executes in-process and prints a one-line summary. Its bundle lands in the same runs dir, so the page lists it.

**Files:**
- Create: `homebase/backtest/runner.py`, `tests/backtest_util.py`
- Test: `tests/test_backtest_runner.py`

**Interfaces:**
- Consumes: everything above: `strategies.get/resolve_inputs`, `discipline.parse_range/check/record_spend`, `report.build/equity`, `engine.run_session/Costs/ENGINE_VERSION`, `tape.TapeStore/missing_hours/coverage_reason/ARCHIVE/CACHE`, `paths.repo_root/state_dir`.
- Produces: `RUN_ID` (regex), `default_base() -> homebase/.state/tester`, `validate(body) -> dict`, `prepare(body, base) -> id`, `execute(run_dir, store) -> run.json dict`, `exec_run(run_dir, store) -> 0`, `read_json(path, default=None)`, `write_json(path, data)`, `RunManager` with `.submit(body) -> id`, `.status(id) -> dict` (+ `queue_position` while queued), `.cancel(id) -> dict`, `.runs_list(limit=50) -> [{id, strategy, created, status, range, holdout, trades, net_profit}]`, `.bundle(id) -> {run, trades, equity, plots}` (ValueError unless done), `.dir(id)` (KeyError on unknown), `main(argv)`.

- [ ] **Step 1: Write the synthetic archive helper** — `tests/backtest_util.py`:

```python
"""A synthetic NQ archive for runner/API tests: two sessions, one with a hole."""
from __future__ import annotations

import datetime as dt

from homebase.backtest.tape import et_ns
from tests.charts_util import rows, write_archive

D1, D2 = dt.date(2024, 3, 5), dt.date(2024, 3, 6)


def ms(d: dt.date, hms: str) -> int:
    return et_ns(d, hms) // 1_000_000


def nq_archive(base):
    """D1: a full 09:25-16:00 day whose 09:30 long straddle leg wins (+15 pts).
    D2: prints stop at 12:59 — missing 13:00-16:00, so the tester must skip it."""
    day = rows(ms(D1, "09:25:00"), [100.0] * 290, step_ms=1000)                    # to 09:29:50
    day += rows(ms(D1, "09:30:01"), [110.0, 112.0, 126.0], step_ms=1000)
    day += rows(ms(D1, "09:31:00"), [120.0] * 1500, step_ms=15_000)                # to 15:45
    write_archive(base, "NQ", D1, "NQH4", day)
    write_archive(base, "NQ", D2, "NQH4", rows(ms(D2, "09:25:00"), [100.0] * 1284, step_ms=10_000))
    return base
```

- [ ] **Step 2: Write the failing tests** — `tests/test_backtest_runner.py`:

```python
"""Runner: validation + spends, the bundle, one-at-a-time child processes, cancel, recovery."""
from __future__ import annotations

import fcntl
import json
import time

import pytest

from homebase.backtest import runner
from homebase.backtest.discipline import DisciplineError
from homebase.backtest.runner import RunManager, execute, prepare, read_json, validate
from homebase.backtest.tape import TapeStore
from tests.backtest_util import D1, D2, nq_archive

RANGE = {"kind": "custom", "start": "2024-03-01", "end": "2024-03-31"}


def body(**kw):
    return {"strategy": "nq930", "inputs": {"adx_gate": False}, "range": RANGE, **kw}


def wait(m: RunManager, rid: str, want=("done", "error", "cancelled"), s=30.0) -> dict:
    t = time.monotonic() + s
    while time.monotonic() < t:
        st = m.status(rid)
        if st.get("status") in want:
            return st
        time.sleep(0.05)
    raise AssertionError(f"{rid} stuck at {m.status(rid)}")


def test_validate_fills_defaults_and_refuses_bad_requests():
    v = validate({"strategy": "nq930"})
    assert v["range"]["kind"] == "research" and v["range"]["start"] == "2021-01-01"
    assert (v["qty"], v["commission"], v["slippage_ticks"], v["capital"]) == (1, 4.0, 1.0, 50_000.0)
    assert v["holdout"] is None and v["inputs"]["sl_pts"] == 5.0
    for bad, msg in (({"strategy": "zz"}, "unknown strategy"), (body(qty=0), "qty"),
                     (body(qty=1.5), "whole"), (body(commission=-1), "commission"),
                     (body(slippage_ticks="1"), "number"), (body(extra=1), "unknown field"),
                     (body(inputs={"sl_pts": -1}), "sl_pts"), ("x", "JSON object")):
        with pytest.raises(ValueError, match=msg):
            validate(bad)


def test_a_holdout_range_needs_the_switch_and_every_accepted_run_is_a_spend(tmp_path):
    late = {"kind": "custom", "start": "2024-12-01", "end": "2025-02-01"}
    with pytest.raises(DisciplineError):
        prepare(body(range=late), tmp_path)
    assert not (tmp_path / "spends.jsonl").exists()
    rid = prepare(body(range=late, holdout={"reason": "forward check"}), tmp_path)
    [spend] = [json.loads(x) for x in (tmp_path / "spends.jsonl").read_text().splitlines()]
    assert spend["strategy"] == "nq930" and spend["reason"] == "forward check"
    assert spend["range"]["end"] == "2025-02-01" and spend["inputs"]["adx_gate"] is False
    req = read_json(tmp_path / "runs" / rid / "request.json")
    assert req["holdout"] == {"reason": "forward check"}
    prepare(body(), tmp_path)
    assert len((tmp_path / "spends.jsonl").read_text().splitlines()) == 1     # research: no spend


def test_execute_writes_the_bundle_and_lists_skipped_sessions(tmp_path):
    store = TapeStore(nq_archive(tmp_path / "ticks"), tmp_path / "cache")
    rid = prepare(body(qty=2), tmp_path / "t")
    d = tmp_path / "t" / "runs" / rid
    meta = execute(d, store)
    assert meta["engine"] == "tick-1" and meta["fill_law"] == "tick replay" and meta["holdout"] is False
    cov = meta["coverage"]
    assert (cov["sessions"], cov["used"]) == (2, 1)
    assert cov["skipped"] == [{"date": D2.isoformat(), "reason": "missing 13:00–16:00 ET"}]
    assert cov["skipped_by_reason"] == {"missing 13:00–16:00 ET": 1}
    [t] = read_json(d / "trades.json")
    assert (t["date"], t["side"], t["qty"], t["exit_reason"]) == (D1.isoformat(), "long", 2, "tp")
    assert t["net"] == round(15 * 20 * 2 - 8.0, 2)
    assert meta["report"]["summary"]["all"]["net_profit"] == t["net"]
    assert read_json(d / "equity.json")["equity"] == [t["net"]]
    assert read_json(d / "plots.json")["hlines"][0]["name"] == "anchor"
    assert read_json(d / "status.json")["status"] == "done"


def test_execute_refuses_a_tampered_request_reaching_the_holdout(tmp_path):
    rid = prepare(body(), tmp_path)
    p = tmp_path / "runs" / rid / "request.json"
    req = read_json(p)
    req["range"] = {"kind": "custom", "start": "2024-12-01", "end": "2025-03-01"}
    p.write_text(json.dumps(req))
    with pytest.raises(DisciplineError):
        execute(tmp_path / "runs" / rid, TapeStore(tmp_path / "ticks", tmp_path / "cache"))


def test_manager_runs_a_child_process_to_done(tmp_path):
    m = RunManager(tmp_path / "t", archive=nq_archive(tmp_path / "ticks"), cache=tmp_path / "cache")
    rid = m.submit(body())
    st = wait(m, rid)
    assert st["status"] == "done", (tmp_path / "t" / "runs" / rid / "log.txt").read_text()
    assert st["pid"] != __import__("os").getpid()             # a separate process
    b = m.bundle(rid)
    assert b["run"]["coverage"]["used"] == 1 and len(b["trades"]) == 1
    assert m.runs_list()[0]["id"] == rid and m.runs_list()[0]["trades"] == 1


def test_runs_queue_one_at_a_time_and_cancel(tmp_path):
    m = RunManager(tmp_path / "t", archive=nq_archive(tmp_path / "ticks"), cache=tmp_path / "cache")
    (tmp_path / "t" / "runs").mkdir(parents=True, exist_ok=True)
    with open(tmp_path / "t" / "runs" / ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)                         # a "script run" holds the desk
        a, b = m.submit(body()), m.submit(body())
        log = tmp_path / "t" / "runs" / a / "log.txt"
        t = time.monotonic() + 10
        while not log.exists() and time.monotonic() < t:         # the manager launched a's child
            time.sleep(0.02)
        time.sleep(0.2)
        assert m.status(a)["status"] == "queued"                 # ...which waits on the lock
        assert m.status(b)["queue_position"] == 1
        assert m.cancel(b)["status"] == "cancelled"
        assert m.cancel(a)["status"] == "cancelled"
    c = m.submit(body())
    assert wait(m, c)["status"] == "done"
    assert m.status(a)["status"] == m.status(b)["status"] == "cancelled"
    with pytest.raises(ValueError):
        m.bundle(a)
    with pytest.raises(KeyError):
        m.dir("../../etc")


def test_a_restart_marks_orphaned_runs_as_interrupted(tmp_path):
    rid = prepare(body(), tmp_path)
    p = tmp_path / "runs" / rid / "status.json"
    p.write_text(json.dumps({**read_json(p), "status": "running", "pid": 999_999_999}))
    m = RunManager(tmp_path)
    assert m.status(rid)["status"] == "error" and "restarted" in m.status(rid)["error"]


def test_cli_run_prints_a_summary(tmp_path, capsys):
    arch = nq_archive(tmp_path / "ticks")
    assert runner.main(["run", "--strategy", "nq930", "--input", "adx_gate=false",
                        "--range", "2024-03-01:2024-03-31", "--base", str(tmp_path / "t"),
                        "--archive", str(arch), "--cache", str(tmp_path / "cache")]) == 0
    assert "1 trades" in capsys.readouterr().out
```

- [ ] **Step 3: Run them to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_backtest_runner.py`
Expected: FAIL — `ImportError: cannot import name 'runner' from 'homebase.backtest'`.

- [ ] **Step 4: Implement** — `homebase/backtest/runner.py` (Task 8 adds the prop sim to it):

```python
"""Tester runs: validated, one at a time, each in its OWN process, into a run bundle.

    <base> = homebase/.state/tester
      spends.jsonl              holdout spends (discipline.py)
      runs/.lock                held (flock) by whichever run is executing
      runs/<id>/request.json    the validated request
      runs/<id>/status.json     {status, phase, done, total, error?, pid?, updated}
      runs/<id>/log.txt         the child's stdout/stderr
      runs/<id>/run.json        meta + inputs + range + coverage + report   (when done)
      runs/<id>/trades.json | equity.json | plots.json                      (when done)

status: queued -> running -> done | error | cancelled. The chart service owns a
RunManager (submit / status / cancel / runs / bundle) that launches
`python -m homebase.backtest.runner exec <run_dir>` with its own interpreter,
FIFO, one child at a time — never in the service's event loop. A script run
(`python -m homebase.backtest.runner run --strategy nq930 ...`) executes in the
script's process and writes into the same runs dir, so the page lists it; the
flock keeps it from overlapping a page run.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from bisect import bisect_left
from collections import deque
from pathlib import Path

from .. import strategies
from ..paths import repo_root, state_dir
from . import discipline, report
from .engine import ENGINE_VERSION, Costs, run_session
from .tape import ARCHIVE, CACHE, TapeStore, coverage_reason, missing_hours

RUN_ID = re.compile(r"^\d{8}-\d{6}-[a-z0-9_]+-[0-9a-f]{4}$")
FIELDS = {"strategy", "inputs", "range", "qty", "commission", "slippage_ticks", "capital", "holdout"}
FINAL = {"done", "error", "cancelled"}
PROGRESS_S = 0.5
DAILY_LOOKBACK = dt.timedelta(days=400)     # > 250 sessions of daily bars for the ADX gate


def default_base() -> Path:
    return state_dir() / "tester"


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def write_json(path: Path, data) -> None:
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, separators=(",", ":"), default=str))
    os.replace(tmp, path)


def read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def _num(body: dict, key: str, default: float, lo: float, hi: float, integer: bool = False):
    v = body.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v:
        raise ValueError(f"{key}: expected a number")
    if integer and float(v) != int(v):
        raise ValueError(f"{key}: expected a whole number")
    if not lo <= v <= hi:
        raise ValueError(f"{key}: must be within [{lo:g}, {hi:g}]")
    return int(v) if integer else float(v)


def validate(body) -> dict:
    """The request as the engine will run it. ValueError (DisciplineError is one)
    with a message for the page on anything the schema or the data rules refuse."""
    if not isinstance(body, dict):
        raise ValueError("the body is a JSON object")
    extra = sorted(set(body) - FIELDS)
    if extra:
        raise ValueError(f"unknown field(s): {', '.join(extra)}")
    cls = strategies.get(str(body.get("strategy", "")))
    inputs = strategies.resolve_inputs(cls.inputs(), body.get("inputs") or {})
    rng = discipline.parse_range(body.get("range"))
    reason = discipline.check(rng, body.get("holdout"))
    return {"strategy": cls.id, "inputs": inputs, "range": rng.to_dict(),
            "qty": _num(body, "qty", 1, 1, 100, integer=True),
            "commission": _num(body, "commission", 4.00, 0.0, 100.0),
            "slippage_ticks": _num(body, "slippage_ticks", 1.0, 0.0, 20.0),
            "capital": _num(body, "capital", 50_000.0, 1.0, 1e9),
            "holdout": {"reason": reason} if reason else None}


def prepare(body, base: Path) -> str:
    """Validate, create runs/<id>/ (request + queued status), record a holdout spend."""
    req = validate(body)
    now = dt.datetime.now()
    rid = f"{now:%Y%m%d-%H%M%S}-{req['strategy']}-{secrets.token_hex(2)}"
    d = base / "runs" / rid
    d.mkdir(parents=True)
    write_json(d / "request.json", {**req, "id": rid, "created": _now()})
    write_json(d / "status.json", {"id": rid, "status": "queued", "phase": "queued",
                                   "done": 0, "total": 0, "updated": _now()})
    if req["holdout"]:
        discipline.record_spend(base / "spends.jsonl", strategy=req["strategy"], inputs=req["inputs"],
                                rng=discipline.parse_range(req["range"]), reason=req["holdout"]["reason"])
    return rid


def execute(run_dir: Path, store: TapeStore) -> dict:
    """Run one prepared request to a bundle (in THIS process). Returns run.json."""
    req = read_json(run_dir / "request.json")
    cls = strategies.get(req["strategy"])
    rng = discipline.parse_range(req["range"])
    reason = discipline.check(rng, req.get("holdout"))            # defence in depth
    strat = cls(req["inputs"])             # one instance: on_session resets its day state
    days = [d for d in store.sessions(cls.root, rng.start, rng.end)
            if rng.includes(d) and strat.trades_on(d)]
    status = {"id": req["id"], "status": "running", "phase": "run", "done": 0, "total": len(days),
              "pid": os.getpid(), "started": _now(), "updated": _now()}
    write_json(run_dir / "status.json", status)

    dailies: list[dict] = []
    if strat.needs_daily():
        status["phase"] = "daily bars"
        write_json(run_dir / "status.json", status)
        for d in store.sessions(cls.root, rng.start - DAILY_LOOKBACK, rng.end):
            bar = store.daily(cls.root, d)
            if bar is not None:
                dailies.append(bar)
    daily_dates = [b["date"] for b in dailies]

    costs = Costs(req["commission"], req["slippage_ticks"])
    trades, skipped, no_trade, hlines = [], [], [], []
    plots: dict[str, list] = {}
    last = 0.0
    for i, d in enumerate(days):
        if time.monotonic() - last >= PROGRESS_S:
            status.update(done=i, phase="run" if store.cached(cls.root, d) else "building cache",
                          updated=_now())
            write_json(run_dir / "status.json", status)
            last = time.monotonic()
        tape = store.load(cls.root, d)
        if tape is None:
            skipped.append({"date": d.isoformat(), "reason": "no tape"})
            continue
        gaps = missing_hours(tape.ts, d, cls.session_window)
        if gaps:
            skipped.append({"date": d.isoformat(), "reason": coverage_reason(gaps)})
            continue
        prior = dailies[:bisect_left(daily_dates, d.isoformat())]
        res = run_session(strat, tape, costs, qty=req["qty"], daily=prior)
        trades += [t.to_dict() for t in res.trades]
        if res.skip:
            no_trade.append({"date": d.isoformat(), "reason": res.skip})
        for k, pts in res.plots.items():
            plots.setdefault(k, []).extend(pts)
        hlines += res.hlines

    by_reason: dict[str, int] = {}
    for s in skipped:
        by_reason[s["reason"]] = by_reason.get(s["reason"], 0) + 1
    rep = report.build(trades, req["capital"])
    meta = {"id": req["id"], "created": req["created"], "finished": _now(),
            "engine": ENGINE_VERSION, "fill_law": "tick replay",
            "strategy": {"id": cls.id, "name": cls.name, "root": cls.root},
            "inputs": req["inputs"], "range": req["range"], "qty": req["qty"],
            "commission": req["commission"], "slippage_ticks": req["slippage_ticks"],
            "capital": req["capital"], "holdout": reason is not None, "holdout_reason": reason,
            "coverage": {"sessions": len(days), "used": len(days) - len(skipped),
                         "skipped": skipped, "skipped_by_reason": by_reason, "no_trade": no_trade},
            "report": rep}
    trades.sort(key=lambda t: (t["exit_ns"], t["entry_ns"]))
    write_json(run_dir / "trades.json", trades)
    write_json(run_dir / "equity.json", report.equity(trades))
    write_json(run_dir / "plots.json", {"plots": plots, "hlines": hlines})
    write_json(run_dir / "run.json", meta)
    status.update(status="done", phase="done", done=len(days), updated=_now())
    write_json(run_dir / "status.json", status)
    return meta


def _locked(runs: Path):
    runs.mkdir(parents=True, exist_ok=True)
    fh = open(runs / ".lock", "a")
    fcntl.flock(fh, fcntl.LOCK_EX)          # one run at a time, page or script
    return fh


def exec_run(run_dir: Path, store: TapeStore) -> int:
    fh = _locked(run_dir.parent)
    try:
        execute(run_dir, store)
        return 0
    except Exception as e:  # noqa: BLE001 — the page must see why
        st = read_json(run_dir / "status.json", {}) or {}
        st.update(status="error", error=f"{type(e).__name__}: {e}", updated=_now())
        write_json(run_dir / "status.json", st)
        raise
    finally:
        fh.close()


class RunManager:
    """The chart service's handle on tester runs (thread-safe; no asyncio)."""

    def __init__(self, base: Path, *, archive: Path = ARCHIVE, cache: Path = CACHE,
                 python: str = sys.executable):
        self.base, self.runs = Path(base), Path(base) / "runs"
        self.archive, self.cache, self.python = Path(archive), Path(cache), python
        self.runs.mkdir(parents=True, exist_ok=True)
        self._q: deque[str] = deque()
        self._proc: tuple[str, subprocess.Popen] | None = None
        self._cancelled: set[str] = set()
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._recover()

    def _recover(self) -> None:
        """Runs a previous service process left queued/running are dead now."""
        for st_path in self.runs.glob("*/status.json"):
            st = read_json(st_path, {}) or {}
            if st.get("status") in ("queued", "running") and not _alive(st.get("pid")):
                st.update(status="error", error="interrupted (the chart service restarted)",
                          updated=_now())
                write_json(st_path, st)

    def dir(self, rid: str) -> Path:
        if not RUN_ID.match(rid or "") or not (self.runs / rid).is_dir():
            raise KeyError(rid)
        return self.runs / rid

    def submit(self, body) -> str:
        rid = prepare(body, self.base)
        with self._lock:
            self._q.append(rid)
            if self._thread is None:
                self._thread = threading.Thread(target=self._loop, name="tester-runs", daemon=True)
                self._thread.start()
        self._wake.set()
        return rid

    def status(self, rid: str) -> dict:
        st = read_json(self.dir(rid) / "status.json", {}) or {}
        with self._lock:
            if rid in self._q:
                st["queue_position"] = list(self._q).index(rid) + 1
        return st

    def cancel(self, rid: str) -> dict:
        d = self.dir(rid)
        with self._lock:
            st = read_json(d / "status.json", {}) or {}
            if st.get("status") in FINAL:
                return st                       # finished (or already cancelled): leave it
            if rid in self._q:
                self._q.remove(rid)
                proc = None
            elif self._proc and self._proc[0] == rid:
                proc = self._proc[1]
                self._cancelled.add(rid)        # the worker must not report its exit as an error
            else:
                raise ValueError("this run was not started by the chart service (stop it where it runs)")
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        st = read_json(d / "status.json", {}) or {}
        if st.get("status") == "done":
            return st                           # it finished before the signal landed
        st.update(status="cancelled", phase="cancelled", updated=_now())
        write_json(d / "status.json", st)
        return st

    def runs_list(self, limit: int = 50) -> list[dict]:
        out = []
        for d in sorted((p for p in self.runs.iterdir() if RUN_ID.match(p.name)),
                        key=lambda p: p.name, reverse=True)[:limit]:
            req = read_json(d / "request.json", {}) or {}
            st = read_json(d / "status.json", {}) or {}
            meta = read_json(d / "run.json", {}) or {}
            allc = ((meta.get("report") or {}).get("summary") or {}).get("all") or {}
            out.append({"id": d.name, "strategy": req.get("strategy"), "created": req.get("created"),
                        "status": st.get("status"), "range": req.get("range"),
                        "holdout": bool(req.get("holdout")), "trades": allc.get("trades"),
                        "net_profit": allc.get("net_profit")})
        return out

    def bundle(self, rid: str) -> dict:
        d = self.dir(rid)
        st = read_json(d / "status.json", {}) or {}
        if st.get("status") != "done":
            raise ValueError(f"run {rid} is {st.get('status')}, not done")
        return {"run": read_json(d / "run.json"), "trades": read_json(d / "trades.json"),
                "equity": read_json(d / "equity.json"), "plots": read_json(d / "plots.json")}

    def _loop(self) -> None:
        while True:
            self._wake.wait()
            with self._lock:
                if not self._q:
                    self._wake.clear()
                    continue
                rid = self._q.popleft()
                d = self.runs / rid
                log = open(d / "log.txt", "ab")
                proc = subprocess.Popen(
                    [self.python, "-m", "homebase.backtest.runner", "exec", str(d),
                     "--archive", str(self.archive), "--cache", str(self.cache)],
                    cwd=repo_root(), stdout=log, stderr=subprocess.STDOUT)
                self._proc = (rid, proc)
            code = proc.wait()
            log.close()
            with self._lock:
                self._proc = None
                if rid in self._cancelled:
                    continue                    # cancel() writes the final status
            st = read_json(d / "status.json", {}) or {}
            if st.get("status") not in FINAL:
                tail = (d / "log.txt").read_text(errors="replace")[-600:]
                st.update(status="error", error=f"runner exited {code}: {tail}", updated=_now())
                write_json(d / "status.json", st)


def _alive(pid) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _kv(s: str) -> tuple[str, object]:
    k, _, v = s.partition("=")
    try:
        return k, json.loads(v)
    except ValueError:
        return k, v


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m homebase.backtest.runner")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("exec", help="run a prepared run dir (the chart service uses this)")
    ex.add_argument("run_dir", type=Path)
    run = sub.add_parser("run", help="validate + run in this process (scripts, the assistant)")
    run.add_argument("--strategy", required=True)
    run.add_argument("--input", action="append", default=[], help="key=value (JSON value)")
    run.add_argument("--range", default="research", help="research | is_months | START:END")
    run.add_argument("--qty", type=int, default=1)
    run.add_argument("--commission", type=float, default=4.00)
    run.add_argument("--slippage-ticks", type=float, default=1.0)
    run.add_argument("--capital", type=float, default=50_000.0)
    run.add_argument("--holdout-reason")
    run.add_argument("--base", type=Path, default=None)
    for p in (ex, run):
        p.add_argument("--archive", type=Path, default=ARCHIVE)
        p.add_argument("--cache", type=Path, default=CACHE)
    a = ap.parse_args(argv)
    store = TapeStore(a.archive, a.cache)
    if a.cmd == "exec":
        os.nice(5)          # on top of the chart job's own nice 5: a backtest never competes with the desk
        return exec_run(a.run_dir, store)
    if a.range in ("research", "is_months"):
        rng = {"kind": a.range}
    else:
        s, _, e = a.range.partition(":")
        rng = {"kind": "custom", "start": s, "end": e}
    body = {"strategy": a.strategy, "inputs": dict(_kv(x) for x in a.input), "range": rng,
            "qty": a.qty, "commission": a.commission, "slippage_ticks": a.slippage_ticks,
            "capital": a.capital}
    if a.holdout_reason:
        body["holdout"] = {"reason": a.holdout_reason}
    base = a.base or default_base()
    rid = prepare(body, base)
    t0 = time.monotonic()
    exec_run(base / "runs" / rid, store)
    meta = read_json(base / "runs" / rid / "run.json")
    s = meta["report"]["summary"]["all"]
    print(f"{rid}: {s['trades']} trades, net ${s['net_profit']:,.2f}, WR {s['win_rate'] or 0:.1f}%, "
          f"PF {s['profit_factor'] or 0:.2f}, Sharpe {s['sharpe']:.2f}, t {s['t_stat'] or 0:.2f}, "
          f"skipped {len(meta['coverage']['skipped'])}, {time.monotonic() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/test_backtest_runner.py` → Expected: 8 passed (~1 s; two tests spawn a real child process on a synthetic archive in `tmp_path`). Then the full suite → all green.

- [ ] **Step 6: Commit**

```bash
git add homebase/backtest/runner.py tests/backtest_util.py tests/test_backtest_runner.py
git commit -m "feat(tester): runs — validated, one at a time in a child process, progress, run bundles, cancel, script CLI" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: Benchmark (not a unit test): full 2021–2024 `nq930`, warm cache, ≤ 30 s**

Warm the real cache first (writes only `~/futures_derived/homebase_tape/NQ/`, ~6 GB; reads `~/futures_ticks/NQ` read-only; a few minutes):

```bash
.venv/bin/python -m homebase.backtest.tape warm NQ 2021-01-01 2024-12-31 --jobs 6
time .venv/bin/python -m homebase.backtest.runner run --strategy nq930 --input adx_gate=false --range research
time .venv/bin/python -m homebase.backtest.runner run --strategy nq930 --range research
```

Expected: each `run` line prints `…: N trades, net $…, WR …, PF …, Sharpe …, t …, skipped K, X.Xs`, and `real` ≤ 30 s. While planning, NQ 2024 measured 2.6 ms/session warm, so ~3 s for ~820 sessions. The second command runs the worktree's frozen defaults (gated): its first ~110 sessions are skipped "trend gate unknown". The ungated run should read as the spec says the tape does: roughly a coin flip after costs, not the TradingView +$14.5k. If `real` > 30 s, profile before changing anything: `.venv/bin/python -m cProfile -s cumtime -m homebase.backtest.runner run --strategy nq930 --input adx_gate=false --range research | head -40`. The bundles land in `homebase/.state/tester/runs/` (gitignored). Report the two timings in the task summary. Nothing to commit.

---

### Task 8: Prop-eval pass rate — vendored ONYX propsim on every run

The spec's added section "Prop-eval pass rate". Every run gets a `propsim.json`: the vendored ONYX Monte Carlo (i.i.d. day bootstrap over the weekday grid of the run's daily net P&L) with eval pass % + 95% Wilson CI, bust %, median days to pass, funded payout % and expected cheque, the rule set's name/label, and the "days drawn independently" caveat. The rule set is selectable per run (`prop_rules`, default `lucid-flex-50k@2026-08`).

**Files:**
- Create (generated by Step 1): `homebase/backtest/propsim/propsim.py`, `homebase/backtest/propsim/rules/lucid-flex-50k@2026-08.json`
- Create: `homebase/backtest/propsim/__init__.py`, `homebase/backtest/propsim/rules/apex-50k@unconfirmed.json`
- Modify: `homebase/backtest/runner.py` (the `prop_rules` field, the prop sim after the report, `propsim.json`, the bundle)
- Test: `tests/test_backtest_propsim.py`

**Interfaces:**
- Consumes: engine `Trade.to_dict()` rows (`date`, `net`) (Task 2); `runner.validate/prepare/execute/read_json/RunManager.bundle` (Task 7); `tests/backtest_util.nq_archive` (Task 7).
- Produces:
  - `homebase.backtest.propsim`: `RULES_DIR`, `DEFAULT_RULES = "lucid-flex-50k@2026-08"`, `N_PATHS = 20_000`, `HORIZON = 250`, `SEED = 20260801`, `CAVEAT`, `list_rules() -> [{id, name, version, confirmed}]`, `load_rules(rule_id) -> dict` (ValueError "prop_rules: one of …"), `weekday_grid(trades) -> (pnls, flags, dates)`, `evaluate(trades, rule_id=DEFAULT_RULES, *, n_paths=N_PATHS, horizon=HORIZON, seed=SEED) -> dict`.
  - `evaluate` returns `{rules: {id, name, version, confirmed, label}, caveat, engine, n_paths, horizon, seed}`, then either `skipped` or `grid: {first, last, weekdays, trade_days}` + `headline: {eval_pass_p, eval_pass_ci, bust_p, timeout_p, median_days_to_pass, funded_payout_p, funded_expected_cheque}` + `result: {series, eval, retries, funded}`.
  - `homebase.backtest.propsim.propsim` = the vendored module (`run`, `run_eval`, `run_funded`, `wilson_ci`, `load_rules`).
  - Runner: request field `prop_rules`; `run.json["prop_rules"]`; `runs/<id>/propsim.json`; `RunManager.bundle(id)["propsim"]`.

- [ ] **Step 1: Vendor the simulator and its LucidFlex rules** (read-only source; `propsim.py` is untracked in ONYX's git, so the header records its sha256). Run from the worktree root:

```bash
.venv/bin/python - <<'EOF'
"""One-shot: vendor ONYX's prop simulator + its LucidFlex rules into homebase/backtest/propsim/."""
import hashlib
import shutil
from pathlib import Path

ONYX = Path("/Users/ramoscapital/ONYX TRADING/onyx/report")
DST = Path.cwd() / "homebase" / "backtest" / "propsim"
SRC_SHA = "0d480ccd3d67ad034e89674cf7211f129fce27af0a9ac9ba7f82f72f0452cdf0"   # seen while planning
src = (ONYX / "propsim.py").read_bytes()
sha = hashlib.sha256(src).hexdigest()
if sha != SRC_SHA:
    print(f"NOTE: onyx/report/propsim.py changed since planning (sha256 {sha}); vendoring it and recording the new hash")
(DST / "rules").mkdir(parents=True, exist_ok=True)
head = (f"# VENDORED from ONYX TRADING onyx/report/propsim.py — untracked in ONYX's git when vendored\n"
        f"# (2026-09-26), sha256 {sha}. Do not edit here: re-vendor instead. Stdlib only.\n")
(DST / "propsim.py").write_text(head + src.decode())
shutil.copyfile(ONYX / "rules" / "lucid-flex-50k@2026-08.json", DST / "rules" / "lucid-flex-50k@2026-08.json")
print("vendored propsim.py + rules/lucid-flex-50k@2026-08.json")
EOF
```

Expected: `vendored propsim.py + rules/lucid-flex-50k@2026-08.json`. If it also prints a `NOTE:` (ONYX's file changed since planning), keep the new hash it recorded and say so in the task report. Check: `cmp homebase/backtest/propsim/rules/lucid-flex-50k@2026-08.json "/Users/ramoscapital/ONYX TRADING/onyx/report/rules/lucid-flex-50k@2026-08.json"` prints nothing.

- [ ] **Step 2: Add the Apex 50K placeholder rule set** — `homebase/backtest/propsim/rules/apex-50k@unconfirmed.json` (same schema as LucidFlex; every rule number is LucidFlex's, marked PLACEHOLDER; the user supplies the real numbers later):

```json
{
  "name": "Apex 50K",
  "version": "unconfirmed",
  "as_of": null,
  "confirmed": false,
  "source": "PLACEHOLDER - every rule number in this file is COPIED FROM lucid-flex-50k@2026-08.json and is NOT Apex's rule. The user confirms Apex 50K's real numbers; then replace them, set \"confirmed\": true, fill as_of/version and rename the file apex-50k@<YYYY-MM>.json.",
  "placeholder_fields": [
    "account_size",
    "eval_target",
    "eval_min_days",
    "consistency",
    "trailing_mll",
    "lock_at",
    "lock_floor",
    "win_day",
    "payout_win_days",
    "payout_share",
    "payout_cap",
    "max_payout_profit",
    "daily_loss_limit",
    "max_days",
    "scaling_micros",
    "cap_micros",
    "flat_by_et",
    "no_overnight"
  ],
  "account_size": 50000,
  "eval_target": 3000,
  "eval_min_days": 2,
  "consistency": 0.5,
  "trailing_mll": 2000,
  "lock_at": 2100,
  "lock_floor": 100,
  "win_day": 150,
  "payout_win_days": 5,
  "payout_share": 0.5,
  "payout_cap": 2000,
  "max_payout_profit": 4000,
  "daily_loss_limit": null,
  "max_days": null,
  "scaling_micros": {
    "start": 20,
    "at_1000": 30,
    "at_2000": 40
  },
  "cap_micros": 40,
  "flat_by_et": "16:10",
  "no_overnight": true,
  "mini_point_values": {
    "NQ": 20,
    "ES": 50,
    "GC": 100,
    "CL": 1000
  },
  "payout_ladder": "PLACEHOLDER - unknown until the user confirms Apex 50K's payout rules",
  "notes": [
    "PLACEHOLDER: the numbers are LucidFlex 50K's, copied so the file loads; the tester labels every result from this file 'unconfirmed rules' until it says \"confirmed\": true."
  ],
  "disclaimer": "Unconfirmed placeholder - do not rely on any number derived from this file."
}
```

- [ ] **Step 3: Write the failing tests** — `tests/test_backtest_propsim.py`:

```python
"""Prop-eval pass rate: the vendored engine's determinism, always-pass / always-bust
ledgers, rule files and the unconfirmed label, and the runner's propsim.json."""
from __future__ import annotations

import datetime as dt
import json

import pytest

from homebase.backtest import propsim
from homebase.backtest.propsim import (CAVEAT, DEFAULT_RULES, RULES_DIR, evaluate, list_rules,
                                       load_rules, weekday_grid)
from homebase.backtest.propsim import propsim as engine
from homebase.backtest.runner import execute, prepare, read_json, validate
from homebase.backtest.tape import TapeStore
from tests.backtest_util import nq_archive

MON = dt.date(2024, 3, 4)


def day_trades(nets, start=MON):
    """One trade per WEEKDAY from `start`, net P&L as given."""
    out, d = [], start
    for n in nets:
        while d.weekday() >= 5:
            d += dt.timedelta(days=1)
        out.append({"date": d.isoformat(), "net": n})
        d += dt.timedelta(days=1)
    return out


def test_the_vendored_engine_is_deterministic():
    pnls = [350.0, -420.0, 0.0, 610.0, -150.0, 90.0, 0.0, 1200.0, -800.0, 300.0]
    a = engine.run(pnls, n_paths=2000, sweep=(), degradation=(), seed=7)
    b = engine.run(pnls, n_paths=2000, sweep=(), degradation=(), seed=7)
    c = engine.run(pnls, n_paths=2000, sweep=(), degradation=(), seed=8)
    assert a == b
    assert a["eval"]["p"] != c["eval"]["p"] or a["funded"] != c["funded"]
    assert evaluate(day_trades(pnls), n_paths=2000) == evaluate(day_trades(pnls), n_paths=2000)


def test_a_ledger_that_always_passes():
    r = evaluate(day_trades([1000.0] * 10), n_paths=500)
    h = r["headline"]
    assert h["eval_pass_p"] == 1.0 and h["bust_p"] == 0.0 and h["timeout_p"] == 0.0
    assert h["median_days_to_pass"] == 3            # +3,000 on day 3; largest day 1,000 <= 50%
    assert h["eval_pass_ci"][1] == pytest.approx(1.0) and h["eval_pass_ci"][0] > 0.99   # Wilson, n=500
    assert h["funded_payout_p"] == 1.0 and h["funded_expected_cheque"] == 2000.0   # 50% of 5,000, capped


def test_a_ledger_that_always_busts():
    h = evaluate(day_trades([-2500.0] * 10), n_paths=500)["headline"]
    assert h["eval_pass_p"] == 0.0 and h["bust_p"] == 1.0
    assert h["median_days_to_pass"] is None and h["funded_expected_cheque"] == 0.0


def test_the_weekday_grid_fills_no_trade_weekdays_with_zero():
    trades = [{"date": "2024-03-04", "net": 100.0}, {"date": "2024-03-07", "net": -50.0},
              {"date": "2024-03-07", "net": 20.0}, {"date": "2024-03-11", "net": 10.0}]
    pnls, flags, dates = weekday_grid(trades)
    assert dates == ["2024-03-04", "2024-03-05", "2024-03-06", "2024-03-07", "2024-03-08", "2024-03-11"]
    assert pnls == [100.0, 0.0, 0.0, -30.0, 0.0, 10.0]
    assert flags == [True, False, False, True, False, True]
    assert weekday_grid([]) == ([], [], [])


def test_rule_files_and_the_unconfirmed_label():
    ids = {r["id"]: r for r in list_rules()}
    assert ids["lucid-flex-50k@2026-08"]["confirmed"] is True
    assert ids["apex-50k@unconfirmed"] == {"id": "apex-50k@unconfirmed", "name": "Apex 50K",
                                          "version": "unconfirmed", "confirmed": False}
    lucid = evaluate(day_trades([500.0] * 5), n_paths=200)
    apex = evaluate(day_trades([500.0] * 5), "apex-50k@unconfirmed", n_paths=200)
    assert lucid["rules"]["id"] == DEFAULT_RULES and lucid["rules"]["label"] == "LucidFlex 50K"
    assert apex["rules"]["confirmed"] is False
    assert apex["rules"]["label"] == "Apex 50K · unconfirmed rules"
    assert lucid["caveat"] == apex["caveat"] == CAVEAT
    for bad in ("nope@x", "../lucid-flex-50k@2026-08", "", None):
        with pytest.raises(ValueError, match="prop_rules"):
            load_rules(bad)


def test_apex_placeholders_are_the_lucidflex_numbers_until_confirmed():
    apex = json.loads((RULES_DIR / "apex-50k@unconfirmed.json").read_text())
    lucid = load_rules(DEFAULT_RULES)
    assert apex["confirmed"] is False and "PLACEHOLDER" in apex["source"]
    assert set(apex) >= set(lucid) - {"source", "as_of", "notes", "disclaimer", "payout_ladder"}
    for k in apex["placeholder_fields"]:
        assert apex[k] == lucid[k], k


def test_no_trades_is_a_skip_not_a_crash():
    r = evaluate([], n_paths=10)
    assert r["skipped"].startswith("no trades") and "headline" not in r


def test_the_runner_writes_propsim_json_and_validates_the_rule_set(tmp_path, monkeypatch):
    monkeypatch.setattr(propsim, "N_PATHS", 300)
    assert validate({"strategy": "nq930"})["prop_rules"] == DEFAULT_RULES
    with pytest.raises(ValueError, match="prop_rules"):
        validate({"strategy": "nq930", "prop_rules": "zz@1"})
    store = TapeStore(nq_archive(tmp_path / "ticks"), tmp_path / "cache")
    rid = prepare({"strategy": "nq930", "inputs": {"adx_gate": False}, "prop_rules": "apex-50k@unconfirmed",
                   "range": {"kind": "custom", "start": "2024-03-01", "end": "2024-03-31"}}, tmp_path / "t")
    meta = execute(tmp_path / "t" / "runs" / rid, store)
    p = read_json(tmp_path / "t" / "runs" / rid / "propsim.json")
    assert meta["prop_rules"] == "apex-50k@unconfirmed"
    assert p["rules"]["label"] == "Apex 50K · unconfirmed rules" and p["n_paths"] == 300
    assert p["grid"] == {"first": "2024-03-05", "last": "2024-03-05", "weekdays": 1, "trade_days": 1}
    assert 0.0 <= p["headline"]["eval_pass_p"] <= 1.0 and p["caveat"] == CAVEAT
```

- [ ] **Step 4: Run them to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_backtest_propsim.py`
Expected: FAIL — `ImportError: cannot import name 'CAVEAT' from 'homebase.backtest.propsim'`.

- [ ] **Step 5: Implement** — `homebase/backtest/propsim/__init__.py`:

```python
"""Prop-eval pass rate for a tester run: the vendored ONYX Monte Carlo over the run's daily net P&L.

Vendored (do not edit — re-vendor):
  propsim.py                          <- ONYX TRADING onyx/report/propsim.py (header: source + sha256)
  rules/lucid-flex-50k@2026-08.json   <- onyx/report/rules/ @ 0a75af5, shipped as is (confirmed by
                                         the account holder 2026-08-01)
Homebase's own:
  rules/apex-50k@unconfirmed.json     PLACEHOLDER numbers copied from LucidFlex, "confirmed": false.

The model: i.i.d. day bootstrap over the WEEKDAY GRID of the run's daily net P&L —
every Mon–Fri from the first to the last trading session, 0.0 on weekdays without a
trade (so "days" are calendar weekdays, the fee clock) — then the eval race (pass /
bust / timeout, Wilson CI, days to pass) and the funded race (first payout, expected
cheque). A rule file is UNCONFIRMED when it says "confirmed": false; its results carry
confirmed=False and the label "<name> · unconfirmed rules". Every result carries CAVEAT.
"""
from __future__ import annotations

import datetime as dt
import json
import re
from pathlib import Path

from . import propsim as engine

RULES_DIR = Path(__file__).resolve().parent / "rules"
DEFAULT_RULES = "lucid-flex-50k@2026-08"
N_PATHS, HORIZON, SEED = 20_000, 250, 20260801        # the notebook's defaults
CAVEAT = ("Days are drawn independently: streaks and regime clustering are not modeled, "
          "so read these rates as the friendly end of the band.")
_ID = re.compile(r"^[a-z0-9-]+@[a-z0-9-]+$")


def list_rules() -> list[dict]:
    out = []
    for p in sorted(RULES_DIR.glob("*.json")):
        r = json.loads(p.read_text())
        out.append({"id": p.stem, "name": r.get("name", p.stem), "version": r.get("version"),
                    "confirmed": r.get("confirmed") is not False})
    return out


def load_rules(rule_id: str) -> dict:
    p = RULES_DIR / f"{rule_id}.json"
    if not isinstance(rule_id, str) or not _ID.match(rule_id) or not p.is_file():
        ids = ", ".join(r["id"] for r in list_rules())
        raise ValueError(f"prop_rules: one of {ids}")
    return json.loads(p.read_text())


def weekday_grid(trades: list[dict]) -> tuple[list[float], list[bool], list[str]]:
    """(daily net P&L, traded?, session dates): every Mon–Fri from the first to the last
    trading session, plus any weekend session that traded (P&L is never dropped)."""
    by: dict[str, float] = {}
    for t in trades:
        by[t["date"]] = by.get(t["date"], 0.0) + t["net"]
    if not by:
        return [], [], []
    d0, d1 = dt.date.fromisoformat(min(by)), dt.date.fromisoformat(max(by))
    days = {(d0 + dt.timedelta(i)).isoformat() for i in range((d1 - d0).days + 1)
            if (d0 + dt.timedelta(i)).weekday() < 5} | set(by)
    dates = sorted(days)
    return [by.get(d, 0.0) for d in dates], [d in by for d in dates], dates


def evaluate(trades: list[dict], rule_id: str = DEFAULT_RULES, *, n_paths: int = N_PATHS,
             horizon: int = HORIZON, seed: int = SEED) -> dict:
    """The run's propsim.json."""
    r = load_rules(rule_id)
    confirmed = r.get("confirmed") is not False
    out = {"rules": {"id": rule_id, "name": r.get("name"), "version": r.get("version"),
                     "confirmed": confirmed,
                     "label": r.get("name") if confirmed else f"{r.get('name')} · unconfirmed rules"},
           "caveat": CAVEAT, "engine": "iid-weekday-bootstrap (IP notebook port)",
           "n_paths": n_paths, "horizon": horizon, "seed": seed}
    pnls, flags, dates = weekday_grid(trades)
    if not pnls:
        return {**out, "skipped": "no trades: nothing to simulate"}
    res = engine.run(pnls, trade_flags=flags, rules=r, n_paths=n_paths, horizon=horizon,
                     seed=seed, sweep=(), degradation=())
    ev, fu = res["eval"], res["funded"]
    return {**out,
            "grid": {"first": dates[0], "last": dates[-1], "weekdays": len(pnls),
                     "trade_days": sum(flags)},
            "headline": {"eval_pass_p": ev["p"], "eval_pass_ci": ev["ci"], "bust_p": ev["bust_p"],
                         "timeout_p": ev["timeout_p"], "median_days_to_pass": ev["days"]["median"],
                         "funded_payout_p": fu["payout_p"],
                         "funded_expected_cheque": fu["expected_payout"]},
            "result": {k: res[k] for k in ("series", "eval", "retries", "funded")}}
```

Then apply these edits to `homebase/backtest/runner.py` (from the Task 7 version). The docstring gains one line; the import, `FIELDS`, `validate` + a new `_prop_rules`, `execute` (the prop sim after the report, `prop_rules` in `run.json`, `propsim.json` written before `run.json`) and `RunManager.bundle` change:

```diff
@@ -8,6 +8,7 @@
       runs/<id>/log.txt         the child's stdout/stderr
       runs/<id>/run.json        meta + inputs + range + coverage + report   (when done)
       runs/<id>/trades.json | equity.json | plots.json                      (when done)
+      runs/<id>/propsim.json    the prop-eval Monte Carlo on the run's daily net P&L (when done)
 
 status: queued -> running -> done | error | cancelled. The chart service owns a
 RunManager (submit / status / cancel / runs / bundle) that launches
@@ -36,12 +37,13 @@
 
 from .. import strategies
 from ..paths import repo_root, state_dir
-from . import discipline, report
+from . import discipline, propsim, report
 from .engine import ENGINE_VERSION, Costs, run_session
 from .tape import ARCHIVE, CACHE, TapeStore, coverage_reason, missing_hours
 
 RUN_ID = re.compile(r"^\d{8}-\d{6}-[a-z0-9_]+-[0-9a-f]{4}$")
-FIELDS = {"strategy", "inputs", "range", "qty", "commission", "slippage_ticks", "capital", "holdout"}
+FIELDS = {"strategy", "inputs", "range", "qty", "commission", "slippage_ticks", "capital", "holdout",
+          "prop_rules"}
 FINAL = {"done", "error", "cancelled"}
 PROGRESS_S = 0.5
 DAILY_LOOKBACK = dt.timedelta(days=400)     # > 250 sessions of daily bars for the ADX gate
@@ -96,7 +98,13 @@
             "commission": _num(body, "commission", 4.00, 0.0, 100.0),
             "slippage_ticks": _num(body, "slippage_ticks", 1.0, 0.0, 20.0),
             "capital": _num(body, "capital", 50_000.0, 1.0, 1e9),
-            "holdout": {"reason": reason} if reason else None}
+            "holdout": {"reason": reason} if reason else None,
+            "prop_rules": _prop_rules(body.get("prop_rules", propsim.DEFAULT_RULES))}
+
+
+def _prop_rules(rule_id) -> str:
+    propsim.load_rules(rule_id)             # ValueError "prop_rules: one of ..." when unknown
+    return rule_id
 
 
 def prepare(body, base: Path) -> str:
@@ -169,12 +177,16 @@
     for s in skipped:
         by_reason[s["reason"]] = by_reason.get(s["reason"], 0) + 1
     rep = report.build(trades, req["capital"])
+    status.update(phase="prop sim", done=len(days), updated=_now())
+    write_json(run_dir / "status.json", status)
+    prop = propsim.evaluate(trades, req["prop_rules"], n_paths=propsim.N_PATHS)
     meta = {"id": req["id"], "created": req["created"], "finished": _now(),
             "engine": ENGINE_VERSION, "fill_law": "tick replay",
             "strategy": {"id": cls.id, "name": cls.name, "root": cls.root},
             "inputs": req["inputs"], "range": req["range"], "qty": req["qty"],
             "commission": req["commission"], "slippage_ticks": req["slippage_ticks"],
             "capital": req["capital"], "holdout": reason is not None, "holdout_reason": reason,
+            "prop_rules": req["prop_rules"],
             "coverage": {"sessions": len(days), "used": len(days) - len(skipped),
                          "skipped": skipped, "skipped_by_reason": by_reason, "no_trade": no_trade},
             "report": rep}
@@ -182,6 +194,7 @@
     write_json(run_dir / "trades.json", trades)
     write_json(run_dir / "equity.json", report.equity(trades))
     write_json(run_dir / "plots.json", {"plots": plots, "hlines": hlines})
+    write_json(run_dir / "propsim.json", prop)
     write_json(run_dir / "run.json", meta)
     status.update(status="done", phase="done", done=len(days), updated=_now())
     write_json(run_dir / "status.json", status)
@@ -303,7 +316,8 @@
         if st.get("status") != "done":
             raise ValueError(f"run {rid} is {st.get('status')}, not done")
         return {"run": read_json(d / "run.json"), "trades": read_json(d / "trades.json"),
-                "equity": read_json(d / "equity.json"), "plots": read_json(d / "plots.json")}
+                "equity": read_json(d / "equity.json"), "plots": read_json(d / "plots.json"),
+                "propsim": read_json(d / "propsim.json")}
 
     def _loop(self) -> None:
         while True:
```

The runner calls `evaluate(..., n_paths=propsim.N_PATHS)` explicitly (not the default argument), so a test can shrink `N_PATHS` with `monkeypatch`.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/test_backtest_propsim.py tests/test_backtest_runner.py` → Expected: 16 passed.
Run: `.venv/bin/python -m pytest -q` → Expected: all green (412).

- [ ] **Step 7: Check the ≤ 3 s budget on a real ledger** (only if Task 7 Step 7 left a warm cache and bundles):

```bash
.venv/bin/python - <<'EOF'
import glob, json, time
from homebase.backtest.propsim import evaluate
f = sorted(glob.glob("homebase/.state/tester/runs/*/trades.json"))[-1]
t = time.time(); r = evaluate(json.load(open(f))); print(f, round(time.time() - t, 2), "s", r["headline"])
EOF
```

Expected: ≤ 3 s at 20,000 paths (planning measured 0.2–1.3 s on `nq930` ledgers). Nothing to commit from this step.

- [ ] **Step 8: Commit**

```bash
git add homebase/backtest/propsim homebase/backtest/runner.py tests/test_backtest_propsim.py
git commit -m "feat(tester): prop-eval pass rate on every run — vendored ONYX propsim, LucidFlex 50K rules, an unconfirmed Apex 50K placeholder, propsim.json in the bundle" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: The chart-service API

**Requirements:**
- A new module `homebase/charts/tester_api.py` exposes `make_router(write_ok, manager) -> APIRouter` (prefix `/api/tester`) and `tester_router(write_ok, archive, state=None)`. With `state=None` (production) it uses `homebase/.state/tester` and the `~/futures_derived/homebase_tape` cache. A test passes its tmp dir and gets the runs and the cache under it.
- Routes (all plain `def`, so they run in FastAPI's threadpool and never block the chart pump's loop):
  - `GET /strategies` → `catalog()`.
  - `GET /prop-rules` → `propsim.list_rules()` (`[{id, name, version, confirmed}]`).
  - `POST /run` → `{id}`: `write_ok(request)` first (403 cross-site), then 400 with the validation/discipline message.
  - `GET /run/{id}` → status (404 unknown).
  - `POST /run/{id}/cancel` → `write_ok` first; 409 if not cancellable.
  - `GET /run/{id}/bundle` → 409 until done; the bundle carries `propsim`.
  - `GET /runs` → newest first.
- `homebase/charts/server.py` gets exactly two added lines and nothing else (another branch edits this file):
  1. the import `from .tester_api import tester_router`, placed right before `from .tickfeed import TickFeed`;
  2. `app.include_router(tester_router(browser_write_ok, base, Path(state) / "tester" if state else None))`, placed right after the `known_root` helper, before `@app.get("/api/layouts")`.

  It reuses the closure `browser_write_ok` (the existing Origin check) and the service's own archive `base`.

**Files:**
- Create: `homebase/charts/tester_api.py`
- Modify: `homebase/charts/server.py` (+2 lines, see above)
- Test: `tests/test_tester_api.py`

**Interfaces:**
- Consumes: `RunManager`, `default_base` (Task 7), `propsim.list_rules` (Task 8), `CACHE` (Task 1), `strategies.catalog` (Task 3), `create_app(..., base=, state=)` and its `browser_write_ok` (existing).
- Produces: the seven routes above.

- [ ] **Step 1: Write the failing tests** — `tests/test_tester_api.py`:

```python
"""The tester routes on the chart service: schema list, run lifecycle, Origin check."""
from __future__ import annotations

import datetime as dt
import time

from fastapi.testclient import TestClient

from homebase.charts.server import create_app
from tests.backtest_util import D1, nq_archive

EVIL = {"origin": "https://evil.example"}
RUN = {"strategy": "nq930", "inputs": {"adx_gate": False},
       "range": {"kind": "custom", "start": "2024-03-01", "end": "2024-03-31"}}


def app(tmp_path):
    return create_app(roots=["NQ"], base=nq_archive(tmp_path / "ticks"), replay=D1, speed=1,
                      start_et=dt.time(9, 30), state=tmp_path / "state")


def poll(c, rid, s=30.0):
    t = time.monotonic() + s
    while time.monotonic() < t:
        st = c.get(f"/api/tester/run/{rid}").json()
        if st["status"] in ("done", "error", "cancelled"):
            return st
        time.sleep(0.05)
    raise AssertionError("run never finished")


def test_strategies_lists_the_schemas(tmp_path):
    with TestClient(app(tmp_path)) as c:
        got = {s["id"]: s for s in c.get("/api/tester/strategies").json()}
        assert set(got) == {"nq930", "ym930", "nq10am", "gc_nfpcpi"}
        assert got["nq930"]["inputs"][0]["key"] == "offset_pts"


def test_prop_rule_sets_are_listed_with_the_unconfirmed_flag(tmp_path):
    with TestClient(app(tmp_path)) as c:
        rules = {r["id"]: r for r in c.get("/api/tester/prop-rules").json()}
        assert rules["lucid-flex-50k@2026-08"]["confirmed"] is True
        assert rules["apex-50k@unconfirmed"]["confirmed"] is False
        r = c.post("/api/tester/run", json={**RUN, "prop_rules": "nope@1"})
        assert r.status_code == 400 and "prop_rules" in r.json()["detail"]


def test_a_run_goes_from_post_to_bundle(tmp_path):
    with TestClient(app(tmp_path)) as c:
        rid = c.post("/api/tester/run", json=RUN, headers={"origin": "http://localhost:8852"}).json()["id"]
        assert poll(c, rid)["status"] == "done"
        b = c.get(f"/api/tester/run/{rid}/bundle").json()
        assert b["run"]["coverage"]["skipped_by_reason"] == {"missing 13:00–16:00 ET": 1}
        assert len(b["trades"]) == 1 and b["equity"]["equity"] == [b["trades"][0]["net"]]
        assert b["propsim"]["rules"]["label"] == "LucidFlex 50K" and "headline" in b["propsim"]
        assert c.get("/api/tester/runs").json()[0]["id"] == rid
        assert (tmp_path / "state" / "tester" / "runs" / rid / "run.json").exists()


def test_writes_from_another_site_are_refused(tmp_path):
    with TestClient(app(tmp_path)) as c:
        assert c.post("/api/tester/run", json=RUN, headers=EVIL).status_code == 403
        assert c.get("/api/tester/runs").json() == []


def test_bad_requests_and_unknown_runs(tmp_path):
    with TestClient(app(tmp_path)) as c:
        r = c.post("/api/tester/run", json={**RUN, "range": {"kind": "custom", "start": "2025-01-02",
                                                               "end": "2025-02-01"}})
        assert r.status_code == 400 and "Holdout" in r.json()["detail"]
        assert c.post("/api/tester/run", json={**RUN, "strategy": "zz"}).status_code == 400
        assert c.get("/api/tester/run/20260926-120000-nq930-abcd").status_code == 404
        assert c.get("/api/tester/run/..%2F..%2Fetc").status_code == 404
        assert c.post("/api/tester/run/20260926-120000-nq930-abcd/cancel").status_code == 404
        rid = c.post("/api/tester/run", json=RUN).json()["id"]
        poll(c, rid)
        assert c.post(f"/api/tester/run/{rid}/cancel", headers=EVIL).status_code == 403
        assert c.post(f"/api/tester/run/{rid}/cancel").json()["status"] == "done"   # already final
```

- [ ] **Step 2: Run them to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_tester_api.py`
Expected: FAIL — the `/api/tester/*` routes do not exist yet (404s; `ModuleNotFoundError` once the import is added without the module).

- [ ] **Step 3: Implement** — `homebase/charts/tester_api.py`:

```python
"""The Strategy Tester's HTTP API on the chart service (:8852).

    GET  /api/tester/strategies          strategies with input schemas + defaults
    GET  /api/tester/prop-rules          prop-eval rule sets [{id, name, version, confirmed}]
    POST /api/tester/run                 {strategy, inputs, range, qty, commission,
                                          slippage_ticks, capital?, prop_rules?,
                                          holdout?: {reason}} -> {id}
    GET  /api/tester/run/{id}            status + progress
    POST /api/tester/run/{id}/cancel
    GET  /api/tester/run/{id}/bundle     run (meta + report + coverage), trades, equity, plots, propsim
    GET  /api/tester/runs                recent runs, newest first

Runs execute in a child process (homebase.backtest.runner), never in this process; and
every route is a plain `def`, so FastAPI runs it in its threadpool and
the chart pump's event loop never waits on disk. POSTs pass the service's Origin
check (browser_write_ok), passed in by create_app.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from fastapi import APIRouter, HTTPException, Request

from .. import strategies
from ..backtest import propsim
from ..backtest.runner import RunManager, default_base
from ..backtest.tape import CACHE


def make_router(write_ok: Callable[[Request], None], manager: RunManager) -> APIRouter:
    r = APIRouter(prefix="/api/tester")

    def known(rid: str):
        try:
            return manager.dir(rid)
        except KeyError:
            raise HTTPException(404, f"no run {rid!r}") from None

    @r.get("/strategies")
    def list_strategies():
        return strategies.catalog()

    @r.get("/prop-rules")
    def prop_rules():
        return propsim.list_rules()

    @r.post("/run")
    def start_run(request: Request, body: dict):
        write_ok(request)
        try:
            return {"id": manager.submit(body)}
        except ValueError as e:
            raise HTTPException(400, str(e)) from None

    @r.get("/run/{rid}")
    def run_status(rid: str):
        known(rid)
        return manager.status(rid)

    @r.post("/run/{rid}/cancel")
    def cancel_run(rid: str, request: Request):
        write_ok(request)
        known(rid)
        try:
            return manager.cancel(rid)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @r.get("/run/{rid}/bundle")
    def run_bundle(rid: str):
        known(rid)
        try:
            return manager.bundle(rid)
        except ValueError as e:
            raise HTTPException(409, str(e)) from None

    @r.get("/runs")
    def recent_runs():
        return manager.runs_list()

    return r


def tester_router(write_ok: Callable[[Request], None], archive: Path,
                  state: Path | None = None) -> APIRouter:
    """Production (state None): homebase/.state/tester + the ~/futures_derived tape
    cache. A test passes its tmp dir and gets the runs AND the cache under it."""
    base = Path(state) if state else default_base()
    return make_router(write_ok, RunManager(base, archive=archive,
                                            cache=base / "tape" if state else CACHE))
```

Then the two lines in `homebase/charts/server.py`. The resulting `git diff homebase/charts/server.py` must be exactly:

```diff
--- a/homebase/charts/server.py
+++ b/homebase/charts/server.py
@@ -34,6 +34,7 @@
 from .store import ARCHIVE, TickStore
 from .studies import make
 from .tick import SideClassifier, from_row
+from .tester_api import tester_router
 from .tickfeed import TickFeed
 
 STATIC = Path(__file__).resolve().parent.parent / "static"
@@ -430,6 +431,8 @@
             raise HTTPException(404, f"{root!r} is not a charted symbol")
         return r
 
+    app.include_router(tester_router(browser_write_ok, base, Path(state) / "tester" if state else None))
+
     @app.get("/api/layouts")
     async def get_layouts():
         return read_json(layouts_path)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/test_tester_api.py` → Expected: 5 passed.
Run: `.venv/bin/python -m pytest -q` → Expected: all green (281 existing + 136 new = 417); run it three times — the process tests must never flake, with `tests/test_charts_server.py` untouched and passing.
Run: `git diff --stat -- homebase/charts/server.py` → `1 file changed, 3 insertions(+)` (two code lines + one blank).
Run: `git status --short` → only this plan's files; no `config.json`, no `.state`, nothing under `~/futures_ticks` (verify with `find ~/futures_ticks -newer homebase/backtest/tape.py -type f | head` → empty).

- [ ] **Step 5: Commit**

```bash
git add homebase/charts/tester_api.py homebase/charts/server.py tests/test_tester_api.py
git commit -m "feat(charts): tester API — strategies, prop rule sets, run, status, cancel, bundle, recent runs; writes behind the Origin check" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

## Self-review (done while writing; kept for the executor)

- **Spec coverage.**
  - Strategy contract: metadata, input schema, `on_session`/`on_time`/`on_bar`, `stop_entry`/`limit_entry`/`market`/`oco`/`cancel`/`flatten`/`move_brackets_to_fill`, `plot`/`hline` → Tasks 2–3.
  - v1 strategies with parity tests against `config.json` geometry and `engine._legs` → Task 3.
  - `tape.py`: archive, front contract, cache, coverage → Task 1.
  - `engine.py`: house law, OCO/OSO, re-price, costs, scheduled cancel/flat, per-trade record → Task 2.
  - `report.py`: All/Long/Short, dollar metrics, Sharpe/Sortino/t-stat/expectancy, year and month tables, equity/drawdown → Task 5.
  - `runner.py`: separate process, progress, bundle files, one at a time, queue, cancel → Task 7.
  - Prop-eval pass rate (the spec's added section): vendored `propsim.py` + rules, the Apex set marked unconfirmed, `propsim.json` from the daily net P&L; tests for determinism, always-pass, always-bust, rule loading and the unconfirmed label → Task 8.
  - `discipline.py` → Task 6. API → Task 9.
  - Validation: golden → Task 4; unit fill-law cases → Task 2 (missing hour → Tasks 1 and 7); metrics → Task 5; discipline → Tasks 6–7; performance → Task 7 Step 7 (and ≤ 3 s propsim → Task 8 Step 7).
  - Out of scope, per the brief: the page/JS, grids, desk code edits. (Monte Carlo was out of scope in v1; the spec's added section brings in the prop-eval sim only — Task 8.)
- **Placeholders:** none. Every code step carries the full file, every command its expected output.
- **Type consistency:** these names are used identically across tasks: `Tape`/`TapeStore(archive, cache, min_ticks)`, `run_session(strategy, tape, costs, qty, daily)`, `Trade` field names (report and runner read `date, side, qty, entry_ns, exit_ns, net, commission, mfe_usd, mae_usd, seconds, bars`), `RunManager(base, archive=, cache=)`, `propsim.evaluate(trades, rule_id, n_paths=)`, `tester_router(write_ok, archive, state)`. The code was run end to end while planning, task by task in a fresh copy: 136 new tests green plus the existing 281 (417), stable across repeated full-suite runs.
