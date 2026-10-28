"""The desk's background loops (clock + 09:25 readiness, equity record, the sibling watch, the inactive sweep) and
the app's lifespan: the desk and Lab keys, every loop started in its order, the shutdown.

Moved verbatim from homebase.server.create_app."""
from __future__ import annotations

import asyncio
import contextlib
import sys

from ..desk import desk_api, dayopen, equity
from ..desk import inactive as inactive_mod
from .readiness import compute_readiness, power_status, should_fire_readiness

CLOCK_INTERVAL_S = 1       # also paces the sibling-cancel backstop (cache reads)
SIBLING_INTERVAL_S = 0.25  # engine.sibling_tick: the close watch on the other entry after a fill
EQUITY_INTERVAL_S = 60


def make_lifespan(*, cfg, engine, adapters, acct_status, timer, level_timer, desk, labdesk, paper_http,
                  background, state_dir, _equity_path, _refresh_snapshots, _broker_loop, feed_status, _feed_loop,
                  _feed_close):
    async def _equity_loop():
        while True:
            with contextlib.suppress(Exception):
                await _refresh_snapshots()
            for aid, ad in list(adapters.items()):
                try:        # from the caches: no broker request
                    if ad.connected:
                        m = await ad.get_metrics()
                        if m.get("balance") is not None and m.get("account"):
                            equity.record_equity(_equity_path(), str(m["account"]), float(m["balance"]),
                                                 engine.now_et().date().isoformat())
                            day = engine._today()
                            dayopen.note(state_dir() / "day_open.json", aid, m["balance"], day,
                                         dayopen.prior_close(equity.equity_by_day(_equity_path(), str(m["account"])), day))
                except Exception:  # noqa: BLE001 — snapshots must never crash
                    pass
            await asyncio.sleep(EQUITY_INTERVAL_S)

    readiness_fired = {"date": None}

    async def _sibling_loop():
        while True:
            try:
                await engine.sibling_tick()
            except Exception as e:  # noqa: BLE001 — the sibling watch must never die
                engine.journal("sibling_loop_error", error=str(e)[:200])
            await asyncio.sleep(SIBLING_INTERVAL_S)

    async def _inactive_loop():
        while True:
            try:
                inactive_mod.sweep(cfg, engine, engine.now_et())
            except Exception as e:  # noqa: BLE001 — a journaling aid must never die or block
                engine.journal("inactive_loop_error", error=str(e)[:200])
            await asyncio.sleep(20.0)

    async def _clock_loop():
        while True:
            try:
                await engine.clock_tick()
                now = engine.now_et()
                if should_fire_readiness(now, readiness_fired["date"]):
                    readiness_fired["date"] = now.date().isoformat()
                    r = compute_readiness(now, cfg, engine, acct_status,
                                          feed_status(), timer.status(), power_status(), lab=labdesk)
                    engine.journal(
                        "morning_readiness", ready=r["ready"],
                        problems=[c["label"] + ": " + c["detail"]
                                  for c in r["checks"]
                                  if c["level"] in ("bad", "warn")])
            except Exception as e:  # noqa: BLE001 — the clock must never die
                engine.journal("clock_error", error=str(e))
            await asyncio.sleep(CLOCK_INTERVAL_S)

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        _app.state.desk_key, key_err = desk_api.ensure_key(state_dir() / desk_api.KEY_FILE)
        if key_err:
            engine.journal("desk_key_error", error=key_err)
        # the Lab runner's OWN key (never the chart service's): /api/lab/* answers 503 without it
        _app.state.lab_key = None

        def _lab_key() -> None:
            if not labdesk.on:                       # an OFF desk makes no key: the gate answers 503 and the runner
                return                               # has none to read (it stays in shadow)
            _app.state.lab_key, lab_key_err = desk_api.ensure_key(state_dir() / desk_api.LAB_KEY_FILE)
            if lab_key_err:
                engine.journal("lab_key_error", error=lab_key_err)

        for step in (_lab_key, labdesk.start):       # (start: says whether the Lab side is on, rebuilds its counters)
            try:                             # a Lab problem never fails the desk's start, and one step's never the other's
                step()
            except Exception as e:  # noqa: BLE001
                print(f"homebase desk: the Lab side's start failed: {e!r}", file=sys.stderr)
                with contextlib.suppress(Exception):
                    engine.journal("lab_start_error", error=f"{type(e).__name__}: {e}"[:200])
        tasks = []
        if background:
            tasks = [asyncio.create_task(_clock_loop()),
                     asyncio.create_task(_broker_loop()),
                     asyncio.create_task(_equity_loop()),
                     asyncio.create_task(timer.loop()),
                     asyncio.create_task(level_timer.loop()),
                     asyncio.create_task(_inactive_loop()),
                     asyncio.create_task(_sibling_loop()),
                     asyncio.create_task(_feed_loop()),
                     asyncio.create_task(desk.run())]
            if labdesk.on:
                tasks.append(asyncio.create_task(labdesk.run()))
        try:
            yield
        finally:
            for t in tasks:
                t.cancel()
            with contextlib.suppress(Exception):
                labdesk.close()              # the Lab store's desk lock goes back (the desk that starts next owns it)
            await _feed_close("shutdown")
            for ad in adapters.values():
                with contextlib.suppress(Exception):
                    await ad.close()
            with contextlib.suppress(Exception):
                await paper_http.aclose()

    return lifespan
