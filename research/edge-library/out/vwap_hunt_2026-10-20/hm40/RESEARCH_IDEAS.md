**Portfolio hunt: 21 ideas, ranked**

This list is built from the `bp.py blocks` listing (main and the hm60 worktree are the same apart from `jj_fair`) and the research JSON. I also read `vwap_hunt_2026-10-20/PREREG.md`, `hm40/PREREG_HM40.md` and the hm60 diff. Nothing was backtested.

**Facts from the code that change the plan:**
- **Exit table:** the route is hm60, which is hm40 plus fixed-point stops. NQ uses 15/25/40/60 points, ES 4/6/10/15, GC 2.5/4/6.5/10.
- **Families with no structure stop get 40 cells** (ATR and fixed points), not 20: avwap_*, ind_signal, mid_fade, noise_band, open_fade, rsi2, straddle, tod_drift, vol_spike_break, vwap_* and others.
  - open_fade has no structure stop, contrary to what the research says.
- **onr_orb:** its `k` only sets its own stop. It moves the same way as the structure cells, so vary `adx_min` instead.
- **tod_drift:** it carries a built-in 6-bar time exit.
- **open_candle:** the listing shows `pre` only, but `start` 0300 runs in `london` and 1800/2000 run in `eve`. The spec check may refuse those sessions, because it probes the family with its default settings.
- **The VWAP hunt is NQ-only and already covers most VWAP ideas.** Those are left out below.

---

**1. nq_fvg_oside15_a1m3**
- **Setup:** NQ · 15m · nyam, one instance with entries to 15:00 · `fvg_oside`
- **Main:** `min_gap` 0 / 0.1 / 0.25
- **Fixed:** `mode` touch, `pick` newest, `atr1` 3.0, limits `max_tr` 20
- **Trades a day:** 1.2–1.7
- **Why it pays:** it buys the newest pullback gap on the side of the 09:30 open. At the same 37-point bracket, the open side made $53 against $12 with no side. Traders who chase against the day's side lose.
- **Evidence:** the only leg on file that clears Gates 1 and 2. Walk-forward: 380 trades, +$28.5k. Blind months: 99 trades, +$6.6k. Beats 99.55% of random. Build days rise steadily with the setting: $98 / $108 / $121.
- **Risk:** its months have been read at least 8 times. It lost $13.5k from May to Aug 2026. The middle-candle, cap-2 sibling failed. Skip cells under 25 points.

**2. nq_disp15_1000**
- **Setup:** NQ · 15m · nyam · `displace`
- **Main:** `k` 1.25 / 1.5 / 2.0
- **Fixed:** `mode` follow, `close_r` 0, `w_start` 09:45, `w_end` 11:00, `max_tr` 1
- **Trades a day:** 0.4–0.7
- **Why it pays:** a big 15m candle in the first 90 minutes is real buying or selling pressure. People fading the open lose.
- **Evidence:** build rises steadily with `k` ($90 / $171 / $219), beats 99.8–100% of random, every year positive. The walk-forward failed only through the per-block pick. The fixed 1R cell made $123 on 188 trades, +$3.5k on 47 unseen. The fixed-box route is that test. The family is nearly blind.
- **Risk:** under 200 test trades. The 10:00 start was a choice made on build days. Widening the window has killed it every time.

**3. gc_rel0830_bracket**
- **Setup:** GC · 5m · pre · `straddle`
- **Main:** `off_atr` 0.5 / 0.75 / 1.0
- **Fixed:** `delay_min` 5 (orders go in at 08:30), `news_only` false, `days` rel0830. Neighbour: `days` tier1.
- **Trades a day:** about 0.4
- **Why it pays:** US 08:30 data re-prices gold within seconds. Stale resting orders lose.
- **Evidence:** release days made +$4.7k / +$5.0k / +$5.5k a year in 2022–24 (319 trades, 68% win, PF 1.90). Non-release days lost $6.6k. In the tick study, off 2 / stop 3 at 1:2 made +$16.2k (t 2.56), and the non-release control lost $10.9k. NFP/CPI held from 2025-01 to 2026-09 at the in-sample level. It is the only mechanism on file that beats random controls.
- **Risk:** it rests orders on both sides (OCO), and fills come in a 1-second burst. PPI, retail and PCE days lost on their own. GC's 2.5 / 4-point cells are close to the old 3-point bracket.

**4. nq_pm_first_bar15**
- **Setup:** NQ · 15m · pm · `first_bar_mom`
- **Main:** `k` 0.2 / 0.5 / 1.0
- **Trades a day:** 0.6–1.0
- **Why it pays:** the session opener after lunch. Traders playing the lunch range lose.
- **Evidence:** build 930 trades, beats 99.92% of random. 3:1 block walk-forward: 245 trades, 50.6% at 1:1.1 against a break-even of 47.6% (+3.0), PF 1.13, P6.1–6.4 pass. The pm session beats random by 3.5–5.5x.
- **Risk:** long +$38.3k against short −$0.9k, so it may be drift. Blind months −$2.1k on 60 trades. Partly seen.

**5. nq_daymove_1500 (long card + short card)**
- **Setup:** NQ · 5m · pm · `noise_band`
- **Main:** `k` 0.25 / 0.5 / 0.75
- **Fixed:** `anchor` rth, `w_start` 14:40, `w_end` 15:05, `max_tr` 1, `dir` long or short
- **Trades a day:** 0.4–0.6
- **Why it pays:** late-day hedging and rebalancing push in the direction of the day's move. Afternoon faders lose.
- **Evidence:** build $88, PF 1.28. Unseen 138 trades, $72, PF 1.20. Desk read $71. Its twin made $89 unseen.
  - **Why it is not the failed last-30-minute test:** it uses the 15:00 window, and it held unseen.
- **Risk:** read twice, and the random gate was never run. The proxy adds a VWAP condition and uses daily ATR instead of the prior range. The exact form needs a new `day_move` block.

**6. nq_noise_gx_mid_long**
- **Setup:** NQ · 15m (1m and 30m as neighbours) · mid · `noise_band`
- **Main:** `k` 0.2 / 0.3 / 0.4
- **Fixed:** `anchor` globex, `dir` long. The short card is the control.
- **Trades a day:** 0.3–0.5
- **Why it pays:** an overnight trend still holding at midday keeps going. Midday mean-reverters lose.
- **Evidence:** the 1m version passed unseen: 263 trades, +$39.2k, PF 1.37, beats 99.98% of random. Block walk-forward $24.4k on 262 trades, but it beat only 89.5% of random. The ES and GC neighbour maps were both profitable.
  - vault_break failed in nyam, which is a different session.
- **Why 15m:** on 1m bars hm60's ATR stops are 2–12 points, which drag down the average box.
- **Risk:** long-only, so it needs the same-side random check. Rebuilds were unstable (from +$77k to −$5.7k).

**7. es_noise30_ny (long card + short card)**
- **Setup:** ES · 30m · nyam+mid+pm · `noise_band`
- **Main:** `k` 0.25 / 0.35 / 0.5
- **Fixed:** `anchor` rth, `max_tr` 1, `dir` long or short
- **Trades a day:** 0.6–1.2 for both cards
- **Why it pays:** intraday momentum. Zarattini et al. (SPY 2007–24, net): Sharpe 1.33, +24% to +37% in every year 2020–24. Baltussen: 14 of 17 markets positive out of sample.
- **Why it is new:** a different market and bar size from the VWAP hunt's NQ 5m version.
- **Risk:** ES fails almost everything locally. The paper's edge needs a trailing exit, and hm60 caps targets at 2R. The flat band is not the paper's time-of-day band.

**8. nq_0300_candle**
- **Setup:** NQ · 5m · london · `open_candle`
- **Main:** `body_r` 0.4 / 0.5 / 0.7
- **Fixed:** `start` 0300, `w_flat` 09:25 (frees the account for the NY legs)
- **Trades a day:** 0.5
- **Why it pays:** the London cash open brings the first real flow of the night. Asia range traders lose.
- **Evidence:** build $103, PF 1.25. Test days 191 trades, PF 1.26. A one-cell block walk-forward made $237 on 53 unseen trades.
- **Risk:** the edge was the 3R target. At 2R the test days made +$3.5k against +$35k at 3R. Long-heavy, and 2023-heavy.

**9. gc_0300_candle**
- **Setup:** GC · 5m · london · `open_candle`
- **Main:** `body_r` 0.4 / 0.55 / 0.7
- **Fixed:** `start` 0300, `w_flat` 08:20
- **Trades a day:** 0.5
- **Why it pays:** the London gold market opening is gold's own handover from Asia.
- **Evidence:** only the NQ result and retail XAUUSD tests.
- **Risk:** NQ rules rarely port to GC. GC's London ATR is small against $24 costs. Overlaps #13.

**10. nq_onr_orb**
- **Setup:** NQ · 15m · nyam (the family stretches it to 15:30) · `onr_orb`
- **Main:** `adx_min` 15 / 20 / 25
- **Fixed:** `k` 0.3, `earliest` 10:30, `ov_from` 01:00
- **Trades a day:** 0.3–0.4
- **Why it pays:** where the 09:30 open sits in the overnight range sets the day's side.
- **Evidence:** build $484 a trade, PF 1.76, every year positive. The map averaged $144 with 95.8% of boxes green.
- **Risk:** its code check failed (trades outside the window, probably the check using the nyam window), so re-run the check first. Only about 100 test trades. The 3R target is gone.

**11. gc_rel1000_bracket**
- **Setup:** GC · 5m · nyam · `straddle`
- **Main:** `off_atr` 0.5 / 0.75 / 1.0
- **Fixed:** `delay_min` 30, `days` rel1000
- **Trades a day:** about 0.2
- **Evidence:** 143 trades, 79% win, PF 3.35 (2022–24).
- **Risk:** JOLTS failed its out-of-sample read. The London gold price auction has been electronic since 2015. Very low trade count. Rests orders on both sides.

**12. gc_us_morning_short**
- **Setup:** GC · 15m · nyam · `tod_drift`
- **Main:** `off_min` 0 / 15 / 30
- **Fixed:** `dir` short
- **Trades a day:** 1.0
- **Why it pays:** Asian buying gets given back in US hours.
- **Evidence:** Blose et al. 2018 (COMEX day session negative after costs). World Gold Council H1 2026: US hours −15%, Asian hours +13%. The local hour table was null.
- **Risk:** this is the hidden 6-bar exit question. It must pass the same-side random check. A pass during the 2024–26 gold bull market would at least not be drift.

**13. gc_asia_range_london_break**
- **Setup:** GC · 15m · london · `donchian` as a proxy
- **Main:** `n` 8 / 10 / 12 (the last 2 to 3 hours of the Asia range at 03:00)
- **Fixed:** `w_start` 03:00, `w_end` 05:00, `max_tr` 1
- **Trades a day:** about 0.7
- **Evidence:** MQL5 study, 715 trades, PF 1.38. Held-out 2026: PF 1.61 on 157 trades.
- **Risk:** only retail, gross evidence. The proxy's channel rolls into London bars after 03:00. The exact rule needs `win_break` opened outside nyam.

**14. nq_fvg15_am_plain**
- **Setup:** NQ · 15m · nyam+mid · `fvg`
- **Main:** `min_gap` 0 / 0.1 / 0.25
- **Fixed:** `mode` touch, `new_gap` replace, `max_tr` 4, `w_end` 12:55
- **Trades a day:** 1.2–1.4
- **Evidence:** unseen 58.9% against a break-even of 55.2%.
- **Risk:** dead from Jul to Oct 2026, and overlaps #1.

**15. nq_0830_candle**
- **Setup:** NQ · 5m · pre · `open_candle`
- **Main:** `body_r` 0.5 / 0.7 / 0.85
- **Fixed:** `start` 0830, `w_flat` 09:25
- **Trades a day:** 0.25–0.45
- **Evidence:** unseen 76 trades, $119, PF 1.41. It missed its month and Monte Carlo lines by half a point.
- **Risk:** mostly short, depends on news days, very few trades.

**16. gc_eve_long**
- **Setup:** GC · 30m · eve · `tod_drift`
- **Main:** `off_min` 60 / 120 / 180
- **Fixed:** `dir` long
- **Trades a day:** 1.0
- **Risk:** the same bet as #12, mirrored. The evening Desk is shadow-only. The local hour table was null.

**17. nq_holy_grail**
- **Setup:** NQ · 5m · nyam · `ema_pullback`
- **Main:** `g_lvl` 20 / 25 / 30
- **Fixed:** `n` 20, `gate` adx, `g_n` 14, `g_side` with, `max_tr` 2
- **Trades a day:** 0.5–1
- **Why it is new:** never run before with an ADX gate.
- **Risk:** every trend gate lost its blind months after mid-2025.

**18. es_supertrend15_adx**
- **Setup:** ES · 15m · nyam+mid+pm · `supertrend`
- **Main:** `mult` 2 / 3 / 4
- **Fixed:** `gate` adx, `g_n` 14, `g_lvl` 20, `g_side` with, `max_tr` 2
- **Trades a day:** 1–2
- **Evidence:** supertrend has the broadest cross-market support of any trend family (4 of 27 ES units passed naked).
- **Risk:** naked flips are no better than random.

**19. nq_volspike15_pm**
- **Setup:** NQ · 15m · pm · `vol_spike_break`
- **Main:** `m` 2 / 3 / 4
- **Trades a day:** 0.3–0.5
- **Why 15m:** the 20-bar median then covers 08:45–13:45, not thin overnight bars.
- **Risk:** afternoon edges pass build and then fail (the 30m version failed 2024).

**20. es_avwap_onh_flip**
- **Setup:** ES · 5m · nyam · `avwap_flip`
- **Main:** `vol_m` 0 / 1.5 / 2.5
- **Fixed:** `line` onh, `also` rth, `hold` 2. Neighbour: `line` onl.
- **Trades a day:** 0.5–1
- **Risk:** Shannon's rule has no published stats. NQ VWAP-cross ideas averaged about $15.

**21. nq_open15_bigbody**
- **Setup:** NQ · 15m · nyam, held to 15:58 · `first_bar_mom`
- **Main:** `k` 1.0 / 1.5 / 2.0
- **Trades a day:** 0.5–0.8
- **Evidence:** only the 15m opening range showed a direction edge. The big-body subset made $123.
- **Risk:** beats only about 92.7% of random. Flattened at 11:00 it loses, so check that the nyam pass holds to the day. Overlaps #1 and #2.

**If every leg passed:** about 6.3 trades a day from #1–10 and about 14 from all 21. At past pass rates, expect 2–4 legs and roughly 2–4 trades a day.

**Dropped:**
- **Failed, per the project's own findings:** open_fade, mid_fade, gap fill, the 09:30 5m volume candle, the ES 02:00 drift, GC settlement momentum, the ES night `vwap_z`, the GC 20:00 candle, the wide 09:30 straddle, and displacement with an open-side gate.
- **Already in the VWAP hunt:** VWAP touch with an ER gate, the VWAP band break, `ema_ribbon` with VWAP, and IB/ORB with VWAP.
- **Weak record or fades:** squeeze, rsi2, lunch-range donchian.
- **Folded into other ideas:** the atr_rank noise band and ES late-day `tod_drift` with a roc gate.

---

**5 lessons for the hunt**
1. **Frequency comes from stacking.** 5–10 trades a day means 5–10 separate legs of about 0.3–1.5 each, on different clocks and markets. Busier versions of one rule fall to break-even: JJ at 2.4 → 5.1 trades a day went from +$34 to +$12, and none of 51 sheets at 2+ a day reached +0.075R. A build pass holds about 1 time in 5–10.
2. **Stop width decides the sign, and hm60 judges the average box.** NQ stops of 20 points or less and 0.5x ATR on 1–5m bars lose. ES and GC costs eat about 4x more of each R than on NQ. The 2R cap removes the 3R tails that made the 03:00 candle, onr_orb and the noise band work.
3. **Only real mechanisms have beaten random.** That means GC release brackets, session-opener bars (09:30, 13:30, 03:00) and a day-context side (the 09:30 open side, the overnight third). Fades lose, gates improve the fit but not the out-of-sample check, and NQ rules port to ES/GC only when the reason is specific to that market.
4. **NQ's out-of-sample months are spent, and the market changed in mid-2025.** Only Sep 2025, Jan 2026 and May 2026 are fresh. Weight the 2025-07+ in-sample check heavily. ES and GC legs are the cleaner test. One-sided legs must pass the same-side random check.
5. **Check the plumbing before any run:**
   - Does the spec check accept `open_candle` in london/eve?
   - `win_*` and `candle930` run in nyam only.
   - onr_orb: vary `adx_min`, not `k`.
   - tod_drift has a hidden 6-bar exit.
   - straddle rests orders on both sides.
   - Do `vol_m` / `med_m` stay within the in-sample months?
   - Re-run onr_orb's code check.

**Questions for the owner**
1. Are the 5 accounts Apex or Lucid? Are both-sided brackets (#3 and #11) allowed?
2. Does tod_drift's built-in 6-bar exit count as allowed under the fixed exit table (#12, #16)?
3. Can london and eve legs trade live? Should night legs be flat by 08:20 / 09:25 to free the account?
4. May I build two new blocks: `day_move` (#5) and `win_break` outside nyam (#13)? Or should the proxies stand?
5. Should NQ legs whose months have already been read (#1, #2, #4, #6, #14) still count, or do ES/GC legs come first?
6. Are one-sided legs OK if they pass the same-side random check (#6, #12, #16)?
7. Are the hm60 fixed stops for ES (4/6/10/15) and GC (2.5/4/6.5/10) the ones you want? Is the pass bar the same as the VWAP hunt's (C1–C6 in-sample, then out-of-sample only on your word)?

Beyond `bp.py blocks` I ran one read-only Python call to list which families have a structure stop, and nothing else. I did not open any `logs/` or `wf/` file, and I did not check whether the spec check accepts each of these settings.