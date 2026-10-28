# Homebase design audit, Phase 0

Audit base: main `de614919`. The real main tip was `b121ae08`; `git diff --stat de614919 HEAD -- homebase/static` is empty, so the UI files are the same.
Nothing in the app was changed. Only new files under `docs/design/phase0/` exist on branch `claude/design-phase0`.
All paths are under `homebase/static/` unless they start with `/tmp`. Screenshot names are files in `shots/` (see `shots/INDEX.md`).

## The answer first

1. The safety controls are all there. They are too quiet. "This Mac" is a pale grey 11 px chip in the corner by the gear, far from Arm and Kill. "Chart trading ON" is 10 px text. The Charts page has no machine chip at all and its confirms do not name the machine.
2. White text on the red of Kill and ARMED fails the readable-contrast bar (3.57 light, 3.43 dark; the bar is 4.5). Light-mode grey text fails it in 150 places. The light focus ring fails 3:1.
3. The look is four styles stacked: 492 CSS variables in four naming systems, 521 colours, 46 font sizes, 43 radii, 118 shadows, 14 stylesheets. The Mac skin hides most of it, but every new screen pays for it.
4. The Desk has no big number for the day and no account strip. Readiness is shown five times. "Changes (7 days)" sits at the bottom of a strategy page.
5. The Lab has the right steps but shows them twice (chip row plus a dropdown), draws a 17-column table in a 320 px panel, and cannot show REAL because two lines are never run.
6. Words: the retired Build/Unseen split is still on screen, four sentences are wrong today, 95 strings SHOUT, raw "HTTP 404" reaches people, money has 7 formatters.
7. What to do: one token set (about 70 tokens, from 492), one safety row that is loud, one big day number, one verdict stepper. See `DIRECTIONS.md` (two mockups) and `DECISIONS.md` (numbered questions for you).

## 1. Inventory counts: now and target

Every "now" number comes from `python3 -I /tmp/hb_design/inv_tokens.py` (it parses every CSS file, the Desk `<style>` block and every JS file; full output `/tmp/hb_design/inv_tokens.md`, `.json`) unless a command is shown. "Target" is a proposal, not a measurement.

| Thing | Now | Target | How "now" was counted |
|---|---:|---:|---|
| Distinct colour literals | 521 (225 opaque, 178 alpha, 113 unresolved `color-mix`, 5 named) | about 40 values (20 per scheme) | inv_tokens.py section 1 |
| Colour uses outside a token definition | 1,002 of 1,487 | 0 in chrome (chart canvases keep their own series ramp) | inv_tokens.py |
| CSS variables defined | 492 (`--a-*` 48, `--hb-*` 63, shadcn 30, other 97, `--font-*` 3, `--sf-*` 251) | about 70, one naming system | inv_tokens.py |
| Variables defined, never used / used, never defined | 36 / 7 | 0 / 0 | inv_tokens.py |
| Variable names redefined in 3 or more files | 48 | 0 | inv_tokens.py |
| Variables by scheme (light and dark) | light and dark values for the `--a-*` set in `apple/system.css:24-110` (light) and `:115+` (dark); other sets have a dark block of their own | one token file, `:root` plus `[data-theme=dark]` | read of `apple/system.css` |
| Font sizes | 46 (23 px literals, 7 `var()` forms) | 8 | inv_tokens.py |
| Font families | 16 stacks | 2 (system sans, SF Mono) plus the chart canvas font | inv_tokens.py |
| Font weights | 9 | 3 (400, 600, 700) | inv_tokens.py |
| Radii | 43 atoms | 4 plus pill | inv_tokens.py |
| Shadows | 118 literal (+17 `var()`) | 3 | inv_tokens.py |
| Spacing atoms | 75; 1,199 of 3,107 uses off the 4 px scale; 0 spacing tokens | 12 on a 4 px scale | inv_tokens.py |
| z-index values | 27; 0 tokens | 6 named layers | inv_tokens.py |
| Durations | 21 ms values (+9 easings, 9 keyframes); `--dur-1/-2` defined, never used | 3 durations (120, 180, 260 ms), 2 easings | inv_tokens.py |
| Stylesheets | 14 CSS files; Desk page links 3 (+533-line inline `<style>`), Charts 5, Lab 6 | 5 (tokens, base, desk, charts, lab) | `find homebase/static -name '*.css' \| wc -l` = 14; link counts from inv_tokens.py |
| SF Symbol icon masks | 251 in `apple/symbols.css` = 144,920 bytes | 0; Lucide only | `wc -c apple/symbols.css`; `grep -o -e '--sf-[a-z0-9-]*:' apple/symbols.css \| sort -u \| wc -l` = 251 |
| `backdrop-filter` declarations | 75 | chrome only (about 12) | `grep -rn backdrop-filter . --include='*.css' \| wc -l` = 75 |
| Rules that remove the outline | 45 | 0 without a replacement ring | `grep -rE 'outline: *(none\|0)' . --include='*.css' \| wc -l` = 45 |
| Uses of the light-failing secondary text token | 150 (`--a-label-2`), 48 (`--a-label-3`) | 0 | `grep -o 'var(--a-label-2)' apple/*.css \| wc -l` |
| Tabular-number lines (good, keep) | 119 | keep | `grep -rn tabular-nums . \| wc -l` |
| Reds / oranges / greens doing one job each | 6 / 6 / 8 | 1 / 1 / 1 per scheme | inv_tokens.py section 2.2 |
| Desk inline `style=` / inline `onclick=` | 143 (56 + 87) / 125 (90 + 35) | 0 / 0 | `grep -o 'style="' index.html \| wc -l` (56); `grep -o 'style="' desk/*.js` (87); `grep -o 'onclick=' desk/*.js` (90) and `index.html` (35) |
| `.btn` defined in | 8 places | 1 | `/tmp/hb_design/inv_components.md` section 2.1 |
| Tab looks / switch looks / text-input styles | 6 / 4 / 9 | 1 / 1 / 2 | `/tmp/hb_design/inv_components.md` 2.2-2.5 |
| Money formatters | 7 | 1 | `/tmp/hb_design/inv_text.md` section 6 |
| Table styles in the Lab | 5 | 1 | `/tmp/hb_design/map_lab.md` section 5 |
| Charts outside the trading chart | 13 (4 LightweightCharts, rest SVG or CSS) | 1 shared style | `grep -rn "createChart(" --include='*.js' .` = 5 call sites (which one is the trading chart was not checked per site) |

## 2. The 30 worst problems, ranked

Order: safety first, then readability, then consistency, then words. Each row: what, where, why it hurts you, screenshot, one-line fix.

| # | What | Where (file:line) | Why it hurts you | Screenshot | Fix |
|---|---|---|---|---|---|
| 1 | The Charts page places real orders but shows no machine chip, and its confirms do not name the machine | `charts/tradeui.js:225` (confirm), `:478` (flatten), `:488` (cancel); chip exists only on Desk (`apple/desk.js:56-58`) | You can send an order from Charts without seeing whether it goes through the Mac or the Chicago server | `charts-replay-normal-light-1440` | Put the same machine chip in the Charts toolbar and name the machine in every Charts confirm |
| 2 | The machine chip and "Chart trading ON" chip are the quietest things in the bar; the machine chip sits by the gear, far from Arm and Kill; the Server chip is blue and unreadable in dark (2.45:1) | `apple/desk.css:73-77` (11 px, grey), `:41-45` (10 px, 17 px high), `apple/desk.js:56-58` (placement); blue at `apple/desk.css:75-76`, `index.html:116-117` | The two facts that decide where a LIVE order goes are the smallest text in the bar | `desk-today-light-1440`, `desk-today-dark-1440` | One safety row: machine chip, ARMED, chart-trading chip, Kill, all 13-14 px bold, beside each other (see mockups) |
| 3 | White text on the red of Kill and ARMED fails contrast (3.57 light, 3.43 dark; need 4.5) | `apple/desk.css:52` (ARMED), `:64` (Kill), `:274`, `:386` (alert bar); `apple/system.css:61` (`--a-red #ff383c`) | The most important buttons are the hardest to read in glare | `desk-today-light-1440`, `desk-arm-confirm-light-1440` | Red fill `#c4001a` light (6.25:1) and `#d92c35` dark (4.81:1) with white text; keep red for armed/kill/loss only |
| 4 | The highest-consequence controls are the smallest: Close/Cancel 20 px, ARMED pill 17 px with 10 px text, rail corner 11 px, legend icons 18 px | `apple/charts.css:289` (`.bp-act` 20 px), `:155` (rail corner 11x11), `:134` (`.ib` 18x18); `apple/desk.css:52` (ARMED 17 px) | A mis-click on Close or a missed ARMED costs money | `charts-replay-normal-light-1440` | Minimum 28 px for any control that moves money; ARMED 34 px |
| 5 | One-click trading can skip the confirm, including for LIVE accounts | `charts/trade.js:401` (`sendsWithoutConfirm`), `charts/settings-dialog.js:150-154` (three switches) | A stray click on a chart line can place or cancel a live order | `charts-settings-trading-account-ticked-light-1440` | Owner decision (see DECISIONS): always confirm when the account is LIVE |
| 6 | A funded account sent as "demo" shows a DEMO tag but behaves like LIVE | `desk/book.js:119-129` | A tag says "practice" on an account that may hold real money | `desk-accounts-live-demo-light-1440` | Show a LIVE tag for any account that asks like LIVE; DEMO only when it is truly practice |
| 7 | "Changes (7 days)" with Put back is buried at the bottom of a strategy page; group lines have no Put back | `desk/activity.js:384-502`, embedded at `desk/strategy.js:307`, `desk/labdesk.js:181`, no Put back at `activity.js:471` | The undo for a risky edit is the thing you cannot find | not reached (see section 7) | A header link "Changes (7 days)" with a count on Today (both mockups) |
| 8 | Light-mode secondary text fails contrast (3.84-3.95; need 4.5) in 150 places, many at 10-11 px | `apple/system.css:24-110` (`--a-label-2`); sites `apple/desk.css:73,192,254`, `apple/charts.css:125,275,314`, `apple/lab.css:283,406` | Labels, headers, status bar and tags are hard to read | `desk-today-light-1440`, `lab-strategy-open-light-1440` | Light secondary `#6c6c70` (5.23:1 on white, 4.80 on `#f5f5f7`); never below 11 px |
| 9 | The light focus ring is 2.49:1 (need 3:1); 45 rules remove the outline, some with no replacement | `apple/system.css:60,151-152`; `apple/lab.css:152` (splitter), `:169` (editor), `apple/charts.css:411` | Keyboard users lose their place | code only | Ring `#48484a` solid 2 px light, `#d1d1d6` dark; no outline removal without a ring |
| 10 | Glass and blur sit on data and trade surfaces: floating Order/DOM/Tape, the Settings dialog, Lab panes | `apple/charts.css:177` (`.hbpanel.floating`), `:399` (dialog, 95% pane + blur), `apple/lab.css:88,235` (`#labLib`, `#labRes`), `index.html:268-270` (toast over data) | Prices and results move over blurred pixels; your rule is glass on chrome only | `charts-replay-order-panel-light-1440`, `charts-settings-symbol-light-1440` | Solid surfaces for anything that holds a number; glass for the top bar and menus only |
| 11 | Buy is blue; a loss is drawn in ink, not red | `charts/apple-charts.css:111-117`; `apple/charts.css:283-284` | Buy/profit/loss do not follow TradingView or your palette (green profit, red loss) | `charts-replay-chart-trading-on-account-ticked-light-1440` | Buy green, Sell red (TV convention), loss text red on every table |
| 12 | Four token vocabularies live at once, 48 names redefined in 3+ files | shadcn (`shadcn.css`), charts (`charts/charts.css:9-10`), `--hb-*` (`hb.css:51,68`), `--a-*` (`apple/system.css`) | Every change needs four edits; some never take effect | code only | One `tokens.css`; delete the other three vocabularies |
| 13 | 521 colours; 6 reds, 6 oranges, 8 greens, each doing one job; brown in chart palettes | inv_tokens.py section 2.2; brown at `charts/catalog.js:82`, `charts/labmix.js:106`, `charts/app.js:2484`; red `apple/system.css:61`, `apple.css:29-31`, `charts/charts.css:10` | The same warning reads orange in one place and red in another (see the Charts OFF state) | `charts-replay-chart-trading-OFF-light-1440` | One red, one orange, one green per scheme; remove brown and orange from series ramps |
| 14 | SF Symbols masks (144,920 bytes, 251 masks) where the rule is Lucide only; the Desk has no Lucide at all; text glyphs "x", "‹", "…" used as icons | `apple/symbols.css`; `apple/desk.js:53` (`sf('gear')`); `apple/charts.css:74,104,408`; `index.html:645,648` ("Tv", "Pa" glyphs) | Two icon families, one of them heavy to load | `desk-today-light-1440` | Inline Lucide SVG sprite; delete `symbols.css` |
| 15 | Trebuchet MS in canvas font stacks | `charts/cell.js:27`, `charts/primitives.js:10,278,385,483`, `charts/charts.css:6`, `charts/testerlayer.js:407`, `charts/testerui.js:207,247,1882` (13 matches: `grep -rn 'Trebuchet' . \| wc -l`) | Chart numbers are in a different face from everything else | code only | System font stack with tabular numbers |
| 16 | No scales: 46 font sizes, 43 radii, 118 shadows, 75 spacing atoms, 27 z-indexes, 21 durations, and no tokens for the last three | inv_tokens.py section 1 | Spacing and layering are guesses; things almost line up | code only | Publish the scale in `DECISIONS.md` and enforce it with one lint |
| 17 | `--text2` is used but never defined (the token is `--text-2`) | used at `charts/guide.css:2,7,13,15,18`, `charts/charts.css:1381` (6 uses); `grep -rn -e '--text2 *:' . \| wc -l` = 0 | The Charts guide and legend note fall back to a default colour | code only | Rename to `--text-2` |
| 18 | One thing, many looks: `.btn` is defined in 8 places; 6 tab looks, 4 switches, 9 text inputs, 5 table styles | `shadcn.css:201`, `apple.css:130`, `hb.css:118`, `index.html:240`, `charts/charts.css:~306`, `charts/lab.css:327`, `apple/system.css:305`, `apple/desk.css` | Row actions in one dialog come in four sizes | `desk-accounts-live-demo-light-1440` | One button, one tab, one switch, one input, one table (see `/tmp/hb_design/inv_components.md` section 2) |
| 19 | Icon-only buttons with no accessible name: Charts 26 of 29 buttons have no `aria-label` (25 have only a `title`); Lab 22 of 36 | `charts.html:27-69`; `backtest.html:62-98` (`grep '<button' charts.html \| grep -vc aria-label` = 26) | A screen reader says "button"; touch and keyboard users see no tooltip | `charts-replay-normal-light-1440` | `aria-label` on every icon button (one helper) |
| 20 | Words that are wrong or retired are on screen: the Build/Test/All chips, "Build days", "Unseen days", "starts Monday at 9:30", "9:30 fire" | `charts/tester.js:33-35`, `desklab.js:211`, `charts/allmetrics.js:10`, `charts/labcode.js:557`, `desk/groups.js:356`, `desk/topbar.js:284,295,299,304`, `charts/lab.js:2578,2664` | You see a month split that no longer exists and a day start that is 18:00 ET | `lab-strategy-open-light-1440` (chips not in view) | Replace with "In-sample months" and "Test months"; read the clock from HBClock |
| 21 | Dialogs barely dim the page (20% scrim in light), dialogs stack, and the toast lands on the last row | `apple/system.css:54` (`--a-scrim` 20%), `apple/desk.css:390`; toast `index.html:268-270` (bottom 18 px, glass) | Text around a dialog stays readable and tempting; a toast hides a row | `desk-settings-inspector-open-light-1440`, `desk-chart-trading-on-confirm-light-1440`, `desk-disarmed-toast-light-1440` | Scrim 35% light / 45% dark, one dialog at a time, toast above the content with a gap |
| 22 | SHOUTING and raw errors: 95 strings in capitals, 68 raw `e.message` sites, 14 "HTTP nnn" strings | `/tmp/hb_design/inv_text.md` sections 2 and 4; e.g. `desk/activity.js:46`, `desk/views.js:65`, `desk/labdesk.js:550` | "Refused - Not Found" tells you nothing | `desk-error-toast-refused-notfound-light-1440` | Sentence case; one error line "Could not do X: reason. Next step." (40 worst strings below) |
| 23 | Seven money formatters: ASCII "-" vs true minus, with and without "+", 0 vs 2 decimals | `desk/core.js:68`, `desk/groups.js:290`, `desklab.js:49`, `charts/labab.js:11`, `charts/labmix.js:10`, `charts/allmetrics.js:168`, `charts/tradepure.js:81` | The same dollars read differently on different screens | code only | One formatter: true minus, sign on P&L, whole dollars |
| 24 | The Lab shows its path twice: a chip row and a dropdown that can disagree | `charts/lab.js:2615-2638` (chips), `:2323` (`THREE_TABS` select) | You read one control and use another | `lab-strategy-open-light-1440` | One stepper (Idea, Code check, In-sample, Pick, Test months, Verdict); delete the select |
| 25 | The in-sample table has 17 columns and `min-width:1100px` inside a 320-348 px panel | `charts/tester.js:803-806` (`WF_FIXED_COLS`), `charts/lab.css:641`, `apple/lab.css:11` | You scroll sideways to read the one table that picks a box | code only (the in-sample table was not run) | 40-cell grid, mean and "boxes that make money" above it, columns behind "Details" |
| 26 | After the pick, nothing says which box is under test | `charts/lab.js:2822` (`wfPick`) | You can lose track of the box you locked | code only | A "Box #n" chip in the stepper, table row, verdict header and curve title |
| 27 | The verdict can never say REAL, and unknown lines read as passes | `charts/reallines.js:118-133` (`labRead`), `:62-76` | "Not yet" looks like "almost" | `lab-strategy-open-light-1440` | Three states per line (pass, fail, not run) and a note listing what was not run |
| 28 | 13 charts outside the trading chart share no axes, grid, tooltip or format; series use brown and orange | `charts/lab.js:2023-2056`, `charts/testerui.js:205,245,1880`, `desk/strategy.js:76-129`, `charts/labmix.js:106` (`#8D6E63`, `#E8A23A`); no test-month bands | You cannot compare two curves or see where the test months are | code only | One chart style (hairline grid, right axis, one tooltip); shade test months |
| 29 | Today has no big day number and no account strip; readiness is shown five times; Setup shows twice | `desk/groups.js:341-374` (sentence), `desk/book.js:24-25`; readiness at `apple/desk.js:37,68`, `labdesk.js:470-492`, `strategy.js:58-59`, `index.html:866`; Setup at `strategy.js:303`, `apple/desk.js:88` | You do the sum yourself and read the same status five times | `desk-today-light-1440` | Day net as the biggest figure, LIVE apart; account strip; one readiness |
| 30 | Today breaks at 1024 px and with a long strategy name: the page title collapses to "T..", "Ready" becomes an icon, long names wrap 4-5 lines and push tags around | `apple/desk.css:86,89-91,507-509`; sidebar `desk/strategy.js:2-60` (no truncation rule) | A real Lab id like `nq_fvg_tap_disp_...` pushes the row apart | `desk-today-light-1024`, `desk-today-longlist-longname-MOCK-light-1440` (labelled JS mock) | One ellipsis rule with full name in a tooltip; both mockups show it |

## 3. Glossary: one name per thing

Safety words stay exactly as they are: This Mac / Server · Chicago chip, Chart trading ON chip, LIVE / DEMO / PAPER tags, confirms that name the machine, old to new before Save, Changes (7 days) with Put back, Kill all, Arm, Disarm, Flatten. Counts are from `/tmp/hb_design/inv_text.md` section 3 (script `count.py`).

| Thing | Use | Retire (in UI text) | Evidence |
|---|---|---|---|
| Months used to choose a box | In-sample months | Build, Build days, selection months | 29 in-sample vs 7 Build strings |
| Months held back, read once | Test months | Unseen, Unseen days, test days, out-of-sample, OOS | 48 vs 10/6/15/3 |
| One row of the heat map | Box | cell, variant, combo, way, param set | box 38 vs cell 20 |
| The table | Heat map | Heat-map, heatmap, grid; Level 2 depth is "Depth map" | 11 vs 5 vs 2 |
| Choosing a box | Pick | lock (for a pick), choose | pick 54 |
| Verdict | Real, Luck, Fake, Not yet | PASS/FAIL, REAL/LUCK caps, pipeline states | `charts/reallines.js:62-76` |
| Number of boxes read | Tries | looks, rounds | `reallines.js:111,131` already say tries |
| Mode that sends nothing | Shadow | dry run, journal only, written down, would-be | shadow 23 vs 3/10/9/5 |
| Preview data | Sample data | Preview mode | `desk/demo.js:9` |
| The thing that trades | Strategy | algo, bot, rule, script, card | strategy 139, algo 17, bot 7 |
| Linking an account | Assign / assigned to | book, booked, booking, unbook | book 48 vs assign 9 |
| Round-robin | Account cycle | Take turns (as a label) | 26 vs 9 |
| The app | Desk (capital) | desk, home page, chart service | 108 vs 66 |
| Moving to Desk | Put on the Desk / Remove from Desk | Promote | 9 vs 3 |
| Undo a setting change | Put back (Changes list only) | | |
| Emergency | Kill all (button and confirm) | "Kill everything" | `index.html:575/579`, `desk/topbar.js:131` |
| Exit | Flatten = cancel orders and close | Close / cancel as synonyms | |
| Stop and target | Desk and Lab: Stop, Target, in points; Charts ticket: Stop loss, Take profit, in ticks | SL, TP, "10t", RR | |
| Reward to risk | 1:2 | RR, "Risk : reward" | |
| Costs | Desk "after fees"; Lab "after costs" | before fees, cheque | |
| Stats | Net, Profit factor, Max drawdown, Win rate, Avg trade, Sharpe (traded days only) | PF, WR, maxDD | |
| Prop | Prop sim (the odds), Eval (the firm's challenge) | PROP EVAL | |
| Walk-forward | 3:1 walk-forward | rolling, scheme, stitched, phase | |
| Time | HBClock text + "ET" | New York time, Eastern, hard-coded 9:30 | 9+ bypass sites, `/tmp/hb_design/inv_text.md` section 6 |
| Money | One formatter: true minus, sign on P&L, whole dollars | 7 formatters | |
| Limits | Contracts per account, Risk per trade, Trades per day, Last entry, Flat by | Most contracts / Contracts / At risk mixed; "Day take" stays (your word) with a one-line help | `index.html:764,767` vs `desklab.js:215` |

## 4. The 40 worst strings, old to new

File:line under `homebase/static/`. Rules: answer first, short, calm, verbs on buttons, no capitals for emphasis, no dev words. Anything that names a machine or an account in a confirm keeps doing so. Wording is a suggestion.

| # | file:line | Now | Proposed |
|---|---|---|---|
| 1 | desk/groups.js:356 | Futures are open. The Desk's day starts Monday at 9:30. | Futures are open. The Desk's day began at 6:00 pm ET. (read from HBClock) |
| 2 | desk/topbar.js:295 | was not booked (or was off) at today's 9:30 fire - nothing was due today | Was off or not assigned when it was due today, so nothing ran. |
| 3 | desk/topbar.js:299 | switched on after today's 9:30 fire - its first run is the next trading day | Turned on after today's run time. First run: next trading day. |
| 4 | desk/topbar.js:304 | added after today's 9:30 fire - its first run is the next trading day | Added after today's run time. First run: next trading day. |
| 5 | index.html:664 | Your login is saved securely on this Mac (so you never ...) | Your login is saved securely on {this Mac / the Chicago server}. |
| 6 | desk/topbar.js:31 | Disarm NOT confirmed - ${why}. The desk may still be ARMED: press Kill, or disarm again. | Could not confirm Disarm: {why}. The Desk may still be armed. Disarm again, or press Kill all. |
| 7 | desk/topbar.js:47 | Signals will place REAL bracketed orders on every account assigned in the book (...). | Signals will place real orders, with stop and target, on every assigned account (...). |
| 8 | desk/topbar.js:97 | Kill NOT confirmed - the desk's answer was unreadable. Check every account and flatten at the broker now. | Could not confirm Kill all. Check each account at the broker and flatten there now. |
| 9 | desk/topbar.js:101 | Kill NOT confirmed - the desk said ok but sent no account results. Check every account and flatten at the broker now. | Kill all sent, but no account replied. Check each account at the broker and flatten there now. |
| 10 | desk/topbar.js:174 | ARMED - signals place REAL orders; SL/TP ride broker-side | Armed: signals place real orders. Stop and target sit at the broker. |
| 11 | desk/popups.js:188 | ${N} NOT switched off - ${why}. It may still trade: switch it off again, or Kill. | Could not turn off {N}: {why}. It may still trade. Turn it off again, or press Kill all. |
| 12 | desk/settings.js:141 | Chart pages can then place REAL orders on the accounts you tick there. No size limit. A bot's symbol stays locked on its accounts while the bot is working. Kill turns it off. | Chart pages can then place real orders on the accounts you tick. No size limit. A strategy's symbol stays reserved on its accounts while it works. Kill all turns this off. |
| 13 | desk/settings.js:218 | Apply takes the live data seat: the other machine's charts lose live data. | Apply moves live data to this machine. Charts on the other machine go quiet. |
| 14 | desk/activity.js:46 | FLATTEN FAILED / CANCEL FAILED / CHECK IT | Flatten failed / Cancel failed / Check this |
| 15 | desk/activity.js:131 | ... order REJECTED ... - ${err} | ... order rejected ... : {plain reason} |
| 16 | desk/activity.js:158 | ... end-of-day FLATTEN FAILED ... | ... could not flatten at end of day ... |
| 17 | desk/demo.js:9 | PREVIEW MODE - SAMPLE DATA, NOTHING IS REAL ... | Sample data. Nothing here is real. |
| 18 | desk/popups.js:110 | MONTE CARLO - 10,000 RESAMPLES OF THE TRADE LIST | Monte Carlo: {n} reshuffles of the trades (read {n} from the result; the 10,000 was not verified) |
| 19 | desk/groups.js:269 | N strategies then send each trade to EVERY account booked... | N strategies will send every trade to all assigned accounts... |
| 20 | desk/groups.js:281 | ...then send each trade to EVERY account booked... | ...will then send every trade to all assigned accounts... |
| 21 | desk/popups.js:475 | Its next trade goes to EVERY account it is booked on, not one at a time. | Its next trade goes to all assigned accounts, not one at a time. |
| 22 | desk/popups.js:482 | Its trades then go to ONE account at a time of N... | Its trades then rotate: one account at a time, out of N... |
| 23 | desk/book.js:71 | ${N}: take turns NOT changed - ${why}. | Could not change {N}'s account cycle: {why}. |
| 24 | desk/book.js:151 | It is a SHADOW strategy: its signals are journaled, never placed - the booking stands if that changes. | Shadow strategy: it runs and logs signals, but sends no orders. The assignment stays if that changes. |
| 25 | charts/trade.js:895 | GTC stays working overnight - if it's still working at 09:28 the 9:30 bot skips this account | A GTC order stays open overnight. If it is still open shortly before the strategy's run time, the strategy skips this account. |
| 26 | charts/trade.js:1143, :1627 | CHECK IT / ${label} · CHECK IT - ... | Check this / {label}: check this. ... |
| 27 | charts/trade.js:1232 | BOT BUY ... / BOT STOP ... | Strategy buy ... / Strategy stop ... |
| 28 | charts/tester.js:33-35 | Build · Sep 2021 - Jun 2025 / Test · Jul 2025 → / All (2021-now) | In-sample months / Test months / All months (since Sep 2021), or drop the chips (old split) |
| 29 | charts/labmix.js:70, :97 | Build days ${start} → ${end} (...); "...old runs that may hold test months" | In-sample months {start} to {end} (the months every member covers) |
| 30 | desklab.js:211, charts/allmetrics.js:10, charts/labcode.js:557 | Build days / Test days / Unseen days | In-sample months / Test months / All months |
| 31 | charts/lab.js:2578 | Build and unseen days | In-sample and test months |
| 32 | charts/lab.js:2664 | Rolling has no unseen test months: each one is a later window's pick month. | (delete: rolling is removed) |
| 33 | charts/reallines.js:44 | not picked yet: the owner picks a box, then the other lines are read | No box picked yet. Pick a box and the other lines will fill in. |
| 34 | charts/lab.js:3006, :264 | Cannot go on the Desk: this file is a written record and places no orders. Rebuild the idea as a real strategy first. | This file does not place orders, so it cannot go on the Desk. Rebuild it as a strategy first. |
| 35 | charts/lab.js:1624 (+1623, 1647, 1671, 1833; labcode.js:361-373) | Each idea is judged at one contract after costs: ... A pass is tagged Live, or Live + Prop ... | Delete the dead pipeline text (Queue / Book / "Press On"); hidden by `PIPE_TABS = []` (`charts/lab.js:25`) |
| 36 | charts/testerui.js:1492, charts/tester.js:737 | Every finished heat-map cell is a look. At a 5% level about 1 in 20 looks reads "significant" by luck alone. | Each box you read is one try. About 1 in 20 tries looks good by luck alone. Tries on this strategy: {n}. |
| 37 | charts/tester.js:1054, charts/testerui.js:1951 | Phase check: ... widest net spread across start months (full-span chains) ... | Start-month check: net changes by {x} depending on the start month. |
| 38 | charts/testerui.js:795 | Claude asked to show ${what}: a run is in flight here -- load it once it finishes | A run is still going. Load {what} when it finishes. |
| 39 | charts/tradeui.js:182 | A flatten is already in flight / Another action is in flight | A flatten is already running. / Another action is still running. |
| 40 | charts/orderpanel.js:302, :821 | No: the breakeven and the trailing stop move while this page is open. Yes: the server keeps moving them... / Not armed on the server: ${e.message} - the order itself was sent | Off: breakeven and trailing stop move only while this page is open. On: the server keeps moving them when it is closed. / The order was sent, but the server did not take over its stop moves: {plain reason}. |

Spares worth fixing in the same pass: `desklab.js:198,214,1035`; `desk/activity.js:107,76`; `desk/labdesk.js:550`; `desk/views.js:65` (raw "HTTP"); `charts/lab.js:2398` ("locks" means "saves"); `apple/desk.js:162`; `index.html:575/579` (title "Kill everything" vs button "Kill all"). Full list: `/tmp/hb_design/inv_text.md` section 8.

## 5. Information map per surface

Question every glance answers: am I safe, is it trading, what is my money doing.

### Desk

| Screen | Shown now (in order) | Shown in the new design (in order) | Why |
|---|---|---|---|
| Top bar | ARMED/DISARMED over the clock, readiness word, Arm, Kill (`apple/desk.js:37-58`); machine chip in the inspector corner | Machine chip, ARMED, chart-trading chip, Ready, then Disarm and Kill all on the right | Where an order goes, whether it will fire, and the way to stop it, in one glance |
| Today | A two-line sentence (`desk/groups.js:344-374`), then one row per strategy | Day net (big, LIVE apart), room to daily limit and drawdown, account strip, strategies, Changes entry point | The sum is the first question; you should not do it in your head |
| Strategy row | Title, Shadow tag, status, $, switch | Switch, name, account tag, state, position, last signal, day net | Everything that explains a $ number on one row |
| Strategy page | Name, ON/OFF, Setup (twice), equity, research buttons, five destructive buttons in one row, Changes (7 days) at the bottom (`desk/strategy.js:261-314`) | Day line, Setup once, equity, Changes (7 days), one "More" menu with Delete last and in red | Frequent first, dangerous last |
| Accounts | List in a dialog with Flatten/Reconnect wrapping (`desk/book.js`) | Always-visible strip: tag, name, dot, day P&L, in a trade | The account is the unit of risk |
| Settings | Chart trading, Market data, Clock, Server updates last | Machine name in the title; Server updates first (a morning safety fact) | |
| Activity | Newest first, about 100 event types as sentences | Same, grouped by day, filter for warn/bad | |

### Charts

| Area | Shown now | Shown in the new design | Why |
|---|---|---|---|
| Toolbar | Symbol, intervals, Indicators, layout, Order/DOM/Tape; no machine chip | Add the machine chip and the chart-trading chip; chart type, alert, undo/redo, snapshot as TradingView has them | Same safety facts as the Desk |
| Rail | Favourites row plus 3 groups plus hidden pool; 11 px corner opens groups | One icon per group with last-used tool (TradingView), 28 px target | The corner is the only path to grouped tools |
| Order panel | Buy/Sell tiles (Buy blue), type, qty, account list | Solid panel; Buy green, Sell red; machine and LIVE tag at the top of the panel | Data on glass moves; colours follow TV |
| Bottom panel | Positions / Orders / Fills; Close and Cancel 20 px | Same, 28 px Close/Cancel, loss in red | |
| Settings | 8 tabs; one-click switches in Trading | Solid dialog; LIVE one-click warning copy beside the switch | |

### Lab

| Step | Shown now | Shown in the new design | Why |
|---|---|---|---|
| Path | Chip row plus dropdown (`charts/lab.js:2615,2323`) | One stepper: Idea, Code check, In-sample, Pick, Test months, Verdict (done / current / waiting) | One way to move |
| In-sample | 17-column sheet, text tone only | 40-cell grid, fill = net around $0, mean and "boxes that make money" on top, pick outlined | Judge the average, never the best box |
| Pick | Weak row highlight | "Box #n" chip everywhere after the lock | |
| Test months | Owner-words dialog (`lab.js:2431`, stays) | Same dialog; button shows "runs once" | A safety rule |
| Verdict | Six lines of 9 px grey text | Six rows: icon, plain sentence, right-aligned number; three states; word last | Unknown must not read as pass |
| Curves | Hand-rolled SVG, no axis | One chart style; shaded test-month bands | The 3:1 test months are every 4th month, not one line |

## 6. Accessibility failures

Method: WCAG 2 relative luminance over tokens and rule pairs (`/tmp/hb_design/work_a11y/scan.py`; 2,711 pairs, 174 under 4.5). Full detail `/tmp/hb_design/inv_a11y.md`. Code level only: no runtime test (section 7).

| Failure | Number | Where |
|---|---|---|
| White on red fill (Kill, ARMED, alert bar, destructive) | 3.57 light, 3.43 dark (need 4.5) | `apple/desk.css:52,64,274,386`; `apple/charts.css:355,469-472` |
| Secondary text, light | 3.84-3.95; 150 uses | `apple/system.css:24-110` |
| Tertiary text | 1.88 light, 2.27 dark; 48 uses | `apple/system.css` (`--a-label-3`; placeholders and line numbers) |
| Server chip, dark | 2.45 | `apple/desk.css:75-76` |
| Green text, light | 4.40 on white, 4.21 on `#fafafa` | `apple/system.css:64` (`#248a3d`) |
| Chart-trading chip, light | 4.14 at 10 px | `apple/desk.css:43` |
| Focus ring, light | 2.49 (need 3) | `apple/system.css:60,152` |
| Outline removed | 45 rules, some with no replacement ring | `apple/lab.css:152,169`, `apple/charts.css:411` |
| Icon-only buttons with no `aria-label` | Charts 26 of 29; Lab 22 of 36 | `charts.html:27-69`, `backtest.html:62-98` |
| Click-only rows and divs (no role, no tabindex) | e.g. `index.html:648,668`; `desk/book.js:20,27,274,278`; `desk/activity.js:301,369` | |
| Menus and tablists without arrow keys | Lab menu, Charts tablists | `charts/lab.js:681-694`; `charts/app.js:1091` and 4 more |
| Tables with no `scope` or `caption` | 43 `<th`, 0 `scope=`, 0 `<caption` | |
| Canvas charts with no text alternative | all | `charts/cell.js:60-80` |
| Small targets | 28 px skin default (below 32); under 28: 24 px tab, 18 px icons, 11 px rail corner, 20 px Close/Cancel | `apple/system.css:296-318`; `apple/charts.css:95,134,155,289` |
| Reduced motion not covered | `apple/charts.css:242` (spring), `charts/lab.js:1421` (smooth scroll in JS) | |
| `prefers-contrast` / `forced-colors` | no `forced-colors` rule; contrast boost only inside 4 combined queries | |
| Colour-only meaning | status bulb in `title` only (`index.html:571`, `desk/topbar.js:239-262`); candle legend OHLC has no sign | |

Fixed by the mockups (contrast computed with the WCAG formula): white on `#c4001a` 6.25, on `#c8202a` 5.68, on `#d92c35` 4.81; green text `#1e7a35` on white 5.40; secondary `#6c6c70` on white 5.23; orange `#a83a00` / `#b3430a` / `#c93400` 5.28-5.64; dark red text `#ff6961` on `#1c1c1e` 6.03; dark secondary `#a1a1a6` 6.61; graphite `#48484a` on white 9.12; silver `#d1d1d6` on `#1c1c1e` 11.18.

## 7. What could not be verified

- No runtime measurement. Contrast and sizes come from CSS values and token math, not computed styles. No axe, no screen reader.
- The `web-design-guidelines` source (a vercel-labs raw GitHub file) was not fetched, so that checklist was not applied.
- States not reached in screenshots: market closed, true offline, the "Server · Chicago" chip (the fake server only says This Mac), Changes (7 days) with Put back, old to new before Save, the in-sample table, DOM, Tape and heat map views.
- The long-name screenshots are a labelled JS mock, not a real data state. The replay clock (May 2025) against the calendar (Oct 2026) is a replay artefact.
- Screenshots are 800 px wide, so small text is soft. Tiny grey text may not be readable in them.
- `Monte Carlo ... 10,000 resamples` (`desk/popups.js:110`) was not checked against the server. Server-side error text (Python `detail`/`error`) was not inventoried.
- Reference content (3,011 strings in `charts/catalog.js`, `guide-*.js` and others) was counted, not reviewed.
- The base was stated as `de614919`; the tip was `b121ae08`. The static tree is identical (command above).
- Not done: the Obsidian vault and `LOG.md` were not updated (the audit rule is to change nothing outside the worktree).
- Mockups use fake data and static HTML. They do not exercise the 2.5 s repaint, focus-freeze, or any real endpoint.

## 8. Files

- `docs/design/phase0/AUDIT.md` (this file), `DIRECTIONS.md`, `DECISIONS.md`
- `today-A.html`, `today-B.html` and their screenshots `today-A-light.png`, `today-A-dark.png`, `today-B-light.png`, `today-B-dark.png`
- `shots/` (50 PNGs and `INDEX.md`)
- Inputs (not committed): `/tmp/hb_design/inv_tokens.md`, `inv_components.md`, `inv_a11y.md`, `inv_text.md`, `map_desk.md`, `map_charts.md`, `map_lab.md`
