# JJ Simon "fair price" strategy: the full rulebook (merged, 2026-10-19)
Sources: BLvsYJ4sqn8 (6 PM / 8 PM), l6iq0ljhxIo (week 13, all sessions), UVKVSWKFlvo (NY AM), DEkzU8gqX-o (why it works + entries), 2BtwoTCxcbc (prop sizing math), HlWSP7ajgpQ (live week), 0uAQUHEB_L8 ($30k/month stack), KN7j6NXXAio (main strategy, 80 trades), KHEQ5g55dQ4 (Chart Fanatics interview + live days), 4Zj4xKiQHQk (start with $1,000). Per-video notes and every example are in those files.

## The idea
- Every session open has a fair price.
- At the open, a rush of orders pushes price too far (the unfair move). Trade WITH it = continuation.
- When the push ends, price comes back to fair. Trade BACK = reversion.

## Chart
- NQ, 1-minute. Optional 5s / 15s to see where a news move ends.
- VWAP: on his chart but not traded. In DEkzU8gqX-o he says VWAP is "a pretty good estimate" of fair price and trading in its direction would work on a prop firm, but he doesn't use it because it ignores news.

## Sessions and fair price
| Session (NY) | Fair price line |
|---|---|
| 18:00 | the 18:00 open |
| 20:00 Asia | 18:00 or 20:00 open (see "Which line is fair") |
| 08:30 news | price just before the news |
| 09:30 | last price before 09:30 (= the open) |
| 14:00 FOMC / news | price just before the news |
| 14:00 normal | only if accounts are left |
Hours: evening 18:00-21:30, morning 09:30-11:00. After that: only with the trend (break of structure), or stop.

## Definitions
- Swing high: a candle whose high is above the candle on each side. Swing low: flipped.
- Break of structure: a candle CLOSES past the last swing.
- Displacement: an opposite-color candle (green after a red, for a buy): body bigger than the red's body AND close above the red's wick (touching is not enough). Two candles together can count but weak; three no.
- Gap: 16:59 close vs 18:00 open. Price wants to fill it.
- Bias (evening): where that morning's 09:30 open is. Above = buy, below = sell.
- Too close: less than 30 pts from the fair line.

## Trade 1: continuation (one per open)
1. First 1-minute candle: green buy, red sell. Enter at once.
2. Window: 18:00 first 5 min; 09:30 first 10-15 min.
3. Weak first candle (wicks both ways, barely breaks): enter on the 2nd candle.
4. Skip if: away from an unfilled gap; against the bias; a wick rejects that side; the candle fails to break structure.
5. News: continuation only if the news candle is huge.
6. Adding: one more per candle until the push stops.

## Trade 2: reversion (back to fair)
1. Price moves away; must be 30+ pts from the line.
2. Wait for a displacement or a break of structure back toward the line.
3. A swing nearby: wait for the break (displacement alone is weak).
4. Never buy the first green candle in a downtrend (or sell the first red in an uptrend).
5. Lost: try again on the next signal (2nd / 3rd try OK).
6. Adding: only while the first is in profit; never while losing; never at the same price as the first entry.

## Why (DEkzU8gqX-o)
- Bias toward fair = small steady edge. With a bias any entry has ~the same edge, so target / stop are set by the account's rules (pass rate on evals, expected value on funded). Entries add ~0.1%. Many trades a day.
- 80 / 20 rule: at least 80% of the target on the near side of the fair line (30 room for 38 is this rule).
- In a long bias he adds on every green candle.
- Why a fixed target: on an eval the drawdown TRAILS, so a $300, $1,000 or $1,500 target each has a different pass rate under -$2,000 / +$3,000. Pick the one with the best pass rate and repeat it. Shown: a 1:1 box (52 / 52) and a 2:1 box on the same move: the account decides, not the chart.
- Break-even on a prop firm = ~3x on eval fees (his claim).

## Stop and target (fixed points, never at a swing or candle; target is NOT the line)
| First candle body | Stop | Target |
|---|---|---|
| under 25 pts | 25 | 38 |
| over 25 pts | 50 | 76 |
Reversions 25 / 38 (needs 30+ room) in the videos; for real he sets target / stop per account (e.g. 50 / 25), changing with firm, eval vs funded, and balance. Small accounts may take closer trades for 10-26 pts with smaller stops (12.5).

## Breakeven and exits
- The push doesn't come: stop to breakeven (by eye).
- An 18:00 trade open just before 20:00: get out (breakeven or market).
- 08:30 news trade: breakeven before 09:30.
- Trades before 09:30 allowed; holding through the open only if very sure of its direction (he checks the book imbalance).

## Which line is fair
Evening:
| First 20:00 move | Fair line |
|---|---|
| toward 18:00 | 18:00 stays |
| no move | 18:00 stays |
| away from 18:00 + breaks structure | 20:00 open (delete 18:00) |
| sits on the open | unclear, skip |
- Price moves away, breaks structure, then sits: move the line to that consolidation.
- Price keeps ignoring the line: the line is wrong, move it. Don't keep fading to it (his own mistake).
- 18:00 not fair (~2%): after big news, a far 18:00 open (207 pts after FOMC) opened unfairly (too little volume 17:00-18:00 to gap that far): keep trading toward the pre-news price.
- Back to an older line (by feel): big break + gap + bias agree -> trade back to the previous session's fair price.
- News: the pre-news price is fair; reversions to it are his strongest trade.

## A+ trade
- The 20:00 candle points back toward the 18:00 line (continuation + reversion at once). Same for any open pushing back to the old fair line. Size up, add.

## Entering
- Funded: at candle close. Evals: mid-candle OK; next eval when the previous is halfway to target.

## No trade
- Price never 20-30 pts from the line (common before FOMC). ~15% of days never come back: take the loss.
- Holiday (NY): only if the 09:30 candle shows a volume burst; smaller target.

## 18:00 vs 09:30
| | 18:00 | 09:30 |
|---|---|---|
| Fair | 18:00 open | last price before 09:30 |
| How sure | very (~98%) | less: pre-news or overnight price may be the real fair |
| Continuation window | 5 min | 10-15 min |
| Second open | 20:00 Asia decides | none, but 08:30 news before |
| Gap rule | yes | no |
| Bias | that morning's 09:30 open | overnight fair prices (18:00, Asia, pre-news) |
| Stop time | 21:30 | 11:00 |
| Volume | low, many too-close days | high, 50 / 76 more often |
| Pre-open | exit 18:00 trade before 20:00 | trades allowed, may hold through |
| News | rare (FOMC carries to 18:00) | 08:30 common |

## From the Chart Fanatics interview (KHEQ5g55dQ4)
- 3 losing reversions in a row in one session = stop for that session (the fair price is somewhere you don't know).
- Target first, stop second ("essentially random"); never a stop under 25 pts in New York. Targets in 25-pt steps (25-200); between two, take the lower.
- Evals take displacement entries (38 / 25); funded take break-of-structure entries with targets near the full distance (80% rule). Too many funded already open the same way -> send evals.
- Copy-trade only the strongest: the first break of structure after expected news.
- 09:30 is not a target after 11:00, only a bias. 14:00: if it opens toward the 09:30 price, continuation + reversion back to 09:30 at ~1:4.
- Continuation filter: bias = the opposite of the last 6-12 hours; the first candle must break the candles before it; he also reads the first second's color.
- Fair can be the pre-open consolidation (open ran straight to it) or the 09:24-09:25 ET pre-open volume-spike candle.
- Two same-color candles together count as a displacement when one huge candle is hard to displace.
- Unexpected news drift: enter with the jump, widest stop (under the last consolidation), no target, exit on a break against; add on the break of the pause; later revert to the new consolidation.
- After a loss, the next trade on that account aims bigger; past 11:00 only if most accounts aren't done.
- His own live money: only reversions, only breaks of structure, mostly expected-news reversions, chart-based targets.

## From the main strategy video (KN7j6NXXAio) - these win over older notes
- New York is the best session. Continuation 09:30-09:35 only; reversions 09:35-11:00; hard stop at 11:00.
- Setup grades: A+ = break of structure, A = displacement, B = never.
- Displacement, zero-discretion version: body bigger than the previous body. Close past the previous wick = preferred, not required. No-body candles that went "all four directions" don't count.
- Break of structure needs a CLOSE (no wick, no limit orders: "no more limits").
- Layer only on a break of structure in your favor while the first trade is ~halfway-75% to target.
- Breakeven only when the opening continuation stalls AND breaks structure against you; then flip.
- Expected news (red folder) = priced in, fair = pre-news. Unexpected news (a tweet) = new fair at the next consolidation; on a tweet, one eval WITH the move.
- Pick the account by the points available back to fair.
- His accounts rule: one account at a time, one trade per account per day; copy two at most, not until ~$20k a month.
- His 80-trade replay: 46 W 34 L (57.5%) at 1.5R; elsewhere he says ~41% is realistic.

## From the $30k/month video (0uAQUHEB_L8)
- Sessions: works for every open, London included (09:30, 08:30 news, 14:00, 18:00, 20:00 Asia, London).
- Continuation needs a break of structure: a choppy open with no break = no continuation until the first break. Add one more at the next candle close while it runs.
- Always 1.5R but the size scales: 12.5 / 19 on a quiet day (~19 pts of room), 25 / 38 normal, 50 / 75 (fewer contracts) when the first candle is over 25 pts.
- Speed beats win rate (his slide: 1% edge x 10 trades a day = 32% pass in ~34 days; 5% edge x 1 a day = 58% pass in ~200 days).
- Backtest as a prop account: $50k, -$2k trailing = gone, count how often +$3k comes first.
- Stack: 200 evals -> 33% pass -> 66 funded -> 33% reach +$3k -> 22 -> three payout cycles (half each time, 5 winning days of $150) = $57.75k gross. Max 5 funded per firm -> 5-8 firms.
- Lower funded risk as the balance grows (same EV, less variance).
- "Don't put every account at risk at the same time." (matches the owner's rotation rule)
- Few accounts: only the stronger setups. Many accounts: every biased signal.

## From his live week (HlWSP7ajgpQ)
- Overnight trades: after the evening session, send accounts with the bias on a trend switch, resting stop + target (OCO). Targets = older fair prices in a ladder (Asia open -> 6 PM open -> last night's consolidation). "Slightly above 50/50."
- 09:25 ET volume spike: read its direction, enter early, hold through the open or go breakeven.
- Funded big trade may aim at the fair LEVEL with a wide stop (3 NQ: +$4,485 / -$5,025 to the consolidation). Evals take the small close trades; funded waits for far ones.
- Choppy day: signals come too late, use LIMIT orders toward fair.
- No entries on a news candle, unless price is so close to fair that waiting leaves no room.
- Bias line: "any time it's above this line, just short" (and the mirror).
- Layer when it reverts (lose ~3 on a failed day, win 6-7 when it works). Chop (red after every green) hurts.
- In one huge move he copy-trades (17 + 22 accounts) because he can't place them one by one fast enough.
- After the session: wait for a trend and quiet volume, then trade with the trend for extra eval trades.

## Sizing and prop math (2BtwoTCxcbc)
- His real stats: 41% win at 1.5R, ~10 trades a day. Break-even at 1.5R = 40%; after costs ~40% = break-even live.
- His claim: right sizing turns break-even into profit on a prop firm. Zero edge sized right = 9.3% payout chance vs 5.0% needed (+$85 per $100 attempt); sized the obvious way = 5.1% ($11 a year).
- Size each stage for its goal: eval = chance of +$3k before -$2k; funded = payout chance x payout size; near payout, after payout, live all differ. Firm and balance change it too.
- Don't copy the same trades to every account: same EV, far more risk (10 copied: 16.5% losing years, bad year -$8k; independent: ~0%, bad year +$27k).
- Real edge: higher risk = faster, more per year (3% risk: 4.5 days per attempt, $9.8k/yr); lower risk = more EV per attempt but slow (0.3%: $787 per attempt, 204 days, $965/yr).
- Sizing depends on three inputs only: edge (measured over 500+ trades, after costs), frequency, fees.
- Exact risk numbers: he won't share them.
- For us: ~40% at 1.5R would fail our pipeline gate (needs 43%) and not get the Live tag.

## Owner's rule: account rotation (2026-10-19, an option, NOT the default)
- Same strategy, one trade per account, then the next account: trade 1 -> A, trade 2 -> B, trade 3 -> C ... after the last account, back to A.
- JJ says the same in KN7j6NXXAio: "one account at a time and one trade per account per day. That is the optimal way."
- Why: a bad move costs each account one stop instead of blowing one; one trade per account per day keeps daily loss limits far away; accounts see different moments so they don't all win or lose together (JJ's copy-trading slide: same average, far fewer losing years).
- It cuts risk, not adds edge: total profit is the same.
- Watch: slower per account (10 trades a day over 10 accounts = 1 a day each; 50 accounts = 1 every 5 days); more eval fees up front; firm caps on funded accounts and inactivity / minimum-day rules; a "no reversion" day still loses on every account that gets a turn.
- Rough size: about as many accounts as trades a day.

## Starting with $1,000 (4Zj4xKiQHQk)
1. Buy nothing yet: prove the plan in replay on 50 complete accounts (not 50 trades), with the firm's exact rules (trailing drawdown, consistency, payout limits).
2. Judge only payouts after split minus all eval costs; unpaid balances don't count. Track pass rate, payout rate, average payout per funded.
3. Not profitable: change the risk-to-reward first (eval and funded separately), then the strategy; re-test 50.
4. $1,000 -> 20 Lucid Flex 25K evals at $50 with the daily loss limit ON. His stats there: 37% pass, 35% payout, 4.2x ROI.
5. Trade exactly what you tested; size under the daily loss limit and remaining drawdown.
6. Request payouts the moment you can; build the bankroll from payouts.
7. Scale: $3,000 -> 50K accounts, $15,000 -> 150K accounts; re-simulate each firm's plan first.
- Risk of ruin = (1 - pass x payout) ^ evals you can buy; smaller payout targets = higher payout chance = lower ruin.
- Plan shapes: 25K $1,250 / $1,000, 50K $3,000 / $2,000, 150K $9,000 / $4,500 -> the best risk-to-reward differs per plan.
- Never start with less than $1,000.

## Money (his)
- Judge by payouts vs eval fees, not daily P&L. Cap a bad day near -$10k (good days +$20k).
- 25 / 38 is an example; size per account and firm. Eval consistency rule caps a win near $1.5k.

## His warnings
- "Slightly winning"; real win rate lower than the examples.
- By feel: breakeven, moving the line, going back to an older line.

## Our tests so far
- 2026-10-19, the owner's search (111 versions, build days, 1:1.5): every fade toward the open = the 38% base rate of fading any bar (entries add nothing). The same displacement traded AWAY from the open: 40.5% target-vs-stop at 11.7 trades a day, +$4 = break-even (within half a tick; stress negative); not a rule he teaches. The 15-minute opening-bar continuation: 42.3%, +$70, 1 a day, the edge in the big-body 50/76 trades; 3:1 walk-forward positive on the stitched months but below the random bar, blind months 34 trades negative; fits the 50-account Lucid Flex 25K test in-sample (+$8k at 2 micros). Adversarial review: 15 of 20 findings confirmed. Finding: 50-Permanent/Findings/2026-10-19-jj-fair-price-111-versions-fade-is-base-rate-momentum-break-even.md. Code: engine/families/jj_fair.py, taught/jj_screen.py, taught/jj_fifty_accounts.py, taught/plan_scan.py.
- 2026-10-19, the $1,000 plan step 1-3 (owner): family jj_fair + taught sheet owner_jj_fair_nyam_25_38 (NY 09:35-11:00, displacement back to the 09:30 open, 25/38, 30-pt room, 3 losses = stop). Build days: 2,025 trades, 36.8% win (break-even ~40.2%), -$44/trade, every year negative, worse than random entries. 50 Lucid Flex 25K accounts (taught/jj_fifty_accounts.py, every payout, 90% split): net -$733 to -$1,600 at $50 a fee (4-6 of 50 pass, 1-3 paid). Monte Carlo: pass ~11-12% (JJ: 37%), funded payout ~18% (JJ: 35%). Finding: 50-Permanent/Findings/2026-10-19-jj-fair-price-reversion-fails-50-account-lucid-flex-25k-test.md.
- NY version (UVKVSWKFlvo, 2026-10-09): both trades stopped at the raw heat map (open fade 12.5% of boxes profitable).
- Evening version (nq_fair_price_eve, 2026-10-11): lost on the build days (-$54k to -$266k).
- Neither used: 30-pt minimum, exact displacement, line moves, pre-news fair, layering.
