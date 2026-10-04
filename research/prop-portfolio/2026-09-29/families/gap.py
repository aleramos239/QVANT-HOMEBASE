"""RTH gap (NY AM only). Hypothesis: the 09:30 open vs the prior daily close (whole archive day, last print
~17:00) leaves an imbalance of at least min_gap_atr x daily ATR(14). fill: fade it at the first tf close
>= 09:30, target = the prior close; go: trade in the gap direction (tgt_r target). No structural stop."""
TITLE = "PP gap"
INPUTS = [("min_gap_atr", "Min gap (x daily ATR)", "float", 0.1, 0, 3, 0.05),
          ("mode", "Mode", "choice", "fill", None, None, None, ("fill", "go"))]


class Fam:
    def fam_filter(self, ids):
        return [s for s in ids if s == "nyam"]

    def fam_signal(self, ctx):
        da, op = self.datr(), self.mo(34200)
        if self.sn != 1 or self.pdc is None or not da or op is None:
            return
        g = op - self.pdc
        if abs(g) < float(self.p["min_gap_atr"]) * da or g == 0:
            return
        if self.p["mode"] == "fill":
            self._mkt(ctx, "short" if g > 0 else "long", tp_px=self.pdc)
        else:
            self._mkt(ctx, "long" if g > 0 else "short")
