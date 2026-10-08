# StaphlRH8NQ - "5 Edges that refuse to die."
Channel: Fabervaale ENG | https://youtu.be/StaphlRH8NQ | 16 min | written from auto-captions (some words garbled: "IVB" is his name for the first-30-minute breakout, "PAAD" = PEAD, "battle" probably = "breakout")
Gist: five "structural" edges, each with a reason and two or three papers named. Only one is intraday futures: the breakout of the first 30 minutes of the cash session. The other four are stocks, options and bitcoin.
## 2. THE FIVE EDGES
### E1 Post-earnings drift, stocks [3:38-7:14]
Why: big funds split their buying over days (VWAP-style execution) to avoid slippage, so good-surprise stocks keep rising for up to 60 days. Claim on screen: ~4% spread between good and bad surprises over 60 days. No rule (surprise size, entry day, stop).
### E2 "IVB" = initial balance / initial volume breakout, Nasdaq [7:14-10:10]
Why: the first 30 minutes of cash trading (09:30-10:00 ET) is a volatility squeeze where overnight orders get matched; a break of it with volume shows which side is left unfilled, and that side carries the day. US stocks also drift up, so the long side has a tailwind.
Rule as said: range = high and low of the first 30 minutes. Trade with the break. Volume should confirm the break. Direction comes from this statistic; order flow and option flow only time the entry.
Number given: with price only (no volume, no order flow), a "skew of 13.5%" at 1:1 reward:risk for sessions that close beyond the breakout [8:49]. UNCLEAR: whether that means 56.75% vs 43.25% or 63.5% wins; which years; how the stop is placed.
Short side: he says it is "more strong" but only when you can read the options gamma regime [9:20]. No rule given for that.
VAGUE: entry (first touch or bar close beyond the range), bar size, stop (other side of the range? mid?), target, cut-off time, volume threshold, one trade or re-entries.
### E3 Copy members of Congress, stocks [10:10-12:26]
Why: lawmakers know policy early; trades are disclosed within 45 days. Three portfolios vs the S&P shown on screen. No rule.
### E4 Sell option premium [12:26-13:56]
Why: implied volatility sits above realised volatility because funds overpay for crash insurance. One 12-month chart. No rule (strikes, expiry, size, tail hedge).
### E5 Bitcoin "smart DCA" on the MVRV z-score [13:56-16:00]
Why: on-chain cost basis shows capitulation and euphoria; buy more when cheap, less when dear. One equity-line comparison. No thresholds.
## 3. CLAIMED RESULTS
- E2: 13.5% skew (above). "Extensive tests over the last 5-10 years" with a quant and an audit by Matteo Conti: said, not shown in the audio.
- E3: Pelosi portfolio +54% in 2024, +65% in 2023 (stated).
- Everything else: charts on screen and paper names. No trade list, costs, drawdown or out-of-sample split for any of the five.
## 4. PAPERS NAMED (for E2)
Zarattini / Barbon / Aziz "A profitable day trading strategy for the US equity market"; Toby Crabel's opening range breakout; Holmberg et al. on intraday opening range breakout profitability. Note: the first one is a 5-minute range on single stocks with unusual volume, not a 30-minute range on index futures.
## 5. DATA NEEDED
E2: price bars and bar volume only. We have them. E1/E3/E4/E5: stock earnings data, filings, options, on-chain data. We have none, and none is intraday futures.
## 6. FITS THE TESTER
- E2 long side: YES and ALREADY IN THE PIPELINE as nq_or_long_a1 / nq_or_long_a5 (orb_confirm, or_min 15 / 30 / 60, long, nyam, no filters). The old library also ran orb_confirm and ib_n grids on NQ / ES / GC on 2026-10-04.
- What the video adds: (1) volume on the break: filters `rvol high`, `rvol spike` or `volume high`; (2) order flow as timing: `delta with`, `cumdelta with`; (3) the short side as its own idea (orb_confirm, dir short). His gamma-regime condition for shorts cannot be built (no options data); `volatility high` is the nearest stand-in and is not the same thing.
- Both-sides variant with resting orders: ib_n, ib_min 30, mode break.
- E1, E3, E4, E5: NO (not futures, not intraday).
## 7. REPEATS FROM THE 2026-10-03 BATCH
E2 = idea 3 there (09:30-10:00 range breakout, long only, close-confirmed; yW6c0K8uGvw, Matteo Conte). Same person is named here as the auditor. E1 = S3 in that same note (skipped then, same reasons).
## 8. LOOK AT SCREEN
- [8:18]-[9:20] the breakout statistic slide: what "13.5%" is measured on (years, sample size, stop).
- [7:47] the IVB flowchart (he offers it in his Telegram): may hold the entry, stop and volume rule the audio never states.
- [9:20] short-side slide: how the gamma regime is used.
## 9. RED FLAGS
Reasons and paper names stand in for results. The 30-minute index version is not what the main cited paper tested. "Short side is stronger" contradicts the upward-drift reason and is unsupported. Sells a platform and a community; his "hedge fund" is planned, not running.
## 10. VERDICT
Nothing new to build. The one usable thing: when nq_or_long reaches its filter round, the filters to try are a volume one (`rvol high`) and a flow one (`delta with`), each alone. A short mirror is a separate idea and has the weakest reason.
