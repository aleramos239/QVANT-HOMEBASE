"""Server: secret gate, status shape, arm/kill/test-alert flows. No network."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

import homebase.config as config_mod
from homebase.config import AccountCfg, AppCfg, StrategyCfg
from homebase.server import create_app
from tests.test_engine import FakeAdapter


@pytest.fixture()
def client(tmp_path, monkeypatch):
    # keep every state/config write inside tmp_path
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.engine.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.server.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.secrets_store.state_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    cfg = AppCfg(armed=False, webhook_secret="tv-secret", account=AccountCfg(),
                 strategies={"nq930": StrategyCfg(symbol="NQ", qty=3,
                                                  offset_pts=10.0, sl_pts=5.0,
                                                  tp_pts=15.0, enabled=True)})
    app = create_app(cfg, FakeAdapter(), background=False,
                     adapter_factory=lambda c: FakeAdapter())
    with TestClient(app) as c:
        c.app = app
        c.adapter = app_adapter(app)
        yield c


def app_adapter(app):
    return app.state.engine.adapter


def test_hook_rejects_bad_secret(client):
    r = client.post("/hook", json={"secret": "wrong", "strategy": "nq930",
                                   "upper": 24510.0, "lower": 24490.0})
    assert r.status_code == 401


def test_hook_good_secret_dry_run(client):
    r = client.post("/hook", json={"secret": "tv-secret", "strategy": "nq930",
                                   "upper": 24510.0, "lower": 24490.0})
    # disarmed => valid alerts are refused only by window or accepted as dry
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] in (True, False)   # window-dependent; never a 500
    assert client.adapter.brackets == [] # and never an order while disarmed


def test_status_shape(client):
    d = client.get("/api/status").json()
    assert d["armed"] is False
    assert "nq930" in d["strategies"]
    assert d["strategies"]["nq930"]["cfg"]["qty"] == 3
    assert d["strategies"]["nq930"]["state"]["status"] == "idle"
    assert "connected" in d["broker"]


def test_arm_toggle_persists(client):
    r = client.post("/api/arm", json={"armed": True}).json()
    assert r["armed"] is True
    assert client.get("/api/status").json()["armed"] is True


def test_test_alert_refused_while_armed(client):
    client.post("/api/arm", json={"armed": True})
    r = client.post("/api/test-alert", json={"strategy": "nq930"})
    assert r.status_code == 409


def test_test_alert_dry_run_places_nothing(client):
    r = client.post("/api/test-alert", json={"strategy": "nq930"})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["ok"] is True and body["result"]["armed"] is False
    assert body["sent"]["upper"] - body["sent"]["lower"] == 20.0
    assert client.adapter.brackets == []


def test_connect_stores_demo_login_and_reconnects(client):
    r = client.post("/api/connect", json={"username": "Demo", "password": "x",
                                          "account_name": "ACC1"}).json()
    assert r["ok"] is True
    import homebase.secrets_store as ss
    assert ss.get_credentials("tv:demo:demo")["username"] == "Demo"
    cfg = client.app.state.cfg
    assert cfg.account.keyring_key == "tv:demo:demo"
    assert cfg.account.live is False          # /api/connect can never go live
    assert client.app.state.engine.adapter is not client.adapter  # swapped


def test_tv_setup_shape(client):
    d = client.get("/api/tv-setup").json()
    assert d["hook_path"] == "/hook" and d["secret"] == "tv-secret"
    assert "nq930" in d["strategies"]
    assert "24510" in d["strategies"]["nq930"]["alert_body_example"]


def test_kill_disarms_and_clears(client):
    client.post("/api/arm", json={"armed": True})
    r = client.post("/api/kill").json()
    assert r["armed"] is False
    ad = client.adapter
    assert ad.cancel_all_calls == 1 and ad.flatten_calls == 1
