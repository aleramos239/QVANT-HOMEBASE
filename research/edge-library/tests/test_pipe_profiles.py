"""test_pipe_profiles.py -- the pipelines to choose from (owner, 2026-10-13): LIVE PIPELINE (templates/pipeline.json, as it was) and WR PIPELINE
(templates/pipeline_wr.json: high win rate, low reward-to-risk). Chosen by HB_PIPELINE or the state file; no word = live."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

W = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(W))
from blueprint import pipe_rules as P  # noqa: E402
from blueprint import rules as R  # noqa: E402


def test_live_is_the_default_and_keeps_the_lane_on_two_named_cards_only(monkeypatch):
    monkeypatch.delenv("HB_PIPELINE")
    P._all.cache_clear()
    assert P.active() == "live" and P.label() == "LIVE PIPELINE"
    assert P.winlane("nq_ib_break_nyam_wl_a5-NQ-tf5") == "ask" and P.winlane("nq_donch_first_nyam_slow_a5-NQ-tf5") == "off"
    assert "max_target_r" not in P.need("winlane")


def test_wr_asks_the_lane_on_every_card_with_a_low_target_and_shows_eval_odds(monkeypatch):
    monkeypatch.setenv("HB_PIPELINE", "wr")
    P._all.cache_clear()
    assert P.active() == "wr" and P.label() == "WR PIPELINE"
    assert P.winlane("nq_donch_first_nyam_slow_a5-NQ-tf5") == "ask" and P.winlane() == "ask"
    assert P.need("winlane", "max_target_r") == 1.0 and P.need("winlane", "risk_usd") == [500, 800]


def test_use_writes_the_state_file_and_the_environment_wins(monkeypatch):
    monkeypatch.delenv("HB_PIPELINE")
    assert P.use("wr") == "wr" and P.active() == "wr" and P.STATE.read_text().strip() == "wr"
    monkeypatch.setenv("HB_PIPELINE", "live")
    assert P.active() == "live"
    with pytest.raises(R.RuleError, match="one of live, wr, payout"):
        P.use("fast")


def test_both_files_load_and_agree_with_the_law(monkeypatch):
    for name in P.PROFILES:
        monkeypatch.setenv("HB_PIPELINE", name)
        P._all.cache_clear()
        assert P.mode() == "variant" and P.need("raw", "strict", "share") == R.need("2.1")
