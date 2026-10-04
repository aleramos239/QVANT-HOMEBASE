"""First-bar momentum. Hypothesis: a session's first tf bar with range >= k x ATR (ATR before that bar)
is momentum ignition; follow its direction at its close. struct stop = the bar's opposite extreme.
Asia lacks ATR history at 00:00 (no trades until 3 tf bars exist, so effectively none)."""
TITLE = "PP first-bar momentum"
INPUTS = [("k", "Min bar range (x ATR)", "float", 1.5, 0.2, 10, 0.1)]


class Fam:
    def fam_signal(self, ctx):
        if self.sn != 1 or not self.atr_p:
            return
        o, h, l, c = self.O[-1], self.H[-1], self.L[-1], self.C[-1]
        if h - l < float(self.p["k"]) * self.atr_p or c == o:
            return
        self._mkt(ctx, "long" if c > o else "short", struct=l if c > o else h)
