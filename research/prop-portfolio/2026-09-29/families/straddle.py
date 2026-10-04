"""Straddle. Hypothesis: a session start (or the news release) is followed by a directional burst; an OCO
pair of stop entries at last price +/- off_atr x ATR catches it either way. news_only=True trades only
CPI/NFP/FOMC days (list embedded) with a pre-release bracket: 08:29:30 on CPI/NFP days (flat 09:00, no entries
after 08:55) and 13:59:30 on FOMC days (statement 14:00; flat 14:30, no entries after 14:25); the sess input is
not used. news_only=False brackets at every active session start +
delay_min. Asia needs delay_min >= 3 x tf (ATR warm-up). struct stop: none (falls back to atr)."""
TITLE = "PP straddle"
USES_NEWS = True
INPUTS = [("delay_min", "Delay after session start (min)", "int", 0, 0, 120, 1),
          ("off_atr", "Bracket offset (x ATR)", "float", 0.5, 0.1, 5, 0.1),
          ("news_only", "News days only (08:29:30 pre-news bracket)", "bool", False, None, None, None)]


class Fam:
    def fam_filter(self, ids):
        return ["news", "fomc"] if self.p["news_only"] else ids

    def sess_on(self, s):
        if not self.p["news_only"]:
            return True
        return ("N" if s == "news" else "F") in NEWS.get(self.day, "")

    def trades_on(self, d):
        return (not self.p["news_only"]) or d.isoformat() in NEWS

    def fam_times(self):
        dm = int(self.p["delay_min"]) * 60
        return [] if self.p["news_only"] else [_hms(SESS[s][0] + dm) for s in self.sessions()]

    def fam_time(self, ctx, sec):
        s = self.sid
        if s is None:
            return
        at = SESS[s][0] + (0 if s in ("news", "fomc") else int(self.p["delay_min"]) * 60)
        if sec != at or not self.can_enter(ctx):
            return
        lp = ctx.last_price
        if lp is None:
            return
        off = float(self.p["off_atr"]) * self.atr
        self._arm(ctx, [("long", lp + off, None, None), ("short", lp - off, None, None)])
