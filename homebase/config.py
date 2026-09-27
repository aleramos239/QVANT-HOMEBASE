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
    shadow: bool = False         # True: signals are journaled, never placed —
                                 # even when the app is armed (forward paper)
    rule: str = ""               # bars: name in rules.RULES
    bar_minutes: int = 1         # bars: the rule's timeframe
    warmup_bars: int = 60        # bars: history loaded before the rule runs


@dataclass
class AccountCfg:
    keyring_key: str = ""        # credentials key in secrets_store
    account_name: str = ""       # pin one account under the login
    live: bool = False           # False = demo environment
    label: str = ""              # display name (defaults to account_name)


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
    config_path().write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")


def assignments(cfg: AppCfg, strategy: str) -> list[dict]:
    """The strategy's book rows, restricted to accounts that exist."""
    return [a for a in cfg.book.get(strategy, [])
            if a.get("account") in cfg.accounts and int(a.get("qty", 0)) > 0]
