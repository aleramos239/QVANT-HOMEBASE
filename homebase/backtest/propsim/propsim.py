# VENDORED from ONYX TRADING onyx/report/propsim.py — untracked in ONYX's git when vendored
# (2026-09-26), sha256 0d480ccd3d67ad034e89674cf7211f129fce27af0a9ac9ba7f82f72f0452cdf0. Stdlib only.
# DIVERGED 2026-09-27, deliberately: `consistency: null` now disables the consistency check
# (LucidPro has no such rule), and the default ruleset is lucid-flex-50k@2026-09-27. ONYX's
# copy carries the same null-handling but also a lucid-flex-50k@2026-09 snapshot claiming Flex
# has NO consistency rule — the account holder WITHDREW that on 2026-09-27, so do NOT re-vendor
# ONYX's rules over homebase's. Re-vendor engine changes only, keeping this divergence.
# DIVERGED 2026-10-11 (the prop audit): a day may carry its WORST OPEN LOSS (open losses count: the
# firms fail an account in real time), the payout rule reads its conditions off the rule file
# (LucidPro's buffer and 40% consistency are not LucidFlex's five winning days), and an eval with
# `max_days` is not raced past them.
"""Monte Carlo over the LucidFlex 50K eval + funded lifecycle.

Port of the Institutional Protocol course's prop-firm notebook engine
(``PropFirm_MonteCarlo_Apex50K_funded_IP_210626.ipynb``, the fixed-v2 copy) —
i.i.d. day bootstrap over a weekday grid — running under OUR LucidFlex rules
instead of Apex. It replaced the 5-layer simulator (``propsim5.py``, deleted
2026-08-14): one sampling model instead of five, in exchange for the notebook's
richer outputs — Wilson CI, drawdown percentiles, cumulative pass across
retries, a position-size sweep, WR/PnL degradation scenarios, and the funded
phase priced in DOLLARS (cheque distribution + expected payout).

THE HEADLINE ASSUMPTION, stated once and echoed on every result: days are drawn
independently. Streaks and regime clustering are NOT modeled — on the ORB
champion the old block/replay layers sat ~5pp below i.i.d., so read every pass
rate here as the friendly end of that band.

THE CLOCK: the sampling pool is the full weekday grid (Mon–Fri, including
0-trade weekdays), so every "days" figure is CALENDAR WEEKDAYS — the desk's fee
clock — not traded sessions.

LUCIDFLEX 50K RULES (account holder 2026-08-01, reaffirmed 2026-09-27; snapshot
in ``rules/lucid-flex-50k@2026-10-11.json``, echoed on every result):

    EVAL    +$3,000 target; $2,000 EOD-trailing max loss which LOCKS at a +$100
            floor once EOD profit reaches +$2,100; 50% consistency (largest
            winning day <= 50% of total profit at the moment of passing, else
            keep trading) ON TOP OF a min 2 trading days; no daily-loss limit;
            no time limit (the sim horizon stands in for "eventually").

LUCIDPRO 50K (``rules/lucid-pro-50k@2026-09-27b.json``) is Flex minus those two
gates — ``consistency: null`` (no check at all) and ``eval_min_days: 1``, so a
single +$3,000 day passes — plus a SOFT $1,200 daily loss limit (hit it and you
are stopped for the day; the account survives). The account holder confirmed
size, target, max loss, the daily limit and max size (4 minis / 40 micros) on
2026-09-27 and that the daily limit can be removed:
``lucid-pro-50k-no-dll@2026-09-27b.json`` is the same account without it. The
lock, EOD trailing and payout terms match Flex; the account holder confirmed the
whole ruleset later the same day, so both files say ``"confirmed": true``. (``lucid-pro-50k@2026-09-27`` -- no daily limit --
stays on disk so older runs reproduce.)
    FUNDED  same $2,000 EOD-trailing max loss locking at +$100. A PAYOUT needs
            5 separate days >= $150 AND net > 0. The cheque is 50% of the
            profit standing when it first qualifies, capped at $2,000 — so the
            MAX payout additionally needs >= $4,000 profit.
            (LUCIDFLEX's. Since 2026-10-11 the payout rule is read off the rule
            file, ``_cheque``: LucidPro pays on a $500 goal, 40% consistency and a
            $2,100 buffer with no winning days -- ``lucid-pro-50k*@2026-10-11``.)

Pure stdlib, seeded, deterministic across processes.
"""
from __future__ import annotations

import json
import math
import os
import random
import statistics
from itertools import chain
from typing import Iterable, List, Optional, Sequence, Tuple

__all__ = ["RULES", "run", "run_eval", "run_funded", "load_rules", "wilson_ci"]

# Deliberately NOT under onyx/propsim/rules/ — that directory is the older
# trade-bootstrap simulator's schema (profit_target / trailing_drawdown /
# daily_loss_limit) and its CLI loads whatever file sorts first. This ruleset
# uses a different, LucidFlex-shaped contract and must not collide with it.
_RULES_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "rules", "lucid-flex-50k@2026-10-11.json")


def load_rules(path: Optional[str] = None) -> dict:
    with open(path or _RULES_PATH, "r") as fh:
        return json.load(fh)


RULES = load_rules()

# Position-size sweep, as multipliers of the ledger's own sizing (x1.0 = as
# backtested). The notebook swept MNQ contract counts; a $-risk ledger has no
# contract axis, so the multiplier IS the size knob.
SWEEP_MULTS = (0.5, 0.75, 1.0, 1.25, 1.5, 2.0)

# The notebook's five what-if-live-is-worse scenarios, verbatim.
DEGRADATION = (
    ("Baseline (backtest as-is)", 0.00, 0.00),
    ("WR -3pp, PnL -10%", -0.03, 0.10),
    ("WR -5pp, PnL -15%", -0.05, 0.15),
    ("WR -5pp, PnL -25% (stress)", -0.05, 0.25),
    ("WR -8pp, PnL -30% (worst)", -0.08, 0.30),
)


def wilson_ci(successes: int, n: int, z: float = 1.96) -> Tuple[float, float]:
    """95% Wilson interval on a proportion — Monte Carlo noise, NOT model risk.

    It shrinks with more paths; the i.i.d. assumption it sits on does not."""
    if n == 0:
        return (0.0, 0.0)
    p = successes / n
    denom = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    margin = (z / denom) * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0.0, center - margin), min(1.0, center + margin))


# --- account mechanics (unchanged from propsim5 — these ARE the rules) -------

def _floor(peak: float, r: dict) -> float:
    """The trailing max-loss line for a given EOD peak profit."""
    return r["lock_floor"] if peak >= r["lock_at"] else peak - r["trailing_mll"]


def _dll(r: dict) -> Optional[float]:
    """The ruleset's daily loss limit in $, or None. Only null/0 (no limit) or a
    positive number is accepted -- a negative one would turn every losing day into a
    win, so it is refused rather than guessed at."""
    v = r.get("daily_loss_limit")
    if v is None or v == 0:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
        raise ValueError(f"daily_loss_limit: null or a positive $ amount, not {v!r}")
    return float(v)


def _cap_day(pnl: float, r: dict) -> float:
    """A SOFT daily loss limit (LucidPro, account holder 2026-09-27): hitting it
    closes you out and stops you for the day -- the account survives. The tester
    applies it at TRADE level first (propsim.limit_trades: the crossing trade is cut
    to the limit, the day's later trades dropped, using each trade's tick-level MAE
    so a dip-then-win is caught); this daily cap is the safety net for callers that
    pass bare daily P&L, which cannot see intraday at all.
    ``daily_loss_limit: null`` = no limit."""
    dll = _dll(r)
    return max(pnl, -dll) if dll else pnl


def _days(path: Iterable) -> Iterable[Tuple[float, bool, float]]:
    """Normalize a path to (pnl, is_trade_day, worst_open_loss) triples. Bare floats
    count a day as traded when its P&L is nonzero — the notebook's own fallback. A day
    without a worst open loss ($ >= 0: how far the day stood below its start at its
    worst point, open trades included) has 0: it can only fail the account on its close."""
    for d in path:
        if isinstance(d, tuple):
            yield d if len(d) == 3 else (d[0], d[1], 0.0)
        else:
            yield (d, d != 0.0, 0.0)


def _cheque(profit: float, win_days: int, big: float, r: dict) -> Optional[float]:
    """The payout that can be requested at this close in $, or None. Every condition is the
    rule file's own, and one it does not name is not asked:
      payout_win_days      that many days of `win_day` $ or more (LucidFlex: 5 of $150)
      payout_min_profit    the profit goal of the cycle (LucidPro: $500)
      payout_consistency   the largest day <= this share of the profit (LucidPro: 40%)
      payout_buffer        paid only from the profit above it (LucidPro: $2,100); without
                           one the cheque is `payout_share` of the profit (LucidFlex: 50%)
      payout_cap           the most one request pays; payout_min the least it may ask for
    Net profit above $0 is always needed."""
    if profit <= 0 or win_days < (r.get("payout_win_days") or 0):
        return None
    if profit < (r.get("payout_min_profit") or 0):
        return None
    cons = r.get("payout_consistency")
    if cons is not None and big > cons * profit:
        return None
    buf = r.get("payout_buffer")
    amt = min(profit - buf if buf is not None else r["payout_share"] * profit, r["payout_cap"])
    return amt if amt > 0 and amt >= (r.get("payout_min") or 0) else None


def run_eval(path: Iterable, r: dict) -> dict:
    """Race one eval attempt. ``path`` yields daily P&L floats, ``(pnl, is_trade_day)``
    pairs or ``(pnl, is_trade_day, worst_open_loss)`` triples; exhausting it without a
    verdict is a ``timeout`` (LucidFlex has no time limit — the horizon stands in).

    OPEN LOSSES COUNT: a day whose worst open point -- the profit it started with minus its
    worst open loss -- is at or under the floor in force is a bust, whatever it closes at.

    -> {outcome: "pass"|"bust"|"timeout", day, trade_days, max_dd}

    The three outcomes are MUTUALLY EXCLUSIVE and partition every path: an
    attempt that passes on day 13 is not also a bust because it would have
    breached on day 40 had it kept trading — that account was already funded.

    ``max_dd`` is the worst EOD drawdown from the EOD peak, recorded for every
    path (the notebook's DD-percentile input, and the live kill-table yardstick).
    """
    profit, peak, floor = 0.0, 0.0, -r["trailing_mll"]
    largest_win_day, trade_days, max_dd, day = 0.0, 0, 0.0, 0
    for pnl, traded, opn in _days(path):
        pnl = _cap_day(pnl, r)
        day += 1
        if traded:
            trade_days += 1
        if opn > 0 and profit - opn <= floor:
            return dict(outcome="bust", day=day, trade_days=trade_days,
                        max_dd=max(max_dd, peak - profit + opn))
        profit += pnl
        largest_win_day = max(largest_win_day, pnl)
        max_dd = max(max_dd, peak - profit)
        if profit <= floor:
            return dict(outcome="bust", day=day, trade_days=trade_days,
                        max_dd=max_dd)
        if profit > peak:
            peak = profit
            floor = _floor(peak, r)
        # `consistency: null` = the account has no consistency rule (LucidPro);
        # a number is the cap on the largest winning day's share of the profit.
        consistency = r.get("consistency")
        if (profit >= r["eval_target"] and trade_days >= r["eval_min_days"]
                and (consistency is None
                     or largest_win_day <= consistency * profit)):
            return dict(outcome="pass", day=day, trade_days=trade_days,
                        max_dd=max_dd)
    return dict(outcome="timeout", day=day, trade_days=trade_days,
                max_dd=max_dd)


def run_funded(path: Iterable, r: dict) -> dict:
    """Race one funded account from a flat start — first payout only.

    -> {payout_at, cheque, max_payout_at, bust_at}  (None where not reached)

    ``cheque`` is sized on the profit standing when the payout FIRST becomes
    claimable (``_cheque``: the rule file's own conditions). A later monster day
    changes nothing — the cheque was already sized. An account can take a payout
    and bust later, so payout and bust are NOT exclusive. Open losses count, as
    in ``run_eval``.
    """
    profit, peak, floor = 0.0, 0.0, -r["trailing_mll"]
    win_days, day, big = 0, 0, 0.0
    payout_at = max_at = bust_at = None
    cheque = None
    win_day = r.get("win_day")
    for pnl, _, opn in _days(path):
        pnl = _cap_day(pnl, r)
        day += 1
        if opn > 0 and profit - opn <= floor:
            bust_at = day
            break
        profit += pnl
        big = max(big, pnl)
        if win_day is not None and pnl >= win_day:
            win_days += 1
        if profit <= floor:
            bust_at = day
            break
        if profit > peak:
            peak = profit
            floor = _floor(peak, r)
        due = _cheque(profit, win_days, big, r)
        if payout_at is None and due is not None:
            payout_at = day
            cheque = due
        if due is not None and profit >= r["max_payout_profit"]:
            max_at = day
            break
    return dict(payout_at=payout_at, cheque=cheque, max_payout_at=max_at,
                bust_at=bust_at)


# --- sampling & degradation --------------------------------------------------

def _draws(pnls: Sequence[float], flags: Sequence[bool],
           rng: random.Random, horizon: int, opens: Optional[Sequence[float]] = None):
    """One simulated attempt: ``horizon`` i.i.d. draws from the weekday pool (a day is
    drawn whole: its P&L, whether it traded, and its worst open loss where given)."""
    n = len(pnls)
    for _ in range(horizon):
        i = rng.randrange(n)
        yield (pnls[i], flags[i]) if opens is None else (pnls[i], flags[i], opens[i])


def _seen(days: Iterable, keep: list) -> Iterable:
    """`days`, remembering in `keep` the ones a walk actually took."""
    for d in days:
        keep.append(d)
        yield d


def degrade(pnls: Sequence[float], flags: Sequence[bool], wr_adj: float,
            pnl_shrink: float, deg_seed: int = 20240101) -> List[float]:
    """The notebook's fixed-v2 degradation, day-level:

    * ``pnl_shrink`` shrinks WINNING days only — it degrades the edge without
      shrinking drawdowns (the original shrank losses too, flattering stress).
    * ``wr_adj`` flips ``round(|adj| * n_trade_days)`` winning days to values
      SAMPLED from the losing-day distribution (variance preserved).
    * Its own RNG (``deg_seed``), so the sim stream is identical across
      scenarios — common random numbers make the comparison fair.
    """
    pool = list(pnls)
    rng = random.Random(deg_seed)
    if pnl_shrink > 0:
        pool = [p * (1.0 - pnl_shrink) if p > 0 else p for p in pool]
    if wr_adj < 0:
        wins = [i for i, p in enumerate(pool) if p > 0]
        losses = [p for p in pool if p < 0]
        n_flip = min(int(round(abs(wr_adj) * sum(flags))), len(wins))
        if n_flip > 0:
            mean = sum(pool) / len(pool)
            for i in rng.sample(wins, n_flip):
                pool[i] = rng.choice(losses) if losses else -abs(mean)
    return pool


# --- summarizing -------------------------------------------------------------

def _pct(sorted_xs: Sequence[float], q: float) -> Optional[float]:
    """q-quantile (0..1) of an already-sorted list, linear interpolation."""
    if not sorted_xs:
        return None
    if len(sorted_xs) == 1:
        return sorted_xs[0]
    pos = q * (len(sorted_xs) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_xs) - 1)
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (pos - lo)


def _timing(days: List[int]) -> dict:
    """Timing among the paths that got there — CONDITIONAL, like the notebook's
    'avg days to pass'. Quoting it without its `p` overstates things."""
    if not days:
        return {"mean": None, "median": None, "min": None, "max": None}
    return {"mean": statistics.mean(days), "median": statistics.median(days),
            "min": min(days), "max": max(days)}


def _simulate(pnls: Sequence[float], flags: Sequence[bool], r: dict, *,
              n_paths: int, horizon: int, rng: random.Random,
              opens: Optional[Sequence[float]] = None) -> dict:
    """Race ``n_paths`` eval attempts and funded accounts; return both blocks.
    Eval and funded draw their own streams, notebook-style. An eval with its own
    ``max_days`` (Apex EOD: 30 calendar days) is raced for those days at most.

    With ``opens`` (open losses count) every path is ALSO walked on the close alone --
    the same days, and past where the open-loss walk ended its own further draws from a
    stream of its own, so the main stream is untouched: ``close_only`` is the friendlier
    reading of the very same paths, never below the number it stands beside."""
    eval_days = min(horizon, int(r.get("max_days") or horizon))
    soft_rng, s_pass, s_bust, s_pay, s_cheques = random.Random(20261011), 0, 0, 0, 0.0
    ev_out: List[str] = []
    ev_days: List[int] = []
    ev_tdays: List[int] = []
    bust_days: List[int] = []
    dds: List[float] = []
    pay_days: List[int] = []
    max_days: List[int] = []
    fbust_days: List[int] = []
    cheques: List[float] = []
    n_payout = n_max = n_fbust = n_neither = 0
    for _ in range(n_paths):
        seen_e: list = []
        seen_f: list = []
        days = _draws(pnls, flags, rng, eval_days, opens)
        e = run_eval(days if opens is None else _seen(days, seen_e), r)
        ev_out.append(e["outcome"])
        dds.append(e["max_dd"])
        if e["outcome"] == "pass":
            ev_days.append(e["day"])
            ev_tdays.append(e["trade_days"])
        elif e["outcome"] == "bust":
            bust_days.append(e["day"])
        days = _draws(pnls, flags, rng, horizon, opens)
        f = run_funded(days if opens is None else _seen(days, seen_f), r)
        if opens is not None:
            es = run_eval(chain((d[:2] for d in seen_e), _draws(pnls, flags, soft_rng, eval_days - len(seen_e))), r)
            fs = run_funded(chain((d[:2] for d in seen_f), _draws(pnls, flags, soft_rng, horizon - len(seen_f))), r)
            s_pass += es["outcome"] == "pass"
            s_bust += es["outcome"] == "bust"
            if fs["payout_at"] is not None:
                s_pay += 1
                s_cheques += fs["cheque"]
        if f["payout_at"] is not None:
            n_payout += 1
            pay_days.append(f["payout_at"])
            cheques.append(f["cheque"])
        if f["max_payout_at"] is not None:
            n_max += 1
            max_days.append(f["max_payout_at"])
        if f["bust_at"] is not None:
            n_fbust += 1
            fbust_days.append(f["bust_at"])
        if f["payout_at"] is None and f["bust_at"] is None:
            n_neither += 1

    n = n_paths
    n_pass = sum(1 for o in ev_out if o == "pass")
    n_bust = sum(1 for o in ev_out if o == "bust")
    dds.sort()
    cheq = sorted(cheques)
    p = n_pass / n
    return {
        **({} if opens is None else {"close_only": {"eval_p": s_pass / n, "bust_p": s_bust / n, "payout_p": s_pay / n,
                                                    "expected_payout": s_cheques / n}}),
        "eval": {
            "p": p,
            "ci": list(wilson_ci(n_pass, n)),
            "bust_p": n_bust / n,
            "timeout_p": (n - n_pass - n_bust) / n,
            "days": _timing(ev_days),
            "trade_days_mean": statistics.mean(ev_tdays) if ev_tdays else None,
            "bust_days": _timing(bust_days),
            "dd": {"mean": statistics.mean(dds), "p50": _pct(dds, 0.50),
                   "p90": _pct(dds, 0.90), "p95": _pct(dds, 0.95),
                   "worst": dds[-1]},
        },
        # The fee-spend numbers: E[evals to pass] and P(pass at least once in
        # N attempts) — the geometric draw the eval fee is buying tickets to.
        "retries": {
            "expected": (1.0 / p) if p > 0 else None,
            "cum": [[k, 1.0 - (1.0 - p) ** k] for k in (1, 2, 3, 4)],
        },
        "funded": {
            "payout_p": n_payout / n,
            "ci": list(wilson_ci(n_payout, n)),
            "bust_p": n_fbust / n,
            # payout and bust are NOT exclusive (an account can take a cheque
            # then die); neither = no payout AND no bust by the horizon.
            "neither_p": n_neither / n,
            "days": _timing(pay_days),
            "bust_days": _timing(fbust_days),
            "max_payout_p": n_max / n,
            "max_payout_days": _timing(max_days),
            # Cheque sizes among the paths that reached a payout; the $2k cap
            # binding (capped_share) means the account left money on the table.
            "payout_usd": {
                "n": len(cheq),
                "mean": statistics.mean(cheq) if cheq else None,
                "median": statistics.median(cheq) if cheq else None,
                "p10": _pct(cheq, 0.10), "p90": _pct(cheq, 0.90),
                "min": cheq[0] if cheq else None,
                "max": cheq[-1] if cheq else None,
                "capped_share": (sum(1 for c in cheq if c >= r["payout_cap"]
                                     - 1e-6) / len(cheq)) if cheq else 0.0,
            },
            # Unconditional: cheque averaged over ALL paths, zeros included —
            # the notebook's E[payout], the number that prices the wrapper.
            "expected_payout": sum(cheques) / n,
        },
    }


def run(
    day_pnls: Sequence[float],
    *,
    trade_flags: Optional[Sequence[bool]] = None,
    day_opens: Optional[Sequence[float]] = None,
    rules: Optional[dict] = None,
    n_paths: int = 20000,
    horizon: int = 250,
    seed: int = 20260801,
    sweep: Sequence[float] = SWEEP_MULTS,
    sweep_paths: int = 5000,
    degradation: Sequence[Tuple[str, float, float]] = DEGRADATION,
) -> dict:
    """Race a daily-USD series through the eval + funded lifecycle.

    ``day_pnls`` should be the full weekday grid (0.0 on no-trade weekdays)
    with ``trade_flags`` marking real trading days — ``ledger.weekday_grid``
    builds both. A bare active-days list also works (every day counts as
    traded); its clock is then sessions, not calendar. ``day_opens`` = each day's
    worst open loss in $ (>= 0): with it OPEN LOSSES COUNT (``run_eval``); without
    it an account fails only on a day's close, the friendlier reading.

    Pass ``sweep=()`` / ``degradation=()`` to skip those blocks (the web
    endpoints do — they only need the headline).
    """
    r = dict(rules or RULES)
    if not day_pnls:
        raise ValueError("no daily P&L — the ledger produced zero trading days")
    pnls = [float(p) for p in day_pnls]
    flags = (list(trade_flags) if trade_flags is not None
             else [p != 0.0 for p in pnls])
    if len(flags) != len(pnls):
        raise ValueError("trade_flags must align with day_pnls (%d != %d)"
                         % (len(flags), len(pnls)))
    opens = None if day_opens is None else [float(o) for o in day_opens]
    if opens is not None and len(opens) != len(pnls):
        raise ValueError("day_opens must align with day_pnls (%d != %d)"
                         % (len(opens), len(pnls)))

    main = _simulate(pnls, flags, r, n_paths=n_paths, horizon=horizon,
                     rng=random.Random(seed), opens=opens)

    sweep_rows = []
    for mult in sweep:
        s = _simulate([p * mult for p in pnls], flags, r, n_paths=sweep_paths,
                      horizon=horizon, rng=random.Random(seed + 1),
                      opens=None if opens is None else [o * mult for o in opens])
        sweep_rows.append({
            "mult": mult,
            "eval_p": s["eval"]["p"], "eval_ci": s["eval"]["ci"],
            "bust_p": s["eval"]["bust_p"],
            "dd_mean": s["eval"]["dd"]["mean"],
            "days_mean": s["eval"]["days"]["mean"],
            "payout_p": s["funded"]["payout_p"],
            "funded_bust_p": s["funded"]["bust_p"],
            "expected_payout": s["funded"]["expected_payout"],
        })

    deg_rows = []
    for label, wr_adj, shrink in degradation:
        pool = degrade(pnls, flags, wr_adj, shrink)
        d = _simulate(pool, flags, r, n_paths=sweep_paths, horizon=horizon,
                      rng=random.Random(seed + 2), opens=opens)   # same stream per scenario
        deg_rows.append({
            "label": label, "wr_adj": wr_adj, "pnl_shrink": shrink,
            "eval_p": d["eval"]["p"], "eval_ci": d["eval"]["ci"],
            "bust_p": d["eval"]["bust_p"],
            "payout_p": d["funded"]["payout_p"],
            "expected_payout": d["funded"]["expected_payout"],
        })

    trade_pnls = [p for p, f in zip(pnls, flags) if f]
    n_trade = len(trade_pnls) or 1
    return {
        "rules": r,
        "engine": "iid-weekday-bootstrap (IP notebook port)",
        "n_paths": n_paths,
        "horizon": horizon,
        "seed": seed,
        "series": {
            # Trader-facing stats speak in TRADE days; the sim samples weekdays.
            "n_days": len(trade_pnls),
            "n_weekdays": len(pnls),
            "active_share": len(trade_pnls) / (len(pnls) or 1),
            "mean_day": (sum(trade_pnls) / n_trade) if trade_pnls else 0.0,
            "median_day": statistics.median(trade_pnls) if trade_pnls else 0.0,
            "worst_day": min(trade_pnls) if trade_pnls else 0.0,
            "best_day": max(trade_pnls) if trade_pnls else 0.0,
            "win_day_rate": (sum(1 for x in trade_pnls if x >= r["win_day"]) / n_trade
                             if r.get("win_day") is not None else None),
            "positive_day_rate": sum(1 for x in trade_pnls if x > 0) / n_trade,
        },
        "eval": main["eval"],
        "retries": main["retries"],
        "funded": main["funded"],
        **({"close_only": main["close_only"]} if "close_only" in main else {}),
        "sweep": sweep_rows,
        "degradation": deg_rows,
    }
