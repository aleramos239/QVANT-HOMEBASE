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


# ================================================================ 3: the flatten answer says, per account, whether a person must look
def _live(d):
    send(d, entry(1), seq=1)
    fill_entry(d.eng, d.ads["a1"], st(d), 110.25)


def _resting(d):
    send(d, entry(1), seq=1)


def _stuck(d):
    _resting(d)
    d.ads["a1"].stuck.add(st(d).upper_id)                                          # the cancel is accepted, the order stays


def _refused_close(d):
    _live(d)
    d.ads["a1"].fail_market = True


def _unreadable(d):
    _live(d)
    d.ads["a1"].net_error = True


def _already_flat(d):
    _live(d)
    d.ads["a1"].net = 0


def _close_out(d):
    _live(d)
    run(d.eng.lab_flatten(LAB, reason="time"))                                     # its one close order is out already


def _lost(d):
    _live(d)
    d.eng._lab_x(st(d))["lost"] = True


def _no_adapter_open(d):
    _live(d)
    del d.ads["a1"]


def _no_adapter_done(d):
    _resting(d)
    run(d.eng.lab_cancel(LAB))
    del d.ads["a1"]


SCENES = {"a position": (_live, True), "a resting entry": (_resting, True), "a cancel that does not take": (_stuck, False),
          "a close the broker refuses": (_refused_close, False), "a position that cannot be read": (_unreadable, False),
          "already flat": (_already_flat, True), "its close order already out": (_close_out, True),
          "a lost record": (_lost, False), "no adapter, a trade open": (_no_adapter_open, False),
          "no adapter, the trade over": (_no_adapter_done, True)}


@pytest.mark.parametrize("scene", list(SCENES))
def test_the_per_account_ok_of_a_flatten_is_the_engines_own(tmp_path, scene):
    """LabDesk.flatten_view reads `ok` off the steps engine.flatten_strategy answers (and the round's status); the
    engine's own per-account ok (lab_flatten's, which flatten_strategy does not pass on) is the judge."""
    setup, want = SCENES[scene]
    d = mkdesk(tmp_path)
    setup(d)
    own, real = {}, d.eng.lab_flatten

    async def spy(name, **kw):
        got = await real(name, **kw)
        own.update(got)
        return got
    d.eng.lab_flatten = spy
    results = run(d.eng.flatten_strategy(LAB))
    view = d.ld.flatten_view(LAB, results)
    assert view == {"a1": {"ok": own["a1"]["ok"], "steps": results["a1"]}}
    assert view["a1"]["ok"] is want and isinstance(view["a1"]["steps"], list)


def test_a_flatten_with_nothing_to_flatten_has_no_account_to_speak_of(tmp_path):
    d = mkdesk(tmp_path)
    assert d.ld.flatten_view(LAB, run(d.eng.flatten_strategy(LAB))) == {}
    assert d.ld.flatten_view(LAB, None) == {} and d.ld.flatten_view(LAB, {"a1": ["internal error: KeyError: 'x'"]}) == \
        {"a1": {"ok": False, "steps": ["internal error: KeyError: 'x'"]}}


# ================================================================ 4: a failed entry's row in the status block, in plain words
NOT_PLACED = "The entry was not placed. Check it."


@pytest.mark.parametrize("note", ["entry: adapter not connected", "placement did not finish: TimeoutError: no answer",
                                  "upper leg: margin", "lower leg: margin", "not written: [Errno 28] No space left"])
def test_a_failed_entrys_row_shows_plain_words_and_keeps_the_engines_note_as_detail(tmp_path, note):
    d = mkdesk(tmp_path)
    send(d, entry(1), seq=1)
    s = st(d)
    s.status, s.exit_reason, s.note = "error", "error", note                       # as the engine leaves a failed placement
    d.eng._lab_x(s)["clean"] = True
    assert d.eng.lab_rounds(LAB)[0]["why"] == note                                 # the engine's own row: its raw note
    row, = d.ld.status_view(LAB)["rounds"]
    assert (row["why"], row["detail"], row["status"]) == (NOT_PLACED, note, "error")
    snap, = d.ld.snapshot()["strategies"][LAB]["rounds"]                           # the stream's row is not changed
    assert snap["why"] == note and "detail" not in snap


def test_a_long_note_is_cut_and_the_engines_own_sentences_are_left_as_they_are(tmp_path):
    d = mkdesk(tmp_path, accounts=("a1", "a2"))
    d.ads["a1"].reject = "x" * 500                                                 # an outcome the engine cannot call a reject
    send(d, entry(1), seq=1)
    rows = {r["account"]: r for r in d.ld.status_view(LAB)["rounds"]}
    assert rows["a1"]["why"] == "The Desk cannot check the last trade's orders." and "detail" not in rows["a1"]
    assert rows["a2"]["why"] is None and "detail" not in rows["a2"]                # a healthy round: no detail key
    s = st(d, "a2")
    s.status, s.note = "error", "entry: " + "y" * 500
    d.eng._lab_x(s)["clean"] = True
    row = {r["account"]: r for r in d.ld.status_view(LAB)["rounds"]}["a2"]
    assert row["why"] == NOT_PLACED and row["detail"] == ("entry: " + "y" * 500)[:200]
    s.note = "account not connected"                                               # a note that is already plain: kept
    assert {r["account"]: r for r in d.ld.status_view(LAB)["rounds"]}["a2"]["why"] == "account not connected"


# ================================================================ 5: the event's own time is part of what makes it the same event
def flatten_calls(d):
    calls, real = [], d.eng.lab_flatten

    async def spy(name, **kw):
        calls.append(kw)
        return await real(name, **kw)
    d.eng.lab_flatten = spy
    return calls


def test_the_same_seq_and_intents_at_another_time_is_another_event(tmp_path):
    d = mkdesk(tmp_path)
    send(d, entry(1), seq=1)
    fill_entry(d.eng, d.ads["a1"], st(d), 110.25)
    calls = flatten_calls(d)
    b = body(d, [{"op": "flatten", "reason": "time"}], seq=2)
    first = run(d.ld.event(b))
    assert run(d.ld.event(dict(b)))["results"] == first["results"] and len(calls) == 1      # the very same event: once
    later = {**b, "t_ns": b["t_ns"] + 5_000_000_000}                               # a runner that lost its place, 5 s on
    out = run(d.ld.event(later))
    assert len(calls) == 2 and out["results"][0]["op"] == "flatten"                # another event: its exit is applied
    assert run(d.ld.event(dict(b)))["results"] == first["results"] and len(calls) == 2      # the first one's answer is kept
    assert d.ld.snapshot()["strategies"][LAB]["answered"] == [1, 2]


def test_a_restarted_desk_tells_them_apart_by_their_time_too(tmp_path):
    d = mkdesk(tmp_path)
    send(d, entry(1), seq=1)
    fill_entry(d.eng, d.ads["a1"], st(d), 110.25)
    b = body(d, [{"op": "flatten", "reason": "time"}], seq=2)
    first = run(d.ld.event(b))
    ld2 = restart(d)
    calls = flatten_calls(d)
    assert run(ld2.event(dict(b)))["results"] == first["results"] and calls == []  # answered before the restart
    run(ld2.event({**b, "t_ns": b["t_ns"] + 1}))
    assert len(calls) == 1
    again = body(d, [entry(1)], seq=1)                                             # an entry under an answered seq at
    out = run(ld2.event({**again, "t_ns": again["t_ns"] + 1}))                     # another time: out of date, never sent
    assert refusal(out) == "This order is out of date." and len(d.ads["a1"].brackets) == 1
