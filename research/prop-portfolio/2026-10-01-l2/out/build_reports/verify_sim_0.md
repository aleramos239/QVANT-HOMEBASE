{
 "ok": true,
 "issues": [
  {
   "severity": "minor",
   "desc": "l2sim.Strategy.__init__ does not validate or coerce inputs the way the tester's resolve_inputs does (only unknown keys raise). A mistyped value runs silently in the sim where the tester would refuse it, so a screening config with a bad choice can produce an empty or odd trade list without any error.",
   "evidence": "l2ref.Donchian accepted {'tf': 15}, {'n': 20.7}, {'stop_val': -3.0}, {'dir': 'sideways'} and {'max_tr': 0} without raising. With dir='sideways', Template.allowed() returns False for both sides, so the run would have zero trades. Tester: homebase/strategies/base.py resolve_inputs raises on wrong type, choice or range.",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/l2sim.py"
  },
  {
   "severity": "minor",
   "desc": "No tester bundle exists for several Template paths the new L2 families will use: struct stops, trail_atr, exit_bars, f_trend/f_vwap, dir long/short, news_only=True, and the new _lim limit-entry helper (which has no counterpart in R/template.py). Their fidelity rests on code identity and engine differential tests, not on a trade-for-trade bundle match.",
   "evidence": "Every in-sample tester job for straddle/orb/donchian in R/jobs.jsonl uses dir=both, filters off, trail_atr=0, exit_bars=0, news_only=False, stop_mode atr or pts. Mitigation I checked: an AST diff of l2sim.Template against R/template.py shows 32 methods identical except tag passthrough and ROLLS -> self.ROLLS; the l2ref families are identical except the NEWS source, and the 104 in-sample news days equal the draft's embedded map.",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/l2sim.py"
  },
  {
   "severity": "minor",
   "desc": "The gate strategies never read ctx.daily (prior-day H/L/C, daily ATR), so that path is not covered by the bundle match. The daily values themselves are correct, but a sub-range run would differ slightly from the tester for a family using datr(): the tester truncates daily history to 400 days before the range start, l2sim passes all prior in-sample days.",
   "evidence": "cache/daily_NQ.json: 825 rows, 0 differ from the tester tape-cache header daily {h,l,c} and contract; the 13 derived roll dates equal the draft's ROLLS list. Tester lookback: homebase/backtest/runner.py DAILY_LOOKBACK = 400 days; l2sim _run_days uses daily[:bisect_left(dates, iso)].",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/l2sim.py"
  },
  {
   "severity": "minor",
   "desc": "Template.ROLLS is only filled in by run/run_many. A Template strategy driven through run_session directly keeps the empty default, so prior-day levels are not dropped on contract-roll days.",
   "evidence": "l2sim.py: class attribute `ROLLS: frozenset = frozenset()`; _run_days sets `st.ROLLS = roll_set` only when roll_set is not None. The builder's own differential test has to set s.ROLLS by hand.",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/l2sim.py"
  },
  {
   "severity": "minor",
   "desc": "A strategy exception propagates and aborts the l2sim run; the tester instead drops that session and counts it under skipped_by_error. Coverage counts would differ for a family that crashes on some days. The builder already flagged this.",
   "evidence": "Tester engine.py run_session wraps the callbacks in try/except and sets skip='strategy error: ...'; l2sim.run_session has no such handler.",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/l2sim.py"
  },
  {
   "severity": "minor",
   "desc": "On CME half days a position still open at the 13:15 ET clamp exits as 'eod' at the last print BEFORE 13:15 (minus/plus one tick), not at a print at or after the close. This is the tester's convention, reproduced exactly; it affects 6 trades per gate config.",
   "evidence": "All 12 eod trades of straddle#10 and orb#10 (2021-11-26, 2022-11-25, 2023-07-03, 2023-11-24, 2024-07-03, 2024-11-29, 2024-12-24): exit_ms equals the last print before 13:15 ET (0.37-1.37 s earlier) and exit price equals that print -/+ 0.25.",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/SIM_VALIDATION.md"
  }
 ],
 "summary": "FIDELITY verdict: PASS. The builder's match rates and net diffs are confirmed, no blocker or major issue, and no mismatches to inspect: every comparison came out identical.\n\n**Gate recompute (my own loader, comparator and session split; exact entry_ms rather than the builder's \u00b11 s):**\n\n| config | scope | tester / sim trades | identical on all 20 fields, same order | tester net = sim net |\n|---|---|---|---|---|\n| hm2-straddle-tf30#10 | all / nyam | 3273 / 820 | 3273 / 820 | +141,158 / +95,315 |\n| hm-orb-tf5#10 | all / mid | 3272 / 820 | 3272 / 820 | +16,152 / +62,610 |\n| fp-donchian-tf15#10 | all / pm | 3571 / 760 | 3571 / 760 | \u22128,064 / +26,940 |\n\nNet diff is $0.00 in every row. Sessions are 825 with 820 used, and the 5 skipped days carry the same reason strings as the tester.\n\n**Params are the exact tester params:**\n- Inputs, qty 1, commission 4.0 and slippage 1 tick are read from each bundle's run.json; placement latency is 85 ms on both sides.\n- The grid ids and cell inputs match R/jobs.jsonl and R/out/funded_summary.md; fp-donchian-tf15#10 (pts 30, tgt_r 0.6) is indeed Pro DLL funded #1.\n- Passing only {tf, sess} resolves to the tester's full resolved inputs for all three families, so the defaults agree.\n\n**Checks beyond what the builder ran:**\n- **Verbatim tester code on the sim engine:** the draft_source stored in each gate bundle, run on l2sim with one worker, is identical to the bundle for all three. This separates the engine/tape port from the l2ref strategy port.\n- **Bundles the builder did not use:** 13 single runs (12 screen runs at tf 1/5/15/30 plus the rollcheck) and 7 other grids, 221 cells and 1,062,453 trades, all identical. Four walk-forward grids with a single session (pm, mid, nyam), 136 cells and 95,631 trades, all identical.\n- **The builder's 88 source-grid cells:** 88 of 88 identical, 310,706 trades.\n- **Fill law from scratch on the raw tape (no engine code):** every non-eod gate trade's entry and exit re-derived with zero deviations; this covers market and stop entries, SL, TP trade-through, SL-first ties, session-end flatten, P&L and MAE/MFE. The 12 eod trades were checked separately and also agree.\n- **Engine differential fuzz of my own:** 340 cases and 16,265 trades against the tester's engine (imported read-only, no bytecode written), with zero divergences. It includes qty above 1, wrong-side brackets, marketable limits, 3-leg OCO, latency 0/85/2000 ms, slippage 0/1/2 ticks, bar sizes 0/1/5/15 and half days.\n- **Tape identity:** the ofb_tick parquet equals the tester tape cache on 825 of 825 in-sample sessions.\n- **Negative controls:** slippage 0 gives 0% match (+28,469 net); latency 0 gives 20.99% on exact ms, which equals the builder's all-fields figure (their 32.24% is the \u00b11 s number); commission 5 changes net only.\n- **Other:** a sub-range run equals the bundle slice; the holdout seal raises on all four entry points I tried; the builder's 60 sim tests pass (46.65 s); the code hashes equal those printed in SIM_VALIDATION.md.\n\nI did not run the other agents' test files (the builder reported 5 failures in test_apex300.py on one full run). I wrote nothing outside the scratchpad, read no 2025+ row, and changed nothing in the pilot directory.\n\nMy scripts are in `/private/tmp/claude-501/-Users-ramoscapital-Library-Application-Support-Claude-scratch-workspaces-bede25d7-4e1b-4b3e-b8ef-70c7ef831e62-9ebb0405-7969-47e0-923d-777091be95f0-scratch-2026-09-30-896b12/db1f7d1a-1c40-4988-9502-1482f7a31fc2/scratchpad/vf/` (v1_gate.py, v2_draft.py, v3_other.py, v4_law.py, v5_misc.py, v6_wf.py, v7_news.py, v8_tape_neg.py, v9_fuzz.py, v10_src.py)."
}