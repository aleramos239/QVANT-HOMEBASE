{
 "ok": true,
 "issues": [
  {
   "severity": "minor",
   "desc": "Not flagged by the author: many port1 cells are exact duplicates of a cell in another unit. For orb (all 3 variants), ib break and lon_break min_rng_atr 0, the tf only changes the ATR stop, so the 24 fixed-point and percent exit cells give identical trades at tf 1 / 5 / 15 / 30. That is 1,080 of the 7,680 port1 cells (360 per root). A further 576 cells are redundant because ib fade and gap fill ignore tgt_r (the author flagged that part). library.py has no dedupe, so the same trade list can pass a plateau and be admitted up to four times. The plan is 37,824 cells + 768 C1 = 38,592 of the 40,000 cap, so the waste matters for stage D. Orchestrator decision before the Run stage (dedupe by trade list at admission; optionally run these cells at one tf).",
   "evidence": "My 6-BUILD-day replay, 1 worker (identity only). orb or_min 15 and 30, pts 20 and pct 0.10: 30 / 30 / 24 / 24 trades at tf 1 / 5 / 15 / 30, every one identical to tf 1 (tf 15 / 30 lose only the warm-up-dead asia session). ib break 10 / 10 / 10 / 10 identical; lon_break 6 / 6 / 6 / 6 identical. With ATR 1.5 stops: 0 identical. `run_menus.py plan`: 279 units, 37,824 cells. Tgt_r: l2sim.Template._tp returns tp_px whenever it is given.",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/edge-library/engine/families/port1.py"
  },
  {
   "severity": "minor",
   "desc": "Confirmed and quantified the author's open risk 1: by warm-up arithmetic, 25 of 132 in-scope unit-sessions per root can never reach 60 % positive cells, because library.plateau counts a zero-trade cell as not > 0. This must be decided BEFORE any BUILD number is seen; changing the denominator afterwards would break pre-registration. It is a library.py / spec decision, not a port1 defect.",
   "evidence": "Computed with the test's own warm_dead(): plateau impossible for orb tf 15 / 30 asia + eve; straddle asia + eve at every tf; donchian tf 5 asia, tf 15 eve / asia / london / pre, tf 30 in all seven sessions; squeeze tf 30 asia. 2,464 of 13,056 cell-sessions per root are structurally dead. My smoke of donchian NQ tf 30: cells_without_trades 64 of 128, ok true.",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/edge-library/library.py"
  },
  {
   "severity": "minor",
   "desc": "gap fill and gap go are mirror entries on the same trigger, and the one rationale sentence covers both directions. Judged over all cells of the unit (as EDGE_SPEC requires), gap can hardly pass. ib break / fade are different setups but share a unit the same way. EDGE_SPEC names mode as the variant axis, so the registry conforms; the author flagged it (risk 2). Orchestrator decision: judge per mode or accept that gap is pre-failed.",
   "evidence": "port1.py Gap.fam_signal: fill = short if g > 0, go = long if g > 0, same bar, same condition. Rationale: '...it is faded back to the prior close (fill) or followed in its direction (go).'",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/edge-library/engine/families/port1.py"
  },
  {
   "severity": "minor",
   "desc": "The ported straddle carries 3 of the menu's 5 'Straddle entry offsets' (ATR x 0.25 / 0.5 / 1.0; no fixed points) and has no time-shuffle null. This follows PROPER RE-RUN item 4 (first heat-map axis) and the tester draft has no points input, but it departs from 'the same menu for every family'. straddle_t covers fixed-point offsets at 03:00 / 09:30 / 13:30 only; the 08:25 (pre) and 11:00 (mid) starts have none. Author disclosed it (risk 4); needs an orchestrator ruling.",
   "evidence": "EDGE_SPEC line 34 vs port1.py: \"variants\": [{\"off_atr\": 0.25}, {\"off_atr\": 0.5}, {\"off_atr\": 1.0}]; l2ref.Straddle has no off_mode / shift_seed input.",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/edge-library/engine/families/port1.py"
  },
  {
   "severity": "minor",
   "desc": "The SECOND-look label (orb, straddle, donchian) exists only in the free-text registry notes. The member spec and card written by library.py do not carry notes, so the label EDGE_SPEC user rule 3 requires will not reach a member card unless the Admit stage adds it. The registry contract has no key for it, so the author could not do better.",
   "evidence": "library.py 612-613: spec keys = name, family, root, tf, sess, cell, inputs, rationale, complexity, weak, l2, penalty. families/__init__.py LIB_KEYS has no second-look key. run_menus.py 244 stores notes only in the unit's run.json.",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/edge-library/library.py"
  },
  {
   "severity": "minor",
   "desc": "Complexity is not counted the same way across the seven families, against the module's own stated rule ('one per extra condition: filter, session restriction'). ib counts 'NY sessions only' as a rule; lon_break and gap, both nyam-only through fam_filter, do not. Complexity is only the tie-breaker, so the effect is small.",
   "evidence": "port1.py comments: ib 'complexity 6 = IB definition + NY sessions only + ...'; lon_break 'complexity 4 = London range definition + OCO stop entries ... (nyam only, gap-through follow) + minimum-range filter + min_rng_atr'; gap 5 with no session rule counted. test_port1.py pins [3, 5, 3, 5, 6, 4, 5].",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/edge-library/engine/families/port1.py"
  },
  {
   "severity": "minor",
   "desc": "Test gap: in the new pre / eve sessions (which the tester cannot run) the port1 triggers are pinned only by trade counts > 0 and session tags, not by an independent oracle (port3 has one). The five tester sessions are properly pinned (AST identity with R, tester identity on 10 days for every bundle and heat-map cell, defaults / variants / tfs / both_sides / complexity all asserted). I wrote the missing oracle and it found no error.",
   "evidence": "test_port1.py::test_declared_sides_sessions_and_instances asserts only tot[n]['pre'] > 0 and tot[n]['eve'] > 0. My tape oracle, 6 BUILD days: orb range high + tick / low - tick in pre, eve, nyam for or_min 5 / 15 / 30: 50 of 50 trades match. lon_break 6 of 6 and ib break 10 of 10 levels match. donchian first signal in eve and pre (tf 1 / 5, n 10 / 20): 47 day-signals match, 0 mismatch. straddle pre bracket = off_atr x ATR14: 22 of 22 match."
  },
  {
   "severity": "minor",
   "desc": "The '44 smokes, all ok' claim has no log on disk (port2 and port3 left theirs in engine/out), so it cannot be checked. Also, run_menus.smoke reports ok true without requiring any trade. My two re-runs were clean.",
   "evidence": "engine/out holds no port1 smoke log. My smokes (counts only, 10 BUILD days, 1 worker): orb GC tf 5 ok, 5,248 trades across all 7 sessions, both_sides_sessions 10, worker parity true; donchian NQ tf 30 ok, 1,516 trades, both_sides_sessions 0.",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/edge-library/run_menus.py"
  },
  {
   "severity": "minor",
   "desc": "Protocol breach, disclosed by the author: the first read of the old pilot's ledger printed two calibration rows with their in-sample net (2021-2024, which includes PICK), one of them an orb cell. No selection path exists: variants, defaults and tfs are derived mechanically from the tune axes and family_inputs.json, and tests assert that. The gate code and its outputs hold no P&L level.",
   "evidence": "Author's report item 8. out/port1_gate.json row keys hold only counts, net_diff and flags. The gate refuses any bundle whose range reaches 2025 and filters rows to 2021-09-22..2024-12-31."
  },
  {
   "severity": "minor",
   "desc": "Outside port1, on the pre-registration timeline: EDGE_SPEC.md was last written at 10:05:43 ET, yet its text cites a menu amendment at 10:10 ET and the PROPER RE-RUN instruction at 10:25 ET. Harmless today (no ledger.csv, no runs/ directory, 0 cells used), but the stamps in the contract do not match the file.",
   "evidence": "stat: 'Oct  2 10:05:43 2026 EDGE_SPEC.md'; text lines 29 and 41 cite 10:10 ET and 10:25 ET.",
   "file": "/Users/ramoscapital/ramos-quant-homebase/research/edge-library/EDGE_SPEC.md"
  }
 ],
 "summary": "**port1 conforms to EDGE_SPEC: no blocker, no major.** The seven families (orb, straddle, donchian, squeeze, ib, lon_break, gap) are registered as the spec requires, and all tests pass. Three decisions are still needed from the orchestrator before the Run stage.\n\n**Spec check, line by line**\n- **Variants:** each family's variants equal the first axis of its heat-map in `R/tune1.jsonl` / `tune2.jsonl`, which I re-read myself. Donchian uses n 10 / 20 / 40 / 60, as EDGE_SPEC names it.\n- **Defaults and ranges:** identical to the tester drafts in `R/family_inputs.json`.\n- **Timeframes and roots:** tf 1 / 5 / 15 / 30 and NQ / ES / GC for all seven; no Level-2 features.\n- **Menu:** exactly 8 stops \u00d7 4 targets per root, with the right point sizes for NQ, ES and GC. That gives 84 units and 7,680 cells.\n- **Rationale and complexity:** present for every family, each rationale one sentence.\n- **Labels:** donchian carries the 2025-26 penalty; orb, straddle and donchian notes say the exam is a second look. EDGE_SPEC asks for no WEAK label in this group.\n- **Both-sides declarations:** match what the simulator stamps on the trades.\n- **Thresholds:** none tuned; the five copied class bodies are identical to the old family files, and straddle and donchian subclass the engine's reference classes without overriding anything.\n- **Tester-match gate:** `PORT1_VALIDATION.md` was generated on the current code (all four file hashes match). It reports 100 % identity for 28 NQ bundles, 28 ES bundles and 300 heat-map cells; I did not re-run the full-window gate, only its 10-day version inside the tests.\n\n**What I ran** (1\u20132 workers, BUILD days only, nothing written under the project)\n- **`tests/test_port1.py`:** 48 of 48 pass.\n- **Rest of the suite:** 1,211 tests, 1,209 pass, 2 skipped by design, 0 fail. The `test_new_l2.py` failure the author saw is gone.\n- **Smokes (counts only):** orb GC tf 5 and donchian NQ tf 30 both ok.\n- **Independent oracles from the raw tape, 6 BUILD days:** every orb, lon_break, ib, donchian and straddle trigger I checked matched, including the new pre and eve sessions the tester cannot run.\n\n**Decisions for the orchestrator before the Run stage**\n1. **Duplicate cells (new, not in the author's report).** For orb, ib break and lon_break with no range filter, the fixed-point and percent cells give identical trades at all four timeframes. That is 1,080 of the 7,680 port1 cells, plus 576 more where ib fade and gap fill ignore the target.\n   - `library.py` does not dedupe, so the same trades can be admitted up to four times.\n   - The plan already uses 38,592 of the 40,000-cell cap.\n2. **Cells that cannot trade.** By warm-up arithmetic, 25 of 132 unit-sessions per root can never reach the 60 % plateau (all of donchian tf 30, straddle asia and eve, and others). The rule for zero-trade cells must be fixed before any BUILD result is seen.\n3. **Opposite modes in one unit.** gap fill and gap go are mirror trades, so gap can hardly pass a plateau judged over all cells; ib break / fade share a unit the same way.\n\n**Smaller points**\n- The second-look label lives only in free-text notes and will not reach a member card.\n- The ported straddle has 3 of the menu's 5 entry offsets and no time-shuffle null.\n- Complexity is counted slightly inconsistently between ib and lon_break / gap.\n- GC has no tester bundle, and pre / eve sessions and percent stops cannot be tester-checked; both are as the author disclosed.\n- The author's one disclosed look at two in-sample calibration nets had no path to influence the registry.\n\nFiles reviewed, all under `/Users/ramoscapital/ramos-quant-homebase/research/edge-library/`:\n- `engine/families/port1.py`\n- `engine/port1_gate.py`\n- `engine/PORT1_VALIDATION.md`\n- `engine/out/port1_gate.json`\n- `engine/tests/test_port1.py`\n- `library.py`\n- `run_menus.py`"
}