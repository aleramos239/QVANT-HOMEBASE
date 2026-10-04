"""Liquidity sweep reversal. Hypothesis: price trading beyond a prior-day high/low or the overnight range
(00:00 -> session start; asia range for london, 00:00-09:30 for NY sessions) and then closing back inside
is a stop run; fade it. One signal per level per session. struct stop = the sweep extreme."""
TITLE = "PP sweep reversal"
INPUTS = [("levels", "Levels", "choice", "both", None, None, None, ("both", "pd", "on"))]


class Fam:
    def fam_day(self, ctx):
        self.lv, self.sw = {}, None

    def fam_session(self, ctx, s):
        m, lv = self.p["levels"], {}
        if m != "on":
            lv.update({"pdh": [self.pdh, 1, None, False], "pdl": [self.pdl, -1, None, False]})
        if m != "pd":
            lv.update({"onh": [self.onh, 1, None, False], "onl": [self.onl, -1, None, False]})
        self.lv = {k: r for k, r in lv.items() if r[0] is not None}

    def fam_update(self, ctx):
        self.sw = None
        if self.sid is None:
            return
        h, l, c = self.H[-1], self.L[-1], self.C[-1]
        for r in self.lv.values():
            px, sd, ext, done = r
            if done:
                continue
            if sd > 0:
                if h > px:
                    r[2] = h if ext is None else max(ext, h)
                if r[2] is not None and c <= px:
                    r[3] = True
                    self.sw = self.sw or ("short", r[2])
            else:
                if l < px:
                    r[2] = l if ext is None else min(ext, l)
                if r[2] is not None and c >= px:
                    r[3] = True
                    self.sw = self.sw or ("long", r[2])

    def fam_signal(self, ctx):
        if self.sw:
            self._mkt(ctx, self.sw[0], struct=self.sw[1])
