"""GET / OPTIONS / PUT /api/settings: the market-data login switch and the clock format."""
from __future__ import annotations

import asyncio

from fastapi import HTTPException, Request, Response
from fastapi.responses import JSONResponse

from ... import netguard
from ... import ticks as T
from ..paperbook import DESK_ORIGINS, _cors, desk_origin_refusal
from ..settings_store import CLOCK_CHOICES, MD_CHOICES, md_only
from ..tickfeed import SwitchInProgress
from .common import browser_write_ok

# Task 4 app-settings plan, Fix round 1 (review of bdaccbd):
BOT_BUSY_STATUSES = ("placing", "placed", "live", "error")   # C3: trading.BOT_BUSY + "error"
MD_SWITCH_COOLDOWN_S = 600         # I3: at most one switch ATTEMPT every 10 min
MD_SWITCH_BUDGET_HEADROOM = 120    # I3/N4: refuse a switch once the TARGET login is this close to 180/h


def register(app, *, settings_store, feed, clock, roots, link, log, md_switch_timeout_s) -> None:
    """md_switch_timeout_s(): MD_SWITCH_TIMEOUT_S, read from charts/server.py at the PUT (a test shortens it there)."""
    last_md_switch_attempt = [0.0]   # epoch s of the last PUT /api/settings that actually switched (I3 cooldown)

    def bot_placing() -> bool:
        """True while the desk reports ANY account working a bot -- trading.py's own BOT_BUSY =
        ("placing", "placed", "live"), plus "error" (cheap to include, and an account in a state
        this process cannot make sense of should read as busy, not idle). Review C3: the desk
        pauses its OWN view publishing for the entire "placing" span (trading.py's
        _views_paused), so this process's DeskLink.state never actually holds "placing" -- it
        jumps idle -> placed directly. Blocking on "placed"/"live" too is what makes this a real
        guard rather than a state this process can never observe.

        Fail closed (review C3): a link that is CONFIGURED but whose state is unknown (never
        received one) or reports `down` reads as busy -- an md switch is optional work, and it
        must never fire blind into a desk this process has lost contact with. `link is None`
        (replay, or no desk link at all) is the one case that is genuinely never busy."""
        if link is None:
            return False
        if link.state is None or link.down is not None:
            return True
        strategies = (link.state.get("bot") or {}).get("strategies") or {}
        return any(a.get("status") in BOT_BUSY_STATUSES
                  for s in strategies.values()
                  for a in (s.get("accounts") or {}).values())

    def md_switch_refused() -> str | None:
        """None, or the one sentence the Settings dialog shows: refused while the desk reports a bot
        actually working (any status, any strategy -- not just today's booked ones)."""
        if bot_placing():
            return "Not while the 9:30 bot is working — try after 09:35."
        return None

    @app.get("/api/settings")
    async def get_settings(request: Request, response: Response):
        """{"md": ..., "accounts": {"live": "···885"|None, "demo": "···021"|None}}. `accounts`
        (review M2) is read from the desk's own config + token files at request time, masked to
        the last 3 characters -- never the settings file, never hard-coded (the Apex login has
        already changed once). None means that login currently has no valid md token, i.e. a
        switch to it would fail (this also surfaces a C2 mismatch before it's ever attempted).

        Desk-settings plan (2026-09-27): answers the desk page's origin too (paperbook's exact-
        origin CORS, extended to this route -- everything else on this service stays same-origin)."""
        bad = desk_origin_refusal(request.headers)
        if bad is not None:
            raise HTTPException(*bad)
        _cors(response, request)
        d = settings_store.get()
        if getattr(feed, "switch_in_progress", False):
            d["md"] = feed.md_env   # the file already names the target; the feed is not there yet
        d["clock"] = settings_store.clock()
        try:
            accts = T.accounts_by_env()
        except Exception:  # noqa: BLE001 — a broken config must never break the dialog, only omit the note
            accts = {"live": None, "demo": None}
        d["accounts"] = {env: (f"···{label[-3:]}" if label and len(label) > 3 else label)
                         for env, label in accts.items()}
        return d

    @app.options("/api/settings")
    async def settings_preflight(request: Request):
        """The desk page's CORS preflight for PUT /api/settings -- allowed for DESK_ORIGINS only
        (anything else: no allow-origin header, so the browser never sends the write)."""
        o = request.headers.get("origin")
        if o not in DESK_ORIGINS:
            return JSONResponse({"detail": "origin not allowed"}, status_code=403)
        return Response(status_code=204, headers={
            "access-control-allow-origin": o, "vary": "Origin", "access-control-allow-methods": "PUT",
            "access-control-allow-headers": "content-type", "access-control-max-age": "600"})

    @app.put("/api/settings")
    async def put_settings(request: Request):
        """{"md": "live"|"demo"}: switches the chart feed's md login in place (TickFeed.switch_md)
        and persists the choice (written first, put back if the switch fails). JSON-only (like the desk proxy) on top
        of the Host check every /api/* route already gets from HostGuard.

        Refused, in order: a bad body (400); replay, which has no switchable feed (503); a switch
        already in flight (409, TickFeed's own SwitchInProgress); a cooldown since the last
        ATTEMPT, successful or not (429, review I3 -- a switch costs roughly 2 requests per root,
        subscribe plus its gap refill, so unthrottled clicking can spend the whole hourly budget
        in under ten); the TARGET login too close to its own hourly budget to afford one
        switch's worth of requests (429); a bot working (423). Any OTHER failure -- a bad connect,
        an environment mismatch, every root refused -- is TickFeed's own RuntimeError (502); nothing else is
        allowed to reach this route as an unhandled 500. A feed that has not answered in
        MD_SWITCH_TIMEOUT_S is 504; the switch still finishes and keeps the file right.

        Desk-settings plan: the exact-origin check (desk_origin_refusal) plus CORS (_cors) wrap
        the whole thing, like paperbook's account-write routes -- a refusal AFTER that check is
        still readable by the desk page, never just "unreachable"."""
        bad = desk_origin_refusal(request.headers)
        if bad is not None:
            raise HTTPException(*bad)
        try:
            result = await do_put_settings(request)
        except HTTPException as e:
            return _cors(JSONResponse({"detail": e.detail}, status_code=e.status_code), request)
        return _cors(JSONResponse(result), request)

    async def do_put_settings(request: Request) -> dict:
        bad = netguard.refusal(request.method, request.scope["headers"], netguard.allowlist())
        if bad is not None:
            raise HTTPException(*bad)
        browser_write_ok(request)
        try:
            body = await request.json()
        except ValueError:
            raise HTTPException(400, "the body is not JSON") from None
        if isinstance(body, dict) and set(body) == {"clock"}:
            # the clock format is a display choice: nothing of the feed moves, so none of the md
            # switch's refusals below apply to it
            if body["clock"] not in CLOCK_CHOICES:
                raise HTTPException(400, f"""the clock is {' or '.join(CLOCK_CHOICES)}""")
            return {"clock": settings_store.set_clock(body["clock"])}
        if not isinstance(body, dict) or "clock" in body or body.get("md") not in MD_CHOICES:
            raise HTTPException(400, f"""a settings update is {{"md": {' or '.join(MD_CHOICES)}}}"""
                                f""" or {{"clock": {' or '.join(CLOCK_CHOICES)}}}""")
        md = body["md"]
        if md_only() not in (None, md):
            raise HTTPException(409, f"this machine's charts use the {md_only()} login only")
        if not hasattr(feed, "switch_md"):
            raise HTTPException(503, "the market-data login can't be switched here (replay)")
        if getattr(feed, "switch_in_progress", False):
            # before the no-op path: its write would overwrite the file the switch in flight
            # already wrote, and a landing switch would then disagree with it
            raise HTTPException(409, "a market-data login switch is already in progress")
        if md == getattr(feed, "md_env", None):
            settings_store.set_md(md)   # already on it -- still make the file agree
            return settings_store.get()
        now_s = clock() / 1000
        since_last = now_s - last_md_switch_attempt[0]
        if since_last < MD_SWITCH_COOLDOWN_S:
            wait = int(MD_SWITCH_COOLDOWN_S - since_last)
            raise HTTPException(429, f"switching logins is limited to once every "
                                     f"{MD_SWITCH_COOLDOWN_S // 60:.0f} minutes — try again in {wait}s")
        if feed.budget_used(md) + 2 * len(roots) > MD_SWITCH_BUDGET_HEADROOM:
            # N4: the switch's getCharts and gap refills are spent on the login switched TO
            raise HTTPException(429, f"the {md} login is close to its hourly market-data budget "
                                     "— try again after it resets")
        reason = md_switch_refused()
        if reason:
            raise HTTPException(423, reason)
        last_md_switch_attempt[0] = now_s   # counts the ATTEMPT, whatever it ends up doing
        previous_md = feed.md_env

        async def switch_and_save() -> None:
            """The file is written FIRST (a write failure then switches nothing) and put back
            if the switch fails -- so the file, status() and the dialog never disagree, and no
            second switch is ever needed to undo one (re-review M-d). Runs as its own task: a
            PUT that times out or is dropped does not cut the bookkeeping short."""
            try:
                settings_store.set_md(md)
            except Exception as e:  # noqa: BLE001
                raise RuntimeError(f"could not save the setting ({type(e).__name__}: {e}) — "
                                   "nothing was switched") from None
            try:
                await feed.switch_md(md)
            except BaseException:
                try:
                    settings_store.set_md(previous_md)
                except Exception as e:  # noqa: BLE001
                    log(f"md switch failed AND the setting could not be put back: {e}")
                raise

        job = asyncio.ensure_future(switch_and_save())
        job.add_done_callback(lambda t: t.cancelled() or t.exception())   # never "never retrieved"
        try:
            await asyncio.wait_for(asyncio.shield(job), md_switch_timeout_s())
        except asyncio.TimeoutError:
            raise HTTPException(504, "the market-data switch is taking too long — its outcome "
                                     "will show in Settings") from None
        except SwitchInProgress as e:
            raise HTTPException(409, str(e)) from None
        except RuntimeError as e:
            raise HTTPException(502, str(e)) from None
        except Exception as e:  # noqa: BLE001 — belt & suspenders: this route must never 500
            raise HTTPException(502, f"{type(e).__name__}: {e}") from None
        return settings_store.get()
