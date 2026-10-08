# FawPrRUGNpk - "The Only Liquidity Guide You'll Ever Need"
Channel: Fabervaale ENG | https://youtu.be/FawPrRUGNpk | 45 min | written from auto-captions (names garbled: "Stokke / Stucky" is one person; "view up" = VWAP; "feeling" = filling; "Deep Tone" = his charting platform)
Gist: a lesson on reading resting orders (the order book drawn over time as a heat map) together with aggressive orders (bubbles). First half is slides, second half is him narrating a live NQ session on 4 May 2026. Every pattern needs a direction chosen elsewhere first. Also an advert for a webinar and the platform.
## 2. THE IDEAS
Base claim, "path of least resistance" [6:43-7:47]: with equal aggressive volume, price moves toward the side with less resting size. His example: 273 contracts on the five levels above, 122 on the five below, so down is easier.
Patterns (he reads them by eye; no numbers for size, distance or time):
- P1 Reload / "break and protect" [8:48, 12:25-14:57, 16:28-17:29, 20:04-21:04]: price breaks a level with aggressive orders AND new resting orders appear just behind the break on the same side. Enter with the break or on the retest, stop behind the new orders, target the next big resting level. If no new orders appear behind the break, expect a pullback [31:49-32:50].
- P2 Absorption at a wall [11:21-12:25, 17:29-18:31]: a big resting level is hit two or three times with heavy aggressive volume and does not give way; the second push is weaker than the first. Fade back toward the next resting level on the other side.
- P3 "Grill" (credited to another trader) [15:58-16:28, 18:31-19:33]: several stacked levels get eaten one after another, often at the open, with fresh orders added behind each step. Ride it, take part off at each level; it tends to tire at a thick cluster.
- P4 Stacked wall beats one print [19:33-20:04]: four thick levels on one side outweigh a single absorption on the other.
- P5 Iceberg [9:50, 21:04-23:08]: a level shows small size but refills again and again; treat it as a wall. Needs a refill detector.
- P6 Book sweep near the session or all-time high / low [10:21-10:51]: a fast run through the book at an extreme; small stop, large reward. No rule.
- P7 Resting orders moved toward price ("raising the bid") = that side is willing to pay up; a continuation sign [8:18, 30:16-31:17, 37:27].
Direction first: bias from the first-30-minute breakout, VWAP bands, volume profile or cumulative delta [14:57, 33:20-34:21, 39:00]. He will not fade while cumulative delta runs against him.
Stops and targets: stop behind the reload or behind the next wall; targets are the next resting levels; 1:2 to 1:3 mentioned once [17:29]. Spoofing warning [9:19]: resting orders can be fake.
## 3. CLAIMED RESULTS
None. Picked examples plus one live hour in which calls are made both ways as price moves. "Accurate 60-70% of the time" is said about the retail guess of where stops sit [2:09], not about his method. No statistics, no trade list.
## 4. DATA NEEDED
Full-depth order book over time and aggressor-side trades. His walls sit 10-60 NQ points from price (27,875 / 27,915 / 27,940 with price near 27,900). Our Level 2 is the top 10 levels (about 2.5 NQ points), NQ only, history to 2026-07-07. So "next big level as target" and far walls cannot be seen in our data; only the near-touch part can.
## 5. FITS THE TESTER
PARTLY, as filters on NQ only. No pattern here is an entry rule on our list (Level 2 entry rules are refused in version 1).
- Base claim = filters `book agree` and `ahead thin`. Already tested by us: top-10 book direction failed against shuffled nulls at 09:30 (findings 2026-10-02 and 2026-10-03: Level 2 says when, not which way).
- P1 = a breakout entry (donchian, vol_spike_break, liq mode break, orb_confirm) + `stack with` (size added on the trade's side in the last minute) + one flow filter (`delta with` or `sweep with`). Two filters is the card's limit.
- P2 = a fade entry (liq sweep, sweep_rev, pinbar) + `delta against_big` (heavy aggression that failed) and/or `stack with`. `wall blocked` is the wrong way round for a fade (it looks ahead of the trade).
- P7 = `stack with`. P6 = `sweep with / against` on liq or sweep_rev.
- P3, P4, P5: NO. Need deep book and per-level refill counts.
- Exits must bend: his stops and targets are book levels; ours come from the standard table.
A small new entry rule that would make P2 testable: "wall test" = a top-10 level holding at least 5x the median level is traded into twice within N minutes without clearing, and net aggressive volume into it is above its 80th percentile; fade at the close of the second failure. It is a Level 2 trigger, so it waits for the Level 2 entry work.
## 6. REPEATS FROM THE 2026-10-03 BATCH
- P2 (absorption, then a failed second push) = idea 2 there (Robbins Cup winner, PL7LKUsCgIQ), seen from the book instead of the footprint.
- "Resting orders as confirmation" = the Bookmap part of CDyrzNSzn8M.
- "Direction from the day, flow only for timing" = our own finding and the same PL7LKUsCgIQ note.
## 7. LOOK AT SCREEN
- [6:43]-[7:47] the 273 vs 122 slide (the one stated number).
- [12:25]-[14:57] reload examples: how far behind the break the new orders sit and how large they are against the rest of the book.
- [17:29]-[18:31] wall with two failed pushes: size of the wall and of the pushes.
- [21:04]-[23:08] iceberg indicator marks.
- [23:39]-[41:33] live session: his calls change with each push; useful to see how often the read flips.
- [41:33]-[44:36] the recap where the heat map level and his "effort" zone line up (ties to Khgj5q1-ln8).
## 8. RED FLAGS
No rule has a number. Live narration explains each move after it happens and names targets on both sides. Deep-book levels are not in our data, and the near-book version of the main claim already failed in our tests. He warns about spoofing and then treats new orders as intent. Advert for a webinar and a platform.
## 9. VERDICT
SKIP as a source of entry rules. Keep one cheap item: when a breakout idea reaches its filter round on NQ, try `stack with` alone (P1 / P7). That is a "when", not a "which way", and fits what our Level 2 tests found.
