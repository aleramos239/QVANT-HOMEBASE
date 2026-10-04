## ledger_wimb_2NQ.csv — report card

```
NET -$48,598 · PF 0.92 · Sharpe -0.58 · WR 23.8% · MaxDD -$71,504 · 776 trades
```

**Equity curve** ($0 → -$48,598)

```
⣿⣿⣷⣿⣷⣷⣷⣷⣷⣿⣷⣷⣶⣦⣶⣶⣶⣶⣶⣦⣦⣤⣄⣄⣄⣀⣀⣄⣀⣀⣄⣀⣤⣄⣄⣤⣤⣄⣤⣤⣤⣤⣤⣄⣄⣤⣦⣦⣦⣦⣶⣦⣤⣤⣤⣤⣤⣦⣤⣄
```

**Edge inference** — EV -$62.63/trade · bootstrap 95% CI [-$181.58, $56.72] · P(EV ≤ 0): 85.9% · 10,000 resamples

**WR stability** — monthly WR 0.0%–47.1% (pooled 23.8%) · wobble 0.8× luck (steady) · worst 3-mo 13.3% (n=60) · 40 months

**Year by year (combined)**

| Year | Trades | Net | Win rate | PF | Sharpe | Max DD | Avg trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021 | 66 | -$11,068 | 21.2% | 0.79 | -1.61 | -$15,270 | -$167.70 |
| 2022 | 235 | -$42,820 | 20.9% | 0.77 | -1.77 | -$47,002 | -$182.21 |
| 2023 | 236 | $8,052 | 26.3% | 1.05 | 0.31 | -$22,706 | $34.12 |
| 2024 | 239 | -$2,762 | 25.1% | 0.98 | -0.11 | -$27,226 | -$11.56 |
| **All** | **776** | **-$48,598** | **23.8%** | **0.92** | **-0.58** | **-$71,504** | **-$62.63** |

**Cost ladder** — net edge vs friction multiple

| Friction | Net | $/trade | PF | Sharpe | Win rate | Max DD | |
|---|---:|---:|---:|---:|---:|---:|---|
| 0.5× | -$41,614 | -$53.63 | 0.930 | -0.50 | 23.8% | -$68,462 | **DEAD** |
| 1× | -$48,598 | -$62.63 | 0.919 | -0.58 | 23.8% | -$71,504 | **DEAD** · **as run** |
| 2× | -$62,566 | -$80.63 | 0.898 | -0.75 | 23.8% | -$77,588 | **DEAD** |
| 4× | -$90,502 | -$116.63 | 0.857 | -1.08 | 23.8% | -$91,534 | **DEAD** |

**Breakeven at -2.48× friction.** Under 2× — a routine slippage miss erases it.

**Breakeven multiple by year** — the pooled figure can hide a newer era that dies earlier

| Year | 0.5× | 1× | 2× | 4× | Breakeven |
|---|---:|---:|---:|---:|---:|
| 2021 | -$10,474 | -$11,068 | -$12,256 | -$14,632 | -8.32× |
| 2022 | -$40,705 | -$42,820 | -$47,050 | -$55,510 | -9.12× |
| 2023 | $10,176 | $8,052 | $3,804 | -$4,692 | 2.90× |
| 2024 | -$611 | -$2,762 | -$7,064 | -$15,668 | 0.36× |

> The ladder subtracts money and nothing else, so it is a **lower bound on the damage** — real added friction also moves fills, so trades appear and disappear. `onyx.lab.costcurve.slip_stress` re-runs the strategy and captures that; this cannot.

**Pooled — all years**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$9,226 | -$39,372 | -$48,598 |
| Total trades | 332 | 444 | 776 |
| Win rate | 24.7% | 23.2% | 23.8% |
| Profit factor | 0.964 | 0.887 | 0.919 |
| Sharpe (ann.) | -0.25 | -0.83 | -0.58 |
| Max drawdown | -$36,532 | -$52,536 | -$71,504 |
| Max run-up | $33,884 | $29,466 | $48,344 |
| Expectancy / trade | -$27.79 | -$88.68 | -$62.63 |
| Avg win | $2,992.00 | $2,988.99 | $2,990.32 |
| Avg loss | -$1,018.28 | -$1,018.29 | -$1,018.29 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | -0.03 | -0.09 | -0.06 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,038 | -$1,038 | -$1,038 |
| Smallest win | $2,992.00 | $2,682.00 | $2,682.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 3 / 1 | 3 / 1 | 4 / 1 |
| Win streak avg | 1.30 | 1.36 | 1.36 |
| Avg profit per win run | $3,894.35 | $4,050.87 | $4,067.72 |
| Best win run | $8,976 | $8,976 | $11,968 |
| Loss streak max / min | 14 / 1 | 15 / 1 | 16 / 1 |
| Loss streak avg | 3.91 | 4.49 | 4.31 |
| Avg loss per loss run | -$3,977.66 | -$4,568.92 | -$4,392.76 |
| Worst loss run | -$14,252 | -$15,270 | -$16,288 |
| Avg trade run-up | $1,346 | $1,337 | $1,341 |
| Max trade run-up | $3,030 | $3,020 | $3,030 |
| Avg trade run-down | $853 | $881 | $869 |
| Max trade run-down | $1,020 | $1,020 | $1,020 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2021**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$1,524 | -$9,544 | -$11,068 |
| Total trades | 33 | 33 | 66 |
| Win rate | 24.2% | 18.2% | 21.2% |
| Profit factor | 0.940 | 0.653 | 0.791 |
| Sharpe (ann.) | -0.42 | -2.92 | -1.61 |
| Max drawdown | -$10,304 | -$14,376 | -$15,270 |
| Max run-up | $7,958 | $7,886 | $10,826 |
| Expectancy / trade | -$46.18 | -$289.21 | -$167.70 |
| Avg win | $2,992.00 | $2,992.00 | $2,992.00 |
| Avg loss | -$1,018.40 | -$1,018.37 | -$1,018.38 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | -0.05 | -0.29 | -0.17 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,028 | -$1,028 | -$1,028 |
| Smallest win | $2,992.00 | $2,992.00 | $2,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 2 / 1 | 2 / 2 | 2 / 1 |
| Win streak avg | 1.33 | 2.00 | 1.17 |
| Avg profit per win run | $3,989.33 | $5,984.00 | $3,490.67 |
| Best win run | $5,984 | $5,984 | $5,984 |
| Loss streak max / min | 10 / 1 | 14 / 3 | 15 / 1 |
| Loss streak avg | 3.57 | 6.75 | 4.00 |
| Avg loss per loss run | -$3,637.14 | -$6,874.00 | -$4,073.54 |
| Worst loss run | -$10,180 | -$14,252 | -$15,270 |
| Avg trade run-up | $1,181 | $1,189 | $1,185 |
| Max trade run-up | $3,010 | $3,010 | $3,010 |
| Avg trade run-down | $844 | $918 | $881 |
| Max trade run-down | $1,010 | $1,010 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2022**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$27,882 | -$14,938 | -$42,820 |
| Total trades | 114 | 121 | 235 |
| Win rate | 19.3% | 22.3% | 20.9% |
| Profit factor | 0.702 | 0.844 | 0.774 |
| Sharpe (ann.) | -2.44 | -1.17 | -1.77 |
| Max drawdown | -$33,526 | -$21,434 | -$47,002 |
| Max run-up | $9,870 | $11,782 | $15,854 |
| Expectancy / trade | -$244.58 | -$123.45 | -$182.21 |
| Avg win | $2,992.00 | $2,992.00 | $2,992.00 |
| Avg loss | -$1,018.54 | -$1,018.32 | -$1,018.43 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | -0.24 | -0.12 | -0.18 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,038 | -$1,028 | -$1,038 |
| Smallest win | $2,992.00 | $2,992.00 | $2,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 3 / 1 | 2 / 1 | 3 / 1 |
| Win streak avg | 1.16 | 1.35 | 1.36 |
| Avg profit per win run | $3,464.42 | $4,039.20 | $4,072.44 |
| Best win run | $8,976 | $5,984 | $8,976 |
| Loss streak max / min | 14 / 1 | 10 / 1 | 14 / 1 |
| Loss streak avg | 4.84 | 4.48 | 5.17 |
| Avg loss per loss run | -$4,931.89 | -$4,558.19 | -$5,261.89 |
| Worst loss run | -$14,252 | -$10,190 | -$14,262 |
| Avg trade run-up | $1,315 | $1,316 | $1,316 |
| Max trade run-up | $3,020 | $3,020 | $3,020 |
| Avg trade run-down | $880 | $886 | $883 |
| Max trade run-down | $1,020 | $1,010 | $1,020 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2023**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $27,652 | -$19,600 | $8,052 |
| Total trades | 91 | 145 | 236 |
| Win rate | 33.0% | 22.1% | 26.3% |
| Profit factor | 1.445 | 0.830 | 1.045 |
| Sharpe (ann.) | 2.54 | -1.29 | 0.31 |
| Max drawdown | -$7,384 | -$25,176 | -$22,706 |
| Max run-up | $28,918 | $13,632 | $29,342 |
| Expectancy / trade | $303.87 | -$135.17 | $34.12 |
| Avg win | $2,992.00 | $2,982.31 | $2,987.00 |
| Avg loss | -$1,018.16 | -$1,018.00 | -$1,018.06 |
| Payoff (avg W / avg L) | 2.94 | 2.93 | 2.93 |
| Avg R multiple | 0.30 | -0.14 | 0.03 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,028 | -$1,018 | -$1,028 |
| Smallest win | $2,992.00 | $2,682.00 | $2,682.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 2 / 1 | 2 / 1 | 4 / 1 |
| Win streak avg | 1.43 | 1.23 | 1.51 |
| Avg profit per win run | $4,274.29 | $3,670.54 | $4,516.93 |
| Best win run | $5,984 | $5,984 | $11,968 |
| Loss streak max / min | 6 / 1 | 15 / 1 | 12 / 1 |
| Loss streak avg | 2.90 | 4.35 | 4.24 |
| Avg loss per loss run | -$2,957.52 | -$4,424.38 | -$4,320.54 |
| Worst loss run | -$6,108 | -$15,270 | -$12,216 |
| Avg trade run-up | $1,682 | $1,272 | $1,430 |
| Max trade run-up | $3,010 | $3,010 | $3,010 |
| Avg trade run-down | $809 | $877 | $851 |
| Max trade run-down | $1,010 | $1,000 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2024**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$7,472 | $4,710 | -$2,762 |
| Total trades | 94 | 145 | 239 |
| Win rate | 23.4% | 26.2% | 25.1% |
| Profit factor | 0.898 | 1.043 | 0.985 |
| Sharpe (ann.) | -0.74 | 0.29 | -0.11 |
| Max drawdown | -$14,376 | -$19,682 | -$27,226 |
| Max run-up | $12,738 | $29,466 | $34,184 |
| Expectancy / trade | -$79.49 | $32.48 | -$11.56 |
| Avg win | $2,992.00 | $2,992.00 | $2,992.00 |
| Avg loss | -$1,018.00 | -$1,018.56 | -$1,018.34 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | -0.08 | 0.03 | -0.01 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,018 | -$1,038 | -$1,038 |
| Smallest win | $2,992.00 | $2,992.00 | $2,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 3 / 1 | 3 / 1 | 3 / 1 |
| Win streak avg | 1.29 | 1.36 | 1.25 |
| Avg profit per win run | $3,872.00 | $4,060.57 | $3,740.00 |
| Best win run | $8,976 | $8,976 | $8,976 |
| Loss streak max / min | 9 / 1 | 12 / 1 | 16 / 1 |
| Loss streak avg | 4.00 | 3.96 | 3.73 |
| Avg loss per loss run | -$4,072.00 | -$4,036.52 | -$3,797.54 |
| Worst loss run | -$9,162 | -$12,216 | -$16,288 |
| Avg trade run-up | $1,114 | $1,454 | $1,321 |
| Max trade run-up | $3,030 | $3,020 | $3,030 |
| Avg trade run-down | $867 | $872 | $870 |
| Max trade run-down | $1,000 | $1,020 | $1,020 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

> Cost ladder basis: $9 round-turn per contract.
wrote /Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/out_wide_1to3/metrics_wimb.json

