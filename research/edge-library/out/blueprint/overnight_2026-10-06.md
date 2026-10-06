# Overnight report — 2026-10-06

Everything below is merged to `main`, tested and pushed. App test suite: 2,943 passed. Toolkit tests: 143 passed. Engine: 1,520 passed.
Nothing was restarted. The desk stayed armed with the same accounts, no positions and no working orders.

## 1. Needs you first
| # | What | Why |
|---|---|---|
| 1 | **Your live market data is exactly 10 minutes late** on login 1552885, since Friday 10-02 08:11 ET. It is also thinned (one print for a burst of fills). | I checked it at 00:29 ET: the newest tick was 601 seconds old. Ten minutes is the exchange's delayed feed, so the real-time data on that login has lapsed or is blocked by too many sessions. Everything on the desk that reads this feed sees old prices, including the 09:30 paper strategy. Only you can restore it with the broker. |
| 2 | **One chart-service restart, today between 5:10 and 5:55 pm ET.** | A restart inside the daily market break loses no ticks. It switches on: groups in the Lab, the new default dates in the tester page, candles drawn on the feed's own clock, blank bands where data is missing, and the "late / thin feed" note on the chart strip. I did not restart: `gc_nfp` is booked to an account that is not a paper account (it is not connected right now). |
| 3 | **Keep the Mac on power and on a steady network.** | It ran on battery Monday 14:31-23:58 and dropped off the network eight times since Wednesday. Each drop is a gap. |

## 2. What was done
| Asked | Done | Live now | Live after the restart |
|---|---|---|---|
| Lock the blueprint; every chat follows it | Law in `BLUEPRINT.md`; skill `strategy-blueprint`; `CLAUDE.md`; memory | Yes. Checked twice with a fresh chat: it refused "run on everything", used the build days and went through the phases | – |
| Tester dates | Build (22 Sep 2021 - 30 Jun 2025) is the default; Test (1 Jul 2025 on) is its own range | Page labels; the connector | The tester itself |
| One saved toolkit, no code rewritten per chat | `bp.py`: blocks, card, code check, build, lock, test, sim, eval card, status. Rules, exit table, random control, Monte Carlo, costs and sizes saved as templates | Yes | – |
| Chats use the app and save in the app | Nine `blueprint_*` connector tools. Each idea is saved in `~/.homebase/ideas/<name>/`, as a draft in the Lab with its card and verdict on top, as a tester run, and in a Lab group for its status | Yes, in any new chat | The Lab page showing the groups |
| Random entries; worse fills; the one test read | In the toolkit. 12 control pools with 10 seeds are already built on the build days (46 million trades, 3 hours, done once). The test days open only after the read is written to the log | Yes | – |
| Organize strategies in the Lab | Groups: create, rename, delete, move; folding sections | From a chat ("file X under Gold") | On the Lab page |
| No more gaps | See section 3 | The refill; the watchdog; the report | The chart drawing |

## 3. The gaps
Three causes were stacked. (1) The live feed is thinned and 10 minutes late (item 1 above). (2) The hourly refill fetched the real
ticks from the broker and then threw them away, because it refused to merge when sizes differed: 91 refusals, 28 sessions frozen.
(3) The Mac kept dropping off the network.

Fixed and running since 01:30 ET: the refill now merges by trade (same id, time and price: the smaller size is kept), keeps what it
fetched, waits for the desk's token instead of giving up, and asks again for ticks that are still missing. The files it rewrites were
backed up first (`~/FUTURES DATA/_backups/2026-10-06_before_merge_rule3`, 165 files).

Monday 10-05 at 06:39 ET: NQ is whole (203,113 → 427,665 ticks). ES 220,824 → 910,763 and still filling. Nine other markets are filling.
No merge has been refused since the fix. Monday stays at the broker until 8 pm ET tonight.

Cannot be recovered without buying data: Friday 10-02 (13 markets, 35 hours), Wednesday 09-30, and two days where the bought backfill
itself is empty (09-22, 09-11, 13:00-15:00).

Added: a watchdog (late, thin, silent, refused merges, holes about to leave the broker) and a coverage report that tells real holes
from non-holes. First reading on the real archive: 343 sessions whole, 15 filling, 26 lost, 16 vendor gaps, 50 not holes. The old
report said "61 need Massive".

"Never a gap again" cannot be promised while the feed is late and the Mac drops offline. What is true now: a hole inside the broker's
two-day window heals itself within hours, and you are told about a late or thin feed instead of finding it on the chart.

## 4. The proof run
One demo idea went through the real chain on the real build days in 4 minutes: `demo_range_break_nq` (opening range break, NQ,
New York morning, 15-minute bars; neighbors 5-minute, 30-minute and ES).

| Line | Result |
|---|---|
| 2.1 Most settings make money | PASS: 82 % of 128 |
| 2.2 Average trade | **FAIL: $54 (need $70)** |
| 2.3 Beats random entries | PASS: 96.2 % (need above 95 %) |
| 2.4 Trades | PASS: 829 |
| 2.5 Neighbors | PASS: 2 of 3 (ES lost) |
| 2.6 Long and short | PASS: both make money |
| 2.8 Monte Carlo | **FAIL: 23 % of runs (need 75 %)** |

It is in the Lab under "Ideas", round 1 of 5 used. Delete it if you do not want it: it is only a proof.

## 5. Decisions I took while you slept — say if you want any changed
1. An idea is saved in the Lab as a record (card, settings, verdict). It is not yet code the tester can trade.
2. The prop simulator counts open losses, as Lucid does. The tester page's own Monte Carlo tile still uses the end-of-day rule.
3. "Above 95 %" is read strictly; "the middle variant" is the median; the default is the middle of the variants that make money on
   the build and on the build with worse fills.
4. A used test read is refused. A second look is possible only from the command line and is labelled SECOND LOOK.
5. The tester page still records a run on the test days and never refuses (your instruction of 27 Sep). The toolkit refuses.
6. No idea batch was run. The waiting batch stays waiting.
7. The 15 old saved strategies are written into the read log as used.

## 6. Not done
- Runnable tester drafts (so the tester can trade an idea's code, needed for the "live equals test" line on an eval).
- An ideas panel on the Lab page.
- What version 1 refuses: a home of "all", the evening session, two filters at once, clock-time ideas, Level 2 filters.
- The branch `fix/depth-stamp-skew` (makes the desk's pre-open check fail on a late feed) is not merged: it changes how the desk
  decides to trade, so it is your call. With the feed late, it is worth a look today.
- Every build result carries a note that the control pools were written before the last engine edit. They were re-checked
  (12 pools, 10,969 trades, none differ); the note stays until they are re-stamped.
