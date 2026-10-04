## ledger_short_2NQ.csv — report card

```
NET -$37,648 · PF 0.94 · Sharpe -0.45 · WR 24.2% · MaxDD -$86,246 · 781 trades
```

**Equity curve** ($0 → -$37,648)

```
⣿⣿⣿⣿⣷⣿⣷⣿⣿⣷⣷⣷⣷⣷⣷⣶⣶⣶⣷⣶⣶⣶⣶⣶⣶⣦⣦⣤⣦⣤⣤⣄⣄⣀⣀⣀⣄⣄⣄⣀⣄⣀⣀⣀⣀⣄⣤⣤⣤⣤⣤⣤⣤⣄⣤⣤⣦⣶⣦⣦
```

**Edge inference** — EV -$48.20/trade · bootstrap 95% CI [-$170.91, $74.20] · P(EV ≤ 0): 78.7% · 10,000 resamples

**WR stability** — monthly WR 0.0%–47.1% (pooled 24.2%) · wobble 0.9× luck (steady) · worst 3-mo 15.0% (n=60) · 40 months

**Year by year (combined)**

| Year | Trades | Net | Win rate | PF | Sharpe | Max DD | Avg trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021 | 67 | -$12,076 | 20.9% | 0.78 | -1.74 | -$15,332 | -$180.24 |
| 2022 | 236 | -$15,788 | 23.7% | 0.91 | -0.62 | -$31,136 | -$66.90 |
| 2023 | 238 | -$46,104 | 20.6% | 0.76 | -1.90 | -$56,744 | -$193.71 |
| 2024 | 240 | $36,320 | 29.2% | 1.21 | 1.32 | -$15,548 | $151.33 |
| **All** | **781** | **-$37,648** | **24.2%** | **0.94** | **-0.45** | **-$86,246** | **-$48.20** |

**Cost ladder** — net edge vs friction multiple

| Friction | Net | $/trade | PF | Sharpe | Win rate | Max DD | |
|---|---:|---:|---:|---:|---:|---:|---|
| 0.5× | -$30,619 | -$39.20 | 0.949 | -0.36 | 24.2% | -$81,233 | **DEAD** |
| 1× | -$37,648 | -$48.20 | 0.938 | -0.45 | 24.2% | -$86,246 | **DEAD** · **as run** |
| 2× | -$51,706 | -$66.20 | 0.916 | -0.61 | 24.2% | -$96,272 | **DEAD** |
| 4× | -$79,822 | -$102.20 | 0.874 | -0.94 | 24.2% | -$116,364 | **DEAD** |

**Breakeven at -1.68× friction.** Under 2× — a routine slippage miss erases it.

**Breakeven multiple by year** — the pooled figure can hide a newer era that dies earlier

| Year | 0.5× | 1× | 2× | 4× | Breakeven |
|---|---:|---:|---:|---:|---:|
| 2021 | -$11,473 | -$12,076 | -$13,282 | -$15,694 | -9.01× |
| 2022 | -$13,664 | -$15,788 | -$20,036 | -$28,532 | -2.72× |
| 2023 | -$43,962 | -$46,104 | -$50,388 | -$58,956 | -9.76× |
| 2024 | $38,480 | $36,320 | $32,000 | $23,360 | 9.41× |

> The ladder subtracts money and nothing else, so it is a **lower bound on the damage** — real added friction also moves fills, so trades appear and disappear. `onyx.lab.costcurve.slip_stress` re-runs the strategy and captures that; this cannot.

**Pooled — all years**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | — | -$37,648 | -$37,648 |
| Total trades | 0 | 781 | 781 |
| Win rate | — | 24.2% | 24.2% |
| Profit factor | — | 0.938 | 0.938 |
| Sharpe (ann.) | — | -0.45 | -0.45 |
| Max drawdown | — | -$86,246 | -$86,246 |
| Max run-up | — | $56,220 | $56,220 |
| Expectancy / trade | — | -$48.20 | -$48.20 |
| Avg win | — | $2,990.36 | $2,990.36 |
| Avg loss | — | -$1,018.29 | -$1,018.29 |
| Payoff (avg W / avg L) | — | 2.94 | 2.94 |
| Avg R multiple | — | -0.05 | -0.05 |
| Largest win | — | $2,992 | $2,992 |
| Largest loss | — | -$1,048 | -$1,048 |
| Smallest win | — | $2,682.00 | $2,682.00 |
| Smallest loss | — | -$1,018.00 | -$1,018.00 |
| Win streak max / min | — / — | 4 / 1 | 4 / 1 |
| Win streak avg | — | 1.28 | 1.28 |
| Avg profit per win run | — | $3,818.77 | $3,818.77 |
| Best win run | — | $11,968 | $11,968 |
| Loss streak max / min | — / — | 15 / 1 | 15 / 1 |
| Loss streak avg | — | 3.97 | 3.97 |
| Avg loss per loss run | — | -$4,045.81 | -$4,045.81 |
| Worst loss run | — | -$15,280 | -$15,280 |
| Avg trade run-up | — | $1,363 | $1,363 |
| Max trade run-up | — | $3,020 | $3,020 |
| Avg trade run-down | — | $875 | $875 |
| Max trade run-down | — | $1,030 | $1,030 |
| Avg contracts | — | 2.00 | 2.00 |
| Max / min contracts | — / — | 2 / 2 | 2 / 2 |

**2021**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | — | -$12,076 | -$12,076 |
| Total trades | 0 | 67 | 67 |
| Win rate | — | 20.9% | 20.9% |
| Profit factor | — | 0.776 | 0.776 |
| Sharpe (ann.) | — | -1.74 | -1.74 |
| Max drawdown | — | -$15,332 | -$15,332 |
| Max run-up | — | $8,656 | $8,656 |
| Expectancy / trade | — | -$180.24 | -$180.24 |
| Avg win | — | $2,992.00 | $2,992.00 |
| Avg loss | — | -$1,018.19 | -$1,018.19 |
| Payoff (avg W / avg L) | — | 2.94 | 2.94 |
| Avg R multiple | — | -0.18 | -0.18 |
| Largest win | — | $2,992 | $2,992 |
| Largest loss | — | -$1,028 | -$1,028 |
| Smallest win | — | $2,992.00 | $2,992.00 |
| Smallest loss | — | -$1,018.00 | -$1,018.00 |
| Win streak max / min | — / — | 2 / 1 | 2 / 1 |
| Win streak avg | — | 1.17 | 1.17 |
| Avg profit per win run | — | $3,490.67 | $3,490.67 |
| Best win run | — | $5,984 | $5,984 |
| Loss streak max / min | — / — | 13 / 1 | 13 / 1 |
| Loss streak avg | — | 4.08 | 4.08 |
| Avg loss per loss run | — | -$4,151.08 | -$4,151.08 |
| Worst loss run | — | -$13,234 | -$13,234 |
| Avg trade run-up | — | $1,307 | $1,307 |
| Max trade run-up | — | $3,010 | $3,010 |
| Avg trade run-down | — | $905 | $905 |
| Max trade run-down | — | $1,010 | $1,010 |
| Avg contracts | — | 2.00 | 2.00 |
| Max / min contracts | — / — | 2 / 2 | 2 / 2 |

**2022**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | — | -$15,788 | -$15,788 |
| Total trades | 0 | 236 | 236 |
| Win rate | — | 23.7% | 23.7% |
| Profit factor | — | 0.914 | 0.914 |
| Sharpe (ann.) | — | -0.62 | -0.62 |
| Max drawdown | — | -$31,136 | -$31,136 |
| Max run-up | — | $12,728 | $12,728 |
| Expectancy / trade | — | -$66.90 | -$66.90 |
| Avg win | — | $2,992.00 | $2,992.00 |
| Avg loss | — | -$1,018.56 | -$1,018.56 |
| Payoff (avg W / avg L) | — | 2.94 | 2.94 |
| Avg R multiple | — | -0.07 | -0.07 |
| Largest win | — | $2,992 | $2,992 |
| Largest loss | — | -$1,048 | -$1,048 |
| Smallest win | — | $2,992.00 | $2,992.00 |
| Smallest loss | — | -$1,018.00 | -$1,018.00 |
| Win streak max / min | — / — | 3 / 1 | 3 / 1 |
| Win streak avg | — | 1.27 | 1.27 |
| Avg profit per win run | — | $3,808.00 | $3,808.00 |
| Best win run | — | $8,976 | $8,976 |
| Loss streak max / min | — / — | 15 / 1 | 15 / 1 |
| Loss streak avg | — | 4.00 | 4.00 |
| Avg loss per loss run | — | -$4,074.22 | -$4,074.22 |
| Worst loss run | — | -$15,280 | -$15,280 |
| Avg trade run-up | — | $1,373 | $1,373 |
| Max trade run-up | — | $3,020 | $3,020 |
| Avg trade run-down | — | $881 | $881 |
| Max trade run-down | — | $1,030 | $1,030 |
| Avg contracts | — | 2.00 | 2.00 |
| Max / min contracts | — / — | 2 / 2 | 2 / 2 |

**2023**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | — | -$46,104 | -$46,104 |
| Total trades | 0 | 238 | 238 |
| Win rate | — | 20.6% | 20.6% |
| Profit factor | — | 0.760 | 0.760 |
| Sharpe (ann.) | — | -1.90 | -1.90 |
| Max drawdown | — | -$56,744 | -$56,744 |
| Max run-up | — | $15,606 | $15,606 |
| Expectancy / trade | — | -$193.71 | -$193.71 |
| Avg win | — | $2,985.67 | $2,985.67 |
| Avg loss | — | -$1,018.00 | -$1,018.00 |
| Payoff (avg W / avg L) | — | 2.93 | 2.93 |
| Avg R multiple | — | -0.19 | -0.19 |
| Largest win | — | $2,992 | $2,992 |
| Largest loss | — | -$1,018 | -$1,018 |
| Smallest win | — | $2,682.00 | $2,682.00 |
| Smallest loss | — | -$1,018.00 | -$1,018.00 |
| Win streak max / min | — / — | 3 / 1 | 3 / 1 |
| Win streak avg | — | 1.17 | 1.17 |
| Avg profit per win run | — | $3,483.29 | $3,483.29 |
| Best win run | — | $8,976 | $8,976 |
| Loss streak max / min | — / — | 13 / 1 | 13 / 1 |
| Loss streak avg | — | 4.50 | 4.50 |
| Avg loss per loss run | — | -$4,581.00 | -$4,581.00 |
| Worst loss run | — | -$13,234 | -$13,234 |
| Avg trade run-up | — | $1,199 | $1,199 |
| Max trade run-up | — | $3,020 | $3,020 |
| Avg trade run-down | — | $891 | $891 |
| Max trade run-down | — | $1,000 | $1,000 |
| Avg contracts | — | 2.00 | 2.00 |
| Max / min contracts | — / — | 2 / 2 | 2 / 2 |

**2024**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | — | $36,320 | $36,320 |
| Total trades | 0 | 240 | 240 |
| Win rate | — | 29.2% | 29.2% |
| Profit factor | — | 1.210 | 1.210 |
| Sharpe (ann.) | — | 1.32 | 1.32 |
| Max drawdown | — | -$15,548 | -$15,548 |
| Max run-up | — | $56,220 | $56,220 |
| Expectancy / trade | — | $151.33 | $151.33 |
| Avg win | — | $2,992.00 | $2,992.00 |
| Avg loss | — | -$1,018.35 | -$1,018.35 |
| Payoff (avg W / avg L) | — | 2.94 | 2.94 |
| Avg R multiple | — | 0.15 | 0.15 |
| Largest win | — | $2,992 | $2,992 |
| Largest loss | — | -$1,038 | -$1,038 |
| Smallest win | — | $2,992.00 | $2,992.00 |
| Smallest loss | — | -$1,018.00 | -$1,018.00 |
| Win streak max / min | — / — | 4 / 1 | 4 / 1 |
| Win streak avg | — | 1.37 | 1.37 |
| Avg profit per win run | — | $4,106.67 | $4,106.67 |
| Best win run | — | $11,968 | $11,968 |
| Loss streak max / min | — / — | 12 / 1 | 12 / 1 |
| Loss streak avg | — | 3.33 | 3.33 |
| Avg loss per loss run | — | -$3,394.51 | -$3,394.51 |
| Worst loss run | — | -$12,236 | -$12,236 |
| Avg trade run-up | — | $1,532 | $1,532 |
| Max trade run-up | — | $3,020 | $3,020 |
| Avg trade run-down | — | $846 | $846 |
| Max trade run-down | — | $1,020 | $1,020 |
| Avg contracts | — | 2.00 | 2.00 |
| Max / min contracts | — / — | 2 / 2 | 2 / 2 |

> Cost ladder basis: $9 round-turn per contract.
wrote /Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/out_1to3_imb/metrics_short.json

