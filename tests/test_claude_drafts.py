"""DRAFT strategies: names, isolation (never imported into the chart service or the desk), the catalog,
clear load errors, and a draft backtest end to end on the synthetic archive."""
from __future__ import annotations

import datetime as dt
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from homebase import draftstore, strategies
from homebase.backtest import grid, runner, slots, walkforward
from homebase.charts.server import create_app
from tests.backtest_util import D1, nq_archive

REPO = Path(__file__).resolve().parent.parent
MARCH = {"kind": "custom", "start": "2024-03-01", "end": "2024-03-31"}

SENTINEL = '''
import os as _os, pathlib as _pl
_d = _os.environ.get("HB_SENTINEL_DIR")
if _d:
    (_pl.Path(_d) / str(_os.getpid())).touch()
'''


def app(tmp_path):
    return create_app(roots=["NQ"], base=nq_archive(tmp_path / "ticks"), replay=D1, speed=1,
                      start_et=dt.time(9, 30), state=tmp_path / "state")


def client(tmp_path):
    return TestClient(app(tmp_path), base_url="http://localhost:8852")


def poll(c, path, s=60.0):
    import time
    t = time.monotonic() + s
    while time.monotonic() < t:
        st = c.get(path).json()
        if st["status"] in ("done", "error", "cancelled"):
            return st
        time.sleep(0.05)
    raise AssertionError("never finished")


@pytest.fixture
def sentinel(tmp_path, monkeypatch):
    d = tmp_path / "sentinel"
    d.mkdir()
    monkeypatch.setenv("HB_SENTINEL_DIR", str(d))
    return d


def write_template(name="my_orb"):
    """The shipped template itself, plus a line that records which process ran it."""
    fut = "from __future__ import annotations\n"
    src = draftstore.DRAFT_TEMPLATE.replace(fut, fut + SENTINEL, 1)
    assert src != draftstore.DRAFT_TEMPLATE
    return draftstore.write(name, src)


# ---------------------------------------------------------------- names

@pytest.mark.parametrize("bad", ["", "a", "Nq930", "9lives", "has-dash", "has space", "../etc", "x" * 41,
                                 "draft_x", "base", "straddle", "nq930", "gc_nfpcpi", "init", "a.b"])
def test_bad_names_are_refused(bad):
    with pytest.raises(ValueError):
        draftstore.validate_name(bad)


def test_every_builtin_id_and_module_is_refused_and_no_builtin_looks_like_a_draft():
    for sid in strategies.REGISTRY:
        assert not sid.startswith(draftstore.PREFIX)
        with pytest.raises(ValueError):
            draftstore.validate_name(sid, builtin_ids=strategies.REGISTRY)
    for p in (REPO / "homebase" / "strategies").glob("*.py"):
        with pytest.raises(ValueError):
            draftstore.validate_name(p.stem)
    assert draftstore.validate_name("nq_orb_15") == "nq_orb_15"


def test_write_touches_only_its_own_file_and_checks_syntax(drafts_dir):
    p = draftstore.write("nq_orb", draftstore.DRAFT_TEMPLATE)
    assert p == drafts_dir / "nq_orb.py" and p.read_text() == draftstore.DRAFT_TEMPLATE
    assert sorted(x.name for x in drafts_dir.iterdir()) == ["nq_orb.py"]
    with pytest.raises(ValueError, match="SyntaxError"):
        draftstore.write("nq_orb2", "def broken(:\n")
    assert not (drafts_dir / "nq_orb2.py").exists()
    with pytest.raises(ValueError):
        draftstore.write("../evil", "x = 1\n")
    assert draftstore.delete("nq_orb") and not p.exists() and not draftstore.delete("nq_orb")


# ---------------------------------------------------------------- listing / validating never runs a draft

@pytest.mark.parametrize("bad", ["json", "homebase", "sitecustomize", "usercustomize", "socket", "charts", "engine"])
def test_names_never_shadow_a_stdlib_or_homebase_module(bad):
    with pytest.raises(ValueError, match="module name|reserved|built-in"):
        draftstore.validate_name(bad)


def test_a_pathological_source_is_a_value_error():
    with pytest.raises(ValueError):
        draftstore.check_source("x = " + "-" * 199_000 + "1\n")


def test_static_meta_reads_the_template_without_running_it():
    m = draftstore.static_meta(draftstore.DRAFT_TEMPLATE)
    assert m["class"] == "MyDraft" and m["root"] == "NQ" and m["session_independent"] is True
    assert [i["key"] for i in m["inputs"]] == ["offset_pts", "sl_pts", "tp_pts"]
    assert m["inputs"][0] == {"key": "offset_pts", "label": "Offset (pts)", "type": "float", "default": 10.0,
                              "min": 0.25, "max": 100, "step": 0.25, "choices": []}


@pytest.mark.parametrize("src,msg", [
    ("from homebase.strategies.base import Strategy\n", "exactly one class"),
    ("from homebase.strategies.base import Strategy\nclass A(Strategy):\n    root = 'NQ'\n"
     "class B(Strategy):\n    root = 'NQ'\n", "exactly one class"),
    ("from homebase.strategies.base import Strategy\nclass A(Strategy):\n    name = 'x'\n", "root"),
    ("from homebase.strategies.base import Strategy\nR = 'NQ'\nclass A(Strategy):\n    root = R\n", "literal"),
    ("from homebase.strategies.base import Input, Strategy\nclass A(Strategy):\n    root = 'NQ'\n"
     "    @classmethod\n    def inputs(cls):\n        xs = []\n        return xs\n", "single `return"),
    ("from homebase.strategies.base import Input, Strategy\nclass A(Strategy):\n    root = 'NQ'\n"
     "    @classmethod\n    def inputs(cls):\n        return [Input('a', 'A', 'float', 1.0 + 2)]\n", "literal"),
])
def test_static_meta_refuses_what_it_cannot_read(src, msg):
    with pytest.raises(ValueError, match=msg):
        draftstore.static_meta(src)


def test_the_catalog_never_runs_a_draft(tmp_path, sentinel):
    write_template()
    (draftstore.drafts_dir() / "not_static.py").write_text(
        "from homebase.strategies.base import Strategy\nclass A(Strategy):\n    root = 'N' + 'Q'\n")
    with client(tmp_path) as c:
        got = {s["id"]: s for s in c.get("/api/tester/strategies").json()}
        c.get("/api/tester/strategies/draft_my_orb/source")
    assert {"nq930", "gc_nfpcpi"} <= set(got)
    d = got["draft_my_orb"]
    assert d["draft"] is True and d["root"] == "NQ" and not d.get("error") and d["session_independent"] is True
    assert [i["key"] for i in d["inputs"]] == ["offset_pts", "sl_pts", "tp_pts"]
    assert "literal" in got["draft_not_static"]["error"]
    assert not list(sentinel.iterdir())                # no draft code ran -- in this process or any child
    assert not any(m.startswith("homebase_draft_") for m in sys.modules)
    assert not any(draftstore.is_draft_id(k) for k in strategies.REGISTRY)


def test_validation_uses_the_static_stub_and_snapshots_the_source(sentinel):
    write_template()
    req = runner.validate({"strategy": "draft_my_orb", "range": MARCH})
    assert req["strategy"] == "draft_my_orb" and req["inputs"]["offset_pts"] == 10.0
    assert req["draft_source"] == (draftstore.drafts_dir() / "my_orb.py").read_text() and req["draft_sha256"]
    g = grid.validate_grid({"strategy": "draft_my_orb", "range": MARCH,
                            "axes": [{"key": "sl_pts", "values": [4, 5]}, {"key": "tp_pts", "values": [10, 15]}]})
    assert len(g["cells"]) == 4 and all(c["req"]["draft_source"] == req["draft_source"] for c in g["cells"])
    wf = walkforward.validate_wf({"strategy": "draft_my_orb", "range": {"kind": "custom", "start": "2024-01-01",
                                  "end": "2024-06-30"}, "axes": [{"key": "sl_pts", "values": [4, 5]},
                                                                 {"key": "tp_pts", "values": [10, 15]}]})
    assert wf["walkforward"]["test_months"] == 3 and all(c["req"]["propsim"] is False for c in wf["cells"])
    with pytest.raises(ValueError, match="sl_pts"):
        runner.validate({"strategy": "draft_my_orb", "inputs": {"sl_pts": 1e9}, "range": MARCH})
    assert not list(sentinel.iterdir())
    assert not any(draftstore.is_draft_id(k) for k in strategies.REGISTRY)


def test_a_bad_draft_request_is_a_clear_400(tmp_path):
    with client(tmp_path) as c:
        r = c.post("/api/tester/run", json={"strategy": "draft_nope", "range": MARCH})
        assert r.status_code == 400 and "no draft 'nope'" in r.json()["detail"]
        r = c.post("/api/tester/run", json={"strategy": "draft_../x", "range": MARCH})
        assert r.status_code == 400


def test_no_draft_run_starts_in_the_quiet_window(tmp_path, monkeypatch):
    write_template()
    with client(tmp_path) as c:
        monkeypatch.setattr(slots, "et_now", lambda: dt.datetime(2026, 9, 28, 9, 25, tzinfo=slots.ET))
        r = c.post("/api/tester/run", json={"strategy": "draft_my_orb", "range": MARCH})
        assert r.status_code == 400 and "09:20" in r.json()["detail"]


def test_a_draft_backtests_end_to_end_in_the_sandbox_and_runs_the_validated_snapshot(tmp_path):
    write_template()
    with client(tmp_path) as c:
        r = c.post("/api/tester/run", json={"strategy": "draft_my_orb", "range": MARCH})
        assert r.status_code == 200, r.text
        rid = r.json()["id"]
        # the file changes after validation: the run still executes the snapshot it was validated with
        draftstore.write("my_orb", draftstore.DRAFT_TEMPLATE.replace('"09:30:00"', '"09:45:00"'))
        st = poll(c, f"/api/tester/run/{rid}")
        assert st["status"] == "done", st.get("error")
        b = c.get(f"/api/tester/run/{rid}/bundle").json()
        assert b["run"]["strategy"]["id"] == "draft_my_orb"
        assert len(b["trades"]) == 1 and b["trades"][0]["side"] == "long" and b["trades"][0]["exit_reason"] == "tp"
        req = runner.read_json(tmp_path / "state" / "tester" / "runs" / rid / "request.json")
        assert '"09:45:00"' not in req["draft_source"]
    assert not any(m.startswith("homebase_draft_") for m in sys.modules)
    assert not list((tmp_path / "state" / "tester" / "tape").glob("**/*.tape")), \
        "a sandboxed draft run never writes the shared tape cache"


def test_source_route_serves_builtins_and_draft_text_without_running_it(tmp_path, sentinel):
    write_template()
    with client(tmp_path) as c:
        s = c.get("/api/tester/strategies/nq930/source").json()
        assert [f["path"] for f in s["files"]] == ["homebase/strategies/nq930.py", "homebase/strategies/straddle.py",
                                                   "homebase/strategies/base.py"]
        d = c.get("/api/tester/strategies/draft_my_orb/source").json()
        assert d["draft"] is True and "class MyDraft" in d["files"][0]["text"]
        assert c.get("/api/tester/strategies/draft_nope/source").status_code == 404
        assert c.get("/api/tester/strategies/nope/source").status_code == 404
    assert not list(sentinel.iterdir())


# ---------------------------------------------------------------- the desk can never load one

DESK_MODULES = ["homebase/server.py", "homebase/engine.py", "homebase/trading.py", "homebase/timer.py",
                "homebase/config.py", "homebase/rules.py", "homebase/desk_api.py", "homebase/feed.py",
                "homebase/gate.py", "homebase/risk.py", "homebase/review.py", "homebase/metrics.py",
                "homebase/charts/desk.py", "homebase/charts/paper.py", "homebase/charts/paperbook.py"]


def test_no_desk_module_references_drafts():
    for rel in DESK_MODULES:
        text = (REPO / rel).read_text()
        assert not re.search(r"draftstore|drafthost|HOMEBASE_DRAFTS_DIR|\.homebase/strategies", text), rel


def test_importing_the_desk_never_loads_a_draft(sentinel):
    """The desk process (homebase.server) imported in a clean interpreter with a draft on disk: no draft
    code runs, no draft module is loaded, and neither draft helper is even imported."""
    write_template()
    code = ("import sys, homebase.server, homebase.engine, homebase.trading, homebase.rules\n"
            "bad = [m for m in sys.modules if m.startswith('homebase_draft_') or m in "
            "('homebase.draftstore', 'homebase.backtest.drafthost', 'homebase.backtest.sandbox')]\n"
            "from homebase.rules import RULES\n"
            "assert not bad, bad\nassert not any(k.startswith('draft_') for k in RULES), RULES\nprint('ok')\n")
    p = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True, timeout=120)
    assert p.returncode == 0 and p.stdout.strip() == "ok", p.stderr
    assert not list(sentinel.iterdir())


def test_the_paper_algo_list_never_carries_a_draft(tmp_path):
    write_template()
    with client(tmp_path) as c:
        ids = [s.get("id") for s in c.get("/api/paper/strategies").json()]
    assert ids and not any(draftstore.is_draft_id(i) for i in ids)
