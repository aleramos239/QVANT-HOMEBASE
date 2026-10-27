"""JSON files read forgivingly and written whole."""
from __future__ import annotations

import json
from pathlib import Path

from . import atomic


def read_json(path: Path, default=None):
    """The file's JSON, or `default` when it is missing, unreadable or not JSON."""
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return default


def read_dict(path: Path) -> dict:
    """The file's JSON object, or {} when it is missing, unreadable, not JSON or not an object."""
    v = read_json(path)
    return v if isinstance(v, dict) else {}


def write_json(path: Path, data) -> None:
    """Compact JSON (what json cannot encode goes in as str), written whole via <name>.<pid>.tmp."""
    atomic.write_text(path, json.dumps(data, separators=(",", ":"), default=str))
