"""The new time families (families/timed.py; EDGE_SPEC families A and B):
  A  straddle_t_<HHMM>  OCO stop entries around the last price at one clock time (nine registry entries)
  B  vwap_ema_x         EMA(n) of the tf closes crosses the VWAP at a tf-bar close -> market entry with the cross

What is pinned here:
  * the registry entries are the pre-registration (times, offsets, variants, rationale, complexity) and carry their labels:
    WEAK RATIONALE (00:00 and 11:05: no event), SECOND LOOK + DUPLICATE (03:00 / 09:30 / 13:30 = the old pilot's
    straddle-tf30 london / nyam / pm: trade for trade on real BUILD days);
  * how long an unfilled entry rests at EVERY time (60 minutes; 55 at 02:00 and 08:30), the time-shuffle null's shift
    range per time, and the coverage rule that drops a holiday's day fires;
  * both triggers on SYNTHETIC tapes with hand-computed levels / bars (no market data);
  * on real BUILD days: straddle_t = the engine's tester-matched l2ref.StraddleT with the menu offset of the root (NQ, ES, GC);
    every vwap_ema_x trade sits on a cross re-derived independently from the raw prints;
  * 1 worker = W workers (L2_TEST_WORKERS, default 8), incl. the time-shuffle null;
  * NO LOOK-AHEAD: every print from a cut time on is replaced by garbage -> the decisions up to the cut and the trades closed
    before it are unchanged;
  * the clock is ET all year (20:00 ET is one hour after the Tokyo open in US winter; documented, not adjusted).
Identity, timing, order prices and counts only: no P&L is judged anywhere in this file."""
import datetime as dt
import os
from zoneinfo import ZoneInfo

import numpy as np
import pytest

import families
import l2ref
import l2sim as S
import run_menus as RM
from families import timed as T

W = max(2, min(int(os.environ.get("L2_TEST_WORKERS", "8")), S.MAX_WORKERS))
D = dt.date(2023, 3, 14)                            # a BUILD weekday (EDT), not a roll day
TIMES = ("18:00", "20:00", "00:00", "02:00", "03:00", "08:30", "09:30", "11:05", "13:30")          # EDGE_SPEC A, verbatim
FLAT = {"18:00": "20:00", "20:00": "23:59", "00:00": "02:00", "02:00": "03:00", "03:00": "08:25", "08:30": "09:30",
        "09:30": "11:00", "11:05": "13:30", "13:30": "15:58"}       # "the next listed time or the session end, whichever is first"
NAMES = ["straddle_t_" + t.replace(":", "") for t in TIMES]
OFFS = ("atr0p25", "atr0p5", "atr1", "ptsA", "ptsB")
WEAK = ("00:00", "11:05")                           # no event: EDGE_SPEC says so for 00:00 and names none for 11:05
SEEN = {"03:00": "london", "09:30": "nyam", "13:30": "pm"}          # = the old pilot's straddle-tf30 in that session (SECOND LOOK)
LIFE = {at: 55 if at in ("02:00", "08:30") else 60 for at in TIMES}  # minutes an unfilled entry rests (flat = at + 60 -> 55)
MENU_OFFS = {"NQ": [("atr", 0.25), ("atr", 0.5), ("atr", 1.0), ("pts", 10.0), ("pts", 20.0)],      # EDGE_SPEC "Variant menu"
             "ES": [("atr", 0.25), ("atr", 0.5), ("atr", 1.0), ("pts", 2.5), ("pts", 5.0)],
             "GC": [("atr", 0.25), ("atr", 0.5), ("atr", 1.0), ("pts", 2.0), ("pts", 4.0)]}
DAYS = list(RM.SMOKE_DAYS)                          # 10 fixed BUILD days: early sample, a roll day, half days, FOMC, plain
WIDE = {"stop_mode": "pts", "stop_val": 45.0, "tgt_r": 0.0}
CELLS = [{"stop_mode": "atr", "stop_val": 1.5, "tgt_r": 2.0}, {"stop_mode": "pts", "stop_val": 20.0, "tgt_r": 1.0},
         {"stop_mode": "pct", "stop_val": 0.10, "tgt_r": 0.0}]


def real_days():
    if S.compute_window_end() is not None:
        pytest.skip("inside an offline compute window")


def hms(ms, tz=S.ET):
    return dt.datetime.fromtimestamp(ms / 1000, tz).strftime("%H:%M:%S")


def ident(t):
    """What a decision fixes about a trade (the rest depends on the prints after the entry)."""
    return (t["date"], t["side"], t["entry_ms"], t["entry_price"], t["order_price"], t["sl"], t["tp"], t["oco"])


# ---- the registry = the pre-registration ----------------------------------------------------------------------------------

def test_one_straddle_entry_per_listed_time_with_the_menu_offsets_as_variants():
    assert TIMES == S.LISTED_TIMES and not [k for k in families.ERRORS if k == "timed" or k in NAMES]
    for at, name in zip(TIMES, NAMES):
        cls, inputs, both, notes = families.REGISTRY[name]
        lib = families.library(name)
        assert cls is T.StraddleT and issubclass(cls, l2ref.StraddleT) and inputs == {"at": at} and both is True
        assert families.MODULE_OF[name] == "timed" and cls.SCREEN_TFS == ("30",) and cls.FEATURES == () and cls.ATR_CARRY
        assert lib["variants"] == [{"off": k} for k in OFFS] and lib["roots"] == ("NQ", "ES", "GC") and lib["l2"] is False
        assert lib["complexity"] == 6 and lib["ported"] is None and lib["penalty"] is None
        assert lib["weak"] is (at in WEAK) and ("WEAK RATIONALE" in notes) is (at in WEAK) and ("NO event" in lib["rationale"]) is (at in WEAK)
        assert lib["rationale"].startswith("At scheduled liquidity events new orders arrive and price leaves its pre-event "
                                           "balance; a straddle rides whichever side breaks (" + at + " ET: ")
        assert lib["rationale"].endswith(".") and lib["rationale"].count(". ") == 0                          # ONE sentence
        assert T.entry_life_min(at) == LIFE[at] and ("entries live 55 min" in notes) is (LIFE[at] == 55) and "cancel unfilled after 60 min" in notes
        st = cls({**inputs, "tf": "30"})
        assert (st.p["cancel_min"], st.p["flat"], st.p["max_tr"], st.p["shift_seed"], st.p["off_mode"]) == (60, "", 1, 0, "menu")
        assert st.S["t"] == (S.clock_sec(at), S.clock_sec(FLAT[at])) and FLAT[at] in notes
        assert st.fam_times() == [at + ":00", S._hms(S.clock_sec(at) + 3600)]                              # arm, cancel 60 min later
        assert RM.is_time_fired(cls)                                                                      # -> its time-shuffle null
        for root in ("NQ", "ES", "GC"):
            g = families.unit_grid(name, root, "30")
            assert len(g) == 160 and len({c["id"] for c in g}) == 160 and g[0]["id"] == "offatr0p25_atr1p5-r0"
            assert [c["exit"] for c in g[:32]] == S.menu(root) and len(RM.cell_specs(g[0])) == 1
            assert g[127]["id"] == "offptsA_pct0p2-r3" and g[128]["spec"][1]["off"] == "ptsB" and g[5]["spec"][1]["at"] == at
            assert [tuple(T.offset_of(root, v["off"]).values()) for v in lib["variants"]] == MENU_OFFS[root]
            assert [T.offset_of(root, k) for k in OFFS] == S.menu_offsets(root)
    assert "Tokyo" in families.library("straddle_t_2000")["rationale"] and "19:00 ET in winter" in families.library("straddle_t_2000")["rationale"]
    assert "NO event" in families.library("straddle_t_0000")["rationale"] and T.WEAK_TIMES == WEAK
    assert "reopen gap" in families.REGISTRY["straddle_t_1800"][3] and "standard time" in families.REGISTRY["straddle_t_2000"][3]
    us = RM.units(only=NAMES, roots=["NQ"])
    assert [u["key"] for u in us] == sorted(n + "-NQ-tf30" for n in NAMES) and all(u["cells"] == 160 and u["null_cells"] == 320 for u in us)


def test_the_old_pilots_straddle_times_are_labelled_a_second_look_and_a_duplicate():
    """EDGE_SPEC user rule 3: 2025-26 was already seen once for the old finalists straddle-tf30 nyam / pm -> their exam is a
    SECOND look and must be labelled. 09:30 / 13:30 (and 03:00: the holdout jobs ran sess = all) are those strategies."""
    assert T.SECOND_LOOK == SEEN
    for at, name in zip(TIMES, NAMES):
        notes, rat = families.REGISTRY[name][3], families.library(name)["rationale"]
        seen = at in SEEN
        assert ("SECOND look" in notes) is seen and ("SECOND LOOK" in notes) is seen and ("SECOND LOOK at 2025-26" in rat) is seen, name
        assert ("DUPLICATE of the ported `straddle` tf 30" in notes) is seen, name
        if seen:
            assert f"straddle-tf30 {SEEN[at]}" in notes and f"straddle-tf30 {SEEN[at]}" in rat and "straddle-tf30 nyam / pm" in notes
    assert "london was in the same bundles" in families.REGISTRY["straddle_t_0300"][3]
    assert families.library("vwap_ema_x")["rationale"].count("SECOND") == 0 and "SECOND" not in families.REGISTRY["vwap_ema_x"][3]


def test_a_stored_straddle_run_resolves_to_the_offset_that_ran():
    for root in ("NQ", "ES", "GC"):
        for off, (mode, val) in zip(OFFS, MENU_OFFS[root]):
            stored = T.StraddleT({"at": "08:30", "off": off, "stop_mode": "pts", "stop_val": 5.0}).p      # what a run's meta keeps
            assert (stored["off"], stored["off_mode"]) == (off, "menu")
            r = T.resolved(root, stored)
            assert (r["off"], r["off_mode"], r["off_val"]) == ("", mode, val) and {k: v for k, v in r.items() if not k.startswith("off")} == {
                k: v for k, v in stored.items() if not k.startswith("off")}
            assert T.StraddleT(r).p["off_val"] == val and l2ref.StraddleT({k: v for k, v in r.items() if k != "off"}).p["off_mode"] == mode
    plain = {"at": "09:30", "off": "", "off_mode": "pts", "off_val": 7.0}
    assert T.resolved("NQ", plain) == plain


def test_vwap_ema_x_entry_is_the_pre_registered_grid_and_carries_the_weak_prior():
    cls, inputs, both, notes = families.REGISTRY["vwap_ema_x"]
    lib = families.library("vwap_ema_x")
    assert cls is T.VwapEmaX and inputs == {} and both is False and "WEAK PRIOR" in notes and "vwap_flip" in notes
    assert cls.SCREEN_TFS == ("1", "5", "15") and cls.FEATURES == () and cls.session_independent is True
    assert lib["variants"] == [{"n": n, "anchor": a} for n in (9, 21, 50) for a in ("session", "rth")]
    assert lib["weak"] is True and lib["complexity"] == 3 and lib["roots"] == ("NQ", "ES", "GC") and lib["l2"] is False
    assert lib["rationale"] == ("When the fast average crosses the day's fair price, control of the day has changed sides and the "
                                "wrong side must exit.")
    assert cls({"tf": "5"}).p["max_tr"] == 3 and not RM.is_time_fired(cls)
    for must in ("SAME strategy in eve / asia / london / pre / nyam", "restarted at 11:00 / 13:30", "no EMA warm-up", "thin in pre / nyam / mid"):
        assert must in notes                                    # what any card of this family must state
    for bad in ({"n": 20}, {"n": "9"}, {"anchor": "0930"}, {"tf": "5", "max_tr": 0}):
        with pytest.raises(ValueError):
            cls(bad)
    for tf in ("1", "5", "15"):
        g = families.unit_grid("vwap_ema_x", "GC", tf)
        assert len(g) == 192 and len({c["id"] for c in g}) == 192 and g[0]["id"] == "anchorsession_n9_atr1p5-r0"
        assert [p["sess"] for _, p in RM.cell_specs(g[0], "session")] == ["all", "pre", "eve"]       # old rule: the tester's five + pre + eve
        assert [(p["sess"], p["hold_to"]) for _, p in RM.cell_specs(g[0])] == [(s, "day") for s in RM.DAY_PASSES]     # flat by 4pm: 7 instances
    with pytest.raises(ValueError, match="SCREEN_TFS"):
        families.unit_grid("vwap_ema_x", "NQ", "30")


def test_straddle_offset_is_either_a_menu_name_or_the_engines_own_inputs():
    for bad in ({"off": ""}, {"off": "ptsA", "off_mode": "pts"}, {"off": "atr0p5", "off_mode": "atr", "off_val": 0.5}, {"off": "pts10"}):
        with pytest.raises(ValueError):
            T.StraddleT({"at": "09:30", **bad})
    st = T.StraddleT({"at": "09:30", "off": "", "off_mode": "pts", "off_val": 7.0})
    assert st.p["off_val"] == 7.0 and T.OFFS == OFFS


# ---- A. straddle_t on synthetic tapes -----------------------------------------------------------------------------------------

def synth(moves=(), root="NQ", base=15000.0, start="07:00", end="11:10", quiet="09:30", d=D, contract="NQM3"):
    """A print every 10 s, size 1. Before `quiet` the price cycles base, base + 8, base + 4: every 30-minute bar has high
    base + 8, low base and closes at base + 4, so every true range is 8 and ATR30 = 8.0; the last print before `quiet` is
    base + 4. From `quiet` on the price rests at base + 4; a move (hms, price) sets every print from that time on to price."""
    ts = np.arange(S.et_ns(d, start), S.et_ns(d, end), 10 * S.NS, dtype=np.int64)
    px = base + np.array([0.0, 8.0, 4.0])[np.arange(len(ts)) % 3]
    px[ts >= S.et_ns(d, quiet)] = base + 4.0
    for at, p in moves:
        px[ts >= S.et_ns(d, at)] = p
    return S.Tape(root, d, contract, ts, px, np.ones(len(ts), np.int64))


def play(params, tape, at="09:30", **kw):
    return S.run_session(T.StraddleT({"at": at, **params}), tape, daily=kw.pop("daily", []), on_error="raise", **kw)


def test_the_tape_builder_gives_atr30_8_and_last_price_base_plus_4():
    seen = {}

    class Peek(T.StraddleT):
        def fam_time(self, ctx, sec):
            if sec == self.S["t"][0]:
                seen.update(atr=self.atr, nb=self.nb, lp=ctx.last_price, mode=self.p["off_mode"], val=self.p["off_val"])
            super().fam_time(ctx, sec)
    S.run_session(Peek({"at": "09:30", "off": "ptsB"}), synth(), daily=[], on_error="raise")
    assert seen == {"atr": 8.0, "nb": 5, "lp": 15004.0, "mode": "pts", "val": 20.0}


def test_straddle_rests_an_oco_pair_at_the_time_and_the_first_fill_cancels_the_other_leg():
    # ptsA on NQ = 10 points around the last price 15004: long stop 15014, short stop 14994
    r = play({"off": "ptsA", **WIDE}, synth([("09:40:00", 15014.25), ("09:45:00", 14990.0)]))
    assert len(r.trades) == 1 and r.both_sides is True           # 09:45 trades THROUGH the short level: that leg is gone
    t = r.trades[0]
    assert (t["side"], t["order_price"], t["entry_price"], hms(t["entry_ms"])) == ("long", 15014.0, 15014.5, "09:40:00")
    assert t["oco"] is True and t["both_sides"] is True and (t["sl"], t["tp"]) == (15014.5 - 45.0, None)
    assert (t["exit_reason"], hms(t["exit_ms"]), t["exit_price"]) == ("time", "11:00:00", 14989.75)       # flat at the session end
    r = play({"off": "ptsA", **WIDE}, synth([("09:40:00", 14993.75), ("09:45:00", 15030.0)]))            # the mirror image
    assert len(r.trades) == 1 and ident(r.trades[0])[1:5] == ("short", r.trades[0]["entry_ms"], 14993.5, 14994.0)
    assert hms(r.trades[0]["entry_ms"]) == "09:40:00" and r.trades[0]["oco"] is True


def test_one_trade_per_time_per_day_no_re_entry_after_a_stop_out():
    moves = [("09:40:00", 15014.25), ("09:45:00", 14990.0), ("09:50:00", 15040.0), ("09:55:00", 14960.0), ("10:05:00", 15040.0)]
    r = play({"off": "ptsA", "stop_mode": "pts", "stop_val": 10.0, "tgt_r": 0.0}, synth(moves))
    assert len(r.trades) == 1
    t = r.trades[0]
    assert (t["side"], t["exit_reason"], hms(t["exit_ms"]), t["sl"], t["exit_price"]) == ("long", "sl", "09:45:00", 15004.5, 14989.75)
    assert T.StraddleT({"at": "09:30"}).p["max_tr"] == 1


def test_unfilled_entries_are_cancelled_sixty_minutes_after_the_time():
    a = play({"off": "ptsA", **WIDE}, synth([("10:29:50", 15030.0)])).trades          # the last print the orders can see
    b = play({"off": "ptsA", **WIDE}, synth([("10:30:00", 15030.0)])).trades          # the cancel runs before this print
    c = play({"off": "ptsA", **WIDE}, synth()).trades                                   # never reaches a level
    assert len(a) == 1 and hms(a[0]["entry_ms"]) == "10:29:50" and b == [] and c == []
    keep = play({"off": "ptsA", "cancel_min": 0, **WIDE}, synth([("10:30:00", 15030.0)])).trades          # the option that is NOT used
    assert len(keep) == 1 and hms(keep[0]["entry_ms"]) == "10:30:00"


def flat_tape(at, move_min, move_s=0, d=D):
    """15000 on a 10 s grid from 90 minutes before `at` (not before 18:00 / 23:00) to 10 minutes after its flat time; from
    `at` + move_min:move_s on every print is 15030 (through the long level of ptsA = 15010)."""
    a, b = S.clock_sec(at), S.clock_sec(S.clock_flat(at))
    mid = S.et_ns(d, "00:00")
    ts = np.arange(mid + max(a - 5400, -21600 if a < 0 else -3600) * S.NS, mid + (b + 600) * S.NS, 10 * S.NS, dtype=np.int64)
    px = np.full(len(ts), 15000.0)
    px[ts >= mid + (a + move_min * 60 + move_s) * S.NS] = 15030.0
    return S.Tape("NQ", d, "NQM3", ts, px, np.ones(len(ts), np.int64))


@pytest.mark.parametrize("at", TIMES)
def test_how_long_an_unfilled_entry_rests_at_every_time(at):
    """EDGE_SPEC: 'cancel unfilled after 60 min'. At 02:00 and 08:30 the flat time is at + 60 min and the Template cancels
    entries 5 minutes before the flat time: there an unfilled entry rests 55 minutes (documented in families/timed.py)."""
    life = LIFE[at]
    daily = [{"date": "2023-03-13", "o": 14900.0, "h": 15050.0, "l": 14880.0, "c": 15000.0, "contract": "NQM3"}]

    def run(move_min, move_s):
        st = T.StraddleT({"at": at, "off": "ptsA", **WIDE})
        kw = {"window": st.eve_window, "segment": "eve"} if S.clock_sec(at) < 0 else {}
        return S.run_session(st, flat_tape(at, move_min, move_s), daily=daily, carry=12.0, on_error="raise", **kw).trades
    last = run(life - 1, 50)                                     # the last print the resting orders can see
    assert len(last) == 1 and last[0]["side"] == "long" and last[0]["order_price"] == 15010.0
    assert last[0]["entry_ms"] == (S.et_ns(D, "00:00") + (S.clock_sec(at) + life * 60 - 10) * S.NS) // 10**6
    for m, s in ((life, 0), (life + 2, 0), (59, 50), (60, 0), (64, 50)):
        if (m, s) >= (life, 0):
            assert run(m, s) == [], (at, m, s)                   # cancelled: no later print fills
    st = T.StraddleT({"at": at})
    want = {at + ":00", S._hms(S.clock_sec(at) + life * 60), S._hms(S.clock_sec(S.clock_flat(at)) - 300), S.clock_flat(at)}
    assert set(st.times()) == want and len(st.times()) == (3 if life == 55 else 4)


def test_the_time_shuffle_null_shifts_one_sided_where_the_window_would_leave_its_segment():
    """For reading 'beats the null': 18:00 and 00:00 draw 0 .. +90 minutes, 20:00 and 13:30 draw -90 .. 0, the rest +/- 90."""
    want = {"18:00": (0, 90), "00:00": (0, 90), "20:00": (-90, 0), "13:30": (-90, 0)}
    for at in TIMES:
        ks = T.StraddleT({"at": at, "shift_seed": 1}).shifts()
        lo, hi = want.get(at, (-90, 90))
        assert ks == list(range(lo, hi + 1)), at
    assert 60 in T.StraddleT({"at": "08:30", "shift_seed": 1}).shifts()          # the 08:30 null can sit on the 09:30 open


@pytest.mark.parametrize("root,base,dist", [("NQ", 15000.0, (2.0, 4.0, 8.0, 10.0, 20.0)), ("ES", 4000.0, (2.0, 4.0, 8.0, 2.5, 5.0)),
                                            ("GC", 1900.0, (2.0, 4.0, 8.0, 2.0, 4.0))])
def test_the_five_menu_offsets_per_root(root, base, dist):
    """ATR30 = 8 on the synthetic tape: atr0p25 / atr0p5 / atr1 = 2 / 4 / 8 points; ptsA / ptsB = the root's fixed sizes."""
    lp = base + 4.0
    for off, d in zip(OFFS, dist):
        up = play({"off": off, **WIDE}, synth([("09:35:00", base + 100.0)], root=root, base=base)).trades
        dn = play({"off": off, **WIDE}, synth([("09:35:00", base - 100.0)], root=root, base=base)).trades
        assert len(up) == len(dn) == 1 and (up[0]["side"], dn[0]["side"]) == ("long", "short")
        assert up[0]["order_price"] == pytest.approx(lp + d, abs=1e-9) and dn[0]["order_price"] == pytest.approx(lp - d, abs=1e-9)
        # the named offset IS the engine's own input pair
        mode, val = MENU_OFFS[root][OFFS.index(off)]
        ref = S.run_session(l2ref.StraddleT({"at": "09:30", "off_mode": mode, "off_val": val, **WIDE}),
                            synth([("09:35:00", base + 100.0)], root=root, base=base), daily=[], on_error="raise").trades
        assert ref == up
        assert play(T.resolved(root, {"off": off, **WIDE}), synth([("09:35:00", base + 100.0)], root=root, base=base)).trades == up


def test_the_1800_fire_brackets_the_prior_close_with_the_carried_atr_and_is_flat_at_2000():
    tape = synth([("18:30:00", 15010.0)], start="18:00", end="20:10", quiet="18:00", d=D - dt.timedelta(days=1))
    tape = S.Tape("NQ", D, "NQM3", tape.ts, tape.px, tape.size)                       # the evening BEFORE trade date D
    daily = [{"date": "2023-03-13", "o": 14900.0, "h": 15050.0, "l": 14880.0, "c": 14990.0, "contract": "NQM3"}]
    st = T.StraddleT({"at": "18:00", "off": "atr0p5", **WIDE})
    assert st.eve_window == S.EVE_WINDOW and st.session_window is None
    r = S.run_session(st, tape, daily=daily, window=st.eve_window, segment="eve", carry=12.0, on_error="raise")
    assert len(r.trades) == 1                                    # anchor 14990 (prior close), ATR 12 (carry): 14996 / 14984
    t = r.trades[0]
    assert (t["side"], t["order_price"], t["date"]) == ("long", 14996.0, "2023-03-14")
    assert hms(t["entry_ms"]) == "18:00:10" and t["entry_price"] == 15004.25         # the reopen is already through the level
    assert (t["exit_reason"], hms(t["exit_ms"])) == ("time", "20:00:00") and S.session_of(t["entry_ms"]) == "eve"
    roll = [{**daily[0], "contract": "NQH3"}]                    # the prior close is another contract: no anchor, no trade
    assert S.run_session(T.StraddleT({"at": "18:00", "off": "atr0p5", **WIDE}), tape, daily=roll, window=st.eve_window,
                         segment="eve", carry=12.0, on_error="raise").trades == []


def test_the_0000_fire_brackets_the_last_evening_print_and_is_flat_at_0200():
    ts = np.arange(S.et_ns(D - dt.timedelta(days=1), "23:00"), S.et_ns(D, "02:10"), 10 * S.NS, dtype=np.int64)
    px = np.full(len(ts), 15000.0)
    px[ts == S.et_ns(D - dt.timedelta(days=1), "23:59:50")] = 15002.0                 # the last print of the evening
    px[ts >= S.et_ns(D, "00:20")] = 14980.0
    tape = S.Tape("NQ", D, "NQM3", ts, px, np.ones(len(ts), np.int64))
    r = S.run_session(T.StraddleT({"at": "00:00", "off": "atr0p5", **WIDE}), tape, daily=[], carry=12.0, on_error="raise")
    assert len(r.trades) == 1                                    # anchor 15002, ATR 12 (the evening just ended): 15008 / 14996
    t = r.trades[0]
    assert (t["side"], t["order_price"], hms(t["entry_ms"]), t["entry_price"]) == ("short", 14996.0, "00:20:00", 14979.75)
    assert (t["exit_reason"], hms(t["exit_ms"])) == ("time", "02:00:00") and S.session_of(t["entry_ms"]) == "asia"


# ---- B. vwap_ema_x on synthetic tapes -----------------------------------------------------------------------------------------

def steps(moves, start="09:00", end="11:10", d=D):
    """A print every 10 s, size 1: from each (hms, price) on, every print is `price`."""
    ts = np.arange(S.et_ns(d, start), S.et_ns(d, end), 10 * S.NS, dtype=np.int64)
    px = np.zeros(len(ts))
    for at, p in moves:
        px[ts >= S.et_ns(d, at)] = p
    return S.Tape("NQ", d, "NQM3", ts, px, np.ones(len(ts), np.int64))


def wave(start="09:00", end="13:40", d=D):
    """Two superposed sines (periods 37 and ~13.7 minutes, +/- 30 and 9 points) on the 10 s grid, uneven sizes."""
    ts = np.arange(S.et_ns(d, start), S.et_ns(d, end), 10 * S.NS, dtype=np.int64)
    x = (ts - ts[0]) / (37 * 60 * S.NS) * 2 * np.pi
    px = np.round((15000.0 + 30.0 * np.sin(x) + 9.0 * np.sin(2.7 * x)) / 0.25) * 0.25
    return S.Tape("NQ", d, "NQM3", ts, px, 1 + (np.arange(len(ts)) % 5))


def crosses(tape, tf, n, sess, anchor="session"):
    """INDEPENDENT re-derivation from the raw prints (no Template code): every cross of EMA(n) of the tf closes over the VWAP
    at a tf close inside session `sess` -> [{'dec': decision ns, 'side': +1 | -1, 'ok': an entry is allowed there}]."""
    d = tape.date
    mid = S.et_ns(d, "00:00")
    if sess == "eve":
        w0, w1 = S.segment_ns(d, S.EVE_WINDOW, "eve")
    else:
        w = S.effective_session_window(d, ("00:00", "16:10"), tape.root)
        w0, w1 = S.et_ns(d, w[0]), S.et_ns(d, w[1])
    lo, hi = (int(v) for v in np.searchsorted(tape.ts, [w0, w1]))
    ts, px, sz = tape.ts[lo:hi], tape.px[lo:hi], tape.size[lo:hi]
    m = (ts - mid) // S.MIN_NS                                   # the minute of every print, relative to 00:00 ET of the trade date
    first = np.flatnonzero(np.r_[True, m[1:] != m[:-1]])
    last = np.r_[first[1:], len(m)] - 1
    mm = m[first]                                                # 1-minute bars: only minutes that have a print
    cl, vol = px[last], np.add.reduceat(sz, first).astype(float)
    typ = (np.maximum.reduceat(px, first) + np.minimum.reduceat(px, first) + cl) / 3.0
    s0, s1 = S.SESS[sess]
    a0 = S.SESS["nyam"][0] if anchor == "rth" and sess in ("nyam", "mid", "pm") else s0       # the VWAP anchor, seconds
    bucket = mm // tf
    out, ema, side_p, nb = [], None, 0, 0
    for k in np.unique(bucket).tolist():
        j = int(np.flatnonzero(bucket == k)[-1])                 # the last 1-minute bar of the tf bar
        c = float(cl[j])
        ema = c if ema is None else ema + 2.0 / (n + 1) * (c - ema)
        nb += 1
        end_min = (k + 1) * tf
        if int(mm[j]) == end_min - 1:
            dec = mid + end_min * S.MIN_NS                       # closed on time
        elif j + 1 < len(mm):
            dec = mid + (int(mm[j + 1]) + 1) * S.MIN_NS          # its last minute had no print: closed when the next bar ends
        else:
            continue
        if not s0 < end_min * 60 <= s1 or dec > mid + s1 * S.NS or dec >= w1:
            continue                                             # not a tf close inside the session
        sel = (mm * 60 >= a0) & (mm <= mm[j])
        v = float(vol[sel].sum())
        if v <= 0:
            continue
        vwap = float((vol[sel] * typ[sel]).sum()) / v
        sd = (ema > vwap) - (ema < vwap)
        if not sd:
            continue
        if side_p and sd != side_p:
            out.append({"dec": int(dec), "side": sd, "ok": nb >= 3 and dec - mid < (s1 - 300) * S.NS})
        side_p = sd
    return out


def fill_ms(tape, dec):
    """The print a market order sent at `dec` fills on: the first one at / after dec + the 85 ms placement latency."""
    i = int(np.searchsorted(tape.ts, dec + T.VwapEmaX.placement_ms * 1_000_000))
    return int(tape.ts[i]) // 1_000_000 if i < len(tape.ts) else None


def test_vwap_ema_x_enters_with_the_cross_at_the_tf_close_hand_computed():
    """tf 1, EMA(9) (alpha 0.2), session VWAP from 09:30. 15000 until 09:40 (EMA = VWAP: no side), ten bars at 14990 (EMA below the
    VWAP from the first of them: side -1, no trade), then 15010 from 09:50 with E0 = 14990 + 10 x 0.8^10 = 14991.0737:
      close 09:51  EMA 15010 - 18.9263 x 0.8  = 14994.859   VWAP (10 x 15000 + 10 x 14990 + 15010) / 21 = 14995.714   below
      close 09:52  EMA 15010 - 18.9263 x 0.64 = 14997.887   VWAP (299900 + 2 x 15010) / 22           = 14996.364   ABOVE -> long"""
    tape = steps([("09:00:00", 15000.0), ("09:40:00", 14990.0), ("09:50:00", 15010.0)])
    base = {"tf": "1", "sess": "nyam", "stop_mode": "pts", "stop_val": 200.0, "tgt_r": 0.0}
    r = S.run_session(T.VwapEmaX({**base, "n": 9}), tape, daily=[], on_error="raise")
    assert len(r.trades) == 1 and r.both_sides is False
    t = r.trades[0]
    assert (t["side"], hms(t["entry_ms"]), t["entry_price"], t["order_price"], t["oco"]) == ("long", "09:52:10", 15010.25, None, False)
    assert (t["exit_reason"], hms(t["exit_ms"])) == ("time", "11:00:00")
    x = crosses(tape, 1, 9, "nyam")
    assert [(hms(c["dec"] // 10**6), c["side"], c["ok"]) for c in x] == [("09:52:00", 1, True)]
    # the first tf close of a session only sets the side: a tape that starts the session already below the VWAP never "crosses"
    assert S.run_session(T.VwapEmaX({**base, "n": 9}), steps([("09:00:00", 15000.0), ("09:40:00", 14990.0)]), daily=[],
                         on_error="raise").trades == []
    # the slower averages on the same tape: the first allowed cross of the independent list is the one trade (held to 11:00)
    for n in (21, 50):
        ok = [c for c in crosses(tape, 1, n, "nyam") if c["ok"]]
        got = S.run_session(T.VwapEmaX({**base, "n": n}), tape, daily=[], on_error="raise").trades
        assert [(t["entry_ms"], t["side"]) for t in got] == [(fill_ms(tape, c["dec"]), "long" if c["side"] > 0 else "short") for c in ok[:1]]


def test_an_opposite_cross_neither_closes_nor_reverses_an_open_trade():
    tape = steps([("09:00:00", 15000.0), ("09:40:00", 14990.0), ("09:50:00", 15010.0), ("10:10:00", 14960.0)])
    x = crosses(tape, 1, 9, "nyam")
    assert [c["side"] for c in x] == [1, -1]                     # up at 09:52, down again after 10:10
    r = S.run_session(T.VwapEmaX({"tf": "1", "sess": "nyam", "n": 9, "stop_mode": "pts", "stop_val": 200.0, "tgt_r": 0.0}), tape,
                      daily=[], on_error="raise").trades
    assert len(r) == 1 and (r[0]["side"], r[0]["exit_reason"], hms(r[0]["exit_ms"])) == ("long", "time", "11:00:00")


def taken(xs, tf, max_tr):
    """The crosses a flat-after-one-bar instance (exit_bars 1) trades: allowed, not the close right after an entry (that close
    exits the trade and does not signal), at most max_tr per session."""
    out = []
    for c in xs:
        if c["ok"] and len(out) < max_tr and (not out or c["dec"] > out[-1]["dec"] + tf * S.MIN_NS):
            out.append(c)
    return out


@pytest.mark.parametrize("tf,n", [(1, 9), (1, 21), (5, 9), (5, 21), (15, 9), (1, 50)])
def test_every_cross_of_a_wave_is_traded_at_its_close_and_nothing_else(tf, n):
    tape = wave()
    for sess, anchor in (("nyam", "session"), ("mid", "session"), ("mid", "rth"), ("nyam", "rth")):
        p = {"tf": str(tf), "sess": sess, "n": n, "anchor": anchor, "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0,
             "exit_bars": 1, "max_tr": 20}
        r = S.run_session(T.VwapEmaX(p), tape, daily=[], on_error="raise")
        want = taken(crosses(tape, tf, n, sess, anchor), tf, 20)
        assert [(t["entry_ms"], t["side"]) for t in r.trades] == [(fill_ms(tape, c["dec"]), "long" if c["side"] > 0 else "short")
                                                                  for c in want]
        assert all(t["order_price"] is None and not t["oco"] for t in r.trades) and r.both_sides is False
        if tf == 1:
            assert len(want) >= 3                                # the wave really crosses
        three = S.run_session(T.VwapEmaX({**p, "max_tr": 3}), tape, daily=[], on_error="raise").trades
        assert three == r.trades[:3]                             # max_tr 3: the first three crosses of the session


def test_the_rth_anchor_differs_from_the_session_anchor_only_after_the_morning():
    tape = wave()
    p = {"tf": "1", "n": 9, "stop_mode": "pts", "stop_val": 500.0, "tgt_r": 0.0, "exit_bars": 1, "max_tr": 20}
    run = lambda sess, anchor: S.run_session(T.VwapEmaX({**p, "sess": sess, "anchor": anchor}), tape, daily=[], on_error="raise").trades  # noqa: E731
    assert run("nyam", "session") == run("nyam", "rth") and len(run("nyam", "rth")) >= 3      # 09:30 is the session start
    assert run("mid", "session") != run("mid", "rth")                                           # 11:00 vs 09:30
    assert [c["dec"] for c in crosses(tape, 1, 9, "mid")] != [c["dec"] for c in crosses(tape, 1, 9, "mid", "rth")]


# ---- real BUILD days: identity with the engine's reference, the independent cross list, worker parity -------------------------

def test_straddle_t_is_the_engines_clock_straddle_with_the_roots_menu_offset():
    real_days()
    for root in ("NQ", "ES", "GC"):
        days = [d for d in DAYS if root == "NQ" or S.hb_tape_path(d, root) is not None]
        if len(days) < 5:
            pytest.skip(f"{root}: tapes of the smoke days are not cached")
        mine, ref = [], []
        for name, at in zip(NAMES, TIMES):
            for c in families.unit_grid(name, root, "30")[1::37]:            # 5 cells per time: every offset, mixed exits
                mine.append(c["spec"])
                mode, val = MENU_OFFS[root][OFFS.index(c["variant"]["off"])]
                ref.append((l2ref.StraddleT, {"at": at, "off_mode": mode, "off_val": val, **c["exit"]}))
        res = S.run_many(mine + ref, days=days, root=root, workers=1)
        a, b = res[:len(mine)], res[len(mine):]
        assert len(mine) == 45 and {s[1]["off"] for s in mine} == set(OFFS)
        for (cls, p), x, y in zip(mine, a, b):
            at = p["at"]
            assert x["trades"] == y["trades"] and x["skipped"] == y["skipped"] and x["skipped_by_error"] == 0
            assert x["meta"]["segments"] == (["eve"] if at in ("18:00", "20:00") else ["day"]) and x["meta"]["root"] == root
            per_day = {}
            for t in x["trades"]:
                d = dt.date.fromisoformat(t["date"])
                base = d - dt.timedelta(days=1) if at in ("18:00", "20:00") else d
                fire, flat = S.et_ns(base, at) // 10**6, S.et_ns(base, FLAT[at]) // 10**6
                assert fire <= t["entry_ms"] < fire + 3600_000 and t["exit_ms"] < flat + 60_000        # armed 60 min, flat by `flat`
                assert t["oco"] is True and t["both_sides"] is True and t["order_price"] is not None
                half = root != "GC" and d in S.EARLY_CLOSES                    # equity half day: the window ends at 13:15 ET
                if t["exit_reason"] == "eod":                                  # only the 11:05 trade (flat 13:30) can meet that close
                    assert half and at == "11:05" and "13:14:00" <= hms(t["exit_ms"]) < "13:15:00"
                else:
                    assert t["exit_reason"] in ("sl", "tp", "time") and (t["exit_reason"] != "time" or t["exit_ms"] >= flat)
                assert S.session_of(t["entry_ms"]) == S.clock_session(at)
                per_day[t["date"]] = per_day.get(t["date"], 0) + 1
            assert set(per_day.values()) <= {1}                              # one trade per time per day
        assert sum(len(x["trades"]) for x in a) > 100                        # the grid really trades
        if root == "NQ":                                                     # no 18:00 trade on the roll day, none at 13:30 on half days
            by = {p["at"]: {t["date"] for x, (_, p2) in zip(a, mine) if p2["at"] == p["at"] for t in x["trades"]} for _, p in mine}
            assert "2022-06-13" in S.default_rolls("NQ") and "2022-06-13" not in by["18:00"] and "2022-06-13" in by["09:30"]
            assert not by["13:30"] & {"2022-11-25", "2023-07-03"} and {"2022-11-25", "2023-07-03"} & by["09:30"]


def test_the_0300_0930_1330_entries_are_the_ported_straddle_within_sixty_minutes():
    """The SECOND LOOK / DUPLICATE label is a fact about trades: with an ATR offset the 03:00 / 09:30 / 13:30 entries are the
    ported `straddle` (the old pilot's family) at tf 30 in london / nyam / pm, minus its entries later than 60 minutes."""
    real_days()
    if "straddle" not in families.REGISTRY:
        pytest.skip("the ported straddle (families/port1.py) is not registered")
    old = families.REGISTRY["straddle"][0]
    assert old({"tf": "30"}).p["delay_min"] == 0 and not old({"tf": "30"}).p["news_only"]
    n = 0
    for root in ("NQ", "ES"):
        days = [d for d in DAYS if root == "NQ" or S.hb_tape_path(d, root) is not None]
        if len(days) < 5:
            continue
        x = S.menu(root)[2 if root == "NQ" else 9]
        pairs = [(at, sess, off, val) for at, sess in SEEN.items() for off, val in zip(OFFS[:3], (0.25, 0.5, 1.0))]
        specs = [sp for at, sess, off, val in pairs for sp in ((T.StraddleT, {"at": at, "off": off, **x}),
                                                                (old, {"tf": "30", "sess": sess, "off_atr": val, **x}))]
        res = S.run_many(specs, days=days, root=root, workers=1)
        for k, (at, sess, off, val) in enumerate(pairs):
            new, was = res[2 * k]["trades"], res[2 * k + 1]["trades"]
            early = [t for t in was if t["entry_ms"] < S.et_ns(dt.date.fromisoformat(t["date"]), at) // 10**6 + 3600_000]
            assert new == early and len(new) >= 5, (root, at, off)      # every field of every trade
            assert all(S.session_of(t["entry_ms"]) == sess for t in was)
            n += len(new)
    assert n > 150


def test_a_day_with_an_empty_clock_hour_loses_all_its_day_fires_but_keeps_the_evening():
    """The engine's coverage rule (the tester's): GC closes 13:45 ET on the day after Thanksgiving -> every 00:00 .. 13:30
    fire of that trade date is skipped (also those before the hole); its 18:00 / 20:00 fires still run."""
    real_days()
    if S.hb_tape_path("2023-11-24", "GC") is None or S.hb_tape_path("2023-11-27", "GC") is None:
        pytest.skip("GC tapes of 2023-11-24 / 27 are not cached")
    days = ["2023-11-24", "2023-11-27"]
    specs = [(T.StraddleT, {"at": at, "off": "ptsA", "stop_mode": "pts", "stop_val": 7.0, "tgt_r": 0.0}) for at in TIMES]
    for (_, p), r in zip(specs, S.run_many(specs, days=days, root="GC", workers=1)):
        eve = p["at"] in ("18:00", "20:00")
        assert r["skipped_by_error"] == 0 and r["sessions"] == 2 and r["used"] == (2 if eve else 1), p["at"]
        assert [s["date"] for s in r["skipped"]] == ([] if eve else ["2023-11-24"])
        assert eve or ("missing" in r["skipped"][0]["reason"] and not [t for t in r["trades"] if t["date"] == "2023-11-24"])


def test_fixed_point_offsets_bracket_the_last_print_on_real_tapes():
    real_days()
    for root, a_pts in (("NQ", 10.0), ("ES", 2.5), ("GC", 2.0)):
        days = [d for d in DAYS if root == "NQ" or S.hb_tape_path(d, root) is not None][:4]
        if not days:
            pytest.skip(f"{root}: tapes of the smoke days are not cached")
        r = S.run(T.StraddleT, {"at": "09:30", "off": "ptsA", **S.menu(root)[9]}, days=days, root=root, workers=1)
        assert r["skipped_by_error"] == 0 and len(r["trades"]) >= 2 and r["meta"]["inputs"]["off"] == "ptsA"
        for t in r["trades"]:
            d = dt.date.fromisoformat(t["date"])
            tape = S.load_tape(d, root)
            lp = float(tape.px[int(np.searchsorted(tape.ts, S.et_ns(d, "09:30"))) - 1])               # the last print before 09:30:00
            assert t["order_price"] - lp == pytest.approx(a_pts if t["side"] == "long" else -a_pts, abs=1e-9)


@pytest.mark.parametrize("tf,n,anchor", [(1, 9, "session"), (5, 21, "rth"), (15, 50, "session"), (5, 9, "session")])
def test_every_vwap_ema_x_trade_is_an_independently_derived_cross_on_real_days(tf, n, anchor):
    real_days()
    days = ["2022-03-15", "2022-11-25", "2023-03-13", "2023-08-09"]          # plain, half day, roll Monday (Sunday evening), plain
    x = S.menu("NQ")[5]                                                      # atr 3.0, target 1:1
    res = S.run_many([(T.VwapEmaX, {"tf": str(tf), "n": n, "anchor": anchor, "sess": s, **x}) for s in RM.SESS_PASSES + ("pm",)], days=days,
                     workers=1)
    assert all(r["skipped_by_error"] == 0 and r["both_sides_sessions"] == 0 for r in res)
    # every session is traded on its own: a pm-only run is the pm part of the sess=all run
    assert res[3]["trades"] == [t for t in res[0]["trades"] if S.session_of(t["entry_ms"]) == "pm"]
    assert tf != 1 or len(res[3]["trades"]) >= 4                 # (a slow average seldom crosses a 09:30 VWAP in the afternoon)
    res = res[:3]
    trades = [t for r in res for t in r["trades"]]
    n_first = 0
    for iso in days:
        tape = S.load_tape(iso)
        for sess in S.ORDER7:
            mine = sorted((t for t in trades if t["date"] == iso and S.session_of(t["entry_ms"]) == sess), key=lambda t: t["entry_ms"])
            xs = crosses(tape, tf, n, sess, anchor)
            want = {(fill_ms(tape, c["dec"]), "long" if c["side"] > 0 else "short") for c in xs if c["ok"]}
            assert len(mine) <= 3 and {(t["entry_ms"], t["side"]) for t in mine} <= want, (iso, sess)
            assert all(t["order_price"] is None and not t["oco"] and not t["both_sides"] for t in mine)
            ok = [c for c in xs if c["ok"]]
            if ok:                                               # flat, no entry yet: the session's FIRST allowed cross is always traded
                assert mine and mine[0]["entry_ms"] == fill_ms(tape, ok[0]["dec"]), (iso, sess)
                n_first += 1
            else:
                assert mine == []
    assert n_first >= (12 if tf < 15 else 5) and len(trades) >= n_first
    five = [t for t in res[0]["trades"]]
    assert {S.session_of(t["entry_ms"]) for t in five} <= set(S.ORDER)       # the sess=all instance: the tester's five only
    assert {S.session_of(t["entry_ms"]) for t in res[1]["trades"]} <= {"pre"} and {S.session_of(t["entry_ms"]) for t in res[2]["trades"]} <= {"eve"}


def parity_specs():
    specs = []
    for name in NAMES:
        g = families.unit_grid(name, "NQ", "30")
        specs += [c["spec"] for c in g[3::41]]                               # 4 cells per time, every stop mode
        specs += [c["spec"] for c in RM.shift_grid(g[3::41])[::3]]           # ... and the time-shuffle null, both seeds
    for tf in T.VwapEmaX.SCREEN_TFS:
        for c in families.unit_grid("vwap_ema_x", "NQ", tf)[7::43]:
            specs += RM.cell_specs(c)                                        # the seven session instances (hold_to day)
    return specs


def test_identical_trades_at_1_and_8_workers():
    real_days()
    specs = parity_specs()
    a = S.run_many(specs, days=DAYS, workers=1)
    b = S.run_many(specs, days=DAYS, workers=W)
    assert len(specs) > 80 and a[0]["meta"]["workers"] == 1 and b[0]["meta"]["workers"] == min(W, len(DAYS))
    for (cls, p), x, y in zip(specs, a, b):
        assert x["trades"] == y["trades"], (cls.__name__, p)                 # every field of every trade, in order
        assert x["skipped_by_error"] == y["skipped_by_error"] == 0 and x["skipped"] == y["skipped"] and x["no_trade"] == y["no_trade"]
        assert x["both_sides_sessions"] == y["both_sides_sessions"] and x["sessions"] == y["sessions"] == len(DAYS)
        if cls is T.VwapEmaX:
            assert x["both_sides_sessions"] == 0 and not any(t["oco"] or t["both_sides"] for t in x["trades"])
    assert sum(len(x["trades"]) for (c, p), x in zip(specs, a) if c is T.StraddleT and not p.get("shift_seed")) > 50
    assert sum(len(x["trades"]) for (c, p), x in zip(specs, a) if c is T.StraddleT and p.get("shift_seed")) > 50
    assert sum(len(x["trades"]) for (c, p), x in zip(specs, a) if c is T.VwapEmaX) > 200
    # the null fires somewhere else than the listed time, and the same minutes for every cell of a seed
    st = T.StraddleT({"at": "09:30", "shift_seed": 1})
    assert len({st.shift_of(d) for d in DAYS}) > 5 and [st.shift_of(d) for d in DAYS] == [
        T.StraddleT({"at": "09:30", "shift_seed": 1, "off": "ptsB", "stop_val": 3.0}).shift_of(d) for d in DAYS]


# ---- no look-ahead: garbage after a cut changes nothing before it ---------------------------------------------------------------

class SpyT(T.StraddleT):
    """Records every bracket decision: when, around what, with which ATR, and the orders it placed."""
    log: list = []

    def _arm(self, ctx, legs, **kw):
        out = super()._arm(ctx, legs, **kw)
        SpyT.log.append((ctx.date.isoformat(), self.p["at"], self.p["off"], ctx.now_ns, kw.get("lp"), self.atr,
                         tuple((s, p) for s, p, _, _ in legs), tuple((o.price, o.sl, o.tp) for o in out)))
        return out


class SpyX(T.VwapEmaX):
    """Records what every tf close inside a session decided: the EMA, both VWAPs, the side and the signal."""
    log: list = []

    def fam_update(self, ctx):
        super().fam_update(ctx)
        if self.sid is not None:
            SpyX.log.append((ctx.date.isoformat(), self.p["tf"], self.p["sess"], self.p["n"], self.p["anchor"], ctx.now_ns, self.sid,
                             self.sn, self.E[self.p["n"]], self.vw(), self.vwr(), self.side_p, self.go))


class LeakT(SpyT):
    """BROKEN ON PURPOSE (the check must catch it): brackets a print 5 minutes AFTER the decision."""

    def fam_time(self, ctx, sec):
        if self.sid == "t" and sec == self.S["t"][0]:
            s = ctx._s
            p = float(s.px[min(int(np.searchsorted(s.ts, ctx.now_ns + 5 * S.MIN_NS)), len(s.px) - 1)])
            self._arm(ctx, [("long", p + 10.0, None, None), ("short", p - 10.0, None, None)], lp=p)


LA_DAYS = ["2022-03-15", "2023-08-09"]
LA_CUTS = ("18:00", "18:07", "20:00", "21:15", "00:00", "00:20", "02:00", "03:00", "05:10", "08:30", "08:31", "09:30", "09:41",
           "11:05", "12:20", "13:30", "14:10")                 # at every listed time (the decision itself) and inside each holding window


def la_specs():
    out = [(SpyT, {"at": at, "off": off, **CELLS[k % 3]}) for k, at in enumerate(TIMES) for off in ("atr0p5", "ptsA")]
    out += [(SpyX, {"tf": tf, "n": n, "anchor": a, "sess": s, **CELLS[1]}) for tf, n, a in (("1", 9, "session"), ("5", 21, "rth"), ("15", 50, "session"))
            for s in RM.SESS_PASSES]
    return out


def la_run(specs):
    SpyT.log, SpyX.log = [], []
    res = S.run_many(specs, days=LA_DAYS, workers=1)
    assert all(r["skipped_by_error"] == 0 for r in res)
    return [t for r in res for t in r["trades"]], list(SpyT.log), list(SpyX.log)


def la_diff(specs, real, tapes, cut, rng, monkeypatch):
    """Replace EVERY print from `cut` (ET clock of the Globex day) on by garbage, replay, and compare with the real replay
    everything that was decided or finished up to the cut. -> (list of what differs, rows compared)."""
    trades, log_t, log_x = real
    cut_ns, fake = {}, {}
    for iso, tp in tapes.items():
        d = dt.date.fromisoformat(iso)
        c = S.et_ns(d - dt.timedelta(days=1) if cut >= "18:00" else d, cut)
        k = int(np.searchsorted(tp.ts, c))
        px, sz = tp.px.copy(), tp.size.copy()
        px[k:] = np.round(tp.px[k:] * rng.uniform(0.5, 1.5, len(px) - k) / 0.25) * 0.25
        sz[k:] = rng.integers(1, 500, len(sz) - k)
        cut_ns[iso], fake[iso] = c, S.Tape("NQ", d, tp.contract, tp.ts, px, sz)
        assert (k > 0 or cut == "18:00") and not np.array_equal(px[k:], tp.px[k:]) and np.array_equal(px[:k], tp.px[:k])
    with monkeypatch.context() as mp:
        mp.setattr(S, "load_tape", lambda d, root="NQ", **kw: fake[S._date(d).isoformat()])
        g_trades, g_t, g_x = la_run(specs)
    cms = {iso: c // 10**6 for iso, c in cut_ns.items()}
    before = lambda rows, i: [r for r in rows if r[i] <= cut_ns[r[0]]]                               # noqa: E731
    closed = lambda ts: [t for t in ts if t["exit_ms"] < cms[t["date"]]]                             # noqa: E731
    opened = lambda ts: sorted(ident(t) for t in ts if t["entry_ms"] < cms[t["date"]])               # noqa: E731
    bad = []
    if before(g_t, 3) != before(log_t, 3):
        bad.append("a bracket decided up to the cut (anchor, ATR, legs, orders)")
    if before(g_x, 5) != before(log_x, 5):
        bad.append("a tf close up to the cut (EMA, VWAPs, side, signal)")
    if closed(g_trades) != closed(trades):
        bad.append("a trade finished before the cut")
    if opened(g_trades) != opened(trades):
        bad.append("the entry of a trade opened before the cut")
    assert g_trades != trades or not trades                      # the garbage really was replayed
    return bad, len(before(log_t, 3)) + len(before(log_x, 5)) + len(closed(trades))


def test_garbage_after_a_cut_time_changes_no_earlier_decision_and_no_earlier_trade(monkeypatch):
    real_days()
    tapes = {iso: S.load_tape(iso) for iso in LA_DAYS}
    real = la_run(la_specs())
    trades, log_t, log_x = real
    assert len(log_t) == 2 * 2 * 9 and len(log_x) > 1000 and len(trades) > 40          # every time armed on both days
    rng = np.random.default_rng(7)
    n = 0
    for cut in LA_CUTS:
        bad, rows = la_diff(la_specs(), real, tapes, cut, rng, monkeypatch)
        assert bad == [], (cut, bad)
        n += rows
    assert n > 5000
    assert S.load_tape(LA_DAYS[0]).px[-1] == tapes[LA_DAYS[0]].px[-1]                  # the patch is gone
    # what a bracket reads besides the prints of its own window is PRIOR data: the anchor price and the carried ATR30
    daily = S.with_eve_atr(S.load_daily("NQ"), "NQ")
    dates = [r["date"] for r in daily]
    for iso, at, off, now, lp, atr, legs, orders in log_t:
        tp, d = tapes[iso], dt.date.fromisoformat(iso)
        fire = S.et_ns(d - dt.timedelta(days=1) if at >= "18:00" else d, at)
        k = int(np.searchsorted(tp.ts, fire))
        prev = daily[dates.index(iso) - 1]
        assert now == fire and len(orders) == 2 and [s for s, _ in legs] == ["long", "short"]
        if at == "18:00":                                        # the previous trade date's close and its evening's closing ATR30
            assert k == 0 and lp == prev["c"] and atr == prev["atr30e"] and prev["date"] < iso
        else:
            assert lp == float(tp.px[k - 1]) and tp.ts[k - 1] < fire                   # the last print before the fire
        if at == "00:00":                                        # the evening that has just ended, from its own prints only
            assert atr == S.eve_atr(S.Tape("NQ", d, tp.contract, tp.ts[:k], tp.px[:k], tp.size[:k])) == daily[dates.index(iso)]["atr30e"]
        want = atr * 0.5 if off == "atr0p5" else 10.0
        assert legs[0][1] - lp == pytest.approx(want, abs=1e-9) and lp - legs[1][1] == pytest.approx(want, abs=1e-9)


def test_the_garbage_check_catches_a_family_that_reads_a_later_print(monkeypatch):
    real_days()
    tapes = {iso: S.load_tape(iso) for iso in LA_DAYS}
    specs = [(LeakT, {"at": "09:30", "off": "ptsA", **WIDE})]
    real = la_run(specs)
    assert len(real[1]) == 2
    bad, _ = la_diff(specs, real, tapes, "09:30", np.random.default_rng(7), monkeypatch)
    assert bad and "bracket" in bad[0]
    honest = [(SpyT, {"at": "09:30", "off": "ptsA", **WIDE})]
    assert la_diff(honest, la_run(honest), tapes, "09:30", np.random.default_rng(7), monkeypatch)[0] == []


# ---- the clock is ET all year ---------------------------------------------------------------------------------------------------

def test_the_2000_fire_is_20_et_in_winter_and_summer_and_is_not_moved_to_the_tokyo_open():
    real_days()
    days = ["2023-01-18", "2023-07-12", "2023-03-14"]            # US winter (EST), US summer (EDT), the US-on-DST / Europe-not-yet week
    SpyT.log = []
    res = S.run_many([(SpyT, {"at": at, "off": "ptsA", **WIDE}) for at in ("20:00", "02:00", "09:30")], days=days, workers=1)
    assert all(r["skipped_by_error"] == 0 for r in res)
    at = {(iso, t): ns for iso, t, _, ns, *_ in SpyT.log}
    clock = lambda iso, t, tz: dt.datetime.fromtimestamp(at[(iso, t)] / 1e9, ZoneInfo(tz)).strftime("%Y-%m-%d %H:%M")   # noqa: E731
    assert len(at) == 9
    for iso in days:
        eve = (dt.date.fromisoformat(iso) - dt.timedelta(days=1)).isoformat()
        assert clock(iso, "20:00", "America/New_York") == eve + " 20:00"     # the evening BEFORE the trade date, 20:00 ET
        assert clock(iso, "02:00", "America/New_York") == iso + " 02:00" and clock(iso, "09:30", "America/New_York") == iso + " 09:30"
    assert clock("2023-07-12", "20:00", "UTC")[-5:] == "00:00" and clock("2023-01-18", "20:00", "UTC")[-5:] == "01:00"
    # Tokyo cash opens 09:00 JST: that is the 20:00 ET fire in US summer, but in US winter the fire is at 10:00 JST (one hour late)
    assert clock("2023-07-12", "20:00", "Asia/Tokyo")[-5:] == "09:00" and clock("2023-01-18", "20:00", "Asia/Tokyo")[-5:] == "10:00"
    # Europe: 02:00 ET = 08:00 Frankfurt, except while only the US is on daylight time (then 07:00: the open is 03:00 ET)
    assert clock("2023-07-12", "02:00", "Europe/Berlin")[-5:] == "08:00" and clock("2023-01-18", "02:00", "Europe/Berlin")[-5:] == "08:00"
    assert clock("2023-03-14", "02:00", "Europe/Berlin")[-5:] == "07:00"
    for r in res[:1]:
        for t in r["trades"]:
            assert "20:00:00" <= hms(t["entry_ms"]) < "21:00:00" and S.session_of(t["entry_ms"]) == "eve"
