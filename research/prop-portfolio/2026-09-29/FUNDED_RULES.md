# Funded / PA rules (user-provided 2026-09-30, from the firms' pages) — 50K accounts

## LucidFlex funded (50K)
- MLL $2,000, EOD trailing on highest closing balance; locks at $50,100 once balance exceeds $52,100;
  after ANY payout request the MLL moves to the locked $50,100. Breach: "account balance reached the MLL".
- DLL optional (chosen at eval purchase) — model both (none / $1,200 soft like Pro; flag the value as assumed).
- Scaling plan (updates at END of session, by simulated profit): $0–999 → 20 micros (2 minis); $1,000–1,999 → 30;
  $2,000+ → 40 (4 minis). After a payout the tier follows the reduced profit.
- No consistency rule, no buffer.
- Payout eligibility per cycle: ≥ 5 separate days with profit ≥ $150 AND cycle net profit > 0. Both reset after payout.
- Payout amount: min $500; max = 50% of profit (account balance − 50,000) up to $2,000 (no growth later).
- Up to 5 payouts per account, then moved live (stop the sim at 5). Split 90% trader / 10% Lucid.
- Payout requests any day once eligible; disbursed within 2 business days.

## LucidPro funded (50K)
- MLL $2,000 EOD trailing, trail balance $52,100, locks at $50,100. Breach on balance reaching MLL.
- Fixed DLL $1,200 (optional; chosen at purchase; soft = stops the day) while balance < $52,100.
  "Scaling DLL = 60% of peak EOD balance" also optional (ambiguous; skip, list as gap).
- Max size 4 minis / 40 micros, NO scaling plan.
- Payout eligibility per cycle (reset after each payout):
  1) cycle profit ≥ $500 (minimum profit goal);
  2) 40% consistency: largest single-day profit in the cycle ≤ 40% of total cycle profit;
  3) buffer: payout only from profit above $52,100 (balance after payout ≥ $52,100).
- Payout min $500 (needs balance ≥ $52,600). Max payout 1 = $2,000 (needs $54,100); payouts 2+ max $2,500 (needs $54,600).
- Split 90/10. Request any day once eligible.

## Apex Legacy PA (50K) — site research + user paste
- Trailing drawdown $2,500, INTRADAY trailing on equity incl. open P&L (Legacy product), stops at start + $100 ($50,100).
  Breach in real time.
- Contract scaling: HALF of max contracts (5 minis / 50 micros of 10 / 100) until the EOD balance exceeds
  $52,600 (initial + trailing DD + $100); full size from the next session.
- 30% negative P&L (MAE) rule: open unrealised loss at any moment ≤ 30% of the start-of-day PROFIT balance
  (50% once EOD profit ≥ 2 × safety net = $5,200). The paste does not say what applies when profit is ~0:
  ASSUMPTION (flag): limit = 30% × max(start-of-day profit, $2,500 drawdown) = $750 minimum. Model as a
  forced cut of the trade at that open loss (and count cuts); a config whose trades routinely hit it is non-compliant.
- 5:1 risk-reward rule: stop ≤ 5 × profit target on every trade → only configs with tgt_r ≥ 0.2 AND a target
  (tgt_r > 0); time/trail-only exits are NON-COMPLIANT for Apex (flag).
- One-direction rule: no working orders on both sides → OCO/bracket families (straddle, orb OCO, lon_break,
  squeeze nr7/inside, ib break) are NON-COMPLIANT for Apex (eval and PA).
- Prohibited: using the trailing threshold as a stop; small target vs disproportionate stop (e.g. 5 vs 150 ticks);
  stockpiling evals to blow up. → fast-pass coin-flip structures are not recommendable at Apex.
- Payout: ≥ 8 trading days since start/last payout; ≥ 5 of them with profit ≥ $50; 30% consistency (highest day
  ≤ 30% of total profit balance at request); safety net for payouts 1–3: balance ≥ $52,600 to request $500, and
  every $1 above $500 needs $1 more balance (post-payout balance ≥ $52,100); min $500, max $2,000 for payouts 1–5.
  Split 100% of first $25k. The trailing DD stops at $50,100.
- Apex Legacy EVAL (site): $3,000 target, $2,500 intraday trailing (peak incl. open P&L), 10 minis; same
  prohibited-strategy rules. (User's earlier rule set said $2,000 EOD — conflict; score both, flag.)

## Funded objective (user): "good payout %, high payout, low payout time"
Report per firm × config: P(≥1 payout within 20/40/60 trading days), median days to first payout, E[first cheque],
E[total paid to trader within 60 trading days] (after split), P(bust before first payout), E[payouts before bust or
cap (5 for Flex)]. Primary objective = E[$ paid to trader within 40 trading days]; show the P(payout)/days/cheque
frontier too. Payout-request policy is a search dimension (request as soon as eligible at ≥ $500 vs wait for
cheque ≥ $1,000 / $1,500 / max).
