"""The dashboard page, /api/status (everything the page renders) and /api/journal.

Moved verbatim from homebase.server.create_app (2026-10-20): same paths, same bodies, registered straight on the app."""
from __future__ import annotations

import asyncio
import datetime as dt
import json
from dataclasses import asdict
from pathlib import Path

from fastapi.responses import FileResponse

from ..backtest.slots import backtests_off, status as backtest_slots
from ..desk import dayopen, labdesk as labdesk_mod
from ..desk.metrics import live_metrics
from ..desk_app import brokers
from .variants import status_view as variants_status


def register(app, *, JOURNAL_TAIL, STATIC, _login_cooldown, acct_status, adapters, cfg, compute_readiness, engine,
                     feed_status, journal_cache, labdesk, level_timer, notices, power_status, state_dir, timer) -> None:

    # ------------------------------------------------------------ dashboard
    @app.get("/")
    async def index():
        return FileResponse(STATIC / "index.html", headers={"cache-control": "no-cache"})   # never a cached page with newer desk/*.js

    live_box: dict = {"recs": None, "live": {}}        # live_metrics of the records it last saw

    @app.get("/api/status")
    async def status():
        import time as _t
        accounts = {}
        day, open_path = engine._today(), state_dir() / "day_open.json"
        for aid, a in cfg.accounts.items():
            ad = adapters.get(aid)
            try:        # the adapters' caches only: a poll costs Tradovate nothing
                m = await ad.get_metrics() if ad else {"connected": False}
            except Exception as e:  # noqa: BLE001
                m = {"connected": False, "error": f"metrics: {e}"}
            s = acct_status.get(aid, {})
            if s.get("error") and not m.get("error"):
                m["error"] = s["error"]
            cooldown_s = max(0.0, _login_cooldown.get(aid, 0) - _t.time())
            accounts[aid] = {"label": a.label or a.account_name or aid,
                             "env": "paper" if a.paper else "live" if a.live else "demo",
                             "prop": brokers.is_prop(a),
                             "cooldown_s": round(cooldown_s, 1) if cooldown_s else 0, **m,
                             "day": engine.day_view(aid),      # the day take in force, the day's closed P&L, the lock
                             "day_pnl": dayopen.day_pnl(open_path, aid, m.get("balance"), day)}   # balance now - balance at the 18:00 open
        # the journal is parsed once, then only the lines appended since the last poll
        jp = state_dir() / "journal.jsonl"
        if live_box["recs"] is None:          # the first poll parses the whole file: in a thread, off the loop
            await asyncio.to_thread(journal_cache.records, jp)
        recs = journal_cache.records(jp)
        if recs is not live_box["recs"]:      # a new list: the journal changed
            live_box.update(recs=recs, live=live_metrics(recs))
        live = live_box["live"]
        journal = recs[-JOURNAL_TAIL:][::-1]
        if labdesk.on:                        # the Lab intake's bookkeeping (two lines an event) stays in the file
            journal = labdesk_mod.journal_tail(recs, JOURNAL_TAIL)     # and out of the page's tail
        return {
            "armed": cfg.armed,
            "machine": "server" if backtests_off() else "mac",   # read-only: the trading server has ~/.homebase/no_backtests
            "backtests": backtest_slots(),   # read-only: {off} on the server, else the cap, the slots held, a quiet window
            "chart_trading": asdict(cfg.chart_trading),
            "et_now": engine.now_et().isoformat(timespec="seconds"),
            "readiness": compute_readiness(engine.now_et(), cfg, engine,
                                           acct_status, feed_status(),
                                           timer.status(), power_status(), lab=labdesk),
            "timer": timer.status(),
            "levels": level_timer.status(),
            "feed": feed_status(),
            "accounts": accounts,
            "notices": notices[::-1],      # newest first, one line each, page wording
            "book": labdesk.book_view(),   # cfg.book; for a Lab strategy only the rows of this desk's accounts
            "variants": variants_status(cfg, engine),   # variant sets {sets, suggest}; a member gone from the Desk shrinks its set
            "groups": engine.groups_view(),     # account cycle groups: {id: {name, members, accounts, risk_usd, max_minis, on, next}}
            "strategies": {
                name: {
                    "cfg": {"symbol": s.symbol, "qty": s.qty,
                            "offset_pts": s.offset_pts, "sl_pts": s.sl_pts,
                            "tp_pts": s.tp_pts, "rr": s.rr, "label": s.label, "cancel_et": s.cancel_et,
                            "flat_et": s.flat_et, "fire_et": s.fire_et,
                            "only_dates": list(s.only_dates), "enabled": s.enabled,
                            "gated": s.gated, "self_fire": s.self_fire,
                            "kind": getattr(s, "kind", "straddle"),
                            "shadow": getattr(s, "shadow", False),
                            "rule": getattr(s, "rule", ""),
                            "bar_minutes": getattr(s, "bar_minutes", 1),
                            "shape": s.shape, "fire_et": s.fire_et, "day_take": s.day_take,
                            "day_lock": s.day_lock, "target_take": s.target_take,
                            "size_tiers": s.size_tiers, "ack_open_loss": s.ack_open_loss},
                    "research": s.metrics,
                    "live": live.get(name),
                    "day_status": engine.day_status(name),
                    "killed": engine.killed_today(name),
                    "rotation": engine.rotation_view(name),       # take turns: {on, next account}
                    "accounts": [{**vars(st), "check_it": engine.needs_check(st)}
                                 for st in engine.day_states(name)],
                    **({"lab": labdesk.status_view(name)} if labdesk.on else {}),   # None unless kind "lab"
                } for name, s in cfg.strategies.items()
            },
            "journal": journal,
        }

    def _read_journal_records(jp: Path) -> list[dict]:
        """The blocking half of /api/journal: read the file and parse each line, off the
        event loop (asyncio.to_thread). A line that isn't valid JSON, or parses to
        something other than an object (a bare number/string/array), is skipped. The lines come from the
        journal cache when it can stand for this read (it parses only what was appended)."""
        snap = journal_cache.whole(jp)
        if snap is not None:
            return snap[0]
        if not jp.exists():
            return []
        out = []
        for line in jp.read_text().splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict):
                out.append(rec)
        return out

    def _names_in(touched, names: set) -> bool:
        """A Kill / account flatten names what it touched as {"<strategy>@<account>": ...}."""
        return isinstance(touched, (dict, list)) and any(str(k).split("@", 1)[0] in names for k in touched)

    def _on_account(rec, account: str) -> bool:
        """A line is on an account when it names it, or when a Kill / flatten lists a "<strategy>@<account>" on it."""
        return rec.get("account") == account or any(
            isinstance(v, (dict, list)) and any(str(k).rsplit("@", 1)[-1] == account for k in v)
            for v in (rec.get("touched"), rec.get("strategies")))

    @app.get("/api/journal")
    async def journal_query(date: str | None = None, event: str | None = None,
                            account: str | None = None, limit: int = 200,
                            strategy: str | None = None, group: str | None = None, days: int = 1):
        """Journal events, newest first, for a day (default today ET) or the `days` days ending on it --
        unlike /api/status's fixed JOURNAL_TAIL preview, this one takes a date and filters, for a real
        read of what happened (the MCP desk_journal tool; the Activity page when it shows one strategy, a
        group or more than today). `strategy` (comma-separated ids) and `group` (an account cycle's id)
        keep a line that names one of those strategies or that group."""
        limit = max(1, min(int(limit), 2000))
        last = date or engine.now_et().date().isoformat()
        try:
            first = (dt.date.fromisoformat(last) - dt.timedelta(days=max(1, min(int(days), 90)) - 1)).isoformat()
        except ValueError:
            first = last
        names = {s for s in (strategy or "").split(",") if s}
        jp = state_dir() / "journal.jsonl"
        records = await asyncio.to_thread(_read_journal_records, jp)
        out = []
        for rec in records:
            if not first <= str(rec.get("et", "")).split("T", 1)[0] <= last:
                continue
            if event and rec.get("event") != event:
                continue
            if account and not _on_account(rec, account):
                continue
            if (names or group) and not (rec.get("strategy") in names or (group and rec.get("group") == group)
                                         or _names_in(rec.get("strategies"), names)):
                continue
            out.append(rec)
        out.reverse()
        return {"date": last, "first": first, "count": len(out), "events": out[:limit]}

