"""VWAP band fade. Hypothesis: a close beyond session VWAP +/- band sigma that is followed by a close back
inside marks a failed extension; fade it toward VWAP. sigma = volume-weighted stdev of typical price
(1m bars) since session start. Needs 3 tf bars in the session. No structural stop (atr fallback)."""
TITLE = "PP VWAP band"
INPUTS = [("band", "Band (sigma)", "float", 2.0, 0.5, 5, 0.25)]


class Fam:
    def fam_session(self, ctx, s):
        self.pout, self.fsig = 0, 0

    def fam_update(self, ctx):
        self.fsig = 0
        v = self.vw() if self.sid is not None and self.sn >= 3 else None
        if v is None or v[1] <= 0:
            return
        b, c = float(self.p["band"]) * v[1], self.C[-1]
        hi, lo = v[0] + b, v[0] - b
        if self.pout == 1 and c <= hi:
            self.fsig = -1
        elif self.pout == -1 and c >= lo:
            self.fsig = 1
        self.pout = 1 if c > hi else -1 if c < lo else 0

    def fam_signal(self, ctx):
        if self.fsig:
            self._mkt(ctx, "long" if self.fsig > 0 else "short")
