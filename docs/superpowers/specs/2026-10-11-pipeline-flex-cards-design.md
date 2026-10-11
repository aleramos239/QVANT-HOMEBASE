# Pipeline flex cards (2026-10-11)

Owner, 2026-10-11: "lets upgrade the cards and pipeline so it can test way more things lets expand it to be way more versatile, use
any timeframe, any indicator in any setting, any time window, everything".

Six cards had been refused: the news-day straddles (08:30 and 10:00), the 03:00 London candle (NQ and ES), the vault break and the
overnight-range break. Reasons: no way to say "release days only", a family that "only trades NQ in 08:25-09:30", two families that only
run on 15- and 30-minute bars while a card could use 1 and 5.

## What a card can now say

| Freedom | How | Where it lives |
|---|---|---|
| Any bar size the library has (1, 5, 15, 30) | `card.bars` (a list; absent = 1 and 5 as before) | `blueprint/pipe_card.py`, `pipeline.json` `card.bars_allowed` |
| A family's own session, read with the way's own settings | `_own_sessions` asks the family with the way's `fixed` + the main setting values | `pipe_card.py` |
| An entry window, any clock time | `w_start`, `w_end` ("HH:MM", Globex-day clock, 18:00-23:59 = the evening before) on EVERY family | `engine/families/_flex.py` |
| A day rule | `days`: news, nonews, rel0830, rel1000, tier1, notier1, nfp, cpi, ppi, retail, gdp, pce, claims, fomc, nofomc, ism, jolts, umich, mon-fri, month_end, month_start, opex | `engine/flexind.py` (calendar `engine/cache/events.csv`) |
| An indicator gate in any setting | `gate` (rsi, price_ema, ema_x, macd, zscore, stoch, roc, cci, vwap_dev, adx, atr_rank, bbw_rank, er) + `g_n`, `g_m`, `g_s`, `g_lvl`, `g_side` (with / against) on EVERY family | `_flex.py`, `flexind.py` |
| An indicator as the trigger | family `ind_signal`: `ind`, `n`, `m`, `s`, `lvl`, `edge`, `mode` | `engine/families/flex.py` |
| Any range window | families `win_break` (close beyond; market, retest limit, fade) and `win_bracket` (OCO stops): `r_start`, `r_end` | `flex.py` |
| Any candle start | family `win_candle`: `start` (a whole bar), gates k / body_r / vol_m / body_pts, follow or fade | `flex.py` |

Every new setting is OFF by default; a family without them is trade for trade what it was (tests/test_flex.py: a fresh `blocks._wrap`
against the patched class, 47 families x 3 sessions, and four families on real build days).

## How it is built (and what it did not touch)

The stores and locks are stamped with the hash of `l2sim.py`, `l2ref.py`, `families/blocks.py`, the family's own module and five reader
files. Editing one re-stamps every store, so none of them is edited. The layer is:

- `engine/flexind.py` (new): incremental indicators fed one CLOSED tf bar at a time, the two reads (`gate_ok` a state, `event` a
  crossing) and the day calendar. Pure math; no engine state.
- `engine/families/_flex.py` (new): `FlexMods`, put in front of every class of `blocks.WRAPPED` (`cls.__bases__`) when
  `families/__init__.py` finishes `load()`. `HOMEBASE_FLEX=0` switches it off. A class keeps its module, its qualified name and its pickle
  reference, so a store's fingerprint (class path + inputs) is what it was.
- `engine/families/flex.py` (new): the four families above, joined to `blocks.BASES` / `WRAPPED` as `orb830.py` does. Their own module
  is in `runner.code()`, and for these families only `flexind.py` and `_flex.py` are stamped too.

`FlexMods.allowed(side)` is the one place a decision is read: it clips to the window, applies the gate (no value yet = both sides
blocked, as the filter blocks do) and then the family's own rules. `trades_on(d)` skips a day outside the day rule before its tape is read.

## Rules the families follow (written before any result)

- `ind_signal`: the indicator's value crosses centre +/- `lvl` at a tf close -> a market order at that close (follow) or the other
  side (fade). `edge exit` = the value comes back out of the zone. One trade a session. Stops and targets: the standard table.
- `win_break`: range = high / low of the 1-minute bars in [r_start, r_end). The FIRST tf close after r_end beyond it is the day's one
  signal, traded or not. Market at that close; or a limit at the broken edge for `wait` minutes; `fade` = the other side at market. Struct
  stop: follow = the other edge, fade = the break bar's extreme.
- `win_bracket`: OCO stop entries one tick beyond both edges, placed at r_end, struct stop = the other edge.
- `win_candle`: the tf bar that opens at `start`, green long / red short (fade: the reverse), gates all off at 0.
- The pass of the instance is the one that holds the first decision (not its last 5 minutes). The card's `session` must be that pass.

## What it still cannot do (said out loud)

1. **Entry windows that cross a session pass.** The tables are tagged by the entry minute's pass, and a family instance runs one pass. A
   window that starts in `nyam` and trades after 11:00 is cut at 11:00 (`mid` / `pm` entries are other passes). Vault break and
   overnight-range break trade `nyam` only; a card with a later window is refused by the pass rule, not silently cut. A multi-pass table
   is the next step (v2).
2. **Latent: `orb_close` start 0830** is one session "pre" 08:30-11:00, but a trade entered after 09:30 is tagged `nyam`/`mid` in the table.
   Older queued cards of that family are read on the entries before 09:30 only. Reported, not changed (it would move stored results).
3. **Indicators have no carry-in**: they warm up from the engine's restart (00:00 ET; 18:00 for an evening). A 200-bar EMA on 5-minute
   bars exists only after 16:40. `bars_needed` says it; a value that does not exist yet blocks both sides.
4. **Bar sizes 2, 3, 10, 60**: the library has 1, 5, 15, 30 (the overnight pools and tape caches are built for those).
5. **YM, RTY, SI**: the app keeps them, the pipeline's cost floors and tape builds are not set (owner's word needed on floors).
6. **Exits**: the standard table (48 cells) only. A custom flat time, breakeven or trail is not a card setting yet.
7. **The calendar ends 2026-10-02** (`events.csv`): later dates have no release rows, so `news` days after it read as "no news".

## Honest caveat: more freedom, more luck

Every free setting is one more place a lucky box can hide. The pipeline's guards stay as they were (gates mode "prop": makes money on the
build days, 40 % eval odds in 30 days, net > 0 on unseen days; the tries bar; the luck count). With a wider search the same bar lets more
false passes through. `bp.py pipe luck` is the measure; read it before trusting a pass from a flex card, and prefer cards that carry a
reason written before the test (the card's `why` and `loser`).
