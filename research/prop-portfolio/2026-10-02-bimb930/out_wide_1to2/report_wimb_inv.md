## ledger_wimb_inv_2NQ.csv — report card

```
NET -$49,718 · PF 0.91 · Sharpe -0.73 · WR 31.7% · MaxDD -$62,586 · 776 trades
```

**Equity curve** ($0 → -$49,718)

```
⣿⣿⣿⣿⣿⣷⣿⣷⣷⣷⣷⣷⣷⣷⣷⣶⣶⣶⣦⣷⣷⣷⣿⣿⣷⣿⣿⣷⣿⣷⣷⣷⣷⣷⣶⣶⣶⣷⣶⣶⣶⣶⣶⣦⣦⣤⣄⣤⣄⣀⣀⣀⣄⣀⣀⣀⣀⣀⣄⣄
```

**Edge inference** — EV -$64.07/trade · bootstrap 95% CI [-$164.89, $33.02] · P(EV ≤ 0): 89.8% · 10,000 resamples

**WR stability** — monthly WR 11.8%–50.0% (pooled 31.7%) · wobble 0.7× luck (steady) · worst 3-mo 20.7% (n=58) · 40 months

**Year by year (combined)**

| Year | Trades | Net | Win rate | PF | Sharpe | Max DD | Avg trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021 | 66 | -$10,018 | 28.8% | 0.79 | -1.75 | -$12,764 | -$151.79 |
| 2022 | 235 | $4,450 | 34.5% | 1.03 | 0.21 | -$25,592 | $18.94 |
| 2023 | 236 | -$17,518 | 31.4% | 0.89 | -0.84 | -$26,720 | -$74.23 |
| 2024 | 239 | -$26,632 | 30.1% | 0.84 | -1.28 | -$39,632 | -$111.43 |
| **All** | **776** | **-$49,718** | **31.7%** | **0.91** | **-0.73** | **-$62,586** | **-$64.07** |

**Cost ladder** — net edge vs friction multiple

| Friction | Net | $/trade | PF | Sharpe | Win rate | Max DD | |
|---|---:|---:|---:|---:|---:|---:|---|
| 0.5× | -$42,734 | -$55.07 | 0.920 | -0.62 | 31.7% | -$58,380 | **DEAD** |
| 1× | -$49,718 | -$64.07 | 0.908 | -0.73 | 31.7% | -$62,586 | **DEAD** · **as run** |
| 2× | -$63,686 | -$82.07 | 0.884 | -0.93 | 31.7% | -$75,132 | **DEAD** |
| 4× | -$91,622 | -$118.07 | 0.839 | -1.34 | 31.7% | -$100,224 | **DEAD** |

**Breakeven at -2.56× friction.** Under 2× — a routine slippage miss erases it.

**Breakeven multiple by year** — the pooled figure can hide a newer era that dies earlier

| Year | 0.5× | 1× | 2× | 4× | Breakeven |
|---|---:|---:|---:|---:|---:|
| 2021 | -$9,424 | -$10,018 | -$11,206 | -$13,582 | -7.43× |
| 2022 | $6,565 | $4,450 | $220 | -$8,240 | 2.05× |
| 2023 | -$15,394 | -$17,518 | -$21,766 | -$30,262 | -3.12× |
| 2024 | -$24,481 | -$26,632 | -$30,934 | -$39,538 | -5.19× |

> The ladder subtracts money and nothing else, so it is a **lower bound on the damage** — real added friction also moves fills, so trades appear and disappear. `onyx.lab.costcurve.slip_stress` re-runs the strategy and captures that; this cannot.

**Pooled — all years**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$33,752 | -$15,966 | -$49,718 |
| Total trades | 444 | 332 | 776 |
| Win rate | 31.3% | 32.2% | 31.7% |
| Profit factor | 0.891 | 0.930 | 0.908 |
| Sharpe (ann.) | -0.86 | -0.54 | -0.73 |
| Max drawdown | -$43,798 | -$40,180 | -$62,586 |
| Max run-up | $31,292 | $19,852 | $29,690 |
| Expectancy / trade | -$76.02 | -$48.09 | -$64.07 |
| Avg win | $1,992.00 | $1,992.00 | $1,992.00 |
| Avg loss | -$1,018.49 | -$1,018.27 | -$1,018.40 |
| Payoff (avg W / avg L) | 1.96 | 1.96 | 1.96 |
| Avg R multiple | -0.08 | -0.05 | -0.06 |
| Largest win | $1,992 | $1,992 | $1,992 |
| Largest loss | -$1,028 | -$1,048 | -$1,048 |
| Smallest win | $1,992.00 | $1,992.00 | $1,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 5 / 1 | 3 / 1 | 6 / 1 |
| Win streak avg | 1.43 | 1.51 | 1.53 |
| Avg profit per win run | $2,854.52 | $3,002.03 | $3,043.68 |
| Best win run | $9,960 | $5,976 | $11,952 |
| Loss streak max / min | 10 / 1 | 18 / 1 | 12 / 1 |
| Loss streak avg | 3.11 | 3.12 | 3.27 |
| Avg loss per loss run | -$3,169.80 | -$3,182.08 | -$3,331.79 |
| Worst loss run | -$10,190 | -$18,324 | -$12,216 |
| Avg trade run-up | $1,064 | $1,104 | $1,081 |
| Max trade run-up | $2,020 | $2,020 | $2,020 |
| Avg trade run-down | $809 | $831 | $819 |
| Max trade run-down | $1,010 | $1,030 | $1,030 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2021**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$6,524 | -$3,494 | -$10,018 |
| Total trades | 33 | 33 | 66 |
| Win rate | 27.3% | 30.3% | 28.8% |
| Profit factor | 0.733 | 0.851 | 0.791 |
| Sharpe (ann.) | -2.30 | -1.20 | -1.75 |
| Max drawdown | -$9,490 | -$8,276 | -$12,764 |
| Max run-up | $3,984 | $6,950 | $5,844 |
| Expectancy / trade | -$197.70 | -$105.88 | -$151.79 |
| Avg win | $1,992.00 | $1,992.00 | $1,992.00 |
| Avg loss | -$1,018.83 | -$1,018.00 | -$1,018.43 |
| Payoff (avg W / avg L) | 1.96 | 1.96 | 1.96 |
| Avg R multiple | -0.20 | -0.11 | -0.15 |
| Largest win | $1,992 | $1,992 | $1,992 |
| Largest loss | -$1,028 | -$1,018 | -$1,028 |
| Smallest win | $1,992.00 | $1,992.00 | $1,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 2 / 1 | 3 / 1 | 2 / 1 |
| Win streak avg | 1.12 | 1.43 | 1.27 |
| Avg profit per win run | $2,241.00 | $2,845.71 | $2,523.20 |
| Best win run | $3,984 | $5,976 | $3,984 |
| Loss streak max / min | 6 / 1 | 5 / 1 | 6 / 1 |
| Loss streak avg | 3.00 | 2.88 | 2.94 |
| Avg loss per loss run | -$3,056.50 | -$2,926.75 | -$2,991.62 |
| Worst loss run | -$6,108 | -$5,090 | -$6,108 |
| Avg trade run-up | $1,077 | $1,161 | $1,119 |
| Max trade run-up | $2,010 | $2,010 | $2,010 |
| Avg trade run-down | $830 | $831 | $830 |
| Max trade run-down | $1,010 | $1,000 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2022**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$5,858 | $10,308 | $4,450 |
| Total trades | 121 | 114 | 235 |
| Win rate | 32.2% | 36.8% | 34.5% |
| Profit factor | 0.930 | 1.141 | 1.028 |
| Sharpe (ann.) | -0.54 | 0.98 | 0.21 |
| Max drawdown | -$20,326 | -$11,448 | -$25,592 |
| Max run-up | $12,520 | $19,852 | $27,164 |
| Expectancy / trade | -$48.41 | $90.42 | $18.94 |
| Avg win | $1,992.00 | $1,992.00 | $1,992.00 |
| Avg loss | -$1,018.85 | -$1,018.83 | -$1,018.84 |
| Payoff (avg W / avg L) | 1.96 | 1.96 | 1.96 |
| Avg R multiple | -0.05 | 0.09 | 0.02 |
| Largest win | $1,992 | $1,992 | $1,992 |
| Largest loss | -$1,028 | -$1,048 | -$1,048 |
| Smallest win | $1,992.00 | $1,992.00 | $1,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 5 / 1 | 3 / 1 | 4 / 1 |
| Win streak avg | 1.44 | 1.50 | 1.62 |
| Avg profit per win run | $2,877.33 | $2,988.00 | $3,227.04 |
| Best win run | $9,960 | $5,976 | $7,968 |
| Loss streak max / min | 10 / 1 | 7 / 1 | 9 / 1 |
| Loss streak avg | 3.04 | 2.48 | 3.02 |
| Avg loss per loss run | -$3,094.30 | -$2,529.52 | -$3,076.51 |
| Worst loss run | -$10,190 | -$7,156 | -$9,162 |
| Avg trade run-up | $1,097 | $1,108 | $1,102 |
| Max trade run-up | $2,020 | $2,010 | $2,020 |
| Avg trade run-down | $799 | $827 | $812 |
| Max trade run-down | $1,010 | $1,030 | $1,030 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2023**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $14,920 | -$32,438 | -$17,518 |
| Total trades | 145 | 91 | 236 |
| Win rate | 37.2% | 22.0% | 31.4% |
| Profit factor | 1.161 | 0.551 | 0.894 |
| Sharpe (ann.) | 1.12 | -4.51 | -0.84 |
| Max drawdown | -$10,356 | -$34,430 | -$26,720 |
| Max run-up | $22,134 | $5,888 | $14,874 |
| Expectancy / trade | $102.90 | -$356.46 | -$74.23 |
| Avg win | $1,992.00 | $1,992.00 | $1,992.00 |
| Avg loss | -$1,018.11 | -$1,018.00 | -$1,018.06 |
| Payoff (avg W / avg L) | 1.96 | 1.96 | 1.96 |
| Avg R multiple | 0.10 | -0.36 | -0.07 |
| Largest win | $1,992 | $1,992 | $1,992 |
| Largest loss | -$1,028 | -$1,018 | -$1,028 |
| Smallest win | $1,992.00 | $1,992.00 | $1,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 5 / 1 | 2 / 1 | 6 / 1 |
| Win streak avg | 1.54 | 1.25 | 1.54 |
| Avg profit per win run | $3,073.37 | $2,490.00 | $3,071.00 |
| Best win run | $9,960 | $3,984 | $11,952 |
| Loss streak max / min | 9 / 1 | 18 / 1 | 12 / 1 |
| Loss streak avg | 2.53 | 4.44 | 3.31 |
| Avg loss per loss run | -$2,573.56 | -$4,517.38 | -$3,365.84 |
| Worst loss run | -$9,162 | -$18,324 | -$12,216 |
| Avg trade run-up | $1,126 | $866 | $1,026 |
| Max trade run-up | $2,010 | $2,020 | $2,020 |
| Avg trade run-down | $768 | $888 | $814 |
| Max trade run-down | $1,010 | $1,000 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2024**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$36,290 | $9,658 | -$26,632 |
| Total trades | 145 | 94 | 239 |
| Win rate | 25.5% | 37.2% | 30.1% |
| Profit factor | 0.670 | 1.161 | 0.843 |
| Sharpe (ann.) | -3.02 | 1.11 | -1.28 |
| Max drawdown | -$43,798 | -$10,444 | -$39,632 |
| Max run-up | $7,748 | $16,382 | $16,206 |
| Expectancy / trade | -$250.28 | $102.74 | -$111.43 |
| Avg win | $1,992.00 | $1,992.00 | $1,992.00 |
| Avg loss | -$1,018.46 | -$1,018.00 | -$1,018.30 |
| Payoff (avg W / avg L) | 1.96 | 1.96 | 1.96 |
| Avg R multiple | -0.25 | 0.10 | -0.11 |
| Largest win | $1,992 | $1,992 | $1,992 |
| Largest loss | -$1,028 | -$1,018 | -$1,028 |
| Smallest win | $1,992.00 | $1,992.00 | $1,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 3 / 1 | 3 / 1 | 4 / 1 |
| Win streak avg | 1.32 | 1.75 | 1.50 |
| Avg profit per win run | $2,632.29 | $3,486.00 | $2,988.00 |
| Best win run | $5,976 | $5,976 | $7,968 |
| Loss streak max / min | 10 / 1 | 8 / 1 | 12 / 1 |
| Loss streak avg | 3.72 | 2.81 | 3.41 |
| Avg loss per loss run | -$3,792.90 | -$2,860.10 | -$3,470.53 |
| Worst loss run | -$10,180 | -$8,144 | -$12,216 |
| Avg trade run-up | $972 | $1,311 | $1,105 |
| Max trade run-up | $2,010 | $2,020 | $2,020 |
| Avg trade run-down | $854 | $782 | $826 |
| Max trade run-down | $1,010 | $1,000 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

> Cost ladder basis: $9 round-turn per contract.
wrote /Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/out_wide_1to2/metrics_wimb_inv.json

