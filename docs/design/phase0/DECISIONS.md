# Decisions for the owner

Answer by number, for example "1 B, 2 yes, 3 no". My pick is first in each line. Nothing is built until you answer. Evidence is in `AUDIT.md` (problem numbers in brackets).

1. **Direction.** A (quiet, dense), B (airy), or the hybrid? Pick: hybrid, A's density with B's big day-net and larger safety row. See `DIRECTIONS.md`.
2. **Density default.** Compact (13 px rows) or comfortable (15 px)? Pick: compact for the Desk and Lab, comfortable for Charts dialogs; one switch in Settings.
3. **Glass.** Glass on the top bar and menus only, solid everywhere a number is shown (order panel, DOM, Tape, dialogs, Lab panes)? Pick: yes [10].
4. **Command palette (Cmd-K).** Include it? Pick: yes, but only for going places (Today, a strategy, Accounts, Charts, Lab, Settings). It never arms, kills or flattens; those stay buttons.
5. **Names.** Approve the glossary in `AUDIT.md` section 3 (In-sample months, Test months, Box, Pick, Tries, Shadow, Assign, Account cycle, Put on the Desk, Sample data)? Pick: yes. Retire Build, Unseen, OOS, cell, lock, bot, promote, book, dry run in the UI [20].
6. **VPS app.** Restyle the Chicago server's Desk too? It runs the same code, so it changes by itself once the work is on main (vpssync). Pick: yes, same look, with the machine chip reading "Server · Chicago" in the same loud style. Nothing ships while accounts trade, per vpssync.
7. **Server chip colour.** Today it is blue, 2.45:1 in dark. Pick: the same graphite/silver chip as This Mac, plus a thicker border and the word "Server · Chicago". The word, not the hue, tells them apart [2].
8. **One-click on LIVE.** One-click trading currently can skip the confirm, LIVE accounts included. Pick: always confirm when the account is LIVE; one-click stays for DEMO/PAPER only [5].
9. **DEMO tag on funded accounts.** A funded PA/LTF account is shown as DEMO but acts like LIVE. Pick: show LIVE for it [6].
10. **Charts machine chip.** Add the machine chip and name the machine in every Charts confirm? Pick: yes [1].
11. **Buy colour.** Buy green and Sell red (TradingView), or keep Buy blue? Pick: green/red. Loss text red everywhere [11].
12. **Kill red.** Darker red fill `#c4001a` (light) / `#d92c35` (dark) with white text, so it passes contrast? Pick: yes [3].
13. **Control sizes.** 28 px minimum for anything that moves money; ARMED 34 px; Kill all 44 px on the Desk? Pick: yes [4].
14. **Icons.** SF Symbols to Lucide (delete `apple/symbols.css`, 144,920 bytes)? Pick: yes, owner rule is Lucide only [14].
15. **Old style layers.** Retire shadcn, `apple.css`, `hb.css` and the Charts token set into one `tokens.css` (about 70 tokens)? Pick: yes, in 5 steps, one surface at a time, Charts last [12, 13, 16].
16. **Accent.** Graphite `#48484a` light, silver `#d1d1d6` dark, no cream or brown. Confirm? Pick: yes. Brown and the extra oranges leave the chart palettes [13].
17. **Gold Au badge.** Keep `#c9a227`? Pick: yes, the only gold.
18. **Secondary text.** Darken light-mode grey to `#6c6c70` (150 places)? Pick: yes [8].
19. **Today.** Show the big day net, LIVE apart, with an account strip and one readiness? Pick: yes [29].
20. **Changes (7 days).** Move the entry to a header link on Today with a count, keep Put back unchanged? Pick: yes [7].
21. **Scrim.** Darken dialog backdrop to 35% (light) / 45% (dark), one dialog at a time? Pick: yes [21].
22. **Errors.** Replace "Refused - Not Found" style messages with "Could not do X: reason. Next step."? Pick: yes. The 40 worst strings in `AUDIT.md` section 4 [22].
23. **Capital letters.** Sentence case for the 95 shouting strings, except LIVE, DEMO, PAPER, ARMED, Kill all? Pick: yes.
24. **Lab path.** One stepper, delete the dropdown, and a "Box #n" chip after the pick? Pick: yes [24, 26].
25. **Lab verdict.** Show three states per line (pass, fail, not run) and say what was not run? Pick: yes. Note: the Lab can never print REAL while the worse-fills run is not saved. That is a logic gap, not a design one; say if you want it built [27].
26. **In-sample table.** 40-cell grid with mean and "boxes that make money" on top, columns behind Details? Pick: yes [25].
27. **Test-month bands.** Shade the test months on every Lab curve? Pick: yes [28].
28. **Money format.** One formatter: true minus, sign on P&L, whole dollars? Pick: yes [23].
29. **Dark mode.** Keep it as a full theme (not an inverted copy), checked at 4.5:1? Pick: yes.
30. **Rollout.** Order: tokens and safety row, then Desk Today, Accounts, Charts chrome, Lab. Pick: yes, one branch per step, nothing merged without your word.
