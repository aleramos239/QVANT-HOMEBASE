"""Suite-wide pins for the tester's machine-wide state:

  * HOMEBASE_TESTER_SHARED -> a fresh tmp dir per test, so no test ever touches the real
    per-machine ~/.homebase/tester (the backtest slots and looks.json); runner children
    started by a test inherit it through the environment;
  * the tester's clock -> a Monday noon ET (desk hours: the cap is 2), so a test that counts
    slots never depends on when it runs. A test that needs another time injects its own clock
    (Slots(clock=...)) or re-patches slots.et_now."""
from __future__ import annotations

import datetime as dt
import os
from pathlib import Path

import pytest

from homebase import strategies
from homebase.backtest import slots
from tests.straddle_twin import NQ930

# The whole run, not just each test: the stores that live under ~/.homebase point at a throwaway folder from the moment
# the tests start. The fixtures below give every test its own folder on top; this catches what runs outside a test -- a
# thread or a child still writing after its test ended, a module- or session-scoped fixture -- which used to land in the
# REAL store (2026-10-20: a test strategy "PP" appeared on the owner's Desk).
import tempfile as _tempfile                                                                  # noqa: E402
_RUN = Path(_tempfile.mkdtemp(prefix="homebase-tests-"))
for _key, _sub in (("HOMEBASE_DESKLAB_ROOT", "desklab"), ("HOMEBASE_DRAFTS_DIR", "drafts"), ("HOMEBASE_IDEAS_ROOT", "ideas"),
                   ("HOMEBASE_TESTER_SHARED", "tester")):
    os.environ[_key] = str(_RUN / _sub)
os.environ["HOMEBASE_TESTER_SLOTS_FILE"] = str(_RUN / "tester" / "no_override.json")

_REPO = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def tester_shared(tmp_path_factory, monkeypatch):
    d = tmp_path_factory.mktemp("tester-shared")
    monkeypatch.setenv("HOMEBASE_TESTER_SHARED", str(d))
    monkeypatch.setenv("HOMEBASE_TESTER_SLOTS_FILE", str(d / "no_override.json"))   # never the real ~/.homebase file
    return d


@pytest.fixture(autouse=True)
def _nq930_twin(monkeypatch):
    """The old built-in nq930, for the tester tests only (tests/straddle_twin.py)."""
    monkeypatch.setitem(strategies.REGISTRY, "nq930", NQ930)


@pytest.fixture(autouse=True)
def twin_in_children(monkeypatch):
    """A backtest a test runs in a child process sees the nq930 twin too (tests/child_site). A test that checks what a
    bare child imports (test_fanout) takes PYTHONPATH off again."""
    site = [str(_REPO / "tests" / "child_site"), str(_REPO)]
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(site + [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]))


@pytest.fixture(autouse=True)
def _a_monday_noon(monkeypatch):
    monkeypatch.setattr(slots, "et_now", lambda: dt.datetime(2026, 9, 28, 12, 0, tzinfo=slots.ET))


@pytest.fixture(autouse=True)
def _no_broker_connections(monkeypatch):
    """Tests never open broker connections (GOTCHAS): a test that reaches the Tradovate
    auth's HTTP calls (login, renew, account list) or opens a broker websocket fails --
    e.g. a reconnect() on the real clock, weekdays 09:10-10:00 ET, renews before the window.
    pytest.fail raises a BaseException: the desk's `except Exception` fallbacks (a
    best-effort renewal, the keepalive) can never swallow it into a pass."""
    def refuse_http(*a, **k):
        pytest.fail("a real Tradovate HTTP call from a test")

    def refuse_socket(*a, **k):
        pytest.fail("a real broker websocket from a test")

    monkeypatch.setattr("homebase.broker.tradovate_auth.http_post_json", refuse_http)
    monkeypatch.setattr("homebase.broker.tradovate_auth.http_get_json", refuse_http)
    monkeypatch.setattr("homebase.broker.tradovate_ws.websockets.connect", refuse_socket)


@pytest.fixture(autouse=True)
def drafts_dir(tmp_path_factory, monkeypatch):
    """DRAFT strategies (homebase.draftstore): a fresh, empty tmp dir per test -- never ~/.homebase/strategies.
    Child processes (the draft host, runner exec) inherit it through the environment."""
    d = tmp_path_factory.mktemp("drafts")
    monkeypatch.setenv("HOMEBASE_DRAFTS_DIR", str(d))
    return d


@pytest.fixture(autouse=True)
def ideas_root(tmp_path_factory, monkeypatch):
    """Blueprint ideas (homebase.ideastore): a fresh, empty tmp dir per test -- never ~/.homebase/ideas.
    Child processes (the blueprint toolkit the connector starts) inherit it through the environment."""
    d = tmp_path_factory.mktemp("ideas")
    monkeypatch.setenv("HOMEBASE_IDEAS_ROOT", str(d))
    return d


@pytest.fixture(autouse=True)
def desklab_root(tmp_path_factory, monkeypatch):
    """Promoted Lab strategies (homebase.labrun.store): a fresh, empty tmp dir per test -- never ~/.homebase/desklab.
    Child processes (the runner, python -m homebase.labrun) inherit it through the environment."""
    d = tmp_path_factory.mktemp("desklab")
    monkeypatch.setenv("HOMEBASE_DESKLAB_ROOT", str(d))
    return d


@pytest.fixture(autouse=True)
def no_real_desk_for_the_lab_list(monkeypatch):
    """The Lab's list of the Desk's built-ins asks the Desk on :8850: a test never asks a real one."""
    try:
        from homebase.charts import tester_api
    except Exception:       # (a test of something that does not load the chart service)
        return
    monkeypatch.setattr(tester_api, "desk_strategy_ids", lambda: [])


_LOCAL = ("127.0.0.1", "::1", "localhost", None)


@pytest.fixture(autouse=True)
def no_network(request, monkeypatch):
    """The Vest/TopstepX tests never reach the network (M7): a non-local socket connect or DNS lookup raises, and the test fails
    at teardown even if it caught the error. Other tests are untouched."""
    hits: list = []
    if request.path.name.startswith(("test_vest", "test_topstepx")):
        import socket
        connect, gai = socket.socket.connect, socket.getaddrinfo

        def guard(self, addr, *a, **k):
            host = addr[0] if isinstance(addr, tuple) else addr
            if isinstance(host, str) and host.startswith("/") or host in _LOCAL:        # a unix socket or this machine
                return connect(self, addr, *a, **k)
            hits.append(host)
            raise OSError(f"network blocked in Vest/TopstepX tests: {host}")

        def lookup(host, *a, **k):
            if host in _LOCAL:
                return gai(host, *a, **k)
            hits.append(host)
            raise socket.gaierror(f"network blocked in Vest/TopstepX tests: {host}")
        monkeypatch.setattr(socket.socket, "connect", guard)
        monkeypatch.setattr(socket, "getaddrinfo", lookup)
    yield hits
    assert not hits, f"a Vest/TopstepX test tried the network: {hits}"
