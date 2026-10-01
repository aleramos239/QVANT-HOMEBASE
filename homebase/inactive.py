"""A booked strategy must never silently do nothing.

An enabled strategy with accounts booked either trades today or says, once, why it will not:
the journal event `inactive_today` (strategy, code, reason) and a readiness line.  Two sources:

  static_reason(...)  what is knowable before its time -- not scheduled today (only_dates), not
                      self-fired, a half day, a rule that does not exist, every booked account sitting
                      out (open-loss rule not acknowledged, no prop block for target_take);
  engine.note_inactive  what only the day itself knows -- no ATR data, a roll between stage and fire,
                      a missed window, every account sat out at the fire, a bar rule that gave no
                      signal in its window (sweep, below).

Journaled once per (date, strategy, code); a restart reads today's journal and does not repeat.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

from .config import AppCfg, assignments
from .levels import SHAPES, is_early_close_skip
from .rules import RULES

EVENT = "inactive_today"


def _acct_reason(cfg: AppCfg, engine, name: str, s, aid: str) -> Optional[str]:
    """Why a booked account sits a levels strategy out for the whole day, when that is knowable."""
    acct = cfg.accounts.get(aid)
    if not s.ack_open_loss and not (acct is not None and acct.paper):
        return "open-loss rule not acknowledged (ack_open_loss)"
    rules = engine.rules_for(aid) if engine is not None else None
    if rules is not None and rules.target_take and not rules.day_take:
        prop = dict(getattr(acct, "prop", None) or {})
        if prop.get("start_balance") is None or not prop.get("rules") or prop.get("mode", "eval") != "eval":
            return "no prop block (start_balance / rules / eval mode) for target_take"
    return None


def static_reason(cfg: AppCfg, engine, name: str, s, date: dt.date) -> Optional[tuple[str, str]]:
    """(code, why) when an enabled, booked strategy will not trade on `date`, else None.  Unbooked or
    disabled strategies are not asked: nothing is expected of them."""
    if not s.enabled:
        return None
    book = assignments(cfg, name)
    if not book:
        return None
    if not s.trades_on(date):
        return "not_scheduled_today", "trades only on " + ", ".join(str(d) for d in s.only_dates)
    kind = getattr(s, "kind", "straddle")
    if not getattr(s, "self_fire", False):
        return "not_self_fire", "self_fire is off and nothing else fires it"
    if kind == "bars" and s.rule not in RULES:
        return "unknown_rule", f"rule {s.rule!r} does not exist"
    if kind == "levels":
        if s.shape not in SHAPES:
            return "bad_shape", f"unknown shape {s.shape!r}"
        if s.skip_early_close and is_early_close_skip(s.symbol, date, s.flat_et):
            return "early_close", f"half day: the market closes before its {s.flat_et} flat"
        why = {a["account"]: _acct_reason(cfg, engine, name, s, a["account"]) for a in book}
        if all(why.values()):
            return "every_account_sits_out", "; ".join(sorted({f"{k}: {v}" for k, v in why.items()}))
    return None


def sweep(cfg: AppCfg, engine, now_et: dt.datetime) -> list[tuple[str, str, str]]:
    """Weekdays: journal today's static reasons (once each), and, for bar rules, that the accept window
    closed with no signal.  Returns what was newly journaled."""
    if now_et.weekday() >= 5:
        return []
    date, out = now_et.date(), []
    for name, s in cfg.strategies.items():
        got = static_reason(cfg, engine, name, s, date)
        if got is None and s.enabled and getattr(s, "kind", "") == "bars" and s.rule in RULES \
                and assignments(cfg, name) and not getattr(s, "shadow", False) \
                and now_et.time() > _hhmm(s.accept_until_et) and engine.day_status(name) == "idle" \
                and not engine.signalled_today(name):
            got = "no_signal", f"its rule gave no signal in the {s.accept_from_et}-{s.accept_until_et} window"
        if got and engine.note_inactive(name, got[0], got[1], source="sweep"):
            out.append((name, *got))
    return out


def _hhmm(t: str) -> dt.time:
    h, m = t.split(":")[:2]
    return dt.time(int(h), int(m))
