# Two directions for the Desk "Today" screen

Files: `today-A.html`, `today-B.html`, screenshots `today-A-light.png`, `today-A-dark.png`, `today-B-light.png`, `today-B-dark.png`. Same fake data in both. Open the HTML files in a browser; the bar at the top has a light/dark button and a "Show Server chip" toggle.

| | A: quiet and dense (Bloomberg meets Linear) | B: airy (Apple Stocks) |
|---|---|---|
| 1. Look | Tables first. 13 px rows, hairlines, graphite and silver. | Big numbers and cards. 15-17 px type, room around everything. |
| 2. Day net | A KPI strip: one figure among four. | A 64 px figure, LIVE shown apart under it. |
| 3. Safety row | 52 px bar. Machine chip, ARMED (28 px), chart-trading chip, Kill all (36 px, hold 1 s). | 64 px bar, glass only here. Chips 34 px, ARMED 14 px bold, Kill all 44 px. |
| 4. Accounts | A table. The LIVE row is tinted red. | Three cards. The LIVE card has a 2 px red ring. |
| 5. Strategies | 6 rows fit with the accounts in one screen. Long names cut with a tooltip. | 4 to 5 rows per screen. 44 px switches. |
| 6. Changes (7 days) | Right rail, three entries with old to new and Put back. | A button with a count in the header, plus a card at the bottom. |

Both keep LIVE, ARMED, Kill all and the machine name as the loudest things on screen. Both use red only for armed, Kill and loss, orange for warnings, green for profit. Nothing in either mockup weakens a confirm.

**Recommendation: A's density with B's top.** Use A as the base, because you read a lot of rows (strategies, accounts, trades) and A shows them all without scrolling. Take two things from B: the large day-net figure with LIVE apart, and the larger safety row (34 px chips, 44 px Kill all). Keep glass on the top bar only, with a solid fallback. Give B's airy cards to the Lab pick screen, where there is one decision at a time.
