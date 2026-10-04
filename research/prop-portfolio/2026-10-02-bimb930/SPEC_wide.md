# wimb — wide-ladder imbalance at 09:30, both directions, 1:2 and 1:3 (pre-registered 2026-10-02, BEFORE any run)

User idea (2026-10-02): "if there are more orders above [the price] then buy, if there are more orders below then sell, and vice
versa (inverse) too", answered with the WIDER ladder (the top-10 version, `imb10`, was already run: SPEC.md and SPEC_inverse.md).

## Plain-words reason (written before testing)
If much more size is resting below the market than above across the whole visible book (about 10 points each way), buyers
are stacked and sellers are thin, so price should lift; the reverse says it should fall. The inverse reads the stacked side as
a magnet / wall that price gets pulled toward or sold into. Both are tested; neither is assumed.

## Definition (zero tunable parameters)
- `wimb` = (B - A) / (B + A) at the depth snapshot keyed 09:29:00 ET (the book at the end of minute 09:29, usable at 09:30:00),
  B / A = total resting size over EVERY level of the near ladder of the bid / ask side: zero-size slots dropped, then the
  best-first prefix that keeps stepping away from the best by <= 10 points per step (l2data's own near-book rule) with NO 10-level cap.
- Data checks (no P&L): the file has 64 slots per side, ~40 populated near-ladder levels per side; with cap = 10 the code reproduces
  the cached imb10 (max abs diff 1.4e-8 on 79 sessions); wimb vs imb10 on 79 sessions: correlation 0.44, same sign 66%, so it is a
  different signal. Same book_ok mask as every other book feature (roll-block / other-contract days = no trade).
- `wimb > 0` (more size below) -> LONG, `< 0` -> SHORT (`wimb`); inverse `wimb_inv` flips the side. `== 0` / no book = no trade.

## Everything else as before
Market entry 09:30:00, stop 25 pts, target 50 pts (1:2) AND 75 pts (1:3), 2 NQ, one trade per day, flat 15:58 ET, tester cost law,
2021-09-22..2024-12-31 only (2025+ sealed). Controls: always-long / always-short on the same days; 20 shuffled-wimb nulls per
direction per bracket (wimb replaced by a random other day's value at 09:30). Verdict: informative ONLY IF win rate >= null
95th percentile AND net > 0 AND win rate above the null mean in >= 3 of 4 years. One run each, no retune.
Count: this is test #9-#12 of the day on the 09:30 direction question (8 earlier + 4 here); a single pass among them would be a LEAD only.
