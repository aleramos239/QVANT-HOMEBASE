## ledger_flow_inv_2NQ.csv — report card

```
NET -$37,246 · PF 0.93 · Sharpe -0.51 · WR 32.3% · MaxDD -$44,374 · 817 trades
```

**Equity curve** ($0 → -$37,246)

```
⣿⣷⣦⣦⣤⣤⣤⣄⣤⣦⣦⣶⣦⣦⣶⣶⣶⣦⣷⣿⣷⣶⣷⣷⣦⣦⣦⣶⣦⣶⣦⣤⣦⣦⣦⣦⣤⣦⣦⣶⣦⣶⣶⣶⣦⣶⣶⣶⣶⣷⣦⣤⣦⣤⣦⣤⣄⣄⣄⣀
```

**Edge inference** — EV -$45.59/trade · bootstrap 95% CI [-$141.39, $50.26] · P(EV ≤ 0): 82.4% · 10,000 resamples

**WR stability** — monthly WR 0.0%–70.0% (pooled 32.3%) · wobble 1.2× luck (steady) · worst 3-mo 19.1% (n=47) · 40 months

**Year by year (combined)**

| Year | Trades | Net | Win rate | PF | Sharpe | Max DD | Avg trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021 | 68 | -$24,104 | 22.1% | 0.55 | -4.47 | -$30,026 | -$354.47 |
| 2022 | 248 | $18,346 | 36.3% | 1.11 | 0.81 | -$21,466 | $73.98 |
| 2023 | 249 | -$3,682 | 33.3% | 0.98 | -0.17 | -$21,826 | -$14.79 |
| 2024 | 252 | -$27,806 | 30.2% | 0.84 | -1.27 | -$32,188 | -$110.34 |
| **All** | **817** | **-$37,246** | **32.3%** | **0.93** | **-0.51** | **-$44,374** | **-$45.59** |

**Cost ladder** — net edge vs friction multiple

| Friction | Net | $/trade | PF | Sharpe | Win rate | Max DD | |
|---|---:|---:|---:|---:|---:|---:|---|
| 0.5× | -$29,893 | -$36.59 | 0.946 | -0.41 | 32.3% | -$39,352 | **DEAD** |
| 1× | -$37,246 | -$45.59 | 0.934 | -0.51 | 32.3% | -$44,374 | **DEAD** · **as run** |
| 2× | -$51,952 | -$63.59 | 0.909 | -0.72 | 32.3% | -$54,418 | **DEAD** |
| 4× | -$81,364 | -$99.59 | 0.863 | -1.12 | 32.3% | -$81,364 | **DEAD** |

**Breakeven at -1.53× friction.** Under 2× — a routine slippage miss erases it.

**Breakeven multiple by year** — the pooled figure can hide a newer era that dies earlier

| Year | 0.5× | 1× | 2× | 4× | Breakeven |
|---|---:|---:|---:|---:|---:|
| 2021 | -$23,492 | -$24,104 | -$25,328 | -$27,776 | -18.69× |
| 2022 | $20,578 | $18,346 | $13,882 | $4,954 | 5.11× |
| 2023 | -$1,441 | -$3,682 | -$8,164 | -$17,128 | 0.18× |
| 2024 | -$25,538 | -$27,806 | -$32,342 | -$41,414 | -5.13× |

> The ladder subtracts money and nothing else, so it is a **lower bound on the damage** — real added friction also moves fills, so trades appear and disappear. `onyx.lab.costcurve.slip_stress` re-runs the strategy and captures that; this cannot.

**Pooled — all years**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $5,408 | -$42,654 | -$37,246 |
| Total trades | 444 | 373 | 817 |
| Win rate | 34.2% | 30.0% | 32.3% |
| Profit factor | 1.018 | 0.840 | 0.934 |
| Sharpe (ann.) | 0.14 | -1.31 | -0.51 |
| Max drawdown | -$21,964 | -$42,654 | -$44,374 |
| Max run-up | $35,878 | $23,924 | $38,686 |
| Expectancy / trade | $12.18 | -$114.35 | -$45.59 |
| Avg win | $1,992.00 | $1,992.00 | $1,992.00 |
| Avg loss | -$1,018.41 | -$1,018.23 | -$1,018.33 |
| Payoff (avg W / avg L) | 1.96 | 1.96 | 1.96 |
| Avg R multiple | 0.01 | -0.11 | -0.05 |
| Largest win | $1,992 | $1,992 | $1,992 |
| Largest loss | -$1,038 | -$1,028 | -$1,038 |
| Smallest win | $1,992.00 | $1,992.00 | $1,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 4 / 1 | 5 / 1 | 6 / 1 |
| Win streak avg | 1.43 | 1.44 | 1.50 |
| Avg profit per win run | $2,856.45 | $2,860.31 | $2,988.00 |
| Best win run | $7,968 | $9,960 | $11,952 |
| Loss streak max / min | 11 / 1 | 16 / 1 | 15 / 1 |
| Loss streak avg | 2.73 | 3.30 | 3.12 |
| Avg loss per loss run | -$2,779.21 | -$3,364.03 | -$3,181.55 |
| Worst loss run | -$11,198 | -$16,288 | -$15,270 |
| Avg trade run-up | $1,078 | $1,073 | $1,076 |
| Max trade run-up | $2,020 | $2,020 | $2,020 |
| Avg trade run-down | $790 | $846 | $815 |
| Max trade run-down | $1,020 | $1,010 | $1,020 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2021**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$2,584 | -$21,520 | -$24,104 |
| Total trades | 38 | 30 | 68 |
| Win rate | 31.6% | 10.0% | 22.1% |
| Profit factor | 0.902 | 0.217 | 0.553 |
| Sharpe (ann.) | -0.76 | -12.40 | -4.47 |
| Max drawdown | -$10,322 | -$21,520 | -$30,026 |
| Max run-up | $5,922 | $2,966 | $6,950 |
| Expectancy / trade | -$68.00 | -$717.33 | -$354.47 |
| Avg win | $1,992.00 | $1,992.00 | $1,992.00 |
| Avg loss | -$1,018.77 | -$1,018.37 | -$1,018.57 |
| Payoff (avg W / avg L) | 1.96 | 1.96 | 1.96 |
| Avg R multiple | -0.07 | -0.72 | -0.35 |
| Largest win | $1,992 | $1,992 | $1,992 |
| Largest loss | -$1,028 | -$1,028 | -$1,028 |
| Smallest win | $1,992.00 | $1,992.00 | $1,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 2 / 1 | 1 / 1 | 3 / 1 |
| Win streak avg | 1.33 | 1.00 | 1.36 |
| Avg profit per win run | $2,656.00 | $1,992.00 | $2,716.36 |
| Best win run | $3,984 | $1,992 | $5,976 |
| Loss streak max / min | 6 / 1 | 16 / 1 | 13 / 1 |
| Loss streak avg | 2.89 | 6.75 | 4.82 |
| Avg loss per loss run | -$2,943.11 | -$6,874.00 | -$4,907.64 |
| Worst loss run | -$6,118 | -$16,288 | -$13,234 |
| Avg trade run-up | $1,049 | $951 | $1,006 |
| Max trade run-up | $2,020 | $2,010 | $2,020 |
| Avg trade run-down | $794 | $938 | $858 |
| Max trade run-down | $1,010 | $1,010 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2022**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $5,008 | $13,338 | $18,346 |
| Total trades | 134 | 114 | 248 |
| Win rate | 35.1% | 37.7% | 36.3% |
| Profit factor | 1.057 | 1.184 | 1.114 |
| Sharpe (ann.) | 0.41 | 1.27 | 0.81 |
| Max drawdown | -$13,278 | -$9,250 | -$21,466 |
| Max run-up | $15,780 | $23,924 | $38,686 |
| Expectancy / trade | $37.37 | $117.00 | $73.98 |
| Avg win | $1,992.00 | $1,992.00 | $1,992.00 |
| Avg loss | -$1,018.57 | -$1,018.56 | -$1,018.57 |
| Payoff (avg W / avg L) | 1.96 | 1.96 | 1.96 |
| Avg R multiple | 0.04 | 0.12 | 0.07 |
| Largest win | $1,992 | $1,992 | $1,992 |
| Largest loss | -$1,028 | -$1,028 | -$1,028 |
| Smallest win | $1,992.00 | $1,992.00 | $1,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 3 / 1 | 5 / 1 | 6 / 1 |
| Win streak avg | 1.47 | 1.65 | 1.70 |
| Avg profit per win run | $2,925.75 | $3,294.46 | $3,382.64 |
| Best win run | $5,976 | $9,960 | $11,952 |
| Loss streak max / min | 11 / 1 | 7 / 1 | 11 / 1 |
| Loss streak avg | 2.72 | 2.73 | 2.98 |
| Avg loss per loss run | -$2,769.25 | -$2,781.46 | -$3,036.49 |
| Worst loss run | -$11,198 | -$7,126 | -$11,218 |
| Avg trade run-up | $1,137 | $1,138 | $1,137 |
| Max trade run-up | $2,020 | $2,020 | $2,020 |
| Avg trade run-down | $780 | $817 | $797 |
| Max trade run-down | $1,010 | $1,010 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2023**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $19,016 | -$22,698 | -$3,682 |
| Total trades | 138 | 111 | 249 |
| Win rate | 38.4% | 27.0% | 33.3% |
| Profit factor | 1.220 | 0.725 | 0.978 |
| Sharpe (ann.) | 1.49 | -2.42 | -0.17 |
| Max drawdown | -$7,478 | -$28,674 | -$21,826 |
| Max run-up | $24,194 | $5,932 | $17,170 |
| Expectancy / trade | $137.80 | -$204.49 | -$14.79 |
| Avg win | $1,992.00 | $1,992.00 | $1,992.00 |
| Avg loss | -$1,018.35 | -$1,018.00 | -$1,018.18 |
| Payoff (avg W / avg L) | 1.96 | 1.96 | 1.96 |
| Avg R multiple | 0.14 | -0.20 | -0.01 |
| Largest win | $1,992 | $1,992 | $1,992 |
| Largest loss | -$1,038 | -$1,018 | -$1,038 |
| Smallest win | $1,992.00 | $1,992.00 | $1,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 4 / 1 | 2 / 1 | 5 / 1 |
| Win streak avg | 1.43 | 1.25 | 1.43 |
| Avg profit per win run | $2,853.41 | $2,490.00 | $2,850.62 |
| Best win run | $7,968 | $3,984 | $9,960 |
| Loss streak max / min | 6 / 1 | 10 / 1 | 10 / 1 |
| Loss streak avg | 2.24 | 3.52 | 2.86 |
| Avg loss per loss run | -$2,277.89 | -$3,585.13 | -$2,914.10 |
| Worst loss run | -$6,108 | -$10,180 | -$10,180 |
| Avg trade run-up | $1,179 | $967 | $1,084 |
| Max trade run-up | $2,020 | $2,010 | $2,020 |
| Avg trade run-down | $762 | $852 | $802 |
| Max trade run-down | $1,020 | $1,000 | $1,020 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2024**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$16,032 | -$11,774 | -$27,806 |
| Total trades | 134 | 118 | 252 |
| Win rate | 29.9% | 30.5% | 30.2% |
| Profit factor | 0.832 | 0.859 | 0.845 |
| Sharpe (ann.) | -1.37 | -1.14 | -1.27 |
| Max drawdown | -$21,964 | -$22,224 | -$32,188 |
| Max run-up | $10,846 | $15,540 | $13,152 |
| Expectancy / trade | -$119.64 | -$99.78 | -$110.34 |
| Avg win | $1,992.00 | $1,992.00 | $1,992.00 |
| Avg loss | -$1,018.21 | -$1,018.12 | -$1,018.17 |
| Payoff (avg W / avg L) | 1.96 | 1.96 | 1.96 |
| Avg R multiple | -0.12 | -0.10 | -0.11 |
| Largest win | $1,992 | $1,992 | $1,992 |
| Largest loss | -$1,028 | -$1,028 | -$1,028 |
| Smallest win | $1,992.00 | $1,992.00 | $1,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 4 / 1 | 4 / 1 | 4 / 1 |
| Win streak avg | 1.38 | 1.44 | 1.38 |
| Avg profit per win run | $2,747.59 | $2,868.48 | $2,752.58 |
| Best win run | $7,968 | $7,968 | $7,968 |
| Loss streak max / min | 9 / 1 | 12 / 1 | 15 / 1 |
| Loss streak avg | 3.13 | 3.15 | 3.14 |
| Avg loss per loss run | -$3,190.40 | -$3,211.00 | -$3,199.96 |
| Worst loss run | -$9,162 | -$12,216 | -$15,270 |
| Avg trade run-up | $925 | $1,143 | $1,027 |
| Max trade run-up | $2,020 | $2,020 | $2,020 |
| Avg trade run-down | $826 | $846 | $836 |
| Max trade run-down | $1,010 | $1,010 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

> Cost ladder basis: $9 round-turn per contract.
wrote /Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/out_inv_flow_1to2/metrics_flow_inv.json

