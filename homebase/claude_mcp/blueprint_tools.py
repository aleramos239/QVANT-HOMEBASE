"""Blueprint tools: run a strategy idea through the house blueprint (research/edge-library/BLUEPRINT.md,
section 2), one tool per phase. A `BlueprintMixin` (see tools.Toolbox, which inherits it), in its own module
like the desk bridge.

Nothing is judged here. Each tool starts the blueprint TOOLKIT -- research/edge-library/bp.py, run with the
research engine's Python -- as a child process and returns what it answers. The contract between the two is
the toolkit plan's section 8 (research/edge-library/out/blueprint/toolkit_plan.md):

    <python> <bp.py> <command> [its arguments] --root=<the idea folder> --json
      blocks                                   what an idea can be built from                 before the card
      card <name> --spec=-                     stdin: {"name", "card", "run"}                 phase 0
      code-check <name> [--store=KEY | --trades=FILE | --run-id=ID] [--looked]                phase 1
      build <name> --reason=TEXT --wait=S                                                     phase 2
      lock <name>                                                                             phase 3
      test <name> --confirm [--early-look] --wait=S                                           phase 4
      sim <name> --account=ID --attempts=N --fee-budget=USD                                   phase 5
      eval-card <name> [--account=ID] [--fills=-]     stdin: {"fills": [...]}                 phase 6
      status [<name>]
      heatmap <name> [--place=home|1|2|...|not_here] [--round=N]     a build round's heat map, as saved
      mc <name> [--on=build|test]              the Monte Carlo tables of the build or the test, as saved
      job <id> --wait=S                        keep waiting on a build or a test

    stdout: ONE JSON object {ok, command, name, status, phase, round, lines: [{line, passed, number, need,
    text}], text, next, job: {id, state, progress} | null, saved, error}; logs go to stderr.
    exit 0 = done (lines may still fail) · 2 = refused (`error` says why) · anything else = it crashed.
    A line's `passed` is true, false or null. null = the line is not judged yet (an eval card before its live
    trades) or it does not apply (2.7 without a filter): the line's own text says which.

The toolkit is looked for at <repo>/research/edge-library/bp.py and run with
$HOME/ONYX TRADING/.venv/bin/python; HOMEBASE_BP and HOMEBASE_BP_PYTHON move them. A toolkit that is not
there is a plain error. The child runs in the toolkit's own folder and never gets this server's stdin (the
JSON-RPC stream): it reads the JSON handed to it, or nothing.

Long commands (build, test) follow the tester tools' wait: the toolkit waits `wait_s` (--wait) and then answers
job.state = running; the same tool called with that job_id keeps waiting (`job <id>`).

heatmap and mc are views: they read what a build or a test saved, run nothing and count no round.

An early look (test --early-look) reads the test days for an idea that is NOT locked, on the owner's clear yes
(his decision of 2026-10-06: "warn, then run if I say yes"). The toolkit labels its answer ("early_look": true,
EARLY LOOK) and keeps it beside the idea's own files (early_look/test.json), never as its test.json. It can
never prove the idea: homebase.ideastore reads no status there, and counts no result that says it is one.

After a command the app's own copies of the idea are brought up to date (homebase.ideastore.sync): idea.json,
the record block on its Lab draft, the Lab group of its status. That is a mirror, never a gate: a Lab file that
cannot be written is said in the tool's text, and the phase's answer stands.

No tool here trades and none asks a service: no request leaves this module.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path

from .. import draftstore, ideastore, paths
from .client import ToolError

ENV_BP, ENV_PYTHON = "HOMEBASE_BP", "HOMEBASE_BP_PYTHON"
DEFAULT_WAIT_S, MAX_WAIT_S = 120, 3600   # tools.py's own, repeated (it imports this module); a test holds them equal
GRACE_S = 60.0                           # past --wait: the toolkit's own start-up and saving
SHORT_S = 300.0                          # not a job: blocks, card, code check, lock, sim, portfolio, eval card, status, views
RUNNING = ("queued", "running")
_JOB_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@-]{0,119}$")
_PLACE_RE = re.compile(r"^(home|not_here|[1-9][0-9]?)$")   # the table a heat map is of, in the toolkit's words
MC_ON = ("build", "test")                                  # the saved result the Monte Carlo tables are of


def toolkit() -> tuple[str, str]:
    """(python, bp.py) as configured -- whether or not they are there."""
    return (os.environ.get(ENV_PYTHON) or str(Path.home() / "ONYX TRADING" / ".venv" / "bin" / "python"),
            os.environ.get(ENV_BP) or str(paths.repo_root() / "research" / "edge-library" / "bp.py"))


def toolkit_stamp() -> tuple:
    """What changes when the toolkit's code or templates do (the newest file time and the file count): the Lab keeps the block
    list with its code until this changes."""
    root = Path(toolkit()[1]).parent
    files = [f for pat in ("*.py", "engine/*.py", "engine/families/*.py", "blueprint/*.py", "blueprint/templates/*.json") for f in root.glob(pat)]
    return (max((f.stat().st_mtime_ns for f in files), default=0), len(files))


# ---------------------------------------------------------------- schemas

def _spec(name, description, props=None, required=()):
    return {"name": name, "description": description,
            "inputSchema": {"type": "object", "properties": props or {}, "required": list(required),
                            "additionalProperties": False}}


_NAME = {"type": "string", "description": "The idea's name: a-z, 0-9 and '_' (2-40 characters, a letter first), e.g. "
                                          "nq_orb_pre. Its Lab draft is draft_<name>."}
_WAIT = {"type": "integer", "minimum": 0, "maximum": MAX_WAIT_S,
         "description": f"Seconds to wait for the job (default {DEFAULT_WAIT_S}); 0 = start it and return the id."}
_JOB = {"type": "string", "description": "A job id an earlier call returned: keep waiting on that job instead of "
                                         "starting again."}
_CARD = {
    "type": "object", "description": "The idea card, lines 0.1 to 0.7, in plain words.",
    "properties": {
        "why": {"type": "string", "description": "0.1 The reason in one sentence: why it should make money."},
        "loser": {"type": "string", "description": "0.1 Who is on the losing side."},
        "home": {"type": "object", "description": "0.3 Its home: ONE market, session and bar size -- where the reason "
                                                  "fits best. The others go under neighbors.",
                 "properties": {"market": {"type": "string", "description": "NQ, ES or GC."},
                                "session": {"type": "string",
                                            "description": "asia, london, pre, nyam, mid or pm."},
                                "bar": {"type": "string",
                                        "description": "The bar size in minutes (5, 15, ...)."}},
                 "required": ["market", "session", "bar"], "additionalProperties": False},
        "neighbors": {"type": "array", "items": {"type": "string"},
                      "description": "0.4 Where else it should work: the next bar sizes, the other sessions or markets "
                                     "it should fit."},
        "not_here": {"type": "string", "description": "0.4 Optional since 2026-10-07 (leave it out: no such table is run). A place it should NOT work; when named it is run and shown, no line reads it."},
        "main_setting": {"type": "string", "description": "0.5 The main setting: the key of settings.params that "
                                                          "carries its 3-4 values."},
        "sides": {"type": "string", "enum": ["both", "long", "short"], "description": "0.6 Both sides, or one."},
        "sides_why": {"type": "string", "description": "0.6 Why."},
        "loses_when": {"type": "string", "description": "0.7 When it should lose: one stretch or kind of market in which "
                                                         "the idea must lose money. No filter is added only to erase it."}},
    "required": ["why", "loser", "home", "neighbors", "main_setting", "sides", "sides_why", "loses_when"],
    "additionalProperties": False}
_SETTINGS = {
    "type": "object", "description": "How the research engine runs it (line 0.2: one entry trigger, at most 2 filters, "
                                     "exits from the standard table only).",
    "properties": {
        "family": {"type": "string",
                   "description": "The entry trigger: one of the engine's bar-based families, e.g. orb."},
        "params": {"type": "object", "additionalProperties": True,
                   "description": "The main setting and its 3-4 values, e.g. {\"or_min\": [\"5\", \"15\", \"30\"]}: "
                                  "each value is one variant."},
        "fixed": {"type": "object", "additionalProperties": True, "description": "Family inputs held at one value."},
        "filters": {"type": "array", "maxItems": 2, "items": {"type": "object"},
                    "description": "At most 2, each {block, side}. A filter is kept only if it wins alone (line 2.7)."},
        "exits": {"type": "string", "enum": ["standard"],
                  "description": "Always \"standard\": the table of 8 stops x 6 targets (none, 0.5, 0.75, 1, 2, 3 x the stop)."},
        "limits": {"type": "object", "additionalProperties": True,
                   "description": "Optional: max_tr (entries per session), dir."}},
    "required": ["family", "params", "exits"], "additionalProperties": True}
# One live order of an eval, as the toolkit reads it (research/edge-library/blueprint/evalcard.py: FILLS, its KEYS in
# their order, a trade's first eight required): a trade, or an order that did not trade.
_WHEN = ["string", "number"]             # a time: ISO 8601 WITH its UTC offset, or epoch milliseconds
_REPLAY = {
    "type": "object", "description": "The tester's replay of the SAME trade, once it is known: {\"entry_time\": ..., "
                                     "\"exit_reason\": ...} -- or {\"no_trade\": true} when the replay did not trade "
                                     "there. Left out: the trade is not held against the test yet (line 6.1 waits for "
                                     "it).",
    "properties": {"entry_time": {"type": _WHEN}, "exit_reason": {"type": "string"}, "no_trade": {"type": "boolean"}},
    "additionalProperties": False}
_TRADE = {
    "type": "object", "description": "A TRADE: an order that filled and is flat again.",
    "properties": {
        "status": {"type": "string", "enum": ["filled"], "description": "Left out: a trade is read as filled."},
        "entry_time": {"type": _WHEN, "description": "When the entry filled: ISO 8601 WITH its UTC offset "
                                                     "(\"2026-10-06T09:45:02-04:00\"), or epoch milliseconds (the "
                                                     "desk journal's ts x 1000)."},
        "exit_time": {"type": _WHEN, "description": "When the trade was flat again, written the same way."},
        "side": {"type": "string", "description": "\"long\" | \"short\" (the desk's \"Buy\" | \"Sell\" are read too)."},
        "size": {"type": "integer", "minimum": 1,
                 "description": "Micros traded: a whole number from 1 (stage A is 1)."},
        "entry_price": {"type": "number", "description": "The average entry fill price."},
        "exit_price": {"type": "number", "description": "The average exit fill price."},
        "net": {"type": "number", "description": "Dollars after commissions, at that size."},
        "exit_reason": {"type": "string", "description": "How it ended: \"tp\" (target), \"sl\" (stop), \"time\" | "
                                                         "\"eod\" | \"flat\" (the clock: ONE reason), or any other "
                                                         "word, compared as it is written."},
        "entry_slip_ticks": {"type": "number", "description": "The entry fill against its trigger, in ticks, worse = "
                                                              "positive (the desk's slip_ticks). Left out: give "
                                                              "trigger_price and it is counted from the two prices. "
                                                              "Neither: line 6.2 is not read."},
        "trigger_price": {"type": "number", "description": "The price the entry was to trigger at: read when "
                                                           "entry_slip_ticks is left out."},
        "replay": _REPLAY,
        "fixed": {"type": "string", "description": "A sentence: this trade's mismatch was a bug, and the bug IS FIXED "
                                                   "(the count goes on)."},
        "note": {"type": "string", "description": "Free words, kept with the trade."}},
    "required": ["entry_time", "exit_time", "side", "size", "entry_price", "exit_price", "net", "exit_reason"],
    "additionalProperties": False}
_NO_TRADE = {
    "type": "object", "description": "AN ORDER THAT DID NOT TRADE where the test did, with entry_time, side and replay "
                                     "when they are known. It is a mismatch (6.1) and, in stage A, the end of that "
                                     "stage A (6.2).",
    "properties": {"status": {"type": "string", "enum": ["missed", "rejected"]}, "entry_time": {"type": _WHEN},
                   **{k: _TRADE["properties"][k] for k in ("side", "replay", "fixed", "note")}},
    "required": ["status"], "additionalProperties": False}

SPECS = [
    _spec("blueprint_blocks", "Blueprint, before the card: the blocks, one plain list of everything an idea can be "
          "built from without writing code -- the entry triggers (families) with their settings, the filters, the "
          "standard exit table, the sessions, the bar sizes, the markets with their cost floors, the Monte Carlo "
          "settings and the size steps -- and of what version 1 of the toolkit refuses. Call this before writing an "
          "idea card (blueprint_card). Runs nothing."),
    _spec("blueprint_card", "Blueprint phase 0, the idea card: write an idea down BEFORE any run -- why it should make "
          "money and who loses, its home, its neighbors and one place it should not work, its main setting with 3-4 "
          "values, both sides or one. Saves the card and the settings in the app, and a record draft in the Lab "
          "(draft_<name>, filed under Ideas). Refused when a line of the card is missing, the exits are not the "
          "standard table, or there are more than 2 filters. Version 1 also refuses a home of \"all\" (it judges ONE "
          "home table: the others are neighbors), the evening session, and limits.trail_atr / limits.exit_bars (exits "
          "of their own): blueprint_blocks lists everything it refuses.",
          {"name": _NAME, "card": _CARD, "settings": _SETTINGS}, ["name", "card", "settings"]),
    _spec("blueprint_code_check", "Blueprint phase 1, the code check (build days only): do the trades do what the card "
          "says? It counts entries outside the session window, more than one position at a time or a trade not flat "
          "by 15:58 ET, a trade count the rule does not imply, winners and losers that do not pay about the target "
          "and the stop, and a trade list that no longer reproduces after a code change -- and names 10 trades to "
          "look at on the chart (the first 5 and 5 at random). Give at most one of store, trades_file, run_id. Call "
          "it again with looked=true once those 10 were looked at. Refused for any day on or after 2025-07-01.",
          {"name": _NAME,
           "store": {"type": "string", "description": "A store key of the research engine."},
           "trades_file": {"type": "string", "description": "The path of a trade list file."},
           "run_id": {"type": "string", "description": "A tester run id (from backtest / list_runs)."},
           "looked": {"type": "boolean", "description": "true = the 10 trades it named were looked at on the chart, "
                                                        "and each entry and exit sits where the rule says (line 1.5). "
                                                        "Default false."}},
          ["name"]),
    _spec("blueprint_build", "Blueprint phase 2, the build (2021-09-22 to 2025-06-30, where all tuning happens): runs "
          "the idea's table and its random-entry control when they are missing, then reads lines 2.1 to 2.9, each "
          "pass or fail with its number. All pass = a LEAD, approved for the out-of-sample test. Every call is one "
          "round: at most 5, each with its reason written before the run. Long: after wait_s it returns a job id -- "
          "call it again with that job_id to keep waiting. Refused without a card, without a reason, at round 6.",
          {"name": _NAME,
           "reason": {"type": "string", "description": "Why this round is run, in a sentence or two: it is saved "
                                                       "before the run. Needed to start a round; not with job_id."},
           "wait_s": _WAIT, "job_id": _JOB}, ["name"]),
    _spec("blueprint_lock", "Blueprint phase 3, the freeze: saves the rule, the variant list, the default variant (the "
          "middle survivor, never the best), the random control and the costs, and returns the lock's hash, the "
          "default and the test range. BEFORE the freeze the default variant is read on its own on the build days "
          "(lines 3.3 to 3.7: profit factor 1.2, net / worst drawdown 3, Sharpe 1, its drawdown at 1 micro under "
          "$2,000, money in 90% of 1,000 reshuffled runs; the drawdown counts open losses): one not met = no "
          "freeze, back to the build. It also SHOWS the default variant's prop odds on the build days (LucidPro "
          "50K; a number, never a pass line). From here "
          "nothing may change: a change is a new version, back to the build. "
          "Refused while any build line fails.", {"name": _NAME}, ["name"]),
    _spec("blueprint_test", "Blueprint phase 4, the out-of-sample test (2025-07-01 on). THE TEST DAYS ARE READ ONCE: "
          "the read is logged before it starts and is never repeated -- not for this idea, not for a relative of it, "
          "not after a failure (a strategy that fails is not re-tuned and re-tested). Run it only for a locked idea "
          "and only when the owner has said to: confirm must be true. Reads lines 4.1 to 4.9; all pass = PROVEN ON "
          "HISTORY, approved for a real eval. Long: after wait_s it returns a job id -- call it again with that "
          "job_id to keep waiting (nothing is read again). Refused when the idea is not locked, its lock no longer "
          "matches, or a read is already on file. The one exception is AN EARLY LOOK (early_look: true): it reads "
          "the test days for an idea that is NOT locked, uses them up for that idea, is labelled EARLY LOOK, can "
          "never prove the idea, and needs the owner's clear yes in chat first -- warn him, then ask (confirm is "
          "still required).",
          {"name": _NAME,
           "confirm": {"type": "boolean", "description": "Must be true: the owner has said to run the one read. The "
                                                         "test days are read once for an idea, and a read cannot be "
                                                         "taken back."},
           "early_look": {"type": "boolean", "description": "true = an EARLY LOOK at the test days for an idea that "
                                                            "is not locked: only after the owner, warned that it "
                                                            "uses the test days up for this idea and can never "
                                                            "prove it, said a clear yes in chat. Default false."},
           "wait_s": _WAIT, "job_id": _JOB}, ["name", "confirm"]),
    _spec("blueprint_sim", "Blueprint phase 5, before the eval is bought: the prop simulator on the test-period trades "
          "of ONE strategy for one account -- per size, the odds of a pass before a bust and of a first payout before "
          "a bust (no day limit), on the plain row and on the \"live is worse\" row (win rate -5 points, winners "
          "-15%). One strategy's bar is line 5.5: 50% or more on each. The 60% within 10 days / 75% within 20 days "
          "bar (line 5.3) is the PORTFOLIO's (blueprint_portfolio); for one strategy it is said, not judged. Open "
          "losses count against the drawdown here, which the tester's own prop tile does not do. attempts and "
          "fee_budget are the owner's numbers (line 5.4): ask him, never guess. Refused until the test is passed.",
          {"name": _NAME,
           "account": {"type": "string", "description": "The account in question: a rule set id from list_prop_rules, "
                                                        "e.g. lucid-pro-50k@2026-09-27b."},
           "attempts": {"type": "integer", "minimum": 1, "description": "How many evals the owner will buy at most."},
           "fee_budget": {"type": "number", "minimum": 0, "description": "The owner's total fee budget, in dollars."}},
          ["name", "account", "attempts", "fee_budget"]),
    _spec("blueprint_portfolio", "Blueprint phase 5 for SEVERAL strategies on one account: two or more ideas that are "
          "each proven on history, each at its default variant, every member at the same size, their test-period "
          "days drawn together. Lines 5.2 (the \"live is worse\" row), 5.3 (eval pass within 10 trading days 60% or "
          "more; maximum payout within 20 trading days 75% or more), 5.6 (no two members are the same idea on the "
          "same market) and 5.7 (every member raises the portfolio's eval odds; one that lowers them stays out). "
          "Open losses count. Refused when a member's out-of-sample test is not passed.",
          {"names": {"type": "array", "items": {"type": "string"}, "minItems": 2,
                     "description": "The ideas of the portfolio: two or more names, each proven on history."},
           "account": {"type": "string", "description": "The account in question: a rule set id from list_prop_rules, "
                                                        "e.g. lucid-pro-50k@2026-09-27b."}},
          ["names", "account"]),
    _spec("blueprint_eval_card", "Blueprint phase 6, the eval: the eval card -- lines 6.1 to 6.9 read on the live "
          "fills so far, and the drawdown table after 10, 20, 30 and 40 trades. Without fills it is the card as it "
          "stands before the first live trade. THE FILLS: one object per live order of the eval, oldest first. A "
          "TRADE (an order that filled and is flat again) must say entry_time, exit_time, side, size, entry_price, "
          "exit_price, net and exit_reason; entry_slip_ticks (or trigger_price), replay, fixed and note are optional. "
          "AN ORDER THAT DID NOT TRADE where the test did is {\"status\": \"missed\" | \"rejected\"}, with "
          "entry_time, side and replay when they are known. A field that is not listed is refused. Refused until the "
          "sim is done. AFTER A HARD ALARM (the drawdown at the 95th percentile: the strategy is switched off), "
          "replay_since_stop = the tester's replay of the days since, and line 6.9 is read on it: the last 5 and 12 "
          "months above $0 and the last 3 months above the long-run pace.",
          {"name": _NAME,
           "fills": {"type": "array", "items": {"anyOf": [_TRADE, _NO_TRADE]},
                     "description": "The live orders of the eval so far, oldest first, as the desk recorded them "
                                    "(desk_journal): one object per order. Left out: no live trade yet."},
           "account": {"type": "string", "description": "The account the card stands on: a rule set id, as given to "
                                                        "blueprint_sim. Left out: the card's own, else the one of "
                                                        "the simulator result saved last."},
           "replay_since_stop": {"type": "array",
                                 "items": {"type": "object", "additionalProperties": False,
                                           "properties": {"exit_time": {"type": ["string", "number"]},
                                                          "net": {"type": "number"}, "size": {"type": "integer", "minimum": 1}},
                                           "required": ["exit_time", "net", "size"]},
                                 "description": "After a hard alarm only: the tester's replay of the strategy on the "
                                                "days since it was switched off, one object a trade (exit_time, net in "
                                                "dollars, size in micros). Needs fills (the eval's live orders)."}},
          ["name"]),
    _spec("blueprint_status", "Blueprint, any phase: where things stand -- every idea with its status (idea, lead, "
          "proven on history, proven live, shelved), phase, round and next step; or one idea (name); or one job "
          "(job_id). Runs nothing.",
          {"name": _NAME, "job_id": {"type": "string", "description": "A job id a build or a test returned."}}),
    _spec("blueprint_heatmap", "Blueprint, a view of what is saved: the heat map of an idea's build -- one table of a "
          "build round as a grid: the table of its home, of a neighbor its card names, or of the place it should not "
          "work. It only reads saved results: it runs nothing and counts no round.",
          {"name": _NAME,
           "place": {"type": ["string", "integer"],
                     "description": "Which table: home (the idea's home), a neighbor by its number on the card (1, 2, "
                                    "...), or not_here (the place it should not work)."},
           "round": {"type": "integer", "minimum": 1, "maximum": ideastore.MAX_ROUNDS,
                     "description": f"A build round that is on file, 1 to {ideastore.MAX_ROUNDS}. Left out: the "
                                    "latest round."}}, ["name"]),
    _spec("blueprint_mc", "Blueprint, a view of what is saved: the Monte Carlo tables of an idea -- the reshuffled "
          "runs of its build, or of its test. It only reads saved results: it runs nothing and counts no round.",
          {"name": _NAME,
           "on": {"type": "string", "enum": list(MC_ON),
                  "description": "build = the tables of the build that is on file; test = the tables of the test that "
                                 "is on file (this tool never reads the test days itself)."}}, ["name"]),
]


# ---------------------------------------------------------------- arguments

def _name(name) -> str:
    """An idea's name (ideastore.validate_name): also what keeps an option out of the command line."""
    try:
        return ideastore.validate_name(name)
    except ValueError as e:
        raise ToolError(str(e)) from None


def _job_id(job_id) -> str:
    if not isinstance(job_id, str) or not _JOB_RE.fullmatch(job_id):
        raise ToolError("job_id: the id a blueprint tool returned")
    return job_id


def _place(place) -> str:
    """The table a heat map is of. A neighbor's number may come as a number."""
    s = str(place) if type(place) is int else place
    if not isinstance(s, str) or not _PLACE_RE.fullmatch(s):
        raise ToolError("place: home, a neighbor's number on the card (1, 2, ...) or not_here")
    return s


def _text(v, key: str) -> str:
    if not isinstance(v, str) or not v.strip():
        raise ToolError(f"{key}: a string")
    return v


def _object(v, key: str) -> dict:
    if not isinstance(v, dict):
        raise ToolError(f"{key}: an object")
    return v


def _wait_s(wait_s) -> int:
    if wait_s is None:
        return DEFAULT_WAIT_S
    if isinstance(wait_s, bool) or not isinstance(wait_s, (int, float)):
        raise ToolError("wait_s: seconds, a whole number")
    return max(0, min(int(wait_s), MAX_WAIT_S))


# ---------------------------------------------------------------- the toolkit's answer

def _last_line(s) -> str:
    return next((ln.strip() for ln in reversed((s or "").splitlines()) if ln.strip()), "")


def _json_object(text):
    """The one JSON object of the contract -- also when a library printed a stray line before it."""
    s = (text or "").strip()
    for cand in (s, s[s.find("{"):s.rfind("}") + 1]):
        try:
            got = json.loads(cand)
        except ValueError:
            continue
        if isinstance(got, dict):
            return got
    return None


def _answer(command: str, p) -> dict:
    """The toolkit's result, or a ToolError that says what happened: refused (exit 2 or ok false), crashed
    (any other exit code), or an answer that is not the contract's."""
    r = _json_object(p.stdout)
    if p.returncode == 2 or (r is not None and r.get("ok") is False):
        r = r or {}
        why = r.get("error") or _last_line(r.get("text")) or _last_line(p.stderr) or "no reason given"
        raise ToolError(f"Refused (blueprint {command}): {why}\nNothing was run."
                        + (f"\nNext: {r['next']}" if r.get("next") else ""))
    if p.returncode != 0:
        raise ToolError(f"The blueprint toolkit crashed (exit {p.returncode}) on `{command}`: "
                        f"{(p.stderr or p.stdout or 'no output').strip()[-600:]}")
    if r is None:
        raise ToolError(f"The blueprint toolkit answered something that is not the agreed JSON on `{command}`: "
                        f"{(p.stdout or 'nothing').strip()[:300]}")
    return r


def _caps(status) -> str:
    """proven_on_history -> PROVEN ON HISTORY, as the blueprint writes a status."""
    return str(status).replace("_", " ").upper()


def _head(r: dict) -> str:
    bits = [f"Blueprint {r.get('command') or '?'}"]
    if r.get("name"):
        bits.append(str(r["name"]))
    if r.get("status"):
        bits.append(_caps(r["status"]))
    if r.get("phase") is not None:
        bits.append(f"phase {r['phase']}")
    if r.get("round") is not None:
        bits.append(f"round {r['round']}")
    return " · ".join(bits)


def _lines(r: dict) -> list[str]:
    """Every pass/fail line the result's own text does not already show, then the count."""
    text, out, failed, na, passed = r.get("text") or "", [], [], [], 0
    for ln in r.get("lines") or []:
        if not isinstance(ln, dict):
            continue
        mark = "PASS" if ln.get("passed") is True else "FAIL" if ln.get("passed") is False else "n/a"
        passed += mark == "PASS"
        if mark != "PASS":
            (failed if mark == "FAIL" else na).append(str(ln.get("line")))
        said = str(ln.get("text") or f"{ln.get('line')} {mark}")
        if said not in text:
            out.append(said)
    if passed or failed or na:
        out.append(f"Lines: {passed} passed · {len(failed)} FAILED" + (f" ({', '.join(failed)})" if failed else "")
                   + (f" · {len(na)} not judged or {'does' if len(na) == 1 else 'do'} not apply ({', '.join(na)})"
                      if na else ""))
    return out


def _report(r: dict, notes=()) -> str:
    out = [_head(r)]
    if (r.get("text") or "").strip():
        out.append(r["text"].strip())
    out += _lines(r)
    if r.get("next"):
        out.append(f"Next: {r['next']}")
    saved = [str(s) for s in r.get("saved") or []]
    if saved:
        out.append("Saved: " + ", ".join(saved[:6]) + (f" and {len(saved) - 6} more" if len(saved) > 6 else ""))
    return "\n".join([*out, *notes])


class BlueprintMixin:
    """Mixed into tools.Toolbox. It needs nothing from it: no service is asked."""

    _bp_grace_s: float = GRACE_S

    def _bp(self, args: list, *, stdin=None, timeout: float = SHORT_S) -> dict:
        """Run one toolkit command and return its result (the module docstring has the command line)."""
        python, script = toolkit()
        if not Path(script).is_file():
            raise ToolError(f"The blueprint toolkit is not installed yet: {script} is missing "
                            f"({ENV_BP} names another bp.py).")
        if shutil.which(python) is None:
            raise ToolError(f"The blueprint toolkit is not installed yet: its Python, {python}, is missing "
                            f"({ENV_PYTHON} names another one).")
        argv = [python, script, *args, f"--root={ideastore.ideas_root()}", "--json"]
        # never this server's own stdin: that is the JSON-RPC stream
        feed = {"stdin": subprocess.DEVNULL} if stdin is None else {"input": json.dumps(stdin)}
        try:
            p = subprocess.run(argv, capture_output=True, encoding="utf-8", errors="replace", timeout=timeout,
                               cwd=str(Path(script).parent), env={**os.environ, "PYTHONIOENCODING": "utf-8"}, **feed)
        except subprocess.TimeoutExpired:
            raise ToolError(f"The blueprint toolkit did not answer `{args[0]}` within {timeout:g} s and was stopped. "
                            "blueprint_status shows whether a job is still running.") from None
        except OSError as e:
            raise ToolError(f"The blueprint toolkit could not be started: {e}") from None
        return _answer(args[0], p)

    def _lab(self, r: dict) -> list[str]:
        """After a command: the app's own copies of the idea, brought up to date (ideastore.sync). Lines for
        the tool's text; never an error -- a phase is not failed for the Lab's copy of it."""
        name = r.get("name")
        try:
            if not ideastore.exists(name):
                return []
        except ValueError:
            return []                       # not an idea's name (a dry run names a stored table)
        try:
            got = ideastore.sync(name)
        except (ValueError, OSError) as e:
            return [f"Lab: not updated ({e})."]
        out = [f'Lab: {draftstore.draft_id(name)} is now in the group "{got["filed"]}".'] if got["filed"] else []
        said, saved = r.get("status"), got["idea"]["status"]
        if said and said != saved:          # the toolkit's word against what is on file: never passed over in silence
            out.append(f"Lab: the saved results read {_caps(saved)}, not {_caps(said)}.")
        return out + [f"Lab: {n}." for n in got["notes"]]

    def _finish(self, r: dict, keep: str = "blueprint_status(job_id={id}) shows it.") -> str:
        """A result as the tool's text; a job that is still going says how to keep waiting on it."""
        job = r.get("job") if isinstance(r.get("job"), dict) else {}
        if job.get("state") == "error":
            raise ToolError(f"{_head(r)}: job {job.get('id')} failed: "
                            f"{r.get('error') or job.get('progress') or 'no reason given'}")
        notes = self._lab(r)
        if job.get("state") in RUNNING:
            going = " · ".join(str(x) for x in (job.get("state"), job.get("progress")) if x)
            return "\n".join([f"{_head(r)}: job {job.get('id')} is still going ({going}). "
                              + keep.format(id=repr(job.get("id"))), *notes])
        return _report(r, notes)

    # ---- before the card: the blocks

    def t_blueprint_blocks(self) -> str:
        return self._finish(self._bp(["blocks"]))

    def block_code(self) -> dict:
        """Not a tool: the Lab's Toolkit view. The same blocks as `blueprint_blocks`, each with the code that implements it
        (bp.py blockcode): {groups: [{id, title, words, items}], sources: {id: {file, start, end, code}}, counts}."""
        r = self._bp(["blockcode"])
        return {k: r[k] for k in ("groups", "sources", "counts") if k in r}

    # ---- phase 0: the card

    def t_blueprint_card(self, name: str, card: dict, settings: dict) -> str:
        spec = {"name": _name(name), "card": _object(card, "card"), "run": _object(settings, "settings")}
        return self._finish(self._bp(["card", name, "--spec=-"], stdin=spec))

    # ---- phase 1: the code check

    def t_blueprint_code_check(self, name: str, store=None, trades_file=None, run_id=None, looked=False) -> str:
        args = ["code-check", _name(name)]
        sources = (("--store", "store", store), ("--trades", "trades_file", trades_file),
                   ("--run-id", "run_id", run_id))
        given = [(flag, key, v) for flag, key, v in sources if v is not None]
        if len(given) > 1:
            raise ToolError("give one of store, trades_file, run_id")
        args += [f"{flag}={_text(v, key)}" for flag, key, v in given]
        if not isinstance(looked, bool):
            raise ToolError("looked: true or false")
        return self._finish(self._bp(args + ["--looked"] if looked else args))

    # ---- phase 2: the build

    def t_blueprint_build(self, name: str, reason=None, wait_s=None, job_id=None) -> str:
        _name(name)
        wait = _wait_s(wait_s)
        if job_id is not None:
            args = ["job", _job_id(job_id)]
        elif not isinstance(reason, str) or not reason.strip():
            raise ToolError("reason: why this round is run, in a sentence or two -- it is written before the run "
                            "(line 2.9). To keep waiting on a build already started, pass its job_id.")
        else:
            args = ["build", name, f"--reason={reason.strip()}"]
        r = self._bp([*args, f"--wait={wait}"], timeout=wait + self._bp_grace_s)
        return self._finish(r, f"Call blueprint_build(name={name!r}, job_id={{id}}) to keep waiting.")

    # ---- phase 3: the freeze

    def t_blueprint_lock(self, name: str) -> str:
        return self._finish(self._bp(["lock", _name(name)]))

    # ---- phase 4: the one read of the test days

    def t_blueprint_test(self, name: str, confirm, early_look=False, wait_s=None, job_id=None) -> str:
        _name(name)
        if not isinstance(early_look, bool):
            raise ToolError("early_look: true or false")
        if confirm is not True:
            raise ToolError("confirm: must be true. The test days are read ONCE for an idea, and a read cannot be "
                            "taken back: run this only for a locked idea, when the owner has said to"
                            + (" -- or as an early look, after his clear yes in chat." if early_look else "."))
        wait = _wait_s(wait_s)
        args = ["job", _job_id(job_id)] if job_id is not None else ["test", name, "--confirm"]
        if early_look and job_id is None:               # a job that is waited on was started as what it is
            args.append("--early-look")
        r = self._bp([*args, f"--wait={wait}"], timeout=wait + self._bp_grace_s)
        return self._finish(r, f"Call blueprint_test(name={name!r}, confirm=true, job_id={{id}}) to keep waiting: "
                               "nothing is read again.")

    # ---- phase 5: before the eval is bought

    def t_blueprint_sim(self, name: str, account: str, attempts: int, fee_budget: float) -> str:
        _name(name)
        _text(account, "account")
        if type(attempts) is not int or attempts < 1:
            raise ToolError("attempts: how many evals the owner will buy at most, a whole number from 1 (line 5.4: "
                            "his number, never a guess)")
        if isinstance(fee_budget, bool) or not isinstance(fee_budget, (int, float)) or not math.isfinite(fee_budget) \
                or fee_budget < 0:
            raise ToolError("fee_budget: the owner's total fee budget in dollars, 0 or more (line 5.4)")
        return self._finish(self._bp(["sim", name, f"--account={account}", f"--attempts={attempts}",
                                      f"--fee-budget={fee_budget}"]))

    def t_blueprint_portfolio(self, names: list, account: str) -> str:
        if not isinstance(names, list) or len(names) < 2 or len(set(names)) != len(names):
            raise ToolError("names: two or more DIFFERENT ideas, each proven on history (one strategy alone: "
                            "blueprint_sim)")
        for n in names:
            _name(n)
        _text(account, "account")
        return self._finish(self._bp(["portfolio", *names, f"--account={account}"]))

    # ---- phase 6: the eval

    def t_blueprint_eval_card(self, name: str, fills=None, account=None, replay_since_stop=None) -> str:
        args = ["eval-card", _name(name)]
        if account is not None:
            args.append(f"--account={_text(account, 'account')}")
        if fills is None:
            if replay_since_stop is not None:
                raise ToolError("replay_since_stop goes with fills: the eval's live orders, on which the hard alarm stands")
            return self._finish(self._bp(args))
        if not isinstance(fills, list) or not all(isinstance(f, dict) for f in fills):
            raise ToolError("fills: the live trades so far, a list of objects")
        if replay_since_stop is not None and (not isinstance(replay_since_stop, list)
                                              or not all(isinstance(t, dict) for t in replay_since_stop)):
            raise ToolError("replay_since_stop: the tester's replay of the days since the stop, a list of objects")
        body = {"fills": fills, **({} if replay_since_stop is None else {"replay_since_stop": replay_since_stop})}
        return self._finish(self._bp([*args, "--fills=-"], stdin=body))

    # ---- any phase

    def t_blueprint_status(self, name=None, job_id=None) -> str:
        if name is not None and job_id is not None:
            raise ToolError("give either name or job_id (or neither: every idea)")
        if job_id is not None:
            r = self._bp(["job", _job_id(job_id), "--wait=0"], timeout=self._bp_grace_s)
            return self._finish(r, "Call blueprint_status(job_id={id}) to look again.")
        return self._finish(self._bp(["status"] if name is None else ["status", _name(name)]))

    # ---- views of what is saved: they run nothing and count no round

    def t_blueprint_heatmap(self, name: str, place=None, round=None) -> str:  # noqa: A002
        args = ["heatmap", _name(name)]
        if place is not None:
            args.append(f"--place={_place(place)}")
        if round is not None:
            if type(round) is not int or not 1 <= round <= ideastore.MAX_ROUNDS:
                raise ToolError(f"round: a build round that is on file, 1 to {ideastore.MAX_ROUNDS}")
            args.append(f"--round={round}")
        return self._finish(self._bp(args))

    def t_blueprint_mc(self, name: str, on=None) -> str:
        args = ["mc", _name(name)]
        if on is not None:
            if on not in MC_ON:
                raise ToolError(f"on: {' or '.join(MC_ON)}")
            args.append(f"--on={on}")
        return self._finish(self._bp(args))
