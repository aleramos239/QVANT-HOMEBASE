"""Logins and broker accounts: connect, add, reconnect, remove, the permission check and the self-test order.

Moved verbatim from homebase.server.create_app (2026-10-20): same paths, same bodies, registered straight on the app."""
from __future__ import annotations

import asyncio
import contextlib
import json

from fastapi import HTTPException, Request

from .. import config as config_mod
from ..store import secrets_store
from ..broker.base import AccountNotOnLogin, OrderRequest
from ..data.marketdata import TradovateMD

PAPER_ID = "paper"   # the Charts page's built-in paper account (charts/paperbook.PAPER_ID)


def register(app, *, ADD_MANY_MAX, _add_lock, _connect_account, _connect_failed, _drop_account, _key_env, _listed,
                     _login_cooldown, _login_first_spent, _on_desk, acct_status, adapter_factory, adapters, budget, cfg,
                     engine, paper_http) -> None:

    # ------------------------------------------------------------ setup
    @app.get("/api/logins")
    async def logins():
        in_use = {a.keyring_key for a in cfg.accounts.values()}
        out = []
        for key in secrets_store._load_all():
            out.append({"key": key, "label": (key.split(":", 2)[-1] or key).upper(),
                        "env": _key_env(key),
                        "in_use": key in in_use})
        return {"logins": out}

    @app.post("/api/logins/delete")
    async def logins_delete(request: Request):
        body = await request.json()
        key = str(body.get("key") or "")
        if any(a.keyring_key == key for a in cfg.accounts.values()):
            raise HTTPException(409, "that login is in use by an account")
        secrets_store.delete_credentials(key)
        return {"ok": True}

    @app.post("/api/connect")
    async def connect(request: Request):
        """Validate a login (saved or new; demo by default, live on request)
        with a throwaway probe and return every account under it. Nothing is
        added to the pool yet — that is /api/accounts/add, one per account."""
        # the probe is a real login that re-rolls the login's shared token
        body = await request.json()
        env = "live" if str(body.get("env") or "").lower() == "live" else "demo"
        saved = str(body.get("saved_key") or "")
        if saved:
            if not secrets_store.get_credentials(saved):
                raise HTTPException(404, f"no saved login {saved!r}")
            key, env = saved, _key_env(saved)
        else:
            username = str(body.get("username") or "").strip()
            # newlines/CRs are never valid in a password but ride along with
            # clipboard pastes; spaces are preserved (could be legitimate)
            password = str(body.get("password") or "").strip("\r\n")
            if not username or not password:
                raise HTTPException(400, "username and password required")
            key = f"tv:{env}:{username.lower()}"
            secrets_store.set_credentials(key, username=username,
                                          password=password)
        # the probe is a real login: it goes through the user's budget like every other
        # (a 429 cool-down or the hourly cap refuses it; the wizard shows why). It is the
        # ONE login of an "add several" -- the entries then ride the token it leaves on
        # the shared auth (reconnect, no login).
        login_id = (key, env == "live")
        why = budget.blocked(key, first=login_id not in _login_first_spent, manual=True)
        if why:
            return {"ok": False, "error": why, "key": key}
        _login_first_spent.add(login_id)
        budget.record_login(key)
        probe = adapter_factory("probe", config_mod.AccountCfg(
            keyring_key=key, live=(env == "live")))
        try:
            await probe.connect()
            accounts = probe.list_accounts() if hasattr(probe, "list_accounts") else []
            budget.login_result(key)
        except Exception as e:  # noqa: BLE001 — surface to the wizard
            budget.login_result(key, e)
            return {"ok": False, "error": str(e), "key": key}
        finally:
            with contextlib.suppress(Exception):
                await probe.close()
        _listed[key] = {str(a.get("name") or "").lower() for a in accounts}
        accounts = [{**a, "on_desk": _on_desk(key, str(a.get("name") or "")) is not None}
                    for a in accounts]
        return {"ok": True, "key": key, "env": env, "accounts": accounts}

    @app.post("/api/accounts/add")
    async def accounts_add(request: Request):
        """Add one broker account to the pool and connect it. Demo or live is
        the login's (verified) env — never a client flag. A new account is
        never assigned to a strategy: it trades only once the user assigns it."""
        body = await request.json()
        key = str(body.get("key") or "")
        account_name = str(body.get("account_name") or "").strip()
        if not key or not secrets_store.get_credentials(key):
            raise HTTPException(400, "unknown login key")
        if not account_name:
            raise HTTPException(400, "account_name required")
        aid = account_name.lower()
        live = _key_env(key) == "live"
        cfg.accounts[aid] = config_mod.AccountCfg(
            keyring_key=key, account_name=account_name, live=live,
            label=str(body.get("label") or account_name))
        config_mod.save(cfg)
        engine.journal("account_added", account=aid, live=live)
        try:
            await _connect_account(aid, manual=True)
        except Exception as e:  # noqa: BLE001
            _connect_failed(aid, e)
            return {"ok": True, "account": aid, "connected": False,
                    "error": acct_status[aid]["error"]}
        return {"ok": True, "account": aid, "connected": True}

    @app.post("/api/accounts/add-many")
    async def accounts_add_many(request: Request):
        """Add several accounts of ONE login (the wizard's checkboxes). Each becomes a
        normal entry pinned to its own broker account -- never booked, never assigned to
        a strategy: booking stays the account holder's call. One at a time, on the shared
        token the wizard's probe left (reconnect, no login): N accounts cost the probe's
        ONE login, and the batch stops at the first failure that could spend another
        (a login refused, a socket error), so it never turns into N logins.
        Answers one row per requested account: added (connected or not, with why),
        exists (already on the desk) or failed (with the reason)."""
        body = await request.json()
        key = str(body.get("key") or "")
        raw = body.get("accounts")
        if not isinstance(raw, list) or not raw or not all(isinstance(n, str) for n in raw):
            raise HTTPException(400, "accounts: a list of account names required")
        names: list[str] = []
        for n in raw:
            n = n.strip()
            if n and n.lower() not in {x.lower() for x in names}:
                names.append(n)
        if not names:
            raise HTTPException(400, "accounts: a list of account names required")
        if len(names) > ADD_MANY_MAX:
            raise HTTPException(400, f"at most {ADD_MANY_MAX} accounts at a time")
        if not key or not secrets_store.get_credentials(key):
            raise HTTPException(400, "unknown login key")
        listed = _listed.get(key)
        if listed is None:
            raise HTTPException(409, "look this login's accounts up first (Find my accounts)")
        live = _key_env(key) == "live"
        rows: list[dict] = []
        stop = ""                    # why the rest were not tried
        async with _add_lock:
            for name in names:
                low = name.lower()
                row = {"name": name}
                rows.append(row)
                if stop:
                    row.update(status="failed", error=f"not tried — {stop}")
                    continue
                if low not in listed:
                    row.update(status="failed", error="not on this login")
                    continue
                have = _on_desk(key, name)
                if have is not None:
                    row.update(status="exists", id=have)
                    continue
                if low in cfg.accounts:
                    row.update(status="failed", error="another entry on the desk already "
                               "uses this id")
                    continue
                cfg.accounts[low] = config_mod.AccountCfg(
                    keyring_key=key, account_name=name, live=live, label=name)
                config_mod.save(cfg)
                engine.journal("account_added", account=low, live=live, batch=True)
                row.update(status="added", id=low)
                try:
                    row["mode"] = await _connect_account(low, manual=True)
                    row["connected"] = True
                    if row["mode"] == "login":
                        # the shared token did not carry it, so it spent a login: the
                        # next one could too -- stop here, the rest can be added again
                        stop = "the previous account had to log in again"
                except Exception as e:  # noqa: BLE001 — recorded, reported per account
                    _connect_failed(low, e)
                    row["connected"] = False
                    row["error"] = str((acct_status.get(low) or {}).get("error") or e)[:200]
                    if not isinstance(e, AccountNotOnLogin):
                        stop = "the connection failed (" + str(e)[:120] + ")"
        counts = {s: sum(1 for r in rows if r["status"] == s)
                  for s in ("added", "exists", "failed")}
        engine.journal("accounts_added_batch", login=key, live=live, **counts)
        return {"ok": not counts["failed"], "results": rows, **counts}

    @app.post("/api/accounts/reconnect")
    async def accounts_reconnect(request: Request):
        """Manual reconnect for one account (or all). Clears the account's retry
        cooldown and the user's login backoff -- the user is explicitly asking --
        but never a 429 cool-down or the hourly login cap. One attempt each: a
        parked account (not on its login) is retried once and stays parked if it
        still is not there. Reconciles positions afterwards."""
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001 — empty body = all accounts
            body = {}
        only = str(body.get("account") or "")
        targets = [only] if only else list(cfg.accounts)
        results = {}
        for aid in targets:
            if aid not in cfg.accounts:
                results[aid] = {"ok": False, "error": "unknown account"}
                continue
            _login_cooldown.pop(aid, None)
            try:     # one attempt: a parked account stays parked if it fails again
                mode = await _connect_account(aid, manual=True)
                _login_cooldown.pop(aid, None)
                results[aid] = {"ok": True, "mode": mode}
            except Exception as e:  # noqa: BLE001 — surface the reason
                _connect_failed(aid, e)
                results[aid] = {"ok": False, "error": acct_status[aid]["error"][:200]}
        engine.journal("manual_reconnect", results=results)
        if str(body.get("source") or "") == "mcp":
            engine.journal("mcp_action", tool="account_reconnect", account=only or "all",
                           results=results)
        return {"ok": all(r["ok"] for r in results.values()) if results else False,
                "results": results}

    @app.post("/api/accounts/remove")
    async def accounts_remove(request: Request):
        """Remove an account from the pool: unassign it from every strategy,
        close its adapter, drop it. Refused (409) unless the adapter is
        connected with its caches seeded, its cached view shows no position
        in any symbol and no working order, and today's day-states show it
        neither placing, placed nor live. This is NOT the path the login-loop
        fix's automatic gone-account removal takes (_gone_step -> _drop_account
        directly) -- that keeps removing a truly gone account on its own terms.
        A paper account is refused while it exists on the Charts page (remove it there);
        one the chart service no longer lists is dropped here."""
        body = await request.json()
        aid = str(body.get("account") or "")
        if aid not in cfg.accounts:
            raise HTTPException(404, f"unknown account {aid!r}")
        if cfg.accounts[aid].paper:
            # A paper account lives on the Charts page: while it exists there the pool sync would
            # add it straight back. One that is GONE there has no other way out of the pool, so
            # the desk drops it -- but only once the chart service itself says it is gone.
            try:
                r = await paper_http.get("/api/paper/accounts")
                r.raise_for_status()
                listed = {str(row["id"]) for row in r.json()["accounts"]}
            except Exception:  # noqa: BLE001 — not asked, not removed
                raise HTTPException(409, "can't reach the Charts page to check this paper "
                                    "account — try again in a moment") from None
            if aid in listed and aid != PAPER_ID:
                # the owner (2026-10-20): x removes it everywhere -- the Charts page first (it refuses one that
                # still holds a position or orders), then the pool below
                try:
                    r = await paper_http.post("/api/paper/accounts/remove", json={"account": aid})
                    out = r.json()
                except Exception:  # noqa: BLE001 — not removed there, so not here either
                    raise HTTPException(409, "can't reach the Charts page to remove this paper "
                                        "account — try again in a moment") from None
                if not out.get("ok"):
                    raise HTTPException(409, str(out.get("error") or out.get("detail") or "refused by the Charts page"))
            # the built-in PAPER stays on the Charts page (chart trading's own); the pool no longer takes it back
        from_mcp = str(body.get("source") or "") == "mcp"
        ad = adapters.get(aid)
        readable = (ad is not None and ad.connected
                    and getattr(ad, "caches_seeded", False))
        if readable:
            view = ad.trade_view()
            if view is None:
                raise HTTPException(409, "can't read this adapter's cached view — "
                                    "try again once it's connected")
            if view.get("positions"):
                raise HTTPException(409, "account has an open position — flatten first")
            if view.get("orders"):
                raise HTTPException(409, "account has a working order — cancel it first")
        elif from_mcp or (ad is not None and ad.connected and not cfg.accounts[aid].paper):
            # Claude never removes an account whose state it can't read; nor does the page one that is connected
            # but not seeded yet (it may hold a position -- only a disconnected, broken-login entry is the holder's call)
            raise HTTPException(409, "account not connected (or its caches haven't "
                                "seeded yet) — try again once it's connected")
        # else: the account holder's own Remove (the desk page confirms it) of an
        # account the desk can't read -- a blown / closed / broken-login entry.
        # Their call: it has nothing the desk can manage anyway.
        for st in engine.day_states_for_account(aid):
            if st.status in ("placing", "placed", "live"):
                raise HTTPException(409, f"account is {st.status} in "
                                    f"{st.strategy!r} today — wait for it to finish")
        await _drop_account(aid)
        if from_mcp:
            engine.journal("mcp_action", tool="account_remove", account=aid)
        return {"ok": True, "removed": aid}

    @app.get("/api/diag-permissions")
    async def diag_permissions(account: str):
        """Read-only: what the broker says this login may do. No orders."""
        ad = adapters.get(account)
        if ad is None or not ad.connected:
            raise HTTPException(409, "account not connected")
        ws = getattr(ad, "_ws", None)
        if ws is None:
            raise HTTPException(409, "no socket")
        out: dict = {}
        try:
            sync = await ad._ws.user_sync()
            out["userPlugins"] = sync.get("userPlugins")
            out["accountRiskStatuses"] = sync.get("accountRiskStatuses")
            out["userProperties"] = sync.get("userProperties")
            out["users"] = [{k: v for k, v in u.items()
                             if k in ("id", "name", "status", "professional",
                                      "organizationId", "userType")}
                            for u in (sync.get("users") or [])]
        except Exception as e:  # noqa: BLE001
            out["sync_error"] = str(e)
        for label, ep in (("tradingPermissions", "tradingPermission/list"),):
            try:
                out[label] = await ws.request(ep, "")
            except Exception as e:  # noqa: BLE001
                out[label] = f"ERROR: {e}"
        return out

    @app.post("/api/selftest-order")
    async def selftest_order(request: Request):
        """Prove the REAL order path end to end: place one bracketed stop
        entry far from the market, confirm the broker accepted it, then
        cancel it. qty is forced to 1 and the offset has a hard floor, so
        it cannot fill. Parent is a Day order, so even a failed cancel
        expires at the session end."""
        body = await request.json()
        aid = str(body.get("account") or "")
        if aid not in cfg.accounts:
            raise HTTPException(404, f"unknown account {aid!r}")
        ad = adapters.get(aid)
        if ad is None or not ad.connected:
            raise HTTPException(409, "account not connected")
        if cfg.accounts[aid].live:
            raise HTTPException(409, "a live account takes no self-test order")
        if not cfg.accounts[aid].paper:
            # funded PA / LTF accounts are live=False but real money, and a stale ref_price can put the stop at the
            # market: only an account with nothing on it (no position, no working order, no bot busy) is tested
            try:
                m = await ad.get_metrics()
            except Exception as e:  # noqa: BLE001
                raise HTTPException(409, f"can't read this account ({e}) — not tested") from None
            busy = [st.strategy for st in engine.day_states_for_account(aid)
                    if st.status in ("placing", "placed", "live")]
            if m.get("open_positions") or m.get("working_orders") or busy:
                raise HTTPException(409, "the account has a position, a working order or a bot at work — "
                                    "the self-test runs only on an idle account")
        symbol = str(body.get("symbol") or "NQ")
        offset = max(20.0, float(body.get("offset_pts") or 1000))
        plain = bool(body.get("plain"))      # single order, no bracket
        ref = body.get("ref_price")
        if ref is None:
            raise HTTPException(400, "ref_price required (a recent market price)")
        entry = round(float(ref) + offset, 2)
        trace: dict = {"symbol": symbol, "entry_stop": entry, "qty": 1,
                       "offset_pts": offset, "mode": "plain" if plain else "bracket"}
        req = OrderRequest(symbol=symbol, side="Buy", qty=1, order_type="Stop",
                           price=entry,
                           stop_price=None if plain else entry - 5,
                           tp_price=None if plain else entry + 15,
                           text="homebase:selftest")
        if str(body.get("transport") or "ws") == "rest":
            # Same account, same token, completely different transport — tells
            # us whether the refusal is the socket path or the account itself.
            import urllib.request, urllib.error  # noqa: PLC0415
            host = "live" if cfg.accounts[aid].live else "demo"
            url = f"https://{host}.tradovateapi.com/v1/order/placeorder"
            payload = {"accountSpec": getattr(ad, "_acct_name", ""),
                       "accountId": getattr(ad, "_acct_num", 0),
                       "action": "Buy", "symbol": TradovateMD.resolve(symbol),
                       "orderQty": 1, "orderType": "Stop", "stopPrice": entry,
                       "timeInForce": "Day", "isAutomated": True,
                       "text": "homebase:selftest"}
            tok = getattr(getattr(ad, "_auth", None), "access_token", "")
            rq = urllib.request.Request(
                url, data=json.dumps(payload).encode(),
                headers={"Content-Type": "application/json",
                         "Accept": "application/json",
                         "Authorization": f"Bearer {tok}"})
            def _post():
                try:
                    with urllib.request.urlopen(rq, timeout=20) as resp:
                        return resp.status, resp.read().decode()[:600]
                except urllib.error.HTTPError as e:
                    return e.code, e.read().decode()[:600]
                except Exception as e:  # noqa: BLE001
                    return -1, str(e)[:300]
            st, txt = await asyncio.to_thread(_post)
            trace["rest"] = {"url": url, "http_status": st, "response": txt,
                             "sent": {k: v for k, v in payload.items()
                                      if k != "accountSpec"}}
            engine.journal("selftest_order_rest", account=aid, **trace["rest"])
            return {"ok": st == 200, "trace": trace}
        r = await ad.place_order(req) if plain else await ad.place_bracket(req)
        trace["placed"] = {"ok": r.ok, "order_id": r.order_id, "error": r.error,
                           "raw": r.raw}      # full broker response, verbatim
        try:
            if r.ok and r.order_id:
                await asyncio.sleep(1.5)
                try:
                    m = await ad.get_metrics()
                    trace["working_orders_after_place"] = m.get("working_orders")
                    trace["net_position"] = await ad.get_net_position(symbol)
                except Exception as e:  # noqa: BLE001
                    trace["readback_error"] = str(e)
        finally:
            if r.ok and r.order_id:
                c = await ad.cancel_order_by_id(r.order_id)
                trace["cancelled"] = {"ok": c.ok, "error": c.error}
                # (a failed cancel never falls back to cancel_all: that takes every order of the account)
                await asyncio.sleep(1.0)
                try:
                    m2 = await ad.get_metrics()
                    trace["working_orders_after_cancel"] = m2.get("working_orders")
                    # safety: a close-to-market test stop could fill before the
                    # cancel lands — never leave a position behind. The account was idle at the start, so
                    # a position here is the test's own: close that symbol only, never the whole account
                    net = await ad.get_net_position(symbol)
                    trace["net_after_cancel"] = net
                    if net:
                        f = await ad.flatten_symbol(symbol)
                        trace["emergency_flatten"] = {"ok": f.ok, "error": f.error}
                except Exception as e:  # noqa: BLE001
                    trace["final_readback_error"] = str(e)
        engine.journal("selftest_order", account=aid, **trace)
        return {"ok": bool(r.ok), "trace": trace}

