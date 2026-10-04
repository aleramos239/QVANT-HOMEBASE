{
 "ok": true,
 "issues": [
  {
   "severity": "minor",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/tests/test_score_verify.py",
   "desc": "The equivalence tests are not safe when two suite runs overlap. The `native` fixture uses one fixed scratch directory (`L/out/_score_verify_tmp`) and deletes it in `finally`, so a second run removes the first run's files. The `files` fixture also re-exports `L/trades/R__*.json` on every run through one shared `.json.tmp` name. This workflow runs several re-checkers that each run the whole suite, so false failures are likely. Fix: use pytest's `tmp_path_factory` (not applied; report only).",
   "evidence": "My first full-suite run (22:15 ET, while another agent's pytest was running) gave 335 passed and 7 errors, all `FileNotFoundError: .../out/_score_verify_tmp/out.json`. Reproduced on purpose: two runs of `tests/test_score_verify.py` started 4 s apart gave `........` for the first and `.EEEEEEE` for the second. Run alone at 22:38-22:41 ET, the whole suite passes (342 of 342)."
  },
  {
   "severity": "minor",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/score.py",
   "desc": "A sim run made with `days=` (a subset) is scored on the full 825-session calendar without any error (the owner's open risk 1). The result dict already carries `sessions`, so `load_trades` could refuse a result whose session count is below the calendar's, but it does not.",
   "evidence": "My timing-only probe run on every third session (`sessions` = 275, `meta.range` 2021-09-22 to 2024-12-31): `score_eval(..., 'apex', micros=60)` gives P5 0.1717 on the default calendar and 0.1882 with `calendar=days`. Nothing is raised."
  },
  {
   "severity": "minor",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/SCORING.md",
   "desc": "The Apex 300K bars for `plus3000` and `plus7600` are fixed cells, not searched, so they understate what the baseline strategy can do from those states. The owner disclosed this. The risk is a candidate's searched pick being compared with an unsearched baseline in the sensitivities. The `fresh` bar (the real account state) is a searched pick and is correct.",
   "evidence": "The `fresh` pick's own cell (donchian-tf15#1 nyam, 100 micros, take 3000 / lock 3000, policy max) scores E$40 2,915 at `plus3000`, above the reported bar of 2,826, and is compliant. A 216-cell `search_funded` at `plus3000` finds a stable pick of 2,932. The `plus7600` bar of 3,427 is likewise an unsearched fixed cell."
  },
  {
   "severity": "minor",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/score.py",
   "desc": "`score_baseline()` does not pass the family metadata (`BASELINE_META`: strategy, inputs, both_sides) to the compliance gate. As a result `out/baseline_insample.json` records the approved Apex 50K PA pick as non-compliant because one direction is UNCHECKED. A report stage reading that JSON could wrongly state that the approved pick fails compliance. `score_baseline_apex300` does pass the metadata.",
   "evidence": "`score_baseline('apex_pa_funded')` returns compliance `{one_direction: UNCHECKED, stop_5x_target: ok, mae_rule: ok}`, compliant False. The same pick scored with its metadata returns all three ok, compliant True, with the same E$40 of 1093.08."
  },
  {
   "severity": "minor",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/score.py",
   "desc": "The price-name pattern in `c2_is_fixed` treats any column with a token such as low, high, open, close, mid, px, price or vwap as fixed. With the default `shuffle_cols=None`, `C2Features` would then leave such a feature real in the null without raising. This is latent: no current data-layer column is affected.",
   "evidence": "`c2_is_fixed` is True for hypothetical feature names `depth_low_pct`, `close_loc`, `open_imb`, `f_vwap_dev`, `high_vol_flag`, `wall_px_dist`, `spread_vs_mid`. For the real table, all 45 feature columns are shuffled and the 17 fixed ones are genuine prices, tags and flags."
  },
  {
   "severity": "minor",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/score.py",
   "desc": "In-memory sources, including an `l2sim.run` result dict (the preferred source), are labelled 'inline'. Every config of a session therefore shares one C1 seed unless the caller passes `label=`. This is documented but not enforced, although the result dict's `meta.strategy` and `meta.inputs` could supply a default name.",
   "evidence": "`lift_vs_control` without a label on two different configs (first_bar_mom and pinbar, sess pm) both use seed 80033. With `label='A'` and `label='B'` the seeds are 45571 and 8365."
  },
  {
   "severity": "minor",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/score.py",
   "desc": "Two properties of the C2 null to keep in mind when reading lifts; neither is a defect against the SPEC. First, the null can trade at a different frequency from the real family, so the lift mixes information with trade count; `ctrl_trades` is returned but nothing warns. Second, the null has about 0.4 percentage points fewer valid feature rows than the real table, as the owner stated.",
   "evidence": "Toy donchian-with-imbalance-filter family at tf5: 770 real nyam trades against 847-899 in five nulls; control P5 0.336-0.380 against real 0.331. Valid-row shares, real then null: `imb10` 0.9157 and 0.9116, `f_delta` 0.9619 and 0.9584."
  },
  {
   "severity": "minor",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/score.py",
   "desc": "`c1_pool()` resolves pools from R's live `ledger.csv` and `jobs.jsonl`, not from R's frozen snapshot. R's job daemon (`hb.py`) is still running, so the pools could change if R adds control runs. They should be pinned in the stage D freeze manifest. Today they are identical to the snapshot.",
   "evidence": "Live catalog and R's pass-3 snapshot both hold 110 exit profiles with 0 differing pools. No live control source has a run range reaching 2025. `R/progress.md` was rewritten by `hb.py` (pid 85410) at 22:36 ET; neither score.py nor my scripts write to it."
  }
 ],
 "summary": "**The score component holds up: no blocker or major issue, eight minor ones, and the whole suite passes (342 of 342) when run alone.** My first suite run showed 7 errors, caused by a second agent's suite run deleting a shared scratch directory; that is the first issue in the list.\n\n## Equivalence\nI wrote my own native reference that never imports score.py and takes a different route through R than the one score.py wraps (`evalcore.build` \u2192 `walk` \u2192 `race`, `funded.evaluate_funded`, `apex300.evaluate_funded`, `a3p3.search3`, `funded.search`, `wf_offline.task`).\n\n- **Bundles nobody used before:** ib-tf15#7, pinbar-tf5#13, vwap_z-tf5#4, gap-tf15#2, vwap_flip-tf1#5, first_bar_mom-tf15#6, and the donchian-tf15 and tema_slope-tf30 screen runs, with tf15 and tf1 control pools and my own seeds.\n- **Result:** 8,919 values compared, 0 mismatches. That covers 70 eval cases (5 firms \u00d7 3 breach models, single and multi-session, 2- and 3-member portfolios), 20 odd-rule and news cases, 45 funded cases, 36 Apex 300K / 50K cases across the three start states, 5 C1 lifts, 6 rule searches and 3 funded searches. Five source types were rotated (path, list, `{'path'}`, `file:`, `{'trades'}`).\n- **Negative control:** a one-tick change on one trade per bundle produced 133 mismatches across 33 cases.\n- **Walk-forward:** a 3-cell family grid on 2 firms with controls is identical to R's `wf_offline.task` plus `agg_task`.\n- **Baseline:** `out/baseline_insample.json` reproduces exactly from R's native bundles, including the 7,680-row Apex 300K grid search (233 s on 6 workers). The six approved picks match R's frozen manifest; three funded E$40 values differ only in the 12th decimal.\n- **Other paths:** member-list search, a bundle directory with a shorter run range, and `apex300.search` at non-fresh starts all match.\n\n## Controls\n- **C2 on the real in-sample features** (5 column sets \u00d7 5 seeds):\n  - every one of the 825 sim sessions with a live shuffled feature gets a donor, and the map is a bijection with in-sample donors only;\n  - every null value equals the real value of the donor session at the same minute;\n  - prices, tags and flags are untouched, and no session keeps a live real feature;\n  - a scan of column combinations found no single-session group that would keep its own features;\n  - at most 8 sessions have a donor closer than 5 sessions (minimum 3).\n- **C2 end to end through l2sim with my own probes:**\n  - a timing-only probe gives an identical ledger under the null, with lift exactly 0;\n  - a feature-driven probe's 1,529 null trades each saw the donor's value, while `f_c` and `t_utc` stayed the receiving session's own;\n  - its null sides agree with the real sides 50\u201354% of the time;\n  - the donor map is identical across worker processes and under three hash seeds.\n- **Guards:** shuffling a price, tag or flag column is refused, and so is leaving a feature real without `allow_partial`. `strata=\"year\"` gives same-year donors.\n- **C1:** per (date, session) trade counts match the config, no pool trade is reused within a draw, fallbacks come from the same session, and pools are in-sample. An empty control counts as never passing.\n- **Calendar and seal:** the 825 sessions are identical across R's cache, the tape store, `Ctx.calendar`, `l2sim.sessions` and `apex300.default_calendar`. Twelve entry points raise on synthetic 2025 rows. The Apex gate fails closed.\n\n## Housekeeping\nThe documented SCORING.md workflow and the CLI run as written. No 2025+ row was read, nothing was committed, R was not touched, and nothing of mine is left under the pilot directory.\n\nMy scripts are in the scratchpad, `/private/tmp/claude-501/-Users-ramoscapital-Library-Application-Support-Claude-scratch-workspaces-bede25d7-4e1b-4b3e-b8ef-70c7ef831e62-9ebb0405-7969-47e0-923d-777091be95f0-scratch-2026-09-30-896b12/db1f7d1a-1c40-4988-9502-1482f7a31fc2/scratchpad/v/`: `nat.py`, `fil.py`, `c2chk.py`, `c2e2e.py`, `c2scan.py`, `c1chk.py`, `wf_nat.py`, `wf_fil.py`, `misc.py`, `misc2.py`, `base300.py`, `doc.py`."
}