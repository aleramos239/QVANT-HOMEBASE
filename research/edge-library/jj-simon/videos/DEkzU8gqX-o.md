# Video notes: DEkzU8gqX-o - JJ Simon "The Prop Firm Strategy That Made $1.8M"
https://www.youtube.com/watch?v=DEkzU8gqX-o | 14:13 | captions read in full + chart frames (2026-10-19)
Same fair-price rule (see jj-simon-fair-price-rulebook.md). This video is the WHY plus the entry list; two NQ 1m examples.

## His argument
- A prop firm is a rule set, not a live market: optimize the PASS RATE (hit target before max loss) on evals, and EXPECTED VALUE (chance of payout x payout size) on funded.
- For any rule set there is a best target and best stop. Find it and repeat it as often as you can.
- That only works with a BIAS: a small, steady drift your way (maybe ~1% edge). Reversion to fair price is that bias.
- With a bias, any entry along the move has about the same edge, so the target / stop can be set by the account, not by the chart. Entry signals add only ~0.1% edge; the bias is what matters.
- Discretionary targets (previous high, stop under a low) suit a live account, not a prop firm.
- Many trades a day spread risk. "Please don't take one trade a day" on a prop firm.

## Rules said here (new or sharper)
- Fair price = the session open, or the pre-news price.
- Entries toward fair, two kinds:
  - Break of structure: a candle whose wick is taller than the candles on each side = structure; a candle closing past it = the break.
  - Displacement: body bigger than the previous body AND close past the previous candle's wick.
- Stop / target = whatever the account needs (e.g. target 50, stop 25; or 45, 70...). Not fixed 25 / 38, not at structure.
- 80 / 20 rule: at least 80% of the target must lie on the near side of the fair line; no more than 20% of the target beyond fair. (Same idea as "30 pts room for a 38 target".)
- Moving the line: a displacement or break of structure AWAY from the open moves fair to the latest price. Failed attempts don't move it. A successful push away moves it to that area (on his example this matched VWAP).
- Layering: every green candle (in a long bias) he adds; "a green candle has a 50.5% chance the next is green".
- Higher-quality (trend-confirmed) entries win slightly more, but he doesn't wait for them: speed matters, get all accounts traded.
- VWAP: "a pretty good estimate on average... you could just trade in the direction of VWAP" on a prop firm with the right target / stop. He does NOT use it because VWAP ignores news. He uses the open / pre-news price with a little discretion.
- Target / stop change by: firm, eval vs funded, new / in loss / in profit / taking a payout. Decide with expected value: (chance of win x account worth after the win) - (chance of loss x account worth after the loss).

## Re-check 2026-10-19 (frames 0-14 min)
- Whiteboard: bias drawn as a slightly rising line; eval box -2,000 / +3,000 with 300 / 1,000 / 1,500 targets each having a different pass rate because the drawdown trails.
- A +350 / -270 discretionary box (target at the previous high, stop under the low) drawn as the WRONG way for a prop firm.
- Sep 8 boxes: 52.25 / 52.25 (1:1) and a ~2:1 box on the same move, to show the same bias fits different accounts. Entry low in the move = ~100 pts of room; entry near the line = ~10.

## Examples
| Day | What happened |
|---|---|
| Tue Sep 8 2026, 09:30 | Big red flush from the open (~29,640 -> ~29,430). Reversion longs: displacement, displacement, break, displacement, break -> 5 losses in a row. Then a displacement W, a break W, then a chain of breaks all W as it trended back. Stop near the red (open) line; he took one trade above it. Line moved once to where a push down succeeded (in line with VWAP). Fixed stop ~24 pts, targets set per account (one drawn at 67.75). |
| Fri Sep 4 2026, 08:30 news | News drop from the pre-news price. Reversion longs to the pre-news price: displacement, breaks, ~7 entries, mostly W as it climbed back to and past the pre-news price by 10:00. |

## His numbers
- $1.8M payouts, ~$557k spent on evals (3.5x). Started Feb 2025 with $5k; first six-figure month July 2025.
