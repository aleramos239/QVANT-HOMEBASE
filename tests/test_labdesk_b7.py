"""Step B, task B7: the Desk's small follow-ups (parked items of the B2, B3 and B6 reviews, server side). One group
of tests per item, each written before its change. The real engine on fake adapters; no broker, no network."""
from __future__ import annotations

import dataclasses
import datetime as dt
import json

import pytest

from homebase import labdesk
from homebase.labdesk import LabDesk
from homebase.labrun import store
from tests.labdesk_util import DATE, LAB, MARK, Stepper, body, entry, journal, mkdesk, pair, send
from tests.test_engine import run
from tests.test_engine_lab import fill_entry, fill_exit
from tests.test_labdesk import NQ930, hold_clock, placed, refusal, st, tick
from tests.trading_util import Mono

UTC = dt.timezone.utc
BOT = {"nq930": dataclasses.replace(NQ930, self_fire=False)}


def restart(d) -> LabDesk:
    ld2 = LabDesk(d.cfg, d.eng, d.ads)
    ld2._mono = Stepper()
    ld2.start()
    return ld2


def lines(d, name=None):
    return journal(d.tmp, name)


# ================================================================ 1: the runner is alive across the view pause, or by beats
class Wall:
    """The desk's wall clock for the runner's file (LabDesk._utc), moved by hand."""

    def __init__(self):
        self.now = dt.datetime(2026, 9, 14, 13, 29, 45, tzinfo=UTC)

    def __call__(self):
        return self.now

    def plus(self, s):
        self.now += dt.timedelta(seconds=s)


def runner_file(wall, age_s):
    store.put_runner({"pid": 1, "seen_utc": (wall.now - dt.timedelta(seconds=age_s)).isoformat()})


def alive(d):
    return d.ld.status_view(LAB)["runner"]["alive"]


def test_a_fresh_runner_stays_alive_through_a_sixty_second_view_pause(tmp_path):
    d = mkdesk(tmp_path)
    wall = d.ld._utc = Wall()
    d.ld._mono = Mono()
    runner_file(wall, 3)
    run(d.ld.refresh())
    assert alive(d) is True
    paused = [True]
    d.ld._paused = lambda: paused[0]                                               # 09:29:50: the views pause, no refresh runs
    reads = []
    real = d.ld._read
    d.ld._read = lambda: (reads.append(1), real())[1]
    for _ in range(30):                                                            # sixty seconds of skipped refreshes
        wall.plus(2)
        assert run(d.ld.refresh()) is None
        assert alive(d) is True
    assert reads == []                                                             # ... and not one disk read in the pause
    assert d.ld.status_view(LAB)["runner"]["age_s"] == 3.0                         # its age as it was read, not as of now
    paused[0] = False
    assert alive(d) is True                                                        # the pause is over, the next refresh not yet run
    runner_file(wall, 2)                                                           # the runner kept writing all along
    run(d.ld.refresh())
    assert alive(d) is True and reads == [1]


def test_a_runner_that_died_before_the_pause_is_not_alive_in_it(tmp_path):
    d = mkdesk(tmp_path)
    wall = d.ld._utc = Wall()
    d.ld._mono = Mono()
    runner_file(wall, 90)
    run(d.ld.refresh())
    assert alive(d) is False
    d.ld._paused = lambda: True
    wall.plus(30)
    run(d.ld.refresh())
    assert alive(d) is False and d.ld.status_view(LAB)["runner"]["age_s"] == 90.0


def test_a_runner_that_dies_in_the_pause_is_found_dead_by_the_first_refresh_after_it(tmp_path):
    d = mkdesk(tmp_path)
    wall = d.ld._utc = Wall()
    d.ld._mono = Mono()
    runner_file(wall, 1)
    run(d.ld.refresh())
    paused = [True]
    d.ld._paused = lambda: paused[0]
    wall.plus(60)
    run(d.ld.refresh())
    paused[0] = False
    run(d.ld.refresh())                                                            # the file is 61 s old by now
    assert alive(d) is False
    wall.plus(5)
    assert d.ld.status_view(LAB)["runner"]["age_s"] == 66.0                        # outside a pause the age is as of now


def test_heartbeat_posts_alone_keep_the_runner_alive(tmp_path):
    d = mkdesk(tmp_path)
    d.ld._utc = Wall()
    mono = d.ld._mono = Mono()
    assert d.ld.status_view(LAB)["runner"] == {"alive": False, "age_s": None}      # no file, no beat
    d.ld.heartbeat({"pid": 7, "strategies": {}})                                   # a post, whatever it names
    mono.t += 19.5
    assert d.ld.status_view(LAB)["runner"] == {"alive": True, "age_s": 19.5}
    mono.t += 1.0
    assert alive(d) is False
    runner_file(d.ld._utc, 500)                                                    # a stale file beside fresh beats: alive
    run(d.ld.refresh())
    d.ld.heartbeat({"pid": 7, "strategies": {}})
    assert d.ld.status_view(LAB)["runner"] == {"alive": True, "age_s": 0.0}
