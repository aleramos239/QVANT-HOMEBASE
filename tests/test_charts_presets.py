"""homebase/charts/presets.py: the generic named-preset store behind /api/presets (2026-09-27
draw-tools plan) -- kind/name validation and PresetsStore's atomic read/write/delete. The routes
themselves (write guard, body cap, JSON-object payloads) are covered in test_charts_server.py."""
from __future__ import annotations

import json

import pytest

from homebase.charts.presets import DEFAULT_NAME, MAX_PRESET_NAME, PresetsStore, check_kind, check_preset_name


@pytest.mark.parametrize("kind", ["drawing:trend", "drawing:h", "drawing:a-b_c9", "indicator:rsi", "drawing:" + "a" * 32])
def test_check_kind_accepts(kind):
    assert check_kind(kind) == kind


@pytest.mark.parametrize("kind", [
    "", "trend", "drawing", "drawing:", "drawing:Trend", "drawing:tr end", "drawing:tr/end",
    "sticker:trend", "drawing:" + "a" * 33, 7, None, ["drawing:trend"],
])
def test_check_kind_refuses(kind):
    with pytest.raises(ValueError):
        check_kind(kind)


@pytest.mark.parametrize("name", ["x", "x" * MAX_PRESET_NAME, DEFAULT_NAME, "My preset", "a · b"])
def test_check_preset_name_accepts(name):
    assert check_preset_name(name) == name


@pytest.mark.parametrize("name", ["", "x" * (MAX_PRESET_NAME + 1), "a/b", "a\\b", "..", "a..b", "tab\there", "nul\x00", 7, None])
def test_check_preset_name_refuses(name):
    with pytest.raises(ValueError):
        check_preset_name(name)


def test_store_roundtrip(tmp_path):
    store = PresetsStore(tmp_path / "state" / "presets.json")
    assert store.list("drawing:trend") == {}
    store.put("drawing:trend", "Bold blue", {"width": 3, "textColor": "#2962FF"})
    store.put("drawing:trend", DEFAULT_NAME, {"width": 2})
    store.put("drawing:rect", "Fill", {"fillColor": "rgba(0,0,0,.2)"})
    assert store.list("drawing:trend") == {"Bold blue": {"width": 3, "textColor": "#2962FF"}, DEFAULT_NAME: {"width": 2}}
    assert store.list("drawing:rect") == {"Fill": {"fillColor": "rgba(0,0,0,.2)"}}
    on_disk = json.loads((tmp_path / "state" / "presets.json").read_text())
    assert on_disk == {"drawing:trend": {"Bold blue": {"width": 3, "textColor": "#2962FF"}, DEFAULT_NAME: {"width": 2}},
                       "drawing:rect": {"Fill": {"fillColor": "rgba(0,0,0,.2)"}}}


def test_put_overwrites_a_name(tmp_path):
    store = PresetsStore(tmp_path / "presets.json")
    store.put("drawing:trend", "A", {"width": 1})
    store.put("drawing:trend", "A", {"width": 4})
    assert store.list("drawing:trend") == {"A": {"width": 4}}


def test_delete_is_idempotent(tmp_path):
    store = PresetsStore(tmp_path / "presets.json")
    store.put("drawing:trend", "A", {"width": 1})
    store.delete("drawing:trend", "A")
    assert store.list("drawing:trend") == {}
    store.delete("drawing:trend", "A")   # deleting nothing is fine, like the templates route
    store.delete("drawing:never-saved", "A")   # nor is deleting from a kind that was never written
    assert store.list("drawing:trend") == {}


def test_delete_never_touches_another_kind(tmp_path):
    store = PresetsStore(tmp_path / "presets.json")
    store.put("drawing:trend", "A", {"width": 1})
    store.put("drawing:rect", "A", {"width": 2})
    store.delete("drawing:trend", "A")
    assert store.list("drawing:trend") == {}
    assert store.list("drawing:rect") == {"A": {"width": 2}}


def test_list_refuses_a_bad_kind(tmp_path):
    store = PresetsStore(tmp_path / "presets.json")
    with pytest.raises(ValueError):
        store.list("not-a-kind")


def test_put_refuses_a_non_object_payload(tmp_path):
    store = PresetsStore(tmp_path / "presets.json")
    for bad in ([1, 2], "text", None, 7):
        with pytest.raises(ValueError):
            store.put("drawing:trend", "A", bad)
    assert store.list("drawing:trend") == {}


def test_a_torn_file_reads_back_as_empty_never_crashes(tmp_path):
    p = tmp_path / "presets.json"
    p.write_text("{not json")
    store = PresetsStore(p)
    assert store.list("drawing:trend") == {}
    store.put("drawing:trend", "A", {"width": 1})   # writes clean over the torn file
    assert json.loads(p.read_text()) == {"drawing:trend": {"A": {"width": 1}}}
