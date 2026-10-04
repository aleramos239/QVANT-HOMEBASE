"""hb.py dry-run: a fake chart-service client and a fake clock in a temp dir. Touches nothing real."""
import csv
import datetime as dt
import json
import os
import tempfile
from pathlib import Path

import hb
from homebase.claude_mcp.client import ToolError

ET = hb.ET


class Clock:
    def __init__(self, t):
        self.t, self.m = t, 0.0

    def now(self):
        return self.t

    def mono(self):
        return self.m

    def sleep(self, s):
        self.t += dt.timedelta(seconds=s)
        self.m += s


class Fake:
    """Jobs take `dur` fake seconds; refuses the first `refuse` posts (409) and any strategy named 'bad' (400)."""

    def __init__(self, clk, dur=60, refuse=0):
        self.clk, self.dur, self.refuse, self.posts, self.jobs, self.peak = clk, dur, refuse, [], {}, 0

    def post(self, path, body):
        assert not hb.quiet_wait(self.clk.now()), f"POST inside the quiet window at {self.clk.now()}"
        if body["strategy"] == "bad":
            raise ToolError("400: unknown strategy")
        if self.refuse > 0:
            self.refuse -= 1
            raise ToolError("409: not 09:20-09:35 ET on weekdays")
        jid = f"id{len(self.posts):03d}"
        self.posts.append((self.clk.now(), path, jid))
        self.jobs[jid] = (self.clk.m, path, body)
        self.peak = max(self.peak, sum(1 for x in self.jobs if self._st(x)["status"] != "done"))
        return {"id": jid}

    def _st(self, jid):
        t0, path, body = self.jobs[jid]
        st = {"status": "done" if self.clk.m - t0 >= self.dur else "running"}
        if path.endswith("/grid") or path.endswith("/walkforward"):
            n = 3
            st["cells"] = [{"i": i, "status": "done", "params": {"x": i},
                            "summary": {"net_profit": 10.0 * i, "sharpe": 1.0, "trades": 5, "win_rate": 50.0,
                                        "profit_factor": 1.1, "max_drawdown": -20.0}} for i in range(n)]
        return st

    def get(self, path):
        parts = path.strip("/").split("/")
        if parts[-1] == "result":
            return {"stitched": {"stats": {"net_profit": 5.0, "trades": 9, "sharpe": 0.5}}}
        if parts[-1] == "bundle":
            return {"run": {"report": {"summary": {"all": {"trades": 7, "net_profit": 123.0, "sharpe": 0.9, "win_rate": 55.0,
                                                          "profit_factor": 1.2, "max_drawdown": -50.0}}}},
                    "propsim": {"headline": {"eval_pass_p": 0.3, "bust_p": 0.7, "median_days_to_pass": 5}}}
        return self._st(parts[-1])


def job(key, kind="run", stage="screen", strategy="s", **kw):
    j = {"key": key, "kind": kind, "stage": stage, "strategy": strategy, "inputs": {}, "range": {"preset": "custom", "start": "2024-03-04", "end": "2024-03-08"},
         "prop_rules": "lucid-flex-50k@2026-09-27"}
    if kind != "run":
        j["axes"] = [{"key": "x", "values": [1, 2, 3]}]
    return {**j, **kw}


def mk(tmp, jobs, start, **fk):
    (tmp / "queue.jsonl").write_text("".join(json.dumps(j) + "\n" for j in jobs))
    clk, caps = Clock(start), fk.pop("caps", None)
    fake = Fake(clk, **fk)
    d = hb.Driver(tmp, fake, now=clk.now, sleep=clk.sleep, state=None, caps=caps)
    d.mono = clk.mono
    return d, fake, clk


def ledger(tmp):
    return list(csv.DictReader((tmp / "ledger.csv").open()))


def main():
    hb.POLL_S = 5
    os.environ["HOMEBASE_TESTER_SLOTS_FILE"] = str(Path(tempfile.gettempdir()) / "hb_dryrun_no_override.json")   # never the real override
    tue = lambda h, m: dt.datetime(2026, 9, 29, h, m, tzinfo=ET)
    ok = []

    def check(name, cond):
        ok.append(cond)
        print(("PASS " if cond else "FAIL ") + name)

    # 1 concurrency cap, ledger rows, progress block, refusal/back-off
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / "progress.md").write_text("# p\n\n## Decisions\nkeep me\n\n## Queue status\nold\n\n## Tail\nkeep too\n")
        js = [job(f"r{i}") for i in range(5)] + [job("g1", "grid", "calib"), job("bad1", strategy="bad")]
        d, fake, clk = mk(t, js, tue(11, 0), refuse=2)
        d.loop(once=True, max_s=3600)
        check("all jobs finished", all(j["status"] in hb.TERMINAL for j in d.jobs.values()))
        check("<=2 of ours running at once", fake.peak <= 2)
        check("bad job errored, not retried", d.jobs["bad1"]["status"] == "error")
        check("refusal backed off >=60s (first post no earlier than 11:03)", fake.posts[0][0] >= tue(11, 0) + dt.timedelta(seconds=180))
        rows = ledger(t)
        check("ledger: 5 runs + 3 grid cells", len(rows) == 8 and rows[0]["pe_lucid_pass"] == "0.3" and rows[0]["net"] == "123.0")
        p = (t / "progress.md").read_text()
        check("progress block replaced, other sections kept", "keep me" in p and "keep too" in p and "old" not in p
              and "caps used: screening runs 5/400" in p and "heat-map cells 3/3000" in p)

        # 2 idempotency: same key re-queued, restart -> no new posts, no dup ledger rows
        n = len(fake.posts)
        with (t / "queue.jsonl").open("a") as f:
            f.write(json.dumps(job("r0")) + "\n")
        d2 = hb.Driver(t, fake, now=clk.now, sleep=clk.sleep, state=None)
        d2.mono = clk.mono
        d2.loop(once=True, max_s=200)
        check("done key never resubmitted", len(fake.posts) == n and len(ledger(t)) == 8)

    # 3 restart re-attach
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        d, fake, clk = mk(t, [job("a"), job("b")], tue(11, 0), dur=100)
        last = [-1e9]
        d.tick(last)
        check("two submitted", len(fake.posts) == 2 and len(d.running()) == 2)
        d2 = hb.Driver(t, fake, now=clk.now, sleep=clk.sleep, state=None)      # "crash" + restart
        d2.mono = clk.mono
        check("restart sees them as running", len(d2.running()) == 2)
        d2.loop(once=True, max_s=600)
        check("re-attached, finished, no resubmit", len(fake.posts) == 2 and all(j["status"] == "done" for j in d2.jobs.values())
              and len(ledger(t)) == 2)

    # 4 the 09:20-09:35 window
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        d, fake, clk = mk(t, [job(f"w{i}") for i in range(5)], tue(9, 17), dur=30)
        d.loop(once=True, max_s=3600)
        times = sorted(p[0] for p in fake.posts)
        check("nothing posted 09:18-09:36, resumed at 09:36", all(x.time() < dt.time(9, 18) or x.time() >= dt.time(9, 36) for x in times)
              and any(x.time() >= dt.time(9, 36) for x in times))
        d, fake, clk = mk(Path(t), [job("w3")], dt.datetime(2026, 9, 26, 9, 25, tzinfo=ET), dur=30)   # a Saturday
        check("weekend has no window", hb.quiet_wait(clk.now()) == 0)

    # 4b the runtime override: NFP quiet window + 4 slots all day
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        ovf = t / "ov.json"
        ovf.write_text(json.dumps({"cap": 4, "until": "2026-10-05T08:00",
                                   "quiet": [{"from": "2026-10-02T08:15", "to": "2026-10-02T08:45"}]}))
        old = os.environ.get("HOMEBASE_TESTER_SLOTS_FILE")
        os.environ["HOMEBASE_TESTER_SLOTS_FILE"] = str(ovf)
        try:
            fri = lambda h, m, s=0: dt.datetime(2026, 10, 2, h, m, s, tzinfo=ET)
            check("override window: 08:30 waits 15 min", hb.quiet_wait(fri(8, 30)) == 15 * 60)
            check("override window: 08:14 and 08:45 go", hb.quiet_wait(fri(8, 14)) == 0 and hb.quiet_wait(fri(8, 45)) == 0)
            check("offline pause honours it, and 09:20 rule stays",
                  hb.offline_pause_s(fri(8, 20)) == 25 * 60 and hb.offline_pause_s(fri(9, 25)) == 11 * 60)
            check("our slots = 4 in desk hours under the override", hb.max_ours(fri(11, 0)) == 4)
            d, fake, clk = mk(t, [job(f"n{i}") for i in range(6)], fri(8, 10), dur=30)
            d.loop(once=True, max_s=7200)
            check("nothing posted 08:15-08:45", all(not (dt.time(8, 15) <= p[0].time() < dt.time(8, 45)) for p in fake.posts)
                  and len(fake.posts) == 6)
        finally:
            if old is None:
                os.environ.pop("HOMEBASE_TESTER_SLOTS_FILE", None)
            else:
                os.environ["HOMEBASE_TESTER_SLOTS_FILE"] = old

    # 5 caps
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        js = [job(f"c{i}") for i in range(4)] + [job("g1", "grid"), job("g2", "grid"), job("w1", "walkforward"),
                                                 job("w2", "walkforward"), job("k1", stage="calib")]
        d, fake, clk = mk(t, js, tue(11, 0), dur=10, caps={"screen_runs": 3, "grid_cells": 3, "walkforwards": 1})
        d.loop(once=True, max_s=3600)
        st = {k: v["status"] for k, v in d.jobs.items()}
        check("screen cap: 3 done, 1 capped", sorted(st[f"c{i}"] for i in range(4)) == ["capped", "done", "done", "done"])
        check("grid cell cap: one grid ok, one capped", sorted([st["g1"], st["g2"]]) == ["capped", "done"])
        check("walk-forward cap", sorted([st["w1"], st["w2"]]) == ["capped", "done"])
        check("calib stage uncapped", st["k1"] == "done")
    # 6 two pilots, one daemon: NQ first, per-pilot caps / ledger / progress block / jobs file, same key in both pilots
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        nq, es = t / "nq", t / "es"
        nq.mkdir(), es.mkdir()
        (es / "progress.md").write_text("# es\n\n## Keep\nhere\n")
        njobs = [job("r0"), job("r1"), job("r2")]
        ejobs = [job("r0", pilot="es", strategy="draft_pp_es_x"), job("e1", pilot="es", strategy="draft_pp_es_x"),
                 job("e2", pilot="es", strategy="draft_pp_es_x"), job("g1", "grid", "screen", pilot="es", strategy="draft_pp_es_x")]
        (nq / "queue.jsonl").write_text("".join(json.dumps(j) + "\n" for j in njobs))
        (es / "queue.jsonl").write_text("".join(json.dumps(j) + "\n" for j in ejobs))
        clk = Clock(tue(11, 0))
        fake = Fake(clk, dur=60)
        d = hb.Driver(nq, fake, now=clk.now, sleep=clk.sleep, state=None, caps={"screen_runs": 3, "grid_cells": 3, "walkforwards": 15},
                      pilots={"nq": nq, "es": es})
        d.mono = clk.mono
        d.loop(once=True, max_s=3600)
        order = [p_[2] for p_ in fake.posts]                                   # post order = job order
        names = [d.lab(j) for j in sorted(d.jobs.values(), key=lambda x: x["id"] if x.get("id") else "z")]
        check("all NQ jobs submitted before any ES job", names[:3] == ["r0", "r1", "r2"] and names[3].startswith("es:"))
        check("same key in both pilots stays two jobs", d.jobs["r0"]["pilot"] == "nq" and d.jobs["es:r0"]["pilot"] == "es")
        check("<=2 running across both pilots", fake.peak <= 2)
        check("caps are per pilot (NQ 3/3 runs; ES 3 runs + grid within its own cap)",
              all(d.jobs[k]["status"] == "done" for k in ("r0", "r1", "r2", "es:r0", "es:e1", "es:e2", "es:g1")))
        check("separate ledgers", len(ledger(nq)) == 3 and len(ledger(es)) == 6 and {r["key"] for r in ledger(es)} == {"r0", "e1", "e2", "g1"})
        jl = lambda d_: [json.loads(x) for x in (d_ / "jobs.jsonl").read_text().splitlines()]
        check("separate jobs files", len(jl(es)) == 4 and len(jl(nq)) == 3 and all(x["pilot"] == "es" for x in jl(es))
              and all("pilot" not in x for x in jl(nq)))
        pe, pn = (es / "progress.md").read_text(), (nq / "progress.md").read_text()
        check("per-pilot progress blocks (ES keeps its own sections)", "## Keep" in pe and "pilot es" in pe and "pilot nq" in pn
              and "screening runs 3/3," in pe and "screening runs 3/3," in pn and "heat-map cells 3/3," in pe and "heat-map cells 0/3," in pn)
        # cap per pilot: a 4th ES screening run is capped while NQ is untouched
        with (es / "queue.jsonl").open("a") as f:
            f.write(json.dumps(job("e3", pilot="es", strategy="draft_pp_es_x")) + "\n")
        d.caps["screen_runs"] = 3
        d.loop(once=True, max_s=600)
        check("ES cap hit independently of NQ", d.jobs["es:e3"]["status"] == "capped" and all(d.jobs[k]["status"] == "done" for k in ("r0", "r1", "r2")))
        # restart re-attaches an ES job by id
        (es / "queue.jsonl").write_text(json.dumps(job("late", pilot="es", strategy="draft_pp_es_x")) + "\n")
        (nq / "queue.jsonl").write_text("")
        d3 = hb.Driver(nq, fake, now=clk.now, sleep=clk.sleep, state=None, pilots={"nq": nq, "es": es})
        d3.mono = clk.mono
        n0 = len(fake.posts)
        d3.tick([-1e9])
        check("ES job submitted after restart", len(d3.running()) == 1 and len(fake.posts) == n0 + 1)
        d4 = hb.Driver(nq, fake, now=clk.now, sleep=clk.sleep, state=None, pilots={"nq": nq, "es": es})
        d4.mono = clk.mono
        check("restart re-attaches the ES job by id (no resubmit)", len(d4.running()) == 1 and d4.running()[0]["pilot"] == "es" and len(fake.posts) == n0 + 1)

    # 7 holdout guard: 2025+ only as stage holdout, key + spec frozen in a manifest whose sha256 matches; own ledger; counted in the cap
    HO = {"preset": "custom", "start": "2025-01-01", "end": "2026-09-30"}
    hj = lambda key, **kw: job(key, stage="holdout", range=HO, prop_rules=None, strategy="draft_pp_x", inputs={"tf": "5"}, costs={"qty": 1}, **kw)
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        ok_ = hj("ho-a")
        bad_stage = job("sneak", stage="screen", range=HO)
        bad_all = job("sneak2", stage="screen", range={"preset": "2025-2026"})
        js = [ok_, bad_stage, bad_all, hj("ho-not-frozen"), job("old", stage="screen")]
        d, fake, clk = mk(t, js, tue(11, 0), dur=10)
        d.loop(once=True, max_s=600)
        st = {k: v["status"] for k, v in d.jobs.items()}
        check("no manifest: every 2025+ job refused (holdout stage too), in-sample job runs", st["ho-a"] == "error" and st["sneak"] == "error"
              and st["sneak2"] == "error" and st["ho-not-frozen"] == "error" and st["old"] == "done" and len(fake.posts) == 1)
    with tempfile.TemporaryDirectory() as t:
        t = Path(t)
        (t / "out").mkdir()
        man = {"jobs": [{"key": "ho-a", "kind": "run", "strategy": "draft_pp_x", "inputs": {"tf": "5"}, "range": HO, "costs": {"qty": 1}}]}
        (t / "out" / "holdout_manifest.json").write_text(json.dumps(man))
        (t / "out" / "holdout_manifest.sha256").write_text(hb.sha256_file(t / "out" / "holdout_manifest.json") + "  holdout_manifest.json\n")
        js = [hj("ho-a"), hj("ho-b"), hj("ho-a2"), job("sneak", stage="screen", range=HO), job("x", stage="holdout", range={"preset": "2021-2024"})]
        js[2] = {**hj("ho-a"), "key": "ho-a", "inputs": {"tf": "15"}}               # same key (deduped) -> only the first line counts
        wrong = {**hj("ho-c"), "inputs": {"tf": "5"}}
        d, fake, clk = mk(t, [js[0], js[1], js[3], js[4], wrong], tue(11, 0), dur=10)
        d.loop(once=True, max_s=600)
        st = {k: v["status"] for k, v in d.jobs.items()}
        check("frozen key runs; unknown key / wrong stage / non-2025 holdout stage refused", st["ho-a"] == "done" and st["ho-b"] == "error"
              and st["sneak"] == "error" and st["x"] == "error" and st["ho-c"] == "error" and len(fake.posts) == 1)
        check("holdout ledger separate (ledger_holdout.csv, not ledger.csv)", (t / "ledger_holdout.csv").exists() and not (t / "ledger.csv").exists()
              and len(list(csv.DictReader((t / "ledger_holdout.csv").open()))) == 1)
        check("holdout run counted in the screening-run cap", "screening runs 1/400," in (t / "progress.md").read_text()
              and "2025+ frozen-manifest runs started: 1" in (t / "progress.md").read_text())
        why = hb.holdout_refusal("nq", {**hj("ho-a"), "inputs": {"tf": "15"}}, {"nq": t})
        check("spec drift from the manifest line refused", why is not None and "inputs differs" in why)
        (t / "out" / "holdout_manifest.json").write_text(json.dumps({**man, "jobs": man["jobs"] + [{"key": "ho-z"}]}))
        check("manifest edited after the freeze: all holdout jobs refused", "sha256" in (hb.holdout_refusal("nq", hj("ho-a"), {"nq": t}) or ""))
        q = t / "q.jsonl"
        q.write_text(json.dumps(job("sneak", stage="screen", range=HO)) + "\n")
        try:
            hb.cmd_submit(str(q))
            check("cmd_submit refuses a 2025+ non-holdout line", False)
        except SystemExit as e:
            check("cmd_submit refuses a 2025+ non-holdout line", "HOLDOUT GUARD" in str(e))

    print("DRY-RUN", "OK" if all(ok) else "FAILED", f"({sum(ok)}/{len(ok)})")
    return 0 if all(ok) else 1
