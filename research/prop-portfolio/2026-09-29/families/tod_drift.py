"""Time-of-day drift (control for pure clock effects). Hypothesis: a fixed-direction position held for a
fixed time from a session offset earns a stable drift. Enters dir (long|short, default long) at session
start + off_min, exits after exit_bars tf bars (default 6) or at the stop / session end; max 1 per session.
tgt_r defaults to 0 (no target). No structural stop."""
TITLE = "PP TOD drift"
OVERRIDES = {"dir": {"default": "long", "choices": ("long", "short")}, "exit_bars": {"default": 6},
             "tgt_r": {"default": 0.0}, "max_tr": {"default": 1}}
INPUTS = [("off_min", "Entry offset from session start (min)", "int", 0, 0, 240, 1)]


class Fam:
    def fam_times(self):
        om = int(self.p["off_min"]) * 60
        return [_hms(SESS[s][0] + om) for s in self.sessions()]

    def fam_time(self, ctx, sec):
        s, lp = self.sid, ctx.last_price
        if s is None or lp is None or sec != SESS[s][0] + int(self.p["off_min"]) * 60 or not self.can_enter(ctx):
            return
        self._mkt(ctx, self.p["dir"], ref=lp)
