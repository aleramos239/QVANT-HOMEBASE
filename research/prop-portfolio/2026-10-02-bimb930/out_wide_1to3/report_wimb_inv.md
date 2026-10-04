## ledger_wimb_inv_2NQ.csv — report card

```
NET -$16,818 · PF 0.97 · Sharpe -0.20 · WR 24.9% · MaxDD -$66,274 · 776 trades
```

**Equity curve** ($0 → -$16,818)

```
⣿⣿⣿⣿⣿⣷⣷⣶⣷⣶⣶⣶⣶⣷⣷⣶⣦⣶⣦⣶⣶⣶⣿⣷⣷⣷⣷⣶⣷⣶⣶⣷⣶⣶⣦⣦⣦⣶⣶⣦⣦⣶⣦⣦⣤⣄⣀⣀⣀⣀⣀⣀⣄⣄⣄⣤⣤⣦⣶⣶
```

**Edge inference** — EV -$21.67/trade · bootstrap 95% CI [-$145.00, $103.03] · P(EV ≤ 0): 64.3% · 10,000 resamples

**WR stability** — monthly WR 10.0%–45.0% (pooled 24.9%) · wobble 0.6× luck (steady) · worst 3-mo 13.8% (n=58) · 40 months

**Year by year (combined)**

| Year | Trades | Net | Win rate | PF | Sharpe | Max DD | Avg trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021 | 66 | -$11,078 | 21.2% | 0.79 | -1.61 | -$14,644 | -$167.85 |
| 2022 | 235 | $1,230 | 25.5% | 1.01 | 0.05 | -$28,758 | $5.23 |
| 2023 | 236 | -$12,218 | 24.2% | 0.93 | -0.48 | -$26,354 | -$51.77 |
| 2024 | 239 | $5,248 | 25.9% | 1.03 | 0.20 | -$43,572 | $21.96 |
| **All** | **776** | **-$16,818** | **24.9%** | **0.97** | **-0.20** | **-$66,274** | **-$21.67** |

**Cost ladder** — net edge vs friction multiple

| Friction | Net | $/trade | PF | Sharpe | Win rate | Max DD | |
|---|---:|---:|---:|---:|---:|---:|---|
| 0.5× | -$9,834 | -$12.67 | 0.983 | -0.12 | 24.9% | -$60,802 | **DEAD** |
| 1× | -$16,818 | -$21.67 | 0.972 | -0.20 | 24.9% | -$66,274 | **DEAD** · **as run** |
| 2× | -$30,786 | -$39.67 | 0.949 | -0.36 | 24.9% | -$77,218 | **DEAD** |
| 4× | -$58,722 | -$75.67 | 0.906 | -0.69 | 24.9% | -$99,106 | **DEAD** |

**Breakeven at -0.20× friction.** Under 2× — a routine slippage miss erases it.

**Breakeven multiple by year** — the pooled figure can hide a newer era that dies earlier

| Year | 0.5× | 1× | 2× | 4× | Breakeven |
|---|---:|---:|---:|---:|---:|
| 2021 | -$10,484 | -$11,078 | -$12,266 | -$14,642 | -8.32× |
| 2022 | $3,345 | $1,230 | -$3,000 | -$11,460 | 1.29× |
| 2023 | -$10,094 | -$12,218 | -$16,466 | -$24,962 | -1.88× |
| 2024 | $7,399 | $5,248 | $946 | -$7,658 | 2.22× |

> The ladder subtracts money and nothing else, so it is a **lower bound on the damage** — real added friction also moves fills, so trades appear and disappear. `onyx.lab.costcurve.slip_stress` re-runs the strategy and captures that; this cannot.

**Pooled — all years**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$15,612 | -$1,206 | -$16,818 |
| Total trades | 444 | 332 | 776 |
| Win rate | 24.5% | 25.3% | 24.9% |
| Profit factor | 0.954 | 0.995 | 0.972 |
| Sharpe (ann.) | -0.32 | -0.03 | -0.20 |
| Max drawdown | -$46,254 | -$42,996 | -$66,274 |
| Max run-up | $36,698 | $39,940 | $49,026 |
| Expectancy / trade | -$35.16 | -$3.63 | -$21.67 |
| Avg win | $2,987.14 | $2,992.00 | $2,989.25 |
| Avg loss | -$1,018.54 | -$1,018.28 | -$1,018.43 |
| Payoff (avg W / avg L) | 2.93 | 2.94 | 2.94 |
| Avg R multiple | -0.04 | -0.00 | -0.02 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,038 | -$1,048 | -$1,048 |
| Smallest win | $2,462.00 | $2,992.00 | $2,462.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 3 / 1 | 3 / 1 | 4 / 1 |
| Win streak avg | 1.36 | 1.40 | 1.34 |
| Avg profit per win run | $4,069.97 | $4,188.80 | $4,006.43 |
| Best win run | $8,976 | $8,976 | $11,968 |
| Loss streak max / min | 19 / 1 | 20 / 1 | 16 / 1 |
| Loss streak avg | 4.14 | 4.07 | 4.02 |
| Avg loss per loss run | -$4,212.47 | -$4,139.90 | -$4,094.79 |
| Worst loss run | -$19,342 | -$20,360 | -$16,288 |
| Avg trade run-up | $1,332 | $1,395 | $1,359 |
| Max trade run-up | $3,020 | $3,020 | $3,020 |
| Avg trade run-down | $857 | $868 | $862 |
| Max trade run-down | $1,020 | $1,030 | $1,030 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2021**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$9,564 | -$1,514 | -$11,078 |
| Total trades | 33 | 33 | 66 |
| Win rate | 18.2% | 24.2% | 21.2% |
| Profit factor | 0.652 | 0.941 | 0.791 |
| Sharpe (ann.) | -2.93 | -0.42 | -1.61 |
| Max drawdown | -$11,538 | -$6,418 | -$14,644 |
| Max run-up | $6,930 | $5,984 | $8,718 |
| Expectancy / trade | -$289.82 | -$45.88 | -$167.85 |
| Avg win | $2,992.00 | $2,992.00 | $2,992.00 |
| Avg loss | -$1,019.11 | -$1,018.00 | -$1,018.58 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | -0.29 | -0.05 | -0.17 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,028 | -$1,018 | -$1,028 |
| Smallest win | $2,992.00 | $2,992.00 | $2,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 2 / 1 | 2 / 1 | 2 / 1 |
| Win streak avg | 1.20 | 1.14 | 1.08 |
| Avg profit per win run | $3,590.40 | $3,419.43 | $3,222.15 |
| Best win run | $5,984 | $5,984 | $5,984 |
| Loss streak max / min | 8 / 1 | 5 / 1 | 9 / 1 |
| Loss streak avg | 4.50 | 3.12 | 3.71 |
| Avg loss per loss run | -$4,586.00 | -$3,181.25 | -$3,783.29 |
| Worst loss run | -$8,144 | -$5,090 | -$9,162 |
| Avg trade run-up | $1,292 | $1,436 | $1,364 |
| Max trade run-up | $3,010 | $3,010 | $3,010 |
| Avg trade run-down | $901 | $888 | $895 |
| Max trade run-down | $1,010 | $1,000 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2022**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $5,072 | -$3,842 | $1,230 |
| Total trades | 121 | 114 | 235 |
| Win rate | 26.4% | 24.6% | 25.5% |
| Profit factor | 1.056 | 0.956 | 1.007 |
| Sharpe (ann.) | 0.37 | -0.31 | 0.05 |
| Max drawdown | -$16,504 | -$18,554 | -$28,758 |
| Max run-up | $20,562 | $11,782 | $26,226 |
| Expectancy / trade | $41.92 | -$33.70 | $5.23 |
| Avg win | $2,992.00 | $2,992.00 | $2,992.00 |
| Avg loss | -$1,018.79 | -$1,018.81 | -$1,018.80 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | 0.04 | -0.03 | 0.01 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,028 | -$1,048 | -$1,048 |
| Smallest win | $2,992.00 | $2,992.00 | $2,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 3 / 1 | 2 / 1 | 3 / 1 |
| Win streak avg | 1.39 | 1.40 | 1.43 |
| Avg profit per win run | $4,162.78 | $4,188.80 | $4,274.29 |
| Best win run | $8,976 | $5,984 | $8,976 |
| Loss streak max / min | 11 / 1 | 8 / 1 | 12 / 1 |
| Loss streak avg | 3.87 | 4.10 | 4.07 |
| Avg loss per loss run | -$3,942.26 | -$4,172.29 | -$4,146.28 |
| Worst loss run | -$11,208 | -$8,144 | -$12,216 |
| Avg trade run-up | $1,372 | $1,419 | $1,395 |
| Max trade run-up | $3,020 | $3,010 | $3,020 |
| Avg trade run-down | $841 | $876 | $858 |
| Max trade run-down | $1,010 | $1,030 | $1,030 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2023**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $16,260 | -$28,478 | -$12,218 |
| Total trades | 145 | 91 | 236 |
| Win rate | 28.3% | 17.6% | 24.2% |
| Profit factor | 1.154 | 0.627 | 0.933 |
| Sharpe (ann.) | 0.99 | -3.24 | -0.48 |
| Max drawdown | -$10,366 | -$33,072 | -$26,354 |
| Max run-up | $23,386 | $11,844 | $23,440 |
| Expectancy / trade | $112.14 | -$312.95 | -$51.77 |
| Avg win | $2,979.07 | $2,992.00 | $2,982.70 |
| Avg loss | -$1,018.10 | -$1,018.00 | -$1,018.06 |
| Payoff (avg W / avg L) | 2.93 | 2.94 | 2.93 |
| Avg R multiple | 0.11 | -0.31 | -0.05 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,028 | -$1,018 | -$1,028 |
| Smallest win | $2,462.00 | $2,992.00 | $2,462.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 3 / 1 | 2 / 1 | 3 / 1 |
| Win streak avg | 1.41 | 1.23 | 1.27 |
| Avg profit per win run | $4,211.79 | $3,682.46 | $3,778.09 |
| Best win run | $8,976 | $5,984 | $8,976 |
| Loss streak max / min | 10 / 1 | 20 / 1 | 16 / 1 |
| Loss streak avg | 3.47 | 5.77 | 3.89 |
| Avg loss per loss run | -$3,529.40 | -$5,873.08 | -$3,961.57 |
| Worst loss run | -$10,180 | -$20,360 | -$16,288 |
| Avg trade run-up | $1,439 | $1,070 | $1,297 |
| Max trade run-up | $3,020 | $3,020 | $3,020 |
| Avg trade run-down | $830 | $914 | $862 |
| Max trade run-down | $1,010 | $1,000 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2024**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$27,380 | $32,628 | $5,248 |
| Total trades | 145 | 94 | 239 |
| Win rate | 20.7% | 34.0% | 25.9% |
| Profit factor | 0.766 | 1.517 | 1.029 |
| Sharpe (ann.) | -1.84 | 2.88 | 0.20 |
| Max drawdown | -$46,254 | -$8,144 | -$43,572 |
| Max run-up | $19,018 | $39,940 | $49,026 |
| Expectancy / trade | -$188.83 | $347.11 | $21.96 |
| Avg win | $2,992.00 | $2,992.00 | $2,992.00 |
| Avg loss | -$1,018.61 | -$1,018.00 | -$1,018.40 |
| Payoff (avg W / avg L) | 2.94 | 2.94 | 2.94 |
| Avg R multiple | -0.19 | 0.35 | 0.02 |
| Largest win | $2,992 | $2,992 | $2,992 |
| Largest loss | -$1,038 | -$1,018 | -$1,038 |
| Smallest win | $2,992.00 | $2,992.00 | $2,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 3 / 1 | 3 / 1 | 4 / 1 |
| Win streak avg | 1.30 | 1.60 | 1.41 |
| Avg profit per win run | $3,902.61 | $4,787.20 | $4,216.00 |
| Best win run | $8,976 | $8,976 | $11,968 |
| Loss streak max / min | 19 / 1 | 8 / 1 | 12 / 1 |
| Loss streak avg | 4.79 | 2.95 | 3.93 |
| Avg loss per loss run | -$4,880.83 | -$3,005.52 | -$4,005.69 |
| Worst loss run | -$19,342 | -$8,144 | -$12,216 |
| Avg trade run-up | $1,202 | $1,664 | $1,383 |
| Max trade run-up | $3,020 | $3,020 | $3,020 |
| Avg trade run-down | $889 | $804 | $856 |
| Max trade run-down | $1,020 | $1,000 | $1,020 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

> Cost ladder basis: $9 round-turn per contract.
wrote /Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/out_wide_1to3/metrics_wimb_inv.json

