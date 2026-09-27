"""Prop-eval pass rate for a tester run: the vendored ONYX Monte Carlo over the run's daily net P&L.

Vendored (see its header before editing):
  propsim.py                             <- ONYX TRADING onyx/report/propsim.py, with a deliberate
                                            local divergence (null consistency, default ruleset)
Rulesets — one FAMILY per eval the account holder runs, newest version per family is
what the picker offers; older snapshots stay on disk and stay loadable so a past run
reproduces:
  rules/lucid-flex-50k@2026-09-27.json   the DEFAULT. 50% consistency ON TOP OF a 2-day
                                         minimum (account holder, reaffirmed 2026-09-27);
                                         the numbers are 2026-08's, unchanged.
  rules/lucid-flex-50k@2026-08.json      superseded, kept for reproducing older runs.
  rules/lucid-pro-50k@2026-09-27b.json   LucidPro: no consistency rule, no minimum days,
                                         a SOFT $1,200 daily loss limit; every number
                                         confirmed by the account holder (2026-09-27),
                                         including the lock, EOD trailing and payout
                                         terms it shares with Flex.
  rules/lucid-pro-50k-no-dll@2026-09-27b.json  the same account with the daily limit
                                         removed (an option Lucid offers).
  rules/lucid-flex-50k-dll@2026-09-27b.json  Flex plus a SOFT $1,200 daily limit.
  rules/topstep-50k@2026-09-27b.json     Flex rules, no daily limit, 5-mini cap.
  rules/apex-legacy-50k@2026-09-27b.json $3,000 / $2,000 EOD trail locking at +$100, no
                                         consistency, 1 day, 10 minis.
  rules/apex-eod-50k@2026-09-27b.json    the same plus a SOFT $1,000 daily limit, 6 minis.
                                         Both Apex files: payout terms are placeholders
                                         copied from Flex, "confirmed": false.
  rules/lucid-pro-50k@2026-09-27.json    superseded (no daily limit, all but two numbers
                                         inherited), kept for reproducing older runs.
Apex and Topstep files carry ONLY numbers the account holder gave (2026-09-27); an
invented number is worse than no file (an earlier Apex placeholder was deleted
2026-09-27).

The model: i.i.d. day bootstrap over the WEEKDAY GRID of the run's daily net P&L —
every Mon–Fri from the first to the last trading session, 0.0 on weekdays without a
trade (so "days" are calendar weekdays, the fee clock) — then the eval race (pass /
bust / timeout, Wilson CI, days to pass) and the funded race (first payout, expected
cheque). A rule file is UNCONFIRMED when it says "confirmed": false; its results carry
confirmed=False and the label "<name> · unconfirmed rules". Every result carries CAVEAT.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from pathlib import Path

from . import propsim as engine

RULES_DIR = Path(__file__).resolve().parent / "rules"
DEFAULT_RULES = "lucid-flex-50k@2026-09-27"
N_PATHS, HORIZON, SEED = 20_000, 250, 20260801        # the notebook's defaults
CAVEAT = ("Days are drawn independently: streaks and regime clustering are not modeled, "
          "so read these rates as the friendly end of the band.")
_ID = re.compile(r"^[a-z0-9-]+@[a-z0-9-]+$")


def list_rules() -> list[dict]:
    """The evals offered in the picker: the NEWEST version of each family (the part of
    the id before the ``@``), ordered by family. A superseded snapshot stays on disk and
    `load_rules` still reads it — an old run reproduces — it is just not offered."""
    newest: dict[str, Path] = {}
    for p in sorted(RULES_DIR.glob("*.json")):
        family, _, version = p.stem.partition("@")
        cur = newest.get(family)
        if cur is None or version > cur.stem.partition("@")[2]:
            newest[family] = p
    out = []
    for family in sorted(newest):
        p = newest[family]
        r = json.loads(p.read_text())
        out.append({"id": p.stem, "name": r.get("name", p.stem), "version": r.get("version"),
                    "confirmed": r.get("confirmed") is not False})
    return out


def load_rules(rule_id: str) -> dict:
    p = RULES_DIR / f"{rule_id}.json"
    if not isinstance(rule_id, str) or not _ID.match(rule_id) or not p.is_file():
        ids = ", ".join(r["id"] for r in list_rules())
        raise ValueError(f"prop_rules: one of {ids}")
    return json.loads(p.read_text())


def weekday_grid(trades: list[dict]) -> tuple[list[float], list[bool], list[str]]:
    """(daily net P&L, traded?, session dates): every Mon–Fri from the first to the last
    trading session, plus any weekend session that traded (P&L is never dropped)."""
    by: dict[str, float] = {}
    for t in trades:
        by[t["date"]] = by.get(t["date"], 0.0) + t["net"]
    if not by:
        return [], [], []
    d0, d1 = dt.date.fromisoformat(min(by)), dt.date.fromisoformat(max(by))
    days = {(d0 + dt.timedelta(i)).isoformat() for i in range((d1 - d0).days + 1)
            if (d0 + dt.timedelta(i)).weekday() < 5} | set(by)
    dates = sorted(days)
    return [by.get(d, 0.0) for d in dates], [d in by for d in dates], dates


def _has_mae(t: dict) -> bool:
    v = t.get("mae_usd")
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _span(t: dict) -> tuple | None:
    """(entry, exit) in ns from either ledger form (engine ns, bundle ms), else None."""
    if "entry_ns" in t and "exit_ns" in t:
        return t["entry_ns"], t["exit_ns"]
    if "entry_ms" in t and "exit_ms" in t:
        return t["entry_ms"] * 1_000_000, t["exit_ms"] * 1_000_000
    return None


def overlap_days(trades: list[dict]) -> int:
    """Days on which a position opened before an earlier-listed one had closed. limit_trades
    walks trades one after another, so on those days two open drawdowns are never summed and
    the daily limit can be missed -- evaluate() says so."""
    last_exit, days = {}, set()
    for t in trades:
        sp = _span(t)
        if sp is None:
            continue
        d = t["date"]
        if d in last_exit and sp[0] < last_exit[d]:
            days.add(d)
        last_exit[d] = max(last_exit.get(d, sp[1]), sp[1])
    return len(days)


def _worst(t: dict) -> float:
    """A trade's worst moment in $, net of its commission: -mae_usd - commission (the engine's
    tick-level adverse excursion). A ledger without mae_usd (old runs, bare {date, net}) falls
    back to the closing net -- blind to a dip-then-win, which evaluate() then warns about."""
    net = float(t["net"])
    if not _has_mae(t):
        return net
    mae = t["mae_usd"]
    return min(net, -abs(float(mae)) - float(t.get("commission") or 0.0))


def limit_trades(trades: list[dict], r: dict) -> list[dict]:
    """The ledger as a SOFT daily loss limit leaves it (LucidPro: the moment the day's P&L --
    closed trades plus the open one -- reaches -limit you are closed out and stopped for the
    day; the account survives). Walking each day's trades in ledger order (the engine's is
    by EXIT time), a trade whose WORST moment (``_worst``: its tick-level MAE, so a trade that
    dipped past the limit and then won is caught) takes the day to -limit is closed at exactly
    the limit, marked ``dll_stop``, and the day's later trades are dropped.

    Approximations, both small: the stop fills at exactly -limit (Lucid liquidates at market,
    so a fast market can cost a little more), and two positions open AT THE SAME TIME are
    walked one after the other rather than summed. Null limit: the ledger unchanged."""
    dll = engine._dll(r)
    if not dll:
        return trades
    out, cum, stopped = [], {}, set()
    for t in trades:
        d = t["date"]
        if d in stopped:
            continue
        c = cum.get(d, 0.0)
        if c + _worst(t) <= -dll:
            out.append({**t, "net": -dll - c, "dll_stop": True})
            stopped.add(d)
            continue
        cum[d] = c + float(t["net"])
        out.append(t)
    return out


def evaluate(trades: list[dict], rule_id: str = DEFAULT_RULES, *, n_paths: int = N_PATHS,
             horizon: int = HORIZON, seed: int = SEED, rules: dict | None = None) -> dict:
    """The run's propsim.json. Pass `rules` when the caller already loaded the rule file
    (the runner does, from `validate()`) so it is not read from disk a second time."""
    r = rules if rules is not None else load_rules(rule_id)
    confirmed = r.get("confirmed") is not False
    out = {"rules": {"id": rule_id, "name": r.get("name"), "version": r.get("version"),
                     "confirmed": confirmed,
                     "label": r.get("name") if confirmed else f"{r.get('name')} · unconfirmed rules"},
           "caveat": CAVEAT, "engine": "iid-weekday-bootstrap (IP notebook port)",
           "n_paths": n_paths, "horizon": horizon, "seed": seed}
    dll = engine._dll(r)
    if dll:
        limited = limit_trades(trades, r)
        out["dll_stopped_days"] = sum(1 for t in limited if t.get("dll_stop"))
        # only a ledger WITHOUT the engine's mae_usd is blind to a dip-then-win
        notes = []
        if any(not _has_mae(t) for t in trades):
            notes.append(f"This ledger has no per-trade adverse excursion, so a trade that dipped past the "
                         f"${dll:,.0f} daily limit and then recovered is counted in full.")
        ov = overlap_days(trades)
        if ov:
            out["dll_overlap_days"] = ov
            notes.append(f"On {ov} day(s) positions overlapped; their open losses are not added together, so the "
                         f"${dll:,.0f} daily limit can be missed there.")
        if notes:
            out["caveat"] = f"{CAVEAT} {' '.join(notes)} The pass rate is OVERSTATED."
    else:
        limited = trades
    pnls, flags, dates = weekday_grid(limited)
    if not pnls:
        return {**out, "skipped": "no trades: nothing to simulate"}
    res = engine.run(pnls, trade_flags=flags, rules=r, n_paths=n_paths, horizon=horizon,
                     seed=seed, sweep=(), degradation=())
    ev, fu = res["eval"], res["funded"]
    return {**out,
            "grid": {"first": dates[0], "last": dates[-1], "weekdays": len(pnls),
                     "trade_days": sum(flags)},
            "headline": {"eval_pass_p": ev["p"], "eval_pass_ci": ev["ci"], "bust_p": ev["bust_p"],
                         "timeout_p": ev["timeout_p"], "median_days_to_pass": ev["days"]["median"],
                         "funded_payout_p": fu["payout_p"],
                         "funded_expected_cheque": fu["expected_payout"]},
            "result": {k: res[k] for k in ("series", "eval", "retries", "funded")}}
