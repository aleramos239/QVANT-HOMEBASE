"""VWAP z-score fade. Hypothesis: a close >= zth sigma from session VWAP is stretched and reverts; fade it
at once at the close. z = (close - VWAP)/sigma, sigma as in vwap_band. Needs 3 tf bars in the session.
No structural stop (atr fallback)."""
TITLE = "PP VWAP z"
INPUTS = [("zth", "Z threshold", "float", 2.0, 0.5, 6, 0.25)]


class Fam:
    def fam_signal(self, ctx):
        v = self.vw() if self.sn >= 3 else None
        if v is None or v[1] <= 0:
            return
        z = (self.C[-1] - v[0]) / v[1]
        zt = float(self.p["zth"])
        if z >= zt:
            self._mkt(ctx, "short")
        elif z <= -zt:
            self._mkt(ctx, "long")
