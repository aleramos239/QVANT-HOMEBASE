"""Whole-file writes: a temp file beside the target, then os.replace -- a reader sees the old file or the new one, never half.

Nothing is added by default (a hot path must not pay for an fsync it never had); each caller asks for what it always had:
  fsync      flush the temp file to disk before the rename
  fsync_dir  also fsync the folder after the rename (the rename itself survives a power loss)
  tmp        the caller's own temp name (default <name>.<pid>.tmp); a site keeps the name it always used
  encoding   None = the locale default, exactly as Path.write_text
A failed write leaves its temp file behind and raises, as every site did before. os.replace / os.fsync / os.open are
looked up on `os` at call time (never `from os import ...`): tests patch them there.
"""
from __future__ import annotations

import os
from pathlib import Path


def tmp_for(path: Path) -> Path:
    """The default temp name, <name>.<pid>.tmp beside the target: two processes never write one temp file."""
    return path.with_name(f"{path.name}.{os.getpid()}.tmp")


def write_text(path: Path, text: str, *, tmp: Path | None = None, encoding: str | None = None,
               fsync: bool = False, fsync_dir: bool = False) -> None:
    """Replace `path` with `text`, whole."""
    tmp = tmp_for(path) if tmp is None else tmp
    with open(tmp, "w", encoding=encoding) as f:
        f.write(text)
        if fsync:
            f.flush()
            os.fsync(f.fileno())
    _replace(tmp, path, fsync_dir)


def write_bytes(path: Path, data: bytes, *, tmp: Path | None = None, fsync: bool = False,
                fsync_dir: bool = False) -> None:
    """Replace `path` with `data`, whole."""
    tmp = tmp_for(path) if tmp is None else tmp
    with open(tmp, "wb") as f:
        f.write(data)
        if fsync:
            f.flush()
            os.fsync(f.fileno())
    _replace(tmp, path, fsync_dir)


def _replace(tmp: Path, path: Path, fsync_dir: bool) -> None:
    os.replace(tmp, path)
    if fsync_dir:
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
