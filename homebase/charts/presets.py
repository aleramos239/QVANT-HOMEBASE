"""Generic named presets for the charts page (2026-09-27 draw-tools plan): one JSON file, presets
grouped by "kind" (e.g. "drawing:trend", "indicator:rsi"), each kind a dict of name -> JSON-object
payload. Built for the drawing tools' per-tool Template menu (Save as.../Apply); "kind" rather than
a drawing-specific name so the indicator dialog can reuse this same store and routes later.

DEFAULT_NAME ("__default__") is a name like any other here -- what a new drawing/indicator of a
tool starts from ("Save as default" / "Apply default" in the page's Template menu) is entirely the
page's call. This module only stores and validates.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

KIND_RE = re.compile(r"^(drawing|indicator):[a-z0-9_-]{1,32}$")
DEFAULT_NAME = "__default__"
MAX_PRESET_NAME = 40
MAX_PRESET_BYTES = 16 * 1024   # one preset, as JSON (matches MAX_TEMPLATE_BYTES elsewhere in server.py)


def check_kind(kind) -> str:
    """"drawing:<tool>" or "indicator:<tool>", the tool 1-32 lowercase letters, digits, - or _.
    ValueError (with a page-facing message) otherwise."""
    if not isinstance(kind, str) or not KIND_RE.fullmatch(kind):
        raise ValueError('kind: "drawing:<tool>" or "indicator:<tool>"')
    return kind


def check_preset_name(name) -> str:
    """1-40 characters, no / \\ .. or control characters (it rides in the URL path), and not "."
    on its own (the browser resolves /api/presets/<kind>/. as a path step, landing on the list
    route rather than this name) -- the same rule as check_template_name in server.py.
    __default__ is valid input here like any other name; nothing in this file treats it
    specially."""
    if not isinstance(name, str) or not 1 <= len(name) <= MAX_PRESET_NAME:
        raise ValueError(f"a preset name has 1-{MAX_PRESET_NAME} characters")
    if name == ".":
        raise ValueError('a preset name cannot be "."')
    if "/" in name or "\\" in name or ".." in name or any(ord(ch) < 32 or ord(ch) == 127 for ch in name):
        raise ValueError("a preset name has no / \\ .. or control characters")
    return name


class PresetsStore:
    """One JSON file: {kind: {name: payload}}. Atomic writes (temp file + rename, the same pattern
    as layouts.json / templates.json / drawings.json in server.py's write_json): a crash or a full
    disk mid-write must never tear the file."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _read_all(self) -> dict:
        try:
            v = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return {}
        return v if isinstance(v, dict) else {}

    def _write_all(self, data: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2))
        os.replace(tmp, self.path)

    def list(self, kind: str) -> dict:
        """{name: payload} for one kind, or {} when none are saved yet. ValueError on a bad kind."""
        kind = check_kind(kind)
        v = self._read_all().get(kind)
        return v if isinstance(v, dict) else {}

    def put(self, kind: str, name: str, payload: dict) -> None:
        kind, name = check_kind(kind), check_preset_name(name)
        if not isinstance(payload, dict):
            raise ValueError("a preset is a JSON object")
        all_ = self._read_all()
        bucket = all_.get(kind)
        if not isinstance(bucket, dict):
            bucket = all_[kind] = {}
        bucket[name] = payload
        self._write_all(all_)

    def delete(self, kind: str, name: str) -> None:
        """Idempotent, like server.py's delete_template: a name that was never saved is not an
        error, and this always re-saves the file (never distinguishes "removed" from "already
        gone")."""
        kind, name = check_kind(kind), check_preset_name(name)
        all_ = self._read_all()
        bucket = all_.get(kind)
        if isinstance(bucket, dict):
            bucket.pop(name, None)
        self._write_all(all_)
