"""Opening-range breakout. Hypothesis: the first or_min minutes of a session set the range that the
rest of the session resolves; a break of either side (OCO stop entries one tick beyond, placed at the
range end) carries. struct stop = the other side of the range. One bracket per session (max_tr moot)."""
TITLE = "PP ORB"
INPUTS = [("or_min", "Opening range (min)", "choice", "15", None, None, None, ("5", "15", "30"))]


class Fam:
    def fam_times(self):
        m = int(self.p["or_min"]) * 60
        return [_hms(SESS[s][0] + m) for s in self.sessions()]

    def fam_time(self, ctx, sec):
        s = self.sid
        if s is None or sec != SESS[s][0] + int(self.p["or_min"]) * 60 or not self.can_enter(ctx):
            return
        r = self.rng(SESS[s][0], sec)
        if r is None:
            return
        hi, lo = r
        t = ctx.tick
        self._arm(ctx, [("long", hi + t, lo, None), ("short", lo - t, hi, None)])
