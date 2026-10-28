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
