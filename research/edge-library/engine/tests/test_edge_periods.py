"""The three periods (EDGE_SPEC user rule 3): constants in ONE place, the EXAM seal, the range recorded in every bundle,
and the period calendars of the scoring layer. No P&L is asserted."""
import datetime as dt
import json

import pytest

import l2ref
import l2sim as S


def test_the_three_periods_are_defined_once_and_do_not_overlap():
    assert S.BUILD == (dt.date(2021, 9, 22), dt.date(2023, 12, 31)) and S.PICK == (dt.date(2024, 1, 1), dt.date(2024, 12, 31))
    assert S.EXAM_START == S.HOLDOUT_START == dt.date(2025, 1, 1) and S.BUILD[1] < S.PICK[0] <= S.PICK[1] < S.EXAM_START
    assert S.IN_SAMPLE == (S.BUILD[0], S.PICK[1]) and S.EXAM_END["NQ_L2"] == dt.date(2026, 7, 8)
    assert S.period("build") == S.BUILD and S.period("PICK") == S.PICK and S.period("insample") == S.IN_SAMPLE
    assert S.period(("2022-01-03", "2022-01-07")) == (dt.date(2022, 1, 3), dt.date(2022, 1, 7))
    with pytest.raises(S.HoldoutSealed):
        S.period("exam")                                       # the EXAM has no name to run by: dates + allow_exam only
    with pytest.raises(KeyError):
        S.period("holdout")
    assert [S.period_of(*x) for x in (S.BUILD, S.PICK, S.IN_SAMPLE, ("2025-01-02", "2025-03-01"), ("2024-12-01", "2025-01-10"),
                                      ("2022-03-01", "2022-03-31"))] == ["build", "pick", "insample", "check", "mixed", "build"]
    assert S.period_of("2026-01-02", "2026-03-01") == "exam"   # 2025 alone is the CHECK year since "PERIODS AMENDED" (test_check_period.py)


@pytest.mark.parametrize("root", ["NQ", "ES", "GC"])
def test_every_loader_raises_on_the_exam_unless_allow_exam(root):
    for fn in (lambda: S.load_tape("2025-01-02", root), lambda: S.sessions("2024-12-01", "2025-01-10", root),
               lambda: S.run(l2ref.Donchian, {"tf": "15"}, "2024-12-01", "2025-01-10", root=root, workers=1),
               lambda: S.run(l2ref.Donchian, {"tf": "15"}, days=["2025-02-03"], root=root, workers=1),
               lambda: S.build_tapes(root, "2024-12-01", "2025-01-10") if root != "NQ" else S.check_exam("2025-01-02")):
        with pytest.raises(S.HoldoutSealed):
            fn()
    S.check_holdout("2025-01-02", True)                         # the explicit switch (the orchestrator's exam stage only)
    assert S.check_exam is S.check_holdout
    with pytest.raises(S.HoldoutSealed):
        S.check_exam("2025-01-02", allow_holdout=1)             # only the literal True opens it


def test_a_run_records_its_range_and_period_and_the_bundle_carries_it(l_tmp):
    r = S.run(l2ref.Donchian, {"tf": "15"}, "2023-03-01", "2023-03-07", workers=1)
    assert r["meta"]["range"] == {"start": "2023-03-01", "end": "2023-03-07", "holdout": False, "period": "build"}
    assert r["meta"]["root"] == "NQ" and r["meta"]["point_value"] == 20.0 and r["meta"]["tick"] == 0.25 and r["meta"]["segments"] == ["day"]
    out = S.write_bundle(r, l_tmp / "b")
    assert json.loads((out / "run.json").read_text())["range"]["period"] == "build"
    with pytest.raises(ValueError):
        S.run(l2ref.Donchian, {"tf": "15"}, "2023-03-01", "2023-03-07", period="build", workers=1)      # one or the other
    p = S.run(l2ref.Donchian, {"tf": "15"}, days=["2023-03-01"], period=None, workers=1)
    assert p["meta"]["range"]["period"] == "insample" and p["meta"]["days_subset"]


def test_period_argument_sets_the_range():
    days = S.sessions(*S.period("build"))
    assert days[0] == S.BUILD[0] and days[-1] <= S.BUILD[1] and len(days) == 573
    assert len(S.sessions(*S.period("pick"))) == 252 and len(S.sessions(*S.period("insample"))) == 825
    r = S.run(l2ref.Donchian, {"tf": "15"}, period="build", days=["2023-03-01"], workers=1)
    assert r["meta"]["range"] == {"start": "2021-09-22", "end": "2023-12-31", "holdout": False, "period": "build"}
    assert S.run(l2ref.Donchian, {"tf": "15"}, period="pick", days=["2024-03-05"], workers=1)["meta"]["range"]["period"] == "pick"


def test_score_builds_the_period_calendars():
    import score
    b, p, a = (score.period_sessions(x) for x in ("build", "pick", "insample"))
    assert b + p == a == score.in_sample_sessions() and (len(b), len(p)) == (573, 252)
    assert b == [d.isoformat() for d in S.sessions(*S.period("build"))] and p == [d.isoformat() for d in S.sessions(*S.period("pick"))]
    assert score.make_calendar("build").iso == b and score.make_calendar("pick").window["sessions"] == 252
    assert score.make_calendar().D == 825                       # the old in-sample calendar stays the default (gates)
    with pytest.raises(score.HoldoutError):
        score.period_sessions("exam")
    with pytest.raises(KeyError):
        score.period_sessions("2024")
    assert score.PERIODS["build"] == tuple(d.isoformat() for d in S.BUILD) and score.PERIODS["pick"] == tuple(d.isoformat() for d in S.PICK)


def test_the_session_tagger_of_scoring_knows_eve_and_pre_and_keeps_the_five():
    import score
    E = score.E
    assert [E.SESS_CODE[k] for k in ("asia", "london", "nyam", "mid", "pm", "pre", "eve")] == [0, 1, 2, 3, 4, 5, 6]
    assert E.SESS["pre"] == (505, 570) and E.SESS["eve"] == (1080, 1439) and score.SESS5 == ("asia", "london", "nyam", "mid", "pm")

    def row(date, hhmm):
        ms = S.et_ns(dt.date.fromisoformat(date), hhmm) // 1_000_000
        return {"date": "2023-03-14", "side": "long", "qty": 1, "entry_price": 100.0, "exit_price": 101.0, "exit_reason": "tp",
                "gross": 20.0, "commission": 4.0, "net": 16.0, "mae_usd": 5.0, "mfe_usd": 20.0, "entry_ms": ms, "exit_ms": ms + 60000}
    rows = [row("2023-03-13", "18:00"), row("2023-03-13", "23:58"), row("2023-03-14", "00:00"), row("2023-03-14", "03:00"),
            row("2023-03-14", "08:25"), row("2023-03-14", "08:30"), row("2023-03-14", "09:30"), row("2023-03-14", "11:05"),
            row("2023-03-14", "13:30"), row("2023-03-14", "16:05")]
    t = score.load_trades(rows)
    assert t.sess.tolist() == [6, 6, 0, 1, 5, 5, 2, 3, 4, -1]
    assert [S.session_of(r["entry_ms"]) for r in rows] == ["eve", "eve", "asia", "london", "pre", "pre", "nyam", "mid", "pm", None]
    assert set(t.iso) == {"2023-03-14"}                          # an evening trade is scored on the trade date it belongs to
    assert score._mask(t, "eve", "all").sum() == 2 and score._mask(t, "pre+nyam", "all").sum() == 3
