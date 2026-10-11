"""Prop-eval pass rate for a tester run: the vendored ONYX Monte Carlo over the run's daily net P&L.

Vendored (see its header before editing):
  propsim.py                             <- ONYX TRADING onyx/report/propsim.py, with a deliberate
                                            local divergence (null consistency, default ruleset)
Rulesets — one FAMILY per eval the account holder runs, newest version per family is
what the picker offers; older snapshots stay on disk and stay loadable so a past run
reproduces:
  rules/*@2026-10-11.json                the prop audit's corrections, each from the firm's own
                                         pages (the URLs are in its "source"): LucidPro's OWN
                                         payout rule (buffer + 40% consistency, no winning days),
                                         LucidFlex's $500 minimum request and $2,000 cap, Apex EOD's
                                         30 days and payout rule, and the Apex Legacy files
                                         renamed for what they are (the holder's end-of-day
                                         reading; Apex trails the intraday high).
                                         lucid-flex-50k@2026-10-11 is the DEFAULT.
  rules/lucid-flex-50k@2026-09-27.json   superseded 2026-10-11 (the pipeline's book still names
                                         it). 50% consistency ON TOP OF a 2-day
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
  (Topstep: REMOVED 2026-10-11 on the account holder's word, "remove topstep for now". The
   2026-09-27b file was a copy of LucidFlex; Topstep's own rules -- 55% consistency, the floor
   locking at $50,000, a funded account that starts at 2 lots -- are in git history as
   topstep-50k@2026-10-11.json, unconfirmed.)
  rules/apex-legacy-50k@2026-09-27b.json $3,000 / $2,000 EOD trail locking at +$100, no
                                         consistency, 1 day, 10 minis.
  rules/apex-eod-50k@2026-09-27b.json    the same plus a SOFT $1,000 daily limit, 6 minis.
                                         Both Apex files: payout terms are placeholders
                                         copied from Flex, "confirmed": false.
  rules/lucid-pro-50k@2026-09-27.json    superseded (no daily limit, all but two numbers
                                         inherited), kept for reproducing older runs.
Apex files carry ONLY numbers the account holder gave (2026-09-27); an
invented number is worse than no file (an earlier Apex placeholder was deleted
2026-09-27).

The model: i.i.d. day bootstrap over the WEEKDAY GRID of the run's daily net P&L —
every Mon–Fri from the first to the last trading session, 0.0 on weekdays without a
trade (so "days" are calendar weekdays, the fee clock) — then the eval race (pass /
bust / timeout, Wilson CI, days to pass) and the funded race (first payout, expected
cheque). A rule file is UNCONFIRMED when it says "confirmed": false; its results carry
confirmed=False and the label "<name> · unconfirmed rules". Every result carries CAVEAT.

AN INTRADAY TRAIL (rule file `trail: "intraday"`: the Apex Legacy files @2026-10-11b): the floor follows the
highest LIVE balance, not the close. `day_trail` gives each day its worst fall from its own running high and
its highest open point, off every trade's mfe_usd / mae_usd; the result says `trail` and, as the careful bound,
`trail_worst_case` (every trade's high before its low). The pipeline's stores keep no high: propodds refuses
such a file.

OPEN LOSSES COUNT (the account holder, 2026-10-02; the tile since 2026-10-11): a ledger whose
trades all carry the engine's `mae_usd` is raced with each day's worst open loss (`day_opens`),
so a day whose worst open point reaches the drawdown floor fails the account whatever it closes
at -- `breach` = BREACH_OPEN, and the friendlier close-only reading is kept beside it as
`close_only`. A ledger without it cannot see inside a day: `breach` = BREACH_CLOSE, and the
caveat says the rate is overstated. The pipeline's simulator (research/edge-library/blueprint/
propodds.py) has always read the open-loss rule; the two now agree on it.
"""
from __future__ import annotations

import datetime as dt
import json
import math
import re
from pathlib import Path

from . import propsim as engine

RULES_DIR = Path(__file__).resolve().parent / "rules"
DEFAULT_RULES = "lucid-flex-50k@2026-10-11"
N_PATHS, HORIZON, SEED = 20_000, 250, 20260801        # the notebook's defaults
CAVEAT = ("Days are drawn independently: streaks and regime clustering are not modeled, "
          "so read these rates as the friendly end of the band.")
BREACH_OPEN, BREACH_CLOSE = "open losses count", "close only"
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


def day_opens(trades: list[dict], dates: list[str], r: dict) -> list[float] | None:
    """Each day's WORST OPEN LOSS in $ (>= 0), aligned with `dates` (weekday_grid's): how far the
    day's P&L, open trades included, stood below its start at the worst point. At every entry:
    [what the trades already closed realised] - [mae_usd + commission of every trade open then];
    a trade is charged its whole MAE for as long as it is open and overlapping trades add theirs
    (conservative; the same walk as research/edge-library library._worst_open, locked to it by
    tests/test_blueprint_propodds.py). Never more than the account's soft daily loss limit: a
    day that reached it was closed there. Trades without entry / exit times are walked one after
    the other in ledger order. None when a trade has no mae_usd: the day cannot be seen into."""
    if any(not _has_mae(t) for t in trades):
        return None
    timed = all(_span(t) is not None for t in trades)
    by: dict[str, list] = {}
    for i, t in enumerate(trades):
        a, b = _span(t) if timed else (i, i)
        by.setdefault(t["date"], []).append((a, b, float(t["net"]), abs(float(t["mae_usd"])) + float(t.get("commission") or 0.0)))
    dll, out = engine._dll(r), []
    for d in dates:
        worst, real, live = 0.0, 0.0, []
        for t in sorted(by.get(d, ()), key=lambda x: (x[0], x[1])):
            for o in [o for o in live if o[1] <= t[0]]:
                real += o[2]
                live.remove(o)
            live.append(t)
            worst = min(worst, real - sum(o[3] for o in live))
        out.append(min(-worst, dll) if dll else -worst + 0.0)
    return out


def day_trail(trades: list[dict], dates: list[str], worst: bool = False) -> list[tuple] | None:
    """Each day's (drop, high) in $ for an account whose floor trails the INTRADAY high (propsim._trail_day),
    aligned with `dates`: drop = the day's worst fall from its own running high, high = its highest open point
    above its start. A trade is three points from where the day stood at its entry: its high (mfe_usd less its
    commission), its low (mae_usd plus it) and its close (net). THE ORDER of high and low inside a trade is not
    on file. The natural reading (the number): a winner made its low first, then its high; a loser its high
    first, then its low -- the old research engine's 'nat'. worst=True: every trade made its high first, so
    its whole fall counts against the lifted floor ('pess': the careful bound). Trades are walked one after
    the other in entry order. None when a trade has no mfe_usd or mae_usd: the day's high cannot be seen."""
    num = lambda v: isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)  # noqa: E731
    if any(not _has_mae(t) or not num(t.get("mfe_usd")) for t in trades):
        return None
    timed = all(_span(t) is not None for t in trades)
    by: dict[str, list] = {}
    for i, t in enumerate(trades):
        by.setdefault(t["date"], []).append((_span(t) if timed else (i, i), t))
    out = []
    for d in dates:
        real = run = drop = 0.0
        for _, t in sorted(by.get(d, ()), key=lambda x: x[0]):
            net, c = float(t["net"]), float(t.get("commission") or 0.0)
            hi, lo = max(abs(float(t["mfe_usd"])) - c, net, 0.0), min(-abs(float(t["mae_usd"])) - c, net, 0.0)
            for e in ((lo, hi, net) if net > 0 and not worst else (hi, lo, net)):
                run = max(run, real + e)
                drop = max(drop, run - (real + e))
            real += net
        out.append((drop, run))
    return out


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
    opens = day_opens(limited, dates, r)
    intraday = r.get("trail") == "intraday"
    trail = day_trail(limited, dates) if intraday and opens is not None else None
    kw = dict(trade_flags=flags, day_opens=opens, rules=r, n_paths=n_paths, horizon=horizon, seed=seed, sweep=(), degradation=())
    res = engine.run(pnls, day_trail=trail, **kw)
    ev, fu = res["eval"], res["funded"]
    if intraday:
        out["trail"] = "intraday" if trail is not None else "closes only"
        if trail is None:
            out["caveat"] += (" This account's floor trails the INTRADAY high, and this ledger has no per-trade open-profit "
                              "high: the floor was trailed on the closes only. The pass rate is OVERSTATED.")
        else:
            hard = engine.run(pnls, day_trail=day_trail(limited, dates, worst=True), **kw)
            out["trail_worst_case"] = {"eval_pass_p": hard["eval"]["p"], "bust_p": hard["eval"]["bust_p"],
                                       "funded_payout_p": hard["funded"]["payout_p"]}
            out["caveat"] += (" The floor trails the intraday high: a winning trade is taken to make its low before its "
                              "high, a losing trade its high before its low (the order is not on file). If every trade "
                              f"made its high first, pass would be about {100 * hard['eval']['p']:.1f}%.")
    if opens is None:
        out["breach"] = BREACH_CLOSE
        out["caveat"] += (" This ledger has no per-trade adverse excursion, so the account is failed only when a "
                          "day CLOSES at the drawdown floor; the firms count open losses. The pass rate is OVERSTATED.")
    else:
        soft = res["close_only"]                  # the friendlier close-only reading of the SAME paths, kept beside the number
        out["breach"] = BREACH_OPEN
        out["close_only"] = {"eval_pass_p": soft["eval_p"], "bust_p": soft["bust_p"], "funded_payout_p": soft["payout_p"],
                             "funded_expected_cheque": soft["expected_payout"]}
        out["caveat"] += (f" Open losses count: a day whose worst open point reaches the drawdown floor fails the "
                          f"account. Failing it only on a day's close (the old reading) would say pass "
                          f"{100 * soft['eval_p']:.1f}%.")
    return {**out,
            "grid": {"first": dates[0], "last": dates[-1], "weekdays": len(pnls),
                     "trade_days": sum(flags)},
            "headline": {"eval_pass_p": ev["p"], "eval_pass_ci": ev["ci"], "bust_p": ev["bust_p"],
                         "timeout_p": ev["timeout_p"], "median_days_to_pass": ev["days"]["median"],
                         "funded_payout_p": fu["payout_p"],
                         "funded_expected_cheque": fu["expected_payout"]},
            "result": {k: res[k] for k in ("series", "eval", "retries", "funded")}}
