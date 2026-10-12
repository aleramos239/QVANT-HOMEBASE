from homebase.charts.bookflow import BookTracker, BUY, SELL, TUNING

TICK = 0.25

def lv(px0, sizes, step):
    return [[px0 + i * step, s] for i, s in enumerate(sizes)]

def book(bid=100.0, size=10, big=None):
    """10 bids below `bid`, 10 offers above bid+0.25; every level `size`; big = {('b'|'a', n_ticks_from_touch): size}"""
    big = big or {}
    b = [[bid - i * TICK, big.get(('b', i), size)] for i in range(10)]
    a = [[bid + TICK + i * TICK, big.get(('a', i), size)] for i in range(10)]
    return b, a

def warm(tr, secs=12, t0=0):
    out = []
    for s in range(secs):
        out += tr.on_book(t0 + s * 1000, *book())
    return out

def eps(events): return [e for e in events if e["k"] == "ep"]
def samples(events): return [e for e in events if e["k"] == "sample"]

def test_samples_once_per_second_last_book_wins():
    tr = BookTracker(TICK)
    ev = tr.on_book(1000, *book(size=10)) + tr.on_book(1500, *book(size=30))
    assert ev == []
    ev = tr.on_book(2100, *book(size=10))
    s = samples(ev)
    assert len(s) == 1 and s[0]["t"] == 1000
    t, b10, a10, i1, i5, i10, micro, spread = s[0]["row"]
    assert (t, b10, a10) == (1000, 300.0, 300.0)
    assert i1 == i5 == i10 == 0.0 and spread == 1 and micro == 100.125

def test_imbalance_signs_and_micro_leans_to_the_thin_side():
    tr = BookTracker(TICK)
    b, a = book()
    b[0][1] = 50                       # bid heavy at the touch
    tr.on_book(1000, b, a)
    row = samples(tr.flush(2000))[0]["row"]
    assert row[3] > 0 and row[4] > 0 and row[5] > 0
    assert row[6] > 100.125            # microprice sits nearer the thin offer

def test_no_episode_before_a_median_exists():
    tr = BookTracker(TICK)
    ev = []
    for s in range(5):
        ev += tr.on_book(s * 1000, *book(big={('b', 3): 200}))
    assert eps(ev) == []

def test_big_level_opens_after_two_seconds_and_traded_when_consumed():
    tr = BookTracker(TICK)
    ev = warm(tr, 12)
    t = 12_000
    big_px = 100.0 - 3 * TICK
    ev += tr.on_book(t, *book(big={('b', 3): 200}))             # level appears
    assert eps(ev) == []
    ev += tr.on_book(t + 3500, *book(big={('b', 3): 200}))      # old enough: shown
    e = eps(ev)
    assert len(e) == 1 and e[0]["end"] == "open" and e[0]["p"] == big_px and e[0]["s"] == "b"
    ev = tr.on_print(t + 4000, big_px, 150, SELL)               # sellers hit it
    ev += tr.on_book(t + 4250, *book(big={('b', 3): 40}))
    ev += tr.on_book(t + 4500, *book())                          # gone
    e = eps(ev)
    assert e and e[-1]["end"] == "traded" and e[-1]["tr"] == 150 and e[-1]["t1"] == t + 4500

def test_pulled_when_it_vanishes_with_price_close_and_no_trades():
    tr = BookTracker(TICK)
    warm(tr, 12)
    t = 12_000
    tr.on_book(t, *book(big={('b', 1): 300}))                    # one tick under the touch
    tr.on_book(t + 3500, *book(big={('b', 1): 300}))
    ev = tr.on_book(t + 4000, *book())
    e = eps(ev)
    assert e and e[-1]["end"] == "pulled"

def test_far_level_that_drifts_off_is_faded_not_pulled():
    tr = BookTracker(TICK)
    warm(tr, 12)
    t = 12_000
    tr.on_book(t, *book(big={('b', 8): 300}))                    # 8 ticks away
    tr.on_book(t + 3500, *book(big={('b', 8): 300}))
    ev = tr.on_book(t + 4000, *book())
    assert eps(ev)[-1]["end"] == "faded"

def test_short_lived_level_is_never_emitted():
    tr = BookTracker(TICK)
    warm(tr, 12)
    ev = tr.on_book(12_000, *book(big={('b', 2): 300}))
    ev += tr.on_book(13_000, *book())
    assert eps(ev) == []

def test_absorption_flag_when_volume_is_eaten_but_the_level_holds():
    tr = BookTracker(TICK)
    warm(tr, 12)
    t = 12_000
    big_px = 100.0 - 1 * TICK
    tr.on_book(t, *book(big={('b', 1): 100}))
    ev = tr.on_book(t + 3500, *book(big={('b', 1): 100}))
    assert eps(ev)[-1]["ab"] is None
    ev = tr.on_print(t + 4000, big_px, 60, SELL)                 # 0.6x shown, not yet 1x
    assert [e for e in eps(ev) if e["ab"]] == []
    ev = tr.on_print(t + 4100, big_px, 60, SELL)                 # 120 traded >= 1 x 100 and >= 4 x median; still shows size
    flagged = [e for e in eps(ev) if e["ab"] is not None]
    assert flagged and flagged[0]["ab"] == t + 4100 and flagged[0]["end"] == "open"

def test_no_absorption_when_price_trades_through():
    tr = BookTracker(TICK)
    warm(tr, 12)
    t = 12_000
    tr.on_book(t, *book(big={('b', 1): 100}))
    tr.on_book(t + 3500, *book(big={('b', 1): 100}))
    tr.on_print(t + 3600, 100.0 - 3 * TICK, 5, SELL)             # printed 2 ticks beyond
    ev = tr.on_print(t + 4000, 100.0 - TICK, 300, SELL)
    assert [e for e in eps(ev) if e["ab"]] == []

def test_finish_closes_open_levels_and_commits_the_last_second():
    tr = BookTracker(TICK)
    warm(tr, 12)
    tr.on_book(12_000, *book(big={('b', 1): 300}))
    tr.on_book(15_000, *book(big={('b', 1): 300}))
    ev = tr.finish()
    assert samples(ev) and eps(ev)[-1]["end"] == "faded"

def test_deterministic_same_input_same_output():
    def run():
        tr = BookTracker(TICK); out = warm(tr, 12)
        out += tr.on_book(12_000, *book(big={('a', 2): 250}))
        out += tr.on_print(14_000, 100.0 + TICK + 2 * TICK, 90, BUY)
        out += tr.on_book(16_000, *book(big={('a', 2): 250}))
        out += tr.finish()
        return out
    assert run() == run()


def test_an_empty_or_one_sided_book_line_never_breaks_the_tracker():
    tr = BookTracker(TICK)
    out = warm(tr, 12)
    out += tr.on_book(12_000, [], [])                                  # nothing resting at all
    out += tr.on_book(13_000, [[100.0, 10]], [])                       # one side only
    out += tr.on_book(14_000, *book())
    out += tr.on_print(14_100, 100.0, 5, SELL)
    out += tr.flush(20_000)
    rows = {e["t"]: e["row"] for e in out if e["k"] == "sample"}
    assert rows[12_000][6] is None and rows[12_000][7] is None         # microprice and spread: none
    assert rows[13_000][6] is None
    assert rows[14_000][6] is not None


def test_a_print_before_any_book_is_harmless():
    tr = BookTracker(TICK)
    assert tr.on_print(1000, 100.0, 5, BUY) == []
    out = tr.on_book(2000, *book()) + tr.flush(4000)
    ts = [e["row"][0] for e in out if e["k"] == "sample"]
    assert ts and ts == sorted(set(ts))                                # ascending, one row a second


def _two_walls(tr):
    """warm, then a bid wall and an ask wall that are old enough to be shown; returns (events, t of the last line)."""
    ev = warm(tr, 12)
    t = 12_000
    walls = book(big={('b', 3): 200, ('a', 3): 200})
    ev += tr.on_book(t, *walls)
    ev += tr.on_book(t + 3500, *walls)
    return ev, t + 3500, walls


def test_an_empty_book_line_is_no_information_for_open_episodes():
    tr = BookTracker(TICK)
    ev, t, walls = _two_walls(tr)
    shown = {e["id"]: e["t0"] for e in eps(ev)}
    assert len(shown) == 2 and {e["s"] for e in eps(ev)} == {"b", "a"}
    mid = tr.on_book(t + 500, [], [])                                  # a transient empty snapshot
    mid += tr.on_book(t + 1000, *walls)                                # the same book again
    assert [e for e in eps(mid) if e["end"] != "open"] == []           # nothing pulled / faded by the gap
    assert [e for e in eps(mid) if e["id"] not in shown or e["t0"] != shown[e["id"]]] == []
    end = eps(tr.finish())
    assert {e["id"]: e["t0"] for e in end} == shown                    # same two episodes, t0 unchanged, none re-opened
    assert {e["end"] for e in end} == {"faded"}


def test_a_one_sided_book_line_keeps_the_missing_side_and_updates_the_other():
    tr = BookTracker(TICK)
    ev, t, walls = _two_walls(tr)
    shown = {e["id"]: (e["s"], e["t0"]) for e in eps(ev)}
    bids_plain = book()[0]
    mid = tr.on_book(t + 500, bids_plain, [])                          # offers empty; the bid wall is really gone
    ended = [e for e in eps(mid) if e["end"] != "open"]
    assert len(ended) == 1 and ended[0]["s"] == "b" and ended[0]["end"] in ("pulled", "faded")
    assert [e for e in eps(mid) if e["s"] == "a"] == []                # the ask wall: untouched
    mid = tr.on_book(t + 1000, *walls)                                 # book returns with the ask wall still there
    assert [e for e in eps(mid) if e["s"] == "a" and (e["end"] != "open" or e["id"] not in shown)] == []
    ask = [e for e in eps(tr.finish()) if e["s"] == "a"]
    assert len(ask) == 1 and shown[ask[0]["id"]] == ("a", ask[0]["t0"])   # same id and t0 as when first shown


def _rest_30s(tr, t0=12_000):
    """A 200-lot bid two ticks under the touch for 30 s, a line a second; returns (events, last stamp)."""
    ev = []
    for s in range(31):
        ev += tr.on_book(t0 + s * 1000, *book(big={('b', 2): 200}))
    return ev, t0 + 30_000

def test_a_feed_gap_closes_open_levels_as_faded_at_the_last_stamp_never_pulled():
    tr = BookTracker(TICK)
    warm(tr, 12)
    ev, last = _rest_30s(tr)
    assert eps(ev) and eps(ev)[-1]["end"] == "open"
    ev = tr.on_book(last + 600_000, *book())                    # the feed was down 10 minutes; the level is not there
    e = [x for x in eps(ev) if x["end"] != "open"]
    assert len(e) == 1 and e[0]["end"] == "faded" and e[0]["t1"] == last
    assert all(x["end"] != "pulled" for x in eps(ev))

def test_a_print_after_a_feed_gap_closes_open_levels_too_and_the_median_window_restarts():
    tr = BookTracker(TICK)
    warm(tr, 12)
    ev, last = _rest_30s(tr)
    ev = tr.on_print(last + 600_000, 100.0 - 2 * TICK, 5, SELL)
    e = eps(ev)
    assert len(e) == 1 and e[0]["end"] == "faded" and e[0]["t1"] == last and e[0]["tr"] == 0
    # no median until 10 s of books after the gap: a big level there opens nothing
    ev = []
    for s in range(5):
        ev += tr.on_book(last + 601_000 + s * 1000, *book(big={('b', 3): 300}))
    assert eps(ev) == []
    assert tr._eps == {}

def test_a_quiet_book_under_a_minute_is_not_a_feed_gap():
    tr = BookTracker(TICK)
    warm(tr, 12)
    ev, last = _rest_30s(tr)
    walls = book(big={('b', 2): 200})
    ev = tr.on_book(last + 40_000, *walls)                      # a quiet overnight book: 40 s with no change at all
    assert [x for x in eps(ev) if x["end"] != "open"] == []     # the resting level is still there, not faded


def test_a_short_gap_is_not_a_feed_gap():
    tr = BookTracker(TICK)
    warm(tr, 12)
    ev, last = _rest_30s(tr)
    ev = tr.on_book(last + 5_000, *book())                      # 5 s of nothing, then the level is gone: still pulled
    e = [x for x in eps(ev) if x["end"] != "open"]
    assert len(e) == 1 and e[0]["end"] == "pulled" and e[0]["t1"] == last + 5_000


# ---- icebergs: a level that is hit again and again and keeps showing size

def _hit_and_reload(tr, t, n, size=10, px=100.0, side=SELL, shown_after=2, lvl=('b', 0)):
    """n times: a print of `size` at the level, the book shows it nearly empty, then full again."""
    ev = []
    for k in range(n):
        tk = t + k * 1000
        ev += tr.on_print(tk, px, size, side)
        ev += tr.on_book(tk + 100, *book(big={lvl: shown_after}))
        ev += tr.on_book(tk + 500, *book())
    return ev, t + n * 1000

def ices(ev): return [e for e in eps(ev) if "rl" in e]

def test_iceberg_flagged_when_a_level_is_hit_again_and_again_and_reloads():
    tr = BookTracker(TICK)
    warm(tr, 12)
    ev, t = _hit_and_reload(tr, 13_000, 10)               # 100 contracts into a level that shows 10
    ic = ices(ev)
    assert ic and ic[0]["s"] == "b" and ic[0]["p"] == 100.0 and ic[0]["id"].startswith("ib")
    assert ic[0]["end"] == "open" and ic[0]["t1"] is None and ic[0]["r"] == 0.0 and ic[0]["ab"] is None
    assert ic[0]["pk"] == 10 and ic[0]["tr"] >= 30 and ic[0]["rl"] >= 2        # flagged at 3x what it showed
    assert ic[-1]["tr"] >= 60                                                  # sent again when its total doubled

def test_an_iceberg_is_never_taken_for_a_wall_or_an_absorption():
    tr = BookTracker(TICK)
    warm(tr, 12)
    ev, _ = _hit_and_reload(tr, 13_000, 10)
    assert all(e["r"] < 1 and e["ab"] is None for e in ices(ev))
    assert [e for e in eps(ev) if "rl" not in e] == []     # no big-level episode came of it

def test_no_iceberg_for_a_level_that_is_simply_eaten():
    tr = BookTracker(TICK)
    warm(tr, 12)
    ev = tr.on_print(13_000, 100.0, 10, SELL)
    ev += tr.on_book(13_100, *book(big={('b', 0): 0}))     # gone
    ev += tr.on_print(13_200, 100.0 - TICK, 90, SELL)
    assert ices(ev) == []

def test_no_iceberg_without_reloads_even_if_much_traded():
    tr = BookTracker(TICK)
    warm(tr, 12)
    ev = []
    for k in range(10):
        ev += tr.on_print(13_000 + k * 100, 100.0, 10, SELL)    # 100 traded, the book never showed a reload
        ev += tr.on_book(13_050 + k * 100, *book())
    assert ices(ev) == []

def test_iceberg_closes_when_price_trades_through_or_the_level_leaves():
    tr = BookTracker(TICK)
    warm(tr, 12)
    ev, t = _hit_and_reload(tr, 13_000, 10)
    assert ices(ev)
    ev = tr.on_print(t + 100, 100.0 - 2 * TICK, 5, SELL)       # 2 ticks through
    done = [e for e in ices(ev) if e["end"] == "ice"]
    assert len(done) == 1 and done[0]["t1"] == t + 100 and done[0]["tr"] >= 80

def test_iceberg_on_the_ask_side_and_buy_prints():
    tr = BookTracker(TICK)
    warm(tr, 12)
    ev, _ = _hit_and_reload(tr, 13_000, 10, px=100.25, side=BUY, lvl=('a', 0))
    ic = ices(ev)
    assert ic and ic[0]["s"] == "a" and ic[0]["p"] == 100.25 and ic[0]["id"].startswith("ia")

def test_iceberg_is_dropped_after_it_goes_idle_and_finish_closes_a_flagged_one():
    tr = BookTracker(TICK)
    warm(tr, 12)
    ev, t = _hit_and_reload(tr, 13_000, 10)
    end = ices(tr.finish(t + 1000))
    assert len(end) == 1 and end[0]["end"] == "ice" and end[0]["t1"] == t + 1000

def test_iceberg_same_input_same_output():
    def run():
        tr = BookTracker(TICK)
        out = warm(tr, 12)
        ev, t = _hit_and_reload(tr, 13_000, 10)
        return out + ev + tr.finish(t + 1000)
    assert run() == run()
