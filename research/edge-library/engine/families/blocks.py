"""blocks -- EXIT and FILTER BLOCKS for every bar-based library family, the `ib_n` family, the extended exit menu.

WHY: a new idea should be SETTINGS built from blocks that are tested once (ideas/specs/<name>.json, run_idea.py), not new
strategy code plus new look-ahead tests. Nothing in l2sim.py or in another family module is changed: `Blocks` is a mixin put
IN FRONT of a family class. With every block off a wrapped family is trade-for-trade the original (tests/test_blocks.py).

    WRAPPED[name]    = class B_<name>(Blocks, <the family's registered class>)   every bar-based library family without
                       Level-2 features of port1 / port2 / port3 / round1 / timed / fvg, and ib_n (time-fired families are left out)
    CONTROLS[name]   = class R_<name>(Blocks, l2ref.Random)   the random-entry control of a range stop: a random entry that
                       carries the family's own structure height (same stop rule, random time and side)

WHEN A BLOCK IS READ: at the moment the family places its order -- inside `allowed(side)`, which the Template calls for every
market entry (the signal bar's close) and for every leg of a resting bracket (the instant the bracket is placed: orb / ib_n at
the range end). A filter never looks at a fill that comes later; a direction filter on a two-sided bracket keeps the leg it
allows. Every filter has two sides; a filter WITHOUT A SIGNAL (too little history, a missing book) blocks the entry on BOTH.

EXIT BLOCKS
  stop_mode = "rng"   stop distance = stop_val x the HEIGHT of the structure the family trades, read at the order (HEIGHTS):
        orb            high - low of the first or_min minutes of the session
        orb_confirm    high - low of the first or_min minutes from 09:30
        ib / ib_n      high - low of 09:30 .. 10:30 / of the first ib_min minutes from 09:30
        lon_break      high - low of 03:00 .. 08:25
        donchian       high - low of the n tf bars before the signal bar (the channel)
        vol_spike_break  high - low of the 20 tf bars before the signal bar
        first_bar_mom  high - low of the signal bar
      floored at 2 ticks like every stop; no structure yet (or height 0) -> no entry. A family that is not in HEIGHTS has no
      structure and REFUSES the mode (ValueError at construction).
  more ATR stops / targets: the Template takes any stop_val / tgt_r; they are only menu cells: menu_extended(root).
  MENU "extended" = the 32 standard cells first (same order, same ids), then the 8 standard stops x targets {1.5, 4}, then the
      new stops (ATR x 1 and x 2, then range x 0.25 / 0.5 / 1) x targets {0, 1, 2, 3, 1.5, 4}: 78 cells, 60 without a structure.

FILTER BLOCKS (FILTERS: block -> side -> the inputs that switch it on)
  volatility  high | low    f_dvol = hi | lo     the PRIOR trade date's range (h - l) above / not above the median of the 20
        daily ranges ending with that day (ctx.daily = bars dated before today only; the definition of out/deepen/labels.py
        T2, checked against it). Fewer than 20 daily bars -> no entry.
  momentum    with | against  f_rsi              Wilder RSI(14) of the tf closes since the indicator restart (00:00 ET; 18:00
        for a held evening), closed bars only, at the signal bar's close. with: long needs RSI > 50, short < 50; against: the
        mirror. Fewer than 15 closes, or RSI exactly 50 -> no entry.
  momentum (more)  strong_with | extreme_against   f_rsi    strong_with: long needs RSI >= 60, short <= 40 (RSI_STRONG = 10 points
        beyond 50); extreme_against: long needs RSI <= 30, short >= 70 (RSI_EXTREME = 20 points beyond 50, a fade of an extreme).
  volume      high | low    f_cvol = hi | lo     the volume traded from the SESSION'S ANCHOR to the decision (completed
        1-minute bars only) above / below the median, over the 20 trade dates before today, of the volume of the same clock
        window. Anchor = the Template's anchored-VWAP anchor: asia 00:00, london 03:00, pre 08:25, nyam / mid / pm 09:30 (the
        cash open: a midday or afternoon signal reads the volume since 09:30), eve 18:00. Fewer than 20 prior dates, a prior
        date without a tape, equality, or a decision AT the anchor (an empty window) -> no entry.
        Prior days come from cache/minvol_<ROOT>.npz (build_minvol; per ET minute of the Globex day, by trade date).
  news        yes | no      f_news               the trade date has / has not a row at 08:30 or 10:00 ET in cache/events.csv
        (the STAGE 3 calendar: groups A and C; the 14:00 FOMC rows are not release days here). A schedule: known in advance.
  book        agree | disagree  (NQ only)        agree = the Template's own f_book = "on" (the 5-minute mean of the top-10
        imbalance imb10 does not oppose the side: long needs mean >= 0); disagree = f_bookopp = "on": the same signal
        (l2sim.book_mean5) OPPOSES the side (long needs mean < 0). No signal -> no entry. Needs features (BOOK_COLS).

  PRICE-AND-TREND BLOCKS (NQ, ES and GC; every one reads the idea's own tf bars, closed bars only, at the signal bar's close; a line that
        cannot be computed yet, or a close exactly on it, has no signal and blocks the entry on both sides)
  ema20, ema50  with | against      f_ema20 / f_ema50   the close above (with: a long) / below (a short) the EMA(20) / EMA(50) of the tf closes since
        the indicator restart; the EMA is seeded with the first close, as the Template's own EMAs. 20 / 50 closes needed.
  trend         with | against      f_trend             the Template's own option: the slope of that EMA(50) (long needs it rising).
  vwap          with | against      f_vwap              the Template's own option: the close against the SESSION'S volume-weighted
        average price (the session instance's own VWAP: it restarts at each session).
  avwap         with | against      f_avwap             the close against the volume-weighted average price ANCHORED at the day's anchor
        (VOL_ANCHOR: asia 00:00, london 03:00, pre 08:25, nyam / mid / pm 09:30 -- a midday trade reads the VWAP since the cash open).
  vwma          with | against      f_vwma              the close against the volume-weighted moving average of the last VWMA_N = 20 tf
        closes (weights = the tf bars' volume). 20 bars needed.
  channel       with | against      f_channel           where the close sits in the channel of the CH_N = 20 tf bars before the signal bar:
        position = (close - channel low) / (channel high - channel low). with: long needs the top third (>= 2/3, a break above
        counts), short the bottom third (<= 1/3); against: the other way round (a dip bought, a rally sold). 21 bars needed.
  adx           strong | weak       f_adx               Wilder's ADX(14) of the tf bars since the restart: strong = at least ADX_STRONG =
        25, weak = below ADX_WEAK = 20; between them no signal (both sides). 28 bars needed. A filter of the regime, not of a side.
  rvol          high | low | spike  f_rvol              the volume of the tf bar that just closed against the SAME clock bar on the RVOL_DAYS
        = 14 trade dates before today (a 09:30 bar against fourteen 09:30 bars): high = above their median, low = below it, spike =
        at least RVOL_SPIKE = 2 times it. 10 of the 14 dates needed (cache/minvol_<ROOT>.npz, as the volume block).

  LIQUIDITY-LEVEL BLOCKS (NQ, ES and GC; the levels are engine/levels.py: prior day, overnight, Asia 00:00-03:00, early London 02:00-05:00,
        London 03:00-08:25, the evening before 20:00-24:00, the last 5 days, the swing high / low of the last 5 sessions (50 5-minute bars
        each side, still untraded), and the equal highs / lows (NQ only: two such swings within 10 points, the second not beyond the first); each is a high and a low that has ENDED; the swing needs cache/bars5m_<ROOT>.npz, as the volume block)
  level         near | clear        f_level             the distance of the last close to the closest level price (any level, high or low):
        near = within NEAR_ATR = 0.5 x ATR of it, clear = farther than CLEAR_ATR = 1.0 x ATR from every level. No level known: no signal.
  swept         with | against      f_swept             since 00:00 ET a bar traded beyond a level (levels.track): with = the liquidity on
        the OTHER side of the trade was taken (a long needs a LOW swept, a short a HIGH swept); against = the liquidity on the trade's own
        side was taken (a long needs a HIGH swept). Nothing swept: both sides blocked.

  ZONE BLOCKS (NQ, ES and GC; SMT NQ and ES; first-guess definitions, written in engine/zones.py before any result)
  pdz           with | against      f_pdz               premium / discount: the close against the midpoint of the day's range since 00:00 ET
  ote           in | out            f_ote               the 62-79 % retracement zone of that range's leg
  htf15, htf60  with | against      f_htf15 / f_htf60   the close of the last closed 15- / 60-minute bar against its EMA(20) / EMA(8)
  smt           agree | disagree    f_smt               NQ and ES diverge at a new 3-hour extreme (the last 6 5-minute bars against the 36 before)
  pdz_move, pdz_swing, pdz_leg   with | against     f_pdz_<range>   premium / discount on the owner's three ranges (NQ only; engine/ranges.py): the move in progress,
                                    the swing pair, the leg rule; the close must be inside the range
  ote_move, ote_swing, ote_leg   in | out           f_ote_<range>   the 62-79 % zone of the same three ranges (a leg that points the trade's way)

  BATCH 4 BLOCKS (NQ, ES and GC; first-guess definitions written in engine/indicators.py before any result, the owner reviews each; the
        idea's own tf bars, closed bars, at the signal bar's close, since the indicator restart; no signal = both sides blocked)
  bbw           tight | wide        f_bbw       the Bollinger bandwidth ((upper - lower) / middle, 20 bars, 2 sigma) ranked among the 120
        before it: tight = rank at most BBW_TIGHT = 20 %, wide = at least BBW_WIDE = 80 %, between: no signal. 140 closes needed. Direction-free.
  atrp          high | low          f_atrp      Wilder's ATR(14) ranked among the 100 ATR values before it: high = at least ATRP_HIGH = 70 %,
        low = at most ATRP_LOW = 30 %. 114 bars needed. Direction-free.
  er            trend | chop        f_er        Kaufman's efficiency ratio of 14 bars (|net change| / the path): trend = at least ER_TREND =
        0.5, chop = at most ER_CHOP = 0.25, between: no signal. Direction-free.
  macd          with | against      f_macd      the MACD(12, 26, 9) histogram: with = a long needs it above 0 and not below the bar before's
        (a short the mirror); against = the opposite pairing. A fading histogram, or exactly 0: no signal. 35 closes needed.
  rsidiv        with | against      f_rsidiv    RSI(14) divergence against the lowest low / highest high of the bars [-20:-3]: bullish = a new
        low with a HIGHER RSI than at that earlier low, bearish = the mirror. with = a long needs bullish (a short bearish); against = the reverse.
  mfi           with | against | extreme_against   f_mfi   Money Flow Index of 14 bars (typical price x volume): with = a long needs MFI above 50
        (a short below); against = the mirror; extreme_against = a long needs MFI at most 50 - MFI_EXTREME = 20, a short at least 80.
  deltadiv      with | against      f_deltadiv  price against the net delta of the last 20 tf bars (the delta blocks' flow table, whole minutes
        before the decision): bullish = the close fell over them and the net delta is positive, bearish = it rose and the delta is negative.
        with = a long needs bullish (a short bearish); against = the reverse. A delta block for the data cap (FLOW_BLOCKS).
  candle        displace | engulf | reject   f_candle   the signal bar's shape: displace = body at least 1.5 ATR and the close in the top 25 %
        of the range (a long) / bottom 25 % (a short); engulf = the body covers the previous bar's body, opposite colours, the new bar points
        the trade's way; reject = a wick of at least 2 x the body on the trade's side (a long: the lower wick), body above 0.

  LEVEL-2 BLOCKS (the vendor's order book, NQ only, the feature table of l2data: one row per minute, usable at the minute's end;
        a minute without a valid book -- a roll day, a crossed book, another contract -- is NaN and has no signal: both sides blocked)
  book        agree | disagree      (above)  the 5-minute mean of the top-10 imbalance leans the trade's way / against it
  depth       thin | thick          the top-10 depth against its median at the same minute over the 20 sessions before (the Template's
                                    f_depth): thin = at most 0.8 of it, thick = at least 1.2 of it (the SPEC's B6)
  ahead       thin | thick          the depth the trade must push through (a long: the offers; a short: the bids) against its own
                                    median of the last 15 minutes: thin = at most 0.8 of it (the Template's f_thin, SPEC D4), thick = above that
  wall        clear | blocked       blocked = a level of the opposing side's top 10 holds at least WALL_X = 5 times the median level
                                    and stands within WALL_TICKS = 8 ticks of the touch (SPEC B4's wall); clear = there is none
  stack       with | against        the minute's change of the top-10 size on the trade's side minus the other side's, as a share of the
                                    depth: at least +STACK_FRAC = 5 % (with: size was added behind the trade / pulled in front of it)
                                    or at most -5 % (against). A smaller change has no signal.
  Level 2 history: the build days (to 2025-06-30) are bpfeat's table, the test days (2025-07-01 .. 2026-07-07: the vendor's depth history
  ends 2026-07-07 15:59) are btfeat's; a Level 2 idea's frozen test range ends at that table's last day (blueprint/freeze.py).

  DELTA BLOCKS (order flow of the desk's own tick archive, flowtab.py; NQ, ES and GC; the aggressor side is an estimate)
        One rule for the four: SHARE = (the series summed over a clock window) / (the volume of that window), completed
        minutes only (a decision at T reads the minutes before T). The window of delta / sweep / bigorder is the last FLOW_WIN
        = 5 minutes; of cumdelta it is the session's anchor (VOL_ANCHOR) to the decision. The SIZE bar is the same window's
        |share| on the 20 trade dates before today (at least 15 of them with volume): a share at or above their median
        (with / against) or above their 80th percentile (with_big / against_big). `with` = the share points the trade's way
        (long needs buyers ahead), `against` = the other way (a fade). No signal (a date without flow rows, fewer than 15
        reference dates, an empty window, a share of exactly 0) blocks the entry on both sides.
  delta       f_delta = with | against | with_big | against_big    series: delta = buy volume - sell volume of the aggressors
  cumdelta    f_cumdelta = ...                                      the same, summed since the session's anchor
  sweep       f_sweep = ...                                         series: buy - sell volume of aggressor orders that walked
                                                                    two price levels or more (their side is certain)
  bigorder    f_bigorder = ...                                      series: the largest aggressor order of each minute, signed
                                                                    by its side (big buys minus big sells)

ib_n = port1.Ib with the range length as an input: ib_min 5 | 15 | 30 | 60 minutes from 09:30 (60 = ib, trade for trade).
"""
from __future__ import annotations

import csv
import os
from multiprocessing import get_context

import numpy as np

import flowtab
import indicators as IND
import l2ref
import levels as LV
import l2sim as S
import ranges as RG
import zones as Z
from l2sim import NS, SESS, _hms

from . import fvg, liq, port1, port2, port3, round1, timed

OPEN = 34200                                        # 09:30 ET, seconds after 00:00
VOL_DAYS = 20                                       # volatility and volume blocks: the 20 trade dates before today
RSI_N = 14
NEWS_TIMES = ("08:30", "10:00")                     # the release groups of cache/events.csv that make a "release day"
BOOK_COLS = ("imb10", "t_utc", "depth10_rel20d", "bid10_rel15", "ask10_rel15", "bid10_chg", "ask10_chg", "depth10",
             "bid_wall_sz", "ask_wall_sz", "bid_wall_dist", "ask_wall_dist", "bid_med_sz", "ask_med_sz")      # what the Level-2 blocks read through ctx.feat
WALL_X, WALL_TICKS = 5.0, 8                         # wall block: a level >= WALL_X x the median level, within WALL_TICKS of the touch
STACK_FRAC = 0.05                                   # stack block: the change of (own side - other side) top-10 size, as a share of the depth
MIN0, NMIN = -360, 1380                             # minute volume: index 0 = 18:00 ET of the evening before .. 17:00 ET
# volume block: where "the session so far" starts -- the Template's anchored-VWAP anchors (asia 00:00, london 03:00, pre 08:25,
# the three NY sessions 09:30, eve 18:00); a family's own session window starts at its own start
NEAR_ATR, CLEAR_ATR = 0.5, 1.0                      # level block: "near" / "clear" in ATRs of the idea's bars
RSI_STRONG, RSI_EXTREME = 10.0, 20.0                 # momentum block: points beyond 50 for strong_with (60 / 40) and extreme_against (30 / 70)
VWMA_N, CH_N, ADX_N = 20, 20, 14                    # vwma length, channel length, ADX length (tf bars)
CH_EDGE = 2.0 / 3.0                                 # channel block: the top third / the bottom third of the channel
ADX_STRONG, ADX_WEAK = 25.0, 20.0                   # adx block
RVOL_DAYS, RVOL_MIN, RVOL_SPIKE = 14, 10, 2.0       # rvol block: the dates compared, the fewest with a tape, the spike multiple
LINE_BLOCKS = ("ema20", "ema50", "vwma", "avwap")   # blocks that compare the close with a line
FLOW_WIN = 5                                        # delta blocks: the minutes of the short window
FLOW_REF, FLOW_REF_MIN = 20, 15                     # ... the trade dates of the size bar, and the fewest of them with volume
FLOW_Q = {"": 0.5, "_big": 0.8}                     # ... the size bar: the median / the 80th percentile of the reference |share|
FLOW_SERIES = {"delta": 1, "cumdelta": 1, "sweep": 2, "bigorder": 3}      # block -> row of flowtab's prefix sums
FLOW_BLOCKS = (*FLOW_SERIES, "deltadiv")            # every block that reads the flow table: its test range ends where the flow file ends
BBW_TIGHT, BBW_WIDE = 0.20, 0.80                    # bbw block: the rank at most / at least
ATRP_HIGH, ATRP_LOW = 0.70, 0.30                    # atrp block
ER_TREND, ER_CHOP = 0.5, 0.25                       # er block
MFI_EXTREME = 30.0                                  # mfi block: points beyond 50 for extreme_against (20 / 80)
DIR_BLOCKS = ("macd", "rsidiv", "deltadiv")         # blocks whose signal is a direction (+1 bullish, -1 bearish): with / against
VOL_ANCHOR = {"asia": 0, "london": 10800, "pre": 30300, "nyam": OPEN, "mid": OPEN, "pm": OPEN, "eve": -21600}

X_STOP_ATR = (1.0, 2.0)                             # the extended menu's new stops and targets
X_STOP_RNG = (0.25, 0.5, 1.0)
X_TGT_R = (1.5, 4.0)

FILTERS = {"volatility": {"high": {"f_dvol": "hi"}, "low": {"f_dvol": "lo"}},
           "momentum": {"with": {"f_rsi": "with"}, "against": {"f_rsi": "against"}, "strong_with": {"f_rsi": "strong_with"},
                        "extreme_against": {"f_rsi": "extreme_against"}},
           "ema20": {"with": {"f_ema20": "with"}, "against": {"f_ema20": "against"}},
           "ema50": {"with": {"f_ema50": "with"}, "against": {"f_ema50": "against"}},
           "trend": {"with": {"f_trend": "with"}, "against": {"f_trend": "against"}},
           "vwap": {"with": {"f_vwap": "with"}, "against": {"f_vwap": "against"}},
           "avwap": {"with": {"f_avwap": "with"}, "against": {"f_avwap": "against"}},
           "vwma": {"with": {"f_vwma": "with"}, "against": {"f_vwma": "against"}},
           "channel": {"with": {"f_channel": "with"}, "against": {"f_channel": "against"}},
           "adx": {"strong": {"f_adx": "strong"}, "weak": {"f_adx": "weak"}},
           "level": {"near": {"f_level": "near"}, "clear": {"f_level": "clear"}},
           "swept": {"with": {"f_swept": "with"}, "against": {"f_swept": "against"}},
           "pdz": {"with": {"f_pdz": "with"}, "against": {"f_pdz": "against"}},
           "ote": {"in": {"f_ote": "in"}, "out": {"f_ote": "out"}},
           "htf15": {"with": {"f_htf15": "with"}, "against": {"f_htf15": "against"}},
           "htf60": {"with": {"f_htf60": "with"}, "against": {"f_htf60": "against"}},
           "smt": {"agree": {"f_smt": "agree"}, "disagree": {"f_smt": "disagree"}},
           **{f"pdz_{k}": {"with": {f"f_pdz_{k}": "with"}, "against": {f"f_pdz_{k}": "against"}} for k in RG.KINDS},
           **{f"ote_{k}": {"in": {f"f_ote_{k}": "in"}, "out": {f"f_ote_{k}": "out"}} for k in RG.KINDS},
           "rvol": {"high": {"f_rvol": "high"}, "low": {"f_rvol": "low"}, "spike": {"f_rvol": "spike"}},
           "volume": {"high": {"f_cvol": "hi"}, "low": {"f_cvol": "lo"}},
           "news": {"yes": {"f_news": "yes"}, "no": {"f_news": "no"}},
           "book": {"agree": {"f_book": "on"}, "disagree": {"f_bookopp": "on"}},
           "depth": {"thin": {"f_depth": "thin"}, "thick": {"f_depth": "thick"}},
           "ahead": {"thin": {"f_ahead": "thin"}, "thick": {"f_ahead": "thick"}},
           "wall": {"clear": {"f_wall": "clear"}, "blocked": {"f_wall": "blocked"}},
           "stack": {"with": {"f_stack": "with"}, "against": {"f_stack": "against"}},
           "bbw": {"tight": {"f_bbw": "tight"}, "wide": {"f_bbw": "wide"}},
           "atrp": {"high": {"f_atrp": "high"}, "low": {"f_atrp": "low"}},
           "er": {"trend": {"f_er": "trend"}, "chop": {"f_er": "chop"}},
           "macd": {"with": {"f_macd": "with"}, "against": {"f_macd": "against"}},
           "rsidiv": {"with": {"f_rsidiv": "with"}, "against": {"f_rsidiv": "against"}},
           "mfi": {"with": {"f_mfi": "with"}, "against": {"f_mfi": "against"}, "extreme_against": {"f_mfi": "extreme_against"}},
           "deltadiv": {"with": {"f_deltadiv": "with"}, "against": {"f_deltadiv": "against"}},
           "candle": {"displace": {"f_candle": "displace"}, "engulf": {"f_candle": "engulf"}, "reject": {"f_candle": "reject"}},
           **{blk: {side: {f"f_{blk}": side} for side in ("with", "against", "with_big", "against_big")} for blk in FLOW_SERIES}}
L2_BLOCKS = ("book", "depth", "ahead", "wall", "stack")      # NQ only: they read the Level-2 feature table
BLOCK_MARKETS = {"smt": ("NQ", "ES"), **{b: ("NQ",) for b in Z.RANGE_BLOCKS}}                        # the other blocks that are not for all three markets (SMT compares NQ with ES)
PLAIN = {("volatility", "high"): "only after a day whose range was above its own 20-day median",
         ("volatility", "low"): "only after a day whose range was at or below its own 20-day median",
         ("momentum", "with"): "only when RSI(14) on the idea's bars points the trade's way (long above 50, short below 50)",
         ("momentum", "against"): "only when RSI(14) on the idea's bars points against the trade (long below 50, short above 50)",
         ("volume", "high"): "only when the session's volume so far is above its 20-day median for that time of day",
         ("volume", "low"): "only when the session's volume so far is below its 20-day median for that time of day",
         ("news", "yes"): "only on days with an 08:30 or 10:00 ET US data release",
         ("news", "no"): "never on days with an 08:30 or 10:00 ET US data release",
         ("book", "agree"): "only when the top-10 order book leans the trade's way (5-minute mean imbalance)",
         ("book", "disagree"): "only when the top-10 order book leans against the trade (5-minute mean imbalance)"}
PLAIN.update({("level", "near"): "only when the close is within half an ATR of a liquidity level (prior day, overnight, Asia, London, the evening before, 5 days, the swing high / low, equal highs / lows on NQ)",
              ("level", "clear"): "only when the close is more than one ATR from every liquidity level",
              ("swept", "with"): "only when liquidity on the other side was taken today (a long after a level low was swept, a short after a level high)",
              ("swept", "against"): "only when liquidity on the trade's own side was taken today (a long after a level high was swept, a short after a level low)"})
PLAIN.update({("momentum", "strong_with"): "only when RSI(14) is strongly with the trade (a long needs RSI at least 60, a short at most 40)",
              ("momentum", "extreme_against"): "only when RSI(14) is at an extreme against the trade (a long needs RSI at most 30, a short at least 70)",
              ("adx", "strong"): "only when the trend is strong: Wilder's ADX(14) on the idea's bars is at least 25",
              ("adx", "weak"): "only when there is no trend: Wilder's ADX(14) on the idea's bars is below 20",
              ("rvol", "high"): "only when the bar that just closed has more volume than the median of the same clock bar over the 14 days before",
              ("rvol", "low"): "only when the bar that just closed has less volume than the median of the same clock bar over the 14 days before",
              ("rvol", "spike"): "only when the bar that just closed has at least twice the median volume of the same clock bar over the 14 days before",
              ("trend", "with"): "only when the slope of the EMA(50) of the idea's bars points the trade's way (a long needs it rising)",
              ("trend", "against"): "only when the slope of the EMA(50) of the idea's bars points against the trade",
              ("vwap", "with"): "only when the close is on the trade's side of the session's volume-weighted average price (a long needs it above)",
              ("vwap", "against"): "only when the close is on the other side of the session's volume-weighted average price",
              ("avwap", "with"): "only when the close is on the trade's side of the VWAP anchored at the day's anchor (09:30 for the New York sessions)",
              ("avwap", "against"): "only when the close is on the other side of the VWAP anchored at the day's anchor (09:30 for the New York sessions)",
              ("vwma", "with"): "only when the close is on the trade's side of the 20-bar volume-weighted moving average (a long needs it above)",
              ("vwma", "against"): "only when the close is on the other side of the 20-bar volume-weighted moving average",
              ("channel", "with"): "only when the close sits in the trade's third of the 20-bar channel (a long in the top third, a short in the bottom third)",
              ("channel", "against"): "only when the close sits in the opposite third of the 20-bar channel (a dip bought, a rally sold)"})
PLAIN.update({("pdz", "with"): "only when the close is cheap for the trade inside the day's range so far (a long in the lower half, a short in the upper half)",
              ("pdz", "against"): "only when the close is dear for the trade inside the day's range so far (a long in the upper half, a short in the lower half)",
              ("ote", "in"): "only when the close is in the 62-79 % retracement zone of the day's range leg that points the trade's way",
              ("ote", "out"): "only when the day's range leg points the trade's way and the close is NOT in its 62-79 % retracement zone",
              ("htf15", "with"): "only when the 15-minute trend points the trade's way (the last 15-minute close above its EMA(20) for a long)",
              ("htf15", "against"): "only when the 15-minute trend points against the trade (EMA(20) of 15-minute closes)",
              ("htf60", "with"): "only when the 60-minute trend points the trade's way (the last 60-minute close above its EMA(8) for a long)",
              ("htf60", "against"): "only when the 60-minute trend points against the trade (EMA(8) of 60-minute closes)",
              ("smt", "agree"): "only when NQ and ES diverge at a new extreme in the trade's favour (a long after exactly one made a new 3-hour low, a short after one made a new high)",
              ("smt", "disagree"): "only when NQ and ES diverge at a new extreme against the trade (a long after exactly one made a new high)"})
for _k, _w in RG.WORDS.items():
    PLAIN.update({(f"pdz_{_k}", "with"): f"only when the close is cheap for the trade inside {_w} (a long in the lower half, a short in the upper half)",
                  (f"pdz_{_k}", "against"): f"only when the close is dear for the trade inside {_w} (a long in the upper half, a short in the lower half)",
                  (f"ote_{_k}", "in"): f"only when the close is in the 62-79 % retracement zone of {_w}, a leg that points the trade's way",
                  (f"ote_{_k}", "out"): f"only when {_w} points the trade's way and the close is NOT in its 62-79 % retracement zone"})
for _n in (20, 50):
    PLAIN[(f"ema{_n}", "with")] = f"only when the close is on the trade's side of the EMA({_n}) of the idea's bars (a long needs it above)"
    PLAIN[(f"ema{_n}", "against")] = f"only when the close is on the other side of the EMA({_n}) of the idea's bars"
PLAIN.update({("depth", "thin"): "only when the top-10 book is thin: its depth is at most 80 % of its median at that minute over the 20 sessions before",
              ("depth", "thick"): "only when the top-10 book is thick: its depth is at least 120 % of its median at that minute over the 20 sessions before",
              ("ahead", "thin"): "only when the resting size the trade must push through (offers for a long, bids for a short) is at most 80 % of its own 15-minute median",
              ("ahead", "thick"): "only when the resting size the trade must push through is above 80 % of its own 15-minute median",
              ("wall", "clear"): "only when no wall stands ahead: no level of the opposing top 10 holds 5 times the median level within 8 ticks of the touch",
              ("wall", "blocked"): "only when a wall stands ahead: a level of the opposing top 10 holds 5 times the median level within 8 ticks of the touch",
              ("stack", "with"): "only when, in the last minute, top-10 size was added on the trade's side (or pulled on the other) by at least 5 % of the depth",
              ("stack", "against"): "only when, in the last minute, top-10 size was added on the other side (or pulled on the trade's) by at least 5 % of the depth"})
PLAIN.update({("bbw", "tight"): "only when the Bollinger bands (20 bars, 2 sigma) are tight: their width is in the lowest fifth of its last 120 values",
              ("bbw", "wide"): "only when the Bollinger bands (20 bars, 2 sigma) are wide: their width is in the highest fifth of its last 120 values",
              ("atrp", "high"): "only when volatility is high: the ATR(14) of the idea's bars is in the top 30 % of its last 100 values",
              ("atrp", "low"): "only when volatility is low: the ATR(14) of the idea's bars is in the bottom 30 % of its last 100 values",
              ("er", "trend"): "only when price moves in a line: the efficiency ratio of the last 14 bars (net change / path travelled) is at least 0.5",
              ("er", "chop"): "only when price chops: the efficiency ratio of the last 14 bars (net change / path travelled) is at most 0.25",
              ("macd", "with"): "only when the MACD(12, 26, 9) histogram points the trade's way and is not weakening (a long needs it above 0 and not below the bar before)",
              ("macd", "against"): "only when the MACD(12, 26, 9) histogram points against the trade and is not weakening (a long needs it below 0 and not above the bar before)",
              ("rsidiv", "with"): "only when RSI(14) diverges in the trade's favour (a long: a new 20-bar low with a higher RSI than at the earlier low; a short the mirror)",
              ("rsidiv", "against"): "only when RSI(14) diverges against the trade (a long: a new 20-bar high with a lower RSI than at the earlier high)",
              ("mfi", "with"): "only when the Money Flow Index (14 bars) is on the trade's side of 50 (a long needs it above 50)",
              ("mfi", "against"): "only when the Money Flow Index (14 bars) is on the other side of 50 (a long needs it below 50)",
              ("mfi", "extreme_against"): "only when the Money Flow Index (14 bars) is at an extreme against the trade (a long needs it at most 20, a short at least 80)",
              ("deltadiv", "with"): "only when price and net buying volume disagree in the trade's favour over the last 20 bars (a long: price fell while net delta is positive)",
              ("deltadiv", "against"): "only when price and net buying volume disagree against the trade over the last 20 bars (a long: price rose while net delta is negative)",
              ("candle", "displace"): "only when the signal bar is a strong push the trade's way: body at least 1.5 ATR and the close in the outer quarter of its range",
              ("candle", "engulf"): "only when the signal bar's body engulfs the previous bar's body, in the opposite colour and the trade's direction",
              ("candle", "reject"): "only when the signal bar shows a rejection wick on the trade's side: at least twice its body (a long: the lower wick)"})
_WHAT = {"delta": ("net buying volume of the last 5 minutes", "buy volume minus sell volume of the aggressors"),
         "cumdelta": ("net buying volume since the session's anchor", "buy minus sell volume of the aggressors since 09:30 (the session's anchor)"),
         "sweep": ("net sweep volume of the last 5 minutes", "buy minus sell volume of orders that walked two price levels or more"),
         "bigorder": ("the biggest orders of the last 5 minutes", "the largest aggressor order of each minute, big buys minus big sells")}
for _b, (_nm, _how) in _WHAT.items():
    for _side, _dir in (("with", "points the trade's way (long needs buyers ahead, short sellers)"), ("against", "points against the trade (a fade)")):
        for _sfx, _bar in (("", "at least its 20-day median for that window"), ("_big", "above the 80th percentile of its 20 days for that window")):
            PLAIN[(_b, _side + _sfx)] = f"only when {_nm} {_dir} and its share of volume is {_bar}"


# ---- the menu ---------------------------------------------------------------------------------------------------------------
def menu_extended(root: str, rng: bool = True) -> list:
    """The EXTENDED exit menu of `root` (module docstring): the 32 standard cells, then the cells with a new target or a new
    stop. rng False (a family without a structure) leaves the range stops out. Cells shared by both forms keep their index."""
    stops = S.menu_stops(root)
    new = [{"stop_mode": "atr", "stop_val": v} for v in X_STOP_ATR]
    if rng:
        new += [{"stop_mode": "rng", "stop_val": v} for v in X_STOP_RNG]
    return (S.menu(root) + [{**st, "tgt_r": r} for st in stops for r in X_TGT_R]
            + [{**st, "tgt_r": r} for st in new for r in S.MENU_TGT_R + X_TGT_R])


BP_TGT_R = (0.5, 0.75)                              # the blueprint's small targets (BLUEPRINT.md version 1.1, the owner 2026-10-06)


def menu_blueprint(root: str) -> list:
    """THE EXIT TABLE OF THE BLUEPRINT (BLUEPRINT.md section 2; blueprint/templates/exit_menu.json): the 32 standard cells
    first (same order, same ids: a store of the 32 keeps its cells), then the 8 standard stops x the targets 0.5 and 0.75 x
    the stop = 48 cells, every one judged like the others."""
    return S.menu(root) + [{**st, "tgt_r": r} for st in S.menu_stops(root) for r in BP_TGT_R]


def exits(kind: str, root: str, family: str) -> list:
    """The exit cells of an idea: 'standard' = l2sim.menu(root); 'extended' = menu_extended (range stops only when the
    family has a structure); 'blueprint' = menu_blueprint (what a blueprint build runs: blueprint/runner.py)."""
    if kind == "standard":
        return S.menu(root)
    if kind == "extended":
        return menu_extended(root, rng=family in HEIGHTS)
    if kind == "blueprint":
        return menu_blueprint(root)
    raise ValueError(f"exits {kind!r}: 'standard', 'extended' or 'blueprint'")


COMBO, MAX_FILTERS = "+", 2                         # a unit may hold several filters at once: ("ote+pdz", "in+with"); at most 2 (BLUEPRINT.md 0.2)


def parts(filt) -> list:
    """The (block, side) pairs of a filter given as a pair, a combined pair or the string "block_side" (None / "" -> [])."""
    if not filt:
        return []
    b, s = filt.split("_", 1) if isinstance(filt, str) else filt
    return list(zip(b.split(COMBO), s.split(COMBO)))


def reads(filt, which) -> bool:
    """Does any filter of the unit belong to `which` (a collection of block names)?"""
    return any(b in which for b, _ in parts(filt))


def combine(filters) -> tuple:
    """Several (block, side) pairs -> ONE combined pair, blocks sorted by name so the same two filters always give the same unit."""
    fs = sorted(filters)
    return (COMBO.join(b for b, _ in fs), COMBO.join(s for _, s in fs)) if len(fs) > 1 else tuple(fs[0])


def plain(filt) -> str:
    """The plain words of a (combined) filter: each part's sentence, joined with ' AND '."""
    return " AND ".join(PLAIN[p] for p in parts(filt))


def filter_inputs(block: str, side: str, root: str = "NQ") -> dict:
    """The inputs that switch ONE filter block on, on one of its two sides -- or, for a combined pair, every part's inputs together."""
    if COMBO in block or COMBO in side:
        ps = parts((block, side))
        if len(ps) > MAX_FILTERS or len({b for b, _ in ps}) < len(ps) or len(block.split(COMBO)) != len(side.split(COMBO)):
            raise ValueError(f"filter {block!r} / {side!r}: at most {MAX_FILTERS} different blocks, one side each")
        return {k: v for b, sd in ps for k, v in filter_inputs(b, sd, root).items()}
    if block not in FILTERS or side not in FILTERS[block]:
        raise ValueError(f"filter {block!r} / {side!r}: blocks and sides are {({b: tuple(s) for b, s in FILTERS.items()})}")
    if block in L2_BLOCKS and root not in S.L2_ROOTS:
        raise ValueError(f"the {block} block reads Level 2: {sorted(S.L2_ROOTS)} only, not {root}")
    return dict(FILTERS[block][side])


# ---- volatility: the prior day's range against its own 20-day median ------------------------------------------------------------
def day_vol(rows: list, iso: str):
    """'hi' | 'lo' | None for trade date `iso` from daily bars [{date, h, l, ...}] ascending: ONLY rows dated before `iso`
    are read. hi = the last such bar's range is above the median of the last 20 such ranges (itself included); lo = not
    above; None with fewer than 20."""
    j = len(rows)
    while j and rows[j - 1]["date"] >= iso:           # the engine hands bars dated < iso only; a longer list is cut here
        j -= 1
    if j < VOL_DAYS:
        return None
    rng = [rows[k]["h"] - rows[k]["l"] for k in range(j - VOL_DAYS, j)]
    return "hi" if rng[-1] > float(np.median(rng)) else "lo"


# ---- momentum: Wilder RSI ---------------------------------------------------------------------------------------------------------
def rsi(closes, n: int = RSI_N):
    """Wilder RSI(n) at the last of `closes` (closed bars, oldest first): the first average gain / loss = the mean of the
    first n changes, then Wilder smoothing. None with fewer than n + 1 closes; 50 when nothing has moved."""
    if len(closes) < n + 1:
        return None
    g = l = 0.0
    for i in range(1, n + 1):
        d = closes[i] - closes[i - 1]
        if d > 0:
            g += d
        else:
            l -= d
    g /= n
    l /= n
    for i in range(n + 1, len(closes)):
        d = closes[i] - closes[i - 1]
        g = (g * (n - 1) + (d if d > 0 else 0.0)) / n
        l = (l * (n - 1) + (-d if d < 0 else 0.0)) / n
    return 50.0 if g + l == 0 else 100.0 * g / (g + l)


# ---- price-and-trend lines ---------------------------------------------------------------------------------------------------
def ema_last(closes, n: int):
    """The EMA(n) of `closes` at the last one, seeded with the first close (the Template's own EMA rule), or None before n closes."""
    if len(closes) < n:
        return None
    e, k = None, 2.0 / (n + 1)
    for c in closes:
        e = c if e is None else e + k * (c - e)
    return e


def vwma_last(closes, vols, n: int = VWMA_N):
    """sum(close x volume) / sum(volume) over the last n bars, or None (fewer than n bars, or no volume)."""
    if len(closes) < n:
        return None
    v = sum(vols[-n:])
    return None if v <= 0 else sum(c * w for c, w in zip(closes[-n:], vols[-n:])) / v


def _dx(tr: float, p: float, m: float) -> float:
    if tr <= 0:
        return 0.0
    pi, mi = 100.0 * p / tr, 100.0 * m / tr
    return 0.0 if pi + mi == 0 else 100.0 * abs(pi - mi) / (pi + mi)


def adx_last(H, L, C, n: int = ADX_N):
    """Wilder's ADX(n) at the last bar (+DM / -DM / TR summed over n and then smoothed s - s / n + x; ADX = the mean of the first n
    DX, then (ADX x (n - 1) + DX) / n), or None with fewer than 2 n bars."""
    N = len(C)
    if N < 2 * n:
        return None
    tr, pdm, mdm = [], [], []
    for i in range(1, N):
        up, dn = H[i] - H[i - 1], L[i - 1] - L[i]
        pdm.append(up if up > dn and up > 0 else 0.0)
        mdm.append(dn if dn > up and dn > 0 else 0.0)
        tr.append(max(H[i] - L[i], abs(H[i] - C[i - 1]), abs(L[i] - C[i - 1])))
    s_tr, s_p, s_m = sum(tr[:n]), sum(pdm[:n]), sum(mdm[:n])
    dxs = [_dx(s_tr, s_p, s_m)]
    for i in range(n, len(tr)):
        s_tr += tr[i] - s_tr / n
        s_p += pdm[i] - s_p / n
        s_m += mdm[i] - s_m / n
        dxs.append(_dx(s_tr, s_p, s_m))
    a = sum(dxs[:n]) / n
    for x in dxs[n:]:
        a = (a * (n - 1) + x) / n
    return a


# ---- volume: the minute-volume profile of the prior days -----------------------------------------------------------------------
_MV_FILE: dict = {}                                 # root -> ({iso: row}, int64 [dates, NMIN])      read once per process
_CUM: dict = {}                                     # (root, iso) -> int64 [NMIN + 1] prefix sums, or None (no tape)


def minute_volume(tape) -> np.ndarray:
    """Volume per ET clock minute of a tape's Globex day: int64 [NMIN], index 0 = 18:00 ET of the evening before the
    trade date (the same minutes, and the same sums, as the engine's 1-minute bars)."""
    k = (tape.ts - S.et_ns(tape.date, "00:00")) // S.MIN_NS - MIN0
    ok = (k >= 0) & (k < NMIN)
    return np.bincount(k[ok], weights=tape.size[ok], minlength=NMIN).astype(np.int64)


def _mv_path(root: str):
    return S.CACHE / f"minvol_{root}.npz"


def _mv_file(root: str) -> tuple:
    if root not in _MV_FILE:
        p = _mv_path(root)
        if p.exists():
            z = np.load(p)
            _MV_FILE[root] = ({d: i for i, d in enumerate(z["dates"].tolist())}, z["vol"])
        else:
            _MV_FILE[root] = ({}, np.zeros((0, NMIN), np.int64))
    return _MV_FILE[root]


def cum_volume(root: str, iso: str):
    """Prefix sums [NMIN + 1] of trade date `iso`'s minute volume: the cache file when it holds the date, else from the tape
    (None when the date has none; a 2025+ date raises HoldoutSealed in load_tape). Remembered per process."""
    key = (root, iso)
    if key not in _CUM:
        idx, vol = _mv_file(root)
        if iso in idx:
            v = vol[idx[iso]]
        else:
            t = S.load_tape(iso, root)
            v = None if t is None or not len(t.ts) else minute_volume(t)
        _CUM[key] = None if v is None else np.concatenate(([0], np.cumsum(v, dtype=np.int64)))
    return _CUM[key]


def cum_ref(root: str, dates: list, a: int, b: int):
    """Median over `dates` (the 20 trade dates before today, from the daily bars) of the volume traded in the clock window
    [a, b) -- seconds after 00:00 ET of each date, whole minutes. None: fewer than 20 dates, one without a tape, or an empty /
    out-of-day window."""
    i, j = a // 60 - MIN0, b // 60 - MIN0
    if len(dates) < VOL_DAYS or not 0 <= i < j <= NMIN:
        return None
    vals = []
    for iso in dates[-VOL_DAYS:]:
        c = cum_volume(root, iso)
        if c is None:
            return None
        vals.append(int(c[j] - c[i]))
    return float(np.median(vals))


def _mv_one(args):
    iso, root, allow = args
    S.wait_compute_window()
    t = S.load_tape(iso, root, **allow)
    return iso, (None if t is None or not len(t.ts) else minute_volume(t))


def build_minvol(root: str, period: str = "build", workers: int = 1, **allow) -> dict:
    """Fill cache/minvol_<root>.npz with the minute volume of every session of `period` (default BUILD: nothing else is
    read) the file does not hold yet. -> {'path', 'dates', 'added'}. run_idea calls it before a volume-block pass; a worker
    that misses a date computes it from that date's tape with the same function -- WITHOUT a seal switch, so a sealed
    date that is not in the file stops the run (HoldoutSealed). `allow`: the engine's own seal switch of the stage that
    opens a later period (handed to l2sim.sessions / load_tape unchanged, e.g. allow_check=True); never set here."""
    p = _mv_path(root)
    _MV_FILE.pop(root, None)
    idx, vol = _mv_file(root)
    a, b = S.period(period)
    todo = [(d.isoformat(), root, allow) for d in S.sessions(a, b, root, **allow)
            if d.isoformat() not in idx and (root == "NQ" or S.hb_tape_path(d, root) is not None)]
    if todo:
        workers = max(1, min(int(workers), S.MAX_WORKERS))
        S.wait_compute_window()
        if workers == 1 or not S.pool_usable():
            res = [_mv_one(x) for x in todo]
        else:
            with get_context("spawn").Pool(workers) as pool:
                res = pool.map(_mv_one, todo, chunksize=16)
        have = {d: vol[i] for d, i in idx.items()}
        have.update({d: v for d, v in res if v is not None})
        dates = sorted(have)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_name(f".{p.stem}.{os.getpid()}.tmp.npz")
        np.savez_compressed(tmp, dates=np.array(dates), vol=np.stack([have[d] for d in dates]) if dates else vol)
        os.replace(tmp, p)
        _MV_FILE.pop(root, None)
        for d, _, _ in todo:
            _CUM.pop((root, d), None)
    return {"path": str(p), "dates": len(_mv_file(root)[0]), "added": len(todo)}


# ---- news: release days ---------------------------------------------------------------------------------------------------------
_NEWS: list = []


def release_days() -> frozenset:
    """ISO dates with a calendar row at 08:30 or 10:00 ET (cache/events.csv: official release schedules, never checked
    against the tape). Read once per process."""
    if not _NEWS:
        with (S.CACHE / "events.csv").open(newline="") as fh:
            _NEWS.append(frozenset(r["date"] for r in csv.DictReader(fh) if r["time_et"] in NEWS_TIMES))
    return _NEWS[0]


# ---- the structure heights (stop_mode = "rng") ---------------------------------------------------------------------------------
def _now_s(st) -> int:
    """Seconds after 00:00 ET of the trade date at this decision."""
    return (st._cx.now_ns - st.t0) // NS


def _range_after(st, a: int, b: int):
    """High - low of the completed 1-minute bars in [a, b), once the window has ended; else None."""
    if _now_s(st) < b:
        return None
    r = st.rng(a, b)
    return None if r is None else r[0] - r[1]


def _h_orb(st):
    if st.sid is None:
        return None
    a = st.S[st.sid][0]
    return _range_after(st, a, a + int(st.p["or_min"]) * 60)


def _h_orb_confirm(st):
    return _range_after(st, OPEN, OPEN + int(st.p["or_min"]) * 60)


def _h_ib(st):
    return _range_after(st, OPEN, OPEN + int(st.p.get("ib_min", "60")) * 60)


def _h_lon(st):
    return _range_after(st, 10800, 30300)


def _channel(st, n: int):
    return max(st.H[-n - 1:-1]) - min(st.L[-n - 1:-1]) if st.nb > n else None


def _h_donchian(st):
    return _channel(st, int(st.p["n"]))


def _h_spike(st):
    return _channel(st, round1.VolSpikeBreak.N)


def _h_bar(st):
    return st.H[-1] - st.L[-1] if st.nb else None


# family -> (the structure in plain words, height function, the family inputs the function reads)
HEIGHTS = {"orb": ("the opening range: the first or_min minutes of the session", _h_orb, ("or_min",)),
           "orb_confirm": ("the opening range: the first or_min minutes from 09:30", _h_orb_confirm, ("or_min",)),
           "ib": ("the initial balance 09:30-10:30", _h_ib, ()),
           "ib_n": ("the opening range: the first ib_min minutes from 09:30", _h_ib, ("ib_min",)),
           "lon_break": ("the London range 03:00-08:25", _h_lon, ()),
           "donchian": ("the channel: the n bars before the signal bar", _h_donchian, ("n",)),
           "vol_spike_break": ("the channel: the 20 bars before the signal bar", _h_spike, ()),
           "first_bar_mom": ("the signal bar's range", _h_bar, ())}


# ---- the mixin ------------------------------------------------------------------------------------------------------------------
class Blocks:
    """The blocks, in front of a family class (module docstring). All default off: the family is then unchanged."""
    DEFAULTS = {"f_dvol": "off", "f_rsi": "off", "f_cvol": "off", "f_news": "off", "f_bookopp": "off",
                "f_ahead": "off", "f_wall": "off", "f_stack": "off",
                "f_level": "off", "f_swept": "off", "f_ema20": "off", "f_ema50": "off", "f_vwma": "off", "f_avwap": "off", "f_channel": "off", "f_adx": "off", "f_rvol": "off",
                "f_pdz": "off", "f_ote": "off", "f_htf15": "off", "f_htf60": "off", "f_smt": "off",
                **{f"f_pdz_{k}": "off" for k in RG.KINDS}, **{f"f_ote_{k}": "off" for k in RG.KINDS},
                "f_bbw": "off", "f_atrp": "off", "f_er": "off", "f_macd": "off", "f_rsidiv": "off", "f_mfi": "off", "f_deltadiv": "off", "f_candle": "off",
                **{f"f_{b}": "off" for b in FLOW_SERIES}}
    SCHEMA = {"stop_mode": ("choice", ("atr", "pts", "struct", "pct", "rng")),
              "f_dvol": ("choice", ("off", "hi", "lo")), "f_rsi": ("choice", ("off", "with", "against", "strong_with", "extreme_against")),
              "f_cvol": ("choice", ("off", "hi", "lo")), "f_news": ("choice", ("off", "yes", "no")),
              "f_bookopp": ("choice", ("off", "on")), "f_ahead": ("choice", ("off", "thin", "thick")),
              "f_wall": ("choice", ("off", "clear", "blocked")), "f_stack": ("choice", ("off", "with", "against")),
              **{f"f_{b}": ("choice", ("off", "with", "against")) for b in ("ema20", "ema50", "vwma", "avwap", "channel")},
              "f_level": ("choice", ("off", "near", "clear")), "f_swept": ("choice", ("off", "with", "against")),
              "f_adx": ("choice", ("off", "strong", "weak")), "f_rvol": ("choice", ("off", "high", "low", "spike")),
              "f_pdz": ("choice", ("off", "with", "against")), "f_ote": ("choice", ("off", "in", "out")),
              "f_htf15": ("choice", ("off", "with", "against")), "f_htf60": ("choice", ("off", "with", "against")),
              "f_smt": ("choice", ("off", "agree", "disagree")),
              **{f"f_pdz_{k}": ("choice", ("off", "with", "against")) for k in RG.KINDS}, **{f"f_ote_{k}": ("choice", ("off", "in", "out")) for k in RG.KINDS},
              "f_bbw": ("choice", ("off", "tight", "wide")), "f_atrp": ("choice", ("off", "high", "low")), "f_er": ("choice", ("off", "trend", "chop")),
              "f_mfi": ("choice", ("off", "with", "against", "extreme_against")), "f_candle": ("choice", ("off", "displace", "engulf", "reject")),
              **{f"f_{b}": ("choice", ("off", "with", "against")) for b in DIR_BLOCKS},
              **{f"f_{b}": ("choice", ("off", "with", "against", "with_big", "against_big")) for b in FLOW_SERIES}}
    BASE = None                                     # the family name the class was built for
    STRUCT = None                                   # its structure in plain words; None = it has none

    def __init__(self, params: dict | None = None):
        super().__init__(params)
        if self.p["stop_mode"] == "rng" and self.STRUCT is None:
            raise ValueError(f"stop_mode='rng' needs a structure (an opening range, a channel, a signal bar): {self.BASE or type(self).__name__} "
                             f"has none; families with one: {sorted(HEIGHTS)}")
        if self.p["f_book"] != "off" and self.p["f_bookopp"] != "off":
            raise ValueError("f_book (agree) and f_bookopp (disagree) are the two sides of ONE block: switch on one")

    def height(self):
        """The structure height at this decision (HEIGHTS), or None."""
        return None

    def blk_height(self):
        h = self.height()
        return h if h is not None and h > 0 else None

    def blk_session_volume(self):
        """(a, b, volume): the session's ANCHOR second (VOL_ANCHOR), this decision's second (both after 00:00 ET of the
        trade date) and the volume of the COMPLETED 1-minute bars inside [a, b); None outside a session."""
        if self.sid is None:
            return None
        a, b = VOL_ANCHOR.get(self.sid, self.S[self.sid][0]), _now_s(self)
        return a, b, sum(m[5] for m in self.M if a <= m[0] and m[0] + 60 <= b)

    def blk_cvol(self):
        """'hi' | 'lo' | None: the session's volume so far against the 20-day median of the same clock window."""
        sv = self.blk_session_volume()
        if sv is None:
            return None
        a, b, today = sv
        ref = cum_ref(self._cx.root, [r["date"] for r in self.dl[-VOL_DAYS:]], a, b)
        if ref is None or today == ref:
            return None
        return "hi" if today > ref else "lo"

    def blk_flow(self, block: str):
        """The delta blocks' signal at this decision: (share today, the 50th and the 80th percentile of |share| on the 20 dates
        before today) or None = no signal (module docstring, DELTA BLOCKS). share = the series over its window / the volume of
        the same window; delta / sweep / bigorder read the last FLOW_WIN minutes, cumdelta the minutes since the session's anchor."""
        if self.sid is None:
            return None
        b = _now_s(self) // 60 * 60                                 # completed minutes only
        a = VOL_ANCHOR.get(self.sid, self.S[self.sid][0]) if block == "cumdelta" else b - FLOW_WIN * 60
        row, root = FLOW_SERIES[block], self._cx.root

        def share(iso):
            w = flowtab.window(root, iso, a, b)
            return None if w is None or w[0] <= 0 else w[row] / w[0]
        x = share(self.day)
        if x is None:
            return None
        ref = [abs(v) for v in (share(r["date"]) for r in self.dl[-FLOW_REF:]) if v is not None]
        if len(ref) < FLOW_REF_MIN:
            return None
        return x, float(np.quantile(ref, FLOW_Q[""])), float(np.quantile(ref, FLOW_Q["_big"]))

    def blk_deltadiv(self):
        """+1 | -1 | None: the close of the last IND.DIV_N tf bars against the net delta of the same clock window (whole minutes before
        the decision, from the flow table); None outside a session, with too few bars, no flow row for today, or no volume in the window."""
        if self.sid is None or self.nb < IND.DIV_N + 1:
            return None
        b = _now_s(self) // 60 * 60
        w = flowtab.window(self._cx.root, self.day, b - IND.DIV_N * self.tf * 60, b)
        return None if w is None or w[0] <= 0 else IND.delta_div(self.C[-1] - self.C[-IND.DIV_N - 1], w[1])

    def blk_dir(self, block: str):
        """The direction signal (+1 bullish, -1 bearish, None) of a DIR_BLOCKS block."""
        if block == "macd":
            return IND.macd_dir(self.C)
        if block == "rsidiv":
            return IND.rsidiv(self.H, self.L, lambda i: rsi(self.C[:i + 1]))
        return self.blk_deltadiv()

    def on_session(self, ctx):
        super().on_session(ctx)
        self._swept = {"hi": False, "lo": False}                     # swept block: liquidity taken since 00:00 ET of this trade date

    def fam_update(self, ctx):
        super().fam_update(ctx)
        if self.p["f_swept"] != "off":
            LV.track(self)

    def blk_line(self, block: str):
        """The line a LINE_BLOCKS block compares the close with, or None."""
        if block == "ema20":
            return ema_last(self.C, 20)
        if block == "ema50":
            return ema_last(self.C, 50)
        if block == "vwma":
            return vwma_last(self.C, self.V)
        w = self.vwr()                                              # avwap: anchored at the day's anchor (the Template's rth VWAP)
        return None if w is None else w[0]

    def blk_channel(self):
        """The close's position in the channel of the CH_N bars before the signal bar ((close - low) / (high - low); it may lie
        outside 0..1), or None."""
        if self.nb < CH_N + 1:
            return None
        hi, lo = max(self.H[-CH_N - 1:-1]), min(self.L[-CH_N - 1:-1])
        return None if hi <= lo else (self.C[-1] - lo) / (hi - lo)

    def blk_rvol(self):
        """(the volume of the tf bar that just closed, the median volume of the same clock bar on the RVOL_DAYS dates before today)
        or None: outside a session, fewer than RVOL_MIN dates with a tape, or a median of 0."""
        if self.sid is None:
            return None
        b = _now_s(self) // 60 * 60
        a = b - self.tf * 60
        i, j = a // 60 - MIN0, b // 60 - MIN0
        if not 0 <= i < j <= NMIN:
            return None
        today = sum(m[5] for m in self.M if a <= m[0] and m[0] + 60 <= b)
        ref = []
        for r in self.dl[-RVOL_DAYS:]:
            c = cum_volume(self._cx.root, r["date"])
            if c is not None:
                ref.append(int(c[j] - c[i]))
        if len(ref) < RVOL_MIN:
            return None
        med = float(np.median(ref))
        return None if med <= 0 else (float(today), med)

    def blk_wall(self, sd: int):
        """True = a wall stands ahead (the opposing top 10 holds a level >= WALL_X x its median level within WALL_TICKS of the
        touch), False = none, None = no signal (no fresh valid book)."""
        cx = self._cx
        if not S.feat_fresh(cx):
            return None
        side = "ask" if sd > 0 else "bid"
        sz, med, dist = (cx.feat(f"{side}_{c}") for c in ("wall_sz", "med_sz", "wall_dist"))
        if any(v is None or v != v for v in (sz, med, dist)) or med <= 0:
            return None
        return bool(sz >= WALL_X * med and dist <= WALL_TICKS)

    def blk_stack(self, sd: int):
        """The last minute's change of (the trade's side minus the other side's) top-10 size, as a share of the depth, or None."""
        cx = self._cx
        if not S.feat_fresh(cx):
            return None
        bc, ac, d = (cx.feat(c) for c in ("bid10_chg", "ask10_chg", "depth10"))
        if any(v is None or v != v for v in (bc, ac, d)) or d <= 0:
            return None
        return (bc - ac) * sd / d

    def allowed(self, side):
        if not super().allowed(side):
            return False
        p = self.p
        sd = 1 if side == "long" else -1
        if p["stop_mode"] == "rng" and self.blk_height() is None:
            return False                            # no structure yet: nothing to size the stop with
        if p["f_dvol"] != "off" and day_vol(self.dl, self.day) != p["f_dvol"]:
            return False
        if p["f_news"] != "off" and (self.day in release_days()) != (p["f_news"] == "yes"):
            return False
        if p["f_rsi"] != "off":
            r = rsi(self.C)
            if r is None:
                return False
            d, mode = (r - 50.0) * sd, p["f_rsi"]                    # + = RSI on the trade's side of 50
            if not (d > 0 if mode == "with" else d < 0 if mode == "against" else d >= RSI_STRONG if mode == "strong_with" else d <= -RSI_EXTREME):
                return False
        if p["f_cvol"] != "off" and self.blk_cvol() != p["f_cvol"]:
            return False
        if p["f_bookopp"] != "off":
            m = S.book_mean5(self._cx)
            if m is None or m * sd >= 0:
                return False
        for blk in LINE_BLOCKS:
            mode = p[f"f_{blk}"]
            if mode != "off":
                ln = self.blk_line(blk)
                if ln is None or self.C[-1] == ln or ((self.C[-1] - ln) * sd > 0) != (mode == "with"):
                    return False
        if p["f_channel"] != "off":
            pos = self.blk_channel()
            if pos is None:
                return False
            top, bot = pos >= CH_EDGE, pos <= 1.0 - CH_EDGE
            if not ((top if sd > 0 else bot) if p["f_channel"] == "with" else (bot if sd > 0 else top)):
                return False
        if p["f_adx"] != "off":
            a = adx_last(self.H, self.L, self.C)
            if a is None or not (a >= ADX_STRONG if p["f_adx"] == "strong" else a < ADX_WEAK):
                return False
        if p["f_bbw"] != "off":
            r = IND.bbw_rank(self.C)
            if r is None or not (r <= BBW_TIGHT if p["f_bbw"] == "tight" else r >= BBW_WIDE):
                return False
        if p["f_atrp"] != "off":
            r = IND.atr_rank(self.H, self.L, self.C)
            if r is None or not (r >= ATRP_HIGH if p["f_atrp"] == "high" else r <= ATRP_LOW):
                return False
        if p["f_er"] != "off":
            e = IND.efficiency(self.C)
            if e is None or not (e >= ER_TREND if p["f_er"] == "trend" else e <= ER_CHOP):
                return False
        if p["f_mfi"] != "off":
            m = IND.mfi_last(self.H, self.L, self.C, self.V)
            if m is None:
                return False
            d, mode = (m - 50.0) * sd, p["f_mfi"]                    # + = MFI on the trade's side of 50
            if not (d > 0 if mode == "with" else d < 0 if mode == "against" else d <= -MFI_EXTREME):
                return False
        for blk in DIR_BLOCKS:
            mode = p[f"f_{blk}"]
            if mode != "off":
                d = self.blk_dir(blk)
                if d is None or (d == sd) != (mode == "with"):
                    return False
        if p["f_candle"] != "off" and not IND.candle(p["f_candle"], sd, self.O, self.H, self.L, self.C, self.atr):
            return False
        if p["f_rvol"] != "off":
            sig = self.blk_rvol()
            if sig is None:
                return False
            today, med = sig
            if not (today > med if p["f_rvol"] == "high" else today < med if p["f_rvol"] == "low" else today >= RVOL_SPIKE * med):
                return False
        if p["f_level"] != "off":
            dist = LV.nearest(self)
            if dist is None or self.atr is None or not (dist <= NEAR_ATR * self.atr if p["f_level"] == "near" else dist > CLEAR_ATR * self.atr):
                return False
        if p["f_swept"] != "off":
            need = ("lo" if sd > 0 else "hi") if p["f_swept"] == "with" else ("hi" if sd > 0 else "lo")
            if not self._swept[need]:
                return False
        if p["f_pdz"] != "off":
            z = Z.pdz(self)
            if z is None or (z == "discount") != ((sd > 0) == (p["f_pdz"] == "with")):
                return False
        if p["f_ote"] != "off":
            o = Z.ote(self, sd)
            if o is None or o != (p["f_ote"] == "in"):
                return False
        for k in RG.KINDS:
            if p[f"f_pdz_{k}"] != "off":
                z = Z.pdz_range(self, k)
                if z is None or (z == "discount") != ((sd > 0) == (p[f"f_pdz_{k}"] == "with")):
                    return False
            if p[f"f_ote_{k}"] != "off":
                o = Z.ote_range(self, sd, k)
                if o is None or o != (p[f"f_ote_{k}"] == "in"):
                    return False
        for blk in Z.HTF:
            mode = p[f"f_{blk}"]
            if mode != "off":
                t = Z.htf(self, blk)
                if t is None or (t == sd) != (mode == "with"):
                    return False
        if p["f_smt"] != "off":
            x = Z.smt(self)
            if x is None or (x == "bull") != ((sd > 0) == (p["f_smt"] == "agree")):
                return False
        if p["f_ahead"] != "off":
            t = S.thin_ahead(self._cx, sd)
            if t is None or t != (p["f_ahead"] == "thin"):
                return False
        if p["f_wall"] != "off":
            w = self.blk_wall(sd)
            if w is None or w != (p["f_wall"] == "blocked"):
                return False
        if p["f_stack"] != "off":
            x = self.blk_stack(sd)
            if x is None or not (x >= STACK_FRAC if p["f_stack"] == "with" else x <= -STACK_FRAC):
                return False
        for blk in FLOW_SERIES:
            mode = p[f"f_{blk}"]
            if mode == "off":
                continue
            sig = self.blk_flow(blk)
            if sig is None or sig[0] == 0:
                return False
            x, med, big = sig
            way = mode.split("_")[0]
            if abs(x) < (big if mode.endswith("_big") else med) or (x * sd > 0) != (way == "with"):
                return False
        return True

    def _dist(self, ctx, ref, struct):
        if self.p["stop_mode"] != "rng":
            return super()._dist(ctx, ref, struct)
        h = self.blk_height()
        if h is None:
            raise RuntimeError("stop_mode='rng': an order was priced without a structure height")
        return max(self.p["stop_val"] * h, 2 * ctx.tick)


# ---- ib_n: the initial balance with a range length -----------------------------------------------------------------------------
class IbN(port1.Ib):
    """port1.Ib with the range length as an input: the range = the first ib_min minutes from 09:30 (5 | 15 | 30 | 60;
    60 = ib, trade for trade). break: OCO stop entries one tick beyond the range, placed at max(range end, session start);
    a leg already through the last print is skipped. fade: as ib, from the range end. NY sessions only (nyam / mid / pm)."""
    DEFAULTS = {"ib_min": "60"}
    SCHEMA = {"ib_min": ("choice", ("5", "15", "30", "60"))}
    SCREEN_TFS = ("5", "15", "30")
    FEATURES = ()

    def _end(self) -> int:
        return OPEN + int(self.p["ib_min"]) * 60

    def fam_times(self):
        return [_hms(self._end())]

    def _ib(self):
        if self.ibh is None:
            r = self.rng(OPEN, self._end())
            if r:
                self.ibh, self.ibl = r
        return self.ibh is not None

    def fam_time(self, ctx, sec):
        s = self.sid
        if (s is None or self.p["mode"] != "break" or sec != max(self._end(), SESS[s][0])
                or not self.can_enter(ctx) or not self._ib()):
            return
        t = ctx.tick
        self._arm(ctx, [("long", self.ibh + t, self.ibl, None), ("short", self.ibl - t, self.ibh, None)])

    def fam_update(self, ctx):
        self.fade = 0
        if self.p["mode"] != "fade" or ctx.now_ns - self.t0 < self._end() * NS or not self._ib():
            return
        c = self.C[-1]
        if c > self.ibh:
            self.brk = 1
        elif c < self.ibl:
            self.brk = -1
        elif self.brk:
            self.fade, self.brk = -self.brk, 0


FAMILIES = {
    # complexity 7 = ib's 6 (range definition + NY sessions only + break: OCO stop entries + fade: close beyond + fade: first
    #                close back inside -> fade to the mid + mode) + ib_min
    "ib_n": (IbN, {}, True,
             "blocks ib_n: the 09:30 range of ib_min minutes (5 / 15 / 30 / 60), NY sessions only. break = OCO stop entries one "
             "tick beyond the range from max(range end, session start); fade = as ib (tgt_r unused). ib_min 60 = ib",
             {"rationale": "The first minutes after the 09:30 open set a range that the rest of the NY day resolves: a break of "
                           "it traps the side that leaned on it and carries; how long that first balance has to be is the "
                           "question the range length asks.",
              "complexity": 7,
              "variants": [{"ib_min": "5"}, {"ib_min": "15"}, {"ib_min": "30"}, {"ib_min": "60"}]}),
}


# ---- the wrapped families and the range-stop controls ---------------------------------------------------------------------------
def _bar_based(entry) -> bool:
    cls = entry[0]
    return len(entry) == 5 and tuple(cls.FEATURES) == () and "shift_seed" not in cls.defaults()


BASES = {n: e for m in (port1, port2, port3, round1, timed, fvg, liq) for n, e in m.FAMILIES.items() if _bar_based(e)}
BASES.update(FAMILIES)


def _wrap(name: str, cls):
    body = {"__module__": __name__, "__qualname__": f"B_{name}", "BASE": name,
            "__doc__": f"{name} with the blocks: Blocks in front of {cls.__module__}.{cls.__name__} (all blocks default off)."}
    if name in HEIGHTS:
        body["STRUCT"], body["height"] = HEIGHTS[name][0], HEIGHTS[name][1]
    return type(f"B_{name}", (Blocks, cls), body)


def _control(name: str):
    what, fn, keys = HEIGHTS[name]
    cls = BASES[name][0]
    d, sc = cls.defaults(), cls.schema()
    body = {"__module__": __name__, "__qualname__": f"R_{name}", "BASE": name, "STRUCT": what, "height": fn,
            "DEFAULTS": {k: d[k] for k in keys}, "SCHEMA": {k: sc[k] for k in keys if k in sc},
            "__doc__": f"Random-entry control of a range stop on {name}: l2ref.Random (a market entry at a tf close with "
                       f"probability p_entry, random side) whose 'rng' stop reads {what}."}
    return type(f"R_{name}", (Blocks, l2ref.Random), body)


WRAPPED = {n: _wrap(n, e[0]) for n, e in BASES.items()}     # family name -> the class an idea spec runs
CONTROLS = {n: _control(n) for n in HEIGHTS}                # family name -> its range-stop random-entry control
globals().update({c.__name__: c for c in list(WRAPPED.values()) + list(CONTROLS.values())})      # workers import them by name
