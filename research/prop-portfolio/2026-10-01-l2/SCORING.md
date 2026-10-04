# SCORING.md — how to score an L2 config (one page for the screening agents)

`score.py` turns trade lists from `l2sim` into the previous pilot's (R) eval / funded / control numbers, **bit-identical to R**
(verified cross-process on bundles the builder never used: `tests/test_score_verify.py`). Never call R's functions directly.

```python
import sys; sys.path.insert(0, "<L>")          # L = ~/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2
import l2sim, score as S                        # python: "~/ONYX TRADING/.venv/bin/python"
res = l2sim.run(Fam, params, features=l2sim.L2Features(cols))          # full in-sample run (825 sessions, 820 used)
```

**Trade source** (`trades` everywhere): an `l2sim.run` result dict (preferred: its range is honoured and a result with
`skipped_by_error > 0` is refused), `res["trades"]`, `"file:<name>"` (= `L/trades/<name>.json`), a bundle directory from
`l2sim.write_bundle`, an R run id / `grid#cell`. Portfolio = `[{"src": ..., "sess": "nyam", "micros": 20}, ...]`.
`sess`: `"all"`, one of asia/london/nyam/mid/pm, or several (`"nyam+pm"` or a list). Trades are per 1 NQ; sizing is `micros`.
A sim result / bundle that simulated fewer sessions than the calendar of its run range (a `days=` subset run) is **refused**
unless you pass `calendar=days` (ENFORCED since 2026-10-02; a bare row list cannot be checked). An in-memory sim result is named
`<Class>|k=v,...` from its meta (the C1 seed follows the name); a screen bundle is named by its key. 2025+ rows always raise
(`HoldoutError`). Screen bundles: `runs/<key>/` (`screen.py`), e.g. `S.score_eval(str(L / "runs" / "bimb_follow-tf5"), ...)`.

## Eval (firms `lucid`, `lucidpro`, `lucidpro_nodll`, `apex`, `apex_eod`)
| call | returns |
|---|---|
| `S.score_eval(trades, firm, rules, micros=40, sess="nyam")` | `p1..p5` (P(pass ≤ k days)), `bust5`, `ci_p5`, `models[eod|realized|intraday]`, `walk`, `cost` |
| `S.search_rules(trades, firm, sess="nyam")` | R's pass-3 grid (micros × day_lock × day_take × day_stop × max_day_tr × target_take): `rows`, `picks["primary"]` (stable-P5 cell), `picks["speed_p1"|"speed_p3"]` |
| `S.walk_forward([cfg1, cfg2, ...], firm, sess=, control_pool=pool)` | R's quarterly walk-forward of one family grid: `rows` = OOS P5, OOS lift vs C1, CIs |

`rules` keys: `day_lock, day_take, day_stop, max_day_tr, target_take` (0 = off; `target_stop` is on, as in R's searches).
Headline model = the firm's primary (**Lucid: realized; Apex: intraday**); always report `models["intraday"]["p5"]` next to it
(the tie-break). Criterion: P5 ≥ 0.60 on the primary model AND ≥ the approved pick AND lift > 0 vs C1 and C2.

**Apex Legacy 300K evaluation (firm `apex300_eval`)** — $20,000 goal at a close, $7,500 threshold trailing the highest LIVE
balance (open P&L included, no lock), 350 micros, 7 traded days, Apex commissions; the 5-day criterion cannot apply:
| call | returns |
|---|---|
| `S.score_eval(trades, "apex300_eval", rules, micros=200, sess="nyam", strategy=, inputs=, both_sides=)` | `p_pass_10`, `p_pass_20` (= `p10`, `p20`), `bust_10`, `bust_20`, `med_days`, `ci_p10 / ci_p20 / ci_bust20`, `models[pess|nat|opt]` (headline `pess`), `coast1` (1 micro once the goal is reached and days are missing), `variants` (`holder_rule_file` = homebase's apex-legacy-300k rule file: EOD trail, lock +$100, 1 day; `min_days_1`; `trail_eod`), `compliance` = `{one_direction}` |
| `S.search_rules(trades, "apex300_eval", sess=)` | `S.APEX300_EVAL_GRID` (1,008 cells, seconds): `rows`, `picks["primary"]` (stable P(pass ≤ 20 d)), `picks["p10"]`, each with `detail` |

Rule keys as above; `target_take` stops the day at the goal once the day count allows a pass; `target_stop` is not modelled.

## Funded (firms `flex`, `flex_dll`, `pro_dll`, `pro_nodll`, `apex`, `apex300_pa`, `apex50_pa`)
| call | returns |
|---|---|
| `S.score_funded(trades, firm, policy, micros=, rules=, sess=)` | `e_net_40` (E[$ to trader in 40 trading days]), `e_net_40_ci`, `p_pay_20/40/60`, `p_bust_pre_first`, `med_days_first`, `models[...]` |
| `S.score_funded_starts(trades, "apex300_pa", policy, ...)` | the same from every start state: `{"fresh", "plus3000", "plus7600"}` (`S.start_states(firm)`; `start=` also takes a profit in $) |
| `S.search_funded(trades, firm, sess=, workers=6, start="fresh")` | grid (micros × day_take × day_lock × day_stop × max_day_tr × policy): `rows`, `eligible`, `picks["e40_stable"]`; grid = `S.funded_grid(firm)` |

`policy` = payout-request threshold (`500 | 1000 | 1500 | "max"`; apex300_pa `500 | 1500 | 2500 | "max"`). `flex … apex` are R's
frozen semantics (use them to compare with the approved picks). **`apex300_pa` = the user's five Apex Legacy 300K PAs**
(`apex300.py`, APEX300_RULES.md): conservative rule readings by default, Apex commissions, start states (the desk shows all five
at $300,000 → **`fresh` is the real state**; plus3000 / plus7600 are sensitivities), and the other reading of the unconfirmed
consistency base in `cons_alt` (search rows: `e_net_40_cons_balance`). Select on the default (conservative) numbers.

**Apex compliance gate (mandatory, fail closed; proof-based since 2026-10-02).** Result: `compliance = {one_direction,
stop_5x_target, mae_rule}` each `ok | FAIL | UNCHECKED`, `compliant`, `apex_flags`, `one_direction_basis`. Anything UNCHECKED
is non-compliant; `search_funded` keeps only `apex300.compliant(rows)`.
* `one_direction` is **proven by the rows, not by your word**: an `l2sim` result / screen bundle carries the simulator's stamp
  on every row (`both_sides`, `oco`) and its `both_sides_sessions` → `ok` (basis `sim_rows`) or `FAIL` without any argument.
  Tester bundles carry no stamp: `ok` (basis `market_entries`) needs `both_sides=False` AND market entries only; a tester
  family with resting entries stays UNCHECKED until it is replayed through l2sim. `both_sides=True` and R's OCO families
  (`strategy=`) always FAIL.
* `stop_5x_target`: every row needs `sl` and `tp` with stop ≤ 5 × target from the fill, **no tolerance** (a family with
  `tgt_r` 0.2 can fail on tick rounding; a family without a target, e.g. O1 as pre-registered, fails). Pass `inputs=` (the
  family inputs incl. `tgt_r`) and `strategy=` as before: a `tgt_r` < 0.2 in `inputs` fails whatever the rows say.
* `score_baseline(name)` hands `BASELINE_META` to the gate itself (the approved Apex 50K PA pick is compliant).
The 300K grid, flags and thresholds are
`apex300`'s (a $2,250 day stop is fine on a $7,500 threshold), never R's 50K constants. Apex bans automation on PA accounts:
an apex300 pick must be simple enough to trade by hand and is labelled so (see `warnings` in the result).

## Controls (promotion needs lift > 0 against BOTH)
**C1 day-matched random entries** — same exit profile, same trade count per (date, session), K seeded draws:
```python
pool = S.c1_pool({"tf": "5"})                   # R's random-entry pool for the exit profile (tf, stop, tgt_r, exit_bars, trail)
lift = S.lift_vs_control(res, pool["srcs"], "lucid", rules, micros=40, sess="nyam", label="<config name>")      # eval
lift = S.lift_vs_control(res, pool["srcs"], "apex300_pa", rules, micros=90, sess="nyam", kind="funded", policy=2500, label=...)
```
→ `lift`, `ci`, `lift_gt0`, per model in `models`, plus `fallback_share` / `short` (draw quality) — report `pool["flag"]` when the
pool is not `exact`. Always pass `label` (an unnamed list shares one seed with every other list). C1 matches the day and the
session, not the minute: for clock-time families (O1 `open_dir`) the timing-matched control is C2.

**C2 feature-shuffle null** — the same family, same params, same simulator, with its L2 features replaced by the same
time-of-day values of a random other session (bijection, ≥ 5 sessions apart, in-sample donors only):
```python
cols = ["imb10", "depth10_rel20d", "f_delta", "f_c"]                  # everything the family reads through ctx.feat
null = [l2sim.run(Fam, params, features=S.C2Features(cols, seed=k)) for k in range(1, 6)]          # K >= 5
lift = S.lift_vs_control(res, null, "lucid", rules, micros=40, sess="nyam", mode="direct")
```
`C2Features` shuffles every feature column it loads and leaves prices / anchors / flags (`f_o f_h f_l f_c`, `bid_px ask_px`,
`book_ok` …) as the receiving session's own; asking it to shuffle a price raises. Check `out["ctrl_trades"]` against the real
trade count. Robustness for finalists: `S.C2Features(cols, seed=k, strata="year")` (donors from the same year).
Gates on approved trade lists (G1–G3; `gates.py`, FAMILIES.md "Gates" + its addendum): the control is the gate's own
permutation null (`runs/gate_<pick>_<G>-perms<seed>/`: the same gate on `S.C2Features(cols, seed)` read through `l2sim.Ctx`,
count-matched per session). Score through `gates.cell(pick, gate, slot)` → `gates.score_cell` / `gates.lift_cell`: a G3 bundle
is a PORTFOLIO of its size-tier bundles (never its half-unit rows, which have no `trades.json`), and `lift_vs_control` (one
source) cannot take it.

## Baseline to beat (in-sample 2021-09-22 → 2024-12-31; `python score.py baseline` → `out/baseline_insample.json`)
| slot | approved pick | cell | in-sample bar |
|---|---|---|---|
| Flex eval (`lucid`) | straddle-tf30#10 nyam | m40, lock 750, take 1500, target_take | P5 0.692 (intraday 0.010) |
| Pro noDLL eval (`lucidpro_nodll`) | straddle-tf30#10 nyam | m40, lock 1000, target_take | P5 0.706 (intraday 0.228) |
| Flex funded (`flex`) | straddle-tf30#32 pm | m40, take 600, lock 300, T1500 | E$40 3,330 |
| Pro noDLL funded (`pro_nodll`) | orb-tf5#10 mid | m40, take 1000, lock 300, T1000 | E$40 5,426 |
| Pro DLL funded (`pro_dll`) | donchian-tf15#10 pm | m30, lock 600, T1500 | E$40 1,996 |
| Apex 50K PA (`apex`) | donchian-tf15#1 nyam | m30, take 1000, lock 1000, T1000 | E$40 1,093 |
| **Apex 300K PA** (`apex300_pa`, fresh) | donchian-tf15#1 nyam (the 50K PA pick's strategy) | m100, take 3000, lock 3000, Tmax | **E$40 2,111**, P(bust before 1st payout) 0.56 |

Lucid Pro DLL eval and Apex eval have no approved pick (bar = the 0.60 criterion). `S.score_baseline(name)` re-scores one pick
(`S.BASELINE`); `S.score_baseline_apex300(search=True, workers=6)` re-scores the approved strategies on the 300K PA. Straddle and
ORB are OCO families: non-compliant at Apex, never the 300K bar.

Apex 300K PA bar per start state (model `pess`, conservative readings; in brackets the other consistency reading):

| start | E$40 | P(payout ≤ 40d) | P(bust before 1st payout) | from |
|---|---|---|---|---|
| `fresh` (the real state) | 2,111 (2,751) | 0.41 | 0.56 | fp-donchian-tf15#1 nyam, m100, take 3000, lock 3000, Tmax; grid search (e40_stable) |
| `plus3000` | 2,826 (3,660) | 0.53 | 0.46 | fp-donchian-tf15#1 nyam, m90, take 3000, lock 3000, T2500; fixed cell x3 |
| `plus7600` | 3,427 (3,878) | 0.72 | 0.21 | fp-donchian-tf15#10 pm, m30, take 1000, lock 1000, T500; fixed cell x1 |

The 300K grid was searched for `fresh` only; plus3000 / plus7600 are the fixed cells `x1` (the 50K pick's cell) and `x3` (scaled ×3). A candidate for the 300K PAs must beat the `fresh` row with its own `search_funded(..., "apex300_pa")` pick and pass the gate.

## Checklist
1. Run the family on the whole in-sample window; `res["skipped_by_error"] == 0` and `res["unrealistic_winners"] == 0`.
2. Score eval firms with `search_rules` (≤ grid caps), funded with `search_funded`; quote the pick's cell and all three models.
3. C1 and C2 lifts at the SAME micros + rules as the pick; K ≥ 5 nulls; report lift, CI and control trade counts.
4. Apex firms: `strategy`, `inputs` (and `both_sides` for tester bundles) on every call; quote `compliance`,
   `one_direction_basis` and `cons_alt`. Apex evaluation: `score_eval(..., "apex300_eval")` → P(pass ≤ 10 / 20 d), bust.
5. Compute windows (09:18–09:36 ET weekdays; Fri 2026-10-02 08:15–08:50) are waited out by the searches; ≤ 8 workers.

CLI: `python score.py eval|funded|search <trades> --firm F [--sess S --micros N --rules '{...}' --policy T --start all
--strategy fam --inputs '{...}' --one-direction|--both-sides]`, `python score.py baseline [--search --workers 6]`.
