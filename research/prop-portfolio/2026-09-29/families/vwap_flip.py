"""VWAP flip / reclaim. Hypothesis: a close crossing VWAP that then holds the new side for `hold` more bars is
a trend change; enter that way. anchor=session: VWAP since session start; rth: anchored at 09:30 for
NY sessions (03:00 london, 00:00 asia), i.e. the anchored-VWAP reclaim. No structural stop (atr fallback)."""
TITLE = "PP VWAP flip"
INPUTS = [("hold", "Bars holding the new side", "int", 2, 1, 6, 1),
          ("anchor", "VWAP anchor", "choice", "session", None, None, None, ("session", "rth"))]


class Fam:
    def fam_session(self, ctx, s):
        self.pside = self.pend = self.cnt = self.go = 0

    def fam_update(self, ctx):
        self.go = 0
        if self.sid is None:
            return
        v = self.vw() if self.p["anchor"] == "session" else self.vwr()
        if v is None:
            return
        c = self.C[-1]
        sd = 1 if c > v[0] else -1 if c < v[0] else 0
        if not sd:
            return
        if self.pside and sd != self.pside:
            self.pend, self.cnt = sd, 0
        elif self.pend:
            self.cnt += 1
            if self.cnt >= int(self.p["hold"]):
                self.go, self.pend = sd, 0
        self.pside = sd

    def fam_signal(self, ctx):
        if self.go:
            self._mkt(ctx, "long" if self.go > 0 else "short")
