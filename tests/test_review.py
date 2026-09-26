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
