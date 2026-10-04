# Member odds — each library member ALONE on each account (2026-10-04, stage 2b)

Data: 22 Sep 2021 to end 2024 (825 trading days, every possible start day), 1 strategy alone, no daily take / stop rules. 2025+ was not read.
Rule used: open losses count (intraday rule; Apex funded = the worst intraday order). Size: about $1,000 of risk a trade = one fixed number of micros (orb: 62, tight straddle: 100), cut to the account's contract limit (Lucid 50K: 40 micros). **The user's bar: 60 % (eval), 75 % (funded). No member reaches it on any account.**

| member | account | micros (risk a trade) | worst open loss, one trade | eval: P(pass within 10 trading days) | eval: P(bust within 10) | funded: P(maximum payout within 20 trading days) | funded: P(bust before first payout) | at the bar? |
|---|---|---|---|---|---|---|---|---|
| orb_NQ_tf1_pre | Lucid Flex 50K | 40 ($640, cut by the contract limit) | $4,480 | 26 % | 59 % | 23 % | 67 % | no |
| orb_NQ_tf1_pre | Lucid Pro 50K (daily loss limit) | 40 ($640, cut by the contract limit) | $4,480 | 32 % | 56 % | 25 % | 73 % | no |
| orb_NQ_tf1_pre | Lucid Pro 50K, no daily loss limit | 40 ($640, cut by the contract limit) | $4,480 | 31 % | 57 % | 24 % | 74 % | no |
| orb_NQ_tf1_pre | Apex 50K | 62 ($992) | $6,944 | 34 % | 64 % | 11 % | 87 % | no; not allowed on Apex: orders on both sides |
| orb_NQ_tf1_pre | Apex 300K PA | 62 ($992) | $6,944 | 0 % (300K eval) | 20 % | 17 % | 57 % | no; not allowed on Apex: orders on both sides |
| straddle_tight_0830_NQ_tf30_pre (FLAGGED) | Lucid Flex 50K | 40 ($400, cut by the contract limit) | $2,040 | 21 % | 40 % | 8 % | 60 % | no |
| straddle_tight_0830_NQ_tf30_pre (FLAGGED) | Lucid Pro 50K (daily loss limit) | 40 ($400, cut by the contract limit) | $2,040 | 21 % | 40 % | 24 % | 68 % | no |
| straddle_tight_0830_NQ_tf30_pre (FLAGGED) | Lucid Pro 50K, no daily loss limit | 40 ($400, cut by the contract limit) | $2,040 | 21 % | 40 % | 23 % | 69 % | no |
| straddle_tight_0830_NQ_tf30_pre (FLAGGED) | Apex 50K | 100 ($1,000) | $5,100 | 32 % | 68 % | 11 % | 80 % | no; not allowed on Apex: orders on both sides |
| straddle_tight_0830_NQ_tf30_pre (FLAGGED) | Apex 300K PA | 100 ($1,000) | $5,100 | 0 % (300K eval) | 24 % | 24 % | 58 % | no; not allowed on Apex: orders on both sides |

How to read it:
* Both members trade the same 08:30 ET data burst (daily profit correlation 0.41, same side on 80 % of shared days), so they are one strategy for a stack, not two.
* At this size one bad fill can end a 50K account: the worst single open loss (orb $112 per micro, tight straddle $51 per micro) is above the $2,000 loss limit on every 50K row. Inside $2,000 the limit is 17 micros (orb) and 39 micros (tight straddle).
* Apex: both members place orders on both sides at once (a bracket), which the Apex one-direction rule does not allow; the Apex rows are for information.
* The Apex 50K rules in the engine are marked unconfirmed. The Apex 300K eval figure is P(pass within 10 days) of the $20,000 goal: about $1,000 of risk is far too small for it.
* The eval window is 10 trading days (the engine's own day walk and race on a 10-day window; its built-in 5-day figure is reproduced exactly by the same helper).
* Funded = the first payout at the per-payout cap (policy 'max') within 20 trading days of a start.
* straddle_tight_0830_NQ_tf30_pre is a FLAGGED member (thin random bar, 2024 survives the stress by $769): see its card before using its row.

Script: `out/admit_r1/member_odds.py` · numbers: `out/admit_r1/member_odds.json`.

## CHECKER CORRECTION (2026-10-04, out/check_r1/) — overrides the text above
straddle_tight_0830_NQ_tf30_pre is DEMOTED (members/_demoted/): it fails the unchanged stage-1 bar (t 1.98 vs 2.56) and its profit
needs a fill on the trigger print (1 ms later: 2024 $4,869 -> $729). Round 1 admits NOTHING; the library has ONE member (orb_NQ_tf1_pre).
The member odds inherit the same optimistic burst fills: orb_NQ_tf1_pre has NOT yet had the fill-after-trigger probe.
