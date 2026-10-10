# A fill-in form to make a Lab strategy

> PLAN ONLY. Nothing here is built. No task starts before the owner approves. One fresh subagent a task, review
> between tasks, TDD inside each.

**Goal:** the owner makes a new strategy in the Lab by filling in a form (market, entry rule, stop, target, times),
with no Python and no chat. What comes out is a normal Lab strategy: it is listed, backtested, shown on the chart
and promoted to the Desk like any other.

**The owner's words (2026-10-09):** "i just want to be able to manually create a strategy view it on lab, promote
to desk and run ... just like any strategy", and on the form: "I liked the fill in form option".

**What exists** (read before any task):
- The Lab's + menu: `homebase/static/charts/lab.js` `newMenu` (Paste a script, Open a .py file, three templates:
  Stop straddle, Bar breakout, Blank), `openScript(code, name)`, `save`, `run`; the ⋯ menu `moreMenu`.
- Templates are plain text: `homebase/charts/lab_templates.py` (stdlib only; every template passes
  `draftstore.check_source`; a test runs one end to end in the sandbox).
- A draft is ONE Python class in `~/.homebase/strategies/<name>.py` (`homebase/draftstore.py`). Its `inputs()` already
  become the settings boxes of a backtest (`settingsHtml` in lab.js), so a generated strategy gets its settings
  panel for free.
- The Guide page has a form of its own (`lab.js` around "Write an idea", helpers in `labcode.js`): its field
  components and helper-word style are the model. It makes pipeline idea cards, a different thing; this plan
  does not touch it.
- "Promote to Desk" (plan `2026-10-09-lab-strategy-on-the-desk.md`, built on branch
  `claude/beautiful-clarke-590048`): the door (`homebase/labrun/door.py` `read_source`) notes what the Desk would
  refuse. A form-made strategy must give no such note.

## How it works

1. **Lab > + > "Fill in a form"** (first item of the menu). A dialog with the fields below, each with one line of
   plain words under it, and a live sentence at the bottom that reads the strategy back:
   "NQ: at 09:30 place a buy stop 15 points above and a sell stop 15 points below. Stop 50 points, target 3 x the
   stop. One trade a day. Out by 15:55."
2. **"Make it"** turns the answers into the code of a normal draft and opens it in the editor, named and ready.
   From there everything is the Lab he already has: Save, Run, Show trades on the chart, Promote to Desk.
3. **The answers travel with the file.** The first lines of the generated file are a comment block holding the
   answers. **⋯ > "Edit in the form"** opens the form filled in again. If the code was changed by hand since,
   the form says so and asks before it replaces the code.
4. **The numbers stay adjustable.** Stop, target, offsets and times that are numbers become the strategy's
   settings, so he can change them in the backtest's settings panel and run a heat map without reopening the form.

## The fields (version 1)

| Field | Choices | Refused when |
|---|---|---|
| Name | letters, digits, `_` | taken, or not a valid name |
| Market | NQ, ES, YM, RTY, GC, SI | |
| Entry rule | the list below | |
| Side | Both, Long only, Short only | |
| Stop | points; for the opening range also "the other side of the range" | empty or 0: "Every entry needs a stop." |
| Target | points, or x the stop, or None | below 1 tick |
| First trade from / last entry | New York time | last entry before the first |
| Out by | New York time, at most 15:55 | not after the last entry |
| Trades a day | 1 to 5 (one position at a time) | |

**Entry rules** (each is one small, fixed piece of code; proposed list, Question 1):

| Rule | Its own fields | What it does |
|---|---|---|
| Open straddle | time (09:30), distance in points | a buy stop above and a sell stop below the price at that time; the first to fill cancels the other |
| Opening-range breakout | range length in minutes (5 / 15 / 30) | a buy stop above the range's high and a sell stop below its low, placed when the range ends |
| Bar breakout | bar size (1 / 5 / 15 min), how many bars back | at a bar's close above the last N bars' high: buy; below their low: sell |
| At a time | time, side | buys or sells at the market at that time |

Size is not on the form: it is set in the backtest and, later, per account on the Desk.

## Decisions taken (change any of them)

- **The form writes code; it is not a second kind of strategy.** One thing to list, backtest and promote. The
  generator lives beside the templates as plain text (`homebase/charts/lab_forms.py`), not in the research
  toolkit: the app never imports research code.
- **Not the pipeline's blocks.** The Guide's form sends idea cards to the pipeline, which tests them stage by
  stage. This form makes a strategy he can look at right now. A "send this to the pipeline" button is a later step.
- **Every generated entry carries a stop, one position at a time, `session_independent = True`.** So the Desk's
  door has nothing to refuse and the walk-forward accepts it.
- **Hand edits are allowed.** The file is his. The form only warns before it overwrites them.

## Tasks

**F1. The generator.** Create `homebase/charts/lab_forms.py` (stdlib only): `schema()` (the fields, choices, limits
and helper words, kept in ONE place), `build(answers) -> code` (a `ValueError` naming the field and the sentence
to show), `read(code) -> {"answers", "intact"} | None` (the header block; `intact` = the code below it is exactly
what `build` gives for those answers), `sentence(answers) -> str`. Tests `tests/test_lab_forms.py`: every rule x
side x stop kind x target kind builds; each result passes `draftstore.check_source` and `static_meta`;
`labrun.door.read_source` gives no note for any of them; `read(build(a)) == a`; a hand edit flips `intact`; each
refusal sentence; and one backtest per rule in the sandbox on a fixture day that takes the expected trade (the way
`tests/test_lab_api.py` runs the bar template).

**F2. The routes** (`homebase/charts/tester_api.py`, beside `/drafts/templates`): `GET /drafts/form` (the schema),
`POST /drafts/form/build {answers}` -> `{ok, code, name, sentence}` or `{ok: false, errors: {field: sentence}}`,
`POST /drafts/form/read {code}` -> `{answers, intact}` or `{answers: null}`. They only build and read text;
saving stays the existing `PUT /drafts/{name}`. `tests/test_lab_api.py`: shapes, refusals, strict bodies.

**F3. The page.** `lab.js` / `labcode.js` / `lab.css` (+ `apple/lab.css`): "Fill in a form" in `newMenu`; the dialog
(the Guide form's field components; fields of the chosen rule only; errors under their field; the live sentence);
"Edit in the form" in `moreMenu` for a draft whose header reads; the overwrite question. Pure helpers in
`labcode.js` with tests in `tests/js/labcode.test.mjs`. It adds one menu item and one dialog and changes no line
of the Promote row.

**F4. Verify without risk.** In a replay copy of the chart service with temp folders: fill the form for each rule,
Make it, Save, Run one month, Show trades on the chart, Edit in the form, change the stop, Run again, Promote.
Then one gated chart-service restart (no running tester job, never 09:20-09:35 ET) to put it live.

## Not in version 1

Indicator filters (trend, VWAP side, RSI), trailing stops, exits after N bars, more than one position at a time,
limit entries, sending a form-made strategy to the pipeline, editing an old hand-written draft in the form.

## Questions for the owner

1. **Are these four entry rules the right first list** (open straddle, opening-range breakout, bar breakout, at a
   time)? Any to drop, or one to add?
2. Filters (trend, VWAP side) in version 1, or later? Proposed: later, one at a time, each only if it earns it.
3. Build this after Promote and shadow are switched on (proposed), or before?
