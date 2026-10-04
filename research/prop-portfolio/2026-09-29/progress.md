# NQ prop-portfolio pilot — progress (read me first on resume)

Brief: user's prompt 2026-09-29 (NQ pilot, Lucid Flex 50K + Apex Legacy 50K, P(pass≤5d) ≥ 60%).
Spec: SPEC.md. Ledger: ledger.csv. Jobs: jobs.jsonl. Driver log: hb.log.

## Decisions
- Breach model: PRIMARY `eod` = Homebase rule files (Lucid help-centre: intraday recovery OK);
  `intraday` = sensitivity column. Apex UNCONFIRMED everywhere.
- Sizing + daily rules applied OFFLINE on tester trade lists (exact for sequential trades; one
  run → many rule sets). Tester runs at qty 1 NQ.
- Screening: one run per family × tf with sess=all, split by session offline (5 configs/run).
- Asia reachable only as 00:00–03:00 ET (calendar-day sessions).

## USER PRIORITY (2026-09-30 09:21 ET)
"i care more about a high % rate in a short time the most" → rank by P(pass ≤ k days) (k=1,2,3,5);
edge lift becomes a warning label, not a filter (still reported; original pass-criteria verdict still stated).
Added FAST-PASS track: pts stops {10,20,30,45} × tgt_r {0.25,0.4,0.6,1.0} on best entry signals +
random ctrl (fastpass.jsonl, ahead of tune2 remainder). Pair with target_take / day_take + max size.
Mac hibernated 00:40–09:00 on dead battery (8 h tester loss); offline compute pauses 09:18–09:36 ET.

USER 2026-09-30 09:25: also score LucidPro 50K (no consistency, 1-day pass, $2k EOD, $3k target) — both with
the $1,200 soft DLL (rule file default) and without (removable option). SPEC "Firms" section = 4 rule sets.

USER 2026-09-30 16:5x: (1) run EVERYTHING for ES too → pilot dir ../2026-09-30-es (own caps/ledger; one hb.py queue with
per-pilot caps); (2) FUNDED mode for Apex Legacy PA, LucidPro funded, LucidFlex funded — objective: high payout %, high
payout, short time to payout. Rules in FUNDED_RULES.md (user paste). Apex compliance: no OCO/both-side orders, stop ≤ 5×
target, no threshold-as-stop, no eval stockpiling → fast-pass not recommendable at Apex. wf_ff657978-21f = funded engine
+ NQ funded search + ES setup/screen/tuning queue + verify.

## Stage log
- [x] 0 Build infra — workflow wf_ee3d6308-626 (7 sonnet agents). Review fixed exit_bars off-by-one,
  roll-day stale prior-day levels (ROLLS list, 2021-24 only — extend before holdout), FOMC window
  13:59:30–14:30; evaluator fixes: day_stop worst, qty-normalised loads, cost ratio.
  Run evaluator with /usr/bin/python3 (numpy); hb.py with the venv.
- [x] 0 Calibrate: full 2021–24 run (ema_pullback tf5 all) = 23 s; 20-cell heat-map = 244 s (~12 s/cell @2 slots).
  DATA GAP: NQ ticks start 2021-09-22 → research window = 2021-09-22..2024-12-31 (825 sessions).
  PLAN (projection): A1 screen 80 runs + 16 random ctrl ≈ 20 min · A3 tester heat-maps ≤ 2,500 cells ≈ 8.5 h ·
  A4 15 walk-forwards ≈ 2 h · holdout ≈ 10 runs · all offline scoring < 1 h. Total ≈ 12 h ≤ 48 h cap → no scope cuts.
- [x] A1 Screen: 80 family×tf runs + 16 random ctrl (out/screen_table.csv, screen_summary.md). Only 2/252
  (≥300 tr) configs have t≥2: donchian/15/pm t3.05 PF1.45 (+$81k, 57k of it 2022), donchian/30/pm t2.11.
  Apex eod-model random baseline 0.42–0.63 at 100mc (EOD-only breach lets intraday −$4.5k recover);
  intraday model ~0.12–0.28. Lucid P5 ~0.03–0.15 without daily rules (consistency + 2-day min).
- [~] A2: old lift confounded by day-spread → day-matched control being built (workflow wf_4d6a080a-9a0).
- [~] A3: rules search pass 1 (screen configs) running; tester heat-maps tune1.jsonl (13 fams, ~450 cells)
  + hmctrl random grids + ctrl2 random runs queued (controls first). Pass 2 on heat-map cells next.
- [x] A3 pass 1 (screen configs, wf_4d6a080a-9a0): day-matched control built (Lucid lift shrank ~half — was
  day-spread; Apex held). Null-lift thresholds (p95): Lucid eod .050 / intra .046; Apex eod .088 / intra .072.
  Above threshold: Lucid 29/252, Apex 26/252 (≈12.6 expected by chance) → modest real excess.
  Best stable P5: Lucid ≈0.25 (bust5 ≈0.67), Apex eod ≈0.50–0.59 (intraday ≈0.26–0.34).
  Optimised zero-edge baseline P5: Lucid eod mean .06 / max .25; Apex eod mean .39 / max .61; Apex intraday max .34.
  INSIGHT: single-session configs lack daily $ variance for Lucid (40mc cap, 5 days, 50% consistency) →
  need intraday day_take (flatten at ~+$1,500) + bigger stops / multi-session portfolios.
- [~] A3 pass 2 (next): heat-map cells + day_take/target_take rules (MFE-based, pessimistic ordering),
  hmctrl seeds 11–13 for matched controls, null per exit profile. Then shortlist → A4.
- [~] tune2.jsonl queued 00:20 ET (16 more family heat-maps + tod_drift tf15/30 + randomtod exit-bars ctrl, 603 cells)
  → needs a pass-3 search (reuse a3 pass-2 script) once done.
- [x] A3 pass 2 (wf_0dc4f45c-8c5): 1,719 configs (hm-* cells + screen), 2.97M rule cells. With day_take/target_take:
  eod stable P5 best Lucid .675 / Apex .836; NULL (zero-edge) mean .336/.680, max .624/.834 → rules drive most
  of P5; real lift +0.10..+0.22 over day-matched ctrl. Intraday model: best Lucid .31 / Apex .40. Shortlist
  (out/shortlist.csv, 40/firm) = vwap_band/vwap_z tf5 london/mid dominate; eod-optimal rules need NO day_stop
  and EOD-only breach (a $1k day_stop collapses P5). Verifier: numbers exact; 77/80 carry overfit flags
  (one-year net concentration, net≤0 rule-walked, neighbour collapse).
- [~] wf_d0f72abc-0c2: web check of EOD-vs-intraday enforcement (rules_research.md) + LucidPro search + P1/P2/P3/P5.
- [x] wf_d0f72abc-0c2: rules_research.md (firm pages). APEX: breach is REAL-TIME incl. open P&L (EOD accts);
  "Legacy" = intraday-trailing $2,500 product → user's apex rule set is a hybrid, flagged; site-consistent
  variant apex_eod = apex-eod-50k@2026-09-27b ($2k, $1k soft DLL, 60mc). LUCID: "account balance reached MLL",
  no real-time wording → report eod / realized / intraday. LucidPro added (out/a3p2_lucidpro*.csv,
  shortlist_all.csv, a3p2_fast.csv). Best P5 eod|intraday: Flex .68|.31, Pro+DLL .45|.40, ProNoDLL .69|.40,
  Apex .84|.40. Null mean eod: .34/.28/.47/.68. Pro+DLL = most robust to breach-model uncertainty.
- [~] wf_e6b7781b-a5f: 'realized' breach model + apex_eod variant; OFFLINE walk-forward (params+rules, quarterly,
  trailing-12m selection) on shortlist families with random-control OOS lift.
- [x] wf_e6b7781b-a5f: 'realized' model + apex_eod variant (evalcore.MODELS, primary_model map; verifier fixed a
  conservative realized-model bug for overlapping stop/take flattens). OFFLINE WF (out/wf_offline.csv): IS→OOS drop
  ≈0.02–0.03; OOS P5 median eod/realized: Lucid .54, Pro .37, ProNoDLL .60, Apex .79; intraday .23/.34/.34/.34.
  OOS lift vs optimised random: eod +.10..+.19, intraday +.03..+.08. Strict survivors: orb-tf5/nyam, tema_slope-tf5/
  london, vwap_band-tf5/london, donchian-tf15/pm, donchian-tf30/nyam, first_bar_mom-tf15/nyam, orb-tf5/mid, rsi2-tf1/mid.
  Family-selection bias probed: negligible (ex-ante picks do as well).
- [x] Homebase tester WFs (A4, 8/15): param pick on 1 month by t_stat, test 3 months, stitched OOS at 1 NQ, raw P&L:
  POSITIVE only donchian-tf15-pm (+$35.6k, PF 1.15, Sh .74, 712 tr) and first_bar_mom-tf15-nyam (+$22.3k, PF 1.06, 740 tr).
  Negative: orb-tf5-nyam −9.9k, tema_slope-tf5-london −31.6k, vwap_band-tf5-london −20.3k, donchian-tf30-nyam −5.5k,
  orb-tf5-mid −8.0k, rsi2-tf1-mid −19.3k. → most pass-rate 'edge' is payoff SHAPE under the rules, not expectancy;
  funded-phase (needs +expectancy) should lean on donchian pm + first_bar_mom nyam.
  WF 9-15 (all 15 used): donchian-tf5-pm +$82.0k PF1.22 (1,265 tr) ← strongest; straddle-tf30-pm +$18.6k PF1.07;
  tod_drift-tf5-mid +$19.7k PF1.07; orb-tf5-nyam fast-pass +$7.1k PF1.08; negative: straddle-tf30-nyam −5.2k,
  squeeze-tf5-mid −58.0k, tod_drift-tf5-mid fast-pass −1.0k. → 6/15 positive OOS; DONCHIAN PM robust across tf.
- 2026-09-30 17:34 tester slots 2→4 off desk hours (slots.py cap_at, grid WORKERS 4, hb.py max_ours) — uncommitted.
- [x] PASS 3 (wf_3a7f28d0): 1,283 configs x 5 firms x 3 models; best primary P5: Flex .69 (intraday .01), LP+DLL .48, LP noDLL .71 (P1 .67),
  Apex .42, ApexEOD .42; real bests sit near the optimised-null max -> the rules grid drives most of P5. Out: out/candidates.csv, a3p3_summary.md.
- [x] STAGE B portfolio (verified; WF look-ahead in the 50% guard FIXED): members add 0..+.03 P5; under max_day_tr=1 the LPnoDLL and Apex
  "portfolios" execute as ONE strategy (executed-share 100%) -> treat portfolios as singles. Best: Flex .688 (straddle-tf30#8 nyam + 2), LP+ .423,
  LPnoDLL .706 (straddle-tf30#9 nyam), Apex .402 (UNCONFIRMED), ApexEOD .424. Corrected reselect-WF OOS P5: .649/.374/.647/.387/.374.
  MULTI-ACCOUNT (parallel evals, distinct strategies) is the real diversifier: P(>=1 pass<=5d) N=3 .916 ($250), N=5 .960 ($465), N=6 .981 ($525)
  [intraday bound .67/.81/.81]; in-sample greedy -> optimistic. Out: out/portfolio_summary.md, portfolio_members.md, portfolio_results.json.
- [x] FUNDED (funded.py + funded_search.py; verified independently, Pro DLL non-sticky bug FIXED): top E$ to trader by 40d (primary model):
  Pro noDLL orb-tf5/mid m40 K1000 L300 $5.4k (P payout 20d 61%, median 4d, bust-before-payout 39%; WF OOS median $3.2k);
  Flex straddle-tf30/pm m40 K600 L300 req>=$1.5k $3.3k (61%, 7d; WF $2.2k); Pro DLL donchian-tf15/pm m30 $2.0k (40%, 12d; WF $1.5k);
  Flex+DLL $1.7k; Apex PA donchian-tf15/nyam m30 $1.1k (23%, 20d; WF $0.5k; UNCONFIRMED). E[net per eval purchase] same-config:
  Pro noDLL ~$3.8k, Flex ~$2.0k, Flex+DLL ~$0.85k, Pro DLL ~$0.8k, Apex ~$0.66k. Out: out/funded_summary.md, funded_candidates.csv, funded_wf.csv.
- !! KEY RISK: every Lucid headline (eval AND funded) assumes Lucid breaches on realised/closed balance. Under intraday (open P&L) Flex P5 -> .07,
  LPnoDLL -> .26, funded Flex/LPnoDLL E$40 -> ~$0-40. Confirming Lucid's breach rule is the single most valuable unknown.
- [ ] C Holdout 2025->latest (ONCE, frozen manifest) · [ ] Deliverables · [ ] ES pipeline (tuning done 22:17)

## Holdout NQ part 1 (2026-09-30 22:15-23:12 ET): freeze + submit; NO 2025+ result opened
- Data: NQ ticks complete through 2026-09-30 (440 weekday sessions 2025-01-02..2026-09-30; 2 partial: 2026-09-23, 09-25; coverage tool also lists 09-11, 09-22 partial, 09-07 = holiday). Holdout range 2025-01-01..2026-09-30.
  News 2025+: news_days.csv already has 54 CPI/NFP/FOMC days in the range (source ff_usd_red_raw.txt) -> news split available.
- ROLLS: gen_drafts.build_rolls now reads every archive year (13 -> 20 dates, + 2025-03-18, 06-16, 09-15, 12-15, 2026-03-16, 06-15, 09-14). The 21 NQ drafts regenerated: identical to the previous
  files except the ROLLS list (prefix of 13 dates unchanged); family_inputs.json + news_days.csv byte-identical. 4 in-sample re-runs (hm2-straddle-tf30#10 vs its grid cell, screen sweep_rev / gap / pinbar tf5)
  reproduce their ledger trades EXACTLY (3273 / 3430 / 559 / 2111 trades, dict-equal). 277 existing tests + 3 new pass; hb dry-run 33/33.
- hb.py holdout guard: a range reaching 2025+ is refused (queue time + submit time) unless stage 'holdout', key + kind/strategy/inputs/range/costs equal the frozen manifest line and out/holdout_manifest.json matches
  out/holdout_manifest.sha256; holdout runs count in the 400 screening cap and write ledger_holdout.csv (ledger.csv stays in-sample only). Daemon restarted 22:32 (pid 7156) to load it.
- Frozen 22:39 ET: out/holdout_manifest.json sha256 7d342e8751df9dddee1afa80582e489c360824c1ae31402ee2f065f5aa14328a. Code sha256: evalcore 0cd331e9..., funded 3f25891e..., portfolio 8222633e..., holdout_score 98d587d9...
  (full hashes in out/holdout_manifest.json code_sha256; `holdout_score.py hashes`). 36 eval finalists (5 firms: p5 single, best2, >=3 portfolio, fast single / fast portfolio, speed P1/P3, fast-pass; Apex speed/fast-pass picks
  restricted to compliant cells, reported non-compliant Apex sets kept and flagged), 10 funded finalists (top + runner-up x flex, flex_dll, pro_dll, pro_nodll, apex), mixes N=2..6 as reported.
  41 unique tester configs + 105 day-matched random control runs = 146 holdout runs (screening cap now 289/400), all done 23:12, all bundles range 2025-01-01..2026-09-30.
- holdout_score.py (frozen scorer): `validate` reproduces every frozen in-sample P5 (max diff 5e-7), lift, funded E$40 and the multi-account mixes on 2021-24; `selftest` shows the holdout code path
  (Resolver, tape calendar, load(holdout=True)) equals the in-sample path. `score` refuses unless manifest + code + input hashes match. NEXT (part 3): run `holdout_score.py score` -> out/holdout_results.json, out/holdout_summary.md.

## Queue status
_auto-written by hb.py; daemon running; pilot nq; updated 2026-10-02 21:19 ET_
- stages: calib: done 6; ctrl: done 84 error 9; holdout: done 146; screen: done 80; sizing: done 40; wf: done 15
- caps used: screening runs 289/400, heat-map cells 1484/3000, walk-forwards 15/15
- 2025+ frozen-manifest runs started: 146 (counted in the screening-run cap above)
- running (0/4, slots shared by all pilots): none
- last error: none

## Holdout NQ part 2 (2026-09-30 23:13 ET): frozen scoring DONE (single pass, no re-selection, no code change)
- Verified before scoring: manifest sha256 7d342e87... and evalcore/funded/portfolio/holdout_score hashes unchanged; 146/146 holdout jobs done. `holdout_score.py score` ran once (10 s) -> out/holdout_results.json,
  out/holdout_summary_full.md (scorer's own 90-line output); out/holdout_summary.md is the <=70-line view made by compact_summary.py (formatting only: eval tables merged, blank lines dropped, no number recomputed).
- 60% criterion (P(pass<=5d)>=0.60, primary model): lucid PASS (P5 .74-.78, CI lo .73 single, lift +.13/+.15; eod .78, realized .78, INTRADAY .02-.04), lucidpro_nodll PASS (.81, lift +.12..+.14; intraday .07-.22),
  lucidpro FAIL (best .41), apex FAIL (best compliant .43, fast_single, lift +.06), apex_eod FAIL (best .35). Lucid headline = realised-balance breach: under intraday breach both Lucid passes fail.
- Straddle-tf30 (nyam) family carries both Lucid passes and the funded Flex/Pro-noDLL picks; in-sample P5 .69-.71 -> HO .78-.81 (decay positive). Lucid Pro (DLL) and Apex finalists decayed -.08..-.18 vs in-sample.
- Funded E$40 in-sample -> HO: flex#1 3330->2488, flex#2 3339->2329, flex_dll 1734->703 / 1612->751, pro_dll 1996->1252 / 1881->744, pro_nodll#1 5426->4824 (P20 .69, 4d), pro_nodll#2 4861->3607, apex 1093->1133 / 926->705.
  Flex/ProNoDLL intraday-breach E$40 ~0-17 on holdout (same fragility as in-sample).
- Multi-account P(>=1 pass<=5d): N=2 .860, N=3 .913, N=4 .899, N=5 .936, N=6 .968 (IS .839/.916/.928/.960/.981); intraday bound .33-.63.

## Holdout NQ part 3 (2026-09-30 23:15-23:45 ET): adversarial verification -- NO plumbing errors found, nothing changed
- Freeze order: manifest frozen_at 22:39:56 (file + .sha256 22:39; sha 7d342e87... unchanged, code + 7 input hashes unchanged: verify_frozen = []). Every pilot 2025+ run/grid in the tester state (146 of 146, scanned all 594 run/grid dirs) is stage 'holdout', submitted 22:40:06-23:11:08, i.e. after the freeze;
  no earlier pilot run has an end date >= 2025. Only other 2025+ runs: 9 runs/grids of the separate nq930 / nq_930_side_sltp project (not pilot strategies). All selection sources (portfolio_summary.md, funded_summary.md, candidates) are dated <= 22:17;
  all 15 single/best2/portfolio finalists match portfolio_summary.md exactly (members, micros, rules). holdout_results.json written once 23:13:16; scorer + hashes untouched since.
- ROLLS: used only as `self.day not in ROLLS`; first new date 2025-03-18. The 4 rollcheck re-runs (straddle#10, sweep_rev, gap, pinbar) equal their original in-sample trades.json dict-for-dict (3273/3430/559/2111). No 2025+ date/trade in any in-sample file/source (checked 146 in-sample sources + out/*, ledger.csv, bundles_cache calendar ends 2024-12-31).
- Independent re-derivation (verify_holdout_indep.py: verify_indep.py eval walk + verify_funded_indep.py lifecycle; share only E.load, rule JSON, manifest; calendar rebuilt from archive file names = 440 sessions, 436 starts5, 381 starts60):
  ALL 36 eval finalists x eod/realized/intraday (P1,P2,P3,P5,bust5), the 5 per-firm criterion picks (best, pass/fail, executed trades, net), mixes N=2..6 (primary + 3 bounds), ALL 10 funded finalists x 3 models x 10 metrics (E$40, P20/40/60, median days, bust ...),
  and lift vs day-matched controls for the top eval + mix accounts: max abs diff 0.0, 0 mismatches.
- Controls: all 146 holdout runs have inputs/qty/commission/slippage/capital/fill law/engine identical to their in-sample source (only the tester's own prop_rules label differs; not used by the scorer); control (date,session) counts equal the real member's except <=2 shortfall trades; fallback share <=9.3%;
  same micros + rules per finalist. Caveat: 5 configs use a NEAREST (non-exact) control profile (apex donchian fp-donchian-tf15#15/#10/#13/#1 dist 10 -> tf1 proxy; lucidpro:pf member hm-tod_drift-tf5#15 dist 1): lift there is approximate.
- Observations (not errors): Lucid Flex P1=P2=0 is structural (consistency 50% + min 2 days + day_take 1500 minus 20 slippage => two days reach ~$2,960 < $3,000, so >= 3 days). Tester skipped 7 of 440 sessions for data gaps/closures (counted as no-trade days, same convention as in-sample).
  The Lucid passes depend on the realised-breach model: lift vs controls is ~0 under intraday; a straddle-tf30 stop of 3 ATR means single-day open losses of $15-35k at 40 micros are ignored by the realised model. tester ledger_holdout.csv trade counts + gross equal the loader's trades (146/146).
