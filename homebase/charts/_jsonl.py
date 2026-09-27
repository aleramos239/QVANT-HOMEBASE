"""Tiny JSONL helpers shared by news.py and bursts.py: append one line, read
every line back, or rewrite the whole file.

`append()` is a true O(1) append (open in append mode, write one line,
flush) -- it must never rewrite the whole file: these run under a caller's
lock or on a hot tick path, and an O(n) rewrite per line would turn either
into an O(n^2) growth or (worse) block a reader for as long as the file
takes to rewrite. `write_all()`/`write_json()` genuinely replace the whole
file (a burst's `near_news` update, state.json), so those stay atomic via a
temp file + `os.replace`, which a single small append does not need."""
from __future__ import annotations

import json
import os
from pathlib import Path

DAY_FILE_RE = r"^\d{4}-\d{2}-\d{2}\.jsonl$"     # anchored: never matches another prefix's file


def read_all(path: Path) -> list[dict]:
    out = []
    try:
        text = path.read_text()
    except OSError:
        return out
    for line in text.splitlines():
        try:
            v = json.loads(line)
        except ValueError:
            continue
        if isinstance(v, dict):
            out.append(v)
    return out


def write_all(path: Path, objs: list[dict]) -> None:
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text("".join(json.dumps(o) + "\n" for o in objs))
    os.replace(tmp, path)


def append(path: Path, obj: dict) -> None:
    """One more line, in O(1): open in append mode, write it, flush. Never
    reads or rewrites the file's existing content."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj) + "\n")
        f.flush()


def write_json(path: Path, data: dict) -> None:
    """Same atomic pattern for a single JSON object (state files)."""
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data))
    os.replace(tmp, path)


def read_json(path: Path) -> dict:
    try:
        v = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return v if isinstance(v, dict) else {}
