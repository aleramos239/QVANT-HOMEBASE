# judge.py — ADMISSION v2 as one tool (unit in -> verdict + card out)
The owner's rule (EDGE_SPEC "ADMISSION v2", "PERIODS AMENDED", "CHECKER FIXES" F1-F6): judge a strategy by the AVERAGE of all its
variants, never by one. `judge.py` only READS stores; it never runs a simulation and never opens a year. Every threshold sits at
the top of the file with the spec text it comes from. Locked by `tests/test_judge.py`. Python: `"$HOME/ONYX TRADING/.venv/bin/python"`.

**Unit** = `<family>-<ROOT>-tf<tf>-<session>[:<axis>=<value>][@<day filter>]`: `orb-NQ-tf15-pre`, `gap-ES-tf15-nyam:mode=fill`, `straddle_tight_0830-NQ-tf30-pre@A`.
Day filters: `@A` every 08:30 ET release day, `@B` tier-1 08:30 releases only, `@C` every 10:00 ET release day (STAGE 3, `engine/cache/events.csv`); `@vol_lo`,
`@news_only`, ... (STAGE 2a, `out/deepen/labels.py`, 2021-24 only). The v2 uid `orb-NQ-tf15|pre|` also works. `c1-NQ-tf1-eve:seed=2` = a placebo unit (random entries judged as a strategy).

## Commands (all take `--draws N`, `--seeds N`, `--upto build|pick|check`, `--as-v2`; `--exam` = the explicit EXAM flag, see "The EXAM")
| command | what it does |
|---|---|
| `judge.py build <unit> [...]` | tests (1)-(3) on BUILD, one line per unit: pass or the failed tests, the numbers, the seeds and draws behind (2). Exit 0 = pass. |
| `judge.py year <unit> --period pick\|check` (`exam` with `--exam`) | tests (4)-(6) for that year ON ITS OWN. `pick` also gives the surviving set, the default and the final verdict; `check` re-tunes nothing: CONFIRMED / WEAK / FAILED. Prints every store used (new or re-used) and appends it to `out/judge/year_reads.csv`. Refuses, and prints the `jobs.json` to run, when a store is missing. |
| `judge.py card <unit> [--out DIR]` | writes `members/<name>/card.md` and `surviving_set.csv` (a row per period that exists). Members only. |
| `judge.py table [units] [--stage s1,r1,ev,en,2a\|members\|placebo\|all\|<catalog.csv>] [--out PREFIX]` | one line per unit, CSV + markdown (default `out/judge/table.*`). All 1,916 units, 8 workers: about 6 min at 4,000 draws, 19 s with `--as-v2`. |

Defaults = the rule in force: 4,000 draws, every control seed and every year on disk, more than 60 %. `--as-v2` = exactly as out/v2 coded and ran it
(200 draws, 2 seeds, 60 % or more, a year de-duplicated again, its six store folders, BUILD + 2024): for the regression lock only. Draws come in blocks of 200 (block i =
the unit's seed + i): `--draws 200` is out/v2's own draw, 4,000 is the checker's 20 seeds (`out/check_v2/chk_seed.json`), draw for draw. API: `unit`,
`build`, `year`, `judge`, `member`, `card`, `table_rows`, `catalog`; settings in `judge.RULE`; a refusal is `judge.Refuse` (`.jobs` = what to run).

## The six tests (table = the unit's variants; dead and author cells out, identical trade lists counted once)
BUILD, 22 Sep 2021 - 2023:
1. More than 60 % of the variants make money, and the average variant makes money.
2. Real edge: the table's average beats the average of the same table with random entries, and beats 95 % of 4,000 random tables. Drawn only when (1) is near (average > 0, 50 % of variants profitable); otherwise the unit already fails (1).
3. Enough trades: the average variant's BUILD trades, scaled to BUILD + 2024 at the same daily rate, reach 100 (re-checked on the real count once 2024 is read).

A year on its own (2024 = PICK, then 2025 = CHECK), read only if everything before it passed, on the BUILD variant list:
4. The average of all variants makes money, and so does the median variant.
5. The average still beats the random average (lift > 0) against every control used on BUILD.
6. The average still makes money under stress: 2 ticks + 250 ms, + a 100 ms late cancel of the other side for two-sided brackets.

SAVED = the variants that make money on BUILD, on 2024 and under stress in both. DEFAULT = the middle one by BUILD net (never the best).
CHECK keeps both and reports them on 2025. Speed is on the card two ways (fast winners / all winners; net of fast trades / total net = the FAST flag).

## Control per unit type (every control that applies must pass; random controls use EVERY seed on disk)
| unit type | control | real replicates |
|---|---|---|
| bar-based | `c1`: random entries, same exits, session and days; coupled random tables | the seeds of every random-entry store on disk for that market, bar size, period (2 today; under 10 = THIN) |
| time-fired (`shift_seed` families: brackets at a clock time, late_mom, ...) | `shift`: the same table at a random minute / with a random direction; day-mixes of the seeds | the seeds on disk (2 today = THIN) |
| Level 2 family | + `c2`: the same table on a shuffled book (`<key>...-c2s<seed>`); day-mixes | the seeds on disk; fewer than 2 on BUILD = fail |
| Level 2 option of a base family | + `base`: net per trade must beat the same strategy without the option | one comparison |
| day filter (`@A`, `@vol_lo`, ...) | `days` first: net per trade beats the unfiltered table and 95 % of 4,000 random same-size day subsets; then the unit's own `c1` / `shift` on the same days | 4,000 subsets |
| placebo (`c1-...:seed=k`) | `c1` from the other seeds | the other seeds |

A seed is found in ANY `runs*/` folder (never `runs_void/`) by its run.json: control `c1` / `shift` / `c2`, same family, market, bar size, period (the store's date range) and session, cells `s<seed>_<id>` with the BUILD control's inputs.
With more than 2 seeds the first-2-seeds result is shown beside the new one; a unit that passes all six with the first 2 seeds but fails (2) or (5) with all of them is DEMOTED ("luck not excluded": kept on file, not edge).

## How a new round uses it
1. Run the BUILD menu and its control: `python run_menus.py run --family <f> --roots <R> --tf <tf>` (+ `run_menus.py nulls` for the c1 pool).
2. `judge.py build <unit>` (a whole round at once: `judge.py table --stage <catalog.csv>`, columns `key`, `sess`, optional `label`, `group`). A fail stops here: 2024 is never read for it.
3. `judge.py year <unit> --period pick` -> REFUSED + `jobs.json` (whole menu + control on 2024) -> `python out/v2/run_v2.py run jobs.json` -> again.
   If (4) and (5) pass it prints the stress jobs, then the BUILD-stress jobs for the surviving set: run each, call it again. Ends in MEMBER or the failed tests.
4. `judge.py card <unit>`. The default's full trade rows (`spec.json`, `trades_*.json`, `daily.csv`) come from the member run, not from here.
5. CHECK: `judge.py year <unit> --period check`, then `card`. A 2025 store = a store in any `runs*/` folder with a 2025 date range, named `<key>-<sess>-check[-stress|-shift|-c2sN]` / `c1-<ROOT>-tf<tf>-<sess>-check`. 2026+ = the EXAM: refused (next section).

## The EXAM (2026) — sealed; opened once, per unit, by EDGE_SPEC "FULL OUT-OF-SAMPLE FOR THE SAVED STRATEGIES" (2026-10-05)
`judge.py year <unit> --period exam --exam` = the SAME tests (4)-(6) and the same code path as `check`, on the 2026 stores (`runs_exam2026/`, range 2026-01-01 .. the last
complete session per market). Refused BEFORE any store is looked at unless BOTH hold: the `--exam` flag (`RULE["exam"] is True`) and the unit is listed in
`out/exam2026/allowed.json` (members under the rule in force that pass (4)-(6) on 2025; written from the 2025 verdicts before the first 2026 run; it also holds the end
date per market). A DEMOTED unit never reaches 2026. Without the flag nothing changes: no 2026 calendar row is returned, `judge` / `card` / `table` stop at 2025.
`card --exam` adds the 2026 row for an allowed unit. Runner: `out/exam2026/run_exam.py` (allowed units only, `allow_exam=True`, reads in `out/exam2026/reads.csv`).
Locked by `test_exam_is_sealed_without_the_flag_and_off_the_allowed_list` (flag, list, engine seal, runner seal).

## Differences from out/v2 at `--as-v2` (the only ones the lock lets through) and tests
a. `final.json` lists test 6 as failed for the 38 units whose stress never ran; here `failed` = judged tests only (`not_judged` has the rest). b. "SAME IDEA" names in folder order. c. Card layout of the Real edge and Speed sections (checker fixes).
`pytest tests/test_judge.py` (2 min): layer A = out/v2 exactly; layer B = F1-F6. `JUDGE_FULL=1` adds all 1,916 units at both settings (7 min). Reads BUILD and 2024 only, from out/v2's six folders.
