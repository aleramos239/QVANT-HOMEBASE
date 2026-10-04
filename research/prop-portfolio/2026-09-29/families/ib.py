"""Initial balance (09:30-10:30, NY sessions nyam/mid/pm only). Hypothesis: the IB range anchors the day.
break: OCO stop entries at IB high/low placed at max(10:30, session start); a leg already through the last
print is skipped. fade: the first tf close back inside after a close beyond the IB is faded, target = IB mid.
struct stop = the other IB side (break) / atr fallback (fade)."""
TITLE = "PP initial balance"
INPUTS = [("mode", "Mode", "choice", "break", None, None, None, ("break", "fade"))]


class Fam:
    def fam_filter(self, ids):
        return [s for s in ids if s in ("nyam", "mid", "pm")]

    def fam_day(self, ctx):
        self.ibh = self.ibl = None
        self.brk = self.fade = 0

    def fam_times(self):
        return ["10:30:00"]

    def _ib(self):
        if self.ibh is None:
            r = self.rng(34200, 37800)
            if r:
                self.ibh, self.ibl = r
        return self.ibh is not None

    def fam_time(self, ctx, sec):
        s = self.sid
        if (s is None or self.p["mode"] != "break" or sec != max(37800, SESS[s][0])
                or not self.can_enter(ctx) or not self._ib()):
            return
        t = ctx.tick
        self._arm(ctx, [("long", self.ibh + t, self.ibl, None), ("short", self.ibl - t, self.ibh, None)])

    def fam_update(self, ctx):
        self.fade = 0
        if self.p["mode"] != "fade" or ctx.now_ns - self.t0 < 37800 * NS or not self._ib():
            return
        c = self.C[-1]
        if c > self.ibh:
            self.brk = 1
        elif c < self.ibl:
            self.brk = -1
        elif self.brk:
            self.fade, self.brk = -self.brk, 0

    def fam_signal(self, ctx):
        if self.fade and self._ib():
            self._mkt(ctx, "long" if self.fade > 0 else "short", tp_px=(self.ibh + self.ibl) / 2.0)
