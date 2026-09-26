# Trading from the chart — backend + desk page — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The desk (:8850) can take orders from the chart page, and it does so safely. Only the desk talks to Tradovate. It runs guards and a bot lock and journals every action. The chart service (:8852) relays the desk's live state to the pages and proxies the pages' trading requests to the desk with a desk key. The chart PAGE UI is a later plan.

**Architecture:**
- The Tradovate adapter first stops silently falling back to another account when the pinned one is missing.
- The adapter then gains an entity listener, position and cash caches, and symbol-scoped flatten/cancel.
- A new `homebase/trading.py` `ChartDesk` holds the per-account and bot views, runs the guards and journals.
- A new `homebase/desk_api.py` serves `/api/trade/*`: key and no-Origin only, with SSE.
- The desk page gets a switch and limits.
- At 09:28:30 the timer skips any booked account that already holds the bot's symbol.
- The chart service gains `homebase/charts/desk.py`: the SSE client, fan-out, the proxy, and bid/ask from the ticks.

**Tech Stack:** Python 3 / FastAPI 0.141 / Starlette 1.6 / uvicorn 0.53 / httpx 0.28 / pytest; plain browser JS in `homebase/static/index.html`.

**Spec:** `docs/superpowers/specs/2026-09-26-desk-on-chart-trading-design.md` (APPROVED; the binding authority).

## Global Constraints

- Tests never open broker connections, never read tokens or the keychain, never write under `~/futures_ticks`.
- No real order is ever placed by anyone but the user.
- Never touch `/Users/ramoscapital/ramos-quant-homebase` outside `.worktrees/desk-trading`.
- Never restart services or run `deploy/install.sh` (deploying needs a desk restart the user approves separately).
- The 9:30 fire path changes ONLY by the prestage skip.
- The full existing suite stays green.
- Commit on `feat/desk-trading` with the trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- The user's shell hook blocks `rm -rf` and any single command containing both the words "live" and "tradovate". Plan test commands must not contain both words; test file names are fine as long as a single command line avoids the pair. **This includes commit messages:** a `git commit` whose `git add` names `homebase/broker/tradovate.py` must not contain the letters `live` anywhere (watch out for "deliver", "alive", "keepalive").
- Work only in `/Users/ramoscapital/ramos-quant-homebase/.worktrees/desk-trading` (branch `feat/desk-trading`). Python is `.venv/bin/python`, a symlink to the live venv: never `pip install`. Run tests as `.venv/bin/python -m pytest -q …` from the worktree root.
- Chart-service tests never reach the real desk. `create_app(desk_factory=None)` is the default. Every `DeskLink` in a test gets an `httpx.MockTransport`. Desk-side tests monkeypatch `state_dir`/`config_path` to `tmp_path`, as `tests/test_server.py` does.
- `homebase/symbols.py` and `homebase/contracts.py` are imported by the trading engine: this plan does not change them.
- `homebase/server.py` and `homebase/charts/server.py` are also edited on another branch: keep every diff there to the small, listed insertions.
- Journal events written by chart trading (`manual_*`, `chart_trading_set`) never carry a `strategy` key. `metrics.py` then never counts them as bot trades.
- Never push. Commit with `git add <your files>` then `git commit -m "<subject>" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"`.

## Rulings on spec ambiguities (binding for this plan)

1. **`/ws` message key.** The spec writes `{"t": "desk", …}`, but every existing `/ws` message and the page's dispatcher (`app.js` `m.type`) use `type`. So desk messages are `{"type": "desk", "event": <state|account|bot|fill|result>, "data": …}` or `{"type": "desk", "down": "<reason>"}`. Quotes go out as `{"type": "quote", …}`.
2. **Bid/ask comes from the ticks, not `md/subscribeQuote`.** The repo has evidence only for `md/getChart` counting against the 180/h budget, and none that quote subscriptions are exempt. That budget belongs to the demo md login whose token the desk timer's 09:28:30 anchor quote also uses. The fallback is exact enough: every tick row carries the bid/ask at that trade, labelled `"asof": "last_trade"`. Task 8 Step 1 verifies this before any code.
3. **Stop-side reference price.** The desk has no market data of its own outside the timer/feed windows. The chart service therefore attaches its latest per-root quote (`quotes`) to every proxied body and overwrites anything the page sent. A Stop order, a Stop modify, or a bracket on a Market order needs a quote at most 30 s old.
4. **What the bot lock covers:**
   - **Which strategies.** A booking row with the matching symbol, for any strategy, whether enabled or not. Matching uses the engine's own substring rule (`"NQ" in "MNQZ6"`): `engine.on_fill` would read an MNQ fill as the NQ bot's exit.
   - **Refused actions.** The window (09:20–09:35 ET, weekdays) and the busy states (`placing|placed|live`) refuse order, modify, reverse, flatten and cancel-symbol.
   - **Cancel by id.** Cancelling a *manual* order by id stays allowed, so the user can always clear an order before the fire. It is refused only while the bot is `placing`, or when the order is one of the bot's.
   - **Bot orders.** They are never modified or cancelled from the chart (the desk's Kill stays the emergency path).
5. **Guards added for safety.**
   - A bracket's SL/TP must sit on the losing/winning side of the entry.
   - Reverse is refused when |net| > `max_order_qty`.
   - An unknown contract spec is refused.
   - The position limit is a worst case: position plus every working order on its side plus this order. An OCO pair counts twice.
   - A repeated `client_id` returns the first result (10 min).
   - Hard caps for the editable limits are 50 per order and 100 per position.
6. **Prestage details.**
   - Positions are read with `get_net_position`, the authoritative broker read, not the new cache. All accounts are read concurrently with a 2 s total timeout.
   - An unreadable or timed-out read fires as before, journaled `prestage_check_failed`.
   - If every booked account is skipped, the alert is refused with `all_accounts_skipped`.
   - **Known gap:** a manual *working order* resting across 09:20 is not cancelled or skipped. The approved rule is position-only; flag this to the user.
7. **Open P&L** is computed by the page. The desk sends the average price and the point value, and the page has the price.
8. **Desk key file.** If it is corrupt or unwritable, the desk still starts (the 9:30 bot must run) and `/api/trade/*` answers 503. The error is journaled as `desk_key_error`.
9. **Shutdown with a stream open.** An open SSE stream would block uvicorn's graceful shutdown forever. The desk's plist template gains `--timeout-graceful-shutdown 5`. It takes effect only at the user-approved deploy.
10. **Replay mode** chart service: no desk link, and the proxy answers 503. A replayed price must never reach an order.

## File Structure

| File | Responsibility |
|---|---|
| `homebase/broker/base.py` (modify) | listener hook, `pinned_ok`, default `trade_view`/`contract_name`/`flatten_symbol`/`cancel_symbol` |
| `homebase/broker/tradovate.py` (modify) | missing pin raises; listener; position/cash caches seeded per (re)connect; `trade_view`, `contract_id`, `flatten_symbol`, `cancel_symbol` |
| `homebase/config.py` (modify) | `ChartTradingCfg` (`enabled` false, 10, 20), hard caps, load/save |
| `homebase/trading.py` (new) | `ChartDesk`: views, pub/sub, settings, parsing, guards, actions, journaling |
| `homebase/desk_api.py` (new) | desk key file, SSE stream, `/api/trade/*` router, `/api/chart-trading` |
| `homebase/server.py` (modify, small) | build/mount `ChartDesk` + routers, key at startup, Kill disables, status field, readiness line |
| `homebase/engine.py` (modify, small) | per-day skip set; `handle_alert` filters skipped accounts |
| `homebase/timer.py` (modify, small) | prestage position check at `STAGE_T` |
| `homebase/static/index.html` (modify) | "Chart trading" card: switch + two limits |
| `deploy/com.ramosquant.homebase.plist.template` (modify) | `--timeout-graceful-shutdown 5` |
| `homebase/charts/desk.py` (new) | `SSEParser`, `Quotes`, `DeskLink`, `register()` proxy |
| `homebase/charts/server.py`, `__main__.py`, `__init__.py` (modify, small) | wire quotes + link + proxy |
| tests | `test_account_pin.py`, `test_adapter_caches.py`, `trading_util.py`, `test_trading_views.py`, `test_trading_guards.py`, `test_desk_api.py`, `test_prestage.py`, `test_desk_page.py`, `test_charts_desk.py`, `test_charts_desk_server.py`; one test appended to `test_server.py` |

---

### Task 1: A pinned account missing from the login raises

**Files:**
- Modify: `homebase/broker/base.py` (one attribute), `homebase/broker/tradovate.py:178-201` (`_resolve_account`)
- Test: `tests/test_account_pin.py` (new), `tests/test_server.py` (append one test)

**Interfaces:**
- Produces: `BrokerAdapter.pinned_ok: bool` (False by default). `TradovateAdapter._resolve_account` raises `RuntimeError("account <pin> not on this login (has: A, B)")` and leaves `_connected=False`, `_acct_num=None`, `_acct_name=""`, `pinned_ok=False`. It sets `pinned_ok=True` when a pin matched.

- [ ] **Step 1: Write the failing tests**

`tests/test_account_pin.py`:

```python
"""A pinned account that is not on the login is an ERROR, never a fallback
(2026-09-26: pins ...044/...045 silently connected to ...047)."""
from __future__ import annotations

import pytest

from tests.test_tradovate import mkadapter, tradovate_like

ACCTS = [{"id": 47, "name": "APEX-047", "active": True},
         {"id": 48, "name": "APEX-048", "active": True}]


def test_a_pinned_name_missing_from_the_login_raises_and_disconnects(tmp_path):
    ad = mkadapter(tmp_path, tradovate_like)          # connected, on account 66121477
    ad.account_selector = {"account_name": "APEX-044"}
    with pytest.raises(RuntimeError,
                       match=r"^account APEX-044 not on this login \(has: APEX-047, APEX-048\)$"):
        ad._resolve_account(ACCTS)
    assert (ad._acct_num, ad._acct_name, ad.pinned_ok) == (None, "", False)
    assert ad.connected is False                        # never "connected" on the wrong account


def test_a_pinned_id_missing_raises_too(tmp_path):
    ad = mkadapter(tmp_path, tradovate_like)
    ad.account_selector = {"tradovate_account_id": 44}
    with pytest.raises(RuntimeError, match=r"^account 44 not on this login"):
        ad._resolve_account(ACCTS)


def test_a_pin_matches_by_name_or_nickname_case_insensitively(tmp_path):
    ad = mkadapter(tmp_path, tradovate_like)
    ad.account_selector = {"account_name": "my eval"}
    ad._resolve_account([ACCTS[0], {"id": 48, "name": "APEX-048", "nickname": "My Eval"}])
    assert (ad._acct_num, ad._acct_name, ad.pinned_ok) == (48, "APEX-048", True)


def test_no_pin_keeps_the_first_active_fallback_but_is_not_pinned(tmp_path):
    ad = mkadapter(tmp_path, tradovate_like)
    ad.account_selector = {}
    ad._resolve_account([{"id": 47, "name": "APEX-047", "active": False}, ACCTS[1]])
    assert (ad._acct_num, ad._acct_name, ad.pinned_ok) == (48, "APEX-048", False)
```

Append to `tests/test_server.py`:

```python
def test_a_missing_pin_shows_its_reason_on_the_account(client):
    """The reason reaches acct_status, /api/status and the readiness strip.
    (Pins the existing surfacing; the raise itself is tested in
    tests/test_account_pin.py.)"""
    reason = "account APEX-044 not on this login (has: APEX-047)"

    async def refuse():
        raise RuntimeError(reason)

    client.adapter.connect = refuse
    client.adapter._connected = False
    r = client.post("/api/accounts/reconnect", json={"account": "main"}).json()
    assert r["results"]["main"] == {"ok": False, "error": reason}
    st = client.get("/api/status").json()
    assert st["accounts"]["main"]["connected"] is False
    assert st["accounts"]["main"]["error"] == reason
    assert {"level": "bad", "label": "MAIN", "detail": reason} in st["readiness"]["checks"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_account_pin.py tests/test_server.py`
Expected:
- the raise tests and the nickname test FAIL: `pinned_ok` is missing, and a missing pin falls back to 47/48;
- the server test PASSES already (the reason is already surfaced).

- [ ] **Step 3: Implement**

`homebase/broker/base.py`, in `BrokerAdapter.__init__` after `self._connected = False`:

```python
        # True only when the broker account was chosen by the config's pin
        # (chart trading refuses any account that is not on its own pin)
        self.pinned_ok = False
```

`homebase/broker/tradovate.py`: replace the whole `_resolve_account` method with:

```python
    def _resolve_account(self, accounts: list) -> None:
        self._all_accounts = list(accounts)
        if not accounts:
            raise RuntimeError(f"{self.account_id}: login exposes no accounts")
        sel = self.account_selector
        chosen = None
        want_id = sel.get("tradovate_account_id")
        if want_id:
            chosen = next((a for a in accounts if a.get("id") == want_id), None)
        want_name = sel.get("account_name") or sel.get("tradovate_account_name")
        if chosen is None and want_name:
            w = str(want_name).lower()
            chosen = next((a for a in accounts
                           if str(a.get("name", "")).lower() == w
                           or str(a.get("nickname", "")).lower() == w), None)
        if chosen is None and (want_id or want_name):
            # A pin that is not on this login is an ERROR, never a fallback:
            # on 2026-09-26 pins ...044/...045 silently connected to ...047.
            # Drop the connected flag too, so a reconnect can never keep
            # reporting the OLD account as up on the new socket.
            self._connected = False
            self._acct_num, self._acct_name, self.pinned_ok = None, "", False
            have = ", ".join(str(a.get("name") or a.get("nickname") or a.get("id"))
                             for a in accounts)
            raise RuntimeError(f"account {want_name or want_id} not on this login (has: {have})")
        pinned = chosen is not None
        if chosen is None:
            active = [a for a in accounts if a.get("active", True)]
            chosen = (active or accounts)[0]
            if len(accounts) > 1:
                _log(f"{self.account_id}: {len(accounts)} accounts under this login; "
                     f"using {chosen.get('name')} (#{chosen.get('id')}). "
                     f"Pin one with extra.account_name in config.")
        self._acct_num = chosen.get("id")
        self._acct_name = chosen.get("name") or chosen.get("nickname") or str(self._acct_num)
        self.pinned_ok = pinned
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `.venv/bin/python -m pytest -q tests/test_account_pin.py tests/test_server.py tests/test_tradovate.py`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add homebase/broker/base.py homebase/broker/tradovate.py tests/test_account_pin.py tests/test_server.py
git commit -m "fix(broker): a pinned account missing from the login raises instead of connecting another account" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Adapter listener, position/cash caches, symbol-scoped flatten and cancel

**Files:**
- Modify: `homebase/broker/base.py`, `homebase/broker/tradovate.py`
- Test: `tests/test_adapter_caches.py` (new)

**Interfaces:**
- Consumes: `pinned_ok` (Task 1).
- Produces (on `BrokerAdapter`, defaults no-op/unsupported):
  - `add_listener(cb: Callable[[str, dict], None]) -> None` and `_notify(entity_type, entity)`. Types: `order`, `orderVersion`, `position`, `fill`, `cashBalance`, and `sync` (the caches were reseeded, so re-read everything).
  - `trade_view() -> Optional[dict]`.
  - `contract_name(contract_id) -> Optional[str]`.
  - `async flatten_symbol(symbol) -> OrderResult` and `async cancel_symbol(symbol) -> OrderResult`.
- Produces (on `TradovateAdapter`):
  - `caches_seeded: bool`;
  - `async contract_id(symbol) -> int`;
  - `trade_view()` returns `{"broker_account", "pinned", "seeded", "balance", "realized_pnl", "positions": [{"contract_id", "symbol", "net", "avg_price"}], "orders": [{"order_id": str, "symbol", "side", "type", "qty", "price", "stop_price", "status"}]}`. Only this account and only non-zero positions; `orders` holds the working ones.
- Listeners hear only THIS account's entities, after the adapter's own caches took them. The fill path (dedup, enqueue) is behaviourally identical.

- [ ] **Step 1: Write the failing tests**

`tests/test_adapter_caches.py`:

```python
"""Chart trading's adapter surface: the entity listener, the position/cash
caches, symbol-scoped flatten/cancel. No network: the fake socket from
tests/test_tradovate.py answers every frame."""
from __future__ import annotations

import asyncio
import json

from homebase import symbols
from homebase.broker.tradovate import TradovateAdapter
from tests.test_tradovate import (BUY_STOP, collect_fills, fill_push, mkadapter, run,
                                  tradovate_like)

NQC, ESC = symbols.resolve_contract("NQ"), symbols.resolve_contract("ES")
CID = {NQC: 3267315, ESC: 3267400}
ME, OTHER = 66121477, 99


def broker(positions=None, cash=None, place=None):
    """An answer function + the list of (endpoint, query, body) it saw.
    positions=None -> position/list answers 404 (unreadable)."""
    sent = []

    def answer(endpoint, query, body):
        sent.append((endpoint, query, json.loads(body) if body else None))
        if endpoint == "contract/find":
            name = query[len("name="):]
            return {"id": CID[name], "name": name} if name in CID else None
        if endpoint == "contract/item":
            cid = int(query[len("id="):])
            name = {v: k for k, v in CID.items()}.get(cid)
            return {"id": cid, "name": name} if name else None
        if endpoint == "position/list":
            return positions
        if endpoint == "cashBalance/list":
            return cash if cash is not None else []
        if endpoint == "order/placeorder":
            return place if place is not None else {"orderId": 900}
        if endpoint == "order/cancelorder":
            return {}
        return None

    return answer, sent


def push(ad, et, ent):
    ad._on_ws_event({"e": "props", "d": {"entityType": et, "entity": ent}})


def working(oid, cid, acct=ME, status="Working", action="Sell"):
    return {"id": oid, "accountId": acct, "contractId": cid, "ordStatus": status, "action": action}


# --- the listener ------------------------------------------------------------
def test_listener_hears_this_accounts_entities_after_the_cache_took_them(tmp_path):
    ad = mkadapter(tmp_path, tradovate_like)
    ad._contracts[3267315] = "NQZ6"
    got = []
    ad.add_listener(lambda et, ent: got.append((et, dict(ent))))
    push(ad, "order", working(5, 3267315, action="Buy"))
    push(ad, "order", working(6, 3267315, acct=OTHER))
    push(ad, "orderVersion", {"id": 50, "orderId": 5, "orderType": "Limit", "price": 100.0, "orderQty": 2})
    push(ad, "orderVersion", {"id": 60, "orderId": 6, "orderType": "Limit", "price": 1.0, "orderQty": 1})
    push(ad, "position", {"id": 7, "accountId": ME, "contractId": 3267315, "netPos": 2, "netPrice": 100.0})
    push(ad, "position", {"id": 8, "accountId": OTHER, "contractId": 3267315, "netPos": 9})
    push(ad, "cashBalance", {"id": 1, "accountId": ME, "amount": 5.0, "realizedPnL": 1.5})
    push(ad, "cashBalance", {"id": 2, "accountId": OTHER, "amount": 7.0})
    push(ad, "contract", {"id": 3267315, "name": "NQZ6"})          # not a listened type
    assert [et for et, _ in got] == ["order", "orderVersion", "position", "cashBalance"]
    assert got[0][1] == ad._orders[5]                                 # the cache took it first
    v = ad.trade_view()
    assert v["positions"] == [{"contract_id": 3267315, "symbol": "NQZ6", "net": 2, "avg_price": 100.0}]
    assert v["orders"] == [{"order_id": "5", "symbol": "NQZ6", "side": "Buy", "type": "Limit",
                            "qty": 2, "price": 100.0, "stop_price": None, "status": "Working"}]
    assert (v["balance"], v["realized_pnl"]) == (5.0, 1.5)


def test_the_fill_path_is_unchanged_by_listeners(tmp_path):
    pushes = [fill_push(663695020149, "Buy", 3, 30231.5, 7001),
              fill_push(663695020149, "Buy", 3, 30231.5, 7001)]         # a duplicate push
    plain = collect_fills(mkadapter(tmp_path / "a", tradovate_like), list(pushes), place=BUY_STOP)
    ad = mkadapter(tmp_path / "b", tradovate_like)
    heard = []
    ad.add_listener(lambda et, ent: heard.append((et, ent.get("id"))))
    ad.add_listener(lambda et, ent: 1 / 0)                           # a broken listener changes nothing
    watched = collect_fills(ad, list(pushes), place=BUY_STOP)

    def key(fs):
        return [(f.account_id, f.symbol, f.side, f.qty, f.price, f.raw.get("orderId")) for f in fs]

    assert key(watched) == key(plain) and len(plain) == 1
    assert heard == [("fill", 7001)]           # our own order's fill, announced once


# --- the caches ----------------------------------------------------------------
def test_seed_reads_this_accounts_positions_and_cash_and_resolves_names(tmp_path):
    answer, _ = broker(
        positions=[{"accountId": ME, "contractId": CID[NQC], "netPos": 2, "netPrice": 30100.5},
                   {"accountId": ME, "contractId": CID[ESC], "netPos": 0},
                   {"accountId": OTHER, "contractId": CID[ESC], "netPos": 1}],
        cash=[{"accountId": OTHER, "amount": 1.0},
              {"accountId": ME, "amount": 50123.5, "realizedPnL": -80.0}])
    ad = mkadapter(tmp_path, answer)
    got = []
    ad.add_listener(lambda et, ent: got.append(et))
    run(ad._seed_caches())
    v = ad.trade_view()
    assert v["seeded"] is True and (v["balance"], v["realized_pnl"]) == (50123.5, -80.0)
    assert v["positions"] == [{"contract_id": CID[NQC], "symbol": NQC, "net": 2, "avg_price": 30100.5}]
    assert got[-1] == "sync"


def test_a_failed_seed_leaves_the_caches_unseeded_and_is_audited(tmp_path):
    answer, _ = broker(positions=None)                     # position/list -> 404
    ad = mkadapter(tmp_path, answer)
    events = []
    ad.audit = events.append
    run(ad._seed_caches())
    assert ad.caches_seeded is False and ad.trade_view()["seeded"] is False
    assert events and events[-1]["event"] == "cache_seed_error"


class SyncWS:
    """Stands in for TradovateWS during reconnect(): no network."""

    def __init__(self, token=None, environment="demo"):
        self.event_handlers, self.connected = [], True

    async def connect(self): ...
    async def authorize(self): ...
    async def close(self): ...

    async def user_sync(self):
        return {"accounts": [{"id": ME, "name": "APEX"}], "contracts": [{"id": CID[NQC], "name": NQC}]}

    async def position_list(self):
        return [{"accountId": ME, "contractId": CID[NQC], "netPos": -1, "netPrice": 5.0}]

    async def cash_balance_list(self):
        return [{"accountId": ME, "amount": 7.0}]


def test_reconnect_reseeds_the_caches_in_the_background(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.broker.tradovate.TradovateWS", SyncWS)
    ad = TradovateAdapter("acct", env="demo", keyring_key="k", state_dir=tmp_path,
                          account_selector={"account_name": "APEX"})
    monkeypatch.setattr(ad._auth, "ensure_valid", lambda *a: None)

    async def go():
        await ad.reconnect()
        for _ in range(100):
            if ad.caches_seeded:
                break
            await asyncio.sleep(0.01)
        v = ad.trade_view()
        await ad.close()
        return v

    v = run(go())
    assert v["seeded"] is True and v["pinned"] is True and v["balance"] == 7.0
    assert v["positions"][0]["net"] == -1 and ad.caches_seeded is False   # close() clears it


# --- symbol-scoped flatten / cancel ----------------------------------------------
def orders_nq_es(ad):
    ad._contracts.update({CID[NQC]: NQC, CID[ESC]: ESC})
    ad._orders.update({1: working(1, CID[NQC]), 2: working(2, CID[ESC], action="Buy"),
                       3: working(3, CID[NQC], acct=OTHER, action="Buy"),
                       4: working(4, CID[NQC], status="Filled", action="Buy"),
                       5: {"id": 5, "accountId": ME, "ordStatus": "Working"}})   # contract unknown


def test_flatten_symbol_markets_out_then_cancels_only_that_contract(tmp_path):
    answer, sent = broker(positions=[{"accountId": ME, "contractId": CID[NQC], "netPos": 3},
                                     {"accountId": OTHER, "contractId": CID[NQC], "netPos": 5}])
    ad = mkadapter(tmp_path, answer)
    orders_nq_es(ad)
    r = run(ad.flatten_symbol("NQ"))
    assert r.ok is True and r.raw["net_before"] == 3
    eps = [e for e, _, _ in sent]
    placed = [b for e, _, b in sent if e == "order/placeorder"]
    assert len(placed) == 1
    assert (placed[0]["action"], placed[0]["orderQty"], placed[0]["symbol"],
            placed[0]["orderType"], placed[0]["accountId"]) == ("Sell", 3, NQC, "Market", ME)
    assert [b["orderId"] for e, _, b in sent if e == "order/cancelorder"] == [1]
    assert eps.index("order/placeorder") < eps.index("order/cancelorder")


def test_flatten_symbol_refused_market_cancels_nothing(tmp_path):
    answer, sent = broker(positions=[{"accountId": ME, "contractId": CID[NQC], "netPos": -2}],
                          place={"failureReason": "Risk", "failureText": "Insufficient margin"})
    ad = mkadapter(tmp_path, answer)
    orders_nq_es(ad)
    r = run(ad.flatten_symbol("NQ"))
    assert r.ok is False and r.error == "flatten order refused: Insufficient margin — orders left working"
    assert not any(e == "order/cancelorder" for e, _, _ in sent)


def test_flatten_symbol_unreadable_position_does_nothing(tmp_path):
    answer, sent = broker(positions=None)
    ad = mkadapter(tmp_path, answer)
    orders_nq_es(ad)
    r = run(ad.flatten_symbol("NQ"))
    assert r.ok is False and r.error.startswith("position unreadable")
    assert not any(e in ("order/placeorder", "order/cancelorder") for e, _, _ in sent)


def test_cancel_symbol_touches_only_this_accounts_working_orders_in_that_contract(tmp_path):
    answer, sent = broker()
    ad = mkadapter(tmp_path, answer)
    orders_nq_es(ad)
    r = run(ad.cancel_symbol("ES"))
    assert r.ok is True and r.raw == {"cancelled": 1, "ids": ["2"], "unknown_contract": 1}
    assert [b["orderId"] for e, _, b in sent if e == "order/cancelorder"] == [2]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `.venv/bin/python -m pytest -q tests/test_adapter_caches.py`
Expected: FAIL. `add_listener`, `trade_view`, `_seed_caches`, `flatten_symbol` and `cancel_symbol` don't exist yet.

- [ ] **Step 3: Implement the base-class surface**

`homebase/broker/base.py`:
- add `import sys` to the imports;
- add after `FillCallback = …`: `EntityListener = Callable[[str, dict], None]`;
- in `__init__`, after `self.pinned_ok = False`, add `self._listeners: list[EntityListener] = []`;
- add these methods to `BrokerAdapter`, before `# --- reads ---`:

```python
    # --- chart trading (spec 2026-09-26) -------------------------------------
    def add_listener(self, cb: EntityListener) -> None:
        """Call cb(entity_type, entity) for THIS account's entity pushes, after
        the adapter's own caches took them. Types: order, orderVersion,
        position, fill, cashBalance, and "sync" (the caches were reseeded:
        re-read everything). Adding the same callable twice is a no-op."""
        if cb not in self._listeners:
            self._listeners.append(cb)

    def _notify(self, entity_type: str, entity: dict) -> None:
        for cb in list(self._listeners):
            try:
                cb(entity_type, entity)
            except Exception as e:  # noqa: BLE001 — a listener must never break the socket reader
                print(f"[broker] {self.account_id}: listener error: {type(e).__name__}: {e}",
                      file=sys.stderr, flush=True)

    def trade_view(self) -> Optional[dict]:
        """Cached positions / working orders / cash for chart trading, with no
        broker call. None = this adapter cannot provide one."""
        return None

    def contract_name(self, contract_id) -> Optional[str]:
        return None

    async def flatten_symbol(self, symbol: str) -> OrderResult:
        return OrderResult(ok=False, error="flatten_symbol not supported")

    async def cancel_symbol(self, symbol: str) -> OrderResult:
        return OrderResult(ok=False, error="cancel_symbol not supported")
```

- [ ] **Step 4: Implement the Tradovate side**

`homebase/broker/tradovate.py`:

(a) In `__init__`, after `self._keepalive: Optional[asyncio.Task] = None`, add:

```python
        self._positions: dict[int, dict] = {}     # contractId -> position, THIS account only
        self._cash: dict = {}                     # cashBalance, THIS account only
        self._contract_lookups: set = set()       # contract ids being resolved in the background
        self._seed_task: Optional[asyncio.Task] = None
        self.caches_seeded = False                # position/cash read after the last (re)connect
```

(b) In `connect()`, make `self.caches_seeded = False` the first statement. Then add the line `self._schedule_seed()` right after `self._connected = True`. In `reconnect()`, make `self.caches_seeded = False` the first statement too, and add `self._schedule_seed()` right after `self._connected = True`. In `close()`, add `self.caches_seeded = False` after `self._connected = False`, and change the task tuple to `(self._keepalive, self._consumer, self._seed_task)`.

(c) Replace `_on_ws_event` with the following. The contract and fill branches keep today's logic; the fill branch changes only by the listener call after it:

```python
    def _on_ws_event(self, msg: dict) -> None:
        """Sync handler invoked from the WS reader for every unsolicited frame.
        The adapter's own caches take each push first; listeners (chart
        trading) hear about it after, and only for THIS account."""
        if msg.get("e") != "props":
            return
        d = msg.get("d") or {}
        et = d.get("entityType")
        ent = d.get("entity")
        if not et or not isinstance(ent, dict):
            return
        if et == "contract":
            if "id" in ent and "name" in ent:
                self._contracts[ent["id"]] = ent["name"]
        elif et == "order":
            if "id" in ent:
                self._orders[ent["id"]] = {**self._orders.get(ent["id"], {}), **ent}
                self._notify_mine(et, self._orders[ent["id"]])
        elif et == "orderVersion":
            oid = ent.get("orderId")
            if oid is not None:
                self._order_versions[oid] = {**self._order_versions.get(oid, {}), **ent}
                self._notify_mine(et, self._order_versions[oid])
        elif et == "fill":
            fid = ent.get("id")
            if fid is None or not self._mark_seen(fid):
                return
            if self._on_fill is not None:     # this account is being observed as master
                self._enqueue_fill(ent)
            self._notify_mine(et, ent)
        elif et == "position":
            if self._ingest_position(ent):
                self._notify_mine(et, self._positions[ent["contractId"]])
        elif et == "cashBalance":
            if self._ingest_cash(ent):
                self._notify_mine(et, self._cash)
```

(d) Add after `_on_ws_event`:

```python
    def _owner(self, et: str, ent: dict):
        """The account an entity belongs to. orderVersion and fill pushes
        carry no accountId: their order's, or ours when WE placed it."""
        acct = ent.get("accountId")
        if acct is None and et in ("orderVersion", "fill"):
            oid = ent.get("orderId")
            acct = (self._orders.get(oid) or {}).get("accountId")
            if acct is None and oid in self._order_symbols:
                acct = self._acct_num
        return acct

    def _notify_mine(self, et: str, ent: dict) -> None:
        if self._listeners and self._acct_num is not None \
                and self._owner(et, ent) == self._acct_num:
            self._notify(et, dict(ent))

    def _ingest_position(self, ent: dict) -> bool:
        cid = ent.get("contractId")
        if self._acct_num is None or ent.get("accountId") != self._acct_num or cid is None:
            return False
        self._positions[cid] = {**self._positions.get(cid, {}), **ent}
        if cid not in self._contracts:
            self._want_contract(cid)
        return True

    def _ingest_cash(self, ent: dict) -> bool:
        if self._acct_num is None or ent.get("accountId") != self._acct_num:
            return False
        self._cash = {**self._cash, **ent}
        return True

    def _want_contract(self, cid) -> None:
        """Resolve an unseen contract name in the background (a position push
        may name only its contractId). No running loop -> leave it unresolved."""
        if cid in self._contract_lookups or self._ws is None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        self._contract_lookups.add(cid)
        loop.create_task(self._lookup_contract(cid))

    async def _lookup_contract(self, cid) -> None:
        try:
            c = await self._ws.contract_item(cid)
            name = (c or {}).get("name")
            if name:
                self._contracts[cid] = name
                if cid in self._positions:
                    self._notify_mine("position", self._positions[cid])
        except Exception as e:  # noqa: BLE001 — shown unresolved; chart trading refuses meanwhile
            _log(f"{self.account_id}: contract/item {cid} failed: {e}")
        finally:
            self._contract_lookups.discard(cid)

    def _schedule_seed(self) -> None:
        """Positions + cash read in the BACKGROUND after a (re)connect: it
        never delays the connect the 9:30 bot is waiting on."""
        if self._seed_task is not None and not self._seed_task.done():
            self._seed_task.cancel()
        self._seed_task = asyncio.create_task(self._seed_caches())

    async def _seed_caches(self) -> None:
        """Positions and cash balance for THIS account, once per (re)connect;
        pushes keep them current after. A failure leaves caches_seeded False
        (chart trading then refuses this account) and is audited."""
        try:
            positions = await self._ws.position_list()
            cash = await self._ws.cash_balance_list()
        except Exception as e:  # noqa: BLE001
            _log(f"{self.account_id}: cache seed failed: {e}")
            self.audit({"event": "cache_seed_error", "account": self.account_id,
                        "error": str(e)[:200]})
            return
        me = self._acct_num
        self._positions = {p["contractId"]: p for p in positions or []
                           if isinstance(p, dict) and p.get("accountId") == me
                           and p.get("contractId") is not None}
        self._cash = next((b for b in cash or []
                           if isinstance(b, dict) and b.get("accountId") == me), {})
        for cid in [c for c in self._positions if c not in self._contracts]:
            await self._lookup_contract(cid)
        self.caches_seeded = True
        self._notify("sync", {})
```

(e) Add the chart-trading reads and actions after `get_protective_orders`:

```python
    def contract_name(self, contract_id) -> Optional[str]:
        return self._contracts.get(contract_id)

    async def contract_id(self, symbol: str) -> int:
        """The contract id for a root or contract, from the cache or one
        contract/find (cached after)."""
        name = symbols.resolve_contract(symbol)
        for cid, n in list(self._contracts.items()):
            if n == name:
                return cid
        c = await self._ws.contract_find(name)
        cid = (c or {}).get("id")
        if cid is None:
            raise RuntimeError(f"no contract found for {name}")
        self._contracts[cid] = name
        return cid

    def trade_view(self) -> dict:
        """Positions, working orders and cash for THIS account, from the pushed
        caches only (no broker call). `seeded` is False until the (re)connect's
        position/cash read landed."""
        me = self._acct_num
        positions = [{"contract_id": cid, "symbol": self._contracts.get(cid),
                      "net": int(p.get("netPos") or 0), "avg_price": p.get("netPrice")}
                     for cid, p in self._positions.items() if int(p.get("netPos") or 0)]
        orders = []
        for oid, o in self._orders.items():
            if me is None or o.get("accountId") != me \
                    or o.get("ordStatus") not in self._WORKING_STATUSES:
                continue
            ov = self._order_versions.get(oid, {})
            cid = o.get("contractId") or ov.get("contractId")
            orders.append({
                "order_id": str(oid),
                "symbol": self._contracts.get(cid) if cid is not None else None,
                "side": o.get("action") or ov.get("action"),
                "type": ov.get("orderType") or o.get("orderType"),
                "qty": ov.get("orderQty") or o.get("orderQty"),
                "price": ov.get("price") if ov.get("price") is not None else o.get("price"),
                "stop_price": (ov.get("stopPrice") if ov.get("stopPrice") is not None
                               else o.get("stopPrice")),
                "status": o.get("ordStatus")})
        return {"broker_account": self._acct_name or None, "pinned": self.pinned_ok,
                "seeded": self.caches_seeded, "balance": self._cash.get("amount"),
                "realized_pnl": self._cash.get("realizedPnL"),
                "positions": sorted(positions, key=lambda p: str(p["symbol"])),
                "orders": sorted(orders, key=lambda o: o["order_id"])}

    async def cancel_symbol(self, symbol: str) -> OrderResult:
        """Cancel THIS account's working orders in ONE contract (from the
        pushed order cache). An order whose contract is unknown is left alone
        and counted in raw["unknown_contract"]."""
        if self._ws is None or self._acct_num is None:
            return OrderResult(ok=False, error="adapter not connected")
        try:
            cid = await self.contract_id(symbol)
        except Exception as e:  # noqa: BLE001
            return OrderResult(ok=False, error=f"no contract for {symbol}: {e}")
        ids, unknown = [], 0
        for oid, o in list(self._orders.items()):
            if o.get("accountId") != self._acct_num \
                    or o.get("ordStatus") not in self._WORKING_STATUSES:
                continue
            o_cid = o.get("contractId") or self._order_versions.get(oid, {}).get("contractId")
            if o_cid is None:
                unknown += 1
            elif o_cid == cid:
                ids.append(oid)
        res = await asyncio.gather(*(self.cancel_order_by_id(str(i)) for i in ids),
                                   return_exceptions=True)
        errors = [f"{i}: {r if isinstance(r, Exception) else r.error}"
                  for i, r in zip(ids, res) if isinstance(r, Exception) or not r.ok]
        return OrderResult(ok=not errors, error="; ".join(errors) or None,
                           raw={"cancelled": len(ids) - len(errors),
                                "ids": [str(i) for i in ids], "unknown_contract": unknown})

    async def flatten_symbol(self, symbol: str) -> OrderResult:
        """Close THIS account's position in ONE contract, then cancel only that
        contract's working orders. Position read from the broker (unreadable is
        not flat -> nothing done); the market order must be accepted before
        anything is cancelled, so a refused order leaves the stop working."""
        if self._ws is None or self._acct_num is None:
            return OrderResult(ok=False, error="adapter not connected")
        try:
            net = await self.get_net_position(symbol)
        except Exception as e:  # noqa: BLE001
            return OrderResult(ok=False, error=f"position unreadable ({e}) — nothing done")
        raw: dict = {"net_before": net}
        if net:
            r = await self.place_order(OrderRequest(
                symbol=symbol, side="Sell" if net > 0 else "Buy", qty=abs(net),
                order_type="Market", text="homebase:chart-flat"))
            raw["market"] = {"ok": r.ok, "order_id": r.order_id, "error": r.error}
            if not r.ok:
                return OrderResult(ok=False, raw=raw,
                                   error=f"flatten order refused: {r.error} — orders left working")
        c = await self.cancel_symbol(symbol)
        raw["cancel"] = {"ok": c.ok, "error": c.error, **(c.raw or {})}
        return OrderResult(ok=c.ok, error=c.error, raw=raw)
```

- [ ] **Step 5: Run the new and the adapter tests**

Run: `.venv/bin/python -m pytest -q tests/test_adapter_caches.py tests/test_tradovate.py tests/test_account_pin.py tests/test_engine.py`
Expected: all PASS.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m pytest -q`
Expected: all PASS (281 + this plan's new tests so far).

- [ ] **Step 7: Commit**

```bash
git add homebase/broker/base.py homebase/broker/tradovate.py tests/test_adapter_caches.py
git commit -m "feat(broker): entity listener, position and cash caches, symbol-scoped flatten and cancel for chart trading; the fill path is unchanged" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: `chart_trading` config + `ChartDesk` views, events and settings

**Files:**
- Modify: `homebase/config.py`
- Create: `homebase/trading.py`, `tests/trading_util.py`
- Test: `tests/test_trading_views.py`

**Interfaces:**
- Consumes: `trade_view()`, `contract_name()`, `add_listener()`, `_notify()`, `pinned_ok` (Task 2); `Engine.day_states`, `day_states_for_account`, `day_status`, `journal`, `_state` (existing).
- Produces:
  - **config:** `config.ChartTradingCfg(enabled=False, max_order_qty=10, max_position_qty=20)`, `AppCfg.chart_trading`, `config.HARD_MAX_ORDER_QTY=50`, `config.HARD_MAX_POSITION_QTY=100`, `config.chart_trading_from(d)`.
  - **construction:** `ChartDesk(cfg, engine, adapters, acct_status, *, timer_status=None, save=None, mono=time.monotonic)`.
  - **views:** `.snapshot() -> {"enabled", "limits": {"max_order_qty", "max_position_qty"}, "accounts": [account_view], "bot": bot_view}` and `.account_view(aid)`. Account view keys: `id, label, pinned, broker_account, env, connected, error, tradable, balance, realized_pnl, positions[+root, point_value], orders[+owner], fills, strategies`. Also `.bot_view() -> {"date", "strategies": {name: {symbol, kind, enabled, shadow, offset_pts, sl_pts, tp_pts, book, timer, day_status, accounts: {aid: state_view}}}}`.
  - **pub/sub:** `.subscribe() -> asyncio.Queue` (items `(event, data)`; `(None, None)` = dropped), `.unsubscribe(q)`, `.publish(event, data)`, `.publish_state()`, `.flush()`, `.attach(aid, adapter)`, `async .run()`.
  - **settings:** `.set_settings(body) -> dict` (ValueError on bad input), `.disable(cause)`.
  - **pure:** module function `state_view(day_state, strategy_cfg) -> dict`; constants `SUB_QUEUE_MAX`, `WATCH_S`.

- [ ] **Step 1: Write the shared test helpers** — `tests/trading_util.py`:

```python
"""Shared fakes for the chart-trading tests: a desk with two accounts, no broker, no network."""
from __future__ import annotations

import asyncio
import json

from homebase import symbols
from homebase.broker.base import OrderResult
from homebase.config import AccountCfg, AppCfg, ChartTradingCfg, StrategyCfg
from homebase.engine import Engine
from homebase.trading import ChartDesk
from tests.test_engine import Clock, FakeAdapter

NQC = symbols.resolve_contract("NQ")
ESC = symbols.resolve_contract("ES")
MNQC = symbols.resolve_contract("MNQ")


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


class Mono:
    """Injected monotonic clock for the rate limiter."""

    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


class TradeAdapter(FakeAdapter):
    """FakeAdapter + the chart-trading surface: a live view, symbol-scoped
    flatten/cancel, a pinned account."""

    def __init__(self, aid):
        super().__init__(aid)
        self.pinned_ok = True
        self.view = {"broker_account": aid.upper(), "pinned": True, "seeded": True,
                     "balance": 50000.0, "realized_pnl": 0.0, "positions": [], "orders": []}
        self.flattened: list[str] = []
        self.sym_cancelled: list[str] = []
        self.fail_flatten = False

    def trade_view(self):
        return {**self.view, "positions": [dict(p) for p in self.view["positions"]],
                "orders": [dict(o) for o in self.view["orders"]]}

    def contract_name(self, cid):
        return {1: NQC, 2: ESC}.get(cid)

    async def flatten_symbol(self, symbol):
        self.flattened.append(symbol)
        if self.fail_flatten:
            return OrderResult(ok=False, error="flatten rejected by test")
        return OrderResult(ok=True, raw={"net_before": self.net})

    async def cancel_symbol(self, symbol):
        self.sym_cancelled.append(symbol)
        return OrderResult(ok=True, raw={"cancelled": 1})


def mkdesk(tmp_path, *, enabled=True, et=(11, 0), book=None):
    """Desk at `et` ET on Monday 2026-09-14 (EDT). a1 is booked to nq930 (NQ)."""
    clock = Clock()
    clock.set_et(*et)
    cfg = AppCfg(
        armed=True, webhook_secret="s",
        accounts={a: AccountCfg(keyring_key="k", account_name=a.upper(), label=a.upper())
                  for a in ("a1", "a2")},
        book=book if book is not None else {"nq930": [{"account": "a1", "qty": 3}]},
        strategies={"nq930": StrategyCfg(symbol="NQ", qty=3, offset_pts=10.0, sl_pts=5.0,
                                         tp_pts=15.0, enabled=True, self_fire=True)},
        chart_trading=ChartTradingCfg(enabled=enabled))
    adapters = {a: TradeAdapter(a) for a in cfg.accounts}
    engine = Engine(cfg, adapters, now_fn=clock, root=tmp_path)
    saved: list = []
    mono = Mono()
    desk = ChartDesk(cfg, engine, adapters, {}, save=saved.append, mono=mono,
                     timer_status=lambda: {"date": "2026-09-14", "strategies": {
                         "nq930": {"stage": "gated", "gate": True, "adx": 23.4, "anchor": None}}})
    return desk, engine, adapters, clock, mono, saved


def quote(clock, root="NQ", last=100.0, age_s=0.0):
    """The `quotes` block the chart service attaches to a proxied body."""
    ms = int((clock().timestamp() - age_s) * 1000)
    return {root: {"bid": last - 0.25, "ask": last, "last": last, "ts_ms": ms}}


def journal(tmp_path):
    p = tmp_path / "journal.jsonl"
    return [json.loads(line) for line in p.read_text().splitlines()] if p.exists() else []


def drain(q) -> list:
    return [q.get_nowait() for _ in range(q.qsize())]
```

- [ ] **Step 2: Write the failing tests** — `tests/test_trading_views.py`:

```python
"""ChartDesk views, events and settings. No broker, no network."""
from __future__ import annotations

import asyncio
import json
import re
from dataclasses import asdict

import pytest

import homebase.config as config_mod
from homebase.config import ChartTradingCfg
from homebase.trading import state_view
from tests.trading_util import NQC, drain, journal, mkdesk, run


def test_chart_trading_config_defaults_roundtrip_and_garbage(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    cfg = config_mod.load()
    assert asdict(cfg.chart_trading) == {"enabled": False, "max_order_qty": 10, "max_position_qty": 20}
    cfg.chart_trading = ChartTradingCfg(enabled=True, max_order_qty=3, max_position_qty=6)
    config_mod.save(cfg)
    assert asdict(config_mod.load().chart_trading) == {"enabled": True, "max_order_qty": 3,
                                                       "max_position_qty": 6}
    for junk in ({"enabled": "true"}, {"enabled": True, "max_order_qty": 0},
                 {"enabled": True, "max_position_qty": "x"}, "on"):
        (tmp_path / "config.json").write_text(json.dumps({"chart_trading": junk}))
        assert config_mod.load().chart_trading.enabled is False


def test_snapshot_shape(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a1"].view["positions"] = [{"contract_id": 1, "symbol": NQC, "net": 2, "avg_price": 100.5}]
    st = eng._state("nq930", "a1")
    st.status, st.upper_id = "done", "60"
    ads["a1"].view["orders"] = [{"order_id": "60", "symbol": NQC, "side": "Buy", "type": "Stop",
                                 "qty": 3, "price": None, "stop_price": 110.0, "status": "Working"}]
    s = desk.snapshot()
    assert s["enabled"] is True and s["limits"] == {"max_order_qty": 10, "max_position_qty": 20}
    a1, a2 = s["accounts"]
    assert (a1["id"], a1["label"], a1["pinned"], a1["env"]) == ("a1", "A1", "A1", "demo")
    assert a1["connected"] is True and a1["tradable"] is True and a1["error"] is None
    assert a1["positions"] == [{"contract_id": 1, "symbol": NQC, "net": 2, "avg_price": 100.5,
                                "root": "NQ", "point_value": 20.0}]
    assert a1["orders"][0]["owner"] == "nq930"                 # the bot's own order is marked
    assert a1["strategies"] == ["nq930"] and a2["strategies"] == []
    bot = s["bot"]["strategies"]["nq930"]
    assert bot["book"] == {"a1": 3} and bot["timer"]["adx"] == 23.4
    assert bot["day_status"] == "done" and bot["accounts"]["a1"]["status"] == "done"
    json.dumps(s)                                               # JSON-clean


def test_an_unpinned_or_unseeded_account_is_not_tradable(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a1"].pinned_ok = False
    ads["a2"].view["seeded"] = False
    assert [a["tradable"] for a in desk.snapshot()["accounts"]] == [False, False]


def test_bot_levels_follow_the_engine(tmp_path):
    desk, eng, *_ = mkdesk(tmp_path)
    s = eng.cfg.strategies["nq930"]
    st = eng._state("nq930", "a1")
    st.status, st.upper_px, st.lower_px, st.qty = "placed", 110.0, 90.0, 3
    v = state_view(st, s)
    assert (v["upper"], v["lower"], v["sl"], v["tp"]) == (110.0, 90.0, None, None)
    st.status, st.entry_side, st.entry_anchor, st.entry_fill = "live", "Buy", 110.0, 110.5
    assert (state_view(st, s)["sl"], state_view(st, s)["tp"]) == (105.0, 125.0)   # from the anchor
    st.brackets_moved = True
    assert (state_view(st, s)["sl"], state_view(st, s)["tp"]) == (105.5, 125.5)   # moved to the fill
    st.entry_side, st.entry_anchor, st.entry_fill = "Sell", 90.0, 89.75
    assert (state_view(st, s)["sl"], state_view(st, s)["tp"]) == (94.75, 74.75)
    st.sl_px, st.tp_px = 80.0, 70.0                                              # a bars rule
    assert (state_view(st, s)["sl"], state_view(st, s)["tp"]) == (80.0, 70.0)


def test_listener_publishes_the_fill_then_the_changed_account(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    desk.attach("a1", ads["a1"])
    desk.attach("a1", ads["a1"])                                 # idempotent
    assert len(ads["a1"]._listeners) == 1

    async def go():
        q = desk.subscribe()
        desk.flush()                                             # first flush: the full state
        ads["a1"].view["positions"] = [{"contract_id": 1, "symbol": NQC, "net": 1, "avg_price": 100.0}]
        ads["a1"]._notify("fill", {"id": 9, "orderId": 5, "contractId": 1, "action": "Buy",
                                   "qty": 1, "price": 100.0, "timestamp": "t"})
        await asyncio.sleep(0)                                   # the scheduled flush runs
        await asyncio.sleep(0)
        return drain(q)

    evs = run(go())
    assert [e for e, _ in evs] == ["state", "fill", "account"]
    assert evs[1][1] == {"account": "a1", "fill": {
        "id": 9, "order_id": "5", "symbol": NQC, "side": "Buy", "qty": 1, "price": 100.0,
        "time": "t", "owner": None}}
    assert evs[2][1]["positions"][0]["net"] == 1 and evs[2][1]["fills"][-1]["id"] == 9


def test_flush_publishes_only_what_changed(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)

    async def go():
        q = desk.subscribe()
        desk.flush()
        desk.flush()                                             # nothing changed
        eng._state("nq930", "a1").status = "placed"
        desk.flush()                                             # the bot changed
        ads["a2"]._connected = False
        desk.flush()                                             # one account changed
        return [e for e, _ in drain(q)]

    assert run(go()) == ["state", "bot", "account"]


def test_a_reader_that_falls_behind_is_dropped_with_an_end_marker(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.trading.SUB_QUEUE_MAX", 3)
    desk, *_ = mkdesk(tmp_path)

    async def go():
        q = desk.subscribe()
        for i in range(5):
            desk.publish("fill", {"i": i})
        return drain(q), q in desk._subs

    items, still = run(go())
    assert items == [(None, None)] and still is False


def test_settings_validate_save_journal_and_publish(tmp_path):
    desk, eng, ads, clock, mono, saved = mkdesk(tmp_path, enabled=False)

    async def go():
        q = desk.subscribe()
        out = desk.set_settings({"enabled": True, "max_order_qty": 4})
        return out, [e for e, _ in drain(q)]

    out, evs = run(go())
    assert out == {"enabled": True, "max_order_qty": 4, "max_position_qty": 20}
    assert saved[-1].chart_trading.enabled is True and evs == ["state"]
    ev = [e for e in journal(tmp_path) if e["event"] == "chart_trading_set"][-1]
    assert ev["enabled"] is True and ev["max_order_qty"] == 4 and "strategy" not in ev
    for bad, msg in (({"enabled": "yes"}, "enabled: true or false"),
                     ({"max_order_qty": 0}, "max_order_qty: a whole number 1-50"),
                     ({"max_position_qty": 101}, "max_position_qty: a whole number 1-100"),
                     ({"max_order_qty": True}, "max_order_qty: a whole number 1-50"),
                     ([], "the body is a JSON object")):
        with pytest.raises(ValueError, match=re.escape(msg)):
            desk.set_settings(bad)
    assert desk.cfg.chart_trading.max_order_qty == 4             # a refused change changes nothing


def test_disable_switches_off_and_never_raises(tmp_path):
    desk, eng, *_ = mkdesk(tmp_path)

    def broken(cfg):
        raise OSError("disk full")

    desk._save = broken
    desk.disable(cause="kill")
    assert desk.cfg.chart_trading.enabled is False
    ev = [e for e in journal(tmp_path) if e["event"] == "chart_trading_set"][-1]
    assert ev == {**ev, "enabled": False, "cause": "kill"}
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/python -m pytest -q tests/test_trading_views.py`
Expected: FAIL at import (`ChartTradingCfg`, `homebase.trading` missing).

- [ ] **Step 4: Implement the config**

`homebase/config.py`. Add before `@dataclass class AppCfg`:

```python
HARD_MAX_ORDER_QTY = 50        # the desk page cannot set chart-trading limits above these
HARD_MAX_POSITION_QTY = 100


@dataclass
class ChartTradingCfg:
    enabled: bool = False        # orders from the chart page; off until switched on
    max_order_qty: int = 10      # per order, per account
    max_position_qty: int = 20   # worst-case |net| per contract, per account


def chart_trading_from(d) -> ChartTradingCfg:
    """config.json's chart_trading block; anything malformed -> the safe
    defaults (off). `enabled` must be the JSON literal true."""
    base = ChartTradingCfg()
    if not isinstance(d, dict):
        return base
    try:
        c = ChartTradingCfg(enabled=d.get("enabled") is True,
                            max_order_qty=int(d.get("max_order_qty", base.max_order_qty)),
                            max_position_qty=int(d.get("max_position_qty", base.max_position_qty)))
    except (TypeError, ValueError):
        return base
    if not (1 <= c.max_order_qty <= HARD_MAX_ORDER_QTY
            and 1 <= c.max_position_qty <= HARD_MAX_POSITION_QTY):
        return base
    return c
```

Add to `AppCfg`, after `strategies: …`:

```python
    chart_trading: ChartTradingCfg = field(default_factory=ChartTradingCfg)
```

In `load()`, after `cfg.book = {…}`:

```python
    cfg.chart_trading = chart_trading_from(data.get("chart_trading"))
```

(`save()` already writes `asdict(cfg)`, which nests the block.)

- [ ] **Step 5: Implement `homebase/trading.py` (views, events, settings)**

```python
"""Trading from the chart — the desk-side half.

Spec: docs/superpowers/specs/2026-09-26-desk-on-chart-trading-design.md

The chart page asks through the chart service; only the desk talks to the
broker. ChartDesk keeps a live view per account (from the adapters' pushed
caches: no broker call), a view of the bots, and publishes changes to the
SSE stream (desk_api). Every order, modify, cancel, flatten and reverse
starts from a user's click, passes the guards below (authoritative — the
page's checks are a convenience) and is journaled with its result as a
manual_* event. Those events never carry a "strategy" key, so the bots'
live metrics (metrics.py) never count them.

Guards, per account (a refusal is one sentence the page shows as-is):
  1. chart trading is enabled (config chart_trading.enabled, default off;
     the desk's Kill switches it off)
  2. the account exists, is connected, sits on its own pinned broker
     account (adapter.pinned_ok) and its position cache is loaded
  5. at most 5 actions a second per account (checked right after the
     account exists, before any broker work)
  4. the bot lock: an account booked to a strategy whose symbol matches the
     contract (the engine's own substring rule: NQ also claims MNQ) is
     locked 09:20-09:35 ET on weekdays; any account whose day state for
     that strategy is placing|placed|live is locked. Cancelling one of YOUR
     orders by id stays allowed (except while the bot is placing), so a
     manual order can always be cleared before the fire; the bots' own
     orders are never modified or cancelled from the chart.
  3. quantity: 1..max_order_qty per order; the worst-case |net| in the
     contract (position + every working order on that side + this order)
     <= max_position_qty
  6. prices: tick-rounded; a buy stop above / a sell stop below the last
     trade (a fresh quote from the chart service is required); bracket
     stop/target on the losing/winning side of the entry.
"""
from __future__ import annotations

import asyncio
import copy
import datetime as dt
import math
import re
import sys
import time
from collections import deque
from dataclasses import asdict, dataclass
from typing import Callable, Optional

from . import config as config_mod
from . import symbols
from .broker.base import OrderRequest, OrderResult
from .config import (HARD_MAX_ORDER_QTY, HARD_MAX_POSITION_QTY, AppCfg,
                     ChartTradingCfg, assignments)
from .contracts import point_value, root_of, round_to_tick, spec_for

LOCK_FROM, LOCK_UNTIL = dt.time(9, 20), dt.time(9, 35)
BOT_BUSY = ("placing", "placed", "live")
RATE_N, RATE_WINDOW_S = 5, 1.0
QUOTE_MAX_AGE_S = 30.0
FILLS_KEPT = 50
DEDUP_TTL_S = 600.0
SUB_QUEUE_MAX = 500
WATCH_S = 0.5
SIDES = ("Buy", "Sell")
TYPES = ("Market", "Limit", "Stop")
_ROOT = re.compile(r"[A-Z0-9]{1,6}")
_ORDER_ID = re.compile(r"[0-9]{1,20}")


def _log(msg: str) -> None:
    print(f"[trading] {msg}", file=sys.stderr, flush=True)


class Refused(Exception):
    """A guard said no. str(e) is the one sentence the page shows as-is."""


def state_view(st, s) -> dict:
    """One bot day state for the chart: status, the two entry triggers and
    the SL/TP the desk is working. A straddle measures them from the anchor,
    or from the average fill once its brackets were moved
    (engine._move_brackets); a bars rule has absolute levels."""
    sign = {"Buy": 1, "Sell": -1}.get(st.entry_side or "", 0)
    sl = tp = None
    if st.sl_px is not None or st.tp_px is not None:
        sl, tp = st.sl_px, st.tp_px
    elif sign and st.entry_anchor is not None:
        base = st.entry_fill if (st.brackets_moved and st.entry_fill is not None) \
            else st.entry_anchor
        sl = round_to_tick(s.symbol, base - sign * s.sl_pts)
        tp = round_to_tick(s.symbol, base + sign * s.tp_pts)
    return {"status": st.status, "qty": st.qty, "upper": st.upper_px, "lower": st.lower_px,
            "entry_side": st.entry_side, "entry_fill": st.entry_fill,
            "entry_qty": st.entry_qty, "sl": sl, "tp": tp, "exit_fill": st.exit_fill,
            "exit_reason": st.exit_reason, "pnl": st.pnl, "note": st.note}


# --- request parsing + pure guards (added in Task 4) ---


class ChartDesk:
    def __init__(self, cfg: AppCfg, engine, adapters: dict, acct_status: dict, *,
                 timer_status: Callable[[], dict] | None = None,
                 save: Callable[[AppCfg], None] | None = None,
                 mono: Callable[[], float] = time.monotonic):
        self.cfg, self.engine, self.adapters, self.acct_status = cfg, engine, adapters, acct_status
        self.timer_status = timer_status or (lambda: {"date": None, "strategies": {}})
        self._save = save or config_mod.save
        self._mono = mono
        self._hits: dict[str, deque] = {}              # account -> recent action times
        self._done: dict[tuple, tuple[float, dict]] = {}   # (action, client_id) -> (t, result)
        self._fills: dict[str, deque] = {}             # account -> recent fill views
        self._subs: set[asyncio.Queue] = set()
        self._attached: dict[str, object] = {}
        self._last_ids: list | None = None
        self._last_acct: dict[str, dict] = {}
        self._last_bot: dict | None = None
        self._flush_soon = False

    # --- pub/sub ------------------------------------------------------------
    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue(maxsize=SUB_QUEUE_MAX)
        self._subs.add(q)
        return q

    def unsubscribe(self, q) -> None:
        self._subs.discard(q)

    def publish(self, event: str, data: dict) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait((event, data))
            except asyncio.QueueFull:
                # a reader this far behind is dropped with an end marker; it
                # reconnects and starts again from a fresh state
                self._subs.discard(q)
                while not q.empty():
                    q.get_nowait()
                q.put_nowait((None, None))

    def publish_state(self) -> None:
        snap = self.snapshot()
        self._last_ids = list(self.cfg.accounts)
        self._last_acct = {v["id"]: v for v in snap["accounts"]}
        self._last_bot = snap["bot"]
        self.publish("state", snap)

    # --- views ----------------------------------------------------------------
    def _label(self, aid: str) -> str:
        a = self.cfg.accounts.get(aid)
        return (a.label or a.account_name or aid) if a else aid

    def _bot_orders(self, aid: str) -> dict[str, str]:
        """order id -> strategy, for every order a bot placed on this account today."""
        out: dict[str, str] = {}
        for st in self.engine.day_states_for_account(aid):
            for i in (st.upper_id, st.lower_id, st.up_sl_id, st.up_tp_id, st.dn_sl_id, st.dn_tp_id):
                if i:
                    out[str(i)] = st.strategy
        return out

    def _booked(self, aid: str) -> list[str]:
        return [n for n in self.cfg.strategies
                if any(r.get("account") == aid for r in assignments(self.cfg, n))]

    def account_view(self, aid: str) -> dict:
        a = self.cfg.accounts[aid]
        ad = self.adapters.get(aid)
        lv = (ad.trade_view() if ad is not None else None) or {}
        bot = self._bot_orders(aid)
        connected = bool(ad is not None and ad.connected)
        return {
            "id": aid, "label": self._label(aid), "pinned": a.account_name,
            "broker_account": lv.get("broker_account"), "env": "live" if a.live else "demo",
            "connected": connected, "error": (self.acct_status.get(aid) or {}).get("error"),
            "tradable": (connected and bool(a.account_name)
                         and bool(getattr(ad, "pinned_ok", False)) and bool(lv.get("seeded"))),
            "balance": lv.get("balance"), "realized_pnl": lv.get("realized_pnl"),
            "positions": [{**p, "root": root_of(p["symbol"]) if p.get("symbol") else None,
                           "point_value": point_value(p["symbol"]) if p.get("symbol") else None}
                          for p in lv.get("positions", [])],
            "orders": [{**o, "owner": bot.get(str(o.get("order_id")))}
                       for o in lv.get("orders", [])],
            "fills": list(self._fills.get(aid, ())),
            "strategies": self._booked(aid),
        }

    def bot_view(self) -> dict:
        ts = self.timer_status() or {}
        out = {}
        for name, s in self.cfg.strategies.items():
            rows = assignments(self.cfg, name)
            if not rows:
                continue
            out[name] = {
                "symbol": s.symbol, "kind": s.kind, "enabled": s.enabled, "shadow": s.shadow,
                "offset_pts": s.offset_pts, "sl_pts": s.sl_pts, "tp_pts": s.tp_pts,
                "book": {r["account"]: int(r["qty"]) for r in rows},
                # a copy: the timer mutates its own dict, and flush() compares views
                "timer": copy.deepcopy((ts.get("strategies") or {}).get(name)),
                "day_status": self.engine.day_status(name),
                "accounts": {st.account: state_view(st, s) for st in self.engine.day_states(name)},
            }
        return {"date": ts.get("date"), "strategies": out}

    def snapshot(self) -> dict:
        ct = self.cfg.chart_trading
        return {"enabled": ct.enabled,
                "limits": {"max_order_qty": ct.max_order_qty,
                           "max_position_qty": ct.max_position_qty},
                "accounts": [self.account_view(a) for a in self.cfg.accounts],
                "bot": self.bot_view()}

    # --- change detection ------------------------------------------------------
    def flush(self) -> None:
        """Publish what changed since the last flush: the full state when the
        account list changed, else one `account` event per changed account
        and a `bot` event when the bot view changed. Nothing when nobody listens."""
        self._flush_soon = False
        if not self._subs:
            return
        if list(self.cfg.accounts) != self._last_ids:
            self.publish_state()
            return
        for aid in self.cfg.accounts:
            v = self.account_view(aid)
            if v != self._last_acct.get(aid):
                self._last_acct[aid] = v
                self.publish("account", v)
        b = self.bot_view()
        if b != self._last_bot:
            self._last_bot = b
            self.publish("bot", b)

    def _safe_flush(self) -> None:
        try:
            self.flush()
        except Exception as e:  # noqa: BLE001 — views must never take the desk down
            _log(f"flush: {type(e).__name__}: {e}")

    async def run(self, interval_s: float = WATCH_S) -> None:
        """Publish what the pushes do not announce (connection state, the
        bots' day states, the timer): in-memory reads, twice a second."""
        while True:
            self._safe_flush()
            await asyncio.sleep(interval_s)

    def attach(self, aid: str, ad) -> None:
        """Listen to one adapter's pushes (called on every (re)connect; idempotent)."""
        if self._attached.get(aid) is ad:
            return
        self._attached[aid] = ad
        ad.add_listener(lambda et, ent, aid=aid: self._on_entity(aid, et, ent))

    def _fill_view(self, aid: str, ent: dict) -> dict:
        ad = self.adapters.get(aid)
        cid = ent.get("contractId")
        oid = ent.get("orderId")
        oid = str(oid) if oid is not None else None
        return {"id": ent.get("id"), "order_id": oid,
                "symbol": ad.contract_name(cid) if (ad is not None and cid is not None) else None,
                "side": ent.get("action"), "qty": ent.get("qty"), "price": ent.get("price"),
                "time": ent.get("timestamp"),
                "owner": self._bot_orders(aid).get(oid) if oid else None}

    def _on_entity(self, aid: str, et: str, ent: dict) -> None:
        if et == "fill":
            fv = self._fill_view(aid, ent)
            self._fills.setdefault(aid, deque(maxlen=FILLS_KEPT)).append(fv)
            self.publish("fill", {"account": aid, "fill": fv})
        if not self._flush_soon:
            try:
                asyncio.get_running_loop().call_soon(self._safe_flush)
                self._flush_soon = True
            except RuntimeError:            # no running loop: the watch loop catches up
                pass

    # --- settings (the desk page) ----------------------------------------------
    def set_settings(self, body) -> dict:
        """{enabled?, max_order_qty?, max_position_qty?} -> the new settings.
        ValueError (the page shows it) on anything malformed; nothing changes then."""
        if not isinstance(body, dict):
            raise ValueError("the body is a JSON object")
        ct = self.cfg.chart_trading
        new = ChartTradingCfg(enabled=ct.enabled, max_order_qty=ct.max_order_qty,
                              max_position_qty=ct.max_position_qty)
        if "enabled" in body:
            if not isinstance(body["enabled"], bool):
                raise ValueError("enabled: true or false")
            new.enabled = body["enabled"]
        for k, hi in (("max_order_qty", HARD_MAX_ORDER_QTY),
                      ("max_position_qty", HARD_MAX_POSITION_QTY)):
            if k in body:
                v = body[k]
                if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= hi:
                    raise ValueError(f"{k}: a whole number 1-{hi}")
                setattr(new, k, v)
        self.cfg.chart_trading = new
        self._save(self.cfg)
        self.engine.journal("chart_trading_set", **asdict(new))
        self.publish_state()
        return asdict(new)

    def disable(self, cause: str) -> None:
        """Switch chart trading off (the desk's Kill). Never raises: the kill
        must finish; the flag is off in memory before anything can fail."""
        self.cfg.chart_trading.enabled = False
        try:
            self._save(self.cfg)
        except Exception as e:  # noqa: BLE001
            _log(f"chart trading is off, but the config save failed: {e}")
        try:
            self.engine.journal("chart_trading_set", enabled=False, cause=cause)
            self.publish_state()
        except Exception as e:  # noqa: BLE001
            _log(f"disable: {type(e).__name__}: {e}")

    # --- actions: guards + order/modify/cancel/cancel-symbol/flatten/reverse (added in Task 4) ---
```

- [ ] **Step 6: Run to verify the tests pass**

Run: `.venv/bin/python -m pytest -q tests/test_trading_views.py`
Expected: all PASS.

- [ ] **Step 7: Full suite, then commit**

Run: `.venv/bin/python -m pytest -q` (expected: all PASS)

```bash
git add homebase/config.py homebase/trading.py tests/trading_util.py tests/test_trading_views.py
git commit -m "feat(trading): chart_trading config (off by default, 10/20) and the ChartDesk account + bot views, change events and settings" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: `ChartDesk` guards, actions and journaling

**Files:**
- Modify: `homebase/trading.py`. Replace the two `(added in Task 4)` marker comments.
- Test: `tests/test_trading_guards.py`

**Interfaces:**
- Consumes: Task 3's `ChartDesk` internals (`_label`, `_bot_orders`, `_hits`, `_done`, `_mono`, `publish`); the adapters' `trade_view`, `place_order`, `place_bracket`, `modify_order`, `cancel_order_by_id`, `flatten_symbol`, `cancel_symbol`, `get_net_position`.
- Produces:
  - **parsing and pure guards:** `parse_order(body) -> OrderIntent`, `parse_modify`, `parse_cancel`, `parse_symbol_action` (ValueError → HTTP 400 in Task 5), `in_lock_window(now_et) -> bool`, `contract_matches(symbol, contract) -> bool`, `fresh_quote(body, root, now_s) -> dict|None`, `check_prices(...)`, `worst_net(view, contract, side, qty) -> int`.
  - **async actions** (each takes a body dict): `ChartDesk.order`, `.modify`, `.cancel`, `.cancel_symbol`, `.flatten`, `.reverse`. Each returns `{"results": {account: {"ok", "order_id", "error"[, "refused": True]}}}` and publishes a `result` event `{client_id, action, results}`.
  - **journal events:** `manual_order`, `manual_modify`, `manual_cancel`, `manual_flatten`, `manual_reverse` (steps `flatten`, `open`), `manual_refused`. All carry `source="chart"` and never `strategy`.

- [ ] **Step 1: Write the failing tests** — `tests/test_trading_guards.py`:

```python
"""Every chart-trading guard, the bot lock (incl. DST), placement across
accounts, and the journal. No broker, no network."""
from __future__ import annotations

import asyncio
import datetime as dt
import re

import pytest

from homebase.broker.base import OrderResult
from homebase.engine import ET
from homebase.trading import in_lock_window, parse_order
from tests.trading_util import ESC, MNQC, NQC, journal, mkdesk, quote, run

UTC = dt.timezone.utc


def order(desk, **kw):
    body = {"client_id": kw.pop("cid", "c1"), "accounts": kw.pop("accounts", ["a1"]),
            "root": kw.pop("root", "NQ"), "side": "Buy", "qty": 1, "type": "Market", **kw}
    return run(desk.order(body))["results"]


WORKING = {"order_id": "77", "symbol": NQC, "side": "Buy", "type": "Limit", "qty": 2,
           "price": 99.0, "stop_price": None, "status": "Working"}


# --- parsing ---------------------------------------------------------------------
@pytest.mark.parametrize("patch,msg", [
    ({"side": "buy"}, "side: Buy or Sell"),
    ({"type": "StopLimit"}, "type: Market, Limit or Stop"),
    ({"qty": 1.5}, "qty: a whole number"),
    ({"qty": True}, "qty: a whole number"),
    ({"type": "Limit"}, "price is required"),
    ({"price": 100.0}, "a Market order carries no price"),
    ({"accounts": []}, "accounts: a list of 1-20 account ids"),
    ({"root": "N Q"}, "root: a symbol root such as NQ"),
    ({"client_id": ""}, "client_id: a string of 1-64 characters"),
    ({"sl_price": float("nan")}, "sl_price: a positive number"),
])
def test_parse_order_rejects_malformed_bodies(patch, msg):
    body = {"client_id": "c", "accounts": ["a1"], "root": "NQ", "side": "Buy", "qty": 1,
            "type": "Market", **patch}
    with pytest.raises(ValueError, match=re.escape(msg)):
        parse_order(body)


# --- guards 1 and 2 ----------------------------------------------------------------
def test_chart_trading_off_refuses_everything(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path, enabled=False)
    res = order(desk, accounts=["a1", "a2"])
    assert all(r["ok"] is False and r["refused"] for r in res.values())
    assert res["a1"]["error"] == "chart trading is off — switch it on on the desk page"
    assert ads["a1"].orders == [] and ads["a2"].orders == []
    ev = [e for e in journal(tmp_path) if e["event"] == "manual_refused"]
    assert len(ev) == 2 and ev[0]["action"] == "order" and "strategy" not in ev[0]


def test_unknown_disconnected_unpinned_unseeded_accounts_are_refused(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    assert order(desk, accounts=["zz"])["zz"]["error"] == "unknown account 'zz'"
    ads["a1"]._connected = False
    desk.acct_status["a1"] = {"connected": False, "error": "account A1 not on this login (has: A3)"}
    assert order(desk, cid="c2")["a1"]["error"] == \
        "A1 is not connected (account A1 not on this login (has: A3))"
    ads["a1"]._connected = True
    ads["a1"].pinned_ok = False
    assert "pinned broker account" in order(desk, cid="c3")["a1"]["error"]
    ads["a1"].pinned_ok = True
    ads["a1"].view["seeded"] = False
    assert "not loaded yet" in order(desk, cid="c4")["a1"]["error"]
    assert ads["a1"].orders == []


def test_a_root_without_a_contract_spec_is_refused(tmp_path):
    desk, *_ = mkdesk(tmp_path)
    assert order(desk, root="ZZZ")["a1"]["error"] == \
        "ZZZ has no contract spec on the desk — not tradable from the chart"


# --- guard 3: quantity -----------------------------------------------------------------
def test_quantity_limits(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    assert order(desk, qty=0)["a1"]["error"] == "quantity must be 1-10"
    assert order(desk, cid="c2", qty=11)["a1"]["error"] == "quantity must be 1-10"
    assert order(desk, cid="c3", qty=10)["a1"]["ok"] is True
    assert ads["a1"].orders[-1].qty == 10


def test_position_limit_counts_the_position_and_every_working_order(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a1"].view["positions"] = [{"contract_id": 1, "symbol": NQC, "net": 18, "avg_price": 100.0}]
    assert order(desk, qty=3)["a1"]["error"] == \
        f"that could take {NQC} on A1 to 21 contracts (limit 20)"
    assert order(desk, cid="c2", qty=3, side="Sell")["a1"]["ok"] is True       # reducing
    ads["a1"].view["positions"] = [{"contract_id": 2, "symbol": ESC, "net": 20, "avg_price": 5000.0}]
    ads["a1"].view["orders"] = [{**WORKING, "qty": 15}]
    assert order(desk, cid="c3", qty=6)["a1"]["error"].endswith("to 21 contracts (limit 20)")
    assert order(desk, cid="c4", qty=5)["a1"]["ok"] is True                     # ES never counts


def test_an_unresolved_contract_in_the_cache_refuses_orders(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a1"].view["positions"] = [{"contract_id": 9, "symbol": None, "net": 1, "avg_price": 1.0}]
    assert order(desk)["a1"]["error"] == \
        "a position or order's contract is not resolved yet — try again in a moment"


# --- guard 4: the bot lock ---------------------------------------------------------------
@pytest.mark.parametrize("hh,mm,locked", [(9, 19, False), (9, 20, True), (9, 34, True), (9, 35, False)])
def test_bot_lock_window_on_a_booked_account(tmp_path, hh, mm, locked):
    desk, eng, ads, *_ = mkdesk(tmp_path, et=(hh, mm))
    r = order(desk, accounts=["a1", "a2"])
    assert (r["a1"]["ok"] is False) is locked
    if locked:
        assert r["a1"]["error"] == f"{NQC} on A1 is locked 09:20-09:35 ET for the nq930 bot"
    assert r["a2"]["ok"] is True                        # not booked: never window-locked


def test_lock_covers_mnq_but_not_es_and_not_weekends(tmp_path):
    desk, eng, ads, clock, *_ = mkdesk(tmp_path, et=(9, 25))
    assert order(desk, root="MNQ")["a1"]["error"] == \
        f"{MNQC} on A1 is locked 09:20-09:35 ET for the nq930 bot"
    assert order(desk, cid="c2", root="ES")["a1"]["ok"] is True
    clock.dt = dt.datetime(2026, 9, 19, 13, 25, tzinfo=UTC)          # Saturday 09:25 ET
    assert order(desk, cid="c3")["a1"]["ok"] is True


def test_lock_window_follows_new_york_time_across_dst(tmp_path):
    def et(y, m, d, hh, mm):
        return dt.datetime(y, m, d, hh, mm, tzinfo=UTC).astimezone(ET)
    # Fri 2026-03-06 is EST (UTC-5): 14:25 UTC = 09:25 ET locked; 13:25 UTC = 08:25 open
    assert in_lock_window(et(2026, 3, 6, 14, 25)) and not in_lock_window(et(2026, 3, 6, 13, 25))
    # Mon 2026-03-09 is EDT (DST began Sun 03-08): 13:25 UTC = 09:25 locked; 14:25 = 10:25 open
    assert in_lock_window(et(2026, 3, 9, 13, 25)) and not in_lock_window(et(2026, 3, 9, 14, 25))
    # Mon 2026-11-02 is EST again (DST ended Sun 11-01)
    assert in_lock_window(et(2026, 11, 2, 14, 25)) and not in_lock_window(et(2026, 11, 2, 13, 25))
    desk, eng, ads, clock, mono, _ = mkdesk(tmp_path)
    clock.dt = dt.datetime(2026, 3, 9, 13, 25, tzinfo=UTC)
    assert "locked 09:20-09:35" in order(desk)["a1"]["error"]
    clock.dt = dt.datetime(2026, 3, 6, 13, 25, tzinfo=UTC)
    assert order(desk, cid="c2")["a1"]["ok"] is True


@pytest.mark.parametrize("status,locked", [("placing", True), ("placed", True), ("live", True),
                                           ("done", False), ("error", False), ("idle", False)])
def test_the_bots_day_state_locks_its_symbol_on_its_account(tmp_path, status, locked):
    desk, eng, ads, *_ = mkdesk(tmp_path)                             # 11:00 ET: outside the window
    eng._state("nq930", "a1").status = status
    r = order(desk)["a1"]
    assert (not r["ok"]) is locked
    if locked:
        assert r["error"] == (f"{NQC} on A1 belongs to the nq930 bot right now ({status}) "
                              "— use the desk's Kill in an emergency")
    assert order(desk, cid="c2", root="ES")["a1"]["ok"] is True


# --- guard 5: rate -------------------------------------------------------------------------
def test_at_most_five_actions_a_second_per_account(tmp_path):
    desk, eng, ads, clock, mono, _ = mkdesk(tmp_path)
    oks = [order(desk, cid=f"c{i}")["a1"]["ok"] for i in range(6)]
    assert oks == [True] * 5 + [False]
    assert order(desk, cid="c5")["a1"]["error"] == "too fast — at most 5 actions a second on A1"
    assert order(desk, cid="c9", accounts=["a2"])["a2"]["ok"] is True          # per account
    mono.t += 1.0
    assert order(desk, cid="c10")["a1"]["ok"] is True


# --- guard 6: prices -------------------------------------------------------------------------
def test_stop_orders_need_a_fresh_price_on_the_right_side(tmp_path):
    desk, eng, ads, clock, mono, _ = mkdesk(tmp_path)
    q = quote(clock, last=100.25)
    assert order(desk, type="Stop", price=100.0, quotes=q)["a1"]["error"] == \
        "a buy stop must be above the last price (100.25)"
    assert order(desk, cid="c2", type="Stop", side="Sell", price=100.5, quotes=q)["a1"]["error"] == \
        "a sell stop must be below the last price (100.25)"
    assert order(desk, cid="c3", type="Stop", price=101.0)["a1"]["error"] == \
        f"no trade in {NQC} in the last 30 s — a stop order needs a fresh price"
    stale = quote(clock, last=100.25, age_s=31)
    assert "no trade" in order(desk, cid="c4", type="Stop", price=101.0, quotes=stale)["a1"]["error"]
    mono.t += 1
    assert order(desk, cid="c5", type="Stop", price=101.0, quotes=q)["a1"]["ok"] is True
    o = ads["a1"].orders[-1]
    assert (o.order_type, o.price, o.symbol) == ("Stop", 101.0, NQC)


def test_prices_are_tick_rounded(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    assert order(desk, type="Limit", price=100.1)["a1"]["ok"] is True
    assert ads["a1"].orders[-1].price == 100.0
    assert order(desk, cid="c2", type="Limit", price=100.13, sl_price=95.06,
                 tp_price=110.2)["a1"]["ok"] is True
    b = ads["a1"].brackets[-1]
    assert (b.price, b.stop_price, b.tp_price) == (100.25, 95.0, 110.25)


def test_bracket_levels_must_sit_on_the_right_sides(tmp_path):
    desk, eng, ads, clock, *_ = mkdesk(tmp_path)
    assert order(desk, type="Limit", price=100.0, sl_price=101.0)["a1"]["error"] == \
        "the stop loss must be on the losing side of the entry"
    assert order(desk, cid="c2", type="Limit", side="Sell", price=100.0,
                 tp_price=101.0)["a1"]["error"] == "the target must be on the winning side of the entry"
    assert order(desk, cid="c3", sl_price=99.0)["a1"]["error"] == \
        f"no trade in {NQC} in the last 30 s — a bracket on a market order needs a fresh price"
    r = order(desk, cid="c4", sl_price=99.0, tp_price=102.0, quotes=quote(clock, last=100.0))["a1"]
    assert r["ok"] is True and ads["a1"].brackets[-1].order_type == "Market"
    assert ads["a1"].orders == []                          # brackets go through place_bracket only


# --- placement, dedup, journal -----------------------------------------------------------------
def test_one_order_goes_to_every_ticked_account_with_a_result_each(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a2"]._connected = False
    r = order(desk, accounts=["a1", "a2", "a1"])
    assert list(r) == ["a1", "a2"]
    assert r["a1"] == {"ok": True, "order_id": "plain", "error": None}
    assert r["a2"]["ok"] is False and r["a2"]["error"] == "A2 is not connected"
    placed = [e for e in journal(tmp_path) if e["event"] == "manual_order"]
    assert len(placed) == 1 and placed[0]["account"] == "a1" and placed[0]["contract"] == NQC
    assert placed[0]["source"] == "chart" and "strategy" not in placed[0]


def test_accounts_are_placed_concurrently(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)

    async def go():
        both, started = asyncio.Event(), []

        async def slow(req, ad):
            started.append(ad.account_id)
            if len(started) == 2:
                both.set()
            await asyncio.wait_for(both.wait(), 1.0)    # a sequential placement would time out here
            return OrderResult(ok=True, order_id=ad.account_id)

        for ad in ads.values():
            ad.place_order = (lambda req, ad=ad: slow(req, ad))
        return await desk.order({"client_id": "c", "accounts": ["a1", "a2"], "root": "NQ",
                                 "side": "Buy", "qty": 1, "type": "Market"})

    out = run(go())["results"]
    assert out["a1"]["order_id"] == "a1" and out["a2"]["order_id"] == "a2"


def test_a_repeated_client_id_returns_the_first_result_without_placing_again(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    first = order(desk)
    assert order(desk) == first and len(ads["a1"].orders) == 1


def test_every_action_publishes_its_result(tmp_path):
    desk, *_ = mkdesk(tmp_path)

    async def go():
        q = desk.subscribe()
        await desk.order({"client_id": "c", "accounts": ["a1"], "root": "NQ", "side": "Buy",
                          "qty": 1, "type": "Market"})
        return q.get_nowait()

    ev, data = run(go())
    assert ev == "result" and data["client_id"] == "c" and data["action"] == "order"
    assert data["results"]["a1"]["ok"] is True


# --- modify / cancel ---------------------------------------------------------------------------
def test_modify_moves_a_manual_order_tick_rounded(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a1"].view["orders"] = [dict(WORKING)]
    r = run(desk.modify({"client_id": "m1", "account": "a1", "order_id": "77", "price": 98.6}))
    assert r["results"]["a1"] == {"ok": True, "order_id": "77", "error": None}
    assert ads["a1"].modified == [("77", "Limit", 98.5)]
    assert [e["event"] for e in journal(tmp_path)][-1] == "manual_modify"


def test_modify_refuses_bot_orders_unknown_orders_and_wrong_side_stops(tmp_path):
    desk, eng, ads, clock, *_ = mkdesk(tmp_path)
    st = eng._state("nq930", "a1")
    st.status, st.up_sl_id = "done", "55"
    stop = {**WORKING, "type": "Stop", "side": "Sell", "price": None, "stop_price": 95.0}
    ads["a1"].view["orders"] = [dict(WORKING), {**stop, "order_id": "55"}, {**stop, "order_id": "56"}]

    def m(cid, oid, px, **kw):
        body = {"client_id": cid, "account": "a1", "order_id": oid, "price": px, **kw}
        return run(desk.modify(body))["results"]["a1"]

    assert m("m1", "55", 96.0)["error"] == \
        "order 55 belongs to the nq930 bot — it cannot be changed from the chart"
    assert m("m2", "99", 96.0)["error"] == "order 99 is not working on A1"
    assert m("m3", "56", 101.0, quotes=quote(clock, last=100.0))["error"] == \
        "a sell stop must be below the last price (100.0)"
    assert m("m4", "56", 96.0, quotes=quote(clock, last=100.0))["ok"] is True
    assert ads["a1"].modified == [("56", "Stop", 96.0)]


def test_cancel_by_id_stays_allowed_in_the_window_but_never_for_bot_orders(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path, et=(9, 25))
    st = eng._state("nq930", "a1")
    st.status, st.upper_id = "placed", "60"
    ads["a1"].view["orders"] = [dict(WORKING), {**WORKING, "order_id": "60", "type": "Stop"}]

    def c(cid, oid):
        return run(desk.cancel({"client_id": cid, "account": "a1", "order_id": oid}))["results"]["a1"]

    assert c("x1", "77")["ok"] is True
    assert c("x2", "60")["error"] == \
        "order 60 belongs to the nq930 bot — it cannot be changed from the chart"
    st.status = "placing"
    assert c("x3", "77")["error"].startswith(f"{NQC} on A1 belongs to the nq930 bot right now (placing)")
    assert ads["a1"].cancelled == ["77"]
    assert [e["event"] for e in journal(tmp_path) if e["event"].startswith("manual_")] == \
        ["manual_cancel", "manual_refused", "manual_refused"]


# --- flatten / cancel-symbol / reverse ------------------------------------------------------------
def test_flatten_and_cancel_symbol_are_symbol_scoped_and_journaled(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    body = {"client_id": "f1", "accounts": ["a1", "a2"], "root": "NQ"}
    r = run(desk.flatten(body))["results"]
    assert r["a1"]["ok"] and r["a2"]["ok"]
    assert ads["a1"].flattened == [NQC] and ads["a2"].flattened == [NQC]
    run(desk.cancel_symbol({**body, "client_id": "f2"}))
    assert ads["a1"].sym_cancelled == [NQC] and ads["a2"].sym_cancelled == [NQC]
    ev = [e for e in journal(tmp_path) if e["event"] in ("manual_flatten", "manual_cancel")]
    assert [e["event"] for e in ev] == ["manual_flatten"] * 2 + ["manual_cancel"] * 2
    assert all(e["source"] == "chart" and "strategy" not in e for e in ev)


def test_flatten_is_locked_in_the_window_for_the_booked_account_only(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path, et=(9, 25))
    r = run(desk.flatten({"client_id": "f1", "accounts": ["a1", "a2"], "root": "NQ"}))["results"]
    assert r["a1"]["error"] == f"{NQC} on A1 is locked 09:20-09:35 ET for the nq930 bot"
    assert r["a2"]["ok"] is True and ads["a1"].flattened == []


def test_reverse_flattens_then_opens_the_other_side(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)
    ads["a1"].net = 2
    r = run(desk.reverse({"client_id": "r1", "accounts": ["a1"], "root": "NQ"}))["results"]["a1"]
    assert r["ok"] is True and ads["a1"].flattened == [NQC]
    o = ads["a1"].orders[-1]
    assert (o.symbol, o.side, o.qty, o.order_type) == (NQC, "Sell", 2, "Market")
    assert [e["step"] for e in journal(tmp_path) if e["event"] == "manual_reverse"] == ["flatten", "open"]


def test_reverse_refuses_flat_oversized_and_a_failed_flatten(tmp_path):
    desk, eng, ads, *_ = mkdesk(tmp_path)

    def rv(cid):
        return run(desk.reverse({"client_id": cid, "accounts": ["a1"], "root": "NQ"}))["results"]["a1"]

    assert rv("r1")["error"] == f"no {NQC} position on A1 to reverse"
    ads["a1"].net = -11
    assert rv("r2")["error"] == "reversing 11 is over the per-order limit (10)"
    ads["a1"].net, ads["a1"].fail_flatten = -3, True
    assert rv("r3")["error"] == "flatten failed: flatten rejected by test — not reversed"
    assert ads["a1"].orders == []
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest -q tests/test_trading_guards.py`
Expected: FAIL at import (`in_lock_window`, `parse_order` missing).

- [ ] **Step 3: Implement parsing and pure guards.** Replace the line `# --- request parsing + pure guards (added in Task 4) ---` in `homebase/trading.py` with:

```python
# --- request parsing (ValueError -> HTTP 400 in desk_api) --------------------------
def _finite(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _price(v, name: str, *, required: bool = False) -> Optional[float]:
    if v is None:
        if required:
            raise ValueError(f"{name} is required")
        return None
    if not _finite(v) or v <= 0:
        raise ValueError(f"{name}: a positive number")
    return float(v)


def _obj(body) -> dict:
    if not isinstance(body, dict):
        raise ValueError("the body is a JSON object")
    return body


def _client_id(body: dict) -> str:
    cid = body.get("client_id")
    if not isinstance(cid, str) or not 1 <= len(cid) <= 64:
        raise ValueError("client_id: a string of 1-64 characters")
    return cid


def _account(body: dict) -> str:
    a = body.get("account")
    if not isinstance(a, str) or not 1 <= len(a) <= 64:
        raise ValueError("account: an account id")
    return a


def _accounts(body: dict) -> tuple:
    a = body.get("accounts")
    if not isinstance(a, list) or not 1 <= len(a) <= 20 \
            or not all(isinstance(x, str) and 1 <= len(x) <= 64 for x in a):
        raise ValueError("accounts: a list of 1-20 account ids")
    return tuple(dict.fromkeys(a))                    # de-duplicated, order kept


def _root(body: dict) -> str:
    r = body.get("root")
    if not isinstance(r, str) or not _ROOT.fullmatch(r.upper()):
        raise ValueError("root: a symbol root such as NQ")
    return r.upper()


def _order_id(body: dict) -> str:
    o = body.get("order_id")
    if isinstance(o, int) and not isinstance(o, bool):
        o = str(o)
    if not isinstance(o, str) or not _ORDER_ID.fullmatch(o):
        raise ValueError("order_id: the broker's numeric order id")
    return o


@dataclass(frozen=True)
class OrderIntent:
    client_id: str
    accounts: tuple
    root: str
    side: str
    qty: int
    type: str
    price: Optional[float]
    sl_price: Optional[float]
    tp_price: Optional[float]


def parse_order(body) -> OrderIntent:
    body = _obj(body)
    side, typ, qty = body.get("side"), body.get("type"), body.get("qty")
    if side not in SIDES:
        raise ValueError("side: Buy or Sell")
    if typ not in TYPES:
        raise ValueError("type: Market, Limit or Stop")
    if isinstance(qty, bool) or not isinstance(qty, int):
        raise ValueError("qty: a whole number")
    price = _price(body.get("price"), "price", required=typ != "Market")
    if typ == "Market" and price is not None:
        raise ValueError("a Market order carries no price")
    return OrderIntent(_client_id(body), _accounts(body), _root(body), side, qty, typ, price,
                       _price(body.get("sl_price"), "sl_price"),
                       _price(body.get("tp_price"), "tp_price"))


def parse_modify(body) -> tuple:
    body = _obj(body)
    return (_client_id(body), _account(body), _order_id(body),
            _price(body.get("price"), "price", required=True))


def parse_cancel(body) -> tuple:
    body = _obj(body)
    return _client_id(body), _account(body), _order_id(body)


def parse_symbol_action(body) -> tuple:
    body = _obj(body)
    return _client_id(body), _accounts(body), _root(body)


# --- pure guards ---------------------------------------------------------------------
def in_lock_window(now_et: dt.datetime) -> bool:
    """09:20:00 <= t < 09:35:00 ET on a weekday. `now_et` is ET-aware
    (engine.now_et()), so DST is the zone's business, not ours."""
    return now_et.weekday() < 5 and LOCK_FROM <= now_et.time() < LOCK_UNTIL


def contract_matches(strategy_symbol: str, contract: str) -> bool:
    """engine.on_fill gives a fill to a strategy when the strategy's symbol
    is a SUBSTRING of the fill's contract (NQ claims MNQZ6). The lock uses
    the same rule, never a narrower one."""
    return bool(strategy_symbol) and strategy_symbol.upper() in str(contract or "").upper()


def fresh_quote(body: dict, root: str, now_s: float) -> Optional[dict]:
    """The chart service's latest quote for `root` (body["quotes"]), if its
    last trade is at most QUOTE_MAX_AGE_S old; else None."""
    qs = body.get("quotes") if isinstance(body, dict) else None
    q = qs.get(root) if isinstance(qs, dict) else None
    if not isinstance(q, dict):
        return None
    last, ts = q.get("last"), q.get("ts_ms")
    if not _finite(last) or not _finite(ts) or now_s - ts / 1000.0 > QUOTE_MAX_AGE_S:
        return None
    return {"last": float(last),
            "bid": float(q["bid"]) if _finite(q.get("bid")) else None,
            "ask": float(q["ask"]) if _finite(q.get("ask")) else None}


def check_prices(side: str, typ: str, price, sl, tp, contract: str,
                 quote: Optional[dict]) -> tuple:
    """Tick-round every price; refuse a stop on the wrong side of the last
    trade, and a bracket whose stop/target sit on the wrong side of the
    entry. Returns (price, sl, tp) rounded."""
    def rnd(p):
        return None if p is None else round_to_tick(contract, p)

    price, sl, tp = rnd(price), rnd(sl), rnd(tp)
    last = quote["last"] if quote else None
    fresh = f"no trade in {contract} in the last {QUOTE_MAX_AGE_S:.0f} s"
    if typ == "Stop":
        if last is None:
            raise Refused(f"{fresh} — a stop order needs a fresh price")
        if side == "Buy" and price <= last:
            raise Refused(f"a buy stop must be above the last price ({last:,})")
        if side == "Sell" and price >= last:
            raise Refused(f"a sell stop must be below the last price ({last:,})")
    if sl is not None or tp is not None:
        ref = price if typ != "Market" else last
        if ref is None:
            raise Refused(f"{fresh} — a bracket on a market order needs a fresh price")
        sign = 1 if side == "Buy" else -1
        if sl is not None and not sign * (ref - sl) > 0:
            raise Refused("the stop loss must be on the losing side of the entry")
        if tp is not None and not sign * (tp - ref) > 0:
            raise Refused("the target must be on the winning side of the entry")
    return price, sl, tp


def worst_net(view: dict, contract: str, side: str, qty: int) -> int:
    """Worst-case |net| in `contract` if this order AND every working order
    on its side fill. An OCO pair counts twice (conservative)."""
    net = sum(int(p.get("net") or 0) for p in view.get("positions", [])
              if p.get("symbol") == contract)
    mine = [o for o in view.get("orders", []) if o.get("symbol") == contract]
    buys = sum(int(o.get("qty") or 0) for o in mine if o.get("side") == "Buy")
    sells = sum(int(o.get("qty") or 0) for o in mine if o.get("side") == "Sell")
    up = net + buys + (qty if side == "Buy" else 0)
    dn = net - sells - (qty if side == "Sell" else 0)
    return max(abs(up), abs(dn))


async def _call(coro) -> OrderResult:
    """A broker call whose raise is a failed result, never an exception."""
    try:
        return await coro
    except Exception as e:  # noqa: BLE001
        return OrderResult(ok=False, error=str(e))
```

- [ ] **Step 4: Implement the guards and actions.** Replace the line `    # --- actions: guards + order/modify/cancel/cancel-symbol/flatten/reverse (added in Task 4) ---` with:

```python
    # --- guards -------------------------------------------------------------------
    def _gate(self, aid: str) -> tuple:
        """Guards 1, 2 and 5. Returns (adapter, live view, label)."""
        if not self.cfg.chart_trading.enabled:
            raise Refused("chart trading is off — switch it on on the desk page")
        a = self.cfg.accounts.get(aid)
        if a is None:
            raise Refused(f"unknown account {aid!r}")
        label = self._label(aid)
        now = self._mono()
        hits = self._hits.setdefault(aid, deque())
        while hits and now - hits[0] >= RATE_WINDOW_S:
            hits.popleft()
        if len(hits) >= RATE_N:
            raise Refused(f"too fast — at most {RATE_N} actions a second on {label}")
        hits.append(now)
        ad = self.adapters.get(aid)
        if ad is None or not ad.connected:
            err = (self.acct_status.get(aid) or {}).get("error")
            raise Refused(f"{label} is not connected" + (f" ({err})" if err else ""))
        if not a.account_name or not getattr(ad, "pinned_ok", False):
            raise Refused(f"{label} is not on its own pinned broker account — "
                          "chart trading refuses it")
        view = ad.trade_view()
        if not view or not view.get("seeded"):
            raise Refused(f"{label}'s positions are not loaded yet — try again in a moment")
        return ad, view, label

    def _contract(self, root: str) -> str:
        if not spec_for(root).known:
            raise Refused(f"{root} has no contract spec on the desk — not tradable from the chart")
        try:
            return symbols.resolve_contract(root)
        except ValueError as e:
            raise Refused(f"{root}: no front contract ({e})") from None

    def _day_state(self, aid: str, name: str):
        return next((s for s in self.engine.day_states_for_account(aid) if s.strategy == name), None)

    def _lock(self, aid: str, contract: str, label: str, *, cancel_by_id: bool = False) -> None:
        """Guard 4. A cancel by id of a non-bot order is only refused while
        a bot is placing (its new orders are not yet known by id)."""
        for name, s in self.cfg.strategies.items():
            if not contract_matches(s.symbol, contract):
                continue
            st = self._day_state(aid, name)
            if st is not None and st.status in BOT_BUSY \
                    and not (cancel_by_id and st.status != "placing"):
                raise Refused(f"{contract} on {label} belongs to the {name} bot right now "
                              f"({st.status}) — use the desk's Kill in an emergency")
            if cancel_by_id:
                continue
            if in_lock_window(self.engine.now_et()) \
                    and any(r.get("account") == aid for r in assignments(self.cfg, name)):
                raise Refused(f"{contract} on {label} is locked 09:20-09:35 ET for the {name} bot")

    @staticmethod
    def _unresolved(view: dict) -> None:
        if any(p.get("symbol") is None for p in view.get("positions", [])) \
                or any(o.get("symbol") is None for o in view.get("orders", [])):
            raise Refused("a position or order's contract is not resolved yet — try again in a moment")

    def _not_bot_order(self, aid: str, oid: str) -> None:
        owner = self._bot_orders(aid).get(oid)
        if owner:
            raise Refused(f"order {oid} belongs to the {owner} bot — it cannot be changed from the chart")

    def _now_s(self) -> float:
        return self.engine.now_et().timestamp()

    # --- bookkeeping ------------------------------------------------------------------
    def _dedup(self, action: str, cid: str) -> Optional[dict]:
        now = self._mono()
        for k in [k for k, (t, _) in self._done.items() if now - t > DEDUP_TTL_S]:
            del self._done[k]
        hit = self._done.get((action, cid))
        return hit[1] if hit else None

    def _finish(self, action: str, cid: str, results: dict) -> dict:
        out = {"results": results}
        self._done[(action, cid)] = (self._mono(), out)
        self.publish("result", {"client_id": cid, "action": action, **out})
        return out

    def _refuse(self, action: str, cid: str, aid: str, reason: str) -> dict:
        self.engine.journal("manual_refused", source="chart", action=action, client_id=cid,
                            account=aid, reason=reason)
        return {"ok": False, "order_id": None, "error": reason, "refused": True}

    @staticmethod
    def _gathered(accounts: tuple, outs: list) -> dict:
        return {aid: (o if isinstance(o, dict) else
                      {"ok": False, "order_id": None, "error": f"internal error: {o}"})
                for aid, o in zip(accounts, outs)}

    # --- order ------------------------------------------------------------------------
    async def order(self, body) -> dict:
        it = parse_order(body)
        hit = self._dedup("order", it.client_id)
        if hit is not None:
            return hit
        quote = fresh_quote(body, it.root, self._now_s())
        outs = await asyncio.gather(*(self._order_one(it, aid, quote) for aid in it.accounts),
                                    return_exceptions=True)
        return self._finish("order", it.client_id, self._gathered(it.accounts, outs))

    async def _order_one(self, it: OrderIntent, aid: str, quote: Optional[dict]) -> dict:
        try:
            ad, view, label = self._gate(aid)
            contract = self._contract(it.root)
            self._lock(aid, contract, label)
            lim = self.cfg.chart_trading
            if not 1 <= it.qty <= lim.max_order_qty:
                raise Refused(f"quantity must be 1-{lim.max_order_qty}")
            self._unresolved(view)
            worst = worst_net(view, contract, it.side, it.qty)
            if worst > lim.max_position_qty:
                raise Refused(f"that could take {contract} on {label} to {worst} contracts "
                              f"(limit {lim.max_position_qty})")
            price, sl, tp = check_prices(it.side, it.type, it.price, it.sl_price, it.tp_price,
                                         contract, quote)
        except Refused as e:
            return self._refuse("order", it.client_id, aid, str(e))
        req = OrderRequest(symbol=contract, side=it.side, qty=it.qty, order_type=it.type,
                           price=price, stop_price=sl, tp_price=tp, text="homebase:chart")
        bracket = sl is not None or tp is not None
        r = await _call(ad.place_bracket(req) if bracket else ad.place_order(req))
        self.engine.journal("manual_order", source="chart", client_id=it.client_id, account=aid,
                            root=it.root, contract=contract, side=it.side, qty=it.qty,
                            type=it.type, price=price, sl=sl, tp=tp, ok=r.ok,
                            order_id=r.order_id, error=r.error)
        return {"ok": r.ok, "order_id": r.order_id, "error": r.error}

    # --- modify / cancel (one account, one order) ---------------------------------------
    def _find_order(self, view: dict, oid: str, label: str) -> dict:
        o = next((o for o in view.get("orders", []) if str(o.get("order_id")) == oid), None)
        if o is None:
            raise Refused(f"order {oid} is not working on {label}")
        return o

    async def modify(self, body) -> dict:
        cid, aid, oid, price = parse_modify(body)
        hit = self._dedup("modify", cid)
        if hit is not None:
            return hit
        try:
            ad, view, label = self._gate(aid)
            o = self._find_order(view, oid, label)
            self._not_bot_order(aid, oid)
            contract = o.get("symbol")
            if not contract:
                raise Refused("that order's contract is not resolved yet — try again in a moment")
            self._lock(aid, contract, label)
            typ = o.get("type")
            if typ not in ("Limit", "Stop"):
                raise Refused(f"only Limit and Stop orders can be moved (this one is {typ})")
            px = round_to_tick(contract, price)
            if typ == "Stop":
                check_prices(o.get("side"), "Stop", px, None, None, contract,
                             fresh_quote(body, root_of(contract), self._now_s()))
        except Refused as e:
            return self._finish("modify", cid, {aid: self._refuse("modify", cid, aid, str(e))})
        r = await _call(ad.modify_order(oid, typ,
                                        price=px if typ == "Limit" else None,
                                        stop_price=px if typ == "Stop" else None,
                                        qty=int(o.get("qty") or 0) or None))
        self.engine.journal("manual_modify", source="chart", client_id=cid, account=aid,
                            order_id=oid, contract=contract, type=typ, price=px,
                            ok=r.ok, error=r.error)
        return self._finish("modify", cid, {aid: {"ok": r.ok, "order_id": oid, "error": r.error}})

    async def cancel(self, body) -> dict:
        cid, aid, oid = parse_cancel(body)
        hit = self._dedup("cancel", cid)
        if hit is not None:
            return hit
        try:
            ad, view, label = self._gate(aid)
            o = self._find_order(view, oid, label)
            self._not_bot_order(aid, oid)
            contract = o.get("symbol")
            if contract:
                self._lock(aid, contract, label, cancel_by_id=True)
            elif any(s.status == "placing" for s in self.engine.day_states_for_account(aid)):
                raise Refused("a bot is placing on this account — try again in a second")
        except Refused as e:
            return self._finish("cancel", cid, {aid: self._refuse("cancel", cid, aid, str(e))})
        r = await _call(ad.cancel_order_by_id(oid))
        self.engine.journal("manual_cancel", source="chart", scope="order", client_id=cid,
                            account=aid, order_id=oid, contract=contract, ok=r.ok, error=r.error)
        return self._finish("cancel", cid, {aid: {"ok": r.ok, "order_id": oid, "error": r.error}})

    # --- per-symbol actions (many accounts) -------------------------------------------------
    async def _per_symbol(self, action: str, body, fn) -> dict:
        cid, accounts, root = parse_symbol_action(body)
        hit = self._dedup(action, cid)
        if hit is not None:
            return hit
        outs = await asyncio.gather(*(self._symbol_one(action, cid, aid, root, fn)
                                      for aid in accounts), return_exceptions=True)
        return self._finish(action, cid, self._gathered(accounts, outs))

    async def _symbol_one(self, action: str, cid: str, aid: str, root: str, fn) -> dict:
        try:
            ad, view, label = self._gate(aid)
            contract = self._contract(root)
            self._lock(aid, contract, label)
            return await fn(cid, aid, ad, contract, label)
        except Refused as e:
            return self._refuse(action, cid, aid, str(e))

    async def cancel_symbol(self, body) -> dict:
        return await self._per_symbol("cancel-symbol", body, self._do_cancel_symbol)

    async def flatten(self, body) -> dict:
        return await self._per_symbol("flatten", body, self._do_flatten)

    async def reverse(self, body) -> dict:
        return await self._per_symbol("reverse", body, self._do_reverse)

    async def _do_cancel_symbol(self, cid, aid, ad, contract, label) -> dict:
        r = await _call(ad.cancel_symbol(contract))
        self.engine.journal("manual_cancel", source="chart", scope="symbol", client_id=cid,
                            account=aid, contract=contract, ok=r.ok, error=r.error,
                            cancelled=(r.raw or {}).get("cancelled"))
        return {"ok": r.ok, "order_id": None, "error": r.error}

    async def _do_flatten(self, cid, aid, ad, contract, label) -> dict:
        r = await _call(ad.flatten_symbol(contract))
        self.engine.journal("manual_flatten", source="chart", client_id=cid, account=aid,
                            contract=contract, ok=r.ok, error=r.error, detail=r.raw)
        return {"ok": r.ok, "order_id": None, "error": r.error}

    async def _do_reverse(self, cid, aid, ad, contract, label) -> dict:
        try:
            net = await ad.get_net_position(contract)
        except Exception as e:  # noqa: BLE001 — unreadable is not flat
            raise Refused(f"the {contract} position on {label} is unreadable ({e}) — nothing done") from None
        if not net:
            raise Refused(f"no {contract} position on {label} to reverse")
        lim = self.cfg.chart_trading
        if abs(net) > lim.max_order_qty or abs(net) > lim.max_position_qty:
            raise Refused(f"reversing {abs(net)} is over the per-order limit ({lim.max_order_qty})")
        f = await _call(ad.flatten_symbol(contract))
        self.engine.journal("manual_reverse", source="chart", step="flatten", client_id=cid,
                            account=aid, contract=contract, net_before=net, ok=f.ok, error=f.error)
        if not f.ok:
            return {"ok": False, "order_id": None, "error": f"flatten failed: {f.error} — not reversed"}
        side = "Sell" if net > 0 else "Buy"
        r = await _call(ad.place_order(OrderRequest(symbol=contract, side=side, qty=abs(net),
                                                    order_type="Market",
                                                    text="homebase:chart-reverse")))
        self.engine.journal("manual_reverse", source="chart", step="open", client_id=cid,
                            account=aid, contract=contract, side=side, qty=abs(net), ok=r.ok,
                            order_id=r.order_id, error=r.error)
        return {"ok": r.ok, "order_id": r.order_id, "error": r.error}
```

- [ ] **Step 5: Run the guard and view tests**

Run: `.venv/bin/python -m pytest -q tests/test_trading_guards.py tests/test_trading_views.py`
Expected: all PASS.

- [ ] **Step 6: Full suite, then commit**

Run: `.venv/bin/python -m pytest -q` (expected: all PASS)

```bash
git add homebase/trading.py tests/test_trading_guards.py
git commit -m "feat(trading): chart-trading guards (enabled, own pinned account, qty, bot lock with DST, rate, stop side, tick rounding), concurrent multi-account actions, manual_* journal" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: `desk_api.py`: key, SSE, `/api/trade/*`, `/api/chart-trading`, and mounting it in the desk

**Files:**
- Create: `homebase/desk_api.py`
- Modify: `homebase/server.py` (small insertions only), `deploy/com.ramosquant.homebase.plist.template`
- Test: `tests/test_desk_api.py`

**Interfaces:**
- Consumes:
  - `ChartDesk.snapshot/subscribe/unsubscribe/order/modify/cancel/cancel_symbol/flatten/reverse/set_settings/disable/attach/run` (Tasks 3–4);
  - `ChartTradingCfg` (Task 3).
- Produces:
  - `desk_api.KEY_FILE = "desk.key"`, `ensure_key(path) -> (key|None, error|None)`, `sse(event, data) -> str`, `async event_stream(desk, *, heartbeat_s=15.0)`, `read_json(request, limit)`, `trade_router(desk)` (mounted at `/api/trade`), `settings_router(desk)` (`POST /api/chart-trading`).
  - `app.state.desk`, `app.state.desk_key`.
  - `/api/status` gains `"chart_trading": {enabled, max_order_qty, max_position_qty}`.
  - `/api/kill` switches chart trading off.

- [ ] **Step 1: Write the failing tests** — `tests/test_desk_api.py`:

```python
"""/api/trade/* (key + no-Origin), the SSE stream, /api/chart-trading, the
Kill, the key file. No network, no broker: TradeAdapter fakes."""
from __future__ import annotations

import os
import plistlib
import re
import stat
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import homebase.config as config_mod
from homebase.config import AccountCfg, AppCfg, ChartTradingCfg, StrategyCfg
from homebase.desk_api import ensure_key, event_stream
from homebase.server import create_app
from tests.trading_util import NQC, TradeAdapter, journal, mkdesk, run

ACTIONS = ("order", "modify", "cancel", "cancel-symbol", "flatten", "reverse")


@pytest.fixture()
def desk_client(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.paths.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.engine.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.server.state_dir", lambda: tmp_path)
    monkeypatch.setattr("homebase.secrets_store.state_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")
    cfg = AppCfg(armed=False, webhook_secret="s",
                 accounts={"a1": AccountCfg(keyring_key="k", account_name="A1", label="A1")},
                 book={},                                  # nothing booked: never bot-locked
                 strategies={"nq930": StrategyCfg(symbol="NQ", qty=3, offset_pts=10.0,
                                                  sl_pts=5.0, tp_pts=15.0, enabled=True)},
                 chart_trading=ChartTradingCfg(enabled=True))
    adapters = {"a1": TradeAdapter("a1")}
    app = create_app(cfg, adapters, background=False)
    with TestClient(app) as c:
        c.app, c.adapters, c.tmp = app, adapters, tmp_path
        c.key = (tmp_path / "desk.key").read_text().strip()
        c.H = {"X-Homebase-Key": c.key}
        yield c


# --- the key -----------------------------------------------------------------------
def test_the_key_file_is_created_0600_with_a_hex_key(desk_client):
    p = desk_client.tmp / "desk.key"
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    assert re.fullmatch(r"[0-9a-f]{64}", desk_client.key)


def test_an_existing_key_is_kept_and_tightened(tmp_path):
    p = tmp_path / "desk.key"
    p.write_text("ab" * 32 + "\n")
    os.chmod(p, 0o644)
    assert ensure_key(p) == ("ab" * 32, None)
    assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_a_corrupt_key_never_raises(tmp_path):
    p = tmp_path / "desk.key"
    p.write_text("nope")
    key, err = ensure_key(p)
    assert key is None and "desk.key does not hold a desk key" in err


# --- the gate on every trade route -------------------------------------------------------
def test_every_trade_route_needs_the_key_and_refuses_browsers(desk_client):
    c = desk_client
    routes = [("get", "/api/trade/state"), ("get", "/api/trade/stream")] + \
             [("post", f"/api/trade/{a}") for a in ACTIONS]
    for m, url in routes:
        assert getattr(c, m)(url).status_code == 401, url
        assert getattr(c, m)(url, headers={"X-Homebase-Key": "0" * 64}).status_code == 401, url
        assert getattr(c, m)(url, headers={**c.H, "Origin": "http://127.0.0.1:8850"}).status_code == 403, url


def test_state_is_the_cached_snapshot(desk_client):
    d = desk_client.get("/api/trade/state", headers=desk_client.H).json()
    assert d["enabled"] is True and d["accounts"][0]["id"] == "a1" and "bot" in d


def test_order_route_validates_then_answers_per_account(desk_client):
    c = desk_client
    good = {"client_id": "c", "accounts": ["a1"], "root": "NQ", "side": "Buy", "qty": 1,
            "type": "Market"}
    assert c.post("/api/trade/order", headers=c.H, json={**good, "side": "Up"}).status_code == 400
    r = c.post("/api/trade/order", headers=c.H, json=good)
    assert r.status_code == 200 and r.json()["results"]["a1"]["ok"] is True
    assert c.adapters["a1"].orders[-1].symbol == NQC
    assert c.post("/api/trade/order", headers=c.H, content=b"x" * 20000).status_code == 413
    assert c.post("/api/trade/order", headers=c.H, content=b"not json").status_code == 400


def test_the_tunneled_hook_app_has_no_trade_routes(desk_client):
    paths = {r.path for r in desk_client.app.state.hook_app.routes if hasattr(r, "path")}
    assert not any(p.startswith("/api/trade") or p == "/api/chart-trading" for p in paths)


# --- the desk page's switch ----------------------------------------------------------------
def test_settings_route_is_same_origin_json_only(desk_client):
    c = desk_client
    assert c.post("/api/chart-trading", content='{"enabled": false}',
                  headers={"content-type": "text/plain"}).status_code == 415
    assert c.post("/api/chart-trading", json={"enabled": False},
                  headers={"origin": "https://evil.example"}).status_code == 403
    r = c.post("/api/chart-trading", json={"enabled": False, "max_position_qty": 8},
               headers={"origin": "http://testserver"})
    assert r.status_code == 200 and r.json()["chart_trading"]["max_position_qty"] == 8
    assert c.get("/api/status").json()["chart_trading"] == \
        {"enabled": False, "max_order_qty": 10, "max_position_qty": 8}
    assert c.post("/api/chart-trading", json={"max_order_qty": 0}).status_code == 400


def test_kill_switches_chart_trading_off(desk_client):
    c = desk_client
    c.post("/api/kill")
    assert c.get("/api/status").json()["chart_trading"]["enabled"] is False
    assert any(e["event"] == "chart_trading_set" and e.get("cause") == "kill"
               for e in journal(c.tmp))
    good = {"client_id": "k", "accounts": ["a1"], "root": "NQ", "side": "Buy", "qty": 1,
            "type": "Market"}
    assert c.post("/api/trade/order", headers=c.H, json=good).json()["results"]["a1"]["error"] \
        == "chart trading is off — switch it on on the desk page"


# --- the SSE stream (the generator directly: an endless response cannot run in TestClient) --
def test_stream_sends_state_first_then_events_in_order_and_heartbeats(tmp_path):
    desk, *_ = mkdesk(tmp_path)

    async def go():
        gen = event_stream(desk, heartbeat_s=0.05)
        first = await gen.__anext__()
        desk.publish("fill", {"n": 1})
        desk.publish("result", {"n": 2})
        second, third = await gen.__anext__(), await gen.__anext__()
        hb = await gen.__anext__()
        await gen.aclose()
        return first, second, third, hb, len(desk._subs)

    first, second, third, hb, subs = run(go())
    assert first.startswith("event: state\ndata: {") and first.endswith("\n\n")
    assert second == 'event: fill\ndata: {"n": 1}\n\n'
    assert third == 'event: result\ndata: {"n": 2}\n\n'
    assert hb.startswith("event: heartbeat\ndata: {")
    assert subs == 0                                        # unsubscribed on close


def test_stream_ends_when_the_reader_was_dropped(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.trading.SUB_QUEUE_MAX", 2)
    desk, *_ = mkdesk(tmp_path)

    async def go():
        gen = event_stream(desk, heartbeat_s=5)
        await gen.__anext__()
        for i in range(4):
            desk.publish("fill", {"i": i})
        with pytest.raises(StopAsyncIteration):
            await gen.__anext__()

    run(go())


def test_the_desk_service_bounds_its_graceful_shutdown():
    """An open SSE stream would hold uvicorn's graceful shutdown forever."""
    p = Path(__file__).resolve().parent.parent / "deploy" / "com.ramosquant.homebase.plist.template"
    args = plistlib.loads(p.read_bytes())["ProgramArguments"]
    i = args.index("--timeout-graceful-shutdown")
    assert args[i + 1] == "5"
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest -q tests/test_desk_api.py`
Expected: FAIL at import (`homebase.desk_api` missing).

- [ ] **Step 3: Implement `homebase/desk_api.py`**

```python
"""Desk-side HTTP for trading from the chart (spec 2026-09-26 desk-on-chart).

/api/trade/* is for the chart service only:
  * every route needs X-Homebase-Key = the hex secret in
    homebase/.state/desk.key (created 0600 at startup); a browser cannot send
    that header cross-origin without a preflight this app never answers;
  * any request carrying an Origin header is refused (403): browsers send
    one, the chart service does not.
POST /api/chart-trading is the desk page's own switch + limits (same-origin
JSON only).
"""
from __future__ import annotations

import asyncio
import hmac
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

KEY_FILE = "desk.key"
BODY_MAX = 16 * 1024
SETTINGS_BODY_MAX = 1024
HEARTBEAT_S = 15.0
LOCAL_HOSTS = ("localhost", "127.0.0.1")
_KEY = re.compile(r"[0-9a-f]{64}")


def ensure_key(path: Path) -> tuple[Optional[str], Optional[str]]:
    """(key, None), creating `path` (32 random bytes as hex, mode 0600) when
    missing; (None, reason) when it cannot be read or holds no key. Never
    raises: the desk must start for the 9:30 bot whatever this file looks
    like — the trade routes then answer 503."""
    try:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        try:
            key = path.read_text().strip()
            os.chmod(path, 0o600)
        except OSError as e:
            return None, f"{path.name} unreadable: {e}"
        if not _KEY.fullmatch(key):
            return None, (f"{path.name} does not hold a desk key — delete it and restart "
                          "the desk to make a new one")
        return key, None
    except OSError as e:
        return None, f"{path.name} could not be created: {e}"
    key = secrets.token_hex(32)
    with os.fdopen(fd, "w") as f:
        f.write(key + "\n")
    return key, None


def sse(event: str, data) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


async def event_stream(desk, *, heartbeat_s: float = HEARTBEAT_S):
    """`state` first, then every published event in order; a heartbeat when
    nothing happened for heartbeat_s. Subscribes BEFORE the snapshot, so
    nothing published in between is lost. Ends if the desk dropped this
    reader (it fell SUB_QUEUE_MAX behind): the client reconnects."""
    q = desk.subscribe()
    try:
        yield sse("state", desk.snapshot())
        while True:
            try:
                event, data = await asyncio.wait_for(q.get(), heartbeat_s)
            except asyncio.TimeoutError:
                yield sse("heartbeat", {"ts": time.time()})
                continue
            if event is None:
                return
            yield sse(event, data)
    finally:
        desk.unsubscribe(q)


async def read_json(request: Request, limit: int):
    cl = request.headers.get("content-length")
    if cl is not None and (not cl.isdigit() or int(cl) > limit):
        raise HTTPException(413, f"request too large ({limit} bytes max)")
    raw = b""
    async for chunk in request.stream():
        raw += chunk
        if len(raw) > limit:
            raise HTTPException(413, f"request too large ({limit} bytes max)")
    try:
        return json.loads(raw or b"null")
    except ValueError:
        raise HTTPException(400, "the body is not JSON") from None


def trade_router(desk) -> APIRouter:
    r = APIRouter()

    def check(request: Request) -> None:
        if request.headers.get("origin") is not None:
            raise HTTPException(403, "browser requests are refused — trade through the chart service")
        key = getattr(request.app.state, "desk_key", None)
        if not key:
            raise HTTPException(503, "the desk key is not available — see desk_key_error in the journal")
        got = request.headers.get("x-homebase-key", "")
        if not hmac.compare_digest(got.encode(), key.encode()):
            raise HTTPException(401, "bad or missing X-Homebase-Key")

    @r.get("/state")
    async def trade_state(request: Request):
        check(request)
        return desk.snapshot()

    @r.get("/stream")
    async def trade_stream(request: Request):
        check(request)
        return StreamingResponse(event_stream(desk), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache"})

    def post(path: str, fn) -> None:
        async def handler(request: Request):
            check(request)
            body = await read_json(request, BODY_MAX)
            try:
                return await fn(body)
            except ValueError as e:
                raise HTTPException(400, str(e)) from None
        r.add_api_route(path, handler, methods=["POST"], name=f"trade_{path.strip('/')}")

    post("/order", desk.order)
    post("/modify", desk.modify)
    post("/cancel", desk.cancel)
    post("/cancel-symbol", desk.cancel_symbol)
    post("/flatten", desk.flatten)
    post("/reverse", desk.reverse)
    return r


def same_origin_json(request: Request) -> None:
    """The desk page's own POSTs: JSON only (a cross-site form cannot send
    it without a preflight), and an Origin, when present, must be this host
    or localhost."""
    ctype = request.headers.get("content-type", "").split(";")[0].strip().lower()
    if ctype != "application/json":
        raise HTTPException(415, "send JSON (Content-Type: application/json)")
    origin = request.headers.get("origin")
    if origin is not None:
        try:
            o = urlsplit(origin).hostname
            h = urlsplit("//" + (request.headers.get("host") or "")).hostname
        except ValueError:
            o = h = None
        if o is None or not (o in LOCAL_HOSTS or o == h):
            raise HTTPException(403, "changes from another site are refused")


def settings_router(desk) -> APIRouter:
    r = APIRouter()

    @r.post("/api/chart-trading")
    async def chart_trading(request: Request):
        same_origin_json(request)
        body = await read_json(request, SETTINGS_BODY_MAX)
        try:
            out = desk.set_settings(body)
        except ValueError as e:
            raise HTTPException(400, str(e)) from None
        return {"ok": True, "chart_trading": out}

    return r
```

- [ ] **Step 4: Wire it into `homebase/server.py` (small insertions only)**

1. Imports. Add `from dataclasses import asdict` with the stdlib imports, and add after `from .timer import SelfTimer`:

```python
from . import desk_api
from .trading import ChartDesk
```

2. After `timer = SelfTimer(cfg, engine, md_factory=_md_factory)`:

```python
    # trading from the chart (spec 2026-09-26): views, guards, journaling
    desk = ChartDesk(cfg, engine, adapters, acct_status, timer_status=timer.status)
```

3. In `_connect_account`, right after `await ad.observe_fills(engine.on_fill)`:

```python
        desk.attach(aid, ad)
```

4. In `lifespan`, make these the first lines of the body, before `tasks = []`:

```python
        _app.state.desk_key, key_err = desk_api.ensure_key(state_dir() / desk_api.KEY_FILE)
        if key_err:
            engine.journal("desk_key_error", error=key_err)
```

   In the `tasks = [...]` list, add `asyncio.create_task(desk.run()),` just before `asyncio.create_task(hook_server.serve())`.

5. After `app.state.feed_box = feed_box`:

```python
    app.state.desk = desk
    app.include_router(desk_api.trade_router(desk), prefix="/api/trade")
    app.include_router(desk_api.settings_router(desk))
```

6. In `status()`'s return dict, after `"armed": cfg.armed,`:

```python
            "chart_trading": asdict(cfg.chart_trading),
```

7. In `kill()`, right after `cfg.armed = False`:

```python
        desk.disable(cause="kill")          # chart trading off too; never raises
```

- [ ] **Step 5: Bound the desk service's graceful shutdown.** In `deploy/com.ramosquant.homebase.plist.template`, after the line `<string>--log-level</string><string>warning</string>` add:

```xml
    <string>--timeout-graceful-shutdown</string><string>5</string>
```

(This takes effect only at the user-approved deploy. Do NOT run `deploy/install.sh`.)

- [ ] **Step 6: Run the new tests and the server tests**

Run: `.venv/bin/python -m pytest -q tests/test_desk_api.py tests/test_server.py tests/test_feed_rules.py`
Expected: all PASS.

- [ ] **Step 7: Full suite, then commit**

Run: `.venv/bin/python -m pytest -q` (expected: all PASS)

```bash
git add homebase/desk_api.py homebase/server.py deploy/com.ramosquant.homebase.plist.template tests/test_desk_api.py
git commit -m "feat(desk): /api/trade (desk key, no Origin, SSE state/account/bot/fill/result + 15 s heartbeat), /api/chart-trading, Kill switches chart trading off" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Prestage skip at 09:28:30 (user-approved)

**Files:**
- Modify: `homebase/engine.py` (skip set plus a filter in `handle_alert`), `homebase/timer.py` (the check at `STAGE_T`), `homebase/server.py` (`compute_readiness`, one block)
- Test: `tests/test_prestage.py`

**Interfaces:**
- Consumes: `FakeAdapter.net`/`net_error` (tests), `config.assignments`.
- Produces:
  - `Engine.skip_today(strategy, account)` and `Engine.skipped_today(strategy) -> set[str]` (in memory, per ET date);
  - the `handle_alert` filter, with the refusal reason `all_accounts_skipped`;
  - `SelfTimer._prestage_skip(name, s, st)` and `timer.PRESTAGE_READ_S = 2.0`;
  - the timer day state gains `skipped_accounts: {account: net}`;
  - journal events `timer_skipped` (reason `manual_position`, `account`, `net`) and `prestage_check_failed`;
  - a readiness check at level `bad` for each skipped account.

- [ ] **Step 1: Write the failing tests** — `tests/test_prestage.py`:

```python
"""The 9:30 bot skips, for the day, any booked account already holding a
position in its symbol at 09:28:30 (user-approved, spec 2026-09-26)."""
from __future__ import annotations

import asyncio
import datetime as dt

from homebase.config import AccountCfg, AppCfg, StrategyCfg
from homebase.engine import Engine
from homebase.server import compute_readiness
from homebase.timer import SelfTimer
from tests.test_engine import Clock, FakeAdapter
from tests.test_timer import FakeMD, _drive_to_fire, events, run

UTC = dt.timezone.utc


class HangingAdapter(FakeAdapter):
    async def get_net_position(self, symbol):
        await asyncio.sleep(10)
        return 0


def mk2(tmp_path, nets, adapter_cls=FakeAdapter):
    """Two-or-more booked accounts; nets: {account: net | "error"}."""
    clock = Clock()
    cfg = AppCfg(armed=False, webhook_secret="s",
                 accounts={a: AccountCfg(keyring_key="k", account_name=a.upper(), label=a.upper())
                           for a in nets},
                 book={"nq930": [{"account": a, "qty": 1} for a in nets]},
                 strategies={"nq930": StrategyCfg(symbol="NQ", qty=1, offset_pts=10.0, sl_pts=5.0,
                                                  tp_pts=15.0, enabled=True, gated=True,
                                                  self_fire=True)})
    adapters = {}
    for a, net in nets.items():
        ad = adapter_cls(a)
        if net == "error":
            ad.net_error = True
        else:
            ad.net = net
        adapters[a] = ad
    engine = Engine(cfg, adapters, now_fn=clock, root=tmp_path)
    md = FakeMD(last_trade=24500.0)
    return SelfTimer(cfg, engine, md_factory=lambda: md, now_fn=clock), engine, clock


def test_prestage_skips_an_account_holding_the_bots_symbol(tmp_path):
    timer, engine, clock = mk2(tmp_path, {"a1": 0, "a2": 2})
    _drive_to_fire(timer, clock)
    st = timer.status()["strategies"]["nq930"]
    assert st["stage"] == "fired" and st["skipped_accounts"] == {"a2": 2}
    ev = events(tmp_path)
    skips = [e for e in ev if e["event"] == "timer_skipped"]
    assert len(skips) == 1
    assert {k: skips[0][k] for k in ("strategy", "reason", "account", "net")} == \
        {"strategy": "nq930", "reason": "manual_position", "account": "a2", "net": 2}
    assert [e["account"] for e in ev if e["event"] == "dry_run"] == ["a1"]
    assert ev.index(skips[0]) < next(i for i, e in enumerate(ev) if e["event"] == "dry_run")


def test_the_check_runs_at_0928_30_not_before(tmp_path):
    timer, engine, clock = mk2(tmp_path, {"a1": 1})
    clock.set_et(9, 21)
    run(timer.tick())
    clock.dt = dt.datetime(2026, 9, 14, 13, 28, 29, tzinfo=UTC)
    run(timer.tick())
    assert not any(e["event"] == "timer_skipped" for e in events(tmp_path))
    clock.dt = dt.datetime(2026, 9, 14, 13, 28, 30, tzinfo=UTC)
    run(timer.tick())
    assert [e["account"] for e in events(tmp_path) if e["event"] == "timer_skipped"] == ["a1"]
    assert engine.skipped_today("nq930") == {"a1"}


def test_all_accounts_skipped_refuses_the_fire(tmp_path):
    timer, engine, clock = mk2(tmp_path, {"a1": -1})
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    assert any(e["event"] == "alert_refused" and e["reason"] == "all_accounts_skipped" for e in ev)
    assert next(e for e in ev if e["event"] == "timer_fired")["result"] is False
    assert not any(e["event"] == "dry_run" for e in ev)


def test_an_unreadable_position_fires_as_before(tmp_path):
    timer, engine, clock = mk2(tmp_path, {"a1": "error", "a2": 0})
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    assert any(e["event"] == "prestage_check_failed" and e.get("account") == "a1" for e in ev)
    assert sorted(e["account"] for e in ev if e["event"] == "dry_run") == ["a1", "a2"]
    assert "skipped_accounts" not in timer.status()["strategies"]["nq930"]


def test_a_hung_position_read_times_out_and_fires_as_before(tmp_path, monkeypatch):
    monkeypatch.setattr("homebase.timer.PRESTAGE_READ_S", 0.05)
    timer, engine, clock = mk2(tmp_path, {"a1": 0, "a2": 0}, adapter_cls=HangingAdapter)
    _drive_to_fire(timer, clock)
    ev = events(tmp_path)
    assert any(e["event"] == "prestage_check_failed" and "account" not in e for e in ev)
    assert timer.status()["strategies"]["nq930"]["stage"] == "fired"
    assert sorted(e["account"] for e in ev if e["event"] == "dry_run") == ["a1", "a2"]


def test_a_skip_turns_readiness_red_for_that_account(tmp_path):
    timer, engine, clock = mk2(tmp_path, {"a1": 0, "a2": 2})
    clock.set_et(9, 21)
    run(timer.tick())
    clock.set_et(9, 29)
    run(timer.tick())
    r = compute_readiness(engine.now_et(), engine.cfg, engine,
                          {"a1": {"connected": True}, "a2": {"connected": True}},
                          timer_status=timer.status())
    assert r["ready"] is False
    assert {"level": "bad", "label": "A2",
            "detail": "nq930 skipped today — holds +2 NQ (manual position at 09:28:30)"} in r["checks"]


def test_skips_are_for_today_only(tmp_path):
    timer, engine, clock = mk2(tmp_path, {"a1": 0})
    engine.skip_today("nq930", "a1")
    assert engine.skipped_today("nq930") == {"a1"}
    clock.dt += dt.timedelta(days=1)
    assert engine.skipped_today("nq930") == set()
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest -q tests/test_prestage.py`
Expected: FAIL (`skip_today` and `skipped_today` missing; no `timer_skipped` event).

- [ ] **Step 3: Engine.** In `homebase/engine.py` `Engine.__init__`, before `self._load_today()`, add:

```python
        # (date, strategy) -> accounts the 9:30 bot skips today: they held a
        # manual position in its symbol at the prestage (timer.STAGE_T)
        self._skips: dict[tuple[str, str], set[str]] = {}
```

Add after `day_status`:

```python
    def skip_today(self, strategy: str, account: str) -> None:
        self._skips.setdefault((self._today(), strategy), set()).add(account)

    def skipped_today(self, strategy: str) -> set[str]:
        return set(self._skips.get((self._today(), strategy), ()))
```

In `handle_alert`, replace:

```python
        asg = assignments(self.cfg, name)
        if not asg:
            self.journal("alert_refused", strategy=name, reason="no_assignments",
```

with:

```python
        asg = assignments(self.cfg, name)
        skipped = self.skipped_today(name)
        if skipped:                              # the prestage skip (timer._prestage_skip)
            asg = [a for a in asg if a["account"] not in skipped]
            if not asg:
                self.journal("alert_refused", strategy=name, reason="all_accounts_skipped",
                             skipped=sorted(skipped), source=source)
                return {"ok": False,
                        "reason": "every booked account holds a manual position — skipped today"}
        if not asg:
            self.journal("alert_refused", strategy=name, reason="no_assignments",
```

(The rest of that `if not asg:` block is unchanged.)

- [ ] **Step 4: Timer.** In `homebase/timer.py`:
- change `from .config import AppCfg` to `from .config import AppCfg, assignments`;
- add `PRESTAGE_READ_S = 2.0   # every booked account's position, read concurrently, at most this long` after `MIN_GATE_BARS`.

In `_advance`, change the stage block to:

```python
        if st["stage"] == "gated" and t >= STAGE_T:
            md = await self._ensure_md()
            if s.symbol not in self._subs:
                self._subs[s.symbol] = await md.subscribe_quote(s.symbol)
            await self._prestage_skip(name, s, st)
            st["stage"] = "staged"
```

Add this method after `_advance`:

```python
    async def _prestage_skip(self, name, s, st) -> None:
        """User-approved (spec 2026-09-26): a booked account that already holds
        a position in this strategy's symbol at the prestage is skipped for
        the day. Otherwise the bot would net against those contracts at its
        12:55/15:55 flatten and could misattribute their fills. Positions
        are the broker's (get_net_position), read concurrently, at most
        PRESTAGE_READ_S in total. Unreadable -> the account fires as before
        (journaled). Never raises: the stage must not fail on this check."""
        async def read(aid):
            ad = self.engine.adapters.get(aid)
            if ad is None or not ad.connected:
                return aid, None, "not connected"
            try:
                return aid, await ad.get_net_position(s.symbol), None
            except Exception as e:  # noqa: BLE001
                return aid, None, str(e)[:120] or type(e).__name__

        try:
            got = await asyncio.wait_for(
                asyncio.gather(*(read(a["account"]) for a in assignments(self.cfg, name))),
                PRESTAGE_READ_S)
        except Exception as e:  # noqa: BLE001 — incl. the timeout: fire as before
            self.engine.journal("prestage_check_failed", strategy=name,
                                error=str(e)[:200] or type(e).__name__)
            return
        skipped = {}
        for aid, net, err in got:
            if err is not None:
                self.engine.journal("prestage_check_failed", strategy=name, account=aid, error=err)
            elif net:
                skipped[aid] = int(net)
                self.engine.skip_today(name, aid)
                self.engine.journal("timer_skipped", strategy=name, reason="manual_position",
                                    account=aid, net=int(net))
        if skipped:
            st["skipped_accounts"] = skipped
```

- [ ] **Step 5: Readiness.** In `homebase/server.py` `compute_readiness`, add this right after the `if timer_status is not None and weekday and dt.time(9, 21) <= …:` block ends (before `bars = [...]`):

```python
    for name, tst in ((timer_status or {}).get("strategies") or {}).items():
        sym = getattr(cfg.strategies.get(name), "symbol", "?")
        for aid, net in (tst.get("skipped_accounts") or {}).items():
            a = cfg.accounts.get(aid)
            checks.append({"level": "bad",
                           "label": (a.label or a.account_name or aid) if a else aid,
                           "detail": f"{name} skipped today — holds {int(net):+d} {sym} "
                                     "(manual position at 09:28:30)"})
```

- [ ] **Step 6: Run the prestage, timer, engine and server tests**

Run: `.venv/bin/python -m pytest -q tests/test_prestage.py tests/test_timer.py tests/test_engine.py tests/test_server.py`
Expected: all PASS. Every existing timer test is unchanged, because a flat account never skips.

- [ ] **Step 7: Full suite, then commit**

Run: `.venv/bin/python -m pytest -q` (expected: all PASS)

```bash
git add homebase/engine.py homebase/timer.py homebase/server.py tests/test_prestage.py
git commit -m "feat(timer): at 09:28:30 a booked account holding the bot's symbol is skipped for the day (timer_skipped manual_position, readiness red); nothing else in the 9:30 path changes" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Desk page — the "Chart trading" switch and limits

**Files:**
- Modify: `homebase/static/index.html`
- Test: `tests/test_desk_page.py`

**Interfaces:**
- Consumes: `GET /api/status` → `chart_trading`; `POST /api/chart-trading` (Task 5); the page's own `post()`, `confirmDlg()`, `toast()` and `refresh()`.
- Produces: element ids `ctSwitch`, `ctState`, `ctMaxOrder`, `ctMaxPos`, `ctSave`; JS `renderChartTrading(ct)`, `setChartTrading(enabled)`.

- [ ] **Step 1: Write the failing test** — `tests/test_desk_page.py`:

```python
"""The desk page carries the chart-trading switch + limits, and switching
it ON goes through the confirm dialog before the POST."""
from __future__ import annotations

from pathlib import Path

HTML = (Path(__file__).resolve().parent.parent / "homebase" / "static" / "index.html").read_text()


def test_the_desk_page_has_the_chart_trading_switch_and_limits():
    for needle in ('id="ctSwitch"', 'id="ctState"', 'id="ctMaxOrder"', 'id="ctMaxPos"',
                   'id="ctSave"', 'post("/api/chart-trading"', "renderChartTrading(s.chart_trading)"):
        assert needle in HTML, needle


def test_switching_on_asks_first():
    fn = HTML[HTML.index("async function setChartTrading"):]
    fn = fn[:fn.index("\n}\n")]
    assert fn.index("confirmDlg(") < fn.index('post("/api/chart-trading"')


def test_the_preview_data_carries_chart_trading():
    demo = HTML[HTML.index("function demoStatus()"):]
    assert "chart_trading: {enabled: false, max_order_qty: 10, max_position_qty: 20}" in demo
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest -q tests/test_desk_page.py`
Expected: FAIL.

- [ ] **Step 3: Add the card.** In `homebase/static/index.html`, insert right after `<div id="strats"></div>`:

```html
      <div class="sec-head" style="margin-top:26px">
        <span class="h">Chart trading</span>
        <span class="hint">orders from the chart page — off by default; the Kill switches it off</span>
      </div>
      <div class="card"><div class="card-content" style="padding-top:14px">
        <div class="acct" style="padding:4px 0;gap:12px;flex-wrap:wrap">
          <button class="switch" id="ctSwitch" aria-checked="false"
            title="OFF — the chart page cannot trade"></button>
          <span class="nm" id="ctState" style="font-size:13px">Off</span>
          <span class="spacer"></span>
          <label class="hint" for="ctMaxOrder">Max per order</label>
          <input id="ctMaxOrder" type="number" min="1" max="50" step="1"
            style="width:64px;padding:5px 8px;border:1px solid var(--input);border-radius:var(--radius-md);background:var(--background);color:var(--foreground)">
          <label class="hint" for="ctMaxPos">Max position</label>
          <input id="ctMaxPos" type="number" min="1" max="100" step="1"
            style="width:64px;padding:5px 8px;border:1px solid var(--input);border-radius:var(--radius-md);background:var(--background);color:var(--foreground)">
          <button class="btn btn-outline btn-sm" id="ctSave">Save limits</button>
        </div>
      </div></div>
```

- [ ] **Step 4: Add the JS.**
- In `render()`, right after the line `$("#disarmBtn").style.display = s.armed ? "" : "none";`, add `  renderChartTrading(s.chart_trading);`.
- In `demoStatus()`'s returned object, right after `armed: true,`, add `    chart_trading: {enabled: false, max_order_qty: 10, max_position_qty: 20},`.
- Add this block right after the `$("#killBtn").onclick = …;` handler:

```js
/* ---- chart trading (orders from the chart page; the desk decides) ---- */
function renderChartTrading(ct) {
  if (!ct) return;
  const sw = $("#ctSwitch");
  sw.setAttribute("aria-checked", String(!!ct.enabled));
  sw.title = ct.enabled ? "ON — the chart page can place real orders"
                        : "OFF — the chart page cannot trade";
  $("#ctState").textContent = ct.enabled ? "On — the chart page can place orders" : "Off";
  for (const [id, v] of [["ctMaxOrder", ct.max_order_qty], ["ctMaxPos", ct.max_position_qty]]) {
    const el = $("#" + id);
    if (document.activeElement !== el) el.value = v;       // never overwrite a value being typed
  }
}
async function setChartTrading(enabled) {
  const ct = (ST && ST.chart_trading) || {};
  if (enabled && !await confirmDlg("Turn chart trading ON?",
      `The chart page can then place REAL orders on the accounts you tick there — at most ${ct.max_order_qty} per order and ${ct.max_position_qty} per position. The 9:30 bot's symbol stays locked 09:20–09:35 ET on its accounts. The desk's Kill switches it off.`,
      "Turn on", false)) { refresh(); return; }
  const r = await post("/api/chart-trading", {enabled});
  toast(r.ok ? (enabled ? "Chart trading is ON." : "Chart trading is OFF.")
             : "Refused — " + (r.detail || "unknown"), 5000);
  refresh();
}
$("#ctSwitch").onclick = () =>
  setChartTrading(!(ST && ST.chart_trading && ST.chart_trading.enabled));
$("#ctSave").onclick = async () => {
  const body = {max_order_qty: parseInt($("#ctMaxOrder").value, 10),
                max_position_qty: parseInt($("#ctMaxPos").value, 10)};
  const r = await post("/api/chart-trading", body);
  toast(r.ok ? `Limits saved — ${body.max_order_qty} per order, ${body.max_position_qty} per position.`
             : "Refused — " + (r.detail || "unknown"), 5000);
  refresh();
};
```

- [ ] **Step 5: Run the page test**

Run: `.venv/bin/python -m pytest -q tests/test_desk_page.py`
Expected: PASS.

- [ ] **Step 6 (optional visual check; no desk code runs).** Start a plain static server as a background job: `.venv/bin/python -m http.server 8898 --bind 127.0.0.1 --directory homebase`. Open `http://127.0.0.1:8898/static/index.html?demo=1` in the Browser pane.
- Check that the "Chart trading" card renders under the strategies with the switch and both inputs, in light and dark themes, and at phone width.
- Clicking the switch in preview only toasts "Preview mode".
- Stop the server afterwards.
- Do NOT start the desk (`homebase.server`): its module-level app would connect to brokers.

- [ ] **Step 7: Full suite, then commit**

Run: `.venv/bin/python -m pytest -q` (expected: all PASS)

```bash
git add homebase/static/index.html tests/test_desk_page.py
git commit -m "feat(desk-page): Chart trading switch (confirm to turn on) and the per-order / per-position limits" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Chart service `homebase/charts/desk.py`: SSE client, quotes, proxy

**Files:**
- Create: `homebase/charts/desk.py`
- Test: `tests/test_charts_desk.py`

**Interfaces:**
- Consumes: the desk's `/api/trade/stream` and `/api/trade/<action>` (Task 5); `browser_write_ok(request)` from `homebase/charts/server.py` (existing).
- Produces:
  - constants `DESK_URL`, `ACTIONS`, `BODY_MAX=4096`, `BACKOFF_S=(1, 2, 4, 8, 16, 30)`, `NO_LINK`; exception `DeskDown`;
  - `SSEParser.feed(line) -> (event, data)|None`;
  - `Quotes.note(root, rows)`, `.snapshot() -> {root: {bid, ask, last, ts_ms}}`, `.drain() -> [{"type": "quote", "root", "bid", "ask", "last", "ts_ms", "asof": "last_trade"}]`;
  - `DeskLink(fanout, *, key_path, url=DESK_URL, transport=None, sleep=asyncio.sleep)` with `.key()`, `.hello() -> dict`, `.on_event(event, raw)`, `async .run()`, `.stop()`, `async .post(action, body) -> (status, dict)`;
  - `register(app, *, link, quotes, browser_write_ok)`.

- [ ] **Step 1: Verify the md budget question BEFORE writing code (ruling 2)**

Run:
```bash
grep -n "count_request\|md/getChart" homebase/charts/tickfeed.py
grep -n "180\|p-ticket\|LIVE login\|demo login" homebase/ticks.py | head -20
grep -rn "subscribeQuote" homebase
grep -n "def md_source" -A15 homebase/server.py
```
Expected:
- `count_request` wraps only `md/getChart`.
- `ticks.py` documents the 180 requests/hour penalty on `getChart`.
- `subscribeQuote` appears only in `homebase/marketdata.py`, the desk timer's 09:28:30 anchor quote.
- `md_source` prefers the demo login, the same login whose md token the chart feed reads (`MD_ENV = "demo"`).

Conclusion to record in the commit message: nothing in the repo shows quote subscriptions are exempt from the budget of the login the 9:30 anchor depends on. So bid/ask come from the ticks (`"asof": "last_trade"`), and `md/subscribeQuote` is not added. **If any grep shows something else** (e.g., a documented exemption or a second md login), STOP and report to the controller before writing code.

- [ ] **Step 2: Write the failing tests** — `tests/test_charts_desk.py`:

```python
"""The chart service's desk link: SSE parsing, fan-out, backoff, the key,
the proxy's POST, and quotes from the ticks. No network: every DeskLink
gets an httpx.MockTransport; the real desk is never reached."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import httpx

import homebase.charts
from homebase.charts.desk import DeskLink, Quotes, SSEParser


def run(coro):
    return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)


KEY = "ab" * 32
STATE = ["event: state", 'data: {"enabled": true, "accounts": [{"id": "a1", "n": 0}], "bot": {}}', ""]
ACCT = ["event: account", 'data: {"id": "a1", "n": 1}', ""]
BEAT = ["event: heartbeat", 'data: {"ts": 1}', ""]


def key_file(tmp_path, key=KEY):
    p = tmp_path / "desk.key"
    if key is not None:
        p.write_text(key + "\n")
    return p


def mklink(tmp_path, script, key=KEY):
    """script: one item per stream attempt — an exception to raise, or
    (status, lines). The link stops itself once the script is used up."""
    fanned, seen, slept = [], [], []

    def handler(request):
        seen.append(request)
        item = script.pop(0)
        if isinstance(item, Exception):
            raise item
        status, lines = item
        return httpx.Response(status, content=("\n".join(lines) + "\n").encode(),
                              headers={"content-type": "text/event-stream"})

    async def sleep(s):
        slept.append(s)
        if not script:
            link.stop()

    link = DeskLink(fanned.append, key_path=key_file(tmp_path, key),
                    transport=httpx.MockTransport(handler), sleep=sleep)
    return link, fanned, seen, slept


def test_sse_parser():
    p = SSEParser()
    lines = ["event: state", 'data: {"a":', "data: 1}", "", ": a comment", "data: x", "", ""]
    assert [p.feed(x) for x in lines] == \
        [None, None, None, ("state", '{"a":\n1}'), None, None, ("message", "x"), None]


def test_link_fans_out_events_with_the_key_and_says_when_the_desk_goes(tmp_path):
    link, fanned, seen, slept = mklink(tmp_path, [(200, STATE + ACCT + BEAT)])
    run(link.run())
    assert str(seen[0].url) == "http://127.0.0.1:8850/api/trade/stream"
    assert seen[0].headers["x-homebase-key"] == KEY and "origin" not in seen[0].headers
    assert fanned == [
        {"type": "desk", "event": "state",
         "data": {"enabled": True, "accounts": [{"id": "a1", "n": 0}], "bot": {}}},
        {"type": "desk", "event": "account", "data": {"id": "a1", "n": 1}},
        {"type": "desk", "down": "the desk closed the stream"},        # heartbeats never fan out
    ]
    assert link.hello() == {"type": "desk", "down": "the desk closed the stream"}


def test_hello_is_the_latest_state_or_the_down_reason(tmp_path):
    link, *_ = mklink(tmp_path, [])
    assert link.hello() == {"type": "desk", "down": "connecting to the desk"}
    link.on_event("account", '{"id": "a1", "n": 9}')              # before any state: ignored
    link.on_event("state", '{"accounts": [{"id": "a1", "n": 0}], "bot": {"x": 0}}')
    link.on_event("account", '{"id": "a1", "n": 1}')
    link.on_event("account", '{"id": "a2", "n": 5}')
    link.on_event("bot", '{"x": 1}')
    link.on_event("fill", "not json")                             # ignored
    assert link.hello() == {"type": "desk", "event": "state", "data": {
        "accounts": [{"id": "a1", "n": 1}, {"id": "a2", "n": 5}], "bot": {"x": 1}}}


def test_link_backs_off_1_to_30_s_and_resets_after_a_state(tmp_path):
    refused = httpx.ConnectError("refused")
    link, fanned, seen, slept = mklink(tmp_path, [refused] * 7 + [(200, STATE)] + [refused])
    run(link.run())
    assert slept == [1, 2, 4, 8, 16, 30, 30, 1, 2]
    assert [m["down"] for m in fanned if "down" in m] == [
        "desk unreachable: ConnectError: refused",       # announced once, not per retry
        "the desk closed the stream",
        "desk unreachable: ConnectError: refused"]


def test_a_refused_stream_and_a_missing_key_are_down_with_the_reason(tmp_path):
    link, fanned, seen, _ = mklink(tmp_path, [(401, [])])
    run(link.run())
    assert fanned == [{"type": "desk", "down": "desk refused the stream: HTTP 401"}]
    link, fanned, seen, _ = mklink(tmp_path / "nokey", [], key=None)    # no key file at all
    run(link.run())
    assert seen == [] and fanned == [{"type": "desk", "down":
                                      "desk key missing — start the desk (it creates homebase/.state/desk.key)"}]


def test_post_adds_the_key_and_maps_failures(tmp_path):
    seen = []

    def handler(req):
        seen.append(req)
        if req.url.path == "/api/trade/order":
            return httpx.Response(200, json={"results": {"a1": {"ok": True}}})
        if req.url.path == "/api/trade/flatten":
            raise httpx.ReadTimeout("slow")
        raise httpx.ConnectError("refused")

    link = DeskLink(lambda m: None, key_path=key_file(tmp_path),
                    transport=httpx.MockTransport(handler))
    assert run(link.post("order", {"client_id": "c"})) == (200, {"results": {"a1": {"ok": True}}})
    assert seen[0].headers["x-homebase-key"] == KEY and "origin" not in seen[0].headers
    assert json.loads(seen[0].content) == {"client_id": "c"}
    status, body = run(link.post("flatten", {}))
    assert status == 504 and "check the Orders tab" in body["detail"]
    assert run(link.post("cancel", {})) == (502, {"detail": "desk unreachable: ConnectError"})
    nokey = DeskLink(lambda m: None, key_path=tmp_path / "missing.key")
    assert run(nokey.post("order", {}))[0] == 503


def test_quotes_keep_the_last_sane_bid_ask_and_drain_changes_once():
    q = Quotes()
    q.note("NQ", [{"ts_ms": 1, "price": 100.0, "bid": 99.75, "ask": 100.0},
                  {"ts_ms": 2, "price": 100.25, "bid": "", "ask": ""}])
    assert q.snapshot() == {"NQ": {"bid": 99.75, "ask": 100.0, "last": 100.25, "ts_ms": 2}}
    q.note("NQ", [{"ts_ms": 3, "price": 100.5, "bid": 100.75, "ask": 100.5}])   # crossed: kept
    assert q.drain() == [{"type": "quote", "root": "NQ", "bid": 99.75, "ask": 100.0,
                          "last": 100.5, "ts_ms": 3, "asof": "last_trade"}]
    assert q.drain() == []
    q.note("ES", [])
    assert "ES" not in q.snapshot()


def test_the_chart_service_never_subscribes_quotes():
    """Ruling 2026-09-26: bid/ask come from the ticks. An md quote
    subscription could spend the budget of the login the 9:30 anchor uses."""
    pkg = Path(homebase.charts.__file__).parent
    assert not any("md/subscribeQuote" in p.read_text() for p in pkg.glob("*.py"))
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/bin/python -m pytest -q tests/test_charts_desk.py`
Expected: FAIL at import.

- [ ] **Step 4: Implement `homebase/charts/desk.py`**

```python
"""The chart service's link to the desk (spec 2026-09-26 desk-on-chart).

Only the desk (:8850) talks to the broker's order API. This module:
  * DeskLink: one SSE connection to the desk's /api/trade/stream (key from
    homebase/.state/desk.key), reconnecting 1 s -> 30 s. Each event goes to
    every page over the existing /ws as {"type": "desk", "event": <state|
    account|bot|fill|result>, "data": ...}; while the desk is unreachable:
    {"type": "desk", "down": "<reason>"} and the page disables trading.
    (The spec writes {"t": "desk"}; every /ws message is keyed on "type".)
  * register(): POST /api/desk/{order|modify|cancel|cancel-symbol|flatten|
    reverse} -> the desk's /api/trade/*, after the page-origin check, with
    the body capped at 4 KB, the key added, and `quotes` (this service's
    latest quote per root) attached for the desk's stop-side check.
  * Quotes: bid/ask for the Buy/Sell buttons, "as of last trade": every tick
    the md feed delivers carries the quote at that trade. Decided
    2026-09-26: no md quote subscription — nothing in the repo shows one is
    exempt from the 180 requests/hour md budget, and that budget belongs to
    the login whose feed the 9:30 bot anchors on.
"""
from __future__ import annotations

import asyncio
import copy
import json
import math
import re
from pathlib import Path
from typing import AsyncIterator, Callable, Optional

import httpx
from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

DESK_URL = "http://127.0.0.1:8850"
ACTIONS = ("order", "modify", "cancel", "cancel-symbol", "flatten", "reverse")
BODY_MAX = 4096
BACKOFF_S = (1, 2, 4, 8, 16, 30)
READ_TIMEOUT_S = 45.0          # three missed 15 s heartbeats = the desk is gone
POST_TIMEOUT_S = 20.0
NO_LINK = "chart trading is not available here (replay, or started without the desk link)"
_KEY = re.compile(r"[0-9a-f]{64}")


class DeskDown(Exception):
    """The desk cannot be reached or refused us; str(e) is shown to the page."""


def _f(v) -> Optional[float]:
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


class SSEParser:
    """text/event-stream, line by line: `event:` and `data:` fields, a blank
    line ends one event, `:` lines are comments; data lines join with \\n."""

    def __init__(self):
        self._event, self._data = "message", []

    def feed(self, line: str):
        if line == "":
            if not self._data:
                self._event = "message"
                return None
            out = (self._event, "\n".join(self._data))
            self._event, self._data = "message", []
            return out
        if line.startswith(":"):
            return None
        field, _, value = line.partition(":")
        if value.startswith(" "):
            value = value[1:]
        if field == "event":
            self._event = value
        elif field == "data":
            self._data.append(value)
        return None


class Quotes:
    """Last bid/ask/trade per root, from the tick rows (the quote AT each
    trade). A crossed or missing quote keeps the previous bid/ask."""

    def __init__(self):
        self._q: dict[str, dict] = {}
        self._dirty: set[str] = set()

    def note(self, root: str, rows: list) -> None:
        if not rows:
            return
        q = dict(self._q.get(root) or {"bid": None, "ask": None})
        for r in rows:
            bid, ask = _f(r.get("bid")), _f(r.get("ask"))
            if bid is not None and ask is not None and bid <= ask:
                q["bid"], q["ask"] = bid, ask
            q["last"], q["ts_ms"] = float(r["price"]), int(r["ts_ms"])
        self._q[root] = q
        self._dirty.add(root)

    def snapshot(self) -> dict:
        return {r: dict(q) for r, q in self._q.items()}

    def drain(self) -> list[dict]:
        out = [{"type": "quote", "root": r, **self._q[r], "asof": "last_trade"}
               for r in sorted(self._dirty)]
        self._dirty.clear()
        return out


class DeskLink:
    def __init__(self, fanout: Callable[[dict], None], *, key_path, url: str = DESK_URL,
                 transport: Optional[httpx.AsyncBaseTransport] = None, sleep=asyncio.sleep):
        self.fanout = fanout                  # (msg) -> None: sends to every page
        self.key_path = Path(key_path)
        self.url = url
        self._transport = transport
        self._sleep = sleep
        self.state: Optional[dict] = None
        self.down: Optional[str] = "connecting to the desk"
        self._stop = False

    def key(self) -> str:
        try:
            k = self.key_path.read_text().strip()
        except OSError:
            raise DeskDown("desk key missing — start the desk "
                           "(it creates homebase/.state/desk.key)") from None
        if not _KEY.fullmatch(k):
            raise DeskDown("desk key unreadable")
        return k

    def _client(self, timeout) -> httpx.AsyncClient:
        # trust_env=False: a proxy from the environment must never carry the key
        return httpx.AsyncClient(timeout=timeout, transport=self._transport, trust_env=False)

    def hello(self) -> dict:
        """What a page gets when it connects (a copy: later events must not
        change a message already queued to a page)."""
        if self.down is not None or self.state is None:
            return {"type": "desk", "down": self.down or "connecting to the desk"}
        return {"type": "desk", "event": "state", "data": copy.deepcopy(self.state)}

    def _apply(self, event: str, data) -> None:
        if event == "state":
            self.state = copy.deepcopy(data)      # the fanned-out `data` is never mutated
        elif event == "account" and isinstance(data, dict) and self.state is not None:
            accts = self.state.setdefault("accounts", [])
            for i, a in enumerate(accts):
                if a.get("id") == data.get("id"):
                    accts[i] = data
                    break
            else:
                accts.append(data)
        elif event == "bot" and self.state is not None:
            self.state["bot"] = data
        # fill / result: passed through, nothing cached

    def on_event(self, event: str, raw: str) -> None:
        if event == "heartbeat":
            return
        try:
            data = json.loads(raw)
        except ValueError:
            return
        if event == "state":
            self.down = None
        elif self.down is not None:
            return                                   # nothing to build on before a state
        self._apply(event, data)
        self.fanout({"type": "desk", "event": event, "data": data})

    def _set_down(self, reason: str) -> None:
        self.state = None
        if reason != self.down:                      # announced once per change, not per retry
            self.down = reason
            self.fanout({"type": "desk", "down": reason})

    async def _lines(self, key: str) -> AsyncIterator[str]:
        async with self._client(httpx.Timeout(10.0, read=READ_TIMEOUT_S)) as c:
            async with c.stream("GET", f"{self.url}/api/trade/stream",
                                headers={"X-Homebase-Key": key}) as r:
                if r.status_code != 200:
                    raise DeskDown(f"desk refused the stream: HTTP {r.status_code}")
                async for line in r.aiter_lines():
                    yield line

    async def run(self) -> None:
        attempt = 0
        while not self._stop:
            try:
                key = self.key()
                parser = SSEParser()
                async for line in self._lines(key):
                    got = parser.feed(line)
                    if got is not None:
                        self.on_event(*got)
                        if got[0] == "state":
                            attempt = 0
                reason = "the desk closed the stream"
            except DeskDown as e:
                reason = str(e)
            except Exception as e:  # noqa: BLE001 — any failure: down, then retry with backoff
                reason = f"desk unreachable: {type(e).__name__}: {e}"[:200]
            if self._stop:
                break
            self._set_down(reason)
            await self._sleep(BACKOFF_S[min(attempt, len(BACKOFF_S) - 1)])
            attempt += 1

    def stop(self) -> None:
        self._stop = True

    async def post(self, action: str, body: dict) -> tuple[int, dict]:
        try:
            key = self.key()
        except DeskDown as e:
            return 503, {"detail": str(e)}
        try:
            async with self._client(POST_TIMEOUT_S) as c:
                r = await c.post(f"{self.url}/api/trade/{action}", json=body,
                                 headers={"X-Homebase-Key": key})
        except httpx.TimeoutException:
            return 504, {"detail": f"no answer from the desk in {POST_TIMEOUT_S:.0f} s — "
                                   "check the Orders tab before trying again"}
        except Exception as e:  # noqa: BLE001
            return 502, {"detail": f"desk unreachable: {type(e).__name__}"}
        try:
            data = r.json()
        except ValueError:
            data = {"detail": r.text[:200]}
        return r.status_code, data if isinstance(data, dict) else {"detail": data}


def register(app, *, link: Optional[DeskLink], quotes: Quotes, browser_write_ok) -> None:
    """POST /api/desk/{action}: the page's trading requests, relayed to the desk."""

    @app.post("/api/desk/{action}")
    async def desk_proxy(action: str, request: Request):
        browser_write_ok(request)
        if action not in ACTIONS:
            raise HTTPException(404, f"unknown desk action {action!r}")
        if link is None:
            raise HTTPException(503, NO_LINK)
        cl = request.headers.get("content-length")
        if cl is not None and (not cl.isdigit() or int(cl) > BODY_MAX):
            raise HTTPException(413, "request too large (4 KB max)")
        raw = b""
        async for chunk in request.stream():
            raw += chunk
            if len(raw) > BODY_MAX:
                raise HTTPException(413, "request too large (4 KB max)")
        try:
            body = json.loads(raw)
        except ValueError:
            raise HTTPException(400, "the body is not JSON") from None
        if not isinstance(body, dict):
            raise HTTPException(400, "the body is a JSON object")
        body["quotes"] = quotes.snapshot()          # ours, never the page's
        status, data = await link.post(action, body)
        return JSONResponse(data, status_code=status)
```

- [ ] **Step 5: Run the tests**

Run: `.venv/bin/python -m pytest -q tests/test_charts_desk.py`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add homebase/charts/desk.py tests/test_charts_desk.py
git commit -m "feat(charts): desk link (SSE 1-30 s backoff, fan-out, down state), trading proxy with the desk key, bid/ask from the ticks - no md quote subscription: nothing shows it is exempt from the 180/h budget the 9:30 anchor login depends on" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Wire the desk link into the chart service; final verification

**Files:**
- Modify: `homebase/charts/server.py` (small insertions only), `homebase/charts/__main__.py`, `homebase/charts/__init__.py` (docstring line)
- Test: `tests/test_charts_desk_server.py`

**Interfaces:**
- Consumes: `Quotes`, `DeskLink`, `register`, `NO_LINK` (Task 8).
- Produces:
  - `create_app(..., desk_factory=None)`, where `desk_factory(fanout) -> DeskLink`; it is ignored in replay;
  - a page receives `{"type": "desk", …}` right after its first `status`;
  - `{"type": "quote", …}` messages at most 4 a second per root;
  - `POST /api/desk/{action}`.

- [ ] **Step 1: Write the failing tests** — `tests/test_charts_desk_server.py`:

```python
"""The chart service with the desk link wired in: hello, fan-out, quotes
from the ticks, the proxy. The real desk is never reached (MockTransport)."""
from __future__ import annotations

import asyncio
import json
import queue

import httpx
from fastapi.testclient import TestClient

from homebase.charts.desk import NO_LINK, DeskLink
from homebase.charts.server import create_app
from tests.charts_util import D, rows, session_ms
from tests.test_charts_server import archive, next_of

KEY = "cd" * 32


class QuietFeed:
    """A live feed that delivers only what the test queues. No network."""
    last = None

    def __init__(self, roots, on_ticks, on_subscribed=None):
        self.on_ticks, self.ws, self.q = on_ticks, None, queue.Queue()
        QuietFeed.last = self

    async def run(self):
        while True:
            try:
                self.on_ticks(*self.q.get_nowait())
            except queue.Empty:
                await asyncio.sleep(0.01)

    def stop(self):
        pass

    def budget_used(self):
        return 0

    def count_request(self):
        pass

    def status(self):
        return {"mode": "live", "connected": True, "error": None, "roots": {},
                "budget_hour": 0, "reconnects": 0}


def live_app(tmp_path, **kw):
    return create_app(roots=["NQ"], base=tmp_path / "ticks", feed_factory=QuietFeed,
                      now_ms=lambda: session_ms(D, 9, 45), state=tmp_path / "state", **kw)


def key_file(tmp_path):
    p = tmp_path / "desk.key"
    p.write_text(KEY)
    return p


def test_without_a_desk_link_the_page_is_told_and_the_proxy_answers_503(tmp_path):
    with TestClient(live_app(tmp_path)) as c:
        with c.websocket_connect("/ws") as ws:
            assert ws.receive_json()["type"] == "status"
            assert ws.receive_json() == {"type": "desk", "down": NO_LINK}
        assert c.post("/api/desk/order", json={}).status_code == 503


def test_replay_never_links_to_the_desk(tmp_path):
    called = []
    app = create_app(roots=["NQ"], base=archive(tmp_path), replay=D, speed=50,
                     state=tmp_path / "state", desk_factory=lambda fan: called.append(1))
    with TestClient(app) as c:
        assert c.post("/api/desk/order", json={}).status_code == 503
    assert called == []


def test_desk_state_fans_out_to_the_page(tmp_path):
    async def body():
        yield b'event: state\ndata: {"enabled": true, "accounts": [], "bot": {}}\n\n'
        await asyncio.Event().wait()                     # the stream stays open

    def handler(req):
        return httpx.Response(200, content=body(), headers={"content-type": "text/event-stream"})

    kp = key_file(tmp_path)
    app = live_app(tmp_path, desk_factory=lambda fan: DeskLink(
        fan, key_path=kp, transport=httpx.MockTransport(handler)))
    with TestClient(app) as c, c.websocket_connect("/ws") as ws:
        for _ in range(400):
            m = ws.receive_json()
            if m.get("type") == "desk" and m.get("event") == "state":
                break
        else:
            raise AssertionError("no desk state reached the page")
    assert m["data"]["enabled"] is True


def test_quotes_reach_the_page_as_of_the_last_trade(tmp_path):
    with TestClient(live_app(tmp_path)) as c, c.websocket_connect("/ws") as ws:
        QuietFeed.last.q.put(("NQ", "NQZ6", rows(session_ms(D, 9, 40), [100.0, 100.25])))
        m = next_of(ws, "quote", limit=400)
    assert m == {"type": "quote", "root": "NQ", "bid": 100.0, "ask": 100.25, "last": 100.25,
                 "ts_ms": session_ms(D, 9, 40) + 1000, "asof": "last_trade"}


def test_proxy_checks_origin_size_and_forwards_with_our_quotes(tmp_path):
    posted = []

    def handler(req):
        if req.method == "GET":
            return httpx.Response(200, content=b'event: state\ndata: {"accounts": [], "bot": {}}\n\n',
                                  headers={"content-type": "text/event-stream"})
        posted.append((req.url.path, req.headers.get("x-homebase-key"), json.loads(req.content)))
        return httpx.Response(200, json={"results": {}})

    kp = key_file(tmp_path)
    app = live_app(tmp_path, desk_factory=lambda fan: DeskLink(
        fan, key_path=kp, transport=httpx.MockTransport(handler)))
    with TestClient(app) as c:
        assert c.post("/api/desk/order", json={"x": 1},
                      headers={"origin": "https://evil.example"}).status_code == 403
        assert c.post("/api/desk/bogus", json={}).status_code == 404
        assert c.post("/api/desk/order", content=b"{" + b" " * 5000 + b"}").status_code == 413
        assert c.post("/api/desk/order", content=b"[1]").status_code == 400
        r = c.post("/api/desk/order", json={"client_id": "c", "quotes": {"NQ": {"last": 1}}},
                   headers={"origin": "http://localhost:8852"})
        assert r.status_code == 200 and r.json() == {"results": {}}
    path, key, body = posted[-1]
    assert (path, key) == ("/api/trade/order", KEY)
    assert body == {"client_id": "c", "quotes": {}}           # the page's own quotes are replaced
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/bin/python -m pytest -q tests/test_charts_desk_server.py`
Expected: FAIL (`desk_factory` is not a `create_app` parameter; no `/api/desk` route).

- [ ] **Step 3: Wire `homebase/charts/server.py` (insertions only)**

1. Import, after `from .tickfeed import TickFeed`:

```python
from .desk import NO_LINK, Quotes, register as register_desk
```

2. `create_app` signature: add `desk_factory=None` after `state: Path | None = None`.

3. Right after `conns: set[Conn] = set()`:

```python
    quotes = Quotes()                     # bid/ask per root for the Buy/Sell buttons (desk.py)

    def fan(msg: dict) -> None:
        for c in list(conns):
            c.send(msg)

    # the desk link: never in replay (a replayed price must never reach an order)
    link = desk_factory(fan) if (desk_factory is not None and not replay) else None
```

4. In `on_live`, right after the line `rows = [r for r in rows if session_date(int(r["ts_ms"]), root) >= today]`:

```python
            quotes.note(root, rows)
```

5. In `pump()`, inside the `try:` that drains the hub, right after the `for (conn, cid), msg in hub.drain(): …` loop:

```python
                for m in quotes.drain():
                    fan(m)
```

6. In `lifespan`, right after `tasks = [asyncio.create_task(pump()), asyncio.create_task(feed.run())]`:

```python
        if link is not None:
            tasks.append(asyncio.create_task(link.run()))
```

   In its `finally:`, right after `feed.stop()`:

```python
            if link is not None:
                link.stop()
```

7. Right after the `known_root` function definition:

```python
    register_desk(app, link=link, quotes=quotes, browser_write_ok=browser_write_ok)
```

8. In `ws_endpoint`, right after `conn.send({"type": "status", **status()})`:

```python
        conn.send(link.hello() if link is not None else {"type": "desk", "down": NO_LINK})
```

- [ ] **Step 4: `__main__.py` and the package docstring**

`homebase/charts/__main__.py`:
- add imports `from ..paths import state_dir` and `from .desk import DeskLink`;
- pass this to `create_app(...)`:

```python
                     desk_factory=None if a.replay else (
                         lambda fan: DeskLink(fan, key_path=state_dir() / "desk.key")))
```

`homebase/charts/__init__.py`: replace the sentence `Nothing in this package places, modifies or cancels orders.` with `Nothing in this package talks to the broker's order API: trading from the chart goes to the desk (:8850) through desk.py, which holds the only key.`

- [ ] **Step 5: Run the chart tests**

Run: `.venv/bin/python -m pytest -q tests/test_charts_desk_server.py tests/test_charts_desk.py tests/test_charts_server.py`
Expected: all PASS. The existing chart tests still see `status` first, and the new `desk` message only follows it.

- [ ] **Step 6: Final verification — the full suite and the invariants**

Run: `.venv/bin/python -m pytest -q`
Expected: all PASS, 281 pre-existing tests plus this plan's.

Run:
```bash
git diff main --stat
grep -n "strategy=" homebase/trading.py
git diff main -- homebase/timer.py homebase/engine.py | grep "^[+-]" | grep -v "^+++\|^---"
```
Expected:
- The diff touches only the files in this plan's File Structure, plus the plan doc.
- `grep "strategy="` in `trading.py` prints nothing: no `manual_*` event carries a strategy.
- The only timer/engine changes are the `_prestage_skip` call and method, `PRESTAGE_READ_S`, the `assignments` import, `_skips`/`skip_today`/`skipped_today`, and the `handle_alert` filter.

- [ ] **Step 7: Commit**

```bash
git add homebase/charts/server.py homebase/charts/__main__.py homebase/charts/__init__.py tests/test_charts_desk_server.py
git commit -m "feat(charts): wire the desk link - desk hello after status, desk events and quotes to every page, POST /api/desk/* proxy; replay never links" -m "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

**Deploying is out of scope.** It needs the user's explicit OK for a desk restart, outside market hours, and chart trading stays OFF until the user switches it on. The first real order is the user's.
