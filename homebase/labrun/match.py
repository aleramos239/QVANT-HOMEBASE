"""The daily match: did the Desk's shadow day equal the backtest of that day? (2026-10-09)

After a strategy's session ends, the tester runs the SAME frozen code on that day's RECORDED prices, and the day
summary gets `match = {"ok": bool | None, "text": str}`. It is a parity check of the runner, not a result: it never
shows the tester's P&L or metrics, only "matched" or the first difference. ok None = not checked yet (the day's prices
are not stored yet, the tester is busy, ...); the runner (labrun/host.py) tries again later.

    compare       two lists of trades (the engine's Trade.to_dict() rows) -> the verdict (pure)
    stored        is the day's recording merged into the archive yet? (its manifest lists a `live` source)
    from_summary  a day summary's trade rows -> those rows, for a day read back from its file
    tester_day    the tester on one day, in the sandbox a draft backtest runs in, the way the chart service launches it
    match_day     compare(shadow, tester_day(...)); a day that cannot be read yet becomes "Not checked yet: ..."

Nothing here places an order or talks to a service. The backtest child is the tester's own (backtest/runner.py).
"""
from __future__ import annotations

import datetime as dt
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .. import tickarchive
from ..backtest import drafthost, runner, sandbox
from ..backtest.slots import Slots
from ..backtest.tape import ET, TapeStore, et_ns
from ..contracts import tick_size

TIME_NS = 2_000_000_000          # two trades agree on a time within this
TICKS = 2                        # ... and on a price within this many ticks
EPS = 1e-9                       # (64.01 + 0.02 is not 64.03)
KEEP_RUNS_S = 7 * 86400          # a run folder left behind (the runner went away mid-run) is cleaned after this
SLOT_WAIT_S = 20 * 60            # the longest the check waits in line for one of the machine's backtest slots
PENDING = "Not checked yet"      # the start of every text that is asked again later


class MatchUnavailable(Exception):
    """The day cannot be checked yet; str(e) is the reason in plain words."""


class StrategyFailed(Exception):
    """The strategy raised in the backtest of that day: the Desk's day and the tester's cannot be the same."""


class DoesNotTrade(Exception):
    """The day is recorded but the strategy does not trade it (its trades_on says no): nothing to check."""


def _hms(ns: int) -> str:
    return dt.datetime.fromtimestamp(ns // 1_000_000_000, ET).strftime("%H:%M:%S")


def _px(v: float, tick: float) -> str:
    digits = max(2, len(f"{tick:.10f}".rstrip("0").split(".")[1]))
    return f"{v:,.{digits}f}"


def _differs(a: dict, b: dict, tick: float) -> tuple[str, str, str] | None:
    """The first field two trades disagree on, in the order the owner reads a trade: (field, desk, backtest)."""
    far = TICKS * tick + EPS
    checks = (("side", a["side"], b["side"], a["side"] != b["side"], str),
              ("size", a["qty"], b["qty"], a["qty"] != b["qty"], str),
              ("entry time", a["entry_ns"], b["entry_ns"], abs(a["entry_ns"] - b["entry_ns"]) > TIME_NS, _hms),
              ("entry price", a["entry_price"], b["entry_price"], abs(a["entry_price"] - b["entry_price"]) > far,
               lambda v: _px(v, tick)),
              ("exit time", a["exit_ns"], b["exit_ns"], abs(a["exit_ns"] - b["exit_ns"]) > TIME_NS, _hms),
              ("exit price", a["exit_price"], b["exit_price"], abs(a["exit_price"] - b["exit_price"]) > far,
               lambda v: _px(v, tick)),
              ("exit", a["exit_reason"], b["exit_reason"], a["exit_reason"] != b["exit_reason"], str))
    for field, desk, tester, no, say in checks:
        if no:
            return field, say(desk), say(tester)
    return None


def compare(shadow: list[dict], tester: list[dict], tick: float) -> dict:
    """The verdict on two days' trades, in order. Two trades agree when side, size and exit reason are equal, the
    times are within 2 s and the prices within 2 ticks."""
    if not shadow and not tester:
        return {"ok": True, "text": "No trades, same as the backtest."}
    if len(shadow) != len(tester):
        one = "trade" if len(tester) == 1 else "trades"
        return {"ok": False, "text": f"Did not match: the backtest took {len(tester)} {one}, the Desk {len(shadow)}."}
    for n, (a, b) in enumerate(zip(shadow, tester), 1):
        got = _differs(a, b, tick)
        if got:
            return {"ok": False, "text": f"Did not match at trade {n}: {got[0]} {got[1]} on the Desk, {got[2]} in the backtest."}
    return {"ok": True, "text": f"Matched the backtest: {len(shadow)} of {len(shadow)} {'trade' if len(shadow) == 1 else 'trades'}."}


def from_summary(trades: list[dict], date) -> list[dict]:
    """A day summary's trade rows (HH:MM:SS to the second) as the engine's rows: for a day read back from its file."""
    d = date if isinstance(date, dt.date) else dt.date.fromisoformat(date)
    return [{"side": t["side"], "qty": t["qty"], "entry_ns": et_ns(d, t["entry_t"]), "entry_price": t["entry_px"],
             "exit_ns": et_ns(d, t["exit_t"]), "exit_price": t["exit_px"], "exit_reason": t["reason"]} for t in trades]


def retry(verdict: dict) -> bool:
    """True for a verdict that is only "not checked yet": the runner asks again. A day that is not checked for good
    (stopped, does not trade) and a real answer are not."""
    return verdict.get("ok") is None and str(verdict.get("text")).startswith(PENDING)


def _log(msg: str) -> None:
    print(f"[labrun] match: {msg}", file=sys.stderr, flush=True)


def drop(run_dir, base) -> None:
    """Remove one run folder -- only when it is a real folder directly inside <base>/runs (never the runs folder
    itself, a link, or anything outside it)."""
    runs, d = Path(base).resolve() / "runs", Path(run_dir)
    if d.is_symlink() or d.parent.resolve() != runs or not d.is_dir():
        return
    shutil.rmtree(d, ignore_errors=True)


def clean(base, now: float | None = None) -> None:
    """Remove the run folders in <base>/runs that are older than a week (a run the runner never got to remove)."""
    runs = Path(base) / "runs"
    now = time.time() if now is None else now
    try:
        found = list(runs.iterdir())
    except OSError:
        return
    for d in found:
        try:
            if d.is_dir() and not d.is_symlink() and now - d.stat().st_mtime > KEEP_RUNS_S:
                drop(d, base)
        except OSError:
            continue


def stored(root: str, d: dt.date, archive, cache) -> bool:
    """The archive holds the day: the manifest of its file lists a `live` source. The tick job merges the day's
    recording (the chart service's .live.csv.gz) into the archive file after the close and logs every merge in the
    manifest's `sources` (tickarchive.merge_session); a file with no `live` source yet is a fragment -- an hourly
    fill -- and a backtest of it is not a backtest of the day. Read only."""
    got = TapeStore(archive, cache).pick(root, d)
    if got is None:
        return False
    sources = tickarchive.load_manifest(got[0]).get("sources")
    return isinstance(sources, list) and any(isinstance(x, dict) and x.get("kind") == "live" for x in sources)


def _unavailable(run: dict, recorded: bool) -> str | None:
    """Why a finished run did not really read the day, in plain words (None: it did). recorded: the archive holds the
    day. A strategy that raised is not a reason, it is raised as StrategyFailed (and a day it does not trade as
    DoesNotTrade)."""
    cov = run.get("coverage") or {}
    skipped = cov.get("skipped") or []
    if not cov.get("sessions") and recorded and not skipped:
        raise DoesNotTrade
    if not cov.get("sessions") or any(s.get("reason") == "no tape" for s in skipped):
        return "the day's prices are not stored yet"
    if skipped:
        return "the stored prices for the day have a gap"
    reasons = [str(n.get("reason")) for n in cov.get("no_trade") or []]
    if any(r.startswith("strategy error") for r in reasons):
        raise StrategyFailed
    if any(r.startswith(runner.HOLE_REASONS) for r in reasons):
        return "the day's prices have a gap"
    return None


def tester_day(record: dict, date, *, base: Path, archive, cache, python: str, timeout_s: float = 600,
               slots: Slots | None = None, launch=None, slot_wait_s: float = SLOT_WAIT_S) -> list[dict]:
    """The tester on that ONE day with the record's frozen source, settings and size, as a draft backtest runs: the
    child in the macOS sandbox, holding one of the machine's backtest slots. Its run folder lives under `base`
    (never in the Lab's own runs folder) and is removed when the run is read or has failed. Returns the day's trades as
    the engine's rows. MatchUnavailable when the day cannot be read yet (its recording is not in the archive yet
    (stored), a gap, a missing print at a fire time), no slot came free in `slot_wait_s`, the sandbox is not working,
    the run takes longer than `timeout_s` (it is stopped) or fails; StrategyFailed when the strategy raised that day;
    DoesNotTrade when it does not trade that day. It WAITS in line for its slot (the caller is a worker thread), and
    the line never lets a backtest start 09:20-09:35 ET on a weekday. launch: runner.launch (the tests', a stand-in)."""
    d = date if isinstance(date, dt.date) else dt.date.fromisoformat(date)
    name, launch = record["name"], launch or runner.launch
    if not stored(record["root"], d, archive, cache):    # before a slot is asked for: nothing to run yet
        raise MatchUnavailable("the day's prices are not stored yet")
    end = time.monotonic() + slot_wait_s
    slot = (slots or Slots()).acquire(lambda: time.monotonic() >= end)
    if slot is None:                                 # none came free in time (or the 09:20-09:35 window outlasted it)
        raise MatchUnavailable("the tester is busy")
    run_dir = proc = None
    try:
        body = {"strategy": record["id"], "inputs": record.get("params") or {}, "qty": record.get("qty") or 1,
                "range": {"kind": "custom", "start": d.isoformat(), "end": d.isoformat()}}
        try:
            stub = drafthost.stub_class(name, record["source"])
            run_dir = Path(base) / "runs" / runner.prepare(body, Path(base), draft=(stub, record["source"]))
            proc = launch(run_dir, python, archive, cache, slot, ("--no-lock",))
        except (ValueError, OSError) as e:           # a draft that cannot be read, a child that cannot start
            if isinstance(e, sandbox.SandboxUnavailable):
                raise MatchUnavailable("the sandbox is not working") from None
            raise MatchUnavailable("the backtest could not run") from None
        try:
            proc.wait(timeout=timeout_s)
        except subprocess.TimeoutExpired:
            runner.stop_proc(proc)
            raise MatchUnavailable("the backtest took too long") from None
        try:
            got = runner.read_bundle(run_dir)
        except ValueError:
            err = (runner.read_json(run_dir / "status.json", {}) or {}).get("error")
            _log(f"{name} {d}: the run failed: {str(err)[-300:]}")
            raise MatchUnavailable("the backtest could not run") from None
        recorded = bool(TapeStore(archive, cache).sessions(record["root"], d, d))
        why = _unavailable(got["run"] or {}, recorded)
        if why:
            raise MatchUnavailable(why)
        return [{**{k: v for k, v in t.items() if k not in ("entry_ms", "exit_ms")},
                 "entry_ns": t["entry_ms"] * 1_000_000, "exit_ns": t["exit_ms"] * 1_000_000} for t in got["trades"] or []]
    finally:
        slot.close()
        if proc is not None:
            runner.finish_proc(proc)
        if run_dir is not None:
            drop(run_dir, base)


def match_day(record: dict, date, shadow_trades: list[dict], **kw) -> dict:
    """The day's verdict: compare(shadow_trades, tester_day(record, date, **kw)). A day that cannot be read yet is
    {"ok": None, "text": "Not checked yet: <why>."}; a strategy that raised in the backtest never matches; a day it
    does not trade is not checked, for good."""
    try:
        return compare(shadow_trades, tester_day(record, date, **kw), tick_size(record["root"]))
    except MatchUnavailable as e:
        return {"ok": None, "text": f"{PENDING}: {e}."}
    except StrategyFailed:
        return {"ok": False, "text": "Did not match: the strategy failed in the backtest."}
    except DoesNotTrade:
        return {"ok": None, "text": "Not checked: it does not trade that day."}
