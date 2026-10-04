**new_time group report: `straddle_t` (nine clock times) and `vwap_ema_x` are registered, tested and smoke-clean; no menu was run and the ledger is untouched.**

The 1-vs-8-worker identity was only run at 2 workers, because of the 1–2 worker rule for non-RUN agents. At 10 days both settings give one fresh instance per day, so only the process count differs; the verify stage should re-run it at the default 8.

## Files (all under `/Users/ramoscapital/ramos-quant-homebase/research/edge-library/`)
- `engine/families/timed.py` (new)
- `engine/tests/test_new_time.py` (new, 31 tests)
- `progress.md` (one entry appended)

## What was built
**A. `straddle_t`** — one registry entry per time: `straddle_t_1800`, `_2000`, `_0000`, `_0200`, `_0300`, `_0830`, `_0930`, `_1105`, `_1330`.
- The class is the engine's `l2ref.StraddleT` with one added input, `off`, naming the five menu offsets: `atr0p25`, `atr0p5`, `atr1`, `ptsA`, `ptsB`.
- The two fixed-point offsets differ per root (`ptsA` = NQ 10 / ES 2.5 / GC 2; `ptsB` = NQ 20 / ES 5 / GC 4), and the registry only allows one variant list per family. So they are resolved from `l2sim.menu_offsets(root)` at run time.
- A stored run therefore shows `off=<name>`, `off_mode="menu"`; `timed.offset_of(root, off)` gives the numbers that ran.
- Cancel after 60 min, flat at `clock_flat(at)`, `max_tr` 1, tf 30, OCO with `both_sides=True`, time-shuffle null inherited.
- `00:00` carries `weak: True` and "WEAK RATIONALE" in its notes. Complexity 6 (3 rules + 3 numbers).
- The clock is ET all year. The module docstring and the 20:00 rationale state that Tokyo opens at 19:00 ET in US winter; nothing is adjusted.

**B. `vwap_ema_x`** — the EMA(n) of tf closes crossing the VWAP at a tf close inside the session gives a market entry with the cross.
- Variants are n {9, 21, 50} × anchor {session, rth}; tfs 1 / 5 / 15; `max_tr` 3; `weak: True` with "WEAK PRIOR" in the notes; complexity 3.
- The first close of a session only sets the side. An opposite cross does not close or reverse an open trade; exits are the menu's.
- The EMA is the Template's own (seeded at the 00:00 / 18:00 restart, no extra warm-up), as for the ported EMA families.

Each entry carries the EDGE_SPEC rationale sentence, with the source lines quoted in comments.

## Test results
- **`tests/test_new_time.py`:** 31 passed.
  - Registry equals the pre-registration (times, flat times, offsets per root, variants, weak labels, grid sizes 160 / 192).
  - Straddle on synthetic tapes: OCO cancel of the second leg, one trade per day, the 60-minute cancel boundary, all five offsets on NQ / ES / GC, the 18:00 and 00:00 anchors, the roll-day skip.
  - `vwap_ema_x` on synthetic tapes: a hand-computed cross, plus an independent re-derivation from raw prints.
  - Real BUILD days: `straddle_t` is trade-for-trade the engine straddle on NQ, ES and GC; every `vwap_ema_x` trade sits on an independently derived cross.
  - No look-ahead: garbage after 17 cut times changes no earlier decision or trade, and a deliberately leaky family is caught by the same check.
  - DST: the 20:00 fire is 20:00 ET in winter and summer.
- **Full engine suite** (1,256 tests collected, including the other authors' new files): exit code 0 at 2 workers; two skips showed in the progress output.
- **Registry:** `python -m families` shows 0 errors.
- **Smokes (counts only, 10 BUILD days, 1 worker):** all `ok: true` — the nine straddle entries on NQ, ES and GC (27 units), and `vwap_ema_x` on NQ tf 1 / 5 / 15, ES tf 5, GC tf 5. No dropped session, no empty cell, parity holds, the nulls run.
- **`run_menus.py plan`:** 36 units = 14,688 cells including time-shuffle nulls (12,960 straddle, 1,728 `vwap_ema_x`), i.e. 37 % of the 40,000 cap.

## Open risks and decisions for the orchestrator
1. **11:05 has no event in EDGE_SPEC.** I marked only 00:00 weak, as the spec says; the 11:05 rationale and notes state that no event is named. Decide before the menu whether 11:05 should also need t ≥ 3.
2. **`vwap_ema_x` anchors are the same strategy outside mid / pm.** Before 09:30 there is no RTH VWAP, so `rth` falls back to the session start (the old pilot's `anchor` convention). In asia, london, pre, nyam and eve half of the 192 cells are duplicates: the plateau statistics are unaffected, but they cost cells.
3. **Structurally thin `vwap_ema_x` cells.** On the 10 smoke days, tf 15 with n = 50 had no trade in pre or nyam, and tf 5 with n = 50 had one. Such cells will miss the 100-trade bar, and an empty cell counts as "not > 0" in the plateau.
4. **Half days:** NQ / ES have no 13:30 trade, and an open 11:05 trade is closed at the 13:15 early close with `exit_reason` "eod".
5. **Time-shuffle null and session tags:** the null fires within ±90 min, so its trades can carry a different session tag than the real time. Compare a time's cells with the null over all sessions, not per session.
6. **08:30 on data days:** the bracket goes live 85 ms after the release. The 2 ticks + 250 ms stress is the gate, and live slippage on CPI / NFP can exceed it.
7. **Europe DST weeks:** in the 1–3 weeks each March and late October / early November when the US and Europe are on different DST, the Europe opens are 03:00 / 04:00 ET. The 02:00 and 03:00 fires are not adjusted (documented and tested).
8. **One accident:** a stray `cat` in one of my shell commands blocked on stdin, and I killed it with a `pkill` that matches bare `cat` processes of this user. A bare `cat` belonging to another agent at that moment would also have been killed.

Nothing was written outside the edge-library directory, nothing committed, no tester jobs, nothing at or after 2024 read.