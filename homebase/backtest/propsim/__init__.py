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
                                         a SOFT $1,200 daily loss limit; size/target/max
                                         loss/limit/max size from the account holder
                                         (2026-09-27); lock, EOD trailing and payout terms
                                         INHERITED from Flex, "confirmed": false.
  rules/lucid-pro-50k-no-dll@2026-09-27b.json  the same account with the daily limit
                                         removed (an option Lucid offers).
  rules/lucid-pro-50k@2026-09-27.json    superseded (no daily limit, all but two numbers
                                         inherited), kept for reproducing older runs.
There is deliberately NO Apex file: the account holder maps other accounts onto Flex or
Pro, and a file of invented numbers is worse than no file (the placeholder was deleted
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


def limit_trades(trades: list[dict], r: dict) -> list[dict]:
    """The ledger as a SOFT daily loss limit leaves it (LucidPro: hit the limit and you are
    closed out and stopped for the day; the account survives). Walking each day's trades in
    ledger order, the trade that takes the day's running P&L to -limit is cut to exactly the
    limit and the day's later trades are dropped. Null limit: the ledger unchanged. What it
    still cannot see is a trade that dipped past the limit INTRADE and then won -- evaluate()
    warns about those."""
    dll = engine._dll(r)
    if not dll:
        return trades
    out, cum, stopped = [], {}, set()
    for t in trades:
        d = t["date"]
        if d in stopped:
            continue
        c, x = cum.get(d, 0.0), float(t["net"])
        if c + x <= -dll:
            out.append({**t, "net": -dll - c})
            stopped.add(d)
            continue
        cum[d] = c + x
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
        over = sum(1 for t in trades if float(t.get("net", 0.0)) < -dll)
        out["dll_trades_over"] = over
        if over:
            out["caveat"] = (f"{CAVEAT} {over} trade(s) lost more than the ${dll:,.0f} daily limit on their own: "
                             "they are cut to the limit here, but a trade that dipped past it before winning is still "
                             "counted as a win, so this pass rate is OVERSTATED.")
    pnls, flags, dates = weekday_grid(limit_trades(trades, r))
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
