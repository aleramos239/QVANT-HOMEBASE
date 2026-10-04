"""TEMA slope turn. Hypothesis: the low-lag TEMA(n) changing slope sign marks a turn early; enter in the new
slope direction. TEMA = 3E1 - 3E2 + E3 on tf closes, seeded each day. No structural stop (atr fallback)."""
TITLE = "PP TEMA slope"
INPUTS = [("n", "TEMA length", "int", 20, 3, 100, 1)]


class Fam:
    WARM = 8

    def fam_day(self, ctx):
        self.t1 = self.t2 = self.t3 = self.tp = None
        self.tsg, self.flip = 0, 0

    def fam_update(self, ctx):
        k, c = 2.0 / (int(self.p["n"]) + 1), self.C[-1]
        if self.t1 is None:
            self.t1 = self.t2 = self.t3 = c
        else:
            self.t1 += k * (c - self.t1)
            self.t2 += k * (self.t1 - self.t2)
            self.t3 += k * (self.t2 - self.t3)
        te = 3 * self.t1 - 3 * self.t2 + self.t3
        self.flip = 0
        if self.tp is not None:
            sg = 1 if te > self.tp else -1 if te < self.tp else 0
            if sg:
                if self.tsg and sg != self.tsg:
                    self.flip = sg
                self.tsg = sg
        self.tp = te

    def fam_signal(self, ctx):
        if self.flip:
            self._mkt(ctx, "long" if self.flip > 0 else "short")
