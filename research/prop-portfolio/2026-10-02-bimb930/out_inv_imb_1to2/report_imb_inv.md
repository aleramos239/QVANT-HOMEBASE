## ledger_imb_inv_2NQ.csv — report card

```
NET -$53,540 · PF 0.90 · Sharpe -0.79 · WR 31.5% · MaxDD -$62,766 · 765 trades
```

**Equity curve** ($0 → -$53,540)

```
⣿⣿⣿⣿⣷⣷⣷⣶⣶⣶⣷⣷⣷⣶⣶⣦⣤⣤⣄⣦⣦⣦⣦⣦⣤⣦⣤⣤⣦⣦⣦⣦⣦⣦⣤⣤⣤⣦⣦⣤⣤⣤⣦⣤⣤⣤⣄⣄⣄⣄⣄⣄⣄⣄⣀⣀⣀⣄⣀⣀
```

**Edge inference** — EV -$69.99/trade · bootstrap 95% CI [-$164.48, $28.43] · P(EV ≤ 0): 90.9% · 10,000 resamples

**WR stability** — monthly WR 10.0%–45.5% (pooled 31.5%) · wobble 0.5× luck (steady) · worst 3-mo 22.4% (n=58) · 40 months

**Year by year (combined)**

| Year | Trades | Net | Win rate | PF | Sharpe | Max DD | Avg trade |
|---|---:|---:|---:|---:|---:|---:|---:|
| 2021 | 63 | -$9,954 | 28.6% | 0.78 | -1.83 | -$17,746 | -$158.00 |
| 2022 | 235 | -$16,600 | 31.5% | 0.90 | -0.80 | -$33,628 | -$70.64 |
| 2023 | 234 | -$3,442 | 33.3% | 0.98 | -0.16 | -$15,588 | -$14.71 |
| 2024 | 233 | -$23,544 | 30.5% | 0.86 | -1.16 | -$34,850 | -$101.05 |
| **All** | **765** | **-$53,540** | **31.5%** | **0.90** | **-0.79** | **-$62,766** | **-$69.99** |

**Cost ladder** — net edge vs friction multiple

| Friction | Net | $/trade | PF | Sharpe | Win rate | Max DD | |
|---|---:|---:|---:|---:|---:|---:|---|
| 0.5× | -$46,655 | -$60.99 | 0.912 | -0.69 | 31.5% | -$56,358 | **DEAD** |
| 1× | -$53,540 | -$69.99 | 0.900 | -0.79 | 31.5% | -$62,766 | **DEAD** · **as run** |
| 2× | -$67,310 | -$87.99 | 0.876 | -1.00 | 31.5% | -$75,582 | **DEAD** |
| 4× | -$94,850 | -$123.99 | 0.831 | -1.41 | 31.5% | -$101,214 | **DEAD** |

**Breakeven at -2.89× friction.** Under 2× — a routine slippage miss erases it.

**Breakeven multiple by year** — the pooled figure can hide a newer era that dies earlier

| Year | 0.5× | 1× | 2× | 4× | Breakeven |
|---|---:|---:|---:|---:|---:|
| 2021 | -$9,387 | -$9,954 | -$11,088 | -$13,356 | -7.78× |
| 2022 | -$14,485 | -$16,600 | -$20,830 | -$29,290 | -2.92× |
| 2023 | -$1,336 | -$3,442 | -$7,654 | -$16,078 | 0.18× |
| 2024 | -$21,447 | -$23,544 | -$27,738 | -$36,126 | -4.61× |

> The ladder subtracts money and nothing else, so it is a **lower bound on the damage** — real added friction also moves fills, so trades appear and disappear. `onyx.lab.costcurve.slip_stress` re-runs the strategy and captures that; this cannot.

**Pooled — all years**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$25,808 | -$27,732 | -$53,540 |
| Total trades | 451 | 314 | 765 |
| Win rate | 31.9% | 30.9% | 31.5% |
| Profit factor | 0.917 | 0.874 | 0.900 |
| Sharpe (ann.) | -0.65 | -1.01 | -0.79 |
| Max drawdown | -$39,124 | -$42,294 | -$62,766 |
| Max run-up | $29,300 | $16,734 | $17,390 |
| Expectancy / trade | -$57.22 | -$88.32 | -$69.99 |
| Avg win | $1,992.00 | $1,992.00 | $1,992.00 |
| Avg loss | -$1,018.42 | -$1,018.23 | -$1,018.34 |
| Payoff (avg W / avg L) | 1.96 | 1.96 | 1.96 |
| Avg R multiple | -0.06 | -0.09 | -0.07 |
| Largest win | $1,992 | $1,992 | $1,992 |
| Largest loss | -$1,028 | -$1,028 | -$1,028 |
| Smallest win | $1,992.00 | $1,992.00 | $1,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 5 / 1 | 5 / 1 | 5 / 1 |
| Win streak avg | 1.45 | 1.37 | 1.42 |
| Avg profit per win run | $2,897.45 | $2,721.46 | $2,823.95 |
| Best win run | $9,960 | $9,960 | $9,960 |
| Loss streak max / min | 11 / 1 | 12 / 1 | 19 / 1 |
| Loss streak avg | 3.07 | 3.01 | 3.06 |
| Avg loss per loss run | -$3,126.56 | -$3,068.83 | -$3,120.54 |
| Worst loss run | -$11,198 | -$12,216 | -$19,342 |
| Avg trade run-up | $1,078 | $1,096 | $1,085 |
| Max trade run-up | $2,020 | $2,010 | $2,020 |
| Avg trade run-down | $819 | $824 | $821 |
| Max trade run-down | $1,010 | $1,010 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2021**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $3,632 | -$13,586 | -$9,954 |
| Total trades | 26 | 37 | 63 |
| Win rate | 38.5% | 21.6% | 28.6% |
| Profit factor | 1.223 | 0.540 | 0.783 |
| Sharpe (ann.) | 1.48 | -4.64 | -1.83 |
| Max drawdown | -$8,188 | -$16,508 | -$17,746 |
| Max run-up | $9,916 | $3,984 | $7,924 |
| Expectancy / trade | $139.69 | -$367.19 | -$158.00 |
| Avg win | $1,992.00 | $1,992.00 | $1,992.00 |
| Avg loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Payoff (avg W / avg L) | 1.96 | 1.96 | 1.96 |
| Avg R multiple | 0.14 | -0.37 | -0.16 |
| Largest win | $1,992 | $1,992 | $1,992 |
| Largest loss | -$1,018 | -$1,018 | -$1,018 |
| Smallest win | $1,992.00 | $1,992.00 | $1,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 3 / 1 | 2 / 1 | 3 / 1 |
| Win streak avg | 1.67 | 1.14 | 1.38 |
| Avg profit per win run | $3,320.00 | $2,276.57 | $2,758.15 |
| Best win run | $5,976 | $3,984 | $5,976 |
| Loss streak max / min | 6 / 1 | 8 / 1 | 8 / 1 |
| Loss streak avg | 2.67 | 3.62 | 3.46 |
| Avg loss per loss run | -$2,714.67 | -$3,690.25 | -$3,523.85 |
| Worst loss run | -$6,108 | -$8,144 | -$8,144 |
| Avg trade run-up | $1,188 | $1,149 | $1,166 |
| Max trade run-up | $2,020 | $2,010 | $2,020 |
| Avg trade run-down | $766 | $879 | $832 |
| Max trade run-down | $1,000 | $1,000 | $1,000 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2022**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$12,142 | -$4,458 | -$16,600 |
| Total trades | 139 | 96 | 235 |
| Win rate | 30.9% | 32.3% | 31.5% |
| Profit factor | 0.876 | 0.933 | 0.899 |
| Sharpe (ann.) | -0.99 | -0.52 | -0.80 |
| Max drawdown | -$22,582 | -$13,498 | -$33,628 |
| Max run-up | $10,572 | $9,642 | $17,390 |
| Expectancy / trade | -$87.35 | -$46.44 | -$70.64 |
| Avg win | $1,992.00 | $1,992.00 | $1,992.00 |
| Avg loss | -$1,018.73 | -$1,018.62 | -$1,018.68 |
| Payoff (avg W / avg L) | 1.96 | 1.96 | 1.96 |
| Avg R multiple | -0.09 | -0.05 | -0.07 |
| Largest win | $1,992 | $1,992 | $1,992 |
| Largest loss | -$1,028 | -$1,028 | -$1,028 |
| Smallest win | $1,992.00 | $1,992.00 | $1,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 4 / 1 | 3 / 1 | 4 / 1 |
| Win streak avg | 1.30 | 1.41 | 1.37 |
| Avg profit per win run | $2,595.64 | $2,806.91 | $2,729.78 |
| Best win run | $7,968 | $5,976 | $7,968 |
| Loss streak max / min | 10 / 1 | 12 / 1 | 19 / 1 |
| Loss streak avg | 2.91 | 2.95 | 2.98 |
| Avg loss per loss run | -$2,963.58 | -$3,009.55 | -$3,037.19 |
| Worst loss run | -$10,190 | -$12,216 | -$19,342 |
| Avg trade run-up | $1,093 | $1,055 | $1,077 |
| Max trade run-up | $2,020 | $2,010 | $2,020 |
| Avg trade run-down | $827 | $846 | $834 |
| Max trade run-down | $1,010 | $1,010 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2023**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | $15,894 | -$19,336 | -$3,442 |
| Total trades | 147 | 87 | 234 |
| Win rate | 37.4% | 26.4% | 33.3% |
| Profit factor | 1.170 | 0.703 | 0.978 |
| Sharpe (ann.) | 1.17 | -2.64 | -0.16 |
| Max drawdown | -$10,180 | -$23,320 | -$15,588 |
| Max run-up | $24,488 | $7,836 | $15,496 |
| Expectancy / trade | $108.12 | -$222.25 | -$14.71 |
| Avg win | $1,992.00 | $1,992.00 | $1,992.00 |
| Avg loss | -$1,018.11 | -$1,018.00 | -$1,018.06 |
| Payoff (avg W / avg L) | 1.96 | 1.96 | 1.96 |
| Avg R multiple | 0.11 | -0.22 | -0.01 |
| Largest win | $1,992 | $1,992 | $1,992 |
| Largest loss | -$1,028 | -$1,018 | -$1,028 |
| Smallest win | $1,992.00 | $1,992.00 | $1,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 5 / 1 | 2 / 1 | 5 / 1 |
| Win streak avg | 1.72 | 1.10 | 1.47 |
| Avg profit per win run | $3,423.75 | $2,181.71 | $2,931.62 |
| Best win run | $9,960 | $3,984 | $9,960 |
| Loss streak max / min | 10 / 1 | 9 / 1 | 9 / 1 |
| Loss streak avg | 2.79 | 3.20 | 2.94 |
| Avg loss per loss run | -$2,838.36 | -$3,257.60 | -$2,996.57 |
| Worst loss run | -$10,180 | -$9,162 | -$9,162 |
| Avg trade run-up | $1,179 | $931 | $1,087 |
| Max trade run-up | $2,010 | $2,010 | $2,010 |
| Avg trade run-down | $774 | $826 | $793 |
| Max trade run-down | $1,010 | $1,000 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

**2024**

| Metric | Long | Short | Combined |
|---|---:|---:|---:|
| Net profit | -$33,192 | $9,648 | -$23,544 |
| Total trades | 139 | 94 | 233 |
| Win rate | 25.9% | 37.2% | 30.5% |
| Profit factor | 0.684 | 1.161 | 0.857 |
| Sharpe (ann.) | -2.86 | 1.11 | -1.16 |
| Max drawdown | -$39,124 | -$13,894 | -$34,850 |
| Max run-up | $6,950 | $14,786 | $12,828 |
| Expectancy / trade | -$238.79 | $102.64 | -$101.05 |
| Avg win | $1,992.00 | $1,992.00 | $1,992.00 |
| Avg loss | -$1,018.49 | -$1,018.17 | -$1,018.37 |
| Payoff (avg W / avg L) | 1.96 | 1.96 | 1.96 |
| Avg R multiple | -0.24 | 0.10 | -0.10 |
| Largest win | $1,992 | $1,992 | $1,992 |
| Largest loss | -$1,028 | -$1,028 | -$1,028 |
| Smallest win | $1,992.00 | $1,992.00 | $1,992.00 |
| Smallest loss | -$1,018.00 | -$1,018.00 | -$1,018.00 |
| Win streak max / min | 3 / 1 | 5 / 1 | 4 / 1 |
| Win streak avg | 1.24 | 1.59 | 1.37 |
| Avg profit per win run | $2,472.83 | $3,169.09 | $2,719.85 |
| Best win run | $5,976 | $9,960 | $7,968 |
| Loss streak max / min | 11 / 1 | 7 / 1 | 9 / 1 |
| Loss streak avg | 3.43 | 2.68 | 3.12 |
| Avg loss per loss run | -$3,496.80 | -$2,730.55 | -$3,172.62 |
| Worst loss run | -$11,198 | -$7,126 | -$9,172 |
| Avg trade run-up | $934 | $1,270 | $1,070 |
| Max trade run-up | $2,010 | $2,010 | $2,010 |
| Avg trade run-down | $868 | $778 | $832 |
| Max trade run-down | $1,010 | $1,010 | $1,010 |
| Avg contracts | 2.00 | 2.00 | 2.00 |
| Max / min contracts | 2 / 2 | 2 / 2 | 2 / 2 |

> Cost ladder basis: $9 round-turn per contract.
wrote /Users/ramoscapital/ramos-quant-homebase/research/prop-portfolio/2026-10-02-bimb930/out_inv_imb_1to2/metrics_imb_inv.json

