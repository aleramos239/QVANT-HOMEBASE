"""The "Backtest metrics" popup's research artifacts (homebase/research/<name>_equity.json).

Every strategy whose metrics name an equity_file must ship a well-formed artifact, /api/research-equity must
return it, and the pointer must reach the running config even when a config.json written before the pointer
existed carries its own (older) copy of the metrics.  The artifacts are built by
homebase/research/build_algo_metrics.py from the research files; these tests read what is committed."""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import homebase.config as config_mod
from homebase.server import create_app
from tests.levels_util import strategy_cfg

RESEARCH = Path(config_mod.__file__).resolve().parent / "research"
ALGOS = ("gc_nfp",)
SHIPPED_WITH_FILE = sorted(n for n, s in config_mod._defaults().strategies.items() if s.metrics.get("equity_file"))
WITH_FILE = SHIPPED_WITH_FILE


def artifact(name: str) -> dict:
    return json.loads((RESEARCH / strategy_cfg(name).metrics["equity_file"]).read_text())


def row(art: dict, key: str) -> str:
    return next(v for _, k, v in art["table"] if k == key)


def test_every_algo_names_its_artifact():
    assert set(ALGOS) | {"nq930"} <= set(WITH_FILE)
    assert SHIPPED_WITH_FILE == ["gc_nfp", "nq930"]                        # the desk ships these two
    assert not list(RESEARCH.glob("nq_*_equity.json"))                     # the four NQ levels algos' artifacts are gone
    for n in ALGOS:
        m = strategy_cfg(n).metrics
        assert m["equity_file"] == f"{n}_equity.json"
        assert {"source", "rows", "caveat"} <= set(m)                      # the profile's own record is untouched


@pytest.mark.parametrize("name", WITH_FILE)
def test_the_artifact_exists_and_is_well_formed(name):
    f = RESEARCH / strategy_cfg(name).metrics["equity_file"]
    assert f.is_file(), f"{name}: {f.name} is not committed"
    a = json.loads(f.read_text())
    assert isinstance(a["label"], str) and a["label"] and isinstance(a["note"], str) and a["note"]
    pts = a["points"]
    assert len(pts) >= 2
    dates = []
    for p in pts:
        assert len(p) == 2 and isinstance(p[1], (int, float)) and not isinstance(p[1], bool)
        dates.append(dt.date.fromisoformat(p[0]))
    assert dates == sorted(dates)                                          # the curve runs forward in time
    assert a["table"] and all(len(r) == 3 and all(isinstance(x, str) for x in r) for r in a["table"])
    assert a["prop_table"] and all(len(r) == 2 and all(isinstance(x, str) for x in r) for r in a["prop_table"])
    # the page writes these strings into the DOM as they are (index.html openRes)
    texts = [a[k] for k in ("label", "note", "table_note", "prop_title", "prop_note", "mc_note") if k in a]
    texts += [x for r in a["table"] + a["prop_table"] + a.get("mc_table", []) for x in r]
    assert not [t for t in texts if "<" in t]


@pytest.mark.parametrize("name", ALGOS)
def test_the_table_describes_the_curve_it_sits_under(name):
    a = artifact(name)
    pts = a["points"]
    assert len({p[0] for p in pts}) == len(pts)                            # one trade a day: the chart drops a repeated date
    assert row(a, "trades") == str(len(pts))
    assert row(a, "window") == f"{pts[0][0]} → {pts[-1][0]}"
    net = pts[-1][1]
    assert row(a, "net") == ("-$" if net < 0 else "$") + f"{abs(net):,.2f}"
    assert str(len(pts)) in a["label"]
    cfg = strategy_cfg(name)
    assert cfg.metrics["caveat"] in a["table_note"]                        # the caveat on file travels with the numbers
    assert "mc_table" not in a                                             # no resample is claimed for these ledgers


def test_the_gc_artifact_covers_every_nfp_and_marks_2025():
    a = artifact("gc_nfp")
    dates = [p[0] for p in a["points"]]
    assert dates[0].startswith("2021") and dates[-1].startswith("2026")
    first_2025 = next(i for i, d in enumerate(dates) if d >= "2025-01-01")
    assert f"2025 starts at event {first_2025 + 1} ({dates[first_2025]})" in a["note"]
    assert "not a clean exam" in a["note"]
    assert ["numbers shown", "2025-26 / 2021-24"] in a["prop_table"]
    assert ["events", f"{len(dates) - first_2025} / {first_2025}"] in a["prop_table"]


# ---- the endpoint ----------------------------------------------------------------------------------
@pytest.fixture
def desk(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.engine.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.server.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.secrets_store.state_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    app = create_app(config_mod._defaults(), {}, background=False)        # disarmed, no account, nothing booked
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        yield c


@pytest.mark.parametrize("name", SHIPPED_WITH_FILE)
def test_research_equity_returns_the_committed_artifact(desk, name):
    got = desk.get("/api/research-equity", params={"strategy": name})
    assert got.status_code == 200
    assert got.json() == artifact(name)
    assert len(got.json()["points"]) >= 2                                  # the popup draws a curve, not the empty note


def test_research_equity_has_nothing_for_an_unknown_strategy(desk):
    assert desk.get("/api/research-equity", params={"strategy": "nope"}).json() == {"points": None}


# ---- config.json must not hide the pointer -------------------------------------------------------------
@pytest.fixture
def cfg_path(tmp_path, monkeypatch):
    p = tmp_path / "config.json"
    monkeypatch.setattr(config_mod, "config_path", lambda: p)
    return p


def test_a_config_saved_before_the_pointer_still_gets_it(cfg_path):
    """The desk's config.json holds each strategy's whole metrics dict (save() writes it).  One written before
    equity_file existed must not shadow the default's pointer after a restart; what the file does say stays."""
    saved = {}
    for n, s in config_mod._defaults().strategies.items():
        m = {k: v for k, v in s.metrics.items() if k != "equity_file"}
        saved[n] = {"qty": s.qty, "enabled": False, "metrics": m}
    saved["nq930"]["metrics"]["source"] = "edited by hand"
    cfg_path.write_text(json.dumps({"armed": False, "strategies": saved}))
    cfg = config_mod.load()
    for n in ("gc_nfp", "nq930"):
        assert cfg.strategies[n].metrics["equity_file"] == f"{n}_equity.json"
        assert (RESEARCH / cfg.strategies[n].metrics["equity_file"]).is_file()
    assert cfg.strategies["nq930"].metrics["source"] == "edited by hand"               # the file's own keys win
    assert cfg.strategies["nq930"].metrics["rows"] == config_mod._defaults().strategies["nq930"].metrics["rows"]
    config_mod.save(cfg)                                                   # and the next save carries the pointer
    again = json.loads(cfg_path.read_text())["strategies"]
    assert again["gc_nfp"]["metrics"]["equity_file"] == "gc_nfp_equity.json"
    assert config_mod.load().strategies["nq930"].metrics["source"] == "edited by hand"


def test_a_saved_pointer_wins_over_the_default(cfg_path):
    cfg_path.write_text(json.dumps({"strategies": {
        "nq930": {"metrics": {"equity_file": "ym930_equity.json"}},
        "gc_nfp": {"metrics": {"rev": 3, "equity_file": ""}}}}))
    cfg = config_mod.load()
    assert cfg.strategies["nq930"].metrics["equity_file"] == "ym930_equity.json"
    assert cfg.strategies["gc_nfp"].metrics["equity_file"] == ""           # switched off by hand: stays off
    assert cfg.strategies["nq930"].metrics["caveat"]                       # the rest comes from the defaults


def test_a_saved_strategy_without_metrics_keeps_the_defaults(cfg_path):
    cfg_path.write_text(json.dumps({"strategies": {"gc_nfp": {"qty": 2}}}))
    cfg = config_mod.load()
    assert cfg.strategies["gc_nfp"].qty == 2
    assert cfg.strategies["gc_nfp"].metrics == config_mod._defaults().strategies["gc_nfp"].metrics


def test_a_corrected_record_replaces_the_copy_saved_before_the_correction(cfg_path):
    """gc_nfp's record was corrected (rev 2: the 08:30:00 numbers on an 08:29:59 fire; rev 3: one setup for NFP
    and CPI). The shipped record carries "rev"; a saved copy with a lower rev is the stale text and must not
    shadow the correction."""
    d = config_mod._defaults().strategies["gc_nfp"].metrics
    assert d["rev"] == 3 and d["source"].startswith("GC 08:30 NFP + CPI straddle")
    stale = {**d, "rows": {**d["rows"], "TP": "7.7 pts old"}, "caveat": "old"}
    stale.pop("rev")
    cfg_path.write_text(json.dumps({"strategies": {"gc_nfp": {"qty": 4, "enabled": True, "metrics": stale}}}))
    cfg = config_mod.load()
    assert cfg.strategies["gc_nfp"].metrics == d
    assert cfg.strategies["gc_nfp"].enabled is True and cfg.strategies["gc_nfp"].qty == 4   # only the record changes
    config_mod.save(cfg)
    cfg.strategies["gc_nfp"].metrics["source"] = "edited by hand"          # a later hand edit (same rev) still wins
    config_mod.save(cfg)
    assert config_mod.load().strategies["gc_nfp"].metrics["source"] == "edited by hand"
