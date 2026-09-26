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
                 run_id: str | None = None, ts: str | None = None) -> dict:
    """Append ONE spend line (never rewrites). `run_id`, when given, lets a later
    caller (execute()'s Item 5 dedup) recognize a spend it already logged for this
    run — it is left out of the record entirely when not given, matching every
    spend logged before Item 5 existed."""
    rec = {"ts": ts or dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "strategy": strategy, "inputs": inputs, "range": rng.to_dict(), "reason": reason}
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
