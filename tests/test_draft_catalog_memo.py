"""The draft catalog reads again only the draft that changed, and the built-in names are read again only when their folder
changes (2026-10-26): the answers are the ones a fresh read gives."""
from __future__ import annotations

import os
from pathlib import Path

from homebase import draftstore
from homebase.backtest import drafthost

CODE = draftstore.DRAFT_TEMPLATE


SETTLE = 100_000_000_000         # 100 s here, so a slow machine never settles a file mid-test


def age(p: Path, s: float = 1000.0) -> None:
    t = p.stat().st_mtime_ns - int(s * 1e9)
    os.utime(p, ns=(t, t))


def test_only_the_draft_that_changed_is_read_again(drafts_dir, monkeypatch):
    monkeypatch.setattr(drafthost, "SETTLED_NS", SETTLE)
    for n in ("nq_a", "nq_b", "nq_c"):
        age(draftstore.write(n, CODE))
    first = drafthost.catalog()
    assert [e["id"] for e in first] == ["draft_nq_a", "draft_nq_b", "draft_nq_c"]
    read = []
    real = drafthost.stub_class
    monkeypatch.setattr(drafthost, "stub_class", lambda name, src: read.append(name) or real(name, src))
    p = draftstore.write("nq_b", CODE + "\n# edited\n")
    got = drafthost.catalog()
    assert read == ["nq_b"] and got == first          # the one that changed (same metadata); the others as kept
    assert drafthost.catalog() is got and read == ["nq_b"]                  # nothing changed: the whole answer as before
    (drafts_dir / "nq_c.py").write_text("this is not python(")
    assert drafthost.catalog()[2]["error"] and read == ["nq_b", "nq_b", "nq_c"]   # nq_b: just written, read again
    age(p)
    read.clear()
    drafthost.catalog(builtin_ids={"draft_nq_a"})
    assert read == ["nq_b", "nq_c"]                    # settled now: kept from here on
    read.clear()
    assert [e["id"] for e in drafthost.catalog(builtin_ids={"draft_nq_a"} | {"x"})] == ["draft_nq_b", "draft_nq_c"]
    assert read == ["nq_c"]                            # the broken one was just written


class Counting(type(Path())):
    globs = 0

    def glob(self, pattern, **kw):
        Counting.globs += 1
        return super().glob(pattern, **kw)


def test_the_built_in_names_are_read_again_only_when_their_folder_changes(tmp_path, monkeypatch):
    d = Counting(tmp_path)
    (d / "orb.py").write_text("")
    monkeypatch.setattr(draftstore, "_BUILTIN_DIR", d)
    monkeypatch.setattr(draftstore, "_BUILTIN_NAMES", None)
    monkeypatch.setattr(draftstore, "SETTLED_NS", SETTLE)
    assert draftstore.builtin_names() == {"orb"} and draftstore.builtin_names() == {"orb"}
    assert Counting.globs == 2                          # the folder just changed: read each time
    age(d)
    draftstore.builtin_names()
    assert draftstore.builtin_names() == {"orb"} and Counting.globs == 3
    (d / "fade.py").write_text("")                     # an entry added: the folder's mtime moves
    assert draftstore.builtin_names() == {"orb", "fade"} and Counting.globs == 4
    (d / "orb.py").write_text("# edited")              # a file's text: no name changes, the folder stays
    age(d)
    draftstore.builtin_names()
    assert draftstore.builtin_names() == {"orb", "fade"} and Counting.globs == 5
