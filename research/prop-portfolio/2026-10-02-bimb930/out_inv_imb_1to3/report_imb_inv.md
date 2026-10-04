## ledger_imb_inv_2NQ.csv — report card

```
NET -$25,620 · PF 0.96 · Sharpe -0.31 · WR 24.6% · MaxDD -$58,622 · 765 trades
```

**Equity curve** ($0 → -$25,620)

```
⣿⣿⣿⣿⣷⣷⣷⣶⣶⣦⣶⣶⣷⣶⣶⣤⣤⣤⣄⣄⣄⣤⣦⣤⣄⣤⣄⣄⣄⣄⣄⣤⣄⣤⣄⣄⣄⣤⣤⣄⣀⣄⣄⣀⣀⣀⣀⣀⣀⣀⣀⣀⣤⣄⣀⣄⣄⣦⣤⣤
```

**Edge inference** — EV -$33.49/trade · bootstrap 95% CI [-$153.36, $90.84] · P(EV ≤ 0): 70.3% · 10,000 resamples

**WR stability** — monthly WR 5.0%–40.9% (pooled 24.6%) · wobble 0.7× luck (steady) · worst 3-mo 15.5% (n=58) · 40 months

**Year by year (combined)**

| Year | Trades | Net | Win rate | PF | Sharpe | Max DD | Avg trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021 | 63 | -$8,004 | 22.2% | 0.84 | -1.20 | -$19,600 | -$127.05 |
| 2022 | 235 | -$18,800 | 23.4% | 0.90 | -0.75 | -$36,758 | -$80.00 |
| 2023 | 234 | -$10,182 | 24.4% | 0.94 | -0.40 | -$25,646 | -$43.51 |
| 2024 | 233 | $11,366 | 26.6% | 1.07 | 0.44 | -$19,972 | $48.78 |
| **All** | **765** | **-$25,620** | **24.6%** | **0.96** | **-0.31** | **-$58,622** | **-$33.49** |

**Cost ladder** — net edge vs friction multiple

| Friction | Net | $/trade | PF | Sharpe | Win rate | Max DD | |
|---|---:|---:|---:|---:|---:|---:|---|
| 0.5× | -$18,735 | -$24.49 | 0.968 | -0.23 | 24.6% | -$53,501 | **DEAD** |
| 1× | -$25,620 | -$33.49 | 0.956 | -0.31 | 24.6% | -$58,622 | **DEAD** · **as run** |
| 2× | -$39,390 | -$51.49 | 0.934 | -0.47 | 24.6% | -$69,972 | **DEAD** |
| 4× | -$66,930 | -$87.49 | 0.892 | -0.80 | 24.6% | -$92,724 | **DEAD** |

**Breakeven at -0.86× friction.** Under 2× — a routine slippage miss erases it.

**Breakeven multiple by year** — the pooled figure can hide a newer era that dies earlier

| Year | 0.5× | 1× | 2× | 4× | Breakeven |
|---|---:|---:|---:|---:|---:|
| 2021 | -$7,437 | -$8,004 | -$9,138 | -$11,406 | -6.06× |
| 2022 | -$16,685 | -$18,800 | -$23,030 | -$31,490 | -3.44× |
| 2023 | -$8,076 | -$10,182 | -$14,394 | -$22,818 | -1.42× |
| 2024 | $13,463 | $11,366 | $7,172 | -$1,216 | 3.71× |

> The ladder subtracts money and nothing else, so it is a **lower bound on the damage** — real added friction also moves fills, so trades appear and disappear. `onyx.lab.costcurve.slip_stress` re-runs the strategy and captures that; this cannot.

**Pooled — all years**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$22,698 | -$2,922 | -$25,620 |
| Total trades | 451 | 314 | 765 |
| Win rate | 24.2% | 25.2% | 24.6% |
| Profit factor | 0.935 | 0.988 | 0.956 |
| Sharpe (ann.) | -0.47 | -0.08 | -0.31 |
| Max drawdown | -$36,124 | -$48,464 | -$58,622 |
| Max run-up | $28,616 | $44,710 | $28,800 |
| Expectancy / trade | -$50.33 | -$9.31 | -$33.49 |
| Avg win | $2,987.14 | $2,992.00 | $2,989.18 |
| Avg loss | -$1,018.41 | -$1,018.26 | -$1,018.35 |
| Payoff (avg W / avg L) | 2.93 | 2.94 | 2.94 |
| Avg R multiple | -0.05 | -0.01 | -0.03 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,028 | -$1,028 | -$1,028 |
| Smallest win | $2,462.00 | $2,992.00 | $2,462.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 4 / 1 | 5 / 1 | 4 / 1 |
| Win streak avg | 1.31 | 1.32 | 1.27 |
| Avg profit per win run | $3,922.87 | $3,939.47 | $3,797.07 |
| Best win run | $11,968 | $14,960 | $11,968 |
| Loss streak max / min | 18 / 1 | 12 / 1 | 19 / 1 |
| Loss streak avg | 4.07 | 3.85 | 3.87 |
| Avg loss per loss run | -$4,146.38 | -$3,922.79 | -$3,943.53 |
| Worst loss run | -$18,324 | -$12,216 | -$19,342 |
| Avg trade run-up | $1,341 | $1,380 | $1,357 |
| Max trade run-up | $3,020 | $3,020 | $3,020 |
| Avg trade run-down | $864 | $859 | $862 |
| Max trade run-down | $1,010 | $1,010 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2021**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$2,418 | -$5,586 | -$8,004 |
| Total trades | 26 | 37 | 63 |
| Win rate | 23.1% | 21.6% | 22.2% |
| Profit factor | 0.881 | 0.811 | 0.840 |
| Sharpe (ann.) | -0.86 | -1.43 | -1.20 |
| Max drawdown | -$13,244 | -$11,508 | -$19,600 |
| Max run-up | $12,924 | $6,940 | $14,712 |
| Expectancy / trade | -$93.00 | -$150.97 | -$127.05 |
| Avg win | $2,992.00 | $2,992.00 | $2,992.00 |
| Avg loss | -$1,018.50 | -$1,018.00 | -$1,018.20 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | -0.09 | -0.15 | -0.13 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,028 | -$1,018 | -$1,028 |
| Smallest win | $2,992.00 | $2,992.00 | $2,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 3 / 1 | 2 / 1 | 3 / 1 |
| Win streak avg | 1.50 | 1.14 | 1.27 |
| Avg profit per win run | $4,488.00 | $3,419.43 | $3,808.00 |
| Best win run | $8,976 | $5,984 | $8,976 |
| Loss streak max / min | 13 / 1 | 8 / 1 | 10 / 1 |
| Loss streak avg | 4.00 | 3.62 | 4.08 |
| Avg loss per loss run | -$4,074.00 | -$3,690.25 | -$4,157.67 |
| Worst loss run | -$13,244 | -$8,144 | -$10,190 |
| Avg trade run-up | $1,468 | $1,366 | $1,408 |
| Max trade run-up | $3,010 | $3,010 | $3,010 |
| Avg trade run-down | $878 | $894 | $887 |
| Max trade run-down | $1,010 | $1,000 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2022**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$5,232 | -$13,568 | -$18,800 |
| Total trades | 139 | 96 | 235 |
| Win rate | 24.5% | 21.9% | 23.4% |
| Profit factor | 0.951 | 0.822 | 0.897 |
| Sharpe (ann.) | -0.35 | -1.35 | -0.75 |
| Max drawdown | -$20,642 | -$23,796 | -$36,758 |
| Max run-up | $16,552 | $11,824 | $17,426 |
| Expectancy / trade | -$37.64 | -$141.33 | -$80.00 |
| Avg win | $2,992.00 | $2,992.00 | $2,992.00 |
| Avg loss | -$1,018.67 | -$1,018.67 | -$1,018.67 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | -0.04 | -0.14 | -0.08 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,028 | -$1,028 | -$1,028 |
| Smallest win | $2,992.00 | $2,992.00 | $2,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 3 / 1 | 2 / 1 | 3 / 1 |
| Win streak avg | 1.17 | 1.24 | 1.17 |
| Avg profit per win run | $3,507.86 | $3,696.00 | $3,501.28 |
| Best win run | $8,976 | $5,984 | $8,976 |
| Loss streak max / min | 10 / 1 | 12 / 1 | 19 / 1 |
| Loss streak avg | 3.62 | 4.41 | 3.83 |
| Avg loss per loss run | -$3,688.28 | -$4,494.12 | -$3,901.28 |
| Worst loss run | -$10,190 | -$12,216 | -$19,342 |
| Avg trade run-up | $1,345 | $1,338 | $1,342 |
| Max trade run-up | $3,020 | $3,010 | $3,020 |
| Avg trade run-down | $857 | $895 | $872 |
| Max trade run-down | $1,010 | $1,010 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2023**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $10,214 | -$20,396 | -$10,182 |
| Total trades | 147 | 87 | 234 |
| Win rate | 27.2% | 19.5% | 24.4% |
| Profit factor | 1.094 | 0.714 | 0.943 |
| Sharpe (ann.) | 0.62 | -2.33 | -0.40 |
| Max drawdown | -$14,386 | -$26,380 | -$25,646 |
| Max run-up | $21,864 | $7,958 | $21,466 |
| Expectancy / trade | $69.48 | -$234.44 | -$43.51 |
| Avg win | $2,978.75 | $2,992.00 | $2,982.70 |
| Avg loss | -$1,018.09 | -$1,018.00 | -$1,018.06 |
| Payoff (avg W / avg L) | 2.93 | 2.94 | 2.93 |
| Avg R multiple | 0.07 | -0.23 | -0.04 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,028 | -$1,018 | -$1,028 |
| Smallest win | $2,462.00 | $2,992.00 | $2,462.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 4 / 1 | 2 / 1 | 4 / 1 |
| Win streak avg | 1.48 | 1.06 | 1.33 |
| Avg profit per win run | $4,412.96 | $3,179.00 | $3,953.81 |
| Best win run | $11,968 | $5,984 | $11,968 |
| Loss streak max / min | 12 / 1 | 12 / 1 | 13 / 1 |
| Loss streak avg | 3.82 | 4.67 | 4.12 |
| Avg loss per loss run | -$3,890.57 | -$4,750.67 | -$4,190.60 |
| Worst loss run | -$12,216 | -$12,216 | -$13,234 |
| Avg trade run-up | $1,488 | $1,162 | $1,367 |
| Max trade run-up | $3,020 | $3,020 | $3,020 |
| Avg trade run-down | $838 | $875 | $852 |
| Max trade run-down | $1,010 | $1,000 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2024**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$25,262 | $36,628 | $11,366 |
| Total trades | 139 | 94 | 233 |
| Win rate | 20.9% | 35.1% | 26.6% |
| Profit factor | 0.775 | 1.590 | 1.065 |
| Sharpe (ann.) | -1.76 | 3.21 | 0.44 |
| Max drawdown | -$35,820 | -$8,268 | -$19,972 |
| Max run-up | $8,976 | $41,780 | $28,800 |
| Expectancy / trade | -$181.74 | $389.66 | $48.78 |
| Avg win | $2,992.00 | $2,992.00 | $2,992.00 |
| Avg loss | -$1,018.45 | -$1,018.16 | -$1,018.35 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | -0.18 | 0.39 | 0.05 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,028 | -$1,028 | -$1,028 |
| Smallest win | $2,992.00 | $2,992.00 | $2,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 3 / 1 | 5 / 1 | 4 / 1 |
| Win streak avg | 1.26 | 1.57 | 1.29 |
| Avg profit per win run | $3,772.52 | $4,701.71 | $3,864.67 |
| Best win run | $8,976 | $14,960 | $11,968 |
| Loss streak max / min | 18 / 1 | 7 / 1 | 13 / 1 |
| Loss streak avg | 4.58 | 2.90 | 3.56 |
| Avg loss per loss run | -$4,667.92 | -$2,957.52 | -$3,627.88 |
| Worst loss run | -$18,324 | -$7,126 | -$13,234 |
| Avg trade run-up | $1,158 | $1,631 | $1,349 |
| Max trade run-up | $3,020 | $3,020 | $3,020 |
| Avg trade run-down | $895 | $795 | $854 |
| Max trade run-down | $1,010 | $1,010 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

> Cost ladder basis: $9 round-turn per contract.
wrote /Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/out_inv_imb_1to3/metrics_imb_inv.json

