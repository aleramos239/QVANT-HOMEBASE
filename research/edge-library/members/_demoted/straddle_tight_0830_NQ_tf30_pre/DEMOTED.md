# Demoted — 2026-10-04 (independent checker out/check_r1/, confirmed by the orchestrator)
1. It passed only a bar reading that differs from stage 1's: t 1.98 vs 2.56 under the unchanged stage-1 rule (all 26 NQ
   random-minute replicates), and vs the 2.02 NQ random-entry bar. Under the unchanged rule round 1 admits nothing.
2. Its whole profit ($13,352 of $13,823) is trades that open and close within 2 seconds at 08:30, and it needs the stop entry
   to fill ON the trigger print. Entry filled 1 ms later: BUILD $8,954 -> $3,624, 2024 $4,869 -> $729. 25 ms later: $239 / -$3,281.
3. Stress: 2 ticks alone takes 2024 from $4,869 to $974; at 3 ticks 2024 is -$361.
Same 08:30 idea as orb_NQ_tf1_pre (same side on 78.5 % of shared days).
