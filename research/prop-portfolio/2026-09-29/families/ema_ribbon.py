"""EMA ribbon. Hypothesis: EMA 8/21/55 becoming fully stacked marks a fresh trend leg; enter on the bar the
stack forms (long 8>21>55, short reverse). EMAs seed at the day's first tf bar, so tf 30 is barely warm.
No structural stop (atr fallback)."""
TITLE = "PP EMA ribbon"
INPUTS = []


class Fam:
    SPANS = (8, 21, 55)
    WARM = 10

    def fam_day(self, ctx):
        self.al, self.chg = 0, 0

    def fam_update(self, ctx):
        a, b, c = self.E[8], self.E[21], self.E[55]
        prev = self.al
        self.al = 1 if a > b > c else -1 if a < b < c else 0
        self.chg = self.al if self.al and self.al != prev else 0

    def fam_signal(self, ctx):
        if self.chg:
            self._mkt(ctx, "long" if self.chg > 0 else "short")
