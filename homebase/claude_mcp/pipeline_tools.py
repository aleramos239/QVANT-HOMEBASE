"""Pipeline tools: the strategy pipeline (docs/superpowers/specs/2026-10-07-strategy-pipeline-design.md) from a
chat and from the Lab. A `PipelineMixin` (see tools.Toolbox, which inherits it beside BlueprintMixin), in its own
module like the blueprint tools.

The pipeline itself is the research toolkit's (research/edge-library/blueprint/pipe_runner.py): idea cards go in,
its runner takes each one through eight fixed stages by itself and stops it at the first one it fails. Nothing is
judged here and nothing is run here. Each tool is ONE command of the toolkit, started by BlueprintMixin._bp -- the
one way this app has to the toolkit -- and what comes back is the toolkit's own text:

    <python> <bp.py> pipe <sub> [its arguments] --root=<the PIPELINE's folder> --json
      pipe add --spec=- [--inbox]              stdin: the idea card                     pipeline_add
      pipe list | show <name>                                                           pipeline_status
      pipe start | pause | resume                                                       pipeline_control
      pipe approve <name> | refuse <name> --why=TEXT                                    pipeline_decide
      pipe book                                                                         pipeline_book

--root here is the pipeline's OWN folder ($HOMEBASE_PIPELINE_ROOT, else ~/.homebase/pipeline), never the app's
idea folder: the toolkit keeps a pipeline idea's heat maps inside it, so the Lab's list is not flooded.

No tool can skip a stage, change a pass line or touch the desk: a chat adds cards, starts / pauses / resumes the
runner, reads, and passes on the owner's yes or no for an idea that passed every stage.

Three things the Lab's pages read are written ONCE, here: STAGES (the eight stages, a plain sentence each), LABELS
(the word the page shows for a status of the toolkit) and what the two views hold (PipelineMixin.pipeline_state,
.pipeline_idea; the routes are GET /api/tester/pipeline and /api/tester/pipeline/idea/{name}).

FOR THE PAGE ONLY (a chat's tools say what they always said):
  plain(text)                 the toolkit's words without what no page has: its own command line ("(bp.py pipe ...)", a
                              "Next: bp.py ..." line) and the folders of a file path
  page_said(action, r)        ONE plain sentence for an action that worked ("fvg_open is in the Queue, place 1 of 3.")
  page_refusal(error)         a refusal's reason in the toolkit's own words, made plain()
  PipelineMixin.pipeline_do   one action of the page: the same checks and the same ONE command as the tool a chat has
  PipelineMixin.pipeline_parts  what the add-idea form is built from, off ONE `bp.py blocks` kept for the life of the process:
                              {rules: [{name, words, markets, sessions, bars, settings: [{name, kind, min, max, choices,
                              default, tried}]}], indicators: [{block, sides: [{side, words}], markets}], sessions: [{name, words}]}
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from .blueprint_tools import PIPE, SHORT_S, _spec
from .client import ToolError

ENV_ROOT = "HOMEBASE_PIPELINE_ROOT"
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{1,33}$")        # a pipeline card's name, as the toolkit takes it (pipe_store.NAME)
ACTIONS = ("start", "pause", "resume")                 # pipeline_control
DECISIONS = ("approve", "refuse")                      # pipeline_decide
LOOK_S = 20.0                                          # the longest a page's look waits for the toolkit: it reads a few small files
# The eight stages, for the Lab's Guide and for an idea's page: the toolkit's own numbers (pipe_runner.NAMES), a
# plain sentence each. Written here once; the page reads them from the route and types none. Since 2026-10-08 (variant
# mode, pipeline.json "mode": "variant") the map gets a loose check at stage 1 and the pick is made there: stages 3 and 4
# judge the picked variant, not the whole map. The names are the toolkit's and stay (they are on every card on file).
STAGES = [
    {"n": 0, "name": "Idea card", "words": "Is the card complete, and does it use only parts that exist?"},
    {"n": 1, "name": "Raw heat map", "words": "Does a region of the map make money (enough boxes at the floor)?"},
    {"n": 2, "name": "Machine check", "words": "Does every trade do exactly what the rule says?"},
    {"n": 3, "name": "Indicators", "words": "Does the picked variant make money on its side(s), even without its best trades?"},
    {"n": 4, "name": "Proof", "words": "Does the picked variant hold up against luck?"},
    {"n": 5, "name": "Pick one box and lock", "words": "Does the picked stop and target hold up on its own, so the rule can be frozen?"},
    {"n": 6, "name": "Unseen days", "words": "Does it still make money on days it has never seen, read one time only?"},
    {"n": 7, "name": "The owner's look", "words": "You read its card and approve it for the Book, or refuse it."},
]
# A status of the toolkit (pipe_store.STATUS, in its order) -> the word the page shows.
LABELS = {"queued": "Waiting", "running": "Running", "stopped": "Stopped", "code_problem": "Problem",
          "awaiting_owner": "Passed", "book": "In the book", "refused": "Refused"}


def pipeline_root() -> Path:
    """The pipeline's own folder, where the toolkit looks for it too (pipe_store.root) -- whether or not it is there."""
    v = os.environ.get(ENV_ROOT)
    return Path(v).expanduser() if v else Path.home() / ".homebase" / "pipeline"


# ---------------------------------------------------------------- the page's words

_HINT = re.compile(r"[ \t]*\(`?bp\.py[^)]*\)")                         # "(bp.py pipe refuse x --why=TEXT)", "(`bp.py blocks` lists them)"
_NEXT = re.compile(r"(?m)^(?:Next: .*|Nothing was run\.)\n?")            # the connector's own two lines after a refusal
_HEAD = re.compile(r"^Refused \([^)]*\): ")                              # ... and its head
_LONE_PATH = re.compile(r"[ \t]*\((?:~?/)[^\s()]*\)")                   # "(/Users/x/.homebase/pipeline/book/x.json)"
_PATH = re.compile(r"(?<![\w.])~?/(?:[^\s/()'\"]+/)+([^\s/()'\",;:]+)")  # a path anywhere else: its last name stays
_LOOSE = re.compile(r"[ \t]*`?bp\.py\b[^.;:\n]*`?")                      # a command line outside brackets
_PLACE = re.compile(r"place (\d+) of (\d+)")


def plain(text) -> str:
    """The toolkit's words as a page shows them: no command line of its own and no folders (module docstring).
    Nothing else is touched: a number, a line's name and a bracket that names no command stay as they are."""
    t = _HINT.sub("", str(text or ""))
    t = _LONE_PATH.sub("", t)
    t = _PATH.sub(lambda m: m.group(1), t)
    return _LOOSE.sub("", t).strip()


def page_refusal(error) -> str:
    """A refusal for the page: the reason in the toolkit's own words (they say what is wrong with a card), plain()."""
    return plain(_NEXT.sub("", _HEAD.sub("", str(error or "")))) or "It was refused."


def page_said(action: str, r: dict) -> str:
    """ONE plain sentence for an action of the page that worked, from the toolkit's result (never its text as it is)."""
    name, state = r.get("name"), r.get("state") if isinstance(r.get("state"), dict) else {}
    if action == "add":
        m = _PLACE.search(str(r.get("text") or ""))
        return f"{name} is in the Queue" + (f", place {m.group(1)} of {m.group(2)}." if m else ".")
    if action == "start":
        return ("Testing is already on." if r.get("already") else "Testing has started.") + (" It is paused: press Resume." if r.get("paused") else "")
    if action == "pause":
        return "Paused. It stops after the stage it is on."
    if action == "resume":
        return "Testing carries on." if r.get("running") else "It is not paused any more."
    if action == "approve":
        return f"{name} is in the Book."
    return f"{name} is refused: {plain(state.get('why'))}"


# ---------------------------------------------------------------- what the add-idea form is built from (`bp.py blocks`)

_RANGE = re.compile(r"^a (whole )?number (-?\d+(?:\.\d+)?) \.\. (-?\d+(?:\.\d+)?)$")


def _num(text: str):
    v = float(text)
    return int(v) if v.is_integer() else v


def _setting(s: dict, tried: list) -> dict:
    """One setting of an entry rule for the form. The toolkit says its values in words (blocklist._values): "a number
    0 .. 10", "a whole number 2 .. 200", "touch | mid | go", "true | false" -- read back here into a kind and its limits.
    Words this does not know: kind "text" (the form then takes what is typed)."""
    words, out = str(s.get("values") or "").strip(), {"name": s.get("name"), "kind": "text", "min": None, "max": None, "choices": [],
                                                      "default": s.get("default"), "tried": tried}
    m = _RANGE.match(words)
    if m:
        out.update(kind="whole" if m.group(1) else "number", min=_num(m.group(2)), max=_num(m.group(3)))
    elif words == "true | false":
        out.update(kind="bool")
    elif words:
        out.update(kind="choice", choices=[c.strip() for c in words.split(" | ") if c.strip()])
    return out


def parts(blocks) -> dict:
    """The toolkit's block list (`bp.py blocks --json`, its "blocks") -> what the form needs of it, and nothing else."""
    b = blocks if isinstance(blocks, dict) else {}
    rules, by = [], {}
    for f in b.get("families") or []:
        if not isinstance(f, dict) or f.get("runs") is False:
            continue
        ran = [t for t in f.get("tried") or [] if isinstance(t, dict)]
        rules.append({"name": f.get("name"), "words": str(f.get("does") or ""), "markets": list(f.get("markets") or []),
                      "sessions": list(f.get("sessions") or []), "bars": [str(x) for x in f.get("bars") or []],
                      "settings": [_setting(s, list(dict.fromkeys(t[s["name"]] for t in ran if s.get("name") in t)))
                                   for s in f.get("settings") or [] if isinstance(s, dict) and s.get("name")]})
    for x in b.get("filters") or []:
        if isinstance(x, dict) and x.get("runs") is not False and x.get("block") and x.get("side"):
            one = by.setdefault(x["block"], {"block": x["block"], "sides": [], "markets": list(x.get("markets") or [])})
            one["sides"].append({"side": x["side"], "words": str(x.get("words") or "")})
    return {"rules": rules, "indicators": list(by.values()),
            "sessions": [{"name": x.get("name"), "words": str(x.get("words") or "")} for x in b.get("sessions") or [] if isinstance(x, dict) and x.get("name")]}


def label(status) -> str:
    """The page's word for a status; one the app does not know yet is shown as the toolkit wrote it."""
    return LABELS.get(status) or str(status)


def rows(ideas) -> list[dict]:
    """The toolkit's state rows as they are, each with its `label`."""
    return [{**s, "label": label(s.get("status"))} for s in ideas or [] if isinstance(s, dict)]


def counts(ideas) -> dict:
    """How many ideas the page shows under each label: every label of LABELS, in its order, 0 too."""
    out = dict.fromkeys(LABELS.values(), 0)
    for s in rows(ideas):
        out[s["label"]] = out.get(s["label"], 0) + 1
    return out


# ---------------------------------------------------------------- schemas

_NAME = {"type": "string", "description": "The idea's name, as it was added (pipeline_status lists them)."}
_WAY = {
    "type": "object", "description": "One way to enter: an entry rule and the ONE setting of it that is varied.",
    "properties": {
        "family": {"type": "string", "description": "The entry rule: a family that blueprint_blocks lists as running "
                                                    "on the build days, on the card's market, in its session."},
        "main_setting": {"type": "string", "description": "The ONE setting of that family whose values are tried."},
        "values": {"type": "array", "minItems": 3, "maxItems": 3,
                   "description": "EXACTLY 3 values of the main setting, each once, e.g. [\"0.1\", \"0.25\", \"0.5\"]."},
        "fixed": {"type": "object", "additionalProperties": True,
                  "description": "The family's other settings held at one value, e.g. {\"mode\": \"touch\"}. Left out: "
                                 "the family's own defaults."},
        "limits": {"type": "object", "additionalProperties": True,
                   "description": "Optional: max_tr (entries per session), dir."}},
    "required": ["family", "main_setting", "values"], "additionalProperties": False}
_INDICATOR = {
    "type": "object", "description": "One indicator to try: it is tried ALONE, never together with another.",
    "properties": {
        "block": {"type": "string", "description": "A filter block that blueprint_blocks lists."},
        "side": {"type": "string", "description": "One of that block's sides, e.g. with."},
        "why": {"type": "string", "description": "Why it should help, in a sentence."}},
    "required": ["block", "side", "why"], "additionalProperties": False}
_CARD = {
    "type": "object", "description": "The idea card: everything the pipeline will try for ONE idea.",
    "properties": {
        "name": {"type": "string", "description": "A short name: a-z, 0-9 and '_' (2-34 characters, a letter first), "
                                                  "e.g. fvg_open."},
        "why": {"type": "string", "description": "Why it should make money: ONE sentence."},
        "loser": {"type": "string", "description": "Who is on the losing side: ONE sentence. With why, 8 words or more."},
        "source": {"type": "string", "enum": ["owner", "video", "claude", "wiki", "paper", "book", "course"],
                   "description": "Where the idea came from. claude = you thought of it."},
        "market": {"type": "string", "enum": ["NQ", "ES", "GC"], "description": "ONE market."},
        "session": {"type": "string", "enum": ["asia", "london", "pre", "nyam", "mid", "pm"],
                    "description": "ONE time of day: asia, london, pre (pre-market), nyam (New York morning), mid "
                                   "(midday) or pm (afternoon)."},
        "sides": {"type": "string", "enum": ["both", "long", "short"], "description": "Both sides, or one."},
        "sides_why": {"type": "string", "description": "Why one side only. Needed when sides is long or short."},
        "ways": {"type": "array", "minItems": 1, "maxItems": 3, "items": _WAY,
                 "description": "1 to 3 ways to enter. Each is run on 1-minute and on 5-minute bars."},
        "indicators": {"type": "array", "maxItems": 5, "items": _INDICATOR,
                       "description": "0 to 5 indicators, in the order they are tried; no block twice. They are tried "
                                      "only when the plain idea passes the lower bar and misses the full one."},
        "ref": {"type": "string", "description": "Optional: WHICH paper, book, video or course (one line, 300 characters "
                                                 "at most), e.g. 'Zarattini & Aziz 2023 (SSRN 4416622)'."}},
    "required": ["name", "why", "loser", "source", "market", "session", "sides", "ways"],
    "additionalProperties": False}

SPECS = [
    _spec("pipeline_add", "Pipeline, add an idea: put ONE idea card in the queue of the strategy pipeline -- the "
          "program that takes an idea through eight fixed stages by itself (the card, the raw heat map, the machine "
          "check, the indicators, the proof, one box locked, the unseen days, the owner's look) and stops it at the "
          "first stage it fails, with the reason. Call blueprint_blocks first: it lists the entry rules (families) "
          "with their settings and the indicators (filters) that exist, and a card uses only those. THE CARD: name; "
          "why (one sentence: why it should make money) and loser (one sentence: who is on the losing side); source "
          "(owner, video, claude, wiki, paper, book or course) and, optionally, ref (which paper, book, video or course, "
          "one line); ONE market (NQ, ES or GC); ONE session (asia, london, pre, nyam, mid or "
          "pm); sides (both, or long / short with sides_why); ways: 1 to 3 ways to enter, each a family, ONE main "
          "setting of it and EXACTLY 3 values (its other settings go under fixed); indicators: 0 to 5, each a filter "
          "block, one of its sides and the reason it should help. The bars are always 1 and 5 minutes and the stops "
          "and targets are the standard table: a card does not choose them. The same idea (the same market, session, "
          "sides and ways) cannot be added twice, not under another name either. Nothing is chosen after the run "
          "starts: every choice is on the card. A card with a line missing is refused with the lines that fail, and "
          "nothing is saved. The runner tests it when it is started (pipeline_control).",
          {"card": _CARD,
           "inbox": {"type": "boolean", "description": "true = the owner's own idea: it goes before the cards that are "
                                                       "waiting. Default false."}}, ["card"]),
    _spec("pipeline_status", "Pipeline, where things stand: the queue -- one row an idea (its status, the stage it "
          "reached, how many heat maps were tried, and the line that stopped it), the count by status, and whether "
          "the runner is working or paused. With name: that ONE idea in full -- its card, and every stage it went "
          "through with pass or fail and its numbers. The statuses: queued (waiting), running, stopped (it failed a "
          "stage: a verdict on the idea), code_problem (the code was wrong, not the idea: it waits for a repair), "
          "awaiting_owner (it passed every stage and waits for the owner's yes or no), book, refused. Runs nothing.",
          {"name": {**_NAME, "description": _NAME["description"] + " Left out: the whole queue."}}),
    _spec("pipeline_control", "Pipeline, the runner: start, pause or resume the program that works through the queue "
          "by itself. start = it starts as its own process: it goes on after this chat ends, and after any stop it "
          "carries on where it was (a second start changes nothing). pause = it stops after the stage in hand; "
          "nothing is lost. resume = it carries on. No stage can be skipped and no pass line can be changed from here.",
          {"action": {"type": "string", "enum": list(ACTIONS), "description": "start, pause or resume."}}, ["action"]),
    _spec("pipeline_decide", "Pipeline, the owner's yes or no: approve or refuse ONE idea that passed every stage and "
          "is awaiting the owner. USE IT ONLY ON THE OWNER'S WORD: show him the idea first (pipeline_status with its "
          "name), and call this only after he has said yes or no in chat -- never on your own judgment. approve = its "
          "card goes in the book, as proven on history (nothing in the book is edited afterwards). refuse = it is kept "
          "as refused, with his reason. Refused for an idea in any other status.",
          {"name": _NAME,
           "decision": {"type": "string", "enum": list(DECISIONS), "description": "approve or refuse: the owner's word."},
           "why": {"type": "string", "description": "The owner's reason, in his words: needed to refuse (it is kept "
                                                    "with the idea). Not read for approve."}},
          ["name", "decision"]),
    _spec("pipeline_book", "Pipeline, the book: the strategies that passed every stage and that the owner approved, "
          "one row each -- its name, its label (stands alone, or helper), its entry rule, market, session and bar "
          "size. Runs nothing."),
]


# ---------------------------------------------------------------- arguments, and the toolkit's answer as text

def _name(name) -> str:
    """An idea's name as the toolkit takes it: also what keeps an option out of the command line."""
    if not isinstance(name, str) or not NAME_RE.fullmatch(name):
        raise ToolError("name: an idea's name -- a-z, 0-9 and '_' (2-34 characters, a letter first); pipeline_status "
                        "lists the ideas")
    return name


def _card_ok(card, inbox) -> None:
    """pipeline_add's inputs, as far as the connector reads them (the toolkit checks the card itself)."""
    if not isinstance(card, dict):
        raise ToolError("card: an object -- the idea card (name, why, loser, source, market, session, sides, ways, "
                        "indicators)")
    if not isinstance(inbox, bool):
        raise ToolError("inbox: true or false")


def _action_ok(action) -> str:
    if action not in ACTIONS:
        raise ToolError(f"action: {', '.join(ACTIONS[:-1])} or {ACTIONS[-1]}")
    return action


def _decided(name, decision, why) -> list:
    """pipeline_decide's inputs -> what follows the command's word: the name, and for a refusal the owner's reason."""
    _name(name)
    if decision not in DECISIONS:
        raise ToolError(f"decision: {' or '.join(DECISIONS)} -- the owner's word, never a guess")
    if decision == "approve":
        return [name]
    if not isinstance(why, str) or not why.strip():
        raise ToolError("why: the owner's reason for refusing it, in his words -- it is kept with the idea")
    return [name, f"--why={' '.join(why.split())}"]


def _plain_row(s: dict) -> dict:
    """An idea's row for the page: the line that stopped it without the toolkit's command line."""
    return {**s, "why": plain(s["why"])} if isinstance(s.get("why"), str) and s["why"] else s


def _plain_book(card) -> dict:
    """A book card for the page: its stages' first lines made plain(); everything else as the toolkit keeps it."""
    if not isinstance(card, dict) or not isinstance(card.get("stages"), dict):
        return card
    return {**card, "stages": {n: ({**c, "text": plain(c.get("text"))} if isinstance(c, dict) else c) for n, c in card["stages"].items()}}


def _said(r: dict, more=()) -> str:
    """A result as the tool's text: what it is of, then the toolkit's own words (never its JSON). The toolkit's
    `next` is left out: it names its own command line, which no chat and no page has."""
    head = [f"Pipeline {str(r.get('command') or '?').removeprefix(PIPE + ' ')}", r.get("name"), LABELS.get(r.get("status"))]
    text = (r.get("text") or "").strip()
    return "\n".join([" · ".join(str(x) for x in head if x), *([text] if text else []), *more])


def _full(r: dict) -> list[str]:
    """One idea in full, after the toolkit's own words (which give a stage's first line only): what its card tries,
    then the lines of every stage it went through, each with its number."""
    card, stages, out = r.get("card") or {}, r.get("stages") or {}, []
    for i, w in enumerate(x for x in card.get("ways") or [] if isinstance(x, dict)):
        fixed = ", ".join(f"{k} {v}" for k, v in (w.get("fixed") or {}).items())
        out.append(f"way {chr(97 + i)}: {w.get('family')}, {w.get('main_setting')} "
                   f"{' / '.join(str(v) for v in w.get('values') or [])}" + (f" ({fixed})" if fixed else ""))
    for i, x in enumerate((x for x in card.get("indicators") or [] if isinstance(x, dict)), 1):
        out.append(f"indicator {i}: {x.get('block')} {x.get('side')} -- {x.get('why')}")
    for n in sorted(stages, key=_stage_no):
        c = stages[n] if isinstance(stages[n], dict) else {}
        said = [str(x["text"]) for x in c.get("lines") or [] if isinstance(x, dict) and x.get("text")]
        if said:
            out += [f"stage {n}, its lines:", *(f"  {t}" for t in said)]
    return out


def _stage_no(n) -> int:
    return int(n) if str(n).isdigit() else 99


class PipelineMixin:
    """Mixed into tools.Toolbox beside BlueprintMixin, whose `_bp` starts every command: no second way to the toolkit."""

    _pipe_look_s: float = LOOK_S

    def _pipe(self, sub: str, *more: str, stdin=None, timeout: float = SHORT_S) -> dict:
        """One command of the pipeline, in the pipeline's own folder -> the toolkit's result."""
        return self._bp([PIPE, sub, *more], stdin=stdin, timeout=timeout, root=pipeline_root())

    # ---- not tools: what the Lab's pages read (a page asks every few seconds: a look never waits a tool's 300 s)

    def pipeline_state(self) -> dict:
        """Not a tool: the Lab's Queue, Book and Guide in one answer (`pipe list` and `pipe book`, two commands)."""
        got, book = self._pipe("list", timeout=self._pipe_look_s), self._pipe("book", timeout=self._pipe_look_s)
        return {"runner": {"running": bool(got.get("running")), "paused": bool(got.get("paused"))},
                "counts": counts(got.get("ideas")), "ideas": [_plain_row(s) for s in rows(got.get("ideas"))],
                "book": [_plain_book(c) for c in book.get("book") or []], "stages": STAGES}

    def pipeline_idea(self, name) -> dict:
        """Not a tool: one idea for its page (`pipe show`): its card as it was added, its state with the page's label,
        and every stage it went through -- under the stage's name of STAGES, with its lines' own words."""
        r = self._pipe("show", _name(name), timeout=self._pipe_look_s)
        names, stages = {s["n"]: s["name"] for s in STAGES}, r.get("stages") or {}
        out = []
        for n in sorted(stages, key=_stage_no):
            c = stages[n] if isinstance(stages[n], dict) else {}
            out.append({"n": _stage_no(n), "name": names.get(_stage_no(n)) or str(c.get("name") or ""), "passed": c.get("passed"),
                        "result": c.get("result"), "text": plain(c.get("text")),
                        "lines": [{"line": x.get("line"), "passed": x.get("passed"), "text": plain(x.get("text"))}
                                  for x in c.get("lines") or [] if isinstance(x, dict)]})
        return {"card": {k: v for k, v in (r.get("card") or {}).items() if k != "subs"},      # (the toolkit's own heat-map specs stay there)
                "state": _plain_row(rows([r.get("state") or {}])[0]), "stages": out}

    def pipeline_parts(self) -> dict:
        """Not a tool: what the add-idea form is built from (parts() of ONE `bp.py blocks`). The block list changes only
        when the code does, so the first good answer is kept for the life of the process (a restart reads it again); an
        answer without a block list is not kept."""
        kept = getattr(self, "_pipe_parts", None)
        if kept is None:
            r = self._bp(["blocks"], timeout=self._pipe_look_s, root=pipeline_root())
            kept = parts(r.get("blocks"))
            if isinstance(r.get("blocks"), dict):
                self._pipe_parts = kept
        return kept

    def pipeline_do(self, action: str, card=None, inbox=False, name=None, why=None) -> str:
        """Not a tool: ONE action of the Lab's page -- the same checks and the same ONE command as the tool a chat has
        (t_pipeline_add / _control / _decide), answered in one plain sentence (page_said) instead of the tool's text."""
        if action == "add":
            _card_ok(card, inbox)
            r = self._pipe("add", "--spec=-", *(["--inbox"] if inbox else []), stdin=card)
        elif action in DECISIONS:
            r = self._pipe(action, *_decided(name, action, why))
        else:
            r = self._pipe(_action_ok(action))
        return page_said(action, r)

    # ---- the tools

    def t_pipeline_add(self, card: dict, inbox=False) -> str:
        _card_ok(card, inbox)
        return _said(self._pipe("add", "--spec=-", *(["--inbox"] if inbox else []), stdin=card))

    def t_pipeline_status(self, name=None) -> str:
        if name is None:
            return _said(self._pipe("list"))
        r = self._pipe("show", _name(name))
        return _said(r, _full(r))

    def t_pipeline_control(self, action: str) -> str:
        return _said(self._pipe(_action_ok(action)))

    def t_pipeline_decide(self, name: str, decision: str, why=None) -> str:
        return _said(self._pipe(decision, *_decided(name, decision, why)))

    def t_pipeline_book(self) -> str:
        return _said(self._pipe("book"))
