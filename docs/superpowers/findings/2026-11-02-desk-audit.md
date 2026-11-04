# Desk audit (2026-11-02)

How the Desk looks and works today: what is wrong, duplicated, dead or confusing. It was read from the code on main
(28e51f48) and checked on a practice copy of the Desk with the Mac's strategies. Nothing was changed.

## 1. Wrong or contradicting on screen

| What you see | Why it is wrong |
|---|---|
| Today says "Desk armed · 0 strategies on" while 13 switches are ON | The headline counts only strategies on accounts; the switches count shadow ones too. "On" means two things |
| A strategy's page says "Size: $650 at risk a trade" | Its Set up card says "Contracts per account: 1" and "for $ risk, put it in a team" |
| Limits read "Most contracts per account 1000000 · Most at risk per trade $0" | Placeholder numbers shown as if they were real limits |
| Two strategies called "NQ 9:30 STOP AGAINST THE OVERNIGHT MOVE, 1-MIN CANCEL, 22 / 10.25" | Same name, different strategies (`nq_930_against_on`, `..._on2`) |
| Every row has a grey "Shadow" badge, and the sidebar also shows "Off" or "$0" | The same state is said three ways on one row |
| "Shadow" in one place, "practice" in another | Same meaning, two words |
| Your "Shadow" and "Live trading" folders are families | Families were built for variants of one idea. You use them as status folders, and you have to keep them up to date by hand |

## 2. Duplicates: one job, many places

| Job | Places today |
|---|---|
| A strategy's settings | 3 on its page: the Setup summary at the top, the small settings form under it, and the Set up card at the very bottom (under the calendar and history) |
| Size | 5: the account row's contracts, the team's $ risk, Limits, the settings form, and a dead account sheet |
| Take turns | 3: the strategy's switch, the team's "how" choice, the solo card. A team switches it on for each member, but switching the team off leaves it on, out of sight |
| Which team a strategy is in | 4: the team card, the Manage list, the Setup summary row "Group", the solo card |
| A team itself | 2 files (Desk groups and account groups) kept in step by code. When they drift apart, a "Remove orphan" repair row appears |
| Strategy ON/OFF | 3 switches. The chart-side one skips the owner check and does not cancel waiting entries when it turns a strategy OFF |
| Getting rid of a strategy | 6 words: Remove, Archive, Delete, Delete history, Hide, Unassign |
| Account day stop | 2-3: Accounts popup "Day take $", the dead account sheet, Limits |
| "Is everything ready?" | 5: the bulb list, the ready strip, the pre-open banner, Settings › Health, Activity |
| Calendars | 3: per account, per strategy (Shadow/Live), the LIVE popup |

## 3. Dead weight (nothing uses it)

| Piece | Note |
|---|---|
| The per-account Settings sheet (`acctset.js` panel, its popup markup) | Nothing opens it any more. Keep its small helper, which other pages use |
| The built-in strategy page (straddles: RR fields, Test fire, Take-turns switch, built-in archive/restore) | No built-in strategy is left on the Mac. **Check the server's config before removing it** |
| "Show on home page" switches (Manage algos) | A per-browser hide that duplicates families and the archive |
| Server routes with no caller: `POST /api/groups`, `/api/accounts/add`, `/api/diag-permissions`, `/api/selftest-order`, Desk group "kind" | Tests only |
| The "Remove orphan" team repair | Only needed because a team lives in two files |
| `removeDeskLab`, the `?demo=1` preview strategies | Unused |
| Old help text in the Connect wizard ("each strategy's page, under Accounts") | Points at a section that moved |

## 4. Confusing words

| Today | Means |
|---|---|
| team / group / account group / cycle / family | Team, account group and cycle are one thing in three words. Family is something else. "Group" is also the Lab's list group |
| Take turns / rotation / cycle / "one account a trade" | One thing, four words |
| Armed / ON / enabled / live / shadow / practice | Armed = the whole Desk. ON = a strategy. Live = a real-money account, the LIVE popup AND the live data login |
| Remove / Archive / Delete / Hide / Unassign | Five ways to say "take it away", each doing something different |
| Day take / profit lock / day lock | One setting, three names |
| DEMO on funded prop accounts | Funded Apex accounts show as DEMO |
| "Lab" tab vs "backtest" page | Same page |

## 5. Silent traps (a strategy can't trade, and nothing on the page says why)

| Trap | Said anywhere? |
|---|---|
| A new version, or Limits removed, takes the strategy off its accounts | No |
| A team turned OFF leaves Take turns ON, so each strategy trades on one account a trade | No |
| Saving the Set up card wipes the $-risk size, stop-after and "most" fields on each account | No |
| The runner is down or silent | Only on the strategy's page, not in the ready list |
| Two strategies on the same market and account: one waits, or Hold overnight blocks the other | No |
| An open broker position, or one the Desk can't read, blocks the entry | Journal only |
| A window outside the Desk's 18:00-17:00 day: shadow only | No |
| The Lab switch file is missing: every Lab strategy disappears | No |

## 6. Size of it today

8 page layouts · 12 popups · about 14 cards · about 150 buttons · 13 dropdowns · about 34 input boxes.
