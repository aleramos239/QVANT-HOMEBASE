## ledger_flow_inv_2NQ.csv — report card

```
NET -$2,716 · PF 1.00 · Sharpe -0.03 · WR 25.3% · MaxDD -$30,622 · 817 trades
```

**Equity curve** ($0 → -$2,716)

```
⣷⣶⣦⣦⣤⣤⣤⣀⣄⣄⣀⣄⣀⣄⣄⣄⣤⣄⣶⣿⣶⣶⣷⣷⣦⣤⣦⣦⣤⣦⣄⣀⣦⣦⣤⣶⣤⣤⣤⣦⣄⣦⣶⣦⣄⣦⣶⣶⣿⣿⣷⣦⣶⣶⣷⣷⣷⣿⣿⣷
```

**Edge inference** — EV -$3.32/trade · bootstrap 95% CI [-$121.29, $118.97] · P(EV ≤ 0): 52.2% · 10,000 resamples

**WR stability** — monthly WR 0.0%–50.0% (pooled 25.3%) · wobble 0.9× luck (steady) · worst 3-mo 19.0% (n=63) · 40 months

**Year by year (combined)**

| Year | Trades | Net | Win rate | PF | Sharpe | Max DD | Avg trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021 | 68 | -$21,144 | 17.6% | 0.63 | -3.20 | -$23,036 | -$310.94 |
| 2022 | 248 | $16,106 | 27.0% | 1.09 | 0.58 | -$19,466 | $64.94 |
| 2023 | 249 | -$5,732 | 24.9% | 0.97 | -0.21 | -$22,680 | -$23.02 |
| 2024 | 252 | $8,054 | 26.2% | 1.04 | 0.29 | -$24,494 | $31.96 |
| **All** | **817** | **-$2,716** | **25.3%** | **1.00** | **-0.03** | **-$30,622** | **-$3.32** |

**Cost ladder** — net edge vs friction multiple

| Friction | Net | $/trade | PF | Sharpe | Win rate | Max DD | |
|---|---:|---:|---:|---:|---:|---:|---|
| 0.5× | $4,637 | $5.68 | 1.008 | 0.05 | 25.3% | -$29,146 | alive |
| 1× | -$2,716 | -$3.32 | 0.996 | -0.03 | 25.3% | -$30,622 | **DEAD** · **as run** |
| 2× | -$17,422 | -$21.32 | 0.972 | -0.19 | 25.3% | -$34,016 | **DEAD** |
| 4× | -$46,834 | -$57.32 | 0.928 | -0.52 | 25.3% | -$55,296 | **DEAD** |

**Breakeven at 0.82× friction.** Under 2× — a routine slippage miss erases it. Friction is 122.7% of gross profit ($14,706 of $11,990).

**Breakeven multiple by year** — the pooled figure can hide a newer era that dies earlier

| Year | 0.5× | 1× | 2× | 4× | Breakeven |
|---|---:|---:|---:|---:|---:|
| 2021 | -$20,532 | -$21,144 | -$22,368 | -$24,816 | -16.27× |
| 2022 | $18,338 | $16,106 | $11,642 | $2,714 | 4.61× |
| 2023 | -$3,491 | -$5,732 | -$10,214 | -$19,178 | -0.28× |
| 2024 | $10,322 | $8,054 | $3,518 | -$5,554 | 2.78× |

> The ladder subtracts money and nothing else, so it is a **lower bound on the damage** — real added friction also moves fills, so trades appear and disappear. `onyx.lab.costcurve.slip_stress` re-runs the strategy and captures that; this cannot.

**Pooled — all years**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $32,538 | -$35,254 | -$2,716 |
| Total trades | 444 | 373 | 817 |
| Win rate | 27.3% | 23.1% | 25.3% |
| Profit factor | 1.099 | 0.879 | 0.996 |
| Sharpe (ann.) | 0.65 | -0.89 | -0.03 |
| Max drawdown | -$19,538 | -$40,738 | -$30,622 |
| Max run-up | $44,602 | $25,280 | $37,834 |
| Expectancy / trade | $73.28 | -$94.51 | -$3.32 |
| Avg win | $2,987.62 | $2,988.40 | $2,987.94 |
| Avg loss | -$1,018.46 | -$1,018.31 | -$1,018.39 |
| Payoff (avg W / avg L) | 2.93 | 2.93 | 2.93 |
| Avg R multiple | 0.07 | -0.09 | -0.00 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,038 | -$1,038 | -$1,038 |
| Smallest win | $2,462.00 | $2,682.00 | $2,462.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 4 / 1 | 2 / 1 | 4 / 1 |
| Win streak avg | 1.32 | 1.26 | 1.39 |
| Avg profit per win run | $3,929.37 | $3,779.44 | $4,151.03 |
| Best win run | $11,968 | $5,984 | $11,968 |
| Loss streak max / min | 17 / 1 | 18 / 1 | 17 / 1 |
| Loss streak avg | 3.47 | 4.16 | 4.07 |
| Avg loss per loss run | -$3,537.25 | -$4,235.59 | -$4,141.47 |
| Worst loss run | -$17,316 | -$18,324 | -$17,326 |
| Avg trade run-up | $1,371 | $1,336 | $1,355 |
| Max trade run-up | $3,020 | $3,020 | $3,020 |
| Avg trade run-down | $837 | $885 | $859 |
| Max trade run-down | $1,020 | $1,020 | $1,020 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2021**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$2,624 | -$18,520 | -$21,144 |
| Total trades | 38 | 30 | 68 |
| Win rate | 23.7% | 10.0% | 17.6% |
| Profit factor | 0.911 | 0.326 | 0.629 |
| Sharpe (ann.) | -0.63 | -8.01 | -3.20 |
| Max drawdown | -$11,332 | -$18,520 | -$23,036 |
| Max run-up | $10,888 | $4,966 | $10,950 |
| Expectancy / trade | -$69.05 | -$617.33 | -$310.94 |
| Avg win | $2,992.00 | $2,992.00 | $2,992.00 |
| Avg loss | -$1,019.03 | -$1,018.37 | -$1,018.71 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | -0.07 | -0.62 | -0.31 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,028 | -$1,028 | -$1,028 |
| Smallest win | $2,992.00 | $2,992.00 | $2,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 2 / 1 | 1 / 1 | 3 / 1 |
| Win streak avg | 1.50 | 1.00 | 1.50 |
| Avg profit per win run | $4,488.00 | $2,992.00 | $4,488.00 |
| Best win run | $5,984 | $2,992 | $8,976 |
| Loss streak max / min | 10 / 1 | 16 / 1 | 13 / 1 |
| Loss streak avg | 4.14 | 6.75 | 6.22 |
| Avg loss per loss run | -$4,221.71 | -$6,874.00 | -$6,338.67 |
| Worst loss run | -$10,190 | -$16,288 | -$13,234 |
| Avg trade run-up | $1,302 | $1,051 | $1,191 |
| Max trade run-up | $3,010 | $3,010 | $3,010 |
| Avg trade run-down | $854 | $938 | $891 |
| Max trade run-down | $1,010 | $1,010 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2022**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $7,898 | $8,208 | $16,106 |
| Total trades | 134 | 114 | 248 |
| Win rate | 26.9% | 27.2% | 27.0% |
| Profit factor | 1.079 | 1.097 | 1.087 |
| Sharpe (ann.) | 0.52 | 0.64 | 0.58 |
| Max drawdown | -$12,278 | -$17,072 | -$19,466 |
| Max run-up | $20,754 | $24,324 | $34,180 |
| Expectancy / trade | $58.94 | $72.00 | $64.94 |
| Avg win | $2,992.00 | $2,992.00 | $2,992.00 |
| Avg loss | -$1,018.51 | -$1,018.60 | -$1,018.55 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | 0.06 | 0.07 | 0.06 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,028 | -$1,028 | -$1,028 |
| Smallest win | $2,992.00 | $2,992.00 | $2,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 2 / 1 | 2 / 1 | 3 / 1 |
| Win streak avg | 1.33 | 1.41 | 1.49 |
| Avg profit per win run | $3,989.33 | $4,216.00 | $4,454.76 |
| Best win run | $5,984 | $5,984 | $8,976 |
| Loss streak max / min | 11 / 1 | 10 / 1 | 14 / 1 |
| Loss streak avg | 3.63 | 3.77 | 4.02 |
| Avg loss per loss run | -$3,696.81 | -$3,842.91 | -$4,096.84 |
| Worst loss run | -$11,198 | -$10,190 | -$14,272 |
| Avg trade run-up | $1,419 | $1,455 | $1,436 |
| Max trade run-up | $3,020 | $3,020 | $3,020 |
| Avg trade run-down | $835 | $867 | $850 |
| Max trade run-down | $1,010 | $1,010 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2023**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $15,346 | -$21,078 | -$5,732 |
| Total trades | 138 | 111 | 249 |
| Win rate | 28.3% | 20.7% | 24.9% |
| Profit factor | 1.152 | 0.765 | 0.970 |
| Sharpe (ann.) | 0.98 | -1.85 | -0.21 |
| Max drawdown | -$10,200 | -$29,744 | -$22,680 |
| Max run-up | $20,908 | $8,728 | $22,050 |
| Expectancy / trade | $111.20 | -$189.89 | -$23.02 |
| Avg win | $2,978.41 | $2,978.52 | $2,978.45 |
| Avg loss | -$1,018.30 | -$1,018.00 | -$1,018.16 |
| Payoff (avg W / avg L) | 2.92 | 2.93 | 2.93 |
| Avg R multiple | 0.11 | -0.19 | -0.02 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,038 | -$1,018 | -$1,038 |
| Smallest win | $2,462.00 | $2,682.00 | $2,462.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 3 / 1 | 2 / 1 | 4 / 1 |
| Win streak avg | 1.30 | 1.15 | 1.35 |
| Avg profit per win run | $3,871.93 | $3,425.30 | $4,014.43 |
| Best win run | $8,976 | $5,984 | $11,968 |
| Loss streak max / min | 10 / 1 | 14 / 1 | 17 / 1 |
| Loss streak avg | 3.19 | 4.63 | 4.07 |
| Avg loss per loss run | -$3,252.00 | -$4,714.95 | -$4,139.04 |
| Worst loss run | -$10,200 | -$14,252 | -$17,326 |
| Avg trade run-up | $1,495 | $1,204 | $1,365 |
| Max trade run-up | $3,010 | $3,020 | $3,020 |
| Avg trade run-down | $828 | $891 | $856 |
| Max trade run-down | $1,020 | $1,000 | $1,020 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2024**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $11,918 | -$3,864 | $8,054 |
| Total trades | 134 | 118 | 252 |
| Win rate | 27.6% | 24.6% | 26.2% |
| Profit factor | 1.121 | 0.957 | 1.043 |
| Sharpe (ann.) | 0.78 | -0.30 | 0.29 |
| Max drawdown | -$19,538 | -$18,510 | -$24,494 |
| Max run-up | $27,642 | $22,650 | $30,996 |
| Expectancy / trade | $88.94 | -$32.75 | $31.96 |
| Avg win | $2,992.00 | $2,992.00 | $2,992.00 |
| Avg loss | -$1,018.41 | -$1,018.34 | -$1,018.38 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | 0.09 | -0.03 | 0.03 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,038 | -$1,038 | -$1,038 |
| Smallest win | $2,992.00 | $2,992.00 | $2,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 4 / 1 | 2 / 1 | 3 / 1 |
| Win streak avg | 1.28 | 1.26 | 1.32 |
| Avg profit per win run | $3,817.38 | $3,772.52 | $3,949.44 |
| Best win run | $11,968 | $5,984 | $8,976 |
| Loss streak max / min | 17 / 1 | 18 / 1 | 16 / 1 |
| Loss streak avg | 3.23 | 3.71 | 3.65 |
| Avg loss per loss run | -$3,292.87 | -$3,776.33 | -$3,714.08 |
| Worst loss run | -$17,316 | -$18,324 | -$16,288 |
| Avg trade run-up | $1,214 | $1,416 | $1,309 |
| Max trade run-up | $3,020 | $3,020 | $3,020 |
| Avg trade run-down | $843 | $884 | $862 |
| Max trade run-down | $1,020 | $1,020 | $1,020 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

> Cost ladder basis: $9 round-turn per contract.
wrote /Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/out_inv_flow_1to3/metrics_flow_inv.json

