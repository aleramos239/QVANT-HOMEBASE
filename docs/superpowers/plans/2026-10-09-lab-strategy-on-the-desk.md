# A Lab strategy on the Desk, just like any strategy

> PLAN ONLY. Nothing here is built. No task starts before the owner approves this plan and answers the
> questions in the last section. One fresh subagent a task, review between tasks, TDD inside each.

**The goal, in the owner's words (2026-10-09):** "i just want to be able to manually create a strategy view it on
lab, promote to desk and run on paper or conncect to live account or funded demo, just like any strategy".

So: he writes a strategy in the Lab by hand, backtests it and sees its trades on the Lab chart, presses
**Promote to Desk**, and from then on it is a Desk strategy like nq930: the same sidebar row, the same page, the
same on / off switch, the same "+ Assign an account" picker (paper, a funded demo or eval login, the live
account), the same "Flatten & turn off". Everything by clicking. No chat.

> **Owner's change, 2026-10-09 (after Step A was built):** "i dont want to 'allowed up to' i just want it to be on
> desk and its automatically off but i can turn on and add into any account".
> So: **no unlock ladder.** A promoted strategy lands on the Desk switched OFF. He turns it on with the same switch
> as nq930 and assigns any account (paper, funded demo, live) with the same picker and the same "Book live"
> confirm nq930 has. With no account it runs in shadow. What stays: the door (a stop on every entry, one position
> at a time, the limits), the desk's own flat time, Kill, "Flatten & turn off", and the daily "Matched the
> backtest" line (now information, not a lock). Wherever this plan says "Allowed up to", "unlock" or "level",
> read this note instead: sections 1.3, 1.4, 5 and the review lock in 6 are replaced by it; task B3's
> `/api/lab/level` and the level file in B1 are dropped; the limits are set on the strategy's page before the
> first account is assigned (no limits set = no account can be assigned).

## Where each step stands today

| # | Step | Today | To build |
|---|---|---|---|
| 1 | Create a strategy by hand | **Works.** Lab > + > a template (Stop straddle, Bar breakout, Blank) or Paste; the editor checks it as he types; Save. No review is needed to save or to backtest | Nothing. One gap to decide: it is Python in an editor, there is no fill-in form (Question 9) |
| 2 | View it on the Lab | **Works.** Run backtests it in the sandbox; "Show trades on the chart" draws every entry and exit; Full report | Nothing |
| 3 | Promote to Desk | **Missing.** The only Promote is on Book cards and is watch-only (a record) | The button on a Lab strategy, and the runner that hosts it |
| 4 | On the Desk like any strategy | **Missing.** The Desk only knows the strategies shipped in its code (`config._defaults()`); any other name is dropped on load | A Lab strategy as a real Desk strategy: row, page, switch, account picker, Flatten & turn off, Remove |
| 5 | Shadow -> paper -> funded demo -> live, with the door checks | **Missing** for Lab code. The parts exist for nq930: one-order-with-its-stop, the paper adapter, the kill, the flat clock | The unlock ladder, the door, several trades a day in the engine |

Steps 1 and 2 were checked on 2026-10-09 by reading the code, running its tests (`tests/test_lab_api.py`,
`tests/test_claude_drafts.py`, `tests/js/labcode.test.mjs`: all pass) and asking the running Lab for its templates
and its list (3 templates, 79 drafts, all readable). They were NOT clicked through in the browser: that walk is
Task A0.

**Why step 3 is not one line of code:** a Lab strategy acts through `ctx` many times a day (entries, its own
cancels, its own exits). The desk engine takes ONE bracketed signal a strategy a day. And Lab code has only ever
run inside the backtest sandbox, never near the armed desk.

**What exists** (read before any task):
- The contract: `homebase/strategies/base.py`. The tester's `Ctx` and fill law: `homebase/backtest/engine.py`
  (`Ctx`, `_Sim`, `run_session`, `build_bars`).
- Drafts: `~/.homebase/strategies/<name>.py` (`homebase/draftstore.py`), routes `/api/tester/drafts*` in
  `homebase/charts/tester_api.py`, the Lab page `homebase/static/charts/lab.js` (`newMenu`, `save`, `run`,
  `showOnChart`, `paintRes`). A draft's code runs in ONE place: the backtest child in the macOS sandbox
  (`backtest/drafthost.register_source`, `backtest/sandbox.py`, `draft.sb`: no network, no fork, no keys).
- The desk engine: `homebase/engine.py` (`handle_signal`, `_place_one`, the two-leg `_place`, `_move_brackets`,
  `clock_tick`, `kill_strategy`, `flatten_strategy`, `flatten_today`; one `DayState` per `strategy@account` a day).
  Config: `homebase/config.py` (`StrategyCfg`, the book). Routes in `homebase/server.py`: `/api/strategy` (on /
  off), `/api/book` (accounts and sizes), `/api/strategy-flatten`, `/api/kill`.
- Accounts on the desk today: paper (`broker/paper.py`), demo-side logins (the funded and eval accounts:
  `live: false`) and live. The page already asks "Book live" before a live account is assigned.
- The narrow, guarded way in that chart trading uses: `homebase/desk_api.py` (`/api/trade/*`) and
  `homebase/trading.py`.
- The Desk page: `homebase/static/index.html` (`renderSide`, `todayRow`, `stratView`, `pickAsg`, `flattenStrat`,
  Manage algos), skin `homebase/static/apple/desk.js`. The watch list: `homebase/charts/watch.py`.
- `tools/fake_desk.py`, the chart service's `--replay` mode, `docs/superpowers/GOTCHAS.md`.

**What the owner's 79 drafts call** (read 2026-10-09): `market` and `stop_entry`, every one with `sl=` (one,
`nq_long_930_1100`, passes no stop when its stop setting is 0), `oco` on a buy-stop / sell-stop pair, `cancel`,
`flatten` (time, bar-count and trail exits), `flat`, `last_price`, `daily`, `move_brackets_to_fill`, a target
sometimes absent, up to `max_tr` entries a session, one position at a time. No `limit_entry`, no own `qty`.
Version 1 is cut to exactly this.

## Global constraints

- **Until the owner approves:** no edit to `homebase/engine.py`, `config.py`, `config.json`, `server.py`,
  `trading.py`, `desk_api.py`, `broker/` or anything else the armed desk runs, and no desk restart.
- The desk is never restarted or changed without the owner's say. A chart-service restart is gated on no running
  tester job and never 09:20-09:35 ET; the lead does it, never a task's subagent.
- Strategy code never runs in the desk process or the chart-service process, and never outside the sandbox.
- No separate "runner" screen. A promoted strategy is drawn by the Desk's own row and page code.
- Only the Desk page unlocks a level or books an account. No chat tool and no Lab button can (a test pins that
  the connector's tool list has none).
- Changing the code or the settings = Promote again = back to shadow.
- Fail closed; a kill or flatten acts on the strategy's own position only, capped at its own filled size
  (GOTCHAS, money paths).
- No new market-data request to the broker: the runner reads the ticks the chart service already has.
- Words on screen: simple, minimal, no jargon.
- Tests: `.venv/bin/python -m pytest -q tests/<file> -p no:cacheprovider`; JS: `node --test tests/js/<file>`.
- `tests/test_order_bodies_pinned.py` and the engine's existing tests pass unchanged after every task: the
  nq930 and gc_nfp paths are not allowed to move.

---

## The design

### 1. What the owner does

1. **Lab:** + New, write or paste, Save, Run, "Show trades on the chart". (Works today.)
2. **Lab:** **Promote to Desk**, a row in the result pane under "Full report". Greyed with the reason until a
   finished backtest of exactly this code is open. It freezes a copy: the code, its fingerprint (sha256), the
   settings of that run and its headline numbers. If the door will refuse some of its orders, a note says so
   up front ("1 order can go out with no stop: fine in shadow, refused on an account").
3. **Desk:** the strategy is in the sidebar under Strategies, with the others. Its page is the strategy page:
   title, on / off switch, today's state, live results, Accounts with "+ Assign an account",
   "Flatten & turn off". Three things are added to that page for a Lab strategy:
   - **Allowed up to:** `Shadow | Paper | Funded demo | Live`. A level is unlocked by him, here, in order. A
     locked level shows why ("Needs 5 matched shadow days: 2 so far"). Unlocking Funded demo or Live opens a
     dialog with the limits (below); what the dialog showed is what runs.
   - **Matched the backtest**, a line a day (section 3).
   - **Remove** (refused while it holds a position or a working order: "Flatten it first").
4. **The account picker is the existing one.** With no account it runs in shadow. He assigns a paper account, a
   funded demo or eval account, or the live account, each with its size. The picker refuses an account above
   the unlocked level with one sentence. It can sit on several accounts at once, like nq930.
5. Pause = the on / off switch. Arm = the desk's Arm. Kill, "Flatten & turn off" and the desk-wide Kill cover it.

### 2. The runner: a process of its own, strategy code one step further out

```
chart service :8852 --ticks (read-only)--> RUNNER (own launchd job) --stdin/stdout--> one sandboxed child a strategy
                                              |
                                              +-- its own would-be fills + notes (always; this is "shadow")
                                              +-- one narrow route into the desk :8850 (when an account is booked)
```

- **Where it lives: beside the desk and beside the chart service**, as `python -m homebase.labrun`
  (launchd `com.ramosquant.homebase-labrun`). Not inside the desk: strategy code would share the loop that sends
  the 9:30 orders. Not inside the chart service: it restarts often, and draft code is never run there. The
  runner has no screen of its own; the Desk page shows what it does.
- **One child process a strategy, inside the existing sandbox.** The child holds the strategy object and a
  `LiveCtx` (the tester `Ctx`'s names and arguments). No network, no keys, nothing to write. It reads one event
  a line and answers with the orders that handler asked for.
- **Events**, made from the tick stream in the tester's order: `session`, `bar` (the tester's own `build_bars`
  alignment, built from ticks), `time`. With no print, a bar or a time closes 1 s after its moment. Before each
  event the child is told every fill since the last one, so `ctx.flat` and each order's status are true when the
  handler runs (the contract has no fill handler; the tester works the same way).
- **How a bug can never stall the armed desk:**
  1. The desk never calls the runner and never waits for it. The runner asks, the desk answers. The desk's event
     stream to the runner has a bounded queue and drops a slow reader, like `/api/trade/stream`.
  2. A handler that raises: the tester's law. Stopped for today, unfilled entries cancelled, position flattened.
  3. A slow handler or an endless loop: every event has a 1 s deadline. No answer: the child is killed, then 2.
  4. A flood: at most 20 orders an event and 64 KB a line from the child; at the desk 5 requests a second and
     the day's entry cap. Three refusals in a row stop it for today.
  5. The runner itself dies: after 20 s without its heartbeat the desk cancels that strategy's unfilled entries
     and shows "Runner down". An open position keeps its broker-held stop and the desk's own flat time.
     (Question 5.)
  6. The 9:30 bot goes first: a Lab order that arrives while a timer strategy is `placing` waits for its acks
     (2 s at most). nq930's `place_ms` is compared before and after.
- **Late or missing prices:** newest tick more than 2 s behind the clock for 5 s, or the stream down: no new
  entry, and the page says "Prices are late". Cancels and flattens still go. (On 2026-10-06 the live feed was
  found 10 minutes late: this gate is not optional.) A market with no live ticks cannot be promoted.

### 3. Shadow: no account booked

- The runner hosts it on live prices. Every order it would send is noted, with the door's verdict as if an
  account were booked. **Nothing is placed anywhere.**
- Would-be fills come from the tester's own fill code (`_Sim`) fed tick by tick, so `ctx.flat`, OCO and brackets
  behave as in the backtest and it takes its second and third trades of the day.
- **The daily match:** after the session the tester runs the same frozen code on the day's recorded ticks. The
  page shows "Matched the backtest: 3 of 3 trades" or the first difference. The would-be fills keep running
  after an account is booked, so on paper and beyond the line also shows the real fills against the model.

### 4. Paper, funded demo, live: one road, different account at the end

- An order goes runner -> the desk's narrow route -> the door -> the engine -> the account's adapter: the paper
  book, the demo-side login, or the live login. The door, the caps, the broker-held stop, the kill, the flat
  clock and the journal are the same on all three. When he moves up a level, only the account changes.
- **Several accounts, one strategy:** the engine fans an order out to every booked account at that account's
  size, as it does for nq930. The strategy sees itself as **not flat while any account holds a position or a
  working entry**, and an order as filled when the first account fills. Its cancels and flattens go to every
  account. An account whose entry was rejected sits that trade out.

**The door** (at the desk, authoritative; the same rules are read from the code at Promote and run on every
shadow order, so he sees the refusals long before an account is at stake):

| `ctx` call | On an account | The sentence he sees when refused |
|---|---|---|
| `market`, `stop_entry` with `sl=` | Allowed. ONE broker order with its stop (and target) attached | |
| any entry without a stop | Refused | "Every entry needs a stop held at the broker." |
| stop or target on the wrong side | Refused | "The stop must sit on the losing side of the entry." |
| `tp=` / `tp_rr=` | Optional. With none, the stop and the flat time are the exits | |
| `limit_entry` | Refused in version 1 (no draft uses it) | "Limit entries are not built yet." |
| `oco(a, b)` | Allowed for one buy stop + one sell stop of the same size | "Only a buy-stop and sell-stop pair can be linked." |
| an entry while a position is open or another entry is working | Refused | "One position at a time." |
| more entries than the day's cap | Refused | "Daily limit reached (N trades)." |
| own `qty=` | Refused. Size is the account's size in the book, never above the size cap | "Size is set on the Desk, per account." |
| risk (entry to stop x size) above the cap | Refused | "Stop too far: $X at risk, limit $Y." |
| an entry after the last-entry time or outside the session | Refused | "Too late for a new trade today." |
| an entry while prices are late | Refused (at the runner) | "Prices are late." |
| `cancel(order)`, `flatten()` | Always allowed: own orders, own position, own size | |
| `move_brackets_to_fill` | Allowed (the desk already re-prices to the fill) | |
| `plot`, `hline`, `skip`, `daily`, `flat`, `last_price`, `now_ns`, `date`, `tick` | Allowed: read or display only | |
| anything else on `ctx` | Does not exist: stopped for today | "Strategy error: ..." |

**The limits**, set by him in the unlock dialog and frozen there: trades a day (default 1), size cap an account
(default 1), most dollars at risk a trade (no default: Funded demo and Live stay locked until he sets one),
last-entry time and flat time (default: the strategy's own, never later than 15:55 ET).
- **Flat by the set time is the desk's job:** `clock_tick` flattens at the flat time even if the runner is gone.
- Disarmed = written down only, as today. One strategy a market an account: it cannot be booked on an account
  that another strategy already trades the same market on.
- **Kill and "Flatten & turn off"** are the engine's own, on the same buttons as nq930; both also stop the
  strategy in the runner for today.

**How real fills reach `ctx`:**

| At the broker | What the strategy sees |
|---|---|
| Entry filled | `order.status == "filled"`, `fill_px`, `ctx.flat` False |
| Entry partly filled | `ctx.flat` False at the first contract; "working" until the rest fills or is cancelled; the exit covers what filled |
| Entry rejected | `order.status == "cancelled"`; the broker's words on the page. Counts toward the day's cap; two rejects stop it for today |
| A fill that beat the cancel | The position is live with its stop; `ctx.flat` False at the next event |
| Both legs of a pair filled | The engine's emergency: flatten, cancel, stopped for today |
| Stop or target filled | `ctx.flat` True at the next event (once every account is out) |
| The desk cannot resolve an order | No new entry; "Check it" on the page |

**What survives a restart mid-day:**

| What restarts | Orders and positions | The strategy |
|---|---|---|
| The desk | Stop and target are at the broker. Day states, the unlocked level, the limits and "killed today" reload from disk and the journal | The runner keeps running; entries wait until the desk answers (an entry is never retried; cancels and flattens are, for 10 s) |
| The runner | Untouched: the desk holds them, cancels unfilled entries after 20 s without a heartbeat, flattens at the flat time | Rebuilt by replaying today's ticks and today's real fills through a fresh child. If the rebuilt day does not give the same orders as the journal, it stays **stopped for today** |
| The chart service | Untouched | Blind for some seconds: no new entry; the missed ticks are read back before it goes on |
| The Mac | As the desk row; all jobs come back at login | As the runner row |

### 5. The unlock ladder

| Level | Accounts the picker offers | Unlocks when |
|---|---|---|
| Shadow | none | at Promote |
| Paper | paper accounts | N shadow days matched the backtest (Question 3) |
| Funded demo | + demo-side logins (funded, eval) | N paper days, the limits set, the review on file (below) |
| Live | + the live login | N funded-demo days, his "Book live" confirm, the review still valid for this code |

Going down a level is always allowed once it is flat. Promote again (new code or settings) starts at Shadow.

### 6. The pre-flight review

- The owner's rule: nothing goes to sim or live without the `strategy-review` skill.
- The Lab's "Request a review" (`charts/reviewpack.py`) writes the pack. The review reads the **frozen copy**,
  by fingerprint, with the shadow and paper notes: look-ahead, repaint, sizing, prop rules, fees, and "does the
  Desk send the same orders as the backtest" (the daily match answers that with numbers).
- The verdict is saved beside the strategy (`desklab/<name>.review.json`). The Funded demo and Live locks read
  it: no pass for this exact code = locked, with the reason. The review never unlocks anything itself.
- This is the one step that is not a click (Question 4).

---

## Tasks

### Step A: promote and shadow. Nothing the armed desk runs is edited; no desk restart.

**A0. The hand walk (lead, in the browser, outside 09:20-09:35 ET):** + New from the "Bar breakout" template,
rename, Save, Run on one month, "Show trades on the chart", Delete. Write down anything that needed the chat.

**A1. `LiveCtx` and the child.** Create `homebase/labrun/__init__.py`, `livectx.py` (the tester `Ctx`'s surface;
orders become intent records; `Order` objects with `status`, `fill_px`, `fill_sl`, `fill_tp` kept true from fill
events; stdlib only), `child.py` (loads the frozen source with `drafthost.register_source`; events in, intents
out). `tests/test_labrun_livectx.py`: every `ctx` name a draft uses exists; an unknown name raises; **parity:
three recorded fixture days fed tick by tick through child + `LiveCtx` + the would-be fills give the same trades
as `run_session` on the whole day** (a straddle, a multi-entry bar strategy, a time-exit strategy).

**A2. The door, as pure functions.** `homebase/labrun/door.py`: `check(intent, state, limits) -> sentence | None`
for every row of the table, and `read_source(text) -> [notes]` (reads the code, runs nothing).
`tests/test_labrun_door.py`: one test a row, both verdicts.

**A3. The store and Promote.** `homebase/labrun/store.py` (`~/.homebase/desklab`, env override for tests; add /
get / list / remove; the frozen copy and its sha256; whole-file writes like `watch.put`). Routes in
`homebase/charts/tester_api.py` beside the watch routes: `GET /desklab`, `POST /desklab/{promote|remove|onoff}`.
Promote checks `draft_sha256` in the run's `request.json`. `tests/test_tester_desklab.py`.

**A4. The runner.** `homebase/labrun/host.py`, `__main__.py`, `shadowfills.py` (the tester's `_Sim`, fed tick by
tick), `deploy/com.ramosquant.homebase-labrun.plist`. Ticks: one new read-only, loopback-only stream on the chart
service (`GET /api/labrun/ticks?roots=&since_ms=`), fed where `paper_ticks` is. Events, the watchdog, the
price-age gate, the notes, the daily match (a tester run at 16:20 ET through the tester's own slots).
`tests/test_labrun_host.py` with planted bad strategies: raises, `while True`, sleeps 5 s, prints 10 MB,
allocates without end. Each ends "stopped for today" inside 2 s and the next strategy's events are on time.

**A5. The pages.** `lab.js` / `labcode.js` / `lab.css`: the "Promote to Desk" row and its states.
`index.html` + `apple/desk.js`: a promoted strategy goes through the SAME `renderSide` row, `todayRow` and
`stratView` as nq930, fed for now from the chart service's list (as the watch list is); plus "Allowed up to"
(Shadow on, the rest locked: "Needs the Desk update"), "Matched the backtest" and Remove. The account picker is
shown and locked with the same sentence. JS tests in `tests/js/`.

**A6. Verify.** Replay: the chart service in `--replay` on a past build day, the runner pointed at it with a
temp store; its shadow trades equal the tester's. Then live prices, five sessions, one strategy: the daily
match, the watchdog log, and the desk's own journal untouched. Go-live = one gated chart-service restart and
loading the launchd job.

### Step B: a real Desk strategy (armed code; its own yes, and one desk restart)

**B1. Lab strategies in the desk's config.** `config.py`: kind `"lab"`, the limit fields (`max_trades_day`,
`max_qty`, `max_risk_usd`, `last_entry_et`), and `load()` reads the store so a promoted strategy is a known
strategy and is not dropped. The unlocked level lives in `desklab/<name>.level.json`, written by the desk only.
From here the page reads it from the desk's own status, and on / off, the book and "Flatten & turn off" are the
existing routes. Tests: nq930 / gc_nfp load byte-for-byte as before; Remove leaves no row behind.

**B2. Several trades a day in the engine.** `engine.py`: for kind `"lab"` only, a day may hold several rounds,
one open at a time (`DayState.round`, key `strategy@account#n`), bounded by `max_trades_day`. Entry (single, or
a stop pair), cancel and flatten come in through one new method and reuse `_place_one`, the two-leg `_place`,
`_move_brackets`, `_flatten_state` and the sibling guard. A stop with no target is a legal bracket. The brief
carries an audit list of every place that assumes one state a strategy an account (`_kill_one`'s dict by
account, `on_fill` routing, `needs_check`, `bothistory`, `metrics`, `trading.ChartDesk._day_state` /
`_bot_orders`). `tests/test_engine_lab.py` with the fake adapter: three rounds in a day; two accounts with
different fills; a partial fill; a reject; a raced cancel; both legs filled; kill and "Flatten & turn off"
mid-round; the flat time with the runner silent; a restart between rounds.

**B3. The way in, the door, the ladder.** `homebase/labdesk.py` + routes `/api/lab/{intent,stream,heartbeat,
state}` under the same gate as `/api/trade/*`; the door (authoritative here); 5 requests a second; the heartbeat
watch; "9:30 bot goes first". `POST /api/lab/level` and `/api/lab/remove` on the desk's page routes (WriteGuard).
`/api/book` refuses an account above the unlocked level; the engine checks again at placement.
`tests/test_labdesk.py`.

**B4. The fake desk and the runner's desk side.** `tools/fake_desk.py` learns `/api/lab/*`;
`homebase/labrun/desksink.py`; the rebuild after a restart (match or stay stopped).
`tests/test_fake_desk.py`, `tests/test_labrun_restart.py`.

**B5. The page, unlocked.** The account picker live for Lab strategies with its refusals, the unlock dialogs
with the frozen limits, the review lock, Remove through the desk. JS tests.

### Step C: verify and move up (each line is a stop for the owner)

**C1. No-risk rehearsal:** replay chart service + fake desk + runner, in the browser: create, backtest, promote,
unlock, assign, a trade, "Flatten & turn off" mid-trade, a runner stop mid-trade, a fake-desk restart mid-trade.
**C2. Desk restart on the merged code** (his say; only paper is booked today: nq930 on paper-5). The next
morning: nq930's fire and `place_ms` as on the days before.
**C3. Paper:** one strategy on a paper account for the agreed sessions; one deliberate "Flatten & turn off" and
one deliberate runner stop while it holds a position.
**C4. Pre-flight:** `strategy-review` on the frozen copy with the shadow and paper notes; the verdict on file.
**C5. Funded demo:** he unlocks and assigns one account at the smallest size. **C6. Live:** the same, later.

## Not in version 1

Limit entries, more than one position at a time, a strategy's own sizing, moving a stop after the entry (the Lab
contract has no call for it), Level 2 inside a running strategy, pipeline Book strategies as runners (they stay
watch-only records), one strategy on two markets, a fill-in form for making a strategy.

## Open decisions for the owner

1. **Paper through the desk, or straight to the paper book?** Proposed: through the desk, so paper tests
   everything funded demo and live will use. It needs the desk change and one desk restart before paper.
2. **The limits' defaults:** trades a day (proposed 1), size an account (1), dollars at risk a trade (he sets
   it), latest flat time (15:55 ET).
3. **Days before each level unlocks.** Proposed: 5 matched shadow days, 10 paper days, 10 funded-demo days.
4. **The review** is the only step that needs the chat. Proposed: required before Funded demo and Live, not
   before Paper. Or: before Paper too. Or: his own ticked checklist counts as well.
5. **The runner dies while a trade is open:** keep the trade on its broker stop until the flat time (proposed),
   or get out at once?
6. **The strategy crashes or hangs while a trade is open:** get out at once, like the backtest (proposed), or
   keep the trade on its stop?
7. **Which strategy goes first?** One strategy climbs the whole ladder before a second is promoted.
8. **Approve Step A alone now, or A, B and C?** Step A gives Promote and shadow, in the Desk's own look, with
   the armed desk untouched. Steps B and C change the armed desk.
9. **Making a strategy by hand** today means editing a template's Python in the Lab. Enough, or does he want a
   fill-in form (market, entry rule, stop, target, times)? A form is a separate, later plan.
