"""The tick fields a Bar carries for the order-flow indicators: te, span, sweeps (sw), bubbles (bub)."""
from __future__ import annotations

import random

from homebase.charts.bars import BUB_CAP, BarSpec, build, resample
from homebase.charts.studies import Profile
from homebase.charts.tick import BUY, SELL, Tick

TS = 0.25
BASE = 1_760_000_040_000          # a whole minute (a multiple of 60 000 ms)
M1 = BarSpec.parse("time:60")


def T(ms, price, size=1, side=BUY):
    return Tick(BASE + ms, price, size, side)


def test_te_is_the_last_print_and_span_the_time_bars_length():
    closed, cur = build([T(0, 100.0), T(1500, 100.25), T(61_000, 101.0)], M1, TS)
    assert closed[0].te == BASE + 1500 and closed[0].span == 60_000
    assert cur.te == BASE + 61_000 and cur.span == 60_000
    tick_bars, _ = build([T(i * 10, 100.0) for i in range(6)], BarSpec.parse("tick:3"), TS)
    assert tick_bars[0].span == 0


def test_a_sweep_is_one_aggressor_walking_levels_inside_one_millisecond():
    ticks = [T(0, 100.0, 1), T(0, 100.25, 2), T(0, 100.75, 5),       # one ms, one side, 4 ticks wide
             T(5, 101.0, 4), T(5, 101.0, 3),                          # same ms and level twice: not a sweep
             T(9, 101.0, 1, SELL), T(9, 100.75, 1, SELL),             # two levels (1 tick): not a sweep
             T(20, 100.0, 1)]
    closed, cur = build(ticks, M1, TS)
    assert cur.wire(TS)["sw"] == [[BASE, 100.0, 100.75, 8, BUY]]
    closed, _ = build(ticks + [T(61_000, 100.0)], M1, TS)
    assert closed[0].sw == [[BASE, 100.0, 100.75, 8, BUY]]            # sealed with the bar


def test_bubbles_are_second_price_side_totals_of_at_least_three_largest_sixty_kept():
    ticks = [T(0, 100.0, 1), T(400, 100.0, 2), T(999, 100.0, 1, SELL),       # 100.0 buy 3 in second 0; the sell is 1
             T(1000, 100.0, 2), T(1100, 100.25, 9, SELL)]                    # second 1: buy 2 (below min), sell 9
    closed, cur = build(ticks + [T(61_000, 100.0)], M1, TS)
    sec0 = BASE // 1000
    assert closed[0].bub == [[sec0, 100.0, 3, BUY], [sec0 + 1, 100.25, 9, SELL]]
    many = [T(s * 1000, 100.0 + (s % 50) * TS, 3 + s % 7) for s in range(55)] + [T(s * 1000 + 500, 90.0, 40) for s in range(30)]
    bar, _ = build(many + [T(61_000, 100.0)], M1, TS)
    assert len(bar[0].bub) == BUB_CAP
    assert min(b[2] for b in bar[0].bub) >= 3
    assert sum(1 for b in bar[0].bub if b[2] == 40) == 30           # the big ones all stayed


def test_wire_carries_sw_and_bub_with_the_flow_flag_and_not_without():
    closed, _ = build([T(0, 100.0, 12), T(0, 100.5, 3), T(61_000, 100.0)], M1, TS)
    w = closed[0].wire(TS)
    assert "sw" in w and "bub" in w and "big" in w
    lean = closed[0].wire(TS, flow=False)
    assert "sw" not in lean and "bub" not in lean and "big" in lean
    assert "sw" in closed[0].wire(TS, big=False)


def test_resampled_bubbles_and_sweeps_equal_the_direct_build_on_an_ordered_tape():
    rng = random.Random(7)
    ticks, t = [], 0
    for _ in range(12000):
        t += rng.choice([0, 0, 1, 3, 40, 300, 900])
        ticks.append(T(t, 100.0 + rng.randint(0, 12) * TS, rng.randint(1, 15), rng.choice([BUY, SELL])))
    cut = ticks[-1].ts_ms + 1
    ticks.append(Tick(cut + 120_000, 100.0, 1, BUY))
    m1, _ = build(ticks, M1, TS)
    direct, _ = build(ticks, BarSpec.parse("time:300"), TS)
    via = resample(m1, BarSpec.parse("time:300"))
    n = min(len(direct), len(via)) - 1
    assert n >= 3
    for a, b in zip(direct[:n], via[:n]):
        assert a.sw == b.sw and a.bub == b.bub and a.te == b.te and a.span == b.span


def test_copy_keeps_the_developing_state_and_never_shares_it():
    _, cur = build([T(0, 100.0, 2), T(0, 100.25, 1)], M1, TS)      # one tick wide so far: no sweep
    c = cur.copy()
    c.add(T(0, 101.0, 4), TS)
    assert cur.wire(TS)["sw"] == [] and c.wire(TS)["sw"] == [[BASE, 100.0, 101.0, 7, BUY]]


def _oracle_bubbles(ticks):
    """Bubbles straight from the definition: second x price x side totals of >= 3, the 60 largest, in time order."""
    tot = {}
    for tk in ticks:
        key = (tk.ts_ms // 1000, round(tk.price, 6), 1 if tk.side > 0 else -1)
        tot[key] = tot.get(key, 0) + tk.size
    rows = [[s, px, q, side] for (s, px, side), q in tot.items() if q >= 3]
    rows.sort(key=lambda r: (-r[2], r[0], r[1], r[3]))
    return sorted(rows[:BUB_CAP], key=lambda r: (r[0], r[1], r[3]))


def test_a_developing_bar_holds_only_the_current_second_and_wires_what_the_definition_says():
    from homebase.charts.bars import Bar

    rng = random.Random(11)
    ticks, t = [], 0
    for _ in range(4000):                          # ~100 s, 40 levels, so far more than 60 bubbles pile up
        t += rng.choice([0, 0, 5, 20, 60])
        ticks.append(T(t, 100.0 + rng.randint(0, 39) * TS, rng.randint(1, 6), rng.choice([BUY, SELL])))
    bar = Bar.open_at(BASE, "2025-10-09", ticks[0].price)
    folded = False
    for i, tk in enumerate(ticks):
        bar.add(tk, TS)
        assert {k[0] for k in bar._bd} <= {tk.ts_ms // 1000}               # only the current second develops
        folded = folded or bool(bar.bub)
        assert len(bar.bub) <= BUB_CAP
        if i % 97 == 0 or i == len(ticks) - 1:
            assert bar.wire(TS)["bub"] == _oracle_bubbles(ticks[: i + 1])   # equal to the definition, before sealing
    assert folded and len(bar._bd) < 100
    before = bar.wire(TS)
    bar.seal(TS)
    assert bar.wire(TS) == before and bar._bd == {}                        # sealing changes nothing on the wire
    assert bar.bub == _oracle_bubbles(ticks) and len(bar.bub) == BUB_CAP


def test_profile_keeps_the_prior_session_for_the_ghost_and_the_lines():
    from homebase.charts.bars import Bar

    def b(session, px, v):
        x = Bar.open_at(0, session, px)
        x.fp = {int(px / TS): [0, v]}
        return x
    p = Profile(TS)
    p.push(b("2026-10-08", 100.0, 5))
    assert "prev" not in p.value()
    p.push(b("2026-10-09", 101.0, 7))
    v = p.value()
    assert v["poc"] == 101.0 and v["prev"]["poc"] == 100.0
    live = b("2026-10-10", 102.0, 1)                 # the developing bar opens a new session
    v = p.value(live)
    assert v["poc"] == 102.0 and v["prev"]["poc"] == 101.0


def _sweep_ticks(n, base_ms=0):
    """n sweeps, one per 10 ms: a 1-lot at 100.0 and a q-lot at 100.5 in the same millisecond (3 ticks wide)."""
    out = []
    for i in range(n):
        out += [T(base_ms + i * 10, 100.0, 1), T(base_ms + i * 10, 100.5, 1 + (i * 7) % 23)]
    return out


def test_a_bar_keeps_only_the_largest_sweep_cap_in_time_order_and_the_same_ones_every_build():
    from homebase.charts.bars import SW_CAP

    ticks = _sweep_ticks(500) + [T(61_000, 100.0)]
    a, _ = build(ticks, M1, TS)
    b, _ = build(ticks, M1, TS)
    sw = a[0].sw
    assert len(sw) == SW_CAP and sw == b[0].sw
    assert [r[0] for r in sw] == sorted(r[0] for r in sw)                 # time order
    sizes = sorted((1 + (i * 7) % 23 + 1 for i in range(500)), reverse=True)
    assert sorted((r[3] for r in sw), reverse=True) == sizes[:SW_CAP]     # the largest, no smaller one in
    assert len(a[0].wire(TS)["sw"]) <= SW_CAP
    cur = build(_sweep_ticks(500), M1, TS)[1]                             # still developing: the wire is capped too
    assert len(cur.wire(TS)["sw"]) <= SW_CAP


def test_merging_capped_bars_stays_capped_and_equals_the_direct_build():
    from homebase.charts.bars import SW_CAP

    ticks = _sweep_ticks(300, 0) + _sweep_ticks(300, 60_000) + [T(121_000, 100.0)]
    m1, _ = build(ticks, M1, TS)
    assert len(m1[0].sw) == SW_CAP and len(m1[1].sw) == SW_CAP
    via = resample(m1, BarSpec.parse("time:120"))
    direct, _ = build(ticks, BarSpec.parse("time:120"), TS)
    assert len(via[0].sw) == SW_CAP and via[0].sw == direct[0].sw


def test_the_prior_session_profile_is_built_once_per_session_not_once_per_update(monkeypatch):
    import homebase.charts.studies as st
    from homebase.charts.bars import Bar

    def b(session, px, v):
        x = Bar.open_at(0, session, px)
        x.fp = {int(px / TS): [0, v]}
        return x
    calls = []
    real = st.profile_from
    monkeypatch.setattr(st, "profile_from", lambda vol, tick, va=0.70: calls.append(dict(vol)) or real(vol, tick, va))
    p = Profile(TS)
    p.push(b("2026-10-08", 100.0, 5))
    p.push(b("2026-10-09", 101.0, 7))
    first = p.value()
    assert first["prev"]["poc"] == 100.0 and len(calls) == 2               # this session + the prior one
    for _ in range(5):
        assert p.value() == first
    assert len(calls) == 2 + 5                                             # only the current session again
    live = b("2026-10-10", 102.0, 1)                                       # a new session developing: the prior is 10-09
    calls.clear()
    v = p.value(live)
    assert v["prev"]["poc"] == 101.0 and len(calls) == 2
    assert p.value(live) == v and len(calls) == 3
    p.push(live)                                                           # it closes: the same prior, still cached
    assert p.value()["prev"]["poc"] == 101.0 and len(calls) == 4


# ---- tape orders (ag), print counts (fpn) and the running-delta numbers (dmax / dmin / dhi / dlo), 2026-10-21

def test_a_tape_order_is_one_run_of_same_side_prints_in_one_millisecond_at_its_average_price():
    from homebase.charts.bars import AG_CAP, AG_MIN
    ticks = [T(0, 100.0, 4), T(0, 100.25, 3), T(0, 100.5, 5),          # one buy of 12 over three levels
             T(5, 100.0, 10, SELL),                                      # one print of 10: an order too
             T(7, 100.0, 4, SELL), T(7, 100.25, 5, SELL),                # 9: below AG_MIN
             T(9, 100.0, 6), T(9, 100.0, 6)]                             # the run still forming at the end
    closed, cur = build(ticks, M1, TS)
    big = [BASE, round(1203.25 / 12, 6), 100.0, 100.5, 12, BUY, 3]
    ten = [BASE + 5, 100.0, 100.0, 100.0, 10, SELL, 1]
    assert cur.ag == [big, ten]
    assert cur.wire(TS)["ag"] == [big, ten, [BASE + 9, 100.0, 100.0, 100.0, 12, BUY, 2]]
    assert "ag" not in cur.wire(TS, flow=False)
    closed, _ = build(ticks + [T(61_000, 100.0)], M1, TS)
    assert closed[0].ag == [big, ten, [BASE + 9, 100.0, 100.0, 100.0, 12, BUY, 2]]
    many = [T(i * 2, 100.0 + (i % 9) * TS, AG_MIN + i % 5, BUY if i % 2 else SELL) for i in range(200)]
    bar, _ = build(many + [T(61_000, 100.0)], M1, TS)
    assert len(bar[0].ag) == AG_CAP and sum(1 for r in bar[0].ag if r[4] == AG_MIN + 4) == 40    # the largest stay
    assert min(r[4] for r in bar[0].ag) == AG_MIN + 3
    assert bar[0].ag == sorted(bar[0].ag)                                              # in time order


def test_fpn_counts_the_prints_at_each_price_by_side():
    ticks = [T(0, 100.0, 5, SELL), T(1, 100.0, 1, SELL), T(2, 100.0, 7), T(3, 100.25, 2), T(4, 100.25, 2)]
    _, cur = build(ticks, M1, TS)
    assert cur.fpn == {400: [2, 1], 401: [0, 2]}
    w = cur.wire(TS)
    assert w["fpn"] == [[100.0, 2, 1], [100.25, 0, 2]] and w["fp"] == [[100.0, 6, 7], [100.25, 0, 4]]
    assert "fpn" not in cur.wire(TS, fp=False)


def test_the_running_delta_numbers_follow_the_definition():
    ticks = [T(0, 100.0, 3), T(1, 99.75, 5, SELL), T(2, 100.5, 4), T(3, 100.5, 1, SELL), T(4, 100.0, 2, SELL)]
    _, cur = build(ticks, M1, TS)                    # delta: 3, -2, 2, 1, -1
    assert (cur.dmax, cur.dmin, cur.dhi, cur.dlo) == (3, -2, 1, -2)
    w = cur.wire(TS)
    assert (w["dmax"], w["dmin"], w["dhi"], w["dlo"]) == (3, -2, 1, -2)
    _, cur = build([T(0, 100.0, 2, SELL), T(1, 100.0, 1, SELL)], M1, TS)
    assert (cur.dmax, cur.dmin, cur.dhi, cur.dlo) == (0, -3, -3, -3)     # the open counts as delta 0


def test_resampled_tape_orders_counts_and_delta_numbers_equal_the_direct_build():
    rng = random.Random(5)
    ticks, t = [], 0
    for _ in range(12000):
        t += rng.choice([0, 0, 0, 1, 3, 40, 300, 900])
        ticks.append(T(t, 100.0 + rng.randint(0, 12) * TS, rng.choice([1, 2, 3, 5, 8, 12, 30]), rng.choice([BUY, SELL])))
    ticks.append(Tick(ticks[-1].ts_ms + 120_001, 100.0, 1, BUY))
    m1, _ = build(ticks, M1, TS)
    for size in (300, 900):
        direct, _ = build(ticks, BarSpec.parse(f"time:{size}"), TS)
        via = resample(m1, BarSpec.parse(f"time:{size}"))
        n = min(len(direct), len(via)) - 1
        assert n >= 1
        for a, b in zip(direct[:n], via[:n]):
            assert a.ag == b.ag and a.fpn == b.fpn and len(a.ag) > 0
            assert (a.dmax, a.dmin, a.dhi, a.dlo) == (b.dmax, b.dmin, b.dhi, b.dlo)
            assert a.wire(TS) == b.wire(TS)
    one = m1[0].copy()
    for m in m1[1:5]:
        one.merge(m)                                 # cap=True at every step keeps the same rows as capping once
    five = m1[0].copy()
    for m in m1[1:5]:
        five.merge(m, cap=False)
    five.finish_merge()
    assert one.ag == five.ag and one.fpn == five.fpn and (one.dmax, one.dmin, one.dhi, one.dlo) == (five.dmax, five.dmin, five.dhi, five.dlo)


def test_a_bar_from_before_the_tape_fields_loads_with_none_and_a_resample_that_takes_it_has_none():
    import pickle
    from homebase.charts.bars import Bar
    closed, _ = build([T(0, 100.0, 12), T(1, 100.25, 3, SELL), T(60_000, 100.0, 2), T(120_000, 100.0, 1)], M1, TS)
    state = dict(closed[0].__dict__)
    for k in ("ag", "fpn", "dmax", "dmin", "dhi", "dlo"):
        del state[k]
    old = Bar.__new__(Bar)
    old.__dict__.update(state)
    again = pickle.loads(pickle.dumps(old))
    assert (again.ag, again.fpn, again.dmax, again.dmin, again.dhi, again.dlo) == (None,) * 6
    w = again.wire(TS)
    assert not {"ag", "fpn", "dmax", "dmin", "dhi", "dlo"} & set(w) and w["sw"] == closed[0].wire(TS)["sw"]
    again.add(T(2, 100.0, 15), TS)                   # an old bar keeps developing without them
    assert again.ag is None and again.fpn is None and again.dmax is None
    three = resample([again, closed[1]], BarSpec.parse("time:180"))
    assert len(three) == 1 and (three[0].ag, three[0].fpn, three[0].dmax, three[0].dlo) == (None,) * 4
    assert three[0].n == again.n + closed[1].n and three[0].ords_b == again.ords_b + closed[1].ords_b
    c = again.copy()
    assert (c.ag, c.fpn, c.dhi) == (None, None, None)


# What the OLD bars.py (main ab61bbb0, before ag / fpn / the delta numbers) made of this fixture: every field and wire
# key that existed then, hashed. The new fields must never move any of them (the engine mirrors these definitions).
_OLD_KEYS = ("t", "ms", "s", "o", "h", "l", "c", "v", "d", "n", "big", "sw", "bub", "fp")
_OLD_SHA = "6c3a0483bbb01c96bc80b2563fc8546dadc4e3dcd8c5f4b2d0fca5897a616459"


def test_the_fields_and_wire_keys_from_before_are_byte_for_byte_what_they_were():
    import hashlib
    import json
    rng = random.Random(21)
    ticks, t = [], 0
    for _ in range(9000):
        t += rng.choice([0, 0, 0, 1, 2, 30, 250, 700])
        ticks.append(Tick(BASE + t, 100.0 + rng.randint(0, 15) * TS, rng.choice([1, 1, 2, 3, 5, 8, 12, 25]), rng.choice([BUY, SELL])))
    ticks.append(Tick(BASE + t + 600_000, 100.0, 1, BUY))
    out = []
    for key in ("time:60", "tick:50", "volume:300", "range:4"):
        closed, cur = build(ticks, BarSpec.parse(key), TS)
        bars = closed + ([cur] if cur else [])
        if key == "time:60":
            bars += resample(closed, BarSpec.parse("time:300"))
        for b in bars:
            w = b.wire(TS)
            out.append([[w[k] for k in _OLD_KEYS], b.sw, b.bub, b.big, b.ords_b, b.ords_s, sorted(b.fp.items()),
                        b.v, b.buy, b.sell, b.n, b.pv, b.p2v, b.te, b.span, b.closed])
    assert len(out) == 5613
    assert hashlib.sha256(json.dumps(out, separators=(",", ":")).encode()).hexdigest() == _OLD_SHA
