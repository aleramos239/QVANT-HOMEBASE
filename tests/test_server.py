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
    created = []                       # every adapter the app builds (probes too)

    def factory(aid, a):
        ad = FakeAdapter(aid)
        ad.cfg = a
        created.append(ad)
        return ad

    app = create_app(cfg, adapters, background=False, adapter_factory=factory)
    with TestClient(app) as c:
        c.app = app
        c.adapters = adapters
        c.adapter = adapters["main"]
        c.created = created
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


def test_strategy_flatten_disables(client):
    r = client.post("/api/strategy-flatten", json={"strategy": "nq930"}).json()
    assert r["ok"] is True and r["enabled"] is False
    assert client.app.state.cfg.strategies["nq930"].enabled is False


def test_accounts_remove_unassigns_and_drops(client):
    r = client.post("/api/accounts/remove", json={"account": "main"}).json()
    assert r["ok"] is True
    cfg = client.app.state.cfg
    assert "main" not in cfg.accounts
    assert cfg.book["nq930"] == []
    assert "main" not in client.app.state.adapters
    assert client.post("/api/accounts/remove",
                       json={"account": "nope"}).status_code == 404


def test_manual_reconnect_endpoint(client):
    r = client.post("/api/accounts/reconnect", json={"account": "main"}).json()
    assert r["ok"] is True and r["results"]["main"]["ok"] is True
    all_ = client.post("/api/accounts/reconnect", json={}).json()
    assert "main" in all_["results"]
    bad = client.post("/api/accounts/reconnect", json={"account": "nope"}).json()
    assert bad["results"]["nope"]["ok"] is False


def test_strategy_live_detail_from_real_fills_only(client, tmp_path):
    import json as _j
    j = tmp_path / "journal.jsonl"
    rows = [
        # a dry run and a self-test must NOT count
        {"et": "2026-09-16T09:30:00", "event": "dry_run", "strategy": "nq930"},
        {"et": "2026-09-16T23:00:00", "event": "selftest_order", "account": "main"},
        # day 1: short, stopped out, no slippage
        {"et": "2026-09-17T09:30:00", "event": "placed", "strategy": "nq930",
         "account": "main", "qty": 3},
        {"et": "2026-09-17T09:30:07", "event": "entry_fill", "strategy": "nq930",
         "account": "main", "side": "Sell", "fill": 29718.0, "anchor": 29718.0},
        {"et": "2026-09-17T09:30:09", "event": "exit_fill", "strategy": "nq930",
         "account": "main", "reason": "sl", "fill": 29723.0, "pnl": -300.0},
        # day 2: long, target, 2 ticks of exit slippage
        {"et": "2026-09-18T09:30:00", "event": "placed", "strategy": "nq930",
         "account": "main", "qty": 3},
        {"et": "2026-09-18T09:30:01", "event": "entry_fill", "strategy": "nq930",
         "account": "main", "side": "Buy", "fill": 29824.0, "anchor": 29824.0},
        {"et": "2026-09-18T09:31:00", "event": "exit_fill", "strategy": "nq930",
         "account": "main", "reason": "tp", "fill": 29838.5, "pnl": 870.0},
    ]
    j.write_text("".join(_j.dumps(r) + "\n" for r in rows))
    d = client.get("/api/strategy-live", params={"strategy": "nq930"}).json()
    assert len(d["trades"]) == 2
    assert d["days"]["2026-09-17"]["gross"] == -300.0
    assert d["days"]["2026-09-18"]["wins"] == 1
    t2 = d["trades"][1]
    assert t2["entry_slip_ticks"] == 0.0
    assert t2["exit_slip_ticks"] == 2.0          # TP level 29839.0, filled 29838.5
    assert t2["net"] == round(870.0 - 3.10 * 3, 2)
    table = {k: v for _, k, v in d["table"]}
    assert table["win rate"] == "50.0%"
    assert table["trades"] == "2"
    assert client.get("/api/strategy-live",
                      params={"strategy": "nope"}).status_code == 404


def test_exit_slippage_measured_from_the_moved_brackets(client, tmp_path):
    """SL/TP re-priced to the fill: the TP at 24525.25 filling at 24525.25 is
    0 ticks of slippage — not '1 better' against the old trigger level."""
    import json as _j
    rows = [
        {"et": "2026-09-22T09:30:00", "event": "placed", "strategy": "nq930",
         "account": "main", "qty": 3},
        {"et": "2026-09-22T09:30:01", "event": "entry_fill", "strategy": "nq930",
         "account": "main", "side": "Buy", "fill": 24510.25, "anchor": 24510.0},
        {"et": "2026-09-22T09:30:01", "event": "brackets_moved", "strategy": "nq930",
         "account": "main", "fill": 24510.25, "sl": 24505.25, "tp": 24525.25,
         "moved": True},
        {"et": "2026-09-22T09:31:00", "event": "exit_fill", "strategy": "nq930",
         "account": "main", "reason": "tp", "fill": 24525.25, "pnl": 900.0},
    ]
    (tmp_path / "journal.jsonl").write_text("".join(_j.dumps(r) + "\n" for r in rows))
    t = client.get("/api/strategy-live", params={"strategy": "nq930"}).json()["trades"][0]
    assert t["entry_slip_ticks"] == 1.0 and t["exit_slip_ticks"] == 0.0


def test_live_login_probes_live_and_the_account_is_live(client):
    r = client.post("/api/connect", json={"username": "RealMe", "password": "x",
                                          "env": "live"}).json()
    assert r["ok"] is True and r["key"] == "tv:live:realme"
    assert client.created[-1].cfg.live is True          # the probe logged in LIVE
    add = client.post("/api/accounts/add", json={"key": "tv:live:realme",
                                                 "account_name": "LIVE123"}).json()
    assert add["ok"] is True
    assert client.app.state.cfg.accounts["live123"].live is True
    # never auto-assigned: it trades only once the user assigns it
    assert client.app.state.cfg.book["nq930"] == [{"account": "main", "qty": 3}]
    # a saved live login stays live on the next connect
    again = client.post("/api/connect", json={"saved_key": "tv:live:realme"}).json()
    assert again["ok"] and client.created[-1].cfg.live is True


def test_live_login_with_a_colon_in_the_username_stays_live(client):
    """2026-09-21: a Google-linked login is 'Google:1012...'. The key
    'tv:live:google:1012...' has FOUR colon parts; it was read as demo, the
    account connected to demo and found no accounts."""
    r = client.post("/api/connect", json={"username": "Google:1012", "password": "x",
                                          "env": "live"}).json()
    assert r["key"] == "tv:live:google:1012" and client.created[-1].cfg.live is True
    client.post("/api/accounts/add", json={"key": "tv:live:google:1012",
                                           "account_name": "1552885"})
    assert client.app.state.cfg.accounts["1552885"].live is True
    envs = {l["key"]: l["env"] for l in client.get("/api/logins").json()["logins"]}
    assert envs["tv:live:google:1012"] == "live"


def test_demo_stays_the_default_login(client):
    r = client.post("/api/connect", json={"username": "Guy", "password": "x"}).json()
    assert r["key"] == "tv:demo:guy" and client.created[-1].cfg.live is False


def test_market_data_takes_host_and_token_from_one_login():
    """The md token only works on its own env's md host. Demo first (the
    proven feed); never a live host with the demo login's token."""
    from types import SimpleNamespace as NS
    from homebase.server import md_source
    cfg = AppCfg(accounts={
        "live1": AccountCfg(keyring_key="tv:live:me", account_name="L", live=True),
        "main": AccountCfg(keyring_key="tv:demo:me", account_name="M")})
    demo, live = FakeAdapter("main"), FakeAdapter("live1")
    demo._auth = NS(tokens=NS(md_access_token="demo-md"))
    live._auth = NS(tokens=NS(md_access_token="live-md"))
    key, env, tok = md_source(cfg, {"main": demo, "live1": live})
    assert (key, env, tok()) == ("tv:demo:me", "demo", "demo-md")
    demo._connected = False
    key, env, tok = md_source(cfg, {"main": demo, "live1": live})
    assert (key, env, tok()) == ("tv:live:me", "live", "live-md")


def test_kill_disarms_and_clears_every_account(client):
    client.post("/api/arm", json={"armed": True})
    r = client.post("/api/kill").json()
    assert r["armed"] is False
    ad = client.adapter
    assert ad.cancel_all_calls == 1 and ad.flatten_calls == 1
    assert "main" in r["results"]
