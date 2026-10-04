"""Donchian breakout. Hypothesis: a close beyond the prior n-bar channel starts a continuation move.
struct stop = the opposite channel side. Needs n+1 tf bars since 00:00."""
TITLE = "PP Donchian"
INPUTS = [("n", "Channel length (bars)", "int", 20, 2, 200, 1)]


class Fam:
    WARM = 5

    def fam_signal(self, ctx):
        n = int(self.p["n"])
        if self.nb <= n:
            return
        hh, ll, c = max(self.H[-n - 1:-1]), min(self.L[-n - 1:-1]), self.C[-1]
        if c > hh:
            self._mkt(ctx, "long", struct=ll)
        elif c < ll:
            self._mkt(ctx, "short", struct=hh)
