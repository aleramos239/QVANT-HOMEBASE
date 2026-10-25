# JJ Simon: everything in one place (2026-10-20)

The owner's goal: copy JJ Simon's NQ "fair price" strategy and his $1,000 prop plan, test it honestly, follow it if it works.

## 1. Start here
- **[RULEBOOK.md](RULEBOOK.md)**: the whole strategy and every rule, merged from all the videos.
- **The answer so far:** his fade back to the fair price has no edge on NQ. His 40 % at 1:1.5 with many trades a day does not hold
  out of sample. The best rule found while testing is your own FVG rule, but it is not approved and not yet tradeable (below).
- **The latest report:** [`docs/superpowers/findings/2026-10-20-jj-plan-overnight-report.md`](../../../docs/superpowers/findings/2026-10-20-jj-plan-overnight-report.md).

## 2. The videos (notes in `videos/`)
| # | Video | What it is |
|---|---|---|
| 1 | [BLvsYJ4sqn8](videos/BLvsYJ4sqn8.md) | The 6 PM / 8 PM evening fair-price setup |
| 2 | [l6iq0ljhxIo](videos/l6iq0ljhxIo.md) | A bad week on prop firms (week 13) |
| 3 | [DEkzU8gqX-o](videos/DEkzU8gqX-o.md) | Why it works and the entries ($1.8M) |
| 4 | [2BtwoTCxcbc](videos/2BtwoTCxcbc.md) | "Your strategy doesn't matter on prop firms": the sizing math |
| 5 | [HlWSP7ajgpQ](videos/HlWSP7ajgpQ.md) | A live week of trades (Ep. 12) |
| 6 | [0uAQUHEB_L8](videos/0uAQUHEB_L8.md) | $30,000 a month: stacking accounts |
| 7 | [KN7j6NXXAio](videos/KN7j6NXXAio.md) | The main strategy, 80 trades shown |
| 8 | [KHEQ5g55dQ4](videos/KHEQ5g55dQ4.md) | Chart Fanatics interview: the 1-minute strategy (re-checked with frames) |
| 9 | [4Zj4xKiQHQk](videos/4Zj4xKiQHQk.md) | Start over with $1,000: the 50-account test, Lucid Flex 25K |
| 10 | [UVKVSWKFlvo](videos/UVKVSWKFlvo.md) | "My $1.3M strategy in 10 minutes" (NY morning) |
| 11 | [aCOgfvL6lK8](videos/aCOgfvL6lK8.md) | Titans Of Tomorrow interview (JJ as the guest) |

## 3. What was tested and what came out
| Test | Result |
|---|---|
| His fade as taught (`owner_jj_fair_nyam_25_38`) | 36.8 % win, -$44 a trade, worse than random. 50 Lucid accounts lose. |
| 180 versions (`taught/jj_screen.py`, batches 2-7) | The fade is the 38 % base rate. Trading the same candle the other way is break-even. |
| VWAP pullback (your idea) | 42 % in-sample. It fails the 3:1 walk-forward alone. With the 09:45 bar it nearly passes (it misses one line by 0.3 points). |
| First 15-minute bar of a session | 13:30 passes the walk-forward, but thinly (mostly afternoon drift). 09:30 works only with JJ's exits. 03:00 and 11:00 do not. |
| Your FVG rule on the side of the 09:30 open (`owner_fvg_oside_15_a1m3_nl_r075 / _r1`) | Passes all 4 walk-forward lines, and its blind months made money. About +$130-160 an eval at 1 micro. Not approved. |
| The $1,000 plan sizing | 1 micro beats bigger sizes out of sample. Pro beats Flex in-sample. Kelly says 2-5 evals at a time. |

Full detail: vault findings
`50-Permanent/Findings/2026-10-19-jj-fair-price-reversion-fails-50-account-lucid-flex-25k-test.md`,
`2026-10-19-jj-fair-price-111-versions-fade-is-base-rate-momentum-break-even.md` (batches 1-9, the out-of-sample account read),
`2026-10-19-1000-plan-sizing-kelly-flex-vs-pro-coin-flip-geometry.md` (sections 1-8).
Project hub: `30-Projects/Onyx-Trading/jj-simon-fair-price-video-series-2026-10-19.md`.

## 4. Where the working files are (left in place: the tools look for them there)
- Family (the rule in code): `../engine/families/jj_fair.py`, tests `../engine/tests/test_jj_fair.py`.
- Taught sheets (`../taught/`): `owner_jj_*`, `owner_vwap_*`, `owner_mom_body1_c15`, `owner_*_first_bar_15`,
  `owner_fvg_oside_15_a1m3_nl_*`. Their stores and walk-forwards: `~/.homebase/taught/<name>/`.
- Tools (`../taught/`):
  - `jj_screen.py`: a fast screen of many versions.
  - `jj_fifty_accounts.py`: 50 Lucid accounts, with `--wf` (walk-forward trades), `--mc` (Monte Carlo), `--no-edge`, `--set-risk`,
    `--day-take/--day-stop`, and several rules on one account.
  - `jj_plan_speed.py`: risk and speed for a coin flip.
  - `plan_scan.py`: every stored strategy through the plan.
- Prop rule files: `homebase/backtest/propsim/rules/lucid-flex-25k-dll@2026-10-19.json`, `lucid-pro-25k@2026-10-19.json` (not confirmed).

## 5. Built for the plan on the Desk
- Take turns, one account a trade (your rotation rule): on main since 2026-10-19, off by default.
- Limit-order entry for Lab strategies (needed for the FVG rule): built on branch `feat/desk-lab-limit-entry`, paper accounts only.
  Not merged. Design: `docs/superpowers/specs/2026-10-20-desk-lab-limit-entry-design.md` on that branch.

## 6. Status
Nothing from JJ's material is approved. The pipeline book was emptied on 2026-10-20 (the owner: "restart"). Do not buy evals yet.
