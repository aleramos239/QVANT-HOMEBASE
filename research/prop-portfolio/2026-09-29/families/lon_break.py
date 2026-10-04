"""London range break at the NY AM open. Hypothesis: the London (03:00-08:25) high/low is the overnight
inventory; the NY open resolves it. OCO stop entries one tick beyond London high/low placed at 09:30
(nyam only); a leg already through the 09:30 price fills at once (gap-through follow). struct stop = the
other London side. min_rng_atr skips days with a tiny London range."""
TITLE = "PP London break"
INPUTS = [("min_rng_atr", "Min London range (x ATR)", "float", 0.0, 0, 20, 0.5)]


class Fam:
    def fam_filter(self, ids):
        return [s for s in ids if s == "nyam"]

    def fam_time(self, ctx, sec):
        if self.sid != "nyam" or sec != 34200 or not self.can_enter(ctx):
            return
        r = self.rng(10800, 30300)
        if r is None or r[0] - r[1] < float(self.p["min_rng_atr"]) * self.atr:
            return
        t = ctx.tick
        self._arm(ctx, [("long", r[0] + t, r[1], None), ("short", r[1] - t, r[0], None)], imm=True)
