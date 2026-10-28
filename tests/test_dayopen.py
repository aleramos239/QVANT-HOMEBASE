from homebase.desk import dayopen


def test_the_first_balance_of_a_day_is_its_open_and_the_pnl_reads_off_it(tmp_path):
    p = tmp_path / "day_open.json"
    assert dayopen.day_pnl(p, "A", 100.0, "2026-10-28") is None          # no open yet
    dayopen.note(p, "A", 1000.0, "2026-10-28")
    dayopen.note(p, "A", 1250.5, "2026-10-28")                           # a later note never moves the open
    assert dayopen.day_pnl(p, "A", 1250.5, "2026-10-28") == 250.5
    assert dayopen.day_pnl(p, "A", 900.0, "2026-10-28") == -100.0


def test_a_new_desk_day_opens_again_and_an_old_open_is_not_used(tmp_path):
    p = tmp_path / "day_open.json"
    dayopen.note(p, "A", 1000.0, "2026-10-28")
    assert dayopen.day_pnl(p, "A", 1300.0, "2026-10-29") is None
    dayopen.note(p, "A", 1300.0, "2026-10-29")
    assert dayopen.day_pnl(p, "A", 1300.0, "2026-10-29") == 0.0
    assert dayopen.day_pnl(p, "B", 5.0, "2026-10-29") is None            # another account: its own open


def test_no_balance_writes_nothing(tmp_path):
    p = tmp_path / "day_open.json"
    dayopen.note(p, "A", None, "2026-10-28")
    assert not p.exists()


def test_the_open_is_the_balance_the_day_before_closed_with_and_a_note_without_it_is_replaced_once(tmp_path):
    p = tmp_path / "day_open.json"
    by_day = {"2026-10-26": 900.0, "2026-10-27": 1000.0, "2026-10-28": 1100.0}
    assert dayopen.prior_close(by_day, "2026-10-28") == 1000.0
    assert dayopen.prior_close(by_day, "2026-10-26") is None
    dayopen.note(p, "A", 1100.0, "2026-10-28")                          # an older desk wrote the first balance seen
    dayopen.note(p, "A", 1100.0, "2026-10-28", 1000.0)                  # replaced by the real open
    assert dayopen.day_pnl(p, "A", 1100.0, "2026-10-28") == 100.0
    dayopen.note(p, "A", 1300.0, "2026-10-28", 1010.0)                  # then fixed for the day
    assert dayopen.day_pnl(p, "A", 1300.0, "2026-10-28") == 300.0
