"""The tick-archive JOB: `python -m homebase.ticks` (homebase/ticks.py hands its command line to main() here). One run =
fetch and merge (homebase.ticks.record), the data watchdog (homebase.datawatch), the coverage report (homebase.tickcoverage),
or the manual Massive fill (homebase.tickmassive). The library it drives stays in homebase.ticks and is reached as T.<name>,
so a test that patches homebase.ticks (now_et, state_dir, record ...) patches the job too. Split out of ticks.py so the
watchdog, the report and the fill can import the library at the top without an import loop."""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import json
import time
from pathlib import Path

from . import datawatch, tickcoverage
from .. import paths
from . import ticks as T


REPORT_EVERY = dt.timedelta(hours=12)    # a run with nothing to do still refreshes the report this often


def coverage_report(roots, base: Path, sessions: int) -> None:
    """Write homebase/.state/tick_coverage.json -- every session classed (whole, filling, lost, vendor
    gap, not a hole), the data watchdog's last reading in it -- and log its summary line and what
    changed since the report before; a failure here is logged, never raised (the run's data is already
    written)."""
    try:
        tickcoverage.write_report(roots, base, T.now_et(), T.state_dir() / "tick_coverage.json", sessions,
                                  watch=datawatch.load(T.state_dir() / "data_watch.json") or None)
    except Exception as e:  # noqa: BLE001
        T.log(f"coverage report failed: {type(e).__name__}: {e}")


def data_watch(roots, base: Path, cache: dict) -> dict | None:
    """The data watchdog at the end of a run (homebase.datawatch: is the live feed late, thin or
    silent; refused merges; what is about to leave the broker): homebase/.state/data_watch.json and,
    while something is wrong, its line in this log. It only reads the archive. A failure here is
    logged, never raised (the run's data is already written)."""
    try:
        return datawatch.run(roots, base, T.now_et(), cache, T.state_dir() / "data_watch.json")
    except Exception as e:  # noqa: BLE001
        T.log(f"data watch failed: {type(e).__name__}: {e}")
        return None


def report_due(path: Path) -> bool:
    try:
        age = dt.datetime.now(T.UTC) - dt.datetime.fromtimestamp(path.stat().st_mtime, T.UTC)
    except OSError:
        return True
    return age >= REPORT_EVERY


def load_cache(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def prune_cache(cache: dict, now: dt.datetime, days: int = T.LIVE_LOOKBACK_DAYS + 5) -> None:
    """Forget files and sessions older than the live lookback (the cache only
    speeds up the runs; anything dropped is simply read again)."""
    cut = (now.astimezone(T.ET).date() - dt.timedelta(days=days)).isoformat()
    for k in [k for k in cache if not k.startswith("_") and (Path(k).name[:10] < cut or not Path(k).exists())]:
        del cache[k]
    for key in (T.ASKED, T.REFUSED, T.EMPTY_ONCE):
        d = cache.get(key, {})
        for k in [k for k in d if k.split(" ")[-1] < cut]:
            del d[k]


def fill_from_massive(a, roots, base: Path) -> int:
    from . import tickmassive                     # lazy: manual only (--fill-from-massive); the hourly job never loads it
    dates = [dt.date.fromisoformat(x.strip()) for x in a.dates.split(",") if x.strip()] if a.dates else None
    kw = dict(dates=dates, since=dt.date.fromisoformat(a.since), include_fetchable=a.include_fetchable,
              raw=Path(a.raw_dir))
    try:
        if a.dry_run:
            tickmassive.fill(roots, base, T.now_et(), dry_run=True, **kw)
            return 0
        with T.archive_lock(T.state_dir() / "ticks.lock"):
            tickmassive.fill(roots, base, T.now_et(), **kw)
            coverage_report(roots, base, a.sessions)
    except Exception as e:  # noqa: BLE001 — Refused, the lock, the network: said, never a key in it
        T.log(f"massive: {type(e).__name__}: {e}")
        return 1
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=T.__doc__.split("\n")[0])
    ap.add_argument("--date", help="one session date YYYY-MM-DD (default: every "
                                   "complete session in the last 3 days)")
    ap.add_argument("--roots", default=",".join(T.ROOTS))
    ap.add_argument("--dir", default=str(T.ARCHIVE))
    ap.add_argument("--coverage", action="store_true",
                    help="only write homebase/.state/tick_coverage.json (no market data)")
    ap.add_argument("--rescan", action="store_true",
                    help="write each recent front-month file's hour-by-hour coverage into its "
                         "manifest (data files untouched), then the report (no market data)")
    ap.add_argument("--sessions", type=int, default=30, help="sessions per root the report covers")
    ap.add_argument("--full", action="store_true",
                    help="by day too, without the per-run page caps (the Refresh data button); it still stops "
                         "when the live login's hour is spent")
    fm = ap.add_argument_group("Massive gap-fill (manual, off by default; homebase.tickmassive)")
    fm.add_argument("--fill-from-massive", action="store_true",
                    help="fill the archive from Massive flat files (env MASSIVE_S3_KEY / MASSIVE_S3_SECRET)")
    fm.add_argument("--holes", action="store_true",
                    help="every session since --since the coverage check finds missing or holed, "
                         "once the broker no longer has it")
    fm.add_argument("--dates", help="these session dates instead, YYYY-MM-DD[,YYYY-MM-DD...]")
    fm.add_argument("--since", default="2026-09-22", help="--holes: the first session to look at")
    fm.add_argument("--include-fetchable", action="store_true",
                    help="--holes: also what the broker's history still has")
    fm.add_argument("--dry-run", action="store_true",
                    help="list every file, hour and MB it would touch; download and write nothing")
    fm.add_argument("--raw-dir", default=str(paths.massive_raw()),
                    help="Massive's raw files, kept here (research/massive_ticks.py's layout)")
    a = ap.parse_args(argv)
    roots = tuple(r.strip().upper() for r in a.roots.split(",") if r.strip())
    base = Path(a.dir)
    if a.coverage:
        coverage_report(roots, base, a.sessions)
        return 0
    if a.fill_from_massive:
        if a.holes == bool(a.dates):
            ap.error("--fill-from-massive needs exactly one of --holes or --dates")
        return fill_from_massive(a, roots, base)
    if a.rescan:
        try:
            with T.archive_lock(T.state_dir() / "ticks.lock"):
                n = tickcoverage.rescan(roots, base, T.now_et(), a.sessions)
                T.log(f"rescan: {n} manifest(s) rewritten with their hour-by-hour coverage")
                coverage_report(roots, base, a.sessions)
        except T.Busy as e:
            T.log(str(e))
            return 1
        return 0
    return run(roots, [dt.date.fromisoformat(a.date)] if a.date else None, base, a.sessions, full=a.full)


def _wait_for_token(left: float, poll_s: float, sleep) -> tuple[bool, float]:
    """Poll the token files (a read of the disk -- never a login) every poll_s until one
    is valid or `left` seconds are used up. (found, seconds left)."""
    while left > 0:
        sleep(poll_s)
        left -= poll_s
        if T._valid_md_tokens(T.config_mod.load(unknown="ignore").accounts.items()):
            return True, left
    return False, 0.0


def run(roots, dates, base: Path, sessions: int = 30, *, sleep=time.sleep,
        token_wait_s: float = T.TOKEN_WAIT_S, token_poll_s: float = T.TOKEN_POLL_S, full: bool = False) -> int:
    """One run of the job (launchd: hourly, on load, 17:20 and 05:30): fetch
    and merge whatever is missing (record), then the data watchdog (data_watch),
    then the coverage report when the run changed something or the last report
    is REPORT_EVERY old. Silent when there is nothing to do and the data is
    fine; a run already in progress (the lock) is left to it. A run that fails ONLY for want of a valid md token
    (it ran right after a wake, before the desk reconnected and wrote one) waits for the
    token and retries within itself, every token_poll_s for up to token_wait_s, then gives
    up quietly until the next run; it never logs in. A click (full) that gives up so exits
    NO_TOKEN_EXIT, for the Refresh data button to say why nothing was fetched."""
    cache_path = T.state_dir() / "tick_runs.json"
    rc, no_token = 0, False
    try:
        with T.archive_lock(T.state_dir() / "ticks.lock"):
            cache = load_cache(cache_path)
            written: list = []
            try:
                left = token_wait_s
                while True:
                    try:
                        written += asyncio.run(T.record(roots, dates, base, cache=cache,
                                                      charts_usage=T.state_dir() / "charts" / "md_usage.json",
                                                      full=full))
                        break
                    except T.NoMdToken as ex:
                        written += ex.written
                        if left == token_wait_s:
                            T.log(f"no valid md token on disk yet — waiting for the desk "
                                f"(looking every {token_poll_s:g} s for up to {token_wait_s / 60:g} min)")
                        found, left = _wait_for_token(left, token_poll_s, sleep)
                        if not found:
                            T.log("still no valid md token — the desk is not connected; "
                                "nothing fetched, the next run tries again")
                            no_token = True
                            break
            except Exception as e:  # noqa: BLE001
                T.log(f"run failed: {type(e).__name__}: {e}")
                rc = 1
            finally:
                data_watch(roots, base, cache)    # before the cache is saved: what it read of the files is kept
                try:
                    prune_cache(cache, T.now_et())
                    T.tickarchive.atomic_write(cache_path, json.dumps(cache).encode())
                except OSError as e:
                    T.log(f"could not save {cache_path.name}: {e}")
                # a click (full) always: the button shows the report's numbers, so they must be this run's
                if written or rc or full or report_due(T.state_dir() / "tick_coverage.json"):
                    coverage_report(roots, base, sessions)
    except T.Busy:
        return 0                                  # the run in progress does the work
    return T.NO_TOKEN_EXIT if no_token and full and not rc else rc
