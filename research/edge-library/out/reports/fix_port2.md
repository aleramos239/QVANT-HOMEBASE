**Port group 2 is fixed as far as an author can fix it: `tod_drift` is now marked weak, the tester-match gate was re-run cleanly and passes at 100 %, and the full suite is green.** One major — how `tod_drift`'s plateau is judged — needs your decision before the BUILD run. No menu was run, the ledger is empty, no P&L was read, and nothing dated 2025 or later was touched.

## Decisions needed before the BUILD run
1. **`tod_drift` plateau.** Read literally, EDGE_SPEC puts long and short of the same clock time in one 256-cell unit. Under the family's own drift hypothesis about 50 % of cells can be positive at best, against the 60 % bar. I left the registry literal. The three options are prepared, none switched on:
   - **A, literal (default):** a foregone fail, costing 3,072 cells (1,024 on NQ).
   - **B, per direction:** `port2.plateau_sets("tod_drift", table)` gives a long set and a short set of 128 cells each; that is two looks per unit-session.
   - **C, drop the family.**
   
   Port group 1 has the same trap in `ib` and `gap`; one rule for all three would be best.
2. **`tod_drift` weak flag.** I set `weak: True` (admission needs t ≥ 3 on BUILD) because its rationale names no counterparty — the old source calls it a "control for pure clock effects". To waive it, delete that one line and the matching pin in `tests/test_port2.py`; the gate stays valid.
3. **Penalty for the other second-look families.** `ema_pullback`, `rsi2`, `tod_drift` and `tema_slope` (ES) also had 2025-26 read by the old pilots. Whether their favourites failed is sealed to me, so only `first_bar_mom` carries the penalty.
4. **Rationales of `ema_ribbon`, `tema_slope`, `ema_pullback`, `supertrend`** restate the trigger. They are the old docstring sentences, written before the old screen ran, and of the same kind as EDGE_SPEC's own examples. I left them not weak; accept or mark weak.
5. **`tod_drift` runs as the tester draft ran it**: every screen tf, ATR(14) of its own tf, and the C1 random-entry control rather than the time-shuffle null. Its four tfs share the same entry prints, so they are four correlated looks.
6. **Engine owner:** `library.card` and `spec.json` have no field for the second-look label, so the Admit stage must add `port2.second_look(family)`. I did not touch `tests/test_families.py`; the earlier stricter edit still awaits confirmation.

## What changed
- **`families/port2.py`**: class bodies are untouched (the trading-code hash equals that of the pre-edit file). Added:
  - `weak: True` on `tod_drift`;
  - `SECOND_LOOK` and `second_look(name)`, built from the old holdout job keys only;
  - `MIRROR_AXIS`, `can_trade(family, variant, tf, sess)` for cells with zero trades by construction, and the `plateau_sets` / `tradable` splits;
  - docstring notes on the inherited semantics: the mirror, the 6-bar exit, supertrend starting each restart "up", the 08:30:00 market entry of `first_bar_mom` in `pre`, and the complexity counting rule.
- **`port2_validate.py`**: file hashes are read before each pass and checked after it, and the gate aborts if a file changes under it. It also records a trading-code hash that ignores metadata and docstrings, and lists which tester cells matched each registered variant.
- **`tests/test_port2.py`**: 29 → 39 tests.
  - An independent first-signal oracle (no Template) covers all seven sessions on NQ, ES and GC, checking side, entry print, fill, stop and target for atr, pts and pct stops, plus `tod_drift`'s 6-bar exit. These are the paths no tester bundle covers. Two deliberately broken families and a wrong oracle are caught.
  - The gate report is tied to the code on disk.
  - The parity test's worker count now drops by itself on a busy machine.
- **`PORT2_NOTES.md`** (new): the decisions above, the structural-empty tables, and the execution-realism flags.

## Results
| check | result |
|---|---|
| Tester-match gate (`--fresh`, 2 workers) | 93 bundles, 776 runs + cells, 4,408,308 trades, all identical, net diff $0, one hash on every row |
| Registered variants | every one matched by at least 5 tester cells |
| Oracle | 0 mismatches on NQ, ES, GC (10 BUILD days each) |
| `tests/test_port2.py` | 39 passed |
| Full engine suite (2 workers) | 1,294 tests: 1,292 passed, 2 skipped by design, 0 failed |
| Smokes (counts only) | 48 of 48 ok, same trade counts as before the edit |

## Open risks
- GC has no tester bundle; the oracle covers it but is not the tester. Keep GC members flagged.
- `first_bar_mom` in `pre` at tf 5 / 15 / 30 enters by market order on the 08:30 data release; the 2 ticks + 250 ms stress is the decisive number there.
- Cells that cannot trade lower plateau ceilings. `tod_drift` in eve / asia can trade in 75 % of cells at tf 1 / 5, 25 % at tf 15 and none at tf 30. Several other unit-sessions are empty outright (`first_bar_mom` eve / asia, `ema_pullback` tf 30 before 10:00).
- `mid_fade` is sparse (289 trades per tf on NQ over the in-sample window), close to the 100-trade rule.
- I killed and relaunched the first gate launch within seconds to detach it; the log was cleaned of that attempt's tracebacks. Other agents ran up to 9 processes at times; my own footprint stayed at 3 or fewer.

## Files (under `/Users/ramoscapital/ramos-quant-homebase/research/edge-library/`)
- `engine/families/port2.py`
- `engine/port2_validate.py`
- `engine/PORT2_VALIDATION.md`
- `engine/PORT2_NOTES.md`
- `engine/tests/test_port2.py`
- `engine/out/port2_validation.json`
- `engine/out/port2_validation.partial.jsonl`
- `engine/out/port2_validate.log`
- `engine/out/port2_smoke.jsonl`
- `engine/out/port2_smoke.log`
- `progress.md` (one line appended)

Unrelated to this task: the `plugin:nimble:nimble` MCP server needs authorization (via `/mcp`) before its tools can be used.