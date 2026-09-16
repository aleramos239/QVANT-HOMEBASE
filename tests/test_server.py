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


def test_logins_list_and_delete(client):
    import homebase.secrets_store as ss
    ss.set_credentials("tv:demo:abc", username="abc", password="x")
    d = client.get("/api/logins").json()
    keys = [l["key"] for l in d["logins"]]
    assert "tv:demo:abc" in keys
    assert client.post("/api/logins/delete", json={"key": "tv:demo:abc"}).json()["ok"]
    assert ss.get_credentials("tv:demo:abc") is None


def test_connect_with_saved_key(client):
    import homebase.secrets_store as ss
    ss.set_credentials("tv:demo:saved", username="saved", password="x")
    r = client.post("/api/connect", json={"saved_key": "tv:demo:saved"}).json()
    assert r["ok"] is True and "accounts" in r
    assert client.app.state.cfg.account.keyring_key == "tv:demo:saved"


def test_select_account_pins_and_reconnects(client):
    r = client.post("/api/select-account", json={"account_name": "ACC9"}).json()
    assert r["ok"] is True
    assert client.app.state.cfg.account.account_name == "ACC9"


def test_calendar_close_over_close(client, tmp_path):
    from homebase import server as S
    for date, eq in [("2026-09-09", 50000.0), ("2026-09-10", 50250.0),
                     ("2026-09-11", 50100.0)]:
        S.record_equity("ACC1", eq, date)
    d = client.get("/api/calendar", params={"month": "2026-09",
                                            "account": "ACC1"}).json()
    assert d["days"]["2026-09-10"] == 250.0
    assert d["days"]["2026-09-11"] == -150.0
    assert "2026-09-09" not in d["days"]     # first day has no prior close
    assert d["total"] == 100.0


def test_readiness_in_status_and_logic(client):
    d = client.get("/api/status").json()
    r = d["readiness"]
    assert r["ready"] is False                      # FakeAdapter not connected
    assert any(c["label"] == "Broker" and c["level"] == "bad" for c in r["checks"])

    import datetime as dt
    from homebase.server import compute_readiness, should_fire_readiness
    from homebase.config import StrategyCfg
    cfg = client.app.state.cfg
    cfg.strategies["ym"] = StrategyCfg(symbol="YM", qty=1, offset_pts=20,
                                       sl_pts=5, tp_pts=15, enabled=True)
    cfg.strategies["nq930"].gated = True
    ten_am = dt.datetime(2026, 9, 14, 10, 0)       # Monday, after window
    r2 = compute_readiness(ten_am, cfg, {}, True, None)
    by = {c["label"]: c["level"] for c in r2["checks"]}
    assert by["ym"] == "bad"                        # unfiltered: missed alert
    assert by["nq930"] == "warn"                    # gated: could be the gate
    assert r2["ready"] is False

    assert should_fire_readiness(dt.datetime(2026, 9, 14, 9, 26), None) is True
    assert should_fire_readiness(dt.datetime(2026, 9, 14, 9, 26), "2026-09-14") is False
    assert should_fire_readiness(dt.datetime(2026, 9, 13, 9, 26), None) is False  # Sunday
    assert should_fire_readiness(dt.datetime(2026, 9, 14, 9, 10), None) is False


def test_kill_disarms_and_clears(client):
    client.post("/api/arm", json={"armed": True})
    r = client.post("/api/kill").json()
    assert r["armed"] is False
    ad = client.adapter
    assert ad.cancel_all_calls == 1 and ad.flatten_calls == 1
