"""Volatility squeeze. Hypothesis: compression precedes expansion. bbkc: BB(20,2) inside KC(20,1.5; EMA20
mid, SMA(TR,20) width) for >= 3 bars, then release -> market entry toward the close vs the BB mid.
nr7 / inside: the narrowest-of-7 / inside bar arms OCO stop entries at its high/low (valid one tf bar);
struct stop = the other side. bbkc has no structural stop (falls back to atr)."""
TITLE = "PP squeeze"
INPUTS = [("sq_type", "Squeeze type", "choice", "bbkc", None, None, None, ("bbkc", "nr7", "inside"))]


class Fam:
    SPANS = (20,)

    def fam_day(self, ctx):
        self.sqn, self.rel = 0, 0

    def fam_update(self, ctx):
        self.rel = 0
        if self.p["sq_type"] != "bbkc" or self.nb < 20:
            return
        c = self.C[-20:]
        m = sum(c) / 20.0
        sd = math.sqrt(sum((x - m) ** 2 for x in c) / 20.0)
        e, ka = self.E[20], sum(self.TR[-20:]) / 20.0
        if m + 2 * sd < e + 1.5 * ka and m - 2 * sd > e - 1.5 * ka:
            self.sqn += 1
        else:
            if self.sqn >= 3:
                self.rel = 1 if self.C[-1] > m else -1
            self.sqn = 0

    def fam_signal(self, ctx):
        t = self.p["sq_type"]
        if t == "bbkc":
            if self.rel:
                self._mkt(ctx, "long" if self.rel > 0 else "short")
            return
        h, l = self.H[-1], self.L[-1]
        if t == "nr7":
            if self.nb < 7 or h - l >= min(self.H[i] - self.L[i] for i in range(-7, -1)):
                return
        elif self.nb < 2 or not (h < self.H[-2] and l > self.L[-2]):
            return
        tk = ctx.tick
        self._arm(ctx, [("long", h + tk, l, None), ("short", l - tk, h, None)], ttl=1)
