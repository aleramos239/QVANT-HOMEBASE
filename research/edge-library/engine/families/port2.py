"""PORT GROUP 2 of the old NQ pilot's families (EDGE_SPEC family C; R = research/prop-portfolio/2026-09-29):
    ema_ribbon, tema_slope, ema_pullback, supertrend, rsi2, first_bar_mom, tod_drift, mid_fade.

Each class body below is the VERBATIM `class Fam` body of R/families/<fam>.py (the trigger code that gen_drafts.py spliced
into R/template.py to make the tester draft pp_<fam>), on l2sim.Template (= the port of R/template.py). Nothing is added,
re-tuned or re-defined: inputs, ranges and defaults are those of the tester draft (R/families/<fam>.py INPUTS / OVERRIDES).
`SESS` and `_hms` are l2sim's module globals (the R session table + the new sessions `pre` and `eve`), so a family that
reads `SESS[s]` (tod_drift) also runs in the two new sessions without any change.

TESTER-MATCH GATE (ENGINE.md 8): engine/port2_validate.py -> engine/PORT2_VALIDATION.md (every NQ and ES screen run of these
eight families at tf 1 / 5 / 15 / 30 + every cell of their sizing heat-maps, trade identity only, in-sample bundles only).
Tests: tests/test_port2.py. READ engine/PORT2_NOTES.md BEFORE THE BUILD RUN: it lists the decisions the orchestrator owes.

REGISTRY FIELDS
  rationale    the family's hypothesis as written in R/families/<fam>.py's docstring on 2026-09-29, BEFORE the old pilot's
               screen ran (EDGE_SPEC C: "Rationale per family as in R/SPEC.md"). Quoted, not rewritten after any result.
  complexity   rules + free parameters of the FAMILY: the trigger rules, plus every number the family ITSELF fixes or
               exposes (indicator lengths, multipliers, thresholds, offsets). NOT counted, for every family alike: what the
               Template gives all families -- tf, session, the stop / target menu, its Wilder ATR(14) of the tf bars
               (first_bar_mom), its daily ATR(14) `datr()` and its session clock (mid_fade's 09:30 -> 11:00 = the nyam
               session). Counted from the code below, before any run; it only breaks ties.
  variants     EDGE_SPEC "PROPER RE-RUN" item 4: the values of the FIRST axis of the family's heat-map in R/tune1.jsonl /
               R/tune2.jsonl; "families whose first axis is max_tr or that have no grid: defaults only". The source line is
               quoted next to each entry.
  weak         tod_drift ONLY (set 2026-10-02, before any menu run): its rationale names no counterparty, no flow and no
               reason to persist -- the old source calls it a "control for pure clock effects" (R/SPEC.md 17: "Tests pure
               time-of-day drift"). EDGE_SPEC user rule 2 rejects an effect without a reason and labels the analogous
               straddle_t 00:00 ("NO event behind it") WEAK; the same standard is applied here: admission needs t >= 3 on
               BUILD. The other seven keep `weak` unset: EDGE_SPEC C accepts their R/SPEC.md hypotheses (its own examples
               -- "donchian = trend continuation", "vwap fades = mean reversion to fair price" -- are of the same kind).
  SCREEN_TFS   the tfs the old screen ran for the family (R/screen.jsonl: tf 1, 5, 15, 30 for all eight).
All eight read no Level-2 feature (FEATURES = ()), place market entries only (both_sides False) and keep no state across a
session date (session_independent stays True: every attribute is (re)built in fam_day / by the Template's on_session).

DECLARED BELOW THE REGISTRY (facts for the Admit / exam stages, written before any run; none changes a trade):
  SECOND_LOOK   the families whose 2025-26 was already read by the old pilots (holdout-stage job keys of R / RE
                jobs.jsonl; keys only, no bundle was opened) -> `second_look(name)` = the label EDGE_SPEC rule 3 demands.
  MIRROR_AXIS   tod_drift's `dir`: its long and short variants are OPPOSITE hypotheses on the same clock time.
  can_trade()   which (variant, tf, session) cells can trade at all by the family's own rules (see below).
  plateau_sets() / tradable()   the pre-declared ALTERNATIVE ways to read tod_drift's plateau (orchestrator's decision).

KNOWN, STRUCTURAL (not tuned, stated before any run):
  * indicators restart at 00:00 ET (and at 18:00 for `eve`): a family with a long warm-up trades little or not at all early
    in asia / eve at tf 15 / 30 (ema_pullback WARM 20, ema_ribbon / supertrend WARM 10, tema_slope WARM 8). Never a trade
    (can_trade False for every variant): ema_pullback tf 15 asia and tf 30 eve / asia / london / pre; ema_ribbon,
    supertrend and tema_slope tf 30 asia.
  * first_bar_mom never trades in asia or eve: the session's first tf bar is also the first bar since the restart, so no
    ATR exists before it (the old docstring says so for asia). In `pre` (08:25 start, not a multiple of tf 15 / 30) the
    "first bar" at tf 15 / 30 is the clock bar that CLOSES first inside the session (08:15-08:30 / 08:00-08:30), i.e. mostly
    pre-session data. At tf 5 / 15 / 30 that close is 08:30:00: the market order goes live at 08:30:00.085, ON the US data
    release, and is filled at the next print + 1 tick. No look-ahead, but an execution-realism risk on data days: for a
    `pre` member the 2 ticks + 250 ms stress test is the decisive number (tf 1 enters at 08:26).
  * tod_drift: the entry needs 3 tf bars since the restart and a print in the window, and lies before the last 5 minutes
    of the session -> no trade at 00:00 / 18:00 with off_min 0 (as in the tester: asia), none in `pre` with off_min 60
    (08:25 + 60 min = 09:25 = the no-entry line); in eve / asia at tf 15 only off_min 60 trades, at tf 30 nothing.
    Such (variant, session) cells have zero trades by construction.
  * tod_drift, THE MIRROR: `dir` long and short at the same offset are the same entries on opposite sides (with the 1:1
    target exact mirror trades, costs aside; in the other exit cells only the exits differ). Under the family's OWN
    hypothesis -- a drift in one direction -- the other direction's half of the unit's cells loses, so about 50 % of a
    unit-session's 256 cells can be > 0 at best, against the plateau's 60 %: read literally (EDGE_SPEC "PROPER RE-RUN" 4:
    "tod_drift off_min x dir", "the plateau is judged over ALL (parameter x exit) cells of a unit") a tod_drift
    unit-session can pass only if BOTH directions make money at the same clock time (a volatility effect of tight stops,
    not the stated drift). The registry follows EDGE_SPEC literally (8 variants in one unit); judging per direction
    (`plateau_sets`) is a deviation only the orchestrator may switch on, BEFORE the BUILD run (PORT2_NOTES.md, decision 1).
  * tod_drift is fired by the clock but is a VERBATIM port of a Template bar family: it runs at every screen tf, its ATR
    stop is the Template's Wilder ATR(14) of ITS OWN tf bars (not the ATR30 of EDGE_SPEC's time-fired straddle_t), and it
    has no `shift_seed` input, so run_menus gives it the C1 random-entry control (day- and session-matched), not the
    time-shuffle null. The tester draft pp_tod_drift does exactly this (PORT2_VALIDATION.md).
  * tod_drift keeps `exit_bars` 6 (the tester draft's default): its menu cells with target "none" end after 6 tf bars
    (or at the stop / the session end), not at the session end.
  * supertrend starts every restart (00:00, and 18:00 in `eve`) with direction up: the first signal after a restart can
    only be a short (the old code, unchanged).
  * mid_fade trades the `mid` session only (fam_filter): its `pre` and `eve` instances never trade.
  * mid_fade reads the daily ATR (`datr()`, prior daily bars): no trade before 15 daily bars exist.
"""
from __future__ import annotations

from l2sim import SESS, Template, _hms

TFS = ("1", "5", "15", "30")                   # R/screen.jsonl: screen-<fam>-tf1 / tf5 / tf15 / tf30 for every family here


class EmaRibbon(Template):
    """EMA ribbon. Hypothesis: EMA 8/21/55 becoming fully stacked marks a fresh trend leg; enter on the bar the
    stack forms (long 8>21>55, short reverse). EMAs seed at the day's first tf bar, so tf 30 is barely warm.
    No structural stop (atr fallback)."""
    SCREEN_TFS = TFS
    FEATURES = ()
    SPANS = (8, 21, 55)
    WARM = 10

    def fam_day(self, ctx):
        self.al, self.chg = 0, 0

    def fam_update(self, ctx):
        a, b, c = self.E[8], self.E[21], self.E[55]
        prev = self.al
        self.al = 1 if a > b > c else -1 if a < b < c else 0
        self.chg = self.al if self.al and self.al != prev else 0

    def fam_signal(self, ctx):
        if self.chg:
            self._mkt(ctx, "long" if self.chg > 0 else "short")


class TemaSlope(Template):
    """TEMA slope turn. Hypothesis: the low-lag TEMA(n) changing slope sign marks a turn early; enter in the new
    slope direction. TEMA = 3E1 - 3E2 + E3 on tf closes, seeded each day. No structural stop (atr fallback)."""
    DEFAULTS = {"n": 20}
    SCHEMA = {"n": ("int", 3, 100)}                                                                # as pp_tema_slope
    SCREEN_TFS = TFS
    FEATURES = ()
    WARM = 8

    def fam_day(self, ctx):
        self.t1 = self.t2 = self.t3 = self.tp = None
        self.tsg, self.flip = 0, 0

    def fam_update(self, ctx):
        k, c = 2.0 / (int(self.p["n"]) + 1), self.C[-1]
        if self.t1 is None:
            self.t1 = self.t2 = self.t3 = c
        else:
            self.t1 += k * (c - self.t1)
            self.t2 += k * (self.t1 - self.t2)
            self.t3 += k * (self.t2 - self.t3)
        te = 3 * self.t1 - 3 * self.t2 + self.t3
        self.flip = 0
        if self.tp is not None:
            sg = 1 if te > self.tp else -1 if te < self.tp else 0
            if sg:
                if self.tsg and sg != self.tsg:
                    self.flip = sg
                self.tsg = sg
        self.tp = te

    def fam_signal(self, ctx):
        if self.flip:
            self._mkt(ctx, "long" if self.flip > 0 else "short")


class EmaPullback(Template):
    """EMA pullback. Hypothesis: in a trend (EMA50 slope) a dip that tags EMA20 and closes back on the trend
    side is a continuation entry. struct stop = the pullback bar's extreme."""
    SCREEN_TFS = TFS
    FEATURES = ()
    SPANS = (20, 50)
    WARM = 20

    def fam_signal(self, ctx):
        e20, e50, p50 = self.E[20], self.E[50], self.Ep[50]
        if p50 is None:
            return
        h, l, c = self.H[-1], self.L[-1], self.C[-1]
        if e50 > p50 and l <= e20 < c:
            self._mkt(ctx, "long", struct=l)
        elif e50 < p50 and h >= e20 > c:
            self._mkt(ctx, "short", struct=h)


class Supertrend(Template):
    """Supertrend(10, 3) flip. Hypothesis: a flip of the ATR-band trend line starts a directional leg; enter in
    the new direction. struct stop = the Supertrend line after the flip."""
    SCREEN_TFS = TFS
    FEATURES = ()
    WARM = 10

    def fam_day(self, ctx):
        self.sa = self.up = self.dn = self.line = None
        self.dr, self.flip = 1, 0

    def fam_update(self, ctx):
        tr, n = self.TR[-1], self.nb
        self.sa = sum(self.TR) / n if n <= 10 else (self.sa * 9.0 + tr) / 10.0
        h, l, c = self.H[-1], self.L[-1], self.C[-1]
        up, dn = (h + l) / 2.0 - 3 * self.sa, (h + l) / 2.0 + 3 * self.sa
        self.flip = 0
        if self.up is not None:
            pc = self.C[-2]
            if pc > self.up:
                up = max(up, self.up)
            if pc < self.dn:
                dn = min(dn, self.dn)
            if self.dr == -1 and c > self.dn:
                self.dr, self.flip = 1, 1
            elif self.dr == 1 and c < self.up:
                self.dr, self.flip = -1, -1
        self.up, self.dn = up, dn
        self.line = up if self.dr == 1 else dn

    def fam_signal(self, ctx):
        if self.flip:
            self._mkt(ctx, "long" if self.flip > 0 else "short", struct=self.line)


class Rsi2(Template):
    """RSI(2) mean reversion. Hypothesis: a 2-bar RSI below th (above 100-th) is a short-term exhaustion that
    snaps back; fade it at the close. trend_f=True only takes longs with EMA50 rising / shorts with it falling.
    No structural stop (atr fallback)."""
    DEFAULTS = {"th": 10.0, "trend_f": False}
    SCHEMA = {"th": ("float", 1, 40), "trend_f": ("bool",)}                                        # as pp_rsi2
    SCREEN_TFS = TFS
    FEATURES = ()
    WARM = 4

    def fam_day(self, ctx):
        self.ag = self.alo = self.rsi = None

    def fam_update(self, ctx):
        if self.nb < 2:
            return
        d = self.C[-1] - self.C[-2]
        g, ls = max(d, 0.0), max(-d, 0.0)
        if self.ag is None:
            self.ag, self.alo = g, ls
        else:
            self.ag, self.alo = (self.ag + g) / 2.0, (self.alo + ls) / 2.0
        self.rsi = 50.0 if self.ag + self.alo == 0 else 100.0 if self.alo == 0 else 100 - 100 / (1 + self.ag / self.alo)

    def fam_signal(self, ctx):
        r, th = self.rsi, float(self.p["th"])
        if r is None:
            return
        sl_ = self.E[50] - self.Ep[50] if self.Ep[50] is not None else 0.0
        tf_ = self.p["trend_f"]
        if r < th and (not tf_ or sl_ > 0):
            self._mkt(ctx, "long")
        elif r > 100 - th and (not tf_ or sl_ < 0):
            self._mkt(ctx, "short")


class FirstBarMom(Template):
    """First-bar momentum. Hypothesis: a session's first tf bar with range >= k x ATR (ATR before that bar)
    is momentum ignition; follow its direction at its close. struct stop = the bar's opposite extreme.
    Asia lacks ATR history at 00:00 (no trades until 3 tf bars exist, so effectively none)."""
    DEFAULTS = {"k": 1.5}
    SCHEMA = {"k": ("float", 0.2, 10)}                                                             # as pp_first_bar_mom
    SCREEN_TFS = TFS
    FEATURES = ()

    def fam_signal(self, ctx):
        if self.sn != 1 or not self.atr_p:
            return
        o, h, l, c = self.O[-1], self.H[-1], self.L[-1], self.C[-1]
        if h - l < float(self.p["k"]) * self.atr_p or c == o:
            return
        self._mkt(ctx, "long" if c > o else "short", struct=l if c > o else h)


class TodDrift(Template):
    """Time-of-day drift (control for pure clock effects). Hypothesis: a fixed-direction position held for a
    fixed time from a session offset earns a stable drift. Enters dir (long|short, default long) at session
    start + off_min, exits after exit_bars tf bars (default 6) or at the stop / session end; max 1 per session.
    tgt_r defaults to 0 (no target). No structural stop."""
    # R/families/tod_drift.py OVERRIDES (the tester draft's own defaults of four common inputs) + INPUTS
    DEFAULTS = {"dir": "long", "exit_bars": 6, "tgt_r": 0.0, "max_tr": 1, "off_min": 0}
    SCHEMA = {"dir": ("choice", ("long", "short")), "off_min": ("int", 0, 240)}                    # as pp_tod_drift
    SCREEN_TFS = TFS
    FEATURES = ()

    def fam_times(self):
        om = int(self.p["off_min"]) * 60
        return [_hms(SESS[s][0] + om) for s in self.sessions()]

    def fam_time(self, ctx, sec):
        s, lp = self.sid, ctx.last_price
        if s is None or lp is None or sec != SESS[s][0] + int(self.p["off_min"]) * 60 or not self.can_enter(ctx):
            return
        self._mkt(ctx, self.p["dir"], ref=lp)


class MidFade(Template):
    """Lunch mean reversion (mid session only). Hypothesis: a large NY AM move (09:30 open to the 11:00 close)
    of at least k x daily ATR(14) is over-extended; fade it at the first tf close of mid. No structural stop."""
    DEFAULTS = {"k": 0.3}
    SCHEMA = {"k": ("float", 0, 3)}                                                                # as pp_mid_fade
    SCREEN_TFS = TFS
    FEATURES = ()

    def fam_filter(self, ids):
        return [s for s in ids if s == "mid"]

    def fam_signal(self, ctx):
        da, op, cl = self.datr(), self.mo(34200), self.mc(34200, 39600)
        if self.sn != 1 or not da or op is None or cl is None:
            return
        mv = cl - op
        if abs(mv) >= float(self.p["k"]) * da and mv != 0:
            self._mkt(ctx, "short" if mv > 0 else "long")


SEEN = "2025-26 was already read once for this family's old finalists (R / RE jobs.jsonl stage holdout): EXAM = a SECOND look"

FAMILIES = {      # name -> (StrategyClass, default_inputs, both_sides, notes, LIBRARY dict)
    "ema_ribbon": (EmaRibbon, {}, False,
                   "C (R 5): EMA 8 / 21 / 55 become fully stacked at this tf close -> market with the stack; ATR stop",
                   {"rationale": "EMA 8/21/55 becoming fully stacked marks a fresh trend leg; enter on the bar the stack forms "
                                 "(long 8>21>55, short reverse).",
                    "complexity": 4,                 # 1 rule (the stack forms on this bar) + 3 fixed lengths (8, 21, 55)
                    # R/tune2.jsonl line 4, key hm2-ema_ribbon-tf1: "axes": [{"key": "max_tr", "values": [1, 3]},
                    #   {"key": "stop_val", ...}, {"key": "tgt_r", ...}] -> first axis max_tr -> defaults only (R/tune1: no grid)
                    "variants": [{}],
                    "ported": "ema_ribbon"}),
    "tema_slope": (TemaSlope, {}, False,
                   "C (R 6): TEMA(n) slope changes sign at a tf close -> market in the new slope direction; ATR stop. "
                   "ES finalist: " + SEEN,
                   {"rationale": "The low-lag TEMA(n) changing slope sign marks a turn early; enter in the new slope direction.",
                    "complexity": 2,                 # 1 rule (slope sign flips) + 1 parameter (n)
                    # R/tune1.jsonl line 12, key hm-tema_slope-tf5 (and R/tune2.jsonl line 10, hm2-tema_slope-tf1):
                    #   "axes": [{"key": "n", "values": [10, 20, 40]}, {"key": "stop_val", ...}, {"key": "tgt_r", ...}]
                    "variants": [{"n": 10}, {"n": 20}, {"n": 40}],
                    "ported": "tema_slope"}),
    "ema_pullback": (EmaPullback, {}, False,
                     "C (R 7): EMA50 slope up and a bar tags EMA20 from above and closes back over it -> long (mirror short); "
                     "struct stop = the pullback bar's extreme. " + SEEN,
                     {"rationale": "In a trend (EMA50 slope) a dip that tags EMA20 and closes back on the trend side is a "
                                   "continuation entry.",
                      "complexity": 4,               # 2 rules (trend by EMA50 slope; tag of EMA20 + close back) + 2 lengths (20, 50)
                      # R/tune1.jsonl line 13, key hm-ema_pullback-tf5 (and R/tune2.jsonl line 14, hm2-ema_pullback-tf1):
                      #   "axes": [{"key": "max_tr", "values": [1, 3]}, {"key": "stop_val", ...}, {"key": "tgt_r", ...}]
                      #   -> first axis max_tr -> defaults only
                      "variants": [{}],
                      "ported": "ema_pullback"}),
    "supertrend": (Supertrend, {}, False,
                   "C (R 8): Supertrend(10, 3) flips at a tf close -> market in the new direction; struct stop = the line",
                   {"rationale": "A flip of the ATR-band trend line (Supertrend 10, 3) starts a directional leg; enter in the "
                                 "new direction.",
                    "complexity": 3,                 # 1 rule (the line flips) + 2 fixed numbers (ATR length 10, multiple 3)
                    # R/tune2.jsonl line 5, key hm2-supertrend-tf5: "axes": [{"key": "max_tr", "values": [1, 3]},
                    #   {"key": "stop_val", ...}, {"key": "tgt_r", ...}] -> first axis max_tr -> defaults only (R/tune1: no grid)
                    "variants": [{}],
                    "ported": "supertrend"}),
    "rsi2": (Rsi2, {}, False,
             "C (R 9): RSI(2) < th at a tf close -> long, > 100 - th -> short (fade); ATR stop; trend_f off. " + SEEN,
             {"rationale": "A 2-bar RSI below th (above 100-th) is a short-term exhaustion that snaps back; fade it at the close.",
              "complexity": 3,                       # 1 rule (RSI beyond the threshold -> fade) + RSI length 2 + threshold th
              # R/tune1.jsonl line 11, key hm-rsi2-tf5 (and R/tune2.jsonl line 11, hm2-rsi2-tf1):
              #   "axes": [{"key": "th", "values": [5.0, 10.0, 15.0]}, {"key": "stop_val", ...}, {"key": "tgt_r", ...}]
              "variants": [{"th": 5.0}, {"th": 10.0}, {"th": 15.0}],
              "ported": "rsi2"}),
    "first_bar_mom": (FirstBarMom, {}, False,
                      "C (R 20): the session's first tf bar has range >= k x ATR -> market in its direction at its close; "
                      "struct stop = the bar's other extreme. " + SEEN,
                      {"rationale": "A session's first tf bar with range >= k x ATR (ATR before that bar) is momentum ignition; "
                                    "follow its direction at its close.",
                       "complexity": 3,              # 2 rules (first bar of the session; range >= k x ATR, follow it) + k
                       # R/tune1.jsonl line 8, key hm-first_bar_mom-tf15:
                       #   "axes": [{"key": "k", "values": [1.0, 1.5, 2.0]}, {"key": "stop_val", ...}, {"key": "tgt_r", ...}]
                       "variants": [{"k": 1.0}, {"k": 1.5}, {"k": 2.0}],
                       "ported": "first_bar_mom",
                       # EDGE_SPEC C: "Families whose in-sample favourites FAILED on 2025-26 (donchian pm, first_bar_mom nyam)
                       #   start with a penalty: they need the plateau on BUILD and PICK and a reason why the failure was noise."
                       "penalty": "in-sample favourite (first_bar_mom tf15 nyam) FAILED on 2025-26: needs the plateau on BUILD "
                                  "and PICK and a reason why the failure was noise"}),
    "tod_drift": (TodDrift, {}, False,
                  "C (R 17): market `dir` at session start + off_min, out after 6 tf bars / stop / session end; 1 per session; "
                  "pure clock effect (the old pilot's control for it): WEAK RATIONALE. long and short are opposite "
                  "hypotheses in one unit (PORT2_NOTES.md). " + SEEN,
                  {"rationale": "A fixed-direction position held for a fixed time from a session offset earns a stable drift "
                                "(pure time-of-day effect).",
                   # WEAK RATIONALE (EDGE_SPEC user rule 2; set before any menu run): no counterparty, no flow, no reason to
                   # persist -- R/families/tod_drift.py: "control for pure clock effects"; R/SPEC.md 17: "Tests pure
                   # time-of-day drift". Same standard as straddle_t 00:00 ("NO event behind it"): t >= 3 on BUILD.
                   "weak": True,
                   "complexity": 5,                  # 2 rules (enter at start + offset; time exit) + off_min, dir, exit_bars
                   # EDGE_SPEC "PROPER RE-RUN" 4: "tod_drift off_min x dir".
                   # R/tune1.jsonl line 3, key hm-tod_drift-tf5 (and R/tune2.jsonl lines 17 / 18, hm2-tod_drift-tf15 / tf30):
                   #   "axes": [{"key": "off_min", "values": [0, 15, 30, 60]}, {"key": "exit_bars", "values": [6, 12, 24]},
                   #            {"key": "dir", "values": ["long", "short"]}]        (exit_bars stays the default 6)
                   "variants": [{"off_min": m, "dir": d} for m in (0, 15, 30, 60) for d in ("long", "short")],
                   "ported": "tod_drift"}),
    "mid_fade": (MidFade, {}, False,
                 "C (R 21): mid only; |09:30 open -> 11:00 close| >= k x daily ATR(14) -> fade it at the first tf close of mid",
                 {"rationale": "A large NY AM move (09:30 open to the 11:00 close) of at least k x daily ATR(14) is "
                               "over-extended; fade it at the first tf close of mid (lunch mean reversion).",
                  "complexity": 3,                   # 2 rules (first tf close of mid; AM move >= k x daily ATR -> fade) + k
                  #   (the daily ATR(14) and the 09:30 -> 11:00 window are the Template's: not counted, see the module docstring)
                  # no heat-map of mid_fade in R/tune1.jsonl or R/tune2.jsonl (no line names draft_pp_mid_fade)
                  #   -> "families ... that have no grid: defaults only"
                  "variants": [{}],
                  "ported": "mid_fade"}),
}


# ---- facts for the Admit / exam stages (declared 2026-10-02 BEFORE any menu run; nothing below changes a trade) ------------

# EDGE_SPEC user rule 3: a family whose 2025-26 was already seen once "must be labelled": its EXAM is a SECOND look.
# family -> root -> the tfs with `holdout`-stage jobs in the old pilots' job lists (R/jobs.jsonl = NQ, RE/jobs.jsonl = ES;
# keys ho-<fam>-tf<tf>-*; job KEYS only were read, never a holdout bundle). EDGE_SPEC's own list names first_bar_mom and
# tod_drift only; the job lists also hold ema_pullback, rsi2 and (ES) tema_slope. Whether those favourites FAILED on
# 2025-26 is sealed here, so only first_bar_mom carries EDGE_SPEC's `penalty` (PORT2_NOTES.md, decision 3).
SECOND_LOOK = {
    "tema_slope": {"ES": ("5",)},
    "ema_pullback": {"NQ": ("1", "5"), "ES": ("5",)},
    "rsi2": {"NQ": ("1", "5"), "ES": ("5",)},
    "first_bar_mom": {"NQ": ("15",), "ES": ("30",)},
    "tod_drift": {"NQ": ("5", "15", "30"), "ES": ("5", "15")},
}

# A variant axis whose values are OPPOSITE hypotheses on the same entries (same clock time, opposite sides): tod_drift `dir`.
MIRROR_AXIS = {"tod_drift": "dir"}


def second_look(name: str) -> str | None:
    """The EDGE_SPEC rule-3 label of a family for its member card / the exam report, or None (2025-26 never read)."""
    seen = SECOND_LOOK.get(name)
    if not seen:
        return None
    where = "; ".join(f"{root} tf {' / '.join(tfs)}" for root, tfs in seen.items())
    return (f"SECOND LOOK: 2025-26 was already read once for this family's old finalists ({where}); the EXAM is not a first "
            "look for it -- its real proof is forward paper / shadow trading")


def can_trade(name: str, variant: dict, tf, sess: str) -> bool:
    """Can this (family variant, tf, session) trade AT ALL by the family's own rules? False = zero trades by construction
    (the module docstring's structural list), which the plateau counts as "not > 0". From the code above and the Template's
    gates only (no data): the session window, the warm-up (WARM tf bars since the restart at 00:00, or 18:00 for `eve`),
    no entry in the last 5 minutes of a session, first_bar_mom / mid_fade's "first tf close of the session", tod_drift's
    clock time, mid_fade's session filter. True does not promise a trade (the trigger must still fire)."""
    cls, inputs = FAMILIES[name][0], FAMILIES[name][1]
    p = {**cls.defaults(), **inputs, **variant}
    if sess not in cls({**inputs, **variant, "tf": str(tf), "sess": sess if sess in ("pre", "eve") else "all"}).sessions():
        return False                                   # the family's own session filter (mid_fade: mid only)
    a, b = SESS[sess]
    step, restart = int(tf) * 60, (a if sess == "eve" else 0)
    if name == "tod_drift":                            # fam_time at session start + off_min: 3 tf bars closed by then
        t = a + int(p["off_min"]) * 60
        return t < b - 300 and (t - restart) // step >= cls.WARM
    closes = [e for e in range(restart + step, b + 1, step) if a < e]           # the tf closes that belong to the session
    if name in ("first_bar_mom", "mid_fade"):
        closes = closes[:1]                            # `self.sn != 1`: only the session's first tf close
    return any(e < b - 300 and (e - restart) // step >= cls.WARM for e in closes)


def tradable(name: str, table: list, tf, sess: str) -> list:
    """The rows of a unit-session plateau table (library.session_table: 'vi' = variant index) whose variant can trade there."""
    variants = FAMILIES[name][4]["variants"]
    return [r for r in table if can_trade(name, variants[r["vi"]], tf, sess)]


def plateau_sets(name: str, table: list) -> dict:
    """Split ONE unit-session plateau table (library.session_table rows) into its plateau sets. It only SPLITS: it never
    judges and never drops a cell (`tradable` drops the cells that cannot trade by construction).
      a family without a MIRROR_AXIS   {"all": table}: EDGE_SPEC's rule, one plateau over ALL the unit's cells.
      tod_drift                        {"long": [128 rows], "short": [128 rows]}: one set per direction.
    THE DEFAULT FOR tod_drift IS ALSO THE LITERAL RULE -- library.plateau(table) over all 256 cells. The per-direction
    sets are a PRE-DECLARED ALTERNATIVE (written before any run), to be used ONLY if the orchestrator decides so before
    the BUILD run: each set is then judged by library.plateau on its own, and a pass makes that direction's central cell
    the candidate (two looks per unit-session instead of one: say so next to the result)."""
    axis = MIRROR_AXIS.get(name)
    if axis is None:
        return {"all": list(table)}
    variants = FAMILIES[name][4]["variants"]
    out: dict = {}
    for r in table:
        out.setdefault(str(variants[r["vi"]][axis]), []).append(r)
    return out
