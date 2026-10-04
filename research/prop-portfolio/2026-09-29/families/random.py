"""CONTROL: random entries. At each tf close while flat (and entries < max_tr) enter with probability
p_entry; side random (or dir if long/short). RNG = Random(f"{seed}|{date}|{session}") drawn at EVERY tf close
of a session, so the stream does not depend on the trade path (session id, not the sess input, so a sess=nyam
run equals the nyam part of a sess=all run). Same stops/targets/exits as every family."""
TITLE = "PP random control"
IMPORTS = ["random"]
INPUTS = [("p_entry", "Entry probability per tf close", "float", 0.05, 0, 1, 0.01),
          ("seed", "RNG seed", "int", 1, 0, 1000000, 1)]


class Fam:
    def fam_session(self, ctx, s):
        self.rg = random.Random("%s|%s|%s" % (self.p["seed"], ctx.date, s))

    def fam_update(self, ctx):
        self.rr = (self.rg.random(), self.rg.random()) if self.sid is not None else None

    def fam_signal(self, ctx):
        r, d = self.rr, self.p["dir"]
        if r is not None and r[0] < float(self.p["p_entry"]):
            self._mkt(ctx, d if d != "both" else ("long" if r[1] < 0.5 else "short"))
