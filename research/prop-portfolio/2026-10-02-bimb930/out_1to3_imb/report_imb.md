## ledger_imb_2NQ.csv — report card

```
NET -$33,410 · PF 0.94 · Sharpe -0.40 · WR 24.3% · MaxDD -$57,248 · 765 trades
```

**Equity curve** ($0 → -$33,410)

```
⣿⣿⣷⣷⣶⣶⣷⣶⣷⣷⣶⣦⣤⣤⣦⣦⣶⣦⣶⣶⣦⣤⣤⣄⣄⣄⣀⣄⣄⣄⣀⣀⣄⣀⣄⣄⣤⣄⣄⣤⣶⣦⣦⣤⣄⣄⣦⣄⣄⣄⣄⣄⣀⣀⣀⣄⣤⣄⣤⣤
```

**Edge inference** — EV -$43.67/trade · bootstrap 95% CI [-$164.58, $77.01] · P(EV ≤ 0): 77.0% · 10,000 resamples

**WR stability** — monthly WR 0.0%–40.0% (pooled 24.3%) · wobble 0.6× luck (steady) · worst 3-mo 17.4% (n=46) · 40 months

**Year by year (combined)**

| Year | Trades | Net | Win rate | PF | Sharpe | Max DD | Avg trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021 | 63 | -$16,044 | 19.0% | 0.69 | -2.55 | -$21,956 | -$254.67 |
| 2022 | 235 | -$22,790 | 23.0% | 0.88 | -0.91 | -$31,804 | -$96.98 |
| 2023 | 234 | $10,088 | 26.5% | 1.06 | 0.39 | -$21,688 | $43.11 |
| 2024 | 233 | -$4,664 | 24.9% | 0.97 | -0.18 | -$29,458 | -$20.02 |
| **All** | **765** | **-$33,410** | **24.3%** | **0.94** | **-0.40** | **-$57,248** | **-$43.67** |

**Cost ladder** — net edge vs friction multiple

| Friction | Net | $/trade | PF | Sharpe | Win rate | Max DD | |
|---|---:|---:|---:|---:|---:|---:|---|
| 0.5× | -$26,525 | -$34.67 | 0.955 | -0.32 | 24.3% | -$51,495 | **DEAD** |
| 1× | -$33,410 | -$43.67 | 0.943 | -0.40 | 24.3% | -$57,248 | **DEAD** · **as run** |
| 2× | -$47,180 | -$61.67 | 0.921 | -0.57 | 24.3% | -$69,596 | **DEAD** |
| 4× | -$74,720 | -$97.67 | 0.880 | -0.90 | 24.3% | -$94,292 | **DEAD** |

**Breakeven at -1.43× friction.** Under 2× — a routine slippage miss erases it.

**Breakeven multiple by year** — the pooled figure can hide a newer era that dies earlier

| Year | 0.5× | 1× | 2× | 4× | Breakeven |
|---|---:|---:|---:|---:|---:|
| 2021 | -$15,477 | -$16,044 | -$17,178 | -$19,446 | -13.15× |
| 2022 | -$20,675 | -$22,790 | -$27,020 | -$35,480 | -4.39× |
| 2023 | $12,194 | $10,088 | $5,876 | -$2,548 | 3.40× |
| 2024 | -$2,567 | -$4,664 | -$8,858 | -$17,246 | -0.11× |

> The ladder subtracts money and nothing else, so it is a **lower bound on the damage** — real added friction also moves fills, so trades appear and disappear. `onyx.lab.costcurve.slip_stress` re-runs the strategy and captures that; this cannot.

**Pooled — all years**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $1,068 | -$34,478 | -$33,410 |
| Total trades | 314 | 451 | 765 |
| Win rate | 25.5% | 23.5% | 24.3% |
| Profit factor | 1.004 | 0.902 | 0.943 |
| Sharpe (ann.) | 0.03 | -0.71 | -0.40 |
| Max drawdown | -$31,452 | -$56,814 | -$57,248 |
| Max run-up | $45,020 | $29,710 | $31,378 |
| Expectancy / trade | $3.40 | -$76.45 | -$43.67 |
| Avg win | $2,992.00 | $2,989.08 | $2,990.33 |
| Avg loss | -$1,018.34 | -$1,018.32 | -$1,018.33 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | 0.00 | -0.08 | -0.04 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,038 | -$1,048 | -$1,048 |
| Smallest win | $2,992.00 | $2,682.00 | $2,682.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 4 / 1 | 3 / 1 | 5 / 1 |
| Win streak avg | 1.48 | 1.25 | 1.33 |
| Avg profit per win run | $4,432.59 | $3,727.55 | $3,972.87 |
| Best win run | $11,968 | $8,976 | $14,960 |
| Loss streak max / min | 16 / 1 | 13 / 1 | 15 / 1 |
| Loss streak avg | 4.25 | 4.06 | 4.11 |
| Avg loss per loss run | -$4,332.58 | -$4,133.18 | -$4,181.65 |
| Worst loss run | -$16,318 | -$13,234 | -$15,270 |
| Avg trade run-up | $1,341 | $1,351 | $1,346 |
| Max trade run-up | $3,030 | $3,020 | $3,030 |
| Avg trade run-down | $842 | $885 | $867 |
| Max trade run-down | $1,020 | $1,030 | $1,030 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2021**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$5,606 | -$10,438 | -$16,044 |
| Total trades | 37 | 26 | 63 |
| Win rate | 21.6% | 15.4% | 19.0% |
| Profit factor | 0.810 | 0.534 | 0.691 |
| Sharpe (ann.) | -1.44 | -4.32 | -2.55 |
| Max drawdown | -$14,510 | -$13,234 | -$21,956 |
| Max run-up | $5,984 | $5,922 | $9,932 |
| Expectancy / trade | -$151.51 | -$401.46 | -$254.67 |
| Avg win | $2,992.00 | $2,992.00 | $2,992.00 |
| Avg loss | -$1,018.69 | -$1,018.45 | -$1,018.59 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | -0.15 | -0.40 | -0.25 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,028 | -$1,028 | -$1,028 |
| Smallest win | $2,992.00 | $2,992.00 | $2,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 2 / 1 | 1 / 1 | 3 / 1 |
| Win streak avg | 1.33 | 1.00 | 1.33 |
| Avg profit per win run | $3,989.33 | $2,992.00 | $3,989.33 |
| Best win run | $5,984 | $2,992 | $8,976 |
| Loss streak max / min | 8 / 1 | 13 / 1 | 11 / 1 |
| Loss streak avg | 4.14 | 4.40 | 5.10 |
| Avg loss per loss run | -$4,220.29 | -$4,481.20 | -$5,194.80 |
| Worst loss run | -$8,154 | -$13,234 | -$11,208 |
| Avg trade run-up | $1,132 | $1,119 | $1,127 |
| Max trade run-up | $3,010 | $3,010 | $3,010 |
| Avg trade run-down | $860 | $932 | $890 |
| Max trade run-down | $1,010 | $1,010 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2022**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$17,578 | -$5,212 | -$22,790 |
| Total trades | 96 | 139 | 235 |
| Win rate | 20.8% | 24.5% | 23.0% |
| Profit factor | 0.773 | 0.951 | 0.876 |
| Sharpe (ann.) | -1.78 | -0.34 | -0.91 |
| Max drawdown | -$23,786 | -$20,866 | -$31,804 |
| Max run-up | $19,802 | $14,650 | $21,730 |
| Expectancy / trade | -$183.10 | -$37.50 | -$96.98 |
| Avg win | $2,992.00 | $2,992.00 | $2,992.00 |
| Avg loss | -$1,018.66 | -$1,018.48 | -$1,018.55 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | -0.18 | -0.04 | -0.10 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,038 | -$1,048 | -$1,048 |
| Smallest win | $2,992.00 | $2,992.00 | $2,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 3 / 1 | 2 / 1 | 3 / 1 |
| Win streak avg | 1.43 | 1.21 | 1.35 |
| Avg profit per win run | $4,274.29 | $3,633.14 | $4,039.20 |
| Best win run | $8,976 | $5,984 | $8,976 |
| Loss streak max / min | 16 / 1 | 11 / 1 | 15 / 1 |
| Loss streak avg | 5.07 | 3.62 | 4.41 |
| Avg loss per loss run | -$5,161.20 | -$3,687.59 | -$4,496.54 |
| Worst loss run | -$16,318 | -$11,198 | -$15,270 |
| Avg trade run-up | $1,343 | $1,386 | $1,368 |
| Max trade run-up | $3,020 | $3,020 | $3,020 |
| Avg trade run-down | $865 | $871 | $868 |
| Max trade run-down | $1,020 | $1,030 | $1,030 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2023**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $35,734 | -$25,646 | $10,088 |
| Total trades | 87 | 147 | 234 |
| Win rate | 35.6% | 21.1% | 26.5% |
| Profit factor | 1.627 | 0.783 | 1.058 |
| Sharpe (ann.) | 3.38 | -1.69 | 0.39 |
| Max drawdown | -$9,286 | -$35,232 | -$21,688 |
| Max run-up | $41,072 | $15,606 | $31,378 |
| Expectancy / trade | $410.74 | -$174.46 | $43.11 |
| Avg win | $2,992.00 | $2,982.00 | $2,987.00 |
| Avg loss | -$1,018.18 | -$1,018.00 | -$1,018.06 |
| Payoff (avg W / avg L) | 2.94 | 2.93 | 2.93 |
| Avg R multiple | 0.41 | -0.17 | 0.04 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,028 | -$1,018 | -$1,028 |
| Smallest win | $2,992.00 | $2,682.00 | $2,682.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 4 / 1 | 3 / 1 | 5 / 1 |
| Win streak avg | 1.55 | 1.24 | 1.35 |
| Avg profit per win run | $4,637.60 | $3,697.68 | $4,025.96 |
| Best win run | $11,968 | $8,976 | $14,960 |
| Loss streak max / min | 7 / 1 | 13 / 1 | 12 / 1 |
| Loss streak avg | 2.67 | 4.64 | 3.66 |
| Avg loss per loss run | -$2,715.14 | -$4,723.52 | -$3,725.66 |
| Worst loss run | -$7,126 | -$13,234 | -$12,226 |
| Avg trade run-up | $1,643 | $1,207 | $1,369 |
| Max trade run-up | $3,010 | $3,010 | $3,010 |
| Avg trade run-down | $789 | $900 | $859 |
| Max trade run-down | $1,010 | $1,000 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2024**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$11,482 | $6,818 | -$4,664 |
| Total trades | 94 | 139 | 233 |
| Win rate | 22.3% | 26.6% | 24.9% |
| Profit factor | 0.845 | 1.066 | 0.974 |
| Sharpe (ann.) | -1.15 | 0.44 | -0.18 |
| Max drawdown | -$27,212 | -$15,518 | -$29,458 |
| Max run-up | $12,800 | $29,710 | $28,096 |
| Expectancy / trade | -$122.15 | $49.05 | -$20.02 |
| Avg win | $2,992.00 | $2,992.00 | $2,992.00 |
| Avg loss | -$1,018.00 | -$1,018.49 | -$1,018.29 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | -0.12 | 0.05 | -0.02 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,018 | -$1,038 | -$1,038 |
| Smallest win | $2,992.00 | $2,992.00 | $2,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 3 / 1 | 3 / 1 | 3 / 1 |
| Win streak avg | 1.50 | 1.32 | 1.29 |
| Avg profit per win run | $4,488.00 | $3,953.71 | $3,856.36 |
| Best win run | $8,976 | $8,976 | $8,976 |
| Loss streak max / min | 12 / 1 | 9 / 1 | 14 / 1 |
| Loss streak avg | 4.87 | 3.64 | 3.80 |
| Avg loss per loss run | -$4,954.27 | -$3,710.21 | -$3,873.91 |
| Worst loss run | -$12,216 | -$9,162 | -$14,262 |
| Avg trade run-up | $1,141 | $1,511 | $1,362 |
| Max trade run-up | $3,030 | $3,010 | $3,030 |
| Avg trade run-down | $860 | $873 | $868 |
| Max trade run-down | $1,000 | $1,020 | $1,020 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

> Cost ladder basis: $9 round-turn per contract.
wrote /Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/out_1to3_imb/metrics_imb.json

