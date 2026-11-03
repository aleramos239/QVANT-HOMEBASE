"""Logins and broker accounts: connect, add, reconnect, remove, the permission check and the self-test order.

Moved verbatim from homebase.server.create_app (2026-10-20): same paths, same bodies, registered straight on the app."""
from __future__ import annotations

import asyncio
import contextlib
import json
import re
import time

import httpx
from fastapi import HTTPException, Request

from .. import config as config_mod
from ..store import secrets_store
from ..broker.base import AccountNotOnLogin, OrderRequest
from ..broker.login_budget import LoginDeferred
from ..broker.alphatrader_auth import NeedsCode as AtrNeedsCode
from ..broker.topstepx_auth import NeedsCode, TsxLoginFailed
from ..broker.vest_auth import NeedsSignature
from ..data.marketdata import TradovateMD
from ..desk_app import brokers
from ..desk_app.brokers import NEEDS_SIGNATURE, is_atr_key, is_tsx_key, is_vest_key

PAPER_ID = "paper"   # the Charts page's built-in paper account (charts/paperbook.PAPER_ID)
VEST_PENDING_S = 300       # a wallet challenge waits this long for its signature
VEST_PENDING_MAX = 100     # challenges kept waiting at once (the oldest dropped)
_ADDR = re.compile(r"0x[0-9a-fA-F]{40}")
_SIG = re.compile(r"0x[0-9a-fA-F]{2,20000}")    # a smart wallet's signature is long, still hex
_mono = time.monotonic


def _vest_addr(body) -> str:
    addr = body.get("address") if isinstance(body, dict) else None
    if not isinstance(addr, str) or not _ADDR.fullmatch(addr):
        raise HTTPException(400, "address: a wallet address (0x and 40 hex digits) required")
    return addr.lower()


def _vest_why(e: Exception) -> str:
    """Why a Vest login step failed, in words that never carry what was sent (the signature) nor Vest's answer body."""
    if isinstance(e, NeedsSignature):
        return NEEDS_SIGNATURE
    if isinstance(e, LoginDeferred):
        return str(e)
    if isinstance(e, httpx.HTTPStatusError):
        return f"Vest refused it (HTTP {e.response.status_code})"
    return f"the Vest login failed ({type(e).__name__})"


def _tsx_why(e: Exception) -> str:
    """Why a TopstepX login step failed, in words that never carry the password, the token nor TopstepX's answer body."""
    if isinstance(e, httpx.HTTPStatusError):
        return f"TopstepX refused it (HTTP {e.response.status_code})"
    if isinstance(e, (LoginDeferred, TsxLoginFailed)):    # the budget's words / TopstepX's own (the session masks the password)
        return str(e)[:200]
    return f"the TopstepX login failed ({type(e).__name__})"


def _atr_why(e: Exception) -> str:
    """Why an AlphaTrader login step failed, in words that never carry the password, a token nor Alpha's answer body."""
    if isinstance(e, httpx.HTTPStatusError):
        return f"AlphaTrader refused it (HTTP {e.response.status_code})"
    if isinstance(e, RuntimeError):     # the budget's words, Alpha's own (the session masks the password), the socket's
        return str(e)[:200]
    return f"the AlphaTrader login failed ({type(e).__name__})"


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def register(app, *, ADD_MANY_MAX, _add_lock, _connect_account, _connect_failed, _drop_account, _key_env, _listed,
                     _login_cooldown, _login_first_spent, _on_desk, acct_status, adapter_factory, adapters, budget, cfg,
                     engine, paper_http) -> None:

    # ------------------------------------------------------------ setup
    @app.get("/api/logins")
    async def logins():
        in_use = {a.keyring_key for a in cfg.accounts.values()}
        out = []
        for key in secrets_store._load_all():
            label = (key.split(":", 2)[-1] or key).upper()
            if is_vest_key(key):                    # the wallet, short: 0xBBE1…1EAB
                label = "0x" + key[7:11].upper() + "…" + key[-4:].upper()
            if is_tsx_key(key) or is_atr_key(key):  # the username / email, as typed
                label = str((secrets_store.get_credentials(key) or {}).get("username") or key[4:])
            out.append({"key": key, "label": label,
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
        for sessions in (brokers._TSX_SESSIONS, brokers._ATR_SESSIONS):
            sess = sessions.pop(key, None)
            if sess is not None:
                with contextlib.suppress(Exception):
                    await sess.aclose()
        return {"ok": True}

    # ------------------------------------------------------------ Vest: the wallet login
    vest_pending: dict[str, float] = {}      # wallet address -> when its challenge was handed out
    vest_registering: dict[str, int] = {}    # login key -> registers in flight on it (they may overlap): its session stays

    async def _vest_forget(key: str) -> None:
        """A wallet that never signed keeps no session (nothing saved under it, no entry on it, no register running)."""
        if (vest_registering.get(key, 0) > 0 or secrets_store.get_credentials(key)
                or any(a.keyring_key == key for a in cfg.accounts.values())):
            return
        sess = brokers._VEST_SESSIONS.pop(key, None)
        if sess is not None:
            with contextlib.suppress(Exception):
                await sess.aclose()

    async def _vest_drop(addr: str) -> None:
        vest_pending.pop(addr, None)
        await _vest_forget("vest:" + addr)

    def _vest_on_desk(key: str, vest_account_id) -> str | None:
        """The entry already carrying this Vest account (by its id: two entries never trade one account)."""
        return next((aid for aid, a in cfg.accounts.items()
                     if a.keyring_key == key and a.vest_account_id == str(vest_account_id)), None)

    @app.post("/api/vest/challenge")
    async def vest_challenge(request: Request):
        """Step 1 of a Vest login: Vest's login message (EIP-712 typed data) for the owner's wallet to sign. It waits
        5 minutes on the login's one shared session (R47); a new challenge for the same wallet replaces the old one."""
        addr = _vest_addr(await request.json())
        key = "vest:" + addr
        why = budget.blocked(key, manual=True)      # the login it leads to would be refused: never ask for a signature
        if why:
            return {"ok": False, "error": why}
        now = _mono()
        vest_pending.pop(addr, None)                 # a new challenge replaces this wallet's old one
        for a in [a for a, t in vest_pending.items() if now - t > VEST_PENDING_S]:
            await _vest_drop(a)
        while len(vest_pending) >= VEST_PENDING_MAX:
            await _vest_drop(next(iter(vest_pending)))
        sess = brokers.vest_session(key)
        sess.budget = budget
        try:
            ch = await sess.challenge(addr)
        except Exception as e:  # noqa: BLE001 — surface to the wizard
            await _vest_forget(key)
            return {"ok": False, "error": _vest_why(e)}
        vest_pending[addr] = now
        return {"ok": True, "typed_data": ch["message"]}

    async def _vest_connect(body: dict, saved: str) -> dict:
        """/api/connect for Vest: a saved login (its session renews itself, or it needs a new signature) or a new one
        (the wallet signed the pending challenge; `register` books the login on the desk's budget: blocked,
        record_login, login_result). Then the same throwaway probe as Tradovate lists the login's accounts (R3)."""
        if saved:
            if not secrets_store.get_credentials(saved):
                raise HTTPException(404, f"no saved login {saved!r}")
            key = saved
            sess = brokers.vest_session(key)
            sess.budget = budget
            if sess.needs_signature:
                return {"ok": False, "error": NEEDS_SIGNATURE, "key": key}
        else:
            addr = _vest_addr(body)
            key = "vest:" + addr
            sig = body.get("signature")
            if not isinstance(sig, str) or not _SIG.fullmatch(sig):
                raise HTTPException(400, "signature: the wallet's signature (0x and hex) required")
            t = vest_pending.get(addr)
            if t is None or _mono() - t > VEST_PENDING_S:     # (a double-click lands here; the sweep cleans up)
                raise HTTPException(400, "no wallet challenge waiting for this address — start the login again")
            del vest_pending[addr]                   # one try per challenge
            sess = brokers.vest_session(key)
            sess.budget = budget
            vest_registering[key] = vest_registering.get(key, 0) + 1
            failed = None
            try:
                await sess.register(addr, sig)
            except Exception as e:  # noqa: BLE001 — surface to the wizard, never the signature
                failed = e
            finally:                                 # a cancelled request too: never a mark left behind
                vest_registering[key] -= 1
                if not vest_registering[key]:
                    del vest_registering[key]
            if failed is not None:
                await _vest_forget(key)
                return {"ok": False, "error": _vest_why(failed), "key": key}
        probe = adapter_factory("probe", config_mod.AccountCfg(keyring_key=key))   # no vest_account_id: no orders
        try:
            await probe.connect()
            accounts = await probe.list_accounts()
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": _vest_why(e), "key": key}
        finally:
            with contextlib.suppress(Exception):
                await probe.close()
        _listed[key] = {str(a["name"]).lower(): a for a in accounts}     # name -> row: add-many reads the id from it
        accounts = [{**a, "on_desk": _vest_on_desk(key, a["id"]) is not None} for a in accounts]
        return {"ok": True, "key": key, "env": "vest", "accounts": accounts}

    async def _tsx_connect(body: dict, saved: str) -> dict:
        """/api/connect for TopstepX: a saved login or a new username + password (+ the one-time code the wizard asked
        for). New credentials, or a code, are checked by a real login here; a saved login reuses its session's token or
        renews it through the budget. Then the same throwaway probe as Tradovate lists the login's accounts."""
        if saved:
            if not secrets_store.get_credentials(saved):
                raise HTTPException(404, f"no saved login {saved!r}")
            key = saved
        else:
            username = str(body.get("username") or "").strip()
            password = str(body.get("password") or "").strip("\r\n")
            if not username or not password:
                raise HTTPException(400, "username and password required")
            key = f"tsx:{username.lower()}"
            secrets_store.set_credentials(key, username=username, password=password)
        code = str(body.get("code") or "").strip()
        login_id = (key, False)
        why = budget.blocked(key, first=login_id not in _login_first_spent, manual=True)
        if why:
            return {"ok": False, "error": why, "key": key}
        _login_first_spent.add(login_id)
        sess = brokers.tsx_session(key)
        sess.budget, sess.journal = budget, engine.journal
        if code or not saved:
            budget.record_login(key)
            try:
                # under the session's lock: the 401 retry, a renewal and the kick handler all hold it, and a login they
                # run at the same moment would be overwritten by (or would overwrite) this one -- a ping-pong of tokens
                async with sess._lock:
                    await sess.login(code=code or None)
            except NeedsCode:
                budget.login_result(key)             # nothing was refused: the owner answers the code
                return {"ok": False, "needs_code": True, "key": key}
            except Exception as e:  # noqa: BLE001
                budget.login_result(key, e)
                return {"ok": False, "error": _tsx_why(e), "key": key}
            budget.login_result(key)
            for aid, a in cfg.accounts.items():     # the code is answered: its accounts need not wait out their cool-down
                if a.keyring_key == key:
                    _login_cooldown.pop(aid, None)
        probe = adapter_factory("probe", config_mod.AccountCfg(keyring_key=key))
        try:
            await probe.connect()        # reuses the token; with none (a saved login) it logs in through the budget
            accounts = probe.list_accounts()
        except NeedsCode:
            return {"ok": False, "needs_code": True, "key": key}
        except Exception as e:  # noqa: BLE001 — surface to the wizard
            return {"ok": False, "error": _tsx_why(e), "key": key}
        finally:
            with contextlib.suppress(Exception):
                await probe.close()
        _listed[key] = {str(a["name"]).lower(): a for a in accounts}     # name -> row: add-many reads `practice` from it
        accounts = [{**a, "on_desk": _on_desk(key, str(a["name"])) is not None} for a in accounts]
        return {"ok": True, "key": key, "env": "tsx", "accounts": accounts}

    async def _atr_connect(body: dict, saved: str) -> dict:
        """/api/connect for AlphaTrader, as TopstepX: a saved login or a new email + password (+ the one-time code the
        wizard asked for). New credentials, or a code, are checked by a real login here (the session books it on the
        budget); a saved login reuses its session's token or renews it (refresh, else a booked login). Then a throwaway
        probe lists the login's accounts, and is closed (it leaves no socket of its own)."""
        if saved:
            if not secrets_store.get_credentials(saved):
                raise HTTPException(404, f"no saved login {saved!r}")
            key = saved
        else:
            email = str(body.get("email") or body.get("username") or "").strip()
            password = str(body.get("password") or "").strip("\r\n")
            if not email or not password:
                raise HTTPException(400, "email and password required")
            key = f"atr:{email.lower()}"
            secrets_store.set_credentials(key, username=email, password=password)
        code = str(body.get("code") or "").strip()
        login_id = (key, False)
        why = budget.blocked(key, first=login_id not in _login_first_spent, manual=True)
        if why:
            return {"ok": False, "error": why, "key": key}
        _login_first_spent.add(login_id)
        sess = brokers.atr_session(key)
        sess.budget, sess.journal = budget, engine.journal
        try:
            if code or not saved:
                await sess.login(code=code or None, manual=True)    # books itself on the budget, under the session's lock
                for aid, a in cfg.accounts.items():     # answered: its accounts need not wait out their cool-down
                    if a.keyring_key == key:
                        _login_cooldown.pop(aid, None)
            else:
                await sess.access()
        except AtrNeedsCode:
            return {"ok": False, "needs_code": True, "key": key}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": _atr_why(e), "key": key}
        probe = adapter_factory("probe", config_mod.AccountCfg(keyring_key=key))
        try:
            await probe.connect(manual=True)        # joins the login's T4 socket, or opens one (closed with the probe if it is alone)
            accounts = probe.list_accounts()
        except AtrNeedsCode:
            return {"ok": False, "needs_code": True, "key": key}
        except Exception as e:  # noqa: BLE001 — surface to the wizard
            return {"ok": False, "error": _atr_why(e), "key": key}
        finally:
            with contextlib.suppress(Exception):
                await probe.close()
        _listed[key] = {str(a["name"]).lower(): a for a in accounts}     # name -> row: add-many reads id and practice
        accounts = [{**a, "on_desk": _on_desk(key, str(a["id"])) is not None} for a in accounts]
        return {"ok": True, "key": key, "env": "atr", "accounts": accounts}

    @app.post("/api/connect")
    async def connect(request: Request):
        """Validate a login (saved or new; demo by default, live on request)
        with a throwaway probe and return every account under it. Nothing is
        added to the pool yet — that is /api/accounts/add, one per account."""
        # the probe is a real login that re-rolls the login's shared token
        body = await request.json()
        env = "live" if str(body.get("env") or "").lower() == "live" else "demo"
        saved = str(body.get("saved_key") or "")
        if is_vest_key(saved) or (not saved and str(body.get("broker") or "").lower() == "vest"):
            return await _vest_connect(body, saved)
        if is_tsx_key(saved) or (not saved and str(body.get("broker") or "").lower() == "tsx"):
            return await _tsx_connect(body, saved)
        if is_atr_key(saved) or (not saved and str(body.get("broker") or "").lower() == "atr"):
            return await _atr_connect(body, saved)
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
        vest = is_vest_key(key)
        tsx = is_tsx_key(key)
        atr = is_atr_key(key)
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
                have = (_vest_on_desk(key, listed[low].get("id")) if vest
                        else _on_desk(key, str(listed[low].get("id"))) if atr else _on_desk(key, name))
                if have is not None:
                    row.update(status="exists", id=have)
                    continue
                aid = _slug(name) if vest or atr else low
                if aid in cfg.accounts:
                    row.update(status="failed", error="another entry on the desk already "
                               "uses this id")
                    continue
                if vest:     # no floors: its entries are refused until the owner sets them (fail closed)
                    try:     # a row Vest worded oddly fails alone; no demo flag = live (the stricter rules)
                        v = listed[low]
                        acct = config_mod.AccountCfg(keyring_key=key, vest_account_id=str(v["id"]),
                                                     live=not bool(v.get("demo", False)), label=name)
                    except (KeyError, TypeError, AttributeError) as e:
                        row.update(status="failed", error=f"Vest's row for it is unreadable ({type(e).__name__})")
                        continue
                    cfg.accounts[aid] = acct
                elif atr:    # pinned by its T4 account id (the name shown is its display name); practice = demo, else live
                    cfg.accounts[aid] = config_mod.AccountCfg(
                        keyring_key=key, account_name=str(listed[low]["id"]), label=name,
                        live=not bool(listed[low].get("practice", False)))
                else:    # TopstepX: a practice account is demo, every other is live (no marker = live, the stricter rules)
                    cfg.accounts[aid] = config_mod.AccountCfg(
                        keyring_key=key, account_name=name, label=name,
                        live=not bool(listed[low].get("practice", False)) if tsx else live)
                config_mod.save(cfg)
                engine.journal("account_added", account=aid, live=cfg.accounts[aid].live, batch=True)
                row.update(status="added", id=aid)
                try:
                    row["mode"] = await _connect_account(aid, manual=True)
                    row["connected"] = True
                    # a Vest entry only mints its account token on the login's one session: it never logs in again
                    # nor a TopstepX one: its session books its own logins, `mode` is always "login"
                    if row["mode"] == "login" and not vest and not tsx and not atr:
                        # the shared token did not carry it, so it spent a login: the
                        # next one could too -- stop here, the rest can be added again
                        stop = "the previous account had to log in again"
                except Exception as e:  # noqa: BLE001 — recorded, reported per account
                    _connect_failed(aid, e)
                    row["connected"] = False
                    row["error"] = str((acct_status.get(aid) or {}).get("error") or e)[:200]
                    if not isinstance(e, AccountNotOnLogin):
                        stop = "the connection failed (" + str(e)[:120] + ")"
        counts = {s: sum(1 for r in rows if r["status"] == s)
                  for s in ("added", "exists", "failed")}
        engine.journal("accounts_added_batch", login=key, live=None if vest or tsx or atr else live, **counts)   # a Vest / TopstepX / AlphaTrader row has its own
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
