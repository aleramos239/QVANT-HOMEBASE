## ledger_wimb_2NQ.csv — report card

```
NET -$43,588 · PF 0.92 · Sharpe -0.63 · WR 32.0% · MaxDD -$46,296 · 776 trades
```

**Equity curve** ($0 → -$43,588)

```
⣿⣿⣶⣷⣦⣦⣦⣦⣶⣷⣷⣷⣶⣤⣶⣶⣶⣦⣶⣦⣦⣦⣤⣄⣀⣀⣀⣄⣤⣤⣤⣄⣤⣀⣤⣄⣄⣄⣤⣤⣤⣤⣤⣤⣀⣤⣦⣤⣦⣦⣤⣤⣤⣤⣤⣄⣄⣄⣄⣀
```

**Edge inference** — EV -$56.17/trade · bootstrap 95% CI [-$153.18, $44.65] · P(EV ≤ 0): 87.3% · 10,000 resamples

**WR stability** — monthly WR 0.0%–52.9% (pooled 32.0%) · wobble 0.9× luck (steady) · worst 3-mo 20.8% (n=48) · 40 months

**Year by year (combined)**

| Year | Trades | Net | Win rate | PF | Sharpe | Max DD | Avg trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021 | 66 | -$22,058 | 22.7% | 0.58 | -4.17 | -$24,970 | -$334.21 |
| 2022 | 235 | -$10,520 | 32.3% | 0.94 | -0.50 | -$25,732 | -$44.77 |
| 2023 | 236 | $3,552 | 34.3% | 1.02 | 0.17 | -$16,640 | $15.05 |
| 2024 | 239 | -$14,562 | 31.8% | 0.91 | -0.69 | -$25,150 | -$60.93 |
| **All** | **776** | **-$43,588** | **32.0%** | **0.92** | **-0.63** | **-$46,296** | **-$56.17** |

**Cost ladder** — net edge vs friction multiple

| Friction | Net | $/trade | PF | Sharpe | Win rate | Max DD | |
|---|---:|---:|---:|---:|---:|---:|---|
| 0.5× | -$36,604 | -$47.17 | 0.931 | -0.53 | 32.0% | -$43,173 | **DEAD** |
| 1× | -$43,588 | -$56.17 | 0.919 | -0.63 | 32.0% | -$46,296 | **DEAD** · **as run** |
| 2× | -$57,556 | -$74.17 | 0.895 | -0.84 | 32.0% | -$57,556 | **DEAD** |
| 4× | -$85,492 | -$110.17 | 0.849 | -1.25 | 32.0% | -$85,492 | **DEAD** |

**Breakeven at -2.12× friction.** Under 2× — a routine slippage miss erases it.

**Breakeven multiple by year** — the pooled figure can hide a newer era that dies earlier

| Year | 0.5× | 1× | 2× | 4× | Breakeven |
|---|---:|---:|---:|---:|---:|
| 2021 | -$21,464 | -$22,058 | -$23,246 | -$25,622 | -17.57× |
| 2022 | -$8,405 | -$10,520 | -$14,750 | -$23,210 | -1.49× |
| 2023 | $5,676 | $3,552 | -$696 | -$9,192 | 1.84× |
| 2024 | -$12,411 | -$14,562 | -$18,864 | -$27,468 | -2.38× |

> The ladder subtracts money and nothing else, so it is a **lower bound on the damage** — real added friction also moves fills, so trades appear and disappear. `onyx.lab.costcurve.slip_stress` re-runs the strategy and captures that; this cannot.

**Pooled — all years**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $2,114 | -$45,702 | -$43,588 |
| Total trades | 332 | 444 | 776 |
| Win rate | 34.0% | 30.4% | 32.0% |
| Profit factor | 1.009 | 0.855 | 0.919 |
| Sharpe (ann.) | 0.07 | -1.18 | -0.63 |
| Max drawdown | -$23,408 | -$56,050 | -$46,296 |
| Max run-up | $35,966 | $18,550 | $27,858 |
| Expectancy / trade | $6.37 | -$102.93 | -$56.17 |
| Avg win | $1,992.00 | $1,992.00 | $1,992.00 |
| Avg loss | -$1,018.18 | -$1,018.19 | -$1,018.19 |
| Payoff (avg W / avg L) | 1.96 | 1.96 | 1.96 |
| Avg R multiple | 0.01 | -0.10 | -0.06 |
| Largest win | $1,992 | $1,992 | $1,992 |
| Largest loss | -$1,028 | -$1,028 | -$1,028 |
| Smallest win | $1,992.00 | $1,992.00 | $1,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 4 / 1 | 4 / 1 | 6 / 1 |
| Win streak avg | 1.55 | 1.55 | 1.50 |
| Avg profit per win run | $3,083.51 | $3,091.03 | $2,994.04 |
| Best win run | $7,968 | $7,968 | $11,952 |
| Loss streak max / min | 10 / 1 | 15 / 1 | 15 / 1 |
| Loss streak avg | 2.96 | 3.55 | 3.18 |
| Avg loss per loss run | -$3,013.27 | -$3,616.34 | -$3,238.58 |
| Worst loss run | -$10,180 | -$15,270 | -$15,270 |
| Avg trade run-up | $1,069 | $1,071 | $1,070 |
| Max trade run-up | $2,030 | $2,020 | $2,030 |
| Avg trade run-down | $803 | $832 | $820 |
| Max trade run-down | $1,010 | $1,010 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2021**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$6,514 | -$15,544 | -$22,058 |
| Total trades | 33 | 33 | 66 |
| Win rate | 27.3% | 18.2% | 22.7% |
| Profit factor | 0.733 | 0.435 | 0.575 |
| Sharpe (ann.) | -2.30 | -6.34 | -4.17 |
| Max drawdown | -$12,304 | -$16,474 | -$24,970 |
| Max run-up | $4,958 | $3,984 | $4,958 |
| Expectancy / trade | -$197.39 | -$471.03 | -$334.21 |
| Avg win | $1,992.00 | $1,992.00 | $1,992.00 |
| Avg loss | -$1,018.42 | -$1,018.37 | -$1,018.39 |
| Payoff (avg W / avg L) | 1.96 | 1.96 | 1.96 |
| Avg R multiple | -0.20 | -0.47 | -0.33 |
| Largest win | $1,992 | $1,992 | $1,992 |
| Largest loss | -$1,028 | -$1,028 | -$1,028 |
| Smallest win | $1,992.00 | $1,992.00 | $1,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 2 / 1 | 2 / 2 | 2 / 1 |
| Win streak avg | 1.29 | 2.00 | 1.15 |
| Avg profit per win run | $2,561.14 | $3,984.00 | $2,298.46 |
| Best win run | $3,984 | $3,984 | $3,984 |
| Loss streak max / min | 10 / 1 | 14 / 3 | 15 / 1 |
| Loss streak avg | 3.43 | 6.75 | 3.92 |
| Avg loss per loss run | -$3,491.71 | -$6,874.00 | -$3,995.23 |
| Worst loss run | -$10,180 | -$14,252 | -$15,270 |
| Avg trade run-up | $933 | $1,007 | $970 |
| Max trade run-up | $2,020 | $2,010 | $2,020 |
| Avg trade run-down | $818 | $918 | $868 |
| Max trade run-down | $1,010 | $1,010 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2022**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$1,692 | -$8,828 | -$10,520 |
| Total trades | 114 | 121 | 235 |
| Win rate | 33.3% | 31.4% | 32.3% |
| Profit factor | 0.978 | 0.896 | 0.935 |
| Sharpe (ann.) | -0.17 | -0.83 | -0.50 |
| Max drawdown | -$20,800 | -$16,650 | -$25,732 |
| Max run-up | $21,188 | $10,802 | $18,442 |
| Expectancy / trade | -$14.84 | -$72.96 | -$44.77 |
| Avg win | $1,992.00 | $1,992.00 | $1,992.00 |
| Avg loss | -$1,018.26 | -$1,018.36 | -$1,018.31 |
| Payoff (avg W / avg L) | 1.96 | 1.96 | 1.96 |
| Avg R multiple | -0.01 | -0.07 | -0.04 |
| Largest win | $1,992 | $1,992 | $1,992 |
| Largest loss | -$1,028 | -$1,028 | -$1,028 |
| Smallest win | $1,992.00 | $1,992.00 | $1,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 3 / 1 | 3 / 1 | 6 / 1 |
| Win streak avg | 1.52 | 1.46 | 1.49 |
| Avg profit per win run | $3,027.84 | $2,911.38 | $2,968.47 |
| Best win run | $5,976 | $5,976 | $11,952 |
| Loss streak max / min | 7 / 1 | 10 / 1 | 10 / 1 |
| Loss streak avg | 3.04 | 3.07 | 3.12 |
| Avg loss per loss run | -$3,095.52 | -$3,130.52 | -$3,174.75 |
| Worst loss run | -$7,126 | -$10,180 | -$10,180 |
| Avg trade run-up | $1,085 | $1,053 | $1,068 |
| Max trade run-up | $2,030 | $2,020 | $2,030 |
| Avg trade run-down | $810 | $828 | $819 |
| Max trade run-down | $1,010 | $1,010 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2023**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $30,762 | -$27,210 | $3,552 |
| Total trades | 91 | 145 | 236 |
| Win rate | 45.1% | 27.6% | 34.3% |
| Profit factor | 1.604 | 0.745 | 1.023 |
| Sharpe (ann.) | 3.56 | -2.21 | 0.17 |
| Max drawdown | -$5,276 | -$30,176 | -$16,640 |
| Max run-up | $31,780 | $11,820 | $22,534 |
| Expectancy / trade | $338.04 | -$187.66 | $15.05 |
| Avg win | $1,992.00 | $1,992.00 | $1,992.00 |
| Avg loss | -$1,018.20 | -$1,018.00 | -$1,018.06 |
| Payoff (avg W / avg L) | 1.96 | 1.96 | 1.96 |
| Avg R multiple | 0.34 | -0.19 | 0.02 |
| Largest win | $1,992 | $1,992 | $1,992 |
| Largest loss | -$1,028 | -$1,018 | -$1,028 |
| Smallest win | $1,992.00 | $1,992.00 | $1,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 4 / 1 | 4 / 1 | 6 / 1 |
| Win streak avg | 1.71 | 1.43 | 1.62 |
| Avg profit per win run | $3,403.00 | $2,845.71 | $3,227.04 |
| Best win run | $7,968 | $7,968 | $11,952 |
| Loss streak max / min | 5 / 1 | 15 / 1 | 12 / 1 |
| Loss streak avg | 2.08 | 3.75 | 3.10 |
| Avg loss per loss run | -$2,121.25 | -$3,817.50 | -$3,156.00 |
| Worst loss run | -$5,090 | -$15,270 | -$12,216 |
| Avg trade run-up | $1,306 | $1,031 | $1,137 |
| Max trade run-up | $2,010 | $2,010 | $2,010 |
| Avg trade run-down | $736 | $838 | $798 |
| Max trade run-down | $1,010 | $1,000 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2024**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$20,442 | $5,880 | -$14,562 |
| Total trades | 94 | 145 | 239 |
| Win rate | 26.6% | 35.2% | 31.8% |
| Profit factor | 0.709 | 1.061 | 0.912 |
| Sharpe (ann.) | -2.58 | 0.45 | -0.69 |
| Max drawdown | -$23,408 | -$10,194 | -$25,150 |
| Max run-up | $9,916 | $18,550 | $20,234 |
| Expectancy / trade | -$217.47 | $40.55 | -$60.93 |
| Avg win | $1,992.00 | $1,992.00 | $1,992.00 |
| Avg loss | -$1,018.00 | -$1,018.21 | -$1,018.12 |
| Payoff (avg W / avg L) | 1.96 | 1.96 | 1.96 |
| Avg R multiple | -0.22 | 0.04 | -0.06 |
| Largest win | $1,992 | $1,992 | $1,992 |
| Largest loss | -$1,018 | -$1,028 | -$1,028 |
| Smallest win | $1,992.00 | $1,992.00 | $1,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 3 / 1 | 3 / 1 | 5 / 1 |
| Win streak avg | 1.39 | 1.65 | 1.43 |
| Avg profit per win run | $2,766.67 | $3,277.16 | $2,856.45 |
| Best win run | $5,976 | $5,976 | $9,960 |
| Loss streak max / min | 9 / 1 | 8 / 1 | 11 / 1 |
| Loss streak avg | 3.63 | 3.13 | 3.08 |
| Avg loss per loss run | -$3,696.95 | -$3,190.40 | -$3,131.21 |
| Worst loss run | -$9,162 | -$8,144 | -$11,198 |
| Avg trade run-up | $866 | $1,141 | $1,033 |
| Max trade run-up | $2,020 | $2,020 | $2,020 |
| Avg trade run-down | $854 | $811 | $828 |
| Max trade run-down | $1,000 | $1,010 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

> Cost ladder basis: $9 round-turn per contract.
wrote /Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/out_wide_1to2/metrics_wimb.json

