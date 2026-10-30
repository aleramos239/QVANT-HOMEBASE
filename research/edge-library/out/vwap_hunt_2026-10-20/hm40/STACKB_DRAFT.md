# Stack B: DRAFT (written 2026-10-21 evening; NOT pre-registered, nothing ported, nothing run forward; the owner decides)

In-sample months only (runs_wf/<store>/is, the pinned 14 blocks, 883 New York days 2021-10-01 .. 2026-04-30). No test month, grade,
LUCK or oos file was read. Numbers: `stackb_draft.py` (this folder; it writes nothing) + onr_side_study.csv. PREREG_HM40.md is untouched.

**The answer first: in-sample, no NQ rule set is both clearly different from stack A and 5+ trades a day.**
The rule below keeps only rules that are less tied to stack A than A's typical member is. It picks **2 rules, 2.42 trades a day,
daily-net correlation 0.34 with stack A.** Getting to 5+ a day means adding 2 trend-pullback rules that are tied to A about as
closely as A's own members are (0.56, 0.61). That gives 6.44 a day at correlation 0.66: mostly a second copy of A's bet.

## 1. Why the choice is this small (in-sample)
| Place to look | What the in-sample stores say |
|---|---|
| Other markets (ES, GC) | 2 ES stores have an eligible version (onr_orb 0.42 a day, supertrend 0.59 a day). Both are trend rules on a market that moves with NQ, and ES costs $21.32 a trade vs NQ $10.79. GC: no eligible version. |
| London / overnight | 0 eligible versions in 24 non-NY store-groups. 22 of the 24 have 24 % of boxes positive or fewer. The one broad store (NQ London VWAP touch, 76 %) belongs to an idea whose average trade is negative (idea 5, -$9.3), so it fails S2. |
| Fades / reversion | vwap_z, vwap_band, rv_fade, vwap_flip: 1-34 % of boxes positive across 12 NQ NY stores. All fail S3. |
| Mid / pm sessions | Not new ground. Stack A already trades 44 % nyam / 29 % mid / 27 % pm (avg trade +$272 / +$205 / +$92). |
| 15m bars | Not new ground. 6 of A's 8 rules already use 15m bars. |
| **Entry type** | **The one axis that differs.** Two rules enter at a VWAP line (a limit at the line, or the bar after a VWAP touch). They correlate 0.27-0.30 with A. The other 3 stores left for B (one breakout, two trend-pullback) correlate 0.56-0.73. |

For scale: A's members correlate 0.28-0.79 with the other 7 (median 0.475), and 0.305 with each other on average.

## 2. The one rule (draft text, in the style of Amendment K)
- **B1-B7** = Amendment K's S1-S7, unchanged (NQ, 5 / 15m bars, the NY group; idea average > 0; > 50 % of the store's NY boxes positive;
  wide exits only; C1-C9 with Amendment J's C1 and worse fills > 0; the lower middle; one store per idea x family). Their output is
  already on file: stack.json "rest" = the 5 stores that pass S1-S7 but are not in stack A. S7 leaves one store per idea x family, so
  none shares an idea x family with A.
- **B8, different:** the pick's in-sample daily net is correlated with stack A's in-sample daily net at **<= 0.475** (Pearson). Daily net
  = NY sessions over the 883 days, $0 on a day with no trade; A = its 8 picks summed. 0.475 is the median, over A's 8 members, of each
  member's correlation with the other 7, computed once and frozen. Said plainly: the cap was chosen with the 5 correlations already on
  screen (0.27 / 0.30 / 0.56 / 0.61 / 0.73). Any cap from 0.30 to 0.55 picks the same 2, A's average pair (0.305) included.
- **B9, the stack:** what is left, lowest correlation first. At most 12 rules; stop at 10 a day. If the total is under 5 a day, take all
  of them and state the shortfall.
- Not used: test months, grades, LUCK, SEEN labels. (Idea 1's test months were read on another store on 2026-10-20. A forward test does
  not care, as in K.)

## 3. What it picks (in-sample)
| Store | Box | Family | Bars | Trades/day | Avg $ | Win | Break-even | Blocks + | Block t | Months + | Boxes + | Corr with A | nyam / mid / pm % | B8 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| vh_i11_touch_gx_5_ny-NQ-tf5 | away160_pts60-r2 | avwap_touch | 5m | 1.41 | 117 | 42.9 % | 38.8 % | 9/14 | 2.44 | 8/9 | 59 % | **0.27** | 43 / 33 / 25 | **IN** |
| vh_i1_pb_5_ny-NQ-tf5 | vwap_slope60_pts60-r2 | jj_fair | 5m | 1.01 | 94 | 40.5 % | 37.4 % | 9/14 | 2.24 | 9/9 | 54 % | **0.30** | 62 / 27 / 11 | **IN** |
| vh_i2_tp_15_ny-NQ-tf15 | x0p2_atr2-r1p5 | vwap_trend_pull | 15m | 1.43 | 133 | 49.7 % | 45.3 % | 10/14 | 2.35 | 9/9 | 68 % | 0.56 | 21 / 47 / 32 | out |
| vh_i10_adx_tp_5_ny-NQ-tf5 | g_lvl20_atr2-r2 | vwap_trend_pull | 5m | 2.59 | 128 | 44.4 % | 39.8 % | 13/14 | 3.49 | 8/9 | 71 % | 0.61 | 24 / 43 / 33 | out |
| vh_i6_g_cbrk_15_ny-NQ-tf15 | backrange_own1p5-r2 | candle_sweep | 15m | 4.16 | 112 | 44.9 % | 41.2 % | 13/14 | 4.29 | 8/9 | 72 % | 0.73 | 28 / 35 / 37 | out |

The two rules in plain words:
- **B-1, VWAP touch with two anchors (avwap_touch).** When a 1-minute close is 40 points (160 ticks) from the 09:30 VWAP, a limit order
  waits AT that VWAP on the side price came from: above means buy the pullback, below means sell the bounce. The order is re-priced at
  every 5-minute close. It is placed only if price is also on the trade's side of the Globex VWAP (anchored at 18:00 the evening
  before). The first minute that comes within 3 ticks of the line uses up the setup, filled or not. Stop 60 points, target 2R.
  At most 3 entries per session; nyam, mid and pm run as separate instances.
- **B-2, VWAP-touch momentum (jj_fair, entry mom).** Between 09:35 and 15:00, on a 5-minute two-bar displacement: bar 2's body is bigger
  than bar 1's and the two bars are opposite colours (the wick test is off in this spec). Enter at market in the displacement's
  direction, but only if three things hold: bar 1 touched the session VWAP, the close is on the trade's side of the VWAP, and
  the VWAP has moved the trade's way over the last 60 minutes. Stop 60 points, target 2R. One instance.
  Its recent in-sample average (from 2024-10) is only +$35.

## 4. Stack B as a whole vs stack A (in-sample, 883 days)
| Set | Rules | Trades/day | Avg trade | Win | Corr with A (2021-10..2023-12 / 2023-12..2026-04) | Its avg day on A's 449 losing days (A: -$7,899) |
|---|---|---|---|---|---|---|
| **Stack B (the rule)** | 2 | **2.42** | +$107 | 41.9 % | **0.34** (0.42 / 0.29) | -$885 |
| B with the cap lifted to 0.65 | 4 | 6.44 | +$121 | 44.6 % | 0.66 (0.74 / 0.60) | -$2,613 |
| All 5 "not taken" (no cap) | 5 | 10.60 | +$118 | 44.7 % | 0.77 (0.84 / 0.71) | -$4,302 |
| The 3 Amendment-J rules already in shadow | 3 | 1.74 | +$158 | 45.0 % | 0.38 (0.43 / 0.36) | -$335 |
| Stack B + the 3 J rules | 5 | 4.16 | +$128 | 43.2 % | 0.46 (0.54 / 0.41) | -$1,220 |

Stack B correlates 0.25 with the 3 J rules.

## 5. The overnight-side gate: not in the rule (in-sample numbers)
The 09:30 open's third of the 01:00-09:30 range (onr_side_study.csv, front-month 1-minute bars; filters cannot run on the 3:1 route yet):
| Pick | Share with / against / middle third | Avg trade with / against / middle | Trades a day: no gate / with-side only / skip the middle third |
|---|---|---|---|
| B-1 touch_gx | 41 / 27 / 32 % | +$203 / +$166 / -$33 | 1.41 / 0.58 / 0.95 |
| B-2 pb_5 | 48 / 22 / 31 % | +$262 / -$142 / -$2 | 1.01 / 0.48 / 0.70 |

- The with-side gate would cut B from 2.42 to 1.06 trades a day. It is left out.
- A broader lead, found while writing this (in-sample, not pre-registered): across 61 NQ stores, the average box (each store weighted
  equally) makes +$1.5 a trade on days when the open sits in the MIDDLE third, vs +$27.3 on the other days (48 of 61 stores; 30 % of
  trades). Weighted by trades instead: -$5.7 vs +$12.9. Skipping the middle third would cut B
  to 1.65 a day. It would apply to stack A as well. The owner's call; it is not part of this rule.

## 6. What it would cost to port (as in K: one Lab draft per NY session instance, exact parity on the in-sample months first)
| Rule | Drafts | What is new in the Lab | What can be reused | Blockers / notes |
|---|---|---|---|---|
| B-1 touch_gx | 3 (nyam / mid / pm) | The **Globex VWAP from 18:00 the evening before** | The limit-at-the-line code and the RTH VWAP line from nq_sk_orbpb15_* (orb_vwap_pb is the same avwap._Touch class) | A **limit entry: can be shadowed, not booked** (K). In the Lab today, evening minutes go only to a draft whose window starts the evening before, and such a draft is shadow-only (labcfg.evening / SAY_EVENING). Fine for shadow; a second blocker before money. |
| B-2 pb_5 | 1 (09:35-15:00) | The jj_fair family (engine file 247 lines) | The session VWAP from any nq_sk draft | **research/edge-library/engine/families/jj_fair.py is untracked in git** (git status `??`). The parity reference is someone's uncommitted work: it has to be frozen first, and the owner or its author decides how. |

- **Effort:** stack A's 20 drafts were written 16:59-17:14 and run in the Lab at 17:25 (stack_drafts timestamps, stack_runs.txt), about
  30 minutes with parallel agents. Stack B is 4 drafts but 2 new families, so expect about the same 30-60 minutes including parity.
- **Runner load:** the Mac runner hosts 29 hunt drafts today (20 nq_sk + 9 nq_vh). B adds 4 (+14 %).
- Lifting the cap to 0.65 adds 6 drafts (vwap_trend_pull, round1.VwapTrendPull, x 2 stores x 3 sessions). adx_tp can reuse the ADX gate
  from nq_vh_adxtouch_*.

## 7. The bar, if B runs (mirrors STACK_BAR.md; written before any B day)
- Day 1 = the first session with all 4 drafts in shadow. Read once, 26 weeks later (~130 sessions, ~315 trades, per-trade sd $1,550,
  one standard error $87).
- Fidelity: >= 90 % of days "Matched the backtest" for each draft.
- Stop, checked monthly from 100 trades: the average trade is at or below -2 standard errors (-$310 at 100 trades, -$219 at 200, -$175
  at 315).
- Pass: >= 200 trades AND the average trade after costs, with one more tick a side, is >= +1 standard error AND the win rate is >= its
  own break-even.
- What a pass can show: a B with no edge passes ~13 % of the time; +$50 a trade ~29 %; +$100 ~51 %; the in-sample +$107 ~54 %; +$200
  ~88 %. Like A, it can only tell a +$100-a-trade edge from nothing.

## 8. For the owner
| Choice | Trades a day | Corr with A | What it adds |
|---|---|---|---|
| **1. B as drafted** (recommended) | 2.42 (4.16 with the J rules already running) | 0.34 (0.46 with J) | A second, mostly separate forward test: entries at the VWAP line, not breakouts |
| 2. Lift the cap to 0.65 | 6.44 | 0.66 | Meets 5-10 a day, but the 4 added a day are A's trend-day bet again |
| 3. No stack B | 0 | n/a | Nothing new to port; A and the J rules run as they are |
