"""homebase.review: the morning review reads the journal only. Task 6 review
minor 4 — a SKIPPED line names the account for an account-level skip
(manual_position / manual_order); a strategy-wide skip (gate_chop) has none
to name and stays as before."""
from __future__ import annotations

import json

import homebase.config as config_mod
from homebase.review import review

DATE = "2026-09-26"


def _write_journal(tmp_path, events):
    p = tmp_path / "journal.jsonl"
    p.write_text("\n".join(json.dumps(e) for e in events) + "\n")


def _patch(monkeypatch, tmp_path):
    monkeypatch.setattr("homebase.review.state_dir", lambda: tmp_path)
    monkeypatch.setattr(config_mod, "config_path", lambda: tmp_path / "config.json")


def test_a_manual_position_skip_names_the_account(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path)
    _write_journal(tmp_path, [
        {"ts": 1, "et": f"{DATE}T09:28:30", "event": "timer_skipped",
         "strategy": "nq930", "reason": "manual_position", "account": "a2", "net": 2},
    ])
    out = review(DATE)
    assert "SKIPPED a2 — manual_position" in out


def test_a_manual_order_skip_names_the_account(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path)
    _write_journal(tmp_path, [
        {"ts": 1, "et": f"{DATE}T09:28:30", "event": "timer_skipped",
         "strategy": "nq930", "reason": "manual_order", "account": "a1", "net": 0,
         "orders": ["7"]},
    ])
    out = review(DATE)
    assert "SKIPPED a1 — manual_order" in out


def test_a_gate_chop_skip_has_no_account_to_name(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path)
    _write_journal(tmp_path, [
        {"ts": 1, "et": f"{DATE}T09:30:00", "event": "timer_skipped",
         "strategy": "nq930", "reason": "gate_chop", "adx": 14.2},
    ])
    out = review(DATE)
    assert "SKIPPED — gate_chop" in out
    assert "SKIPPED a" not in out


def test_a_late_fire_is_a_problem_and_says_when_and_why(tmp_path, monkeypatch):
    """timer.FIRE_LATE_MAX_S: a fire past the open's grace still fires, on the price then --
    and the review never says "PROBLEMS — none" over it."""
    _patch(monkeypatch, tmp_path)
    _write_journal(tmp_path, [
        {"ts": 1, "et": f"{DATE}T09:31:04", "event": "timer_fired", "strategy": "nq930",
         "anchor": 24619.0, "result": True, "note": None, "late": True, "late_s": 64.25,
         "reason": "late_start", "anchor_source": "current"},
        {"ts": 2, "et": f"{DATE}T09:30:02", "event": "timer_fired", "strategy": "ym930",
         "anchor": 46010.0, "result": True, "note": None, "late": True, "late_s": 2.1,
         "reason": "late_fire", "anchor_source": "current"},
    ])
    out = review(DATE)
    assert ("FIRED LATE at 9:31:04, 64.25 s past 09:30:00 — the desk started after the open · "
            "anchor 24619.0, the latest trade then (not the last before the open) · accepted=True") in out
    assert "late fire: nq930 fired at 9:31:04, 64.25 s past 09:30:00 — the desk started after the open" in out
    assert "late fire: ym930 fired at 9:30:02, 2.1 s past 09:30:00 — the fire ran 2.1 s late" in out
    assert "PROBLEMS — none" not in out


def test_an_on_time_fire_is_no_problem(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path)
    _write_journal(tmp_path, [
        {"ts": 1, "et": f"{DATE}T09:30:00", "event": "timer_fired", "strategy": "nq930",
         "anchor": 24500.25, "result": True, "note": None, "late": False, "late_s": 0.002,
         "anchor_source": "pre_open"}])
    out = review(DATE)
    assert "FIRED · anchor 24500.25 · accepted=True" in out and "PROBLEMS — none" in out


def test_a_miss_is_a_problem_and_says_why(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path)
    _write_journal(tmp_path, [
        {"ts": 1, "et": f"{DATE}T11:00:00", "event": "timer_missed", "strategy": "nq930",
         "reason": "late_start", "at": "11:00:00.000", "late_s": 5400.0, "window_end": "09:45"}])
    out = review(DATE)
    assert ("MISSED nq930 — the desk started after the accept window closed (09:45); "
            "nothing placed") in out
    assert "timer_missed: " in out and "PROBLEMS — none" not in out


def test_a_restart_after_the_window_keeps_its_one_line(tmp_path, monkeypatch):
    """Journals from before the miss was said once a day: a line per restart."""
    _patch(monkeypatch, tmp_path)
    _write_journal(tmp_path, [
        {"ts": i, "et": f"{DATE}T{hh}", "event": "timer_missed", "strategy": "nq930",
         "at": hh, "window_end": "09:45"} for i, hh in enumerate(("11:00:00", "23:03:00"))])
    out = review(DATE)
    assert out.count("MISSED the window (service restarted after 09:45)") == 1
    assert out.count("timer_missed: ") == 1
