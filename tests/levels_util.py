"""Neutral "levels" configs for the engine / timer / geometry tests.

No strategy ships on kind "levels" any more (2026-10-08: the desk ships nq930 and gc_nfp). The engine is
still covered, on these four local configs; their numbers are the ones the four removed NQ algos had, so
the geometry, take rules, size tiers and early-close skip keep the coverage they had:

  lv_atr_take    09:30 ATR straddle, +/- 0.25 ATR30, day_take $1,500 + target_take
  lv_atr_target  09:30 ATR straddle, same entry, target_take only
  lv_orb         11:05 opening-range breakout, ATR5 stop, day_take $1,000, skips half days
  lv_atr_tiers   13:30 ATR straddle, +/- 1.0 ATR30, day_take $600, size tiers 2/3/4, skips half days
"""
from __future__ import annotations

import dataclasses

from homebase.config import StrategyCfg, _defaults

NAMES = ("lv_atr_take", "lv_atr_target", "lv_orb", "lv_atr_tiers")

_BASE = dict(symbol="NQ", qty=4, offset_pts=0.0, sl_pts=0.0, tp_pts=0.0, enabled=False, self_fire=True,
             kind="levels", sl_atr=3.0, fee_rt=4.0)


def _levels() -> dict[str, StrategyCfg]:
    return {
        "lv_atr_take": StrategyCfg(
            **_BASE, cancel_et="10:55", flat_et="11:00", accept_from_et="09:29", accept_until_et="09:31",
            shape="atr_straddle", fire_et="09:30:00", atr_tf=30, off_atr=0.25, day_take=1500.0, target_take=True),
        "lv_atr_target": StrategyCfg(
            **_BASE, cancel_et="10:55", flat_et="11:00", accept_from_et="09:29", accept_until_et="09:31",
            shape="atr_straddle", fire_et="09:30:00", atr_tf=30, off_atr=0.25, day_take=0.0, target_take=True),
        "lv_orb": StrategyCfg(
            **_BASE, cancel_et="13:25", flat_et="13:30", accept_from_et="11:04", accept_until_et="11:06",
            shape="orb", fire_et="11:05:00", atr_tf=5, or_min=5, day_take=1000.0, skip_early_close=True),
        "lv_atr_tiers": StrategyCfg(
            **_BASE, cancel_et="15:53", flat_et="15:58", accept_from_et="13:29", accept_until_et="13:31",
            shape="atr_straddle", fire_et="13:30:00", atr_tf=30, off_atr=1.0, day_take=600.0,
            size_tiers=[[0, 2], [1000, 3], [2000, 4]], skip_early_close=True),
    }


def levels_cfg(name: str, **over) -> StrategyCfg:
    """One levels config, fields overridden by `over`. A fresh copy every call."""
    return dataclasses.replace(_levels()[name], **over)


def strategy_cfg(name: str, **over) -> StrategyCfg:
    """A levels config, or a shipped desk strategy (nq930, gc_nfp)."""
    base = _levels().get(name) or _defaults().strategies[name]
    return dataclasses.replace(base, **over)
