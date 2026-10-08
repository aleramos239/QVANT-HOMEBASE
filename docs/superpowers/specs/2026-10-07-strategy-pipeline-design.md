# The strategy pipeline — design

Date: 2026-10-07. Agreed with the owner in chat, piece by piece. Nothing here is built yet.

## 1. What it is

One program inside Homebase. Idea cards go in. The program runs each idea through fixed stages.
An idea stops at the first gate it fails, and the program writes why. The few that pass every
stage reach the owner for one last look, then go in **the book**. Later, strategies from the book
are mixed into prop-firm portfolios.

- Built for prop firms, not live trading. First account: **LucidPro 50K, no daily loss limit**.
  LucidFlex 50K next. Apex 300K on the side. A book card shows the odds on all three.
- Claude is used only at the two ends: to write idea cards, and to read the results out. The
  testing is plain code and uses no tokens.
- Nothing is chosen in the middle of a run. Every choice is on the card before the run starts.
- The owner looks only at the end.

It replaces the round-by-round way of working in `research/edge-library/BLUEPRINT.md` (version 1.1).
Section 9 lists every difference. The build days and the unseen days do not change:
build = 2021-09-22 to 2025-06-30, unseen = 2025-07-01 to the latest day.

## 2. The idea card (stage 0)

| Line | What it holds | Limit |
|---|---|---|
| Name | a short name | — |
| Why | why it should make money, and who loses | one sentence |
| Family, source | filled in by the program: the family (FVG, range break, VWAP ...) and where the idea came from (owner, video, Claude) | — |
| Market | NQ, ES or GC | one |
| Time of day | one session | one |
| Ways to enter | the exact entry rules to try | up to 3 |
| Main setting | 3 values for each way | 3 |
| Bar size | 1-minute and 5-minute | both, always |
| Stops and targets | the standard table (8 stops x 6 targets = 48 boxes) | fixed |
| Indicators to try | each with its reason, in order | up to 5 |
| Sides | long and short, or one side and why | — |

Rules for cards:

- A card uses only blocks that exist. An idea that needs a new block waits on a "needs a block"
  list; building the block is a separate job.
- "The same idea" = the same entry rule, market, time of day and settings. The program keeps every
  card it has seen and refuses a repeat. A new way of an old idea counts against that idea's 3 ways.
- What Claude aims for when writing cards (aims, not gates): trades most days; holds longer than
  5 seconds; a capped loss per trade; risks a small part of $2,000.

Pass: the card is complete and uses only blocks that exist.

## 3. The stages

A **heat map** = one way on one bar size: 48 stop/target boxes x 3 setting values = 144 boxes.
A **try** = one heat map the program judged for an idea (a way on a bar size at stage 1, or an
indicator at stage 3). The program counts tries; stage 4 gets harder with each one.
Costs are on from the first run. One contract. Floors for the average trade after costs:
NQ $70, ES $75, GC $140.

### Stage 1 — raw heat map (no indicators)

Up to 6 heat maps an idea (3 ways x 2 bar sizes).

| Result | Needs all of |
|---|---|
| Strict pass → stage 2, then skip stage 3 | over 60 % of boxes profitable · average trade at the full floor · 200+ trades a box |
| Low pass → stage 2, then stage 3 | over half the boxes profitable · average trade at half the floor (NQ $35, ES $38, GC $70) · 300+ trades a box |
| Fail | anything less |

- All heat maps fail → the idea is dropped.
- Only ONE heat map an idea moves on: a strict pass before a low pass, then the one with the
  biggest average trade.

### Stage 2 — machine check

Every trade of the heat map that moved on is checked: every entry is inside the session · one position
at a time · flat by the cut-off (15:58 ET, 13:13 on half days) · the trade count fits the rule · winners
end near the target, losers near the stop. The middle box is run again and every entry and exit price
of it must sit inside its 1-minute bar.

**As built (2026-10-08):** the entry signal is NOT re-derived by a second implementation of each entry
rule (28 of them): that was not realistic. Each block keeps its own unit tests.

One wrong trade → the idea stops as a **code problem** (not a bad idea) and is flagged for repair.
Nobody looks at a chart here. The unseen days are never touched by an idea that failed this check.

### Stage 3 — indicators (only after a low pass)

Each indicator on the card is tried alone on the heat map, in the card's order. One passes when
all of these hold:

- over 60 % of boxes profitable
- average trade at the full floor
- 200+ trades a box
- long and short each make money (a one-sided idea: its side)
- it beats the raw heat map on BOTH average trade and share of profitable boxes
- at least half of the other-market heat maps are profitable (the same idea on the other two markets)

If several pass, the one with the biggest average trade moves on. If none of the 5 passes, the idea
is dropped. Two indicators at once are not in this version.

A strict pass from stage 1 must also meet lines 4 and 6 above before stage 4.

### Stage 4 — proof

| Check | Pass |
|---|---|
| Reshuffle the days 1,000 times | the first two strict lines hold in 75 % of the runs |
| Beat random entries (same stops, targets, hours and days) | better than (100 − 5 ÷ tries) % of random heat maps: 1 try 95 %, 2 tries 97.5 %, 5 tries 99 %, 11 tries 99.5 % |

The reshuffle runs first (minutes). The random check (hours) runs only if the reshuffle passed.

### Stage 5 — pick one box and lock

- The program picks the box in the middle of the profitable area (the blueprint's default variant:
  the middle survivor, never the best). If that box fails, the idea stops. No second box.
- The box alone, on the build days, must show:
  - profit factor 1.2 or more
  - net profit at least 3 times the worst drawdown
  - Sharpe 1 or more
  - worst drawdown at 1 micro under $2,000, open losses counted
  - makes money in 80 % of 1,000 reshuffled runs
  - still makes money without its best 1 % of days
- Prop check, LucidPro 50K no daily limit, at the best size (1 to 40 micros), open losses counted,
  read on the "live is worse" row (win rate −5 points, winners −15 %):
  - chance to pass the eval within 30 trading days: over 50 %
  - chance to reach the maximum payout within 30 trading days: over 50 %
  Both yes = **stands alone**. Otherwise = **helper**. This is a label, not a gate.
  (As built: the eval number is read at the size that is best for the eval, the payout number at the
  size that is best for the funded account; the two sizes can differ.)
- Then the rule, settings, box and costs are frozen. Any change = a new idea from stage 0.

### Stage 6 — unseen days (one read, never repeated)

Every line must hold:

- July-December 2025 and January-September 2026 each make money
- the average box and the middle box of the heat map make money
- average trade at the full floor, and at least half of what it was on the build days
- beats 95 % of random heat maps
- still makes money with worse fills (2 ticks and 250 ms late)
- still makes money without its best 1 % of days (4 of the about 315 days of this stretch)
- makes money in 80 % of 1,000 reshuffled runs
- the picked box keeps profit factor 1.2 or more

A fail is final: no re-tune, no second read.

### Stage 7 — the owner's look, then the book

The owner sees the strategy's card with every stage's numbers and approves or refuses it. Approved
= saved in the book as **proven on history**. It becomes **proven live** only when its real eval
trades match the test (1 micro first, as the blueprint's phase 6 says).

The book card holds: the frozen rule · the label, set from the unseen-day trades · hours it trades ·
best size · eval odds and payout odds within 30 days on LucidPro, LucidFlex and Apex 300K · days to
pass · winning days a month · winning months (for example 31 of 45) · biggest day as a share of
profit · share of profit from trades held 5 seconds or less · worst day · worst drawdown.

Nothing in the book is edited.

### Stage 8 — the portfolio (built later; rules fixed now)

- Only book strategies. No two from the same family on the same market.
- Each added strategy must raise the mix's eval odds, or it is left out.
- The account's own rules must hold for the mix: at most half the profit from trades held
  5 seconds or less; for Flex the biggest day at most half the profit.
- The mix passes at: **60 % to pass the eval within 5 weekdays** and **75 % to reach the maximum
  payout within 14 trading days**. Fewer days and a higher chance are better: mixes are ranked that way.
- The program always shows the best mix it found and how far it is from that bar.

## 4. Guards against luck

- Tries are counted for an idea and raise the random bar (stage 4).
- A card cannot come back under a new name.
- One box, no second pick. One read of the unseen days.
- The Book shows a running count: strategies read on unseen days, and how many passed. A pass share
  near what luck alone gives means the book is not to be trusted yet.

## 5. In Homebase

| Part | What it is |
|---|---|
| **Guide** (Lab) | The step-by-step page, section 6 |
| **Queue** (Lab) | One row an idea: the stage it reached, running / stopped / passed, and the exact line and number that stopped it |
| **Book** (Lab) | The cards of the finishers and the luck count |
| **Runner** | Works through the queue by itself. Its own process (not the chart service): a chart restart does not kill it, and after any stop it carries on where it was |
| **Rules file** | One file with every gate number. Each stage card records the numbers it was judged by |
| **Controls** | Start, pause, add cards. Claude adds cards from chat; the owner can pause at any time |

The runner follows the machine's limits as they are: 2 tests at a time in desk hours, 4 outside them.
One way takes about 20 minutes at stage 1, so about 20 to 30 ideas get a first verdict a night.

## 6. The Guide page

For someone who has never traded. Six steps, each one sentence and one button. A button is grey
until its step is allowed, so the steps cannot be done out of order, and there is no setting to pick.

1. **Write the idea.** Fill the card, or tell Claude the idea and it fills the card.
2. **Press Start.**
3. **Wait.** The computer tests it. This can take a night.
4. **Read the Queue.** Red = stopped, and it says why in one line. Green = it passed everything.
5. **Look at a green one.** Read its card. Press Approve to put it in the Book, or Refuse.
6. **Build a portfolio** from the Book (later).

Under the steps: the ladder of stages, each with one plain sentence ("Stage 1: does it make money
with many different stops and targets?") and how many ideas are at it now.

## 7. Build order

1. Bring the test tools in the running folder up to date with GitHub main.
2. The new idea card and the rules file.
3. The runner for stages 1 to 3, and the Queue.
4. Stages 4 to 6 and the full machine check.
5. The Book and the Guide.
6. The portfolio.
7. The hunter (section 12).

## 8. Not in this version

Two indicators at once · markets other than NQ, ES, GC · the evening session · exits outside the
standard table · Level 2 indicators past stage 3 (their history ends 2026-07-08) · blocks that do
not run on the build days yet.

## 9. What changes against the blueprint (version 1.1)

| Blueprint 1.1 | The pipeline |
|---|---|
| One entry rule, a main setting with 3-4 values, one home bar size | Up to 3 ways, 3 values each, 1-minute and 5-minute always |
| At most 5 rounds, a reason written before each | No rounds: everything is on the card; tries are counted instead |
| Random bar 95 / 97.5 / 98.3 / 98.75 / 99 % on rounds 1-5 | The same numbers, by tries: (100 − 5 ÷ tries) % |
| At most 2 filters, one a round | Up to 5 indicators on the card, each tried alone; one is kept |
| No lower bar | A lower bar at stage 1 earns the indicator tries |
| Code check: 10 trades looked at on the chart | Every trade re-checked by the machine; no chart look before the end |
| Card lines "where else", "where not", "when it loses" | Dropped; the other markets are run by the program |
| Reshuffle 90 % at the lock and on the test | 80 % at both |
| Profitable without its 3 best days (test only) | Without its best 1 % of days, at the lock and on the test |
| One strategy: a pass before a bust 50 %, no day limit (a bar) | Eval and max payout within 30 trading days over 50 % (a label: stands alone / helper) |
| Portfolio: 60 % within 10 days, 75 % max payout within 20 days | 60 % within 5 weekdays, 75 % within 14 trading days |
| A failed lock goes back to the build | The idea stops |

When this is built, `BLUEPRINT.md`, the `strategy-blueprint` skill and the repo's `CLAUDE.md` are
rewritten to match, so every chat follows the same law.

## 10. Where each number comes from

- **From the blueprint (unchanged):** the floors, 60 %, 200 trades, both sides, other markets, the
  75 % reshuffle at stage 4, the random bar, profit factor 1.2, net 3 times the drawdown, Sharpe 1,
  the 1-micro drawdown line, every stage 6 line except the two changed ones.
- **The owner's (2026-10-07):** 5 indicators · everything by machine · the two 30-day prop numbers ·
  helper stays in the book · 80 % reshuffles · the portfolio bar (5 weekdays, 14 days).
- **Claude's judgment, to be checked against the stored build-day tables before the numbers are
  frozen:** the lower bar (half the floor, over half the boxes, 300 trades) · one heat map moves on ·
  the best 1 % of days.

## 11. Open points

- "14 days" for the maximum payout is read as 14 trading days.
- 60 % within 5 weekdays is far above anything found so far: the best mix of the old pilot reached
  about 42 % in 5 days on the days it was built on and 37 % on unseen days, under the open-loss rule; no edge at all
  passes about 40 % of evals with no day limit. The bar stays
  as the owner set it; the program shows how close the best mix is.

## 12. The hunter (added the same day)

The owner wants it always running: Claude hunts for strategies until the portfolios are built.

**Goal:** 2 portfolios for each account type — LucidPro 50K, LucidFlex 50K, Apex 300K — 6 in all,
LucidPro first. No strategy is shared between two portfolios at the same firm (Pro and Flex are one
firm); a strategy may sit in a Lucid portfolio and an Apex one. After the goal is met the hunter keeps
going, to replace weaker members, until the owner pauses it.

**The loop, every night (a scheduled Claude job on this Mac):**

1. Claude reads the Queue's summary: what was tried, where each idea stopped and why, by family.
2. Claude writes the next batch of idea cards (at most 25 a night: what the runner can test) and adds
   them. Ideas the owner dropped in the **ideas inbox** go first. Other sources: the block list, the
   video and wiki notes, and what the results so far point to.
3. The runner tests them. No Claude, no tokens.
4. Finishers wait for the owner's look (stage 7). The hunter does not wait for it.
5. When the Book changes, the program tries new mixes (stage 8).

**Limits:**

- The hunter only adds idea cards. It cannot touch the desk, an account, a setting or the code.
- Existing blocks only. A block it wants goes on the "needs a block" list; blocks are built with the owner.
- The owner can pause it at any time. A nightly cap on cards and on Claude's time.

**Guards against luck (a hunt that never stops finds winners by chance):**

- **The luck rate, measured.** Random-entry strategies that happened to look good on the build days
  are read on the unseen days through the same stage 6 lines. The share that passes is what luck
  alone gives. The Book shows it beside the real pass share.
- **The score since the lock.** Every day adds unseen data. Each book strategy is run on paper on the
  days after its lock, by the program, every day; its card shows "since lock: +$X in N days". This is
  the one proof luck cannot fake.
- Portfolios prefer strategies that hold up since their lock. One whose drawdown since the lock passes
  the 95th percentile of its own reshuffled runs is flagged and left out of new mixes until reviewed.

## 13. Apex Legacy 300K — the rules as Apex states them (read 2026-10-07)

Source: the Legacy pages of Apex's help center the owner sent (PA trading rules, evaluation rules,
trailing drawdown rule, PA payout parameters, safety net rule). The app's rule file
`apex-legacy-300k@2026-09-28` is unconfirmed and differs; a new version is written from these in the
build. Not read: the detail pages for contract scaling, the 30 % open-loss rule, the 5:1 rule, hedging
and one direction, and the end of the long evaluation page.

| Rule | Apex says | The app's file has |
|---|---|---|
| Legacy evals | cannot be bought since 2026-03-01; passed ones still become Legacy PA accounts | an eval with a $20,000 target |
| Drawdown | $7,500, trailing the highest LIVE balance during trades (open profit counts) | end of day |
| Where it stops (PA) | fixed at $300,100 once the live peak reaches $307,600 | the same level, reached at end of day |
| Size | 35 minis; only half until the end-of-day balance is above $307,600 | 35 minis |
| Daily loss limit | none | none |
| Open loss | at most 30 % of the profit balance at the start of the day (50 % later) | not there |
| Stop against target | the stop at most 5 times the target | not there |
| One direction | no orders resting on both sides, no long and short together | not there |
| Payout: days | 8 trading days, 5 of them with $50 or more | 5 days of $150 (copied from Lucid) |
| Payout: balance | at least $307,600 for the first three payouts | not there |
| Payout: size | $500 minimum, $3,500 maximum for the first five | half the profit, $2,000 at most (copied from Lucid) |
| Payout: one big day | no day above 30 % of the profit, until the sixth payout | not there |
| Flat by | 16:59 ET | 16:10 ET |

What it means for the pipeline:

- Apex is **funded accounts only**: the owner's five PA accounts. There is no Apex eval to pass, so
  the Apex portfolios are judged on the payout odds alone.
- Two-sided entries (a buy stop and a sell stop resting together: straddle, range-break and the other
  blocks marked "rests orders on both sides") cannot go in an Apex portfolio.
- A box whose stop is more than 5 times its target cannot go in an Apex portfolio.
- The Apex mix must keep its biggest day at or under 30 % of the profit.
- The book card's Apex odds use the live-peak drawdown, not the end-of-day one.

## 14. As built: the one-read rule (open, the owner decides)

The toolkit lets only ONE idea of a family, market and time of day be read on the unseen days (a
relative's read uses the days up for the others). The pipeline inherits it: a second idea in the same
slot is refused at stage 6. Asked of the owner 2026-10-08: A refuse such a card when it is added
(Claude's pick) · B let ideas of one slot wait at stage 5 and read only the strongest · C drop the rule.

