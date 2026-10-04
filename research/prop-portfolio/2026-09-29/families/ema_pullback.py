"""EMA pullback. Hypothesis: in a trend (EMA50 slope) a dip that tags EMA20 and closes back on the trend
side is a continuation entry. struct stop = the pullback bar's extreme."""
TITLE = "PP EMA pullback"
INPUTS = []


class Fam:
    SPANS = (20, 50)
    WARM = 20

    def fam_signal(self, ctx):
        e20, e50, p50 = self.E[20], self.E[50], self.Ep[50]
        if p50 is None:
            return
        h, l, c = self.H[-1], self.L[-1], self.C[-1]
        if e50 > p50 and l <= e20 < c:
            self._mkt(ctx, "long", struct=l)
        elif e50 < p50 and h >= e20 > c:
            self._mkt(ctx, "short", struct=h)
