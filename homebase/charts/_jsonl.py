"""Tiny atomic JSONL helpers shared by news.py and bursts.py: append one
line, read every line back, or rewrite the whole file -- always via a temp
file + `os.replace`, so a crash or a full disk mid-write can never leave a
torn line for the next reader."""
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
    """One more line, atomically (temp file with the file's prior content
    plus the new line, then rename)."""
    line = json.dumps(obj)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    prior = path.read_text() if path.exists() else ""
    tmp.write_text(prior + line + "\n")
    os.replace(tmp, path)


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
