**PORT1 report — the seven families are registered and every tester-match gate passes at 100 %, on NQ and on ES. No menu was run.**

Families: orb, straddle, donchian, squeeze, ib, lon_break, gap. All have screen tfs 1 / 5 / 15 / 30, no Level-2 features, roots NQ / ES / GC. That is 84 units and 7,680 menu cells (2,560 per root).

## Tester-match gate (trade identity only, nothing ≥ 2025 read)
`engine/PORT1_VALIDATION.md`, re-run on the final code with 2 workers:

| what was replayed | size | result |
|---|---|---|
| NQ screen bundles (R ledger, stage screen) | 28 bundles, 7 families × 4 tfs | 100 % identical on all 20 fields, net diff $0, same skipped days |
| ES screen bundles (ES pilot ledger) | 28 bundles | 100 % identical, net diff $0 |
| NQ heat-maps the variants come from | 9 heat-maps, 300 cells, every registered variant | 300 of 300 cells identical |

- **Beyond the brief:** the screen bundles only run each family at its default inputs, so I added the heat-map cells (squeeze nr7 / inside, ib fade, gap go, and so on are separate code paths) and the ES bundles.
- **GC:** no tester bundle exists, so GC rests on the engine owner's by-construction argument only.

## Registry
| family | variants (first axis, source line quoted in the module) | complexity | both sides |
|---|---|---|---|
| orb | or_min 5 / 15 / 30 (tune1 line 9) | 3 | yes |
| straddle | off_atr 0.25 / 0.5 / 1.0 (tune2 line 1) | 5 | yes |
| donchian | n 10 / 20 / 40 / 60 (tune1 line 1) | 3 | no |
| squeeze | sq_type bbkc / nr7 / inside (tune2 line 2) | 5 | yes |
| ib | mode break / fade (tune1 line 4) | 6 | yes |
| lon_break | min_rng_atr 0 / 1 / 2 (tune2 line 9) | 4 | yes |
| gap | mode fill / go (tune2 line 8) | 5 | no |

- **Rationales** use EDGE_SPEC's wording where it gives one (orb, donchian, lon_break) and otherwise the hypothesis written in the old family file before the old screen.
- **donchian** carries the 2025-26 penalty text; orb, straddle and donchian notes label the exam as a second look.
- **Code:** orb, squeeze, ib, lon_break and gap are the old `class Fam` bodies copied verbatim (a test compares the syntax trees). straddle and donchian subclass the tester-matched `l2ref` classes without overriding anything.

## Tests
- `engine/tests/test_port1.py`: 48 tests, all pass (72 s). It covers:
  - registry, variants against the tune files, inputs against the tester drafts;
  - 10-day tester match for NQ, ES and all heat-map cells;
  - worker identity over every family × variant × tf × session instance (240 specs), plus a fresh-instance-per-day check;
  - no-look-ahead (garbage after 16 cut times, 2 days, 3 tfs), plus a deliberately leaky family the check must catch.
- **Worker identity was run at 2 workers, not 8**, because of the machine load and my 1–2 worker limit. On 8 days that still gives one fresh instance per day, which is what 8 workers would do; the test defaults to 8.
- **Full suite** (2 workers): 1,256 tests, 1,253 passed, 2 skipped, 1 failed in `tests/test_new_l2.py` (another author's file, mid-edit). That test passed when I re-ran it alone afterwards.
- **Smokes** (counts only, 10 BUILD days): 44 runs, all `ok` — NQ at every tf, ES and GC at tf 5, straddle and donchian also at tf 30. No dropped session, worker parity holds, both-side declarations match.

## Open risks and decisions for the orchestrator
1. **Cells that cannot trade count as "not > 0" in the plateau.** Indicators restart at 00:00 (18:00 for the evening), so some registered variant × tf pairs never enter:
   - donchian tf 30: n 40 and n 60 never trade in any session (64 of 128 cells empty on NQ, ES and GC). The 60 % rule can therefore never pass for donchian tf 30.
   - donchian tf 15: n 60 trades only in pm, n 40 only from 10:15.
   - squeeze bbkc tf 30: from 11:30 only.
   - orb: asia and eve need or_min ≥ 3 × tf.
   - straddle: never trades asia or eve (ATR not warm at the session start, as in the tester).

   Suggested fix, without looking at P&L: exclude cells with zero trades in a session from that session's denominator. That is a `library.py` change, not mine to make.
2. **ib and gap variants are opposite hypotheses in one unit** (break vs fade, fill vs go). A plateau over all cells of the unit is biased to fail; judging per mode would be fairer.
3. **ib fade and gap fill ignore the menu's target** (their target is the IB mid / prior close), so each stop has 4 identical cells that the plateau counts 4 times.
4. **straddle overlaps `straddle_t`** at tf 30 london / nyam / pm (same trades as 03:00 / 09:30 / 13:30). Do not admit both as separate members. The ported straddle has no fixed-point offsets and no time-shuffle null; its control is the random-entry one.
5. **ib, gap and lon_break are equity-session ideas** (09:30 open, London range). They run on GC as the spec says, but the rationale is weaker there.
6. **gap** is not marked weak (EDGE_SPEC does not say so), though the old pilot found it thin or negative; the note says so.
7. **Pre / eve sessions, percent stops and the menu's fixed-point stops** on these families cannot be checked against the tester.
8. **Disclosure:** my first look at the old pilot's ledger printed two calibration rows with their in-sample net (ema_pullback and one orb cell). Nothing was decided from it; all later reads used identity columns only.

## Files (all under `/Users/ramoscapital/ramos-quant-homebase/research/edge-library/`)
- `engine/families/port1.py`
- `engine/port1_gate.py`
- `engine/PORT1_VALIDATION.md`
- `engine/out/port1_gate.json`
- `engine/tests/test_port1.py`
- `progress.md` (one line appended)

Nothing was written outside this directory, nothing committed, no tester jobs, `ledger.csv` untouched.