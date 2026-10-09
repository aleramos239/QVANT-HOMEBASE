# A Lab strategy on the Desk: shadow, then paper, then live

> PLAN ONLY. Nothing here is built. No task starts before the owner approves this plan and answers the
> questions in the last section. One fresh subagent a task, review between tasks, TDD inside each.

**Goal:** the owner takes one of his own Lab strategies (a draft with a finished backtest), puts it on the Desk
with one button, and promotes it by hand through three stages: **shadow** (orders are written down, none is sent),
**paper** (orders go to a paper account), **live** (orders go to a real account). Each stage is a switch only he flips.
No chat and no AI is needed to add, promote, stop or remove a strategy.

**Why it cannot run today:** the Desk has no runner for Lab code. A Lab strategy acts through `ctx` (many orders a
day, its own cancels and flattens); the desk engine takes ONE bracketed signal a strategy a day, and its strategy
list comes only from `config._defaults()` (a name that is not shipped there is dropped on load, with its book rows).

**What exists** (read before any task):
- The contract: `homebase/strategies/base.py` (`on_session` / `on_bar` / `on_time`, acting through `ctx`). The
  tester's `Ctx` and fill law: `homebase/backtest/engine.py` (`Ctx`, `_Sim`, `run_session`, `build_bars`).
- Drafts: text in `~/.homebase/strategies/<name>.py` (`homebase/draftstore.py`). A draft's code runs in ONE place
  today: the backtest child inside the macOS sandbox (`backtest/drafthost.register_source`, `backtest/sandbox.py`,
  `draft.sb`: no network, no fork, no keys, no `~/.homebase`). The chart service and the desk never run it.
- The desk engine: `homebase/engine.py`. `handle_signal` (one bracketed `rules.Signal`), `handle_levels` /
  `handle_alert` (two stop legs, sibling cancel), `_place_one`, `_move_brackets` (stop and target re-priced to the
  fill), `clock_tick` (cancel time, flat time), `kill_strategy`, `flatten_strategy`, `flatten_today`. One `DayState`
  per `strategy@account` per day, saved in `day-<date>.json`; the journal is `journal.jsonl`.
- Desk accounts: real, demo (`live: false`) and the chart service's paper accounts through
  `homebase/broker/paper.py` (`PaperAdapter`: the engine runs unchanged on a paper account).
- Chart trading's intake is the model for a narrow, guarded way in: `homebase/desk_api.py` (`/api/trade/*`:
  loopback Host, no Origin, the desk key) and `homebase/trading.py` (parsers, guards, one action at a time an
  account, 5 actions a second).
- The watch list (records only): `homebase/charts/watch.py`, routes in `homebase/charts/tester_api.py`, the Desk
  page `homebase/static/index.html` (`watchView`), the skin `homebase/static/apple/desk.js`.
- The Lab page: `homebase/static/charts/lab.js` (`paintRes`: the result pane of the open strategy, `S.run`).
- `tools/fake_desk.py` (a desk that never reaches a broker), the chart service's `--replay` mode,
  `docs/superpowers/GOTCHAS.md` (staple it to every brief).

**What the owner's 79 drafts actually call** (read 2026-10-09): `market` and `stop_entry`, every one with `sl=`
(one, `nq_long_930_1100`, passes no stop when its stop setting is 0), `oco` on a buy-stop / sell-stop pair, `cancel`, `flatten` (time, bar-count and
trail exits), `flat`, `last_price`, `daily`, `move_brackets_to_fill`, `tp` sometimes absent, up to `max_tr`
entries a session, one position at a time. No `limit_entry`, no own `qty`. Version 1 is cut to exactly this.

## Global constraints

- **Until the owner approves:** no edit to `homebase/engine.py`, `config.py`, `config.json`, `server.py`,
  `trading.py`, `desk_api.py`, `broker/` or anything else the armed desk runs, and no desk restart. Stage 1 is
  built without touching any of them.
- The desk is never restarted or changed without the owner's say. A chart-service restart is gated on no running
  tester job and never 09:20-09:35 ET; the lead does it, never a task's subagent.
- Strategy code never runs in the desk process or the chart-service process, and never outside the sandbox.
- Fail closed (GOTCHAS, money paths): a state the runner or the desk cannot resolve means no new order, and it
  says so on the page.
- A kill or flatten acts on the strategy's own position only, capped at its own filled quantity.
- No new market-data request to the broker: the runner reads the ticks the chart service already has.
- Only the Desk page changes a stage. No chat tool, no Lab button and no file edit by an assistant may do it
  (a test pins that the connector's tool list has no stage tool).
- Changing the code or the settings of a strategy on the Desk = Remove and Add again = back to shadow.
- Words on screen: simple, minimal, no jargon. "Shadow", "Paper", "Live", "Stopped", "Refused: <one sentence>".
- Tests: `.venv/bin/python -m pytest -q tests/<file> -p no:cacheprovider`; JS: `node --test tests/js/<file>`.
- `tests/test_order_bodies_pinned.py` and the engine's existing tests pass unchanged after every task: the
  nq930 and gc_nfp paths are not allowed to move.

---

## The design

### 1. The runner: a process of its own, strategy code one step further out

```
chart service :8852 --ticks (read-only stream)--> RUNNER (own launchd job) --stdin/stdout--> one sandboxed child a strategy
                                                    |
                                                    +-- shadow: its own would-be fills + journal (no desk involved)
                                                    +-- paper / live: one narrow route into the desk :8850
```

- **Where it lives: beside the desk and beside the chart service**, as `python -m homebase.labrun`
  (launchd `com.ramosquant.homebase-labrun`). Not inside the desk: strategy code would share the loop that sends
  the 9:30 orders. Not inside the chart service: it restarts often, and draft code is never run there.
- **One child process a strategy, inside the existing sandbox** (`sandbox.wrap`; a tighter profile `labrun.sb` if
  `draft.sb` allows more than the child needs). The child holds the strategy object and a `LiveCtx`. It has no
  network, no keys, no files to write. It reads one event a line on stdin and answers one line on stdout: the
  orders that handler asked for.
- **Events**, made by the runner from the tick stream, in the tester's order: `session` at
  `session_window[0]`, `bar` at each bar close (the tester's own `build_bars` alignment, built from ticks, not
  from the broker's minute bars), `time` for each of `times()`. A bar or a time with no print closes 1 s after
  its moment by the wall clock. Before each event the child is first told every fill since the last one, so
  `ctx.flat` and each order's status are true when the handler runs (the contract has no fill handler; the
  tester works the same way).
- **How a bug can never stall the armed desk:**
  1. The desk never calls the runner and never waits for it. Traffic goes one way: the runner asks, the desk
     answers. The desk's event stream to the runner has a bounded queue and drops a slow reader, like
     `/api/trade/stream`.
  2. A handler that raises: the tester's law, live. The strategy is **stopped for today**, its unfilled entries
     are cancelled and its position is flattened.
  3. A slow handler or an endless loop: every event has a 1 s deadline. No answer: the child is killed, then
     the same as 2.
  4. A flood: at most 20 orders an event and 64 KB a line from the child; at the desk 5 requests a second and
     the day's entry cap. Over the limit is a refusal; three refusals in a row stop the strategy for today.
  5. The runner itself dies: the desk hears no heartbeat for 20 s, cancels that strategy's unfilled entries and
     marks it "Runner down". An open position keeps its broker-held stop (and target) and the desk's own flat
     time. (Question 5: get out at once instead.)
  6. The 9:30 bot goes first: a Lab order that arrives while any timer strategy is `placing` waits for its acks
     (2 s at most), then goes. nq930's `place_ms` in the journal is compared before and after (Task 9).
- **Late or missing prices:** when the newest tick is more than 2 s behind the wall clock for 5 s, or the stream
  is down, the runner sends no new entry and the page says "Prices are late". Cancels and flattens still go.
  (On 2026-10-06 the live feed was found 10 minutes late; a late feed makes shadow results worthless and live
  entries wrong, so this gate is not optional.) Markets with no live ticks in the chart service cannot be added.

### 2. Shadow

- **Add to Desk** (Lab) freezes a copy: the draft's source text, its sha256, the settings of the finished run,
  the run id and its headline numbers. Refused unless the open strategy is a draft, its run is finished, and the
  run was made from exactly this source (`draft_sha256` in the run's `request.json`). Store: `~/.homebase/desklab/<name>.json`
  (written by the chart service's routes, like `watch.py`). A new strategy is always shadow.
- The runner hosts it on live prices. Every order it would send is journaled
  (`~/.homebase/desklab/<name>/journal.jsonl`: time, call, side, price, stop, target, size, and the door's
  verdict as if it were live: "would be refused: no stop"). **Nothing is placed anywhere.**
- Would-be fills come from the tester's own fill code (`_Sim`) fed tick by tick, so `ctx.flat`, OCO and brackets
  behave as in the backtest and the strategy takes its second and third trades of the day.
- **The daily match:** after the session the tester runs the same frozen code on the day's recorded ticks. The
  Desk shows "Matched the backtest: 3 of 3 trades" or the first difference. A strategy that does not match its
  own backtest is not ready for paper.

### 3. Paper

- **Paper is the live road with a paper account at the end.** Orders go runner -> desk -> engine ->
  `PaperAdapter` -> the chart service's paper book. The door check, the caps, the broker-held stop, the kill, the
  flat time and the journal are the ones live will use. When he later flips to live, the only thing that changes
  is the account. (Question 1: the cheaper way is to post straight to the paper book and leave the desk alone
  until live; it rehearses nothing.)
- In stage paper the book accepts only paper accounts for this strategy; the engine checks it again at placement.

### 4. Live: the check at the door

Every order from a Lab strategy passes the door at the desk (authoritative) before the engine sees it. The same
rules are run at Add time on the source text (a reading of the code, nothing is executed) and on every shadow
order, so he sees the refusals long before live.

| `ctx` call | Paper / live | The sentence he sees when refused |
|---|---|---|
| `market`, `stop_entry` with `sl=` | Allowed. Sent as ONE broker order with its stop (and target) attached | |
| any entry without `sl=` | Refused | "Every entry needs a stop held at the broker." |
| stop on the wrong side, or target on the wrong side | Refused | "The stop must sit on the losing side of the entry." |
| `tp=` / `tp_rr=` | Optional. With none, the stop and the flat time are the exits | |
| `limit_entry` | Refused in version 1 (no draft uses it) | "Limit entries are not built for live yet." |
| `oco(a, b)` | Allowed for one buy stop + one sell stop of the same size | "Only a buy-stop and sell-stop pair can be linked." |
| an entry while a position is open or another entry is working | Refused | "One position at a time." |
| more entries than the day's cap | Refused | "Daily limit reached (N trades)." |
| own `qty=` | Refused. Size is the account's size in the book, never above the strategy's size cap | "Size is set on the Desk, per account." |
| risk (entry to stop x size) above the cap | Refused | "Stop too far: $X at risk, limit $Y." |
| an entry after the last-entry time or outside the session | Refused | "Too late for a new trade today." |
| an entry while prices are late | Refused (at the runner) | "Prices are late." |
| `cancel(order)` | Always allowed | |
| `flatten()` | Always allowed: own position only, own size only | |
| `move_brackets_to_fill` | Allowed (the desk already re-prices to the fill) | |
| `plot`, `hline`, `skip`, `daily`, `flat`, `last_price`, `now_ns`, `date`, `tick` | Allowed, read or display only | |
| anything else on `ctx` | Does not exist: the strategy stops for today | "Strategy error: ..." |

Set by the owner at the live switch, frozen in the confirm dialog (what the dialog showed is what runs), and
changeable only by going back through the dialog:
- trades a day (default 1), size cap a account (default 1), most dollars at risk a trade (default: none set = live
  refused until he sets one), last-entry time and flat time (default: the strategy's own last `times()` entry,
  never later than 15:55 ET).
- **Flat by a set time is the desk's job, not the strategy's:** `clock_tick` flattens at `flat_et` even if the
  runner is gone.
- Disarmed: journaled only, as today. One strategy a market an account: a Lab strategy cannot be booked on an
  account that another strategy already trades the same market on.
- **Kill and "Flatten & turn off"** are the engine's own (`kill_strategy`, `flatten_strategy`), on the same
  buttons as nq930. Both also tell the runner to stop the strategy for today. The desk-wide Kill covers it too.

**How real fills reach `ctx`** (the desk streams this strategy's order and fill events to the runner; they are
applied before the next handler):

| What happens at the broker | What the strategy sees |
|---|---|
| Entry filled | `order.status == "filled"`, `fill_px`, `ctx.flat` False |
| Entry partly filled | `ctx.flat` False at the first contract; status stays "working" until the rest fills or is cancelled; the exit covers what filled |
| Entry rejected | `order.status == "cancelled"`; the broker's words on the page. It counts toward the day's cap; two rejects stop it for today |
| A fill that beat the cancel | The position is live with its stop; `ctx.flat` False at the next event (the engine's `cancel_raced_fill`) |
| Both legs of a pair filled | The engine's emergency: flatten, cancel, stopped for today |
| Stop or target filled | `ctx.flat` True at the next event |
| The desk cannot resolve an order | No new entry; "Check it" on the page (the engine's `needs_check`) |

**What survives a restart mid-day**

| What restarts | Orders and positions | The strategy |
|---|---|---|
| The desk | Stop and target are at the broker. Day states reload from `day-<date>.json`; the stage, limits and "killed today" reload from disk and the journal | The runner keeps running; new entries wait until the desk answers (no retry of an entry, cancels and flattens retried for 10 s) |
| The runner | Untouched: the desk holds them, cancels unfilled entries after 20 s without a heartbeat, flattens at flat time | Rebuilt by replaying today's ticks and today's real fills through a fresh child. If the rebuilt day does not give the same orders as the journal, it stays **stopped for today** |
| The chart service | Untouched | Blind for some seconds: no new entry while prices are missing; the missed ticks are read back before it goes on |
| The Mac | As the desk row; all three jobs come back at login | As the runner row |

### 5. What the owner does, on the pages

- **Lab > Strategies > (his strategy) > Run > "Add to Desk"** (a row under "Full report" in the result pane).
  Greyed with the reason until a finished run of this exact code is open. After: "On the Desk: shadow" and
  "Open on the Desk". If the code has orders the door may refuse, a note lists them ("1 order can go out with
  no stop: fine in shadow, refused on paper and live").
- **Desk > Strategies:** his Lab strategies are rows like nq930, with a tag for the stage. On the strategy's page:
  - a three-way switch **Shadow | Paper | Live**. Paper and Live open a confirm dialog with the frozen limits
    and accounts. Paper is locked until N shadow days matched (Question 3). Live is locked until the review is
    on file for this exact code (below) and N paper days are done. Going back down (Live -> Paper -> Shadow) is
    always allowed once it is flat.
  - "Today": what it did, or would have done, each line in plain words; refusals with their sentence.
  - "Matched the backtest" for each past day; the accounts and sizes (paper and live); Kill for today;
    "Flatten & turn off"; **Remove** (refused while it holds a position or a working order: "Flatten it first").
- Watch-only Book strategies stay as they are: a record. This plan does not turn them into runners.

### 6. The pre-flight review, before live

- The owner's rule: nothing goes to sim or live without the `strategy-review` skill.
- The Lab's "Request a review" (`charts/reviewpack.py`) already writes the pack. The review is run on the
  **frozen copy**, by sha256, with the shadow and paper journals attached: look-ahead, repaint, sizing, prop
  rules, fees, and "does the Desk send the same orders as the backtest" (the daily match answers that one with
  numbers).
- The verdict is saved beside the strategy (`desklab/<name>.review.json`: sha256, date, pass / fail, findings).
  The Live switch reads it: no passing review for this exact code = locked, with the reason. The review never
  flips the switch. (Question 4: require it before paper too.)

---

## Tasks

Step A is stage 1 and touches nothing the desk runs. Steps B and C touch armed code and start only after a
second, separate yes from the owner.

### Step A: shadow

**A1. `LiveCtx` and the child.** Create `homebase/labrun/__init__.py`, `livectx.py` (the tester `Ctx`'s surface:
the same names and arguments; orders become intent records; `Order` objects with `status`, `fill_px`, `fill_sl`,
`fill_tp` kept true from fill events; stdlib only), `child.py` (loads the frozen source with
`drafthost.register_source`, reads events, writes intents). Tests `tests/test_labrun_livectx.py`: every `ctx`
name a draft uses exists; an unknown name raises; **parity: three recorded fixture days fed tick by tick through
child + `LiveCtx` + the shadow fills give the same trades as `run_session` on the whole day** (a straddle, a
multi-entry bar strategy, a time-exit strategy).

**A2. The door, as pure functions.** `homebase/labrun/door.py`: `check(intent, state, limits) -> sentence | None`
for every row of the table in section 4, and `read_source(text) -> [notes]` (an AST reading; runs nothing).
`tests/test_labrun_door.py`: one test a row, both verdicts.

**A3. The store.** `homebase/labrun/store.py` (`~/.homebase/desklab`, env override for tests; add / get / list /
remove; the frozen copy and its sha256; whole-file writes like `watch.put`). Routes in
`homebase/charts/tester_api.py` beside the watch routes: `GET /desklab`, `POST /desklab/{add|remove}`, with the
watch routes' guard and CORS. Add checks the run's `draft_sha256`. `tests/test_tester_desklab.py`.

**A4. The runner.** `homebase/labrun/host.py`, `__main__.py`, `shadowfills.py` (the tester's `_Sim`, fed tick
by tick), `deploy/com.ramosquant.homebase-labrun.plist`. Ticks: one new read-only, loopback-only stream on the
chart service (`GET /api/labrun/ticks?roots=&since_ms=`: today's ticks from `since_ms`, then live), fed from the
same place `paper_ticks` is. Events, the watchdog (deadline, kill, the crash law), the price-age gate, the
journal, the daily match job (a tester run at 16:20 ET, through the tester's own slots, never 09:20-09:35).
`tests/test_labrun_host.py` with planted bad strategies: raises, `while True`, sleeps 5 s, prints 10 MB,
allocates without end. Each ends "stopped for today" inside 2 s and the next strategy's events are on time.

**A5. The pages, shadow only.** `lab.js` / `labcode.js` / `lab.css`: the "Add to Desk" row and its states.
`index.html` + `apple/desk.js`: the Lab strategies' rows and page (Today, Matched the backtest, Remove). The
stage switch is drawn with Paper and Live locked ("Not built yet"). JS tests in `tests/js/`.

**A6. Verify stage 1 without risk.** (1) Replay: the chart service in `--replay` on a past build day, the
runner pointed at it with a temp store; its shadow trades equal the tester's for that day. (2) Live prices, five
sessions, one strategy: the daily match, the watchdog log, and the desk's own journal untouched (no line from the
runner). Go-live for stage 1 = one gated chart-service restart and loading the launchd job.

### Step B: the desk side (armed code; needs its own yes)

**B1. Lab strategies in the desk's config.** `config.py`: kind `"lab"`, the limit fields (`max_trades_day`,
`max_qty`, `max_risk_usd`, `last_entry_et`), and `load()` reads the store so a Lab strategy is a known strategy
and is not dropped. The stage lives in `desklab/<name>.stage.json`, written by the desk only (absent = shadow).
Tests: nq930 / gc_nfp load byte-for-byte as before; a removed Lab strategy leaves with its book rows.

**B2. Rounds in the engine.** `engine.py`: for kind `"lab"` only, a day may hold several rounds, one open at a
time (`DayState.round`, key `strategy@account#n`), bounded by `max_trades_day`. Entry (single, or a stop pair),
cancel and flatten come in through one new method and reuse `_place_one`, the two-leg `_place`, `_move_brackets`,
`_flatten_state` and the sibling guard. A stop with no target is a legal bracket. An audit list in the brief:
every place that assumes one state a strategy an account (`_kill_one`'s dict by account, `on_fill` routing,
`needs_check`, `bothistory`, `metrics`, `trading.ChartDesk._day_state` / `_bot_orders`). Tests
`tests/test_engine_lab.py` with the fake adapter: three rounds in a day; a partial fill; a reject; a raced
cancel; both legs filled; kill and "Flatten & turn off" mid-round; the flat time with the runner silent; a
restart between rounds. The existing engine tests and the pinned order bodies pass unchanged.

**B3. The way in.** `homebase/labdesk.py` + routes `/api/lab/{intent,stream,heartbeat,state}` under the same
gate as `/api/trade/*` (loopback Host, no Origin, the desk key); the door (`labrun/door.py`, authoritative
here); 5 requests a second; the heartbeat watch; "9:30 bot goes first". `POST /api/lab/stage` on the desk's own
page routes (WriteGuard), refusing Live without a passing review for the sha and without the limits set.
`tests/test_labdesk.py`.

**B4. The fake desk and the runner's desk sink.** `tools/fake_desk.py` learns `/api/lab/*`;
`homebase/labrun/desksink.py`; the rebuild-after-restart (replay ticks and real fills; match or stay stopped).
Tests: `tests/test_fake_desk.py`, `tests/test_labrun_restart.py`.

**B5. The pages, paper and live.** The stage switch with its dialogs and locks, accounts and sizes, Kill,
"Flatten & turn off", refusals in plain words. JS tests.

### Step C: verify, review, promote (each line is a stop for the owner)

**C1. No-risk rehearsal:** replay chart service + fake desk + runner, in the browser: add, shadow, paper, live
switch (fake), a kill mid-trade, a runner kill mid-trade, a fake-desk restart mid-trade.
**C2. Desk restart on the merged code** (his say; only paper booked, as it is today: nq930 on paper-5).
The next morning: nq930's fire and `place_ms` as on the days before.
**C3. Paper:** one strategy on a paper account for the agreed number of sessions; the daily match on real paper
fills; one deliberate "Flatten & turn off" and one deliberate runner stop while it holds a position.
**C4. Pre-flight:** `strategy-review` on the frozen copy with the shadow and paper journals; the verdict on file.
**C5. Live:** he flips the switch, smallest size, one account. First live day: the journal read line by line
against the paper days.

## Not in version 1

Limit entries, more than one position at a time, a strategy's own sizing, moving a stop after the entry (the Lab
contract has no call for it), Level 2 inside a live strategy, pipeline Book strategies as runners, one runner
trading two markets.

## Open decisions for the owner

1. **Paper: through the desk, or straight to the paper book?** Recommended: through the desk. It needs the desk
   change and one desk restart before paper, and in return paper tests everything live will use.
2. **The live limits' defaults:** trades a day (proposed 1), size a account (1), dollars at risk a trade (no
   default: he sets it), latest flat time (15:55 ET).
3. **How many days before each switch unlocks?** Proposed: 5 matched shadow sessions before Paper, 10 paper
   sessions before Live.
4. **Review before live only, or before paper too?** The task says before live; the house rule says "sim or
   live". Proposed: before live, since paper is the rehearsal that feeds the review.
5. **The runner dies while a trade is open:** keep the trade on its broker stop until the flat time (proposed),
   or get out at once?
6. **A strategy crashes or hangs while a trade is open:** get out at once, like the backtest does (proposed), or
   keep the trade on its stop?
7. **Which strategy goes first?** One draft, picked by him, carries the whole ladder before a second is added.
8. **The second yes:** stage 1 (shadow) can be built and switched on without touching the desk. Steps B and C
   change the armed desk. Approve stage 1 alone now, or all three?
