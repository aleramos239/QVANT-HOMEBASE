"""Homebase config: strategies, accounts, and the BOOK that joins them.

The frozen strategy geometry (offset / SL / TP / times) lives HERE,
server-side. A signal only carries prices; anything the wire says is
validated against this file before an order exists.

The book is the portfolio: strategy -> [{account, qty}, ...]. One signal
fans out to every assigned account at that account's qty. One account may
appear under many strategies.
"""
from __future__ import annotations

import json
import os
import logging
from dataclasses import asdict, dataclass, field

from .netguard import clean_entry
from .paths import config_path


@dataclass
class StrategyCfg:
    symbol: str                  # canonical, e.g. "NQ" (front month resolved live)
    qty: int                     # spec/default size — the BOOK sets per-account qty
    offset_pts: float            # entry stops sit this far off the anchor close
    sl_pts: float                # protective stop, points from entry trigger
    tp_pts: float                # target, points from entry trigger
    cancel_et: str = "12:55"     # unfilled entries are cancelled here
    flat_et: str = "15:55"       # any open position is force-flattened here
    accept_from_et: str = "09:29"   # alerts outside this ET window are refused
    accept_until_et: str = "09:45"
    enabled: bool = False
    gated: bool = False          # True = a no-alert day can be the regime gate
    self_fire: bool = False      # True: the APP computes and fires the signal;
                                 # False: a Pine alert feeds /hook
    pine_file: str = ""          # committed Pine source (homebase/research/)
    metrics: dict = field(default_factory=dict)   # research record, display-only
    kind: str = "straddle"       # "straddle": two stop legs at the anchor (timer/Pine)
                                 # "bars": a price-action RULE on closed bars (feed)
                                 # "levels": OCO stop entries from a NEW geometry each day (ATR / opening
                                 #   range), fired at fire_et by leveltimer.LevelTimer; daily rules below
    shadow: bool = False         # True: signals are journaled, never placed —
                                 # even when the app is armed (forward paper)
    rule: str = ""               # bars: name in rules.RULES
    bar_minutes: int = 1         # bars: the rule's timeframe
    warmup_bars: int = 60        # bars: history loaded before the rule runs
    fire_et: str = "09:30:00"    # straddle: the ET moment the anchor is read and the legs go out.
                                 # The timer's gate / prestage / done times hang off it (-10 min,
                                 # -90 s, +1 min); 09:30:00 is the original schedule, unchanged.
    only_dates: list = field(default_factory=list)   # ISO ET dates it trades; empty = every weekday

    def trades_on(self, date) -> bool:
        """Does this strategy trade on `date` (a date or an ISO string)? An empty `only_dates`
        means every weekday; otherwise only the listed days (an event-day strategy)."""
        return not self.only_dates or str(date) in {str(d) for d in self.only_dates}
    # ---- kind "levels" (homebase/levels.py, homebase/leveltimer.py): spec 2026-10-01 ----
    shape: str = ""              # levels: "atr_straddle" | "orb"
    atr_tf: int = 30             # levels: ATR(14, Wilder) bar size, minutes, restarting at 00:00 ET
    off_atr: float = 0.0         # atr_straddle: entry offset, x ATR
    sl_atr: float = 3.0          # levels: stop distance from the trigger, x ATR
    or_min: int = 5              # orb: opening-range minutes before the fire
    tgt_r: float = 2.0           # levels: with no take rule the target is tgt_r x the stop distance
    fee_rt: float = 4.0          # levels: $ commission per contract per round turn (NQ mini)
    day_take: float = 0.0        # $ net: the day's open + closed P&L reaches it -> flatten, stop for the day
    day_lock: float = 0.0        # $ closed: a trade closes with the day >= it -> no new entry today
    target_take: bool = False    # eval accounts: take = the account's remaining distance to pass
    size_tiers: list = field(default_factory=list)   # [[EOD profit >=, contracts], ...]; the book's qty caps it
    skip_early_close: bool = False   # levels: no fire on a half day (13:15 close) when flat_et is after the close
    ack_open_loss: bool = False  # levels: the account holder accepts that the 3 x ATR stop is several times a
                                 # prop account's max loss (Lucid's open-loss rule unconfirmed): without it
                                 # a REAL (non-paper) account sits out


@dataclass
class AccountCfg:
    keyring_key: str = ""        # credentials key in secrets_store
    account_name: str = ""       # pin one account under the login
    live: bool = False           # False = demo environment
    label: str = ""              # display name (defaults to account_name)
    paper: bool = False          # a chart-service paper account (homebase.broker.paper): no login, no broker
    # prop-account standing for the daily rules (kind "levels"): {"rules": "<propsim rule id>",
    # "start_balance": 50000, "largest_day": 0, "days": 0}.  `rules` supplies the eval target / minimum
    # days / consistency (backtest/propsim/rules); largest_day / days seed what the desk's own daily
    # balance record does not yet cover.  Empty = no standing: tiers use their smallest size, target_take
    # has no level.
    prop: dict = field(default_factory=dict)


HARD_MAX_ORDER_QTY = 50        # the desk page cannot set chart-trading limits above these
HARD_MAX_POSITION_QTY = 100


@dataclass
class ChartTradingCfg:
    enabled: bool = False        # orders from the chart page; off until switched on
    max_order_qty: int = 10      # per order, per account
    max_position_qty: int = 20   # worst-case |net| per contract, per account


def chart_trading_from(d) -> ChartTradingCfg:
    """config.json's chart_trading block; anything malformed -> the safe
    defaults (off). `enabled` must be the JSON literal true."""
    base = ChartTradingCfg()
    if not isinstance(d, dict):
        return base
    try:
        c = ChartTradingCfg(enabled=d.get("enabled") is True,
                            max_order_qty=int(d.get("max_order_qty", base.max_order_qty)),
                            max_position_qty=int(d.get("max_position_qty", base.max_position_qty)))
    except (TypeError, ValueError):
        return base
    if not (1 <= c.max_order_qty <= HARD_MAX_ORDER_QTY
            and 1 <= c.max_position_qty <= HARD_MAX_POSITION_QTY):
        return base
    return c


log = logging.getLogger(__name__)


def warn_bad_allowed_hosts(v) -> None:
    """Log each allowed_hosts entry netguard cannot match (it is ignored by
    the allowlist). The raw value itself stays in the config, untouched, so
    save() never erases what the user wrote."""
    if not isinstance(v, list):
        log.warning("config allowed_hosts is not a list, ignored: %r", v)
        return
    for e in v:
        if clean_entry(e) is None:
            log.warning("config allowed_hosts entry ignored (a bare hostname or IP, "
                        "no port, no brackets, no wildcard): %r", e)


@dataclass
class AppCfg:
    armed: bool = False          # master switch: disarmed = journal-only dry run
    webhook_secret: str = ""     # shared secret the TV alert must carry
    hook_port: int = 8851        # hook-ONLY listener — the only tunneled port
    public_hook_url: str = ""    # the tunnel's public origin, once one is up
    accounts: dict[str, AccountCfg] = field(default_factory=dict)
    book: dict[str, list] = field(default_factory=dict)   # strategy -> [{account, qty}]
    strategies: dict[str, StrategyCfg] = field(default_factory=dict)
    chart_trading: ChartTradingCfg = field(default_factory=ChartTradingCfg)
    # hostnames / IPs, besides loopback, that may WRITE to the desk (e.g. a
    # Tailscale MagicDNS name or 100.x IP); exact match, no port, no wildcard.
    # Kept RAW as written in config.json; netguard.allowlist() cleans it.
    allowed_hosts: list[str] = field(default_factory=list)


def _defaults() -> AppCfg:
    return AppCfg(
        strategies={
            # NQ 9:30 straddle — the approved champion (spec 2026-09-09,
            # OOS-passed 2026-09-10). The TREND gate runs in-app (self_fire)
            # and in the Pine script alike.
            "nq930": StrategyCfg(
                symbol="NQ", qty=3, offset_pts=10.0, sl_pts=5.0, tp_pts=15.0,
                enabled=True, gated=True, self_fire=True, pine_file="nq930.pine",
                metrics={
                    "source": "one-shot sealed-year OOS exam · 2025-07-08→2026-07-07 · TV 15s",
                    "rows": {"trades": "167", "WR": "47.3%", "PF": "2.34",
                             "t": "5.04", "avg/trade/mini": "$79.0",
                             "maxDD/mini": "−$1,135", "green months": "10/10"},
                    "caveat": "does not cover live fill quality — the edge is 2–4 ticks deep",
                    "equity_file": "nq930_equity.json",
                }),
            # YM 9:30 straddle (OOS-passed 2026-09-13), unfiltered, app-timed
            # like NQ. Disabled until the user sizes and enables it.
            "ym930": StrategyCfg(
                symbol="YM", qty=1, offset_pts=20.0, sl_pts=5.0, tp_pts=15.0,
                enabled=False, gated=False, self_fire=True, pine_file="ym930.pine",
                metrics={
                    "source": "one-shot OOS exam · 2025-01-07→2026-09-10 · TV 15s",
                    "rows": {"trades": "434", "WR": "50.7%", "PF": "1.76",
                             "t": "5.76", "avg/trade": "$14.51",
                             "maxDD": "−$316", "green months": "19/21"},
                    "caveat": "modeled friction is already 56% of the $25 risk — thin book",
                    "equity_file": "ym930_equity.json",
                }),
            # 10am NQ continuation — a CANDIDATE (spec 2026-09-06, unvalidated).
            # The first price-action strategy on the app's own feed: runs in
            # SHADOW (journals what it would do, places nothing) so the path is
            # proven and forward evidence accrues. Arming it is a user decision.
            "nq10am": StrategyCfg(
                symbol="NQ", qty=1, offset_pts=0.0, sl_pts=0.0, tp_pts=0.0,
                accept_from_et="09:59", accept_until_et="10:05",
                enabled=True, shadow=True, self_fire=True, kind="bars",
                rule="nq_10am_continuation", bar_minutes=1, warmup_bars=60,
                metrics={
                    "source": "candidate · 2023-07-07→2025-07-07 · 1m · $300 risk · UNVALIDATED",
                    "rows": {"trades": "264", "TP rate": "59.5%", "RR": "1:0.81",
                             "t": "2.76 (uncorrected)", "net": "+$10,574",
                             "maxDD": "−$1,447", "days green": "63.6%"},
                    "caveat": "post-hoc filter, ~130 cells on one window — shadow only",
                }),
            # GC 08:30 NFP straddle (verified 2026-10-01, research/nfp-2026-10-02/verify): 4 gold
            # contracts, OCO stops at anchor +/- 2.0, SL 5.0 (-$2,000 before slippage: the user's choice 2026-10-01, a stop-out ends the eval), TP 7.7
            # (+$3,080 gross, +$3,061.60 after $2.30 a side), unfilled cancelled 08:45, flat 09:55.
            # Fires 08:29:59 (the user's choice 2026-10-01): the stops rest at the exchange before the release;
            # tested on 57 NFPs, same pass rate as 08:30:00.
            # Trades ONLY the days in only_dates (2026-10-02, the BLS NFP date; extend it by hand).
            # accept_until 08:31: a fire more than a minute late is refused, not re-anchored on a
            # post-release price. Ships off and unbooked: the user books the evals and enables it.
            "gc_nfp": StrategyCfg(
                symbol="GC", qty=4, offset_pts=2.0, sl_pts=5.0, tp_pts=7.7,
                cancel_et="08:45", flat_et="09:55",
                accept_from_et="08:29", accept_until_et="08:31",
                enabled=False, gated=False, self_fire=True,
                fire_et="08:29:59", only_dates=["2026-10-02"],
                metrics={
                    "source": "NFP-only tick replay · 57 events 2021-10..2026-09 · the 2025-26 part was "
                              "already spent on this family: a consistency check, not a clean exam",
                    "rows": {"entry": "OCO stops anchor ±2.0 (anchor = last print before 08:29:59; orders rest before the 08:30 release)",
                             "SL": "5.0 pts · $500/ct · $2,000 at 4 ct (a stop-out ends the eval)",
                             "TP": "7.7 pts · $770/ct · $3,080 at 4 ct",
                             "pass / bust": "61% (2021-24) · 74% (2025-26) / 26-36%", "day": "2026-10-02 only"},
                    "caveat": "evals bought together win or lose together; 24 of 35 sim wins were held "
                              "5 s or less (Lucid micro-scalping rule)",
                }),
            # 9:30 open, one direction each: market on the 09:29 close, TP 120 ticks /
            # SL 45 ticks, both moved to the fill. Added 2026-09-29 at the account
            # holder's request for 2026-09-30 only (rules.OPEN_930_DAY). Ships off and
            # unbooked: the user books the accounts and enables it.
            **{f"nq_open_{side}": StrategyCfg(
                symbol="NQ", qty=1, offset_pts=0.0, sl_pts=11.25, tp_pts=30.0,
                accept_from_et="09:29", accept_until_et="09:31",
                enabled=False, self_fire=True, kind="bars", rule=f"open_{side}",
                bar_minutes=1, warmup_bars=60,
                metrics={
                    "source": f"added 2026-09-29 at the account holder's request: {side} at the "
                              "9:30 open, 2026-09-30 only",
                    "rows": {"entry": "market, 09:30 ET", "TP": "120 ticks · 30 pts · $600/mini",
                             "SL": "45 ticks · 11.25 pts · $225/mini", "day": "2026-09-30"},
                    "caveat": "no backtest — a one-day directional trade",
                }) for side in ("long", "short")},
            # The 3 NQ prop strategies (research 2026-09-29/30, desk review 2026-10-01). Kind "levels":
            # a NEW geometry every day from ATR(14) of bars built from the tape since 00:00 ET, OCO stop
            # entries, NQ minis, one entry a day, stop 3 x ATR from the trigger, a take sized in dollars
            # (day_take / target_take). They ship OFF and unbooked: build on paper first. Flex and Pro need
            # separate names: one signal gives one geometry and the take differs per rule set.
            "nq_nyam_flex": StrategyCfg(
                symbol="NQ", qty=4, offset_pts=0.0, sl_pts=0.0, tp_pts=0.0,
                cancel_et="10:55", flat_et="11:00", accept_from_et="09:29", accept_until_et="09:31",
                enabled=False, self_fire=True, kind="levels", shape="atr_straddle",
                fire_et="09:30:00", atr_tf=30, off_atr=0.25, sl_atr=3.0, fee_rt=4.0,
                day_take=1500.0, target_take=True,
                metrics={
                    "source": "hm2-straddle-tf30#10 · NYAM · LucidFlex 50K eval · 2025-01→2026-09 holdout",
                    "rows": {"entry": "09:30:00, anchor ± 0.25 ATR30", "stop": "3 ATR from the trigger",
                             "take": "day_take $1,500 net (4 NQ: 19.0 pts) + target_take",
                             "cancel / flat": "10:55 / 11:00"},
                    "caveat": "entry edge is thin (lift +0.125); the 3 ATR stop is ~5x the $2,000 max loss: "
                              "every Lucid number assumes only CLOSED balance counts",
                }),
            "nq_nyam_pro": StrategyCfg(
                symbol="NQ", qty=4, offset_pts=0.0, sl_pts=0.0, tp_pts=0.0,
                cancel_et="10:55", flat_et="11:00", accept_from_et="09:29", accept_until_et="09:31",
                enabled=False, self_fire=True, kind="levels", shape="atr_straddle",
                fire_et="09:30:00", atr_tf=30, off_atr=0.25, sl_atr=3.0, fee_rt=4.0,
                day_take=0.0, target_take=True,
                metrics={
                    "source": "hm2-straddle-tf30#10 · NYAM · LucidPro 50K no-DLL eval · 2025-01→2026-09 holdout",
                    "rows": {"entry": "09:30:00, anchor ± 0.25 ATR30", "stop": "3 ATR from the trigger",
                             "take": "target_take only: day 1 = $3,000 net (4 NQ: 37.75 pts)",
                             "cancel / flat": "10:55 / 11:00"},
                    "caveat": "the account must be bought with the daily-loss limit OFF; same open-loss "
                              "caveat as nq_nyam_flex",
                }),
            "nq_orb_pro": StrategyCfg(
                symbol="NQ", qty=4, offset_pts=0.0, sl_pts=0.0, tp_pts=0.0,
                cancel_et="13:25", flat_et="13:30", accept_from_et="11:04", accept_until_et="11:06",
                enabled=False, self_fire=True, kind="levels", shape="orb",
                fire_et="11:05:00", atr_tf=5, or_min=5, sl_atr=3.0, fee_rt=4.0, day_take=1000.0,
                skip_early_close=True,
                metrics={
                    "source": "hm-orb-tf5#10 · MID · funded LucidPro no-DLL · 2025-01→2026-09 holdout",
                    "rows": {"entry": "11:05:00, 11:00-11:05 high + 1 tick / low - 1 tick",
                             "stop": "3 ATR5 from the trigger", "take": "day_take $1,000 net (4 NQ: 12.75 pts)",
                             "cancel / flat": "13:25 / 13:30"},
                    "caveat": "no entry edge over random entries (lift -0.044 eval): the take rule carries it; "
                              "request the payout at $1,000",
                }),
            "nq_pm_flex": StrategyCfg(
                symbol="NQ", qty=4, offset_pts=0.0, sl_pts=0.0, tp_pts=0.0,
                cancel_et="15:53", flat_et="15:58", accept_from_et="13:29", accept_until_et="13:31",
                enabled=False, self_fire=True, kind="levels", shape="atr_straddle",
                fire_et="13:30:00", atr_tf=30, off_atr=1.0, sl_atr=3.0, fee_rt=4.0, day_take=600.0,
                size_tiers=[[0, 2], [1000, 3], [2000, 4]], skip_early_close=True,
                metrics={
                    "source": "hm2-straddle-tf30#32 · PM · funded LucidFlex · 2025-01→2026-09 holdout",
                    "rows": {"entry": "13:30:00, anchor ± 1.0 ATR30", "stop": "3 ATR from the trigger",
                             "take": "day_take $600 net (2/3/4 NQ: 15.25 / 10.25 / 7.75 pts)",
                             "size": "2 NQ under $1,000 profit, 3 under $2,000, 4 above",
                             "cancel / flat": "15:53 / 15:58"},
                    "caveat": "small edge (funded lift +$441); skipped on half days (11-27, 12-24)",
                }),
        },
    )


def load() -> AppCfg:
    """Defaults overlaid with config.json. Migrates the pre-book single
    'account' layout into accounts{main} + a book assignment."""
    cfg = _defaults()
    p = config_path()
    if not p.exists():
        return cfg
    data = json.loads(p.read_text())
    cfg.armed = bool(data.get("armed", cfg.armed))
    # the TradingView webhook was removed 2026-09-27: a stored secret / tunnel URL is ignored,
    # and save() writes them blank, so the old secret leaves the config file on the next save
    for aid, a in (data.get("accounts") or {}).items():
        base = asdict(AccountCfg())
        cfg.accounts[aid] = AccountCfg(**{**base, **a})
    for name, s in (data.get("strategies") or {}).items():
        base = asdict(cfg.strategies[name]) if name in cfg.strategies else {}
        cfg.strategies[name] = StrategyCfg(**{**base, **s})
    cfg.book = {k: list(v) for k, v in (data.get("book") or {}).items()}
    cfg.chart_trading = chart_trading_from(data.get("chart_trading"))
    if "allowed_hosts" in data:
        cfg.allowed_hosts = data["allowed_hosts"]
        warn_bad_allowed_hosts(cfg.allowed_hosts)

    # ---- migration: single-account era ("account": {...}) ----
    legacy = data.get("account")
    if legacy and not cfg.accounts and legacy.get("keyring_key"):
        cfg.accounts["main"] = AccountCfg(
            keyring_key=legacy.get("keyring_key", ""),
            account_name=legacy.get("account_name", ""),
            live=bool(legacy.get("live", False)),
            label=legacy.get("account_name", "main"))
        if not cfg.book:
            cfg.book = {n: [{"account": "main", "qty": s.qty}]
                        for n, s in cfg.strategies.items() if s.enabled}
    return cfg


def save(cfg: AppCfg) -> None:
    d = asdict(cfg)
    d["webhook_secret"] = ""      # the webhook is gone (2026-09-27): never persist a secret
    d["public_hook_url"] = ""
    # atomic: a crash mid-write must never leave a truncated config (the desk now
    # rewrites it on its own, e.g. removing a closed account)
    path = config_path()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)


def assignments(cfg: AppCfg, strategy: str) -> list[dict]:
    """The strategy's book rows, restricted to accounts that exist."""
    return [a for a in cfg.book.get(strategy, [])
            if a.get("account") in cfg.accounts and int(a.get("qty", 0)) > 0]
