"""noise_band_eve -- noise_band with the EVENING anchor (owner, 2026-10-26: F76, "noise band k 0.2 on the 18:00-23:55 evening, both sides").

noise_band (families/noise.py) is untouched; this adds one anchor value, `eve` = the open of the first 1-minute bar from 18:00 ET (the session
open), the VWAP from 18:00, band = that open +/- k x the daily ATR(14) of the days before. It reads the evening instance's own bars (they start at
-21600 s on the trade date's clock), so it is only meaningful with the card's home session `eve`; in any other session the anchor is not in the
day's bars and the day has no anchor (no trade). Everything else is noise_band's. Registration as eve_gap_follow.py: join_blocks().
Tests: engine/tests/test_noise_eve.py."""
from __future__ import annotations

from . import noise as NB

NB.ANCHOR_S.setdefault("eve", -21600)                     # shortcut: one new key in noise's dict; nothing reads "eve" but this family's cards


class NoiseBandEve(NB.NoiseBand):
    DEFAULTS = {**NB.NoiseBand.DEFAULTS, "anchor": "eve"}
    SCHEMA = {**NB.NoiseBand.SCHEMA, "anchor": ("choice", tuple(NB.ANCHOR_S))}


FAMILIES = {
    "noise_band_eve": (NoiseBandEve, {}, False,
                       "noise_band_eve: noise_band anchored at the 18:00 ET evening open (open +/- k x A and the VWAP from 18:00); home session eve",
                       {"rationale": "The evening has its own open: a move away from the 18:00 price bigger than the usual noise, with the "
                                     "evening VWAP behind it, shows one-way participation that the rest of the evening keeps chasing.",
                        "complexity": 6,
                        "variants": [{"k": k} for k in (0.2, 0.3, 0.4)]}),
}


def join_blocks() -> None:
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
