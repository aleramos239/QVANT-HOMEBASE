## ledger_flow_2NQ.csv — report card

```
NET -$74,026 · PF 0.88 · Sharpe -0.85 · WR 23.1% · MaxDD -$114,702 · 817 trades
```

**Equity curve** ($0 → -$74,026)

```
⣿⣿⣿⣿⣿⣿⣿⣿⣿⣷⣿⣷⣷⣶⣷⣶⣶⣶⣦⣦⣦⣦⣦⣤⣦⣤⣤⣤⣦⣤⣤⣦⣤⣤⣤⣤⣤⣤⣤⣤⣦⣦⣤⣤⣤⣄⣄⣄⣀⣀⣀⣄⣄⣀⣀⣀⣄⣤⣄⣄
```

**Edge inference** — EV -$90.61/trade · bootstrap 95% CI [-$208.39, $27.23] · P(EV ≤ 0): 93.3% · 10,000 resamples

**WR stability** — monthly WR 5.0%–43.5% (pooled 23.1%) · wobble 0.7× luck (steady) · worst 3-mo 12.9% (n=62) · 40 months

**Year by year (combined)**

| Year | Trades | Net | Win rate | PF | Sharpe | Max DD | Avg trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021 | 68 | -$5,074 | 23.5% | 0.90 | -0.69 | -$15,652 | -$74.62 |
| 2022 | 248 | -$56,094 | 19.8% | 0.72 | -2.24 | -$61,060 | -$226.19 |
| 2023 | 249 | $3,148 | 25.7% | 1.02 | 0.11 | -$20,866 | $12.64 |
| 2024 | 252 | -$16,006 | 23.8% | 0.92 | -0.59 | -$50,884 | -$63.52 |
| **All** | **817** | **-$74,026** | **23.1%** | **0.88** | **-0.85** | **-$114,702** | **-$90.61** |

**Cost ladder** — net edge vs friction multiple

| Friction | Net | $/trade | PF | Sharpe | Win rate | Max DD | |
|---|---:|---:|---:|---:|---:|---:|---|
| 0.5× | -$66,673 | -$81.61 | 0.895 | -0.77 | 23.1% | -$108,726 | **DEAD** |
| 1× | -$74,026 | -$90.61 | 0.884 | -0.85 | 23.1% | -$114,702 | **DEAD** · **as run** |
| 2× | -$88,732 | -$108.61 | 0.864 | -1.02 | 23.1% | -$126,654 | **DEAD** |
| 4× | -$118,144 | -$144.61 | 0.825 | -1.36 | 23.1% | -$150,558 | **DEAD** |

**Breakeven at -4.03× friction.** Under 2× — a routine slippage miss erases it.

**Breakeven multiple by year** — the pooled figure can hide a newer era that dies earlier

| Year | 0.5× | 1× | 2× | 4× | Breakeven |
|---|---:|---:|---:|---:|---:|
| 2021 | -$4,462 | -$5,074 | -$6,298 | -$8,746 | -3.15× |
| 2022 | -$53,862 | -$56,094 | -$60,558 | -$69,486 | -11.57× |
| 2023 | $5,389 | $3,148 | -$1,334 | -$10,298 | 1.70× |
| 2024 | -$13,738 | -$16,006 | -$20,542 | -$29,614 | -2.53× |

> The ladder subtracts money and nothing else, so it is a **lower bound on the damage** — real added friction also moves fills, so trades appear and disappear. `onyx.lab.costcurve.slip_stress` re-runs the strategy and captures that; this cannot.

**Pooled — all years**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$55,034 | -$18,992 | -$74,026 |
| Total trades | 373 | 444 | 817 |
| Win rate | 21.7% | 24.3% | 23.1% |
| Profit factor | 0.815 | 0.944 | 0.884 |
| Sharpe (ann.) | -1.41 | -0.39 | -0.85 |
| Max drawdown | -$59,804 | -$70,892 | -$114,702 |
| Max run-up | $40,390 | $42,468 | $35,322 |
| Expectancy / trade | -$147.54 | -$42.77 | -$90.61 |
| Avg win | $2,992.00 | $2,992.00 | $2,992.00 |
| Avg loss | -$1,018.45 | -$1,018.24 | -$1,018.33 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | -0.15 | -0.04 | -0.09 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,038 | -$1,048 | -$1,048 |
| Smallest win | $2,992.00 | $2,992.00 | $2,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 4 / 1 | 4 / 1 | 5 / 1 |
| Win streak avg | 1.35 | 1.44 | 1.33 |
| Avg profit per win run | $4,039.20 | $4,308.48 | $3,982.31 |
| Best win run | $11,968 | $11,968 | $14,960 |
| Loss streak max / min | 37 / 1 | 23 / 1 | 22 / 1 |
| Loss streak avg | 4.79 | 4.42 | 4.39 |
| Avg loss per loss run | -$4,875.18 | -$4,501.68 | -$4,472.13 |
| Worst loss run | -$37,676 | -$23,424 | -$22,426 |
| Avg trade run-up | $1,333 | $1,364 | $1,350 |
| Max trade run-up | $3,030 | $3,020 | $3,030 |
| Avg trade run-down | $874 | $871 | $873 |
| Max trade run-down | $1,020 | $1,030 | $1,030 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2021**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$10,500 | $5,426 | -$5,074 |
| Total trades | 30 | 38 | 68 |
| Win rate | 16.7% | 28.9% | 23.5% |
| Profit factor | 0.588 | 1.197 | 0.904 |
| Sharpe (ann.) | -3.65 | 1.23 | -0.69 |
| Max drawdown | -$12,474 | -$8,144 | -$15,652 |
| Max run-up | $3,938 | $11,596 | $11,906 |
| Expectancy / trade | -$350.00 | $142.79 | -$74.62 |
| Avg win | $2,992.00 | $2,992.00 | $2,992.00 |
| Avg loss | -$1,018.40 | -$1,018.00 | -$1,018.19 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | -0.35 | 0.14 | -0.07 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,028 | -$1,018 | -$1,028 |
| Smallest win | $2,992.00 | $2,992.00 | $2,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 1 / 1 | 2 / 1 | 3 / 1 |
| Win streak avg | 1.00 | 1.38 | 1.23 |
| Avg profit per win run | $2,992.00 | $4,114.00 | $3,682.46 |
| Best win run | $2,992 | $5,984 | $8,976 |
| Loss streak max / min | 9 / 1 | 8 / 1 | 10 / 1 |
| Loss streak avg | 4.17 | 3.00 | 3.71 |
| Avg loss per loss run | -$4,243.33 | -$3,054.00 | -$3,781.86 |
| Worst loss run | -$9,162 | -$8,144 | -$10,180 |
| Avg trade run-up | $1,258 | $1,465 | $1,374 |
| Max trade run-up | $3,010 | $3,010 | $3,010 |
| Avg trade run-down | $907 | $886 | $895 |
| Max trade run-down | $1,010 | $1,000 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2022**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$31,912 | -$24,182 | -$56,094 |
| Total trades | 114 | 134 | 248 |
| Win rate | 18.4% | 20.9% | 19.8% |
| Profit factor | 0.663 | 0.776 | 0.723 |
| Sharpe (ann.) | -2.85 | -1.75 | -2.24 |
| Max drawdown | -$32,868 | -$36,084 | -$61,060 |
| Max run-up | $8,904 | $11,658 | $12,924 |
| Expectancy / trade | -$279.93 | -$180.46 | -$226.19 |
| Avg win | $2,992.00 | $2,992.00 | $2,992.00 |
| Avg loss | -$1,018.75 | -$1,018.47 | -$1,018.60 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | -0.28 | -0.18 | -0.23 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,038 | -$1,048 | -$1,048 |
| Smallest win | $2,992.00 | $2,992.00 | $2,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 2 / 1 | 3 / 1 | 3 / 1 |
| Win streak avg | 1.05 | 1.40 | 1.32 |
| Avg profit per win run | $3,141.60 | $4,188.80 | $3,962.38 |
| Best win run | $5,984 | $8,976 | $8,976 |
| Loss streak max / min | 12 / 1 | 23 / 1 | 22 / 1 |
| Loss streak avg | 4.43 | 5.05 | 5.24 |
| Avg loss per loss run | -$4,511.62 | -$5,140.86 | -$5,334.26 |
| Worst loss run | -$12,246 | -$23,424 | -$22,426 |
| Avg trade run-up | $1,283 | $1,283 | $1,283 |
| Max trade run-up | $3,020 | $3,020 | $3,020 |
| Avg trade run-down | $885 | $893 | $889 |
| Max trade run-down | $1,020 | $1,030 | $1,030 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2023**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $35,362 | -$32,214 | $3,148 |
| Total trades | 111 | 138 | 249 |
| Win rate | 33.3% | 19.6% | 25.7% |
| Profit factor | 1.469 | 0.715 | 1.017 |
| Sharpe (ann.) | 2.66 | -2.32 | 0.11 |
| Max drawdown | -$9,162 | -$35,480 | -$20,866 |
| Max run-up | $39,434 | $14,774 | $25,874 |
| Expectancy / trade | $318.58 | -$233.43 | $12.64 |
| Avg win | $2,992.00 | $2,992.00 | $2,992.00 |
| Avg loss | -$1,018.14 | -$1,018.00 | -$1,018.05 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | 0.32 | -0.23 | 0.01 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,028 | -$1,018 | -$1,028 |
| Smallest win | $2,992.00 | $2,992.00 | $2,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 4 / 1 | 4 / 1 | 5 / 1 |
| Win streak avg | 1.68 | 1.35 | 1.39 |
| Avg profit per win run | $5,032.00 | $4,039.20 | $4,162.78 |
| Best win run | $11,968 | $11,968 | $14,960 |
| Loss streak max / min | 9 / 1 | 17 / 1 | 13 / 1 |
| Loss streak avg | 3.22 | 5.29 | 3.94 |
| Avg loss per loss run | -$3,275.74 | -$5,380.86 | -$4,007.23 |
| Worst loss run | -$9,162 | -$17,306 | -$13,234 |
| Avg trade run-up | $1,607 | $1,170 | $1,365 |
| Max trade run-up | $3,020 | $3,010 | $3,020 |
| Avg trade run-down | $803 | $896 | $854 |
| Max trade run-down | $1,010 | $1,000 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2024**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$47,984 | $31,978 | -$16,006 |
| Total trades | 118 | 134 | 252 |
| Win rate | 15.3% | 31.3% | 23.8% |
| Profit factor | 0.529 | 1.341 | 0.918 |
| Sharpe (ann.) | -4.46 | 2.03 | -0.59 |
| Max drawdown | -$53,772 | -$15,300 | -$50,884 |
| Max run-up | $11,968 | $42,468 | $35,322 |
| Expectancy / trade | -$406.64 | $238.64 | -$63.52 |
| Avg win | $2,992.00 | $2,992.00 | $2,992.00 |
| Avg loss | -$1,018.40 | -$1,018.33 | -$1,018.36 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | -0.41 | 0.24 | -0.06 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,028 | -$1,038 | -$1,038 |
| Smallest win | $2,992.00 | $2,992.00 | $2,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 4 / 1 | 4 / 1 | 4 / 1 |
| Win streak avg | 1.38 | 1.56 | 1.30 |
| Avg profit per win run | $4,142.77 | $4,654.22 | $3,902.61 |
| Best win run | $11,968 | $11,968 | $11,968 |
| Loss streak max / min | 37 / 2 | 15 / 1 | 14 / 1 |
| Loss streak avg | 7.69 | 3.41 | 4.17 |
| Avg loss per loss run | -$7,833.85 | -$3,469.85 | -$4,250.57 |
| Worst loss run | -$37,676 | -$15,300 | -$14,252 |
| Avg trade run-up | $1,141 | $1,617 | $1,394 |
| Max trade run-up | $3,030 | $3,020 | $3,030 |
| Avg trade run-down | $923 | $820 | $868 |
| Max trade run-down | $1,010 | $1,020 | $1,020 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

> Cost ladder basis: $9 round-turn per contract.
wrote /Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/out_1to3_flow/metrics_flow.json

