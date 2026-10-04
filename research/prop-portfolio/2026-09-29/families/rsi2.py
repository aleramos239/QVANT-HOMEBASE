"""RSI(2) mean reversion. Hypothesis: a 2-bar RSI below th (above 100-th) is a short-term exhaustion that
snaps back; fade it at the close. trend_f=True only takes longs with EMA50 rising / shorts with it falling.
No structural stop (atr fallback)."""
TITLE = "PP RSI2"
INPUTS = [("th", "RSI threshold (long < th, short > 100-th)", "float", 10.0, 1, 40, 1),
          ("trend_f", "Only with EMA50 slope", "bool", False, None, None, None)]


class Fam:
    WARM = 4

    def fam_day(self, ctx):
        self.ag = self.alo = self.rsi = None

    def fam_update(self, ctx):
        if self.nb < 2:
            return
        d = self.C[-1] - self.C[-2]
        g, ls = max(d, 0.0), max(-d, 0.0)
        if self.ag is None:
            self.ag, self.alo = g, ls
        else:
            self.ag, self.alo = (self.ag + g) / 2.0, (self.alo + ls) / 2.0
        self.rsi = 50.0 if self.ag + self.alo == 0 else 100.0 if self.alo == 0 else 100 - 100 / (1 + self.ag / self.alo)

    def fam_signal(self, ctx):
        r, th = self.rsi, float(self.p["th"])
        if r is None:
            return
        sl_ = self.E[50] - self.Ep[50] if self.Ep[50] is not None else 0.0
        tf_ = self.p["trend_f"]
        if r < th and (not tf_ or sl_ > 0):
            self._mkt(ctx, "long")
        elif r > 100 - th and (not tf_ or sl_ < 0):
            self._mkt(ctx, "short")
