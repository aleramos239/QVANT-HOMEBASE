# PORT3_NOTES — vwap_band, vwap_z, vwap_flip, pinbar, sweep_rev (families/port3.py), for the Run / Admit agents

Written 2026-10-02 by the port3 author, BEFORE any menu run. Nothing here is a result: counts and structure only.

## What is registered
| family | variants (first axis of its R heat-map) | tfs | complexity | both sides | roots |
|---|---|---|---|---|---|
| vwap_band | band 1.5 / 2.0 / 2.5 / 3.0 (R/tune1 `hm-vwap_band-tf5`) | 1, 5, 15, 30 | 3 | no | NQ, ES, GC |
| vwap_z | zth 1.5 / 2.0 / 2.5 / 3.0 (R/tune1 `hm-vwap_z-tf5`) | 1, 5, 15, 30 | 2 | no | NQ, ES, GC |
| vwap_flip | hold 1 / 2 / 3 (R/tune1 `hm-vwap_flip-tf15`, R/tune2 `hm2-vwap_flip-tf1`, `-tf5`); anchor stays `session` | 1, 5, 15, 30 | 4 | no | NQ, ES, GC |
| pinbar | wick 0.6 / 0.667 / 0.75 (R/tune2 `hm2-pinbar-tf5`) | 1, 5, 15, 30 | 5 | no | NQ, ES, GC |
| sweep_rev | levels both / pd / on (R/tune2 `hm2-sweep_rev-tf5`) | 1, 5, 15, 30 | 4 | no | NQ, ES, GC |

Unit grid = variants × 32 exit cells: 128 cells (vwap_band, vwap_z), 96 (vwap_flip, pinbar, sweep_rev) per family × root × tf.
Four tfs × three roots = 12 units per family; 6,528 base cells for the group (2 × 1,536 + 3 × 1,152), before the C1 nulls.
Class bodies are `R/families/<fam>.py` verbatim; every entry is a market order at a tf close (no resting entry, no OCO).

## Proof
* `PORT3_VALIDATION.md` (`python port3_validate.py`): every in-sample tester bundle of the five families, NQ and ES, trade for trade.
* `tests/test_port3.py`: verbatim-body check, scripted trigger semantics, one tester month, an independent first-signal oracle in
  all seven sessions (also `pre` / `eve`), garbage-after-cut (no look-ahead), 1-vs-8-worker identity, the counts-only smoke.
* `out/port3_smoke.log`: the 30 smokes (5 families × NQ tf 1 / 5 / 15 / 30, ES tf 5, GC tf 5), 10 BUILD days each, counts only.

## Structural facts to know BEFORE reading a plateau table (not bugs, not evidence)
The plateau rule counts a cell without a trade as "not > 0". These unit-sessions are empty or part-empty BY CONSTRUCTION
(the families' own rules, unchanged from R; the tester draft behaves the same in its five sessions):
1. **vwap_band, vwap_z at tf 30 in `nyam` and `pre`: never a trade.** Both need 3 tf closes inside the session; in nyam
   (09:30–11:00) and pre (08:25–09:30) the 3rd half-hour close is the session end, where no entry is allowed.
2. **vwap_flip at tf 30 in `nyam` and `pre`: never a trade** (a cross needs a prior close in the session, then `hold` ≥ 1 more).
3. **sweep_rev `levels=on` in `eve` and `asia`: never a trade** (there is no overnight range there) → a third of that
   unit-session's cells are empty, so at most 66.7 % of its cells can be > 0. `levels=pd` / `both` trade there on prior-day levels
   only, and not on contract-roll days.
4. **pinbar** uses the overnight high / low in nyam / mid / pm only (as R wrote it: "NY sessions only") — not in `pre`,
   `london`, `asia`, `eve`. Prior-day H / L / C and the session VWAP count in every session.
5. At tf 15 / 30 the first tf bar that closes inside `pre` (08:30) started before 08:25: the signal is taken at a close inside the
   session on a bar that began before it (the Template's rule for every session; no future data).
6. High thresholds at slow tfs are sparse: on the 10 smoke days `band 3.0` / `zth 3.0` had no trade at all at tf 15 and tf 30
   (trade counts per variant fall 63 / 32 / 10 / 0 for vwap_band tf 15): expect thin or empty cells there, and the ≥ 100-trade rule.

## Flags for admission
* **SECOND LOOK**: holdout-stage tester jobs exist in the old pilots for `vwap_z` tf 5 (R and RE `jobs.jsonl`, keys `ho-vwap_z-tf5-*`) and
  for `vwap_flip` tf 5 / tf 15 on ES (RE, keys `ho-vwap_flip-*`). EDGE_SPEC user rule 3 does not list them among the finalists; their
  exam is nevertheless a second look and must be labelled. (Keys only were read; no holdout bundle was opened.)
* **vwap_flip**: EDGE_SPEC B says this family did not survive the old NQ pilot. It is registered with `weak: False` because the spec
  marks only `straddle_t` 00:00 and `vwap_ema_x` as weak; the orchestrator may set `"weak": True` (one line in `families/port3.py`,
  then re-run `port3_validate.py`: the gate report is tied to the file's hash).
* **GC**: no GC tester bundle exists for any family; these five are tester-matched on NQ and ES only.
* `pre` / `eve` and the percent stop cannot be run in the tester: their proof is `tests/test_port3.py` (oracle + look-ahead + parity).
