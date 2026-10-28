"""Two strategies signal in the same instant (owner, 2026-10-27). Fake adapters, no broker. Every broker read yields,
so the two entries really interleave (the same trick as test_engine_lab's two-at-once test)."""
from __future__ import annotations

import asyncio

from homebase.desk.engine_lab import GROUP_HEDGE
from tests import test_engine_lab as tlab
from tests.test_engine_groups import ACCTS, TWO, group, mk, took


def slow_reads(ads):
    for ad in ads.values():
        real = ad.get_net_position

        async def slow(symbol, real=real):
            await asyncio.sleep(0)
            return await real(symbol)

        ad.get_net_position = slow


def both(eng, a_leg, b_leg):
    sizes = {a: 1 for a in eng.adapters}

    async def go():
        return await asyncio.gather(eng.lab_enter(tlab.LAB, [a_leg], sizes, max_rounds=5),
                                    eng.lab_enter(TWO, [b_leg], sizes, max_rounds=5))
    return tlab.run(go())


def test_same_group_same_side_goes_to_two_accounts(tmp_path):
    eng, ads, _ = mk(tmp_path)
    group(eng)
    slow_reads(ads)
    one, two = both(eng, tlab.leg(iid=1), tlab.leg(iid=2))
    assert sorted(took(one) + took(two)) == ["a1", "a2"]
    assert [len(ads[a].brackets) for a in ACCTS] == [1, 1, 0]
    assert eng.groups["g"]["last"] in ("a1", "a2")


def test_same_group_opposite_side_sends_one_and_refuses_the_other(tmp_path):
    eng, ads, _ = mk(tmp_path)
    group(eng)
    slow_reads(ads)
    one, two = both(eng, tlab.leg(iid=1, side="Buy"), tlab.leg(iid=2, side="Sell", px=90.0, sl=95.0, tp=80.0))
    assert took(one) == ["a1"] and took(two) == [] and two["reason"] == GROUP_HEDGE
    assert sum(len(ads[a].brackets) for a in ACCTS) == 1


def test_not_in_a_group_each_takes_its_own_turn_on_the_same_account(tmp_path):
    eng, ads, _ = mk(tmp_path, accounts=("a1",))
    slow_reads(ads)
    one, two = both(eng, tlab.leg(iid=1), tlab.leg(iid=2))
    assert sorted(took(one) + took(two)) == ["a1"]                  # one market, one account: the second waits out
    assert len(ads["a1"].brackets) == 1


def test_take_turns_without_a_group_second_signal_moves_to_the_next_account(tmp_path):
    eng, ads, _ = mk(tmp_path)
    eng.set_rotation(tlab.LAB, True)
    eng.set_rotation(TWO, True)
    slow_reads(ads)
    one, two = both(eng, tlab.leg(iid=1), tlab.leg(iid=2))
    assert sorted(took(one) + took(two)) == ["a1", "a2"]


def test_next_turn_after_a_simultaneous_pair_skips_the_busy_accounts(tmp_path):
    eng, ads, _ = mk(tmp_path)
    group(eng)
    slow_reads(ads)
    both(eng, tlab.leg(iid=1), tlab.leg(iid=2))
    out = tlab.run(eng.lab_enter(tlab.LAB, [tlab.leg(iid=3)], {a: 1 for a in eng.adapters}, max_rounds=5))
    assert took(out) == ["a3"]
