"""homebase/core: each helper keeps the exact behavior of the copies it replaced (see the module docstrings)."""
import datetime as dt
import json
import os
from pathlib import Path

import pytest

from homebase import paths
from homebase.core import atomic, clock, jsonio, num

BIG = 10 ** 400                     # an int past float range: the one value the three finite checks disagree on


@pytest.mark.parametrize("v,want", [(0, True), (-1.5, True), (1e308, True), (float("nan"), False), (float("inf"), False),
                                    (True, False), (None, False), ("1", False)])
def test_the_finite_checks_agree_on_ordinary_values(v, want):
    assert num.finite(v) is want and num.finite_big_int_ok(v) is want and num.finite_no_overflow(v) is want


def test_the_finite_checks_differ_only_on_an_int_past_float_range():
    with pytest.raises(OverflowError):
        num.finite(BIG)
    assert num.finite_big_int_ok(-BIG) is True and num.finite_no_overflow(BIG) is False


def test_is_int_float_or_none_to_tick():
    assert [num.is_int(v) for v in (3, -2, True, 3.0, None)] == [True, True, False, False, False]
    assert num.float_or_none(2) == 2.0 and num.float_or_none(True) is None and num.float_or_none("2") is None
    assert num.float_or_none(float("nan")) != num.float_or_none(float("nan"))        # NaN passes through
    assert num.to_tick(100.13, 0.25) == 100.25 and num.to_tick(1.23456789, 1e-4) == 1.2346


def test_clock():
    assert clock.ET is __import__("zoneinfo").ZoneInfo("America/New_York")
    assert len(clock.utc_iso()) == 25 and clock.utc_iso().endswith("+00:00")
    assert clock.epoch_ms(dt.datetime(1970, 1, 1, 0, 0, 1, 999, tzinfo=dt.timezone.utc)) == 1000
    assert clock.et_hms(0) == "19:00:00" and clock.et_hms(999_999_999) == "19:00:00"       # floored, never rounded up
    assert [clock.is_hhmm(v) for v in ("09:30", "23:59", "24:00", "9:30", "09:30\n", 930)] == [True, True, False, False, False, False]
    assert clock.hhmm_minutes("09:30") == 570


def test_write_text_replaces_whole_and_keeps_the_callers_temp_name(tmp_path, monkeypatch):
    p = tmp_path / "a.json"
    p.write_text("old")
    moves, real = [], os.replace
    monkeypatch.setattr(os, "replace", lambda s, d: (moves.append(os.fspath(s)), real(s, d))[1])
    atomic.write_text(p, "new")
    atomic.write_text(p, "newer", tmp=p.with_suffix(".tmp"))
    assert p.read_text() == "newer" and moves == [f"{p}.{os.getpid()}.tmp", str(tmp_path / "a.tmp")]
    assert sorted(x.name for x in tmp_path.iterdir()) == ["a.json"]


def test_a_failed_replace_leaves_the_old_file_whole(tmp_path, monkeypatch):
    p = tmp_path / "a.json"
    p.write_text("old")

    def boom(s, d):
        assert open(s).read() == "new"                  # complete before the move
        raise OSError("disk full")
    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        atomic.write_text(p, "new")
    assert p.read_text() == "old"


def test_a_plain_write_goes_through_path_write_text_so_a_torn_write_is_testable(tmp_path, monkeypatch):
    p = tmp_path / "a.json"
    p.write_text("old")

    def torn(self, data, *a, **k):
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(Path, "write_text", torn)
    with pytest.raises(OSError):
        atomic.write_text(p, "new")
    monkeypatch.undo()
    assert p.read_text() == "old"


@pytest.mark.parametrize("kw,n", [({}, 0), ({"fsync": True}, 1), ({"fsync": True, "fsync_dir": True}, 2)])
def test_fsync_only_when_asked(tmp_path, monkeypatch, kw, n):
    calls, real = [], os.fsync
    monkeypatch.setattr(os, "fsync", lambda fd: (calls.append(fd), real(fd))[1])
    atomic.write_bytes(tmp_path / "b.bin", b"\x00\x01", **kw)
    assert (tmp_path / "b.bin").read_bytes() == b"\x00\x01" and len(calls) == n


def test_jsonio(tmp_path):
    p = tmp_path / "x.json"
    jsonio.write_json(p, {"d": dt.date(2026, 1, 2), "n": [1, 2.5]})
    assert p.read_text() == '{"d":"2026-01-02","n":[1,2.5]}'
    (tmp_path / "bad.json").write_text("{oops")
    (tmp_path / "list.json").write_text("[1]")
    assert jsonio.read_json(tmp_path / "missing.json", "D") == "D" and jsonio.read_json(tmp_path / "bad.json") is None
    assert jsonio.read_dict(tmp_path / "list.json") == {} and jsonio.read_dict(p)["n"] == [1, 2.5]


def test_home_paths_follow_home_at_call_time_and_create_nothing(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("HB_TEST_DIR", raising=False)
    assert paths.user_dir() == tmp_path / ".homebase" and paths.ticks_archive() == tmp_path / "futures_ticks"
    assert paths.tape_cache() == tmp_path / "futures_derived" / "homebase_tape"
    assert paths.depth_archive() == tmp_path / "futures_depth" and paths.massive_raw() == tmp_path / "massive_raw"
    assert paths.from_env("HB_TEST_DIR", ".homebase", "pine") == tmp_path / ".homebase" / "pine"
    monkeypatch.setenv("HB_TEST_DIR", "")
    assert paths.from_env("HB_TEST_DIR", "Downloads") == tmp_path / "Downloads"          # empty = not set
    monkeypatch.setenv("HB_TEST_DIR", "~/elsewhere")
    assert paths.from_env("HB_TEST_DIR", "Downloads") == tmp_path / "elsewhere"
    assert list(tmp_path.iterdir()) == []
