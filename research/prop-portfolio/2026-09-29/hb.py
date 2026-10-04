#!/usr/bin/env python3
"""hb.py: the only submitter of tester jobs for the prop-portfolio pilots (NQ in R, ES in ../2026-09-30-es; see SPEC.md).

ONE daemon, ONE queue order: every pilot has its own queue.jsonl / jobs.jsonl / ledger.csv / progress.md block, but at most 2
of OUR jobs run at once across all pilots and queued jobs are taken pilot by pilot in PILOT_ORDER (NQ first, then ES), each in
queue order. A job line's "pilot" field ("nq" default, "es") picks the pilot; caps (400 screening runs / 3,000 heat-map cells /
15 walk-forwards) are counted PER pilot.

  hb.py submit <jobs.jsonl>   append job lines to their pilot's queue.jsonl (deduped by key within a pilot)
  hb.py run [--once]          the daemon loop: nohup ... hb.py run >> hb.log 2>&1 &   (--once: exit when idle)
  hb.py status                <= 15 line summary          hb.py wait <stage> [pilot|all]   block until the stage is finished (pilot default nq)
  hb.py dry-run               self-test against a fake client (touches nothing real)

HOLDOUT GUARD (2026-09-30): a range that reaches 2025-01-01 or later is refused everywhere (queue time and submit time) unless the job is
stage "holdout", its key is in the pilot's FROZEN manifest (out/holdout_manifest.json, whose sha256 must equal out/holdout_manifest.sha256)
and kind / strategy / inputs / range / costs equal the manifest's job line. Holdout runs count against the screening-run cap and their
ledger rows go to ledger_holdout.csv (never into ledger.csv, which the in-sample scripts read).

Run it as:  cd R && PYTHONPATH=~/ramos-quant-homebase nohup ~/ramos-quant-homebase/.venv/bin/python hb.py run >> hb.log 2>&1 &
Stop it with `kill $(cat R/hb.pid)`; jobs keep running server-side and the next `run` re-attaches by id.
Only loopback chart-service (:8852) tester routes are used; the desk is never touched.
"""
from __future__ import annotations

import csv
import datetime as dt
import fcntl
import json
import os
import re
import signal
import sys
import time
from pathlib import Path
from zoneinfo import ZoneInfo

R = Path(__file__).resolve().parent
REPO = Path(os.environ.get("HB_REPO", Path.home() / "ramos-quant-homebase"))
sys.path.insert(0, str(REPO))
from homebase.claude_mcp.client import Client, ToolError   # noqa: E402
from homebase.claude_mcp.tools import _costs, range_body    # noqa: E402  (the bodies t_backtest/t_heatmap/t_walkforward send)

sys.path.insert(0, str(R))
import pilot as PLT   # noqa: E402  (pilot registry: name -> root / data dir)

ET = ZoneInfo("America/New_York")
FINAL = ("done", "error", "cancelled")
TERMINAL = ("done", "error", "cancelled", "capped")
POLL_S, TICK_S = 20, 5


def max_ours(now) -> int:
    """Our concurrent jobs = the machine's slot cap at this ET time (2 desk hours, 4 off hours)."""
    from homebase.backtest.slots import cap_at
    return cap_at(now)
QUIET_FROM, QUIET_TO = dt.time(9, 18), dt.time(9, 36)      # nothing starts 09:20-09:35 ET (+2 min margin)
CAPS = {"screen_runs": 400, "grid_cells": 3000, "walkforwards": 15}      # PER pilot
PILOT_ORDER = ("nq", "es")                                                  # queued jobs are taken in this pilot order
PILOT_DIRS = {n: Path(v["dir"]) for n, v in PLT.PILOTS.items()}
COLS = ("stage key kind strategy params_json run_id grid_id cell trades net sharpe wr pf maxdd "
        "pe_lucid_pass pe_lucid_bust pe_lucid_days elapsed_s finished_utc").split()
STATE = REPO / "homebase" / ".state" / "tester"
HOLDOUT_START = "2025-01-01"
CAP_STAGES = ("screen", "ctrl", "holdout")             # stages counted against the screening-run cap


def utc() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- holdout guard

def sha256_file(p) -> str:
    import hashlib
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def reaches_holdout(rng) -> bool:
    """True when a job range includes any day >= 2025-01-01 (custom end >= 2025, or the 2025-2026 / all presets)."""
    try:
        b = range_body(rng)
    except ToolError:
        return True                                   # unparseable range: treat as reaching (refused unless frozen)
    return b.get("kind") == "custom" and str(b.get("end") or "9999") >= HOLDOUT_START


def frozen_manifest(pilot: str, dirs: dict | None = None):
    """-> (manifest dict, None) when the pilot's manifest exists and matches its .sha256, else (None, reason)."""
    d = Path((dirs or PILOT_DIRS)[pilot])
    mp, sp = d / "out" / "holdout_manifest.json", d / "out" / "holdout_manifest.sha256"
    if not mp.exists() or not sp.exists():
        return None, "no frozen manifest (out/holdout_manifest.json + .sha256)"
    if sha256_file(mp) != sp.read_text().split()[0]:
        return None, "manifest sha256 does not match holdout_manifest.sha256 (manifest changed after the freeze)"
    return json.loads(mp.read_text()), None


def holdout_refusal(pilot: str, spec: dict, dirs: dict | None = None) -> str | None:
    """None = allowed. Everything reaching 2025+ must be a frozen-manifest holdout run; holdout stage jobs must reach 2025+."""
    reach, stage = reaches_holdout(spec.get("range")), spec.get("stage")
    if not reach and stage != "holdout":
        return None
    if reach and stage != "holdout":
        return f"range reaches {HOLDOUT_START}+ but stage is {stage!r}: only stage 'holdout' jobs of the frozen manifest may"
    if not reach:
        return "stage 'holdout' needs a range that reaches 2025+"
    if spec.get("kind") != "run":
        return "holdout jobs must be single runs (no grids / walk-forwards)"
    man, why = frozen_manifest(pilot, dirs)
    if man is None:
        return why
    jl = {j["key"]: j for j in man.get("jobs", [])}.get(spec.get("key"))
    if jl is None:
        return f"key {spec.get('key')!r} is not in the frozen manifest"
    for k in ("kind", "strategy", "inputs", "range", "costs"):
        if (spec.get(k) or ({} if k in ("inputs", "costs") else None)) != (jl.get(k) or ({} if k in ("inputs", "costs") else None)):
            return f"{k} differs from the frozen manifest's job line"
    return None


def quiet_wait(now: dt.datetime) -> float:
    """Seconds to sleep before a submit is allowed (0 = go)."""
    now = now.astimezone(ET)
    wait = 0.0
    if now.weekday() < 5 and QUIET_FROM <= now.time() < QUIET_TO:
        wait = (dt.datetime.combine(now.date(), QUIET_TO, ET) - now).total_seconds()
    # the tester's runtime override (~/.homebase/tester_slots.json "quiet" windows, e.g. the NFP bot)
    from homebase.backtest.slots import quiet_end
    end = quiet_end(now)
    if end is not None:
        wait = max(wait, (end - now).total_seconds())
    return wait


def offline_pause_s(now: dt.datetime | None = None) -> float:
    """Seconds an OFFLINE compute batch (searches, Monte Carlo) must sleep before starting: 0 = go.
    Same windows as quiet_wait (09:18-09:36 weekdays + the override's windows)."""
    return quiet_wait(now or dt.datetime.now(ET))


def q(s) -> str:
    from urllib.parse import quote
    return quote(str(s), safe="")


class Driver:
    def __init__(self, root: Path, client, now=None, sleep=time.sleep, state: Path | None = STATE, caps=None, pilots=None):
        """pilots: {name: data dir} (default {"nq": root}); root = the daemon's home (hb.pid / hb.log)."""
        self.root, self.c, self.sleep, self.state = Path(root), client, sleep, state
        self.now = now or (lambda: dt.datetime.now(ET))
        self.caps = dict(CAPS, **(caps or {}))
        self.pdirs: dict[str, Path] = {n: Path(d) for n, d in (pilots or {"nq": self.root}).items()}
        self.guard_dirs = dict(self.pdirs)
        self.pnames = sorted(self.pdirs, key=lambda n: (PILOT_ORDER.index(n) if n in PILOT_ORDER else len(PILOT_ORDER), n))
        self.queue_f, self.jobs_f, self.ledger_f = (self.root / n for n in ("queue.jsonl", "jobs.jsonl", "ledger.csv"))   # nq/home files
        self.progress_f, self.log_f = self.root / "progress.md", self.root / "hb.log"
        self.jobs: dict[str, dict] = {}         # uid -> job; uid = key for nq (as before), "<pilot>:<key>" for the others
        self.last_error, self.backoff, self.retry_at = "", 60, 0.0
        self.errs: dict[str, str] = {}
        self.block_at, self.block_txt, self.stop = {}, {}, False
        self.mono = time.monotonic          # fake clocks override
        self._load_jobs()
        self.ledger_seen = {n: self._ledger_keys(n) for n in self.pnames}

    # ---- per-pilot files
    def pf(self, pilot: str, name: str) -> Path:
        return self.pdirs[pilot] / name

    @staticmethod
    def uid(pilot: str, key: str) -> str:
        return key if pilot == "nq" else f"{pilot}:{key}"

    def lab(self, j: dict) -> str:
        """log label: the key, prefixed with the pilot when it is not nq."""
        return self.uid(j["pilot"], j["key"])

    def _err(self, j: dict, msg: str):
        self.last_error = msg
        self.errs[j["pilot"]] = msg

    # ---- persistence
    def log(self, msg):
        line = f"{self.now().strftime('%Y-%m-%d %H:%M:%S')} {msg}"
        print(line, flush=True)

    def _load_jobs(self):
        for n in self.pnames:
            f = self.pf(n, "jobs.jsonl")
            if f.exists():
                for ln in f.read_text().splitlines():
                    if ln.strip():
                        j = json.loads(ln)
                        j["pilot"] = n
                        self.jobs[self.uid(n, j["key"])] = j

    def _save_jobs(self, pilot: str | None = None):
        for n in ([pilot] if pilot else self.pnames):
            f = self.pf(n, "jobs.jsonl")
            tmp = f.with_suffix(".tmp")
            tmp.write_text("".join(json.dumps({k: v for k, v in j.items() if k != "pilot"} | ({"pilot": n} if n != "nq" else {}),
                                              sort_keys=True) + "\n" for j in self.jobs.values() if j["pilot"] == n))
            os.replace(tmp, f)

    def _ledger_keys(self, pilot: str = "nq") -> set:
        out = set()
        for nm in ("ledger.csv", "ledger_holdout.csv"):
            f = self.pf(pilot, nm)
            if f.exists():
                with f.open(newline="") as fh:
                    out |= {(r["key"], r["cell"]) for r in csv.DictReader(fh)}
        return out

    def read_queue(self, pilot: str = "nq") -> list[dict]:
        out, f = [], self.pf(pilot, "queue.jsonl")
        if f.exists():
            for ln in f.read_text().splitlines():
                if ln.strip():
                    out.append(json.loads(ln))
        return out

    def sync_queue(self):
        for n in self.pnames:
            for spec in self.read_queue(n):
                u = self.uid(n, spec["key"])
                if u not in self.jobs:
                    self.jobs[u] = {"key": spec["key"], "kind": spec["kind"], "stage": spec.get("stage", "?"), "pilot": n,
                                    "strategy": spec.get("strategy"), "status": "queued", "spec": spec}
                    self._save_jobs(n)

    # ---- caps
    def cap_check(self, j: dict) -> str | None:
        sp, started = j["spec"], [x for x in self.jobs.values() if x.get("id") and x["pilot"] == j["pilot"]]
        if j["kind"] == "run" and j["stage"] in CAP_STAGES:
            used = sum(1 for x in started if x["kind"] == "run" and x["stage"] in CAP_STAGES)
            if used + 1 > self.caps["screen_runs"]:
                return f"screening-run cap {self.caps['screen_runs']} reached ({used} used)"
        if j["kind"] == "grid":
            from homebase.backtest.grid import expand
            n = len(expand(sp["axes"]))
            used = sum(x.get("cells", 0) for x in started if x["kind"] == "grid")
            if used + n > self.caps["grid_cells"]:
                return f"heat-map cell cap {self.caps['grid_cells']} would be exceeded ({used} used + {n})"
            j["cells"] = n
        if j["kind"] == "walkforward":
            used = sum(1 for x in started if x["kind"] == "walkforward")
            if used + 1 > self.caps["walkforwards"]:
                return f"walk-forward cap {self.caps['walkforwards']} reached ({used} used)"
        return None

    # ---- submit / poll
    def body(self, sp: dict) -> tuple[str, dict]:
        b = {"strategy": sp["strategy"], "inputs": sp.get("inputs") or {}, "range": range_body(sp.get("range")),
             **_costs(sp.get("costs"))}
        if sp.get("prop_rules"):
            b["prop_rules"] = sp["prop_rules"]
        if sp["kind"] == "run":
            return "/api/tester/run", b
        b["axes"] = sp["axes"]
        if sp.get("max_cells") is not None:
            b["max_cells"] = sp["max_cells"]
        if sp["kind"] == "grid":
            return "/api/tester/grid", b
        b["test_months"] = sp.get("ratio", 3)
        for k in ("metric", "min_trades"):
            if sp.get(k) is not None:
                b[k] = sp[k]
        return "/api/tester/walkforward", b

    def status_path(self, j):
        return {"run": "/api/tester/run/", "grid": "/api/tester/grid/", "walkforward": "/api/tester/walkforward/"}[j["kind"]] + q(j["id"])

    def running(self) -> list[dict]:
        return [j for j in self.jobs.values() if j["status"] == "submitted"]

    def try_submit(self, j: dict) -> bool:
        why = holdout_refusal(j["pilot"], j["spec"], self.guard_dirs)
        if why:
            j.update(status="error", error="HOLDOUT GUARD: " + why, finished_utc=utc())
            self._err(j, f"{j['key']}: HOLDOUT GUARD {why}")
            self.log(f"HOLDOUT GUARD refuse {self.lab(j)}: {why}")
            self._save_jobs(j["pilot"])
            return True
        why = self.cap_check(j)
        if why:
            j.update(status="capped", error=why, finished_utc=utc())
            self._err(j, f"{j['key']}: {why}")
            self.log(f"CAP refuse {self.lab(j)}: {why}")
            self._save_jobs(j["pilot"])
            return True
        path, body = self.body(j["spec"])
        try:
            jid = self.c.post(path, body)["id"]
        except ToolError as e:
            msg = str(e)
            j.pop("cells", None)
            if re.match(r"(400|404|415|422):", msg):          # a bad job, not a refusal: never retried
                j.update(status="error", error=msg, finished_utc=utc())
                self._err(j, f"{j['key']}: {msg}")
                self.log(f"BAD JOB {self.lab(j)}: {msg}")
                self._save_jobs(j["pilot"])
                return True
            self._err(j, f"{j['key']}: {msg}")
            self.retry_at = self.mono() + self.backoff
            self.log(f"REFUSED {self.lab(j)}: {msg} -> back off {self.backoff}s")
            self.backoff = min(self.backoff * 2, 900)
            return False
        self.backoff = 60
        j.update(status="submitted", id=jid, submitted_utc=utc(), _t0=self.mono())
        self._save_jobs(j["pilot"])
        self.log(f"submitted {self.lab(j)} -> {jid}")
        return True

    def finish(self, j: dict, st: dict):
        j["elapsed_s"] = round(self.mono() - j["_t0"]) if "_t0" in j else None
        j["finished_utc"] = utc()
        if st.get("status") != "done":
            j.update(status=st["status"], error=st.get("error") or "")
            self._err(j, f"{j['key']}: {st['status']} {st.get('error') or ''}".strip())
            self.log(f"{self.lab(j)} {st['status']}: {st.get('error') or ''}")
        else:
            try:
                n = self.write_ledger(j, st)
            except Exception as e:                                   # keep the job pollable; retry next poll
                self._err(j, f"{j['key']}: ledger {e!r}")
                self.log(f"LEDGER FAIL {self.lab(j)}: {e!r}")
                return
            j["status"] = "done"
            self.log(f"{self.lab(j)} done ({n} ledger rows, {j['elapsed_s']}s)")
        self._save_jobs(j["pilot"])

    def poll(self):
        for j in self.running():
            try:
                st = self.c.get(self.status_path(j))
            except ToolError as e:
                self._err(j, f"{j['key']}: poll {e}")
                continue
            if st.get("status") in FINAL:
                self.finish(j, st)

    # ---- ledger
    def _disk(self, *parts):
        if self.state:
            p = self.state.joinpath(*parts)
            if p.exists():
                return json.loads(p.read_text())
        return None

    def metrics(self, summary: dict | None, propsim: dict | None, rules_id: str | None) -> dict:
        s = summary or {}
        m = {"trades": s.get("trades"), "net": s.get("net_profit"), "sharpe": s.get("sharpe"), "wr": s.get("win_rate"),
             "pf": s.get("profit_factor"), "maxdd": s.get("max_drawdown")}
        h = (propsim or {}).get("headline") or {}
        if str(rules_id or "").startswith("lucid") and h:
            m.update(pe_lucid_pass=h.get("eval_pass_p"), pe_lucid_bust=h.get("bust_p"), pe_lucid_days=h.get("median_days_to_pass"))
        return m

    def rows_for(self, j: dict, st: dict) -> list[dict]:
        sp, rules = j["spec"], j["spec"].get("prop_rules")
        if j["kind"] == "run":
            run, ps = self._disk("runs", j["id"], "run.json"), self._disk("runs", j["id"], "propsim.json")
            if run is None:
                b = self.c.get(f"/api/tester/run/{q(j['id'])}/bundle")
                run, ps = b["run"], b.get("propsim")
            return [dict(params_json=json.dumps(sp.get("inputs") or {}, sort_keys=True), run_id=j["id"], cell="",
                         **self.metrics(((run.get("report") or {}).get("summary") or {}).get("all"), ps, rules))]
        if j["kind"] == "grid":
            rows = []
            for c in st.get("cells") or []:
                if c.get("status") != "done" or (c.get("summary") or {}).get("net_profit") is None:
                    continue
                ps = self._disk("grids", j["id"], "cells", f"{int(c['i']):02d}", "propsim.json")
                if ps is None and rules:
                    try:
                        ps = self.c.get(f"/api/tester/grid/{q(j['id'])}/cell/{c['i']}/bundle").get("propsim")
                    except ToolError:
                        ps = None
                rows.append(dict(params_json=json.dumps({**(sp.get("inputs") or {}), **(c.get("params") or {})}, sort_keys=True),
                                 grid_id=j["id"], cell=c["i"], **self.metrics(c["summary"], ps, rules)))
            return rows
        r = self.c.get(f"/api/tester/walkforward/{q(j['id'])}/result")     # walk-forward: one row, stitched OOS stats
        return [dict(params_json=json.dumps({"wf": {k: sp.get(k) for k in ("ratio", "metric", "min_trades")}, "axes": sp["axes"]}, sort_keys=True),
                     grid_id=j["id"], cell="wf", **self.metrics((r.get("stitched") or {}).get("stats"), None, rules))]

    def write_ledger(self, j: dict, st: dict) -> int:
        p = j["pilot"]
        seen, lf = self.ledger_seen[p], self.pf(p, "ledger_holdout.csv" if j["stage"] == "holdout" else "ledger.csv")
        rows = [r for r in self.rows_for(j, st) if (j["key"], str(r["cell"])) not in seen]
        new = not lf.exists() or lf.stat().st_size == 0
        with lf.open("a", newline="") as f:
            w = csv.DictWriter(f, COLS, restval="")
            if new:
                w.writeheader()
            for r in rows:
                w.writerow({"stage": j["stage"], "key": j["key"], "kind": j["kind"], "strategy": j["strategy"],
                            "elapsed_s": j["elapsed_s"], "finished_utc": j["finished_utc"], **r})
                seen.add((j["key"], str(r["cell"])))
        return len(rows)

    # ---- progress.md (one "## Queue status" block per pilot, in that pilot's own progress.md)
    def block(self, alive=True, pilot: str = "nq") -> str:
        mine = [j for j in self.jobs.values() if j["pilot"] == pilot]
        by: dict[str, dict] = {}
        for j in mine:
            d = by.setdefault(j["stage"], {})
            d[j["status"]] = d.get(j["status"], 0) + 1
        st = [f"{s}: " + " ".join(f"{k} {v}" for k, v in sorted(d.items())) for s, d in sorted(by.items())]
        started = [x for x in mine if x.get("id")]
        sr = sum(1 for x in started if x["kind"] == "run" and x["stage"] in CAP_STAGES)
        ho = sum(1 for x in started if x["stage"] == "holdout")
        gc = sum(x.get("cells", 0) for x in started if x["kind"] == "grid")
        wf = sum(1 for x in started if x["kind"] == "walkforward")
        run = [f"{self.lab(j)}={j['id']}" for j in self.running()]         # the 2 slots are shared by all pilots
        err = self.errs.get(pilot) if len(self.pnames) > 1 else (self.errs.get(pilot) or self.last_error)
        return "\n".join([
            "## Queue status",
            f"_auto-written by hb.py; daemon {'running' if alive else 'stopped'}; pilot {pilot}; updated {self.now().strftime('%Y-%m-%d %H:%M ET')}_",
            "- stages: " + ("; ".join(st) or "empty"),
            f"- caps used: screening runs {sr}/{self.caps['screen_runs']}, heat-map cells {gc}/{self.caps['grid_cells']}, "
            f"walk-forwards {wf}/{self.caps['walkforwards']}",
            f"- 2025+ frozen-manifest runs started: {ho} (counted in the screening-run cap above)",
            f"- running ({len(run)}/{max_ours(self.now())}{', slots shared by all pilots' if len(self.pnames) > 1 else ''}): " + (", ".join(run) or "none"),
            f"- last error: {err or 'none'}",
            ""])

    def write_block(self, alive=True, force=False):
        for n in self.pnames:
            txt = self.block(alive, n)
            body = re.sub(r"updated [^_]*", "", txt)
            if not force and body == self.block_txt.get(n) and self.mono() - self.block_at.get(n, 0.0) < 300:
                continue
            self.block_txt[n], self.block_at[n] = body, self.mono()
            pf = self.pf(n, "progress.md")
            cur = pf.read_text() if pf.exists() else ""
            pat = re.compile(r"^## Queue status\n.*?(?=^## |\Z)", re.M | re.S)
            new = pat.sub(lambda _m: txt + "\n", cur, count=1) if pat.search(cur) else cur.rstrip("\n") + "\n\n" + txt + "\n"
            tmp = pf.with_suffix(".tmp")
            tmp.write_text(new)
            os.replace(tmp, pf)

    # ---- the loop
    def tick(self, last_poll: list):
        self.sync_queue()
        if self.mono() - last_poll[0] >= POLL_S:
            last_poll[0] = self.mono()
            self.poll()
        if quiet_wait(self.now()) == 0 and self.mono() >= self.retry_at:
            queued = [x for x in self.jobs.values() if x["status"] == "queued"]
            queued.sort(key=lambda x: self.pnames.index(x["pilot"]))          # stable: nq jobs first, then es, each in queue order
            for j in queued:
                if len(self.running()) >= max_ours(self.now()):
                    break
                if not self.try_submit(j) or quiet_wait(self.now()):
                    break
        self.write_block()

    def idle(self) -> bool:
        return not any(j["status"] in ("queued", "submitted") for j in self.jobs.values())

    def loop(self, once=False, max_s=None):
        self.log("hb driver up")
        last, t0 = [-1e9], self.mono()
        while not self.stop:
            self.tick(last)
            if once and self.idle():
                break
            if max_s and self.mono() - t0 > max_s:
                break
            self.sleep(TICK_S)
        self.write_block(alive=False, force=True)
        self.log("hb driver down")


# ---------------------------------------------------------------- CLI

def pid_alive(p) -> bool:
    try:
        os.kill(int(p), 0)
        return True
    except (OSError, ValueError, TypeError):
        return False


def active_pilots() -> dict[str, Path]:
    """nq (R) always; every other registered pilot whose data dir exists."""
    return {n: d for n, d in PILOT_DIRS.items() if n == "nq" or d.is_dir()}


def cmd_submit(path):
    """Append job lines to their pilot's queue.jsonl ("pilot": "nq" default | "es"); deduped by key within a pilot."""
    dirs = active_pilots()
    have: dict[str, set] = {}
    files: dict[str, object] = {}
    n = 0
    for ln in Path(path).read_text().splitlines():                    # holdout guard first: nothing is queued if any line is refused
        if ln.strip():
            j = json.loads(ln)
            why = holdout_refusal(j.get("pilot", "nq"), j, dirs) if j.get("pilot", "nq") in dirs else None
            if why:
                sys.exit(f"HOLDOUT GUARD refused {j.get('key')!r}: {why}")
    try:
        for ln in Path(path).read_text().splitlines():
            if not ln.strip():
                continue
            j = json.loads(ln)
            missing = [k for k in ("key", "kind", "stage", "strategy") if k not in j]
            if missing or j["kind"] not in ("run", "grid", "walkforward") or (j["kind"] != "run" and "axes" not in j):
                sys.exit(f"bad job line (need key, kind, stage, strategy, axes for grid/walkforward): {ln[:120]}")
            pl = j.get("pilot", "nq")
            if pl not in dirs:
                sys.exit(f"bad job line: unknown pilot {pl!r} (known: {sorted(dirs)}): {ln[:120]}")
            want = "draft_" + ("pp_" if pl == "nq" else f"pp_{pl}_")         # an NQ draft must never land in the ES ledger (and v.v.)
            if not str(j["strategy"]).startswith(want) or (pl == "nq" and str(j["strategy"]).startswith("draft_pp_es_")):
                sys.exit(f"bad job line: pilot {pl} needs a {want}* strategy, got {j['strategy']!r}")
            qf = dirs[pl] / "queue.jsonl"
            if pl not in have:
                have[pl] = {json.loads(x)["key"] for x in qf.read_text().splitlines() if x.strip()} if qf.exists() else set()
                files[pl] = qf.open("a")
            if j["key"] in have[pl]:
                continue
            have[pl].add(j["key"])
            files[pl].write(json.dumps(j) + "\n")
            n += 1
    finally:
        for f in files.values():
            f.close()
    print(f"queued {n} new job(s)")


def cmd_run(once=False):
    lock = open(R / "hb.pid", "a+")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        sys.exit("another hb.py run is already active (see hb.pid)")
    lock.seek(0), lock.truncate(), lock.write(str(os.getpid())), lock.flush()
    d = Driver(R, Client(), pilots=active_pilots())
    d.log("pilots: " + ", ".join(f"{n}={p}" for n, p in d.pdirs.items()))
    signal.signal(signal.SIGTERM, lambda *_: setattr(d, "stop", True))
    signal.signal(signal.SIGINT, lambda *_: setattr(d, "stop", True))
    d.loop(once=once)


def cmd_status():
    d = Driver(R, None, pilots=active_pilots())
    d.sync_queue()
    pid = (R / "hb.pid").read_text().strip() if (R / "hb.pid").exists() else ""
    alive = pid_alive(pid)
    for n in d.pnames:
        print("\n".join(x for x in d.block(alive, n).splitlines() if x.strip() and not x.startswith("_auto")))
    print(f"pid {pid or '-'} {'alive' if alive else 'not running'}; ledger rows: "
          + ", ".join(f"{n} {len(d.ledger_seen[n])}" for n in d.pnames))


def cmd_wait(stage, pilot="nq"):
    d = Driver(R, None, pilots=active_pilots())
    names = d.pnames if pilot == "all" else [pilot]
    while True:
        d.jobs.clear()
        d._load_jobs()
        d.sync_queue()
        js = [j for j in d.jobs.values() if j["stage"] == stage and j["pilot"] in names]
        if js and all(j["status"] in TERMINAL for j in js):
            bad = [d.lab(j) for j in js if j["status"] != "done"]
            print(f"stage {stage} ({pilot}): {len(js)} job(s) finished; not done: {bad or 'none'}")
            return
        if not pid_alive((R / "hb.pid").read_text().strip() if (R / "hb.pid").exists() else ""):
            print("warning: no hb.py run daemon is alive", file=sys.stderr)
        time.sleep(15)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["submit"] and len(a) == 2:
        cmd_submit(a[1])
    elif a[:1] == ["run"]:
        cmd_run("--once" in a)
    elif a[:1] == ["status"]:
        cmd_status()
    elif a[:1] == ["wait"] and len(a) in (2, 3):
        cmd_wait(*a[1:])
    elif a[:1] == ["dry-run"] or a[:1] == ["--dry-run"]:
        import hb_dryrun
        sys.exit(hb_dryrun.main())
    else:
        sys.exit(__doc__)
