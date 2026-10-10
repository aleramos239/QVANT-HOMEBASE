"""The tell-log (Step B, task B4): what a strategy's child was told and what it answered, one JSON line each, for one
day in desk mode. Appended only, under the day's folder; a runner that starts again reads it back. tmp_path only."""
from __future__ import annotations

import json

import pytest

from homebase.labrun import store

DATE = "2024-03-05"


def test_the_tell_log_sits_beside_the_day_file_and_is_never_a_day(tmp_path):
    f = store.tell_path("pp", DATE, tmp_path)
    assert f == tmp_path / "pp" / "days" / f"{DATE}.tell.jsonl"
    store.tell("pp", DATE, {"seq": 1, "kind": "session"}, tmp_path)
    store.put_day("pp", {"date": DATE, "state": "running"}, tmp_path)
    assert store.days("pp", at=tmp_path) == [{"date": DATE, "state": "running"}]    # the listing of days never reads it
    assert store.get_day("pp", DATE, tmp_path) == {"date": DATE, "state": "running"}
    assert store.listing(tmp_path) == []


def test_lines_come_back_in_the_order_they_were_written(tmp_path):
    assert store.tells("pp", DATE, tmp_path) == []                                  # no log: nothing to read
    lines = [{"head": True, "mark": ["ab", "x"]}, {"seq": 1, "t_ns": 5, "kind": "bar", "arg": {"o": 1.5}},
             {"seq": 1, "intents": []}, {"seq": 1, "results": []}]
    for line in lines:
        store.tell("pp", DATE, line, tmp_path)
    assert store.tells("pp", DATE, tmp_path) == lines
    raw = store.tell_path("pp", DATE, tmp_path).read_text()
    assert raw.count("\n") == 4 and [json.loads(x) for x in raw.splitlines()] == lines     # one whole line each


def test_a_line_that_was_cut_off_or_does_not_read_is_left_out(tmp_path):
    store.tell("pp", DATE, {"seq": 1}, tmp_path)
    with open(store.tell_path("pp", DATE, tmp_path), "a") as fh:
        fh.write('[1, 2]\n{"seq": 2, "t_ns"')                                       # the runner went away mid-write
    assert store.tells("pp", DATE, tmp_path) == [{"seq": 1}]


def test_each_day_and_each_strategy_has_its_own(tmp_path):
    store.tell("pp", DATE, {"seq": 1}, tmp_path)
    store.tell("pp", "2024-03-06", {"seq": 7}, tmp_path)
    store.tell("qq", DATE, {"seq": 9}, tmp_path)
    assert store.tells("pp", DATE, tmp_path) == [{"seq": 1}] and store.tells("qq", DATE, tmp_path) == [{"seq": 9}]


@pytest.mark.parametrize("name, date", [("../x", DATE), ("pp", "2024-3-5"), ("pp", "../../etc"), ("runner", DATE)])
def test_a_name_or_a_date_that_is_not_one_is_refused(tmp_path, name, date):
    with pytest.raises(ValueError):
        store.tell(name, date, {"seq": 1}, tmp_path)
    with pytest.raises(ValueError):
        store.tells(name, date, tmp_path)
