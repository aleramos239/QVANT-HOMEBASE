"""Server: secret gate, status shape, book/accounts flows, readiness,
calendar. No network."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import homebase.config as config_mod
from homebase.config import AccountCfg, AppCfg, StrategyCfg
from homebase.server import create_app
from tests.test_engine import FakeAdapter


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.engine.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.server.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.secrets_store.state_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    cfg = AppCfg(armed=False, webhook_secret="tv-secret",
                 accounts={"main": AccountCfg(keyring_key="k",
                                              account_name="MAIN")},
                 book={"nq930": [{"account": "main", "qty": 3}]},
                 strategies={"nq930": StrategyCfg(symbol="NQ", qty=3,
                                                  offset_pts=10.0, sl_pts=5.0,
                                                  tp_pts=15.0, enabled=True)})
    adapters = {"main": FakeAdapter("main")}
    app = create_app(cfg, adapters, background=False,
                     adapter_factory=lambda aid, a: FakeAdapter(aid))
    with TestClient(app) as c:
        c.app = app
        c.adapters = adapters
        c.adapter = adapters["main"]
        yield c


def test_hook_rejects_bad_secret(client):
    r = client.post("/hook", json={"secret": "wrong", "strategy": "nq930",
                                   "upper": 24510.0, "lower": 24490.0})
    assert r.status_code == 401


def test_hook_good_secret_dry_run(client):
    r = client.post("/hook", json={"secret": "tv-secret", "strategy": "nq930",
                                   "upper": 24510.0, "lower": 24490.0})
    assert r.status_code == 200
    assert r.json()["ok"] in (True, False)      # window-dependent, never 500
    assert client.adapter.brackets == []        # disarmed: nothing placed


def test_status_shape(client):
    d = client.get("/api/status").json()
    assert d["armed"] is False
    s = d["strategies"]["nq930"]
    assert s["cfg"]["qty"] == 3
    assert s["day_status"] == "idle"
    assert "research" in s and "live" in s
    assert d["book"] == {"nq930": [{"account": "main", "qty": 3}]}
    assert d["accounts"]["main"]["label"] == "MAIN"


def test_hook_app_exposes_only_the_hook(client):
    hook_app = client.app.state.hook_app
    paths = {r.path for r in hook_app.routes if hasattr(r, "path")}
    assert "/hook" in paths
    assert not any(p.startswith("/api") or p == "/" for p in paths)
    hc = TestClient(hook_app)
    assert hc.post("/hook", json={"secret": "tv-secret", "strategy": "nq930",
                                  "upper": 24510.0,
                                  "lower": 24490.0}).status_code == 200
    assert hc.get("/api/status").status_code == 404


def test_hook_url_persists_into_tv_setup(client):
    client.post("/api/hook-url", json={"url": "https://x.trycloudflare.com/"})
    d = client.get("/api/tv-setup").json()
    assert d["public_hook_url"] == "https://x.trycloudflare.com/hook"


def test_arm_toggle_persists(client):
    r = client.post("/api/arm", json={"armed": True}).json()
    assert r["armed"] is True
    assert client.get("/api/status").json()["armed"] is True


def test_test_alert_refused_while_armed(client):
    client.post("/api/arm", json={"armed": True})
    assert client.post("/api/test-alert",
                       json={"strategy": "nq930"}).status_code == 409


def test_test_alert_dry_run_places_nothing(client):
    r = client.post("/api/test-alert", json={"strategy": "nq930"})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["ok"] is True and body["result"]["armed"] is False
    assert client.adapter.brackets == []


def test_logins_list_and_delete(client):
    import homebase.secrets_store as ss
    ss.set_credentials("tv:demo:abc", username="abc", password="x")
    d = client.get("/api/logins").json()
    assert "tv:demo:abc" in [l["key"] for l in d["logins"]]
    assert client.post("/api/logins/delete",
                       json={"key": "tv:demo:abc"}).json()["ok"]
    assert ss.get_credentials("tv:demo:abc") is None


def test_connect_probes_and_returns_key(client):
    import homebase.secrets_store as ss
    r = client.post("/api/connect", json={"username": "NewGuy",
                                          "password": "x"}).json()
    assert r["ok"] is True and r["key"] == "tv:demo:newguy"
    assert ss.get_credentials("tv:demo:newguy")["username"] == "NewGuy"
    assert "main" in client.app.state.cfg.accounts   # pool untouched by probe
    assert len(client.app.state.cfg.accounts) == 1


def test_accounts_add_creates_and_connects(client):
    import homebase.secrets_store as ss
    ss.set_credentials("tv:demo:z", username="z", password="x")
    r = client.post("/api/accounts/add",
                    json={"key": "tv:demo:z", "account_name": "EVAL77",
                          "label": "Eval"}).json()
    assert r["ok"] is True and r["account"] == "eval77"
    cfg = client.app.state.cfg
    assert cfg.accounts["eval77"].keyring_key == "tv:demo:z"
    assert cfg.accounts["eval77"].live is False
    assert "eval77" in client.app.state.adapters


def test_book_endpoint_sets_assignments(client):
    import homebase.secrets_store as ss
    ss.set_credentials("tv:demo:z", username="z", password="x")
    client.post("/api/accounts/add", json={"key": "tv:demo:z",
                                           "account_name": "EVAL77"})
    r = client.post("/api/book", json={
        "strategy": "nq930",
        "assignments": [{"account": "main", "qty": 2},
                        {"account": "eval77", "qty": 1}]}).json()
    assert r["ok"] is True
    assert r["book"]["nq930"] == [{"account": "main", "qty": 2},
                                  {"account": "eval77", "qty": 1}]
    bad = client.post("/api/book", json={"strategy": "nq930",
                                         "assignments": [{"account": "nope",
                                                          "qty": 1}]})
    assert bad.status_code == 400


def test_readiness_reflects_accounts_and_book(client):
    d = client.get("/api/status").json()
    r = d["readiness"]
    by = {c["label"]: c for c in r["checks"]}
    assert by["MAIN"]["level"] == "bad"          # FakeAdapter never "connects"
    assert r["ready"] is False
    # strategy enabled but unassigned -> warn
    client.post("/api/book", json={"strategy": "nq930", "assignments": []})
    r2 = client.get("/api/status").json()["readiness"]
    assert any(c["label"] == "nq930" and "no accounts assigned" in c["detail"]
               for c in r2["checks"])


def test_calendar_close_over_close(client, tmp_path):
    from homebase import server as S
    for date, eq in [("2026-09-09", 50000.0), ("2026-09-10", 50250.0),
                     ("2026-09-11", 50100.0)]:
        S.record_equity("ACC1", eq, date)
    d = client.get("/api/calendar", params={"month": "2026-09",
                                            "account": "ACC1"}).json()
    assert d["days"]["2026-09-10"] == 250.0
    assert d["days"]["2026-09-11"] == -150.0
    assert "2026-09-09" not in d["days"]
    assert d["total"] == 100.0


def test_strategy_toggle(client):
    r = client.post("/api/strategy", json={"strategy": "nq930",
                                           "enabled": False}).json()
    assert r["ok"] is True and r["enabled"] is False
    assert client.app.state.cfg.strategies["nq930"].enabled is False
    out = client.post("/api/test-alert", json={"strategy": "nq930"}).json()
    assert out["result"]["ok"] is False          # disabled ignores signals
    client.post("/api/strategy", json={"strategy": "nq930", "enabled": True})
    assert client.post("/api/strategy",
                       json={"strategy": "nope", "enabled": True}).status_code == 404


def test_kill_disarms_and_clears_every_account(client):
    client.post("/api/arm", json={"armed": True})
    r = client.post("/api/kill").json()
    assert r["armed"] is False
    ad = client.adapter
    assert ad.cancel_all_calls == 1 and ad.flatten_calls == 1
    assert "main" in r["results"]
