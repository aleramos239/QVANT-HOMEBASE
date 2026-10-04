## ledger_long_2NQ.csv — report card

```
NET -$21,908 · PF 0.96 · Sharpe -0.26 · WR 24.7% · MaxDD -$55,218 · 781 trades
```

**Equity curve** ($0 → -$21,908)

```
⣶⣶⣶⣶⣶⣦⣦⣤⣤⣦⣦⣤⣄⣤⣤⣤⣄⣄⣀⣄⣤⣀⣄⣀⣀⣀⣀⣄⣄⣄⣄⣦⣶⣷⣶⣷⣶⣶⣶⣶⣷⣿⣿⣷⣦⣦⣤⣄⣄⣄⣄⣄⣄⣄⣀⣀⣀⣀⣤⣄
```

**Edge inference** — EV -$28.05/trade · bootstrap 95% CI [-$150.60, $93.91] · P(EV ≤ 0): 68.5% · 10,000 resamples

**WR stability** — monthly WR 5.0%–50.0% (pooled 24.7%) · wobble 0.9× luck (steady) · worst 3-mo 10.2% (n=59) · 40 months

**Year by year (combined)**

| Year | Trades | Net | Win rate | PF | Sharpe | Max DD | Avg trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021 | 67 | -$8,096 | 22.4% | 0.85 | -1.14 | -$17,502 | -$120.84 |
| 2022 | 236 | -$23,828 | 22.9% | 0.87 | -0.95 | -$30,644 | -$100.97 |
| 2023 | 238 | $45,886 | 30.3% | 1.27 | 1.66 | -$13,296 | $192.80 |
| 2024 | 240 | -$35,870 | 21.7% | 0.81 | -1.43 | -$55,218 | -$149.46 |
| **All** | **781** | **-$21,908** | **24.7%** | **0.96** | **-0.26** | **-$55,218** | **-$28.05** |

**Cost ladder** — net edge vs friction multiple

| Friction | Net | $/trade | PF | Sharpe | Win rate | Max DD | |
|---|---:|---:|---:|---:|---:|---:|---|
| 0.5× | -$14,879 | -$19.05 | 0.975 | -0.17 | 24.7% | -$53,851 | **DEAD** |
| 1× | -$21,908 | -$28.05 | 0.963 | -0.26 | 24.7% | -$55,218 | **DEAD** · **as run** |
| 2× | -$35,966 | -$46.05 | 0.941 | -0.42 | 24.7% | -$58,746 | **DEAD** |
| 4× | -$64,082 | -$82.05 | 0.898 | -0.75 | 24.7% | -$77,232 | **DEAD** |

**Breakeven at -0.56× friction.** Under 2× — a routine slippage miss erases it.

**Breakeven multiple by year** — the pooled figure can hide a newer era that dies earlier

| Year | 0.5× | 1× | 2× | 4× | Breakeven |
|---|---:|---:|---:|---:|---:|
| 2021 | -$7,493 | -$8,096 | -$9,302 | -$11,714 | -5.71× |
| 2022 | -$21,704 | -$23,828 | -$28,076 | -$36,572 | -4.61× |
| 2023 | $48,028 | $45,886 | $41,602 | $33,034 | 11.71× |
| 2024 | -$33,710 | -$35,870 | -$40,190 | -$48,830 | -7.30× |

> The ladder subtracts money and nothing else, so it is a **lower bound on the damage** — real added friction also moves fills, so trades appear and disappear. `onyx.lab.costcurve.slip_stress` re-runs the strategy and captures that; this cannot.

**Pooled — all years**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$21,908 | — | -$21,908 |
| Total trades | 781 | 0 | 781 |
| Win rate | 24.7% | — | 24.7% |
| Profit factor | 0.963 | — | 0.963 |
| Sharpe (ann.) | -0.26 | — | -0.26 |
| Max drawdown | -$55,218 | — | -$55,218 |
| Max run-up | $59,890 | — | $59,890 |
| Expectancy / trade | -$28.05 | — | -$28.05 |
| Avg win | $2,989.25 | — | $2,989.25 |
| Avg loss | -$1,018.43 | — | -$1,018.43 |
| Payoff (avg W / avg L) | 2.94 | — | 2.94 |
| Avg R multiple | -0.03 | — | -0.03 |
| Largest win | $2,992 | — | $2,992 |
| Largest loss | -$1,038 | — | -$1,038 |
| Smallest win | $2,462.00 | — | $2,462.00 |
| Smallest loss | -$1,018.00 | — | -$1,018.00 |
| Win streak max / min | 4 / 1 | — / — | 4 / 1 |
| Win streak avg | 1.28 | — | 1.28 |
| Avg profit per win run | $3,820.70 | — | $3,820.70 |
| Best win run | $11,968 | — | $11,968 |
| Loss streak max / min | 16 / 1 | — / — | 16 / 1 |
| Loss streak avg | 3.87 | — | 3.87 |
| Avg loss per loss run | -$3,939.70 | — | -$3,939.70 |
| Worst loss run | -$16,288 | — | -$16,288 |
| Avg trade run-up | $1,342 | — | $1,342 |
| Max trade run-up | $3,030 | — | $3,030 |
| Avg trade run-down | $856 | — | $856 |
| Max trade run-down | $1,020 | — | $1,020 |
| Avg contracts | 2.00 | — | 2.00 |
| Max / min contracts | 2 / 2 | — / — | 2 / 2 |

**2021**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$8,096 | — | -$8,096 |
| Total trades | 67 | 0 | 67 |
| Win rate | 22.4% | — | 22.4% |
| Profit factor | 0.847 | — | 0.847 |
| Sharpe (ann.) | -1.14 | — | -1.14 |
| Max drawdown | -$17,502 | — | -$17,502 |
| Max run-up | $12,852 | — | $12,852 |
| Expectancy / trade | -$120.84 | — | -$120.84 |
| Avg win | $2,992.00 | — | $2,992.00 |
| Avg loss | -$1,018.77 | — | -$1,018.77 |
| Payoff (avg W / avg L) | 2.94 | — | 2.94 |
| Avg R multiple | -0.12 | — | -0.12 |
| Largest win | $2,992 | — | $2,992 |
| Largest loss | -$1,028 | — | -$1,028 |
| Smallest win | $2,992.00 | — | $2,992.00 |
| Smallest loss | -$1,018.00 | — | -$1,018.00 |
| Win streak max / min | 3 / 1 | — / — | 3 / 1 |
| Win streak avg | 1.36 | — | 1.36 |
| Avg profit per win run | $4,080.00 | — | $4,080.00 |
| Best win run | $8,976 | — | $8,976 |
| Loss streak max / min | 9 / 1 | — / — | 9 / 1 |
| Loss streak avg | 4.33 | — | 4.33 |
| Avg loss per loss run | -$4,414.67 | — | -$4,414.67 |
| Worst loss run | -$9,162 | — | -$9,162 |
| Avg trade run-up | $1,263 | — | $1,263 |
| Max trade run-up | $3,010 | — | $3,010 |
| Avg trade run-down | $873 | — | $873 |
| Max trade run-down | $1,010 | — | $1,010 |
| Avg contracts | 2.00 | — | 2.00 |
| Max / min contracts | 2 / 2 | — / — | 2 / 2 |

**2022**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$23,828 | — | -$23,828 |
| Total trades | 236 | 0 | 236 |
| Win rate | 22.9% | — | 22.9% |
| Profit factor | 0.871 | — | 0.871 |
| Sharpe (ann.) | -0.95 | — | -0.95 |
| Max drawdown | -$30,644 | — | -$30,644 |
| Max run-up | $14,588 | — | $14,588 |
| Expectancy / trade | -$100.97 | — | -$100.97 |
| Avg win | $2,992.00 | — | $2,992.00 |
| Avg loss | -$1,018.66 | — | -$1,018.66 |
| Payoff (avg W / avg L) | 2.94 | — | 2.94 |
| Avg R multiple | -0.10 | — | -0.10 |
| Largest win | $2,992 | — | $2,992 |
| Largest loss | -$1,038 | — | -$1,038 |
| Smallest win | $2,992.00 | — | $2,992.00 |
| Smallest loss | -$1,018.00 | — | -$1,018.00 |
| Win streak max / min | 3 / 1 | — / — | 3 / 1 |
| Win streak avg | 1.23 | — | 1.23 |
| Avg profit per win run | $3,672.00 | — | $3,672.00 |
| Best win run | $8,976 | — | $8,976 |
| Loss streak max / min | 14 / 1 | — / — | 14 / 1 |
| Loss streak avg | 4.14 | — | 4.14 |
| Avg loss per loss run | -$4,213.55 | — | -$4,213.55 |
| Worst loss run | -$14,292 | — | -$14,292 |
| Avg trade run-up | $1,342 | — | $1,342 |
| Max trade run-up | $3,020 | — | $3,020 |
| Avg trade run-down | $861 | — | $861 |
| Max trade run-down | $1,020 | — | $1,020 |
| Avg contracts | 2.00 | — | 2.00 |
| Max / min contracts | 2 / 2 | — / — | 2 / 2 |

**2023**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $45,886 | — | $45,886 |
| Total trades | 238 | 0 | 238 |
| Win rate | 30.3% | — | 30.3% |
| Profit factor | 1.272 | — | 1.272 |
| Sharpe (ann.) | 1.66 | — | 1.66 |
| Max drawdown | -$13,296 | — | -$13,296 |
| Max run-up | $53,012 | — | $53,012 |
| Expectancy / trade | $192.80 | — | $192.80 |
| Avg win | $2,984.64 | — | $2,984.64 |
| Avg loss | -$1,018.12 | — | -$1,018.12 |
| Payoff (avg W / avg L) | 2.93 | — | 2.93 |
| Avg R multiple | 0.19 | — | 0.19 |
| Largest win | $2,992 | — | $2,992 |
| Largest loss | -$1,028 | — | -$1,028 |
| Smallest win | $2,462.00 | — | $2,462.00 |
| Smallest loss | -$1,018.00 | — | -$1,018.00 |
| Win streak max / min | 4 / 1 | — / — | 4 / 1 |
| Win streak avg | 1.29 | — | 1.29 |
| Avg profit per win run | $3,837.39 | — | $3,837.39 |
| Best win run | $11,438 | — | $11,438 |
| Loss streak max / min | 10 / 1 | — / — | 10 / 1 |
| Loss streak avg | 2.91 | — | 2.91 |
| Avg loss per loss run | -$2,965.05 | — | -$2,965.05 |
| Worst loss run | -$10,180 | — | -$10,180 |
| Avg trade run-up | $1,536 | — | $1,536 |
| Max trade run-up | $3,020 | — | $3,020 |
| Avg trade run-down | $821 | — | $821 |
| Max trade run-down | $1,010 | — | $1,010 |
| Avg contracts | 2.00 | — | 2.00 |
| Max / min contracts | 2 / 2 | — / — | 2 / 2 |

**2024**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$35,870 | — | -$35,870 |
| Total trades | 240 | 0 | 240 |
| Win rate | 21.7% | — | 21.7% |
| Profit factor | 0.813 | — | 0.813 |
| Sharpe (ann.) | -1.43 | — | -1.43 |
| Max drawdown | -$55,218 | — | -$55,218 |
| Max run-up | $17,580 | — | $17,580 |
| Expectancy / trade | -$149.46 | — | -$149.46 |
| Avg win | $2,992.00 | — | $2,992.00 |
| Avg loss | -$1,018.37 | — | -$1,018.37 |
| Payoff (avg W / avg L) | 2.94 | — | 2.94 |
| Avg R multiple | -0.15 | — | -0.15 |
| Largest win | $2,992 | — | $2,992 |
| Largest loss | -$1,038 | — | -$1,038 |
| Smallest win | $2,992.00 | — | $2,992.00 |
| Smallest loss | -$1,018.00 | — | -$1,018.00 |
| Win streak max / min | 4 / 1 | — / — | 4 / 1 |
| Win streak avg | 1.30 | — | 1.30 |
| Avg profit per win run | $3,889.60 | — | $3,889.60 |
| Best win run | $11,968 | — | $11,968 |
| Loss streak max / min | 16 / 1 | — / — | 16 / 1 |
| Loss streak avg | 4.59 | — | 4.59 |
| Avg loss per loss run | -$4,669.61 | — | -$4,669.61 |
| Worst loss run | -$16,288 | — | -$16,288 |
| Avg trade run-up | $1,172 | — | $1,172 |
| Max trade run-up | $3,030 | — | $3,030 |
| Avg trade run-down | $881 | — | $881 |
| Max trade run-down | $1,020 | — | $1,020 |
| Avg contracts | 2.00 | — | 2.00 |
| Max / min contracts | 2 / 2 | — / — | 2 / 2 |

> Cost ladder basis: $9 round-turn per contract.
wrote /Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/out_wide_1to3/metrics_long.json

