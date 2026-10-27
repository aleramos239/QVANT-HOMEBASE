"""The Desk's speed fixes (2026-10-26): the same answers, less work on the event loop."""
from __future__ import annotations

import asyncio

from tests.test_server import _write_journal, client  # noqa: F401  (the desk app over fakes, its state in tmp_path)


def _spy_threads(monkeypatch):
    seen, real = [], asyncio.to_thread

    async def spy(fn, *a, **k):
        seen.append(getattr(fn, "__name__", fn))
        return await real(fn, *a, **k)

    monkeypatch.setattr(asyncio, "to_thread", spy)
    return seen


def test_the_first_status_parses_the_journal_in_a_thread_and_the_next_ones_from_the_cache(client, tmp_path,
                                                                                          monkeypatch):
    _write_journal(tmp_path, 300)
    seen = _spy_threads(monkeypatch)
    first = client.get("/api/status")
    assert seen == ["records"]
    assert client.get("/api/status").content == first.content and seen == ["records"]
