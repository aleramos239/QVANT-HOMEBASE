# v2 members — one line per idea (2026-10-04, ADMISSION v2)

Same idea = same family + market + session, OR the default variants trade the same side on at least 70 % of the days both trade (at least 30 shared days; a day's side = the side of the default's first trade that day). Links chain. **One idea = one strategy for a stack, never two.**
Dollars: the AVERAGE variant, BUILD + 2024 combined, 1 contract after costs. Pair table: `out/v2/members.json` (`pairs`). Cards: `members/<unit>/card.md`.

| # | idea | market | session | units (member folders) | why they are one idea | average variant, combined | flags |
|---|---|---|---|---|---|---|---|
| 1 | Bracket around the 08:30 ET data burst | NQ + GC | pre-market | `straddle_t_0830_NQ_tf30_pre` (all days, wide ATR bracket) · `straddle_tight_0830_NQ_tf30_pre` (all days, tight) · `straddle_tight_0830_NQ_tf30_pre_evA` (08:30 release days) · `straddle_tight_0830_NQ_tf30_pre_evB` (tier-1 days) · `straddle_tight_0830_GC_tf30_pre_evA` · `straddle_tight_0830_GC_tf30_pre_evB` | NQ units: same side on 74-100 % of shared days. Gold evA / evB: same variant, evB is a subset of evA's days (100 %). Gold joins NQ only through the wide NQ bracket at 70.4 % and 70.3 % (borderline; against the tight NQ units 64-68 %) | $50,993 · $15,283 · $14,021 · $12,418 · $16,095 · $13,113 | 2024 second look; thin control (2 random-minute seeds); burst fill risk; tight units are FAST (52-77 % of profit under 5 s) |
| 2 | Tight bracket at 10:00 ET on 10:00 release days | NQ | NY morning | `straddle_tight_1000_NQ_tf30_nyam_evC` | alone (same side as the gold unit on 62 % of shared days) | $7,342 (141 trades) | thin control; burst fill risk; FAST (56 %) |
| 3 | Tight bracket at 10:00 ET on 10:00 release days | GC | NY morning | `straddle_tight_1000_GC_tf30_nyam_evC` | alone | $12,519 (142 trades) | 2024 second look; thin control; burst fill risk (v1 probe: fill-fragile); 47 % of profit under 5 s |
| 4 | First-bar momentum at midday | NQ + ES | midday | `first_bar_mom_NQ_tf30_mid` · `first_bar_mom_NQ_tf15_mid` · `first_bar_mom_ES_tf15_mid` | same family and session; same side on 90-98 % of shared days (NQ and ES move together) | $25,608 · $20,906 · $7,313 | 2025-26 PENALTY family |
| 5 | Opening range break, pre-market, 15-minute range | NQ | pre-market | `orb_NQ_tf15_pre` | alone: same side as the 08:30 brackets on only 49-59 % of shared days (its range ends 08:40, after the burst) | $33,593 (725 trades) | the 1-, 5- and 30-minute versions FAIL test (2); 2024 read before at 1 minute; EXAM would be a second look |
| 6 | Bracket at 18:00 ET (the evening reopen) | NQ | evening | `straddle_t_1800_NQ_tf30_eve` | alone (same side as idea 7 on 49 %) | $28,219 (647 trades) | thin control; 2024 lift over random minutes only $142 |
| 7 | Fast-average (TEMA) slope turn | NQ | evening | `tema_slope_NQ_tf30_eve` | alone | $31,939 (480 trades) | WEAK reason; EXAM would be a second look |

14 units, 7 ideas. If gold's borderline link is cut, idea 1 splits into "08:30 burst NQ" (4 units) and "08:30 burst gold" (2 units) = 8 ideas.
Luck check (see `out/v2_summary.md`): 1 of 168 random-entry tables passes the same six tests; ideas 4-7 and the two all-day brackets of idea 1 are not shown to be more than luck by that count.
