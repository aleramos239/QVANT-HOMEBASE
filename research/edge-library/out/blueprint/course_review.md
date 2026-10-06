# The Institutional Protocol, read in full against the blueprint — 2026-10-05

Read: all 12 transcripts (48,418 words), the templates, the instructor's notes on every code template, the 6 PDFs and the two
Colab notebooks (opened read-only). Five readers, one per group of lessons; every row has its file and line. The rows marked ✔ were
re-read by me in the transcript. Nothing here is in `BLUEPRINT.md` yet: these are proposals for the owner to pick from.
Course folder: `~/Library/Mobile Documents/com~apple~CloudDocs/Institutional Protocol/` (L03 = `transcripts/L03.txt`, and so on).

## A. Worth adding (ranked)

| # | Add | What the course says | Where | Why it helps |
|---|---|---|---|---|
| 1 | **Check the code before any number counts** — a step between the idea card and the build | Behaviour is signed off first, profit comes after. Plot each rule, write what you expect to see, then check the trade list: entry and exit times, one trade a day, no weekend hold, winners near the target in dollars. His own first runs were wrong on all of these | L07:5-7, 110-113, 213-219, 261-281, 424-440 · L06:149-186 · LE01:199-262 | The blueprint guards against luck, not against a wrong test. A mis-coded idea is shelved for good because a fast "no" is trusted |
| 2 | **Base case first** — the entry with a plain time exit, before stops and targets | Prove the entry alone with a throw-away time exit, then add the real exits. First question for a paper idea: does the logic give a positive drift | L07:167-181, 413-415 · LE01:232-237 · note 08 line 1 | On the stored tables the money often came from the exits, not the entry |
| 3 | **Eval in two stages** — first days at 1 micro, then the simulator's size | First days one micro only, to confirm order timing, fills, entries and exits. Then scale. 3 micros passed 0.7 % of the time, 17 passed 48 % | L10:539-547 ✔, 722-732 ✔ | The draft says "smallest size, one step per 40 trades". A tiny size cannot pass an eval |
| 4 | **The course's stated drawdown rule: cut risk at the 75th percentile, pause at the 95th** | "Two rules": hard stop at the 95th percentile of the Monte Carlo drawdown, read after 10 / 20 / 30 / 40 trades. Lesson 9 walks through 50 / 90 / 99 as yardsticks | L03:335-341 ✔, 357-362 ✔ · L09:526-547 ✔ | The draft uses the looser pair (90-95 / 99) and calls it the course's table |
| 5 | **A break pauses, it does not delete** — with a review | Pausing is not deleting. Soft review when the last 5 months run well below the long-run pace: is it in history, can I explain it, is it normal | L03:363-381 ✔ | The draft only has "retire" |
| 6 | **Before an eval is bought: the payout phase too, on a "live is worse" row** | Eval and funded are separate tests. His example passed the eval 48 % and qualified for a payout 14 %: not usable. Five fixed worse-than-backtest cases (win rate -3 to -8 points, winners -10 to -30 %) | L10:668-670, 813-857, 909-919 · notebook cells 2, 8, 14 | A pass alone can be worth nothing. The draft lets the live average fall to half of history, so the odds should be read there |
| 7 | **Attempts and fee budget written down before the first eval** | A failed attempt is bought again unchanged: 48 → 73 → 86 → 93 % over four tries. At the best size 37-44 % of runs bust | L10:715, 765-773 · notebook cells 7, 11 | Says in advance that one bust inside the drawdown table is not a reason to retire |
| 8 | **Long and short shown separately** | The short side erased about 35 % of the long side's profit: revise or remove it | L08:117-125 ✔ · L09:446-450 | Finds a dead side while tuning is still allowed. Dropping a side counts as a round |
| 9 | **Three more lines on the idea card: when it should lose · the data it needs and its grade · its family (trend or reversion)** | The overnight long must lose through 2022; a version without that loss is a red flag. Volume can be tick count, delta from bar shape is a proxy. Each family has its usual way of losing | LE01:304-308 · indicator notes 01, 08 · L02:5-25 | Each line is one more way for the idea to be wrong before a run |
| 10 | **Freeze list: every indicator's window and warm-up, order types, time zone, what a "day" is** | An average counted from the chart's first day changes with how much history is loaded. Code assumed Eastern time on Chicago data. Label 9:00 traded at 9:30 | note 11 lines 9-15, 34-48 · LE01:170-172, 208-222 · L06:163-186 | The unseen test is read once. A cold or start-dependent indicator would change the 2025-26 trades and cannot be fixed without a second look |
| 11 | **Live must equal the test** | Same symbol, session and contract settings as the test; the first live level must equal the full-history value; after any code change the trade list must be reproduced exactly | note 12 lines 43-61 · L10:140-161 | Slip and drawdown lines only mean something if the live strategy is the tested one |
| 12 | **A filter must win alone; a combination must beat both parts** | Trend filter alone $115 against a $104 base: kept. Sentiment $93, VIX worse: dropped. Two-of-three $135: still rejected, because two members fail alone | LE01:263-301 · script 15 (range breakout) 32-36 | The draft says "beats the same table without it"; this adds "alone, against the plain base" |

## B. Show on the card, not a gate

| Item | Where | Note |
|---|---|---|
| Each build year on its own, and the best year's share of the profit | script 15 (overnight) 28-37 | Per-year gate did not help on the stored tables (44 %); worth re-testing now that the build is four years |
| Average trade in dollars and in R (1R = the stop) | L09:323-332 | Makes strategies with different stops comparable |
| Build next to unseen: average trade, win rate, drawdown, the two confidence ranges | L09:271-290, 472-491 | The course's main overfitting read |
| Unseen P(EV<0): under 10 % is his least, under 5 % reassuring | L09:495-499, 621-633, 675 | He turned a strategy down at 21.7 % though its average trade matched. The draft uses "beats 95 % of random tables" instead, which is stricter |
| Win rate next to the break-even win rate of its stop and target | L08:126-137 ✔ | |
| Longest losing streak at the 50th and 95th percentile | L01:38-43 | |
| Average trade by volatility third | glossary p.18 | Flags profit that sits in one kind of market |
| Trend-or-reversion check for the market (buy after an up minute, hold one bar) | note 13 lines 6-27 | By his own word not a scientific test: information only |

## C. Where the blueprint is already stricter (keep ours)

| Item | The course | The blueprint |
|---|---|---|
| Cost floor | On a backtest WITHOUT commission or slippage (L08:115-117 ✔, 144-148 ✔) | After costs — and that is how it was tested on the stored tables (66 % and 71 %) |
| Unseen pass line | A reading by eye, plus P(EV<0) under 10 % | Each year profitable, beats 95 % of random tables, cost floor, worse fills |
| Tries | No limit; "iterate" (L09:194-213; L06:283-299) | 5 counted rounds with a rising bar |
| Picking a setting | Takes the top row in the lesson (L09:143-145) | The middle survivor, never the best |
| Costs | Added after the first read (LE01:233, 297) | From the first run |
| Monte Carlo for sizing | Draws single trades (notebook step 12) | Draws whole days, so losing streaks stay together |

## D. Two places where the course asks for more than we have

| Item | The course | Us |
|---|---|---|
| Years to build on | At least 5, 10+ for regime-dependent ideas; "when in doubt add 5 more" (L08:17-26, 238-241). He built on 5 years and tested on 15 more months | 39 months build, 21 unseen. Older data is parked |
| Trades | 200 for a strategy trading about once a day (ORB validation sheet, PDF p.7) | 100. Test 200 on the stored tables before changing |

## E. Do not copy

- Choosing filters and settings on all years up to today (LE01:163-166, 263-288; L10:858-913). Nothing is left unseen.
- Debugging on the newest data (L06:28-31). It would spend 2025-26.
- Re-optimizing a live strategy after a one-month lock (L03:283-285).
- Building to the pass shape — target between half the stop and the stop, 60 % wins (L10:583-603). His own example built that way failed the payout test; it is also the old pilot's flaw.
- The reshuffle Monte Carlo as a pass test (L03:149-179; L08:194-195). Reshuffling keeps the total, so "share of runs that lose" cannot fail.
- More ratio gates: profit factor above 1.2, return over drawdown above 3 (ORB sheet). Sharpe did not help on the stored tables.
- Template exits: target tested before the stop in the same bar, no end-of-day exit (L07 templates). Keep pessimistic fills and flat by 4pm.

## F. Small operational lines for the eval card
Account and contract month checked each time · roll date · flat on both sides before arming · manual flatten tested · what protects an
open position if the desk drops · order types the same as the tester assumes · stop and target in points do not move when size changes
(L10:65-124, 162-189, 198-215, 303-309, 492-504).
