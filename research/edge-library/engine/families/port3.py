"""PORT GROUP 3 (EDGE_SPEC family C, "PROPER RE-RUN OF THE PILOT"): five of the old pilot's 21 families, ported to
l2sim.Template from R/families/<fam>.py -- vwap_band, vwap_z, vwap_flip, pinbar, sweep_rev.

THE PORT. Each class body below is the R family's `class Fam` body VERBATIM (tests/test_port3.py compares the syntax
trees method by method); DEFAULTS / SCHEMA are the R family's INPUTS (= the tester draft pp_<fam>, R/family_inputs.json).
Nothing else is added: no feature, no clock time, no new threshold. FEATURES = () -> roots NQ, ES, GC.

TESTER-MATCH GATE (ENGINE.md 8): `python port3_validate.py` replays every in-sample tester bundle of the five families
(NQ: the 20 screen runs = every family x tf 1 / 5 / 15 / 30, and every cell of their 9 heat-maps; ES: the 20 ES-pilot
screen runs and 6 heat-maps) and compares trade for trade -> engine/PORT3_VALIDATION.md. Trade identity only.

FAMILY-PARAMETER VARIANTS (EDGE_SPEC "PROPER RE-RUN" 4) = the values of the FIRST axis of the family's heat-map in
R/tune1.jsonl / R/tune2.jsonl; the source line is quoted above each entry. SCREEN_TFS = the tfs of the old screen
(R/jobs.jsonl stage `screen`: screen-<fam>-tf1 / tf5 / tf15 / tf30 for each of the five).

SESSIONS. The five tester sessions run exactly as the tester draft (the gate). `pre` (08:25-09:30) and `eve` (18:00-23:59)
come from the Template without any family code (run_menus runs them as their own instances), with these consequences of
the verbatim bodies -- fixed here BEFORE any run:
  vwap_band / vwap_z / vwap_flip   the session VWAP restarts at 08:25 (pre) / 18:00 (eve) like at every session start.
  pinbar      key levels: prior-day H / L / C and the session VWAP in every session; the overnight H / L only in the NY
              sessions (nyam / mid / pm), as R wrote it -- so NOT in pre, eve, asia or london.
  sweep_rev   prior-day H / L in every session; the overnight range where the Template has one: london (00:00-03:00),
              pre (00:00-08:25), NY sessions (00:00-09:30); asia and eve have none (levels="on" cannot trade there).
  Prior-day levels are unset on contract-roll days (Template); in `eve` they are the day that ended at 17:00.

COMPLEXITY = trigger rules + free parameters (declared family inputs + hard-coded thresholds), counted per entry below.
"""
from __future__ import annotations

import l2sim as S


class VwapBand(S.Template):
    """R/families/vwap_band.py -- VWAP band fade. Hypothesis: a close beyond session VWAP +/- band sigma that is followed
    by a close back inside marks a failed extension; fade it toward VWAP. sigma = volume-weighted stdev of typical price
    (1m bars) since session start. Needs 3 tf bars in the session. No structural stop (atr fallback)."""
    DEFAULTS = {"band": 2.0}
    SCHEMA = {"band": ("float", 0.5, 5)}                                                             # as pp_vwap_band
    SCREEN_TFS = ("1", "5", "15", "30")
    FEATURES = ()

    def fam_session(self, ctx, s):
        self.pout, self.fsig = 0, 0

    def fam_update(self, ctx):
        self.fsig = 0
        v = self.vw() if self.sid is not None and self.sn >= 3 else None
        if v is None or v[1] <= 0:
            return
        b, c = float(self.p["band"]) * v[1], self.C[-1]
        hi, lo = v[0] + b, v[0] - b
        if self.pout == 1 and c <= hi:
            self.fsig = -1
        elif self.pout == -1 and c >= lo:
            self.fsig = 1
        self.pout = 1 if c > hi else -1 if c < lo else 0

    def fam_signal(self, ctx):
        if self.fsig:
            self._mkt(ctx, "long" if self.fsig > 0 else "short")


class VwapZ(S.Template):
    """R/families/vwap_z.py -- VWAP z-score fade. Hypothesis: a close >= zth sigma from session VWAP is stretched and
    reverts; fade it at once at the close. z = (close - VWAP)/sigma, sigma as in vwap_band. Needs 3 tf bars in the
    session. No structural stop (atr fallback)."""
    DEFAULTS = {"zth": 2.0}
    SCHEMA = {"zth": ("float", 0.5, 6)}                                                              # as pp_vwap_z
    SCREEN_TFS = ("1", "5", "15", "30")
    FEATURES = ()

    def fam_signal(self, ctx):
        v = self.vw() if self.sn >= 3 else None
        if v is None or v[1] <= 0:
            return
        z = (self.C[-1] - v[0]) / v[1]
        zt = float(self.p["zth"])
        if z >= zt:
            self._mkt(ctx, "short")
        elif z <= -zt:
            self._mkt(ctx, "long")


class VwapFlip(S.Template):
    """R/families/vwap_flip.py -- VWAP flip / reclaim. Hypothesis: a close crossing VWAP that then holds the new side for
    `hold` more bars is a trend change; enter that way. anchor=session: VWAP since session start; rth: anchored at 09:30
    for NY sessions (03:00 london, 00:00 asia), i.e. the anchored-VWAP reclaim. No structural stop (atr fallback)."""
    DEFAULTS = {"hold": 2, "anchor": "session"}
    SCHEMA = {"hold": ("int", 1, 6), "anchor": ("choice", ("session", "rth"))}                       # as pp_vwap_flip
    SCREEN_TFS = ("1", "5", "15", "30")
    FEATURES = ()

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


class Pinbar(S.Template):
    """R/families/pinbar.py -- Pin-bar reversal at a key level. Hypothesis: a bar whose wick is >= wick of its range and
    whose extreme sits within 0.25 x ATR of prior-day H/L/C, the overnight (00:00-09:30) H/L (NY sessions only) or session
    VWAP shows rejection; trade the reversal at the close. struct stop = the wick end."""
    DEFAULTS = {"wick": 0.667}
    SCHEMA = {"wick": ("float", 0.5, 0.95)}                                                          # as pp_pinbar
    SCREEN_TFS = ("1", "5", "15", "30")
    FEATURES = ()

    def _near(self, x, tol):
        lv = [self.pdh, self.pdl, self.pdc]
        if self.sid in ("nyam", "mid", "pm"):
            lv += [self.onh, self.onl]
        v = self.vw()
        if v:
            lv.append(v[0])
        return any(z is not None and abs(x - z) <= tol for z in lv)

    def fam_signal(self, ctx):
        o, h, l, c = self.O[-1], self.H[-1], self.L[-1], self.C[-1]
        rg = h - l
        if rg <= 0:
            return
        w, tol = float(self.p["wick"]), 0.25 * self.atr
        if (min(o, c) - l) / rg >= w and self._near(l, tol):
            self._mkt(ctx, "long", struct=l)
        elif (h - max(o, c)) / rg >= w and self._near(h, tol):
            self._mkt(ctx, "short", struct=h)


class SweepRev(S.Template):
    """R/families/sweep_rev.py -- Liquidity sweep reversal. Hypothesis: price trading beyond a prior-day high/low or the
    overnight range (00:00 -> session start; asia range for london, 00:00-09:30 for NY sessions) and then closing back
    inside is a stop run; fade it. One signal per level per session. struct stop = the sweep extreme."""
    DEFAULTS = {"levels": "both"}
    SCHEMA = {"levels": ("choice", ("both", "pd", "on"))}                                            # as pp_sweep_rev
    SCREEN_TFS = ("1", "5", "15", "30")
    FEATURES = ()

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


FAMILIES = {      # name -> (StrategyClass, default_inputs, both_sides, notes, LIBRARY dict)
    # R/tune1.jsonl "hm-vwap_band-tf5": "axes": [{"key": "band", "values": [1.5, 2.0, 2.5, 3.0]}, {"key": "stop_val", ...
    # complexity 3 = 2 rules (a close outside the band; then a close back inside -> fade) + 1 parameter (band)
    "vwap_band": (VwapBand, {}, False,
                  "C / R#10: tf close back inside session VWAP +/- band sigma after a close outside -> fade at market",
                  {"rationale": "VWAP fade = mean reversion to fair price (EDGE_SPEC C): a close beyond session VWAP +/- band "
                                "sigma followed by a close back inside is a failed extension, so the traders who chased it must "
                                "exit and their orders carry price back toward VWAP.",
                   "complexity": 3,
                   "variants": [{"band": 1.5}, {"band": 2.0}, {"band": 2.5}, {"band": 3.0}],
                   "ported": "vwap_band"}),
    # R/tune1.jsonl "hm-vwap_z-tf5": "axes": [{"key": "zth", "values": [1.5, 2.0, 2.5, 3.0]}, {"key": "stop_val", ...
    # complexity 2 = 1 rule (|z| >= zth at a tf close -> fade at once) + 1 parameter (zth)
    "vwap_z": (VwapZ, {}, False,
               "C / R#11: |close - session VWAP| >= zth sigma at a tf close -> fade at market. SECOND LOOK: the old pilots "
               "ran holdout-stage tester jobs on vwap_z tf5 (R and RE jobs.jsonl keys ho-vwap_z-tf5-*): label its exam",
               {"rationale": "VWAP fade = mean reversion to fair price (EDGE_SPEC C): a close zth sigma away from session VWAP is "
                             "stretched beyond what the session's own volume has accepted, so responsive traders lean against "
                             "the extreme and late chasers are forced out as price returns toward VWAP.",
                "complexity": 2,
                "variants": [{"zth": 1.5}, {"zth": 2.0}, {"zth": 2.5}, {"zth": 3.0}],
                "ported": "vwap_z"}),
    # R/tune1.jsonl "hm-vwap_flip-tf15": "axes": [{"key": "hold", "values": [1, 2, 3]}, {"key": "stop_val", ...
    # R/tune2.jsonl "hm2-vwap_flip-tf1" and "hm2-vwap_flip-tf5": "axes": [{"key": "hold", "values": [1, 2, 3]}, ...
    # complexity 4 = 2 rules (a close crosses VWAP; the next `hold` closes stay on the new side) + 2 parameters (hold, anchor)
    "vwap_flip": (VwapFlip, {}, False,
                  "C / R#12: tf close crosses session VWAP and the next `hold` closes stay on the new side -> enter with it. "
                  "EDGE_SPEC B: this family did not survive the old NQ pilot (state it next to any result). SECOND LOOK: the "
                  "ES pilot ran holdout-stage tester jobs on vwap_flip tf5 / tf15 (RE jobs.jsonl keys ho-vwap_flip-*)",
                  {"rationale": "A close crossing session VWAP that then holds the new side for `hold` more bars means control of "
                                "the session's fair price has changed sides (R/SPEC 12: a trend change), and the side that is now "
                                "offside must exit into the move.",
                   "complexity": 4,
                   "variants": [{"hold": 1}, {"hold": 2}, {"hold": 3}],
                   "ported": "vwap_flip"}),
    # R/tune2.jsonl "hm2-pinbar-tf5": "axes": [{"key": "wick", "values": [0.6, 0.667, 0.75]}, {"key": "stop_val", ...
    # complexity 5 = 2 rules (wick >= wick x range; the wick end within tolerance of a key level) + 3 parameters
    #                (wick; the hard-coded 0.25 x ATR tolerance; the key-level set PDH / PDL / PDC, overnight H / L, VWAP)
    "pinbar": (Pinbar, {}, False,
               "C / R#13: tf bar with wick >= `wick` of its range and its extreme within 0.25 ATR of a key level "
               "(prior-day H/L/C, overnight H/L in NY sessions, session VWAP) -> reversal at market; struct = wick end",
               {"rationale": "A bar whose wick is most of its range and whose extreme sits at a key level (prior-day H / L / C, "
                             "the overnight H / L, session VWAP) shows that orders resting at that level absorbed the push "
                             "(R/SPEC 13: rejection), so the traders who pushed into it are trapped and price reverses away.",
                "complexity": 5,
                "variants": [{"wick": 0.6}, {"wick": 0.667}, {"wick": 0.75}],
                "ported": "pinbar"}),
    # R/tune2.jsonl "hm2-sweep_rev-tf5": "axes": [{"key": "levels", "values": ["both", "pd", "on"]}, {"key": "stop_val", ...
    # complexity 4 = 3 rules (a tf bar trades beyond a level; a tf close back inside -> fade; one signal per level per
    #                session) + 1 parameter (levels)
    "sweep_rev": (SweepRev, {}, False,
                  "C / R#14: a tf bar trades beyond the prior-day or overnight high / low and a tf close comes back inside "
                  "-> reversal at market, once per level per session; struct = the sweep extreme",
                  {"rationale": "Stop-run exhaustion at prior-day / overnight extremes (EDGE_SPEC C): price trading beyond the "
                                "prior-day or overnight high / low fills the stops resting there, and a close back inside shows "
                                "nobody followed through once they were filled, so the breakout traders are trapped and price "
                                "reverts.",
                   "complexity": 4,
                   "variants": [{"levels": "both"}, {"levels": "pd"}, {"levels": "on"}],
                   "ported": "sweep_rev"}),
}
