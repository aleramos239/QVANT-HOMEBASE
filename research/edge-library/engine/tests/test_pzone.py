"""PZONE: the stacked profile zones (families/pzone.py) -- the zone rule against the chart's own example (tests/js/flowmath.test.mjs
profileZones), the tick-rule delta, and the levels a day trades. No net, win rate or profit factor is read."""
import datetime as dt
from types import SimpleNamespace

import numpy as np

import l2sim as S
from families import pzone as P


def day_raw():
    """The chart test's session on 1-point ticks: A balances at 100-101, B runs 101 -> 110 with buyers hitting 105 hard, C and D balance at
    109-111 (per tick: volume, delta from its footprint rows)."""
    vol = {100: 40, 101: 42, 102: 3, 103: 3, 104: 3, 105: 41, 106: 3, 107: 3, 108: 3, 109: 85, 110: 99, 111: 82}
    dlt = {100: 0, 101: 2, 102: 1, 103: 1, 104: 1, 105: 39, 106: 1, 107: 1, 108: 1, 109: -1, 110: -1, 111: 2}
    k0 = 100
    return {"k0": k0, "vol": np.array([vol[k] for k in range(100, 112)], float), "dlt": np.array([dlt[k] for k in range(100, 112)], float),
            "mmin": np.array([0, 30, 60, 90]), "mlo": np.array([100, 101, 109, 109]), "mhi": np.array([101, 110, 111, 111]), "eve": 0, "n": 4}


def test_zone_rule_matches_the_chart():
    assert P.zones_of(day_raw(), 1, 30, 3.0, 30) == [(105, 105, 1, 39.0)]
    assert P.zones_of(day_raw(), 1, 30, 3.0, 0) == []                     # no low volume node
    assert P.zones_of(day_raw(), 1, 30, 50.0, 30) == []                   # no outlier
    r = day_raw()
    r.update(mmin=r["mmin"][:2], mlo=r["mlo"][:2], mhi=r["mhi"][:2])
    assert P.zones_of(r, 1, 30, 3.0, 30) == []                             # single prints of the last letter do not count yet
    r = day_raw()
    r.update(mmin=np.append(r["mmin"], 120), mlo=np.append(r["mlo"], 104), mhi=np.append(r["mhi"], 106))
    assert P.zones_of(r, 1, 30, 3.0, 30) == []                             # traded back into later the same session: gone


def test_tick_rule_delta_and_minutes():
    d = dt.date(2024, 3, 5)
    t0 = S.et_ns(d, "00:00") - 60 * S.NS                                    # 23:59 the evening before, then 00:00
    tape = SimpleNamespace(root="NQ", date=d, ts=np.array([t0, t0 + 1, t0 + 60 * S.NS, t0 + 60 * S.NS + 5, t0 + 60 * S.NS + 9]),
                           px=np.array([100.0, 100.25, 100.25, 100.0, 100.0]), size=np.array([1, 2, 3, 4, 5]))
    r = P.raw_of(tape)
    assert r["k0"] == 400 and list(r["vol"]) == [10, 5] and list(r["dlt"]) == [-9, 5]   # up, same (up), down, same (down); the first: none
    assert list(r["mmin"]) == [0, 1] and list(r["mlo"]) == [400, 400] and list(r["mhi"]) == [401, 401] and r["eve"] == 1


def test_a_touch_uses_a_zone_up():
    z = [(105, 105, 1, 39.0), (120, 123, -1, -50.0)]
    assert P._touch(z, 100, 104) == z
    assert P._touch(z, 104, 105) == z[1:]
    assert P._touch(z, 123, 130) == z[:1]


def test_colour_match_picks_only_the_matching_zone():
    class Ctx:
        def __init__(self):
            self.placed = []
        def cancel(self, o):
            pass
        def oco(self, a, b):
            pass
    z = P.PZone.__new__(P.PZone)
    z.tick, z.C, z.orders, z.oz, z.atr = 1.0, [100.0], [], {}, 2.0
    z.live = [(103, 103, 1, 50.0), (106, 106, -1, -50.0), (97, 97, -1, -50.0), (94, 94, 1, 50.0)]
    got = []
    z._lim = lambda ctx, side, px, struct=None: got.append((side, px)) or None
    for match, want in (("off", [("short", 103.0), ("long", 97.0)]), ("on", [("short", 106.0), ("long", 94.0)])):
        got.clear()
        z.p = {**P.PZone.DEFAULTS, **{"match": match, "stop_atr": 1.0, "orders": "nearest", "vwap18": "off"}}
        z.fam_signal(Ctx())
        assert sorted(got) == sorted(want), match


def test_leg_outlier_is_measured_against_its_own_leg():
    """The chart test of the same name (tests/js/flowmath.test.mjs): busy one-sided balances, the leg's 105 is 6 against a leg median of 1."""
    vol = {100: 40, 101: 40, 102: 3, 103: 3, 104: 3, 105: 8, 106: 3, 107: 3, 108: 3, 109: 53, 110: 71, 111: 80}
    dlt = {100: 30, 101: 30, 102: 1, 103: 1, 104: 1, 105: 6, 106: 1, 107: 1, 108: 1, 109: 31, 110: 31, 111: 60}
    r = day_raw()
    r.update(vol=np.array([vol[k] for k in range(100, 112)], float), dlt=np.array([dlt[k] for k in range(100, 112)], float))
    assert P.zones_of(r, 1, 30, 3.0, 30, "session") == []
    assert P.zones_of(r, 1, 30, 3.0, 30, "leg") == [(105, 105, 1, 6.0)]
    assert P.zones_of(day_raw(), 1, 30, 3.0, 30, "leg") == [(105, 105, 1, 39.0)]


def test_every_zone_gets_an_order():
    class Ctx:
        def cancel(self, o):
            pass
        def oco(self, *os):
            grp.append(len(os))
    z = P.PZone.__new__(P.PZone)
    z.tick, z.C, z.orders, z.oz, z.atr = 1.0, [100.0], [], {}, 2.0
    z.live = [(103, 103, 1, 50.0), (106, 106, -1, -50.0), (97, 97, -1, -50.0), (94, 94, 1, 50.0)]
    got, grp, n = [], [], [0]

    class O:
        def __init__(self, side):
            n[0] += 1
            self.id, self.side, self.status = n[0], side, "working"

    def lim(ctx, side, px, struct=None):
        got.append((side, px))
        return O(-1 if side == "short" else 1)
    z._lim = lim
    for match, want in (("off", [("long", 94.0), ("long", 97.0), ("short", 103.0), ("short", 106.0)]), ("on", [("long", 94.0), ("short", 106.0)])):
        got.clear(); grp.clear(); z.orders, z.oz = [], {}
        z.p = {**P.PZone.DEFAULTS, **{"match": match, "stop_atr": 1.0, "orders": "all", "vwap18": "off"}}
        z.fam_signal(Ctx())
        assert got == want and grp == [len(want)], match


def test_6pm_vwap_keeps_one_side():
    class Ctx:
        def cancel(self, o):
            pass
        def oco(self, *os):
            pass
    z = P.PZone.__new__(P.PZone)
    z.tick, z.C, z.orders, z.oz, z.atr = 1.0, [100.0], [], {}, 2.0
    z.live = [(103, 103, 1, 50.0), (106, 106, -1, -50.0), (97, 97, -1, -50.0), (94, 94, 1, 50.0)]
    got = []
    z._lim = lambda ctx, side, px, struct=None: got.append((side, px)) or None
    for vp, vv, want in ((99.0, 1.0, [("long", 94.0), ("long", 97.0)]), (101.0, 1.0, [("short", 103.0), ("short", 106.0)]), (0.0, 0.0, [])):
        got.clear()
        z.vp, z.vv = vp, vv
        z.p = {**P.PZone.DEFAULTS, **{"match": "off", "stop_atr": 1.0, "orders": "all", "vwap18": "with"}}
        z.fam_signal(Ctx())
        assert sorted(got) == want, (vp, vv)


def test_vwap_side_is_fixed_once():
    class Ctx:
        date = dt.date(2024, 3, 5)
        def __init__(self, m):
            self.now_ns = S.et_ns(self.date, "00:00") + m * 60 * S.NS
        def cancel(self, o):
            pass
        def oco(self, *os):
            pass
    z = P.PZone.__new__(P.PZone)
    z.tick, z.orders, z.oz, z.atr, z.fixed = 1.0, [], {}, 2.0, 0
    z.live = [(103, 103, 1, 50.0), (106, 106, -1, -50.0), (97, 97, -1, -50.0), (94, 94, 1, 50.0)]
    z.vp, z.vv = 101.0, 1.0
    got = []
    z._lim = lambda ctx, side, px, struct=None: got.append((side, px)) or None
    z.p = {**P.PZone.DEFAULTS, **{"match": "off", "stop_atr": 1.0, "orders": "all", "vwap18": "fix", "vfix": 570, "ema1h": 0, "emaside": "with"}}
    z.C = [100.0]
    z.fam_signal(Ctx(560))
    assert got == []                                   # before the fix time: nothing, and the side is not read yet
    z.fam_signal(Ctx(570))
    assert sorted(got) == [("short", 103.0), ("short", 106.0)]
    assert z.fixed == -1                               # 100 is under the 101 VWAP: sells only, for the rest of the day
    got.clear(); z.C = [110.0]
    z.fam_signal(Ctx(600))
    assert z.fixed == -1                               # price crossing the VWAP later does not flip the side


def test_vwap_zone_mode_needs_the_zone_on_the_right_side():
    class Ctx:
        def cancel(self, o):
            pass
        def oco(self, *os):
            pass
    z = P.PZone.__new__(P.PZone)
    z.tick, z.C, z.orders, z.oz, z.atr, z.fixed = 1.0, [100.0], [], {}, 2.0, 0
    z.live = [(103, 103, 1, 50.0), (106, 106, -1, -50.0), (97, 97, -1, -50.0), (94, 94, 1, 50.0)]
    got = []
    z._lim = lambda ctx, side, px, struct=None: got.append((side, px)) or None
    z.p = {**P.PZone.DEFAULTS, "orders": "all", "vwap18": "zone"}
    z.vp, z.vv = 95.0, 1.0                                # the VWAP at 95: buys above it (97), sells below it (none)
    z.fam_signal(Ctx())
    assert got == [("long", 97.0)]
