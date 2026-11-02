"""The desk's pre-open readiness checks (/api/status `readiness`, the 09:25 morning_readiness journal line).

Moved verbatim from homebase/server.py; homebase.server re-exports compute_readiness and power_status."""
from __future__ import annotations

from .. import config as config_mod
from ..desk import inactive as inactive_mod
from ..desk import labdesk as labdesk_mod
from ..desk.timer import fire_clock, fire_said, fire_time, miss_why, off_anchor, schedule
from .barsfeed import feed_window

READINESS_FROM = (9, 25)


_POWER_CACHE: dict = {"ts": 0.0, "out": None}


def power_status() -> dict | None:
    """{'ac': bool, 'pct': int|None, 'discharging': bool} from pmset, cached
    60 s so /api/status never waits on a subprocess. None off-macOS."""
    import re
    import subprocess
    import time as _t
    if _t.time() - _POWER_CACHE["ts"] < 60:
        return _POWER_CACHE["out"]
    try:
        txt = subprocess.run(["pmset", "-g", "batt"], capture_output=True,
                             text=True, timeout=3).stdout
    except Exception:  # noqa: BLE001 — not macOS / pmset missing
        txt = ""
    out = None
    if txt:
        m = re.search(r"(\d+)%", txt)
        out = {"ac": "AC Power" in txt, "pct": int(m.group(1)) if m else None,
               "discharging": "discharging" in txt}
    _POWER_CACHE.update(ts=_t.time(), out=out)
    return out


def _plus_min(t):
    """`t` (a time of day) a minute later: the readiness check's gate + 1 min."""
    import datetime as dt
    return (dt.datetime.combine(dt.date(2000, 1, 3), t) + dt.timedelta(minutes=1)).time()


def _timer_day(tst: dict | None, status: str, s, armed: bool) -> tuple[str, str] | None:
    """A self-fire straddle's day as its timer saw it, from the open on, as
    (level, detail): a late or off-anchor fire (loud, whatever it placed), a
    wait for a quote, a miss, a timer error, a skip, a fire that placed
    nothing. None: the day status says it."""
    tst = tst or {}
    stage = tst.get("stage")
    if stage == "fired" and off_anchor(tst):
        return "warn", f"{fire_said(tst, fire_time(s))} · " + (status if status != "idle" else "nothing placed")
    if status != "idle":
        return None
    if stage == "waiting":
        return "bad", (f"waiting for a quote since {fire_clock(tst.get('wait_late_s'), fire_time(s))} — "
                       f"{tst.get('wait_text')}")
    if stage == "missed":
        return "bad", "missed today — " + miss_why(tst.get("reason"))
    if stage == "error":
        return "bad", "timer error: " + str(tst.get("error"))[:80]
    if stage == "skipped":
        adx = tst.get("adx")
        chop = "CHOP" + (f" ADX {adx:.1f}" if isinstance(adx, (int, float)) else "")
        return "ok", "skipped today — " + ("killed" if tst.get("killed") else
                                            chop if tst.get("gate") is False else "skipped")
    if stage == "fired":
        if armed and not getattr(s, "shadow", False):
            return "warn", "fired at the open, but nothing was placed — see the journal"
        return "info", "fired at the open — journaled only (" + (
            "shadow" if getattr(s, "shadow", False) else "disarmed") + ")"
    return None


def compute_readiness(now_et, cfg: config_mod.AppCfg, engine,
                      acct_status: dict, feed_status: dict | None = None,
                      timer_status: dict | None = None,
                      power: dict | None = None, lab=None) -> dict:
    """Every check the desk needs before the open, across ALL strategies
    and ALL accounts. levels: ok | info | warn | bad; ready = no bad."""
    import datetime as dt
    checks = []
    if not cfg.accounts:
        checks.append({"level": "bad", "label": "Accounts",
                       "detail": "none connected — the book is empty"})
    for aid, a in cfg.accounts.items():
        s = acct_status.get(aid, {})
        checks.append({"level": "ok" if s.get("connected") else "bad",
                       "label": a.label or a.account_name or aid,
                       "detail": "connected" if s.get("connected")
                       else (s.get("error") or "not connected")})
    if power is not None:
        if power.get("discharging") and (power.get("pct") or 100) < 25:
            checks.append({"level": "bad", "label": "Power",
                           "detail": f"battery {power.get('pct')}% and unplugged — "
                                     "the laptop will die"})
        elif power.get("discharging"):
            # under half is worth a look; above it, on battery is a fact and the shield stays quiet
            low = (power.get("pct") or 100) < 50
            checks.append({"level": "warn" if low else "info", "label": "Power",
                           "detail": f"on battery ({power.get('pct')}%)" + (" — plug in" if low else "")})
        else:
            checks.append({"level": "ok", "label": "Power", "detail": "on power"})
    def shown(n):                       # a strategy as the page names it: its label, else its id
        return cfg.strategies[n].label or n

    # an event-day strategy (only_dates) is not part of a day it does not trade
    enabled = {n: s for n, s in cfg.strategies.items()
               if s.enabled and s.trades_on(now_et.date())}
    teams = getattr(engine, "groups", None) or {}
    for name, s in cfg.strategies.items():             # switched OFF on accounts: says it, so OFF is never a surprise
        if getattr(s, "kind", "straddle") == "lab" and not s.enabled and config_mod.assignments(cfg, name):
            checks.append({"level": "info", "label": shown(name), "detail": "switched OFF: it will not trade"})
    for name, s in enabled.items():
        booked = [a["account"] for a in config_mod.assignments(cfg, name)]
        if not booked:
            if getattr(s, "kind", "straddle") == "lab":      # a promoted Lab strategy: its resting state too
                team = next((g for g in teams.values() if name in g.get("members", ()) and g.get("mode") == "split"), None)
                checks.append({"level": "warn", "label": shown(name),
                               "detail": f"in team {team['name']} with no account: it never trades"} if team else
                              {"level": "info", "label": shown(name), "detail": "no account: runs in shadow"})
                continue
        elif getattr(s, "kind", "straddle") == "lab":       # its accounts stopped for the day (day take / lock / loss)
            locked = [a for a in booked if engine.account_locked(a)]
            if locked:
                names = ", ".join((cfg.accounts[a].label or a) if a in cfg.accounts else a for a in locked)
                checks.append({"level": "warn" if len(locked) == len(booked) else "info", "label": shown(name),
                               "detail": f"account stopped for today: {names}"})
        if not booked:
            # a SHADOW strategy with no account is a normal resting state —
            # it must not hold the bulb amber forever
            checks.append({"level": "info" if getattr(s, "shadow", False) else "warn",
                           "label": shown(name),
                           "detail": "enabled but no accounts assigned"})
    weekday = now_et.weekday() < 5
    if weekday:                          # a booked strategy that will not trade today says why (inactive.py)
        for name, s in cfg.strategies.items():
            why = dict(engine.inactive_today(name))
            got = inactive_mod.static_reason(cfg, engine, name, s, now_et.date())
            if got is not None:
                why.setdefault(*got)
            why.pop("not_scheduled_today", None)    # an event-day strategy off its day: expected, journaled only
            if why and s.enabled and config_mod.assignments(cfg, name):
                checks.append({"level": "warn", "label": shown(name),
                               "detail": "inactive today — " + "; ".join(why.values())})
    live_strats = [n for n, s in enabled.items()
                   if not getattr(s, "shadow", False)
                   and config_mod.assignments(cfg, n)]
    if timer_status is not None and weekday:
        # a minute after the gate (09:21 for the 9:30 fire) every enabled self-fire straddle must
        # have gated (ungated ones gate instantly at the gate time) — idle here means its fire is
        # NOT coming; error carries the reason (e.g. no market data)
        tstat = timer_status.get("strategies") or {}
        for name, sc in enabled.items():
            if getattr(sc, "kind", "straddle") != "straddle" \
                    or not getattr(sc, "self_fire", False):
                continue
            gate_t, _, fire_t, _ = schedule(sc)
            if not (_plus_min(gate_t) <= now_et.time() < fire_t):
                continue
            stage = (tstat.get(name) or {}).get("stage")
            if stage in (None, "idle"):
                checks.append({"level": "bad", "label": shown(name),
                               "detail": f"timer has not gated — the {fire_t.hour}:{fire_t.minute:02d} fire "
                                         "is not armed"})
            elif stage == "error":
                checks.append({"level": "bad", "label": shown(name),
                               "detail": "timer error: " +
                                         str((tstat.get(name) or {}).get("error"))[:80]})
    for name, tst in ((timer_status or {}).get("strategies") or {}).items():
        sym = getattr(cfg.strategies.get(name), "symbol", "?")
        orders = tst.get("skipped_orders") or {}
        unreadable = tst.get("skipped_unreadable") or {}
        unsynced = tst.get("skipped_unsynced") or {}
        checked_at = tst.get("prestage_checked_at") or "09:28:30"   # the real check time
        for aid, net in (tst.get("skipped_accounts") or {}).items():
            a = cfg.accounts.get(aid)
            if aid in unsynced:
                detail = (f"{shown(name)} skipped today — its positions and orders were not synced "
                          f"at {checked_at}: unknown, never taken as flat")
            elif net:
                detail = (f"{shown(name)} skipped today — holds {int(net):+d} {sym} "
                          f"(manual position at {checked_at})")
            elif aid in unreadable:
                # the broker read failed and no cached position confirms one
                # either way — say so, rather than implying a known flat book
                detail = (f"{shown(name)} skipped today — position unknown, "
                          f"{len(orders.get(aid) or ())} working {sym} order(s) "
                          f"(manual, at {checked_at})")
            else:
                detail = (f"{shown(name)} skipped today — {len(orders.get(aid) or ())} "
                          f"working {sym} order(s) (manual, at {checked_at})")
            checks.append({"level": "bad",
                           "label": (a.label or a.account_name or aid) if a else aid,
                           "detail": detail})
    bars = [n for n, s in enabled.items() if getattr(s, "kind", "straddle") == "bars"]
    if bars and weekday and feed_window(now_et):
        up = bool((feed_status or {}).get("connected"))
        if up:
            import datetime as _dt
            closes = [w.get("last_close") for w in
                      ((feed_status or {}).get("watching") or {}).values()]
            closes = [c for c in closes if c]
            age = None
            if closes:
                newest = max(_dt.datetime.fromisoformat(c) for c in closes)
                age = (now_et.astimezone(_dt.timezone.utc) - newest).total_seconds()
            if age is not None and age > 240:
                checks.append({"level": "bad", "label": "Price feed",
                               "detail": f"stale — last bar closed {age / 60:.0f} min ago"})
            else:
                checks.append({"level": "ok", "label": "Price feed",
                               "detail": "live bars flowing"})
        else:
            checks.append({"level": "bad", "label": "Price feed",
                           "detail": "down — " + ", ".join(bars) + " cannot see price"})
    tstrats = (timer_status or {}).get("strategies") or {}
    for name, s in enabled.items():
        status = engine.day_status(name)
        if getattr(s, "kind", "straddle") == "lab":
            # the runner stopped its day (2026-10-19: no sandbox on the VPS, both strategies silent all day while the
            # desk said ready): a problem is bad, the owner's own stop or kill only a warning
            said = lab.runner_said(name) if lab is not None else None
            if said and said.get("state") == "stopped":
                why = said.get("why") or "no reason given"
                checks.append({"level": "warn" if why in ("Stopped for today.", "Killed today.") else "bad",
                               "label": shown(name), "detail": "stopped for the day — " + why})
                continue
            # booked after its session opened (2026-10-21: two accounts booked at 09:05 / 09:08 and nothing traded
            # all day while the desk said ready): the runner changes the day over as soon as the strategy has no open
            # trade or order on paper, so this only shows while it has one
            if said and said.get("mode") == "shadow" and config_mod.assignments(cfg, name):
                checks.append({"level": "warn", "label": shown(name),
                               "detail": "booked after today's session opened — starts sending orders as soon as "
                                         "it has no open trade or order"})
                continue
            if status != "idle":
                checks.append({"level": "ok", "label": shown(name), "detail": status})
            continue                     # no trade by its last-entry time is a normal day for a Lab strategy
        h, m = s.accept_until_et.split(":")
        after_window = now_et.time() > dt.time(int(h), int(m))
        if getattr(s, "kind", "straddle") == "bars":
            if status != "idle":
                checks.append({"level": "ok", "label": shown(name), "detail": status})
            continue                     # a rule with no setup today is normal
        if getattr(s, "kind", "straddle") == "levels":
            if status != "idle":
                checks.append({"level": "ok", "label": shown(name), "detail": status})
            continue                     # leveltimer journals every fire / skip / miss with its why
        # from the open, a self-fire straddle's own timer says what its day was
        # (09:21-09:30 has its own check above)
        told = (_timer_day(tstrats.get(name), status, s, cfg.armed)
                if weekday and getattr(s, "self_fire", False) and now_et.time() >= fire_time(s)
                else None)
        if told is not None:
            checks.append({"level": told[0], "label": shown(name), "detail": told[1]})
        elif weekday and after_window and status == "idle":
            if s.gated:
                checks.append({"level": "warn", "label": shown(name),
                               "detail": "no signal today — gated day (expected) "
                                         "or the pipe is broken"})
            else:
                checks.append({"level": "bad", "label": shown(name),
                               "detail": "no signal arrived — this strategy "
                                         "trades every day"})
        elif status != "idle":
            checks.append({"level": "ok", "label": shown(name), "detail": status})
    lab_line = labdesk_mod.readiness_line(cfg)   # only on a desk that reads another desk's Lab store
    if lab_line is not None:
        checks.append(lab_line)
    lab_line = labdesk_mod.orphan_line(cfg, engine)   # only when a Lab round is open for a strategy this desk lacks
    if lab_line is not None:
        checks.append(lab_line)
    if cfg.armed:
        checks.append({"level": "info", "label": "Mode",
                       "detail": "ARMED — signals place real orders"})
    else:
        # disarmed with a live book on a weekday = the algo will NOT trade
        checks.append({"level": "warn" if (weekday and live_strats) else "info",
                       "label": "Mode",
                       "detail": ("DISARMED — " + ", ".join(live_strats) +
                                  " will journal only, no orders")
                       if (weekday and live_strats)
                       else "shadow — signals journal only"})
    return {"ready": not any(c["level"] == "bad" for c in checks),
            "checks": checks}


def should_fire_readiness(now_et, fired_date: str | None) -> bool:
    if now_et.weekday() >= 5 or fired_date == now_et.date().isoformat():
        return False
    t = now_et.time()
    return t.hour == READINESS_FROM[0] and t.minute >= READINESS_FROM[1]
