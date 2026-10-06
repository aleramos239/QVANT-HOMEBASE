# Dry run: the build checklist on the 1,875 stored tables (BUILD = 22 Sep 2021 - 2023)

Side codes found in the stores: [-1, 1] (long = above 0).

| line (each on top of the ones before) | tables left | ideas left |
|---|---|---|
| all stored tables | 1,875 | 65 |
| 1. Heat map: over 60 % of variants profitable | 249 | 42 |
| 2. + average trade at the cost floor | 56 | 20 |
| 3. + on pace for 200 trades (120 on the stored 27 months) | 28 | 11 |
| 4. + long and short each make money | 28 | 11 |
| 5. + half or more of its neighbor tables profitable | 18 | 7 |
| 6. + beats 95 % of random tables | 6 | 3 |
| 7. + Monte Carlo: still meets 1 and 2 in 75 % of reshuffled runs | 3 | 1 |

Each line on its own (how many of the 1,875 tables pass that one line alone):

| line | tables passing it alone |
|---|---|
| Heat map: over 60 % of variants profitable | 249 |
| average trade at the cost floor | 58 |
| on pace for 200 trades (120 on the stored 27 months) | 1,674 |
| long and short each make money | 265 |
| half or more of its neighbor tables profitable | 309 |
| beats 95 % of random tables | 68 |
| Monte Carlo: still meets 1 and 2 in 75 % of reshuffled runs | 13 |
| 200 trades on the stored 27 months (instead of on pace) | 1,477 |

Tables that pass every line:

- `ib-NQ-tf15-mid:mode=break` — average trade $155, 310 trades, 100 % of variants profitable, long $1,028,373 / short $508,927 (all variants), Monte Carlo 96 %
- `ib-NQ-tf30-mid:mode=break` — average trade $168, 310 trades, 100 % of variants profitable, long $1,098,993 / short $564,402 (all variants), Monte Carlo 98 %
- `ib-NQ-tf5-mid:mode=break` — average trade $142, 310 trades, 100 % of variants profitable, long $937,198 / short $467,277 (all variants), Monte Carlo 93 %

Tables that pass lines 1-6 (before the Monte Carlo line):

- `first_bar_mom-NQ-tf15-mid` — average trade $81, 210 trades, Monte Carlo 58 %
- `ib-NQ-tf15-mid:mode=break` — average trade $155, 310 trades, Monte Carlo 96 %
- `ib-NQ-tf30-mid:mode=break` — average trade $168, 310 trades, Monte Carlo 98 %
- `ib-NQ-tf5-mid:mode=break` — average trade $142, 310 trades, Monte Carlo 93 %
- `orb_confirm-NQ-tf15-pm:dir=long` — average trade $92, 281 trades, Monte Carlo 72 %
- `orb_confirm-NQ-tf5-pm:dir=long` — average trade $74, 291 trades, Monte Carlo 58 %
