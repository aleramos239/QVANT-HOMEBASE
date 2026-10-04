# CDyrzNSzn8M — Ex-Hedge Fund Manager Draws Out His Full VWAP Scalping Strategy
Channel: IQCapital Clips. URL: https://youtu.be/CDyrzNSzn8M
Gist: a 30-year discretionary ES scalper (called Robert by the host) takes reactions at anchored VWAPs with a tiny stop; Bookmap resting orders are optional confirmation.

## 2. TESTABLE RULES (core is discretionary; only a skeleton is code-able)
- Market ES (price shown near 7,000), intraday scalping. Three VWAPs: Day VWAP anchored 18:00 ET (his main one); London VWAP anchored at the London open (time not stated); US VWAP anchored at the regular-hours open (09:30 ET assumed, not stated).
- Setup: price moves away from a VWAP, then returns to it; he enters at market when price reaches the VWAP and expects a reaction. Only example shown: price rising up into the US VWAP from below = short. Mirror long (from above) is implied, never shown.
- Stop 10 ticks (2.5 pts). Target 10-15 ticks ("varies"; once says 11). Waits 1 to 1.5 hours for a setup. Exit at target.
- Filters: skip sideways days where the VWAPs are flat ("no A+ setups"); skip when a big resting order near the level looks like it is being pulled (spoofing).
- Optional confirmation: big resting limit order at the VWAP (example about 600 lots). He then says that after 30 years he just takes the trade.
- VAGUE: which VWAP is "most respected" (judged by eye each day); definition of sideways; how far price must leave VWAP first; first touch only or every touch; time window; what counts as a "large" order; how spoofing is told from real liquidity; entry on touch vs bar close; costs on a 2.5-pt stop.

## 3. CLAIMED RESULTS
- 80% win rate at about 1.1:1 reward:risk (host's wording; he answers "yeah"; caption cut off mid-sentence). No period, sample size, or evidence shown. Pure claim. By arithmetic 80% at 1.1:1 is +0.68R per trade before costs, which is not believable for an ES scalp.

## 4. PROP-FIRM TACTICS
None.

## 5. TESTING-METHOD IDEAS
None. Only a claim that his discretion sits on a system based on how algorithms act.

## 6. LOOK AT SCREEN
- [03:02] how "most respected VWAP" and a "sideways" day are judged: needs the chart.
- [05:03]-[06:03] Bookmap: what a large order and a pulled order look like in the book.
- [09:07]-[10:07] the short at the US VWAP: price position vs all three VWAPs is not spoken.
- [12:09] where entry, 10-tick stop and target sit on the chart: no example trade shown.

## 7. RED FLAGS
Purely discretionary; no evidence for 80%; manipulation/spoofing story is untestable ("I don't know" their intention); host asks leading questions; title oversells ("full strategy"); IQCapital brand sells challenges (see wm4A6qo0g3I); he admits the liquidity filter adds little; 2.5-pt stop is easily eaten by slippage in a backtest.

## 8. VERDICT
Maybe, one cheap tick-level test: ES, first return touch of the 18:00 ET and 09:30 ET VWAPs after price was away, market entry, stop 10 ticks, target 12 ticks, count win rate with real fills; expect nowhere near 80%. Everything else is not code-able. wm4A6qo0g3I is the better-specified VWAP idea.
