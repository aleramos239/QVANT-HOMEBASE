"""Filesystem locations for the homebase app.

Two kinds: the checkout's own (repo_root, state_dir, config_path: beside this package) and the machine's, under the
user's home (the tick archive, ~/.homebase, ...). A home path is read at call time (tests point HOME elsewhere) and
never created here.

Dev-only for now: everything lives under the repo checkout. If this ever gets frozen into a bundle, grow the
frozen-app branches back from onyx/paths.py at snapshot 0a75af5.
"""
from __future__ import annotations

import os
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
    """The app's config file (accounts, sizes)."""
    return _PKG_DIR / "config.json"


def user_dir() -> Path:
    """~/.homebase: the machine-wide app folder every checkout shares (ideas, strategies, desklab, tester, pine,
    review-requests, pipeline, arsenal.json, tester_slots.json, no_backtests)."""
    return Path.home() / ".homebase"


def from_env(env: str, *default: str) -> Path:
    """$env with ~ expanded when it is set and not empty, else ~/<default...> (e.g. from_env(ENV, ".homebase", "pine"))."""
    v = os.environ.get(env)
    return Path(v).expanduser() if v else Path.home().joinpath(*default)


def ticks_archive() -> Path:
    """~/futures_ticks: the tick archive, <ROOT>/<YYYY>/<session date>_<contract>.csv.gz."""
    return Path.home() / "futures_ticks"


def tape_cache() -> Path:
    """~/futures_derived/homebase_tape: the tester's binary tick tapes."""
    return Path.home() / "futures_derived" / "homebase_tape"


def depth_archive() -> Path:
    """~/futures_depth: the recorded order book."""
    return Path.home() / "futures_depth"


def massive_raw() -> Path:
    """~/massive_raw: Massive's raw downloads."""
    return Path.home() / "massive_raw"
