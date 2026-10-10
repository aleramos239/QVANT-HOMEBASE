"""draftstore.delete moves a strategy's file into <drafts dir>/.trash/<name>.<UTC timestamp>.py -- it never unlinks.
The trash is never listed, never read as a draft, and a second delete of the same name keeps both copies.
Every drafts folder here is a tmp_path (the conftest's drafts_dir, or base=)."""
import re

import pytest

from homebase import draftstore
from homebase.backtest import drafthost

CODE = draftstore.DRAFT_TEMPLATE
OTHER = CODE + "\n# edited\n"
STAMPED = re.compile(r"^nq_orb\.\d{8}T\d{6}\d{6}Z(-\d+)?\.py$")


def trashed(base):
    t = base / ".trash"
    return sorted(p for p in t.iterdir()) if t.is_dir() else []


def test_delete_moves_the_file_into_the_trash_and_unlinks_nothing(drafts_dir):
    p = draftstore.write("nq_orb", CODE)
    assert not (drafts_dir / ".trash").exists(), "the trash is made on demand"
    assert draftstore.delete("nq_orb") is True
    assert not p.exists()
    got = trashed(drafts_dir)
    assert len(got) == 1 and STAMPED.match(got[0].name), got
    assert got[0].read_text() == CODE


def test_a_second_delete_of_the_same_name_keeps_both_copies(drafts_dir):
    draftstore.write("nq_orb", CODE)
    assert draftstore.delete("nq_orb")
    draftstore.write("nq_orb", OTHER)
    assert draftstore.delete("nq_orb")
    got = trashed(drafts_dir)
    assert len(got) == 2 and len({p.name for p in got}) == 2
    assert sorted(p.read_text() for p in got) == sorted([CODE, OTHER])


def test_two_deletes_in_the_same_instant_still_keep_both(drafts_dir, monkeypatch):
    monkeypatch.setattr(draftstore, "_stamp", lambda: "20261010T120000123456Z")
    draftstore.write("nq_orb", CODE)
    draftstore.delete("nq_orb")
    draftstore.write("nq_orb", OTHER)
    draftstore.delete("nq_orb")
    got = trashed(drafts_dir)
    assert len(got) == 2 and sorted(p.read_text() for p in got) == sorted([CODE, OTHER])


def test_a_name_that_is_not_there_is_false_and_makes_no_trash(drafts_dir):
    assert draftstore.delete("nq_orb") is False
    assert not (drafts_dir / ".trash").exists()


def test_the_listing_never_sees_the_trash(drafts_dir):
    draftstore.write("nq_orb", CODE)
    draftstore.write("nq_keep", CODE)
    draftstore.delete("nq_orb")
    assert [n for n, _ in draftstore.list_files()] == ["nq_keep"]
    assert [d["id"] for d in drafthost.catalog()] == ["draft_nq_keep"]
    assert draftstore.read_groups() == {"groups": [], "members": {}}
    with pytest.raises(FileNotFoundError):
        draftstore.read("nq_orb")


def test_a_trash_file_dropped_by_hand_is_not_a_draft_either(drafts_dir):
    (drafts_dir / ".trash").mkdir()
    (drafts_dir / ".trash" / "nq_old.20260101T000000000000Z.py").write_text(CODE)
    assert draftstore.list_files() == [] and drafthost.catalog() == []


def test_a_symlinked_trash_is_refused_and_the_file_stays(drafts_dir, tmp_path):
    p = draftstore.write("nq_orb", CODE)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (drafts_dir / ".trash").symlink_to(elsewhere)
    with pytest.raises(ValueError, match="trash"):
        draftstore.delete("nq_orb")
    assert p.read_text() == CODE and not list(elsewhere.iterdir())


def test_delete_takes_a_base_folder_like_write_does(tmp_path):
    base = tmp_path / "mine"
    draftstore.write("nq_orb", CODE, base=base)
    assert draftstore.delete("nq_orb", base=base) is True
    assert [p.name for p in trashed(base)][0].startswith("nq_orb.")
