# orb_NQ_tf1_pre: admitted under the v1 rules, NOT under ADMISSION v2 (2026-10-04)

Fails on BUILD (test (2) real edge, control `c1`: lift $525, beats 54 % of replicates (needs lift > 0 and 95 %)). BUILD table: 72 % of 96 variants profitable, average variant $19,279. 2024 was not judged under v2.

Detail (BUILD, 96 variants): with NO target the orb variants average $49,283 and random 1-minute entries with the same stops in the same session $66,766 (random entries are already in the market before 08:30); with a target orb averages $9,278 against $2,750 (ahead by $6,528). Over the whole table the lift is $525.
The 15-minute version of the same idea passes all six v2 tests: `members/orb_NQ_tf15_pre/` (its random control enters later, so it is an easier control). Everything else in this folder is the v1 record, unchanged.
