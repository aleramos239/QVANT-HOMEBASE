"""The daily match: did the Desk's shadow day equal the backtest of that day? (2026-10-09)

After a strategy's session ends, the tester runs the SAME frozen code on that day's RECORDED prices, and the day
summary gets `match = {"ok": bool | None, "text": str}`. It is a parity check of the runner, not a result: it never
shows the tester's P&L or metrics, only "matched" or the first difference. ok None = not checked yet (the day's prices
are not stored yet, the tester is busy, ...); the runner (labrun/host.py) tries again later.

    compare       two lists of trades (the engine's Trade.to_dict() rows) -> the verdict (pure)
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
from pathlib import Path

from ..backtest import drafthost, runner, sandbox
from ..backtest.slots import Slots
from ..backtest.tape import ET, et_ns
from ..contracts import tick_size

TIME_NS = 2_000_000_000          # two trades agree on a time within this
TICKS = 2                        # ... and on a price within this many ticks
EPS = 1e-9                       # (64.01 + 0.02 is not 64.03)


class MatchUnavailable(Exception):
    """The day cannot be checked yet; str(e) is the reason in plain words."""


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


def _unavailable(run: dict) -> str | None:
    """Why a finished run says the day was not read, in plain words (None: it was read)."""
    cov = run.get("coverage") or {}
    skipped = cov.get("skipped") or []
    if not cov.get("sessions") or any(s.get("reason") == "no tape" for s in skipped):
        return "the day's prices are not stored yet"
    return "the stored prices for the day have a gap" if skipped else None


def tester_day(record: dict, date, *, base: Path, archive, cache, python: str, timeout_s: float = 600,
               slots: Slots | None = None, launch=None) -> list[dict]:
    """The tester on that ONE day with the record's frozen source, settings and size, as a draft backtest runs: the
    child in the macOS sandbox, holding one of the machine's backtest slots. Its run folder lives under `base`
    (never in the Lab's own runs folder). Returns the day's trades as the engine's rows. MatchUnavailable when the day
    cannot be read yet (no prices, a gap), no slot is free, the sandbox is not working, the run takes longer than
    `timeout_s` (it is stopped) or fails. launch: runner.launch (the tests', a stand-in)."""
    d = date if isinstance(date, dt.date) else dt.date.fromisoformat(date)
    name, launch = record["name"], launch or runner.launch
    slot = (slots or Slots()).try_acquire()
    if slot is None:                                 # none free, or the 09:20-09:35 window
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
            if run_dir is not None:
                shutil.rmtree(run_dir, ignore_errors=True)
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
        except ValueError:                           # the run's status is not `done`; its folder stays for a look
            raise MatchUnavailable("the backtest could not run") from None
        why = _unavailable(got["run"] or {})
        if why:
            shutil.rmtree(run_dir, ignore_errors=True)
            raise MatchUnavailable(why)
        shutil.rmtree(run_dir, ignore_errors=True)
        return [{**{k: v for k, v in t.items() if k not in ("entry_ms", "exit_ms")},
                 "entry_ns": t["entry_ms"] * 1_000_000, "exit_ns": t["exit_ms"] * 1_000_000} for t in got["trades"] or []]
    finally:
        slot.close()
        if proc is not None:
            runner.finish_proc(proc)


def match_day(record: dict, date, shadow_trades: list[dict], **kw) -> dict:
    """The day's verdict: compare(shadow_trades, tester_day(record, date, **kw)). A day that cannot be read yet is
    {"ok": None, "text": "Not checked yet: <why>."}."""
    try:
        return compare(shadow_trades, tester_day(record, date, **kw), tick_size(record["root"]))
    except MatchUnavailable as e:
        return {"ok": None, "text": f"Not checked yet: {e}."}
