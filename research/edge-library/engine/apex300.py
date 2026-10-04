"""Apex Legacy 300K Performance Account (PA, funded) lifecycle simulator + compliance gate. Rules + sources: APEX300_RULES.md.

Run with "~/ONYX TRADING/.venv/bin/python" or /usr/bin/python3 (numpy). Reuses R = ../2026-09-29 by IMPORT (never edited):
the day walk with the MAE cut + intraday event orders (`funded.walk_day`, `funded.DaySrc`), the metrics (`funded.metrics`),
the grid helpers (`add_stability`, `pick_cells`, `write_csv`) and evalcore's portfolio builder.
Only the account loop is re-implemented here (`_sim`): R's `_sim_apex` always starts from a fresh account and knows none of the
extended options. With the R-compatible readings (`make_spec(firm, **r_compat(firm))`) and a fresh start `_sim` is bit-identical
to R's loop (tests/test_apex300.py checks every attempt tuple on random portfolios, all three event orders, every policy).

ROUTING. The spec is a funded.Spec of kind 'apex' with ext=True. score.py sends every ext spec to THIS module
(`apex300.lifecycle` / `apex300.search` / `apex300.compliance`). Never hand an ext spec to R/funded.lifecycle or funded.search:
R's loop silently ignores the start state, trail='eod', post_req_min, post_cap_net and the Apex commission schedule.

FIRMS (make_spec)
  apex300_pa  Apex Legacy 300K PA. Trailing threshold $7,500 INTRADAY on equity incl. open P&L (peak unrealised balance), the
              floor stops at start + $100 once the peak reaches +$7,600 (safety net). 35 minis = 350 micros; HALF until the EOD
              profit exceeds $7,600, then full size from the next session, for good. Half = 170 micros (17 minis: 17.5 rounded
              DOWN, the conservative reading; variant 'half_175'). No daily loss limit.
              MAE rule: an open loss of max(30% x start-of-day profit, 30% x $7,500 = $2,250) [50% once the start-of-day profit
              >= 2 x safety net = $15,200] is a violation -> modelled as a FORCED CUT at that loss (-1 tick, commission), counted.
              Payout per cycle: >= 8 traded days, >= 5 of them >= $50, largest day <= 30% of the profit (payouts 1-5).
              CONSISTENCY BASE (unconfirmed): default 'cycle' = profit since the last approved payout (conservative, the
              selection default); 'balance' = balance - start (the worked example on the Apex pages). BOTH are always reported
              (`cons_alt` of evaluate_funded, `*_cons_<other>` columns of search).
              Payouts 1-3: balance after the payout >= start + $7,100 (cheque = min($3,500, profit - 7,100) >= $500, so the
              request needs profit >= $7,600). PAYOUTS 4+ (unconfirmed): conservative default = the $307,600 minimum required
              balance is needed for every request AND must remain in the account after the payout (payouts 4-5 and the
              uncapped 6th+: cheque <= profit - 7,600, so a request needs profit >= $8,100); variants 'pay4_free' (R's
              optimistic reading: no minimum, $200 may remain) and 'pay4_req_only' (the minimum to request only).
              Cap $3,500 for payouts 1-5, none after. Split 100% of the first $25,000 per account, 90% after.
              Commissions: Apex's published schedule (default 'apex' = the dearer of Tradovate / Rithmic per instrument:
              NQ $3.98, MNQ $1.04 round turn; the platform of the user's accounts is unknown). Lucid's stay R's ($4.00 / $1.00).
  apex50_pa   the 50K Legacy PA under the same semantics and the same conservative readings (R's `apex` = r_compat("apex50_pa")).
  anything else ('flex', 'pro', 'apex') is passed straight to R/funded.py.

START STATES (`start=`): 'fresh' (profit 0), 'plus3000', 'plus7600', a number (profit $) or a Start(...). The peak defaults to the
start profit (so +7,600 starts with the threshold LOCKED at +$100; any approved payout implies a locked threshold), full size is
derived by the rule (EOD profit > unlock), the payout cycle starts at day 0 with no payout history. All overridable through Start
(peak, full, pays, paid_gross, cd, cw, cmax, cpnl); `resolve_start` VALIDATES the state (hand-typed account states).

MODELS (intraday-primary, as R): 'pess' (primary; every trade's MFE lifts the trailing peak before its MAE is tested), 'nat',
'opt' (bound). Option trail='eod' (spec override) = the account holder's reading (peak updated at the close only; the breach test
stays real time) - a sensitivity, NOT what the Apex help centre says for Legacy.
POLICY T: request on the first EOD the eligibility holds AND the cheque >= T (500 | 1500 | 2500 | 'max' = the per-payout cap);
the cheque taken is always the largest allowed that day. None = never request.
Attempt tuple, metrics and row formats are R/funded.py's: (bust_day, [(day, gross, net)], cuts, executed).

COMPLIANCE GATE (`compliance`, used identically by evaluate_funded, search and score.py): a config is compliant only when ALL
THREE SPEC criteria are PROVEN -
  one direction     PROVEN BY THE ROWS, never by the caller's word alone: (a) every trade row carries the simulator's own stamp
                    `both_sides` = False (l2sim writes it on every row: no entry orders of opposite sides were working at the
                    same time in that session; `oco` = the entry was a leg of a two-sided OCO pair), or (b) for rows without
                    the stamp (tester bundles): the caller declares both_sides=False AND every row is a market entry
                    (`order_price` present and null: nothing rested). FAIL on a declared both_sides=True, an OCO family, a
                    stamped row, a run with both-side sessions, or overlapping opposite-side trades. Anything else UNCHECKED.
  stop <= 5x target every trade carries a stop and a target with stop <= 5 x target, measured from the fill on the rows' sl / tp
                    (no slippage allowance: both simulators price the bracket from the fill); the rows must cover the
                    portfolio's trades. Without any rows: `inputs['tgt_r']` must be GIVEN and >= 0.2. No stop the size of the
                    trailing threshold.
  MAE rule          MAE-rule cuts on <= 2% of the executed trades.
Anything FAILED or UNCHECKED => `noncompliant=True` (fail closed); `compliant(rows)` keeps only proven rows.
EVALUATION: `make_eval_spec` / `eval_lifecycle` / `eval_metrics` = the Legacy 300K evaluation (score.py firm 'apex300_eval').
FIVE ACCOUNTS: `five_accounts(plan)` scores the user's five PAs run as copies of one account (no diversification).
"""
from __future__ import annotations

import datetime as dt
import itertools
import json
import math
import multiprocessing as mp
import sys
import time
from collections import namedtuple
from pathlib import Path

import numpy as np

L = Path(__file__).resolve().parent
REPO = L.parents[2]
R = REPO / "research" / "prop-portfolio" / "2026-09-29"            # the old NQ pilot (READ-ONLY)
sys.dont_write_bytecode = True                         # importing R / homebase must not write __pycache__ there (read-only)
sys.path.insert(0, str(R))
import evalcore as E                                   # noqa: E402
import funded as F                                     # noqa: E402

for _p in (str(R), str(REPO)):                         # as score.py: R / repo stay importable but never shadow L's modules
    while _p in sys.path:
        sys.path.remove(_p)
    sys.path.append(_p)

if Path(E.__file__).resolve().parent != R or Path(F.__file__).resolve().parent != R:
    raise ImportError(f"evalcore / funded were not imported from {R} (name shadowed by another module on sys.path)")

HOLDOUT = E.HOLDOUT                                    # "2025-01-01": sealed
HOLDOUT_MS = int(dt.datetime(2025, 1, 1, tzinfo=E.ET).timestamp() * 1000)
IS_START, IS_END = "2021-09-22", "2024-12-31"          # L2 in-sample window (SPEC.md)
H_LIFE = F.H_LIFE
ORDERS = F.ORDERS
CUT_OK = 0.02                                          # share of executed trades cut by the MAE rule above which a config is non-compliant
STOP_X_TARGET = 5.0                                    # Apex 5:1 rule: stop <= 5 x profit target on every trade
TICK_PTS = E.TICK_USD / E.PT_USD                       # NQ 0.25
TICK_USD = E.TICK_USD                                  # one tick on ONE micro ($0.50)
SLIP_TOL_PTS = 1e-9                                    # NO slippage allowance: sl / tp on the rows are priced from the fill (both
                                                       # simulators), so a 5.2 : 1 row is a 5.2 : 1 trade (float noise only)
POLICIES = {"apex300_pa": (500, 1500, 2500, "max"), "apex50_pa": F.POLICIES}
MAX_WORKERS = 8

# $ per ROUND TURN (NQ, MNQ), Apex help centre 2026-10-01 (APEX300_RULES.md [S19] Tradovate, [S20] Rithmic). 'apex' = the dearer
# of the two per instrument (the platform of the user's accounts is unknown); 'R' = R/evalcore's cost model (Lucid: 4.00 / 1.00).
COMMISSIONS = {"apex": (3.98, 1.04), "tradovate": (3.10, 1.04), "rithmic": (3.98, 1.02), "R": None}

ACCOUNT_WARNINGS = (
    "AUTOMATION_PROHIBITED: Apex bans automation / algorithm usage on PA accounts (AI, bots, algorithms, any hands-off or "
    "set-and-forget trading); the penalty is account closure and forfeiture. Running the desk unattended breaches it. An algo "
    "that places the orders while a person supervises is UNCONFIRMED and LIKELY NON-COMPLIANT (no Apex page allows it; the "
    "Prohibited Activities page reserves rewards for human traders, not preprogrammed logic). Only a rule set a person executes "
    "by hand is clearly inside the rules (APEX300_RULES.md A1).",
    "CROSS_ACCOUNT_HEDGING: never long in one Apex account while short in another (any correlated market, minis or micros), "
    "including accounts of other traders in the same household or related parties; check multi-account plans with "
    "cross_account_conflicts().",
    "COPY_TRADING: copying your own trades across your own accounts is supported (Tradovate Group Trade is enabled for any Apex "
    "user with more than one Tradovate account); copying with OTHER traders is forbidden. The Tradovate group copier does not "
    "allow bracket / ATM orders (NinjaTrader is needed for those): stops and targets must be placed another way.",
    "SIZE_CONSISTENCY: keep the same size / stops / targets through a payout cycle; all-in at the start of a PA is prohibited.",
)


class HoldoutError(ValueError):
    """A row / calendar day / window end dated >= 2025-01-01 was passed without allow_holdout=True."""


# ------------------------------------------------------------------ specs

_APEX300 = dict(
    name="apex300_pa", kind="apex", ext=True, start_balance=300000.0, dll=0.0,
    mll=7500.0, lock_at=7600.0, lock_floor=100.0, trail="intraday",
    cap=350, half=170, unlock=7600.0, sticky_full=True,
    mae_pct=0.30, mae_pct_hi=0.50, mae_hi_at=15200.0, mae_min=2250.0,
    min_days=8, win_days=5, win_day=50.0, days_count="traded",
    cons=0.30, cons_until=5, cons_base="cycle",
    net_pay=7100.0, net_pays=3, post_req_min=7600.0, post_net_min=7600.0, post_cap_net=7600.0,
    min_pay=500.0, pay_cap=3500.0, cap_pays=5,
    split_full=1.0, split_after=0.9, split_until=25000.0, primary="pess")

# every value of a spec that could not be confirmed on the Apex help centre (see APEX300_RULES.md)
UNCONFIRMED = {
    "half": "17.5 minis: default 170 micros (17 minis, rounded down = conservative); 175 micros is the variant 'half_175'",
    "unlock": "rule says the EOD balance must EXCEED start+DD+100, the worked example says REACHES; modelled strictly (>)",
    "cons_base": "key-details text: profit since the last approved payout ('cycle', default, conservative); worked example: total "
                 "profit = balance - start ('balance'); both are always reported",
    "post_req_min": "min-balance table ($307,600) is not qualified by payout number; default: needed for EVERY request "
                    "(conservative); variant 'pay4_free': first three payouts only (as R)",
    "post_net_min": "what must remain after payouts 4-5 is not stated; default: the minimum required balance ($307,600, "
                    "conservative); variants 'pay4_free' / 'pay4_req_only': $200 above the start (as R)",
    "post_cap_net": "6th+ payout: 'the minimum balance threshold' must remain; default $307,600 (conservative), variant $200",
    "trail": "help centre: peak UNREALISED balance (intraday); the account holder said 'EOD trail' (homebase rule file)",
    "mae_scope": "page says both 'per trade' and 'combined open negative P&L'; modelled per trade (as R)",
    "days_count": "'trading day' for the 8-day rule taken as a session with >= 1 executed trade; half-day holidays not modelled",
    "commission": "platform of the user's accounts unknown: default = the dearer of Apex's Tradovate / Rithmic schedules per "
                  "instrument; every 10 micros are costed as one NQ (R's convention) - all-MNQ execution costs more",
}

# rule-uncertainty variants for `sensitivity`: name -> f(base spec) -> spec overrides; 'base' = the default (conservative) spec
VARIANTS = {
    "base": lambda S: {},
    "cons_balance": lambda S: dict(cons_base="balance"),                               # 30% of (balance - start): optimistic reading
    "pay4_free": lambda S: dict(post_req_min=0.0, post_net_min=200.0, post_cap_net=200.0),          # R's reading (optimistic)
    "pay4_req_only": lambda S: dict(post_req_min=S.lock_at, post_net_min=200.0, post_cap_net=S.lock_at),   # request needs the minimum only
    "half_175": lambda S: dict(half=S.cap // 2),                                       # exactly half in micros (300K: 17.5 minis)
    "trail_eod": lambda S: dict(trail="eod"),                                          # account holder's reading (optimistic)
    "comm_tradovate": lambda S: dict(commission="tradovate"),
    "comm_rithmic": lambda S: dict(commission="rithmic"),
}

# What a NEW Legacy 300K evaluation costs / requires (APEX300_RULES.md section 2b; Apex sells them again as a limited-time offer).
# Not simulated here: evals are scored by evalcore on homebase rule files (rule id below = the account holder's wording, which
# says EOD trail and 1 minimum day; the help centre says intraday trail and 7 trading days - UNCONFIRMED which applies).
EVAL300 = dict(
    name="apex300_legacy_eval", start_balance=300000.0, target=20000.0, mll=7500.0, trail="intraday", cap=350, dll=0.0,
    scaling=None, min_days=7, consistency=None, price_month=797.0, price_month_coupon=79.70, pa_fee_lifetime=300.0,
    pa_fee_plan_card=55.0, homebase_rule_id="apex-legacy-300k@2026-09-28",
    status="PURCHASABLE per /legacy-products/ (mod 2026-08-25) and the PA activation page; the Legacy overview page (mod "
           "2026-07-21) still says sales ended 2026-03-01 - CONFLICT, checkout not tested")

Start = namedtuple("Start", "profit peak full pays paid_gross cd cw cmax cpnl", defaults=(0.0, None, None, 0, None, 0, 0, 0.0, 0.0))
STARTS = {"fresh": Start(), "plus3000": Start(3000.0), "plus7600": Start(7600.0)}
EXT_FIRMS = ("apex300_pa", "apex50_pa")


def r_compat(firm: str = "apex300_pa") -> dict:
    """Spec overrides that reproduce R/funded.py's Apex semantics (R's optimistic readings: consistency on balance - start,
    payouts 4+ without a minimum balance, exactly half the contracts, R's Lucid cost model). For parity tests and for comparing
    with R's frozen numbers - NOT a selection default."""
    return dict(cons_base="balance", post_req_min=0.0, post_net_min=200.0, post_cap_net=200.0, commission="R",
                half=175 if firm == "apex300_pa" else 50)


def make_spec(firm: str = "apex300_pa", dll: float | None = None, micros_allowed: bool = True, **over) -> F.Spec:
    """'apex300_pa' | 'apex50_pa' -> an extended Apex spec (for simulate / lifecycle / search / compliance of THIS module);
    any other firm name -> R/funded.make_spec unchanged. Overrides: any spec key, or commission='apex' | 'tradovate' | 'rithmic'
    | 'R'. An unknown override name raises. micros_allowed=False: the half-size cap is rounded down to whole minis."""
    if firm == "apex300_pa":
        d = dict(_APEX300)
    elif firm == "apex50_pa":
        d = dict(F.make_spec("apex").__dict__)
        d.update(name="apex50_pa", ext=True, start_balance=50000.0, trail="intraday", cons_base="cycle",
                 post_req_min=d["lock_at"], post_net_min=d["lock_at"], post_cap_net=d["lock_at"])
    else:
        return F.make_spec(firm, dll, **over)
    valid = set(d) | {"commission", "comm_nq", "comm_mnq"}
    unknown = sorted(set(over) - valid)
    if unknown:
        raise ValueError(f"unknown spec override(s) {unknown} for {firm}; valid names: {sorted(valid)}")
    com = over.pop("commission", "custom" if "comm_nq" in over or "comm_mnq" in over else "apex")
    if com not in COMMISSIONS and com != "custom":
        raise ValueError(f"unknown commission schedule {com!r}; valid: {sorted(COMMISSIONS)}")
    nq, mnq = COMMISSIONS.get(com) or (None, None)
    d.update(commission=com, comm_nq=nq, comm_mnq=mnq)
    if not micros_allowed and "half" not in over:
        d["half"] = (d["cap"] // 10 // 2) * 10
    d["micros_allowed"] = micros_allowed
    d.update(over)
    if (d["comm_nq"] is None) != (d["comm_mnq"] is None):
        raise ValueError("comm_nq and comm_mnq must be given together")
    if d["cons_base"] not in ("cycle", "balance"):
        raise ValueError(f"cons_base {d['cons_base']!r} not in ('cycle', 'balance')")
    if d["trail"] not in ("intraday", "eod"):
        raise ValueError(f"trail {d['trail']!r} not in ('intraday', 'eod')")
    return F.Spec(**d)


def other_cons(S) -> F.Spec:
    """The same spec under the OTHER reading of the consistency base ('cycle' <-> 'balance')."""
    d = dict(S.__dict__)
    d["cons_base"] = "balance" if S.cons_base == "cycle" else "cycle"
    return F.Spec(**d)


def size_micros(contracts: float | None = None, micros: int | None = None, micros_allowed: bool = True) -> int | None:
    """Sizing input -> micros (10 micros = 1 NQ). contracts = NQ minis (fractions only if micros are allowed). None/None -> None
    (each portfolio member keeps its own size)."""
    if contracts is not None and micros is not None:
        raise ValueError("give contracts OR micros, not both")
    if contracts is None and micros is None:
        return None
    n = int(round(contracts * 10)) if contracts is not None else int(micros)
    if not micros_allowed:
        if n % 10:
            raise ValueError(f"size {n} micros is not a whole number of minis (micros_allowed=False)")
    if n < 1:
        raise ValueError("size must be >= 1 micro")
    return n


def as_start(start="fresh") -> Start:
    if isinstance(start, Start):
        return start
    if isinstance(start, str):
        if start not in STARTS:
            raise ValueError(f"unknown start state {start!r}; valid names: {sorted(STARTS)} (or a profit in $, or a Start(...))")
        return STARTS[start]
    if isinstance(start, bool) or not isinstance(start, (int, float, np.integer, np.floating)):
        raise ValueError(f"start must be a name {sorted(STARTS)}, a profit in $ or a Start(...), not {start!r}")
    return Start(float(start))


def start_name(start) -> str:
    if isinstance(start, str):
        as_start(start)
        return start
    st = as_start(start)
    for k, v in STARTS.items():
        if v == st:
            return k
    return f"profit{st.profit:+.0f}" + ("" if st == Start(st.profit) else "_custom")


def mae_limit(S, profit: float) -> float:
    """Open-loss limit ($) in force for a session that starts with `profit` (balance - start)."""
    return max((S.mae_pct_hi if profit >= S.mae_hi_at else S.mae_pct) * profit, S.mae_min)


def floor_of(S, peak: float) -> float:
    """Liquidation threshold (as profit, $ vs the starting balance) for a trailing peak."""
    return S.lock_floor if peak >= S.lock_at else peak - S.mll


def resolve_start(S, start="fresh") -> Start:
    """Start state with its defaults filled in and VALIDATED against the spec (all $ are profit = balance - starting balance):
      peak        default max(profit, 0); with pays >= 1 at least lock_at (an approved payout needs the minimum balance, so the
                  threshold is locked). Must be >= the balance; with pays >= 1 it must be >= lock_at.
      full        default profit > unlock, or pays >= 1 (a payout needs an EOD balance at the safety net); pass full=True for
                  an account that has closed above the safety net before and fell back.
      paid_gross  default min(pays, cap_pays) x pay_cap (conservative: the 100% split band is used up sooner).
      cd / cw / cmax / cpnl   traded days, days >= $50, best day and profit of the CURRENT payout cycle (cpnl counts in the
                  'cycle' consistency base; 0 = the cushion predates the cycle, the conservative default).
    Raises ValueError on an impossible state (balance at / below the liquidation threshold, peak below the balance, ...).
    Idempotent: a resolved Start resolves to itself."""
    st = as_start(start)
    profit, pays = float(st.profit), int(st.pays)
    peak = st.peak if st.peak is None else float(st.peak)
    if not all(math.isfinite(float(v)) for v in (profit, st.cmax, st.cpnl) + (() if peak is None else (peak,))
               + (() if st.paid_gross is None else (st.paid_gross,))):
        raise ValueError(f"invalid start state {st} for {S.name}: profit / peak / paid_gross / cmax / cpnl must be finite numbers")
    bad = []
    if pays < 0 or st.cd < 0 or st.cw < 0 or st.cmax < 0:
        bad.append("pays / cd / cw / cmax must be >= 0")
    if peak is None:
        peak = max(profit, 0.0, S.lock_at if pays >= 1 else 0.0)
    else:
        if peak < max(profit, 0.0) - 1e-9:
            bad.append(f"peak {peak:+.0f} is below the balance ({profit:+.0f}) or the starting balance: the peak is the HIGHEST balance reached")
        if pays >= 1 and peak < S.lock_at - 1e-9:
            bad.append(f"{pays} approved payout(s) imply the peak reached {S.lock_at:+.0f} (threshold locked), got peak {peak:+.0f}")
    if profit <= floor_of(S, peak):
        bad.append(f"profit {profit:+.0f} is at / below the liquidation threshold {floor_of(S, peak):+.0f} (peak {peak:+.0f}): the account is already closed")
    full = (profit > S.unlock or pays >= 1) if st.full is None else bool(st.full)
    if st.full and peak <= S.unlock and pays < 1:              # an approved payout implies full size (the default above), so a
        bad.append(f"full=True needs an EOD balance above {S.unlock:+.0f} at some point, but the peak is {peak:+.0f}")   # resolved state resolves again
    paid = st.paid_gross
    if paid is None:
        paid = min(pays, S.cap_pays) * S.pay_cap
    else:
        paid = float(paid)
        if pays == 0 and paid:
            bad.append("paid_gross > 0 with pays = 0")
        if pays and paid < pays * S.min_pay - 1e-9:
            bad.append(f"paid_gross {paid:.0f} is below {pays} x the minimum payout {S.min_pay:.0f}")
        if 0 < pays <= S.cap_pays and paid > pays * S.pay_cap + 1e-9:
            bad.append(f"paid_gross {paid:.0f} exceeds {pays} x the payout cap {S.pay_cap:.0f}")
    if st.cw > st.cd:
        bad.append("cw (days >= the win-day minimum) cannot exceed cd (traded days of the cycle)")
    if st.cd == 0 and (st.cmax or st.cpnl):
        bad.append("cmax / cpnl need cd >= 1 (a cycle with no traded day has no best day and no profit)")
    if bad:
        raise ValueError(f"invalid start state {st} for {S.name}: " + "; ".join(bad))
    return Start(profit, peak, full, pays, paid, int(st.cd), int(st.cw), float(st.cmax), float(st.cpnl))


# ------------------------------------------------------------------ commissions: R's day walk on the spec's schedule

def comm_of(S):
    """($ per NQ round turn, $ per MNQ round turn) of a spec, or None = R/evalcore's cost model."""
    nq = getattr(S, "comm_nq", None)
    return None if nq is None else (float(nq), float(S.comm_mnq))


def cost(n: int, comm=None) -> float:
    """Round-trip commission for n micros (every 10 micros = one NQ, the rest MNQ: R's convention) under `comm`."""
    return E.cost(n) if comm is None else (n // 10) * comm[0] + (n % 10) * comm[1]


class DaySrc(F.DaySrc):
    """R's memoised day walks (funded.DaySrc / walk_day, unchanged code) on a commission schedule `comm` = (NQ, MNQ) $ per
    round turn; None = R's cost model. The schedule is swapped into R's module only for the duration of one walk
    (single-threaded; fork workers own their copy) and always restored, so Lucid walks in the same process keep R's costs."""

    def __init__(self, P, rules: dict | None = None, micros: int | None = None, events: bool = True, comm=None):
        super().__init__(P, rules, micros, events)
        self.comm = tuple(comm) if comm else None

    def get(self, i, cap, dll=0.0, lim=0.0):
        if self.comm is None:
            return super().get(i, cap, dll, lim)
        nq, mnq = self.comm
        old = F.cost
        F.cost = lambda n: (n // 10) * nq + (n % 10) * mnq
        try:
            return super().get(i, cap, dll, lim)
        finally:
            F.cost = old


def day_src(S, P, rules: dict | None = None, micros: int | None = None) -> DaySrc:
    """Day source of a portfolio for a spec (its commission schedule, events on)."""
    return DaySrc(P, rules, micros, True, comm_of(S))


def as_src(S, src):
    """The source a spec must be walked with: an R funded.DaySrc on another commission schedule is re-based on the spec's
    (clone cached on the source, own memo); anything else (test doubles, a matching source) is returned unchanged."""
    if not isinstance(src, F.DaySrc):
        return src
    comm = comm_of(S)
    if getattr(src, "ev", False) and getattr(src, "comm", None) == comm and (comm is None or isinstance(src, DaySrc)):
        return src                                             # (a source built WITHOUT events would never show a breach)
    cache = src.__dict__.setdefault("_apex300_src", {})
    if comm not in cache:
        d = DaySrc.__new__(DaySrc)
        d.__dict__.update(P=src.P, micros=src.micros, ev=True, rl=src.rl, tk=src.tk, memo={}, _bound=src._bound,
                          n_days=src.n_days, comm=comm)
        cache[comm] = d
    return cache[comm]


# ------------------------------------------------------------------ trades -> portfolio (holdout-sealed)

def _row_reaches_holdout(r) -> bool:
    if str(r.get("date", ""))[:10] >= HOLDOUT:
        return True
    for k in ("entry_ms", "exit_ms"):
        v = r.get(k)
        if v is not None and int(v) >= HOLDOUT_MS:
            return True
    return False


def load_trades(src, allow_holdout: bool = False) -> list:
    """src: list of trade dicts (R trades.json schema, per 1 NQ) | path to a trades.json (a list or {'trades': [...]}) | a
    bundle directory holding trades.json. Raises HoldoutError if ANY row reaches the holdout - by its `date`, its entry_ms or
    its exit_ms (>= 2025-01-01 ET) - unless allow_holdout=True (nothing is returned in that case), and ValueError on a file
    without a trade list or a row whose `date` is not an ISO 'YYYY-MM-DD' string."""
    if isinstance(src, (str, Path)):
        p = Path(src).expanduser()
        p = p / "trades.json" if p.is_dir() else p
        data = json.loads(p.read_text())
        if isinstance(data, list):
            rows = data
        elif isinstance(data, dict) and isinstance(data.get("trades"), list):
            rows = data["trades"]
        else:
            keys = sorted(data) if isinstance(data, dict) else type(data).__name__
            raise ValueError(f"{p}: expected a JSON list of trades or an object with a 'trades' list, got {keys}")
    else:
        rows = list(src)
    if not allow_holdout:
        n = sum(1 for r in rows if _row_reaches_holdout(r))
        if n:
            raise HoldoutError(f"{n} trade rows reach the sealed holdout (date, entry_ms or exit_ms >= {HOLDOUT}); "
                               f"pass allow_holdout=True only on the orchestrator's 'holdout'")
    for i, r in enumerate(rows):
        d = r.get("date")
        try:
            ok = isinstance(d, str) and len(d) == 10 and dt.date.fromisoformat(d).isoformat() == d
        except ValueError:
            ok = False
        if not ok:
            raise ValueError(f"trade row {i}: date {d!r} is not an ISO 'YYYY-MM-DD' string")
    return rows


def default_calendar(start: str, end: str) -> list:
    """Session calendar: R's cached NQ tape sessions (read-only) where they cover the window, plain weekdays elsewhere."""
    cf = E.D / "bundles_cache" / "nq_sessions.json"
    cached = [d for d in (json.loads(cf.read_text()) if cf.exists() else []) if start <= d <= end]
    lo, hi = (cached[0], cached[-1]) if cached else ("9999", "0000")
    out, d, e = set(cached), dt.date.fromisoformat(start), dt.date.fromisoformat(end)
    while d <= e:
        s = d.isoformat()
        if d.weekday() < 5 and (s < lo or s > hi):
            out.add(s)
        d += dt.timedelta(1)
    return sorted(out)


def port_from_trades(trades=None, *, micros: int = 10, sess="all", members: list | None = None, calendar: list | None = None,
                     start: str = IS_START, end: str = IS_END, allow_holdout: bool = False):
    """Trade list(s) -> evalcore Port. Single source: `trades` (+ sess, + default micros of the member); several: members =
    [{'src': trades|path, 'micros': n, 'sess': 'nyam'}, ...]. The holdout is sealed: a window end, a calendar day or any trade row
    reaching 2025-01-01 (date / entry_ms / exit_ms) raises HoldoutError unless allow_holdout=True.
    The per-trade compliance checks of the rows that went in (`trade_checks`) are attached as `P.apex_trades`."""
    if not allow_holdout and end >= HOLDOUT:
        raise HoldoutError(f"end {end} reaches the sealed holdout ({HOLDOUT})")
    mem = [dict(m) for m in members] if members is not None else [{"src": trades, "micros": micros, "sess": sess}]
    for m in mem:
        m["src"] = load_trades(m["src"], allow_holdout)
    cal = default_calendar(start, end) if calendar is None else list(calendar)
    if not allow_holdout and any(d >= HOLDOUT for d in cal):
        raise HoldoutError(f"calendar reaches the sealed holdout ({HOLDOUT})")
    P = E.build({"members": mem, "start": start, "end": end}, cal, holdout=allow_holdout)
    P.apex_trades = trade_checks(mem, start=P.window[0], end=P.window[1], allow_holdout=allow_holdout)
    return P


def _seal(P, allow_holdout: bool) -> None:
    """A Port that already holds holdout sessions / trades is refused unless allow_holdout=True."""
    if allow_holdout:
        return
    iso = getattr(P, "iso", None)
    win = getattr(P, "window", None)
    last_te = max((d[-1][0] for d in P.days if d), default=0)
    if (iso and iso[-1] >= HOLDOUT) or (isinstance(win, (tuple, list)) and len(win) == 2 and str(win[1]) >= HOLDOUT) \
            or last_te >= HOLDOUT_MS:
        raise HoldoutError(f"the portfolio reaches the sealed holdout ({HOLDOUT}); pass allow_holdout=True only on the "
                           f"orchestrator's 'holdout'")


def _need_window(n_days: int, H: int) -> None:
    if n_days < H:
        raise ValueError(f"window too short: {n_days} sessions < the {H}-session horizon (no rolling start has a full horizon); "
                         f"use a longer window or a smaller H")


# ------------------------------------------------------------------ lifecycle

def _sim(S, src, s, H, T, order, st: Start):
    """One Apex Legacy PA attempt from session s and a RESOLVED start state st -> (bust_day, [(day, gross, net)], cuts, executed).
    R/funded._sim_apex generalised: start state, payouts 4+ request minimum, uncapped-payout remainder, optional EOD trail."""
    profit = float(st.profit)
    peak = float(st.peak)
    full = bool(st.full)
    bust, pays, cuts, ex = 0, [], 0, 0
    n0, paid_gross = int(st.pays), float(st.paid_gross)
    cd, cw, cmax, cstart = int(st.cd), int(st.cw), float(st.cmax), profit - float(st.cpnl)
    sel = {"pess": 4, "opt": 5, "nat": 7}[order]
    intraday = getattr(S, "trail", "intraday") == "intraday"
    for k in range(H):
        cap = S.cap if full else S.half
        pct = S.mae_pct_hi if profit >= S.mae_hi_at else S.mae_pct
        lim = max(pct * profit, S.mae_min)
        o = src.get(s + k, cap, 0.0, lim)
        pk, dead = peak, False
        for kind, v in o[sel]:
            x = profit + v
            if kind:
                if intraday and x > pk:
                    pk = x
            elif x <= (S.lock_floor if pk >= S.lock_at else pk - S.mll):
                dead = True
                break
        if dead:
            bust = k + 1
            break
        peak = pk
        pnl = o[0]
        profit += pnl
        if not intraday and profit > peak:
            peak = profit
        cuts += o[6]
        ex += o[3]
        if profit > S.unlock:
            full = True
        elif not S.sticky_full and profit <= S.unlock:
            full = False
        if S.days_count == "all" or o[3] > 0:
            cd += 1
        if pnl >= S.win_day:
            cw += 1
        cmax = max(cmax, pnl)
        if T is None or cd < S.min_days or cw < S.win_days:
            continue
        idx = n0 + len(pays) + 1
        base = profit if S.cons_base == "balance" else profit - cstart
        if idx <= S.cons_until and cmax > S.cons * base + 1e-9:
            continue
        if idx <= S.net_pays:
            avail = profit - S.net_pay
        else:
            if profit < S.post_req_min - 1e-9:
                continue
            avail = profit - (S.post_net_min if idx <= S.cap_pays else S.post_cap_net)
        ch = min(S.pay_cap if idx <= S.cap_pays else math.inf, avail)
        if ch >= S.min_pay and ch >= F._need(T, S.pay_cap) - 1e-9:
            full_part = min(ch, max(0.0, S.split_until - paid_gross))
            pays.append((k + 1, ch, full_part * S.split_full + (ch - full_part) * S.split_after))
            paid_gross += ch
            profit -= ch
            cd = cw = 0
            cmax, cstart = 0.0, profit
    return bust, pays, cuts, ex


def simulate(S, src, s: int, H: int = H_LIFE, T=500, model: str | None = None, start="fresh"):
    """One attempt from session s. Extended Apex specs run here (on the spec's commission schedule); any other spec goes to
    R/funded.simulate (fresh start only)."""
    if not getattr(S, "ext", False):
        if as_start(start) != Start():
            raise ValueError("start states are only modelled for apex300_pa / apex50_pa")
        return F.simulate(S, src, s, H, T, model)
    model = model or S.primary
    if model not in ORDERS:
        raise ValueError(f"apex model {model!r} not in {ORDERS}")
    return _sim(S, as_src(S, src), s, H, T, model, resolve_start(S, start))


def lifecycle(S, src, T=500, H: int = H_LIFE, model: str | None = None, start="fresh", starts=None) -> list:
    """All rolling starts with a full H-session horizon (R convention) -> list of attempt tuples ([] when the window is shorter
    than H). Extended specs are walked on their own commission schedule whatever source is passed (score.py passes R's)."""
    starts = range(src.n_days - H + 1) if starts is None else starts
    if not getattr(S, "ext", False):
        return [simulate(S, src, s, H, T, model, start) for s in starts]
    model = model or S.primary
    if model not in ORDERS:
        raise ValueError(f"apex model {model!r} not in {ORDERS}")
    st, src = resolve_start(S, start), as_src(S, src)
    return [_sim(S, src, s, H, T, model, st) for s in starts]


metrics = F.metrics


# ------------------------------------------------------------------ compliance

_SIDES = {"long": 1, "buy": 1, "b": 1, "l": 1, "short": -1, "sell": -1, "s": -1}


def side_sign(x) -> int:
    """'long' / 'buy' / 'B' / 1 / '+1' -> +1; 'short' / 'sell' / -1 -> -1 (any case). Anything else raises ValueError."""
    if isinstance(x, str):
        k = x.strip().lower()
        if k in _SIDES:
            return _SIDES[k]
    if not isinstance(x, bool):
        try:
            v = float(x)
        except (TypeError, ValueError):
            v = 0.0
        if v in (1.0, -1.0):
            return int(v)
    raise ValueError(f"unknown trade side {x!r} (expected long / short, buy / sell or +1 / -1)")


def _is_members(x) -> bool:
    return isinstance(x, (list, tuple)) and len(x) > 0 and isinstance(x[0], dict) and "src" in x[0]


def _in_sess(ms: int, sess) -> bool:
    names = sess if isinstance(sess, (list, tuple)) else str(sess or "all").split("+")
    if "all" in names:
        return True
    t = dt.datetime.fromtimestamp(ms / 1000, E.ET)
    mod = t.hour * 60 + t.minute
    return any(E.SESS[s][0] <= mod < E.SESS[s][1] for s in names)


def _opposite_overlaps(ev: list) -> int:
    """ev = [(entry_ms, exit_ms, side)]: number of trades that are opened while a trade of the OPPOSITE side is still open."""
    live, n = [], 0
    for te, tx, sd in sorted(ev):
        live = [o for o in live if o[0] > te]
        n += any(o[1] != sd for o in live)
        live.append((tx, sd))
    return n


def trade_checks(trades, sess="all", start: str | None = None, end: str | None = None, allow_holdout: bool = False) -> dict | None:
    """Per-trade Apex compliance of raw trade rows (R trades.json schema: side, entry_price, sl, tp, entry_ms, exit_ms).
    trades: rows | path | member list [{'src': rows | path, 'sess': ...}]; only the rows of the member's session (entry time,
    evalcore's session windows) and of [start, end] are checked. -> None when a source has no rows, else
      n                  trades checked
      no_stop            rows without `sl` (a stop is mandatory)
      no_target          rows without `tp`, or with a target on the wrong side of the entry
      stop_gt_5x         rows whose stop distance exceeds 5 x the target distance, both measured from the fill (no allowance)
      max_stop_over_target   the worst ratio seen
      opposite_overlap   trades opened while an opposite-side trade was still open (both directions at once = hedging)
      both_side_orders   rows the simulator stamped with a truthy `both_sides` / `oco` key (working orders on both sides)
      stamped            rows that carry the simulator's `both_sides` stamp at all (True or False): l2sim's own evidence
      resting_entries    rows NOT proven to be market entries (an `order_price`, or no `order_price` key on the row)
      both_side_sessions sessions of the run(s) in which opposite-side entry orders were working, filled or not (a member's
                         'both_sides_sessions', from the l2sim result / bundle; 0 when the source does not say)
    Fills alone cannot show resting orders: the proof of ONE DIRECTION is the stamp on every row, or market entries only."""
    rows, sess_two = [], 0
    for m in (trades if _is_members(trades) else [{"src": trades, "sess": sess}]):
        if m.get("src") is None:
            return None
        ms = m.get("sess", sess)
        sess_two += int(m.get("both_sides_sessions") or 0)
        rows += [r for r in load_trades(m["src"], allow_holdout)
                 if (start is None or r["date"] >= start) and (end is None or r["date"] <= end) and _in_sess(int(r["entry_ms"]), ms)]
    out = dict(n=len(rows), no_stop=0, no_target=0, stop_gt_5x=0, max_stop_over_target=None, opposite_overlap=0, both_side_orders=0,
               stamped=0, resting_entries=0, both_side_sessions=sess_two)
    ev, worst = [], 0.0
    for r in rows:
        s = side_sign(r.get("side", "long"))
        e, sl, tp = r.get("entry_price"), r.get("sl"), r.get("tp")
        sd = s * (float(e) - float(sl)) if sl is not None and e is not None else None
        td = s * (float(tp) - float(e)) if tp is not None and e is not None else None
        if sd is None:
            out["no_stop"] += 1
        if td is None or td <= 0:
            out["no_target"] += 1
        elif sd is not None:
            worst = max(worst, sd / td)
            out["stop_gt_5x"] += sd > STOP_X_TARGET * td + SLIP_TOL_PTS
        out["both_side_orders"] += bool(r.get("both_sides") or r.get("oco"))
        out["stamped"] += r.get("both_sides") is not None
        out["resting_entries"] += ("order_price" not in r) or r["order_price"] is not None
        ev.append((int(r["entry_ms"]), int(r.get("exit_ms", r["entry_ms"] + 1)), s))
    out["max_stop_over_target"] = worst if rows else None
    out["opposite_overlap"] = _opposite_overlaps(ev)
    return out


def _as_checks(trades, sess="all", allow_holdout: bool = False) -> dict | None:
    """`trades` of the compliance functions -> a trade_checks dict. Accepts raw rows / a path / a member list (-> trade_checks)
    or ready-made statistics: a trade_checks result, or score.py's stop_target_stats ({'n', 'no_stop_share', 'no_target_share',
    'stop_gt_5x_target_share', 'max_stop_over_target'})."""
    if isinstance(trades, dict) and "n" in trades and "src" not in trades:
        n = int(trades["n"])

        def cnt(*keys):
            for k in keys:
                if trades.get(k) is not None:
                    return int(trades[k])
                if trades.get(k + "_share") is not None:
                    return int(math.ceil(float(trades[k + "_share"]) * n - 1e-9))
            return None

        ns, nt, g5 = cnt("no_stop"), cnt("no_target"), cnt("stop_gt_5x", "stop_gt_5x_target")
        rest = cnt("resting_entries")
        out = dict(n=n, no_stop=ns or 0, no_target=nt or 0, stop_gt_5x=g5 or 0,
                   max_stop_over_target=trades.get("max_stop_over_target"), opposite_overlap=cnt("opposite_overlap") or 0,
                   both_side_orders=cnt("both_side_orders") or 0, stamped=cnt("stamped") or 0,
                   resting_entries=n if rest is None else rest, both_side_sessions=cnt("both_side_sessions") or 0)
        if ns is None or nt is None or g5 is None:             # a bare {'n': 90}: nothing was counted, nothing is proven
            out["unproven"] = True
        return out
    return trade_checks(trades, sess, allow_holdout=allow_holdout)


def port_checks(P) -> dict:
    """What a Port alone shows: trades, trades without a stop (risk is nan) and opposite-side overlaps (side / entry / exit)."""
    n = nos = 0
    ev = []
    for trs in P.days:
        for x in trs:
            n += 1
            nos += x[6] != x[6]
            ev.append((x[0], x[1], x[2]))
    return {"n": n, "no_stop": nos, "opposite_overlap": _opposite_overlaps(ev)}


def stop_over_threshold_share(P, micros: int | None, cap: int, mll: float, frac: float = 0.8):
    """Static 'trailing threshold used as the stop' screen: share of trades whose planned stop ($ at the traded size, from the
    trade's `sl`) is >= frac x the trailing threshold. -> (share, share_without_a_stop); (None, 1.0) when no trade carries a stop."""
    n = bad = nos = 0
    for trs in P.days:
        for x in trs:
            n += 1
            if x[6] != x[6]:                                   # nan: no stop on the trade record
                nos += 1
            elif min(micros or x[5], cap) * x[6] * E.PT_USD >= frac * mll:
                bad += 1
    if not n:
        return 0.0, 0.0
    return (bad / (n - nos) if n > nos else None), nos / n


SOFT_FLAGS = ("max_allowed_size_from_day1",)


def hard_flags(f: list) -> list:
    """The flags that make a config NON-COMPLIANT (everything except advisory ones and MAE cuts within the 2% tolerance)."""
    return [x for x in f if x not in SOFT_FLAGS and not (x.startswith("mae30_cuts_") and not x.endswith("_NONCOMPLIANT"))]


def flags(S, strategy: str | None = None, inputs: dict | None = None, rules: dict | None = None, cut_share: float | None = None,
          micros: int | None = None, both_sides: bool | None = None, stop_share: float | None = None, checks: dict | None = None) -> list:
    """Apex Legacy PA compliance flags (empty = none found): R's (OCO families, no target / stop > 5x target, MAE cuts) plus
    both-side working orders declared by the caller, a day_stop >= 80% of the trailing threshold, per-trade stops >= 80% of it,
    the full allowed size from day 1 (advisory: the 'all-in at the start of a PA' prohibition) and, with `checks` (the result
    of `static_checks`), the trade-level findings and every criterion that could NOT be checked (`*_UNCHECKED`)."""
    f = F.apex_flags(strategy, inputs, None, cut_share)
    c = checks or {}
    if (both_sides or c.get("both_side_orders") or c.get("both_side_sessions")) and "OCO_both_side_orders" not in f:
        f.insert(0, "OCO_both_side_orders")
    if c.get("opposite_overlap"):
        f.append(f"opposite_side_overlap_{c['opposite_overlap']}")
    if c.get("one_direction") == "UNCHECKED":
        f.append("one_direction_UNCHECKED")
    if c.get("rows_bad") and "no_target_or_stop_gt_5x_target" not in f:
        f.append("no_target_or_stop_gt_5x_target")
    if c.get("no_stop"):
        f.append(f"no_stop_{c['no_stop']}")
    if c.get("stop_5x_target") == "UNCHECKED":
        f.append("stop_vs_target_UNCHECKED")
    if checks is not None and cut_share is None:
        f.append("mae_rule_UNCHECKED")
    if float((rules or {}).get("day_stop") or 0.0) >= 0.8 * S.mll:
        f.append("day_stop_acts_as_trailing_threshold")
    if stop_share:
        f.append(f"stop_ge_80pct_threshold_{stop_share:.3f}")
    if micros and micros >= S.half:
        f.append("max_allowed_size_from_day1")
    return f


def static_checks(P, strategy: str | None = None, inputs: dict | None = None, both_sides: bool | None = None, trades=None,
                  sess="all", allow_holdout: bool = False) -> dict:
    """The part of the compliance gate that does not depend on size or day rules. Status per criterion: 'ok' | 'FAIL' | 'UNCHECKED'.
    The trade rows count as evidence only when they COVER the portfolio (at least as many rows as the Port has trades, and
    real per-row counts): one clean row does not vouch for 90 trades, a bare {'n': 90} vouches for nothing.
      one_direction   FAIL: both_sides=True, an OCO family (R's table: straddle / orb / lon_break / squeeze nr7|inside / ib break),
                      rows stamped both_sides / oco, a run with both-side sessions, or opposite-side trades that overlap in time.
                      ok (PROVEN, `one_direction_basis`): 'sim_rows' = every row carries the simulator's `both_sides` stamp
                      (all False); 'market_entries' = the caller declares both_sides=False AND every row is a market entry
                      (`order_price` present and null). Otherwise UNCHECKED: a declaration alone proves nothing.
      stop_5x_target  FAIL: a trade without a stop, a row without a target, a row with stop > 5 x target, or inputs['tgt_r'] < 0.2
                      (no target). ok: the covering rows all carry sl and tp within 5:1 (basis 'rows'), or - with NO rows at
                      all - `inputs` GIVE tgt_r >= 0.2 and every trade has a stop (basis 'inputs'). Otherwise UNCHECKED.
    trades = the raw rows (list | path | member list) for the per-trade check, or ready-made statistics (a trade_checks dict
    or shares: n, no_stop_share, no_target_share, stop_gt_5x_target_share); default: `P.apex_trades` (set by port_from_trades)."""
    tc = _as_checks(trades, sess, allow_holdout) if trades is not None else getattr(P, "apex_trades", None)
    pc = port_checks(P)
    r_flags = F.apex_flags(strategy, inputs)
    overlap = max(pc["opposite_overlap"], tc["opposite_overlap"] if tc else 0)
    both_rows = tc["both_side_orders"] if tc else 0
    both_sess = int(tc.get("both_side_sessions") or 0) if tc else 0
    covered = bool(tc and tc["n"] and tc["n"] >= pc["n"] and not tc.get("unproven"))
    one_basis = None
    if both_sides or "OCO_both_side_orders" in r_flags or overlap or both_rows or both_sess:
        one = "FAIL"
    elif covered and tc.get("stamped", 0) == tc["n"]:
        one, one_basis = "ok", "sim_rows"
    elif covered and both_sides is False and tc.get("resting_entries", tc["n"]) == 0:
        one, one_basis = "ok", "market_entries"
    else:
        one = "UNCHECKED"
    no_stop = max(pc["no_stop"], tc["no_stop"] if tc else 0)
    rows_bad = bool(tc and (tc["no_target"] or tc["stop_gt_5x"]))
    tgt = (inputs or {}).get("tgt_r")
    tgt_given = isinstance(tgt, (int, float, np.integer, np.floating)) and not isinstance(tgt, bool) and float(tgt) >= 0.2
    if "no_target_or_stop_gt_5x_target" in r_flags or no_stop or rows_bad:
        rr, basis = "FAIL", ("rows" if rows_bad else "inputs" if "no_target_or_stop_gt_5x_target" in r_flags else "stops")
    elif covered:
        rr, basis = "ok", "rows"
    elif tc is None and tgt_given and pc["n"]:
        rr, basis = "ok", "inputs"
    else:
        rr, basis = "UNCHECKED", None
    return {"one_direction": one, "one_direction_basis": one_basis, "stop_5x_target": rr, "stop_5x_target_basis": basis,
            "opposite_overlap": overlap, "both_side_orders": both_rows, "both_side_sessions": both_sess, "no_stop": no_stop,
            "rows_bad": rows_bad, "rows_cover_port": covered, "trades": tc}


def size_checks(S, P, micros: int | None, start="fresh") -> dict:
    """The size-dependent static screens at the start state: MAE limit, share of trades over it, stops >= 80% of the threshold."""
    st = resolve_start(S, start)
    cap0 = S.cap if st.full else S.half
    lim0 = mae_limit(S, st.profit)
    stop_share, no_stop = stop_over_threshold_share(P, micros, cap0, S.mll)
    return {"mae_limit_at_start": lim0, "mae_over_limit_share": F.mae_over_limit_share(P, micros, cap0, lim0),
            "stop_ge_80pct_threshold_share": stop_share, "no_stop_share": no_stop}


def compliance(S, P, *, micros: int | None = None, rules: dict | None = None, cut_share: float | None = None, start="fresh",
               strategy: str | None = None, inputs: dict | None = None, both_sides: bool | None = None, trades=None, sess="all",
               allow_holdout: bool = False, static: dict | None = None, size: dict | None = None) -> dict:
    """THE Apex compliance gate of one config (evaluate_funded, search and score.py all call this). All three SPEC criteria:
      one_direction / stop_5x_target (see `static_checks`; also FAIL on a day_stop or a per-trade stop >= 80% of the trailing
      threshold) / mae_rule (FAIL when MAE-rule cuts exceed 2% of the executed trades; UNCHECKED without cut_share).
    -> {flags, noncompliant, compliance: {criterion: status}, trade_checks, stop_5x_target_basis, mae_limit_at_start,
        mae_over_limit_share, stop_ge_80pct_threshold_share, no_stop_share}. noncompliant = any criterion not 'ok' (FAIL closed:
    UNCHECKED counts as non-compliant). `static` / `size` take precomputed parts (search)."""
    stc = static if static is not None else static_checks(P, strategy, inputs, both_sides, trades, sess, allow_holdout)
    sz = size if size is not None else size_checks(S, P, micros, start)
    f = flags(S, strategy, inputs, rules, cut_share, micros, both_sides, sz["stop_ge_80pct_threshold_share"], stc)
    rr = stc["stop_5x_target"]
    if "day_stop_acts_as_trailing_threshold" in f or sz["stop_ge_80pct_threshold_share"]:
        rr = "FAIL"
    mae = "UNCHECKED" if cut_share is None else ("FAIL" if cut_share > CUT_OK else "ok")
    crit = {"one_direction": stc["one_direction"], "stop_5x_target": rr, "mae_rule": mae}
    return {"flags": f, "noncompliant": any(v != "ok" for v in crit.values()), "compliance": crit, "trade_checks": stc["trades"],
            "one_direction_basis": stc.get("one_direction_basis"), "stop_5x_target_basis": stc["stop_5x_target_basis"], **sz}


def cross_account_conflicts(accounts: dict) -> dict:
    """Hedging across accounts (prohibited, incl. accounts of household members / related parties): pairs of trades in DIFFERENT
    accounts with opposite sides that overlap in time. accounts = {name: [trade dicts with side, entry_ms, exit_ms]}; side may be
    spelled long / short, buy / sell or +1 / -1 (any case; anything else raises).
    -> {'conflicts': n, 'by_pair': {(a, b): n}, 'examples': [...]}"""
    ev = sorted((int(t["entry_ms"]), int(t.get("exit_ms", t["entry_ms"] + 1)), side_sign(t.get("side", "long")), a)
                for a, ts in accounts.items() for t in ts)
    live, n, by, exs = [], 0, {}, []
    for te, tx, sd, a in ev:
        live = [o for o in live if o[1] > te]
        for o in live:
            if o[3] != a and o[2] != sd:
                n += 1
                k = tuple(sorted((o[3], a)))
                by[k] = by.get(k, 0) + 1
                if len(exs) < 5:
                    exs.append({"accounts": k, "entry_ms": te, "other_entry_ms": o[0]})
        live.append((te, tx, sd, a))
    return {"conflicts": n, "by_pair": by, "examples": exs}


# ------------------------------------------------------------------ one config

def evaluate_funded(P, firm: str = "apex300_pa", *, micros: int | None = None, contracts: float | None = None,
                    micros_allowed: bool = True, rules: dict | None = None, policy=500, dll=None, models=None,
                    H: int = H_LIFE, start="fresh", strategy: str | None = None, inputs: dict | None = None,
                    both_sides: bool | None = None, trades=None, sess="all", allow_holdout: bool = False, **spec_over) -> dict:
    """One config -> {model: metrics} (R/funded.evaluate_funded format) + the compliance gate. firm 'apex300_pa' | 'apex50_pa'
    run here (start = 'fresh' | 'plus3000' | 'plus7600' | number | Start); other firms are delegated to R/funded.evaluate_funded.
    Sizing: micros=n or contracts=x (NQ minis); rules = R day rules (day_take, day_lock, day_stop, max_day_tr, after_loss/win).
    Compliance inputs: strategy / inputs (family + its params), both_sides (True = working orders on both sides; False = the
    caller declares one direction), trades (raw rows for the per-trade sl / tp check; default P.apex_trades).
    Extra keys: cons_base (the selection reading) and cons_alt = {cons_base: other, model: metrics} (the OTHER consistency
    reading, always reported), commission, flags, noncompliant, compliance, trade_checks, warnings, unconfirmed."""
    n = size_micros(contracts, micros, micros_allowed)
    if firm not in EXT_FIRMS:
        return F.evaluate_funded(P, firm, micros=n, rules=rules, policy=policy, dll=dll, models=models, H=H,
                                 strategy=strategy, inputs=inputs, **spec_over)
    S = make_spec(firm, micros_allowed=micros_allowed, **spec_over)
    if n is not None and n > S.cap:
        raise ValueError(f"{n} micros exceeds the {S.name} limit of {S.cap}")
    _seal(P, allow_holdout)
    _need_window(len(P.days), H)
    st = resolve_start(S, start)
    src = day_src(S, P, rules, n)
    S2 = other_cons(S)
    out, alt = {}, {"cons_base": S2.cons_base}
    for m in (models or ORDERS):
        out[m] = metrics(lifecycle(S, src, policy, H, m, st), H)
        alt[m] = metrics(lifecycle(S2, src, policy, H, m, st), H)
    prim = S.primary if S.primary in out else next(iter(out))
    blk = compliance(S, P, micros=n, rules=rules, cut_share=out[prim]["cut_share"], start=st, strategy=strategy, inputs=inputs,
                     both_sides=both_sides, trades=trades, sess=sess, allow_holdout=allow_holdout)
    out.update(primary=S.primary, firm=S.name, start=start_name(start), micros=n, policy=policy, cons_base=S.cons_base,
               cons_alt=alt, commission=S.commission, **blk, warnings=list(ACCOUNT_WARNINGS), unconfirmed=sorted(UNCONFIRMED))
    return out


def evaluate_starts(P, firm: str = "apex300_pa", starts=("fresh", "plus3000", "plus7600"), **kw) -> dict:
    """The same config from each start state -> {start_name: evaluate_funded(...)}."""
    return {start_name(s): evaluate_funded(P, firm, start=s, **kw) for s in starts}


def sensitivity(P, firm: str = "apex300_pa", variants: dict | None = None, starts=("fresh",), model: str | None = None, **kw) -> dict:
    """Rule-uncertainty sensitivity of one config: {(variant, start): metrics of `model` (default the primary)} over VARIANTS
    (the UNCONFIRMED readings) x start states. kw = evaluate_funded arguments (micros, rules, policy, ...)."""
    out, base = {}, make_spec(firm)
    for vn, fn in (variants or VARIANTS).items():
        for s in starts:
            o = evaluate_funded(P, firm, start=s, models=(model or base.primary,), **{**kw, **fn(base)})
            out[(vn, start_name(s))] = o[model or base.primary]
    return out


# ------------------------------------------------------------------ the user's five PAs, run as copies of one account

FIVE_NOTE = ("Five accounts copying one account are ONE bet at five times the size: every account takes the same trades in the same "
             "direction, so with identical start states the $ scale by the number of accounts and the probabilities do not move - "
             "P(at least one payout) = P(all pay) = the single-account P(payout), and P(all bust) = the single-account P(bust). "
             "Copying gives NO diversification. With different start balances the accounts still see the same trades; outcomes "
             "differ only through each account's state (threshold room, half size, payout clock).")


def _joint(per_account: list, H: int) -> dict:
    """per_account = one list of attempt tuples per account, aligned on the rolling start -> joint metrics over the starts."""
    N = len(per_account[0])
    a = len(per_account)

    def first(r):
        return r[1][0][0] if r[1] else 0

    def net(r, k):
        return sum(p[2] for p in r[1] if p[0] <= k)

    out = {"n": N}
    for key, k in (("e_total_40", 40), ("e_total_60", H)):                       # '60' = the whole horizon, as R's e_net_60
        out[key] = float(np.mean([sum(net(acc[i], k) for acc in per_account) for i in range(N)])) if N else None
    for k, key in ((20, "20"), (40, "40"), (H, "60")):
        paid = np.array([[0 < first(acc[i]) <= k for acc in per_account] for i in range(N)], bool).reshape(N, a)
        out[f"p_any_payout_{key}"] = float(paid.any(1).mean()) if N else None
        out[f"p_all_payout_{key}"] = float(paid.all(1).mean()) if N else None
    bust = np.array([[acc[i][0] > 0 for acc in per_account] for i in range(N)], bool).reshape(N, a)
    pre = np.array([[acc[i][0] > 0 and not acc[i][1] for acc in per_account] for i in range(N)], bool).reshape(N, a)
    out.update(p_all_bust=float(bust.all(1).mean()) if N else None, p_any_bust=float(bust.any(1).mean()) if N else None,
               p_all_bust_pre_first=float(pre.all(1).mean()) if N else None)
    return out


def five_accounts(plan: dict, n: int = 5) -> dict:
    """The user's FIVE identical Apex Legacy 300K PAs run as COPIES of one account (same trades, same size, same direction at
    every moment - the only multi-account layout that can never breach the cross-account hedging rule).

    plan = the evaluate_funded arguments of the ONE account being copied, as a dict: 'P' (a Port) or 'trades' (+ 'sess',
    'begin' / 'end' / 'calendar' of the window), 'micros', 'rules', 'policy', 'model', 'H', 'strategy', 'inputs', 'both_sides',
    spec overrides (by name, or under 'spec'), and either 'start' (all accounts in the same state; default 'fresh' = the
    user's five PAs at $300,000) or 'starts' (a list of n start states, one per account).
    A finished evaluate_funded(...) result is accepted too (identical copies: derived without re-running).

    -> {n_accounts, identical, model, e_total_40, e_total_60 (E[$ to the trader, all accounts]), p_any_payout_20/40/60,
        p_all_payout_20/40/60, p_all_bust, p_any_bust, p_all_bust_pre_first, single (the one-account metrics per distinct start),
        cons_base + cons_alt (the same numbers under the other consistency reading), noncompliant / flags / compliance, note}.
    With identical start states this is TRIVIALLY the single-account lifecycle: $ x n, probabilities unchanged (`note`)."""
    if n < 1:
        raise ValueError("n must be >= 1")
    if "P" not in plan and "trades" not in plan:                                # a finished single-account result
        if "primary" not in plan or plan.get("primary") not in plan:
            raise ValueError("plan must hold 'P' or 'trades' (evaluate_funded arguments), or be an evaluate_funded(...) result")

        def from_single(m):
            return {"n": m["n"], "e_total_40": n * m["e_net_40"], "e_total_60": n * m["e_net_60"],
                    **{f"p_{w}_payout_{k}": m[f"p_pay_{k}"] for w in ("any", "all") for k in ("20", "40", "60")},
                    "p_all_bust": m["p_bust_any"], "p_any_bust": m["p_bust_any"], "p_all_bust_pre_first": m["p_bust_pre_first"]}

        prim = plan["primary"]
        out = {"n_accounts": n, "identical": True, "model": prim, "starts": [plan.get("start", "fresh")] * n, **from_single(plan[prim]),
               "single": {plan.get("start", "fresh"): plan[prim]}, "cons_base": plan.get("cons_base"), "note": FIVE_NOTE}
        if isinstance(plan.get("cons_alt"), dict) and prim in plan["cons_alt"]:
            out["cons_alt"] = {"cons_base": plan["cons_alt"]["cons_base"], **from_single(plan["cons_alt"][prim])}
        for k in ("noncompliant", "flags", "compliance", "firm", "micros", "policy"):
            if k in plan:
                out[k] = plan[k]
        out.setdefault("noncompliant", True)                   # a result without the gate's verdict is not compliant (fail closed)
        return out
    kw = dict(plan)
    allow = bool(kw.pop("allow_holdout", False))
    P = kw.pop("P", None)
    trades, sess = kw.pop("trades", None), kw.pop("sess", "all")
    pkw = {k: kw.pop(k) for k in ("calendar", "begin", "end") if k in kw}       # window of a port built here
    if P is None:
        if "begin" in pkw:
            pkw["start"] = pkw.pop("begin")
        P = port_from_trades(trades, sess=sess, allow_holdout=allow, **pkw)
        trades = None                                                           # P.apex_trades carries the row checks
    firm = kw.pop("firm", "apex300_pa")
    if firm not in EXT_FIRMS:
        raise ValueError(f"five_accounts models {EXT_FIRMS} only")
    starts = kw.pop("starts", None)
    start = kw.pop("start", "fresh")
    starts = [start] * n if starts is None else list(starts)
    if len(starts) != n:
        raise ValueError(f"'starts' must list one start state per account ({n}), got {len(starts)}")
    H, policy, model = kw.pop("H", H_LIFE), kw.pop("policy", 500), kw.pop("model", None)
    rules, micros = kw.pop("rules", None), size_micros(kw.pop("contracts", None), kw.pop("micros", None))
    strategy, inputs, both_sides = kw.pop("strategy", None), kw.pop("inputs", None), kw.pop("both_sides", None)
    S = make_spec(firm, **{**kw.pop("spec", {}), **kw})
    if micros is not None and micros > S.cap:
        raise ValueError(f"{micros} micros exceeds the {S.name} limit of {S.cap}")
    _seal(P, allow)
    _need_window(len(P.days), H)
    model = model or S.primary
    src = day_src(S, P, rules, micros)
    res = [resolve_start(S, s) for s in starts]
    distinct = list(dict.fromkeys(res))
    out = {"n_accounts": n, "identical": len(distinct) == 1, "model": model, "firm": S.name, "micros": micros, "policy": policy,
           "starts": [start_name(s) for s in starts], "cons_base": S.cons_base}
    for key, spec in ((None, S), ("cons_alt", other_cons(S))):
        life = {st: lifecycle(spec, src, policy, H, model, st) for st in distinct}
        j = _joint([life[st] for st in res], H)
        if key is None:
            out.update(j)
            mets = {st: metrics(life[st], H) for st in distinct}
            out["single"] = {}
            for s, st in zip(starts, res):
                out["single"].setdefault(start_name(s), mets[st])
        else:
            out[key] = {"cons_base": spec.cons_base, **j}
    cut = max(m["cut_share"] for m in out["single"].values())
    blk = compliance(S, P, micros=micros, rules=rules, cut_share=cut, start=min(res, key=lambda s: s.profit), strategy=strategy,
                     inputs=inputs, both_sides=both_sides, trades=trades, sess=sess, allow_holdout=allow)
    out.update(noncompliant=blk["noncompliant"], flags=blk["flags"], compliance=blk["compliance"],
               cross_account="copies of one account: the same direction in every account at every moment (no cross-account hedge)",
               note=FIVE_NOTE, warnings=list(ACCOUNT_WARNINGS))
    return out


# ------------------------------------------------------------------ the Legacy 300K EVALUATION (score.py firm 'apex300_eval')

EVAL_H = (10, 20)                                              # reported horizons, trading days: P(pass <= 10 / 20)
_EVAL = dict(
    name="apex300_eval", kind="apex_eval", start_balance=300000.0, target=20000.0, mll=7500.0, trail="intraday",
    lock_at=None, lock_floor=None, cap=350, min_days=7, days_count="traded", commission="apex", primary="pess")
# name -> spec overrides: the readings the default (help centre, conservative) does not take
EVAL_VARIANTS = {
    # the account holder's wording in homebase/backtest/propsim/rules/apex-legacy-300k@2026-09-28.json (accounts bought earlier):
    # EOD trail that locks at +$100 once the EOD peak reaches +$7,600, a single day can pass. R's cost model, as that file is scored.
    "holder_rule_file": dict(trail="eod", lock_at=7600.0, lock_floor=100.0, min_days=1, commission="R"),
    "min_days_1": dict(min_days=1),                            # a 1-day-pass promotion on the help-centre rules
    "trail_eod": dict(trail="eod"),
}
EVAL_UNCONFIRMED = {
    "min_days": "help centre: 7 trading days unless a 1-day-pass promotion is active; the homebase rule file (account holder) says 1",
    "trail": "help centre: intraday on the highest live balance; the homebase rule file (account holder) says EOD trail",
    "lock": "Tradovate: the threshold keeps trailing through the evaluation (modelled); Rithmic: it stops once it reaches the "
            "target level; the homebase rule file locks it at +$100",
    "commission": "as apex300_pa: the dearer of Apex's Tradovate / Rithmic schedules per instrument",
    "purchasable": EVAL300["status"],
}


def make_eval_spec(**over) -> F.Spec:
    """The Apex Legacy 300K EVALUATION as a spec for `eval_sim` (APEX300_RULES.md section 2b, help-centre reading = the
    conservative one): profit goal $20,000 (the balance must CLOSE at / above it), trailing threshold $7,500 below the highest
    LIVE balance (intraday, open P&L included; it keeps trailing: no lock), 35 minis = 350 micros, no daily loss limit, no
    scaling, no consistency rule, 7 traded days minimum. Overrides: any key, commission='apex' | 'tradovate' | 'rithmic' | 'R',
    or a whole reading through **EVAL_VARIANTS[name]."""
    d = dict(_EVAL)
    unknown = sorted(set(over) - set(d))
    if unknown:
        raise ValueError(f"unknown eval spec override(s) {unknown}; valid names: {sorted(d)}")
    d.update(over)
    if d["commission"] not in COMMISSIONS:
        raise ValueError(f"unknown commission schedule {d['commission']!r}; valid: {sorted(COMMISSIONS)}")
    if d["trail"] not in ("intraday", "eod"):
        raise ValueError(f"trail {d['trail']!r} not in ('intraday', 'eod')")
    if (d["lock_at"] is None) != (d["lock_floor"] is None):
        raise ValueError("lock_at and lock_floor must be given together")
    nq, mnq = COMMISSIONS[d["commission"]] or (None, None)
    d.update(comm_nq=nq, comm_mnq=mnq)
    return F.Spec(**d)


class EvalSrc(DaySrc):
    """Day walks for the evaluation: `DaySrc` (R's walk_day on the spec's commission schedule, events on) + walks with a
    per-attempt TARGET-TAKE level (`take`), R's target_take law (evalcore._walk_day `tt`): the day is flattened once its open
    equity reaches level + 1 tick per contract and ENDS AT the level (the tick pays the exit slippage), which is how an
    attempt stops on the day it reaches the profit goal. With a day_take rule X the earlier trigger of the two applies."""

    def take(self, i, cap, level):
        trs = self.P.days[i]
        scaled = self.rl[3] != 1.0 or self.rl[4] != 1.0            # after_loss / after_win may change the size: allow for the cap
        n = max([cap if scaled else min(self.micros or t[5], cap) for t in trs] or [0])
        tk = level + TICK_USD * n                                  # walk_day's day_take fills at tk - 1 tick x n = the level
        if self.tk and self.tk < tk:
            tk = self.tk
        key = (i, cap, "take", tk)
        o = self.memo.get(key)
        if o is None:
            if not trs:
                o = (0.0, 0.0, 0.0, 0, (), (), 0, ())
            else:
                mf = getattr(self.P, "mfe", None)
                old = F.cost
                if self.comm is not None:
                    nq, mnq = self.comm
                    F.cost = lambda n: (n // 10) * nq + (n % 10) * mnq
                try:
                    o = F.walk_day(trs, mf[i] if mf else None, cap, self.rl, self.micros, 0.0, tk, 0.0, True)
                finally:
                    F.cost = old
            self.memo[key] = o
        return o


def eval_src(S, P, rules: dict | None = None, micros: int | None = None) -> EvalSrc:
    return EvalSrc(P, rules, micros, True, comm_of(S))


def eval_sim(S, src, s: int, H: int = EVAL_H[-1], order: str = "pess", target_take: bool = False, coast: int = 0) -> tuple:
    """One evaluation attempt from session s -> (outcome 0 neither | 1 pass | 2 bust, day 1-based (H when neither), traded days).
    Each session: the day's equity events (R's walk_day; order 'pess' = every trade's best point lifts the trailing peak before
    its worst point is tested, 'nat', 'opt') are run against the threshold = peak - mll (trail 'intraday': the peak includes
    intraday highs; 'eod': closes only; with lock_at the threshold stops at lock_floor once the peak reaches lock_at). A low at /
    below the threshold = BUST. At the close: PASS when profit >= target and traded days >= min_days.
    target_take: on a day the attempt CAN pass (traded days + 1 >= min_days) the day is flattened at the level that reaches the
    goal (-1 tick, R's day_take law). coast (micros, 0 = off): once the profit is at / above the goal but days are missing, the
    remaining days are traded at `coast` micros (1 = tick the days off at minimum size)."""
    sel = {"pess": 4, "opt": 5, "nat": 7}[order]
    intraday = S.trail == "intraday"
    lock_at, lock_floor, mll = S.lock_at, S.lock_floor, S.mll
    profit = peak = 0.0
    td = 0
    for k in range(H):
        cap = S.cap
        if coast and profit >= S.target:
            cap = min(cap, int(coast))
        if target_take and profit < S.target and td + 1 >= S.min_days:
            o = src.take(s + k, cap, S.target - profit)
        else:
            o = src.get(s + k, cap, 0.0, 0.0)
        pk = peak
        for kind, v in o[sel]:
            x = profit + v
            if kind:
                if intraday and x > pk:
                    pk = x
            elif x <= (lock_floor if (lock_at is not None and pk >= lock_at) else pk - mll):
                return 2, k + 1, td
        peak = pk
        profit += o[0]
        if profit > peak:                                       # the close is a balance too (the only peak under trail 'eod')
            peak = profit
        if S.days_count == "all" or o[3] > 0:
            td += 1
        if profit >= S.target and td >= S.min_days:
            return 1, k + 1, td
    return 0, H, td


def eval_lifecycle(S, src, H: int = EVAL_H[-1], order: str | None = None, target_take: bool = False, coast: int = 0,
                   starts=None) -> tuple:
    """Every rolling start with a full H-session horizon -> (outcome[S] int8, day[S] int16) (evalcore.race's layout)."""
    order = order or S.primary
    if order not in ORDERS:
        raise ValueError(f"apex model {order!r} not in {ORDERS}")
    starts = range(max(src.n_days - H + 1, 0)) if starts is None else starts
    res = [eval_sim(S, src, s, H, order, target_take, coast) for s in starts]
    return (np.array([r[0] for r in res], np.int8), np.array([r[1] for r in res], np.int16))


def eval_metrics(out, day, horizons=EVAL_H) -> dict:
    """{p_pass_<h>, bust_<h>, neither_<h> for h in horizons, med_days (to pass), n}: an attempt that passes / busts after day h
    counts as 'neither' at h. Empty arrays -> None values."""
    n = int(len(out))
    m = {"n": n}
    for h in horizons:
        ps, bs = (out == 1) & (day <= h), (out == 2) & (day <= h)
        m[f"p_pass_{h}"] = float(ps.mean()) if n else None
        m[f"bust_{h}"] = float(bs.mean()) if n else None
        m[f"neither_{h}"] = float(1.0 - ps.mean() - bs.mean()) if n else None
    ps = out == 1
    m["med_days"] = float(np.median(day[ps])) if n and ps.any() else None
    return m


# ------------------------------------------------------------------ offline compute windows

WINDOWS_DAILY = ((dt.time(9, 18), dt.time(9, 36)),)                         # weekdays: the live desk trades at 09:30 ET
WINDOWS_DATED = ((dt.date(2026, 10, 2), dt.time(8, 15), dt.time(8, 50)),)   # Fri 2026-10-02: live NFP trade


def compute_window_wait(now: dt.datetime | None = None, sleep=time.sleep) -> float:
    """Sleep out an offline-compute window (SPEC house rule). Returns the seconds slept (0 outside the windows)."""
    t = now or dt.datetime.now(E.ET)
    wins = [(a, b) for a, b in WINDOWS_DAILY if t.weekday() < 5] + [(a, b) for d, a, b in WINDOWS_DATED if d == t.date()]
    total = 0.0
    for a, b in sorted(wins):
        if a <= t.time() < b:
            end = t.replace(hour=b.hour, minute=b.minute, second=5, microsecond=0)
            sec = (end - t).total_seconds()
            sleep(sec)
            total += sec
            t = end
    return total


# ------------------------------------------------------------------ search (R/funded.search format, + start state)

GRID = {"micros": [10, 20, 30, 40, 50, 75, 100, 125, 150, 170], "day_take": [0, 500, 1000, 1500, 2250, 3000],
        "day_lock": [0, 1000, 2000, 3000], "day_stop": [0, 750, 1500, 2250], "max_day_tr": [1, 0],
        "policy": list(POLICIES["apex300_pa"])}
AXES = F.AXES
ALT_KEYS = ("e_net_40", "e_net_60", "p_pay_20", "p_pay_40", "p_pay_60", "p_bust_pre_first", "p_bust_any")
_G: dict = {}


def _cell(combo):
    """One (micros, day_take, day_lock, day_stop, max_day_tr) cell -> rows, one per policy (fork worker / inline)."""
    compute_window_wait()
    P, S, g, model, H, st, S2 = _G["P"], _G["S"], _G["grid"], _G["model"], _G["H"], _G["start"], _G["other"]
    mi, tk, dl, ds, mt = (g[a][i] for a, i in zip(AXES[:5], combo))
    rules = {"day_take": tk, "day_lock": dl, "day_stop": ds, "max_day_tr": mt}
    src = day_src(S, P, rules, mi)
    sz = size_checks(S, P, mi, st)
    rows = []
    for pi, T in enumerate(g["policy"]):
        m = metrics(lifecycle(S, src, T, H, model, st), H)
        row = {"firm": S.name, "start": _G["start_name"], "model": model or S.primary, "cons_base": S.cons_base, "micros": mi,
               "day_take": tk, "day_lock": dl, "day_stop": ds, "max_day_tr": mt, "policy": T,
               "n_rules": sum(bool(x) for x in (tk, dl, ds, mt)), "_ix": combo + (pi,), **m}
        if S2 is not None:
            a = metrics(lifecycle(S2, src, T, H, model, st), H)
            row.update({f"{k}_cons_{S2.cons_base}": a[k] for k in ALT_KEYS})
        blk = compliance(S, P, micros=mi, rules=rules, cut_share=m.get("cut_share"), start=st, strategy=_G["strategy"],
                         inputs=_G["inputs"], both_sides=_G["both_sides"], static=_G["static"], size=sz)
        row.update(mae_over_limit_share=sz["mae_over_limit_share"], apex_one_direction=blk["compliance"]["one_direction"],
                   apex_stop_5x_target=blk["compliance"]["stop_5x_target"], apex_mae_rule=blk["compliance"]["mae_rule"],
                   apex_flags=";".join(blk["flags"]), apex_noncompliant=blk["noncompliant"])
        rows.append(row)
    return rows


def search(P, S=None, grid: dict | None = None, model: str | None = None, H: int = H_LIFE, workers: int = 1, start="fresh", *,
           strategy: str | None = None, inputs: dict | None = None, both_sides: bool | None = None, trades=None, sess="all",
           both_cons: bool = True, allow_holdout: bool = False) -> list:
    """Grid over micros x day_take x day_lock x day_stop x max_day_tr x policy for an extended Apex spec (default apex300_pa).
    Rows as R/funded.search (+ start, cons_base, mae_over_limit_share), with stab_/score_ columns for e_net_40 and p_pay_20.
    Every row carries the SAME compliance gate as evaluate_funded (`compliance`): apex_one_direction / apex_stop_5x_target /
    apex_mae_rule ('ok' | 'FAIL' | 'UNCHECKED'), apex_flags and apex_noncompliant - so pass strategy / inputs / both_sides
    (and `trades` unless P came from port_from_trades); without them the rows are UNCHECKED = non-compliant.
    both_cons (default): the key metrics under the OTHER consistency reading as `<metric>_cons_<other>` columns.
    workers is capped at 8 (house rule); every cell waits out the offline compute windows."""
    S = S or make_spec("apex300_pa")
    if not getattr(S, "ext", False):
        raise ValueError("apex300.search needs an apex300_pa / apex50_pa spec; use R/funded.search for the other firms")
    _seal(P, allow_holdout)
    _need_window(len(P.days), H)
    g = {**GRID, **(grid or {})}
    if grid is None or "policy" not in grid:
        g["policy"] = list(POLICIES.get(S.name, POLICIES["apex300_pa"]))
    g["micros"] = [m for m in g["micros"] if m <= S.cap]
    _G.update(P=P, S=S, grid=g, model=model, H=H, start=resolve_start(S, start), start_name=start_name(start),
              other=other_cons(S) if both_cons else None, strategy=strategy, inputs=inputs, both_sides=both_sides,
              static=static_checks(P, strategy, inputs, both_sides, trades, sess, allow_holdout))
    combos = list(itertools.product(*[range(len(g[a])) for a in AXES[:5]]))
    workers = max(1, min(int(workers), MAX_WORKERS))
    if workers > 1:
        compute_window_wait()
        with mp.get_context("fork").Pool(workers) as pool:
            parts = pool.map(_cell, combos, chunksize=max(1, len(combos) // (workers * 8)))
    else:
        parts = [_cell(c) for c in combos]
    rows = [r for part in parts for r in part]
    F.add_stability(rows, ("e_net_40", "p_pay_20"))
    return rows


pick_cells = F.pick_cells
write_csv = F.write_csv


def compliant(rows: list) -> list:
    """Rows of a search that PASS the Apex compliance gate: one direction proven, stop <= 5 x target proven on every trade (a
    stop and a target on every trade, no threshold-sized stop), MAE-rule cuts <= 2% of trades. Rows with a FAILED or an
    UNCHECKED criterion (or without the verdict) are excluded."""
    return [r for r in rows if r.get("apex_noncompliant") is False]


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Apex Legacy 300K PA lifecycle: one config or a grid on a trades.json (R schema, per 1 NQ)")
    ap.add_argument("trades", help="path to trades.json (in-sample rows only; the holdout is sealed)")
    ap.add_argument("--firm", default="apex300_pa", choices=EXT_FIRMS)
    ap.add_argument("--sess", default="all")
    ap.add_argument("--micros", type=int, default=None)
    ap.add_argument("--policy", default="500")
    ap.add_argument("--start", default="fresh,plus3000,plus7600")
    ap.add_argument("--strategy", default=None, help="family name (R's OCO table: straddle / orb / lon_break ... are non-compliant)")
    ap.add_argument("--one-direction", action="store_true", help="declare that the config never works orders on both sides")
    ap.add_argument("--both-sides", action="store_true", help="the config works orders on both sides (OCO / straddle): non-compliant")
    ap.add_argument("--five", action="store_true", help="also print the five-copies view (five_accounts)")
    ap.add_argument("--search", action="store_true")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--tag", default="apex300")
    a = ap.parse_args(argv)
    P = port_from_trades(a.trades, sess=a.sess)
    T = a.policy if a.policy == "max" else int(a.policy)
    bs = True if a.both_sides else (False if a.one_direction else None)
    for st in a.start.split(","):
        if a.search:
            rows = search(P, make_spec(a.firm), workers=a.workers, start=st, strategy=a.strategy, both_sides=bs)
            (L / "out").mkdir(exist_ok=True)
            write_csv(rows, L / "out" / f"funded_search_{a.tag}_{a.firm}_{st}.csv")
            ok = compliant(rows)
            print(f"[{a.firm} {st}] {len(ok)} of {len(rows)} rows pass the compliance gate")
            for k, r in pick_cells(ok).items():
                print(f"[{a.firm} {st}] {k}: {F._fmt(r)}")
        else:
            o = evaluate_funded(P, a.firm, micros=a.micros or 10, policy=T, start=st, strategy=a.strategy, both_sides=bs)
            m, alt = o[o["primary"]], o["cons_alt"][o["primary"]]
            print(f"[{a.firm} {st}] m{o['micros']} T{T} cons={o['cons_base']}: E$40={m['e_net_40']:.0f} "
                  f"(cons={o['cons_alt']['cons_base']}: {alt['e_net_40']:.0f}) P20={m['p_pay_20']:.2f} P40={m['p_pay_40']:.2f} "
                  f"P60={m['p_pay_60']:.2f} med={m['med_days_first']} chq={m['e_first_gross']:.0f} bustPre={m['p_bust_pre_first']:.2f} "
                  f"cuts={m['cut_share']:.3f} noncompliant={o['noncompliant']} {o['compliance']} flags={o['flags']}")
            if a.five:
                f = five_accounts(o)
                print(f"   five copies: E$40 total={f['e_total_40']:.0f} P(any payout<=40d)={f['p_any_payout_40']:.2f} "
                      f"P(all bust)={f['p_all_bust']:.2f}  (no diversification: same trades in every account)")


if __name__ == "__main__":
    main()
