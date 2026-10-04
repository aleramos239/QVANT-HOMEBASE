## ledger_long_2NQ.csv — report card

```
NET -$27,698 · PF 0.95 · Sharpe -0.40 · WR 32.7% · MaxDD -$62,292 · 781 trades
```

**Equity curve** ($0 → -$27,698)

```
⣦⣦⣤⣤⣤⣄⣤⣄⣤⣤⣤⣤⣄⣤⣤⣤⣄⣄⣀⣄⣄⣀⣄⣀⣀⣄⣤⣦⣦⣦⣦⣦⣶⣶⣶⣶⣶⣷⣶⣷⣷⣿⣿⣷⣶⣦⣦⣤⣤⣤⣤⣤⣄⣄⣄⣀⣀⣀⣀⣀
```

**Edge inference** — EV -$35.46/trade · bootstrap 95% CI [-$135.64, $64.69] · P(EV ≤ 0): 76.8% · 10,000 resamples

**WR stability** — monthly WR 10.0%–55.6% (pooled 32.7%) · wobble 0.9× luck (steady) · worst 3-mo 16.9% (n=59) · 40 months

**Year by year (combined)**

| Year | Trades | Net | Win rate | PF | Sharpe | Max DD | Avg trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021 | 67 | -$11,046 | 28.4% | 0.77 | -1.91 | -$19,802 | -$164.87 |
| 2022 | 236 | -$8,568 | 32.6% | 0.95 | -0.41 | -$23,316 | -$36.31 |
| 2023 | 238 | $46,656 | 40.3% | 1.32 | 2.10 | -$9,558 | $196.03 |
| 2024 | 240 | -$54,740 | 26.2% | 0.70 | -2.73 | -$62,292 | -$228.08 |
| **All** | **781** | **-$27,698** | **32.7%** | **0.95** | **-0.40** | **-$62,292** | **-$35.46** |

**Cost ladder** — net edge vs friction multiple

| Friction | Net | $/trade | PF | Sharpe | Win rate | Max DD | |
|---|---:|---:|---:|---:|---:|---:|---|
| 0.5× | -$20,669 | -$26.46 | 0.961 | -0.30 | 32.7% | -$60,411 | **DEAD** |
| 1× | -$27,698 | -$35.46 | 0.948 | -0.40 | 32.7% | -$62,292 | **DEAD** · **as run** |
| 2× | -$41,756 | -$53.46 | 0.923 | -0.60 | 32.7% | -$66,054 | **DEAD** |
| 4× | -$69,872 | -$89.46 | 0.876 | -1.01 | 32.7% | -$74,174 | **DEAD** |

**Breakeven at -0.97× friction.** Under 2× — a routine slippage miss erases it.

**Breakeven multiple by year** — the pooled figure can hide a newer era that dies earlier

| Year | 0.5× | 1× | 2× | 4× | Breakeven |
|---|---:|---:|---:|---:|---:|
| 2021 | -$10,443 | -$11,046 | -$12,252 | -$14,664 | -8.16× |
| 2022 | -$6,444 | -$8,568 | -$12,816 | -$21,312 | -1.02× |
| 2023 | $48,798 | $46,656 | $42,372 | $33,804 | 11.89× |
| 2024 | -$52,580 | -$54,740 | -$59,060 | -$67,700 | -11.67× |

> The ladder subtracts money and nothing else, so it is a **lower bound on the damage** — real added friction also moves fills, so trades appear and disappear. `onyx.lab.costcurve.slip_stress` re-runs the strategy and captures that; this cannot.

**Pooled — all years**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$27,698 | — | -$27,698 |
| Total trades | 781 | 0 | 781 |
| Win rate | 32.7% | — | 32.7% |
| Profit factor | 0.948 | — | 0.948 |
| Sharpe (ann.) | -0.40 | — | -0.40 |
| Max drawdown | -$62,292 | — | -$62,292 |
| Max run-up | $58,784 | — | $58,784 |
| Expectancy / trade | -$35.46 | — | -$35.46 |
| Avg win | $1,992.00 | — | $1,992.00 |
| Avg loss | -$1,018.36 | — | -$1,018.36 |
| Payoff (avg W / avg L) | 1.96 | — | 1.96 |
| Avg R multiple | -0.04 | — | -0.04 |
| Largest win | $1,992 | — | $1,992 |
| Largest loss | -$1,028 | — | -$1,028 |
| Smallest win | $1,992.00 | — | $1,992.00 |
| Smallest loss | -$1,018.00 | — | -$1,018.00 |
| Win streak max / min | 5 / 1 | — / — | 5 / 1 |
| Win streak avg | 1.39 | — | 1.39 |
| Avg profit per win run | $2,775.74 | — | $2,775.74 |
| Best win run | $9,960 | — | $9,960 |
| Loss streak max / min | 14 / 1 | — / — | 14 / 1 |
| Loss streak avg | 2.86 | — | 2.86 |
| Avg loss per loss run | -$2,911.18 | — | -$2,911.18 |
| Worst loss run | -$14,252 | — | -$14,252 |
| Avg trade run-up | $1,069 | — | $1,069 |
| Max trade run-up | $2,030 | — | $2,030 |
| Avg trade run-down | $806 | — | $806 |
| Max trade run-down | $1,010 | — | $1,010 |
| Avg contracts | 2.00 | — | 2.00 |
| Max / min contracts | 2 / 2 | — / — | 2 / 2 |

**2021**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$11,046 | — | -$11,046 |
| Total trades | 67 | 0 | 67 |
| Win rate | 28.4% | — | 28.4% |
| Profit factor | 0.774 | — | 0.774 |
| Sharpe (ann.) | -1.91 | — | -1.91 |
| Max drawdown | -$19,802 | — | -$19,802 |
| Max run-up | $6,906 | — | $6,906 |
| Expectancy / trade | -$164.87 | — | -$164.87 |
| Avg win | $1,992.00 | — | $1,992.00 |
| Avg loss | -$1,018.62 | — | -$1,018.62 |
| Payoff (avg W / avg L) | 1.96 | — | 1.96 |
| Avg R multiple | -0.16 | — | -0.16 |
| Largest win | $1,992 | — | $1,992 |
| Largest loss | -$1,028 | — | -$1,028 |
| Smallest win | $1,992.00 | — | $1,992.00 |
| Smallest loss | -$1,018.00 | — | -$1,018.00 |
| Win streak max / min | 3 / 1 | — / — | 3 / 1 |
| Win streak avg | 1.27 | — | 1.27 |
| Avg profit per win run | $2,523.20 | — | $2,523.20 |
| Best win run | $5,976 | — | $5,976 |
| Loss streak max / min | 9 / 1 | — / — | 9 / 1 |
| Loss streak avg | 3.20 | — | 3.20 |
| Avg loss per loss run | -$3,259.60 | — | -$3,259.60 |
| Worst loss run | -$9,162 | — | -$9,162 |
| Avg trade run-up | $1,020 | — | $1,020 |
| Max trade run-up | $2,020 | — | $2,020 |
| Avg trade run-down | $825 | — | $825 |
| Max trade run-down | $1,010 | — | $1,010 |
| Avg contracts | 2.00 | — | 2.00 |
| Max / min contracts | 2 / 2 | — / — | 2 / 2 |

**2022**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$8,568 | — | -$8,568 |
| Total trades | 236 | 0 | 236 |
| Win rate | 32.6% | — | 32.6% |
| Profit factor | 0.947 | — | 0.947 |
| Sharpe (ann.) | -0.41 | — | -0.41 |
| Max drawdown | -$23,316 | — | -$23,316 |
| Max run-up | $16,534 | — | $16,534 |
| Expectancy / trade | -$36.31 | — | -$36.31 |
| Avg win | $1,992.00 | — | $1,992.00 |
| Avg loss | -$1,018.57 | — | -$1,018.57 |
| Payoff (avg W / avg L) | 1.96 | — | 1.96 |
| Avg R multiple | -0.04 | — | -0.04 |
| Largest win | $1,992 | — | $1,992 |
| Largest loss | -$1,028 | — | -$1,028 |
| Smallest win | $1,992.00 | — | $1,992.00 |
| Smallest loss | -$1,018.00 | — | -$1,018.00 |
| Win streak max / min | 4 / 1 | — / — | 4 / 1 |
| Win streak avg | 1.38 | — | 1.38 |
| Avg profit per win run | $2,739.00 | — | $2,739.00 |
| Best win run | $7,968 | — | $7,968 |
| Loss streak max / min | 13 / 1 | — / — | 13 / 1 |
| Loss streak avg | 2.84 | — | 2.84 |
| Avg loss per loss run | -$2,892.00 | — | -$2,892.00 |
| Worst loss run | -$13,234 | — | -$13,234 |
| Avg trade run-up | $1,090 | — | $1,090 |
| Max trade run-up | $2,030 | — | $2,030 |
| Avg trade run-down | $805 | — | $805 |
| Max trade run-down | $1,010 | — | $1,010 |
| Avg contracts | 2.00 | — | 2.00 |
| Max / min contracts | 2 / 2 | — / — | 2 / 2 |

**2023**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $46,656 | — | $46,656 |
| Total trades | 238 | 0 | 238 |
| Win rate | 40.3% | — | 40.3% |
| Profit factor | 1.323 | — | 1.323 |
| Sharpe (ann.) | 2.10 | — | 2.10 |
| Max drawdown | -$9,558 | — | -$9,558 |
| Max run-up | $54,976 | — | $54,976 |
| Expectancy / trade | $196.03 | — | $196.03 |
| Avg win | $1,992.00 | — | $1,992.00 |
| Avg loss | -$1,018.14 | — | -$1,018.14 |
| Payoff (avg W / avg L) | 1.96 | — | 1.96 |
| Avg R multiple | 0.20 | — | 0.20 |
| Largest win | $1,992 | — | $1,992 |
| Largest loss | -$1,028 | — | -$1,028 |
| Smallest win | $1,992.00 | — | $1,992.00 |
| Smallest loss | -$1,018.00 | — | -$1,018.00 |
| Win streak max / min | 5 / 1 | — / — | 5 / 1 |
| Win streak avg | 1.50 | — | 1.50 |
| Avg profit per win run | $2,988.00 | — | $2,988.00 |
| Best win run | $9,960 | — | $9,960 |
| Loss streak max / min | 9 / 1 | — / — | 9 / 1 |
| Loss streak avg | 2.18 | — | 2.18 |
| Avg loss per loss run | -$2,224.25 | — | -$2,224.25 |
| Worst loss run | -$9,162 | — | -$9,162 |
| Avg trade run-up | $1,197 | — | $1,197 |
| Max trade run-up | $2,010 | — | $2,010 |
| Avg trade run-down | $756 | — | $756 |
| Max trade run-down | $1,010 | — | $1,010 |
| Avg contracts | 2.00 | — | 2.00 |
| Max / min contracts | 2 / 2 | — / — | 2 / 2 |

**2024**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$54,740 | — | -$54,740 |
| Total trades | 240 | 0 | 240 |
| Win rate | 26.2% | — | 26.2% |
| Profit factor | 0.696 | — | 0.696 |
| Sharpe (ann.) | -2.73 | — | -2.73 |
| Max drawdown | -$62,292 | — | -$62,292 |
| Max run-up | $8,942 | — | $8,942 |
| Expectancy / trade | -$228.08 | — | -$228.08 |
| Avg win | $1,992.00 | — | $1,992.00 |
| Avg loss | -$1,018.28 | — | -$1,018.28 |
| Payoff (avg W / avg L) | 1.96 | — | 1.96 |
| Avg R multiple | -0.23 | — | -0.23 |
| Largest win | $1,992 | — | $1,992 |
| Largest loss | -$1,028 | — | -$1,028 |
| Smallest win | $1,992.00 | — | $1,992.00 |
| Smallest loss | -$1,018.00 | — | -$1,018.00 |
| Win streak max / min | 4 / 1 | — / — | 4 / 1 |
| Win streak avg | 1.29 | — | 1.29 |
| Avg profit per win run | $2,561.14 | — | $2,561.14 |
| Best win run | $7,968 | — | $7,968 |
| Loss streak max / min | 14 / 1 | — / — | 14 / 1 |
| Loss streak avg | 3.54 | — | 3.54 |
| Avg loss per loss run | -$3,604.72 | — | -$3,604.72 |
| Worst loss run | -$14,252 | — | -$14,252 |
| Avg trade run-up | $935 | — | $935 |
| Max trade run-up | $2,020 | — | $2,020 |
| Avg trade run-down | $853 | — | $853 |
| Max trade run-down | $1,010 | — | $1,010 |
| Avg contracts | 2.00 | — | 2.00 |
| Max / min contracts | 2 / 2 | — / — | 2 / 2 |

> Cost ladder basis: $9 round-turn per contract.
wrote /Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/out_wide_1to2/metrics_long.json

