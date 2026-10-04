"""port1 -- EDGE_SPEC family C, group 1: seven of the old pilot's families ported to l2sim.Template.

    orb, squeeze, ib, lon_break, gap    the `class Fam` body of R/families/<fam>.py, copied verbatim
    straddle, donchian                  the tester-matched reference classes of l2ref.py, subclassed here (the registry
                                        needs the class in THIS module: worker processes import it by name)

R = research/prop-portfolio/2026-09-29 (READ-ONLY). Every class keeps the inputs, defaults and ranges of its tester draft
pp_<fam> (R/family_inputs.json), so a tester bundle's run.json inputs can be handed to it unchanged. No Level-2 feature
is read (FEATURES = ()): the families run on NQ, ES and GC. SCREEN_TFS = the tfs the old screen ran them at
(R/ledger.csv stage `screen`: screen-<fam>-tf{1,5,15,30} for all seven).

PRE-REGISTERED (EDGE_SPEC "PROPER RE-RUN" 4): the family-parameter VARIANTS are the values of the FIRST axis of the
family's heat-map in R/tune1.jsonl / R/tune2.jsonl; the source line is quoted above each entry. Nothing here was chosen
after a performance number: the rationale is the family's hypothesis as written in R/families/<fam>.py and R/SPEC.md
before the old screen, in EDGE_SPEC's wording where it gives one.

COMPLEXITY = rules + free parameters, counted the same way for every family (ENGINE.md's donchian example = 3):
    rules   one per level / state DEFINITION, one per entry TRIGGER, one per extra condition (filter, session restriction)
    params  one per family input of the tester draft (the Template's common inputs and fixed constants are not counted)

TESTER-MATCH GATE: engine/port1_gate.py -> engine/PORT1_VALIDATION.md: every screen bundle of the seven families of the
NQ pilot (R) and of the ES pilot (RE), 4 tfs each, and every cell of the NQ heat-maps the variants come from, trade for
trade. Tests: engine/tests/test_port1.py.

Sessions `pre` and `eve` come from the Template (run_menus runs each cell as three instances: sess all / pre / eve).
ib (NY sessions only), lon_break and gap (nyam only) restrict themselves through fam_filter exactly as in R: their
`pre` and `eve` instances have no session and never trade.

CELLS THAT CANNOT TRADE (warm-up arithmetic, as in the tester; tests/test_port1.py::warm_dead). Indicators restart at
00:00 ET (18:00 for the evening) and an entry needs its bars since the restart, so some registered (variant, tf) pairs
never enter in some sessions -- and count as cells "without a trade" in that session's plateau table:
    donchian   needs n + 1 bars: tf 30 -> n 40 and n 60 never trade (any session), n 20 from 10:30, n 10 from 05:30;
               tf 15 -> n 60 only in pm (from 15:15), n 40 from 10:15; evening: tf 30 n 10 only at 23:30, tf 15 n <= 20
    squeeze    bbkc needs 23 bars (tf 30: from 11:30, never in the evening), nr7 7 bars
    orb        the range end must be >= 3 tf bars after the restart: asia / eve trade only with or_min >= 3 x tf
    straddle   fires at the session start with a warm ATR: asia and eve never trade (delay_min 0), as in the tester
"""
from __future__ import annotations

import math

import l2ref
from l2sim import NS, SESS, Template, _hms

TFS = ("1", "5", "15", "30")


class Orb(Template):
    """Opening-range breakout (R/families/orb.py). Hypothesis: the first or_min minutes of a session set the range that
    the rest of the session resolves; a break of either side (OCO stop entries one tick beyond, placed at the range end)
    carries. struct stop = the other side of the range. One bracket per session (max_tr moot)."""
    DEFAULTS = {"or_min": "15"}
    SCHEMA = {"or_min": ("choice", ("5", "15", "30"))}                                                # as pp_orb
    SCREEN_TFS = TFS
    FEATURES = ()

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


class Straddle(l2ref.Straddle):
    """Straddle (R/families/straddle.py; l2ref.Straddle, tester-matched by the SIM VALIDATION GATE). Hypothesis: a session
    start (or the news release) is followed by a directional burst; an OCO pair of stop entries at last price +/-
    off_atr x ATR catches it either way. Asia / the evening need delay_min >= 3 x tf (ATR warm-up): with the default
    delay 0 they do not trade, exactly as in the tester. struct stop: none (falls back to atr)."""
    SCREEN_TFS = TFS
    FEATURES = ()


class Donchian(l2ref.Donchian):
    """Donchian breakout (R/families/donchian.py; l2ref.Donchian, tester-matched by the SIM VALIDATION GATE).
    Hypothesis: a close beyond the prior n-bar channel starts a continuation move. struct stop = the opposite channel
    side. Needs n + 1 tf bars since the last indicator restart (00:00 ET; 18:00 ET for the evening session)."""
    SCREEN_TFS = TFS
    FEATURES = ()


class Squeeze(Template):
    """Volatility squeeze (R/families/squeeze.py). Hypothesis: compression precedes expansion. bbkc: BB(20,2) inside
    KC(20,1.5; EMA20 mid, SMA(TR,20) width) for >= 3 bars, then release -> market entry toward the close vs the BB mid.
    nr7 / inside: the narrowest-of-7 / inside bar arms OCO stop entries at its high/low (valid one tf bar); struct stop
    = the other side. bbkc has no structural stop (falls back to atr)."""
    DEFAULTS = {"sq_type": "bbkc"}
    SCHEMA = {"sq_type": ("choice", ("bbkc", "nr7", "inside"))}                                       # as pp_squeeze
    SCREEN_TFS = TFS
    FEATURES = ()
    SPANS = (20,)

    def fam_day(self, ctx):
        self.sqn, self.rel = 0, 0

    def fam_update(self, ctx):
        self.rel = 0
        if self.p["sq_type"] != "bbkc" or self.nb < 20:
            return
        c = self.C[-20:]
        m = sum(c) / 20.0
        sd = math.sqrt(sum((x - m) ** 2 for x in c) / 20.0)
        e, ka = self.E[20], sum(self.TR[-20:]) / 20.0
        if m + 2 * sd < e + 1.5 * ka and m - 2 * sd > e - 1.5 * ka:
            self.sqn += 1
        else:
            if self.sqn >= 3:
                self.rel = 1 if self.C[-1] > m else -1
            self.sqn = 0

    def fam_signal(self, ctx):
        t = self.p["sq_type"]
        if t == "bbkc":
            if self.rel:
                self._mkt(ctx, "long" if self.rel > 0 else "short")
            return
        h, l = self.H[-1], self.L[-1]
        if t == "nr7":
            if self.nb < 7 or h - l >= min(self.H[i] - self.L[i] for i in range(-7, -1)):
                return
        elif self.nb < 2 or not (h < self.H[-2] and l > self.L[-2]):
            return
        tk = ctx.tick
        self._arm(ctx, [("long", h + tk, l, None), ("short", l - tk, h, None)], ttl=1)


class Ib(Template):
    """Initial balance (R/families/ib.py; 09:30-10:30, NY sessions nyam/mid/pm only). Hypothesis: the IB range anchors
    the day. break: OCO stop entries at IB high/low placed at max(10:30, session start); a leg already through the last
    print is skipped. fade: the first tf close back inside after a close beyond the IB is faded, target = IB mid (the
    menu's tgt_r is not used by fade). struct stop = the other IB side (break) / atr fallback (fade)."""
    DEFAULTS = {"mode": "break"}
    SCHEMA = {"mode": ("choice", ("break", "fade"))}                                                  # as pp_ib
    SCREEN_TFS = TFS
    FEATURES = ()

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


class LonBreak(Template):
    """London range break at the NY AM open (R/families/lon_break.py). Hypothesis: the London (03:00-08:25) high/low is
    the overnight inventory; the NY open resolves it. OCO stop entries one tick beyond London high/low placed at 09:30
    (nyam only); a leg already through the 09:30 price fills at once (gap-through follow). struct stop = the other
    London side. min_rng_atr skips days with a tiny London range."""
    DEFAULTS = {"min_rng_atr": 0.0}
    SCHEMA = {"min_rng_atr": ("float", 0, 20)}                                                        # as pp_lon_break
    SCREEN_TFS = TFS
    FEATURES = ()

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


class Gap(Template):
    """RTH gap (R/families/gap.py; NY AM only). Hypothesis: the 09:30 open vs the prior daily close (whole archive day,
    last print ~17:00) leaves an imbalance of at least min_gap_atr x daily ATR(14). fill: fade it at the first tf close
    >= 09:30, target = the prior close (the menu's tgt_r is not used by fill); go: trade in the gap direction (tgt_r
    target). No structural stop. No trade on a contract-roll day (no prior close)."""
    DEFAULTS = {"min_gap_atr": 0.1, "mode": "fill"}
    SCHEMA = {"min_gap_atr": ("float", 0, 3), "mode": ("choice", ("fill", "go"))}                     # as pp_gap
    SCREEN_TFS = TFS
    FEATURES = ()

    def fam_filter(self, ids):
        return [s for s in ids if s == "nyam"]

    def fam_signal(self, ctx):
        da, op = self.datr(), self.mo(34200)
        if self.sn != 1 or self.pdc is None or not da or op is None:
            return
        g = op - self.pdc
        if abs(g) < float(self.p["min_gap_atr"]) * da or g == 0:
            return
        if self.p["mode"] == "fill":
            self._mkt(ctx, "short" if g > 0 else "long", tp_px=self.pdc)
        else:
            self._mkt(ctx, "long" if g > 0 else "short")


SECOND_LOOK = "2025-26 was already seen once for this family's old finalist ({}): the EXAM is a SECOND look"

FAMILIES = {      # name -> (StrategyClass, default_inputs, both_sides, notes, LIBRARY dict)
    # R/tune1.jsonl line 9 (hm-orb-tf5): "axes": [{"key": "or_min", "values": ["5", "15", "30"]}, {"key": "stop_val", ...
    # complexity 3 = range definition (first or_min minutes) + OCO stop entries one tick beyond + or_min
    "orb": (Orb, {}, True,
            "C orb: at session start + or_min, OCO stop entries one tick beyond the opening range. "
            + SECOND_LOOK.format("orb-tf5"),
            {"rationale": "Opening range = the first balance of the session: the first or_min minutes set the range the rest "
                          "of the session resolves, so a break of either side traps the other side and carries.",
             "complexity": 3,
             "variants": [{"or_min": "5"}, {"or_min": "15"}, {"or_min": "30"}],
             "ported": "orb"}),
    # R/tune2.jsonl line 1 (hm2-straddle-tf30): "axes": [{"key": "off_atr", "values": [0.25, 0.5, 1.0]}, {"key": "stop_val", ...
    # complexity 5 = bracket definition (last price +/- off_atr x ATR) + OCO stop entries at session start + delay
    #                + off_atr + delay_min + news_only
    "straddle": (Straddle, {}, True,
                 "C straddle: at session start (+ delay_min), OCO stop entries at last price +/- off_atr x ATR. "
                 + SECOND_LOOK.format("straddle-tf30 nyam / pm"),
                 {"rationale": "At a session start new orders arrive and price leaves its pre-open balance in a directional "
                               "burst; an OCO pair of stop entries around the last price rides whichever side breaks.",
                  "complexity": 5,
                  "variants": [{"off_atr": 0.25}, {"off_atr": 0.5}, {"off_atr": 1.0}],
                  "ported": "straddle"}),
    # R/tune1.jsonl line 1 (hm-donchian-tf15): "axes": [{"key": "n", "values": [10, 20, 40, 60]}, {"key": "stop_val", ...
    #   (the tf30 / tf1 / tf5 heat-maps -- tune1 line 2, tune2 lines 15-16 -- ran n 10, 20, 40; EDGE_SPEC names
    #    "donchian n {10,20,40,60}" for the family)
    # complexity 3 = channel definition (prior n tf bars) + close beyond it -> market with it + n     (ENGINE.md's example)
    "donchian": (Donchian, {}, False,
                 "C donchian: close beyond the prior n-bar channel -> market with it. "
                 + SECOND_LOOK.format("donchian-tf15"),
                 {"rationale": "Trend continuation: a close beyond the prior n-bar channel traps the other side, whose stops "
                               "feed a continuation move.",
                  "complexity": 3,
                  "variants": [{"n": 10}, {"n": 20}, {"n": 40}, {"n": 60}],
                  "ported": "donchian",
                  "penalty": "in-sample favourite (donchian pm) FAILED on 2025-26: needs the plateau on BUILD and PICK and a "
                             "reason why the failure was noise"}),
    # R/tune2.jsonl line 2 (hm2-squeeze-tf1; line 3 hm2-squeeze-tf5 the same):
    #   "axes": [{"key": "sq_type", "values": ["bbkc", "nr7", "inside"]}, {"key": "stop_val", ...
    # complexity 5 = bbkc compression (BB inside KC >= 3 bars) + bbkc release -> market toward the close vs the BB mid
    #                + nr7 bar -> OCO at its high / low for one bar + inside bar -> the same + sq_type
    "squeeze": (Squeeze, {}, True,
                "C squeeze: bbkc = BB(20,2) inside KC(20,1.5) >= 3 bars then release -> market toward the close vs the BB mid; "
                "nr7 / inside = OCO stop entries at the narrow / inside bar's high and low for one tf bar",
                {"rationale": "Compression precedes expansion: after a volatility squeeze the positions built inside the "
                              "narrow range are forced out on its release, and the move that starts is followed.",
                 "complexity": 5,
                 "variants": [{"sq_type": "bbkc"}, {"sq_type": "nr7"}, {"sq_type": "inside"}],
                 "ported": "squeeze"}),
    # R/tune1.jsonl line 4 (hm-ib-tf30; line 5 hm-ib-tf15 the same):
    #   "axes": [{"key": "mode", "values": ["break", "fade"]}, {"key": "stop_val", ...
    # complexity 6 = IB definition (09:30-10:30 range) + NY sessions only + break: OCO stop entries at IB high / low
    #                + fade: close beyond the IB + fade: first close back inside -> fade to the IB mid + mode
    "ib": (Ib, {}, True,
           "C ib: initial balance 09:30-10:30, NY sessions only. break = OCO stop entries at IB high / low from 10:30; "
           "fade = first tf close back inside after a close beyond the IB -> fade to the IB mid (tgt_r unused)",
           {"rationale": "The initial balance (09:30-10:30) is the first hour's accepted range and anchors the NY day: a "
                         "break of it carries as the day's range extends, and a break that closes back inside has "
                         "failed and reverts to the IB mid.",
            "complexity": 6,
            "variants": [{"mode": "break"}, {"mode": "fade"}],
            "ported": "ib"}),
    # R/tune2.jsonl line 9 (hm2-lon_break-tf5): "axes": [{"key": "min_rng_atr", "values": [0.0, 1.0, 2.0]}, {"key": "stop_val", ...
    # complexity 4 = London range definition (03:00-08:25) + OCO stop entries one tick beyond at 09:30 (nyam only,
    #                gap-through follow) + minimum-range filter + min_rng_atr
    "lon_break": (LonBreak, {}, True,
                  "C lon_break: at 09:30 (nyam only), OCO stop entries one tick beyond the London (03:00-08:25) high / low; "
                  "skipped when the London range < min_rng_atr x ATR",
                  {"rationale": "NY resolves the London range: the London (03:00-08:25) high and low bound the overnight "
                                "inventory, and the NY open's order flow breaks one side and carries.",
                   "complexity": 4,
                   "variants": [{"min_rng_atr": 0.0}, {"min_rng_atr": 1.0}, {"min_rng_atr": 2.0}],
                   "ported": "lon_break"}),
    # R/tune2.jsonl line 8 (hm2-gap-tf15): "axes": [{"key": "mode", "values": ["fill", "go"]}, {"key": "stop_val", ...
    # complexity 5 = gap definition (09:30 open - prior daily close) + size filter (>= min_gap_atr x daily ATR14)
    #                + entry at the first tf close >= 09:30 (fill: fade to the prior close / go: with the gap)
    #                + min_gap_atr + mode
    "gap": (Gap, {}, False,
            "C gap: nyam only, first tf close >= 09:30, |09:30 open - prior daily close| >= min_gap_atr x daily ATR14. "
            "fill = fade to the prior close (tgt_r unused); go = with the gap. Old pilot: thin / negative ('dead')",
            {"rationale": "The 09:30 open away from the prior daily close leaves an overnight imbalance that the cash "
                          "session must resolve: it is faded back to the prior close (fill) or followed in its "
                          "direction (go).",
             "complexity": 5,
             "variants": [{"mode": "fill"}, {"mode": "go"}],
             "ported": "gap"}),
}
