"""The user's data rules: what a tester range MEANS, and the record of what it read.

  * The dates are the house blueprint's (research/edge-library/BLUEPRINT.md, section 2;
    law since 2026-10-05). BUILD days = 2021-09-22 -> 2025-06-30: all tuning happens
    here. TEST days = 2025-07-01 -> the latest data: read once, only for a locked strategy.
  * Ranges: "research" = the build days (the default; the name is older than the
    blueprint and stays, because every stored run carries it); "is_months" = only
    Jan/Apr/Jul/Oct sessions (inside the build days unless start/end say otherwise);
    "custom" = start/end as given. A request already on disk runs the dates it was
    stored with (stored_range), not today's default.
  * NOTHING here refuses a range for reading late data any more (2026-09-27, the
    user's instruction: "remove all of it"). Every preset and every custom range
    runs. A range that is malformed -- a bad date, a start after its end, an
    unknown kind -- still fails, because it is not a range at all.
  * A range reaching the test days (2025-07-01 or later) is still RECORDED: record()
    appends {ts, strategy, inputs, range[, run_id]} to spends.jsonl when the run is
    accepted, so past results stay attributable. The log is WRITE-ONLY -- it is
    never read back to gate a run or to raise a prompt, and record()'s return
    value is ignored by every caller. The app never edits the vault: the assistant
    folds spends into the burned-data ledger note.
"""
from __future__ import annotations

import datetime as dt
import json
import os
from dataclasses import dataclass
from pathlib import Path

RESEARCH_START = dt.date(2021, 9, 22)       # the build days: from the archive's first session ...
RESEARCH_END = dt.date(2025, 6, 30)
HOLDOUT_START = dt.date(2025, 7, 1)         # ... and the test days, from here to the latest data
IS_MONTHS = (1, 4, 7, 10)
KINDS = ("research", "is_months", "custom")


class DisciplineError(ValueError):
    """A range that is not a range (a bad date, an unknown kind). The message is shown to the user."""


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
            return "Build · Sep 2021 – Jun 2025"
        if self.kind == "custom" and self.start == HOLDOUT_START:
            return f"Test · Jul 2025 → {self.end.isoformat()}"
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


def stored_range(obj) -> Range:
    """A range read back from a request.json (to_dict()'s shape). A "research" range keeps the dates
    it was stored with, whatever the build days are in today's code: a request written when the
    default was 2021-01-01 -> 2024-12-31 (before 2026-10-06, or by a chart service still running
    that code) runs exactly the days its label names."""
    rng = parse_range(obj)
    if rng.kind == "research" and obj and obj.get("start") and obj.get("end"):
        own = parse_range({"kind": "custom", "start": obj["start"], "end": obj["end"]})
        return Range(rng.kind, own.start, own.end)
    return rng


def record(path: Path, *, strategy: str, inputs: dict, rng: Range, run_id: str | None = None,
           ts: str | None = None) -> dict | None:
    """Append ONE spend line (never rewrites, never refuses) when `rng` reaches
    the test days (2025-07-01 or later); None when it ends before them. `run_id`, when
    given, lets a later caller (execute()'s dedup) recognize a spend it already logged
    for this run — it is left out of the record entirely when not given, matching every
    spend logged before run ids existed.

    The return value is a courtesy: every caller ignores it. This log records, it does
    not gate — nothing reads it back to decide whether a run may proceed."""
    if not rng.holdout:
        return None
    rec = {"ts": ts or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "strategy": strategy, "inputs": inputs, "range": rng.to_dict()}
    if run_id is not None:
        rec["run_id"] = run_id
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
