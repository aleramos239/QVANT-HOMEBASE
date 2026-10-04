"""Lunch mean reversion (mid session only). Hypothesis: a large NY AM move (09:30 open to the 11:00 close)
of at least k x daily ATR(14) is over-extended; fade it at the first tf close of mid. No structural stop."""
TITLE = "PP mid fade"
INPUTS = [("k", "Min AM move (x daily ATR)", "float", 0.3, 0, 3, 0.05)]


class Fam:
    def fam_filter(self, ids):
        return [s for s in ids if s == "mid"]

    def fam_signal(self, ctx):
        da, op, cl = self.datr(), self.mo(34200), self.mc(34200, 39600)
        if self.sn != 1 or not da or op is None or cl is None:
            return
        mv = cl - op
        if abs(mv) >= float(self.p["k"]) * da and mv != 0:
            self._mkt(ctx, "short" if mv > 0 else "long")
