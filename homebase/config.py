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
from dataclasses import asdict, dataclass, field, fields

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
                                 # False: nothing fires it (see inactive.py)
    pine_file: str = ""          # unused: the Pine sources are gone; kept so a saved config still loads
    metrics: dict = field(default_factory=dict)   # research record, display-only
    kind: str = "straddle"       # "straddle": two stop legs at the anchor (timer)
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
    label: str = ""              # display name only ("" = show the id); APIs, the book and the journal use the id
    rr: float = 0.0              # straddle: target as a multiple of the stop; 0 = tp_pts is used as written.
                                 # rr > 0: load() sets tp_pts = round(sl_pts * rr, 4) (the owner edits it in the app)

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
    accounts: dict[str, AccountCfg] = field(default_factory=dict)
    book: dict[str, list] = field(default_factory=dict)   # strategy -> [{account, qty}]
    strategies: dict[str, StrategyCfg] = field(default_factory=dict)
    chart_trading: ChartTradingCfg = field(default_factory=ChartTradingCfg)
    # hostnames / IPs, besides loopback, that may WRITE to the desk (e.g. a
    # Tailscale MagicDNS name or 100.x IP); exact match, no port, no wildcard.
    # Kept RAW as written in config.json; netguard.allowlist() cleans it.
    allowed_hosts: list[str] = field(default_factory=list)


def apply_rr(c: StrategyCfg) -> StrategyCfg:
    """A straddle with rr > 0 takes its target from the stop: tp_pts = round(sl_pts * rr, 4). Everything
    that reads the target (engine, trading, review, metrics) reads tp_pts and needs no change."""
    if c.kind == "straddle" and c.rr > 0:
        c.tp_pts = round(c.sl_pts * c.rr, 4)
    return c


def _defaults() -> AppCfg:
    return AppCfg(
        strategies={
            # NQ 9:30 straddle — the approved champion (spec 2026-09-09,
            # OOS-passed 2026-09-10). The TREND gate runs in-app (self_fire).
            # pine_file names a deleted file; the value stays so the tester's
            # recorded desk_cfg is unchanged.
            "nq930": StrategyCfg(
                symbol="NQ", qty=3, offset_pts=5.0, sl_pts=5.0, tp_pts=15.0,
                enabled=True, gated=True, self_fire=True, pine_file="nq930.pine", rr=3.0,
                metrics={
                    "source": "one-shot sealed-year OOS exam · 2025-07-08→2026-07-07 · TV 15s",
                    "rows": {"trades": "167", "WR": "47.3%", "PF": "2.34",
                             "t": "5.04", "avg/trade/mini": "$79.0",
                             "maxDD/mini": "−$1,135", "green months": "10/10"},
                    "caveat": "does not cover live fill quality — the edge is 2–4 ticks deep",
                    "equity_file": "nq930_equity.json",
                }),
            # GC 08:30 NFP straddle (verified 2026-10-01, research/nfp-2026-10-02/verify): 4 gold
            # contracts, OCO stops at anchor +/- 2.0, SL 5.0 (-$2,000 before slippage: the user's choice 2026-10-01, a stop-out ends the eval), TP 7.7
            # (+$3,080 gross, +$3,061.60 after $2.30 a side), unfilled cancelled 08:45, flat 09:55.
            # Fires 08:29:59 (the user's choice 2026-10-01): the stops rest at the exchange before the release;
            # tested on 57 NFPs: 08:29:59 passes 22/38 + 13/19, one second later (08:30:00) 23/38 + 14/19.
            # Trades ONLY the days in only_dates: the BLS NFP days (2026-10-02, 11-06, 12-04) and CPI days (10-14, 11-10, 12-10),
            # 08:30 ET, checked on bls.gov 2026-10-08, one setup for both releases (owner 2026-10-08; extend by hand).
            # The id stays gc_nfp (book, journal, history); the desk shows it as label GC_NFP/CPI.
            # accept_until 08:31: a fire more than a minute late is refused, not re-anchored on a
            # post-release price. Ships off and unbooked: the user books the evals and enables it.
            "gc_nfp": StrategyCfg(
                symbol="GC", qty=4, offset_pts=2.0, sl_pts=5.0, tp_pts=7.7,
                cancel_et="08:45", flat_et="09:55",
                accept_from_et="08:29", accept_until_et="08:31",
                enabled=False, gated=False, self_fire=True,
                fire_et="08:29:59", only_dates=["2026-10-02", "2026-10-14", "2026-11-06", "2026-11-10", "2026-12-04", "2026-12-10"],
                label="GC_NFP/CPI",
                metrics={
                    "source": "GC 08:30 NFP + CPI straddle, one setup for both releases (2026-10-08)",
                    "rows": {"entry": "OCO stops anchor +/-2.0",
                             "SL": "5.0 pts, $500/ct, $2,000 at 4 ct (a stop-out ends the eval)",
                             "TP": "7.7 pts, $770/ct, $3,080 at 4 ct",
                             "2025-01..2026-09 tick replay, 4 ct": "NFP 19 trades 74% win +$32.1k eval pass 68% / "
                                                                  "CPI 20 trades 60% win +$19.6k eval pass 48%",
                             "events": "NFP and CPI days"},
                    "rev": 3,
                    "caveat": "19-20 trades per event; the 2025-26 days were already spent on this family; CPI is "
                              "the weaker of the two and its win rate fell 64% -> 56% from 2025 to 2026; most "
                              "winners last under 5 s (Lucid micro-scalp: over 50% of profit from trades held 5 s "
                              "or less)",
                    "equity_file": "gc_nfp_equity.json",
                }),
        },
    )


_said: set = set()      # (where, key) of the unknown keys a reader already named in the log


def _known(cls, d: dict, where: str, left_out: list) -> dict:
    """d without the keys `cls` does not have: each named in the log once (the key, never its value)
    and noted in `left_out`."""
    names = {f.name for f in fields(cls)}
    for k in d:
        if k not in names:
            left_out.append(k)
            if (where, k) not in _said:
                _said.add((where, k))
                log.warning("config.json: %s has a key this code does not know, left out: %r", where, k)
    return {k: v for k, v in d.items() if k in names}


def load(unknown: str = "raise") -> AppCfg:
    """Defaults overlaid with config.json. Migrates the pre-book single
    'account' layout into accounts{main} + a book assignment.

    A key of an account or a strategy that this code does not know:
      unknown="raise" (the default: the desk) -- a TypeError, as it always was. The desk must not trade on
        settings it only half understands (the key may be a safety switch: shadow, only_dates), and it
        rewrites this file: it would erase the key.
      unknown="ignore" (a process that only READS which login each account rides: the chart service, the
        tick job) -- the key is left out and named in the log, once. Such a process is often older than the
        desk that wrote the file (2026-10-01: the desk restarted on code that writes accounts' "prop"; the
        chart service, still on the code before it, raised on every reconnect for two hours). A load that
        left a key out never rewrites the file: its copy of the settings lacks that key."""
    cfg = _defaults()
    p = config_path()
    if not p.exists():
        for c in cfg.strategies.values():
            apply_rr(c)
        return cfg
    data = json.loads(p.read_text())
    left_out: list = []

    def known(cls, d: dict, where: str) -> dict:
        return _known(cls, d, where, left_out) if unknown == "ignore" else d

    cfg.armed = bool(data.get("armed", cfg.armed))
    # the old webhook keys (webhook_secret, hook_port, public_hook_url) are not read: a file that
    # still holds them loads the same, and save() no longer writes them
    for aid, a in (data.get("accounts") or {}).items():
        base = asdict(AccountCfg())
        cfg.accounts[aid] = AccountCfg(**{**base, **known(AccountCfg, a, f"account {aid}")})
    gone = []
    for name, s in (data.get("strategies") or {}).items():
        if name not in cfg.strategies:       # a removed strategy: nothing runs it, so it leaves the file
            gone.append(name)
            continue
        base = asdict(cfg.strategies[name])
        if isinstance(s.get("metrics"), dict):
            # metrics is the shipped research record (display-only).  The saved copy wins key by key, but a key
            # the defaults gained after the file was written (equity_file) must still reach the running config:
            # the whole-dict overlay below would hide it behind the stale copy.  A shipped record with a higher
            # "rev" than the saved copy was CORRECTED after the file was written: the correction replaces it.
            saved = s["metrics"]
            if int(saved.get("rev") or 0) < int(base["metrics"].get("rev") or 0):
                saved = {}
            s = {**s, "metrics": {**base["metrics"], **saved}}
        cfg.strategies[name] = StrategyCfg(**{**base, **known(StrategyCfg, s, f"strategy {name}")})
    cfg.book = {k: list(v) for k, v in (data.get("book") or {}).items() if k in cfg.strategies}
    gone += [k for k in (data.get("book") or {}) if k not in cfg.strategies and k not in gone]
    for name in gone:
        rows = (data.get("book") or {}).get(name) or []
        log.warning("config.json: dropped strategy %s (no longer shipped) and its %d book row(s): %s",
                    name, len(rows), ", ".join(str(a.get("account")) for a in rows) or "-")
    for c in cfg.strategies.values():
        apply_rr(c)
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
    if gone and left_out:
        log.warning("config.json: not rewritten by this process (it left out %d key(s) it does not know)",
                    len(left_out))
    elif gone:                               # clean the file itself, once; a failed write only retries next start
        try:
            save(cfg)
        except OSError as e:
            log.warning("config.json: could not write the cleaned file: %s", e)
    return cfg


_after_save: list = []  # fn(cfg), called after each save() once the file is whole; the desk registers
                        # labcfg.persist_all here (the Lab strategies' own files). A hook never breaks a save.


def save(cfg: AppCfg) -> None:
    d = asdict(cfg)
    # A promoted Lab strategy (kind "lab", id "lab_<name>": homebase/labcfg.py) lives in the desk's memory and in
    # its own file beside its record, never here: load() drops a strategy it does not ship, with its book rows.
    # With none, `d` is untouched and the file is byte for byte what it always was.
    for name in [n for n, s in cfg.strategies.items() if getattr(s, "kind", "") == "lab"] \
            + [n for n in d["book"] if str(n).startswith("lab_")]:
        d["strategies"].pop(name, None)
        d["book"].pop(name, None)
    # atomic: a crash mid-write must never leave a truncated config (the desk now
    # rewrites it on its own, e.g. removing a closed account)
    path = config_path()
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(d, indent=2, ensure_ascii=False) + "\n")
    os.replace(tmp, path)
    for fn in list(_after_save):
        try:
            fn(cfg)
        except Exception as e:  # noqa: BLE001 -- config.json is written; a hook's trouble is its own
            log.warning("config.json: an after-save step failed: %s", e)


def assignments(cfg: AppCfg, strategy: str) -> list[dict]:
    """The strategy's book rows, restricted to accounts that exist."""
    return [a for a in cfg.book.get(strategy, [])
            if a.get("account") in cfg.accounts and int(a.get("qty", 0)) > 0]
