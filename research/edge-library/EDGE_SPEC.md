# Edge library + stacks: build spec (shared by every agent) — 2026-10-02

Root `W = ~/ramos-quant-homebase/research/edge-library/`. Engine copy `W/engine/` (copied 2026-10-02 from the L2 pilot
`L = ~/ramos-quant-homebase/research/prop-portfolio/2026-10-01-l2/`; develop ONLY in W/engine — L and the old pilot
`R = .../prop-portfolio/2026-09-29/` (+ ES pilot `RE = .../2026-09-30-es/`) are READ-ONLY). Read first: `L/SPEC.md` (all
override sections at the end), `L/FEATURES.md`, `L/SCORING.md`, `L/SIM_VALIDATION.md`, `R/SPEC.md`, and the vault notes
`~/Obsidian/Vault/30-Projects/Onyx-Trading/{lucid-drawdown-counts-open-losses,edge-must-make-sense,prop-pilot-learnings}.md`.

## House rules
* Never touch the live desk (8850) / `homebase/` code / `~/.homebase`. Never commit. Never place orders. Write only under W.
* Tester jobs only through `R/hb.py` (the single submitter) and only if this spec says so — default: everything runs in the
  offline engine (W/engine/l2sim.py), which reproduces the tester 100%.
* Compute windows: no heavy job 09:18–09:36 ET weekdays. ≤ 8 worker processes machine-wide for this project (other research
  jobs may be running: check `ps` and share).
* Python `~/ONYX TRADING/.venv/bin/python`. Tests under W/engine/tests (pytest, tmp_path only). Suite green when you finish.

## User rules (binding)
1. **Lucid's drawdown counts OPEN losses** → PRIMARY breach model for every firm = `intraday`.
2. **Simple beats clever; the edge must make sense.** Every family has a one-sentence RATIONALE written below BEFORE testing.
   Ties go to the simpler variant. An effect that lives in one threshold / one session without a reason is rejected.
3. **Three periods**: BUILD 2021-09-22→2023-12-31, PICK 2024-01-01→2024-12-31, EXAM 2025-01-01→latest (NQ L2 members: →2026-07-08).
   EXAM is sealed (loaders raise) until the orchestrator says "exam"; it is run ONCE on frozen stacks. NOTE: 2025-26 was already
   seen once for the old pilot's finalists (straddle-tf30 nyam/pm, orb-tf5, donchian-tf15, first_bar_mom, tod_drift) — for those
   the exam is a SECOND look and must be labelled; their real proof is forward paper/shadow trading.
4. Markets: Level 2 features NQ only (OFB history; live = Tradovate 10 levels). Non-L2 members may trade NQ, ES, GC.
5. Caps: full strategy runs ≤ 2,000 · grid cells ≤ 40,000 · walk-forwards ≤ 40 (ledger `W/ledger.csv`). Signal studies
   (no fills) are uncapped but every claim must beat the best-of-all-nulls of its batch.

## Variant menu (PRE-REGISTERED, AMENDED by the user 2026-10-02 10:10 ET before any run — the same menu for every family; nobody adds a variant after seeing results)
* Stops (8): ATR × {1.5, 3} (Wilder ATR14 on the family's tf, or ATR30 for time-fired families) · FOUR fixed-point sizes
  NQ {10, 20, 30, 45} (ES {2.5, 5, 8, 12}, GC {2, 3, 5, 7}) · percent of price {0.10 %, 0.20 %}.
* Targets (4), reward:risk from the stop distance: none (time exit at session end) · 1:1 · 1:2 · 1:3.
  → 32 exit cells per family variant.
* Straddle entry offsets (5): ATR30 × {0.25, 0.5, 1.0} · fixed points NQ {10, 20} (ES {2.5, 5}, GC {2, 4}).
* Position size is NOT a variant: every run is 1 contract; sizing (micros) is chosen later by the account-rules layer so the
  worst open loss fits the firm's limit.
* Judging: never the single best cell. A family/time passes only on a PLATEAU: the median over its menu cells is > 0 after
  costs and ≥ 60 % of cells are > 0; the library member is the plateau's most central / simplest cell.
* Caps (raised with the menu, user-approved): grid cells ≤ 40,000 · full strategy runs ≤ 2,000 · walk-forwards ≤ 40.

## PROPER RE-RUN OF THE PILOT (user 2026-10-02 10:25 ET: "re run the pilot tests ... fix them and do it proper") — binding
This project IS the re-run of the 2026-09-29 NQ pilot (and the ES pilot), with each known flaw fixed:
1. Wrong account rule → `intraday` (open losses count) is the selection model everywhere.
2. Pass-rate shape instead of edge → edge first (library admission on raw 1-contract results), account rules only afterwards,
   and no daily take cap is applied to a member before its uncapped edge is measured.
3. Too few stop variants → the amended menu (8 stops × 4 targets) for EVERY family.
4. One look per strategy → every ported family runs at EVERY screen tf {1, 5, 15, 30} (as the old screen: the tfs the family
   supports) × its FAMILY-PARAMETER VARIANTS = the values of the FIRST axis of that family's heat-map in `R/tune1.jsonl` /
   `R/tune2.jsonl` (e.g. donchian n {10,20,40,60}, orb or_min {5,15,30}, vwap_z zth {1.5,2,2.5,3}, squeeze sq_type, ib mode,
   gap mode, sweep_rev levels, lon_break min_rng_atr, tod_drift off_min × dir, first_bar_mom k, rsi2 th, tema_slope n,
   vwap_band band, vwap_flip hold, pinbar wick; families whose first axis is max_tr or that have no grid: defaults only).
   New families: bimb_follow z {1.5, 2.0, 2.5}; flow_exhaust percentile {85, 90, 95}; vwap_ema_x and straddle_t as listed.
   The plateau is judged over ALL (parameter × exit) cells of a unit (family × tf × session × root).
5. No evening sessions → session `eve` (18:00–23:59 ET, belongs to the next trade date; indicators restart at 18:00) and `pre`
   (08:25–09:30) exist for every family, besides asia / london / nyam / mid / pm; asia stays 00:00–03:00.
6. Kind fills → the 2 ticks + 250 ms stress is a hard admission test; report base and stressed side by side.
7. Best-cell picking → plateau judging only; members are the central / simplest cell.
Order of work under the 40,000-cell cap: NQ first (all families), then ES, then GC; L2 filter / exit variants only on base
units that pass the BUILD plateau. If the cap binds, cut GC then ES for families that failed the NQ plateau, and log it.
Deliverables after admission (later stages): per account type the best single member and the best stack (Lucid Flex / Pro /
Pro-noDLL eval + funded, Apex 50K eval + PA, Apex 300K eval + PA), speed-vs-odds table, EXAM once, dashboard + PDF.

## Families and their rationale (written before any run)
A. `straddle_t` — OCO stop entries around the price at a clock time; one trade per time per day.
   Times ET (user list + existing): 18:00, 20:00, 00:00, 02:00, 03:00, 08:30, 09:30, 11:05, 13:30.
   Rationale: at scheduled liquidity events new orders arrive and price leaves its pre-event balance; a straddle rides
   whichever side breaks. Events: 18:00 Globex reopen · 20:00 Tokyo cash open (19:00 in winter) · 02:00/03:00 Europe
   futures/cash open · 08:30 US data · 09:30 US cash open · 13:30 afternoon repositioning. 00:00 has NO event behind it
   (tested at the user's request; label WEAK RATIONALE — it needs stronger evidence to be admitted).
   Cancel unfilled after 60 min; flat at the next listed time or the session end, whichever is first.
B. `vwap_ema_x` (user request) — EMA(n) of closes crosses the session VWAP at a tf-bar close → enter with the cross.
   Variants: n ∈ {9, 21, 50} × tf ∈ {1, 5, 15} × anchor ∈ {session, RTH 09:30}. Rationale: when the fast average crosses
   the day's fair price, control of the day has changed sides and the wrong side must exit. WEAK PRIOR: the old pilot's
   close-crosses-VWAP family (vwap_flip) did not survive — state that next to any result.
C. The old pilot's 21 families (R/families/*.py), re-searched with the tight-stop menu on NQ, ES, GC. Rationale per family
   as in R/SPEC.md (opening range = first balance of the session; donchian = trend continuation; vwap fades = mean reversion
   to fair price; sweep_rev = stop-run exhaustion at prior-day / overnight extremes; lon_break = NY resolves the London
   range; …). Families whose in-sample favourites FAILED on 2025-26 (donchian pm, first_bar_mom nyam) start with a penalty:
   they need the plateau on BUILD and PICK and a reason why the failure was noise.
D. Level 2 (NQ only; deployable tier of L/FEATURES.md):
   D1 `bimb_follow` tf5 (survived the L2 screen vs shuffled book) — rationale: resting size leaning one way is inventory that
      must be worked through; price drifts toward the heavy side over minutes.
   D2 book FILTER on any member: skip a trade when the 5-min mean imb10 opposes its side (rationale: do not trade into the
      heavier book). D3 book EXIT: leave when the 5-min mean imb10 flips against the open trade for 2 consecutive minutes
      (rationale: the inventory that supported the trade is gone).
   D4 `thin_ahead_break`: breakout families (orb / donchian / straddle) only when depth on the break side is thin
      (a10_rel15 or b10_rel15 ≤ 0.8) — rationale: little resting size ahead = less resistance to the move.
   D5 `flow_exhaust`: tf-bar makes a new session high (low) on top-decile |delta| in the move's direction but closes in the
      lower (upper) half of its range → fade — rationale: aggressive buyers were absorbed at the extreme.
E. Controls for every run: C1 random-entry control with the same exit profile, day- and session-matched (2 seeds);
   for L2-dependent members also C2 feature-shuffle (2 seeds). BEST-OF-NULLS bar per batch: the 95th percentile of the best
   null cell over the batch's nulls.

## Library admission (on BUILD + PICK only)
net > 0 after costs in BOTH periods (plateau cell) · beats C1 (and C2 if L2) in both · above the batch's best-of-nulls bar on
BUILD · still > 0 with 2 ticks + 250 ms · ≥ 100 trades · open-loss per trade sizeable inside $2,000 (≥ 1 micro) · rationale
present, WEAK-rationale members need all of the above with margin (t ≥ 3 on BUILD). Each member → `W/members/<name>/`:
spec.json, trades (1 contract), daily.csv (date, net, worst_open_loss, minutes_in_market), card.md (rationale, plateau table,
period table, nulls, stress, complexity count).

## Stacks (after admission; separate stage)
≤ 4 members per account, equal-risk sizing, chosen on PICK by lowest loss-day overlap; scored under intraday for: Lucid Flex /
Pro / Pro-noDLL eval + funded, Apex 50K eval + PA, Apex 300K eval + PA (one direction, by hand, no straddles). Report
P(pass) at 5 / 10 / 20 / 40 days + bust; funded E[$ to trader 40 d] + bust. The user's bar P(pass ≤ 5 d) ≥ 60 % is never
relaxed: if a stack misses it, say so and show the speed-vs-odds table.

## ORCHESTRATOR DECISIONS 2026-10-03 (taken P&L-blind: no BUILD result was opened; they bind every later stage)
Earlier stage reports are in `out/reports/` (infra_engine.md, family_*.md, verify_*.md, fix_*.md).
1. EXIT CONVENTION (user feedback 2026-10-02, vault `feedback-metrics-per-year-then-combined`): "flat by 4pm" — a trade runs to its
   stop / target or is flattened at 15:58 ET of its TRADE DATE (13:13 on half days); NO flatten at the session end. Entries stay
   limited to their session window (and never in its last 5 minutes); one position at a time per unit; straddle_t: unfilled orders
   still cancel after 60 min, the filled side holds to 15:58. This REPLACES "flat at session end / next listed time" for every
   family. The 77 BUILD + 13 null runs made before this decision used the old convention: they are VOID (move to runs_void/, reset
   the ledger; they were never analysed). Tester-match gates keep validating the engine with the old convention switched on.
2. Plateau units: opposite modes are separate units — tod_drift long vs short, ib break vs fade, gap fill vs go (and any other
   MIRROR axis). Cells with identical trade lists count once; cells that cannot trade by construction are excluded.
3. Central cell = the positive cell whose net is closest to the unit's median (ties: lowest variant / exit index).
4. WEAK (admission needs t ≥ 3 on BUILD): straddle_t 00:00 and 11:05, tod_drift, vwap_ema_x, and the families whose rationale only
   restates the trigger (ema_ribbon, tema_slope, ema_pullback, supertrend). Second-look families carry the label on their card;
   the failure PENALTY applies to first_bar_mom and donchian in the pm session.
5. 20:00 ET stays 20:00 all year (user's time; Tokyo is 19:00 ET in winter — stated on the card).
6. Caps: null / control cells do NOT count toward the 40,000 candidate-cell cap (they are tracked separately in the ledger).
7. REPORTING (user): every unit and member shows the full metric set PER YEAR first (2021*, 2022, 2023; then 2024 for PICK), then
   combined; the plateau table gives the share of cells with net > 0 overall, by stop type (fixed / ATR / percent) and per reward
   ratio, and the pass verdict at 60 %, 70 % and 80 %; trades are also shown sized to about $1,000 risk in micros, with Sharpe.
8. EXAM (2025+) stays sealed until the user says to run it.

## USER ACCEPTANCE BAR 2026-10-03 (replaces "P(pass <= 5 d) >= 60 %")
Plateau bar 60 % of variants positive (more is better; show 60 / 70 / 80). Slow is acceptable. EXAM runs only when a member or
stack passes everything: > 60 % variants positive AND eval P(pass <= 10 trading days) >= 60 % (intraday rule) or funded = high
probability of the MAXIMUM payout within 20 trading days. Low trade frequency is fine. DEEPEN round (after admission): near-miss
ideas get a small fixed set of add-ons (RSI-direction agreement, daily ADX trend, flow-and-book "agree" days), every attempt
counted and nulled. Candidate from the user's own work: NQ 09:30 "agree days + RSI direction" (2026-10-02-bimb930).
* 2026-10-03 (user): funded bar = P(maximum payout within 20 trading days) >= 75 %. 2021 (Sep-Dec) stays IN every sample.
  The user's NQ 09:30 "agree days + RSI direction" idea enters the stack stage as a candidate, taken as it stands in
  `research/prop-portfolio/2026-10-02-bimb930` at that time (2021 included), 2025+ untouched until the exam.

## DEEPEN ROUND — user method 2026-10-03 (vault `explore-before-dropping`), runs after stage-1 admission
No idea is called a flop after one look. Every unit that fails the plateau but has a written rationale gets an exploration
budget of up to 4 counted rounds on BUILD, each round a heat map (same 32-cell exit menu; $1,000-risk micro sizing is the
primary view), from this fixed toolbox, one change per round: (1) trade-time book filter (skip when the 5-min book opposes the
side) / book exit; (2) flow-and-book AGREE marker at the trade's moment (signs of the last 15 min delta and of the book
imbalance agree → take the trade; per day only for once-a-day strategies); (3) RSI-direction agreement (5-min RSI14 > 50 long /
< 50 short); (4) daily ADX(14) > 20 and rising; (5) direction restricted to long or short; (6) the inverse of the signal.
A round passes at > 60 % of variants positive; passers go to PICK, nulls (same-day controls, random day subsets, shuffled book)
and the attempt count is printed on the card. Budget spent → "shelved" with notes. Live-data rule: book inputs only from the top
10 levels unless the desk is shown to receive more.

## ADMISSION AMENDMENT 2026-10-03 (user's method — binding for the Admit stage; replaces "run the central cell on PICK")
After a unit's heat map passes on BUILD (> 60 % of variants positive, beats its nulls):
1. Run the WHOLE menu of that unit on PICK (2024), not one cell.
2. The PICK heat map must pass again as a table (> 60 % of variants positive). A unit whose table fails on PICK is not admitted
   (near-miss → DEEPEN round); its few surviving cells are NOT kept (that would keep luck).
3. Save EVERY variant that is positive in BOTH periods and still positive under the 2 ticks + 250 ms stress = the member's
   SURVIVING SET (card: per-variant per-year tables, $1,000-risk view; the central cell is marked as the default variant).
4. Stack stage: one variant per strategy per account (the one whose stop / reward ratio fits that account's rules); two variants
   of the same strategy are the same trades and never count as two members of a stack.
5. EXAM (2025+) is run once on the frozen stacks, only when the user's acceptance bar is met.

## AUTOPILOT MANDATE (user 2026-10-03 evening) — the orchestrator continues without asking until the goal or the stop rule
Goal: per account type a stack that meets the acceptance bar (> 60 % of variants positive; eval P(pass <= 10 trading days) >= 60 %;
funded P(max payout <= 20 trading days) >= 75 %; intraday rule). Authorised: lean multi-agent workflows (sonnet for mechanical
stages, one checker, <= 25-line reports, everything on disk); the 2025+ EXAM, ONCE, automatically, for a strategy variant / stack
that passes every requirement on 2021-2024. NOT authorised without the user: anything on the live desk or a real account, any
desk restart, changing the bar.
Stage order: 1 finish BUILD menus → admission (amended method) → 2 DEEPEN round + SECOND-CHANCE list → 3 Apex 300K one-direction
build → 4 stacks per account → (bar met → EXAM once → report) or (not met → 5 new-idea round, at most TWO rounds) → 6 final report.
Stop rule: both lists done + two new-idea rounds and still no stack at the bar → stop, report the best available with honest odds.

## "DONE" DEFINITION for an idea (user: a fail only counts if the idea was tested thoroughly) — every idea's record must show
[ ] rationale written first · [ ] 4 fixed stops + 2 ATR (volatility) stops + 2 percent stops · [ ] targets none / 1:1 / 1:2 / 1:3
[ ] every session it can trade (eve, asia, london, pre, nyam, mid, pm) or every listed clock time · [ ] bar sizes 1 / 5 / 15 / 30
[ ] its main parameter at 3-4 values · [ ] NQ, and ES + GC when no Level 2 input · [ ] flat by 15:58 · [ ] $1,000-risk view
[ ] nulls (same-exit random / time-shuffle / shuffled book / same-day controls) · [ ] per-year tables
[ ] DEEPEN rounds from the toolbox (max 4, counted): book filter at the trade, book exit, flow+book AGREE marker, RSI direction,
    daily ADX trend, long-only / short-only, inverse, VOLATILITY regime (prior-day range above / below its 20-day median),
    NEWS days (CPI / NFP / FOMC: only / never)
[ ] verdict: ADMITTED (surviving set saved) or SHELVED (what was tried, why it failed) — never silently dropped.
Everything is saved for the user to read: `IDEAS.md` (one line per idea: status, rounds used, link to its folder) and
`ideas/<name>/` (heat maps as CSV + HTML, per-year tables, nulls, notes), `members/<name>/` cards, `stacks/<account>/`.

## STAGE 2a — DEEPEN ROUND 1 ON STORED TRADES (orchestrator, 2026-10-04 05:20 ET, written before any deepen number exists)
Why: stage 1 left 1 member and 208 heat-map passers that fail a control. The user's method: an idea gets counted deepen rounds
before it is shelved. Weekly token budget is at 70 %, so this round re-uses the trades already stored in `runs/` (no new strategy code).
UNITS: the near-misses in `out/admit/near_misses.csv` whose `fail` is exactly `bar` (beat their matched control, miss only the
best-of-random bar) and that are not WEAK and carry no penalty. Units whose 2024 was already read are information only.
orb_NQ_tf1_pre (the member) gets the same splits as INFORMATION ONLY (where does its edge sit).
TOOLS — the same four for every unit, each a split of the unit's own stored BUILD trades (8 sides in all):
  T1 trend: prior-day daily ADX(14) >= 25 / < 25 (daily bars through the PRIOR day only)
  T2 volatility: prior-day range above / below its own 20-day median (through the prior day only)
  T3 news: days with an 08:30 ET CPI or NFP release or an FOMC decision — only / never (calendar already in the engine; if a
     release type has no reliable dates, leave it out and say so)
  T4 direction: long-only / short-only
A SIDE passes BUILD only if ALL hold (nothing is relaxed; the last test pays for trying 8 sides):
  (a) the admission minimum trade count (library.admission, unchanged);
  (b) heat map: >= 60 % of variants positive and median > 0 (library.plateau rules: identical trade lists once, dead cells out);
  (c) the central variant beats its matched random-entry control restricted the same way (lift > 0);
  (d) the central variant's t >= the family's best-of-random bar already on disk (`out/admit/null_bars.json`);
  (e) T1-T3: the central variant's net beats 99.4 % (= 1 - 0.05/8) of 4,000 random same-size subsets of the unit's own trading
      days; T4: its lift beats 99.4 % of same-side random-entry draws.
PICK: 2024 is opened ONLY for sides that pass (a)-(e): the unit's whole menu on 2024 with the same split; the 2024 table must
pass (b) again; the surviving set (positive in both periods and under 2 ticks + 250 ms) is saved; every read logged.
A filtered side is at most ONE member per strategy (ADMISSION AMENDMENT 4). EXAM stays sealed.
RECORDS (the user reads these): `IDEAS.md` = one line per idea tested so far in the library (family x market; status ADMITTED /
OPEN / SHELVED; rounds used; link) and `ideas/<family>_<root>/notes.md` + CSV tables (heat-map shares at 60/70/80 %, per-year
tables, the 8 sides, nulls). An idea is SHELVED only when its DONE checklist is complete; otherwise OPEN with what is left.
Report how many sides were tested and how many would pass by luck.

## STAGE 2b — NEW-IDEA ROUND 1 (orchestrator, 2026-10-04 05:40 ET; rationales written before any code or result)
Sources: the user's videos (`videos/*.md`, vault `video-batch-2026-10-03-takeaways`) + the SECOND-CHANCE list + the Apex 300K
one-direction need. Same pre-registered exit menu (32 cells), same sessions / bar sizes / markets as every family, hold_to = day
(flat 15:58), 1 contract, BUILD only until a unit passes. Same admission tests as stage 1 (heat map >= 60 % and median > 0;
matched random-entry control; best-of-random bar; then the WHOLE menu on 2024 must pass again; surviving set under 2 ticks +
250 ms; the BUILD central variant must itself be positive in 2024 and under stress — no moved default; minimum trades).
CANDIDATE CAP raised 40,000 -> 50,000 cells (the user approved raising the cap; luck is controlled by the nulls, not the cap).
Families (name — plain reason — rules — main parameter):
  N1 vwap_trend_pull — when price holds above a rising session VWAP, the day's buyers are in profit and dips get bought; the first
     candle against the trend gives a better price in the direction of the day's flow. VWAP anchored 09:30 ET. LONG state: bar
     close > VWAP, VWAP now > VWAP 3 bars ago, price up >= X over the last 60 min; trigger = first bar that closes against the
     trend while the state holds -> enter next bar open. SHORT = mirror. No entry before 10:30 or after 15:30; max 4 trades a
     day; stop for the day after 2 losing trades. X = {0.05 %, 0.10 %, 0.20 %}. Author cell (information only, not in the heat
     map): stop 80 pts, target 40 long / 50 short, NQ 15-min.
  N2 va_reclaim — a poke outside yesterday's value area that fails traps the late side; they exit and price returns into value.
     Value area = 70 % of yesterday's RTH volume by price (VAL / VAH). LONG: price trades below VAL by >= D, then a bar closes
     back above VAL -> enter next open. SHORT = mirror at VAH. One trade per side per day. D = {0, 0.25, 0.5} x ATR(14) of the bar.
  N3 orb_confirm (one direction) — the opening range is the first balance; a bar CLOSE outside it shows acceptance, and one
     direction per day never holds opposite positions (Apex rule). Range = first or_min minutes from 09:30; enter next open after
     a bar closes beyond the range; LONG-ONLY and SHORT-ONLY are separate mirror units; one trade a day. or_min = {15, 30, 60}.
     Author cell (information only): stop at the other side of the range, exit 15:30.
  N4 late_mom — the day's early move predicts the last half hour (hedgers and late traders push the same way into the close;
     documented in the academic literature). At 15:30 ET enter in the direction of sign(P_signal - prior close), exit 15:58.
     Signal time = {10:00, 12:00, 15:30}; trade only if |move| >= {0, 0.25 %, 0.5 %}. One trade a day.
  N5 open_fade — the first burst after the open often overshoots while opening orders clear; when it stalls, price reverts toward
     the pre-open price. Ref = 09:29 close. After 09:30, once price is >= K x ATR(14, 1-min x 30) away from ref and a bar closes
     back toward ref beyond the prior bar's opposite extreme -> enter toward ref. Window 09:30-11:00, max 3 trades. K = {0.5, 1, 1.5}.
     Author cell (information only): target = the ref price.
  N6 vol_spike_break — a break of the recent range on unusually high volume has real participation behind it; breaks on normal
     volume are more often noise. Bar volume >= M x median volume of the last 20 bars AND close beyond the 20-bar high / low ->
     enter next open in that direction; max 2 a day. M = {2, 3, 4}.
  N7 straddle_tight (second chance of the old NQ 09:30 straddle) — the first seconds after a scheduled time are one-way; a tight
     bracket catches the burst with a small stop. Clock times 08:30, 09:30, 10:00 ET; stop entries OFFSET points each side,
     armed 1 s before, OCO; offset = {3, 5, 8} pts NQ (ES 0.75 / 1.25 / 2; GC 0.6 / 1 / 1.6); stop = {5, 8, 10} pts NQ (scaled the
     same way); target 1:1 / 1:2 / 1:3; unfilled legs cancel after 5 min. Its null = the same bracket at random minutes.
Not in this round (stay OPEN in IDEAS.md): flow+book AGREE marker at other clock times (needs the wide ladder the live feed does
not show); the delta-flip version of N2 (only if N2 shows life); TIME EXIT as a deepen tool (the `exit_bars` input exists).
"Quiet day" (prior-day range below its 20-day median) is a LEAD from stage 2a, not a rule: report each new unit's quiet / active
split as information only.
At the end: score the library's member(s) alone on each account type (Lucid Flex / Pro / Pro noDLL eval and funded, Apex 50K,
Apex 300K PA) at $1,000 risk with the intraday (open-loss) rule: P(pass <= 10 trading days), P(max payout <= 20 trading days).

## STAGE 3 — NEW-IDEA ROUND 2: EVENT STRADDLES (orchestrator, 2026-10-04 09:10 ET; written before any event-split number exists)
Reason (plain): a scheduled US data release reprices the market in one burst in the first seconds; a bracket placed just before
catches it whichever way. It is the only edge that beat random controls in ~43,000 cells (NQ 08:30) and the one that passed a
live eval on gold (desk journal 2026-10-02: NFP, buy stop filled AT its stop price, fill_vs_anchor 0.0). Stage 2a only looked at
CPI / NFP / FOMC days; this round uses the full calendar and all three markets.
CALENDAR (built from official release schedules, with the source per date; a type that cannot be sourced reliably for
2021-09..2024-12 is dropped; dates are NEVER checked against the tape): 08:30 ET — NFP, CPI, PPI, Retail Sales, GDP, PCE,
weekly Jobless Claims; 10:00 ET — ISM Manufacturing, ISM Services, JOLTS, Michigan sentiment (prelim); 14:00 ET — FOMC decision.
UNITS = day filters on the stored BUILD trades of families already run on every day (no new strategy code):
  E1 `straddle_tight_0830` x {A: every 08:30 release day incl. claims, B: tier-1 only = NFP, CPI, PPI, Retail Sales, GDP, PCE}
  E2 `straddle_t_0830` x {A, B}
  E3 `straddle_tight_1000` x {C: every 10:00 release day}
  x NQ, ES, GC = 15 units. Per-type tables (NFP alone, CPI alone, ...) and FOMC 14:00 are INFORMATION ONLY (too few trades).
A unit passes BUILD only if ALL hold: (a) trade minimum per library.admission (BUILD + 2024 >= 100 for the central variant;
on BUILD alone it must still be reachable); (b) heat map >= 60 % positive and median > 0; (c) central variant beats the SAME
bracket on NON-event days at the same clock time (per-trade mean, lift > 0); (d) central t >= the UNCHANGED stage-1 bar for
that market's random-minute straddles (NQ 2.56, GC 1.63, ES from out/admit/null_bars.json) ; (e) central net beats 99.67 %
(= 1 - 0.05/15) of 4,000 random same-size subsets of the family's own trading days.
PICK: whole menu on 2024 with the same day filter; table must pass (b); BUILD central variant positive in 2024 and under
2 ticks + 250 ms (no moved default). NOTE: 2024 was ALREADY READ for straddle_tight_0830 NQ and GC (all days) and for
straddle_t_0830 NQ (CPI / NFP / FOMC days): a member from those units is flagged SECOND LOOK on 2024.
FILL REALISM (reported on every card, not a new gate): entry filled at the first print >= 1 / 5 / 25 ms after the trigger print;
a member whose BUILD or 2024 net turns negative at 5 ms is flagged FILL-FRAGILE. Run the same probe on orb_NQ_tf1_pre.
LIVE FILLS (read-only): list every `entry_fill` of a REAL account in the desk journal with its `fill_vs_anchor` (slip vs the
stop price) — the only real evidence on burst fills. Never write to the desk.
ODDS (information): each member / the best E unit per market ALONE, Lucid Flex / Pro / Pro noDLL and Apex 50K eval and funded,
intraday rule: (i) eval started on a random day, P(pass <= 10 trading days); (ii) eval started the trading day before a
tier-1 release; funded P(max payout <= 20 trading days). Size: the largest micro count whose worst open loss stays inside the
account's drawdown, and the $1,000-risk size; both fill models (on the trigger print, and 5 ms later).

## STAGE 4 — EVENT ENTRY VARIANTS (user request 2026-10-04 ~10:00 ET: "orders farther away, or market order in the direction
## of the candle closure or lower timeframe candle closure or tick direction"; written before any number exists)
Why: the admitted event straddles need a fill at the stop price in the burst and can double-fill when the sibling cancel is
late. These entries trade the same release burst without a tight two-sided bracket. Same reason as STAGE 3 (a scheduled
release reprices the market in one burst); the question is only HOW to get in.
Run on EVERY day at the clock time (so non-release days are the control), judged on release days with the STAGE 3 calendar.
  W `straddle_wide` — the same OCO bracket, farther away. Offset each side: NQ {10, 15, 20, 30} pts, GC {2, 3, 4, 6}, ES {2.5, 4,
    5, 8}; stop {0.5, 1, 1.5} x offset; target 1:1 / 1:2 / 1:3; armed 1 s before; unfilled legs cancel after 5 min. 36 cells.
  D `event_dir` — NO bracket, ONE direction: at release time + X, if price has moved from the last print before the release,
    send a market order that way (no move = no trade). X = {0.25 s, 0.5 s, 1 s, 2 s, 5 s, 15 s, 60 s}. X <= 2 s is the user's
    "tick direction"; 5 s and 15 s are the "lower timeframe candle close"; 60 s is the 1-minute candle close. One trade per
    release. Exits: the standard 32-cell menu. 7 x 32 = 224 cells. One direction and no opposite orders, so it also fits Apex.
Clock times 08:30 (day groups A = every 08:30 release day, B = tier-1) and 10:00 (group C). Markets NQ, ES, GC.
Units: {W, D} x {A, B, C} x 3 markets = 18. For D the heat map is judged per X as well (information) — the unit is all X.
A unit passes BUILD only if ALL hold: (a)-(d) exactly as STAGE 3 (trade minimum; heat map >= 60 % and median > 0; central
variant beats the same entry on non-release days per trade; central t >= the unchanged stage-1 bar NQ 2.56 / ES 2.00 / GC 1.63);
(e) central net beats 99.72 % (= 1 - 0.05/18) of 4,000 random same-size subsets of its own trading days.
PICK as STAGE 3 (whole menu on 2024 with the day filter, control too; BUILD central variant positive in 2024 and under 2 ticks +
250 ms; no moved default). 2024 for these units is a FIRST look for 10:00 and for D; W at 08:30 on NQ / GC is close kin of units
already read, so flag SECOND LOOK.
Fill realism on every card (information): market orders fill at the first print after the order is live + 1 tick (base) and
2 ticks + 250 ms (stress); the 1 / 5 / 25 ms probe; for W the late-cancel (double-fill) probe from out/oco_probe/.

## USER DIRECTION 2026-10-04 ~10:30 ET (binding; vault `library-first-no-scalping`)
1. LIBRARY FIRST: do not gate on eval pass % / payout % for now. Save strategies that have a real edge (beat random entries),
   are profitable in both periods, are not overfit and have good metrics. Odds and simulators come later, on groups.
2. NO SCALPING: Lucid's micro-scalp limit is 5 seconds. 5-SECOND GATE (applies from STAGE 4 on, and as a flag on existing
   members): net of the central variant with the WINNERS held under 5 seconds removed (losses kept) must be > 0 on BUILD and on
   2024. Every card shows: net / net from trades under 5 s / net without fast winners.
   Existing members under this gate (computed 2026-10-04, BUILD + 2024, 1 contract): orb_NQ_tf1_pre $28,799 -> -$10,309;
   straddle_tight_0830_GC evA $16,094 -> -$7,774; straddle_tight_0830_NQ evB $11,430 -> -$13,138; straddle_tight_1000_GC evC
   $12,368 -> -$736. All four are SCALP-DEPENDENT: kept on file, not usable on Lucid.
3. The live book is Level 2 only (10 levels).

## USER DIRECTION — CORRECTION AND ADMISSION v2 (2026-10-04 ~11:15 ET; written before any v2 result exists)
A. 5-SECOND RULE (replaces the 5-SECOND GATE above). Lucid's exact rule: "More than 50% of your profits are generated from
   trades held for 5 seconds or less." It is an ACCOUNT-level share. Fast strategies are KEPT and saved. Every card shows the
   share of profit from trades held <= 5 s; a group / stack must keep its combined share <= 50 %. It is NOT an admission gate.
   (The STAGE 4 judge was briefed with the old gate: its "5-second" fails are re-judged under this section.)
B. ADMISSION v2 — "judge the average, not one variant" (user). Replaces "the BUILD central variant must itself be positive in
   2024 / no moved default" and the best-of-random bar on the central variant. For every unit (all stages, incl. the 20
   near-misses whose 2024 is unread and the units rejected only on their default variant):
   BUILD (2021-09-22..2023): (1) > 60 % of variants profitable and the AVERAGE variant profitable; (2) REAL EDGE at table
   level: the table's average net beats the average of the same table run with random entries (same stops / targets / session)
   and beats >= 95 % of the random replicates' table averages (time-fired ideas: the random-minute / random-direction / non-release
   replicates); (3) the trade minimum, on the average variant's trade count.
   2024, judged ON ITS OWN (not pooled with 2021-23, so a big 2022 cannot hide a losing 2024): (4) the AVERAGE of ALL variants is
   profitable and the median variant is profitable; (5) the average still beats the random-entry average (lift > 0); (6) the
   average stays profitable under 2 ticks + 250 ms (+ 100 ms late sibling cancel for two-sided brackets).
   SAVED: every variant profitable in both periods under stress (surviving set). Default = the MIDDLE survivor by 2021-23 net
   (fixed rule, never the best). Cards report the AVERAGE variant per year then combined, next to the default.
   2025+ stays sealed: one exam on the group, later. WEAK-reason families and the 2025-26 penalty families keep their flags.
   The user may still choose the pooled alternative ("add 2024 and check the average of all years") — only before a v2 result exists.
C. STRESS for two-sided brackets now includes a 100 ms late cancel of the other side (Costs.oco_cancel_ms = 100).
D. CANDIDATE CAP 50,000 -> 80,000 for DEEPEN ROUND 2 (below); luck is controlled by the table-level random test, not the cap.

## DEEPEN ROUND 2 — the user's toolbox on the near-miss ideas (user 2026-10-04; runs after STAGE 4; written before any result)
Ideas: A ib break (NQ, ES, GC), B/C donchian morning, D vwap_trend_pull, E vol_spike_break and orb_confirm, plus orb.
New exits (added to the standard 32 cells, for every idea): ATR x 1 and x 2 stops; targets 1:1.5 and 1:4. For RANGE ideas
(ib, orb, orb_confirm, donchian) also RANGE stops: 25 %, 50 %, 100 % of the range / channel height.
New range lengths for A: the 09:30 range of 5, 15, 30, 60 minutes, entries allowed in nyam / mid / pm (today only 60 was run).
Regime filters, each judged AGAINST THE SAME TABLE WITHOUT THE FILTER (a filter is kept only if the filtered table's average per
trade beats the unfiltered one on BUILD and again on 2024, and beats 95 % of random same-size day or trade subsets):
  momentum (RSI(14) on the bar size at the signal, in the trade direction above 50 / against), volatility (prior-day range above /
  below its 20-day median — already run, kept for the new cells), volume (the day's volume up to the signal vs the 20-day median
  for the same clock time: above / below), Level 2 on NQ (top-10 book imbalance agrees with the trade at the signal: yes / no).
Bar sizes 5 and 15 (1 and 30 where already run). Judged by ADMISSION v2.

## WORKBENCH PLAN (user-approved 2026-10-04 ~12:30 ET; vault `research-workbench-plan`)
1 ONE FIXED JUDGE: ADMISSION v2 as one tested command (unit in -> verdict + card out); built from the v2 re-judge scripts; after
  it is verified once, later rounds use it and get spot checks only.
2 IDEAS AS SETTINGS: tested blocks (entry / filters / stop / target / time window); a new idea = a few lines of settings.
3 SLOW WORK ONCE: store entries, apply the exit table to them; reuse bars, ranges, day labels, random controls; 12 workers off-hours.
4 INSIDE HOMEBASE (after the weekly token reset): a "test an idea" tester job (whole table, random control, sealed years), results on
  the heat-map page, callable through the MCP connector; EVERY idea and block saved as a preset in the Backtest tab (Lab drafts).
The guards stay (random-entry test, unseen year, look-ahead tests): automated, not removed.
- Screens for step 4: option A (user 2026-10-04) — engine, data and connector here; screens by the redesign chat.

## PERIODS AMENDED — user decision 2026-10-04 ~13:30 ET ("A"): open 2025, keep 2026 sealed (written before any 2025 number exists)
Why: about 50,000 cells have been run on 2021-2024 and 2024 has been opened for most near-misses; the v2 placebo says the non-event
members are not shown to be more than luck. The only clean data left is 2025+.
NEW PERIODS: BUILD 2021-09-22..2023-12-31 · PICK 2024 · CHECK 2025-01-01..2025-12-31 (opened now) · EXAM 2026-01-01..latest (SEALED:
never read, the engine must refuse it; the final exam for groups, once).
FIRST USE OF 2025 — the v2 members that the independent checker confirms (one read each, whole menu + its control, logged in
out/check2025/reads.csv). Judged ON ITS OWN with the same three tests as 2024: (4) the AVERAGE of all variants profitable and the
median variant profitable; (5) the average beats the random-entry average (lift > 0); (6) the average stays profitable under
2 ticks + 250 ms (+ 100 ms late sibling cancel for two-sided brackets). Verdicts: CONFIRMED (passes all three) / WEAK (average
profitable but fails (5) or (6)) / FAILED (average not profitable). Nothing is re-tuned after the read; the default variant and
the surviving set stay as saved (report the default's 2025 result and how many saved variants are profitable in 2025).
Families whose old finalist was already seen on 2025-26 in an earlier pilot keep the SECOND LOOK flag.
FROM NOW ON 2025 is the check year for new ideas: BUILD -> PICK (2024) -> CHECK (2025), each judged on its own by ADMISSION v2.

## ADMISSION v2 — CHECKER FIXES (orchestrator, 2026-10-05 ~09:50 ET; written before any 2025 number exists; all make the rule
## steadier or stricter, none looser)
The independent check (out/check_v2/) reproduced every number and confirmed the 14 members under the rule as coded, with these fixes:
F1 Test (2) uses 4,000 random draws for every unit (200 was a coin flip within ~2 points of the 95 % line). Units that pass at
   4,000 and were kept closed get their year opened; units opened on a lucky 200-draw seed all failed 2024 anyway.
F2 THIN CONTROLS: every control had 2 random seeds. From now on the random-entry pools and the random-minute / random-direction
   stores have 10 seeds for any unit that is a member or a BUILD passer, on every period that is judged; the judge uses every seed
   on disk. A member that no longer beats 95 % of random tables on BUILD with the 10-seed control is DEMOTED to "luck not excluded"
   (kept on file, not counted as edge). Cards show both percentiles (2-seed and 10-seed).
F3 "More than 60 %" is strict (> 60 %).
F4 The "<= 5 s" share is reported two ways: fast winners / all winners (gross) and net profit of trades held <= 5 s / total net
   profit (Lucid's wording is about profits); the FAST flag uses the net version.
F5 On a later year the judged variant list is the BUILD list (no second de-duplication on that year's trades).
F6 pick / check read logs list every store used, new or re-used.
F7 The 464 stage-2a side tables are NOT re-judged: filters are re-tested as blocks in round 3 under the filter rule.
PENDING UNDER F1 (2024 already on disk or to be opened): donchian NQ 30-min morning (v1 member; passes (4),(5) on disk; finish the
whole-menu stress) -> likely a 15th member; vol_spike_break NQ 5-min afternoon, donchian NQ 5-min afternoon, vwap_z NQ 30-min
midday -> re-judge BUILD with the 10-seed control first, open 2024 only if they still pass.
2025 (CHECK) is run for the 14 members + donchian NQ 30-min morning if admitted, as pre-registered; the F2 result is reported next to it.

## FULL OUT-OF-SAMPLE FOR THE SAVED STRATEGIES — user decision 2026-10-05 ~10:00 ET (written before any 2025 or 2026 number exists)
User: "Run 2026 for just these if they meet the requirement, fully finish the OOS so we know which are fully overfit or fully real."
1. 2025 first, as pre-registered (PERIODS AMENDED): each saved strategy (the 14 v2 members + donchian NQ 30-min morning if admitted
   under fix F1), whole menu + 10-seed control + stress, judged on its own by tests (4)-(6).
2. 2026 ONLY for the strategies that pass all three tests on 2025 (CONFIRMED). Period = 2026-01-01 to the last complete session
   on disk (state the date). Whole menu + 10-seed control + stress, with the explicit exam flag, ONE read per strategy, logged in
   out/exam2026/reads.csv. Judged on its own by the same tests (4)-(6). Nothing is re-tuned between or after the reads.
3. Verdict per strategy, in these words:
   REAL        = passes 2025 AND 2026.
   OVERFIT     = the average variant is not profitable on 2025 (2026 not run).
   NOT PROVEN  = everything in between: profitable on 2025 but fails the random or slippage test (2026 not run), or passes 2025
                 and fails 2026 (say which test).
   Also reported for each: the 10-seed BUILD percentile (fix F2), profit per year 2021-2026 for the average and the default
   variant, how many saved variants are profitable in each unseen year, trades, drawdown, share of profit from trades <= 5 s.
4. 2026 stays SEALED for everything else: no other unit, no new idea, and no result from these reads may be used to design or
   tune anything. After the report the orchestrator STOPS until the user says (directive of 09:55 ET).

## RULING BEFORE THE 2025 SCORING (orchestrator, 2026-10-05 ~11:30 ET; no 2025 number has been printed or opened)
The judge tool (judge.py, regression-locked to out/v2) with the 10-seed controls on BUILD and 2024 gives:
- donchian NQ 30-min morning passes all six tests -> 15th saved strategy (fix F1).
- straddle_t_0830 NQ (wide 08:30 bracket) and straddle_t_1800 NQ (18:00 bracket) FAIL test (5) on 2024 against the 10-seed control
  (lift -$1,675 and -$360; they passed only with the first 2 seeds) -> DEMOTED, "luck not excluded" (cards kept on file).
For the full out-of-sample: all 15 units are scored on 2025 (as pre-registered); the two DEMOTED units do not meet the requirement,
so their 2025 result is reported as information and they do NOT go to 2026. 2026 is run only for units that are members under the
rule in force (13) AND pass tests (4)-(6) on 2025.

## ADMISSION v3 = THE BLUEPRINT — owner decision 2026-10-05 night ("lets lock this into the app … i want all strategies or
## strategy buildings to go off this"). Binding for every stage from here on.
The contract is `BLUEPRINT.md`, section 2 (written requirements for each phase). Where this file and BLUEPRINT.md differ, BLUEPRINT.md wins.
REPLACED: the periods (BUILD to 2023 · PICK 2024 · CHECK 2025 · EXAM 2026) -> BUILD 2021-09-22..2025-06-30 · ONE out-of-sample TEST
2025-07-01..latest complete session, read once for a locked strategy. ADMISSION v2 tests (1)-(6) -> BLUEPRINT lines 2.1-2.9 and
4.1-4.7 (cost floor NQ $70 / ES $75 / GC $140 after costs · 200 trades · long and short each profitable · neighbors · a filter wins
alone · Monte Carlo 75 % on build and 90 % on test · beats random tables 95 % rising to 99 % by round 5). The DEEPEN budget of 4
rounds -> 5 rounds, each with its reason written first. "EXAM once on frozen stacks" -> phase 4 per locked strategy, then phases 5-6.
UNCHANGED: house rules and compute windows · the intraday (open-loss) breach model · flat by 15:58 · 1-contract runs · the exit menu ·
costs and the stress definition (2 ticks + 250 ms, + 100 ms late cancel for brackets) · random controls with 10 seeds · the average
rule and the middle-survivor default · the stack rules · the 5-second share shown on every card · every attempt counted in the ledger.
BUILT 2026-10-06: the toolkit bp.py (blocks, card, code-check, build, lock, test, sim, eval-card, status) scores BLUEPRINT section 2
line by line; every threshold is in blueprint/templates/rules.json. Engine switches: bp_build (2021-09-22..2025-06-30) and bp_test
(2025-07-01..latest, opened only by runner.run_test after the read is claimed in the app's read log). Stores: runs_bp/ (build, and
the 12 control pools with 10 seeds), runs_bp_test/ (test). AMENDS "write only under W": idea records are saved in the app,
~/.homebase/ideas/<name>/ (the owner: "saves everything in the app"). judge.py still implements v2 for the old stores: a v2 verdict is
NOT a blueprint verdict. The 15 saved strategies have used their history under the old periods: they stay NOT PROVEN.
Evidence behind the lines: out/blueprint/ (gate_backtest.md, protocol_gates.md, mc_gates.md, funnel.md, course_review.md).
BLUEPRINT VERSION 1.1 (owner, 2026-10-06, after the law was held against the course line by line): + 0.7 (when it should lose) ·
3.3-3.7 (the default variant on its own before the freeze: profit factor 1.2, net / worst drawdown 3, Sharpe 1, drawdown at 1 micro
under $2,000, money in 90 % of reshuffled runs) · 4.8 (test average trade at least half of the build's) · 4.9 (default's profit
factor 1.2 on the test) · 5.5-5.7 (one strategy: 50 % / 50 %; the 60 % / 75 % bar of 5.3 is the PORTFOLIO's) · 6.9 (the hard alarm:
off until the recovery; 6.5-6.6 = the soft alarm). THE BLUEPRINT'S EXIT MENU = the 32 cells above, then the 8 stops x targets 0.5 and
0.75 x the stop: 48 cells (families/blocks.menu_blueprint; the old library's menu() stays 32). Built 2026-10-06: BLUEPRINT.md section 11.
