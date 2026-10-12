# Book health pane, book-coloured candles, book flow and impact cost

Date: 2026-10-12. Status: written for the owner's review. Stages 1 and 2 only; stages 3 and 4 get their own specs.

## What the owner asked for (2026-10-12, in his words, shortened)

More indicators from the Level 2 data: book flow per bar, candles coloured by the book, bars that close every N book
updates, iceberg volume and a per-bar volume profile (traded volume and resting size, both), plus a book "health"
pane: thin book, spread, impact cost. He also said many indicators are hard to read or messy: that is a separate
clean-up, not part of this spec.

## Outcome and success

On the chart page he can see, in plain words, whether the book is thin, wide or cheap to trade through right now
(stage 1 + impact cost in stage 2), which side the book added to or pulled from inside each bar (book flow), and a
candle body colour that shows the book's lean at the close. Success is that each reads at a glance with the word label
the pressure indicator has, and that no number is shown where the data is missing.

Assumed, not said: first-guess thresholds (he reviews them on real days, like every order-flow indicator before);
NQ and ES only, because that is all that is recorded (since 2026-09-28, with holes).

## Design

All per-bar numbers are computed on the page from HBBookStore, as `bk:` series already are (cell.js `bookSv` writes
the bar's value into `b.sv`; flowdefs.js `bookValue` maps a series key to the store's per-bar means). No server
study is involved, so live equals history by the same rule the existing book indicators use.

### Stage 1: needs no new data

The stored one-second row today: `[t, b10, a10, imb1, imb5, imb10, micro, spread_ticks, best_bid, best_ask]`
(bookflow.py `_roll`; store COL map in bookstore.js).

1. **Thin book** (`bk:thin`): the bar's mean of `b10 + a10`, divided by the median of the one-second totals over
   the trailing N minutes (param, default 60, clamped to what the store holds). Line plus a dashed mark at 0.5.
   Word: under 0.5 "Thin", 0.5 to 1.5 "Normal", over 1.5 "Deep". Blank until the store holds 10 minutes.
2. **Spread** (`bk:spread`): the bar's mean `spread_ticks`, histogram; a bar over 2 ticks is solid, 1 to 2 pale,
   under 1 grey (the pressure bar's three tiers). Word: "Tight" / "Wide".
3. **Book health pane**: one own-pane indicator carrying 1 and 2 (and impact cost from stage 2) with one legend
   word. The word follows the worst of its parts so one glance answers "is it cheap to trade right now".
4. **Book candles**: a chart setting `bookCandles` (off by default, in the chart settings dialog). The body fill
   takes the mean `imb10` of the last 10 seconds of the bar: over +0.15 blue (bids heavy), under -0.15 orange (asks
   heavy), else grey. Border and wick keep the up/down colour, so direction stays readable. The book store is today
   fetched only while a visible `bk:` indicator exists (bookevents.js); this setting must also ask for it.

### Stage 2: new stored columns (bookflow.py, bookhist.py, bookstore.js)

New columns are appended after `best_ask` (index 10 onward), so old rows and old readers keep working:

| Col | Name | Meaning |
|---|---|---|
| 10 | `ofi` | Order-flow imbalance at the best bid and ask summed over every book line in that second (Cont, Kukanov and Stoikov: size added at a rising or equal best bid, minus size removed at a falling best bid, and the mirror on the ask). Positive = the book added on the bid side. |
| 11 | `cb10` | Ticks above the best ask that a 10-contract market buy fills at on average (None when the top 10 cannot fill it). |
| 12 | `cs10` | The same for a 10-contract sell against the bids. |
| 13 | `cb50` | The 50-contract buy. |
| 14 | `cs50` | The 50-contract sell. |

- **Book flow per bar** (`bk:flow`): the bar's SUM of `ofi` (a sum, not a mean). Histogram with the three tiers
  scaled to the instrument's own median absolute bar value (so NQ and ES read alike). Word "Book adding bids /
  adding offers / even".
- **Impact cost** (`bk:impact`): lines `cb10`/`cs10` (and 50 on a switch), mean per bar, in ticks.
- `bookhist._average` averages columns when a window asks for a coarser step: `ofi` must be SUMMED there, the
  rest averaged; the client store's `meanAt` must not average it either.
- **No rebuild.** History is replayed on demand from the raw depth files and cached in memory only (bookhist.py is
  read-only), so every recorded day gets the new columns after the chart service restarts. A day whose depth file
  is missing shows blank, as today.
- **Live.** The server's live tracker is the same `BookTracker` code, so the live ws rows carry the same columns.

### Errors and gaps

A bar the store does not cover is a gap (null), never a zero. A feed gap over 60 s resets the tracker's `ofi` carry
(the same rule that already closes open levels as faded), so a level flip across a gap is not counted as flow.

## Testing

- bookflow.py: hand-made book sequences for `ofi` (add at bid, pull at bid, price steps up and down), for
  `cb10`/`cs10` (exact fill across levels, None when thin), and a gap that resets the carry.
- bookhist.py: `_average` sums `ofi`, averages the rest, passes `None` through.
- JS: `bookValue` for `bk:thin`, `bk:spread`, `bk:flow`, `bk:impact`; tier colouring and words; candle colour rule
  and the "book asked for" switch (tests/js, like indstatus and catalog tests).
- Real-tape replay of one NQ session through the tracker: counts of Thin / Wide / flow tiers per hour, so the
  thresholds are seen before they ship.

## Out of scope (own specs later)

Per-bar volume profile with iceberg volume and resting size (stage 3), and bars that close every N book updates
(stage 4: it changes the core bar builder, which has no book today and has history only since 2026-09-28).
These are chart-reading aids, not strategies; a rule that uses one goes through the strategy pipeline.
