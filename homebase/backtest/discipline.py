"""The user's data rules: what a tester range MEANS, and the record of what it read.

  * Ranges: "research" = the research window 2021-01-01 -> 2024-12-31 (the
    default); "is_months" = only Jan/Apr/Jul/Oct sessions (inside the research
    window unless start/end say otherwise); "custom" = start/end as given.
  * NOTHING here refuses a range for reading late data any more (2026-09-27, the
    user's instruction: "remove all of it"). Every preset and every custom range
    runs. A range that is malformed -- a bad date, a start after its end, an
    unknown kind -- still fails, because it is not a range at all.
  * A range reaching 2025-01-01 or later is still RECORDED: record() appends
    {ts, strategy, inputs, range[, run_id]} to spends.jsonl when the run is
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

RESEARCH_START = dt.date(2021, 1, 1)
RESEARCH_END = dt.date(2024, 12, 31)
HOLDOUT_START = dt.date(2025, 1, 1)
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


def record(path: Path, *, strategy: str, inputs: dict, rng: Range, run_id: str | None = None,
           ts: str | None = None) -> dict | None:
    """Append ONE spend line (never rewrites, never refuses) when `rng` reaches
    2025-01-01 or later; None when it stays inside the research data. `run_id`, when
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
