"""Homebase config: which strategies run, at what size, when the clock steps in.

The frozen strategy geometry (offset / SL / TP / qty) lives HERE, server-side.
A TradingView alert only carries the two entry prices; anything the wire says
is validated against this file before an order exists. Edit config.json (or
this file's defaults for a fresh install), never the alert payload, to change
what runs.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field

from .paths import config_path


@dataclass
class StrategyCfg:
    symbol: str                  # canonical, e.g. "NQ" (adapter resolves front month)
    qty: int
    offset_pts: float            # entry stops sit this far off the anchor close
    sl_pts: float                # protective stop, points from entry trigger
    tp_pts: float                # target, points from entry trigger
    cancel_et: str = "12:55"     # unfilled entries are cancelled here
    flat_et: str = "15:55"       # any open position is force-flattened here
    accept_from_et: str = "09:29"   # alerts outside this ET window are refused
    accept_until_et: str = "09:45"
    enabled: bool = False
    gated: bool = False             # True = a no-alert day can be the regime
                                    # gate (expected), not a broken pipe


@dataclass
class AccountCfg:
    keyring_key: str = "tradovate:demo"  # credentials key in secrets_store
    live: bool = False                   # False = Tradovate demo environment
    account_name: str = ""               # pin one account under the login


@dataclass
class AppCfg:
    armed: bool = False          # master switch: disarmed = journal-only dry run
    webhook_secret: str = ""     # shared secret the TV alert must carry
    account: AccountCfg = field(default_factory=AccountCfg)
    strategies: dict[str, StrategyCfg] = field(default_factory=dict)


def _defaults() -> AppCfg:
    return AppCfg(
        strategies={
            # NQ 9:30 straddle — the approved champion (spec 2026-09-09,
            # OOS-passed 2026-09-10): off ±10 / SL 5 / TP 15, 3 minis.
            # The TREND gate lives in the Pine script: no alert on CHOP days.
            "nq930": StrategyCfg(symbol="NQ", qty=3, offset_pts=10.0,
                                 sl_pts=5.0, tp_pts=15.0, enabled=True,
                                 gated=True),
            # YM 9:30 straddle (OOS-passed 2026-09-13): off ±20 / SL 5 / TP 15,
            # unfiltered. Disabled until the user sets the size and enables it.
            "ym930": StrategyCfg(symbol="YM", qty=1, offset_pts=20.0,
                                 sl_pts=5.0, tp_pts=15.0, enabled=False),
        },
    )


def load() -> AppCfg:
    """Defaults overlaid with config.json (missing keys keep their default)."""
    cfg = _defaults()
    p = config_path()
    if not p.exists():
        return cfg
    data = json.loads(p.read_text())
    cfg.armed = bool(data.get("armed", cfg.armed))
    cfg.webhook_secret = str(data.get("webhook_secret", cfg.webhook_secret))
    if isinstance(data.get("account"), dict):
        cfg.account = AccountCfg(**{**asdict(cfg.account), **data["account"]})
    for name, s in (data.get("strategies") or {}).items():
        base = asdict(cfg.strategies[name]) if name in cfg.strategies else {}
        merged = {**base, **s}
        cfg.strategies[name] = StrategyCfg(**merged)
    return cfg


def save(cfg: AppCfg) -> None:
    config_path().write_text(json.dumps(asdict(cfg), indent=2) + "\n")
