"""Old tester output, pruned. Nothing in the app ever deleted a run, heat map or walk-forward folder, so
homebase/.state/tester grew to 11 GB (776 runs, 242 grids) and the lists the Lab loads grew with it.

    python -m homebase.backtest.prune                 # a dry run: what would go, how many GB
    python -m homebase.backtest.prune --days 7 --yes  # delete it

A folder goes only when ALL hold: older than --days (its newest file), not queued/running, and its id is
named nowhere under ~/.homebase (the Desk's Lab strategies, groups, pipeline book, arsenal, ideas) or the chart
service's own saved state. The spends record is the test-days ledger and is never lost: tester/spends.jsonl
is not touched, and a folder that holds a spends.jsonl of its own (a walk-forward's) has its lines appended to it
first.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import time
from pathlib import Path

from ..paths import state_dir

KINDS = ("runs", "grids", "walkforward")
ID = re.compile(r"\d{8}-\d{6}-[A-Za-z0-9_]+-[0-9a-f]{4}")
LIVE = ("queued", "running", "paused")


def referenced(roots: list[Path], skip_names: tuple[str, ...] = ("cache", ".git")) -> set[str]:
    """Every run / grid / walk-forward id written in a .json / .jsonl / .md / .txt file under `roots`."""
    found: set[str] = set()
    for root in roots:
        files = [root] if root.is_file() else (p for p in root.rglob("*") if p.is_file()) if root.exists() else ()
        for p in files:
            if p.suffix not in (".json", ".jsonl", ".md", ".txt") or any(s in p.parts for s in skip_names):
                continue
            try:
                if p.stat().st_size > 50_000_000:
                    continue
                found.update(ID.findall(p.read_text(errors="ignore")))
            except OSError:
                continue
    return found


def _newest(d: Path) -> float:
    t = d.stat().st_mtime
    for p in d.rglob("*"):
        try:
            t = max(t, p.stat().st_mtime)
        except OSError:
            pass
    return t


def _size(d: Path) -> int:
    n = 0
    for p in d.rglob("*"):
        try:
            if p.is_file() and not p.is_symlink():
                n += p.stat().st_size
        except OSError:
            pass
    return n


def _status(d: Path) -> str:
    import json
    for name in ("status.json", "grid.json", "wf.json", "walkforward.json"):
        try:
            return str(json.loads((d / name).read_text()).get("status", ""))
        except (OSError, ValueError, AttributeError):
            continue
    return ""


def candidates(tester: Path, refs: set[str], days: float, now: float | None = None) -> list[tuple[str, Path, int, float]]:
    """[(kind, dir, bytes, age_days)] of the folders that may go, oldest first."""
    now = time.time() if now is None else now
    out = []
    for kind in KINDS:
        base = tester / kind
        if not base.is_dir():
            continue
        for d in base.iterdir():
            if not d.is_dir() or d.name in refs or _status(d) in LIVE:
                continue
            age = (now - _newest(d)) / 86400
            if age > days:
                out.append((kind, d, _size(d), age))
    return sorted(out, key=lambda c: -c[3])


def keep_spends(d: Path, ledger: Path) -> int:
    """Move a folder's own spends lines (a walk-forward keeps its own) into the shared ledger. Returns the lines moved."""
    try:
        lines = [ln for ln in (d / "spends.jsonl").read_text().splitlines() if ln.strip()]
    except OSError:
        return 0
    if lines:
        with open(ledger, "a") as fh:
            fh.write("\n".join(lines) + "\n")
    return len(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--days", type=float, default=7.0, help="keep anything touched within this many days (default 7)")
    ap.add_argument("--yes", action="store_true", help="delete (the default is a dry run)")
    ap.add_argument("--home", type=Path, default=Path.home() / ".homebase")
    a = ap.parse_args(argv)
    tester = state_dir() / "tester"
    refs = referenced([a.home, state_dir() / "charts", state_dir() / "journal.jsonl", state_dir() / "config.json"])
    cands = candidates(tester, refs, a.days)
    by: dict[str, list[int]] = {}
    for kind, _, size, _ in cands:
        by.setdefault(kind, []).append(size)
    for kind in KINDS:
        v = by.get(kind, [])
        print(f"{kind:12s} {len(v):4d} folders  {sum(v) / 1e9:6.2f} GB")
    print(f"{'total':12s} {len(cands):4d} folders  {sum(c[2] for c in cands) / 1e9:6.2f} GB"
          f"  (older than {a.days:g} days, unreferenced, not running; {len(refs)} ids are referenced and kept)")
    if not a.yes:
        print("dry run: add --yes to delete")
        return 0
    moved = 0
    for _, d, _, _ in cands:
        moved += keep_spends(d, tester / "spends.jsonl")
        shutil.rmtree(d, ignore_errors=True)
    print(f"deleted ({moved} test-days spend lines kept in spends.jsonl)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
