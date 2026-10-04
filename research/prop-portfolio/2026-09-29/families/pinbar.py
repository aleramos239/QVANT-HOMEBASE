"""Pin-bar reversal at a key level. Hypothesis: a bar whose wick is >= wick of its range and whose extreme
sits within 0.25 x ATR of prior-day H/L/C, the overnight (00:00-09:30) H/L (NY sessions only) or session VWAP
shows rejection; trade the reversal at the close. struct stop = the wick end."""
TITLE = "PP pinbar"
INPUTS = [("wick", "Min wick / range", "float", 0.667, 0.5, 0.95, 0.05)]


class Fam:
    def _near(self, x, tol):
        lv = [self.pdh, self.pdl, self.pdc]
        if self.sid in ("nyam", "mid", "pm"):
            lv += [self.onh, self.onl]
        v = self.vw()
        if v:
            lv.append(v[0])
        return any(z is not None and abs(x - z) <= tol for z in lv)

    def fam_signal(self, ctx):
        o, h, l, c = self.O[-1], self.H[-1], self.L[-1], self.C[-1]
        rg = h - l
        if rg <= 0:
            return
        w, tol = float(self.p["wick"]), 0.25 * self.atr
        if (min(o, c) - l) / rg >= w and self._near(l, tol):
            self._mkt(ctx, "long", struct=l)
        elif (h - max(o, c)) / rg >= w and self._near(h, tol):
            self._mkt(ctx, "short", struct=h)
