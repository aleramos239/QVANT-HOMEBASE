NQ passes the heat map at 18:00, 03:00, 08:30 (and 11:05 at exactly 60 %), but no time beats the same straddle fired at a random minute by enough (central t 0.56 / 0.89 / 1.67 against a bar of 2.62; 11:05 loses to random minutes by $40,188). ES and GC: no time passes. None admitted; NQ 08:30 and 18:00 go to the DEEPEN round.

## 5. VWAP-EMA cross (user's idea, weak prior)
63 units (21 per market). None passes on NQ or ES. One passes the heat map on GC (15-minute bars, midday: 67 % positive, median $1,856) but it loses to random entries by $2,291 (beats 25 % of draws) and its t is 0.44. Typical share of positive variants: NQ 40 %, ES 14 %, GC 15 %. No edge found; it goes to the DEEPEN round, not the library.

## 6. What Level 2 added (NQ)
* As a strategy: book-imbalance follow passes the heat map in 1 of 7 sessions and flow exhaustion in 5 of 14, but no central variant beats the random or shuffled-book bars (best t 1.88 against 2.02 and 2.65) and two lose to the shuffled book.
* As a filter or exit on breakouts that passed BUILD (27 unit-sessions each), against the same strategy without it on the same days, median change per variant: -$11,683 (skip when the book opposes; keeps 40 % of trades), -$10,445 (trade only into a thin book; keeps 16 %), -$8,835 (exit on a book flip). The change was positive in 0, 1 and 0 of 27, and in 0 of 81 did it beat the shuffled-book version (the real book beat the shuffled one in 37-47 % of variants). Only two shuffles per unit: a thin null.
* The shuffled-book versions passed the heat map more often (79 of 130) than the real ones (39 of 81). At the trade's moment the book added nothing and removed profit.

## 7. Multiple-testing honesty
* 1,623 units were judged. Random controls judged by the same heat-map rule pass on NQ in 6 of 56 cases (random entries) and 5 of 18 (random-minute straddles); on ES and GC in 0 of 56 and 0 of 18. So about 58 of NQ's 128 heat-map passes are what random entries alone would give.
* Second gate (central variant above the 95th percentile of the best random variant): 0 of 168 random units pass both gates; 5 of 1,623 real units do (0.3 %). 168 nulls cannot rule out a chance rate that small, so the BUILD gate alone is not proof. 2024 removed 2 of the 5 and the trade-count rule 1 more.
* The units are not independent: orb on 15- and 30-minute bars is the same trades in 72 of 96 variants; the pre-market orb and the 08:30 straddle (92 % of variants positive on NQ, t 1.67, below its bar) are one idea tested twice; orb pre passes the heat map on all four bar sizes and donchian morning on three, but only one bar size of each clears the bar.
* Both members exist on NQ only: orb pre is negative on ES and GC (16-41 % of variants positive) and the donchian morning does not pass there (ES 30-minute: 59 %).
* Bookkeeping: 33,984 candidate variants of the 40,000 cap (unchanged). The 2024 and stress re-runs (1,144 variants) re-test variants already counted and are booked as control cells; 12 member runs of the 2,000 cap. The orchestrator may re-book them.

## 8. Loss-day overlap of the two members (default variants)
| share of the row's losing days that are also losing days of -> | orb_NQ_tf1_pre | donchian_NQ_tf30_nyam |
|---|---|---|
| orb_NQ_tf1_pre (loses on 55 % of 2024 days) | - | 38 % in 2024 · 40 % over 2021-24 |
| donchian_NQ_tf30_nyam (loses on 37 % of 2024 days) | 57 % in 2024 · 58 % over 2021-24 | - |
Each overlap equals the other member's ordinary losing-day rate: losing days do not cluster. Daily net correlation -0.07.

## 9. Open risks
1. One clean member is not a library. donchian_NQ_tf30_nyam is admitted on a pre-written rule but fails the library's own check on its default variant; treat it as a near miss until the checker rules.
2. orb_NQ_tf1_pre lives on a 7-tick average trade, and 63 % of its profit is made inside 2 seconds in the 08:30 data minute; live fills decide it. Paper-trade it before any account uses it.
3. Evening, pre-market and "hold to 15:58" runs have no Strategy Tester equivalent; their proof is the engine's own tests.
4. 208 units pass the BUILD heat map without admission; their 2024 is unread and clean for the DEEPEN round (`out/near_misses.md`).
