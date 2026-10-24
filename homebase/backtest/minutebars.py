"""A session's 1-minute bars, made once and kept beside its tape.

engine.build_bars was ~45% of a bar strategy's run: max/min/sum over every print of the window (~360k NQ prints a
session) on every run. Bars of a whole number of minutes over a session window on whole minutes are runs of whole
minutes, so run_session composes them from these instead -- the same Bar, field for field.

Sidecar: one file per .tape, `<date>.m1` beside it (or in a sandboxed draft's private cache, see Tape.minutes):
  MAGIC, u32 header length, JSON header {v, n, tape: [st_size, st_mtime_ns], byteorder}, then n x int64 start_ns,
  n x float64 o, h, l, c, n x int64 v -- every NON-EMPTY epoch-aligned minute of the whole tape.
`tape` is the stamp of the .tape it was made from (as read): a rebuilt .tape makes it stale. A sidecar never fails a
run: one that cannot be read is rebuilt in memory, one that cannot be written is simply not kept.

Stdlib only (array + bisect): the desk's venv carries no numpy.
"""
from __future__ import annotations

import json
import os
import sys
import threading
from array import array
from bisect import bisect_left
from contextlib import suppress
from pathlib import Path

MAGIC = b"HBMIN1\n\0"
VERSION = 1
MINUTE = 60_000_000_000
TYPES = "qddddq"          # start_ns, o, h, l, c, v


def build(ts, px, size) -> tuple:
    """(start_ns, o, h, l, c, v) arrays of every non-empty minute of the prints: build_bars' own operations (o the
    first print, h max, l min, c the last print, v the sum of sizes)."""
    st, o, h, l, c, v = (array(t) for t in TYPES)
    n, i0 = len(ts), 0
    while i0 < n:
        m = ts[i0] - ts[i0] % MINUTE
        i1 = bisect_left(ts, m + MINUTE, i0, n)
        seg = px[i0:i1]
        st.append(m)
        o.append(px[i0])
        h.append(max(seg))
        l.append(min(seg))
        c.append(px[i1 - 1])
        v.append(sum(size[i0:i1]))
        i0 = i1
    return st, o, h, l, c, v


def sidecar(tape_path: Path) -> Path:
    return Path(tape_path).with_suffix(".m1")


def _head(f) -> dict | None:
    if f.read(len(MAGIC)) != MAGIC:
        return None
    head = json.loads(f.read(int.from_bytes(f.read(4), "little")))
    return head if head.get("v") == VERSION and head.get("byteorder") == sys.byteorder else None


def read(p: Path, stamp: tuple) -> tuple | None:
    """The minutes in sidecar p when it was made from the .tape stamped `stamp` (st_size, st_mtime_ns), else None."""
    try:
        with open(p, "rb") as f:
            head = _head(f)
            if head is None or head["tape"] != list(stamp):
                return None
            m = tuple(array(t) for t in TYPES)
            for a in m:
                a.fromfile(f, head["n"])
            return m
    except Exception:       # noqa: BLE001 -- a sidecar never fails a run: any bad file is rebuilt (or the prints used)
        return None


def fresh(tape_path: Path) -> bool:
    """The sidecar beside this .tape was made from it as it is now (a header read: the warm job's check)."""
    try:
        st = os.stat(tape_path)
        with open(sidecar(tape_path), "rb") as f:
            head = _head(f)
        return head is not None and head["tape"] == [st.st_size, st.st_mtime_ns]
    except Exception:       # noqa: BLE001 -- any bad file is simply not fresh
        return False


def write(p: Path, stamp: tuple, m: tuple) -> None:
    """Atomically (tmp + replace); any OSError (a read-only or sandboxed cache, a full disk) keeps nothing."""
    raw = json.dumps({"v": VERSION, "n": len(m[0]), "tape": list(stamp), "byteorder": sys.byteorder}).encode()
    tmp = p.with_name(p.name + f".{os.getpid()}.{threading.get_ident()}.tmp")    # one tmp per writer, threads too
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "wb") as f:
            f.write(MAGIC)
            f.write(len(raw).to_bytes(4, "little"))
            f.write(raw)
            for a in m:
                a.tofile(f)
        os.replace(tmp, p)
    except OSError:
        with suppress(OSError):
            os.unlink(tmp)


def load_or_build(tape_path: Path | None, stamp: tuple, ts, px, size, keep: bool = True) -> tuple | None:
    """The tape's minutes from a fresh sidecar beside its .tape; else, when `keep`, built here and written beside it.
    None -- the engine then reads the prints, as before -- for a tape made in memory, or a draft whose shared cache has
    no fresh sidecar yet (the tapewarm job makes them): a copy it built would die with its sandbox and cost the
    whole tape's prints on every run."""
    if tape_path is None:
        return None
    p = sidecar(tape_path)
    m = read(p, stamp)
    if m is not None or not keep:
        return m
    m = build(ts, px, size)
    write(p, stamp, m)
    return m
