"""The four NQ "levels" algos as test fixtures. The desk no longer ships them (2026-10-08: nq930 and gc_nfp
only); the levels engine, timer, geometry and the tester strategies are still covered, on these configs
(config.levels_reference: a fresh copy of the removed shipped defaults on every call)."""
from __future__ import annotations

import dataclasses

from homebase.config import StrategyCfg, levels_reference

NAMES = ("nq_nyam_flex", "nq_nyam_pro", "nq_orb_pro", "nq_pm_flex")


def levels_cfg(name: str, **over) -> StrategyCfg:
    """One levels algo's config, fields overridden by `over`."""
    return dataclasses.replace(levels_reference()[name], **over)


def strategy_cfg(name: str, **over) -> StrategyCfg:
    """A levels algo, or a shipped desk strategy (nq930, gc_nfp)."""
    from homebase.config import _defaults
    base = levels_reference().get(name) or _defaults().strategies[name]
    return dataclasses.replace(base, **over)
