"""App settings (Task 4, 2026-09-27 accounts-paper-layouts-appsettings plan): the store's round
trip and its HOMEBASE_CHARTS_MD env-var default. Tmp dir only -- never a real settings.json."""
from __future__ import annotations

import importlib

import pytest

from homebase.charts.settings_store import MD_CHOICES, SettingsStore


def test_a_fresh_store_reads_the_env_default(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMEBASE_CHARTS_MD", "live")
    import homebase.charts as charts_mod
    importlib.reload(charts_mod)
    import homebase.charts.settings_store as ss_mod
    importlib.reload(ss_mod)
    try:
        store = ss_mod.SettingsStore(tmp_path / "settings.json")
        assert store.get() == {"md": "live"}
        assert not (tmp_path / "settings.json").exists()   # reading never creates the file
    finally:
        monkeypatch.delenv("HOMEBASE_CHARTS_MD", raising=False)
        importlib.reload(charts_mod)
        importlib.reload(ss_mod)


def test_set_md_round_trips_and_persists_across_a_fresh_store(tmp_path):
    path = tmp_path / "sub" / "settings.json"
    store = SettingsStore(path)
    assert store.set_md("live") == {"md": "live"}
    assert path.exists()
    # a fresh store over the same path reads back exactly what was set
    assert SettingsStore(path).get() == {"md": "live"}
    assert SettingsStore(path).set_md("demo") == {"md": "demo"}
    assert SettingsStore(path).get() == {"md": "demo"}


def test_an_invalid_choice_is_refused_and_leaves_the_file_untouched(tmp_path):
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    store.set_md("live")
    with pytest.raises(ValueError):
        store.set_md("paper")
    assert SettingsStore(path).get() == {"md": "live"}


def test_a_stale_or_hand_edited_value_falls_back_to_the_env_default(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text('{"md": "not-a-real-login"}')
    assert SettingsStore(path).get()["md"] in MD_CHOICES


def test_other_keys_in_the_file_survive_a_set_md(tmp_path):
    """More app-wide settings land in the same file later (the brief's "structured so more
    settings can be added later"); set_md must not clobber a key it doesn't own."""
    path = tmp_path / "settings.json"
    path.write_text('{"unrelated": 42}')
    SettingsStore(path).set_md("live")
    import json
    assert json.loads(path.read_text()) == {"unrelated": 42, "md": "live"}


def test_m6_a_write_that_cannot_be_read_back_raises_rather_than_silently_losing_it(tmp_path, monkeypatch):
    """The temp-file write is fsync'd before the atomic rename (review M6). This does not (and
    cannot, from a unit test) prove fsync reaches the disk platter -- it proves the write path
    calls it, so a real OSError during fsync (a full disk) surfaces to the caller instead of a
    silently torn or missing file."""
    import os as os_mod
    path = tmp_path / "settings.json"
    store = SettingsStore(path)
    calls = []
    real_fsync = os_mod.fsync

    def spy_fsync(fd):
        calls.append(fd)
        real_fsync(fd)
    monkeypatch.setattr(os_mod, "fsync", spy_fsync)
    store.set_md("live")
    assert calls, "set_md must fsync the temp file before the atomic rename"
    assert SettingsStore(path).get() == {"md": "live"}


def test_the_env_default_is_normalised_and_an_unknown_value_is_demo():
    """Re-review M-a: "LIVE" means live; anything unrecognised is demo, what it always got."""
    import os
    import subprocess
    import sys
    for raw, want in (("LIVE", "live"), (" live ", "live"), ("demo", "demo"), ("paper", "demo")):
        out = subprocess.run([sys.executable, "-c", "from homebase.charts import MD_ENV; print(MD_ENV)"],
                             capture_output=True, text=True, check=True,
                             env={**os.environ, "HOMEBASE_CHARTS_MD": raw}).stdout.strip()
        assert out == want, raw
