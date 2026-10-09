"""pipe_runner.py -- THE PIPELINE'S RUNNER AND ITS COMMANDS (pipeline plan A, task 8; the design's section 5). It works
through the queue of pipe_store.py by itself: the first idea of the queue, its next stage, the stage's card on disk, the
idea's new state -- until the idea stops, waits for the owner, or the queue is empty. It judges nothing: a stage
(pipe_stages.stage0 .. stage7) says pass or fail, and this module only writes down what the stage said and moves on.
THE STAGES ARE LOADED WHEN ONE IS ASKED FOR (stage_fn), never with this module: a test puts its own in stage_fn's place.

  stage_fn(n)                        the function of stage n: `stage<n>(name, ctx, progress=None) -> the stage card`
  step(name, ctx, progress=None)     ONE stage of ONE idea -> its state. The next stage = 0 for an idea that has finished
                                     none, else the last finished + 1. The state says "running" BEFORE the stage is called:
                                     a runner killed in a stage leaves "running" with the last FINISHED stage, and the next
                                     step runs the same stage again from its start (the toolkit skips what is on disk).
                                       the card says passed False  -> "stopped" ("code_problem" when the card says so),
                                                                      stopped_at = the stage, why = its first failed row
                                       stage 7 came back           -> "awaiting_owner" (the owner decides: approve / refuse)
                                       anything else               -> still "running": the caller steps again
                                       the stage RAISED a refusal  -> "stopped", why = the refusal; the card says refused
                                         ... of the no-compute window -> NOTHING changes and nothing is written: the state
                                                                      as it was, with "wait_until" (the window's end, ISO)
                                       the stage raised anything else -> "code_problem", why = "<Type>: <message>", the
                                                                      card keeps the traceback's last 20 lines ("trace")
                                     Refused (judge.Refuse): an idea that is not queued or running. A stage that cannot
                                     even be LOADED is the runner's fault, not the idea's: the error goes up, no state moves.
  loop(ctx, once=False, sleep=time.sleep, idle_s=60) -> 0
                                     THE RUNNER. One a pipeline root (runner.lock, held for as long as it works: a second
                                     one says "a runner is already working" and ends). It takes the queue's first idea and
                                     steps it until it stops; between two stages it looks at the pause file (a pause ends
                                     the work AFTER the stage in hand: the idea stays "running" and is first again on
                                     resume). The no-compute window is slept out, in slices of idle_s. Nothing to do: it
                                     sleeps idle_s and looks again. once=True: everything that can run now, then back (it
                                     never sleeps: a pause, a wait or an empty queue ends it). One idea's failure never ends
                                     the loop. A line a finished stage on runner.log:
                                         UTC <tab> name <tab> stage <tab> PASS | FAIL | STOP | CODE | WAIT <tab> seconds <tab> text
  start(root=None) -> {"pid", "already"}
                                     the runner as a DETACHED process (`bp.py pipe _loop --root=...`, its own session, its
                                     words to runner.out, its pid in runner.pid) -- or already: True when one is working
  status(root=None) -> {"running", "pid", "paused", "counts": {status: n}, "ideas": [states]}
                                     the ideas: what can run first, in the queue's order, then the rest, the latest change first
  approve(name, root=None) -> state  only from "awaiting_owner": the "book" of the idea's stage-7 card goes to the book
                                     (pipe_store.write_book), the status becomes "book"
  refuse(name, why, root=None) -> state
                                     only from "awaiting_owner", and only with a reason: "refused", why = the reason
  add(card, root=None, inbox=False) -> result
                                     `pipe add`: stage 0's check first (pipe_card.check). A card with a line missing is
                                     refused WITH its rows and nothing is saved; a whole one is filed and queued
  rerun(name, root=None) -> result   `pipe rerun`: an idea that stopped (or was refused) starts again from stage 0 -- its stage cards are moved to
                                     stages_old/<UTC stamp>/ (never deleted), its state is queued and empty, its name goes last in the queue
                                     (pipe_store.reset). Refused while it is running, awaits the owner or is in the book. The stores, the card
                                     and the ledger are not touched
  listing / show / booked / command  `pipe list`, `pipe show`, `pipe book` and every `bp.py pipe <sub>` as ONE result object
                                     (api.result("pipe <sub>", ...)) with a text for a person

ctx = {"root": the pipeline root | None (HOMEBASE_PIPELINE_ROOT, ~/.homebase/pipeline), "tiny": None | a test run's days}:
handed to every stage as it is.
THE NO-COMPUTE WINDOW (_window): a judge.Refuse that comes while the engine's own window is open (l2sim.compute_window_end
at the runner's clock, as runner.may_start reads it) -- or that says may_start's own words (WINDOW_WORDS: the window closed
between the refusal and the look: step again in a minute) -- is a wait, never a stop.
Files of its own under the pipeline root: runner.lock, runner.log, runner.out, runner.pid. Locked by tests/test_pipe_runner.py.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import fcntl
import importlib
import os
import subprocess
import sys
import time
import traceback
from collections import Counter
from pathlib import Path

import judge as J
import l2sim as S

from . import W
from . import api
from . import pipe_card as PC
from . import pipe_store as PS
from . import runner as RUN

LAST = 7                                            # the owner's look: the last stage the runner runs
NAMES = ("idea card", "raw heat map", "machine check", "indicators", "proof", "pick one box and lock", "unseen days", "the owner's look")
LOCK, LOG, OUT, PID = "runner.lock", "runner.log", "runner.out", "runner.pid"
WINDOW_WORDS = "nothing heavy starts"               # runner.may_start's refusal (tests/test_pipe_runner.py holds the two together)
MARK = {True: "PASS", False: "FAIL", None: "n/a"}   # a stage card's verdict, as lines._row prints a line's
WHY = 80                                            # characters of a state's why on a row of `pipe list`
AGAIN = dt.timedelta(minutes=1)                     # the window closed between a stage's refusal and the look: step again in a minute
TRIES, GAP = 3, 0.1                                 # the runner's tries for its lock: `pipe list` holds it for an instant to see whether one works
SUBS = ("add", "list", "show", "start", "pause", "resume", "approve", "refuse", "book", "rerun")


def stage_fn(n: int):
    """The function of stage n (pipe_stages.stage<n>), loaded when it is asked for."""
    return getattr(importlib.import_module(f"{__package__}.pipe_stages"), f"stage{int(n)}")


def _utc() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def _first(text) -> str:
    return (str(text or "").strip().splitlines() or [""])[0]


def _say(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)         # the detached runner's stderr is runner.out


# ---------------------------------------------------------------- one stage of one idea

def _window(e):
    """Is `e` the refusal to start inside the no-compute window? -> when to look again (the window's end, ET), or None."""
    if not isinstance(e, J.Refuse):
        return None
    now = RUN.clock().astimezone(S.ET)
    return S.compute_window_end(now) or (now + AGAIN if WINDOW_WORDS in str(e) else None)


def _blank(n: int, was: dict, t0: float, text: str, **more) -> dict:
    """The stage card of a stage that gave none (it was refused, or it crashed): failed, with why as its text."""
    return {"stage": n, "name": NAMES[n], "passed": False, "result": None, "lines": [], "text": text, "picked": was.get("picked"), "tries": was.get("tries"),
            "rules": {}, "utc": _utc(), "seconds": round(time.monotonic() - t0, 1), **more}


def _step(name, ctx: dict, progress=None) -> tuple:
    """step(), and what the runner's log says of it: -> (the state, {"stage", "word", "seconds", "text"})."""
    root = ctx.get("root")
    was = PS.state(name, root)
    if was.get("status") not in PS.LIVE:
        raise J.Refuse(f"{name} is {was.get('status')}: the runner works on an idea that is queued or running, and on no other")
    n = 0 if was.get("stage") is None else int(was["stage"]) + 1
    if n > LAST:
        raise J.Refuse(f"{name} has finished stage {LAST} and is still {was['status']}: there is no stage {n} (its state file was changed by hand)")
    fn = stage_fn(n)                                # a stage that cannot be loaded: the error goes up before any state moves
    PS.set_state(name, root, status="running")
    t0, word = time.monotonic(), "PASS"
    try:
        card = fn(name, ctx, progress)
        if not isinstance(card, dict):
            raise TypeError(f"stage {n} returned {type(card).__name__}, not a stage card")
        PS.write_stage(name, n, card, root)         # (a card that cannot be saved is a code problem too)
        change = {"stage": n, **{k: card[k] for k in ("tries", "picked") if card.get(k) is not None}}
        if card.get("passed") is False:
            bad = next((r["text"] for r in card.get("lines") or [] if isinstance(r, dict) and r.get("passed") is False and r.get("text")), None)
            word = "CODE" if card.get("code_problem") else "FAIL"
            change.update(status="code_problem" if card.get("code_problem") else "stopped", stopped_at=n, why=bad or _first(card.get("text")))
        elif n == LAST:
            change["status"] = "awaiting_owner"
    except api.REFUSALS as e:
        end = _window(e)
        if end is not None:                         # a wait, not a verdict: the state as it was, no card
            st = PS.set_state(name, root, status=was["status"])
            return {**st, "wait_until": end.isoformat()}, {"stage": n, "word": "WAIT", "seconds": 0.0, "text": _first(e)}
        card, word = _blank(n, was, t0, str(e), refused=True), "STOP"
        PS.write_stage(name, n, card, root)
        change = {"status": "stopped", "stopped_at": n, "why": str(e)}
    except Exception as e:  # noqa: BLE001 - whatever it was, the idea must end and say so
        why = f"{type(e).__name__}: {e}"[:300]
        card, word = _blank(n, was, t0, why, code_problem=True, trace=traceback.format_exc().splitlines()[-20:]), "CODE"
        PS.write_stage(name, n, card, root)
        change = {"status": "code_problem", "stopped_at": n, "why": why}
    secs = card.get("seconds")
    return PS.set_state(name, root, **change), {"stage": n, "word": word, "seconds": time.monotonic() - t0 if secs is None else secs, "text": _first(card.get("text"))}


def step(name, ctx: dict, progress=None) -> dict:
    """ONE stage of ONE idea -> its state (module docstring): the stage's card is on disk before the state says so."""
    return _step(name, ctx, progress)[0]


# ---------------------------------------------------------------- the runner

@contextlib.contextmanager
def _lock(root: Path, tries: int = 1):
    """runner.lock of a pipeline root -> True while this process holds it (it is the runner), False when another does."""
    root.mkdir(parents=True, exist_ok=True)
    with open(root / LOCK, "a") as fh:
        for i in range(tries):
            try:
                fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError:
                if i + 1 < tries:
                    time.sleep(GAP)
                continue
            yield True
            return
        yield False


def _working(root: Path) -> bool:
    """Is a runner working on this root? (Its lock is held: the lock is taken here for an instant, and let go.)"""
    if not (root / LOCK).exists():                  # (a look makes no folder)
        return False
    with _lock(root) as mine:
        return not mine


def _pid(root: Path):
    try:
        return int((root / PID).read_text().strip())
    except (OSError, ValueError):
        return None


def _log(root: Path, name, stage, word: str, seconds, text: str) -> None:
    with contextlib.suppress(OSError, TypeError, ValueError):     # a log line that cannot be written stops no idea
        with open(root / LOG, "a", encoding="utf-8") as f:
            f.write("\t".join((_utc(), str(name), str(stage), word, f"{float(seconds):.0f}s", _first(text))) + "\n")


def _work(name, ctx: dict, root: Path, skip: set):
    """One idea, stage after stage, until it stops, waits or the queue is paused -> the time it waits for, or None."""
    while True:
        try:
            st, did = _step(name, ctx, lambda msg: _say(f"{name}: {msg}"))
        except Exception as e:  # noqa: BLE001 - one idea's failure never ends the loop
            _log(root, name, "-", "CODE", 0, f"the runner could not work on it and left it as it was: {type(e).__name__}: {e}")
            skip.add(name)
            return None
        _log(root, name, **did)
        if "wait_until" in st:
            return st["wait_until"]
        if st["status"] not in PS.LIVE or PS.paused(root):
            return None


def _until(iso: str, sleep, idle_s: float) -> None:
    """Sleep to a time of the runner's clock, in slices of idle_s at most."""
    end = dt.datetime.fromisoformat(iso)
    while True:
        left = (end - RUN.clock()).total_seconds()
        if left <= 0:
            return
        sleep(min(idle_s, left))


def loop(ctx: dict, once: bool = False, sleep=time.sleep, idle_s: float = 60) -> int:
    """THE RUNNER (module docstring) -> 0. `ctx` is handed to every stage; once=True never sleeps."""
    root = PS.root(ctx.get("root"))
    with _lock(root, TRIES) as mine:
        if not mine:
            _say(f"a runner is already working on {root}" + (f" (pid {_pid(root)})" if _pid(root) else "") + ": this one ends")
            return 0
        (root / PID).write_text(str(os.getpid()))
        skip: set = set()                           # the ideas the runner could not even step: left alone until the queue is idle
        while True:
            name = None if PS.paused(root) else next((x for x in PS.order(root) if x not in skip), None)
            if name is None:
                if once:
                    return 0
                skip.clear()
                sleep(idle_s)
                continue
            wait = _work(name, ctx, root, skip)
            if wait:
                if once:
                    return 0
                _until(wait, sleep, idle_s)


def start(root=None) -> dict:
    """The runner as a detached process (jobs.start's way) -> {"pid", "already"}; already = one is working, nothing started."""
    r = PS.root(root)
    if _working(r):
        return {"pid": _pid(r), "already": True}
    r.mkdir(parents=True, exist_ok=True)
    with open(r / OUT, "ab") as out:
        p = subprocess.Popen([sys.executable, str(W / "bp.py"), "pipe", "_loop", f"--root={r}"], stdin=subprocess.DEVNULL, stdout=out, stderr=out,
                             start_new_session=True, cwd=str(W))
    (r / PID).write_text(str(p.pid))
    return {"pid": p.pid, "already": False}


def status(root=None) -> dict:
    """Where everything stands (module docstring). Runs nothing."""
    r = PS.root(root)
    live, by = PS.order(r), {s["name"]: s for s in PS.ideas(r)}
    rest = sorted((s for s in by.values() if s["name"] not in live), key=lambda s: str(s.get("updated_utc")), reverse=True)
    on = _working(r)
    return {"running": on, "pid": _pid(r) if on else None, "paused": PS.paused(r), "counts": dict(Counter(s.get("status") for s in by.values())),
            "ideas": [by[n] for n in live] + rest}


# ---------------------------------------------------------------- the owner's two words

def _awaiting(name, root, what: str) -> dict:
    st = PS.state(name, root)
    if st.get("status") != "awaiting_owner":
        raise J.Refuse(f"{name} is {st.get('status')}: only an idea that passed every stage and waits for the owner (awaiting_owner) is {what}")
    return st


def approve(name, root=None) -> dict:
    """The owner's yes: the book card of stage 7 goes in the book, the status becomes "book" -> the state."""
    _awaiting(name, root, "approved")
    card = (PS.stages(name, root).get(LAST) or {}).get("book")
    if not (isinstance(card, dict) and card):
        raise J.Refuse(f"{name} has no book card: its stage {LAST} card is missing, or carries no \"book\" -- nothing was written")
    PS.write_book(name, card, root)
    return PS.set_state(name, root, status="book")


def refuse(name, why, root=None) -> dict:
    """The owner's no, with his reason -> the state ("refused", why)."""
    _awaiting(name, root, "refused")
    why = " ".join(str(why or "").split())
    if not why:
        raise J.Refuse(f"refusing {name} needs the reason (bp.py pipe refuse {name} --why=TEXT): it is kept with the idea")
    return PS.set_state(name, root, status="refused", why=why)


# ---------------------------------------------------------------- the commands, each as one result

def _table(head: tuple, rows: list, right=()) -> list:
    """Aligned rows under a head; the columns of `right` to the right, the last one as long as it is."""
    rows = [tuple(str(c) for c in r) for r in (head, *rows)]
    wide = [max(len(r[i]) for r in rows) for i in range(len(head))]
    return ["  ".join(c.rjust(wide[i]) if i in right else c if i == len(head) - 1 else c.ljust(wide[i]) for i, c in enumerate(r)).rstrip() for r in rows]


def _reached(st: dict):
    """The stage an idea reached: the one it stopped at, else the last it finished (None = none yet)."""
    return st.get("stopped_at") if st.get("stopped_at") is not None else st.get("stage")


def _dash(v) -> str:
    return "-" if v is None or v == "" else str(v)


def add(card, root=None, inbox: bool = False) -> dict:
    """`pipe add`: lines P0.1-P0.4 first; a whole card is filed and queued (the inbox goes first)."""
    name = card.get("name") if isinstance(card, dict) else None
    rows, subs = PC.check(card)                     # what is no card at all is refused outright (judge.Refuse)
    bad = [r["text"] for r in rows if r["passed"] is False]
    if bad or subs is None:
        return {**api.refused("pipe add", "the card is not whole: " + "; ".join(bad), name), "lines": rows}
    st = PS.add(card, subs, root, inbox, sig=PC.signature(card), family=PC.family_of(card))
    queue, maps = PS.order(root), [s["name"] for s in subs]
    text = [f"{name} is in the queue: place {queue.index(name) + 1} of {len(queue)}" + (" (inbox: it goes first)" if inbox else "") + ".",
            f"Stage 1 will run {len(maps)} heat map{'s' * (len(maps) != 1)}: {', '.join(maps)}."]
    return api.result("pipe add", name, status=st["status"], lines=rows, state=st, subs=maps, text="\n".join(text), saved=[str(PS.root(root) / "p" / name)],
                      next="bp.py pipe start runs the queue by itself; bp.py pipe list shows where each idea is.")


def listing(root=None) -> dict:
    """`pipe list`: one row an idea, what can run first; then the count by status, the runner and the pause."""
    s = status(root)
    rows = [(x["name"], _dash(x.get("family")), x.get("status"), _dash(_reached(x)), x.get("tries") or 0, _first(x.get("why"))[:WHY]) for x in s["ideas"]]
    n = len(rows)
    text = _table(("name", "family", "status", "stage", "tries", "why"), rows, right=(3, 4)) if rows else ["no idea is on file"]
    text += ["", f"{n} idea{'s' * (n != 1)}" + (": " + ", ".join(f"{s['counts'][k]} {k}" for k in PS.STATUS if s["counts"].get(k)) if n else ""),
             "runner: " + (f"working (pid {s['pid']})" if s["running"] and s["pid"] else "working" if s["running"] else "not working")
             + " · queue: " + ("paused" if s["paused"] else "not paused")]
    return api.result("pipe list", **s, text="\n".join(text),
                      next="" if s["running"] or not any(x.get("status") in PS.LIVE for x in s["ideas"]) else "bp.py pipe start runs the queue.")


def show(name, root=None) -> dict:
    """`pipe show <name>`: the card's reason, the state, then every stage card's first line."""
    st, card, stages = PS.state(name, root), PS.card(name, root), PS.stages(name, root)
    picked = st.get("picked") or {}
    text = [f"{name}: {_dash(st.get('family'))} on {card.get('market')} {card.get('session')}, sides {card.get('sides')} (source {_dash(st.get('source'))})",
            f"why: {card.get('why')}", f"loser: {card.get('loser')}",
            f"status: {st.get('status')} · stage {_dash(_reached(st))} · tries {st.get('tries') or 0}"
            + (f" · picked {picked.get('sub')}" + (f" with {picked['filter']}" if picked.get("filter") else "") + (f", box {picked['cell']}" if picked.get("cell") else "")
               if picked.get("sub") else "")]
    if st.get("why"):
        text.append(f"{'refused' if st.get('status') == 'refused' else 'stopped'}: {st['why']}")
    text += [f"stage {n} {MARK.get(c.get('passed'), 'n/a'):<4} {c.get('name') or (NAMES[n] if 0 <= n <= LAST else '')}: {_first(c.get('text'))}" for n, c in stages.items()]
    return api.result("pipe show", name, status=st.get("status"), state=st, card=card, stages={str(n): c for n, c in stages.items()}, text="\n".join(text),
                      next=f"bp.py pipe approve {name}, or bp.py pipe refuse {name} --why=TEXT." if st.get("status") == "awaiting_owner" else "")


def booked(root=None) -> dict:
    """`pipe book`: one row a book card."""
    cards = PS.book(root)
    rows = [tuple(_dash(c.get(k)) for k in ("name", "label", "family", "market", "session", "bar")) for c in cards]
    text = _table(("name", "label", "family", "market", "session", "bar"), rows) if rows else ["the book is empty"]
    return api.result("pipe book", book=cards, text="\n".join(text))


def rerun(name, root=None) -> dict:
    """`pipe rerun`: the idea starts again from its first stage (module docstring) -> one result."""
    moved = len(PS.stages(name, root))
    st = PS.reset(name, root)
    queue = PS.order(root)
    text = (f"{name} runs again from its first stage (place {queue.index(name) + 1} of {len(queue)} in the queue); its {moved} stage card{'s' * (moved != 1)} "
            "are kept under stages_old (nothing was deleted).") if moved else f"{name} is queued again from its first stage (place {queue.index(name) + 1} of {len(queue)})."
    return api.result("pipe rerun", name, status=st["status"], state=st, moved=moved, text=text, next="bp.py pipe start runs the queue (a runner that is working takes it by itself).")


def command(sub: str, name=None, root=None, *, card=None, inbox: bool = False, why=None, once: bool = False) -> dict:
    """`bp.py pipe <sub>` -> the command's ONE result object. `root` = the PIPELINE root (never the app's idea folder)."""
    cmd = f"pipe {sub}"
    if sub == "add":
        return add(card, root, inbox)
    if sub == "list":
        return listing(root)
    if sub == "show":
        return show(name, root)
    if sub == "book":
        return booked(root)
    if sub == "rerun":
        return rerun(name, root)
    if sub == "start":
        got = start(root)
        pid = f" (pid {got['pid']})" if got["pid"] else ""
        text = f"a runner is already working{pid}: nothing was started" if got["already"] else f"the runner is started{pid}: it works through the queue by itself"
        return api.result(cmd, **got, paused=PS.paused(root), text=text + (". The queue is PAUSED: bp.py pipe resume lets it work" if PS.paused(root) else ""),
                          next="bp.py pipe list shows where each idea is.")
    if sub in ("pause", "resume"):
        on = PS.pause(root) if sub == "pause" else PS.resume(root)
        work = _working(PS.root(root))
        text = ("the queue is paused: the runner stops after the stage in hand" if on else
                "the queue is not paused: " + ("the runner carries on" if work else "no runner is working"))
        return api.result(cmd, paused=on, running=work, text=text, next="bp.py pipe resume carries on." if on else "" if work else "bp.py pipe start runs the queue.")
    if sub in ("approve", "refuse"):
        st = approve(name, root) if sub == "approve" else refuse(name, why, root)
        file = PS.root(root) / "book" / f"{name}.json"
        return api.result(cmd, name, status=st["status"], state=st, saved=[str(file)] if sub == "approve" else [],
                          text=f"{name} is in the book ({file})" if sub == "approve" else f"{name} is refused: {st['why']}")
    if sub == "_loop":                              # the detached child of start(): no command of the pipeline's users
        return api.result(cmd, exit=loop({"root": root, "tiny": None}, once=once), text=f"the runner of {PS.root(root)} ended")
    raise J.Refuse(f"pipe {sub}: no command of the pipeline ({', '.join(SUBS)})")
