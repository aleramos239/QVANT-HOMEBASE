"""Add several accounts of one login at once (the connect wizard's checkboxes):
POST /api/connect lists a login's accounts (marking those already on the desk),
POST /api/accounts/add-many adds the ticked ones. Fakes only, no network.

What is pinned: N accounts cost ONE login (the wizard's probe -- the entries ride its
shared token by reconnecting); nothing is booked or assigned; every entry is pinned to
its own broker account; the login budget applies to the probe; nothing is added
09:20-09:35 ET on weekdays; the batch stops at the first failure that could spend another
login; one row per account: added, exists or failed with the reason."""
from __future__ import annotations

import datetime as dt
from types import SimpleNamespace as NS
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import homebase.config as config_mod
import homebase.secrets_store as ss
from homebase.config import AccountCfg, AppCfg, StrategyCfg
from homebase.server import create_app
from tests.test_engine import FakeAdapter
from tests.test_login_budget import S429

KEY = "tv:live:apex"
EVALS = [f"APEX-{n}" for n in range(1, 7)]
ET = ZoneInfo("America/New_York")


class World:
    """The Tradovate side: one shared token per login key, a login counter."""

    def __init__(self):
        self.shared: dict = {}
        self.logins: list[str] = []
        self.accounts = [{"id": 100 + i, "name": n, "active": True} for i, n in enumerate(EVALS)]
        self.login_error: Exception | None = None
        self.reconnect_errors: dict[str, Exception] = {}


def make_adapter_factory(world: World):
    def factory(aid, a):
        ad = FakeAdapter(aid)
        ad.cfg = a
        ad._connected = False
        ad._auth = world.shared.setdefault(a.keyring_key, NS(tokens=None))

        async def connect():
            world.logins.append(aid)
            if world.login_error:
                raise world.login_error
            ad._auth.tokens = NS(access_token="T", expires_at_unix=9e12)
            ad._connected = True
        async def reconnect():
            if a.account_name in world.reconnect_errors:
                raise world.reconnect_errors[a.account_name]
            ad._connected = True
        ad.connect, ad.reconnect = connect, reconnect
        ad.list_accounts = lambda: list(world.accounts)
        return ad
    return factory


@pytest.fixture()
def world():
    return World()


@pytest.fixture()
def client(tmp_path, monkeypatch, world):
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.engine.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.server.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.secrets_store.state_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    cfg = AppCfg(armed=False, webhook_secret="tv-secret",
                 accounts={"main": AccountCfg(keyring_key="k", account_name="MAIN")},
                 book={"nq930": [{"account": "main", "qty": 3}]},
                 strategies={"nq930": StrategyCfg(symbol="NQ", qty=3, offset_pts=10.0,
                                                  sl_pts=5.0, tp_pts=15.0, enabled=True)})
    app = create_app(cfg, {"main": FakeAdapter("main")}, background=False,
                     adapter_factory=make_adapter_factory(world))
    app.state.engine.now_et = lambda: dt.datetime(2026, 9, 30, 10, 0, tzinfo=ET)   # a Wednesday
    ss.set_credentials(KEY, username="apex", password="x")
    with TestClient(app, base_url="http://127.0.0.1:8850") as c:
        c.app = app
        yield c


def clock(client, h, m, day=30):
    client.app.state.engine.now_et = lambda: dt.datetime(2026, 9, day, h, m, tzinfo=ET)


def look_up(client):
    r = client.post("/api/connect", json={"saved_key": KEY}).json()
    assert r["ok"], r
    return r


def add(client, names):
    return client.post("/api/accounts/add-many", json={"key": KEY, "accounts": names})


def test_connect_marks_the_accounts_already_on_the_desk(client):
    cfg = client.app.state.cfg
    cfg.accounts["apex"] = AccountCfg(keyring_key=KEY, account_name="apex-2", live=True)   # pinned
    cfg.accounts["other"] = AccountCfg(keyring_key="tv:live:else", account_name="APEX-3", live=True)
    r = look_up(client)
    on = {a["name"]: a["on_desk"] for a in r["accounts"]}
    assert on == {"APEX-1": False, "APEX-2": True, "APEX-3": False, "APEX-4": False,
                  "APEX-5": False, "APEX-6": False}     # another login's entry is not this login's


def test_n_accounts_cost_one_login(client, world):
    look_up(client)
    assert len(world.logins) == 1                      # the wizard's probe
    r = add(client, EVALS[:4]).json()
    assert r["ok"] and (r["added"], r["exists"], r["failed"]) == (4, 0, 0)
    assert len(world.logins) == 1                      # four accounts, still ONE login
    assert [x["mode"] for x in r["results"]] == ["reconnect"] * 4
    cfg = client.app.state.cfg
    for n in EVALS[:4]:
        a = cfg.accounts[n.lower()]
        assert (a.keyring_key, a.account_name, a.live, a.label) == (KEY, n, True, n)
    assert set(client.app.state.adapters) == {"main", *(n.lower() for n in EVALS[:4])}
    assert all(client.app.state.adapters[n.lower()]._auth is world.shared[KEY] for n in EVALS[:4])


def test_nothing_is_booked_or_assigned(client):
    look_up(client)
    add(client, EVALS)
    cfg = client.app.state.cfg
    assert cfg.book == {"nq930": [{"account": "main", "qty": 3}]}
    assert client.app.state.cfg.strategies["nq930"].enabled is True
    saved = config_mod.load()
    assert saved.book == cfg.book and len(saved.accounts) == 1 + len(EVALS)


def test_one_row_per_account_added_exists_failed(client):
    client.app.state.cfg.accounts["apex"] = AccountCfg(keyring_key=KEY, account_name="APEX-2", live=True)
    look_up(client)
    r = add(client, ["APEX-1", "apex-2", "APEX-9", "APEX-1"]).json()
    assert r["ok"] is False and (r["added"], r["exists"], r["failed"]) == (1, 1, 1)
    rows = {x["name"]: x for x in r["results"]}
    assert len(r["results"]) == 3                                   # the repeat is one row
    assert rows["APEX-1"]["status"] == "added" and rows["APEX-1"]["connected"] is True
    assert rows["apex-2"] == {"name": "apex-2", "status": "exists", "id": "apex"}
    assert rows["APEX-9"]["status"] == "failed" and "not on this login" in rows["APEX-9"]["error"]
    assert "apex-9" not in client.app.state.cfg.accounts
    again = add(client, ["APEX-1"]).json()                          # a second click: already there
    assert (again["added"], again["exists"]) == (0, 1)


def test_an_account_the_desk_rides_unpinned_counts_as_already_there(client):
    client.app.state.cfg.accounts["apex"] = AccountCfg(keyring_key=KEY, live=True)   # no pin
    client.app.state.adapters["apex"] = NS(_acct_name="APEX-3")
    r = look_up(client)
    assert {a["name"]: a["on_desk"] for a in r["accounts"]}["APEX-3"] is True


def test_the_probe_login_goes_through_the_budget(client, world):
    client.app.state.login_budget.note_error(KEY, S429)             # Tradovate said 429
    r = client.post("/api/connect", json={"saved_key": KEY}).json()
    assert r["ok"] is False and "rate-limited" in r["error"] and world.logins == []
    assert client.post("/api/accounts/add-many",
                       json={"key": KEY, "accounts": ["APEX-1"]}).status_code == 409


def test_a_failed_probe_login_feeds_the_budget(client, world):
    world.login_error = RuntimeError(S429)
    assert client.post("/api/connect", json={"saved_key": KEY}).json()["ok"] is False
    assert client.app.state.login_budget.cooling(KEY) > 0


def test_needs_a_lookup_first_and_a_known_login(client):
    assert add(client, ["APEX-1"]).status_code == 409
    look_up(client)
    assert client.post("/api/accounts/add-many",
                       json={"key": "tv:live:nobody", "accounts": ["APEX-1"]}).status_code == 400
    for bad in ([], "APEX-1", [1], [" "]):
        assert client.post("/api/accounts/add-many",
                           json={"key": KEY, "accounts": bad}).status_code == 400


@pytest.mark.parametrize("hm", [(9, 20), (9, 27), (9, 34)])
def test_refused_in_the_930_window(client, world, hm):
    look_up(client)
    clock(client, *hm)
    r = add(client, ["APEX-1"])
    assert r.status_code == 409 and "09:20-09:35" in r.json()["detail"]
    assert "apex-1" not in client.app.state.cfg.accounts
    single = client.post("/api/accounts/add", json={"key": KEY, "account_name": "APEX-1"})
    assert single.status_code == 409


@pytest.mark.parametrize("hm,day", [((9, 19), 30), ((9, 35), 30), ((9, 27), 26)])   # 26 = a Saturday
def test_allowed_outside_the_window(client, hm, day):
    look_up(client)
    clock(client, *hm, day=day)
    assert add(client, ["APEX-1"]).json()["added"] == 1


def test_the_window_opening_mid_batch_stops_it(client):
    look_up(client)
    times = iter([dt.datetime(2026, 9, 30, 9, 19, 59, tzinfo=ET)] * 3 +      # request check + 1st account
                 [dt.datetime(2026, 9, 30, 9, 20, 1, tzinfo=ET)] * 20)
    client.app.state.engine.now_et = lambda: next(times)
    r = add(client, EVALS[:3]).json()
    st = [x["status"] for x in r["results"]]
    assert st == ["added", "failed", "failed"] and "09:20-09:35" in r["results"][1]["error"]


def test_an_entry_that_had_to_log_in_again_stops_the_batch(client, world):
    look_up(client)
    world.reconnect_errors["APEX-2"] = RuntimeError("authorize failed: bad token")
    r = add(client, EVALS[:4]).json()
    st = [(x["name"], x["status"], x.get("mode")) for x in r["results"]]
    assert st == [("APEX-1", "added", "reconnect"), ("APEX-2", "added", "login"),
                  ("APEX-3", "failed", None), ("APEX-4", "failed", None)]
    assert "not tried" in r["results"][2]["error"] and "log in again" in r["results"][2]["error"]
    assert "apex-3" not in client.app.state.cfg.accounts
    assert len(world.logins) == 2                    # the probe, and the one that fell back: no more


def test_a_failed_connect_stops_the_batch_and_reports_why(client, world):
    look_up(client)
    world.reconnect_errors["APEX-2"] = RuntimeError("authorize failed: bad token")
    world.login_error = RuntimeError("Login failed: p-ticket")
    r = add(client, EVALS[:4]).json()
    st = [(x["name"], x["status"], x.get("connected")) for x in r["results"]]
    assert st == [("APEX-1", "added", True), ("APEX-2", "added", False),      # on the desk, not up
                  ("APEX-3", "failed", None), ("APEX-4", "failed", None)]
    assert "Login failed" in r["results"][1]["error"]
    assert "not tried" in r["results"][2]["error"]
    assert "apex-2" in client.app.state.cfg.accounts and "apex-3" not in client.app.state.cfg.accounts
    assert (r["added"], r["exists"], r["failed"]) == (2, 0, 2) and r["ok"] is False


def test_adding_is_journaled(client, tmp_path):
    import json
    look_up(client)
    add(client, EVALS[:2])
    ev = [json.loads(l) for l in (tmp_path / "journal.jsonl").read_text().splitlines()]
    names = [e["event"] for e in ev]
    assert names.count("account_added") == 2 and names.count("accounts_added_batch") == 1
    assert [e for e in ev if e["event"] == "accounts_added_batch"][0]["added"] == 2
