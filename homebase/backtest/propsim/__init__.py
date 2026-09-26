"""Prop-eval pass rate for a tester run: the vendored ONYX Monte Carlo over the run's daily net P&L.

Vendored (do not edit — re-vendor):
  propsim.py                          <- ONYX TRADING onyx/report/propsim.py (header: source + sha256)
  rules/lucid-flex-50k@2026-08.json   <- onyx/report/rules/ @ 0a75af5, shipped as is (confirmed by
                                         the account holder 2026-08-01)
Homebase's own:
  rules/apex-50k@unconfirmed.json     PLACEHOLDER numbers copied from LucidFlex, "confirmed": false.

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
DEFAULT_RULES = "lucid-flex-50k@2026-08"
N_PATHS, HORIZON, SEED = 20_000, 250, 20260801        # the notebook's defaults
CAVEAT = ("Days are drawn independently: streaks and regime clustering are not modeled, "
          "so read these rates as the friendly end of the band.")
_ID = re.compile(r"^[a-z0-9-]+@[a-z0-9-]+$")


def list_rules() -> list[dict]:
    out = []
    for p in sorted(RULES_DIR.glob("*.json")):
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
    pnls, flags, dates = weekday_grid(trades)
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
