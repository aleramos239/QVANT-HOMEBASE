"""NEW TIME FAMILIES of the edge library (EDGE_SPEC "Families and their rationale", A and B). No Level-2 feature is read
(FEATURES = ()): both run on NQ, ES and GC.

A  straddle_t   OCO stop entries around the last price at ONE clock time of the Globex day; one trade per time per day.
                ONE REGISTRY ENTRY PER TIME (EDGE_SPEC list, ET): 18:00, 20:00, 00:00, 02:00, 03:00, 08:30, 09:30, 11:05,
                13:30 -> straddle_t_1800 ... straddle_t_1330. The trigger, the ATR30 carry, the anchor price, the 60-minute
                cancel, the flat rule and the time-shuffle null are the engine's `l2ref.StraddleT` (the tester-matched clock
                path: EDGE_VALIDATION "CLOCK", tests/test_edge_clock.py); this module only adds the menu-offset input `off`
                and registers the nine times.
                  entry    at `at`: long stop at last price + offset, short stop at last price - offset, OCO: the fill of
                           one leg cancels the other (the simulator stamps `oco` / `both_sides` on every trade row).
                  offset   the 5 pre-registered offsets (EDGE_SPEC "Variant menu": "Straddle entry offsets (5): ATR30 x
                           {0.25, 0.5, 1.0} . fixed points NQ {10, 20} (ES {2.5, 5}, GC {2, 4})") = the family-parameter
                           variants, named root-free: atr0p25, atr0p5, atr1, ptsA (NQ 10 / ES 2.5 / GC 2 points),
                           ptsB (NQ 20 / ES 5 / GC 4 points); resolved per root from l2sim.menu_offsets(root).
                  cancel   unfilled entries are cancelled 60 minutes after `at` (EDGE_SPEC). AT 02:00 AND 08:30 THEY LIVE
                           55 MINUTES: there the flat time is `at` + 60 min, and the Template (every family, as in the
                           tester) cancels entries 5 minutes before the flat time and takes no entry in those 5 minutes.
                           `entry_life_min(at)` = 55 at 02:00 / 08:30, 60 at the other seven times.
                  flat     at the next listed time or the session end, whichever is first (l2sim.clock_flat):
                           18:00->20:00, 20:00->23:59, 00:00->02:00, 02:00->03:00, 03:00->08:25, 08:30->09:30,
                           09:30->11:00, 11:05->13:30, 13:30->15:58.
                  stops / targets: the 32 exit cells of the menu (ATR = ATR30). max_tr 1.
                LABELS (set BEFORE any menu run; they change no trade, only what a result means):
                  * WEAK RATIONALE (admission needs t >= 3 on BUILD): 00:00 (EDGE_SPEC: no event) AND 11:05. EDGE_SPEC names
                    an event for every other time but none for 11:05 (it is the old pilots' mid-session arm time, not a
                    liquidity event): under user rule 2 that is the same case as 00:00, so it carries the same label.
                    Lifting it needs an event written into EDGE_SPEC before the menus run, never after a number is seen.
                  * SECOND LOOK: 03:00, 09:30 and 13:30. With an ATR offset these entries are the old pilot's
                    straddle-tf30 in london / nyam / pm under a new name (trade for trade the trades entered within 60
                    minutes: tests/test_new_time.py). EDGE_SPEC user rule 3: 2025-26 was already seen once for the old
                    finalists straddle-tf30 nyam / pm (R and RE jobs.jsonl ho-straddle-tf30-*, NQ and ES: sess = all,
                    so the london trades were in the same bundles; GC was never run there): their EXAM is a SECOND
                    look and must be labelled.
                  * DUPLICATE: for the same reason those three entries with atr0p25 / atr0p5 / atr1 and the ported
                    `straddle` (families/port1.py) at tf 30 in london / nyam / pm are ONE strategy registered twice:
                    at most one of them is a library member (dedupe at admission / stacking).
                CLOCK = ET wall clock ALL YEAR, exactly as EDGE_SPEC writes the times. NOT adjusted for foreign DST:
                  * the Tokyo cash open (09:00 JST) is 20:00 ET only while the US is on daylight time; in US winter it is
                    19:00 ET. `straddle_t_2000` fires at 20:00 ET all year, i.e. one hour AFTER the Tokyo open in winter
                    (US standard time = 309 of the 831 BUILD calendar days, 37 %: no event at the fire on those days).
                    EDGE_SPEC lists the time as 20:00 and names the event "(19:00 in winter)": kept as listed, at full
                    strength; marking it weak or firing at 19:00 in winter is the orchestrator's call BEFORE the menus.
                  * the Europe futures / cash opens are 02:00 / 03:00 ET except in the 1-3 weeks each March and late
                    October / early November when the US and Europe are on different DST: then they are 03:00 / 04:00 ET.
                  The US changes its own clock on a Sunday at 02:00, when Globex is closed: no trade date has a missing or
                  repeated ET hour inside a session.
                KNOWN (engine conventions, ENGINE.md 11; state them on any card):
                  * 18:00: the anchor is the previous trade date's last print (16:59:59; Friday's for a Sunday fire; the
                    holiday session's halt print after a two-day holiday file) and the ATR is the closing ATR30 of the
                    previous trade date's evening (24 h old or more). Prior data only, but stale: the trade is in effect
                    "follow the reopen gap" and many fills land in the reopen burst, so the 2 ticks + 250 ms stress is
                    the real gate. The time-shuffle null (18:00 .. 19:30) does not reproduce the reopen. No 18:00 trade
                    on a contract-roll day.
                  * 00:00: anchors on the last evening print and uses the closing ATR30 of the evening just ended.
                  * half days (13:15 ET close): NQ / ES have no 13:30 trade and an open 11:05 trade is closed at 13:15
                    (exit_reason 'eod'), not at 13:30.
                  * COVERAGE RULE (the tester's): a segment with a clock hour without a print is dropped whole, i.e. ALL
                    of that day's fires in the segment, also those before the hole (listed in the run's `skipped`).
                    On BUILD that removes (verify stage, timestamps only) NQ 5 days + 2 evenings, ES 2 days, GC 7 days:
                    e.g. every 00:00 .. 13:30 fire of GC on the day after Thanksgiving (13:45 close) and of NQ / ES
                    on 2023-04-07 (Good Friday with NFP, traded to 09:15: its 08:30 release straddle is lost). The
                    evening fires of such a day still run. A calendar / data-quality effect, not look-ahead.
                  * TIME-SHUFFLE NULL geometry, for reading "beats the null": the shift is one-sided where the window
                    would leave its segment: 18:00 and 00:00 draw 0 .. +90 min, 20:00 and 13:30 draw -90 .. 0, the
                    other five -90 .. +90. A null fire can sit on a neighbouring listed event (the 08:30 null can fire
                    at 09:30), it trades on roll days at 18:00 and on half days at 13:30 where the real fire does not,
                    and its trades can carry another session tag: compare a time with its null over ALL sessions.
                  * a stored run / member spec reads off = <name>, off_mode = 'menu' and an off_val that was NOT used:
                    `resolved(root, inputs)` gives the inputs that ran (ptsA / ptsB are different points per root).

B  vwap_ema_x   EMA(n) of the tf closes crosses the session VWAP at a tf-bar close -> enter at market WITH the cross
                (EMA from below to above = long, from above to below = short). max_tr 3 per session, one position at a time,
                exits = the menu's stop / target and the session end only (an opposite cross does not close a trade).
                  variants  n in {9, 21, 50} x anchor in {session, rth}; tf in {1, 5, 15} = SCREEN_TFS.
                  cross     at every tf close INSIDE the session: side = sign(EMA(n) - VWAP); a cross = the side differs from
                            the last non-zero side seen at an earlier tf close of THIS session (the first close of a session
                            only sets the side; EMA == VWAP changes nothing). Completed bars only.
                  EMA       the Template's: seeded on the first tf close after the restart (00:00 ET; 18:00 for `eve`) and
                            run over every tf bar since, so early in the Globex day an EMA(50) is a shorter average
                            (the old pilot's convention for every EMA family; no extra warm-up was added).
                  VWAP      volume-weighted typical price (h + l + c) / 3 of the 1-minute bars.
                            anchor = session: since the session start.  anchor = rth: the Template's `vwr()` = the old
                            pilot's `anchor` input: 09:30 for nyam / mid / pm, else the session's own start (asia 00:00,
                            london 03:00, pre 08:25, eve 18:00: there is no 09:30 VWAP yet). So the two anchors are the
                            SAME strategy in asia, london, pre, nyam and eve (duplicate cells there) and differ in mid / pm.
                            In mid / pm the `session` anchor is the VWAP restarted at 11:00 / 13:30 (the old pilot's
                            convention), NOT "the day's fair price" of the rationale: there only `rth` is.
                KNOWN (state them on any card): (a) no EMA warm-up: at tf 15 there are at most 12 bars in asia and 24 in
                eve, so EMA(50) there is mostly its seed close; (b) half of the cells are duplicates outside mid / pm (the
                two anchors); (c) slow n at tf 5 / 15 trades very seldom in pre / nyam / mid: such unit-sessions miss the
                100-trade bar and an empty cell counts as "not > 0" in the plateau.
                WEAK PRIOR (EDGE_SPEC B): the old pilot's close-crosses-VWAP family (vwap_flip) did not survive -- state
                that next to any result of this family.

COMPLEXITY = rules + numbers the family fixes or exposes; the common Template inputs (tf, session, the stop / target menu,
max_tr) are not counted (the same convention as the ported families). Counted from the code, before any run.
Tests: tests/test_new_time.py."""
from __future__ import annotations

import l2ref
import l2sim as S

# ---- A. straddle_t ------------------------------------------------------------------------------------------------------------
# EDGE_SPEC "Variant menu": "Straddle entry offsets (5): ATR30 x {0.25, 0.5, 1.0} . fixed points NQ {10, 20} (ES {2.5, 5},
# GC {2, 4})." -> names in the order of l2sim.menu_offsets(root); the two fixed-point sizes differ per root, hence A / B.
OFFS = tuple("atr" + S._num(v) for v in S.MENU_OFF_ATR) + ("ptsA", "ptsB")


def offset_of(root: str, off: str) -> dict:
    """The menu offset `off` on `root` -> {'off_mode': 'atr' | 'pts', 'off_val': x} (l2ref.StraddleT inputs)."""
    return dict(S.menu_offsets(root)[OFFS.index(off)])


def resolved(root: str, inputs: dict) -> dict:
    """The inputs of a stored straddle_t run / member spec with the menu offset WRITTEN OUT for `root`: off = '' and the
    engine's own off_mode / off_val (the same trades; StraddleT and l2ref.StraddleT both accept them). For a card or a
    live implementation: a stored run shows off = <name>, off_mode 'menu' and an off_val that was not used."""
    p = dict(inputs)
    if p.get("off"):
        p.update(offset_of(root, p["off"]), off="")
    return p


def entry_life_min(at: str) -> int:
    """Minutes an unfilled entry of the `at` straddle rests: the 60-minute cancel, or the Template's own cancel 5 minutes
    before the flat time when that comes first (02:00 and 08:30: flat = at + 60 min -> 55)."""
    return min(int(l2ref.StraddleT.DEFAULTS["cancel_min"]), (S.clock_sec(S.clock_flat(at)) - S.clock_sec(at)) // 60 - 5)


class StraddleT(l2ref.StraddleT):
    """Family A (module docstring). Everything is l2ref.StraddleT; added: `off` = one of the 5 menu offsets by name, turned
    into the engine's (off_mode, off_val) for the root of the tape at each segment start (off_mode 'menu').
    A stored run therefore reads off = <name>, off_mode = 'menu' (its off_val is not used): `offset_of(root, off)` gives
    the numbers that ran, `resolved(root, inputs)` the whole input dict. off = '' with off_mode atr / pts + off_val is the
    engine class unchanged."""
    DEFAULTS = {"off": OFFS[1], "off_mode": "menu"}
    SCHEMA = {"off": ("choice", ("",) + OFFS), "off_mode": ("choice", ("menu", "atr", "pts"))}

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        self._menu = self.p["off"]
        if (self.p["off_mode"] == "menu") != bool(self._menu):
            raise ValueError("straddle_t: either off = a menu offset (off_mode 'menu') or off = '' with off_mode atr / pts + off_val")

    def on_session(self, ctx):
        if self._menu:
            o = offset_of(ctx.root, self._menu)
            self.p["off_mode"], self.p["off_val"] = o["off_mode"], o["off_val"]
        super().on_session(ctx)


# EDGE_SPEC A: "Rationale: at scheduled liquidity events new orders arrive and price leaves its pre-event balance; a straddle
# rides whichever side breaks. Events: 18:00 Globex reopen . 20:00 Tokyo cash open (19:00 in winter) . 02:00/03:00 Europe
# futures/cash open . 08:30 US data . 09:30 US cash open . 13:30 afternoon repositioning. 00:00 has NO event behind it
# (tested at the user's request; label WEAK RATIONALE -- it needs stronger evidence to be admitted)."
RATIONALE_A = ("At scheduled liquidity events new orders arrive and price leaves its pre-event balance; a straddle rides "
               "whichever side breaks")
EVENTS = {"18:00": "Globex reopen", "20:00": "Tokyo cash open (19:00 ET in winter: the fire stays at 20:00 ET)",
          "00:00": "NO event behind it; tested at the user's request -- WEAK RATIONALE, needs stronger evidence to be admitted",
          "02:00": "Europe futures open", "03:00": "Europe cash open", "08:30": "US data", "09:30": "US cash open",
          "11:05": "NO event is named for it in EDGE_SPEC, it is the old pilots' mid-session arm time -- WEAK RATIONALE as "
                   "00:00, needs stronger evidence to be admitted",
          "13:30": "afternoon repositioning"}
# WEAK RATIONALE (admission: t >= 3 on BUILD). 00:00: EDGE_SPEC. 11:05: EDGE_SPEC names an event for every other time and none
# for this one (R/desk_review.md: the ORB-mid range 11:00-11:04, armed 11:05; L/SPEC.md: an open_dir "open") -> user rule 2
# makes it the same case as 00:00. Set in the verify round, BEFORE any menu run (no ledger row, no runs/ store existed).
WEAK_TIMES = ("00:00", "11:05")
# SECOND LOOK (EDGE_SPEC user rule 3): the time = a session start of the old pilot's straddle-tf30, whose finalists (nyam / pm)
# were already run on 2025-26 with sess = all (stage holdout, keys ho-straddle-tf30-*, in R/jobs.jsonl = NQ and RE/jobs.jsonl
# = ES: london was in the bundles). GC has no old pilot: its exam is a first look, the label is kept for the entry as a whole.
SECOND_LOOK = {"03:00": "london", "09:30": "nyam", "13:30": "pm"}
SEEN = ("SECOND LOOK: with an ATR offset this entry is the old pilot's straddle-tf30 {0} under a new name (the trades entered "
        "within 60 min), and 2025-26 was already seen once for the old finalists straddle-tf30 nyam / pm (NQ and ES holdout "
        "jobs with sess = all{1}; GC never): the EXAM is a SECOND look. DUPLICATE of the ported `straddle` tf 30 {0} for atr0p25 / atr0p5 / atr1: "
        "at most one of the two is a library member")
# what else a card of the entry must state (module docstring, KNOWN)
CARD_A = {"18:00": "CARD: anchor = the previous trade date's last print, ATR = the previous evening's closing ATR30 (24 h old or "
                   "more): in effect 'follow the reopen gap', many fills land in the reopen burst -> the 2 ticks + 250 ms "
                   "stress is the real gate; the time-shuffle null does not reproduce the reopen",
          "20:00": "CARD: 20:00 ET all year = one hour AFTER the Tokyo open while the US is on standard time (37 % of the BUILD "
                   "calendar days)",
          "08:30": "CARD: the bracket goes live 85 ms after a data release -> the 2 ticks + 250 ms stress is the gate"}
# rules 3 (OCO bracket at the time; cancel after 60 min; flat at the next listed time / session end) + numbers 3 (the clock
# time, the offset, the 60-minute cancel)
COMPLEXITY_A = 6
assert tuple(EVENTS) == S.LISTED_TIMES, "families/timed.py: the times are EDGE_SPEC's list (l2sim.LISTED_TIMES)"


def _straddle_entry(at: str) -> tuple:
    weak = at in WEAK_TIMES
    flat = S.clock_flat(at)[:5]
    life = entry_life_min(at)
    sess = SECOND_LOOK.get(at)
    seen = f"; SECOND LOOK at 2025-26, it is the old pilot's straddle-tf30 {sess}" if sess else ""
    lib = {"rationale": f"{RATIONALE_A} ({at} ET: {EVENTS[at]}{seen}).", "complexity": COMPLEXITY_A,
           "variants": [{"off": k} for k in OFFS]}
    if weak:
        lib["weak"] = True
    event = "no event" if weak else EVENTS[at].split(" (")[0]
    notes = [f"A straddle_t {at} ET ({event}): OCO stop entries at last price +/- offset, cancel unfilled after 60 min"
             + (f" (entries live {life} min here: the Template cancels them 5 min before the flat time)" if life < 60 else "")
             + f", flat {flat}, 1 trade per day"]
    if weak:
        notes.append("WEAK RATIONALE")
    if sess:
        notes.append(SEEN.format(sess, "" if sess in ("nyam", "pm") else f", so {sess} was in the same bundles"))
    if at in CARD_A:
        notes.append(CARD_A[at])
    return (StraddleT, {"at": at}, True, "; ".join(notes), lib)


# ---- B. vwap_ema_x ------------------------------------------------------------------------------------------------------------
class VwapEmaX(S.Template):
    """Family B (module docstring): EMA(n) of the tf closes crosses the VWAP at a tf-bar close -> market entry with the cross."""
    DEFAULTS = {"n": 21, "anchor": "session", "max_tr": 3}
    SCHEMA = {"n": ("choice", (9, 21, 50)), "anchor": ("choice", ("session", "rth"))}
    SPANS = (9, 21, 50)
    SCREEN_TFS = ("1", "5", "15")
    FEATURES = ()

    def fam_session(self, ctx, s):
        self.side_p = 0                            # the last non-zero side of EMA(n) - VWAP at a tf close of this session
        self.seen = 0                              # tf closes inside this session already looked at (self.sn counts them)
        self.go = 0

    def fam_update(self, ctx):
        self.go = 0
        if self.sid is None or self.sn == self.seen:            # not a tf close inside the session
            return
        self.seen = self.sn
        v = self.vw() if self.p["anchor"] == "session" else self.vwr()
        if v is None:
            return
        e = self.E[self.p["n"]]
        sd = (e > v[0]) - (e < v[0])
        if not sd:
            return
        if self.side_p and sd != self.side_p:
            self.go = sd
        self.side_p = sd

    def fam_signal(self, ctx):
        if self.go:
            self._mkt(ctx, "long" if self.go > 0 else "short")


# EDGE_SPEC B: "`vwap_ema_x` (user request) -- EMA(n) of closes crosses the session VWAP at a tf-bar close -> enter with the
# cross. Variants: n in {9, 21, 50} x tf in {1, 5, 15} x anchor in {session, RTH 09:30}. Rationale: when the fast average
# crosses the day's fair price, control of the day has changed sides and the wrong side must exit. WEAK PRIOR: the old pilot's
# close-crosses-VWAP family (vwap_flip) did not survive -- state that next to any result."
# "PROPER RE-RUN" 4: "New families: ... vwap_ema_x and straddle_t as listed."  (tf is the unit: SCREEN_TFS.)
VARIANTS_B = [{"n": n, "anchor": a} for n in (9, 21, 50) for a in ("session", "rth")]

FAMILIES = {f"straddle_t_{at.replace(':', '')}": _straddle_entry(at) for at in S.LISTED_TIMES}
FAMILIES["vwap_ema_x"] = (
    VwapEmaX, {}, False,
    "B vwap_ema_x: EMA(n) of tf closes crosses the session VWAP at a tf close -> market with the cross; max_tr 3; WEAK PRIOR "
    "(the old pilot's vwap_flip did not survive); CARD: anchors session / rth are the SAME strategy in eve / asia / london / "
    "pre / nyam (duplicate cells); in mid / pm the session anchor is the VWAP restarted at 11:00 / 13:30, only rth is the "
    "day's fair price; no EMA warm-up (tf 15: at most 12 bars in asia, 24 in eve -> EMA(50) is mostly its seed); slow n at "
    "tf 5 / 15 is thin in pre / nyam / mid against the 100-trade bar",
    {"rationale": "When the fast average crosses the day's fair price, control of the day has changed sides and the wrong side "
                  "must exit.",
     "complexity": 3,                               # rule 1 (the cross -> enter with it) + numbers 2 (n, the VWAP anchor)
     "variants": VARIANTS_B, "weak": True})
