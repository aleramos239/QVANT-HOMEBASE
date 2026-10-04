# Inverse direction (pre-registered 2026-10-02, BEFORE any run; user: "try the opposite, long when we should short and vice versa")

The two direction rules, with the side flipped. Everything else identical to SPEC.md / SPEC_flow.md / SPEC_1to3.md:
- `imb_inv`: at 09:30:00, top-10 imb10 > 0 (bids heavier) -> SHORT; < 0 -> LONG; 0 / no book -> no trade.
- `flow_inv`: 15-min pre-open summed f_delta > 0 (buyers heavier) -> SHORT; < 0 -> LONG; 0 / < 8 finite minutes -> no trade.
- Brackets: 25 stop / 50 target (1:2) AND 25 / 75 (1:3), 2 NQ, flat 15:58 ET, 2021-09..2024-12 only (2025+ sealed).
- Controls: 20 C2 nulls per rule per bracket (the signal replaced by a random other day's value, then inverted), plus the
  always-long / always-short controls already run on the same days.
- Verdict: informative ONLY IF (1) win rate >= the 95th percentile of the 20 nulls, (2) net > 0 at 2 NQ after costs,
  (3) win rate above the null mean in >= 3 of 4 years.
CAVEAT, fixed now: the inverse is chosen AFTER the original direction rules were seen not to beat their nulls, so each rule
has now been looked at in both directions (2 tests per rule per bracket, 8 in total). A pass is a LEAD that needs fresh data,
never a result. If a signal carries no information its inverse carries none either; the original runs had win rates at the
null mean (book 32.4% vs 32.0%, volume 31.7% vs 32.1% at 1:2), so the expectation is no pass.
One run per rule per bracket, no retune.
