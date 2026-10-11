"""vault -- the VAULT BREAK as the video says it (Matteo Conti, IQCapital video A0G14JYYVTk, "strategy 1"), written from the video's rule
before any result. It is `noise.NoiseBand` (the noise band entry, anchor globex) with the three differences the video asks for, and nothing else:

  * ONE instance for the whole window. noise_band runs as independent session passes, so its cap of 3 trades counts inside each pass. Here ONE
    instance holds 11:00 -> 15:30 New York (his 10:00 -> 14:30 Central): the cap of 3 trades is a DAY cap and one position at a time holds for
    the whole window. The window opens 1 second before 11:00 so that the 30-minute bar that CLOSES at 11:00 counts (a position may open from
    11:00); entries stop 5 minutes before the window ends (the Template's rule), so the last signal bar closes at 15:00. A trade still open
    is flattened at 15:30 by the family (fam_time).
  * A = the SIMPLE AVERAGE over the last 15 sessions of the daily ATR(14), over the daily bars before the trade date ("a moving average of
    ATR ... not an ATR with a look-back of 15, traditional ATR"); noise_band reads the last ATR(14) alone. Needs 29 prior daily bars.
  * The anchor is always the 01:00 New York bar (midnight Central): the reference price and the VWAP both start there.

The band, the VWAP, the signal (a bar closes strictly above reference + k x A and strictly above the VWAP -> market at the next bar's open; the
mirror for a short) and the re-entry (once a trade has exited, the next close that still qualifies enters again) are noise_band's, read from the
same code. The video's rule is LONG only: the sheet sets dir long. Its exits are fixed dollars ($800 target, $1,500 stop on 1 NQ): the sheet's.

REGISTRATION as noise.py: join_blocks() puts the family into families/blocks.py's BASES and WRAPPED once. Tests: engine/tests/test_vault.py."""
from __future__ import annotations

from l2sim import _hms

from families.noise import NoiseBand

T0_S, END_S = 39600, 55800                          # 11:00 and 15:30 ET, seconds after 00:00 ET
A_DAYS, ATR_N = 15, 14


class VaultBreak(NoiseBand):
    """vault_break (module docstring): NoiseBand over ONE instance 11:00-15:30, A = the 15-session average of the daily ATR(14), anchor 01:00."""
    DEFAULTS = {**NoiseBand.DEFAULTS, "anchor": "globex", "max_tr": 3}
    SCREEN_TFS = ("30",)

    def fam_filter(self, ids):
        return [s for s in ids if s == "nyam"]

    def fam_sessions(self) -> dict:
        return {"nyam": (T0_S - 1, END_S)}

    def fam_times(self):
        return [_hms(END_S)]

    def fam_time(self, ctx, sec):
        if sec == END_S:
            self._cancel(ctx)
            ctx.flatten("time")

    def datr(self):
        """A: the simple average of the last 15 daily ATR(14) values (Wilder) over the daily bars before today; None below 29 bars."""
        if self._datr is None and len(self.dl) >= 1 + 2 * ATR_N:
            dl = self.dl
            trs = [max(dl[i]["h"] - dl[i]["l"], abs(dl[i]["h"] - dl[i - 1]["c"]), abs(dl[i]["l"] - dl[i - 1]["c"])) for i in range(1, len(dl))]
            a = sum(trs[:ATR_N]) / ATR_N
            atrs = [a]
            for x in trs[ATR_N:]:
                a = (a * (ATR_N - 1) + x) / ATR_N
                atrs.append(a)
            if len(atrs) >= A_DAYS:
                self._datr = sum(atrs[-A_DAYS:]) / A_DAYS
        return self._datr


FAMILIES = {
    "vault_break": (VaultBreak, {}, False,
                    "vault_break: a 30-minute bar closes above the 01:00 ET open + k x A (A = the 15-session average of the daily ATR(14)) "
                    "and above the VWAP from 01:00 -> market entry at the next bar's open; entries 11:00-15:00, up to max_tr a day, one "
                    "position at a time, a new trade whenever the close still qualifies after an exit; flat 15:30. Conti's vault break "
                    "(A0G14JYYVTk) as taught; noise_band is the same entry per session pass with the last ATR(14)",
                    {"rationale": "A move away from the session open that is bigger than the day's usual noise, with price above the day's "
                                  "average price, shows one-way buying that keeps being chased, while the moves inside the band are noise.",
                     "complexity": 7,
                     "variants": [{"k": k} for k in (0.2, 0.3, 0.4)]}),
}


def join_blocks() -> None:
    """Put the family into families/blocks.py's BASES and WRAPPED (as noise.py does): the wrapped class a card runs, importable by name."""
    from . import blocks
    for name, entry in FAMILIES.items():
        if not blocks._bar_based(entry):
            raise ValueError(f"{name}: not a bar-based library family (the blocks wrap those only)")
        cls = blocks._wrap(name, entry[0])
        blocks.BASES[name] = entry
        blocks.WRAPPED[name] = cls
        setattr(blocks, cls.__name__, cls)


join_blocks()
