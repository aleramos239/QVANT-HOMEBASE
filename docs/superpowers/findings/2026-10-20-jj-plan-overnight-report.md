# The $1,000 plan: overnight report (2026-10-20, checked in the morning)

**You asked:** hit 40 % at 1:1.5 with JJ's trade count, keep improving, try VWAP, have it ready when you wake up.

## The answer first
1. **40 % at 1:1.5 with JJ's trade count does not hold out of sample on NQ.** About 185 versions now. The many-trades-a-day versions are break-even after costs. VWAP alone looked good in-sample (42 %) and **failed the 3:1 walk-forward**. VWAP pullbacks together with the 09:45 bar (after a bug fix) come closest: 42 % at 1:1.5, 2.4 trades a day, a near-pass (below).
2. **Nothing from tonight is a clean out-of-sample pass that you can book today.** The 13:30 first bar passed the four walk-forward lines, but only just: one extra tick of slippage breaks it, and its profit is mostly the afternoon's usual upward drift.
3. **The strongest rule on file is still your FVG rule** (the newest 15-minute FVG on the side of the 09:30 open, 3 x 1-minute ATR stop, 1:0.75 or 1:1). It passes all four walk-forward lines, and its blind months (July 2025 on) made money: **+$7,195 on 100 trades**. On the account, using its out-of-sample trades: **about +$130-160 an eval at 1 micro** on Flex. Its limit entry cannot be booked on the Desk yet.
4. **Size small.** On every rule, 1 micro (about $50-100 risk a trade) beats 2-3 micros out of sample. The $500 a trade from the coin-flip sizing does not apply to these rules: their edge is small compared with their swings.

## The numbers
Out of sample = the 3:1 walk-forward's own trades. Monte Carlo on Lucid Flex 25K at $45, first cheque only, x 0.9 split. "Edge removed" = the same trades with their average profit taken out.

| Rule | Trades a day | Walk-forward lines | Blind months (Jul 2025 on) | Net an eval, out of sample | Edge removed |
|---|---|---|---|---|---|
| **FVG 1:1** | 1.75 | 4 of 4 | +$6,574 (99 tr) | **+$158** (1 micro) | +$3 |
| FVG 1:0.75 | 1.75 | 4 of 4 | +$7,195 (100 tr) | +$134 (1 micro) | $0 |
| 09:45 + 13:45 first bars | 2.0 | -- | both lose | +$130 (1 micro) | -$2 |
| 09:45 continuation (JJ's exits) | 1.0 | 2 of 4 (fail) | -$726 (34 tr) | +$121 (1 micro) | +$1 |
| 13:30 first bar, 30 / 30 | 1.0 | 4 of 4, thin | -$2,080 (60 tr) | +$76 (2 micros) | -$3 |
| **VWAP pullback + 09:45 bar, 1:1.5 (bug fixed)** | 2.4 | 3 of 4 (win-rate line missed by 0.3 pts) | +$12,208 (93 tr) | +$114 (1 micro) | -$6 |
| VWAP pullback 25 / 38 alone | 1.4 | 0 of 4 | -$3,884 (16 tr) | -- | -- |
| VWAP pullback 50 / 76 | 1.0 | 1 of 4 | -$5,372 (43 tr) | -- | -- |
| JJ's fade as taught | 1-4 | -- | -- | loses | -- |

- The edge-removed column is about $0 for every rule. So whatever a rule makes on the account comes from its own edge, not from the account's shape.
- Pro 25K ($65) comes out about $40-45 an eval below Flex at these small sizes.
- Last night's in-sample account figures (+$440 / +$531 an eval) were build days only, and the review showed they were flattered (below).

## What the checks found (13 checkers, 3 per claim; every number re-ran exactly)
| Last night's claim | What the checks found |
|---|---|
| The 13:30 first bar holds out of sample | Passes 4 lines, but 185 of its 245 trades are build months. +1 tick of slippage, or the blocks moved 2 months, breaks it. Just buying at 13:45 every day made $29 a trade against its $40. |
| VWAP is dead | Still dead. But the VWAP + 09:45 test had a **code bug**: its pullbacks used a 3-point stop instead of 25. Fixed with a test; re-running now (below). |
| FVG at $150 risk = +$440 an eval | $150 was the luckiest of ~21 sizes. Averaged over sizes: about +$220. The money came from two stretches (early 2022, spring 2025). |
| Two first bars at 1 micro = +$531 an eval | All payouts came from accounts started in 2024. Earlier starts lose. Also, the "50-point stop meets the floor" reason was wrong: accounts bust on losing streaks. |

One honesty note: to check the claims, the checkers also looked at every unseen day for the 13:30 bar and the VWAP cells. That was a single look, not the house out-of-sample test (the walk-forward is). Those months are no longer blind for those rules.

## What I learned (plain)
- **Filters and bands don't make an edge.** 19 VWAP-band versions: the wider the band, the closer to 40 % and $0.
- **Only some first bars carry money, each in its own shape.** 13:30 works in-sample at 30 / 30. 09:30 works only with JJ's exits (25 / 38 on a small body, 50 / 76 on a big one, held to the close); at 30 / 30 it loses. 03:00 loses and 11:00 is break-even, both out of sample too.
- **No add-ons helped:** a day box (stop at +$100 / +$200, cut at -$300), a 2-bar time stop on the FVG rule. Keep it simple.
- **Library scan** (every stored strategy through 50 accounts): nothing new. The top fits are look-ahead runs (Asia sweep) or the old NY opening-range breaks, whose unseen read already failed.

## VWAP after the bug fix (done this morning)
- **VWAP pullbacks (25-point stop) + the 09:45 bar, 1:1.5:** 42 % win at 2.4 trades a day, +$34 a trade on build days. The walk-forward passes 3 of 4 lines and misses the win-rate line by 0.3 points. Its blind months made +$12,208 on 93 trades. This is the closest thing to your ask (40 %+ at 1:1.5, more than one trade a day), but it is not a pass.
- Inside it, the 09:45 bar still carries most of the money. The VWAP pullbacks are small but positive everywhere: +$14 a trade on build days, +$36 on the walk-forward, +$69 on blind months. None of that is clearly above zero yet.
- The 50 / 76 VWAP version fails (blind months -$5,372). Dead.
- **More trades a day = back to break-even (12:30 check).** I sent the two busiest screened versions that still showed 40 %+ at 1:1.5 through the walk-forward:

| Version (with the 09:45 bar) | Trades a day | Build days, a trade | Walk-forward, a trade | Result |
|---|---|---|---|---|
| VWAP pullback, exact touch | 2.4 | +$34 | +$42 | near-pass (above) |
| VWAP pullback, 10-point band | 3.1 | +$23 | +$16 | fails 2 lines |
| Momentum away from the open, big bodies | 5.1 | +$12 | +$4 | fails 2 lines |

  Neither busier version traded a single blind month. The most you can get at 1:1.5 and still keep an edge is about 2-3 trades a day, not JJ's 10.
- **Two rules on one account** (FVG + VWAP / 09:45): about the same money per eval as FVG alone (+$154 vs +$158 on Flex, 1 micro), but the pass comes faster: a median 37 trading days instead of 54.

## What I suggest (your call)
1. **Drop "40 % at 1:1.5" as the goal.** Keep the plan's money test. The FVG rule is the strongest: it passed all four lines, and its blind months made money. Second is VWAP + 09:45 (a near-pass; market orders, which the Desk can book).
2. **To trade the FVG rule, the Desk needs a limit-order entry for Lab strategies** (today it is shadow only). That is a build job; say the word and I will scope it.
3. **Do not buy evals yet.** Out of sample the best is about +$150 an eval at 1 micro, roughly a 6 in 10 pass chance, counting only the first payout. Small, and it rests on about 100 blind trades.
4. **Still open from yesterday:** the take-turns rotation is on main. The Desk was restarted at 21:09 ET by the other session. The paper try waits for your pick of a strategy, and none from tonight is a clear candidate.

Files: sheets in `research/edge-library/taught/`; the 50-account tool `taught/jj_fifty_accounts.py` (new: `--wf` walk-forward trades, `--mc` Monte Carlo, `--no-edge` control, `--set-risk`, `--day-take / --day-stop`, several stores on one account, and a fix so it reads big stores in seconds instead of hours); the jj_fair stop fix + test (`engine/families/jj_fair.py`, `engine/tests/test_jj_fair.py`). Vault: `2026-10-19-jj-fair-price-111-versions...` (batches 7-9, the out-of-sample account read) and `2026-10-19-1000-plan-sizing...` (sections 7-8). Nothing is committed.
