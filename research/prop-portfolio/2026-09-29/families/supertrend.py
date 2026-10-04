"""Supertrend(10, 3) flip. Hypothesis: a flip of the ATR-band trend line starts a directional leg; enter in
the new direction. struct stop = the Supertrend line after the flip."""
TITLE = "PP Supertrend"
INPUTS = []


class Fam:
    WARM = 10

    def fam_day(self, ctx):
        self.sa = self.up = self.dn = self.line = None
        self.dr, self.flip = 1, 0

    def fam_update(self, ctx):
        tr, n = self.TR[-1], self.nb
        self.sa = sum(self.TR) / n if n <= 10 else (self.sa * 9.0 + tr) / 10.0
        h, l, c = self.H[-1], self.L[-1], self.C[-1]
        up, dn = (h + l) / 2.0 - 3 * self.sa, (h + l) / 2.0 + 3 * self.sa
        self.flip = 0
        if self.up is not None:
            pc = self.C[-2]
            if pc > self.up:
                up = max(up, self.up)
            if pc < self.dn:
                dn = min(dn, self.dn)
            if self.dr == -1 and c > self.dn:
                self.dr, self.flip = 1, 1
            elif self.dr == 1 and c < self.up:
                self.dr, self.flip = -1, -1
        self.up, self.dn = up, dn
        self.line = up if self.dr == 1 else dn

    def fam_signal(self, ctx):
        if self.flip:
            self._mkt(ctx, "long" if self.flip > 0 else "short", struct=self.line)
