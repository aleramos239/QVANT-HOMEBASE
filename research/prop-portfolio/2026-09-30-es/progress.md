# ES prop-portfolio pilot: progress (read me first on resume)

Brief: same research as the NQ pilot (../2026-09-29/progress.md) on root ES. Spec: SPEC.md (diff vs NQ). Ledger: ledger.csv. Jobs:
jobs.jsonl. Driver log: ../2026-09-29/hb.log (one daemon for both pilots).
USER PRIORITIES: evals = high pass % fast (P(pass <= k days)); funded = high payout %, high payout, short time to payout.
Apex UNCONFIRMED everywhere (PA rules forbid OCO/both-side orders, stop > 5x target, threshold as stop: compliance filters).

## Stage log
- [x] 1 Parameterise (2026-09-30): pilot.py (PP_PILOT / --pilot / PP_DIR), evalcore + all analysis scripts use PL.DIR / PL.ROOT / ES $ constants;
  gen_drafts.py, localcheck.py, hb.py multi-pilot. NQ defaults unchanged: 107 existing tests pass (+ test_pilot.py), hb dry-run 26/26,
  NQ drafts regenerate byte-identically. 21 pp_es_<fam> drafts generated, 21/21 load, localcheck ES ALL OK.
- [x] 2 hb.py multi-pilot: one daemon restarted 17:05 ET, re-attached to the two running NQ walk-forwards (wf-squeeze-tf5-mid,
  wf-orb-tf5-nyam-fp); NQ jobs.jsonl unchanged.
- [x] 3 smoke: 21 families (incl. random), 2024-03-04..15, sess all, tf5: 21/21 done, every family trades (mid_fade 4, gap 6, ib 15 ... ema_pullback 99).
  ~21 s per run wall (4 at a time). The ES tape cache (825 sessions, 7.2 GB in ~/futures_derived/homebase_tape/ES) was ALREADY built
  17:03-17:05 ET (~97 s total, not by these jobs), so no cold-cache cost was observed.
- [x] 4 calibrate (warm cache): full 2021-09-22..2024-12-31 ema_pullback tf5 all = 41 s (NQ 23 s), 7,873 trades, net -$266.9k at 1 ES
  (friction: $4 + 2 ticks x $12.50 = $29 RT vs NQ $14). 20-cell orb heat-map (tf x stop_val) = 320 s (NQ 244 s), 16 s/cell; all 20 cells
  net negative at 1 ES (-$102k..-$174k). ES costs ~2x NQ per contract: expect far fewer survivors than NQ.
- [x] 5 screen (80) + ctrl (36): all done 18:24 ET (2 of 4 slots when shared with the NQ daemon, ~2-3 jobs/min).
- [x] 6 screen analysis (PP_PILOT=es screen_analyze.py, screen_lift_daymatched.py): out/screen_table.csv, screen_summary.md, screen_lift_daymatched.csv.
  ES: 0 of 252 (>=300 trades) configs with t>=2 (NQ 2), 8 with net>0 at 1 ES (NQ 72); best donchian/15/pm t1.72 PF1.22 +$27.9k (all of it 2022).
- [x] 7 pass-1 style rules search with take rules, 5 firms, 3 breach models, day-matched ctrl + null: R/a3p3_screen.py (snap|quick|real|null) ->
  out/a3p3s_quick.csv, a3p3s_rules.csv (6,300 rows), a3p3s_null.csv (2,700 rows), a3_es_summary.md (summary_es.py). 252 configs x 5 firms, ~25 min on 4 workers
  (load ~20 from other agents). Best stable P5 (primary model): Lucid Flex .43 (realized; null max .39), LucidPro .40, ProNoDLL .51, Apex(intraday, compliant) .35, apex_eod .37;
  ES median/max eod P5 Lucid .18/.43 vs NQ .42/.61, Apex .50/.68 vs NQ .72/.81 -> ES is much harder (friction 2x, no positive-expectancy edge).
- [~] 8 ES tuning queued 18:30 ET (tune1.jsonl, 43 jobs, 798 cells; controls first): hm-* heat-maps on top 13 family x tf (vwap_flip/15, tema_slope/30,
  donchian/15, first_bar_mom/30, tod_drift/5, vwap_z/5, donchian/30, vwap_flip/5, tema_slope/15, tod_drift/15, ema_pullback/30, straddle/15, ema_pullback/5),
  fp-* fast-pass (stop pts {3,6,10,15} x tgt_r {.25,.4,.6,1}) on the top 6 (vwap_flip/15, tema_slope/30, donchian/15, first_bar_mom/30, tod_drift/5, vwap_z/5),
  hmctrl-random(tod) / fpctrl-random seeds 11-13 / 21-23. Picks: out/tune_picks.json (rank by t-stat + day-matched lift). NEXT: a3p3 on hm-/fp- cells once done
  (NOTE a3p3.py reads out/a3p3_snap_* : take that snapshot AFTER the tuning jobs finish; a3p3s snapshot is separate).

  2026-09-30 19:55 ET: the 6 hmctrl-randomtod grids (single exit_bars axis) were refused by the tester ("axes: 2 or 3 parameters"); resubmitted as
  hmctrl2-randomtod-tf{5,15}-s{11,12,13} (tune1b.jsonl) with axes exit_bars {6,12,24} x dir {long,short} (6 cells each; matches the tod_drift heat-map
  exit/dir axes). Tuning still running (sizing: 1 done, 4 running, 14+6 queued at 19:55). screen_summary.md / a3_es_summary.md are written (19:03).

## 2026-10-01 (02:30 ET) ES pass 3 (a3p3 under PP_PILOT=es) + WF candidates
- fast-pass: the 6 ES fp grids existed; added the NQ-equivalent rest (fp_ext.jsonl: rsi2/5, ema_pullback/5, tema_slope/5, vwap_flip/5, orb/5, straddle/30; vwap_flip/1 skipped, no tf1 control pool)
  -> all done 22:33 ET (cells 932/3000, runs 116/400). Snapshot out/a3p3_snap_* taken AFTER them; a3p3.py NEW_PFX = hm-/fp- for ES (hm2- for NQ).
- a3p3 real (--all-hm2, ES has few net>0): 2,535 configs (>=300 trades) x 5 firms x 3 breach models x 3,600 rule cells, K=10 day-matched controls -> out/a3p3_rules.csv (63,375 rows),
  null 422 pseudo-configs -> a3p3_null.csv; screen configs re-scored earlier (a3p3s_*, folded in as "pass 2"). a3p3_merge.py (ES-aware) -> out/candidates.csv (13,935 rows)
  + out/a3p3_summary.md. Added columns comp_oco / comp_target / apex_compliant / mae750_share / apex_mae_ok / apex_thr_stop / pos_years.
- RESULT (primary model; eod | intraday bounds): best P5 Flex .49 (.49|.15), LP+DLL .40 (.40|.36), LP noDLL .58 (.58|.34; P1 .38, P3 .54), Apex .38 (.49|.38, UNCONF), ApexEOD .37 (.37|.37, UNCONF).
  NONE reaches .60. Every best sits at/below the zero-edge optimised null max (.40/.38/.55/.35/.35) -> the rules grid, not the edge, drives P5. Flex P1 is structurally 0.
  Real edge (positive-expectancy): donchian tf15/tf30 PM only (net +$43k/+$30k at 1 ES, 2022-heavy).
- APEX MAE-cut bound (a3p3_apexmae.py): at the optimal sizes 72-85% of trades reach the $750 PA negative-P&L floor; capping size so <=2% do -> P5 <= .05 (median ~.00). Apex on ES is not workable.
- offline quarterly WF (wf_offline.py --pass3 --screen --top 12; 60 tasks, kc 5): OOS P5 median Flex .41, LP+ .34, LP0 .47, Apex(intr) .35, AEOD .34; IS->OOS drop +.01..+.04.
  (WF lift is inflated for fp/multi-cell grids: control = first member's exit profile. Read OOS P5 + drop.)
- 15 tester WFs chosen with wf_pick.py (top by primary P5 / P1(P3 for Flex) across firms, distinct family/tf/session, 5 slots positive-expectancy) and submitted via hb.py (wf_es.jsonl, ES cap 15/15):
  straddle-tf15-pm, straddle-tf15-nyam, donchian-tf15-pm, rsi2-tf5-nyam-fp, straddle-tf30-pm, tod_drift-tf5-nyam-fp, tod_drift-tf5-pm-fp, vwap_flip-tf5-pm, rsi2-tf5-nyam, tod_drift-tf15-nyam,
  first_bar_mom-tf30-pm, tod_drift-tf5-nyam, donchian-tf30-pm, ib-tf30-pm, vwap_z-tf5-mid.
  Stitched OOS (1 ES, raw P&L; tester): POSITIVE donchian-tf15-pm +$22.6k PF 1.16 (660 tr), donchian-tf30-pm +$15.9k PF 1.16 (456 tr); ~flat straddle-tf30-pm +$1.7k, vwap_flip-tf5-pm +$1.1k; 11 negative (rsi2 -$33k/-$39k, ib -$25k, straddle-tf15-nyam -$21k...).
- code touched (research dir only): a3p3.py (NEW_PFX), a3p3_merge.py (ES), wf_offline.py (--screen), new wf_pick.py, a3p3_apexmae.py. 280 tests pass.

## 2026-10-01 (10:30 ET) ES Stage B portfolio + funded + tester WF table (a3p3 -> portfolio_final / funded_search under PP_PILOT=es)
- Code (research dir only): portfolio.py (pass-2 snapshot ES = a3p3s_snap; PP_APEX_COMPLIANT=1 restricts the Apex day_stop grid to {0,1000}), portfolio_final.py (L2/J2 from portfolio.py; Apex pools restricted to apex_compliant and apex_thr_stop=0 when PP_APEX_COMPLIANT=1; new `rs` command),
  funded_merge.py (pilot-aware title, same-config line = HEADLINE), new funded_headline.py, apex_mae_port.py, wf_table.py. Chains: run_chain1b.sh / run_chain2b.sh. 280 tests pass; NQ defaults unchanged.
- Stage B (out/portfolio_summary.md, portfolio_members.md, portfolio_results.json): NO firm reaches 60%. P5 single / best2 / >=3: Flex .493/.520/.532, LP+DLL .406/.417/.414, LP noDLL .577/.538/.524, Apex .341/.341/.380, Apex EOD .357/.353/.370 (primary model).
  Re-selecting WF OOS (look-ahead audit identical on truncated data): .466/.323/.455/.312/.316. >=3 sets are forced and flagged (NEGATIVE_EXEC_MEMBER / DEAD_MEMBERS) -> report singles + multi-account.
  Multi-account (in-sample greedy; [eod|intraday]): N=2 .704, N=3 .825, N=4 .895, N=5 .928, N=6 .966 [.97|.88]; independence approx from WF OOS P5: .63/.75/.87/.91/.95. Apex picks violate the PA MAE rule (58-86% of trades hit $750).
- Funded (out/funded_summary.md, funded_headline.md, funded_candidates.csv, funded_wf.csv, funded_econ.json): ES = about half of NQ. Same-config net per eval purchase: Pro noDLL +1,457 (donchian-tf15-pm; eval P5 .57; E$40 2,723, P20 49%, median 6d; intraday-breach bound E$40 189), Flex +670 / +575, Flex+DLL +572, Pro DLL +422, Apex +40
  (Apex funded E$40 382 = null max 379). WF-based: +605/+415/+534/+398/-37. Null max E$40: 1,302/1,037/1,081/1,751/379. Lucid breach model (realised vs open-P&L) is still the key unknown.
- Tester WF table (out/wf_summary.md): 4/15 positive OOS (donchian-tf15-pm +$22.6k PF 1.16, donchian-tf30-pm +$15.9k PF 1.16; flat straddle-tf30-pm, vwap_flip-tf5-pm); 11 negative. Donchian PM = the only real ES edge.

## 2026-10-01 (~12:30 ET) ES adversarial verification (independent re-walk from raw trades.json; scripts verify_insample_indep.py, verify_funded_insample.py in ../2026-09-29)
- VERDICT: the ES numbers are reproduced exactly; no plumbing error in P&L / costs / controls / WF. Two real defects found (Flex rule grid, Apex compliance gate) -> conclusions unchanged: no ES config reaches P(pass<=5d) 60% (criterion not relaxed).
- Instrument/costs: every trade of every finalist / funded pick source (>70k trades) has gross == (exit-entry) x side x $50 x qty, commission $4 per ES, mae/mfe $ = pts x $50; all walks use $1.25/MES tick (verify_indep.TICK = pilot tick; NQ stays $0.50); stitched tester WF P&L of 4 WFs recomputed from raw trades (donchian-tf15-pm +22,648 PF 1.157 n660; donchian-tf30-pm +15,864; straddle-tf30-pm +1,738; vwap_flip-tf5-pm +1,080) = wf_summary.
- Eval: 68 reports (35 main + 33 fast objective: single / best2 / portfolio / extras x 5 firms) x eod|realized|intraday x P1,P2,P3,P5,bust5 + executed trades + per-member executed net + all multi-account mixes N=2..6 (main and fast) match portfolio_results.json to 1e-9, calendar rebuilt from archive file names (825) equals the scorer's. ONLY exception: the 3-member Apex portfolio (and the N=2 mix containing it) differ by <= .0024 (<= 2 of 821 starts) because 4 trades enter on the SAME millisecond in different members; the scorer orders ties by Base creation counter. Permuting members in the independent walk gives 0 diffs, so this is a tie-break artefact, not an error.
- Funded: top-3 per variant (15 picks) re-derived with an independent lifecycle from FUNDED_RULES.md: 9 metrics + eod/intraday alt E$40 + same-config eval P5 + net per purchase: 0 mismatches (max diff 5e-12). Intraday-bound net/purchase in funded_headline.py is an approximation (alt E$40 x E$60/E$40) within $8 of the exact value.
- Controls: 42 distinct members; every pool 'exact' (tf, stop mode/value, tgt_r, exit_bars, trail identical; ES random draft; qty/commission/slippage/capital identical); per-(date,session) trade counts equal the real member's in every cell (0 shortfall, fallback share <= 3%); same micros + rules; independent lift recomputation = scorer.
- WF look-ahead: truncation test (all trades and sessions on/after 2023-07-01 removed) of wf_offline.task: all 60 tasks x 5 quarters x 2 models = 600 picks identical to the full-data run. Portfolio re-select truncation: author's 4 (lucid, lucidpro_nodll) + 6 new (lucidpro, apex, apex_eod, 2023Q1 + 2024Q2) = 10/10 identical. Funded WF trains only on starts whose 60-session horizon ends before the test quarter (code review). Remaining (known) bias: the candidate pool and the 12 WF family-grid x sessions are chosen on full-window P5; fixed-set WF lift is partly look-ahead.
- DEFECT 1 (Flex rule grid; affects Lucid Flex P2/P3/P5 only): day_take max 1,500 makes a 2-day pass impossible (fill = 1,500 - 1 tick x 40 = $1,450/day, two days $2,900 < $3,000), so 'Flex P2 = 0 structural' was a grid artefact (P1 = 0 IS structural: min 2 days). Adding 1,560 / 1,600 (env PP_FLEX_TAKE_EXT=1, default off, NQ unchanged; portfolio.py + a3_pass2.py): Flex single hm-straddle-tf15#21|pm@40 L750 K1560 TT P1/P2/P3/P5 .00/.39/.43/.510 (was 0/0/.41/.493; eod .51 realized .51 intraday .21 (was .145); lift +.036 CI incl 0); best2 on the fast objective .00/.45/.48/.513 (eod .58; members flagged NEGATIVE_EXEC). Verified 0 mismatches vs the independent walk. The null rises too (61 pseudo-configs: mean .140 -> .161, p95 .313 -> .345, max .351 -> .412) and re-selecting WF OOS P5 is .446 (was .466, lift +.034 CI incl 0), so Flex stays below .60 and the extension buys speed (2-day passes), not a higher P5. Outputs: out/portfolio_lucid_flexext{,fast}.json/.npz, out/portfolio_wfres_lucid_flexext.json. NOT re-run: a3p3 scoring of all 2,535 configs, candidates.csv, funded (funded grids do not use the 1,500 cap).
- DEFECT 2 (Apex compliance gate, labelling): apex_thr_stop only tests day_stop >= $2,000. Per-trade stops at the chosen size are median $1,650-$4,725 for every Apex pick (stop > the $2,000 trailing threshold on 32-100% of trades) and MAE >= $750 on 58-86% of trades (a PA rule). The Apex 'compliant' headline P5 (.34 / .38 / .35 / .37, singles / portfolios) are NON-COMPLIANT upper bounds. Compliant bound (a3p3_apexmae: size cut so <= 2% of trades reach $750) re-derived independently for 7 configs: raw P5 <= .05 (MAE share <= .7%). Apex on ES is not workable (the MAE gate is a PA rule; for eval only it is the strictest reading).
- MULTI-ACCOUNT: the mixes in portfolio_results.json include Apex accounts (non-compliant). Lucid-only greedy re-fill (independent walks, in-sample, realized primary): N=2 .805, N=3 .888, N=4 .932, N=5 .953, N=6 .965 (intraday bound .53 / .65 / .79 / .82 / .84; fees $240 / $380 / $495 / $635 / $735). With the extended Flex take: P(>=1 pass <=2d) N=3 .78, N=4 .84, N=6 .87 (<=3d .83 / .89 / .93). Still in-sample greedy; independence approximation from WF OOS P5 (.45 / .32 / .47) is lower (N=3 ~ .80).
- Other checks: Flex-null / zero-edge null maxima reproduced (.401 / .384 / .552 / .354 / .350); ES fp-grid optima sit at the grid edge (stop 15 pts x 1.0R) so wider ES fast-pass stops were not explored (the null uses the same grid); 280 tests pass (NQ defaults).

## ES holdout (2026-10-01 11:00-17:10 ET): freeze, 132 runs, single frozen scoring pass, independent self-check
- Pre-freeze: ES drafts regenerated with ROLLS 13 -> 20 dates (+2025-03-17, 06-16, 09-15, 12-15, 2026-03-16, 06-15, 09-14); all 21 drafts identical except ROLLS; family_inputs.json byte-identical. 3 in-sample re-runs via hb.py (stage calib: hm-donchian-tf15#10, screen sweep_rev tf5, screen pinbar tf5) are dict-equal to their ledger bundles (3267 / 3436 / 2123 trades). 280 tests pass; hb dry-run 33/33.
- Code touched (research dir only, NQ defaults unchanged): build_holdout_manifest.py (pilot snapshot paths, Flex-ext finalists, funded_headline picks, Lucid-only mixes, in-sample Apex PA MAE flag), new lucid_only_mixes.py, verify_holdout_indep.py (pilot-aware, no-compliant-Apex branch), compact_summary.py (pilot dir). Hashed scorer files untouched by this step; portfolio.py hash now differs from the NQ freeze (87b9740a vs 8222633e, edited earlier by the ES stage for PP_FLEX_TAKE_EXT / PP_APEX_COMPLIANT), so NQ verify_frozen would now refuse a NQ re-score (NQ was already scored once).
- FROZEN 2026-10-01 11:15 ET: out/holdout_manifest.json sha256 5f84e45714d9ee4c66f0654fb6307d954c7f076cb0b4799a7750b4c2488443e2 (code: evalcore 0cd331e9, funded 3f25891e, portfolio 87b9740a, holdout_score 98d587d9). 39 eval finalists (5 firms: p5 single/best2/portfolio, fast single/portfolio, speed P1/P3, fast-pass, Apex compliant-flag single, Flex-ext single/best2/fast-best2), 18 funded finalists (summary top-2 + headline top-2 per variant, deduped), mixes N=2..6 as reported + Lucid-only Lo2..Lo6. 45 unique tester configs + 87 day-matched random control runs = 132 holdout runs (ES screening cap 248/400), all done 16:45 ET, range 2025-01-01..2026-09-30 (440 sessions, 436 rolling 5-day starts). News split available (54 CPI/NFP/FOMC days, news_days.csv).
- Scored once 16:50 ET (holdout_score.py score): out/holdout_results.json, out/holdout_summary.md (+ _full). No re-selection, no code change after seeing 2025+.
- RESULT: 60% criterion FAILS for every firm (primary model): Flex best .571 (fx_single, lift +.04 CI incl 0; original-grid single .56), LP+DLL .349, LP noDLL .592 (speed_p3; eod .64 passes, realized .59, intraday .31), Apex (all finalists MAE-noncompliant) .36, Apex EOD .37. Decay IS->HO: Flex +.06, LP noDLL +.03, LP+DLL -.08, Apex -.02..-.09. Lift vs day-matched controls is within CI of 0 for every top pick. Intraday-breach P5: Flex .19-.27, LP noDLL .31.
- FUNDED HO E$40 (IS -> HO): Pro noDLL donchian-tf15-pm 2,723 -> 1,202 (P20 .35, 6d, cheque $575, bust-pre .65); Flex donchian-tf15-pm 1,618 -> 1,080 (P20 .38, 8d, bust-pre .62); Pro DLL 2,093 -> 801; Flex+DLL 1,605 -> 723; Apex 382 -> 86. Intraday-breach E$40 ~65-100 for Flex/Pro noDLL.
- MULTI-ACCOUNT P(>=1 pass<=5d), HO [intraday bound]: as reported N=2..6 .667/.810/.920/.936/.961 [.47/.64/.68/.77/.80] (include non-compliant Apex); Lucid-only Lo2..Lo6 .748/.837/.897/.950/.970 [.43/.60/.67/.77/.80], fees $240-$695. Holds in-sample levels for N>=4; multi-account remains the only lever to reach >= .60.
- Self-check (verify_holdout_indep.py --lift, independent walks from raw holdout trades.json, calendar rebuilt from archive names = 440): all 39 eval finalists x eod/realized/intraday x P1,P2,P3,P5,bust5, per-firm criterion picks (Apex: no compliant finalist, agrees), executed trades/net, all 10 mixes (primary + 3 bounds), all 18 funded x 3 models x 10 metrics, and lift vs controls for the 11 top/mix finalists: 0 mismatches. Controls: all pools exact.

## Queue status
_auto-written by hb.py; daemon running; pilot es; updated 2026-10-02 21:19 ET_
- stages: calib: done 26; ctrl: done 60 error 6; holdout: done 132; screen: done 80; sizing: done 25; wf: done 15
- caps used: screening runs 248/400, heat-map cells 932/3000, walk-forwards 15/15
- 2025+ frozen-manifest runs started: 132 (counted in the screening-run cap above)
- running (0/4, slots shared by all pilots): none
- last error: none

