"""Filesystem locations for the homebase app.

Dev-only for now: everything lives under the repo checkout. If this ever gets
frozen into a bundle, grow the frozen-app branches back from onyx/paths.py at
snapshot 0a75af5.
"""
from __future__ import annotations

from pathlib import Path

_PKG_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _PKG_DIR.parent


def repo_root() -> Path:
    return _REPO_ROOT


def state_dir() -> Path:
    """Writable state (broker tokens, day state, journal). Gitignored."""
    d = _PKG_DIR / ".state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def config_path() -> Path:
    """The app's config file (accounts, sizes, webhook secret name)."""
    return _PKG_DIR / "config.json"
